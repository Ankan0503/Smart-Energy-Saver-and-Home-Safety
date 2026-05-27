import React from 'react';
import { motion } from 'motion/react';
import { 
  Cpu, 
  Zap, 
  ShieldAlert, 
  LayoutDashboard, 
  TrendingUp, 
  Power, 
  Bell, 
  Settings, 
  ChevronRight, 
  Wind, 
  Layers, 
  Activity 
} from 'lucide-react';
import { cn } from '../lib/utils';

interface SidebarProps {
  activeView: string;
  setActiveView: (v: string) => void;
  zonesCount: number;
  alertActive: boolean;
  setZones: React.Dispatch<React.SetStateAction<any[]>>;
  addToast: (message: string, icon: any) => void;
  metrics: any;
  isEcoMode: boolean;
  setIsEcoMode: (v: boolean) => void;
  isSyncing: boolean;
  setIsSyncing: (v: boolean) => void;
}

export const Sidebar = ({ 
  activeView, 
  setActiveView, 
  zonesCount, 
  alertActive, 
  setZones, 
  addToast,
  metrics,
  isEcoMode,
  setIsEcoMode,
  isSyncing,
  setIsSyncing
}: SidebarProps) => {
  const menuItems = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'zones', label: 'Energy Zones', icon: Zap, badge: zonesCount },
    { id: 'analytics', label: 'Analytics', icon: TrendingUp },
    { id: 'controls', label: 'Manual Control', icon: Power },
    { id: 'safety', label: 'Safety Hub', icon: ShieldAlert, alert: alertActive },
    { id: 'automation', label: 'Automation', icon: Cpu },
    { id: 'events', label: 'System Events', icon: Bell },
    { id: 'settings', label: 'Configuration', icon: Settings },
  ];

  return (
    <aside className="w-80 h-screen bg-white border-r border-olive/10 flex flex-col sticky top-0 z-40 overflow-hidden">
      <div className="p-8 pb-4">
        <div className="flex items-center gap-3 mb-8">
          <div className="w-10 h-10 rounded-2xl bg-olive flex items-center justify-center shadow-lg shadow-olive/10">
            <Cpu size={22} className="text-white" />
          </div>
          <div>
            <span className="block font-display font-bold text-xl text-ink leading-none">AETHER.</span>
            <span className="text-[8px] font-black uppercase text-olive tracking-[0.3em]">Mesh OS v2.4</span>
          </div>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto px-6 py-2 space-y-1.5 custom-scrollbar">
        <div className="px-3 mb-4">
          <span className="text-[9px] font-black uppercase text-ink/20 tracking-[0.2em]">Management</span>
        </div>
        {menuItems.map((item) => (
          <button
            key={item.id}
            onClick={() => setActiveView(item.id)}
            className={cn(
              "w-full flex items-center justify-between px-4 py-3.5 rounded-[1.5rem] transition-all group relative",
              activeView === item.id 
                ? "bg-bg-card shadow-sm border border-olive/5 text-ink" 
                : "text-ink/40 hover:bg-bg-card/40 hover:text-ink border border-transparent"
            )}
          >
            <div className="flex items-center gap-4">
              <div className={cn(
                "p-2 rounded-xl transition-colors",
                activeView === item.id ? "bg-white text-olive shadow-sm" : "group-hover:bg-white group-hover:text-olive"
              )}>
                <item.icon size={18} />
              </div>
              <span className="text-[11px] font-black uppercase tracking-widest">{item.label}</span>
            </div>
            <div className="flex items-center gap-2">
              {item.badge && (
                <span className="px-1.5 py-0.5 rounded-lg bg-olive/10 text-olive text-[8px] font-black">{item.badge}</span>
              )}
              {item.alert && (
                <div className="w-2 h-2 rounded-full bg-danger animate-pulse shadow-sm shadow-danger/20" />
              )}
              <ChevronRight size={14} className={cn("transition-transform", activeView === item.id ? "opacity-100" : "opacity-0 group-hover:opacity-40")} />
            </div>
            {activeView === item.id && (
              <motion.div layoutId="nav-glow" className="absolute inset-0 bg-olive/[0.02] rounded-[1.5rem] pointer-events-none" />
            )}
          </button>
        ))}
      </nav>

      <div className="p-8 border-t border-olive/5 space-y-4">
        <div className="space-y-3">
          <button 
            onClick={() => {
              const anyActive = metrics.activeCount > 0;
              setZones(prev => prev.map(z => {
                const nextActive = !anyActive;
                return { 
                  ...z, 
                  active: nextActive, 
                  status: nextActive ? 'Active' : (z.type === 'HVAC' ? 'Standby' : 'Idle'),
                  startTime: nextActive ? Date.now() : null
                };
              }));
              addToast(
                anyActive ? "Global isolation initiated" : "Full system mesh restoration", 
                anyActive ? Power : Zap
              );
            }}
            className={cn(
              "w-full py-4 rounded-[2rem] text-[10px] font-black uppercase tracking-widest transition-all flex items-center justify-center gap-3 shadow-xl group relative overflow-hidden",
              metrics.activeCount > 0 ? "bg-ink text-white shadow-ink/20 hover:bg-danger" : "bg-olive text-white shadow-olive/20 hover:bg-sage"
            )}
          >
            <div className="absolute inset-0 bg-white/10 translate-y-full group-hover:translate-y-0 transition-transform duration-300" />
            <Power size={14} className="relative z-10" />
            <span className="relative z-10">{metrics.activeCount > 0 ? 'Master Override' : 'System Restore'}</span>
          </button>
          
          <div className="p-1.5 bg-bg-card rounded-full flex gap-1 border border-olive/5">
            <button 
              onClick={() => {
                setIsEcoMode(!isEcoMode);
                addToast(isEcoMode ? "Eco Mode Deactivated" : "Eco-Optimization Engaged", TrendingUp);
              }}
              className={cn(
                "flex-1 py-3 rounded-full text-[9px] font-black uppercase tracking-widest transition-all gap-2 flex items-center justify-center",
                isEcoMode ? "bg-olive text-white shadow-lg shadow-olive/10" : "text-ink/30 hover:text-ink"
              )}
            >
              <Wind size={12} />
              Eco
            </button>
            <button 
              disabled={isSyncing}
              onClick={() => {
                setIsSyncing(true);
                addToast("Synchronizing system topology...", Layers);
                setTimeout(() => setIsSyncing(false), 2000);
              }}
              className={cn(
                "flex-1 py-3 rounded-full text-[9px] font-black uppercase tracking-widest transition-all gap-2 flex items-center justify-center relative overflow-hidden",
                isSyncing ? "bg-bg-card text-olive cursor-wait" : "text-ink/30 hover:text-ink"
              )}
            >
              {isSyncing && (
                <motion.div 
                  initial={{ x: '-100%' }}
                  animate={{ x: '100%' }}
                  transition={{ repeat: Infinity, duration: 1, ease: "linear" }}
                  className="absolute inset-0 bg-olive/10"
                />
              )}
              <Layers size={12} className={cn(isSyncing && "animate-spin")} />
              {isSyncing ? 'Syncing...' : 'Sync Mesh'}
            </button>
          </div>
        </div>

        <div className="p-6 rounded-[2.5rem] bg-white border border-olive/10 relative overflow-hidden soft-shadow group">
          <div className="relative z-10 flex items-center justify-between">
            <div>
              <div className="text-[9px] font-black uppercase text-ink/20 tracking-widest mb-1 group-hover:text-olive transition-colors">Grid Capacity</div>
              <div className="text-xl font-display font-medium text-olive">{metrics.totalLoad} <span className="text-[10px] opacity-30">kW</span></div>
            </div>
            <div className="relative">
               <div className="w-10 h-10 rounded-full border border-sage/20 flex items-center justify-center">
                 <Activity size={14} className="text-sage/60 animate-pulse" />
               </div>
               <svg className="absolute inset-0 w-10 h-10 -rotate-90">
                 <circle cx="20" cy="20" r="18" fill="none" stroke="currentColor" strokeWidth="2" className="text-sage/5" />
                 <motion.circle 
                    cx="20" cy="20" r="18" fill="none" stroke="#2D4C3B" strokeWidth="2" 
                    strokeLinecap="round" strokeDasharray="113" 
                    initial={{ strokeDashoffset: 113 }}
                    animate={{ strokeDashoffset: 113 - (parseFloat(metrics.totalLoad) / 2) * 113 }}
                 />
               </svg>
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
};
