# Orchestrating Fan-Out, Fan-In, and Limiting Child Task Concurrency

## Learning objectives

After this lesson, you will be able to:

- Explain fan-out and fan-in in a serverless workflow and recognize suitable use cases.
- Design workflows that run multiple child tasks in parallel, collect outcomes, and aggregate status.
- Distinguish waiting for all tasks, accepting partial results, quorum, and early termination.
- Limit child task counts, concurrency levels, and downstream call rates to prevent overload.
- Handle timeouts, retries, duplicate tasks, partial failures, and cancelling remaining tasks.
- Implement Java handlers for individual child tasks and choose coordination mechanisms aligned with function lifespans.

## 1. Why use fan-out and fan-in?

A workflow typically begins with a business request and executes one or more steps. Some steps must run sequentially because later steps depend on earlier results. However, many cases allow a step to be split into multiple independent units of work.

For example, a customer uploads 30 product images. The system needs to generate thumbnails for each image, extract metadata, scan content, and update the collection status. Generating the thumbnail for the first image does not depend on finishing the second image. Running sequentially makes total duration grow linearly with the processing time of all images.

**Fan-out** splits a job into multiple child tasks that can execute independently or in parallel. **Fan-in** is the convergence step: waiting for, collecting, or aggregating child task outcomes so the parent workflow can decide the next step.

~~~mermaid
flowchart TD
    A[Receive collection processing request] --> B[Fan-out: create 30 child tasks]
    B --> C1[Image task 1]
    B --> C2[Image task 2]
    B --> C3[Image task 3]
    B --> C4[Image task ...]
    C1 --> D[Fan-in: collect results]
    C2 --> D
    C3 --> D
    C4 --> D
    D --> E[Aggregate status]
    E --> F[Mark collection completed]
~~~

In a serverless model, each child task can be executed by a separate Java function, a message consumer, or a child workflow. The workflow engine manages task creation, status tracking, and fan-in coordination. Individual functions may run on different instances; an instance's memory is never the place to store overall workflow state.

Fan-out/fan-in commonly appears in:

- Processing individual invoice lines or order line items.
- Thumbnail generation, transcoding, or analyzing multiple files.
- Calling multiple independent services to gather quotes or data.
- Evaluating multiple independent rules prior to approval.
- Running processing steps per customer, account, or data partition.
- Generating reports from multiple data sources and aggregating the results.

Not every workload benefits from fan-out. If steps have sequential dependencies, splitting creates no useful parallelism. If task counts are tiny and operations are very fast, orchestration overhead can outweigh the benefits.

## 2. The fan-out/fan-in model in workflows

A parent workflow typically executes four main phases:

1. Prepare inputs and identify the set of work units.
2. Create or schedule child tasks.
3. Collect status and outcomes according to a join policy.
4. Aggregate results, update business state, and continue or terminate.

~~~mermaid
flowchart TD
    A[Parent workflow] --> B[Normalize input]
    B --> C[Split into work units]
    C --> D[Fan-out with concurrency limit]
    D --> E[Child workflow or function]
    E --> F[Fan-in per join policy]
    F --> G{Completion criteria met?}
    G -->|Met| H[Aggregate and continue]
    G -->|Not met| I[Handle error or compensate]
    H --> J[End workflow]
    I --> J
~~~

### 2.1. Parent workflows and child tasks

The parent workflow coordinates the overall business process. A child task (or child workflow) processes a single specific unit of work. A child's input should suffice to perform its work without needing to know the parent's entire internal state.

Image collection example:

- The parent receives `collectionId`, determines the list of images to process, and spawns one task per `imageId`.
- Each child receives `collectionId`, `imageId`, transformation type, and configuration version.
- The child reads the file from object storage, generates the thumbnail, stores the output, and returns metadata.
- The parent collects child statuses, counts succeeded/failed images, and updates the collection.

Each child should have a stable identifier, such as `taskId` or the pair `collectionId + imageId`. This identifier aids idempotency, logging, retries, and status lookup.

Never pass entire binary files or huge payloads through workflow state. Pass an object key, internal URI, or record ID; let the child read data directly from authorized storage. That shrinks message sizes, workflow history, and serialization overhead.

### 2.2. Static fan-out vs. dynamic fan-out

**Static fan-out** occurs when branches and tasks are known in advance. For example, a workflow always calls three services: inventory check, address verification, and tax calculation. Each branch runs in parallel and joins before confirming the order.

**Dynamic fan-out** occurs when the number of tasks is determined from input data or at runtime. For example, a report may cover tens of thousands of accounts to aggregate. The workflow reads the account list and spawns children per account or per batch.

| Characteristic | Static fan-out | Dynamic fan-out |
|---|---|---|
| Number of branches | Known upfront in workflow definition | Determined at runtime |
| Example | Calling three independent check services | Processing every file in a directory |
| Cardinality variability | Low | High |
| Limiting mechanism | Configure each branch | Limit item count, batch size, and concurrency |
| Observability | Each branch has a fixed name | Requires item IDs and correlation IDs |

Dynamic fan-out is commonly implemented using Map states, parallel collections, child workflows, or queue consumers. Feature names vary across platforms, yet the principle is identical: each element or batch becomes an independent unit of execution, while the parent workflow manages convergence.

### 2.3. Fan-out does not mean spawning infinite instances

A common design mistake is spawning a child for every element without capping total count or concurrency. If an input contains 100,000 items, the workflow can trigger massive simultaneous invocations and overwhelm databases, third-party APIs, or cloud account quotas.

Separate three distinct concepts:

- **Cardinality:** total number of child tasks created for a workflow.
- **Concurrency:** number of tasks executing simultaneously at a given moment.
- **Throughput:** number of tasks completed per unit of time.

For instance, a workflow may have 10,000 children while allowing at most 50 children to run concurrently. Cardinality is 10,000; max concurrency is 50. Throughput also depends on average processing time, provisioning speed, retries, and downstream capacity.

Capping concurrency does not automatically bound total child count. Conversely, capping total children does not protect downstream services if many workflows run concurrently. Designs must consider both per-workflow limits and system-wide limits.

## 3. Fan-in and join policies

Fan-in determines when the parent workflow can proceed and which results qualify as sufficient. A workflow must select a join policy driven by business requirements; never assume every task must succeed in every case.

### 3.1. Join all: waiting for every task

Join all completes only once every child has reached a terminal state. The parent gathers both successes and failures, then applies an aggregation policy.

This is a business-level join policy. Some workflow engines default to fail-fast: when one branch fails, the parent execution may immediately fail without waiting for sibling branches. If you need to collect outcomes from every child, configure error handling within each branch so errors become aggregatable results, or use catch/continue constructs supported by your platform.

~~~mermaid
flowchart TD
    A[Fan-out 4 children] --> B[Child A]
    A --> C[Child B]
    A --> D[Child C]
    A --> E[Child D]
    B --> F{All children finished?}
    C --> F
    D --> F
    E --> F
    F -->|No| G[Wait for remaining results]
    G --> F
    F -->|Yes| H[Aggregate results]
~~~

Join all fits when every element is mandatory—such as generating all line items of a financial report or processing every file in an inventory audit batch.

Distinguish “all finished” from “all succeeded”. When a child fails, the workflow can:

- Retry the child according to its retry policy.
- Wait for other children to finish and produce a partial report.
- Immediately fail the workflow and request cancellation of remaining children.
- Run compensations for children that already committed business side effects.
- Transition the workflow to a manual intervention state.

Define the policy upfront so the workflow never hangs indefinitely if one child never responds.

### 3.2. Join any: needing only one result

Join any lets the parent proceed as soon as one child meets the success condition. For example, finding one of several service replicas able to serve a request, or querying multiple data providers and taking the first valid response.

Once a result is obtained, remaining children can be cancelled if supported by the platform, or allowed to finish with their results discarded. Cancelling a workflow does not guarantee an in-flight call to an external system stops immediately. Already-started children should support cancellation or check cancellation state before executing subsequent side effects.

Join any must also define what “success” means. The earliest arriving response might be invalid, incomplete, or fail business criteria. The parent may need to wait for the first *valid* result rather than literally the first response.

### 3.3. Join by quorum or threshold

Some business flows require only a certain count or proportion of results. For example, a content moderation system runs five independent classifiers and needs at least three agreements before flagging content for review. Or a pricing service accepts quotes once at least two of three suppliers return valid prices.

Quorum conditions can be expressed as:

- Succeed when valid child count reaches at least `k`.
- Fail when remaining potentially successful children cannot possibly reach `k`.
- Time out if a deadline expires before reaching `k`; the parent applies its defined termination policy.

Given `n` total children, `s` already succeeded, and `r` children still capable of succeeding (pending, running, or awaiting retry), quorum `k` becomes unreachable whenever `s + r < k`. At that point the parent can terminate early per policy.

Quorum works well when sources are genuinely independent, yet it does not replace evaluating individual source quality and reliability. If children share a common underlying dependency or data source, they are not truly independent.

### 3.4. Fan-in result aggregation

After joining, the parent may need to:

- Count succeeded, failed, and skipped children.
- Compute sums or averages from outputs.
- Merge metadata from each child.
- Select the highest-priority result.
- Build an error report and list of items needing reprocessing.
- Update final business state.

It is unnecessary to hold every child payload in memory or workflow history. For large result sets, children write results to a database or object storage, while the parent collects only IDs, statuses, and result locations. A reduce step can read data in batches to aggregate.

### 3.5. Result ordering

Children may finish in an order different from input order. If the business requires preserving original order, pass an `itemIndex` or sort key with each child. The parent sorts outputs by that key before returning.

Never assume completion order equals processing order. With asynchronous tasks, ordering shifts due to network latency, retries, scheduling, and varying processing times.

### 3.6. Safe fan-in when using queues

When a parent dispatches children via a queue, messages can arrive duplicated, out of order, or redelivered after a worker already finished. Therefore, never simply increment a counter each time a completion message arrives. A duplicate message can push the counter past the actual child count and cause the parent to mark the job complete prematurely.

A durable aggregator can use a child-status table keyed uniquely by `taskId`. Upon receiving a result, the aggregator performs a conditional state transition—for example, transitioning from `RUNNING` to `SUCCEEDED` or `FAILED` at most once. The completion counter updates only if that state transition actually occurred. Saving child status and updating the counter should happen in the same transaction or use an equivalent consistency mechanism.

The parent must also know whether fan-out has finished dispatching all children. If the parent sends 100 messages while the aggregator has seen 99 completions, it cannot tell whether the 100th message is delayed or the parent is still creating children. For a pre-known list, store `expectedCount` and all task IDs before letting the aggregator evaluate completion signals. For streaming lists, use a `dispatchClosed` flag or an atomically updated outstanding counter: complete only when the producer is closed and every child has reached a terminal state.

Once completion criteria are met, the aggregator signals the parent via an idempotent operation—such as a uniquely keyed completion record or transactional outbox. That way, redelivered completion messages will not trigger multiple state transitions on the parent workflow.

## 4. Limiting cardinality and concurrency

Capping child tasks is a workflow design responsibility, not merely an operational knob. A workflow may process hundreds or thousands of items, yet the system must control how many jobs are created, how many run concurrently, and how fast they call downstream dependencies.

### 4.1. Per-workflow limits

If the workflow engine supports Map states or dynamic parallelism, configure maximum concurrency on the map branch. For example, 5,000 files can be split into children while permitting only 40 children to run concurrently.

A rough estimation formula:

`throughput ≈ concurrency / average_duration`

If each child takes 2 seconds on average and concurrency is 40, theoretical throughput is around 20 children per second. Actual throughput can be lower due to scheduling overhead, platform limits, retries, database latency, and resource contention. Never substitute this formula for load testing; use it only for initial sizing.

### 4.2. System-wide limits

Capping a workflow at 40 children does not mean the system runs only 40 children. If 100 workflows run concurrently, total concurrency can reach 4,000. When a downstream service can sustain only 200 concurrent requests, per-workflow caps alone will still overload it.

Coordinate limits across multiple layers:

- **Workflow-level concurrency:** caps concurrent children within a single workflow.
- **Global concurrency:** caps total invocations or workers across the entire service.
- **Per-tenant concurrency:** prevents one large tenant from starving all resources.
- **Rate limit:** caps request rate over a time window.
- **Downstream quota:** respects limits of databases, payment APIs, AI services, or external providers.

If the platform lacks a shared global cap across workflows, use a queue with a fixed number of consumers/workers, a distributed semaphore, or a centralized token-issuing mechanism. Distributed mechanisms require leases/expirations so a crashed worker does not hold a lock forever.

### 4.3. Using queues to absorb load

For very large fan-outs or bursty arrivals, queues decouple work creation rate from processing rate. The parent publishes one message per item or per batch. Workers pull messages only when capacity is available. The queue buffers pending work and meters delivery smoothly.

~~~mermaid
flowchart LR
    A[Parent workflow] --> B[Split into batches]
    B --> C[Work queue]
    C --> D1[Java worker 1]
    C --> D2[Java worker 2]
    C --> D3[Java worker N]
    D1 --> E[Result store]
    D2 --> E
    D3 --> E
    E --> F[Fan-in or aggregator]
~~~

Queues provide buffering, not automatic fan-in. The parent still needs to know how many items were created, which items finished, and when the job completes. Use a job/item status table, a workflow engine waiting on a completion signal, or an aggregator tracking processed counts.

Because messages can be redelivered, workers must be idempotent. Monitor queue depth, age of the oldest message, publish/consume rates, and DLQ message counts.

### 4.4. Batching to reduce overhead

Spawning one child per record can skyrocket invocations and state transitions. Instead of 100,000 children for 100,000 rows, split into 1,000 batches of 100 rows each.

Batch size is a trade-off:

- Small batches enable finer-grained retries, shorter per-child durations, and smoother load distribution.
- Large batches reduce scheduling and invocation overhead, but increase memory usage, processing duration, and retry blast radius on failure.
- Oversized batches risk hitting function timeouts or memory limits.
- Tiny batches can make orchestration and messaging overhead larger than actual processing cost.

When a batch can fail partially, outputs should record per-item status or a list of failed items. Do not mark an entire batch successful if only part of its items finished.

### 4.5. Backpressure and reacting to downstream overload

Backpressure slows down work emission or consumption when downstream components run out of capacity. Techniques include:

- Reducing worker concurrency.
- Pausing or throttling publish rates.
- Enqueueing work instead of calling directly.
- Honoring `429` responses and `Retry-After` headers from external APIs.
- Using circuit breakers to temporarily halt calls to continuously failing services.
- Isolating pools or queues by workload type so heavy tasks do not block lightweight ones.

Never blindly increase concurrency when queue depth rises without diagnosing the cause. If the database is already overloaded, adding workers only causes more failures and triggers even more retries.

## 5. Error handling, timeouts, and retries at the child level

In fan-out, every child can have a different outcome. The parent must track per-child status and distinguish recoverable errors, business errors, and failures requiring intervention.

### 5.1. Explicit child states

A simple state model:

| State | Meaning |
|---|---|
| `PENDING` | Created but not yet started |
| `RUNNING` | Currently executing |
| `SUCCEEDED` | Completed successfully |
| `RETRY_WAIT` | Waiting for the next retry attempt |
| `FAILED` | Failed after exhausting retries or unrecoverable error |
| `CANCEL_REQUESTED` | Parent requested cancellation |
| `CANCELLED` | Child confirmed it stopped |
| `TIMED_OUT` | Exceeded execution deadline |

These states are illustrative. A system may use fewer states, provided it distinguishes unstarted, running, completed, and cancelled tasks. The `FAILED` state should also store an error code and diagnostic details for investigation.

### 5.2. Retry individual children, never restart the whole group blindly

Suppose 100 children run and only 3 fail due to transient network errors. If the parent restarts all 100 children, already-succeeded tasks get re-executed. That wastes resources and risks duplicate business side effects.

Retry at the individual failed child or batch level. Apply exponential backoff, jitter, and maximum attempt caps. Classify errors:

- **Transient errors:** timeouts, network glitches, `429`, `5xx` can be retried per policy.
- **Business errors:** invalid data, entity not found, business rule violations; typically return a failure outcome instead of infinite retries.
- **Configuration/permission errors:** missing permissions, wrong endpoint or secret; fix configuration before retrying.
- **Unknown errors:** a timeout after sending a request may mean the operation succeeded while the response was lost; check status or use an idempotency key before retrying.

Multiple layers may retry on their own: SDK, HTTP client, queue trigger, and workflow engine. If each layer retries multiple times, total dependency calls multiply. Define a unified retry policy, align timeouts, and avoid simultaneous uncoordinated retries across every layer.

### 5.3. Idempotency for child tasks

At-least-once delivery and retries can cause a child to execute multiple times. Side-effecting tasks need a stable idempotency key, such as:

`taskKey = workflowId + ":" + itemId + ":" + operationVersion`

Upon receiving a request, the child checks the key in durable storage. If an outcome is already recorded, the child returns the cached result or current status. Otherwise, it executes the operation and persists the result in an appropriate transaction.

Never generate a new idempotency key on every retry, or the system cannot tell it is the same unit of work. If an item legitimately needs reprocessing due to a configuration or data fix, include a business version in the key to distinguish an intentional new run.

Never rely on static variables or in-memory caches inside a Java function for deduplication. The next invocation may run on a different instance or after the previous instance was reclaimed.

### 5.4. Timeouts and runaway children

Every child needs its own timeout; the parent also needs an overall deadline. Child timeouts free up concurrency slots and prevent workflows from hanging indefinitely. Parent deadlines ensure processes reach an end state or escalate to manual review.

When a child calls an external service, a client-side timeout does not prove the service aborted the work. The request may have reached the server and kept running. For long operations, obtain a job ID from the target service and poll/check status instead of holding an HTTP request open.

Upon timeout, a child may be marked `TIMED_OUT`, yet before retrying or compensating, verify whether the side effect already happened. This is vital for payments, shipping labels, or commands sent to systems without distributed transactions.

### 5.5. Partial failures and termination policies

If 97 children succeed and 3 fail, the workflow can apply different policies:

- **All-or-nothing:** consider the workflow complete only if every child succeeds; already-committed side effects require compensation on failure.
- **Partial success:** record successful items, list failed items, and allow targeted retries.
- **Best effort:** auxiliary tasks may fail without blocking the main flow, while errors remain monitored.
- **Quorum:** proceed once a valid result threshold is met.

Do not use a single `COMPLETED` status if callers must distinguish full completion from partial completion. Use `SUCCEEDED`, `PARTIALLY_SUCCEEDED`, `FAILED`, or equivalent business statuses.

### 5.6. Cancelling remaining children and compensation

Once join any or quorum is satisfied, the parent can request cancellation of remaining children. If a workflow fails, the parent can also cancel unstarted or pending tasks.

Cancellation is typically asynchronous. Children should check a cancellation token or status before executing side-effecting steps. A child already running an external call may not stop immediately; the system must have a way to reconcile its final outcome.

Compensation applies when a child has already committed a business side effect that the process must undo. For instance, if a batch of orders reserved inventory and the parent decides to cancel the whole batch, corresponding children may need to release stock. Compensations must also be idempotent and can fail; the parent must track compensation state and escalate to manual review when needed.

### 5.7. Dead-letter queues

After exceeding retries, messages can be routed to a dead-letter queue (DLQ). The DLQ preserves details for investigation and controlled replay. When handling DLQs:

- Identify and fix root causes before replaying.
- Preserve item ID, workflow ID, event ID, and attempt count.
- Verify idempotency before re-executing side effects.
- Never bulk-replay if the downstream service is still failing.
- Update both child and parent status after manual resolution or successful replay.

A DLQ is not an unmonitored dumping ground for failed jobs. Alert when messages enter the DLQ, define retention policies, and establish triage procedures.

## 6. Java examples for child tasks and parallel processing

A Java function should generally process a single well-defined unit of work. The workflow engine or queue handles spawning multiple invocations and managing fan-out/fan-in state.

### 6.1. Data model for child tasks

A message for a child can carry workflow ID, item ID, operation version, and correlation ID:

~~~java
import java.time.Instant;

public record WorkItem(
    String workflowId,
    String itemId,
    int itemIndex,
    String operationVersion,
    String correlationId,
    String objectKey,
    Instant deadline
) {}

public record WorkResult(
    String workflowId,
    String itemId,
    int itemIndex,
    String status,
    String resultKey,
    String errorCode
) {}
~~~

`objectKey` points to the file in object storage. `itemIndex` preserves ordering when needed by the business. `deadline` is the processing cutoff passed down by the parent; the child still enforces platform timeouts and downstream call timeouts.

Never pass credentials or access tokens in payloads. Children should derive permissions from their own execution role/service identity and authorize access to requested objects.

### 6.2. Idempotent child handler

The example below shows the handler structure. Repositories and services are application interfaces backed by a database/object storage or respective service.

~~~java
public final class ImageTaskHandler {
    private final TaskRepository tasks;
    private final ImageProcessor processor;
    private final ResultRepository results;

    public ImageTaskHandler(
            TaskRepository tasks,
            ImageProcessor processor,
            ResultRepository results) {
        this.tasks = tasks;
        this.processor = processor;
        this.results = results;
    }

    public WorkResult handle(WorkItem item) {
        String taskKey = item.workflowId()
                + ":" + item.itemId()
                + ":" + item.operationVersion();

        TaskClaim claim = tasks.claim(taskKey);

        if (claim.alreadySucceeded()) {
            return results.load(taskKey);
        }

        if (!claim.acquired()) {
            throw new TaskAlreadyRunningException(taskKey);
        }

        try {
            if (Instant.now().isAfter(item.deadline())) {
                throw new TaskDeadlineExceededException(taskKey);
            }

            String outputKey = processor.createThumbnail(item.objectKey());

            WorkResult result = new WorkResult(
                    item.workflowId(),
                    item.itemId(),
                    item.itemIndex(),
                    "SUCCEEDED",
                    outputKey,
                    null);

            results.save(taskKey, result);
            tasks.markSucceeded(taskKey);
            return result;
        } catch (RetryableTaskException ex) {
            tasks.releaseForRetry(taskKey, ex.getClass().getSimpleName());
            throw ex;
        } catch (RuntimeException ex) {
            tasks.markFailed(taskKey, ex.getClass().getSimpleName());
            throw ex;
        }
    }
}
~~~

This example assumes `TaskRepository.claim` performs an atomic operation so only one invocation owns a task key at a time. In production, include a lease expiration to recover if an instance terminates abruptly. Saving results and marking succeeded require an atomic transaction or consistent protocol; if one succeeds while the other fails, retries must be able to look up and recover the outcome.

If `processor.createThumbnail` writes to object storage, derive the output key deterministically from the task key or an idempotent rule. Generating a new random filename on every retry creates orphan files or causes the parent to see multiple outputs for the same item.

### 6.3. Parallelism within a single Java invocation

For a small, bounded number of fast independent tasks, Java can execute them in parallel within a single invocation using a bounded executor:

~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public final class LocalFanOut {
    public List<String> process(List<String> itemIds) {
        if (itemIds.isEmpty()) {
            return List.of();
        }

        int workers = Math.min(4, itemIds.size());

        ExecutorService executor = Executors.newFixedThreadPool(workers);
        List<CompletableFuture<String>> futures = new java.util.ArrayList<>();
        try {

            for (String id : itemIds) {
                futures.add(CompletableFuture.supplyAsync(
                        () -> processOne(id), executor));
            }

            CompletableFuture<Void> all =
                    CompletableFuture.allOf(
                            futures.toArray(CompletableFuture[]::new));

            all.orTimeout(20, TimeUnit.SECONDS).join();

            return futures.stream()
                    .map(CompletableFuture::join)
                    .toList();
        } catch (RuntimeException ex) {
            futures.forEach(future -> future.cancel(true));
            executor.shutdownNow();
            throw ex;
        } finally {
            executor.shutdown();
        }
    }

    private String processOne(String itemId) {
        return "processed:" + itemId;
    }
}
~~~

This represents local concurrency inside a single JVM invocation, written in syntax compatible with Java 17+. It comes with clear limitations:

- The four-worker cap applies only within this instance, not across concurrent invocations.
- If the function times out or the instance is reclaimed, running tasks are killed and unsaved progress is lost.
- `allOf` waits for all futures; on join error or timeout, the example cancels futures and calls `shutdownNow`, yet tasks stop only if the code cooperates with interrupts. Outbound calls already dispatched to external services may keep running.
- Executors must be shut down properly; worker counts and queues must fit CPU, memory, and downstream capacity.
- Never use this pattern as a substitute for durable workflows on long-running work or tasks needing independent retries.

When processing hundreds of items, when children can run for minutes, need independent retries, or must survive instance termination, let the workflow engine/queue spawn separate invocations. `CompletableFuture` fits short, local operations inside one request; it is not a durable workflow.

### 6.4. Pseudocode for a dynamic workflow

A workflow can be outlined conceptually as follows:

~~~text
Workflow ProcessCollection(collectionId):
    items = LoadItems(collectionId)
    batches = SplitIntoBatches(items, batchSize = 100)

    results = Map(
        batches,
        maxConcurrency = 20,
        retry = {
            maxAttempts: 3,
            backoff: exponential,
            jitter: true
        },
        task = ProcessBatch
    )

    summary = Aggregate(results)

    if summary.failedItems == 0:
        MarkCollectionCompleted(collectionId)
    else:
        SavePartialReport(collectionId, summary)
        MarkCollectionPartiallyCompleted(collectionId)
~~~

This is pseudocode, not syntax for any specific cloud provider. `Map` represents bounded-concurrency dynamic fan-out. `Aggregate` is the fan-in step. A workflow engine can persist each batch's status, retry history, and results to resume after failures.

## 7. Choosing a workflow engine, queue, or local parallelism

Platforms offer different implementations. For instance, AWS Step Functions provides Map state and Distributed Map; Azure Durable Functions provides the fan-out/fan-in pattern; Google Workflows can coordinate parallel steps. Always check your chosen platform's exact limits and semantics, as quotas, payload limits, child limits, and cancellation behaviors vary.

| Implementation | Best suited when | Key considerations |
|---|---|---|
| Parallel branch in workflow | Branch count is small and known upfront | Easy to inspect, though workflow definition is coupled to branches |
| Map / dynamic parallelism | Item list is determined at runtime | Must bound concurrency and input/state sizes |
| Child workflow | Each work unit has its own lifecycle and state | Improves isolation and tracking, adds orchestration cost |
| Queue + worker | High volume requiring buffering and rate smoothing | Parent needs mechanisms to track completion and timeouts |
| Executor in Java | Few short, local tasks inside a single invocation | Not durable across timeouts or instance termination |

A workflow engine excels when you need coordination state, per-child history, timeouts, retries, joins, and resumption after waits. Queues excel at absorbing bursts and metering worker capacity. Both can be combined: a workflow creates the job, a queue distributes children, a state table tracks outcomes, and the workflow receives the fan-in signal.

Do not spawn a child workflow for every tiny operation if orchestration overhead exceeds the actual work. Group small operations into batches while keeping clear per-item retry and status semantics.

## 8. Workflow state, payload size, and durability

Workflow engines typically persist inputs, outputs, state, and transition histories. Under large fan-out, result data can bloat state and history rapidly.

Useful guidelines:

- Keep workflow state compact: store IDs, statuses, counts, and result URIs.
- Put large payloads into object storage or databases; pass references to children instead of copies.
- Avoid repeating the same bulky data inside every child's input when a shared reference suffices.
- Retain detailed outputs only as long as needed; configure retention on execution histories and logs.
- When aggregating millions of results, use batched reduce steps or a data store rather than loading everything into one in-memory object.
- Choose checkpoints carefully so workflows can resume without reprocessing completed work.

Workflows can persist individual child outcomes, yet payload limits and state-transition quotas vary by platform. Before deciding batch sizes or child counts, verify actual orchestration quotas and test with expected data volumes.

## 9. Synchronous APIs and long-running fan-out jobs

An HTTP request must never hold a connection open while waiting for thousands of children to finish. For long-running jobs, the API can start the workflow and return:

~~~http
HTTP/1.1 202 Accepted
Location: /v1/jobs/job_abc123
Retry-After: 3
Content-Type: application/json
~~~

~~~json
{
  "jobId": "job_abc123",
  "status": "RUNNING",
  "statusUrl": "/v1/jobs/job_abc123"
}
~~~

Clients poll `statusUrl` or receive a callback/webhook upon completion. The status endpoint can return:

~~~json
{
  "jobId": "job_abc123",
  "status": "PARTIALLY_SUCCEEDED",
  "progress": {
    "total": 10000,
    "completed": 9970,
    "failed": 30
  },
  "resultUrl": "/v1/jobs/job_abc123/result"
}
~~~

These progress numbers are illustrative. If total item count is unknown initially, return the processed count and current status without fabricating fake percentages.

Job endpoints require the same authorization checks as the job-creation endpoint. Never allow anyone who guesses a `jobId` to read results. If `resultUrl` points to object storage, issue time-limited download permissions or proxy through an authorized API. Clients may also request cancellation; the endpoint should acknowledge the cancellation request and report `CANCELLED` only once the system confirms children have stopped or reached terminal states per policy.

## 10. Observing and operating fan-out/fan-in

With hundreds of children, individual function logs alone cannot explain the whole workflow. Every log and result should include correlation identifiers:

- `workflowId`: parent workflow identifier.
- `childId` or `taskId`: child task identifier.
- `itemId`: business unit being processed.
- `correlationId`: links requests and events across the flow.
- `attempt`: child attempt number.
- `parentId`: links child workflow to parent when supported by the platform.

Key metrics:

- Total children created, pending, running, and completed.
- Current concurrency and peak concurrency.
- Throughput, average processing duration, and tail percentiles (p95/p99).
- Success, failure, timeout, retry, and cancellation rates.
- Queue depth, age of oldest message, and DLQ count.
- End-to-end duration from fan-out start to fan-in completion.
- Stuck workflows and children exceeding deadlines.
- Invocation, workflow transition, message delivery, storage, and data-transfer costs.

Alert when queue depth grows continuously, message age climbs, retry rates spike, child timeouts cross thresholds, or parents fail to converge within expected windows. Aggregate child success counts alone will not reveal a small subset of items stuck indefinitely.

Use structured logs and exclude secrets, tokens, and unnecessary personal data. When children execute concurrently, never infer business ordering from log line arrival order; rely on timestamps and correlation IDs.

## 11. Security and resource fairness

Fan-out can amplify a single inbound request into thousands of invocations. Therefore, the workflow-initiation API must enforce authentication and authorization before spawning children.

Key principles:

- Verify permissions on the collection or batch before fanning out work.
- Children must still authorize access to their items or tenant; never blindly trust IDs passed by the parent if the parent is not an authoritative boundary.
- Grant each worker least-privilege read/write access only to required buckets, tables, or queues.
- Cap maximum items per job and concurrent jobs per tenant.
- Rate-limit the job-creation API to prevent a single client from flooding workflows.
- Isolate queues by tenant or priority tier when needed to prevent noisy neighbors.
- Verify message signatures or origins if queues/events can accept external input.
- Protect job status and result endpoints with the same access policies as the underlying data.

Per-tenant limits prevent one heavy customer from monopolizing workers. Still, overly restrictive caps can starve legitimate workloads. Tune limits based on SLAs, downstream quotas, and fairness policies.

## 12. Cost and performance

Fan-out reduces wall-clock completion time via parallelism, yet total cost does not automatically drop.

Total cost can include:

- Workflow state transitions or child executions.
- Function invocations and compute duration.
- Message publishes, receives, retries, and storage.
- Database reads/writes, object storage, and inter-service data transfer.
- Workflow history, logs, traces, and metrics.
- Re-processing from retries or replays.

Running 1,000 children concurrently shrinks wall-clock latency compared to sequential runs, while total compute still reflects the sum of CPU/IO time across all children. Excessive concurrency can trigger downstream throttling, increase retries, and end up raising both latency and cost.

To optimize:

1. Measure duration and resource consumption of a single child before choosing batch size.
2. Run load tests at expected concurrent workflow volumes.
3. Set concurrency according to the lowest bottleneck in the dependency chain.
4. Minimize payloads and store only essential outputs.
5. Choose batch sizes balancing orchestration overhead against retry blast radius.
6. Track cost per completed item and cost per successful workflow.
7. Tune using empirical metrics rather than blindly adding workers when things look slow.

## 13. Process for designing a fan-out/fan-in workflow

Follow this sequence:

1. **Define the unit of work.** Does each child process one item or one batch? What business side effects does it perform?
2. **Measure cardinality.** How many children exist per workflow in typical and peak cases? Are input limits enforced?
3. **Choose the fan-out mechanism.** Static branches, Map/dynamic parallelism, child workflows, or queues.
4. **Set concurrency and rate limits.** Account for per-workflow, system-wide, per-tenant, and downstream caps.
5. **Define the join policy.** Wait for all, first valid result, quorum, or partial success?
6. **Define states and outputs.** Give each child an ID, status, attempt count, error code, and result reference.
7. **Design retries and idempotency.** Retry transient child failures; use stable keys for side effects.
8. **Design timeouts and cancellation.** Enforce child and parent deadlines; define behavior when a child already called external services.
9. **Design compensation.** Identify compensating actions, idempotency, and manual escalation points.
10. **Design fan-in and aggregation.** Keep large payloads out of state; preserve order via item index if needed.
11. **Design observability and security.** Propagate correlation IDs, set metrics/alerts, and enforce access and job limits.
12. **Load and fault test.** Simulate duplicates, timeouts, slow children, downstream throttling, DLQs, and mid-flight cancellations.

## 14. Common design pitfalls

- **Creating an unbounded child per record:** quickly exhausts quotas and overwhelms downstream systems. Enforce cardinality limits, batching, and concurrency caps.
- **Confusing concurrency with throughput:** running more children simultaneously does not guarantee completions per second scale proportionally.
- **Waiting for all without timeouts:** a single stuck child can hold the parent workflow forever.
- **Retrying the entire fan-out when only a few children fail:** repeats already-succeeded side effects and inflates cost. Retry only failed children.
- **Missing idempotency:** redelivered messages can create duplicate payments, files, or database records.
- **Collecting all results into workflow state:** oversized payloads exceed engine limits and bloat execution history.
- **Assuming children finish in input order:** completion order depends on scheduling and latency.
- **Cancelling the parent and assuming all children stopped:** external calls may still be running. Implement cancellation protocols and confirmation states.
- **Missing fan-in state:** queues may drain all messages while the parent still has no idea whether the job completed.
- **Missing per-tenant caps:** one huge job can starve all other tenants.
- **Ignoring DLQs and overdue jobs:** failed children sit forgotten and parents never converge.
- **Using local executors for long workflows:** instance reclamation loses in-flight work with no durable state.

## 15. Self-check

**Question 1.** What are fan-out and fan-in?

**Suggested answer:** Fan-out splits a job into multiple independent or parallel child tasks. Fan-in waits for, collects, and aggregates results so the parent workflow can decide the next step.

**Question 2.** How does cardinality differ from concurrency?

**Suggested answer:** Cardinality is the total number of children created in a workflow; concurrency is how many children run at the same time. A workflow can have 10,000 children while capping simultaneous execution at 50 active children.

**Question 3.** When should you use join all, join any, or quorum?

**Suggested answer:** Use join all when every child is mandatory. Use join any when one valid result suffices. Use quorum when business rules accept a minimum count or proportion of results.

**Question 4.** Why shouldn't you retry the entire fan-out when only a few children fail?

**Suggested answer:** Already-succeeded children would re-execute, wasting cost and risking duplicate side effects. Retry only failed children or batches using stable idempotency keys.

**Question 5.** Why aren't per-workflow concurrency limits alone enough to protect a database?

**Suggested answer:** Multiple workflows can run concurrently; total concurrency equals the sum of active children across all workflows. System-wide limits, per-tenant caps, and alignment with downstream capacity are required.

**Scenario exercise:** A job needs to generate thumbnails for 12,000 images. Each child takes 3 seconds on average, the database supports at most 120 concurrent writes, and each tenant is capped at 30 parallel children. Propose batching, concurrency, retry policy, join policy, and job status design. Specify how to handle 20 images failing after three attempts and a client requesting cancellation when 70% of images are already done.

**Suggested approach:** Split images into moderate batches or spawn per-image children with bounded concurrency. A limit of 30 children per tenant stays under the 120 concurrent write limit for a single tenant; when multiple tenants run simultaneously, a global cap and database rate limit are still required. Retry only failed images with backoff and idempotency keys built from job ID, image ID, and processing version. Fan-in can return `PARTIALLY_SUCCEEDED` alongside the list of 20 failed images if business rules allow partial completion. On cancellation, stop dispatching new children, signal active children to check cancellation, and record statuses as completed, cancelled, or uncancellable. Do not delete already-created outputs; if business rules require rollback, define explicit compensations.

## Conclusion

Fan-out splits a workflow into multiple child tasks; fan-in gathers results and determines when the business process can proceed. Designs must specify cardinality, concurrency, throughput, join policies, timeouts, retries, and idempotency. Queues, batching, and per-workflow/system-wide limits control load; durable state, correlation IDs, and batched aggregation enable operating large processes reliably. In serverless architectures, use a workflow engine or queues for distributed, long-running work, reserving local Java parallelism for a small number of brief tasks within a single invocation.
