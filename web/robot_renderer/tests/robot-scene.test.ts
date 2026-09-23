import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { decodeFloat32LittleEndian, decodeUint32LittleEndian, mujocoPositionToThree, mujocoWxyzToThreeQuaternion, readRobotDebugPoses } from '../src/robot-scene';

function base64(bytes: Uint8Array): string {
  let binary = '';
  bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
  return btoa(binary);
}

describe('Panda scene 解码与坐标契约', () => {
  it('按 little-endian 解码网格顶点与索引', () => {
    const vertices = new Uint8Array(new Float32Array([1, -2, 3]).buffer);
    const indices = new Uint8Array(new Uint32Array([0, 2, 1]).buffer);
    expect([...decodeFloat32LittleEndian(base64(vertices))]).toEqual([1, -2, 3]);
    expect([...decodeUint32LittleEndian(base64(indices))]).toEqual([0, 2, 1]);
  });

  it('将 MuJoCo 世界轴映射为 Three.js Y-up，并将 wxyz 转成 xyzw', () => {
    expect(mujocoPositionToThree([.4, .2, .1]).toArray()).toEqual([.4, .1, -.2]);
    expect(mujocoWxyzToThreeQuaternion([.5, .1, .2, .3]).toArray()).toEqual([.1, .2, .3, .5]);
  });

  it('debug 只读取当前 mesh 世界状态，不从帧重新赋值', () => {
    const root = new THREE.Group();
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshBasicMaterial());
    mesh.position.set(.4, .5, -.2); root.add(mesh);
    const before = mesh.position.clone();
    const debug = readRobotDebugPoses(root, [mesh], [7]);
    expect(debug[0].id).toBe('7');
    expect(debug[0].position).toEqual([.4, .5, -.2]);
    expect(mesh.position.equals(before)).toBe(true);
    mesh.geometry.dispose(); (mesh.material as THREE.Material).dispose();
  });
});
