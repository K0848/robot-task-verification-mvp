import { describe, expect, it } from 'vitest';

import {
  computeAnimationTime,
  resolveObjectKind,
  sampleFrame,
  type RendererPayload
} from '../src/payload';

const payload: RendererPayload = {
  view_mode: 'preview',
  title: '??',
  status: 'running',
  success: true,
  scenario_label: '????',
  resolved_scenario: 'success',
  progress: 0,
  current_stage: '????',
  highlight_mode: 'overview',
  camera_preset: 'sim-isometric',
  dynamic_profile: {
    pace: 'fast',
    pace_multiplier: 1.35,
    focus: 'grasp',
    matched_keywords: ['???', '????']
  },
  scene: {
    object_label: '????',
    source_bin: 'A1',
    target_slot: 'Tray-01',
    surface: '???'
  },
  animation: {
    mode: 'loop',
    duration_ms: 1000,
    initial_elapsed_ms: 0
  },
  frames: [
    {
      offset_ms: 0,
      stage: '????',
      gripper_state: 'open',
      arm_pose: { x: 10, y: 20, z: 5 },
      target_state: {
        object_label: '????',
        target_slot: 'Tray-01',
        object_x: 12,
        object_y: 15,
        pickup_x: 12,
        pickup_y: 15,
        dropoff_x: 70,
        dropoff_y: 40,
        held: false,
        placed: false
      }
    },
    {
      offset_ms: 1000,
      stage: '????',
      gripper_state: 'closed',
      arm_pose: { x: 20, y: 40, z: 10 },
      target_state: {
        object_label: '????',
        target_slot: 'Tray-01',
        object_x: 20,
        object_y: 40,
        pickup_x: 12,
        pickup_y: 15,
        dropoff_x: 70,
        dropoff_y: 40,
        held: true,
        placed: false
      }
    }
  ],
  events: []
};

const releaseFrames = [
  {
    offset_ms: 0,
    stage: '????',
    gripper_state: 'closed',
    arm_pose: { x: 20, y: 40, z: 10 },
    target_state: {
      object_label: '????',
      target_slot: 'Tray-01',
      object_x: 20,
      object_y: 40,
      pickup_x: 12,
      pickup_y: 15,
      dropoff_x: 70,
      dropoff_y: 40,
      held: true,
      placed: false
    }
  },
  {
    offset_ms: 1000,
    stage: '????',
    gripper_state: 'open',
    arm_pose: { x: 70, y: 40, z: 10 },
    target_state: {
      object_label: '????',
      target_slot: 'Tray-01',
      object_x: 70,
      object_y: 40,
      pickup_x: 12,
      pickup_y: 15,
      dropoff_x: 70,
      dropoff_y: 40,
      held: false,
      placed: true
    }
  }
];

describe('payload helpers', () => {
  it('computes loop animation time with pace multiplier', () => {
    expect(Math.round(computeAnimationTime(payload, 600))).toBe(810);
  });

  it('samples frames with interpolation', () => {
    const frame = sampleFrame(payload.frames, 500);
    expect(frame?.arm_pose.x).toBeGreaterThan(10);
    expect(frame?.arm_pose.x).toBeLessThan(20);
  });

  it('keeps the object at pickup before grasp is established', () => {
    const early = sampleFrame(payload.frames, 250);
    const late = sampleFrame(payload.frames, 750);

    expect(early?.target_state.object_x).toBe(12);
    expect(early?.target_state.object_y).toBe(15);
    expect(late?.target_state.object_x).toBeGreaterThan(12);
    expect(late?.target_state.object_y).toBeGreaterThan(15);
  });

  it('keeps the object with the gripper before release is established', () => {
    const early = sampleFrame(releaseFrames, 250);
    const late = sampleFrame(releaseFrames, 750);

    expect(early?.target_state.object_x).toBe(20);
    expect(early?.target_state.object_y).toBe(40);
    expect(late?.target_state.object_x).toBeGreaterThan(20);
  });

  it('maps object labels to programmatic geometry kinds', () => {
    expect(resolveObjectKind('\u6cd5\u5170')).toBe('ring');
    expect(resolveObjectKind('\u76d6')).toBe('disc');
    expect(resolveObjectKind('\u7acb\u65b9\u4f53')).toBe('box');
  });
});
