import type { Job } from "../api";

interface Props {
  job: Job;
  onCancel: (jobId: string) => void;
  onDelete: (jobId: string) => void;
}

const STATUS_LABEL: Record<Job["status"], string> = {
  queued: "Queued",
  running: "Generating...",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

export default function JobStatus({ job, onCancel, onDelete }: Props) {
  const active = job.status === "queued" || job.status === "running";

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

      {job.log && (
        <details className="job-card__log">
          <summary>Engine log</summary>
          <pre>{job.log}</pre>
        </details>
      )}

      <div className="job-card__footer">
        <span className="job-card__timing">
          {job.processing_seconds != null && `${job.processing_seconds.toFixed(1)}s`}
        </span>
        <span className="job-card__actions">
          {job.status === "completed" && job.output_video_url && (
            <a href={job.output_video_url} download={`${job.id}.mp4`}>
              Download
            </a>
          )}
          {active ? (
            <button type="button" onClick={() => onCancel(job.id)}>
              Cancel
            </button>
          ) : (
            <button type="button" onClick={() => onDelete(job.id)}>
              Delete
            </button>
          )}
        </span>
      </div>
    </div>
  );
}
