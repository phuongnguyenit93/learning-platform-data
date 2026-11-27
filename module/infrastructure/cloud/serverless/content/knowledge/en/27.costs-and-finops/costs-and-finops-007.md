# Optimizing Batching, Execution Duration, and Provisioned Capacity

Serverless costs do not depend solely on the number of function invocations. For workloads processing messages or streams, how records are grouped into batches, how long batching waits, execution duration, memory/CPU, and reserved capacity can dramatically change both cost and latency. A large batch configuration can reduce invocations while increasing wait time, payload size, and the amount of work retried on failure. A large capacity reservation can stabilize latency while incurring costs even when traffic is low.

This lesson uses AWS Lambda, Amazon SQS, and Java as primary examples, while comparing against Azure Functions Always Ready and Google Cloud Run minimum instances. The goal is choosing batch size, batching window, memory, concurrency, and provisioned capacity based on measured workloads, then evaluating cost per successful business unit.

## 1. Viewing Cost Across the Entire Processing Flow

A serverless message-processing pipeline typically consists of:

~~~mermaid
flowchart LR
    P["Producer"] --> Q["Queue / stream"]
    Q --> E["Event source mapping / poller"]
    E --> B["Batch payload"]
    B --> F["Java function"]
    F --> D[("Database / API / storage")]
    F --> R["Success / partial failure"]
    R --> Q
    F --> DLQ["DLQ / quarantine"]
~~~

Each component can generate costs or affect completion time:

- Queues or streams carry request, storage, throughput, or partition charges.
- Event source mappings may use automatic polling or provisioned pollers.
- Each invocation incurs request charges and compute duration based on allocated memory.
- Provisioned Concurrency incurs capacity charges for the configured time window.
- Logs, metrics, tracing, data transfer, NAT, database connections, and partner APIs also incur costs.
- Retries and duplicates increase the number of times the same message is processed.
- DLQs and replays add storage, request, and compute charges.

Do not optimize one cost line in isolation if it increases costs elsewhere. For example, raising batch size lowers invocation counts yet can lengthen duration, increase queue age, and force more work to re-run when a batch fails.

## 2. Capacity Types Often Confused

In AWS Lambda, three configurations must be distinguished:

| Configuration | Which Resource Is Allocated? | What Problem Does It Solve? | Separate Capacity Fee? |
|---|---|---|---|
| Batch size / batching window | Record count and record collection window | Reduces invocation overhead, balances latency and throughput | No separate capacity fee |
| Reserved Concurrency | Caps and reserves concurrency for a function | Protects function/dependencies, prevents other functions from exhausting account concurrency | No separate configuration fee |
| Provisioned Concurrency | Pre-initialized execution environments for a version/alias | Reduces cold starts for invocations using that capacity | Yes |
| Provisioned Pollers | Dedicated polling resources for an event source mapping | Speeds up queue/stream reading and controls inbound throughput | Yes, in EPU-hours |

Provisioned Concurrency prepares function execution environments. Provisioned Pollers prepare resources to read events from SQS or Kafka. They solve two different bottlenecks.

Reserved Concurrency is not a pool of always-warm instances. It caps total concurrency for the function and reserves that portion of the account quota. If the function needs a new environment, cold starts can still occur.

## 3. Lambda Cost Model

For Lambda Event Functions, baseline costs typically include requests and compute duration. Compute is billed in GB-seconds:

\[
GB\text{-}seconds = Memory_{GB} \times BilledDuration_{seconds}
\]

For workloads without reserved capacity, you can estimate:

\[
C_{function} =
N_{invocations} \times Price_{request}
+
GB\text{-}seconds \times Price_{compute}
\]

Total workload cost must add queues, event pollers, logs, data transfer, databases, caches, NAT, and other dependencies.

With batch processing, invocation count does not equal message count. If there are one million messages and the actual average batch holds 100 messages, theoretical invocations are near 10,000 rather than one million. However, actual batches can be smaller than configured due to batching window expiration, payload limits, or low traffic.

A useful FinOps formula is:

\[
CostPerSuccess =
\frac{TotalWorkloadCost}{SuccessfulBusinessOperations}
\]

The denominator must be valid completed business operations, not just successful invocations. If a message is processed three times or lands in a DLQ, its cost was still incurred.

## 4. Batch Size and Batching Window

With event source mappings, Lambda groups records into batches before invoking the function. Two key settings:

- **Batch size:** maximum number of records in a single batch.
- **Batching window:** maximum time to wait to gather additional records.

Lambda invokes the function when any of these conditions occur: the batching window expires, the batch reaches batch size, or the payload hits the 6 MB limit. The payload limit includes metadata added by the event source and Lambda; thus actual records per batch may be fewer than the configured batch size.

For Amazon SQS:

| Property | Standard Queue | FIFO Queue |
|---|---:|---:|
| Default batch size | 10 | 10 |
| Maximum batch size | 10,000 | 10 |
| Batching window | 0–300 seconds | Not supported |
| Invocation payload limit | 6 MB | 6 MB |
| Partial batch response | Yes | Yes, must preserve ordering |

When batch size exceeds 10, a batching window of at least 1 second must be set. With SQS standard queues, when traffic is low, Lambda may wait up to roughly 20 seconds before invoking even if the batching window is configured lower. Factor this into the latency budget.

Other event sources have distinct batch size and window limits. Do not copy SQS values to Kinesis, DynamoDB Streams, Kafka, Amazon MQ, or DocumentDB without checking the respective source's documentation.

## 5. Choosing Batch Size for Latency and Throughput

Larger batches can cut invocation counts and raise records processed per invocation. However, larger batches are not always faster.

| Batch Size | Benefits | Risks |
|---|---|---|
| Small | Low latency, isolated errors, fewer records reprocessed | High invocations and polling overhead |
| Medium | Balances throughput and latency | Requires benchmarking by payload/duration |
| Large | Lowers invocation counts, amortizes fixed overhead | Long batch duration, high memory, large payloads, and costly retries |

For example, if each record takes 5 ms to process sequentially, a 10-record batch takes roughly 50 ms plus overhead. A 100-record batch takes roughly 500 ms plus overhead. Invocations drop 10x, yet single-invocation duration increases proportionally.

If processed in parallel, duration can drop while CPU, threads, database connections, and API concurrency rise. Batch size must be chosen alongside parallelism and dependency limits.

A practical experiment is benchmarking batch sizes of 10, 25, 50, 100, and 250, then measuring:

- Throughput in records/second.
- p50/p95/p99 from message send to processing completion.
- Invocation duration.
- Peak memory.
- Retries and duplicates.
- Queue age.
- Cost per thousand successful records.

Do not pick batch size solely for the lowest invocation count. Pick the configuration meeting SLOs at the lowest total cost.

## 6. Setting Batching Window by Business Latency

The batching window adds wait time to accumulate records. Larger windows help fill batches during sparse traffic, but force new messages to wait longer before processing starts.

Examples:

- API events needing responses within a couple seconds: window of 0 or very small.
- Telemetry processing tolerating 5–10 seconds delay: larger window can improve batch fullness.
- Minute-level aggregation jobs: longer batching windows may fit well.
- FIFO queues requiring ordering and not supporting batching windows on SQS event source mappings: optimize batch size within FIFO limits.

Do not use batching windows to mask an under-provisioned consumer. If queue age climbs continuously, boost processing capacity, shorten duration, or throttle producer rates.

## 7. Payload Size and the 6 MB Limit

Payload limits can terminate a batch before reaching the configured record count. Records with large bodies, heavy message attributes, or verbose metadata shrink the number of records per batch.

Measure the payload distribution rather than relying only on the average. If most messages are small while some are huge, batch sizes will fluctuate widely.

Measures:

- Send only metadata and object references in messages; store large payloads in object storage.
- Enforce message size limits in the contract.
- Use compression if both producer and consumer handle it safely.
- Avoid repeating redundant metadata on every record.
- Check actual payload size after Lambda appends metadata.
- Separate large message types onto dedicated queues or consumers if their processing profile differs.

Do not compress data solely to shrink payloads if CPU cost and extra duration outweigh the savings. Measure both transfer size and compute spent compressing/decompressing.

## 8. Partial Batch Responses Lower Retry Costs

By default, if a batch-processing function errors, the entire batch may be re-sent. Records that already succeeded can re-run, increasing compute, dependency requests, and risk of duplicate side effects.

With SQS, configure the event source mapping to enable **ReportBatchItemFailures**. The function returns the list of failed message IDs; Lambda makes only those messages visible again for retry. AWS Lambda Powertools for Java provides a Batch Processing utility implementing partial batch responses for SQS, Kinesis, and DynamoDB Streams.

Partial batch responses do not replace idempotency. Event source mappings still provide at-least-once delivery, and duplicates can still occur. With FIFO, stop processing after the first error in a message group or apply equivalent ordering-preservation rules; do not continue processing subsequent records in ways that break business order.

## 9. Java Example Handling SQS Batches with Partial Failures

The example below processes each record and returns only messages needing retry. Permanent errors are written to durable quarantine before treating the record as handled; transient errors are returned so SQS retries them.

~~~java
import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import com.amazonaws.services.lambda.runtime.events.SQSEvent;
import com.amazonaws.services.lambda.runtime.events.SQSBatchResponse;

import java.util.ArrayList;
import java.util.List;

public final class OrderBatchHandler
        implements RequestHandler<SQSEvent, SQSBatchResponse> {

    private final OrderService orderService = OrderService.create();
    private final QuarantineStore quarantine = QuarantineStore.create();

    @Override
    public SQSBatchResponse handleRequest(
            SQSEvent event,
            Context context) {

        List<SQSBatchResponse.BatchItemFailure> failures =
                new ArrayList<>();

        for (SQSEvent.SQSMessage message : event.getRecords()) {
            try {
                orderService.processIdempotently(message);

            } catch (PermanentRecordException error) {
                // Only treat as handled after quarantine writes durably.
                quarantine.store(message, error.getCode());

            } catch (TransientDependencyException error) {
                failures.add(
                        new SQSBatchResponse.BatchItemFailure(
                                message.getMessageId()
                        )
                );

            } catch (RuntimeException error) {
                // Unclassified error: bounded retry per redrive policy.
                failures.add(
                        new SQSBatchResponse.BatchItemFailure(
                                message.getMessageId()
                        )
                );
            }
        }

        return new SQSBatchResponse(failures);
    }
}
~~~

This example uses AWS Lambda Java Events alongside illustrative OrderService/QuarantineStore classes. In production projects, add constructor injection, timeouts, logging, metrics, and exception handling for the quarantine store. If writing to quarantine fails, the record must be reported as failed so it is not lost.

The event source mapping must enable ReportBatchItemFailures. If the function throws an unhandled exception out of the handler, the entire batch may be marked failed; classify errors per record and return a partial response only after every record is handled or safely quarantined.

## 10. Configuring SQS Event Source Mappings

Example updating batch size and batching window:

~~~bash
aws lambda update-event-source-mapping \
  --uuid EVENT_SOURCE_MAPPING_UUID \
  --batch-size 100 \
  --maximum-batching-window-in-seconds 2
~~~

Enabling partial batch responses:

~~~bash
aws lambda update-event-source-mapping \
  --uuid EVENT_SOURCE_MAPPING_UUID \
  --function-response-types ReportBatchItemFailures
~~~

Checking current configuration:

~~~bash
aws lambda get-event-source-mapping \
  --uuid EVENT_SOURCE_MAPPING_UUID
~~~

Commands must run with appropriate event source mapping management permissions. Replace the UUID with the real mapping and verify state after updating.

## 11. Visibility Timeout and Batch Processing Duration

SQS keeps messages invisible during the visibility timeout while Lambda processes a batch. If the function does not finish before timeout expires, messages can reappear and get processed concurrently or repeatedly.

AWS recommends a queue visibility timeout at least six times the function timeout. When a batching window is used, add the batching window to the calculation:

\[
VisibilityTimeout \geq 6 \times FunctionTimeout + BatchingWindow
\]

This is AWS's configuration guideline for SQS event source mappings; still test actual duration, retries, and throttling. Function timeout must be less than or equal to the queue visibility timeout.

For example, a 30-second function timeout and 5-second batching window yield a minimum recommended visibility timeout of 185 seconds. You can choose higher values if the workload experiences tail latency or slow downstream dependencies.

Setting visibility timeout too short can cause duplicate processing. Setting it too long forces failed messages to wait excessively before retrying. Balance it against retry policies and recovery targets.

## 12. Retries, DLQs, and the Cost of Failed Messages

A failing message can incur costs multiple times: retry invocations, dependency calls, logs, traces, and wait time. If a permanent error is retried as transient, costs keep climbing without delivering value.

Classify errors:

| Error Type | Handling Strategy |
|---|---|
| Transient errors: timeout, 429, 503 | Bounded retry with backoff and jitter |
| Permanent errors: invalid schema, malformed data | Quarantine or DLQ |
| Authorization errors | Alert and fix permissions; avoid unbounded retries |
| Broad dependency outage | Reduce concurrency/apply backpressure, open circuit breaker |
| Unclassified errors | Bounded retry, log with correlation ID, and route to DLQ |

Configure an SQS redrive policy with an appropriate maxReceiveCount. AWS recommends a value of at least 5 as a starting point for many scenarios, though this should be tuned to error types and expected recovery times.

A DLQ is not a place to forget messages. Maintain dashboards, alerts, triage workflows, data fixes, and small-batch replays. Replays must be idempotent so they do not trigger duplicate side effects.

## 13. Idempotency Enables Safe Large Batches

Event source mappings process at least once, so duplicates can arise when functions time out, acknowledgements are lost, or messages retry. Large batches increase the number of records that could be reprocessed if partial batch responses are absent.

Each business operation needs a stable idempotency key, such as event ID or business operation ID. Use conditional writes or transactions to guarantee one key executes side effects only once.

Do not use static maps or HashSets inside the JVM as an idempotency store. Execution environments can be recycled and multiple instances run in parallel. State must reside in a durable database or store supporting atomic operations.

When replaying a DLQ, keep the original idempotency key. Generating a new key per replay can make the system re-execute the same business operation as brand-new work.

## 14. Optimizing Java Function Execution Duration

Duration directly drives compute cost and throughput. In Java, common sources of overhead include:

- Initializing frameworks or clients on every invocation.
- Repeated JSON parsing/serialization.
- Opening a new connection for every record.
- Querying the database per record instead of bulk operations.
- Calling APIs sequentially when the dependency supports batching.
- Logging huge payloads or emitting overly verbose traces.
- Unnecessary classpath scanning or reflection.
- Sizing thread pools larger than CPU count or downstream capacity.

Initialize thread-safe clients outside the handler to reuse across invocations. Never store user data or mutable business state in static fields. Optimize serializers, queries, and API calls before scaling up memory.

When dependencies support bulk writes, combine compatible operations within the same batch. However, bulk operations must have clear partial-error semantics; otherwise retrying the whole batch can cause duplicates.

## 15. How Do Memory and CPU Affect Duration?

In AWS Lambda, memory can be configured from 128 MB to 10,240 MB. CPU scales proportionally with memory; at roughly 1,769 MB, a function receives CPU equivalent to one vCPU as described by AWS.

Increasing memory can shorten duration for CPU-bound workloads and some network-bound workloads. Even though the per-second price rises, total GB-seconds can stay flat or drop if the function finishes sufficiently faster.

Illustrative example:

| Memory | Duration | Relative Compute |
|---:|---:|---:|
| 512 MB | 1.2 seconds | 0.6 GB-s |
| 1,024 MB | 0.7 seconds | 0.7 GB-s |
| 2,048 MB | 0.3 seconds | 0.6 GB-s |

The table above uses hypothetical figures to illustrate trade-offs, not real benchmarks. The 2 GB configuration finishes fastest with compute equivalent to 512 MB. If SLOs matter, the faster option may be worthwhile; if optimizing strictly for cost, also weigh requests, concurrency, and downstream limits.

Do not raise memory by guesswork. Benchmark multiple memory tiers while holding code, payloads, architecture, and traffic patterns constant, then compare duration, GB-seconds, error rates, and cost per success.

## 16. Choosing Architecture and Runtime by Benchmark

AWS Lambda supports x86_64 and arm64. Graviton/Arm can improve price-performance for certain workloads, provided native dependencies, JNI, libraries, and container images are compatible.

Evaluation process:

1. Build artifacts for both architectures if dependencies allow.
2. Use identical inputs, batch sizes, memory, and concurrency.
3. Collect enough warm and cold samples.
4. Measure duration, memory, error rates, and CPU-bound time.
5. Compare pricing for the target Region and architecture.
6. Verify native libraries, JDBC drivers, and observability extensions.
7. Pick the configuration achieving target cost per success and latency.

Do not pick Arm solely for a lower unit rate. If dependencies are incompatible or duration grows substantially, total cost can end up higher.

## 17. Parallel Processing in Java

Batches can be processed sequentially or in parallel.

**Sequential** processing easily preserves order, simplifies transaction control, and applies less pressure downstream. It fits FIFO queues, order-dependent logic, or databases with tight connection limits.

**Parallel** processing can boost throughput for independent records, especially when each record waits on I/O. However, thread counts and concurrency must be bounded by CPU, connection pools, and dependency rate limits.

For CPU-bound tasks, worker count should stay close to available CPUs. For I/O-bound tasks, you can use more workers while capping simultaneous requests to databases or partner APIs.

Java 21 virtual threads reduce thread creation overhead for blocking I/O, but do not speed up CPU execution or expand database limits. Use semaphores or bulkheads to bound dependency concurrency.

AWS Lambda Powertools for Java Batch Processing supports parallel processing for SQS standard, Kinesis, and DynamoDB Streams; never use parallel mode for SQS FIFO. Benchmark carefully, as parallelism is not always better.

## 18. Example of Bounded Parallel Processing

An I/O-bound pattern can use an executor with a configured worker count:

~~~java
int workers = Integer.parseInt(
        System.getenv().getOrDefault("BATCH_WORKERS", "8")
);

ExecutorService executor =
        Executors.newFixedThreadPool(workers);

Semaphore downstreamLimit = new Semaphore(12);

void processRecord(OrderEvent event) throws Exception {
    downstreamLimit.acquire();
    try {
        partnerClient.send(event);
    } finally {
        downstreamLimit.release();
    }
}
~~~

This example demonstrates bounding concurrent operations to a dependency. In Lambda, executors should be reused in alignment with the execution environment lifecycle and managed carefully. Do not create a new thread pool per record or per invocation unnecessarily.

Worker count should align with memory/CPU and connection limits. If 10 Lambda execution environments each spin up 20 workers, the dependency can face up to 200 concurrent requests. Calculate concurrency at the system level, not just inside one JVM.

## 19. Throughput and Concurrency

For batches, approximate throughput is:

\[
RecordsPerSecond \approx
ConcurrentInvocations \times
\frac{EffectiveBatchSize}{AverageBatchDuration}
\]

Example: 20 concurrent invocations, 100 records per batch, and 0.5-second average duration:

\[
20 \times \frac{100}{0.5} = 4.000 \text{ records/second}
\]

This is an ideal estimate. Payload limits, poller capacity, downstream bottlenecks, retries, memory, and batching delays can yield lower throughput.

Raising concurrency only helps if dependencies can absorb the load. If a database allows 100 connections and each Lambda environment opens 10 connections, just 10 environments can exhaust the connection pool. Size both function concurrency and connection pools together.

## 20. Reserved Concurrency to Protect Dependencies

Reserved Concurrency sets a maximum limit and reserves a slice of concurrency for a function. It does not keep environments warm and carries no separate configuration fee, though the reserved quota becomes unavailable to other functions in the account.

Use Reserved Concurrency when:

- Databases have connection limits.
- Partner APIs enforce rate limits.
- A function must not scale too rapidly.
- Critical workloads require protected capacity.
- You want to limit blast radius during message bursts.

Example setting maximum concurrency:

~~~bash
aws lambda put-function-concurrency \
  --function-name orders-consumer \
  --reserved-concurrent-executions 40
~~~

The value 40 is illustrative only. If batches handle 100 records across 40 concurrent invocations, the function can process roughly up to 4,000 records per wave, though duration and downstream capacity must be verified.

If Reserved Concurrency is too low, SQS mappings may throttle and message age will climb. If left uncapped, bursts can overwhelm downstream systems. Load test to locate the sweet spot.

## 21. Provisioned Concurrency for Function Execution

Provisioned Concurrency pre-allocates initialized execution environments for a published version or alias. It helps when invocations need very low latency and cold starts threaten SLOs.

PC does not enlarge batch sizes or speed up queue polling. For SQS consumers, it only ensures execution environments are ready when the event source mapping invokes the function. If the bottleneck is the poller or batch filling, PC solves the wrong problem.

PC cost depends on memory, concurrency, and enabled duration. Beyond capacity charges, invocations still incur request and duration charges. Traffic exceeding PC runs on standard concurrency and can hit cold starts. PC charges run from enablement until disablement, rounded up to 5-minute increments; initialization code executed during allocation/recycling can also be billed in duration.

Capacity usage example:

\[
PC\ GB\text{-}seconds =
ProvisionedConcurrency \times Memory_{GB} \times EnabledSeconds
\]

Configuring 20 PC at 2 GB memory for 8 hours:

\[
20 \times 2 \times 28.800 = 1.152.000\ GB\text{-}seconds
\]

This is billable capacity usage before adding request and execution duration charges. Compare against running PC 24/7 or all month to see idle costs.

## 22. Provisioned Pollers for SQS and Kafka

Provisioned Mode on Lambda event source mappings allocates dedicated polling resources to read messages. It suits queues/streams with strict throughput and latency requirements.

For SQS, one event poller can handle roughly up to:

- 1 MB/second throughput.
- 10 concurrent invocations.
- 10 SQS polling API calls per second.

Provisioned Mode lets you set minimum and maximum pollers, then auto-scales within that range. AWS describes this mode as scaling faster than standard mode and supporting higher concurrency for SQS. Minimum pollers for SQS is 2; maximum limits should be verified against current Regional APIs and quotas.

Provisioned Mode is currently supported for SQS, Amazon MSK, and self-managed Kafka. Per-poller capabilities and configurations for Kafka differ from SQS; do not apply SQS formulas to Kafka.

Provisioned Pollers bill separately in Event Poller Unit-hours (EPU-hours). For SQS, one EPU supports one event poller, and every SQS mapping requires at least two pollers. Costs depend on EPU count and usage duration; duration is billed per second with a one-minute minimum.

Provisioned Mode cannot be combined with the maximum concurrency setting on SQS event source mappings. When provisioned mode is enabled, use maximum pollers to govern inbound polling/concurrency. Function-level Reserved Concurrency remains a separate limit to account for.

## 23. Sizing Poller Capacity by Workload

To estimate pollers, measure:

- Peak messages/records per second.
- Average message size.
- Actual batch size.
- Average batch duration.
- Latency target.
- Concurrent invocations and concurrency quotas.

A consumer throughput estimate:

\[
EPS \approx
\frac{PollerCount \times EffectiveBatchSize \times ConcurrentBatchesPerPoller}
{AverageBatchDuration}
\]

Then verify against per-poller throughput and polling API limits. Formulas are only a starting point; benchmark because payloads, batching windows, and downstream limits can cap throughput before pollers do.

For instance, if each poller sustains 100 events/second in practice and peak demand is 1,000 events/second, you need roughly 10 pollers before adding buffer. Measure with real workloads; never treat these numbers as service defaults.

## 24. Configuring Provisioned Pollers via CLI

Example updating an SQS event source mapping:

~~~bash
aws lambda update-event-source-mapping \
  --uuid EVENT_SOURCE_MAPPING_UUID \
  --provisioned-poller-config '{"MinimumPollers": 5, "MaximumPollers": 100}'
~~~

Disabling provisioned mode and returning to default polling:

~~~bash
aws lambda update-event-source-mapping \
  --uuid EVENT_SOURCE_MAPPING_UUID \
  --provisioned-poller-config '{}'
~~~

Inspect the ProvisionedPollers metric and event source mapping status after making changes. Also monitor function concurrency, queue age, and throughput to confirm the capacity is actually utilized.

## 25. Pinpointing Bottlenecks: Batch, Poller, or Function?

| Symptom | Likely Bottleneck | Optimization Direction |
|---|---|---|
| Small batches, high invocations | Low traffic or batching window too short | Adjust batching window if latency allows |
| Full batches yet rising queue age | Long function duration or low concurrency | Optimize Java, memory, batch processing, or concurrency |
| Low function concurrency despite large queue | Event source mapping polling/scaling | Check poller mode, source limits, and mapping settings |
| Spillover/throttling or throttled invocations | Function/account concurrency | Tune reserved concurrency and poller capacity |
| Fast function yet messages keep waiting | Event source poller or batch window | Measure poller throughput and batching delay |
| Function duration grows with batch size | Oversized batches or sequential processing | Shrink batch size or add bounded parallelism |
| DB connection saturation | Excessive concurrency/workers | Cap connections, workers, and function concurrency |
| Cost rising due to retries | Weak partial failure/idempotency handling | Enable partial batch responses and fix record errors |
| High cost when messages are absent | Oversized provisioned pollers or PC baseline | Lower minimums or use schedules if appropriate |

Before adding capacity, pinpoint which component limits throughput. Adding pollers will not help if the function is throttled; adding PC will not help if pollers cannot read messages fast enough; raising batch size will not help if the database is the bottleneck.

## 26. Comparing Provisioned Concurrency and Provisioned Pollers

| Criterion | Provisioned Concurrency | Provisioned Pollers |
|---|---|---|
| Attached to | Lambda version/alias | Event source mapping |
| Pre-warmed resource | Pre-initialized execution environments | Polling resources reading queues/streams |
| Primary impact | Cuts function cold starts | Speeds up and scales polling capacity |
| Capacity unit | Concurrency × memory × duration | EPU × duration |
| Best-fit workloads | HTTP/APIs or functions needing low startup latency | SQS/Kafka with strict throughput/latency targets |
| Solves batch filling? | No | Can improve polling, though batch/window still need tuning |
| Costs money when idle? | Yes | Yes, for minimum allocated pollers/EPUs |

Both mechanisms address different stages of a pipeline, so evaluate total cost and concurrency together. Never turn both on merely hoping for speed; measure whether latency comes from polling or initialization.

## 27. Provisioned Concurrency Costs

PC bills based on configured concurrency, memory, and enabled duration. When the function is invoked, requests and duration still bill. Invocations exceeding PC bill at on-demand rates. Lambda may recycle execution environments and re-run initialization code, so initialization also counts toward duration costs.

Key points to note:

- PC bills from enablement to disablement, rounded up to 5-minute increments.
- Pricing varies by Region, architecture, and memory.
- Lambda Free Tier does not apply to functions with Provisioned Concurrency enabled per current pricing rules.
- Invocations and duration still bill when functions run.
- PC cannot be applied to $LATEST; a published version/alias is required.
- Unused allocated capacity still incurs charges.

If low latency is only needed during peak hours, consider scheduled scaling to raise PC ahead of peaks and lower it afterward. For unexpected spikes, target tracking can scale capacity up, though scale-up takes time; it cannot replace baseline capacity if SLOs demand instant readiness.

## 28. Provisioned Poller Costs

Provisioned Mode for event source mappings bills in EPU-hours. AWS bills based on minimum provisioned pollers and additional pollers added during autoscaling. EPU pricing varies by event source and Region.

General formula:

\[
EPUHours = \sum (AllocatedEPUs \times DurationHours)
\]

\[
PollerCost = EPUHours \times RegionalEPUPrice
\]

For example, if an SQS mapping requires 2 pollers for 10 hours and one EPU corresponds to one poller, usage equals 20 EPU-hours. Check exact fees for your Region and timeframe on the AWS Lambda Pricing page.

Do not use US East EPU pricing to budget for another Region. Use the AWS Pricing Calculator, Cost Explorer, and your account's billing data.

## 29. How Much Can Batching Cut Costs?

Hypothetical example for illustration:

- One million messages to process.
- Processing one message per invocation takes 80 ms at 1 GB memory.
- Batching 100 messages per invocation takes 400 ms at 1 GB memory.
- Excluding retries, request fees, queue fees, and downstream costs.

Single-message processing:

\[
1.000.000 \times 0,08s \times 1GB = 80.000\ GB\text{-}s
\]

Batch-100 processing:

\[
10.000 \times 0,4s \times 1GB = 4.000\ GB\text{-}s
\]

In this example, compute drops 20x and invocations drop 100x. This is not guaranteed savings; if batching 100 messages stretches duration to 8 seconds, raises memory, or retries the whole batch when one record fails, gains can shrink dramatically.

Benchmark with real payloads and failure modes. Factor in partial batch responses, idempotency, and DLQs before rolling large batches into production.

## 30. Cross-Cloud: Always Ready and Minimum Instances

Cloud providers offer similar mechanisms to keep capacity ready, though billing and scaling rules differ:

| Platform | Mechanism | Costs to Monitor |
|---|---|---|
| AWS Lambda | Provisioned Concurrency | Memory × concurrency × enabled time, plus requests and duration |
| AWS Lambda SQS/Kafka | Provisioned Pollers / Provisioned Mode | EPU-hours, plus function compute and queue/stream charges |
| Azure Functions Flex Consumption | Always Ready instances | Baseline memory while idle, execution time, and executions |
| Google Cloud Run | Minimum instances | Idle CPU/memory billing by config plus request/active time |

Azure Flex Consumption allows configuring Always Ready per function or trigger group; idle baselines carry separate fees. Google Cloud Run may bill minimum instances during idle periods depending on the billing mode. These mechanisms are not strictly identical to AWS PC; read the pricing model for the exact plan and Region.

## 31. FinOps: Measuring Cost per Successful Message

A good dashboard does not show only total Lambda spend. Combine cost, throughput, and business quality.

Metrics to track:

| Category | Metrics |
|---|---|
| Batch | Average batch size, batch fullness, batching delay, payload size |
| Compute | Invocations, duration, memory used, GB-seconds |
| Capacity | ConcurrentExecutions, ReservedConcurrentExecutions, ProvisionedConcurrentExecutions |
| Poller | ProvisionedPollers, poller utilization, EPU-hours |
| Queue | ApproximateAgeOfOldestMessage, visible/in-flight count, DLQ count |
| Reliability | Retry count, partial batch failures, duplicate count |
| Performance | Records/second, p95/p99 processing latency |
| Business | Successful orders/payments/jobs |
| Cost | Cost per 1,000 successful messages, cost per transaction |

Key formula:

\[
CostPer1000Success =
\frac{TotalCost}{SuccessfulMessages} \times 1000
\]

If throughput rises while success rate drops or DLQs grow, cost per success can worsen. Never optimize by ignoring errors or counting DLQ messages as successfully processed.

## 32. Tagging and Cost Allocation

Apply consistent cost allocation tags to functions, queues, event source mappings, and related resources. A tag set might include:

- Application
- Service
- Environment
- Team
- CostCenter
- Owner
- BusinessCapability

Use AWS Cost Explorer or the Cost and Usage Report to allocate across accounts, Regions, services, functions, and tags. When multiple workloads share queues, databases, or log groups, allocate by volume or business metrics.

Do not charge the entire queue bill to a consumer function if multiple applications share that queue. Document the allocation methodology so month-over-month comparisons remain meaningful.

## 33. FinOps Guardrails

Guardrails that can be automated:

- Alert when batch size or batching window changes past thresholds.
- Alert when PC or minimum pollers remain active outside expected hours.
- Cap maximum concurrency aligned with downstream capacity.
- Alert on rising queue age and DLQ counts.
- Report cost per successful message by service/team.
- Alert on duration or peak memory increases after releases.
- Require an owner and justification when enabling provisioned capacity.
- Review minimum capacity monthly.
- Automatically scale capacity down on schedule if workloads follow steady schedules and processes allow.

Do not automatically lower PC or pollers solely because utilization dips over a brief window. Account for traffic seasonality, business events, SLOs, and scale-up times.

## 34. Controlled Optimization Process

Run each optimization cycle in order:

1. Define the business unit to optimize: message, order, payment, or job.
2. Measure baseline: cost, throughput, latency, retries, DLQs, and success rate.
3. Identify the bottleneck: batching, function duration, memory, pollers, concurrency, or downstream.
4. Pick one small change: batch size, window, memory, worker count, or capacity.
5. Benchmark using identical payloads and traffic.
6. Verify errors, duplicates, ordering, and queue visibility.
7. Calculate cost per successful operation.
8. Deploy to canary or staging first.
9. Monitor post-release behavior.
10. Keep or roll back based on SLOs and unit cost.

Do not change batch size, memory, concurrency, and pollers simultaneously. If cost drops or latency climbs, the team will struggle to identify which change caused the result.

## 35. Production Checklist

**Batching and Latency**

1. Does batch size suit payload sizes and source type?
2. Does batching window meet the latency budget?
3. Are the 6 MB payload limit and metadata accounted for?
4. Have multiple batch sizes been benchmarked?
5. Is visibility timeout long enough for function timeout and batching window?
6. Is FIFO ordering preserved?

**Java and Error Handling**

7. Can the handler process duplicates safely?
8. Is partial batch response enabled and returning the exact failed message IDs?
9. Are transient and permanent errors classified?
10. Do DLQs/quarantines have owners and replay procedures?
11. Are thread pools/virtual threads bounded to downstream capacity?
12. Are clients, serializers, and connection pools reused properly?

**Capacity**

13. Does Reserved Concurrency protect downstream dependencies?
14. Does Provisioned Concurrency genuinely reduce SLO-impacting cold starts?
15. Do callers invoke the provisioned alias/version?
16. Do Provisioned Pollers improve polling latency/throughput?
17. Do poller capacity and function concurrency align without conflict?
18. Does minimum capacity scale down during low traffic?

**FinOps**

19. Is cost per successful message measured?
20. Are retries, DLQs, queues, pollers, logs, and downstream costs included?
21. Is pricing calculated for the actual Region/architecture?
22. Are dashboards, alarms, tags, and owners in place?
23. Are before/after benchmarks recorded?
24. Is there a rollback plan if latency, error rate, or cost worsens?

## References

- [AWS Lambda pricing](https://aws.amazon.com/lambda/pricing/)
- [How Lambda processes records from stream and queue-based event sources](https://docs.aws.amazon.com/lambda/latest/dg/invocation-eventsourcemapping.html)
- [Lambda parameters for Amazon SQS event source mappings](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-parameters.html)
- [Creating and configuring an Amazon SQS event source mapping](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html)
- [Using Lambda with Amazon SQS and provisioned mode](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html)
- [Handling errors for an SQS event source in Lambda](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html)
- [Configure Lambda function memory](https://docs.aws.amazon.com/lambda/latest/dg/configuration-memory.html)
- [Powertools for AWS Lambda Java: Batch Processing](https://docs.aws.amazon.com/powertools/java/latest/utilities/batch/)
- [Azure Functions Flex Consumption pricing](https://learn.microsoft.com/azure/azure-functions/pricing)
- [Azure Functions Flex Consumption hosting](https://learn.microsoft.com/azure/azure-functions/flex-consumption-plan)
- [Google Cloud Run pricing](https://cloud.google.com/run/pricing)

## Conclusion

Optimizing batching cuts invocation overhead and boosts throughput, yet batch size and batching window must align with latency budgets, payload limits, visibility timeouts, and error handling. In Java, benchmark sequential vs. parallel processing, memory, CPU, connection pools, and partial batch responses. Idempotency and DLQs are prerequisites so large batches do not multiply duplicate side effects or retry costs.

Provisioned Concurrency prepares execution environments; Provisioned Pollers prepare resources to read SQS/Kafka; Reserved Concurrency caps and reserves concurrency to protect workloads. Each mechanism has distinct goals and pricing models. Final decisions should weigh throughput, p95/p99 latency, queue age, retries, cost per successful message, and total pipeline cost—not just a single Lambda metric.
