"use client";

import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { ArrowRight } from "lucide-react";

export default function Hero() {
  return (
    <section className="relative overflow-hidden py-36">
      <div className="container mx-auto px-6 text-center relative z-10">

        <div className="inline-flex items-center rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm">
          AI-Powered Repository Intelligence
        </div>

        <motion.h1
          initial={{ opacity: 0, y: 40 }}
          animate={{ opacity: 1, y: 0 }}
          className="mx-auto mt-8 max-w-5xl text-6xl font-bold leading-tight md:text-8xl"
        >
          Understand Any
          <br />

          <span className="bg-gradient-to-r from-cyan-400 via-blue-400 to-violet-400 bg-clip-text text-transparent">
            Codebase in Minutes
          </span>
        </motion.h1>

        <p className="mx-auto mt-8 max-w-2xl text-lg text-muted-foreground">
          Upload a GitHub repository and instantly generate
          architecture diagrams, knowledge graphs, AI-powered
          documentation and repository chat.
        </p>

        <div className="mt-10 flex justify-center gap-4">
          <Button size="lg">
            Start Free
            <ArrowRight className="ml-2 h-4 w-4" />
          </Button>

          <Button variant="outline" size="lg">
            Live Demo
          </Button>
        </div>
      </div>
    </section>
  );
}