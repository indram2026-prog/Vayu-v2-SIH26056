export function SkeletonBar({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-ink/10 dark:bg-ink-dark/10 ${className}`} />;
}

export function DashboardSkeleton() {
  return (
    <div className="space-y-5" aria-busy="true" aria-label="Loading index data">
      <div className="flex items-baseline gap-4">
        <SkeletonBar className="h-14 w-40" />
        <SkeletonBar className="h-4 w-56" />
      </div>
      <div className="section space-y-3">
        <SkeletonBar className="h-3 w-32" />
        <SkeletonBar className="h-40 w-full" />
      </div>
      <div className="section space-y-2">
        <SkeletonBar className="h-3 w-40" />
        {Array.from({ length: 5 }).map((_, i) => (
          <SkeletonBar key={i} className="h-6 w-full" />
        ))}
      </div>
    </div>
  );
}
