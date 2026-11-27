# Evaluating Machine Learning Model Serving and Inference Architectures

A machine learning model with strong accuracy in experiments is not guaranteed to perform well in production. As request volume grows, input distributions shift, GPUs become scarce, features fall out of sync, or new models roll out, the system can suffer rising latency, inconsistent predictions, runaway costs, or an inability to roll back. Evaluating a machine learning serving architecture therefore requires examining the entire path—from data, features, and model artifacts to runtime inference, application integration, monitoring, and release workflows.

**Model serving** refers to the infrastructure and software that accept inference requests, load models, prepare inputs, execute the model, and return outputs under a published contract. **Inference** is the act of running a trained model on new data to produce predictions or outputs. The two concepts are related but distinct: inference can run inside an application, within a batch job, inside a stream processor, or on an edge device; model serving typically describes a dedicated service or runtime purpose-built for inference.

This lesson belongs to the **Data Platform** chapter of the **CLOUD_ARCHITECTURE** module. Its goal is evaluating whether an architecture satisfies business and technical requirements when deploying models in the cloud. Key areas include inference workloads, data and features, model artifacts, CPU/GPU compute, latency and throughput, scaling, reliability, security, observability, cost, and trade-offs from a Well-Architected perspective.

## 1. Starting from Business Requirements and Inference Workloads

Never choose Kubernetes, GPUs, or a model serving framework before understanding the workload. The same model can be served in very different ways depending on interactivity and when results are needed.

For example, a booking platform uses ML for three capabilities:
- Recommending suitable rooms while a user searches.
- Ranking search results based on behavior and context.
- Batch-scoring booking risk for operations analysis.

Web recommendations need fast responses while the user is actively interacting. Batch risk scoring can run hourly or daily. Forcing both into the same deployment and scaling policy wastes resources or misses SLOs.

### 1.1. Questions to Gather

| Requirement Area | Evaluation Questions | Architectural Impact |
|---|---|---|
| Use case | Which decision or user experience does the model drive? | Defines output contract, criticality, and fallbacks |
| Inference mode | Online, batch, streaming, or edge? | Selects endpoints, queues, jobs, or on-device runtimes |
| Traffic | Average, peak, burst, and seasonal request rates? | Capacity, autoscaling, queues, and quotas |
| Latency | Maximum acceptable p50/p95/p99? | Runtime, networking, feature lookups, and batching |
| Throughput | Requests/second or records/hour? | Replicas, workers, GPUs, and partitions |
| Availability | Required service availability? | Multi-zone, failover, and dependency design |
| Output quality | Precision/recall thresholds, ranking quality, or business KPIs? | Model validation, monitoring, and rollback |
| Freshness | How fresh must the model and features be? | Retraining, feature pipelines, and deployment cadence |
| Data sensitivity | Do inputs/outputs contain PII or sensitive data? | Encryption, access control, retention, and auditing |
| Cost | Budget per request, per prediction, or per month? | Model size, accelerators, batching, and scale-to-zero |
| Failure behavior | How does the business proceed when the model/feature service fails? | Fallbacks, degradation, and retry policies |

### 1.2. Building a Workload Profile

A workload profile should record at least:
- Normal and peak request rates.
- Request and response payload sizes.
- Number of features fetched and input preparation cost.
- Model compute duration per instance type.
- Concurrency levels and batch sizes.
- Cache hit rates if caching features or predictions.
- Error and timeout rates across dependencies.
- Traffic ramp-up and ramp-down patterns.
- Model size, memory footprint, and required compute type.

If these numbers are unknown, benchmark a prototype or run load tests. Never extrapolate production capacity from a developer laptop benchmark, since hardware, networking, batching, preprocessing, and concurrency differ dramatically.

## 2. Selecting the Right Inference Pattern

### 2.1. Online Synchronous Inference

Clients or backend services call an inference endpoint and wait for the result within the same request-response cycle.

~~~mermaid
sequenceDiagram
    actor U as User
    participant API as Booking API
    participant F as Feature service
    participant M as Model endpoint
    U->>API: Search request
    API->>F: Fetch required features
    F-->>API: Feature vector
    API->>M: Predict
    M-->>API: Score / ranking
    API-->>U: Search response
~~~

Suitable when results immediately shape live experiences or real-time decisions. Pros include direct synchronous responses and simple HTTP/gRPC integration. The trade-off is that model latency and every dependency sit on the critical path: if the feature store, model endpoint, or network slows down, the business request slows down too.

Evaluate:
- Total latency across gateway, auth, feature lookup, preprocessing, model compute, and response serialization.
- End-to-end timeouts and tighter per-dependency timeouts.
- Fallbacks when the model fails to respond.
- Concurrency, queueing, and tail latency.
- Never infinitely retry short-deadline requests.

### 2.2. Batch Inference

Batch inference scores a dataset on a schedule or event trigger, writing predictions to storage or a data warehouse for downstream consumption later.

~~~mermaid
flowchart LR
    DATA[("Data lake / warehouse")] --> JOB["Scheduled inference job"]
    JOB --> MODEL["Load model artifact"]
    MODEL --> PRED["Batch predictions"]
    PRED --> OUT[("Prediction table / object store")]
    OUT --> REPORT["Dashboard / downstream system"]
~~~

Suited for customer propensity scoring, demand forecasting, segmentation, daily risk scoring, or precomputed recommendations. No per-request endpoint is needed.

Pros:
- Processes massive volumes efficiently with batching.
- Runs on scheduled compute that shuts down upon completion.
- Easy to rerun a partition or date range when workflows track lineage.
- Isolates batch costs from online services.

Trade-offs:
- Results carry schedule-driven latency.
- Large jobs can run long and require checkpointing.
- Requires preventing duplicate outputs on retries.
- Must handle late-arriving data, schema changes, and backfills.

Evaluation requires explicit completion deadlines (data-to-result SLAs), resumability, idempotency, and input/output record count reconciliation.

### 2.3. Streaming Inference

Streaming inference evaluates events continuously from an event bus or stream processor. For example, updating risk scores whenever booking, payment, or cancellation events occur.

~~~mermaid
flowchart LR
    P["Producers"] --> E[("Event stream")]
    E --> S["Stream processor"]
    S --> F["Feature enrichment"]
    F --> M["Model inference"]
    M --> R[("Scored events / state store")]
    R --> D["Consumers"]
~~~

Suited when near-real-time scores are needed without blocking the originating request. Trade-offs involve ordering, duplicates, late events, checkpointing, state management, backpressure, and replay. Clarify whether inference is idempotent, whether feature windows use event time or processing time, and how prior predictions update.

### 2.4. Edge Inference

Models are packaged and run directly on user devices, gateways, or servers near where data originates—for example, object-detecting cameras or mobile apps classifying content offline.

Pros:
- Eliminates cloud round-trips.
- Continues operating under intermittent connectivity.
- Raw data stays on device, cutting data transfer.

Trade-offs:
- Heterogeneous hardware with tight resource constraints.
- Managing model rollouts, versioning, and rollbacks across fleets.
- Models can be extracted or reverse-engineered on unprotected devices.
- Harder to observe thoroughly and patch rapidly during incidents.

Edge fits when latency, privacy, offline operation, or bandwidth savings outweigh centralizing inference in the cloud.

### 2.5. Comparing Inference Modes

| Mode | Result Turnaround | Common Interfaces | Strengths | Primary Risks |
|---|---|---|---|---|
| Online | Milliseconds to seconds per SLO | HTTP/gRPC | Instant interaction | Tail latency and critical-path dependencies |
| Batch | Scheduled / minutes / hours / days | Jobs, workflows, tables/objects | High throughput and batch efficiency | Stale results, retries/backfills |
| Streaming | Near real-time | Event streams | Continuous processing, decoupled producer-consumer | Ordering, duplicates, late events, backpressure |
| Edge | Immediate on device or gateway | Local SDK/runtime | Ultra-low latency, offline support, low transfer | Fleet rollouts, hardware limits, model protection |

You do not have to pick only one mode. A platform can use online inference for ranking, batch inference for candidate generation, and streaming for feature updates.

## 3. Logical Model Serving Architecture

A production inference service involves more than calling `predict()`:

~~~mermaid
flowchart TB
    CLIENT["Application / API client"] --> GW["API gateway / authentication"]
    GW --> VALID["Request validation"]
    VALID --> FEAT["Feature retrieval / preprocessing"]
    FEAT --> SERVE["Model serving runtime"]
    REG[("Model registry / artifact store")] --> SERVE
    SERVE --> POST["Postprocessing / policy rules"]
    POST --> RESP["Response"]
    SERVE -. "Metrics / traces / logs" .-> OBS["Observability"]
    FEAT -. "Feature freshness / errors" .-> OBS
    GW -. "Access / quota" .-> OBS
~~~

Core components:

1. **Ingress/API layer:** accepts requests, authenticates callers, enforces quotas/rate limits, and routes traffic.
2. **Input validation:** verifies schemas, data types, payload size bounds, and valid ranges.
3. **Feature retrieval:** fetches online features or executes preprocessing.
4. **Model runtime:** loads artifacts, executes inference, and manages concurrency.
5. **Postprocessing:** maps raw scores to business contracts and applies approved thresholds or policy rules.
6. **Response/output:** returns synchronous responses or writes predictions downstream.
7. **Observability:** measures latency, throughput, errors, resource usage, feature/model versions, and post-deployment quality.
8. **Model registry/artifact store:** manages artifacts, metadata, lineage, and deployment approval status.

Not every use case needs separate microservices for each box. A small model using static features can run in-process inside the application. Splitting into multiple services enables independent scaling and ownership at the expense of network hops, cost, and extra failure modes.

## 4. Data, Features, and Training-Serving Consistency

A leading cause of degraded production models is features at inference time diverging from features used during training—known as **training-serving skew**.

For example, a room-ranking model is trained on:
- User cancellation rate over 30 days.
- Average room price over 7 days.
- Search count over 24 hours.
- Latest review score.

If during inference the backend computes user cancellation rate over a 7-day window instead of 30 days, the model receives shifted inputs even though the schema looks identical.

### 4.1. Feature Pipelines

~~~mermaid
flowchart LR
    SRC["Operational data / events"] --> ETL["Ingestion and transformation"]
    ETL --> OFF[("Offline feature store / lake")]
    ETL --> ON[("Online feature store")]
    OFF --> TRAIN["Training pipeline"]
    TRAIN --> MODEL["Model artifact"]
    ON --> SERVE["Online serving"]
    MODEL --> SERVE
~~~

Offline feature stores power training and historical backfills. Online feature stores serve low-latency per-request lookups. When maintaining both, unify feature definitions, transformation logic, and lineage.

### 4.2. Feature Evaluation Questions

- From which sources are features derived, and who owns them?
- Are feature transformations versioned?
- Do offline and online paths share code, or is equivalence verified?
- Do timestamps and event-time windows share identical semantics?
- How are missing or null features handled?
- What is the maximum tolerable feature staleness?
- Can point-in-time historical lookups prevent training data leakage?
- Are tenant boundaries and access controls enforced in feature keys?

### 4.3. Feature Freshness and Fallbacks

When the online feature store lacks fresh values, define explicit policies:
- Use the most recent value if within the freshness budget.
- Use a default validated during model evaluation.
- Query a secondary source if latency permits.
- Degrade to a simpler model or heuristic.
- Reject specific use cases if mandatory features are unavailable.

Never blindly impute `0` for every missing feature. Zero may be a meaningful domain value distinct from missing. Use explicit missingness indicators, model-validated defaults, or explicit fail-closed behavior.

## 5. Model Artifacts, Registry, and Reproducibility

Deployed models must be managed as versioned artifacts—never arbitrary files copied off a developer laptop.

A model package should link to:
- Model name and version.
- Framework/runtime and dependency versions.
- Input/output schemas.
- Feature definitions and versions.
- Training dataset references and data lineage.
- Code/commit SHA, pipeline run ID, and hyperparameters.
- Evaluation metrics and test reports.
- Model signature and checksum.
- Licenses, provenance, and pretrained base model origins if applicable.
- Approval state: candidate, staging, production, deprecated, or revoked.

The model registry manages metadata and lifecycle state; the artifact store holds actual weights, containers, or packages. A registry alone does not guarantee safety or reproducibility unless data sources, code, and dependencies are recorded faithfully.

### 5.1. Registry and Promotion Flow

~~~mermaid
flowchart LR
    TRAIN["Training pipeline"] --> EVAL["Evaluation / validation"]
    EVAL --> CAND["Candidate model"]
    CAND --> APPROVE["Review / approval"]
    APPROVE --> STAGE["Staging deployment"]
    STAGE --> PROD["Production promotion"]
    PROD --> MON["Monitor"]
    MON -->|"Drift / regression"| ROLLBACK["Rollback / disable"]
~~~

Only models passing quality, security, compatibility, and operational checks should promote. Approved model versions and artifact digests must be immutable; mutating an artifact without bumping its version breaks rollbacks and audits.

### 5.2. Model Signatures and Input Contracts

A model signature specifies input/output names, shapes, types, or schemas. Serving gateways/runtimes should validate requests against the published contract. Treat input schema changes like API changes—evaluating consumers, feature pipelines, and model compatibility.

Never let callers pass arbitrary model artifact names or file paths. Server-side policies and the registry must control model routing.

## 6. Choosing Compute: CPU, GPU, and Accelerators

Not every model needs a GPU. Base compute selection on benchmarks with real models, batch sizes, input shapes, concurrency, and SLOs.

| Compute Type | Typically Suited For | Trade-Offs |
|---|---|---|
| CPU | Small models, tree-based models, preprocessing, low-throughput inference | May lack throughput for large tensor models |
| GPU | Neural networks/LLMs, massive parallel math, high throughput | Cost, memory limits, cold starts, utilization tuning |
| Specialized accelerators | Workloads tuned for NPUs/TPUs or custom silicon | Runtime compatibility, porting effort, provider lock-in |
| Edge devices | Local/offline inference or ultra-low latency | Scarce resources, fleet updates, device security |

### 6.1. Measuring Compute Efficiency

Key metrics:
- Predictions/second or requests/second.
- p50/p95/p99 inference latency.
- GPU/CPU utilization.
- Accelerator memory and peak memory usage.
- Effective batch size.
- Model load and cold-start times.
- Queueing and resource wait times.
- Cost per 1,000 or 1 million predictions.

High GPU utilization is not always good—it can coincide with ballooning queue latency. Low utilization may stem from tiny models, small batches, preprocessing bottlenecks, or over-provisioned GPU replicas.

### 6.2. Batching and Dynamic Batching

Batching groups multiple requests into one model execution pass, boosting accelerator throughput. Dynamic batching accumulates requests over a brief wait window.

Trade-offs:
- Larger batches raise compute efficiency but add queueing latency waiting for batches to fill.
- Smaller batches cut wait times but underutilize accelerators.
- Varying input shapes complicate batching.
- One slow or oversized request can delay co-batched requests without careful scheduling.

Tune max batch size and max queue delay directly against SLOs. Never increase batching solely for throughput if p99 latency breaches business limits.

## 7. Measuring Latency, Throughput, and SLOs

Total online latency extends well beyond model execution time:

\[
T_{total} = T_{gateway} + T_{auth} + T_{feature} + T_{preprocess} + T_{queue} + T_{model} + T_{postprocess}
\]

Illustrative targets:
- End-to-end p95 under 150 ms.
- p99 under 300 ms.
- Error rate below agreed threshold.
- Peak throughput with burst headroom.
- Feature freshness within defined bounds.

Assign a latency budget to each stage. If model compute takes 20 ms while feature lookup takes 120 ms, buying faster GPUs will barely improve user experience.

### 7.1. SLOs and Error Budgets

SLOs should capture user-perceived outcomes, not merely container health:
- Percentage of valid requests answered within deadline.
- Percentage of predictions returning valid schema.
- Percentage of requests served by approved model versions.
- Freshness of features or prediction outputs.
- Batch jobs finishing before deadline with full coverage.

Error budgets govern model release velocity. If errors or latency consume the budget, pause rollouts to restore reliability.

### 7.2. Tail Latency

A fast p50 is insufficient if p99 spikes. Tail latency typically degrades due to:
- Slow feature lookups on a hot partition.
- GPU contention or queueing.
- Cold starts and model loading.
- Slow autoscaling reactions.
- GC pauses, memory pressure, or noisy neighbors.
- External dependency throttling.

Measure percentiles across the entire request path, segmented by model version, instance type, region, and input class.

## 8. Scaling and Capacity Planning

### 8.1. Horizontal Scaling

Adding replicas handles higher request volume when requests are independent and runtimes parallelize cleanly. Check:
- Startup and model loading times.
- Artifact size and download speed from the registry.
- GPU/accelerator provisioning time.
- Readiness probes: accept traffic only after models, features, and runtimes finish loading.
- Whether in-process state prevents arbitrary load balancing.
- Which autoscaling signal drives scaling: CPU, GPU, concurrency, queue depth, or latency?

CPU utilization alone often misses GPU bottlenecks. Queue depth, concurrency, or accelerator metrics frequently provide better signals depending on the runtime.

### 8.2. Vertical Scaling

Larger instances provide more memory, CPU, or GPU capacity—useful for large models that cannot split easily or to reduce replica counts. Trade-offs include upper hardware limits, per-node cost, wider blast radius, and cloud capacity availability.

### 8.3. Scale-to-Zero

For dev workloads, batch jobs, or rarely hit endpoints, scale-to-zero saves money. However, the first request pays startup and model-load penalties. Unsuitable for strict latency SLOs unless backed by warm pools, minimum replicas, or fast fallbacks.

### 8.4. Capacity Planning

Estimate capacity from benchmarks:
1. Measure throughput per replica at target latency.
2. Identify peak request rates and required headroom.
3. Calculate replicas needed for peak plus failover margin.
4. Simulate losing a replica or availability zone to verify post-failure capacity.
5. Measure autoscale time from trigger to ready.
6. Verify GPU/accelerator quotas and provisioning latency.
7. Load test both warm and cold models.
8. Periodically reconcile actual demand against spend.

Never assume autoscaling is instantaneous. If traffic bursts faster than new replicas initialize, maintain baseline capacity, queues, or admission control.

## 9. Reliability and Failure Handling

Model serving spans many dependencies: gateways, identity, feature stores, registries/artifact stores, container registries, networking, runtimes, and downstreams. Specify failure behavior for each:

| Failure | Impact | Mitigation |
|---|---|---|
| Model process crash | Requests fail | Health checks, restarts, multiple replicas, safe rollouts |
| Artifact store unreachable | New replicas cannot load models | Cache vetted artifacts, warm deployments, keep running versions |
| Feature store slow | End-to-end latency spikes | Tight timeouts, policy-governed feature caches, defaults/fallbacks |
| GPU quota exhausted | Cannot scale out | Capacity reservations, CPU fallback if quality/SLO allows, queues |
| Model emits NaN/invalid outputs | Corrupt predictions | Output validation, per-model circuit breakers, fallbacks |
| Model version regression | Business KPIs drop | Canaries, traffic splits, rapid rollbacks |
| Network partition | Inference dependencies unreachable | Multi-zone redundancy, timeouts, bounded retries |
| Traffic burst | Growing queues and p99 spikes | Autoscaling, admission control, rate limiting, graceful degradation |

### 9.1. Fallback Strategies

Fallbacks must be approved by product and model owners. Examples:
- Ranking model fails → return popularity- or rule-based ranking.
- Recommendation fails → display curated default catalog.
- Risk score fails → route transactions to manual review rather than auto-approving.
- Classification model fails → return "undetermined" for downstream workflow handling.

Never apply automatic fallbacks blindly to every decision. In sensitive domains, failing open increases fraud/safety risk, while failing closed harms legitimate users. Distinguish fail-open vs. fail-closed by business context.

### 9.2. Timeouts and Retries

Set an end-to-end deadline; every downstream call gets a timeout smaller than the remaining budget. Retry only transient errors with bounded attempts and exponential backoff/jitter. Never stack uncoordinated retries across gateways, applications, feature clients, and model clients without a retry budget, or a single request amplifies into a retry storm.

While inference is mostly read/compute, downstream side effects or prediction logging require idempotency if clients retry.

## 10. Model Rollouts: Canary, Shadow, and Rollback

New models can behave differently even when the API contract stays identical. Rollouts must validate both technical health and prediction quality.

### 10.1. Shadow Deployment

Production requests hit the live model to serve users, while mirrored requests go asynchronously to the candidate model without affecting user responses. Compare outputs, latency, resource consumption, and score distributions.

Strip or mask sensitive data as needed, prevent side effects, and ensure shadow traffic never overloads shared dependencies.

### 10.2. Canary Rollout

Route a small slice of live traffic to the new model, watch errors, latency, and business metrics, then ramp gradually if criteria hold. Support traffic splitting by tenant, request type, or cohort rather than a single global percentage when groups differ significantly.

### 10.3. A/B Testing

A/B tests measure real business impact across assigned user cohorts. Design experiments carefully to prevent leakage, sample ratio mismatches, and bias while tracking meaningful metrics. A/B tests measure user outcomes; they do not replace load testing or security testing.

### 10.4. Rollback

Safe rollbacks require:
- Previous model artifacts remain available and verified.
- Runtimes remain compatible with older artifacts.
- Feature schemas still support the older model.
- Traffic routing switches back rapidly.
- Policies exist for handling predictions/state already emitted by the reverted model.
- Registry logs which model version was rolled back and why.
- Ability to disable a model or route without redeploying the entire application.

Never delete previous artifacts immediately after promotion while still inside the rollback window.

## 11. Security and Governance for Models and Data

Model serving handles PII, prompts, images, text, payment data, or sensitive features. Protect inputs, outputs, artifacts, and execution privileges.

### Identity and Authorization

- Every caller service uses a dedicated identity—never a shared admin credential.
- Only authorized principals can invoke model endpoints.
- Model registries/artifact stores separate publish, approve, deploy, and read permissions.
- Training pipelines do not automatically hold production deployment privileges.
- Serving runtimes should not modify registries or IAM unless strictly necessary.
- Retrieve secrets via workload identities/secrets managers; never bake keys into container images.

### Data Protection

- Encrypt data in transit and at rest.
- Minimize inputs sent to inference services.
- Redact sensitive fields from logs and traces.
- Bound retention of logged request/response samples.
- Isolate tenants and namespaces across caches and feature stores.
- Verify data residency and regulatory compliance.

### Model Artifacts and Supply Chain

- Scan dependencies and container images.
- Verify artifact origins, checksums, and signatures.
- Restrict who can upload or promote models.
- Pin dependency/runtime versions and generate SBOMs where required.
- Never load untrusted model artifacts when serialization formats can execute arbitrary code.
- Track licenses and provenance for pretrained models and training datasets.

### Model Abuse and Output Controls

Depending on use case, guard endpoints against prompt injection, adversarial inputs, model extraction, abuse, and inference data leakage. Enforce payload size/rate limits, authorization, input validation, output policy checks, and anomaly monitoring. For generative models, add use-case guardrails, output filtering, and harmful-content handling workflows.

## 12. Observability: Infrastructure, Model, and Business

Monitoring CPU, memory, and HTTP status codes alone is insufficient. A model can return `200 OK` while emitting garbage predictions from stale features.

### 12.1. Three Observability Layers

**Infrastructure/Runtime**
- Ready replicas, restarts, CPU/GPU utilization, and memory.
- Queue depth, concurrency, and throttling.
- Artifact load times, cold starts, and network errors.
- Autoscaling events, quotas, and node capacity.

**Serving/API**
- Request counts and p50/p95/p99 latency.
- Timeouts, 4xx/5xx responses, and validation failures.
- Input sizes, batch sizes, and model versions.
- Feature lookup latency, miss rates, and staleness.
- Inference compute time and postprocessing time.

**Model/Business**
- Prediction and score distributions.
- Null/NaN/out-of-range output rates.
- Feature drift and data drift.
- Model quality once ground truth arrives.
- Business KPIs, conversions, false positive/negative rates, or ranking quality.
- Bias/fairness metrics where relevant to goals and regulations.

Ground truth is not always immediate. For risk or churn models, true labels may arrive days or months later. Track proxy metrics and preserve prediction lineage so offline evaluation can run once labels arrive.

### 12.2. Data Drift and Concept Drift

- **Data drift:** input/feature distributions shift relative to training/evaluation baselines.
- **Concept drift:** the relationship between features and the target shifts over time, degrading model quality even if input distributions barely change.

Drift alerts alone do not prove model degradation. Pair them with ground truth, domain metrics, and human review. Seasonal shifts may be benign drift; blind automated retraining can actually worsen quality.

### 12.3. Trace Correlation

Propagate correlation/trace IDs across business APIs, feature lookups, and inference endpoints to break down latency per hop. Never log raw sensitive payloads. Record model versions, feature schema versions, and deployment revisions as governed metadata.

## 13. Model Lifecycle Management and MLOps

Model serving cannot operate in isolation from model development. Connect training, evaluation, registry, deployment, and monitoring.

~~~mermaid
flowchart LR
    DATA["Data ingestion / quality"] --> FEAT["Feature engineering"]
    FEAT --> TRAIN["Training"]
    TRAIN --> EVAL["Evaluation / validation"]
    EVAL --> REG[("Model registry")]
    REG --> DEPLOY["Deploy pipeline"]
    DEPLOY --> SERVE["Model serving"]
    SERVE --> MON["Monitor predictions / drift"]
    MON --> REVIEW["Review / retrain decision"]
    REVIEW --> DATA
~~~

A mature MLOps lifecycle includes:
1. Data validation and lineage.
2. Versioned code, dataset/feature definitions, and training configs.
3. Reproducible training (or explicitly documented reproducibility bounds).
4. Evaluation on appropriate holdouts or time-based splits.
5. Model approvals and registry tracking.
6. Image/artifact scanning and deployment gates.
7. Canary, shadow, and rollback workflows.
8. Monitoring infrastructure, drift, and business quality.
9. Reviewed retraining schedules/triggers.
10. Deprecation and deletion of old models/artifacts per retention policies.

Never trigger automatic retraining purely because a drift metric crossed a threshold. Investigate root causes, label quality, data pipelines, and promotion gates first. Every retrained model must pass the exact same validation gates before entering production.

## 14. Cost and Resource Efficiency

ML serving costs span:
- CPU/GPU/accelerator uptime.
- RAM, storage, and model artifact egress.
- Online feature stores/caches and databases.
- Cross-region/cross-zone network traffic.
- Logs, traces, metrics, and prediction archives.
- Batch jobs, training pipelines, and data processing.
- Idle capacity maintained to meet latency SLOs.
- Third-party model API fees or licenses.

### Unit Economics Metrics

Track:
- Cost per 1,000 predictions.
- Cost per successful request.
- GPU-seconds per prediction.
- Cost per batch record.
- Cost of idle replicas.
- Cost per tenant/use case.
- Fallback and retry rates.

Optimizations include quantization, model distillation, pruning, compilation, dynamic batching, multi-model sharing, scale-to-zero for batch, spot/preemptible compute for retryable jobs, or running smaller models on CPUs.

Each optimization can affect quality, latency, or complexity. Re-measure quality afterward; never sacrifice precision/recall or reliability just to cut cost unless the business explicitly accepts the trade-off.

## 15. Well-Architected Architecture Evaluation

| Pillar | Evaluation Questions | Signals / Evidence |
|---|---|---|
| **Operational Excellence** | Are model registry, runbooks, ownership, promotion, and rollbacks in place? | Model lineage, deployment logs, release checklists |
| **Security** | Are identity, data access, artifact provenance, and PII controlled? | IAM reviews, encryption, artifact scans, audits |
| **Reliability** | Do fallbacks, multi-zone setups, and recovery cover model/feature/registry failures? | Failure injection, SLOs, rollback drills |
| **Performance Efficiency** | Are latency budgets, batching, compute, and feature lookups meeting targets? | p95/p99, throughput, GPU utilization |
| **Cost Optimization** | Are resources right-sized and scaled to demand? | Cost per prediction, idle capacity, utilization |
| **Sustainability** | Are wasted compute, obsolete models/artifacts, and excessive telemetry eliminated? | Lifecycle policies, scale-to-zero, retention reviews |

### Common Trade-Offs

**GPU vs. CPU:** GPUs boost throughput for large neural networks but carry higher cost and cold-start overhead. CPUs suit smaller or tree-based models and preprocessing, though high volume may require many replicas. Decide via end-to-end benchmarks.

**Online vs. Batch:** Online minimizes user wait times but demands strict availability and latency SLOs. Batch is cheaper and efficient for non-immediate tasks while accepting delayed outputs.

**Real-Time Feature Lookup vs. Precomputed Features:** Real-time improves freshness at the cost of network dependencies; precomputation cuts latency and load with staler features. Combine real-time features for fast-changing signals with precomputed features for slower ones.

**Shared Endpoint for All Models vs. Dedicated Endpoints:** Sharing lowers infrastructure overhead but risks noisy neighbors and coupled scaling; isolating endpoints improves blast radius control at higher cost and ops effort.

**Scale-to-Zero vs. Minimum Replicas:** Scale-to-zero saves idle spend while risking SLO-breaking cold starts. Minimum replicas add fixed cost to guarantee stable latency.

**Canary vs. Full Rollout:** Canaries shrink blast radius but require strong telemetry and routing. Full rollouts are simpler yet expose 100% of traffic before catching regressions.

## 16. Model Serving Architecture Review Process

Follow these steps during design reviews:

1. **Describe the business decision:** what outputs does the model generate, who consumes them, and what happens when predictions are wrong?
2. **Select inference modes:** online, batch, streaming, edge, or hybrid.
3. **Define SLOs:** percentile latency, throughput, availability, freshness, and output correctness.
4. **Diagram request/data flows:** gateways, identity, features, model runtime, artifacts, outputs, and telemetry.
5. **Audit data/features:** lineage, schemas, training-serving consistency, missing values, and drift.
6. **Audit model lifecycle:** registry, signatures, versioning, approvals, artifact provenance, and rollbacks.
7. **Benchmark compute:** CPU/GPU, batching, concurrency, memory, cold starts, and cost.
8. **Review scaling:** autoscaling signals, quotas, warm capacity, bursts, zone failures, and queues.
9. **Review failure modes:** dependency outages, invalid model outputs, timeouts, fallbacks, and retry budgets.
10. **Review security:** identity, tenant isolation, encryption, data retention, and model supply chain.
11. **Design observability:** infrastructure, serving, features, model quality, and business metrics.
12. **Calculate unit economics:** cost per prediction/use case plus idle and recovery overhead.
13. **Validate:** load tests, failure injection, shadow/canary rollouts, contract tests, and rollback drills.
14. **Record ADR:** chosen design, rejected alternatives, rationale, trade-offs, owners, and review triggers.

### Concise Architecture Checklist

| Item | Passes When |
|---|---|
| Workload profile | Traffic, payloads, latency, and freshness are measured or reasonably estimated |
| Inference mode | Online/batch/stream/edge matches business timing requirements |
| Feature consistency | Training-serving schemas and transforms are versioned and verified |
| Model artifacts | Registry, provenance, checksums, and approvals are explicit |
| Runtime capacity | Benchmarked on production-like hardware with headroom |
| SLOs | Latency, error, availability, and freshness targets have dashboards |
| Resilience | Timeouts, bounded retries, fallbacks, multi-zone, or recovery exist |
| Releases | Canary/shadow, model versioning, and rollbacks are supported |
| Security | Identity, least privilege, encryption, and data handling are clear |
| Operations | Owners, runbooks, alerts, and incident workflows exist |
| Cost | Unit costs and idle capacity are measured |
| Governance | Lineage, retention, approvals, and periodic reviews are active |

## 17. Illustrative ADR — Serving a Ranking Model for the Booking API

> **Context:** The Booking API must rank search results while users wait for the page to load. Traffic peaks hourly, and the model relies on behavioral and pricing features. New models release every few weeks.
>
> **Option A:** Embed the model directly inside the Booking API. Fewer network hops and simpler single-artifact deployment, but model scaling is coupled to the API, container images bloat, and independent rollbacks are hard.
>
> **Option B:** Separate model serving into its own endpoint; the backend fetches features and calls inference over a private network. Allows independent scaling and rollouts, at the cost of extra network hops, a service dependency, and dedicated runtime costs.
>
> **Illustrative Decision:** Choose Option B if benchmarks confirm end-to-end p95 meets SLO and traffic justifies independent model management. Maintain minimum warm capacity to prevent cold starts; enforce timeouts/fallbacks on feature lookups; pin model versions in deployment metadata.
>
> **Resilience:** If the endpoint fails or misses its deadline, return a product-owner-approved rule/popularity ranking—never block search entirely.
>
> **Release:** Shadow the candidate model, compare scores and latency, run cohort-based canary traffic, then ramp up; retain the prior model for rollback.
>
> **Security:** Private endpoint, dedicated workload identity for Booking API, scoped read access to features and model artifacts, and no raw PII in logs.
>
> **Verification:** Peak load tests, p95/p99, GPU/CPU utilization, feature freshness, fallback rates, canary business KPIs, tenant isolation, and rollback drills.
>
> **Review Triggers:** Traffic drops significantly, the model shrinks, and network hops become the dominant bottleneck—at which point revisit in-process inference or batch/precomputed ranking.

## 18. Practice Exercise: Choosing an Inference Architecture for a Booking Platform

The platform requires three ML capabilities:
1. Fast-response search result ranking.
2. Daily regional demand forecasting.
3. Risk scoring when a booking is created to route suspicious transactions to manual review.

The team proposes serving all three on one shared GPU endpoint. Models and features sit in the same bucket; the endpoint returns `200` whenever the runtime is up. There are no fallbacks, model versioning, drift monitoring, or cost-per-prediction metrics yet.

**Tasks:**
1. Select distinct inference modes for ranking, demand forecasting, and risk scoring.
2. Define latency, throughput, availability, and freshness SLOs per use case.
3. Diagram data/feature/model flows and identify sources of truth.
4. Evaluate whether to share one GPU endpoint or split deployments.
5. Design fallbacks when ranking or risk models fail.
6. Propose a registry, artifact versioning, approvals, canary rollouts, and rollbacks.
7. Define infrastructure, serving, feature, and model quality metrics.
8. Specify security controls for inputs, outputs, model artifacts, and tenants.
9. Estimate cost per prediction and propose compute optimizations.
10. Create a test plan covering burst traffic, feature outages, GPU quotas, and model regressions.

### Solution Guidance

- Ranking is online inference because it sits on the search critical path; enforce p95/p99 latency, warm capacity, and a fallback ranker.
- Demand forecasting suits scheduled batch inference; write versioned, timestamped outputs for dashboards with partition-level retry/backfill.
- Risk scoring can be online or streaming depending on whether decisions block booking confirmation; if synchronous, enforce strict deadlines and fall back to manual review/policy rather than auto-approving on model errors.
- Do not default to one shared GPU endpoint. Benchmark each model; use CPUs for lightweight models or batch jobs where effective, and isolate endpoints when SLOs, resource profiles, or blast radii differ.
- The model registry tracks artifacts, schemas, feature versions, lineage, and evaluations; deployments pull only approved versions.
- Run shadow/canary before full rollout; preserve older models and feature compatibility for rollbacks.
- Monitor p95/p99, throughput, errors, GPU/CPU/memory, queue depth, cold starts, feature freshness, drift, score distributions, and business KPIs.
- Enforce workload identities, private endpoints, encryption, least privilege, input validation, log redaction, and retention limits.
- Track cost per 1,000 predictions, utilization, idle replicas, feature lookup costs, and egress; apply batching or quantization only after measuring quality and latency impacts.
- Failure tests must verify fallbacks and end-to-end business behavior—not just HTTP status codes.

### Self-Check Questions

1. Why is high model accuracy in offline evaluation insufficient to prove a strong production architecture?
2. How do online, batch, streaming, and edge inference differ?
3. Beyond model compute, which components contribute to end-to-end latency?
4. When does training-serving skew happen, and how can you detect it?
5. Why do model artifacts need a registry, digests, and provenance?
6. When does CPU outperform GPU cost-efficiency even for neural networks?
7. Dynamic batching boosts throughput, but which metric can it degrade?
8. Why can GPU autoscaling fail to keep up with sudden traffic bursts?
9. How does shadow deployment differ from canary rollouts and A/B testing?
10. Why does HTTP `200` fail to prove a model is producing high-quality predictions?
11. When the feature store fails, which fallbacks are safe depending on the use case?
12. Which metrics prove cost per prediction is dropping while model quality holds steady?

A sound ML serving architecture does more than just make a model run. It **matches the inference mode to the workload, serves consistent features, loads traceable artifacts, meets SLOs on right-sized hardware, recovers cleanly when dependencies fail, and measures both quality and cost in production**. Evaluating across the full lifecycle helps teams choose service boundaries, compute types, and operational controls aligned with real business value.
