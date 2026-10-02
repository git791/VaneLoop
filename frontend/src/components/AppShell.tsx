"use client"
import { useTheme } from "next-themes"
import { Moon, Sun, Settings, Search, Activity } from "lucide-react"
import Link from "next/link"
import { useEffect, useState } from "react"
import { useFleetStream } from "@/lib/useFleetStream"
import { ConnectionBadge } from "@/components/ConnectionBadge"

export function AppShell({ children }: { children: React.ReactNode }) {
  const { setTheme, theme } = useTheme()
  const [mounted, setMounted] = useState(false)
  // One shared stream for the whole app shell — dataset can be made dynamic later
  const { connection } = useFleetStream("FD001")

  useEffect(() => {
    setMounted(true)
  }, [])

  return (
    <div className="flex flex-col h-screen bg-bg-canvas text-foreground">
      {/* Topbar */}
      <header className="h-14 flex items-center justify-between px-4 border-b border-border-hairline bg-bg-surface">
        <div className="flex items-center gap-2 font-semibold">
          <Activity className="h-5 w-5 text-primary" />
          <span>Aircraft Engine Health</span>
        </div>
        <div className="flex items-center gap-4">
          {/* Connection badge — replaces the old static "LIVE" badge (G5 fix) */}
          <ConnectionBadge connection={connection} />
          <button className="text-muted-foreground hover:text-foreground">
            <Search className="h-4 w-4" />
          </button>
          <button
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            className="text-muted-foreground hover:text-foreground flex items-center justify-center w-4 h-4"
          >
            {mounted ? (theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />) : null}
          </button>
          <button className="text-muted-foreground hover:text-foreground">
            <Settings className="h-4 w-4" />
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <aside className="w-48 flex-shrink-0 border-r border-border-hairline bg-bg-surface py-4">
          <nav className="flex flex-col gap-1 px-2 text-sm text-muted-foreground">
            <Link href="/" className="px-3 py-2 rounded-md hover:bg-bg-surface-raised hover:text-foreground font-medium">
              Fleet
            </Link>
            <Link href="/alerts" className="px-3 py-2 rounded-md hover:bg-bg-surface-raised hover:text-foreground">
              Alerts
            </Link>
            <Link href="/benchmark" className="px-3 py-2 rounded-md hover:bg-bg-surface-raised hover:text-foreground">
              Benchmark
            </Link>
          </nav>
        </aside>

        {/* Main Content */}
        <main className="flex-1 overflow-auto p-4 md:p-6 lg:p-8">
          {children}
        </main>
      </div>

      {/* Footer disclaimer — visible on every page (M-3 requirement) */}
      <footer className="h-8 flex items-center px-4 border-t border-border-hairline bg-bg-surface text-[11px] text-muted-foreground">
        ⚠️ Simulated NASA C-MAPSS data only — not for real airworthiness or maintenance decisions.
      </footer>
    </div>
  )
}
