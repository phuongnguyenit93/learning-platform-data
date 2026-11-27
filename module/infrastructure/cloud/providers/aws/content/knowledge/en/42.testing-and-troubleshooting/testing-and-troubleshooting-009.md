# Diagnosing Lambda Timeouts, Throttling, and Queue Backlogs

## Lesson Objectives

Within the CLOUD_PROVIDERS_AWS ecosystem, AWS Lambda executes event-driven code while managing underlying compute infrastructure automatically. Lambda frequently integrates with Amazon SQS, Kinesis Data Streams, DynamoDB Streams, EventBridge, API Gateway, and other AWS services. When load increases or a dependency slows down, systems can suffer timeouts, throttling, continuous retries, or growing backlogs.

These symptoms are often tightly coupled. A function timeout can prevent SQS messages from being deleted; messages reappear after the visibility timeout expires, get processed multiple times, and expand the backlog. If an event source mapping keeps scaling while the database is already overloaded, rising Lambda concurrency can worsen downstream throttling. Therefore, diagnosis must trace the entire event path: producer, invocation model, Lambda execution, dependencies, retries, and where unprocessed messages reside.

After this lesson, learners will be able to:

- Distinguish synchronous invocations, asynchronous invocations, and event source mappings.
- Identify causes of Lambda timeouts, cold starts, and dependency latency.
- Estimate baseline concurrency from request rate and execution duration.
- Distinguish account concurrency, reserved concurrency, provisioned concurrency, and throttling.
- Diagnose SQS event source mappings when messages retry or backlogs grow.
- Configure appropriate visibility timeouts, batch sizes, maximum concurrency, and dead-letter queues.
- Use partial batch responses to retry only failed records.
- Distinguish SQS retry semantics from asynchronous Lambda invocations and stream sources.
- Monitor CloudWatch metrics, logs, SQS queue metrics, and AWS X-Ray.
- Calculate backlog drain rates and decide when to raise consumer capacity or throttle producer rates.
- Build incident runbooks, replay procedures, and idempotency safeguards for downstream dependencies.

## 1. Examine the Full Processing Flow Before Tuning Lambda

A Lambda function can be invoked under three primary models:

| Model | Who Invokes the Function? | Error Handling Behavior |
|---|---|---|
| Synchronous invocation | Client or service calls directly and awaits response | Caller receives the error and decides whether to retry; Lambda does not auto-retry function errors for synchronous invokes |
| Asynchronous invocation | Service submits events to Lambda's internal queue | Lambda manages retries per asynchronous invocation settings and event age |
| Event source mapping | Lambda polls or receives records from SQS, Kinesis, DynamoDB Streams, and other supported sources | Lambda event source mapping manages batching, checkpoints, and retries per source semantics |

Common SQS flow:

~~~mermaid
flowchart LR
    P[Producer] --> Q[(Amazon SQS queue)]
    Q --> E[Lambda event source mapping]
    E --> L[Lambda execution]
    L --> D[(Database or downstream API)]
    L -->|Success and delete| Q
    L -->|Failure or timeout| V[Visibility timeout expires]
    V --> Q
    Q -->|Receive count exceeds threshold| DLQ[(Dead-letter queue)]
~~~

The Lambda event source mapping polls the queue, groups messages into batches, and invokes the function. When the function succeeds, Lambda deletes messages from the queue. If the function fails or times out, messages remain undeleted; once the visibility timeout expires, messages become eligible for redelivery. If messages keep failing, the receive count climbs and the redrive policy can move them to a DLQ.

Key point: Lambda is not always where the backlog lives. With SQS, waiting messages remain in the queue. With asynchronous invocations, events sit in Lambda's internal queue. With Kinesis/DynamoDB Streams, records remain in the stream and consumer lag measures distance behind the latest data.

Before investigating, identify the exact invocation model and event source mapping. Retries, metrics, and replay locations differ across the three models.

## 2. What Is a Lambda Timeout?

Timeout is the maximum duration a single invocation is allowed to run. When execution exceeds the configured limit, Lambda terminates the invocation and logs a timeout error. The default Lambda timeout is 3 seconds; it can be configured up to 900 seconds (15 minutes).

Timeout does not measure CPU execution time alone. It can include:

- Initializing the execution environment and runtime on a cold start.
- Running static initialization, module imports, or dependency loading.
- Establishing connections to databases, caches, or APIs.
- Reading/writing S3, DynamoDB, SQS, or external services.
- Processing a batch of records and calling downstream systems.
- Waiting on networking, DNS, retries, locks, or connection pools.
- Flushing logs, telemetry, and cleanup before the handler exits.

A function can time out even while executing minimal CPU logic if it blocks on an HTTP request, database connection, or DNS lookup lacking its own timeout. Conversely, simply raising Lambda's timeout only extends the wait window and can hold concurrency slots longer.

### 2.1. Execution Time Breakdown

Caller-perceived latency can be broken down as:

\[
T_{total} = T_{init} + T_{handler} + T_{dependency} + T_{overhead}
\]

Where:

- `T_init`: runtime startup and initialization, which can occur on cold starts.
- `T_handler`: time spent executing handler logic.
- `T_dependency`: time waiting on databases, APIs, queues, storage, or networking.
- `T_overhead`: serialization, logging, extensions, and auxiliary overhead.

This is an overall latency analysis model and does not imply the CloudWatch `Duration` metric combines every component. For cold starts, inspect `Init Duration` in the `REPORT` log line; the `Duration` metric primarily reflects invocation execution time. Separate initialization time from handler/dependency latency when comparing runs.

For synchronous requests, timeout must be less than or equal to the upstream caller/gateway timeout so callers do not drop connections before Lambda finishes. For SQS, timeout must align with visibility timeout so messages do not become visible again while an invocation is still running.

Never guess timeouts. Measure workload p95/p99 durations, add headroom for bursts and dependency variance, and verify limits across every component in the chain.

## 3. Distinguishing Timeouts from Cold Starts and Dependency Failures

A cold start is the time Lambda spends preparing an execution environment before running the handler. It can include runtime initialization, package loading, extension startup, static initialization, and establishing connections. A cold start does not automatically mean the function times out.

Diagnostic indicators:

| Symptom | Likely Area to Inspect |
|---|---|
| First invocation is slow, subsequent ones are fast | Cold start, package size, runtime initialization |
| All invocations are slow | Handler logic, dependencies, networking, or insufficient memory/CPU |
| Duration rises alongside database latency | Connection pools, query plans, locks, or database saturation |
| Duration rises right after deployment | Dependency/package changes, initialization, or regressions |
| Timeouts occur only on large payloads | Batch size, memory pressure, serialization, or sequential processing |
| Timeouts occur only when function is in a VPC | DNS, routing, security groups, NAT, or endpoint connectivity |

Ways to reduce cold starts:

- Shrink deployment package size and remove unused dependencies.
- Move reusable client initialization outside the handler, without storing business state in the execution environment.
- Choose runtimes and frameworks with fast startup times.
- Use Provisioned Concurrency when reducing cold-start variance is required and traffic is predictable.
- Evaluate Lambda SnapStart for supported runtimes and versions, and test post-restore state carefully.
- Avoid opening many fresh database connections per invocation.

Provisioned Concurrency pre-initializes execution environments ahead of requests. It reduces initialization latency yet carries pre-allocated capacity costs and does not fix throttling or dependency bottlenecks.

Increasing memory also allocates proportionally more CPU to Lambda. If a workload is CPU-bound or performs heavy decompression/serialization, raising memory can reduce duration and total required concurrency. If the bottleneck is a database or network call, raising memory may yield little improvement.

## 4. Step-by-Step Timeout Diagnosis

When timeouts occur, pinpoint which invocation and which step consumed the time.

1. Identify the function, alias/version, and invocation request ID.
2. Compare configured timeout against `Duration` and p95/p99.
3. Read CloudWatch logs around the request ID to find the last logged step.
4. Cross-check X-Ray traces or custom subsegments if tracing is enabled.
5. Inspect dependency latency, network paths, and retries.
6. Inspect memory, CPU pressure, batch size, and payload size.
7. Determine whether timeouts trigger retries at the caller, async queue, or event source mapping.
8. Reproduce with matching payloads and dependencies in staging.

A log showing only `START` without `END`/`REPORT` may indicate runtime termination or unflushed final logs; by itself it does not prove where code hung. Add timestamped logs before/after dependency calls along with correlation IDs to isolate delays.

Example step-by-step logging:

~~~python
import json
import logging
import time

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def timed_call(name, operation):
    started = time.monotonic()
    logger.info(json.dumps({
        "event": "dependency_start",
        "dependency": name
    }))
    try:
        result = operation()
        logger.info(json.dumps({
            "event": "dependency_success",
            "dependency": name,
            "duration_ms": round((time.monotonic() - started) * 1000, 2)
        }))
        return result
    except Exception:
        logger.exception(json.dumps({
            "event": "dependency_failure",
            "dependency": name,
            "duration_ms": round((time.monotonic() - started) * 1000, 2)
        }))
        raise
~~~

Never log tokens, secrets, full request bodies, or personal data purely for debugging. Log a correlation ID and essential attributes to tie events across Lambda, SQS, and downstream services.

## 5. Setting Dependency Timeouts and Using Remaining Execution Time

HTTP clients, database drivers, and SDKs need their own timeouts. If a dependency can wait indefinitely or retry too long, Lambda stays blocked until it hits its function timeout.

Principles:

- Connection timeout shorter than total dependency call timeout.
- Read/request timeout fits within the invocation's remaining time budget.
- Bound retries with exponential backoff and jitter.
- Do not start a new operation if remaining time is insufficient to finish safely.
- When unable to finish before the deadline, return a controlled error so the source retries via its proper mechanism.

The Lambda context exposes remaining time via `get_remaining_time_in_millis()`. Example:

~~~python
import json

def lambda_handler(event, context):
    remaining_ms = context.get_remaining_time_in_millis()
    safety_margin_ms = 1500

    if remaining_ms <= safety_margin_ms:
        raise TimeoutError("Insufficient execution time remaining")

    dependency_budget_ms = remaining_ms - safety_margin_ms

    # Pass dependency_budget_ms to the HTTP/database client
    # and ensure its own connection/read timeouts stay within this budget.

    return {
        "statusCode": 200,
        "remainingMsAtStart": remaining_ms,
        "dependencyBudgetMs": dependency_budget_ms
    }
~~~

This snippet illustrates deadline budgeting; real clients must configure explicit timeouts and retries. Do not check remaining time only once at the start of the handler if multiple slow steps follow.

## 6. Lambda Concurrency and Throttling

Concurrency is the number of simultaneously executing invocations. Each invocation occupies one concurrency slot for its entire execution duration.

Estimate average concurrency using Little's Law:

\[
Concurrency \approx RequestRate \times AverageDuration
\]

Example:

- 200 requests/second.
- Average duration 0.25 seconds.
- Average concurrency is roughly 50.

If duration increases to 2 seconds at the same request rate, concurrency jumps to roughly 400. Thus, a slow dependency can trigger Lambda throttling even when incoming request rates remain flat.

Throttling occurs when Lambda cannot accept additional invocations given available concurrency or scaling capacity. Common causes:

- Account concurrency quota is exhausted.
- Function's Reserved Concurrency is lower than demand.
- Reserved Concurrency is set to 0, intentionally throttling the function.
- Multiple event source mappings invoke the same function concurrently.
- Provisioned Concurrency is insufficient for immediate demand and spillover occurs while account concurrency is constrained.
- Invocation burst rate exceeds instantaneous scaling speed.
- Downstream throttling raises duration, driving up concurrency.

### 6.1. Account Concurrency

Lambda has a regional account concurrency quota. Portions of that quota may be reserved for specific functions via reserved concurrency. Exact limits vary by account and Region; check Service Quotas and the Lambda console rather than assuming every account shares the same cap.

When total concurrency across functions approaches the quota, a spike in one function can starve other functions. Analyze concurrency at the account level, not solely on the failing function.

### 6.2. Reserved Concurrency

Reserved Concurrency dedicates a portion of account concurrency to a function and simultaneously caps that function's maximum concurrency.

Use it when:

- A critical function needs guaranteed capacity in the account.
- You want to cap a consumer to protect downstream databases or APIs.
- You must prevent a bursting function from consuming all account concurrency.

If Reserved Concurrency is set too low, Lambda can throttle even when the account still has unreserved capacity. Setting it to 0 disables invocations until reconfigured.

### 6.3. Provisioned Concurrency

Provisioned Concurrency keeps execution environments warm to minimize cold starts. It does not increase account concurrency quotas and does not solve downstream throttling.

Use Provisioned Concurrency when startup latency is a measured bottleneck and traffic is predictable. Monitor `ProvisionedConcurrencyUtilization` and `ProvisionedConcurrencySpilloverInvocations` when enabled.

## 7. Reading Throttling and Concurrency Metrics

Key Lambda CloudWatch metrics:

| Metric | Meaning | How to Use During Investigation |
|---|---|---|
| `Invocations` | Number of function invocations | Measure load and traffic patterns |
| `Duration` | Execution duration | Spot rising duration or near-timeout behavior |
| `Errors` | Invocations ending in errors | Correlate with logs and exception types |
| `Throttles` | Invocations rejected due to throttling | Check account/function concurrency |
| `ConcurrentExecutions` | Concurrent running invocations | Compare against reserved/account quotas |
| `UnreservedConcurrentExecutions` | Concurrency outside reserved pools | Assess pressure on the shared account pool |
| `ProvisionedConcurrencyUtilization` | Utilization of Provisioned Concurrency | Check whether pre-warmed capacity suffices |
| `ProvisionedConcurrencySpilloverInvocations` | Invocations overflowing provisioned capacity | Identify spillover |
| `AsyncEventAge` | Age of events in the asynchronous queue | Detect async backlogs |
| `AsyncEventsDropped` | Asynchronous events discarded | Investigate event age/retry limits |
| `IteratorAge` | Lag of stream consumer records | Monitor Kinesis/DynamoDB Streams lag |

Rising `Throttles` alongside `ConcurrentExecutions` near limits points to concurrency pressure. If `Duration` rises first and `Throttles` follows, inspect dependency latency: invocations are holding slots longer rather than purely lacking quota.

Rising `Throttles` while `ConcurrentExecutions` stays low can mean Reserved Concurrency is set too low, set to 0, or another scaling/configuration limit applies. Inspect function configuration and invocation sources.

Never sum metrics arbitrarily across dimensions. Inspect exact `FunctionName`, `Resource`, `ExecutedVersion`, and concurrency type; distinguish aliases/versions when traffic is split.

## 8. How SQS Event Source Mapping Works

An SQS event source mapping is a Lambda-managed poller. It receives messages from a queue, builds batches, and invokes the function. Upon success, Lambda deletes the messages. Upon failure, messages remain in the queue and become eligible for redelivery after the visibility timeout.

Key settings:

| Setting | Role |
|---|---|
| `BatchSize` | Maximum messages delivered in a single invocation |
| `MaximumBatchingWindowInSeconds` | Max wait time to gather a batch before invoking |
| `FunctionResponseTypes` | Enables `ReportBatchItemFailures` to report failed messages individually |
| `ScalingConfig.MaximumConcurrency` | Caps concurrency for the event source mapping |
| `Queue visibility timeout` | Duration a message stays hidden after being received |
| `Redrive policy` | Moves messages to a DLQ after max failed receive attempts |
| `FIFO MessageGroupId` | Groups messages to preserve processing order |

For SQS Standard, max batch size can go up to 10,000 messages depending on configuration; for SQS FIFO, max is 10 messages per batch. Batch sizes above 10 require `MaximumBatchingWindowInSeconds` of at least 1 second. Always verify current quotas and total invocation payload limits.

Larger batch sizes reduce invocations per message yet increase processing duration, memory pressure, and the number of messages retried together if one record fails. Smaller batch sizes shrink blast radius yet increase invocation counts and overhead.

## 9. Visibility Timeout and Retry Loops

Visibility timeout is how long SQS hides a message from other consumers after handing it to the event source mapping. If the function has not finished and deleted the message before the timeout expires, the message can reappear.

AWS recommends setting the SQS queue visibility timeout to at least six times the Lambda function timeout plus the event source mapping's maximum batching window.

\[
VisibilityTimeout \ge 6 \times FunctionTimeout + BatchingWindow
\]

Example:

- Lambda timeout: 30 seconds.
- Maximum batching window: 5 seconds.
- Recommended minimum visibility timeout: 6 × 30 + 5 = 185 seconds.

Setting visibility timeout too short can cause the same message to be processed concurrently multiple times. Setting it too long delays retries or DLQ transitions for failed messages. Choose a value based on p99 processing time, retry behavior, and recovery needs.

If function timeout is 30 seconds while visibility timeout is only 30 seconds, the message can reappear before the first invocation terminates. Two invocations processing one event concurrently can cause duplicate writes or race conditions.

## 10. Partial Batch Responses: Retrying Only Failed Records

By default, if a batch SQS invocation fails, the entire batch can return to the queue for retry. This causes already-succeeded records in the batch to be reprocessed.

Enable partial batch responses by setting `FunctionResponseTypes` to include `ReportBatchItemFailures` on the event source mapping. The function then returns a list of failed message identifiers to retry.

Python handler example:

~~~python
import json

def process_message(record):
    body = json.loads(record["body"])
    # Validate and persist the business event idempotently.
    # Raise an exception when this message cannot be processed.

def lambda_handler(event, context):
    failures = []

    for record in event["Records"]:
        try:
            process_message(record)
        except Exception:
            failures.append({
                "itemIdentifier": record["messageId"]
            })

    return {
        "batchItemFailures": failures
    }
~~~

When partial batch responses are enabled, records omitted from `batchItemFailures` are treated as succeeded and deleted from the queue by Lambda. Only listed records are retried.

Notes:

- If the handler throws an invocation-level exception, the entire batch is still treated as failed.
- For FIFO queues, once one record fails, stop processing subsequent records in the same batch and return the failed record plus all unprocessed ones to preserve ordering.
- Partial batch responses do not guarantee exactly-once delivery; messages can still be redelivered in some scenarios.
- Consumers must remain idempotent even with partial batch responses enabled.

Enable partial batch responses via the AWS CLI:

~~~bash
aws lambda update-event-source-mapping \
  --uuid EVENT_SOURCE_MAPPING_UUID \
  --function-response-types ReportBatchItemFailures \
  --region ap-southeast-1
~~~

Verify configuration:

~~~bash
aws lambda get-event-source-mapping \
  --uuid EVENT_SOURCE_MAPPING_UUID \
  --region ap-southeast-1
~~~

## 11. DLQs and Redrive for SQS

A dead-letter queue (DLQ) holds messages that fail processing after the receive threshold configured in the source queue's redrive policy.

Example redrive policy:

~~~json
{
  "deadLetterTargetArn": "arn:aws:sqs:ap-southeast-1:111122223333:iot-events-dlq",
  "maxReceiveCount": "5"
}
~~~

`maxReceiveCount` must be high enough to survive transient failures yet low enough to stop poison messages from looping endlessly. If too low, a brief downstream blip pushes valid messages into the DLQ. If too high, failing messages tie up pollers and delay fresh traffic.

Redrive workflow:

1. Check `ApproximateNumberOfMessagesVisible` and `ApproximateAgeOfOldestMessage` on the DLQ.
2. Group errors by exception, schema version, tenant, or downstream dependency.
3. Fix the root cause before replaying.
4. Verify messages can be processed by current code or require migration.
5. Use an SQS redrive task or controlled replay tool.
6. Monitor both source queue and DLQ throughout replay.
7. Verify idempotency so replays do not duplicate side effects.

With SQS Standard, messages moved to a DLQ retain their original enqueue timestamp; DLQ retention should exceed source queue retention to allow investigation time. With FIFO queues, the enqueue timestamp resets when moved to a DLQ. Design retention and replay around queue type.

A DLQ does not fix messages or automatically re-run functions. It merely holds messages routed by the redrive policy; operators must resolve root causes and initiate redrives.

## 12. Diagnosing Why Backlogs Grow

Backlogs grow whenever message arrival rate exceeds the rate at which consumers successfully process and delete messages.

Let:

- `λ`: incoming message rate (messages/second).
- `μ`: successful processing and deletion rate (messages/second).
- `B`: queued messages waiting.

If `λ` exceeds `μ`, the backlog grows by roughly `λ − μ` messages/second. If `μ` exceeds `λ`, the queue drains.

Estimating consumer throughput:

\[
\mu \approx \frac{ConcurrentInvocations \times BatchSize \times SuccessRatio}{AverageBatchDuration}
\]

This is an approximate model; batches may be partially full, records vary in processing time, and throttling/downstream latency reduce real throughput.

Example:

- 20 concurrent invocations.
- Batch size 10.
- Average batch duration 2 seconds.
- Success ratio 95%.

Theoretical throughput is roughly 20 × 10 × 0.95 / 2 = 95 messages/second.

If producers send 120 messages/second, the backlog grows by roughly 25 messages/second. If a backlog stands at 90,000 messages and producers drop to 40 messages/second while consumers process 95 messages/second, estimated drain time is:

\[
DrainTime \approx \frac{Backlog}{\mu - \lambda}
= \frac{90,000}{95 - 40}
\approx 1,636 \text{ seconds}
\]

That equals roughly 27 minutes. Always use actual successful processing throughput rather than raw invocation starts.

## 13. CloudWatch Metrics for SQS Backlogs

Monitor SQS metrics in the `AWS/SQS` namespace:

| Metric | Meaning | Interpretation |
|---|---|---|
| `ApproximateNumberOfMessagesVisible` | Messages waiting and available for receive | Unprocessed backlog |
| `ApproximateNumberOfMessagesNotVisible` | Messages currently in-flight/hidden by visibility timeout | Consumers actively receiving or processing slowly |
| `ApproximateNumberOfMessagesDelayed` | Messages currently delayed | Delay queues or per-message delays |
| `ApproximateAgeOfOldestMessage` | Age of oldest message still in queue | End-to-end lag and SLA breach risk |
| `NumberOfMessagesSent` | Messages sent to the queue | Producer rate |
| `NumberOfMessagesReceived` | Receive attempts across messages | Can exceed unique messages due to retries |
| `NumberOfMessagesDeleted` | Messages deleted | Approximates successful throughput, subject to metric semantics |
| `NumberOfEmptyReceives` | Polls returning zero messages | May indicate excess polling |

Read metrics over the exact same time window:

- Rising Visible, low NotVisible: low consumer capacity, mapping disabled, or poller unable to receive.
- Rising Visible, high NotVisible: many messages in-flight; check invocation duration, visibility timeout, and downstream dependencies.
- Continuously rising `AgeOfOldestMessage`: consumers cannot keep up or poison messages are stalling progress.
- `Received` rising without matching `Deleted`: messages are redelivered, invocations are failing, or visibility timeouts are looping.
- Rising DLQ visible count: message errors are exceeding `maxReceiveCount`.

SQS metrics are approximate and published periodically; never draw conclusions from a single datapoint. Compare trends, queue types, and actual logs.

## 14. CloudWatch Metrics for Lambda and Event Source Mappings

Combine Lambda metrics with SQS metrics to pinpoint where the backlog sits.

| Category | Metric | Signal |
|---|---|---|
| Execution | `Duration` | Trending up or near timeout |
| Execution | `Errors` | Handler exceptions or timeouts |
| Capacity | `Throttles` | Lambda rejecting additional invocations |
| Capacity | `ConcurrentExecutions` | Hitting reserved/account concurrency |
| Async | `AsyncEventAge` | Events waiting long in internal async queue |
| Async | `AsyncEventsDropped` | Events dropped due to age/retry limits |
| Streams | `IteratorAge` | Consumer lag on Kinesis/DynamoDB Streams |
| Provisioned | `ProvisionedConcurrencySpilloverInvocations` | Invocations exceeding provisioned capacity |
| SQS | `ApproximateNumberOfMessagesVisible` | Queue backlog |
| SQS | `ApproximateAgeOfOldestMessage` | Age of oldest queued message |
| SQS | `ApproximateNumberOfMessagesNotVisible` | Messages currently in-flight |

For SQS event source mappings, enable event source mapping metrics when granular polling, invocation, and record-processing telemetry is needed. These metrics can incur CloudWatch charges; enable only the groups needed for SLOs and troubleshooting.

AWS X-Ray or compatible tracing reveals time spent in downstream services. If Lambda spends only 100 ms in code while a database subsegment takes 8 seconds, investigate the database/queries/connection pools rather than raising Lambda memory.

## 15. Distinguishing SQS Backlogs from Kinesis Consumer Lag

Both SQS and Kinesis can exhibit backlog symptoms, yet observation and retry behavior differ.

| Characteristic | SQS | Kinesis Data Streams |
|---|---|---|
| Data unit | Message | Record within a shard |
| Consumer model | Polled via event source mapping | Polled or Enhanced Fan-Out |
| Backlog signal | Visible messages and age | `IteratorAge` / `MillisBehindLatest` |
| Post-processing removal | Lambda deletes message upon success | Record stays for retention; consumer checkpoint advances |
| Retries | Visibility timeout and redrive policy | Batch retries, checkpoints, shard ordering, and on-failure destination |
| Poison records | Can route to SQS DLQ | Can stall shard progress if retry policy fails to handle |
| Scaling | Mapping concurrency and queue throughput | Shard count, parallelization factor, and consumer capacity |

With Kinesis, rising `IteratorAge` means consumers are falling behind the latest records. Inspect hot shards, batch retries, checkpoints, and downstream dependencies. Raising Lambda concurrency does not always help if a single shard is constrained by ordering or partition keys.

## 16. Controlling Concurrency to Protect Downstream Systems

Raising concurrency boosts throughput yet also multiplies database connections, API requests, and downstream load.

For example, suppose a database supports only 200 connections. If each Lambda invocation opens 5 connections and 100 invocations run concurrently, theoretical demand hits 500 connections, overwhelming the database.

Control mechanisms:

- Set Reserved Concurrency on the function to cap total invocations.
- Set `ScalingConfig.MaximumConcurrency` per SQS event source mapping.
- Ensure the sum of `MaximumConcurrency` across mappings does not exceed the function's Reserved Concurrency.
- Use connection reuse and bounded pools.
- Buffer with SQS to decouple ingest rates from downstream processing rates.
- Use exponential backoff and jitter when downstream returns 429/5xx.
- Lower batch size if one invocation triggers too many parallel downstream calls.
- Separate consumer workloads by queue/priority so large batches do not starve urgent messages.

Example setting maximum concurrency on an event source mapping:

~~~bash
aws lambda update-event-source-mapping \
  --uuid EVENT_SOURCE_MAPPING_UUID \
  --scaling-config '{"MaximumConcurrency":40}' \
  --region ap-southeast-1
~~~

`MaximumConcurrency` caps that single mapping. If a function has multiple mappings, sum the maximum concurrency across all mappings plus other invocation sources.

Never set Reserved Concurrency lower than the combined maximum concurrency expected across event source mappings. If a mapping tries to scale beyond the function cap, Lambda throttles and messages return to the queue after visibility timeout.

## 17. Batch Size, Batching Window, and Efficient Processing

Batch size controls how many messages enter each invocation. Batching window lets the poller wait for additional messages to assemble larger batches, trading latency for throughput.

Choose batch size based on:

- Payload sizes and total invocation payload limits.
- Processing time per message.
- Independence between records.
- Partial failure handling capability.
- Function memory and CPU.
- Downstream request rates.
- Message age SLAs.

Larger batch sizes boost throughput when handlers perform vectorized/bulk writes. Yet if one bad message fails an entire batch, healthy records get reprocessed. Enable partial batch responses to narrow retry scope.

Batching windows help when producers send sparse messages; pollers accumulate messages to cut invocation counts. Avoid increasing batching windows when SLAs demand near-real-time processing.

If every message triggers a separate database call, consider batch write APIs or grouping records by key before writing. Ensure bulk operations can retry idempotently and identify which records committed during partial successes.

## 18. Asynchronous Invocations: Retries and Event Age

Asynchronous invocations are commonly used with S3 notifications, EventBridge, or API Invoke with `InvocationType=Event`. Lambda places the event in an internal queue and returns an acceptance response to the caller.

For function errors, Lambda retries twice by default after the initial attempt. For throttling or system errors, Lambda retries with exponential backoff while the event remains valid. Event age and retry counts are configurable; events can expire and be discarded if not processed in time.

Asynchronous invocation settings include:

- `MaximumEventAgeInSeconds`: maximum age an event is retained before being dropped.
- `MaximumRetryAttempts`: number of retries on function errors.
- `OnFailure` destination or DLQ: captures failed events for investigation.
- `OnSuccess` destination: records successful outcomes for auditing if needed.

Distinguishing async destinations from SQS redrive DLQs:

| Mechanism | Applies To | Contents |
|---|---|---|
| Lambda asynchronous DLQ | Async invocation | Original event that failed processing |
| Lambda async `OnFailure` destination | Async invocation | Invocation metadata, response/error details, and event |
| SQS source queue DLQ | SQS event source mapping | Original message exceeding the queue redrive policy's `maxReceiveCount` |
| Stream on-failure destination | Kinesis/DynamoDB Streams event source mapping | Failed batch/record metadata per source mapping config |

Never configure one DLQ type expecting it to catch errors from every invocation model. Identify which invocation mechanism carries the event.

## 19. Troubleshooting Scenario: Timeouts Driving Up an SQS Backlog

Suppose an SQS queue receives 500 messages/second. Lambda processes batches of 10 messages with a 30-second timeout and Reserved Concurrency of 100. Database latency jumps from 200 ms to 5 seconds.

Symptoms:

- Lambda `Duration` climbs.
- `ConcurrentExecutions` approaches 100.
- `Throttles` climbs.
- SQS `ApproximateNumberOfMessagesVisible` climbs.
- `ApproximateAgeOfOldestMessage` climbs.
- `ApproximateNumberOfMessagesNotVisible` climbs.
- `NumberOfMessagesReceived` exceeds `NumberOfMessagesDeleted` due to retries.

Causal chain:

1. Database slowness forces each invocation to hold a concurrency slot longer.
2. At constant message rates, required concurrency rises per `request rate × duration`.
3. Reserved Concurrency caps Lambda at 100.
4. Pollers cannot keep up with incoming messages; visible backlog grows.
5. Timeouts or errors leave messages undeleted.
6. Visibility timeouts expire, messages reappear, and receive counts increment.
7. Poison messages or repeatedly failing payloads move to the DLQ.

Runbook:

1. Inspect Lambda `Duration`, `Errors`, `Throttles`, and `ConcurrentExecutions`.
2. Inspect SQS visible, not-visible, age, and DLQ metrics.
3. Check databases/APIs for throttling, locks, connection exhaustion, or high latency.
4. Lower event source mapping `MaximumConcurrency` if downstream is overloaded.
5. Recover the dependency or isolate workloads onto separate queues if possible.
6. Enable partial batch responses if handlers do not yet support them.
7. Verify visibility timeout meets AWS minimum recommendations.
8. Check redrive policy and DLQ; preserve poison messages for inspection.
9. Once downstream recovers, raise concurrency gradually and monitor the drain rate.
10. Verify oldest message age drops, delete rate exceeds send rate, and the DLQ stops growing.

Never raise concurrency unboundedly while a database is already overloaded. That can cascade the outage across the data tier.

## 20. Inspecting and Configuring with the AWS CLI

Get Lambda configuration:

~~~bash
aws lambda get-function-configuration \
  --function-name orders-consumer \
  --region ap-southeast-1
~~~

Update timeout and memory after measuring:

~~~bash
aws lambda update-function-configuration \
  --function-name orders-consumer \
  --timeout 45 \
  --memory-size 1024 \
  --region ap-southeast-1
~~~

Check function concurrency:

~~~bash
aws lambda get-function-concurrency \
  --function-name orders-consumer \
  --region ap-southeast-1
~~~

List event source mappings:

~~~bash
aws lambda list-event-source-mappings \
  --function-name orders-consumer \
  --region ap-southeast-1
~~~

Inspect queue attributes:

~~~bash
aws sqs get-queue-attributes \
  --queue-url https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-events \
  --attribute-names All \
  --region ap-southeast-1
~~~

Update commands modify production configuration. Use change control, verify aliases/versions, and test in staging first. Never change timeout, batch size, concurrency, and retry settings all at once without a baseline; adjust one group at a time so impact stays measurable.

## 21. Security and Reliability During Replay

SQS messages and DLQs can contain business data or sensitive information. Grant receive/delete/send/redrive permissions only to required principals. Use encryption at rest with SQS-managed keys or KMS keys as required; verify KMS key policies when Lambda or operators access encrypted queues.

Common permissions:

- Lambda execution role needs log-writing permissions and access to dependencies.
- Lambda execution role needs `sqs:ReceiveMessage`, `sqs:DeleteMessage`, and `sqs:GetQueueAttributes` on the source queue; if using a customer managed KMS key, check `kms:Decrypt` and the key policy.
- Operators need permissions to inspect the DLQ and initiate redrive tasks.
- Producers need only permission to send messages to the source queue.
- Never grant broad DLQ read permissions to applications that do not handle failed messages.

Replays must preserve original event IDs and can attach replay metadata such as `replayBatchId`, `replayedAt`, and `originalQueue`. Consumers should distinguish replays from fresh events if business rules require it. Before bulk redriving, verify target capacity to avoid triggering a post-outage surge.

## 22. Testing and Operations Checklist

Before promoting a Lambda consumer to production:

- Identify invocation model and retry semantics.
- Choose timeout from p99 duration and upstream deadlines.
- Set HTTP/DB client timeouts shorter than remaining Lambda execution time.
- Measure cold starts, memory, CPU, and dependency latency.
- Estimate concurrency from `request rate × duration`.
- Set Reserved Concurrency to protect downstream dependencies.
- Set `MaximumConcurrency` on SQS mappings where needed.
- Ensure combined mapping concurrency aligns with reserved/account concurrency.
- Set visibility timeout to meet AWS minimum recommendations.
- Choose batch size and batching window around payloads, SLAs, and downstream limits.
- Enable partial batch responses and test mid-batch record failures.
- Configure SQS redrive policies and DLQ retention.
- Design idempotency for duplicates and replays.
- Build dashboards covering Lambda, SQS, and downstream tiers.
- Alert on oldest message age, visible backlog, throttles, errors, and duration.
- Load test bursts, poison messages, dependency latency, and database throttling.
- Rehearse DLQ redrives and verify post-recovery drain rates.

### 22.1. Testing Matrix

| Scenario | Expected Outcome to Verify |
|---|---|
| Handler exceeds timeout | Invocation fails; source retries per exact semantics |
| Database latency rises | Timeouts/remaining time stay controlled; concurrency does not crash DB |
| Reserved Concurrency hits cap | Throttles trigger alarms; queue loses zero messages |
| Batch has one failing record | Partial batch response retries only that record |
| FIFO batch has a failing record | Records after the failure are not processed out of order |
| Visibility timeout too short | Tests detect concurrent duplicate processing |
| Poison message | Message moves to DLQ per `maxReceiveCount` |
| Downstream outage | Backlog grows under control and drains after recovery |
| DLQ redrive | Replayed messages cause zero duplicate side effects |
| Producer burst | Event source mapping scales within downstream limits |

## Conclusion

Lambda timeouts, throttling, and queue backlogs are three symptoms that can lock into a feedback loop: slow dependencies lengthen invocations, concurrency climbs, Lambda throttles, messages go undeleted, visibility timeouts expire, and backlogs keep growing. Proper diagnosis identifies the invocation model, inspects Lambda/SQS metrics across the same time window, and locates whichever dependency is actually slowing down the handler.

For SQS, visibility timeout, batch size, partial batch responses, maximum concurrency, and DLQs govern how the system recovers. Reserved Concurrency protects the account and downstream systems; Provisioned Concurrency reduces cold starts. These two mechanisms solve different problems. Raising concurrency helps only when downstream dependencies still have spare capacity.

A production consumer requires dependency timeouts, idempotency, bounded retries, DLQs, and redrive runbooks. Monitor oldest message age, visible backlog, receive/delete rates, Lambda duration/errors/throttles, and downstream latency to verify whether backlogs are draining. Test bursts, poison messages, and dependency outages before handling real traffic.

## References

- [AWS Lambda execution environment and timeout](https://docs.aws.amazon.com/lambda/latest/dg/configuration-timeout.html)
- [AWS Lambda concurrency](https://docs.aws.amazon.com/lambda/latest/dg/lambda-concurrency.html)
- [Reserved concurrency](https://docs.aws.amazon.com/lambda/latest/dg/configuration-concurrency.html)
- [Provisioned Concurrency](https://docs.aws.amazon.com/lambda/latest/dg/provisioned-concurrency.html)
- [Troubleshooting Lambda function errors](https://docs.aws.amazon.com/lambda/latest/dg/troubleshooting-execution.html)
- [Lambda asynchronous invocation error handling](https://docs.aws.amazon.com/lambda/latest/dg/invocation-async-error-handling.html)
- [Using Lambda with Amazon SQS](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html)
- [Configuring an SQS event source mapping](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html)
- [Handling errors for an SQS event source](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html)
- [Partial batch response for SQS](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html)
- [SQS visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html)
- [Configuring an SQS dead-letter queue](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html)
- [Monitoring Lambda functions with CloudWatch](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-metrics.html)
- [Monitoring Amazon SQS queues using CloudWatch](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-available-cloudwatch-metrics.html)
- [Lambda event source mapping metrics](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-metrics-types.html)
- [AWS X-Ray with Lambda](https://docs.aws.amazon.com/lambda/latest/dg/services-xray.html)
- [Lambda best practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [AWS Lambda quotas](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html)
