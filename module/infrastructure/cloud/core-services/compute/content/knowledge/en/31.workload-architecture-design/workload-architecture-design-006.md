# Designing Accelerator-Backed Inference Workloads

An inference workload takes input data, passes it through a trained model, and returns predictions or outputs. When a model requires heavy matrix math, tensor operations, or image/video processing, CPUs may not meet latency and throughput targets. GPUs, NPUs, or specialized accelerators can boost performance, but only when the model, runtime, data pipeline, and serving architecture are optimized together.

Designing inference workloads differs from designing a pure batch job. Interactive APIs usually enforce p95/p99 latency SLOs; background services care about throughput, queue age, and completion times; generative models may require tracking time to first token and token generation speed. A GPU with high utilization does not guarantee a good user experience if requests sit waiting in a batch too long or VRAM is nearly exhausted.

This lesson focuses on designing accelerator-backed inference systems on the cloud, from hardware and runtime selection to batching, serving, autoscaling, observability, security, and cost optimization. After this lesson, you will be able to:

- Distinguish online inference, streaming inference, and batch inference.
- Choose CPUs, GPUs, NPUs, or accelerators based on model, precision, memory, and SLOs.
- Estimate VRAM/RAM and identify compute, memory, network, or preprocessing bottlenecks.
- Design request lifecycles, batching, concurrency, and queues aligned with a latency budget.
- Select serving runtimes, model packaging approaches, and deployment strategies on VMs or Kubernetes.
- Design autoscaling driven by inference load and accelerator capacity.
- Measure latency, throughput, accelerator utilization, memory, and cost per inference.
- Test accuracy, stability, data security, and resilience when accelerators fail.

## 1. What Is Inference and How Does It Differ from Training?

Training updates model weights over many optimization steps; inference uses fixed weights to compute results for new inputs. Both stages can run on the same kinds of accelerators, yet they have distinct resource profiles and goals.

| Characteristic | Training | Inference |
|---|---|---|
| Goal | Optimize weights over many iterations | Generate predictions from a trained model |
| Memory | Model, gradients, optimizer states, activations | Model weights, activations, caches, and workspace |
| Load pattern | Usually long-running with large batches | Short continuous requests or background batches |
| SLO | Training job completion time | Latency, throughput, response time, or deadlines |
| Scaling | Data/model/pipeline parallelism | Replicas, batching, model sharding, or multi-accelerator |
| Lifecycle | Episodic jobs or pipelines | Persistent service scaling with requests or queues |

Inference operates in several modes:

- **Online inference:** callers send a request and wait for the result in the same interactive call.
- **Streaming inference:** outputs return incrementally, such as tokens or audio chunks.
- **Batch inference:** the system processes large input datasets in batches, typically optimizing for throughput and cost.
- **Asynchronous inference:** the API accepts a job and returns a job ID; workers process it and persist results for later retrieval.
- **Edge inference:** the model runs near devices or data sources to cut latency, reduce data transfer, or operate offline.

A single model can be served in multiple modes. Choose the serving mode based on user experience, input sizes, output lengths, request frequency, and processing deadlines.

## 2. Characterizing the Workload Before Choosing an Accelerator

Never start by asking "Which GPU is fastest?" Describe the workload and success criteria first:

| Attribute | Questions to Answer |
|---|---|
| Model | Architecture, parameter count, framework, input/output shapes, and version |
| Input | Image dimensions, token sequence lengths, audio duration, tensor dimensions, or payloads |
| Output | Labels, embeddings, bounding boxes, tokens, scores, or structured data |
| Arrival rate | Average requests, peaks, bursts, and temporal distribution |
| Concurrency | How many concurrent requests; do requests vary widely in processing time? |
| Latency | p50/p95/p99, time to first token, and deadlines |
| Throughput | Requests/second, images/second, tokens/second, or items/second |
| Accuracy | Precision, recall, error tolerance, or domain-specific metrics |
| Data | Is data sensitive, subject to residency rules, or required to stay at the edge? |
| Cost | Budget per request, token, image, or completed job |

### Defining SLOs by Inference Type

For interactive APIs, p95/p99 latency often matters more than peak throughput. For streaming LLMs, separate:

- **Time to first token (TTFT):** time from request receipt until the first token is sent.
- **Inter-token latency (ITL):** interval between subsequent tokens.
- **Output token throughput:** token generation rate.
- **End-to-end latency:** total time to finish the full response.

For batch inference, overall throughput and total dataset completion time may matter more than per-item latency. For image-processing pipelines, SLOs can be defined in images/second and error rates.

### Latency Budget

Total response time breaks down into components:

\[
T_{total} =
T_{queue} + T_{preprocess} + T_{transfer} +
T_{inference} + T_{postprocess} + T_{network}
\]

Measuring only GPU kernel time misses queueing, model loading, image decoding, tokenization, CPU-GPU data transfers, and serialization. Measure both end-to-end latency and per-phase durations.

## 3. Choosing CPUs, GPUs, NPUs, and Accelerators

Accelerators pay off when workloads involve massive parallel math supported by the runtime. Not every model needs a GPU.

| Hardware Type | Strengths | Suitable Workloads | What to Verify |
|---|---|---|---|
| CPU | Flexible, excels at branching/control logic, easy to deploy | Small models, preprocessing, low QPS, CPU-optimized inference | Vector instructions, core count, memory bandwidth |
| GPU | Massive tensor/matrix parallelism, broad AI ecosystem | LLMs, vision, speech, embeddings, and large batches | VRAM, memory bandwidth, precision, interconnects |
| NPU/AI accelerator | Optimized for specific operators/precisions with high power efficiency | Inference supported by the vendor compiler/runtime | Operator coverage, model conversion, quantization, and drivers |
| FPGA | Configurable hardware pipelines for specialized latency/throughput | Streaming, signal processing, or fixed pipelines | Toolchain, development effort, operators, and operability |

### When Is a CPU Enough?

CPUs can be the right choice when models are small, request rates are low, latency budgets are generous, or libraries are already vectorized. CPUs also commonly handle tokenization, image decoding, request routing, preprocessing, and postprocessing even when inference runs on a GPU.

Do not move an entire pipeline onto a GPU if preprocessing is too small to amortize transfer and kernel launch overhead. Keep decoding/validation on CPU, then send normalized tensors to the accelerator.

### Choosing a GPU for the Workload

Key specifications:

- **VRAM capacity:** holds weights, activations, KV caches, workspaces, and batches.
- **Memory bandwidth:** governs speed of reading weights, tensors, and caches.
- **Compute throughput:** inspect at the actual precision used, such as FP64, FP32, TF32, FP16, BF16, or INT8.
- **Interconnect:** PCIe, NVLink, or equivalent between GPUs and host/other GPUs.
- **GPU topology:** GPUs per node, NUMA affinity, PCIe root complexes, and peer-to-peer capability.
- **Software support:** drivers, CUDA/HIP/runtimes, frameworks, compilers, and serving engines.

Peak FLOPS is only a theoretical ceiling. Benchmarking with your actual model, sequence lengths, image sizes, batch sizes, and precision reveals achievable throughput.

### NPUs and Specialized Accelerators

NPUs can achieve strong energy efficiency when models compile cleanly onto supported graphs/operators. However, unsupported operators may fall back to CPU, inflating latency. Always check compiler reports, operator coverage, quantization constraints, and how the runtime handles fallbacks.

## 4. Estimating Accelerator Memory

VRAM is a hard boundary. Even with abundant GPU compute, a model will fail to load or crash if weights, activations, caches, and workspaces exceed available memory.

An estimation model:

\[
M_{total} \approx M_{weights} + M_{activations} +
M_{cache} + M_{workspace} + M_{runtime}
\]

Where:

- \(M_{weights}\): memory for model parameters.
- \(M_{activations}\): intermediate tensors for the batch and input dimensions.
- \(M_{cache}\): request-serving caches, such as LLM KV caches.
- \(M_{workspace}\): scratch memory for kernels, attention, or math libraries.
- \(M_{runtime}\): context, allocators, graphs, and serving engine overhead.

### Estimating Weights

If a model has \(P\) parameters and each parameter takes \(b\) bytes:

\[
M_{weights} \approx P \times b
\]

For example, a 7-billion-parameter model using 16-bit weights requires roughly:

\[
7 \times 10^9 \times 2 \approx 14 \text{ GB}
\]

This is only theoretical weight size. Real deployments need additional room for overhead, caches, and workspaces; sharding strategies can also allocate extra buffers. Never pick a GPU whose VRAM barely matches raw weight size.

### KV Cache for Token-Generating Models

Autoregressive LLMs maintain a key/value cache to avoid recomputing all prior tokens on every decode step. Cache size scales with concurrent sequences, context length, layer count, KV head count, and head dimension.

An approximate form:

\[
M_{KV} \approx
2 \times L \times B \times S \times H_{KV}
\times D \times bytes
\]

Where \(L\) is layer count, \(B\) is active cached sequences, \(S\) is cached token count, \(H_{KV}\) is KV head count, and \(D\) is head dimension. The factor of 2 accounts for keys and values. GQA/MQA architectures, cache quantization, paging, and runtime allocation strategies alter actual footprint.

This explains why raising concurrency or context length can exhaust VRAM even though model weights remain constant. Benchmark both concurrent sequences and long contexts when sizing serving capacity.

## 5. Precision, Quantization, and Output Quality

Inference can use multiple numeric precisions:

- FP32: higher numerical accuracy at the cost of more memory and compute.
- FP16/BF16: cuts memory and boosts throughput on supporting accelerators; verify accuracy.
- INT8/INT4: shrinks weights and can speed execution, though quality depends on model, calibration, and kernels.
- Mixed precision: assigns different precisions across model layers to balance accuracy and performance.

Quantization may use post-training quantization or quantization-aware training. Choose based on the model, calibration data, supported operators, and quality requirements.

Before promoting a new precision to production:

1. Select a representative validation dataset and define quality metrics.
2. Run a baseline at original precision.
3. Convert/quantize the model and verify operators.
4. Compare accuracy, recall, BLEU/WER, or relevant domain metrics.
5. Benchmark latency, throughput, VRAM, and cost.
6. Test edge cases and out-of-distribution inputs.
7. Run a canary rollout and monitor quality post-deployment.

Never pick INT4 solely to squeeze a model into VRAM. If quality degrades past acceptable limits, choose a smaller model, shard across GPUs, offload, or use a larger accelerator.

## 6. Serving Architecture for Inference

An online inference system typically consists of these layers:

~~~mermaid
flowchart LR
    C["Client"] --> G["API Gateway / Load Balancer"]
    G --> A["Auth, validation, rate limit"]
    A --> Q["Request queue / admission control"]
    Q --> S["Inference serving"]
    S --> P["Preprocess / tokenizer"]
    P --> X["CPU / GPU / NPU runtime"]
    X --> O["Postprocess"]
    O --> R["Response / stream"]
    S --> M["Metrics, logs, traces"]
~~~

Each component has distinct responsibilities:

- The gateway authenticates callers, enforces rate limits, and validates payloads.
- Admission control decides whether to accept, queue, or reject requests when capacity is tight.
- The serving runtime manages models, batching, concurrency, and devices.
- Pre/postprocessing normalizes inputs and formats outputs into API responses.
- Observability records per-phase latency, accelerator usage, errors, and quality signals.

For batch inference, you can omit the interactive gateway and use object storage, manifests, and a scheduler to feed partitioned datasets. For asynchronous inference, an API creates jobs and workers consume them from a queue.

### One Model or Multiple Models per Accelerator?

Co-locating multiple models on one GPU can boost utilization when individual models have low load, at the expense of complex VRAM sharing, scheduling, caching, and isolation. One large model can OOM if a neighbor claims memory or experiences a batch spike.

Strategies:

- One model per GPU: simple, predictable, and cleanly isolated.
- Multiple model replicas across multiple GPUs: increases throughput and availability.
- Multiple models sharing a GPU: improves utilization, requiring tight memory and scheduling controls.
- Model sharding across multiple GPUs: serves models larger than a single GPU.

Choose based on memory footprint, request patterns, SLOs, and operational overhead.

## 7. Batching and Concurrency

Batching combines multiple inputs into a single accelerator call to improve compute efficiency. Larger batches generally increase throughput, yet can also increase latency, VRAM consumption, and request wait times.

### Static Batching

Static batching waits for a fixed number of requests or processes fixed-size batches. Well suited for offline batch inference or workloads with uniform input sizes. Underfilled batches leave accelerators idle; waiting too long hurts latency.

### Dynamic Batching

Dynamic batching accumulates incoming requests over a short window or until hitting a maximum batch size. Configure:

- Max batch size.
- Max queue delay.
- Timeout when a batch is not yet full.
- Concurrency and memory limits.
- Priority policies or separate queues per model/SLO.

For example, a vision API might wait up to a few milliseconds to group images, without letting queue delay exceed the latency budget.

### Continuous Batching for LLMs

LLM serving can employ continuous/in-flight batching: new sequences enter the active batch as soon as other sequences finish or free slots. This improves utilization when prompt and output lengths vary widely. Monitor KV cache occupancy, active sequences, prefill vs. decode throughput, and ITL.

### Higher Concurrency Is Not Always Better

Pushing concurrency too high increases queueing delays and memory pressure; GPUs may OOM or p99 latency may degrade. Benchmark a matrix of `batch size × concurrency × input length`, then choose an operating point inside SLO with safety headroom.

## 8. Selecting an Inference Runtime and Model Server

The runtime governs how models are loaded, graphs optimized, batches managed, memory allocated, and accelerators invoked.

| Runtime / Serving Engine | Common Use Cases | What to Evaluate |
|---|---|---|
| ONNX Runtime | Models exported to ONNX needing multiple execution providers | Operator support, graph optimizations, provider fallback |
| NVIDIA TensorRT | NVIDIA GPUs, optimizing engines for specific models/shapes | Engine build times, precision, shape profiles, compatibility |
| NVIDIA Triton Inference Server | Serving multiple models/backends, dynamic batching, model repositories | Model lifecycle, metrics, concurrency, GPU sharing |
| vLLM | LLM serving with continuous batching and KV cache management | Model support, parallelism, memory efficiency, token metrics |
| Hugging Face TGI | Serving supported text-generation models | Model compatibility, batching, quantization, deployment |
| OpenVINO | Optimizing inference on supported Intel hardware | Operator coverage, precision, device plugins |

No single runtime is optimal for every model. Choose based on source framework, accelerator, operator coverage, streaming/batching requirements, observability, and model update workflows.

### Model Repositories and Versioning

Manage models as versioned artifacts:

- Model ID and version.
- Digest/checksum.
- Framework and runtime versions.
- Precision/quantization details.
- Input/output schemas.
- Dataset or source lineage per policy.
- Benchmark and validation results.

Never overwrite model weights in a live serving directory without versioning and safe rollouts. Deploy new model versions side by side, run shadow or canary traffic, and shift traffic gradually.

## 9. Distributing Models Across Multiple GPUs

When a model does not fit on one GPU or requires higher throughput, multiple GPUs can be used.

### Data Parallel / Replica Parallel

Each GPU holds a copy of the model and serves independent requests. This scales stateless inference cleanly behind a load balancer. Balance request counts, input/output lengths, and memory usage across replicas.

### Tensor Parallelism

Splits tensor operations within a single layer across multiple GPUs. Suits large models or speeding up a single request, but demands frequent inter-GPU communication. Interconnect bandwidth heavily affects performance.

### Pipeline Parallelism

Splits layers into sequential stages across multiple GPUs. Processing multiple microbatches improves utilization, though pipeline bubbles and inter-stage communication can add latency.

### Model Placement and Topology

For multi-GPU setups:

- Inspect GPU-to-GPU bandwidth and topology.
- Place GPUs serving the same model close together when the platform supports it.
- Verify PCIe/NVLink or equivalent interconnects.
- Check CPU/NUMA affinity and host-to-device paths.
- Avoid spanning tightly coupled model parallelism across separate nodes if the network cannot sustain it.

Model replicas typically scale total throughput; model parallelism handles models exceeding one accelerator or single requests needing multiple GPUs. Both strategies can be combined.

## 10. Deploying Inference on Kubernetes

Kubernetes schedules Pods requesting accelerators via vendor-supplied device plugins or extended resource mechanisms. Resource names and node labels depend on hardware/runtime; for instance, NVIDIA commonly exposes GPUs via `nvidia.com/gpu`.

Example Deployment requesting one GPU:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vision-inference
spec:
  replicas: 2
  selector:
    matchLabels:
      app: vision-inference
  template:
    metadata:
      labels:
        app: vision-inference
    spec:
      nodeSelector:
        accelerator: nvidia-gpu
      containers:
        - name: server
          image: registry.example.com/vision-inference:1.2.0
          ports:
            - containerPort: 8080
          resources:
            requests:
              cpu: "4"
              memory: "16Gi"
              nvidia.com/gpu: "1"
            limits:
              cpu: "8"
              memory: "24Gi"
              nvidia.com/gpu: "1"
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
            periodSeconds: 5
            failureThreshold: 6
~~~

This example assumes nodes carry `accelerator=nvidia-gpu` and the device plugin is running. In real environments, configure proper node labels, drivers, container toolkits, device plugins, `RuntimeClass` if needed, and vendor extended resources.

### What to Verify

- Nodes have the expected accelerator model, VRAM, and driver version.
- Device plugins advertise resources and node `allocatable` accurately.
- Pod GPU requests match the accelerator type.
- Model images, weights, and runtimes match host drivers.
- Readiness passes only after model loading and warm-up finish.
- Liveness does not repeatedly restart Pods while large models initialize.
- Pods have enough CPU/memory for preprocessing and serving.
- Node pools have suitable quotas and autoscaling.
- Pod disruptions and rolling updates do not wipe out total capacity.

### GPU Sharing

Some platforms support GPU sharing via MIG, time-slicing, or vendor mechanisms. Semantics differ:

- MIG partitions a GPU into hardware-isolated instances according to supported profiles.
- Time-slicing multiplexes execution time; it can raise utilization without providing isolated VRAM per workload.
- Some vGPU solutions or specialized schedulers offer different sharing abstractions.

Never assume requesting `1` GPU always maps to a dedicated physical GPU if the cluster enables sharing. Understand actual isolation, VRAM limits, noisy-neighbor interference, and quotas.

## 11. Autoscaling Inference Workloads

CPU-based HPA often fails to reflect GPU load. A server can have low CPU while its GPU is saturated; conversely, GPU utilization can be low while requests stall in tokenization or data transfers.

Useful metrics:

| Workload | Useful Metrics |
|---|---|
| Vision API | Requests per replica, queue delay, images/sec, GPU utilization, and VRAM |
| Embedding service | Tokens/sec or items/sec, batch queue, GPU memory |
| LLM serving | Active sequences, pending requests, TTFT, ITL, tokens/sec, KV cache usage |
| Batch inference | Queue depth, oldest job age, completion rate, and estimated time to drain |
| Audio/video | Streams per replica, real-time factor, frames/sec, and accelerator utilization |

### Scale-Up and Scale-Down

Scale-up must account for provisioning latency:

1. HPA/custom metrics detect rising load.
2. Controller creates new Pods.
3. Node autoscaler provisions a GPU node if capacity is missing.
4. Node installs/initializes drivers and device plugins.
5. Pod downloads model weights and initializes runtime.
6. Warm-up finishes and readiness passes.
7. Load balancer begins routing traffic.

Provisioning GPU nodes and loading models can take minutes. For strict-latency APIs, keep baseline replicas or pre-warmed capacity. Scale-to-zero saves costs but induces cold starts incompatible with immediate-response SLOs.

Scale-down must drain active requests, streams, or batches. For LLM streaming, handle client disconnects and avoid cutting off in-flight generation unless resume is supported. For batch workloads, stop accepting new jobs and finish the current batch before terminating.

### Admission Control and Backpressure

When capacity runs out, the system must decide how to respond:

- Queue requests within the latency budget.
- Return `429`/`503` or `Retry-After` guidance.
- Fall back to a smaller model or CPU path if quality/SLOs allow.
- Cap max output tokens or input sizes.
- Prioritize critical requests.
- Reject over-quota requests early.

Unbounded queues turn accelerator overload into unbounded latency. Always enforce queue limits, timeouts, and load-shedding policies.

## 12. Optimizing Inference Latency and Throughput

Optimizing phase by phase prevents upgrading GPUs when the bottleneck lies elsewhere.

### Preprocessing

- Decode images/audio/video efficiently.
- Resize/normalize using vectorized libraries or accelerators when beneficial.
- Parallelize tokenization and cache safely when appropriate.
- Minimize memory copies across processes and host memory.
- Use pinned memory or asynchronous transfers when supported and proven beneficial by benchmarks.

### Model Execution

- Select appropriate precision.
- Fuse operators and optimize execution graphs.
- Use accelerator-tuned kernels/libraries.
- Tune batch sizes and sequence lengths.
- Eliminate unexpected CPU fallbacks.
- Profile kernels and memory access patterns.

### Postprocessing

- Reduce unnecessary serialization.
- Avoid copying large tensors back to CPU if only a few outputs are needed.
- Offload slow result writes to asynchronous workers where appropriate.

### Caching

Caching can serve embeddings, repeated inference outputs, or model artifacts. Cache keys must include model version, preprocessing version, and any parameters affecting results. Never cache outputs keyed on untrusted inputs if cross-tenant data leakage is possible.

## 13. Accuracy, Testing, and Model Rollouts

Performance optimizations must never compromise quality control. Every model version requires a representative validation suite.

### Pre-Release Testing

- Unit tests for preprocessing/postprocessing.
- Golden datasets comparing outputs against baselines.
- Accuracy/precision/recall or domain metrics.
- Edge cases: empty, oversized, malformed, and out-of-distribution inputs.
- Load tests with representative concurrency and payloads.
- Stress tests for VRAM, max batch size, and long contexts.
- Failure tests for timeouts, client disconnects, and accelerator resets.
- Operational tests for model reloads, rollbacks, and node replacements.

### Canary and Shadow Traffic

Canary routes a small percentage of traffic to the new model/runtime while tracking latency, errors, resource usage, and quality. Shadow traffic runs the new version in parallel without returning its outputs to users; watch extra cost and sensitive data handling. Ramp traffic gradually once metrics pass thresholds.

Model rollbacks must revert to verified artifact digests. Never roll back only the container image while forgetting weights, tokenizers, configs, or preprocessing pipelines.

## 14. Inference Observability and Bottleneck Analysis

An effective dashboard combines application and accelerator metrics:

| Group | Metrics |
|---|---|
| Request | Request rate, success/error counts, timeouts, queue depth |
| Latency | p50/p95/p99, queue wait, preprocessing, inference, postprocessing |
| Model | Model load time, version, batch size, input/output sizes |
| GPU | Utilization, VRAM used/free, memory bandwidth, temperature/power if accessible |
| Runtime | Kernel time, host-device transfers, CPU fallback, allocator fragmentation |
| LLM | TTFT, ITL, input/output tokens/sec, active sequences, KV cache |
| Capacity | Replicas, pending Pods, node counts, GPU allocatable, and quotas |
| Cost | GPU-hours, cost per successful request/image/token/job |
| Quality | Accuracy proxies, drift, validation scores, fallback rate |

### Interpreting Signals

- Low GPU utilization with high queue depth: bottleneck likely in CPU preprocessing, locks, data transfers, or scheduling.
- High GPU utilization with low throughput: inspect kernels, memory bandwidth, batch shapes, and precision.
- Near-full VRAM and OOMs: lower concurrency/context/batch size, quantize, or move to larger VRAM accelerators.
- High p99 with healthy p50: inspect queueing, long requests, batching delays, and contention.
- High CPU with low GPU: check tokenization, decoding, serialization, data loaders, and CPU fallbacks.
- High GPU with latency climbing as concurrency rises: tighten admission control or tune batch/sequence scheduling.

Never autoscale on a single metric alone. Combine load, queueing, latency, and memory headroom to avoid continuous scale-out when the bottleneck sits downstream.

## 15. Security and Data Governance for Inference

Inference may process personal data, images, voice, documents, or proprietary content. Protect inputs, outputs, models, and accelerator hosts alike.

- Authenticate callers and enforce tenant-level authorization.
- Encrypt data in transit and at rest.
- Restrict logging of inputs/outputs; redact sensitive data.
- Assign least-privilege workload identities to model servers.
- Pull models only from approved registries/artifact stores.
- Verify checksums, signatures, and provenance of model artifacts.
- Scan images/runtimes and manage host/driver patching.
- Isolate workloads when sharing GPUs; verify memory isolation guarantees.
- Purge caches or temporary data per tenant retention policies.
- Restrict outbound networking and secrets accessing model repositories.

Model artifacts are part of your software supply chain. Tampered weights can alter model behavior or exploit executable serialization formats during load. Fetch artifacts only from trusted sources, verify digests, and use safe serialization formats supported by the framework.

## 16. Design Example: GPU Image Classification API

A service receives product images and returns labels with confidence scores. Average load is 40 requests/second, peaking at 120 requests/second. SLO is p95 under 250 ms. Single-GPU benchmarking shows the model handles 80 images/second at batch size 8, though p95 degrades when queue delay exceeds 10 ms.

### Architecture

~~~mermaid
flowchart TD
    C["Client"] --> G["API Gateway"]
    G --> A["Auth + payload validation"]
    A --> L["Load balancer"]
    L --> S1["GPU inference replica 1"]
    L --> S2["GPU inference replica 2"]
    S1 --> M["Model registry / versioned weights"]
    S2 --> M
    S1 --> O["Response + metrics"]
    S2 --> O
~~~

The initial deployment runs two replicas to retain headroom and survive single-replica failures. Dynamic batching caps batch size at 8 and max queue delay at 10 ms per benchmark results. Each replica enforces concurrency limits and reports ready only after model loading and warm-up complete.

### Preliminary Capacity

If each GPU replica stably handles 80 images/second within SLO, two replicas provide roughly 160 images/second theoretical capacity under even distribution. This is not a production capacity guarantee: reserve headroom and validate peak request shapes, large images, preprocessing overhead, replica failures, and dependencies.

Autoscaling can track requests per replica, queue delay, and GPU utilization. During sustained peaks, add replicas; when load drops steadily, drain requests before scaling down. If GPU nodes take minutes to provision, maintain baseline capacity or pre-warm nodes to avoid SLO breaches.

### Testing

1. Test images across varied resolutions and formats.
2. Ramp concurrency from baseline to peak and beyond peak.
3. Measure p50/p95/p99, queue delay, and inference time separately.
4. Check VRAM usage at maximum batch size.
5. Simulate losing one replica and verify the remaining replica absorbs load.
6. Measure node/Pod scale-up and model readiness times.
7. Compare accuracy against baseline whenever changing precision or runtime.

## 17. Design Example: Streaming LLM Inference

A chat endpoint receives prompts, generates token-by-token responses, and streams them to clients. Key factors:

- Prompt lengths and output token limits.
- TTFT and inter-token latency.
- Concurrent sequences and KV cache memory.
- Prefill throughput vs. decode throughput.
- Continuous batching and scheduling fairness.
- Model weights, quantization, and tensor parallelism.
- Client disconnects, timeouts, and cancellations.

With LLMs, long requests occupy KV cache much longer than short requests. Routing solely by active request count can severely unbalance replicas. Route using active sequences, token budgets, KV cache occupancy, or estimated remaining work.

If a model exceeds one GPU's VRAM, use validated model sharding or quantization. For higher aggregate throughput, scale out replicas and distribute requests; if a single request spans multiple GPUs, verify interconnects and inter-shard communication latency.

## 18. Optimizing Inference Cost

Measure cost per valid outcome:

\[
CostPerInference =
\frac{GPUCost + CPUCost + StorageCost + NetworkCost + ServingOverhead}
{SuccessfulInferences}
\]

For LLMs, measure cost per 1,000 input/output tokens; for vision, cost per 1,000 images; for batch, cost per completed job.

Optimization levers:

- Select accelerators from benchmarks rather than peak specs.
- Tune batch sizes just enough to raise throughput without breaking latency.
- Apply quantization when accuracy stays within thresholds.
- Route simpler requests to smaller models or model cascades.
- Scale on real queue and load metrics; shed idle capacity.
- Use asynchronous/batch inference for tasks not needing instant responses.
- Cache reusable results safely without cross-tenant leaks.
- Optimize preprocessing so GPUs never stall waiting on CPUs.
- Avoid keeping oversized GPU pools provisioned when elastic pools suffice.
- Factor model load, warm-up, and idle overhead into scaling math.

A higher hourly GPU can still yield lower cost per inference if it completes far more requests or cuts total capacity holding time. Always measure cost per successful inference alongside SLOs and quality.

## 19. Common Issues and Remediation

| Symptom | Possible Cause | Remediation |
|---|---|---|
| Model fails to load | Insufficient VRAM, wrong weight precision, or unsupported runtime operator | Measure memory footprint; verify model/runtime and quantization |
| Low GPU utilization | CPU preprocessing, data transfers, or queue scheduling bottleneck | Profile per phase, reduce copies, and optimize data loaders |
| GPU OOM as concurrency rises | Activations/KV cache/batches exceed VRAM | Cap concurrency, batch/context size; quantize or increase VRAM |
| Sharp p99 latency spike | Queueing, batching delays, or long-tail requests | Cap queues, apply admission control, separate workloads by SLO |
| Throughput stalls when adding GPUs | Communication overhead, sharding, or load imbalance | Profile interconnects, topology, and parallelism strategy |
| Pod does not receive GPU | Misconfigured device plugin, node labels, drivers, or resource requests | Check node allocatable, device plugin, and Pod events |
| Pod Ready but requests error | Model still loading or shallow health check | Tie readiness to model availability and warm-up |
| High CPU, idle GPU | Tokenization/decoding or CPU fallback | Check operator coverage and preprocessing pipeline |
| New model drops accuracy | Precision/quantization or preprocessing changes | Run validation suite and roll back artifact |
| Scale-up too slow | Node provisioning, image/model downloads, and warm-up | Retain baseline, cache artifacts, or pre-warm capacity |
| High cost during low traffic | Always-on GPUs or poor batching/concurrency | Safe scale-down, async batching, and rightsizing |

## 20. Accelerator-Backed Inference Deployment Checklist

- [ ] Mode identified: online, streaming, asynchronous, or batch inference.
- [ ] Model, input/output shapes, arrival rate, and concurrency documented.
- [ ] Latency/throughput SLOs and accuracy thresholds defined.
- [ ] CPUs, GPUs, or NPUs benchmarked on representative workloads.
- [ ] VRAM/RAM sized for weights, activations, caches, workspaces, and runtime overhead.
- [ ] Precision/quantization validated for output quality.
- [ ] Runtimes and drivers verified compatible with accelerators.
- [ ] Preprocessing, transfers, inference, and postprocessing measured separately.
- [ ] Batch size, queue delay, and concurrency bounded within SLO/memory limits.
- [ ] Model versions, digests, and preprocessing versions tracked.
- [ ] Kubernetes device plugins, node pools, and resource requests verified.
- [ ] Readiness passes only after model loading and warm-up finish.
- [ ] Autoscaling uses metrics suited to accelerator workloads.
- [ ] Admission control, backpressure, and queue limits implemented.
- [ ] Scale-in drains active requests/streams/jobs before termination.
- [ ] GPU faults, OOMs, node replacements, and model rollbacks tested.
- [ ] Inputs/outputs, model artifacts, secrets, and logs secured.
- [ ] Dashboards track latency, throughput, VRAM, utilization, quality, and cost.
- [ ] Cost per successful inference calculated and SLOs verified at peak.

## 21. Practice Exercise

A team deploys an image classification model on Kubernetes. The model has 5 billion parameters with 16-bit weights. Each GPU has 24 GB VRAM. Running one replica, the model loads successfully but leaves little free VRAM; increasing batch size from 4 to 16 boosts throughput, yet some p99 requests breach SLO and the container occasionally OOMs. Node CPU utilization sits around 35%, while GPU utilization regularly exceeds 90%.

1. Estimate the theoretical memory size of the model weights.
2. Why does a successful model load not mean you can increase batch size arbitrarily?
3. Which VRAM consumers besides weights must be accounted for?
4. Propose how to benchmark batch size and concurrency to find the optimal balance.
5. Should you scale up node CPUs first? What data is needed to decide?
6. Suggest two ways to reduce cost per inference while preserving accuracy and the p99 SLO.

Hint: 5 billion parameters at 2 bytes/parameter take roughly 10 GB for weights, while runtime, activations, workspaces, and caches require additional memory. Larger batches grow activations and can add queueing delay; OOMs can strike before GPU compute maxes out. Measure VRAM across batch/concurrency combinations, p95/p99 latency, queue delay, throughput, and accuracy. Increase CPU only if profiling shows preprocessing/tokenization or host-side pipelines are the bottleneck. Consider validated quantization, bounded dynamic batching, smaller models, or preprocessing optimization.

## Conclusion

Designing accelerator-backed inference workloads begins with the model, input patterns, SLOs, and real bottlenecks. GPUs/NPUs boost throughput only when backed by adequate VRAM, compatible runtimes, efficient data feeding, and an aligned serving architecture. Batching, concurrency, model parallelism, and autoscaling must be tuned together with latency, output quality, and memory headroom. Measuring end-to-end, testing on representative load, securing model artifacts, and optimizing cost per successful inference ensure stable production performance.
