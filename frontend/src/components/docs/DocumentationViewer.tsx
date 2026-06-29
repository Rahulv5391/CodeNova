import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { DocDetail, MarkdownBlock } from "@/types/doc";
import { getDateTime } from "@/utils/repo";
import { Loader2 } from "lucide-react";
import { Fragment, type ReactNode, useMemo } from "react";

export function DocumentationViewer({
  doc,
  error,
  isLoading,
  open,
  onOpenChange,
}: {
  doc: DocDetail | null;
  error: string;
  isLoading: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[100vh] max-w-[min(1100px,calc(100%-2rem))] overflow-hidden border border-[#444254] bg-[#08080b] p-0 text-[#d8d4e6] shadow-[0_24px_90px_rgba(0,0,0,0.52)] sm:max-w-[min(1100px,calc(100%-2rem))]">
        <DialogHeader className="border-b border-[#32313f] px-6 py-5 pr-14">
          <DialogTitle className="font-display text-xl font-bold text-white">
            {doc?.format === "json" ? "Documentation JSON" : "Readme.md"}
          </DialogTitle>
          <DialogDescription className="text-sm text-[#aaa7b8]">
            {doc
              ? `${doc.repo_full_name} - ${getDateTime(doc.created_at)}`
              : "Loading documentation..."}
          </DialogDescription>
        </DialogHeader>

        <div className="flex min-h-0 flex-1 flex-col">
          {isLoading ? (
            <div className="grid min-h-[420px] place-items-center">
              <div className="flex items-center gap-3 text-[#d7d3ff]">
                <Loader2 className="h-5 w-5 animate-spin" />
                Loading documentation...
              </div>
            </div>
          ) : error ? (
            <div className="m-6 rounded-md border border-[#6e2635] bg-[#220b12] px-4 py-3 text-sm text-[#ffb7c4]">
              {error}
            </div>
          ) : doc ? (
            <LoadedDocumentationViewer key={doc.id} doc={doc} />
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function LoadedDocumentationViewer({ doc }: { doc: DocDetail }) {
  return (
    <div className="max-h-[calc(100vh-180px)] overflow-auto px-6 py-6">
      {doc.format === "markdown" ? (
        <MarkdownDocument content={doc.full_document} />
      ) : (
        <pre className="overflow-x-auto rounded-md border border-[#343244] bg-[#09090d] p-5 text-sm leading-6 text-[#d8f8ff]">
          <code>{JSON.stringify(doc.sections, null, 2)}</code>
        </pre>
      )}
    </div>
  );
}

function parseMarkdown(content: string): MarkdownBlock[] {
  const blocks: MarkdownBlock[] = [];
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  let index = 0;

  function readParagraph() {
    const paragraph: string[] = [];

    while (index < lines.length) {
      const line = lines[index];
      const trimmed = line.trim();

      if (
        !trimmed ||
        trimmed.startsWith("#") ||
        trimmed.startsWith(">") ||
        trimmed.startsWith("```") ||
        trimmed === "---" ||
        /^(\d+\.\s+|[-*]\s+)/.test(trimmed)
      ) {
        break;
      }

      paragraph.push(trimmed);
      index += 1;
    }

    if (paragraph.length) {
      blocks.push({ type: "paragraph", text: paragraph.join(" ") });
    }
  }

  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();

    if (!trimmed) {
      index += 1;
      continue;
    }

    if (trimmed === "---") {
      blocks.push({ type: "rule" });
      index += 1;
      continue;
    }

    if (trimmed.startsWith("```")) {
      const language = trimmed.slice(3).trim() || undefined;
      const code: string[] = [];
      index += 1;

      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        code.push(lines[index]);
        index += 1;
      }

      if (index < lines.length) index += 1;
      blocks.push({ type: "code", language, code: code.join("\n") });
      continue;
    }

    const headingMatch = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      blocks.push({
        type: "heading",
        level: headingMatch[1].length,
        text: headingMatch[2],
      });
      index += 1;
      continue;
    }

    if (trimmed.startsWith(">")) {
      const quote: string[] = [];

      while (index < lines.length && lines[index].trim().startsWith(">")) {
        quote.push(lines[index].trim().replace(/^>\s?/, ""));
        index += 1;
      }

      blocks.push({ type: "blockquote", text: quote.join("\n") });
      continue;
    }

    const listMatch = trimmed.match(/^(\d+\.\s+|[-*]\s+)(.+)$/);
    if (listMatch) {
      const ordered = /^\d+\./.test(listMatch[1]);
      const items: string[] = [];

      while (index < lines.length) {
        const itemMatch = lines[index].trim().match(/^(\d+\.\s+|[-*]\s+)(.+)$/);

        if (!itemMatch || /^\d+\./.test(itemMatch[1]) !== ordered) {
          break;
        }

        items.push(itemMatch[2].trim());
        index += 1;
      }

      blocks.push({ type: "list", ordered, items });
      continue;
    }

    readParagraph();
  }

  return blocks;
}

function renderInlineMarkdown(text: string): ReactNode[] {
  const parts: ReactNode[] = [];
  const tokenRegex =
    /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\((https?:\/\/[^)\s]+)\))/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = tokenRegex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }

    const token = match[0];

    if (token.startsWith("**")) {
      parts.push(
        <strong key={match.index} className="font-semibold text-[#f4f0ff]">
          {token.slice(2, -2)}
        </strong>,
      );
    } else if (token.startsWith("`")) {
      parts.push(
        <code
          key={match.index}
          className="rounded border border-[#3c394d] bg-[#0b0b11] px-1.5 py-0.5 font-mono text-[0.9em] text-[#b8f7ff]"
        >
          {token.slice(1, -1)}
        </code>,
      );
    } else {
      const linkMatch = token.match(/^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/);
      parts.push(
        <a
          key={match.index}
          href={linkMatch?.[2] ?? "#"}
          target="_blank"
          rel="noreferrer"
          className="font-medium text-[#9adfff] underline decoration-[#4ea3b7] underline-offset-4 hover:text-white"
        >
          {linkMatch?.[1] ?? token}
        </a>,
      );
    }

    lastIndex = tokenRegex.lastIndex;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts;
}

function MarkdownDocument({ content }: { content: string }) {
  const blocks = useMemo(() => parseMarkdown(content), [content]);

  return (
    <article className="mx-auto max-w-4xl text-[#d8d4e6]">
      {blocks.map((block, index) => {
        if (block.type === "heading") {
          const Heading =
            block.level === 1 ? "h1" : block.level === 2 ? "h2" : "h3";
          const headingClass =
            block.level === 1
              ? "mt-0 text-3xl"
              : block.level === 2
                ? "mt-9 text-2xl"
                : "mt-7 text-xl";

          return (
            <Heading
              key={index}
              className={`${headingClass} mb-4 font-display font-bold leading-tight text-white`}
            >
              {renderInlineMarkdown(block.text)}
            </Heading>
          );
        }

        if (block.type === "blockquote") {
          return (
            <blockquote
              key={index}
              className="my-5 border-l-4 border-[#bbb7ff] bg-[#111119] px-4 py-3 text-sm leading-7 text-[#c9c5d8]"
            >
              {block.text.split("\n").map((line, lineIndex) => (
                <Fragment key={lineIndex}>
                  {renderInlineMarkdown(line)}
                  {lineIndex < block.text.split("\n").length - 1 ? (
                    <br />
                  ) : null}
                </Fragment>
              ))}
            </blockquote>
          );
        }

        if (block.type === "list") {
          const ListTag = block.ordered ? "ol" : "ul";

          return (
            <ListTag
              key={index}
              className={`my-5 space-y-2 pl-6 leading-7 ${
                block.ordered ? "list-decimal" : "list-disc"
              }`}
            >
              {block.items.map((item, itemIndex) => (
                <li key={itemIndex} className="pl-1">
                  {renderInlineMarkdown(item)}
                </li>
              ))}
            </ListTag>
          );
        }

        if (block.type === "code") {
          return (
            <div
              key={index}
              className="my-5 overflow-hidden rounded-md border border-[#343244] bg-[#09090d]"
            >
              {block.language ? (
                <div className="border-b border-[#343244] px-3 py-2 font-mono text-xs uppercase tracking-[0.16em] text-[#8f8b9c]">
                  {block.language}
                </div>
              ) : null}
              <pre className="overflow-x-auto p-4 text-sm leading-6">
                <code className="font-mono text-[#d8f8ff]">{block.code}</code>
              </pre>
            </div>
          );
        }

        if (block.type === "rule") {
          return <hr key={index} className="my-8 border-[#32313f]" />;
        }

        return (
          <p key={index} className="my-4 leading-7">
            {renderInlineMarkdown(block.text).map((part, partIndex) => (
              <Fragment key={partIndex}>{part}</Fragment>
            ))}
          </p>
        );
      })}
    </article>
  );
}
