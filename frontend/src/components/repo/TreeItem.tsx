import { Repository, TreeNode } from "@/types/repo";
import { Icon } from "@iconify/react";
import { ChevronRight } from "lucide-react";
import { useState } from "react";


function getFileIcon(filename: string) {
  const ext = filename.split(".").pop()?.toLowerCase();

  if (filename === "requirements.txt") return "vscode-icons:file-type-pip";
  if (filename === ".env.example" || filename === ".env")
    return "vscode-icons:file-type-dotenv";
  if (filename === ".gitignore") return "vscode-icons:file-type-git";

  switch (ext) {
    case "tsx":
      return "vscode-icons:file-type-reactts";
    case "ts":
      return "vscode-icons:file-type-typescript";
    case "jsx":
      return "vscode-icons:file-type-reactjs";
    case "js":
      return "vscode-icons:file-type-js-official";
    case "json":
      return "vscode-icons:file-type-json";
    case "css":
      return "vscode-icons:file-type-css";
    case "html":
      return "vscode-icons:file-type-html";
    case "py":
      return "vscode-icons:file-type-python";
    case "java":
      return "vscode-icons:file-type-java";
    case "md":
      return "vscode-icons:file-type-markdown";
    case "yml":
    case "yaml":
      return "vscode-icons:file-type-yaml";
    case "Dockerfile":
      return "vscode-icons:file-type-docker2";
    case "go":
      return "vscode-icons:file-type-go";
    case "package.json":
      return "vscode-icons:file-type-node";
    case "README.md":
      return "vscode-icons:file-type-readme";
    case "rs":
      return "vscode-icons:file-type-rust";
    case "kt":
      return "vscode-icons:file-type-kotlin";
    case "swift":
      return "vscode-icons:file-type-swift";
    case "php":
      return "vscode-icons:file-type-php";
    case "rb":
      return "vscode-icons:file-type-ruby";
    case "c":
      return "vscode-icons:file-type-c";
    case "cpp":
    case "cc":
    case "cxx":
      return "vscode-icons:file-type-cpp";
    case "cs":
      return "vscode-icons:file-type-csharp";
    case "sql":
      return "vscode-icons:file-type-sql";
    case "sh":
      return "vscode-icons:file-type-shell";
    case "toml":
      return "vscode-icons:file-type-config";
    case "xml":
      return "vscode-icons:file-type-xml";
    case "graphql":
    case "gql":
      return "vscode-icons:file-type-graphql";
    default:
      return "vscode-icons:default-file";
  }
}


export function FileTree({
  nodes,
  depth = 0,
  repo,
}: {
  nodes: TreeNode[];
  depth?: number;
  repo: Repository | null;
}) {
  return (
    <div className={depth === 0 ? "grid gap-1" : "mt-1 grid gap-1"}>
      {nodes.map((node) => (
        <TreeItem key={node.path} node={node} depth={depth} repo={repo} />
      ))}
    </div>
  );
}


function TreeItem({
  node,
  depth,
  repo,
}: {
  node: TreeNode;
  depth: number;
  repo: Repository | null;
}) {
  const [open, setOpen] = useState(depth < 1);
  const isDirectory = node.type === "dir";

  return (
    <div>
      <button
        type="button"
        className="flex h-8 w-full items-center gap-2 rounded-md px-2 text-left text-sm text-[#d8d4e6] hover:bg-[#252334]"
        style={{ paddingLeft: `${8 + depth * 16}px` }}
        onClick={() => isDirectory && setOpen((current) => !current)}
      >
        {isDirectory ? (
          <ChevronRight
            className={`h-4 w-4 shrink-0 text-[#8f8b9c] transition-transform ${
              open ? "rotate-90" : ""
            }`}
          />
        ) : (
          <span className="h-4 w-4 shrink-0" />
        )}
        {isDirectory ? (
          <>
            <Icon
              icon={
                open
                  ? "vscode-icons:default-folder-opened"
                  : "vscode-icons:default-folder"
              }
              className="h-4 w-4 shrink-0"
            />
            <span className="truncate font-mono">{node.name}</span>
          </>
        ) : (
          <>
            <Icon icon={getFileIcon(node.name)} className="h-4 w-4 shrink-0" />
            {repo ? (
              <a
                href={`${repo.github_url.replace(/\.git$/, "")}/blob/${repo.branch}/${node.path}`}
                target="_blank"
              >
                <span className="truncate font-mono">{node.name}</span>
              </a>
            ) : (
              <span className="truncate font-mono">{node.name}</span>
            )}
          </>
        )}
      </button>

      {isDirectory && open && node.children?.length ? (
        <FileTree nodes={node.children} depth={depth + 1} repo={repo} />
      ) : null}
    </div>
  );
}