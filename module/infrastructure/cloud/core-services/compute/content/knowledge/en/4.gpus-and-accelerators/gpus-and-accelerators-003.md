# VRAM, Memory Bandwidth, and Model Size Limits

## Context: A Powerful GPU Still Cannot Run the Model

When deploying machine learning models or large language models (LLMs), two GPU specifications typically determine the real-world experience: **GPU memory capacity (VRAM)** and **memory bandwidth**. Compute core counts, Tensor Core capability, and FLOPS throughput matter, but they cannot compensate for a model that does not fit in memory or data that cannot be moved to the processors fast enough.

VRAM is where the GPU stores model weights, intermediate tensors, input data, buffers, and compute state. Memory bandwidth indicates how fast data can be read from or written to VRAM by the GPU. Two GPUs with similar theoretical compute counts can still perform very differently if one has less VRAM or lower bandwidth.

In the **CLOUD_CORE_SERVICES_COMPUTE** module, understanding these limits helps you choose appropriate GPUs and accelerators, estimate runnable model sizes, decide on precision or quantization, arrange multi-GPU setups, and optimize both performance and cost in the cloud.

## 1. What Is VRAM and What Is It Used For?

VRAM (Video Random Access Memory) is high-bandwidth local memory attached to the GPU. On server GPUs, VRAM is typically specialized memory such as GDDR or HBM. The GPU uses this memory space to keep data that needs fast access during kernel execution.

An AI workload can use VRAM for multiple components:

- **Model weights:** the learned parameters of the model, usually the largest memory consumer during large model inference.
- **Activations:** intermediate layer outputs during the forward pass; during training, many activations must be retained to compute gradients.
- **Gradients:** derivatives used to update weights during training.
- **Optimizer states:** such as Adam moments, which often consume substantial additional memory per parameter.
- **KV cache:** memory storing keys and values of prior tokens to avoid recomputing full attention at every token generation step in an LLM.
- **Inputs, outputs, and batches:** tokens, images, embeddings, output tensors, and data for multiple samples processed concurrently.
- **Workspaces and runtime memory:** scratch space for kernels, acceleration libraries, CUDA contexts, graphs, allocators, and execution structures.

Therefore, you cannot take the checkpoint file size and conclude the model will definitely run in that amount of VRAM. Checkpoints usually reflect only the weights (or part of them); loading and executing the model incurs additional memory allocations.

### 1.1. VRAM vs. System RAM

System RAM is accessed directly by the CPU; VRAM is accessed by the GPU over its own dedicated bus. GPUs typically have substantially higher VRAM bandwidth than standard system RAM bandwidth, though VRAM capacity is usually smaller than total host RAM.

When VRAM is insufficient, some frameworks or architectures can offload part of the data to system RAM or distribute data to other GPUs. These approaches allow larger workloads to run, but usually increase latency and traffic across PCIe, NVLink, or interconnect fabrics. System RAM should not be treated as equivalent in speed to VRAM.

### 1.2. GB and GiB

Memory specifications may be reported in decimal or binary units:

| Unit | Calculation | Approximate Value |
|---|---|---:|
| 1 GB | `10^9` bytes | 0.931 GiB |
| 1 GiB | `2^30` bytes | 1.074 GB |
| 1 TB/s | `10^12` bytes per second | 0.91 TiB/s |

Manufacturers often advertise VRAM in GB, whereas tools or frameworks display GiB. Thus, 24 GB on a spec sheet may show up as roughly 22.4 GiB in software. The system also reserves a portion of memory for drivers and runtimes, so usable application capacity can be lower than the nominal figure.

## 2. Estimating Memory for Model Weights

Weight size depends on parameter count and the number of bits used to store each parameter. If a model has `P` parameters and each parameter uses `b` bits, theoretical memory for weights is:

\[
M_{weights} = \frac{P \times b}{8}\quad\text{(bytes)}
\]

For example, a 7-billion-parameter (7B) model using FP16 or BF16 typically takes 2 bytes per parameter:

\[
7\times10^9 \times 2 = 14\times10^9\text{ bytes} \approx 13.04\text{ GiB}
\]

This is an estimate for raw weights only. A 16 GiB GPU may not suffice for running inference on this model with substantial batch sizes or context lengths, because you also need room for KV cache, activations, workspaces, and runtime memory.

### 2.1. Precision and Quantization

Precision describes how numbers are represented in computation or storage. Common formats include:

| Format | Common Bit Width | Theoretical Weight Memory per Parameter | Notes |
|---|---:|---:|---|
| FP32 | 32 bits | 4 bytes | High precision, memory-intensive |
| FP16 | 16 bits | 2 bytes | Common in inference and mixed-precision training |
| BF16 | 16 bits | 2 bytes | Wider exponent range than FP16, often useful in training |
| INT8 | 8 bits | 1 byte | Requires scales/zero points or metadata depending on method |
| INT4 | 4 bits | 0.5 bytes | Sharply reduces footprint; quality depends on model and quantization method |

**Quantization** converts weights or certain operations to fewer bits. For instance, FP16 weights for a 7B model have a theoretical size of about 13.04 GiB; storing 4-bit weights reduces the theoretical payload to about 3.26 GiB.

In real deployments, memory does not shrink by an exact 4/16 ratio because of scales, zero points, quantization groups, unquantized tensors, padding, and runtime structures. Some kernels also dequantize data during computation. Consequently, inspect the checkpoint size and measure VRAM after loading the model with the exact framework, format, and kernels you intend to use.

Quantization reduces memory and sometimes improves speed by reducing the amount of data read. However, output quality may change; performance also depends on whether the GPU supports the corresponding operations. Lower-bit formats are not automatically faster if the runtime must convert data frequently or kernels are unoptimized.

### 2.2. Weight Estimate Examples by Model Size

The following table accounts for raw weights only, excluding auxiliary memory:

| Parameters | FP32 (4 bytes) | FP16/BF16 (2 bytes) | INT8 (1 byte) | INT4 (0.5 bytes) |
|---:|---:|---:|---:|---:|
| 7B | ~26.1 GiB | ~13.0 GiB | ~6.5 GiB | ~3.3 GiB |
| 13B | ~48.4 GiB | ~24.2 GiB | ~12.1 GiB | ~6.1 GiB |
| 34B | ~126.7 GiB | ~63.3 GiB | ~31.7 GiB | ~15.8 GiB |
| 70B | ~260.8 GiB | ~130.4 GiB | ~65.2 GiB | ~32.6 GiB |

Values are in GiB and assume each parameter takes the exact byte count shown in the header. For INT4, 0.5 bytes per parameter is a theoretical minimum; actual checkpoints can be larger.

## 3. Memory Beyond Weights: Activations, KV Cache, and Workspaces

### 3.1. Activations and Batch Size

Activations are intermediate tensors produced as the model processes data. Activation size depends on architecture, layer count, hidden state size, sequence length, batch size, precision, and kernel implementation.

A larger batch size processes more samples simultaneously, typically improving GPU utilization and amortizing weight-read costs. However, activations and intermediate tensors also grow with batch size. If the batch is too large, a workload can run out of VRAM even when weights fit comfortably in memory.

During training, activations are often a major component because information must be saved for the backward pass. Activation checkpointing can reduce VRAM by recomputing certain activations on demand, trading extra compute for lower memory. During inference, frameworks can release many intermediate tensors after each step, though workspaces and memory for the active batch are still required.

### 3.2. KV Cache in Token-Generating Models

Autoregressive LLMs generate one token at a time. To avoid recomputing keys and values for all previous tokens at each step, the runtime typically stores them in a KV cache. The cache grows with context length, batch size or active sequence count, number of layers, and number of KV heads.

A common estimation formula for the KV cache is:

\[
M_{KV}=2\times L\times H_{KV}\times D_H\times T\times B\times S
\]

Where:

- `L`: number of model layers.
- `H_KV`: number of key/value heads per layer.
- `D_H`: dimension of each head.
- `T`: number of tokens retained in the cache (typically prompt plus generated tokens).
- `B`: number of sequences served concurrently, according to how the runtime batches them.
- `S`: bytes per cache element, e.g., 2 bytes for FP16/BF16.
- The factor of 2 accounts for both key and value.

For example, a model with 32 layers, 8 KV heads, head dimension 128, FP16 cache, one sequence, and 4,096 tokens:

\[
2\times32\times8\times128\times4096\times1\times2
= 536{,}870{,}912\text{ bytes}=512\text{ MiB}
\]

If serving 8 sequences with the same configuration, the KV cache is approximately 4 GiB. Doubling the context length nearly doubles cache consumption if other factors stay constant. Models using Grouped Query Attention (GQA) have fewer KV heads than attention heads, reducing cache size compared to Multi-Head Attention with the same hidden size.

Actual consumption may differ due to cache paging, block allocation, sliding-window attention, cache quantization, prefix sharing, or how the runtime manages sequences. Formulas help create an initial budget; runtime measurements remain the final authority.

### 3.3. Workspaces, Fragmentation, and Runtime Overhead

Frameworks can allocate temporary regions for cuBLAS, cuDNN, attention kernels, graph capture, and other operations. Some allocators hold onto allocated VRAM for reuse, causing "reserved" figures to exceed currently active tensors. Distinguish between memory actively used by tensors and memory reserved from the GPU by the framework.

If the theoretical total sits right at nominal VRAM capacity, even a small allocation or a larger-than-expected workspace can trigger an out-of-memory error. Leave headroom for the runtime, batch variations, context growth, and model loading.

## 4. What Is GPU Memory Bandwidth?

Memory bandwidth is the volume of data that can be transferred between the GPU and VRAM per unit of time, typically stated in GB/s or TB/s. Bandwidth depends on memory type, transfer rate, bus width, and memory controller design.

A general formula for peak bandwidth is:

\[
Bandwidth = \frac{Transfer\ rate\times Bus\ width}{8}
\]

When transfer rate is measured in bits per second and bus width in bits, divide by 8 to convert to bytes per second. Published manufacturer specifications usually reflect theoretical peak bandwidth. Real-world applications typically achieve less due to access patterns, kernels, concurrency levels, caches, overhead, and workload characteristics.

VRAM capacity and bandwidth solve two different problems:

- **Capacity:** Is there enough room to hold weights, KV cache, and required tensors?
- **Bandwidth:** Can the GPU read/write that data fast enough to keep compute units fed?

A GPU with large VRAM but low bandwidth may run the model yet generate tokens slowly. A GPU with very high bandwidth but too little VRAM may fail to load the model or required context at all.

## 5. Why Does Bandwidth Affect Inference Speed?

### 5.1. Memory-Bound vs. Compute-Bound

A workload is **memory-bound** when its speed is primarily limited by moving data from memory; it is **compute-bound** when speed is primarily limited by arithmetic execution capacity.

In LLM inference, two phases typically exhibit different behaviors:

- **Prefill:** the model processes the input prompt. Many tokens can be processed together, leveraging parallelism better and often trending compute-bound in many configurations.
- **Decode:** the model generates subsequent tokens one by one. At small batch sizes, each step generally has to read most of the weights to compute a single new token, making it prone to being memory-bandwidth-bound.

This is a general trend, not an absolute rule. Batch size, model size, context length, attention kernels, quantization, and hardware can shift the bottleneck.

### 5.2. Arithmetic Intensity and the Roofline Model

Arithmetic intensity is the number of operations performed per byte of data transferred from memory. Workloads with low arithmetic intensity are easily limited by bandwidth; workloads with high intensity can exploit higher compute throughput.

The Roofline model expresses an approximate performance ceiling:

\[
Performance\leq\min(Peak\ FLOPS,\ Bandwidth\times Arithmetic\ Intensity)
\]

If bandwidth multiplied by arithmetic intensity is lower than peak FLOPS, increasing theoretical GPU compute may yield little speedup. In that case, improving memory access patterns, batching, or reducing the bytes read can be more effective.

### 5.3. Estimating Decode Speed Limits

For small-batch LLM inference, a very rough estimate is that each new token requires reading most of the weights once. An upper bound imposed by bandwidth can be conceptualized as:

\[
Tokens/s\approx\frac{Effective\ memory\ bandwidth}{Bytes\ read\ per\ token}
\]

For example, if a model has roughly 14 GB of weights and the GPU achieves 1 TB/s of effective bandwidth, simple division yields around 71 tokens/s. This is only an idealized ceiling to illustrate the impact of bandwidth; real systems also read the KV cache, perform math, synchronize, run sampling, and incur runtime overhead. Effective bandwidth may also fall below peak specs.

Batching can improve weight-reading efficiency: a single read of the weights serves multiple sequences in the same batch, reducing weight bytes read per output token. On the flip side, larger batches consume more KV cache and activations, increasing batch wait latency or VRAM pressure.

## 6. What Limits Runnable Model Size?

No single parameter count determines whether a model can run. Limits depend on usage mode and deployment configuration.

### 6.1. Inference and Training Have Different Memory Budgets

| Component | Inference | Full Training |
|---|---|---|
| Weights | Yes | Yes |
| Activations | Yes, usually freed earlier | Yes, must be retained or recomputed for backward pass |
| KV cache | Typically present for autoregressive LLMs | Not a standard decode cache; other structures may exist depending on task |
| Gradients | No | Yes |
| Optimizer states | No | Yes, e.g., Adam moments |
| Temporary/runtime memory | Yes | Yes, usually larger due to forward/backward passes and optimizer |

Because training needs gradients, optimizer states, and activations, it typically requires substantially more VRAM than inference for the same model. A rough estimate for full fine-tuning with Adam can reach roughly 12–20 bytes or more per parameter, depending on precision, master weights, optimizer, sharding, and implementation—excluding activations and workspaces. Do not use this figure in place of measurements on the actual framework.

### 6.2. Context Length and Concurrency

For LLMs, increasing context length expands the KV cache. Increasing concurrent users or sequences also increases total cache consumption. Consequently, a GPU may fit the weights yet only serve a few concurrent requests, or only support a shorter context than desired.

For example, an inference server capable of running one 8K-token sequence may not be able to run 16 concurrent 8K-token sequences. Budget KV cache according to batch/concurrency alongside workspaces and headroom.

### 6.3. Model Size and Model Splitting Strategies

If weights and auxiliary memory do not fit on a single GPU, consider:

- **Quantization:** reducing bits used for weights or cache, balanced against output quality and kernel support.
- **Tensor parallelism:** splitting tensors or layer computations across multiple GPUs, typically requiring fast inter-GPU communication.
- **Pipeline parallelism:** partitioning layers into stages placed on different GPUs.
- **CPU offload:** keeping part of the weights or states in system RAM and transferring on demand; saves VRAM but can be slow due to PCIe or other interconnect transfers.
- **Smaller context/batch:** reducing KV cache and activations at the cost of shorter input limits or lower throughput.
- **Smaller model or more efficient architecture:** selecting parameter counts, KV head counts, or configurations suited to the deployment budget.

Multiple GPUs do not automatically form a single unified pool of VRAM usable like one large GPU. The framework must support model parallelism, the runtime must manage shards, and data must traverse appropriate GPU interconnects. When GPUs communicate heavily, interconnect bandwidth and latency such as NVLink or PCIe can become a new bottleneck.

## 7. Example VRAM Budget for an LLM Service

Suppose you need to serve a 7B model with FP16 weights. An initial budget can look like this:

| Line Item | Estimate |
|---|---|
| FP16 Weights | ~13.0 GiB |
| KV cache for 1 sequence, 4K tokens (per 32-layer/8-KV-head example) | ~0.5 GiB |
| Activations, workspaces, runtime, and buffers | Depends on framework/kernels; must be measured |
| Operational headroom | Reserved for batch, context, and allocation fluctuations |

If the GPU has 16 GiB VRAM, weights and KV cache alone consume roughly 13.5 GiB before accounting for the rest. This configuration may sit too close to the limit. A 24 GiB GPU provides extra room for runtime overhead and concurrency, though actual serving capacity must still be benchmarked.

If weights are converted to INT4, the theoretical weight payload drops to roughly 3.3 GiB. The saved VRAM can support a larger KV cache, larger batches, or longer contexts. However, verify the quantization format, output quality, and kernel speed on the chosen GPU.

A sizing workflow can follow these steps:

1. Identify parameter count, architecture, layer count, KV head count, head dimension, and precision/quantization.
2. Estimate weights by multiplying parameter count by bytes per parameter.
3. Estimate KV cache based on target context length and concurrency.
4. Estimate activations and workspaces via benchmarking on the target framework/runtime.
5. Add runtime memory and headroom; do not plan right up against nominal capacity.
6. Load-test with context lengths and concurrency close to production conditions, observing peak VRAM and token rates.
7. Adjust GPU choice, quantization, batching, context limits, or model distribution based on measured results.

## 8. Measuring VRAM and Performance in Practice

### 8.1. Inspection Tools

On NVIDIA GPUs, `nvidia-smi` reports memory usage, GPU utilization, processes, and device metrics. With PyTorch, you can inspect memory usage via the following APIs:

```python
import torch

if torch.cuda.is_available():
    free_bytes, total_bytes = torch.cuda.mem_get_info()
    allocated_bytes = torch.cuda.memory_allocated()
    reserved_bytes = torch.cuda.memory_reserved()
    peak_bytes = torch.cuda.max_memory_allocated()

    print(f"Free: {free_bytes / 2**30:.2f} GiB")
    print(f"Total: {total_bytes / 2**30:.2f} GiB")
    print(f"Allocated: {allocated_bytes / 2**30:.2f} GiB")
    print(f"Reserved: {reserved_bytes / 2**30:.2f} GiB")
    print(f"Peak allocated: {peak_bytes / 2**30:.2f} GiB")
```

`memory_allocated` reflects tensor memory currently allocated by PyTorch; `memory_reserved` reflects memory held by the allocator from CUDA. `mem_get_info` returns device memory status at the moment of the call. Measure peak usage after running the actual workload, because reading immediately after loading weights misses memory spikes during prefill or large batches.

### 8.2. Metrics to Benchmark

- Peak VRAM and remaining free VRAM at maximum load.
- Model load time and startup time.
- Time to first token (TTFT), decode speed in tokens/sec, and p50/p95/p99 latency.
- Total throughput in requests or tokens/sec.
- Achievable batch size, context length, and concurrent sequence count.
- GPU utilization, memory bandwidth, or memory controller utilization if supported by tooling.
- Out-of-memory rates, throttling, and errors under increasing load.

Benchmarks should use prompts, output lengths, batches, and concurrency representative of the application. A short test at batch size 1 is insufficient to predict performance for a multi-user service.

## 9. Selecting GPUs by VRAM and Bandwidth

When selecting GPUs for cloud workloads, evaluate these factors together:

| Criterion | Questions to Answer | Impact |
|---|---|---|
| VRAM capacity | Do weights, KV cache, activations, and workspaces fit? | Determines maximum model size, context, and concurrency |
| Memory bandwidth | Can the GPU feed data fast enough for the workload? | Strongly affects memory-bound workloads and decode speed |
| Compute throughput | Is there enough FP16/BF16/FP8/INT8 or required math capacity? | Affects prefill, training, and compute-bound kernels |
| Interconnect | Do multiple GPUs communicate over PCIe or NVLink? | Affects tensor/pipeline parallelism |
| Reliability and availability | Can enough GPUs of the same type be provisioned in the target region? | Affects scalability and availability |
| Cost | What is the hourly price and performance per unit of work? | Determines total serving cost |

A high-VRAM GPU fits models that need to hold large weights or KV caches. A high-bandwidth GPU fits better when data movement is the bottleneck. For training, compute capability, interconnects, and cluster scalability are also critical. Do not decide based solely on a single TFLOPS or VRAM figure.

## 10. Common Misconceptions

**Checkpoint size equals required VRAM.** Checkpoints mostly contain weights; runtimes also need KV cache, activations, workspaces, and buffers.

**A GPU with higher TFLOPS always runs inference faster.** If the workload is memory-bound, bandwidth and memory access patterns can matter more than peak FLOPS.

**4-bit quantization always uses exactly one quarter of FP16 VRAM.** The theoretical payload has that ratio, but metadata, unquantized tensors, and runtime structures make actual footprint larger.

**Full VRAM means the model is too large.** Batch size, context length, KV cache, workspaces, or allocator behavior may also be responsible. Measure peak usage and break down each component.

**Multiple GPUs automatically merge VRAM into one unified memory pool.** Frameworks must support model parallelism; inter-GPU communication incurs overhead and can limit performance.

**One benchmark run is enough.** Performance varies with prompt length, output length, batching, concurrency, precision, and runtime. Test across multiple conditions close to production load.

## Conclusion

VRAM determines how much weight and compute state can stay close to the GPU; memory bandwidth determines how fast data moves between the GPU and VRAM. Model weight size can be estimated initially from parameter count and precision, but practical sizing must include activations, KV cache, workspaces, runtime overhead, context length, and concurrency. When selecting a GPU, match the memory budget with memory-bound/compute-bound characteristics, multi-GPU interconnect capabilities, and benchmark results on representative workloads to balance performance, serving capacity, and cost.
