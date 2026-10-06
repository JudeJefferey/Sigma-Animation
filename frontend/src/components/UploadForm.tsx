import { FormEvent, useEffect, useState } from "react";
import { ENGINE_MODE, type BackendsResponse, type CreateJobInput, type Job, type JobMode } from "../api";

// Matches the backend's default SIGMA_MAX_CLIP_SECONDS.
const MAX_CLIP_SECONDS = 60;
// Smoothing targets; each must stay within the backend's SIGMA_MAX_OUTPUT_FPS (default 120).
const OUTPUT_FPS_CHOICES = [30, 48, 60, 90, 120];

const MODES: { value: JobMode; label: string; hint: string }[] = [
  { value: "motion_transfer", label: "Copy motion", hint: "A character image copies the motion in a driving video." },
  { value: "image_to_video", label: "Animate image", hint: "An image comes to life from a text description, no video needed." },
  {
    value: "reanimate",
    label: "Reanimate video",
    hint: "Give an uploaded video or a previous result new motion, or re-run a previous result with new settings.",
  },
];

type ReanimateSource = "upload" | "previous";

interface Props {
  backends: BackendsResponse | null;
  finishedJobs: Job[];
  submitting: boolean;
  onSubmit: (input: CreateJobInput) => void;
}

export default function UploadForm({ backends, finishedJobs, submitting, onSubmit }: Props) {
  const [mode, setMode] = useState<JobMode>("motion_transfer");
  const [referenceImage, setReferenceImage] = useState<File | null>(null);
  const [drivingVideo, setDrivingVideo] = useState<File | null>(null);
  const [sourceKind, setSourceKind] = useState<ReanimateSource>("upload");
  const [sourceVideo, setSourceVideo] = useState<File | null>(null);
  const [sourceJobId, setSourceJobId] = useState("");
  const [backend, setBackend] = useState("mock");
  const [prompt, setPrompt] = useState("");
  const [width, setWidth] = useState(720);
  const [height, setHeight] = useState(1280);
  const [fps, setFps] = useState(24);
  const [steps, setSteps] = useState(40);
  const [clipSeconds, setClipSeconds] = useState(3);
  const [outputFps, setOutputFps] = useState(0);
  // A target at or below the generation fps would do nothing, so treat it as off.
  const effectiveOutputFps = outputFps > fps ? outputFps : 0;
  const clipFrames = Math.round(clipSeconds * fps);

  const sourceJob = finishedJobs.find((j) => j.id === sourceJobId);
  // Reanimating a previous result without new motion re-runs that job's own
  // inputs, so it needs whatever engine capability that job's mode needs.
  const isRerun = mode === "reanimate" && sourceKind === "previous" && !drivingVideo;
  const engineMode = ENGINE_MODE[isRerun && sourceJob ? sourceJob.params.mode : mode];
  const needsPrompt = mode === "image_to_video" || (isRerun && sourceJob?.params.mode === "image_to_video");

  const engines = backends?.backends ?? [];
  const usable = engines.filter((b) => b.available && b.modes.includes(engineMode));
  const selected = engines.find((b) => b.name === backend);
  const maxSeconds = Math.min(MAX_CLIP_SECONDS, selected?.max_clip_seconds ?? MAX_CLIP_SECONDS);

  // Keep the engine valid for the current mode: the server default if it
  // fits, otherwise the first engine that's set up and can do this mode.
  useEffect(() => {
    if (!backends || usable.some((b) => b.name === backend)) return;
    const preferred = usable.find((b) => b.name === backends.default) ?? usable[0];
    if (preferred) setBackend(preferred.name);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [backends, engineMode]);

  useEffect(() => {
    if (clipSeconds > maxSeconds) setClipSeconds(maxSeconds);
  }, [clipSeconds, maxSeconds]);

  // Default the previous-result picker to the newest finished job.
  useEffect(() => {
    if (!sourceJob && finishedJobs.length > 0) setSourceJobId(finishedJobs[0].id);
  }, [finishedJobs, sourceJob]);

  // Each mode shows different file inputs; drop files picked for hidden ones
  // so they can't silently ride along (e.g. turn a re-run into a reanimate).
  // Bumped on every switch so file inputs remount empty; otherwise the browser
  // keeps showing a stale filename and ignores re-picking that same file.
  const [inputsKey, setInputsKey] = useState(0);

  function switchMode(next: JobMode) {
    setMode(next);
    setReferenceImage(null);
    setDrivingVideo(null);
    setSourceVideo(null);
    // The prompt means motion in one mode and appearance in the others.
    setPrompt("");
    setInputsKey((k) => k + 1);
  }

  const ready = (() => {
    if (mode === "motion_transfer") return Boolean(referenceImage && drivingVideo);
    if (mode === "image_to_video") return Boolean(referenceImage && prompt.trim());
    return sourceKind === "upload" ? Boolean(sourceVideo && drivingVideo) : Boolean(sourceJob);
  })();

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!ready) return;
    const reanimate = mode === "reanimate";
    onSubmit({
      mode,
      referenceImage: reanimate ? null : referenceImage,
      drivingVideo: mode === "image_to_video" ? null : drivingVideo,
      sourceVideo: reanimate && sourceKind === "upload" ? sourceVideo : null,
      sourceJobId: reanimate && sourceKind === "previous" ? sourceJobId : null,
      backend,
      prompt,
      promptRef: "reference video of the character's motion",
      width,
      height,
      fps,
      outputFps: effectiveOutputFps,
      clipLen: clipFrames,
      sampleGuideScale: 3.0,
      steps,
      seed: -1,
    });
  }

  return (
    <form className="upload-form" onSubmit={handleSubmit}>
      <div className="mode-tabs" role="tablist">
        {MODES.map((m) => (
          <button
            key={m.value}
            type="button"
            role="tab"
            aria-selected={mode === m.value}
            className={mode === m.value ? "mode-tabs__tab mode-tabs__tab--active" : "mode-tabs__tab"}
            onClick={() => switchMode(m.value)}
          >
            {m.label}
          </button>
        ))}
      </div>
      <p className="upload-form__hint">{MODES.find((m) => m.value === mode)?.hint}</p>

      {mode !== "reanimate" && (
        <label key={`image-${inputsKey}`}>
          {mode === "image_to_video" ? "Image to animate" : "Reference image (the character to animate)"}
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            onChange={(e) => setReferenceImage(e.target.files?.[0] ?? null)}
          />
        </label>
      )}

      {mode === "reanimate" && (
        <fieldset className="upload-form__fieldset">
          <legend>Video to reanimate</legend>
          <label className="upload-form__radio">
            <input
              type="radio"
              name="source"
              checked={sourceKind === "upload"}
              onChange={() => setSourceKind("upload")}
            />
            Upload a video
          </label>
          <label className="upload-form__radio">
            <input
              type="radio"
              name="source"
              checked={sourceKind === "previous"}
              disabled={finishedJobs.length === 0}
              onChange={() => setSourceKind("previous")}
            />
            A previous result{finishedJobs.length === 0 && " (none yet)"}
          </label>
          {sourceKind === "upload" ? (
            <input
              key={`source-${inputsKey}`}
              type="file"
              accept="video/mp4,video/webm,video/quicktime"
              onChange={(e) => setSourceVideo(e.target.files?.[0] ?? null)}
            />
          ) : (
            <select value={sourceJobId} onChange={(e) => setSourceJobId(e.target.value)}>
              {finishedJobs.map((j) => (
                <option key={j.id} value={j.id}>
                  {j.id.slice(0, 8)} · {j.backend} · {new Date(j.created_at).toLocaleString()}
                </option>
              ))}
            </select>
          )}
          {!isRerun && <span className="upload-form__hint">The character is taken from the video's first frame.</span>}
        </fieldset>
      )}

      {mode !== "image_to_video" && (
        <label key={`driving-${inputsKey}`}>
          {mode === "reanimate" ? "New motion (driving video)" : "Driving video (the motion to transfer)"}
          <input
            type="file"
            accept="video/mp4,video/webm,video/quicktime"
            onChange={(e) => setDrivingVideo(e.target.files?.[0] ?? null)}
          />
          {mode === "reanimate" && sourceKind === "previous" && (
            <span className="upload-form__hint">
              Leave empty to re-run that result from its original inputs with the settings below.
            </span>
          )}
        </label>
      )}

      <label>
        Engine
        <select value={backend} onChange={(e) => setBackend(e.target.value)}>
          {!backends && <option value="mock">mock (engine list unavailable)</option>}
          {engines.map((b) => (
            <option key={b.name} value={b.name} disabled={!b.available || !b.modes.includes(engineMode)}>
              {b.name}
              {!b.available ? " (not set up)" : !b.modes.includes(engineMode) ? " (can't do this)" : ""}
            </option>
          ))}
        </select>
        {selected?.description && <span className="upload-form__hint">{selected.description}</span>}
      </label>

      <label>
        {needsPrompt ? "Motion prompt" : "Appearance prompt (optional)"}
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder={
            needsPrompt
              ? isRerun
                ? "Leave empty to reuse the original prompt"
                : "Describe what happens, e.g. \"the woman turns her head and smiles, hair blowing in the wind\""
              : "Describe the character's appearance and background"
          }
          rows={3}
        />
      </label>

      <div className="grid-3">
        <label>
          Width
          <input type="number" value={width} min={64} max={1920} onChange={(e) => setWidth(Number(e.target.value))} />
        </label>
        <label>
          Height
          <input type="number" value={height} min={64} max={1920} onChange={(e) => setHeight(Number(e.target.value))} />
        </label>
        <label>
          FPS
          <input type="number" value={fps} min={1} max={60} onChange={(e) => setFps(Number(e.target.value))} />
        </label>
      </div>

      <label>
        Output FPS (smoothing)
        <select value={effectiveOutputFps} onChange={(e) => setOutputFps(Number(e.target.value))}>
          <option value={0}>Same as generated ({fps}fps)</option>
          {OUTPUT_FPS_CHOICES.filter((choice) => choice > fps).map((choice) => (
            <option key={choice} value={choice}>
              {choice}fps
            </option>
          ))}
        </select>
        <span className="upload-form__hint">
          Fills in extra frames after generation for smoother motion, without the cost of generating them.
        </span>
      </label>

      <label>
        Clip length (seconds, max {maxSeconds})
        <input
          type="number"
          value={clipSeconds}
          min={1}
          max={maxSeconds}
          step={1}
          onChange={(e) => setClipSeconds(Number(e.target.value))}
        />
        <span className="upload-form__hint">
          {clipFrames} frames at {fps}fps
          {maxSeconds < MAX_CLIP_SECONDS && ` · ${backend} is limited to ${maxSeconds}s`}
        </span>
      </label>

      <label>
        Diffusion steps ({steps})
        <input type="range" min={1} max={60} value={steps} onChange={(e) => setSteps(Number(e.target.value))} />
      </label>

      <button type="submit" disabled={submitting || !ready}>
        {submitting ? "Submitting..." : isRerun ? "Re-run with these settings" : "Generate animation"}
      </button>
    </form>
  );
}
