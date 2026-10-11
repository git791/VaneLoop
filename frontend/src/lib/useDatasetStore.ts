import { create } from "zustand";

interface DatasetState {
  dataset: string;
  setDataset: (ds: string) => void;
}

export const useDatasetStore = create<DatasetState>((set) => ({
  dataset: "FD001",
  setDataset: (dataset: string) => set({ dataset }),
}));
