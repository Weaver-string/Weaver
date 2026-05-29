import type { Metadata } from "next";
import "./globals.css";
import { Navigation } from "@/components/Navigation";

export const metadata: Metadata = {
  title: "Weaver | Smart Energy Scheduler",
  description: "Optimize your home energy usage with Matter and real-time price tracking.",
  icons: {
    icon: "/icon.svg",
  },
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  themeColor: "#eef8fb",
};

import { Toaster } from "sonner";

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className="h-full antialiased"
    >
      <body className="min-h-full bg-background text-foreground flex flex-col font-sans">
        <Toaster position="top-center" expand={true} richColors />
        <main className="flex-1">
          {children}
        </main>
        <Navigation />
      </body>
    </html>
  );
}
