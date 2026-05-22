"use client";

import React, { useCallback, useEffect, useId, useState } from "react";
import { Html5QrcodeScanner } from "html5-qrcode";
import { motion, AnimatePresence } from "framer-motion";
import { AlertCircle, Camera, CheckCircle2, Keyboard, LoaderCircle, X } from "lucide-react";

interface ScannerProps {
  onScan: (data: string) => Promise<void> | void;
  onClose: () => void;
}

export function Scanner({ onScan, onClose }: ScannerProps) {
  const [manualCode, setManualCode] = useState("");
  const [status, setStatus] = useState<"idle" | "pairing" | "paired" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const reactId = useId();
  const readerId = `reader-${reactId.replace(/:/g, "")}`;

  const submitCode = useCallback(async (code: string) => {
    const normalizedCode = code.trim();
    const isVirtualTestCode = normalizedCode.toUpperCase() === "WEAVER-TEST-LOAD";
    const isMatterCode = normalizedCode.startsWith("MT:") || /^\d{11,21}$/.test(normalizedCode);

    if (!isMatterCode && !isVirtualTestCode) {
      setStatus("error");
      setError("Enter an 11-21 digit setup code or an MT: QR payload.");
      return;
    }

    setStatus("pairing");
    setError(null);

    try {
      await onScan(normalizedCode);
      setStatus("paired");
    } catch (err) {
      setStatus("error");
      setError(err instanceof Error ? err.message : "Pairing failed. Check the code and pairing mode.");
    }
  }, [onScan]);

  useEffect(() => {
    if (status !== "idle" || !document.getElementById(readerId)) return;

    const scanner = new Html5QrcodeScanner(
      readerId,
      { fps: 10, qrbox: { width: 250, height: 250 } },
      /* verbose= */ false
    );

    scanner.render(
      (decodedText) => {
        scanner.clear();
        submitCode(decodedText);
      },
      () => {
        // ignore errors
      }
    );

    return () => {
      scanner.clear().catch(e => console.error("Failed to clear scanner", e));
    };
  }, [readerId, status, submitCode]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[100] bg-background/95 backdrop-blur-xl p-6 flex flex-col"
    >
      <div className="flex justify-between items-center mb-8">
        <div>
          <p className="text-xs text-blue-500">Pairing</p>
          <h2 className="text-2xl font-bold text-blue-800">Add appliance</h2>
        </div>
        <button onClick={onClose} className="p-3 bg-white border border-slate-200 rounded-lg text-slate-500 shadow-sm">
          <X size={24} />
        </button>
      </div>

      <div className="flex-1 flex flex-col items-center justify-center space-y-8">
        <AnimatePresence mode="wait">
          {status === "idle" || status === "error" ? (
            <motion.div 
              key="scanner"
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 1.1, opacity: 0 }}
              className="w-full max-w-sm aspect-square organic-card scanner-card overflow-hidden relative border border-blue-200 shadow-lg"
            >
              <div id={readerId} className="w-full h-full"></div>
              <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
                <div className="w-64 h-64 border-2 border-primary/60 border-dashed rounded-lg"></div>
              </div>
            </motion.div>
          ) : status === "pairing" ? (
            <motion.div
              key="pairing"
              initial={{ scale: 0.5, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              className="flex flex-col items-center text-center space-y-4"
            >
              <div className="w-24 h-24 bg-primary rounded-lg flex items-center justify-center text-white shadow-lg shadow-primary/30">
                <LoaderCircle size={48} className="animate-spin" />
              </div>
              <h3 className="text-xl font-bold text-blue-800">Pairing with Matter</h3>
              <p className="text-sm text-slate-500">This can take up to a minute. Keep the appliance in pairing mode...</p>
            </motion.div>
          ) : (
            <motion.div
              key="paired"
              initial={{ scale: 0.5, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              className="flex flex-col items-center text-center space-y-4"
            >
              <div className="w-24 h-24 bg-primary rounded-lg flex items-center justify-center text-white shadow-lg shadow-primary/30">
                <CheckCircle2 size={48} />
              </div>
              <h3 className="text-xl font-bold text-blue-800">Appliance connected</h3>
              <p className="text-sm text-slate-500">The device list is refreshing...</p>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="w-full max-w-sm space-y-4">
          <div className="flex items-center gap-4 text-slate-300">
            <div className="h-[1px] flex-1 bg-slate-200"></div>
            <span className="text-xs font-bold text-slate-700">Or enter manually</span>
            <div className="h-[1px] flex-1 bg-slate-200"></div>
          </div>

          <div className="relative">
            <Keyboard className="absolute left-5 top-1/2 -translate-y-1/2 text-blue-600 w-5 h-5" />
            <input 
              type="text" 
              placeholder="Enter setup code..."
              value={manualCode}
              disabled={status === "pairing" || status === "paired"}
              onChange={(e) => {
                setManualCode(e.target.value);
                if (status === "error") {
                  setStatus("idle");
                  setError(null);
                }
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && manualCode.trim().length > 0) {
                  submitCode(manualCode);
                }
              }}
              className="w-full h-14 organic-card !rounded-lg pl-14 pr-5 text-slate-800 placeholder:text-slate-400 focus:outline-none focus:border-primary transition-colors"
            />
          </div>
          {error && (
            <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm font-semibold text-red-700">
              <AlertCircle size={16} className="mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {manualCode.trim().length > 0 && status !== "pairing" && status !== "paired" && (
            <motion.button
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              onClick={() => submitCode(manualCode)}
              className="btn-whimsical w-full"
            >
              Pair Appliance
            </motion.button>
          )}
        </div>
      </div>

      <div className="py-8 text-center text-xs font-bold text-slate-700 flex items-center justify-center gap-2">
        <Camera size={12} /> Point at the Matter QR Label
      </div>
    </motion.div>
  );
}
