import type { Metadata } from "next";
import { Public_Sans } from "next/font/google";
import "./globals.css";
import { SWRProvider } from "@/components/SWRProvider";

// One typeface, doing both jobs (headline and body) at different weights —
// deliberately not the serif-display + mono-label pairing this project used
// in its first pass. Public Sans is also a real choice for the subject: it's
// the U.S. federal government's own typeface for public-facing services,
// which fits a statistical-agency dashboard better than a generic UI font.
const publicSans = Public_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-public-sans",
  display: "swap",
});

export const metadata: Metadata = {
  title: "India Real-Time Airfare Price Index",
  description: "MoSPI SIH26056: real-time airfare price index feeding the CPI Transport and Communication sub-index.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={publicSans.variable}>
      <body className="bg-paper dark:bg-paper-dark text-ink dark:text-ink-dark font-sans antialiased">
        <SWRProvider>{children}</SWRProvider>
      </body>
    </html>
  );
}
