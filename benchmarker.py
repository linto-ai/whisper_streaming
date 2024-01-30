import os
import argparse
from tqdm import tqdm

LANGUAGE = "fr"
MIN_CHUNK_SIZE = 2

CONFIG_FILE = "benchmark_configs.txt"

def get_possible_params_faster_whisper(device):
    if device == "cpu":
        return {'precisions': ["int8", "float32"],
                'vads': ["", "vad"],
                'methods': ["greedy", "beam-search"],
                }
    return {'precisions': ["int8", "float16", "float32"],
                'vads': ["", "vad"],
                'methods': ["greedy", "beam-search"],
                }


def get_possible_params_whisper_timestamped(device):
    if device == "cpu":
        return {'precisions': ["float32"],
                'vads': ["", "vad", "vad auditok"],
                'methods': ["greedy", "beam-search"],
                }
    return {'precisions': ["float16", "float32"],
                'vads': ["", "vad", "vad auditok"],
                'methods': ["greedy", "beam-search"],
            }

def is_params_valid_faster(device, precision, vad, method, subfolders=False):
    if device == "cpu":
        if precision=="float32" and method=="beam-search":
            return False
        elif precision=="float16":
            return False
        return True
    else:
        if precision=="float16" and (method=="beam-search" or vad):
            return False
        elif precision=="float32" and method=="beam-search":
            return False
        if subfolders:
            if (precision=="float16" or vad!="vad") and not (method=="beam-search" and precision=="int8" and vad==""):
                return False
    return True

def is_params_valid_whisper_timestamped(device, precision, vad, method, subfolders=False):
    if device == "cpu":
        if precision=="float16":
            return False
        return True
    else:
        if precision=="float16" and (method=="beam-search" or vad):
            return False
        if subfolders:
            if (precision=="float16" or vad!="vad") and not (method=="beam-search" and precision=="float32" and vad==""):
                return False
    return True

def generate_test(device, file="benchmark_configs.txt", subfolders=False):
    with open(file, "w") as f:
        backends = ["faster-whisper", "whisper-timestamped-openai", "whisper-timestamped-transformers"]
        for backend in backends:
            if backend == "faster-whisper":
                possible_params = get_possible_params_faster_whisper(device)
            else:
                possible_params = get_possible_params_whisper_timestamped(device)
            for precision in possible_params['precisions']:
                for vad in possible_params['vads']:
                    for method in possible_params['methods']:
                        if vad == "vad auditok":
                            if method == "beam-search":
                                continue
                        test_id = f'{precision}_{method}'
                        if vad!="":
                            test_id += f'_{vad.replace(" ", "-")}'
                        if (backend == "faster-whisper" and is_params_valid_faster(device,precision, vad, method, subfolders)) or (backend.startswith("whisper-timestamped") and is_params_valid_whisper_timestamped(device, precision, vad, method, subfolders)):
                            f.write(f'{backend}_{test_id}\n')
                            if device=="cuda" and ((backend.startswith("whisper_timestamped") and precision=="float32") or (backend=="faster-whisper" and precision=="int8")) and method=="greedy" and vad=="":
                                f.write(f'{backend}_{test_id}_previous-text\n')
                            if not subfolders:
                                if method == "greedy" and ((precision == "int8" and backend == "faster-whisper") or (backend.startswith("whisper-timestamped") and precision=="float32")):
                                    f.write(f'{backend}_{test_id}_silence\n')
                            else:
                                if method == "beam-search" and ((precision == "int8" and backend == "faster-whisper") or (backend.startswith("whisper-timestamped") and precision=="float32")) and vad=="vad":
                                    f.write(f'{backend}_{test_id}_offline\n')
                                    f.write(f'{backend}_{test_id}_medium\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--hardware', type=str, default='koios')
    parser.add_argument('--device', type=str, default='cuda')
    parser.add_argument('--data', type=str, default='../data-fr/normal')
    parser.add_argument('--data_silence', type=str, default='../data-fr/silence')
    parser.add_argument('--subfolders', type=bool, default=False)
    parser.add_argument('--model_size', type=str, default='large-v3')
    args = parser.parse_args()
    hardware = args.hardware
    device = args.device
    data = args.data
    model_size = args.model_size
    data_silence = args.data_silence
    subfolder = args.subfolders



    if hardware == "koios":
        os.system('export CUDA_DEVICE_ORDER=PCI_BUS_ID')
        os.system('export CUDA_VISIBLE_DEVICES=1')
        os.system('export PYTHONPATH="${PYTHONPATH}:/home/abert/abert/speech-army-knife"')
    elif hardware == "biggerboi":
        pass
    else:
        os.system('export PYTHONPATH="${PYTHONPATH}:/mnt/c/Users/berta/Documents/Linagora/speech-army-knife"')
        os.system('export PYTHONPATH="${PYTHONPATH}:/mnt/c/Users/berta/Documents/Linagora/whisper-timestamped"')

    benchmark_folder = f'{data.split("/")[-1]}_{model_size}'
    output_path = os.path.join(benchmark_folder, hardware, device)
    os.makedirs(output_path, exist_ok=True)

    if not os.path.exists(CONFIG_FILE) or True:
        generate_test(device, CONFIG_FILE, subfolder)
    
    pbar = tqdm(total=sum(1 for line in open(CONFIG_FILE, "r") if not line.startswith("#")))
    with open(CONFIG_FILE, "r") as f:
        for line in f.readlines():
            line = line.strip()
            if not line.startswith("#"):
                params = line.split("_")
                backend = params[0]
                if backend.startswith('whisper'):
                    backend = '_'.join(backend.split("-", 1))
                sub_path = os.path.join(output_path, backend, '_'.join(params[1:]))
                os.makedirs(sub_path, exist_ok=True)
                command = ""
                if device == "cpu":
                    command = f'/usr/bin/time -o {sub_path}/ram.txt -f "Maximum RSS size: %M KB\nCPU percentage used: %P" '
                if "silence" in params:
                    command += f'python whisper_online_full_options.py {data_silence} '
                else:
                    command += f'python whisper_online_full_options.py {data} '
                command += f'--language {LANGUAGE} --model {model_size if not "medium" in params else "medium"} --min-chunk-size {MIN_CHUNK_SIZE} --task transcribe --device {device} --backend {backend} --compute_type {params[1]} --method {params[2]} --output_path {sub_path}'
                if subfolder:
                    command += f' --subfolders'
                tmp = [i for i in params if i.startswith('vad')]
                if tmp:
                    command += f' --{tmp[0].replace("-", " ")}'
                if "previous-text" in params:
                    command += f' --previous-text'
                if "offline" in params:
                    command += f' --offline'
                os.system(command)
                pbar.update(1)
