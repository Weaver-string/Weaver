"use client";

import React, { useEffect, useState, useSyncExternalStore } from "react";
import { motion } from "framer-motion";
import { Bell, KeyRound, MapPin, Network, Sun } from "lucide-react";
import { weaverApi, type LivePriceSettings } from "@/lib/api";

const CITY_STORAGE_KEY = "weaver.selectedCity";
const ZONE_NAMES: Record<string, string> = {
  "10Y1001A1001A82H": "Germany",
  "10YDE-RWENET---I": "Germany",
  "10YFR-RTE------C": "France",
  "10YGB----------A": "United Kingdom",
  "10YIEA-TRAN------M": "Ireland",
  "10Y1001A1001A83F": "Germany (LU)",
  "10YPL-TSO------P": "Poland",
  "10YES-REE------0": "Spain",
  "10YIT-GRTN-----B": "Italy",
};

type HouseholdResponse = {
  household_type?: string | null;
  bidding_zone?: string | null;
  location_latitude?: number | null;
  location_longitude?: number | null;
};

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

export default function InfoPage() {
  const [notificationsEnabled, setNotificationsEnabled] = useState(true);
  const [household, setHousehold] = useState<HouseholdResponse | null>(null);
  const [livePriceSettings, setLivePriceSettings] = useState<LivePriceSettings | null>(null);
  const [entsoeApiKey, setEntsoeApiKey] = useState("");
  const [isSavingApiKey, setIsSavingApiKey] = useState(false);
  const [apiKeyError, setApiKeyError] = useState<string | null>(null);
  const selectedCity = useSyncExternalStore(subscribeToCityStorage, getStoredCity, getServerCity);

  useEffect(() => {
    let isMounted = true;

    const fetchLiveState = async () => {
      const [h, priceSettings] = await Promise.all([
        weaverApi.getHousehold("house_1").catch(() => null) as Promise<HouseholdResponse | null>,
        weaverApi.getLivePriceSettings().catch(() => null) as Promise<LivePriceSettings | null>,
      ]);
      if (isMounted) {
        setHousehold(h);
        setLivePriceSettings(priceSettings);
      }
    };

    fetchLiveState();
    const poll = window.setInterval(fetchLiveState, 10000);

    return () => {
      isMounted = false;
      window.clearInterval(poll);
    };
  }, []);

  const hasCitySet = Boolean(household?.location_latitude && household?.location_longitude && household?.bidding_zone);
  const zoneName = household?.bidding_zone ? ZONE_NAMES[household.bidding_zone] || household.bidding_zone : "";
  const cityName = selectedCity || (hasCitySet ? zoneName || "Selected city" : "");
  const energyMode = household?.household_type === "grid_and_pv" ? "Solar + grid" : "Grid only";
  const shouldShowLivePriceSetup = livePriceSettings?.configured === false;

  const handleSaveEntsoeApiKey = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedKey = entsoeApiKey.trim();
    if (!trimmedKey) {
      setApiKeyError("Enter an ENTSO-E API key.");
      return;
    }

    setIsSavingApiKey(true);
    setApiKeyError(null);
    try {
      const settings = await weaverApi.saveEntsoeApiKey(trimmedKey);
      setLivePriceSettings(settings);
      setEntsoeApiKey("");
    } catch (error) {
      setApiKeyError(error instanceof Error ? error.message : "Could not save the API key.");
    } finally {
      setIsSavingApiKey(false);
    }
  };

  return (
    <div className="px-5 pt-10 max-w-lg mx-auto space-y-6 pb-52">
      <motion.header initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}>
        <p className="text-xs font-bold uppercase tracking-[0.24em] text-primary">Info</p>
        <h1 className="text-4xl font-bold mt-1 text-slate-950">What Weaver Does</h1>
        <p className="mt-3 text-sm leading-6 text-slate-600">
          Weaver starts with simple Matter appliance control, then uses local price scheduling and optional solar forecasts to shift flexible loads to better moments.
        </p>
      </motion.header>

      <motion.section
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
        className="organic-card p-5"
      >
        <div className="space-y-3">
          <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <div className="flex items-center gap-3">
              <MapPin className="w-5 h-5 text-primary" />
              <span className="text-sm text-slate-700">City</span>
            </div>
            <span className="text-sm font-bold text-slate-950">{cityName || "Not set"}</span>
          </div>
          <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <div className="flex items-center gap-3">
              <Sun className="w-5 h-5 text-amber-600" />
              <span className="text-sm text-slate-700">Home mode</span>
            </div>
            <span className="text-sm font-bold text-slate-950">{energyMode}</span>
          </div>
        </div>
      </motion.section>

      {shouldShowLivePriceSetup && (
        <motion.section
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.08 }}
          className="organic-card p-5"
        >
          <div className="flex items-start gap-4">
            <div className="w-11 h-11 rounded-lg bg-teal-50 text-teal-700 flex items-center justify-center shrink-0">
              <KeyRound size={20} />
            </div>
            <form onSubmit={handleSaveEntsoeApiKey} className="min-w-0 flex-1">
              <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Live prices</p>
              <h2 className="mt-1 text-base font-bold text-slate-950">ENTSO-E API key</h2>
              <p className="mt-1 text-xs leading-5 text-slate-500">
                Add your ENTSO-E key to use live wholesale prices for scheduling.
              </p>
              <div className="mt-4 flex gap-2">
                <input
                  type="password"
                  value={entsoeApiKey}
                  onChange={(event) => setEntsoeApiKey(event.target.value)}
                  placeholder="Paste API key"
                  className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-800 outline-none focus:border-primary"
                />
                <button
                  type="submit"
                  disabled={isSavingApiKey}
                  className="rounded-lg bg-primary px-4 py-2 text-xs font-bold uppercase tracking-widest text-white disabled:opacity-60"
                >
                  {isSavingApiKey ? "Saving" : "Save"}
                </button>
              </div>
              {apiKeyError && (
                <p className="mt-2 text-xs font-semibold text-red-600">{apiKeyError}</p>
              )}
            </form>
          </div>
        </motion.section>
      )}

      <motion.section
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="organic-card p-5"
      >
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center shrink-0">
            <Sun size={22} />
          </div>
          <div>
            <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Solar + grid</p>
            <h2 className="mt-1 text-xl font-bold text-slate-950">Use your panels first</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              If you turn on the solar toggle, Weaver prioritizes running flexible appliances when your panels are expected to produce, then uses city-based price scheduling as backup.
            </p>
          </div>
        </div>
      </motion.section>

      <motion.section
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
        className="organic-card p-5"
      >
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-lg bg-teal-50 text-teal-700 flex items-center justify-center shrink-0">
            <Network size={22} />
          </div>
          <div>
            <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Matter appliances</p>
            <h2 className="mt-1 text-xl font-bold text-slate-950">Built for local control</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              Weaver keeps appliance control on your home network and uses the city you choose to plan flexible runs around better-priced hours.
            </p>
          </div>
        </div>
      </motion.section>

      <motion.section
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="organic-card p-5"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-11 h-11 rounded-lg bg-blue-50 text-primary flex items-center justify-center">
              <Bell size={20} />
            </div>
            <div>
              <h2 className="text-sm font-bold text-slate-950">Notifications</h2>
              <p className="text-xs text-slate-500">Energy reminders and schedule alerts</p>
            </div>
          </div>
          <button
            type="button"
            aria-pressed={notificationsEnabled}
            onClick={() => setNotificationsEnabled((value) => !value)}
            className={`w-12 h-7 rounded-full p-1 flex transition-colors ${
              notificationsEnabled ? "bg-primary justify-end" : "bg-slate-300 justify-start"
            }`}
          >
            <span className="w-5 h-5 rounded-full bg-white shadow-sm" />
          </button>
        </div>
      </motion.section>
    </div>
  );
}
