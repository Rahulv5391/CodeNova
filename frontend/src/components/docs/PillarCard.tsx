import { Pillar } from "@/types/doc";
import { Check } from "lucide-react";

export function PillarCard({
  pillar,
  selected,
  onToggle,
}: {
  pillar: Pillar;
  selected: boolean;
  onToggle: () => void;
}) {
  const Icon = pillar.icon;

  return (
    <button
      type="button"
      aria-pressed={selected}
      className={`group relative min-h-36 rounded-md border p-5 text-left transition ${
        selected
          ? "border-[#b8b2ff] bg-[#111119] shadow-[0_0_0_1px_rgba(184,178,255,0.16)]"
          : "border-[#32313f] bg-[#08080b] hover:border-[#55536a] hover:bg-[#111115]"
      }`}
      onClick={onToggle}
    >
      <span
        className={`absolute right-4 top-4 grid h-6 w-6 place-items-center rounded-md border transition ${
          selected
            ? "border-[#b8b2ff] bg-[#bbb7ff] text-[#0b08a8]"
            : "border-[#55536a] bg-[#171720] text-transparent group-hover:border-[#aaa7b8]"
        }`}
      >
        <Check className="h-4 w-4" />
      </span>
      <Icon className="h-6 w-6 text-[#55dfff]" />
      <h3 className="mt-5 font-display text-lg font-bold text-white">
        {pillar.title}
      </h3>
      <p className="mt-3 max-w-sm text-sm leading-6 text-[#d8d4e6]">
        {pillar.description}
      </p>
    </button>
  );
}
