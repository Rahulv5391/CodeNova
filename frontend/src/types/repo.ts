export type RepositoryStatus =
  | "pending"
  | "queued"
  | "cloning"
  | "parsing"
  | "graph_building"
  | "embedding"
  | "ready"
  | "failed"
  | "updating";


export type Repository = {
  id: string;
  github_url: string;
  full_name: string;
  branch?: string;
  description?: string | null;
  lang?: string | null;
  status: RepositoryStatus;
  total_files: number;
  total_functions: number;
  total_classes: number;
  indexed_chunks: number;
  created_at: string;
  updated_at: string;
  progress: number;
};


export type TreeNode = {
  name: string;
  path: string;
  type: "dir" | "file";
  size: number | null;
  children: TreeNode[] | null;
};
