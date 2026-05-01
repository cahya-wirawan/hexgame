import * as React from "react";

import { cn } from "../../lib/utils";

type BadgeProps = React.HTMLAttributes<HTMLSpanElement> & {
  tone?: "default" | "empty" | "waiting" | "full" | "winner";
};

const tones: Record<NonNullable<BadgeProps["tone"]>, string> = {
  default: "border-transparent bg-slate-900 text-white",
  empty: "border-slate-300 bg-slate-100 text-slate-700",
  waiting: "border-amber-300 bg-amber-100 text-amber-900",
  full: "border-emerald-300 bg-emerald-100 text-emerald-900",
  winner: "border-blue-300 bg-blue-100 text-blue-900"
};

export function Badge({ className, tone = "default", ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center rounded-md border px-2 text-xs font-medium",
        tones[tone],
        className
      )}
      {...props}
    />
  );
}
