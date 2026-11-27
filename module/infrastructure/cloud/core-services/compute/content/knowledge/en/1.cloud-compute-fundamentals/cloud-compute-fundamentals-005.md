# Classifying Workloads by Runtime Duration, State, and Resource Needs

When deploying an application in the cloud, the first question should not simply be “how many virtual machines do we need?” You must understand what work the application performs, how long it runs, where it keeps state, and how it consumes resources. These characteristics determine the right compute model, scaling approach, availability strategy, and total operating cost.

In cloud compute fundamentals, a **workload** is a service, process, or group of tasks that consumes compute resources to process requests or data. A real-world system typically comprises multiple distinct workloads. For example, an online store has a user-facing API, a database storing orders, an image-processing task, and an overnight report-aggregation job. Because these components have different characteristics, they may require different deployment models.

This lesson presents three primary classification axes:

- **Runtime duration:** Whether the workload runs briefly, in batches, continuously, or on an event stream.
- **State:** Whether the workload must retain data across executions, and to what durability level that data must be preserved.
- **Resource needs:** Whether the workload primarily needs CPU, memory, storage, networking, or accelerators like GPUs.

These three axes are relatively independent. A task running for just a few minutes may still need large amounts of RAM; an always-on service can be completely stateless; a GPU workload can be either a batch job or an interactive service. Properly classifying along each axis helps select the right VM, container, serverless, or managed service.

## 1. Understand the Workload Before Choosing a Compute Model

A workload describes a **resource-usage pattern and execution behavior**, not a specific server or technology. One workload can run on a virtual machine, in a container, or on a serverless platform depending on requirements.

When assessing a workload, answer these questions:

1. Is work triggered by user requests, a schedule, queue messages, or a data stream?
2. How long does a single execution last? Does the process exit after finishing, or must it run continuously?
3. If the process restarts, which data must remain intact? Can the task be safely rerun?
4. Which component limits performance: CPU, RAM, read/write speed, network bandwidth, or GPU?
5. Is load steady or highly spiky? Does the system prioritize low latency, high throughput, or low cost?
6. What access permissions, network connectivity, and isolation level does the workload require?

Do not classify based solely on an application's name. One application can contain multiple workload types. For example, the same system may include an interactive API, a queue-processing worker, a batch job, and a stateful database.

## 2. Classification by Runtime Duration

Runtime duration indicates how long a workload lives and how it starts and terminates. This forms the basis for selecting resource provisioning, orchestration mechanisms, and scaling policies.

| Workload Type | Characteristics | Examples | Common Requirements |
|---|---|---|---|
| Interactive or on-demand | Processes a request and returns a result; typically needs fast responses | APIs, search queries, authentication | Low latency, continuous availability, traffic-based scaling |
| Short-lived task | Runs briefly and exits | Sending emails, generating thumbnails, data validation | Fast startup, reliable execution, error handling, and retries |
| Batch | Processes a dataset or job list; has a defined start and end | Payroll calculation, report aggregation, data ingestion | Throughput, queues, checkpoints, and retryability |
| Long-running service | Continuously running process accepting and handling requests | Web servers, backend APIs, background workers | Health monitoring, rolling updates, scaling, and recovery |
| Streaming | Continuously ingests data, processing events over time | Clickstream analytics, sensor monitoring, fraud detection | Steady throughput, processing latency, offset and window-state management |
| Scheduled task | Starts at a defined time or interval | Backups, sync jobs, daily reports | Reliable scheduling, duplicate-run prevention, failed-run tracking |

### 2.1. Interactive Workloads

Interactive workloads typically sit directly on the user's critical path. When a user opens a product page, the API must respond within an acceptable timeframe. One slow processing step can inflate latency for the entire request, even if CPU utilization has not reached maximum.

Therefore, measure percentile latencies such as p95 or p99, requests per second, concurrent connections, and error rates. Average latency can mask a small group of very slow requests. APIs are commonly deployed across multiple replicas to distribute load and continue serving if one replica fails.

### 2.2. Short-Lived and Batch Tasks

Short-lived tasks are typically triggered by events or messages. Batch tasks process a finite volume of work, taking anywhere from a few minutes to several hours. Both types require defining clearly what happens if a process stops mid-execution.

A resilient design typically places work into a queue so workers pull items and acknowledge completion after successful processing. If a worker fails, the message may be redelivered. Consequently, processing operations should be **idempotent** (safely repeatable without producing incorrect results or duplicate side effects). For large batch jobs, checkpoints allow resuming from the last processed position rather than restarting from scratch.

Not every batch job fits a serverless function. Check execution time limits, memory, data sizes, startup latency, and platform checkpointing capabilities. Long tasks or tasks requiring custom environments may better suit container jobs, managed batch services, or VMs.

### 2.3. Long-Running Services and Streaming

Long-running services maintain processes that continuously accept requests or jobs. They need health checks, graceful shutdown signal handling, version updates, and automatic restarts on failure. When deploying multiple replicas, the application must tolerate any replica disappearing at any moment.

Streaming also runs continuously, but focuses on ingesting and processing sequences of events. The system must track read positions, handle late or duplicate events, and control consumption rates. If input data rates exceed processing rates for extended periods, queues or processing latency will grow. This signals a need to add processing capacity, reduce per-event cost, or apply backpressure.

## 3. Classification by State

**State** is the data a workload must remember across requests, across processing runs, or across restarts. Distinguishing stateless from stateful guides how you scale, store data, and recover.

### 3.1. Stateless Workloads

A stateless workload does not need to hold local business state between two processing runs. Any replica can handle any request, provided it receives sufficient input data and can reach dependent services.

For example, an API receives an order ID, reads info from a database, and returns a result. If the API does not store user sessions in local memory, multiple replicas can serve the same class of requests. When one replica is replaced, subsequent requests route to healthy replicas.

Stateless designs generally favor horizontal scaling, load balancing, and rolling deployments. However, stateless does not mean the overall system lacks stateful data. State may live in a database, shared cache, object storage, or session management service.

### 3.2. Stateful Workloads

Stateful workloads must maintain state across executions. Examples include databases, session stores, message brokers, windowed stream processors, and applications writing data to local disks.

When scaling or replacing a stateful replica, you must know where data resides, which replica holds write authority, and how to restore data. Common requirements include:

- **Data durability:** Must data survive after a VM or container is deleted?
- **Consistency:** At what point must replicas observe the same version of data?
- **Backup and recovery:** Are there periodic backups, cross-region copies, and tested recovery procedures?
- **Data partitioning:** How is data sharded or partitioned as load grows?
- **Fault tolerance:** If the node holding primary data fails, how does another node take over?

A container can run a stateful application, but the container itself does not guarantee data durability. Data must reside on persistent volumes or appropriate storage services. For critical databases, managed database services often reduce operational overhead for backups, patching, and failover.

### 3.3. Ephemeral State vs. Persistent State

Not all data in memory needs long-term storage. Data can be categorized into:

- **Ephemeral data:** Local caches, intermediate files, regenerable computation data. Losing it usually only increases processing time.
- **Session data:** Login info or shopping carts that must persist across requests, though often with an expiration TTL.
- **Persistent business data:** Orders, payments, customer records, or processing outputs that must be preserved and backed up.
- **Progress state:** Offsets, checkpoints, window state, or processing cursors to resume work after a restart.

Clarify the data category before choosing disks, volumes, or storage services. Storing critical business data on an ephemeral compute disk risks data loss when the machine is replaced.

## 4. Classification by Resource Needs

Two workloads with identical runtime durations and state profiles may still require vastly different compute configurations. Identify which resource limits performance (the bottleneck) rather than blindly adding CPUs.

| Resource Group | Signs of Resource Bottleneck | Examples | Optimization Direction |
|---|---|---|---|
| CPU-bound | High CPU utilization; processing time spent mostly on computation | Data compression, encryption, simulations | Increase CPU capacity, optimize algorithms and parallelism |
| Memory-bound | Large working set; memory pressure, garbage collection, or OOM errors | In-memory analytics, large caches | Increase RAM, reduce data copies, stream or micro-batch processing |
| Storage I/O-bound | High read/write latency or disk queues; CPU may remain idle | Databases, large file processing | Choose suitable storage tier, optimize queries, caching, and data layout |
| Network I/O-bound | Heavy network waiting; bandwidth or connection counts are the limit | Proxies, integration APIs, file transfers | Check bandwidth, latency, connection counts, region placement, and service limits |
| GPU/accelerator-bound | Parallel math suited to accelerators; CPU is not the primary limit | Model training, AI inference, image/video processing | Choose matching GPU, optimize batch size, GPU memory, and device utilization |
| Mixed | Multiple resources impact performance or bottleneck shifts by stage | Data pipelines, analytics applications | Measure per stage and split workloads if needed |

### 4.1. CPU-Bound

CPU-bound workloads require heavy processing cycles. Examples include video encoding, data compression, scientific computing, or complex business logic. Increasing vCPUs can boost throughput if the program exploits parallelism. If most work executes sequentially, adding vCPUs may yield minimal speedup.

Measure CPU utilization, CPU time per task, latency, and actual parallelism. Beyond vCPU count, per-core performance and CPU architecture also affect outcomes.

### 4.2. Memory-Bound

Memory-bound workloads need to hold large datasets in RAM or allocate many objects during processing. Insufficient RAM can trigger OS swapping, spiking latency, or cause containers/processes to be killed for exceeding memory limits.

Measure working set size, peak memory usage, memory growth over time, and behavior under rising load. Leave headroom for runtime overhead, caches, connections, and traffic spikes. Sizing RAM too close to average usage risks failures during concurrent request bursts.

### 4.3. Storage I/O-Bound

I/O-bound workloads spend time waiting to read or write data. For databases, metrics like I/O latency, IOPS, throughput, and queue depth can matter more than CPU. Storage with high IOPS but unsuitable latency or insufficient capacity can still slow down the application.

Distinguish hot data needing fast access from long-term archival data. Use caches for frequently read data, optimize queries, batch writes, or offload large files to object storage. Do not use a single disk type for every purpose solely because of a low unit price.

### 4.4. Network I/O-Bound

Network-bound workloads depend on bandwidth, latency, concurrent connections, and distance between components. An API calling multiple services across different regions can be slow even with spare CPU and RAM. Large outbound data transfers out of the cloud can also generate substantial costs.

Measure network wait times, timeout rates, connection counts, ingress/egress traffic, and data transfer costs. Colocate frequently communicating components in close deployment regions, and cap retries to avoid amplifying load when a dependency fails.

### 4.5. GPUs and Accelerators

GPUs fit massively parallel computations such as machine learning training, AI inference, or image processing. GPUs typically cost more than standard CPU resources and carry dedicated device memory. GPU selection should consider compute precision/operations, device memory capacity, numerical precision, software compatibility, and expected utilization.

If a workload uses a GPU for only a brief stage of a pipeline, split that stage into a separate job. That prevents preprocessing or postprocessing steps from holding onto an expensive GPU while waiting on I/O.

## 5. Also Factor in Load Shape and Service Targets

The three axes—runtime duration, state, and resources—provide the foundation, but are not enough for final sizing. Examine how load varies over time:

- **Steady load:** Relatively uniform demand; fits steadily provisioned baseline capacity.
- **Spiky/bursty load:** Short sharp peaks; requires rapid scaling, queuing, or rate limiting.
- **Seasonal or scheduled load:** Increases during peak hours, sales campaigns, or end-of-period cycles; requires advance planning and autoscaling.
- **Unpredictable load:** May suit usage-based pricing models, while still requiring limits, startup latency control, and peak cost caps.

Service targets also shape choices. A workload needing responses in tens of milliseconds has different requirements from a batch job that can finish in several hours. Define clear SLAs/SLOs such as availability, p95 latency, success rate, and recovery time.

## 6. Mapping Workload Characteristics to Cloud Compute Models

Common compute models have distinct strengths and trade-offs. Model selection should reflect workload characteristics and required infrastructure control.

| Model | Best Suited When | Considerations |
|---|---|---|
| Virtual Machine (VM) | OS/kernel control, legacy software, special machine configs, or long-running processes are needed | Must manage patches, OS, headroom capacity, and scaling |
| Container | Consistent packaging, multi-replica deployment, or running services/jobs on an orchestrator is desired | Must manage images, resources, networking, storage, and orchestration platform |
| Serverless function | Short tasks, event-driven triggers, variable load, and minimal server management | Subject to duration, memory, package size, cold start, and platform state limits |
| Serverless container or application platform | APIs, workers, or jobs needing a container environment while minimizing server administration | Check continuous execution support, network config, resource limits, and billing model |
| Managed batch/stream service | Large-scale job scheduling, queue processing, or data streaming is required | Depends on service features, limits, and pricing; design proper retries and observability |

### 6.1. When to Choose VMs?

VMs provide a virtualized computer environment with an allocated OS and resources. VMs fit when an application requires deep control, depends on special kernels or system libraries, or must maintain long-lived processes. Some legacy software is also easier to lift onto a VM than rewrite for containers.

In return, the operations team owns OS updates, security configuration, monitoring, backups, and scaling machine counts. If a workload runs only a few seconds per hour, an always-on VM creates significant idle waste.

### 6.2. When to Choose Containers?

Containers package an application with required dependencies to run consistently across compatible environments. Containers can run long-lived services, background workers, or batch jobs. Combined with an orchestration platform, systems can manage replicas, distribute load, self-heal, and scale on metrics.

Containers do not automatically solve all operational concerns. You must configure CPU/RAM, logging, shutdown signals, readiness/liveness probes, persistent storage, and image update policies. For stateful workloads, design dedicated volumes, backups, and recovery mechanisms.

### 6.3. When to Choose Serverless?

Serverless shifts most server provisioning and management to the provider. For functions, the provider typically triggers code upon events and bills based on usage per service pricing. This fits short tasks, event handling, webhooks, or automation steps with irregular traffic.

Serverless does not mean server-free; servers still exist, though users rarely manage them directly. Check execution duration limits, memory, concurrency, cold starts, private networking, access permissions, and high-traffic costs. If tasks run long, require GPUs, need continuous processes, or need specialized OS environments, containers or VMs may fit better.

### 6.4. Using Managed Services for Specialized Work

Not every component needs to be self-operated on VMs or containers. Managed databases, queues, object storage, and streaming platforms can provide built-in backups, monitoring, replication, or scaling. This choice lets teams focus on application logic, though you must assess cost, limits, portability, and data governance requirements.

## 7. Quick Decision Table

The table below provides a starting point for selecting a deployment model. These are not rigid rules; check provider limits and test with realistic loads.

| Workload Characteristics | Reasonable Starting Point | Rationale |
|---|---|---|
| Stateless API, always-on, relatively steady load | Container or application platform | Easy to run multiple replicas and scale with traffic |
| Webhooks or short event processing, variable load | Serverless function | Event-triggered, reduces idle resources |
| Long batch jobs needing checkpoints or custom environments | Container job, batch service, or VM | Control over execution duration and processing progress |
| Legacy app needing specific OS or kernel | VM | Preserves required execution environment |
| Database needing durable data | Managed database service or dedicated VM | Enables proper storage, backup, and recovery design |
| Continuously running streaming worker | Container or managed streaming service | Supports long-lived processes, state, and orchestration |
| AI training needing GPUs for extended periods | VM or GPU-enabled container | Control over devices, libraries, and runtime duration |

A simple selection workflow:

~~~mermaid
flowchart TD
    A["Describe workload"] --> B{"Need special OS processes or environment?"}
    B -- "Yes" --> C["Evaluate VM"]
    B -- "No" --> D{"Short work triggered by events?"}
    D -- "Yes" --> E["Evaluate serverless function"]
    D -- "No" --> F{"Need packaging and orchestration for services or jobs?"}
    F -- "Yes" --> G["Evaluate container"]
    F -- "No" --> H["Evaluate managed platform or compute service"]
    C --> I["Verify state, resources, security, and cost"]
    E --> I
    G --> I
    H --> I
~~~

Even after selecting a compute model, you must still choose CPU type, RAM size, storage, network configuration, deployment region, and access permissions. Two workloads both running in containers may require completely different resource configurations.

## 8. Selecting and Bounding Resources

Do not size configurations solely from average utilization. Observe peak loads, processing times, latency, and concurrency. A configuration sufficient at average load may fail when many requests arrive simultaneously.

### 8.1. CPU and Memory

For CPU, monitor utilization, wait time, concurrent tasks, and application latency. For memory, monitor working set, peak usage, memory growth over time, and out-of-memory process terminations.

In Kubernetes, `requests` specify resources used to schedule containers; `limits` cap the resources a container can consume. The example below illustrates an API service with three replicas, each container requesting 500 millicores of CPU and 512 MiB of RAM:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: catalog-api
  template:
    metadata:
      labels:
        app: catalog-api
    spec:
      containers:
        - name: api
          image: registry.example/catalog-api:v1
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              cpu: "1"
              memory: "1Gi"
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
          livenessProbe:
            httpGet:
              path: /health
              port: 8080
~~~

This is merely an illustrative configuration, not a universal baseline for every API. Tune values based on load testing. CPU limits set too low can throttle the application; memory limits set too low can cause container termination. Conversely, requests set too high can reduce scheduling bin-packing efficiency and inflate standby capacity costs.

### 8.2. Storage and Networking

For storage, specify capacity, latency, IOPS, throughput, scalability, and data retention duration. Separate temporary data from data requiring preservation. Also inspect data growth rates and snapshot or backup costs.

For networking, determine ingress/egress traffic, connection counts, latency to dependent services, private IP requirements, DNS, load balancing, and connection limits. If a workload transfers large volumes of data across regions or to the Internet, include data transfer costs.

### 8.3. Accelerators

For GPUs or accelerators, beyond device count, consider device memory capacity, framework compatibility, data-loading overhead, and actual device utilization. An expensive GPU frequently idling while waiting on CPU data preparation is underutilized. Optimizing data pipelines and batch sizes can improve throughput before adding more GPUs.

## 9. Scaling Load and Ensuring Availability

**Horizontal scaling** increases the number of workload replicas; **vertical scaling** increases CPU, RAM, or capacity of a single machine. Horizontal scaling typically suits stateless, partitionable workloads. Vertical scaling helps when an application is difficult to split or needs large resources on one node, but faces machine size ceilings and may require restarts.

Choose scaling signals aligned with the workload:

- Interactive API: request rate, latency, in-flight requests, or CPU.
- Queue worker: queue depth, age of oldest message, and processing rate.
- Batch: queued job count, completion deadline, and per-worker throughput.
- Streaming: consumer lag, ingress/egress rates, and parallelizable partition count.

CPU is not always the best scaling metric. A worker may use low CPU while bottlenecked on I/O wait; adding workers in that case can raise throughput. Conversely, scaling replicas without bounds can overload databases or dependent services. Configure concurrency limits, connection pools, and backpressure.

To improve availability, run multiple replicas across distinct fault domains or availability zones, configure health checks, use load balancers, and roll out updates incrementally. Applications must implement graceful shutdown: stop accepting new work, finish or return in-flight work cleanly, and close connections properly.

For stateful workloads, multiple replicas improve availability only when data replication and failover mechanisms are properly engineered. Data replication, backups, and restore testing are essential. Define RPO (maximum acceptable data loss) and RTO (target recovery time) for critical data.

When processing events or messages, retries should be bounded and typically use exponential backoff with jitter to avoid thundering herds. Repeatedly failing messages can be routed to a dead-letter queue for investigation. Idempotency ensures safe handling when a message is delivered multiple times.

## 10. Security by Workload Characteristics

Each workload should have its own identity and access permissions following least privilege. A worker that only processes images does not need read access to all payment records. Separating permissions by role limits blast radius if a component is compromised.

Key areas to verify include:

- **Identity and permissions:** Use IAM roles or workload identities when supported by the platform; avoid sharing long-lived access keys across services.
- **Secrets:** Store passwords, tokens, and certificates in a secrets manager; never write secrets into source code, images, or logs.
- **Networking:** Restrict connection flows between components, use private networks where appropriate, and expose only required endpoints publicly.
- **Data:** Encrypt in transit and at rest; grant data access strictly according to workload needs.
- **Images and OS:** Apply patches, scan for vulnerabilities, use images from trusted provenance, and minimize unnecessary packages.
- **Isolation:** Evaluate VM, container, or sandbox isolation levels matching the workload's trust level and security requirements.

Short-lived workloads still require security. A function running for a few seconds with overly broad permissions can still leak data. Long-lived workloads require regular patching and update routines because longevity increases exposure to outdated components.

## 11. Optimizing Operational Costs

Compute cost is not just CPU or VM pricing. Total cost can include memory, storage, snapshots, data transfer, load balancers, logs, monitoring, licenses, and engineering operations time.

Several practical principles:

1. **Measure before resizing.** Identify bottlenecks and utilization over time to avoid unnecessary upgrades.
2. **Eliminate idle time.** Event-driven or irregular workloads can fit serverless or scale-to-zero mechanisms if latency requirements allow.
3. **Right-size capacity.** Avoid allocating excessive CPU/RAM relative to demand; likewise avoid squeezing configurations so tight that processing stalls or fails.
4. **Optimize data transfer.** Colocate frequently communicating components, compress data when sensible, and reduce unnecessary transfers.
5. **Split workloads by demand.** Do not hold onto GPUs or large machines while another pipeline stage merely waits on I/O.
6. **Evaluate commitments and interruptible capacity.** Discounts like long-term commitments or spot/preemptible instances fit only when load stability or interruption tolerance permits.

Serverless can cut costs when workloads run infrequently, but is not automatically cheaper under continuous or high-volume traffic. VMs can be economical for steady loads with high utilization. Compare cost per unit of work—such as cost per thousand requests or per million records—while holding operational effort and availability requirements equal.

## 12. Practical Example: Classifying Workloads in an Online Store

Suppose an online store consists of the following components:

| Component | Runtime Duration | State | Dominant Resources | Candidate Model |
|---|---|---|---|---|
| Catalog and order API | Long-running, interactive | Stateless at API tier; business data in DB | CPU, networking, latency | Container or application platform |
| Order database | Long-running | Stateful, durable data | RAM, storage I/O, networking | Managed database or dedicated VM |
| Product image processing worker | Short task or queued job | Stateless if source and output files live in object storage | CPU or GPU depending on transforms; I/O | Serverless function or container job |
| Overnight revenue report | Scheduled batch | Checkpointed; outputs require durable storage | CPU, RAM, storage I/O | Batch service or container job |
| User event analytics | Streaming | Stateful by window or offset | Networking, CPU, storage | Managed streaming service or container |

This table shows an application need not run on a single compute model. The API needs fast responses and runs continuously; image processing only consumes resources when new images arrive; reporting runs on a schedule; the database requires durable storage. Splitting workloads lets you match configurations per component and contain blast radius when one component saturates.

For example, during a promotional campaign, API requests surge. You can scale API replicas with traffic while simultaneously monitoring database connections and capacity. Scaling the API without controlling queries can turn the database into the bottleneck. For the image-processing worker, a queue absorbs traffic spikes and scales workers based on queue depth, controlling throughput without paying for peak worker counts all day.

## 13. Process for Classifying a New Workload

Follow this workflow when onboarding a new application or component:

1. **Describe the job:** Record inputs, outputs, triggers, and dependent services.
2. **Identify runtime duration:** Interactive, short-lived, batch, long-running, streaming, or scheduled; note execution duration and startup requirements.
3. **Identify state:** Classify ephemeral data, session data, business data, and checkpoints; define durability, backup, and recovery requirements.
4. **Measure resource needs:** Test CPU, RAM, I/O, networking, and GPU; record averages, peaks, and bottlenecks.
5. **Characterize load shape and SLOs:** Request rate, concurrency, throughput, latency, completion deadlines, and target availability.
6. **Select compute model:** Compare VMs, containers, serverless, and managed services against actual requirements.
7. **Test and cost out:** Run representative load tests, verify errors and recovery, then compare cost per unit of work.

Record classification results in a concise profile per workload. This profile aligns development, operations, and security teams on configuration, access permissions, scaling behavior, and evaluation criteria.

## 14. Common Mistakes

- **Choosing compute before understanding the workload:** Leads to over-provisioning or under-provisioning.
- **Treating containers as durable data stores:** Data in a container's writable filesystem can be lost when replaced.
- **Assuming stateless means zero state exists:** State may reside in databases, caches, or external services and still requires durability design.
- **Monitoring only CPU:** Overlooks RAM, I/O, network, queue, or dependency bottlenecks.
- **Using unbounded retries:** Can overload systems during prolonged outages and trigger duplicate processing.
- **Scaling replicas without checking bottlenecks:** Can shift congestion onto databases, queues, or downstream APIs.
- **Choosing serverless solely because load is irregular:** Must verify execution limits, cold starts, concurrency, and high-load costs.
- **Ignoring data and operational costs:** Cheap compute can still produce high total bills due to data transfer, storage, or monitoring.

## 15. Key Takeaways

Workload classification is the foundational step in designing cloud compute infrastructure. Examine workloads across multiple axes: runtime duration shows how they start and stop; state shows how data must be preserved and recovered; resource needs dictate CPU, RAM, storage, networking, or GPU configurations. Load shape, SLOs, security, and cost complete the final decision.

Understanding these traits allows matching each component to VMs, containers, serverless, or managed services, designing appropriate scaling and availability, and avoiding paying for unnecessary resources.
