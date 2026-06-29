
import { type ComponentType } from "react";

export type DocHistoryItem = {
  id: string
  topics: string[];
  created_at: string;
  format: "markdown" | "json";
  status: string;
};

export type Pillar = {
  id: string;
  title: string;
  description: string;
  icon: ComponentType<{ className?: string }>;
};

export type DocTopics = {
  id: string;
  title: string;
  description: string;
  icon?: ComponentType<{ className?: string }>;
};

export type DocSection = {
  topic_id: string;
  title: string;
  content: string;
  status: string;
  error: string;
  tokens_used: number;
};

export type DocDetail = {
  id: string;
  repository_id: string;
  repo_full_name: string;
  topics: string[];
  user_context: string | null;
  sections: DocSection[];
  full_document: string;
  status: string;
  total_tokens: number;
  created_at: string;
  updated_at: string;
  format: "markdown" | "json";
};

export type MarkdownBlock =
  | { type: "heading"; text: string; level: number }
  | { type: "paragraph"; text: string }
  | { type: "blockquote"; text: string }
  | { type: "list"; ordered: boolean; items: string[] }
  | { type: "code"; code: string; language?: string }
  | { type: "rule" };
