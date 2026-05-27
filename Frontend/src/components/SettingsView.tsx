import React from 'react';
import { motion } from 'motion/react';
import { Settings } from 'lucide-react';

export const SettingsView = () => (
  <motion.div 
    initial={{ opacity: 0 }}
    animate={{ opacity: 1 }}
    className="max-w-2xl bg-white rounded-[4rem] p-12 border border-olive/10 shadow-sm mx-auto pb-20"
  >
    <div className="flex items-center gap-6 mb-10">
      <div className="p-6 bg-olive text-white rounded-3xl soft-shadow">
        <Settings size={32} />
      </div>
      <h3 className="text-2xl font-display font-medium text-olive italic">System Preference Matrix</h3>
    </div>
    
    <div className="space-y-8">
      <div className="flex items-center justify-between p-6 bg-bg-card/20 rounded-3xl">
        <div>
          <h5 className="font-bold text-ink mb-1">Dark Mode Override</h5>
          <p className="text-[10px] text-ink/40 font-black uppercase tracking-widest">Automatic based on solar cycle</p>
        </div>
        <div className="w-12 h-6 bg-sage rounded-full flex items-center px-1">
          <div className="w-4 h-4 bg-white rounded-full translate-x-6 shadow-sm" />
        </div>
      </div>
      <div className="flex items-center justify-between p-6 bg-bg-card/20 rounded-3xl opacity-50">
          <div>
          <h5 className="font-bold text-ink mb-1">Predictive Loading</h5>
          <p className="text-[10px] text-ink/40 font-black uppercase tracking-widest">Beta testing active</p>
        </div>
        <div className="w-12 h-6 bg-ink/10 rounded-full flex items-center px-1">
          <div className="w-4 h-4 bg-ink/20 rounded-full" />
        </div>
      </div>
    </div>

    <div className="mt-12 p-8 bg-olive/5 rounded-[2.5rem] border border-olive/5 text-center">
       <div className="text-[9px] font-black text-olive/40 uppercase tracking-widest mb-2">Mesh Identity</div>
       <div className="text-[10px] font-bold text-ink/40 italic">AETHER-OS-v2.4.1-MESH-TOPOLOGY</div>
    </div>
  </motion.div>
);
