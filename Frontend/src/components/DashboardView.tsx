import React from 'react';
import { motion } from 'motion/react';
import { 
  Zap, 
  Cpu, 
  Globe, 
  DollarSign, 
  ChevronRight, 
  ShieldAlert 
} from 'lucide-react';
import { 
  AreaChart, 
  Area, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer 
} from 'recharts';
import { StatItem } from './StatItem';
import { cn } from '../lib/utils';

interface DashboardViewProps {
  data: any;
  metrics: any;
  zones: any[];
  onZoneSelect: (z: any) => void;
  isSecurityLocked: boolean;
  setIsSecurityLocked: (v: boolean) => void;
  onGoToSafety: () => void;
}

export const DashboardView = ({ 
  data, 
  metrics, 
  zones, 
  onZoneSelect,
  isSecurityLocked,
  setIsSecurityLocked,
  onGoToSafety
}: DashboardViewProps) => (
  <motion.div 
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    className="space-y-10 pb-20"
  >
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-6">
      <StatItem label="Current Load" value={`${metrics.totalLoad} kW`} icon={Zap} trend={-metrics.activeCount} />
      <StatItem label="Est. Daily Cost" value={`₹${metrics.dailySpend}`} icon={DollarSign} trend={+12} sub="Mesh optimized" />
      <StatItem label="System Efficiency" value={`${metrics.efficiency}%`} icon={Cpu} sub="Active node health" />
      <StatItem label="Active Nodes" value={metrics.activeCount} icon={Globe} sub="12ms Mesh Latency" />
    </div>

    <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
      <div className="lg:col-span-2 space-y-8">
        <div className="bg-white rounded-[4rem] p-10 border border-olive/10 shadow-sm transition-all hover:border-olive/20">
          <div className="flex justify-between items-center mb-10">
            <div>
              <h3 className="text-sm font-bold text-ink uppercase tracking-[0.2em]">Global Mesh Consumption</h3>
              <p className="text-[10px] text-ink/30 font-black uppercase mt-1 tracking-widest">Real-time aggregate load tracing</p>
            </div>
            <div className="flex items-center gap-2 px-4 py-2 bg-sage/10 text-sage text-[9px] font-black rounded-xl uppercase tracking-widest border border-sage/5">
              <div className="w-1.5 h-1.5 rounded-full bg-sage animate-pulse" />
              Live Feed
            </div>
          </div>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data}>
                <defs>
                  <linearGradient id="dashboardGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#2D4C3B" stopOpacity={0.15}/>
                    <stop offset="95%" stopColor="#2D4C3B" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#2D4C3B10" />
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fontSize: 9, fontWeight: 900, fill: 'rgba(45,76,59,0.3)' }} />
                <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 9, fontWeight: 900, fill: 'rgba(45,76,59,0.3)' }} />
                <Tooltip 
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      return (
                        <div className="bg-white p-4 rounded-3xl shadow-2xl border border-olive/10 flex flex-col gap-1 ring-8 ring-olive/5">
                          <p className="text-[10px] font-black text-ink/30 uppercase tracking-widest mb-1">{payload[0].payload.name}</p>
                          <div className="flex items-center gap-2">
                            <div className="w-1.5 h-1.5 rounded-full bg-olive" />
                            <p className="text-xs font-bold text-ink">{Number(payload[0].value)?.toFixed(0)} <span className="opacity-40 italic">Watts</span></p>
                          </div>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                <Area type="monotone" dataKey="value" stroke="#2D4C3B" fillOpacity={1} fill="url(#dashboardGrad)" strokeWidth={4} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          {zones.slice(0, 2).map((zone) => (
            <div 
              key={zone.id} 
              onClick={() => onZoneSelect(zone)}
              className="bg-bg-card/40 rounded-[3.5rem] p-8 border border-olive/10 group cursor-pointer hover:bg-white transition-all hover:shadow-xl relative overflow-hidden"
            >
              <div className="flex justify-between items-start mb-6">
                <div className={cn("p-4 rounded-2xl bg-white shadow-sm transition-transform group-hover:scale-110", zone.color)}>
                  <zone.icon size={22} />
                </div>
                <div className="text-right">
                  <div className="text-[10px] font-black uppercase text-ink/20 tracking-widest">Efficiency</div>
                  <div className="text-lg font-display font-medium text-olive">98.4%</div>
                </div>
              </div>
              <h4 className="text-xl font-display font-medium text-ink mb-1">{zone.name}</h4>
              <p className="text-[10px] text-ink/30 font-black uppercase tracking-[0.2em]">{zone.type}</p>
              <div className="mt-6 flex items-center justify-between">
                <div className="flex -space-x-2">
                  {[1, 2, 3].map(i => (
                    <div key={i} className="w-6 h-6 rounded-full border-2 border-white bg-bg-card flex items-center justify-center text-[8px] font-black text-ink/20">
                      {i}
                    </div>
                  ))}
                </div>
                <button className="p-2 rounded-full bg-white text-ink/20 group-hover:text-olive group-hover:bg-olive/10 transition-all">
                  <ChevronRight size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="space-y-8">
        <div className="p-10 rounded-[4rem] bg-olive text-white shadow-2xl shadow-olive/20 relative overflow-hidden h-full flex flex-col min-h-[500px]">
          <div className="absolute top-0 right-0 w-32 h-32 bg-white/5 blur-3xl rounded-full translate-x-1/2 -translate-y-1/2" />
          <ShieldAlert size={140} className="absolute -bottom-10 -right-10 opacity-5" />
          
          <h4 className="text-[10px] font-black uppercase tracking-[0.3em] mb-12 opacity-60">System Security</h4>
          <div className="text-4xl font-display font-medium mb-4 italic leading-[1.1]">Mesh <br /> {isSecurityLocked ? 'Protected' : 'Unlocked'}.</div>
          <p className="text-[11px] opacity-60 mb-10 font-medium italic leading-relaxed">Active perimeter perimeter tracing engaged. All sensor nodes reporting nominal operations with zero signal drop.</p>
          
          <div className="mt-auto space-y-4">
             <div 
               onClick={() => setIsSecurityLocked(!isSecurityLocked)}
               className="p-5 bg-white/10 rounded-[2rem] border border-white/10 backdrop-blur-sm flex items-center justify-between cursor-pointer group"
             >
               <div className="flex items-center gap-4">
                 <div className="p-2 bg-sage/20 rounded-xl transition-colors group-hover:bg-sage/40">
                   <Globe size={14} />
                 </div>
                 <span className="text-[10px] font-bold uppercase tracking-widest">Global Lock</span>
               </div>
               <div className={cn(
                 "w-10 h-6 rounded-full relative p-1 transition-colors duration-300",
                 isSecurityLocked ? "bg-sage" : "bg-white/20"
               )}>
                 <motion.div 
                   animate={{ x: isSecurityLocked ? 16 : 0 }}
                   className="w-4 h-4 bg-white rounded-full shadow-sm" 
                 />
               </div>
             </div>
             <button 
               onClick={onGoToSafety}
               className="w-full py-5 bg-white text-olive rounded-[2rem] text-[10px] font-black uppercase tracking-widest hover:bg-sage hover:text-white transition-all shadow-xl shadow-black/5"
             >
               Configure sentinel
             </button>
          </div>
        </div>
      </div>
    </div>
  </motion.div>
);
