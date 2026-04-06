export type DynamicProfile = {
  pace: string;
  pace_multiplier: number;
  focus: string;
  matched_keywords: string[];
};

export type ArmPose = {
  x: number;
  y: number;
  z: number;
};

export type TargetState = {
  object_label: string;
  target_slot: string;
  object_x: number;
  object_y: number;
  pickup_x: number;
  pickup_y: number;
  dropoff_x: number;
  dropoff_y: number;
  held: boolean;
  placed: boolean;
};

export type FramePayload = {
  offset_ms: number;
  stage: string;
  arm_pose: ArmPose;
  gripper_state: string;
  target_state: TargetState;
};

export type EventPayload = {
  offset_ms: number;
  stage: string;
  level: string;
  message: string;
};

export type RendererPayload = {
  view_mode: string;
  title: string;
  compare_label?: string | null;
  status: string;
  success: boolean;
  scenario_label: string;
  resolved_scenario: string;
  progress: number;
  current_stage: string;
  highlight_mode: string;
  camera_preset: string;
  dynamic_profile: DynamicProfile;
  scene: {
    object_label: string;
    source_bin: string;
    target_slot: string;
    surface: string;
  };
  animation: {
    mode: 'loop' | 'live' | 'static';
    duration_ms: number;
    initial_elapsed_ms: number;
  };
  frames: FramePayload[];
  events: EventPayload[];
};

const DEFAULT_PROFILE: DynamicProfile = {
  pace: 'default',
  pace_multiplier: 1.0,
  focus: 'overview',
  matched_keywords: []
};

export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

export function normalizeDynamicProfile(profile?: Partial<DynamicProfile> | null): DynamicProfile {
  if (!profile) {
    return { ...DEFAULT_PROFILE };
  }
  return {
    pace: profile.pace ?? DEFAULT_PROFILE.pace,
    pace_multiplier:
      typeof profile.pace_multiplier === 'number' && profile.pace_multiplier > 0
        ? profile.pace_multiplier
        : DEFAULT_PROFILE.pace_multiplier,
    focus: profile.focus ?? DEFAULT_PROFILE.focus,
    matched_keywords: Array.isArray(profile.matched_keywords)
      ? profile.matched_keywords.map((item) => String(item))
      : []
  };
}

export function resolveObjectKind(label: string): 'ring' | 'box' | 'disc' {
  if (label.includes('套环') || label.includes('法兰')) {
    return 'ring';
  }
  if (label.includes('盖')) {
    return 'disc';
  }
  return 'box';
}

function easeInOutCubic(value: number): number {
  return value < 0.5 ? 4 * value * value * value : 1 - Math.pow(-2 * value + 2, 3) / 2;
}

function easeOutCubic(value: number): number {
  return 1 - Math.pow(1 - value, 3);
}

function resolveStageRatio(stage: string, ratio: number): number {
  if (/抓取|放置|校验/.test(stage)) {
    return easeInOutCubic(ratio);
  }
  if (/接近|转运|回撤|抬升/.test(stage)) {
    return easeOutCubic(ratio);
  }
  return easeInOutCubic(ratio);
}

export function computeAnimationTime(payload: RendererPayload, mountElapsedMs: number): number {
  const duration = Math.max(payload.animation?.duration_ms ?? 0, 0);
  if (!duration) {
    return 0;
  }
  const profile = normalizeDynamicProfile(payload.dynamic_profile);
  const initial = clamp(payload.animation?.initial_elapsed_ms ?? 0, 0, duration);
  if (payload.animation.mode === 'static') {
    return initial;
  }
  const scaled = initial + mountElapsedMs * profile.pace_multiplier;
  if (payload.animation.mode === 'loop') {
    return scaled % duration;
  }
  return clamp(scaled, 0, duration);
}

function findFrameIndex(frames: FramePayload[], timeMs: number): number {
  const index = frames.findIndex((frame) => frame.offset_ms >= timeMs);
  return index === -1 ? frames.length - 1 : index;
}

function blendNumber(left: number, right: number, ratio: number): number {
  return left + (right - left) * ratio;
}

function blendObjectPosition(
  left: FramePayload,
  right: FramePayload,
  eased: number,
  axis: 'object_x' | 'object_y'
): number {
  const leftValue = left.target_state[axis];
  const rightValue = right.target_state[axis];
  const leftHeld = left.target_state.held;
  const rightHeld = right.target_state.held;

  if (leftHeld && rightHeld) {
    return blendNumber(leftValue, rightValue, eased);
  }
  if (!leftHeld && !rightHeld) {
    return leftValue;
  }

  // Grab transition (false → true): object stays at original position until
  // the gripper closes (eased >= 0.5), then snaps to the gripper instantly.
  if (!leftHeld && rightHeld) {
    return eased >= 0.5 ? rightValue : leftValue;
  }

  // Release transition (true → false): snap to the drop position immediately.
  return eased >= 0.5 ? rightValue : leftValue;
}

export function sampleFrame(frames: FramePayload[], timeMs: number): FramePayload | null {
  if (!frames.length) {
    return null;
  }
  const clamped = clamp(timeMs, frames[0].offset_ms, frames[frames.length - 1].offset_ms);
  if (clamped <= frames[0].offset_ms) {
    return structuredClone(frames[0]);
  }
  if (clamped >= frames[frames.length - 1].offset_ms) {
    return structuredClone(frames[frames.length - 1]);
  }

  const rightIndex = findFrameIndex(frames, clamped);
  const left = frames[Math.max(0, rightIndex - 1)];
  const right = frames[rightIndex];
  const span = Math.max(right.offset_ms - left.offset_ms, 1);
  const eased = resolveStageRatio(right.stage, (clamped - left.offset_ms) / span);

  return {
    offset_ms: Math.round(clamped),
    stage: eased >= 0.58 ? right.stage : left.stage,
    gripper_state: eased >= 0.5 ? right.gripper_state : left.gripper_state,
    arm_pose: {
      x: blendNumber(left.arm_pose.x, right.arm_pose.x, eased),
      y: blendNumber(left.arm_pose.y, right.arm_pose.y, eased),
      z: blendNumber(left.arm_pose.z, right.arm_pose.z, eased)
    },
    target_state: {
      object_label: eased >= 0.5 ? right.target_state.object_label : left.target_state.object_label,
      target_slot: eased >= 0.5 ? right.target_state.target_slot : left.target_state.target_slot,
      object_x: blendObjectPosition(left, right, eased, 'object_x'),
      object_y: blendObjectPosition(left, right, eased, 'object_y'),
      pickup_x: blendNumber(left.target_state.pickup_x, right.target_state.pickup_x, eased),
      pickup_y: blendNumber(left.target_state.pickup_y, right.target_state.pickup_y, eased),
      dropoff_x: blendNumber(left.target_state.dropoff_x, right.target_state.dropoff_x, eased),
      dropoff_y: blendNumber(left.target_state.dropoff_y, right.target_state.dropoff_y, eased),
      held: eased >= 0.5 ? right.target_state.held : left.target_state.held,
      placed: eased >= 0.5 ? right.target_state.placed : left.target_state.placed
    }
  };
}

export function findFailureOffset(events: EventPayload[]): number | null {
  const item = events.find((event) => event.level === 'error' || /失败|滑落/.test(event.stage));
  return item ? item.offset_ms : null;
}
