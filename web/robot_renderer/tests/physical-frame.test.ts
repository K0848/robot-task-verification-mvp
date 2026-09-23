import { describe, expect, it } from 'vitest';
import { samplePhysicalFrame, sampleRobotFrame, physicalWorld, physicalProjection } from '../src/physical-frame';
import { type FramePayload, type RobotFramePayload } from '../src/payload';

const frames: FramePayload[] = [
  {offset_ms:0,stage:'grasp',gripper_state:'closed',arm_pose:{x:0,y:0,z:.2},target_state:{object_label:'box',target_slot:'target',object_x:0,object_y:0,object_z:0,pickup_x:0,pickup_y:0,dropoff_x:.28,dropoff_y:0,held:true,placed:false}},
  {offset_ms:100,stage:'release',gripper_state:'open',arm_pose:{x:1,y:2,z:.4},target_state:{object_label:'box',target_slot:'target',object_x:1,object_y:2,object_z:.1,pickup_x:0,pickup_y:0,dropoff_x:.28,dropoff_y:0,held:false,placed:true}}
];
describe('物理轨迹独立采样',()=>{
  it('抓取/释放过渡不发生 snap 或提前切换状态',()=>{
    const f=samplePhysicalFrame(frames,75)!;
    expect(f.target_state.object_x).toBe(.75);
    expect(f.target_state.object_y).toBe(1.5);
    expect(f.target_state.object_z).toBeCloseTo(.075);
    expect(f.stage).toBe('grasp');expect(f.target_state.held).toBe(true);
    expect(samplePhysicalFrame(frames,100)!.stage).toBe('release');
  });
  it('释放后的物体也按记录移动，不能保持旧位置',()=>{
    const unheld=structuredClone(frames); unheld[0].target_state.held=false;
    expect(samplePhysicalFrame(unheld,50)!.target_state.object_x).toBe(.5);
  });
  it('边界钳制且不修改源数据',()=>{
    expect(samplePhysicalFrame([],0)).toBeNull();
    expect(samplePhysicalFrame(frames,-1)!.offset_ms).toBe(0);
    expect(samplePhysicalFrame(frames,999)!.offset_ms).toBe(100);
    samplePhysicalFrame(frames,25)!.arm_pose.x=99;expect(frames[0].arm_pose.x).toBe(0);
  });
  it('3D 和 SVG 均投影真实米制坐标',()=>{
    expect(physicalWorld(.28,.1,.035)).toEqual([.28,.035,-.1]);
    const [x,z]=physicalProjection(-.28,.035);expect(x).toBeCloseTo(276.8);expect(z).toBeCloseTo(294.6);
  });
  it('Panda 只选择不晚于 cursor 的原始记录帧，不插值', () => {
    const panda: RobotFramePayload[] = [
      { sim_time_ms: 0, stage: 'approach', geom_poses: [{ position: [0, 0, 0], quaternion: [1, 0, 0, 0] }], gripper_width_m: .08 },
      { sim_time_ms: 20, stage: 'grasp', geom_poses: [{ position: [1, 2, 3], quaternion: [1, 0, 0, 0] }], gripper_width_m: .04 }
    ];
    expect(sampleRobotFrame(panda, 19)).toEqual(panda[0]);
    expect(sampleRobotFrame(panda, 20)).toEqual(panda[1]);
    expect(sampleRobotFrame(panda, -1)).toEqual(panda[0]);
  });
});
