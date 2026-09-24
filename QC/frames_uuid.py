import os, subprocess
d = r'./flow_v_uuid'
os.makedirs(d + '/frames', exist_ok=True)
for f in os.listdir(d):
    if f.endswith('.mp4'):
        uuid = f[:-4]
        out = f'{d}/frames/{uuid}.jpg'
        if not os.path.exists(out):
            # 用 -ss 0 直接取第0帧最稳
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-ss', '0.1', '-i', f'{d}/{f}',
                            '-frames:v', '1', out])
print('done:', len([x for x in os.listdir(d + '/frames') if x.endswith('.jpg')]))
