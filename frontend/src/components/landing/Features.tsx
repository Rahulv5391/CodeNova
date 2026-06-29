import { Card } from "@/components/ui/card";
import {
  Network,
  MessageSquare,
  GitBranch,
  FileText,
} from "lucide-react";

const features = [
  {
    icon: Network,
    title: "Knowledge Graph",
    desc: "Visualize relationships between files and services.",
  },
  {
    icon: MessageSquare,
    title: "AI Chat",
    desc: "Ask questions about any repository.",
  },
  {
    icon: GitBranch,
    title: "Architecture Insights",
    desc: "Understand dependencies instantly.",
  },
  {
    icon: FileText,
    title: "Documentation",
    desc: "Generate docs automatically.",
  },
];

export default function Features() {
  return (
    <section
      id="features"
      className="container mx-auto px-6 py-20"
    >
      <div className="text-center">
        <h2 className="text-4xl font-bold">
          Everything You Need
        </h2>

        <p className="mt-4 text-muted-foreground">
          Built for developers, architects and teams.
        </p>
      </div>

      <div className="mt-12 grid md:grid-cols-2 lg:grid-cols-4 gap-6">
        {features.map((feature) => (
          <Card key={feature.title} className="p-6">
            <feature.icon className="h-8 w-8" />

            <h3 className="mt-4 font-semibold">
              {feature.title}
            </h3>

            <p className="mt-2 text-sm text-muted-foreground">
              {feature.desc}
            </p>
          </Card>
        ))}
      </div>
    </section>
  );
}