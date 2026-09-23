import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { type RobotFramePayload, type RobotScenePayload } from './payload';

export type RobotDebugPose = { id: string; position: [number, number, number]; quaternion: [number, number, number, number] };

export const MUJOCO_TO_THREE = new THREE.Euler(-Math.PI / 2, 0, 0);

function decodeBase64(base64: string): Uint8Array {
  const binary = typeof atob === 'function' ? atob(base64) : Buffer.from(base64, 'base64').toString('binary');
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

export function decodeFloat32LittleEndian(base64: string): Float32Array {
  const bytes = decodeBase64(base64);
  if (bytes.byteLength % 4 !== 0) throw new Error('网格顶点字节数不是 float32 的整数倍');
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const result = new Float32Array(bytes.byteLength / 4);
  for (let i = 0; i < result.length; i += 1) result[i] = view.getFloat32(i * 4, true);
  return result;
}

export function decodeUint32LittleEndian(base64: string): Uint32Array {
  const bytes = decodeBase64(base64);
  if (bytes.byteLength % 4 !== 0) throw new Error('网格索引字节数不是 uint32 的整数倍');
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const result = new Uint32Array(bytes.byteLength / 4);
  for (let i = 0; i < result.length; i += 1) result[i] = view.getUint32(i * 4, true);
  return result;
}

export function mujocoPositionToThree(position: readonly [number, number, number]): THREE.Vector3 {
  return new THREE.Vector3(position[0], position[2], -position[1]);
}

export function mujocoWxyzToThreeQuaternion(quaternion: readonly [number, number, number, number]): THREE.Quaternion {
  return new THREE.Quaternion(quaternion[1], quaternion[2], quaternion[3], quaternion[0]);
}

function color(rgba: [number, number, number, number]): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({ color: new THREE.Color(rgba[0], rgba[1], rgba[2]), transparent: rgba[3] < 1, opacity: rgba[3], roughness: .48, metalness: .08 });
}

export type RobotSceneInstance = {
  root: THREE.Group;
  geomMeshes: THREE.Object3D[];
  controls: OrbitControls;
  applyFrame(frame: RobotFramePayload): void;
  readDebugPose(frame: RobotFramePayload): RobotDebugPose[];
  dispose(): void;
};

export function readRobotDebugPoses(root: THREE.Object3D, meshes: THREE.Object3D[], ids: readonly number[]): RobotDebugPose[] {
  root.updateMatrixWorld(true);
  return meshes.map((mesh, index) => {
    const position = new THREE.Vector3(); const quaternion = new THREE.Quaternion();
    mesh.getWorldPosition(position); mesh.getWorldQuaternion(quaternion);
    return { id: String(ids[index]), position: [position.x, position.y, position.z], quaternion: [quaternion.x, quaternion.y, quaternion.z, quaternion.w] };
  });
}

export function createRobotScene(scene: THREE.Scene, camera: THREE.PerspectiveCamera, canvas: HTMLElement, data: RobotScenePayload): RobotSceneInstance {
  const root = new THREE.Group();
  root.name = 'panda-mujoco-world';
  root.rotation.copy(MUJOCO_TO_THREE);
  scene.add(root);
  const meshById = new Map<number, THREE.BufferGeometry>();
  for (const mesh of data.meshes) {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(decodeFloat32LittleEndian(mesh.vertices_b64), 3));
    geometry.setIndex(new THREE.BufferAttribute(decodeUint32LittleEndian(mesh.indices_b64), 1));
    geometry.computeVertexNormals();
    meshById.set(mesh.id, geometry);
  }
  const geomMeshes: THREE.Object3D[] = [];
  data.geoms.forEach((geom, index) => {
    let geometry: THREE.BufferGeometry;
    if (geom.type === 'mesh' && geom.mesh_id !== null && meshById.has(geom.mesh_id)) {
      geometry = meshById.get(geom.mesh_id)!.clone();
    } else if (geom.type === 'plane') {
      geometry = new THREE.PlaneGeometry(Math.max(2, geom.size[0] * 2), Math.max(2, geom.size[1] * 2));
    } else {
      geometry = new THREE.BoxGeometry(geom.size[0] * 2, geom.size[1] * 2, geom.size[2] * 2);
    }
    const object = new THREE.Mesh(geometry, color(geom.rgba));
    object.name = `panda-geom-${geom.id}`;
    object.userData.geomId = geom.id;
    object.castShadow = geom.type !== 'plane';
    object.receiveShadow = true;
    root.add(object);
    geomMeshes[index] = object;
  });
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.target.set(.45, .25, .35);

  const applyFrame = (frame: RobotFramePayload) => {
    data.geoms.forEach((geom, index) => {
      const pose = frame.geom_poses[index];
      if (!pose) return;
      geomMeshes[index].position.set(pose.position[0], pose.position[1], pose.position[2]);
      geomMeshes[index].quaternion.copy(mujocoWxyzToThreeQuaternion(pose.quaternion));
    });
  };
  const readDebugPose = (_frame: RobotFramePayload): RobotDebugPose[] => {
    // Debug 必须观察已经绘制的场景。重新应用 payload 会掩盖绘制/更新缺陷，
    // 也会使这个只读接口产生副作用。
    return readRobotDebugPoses(root, geomMeshes, data.geoms.map((geom) => geom.id));
  };
  const dispose = () => {
    controls.dispose();
    scene.remove(root);
    root.traverse((object) => {
      const mesh = object as THREE.Mesh;
      if (mesh.geometry) mesh.geometry.dispose();
      if (Array.isArray(mesh.material)) mesh.material.forEach((material) => material.dispose());
      else if (mesh.material) mesh.material.dispose();
    });
  };
  return { root, geomMeshes, controls, applyFrame, readDebugPose, dispose };
}
