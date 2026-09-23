import { type FramePayload, type RobotFramePayload, clamp } from './payload';

// 位置线性插值，离散状态保持到下一真实采样点；不使用 V1 snap。
export function samplePhysicalFrame(frames: FramePayload[], timeMs: number): FramePayload | null {
  if (!frames.length) return null;
  const t = clamp(timeMs, frames[0].offset_ms, frames[frames.length - 1].offset_ms);
  const i = frames.findIndex(f => f.offset_ms > t);
  if (i < 0) return structuredClone(frames[frames.length - 1]);
  if (i === 0) return structuredClone(frames[0]);
  const left = frames[i - 1], right = frames[i];
  const ratio = (t - left.offset_ms) / (right.offset_ms - left.offset_ms);
  const mix = (a: number, b: number) => a + (b - a) * ratio;
  const result = structuredClone(left);
  result.offset_ms = t;
  for (const axis of ['x', 'y', 'z'] as const) result.arm_pose[axis] = mix(left.arm_pose[axis], right.arm_pose[axis]);
  for (const key of ['object_x', 'object_y', 'object_z', 'pickup_x', 'pickup_y', 'pickup_z', 'dropoff_x', 'dropoff_y', 'dropoff_z'] as const) {
    result.target_state[key] = mix(left.target_state[key] ?? 0, right.target_state[key] ?? 0);
  }
  return result;
}

/**
 * Panda geometry is recorded at discrete simulation samples. Selecting the
 * last sample at or before the cursor preserves one authoritative pose for
 * every geom and keeps labels/contacts/geometry on the same backend frame.
 */
export function sampleRobotFrame(frames: RobotFramePayload[], timeMs: number): RobotFramePayload | null {
  if (!frames.length) return null;
  const first = frames[0];
  if (timeMs < first.sim_time_ms) return structuredClone(first);
  let selected = first;
  for (const frame of frames) {
    if (frame.sim_time_ms > timeMs) break;
    selected = frame;
  }
  return structuredClone(selected);
}

// MuJoCo Z 向上，Three.js Y 向上；保持右手系，不偏移真实路径。
export function physicalWorld(x: number, y: number, z: number): [number, number, number] { return [x, z, -y]; }
export function physicalProjection(x: number, z: number): [number, number] { return [400 + x * 440, 310 - z * 440]; }
