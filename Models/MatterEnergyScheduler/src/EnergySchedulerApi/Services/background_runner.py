import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from EnergySchedulerApi.Services.matter_controller import MatterController
from EnergySchedulerApi.Services.appliance_registry import ApplianceRegistry
from EnergySchedulerApi.Services.database_service import DatabaseService
from EnergySchedulerApi.Services.cleanup_service import CleanupService
from EnergySchedulerApi.Models.scheduled_appliance import ScheduledAppliance

logger = logging.getLogger(__name__)

class BackgroundRunnerService:
    def __init__(self, matter_controller: MatterController, appliance_registry: ApplianceRegistry, db_service: DatabaseService, cleanup_service: CleanupService):
        self.scheduler = AsyncIOScheduler(jobstores={'default': MemoryJobStore()})
        self.matter_controller = matter_controller
        self.appliance_registry = appliance_registry
        self.db_service = db_service
        self.cleanup_service = cleanup_service

    def start(self):
        if not self.scheduler.running:
            self.scheduler.start()
            self._recover_jobs()
            self._schedule_cleanup()
            logger.info("Background Runner Scheduler started (Jobs recovered, Cleanup scheduled).")

    def _schedule_cleanup(self):
        """Schedule the daily cleanup task"""
        self.scheduler.add_job(
            self.cleanup_service.run_cleanup,
            'interval',
            days=1,
            id='daily_data_cleanup',
            replace_existing=True
        )
        # Also run once on startup
        self.scheduler.add_job(
            self.cleanup_service.run_cleanup,
            'date',
            run_date=datetime.now(),
            id='startup_cleanup'
        )

    def _recover_jobs(self):
        """Recover pending jobs from the database on startup"""
        pending = self.db_service.get_pending_schedules()
        for p in pending:
            # Only recover future jobs
            if p["start_time"] > datetime.now():
                self.scheduler.add_job(
                    self._run_appliance_task,
                    'date',
                    run_date=p["start_time"],
                    args=[p["appliance_id"], p["job_id"], p.get("is_daily", False)],
                    id=p["job_id"],
                    replace_existing=True
                )
                logger.info(f"Recovered job {p['job_id']} for appliance {p['appliance_id']} at {p['start_time']}")
            else:
                self.db_service.update_schedule_status(p["job_id"], "missed")

    def stop(self):
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Background Runner Scheduler stopped.")

    def schedule_appliance(self, appliance_id: str, start_time: datetime, duration: int, power: float, is_daily: bool = False):
        """Schedules an appliance to run at the given start_time"""
        job_id = f"job_run_{appliance_id}_{start_time.timestamp()}"
        
        # Don't schedule in the past
        if start_time < datetime.now():
            logger.warning(f"Start time {start_time} is in the past. Running immediately.")
            start_time = datetime.now()

        # Save to DB first
        self.db_service.save_schedule(
            ScheduledAppliance(
                appliance_id=appliance_id,
                start_time=start_time,
                duration_seconds=duration,
                power_usage_kw=power
            ),
            job_id=job_id,
            is_daily=is_daily
        )

        self.scheduler.add_job(
            self._run_appliance_task,
            'date',
            run_date=start_time,
            args=[appliance_id, job_id, is_daily],
            id=job_id,
            replace_existing=True
        )
        logger.info(f"Scheduled appliance {appliance_id} to run at {start_time}")
        return job_id

    def get_scheduled_jobs(self):
        jobs = []
        raw_jobs = self.scheduler.get_jobs()
        logger.info(f"BackgroundRunner: Found {len(raw_jobs)} raw jobs in APScheduler.")
        for job in raw_jobs:
            app_id = job.args[0] if job.args else "UNKNOWN"
            logger.info(f"  - Job ID: {job.id}, Appliance ID: {app_id}, Next Run: {job.next_run_time}")
            jobs.append({
                "job_id": job.id,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "appliance_id": app_id
            })
        return jobs

    def cancel_job(self, job_id: str):
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            self.db_service.update_schedule_status(job_id, "cancelled")
            logger.info(f"Cancelled job {job_id}")
            return True
        return False

    async def _run_appliance_task(self, appliance_id: str, job_id: str, is_daily: bool = False):
        """The actual task that runs at start_time"""
        try:
            logger.info(f"Executing scheduled run for appliance: {appliance_id} (Job: {job_id})")
            appliance = self.appliance_registry.get_appliance(appliance_id)
            
            self.db_service.update_schedule_status(job_id, "running")

            # Send immediate run command via Matter
            target_id = appliance.matter_node_id if appliance.matter_node_id is not None else appliance.matter_device_id
            await self.matter_controller.send_command(
                target_id,
                "run_now",
                {
                    "duration_seconds": appliance.duration_seconds,
                    "power_kw": appliance.power_usage_kw
                }
            )
            self.db_service.update_schedule_status(job_id, "completed")
            logger.info(f"Successfully sent run command for appliance {appliance_id}")

            # Handle Learning (Recording) - Only record if we don't have a signature yet
            if not appliance.power_profile:
                logger.info(f"No signature found for {appliance_id}. Starting one-time Learn Cycle...")
                self.scheduler.add_job(
                    self._record_power_profile,
                    'interval',
                    minutes=5,
                    args=[appliance_id, appliance.duration_seconds],
                    id=f"record_{appliance_id}"
                )

            # Handle Daily Recurrence
            if is_daily:
                await self._schedule_next_daily_run(appliance_id, job_id)

        except Exception as e:
            self.db_service.update_schedule_status(job_id, "failed")
            logger.error(f"Failed to execute scheduled run for appliance {appliance_id}: {str(e)}")

    async def _schedule_next_daily_run(self, appliance_id: str, old_job_id: str):
        """Calculates and schedules the next run for a daily task (12h window before next deadline)"""
        try:
            with self.db_service.get_db() as db:
                from EnergySchedulerApi.Infrastructure.db_models import DmSchedule
                old_schedule = db.query(DmSchedule).filter(DmSchedule.job_id == old_job_id).first()
                if not old_schedule:
                    return

                # Find the next deadline by adding 1 day to the previous target date
                # and keeping the same time of day as the 'Deadline'.
                # For now, we use the old_schedule.start_time as a reference for the cycle.
                
                # To ensure a 12-hour gap, the NEXT window must start 24 hours after the PREVIOUS window started.
                # If current window was [7am Tue, 7pm Tue], next is [7am Wed, 7pm Wed].
                
                # We calculate the next window start as exactly 24h after the 'hinted' window start.
                # Assuming the previous run was in a 12h window ending at a deadline:
                # We'll just shift the entire schedule forward by exactly 24 hours.
                
                next_run_time = old_schedule.start_time + timedelta(days=1)
                
                logger.info(f"Daily Recurrence for {appliance_id}: Previous run was at {old_schedule.start_time}. Next run scheduled for {next_run_time} (maintaining 12h+ gap).")
                
                self.schedule_appliance(
                    appliance_id,
                    next_run_time,
                    old_schedule.duration_seconds,
                    old_schedule.power_usage_kw,
                    is_daily=True
                )
        except Exception as e:
            logger.error(f"Failed to schedule next daily run: {e}")

    async def _record_power_profile(self, appliance_id: str, total_duration_seconds: int):
        """Periodically pings the device to learn its power signature over time"""
        # Note: In a real implementation, this would accumulate points in a temporary buffer
        # and then aggregate them into 30-minute blocks once the run finishes.
        try:
            # For the prototype, we simulate a single reading
            # In a real Matter device, we'd call controller.read_attribute(cluster=0x0091)
            reading = await self.matter_controller.read_current_power(appliance_id)
            
            with self.db_service.get_db() as db:
                from EnergySchedulerApi.Infrastructure.db_models import DmAppliance
                app = db.query(DmAppliance).filter(DmAppliance.id == appliance_id).first()
                if app:
                    current_fingerprint = app.stored_fingerprint or []
                    # Simple moving average / update logic
                    current_fingerprint.append(reading)
                    # Limit to 48 intervals (24h)
                    app.stored_fingerprint = current_fingerprint[-48:]
                    db.commit()
                    logger.info(f"Learned new power data point for {appliance_id}: {reading}kW")
        except Exception as e:
            logger.error(f"Failed to record power data point: {e}")
