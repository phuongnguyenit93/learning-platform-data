# Business-aligned function design and unit-of-work sizing

Serverless functions deploy quickly, scale automatically, and bill per invocation or resource-time. Yet splitting an application into too many tiny functions can introduce excessive network hops, make transaction tracing harder, and drive up orchestration costs. Conversely, stuffing too much business logic into one giant function makes code hard to test, stretches execution times, widens permissions, and lets a single bug disrupt multiple business flows.

Good design starts with the **business capabilities** the system must provide, then chooses function boundaries, trigger types, and an appropriate unit-of-work size. A function should have a clear responsibility, stable inputs/outputs, and measurable resource limits. The unit of work may be a single request, record, document, message, batch, or partition; picking the wrong size increases overhead, latency, retries, or the risk of hitting platform limits.

This lesson explains how to decompose business capabilities into functions, size units of work and compute settings, structure orchestration, state, errors, and security, and walk through concrete examples balancing maintainability, performance, reliability, and cost.

## 1. Two design decisions to separate

When designing serverless systems, keep two distinct questions separate:

1. **Which business responsibility does the function own?** This defines functional boundaries and logic ownership.
2. **How much work does each invocation process?** This defines the runtime unit-of-work size.

For example, a function may own generating image thumbnails. The business boundary is “generate thumbnails.” Yet a single invocation might process one image, a batch of 10 images, or a message representing a set of images. You do not need a brand-new function simply to change batch size.

### Business boundary

This boundary defines:
- What job the function performs.
- Which events or requests trigger it.
- Input and output data.
- Required access permissions.
- Permitted side effects.
- Who owns and evolves the logic.
- Conditions for success, failure, and retries.

### Unit-of-work size

The unit-of-work size determines:
- Whether one invocation processes one or many items.
- Payload size and memory working set.
- Expected execution duration.
- Volume of I/O and dependency calls.
- Required memory, CPU, and ephemeral storage.
- Degree of parallelism and concurrent invocations.
- Blast radius of work retried on failure.

These two decisions interact but do not substitute for each other. A function with sound business boundaries can still pick an oversized batch; a small batch cannot fix a function with muddled business responsibilities.

## 2. Start from business capabilities

A business capability describes something the organization or product must deliver, such as:
- Accepting orders.
- Confirming payments.
- Checking inventory.
- Sending notifications.
- Processing documents.
- Generating reports.
- Updating delivery status.

A function should serve a meaningful business step expressible clearly as a verb plus noun. Examples: `validate-order`, `reserve-inventory`, `generate-thumbnail`, or `send-invoice-notification`.

One business capability does not strictly map to one function. A broad capability may span several functions coordinated by a workflow. Conversely, one function can contain multiple small technical operations if they serve one cohesive responsibility and belong together as one unit.

### Questions to locate boundaries

For each proposed function, ask:

- If this function fails, what business work should be retried?
- If a business rule changes, should another function need redeployment?
- Does the function require data permissions across multiple domains?
- Are inputs stable and versionable?
- Can outputs be verified independently?
- Can the function run multiple times without creating duplicate effects?
- Is there a clear team or service owner responsible for it?

If a single function confirms orders, deducts inventory, charges cards, creates shipping labels, and sends emails, an email outage could cause callers to retry the entire transaction. Those steps have different failure modes and consistency needs; usually they belong in distinct business steps coordinated via workflows or events.

## 3. Cohesion, coupling, and function size

### Cohesion

Cohesion measures how tightly internal parts serve a single purpose. High-cohesion functions typically:
- Have one primary reason to change.
- Have relatively compact, clear inputs and outputs.
- Require narrow access permissions.
- Can be tested against a single business outcome.
- Can be observed with a consistent set of metrics and logs.

### Coupling

Coupling measures dependencies across functions or domains. A function directly invoking several other functions can create synchronous dependency chains that raise latency and propagate failures.

Reduce coupling using:
- Versioned event contracts.
- Stable API contracts.
- Durable queues or event buses.
- Workflow orchestration when state and branching logic are needed.
- Idempotency and controlled retries.
- Avoiding shared internal database tables across domains when contracts can be used instead.

### Avoiding both extremes

| Design | Problem |
|---|---|
| One function handling the entire system | Hard to test, overly broad permissions, deploys affect unrelated domains, high timeouts and memory |
| One function per line of code or micro-step | Excessive network hops, complex orchestration, higher logging and invocation costs |
| Functions aligned to clear business steps | Clear ownership, testable, retriable by outcome; still requires contract and state discipline |

There is no universal optimal line count or function count. Choose size based on business responsibility, transaction boundaries, failure isolation, and communication overhead.

## 4. Choosing an architecture style: request-driven, event-driven, or workflow

### Request-driven functions

The function is called directly via HTTP/API or SDK. Fits when callers need an immediate reply.

Examples:
- Information lookups.
- Input validation.
- Submitting a processing request and returning a job ID.
- Short operations with immediate results.

Enforce deadlines, timeouts, and response contracts. Never hold a synchronous request open for a long duration if the work can run in the background.

### Event-driven functions

The function is triggered by events from object storage, queues, streams, database change feeds, or event buses.

Fits when:
- Producers do not need to wait for consumers to finish.
- Steps can retry independently.
- Workloads arrive in bursts.
- Queues are needed to absorb load.
- Domains need independent deployment schedules.

Events should include event ID, schema version, source, timestamp, and correlation ID where appropriate.

### Workflow orchestration

When a business process spans multiple steps, conditional branches, retries, timeouts, compensation, or human waits, use a workflow engine or state machine for coordination.

Example:

~~~mermaid
flowchart TD
    A["Receive order"] --> B["Validate order"]
    B --> C{"Valid?"}
    C -->|No| X["Return business error"]
    C -->|Yes| D["Reserve inventory"]
    D --> E{"Reserved?"}
    E -->|No| Y["Notify out of stock"]
    E -->|Yes| F["Authorize payment"]
    F --> G{"Payment succeeded?"}
    G -->|No| H["Release inventory"]
    G -->|Yes| I["Confirm order"]
    I --> J["Publish order-confirmed event"]
    J --> K["Notification function"]
~~~

Each step can be a separate function or a managed task. The workflow persists state and decides the next transition. Avoid chaining synchronous function-to-function calls as a homemade state machine when long-lived progress tracking is needed.

## 5. Function granularity along transaction boundaries

A function should keep operations that must succeed together inside one transaction boundary when they live within a data store supporting appropriate transactions.

For example, updating order status and writing an outbox event can share one database transaction. A function or relay then publishes from the outbox. This avoids committing the database while failing to emit the event.

Conversely, do not try to span a distributed transaction across a database, payment provider, and email service when those systems lack shared transactions. Use sagas or workflows with compensation instead.

### Decision questions

- Must these operations be all-or-nothing?
- Do they share a single database transaction?
- If one operation fails, can it roll back or must compensation run?
- Is eventual consistency acceptable?
- Should retries happen per step or across the entire business process?
- Does the user need visibility into step-by-step progress?

### Example

Order creation might consist of:
1. Validating input data.
2. Persisting the order in pending state.
3. Writing an outbox event within the same transaction.
4. Worker reserving inventory.
5. Payment authorization function.
6. Workflow confirming or cancelling the order.

Each step has explicit state and policy-driven retries. Never keep one invocation running for minutes waiting on every dependency.

## 6. Choosing the unit of work: single item, batch, or partition

This choice directly impacts execution duration, memory, concurrency, and retries.

### Single item per invocation

Each invocation processes one independent item:
- One image.
- One document.
- One order.
- One message.
- One change record.

Advantages:
- Strong failure isolation.
- Retries affect only one item.
- Straightforward attribution of logs, metrics, and idempotency keys.
- Easy parallel processing across items.

Limitations:
- Increases invocation count.
- Increases startup or orchestration overhead.
- Can increase database/API call volume.
- Creates high concurrency pressure during bursts.

Best when items take noticeable time, payloads are independent, or granular retries are required.

### Batch of multiple items per invocation

One invocation receives and processes multiple items:
- A batch of queue messages.
- A group of small files.
- A page of data.
- A set of records from a partition.

Advantages:
- Reduces invocation counts.
- Reuses connections and configuration lookups.
- Amortizes startup and dependency overhead.
- Raises throughput when item processing benefits from grouping.

Limitations:
- Larger payloads and memory footprints.
- Longer execution durations.
- One failing item can impact the whole batch without partial failure handling.
- Whole-batch retries can re-process already succeeded items.
- Oversized batches risk timeouts or OOMs.

Batches need caps on item count, total bytes, expected duration, and retry impact.

### Partitions

Partitioning splits a large dataset into independently processable slices, commonly by key, tenant, shard, or time window.

Fits when:
- Data volume is large.
- Per-key ordering must be preserved.
- Partitions can be processed in parallel.
- Checkpointing or resuming from a processed offset is required.

Design partition keys carefully to avoid hot partitions. If a single tenant generates 80% of traffic, partitioning strictly by tenant creates skew.

### Comparison

| Unit | Throughput | Failure isolation | Overhead | Primary risks |
|---|---|---|---|---|
| Single item | Can be high via parallelism | High | High invocation count | Concurrency spikes |
| Small batch | Good for lightweight items | Moderate/good with partial failure | Lower | Per-item retries |
| Large batch | Lowers overhead but raises latency | Lower | Low per item | Timeouts, memory, retry blast radius |
| Partition | Strong for large datasets | Per partition | More complex orchestration/checkpointing | Hot partitions and ordering stalls |

## 7. Sizing batches systematically

Do not pick a batch size merely to cut invocation count. Measure duration and memory as batch size varies.

Let:
- \(B\) be the number of items in a batch.
- \(t_0\) be the fixed per-invocation overhead.
- \(t_i\) be the average processing time per item.
- \(t_{total}\) be the expected batch duration.

A simple linear estimate:

\[
t_{total} \approx t_0 + B \times t_i
\]

If per-item processing times vary widely, use p95 or p99 rather than averages so batches do not regularly breach timeouts.

Example:
- Invocation overhead: 150 ms.
- Processing time per item: 40 ms.
- Batch of 10 items: roughly 550 ms.
- Batch of 100 items: roughly 4.15 seconds.

This is an illustrative linear model. Real workloads feature bulk APIs, connection reuse, caching, contention, and intra-batch parallelism that produce non-linear timing.

### Sizing against the timeout budget

Given maximum timeout \(T_{max}\), do not target an expected batch duration right against the limit. Leave margin for:
- Fetching input.
- Processing items.
- Writing outputs/checkpoints.
- Network jitter and dependency latency.
- Serialization and cleanup.
- Slow items or internal retries.

Target p95 batch duration well under a safe fraction of the timeout, then validate under load tests. The exact margin depends on workload variance and retry needs.

### Sizing against the memory budget

An estimate:

\[
Memory_{batch} \approx Memory_{base} +
B \times Memory_{perItem} + Memory_{overhead}
\]

Measure the real working set. If a function loads the entire batch into RAM and holds inputs, intermediate objects, and outputs simultaneously, peak memory can far exceed raw payload size.

Stream or chunk items instead of retaining the full batch in memory whenever possible.

### Sizing against retry blast radius

If one failing item triggers a whole-batch retry, larger batches waste more duplicate work. Partial batch responses, checkpoints, or per-item status tracking shrink retry scope.

If the platform lacks partial failure support, lean toward smaller batches or split independent items.

## 8. Choosing memory, CPU, and runtime sizing

In many function services, memory configuration simultaneously influences CPU allocation, network capability, or runtime limits. Exact relationships depend on the provider and function type.

### Memory sizing

Size memory for:
- Runtime and framework baseline.
- Input payload.
- Working set and intermediate structures.
- Native library overhead.
- Serialization/deserialization.
- Concurrency inside a single invocation.
- Network and file buffers.
- Peak memory across the batch.

Never size memory from averages. Measure peak or high percentiles under representative traffic, including the largest allowed batch.

### CPU sizing

Some platforms tie CPU to memory; others allow independent CPU selection or distinct compute tiers. Check:
- Actual CPU allocation.
- CPU-bound execution time.
- Single-thread performance.
- Concurrency within an invocation.
- CPU throttling or quotas.
- Effect of raising memory on execution duration.

When higher memory increases CPU share, invocations may finish faster and reduce total compute-seconds. Total cost per invocation may rise or fall depending on pricing meters. Benchmark both duration and cost.

### Ephemeral storage

Functions may have temporary storage for downloaded files, extracted archives, scratch data, or model caches. Ensure you:
- Measure peak disk usage.
- Delete temporary files after processing.
- Never use ephemeral disk for durable state.
- Check encryption and lifecycle policies.
- Avoid writing large files when streaming works.

### Runtime and cold starts

Runtime, package size, dependency initialization, and network attachments all impact cold starts. Large functions carrying many dependencies typically suffer longer startup and deployment times.

Optimize by:
- Packaging only necessary dependencies.
- Lazy-loading rarely used modules where suitable.
- Reusing connections/clients across execution environments when permitted by the runtime.
- Trimming work on the initialization path.
- Using provisioned/warm capacity when SLOs require it and cost fits.

Do not split logic into an ultra-tiny function solely to shave cold starts if doing so creates extra network hops and state handoffs.

## 9. Concurrency and throughput

Concurrency is the number of simultaneously running invocations. It affects throughput, downstream load, and total cost.

Estimated via Little’s Law:

\[
Concurrency \approx ArrivalRate \times AverageDuration
\]

For example, a function receiving 40 events/second with a 0.5-second average duration:

\[
Concurrency \approx 40 \times 0.5 = 20
\]

This represents steady-state average concurrency. Peaks, tail durations, and bursts require higher capacity.

### Concurrency limits

Monitor and control:
- Account/project quotas.
- Function-level reserved/max concurrency.
- Event source mapping concurrency.
- Queue/stream partition concurrency.
- Downstream connection limits.
- Database capacity.
- API rate limits.
- CPU/memory and storage.

If functions scale faster than databases, the bottleneck shifts from compute to the database. Use semaphores, connection pools, rate limiters, or queues to cap downstream load.

### Interaction between batch size and concurrency

Larger batches cut invocation count, yet each invocation holds memory longer. Low concurrency lets backlogs build. Tiny batches combined with massive concurrency generate storms of small requests and connections.

Benchmark across a `batch size × concurrency` matrix rather than tuning each setting in isolation.

## 10. Designing input and output contracts

A well-designed function has an explicit, versioned contract.

### Input contract

Should include:
- Event ID or request ID.
- Schema version.
- Business entity ID.
- Event type.
- Timestamp.
- Correlation/trace ID.
- Payload or payload reference.
- Required tenant/context metadata.
- Deadline or expiration, if applicable.

For large payloads, pass an object reference rather than embedding raw content inside the event. The function reads data from object storage using least-privilege permissions.

### Output contract

Define:
- Business result.
- Status.
- Structured error codes.
- Resource ID or artifact reference.
- Version.
- Correlation ID.
- Retryability or failure classification, where applicable.

Never return stack traces, secrets, or sensitive data to callers. Error messages should aid handling without exposing internals.

### Versioning

When evolving schemas:
- Make backward-compatible additive changes whenever possible.
- Never repurpose existing fields without bumping the version.
- Ensure consumers handle unsupported versions gracefully.
- Allow overlap windows where old and new producers/consumers run concurrently.
- Test against older events still sitting in queues or replays.

## 11. State, idempotency, and side effects

Functions are generally stateless across invocations. Never assume global variables or temporary files survive long-term or that calls always return to the same execution environment.

### Externalized state

Use databases, durable object storage, workflow state, or queues to store state that must outlive an invocation.

Never keep authoritative business state solely in function memory. Instances can be reclaimed, scaled to zero, or assigned unrelated events.

### Idempotency

Events can be redelivered after timeouts, network failures, or lost acknowledgements. Functions should handle repeated deliveries of the same event without duplicating side effects.

A simple pattern:
1. Extract the event ID or idempotency key.
2. Check whether the record has already been processed.
3. Persist processing state via a transaction or conditional write.
4. Execute the side effect.
5. Persist the outcome and completed state.
6. On failure, determine whether to retry or trigger reconciliation.

Simply checking “have I seen this ID?” before running side effects introduces race conditions when two invocations execute simultaneously. Use conditional writes, unique constraints, or appropriate locks/leases.

### Outbox pattern

When one transaction updates a database and must emit an event, write both business data and an outbox record inside the same database transaction. A publisher reads the outbox and emits the event. Consumers still need idempotency because messages may be emitted or received multiple times.

### Non-rollbackable side effects

Sending emails, charging payments, or calling external APIs often cannot be rolled back. Use:
- Idempotency keys.
- Provider transaction references.
- State machines.
- Compensating actions.
- Reconciliation jobs.
- Audit trails.

Never infinitely retry a side effect without knowing whether the previous attempt already succeeded.

## 12. Synchronous or asynchronous?

### Synchronous processing

Use when:
- Work is short.
- Callers need immediate results.
- Dependencies exhibit predictable latency.
- End-to-end execution stays safely within the timeout budget.

Return explicit errors when unable to complete. Do not hold requests open for long tasks that belong on a queue.

### Asynchronous processing

Use when:
- Work is long or variable.
- Traffic arrives in bursts.
- Eventual consistency is acceptable.
- Retries and dead-letter handling are needed.
- Callers only need a job ID or status handle.

An API can accept the request, save a job, and return HTTP 202 with a job ID. Workers execute asynchronously; callers poll status or receive callbacks/events.

### Workflows

Use workflows when handling multiple steps, branches, retries, timeouts, or compensation. Workflows manage state and overall deadlines; functions execute discrete, testable business activities.

## 13. Example: image processing and unit-of-work sizing

A service accepts user images and produces thumbnails, previews, and metadata.

### Business boundaries

Functions might include:
- Validating upload metadata.
- Scanning files.
- Generating image derivatives.
- Updating asset metadata.
- Publishing an asset-ready event.

Not every thumbnail resolution needs its own function. One derivative-generation function can produce multiple sizes from the same image if they share dependencies and failure boundaries.

### Unit of work

Option A: one invocation per image.
- Easy to retry a single image.
- Easy to measure duration and cost per image.
- Strong fit for large images with variable processing times.
- High invocation counts during bulk uploads.

Option B: batch of 10 images.
- Cuts overhead for small images.
- Reuses decoders/configuration.
- Requires partial failure handling.
- One huge image can slow down or OOM the whole batch.

Option C: one invocation processing an entire folder.
- Risks massive payloads and memory usage.
- Long timeouts.
- Broad retry scope.
- Unsuitable if folder sizes are unbounded.

You might use one image per message for large assets and small batches for lightweight thumbnails. This is a data-profile decision, not a rigid rule.

### Resource controls

Measure:
- p50/p95/p99 file sizes.
- Peak decode memory.
- CPU time by pixel count and format.
- Ephemeral disk used when extracting or generating multiple derivatives.
- Duration.
- Retry counts.
- Cost per accepted image.

Cap pixel dimensions and file sizes to defend against decompression bombs or resource-exhausting payloads. Verify actual file content and MIME type rather than trusting file extensions.

## 14. Example: order workflow

An order workflow can be split into steps:
- Validate order.
- Reserve inventory.
- Authorize payment.
- Confirm order.
- Send notification.

Each function handles one step and receives an event carrying the order ID and version. The workflow tracks current state.

### Why not lump everything together?

If the email provider goes down, you should not re-charge the card simply because a monolithic function timed out. If inventory was reserved but payment fails, inventory must be released via compensation. Each step deserves independent retries and timeouts.

### Why not split too finely?

If reading every field or toggling every status flag becomes a separate function invocation, network hops, IAM policies, logs, and orchestration explode. Grouping purely internal operations that share a transaction boundary usually makes more sense.

### State transitions

| State | Next action | On failure |
|---|---|---|
| RECEIVED | Validate | Return business error |
| VALIDATED | Reserve inventory | Retry or mark unavailable |
| RESERVED | Authorize payment | Retry with idempotency |
| PAID | Confirm order | Reconcile if commit status is uncertain |
| CONFIRMED | Publish event | Outbox retry |
| NOTIFIED | Complete | Notification can retry independently |

States must be persisted durably. Workflows need overall timeouts and policies for handling stuck states.

## 15. Example: choosing batch size for a queue consumer

Suppose a queue receives 600 messages/second. Each message averages 20 ms of CPU and 80 ms of I/O. The function timeout accommodates moderate batches.

### One message per invocation

If each invocation takes 100 ms, estimated average concurrency is:

\[
600 \times 0.1 = 60
\]

Invocation count is high, yet retries and isolation are clean. If dependencies have low connection limits, cap concurrency.

### Batch of 10 messages

If per-invocation overhead is 50 ms and each item takes 100 ms sequentially:

\[
t_{batch} \approx 50ms + 10 \times 100ms = 1.05s
\]

Average batch arrival rate is 60 batches/second. At 1.05-second duration:

\[
Concurrency \approx 60 \times 1.05 = 63
\]

Batching lowers invocation rate yet does not automatically reduce concurrency if each batch runs proportionally longer. If the function processes items in parallel inside a batch, duration drops while CPU, memory, and dependency load climb.

### Test systematically

Benchmark batch sizes of 1, 5, 10, and 20 across concurrency levels. Compare:
- Throughput.
- Queue age/backlog.
- p95/p99 duration.
- Peak memory.
- Dependency connection wait times.
- Partial failures and retries.
- Cost per successfully processed message.

Select the configuration that satisfies SLOs and dependency limits with headroom—not automatically the largest batch.

## 16. Platform limits that shape design

Each provider enforces specific limits on:
- Maximum execution duration.
- Memory range.
- CPU allocation.
- Ephemeral storage.
- Payload/request/response sizes.
- Concurrent executions.
- Invocation rate.
- Environment variables.
- Deployment package size.
- Number of layers/extensions.
- Event source batch size.
- Retry age/count.
- Network access and VPC configuration.

Never hard-code universal limit assumptions across providers. Check documentation for your specific service and region, then capture relevant limits in an architecture decision record.

### Designing within limits

- Split long jobs into multiple steps/checkpoints.
- Move large payloads to object storage and pass references.
- Cap batch sizes.
- Use queues to smooth bursts.
- Use workflows for long-lived processes.
- Keep state outside functions.
- Size memory/CPU from benchmarks.
- Cap concurrency to match downstream capacity.
- Use durable storage for outputs and checkpoints.

### Workloads outgrowing the function model

Consider container jobs, managed batch services, or long-running services when:
- Work runs longer than function timeouts.
- Continuous processes or long-lived connections are required.
- GPUs or custom drivers unsupported by function platforms are needed.
- Payloads/working sets exceed platform ceilings.
- Specialized filesystems or runtimes are needed.
- Steady, continuous load erases serverless cost advantages.
- Deep control over scheduling or host behavior is required.

## 17. Security along business boundaries

Functions should hold least-privilege permissions strictly scoped to their jobs.

Examples:
- `validate-order` only reads the catalog and writes validation results.
- `reserve-inventory` updates inventory without needing email-sending permissions.
- `notification` reads events and sends messages without permissions to alter payments.
- `image-processor` reads input objects and writes only to approved output prefixes.

### Separating permissions

Assign separate execution roles/service identities per function or per tightly related group sharing a responsibility. Avoid one shared admin role across an entire workflow.

### Input validation

- Validate schema and version.
- Verify tenant/owner authorization.
- Cap payload sizes.
- Inspect actual file content and MIME types.
- Distrust client-supplied metadata.
- Defend against replays or duplicates where required by business logic.
- Validate paths/object keys to prevent out-of-scope access.

### Secrets and sensitive data

Never embed secrets in code or images. Use secret managers or workload identities with rotation and scoped access. Keep PII, tokens, and sensitive payloads out of logs.

### Network boundaries

When functions connect to private databases or services, verify subnets, security groups/firewalls, NAT, and connection exhaustion. Attaching functions to a VPC/private network can affect cold starts, egress, and routing depending on the platform.

## 18. Observability by function and unit of work

Track metrics at both the function level and item level.

### Function metrics

- Invocation count.
- p50/p95/p99 duration.
- Errors and timeouts.
- Throttles.
- Concurrent executions.
- Cold starts.
- Peak or used memory.
- Retry count.
- Cost or resource-time.

### Unit-of-work metrics

- Items received.
- Items succeeded/failed.
- Partial batch failures.
- Per-item processing duration.
- Payload size.
- Retries per item.
- Dead-letter count.
- Queue age/backlog.
- Cost per accepted item.

### Correlation

Include:
- Request ID.
- Event ID.
- Business entity ID.
- Workflow execution ID.
- Correlation/trace ID.
- Function version.
- Schema version.

Avoid using high-cardinality business IDs as metric labels if your metrics backend cannot handle high cardinality. Place IDs in structured logs or trace attributes instead.

### Distinguishing function success from business success

An invocation may return success status while processing only 8 of 10 items. Track partial-success metrics so quality is not overstated.

Similarly, a function may return an error due to a downstream timeout even though side effects already committed. Idempotency and reconciliation reveal the true state.

## 19. Measuring efficiency and cost of unit sizing

Simple cost model for one invocation:

\[
C_{invocation} =
C_{request} + C_{resourceTime} + C_{network} + C_{dependency}
\]

Depending on the platform, request charges and resource-time may be metered separately or bundled. Dependency costs may show up under other services.

Cost per successful item:

\[
C_{item} =
\frac{TotalAllocatedCost}
{SuccessfulItems}
\]

When batches retry, include repeated invocations and wasted resource-time. Large batches cut per-request overhead while increasing retry waste.

### Trade-off example

| Configuration | Invocations/month | Average duration | Retry waste | Outcome |
|---|---:|---:|---:|---|
| Batch 1 | High | Short | Low per item | Easy retries, high overhead |
| Batch 10 | Moderate | Moderate | May need partial failure | Often balanced |
| Batch 100 | Low | Long | High if whole batch retries | Timeout and memory risks |

This table illustrates trends only; real figures depend on workload. Measure cost per successful item alongside latency, backlog, and failure rate.

### Do not optimize invocation count alone

Lowering invocation count does not cut total cost if:
- Duration climbs sharply.
- Memory must be bumped up.
- Batch retries duplicate lots of items.
- Queue age grows and forces extra capacity.
- Downstream systems have to scale up.
- Functions time out and abandon half-finished jobs.

Optimize for completed business outcomes and SLOs.

## 20. Testing function design

Before production, verify:
- Contract tests for inputs/outputs.
- Unit tests for business logic.
- Integration tests against databases/queues/storage.
- Idempotency tests when identical events arrive repeatedly.
- Concurrency tests for simultaneous duplicate events.
- Partial batch failure tests.
- Timeout and cancellation tests.
- Payload boundary tests.
- Memory/CPU/load tests.
- Retry storm and downstream throttling tests.
- Workflow compensation tests.
- Historical event replay and schema compatibility tests.

### Testing across data sizes

Use inputs covering:
- Minimum valid size.
- Median.
- p95.
- p99.
- Maximum allowed size.
- Malformed or invalid payloads.
- Payloads containing unusually high record/field counts.

Inspect peak memory and duration distributions rather than single samples.

### Chaos and failure testing

Simulate:
- Slow databases.
- External API timeouts.
- Queue redeliveries.
- Storage throttling.
- Abrupt function termination.
- Expired credentials.
- Slow workflow steps.
- One failing item mid-batch.

Verify state stays consistent, side effects do not duplicate, and retries remain bounded.

## 21. Step-by-step workflow for function design and sizing

1. **Describe business capability:** document the capability and expected outcome.
2. **Identify triggers:** HTTP, events, queues, streams, schedules, or workflows.
3. **Define boundaries:** transactions, side effects, and ownership.
4. **Define contracts:** schemas, versions, identities, and correlation.
5. **Choose unit of work:** item, batch, partition, or workflow step.
6. **Profile workload:** payload size, CPU time, memory, I/O, and duration.
7. **Size resources:** memory, CPU, ephemeral storage, and timeouts.
8. **Size concurrency:** match arrival rate, duration, and downstream capacity.
9. **Design retries:** idempotency, partial failures, DLQs, and compensation.
10. **Design state:** databases, object storage, workflows, or durable queues.
11. **Restrict security:** execution identity and least-privilege access.
12. **Benchmark:** matrix of `batch size × concurrency × resource size`.
13. **Measure unit cost:** cost per successful business output.
14. **Canary deploy:** watch SLOs, errors, backlogs, and cost.
15. **Review periodically:** adjust as payloads, demand, or dependencies evolve.

## 22. Quick selection matrix

| Workload profile | Starting unit of work | Orchestration style | Key watchpoints |
|---|---|---|---|
| Short API needing immediate reply | Single request | Synchronous | Deadlines and response latency |
| Large image or independent file | Single file | Queue/event | Memory, ephemeral disk, and retries |
| Small, independent records | Small batch | Queue/stream | Partial failures and concurrency |
| Stream requiring per-key ordering | Partition/key | Stream consumer | Partition count and hot keys |
| Multi-step business process | One business step per function | Workflow | State, compensation, and overall timeouts |
| Long-running batch | Chunk/checkpoint | Batch orchestrator | Resume, retries, and storage |
| CPU-heavy task | Bounded single task | Queue/worker | CPU allocation and execution limits |
| GPUs or specialized runtimes | Job/container if functions lack support | Batch/platform scheduler | Drivers, devices, and cost |
| Continuous background work | Worker service | Container/service | Idle cost and lifecycle |

Validate starting points with benchmarks and platform limit documentation.

## 23. Common anti-patterns

### Oversized function

A single function spans multiple domains and side effects:
- Broad IAM permissions.
- Hard to deploy independently.
- One shared timeout across unrelated business steps.
- Retries risk repeating earlier side effects.
- Unclear ownership and unit cost.

Split by business capability and transaction boundary.

### Overly granular function

Every tiny technical step becomes a separate invocation:
- Network hops and orchestration multiply.
- Logs/traces fragment.
- Request charges climb.
- Transactions become hard to uphold.
- Larger failure surface.

Consolidate purely internal operations sharing a lifecycle and failure boundary.

### Unbounded batches

No cap on item counts or payload bytes:
- Sudden memory spikes.
- Timeouts.
- Whole-batch retries.
- Climbing queue age and tail latency.

Bound batches by item count, byte size, and expected duration.

### Using global memory as business state

Execution environments may be reused, yet offer zero guarantee of persistence or routing back to the same instance. Use external durable state.

### Retrying an entire business process

If a late step fails, re-running every earlier side effect causes duplicates. Retry per step and enforce idempotency.

### Unchecked concurrency

Rapidly scaling functions can overwhelm databases and APIs. Set concurrency caps and backpressure.

### Optimizing cost while ignoring SLOs

Huge batches can cut request fees while blowing up p99 latency and retries. Evaluate cost per successful, on-time outcome.

## 24. Pre-production checklist

### Business logic and boundaries
- [ ] Function has a clear business responsibility.
- [ ] Transaction boundaries and side effects are defined.
- [ ] Inputs/outputs have explicit schemas and versions.
- [ ] Clear owner and least-privilege permissions are assigned.
- [ ] Workflows use orchestration for multi-step/stateful flows.

### Unit of work and resources
- [ ] Chose item, batch, partition, or workflow step intentionally.
- [ ] Batches cap both item count and payload bytes.
- [ ] Measured p95/p99 duration and peak memory.
- [ ] Memory/CPU/ephemeral storage match workload profile.
- [ ] Adequate headroom exists under timeouts and platform limits.
- [ ] Concurrency aligns with arrival rate and downstream limits.
- [ ] Burst traffic and oversized payloads have been load tested.

### Reliability
- [ ] Idempotency and deduplication are implemented.
- [ ] Partial batch failure handling exists where needed.
- [ ] Retries are bounded with backoff and jitter.
- [ ] DLQ or quarantine mechanisms are configured.
- [ ] Side effects have compensation/reconciliation paths.
- [ ] State is stored durably outside the execution environment.
- [ ] Explicit deadlines and cancellation handling are implemented.

### Operations and cost
- [ ] Invocation and item-level outcome metrics are emitted.
- [ ] Correlation IDs and structured logs are present.
- [ ] Dashboards cover duration, errors, throttles, concurrency, and backlog.
- [ ] Cost per successful item/request is measured.
- [ ] Budget/usage alerts and an owner are configured.
- [ ] Benchmarked across `batch size × concurrency × resource size`.
- [ ] Canary rollout, rollback, and runbooks are in place.

## Conclusion

Serverless function design should start from business capabilities and transaction boundaries, and only then decide whether each invocation handles a single item, batch, or partition. High-cohesion functions with clear contracts and least-privilege permissions reduce coupling and simplify testing. Choose unit-of-work size based on payloads, execution duration, peak memory, CPU, concurrency, retry blast radius, and platform limits. Larger batches trim overhead yet raise timeout, memory, and retry scope; smaller batches improve isolation yet multiply invocations and risk concurrency spikes. Measuring SLOs, throughput, queue age, partial failures, and cost per successful business output together yields configurations well matched to real workloads.
