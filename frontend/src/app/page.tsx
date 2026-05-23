"use client";

import React, { useEffect, useState, useSyncExternalStore } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Layers, Plus, Signal, RefreshCcw, MapPin, AlertCircle, Clock, Search, Zap, X, Sun, Info, Unplug } from "lucide-react";
import { cn } from "@/lib/utils";
import { weaverApi } from "@/lib/api";
import { Scanner } from "@/components/Scanner";
import { toast } from "sonner";

const EUROPE_BOUNDS = { lat: [34, 72], lng: [-25, 45] };
const ZONE_NAMES: Record<string, string> = {
  "10YDE-RWENET---I": "Germany",
  "10YFR-RTE------C": "France",
  "10YGB----------A": "United Kingdom",
  "10YIEA-TRAN------M": "Ireland",
  "10Y1001A1001A83F": "Germany (LU)",
  "10YPL-TSO------P": "Poland",
  "10YES-REE------0": "Spain",
  "10YIT-GRTN-----B": "Italy"
};

type Appliance = {
  id: string;
  name: string;
  power_usage_kw: number;
  duration_seconds: number;
  matter_device_id: string;
  matter_device_ip: string;
  matter_device_port: number;
  matter_node_id?: number | null;
  device_type?: string;
};

type HouseholdResponse = {
  household_type?: string | null;
  bidding_zone?: string | null;
  location_latitude?: number | null;
  location_longitude?: number | null;
};

type ScheduleJob = {
  job_id?: string;
  appliance_id: string;
  next_run_time?: string;
  start_time?: string;
  status?: string;
};

type SchedulesResponse = {
  jobs?: ScheduleJob[];
};

type CityResult = {
  id?: number;
  name: string;
  latitude: number;
  longitude: number;
  country_code: string;
  admin1?: string;
  country?: string;
};

type CurrentPrice = {
  price_per_kwh: number;
  start_time: string;
  is_real: boolean;
};

type ApplianceStatus = {
  appliance_id: string;
  is_on: boolean | null;
  state: string;
};

const getErrorMessage = (error: unknown) => error instanceof Error ? error.message : "Unknown error";
const CITY_STORAGE_KEY = "weaver.selectedCity";
const VIRTUAL_TEST_CODE = "WEAVER-TEST-LOAD";
const DEFAULT_FINISH_BY = "23:00";

const SUPPORTED_COUNTRIES = [
  "IE", "GB", "FR", "DE", "ES", "IT", "BE", "NL", "PT", "DK", "NO", "SE", "FI", "AT", "CH", "PL", "CZ", "HU", "RO", "GR"
];

const subscribeToCityStorage = (onStoreChange: () => void) => {
  window.addEventListener("storage", onStoreChange);
  window.addEventListener("weaver-city-change", onStoreChange);
  return () => {
    window.removeEventListener("storage", onStoreChange);
    window.removeEventListener("weaver-city-change", onStoreChange);
  };
};

const getStoredCity = () => window.localStorage.getItem(CITY_STORAGE_KEY);
const getServerCity = () => null;

export default function Home() {
  const [appliances, setAppliances] = useState<Appliance[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isScanning, setIsScanning] = useState(false);
  const [location, setLocation] = useState<{lat: number, lng: number} | null>(null);
  const [biddingZone, setBiddingZone] = useState<string | null>(null);
  const selectedCity = useSyncExternalStore(subscribeToCityStorage, getStoredCity, getServerCity);
  const [locationError, setLocationError] = useState<string | null>(null);
  const [currentPrice, setCurrentPrice] = useState<CurrentPrice | null>(null);
  const [householdType, setHouseholdType] = useState<"grid_only" | "grid_and_pv">("grid_only");
  const [showSolarInfo, setShowSolarInfo] = useState(false);
  const [isUpdatingSolarMode, setIsUpdatingSolarMode] = useState(false);
  const [showPriceToast, setShowPriceToast] = useState(false);
  const [isSearchingLocation, setIsSearchingLocation] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<CityResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);

  // Per-device UI states
  const [deadlines, setDeadlines] = useState<Record<string, string>>({});
  const [dailyToggles, setDailyToggles] = useState<Record<string, boolean>>({});
  const [schedules, setSchedules] = useState<ScheduleJob[]>([]);
  const [runningIds, setRunningIds] = useState<Set<string>>(new Set());
  const [virtualRunningIds, setVirtualRunningIds] = useState<Set<string>>(new Set());
  const [startingIds, setStartingIds] = useState<Set<string>>(new Set());
  const [schedulingIds, setSchedulingIds] = useState<Set<string>>(new Set());

  // Debug schedules
  useEffect(() => {
    if (schedules.length > 0) {
      console.log("Current Schedules from Backend:", schedules);
      console.log("Current Appliances in UI:", appliances.map(a => ({ id: a.id, name: a.name })));
    }
  }, [schedules, appliances]);

  useEffect(() => {
    fetchData();
  }, []);

  // Autocomplete search
  useEffect(() => {
    const timer = setTimeout(() => {
      if (searchQuery.length >= 2) {
        handleCitySearch();
      } else {
        setSearchResults([]);
      }
    }, 400); // Debounce
    return () => clearTimeout(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchQuery]);

  // Polling for schedules and prices
  useEffect(() => {
    const pollInterval = setInterval(() => {
      fetchData();
    }, 10000); // Every 10 seconds
    return () => clearInterval(pollInterval);
  }, [biddingZone, location]);

  const hasCitySet = Boolean(location && biddingZone);
  const cityDisplay = selectedCity || (hasCitySet ? ZONE_NAMES[biddingZone || ""] || "Selected city" : null);
  const priceSourceLabel = currentPrice?.is_real ? "Live price" : "Estimated fallback price";
  const isVirtualAppliance = (app: Appliance) => app.device_type === "virtual_load" || app.matter_device_id.startsWith("virtual_");
  const isApplianceRunning = (app: Appliance) => runningIds.has(app.id) || virtualRunningIds.has(app.id);

  async function fetchData() {
    try {
      const [devices, h, scheds] = await Promise.all([
        weaverApi.getAppliances() as Promise<Appliance[]>,
        weaverApi.getHousehold("house_1").catch(() => null) as Promise<HouseholdResponse | null>,
        weaverApi.getSchedules().catch(() => ({ jobs: [] })) as Promise<SchedulesResponse>
      ]);
      setAppliances(devices);
      const liveSchedules = scheds.jobs || [];
      setSchedules(liveSchedules);
      const statuses = await Promise.all(
        devices.map((device) => weaverApi.getApplianceStatus(device.id).catch(() => null) as Promise<ApplianceStatus | null>)
      );
      setRunningIds(new Set(
        statuses
          .filter((status): status is ApplianceStatus => Boolean(status?.is_on))
          .map((status) => status.appliance_id)
      ));
      if (h) {
        setHouseholdType(h.household_type === "grid_and_pv" ? "grid_and_pv" : "grid_only");
        if (h.location_latitude && h.location_longitude) {
          setBiddingZone(h.bidding_zone ?? null);
          setLocation({ lat: h.location_latitude, lng: h.location_longitude });
        } else {
          setBiddingZone(null);
          setLocation(null);
        }
        if (h.bidding_zone && h.location_latitude && h.location_longitude) {
          const price = await weaverApi.getCurrentPrice(h.bidding_zone, h.location_latitude, h.location_longitude).catch(() => null) as CurrentPrice | null;
          setCurrentPrice(price);
        } else {
          setCurrentPrice(null);
        }
      }
      
      // Initialize UI states
      setDeadlines(prev => {
        const next = { ...prev };
        devices.forEach((dev) => {
          if (!next[dev.id]) next[dev.id] = "23:00";
        });
        if (JSON.stringify(next) === JSON.stringify(prev)) return prev;
        return next;
      });
      setDailyToggles(prev => {
        const next = { ...prev };
        devices.forEach((dev) => {
          if (next[dev.id] === undefined) next[dev.id] = false;
        });
        if (JSON.stringify(next) === JSON.stringify(prev)) return prev;
        return next;
      });
    } catch (error) {
      console.error(error);
    } finally {
      setIsLoading(false);
    }
  }

  const getCityLabel = (city: CityResult) => [city.name, city.admin1, city.country].filter(Boolean).join(", ");

  const processNewLocation = async (lat: number, lng: number, countryCode?: string, city?: CityResult) => {
    console.log("Processing city selection:", { lat, lng, countryCode, city });
    toast.info("Setting up your city...", { icon: <MapPin size={16} /> });
    setIsSearching(true);
    try {
      if (lat >= EUROPE_BOUNDS.lat[0] && lat <= EUROPE_BOUNDS.lat[1]) {
        // Sync with backend
        const res = await weaverApi.updateHousehold("house_1", { 
          location_latitude: lat, 
          location_longitude: lng,
          country_code: countryCode
        }) as { bidding_zone: string };
        
        // Success! Update states
        const cityLabel = city ? getCityLabel(city) : null;
        setLocation({ lat, lng });
        setBiddingZone(res.bidding_zone);
        if (typeof window !== "undefined") {
          if (cityLabel) {
            window.localStorage.setItem(CITY_STORAGE_KEY, cityLabel);
          } else {
            window.localStorage.removeItem(CITY_STORAGE_KEY);
          }
          window.dispatchEvent(new Event("weaver-city-change"));
        }
        setLocationError(null);
        setIsSearchingLocation(false); // Close immediately for snappiness

        // NUCLEAR OPTION: Browser-First Price Engine
        // Your backend is network-restricted, so we use your browser as a 'scout'
        let priceData: CurrentPrice | null = null;
        console.log("Browser scout: Attempting to fetch live prices...");
        
        try {
          // Route 1: Direct browser fetch (Open-Meteo is CORS-friendly!)
          const targetUrl = `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lng}&hourly=electricity_price&timezone=auto`;
          console.log("Browser scout: Attempting direct fetch from", targetUrl);
          
          const priceRes = await fetch(targetUrl);
          if (priceRes.ok) {
            const priceJson = await priceRes.json();
            if (priceJson.hourly && priceJson.hourly.electricity_price) {
              const times = priceJson.hourly.time;
              const prices = priceJson.hourly.electricity_price;
              
              const fullPrices = times.map((t: string, i: number) => ({
                start_time: t,
                price_per_kwh: (prices[i] || 0) / 1000.0,
                is_real: true
              }));

              const nowIdx = new Date().getHours();
              priceData = {
                price_per_kwh: prices[nowIdx] / 1000.0,
                start_time: new Date().toISOString(),
                is_real: true
              };

              // SYNC TO BACKEND: Tell the backend what we found!
              await weaverApi.syncPrices(res.bidding_zone, fullPrices);
              console.log("Browser scout: Success! Backend synchronized.");
              toast.success("Price data synchronized!", { icon: <Signal size={16} /> });
            }
          }
        } catch (e) {
          console.warn("Browser scout failed, checking backend cache...", e);
        }

        // If browser failed, check if backend has any cached/synced data
        if (!priceData) {
          try {
            priceData = await weaverApi.getCurrentPrice(res.bidding_zone, lat, lng) as CurrentPrice | null;
          } catch {
            // Backend cache miss is acceptable; the UI can still continue.
          }
        }

        setCurrentPrice(priceData);
        setShowPriceToast(true);
        setTimeout(() => setShowPriceToast(false), 5000);
      } else {
        setLocationError("outside_europe");
      }
    } catch (error: unknown) {
      const message = getErrorMessage(error);
      console.error("Location sync failed:", error);
      if (message.includes("outside_supported_region")) {
        setLocationError("outside_europe");
      } else {
        alert(`Location Sync Error: ${message}`);
      }
    } finally {
      setIsSearching(false);
    }
  };

  async function handleCitySearch() {
    if (!searchQuery) return;
    setIsSearching(true);
    try {
      const res = await fetch(`https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(searchQuery)}&count=20&language=en&format=json`);
      const data = await res.json();
      
      // Filter results to only include cities in supported countries
      const filtered = (data.results || []).filter((city: CityResult) => 
        SUPPORTED_COUNTRIES.includes(city.country_code)
      );
      
      setSearchResults(filtered.slice(0, 5)); // Show top 5 valid ones
    } catch (error) {
      console.error("Search failed:", error);
      setSearchResults([]);
      // Don't alert on every keystroke failure, just log it.
    } finally {
      setIsSearching(false);
    }
  }

  const toggleQueue = (id: string) => {
    if (hasCitySet) {
      handleSetSchedule(id);
      return;
    }
    toast.info("Choose a city to enable price scheduling.");
  };

  const handleSolarModeToggle = async () => {
    const nextType = householdType === "grid_and_pv" ? "grid_only" : "grid_and_pv";
    setHouseholdType(nextType);
    setIsUpdatingSolarMode(true);
    try {
      await weaverApi.updateHousehold("house_1", {
        household_type: nextType,
        pv_capacity_kw: nextType === "grid_and_pv" ? 5 : 0,
      });
      toast.success(nextType === "grid_and_pv" ? "Solar + grid enabled" : "Grid only enabled", {
        icon: nextType === "grid_and_pv" ? <Sun size={16} /> : <Signal size={16} />,
      });
    } catch (error) {
      setHouseholdType(householdType);
      toast.error(`Could not update energy mode: ${getErrorMessage(error)}`);
    } finally {
      setIsUpdatingSolarMode(false);
    }
  };

  const handleRunNow = async (applianceId: string) => {
    const app = appliances.find(a => a.id === applianceId);
    if (app && isVirtualAppliance(app)) {
      setVirtualRunningIds(prev => new Set(prev).add(applianceId));
      toast.success(`${app.name} started for UI testing`, {
        icon: <Zap size={16} />,
        style: { borderRadius: '16px', background: '#187b8f', color: '#fff', fontWeight: 'bold' },
      });
      window.setTimeout(() => {
        setVirtualRunningIds(prev => {
          const next = new Set(prev);
          next.delete(applianceId);
          return next;
        });
      }, 30000);
      return;
    }

    setStartingIds(prev => new Set(prev).add(applianceId));
    try {
      await weaverApi.runApplianceNow(applianceId);
      setRunningIds(prev => new Set(prev).add(applianceId));
      toast.success(`${app?.name || "Device"} started!`, {
        icon: <Zap size={16} />,
        style: { borderRadius: '16px', background: '#187b8f', color: '#fff', fontWeight: 'bold' },
      });
      // Refresh to show running status
      fetchData();
    } catch (error: unknown) {
      toast.error(`Failed to start device: ${getErrorMessage(error)}`);
    } finally {
      setStartingIds(prev => {
        const next = new Set(prev);
        next.delete(applianceId);
        return next;
      });
    }
  };

  const handleDisconnect = async (id: string) => {
    if (!confirm("Are you sure you want to completely disconnect this appliance?")) return;
    try {
      await weaverApi.deleteAppliance(id);
      toast.success("Device disconnected");
      // Immediate local update for snappy UI
      setAppliances(prev => prev.filter(a => a.id !== id));
      setRunningIds(prev => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
      await fetchData();
    } catch (error) {
      console.error("Disconnect failed:", error);
      toast.error("Could not disconnect device");
    }
  };

  const handleSetSchedule = async (id: string) => {
    if (!hasCitySet) {
      toast.error("Choose a city before scheduling.");
      return;
    }

    setSchedulingIds(prev => new Set(prev).add(id));
    try {
      const selectedDeadline = deadlines[id] || DEFAULT_FINISH_BY;
      const [deadlineHour, deadlineMinute] = selectedDeadline.split(":").map(Number);
      if (
        Number.isNaN(deadlineHour) ||
        Number.isNaN(deadlineMinute) ||
        deadlineHour < 0 ||
        deadlineHour > 23 ||
        deadlineMinute < 0 ||
        deadlineMinute > 59
      ) {
        toast.error("Choose a valid finish-by time.");
        return;
      }

      const deadline = new Date();
      deadline.setHours(deadlineHour, deadlineMinute, 0, 0);
      if (deadline <= new Date()) {
        deadline.setDate(deadline.getDate() + 1);
      }

      const solarMode = householdType === "grid_and_pv";
      const schedulePayload = {
        appliance_id: id,
        is_daily: dailyToggles[id],
        deadline_override: deadline.toISOString(),
        household: { 
          id: "house_1", 
          household_type: householdType,
          bidding_zone: biddingZone,
          location_latitude: location?.lat,
          location_longitude: location?.lng,
          pv_capacity_kw: solarMode ? 5 : 0,
        }
      };
      await (solarMode ? weaverApi.createSolarSchedule(schedulePayload) : weaverApi.createSchedule(schedulePayload));
      // Refresh schedules immediately
      const scheds = await weaverApi.getSchedules().catch(() => ({ jobs: [] })) as SchedulesResponse;
      setSchedules(scheds.jobs || []);
      const scheduled = scheds.jobs?.find(s => String(s.appliance_id) === String(id));
      const runTime = scheduled?.next_run_time ?? scheduled?.start_time;
      if (runTime) {
        toast.success(`Scheduled for ${new Date(runTime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`);
      }
    } catch (error) {
      toast.error(`Could not schedule run: ${getErrorMessage(error)}`);
    } finally {
      setSchedulingIds(prev => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  };

  const onScanSuccess = async (scannedData: string) => {
    try {
      const setupCode = scannedData.trim();
      if (setupCode.toUpperCase() === VIRTUAL_TEST_CODE) {
        const existingVirtual = appliances.find(isVirtualAppliance);
        if (existingVirtual) {
          toast.success(`${existingVirtual.name} is already connected`);
          setIsScanning(false);
          await fetchData();
          return;
        }

        await weaverApi.registerAppliance({
          name: "Virtual test load",
          matter_device_id: "virtual_test_load",
          matter_device_ip: "127.0.0.1",
          matter_device_port: 1,
          matter_node_id: null,
          device_type: "virtual_load",
          power_usage_kw: 0.8,
          duration_seconds: 45 * 60,
          deadline: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
        });
        toast.success("Virtual test load added for scheduling");
        await fetchData();
        setIsScanning(false);
        return;
      }

      // Detection: Is it a real Matter commissioning code?
      const isMatterCode = setupCode.startsWith("MT:") || /^\d{11,21}$/.test(setupCode);

      if (isMatterCode) {
        toast.info("Pairing with Matter appliance...");
        try {
          const result = await weaverApi.commissionDevice(setupCode) as { status?: string; name?: string; message?: string };
          if (result.status === "success") {
            toast.success(`Successfully paired: ${result.name || "New Device"}`);
            await fetchData();
            setIsScanning(false);
          } else {
            throw new Error(result.message || "Could not identify device type");
          }
        } catch (error: unknown) {
          console.error("Commissioning error:", error);
          const message = getErrorMessage(error) || "Failed to pair. Check if device is in pairing mode.";
          toast.error(message);
          throw new Error(message);
        }
      } else {
        const message = "Enter an 11-21 digit Matter setup code or an MT: QR payload.";
        toast.error(message);
        throw new Error(message);
      }
      
      await fetchData();
    } catch (error: unknown) {
      console.error("Pairing failed:", error);
      throw error instanceof Error ? error : new Error(`Pairing failed: ${getErrorMessage(error)}`);
    }
  };

  const getScheduleTime = (appId: string) => {
    const schedule = schedules.find(s => String(s.appliance_id) === String(appId));
    const runTime = schedule?.next_run_time ?? schedule?.start_time;
    return runTime ? new Date(runTime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : null;
  };

  const getSchedule = (appId: string) => schedules.find(s => String(s.appliance_id) === String(appId));

  const queueAppliances = [...appliances].sort((a, b) => {
    const aRunning = isApplianceRunning(a);
    const bRunning = isApplianceRunning(b);
    if (aRunning !== bRunning) return aRunning ? -1 : 1;

    const aScheduled = Boolean(getSchedule(a.id));
    const bScheduled = Boolean(getSchedule(b.id));
    if (aScheduled !== bScheduled) return aScheduled ? -1 : 1;

    return a.name.localeCompare(b.name);
  }).filter((app) => isApplianceRunning(app) || Boolean(getSchedule(app.id)));

  const connectedAppliances = [...appliances].sort((a, b) => {
    const aRunning = isApplianceRunning(a);
    const bRunning = isApplianceRunning(b);
    if (aRunning !== bRunning) return aRunning ? -1 : 1;
    return a.name.localeCompare(b.name);
  });

  return (
    <div className="min-h-screen px-5 pt-10 pb-32 max-w-lg mx-auto relative overflow-x-hidden">
      <AnimatePresence>
        {isScanning && <Scanner key="scanner-overlay" onScan={onScanSuccess} onClose={() => setIsScanning(false)} />}
        
        {isSearchingLocation && (
          <motion.div 
            key="location-search-overlay"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-[150] bg-background p-6 flex flex-col"
          >
            <div className="flex justify-between items-center mb-10">
              <div>
                <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-slate-400">City setup</p>
                <h2 className="text-3xl font-bold tracking-tight text-slate-950">Choose city</h2>
              </div>
              <button onClick={() => setIsSearchingLocation(false)} className="p-3 bg-white border border-slate-200 rounded-lg text-slate-500 hover:text-red-500 transition-colors shadow-sm">
                <X size={24} />
              </button>
            </div>

            <div className="space-y-6">
              <div className="relative">
                <Search className="absolute left-6 top-1/2 -translate-y-1/2 text-slate-300" size={20} />
                <input 
                  type="text"
                  placeholder="Search city (e.g. Paris, Berlin...)"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleCitySearch()}
                  className="w-full h-14 organic-card !rounded-lg pl-14 pr-5 font-semibold text-slate-800 placeholder:text-slate-400 focus:outline-none focus:border-primary transition-colors"
                />
              </div>

              <div className="space-y-3">
                {searchResults.map((city, idx) => (
                  <motion.button 
                    key={city.id || `city-${idx}`}
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      processNewLocation(city.latitude, city.longitude, city.country_code, city);
                    }}
                    className="w-full p-4 organic-card !rounded-lg flex items-center justify-between hover:bg-blue-50/60 transition-all cursor-pointer relative z-[10]"
                  >
                    <div className="flex items-center gap-4">
                      <MapPin size={18} className="text-primary" />
                      <div className="text-left">
                        <h4 className="font-bold text-slate-950">{city.name}</h4>
                        <p className="text-[10px] text-slate-500 uppercase font-bold tracking-widest">{city.admin1}, {city.country}</p>
                      </div>
                    </div>
                    {isSearching && <RefreshCcw className="animate-spin text-primary" size={16} />}
                  </motion.button>
                ))}
                {isSearching && searchQuery.length >= 2 && searchResults.length === 0 && (
                  <div className="text-center py-8 text-slate-300 font-bold animate-pulse">Searching cities...</div>
                )}
              </div>
            </div>
          </motion.div>
        )}

        {showPriceToast && currentPrice && (
          <motion.div 
            key="price-toast-overlay"
            initial={{ opacity: 0, y: -100 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -100 }}
            className="fixed top-8 left-1/2 -translate-x-1/2 z-[200] w-[calc(100%-3rem)] max-w-sm"
          >
            <div className="bg-blue-950 text-white p-5 rounded-lg shadow-lg flex items-center gap-5 border border-white/10">
              <div className="w-14 h-14 rounded-lg bg-teal-500 flex items-center justify-center text-white shrink-0 shadow-lg">
                <Signal size={28} />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <h3 className="text-[10px] font-bold uppercase tracking-widest text-teal-300">
                    {priceSourceLabel}
                  </h3>
                  <span className={cn(
                    "px-2 py-0.5 rounded-full text-[8px] font-bold uppercase tracking-wide",
                    currentPrice.is_real ? "bg-teal-500/20 text-teal-300" : "bg-amber-500/20 text-amber-300"
                  )}>
                    {currentPrice.is_real ? "Live" : "Fallback"}
                  </span>
                </div>
                <p className="text-2xl font-bold tabular-nums">
                  {currentPrice.price_per_kwh.toFixed(2)}<span className="text-xs ml-1 opacity-60">EUR/kWh</span>
                </p>
                <p className="text-[9px] text-slate-400 uppercase font-bold mt-1">
                  {currentPrice.is_real ? "From" : "Estimated for"} {cityDisplay || "selected city"}
                </p>
              </div>
            </div>
          </motion.div>
        )}

        {locationError && (
          <div key="location-error-overlay" className="fixed inset-0 z-[200] bg-background flex items-center justify-center p-12 text-center">
            <div className="space-y-4">
              <AlertCircle size={64} className="mx-auto text-red-400" />
              <h2 className="text-2xl font-bold">Europe only</h2>
              <button onClick={() => setLocationError(null)} className="btn-whimsical">Got it</button>
            </div>
          </div>
        )}
      </AnimatePresence>

      <header className="flex justify-between items-start mb-10">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.28em] text-slate-400 mb-2">Smart energy scheduler</p>
          <h1 className="text-5xl font-bold text-slate-950 tracking-tight">Weaver</h1>
          <button 
            onClick={() => setIsSearchingLocation(true)} 
            className="mt-4 flex items-center gap-2 px-4 py-3 bg-white rounded-lg border border-slate-200 shadow-sm text-xs font-bold text-slate-600 uppercase tracking-widest hover:border-primary hover:text-primary transition-all active:scale-95"
          >
            <MapPin size={14} className="text-primary" /> 
            {cityDisplay || "Choose City"}
          </button>
        </div>
      </header>

      <main className="space-y-6">
        {!isLoading && (
          <section className="space-y-3">
            <button
              onClick={() => setIsSearchingLocation(true)}
              className="organic-card p-4 text-left hover:border-primary w-full"
            >
              <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">City</p>
              <p className="mt-2 text-lg font-bold text-slate-950">{cityDisplay || "Choose city"}</p>
              <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">
                {hasCitySet ? "Price scheduling enabled" : "Choose city to enable price scheduling"}
              </p>
              {currentPrice && (
                <p className="mt-3 text-xs font-bold text-primary">
                  {priceSourceLabel}: {currentPrice.price_per_kwh.toFixed(3)} EUR/kWh
                </p>
              )}
            </button>
            <div className="organic-card p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-3 min-w-0">
                  <div className={cn(
                    "w-10 h-10 rounded-lg flex items-center justify-center shrink-0",
                    householdType === "grid_and_pv" ? "bg-amber-50 text-amber-600" : "bg-slate-100 text-slate-500"
                  )}>
                    <Sun size={20} />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">Energy mode</p>
                      <button
                        type="button"
                        onClick={() => setShowSolarInfo(value => !value)}
                        className="text-slate-400 hover:text-primary"
                        aria-label="Solar mode info"
                      >
                        <Info size={14} />
                      </button>
                    </div>
                    <p className="mt-1 text-lg font-bold text-slate-950">
                      {householdType === "grid_and_pv" ? "Solar + grid" : "Grid only"}
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={handleSolarModeToggle}
                  disabled={isUpdatingSolarMode}
                  className={cn(
                    "relative mt-2 h-8 w-14 rounded-full border transition-colors shrink-0",
                    householdType === "grid_and_pv" ? "bg-amber-400 border-amber-400" : "bg-slate-200 border-slate-200",
                    isUpdatingSolarMode && "opacity-60"
                  )}
                  aria-pressed={householdType === "grid_and_pv"}
                  aria-label={householdType === "grid_and_pv" ? "I have solar panels" : "I don't have solar panels"}
                >
                  <span className={cn(
                    "absolute left-0.5 top-0.5 h-7 w-7 rounded-full bg-white shadow-sm transition-transform",
                    householdType === "grid_and_pv" ? "translate-x-6" : "translate-x-0"
                  )} />
                </button>
              </div>
              <p className="mt-3 text-[10px] font-bold uppercase tracking-widest text-slate-500">
                {householdType === "grid_and_pv" ? "I have solar panels" : "I don't have solar panels"}
              </p>
              {showSolarInfo && (
                <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs font-semibold text-amber-900">
                  Solar + grid mode prioritizes running flexible appliances when your panels are forecast to produce more energy, then falls back to grid price optimization.
                </div>
              )}
            </div>
          </section>
        )}

        {isLoading ? (
          <div className="text-center py-20 animate-pulse text-slate-400 font-bold uppercase tracking-widest text-xs">Loading Weaver...</div>
        ) : appliances.length === 0 ? (
          <div className="organic-card p-8 text-center space-y-5 border-dashed border-slate-300">
            <div className="w-14 h-14 bg-slate-100 rounded-lg flex items-center justify-center mx-auto text-slate-400">
              <Layers size={28} />
            </div>
            <h3 className="font-bold text-slate-700">No devices connected</h3>
            <button onClick={() => setIsScanning(true)} className="btn-whimsical w-full">Connect Device</button>
          </div>
        ) : (
          <>
          <section className="space-y-3">
            <div>
              <h2 className="text-[11px] font-bold uppercase tracking-[0.24em] text-slate-500">Run queue</h2>
              <p className="text-xs text-slate-500 mt-1">Running devices stay on top. Scheduled devices wait below them.</p>
            </div>

            {queueAppliances.map((app, index) => {
              const isVirtual = isVirtualAppliance(app);
              const isRunning = isApplianceRunning(app);
              const scheduleTime = getScheduleTime(app.id);
              const hasSchedule = Boolean(getSchedule(app.id));
              const statusLabel = isRunning ? "Running" : hasSchedule ? "Scheduled" : "Ready";
              const statusText = isRunning
                ? "Appliance reports active through Matter."
                : scheduleTime
                  ? `Scheduled start: ${scheduleTime}`
                  : hasCitySet
                    ? "Ready for optimized scheduling."
                    : isVirtual
                      ? "Ready for scheduling tests."
                      : "Ready for direct Matter control.";

              return (
                <motion.article
                  key={app.id}
                  layout
                  className={cn(
                    "organic-card p-4 space-y-4",
                    isRunning && "border-primary shadow-[0_12px_28px_rgba(37,99,235,0.16)]"
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-start gap-3 min-w-0">
                      <div className={cn(
                        "w-10 h-10 rounded-lg flex items-center justify-center shrink-0",
                        isRunning ? "bg-primary text-white" : "bg-slate-100 text-slate-500"
                      )}>
                        {isRunning ? <Zap size={20} fill="currentColor" /> : <Layers size={20} />}
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] font-bold text-slate-400 tabular-nums">#{index + 1}</span>
                          <h3 className="font-bold text-slate-950 truncate">{app.name}</h3>
                        </div>
                        <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">{isVirtual ? "Virtual scheduling test" : `Matter node ${app.matter_node_id ?? "unknown"}`}</p>
                      </div>
                    </div>
                    <span className={cn(
                      "px-2 py-1 rounded-md text-[10px] font-bold uppercase tracking-widest",
                      isRunning ? "bg-blue-50 text-primary" : hasSchedule ? "bg-teal-50 text-teal-700" : "bg-slate-100 text-slate-500"
                    )}>
                      {statusLabel}
                    </span>
                  </div>

                  <div className="border border-slate-200 rounded-lg p-3">
                    <p className="text-sm font-semibold text-slate-700">{statusText}</p>
                    {scheduleTime && (
                      <p className="mt-1 text-xs font-semibold text-primary">Turns on at {scheduleTime}</p>
                    )}
                  </div>
                </motion.article>
              );
            })}
          </section>

          <section className="space-y-3">
            <div className="flex justify-between items-center gap-3">
              <div>
                <h2 className="text-[11px] font-bold uppercase tracking-[0.24em] text-slate-500">All connected devices</h2>
                <p className="text-xs text-slate-500 mt-1">Every paired appliance appears here, whether idle, scheduled, or running.</p>
              </div>
              <button
                onClick={() => setIsScanning(true)}
                className="w-10 h-10 rounded-lg bg-primary text-white flex items-center justify-center shadow-sm shrink-0"
                title="Connect device"
              >
                <Plus size={18} />
              </button>
            </div>

            {connectedAppliances.map((app) => {
              const isVirtual = isVirtualAppliance(app);
              const isRunning = isApplianceRunning(app);
              const scheduleTime = getScheduleTime(app.id);
              const status = isRunning ? "Running" : scheduleTime ? `Starts ${scheduleTime}` : "Idle";

              return (
                <motion.article key={`connected-${app.id}`} layout className="organic-card p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className={cn(
                        "w-9 h-9 rounded-lg flex items-center justify-center shrink-0",
                        isRunning ? "bg-primary text-white" : "bg-slate-100 text-slate-500"
                      )}>
                        {isRunning ? <Zap size={18} fill="currentColor" /> : <Layers size={18} />}
                      </div>
                      <div className="min-w-0">
                        <h3 className="font-bold text-slate-950 truncate">{app.name}</h3>
                        <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">{isVirtual ? "Virtual" : `Node ${app.matter_node_id ?? "unknown"}`} | {status}</p>
                        {scheduleTime && (
                          <p className="mt-1 text-xs font-semibold text-primary">Turns on at {scheduleTime}</p>
                        )}
                      </div>
                    </div>
                    <div className="flex gap-2 shrink-0">
                      <button
                        onClick={() => handleRunNow(app.id)}
                        disabled={startingIds.has(app.id)}
                        className="h-10 px-3 rounded-lg bg-primary text-white font-bold text-[10px] uppercase tracking-widest disabled:opacity-60"
                      >
                        {startingIds.has(app.id) ? "Starting" : "Run now"}
                      </button>
                    </div>
                  </div>
                  {hasCitySet ? (
                    <div className="mt-3 grid grid-cols-[1fr_auto] gap-2">
                      <label className="space-y-1">
                        <span className="text-[10px] font-bold uppercase tracking-widest text-slate-500 flex items-center gap-1">
                          <Clock size={11} /> Must finish by
                        </span>
                        <input
                          type="time"
                          value={deadlines[app.id] ?? DEFAULT_FINISH_BY}
                          onChange={(e) => setDeadlines({ ...deadlines, [app.id]: e.target.value })}
                          className="w-full h-10 px-3 rounded-lg bg-white border border-slate-200 focus:border-primary font-semibold text-slate-800 outline-none"
                        />
                      </label>
                      <button
                        onClick={() => toggleQueue(app.id)}
                        disabled={schedulingIds.has(app.id)}
                        className="self-end h-10 px-4 rounded-lg bg-slate-100 text-slate-600 font-bold text-[10px] uppercase tracking-widest hover:bg-slate-200 disabled:opacity-60"
                      >
                        {schedulingIds.has(app.id) ? "Scheduling" : scheduleTime ? "Update" : "Schedule run"}
                      </button>
                    </div>
                  ) : null}
                  <div className="mt-3 pt-3 border-t border-slate-100 flex justify-end">
                    <button
                      onClick={() => handleDisconnect(app.id)}
                      className="inline-flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-slate-500 hover:text-red-600"
                    >
                      <Unplug size={13} />
                      Disconnect appliance
                    </button>
                  </div>
                </motion.article>
              );
            })}
          </section>
          </>
        )}
      </main>

      <footer className="mt-20 text-center opacity-50 flex flex-col items-center gap-2">
        <div className="w-10 h-px bg-slate-400"></div>
        <p className="text-[9px] font-bold uppercase tracking-[0.32em] text-slate-500">Weaver v1.0</p>
      </footer>
    </div>
  );
}
