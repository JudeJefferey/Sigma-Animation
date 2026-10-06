export type JobStatus = "queued" | "running" | "completed" | "failed" | "cancelled";

export const FINISHED_STATUSES: JobStatus[] = ["completed", "failed", "cancelled"];

export type JobMode = "motion_transfer" | "image_to_video" | "reanimate";

// The engine capability each job mode needs (mirrors the backend's ENGINE_MODE).
export const ENGINE_MODE: Record<JobMode, string> = {
  motion_transfer: "motion_transfer",
  image_to_video: "image_to_video",
  reanimate: "motion_transfer",
};

export interface JobParams {
  mode: JobMode;
  source_job_id: string | null;
  width: number;
  height: number;
  fps: number;
  output_fps: number;
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
  modes: string[];
  max_clip_seconds: number | null;
}

export interface BackendsResponse {
  available: string[];
  default: string;
  backends: BackendInfo[];
}

export interface CreateJobInput {
  mode: JobMode;
  referenceImage: File | null;
  drivingVideo: File | null;
  sourceVideo: File | null;
  sourceJobId: string | null;
  backend: string;
  prompt: string;
  promptRef: string;
  width: number;
  height: number;
  fps: number;
  outputFps: number;
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
  form.set("mode", input.mode);
  if (input.referenceImage) form.set("reference_image", input.referenceImage);
  if (input.drivingVideo) form.set("driving_video", input.drivingVideo);
  if (input.sourceVideo) form.set("source_video", input.sourceVideo);
  if (input.sourceJobId) form.set("source_job_id", input.sourceJobId);
  form.set("backend", input.backend);
  form.set("prompt", input.prompt);
  form.set("prompt_ref", input.promptRef);
  form.set("width", String(input.width));
  form.set("height", String(input.height));
  form.set("fps", String(input.fps));
  form.set("output_fps", String(input.outputFps));
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
