const getApiBaseUrl = () => {
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }

  if (typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }

  return "http://127.0.0.1:8000";
};

export type JsonObject = Record<string, unknown>;

export interface AppliancePayload extends JsonObject {
  name: string;
  matter_device_id: string;
  matter_device_ip: string;
  matter_device_port: number;
  matter_node_id?: number | null;
  device_type: string;
  power_usage_kw: number;
  duration_seconds: number;
  deadline?: string;
}

export interface SchedulePayload extends JsonObject {
  appliance_id: string;
  is_daily: boolean;
  deadline_override: string;
  household: JsonObject;
}

export interface HouseholdPayload extends JsonObject {
  household_type?: string;
  location_latitude?: number;
  location_longitude?: number;
  country_code?: string;
  bidding_zone?: string;
  pv_capacity_kw?: number;
}

export async function fetchFromApi<T = unknown>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const apiBaseUrl = getApiBaseUrl();
  let response: Response;

  try {
    response = await fetch(`${apiBaseUrl}${endpoint}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
    });
  } catch {
    throw new Error(`Could not reach Weaver backend at ${apiBaseUrl}. Make sure Weaver is still running.`);
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || "API request failed");
  }

  return response.json() as Promise<T>;
}

export const weaverApi = {
  // Appliances
  getAppliances: () => fetchFromApi("/appliances"),
  registerAppliance: (data: AppliancePayload) => fetchFromApi("/appliances", {
    method: "POST",
    body: JSON.stringify(data),
  }),
  deleteAppliance: (id: string) => fetchFromApi(`/appliances/${id}`, {
    method: "DELETE",
  }),
  getApplianceStatus: (id: string) => fetchFromApi(`/appliances/${id}/status`),
  runApplianceNow: (applianceId: string) => fetchFromApi(`/appliances/${applianceId}/run-now`, {
    method: "POST",
  }),
  
  // Schedules
  getSchedules: () => fetchFromApi("/schedules"),
  createSchedule: (data: SchedulePayload) => fetchFromApi("/schedule/grid-only", {
    method: "POST",
    body: JSON.stringify(data),
  }),
  createSolarSchedule: (data: SchedulePayload) => fetchFromApi("/schedule/grid-pv", {
    method: "POST",
    body: JSON.stringify(data),
  }),
  deleteSchedule: (jobId: string) => fetchFromApi(`/schedules/${jobId}`, {
    method: "DELETE",
  }),

  // Market/Prices
  getCurrentPrice: (zone: string, lat?: number, lng?: number) => 
    fetchFromApi(`/prices/current/${zone}?lat=${lat || ""}&lng=${lng || ""}`),

  // Household
  getHousehold: (id: string) => fetchFromApi(`/households/${id}`),
  updateHousehold: (id: string, data: HouseholdPayload) => fetchFromApi(`/households/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  }),

  // Matter
  getDevices: () => fetchFromApi("/matter/devices"),
  commissionDevice: (code: string) => fetchFromApi("/commission", {
    method: "POST",
    body: JSON.stringify({ code }),
  }),
};
