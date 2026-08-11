import { FormEvent, useState } from "react";
import type { CreateJobInput } from "../api";

interface Props {
  backends: string[];
  submitting: boolean;
  onSubmit: (input: CreateJobInput) => void;
}

export default function UploadForm({ backends, submitting, onSubmit }: Props) {
  const [referenceImage, setReferenceImage] = useState<File | null>(null);
  const [drivingVideo, setDrivingVideo] = useState<File | null>(null);
  const [backend, setBackend] = useState(backends[0] ?? "mock");
  const [prompt, setPrompt] = useState("");
  const [width, setWidth] = useState(720);
  const [height, setHeight] = useState(1280);
  const [fps, setFps] = useState(24);
  const [steps, setSteps] = useState(40);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!referenceImage || !drivingVideo) return;
    onSubmit({
      referenceImage,
      drivingVideo,
      backend,
      prompt,
      promptRef: "reference video of the character's motion",
      width,
      height,
      fps,
      clipLen: 81,
      sampleGuideScale: 3.0,
      steps,
      seed: -1,
    });
  }

  return (
    <form className="upload-form" onSubmit={handleSubmit}>
      <label>
        Reference image (the character to animate)
        <input
          type="file"
          accept="image/png,image/jpeg,image/webp"
          onChange={(e) => setReferenceImage(e.target.files?.[0] ?? null)}
          required
        />
      </label>

      <label>
        Driving video (the motion to transfer)
        <input
          type="file"
          accept="video/mp4,video/webm,video/quicktime"
          onChange={(e) => setDrivingVideo(e.target.files?.[0] ?? null)}
          required
        />
      </label>

      <label>
        Engine
        <select value={backend} onChange={(e) => setBackend(e.target.value)}>
          {backends.length === 0 && <option value="mock">mock (no engines detected)</option>}
          {backends.map((b) => (
            <option key={b} value={b}>
              {b}
            </option>
          ))}
        </select>
      </label>

      <label>
        Appearance prompt (optional)
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Describe the character's appearance and background"
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
        Diffusion steps ({steps})
        <input type="range" min={1} max={60} value={steps} onChange={(e) => setSteps(Number(e.target.value))} />
      </label>

      <button type="submit" disabled={submitting || !referenceImage || !drivingVideo}>
        {submitting ? "Submitting..." : "Generate animation"}
      </button>
    </form>
  );
}
