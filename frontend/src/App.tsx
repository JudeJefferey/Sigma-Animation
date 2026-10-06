import { useEffect, useRef, useState } from "react";
import UploadForm from "./components/UploadForm";
import JobStatus from "./components/JobStatus";
import {
  FINISHED_STATUSES,
  cancelJob,
  createJob,
  deleteJob,
  getJob,
  listBackends,
  listJobs,
  type BackendsResponse,
  type CreateJobInput,
  type Job,
} from "./api";

const POLL_INTERVAL_MS = 2000;

export default function App() {
  const [backends, setBackends] = useState<BackendsResponse | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const pollTimers = useRef<Record<string, ReturnType<typeof setInterval>>>({});

  useEffect(() => {
    listBackends().then(setBackends).catch(() => setBackends(null));
    listJobs()
      .then((initialJobs) => {
        setJobs(initialJobs);
        initialJobs
          .filter((j) => j.status === "queued" || j.status === "running")
          .forEach((j) => watchJob(j.id));
      })
      .catch(() => setJobs([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    return () => {
      Object.values(pollTimers.current).forEach(clearInterval);
    };
  }, []);

  function watchJob(jobId: string) {
    if (pollTimers.current[jobId]) return;
    const timer = setInterval(async () => {
      try {
        const updated = await getJob(jobId);
        setJobs((prev) => prev.map((j) => (j.id === jobId ? updated : j)));
        if (FINISHED_STATUSES.includes(updated.status)) {
          stopWatching(jobId);
        }
      } catch {
        stopWatching(jobId);
      }
    }, POLL_INTERVAL_MS);
    pollTimers.current[jobId] = timer;
  }

  function stopWatching(jobId: string) {
    clearInterval(pollTimers.current[jobId]);
    delete pollTimers.current[jobId];
  }

  async function handleCancel(jobId: string) {
    setActionError(null);
    try {
      const updated = await cancelJob(jobId);
      setJobs((prev) => prev.map((j) => (j.id === jobId ? updated : j)));
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleDelete(jobId: string) {
    setActionError(null);
    try {
      await deleteJob(jobId);
      stopWatching(jobId);
      setJobs((prev) => prev.filter((j) => j.id !== jobId));
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleSubmit(input: CreateJobInput) {
    setSubmitting(true);
    setSubmitError(null);
    try {
      const job = await createJob(input);
      setJobs((prev) => [job, ...prev]);
      watchJob(job.id);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="app">
      <header className="app__header">
        <h1>Sigma Animation</h1>
        <p>Self-hosted character animation. Bring a reference image, bring a driving video, run it on your own hardware.</p>
      </header>

      <main className="app__main">
        <section className="app__panel">
          <h2>New animation</h2>
          <UploadForm backends={backends} submitting={submitting} onSubmit={handleSubmit} />
          {submitError && <div className="app__error">{submitError}</div>}
        </section>

        <section className="app__panel">
          <h2>Jobs</h2>
          {actionError && <div className="app__error">{actionError}</div>}
          {jobs.length === 0 && <p className="app__empty">No jobs yet.</p>}
          <div className="job-list">
            {jobs.map((job) => (
              <JobStatus key={job.id} job={job} onCancel={handleCancel} onDelete={handleDelete} />
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
