import React from 'react';
import { motion } from 'motion/react';
import { ShieldAlert, Info, Activity, Power } from 'lucide-react';
import { ActiveTimeDisplay } from './ActiveTimeDisplay';
import { cn } from '../lib/utils';

interface ManualControlViewProps {
  zones: any[];
  toggleZone: (id: string, e?: React.MouseEvent) => void;
  setZones: React.Dispatch<React.SetStateAction<any[]>>;
  addToast: (message: string, icon: any) => void;
}

export const ManualControlView = ({ zones, toggleZone, setZones, addToast }: ManualControlViewProps) => (
  <motion.div 
    key="controls"
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    className="max-w-4xl space-y-12 pb-20"
  >
    <div className="flex justify-between items-end">
      <div>
        <h2 className="text-3xl font-display font-medium text-ink mb-2 italic">Manual Override Hub</h2>
        <p className="text-[10px] text-ink/30 font-black uppercase tracking-widest leading-relaxed">Direct node interruption. Bypasses predictive schedules.</p>
      </div>
      <div className="flex gap-4">
        <button 
          onClick={() => {
            setZones((z: any[]) => z.map(x => ({ 
              ...x, 
              active: false, 
              status: x.type === 'HVAC' ? 'Standby' : 'Idle',
              startTime: null
            })));
            addToast("Global safety isolation enforced", ShieldAlert);
          }} 
          className="px-6 py-2 rounded-xl bg-ink/5 text-ink/40 text-[10px] font-black uppercase tracking-widest hover:bg-danger/10 hover:text-danger transition-all"
        >
          Kill All Nodes
        </button>
      </div>
    </div>

    <div className="bg-white rounded-[4rem] border border-olive/10 divide-y divide-olive/5 overflow-hidden shadow-sm">
      {zones.map((zone: any) => (
        <div key={zone.id} className="p-8 flex items-center justify-between hover:bg-bg-card/30 transition-colors">
          <div className="flex items-center gap-6">
            <div className={cn("p-4 rounded-2xl bg-bg-card font-bold", zone.active ? zone.color : "text-ink/10")}>
              <zone.icon size={24} />
            </div>
            <div>
              <h4 className="font-bold text-ink leading-none mb-2">{zone.name}</h4>
              <p className="text-[10px] text-ink/30 font-black uppercase tracking-widest">{zone.type} • {zone.active ? 'Consuming ' + zone.nominalConsumption + 'W' : 'Dormant'}</p>
            </div>
          </div>
          <div className="flex items-center gap-8">
            {zone.active && zone.startTime && (
              <div className="text-right hidden md:block">
                <div className="text-[8px] font-black text-olive/30 uppercase tracking-widest">Active Time</div>
                <ActiveTimeDisplay startTime={zone.startTime} />
              </div>
            )}
            <button 
              onClick={(e) => toggleZone(zone.id, e)}
              className={cn(
                "px-8 py-3 rounded-2xl font-black text-[10px] uppercase tracking-widest transition-all border group relative overflow-hidden",
                zone.active 
                  ? "bg-olive text-white border-olive shadow-lg shadow-olive/10" 
                  : "bg-white text-ink/30 border-olive/10 hover:border-olive/30"
              )}
            >
              <motion.span 
                key={zone.active ? 'active' : 'inactive'}
                initial={{ y: 20, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                className="relative z-10 flex items-center gap-2"
              >
                {zone.active ? <Activity size={12} className="animate-pulse" /> : <Power size={12} />}
                {zone.active ? 'Active' : 'Offline'}
              </motion.span>
              {zone.active && (
                <motion.div 
                  initial={{ x: '-100%' }}
                  animate={{ x: '100%' }}
                  transition={{ repeat: Infinity, duration: 1.5, ease: "linear" }}
                  className="absolute inset-0 bg-white/10 skew-x-12"
                />
              )}
            </button>
          </div>
        </div>
      ))}
    </div>

    <div className="p-10 rounded-[3rem] bg-sage/5 border border-sage/10 flex items-center gap-8">
      <div className="w-16 h-16 rounded-full bg-sage flex items-center justify-center shrink-0">
        <Info size={32} className="text-white" />
      </div>
      <div>
        <h5 className="font-bold text-ink mb-1">Governance Mode</h5>
        <p className="text-sm text-ink/50 leading-relaxed italic">Manual overrides expire after 4 hours of inactivity to restore global energy harmony. Ensure critical nodes are locked in the logic settings.</p>
      </div>
    </div>
  </motion.div>
);
