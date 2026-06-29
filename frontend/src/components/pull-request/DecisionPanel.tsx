"use client";

import { PRDecisionRequest, PullRequestPanel } from "@/types/pull-request";
import { Check, GitMerge, Loader2, X } from "lucide-react";
import { useMemo, useState } from "react";


export default function DecisionPanel({decisionOpen, onDecisionOpenChange, onDecision, isApproving, pullRequest} : PullRequestPanel) {

    const [action, setAction] = useState<PRDecisionRequest["action"]>("approve");
    const [note, setNote] = useState("");
    const [mergeOnApprove, setMergeOnApprove] = useState(false);
    const [mergeMethod, setMergeMethod] = useState<PRDecisionRequest["merge_method"]>("merge");
    
    const decisionPayload = useMemo<PRDecisionRequest>(
    () => ({
        action,
        note,
        merge_on_approve: action === "approve" ? mergeOnApprove : false,
        merge_method: mergeMethod,
    }),
    [action, note, mergeMethod, mergeOnApprove],
    );

    const decisionLabel =
    action === "approve"
      ? mergeOnApprove
        ? "Approve and Merge"
        : "Approve PR"
      : "Reject PR";

    return <>
    {decisionOpen ? (
          <button
            type="button"
            className="absolute inset-0 bg-black/45 cursor-pointer"
            aria-label="Close decision panel"
            onClick={() => onDecisionOpenChange(false)}
          />
        ) : null}

        <div
          className={`absolute 2 translate-x-1/2 w-[50%] bottom-0 z-10 flex flex-col border-t border-[#32313f] bg-[#111115] shadow-[0_-30px_80px_rgba(0,0,0,0.56)] transition-transform duration-300 ${
            decisionOpen ? "translate-y-0" : "translate-y-full"
          }`}
        >
          <div className="flex shrink-0 items-start justify-between gap-4 border-b border-[#32313f] p-5">
            <div>
              <h3 className="mt-2 font-display text-2xl font-bold text-white">
                Approve or reject PR
              </h3>
            </div>
            <button
              type="button"
              className="grid h-9 w-9 place-items-center rounded-md border border-[#444254] text-[#d8d4e6] transition hover:bg-[#1b1a20] hover:text-white cursor-pointer"
              onClick={() => onDecisionOpenChange(false)}
              aria-label="Close decision panel"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto p-5 pb-8">
            <div className="space-y-4">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#aaa7b8]">
                Your Decision
              </p>
              <div className="mt-3 grid grid-cols-2 rounded-md border border-[#444254] bg-[#0d0d12] p-1">
                <button
                  type="button"
                  className={`flex h-10 items-center cursor-pointer justify-center gap-2 rounded-sm text-sm font-semibold transition ${
                    action === "approve"
                      ? "bg-[#5df08c] text-[#06140b]"
                      : "text-[#d8d4e6] hover:bg-[#1b1a20] hover:text-white"
                  }`}
                  onClick={() => setAction("approve")}
                >
                  <Check className="h-4 w-4" />
                  Approve
                </button>
                <button
                  type="button"
                  className={`flex h-10 items-center cursor-pointer justify-center gap-2 rounded-sm text-sm font-semibold transition ${
                    action === "reject"
                      ? "bg-[#ff9bad] text-[#23070d]"
                      : "text-[#d8d4e6] hover:bg-[#1b1a20] hover:text-white"
                  }`}
                  onClick={() => setAction("reject")}
                >
                  <X className="h-4 w-4" />
                  Reject
                </button>
              </div>
            </div>

            <label className="block">
              <span className="text-xs font-bold uppercase tracking-[0.16em] text-[#aaa7b8]">
                Decision Note
              </span>
              <textarea
                className="mt-2 min-h-24 w-full resize-y rounded-md border border-[#444254] bg-[#0d0d12] p-3 text-sm leading-6 text-[#f4f0ff] outline-none transition placeholder:text-[#777381] focus:border-[#b8b2ff]"
                maxLength={2000}
                placeholder={
                  action === "approve"
                    ? "Optional approval note for GitHub..."
                    : "Add the rejection reason or requested changes..."
                }
                value={note}
                onChange={(event) => setNote(event.target.value)}
              />
              <span className="mt-1 block text-right font-mono text-xs text-[#8f8b9c]">
                {note.length}/2000
              </span>
            </label>

            {action === "approve" ? (
              <div className="rounded-md border border-[#32313f] bg-[#0d0d12] p-4">
                <label className="flex items-start gap-3 text-sm text-[#d8d4e6]">
                  <input
                    type="checkbox"
                    className="mt-1 h-4 w-4 accent-[#bbb7ff]"
                    checked={mergeOnApprove}
                    onChange={(event) =>
                      setMergeOnApprove(event.target.checked)
                    }
                  />
                  <span>
                    <span className="block font-semibold text-white">
                      Merge after approval
                    </span>
                    <span className="mt-1 block text-xs leading-5 text-[#aaa7b8]">
                      Posts an APPROVE review first, then merges using the
                      selected method.
                    </span>
                  </span>
                </label>

                {mergeOnApprove ? (
                  <label className="mt-4 block">
                    <span className="text-xs font-bold uppercase tracking-[0.16em] text-[#aaa7b8]">
                      Merge Method
                    </span>
                    <select
                      className="mt-2 h-10 w-full rounded-md border border-[#444254] bg-[#121216] px-3 text-sm font-semibold text-[#f4f0ff] outline-none transition focus:border-[#b8b2ff]"
                      value={mergeMethod}
                      onChange={(event) =>
                        setMergeMethod(
                          event.target
                            .value as PRDecisionRequest["merge_method"],
                        )
                      }
                    >
                      <option value="merge">Create a merge commit</option>
                      <option value="squash">Squash and merge</option>
                      <option value="rebase">Rebase and merge</option>
                    </select>
                  </label>
                ) : null}
              </div>
            ) : null}
          </div>

          <button
            type="button"
            disabled={!pullRequest || isApproving}
            className={`sticky bottom-0 cursor-pointer z-10 mt-5 flex h-12 w-full items-center justify-center gap-2 rounded-md font-semibold shadow-[0_-14px_28px_rgba(17,17,21,0.88)] transition disabled:cursor-not-allowed disabled:opacity-50 ${
              action === "approve"
                ? "bg-[#5df08c] text-[#06140b] hover:bg-[#86efac]"
                : "bg-[#ff9bad] text-[#23070d] hover:bg-[#ffc0ca]"
            }`}
            onClick={() => onDecision(decisionPayload)}
          >
            {isApproving ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : action === "approve" && mergeOnApprove ? (
              <GitMerge className="h-5 w-5" />
            ) : action === "approve" ? (
              <Check className="h-5 w-5" />
            ) : (
              <X className="h-5 w-5" />
            )}
            {isApproving ? "Submitting decision..." : decisionLabel}
          </button>
          </div>
        </div>
    </>
}
