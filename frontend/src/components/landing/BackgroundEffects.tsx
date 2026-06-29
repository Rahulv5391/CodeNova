"use client";

export default function BackgroundEffects() {
  return (
    <>
      <div className="absolute left-0 top-0 h-[500px] w-[500px] rounded-full bg-cyan-500/20 blur-[120px]" />

      <div className="absolute right-0 top-20 h-[400px] w-[400px] rounded-full bg-blue-500/20 blur-[120px]" />

      <div className="absolute bottom-0 left-1/2 h-[500px] w-[500px] -translate-x-1/2 rounded-full bg-violet-500/10 blur-[150px]" />
    </>
  );
}