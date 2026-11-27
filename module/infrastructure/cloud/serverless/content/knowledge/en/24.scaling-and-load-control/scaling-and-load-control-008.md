# Orchestrating large fan-out without causing call storms

In the **Scaling and Load Control** chapter, fan-out is how a single request or event splits into multiple child tasks that can run in parallel. This pattern is useful when an order must update multiple systems, a file must be processed in parts, or an event must be delivered to many consumers. However, firing thousands of calls simultaneously without limits can unleash a massive surge of load onto databases, external APIs, queues, or the serverless platform itself.

This lesson belongs to the **CLOUD_SERVERLESS** module, focusing on developing and deploying serverless applications—specifically Java functions triggered by HTTP, messages, or events. Learners handle triggers, state, access control, retries, idempotency, cold starts, scaling, and cost to determine when to use FaaS. Fan-out orchestration must leverage function scalability while controlling concurrency, invocation rates, retries, state, and dependency capacity.

## 1. What is fan-out?

Fan-out occurs when one parent job spawns many child tasks. For example, when a customer imports a file with 20,000 records, the system can split the file into smaller chunks and process them in parallel. An `OrderPlaced` event can also trigger tasks to send emails, update inventory, calculate loyalty points, and generate an invoice.

Fan-in is the step that aggregates results from multiple child tasks to determine whether the parent job is complete. Not every fan-out requires synchronous fan-in; many systems simply process each child task independently and record result status.

~~~mermaid
flowchart TD
    P["Parent request / event"] --> D["Split into child tasks"]
    D --> Q["Durable queue or workflow"]
    Q --> W1["Worker A"]
    Q --> W2["Worker B"]
    Q --> W3["Worker C"]
    W1 --> R["Result store"]
    W2 --> R
    W3 --> R
    R --> A["Completion / fan-in"]
~~~

Fan-out can boost throughput and reduce overall completion time when child tasks are independent. Yet the number of child tasks does not automatically equal the number of tasks that should run simultaneously. The system must decouple total work volume from maximum parallelism.

## 2. Why does unbounded fan-out cause call storms?

Suppose one event creates 5,000 child tasks. If the producer dispatches all of them immediately and each worker in turn calls three downstream APIs, one event can generate 15,000 nearly simultaneous requests. If one of those APIs slows down, requests linger longer, concurrency climbs, and retries amplify load further.

A call storm typically follows a chain of causes:

1. One parent request spawns too many child tasks.
2. Many functions are triggered at once.
3. Functions concurrently call a database or API with a lower quota.
4. The dependency slows down or throttles requests.
5. Workers time out and retry.
6. Retries inject extra request volume while the dependency is already overloaded.
7. Queue age, error rates, and costs climb rapidly.

Scale-out increases worker processing capacity, but it can also overload dependencies much faster. The goal of load control is to keep active work and call rates within bounds the entire system can sustain.

## 3. Distinguishing total tasks, concurrency, and request rate

Three quantities must be managed separately:

| Quantity | Meaning | Example |
|---|---|---|
| Fan-out width | Number of child tasks spawned from one parent job | One file creates 5,000 record tasks |
| Concurrency | Number of tasks running at the same time | Max 40 workers actively processing |
| Request rate | Number of requests sent per unit of time | Max 100 requests/second to an API |

Concurrency and request rate are related but not interchangeable. If each request takes only 5 ms, 20 concurrent workers can generate a very high request rate. If each request takes 5 seconds, the same 20 workers produce a much lower request rate.

An estimation rule from Little's Law:

\[
Concurrency \approx ArrivalRate \times AverageDuration
\]

Where `ArrivalRate` is incoming tasks per second and `AverageDuration` is average processing time per task in seconds.

If workers receive 50 tasks/second and each task takes 2 seconds on average, steady-state concurrency is roughly 100. When processing time climbs to 6 seconds, the same arrival rate can require roughly 300 concurrent slots. This is why a slow dependency drives concurrency up even when task creation rates stay constant.

## 4. Determining dependency limits before scaling out

Before choosing fan-out concurrency, understand the capacity of downstream systems:

- Does an external API enforce requests/second or per-tenant quotas?
- How many concurrent connections and queries can the database handle?
- Does the queue or stream have throughput, partition, or shard limits?
- Does the service enforce rate limits per credential or per account?
- Do peak hours or other batch jobs share the same quota?
- When throttled, what error does the dependency return, and does it include `Retry-After`?
- How many dependencies—and how many times—does a single child task call?

Do not use nominal quota directly as a concurrency cap without factoring in processing duration. An API allowing 100 requests/second does not mean 100 workers is the right limit. If a request averages 2 seconds, 100 requests/second can require roughly 200 in-flight requests.

Reserve headroom for interactive traffic, operational tasks, and latency variance. A batch workload should never consume all capacity and slow down live user-facing APIs.

## 5. Safe fan-out architecture

A common architecture includes these components:

- **Producer:** receives the parent job and spawns child tasks.
- **Queue or event bus:** persists and distributes tasks durably.
- **Worker:** processes a single task or task batch.
- **Concurrency control:** caps active workers.
- **Rate control:** caps dependency call rates.
- **Result store:** persists status and outcomes.
- **Retry/DLQ:** handles transient and persistent failures.
- **Fan-in coordinator:** aggregates results if business logic requires a barrier or completion event.

~~~mermaid
flowchart LR
    API["HTTP / Event"] --> P["Fan-out producer"]
    P --> Q["Queue / Event bus"]
    Q --> W["Bounded workers"]
    W --> RL["Rate limiter"]
    RL --> DS["Downstream APIs / DB"]
    W --> RS["Result store"]
    W --> DLQ["DLQ for poison tasks"]
    RS --> C["Completion coordinator"]
    C --> DONE["Parent completed"]
~~~

Queues create a buffer between task generation speed and processing speed. Workers pull work only while capacity remains. If downstreams slow down, queue age rises, while producers do not have to hold thousands of waiting connections open.

## 6. Choosing the right orchestration mechanism

| Mechanism | Best suited when | What to manage |
|---|---|---|
| Direct parallel calls | Small fan-out, low latency, bounded task count | In-flight limits, deadlines, and per-branch errors |
| SQS | Independent tasks needing buffering and retries | Visibility timeouts, batching, concurrency, DLQs |
| SNS/EventBridge | Broadcasting events to multiple consumers | Target retries, DLQs, filtering, and duplicates |
| Kinesis/DynamoDB Streams | Ordered data streams by partition/key | Shards, checkpoints, batch failures, and lag |
| Step Functions Map | Orchestration, state tracking, and fan-in needed | `MaxConcurrency`, execution history, and quotas |
| Custom workflows | Long-running, multi-step flows with compensation | State persistence, timeouts, and recovery |

Do not force one mechanism onto every fan-out pattern. When child tasks need independent retries and can run asynchronously, queues are usually the natural choice. When you must track each branch's step and complete the parent only after all branches finish, workflow orchestration may fit better.

## 7. Using queues as buffers

Queues decouple producer speed from worker speed. Producers can enqueue tasks quickly while consumers pull tasks at a sustainable pace.

Example processing flow:

1. API receives a file-processing request.
2. Producer records job metadata and generates child tasks.
3. Tasks are pushed to SQS.
4. Lambda event source mapping reads messages in batches.
5. Workers process with bounded concurrency.
6. Successful messages are deleted from the queue; failed messages retry per visibility timeout and redrive policies.
7. Messages exceeding retry thresholds move to a DLQ for investigation.

Queues do not make work vanish; they convert a sudden load spike into an observable backlog that drains over time. Set alerts on queue age and DLQ depth to detect when processing falls behind task creation.

### 7.1. Setting consumer concurrency limits

With AWS Lambda and SQS, you can tune event source mapping maximum concurrency where supported by your configuration. Function reserved concurrency can also cap total invocations. When a function has multiple event source mappings, sum all mapping caps and leave adequate headroom.

Do not set mapping concurrency higher than downstream capacity. Also avoid setting reserved concurrency so low that mappings inadvertently starve each other competing for capacity.

If using separate queues for workloads with different priorities, isolate worker functions or assign separate concurrency caps so batch workloads do not starve interactive tasks.

### 7.2. Visibility timeouts and batching

Visibility timeouts must be long enough for workers to process messages so redelivery does not occur while earlier processing is still running. Misconfiguration can cause the same message to be delivered to multiple workers simultaneously.

Larger batch sizes cut overhead but increase the amount of work impacted when a batch fails. With partial batch responses, workers report individual failed records so successful records do not retry with the batch; enable and test the event source mapping mechanism carefully.

## 8. Using Step Functions Map to cap parallelism

AWS Step Functions Map states run a processing step over a collection of items. You can set `MaxConcurrency` to cap how many items execute concurrently. Distributed Map fits larger datasets and can read items from supported data sources.

Conceptual configuration example:

~~~json
{
  "ProcessItems": {
    "Type": "Map",
    "ItemsPath": "$.items",
    "MaxConcurrency": 25,
    "ItemProcessor": {
      "StartAt": "ProcessOne",
      "States": {
        "ProcessOne": {
          "Type": "Task",
          "Resource": "arn:aws:states:::lambda:invoke",
          "End": true
        }
      },
      "End": true
    }
  }
}
~~~

This is a simplified Map structure; add `Parameters`/`Arguments`, `ResultPath`, or `ResultSelector` to match real inputs/outputs. For Distributed Map, configure `ProcessorConfig` and an appropriate item source. The value 25 is illustrative only, not a default limit or optimal setting.

`MaxConcurrency` limits active Map items. If each item spawns 100 parallel requests of its own, aggregate requests can still exceed downstream limits. Therefore, orchestration limits must pair with rate controls inside workers.

## 9. Fan-out via event buses and consumer isolation

When multiple systems care about one event, an event bus or pub/sub decouples producers from calling each consumer directly.

For example, `OrderPlaced` can be published once to:

- An inventory-update consumer.
- A notification consumer.
- An invoice-generation consumer.
- An analytics consumer.

Each consumer should have separate retry and dead-letter handling so email failures never block inventory updates. With EventBridge or SNS, configure retry policies, target permissions, and DLQs per service capabilities.

Event buses distribute events, but they do not automatically throttle each consumer's processing speed. If a target scales too fast, you still need concurrency caps, queue buffers, or rate limiters at the consumer.

## 10. Limiting fan-out right at the producer

Producers must control how many tasks are created and the size of each batch. Avoid loading a huge file into memory and creating tens of thousands of objects, futures, or HTTP requests at once.

Measures:

- Split inputs into bounded chunks.
- Stream data from object storage instead of loading everything onto the heap.
- Persist job metadata before emitting tasks.
- Cap the maximum number of tasks per parent job.
- Paginate or create tasks in batches.
- Use queue/bulk APIs instead of individual per-item requests whenever possible.
- Block recursive fan-out exceeding allowed depth or branching factors.

Producer limits do not replace worker limits. They prevent generating massive message volumes or state over short intervals and keep orchestration costs predictable.

### 10.1. Java batch-splitting example

~~~java
import java.util.List;

public final class TaskBatcher {
    private TaskBatcher() {
    }

    public static <T> void publishInBatches(
            List<T> items,
            int batchSize,
            BatchPublisher<T> publisher) throws Exception {

        if (batchSize <= 0) {
            throw new IllegalArgumentException("batchSize must be positive");
        }

        for (int start = 0; start < items.size(); start += batchSize) {
            int end = Math.min(start + batchSize, items.size());
            List<T> batch = List.copyOf(items.subList(start, end));
            publisher.publish(batch);
        }
    }

    public interface BatchPublisher<T> {
        void publish(List<T> batch) throws Exception;
    }
}
~~~

This example bounds items per publish call, though it still takes an in-memory `List`. For very large files, read and batch via streams or iterators instead of materializing the entire list upfront.

## 11. Limiting concurrent calls in Java

When a worker calls multiple dependencies, use a semaphore to cap in-flight calls within one process or execution environment.

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.Callable;
import java.util.concurrent.TimeoutException;

public final class LocalCallGate {
    private final Semaphore permits;

    public LocalCallGate(int maxInFlight) {
        if (maxInFlight <= 0) {
            throw new IllegalArgumentException("maxInFlight must be positive");
        }
        this.permits = new Semaphore(maxInFlight);
    }

    public <T> T call(
            Callable<T> operation,
            long waitMs) throws Exception {

        boolean acquired = permits.tryAcquire(waitMs, TimeUnit.MILLISECONDS);
        if (!acquired) {
            throw new TimeoutException("Local downstream capacity is full");
        }

        try {
            return operation.call();
        } finally {
            permits.release();
        }
    }
}
~~~

This semaphore limits calls inside one Java instance only. If Lambda scales to 100 execution environments and each permits 8 calls, aggregate concurrent calls can reach 800. Therefore, a local gate is not a global rate limiter.

Instantiate `LocalCallGate` once inside a reused worker/service object and inject it into branches sharing that limit. Creating a fresh semaphore per task gives every task its own permit pool and defeats the cap.

Pair local limits with event source/orchestrator concurrency caps or a shared rate limiter. If a downstream enforces an account-wide quota, compute limits across all workers sharing that account.

## 12. Rate limiting: capping requests over time

Rate limiting answers how many requests can be sent per second or per minute. Token bucket is a common algorithm:

- A bucket holds up to a maximum capacity.
- Tokens replenish at a defined rate.
- Each request consumes one or more tokens.
- When tokens run out, requests wait, are rejected, or return to the queue.

Token buckets allow short bursts up to bucket capacity while holding the long-term average to the refill rate. If an API allows 100 requests/second but tolerates bursts of only 20, the bucket can be configured to refill 100 tokens/second with a capacity of 20, depending on provider quota semantics.

Rate limiters can live in an API Gateway, service mesh, API client, Redis, or a shared coordination service. Across multiple Lambda environments, the rate limiter must match the real quota's sharing scope.

Do not sleep inside every Lambda invocation waiting for tokens if a queue can hold the work. Sleeping occupies invocations and concurrency while making zero progress. For async workloads, leaving messages in the queue for later processing is far more resource-efficient.

## 13. Backpressure and admission control

Backpressure signals producers when consumers or dependencies cannot keep up. Rather than piling on more work, the system slows producers, lowers concurrency, or rejects excess load.

Approaches:

- Use queue age to throttle task generation speed.
- Use visible message counts to pace batch producers.
- Lower worker concurrency when downstream latency or throttling rises.
- Enforce per-tenant quotas so one customer cannot monopolize capacity.
- Return HTTP 429 or 503 when synchronous APIs cannot accept more load.
- Use `Retry-After` or backoff hints when callers can honor them.
- Pause consumers or lower poll rates cleanly during incidents.

Place admission control before spending expensive resources. If a function spawns thousands of child events before discovering quota is exhausted, the queue already absorbed the backlog and storage/orchestration costs are still incurred.

## 14. Retries can amplify call storms

Retries recover from transient errors, yet they can overload the system further if all workers retry simultaneously.

For example, a downstream starts returning 429 throttles. If 1,000 workers all retry after exactly one second, they generate a new wave of 1,000 requests just before quota recovers.

Use:

- Exponential backoff.
- Random jitter to spread retry timestamps.
- Retry budgets or maximum attempt caps.
- Honoring `Retry-After` when provided by dependencies.
- Classifying transient vs. permanent failures.
- DLQs for tasks failing beyond attempt limits.
- Circuit breakers or load shedding when dependencies are down.

Never retry validation errors, permanent data errors, or `AccessDenied` as if they were network glitches. Place retries deliberately at specific layers; if SDKs, workers, and callers all retry independently, actual call counts multiply.

### 14.1. Exponential backoff with jitter

An illustrative formula:

\[
delay_n = random(0,\ min(maxDelay,\ baseDelay \times 2^n))
\]

Jitter prevents many workers from waking up at the exact same instant. Cap `maxDelay` and total retry duration against the workflow deadline.

With message queues, rather than sleeping inside handlers, let messages retry via visibility timeouts or platform retry policies. Avoid tight retry loops that make queues redeliver failing messages relentlessly.

## 15. Circuit breakers and load shedding

Circuit breakers track dependency failures and temporarily halt calls when error rates cross thresholds. Common states:

- **Closed:** requests flow through and failures are tracked.
- **Open:** requests are blocked for an interval so the dependency can recover.
- **Half-open:** a few probe requests are permitted to test whether the dependency has recovered.

Load shedding drops or rejects excess work instead of letting every request wait until timeout. Prioritize interactive tasks and drop or defer less urgent batch work.

In serverless, in-memory circuit breaker state applies only within one execution environment. Across many environments, each instance may hold a different state. When global circuit breakers or quotas are needed, use a shared mechanism or a central gateway/service—while avoiding introducing an overly fragile new dependency just for load control.

## 16. Idempotency and duplicate handling

Fan-out over queues and event buses typically provides at-least-once delivery semantics. A child task may be redelivered if a worker times out after writing results but before ACKing the message.

Every child task needs a stable idempotency key. Example:

~~~java
public record WorkItem(
        String parentJobId,
        String itemId,
        int operationVersion) {

    public String idempotencyKey() {
        return parentJobId + ":" + itemId + ":" + operationVersion;
    }
}
~~~

Keys must represent a single unique business operation. Never generate a new key on every retry, or redeliveries will be treated as brand-new work.

At the storage layer, use conditional writes or transactions to record task state. Mark tasks complete only after side effects execute or via proper outbox/transactional mechanisms. Idempotency stores need TTLs long enough to cover retry/redrive windows and potential event replays.

## 17. Fan-in and durable result aggregation

If a parent job must wait for all child tasks, do not keep a Lambda invocation open while thousands of tasks run. Invocations can time out, waste concurrency, and lose durable state.

Persist aggregate state:

- Parent job ID.
- Total tasks created.
- Succeeded task count.
- Failed task count.
- Pending or running task count.
- Start/end timestamps.
- Completion status or attention-needed flag.

When a child task finishes, workers record results and increment counters atomically/conditionally. Child status updates and completion recording should run inside a transaction if storage supports it, or via outbox/idempotent consumers so a child never finishes without incrementing the aggregate. Once all tasks reach terminal states, the coordinator emits `ParentCompleted` or `ParentFailed`.

Guard against duplicate updates: the same child completion event must never increment counters twice. Use child state and conditional transitions from `RUNNING` to `SUCCEEDED`/`FAILED` before updating aggregates.

For complex workflows, Step Functions or a workflow engine can manage state and handle retries/fan-in instead of building a custom coordinator from scratch.

## 18. Controlling recursive fan-out and fairness

A worker might emit further events that trigger another fan-out. Left unchecked, the system can spawn an exponential task tree.

For example, if each task spawns 10 child tasks to a depth of 4, total tasks reach thousands from a single root. Define:

- Maximum fan-out width.
- Maximum workflow depth.
- Which event types are permitted to spawn child events.
- Idempotency keys at each level.
- Total task budget per parent job.
- Event loop detection mechanisms.
- Per-tenant or per-customer quotas.

Fairness stops one tenant from monopolizing worker capacity. Use separate queues per tier, weighted scheduling, per-tenant concurrency, or per-API-key rate limits. Relying on a single global queue lets one tenant's huge batch stall every other tenant.

## 19. Payloads, batch sizes, and large data

Avoid passing huge payloads across every fan-out hop. Messages should carry identifiers and references to durable data.

Example message:

~~~json
{
  "parentJobId": "job-2026-001",
  "itemId": "part-00042",
  "source": {
    "bucket": "processing-input",
    "key": "jobs/job-2026-001/input.jsonl"
  },
  "operationVersion": 3
}
~~~

Workers read just the designated slice from object storage. This shrinks message sizes and avoids copying heavy payloads across repeated retries.

Large batch sizes cut invocation overhead but raise memory and per-batch duration. Overly small batches inflate invocation counts and orchestration costs. Benchmark against payload sizes, failure rates, and partial batch response support.

When processing records independently, batch workers should persist results per record or use partial batch failures so one bad record never discards progress on succeeded records.

## 20. Observing a fan-out workflow

Every parent job should carry a correlation ID; every child task should carry a child ID and idempotency key. Logs and traces must link parents to children to investigate failing branches.

Metrics to track:

- Average and maximum fan-out width.
- Total tasks spawned per parent job.
- Active concurrency and request rates.
- Queue depth and age of oldest message.
- Downstream latency, 429/5xx errors, and connection counts.
- Retry counts, duplicate counts, and DLQ depth.
- Fan-in completion time and incomplete job counts.
- Cost per parent job or per succeeded item.

Avoid using parent IDs, child IDs, or customer IDs as metric dimensions when cardinality is high. Log/trace IDs in controlled logs/traces while keeping metric dimensions low-cardinality such as function, environment, operation type, and result.

A dashboard showing only Lambda Duration misses queue backlogs and stalled fan-ins. Monitor the entire path from producer to final outcome.

## 21. Protecting the system with quotas and priorities

Not all tasks share the same priority. A system can classify work as:

- Interactive: users waiting for responses.
- High-priority async: business operations needing fast completion without holding an HTTP connection.
- Batch: high volume, deferrable.
- Background maintenance: runs on spare capacity.

Each class can use its own queue or concurrency allocation. Reserve capacity for interactive traffic and enforce quotas on batches. If every task class shares one concurrency pool, a large import can throttle customer order APIs.

Quotas need owners, explicit limits, usage metrics, and change procedures. Do not rely solely on static config values; watch trends to know when to scale capacity or trim fan-out.

## 22. Costs of fan-out

Costs scale with task counts, invocations, execution duration, messages, state transitions, data transfers, and logs.

Common cost drivers:

- Lambda invocations and GB-seconds.
- SQS requests and message storage duration.
- EventBridge event/target deliveries.
- Step Functions state transitions or workflow executions.
- Database reads/writes for idempotency and result stores.
- Data transfer and object storage.
- Retries, duplicate processing, and DLQs.
- Log/trace ingestion.

One parent job spawning 100,000 child tasks can incur substantial orchestration costs even when each task is tiny. Batching reduces overhead but must balance failure isolation and latency.

Measure cost per parent job, per completed child task, and per business unit. A faster worker configuration that triggers frequent retries can cost more than a slower, steadier configuration.

## 23. Example fan-out orchestration for file processing

A large file-processing pipeline can be designed as follows:

1. API creates a `ParentJob` in `ACCEPTED` state.
2. Producer reads file metadata and determines partition count.
3. Producer dispatches tasks in batches to a queue.
4. SQS event source mapping caps worker concurrency.
5. Worker pulls a task, reads its partition, and processes under rate limits.
6. Worker persists results using an idempotency key.
7. Worker emits `ChildCompleted` once results are durable.
8. Coordinator updates completed task counts.
9. Once all partitions finish, coordinator marks `ParentJob` `COMPLETED`.
10. Tasks failing past retry limits route to a DLQ, and the parent job is marked `NEEDS_ATTENTION` or `FAILED` per policy.

For files with millions of records, you do not need one message per record. Split into appropriately sized partitions or chunks, and let workers process each chunk. Choose chunk size by benchmarking memory, duration, and retry costs.

## 24. Common mistakes

**Spawning all child tasks at once:** Triggers bursts on queues, orchestration, and downstreams. Batch, pace producers, and use buffers.

**Capping concurrency alone:** Short requests can still drive excessive RPS. Add rate limiting.

**Treating local semaphores as global quotas:** Every execution environment holds its own semaphore. Use event source caps or shared rate limiters.

**Letting workers retry immediately:** Many workers retry in lockstep and sustain throttling. Use backoff, jitter, and retry budgets.

**Holding parent invocations waiting on all children:** Consumes concurrency and risks timeouts. Persist fan-in state durably or use a workflow engine.

**Lacking idempotency:** Redelivered messages produce duplicate side effects. Use stable keys and conditional state transitions.

**Overly large batches:** One bad record forces retries across many succeeded records. Use partial batch responses and measurement-driven batch sizes.

**Unbounded recursive fan-out:** One event can trigger exponential task growth. Cap depth, width, and total budgets.

**Sharing one queue across all load types:** Batches can stall interactive work. Separate queues and quotas by priority.

**Ignoring queue age:** Workers look healthy while backlogs grow endlessly. Monitor age, depth, and throughput.

**Neglecting DLQs:** Failed tasks go forgotten or mass-redriving causes another storm. Investigate, fix root causes, and redrive in controlled batches.

**Passing huge payloads inside messages:** Inflates costs and risks payload-size limits. Pass object references and partition metadata.

## 25. Pre-release checklist for large fan-out

- [ ] Total fan-out width and branching factors have been estimated.
- [ ] Maximum child task count per parent job is capped.
- [ ] Fan-out depth is bounded and event loops are prevented.
- [ ] Maximum worker concurrency is defined.
- [ ] Maximum request rate per downstream is defined.
- [ ] Local semaphores are not mistaken for global rate limiters.
- [ ] Queues or workflow buffers decouple producer and consumer speeds.
- [ ] Event source mapping and function concurrency are aligned.
- [ ] Batch sizes match memory, duration, and partial failure requirements.
- [ ] Visibility timeouts, retries, DLQs, and redrive policies are tested.
- [ ] Retries use backoff, jitter, budgets, and error classification.
- [ ] Child tasks carry stable idempotency keys.
- [ ] Fan-in state is durably stored and updated idempotently.
- [ ] Large payloads live outside messages and are passed by reference.
- [ ] Quotas/fairness exist per tenant or workload class.
- [ ] Metrics track queue age, concurrency, RPS, throttles, and DLQs.
- [ ] Load tests and downstream failure tests run in isolated environments.
- [ ] Cost per parent job and per successful task is estimated.
- [ ] Controlled batch DLQ redrive procedures exist.
- [ ] Plans exist to shed load, pause, or roll back if dependencies overload.

## Conclusion

Fan-out harnesses serverless parallelism, yet total tasks, concurrency, and request rates must be bounded across distinct layers. Queues or workflow engines provide buffering and durable state; event source concurrency caps protect workers; rate limiters shield downstream quotas; backpressure, jittered retries, and circuit breakers help the system respond when dependencies slow down.

In Java, semaphores bound calls within one execution environment, not globally when functions scale out. Child tasks need stable idempotency keys, fan-in requires durable state, and metrics must span from producers to final outcomes. Proper orchestration enables processing massive volumes while maintaining load bounds, reliability, and predictable costs.
