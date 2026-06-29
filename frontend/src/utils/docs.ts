import { api } from "@/lib/api";
import {
  Boxes,
  Braces,
  CircleAlert,
  Code2,
  Database,
  FileText,
  KeyRound,
  Layers3,
  Network,
  Rocket,
  ServerCog,
  ShieldCheck,
  SlidersHorizontal,
  TestTube2,
  Gauge,
  BookOpen,
  type LucideIcon,
} from "lucide-react";


const pillarIconMap: Record<string, LucideIcon> = {
  project_overview: Layers3,
  tech_stack: Code2,
  architecture: Network,
  api_reference: Braces,
  data_models: Boxes,
  database_schema: Database,
  authentication: KeyRound,
  dependency_graph: ServerCog,
  configuration: SlidersHorizontal,
  error_handling: CircleAlert,
  testing_strategy: TestTube2,
  deployment_guide: Rocket,
  performance_notes: Gauge,
  security_notes: ShieldCheck,
  onboarding_guide: BookOpen,
};

export function getPillarIcon(id: string): LucideIcon {
  return pillarIconMap[id] ?? FileText;
}

export async function handleDownload(docId: string) {

  const {data} = await api.get(`/docs/${docId}`);

  let content = "";
  let fileName = "";

  if (data.format === "markdown") {
    content = data.full_document;
    fileName = "README.md";
  } else {
    content = JSON.stringify(data.sections, null, 2);
    fileName = "README.json";
  }

  const blob = new Blob([content], {
    type:
      data.format === "markdown"
        ? "text/markdown;charset=utf-8"
        : "application/json;charset=utf-8",
  });

  const url = URL.createObjectURL(blob);

  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();

  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}