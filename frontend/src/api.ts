export type JobStatus = "queued" | "running" | "completed" | "failed" | "cancelled";

export const FINISHED_STATUSES: JobStatus[] = ["completed", "failed", "cancelled"];

export interface JobParams {
  width: number;
  height: number;
  fps: number;
  clip_len: number;
  sample_guide_scale: number;
  steps: number;
  seed: number;
  prompt: string;
  prompt_ref: string;
  backend: string;
}

export interface Job {
  id: string;
  status: JobStatus;
  backend: string;
  params: JobParams;
  output_video_url: string | null;
  error: string | null;
  log: string | null;
  processing_seconds: number | null;
  created_at: string;
  updated_at: string;
}

export interface BackendInfo {
  name: string;
  description: string;
  available: boolean;
}

export interface BackendsResponse {
  available: string[];
  default: string;
  backends: BackendInfo[];
}

export interface CreateJobInput {
  referenceImage: File;
  drivingVideo: File;
  backend: string;
  prompt: string;
  promptRef: string;
  width: number;
  height: number;
  fps: number;
  clipLen: number;
  sampleGuideScale: number;
  steps: number;
  seed: number;
}

async function unwrap<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed with status ${res.status}`);
  }
  return res.json();
}

export async function listBackends(): Promise<BackendsResponse> {
  const res = await fetch("/api/backends");
  return unwrap<BackendsResponse>(res);
}

export async function createJob(input: CreateJobInput): Promise<Job> {
  const form = new FormData();
  form.set("reference_image", input.referenceImage);
  form.set("driving_video", input.drivingVideo);
  form.set("backend", input.backend);
  form.set("prompt", input.prompt);
  form.set("prompt_ref", input.promptRef);
  form.set("width", String(input.width));
  form.set("height", String(input.height));
  form.set("fps", String(input.fps));
  form.set("clip_len", String(input.clipLen));
  form.set("sample_guide_scale", String(input.sampleGuideScale));
  form.set("steps", String(input.steps));
  form.set("seed", String(input.seed));

  const res = await fetch("/api/jobs", { method: "POST", body: form });
  return unwrap<Job>(res);
}

export async function getJob(id: string): Promise<Job> {
  const res = await fetch(`/api/jobs/${id}`);
  return unwrap<Job>(res);
}

export async function listJobs(): Promise<Job[]> {
  const res = await fetch("/api/jobs");
  return unwrap<Job[]>(res);
}

export async function cancelJob(id: string): Promise<Job> {
  const res = await fetch(`/api/jobs/${id}/cancel`, { method: "POST" });
  return unwrap<Job>(res);
}

export async function deleteJob(id: string): Promise<void> {
  const res = await fetch(`/api/jobs/${id}`, { method: "DELETE" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed with status ${res.status}`);
  }
}
