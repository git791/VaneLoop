"use client";

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

const queryClient = new QueryClient();

export function Providers({ children }: { children: React.ReactNode }) {
  const [mswReady, setMswReady] = useState(false);

  useEffect(() => {
    async function initMsw() {
      if (typeof window !== 'undefined') {
        if (process.env.NODE_ENV === 'development') {
          const { worker } = await import('@/mocks/browser');
          await worker.start({ onUnhandledRequest: 'bypass' });
        }
        setMswReady(true);
      }
    }
    initMsw();
  }, []);

  if (!mswReady) return null; // Wait for MSW to initialize

  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
}
