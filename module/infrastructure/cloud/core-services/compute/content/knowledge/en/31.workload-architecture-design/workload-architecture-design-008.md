# Coordinating Multiple Compute Models in a Single System

## Learning Objectives

After this lesson, you will be able to:

- Analyze workload characteristics to choose VMs, containers, serverless functions, or managed compute services.
- Design architectures combining multiple compute models while maintaining clear responsibility boundaries.
- Choose synchronous communication, asynchronous communication, and data-sharing patterns between components.
- Coordinate workflows, identity, networking, configuration, and observability across multiple execution environments.
- Manage resilience, scalability, security, cost, and operational complexity in hybrid-compute systems.
- Validate the architecture using load scenarios, component failures, and dependency outages.

## 1. Why Does a System Need Multiple Compute Models?

A real-world application typically encompasses varied workloads with different demands. User-facing APIs need low latency and steady warm instances. Image-processing workers need to scale with queued tasks. A legacy service may require a specific OS or specialized software. A nightly reporting job running for hours suits a batch platform. Forcing every workload into one compute model can inflate costs, hurt performance, or complicate operations.

Coordinating multiple compute models means partitioning the system into components running in the most appropriate environment, then connecting them via API contracts, events, queues, data flows, and orchestration. For example:

- An order-management API runs in containers for consistent environments and horizontal scaling.
- A legacy scheduling component runs on a virtual machine due to OS or specialized agent dependencies.
- A serverless function reacts when an order is confirmed and emits events to other services.
- Container workers pull long-running tasks or jobs needing specialized libraries from a queue.
- Scheduled data aggregation runs on a managed batch service.
- Databases, caches, and message brokers use managed services to cut data-infrastructure operational effort.

The goal of a multi-model architecture is placing each workload where it fits best while keeping the overall system experience cohesive. Users do not care how many compute types a request traverses; they care that results are accurate, secure, and on time.

## 2. Commonly Combined Compute Models

| Model | Key Characteristics | Suitable Workloads | Cost and Trade-Offs |
|---|---|---|---|
| Virtual Machine (VM) | Control over OS, processes, agents, and machine configuration | Legacy software, apps needing OS privileges, stateful services, or specialized dependencies | Requires OS patching, capacity management, and deployment automation |
| Containers on Kubernetes or container platforms | Packaged apps, uniform deployments, Pod/task-level orchestration and scaling | APIs, microservices, long-running workers, workloads needing flexible runtime config | Requires cluster management or managed platform fees; orchestration overhead |
| Serverless functions | Triggered by requests/events; platform manages execution environment | Webhooks, short event handlers, glue code, intermittent workloads | Duration, runtime, and concurrency limits; cold starts and per-invocation billing |
| Serverless containers | Run containers without managing nodes or clusters | Containerized APIs, workers, or tasks with variable load | Less infrastructure control; must understand platform limits and pricing |
| Managed batch/compute services | Schedule and provision resources for finite jobs | ETL, simulations, data processing, batch jobs | Great for long jobs, but requires managing inputs, retries, and checkpoints |
| Specialized compute services | GPUs, HPC, or task-optimized environments | Model training, scientific simulations, heavy parallel compute | High hourly cost; requires maximizing utilization and resource scheduling |

Do not turn every single component into an independent service. Every new boundary adds network hops, configurations, permissions, logs, alerts, and release pipelines. Split workloads only when meaningful differences exist in lifecycle, resource needs, reliability, scalability, or ownership.

### 2.1. Choosing a Model by Workload Characteristics

Evaluate each workload against these questions:

- **Execution duration:** short requests, continuous workers, or multi-hour jobs?
- **Load pattern:** steady, seasonal, sudden bursts, or scheduled?
- **Resources:** CPU, memory, I/O, network, GPUs, or specialized hardware access?
- **State:** stateless, session-backed, persistent volumes, or checkpoints?
- **Interruptibility:** can it be retried, restarted, or moved across nodes?
- **Environment:** needs OS admin rights, native libraries, or a fixed runtime?
- **Latency:** needs immediate responses or tolerates queueing?
- **Scale:** instance count, concurrency, throughput, and data volume?
- **Operations:** does the team have capacity to manage VMs, clusters, functions, and pipelines?
- **Cost:** billed by runtime duration, reserved capacity, requests, data transfer, and operational effort?

A workload can switch compute models over time. For instance, an ingestion task may start in container workers. As volume grows, the team may move it to a batch service for better scheduling, checkpointing, and resource allocation. Base transitions on telemetry rather than technology trends alone.

## 3. Design Principles for Hybrid Compute Architectures

### 3.1. Split by Capability and Lifecycle

Each component should have a clear responsibility. APIs accept requests and validate preconditions; workers execute heavy logic; serverless functions react to events; batch jobs process bounded datasets; VMs host environment-bound software.

Do not split components merely because two compute models use different deployment tools. A small service can live cleanly inside the same container as a related component if they share lifecycle and scaling profiles. Conversely, if workers must scale to hundreds of instances while the API needs only a few replicas, splitting out a worker pool gives each its own resource policy.

### 3.2. Use Explicit Contracts Between Components

Components should interact through stable contracts:

- API contracts for synchronous request/response.
- Event schemas for event notifications.
- Message schemas for queued tasks.
- Data contracts for tables, files, objects, and data formats.
- Workflow contracts for states, timeouts, retries, and per-step outcomes.

Contracts must specify versions, mandatory fields, error codes, deadlines, and access permissions. Avoid letting one component depend on another's internal structure or local filesystem.

### 3.3. Prefer Asynchronous Communication for Long Work

Synchronous calls work when callers need immediate answers within bounded latency. For long, bursty, or retryable work, use queues or event buses. Callers submit requests, receive a `jobId`, and poll status or listen for completion events.

Never hold an HTTP connection open for minutes waiting on a batch operation when it can be decoupled asynchronously. This removes temporal coupling across compute models and lets each tier scale independently.

### 3.4. Decouple Business State from Compute Lifecycles

VMs, Pods, function invocations, or batch workers can be replaced at any moment. Business state belongs in durable databases, object storage, queues, or state stores. Never treat a function's temp directory or a container's ephemeral disk as the sole copy of results.

When a component restarts in a different compute instance, it must be able to resume from durable data and defined contracts.

### 3.5. Avoid Hiding Essential Platform Semantics

Use adapters or integration layers when portability across equivalent services is needed. However, do not build an overly broad abstraction that obscures crucial differences. Queues, streams, and event buses have different semantics; forcing them behind one lowest-common-denominator interface can lose ordering, visibility timeouts, or replay.

Abstract what is genuinely stable: identifiers, schemas, business state, retry policies, and telemetry. Keep platform-specific settings in adapters or the deployment layer.

## 4. Reference Architecture: E-Commerce Platform

An e-commerce system might coordinate multiple compute models as follows:

    User
       |
       v
    Load balancer / API gateway
       |
       v
    Container service: Order API
       |
       +------> Managed database
       |
       +------> Transactional outbox
                    |
                    v
               Event publisher
                    |
                    v
                Event bus
                 /   |   \
                /    |    \
               v     v     v
          Function  Queue  Function
          payment   image  notification
             |        |        |
             v        v        v
          Payment  Container  Email/SMS
          provider worker    provider
                      |
                      v
                Object storage

    Legacy ERP connector
          (VM)
             |
             +------> ERP database / API

    Nightly reconciliation
          (Managed batch)
             |
             +------> Managed database / Object storage

In this architecture:

- Order API runs in containers, accepting requests, authenticating, and writing orders.
- The database stores business records.
- A transactional outbox records events in the same transaction as the order.
- A publisher forwards outbox records to the event bus.
- Functions handle short steps like payment orchestration or dispatching notifications.
- A queue buffers image-processing tasks; container workers perform heavy work with retries.
- A VM runs the ERP connector because it relies on legacy libraries or network bindings.
- A batch job reconciles transactions nightly and emits reports.

This architecture is an analytical example, not a rigid template. If the ERP connector can be containerized without OS privileges, move it to containers. If image processing is brief and fits runtime limits, a function can handle it directly. Choose based on real requirements and metrics.

## 5. Example Business Flow Spanning Multiple Compute Models

Suppose a customer places an order and the system must capture payment, sync the ERP, generate an invoice, process product images, and send notifications.

1. Client sends a request to the containerized Order API.
2. API authenticates, checks inventory, and writes the order plus an outbox record in one transaction.
3. Publisher reads the outbox and emits `OrderCreated` to the event bus.
4. Payment function receives the event and calls the payment provider with an idempotency key.
5. Upon payment success, the function emits `PaymentCaptured`.
6. Event bus routes the event to the notification function and the invoice-generation queue.
7. Container worker pulls the message from the queue and generates the invoice or processes documents.
8. VM-based ERP connector receives the sync event, transforms schemas, and updates the legacy system.
9. Scheduled batch job reconciles transactions, flags discrepancies, and generates reports.
10. Components update business state so Order API returns consistent status to users.

Each step can fail independently. If the payment provider times out, the function retries within limits using idempotency. If the ERP goes down, the connector buffers work in its own queue for later processing. If the batch job stops, checkpoints let it resume. If the notification provider fails, never roll back a paid order; simply retry notification or mark status as pending follow-up.

A key design point is explicit order state modeling—for instance, `PAYMENT_PENDING`, `PAID`, `ERP_SYNC_PENDING`, `READY_TO_FULFILL`. Never mark an entire order complete simply because one function invocation returned success.

## 6. Connecting VMs, Containers, Serverless, and Batch

### 6.1. Synchronous Connections via API

Use APIs when callers need fast responses with clear request/response contracts. For example, the containerized Order API calls a VM-hosted service to look up customer IDs in the ERP.

Configure:

- Stable DNS and endpoints independent of ephemeral IPs.
- TLS and service-to-service authentication.
- Short timeouts aligned with caller SLAs.
- Retries only for transient errors on safe-to-retry operations.
- Circuit breakers or bulkheads so one slow service cannot exhaust caller resources.
- Connection pool and concurrency caps to protect the VM service.

Never retry synchronous requests indefinitely. If the ERP service fails to respond within timeout, return a controlled error or hand off to a queue for deferred processing depending on business rules.

### 6.2. Asynchronous Connections via Queues or Event Buses

Queues fit when one consumer pool processes work items. Event buses fit when multiple consumers subscribe to different events. Systems often use both: an event bus routes events into dedicated queues per worker group.

Each queue should have:

- Clear owner and purpose.
- Message schema and version.
- Retention, visibility/lease durations, and attempt limits.
- A DLQ and redrive procedure.
- Priority policies, quotas, and backlog limits.
- Metrics for message age and processing rate.

Separating queues by job type allows independent worker scaling. Avoid mixing short, long, and urgent tasks with differing SLAs in one queue; heavy tasks can stall every message behind them.

### 6.3. Exchanging Large Data via Object Storage

Avoid passing large files through APIs or message brokers when payload limits or transfer costs apply. Producers write objects to storage, then emit an event containing the object key, version, checksum, and metadata. Consumers read objects using authorized identities.

Define:

- Who owns the object and who may read/delete it?
- How long does the object live?
- Are versioning or immutable objects enabled?
- How is file integrity verified?
- What happens if an event arrives before the object is readable?
- How is data deleted per retention policies and business rules?

Events should be acknowledged only after the consumer finishes processing or persists resumable state. For large files, stream in chunks instead of buffering the whole file in memory.

### 6.4. Private Networking and Legacy Systems

VMs in private subnets can reach an ERP via VPN or private link. Containers and functions also need proper network paths when accessing internal resources. Never assume serverless functions automatically have VPC or private network access; configure network attachments, routes, DNS, security groups, and permissions per platform.

When compute models span multiple network zones, verify:

- Bidirectional routing and DNS resolution.
- TLS certificates and trust chains.
- Least-privilege firewall rules by source/destination/port.
- NAT, egress, and data transfer costs.
- Bandwidth, latency, and connection limits.
- Resilience when VPN or private links drop.

If a legacy endpoint cannot be exposed directly to cloud subnets, consider running a local connector near the legacy system communicating outbound over a controlled channel.

## 7. Workflow Coordination

When multiple compute models participate in one flow, clarify who owns coordination. Three common patterns exist:

| Pattern | Characteristics | Best Fit |
|---|---|---|
| Choreography | Each component reacts to events and emits subsequent events | Simple flows with independent services |
| Orchestration/workflow | Central workflow manages ordering, state, timeouts, retries, and branches | Multi-step processes needing end-to-end state visibility |
| Scheduler + queue | Scheduler creates scheduled jobs or messages; worker pools process them | Batch jobs, periodic tasks, time-triggered work |

### 7.1. Choreography

In choreography, `OrderCreated` triggers the payment function; `PaymentCaptured` triggers the invoice worker and notification function; the ERP connector listens to its relevant events. Each component handles its own inputs and emits the next event.

The upside is loose coupling between services. The downside is reduced visibility across complex branches, retries, and compensations. Maintain `correlationId`, an event catalog, workflow dashboards, and documented state transitions.

### 7.2. Orchestration

A workflow orchestrator persists process state and invokes each step. Example:

1. Validate order.
2. Reserve inventory.
3. Capture payment.
4. Sync ERP.
5. Dispatch fulfillment.
6. Send notification.

If payment fails after reserving inventory, the workflow invokes a compensating step to release stock. If the ERP is temporarily down, the workflow can wait or enqueue the sync step per SLA.

Do not stuff every service's business logic into the orchestrator. Each step still belongs to its owning component. The workflow manages ordering and state; services execute business logic and return verifiable outcomes.

### 7.3. Batch Orchestration

Batch jobs require schedules, dependencies, partitions, retries, checkpoints, and completion status. A scheduler can launch jobs on a batch service or push messages to worker pools. When sharded, define data partitioning and result aggregation explicitly.

Mark a job successful only after all mandatory shards finish and outputs persist durably. When one shard fails, rerun only that shard if data and logic are idempotent.

## 8. Data Management and Consistency

Multiple compute models often touch shared data. Without clear ownership, services can overwrite each other and cause race conditions.

Principles:

- Each business domain has one authoritative source of truth.
- Other services access it via controlled APIs or event/data contracts.
- Avoid having multiple compute models write directly to the same schema without clear transaction and ownership conventions.
- Use outbox/inbox patterns to emit events reliably alongside data mutations.
- Use idempotency keys, unique constraints, or conditional writes to handle duplicates.
- Use versions or sequence numbers to catch stale updates.
- Accept eventual consistency where business logic permits and surface intermediate states to users.

For example, Order API owns the `orders` table. The ERP connector never updates that table directly; instead it emits `ERPOrderSynced` or writes sync status to its own bounded context. Order service consumes the event and updates order state. This prevents shared-write conflicts.

### 8.1. Do Not Use Shared Filesystems as Integration Contracts

VMs, containers, and functions have incompatible filesystem lifecycles. A file on a VM's local disk will not automatically appear inside a container or function. Use object storage, managed file services, or managed volumes for data sharing, defining object keys, versions, checksums, and retention cleanly.

### 8.2. Avoid Dual Writes

If a component writes to a database and emits an event in two separate operations, one can succeed while the other fails. Use a transactional outbox when the database supports transactions. Consumers use inbox tables or idempotency records to absorb duplicates. Where shared transactions are impossible, design sagas and reconciliation workflows to detect drift.

## 9. Security Across Multiple Compute Models

Each compute model issues identities differently, yet the architecture must enforce least privilege and distinct workload identities everywhere.

| Component | Required Identity and Permissions |
|---|---|
| VM connector | Instance role/service identity scoped to required secrets, ERP endpoints, and target queues |
| Container service | Dedicated service account or workload identity for its database, queues, and object storage |
| Serverless function | Execution role scoped strictly to its event source, target tables, or emitted events |
| Batch job | Job identity scoped strictly to reading inputs, writing outputs, and checkpoints |
| CI/CD pipeline | Deployment identity restricted by environment and authorized resources |

Never share one administrative credential across all compute models. Use workload identities or short-lived roles where supported. Store secrets in a secret manager, rotate them, and keep them out of images, logs, and messages.

Additional controls:

- TLS encryption between components and encryption at rest.
- Network segmentation separating public ingress, application, data, and management planes.
- Firewalls and security groups scoped to required communication flows.
- Schema validation and source authentication on events.
- Audit logging for data access and permission changes.
- Vulnerability management across VM OS, container images, function dependencies, and batch runtimes.
- Isolation across development, staging, and production environments.
- Tight access controls on operator actions, queue redrives, and manual job triggers.

One well-hardened component can still be abused if a neighboring component holds overly broad permissions. Audit the entire permission chain from producer to consumer and from CI/CD to runtime.

## 10. Deployment and Configuration Management

Different compute models follow different deployment lifecycles. VMs use golden images and configuration management; containers use registries and rollouts; functions use deployment packages or container images; batch jobs use images, templates, or job definitions.

To manage consistently:

- Use Infrastructure as Code (IaC) for networks, identities, queues, event rules, clusters, VMs, functions, and IAM policies.
- Use separate pipelines or stages per artifact type while coordinating compatible versions together.
- Store environment configs in config stores/secret managers rather than hardcoding in source.
- Emit versions, build IDs, and trace metadata in logs.
- Use canary, blue-green, or rolling updates appropriate to each model.
- Maintain clear rollback or forward-fix paths for schemas and event contracts.
- Avoid out-of-band manual changes unrecorded in configuration management.

### 10.1. Dependency Deployment Ordering

A safe rollout sequence is typically:

1. Provision networking, DNS, identities, and secrets.
2. Provision databases, queues, event buses, buckets, and policies.
3. Deploy consumers capable of reading both old and new schemas.
4. Deploy producers emitting the new backward-compatible schema.
5. Enable event routing or shift traffic gradually.
6. Monitor errors, backlogs, and business outcomes.
7. Remove old schema support only after zero old producers/consumers remain.

Enabling a new producer before consumers are ready sends messages straight to errors or DLQs. Removing old queues or schemas before consumers migrate strands in-flight work.

## 11. Scaling and Protecting System Capacity

Each compute model scales differently:

- VMs scale vertically or horizontally via autoscaling groups/VM scale sets.
- Containers scale via replicas, HPA, or platform autoscalers.
- Functions scale per invocation and platform-managed concurrency.
- Batch workloads scale by job count, shards, and per-job resources.
- Managed services enforce their own quotas and throughput limits.

Never scale one component in isolation without checking the entire flow. If a function fires 1,000 requests/second at a database capped at 200 requests/second, function autoscaling destabilizes the system.

Define an end-to-end capacity budget:

1. Incoming event or request rates.
2. Maximum throughput per component.
3. Concurrent connections and requests hitting dependencies.
4. Maximum queue depth and message age.
5. API, database, storage, and network quotas.
6. Headroom to survive node/zone failures or loss of capacity in one compute pool.

Use queues to absorb bursts, rate limits to cap speed, concurrency caps to protect dependencies, and circuit breakers to stop hammering failing services. When backlogs breach thresholds, throttle producers, prioritize critical work, or spill eligible workloads to another pool if contracts and data permit.

### 11.1. Fallbacks Across Compute Models

Fallbacks must be designed upfront. For instance, if a serverless function cannot process an oversized file within runtime limits, it can enqueue a job for container workers. If Spot container nodes run short, workers can wait or spill to On-Demand per policy. If the VM ERP connector goes down, queues buffer messages until it recovers.

Never run the exact same task concurrently across two compute models without idempotency and distributed locking. Uncoordinated fallbacks create duplicate processing, resource contention, and nondeterministic ordering. Define trigger conditions, wait limits, state storage, and failback paths clearly.

## 12. Reliability and Incident Recovery

In a hybrid system, failures can strike at any layer: VMs, nodes, functions, brokers, networks, databases, or external providers. Design assuming every component can become temporarily unavailable.

Principles:

- **Timeouts:** enforce explicit timeouts on all synchronous calls.
- **Retries:** retry only recoverable errors using backoff and jitter.
- **Idempotency:** ensure retries never create duplicate side effects.
- **DLQs:** isolate persistently failing messages so main queues keep flowing.
- **Circuit breakers:** stop calling dependencies once failure thresholds trip.
- **Bulkheads:** isolate resource pools per workload so failures stay contained.
- **Health/readiness:** admit traffic only when components are genuinely ready.
- **Checkpoints:** persist progress for batches and long jobs.
- **Graceful shutdown:** stop pulling new work and finish or release in-flight tasks.
- **Multi-zone/region:** distribute components according to recovery goals and budget.

### 12.1. Failure of a Single Compute Model

| Failure | Expected Behavior |
|---|---|
| VM connector loses connectivity | Queue holds messages; connector restarts or fails over to standby instance |
| Container Pod evicted | Deployment launches new Pod; unacked messages redeliver; state loads from durable store |
| Function timeout | Source applies retries or DLQ; idempotency prevents duplicate side effects |
| Batch worker terminated | Job resumes from checkpoint or safely reruns shard |
| Event bus delayed | Monitor event age, retry publishing, and prevent false producer success states |
| Database overloaded | Cap concurrency, throttle consumers, and protect via connection pools |
| Private link/VPN drops | Bounded request timeouts; queues hold tasks; alert connectivity and restore routes |

### 12.2. Failure Boundaries and Degradation Levels

Not every failure should halt the entire system. If the email service fails, orders can still be accepted and notifications retried later. If nightly reconciliation runs slow, the storefront API keeps serving. However, if the payment provider is unreachable, the system must never mark an order as paid.

Explicitly classify core functions, deferrable functions, and degradable functions. Business state should reflect this—such as `NOTIFICATION_PENDING` or `ERP_SYNC_PENDING`—so users and operators see remaining work clearly.

## 13. Cross-Model Observability and Tracing

Each compute environment emits its own logs and metrics. Without shared identifiers, tracing a single request across container APIs, functions, queues, VM connectors, and batch jobs becomes painful.

Propagate these fields:

- `correlationId` or `traceId` across the full business flow.
- `eventId`/`messageId` for each event or message.
- `jobId` for long-running jobs.
- `tenantId` in multi-tenant systems where policy permits.
- `serviceName`, runtime, version, and environment.
- `attempt`/`retryCount` to see how many times a message was retried.

Track these metric groups:

| Group | Metrics |
|---|---|
| API/container | Request rate, p95/p99 latency, error rate, replicas, CPU/memory |
| VM | CPU/memory/disk, process health, patch status, network connections |
| Function | Invocations, duration, cold starts, timeouts, throttles, concurrency |
| Queue/event bus | Depth, oldest age, publish/consume rates, retries, DLQs |
| Batch | Job duration, shard completion, checkpoint age, retries, and failures |
| Data/dependency | Database latency, connections, storage throughput, API 429/5xx |
| Business | Request-to-completion duration, orders in pending states, completion rate |
| Cost | Cost per request/job, compute hours, data transfer, storage, and idle capacity |

Use distributed tracing across HTTP and messaging where supported. When crossing queues, embed trace context in message headers or event envelopes. For multi-hour batch jobs, emit checkpoints and per-shard or per-stage spans rather than keeping one giant span open.

Alert on SLOs and backlogs rather than CPU alone. A function with low CPU and climbing queue age can still breach SLAs due to a slow dependency. A VM running high CPU for several minutes may be completely normal during a scheduled batch.

## 14. Holistic Cost Management

Compare costs across the entire system rather than pricing individual compute units in isolation.

| Model | Cost Components to Account For |
|---|---|
| VM | Instance hours, disks, licenses, snapshots, network egress, and idle capacity |
| Container | CPU/memory requests, node hours, control plane, storage, load balancers, and logging |
| Serverless | Invocations, duration, memory, provisioned capacity, event routing, and retries |
| Batch | Job duration, peak resources, intermediate storage, checkpoints, and wait times |
| Integration | Queue operations, data transfer, NAT, private links, logs, traces, and monitoring |

A serverless function may be cheap per call yet trigger millions of invocations via fan-out or retry loops. A container cluster can waste money on idle nodes if it never scales down. VMs can be economical for steady load yet carry patching and management overhead. Batch jobs save money when confined to run windows and torn down afterward.

Optimization levers:

- Measure cost per completed request or business transaction.
- Shut down or scale down unused resources when safe.
- Use Spot for interruptible batches/workers while keeping stable capacity for critical tiers.
- Rightsize containers/functions based on real profiling.
- Minimize cross-region and cross-service data transfer.
- Set sensible retention on queues, logs, objects, and checkpoints.
- Detect unexpected retry loops and event fan-out amplification.
- Attribute costs by service, team, environment, and tenant.

Never optimize one component locally if it inflates costs elsewhere. Moving processing to functions might shave node hours while multiplying database reads and event-routing fees. Evaluate the entire data path.

## 15. Process for Designing a Hybrid-Compute System

Follow these steps:

1. **Inventory workloads:** document function, owner, runtime duration, load, resources, and state.
2. **Classify requirements:** define latency, throughput, SLAs, interruptibility, security, and data residency.
3. **Select compute:** match each workload to VMs, containers, functions, batch, or managed services.
4. **Define boundaries:** decide which components are services, workers, functions, connectors, or jobs.
5. **Design contracts:** APIs, event schemas, messages, data contracts, versioning, and error codes.
6. **Design data flows:** authoritative sources of truth, file storage, access permissions, and retention.
7. **Choose coordination:** choreography, workflow orchestrator, or scheduler/queue.
8. **Design reliability:** timeouts, retries, idempotency, DLQs, checkpoints, fallbacks, and graceful shutdown.
9. **Design networking and identity:** DNS, TLS, private connectivity, workload identities, and least privilege.
10. **Set capacity and limits:** concurrency, quotas, connection pools, queue depths, and headroom.
11. **Establish observability:** correlation IDs, traces, metrics, logs, and cross-model alerts.
12. **Model costs:** compute, networking, storage, licenses, managed services, and operational effort.
13. **Test failure modes:** simulate VM loss, Pod evictions, function timeouts, backlogs, and dependency outages.
14. **Roll out incrementally:** canary, staged rollouts, and per-component rollbacks while watching SLOs before scaling traffic.

## 16. Example Model Selection by Workload

An enterprise has five workloads:

| Workload | Characteristics | Recommended Model | Rationale |
|---|---|---|---|
| Order API | Short requests, variable load, continuous rollouts | Container service | Horizontal scaling, consistent environment, runtime control |
| ERP connector | Legacy software needing native libraries and private network bindings | VM | Preserves compatibility while planning modernization |
| Image thumbnailing | Short tasks triggered by uploads | Serverless function | Event-driven execution, automatic demand scaling |
| Video transcoding | Long tasks, high CPU/GPU, checkpointable | Container workers or batch compute | Resource control, long-job execution, per-shard retries |
| Nightly reconciliation | Scheduled, data-heavy, terminates on completion | Managed batch | Scheduling, capacity allocation, finite job management |

Selections evolve with scale and platform limits. If thumbnailing needs heavy native libraries or exceeds timeouts, move it to container workers. If the ERP connector gets containerized without OS privileges, move it onto the container platform. If video transcoding runs steadily around the clock, consider dedicated compute pools instead of provisioning per job.

## 17. Pre-Production Verification Scenarios

Test in staging or an equivalent environment:

1. **Happy-path check:** submit a request and trace it across the API, event bus, functions, workers/VM connector, and data stores.
2. **Contract check:** emit a new schema version and confirm older consumers stay compatible; test unsupported versions.
3. **Duplicate check:** replay messages and events; confirm idempotency prevents duplicate side effects.
4. **Timeout check:** slow a dependency past timeout; confirm bounded retries and circuit breakers trigger.
5. **VM loss check:** stop the test connector VM; confirm queues retain work and the recovered connector resumes cleanly.
6. **Pod eviction check:** delete a worker Pod in staging; confirm unacked messages redeliver with zero state loss.
7. **Function throttle check:** cap concurrency or inject a burst; confirm queues absorb load and downstream stays healthy.
8. **Batch checkpoint check:** kill a shard mid-run; confirm the job resumes from checkpoint or reruns safely.
9. **Network check:** sever the test private link/VPN; confirm timeouts, alerts, and backlogs behave cleanly.
10. **Fallback check:** disable one compute pool; confirm work waits, fails over, or degrades per policy.
11. **Observability check:** locate `correlationId` and `eventId` across dashboards, logs, and traces in every component.
12. **Cost check:** compare measured cost per request/job against targets and verify no stray resources linger.

Document recovery times, retry counts, backlog drain times, and SLO impacts. Never run disruptive chaos experiments in production without strict controls and verified recovery procedures.

## 18. Common Incidents and Troubleshooting

| Symptom | Possible Cause | What to Check |
|---|---|---|
| API succeeds but background tasks never run | Outbox publisher failing, wrong event rule, or queue not receiving messages | Check outbox age, publish results, event rules, and queue metrics |
| Function surge breaks the database | Unbounded concurrency or oversized connection pools | Cap concurrency, use proxies/poolers, and monitor DB connections |
| Container workers cannot reach VM ERP | Broken DNS, routes, firewalls, TLS, or private link | Verify bidirectional routing, security groups, and certificates |
| Batch job restarts from scratch after failure | Missing or non-durable checkpoints | Check checkpoint storage, shard IDs, and idempotency |
| Event processed twice across two compute models | Simultaneous fallback or at-least-once delivery | Enforce shared idempotency keys and leased work claims |
| Data inconsistency across services | Multiple writers mutating one store or dual writes | Enforce single source of truth, outbox/inbox, and write permissions |
| Costs climb after splitting services | Rising fan-out, network egress, logging, or idle capacity | Analyze cost by business flow and individual component |
| Hard to trace requests end to end | Missing `correlationId` or trace context across queues | Standardize metadata and propagate trace headers/attributes |
| Rollout breaks schemas | New producer emits events unreadable by old consumers | Use backward-compatible schemas and deploy consumers first |
| Fallback fails when pool goes down | Missing policy, permissions, or reserve capacity | Test failover, verify quotas, identities, and trigger thresholds |

## 19. Design and Operations Checklist

- [ ] Classify workloads by runtime duration, load, resources, state, and interruptibility.
- [ ] Choose VMs, containers, serverless, batch, or managed services from real characteristics.
- [ ] Each component has clear responsibilities, an owner, and data boundaries.
- [ ] Versioned API, event, message, and data contracts are defined.
- [ ] Synchronous vs. asynchronous communication aligns with SLAs and processing times.
- [ ] Business state is persisted in durable stores.
- [ ] Outbox/inbox, idempotency, and checkpoints are used where needed.
- [ ] Timeouts, retries, DLQs, circuit breakers, and graceful shutdown are configured.
- [ ] DNS, TLS, network segmentation, and private connectivity are managed.
- [ ] Dedicated least-privilege workload identities are assigned.
- [ ] Infrastructure and configs are managed via IaC with versioned, rollbackable pipelines.
- [ ] Concurrency, connections, quotas, and queue backlogs are bounded.
- [ ] `correlationId`, traces, metrics, logs, and SLOs are tracked across models.
- [ ] VM loss, Pod evictions, function timeouts, batch failures, and dependency outages are tested.
- [ ] Cost per completed business transaction—including networking and operations—is measured.
- [ ] Runbooks exist for fallbacks, replays, DLQs, and data recovery.

## Conclusion

Coordinating multiple compute models lets every workload run in an environment tailored to its lifecycle, resource profile, and SLAs. The architecture stays reliable only when components honor explicit contracts, state resides in durable stores, interactions use coordinated APIs, queues, events, or workflows, and identity and observability span the entire system. Validate both normal paths and pool or dependency failures, and evaluate end-to-end cost across the business flow before promoting to production.
