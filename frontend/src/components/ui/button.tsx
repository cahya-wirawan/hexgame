import * as React from "react";

import { cn } from "../../lib/utils";

export function Button({ className, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={cn(
        "inline-flex h-9 items-center justify-center gap-2 rounded-md border border-slate-300 bg-white px-3 text-sm font-medium text-slate-900 shadow-sm transition-colors hover:bg-slate-100 disabled:pointer-events-none disabled:opacity-50",
        className
      )}
      {...props}
    />
  );
}
