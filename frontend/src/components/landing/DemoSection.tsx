import { Card } from "@/components/ui/card";

export default function DemoSection() {
  return (
    <section className="container mx-auto px-6 py-24">

      <Card className="overflow-hidden border-white/10 bg-black">

        <div className="border-b border-white/10 p-4 flex gap-2">
          <div className="h-3 w-3 rounded-full bg-red-500" />
          <div className="h-3 w-3 rounded-full bg-yellow-500" />
          <div className="h-3 w-3 rounded-full bg-green-500" />
        </div>

        <div className="grid lg:grid-cols-2">

          <div className="border-r border-white/10 p-8">
            <p className="text-cyan-400">
              $ Analyze microsoft/vscode
            </p>

            <div className="mt-6 space-y-4 text-sm">

              <div>✓ 17,232 files indexed</div>

              <div>✓ 4.2M tokens embedded</div>

              <div>✓ Knowledge graph generated</div>

              <div>✓ Documentation generated</div>

            </div>
          </div>

          <div className="p-8">

            <div className="rounded-xl border border-white/10 p-4">

              <div className="text-sm text-muted-foreground">
                How does authentication work?
              </div>

              <div className="mt-4 text-sm leading-relaxed">
                Authentication is handled through
                AuthenticationService which validates
                JWT tokens before forwarding requests
                to protected controllers...
              </div>

            </div>

          </div>

        </div>

      </Card>

    </section>
  );
}