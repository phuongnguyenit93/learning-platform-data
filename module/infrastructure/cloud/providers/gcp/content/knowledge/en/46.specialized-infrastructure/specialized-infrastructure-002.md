# Cloud TPU and Machine Learning Workload Requirements

In a Google Cloud architecture, Compute Engine might run a Java API, Cloud Storage might hold training data, and GKE might orchestrate containers. However, when the primary job involves large matrix multiplications, learning representations from billions of tokens, or serving generative models at high throughput, standard CPUs are no longer optimal. **Cloud TPU (Tensor Processing Unit)** is a custom-designed Google accelerator built for tensor computations and machine learning workloads capable of exploiting its hardware parallelism.

TPUs are not a drop-in replacement for every GPU or CPU. Workloads with heavy conditional branching, custom CUDA-only operators, CPU-heavy preprocessing dependencies, or FP64 numerical precision requirements may not fit well. Selecting a TPU also depends on **frameworks, the XLA compiler, tensor shapes, HBM memory, TPU slice topology, interconnects, data sources, quotas, pricing, and checkpointing capabilities**.

This lesson belongs to the **Specialized Infrastructure** chapter in the **CLOUD_PROVIDERS_GCP** module. The module progresses from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, and storage and database services; learners practice choosing services, securing resources, automating releases, and monitoring reliability and cost. Cloud TPU is a prime example of choosing infrastructure based on **workload characteristics**, rather than sizing solely by machine count.

## Learning Objectives

After this lesson, you will be able to:

- Explain the roles of TPUs, TensorCores, HBM, XLA, ICI, host VMs, and TPU slices.
- Distinguish between training, fine-tuning, batch inference, and online inference workloads.
- Identify workload characteristics that are suitable or unsuitable for TPUs.
- Compare TPU generations—v5e, v5p, Trillium (v6e), and Ironwood (TPU7x)—based on requirements.
- Estimate memory needs, batch sizes, sequence lengths, throughput, and network/data pipeline requirements.
- Choose among TPU VMs on Compute Engine, TPUs on GKE Standard/Autopilot, or an appropriate managed platform.
- Understand compatibility requirements for JAX, PyTorch/XLA, TensorFlow, libtpu, and TPU software images.
- Practice creating a TPU VM, verifying JAX detects the TPU, running a computation, and cleaning up resources.
- Understand topology and `google.com/tpu` resource requirements when running GKE workloads.
- Build checklists for quotas, placement, security, availability, monitoring, and FinOps.

## 1. What Is Cloud TPU?

A TPU is an accelerator engineered to execute common deep learning tensor operations with high efficiency. Modern TPU generations combine:

- **TensorCore:** specialized hardware for tensor/matrix operations.
- **Matrix Multiply Unit (MXU):** circuitry for highly parallel matrix multiplication.
- **High Bandwidth Memory (HBM):** high-bandwidth memory attached to TPU chips storing parameters, activations, optimizer states, and intermediate data.
- **Inter-Chip Interconnect (ICI):** high-speed links between TPU chips within a slice to exchange tensors and collective operation results.
- **Host VM:** CPU/RAM, operating system, networking, and Python/framework processes controlling the TPU.
- **XLA compiler and TPU runtime:** compiles, arranges memory layouts, optimizes graphs, and executes on the TPU.

TPUs shine when programs perform heavy matrix multiplications and can form large compute blocks with minimal shape changes. Do not think of a TPU simply as a "CPU with more cores": its compilation model, data partitioning, and memory management differ substantially.

### Flow from Model to Hardware

~~~mermaid
flowchart LR
  A[Data: Cloud Storage / dataset] --> B[Input pipeline + CPU host]
  B --> C[JAX / PyTorch-XLA / compatible framework]
  C --> D[XLA compiler + libtpu runtime]
  D --> E[TPU TensorCores + HBM]
  E <--> F[ICI: other TPU chips in slice]
  E --> G[Gradients / outputs / predictions]
  G --> H[Checkpoints / model artifacts]
  H --> I[Cloud Storage / appropriate artifact registry]
~~~

An inference system also has inputs and outputs, though it typically prioritizes latency and batching over gradients/optimizers. This diagram shows logical processing; exact behavior depends on the TPU version and framework.

## 2. TPU, CPU, and GPU: Choosing by Workload Characteristics

| Criterion | CPU | GPU | TPU |
|---|---|---|---|
| Strengths | Control flow, preprocessing, I/O, mixed tasks | Broad parallel compute, CUDA ecosystem | Dense tensor/matrix ops, XLA, and many deep learning models |
| Flexibility | High | High if supported by libraries/ops | Depends on graph, compiler, and operator support |
| Small-request latency | Often good for lightweight logic | Has launch/transfer overhead | Needs proper batching, compilation, and pipelining |
| Large-scale training | Less suited for heavy matrix math | Common | Well-suited when model/framework is compatible |
| Custom operators | Easier to write native code | CUDA/Triton depending on stack | Not every CUDA/custom op has a TPU path |
| Double-precision arithmetic | Widely supported on CPU | Varies by GPU | Not a general fit for heavy FP64 workloads |
| Operations | Standard VMs/containers | Drivers, accelerators, distributed runtime | TPU runtime, topology, quotas/capacity, XLA |

**Selection principle:** run representative benchmarks across CPU, GPU, and TPU when performance/cost matters. Do not compare purely on theoretical TFLOPS or chip-hour pricing.

### Models That Commonly Benefit from TPUs

- Transformers/LLMs with large matrix multiplications.
- Vision models, encoders, and dense recommendation models.
- Medium- to large-scale training using JAX or supported frameworks.
- Fine-tuning with stable batch sizes and sequence lengths.
- Batch inference with sufficient data volume to saturate throughput.
- Online inference when the serving stack, latency budget, and batching align.

### Workloads That May Not Fit

- Pipelines dominated by file reads, CPU image processing, or external API calls.
- Tiny models where each request performs very little compute.
- Graphs with constantly changing tensor shapes causing frequent recompilation.
- CUDA-only operators or extensions lacking equivalent TPU kernels.
- Simulations or scientific workloads requiring heavy FP64 precision.
- Tasks with heavy branching/element-wise ops and minimal matrix multiplication.
- Workloads intolerant of topology/quota/zone constraints or startup times.

Do not assume TPUs can never run operations with dynamic shapes; some frameworks support padding/bucketing or structured graph layouts. The real concern is **recompilation overhead and actual efficiency**.

## 3. TPU Generations to Know

Google Cloud supports TPU generations with distinct catalogs and provisioning models. Common names include:

| Generation | Characteristics / Focus | Example Use Cases |
|---|---|---|
| TPU v5e | Cost-balanced choice for training and inference at appropriate scale | Fine-tuning, serving, batch workloads |
| TPU v5p | Designed for large-scale training across many chips/slices | Pretraining or large distributed jobs |
| TPU Trillium (v6e) | Generation optimized for both training/inference; multiple host sizes | Standard training, fine-tuning, serving |
| TPU7x (Ironwood) | Newer generation focused on high performance and high bandwidth | Large-scale generative AI/inference, compatible training/fine-tuning |
| TPU v4 and older | Found in legacy systems or limited regions | Maintaining workloads while still supported |

Generations differ in TensorCores, HBM, interconnects, precision support, topology, software, and zonal availability. **Do not assume a checkpoint or Docker image runs identically across every generation.**

### Framework Status

JAX and PyTorch/XLA are two popular choices on TPU. TensorFlow is supported on many generations, though **per the current TPU software versions table, TensorFlow does not support Ironwood (TPU7x)**. Runtimes/plugins like TorchTPU or vLLM have their own support conditions; check the **framework × TPU version × image/libtpu** matrix before choosing a configuration.

### Example Machine Types

| TPU | Example TPU-optimized VM | Meaning |
|---|---|---|
| v5e | `ct5lp-hightpu-1t`, `ct5lp-hightpu-4t` | 1 or 4 chips/VM in supported configurations |
| v5p | `ct5p-hightpu-4t` | 4 chips/VM, can form multi-host slices |
| v6e | `ct6e-standard-1t`, `ct6e-standard-4t`, `ct6e-standard-8t` | 1, 4, or 8 chips/VM; check topology |
| TPU7x | `tpu7x-standard-4t` | 4 chips/VM; topology management differs by scenario |

A machine type only describes a valid host/slice shape; it does not guarantee quotas/capacity or optimal framework kernels. Check the current TPU machines/GKE TPU version pages before deploying.

## 4. TPU VM, Chip, Slice, and Pod Are Not the Same Unit

These concepts are frequently misconfigured:

- **TPU chip:** a physical accelerator unit with TensorCores and HBM.
- **TPU VM/host:** a Linux OS with CPU/RAM and one or more attached TPU chips.
- **TPU slice:** the set of chips/hosts allocated to a workload with a specific interconnect topology.
- **TPU Pod:** a large physically interconnected cluster of chips; a slice is a subset of a Pod.
- **Single-host slice:** all chips in the slice are attached to a single VM.
- **Multi-host slice:** multiple VMs participate in one workload over networking/ICI.

Examples on TPU v6e:

| Machine type | Example Topology | Total Slice Chips | VMs | Notes |
|---|---|---:|---:|---|
| `ct6e-standard-1t` | `1x1` | 1 | 1 | Lab and small workloads |
| `ct6e-standard-4t` | `2x2` | 4 | 1 | Single-host |
| `ct6e-standard-8t` | `2x4` | 8 | 1 | 8-chip single-host configuration |
| `ct6e-standard-4t` | `4x4` | 16 | 4 | Multi-host, 4 chips/VM |

These configurations illustrate published topologies; availability depends on product and zone. A topology like `2x2` describes the **chip** arrangement, not "2 VMs × 2 VMs". On GKE, containers request chips **per node**, not all chips of a multi-node slice inside a single pod.

### Why Does Topology Affect Performance?

In distributed training, a model may be sharded across data, model parameters, and optimizer states. When every step requires all-reduce, all-gather, or activation transfers, ICI speed and chip placement can dictate throughput.

More chips do not guarantee proportional training speedup; check:

1. Total chips in the slice and chips per host.
2. Supported topologies for the TPU generation.
3. Model/framework sharding strategy.
4. Bytes exchanged between chips/hosts.
5. Efficiency of collective operations.
6. Impact on memory footprint and batch size.

## 5. XLA, libtpu, and Differences from Standard Python Programs

TPUs do not execute arbitrary Python code on TensorCores. The framework constructs tensor operations; **XLA** compiles the graph into an optimized TPU executable, while **libtpu** provides the runtime/driver.

### JIT Compilation

A JAX step can be decorated with `jax.jit` for XLA compilation:

~~~python
import jax
import jax.numpy as jnp

@jax.jit
def matmul_relu(a, b):
    return jnp.maximum(jnp.matmul(a, b), 0)

a = jnp.ones((1024, 1024), dtype=jnp.bfloat16)
b = jnp.ones((1024, 1024), dtype=jnp.bfloat16)

result = matmul_relu(a, b)
result.block_until_ready()  # Wait for computation to complete before measuring time
print(result.shape)
~~~

The first call can be slow due to compilation. Subsequent calls with matching shapes/dtypes can reuse the compiled executable. Always separate **compile time** from **steady-state step time** in benchmarks.

### Dynamic Shapes

A model continuously receiving tensors of varying lengths can trigger recompilation. Common mitigation techniques include:

- Padding to a fixed set of length buckets.
- Bucketing sequence lengths.
- Keeping batch/shapes stable within pipeline stages.
- Optimizing sharding/layouts and avoiding unnecessary host–device transfers.
- Benchmarking both padding overhead and compilation frequency.

Do not pad every dimension to an extreme maximum size: this wastes HBM and compute. The goal is to **balance minimal recompilation against padded space/compute overhead**.

### Precision

Dtypes like `bfloat16` and `float32` are commonly used for ML on TPUs. Newer generations support additional precisions for training/inference, but never assume every op in FP8 or BF16 achieves identical quality to FP32. Evaluate convergence, loss scaling, numerical stability, and output accuracy.

## 6. Translating Business Requirements into a Workload Specification

An ML infrastructure request should specify **workload goals** before naming a TPU type.

| Category | Fields to Collect | Illustrative Example |
|---|---|---|
| Workload type | Pretrain, fine-tune, batch inference, online inference | Encoder fine-tuning |
| Framework | JAX, PyTorch/XLA, TensorFlow, serving runtime | JAX |
| Model | Parameter count, architecture, operators, tokenizer | Dense Transformer |
| Data | Size, location, format, read throughput | 2 TiB Parquet/TFRecord |
| Sequence | Input/output length, length distribution | 512–2,048 tokens |
| Batch | Global batch, per-device batch, gradient accumulation | Needs benchmarking |
| Precision | BF16/FP32/mixed precision | BF16 + FP32 accumulators |
| Memory | Weights, activations, gradients, optimizer, KV cache | Not yet measured |
| Throughput | Samples/s, tokens/s, or steps/s | Set by ML team |
| Latency | p50/p95, TTFT, TPOT if serving | Per SLO |
| Reliability | Checkpoint cadence, RTO, preemption tolerance | Resumable |
| Security | PII, data residency, model access | Confidential dataset |
| Budget | Cost/experiment, maximum chip-hours | Per project quota |

Example data shows how to document requirements, not actual measured results.

### How Do Training and Inference Differ?

**Training** includes the forward pass, backward pass, and optimizer step; it requires HBM for gradients/optimizer states and can involve heavy inter-chip communication.

**Fine-tuning** may use adapters/LoRA to reduce updated parameters, yet still computes attention and stores activations depending on the technique.

**Batch inference** focuses on throughput; it can aggregate many requests and run over longer windows.

**Online inference** prioritizes p95 latency, time to first token (TTFT), time per output token (TPOT), tokens/s, and availability. Batching boosts throughput but can increase per-request queue wait if unmanaged.

## 7. Estimating HBM: Look Beyond Model Size

A rough calculation for weight memory:

~~~text
Weight memory ≈ number_of_parameters × bytes_per_parameter
~~~

**Hypothetical** example of a 7-billion-parameter dense model stored in BF16:

~~~text
7,000,000,000 × 2 bytes ≈ 14,000,000,000 bytes ≈ 13.0 GiB
~~~

This is **weight memory only**. You cannot conclude from this alone that the model fits on a 32 GiB HBM TPU for arbitrary sequence lengths and concurrency.

### What Else Does Training Need?

- Gradient tensors.
- Optimizer states (e.g., Adam stores two moment estimates).
- Activations for the backward pass.
- Temporary buffers, compiled programs, and input batches.
- Checkpoint staging.
- Sharding/replication overhead and fragmentation.

### What Else Does Inference Need?

- Weights.
- KV cache depending on batch size, layer count, context length, and concurrent sequences.
- Activations and temporary buffers.
- Runtime memory allocation.
- Potential model sharding and communication buffers.

Techniques such as quantization, recomputation/activation checkpointing, or parameter-efficient tuning shift HBM demand and compute cost. Choose optimizations after profiling confirms the bottleneck, not solely from a theoretical spreadsheet.

### Per-Chip HBM and Sharding

A slice's "total" HBM is the hardware sum, **not a transparent shared memory pool**. The framework must shard tensors across devices and pay communication costs when gathering results. If a tensor is improperly sharded or an op materializes a full tensor on one chip, OOM can still occur despite large total slice HBM.

## 8. Optimizing Batch Size and Tensor Shapes

Batch size affects MXU saturation and HBM consumption.

- Batch too small: TPU may be underutilized with high relative overhead.
- Batch too large: OOM, altered convergence, or increased queue latency.
- Highly variable sequence lengths: excessive recompilation or heavy padding.
- Suboptimal layout/sharding: increased all-gather and collective communication.

For distributed training:

~~~text
Global batch size
  = per-device batch size
    × total participating devices
    × gradient accumulation steps
~~~

This illustrative formula applies when devices process non-overlapping data shards in a corresponding data-parallel setup. When using model/pipeline parallelism, "total devices" cannot automatically equal all TPU chips as the data-parallel multiplier; use the actual number of data replicas.

### Batch Benchmarking

1. Start with a batch size that fits HBM.
2. Warm up JIT compilation.
3. Measure steps/s, samples/s, and device utilization.
4. Increase batch size in controlled increments.
5. Check for OOM, numerical quality, and convergence.
6. Measure cost/chip-hour per completed unit of work.
7. Select the batch size meeting both efficiency **and** model quality targets.

## 9. Input Pipeline: Keep TPUs from Waiting on CPU or Storage

A TPU has massive compute speed but can sit idle most of the time if the host reads remote files, decodes images, or tokenizes too slowly.

### Common Bottlenecks

| Bottleneck | Symptom | Mitigation |
|---|---|---|
| Data reading | Low TPU duty cycle, high I/O wait | Parallel reads, prefetching, dataset layout |
| Decode/tokenize | Host CPU busy while TPU is idle | Preprocess ahead of time, vectorize, or scale workers |
| Many small files | Excessive object/metadata requests | Purposefully shard files/record formats |
| Host–device transfer | Transfers dominate step time | Batch, pipeline, and keep tensors on device |
| Cross-region data | Increased egress/latency | Co-locate dataset and compute per residency rules |
| Shuffle/sampling | Stalls before training steps | Prefetch, stable seeds/partitions |
| Checkpointing | Long training pauses during saves | Async checkpointing and tuned frequency |

Cloud Storage works well for datasets and checkpoints, provided you evaluate throughput, request costs, location, IAM, and pipeline readers. Configure data loader workers to match host CPU capacity and avoid all workers redundantly reading the same file set.

### Multi-TB Data Scenarios

If a dataset originates on-premises, complete ingestion and integrity checks before provisioning expensive TPUs. Do not rent TPUs continuously while waiting for data copies. Check bandwidth/latency, checksums, and residency requirements. Schedule jobs so TPU provisioning starts only after data is ready.

## 10. Distributed Training: Data, Model, and Pipeline Parallelism

Three core techniques:

| Technique | Principle | Risks |
|---|---|---|
| Data parallel | Multiple replicas process different batches and aggregate gradients | All-reduce overhead, batch scaling, synchronization |
| Model/tensor parallel | Split tensors or layers across devices | All-gather/all-to-all, HBM, topology |
| Pipeline parallel | Split model stages across devices | Pipeline bubbles, load imbalance |

Real-world systems often combine multiple techniques. TPU slices and ICI reduce communication overhead, yet proper sharding design remains essential. Do not multiply single-chip speed by chip count while ignoring networking, optimizer states, pipeline flushes, and node failures.

### Checkpointing and Recovery

Multi-hour or multi-day training requires:

- Checkpointing weights, optimizer state, and training step.
- Storing artifacts/checkpoints in durable storage outside the TPU VM.
- Recording code revisions, dependency versions, random seeds, and configs.
- Testing actual restoration from checkpoints.
- Implementing retries/backoff, preemption handling, and full distributed worker re-initialization.
- Bounding checkpoint count/retention to control storage costs.

If using Spot, checkpoint cadence must balance storage/I/O cost against compute lost upon preemption.

## 11. Choosing Where to Run: TPU VM, GKE, or Managed Platforms?

| Option | When Appropriate | Key Considerations |
|---|---|---|
| TPU VM / Compute Engine | Experimentation, full OS/runtime control, direct training scripts | Self-managed lifecycle, dependencies, checkpoints, cleanup |
| GKE Standard with TPU slice node pool | Many containerized jobs, Kubernetes orchestration, platform teams | Selecting machine type/topology, requests/limits, node lifecycle |
| GKE Autopilot with TPU workloads | Reduced node management overhead when supported | Different TPU request model than Standard; specific version/quota/manifest rules |
| Vertex AI / managed ML with TPU support | Integrated pipelines, experiment tracking, model lifecycle | Verify supported TPU types, regions, and current capabilities |

Do not treat **Cloud Run** as a place to attach TPUs like a TPU VM; verify accelerator support for each execution service. Cloud Run can act as an HTTP API coordinator calling a TPU inference backend.

### Choosing TPU VMs for Labs

A single TPU VM is ideal for:

- Verifying the framework detects the hardware properly.
- Measuring compile vs. step times.
- Profiling HBM usage on a single node.
- Establishing a small model baseline.
- Debugging before scaling to multi-host.

### Choosing GKE for Production

GKE fits well when you already have container platforms, CI/CD, policies, IAM, and observability. However, TPU slice scheduling enforces an **all chips per node** rule for pods requesting TPUs. Multi-host node pools and distributed training also require coordinating worker/replica counts, networking, and group scheduling per TPU/GKE documentation.

## 12. Frameworks and TPU Runtimes: Avoiding Mismatches

Before running a workload, verify this matrix:

~~~text
TPU generation × machine type × TPU software image
× libtpu version × JAX / PyTorch-XLA / TensorFlow
× serving/training framework × model checkpoint format
~~~

### JAX

JAX is widely used on TPUs, combining `jax.jit`, `jax.numpy`, `jax.grad`, sharding, and PJRT. On supported TPU VMs, JAX documentation uses:

~~~bash
python3 -m pip install "jax[tpu]"
~~~

This installation method is **for compatible lab environments**. In production, pin JAX/JAXLIB/libtpu versions inside tested images according to the compatibility matrix for each TPU generation.

### PyTorch/XLA

PyTorch runs on TPUs via PyTorch/XLA or supported TPU runtimes. Do not assume every PyTorch model, custom CUDA extension, TorchInductor/Triton kernel, or operator ports to TPU without code changes. Verify:

- Matching PyTorch/XLA and libtpu versions.
- Device placement and graph compilation behavior.
- Distributed strategy.
- Unsupported operations and CPU fallbacks.
- Numerical quality and checkpoint compatibility.

### TensorFlow

TensorFlow provides TPU runtime versions per generation, though support is not uniform. Specifically, **TPU7x (Ironwood) is not currently supported by TensorFlow** in Google's TPU software versions table. Legacy TensorFlow models may require another generation or framework migration.

### Inference Runtimes

For LLM serving, Google Cloud documents vLLM and SGLang with JAX or PyTorch backends, such as `vllm-jax`, `vllm-torchtpu`, `sglang-jax`, or `sglang-torchtpu`. Support for models, quantization, and parallelism evolves per release: read the official compatibility tables rather than picking a runtime by name alone.

## 13. Preflight: Project, Zone, API, IAM, Quota, and Capacity

TPUs are specialized resources; **having quota does not guarantee physical capacity** in a target zone.

Minimum checklist:

- Select a billing project and region/zone supporting the machine type.
- Enable the API matching the **provisioning method** (Compute Engine/GKE or Cloud TPU API).
- Check quota for the exact TPU family, region/zone, and provisioning model.
- Confirm actual stock/capacity or an approved reservation.
- Verify the job's service account has permissions to read datasets and write checkpoints.
- Configure VPC, egress, DNS, firewall rules, and private storage access.
- Choose an OS image or container supporting the TPU generation and libtpu.
- Ensure budget alerts, an owner, expected runtime, and a cleanup plan exist.
- Store code, data, and model artifacts outside the VM to prevent loss upon deletion.

### Two Quota Families to Distinguish

- **Compute Engine/GKE TPU:** uses Compute Engine API quotas for accelerator machines/slices by consumption option.
- **Cloud TPU API:** has separate quotas by TPU version, zone, and consumption option.

Do not look at a Cloud TPU API quota line and assume a GKE TPU node pool creation will succeed. GKE TPU documentation describes different quotas from direct Cloud TPU API provisioning.

### Example API Check for Compute Engine TPU VMs

~~~bash
gcloud config set project PROJECT_ID
gcloud services enable compute.googleapis.com
gcloud compute zones list
~~~

This command **does not guarantee** listed zones have available TPU capacity. Check machine type availability and relevant quotas in the Console before provisioning.

## 14. Safe Lab: Creating a TPU v6e VM and Running JAX

Perform this lab only in a **budget-approved sandbox project**. TPUs can be expensive even when idle. Never run resource creation commands below in production.

### Inputs

- Authenticated Google Cloud CLI with permissions to create/delete Compute Engine instances.
- v6e quota and capacity in the chosen zone.
- Confirmed billing, budget alerts, and owner.
- Appropriately scoped VPC/service account for the workload.
- Plan to delete the TPU VM immediately after the lab.

### Step 1: Create the TPU VM

An example from Compute Engine documentation using a VM with 4 Trillium chips:

~~~bash
gcloud compute instances create tpu-lab-v6e \
  --machine-type=ct6e-standard-4t \
  --zone=europe-west4-a \
  --image-project=ubuntu-os-accelerator-images \
  --image-family=ubuntu-accel-2204-amd64-tpu-v5e-v5p-v6e \
  --maintenance-policy=TERMINATE \
  --project=PROJECT_ID
~~~

Choosing `europe-west4-a` is purely a documentation example; switch to a zone matching your organization's quotas, capacity, data residency, and pricing. `maintenance-policy=TERMINATE` is a lifecycle requirement for TPU VMs in this configuration; prepare checkpoints to handle maintenance events.

### Step 2: Inspect the VM and Log In

~~~bash
gcloud compute instances describe tpu-lab-v6e \
  --zone=europe-west4-a \
  --project=PROJECT_ID

gcloud compute ssh tpu-lab-v6e \
  --zone=europe-west4-a \
  --project=PROJECT_ID
~~~

If your environment uses IAP or omits external IPs, connect via your organization's approved SSH method; do not open port 22 to the entire Internet just for a lab.

### Step 3: Verify the Runtime

Inside the TPU VM:

~~~bash
python3 --version
python3 -m pip install "jax[tpu]"
python3 -c 'import jax; print(jax.devices()); assert jax.devices()[0].platform == "tpu"'
~~~

If the image already includes compatible packages, reinstalling is unnecessary. If libtpu/PJRT errors occur, follow the framework–TPU generation version/image guide rather than randomly installing wheels.

### Step 4: Run a Controlled Matrix Multiplication

Create `tpu_smoke_test.py`:

~~~python
import time
import jax
import jax.numpy as jnp

assert any(d.platform == "tpu" for d in jax.devices()), "No TPU devices detected"

@jax.jit
def step(x, y):
    return jnp.matmul(x, y)

x = jnp.ones((1024, 1024), dtype=jnp.bfloat16)
y = jnp.ones((1024, 1024), dtype=jnp.bfloat16)

start = time.perf_counter()
result = step(x, y)
result.block_until_ready()
first_call = time.perf_counter() - start

start = time.perf_counter()
result = step(x, y)
result.block_until_ready()
steady_call = time.perf_counter() - start

print("Devices:", jax.devices())
print("Result shape:", result.shape)
print("First call seconds:", round(first_call, 4))
print("Warm call seconds:", round(steady_call, 4))
~~~

Run:

~~~bash
python3 tpu_smoke_test.py
~~~

The first run includes JIT compilation and will be slower; these measurements are strictly a **smoke test**, not a price/performance benchmark across TPU generations. Official benchmarks require multiple steps, warmup, representative shapes, input pipelines, and stability checks.

### Step 5: Clean Up Resources

Exit the VM, then run on a machine with the Google Cloud CLI:

~~~bash
gcloud compute instances delete tpu-lab-v6e \
  --zone=europe-west4-a \
  --project=PROJECT_ID
~~~

Confirm the VM is deleted, check for leftover attached disks/IPs, and verify Billing. Remove any temporary test checkpoints, datasets, or buckets according to organizational retention policies.

## 15. Running TPU Workloads on GKE Standard

For multi-job environments or Kubernetes scheduling, TPUs are provisioned as TPU slice node pools with specific machine types and topologies.

### Resource Request Rules

GKE uses the `google.com/tpu` resource. When a container requests TPUs on a TPU slice node, **both request and limit values must equal the total number of TPU chips attached to that node** per GKE TPU scheduling rules.

For example, a `ct6e-standard-4t` node has 4 chips, so the workload requires:

~~~yaml
resources:
  requests:
    google.com/tpu: 4
  limits:
    google.com/tpu: 4
~~~

Do not request `google.com/tpu: 1` on a 4-chip node expecting Kubernetes to slice the node across four single-chip pods.

### Example Pod for a Single-Host Slice

Assuming an administrator has provisioned a 4-chip TPU v6e GKE Standard node pool with `2x2` topology:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: jax-tpu-smoke
  labels:
    app: tpu-lab
spec:
  restartPolicy: Never
  nodeSelector:
    cloud.google.com/gke-tpu-accelerator: tpu-v6e-slice
    cloud.google.com/gke-tpu-topology: "2x2"
  containers:
    - name: jax
      # Lab example; pin the image digest in production.
      image: us-docker.pkg.dev/cloud-tpu-images/jax-ai-image/tpu:latest
      command:
        - /bin/bash
        - -c
        - |
          python3 -c 'import jax; print(jax.devices())'
      resources:
        requests:
          google.com/tpu: 4
        limits:
          google.com/tpu: 4
~~~

This manifest **does not create the node pool**. Without a matching node, the Pod remains Pending. Pin image versions/digests in production and verify GKE version/TPU runtime compatibility.

Inspection commands in a lab cluster:

~~~bash
kubectl apply -f jax-tpu-smoke.yaml
kubectl get pods -o wide
kubectl describe pod jax-tpu-smoke
kubectl logs jax-tpu-smoke
kubectl delete pod jax-tpu-smoke
~~~

Running `kubectl apply` requires Kubernetes permissions and a pre-provisioned node pool. GKE Standard also requires managing node pool scaling/quotas; deleting a Pod **does not necessarily delete the node** or stop accelerator billing.

### Multi-Host Differences

For multi-host TPU slices, workers must be scheduled according to topology and participate in a unified distributed job. GKE documentation covers Jobs/JobSets, node pools, placement, and networking. Never create one Pod requesting chips across multiple nodes; each Pod requests chips **on its own node**, while orchestration coordinates multi-host startup and recovery.

### GKE Autopilot

Autopilot uses a different request and provisioning model than GKE Standard. Do not reuse Standard node pool creation commands. With Autopilot, define TPU accelerators and workload manifests per supported TPU versions, topologies, quotas, and conditions. Verify current support before deploying.

## 16. Online Inference on TPUs: Throughput and Latency

For LLMs/chatbots, distinguish two phases:

- **Prefill:** processes the input prompt, typically heavy in matrix multiplications.
- **Decode:** generates subsequent tokens step-by-step, typically sensitive to memory bandwidth and KV cache.

Metrics to track:

| Metric | Meaning | Why It Matters |
|---|---|---|
| Time to First Token (TTFT) | Time from request to first token | Initial responsiveness |
| Time per Output Token (TPOT) | Time per generated token | Streaming smoothness |
| Tokens/s/chip | Normalized throughput | Accelerator efficiency |
| p95 end-to-end latency | Full request latency | User SLO |
| Concurrency and queue wait | Waiting/active requests | Capacity planning |
| KV-cache utilization | Memory used for context | OOM risk / concurrency cap |
| Error/timeout rate | Failed request ratio | Reliability |
| Cost per 1M tokens | Unit cost | FinOps |

Serving stacks like vLLM or SGLang offer JAX/PyTorch TPU backends, though model support varies. Check **model architecture, quantization, TP/DP configuration, context length, and versions**.

### Dynamic Batching

Batching more requests boosts throughput, but an overly long queue degrades TTFT. Optimize for p95 SLOs and cost per token, not just peak synthetic tokens/s.

### Separating API and Model Server

A sound architecture:

~~~mermaid
flowchart LR
  C[Client] --> API[API / auth / quota]
  API --> Q[Request queue / router]
  Q --> T[TPU model serving pool]
  T --> R[Streaming response]
  R --> C
  API --> M[Monitoring / tracing / alerts]
  T --> M
  T --> S[Model weights / checkpoint storage]
~~~

The API can run on Cloud Run or GKE CPU nodes while the model backend runs on TPUs. Optimal layout depends on weight loading speed, concurrency, cold starts, model size, and network isolation rules.

## 17. Monitoring and Profiling: Is the TPU Actually Working?

The goal is not merely "job runs without errors," but knowing whether bottlenecks sit in compute, memory, host, I/O, or communication.

### Observability Layers

| Layer | Signals to Monitor |
|---|---|
| TPU device | Accelerator duty cycle, HBM usage, memory bandwidth utilization |
| Host VM | CPU, RAM, disk/network I/O, loader queues |
| XLA | Compile time, recompilation, operation profiles, collective overhead |
| Training | Steps/s, tokens/s, loss, gradient/optimizer stability |
| Inference | TTFT, TPOT, queue delay, tokens/s, error rate |
| Distributed | Worker failures, collective communication, stragglers |
| Cost | Chip-hours, idle time, checkpoint/storage/egress costs |

Google Cloud exposes metrics like accelerator duty cycle and memory bandwidth utilization for supported TPU versions. Use **Cloud Monitoring** and the **XProf** profiler (for XLA-based workloads) to inspect timelines and operation-level bottlenecks.

### Categorizing Bottlenecks

1. **Low duty cycle, high host CPU:** likely input-bound; measure decode/tokenization/read throughput.
2. **HBM nearly full/OOM:** reduce batch/sequence length, improve sharding, or enable activation checkpointing.
3. **Frequent compilations:** examine shape variability, static arguments, and caching.
4. **High collective time:** inspect topology and partitioning strategy.
5. **Slow model loading:** check storage/size, initialization, and prefetching.
6. **High throughput but poor p95 latency:** inspect queue wait times and batching.
7. **Abnormal training loss:** verify precision, data distribution, optimizer, and numerical stability.

Do not equate "high device utilization" alone with success: a kernel may stay busy doing wasted work from excessive padding, duplicate data, or redundant conversions.

## 18. Security and Data/Model Governance

ML workloads routinely handle datasets, model checkpoints, and sometimes sensitive data. Security design must precede TPU provisioning.

### IAM and Identity

- Use dedicated service accounts for TPU VMs or GKE workloads.
- Grant dataset read access strictly to required buckets/paths.
- Scope checkpoint/artifact write permissions minimally.
- On GKE, prefer Workload Identity Federation for GKE where appropriate.
- Never bake service account keys or tokens into images/containers.
- Restrict TPU creation/deletion and quota adjustments to authorized teams.

### Networking and Egress

- Place accelerators in appropriate VPCs/subnets and restrict inbound traffic.
- Use private access/DNS/routing scoped to required services; never open SSH to the Internet.
- Verify connectivity paths to Cloud Storage and artifact registries.
- Enforce egress restrictions when data/models must not leave the boundary.
- Audit dataset/checkpoint access logs per policy.

### Supply Chain

- Pin container digests and Python package versions.
- Verify model weights from trusted sources along with licenses and provenance.
- Scan images and manage dependencies and secrets.
- Never load unverified scripts or weights onto production VMs with access to sensitive data.
- Record metadata—dataset versions, code commits, TPU types, and framework versions—for reproducibility.

### Data and Retention

- Classify PII and enforce access controls, data residency, and encryption.
- Keep sensitive sample data out of public logs and profiles.
- Store checkpoints according to retention and encryption policies.
- Remember traces/profiles can expose tensor shapes or workload metadata needing protection.

## 19. TPU Costs and Provisioning Models

TPU costs vary by **version, location, and consumption model**. Options include on-demand, Spot, Flex-start, and reservations/commitments where supported.

| Option | Best For | Trade-offs |
|---|---|---|
| On-demand | Labs, experiments, variable workloads | No capacity guarantee, spot-rate pricing |
| Spot | Checkpointed training jobs tolerant of preemption | Can be preempted, must resume |
| Flex-start | Short jobs able to wait within bounded queue windows | Duration limits / provisioning rules |
| Reservation/commitment | Steady, large, predictable demand | Financial commitment, capacity management |
| GKE managed scheduling | Platform teams running multi-tenant workloads | Still requires optimizing node utilization and cleanup |

Listed prices are usually quoted **per chip-hour**, though invoices may include compute resources, storage, networking, reservations, or orchestration charges. Consult [Cloud TPU Pricing](https://cloud.google.com/tpu/pricing) for exact configurations before budgeting.

### Estimation Formula

~~~text
Accelerator cost (estimate)
  ≈ number_of_chips × billable_hours × applicable_price_per_chip_hour

Total experiment cost
  ≈ accelerator cost
    + persistent storage / checkpoint storage
    + data transfers and operations
    + supported host / orchestration charges
    + profiling / logging / monitoring charges where applicable
~~~

This is an estimation framework, not a substitute for actual SKUs/pricing, and you should avoid double-counting items bundled in an SKU.

### Optimizing Job Value

Track metrics such as:

- **Cost per completed training run** (including retries and compile time).
- **Cost per million training tokens**.
- **Cost per million generated tokens**.
- **Cost per evaluated model**.
- **Useful accelerator duty cycle**.
- **Checkpoint recovery loss** measured in potentially lost compute time.

A newer TPU generation with a higher chip-hour price that finishes faster can still be cheaper per **unit of output**. Benchmark using identical datasets, model quality, precision, and latency targets before deciding.

### Avoiding Idle Costs

- Do not provision TPUs upfront before datasets are ready.
- Use checkpoints to split jobs and leverage Spot where suitable.
- Delete/stop resources via supported mechanisms and verify billing state.
- On GKE, check node pools/TPU slices after deleting Pods/Jobs.
- Monitor idle capacity inside reservations and reuse policies.
- Configure budget alerts and assign resource owners.

## 20. Common Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| TPU VM creation fails | Missing quota, unsupported zone, or no capacity | Check version, zone, API, quota, and reservations |
| GKE Pod Pending | Missing node pool, topology/selector mismatch | Check node labels, topology, and cluster version |
| GKE requests 1 TPU on 4-chip node | GKE does not subdivide TPU resources that way | Set requests/limits to full node chip count |
| JAX sees only CPU | Image/libtpu mismatch or accelerator not ready | Check `jax.devices()`, runtime, and image |
| PyTorch model hits unsupported op | CUDA/custom kernel lacks TPU path | Check PyTorch/XLA compatibility and rewrite op |
| TensorFlow fails on TPU7x | Generation does not support TensorFlow | Pick a supported generation or switch frameworks |
| First step is very slow | XLA JIT compilation or input pipeline init | Separate compile time from steady-state time |
| Long runtime but low throughput | CPU input-bound, shape/padding, or communication | Profile with XProf, tune data loader and sharding |
| TPU OOM | Weights + activations + KV cache exceed HBM | Reduce batch/seq, adjust sharding, quantize |
| Training loses progress after Spot | Missing durable checkpoints | Save/test checkpoint restoration and retries |
| Poor inference TTFT | Queueing/batching/cold loading | Measure queue wait, warm-up, and concurrency |
| Multi-host job hangs | A worker failed to start or collective mismatch | Check group scheduling and per-host logs |
| Cost exceeds budget | Idle/oversized TPU, repeated job retries | Track chip-hours, unit costs, and cleanup |
| Divergent training results | Inconsistent precision, seed, runtime, or data | Pin environment and inspect convergence |
| Slow dataset reads | Storage location, file layout, or host I/O | Parallelize reads, prefetch, and shard data |

## 21. Case Study: Choosing TPUs for Three Workloads

### Workload A: Fine-Tuning an Internal Language Model

Profile: Transformer model, sequence length 2,048, tunable batch size, runs several hours per job, and tolerates resuming after preemption.

Evaluation plan:

1. Verify JAX/PyTorch-XLA and model operators are supported.
2. Estimate weights, activations, and optimizer/HBM requirements.
3. Test a v6e slice or another generation with available quota/capacity.
4. Pin the runtime and checkpoint to Cloud Storage.
5. Benchmark steady-state tokens/s and cost per completed run.
6. Consider Spot/Flex-start given preemption tolerance.

### Workload B: Real-Time Product Recommendation API

Profile: small requests, strict p95 SLA, large embeddings, fluctuating traffic over time.

Evaluation plan:

1. Benchmark CPU/GPU/TPU baselines; do not assume TPU wins automatically.
2. Verify whether the model benefits from SparseCore/embedding support.
3. Estimate HBM, concurrency, and batching behavior.
4. Design autoscaling/capacity while avoiding slow cold loads.
5. Measure p95 end-to-end latency and cost per 1,000 requests.
6. Keep API auth/quotas in the appropriate serving tier and isolate the model backend.

### Workload C: Batch CSV Transformation ETL

Profile: CSV parsing, string cleaning, reading/writing many files, and simple additions.

Recommendation: start with CPU/appropriate batch processing. If most time goes to parsing/I/O rather than tensor compute, TPUs will sit idle and waste money. Only consider TPUs if a large, distinct ML tensor stage exists and benchmarks prove clear benefit.

### Analysis Questions

- Which workload requires the most frequent checkpointing?
- Why must Workload B prioritize p95 latency over peak throughput?
- When should you prefer multiple TPU chips on one host over multiple hosts?
- Why might a v6e chip with a lower hourly rate still cost more per training run than another generation?
- How do data boundaries and IAM change when using a sensitive internal model?

## 22. Pre-Production Checklist

- [ ] Workload type and SLOs (steps/s or TTFT/TPOT) defined.
- [ ] Framework and TPU generation compatibility matrix verified.
- [ ] Model operators, precision, and quantization tested.
- [ ] HBM estimate includes weights, activations/gradients, or KV cache.
- [ ] Batch/sequence lengths and sharding strategy evaluated.
- [ ] Topology and chips/host/slice counts confirmed.
- [ ] Zone/quota/capacity or reservations prepared.
- [ ] TPU software image and libtpu/JAX/PyTorch versions pinned.
- [ ] Dataset pipeline throughput sufficient to avoid idling TPUs.
- [ ] Checkpointing/resumption tested, especially when using Spot.
- [ ] Service accounts, bucket access, networking, and secrets comply with policy.
- [ ] Benchmarks measure steady-state, compile overhead, and cost per useful unit.
- [ ] Monitoring tracks TPU duty cycle, HBM, CPU/I/O, and inference/training KPIs.
- [ ] Alerts configured for worker errors, OOMs, queues, job retries, and spend.
- [ ] Cleanup mechanisms exist for TPU VMs and GKE node pools.
- [ ] Rollback plan and host/slice failure recovery in place.
- [ ] Dataset/model versions, seeds, code revisions, and image digests recorded.
- [ ] Regional pricing, TPU generation, and consumption model verified prior to approval.

## Review Questions

1. How do TPUs differ from CPUs and GPUs in computation style and compilation?
2. Why can't you conclude a 7B BF16 model fits in HBM solely by calculating weight memory?
3. How does a TPU slice differ from a TPU VM and a TPU Pod?
4. Why do JIT compilation and dynamic shapes impact TPU benchmarks?
5. When should an I/O-bound workload avoid running on TPUs?
6. Is requesting `google.com/tpu: 1` on a 4-chip node valid under GKE TPU scheduling rules?
7. Distinguish quotas for Compute Engine/GKE TPUs versus the Cloud TPU API.
8. Why might TPU creation fail in a specific zone even when you have quota?
9. Which workloads suit Spot TPUs, and what role does checkpointing play?
10. Which metrics should be measured to optimize online LLM serving on TPUs?
11. Why is TensorFlow not the default choice for TPU7x?
12. How can chip-hour price and cost per completed training run lead to different decisions?

## Conclusion

Cloud TPU is specialized acceleration infrastructure for machine learning tensor operations. Success depends not only on choosing a TPU generation with high TFLOPS or large HBM, but also on **model compatibility, frameworks/XLA, tensor shapes, topology, sharding, data pipelines, quotas, capacity, and recovery requirements**.

For training, measure steady-state step time, tokens/s, model quality, and resumability. For inference, measure TTFT, TPOT, p95 latency, concurrency, KV cache, and cost per token. TPU VMs suit controlled experimentation; GKE suits large-scale container orchestration once node pool, topology, and `google.com/tpu` rules are satisfied.

By grounding decisions in benchmarks and SLOs, protecting datasets/models with IAM, storing checkpoints off-VM, and tracking unit economics, Cloud TPU can deliver substantial value for suitable ML workloads without wasting specialized infrastructure.

## References

- [Understand Tensor Processing Units](https://cloud.google.com/docs/compute-area/tpus)
- [Cloud TPU overview](https://cloud.google.com/tpu/docs/intro-to-tpu)
- [Cloud TPU versions and machine types](https://cloud.google.com/compute/docs/tpus/tpu-machines)
- [Plan your Cloud TPU resources](https://cloud.google.com/tpu/docs/plan-tpus)
- [Create a TPU VM instance](https://cloud.google.com/compute/docs/tpus/create-tpu-vm-instance)
- [Quickstart: Create a TPU instance](https://cloud.google.com/compute/docs/tpus/quickstart-create-tpu-instance)
- [TPU software versions and framework support](https://cloud.google.com/tpu/docs/runtimes)
- [Cloud TPU quotas](https://cloud.google.com/tpu/docs/quota)
- [About TPUs in GKE](https://cloud.google.com/kubernetes-engine/docs/concepts/tpus)
- [Plan TPUs in GKE](https://cloud.google.com/kubernetes-engine/docs/concepts/plan-tpus)
- [Deploy TPU workloads in GKE Standard](https://cloud.google.com/kubernetes-engine/docs/how-to/tpus)
- [Deploy TPU workloads on GKE Autopilot](https://cloud.google.com/kubernetes-engine/docs/how-to/tpus-autopilot)
- [Cloud TPU performance guide](https://cloud.google.com/tpu/docs/performance-guide)
- [Profile your model on Cloud TPU](https://cloud.google.com/tpu/docs/profile-tpu-vm)
- [Monitor Cloud TPU VMs](https://cloud.google.com/tpu/docs/troubleshooting/tpu-vm-monitoring)
- [Run inference on Cloud TPU](https://cloud.google.com/tpu/docs/tpu-inference)
- [Cloud TPU pricing](https://cloud.google.com/tpu/pricing)
- [JAX installation on Cloud TPU](https://docs.jax.dev/en/latest/installation.html)
