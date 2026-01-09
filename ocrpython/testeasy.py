from transformers import AutoModel, AutoTokenizer
import torch

model_name = 'Dogacel/DeepSeek-OCR-Metal-MPS'

tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
tokenizer.pad_token = tokenizer.eos_token

model = AutoModel.from_pretrained(
        model_name, 
        _attn_implementation='eager',
        trust_remote_code=True,
        use_safetensors=True,
    )

device = torch.device("cpu")
dtype = torch.float16

model = model.eval().to(device).to(dtype)

prompt = "<image>\n<|grounding|>Convert the document to markdown. "
image_file = 'congvan.png'
output_path = 'results4'

res = model.infer(
    tokenizer, 
    device=device,
    dtype=dtype,
    prompt=prompt,
    image_file=image_file, 
    output_path = output_path, 
    base_size=1024, 
    image_size=640,
    crop_mode=False, 
    save_results = True, 
    test_compress = True,
)
