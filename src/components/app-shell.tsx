"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Activity, BarChart3, BookOpenCheck, DatabaseZap, FileText, Gauge, Languages, Settings, ShieldCheck, Sparkles, UsersRound } from "lucide-react";
import { createPlayer, fetchPlayers, getActivePlayerId, PlayerWorkspace, setActivePlayerId } from "@/lib/api";
import { Language, LanguageProvider, useLanguage } from "@/lib/i18n";

const navItems = [
  { href: "/welcome", key: "welcome", icon: Sparkles },
  { href: "/", key: "dashboard", icon: BarChart3 },
  { href: "/strategies", key: "strategies", icon: Activity },
  { href: "/data", key: "data", icon: DatabaseZap },
  { href: "/risk", key: "risk", icon: Gauge },
  { href: "/journal", key: "journal", icon: BookOpenCheck },
  { href: "/report", key: "report", icon: FileText },
  { href: "/setup", key: "setup", icon: Settings },
] as const;

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <LanguageProvider>
      <ShellContent>{children}</ShellContent>
    </LanguageProvider>
  );
}

function ShellContent({ children }: { children: React.ReactNode }) {
  const { language, setLanguage, t } = useLanguage();
  const pathname = usePathname();
  const [players, setPlayers] = useState<PlayerWorkspace[]>([]);
  const [activePlayer, setActivePlayer] = useState(getActivePlayerId());

  async function loadPlayers() {
    const payload = await fetchPlayers();
    setPlayers(payload.players);
    setActivePlayer(payload.active_player_id);
    setActivePlayerId(payload.active_player_id);
  }

  async function addPlayer() {
    const name = window.prompt(language === "zh" ? "新玩家名字：" : "New player name:");
    if (!name?.trim()) return;
    const cash = Number(window.prompt(language === "zh" ? "模拟初始资金：" : "Initial paper cash:", "500") || 500);
    const player = await createPlayer(name.trim(), Number.isFinite(cash) && cash > 0 ? cash : 500);
    setActivePlayerId(player.player_id);
    window.location.reload();
  }

  useEffect(() => {
    loadPlayers().catch(() => undefined);
  }, []);

  return (
    <div className="shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <Link href="/" className="brand" aria-label="High-Risk Paper Trader home">
          <ShieldCheck size={22} />
          <span>{language === "zh" ? "模拟交易台" : "Paper Trader"}</span>
        </Link>
        <nav className="nav-list">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <Link href={item.href} className={pathname === item.href ? "nav-item active" : "nav-item"} key={item.href}>
                <Icon size={18} aria-hidden="true" />
                <span>{t.nav[item.key]}</span>
              </Link>
            );
          })}
        </nav>
        <div className="phase-lock">
          <span className="phase-dot" />
          <span>{t.nav.phase}</span>
        </div>
      </aside>
      <main className="main">
        <div className="topbar">
          <div className="topbar-status">
            <span className="phase-dot" />
            <span>{language === "zh" ? "模拟账本 · 真人真钱下单已关闭" : "Paper ledger · live orders disabled"}</span>
          </div>
          <div className="topbar-controls">
            <PlayerSwitcher
              language={language}
              players={players}
              activePlayer={activePlayer}
              onChange={(playerId) => {
                setActivePlayerId(playerId);
                window.location.reload();
              }}
              onAdd={() => void addPlayer()}
            />
            <LanguageToggle language={language} setLanguage={setLanguage} />
          </div>
        </div>
        {children}
      </main>
    </div>
  );
}

function PlayerSwitcher({ language, players, activePlayer, onChange, onAdd }: { language: Language; players: PlayerWorkspace[]; activePlayer: string; onChange: (playerId: string) => void; onAdd: () => void }) {
  return (
    <div className="player-switcher" aria-label={language === "zh" ? "玩家工作区" : "Player workspace"}>
      <UsersRound size={16} aria-hidden="true" />
      <select value={activePlayer} onChange={(event) => onChange(event.target.value)}>
        {players.map((player) => (
          <option value={player.player_id} key={player.player_id}>
            {player.display_name} · {player.onboarding_completed ? (language === "zh" ? "已设置" : "ready") : (language === "zh" ? "待设置" : "setup")}
          </option>
        ))}
      </select>
      <button type="button" onClick={onAdd}>{language === "zh" ? "新玩家" : "New"}</button>
    </div>
  );
}

function LanguageToggle({ language, setLanguage }: { language: Language; setLanguage: (language: Language) => void }) {
  return (
    <div className="language-toggle" aria-label="Language switcher">
      <Languages size={16} aria-hidden="true" />
      <button className={language === "zh" ? "active" : ""} onClick={() => setLanguage("zh")} type="button">
        中
      </button>
      <button className={language === "en" ? "active" : ""} onClick={() => setLanguage("en")} type="button">
        EN
      </button>
    </div>
  );
}
