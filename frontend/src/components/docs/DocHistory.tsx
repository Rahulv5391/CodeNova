import { DocHistoryItem } from "@/types/doc";
import { handleDownload } from "@/utils/docs";
import { getDateTime } from "@/utils/repo";
import {
  Download,
  Eye,
  Filter,
  History,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";

export function DocHistory({
  history,
  topictitleMap,
  onViewDocument,
}: {
  history: DocHistoryItem[];
  topictitleMap: Record<string, string>;
  onViewDocument: (docId: string) => void;
}) {
  return (
    <section className="mt-10 overflow-hidden rounded-md border border-[#444254] bg-[#08080b]">
      <div className="flex items-center justify-between px-6 py-5">
        <h2 className="flex items-center gap-3 font-display text-lg font-bold text-white">
          <History className="h-5 w-5 text-[#c5c1ff]" />
          Generation History
        </h2>
        <div className="flex items-center gap-4 text-[#d8d4e6]">
          <Filter className="h-5 w-5" />
          <RefreshCw className="h-5 w-5" />
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] border-collapse text-left">
          <thead className="border-y border-[#444254] bg-[#1b1a20] text-xs uppercase tracking-[0.16em] text-[#d8d4e6]">
            <tr>
              <th className="px-6 py-4 font-medium">Topics Included</th>
              <th className="px-6 py-4 font-medium">Timestamp</th>
              <th className="px-6 py-4 font-medium">Format</th>
              <th className="px-6 py-4 font-medium">Status</th>
              <th className="px-6 py-4 text-right font-medium">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#32313f]">
            {history.map((item) => (
              <tr key={item.id} className="text-sm text-[#d8d4e6]">
                <td className="px-6 py-4">
                  <div className="flex flex-wrap gap-2">
                    {item.topics.map((topic, idx) => (
                      <span
                        key={`${item.id}-${topic}-${idx}`}
                        className="rounded bg-[#2a2932] px-2.5 py-1 text-xs text-white"
                      >
                        {topictitleMap[topic]}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="px-6 py-4t">{getDateTime(item.created_at)}</td>
                <td
                  className={`px-6 py-4 font-mono ${item.format === "json" ? "text-[#ffbd8a]" : "text-[#55dfff]"}`}
                >
                  {item.format.toUpperCase()}
                </td>
                <td className="px-6 py-4">
                  <span
                    className={`inline-flex items-center gap-2 ${item.status === "Failed" ? "text-[#ffb5b5]" : "text-[#d7d3ff]"}`}
                  >
                    <span
                      className={`h-2.5 w-2.5 rounded-full ${item.status === "Failed" ? "bg-[#ff9b9b]" : "bg-[#c5c1ff]"}`}
                    />
                    {item.status.toUpperCase()}
                  </span>
                </td>
                <td className="px-6 py-4">
                  <div className="flex justify-end gap-5 text-[#d8d4e6]">
                    <button
                      aria-label="Download documentation"
                      disabled={item.status.toLowerCase() === "failed"}
                      className="rounded-sm outline-none transition hover:text-[#c5c1ff] focus-visible:ring-2 focus-visible:ring-[#bbb7ff] disabled:cursor-not-allowed disabled:opacity-35 disabled:hover:text-[#d8d4e6]"
                      onClick={() => handleDownload(item.id)}
                    >
                      <Download
                        className={`h-5 w-5 cursor-pointer ${item.status === "Failed" ? "opacity-35" : "hover:text-[#55dfff]"}`}
                      />
                    </button>
                    <button
                      aria-label="View documentation"
                      disabled={item.status.toLowerCase() === "failed"}
                      className="rounded-sm outline-none transition hover:text-[#c5c1ff] focus-visible:ring-2 focus-visible:ring-[#bbb7ff] disabled:cursor-not-allowed disabled:opacity-35 disabled:hover:text-[#d8d4e6]"
                      onClick={() => onViewDocument(item.id)}
                    >
                      <Eye className="h-5 w-5 cursor-pointer" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button
        type="button"
        className="flex w-full items-center justify-center gap-2 border-t border-[#32313f] px-6 py-4 text-sm text-[#d7d3ff] transition hover:bg-[#111115] hover:text-white"
      >
        View All Activity
        <ShieldCheck className="h-4 w-4" />
      </button>
    </section>
  );
}
