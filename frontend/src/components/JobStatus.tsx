import type { Job } from "../api";

interface Props {
  job: Job;
}

const STATUS_LABEL: Record<Job["status"], string> = {
  queued: "Queued",
  running: "Generating...",
  completed: "Completed",
  failed: "Failed",
};

export default function JobStatus({ job }: Props) {
  return (
    <div className={`job-card job-card--${job.status}`}>
      <div className="job-card__header">
        <span className="job-card__id">{job.id.slice(0, 8)}</span>
        <span className="job-card__status">{STATUS_LABEL[job.status]}</span>
      </div>
      <div className="job-card__meta">
        engine: {job.backend} · {job.params.width}x{job.params.height} · {job.params.fps}fps
      </div>

      {job.status === "completed" && job.output_video_url && (
        <video className="job-card__video" src={job.output_video_url} controls loop />
      )}

      {job.status === "failed" && job.error && <div className="job-card__error">{job.error}</div>}

      {job.processing_seconds != null && (
        <div className="job-card__timing">{job.processing_seconds.toFixed(1)}s</div>
      )}
    </div>
  );
}
