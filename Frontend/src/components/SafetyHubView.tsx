import React from 'react';
import { motion } from 'motion/react';
import { Flame, Wind } from 'lucide-react';
import { cn } from '../lib/utils';

interface SafetyHubViewProps {
  gasLevel: number;
  isFlame: boolean;
}

export const SafetyHubView = ({ gasLevel, isFlame }: SafetyHubViewProps) => (
  <motion.div 
    initial={{ opacity: 0 }}
    animate={{ opacity: 1 }}
    className="grid grid-cols-1 lg:grid-cols-2 gap-10 pb-20"
  >
    <div className={cn("p-12 rounded-[4rem] border-2 transition-all duration-700", isFlame ? "border-danger bg-danger/5 shadow-2xl shadow-danger/20" : "bg-white border-olive/5 shadow-sm")}>
      <div className="flex justify-between items-start mb-12">
        <div className="flex items-center gap-6">
          <div className={cn("p-8 rounded-[2.5rem] soft-shadow transition-transform", isFlame ? "bg-danger text-white scale-110" : "bg-bg-card text-ink/30")}>
            <Flame size={48} />
          </div>
          <div>
            <h4 className="text-2xl font-display font-medium text-ink leading-tight mb-2 italic">Infrared <br /> Thermal Array</h4>
            <p className="text-xs font-bold text-ink/30 uppercase tracking-widest">MQ-2 + IR Shielding Active</p>
          </div>
        </div>
      </div>
      <div className="space-y-4">
          <div className="p-6 bg-bg-card/20 rounded-3xl border border-olive/5 flex items-center justify-between">
            <span className="text-sm font-bold text-ink/60">Molecular Shutter Status</span>
            <span className={cn("text-[10px] font-black uppercase px-2 py-1 rounded", isFlame ? "bg-danger text-white px-3" : "bg-sage/10 text-sage")}>
              {isFlame ? 'LOCKED' : 'OPEN'}
            </span>
          </div>
      </div>
    </div>

    <div className="p-12 rounded-[4rem] bg-white border border-olive/5 shadow-sm space-y-12">
      <div>
        <div className="flex items-center gap-6 mb-10">
          <div className={cn("p-8 rounded-[2.5rem] shadow-sm", gasLevel > 300 ? "bg-clay text-white" : "bg-bg-card text-ink/20")}>
            <Wind size={48} />
          </div>
          <div>
            <h4 className="text-2xl font-display font-medium text-ink italic leading-tight mb-2">Molecular <br /> Concentration</h4>
            <p className="text-xs font-bold text-ink/30 uppercase tracking-widest">{gasLevel.toFixed(1)} PPM</p>
          </div>
        </div>
        <div className="h-4 w-full bg-bg-card rounded-full overflow-hidden relative mb-6">
          <motion.div animate={{ width: `${(gasLevel / 450) * 100}%` }} className={cn("h-full relative z-10 transition-colors", gasLevel > 300 ? "bg-clay" : "bg-sage")} />
        </div>
        <p className="text-xs text-ink/40 leading-relaxed font-medium">Monitoring methane, LPG, and smoke particles across Zone 1-12 metadata clusters.</p>
      </div>
    </div>
  </motion.div>
);
