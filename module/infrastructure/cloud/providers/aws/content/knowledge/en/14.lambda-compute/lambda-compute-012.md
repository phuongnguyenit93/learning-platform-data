# Lambda Observability and Execution Cost Control

> **Chapter:** Lambda Compute  
> **Module:** CLOUD_PROVIDERS_AWS — explore AWS across Regions/Availability Zones (AZs), IAM, VPC, compute, storage, databases, integration, and serverless; practice service selection, secure system design, monitoring, recovery, and cost management.

## Learning Objectives

After this lesson, learners can:

1. Distinguish **metrics, logs, traces, events**, and billing data; build a complete observability picture for applications running on **AWS Lambda**.
2. Interpret CloudWatch metrics accurately — **Invocations, Errors, Duration, Throttles, ConcurrentExecutions, AsyncEventAge, AsyncEventsDropped**, and **IteratorAge** — including choosing the right statistic (**Sum / Average / Maximum / p95**).
3. Read **START / END / REPORT** logs, distinguish **Duration, Billed Duration, Init Duration, Memory Size, Max Memory Used**, and apply structured logging, correlation IDs, Logs Insights, and log retention.
4. Use **AWS X-Ray**, **CloudWatch Lambda Insights**, and other supported telemetry tools to diagnose cold starts, latency, memory, networking, and dependencies.
5. Distinguish **synchronous invocation**, **asynchronous invocation**, and **event source mapping**; monitor retries, duplicate deliveries, DLQs/destinations, queue age, and stream lag.
6. Estimate costs across **requests, GB-seconds, memory, duration**, Provisioned Concurrency, ephemeral storage, SnapStart, and integrated services.
7. Optimize memory/CPU, timeouts, SDK reuse, batching, concurrency, logging, and networking **without sacrificing reliability or security**.
8. Inspect configurations alongside CloudWatch metrics using **read-only AWS CLI**, and design dashboards, alarms, and incident/cost investigation workflows.

## 1. Scoping: How Is Lambda Observed and Billed?

**AWS Lambda** is a compute service that runs code on requests/events without requiring manual server provisioning like traditional EC2. Applications can be invoked by API Gateway, ALB, S3, EventBridge, SNS, or event source mappings for SQS, DynamoDB Streams, Kinesis, and other supported sources.

AWS Lambda currently offers multiple compute models such as **Lambda Event Functions**, **Lambda Managed Instances**, and additional published modes over time. This lesson focuses on **traditional on-demand Lambda Event Functions**, typically billed by requests and memory-weighted execution duration. Do not mechanically apply Event Function formulas to every other Lambda compute mode.

A small app may work fine in a lab, yet in production you must answer:

- How many invocations occurred, how many failed, and did errors impact users?
- How long do tasks take at the mean and at **p95/p99**?
- Are cold starts, throttles, or concurrency caps occurring?
- Which events retried, landed in a DLQ, or expired?
- Did cost rise due to **higher traffic**, **longer runs**, **higher memory**, or **logging/egress**?
- Under load, is the application overwhelming RDS, SQS, or downstream APIs?

No single metric answers all of these questions.

~~~mermaid
flowchart TB
    IN["API Gateway / S3 / SQS / EventBridge"] --> L["AWS Lambda function"]
    L --> DB[("RDS / DynamoDB / S3 / API")]
    L --> CW["CloudWatch Metrics"]
    L --> LOG["CloudWatch Logs / log destination"]
    L --> XR["AWS X-Ray / tracing"]
    CW --> DASH["Dashboard + alarms"]
    LOG --> DASH
    XR --> DASH
    BILL["Cost Explorer / CUR / Budgets"] --> COST["Cost analysis and forecasting"]
    DASH --> OPS["Detection, triage, risk mitigation"]
    COST --> OPS
~~~

This diagram is logical. Metrics, logs, traces, and billing have **different** storage engines, permissions, refresh latencies, retention windows, and pricing models. AWS generally emits technical metrics far faster than aggregated billing data, so never expect Cost Explorer to reflect per-request spend instantaneously.

### 1.1. The Four Observability Pillars

| Signal | Question answered | Lambda examples | Limitations |
| --- | --- | --- | --- |
| **Metrics** | Is the system healthy, and how are trends shifting? | `Invocations`, `Errors`, `Duration` p95, `ConcurrentExecutions`. | Does not detail an individual request. |
| **Logs** | What did one invocation do, and what failed? | Java exceptions, business status, `START`/`REPORT`, `requestId`. | High log volume; needs querying and sensitive-data protection. |
| **Traces** | Where is time spent across components and dependencies? | API Gateway → Lambda → DynamoDB, X-Ray segments. | Subject to sampling/instrumentation and extra cost. |
| **Events/state** | Are source events or processing states delayed, duplicated, or dropped? | SQS backlog, DLQ, EventBridge rule failures, DynamoDB stream lag. | Lambda metrics alone do not reveal full upstream state. |

**Billing/usage data** adds a financial layer to attribute cost spikes and measure optimization impact — it is not real-time health telemetry.

### 1.2. Define SLIs/SLOs Before Picking Dashboards

Example product with an invoice-creation API:

- **Availability SLI:** share of API requests completing validly, not merely Lambda invocations without thrown exceptions.
- **Latency SLI:** end-to-end API p95 under 500 ms under normal load.
- **Background processing SLI:** 99% of queued invoices processed within 2 minutes.
- **Correctness SLI:** zero duplicate invoices issued across retries.
- **Cost KPI:** total cost per 1,000 valid invoices, including Lambda and downstream services.

Watching only **`Invocations`** and **`Errors`** misses cases where the API returns HTTP 500 cleanly at the runtime layer, queued events never reach the handler, or business actions execute twice.

## 2. Lambda Lifecycle and Execution Timing

On each invocation, Lambda uses an **execution environment** running the configured runtime. Environments may be **newly initialized (cold start)** or **reused (warm reuse)**; never assume every invocation is a cold start.

~~~mermaid
sequenceDiagram
    participant E as Event source
    participant S as Lambda service
    participant R as Runtime / extension
    participant H as Function handler
    E->>S: Invoke
    alt Cold start
      S->>R: INIT (runtime, dependencies, init code)
    else Warm reuse
      Note over R: Execution environment already exists
    end
    S->>H: INVOKE event
    H-->>S: Response / error
    S-->>E: Result per invocation mode
    Note over S,R: Freeze/reuse or shutdown per lifecycle
~~~

### 2.1. Init, Invoke, and Shutdown

- **INIT:** Lambda loads the runtime, layers, and dependencies, and runs initialization code outside the handler; extensions may also run initialization.
- **INVOKE:** the handler processes the event, calls dependencies, and returns a response or throws an error.
- **SHUTDOWN:** the execution environment terminates per Lambda's lifecycle.

When an environment is reused, static objects, SDK clients, or connection pools may persist across invocations. **Reuse is never guaranteed**; code must operate correctly on fresh initialization as well.

### 2.2. Cold Starts Are Not the `Duration` Metric

CloudWatch **`Duration`** measures handler execution time per published metric definitions — **it does not include all cold initialization time**. By contrast, latency seen by clients at API Gateway/ALB includes cold starts plus networking and integration overhead.

A `REPORT` log line might show:

~~~text
START RequestId: a1b2c3d4-EXAMPLE Version: $LATEST
END RequestId: a1b2c3d4-EXAMPLE
REPORT RequestId: a1b2c3d4-EXAMPLE
Duration: 183.42 ms
Billed Duration: 319 ms
Memory Size: 512 MB
Max Memory Used: 207 MB
Init Duration: 135.58 ms
~~~

**Numbers are illustrative.** `REPORT` fields and format vary by runtime, logging mode, and AWS platform updates.

Observations:

- The handler took ~**183 ms** per `Duration`.
- **`Billed Duration`** can be higher due to init/extensions and active billing/rounding rules.
- Lambda was configured with **512 MB**, and billing uses configured memory — not the **207 MB actually used**.
- **`Init Duration`** reveals observed initialization time, not something to manually add to every invocation or equate with `Duration`.

### 2.3. Suppressed Init and Timeouts

When an invocation fails, the runtime may reset and run the next initialization inside the `INVOKE` phase (termed **suppressed init** by AWS). Some `REPORT`/`Duration` logs can look confusing if you only read `START`/`END`; the **Lambda Telemetry API** exposes finer-grained lifecycle events.

Timeouts are a major runtime failure:

- If a handler exceeds configured **`Timeout`**, Lambda terminates the invocation.
- CloudWatch **`Errors`** increments and `REPORT` logs **`Status: timeout`** per log format.
- Callers/downstream triggers may retry depending on invocation mode.
- Raising timeout simply lets runs linger longer; it will not fix a hung DB query or missing VPC egress.

For standard Event Functions, configurable timeout caps at **900 seconds (15 minutes)**; specialized Lambda compute modes have separate limits documented in current AWS docs.

## 3. Default Lambda CloudWatch Metrics

Lambda emits metrics automatically into the **`AWS/Lambda`** namespace. Always filter by the right **Region, `FunctionName`, `Resource`, or `ExecutedVersion`**, since functions, aliases, and versions carry different traffic and dimensions.

### 3.1. Invocation and Error Metrics

| Metric | Meaning | Statistic to inspect | Action on anomaly |
| --- | --- | --- | --- |
| **`Invocations`** | Times function code ran (including successes and function errors; throttled requests rejected pre-invoke are excluded). | **Sum** per minute/hour. | Compare traffic sources, deployments, retries, and cost. |
| **`Errors`** | Invocations ending in function/runtime errors (unhandled exceptions, timeouts). | **Sum**, plus computed error rate. | Inspect logs, request IDs, downstream health, error types. |
| **`Throttles`** | Invocation requests rejected due to concurrency/rate limits. | **Sum**. | Check reserved/account concurrency, bursts, caller retries. |
| **`DeadLetterErrors`** | Lambda failed to deliver an async event to the configured DLQ. | **Sum**. | Check queue/topic existence, IAM policies, and KMS. |
| **`DestinationDeliveryFailures`** | Failed delivering invocation record to a configured destination. | **Sum**. | Check destination ARN, resource policy, payload size, quotas. |
| **`RecursiveInvocationsDropped`** | Lambda blocked an invocation suspected of recursive looping where supported. | **Sum**. | Check self-triggering loops, S3 output/event loops, and retries. |

**`Invocations` is not the number of end-user HTTP requests.** One API call may invoke multiple functions, one SQS batch invocation carries many messages, and retries generate extra invocations.

### 3.2. Calculating Error Rate Properly

Over a time window:

\[
\text{Lambda Error Rate} =
\frac{\text{Sum(Errors)}}{\text{Sum(Invocations)}}\times100\%
\]

For example, 20 `Errors` out of 4,000 `Invocations` → **0.5% Lambda error rate**.

Still, check these caveats:

- If **`Invocations = 0`**, the ratio is undefined — never divide by zero and report 0% or 100%.
- If code catches exceptions and returns **HTTP 500** cleanly in its response body, Lambda marks the invocation **succeeded** and `Errors` stays 0.
- If API Gateway/ALB rejects requests **before invoking Lambda**, Lambda `Invocations` won't increment.
- If a message retries multiple times and throws each time, every failed attempt adds to `Errors`.

Critical dashboards must therefore include **API Gateway 4xx/5xx, ALB 5xx, successful business transactions, and SQS DLQ/age** or custom metrics.

### 3.3. Performance Metrics

| Metric | Unit/meaning | Recommendation |
| --- | --- | --- |
| **`Duration`** | Milliseconds spent executing the handler. | Watch Average, p95/p99, and Maximum per workload; compare pre/post deploy. |
| **`PostRuntimeExtensionsDuration`** | Time extensions spend running after handler return where measured. | If high, audit observability/extension overhead. |
| **`IteratorAge`** | Age of stream records when processed (Kinesis/DynamoDB/DocumentDB streams). | Watch Maximum or appropriate aggregations; alert on stream lag. |
| **`OffsetLag`** | Offset processing lag for Kafka/MSK where supported. | Monitor backlog by Kafka topic/consumer context. |

**`IteratorAge` is not SQS backlog.** For SQS, track **`ApproximateAgeOfOldestMessage`**, visible/in-flight message counts, DLQs, and enabled ESM metrics.

### 3.4. Concurrency Metrics

| Metric | Meaning | When useful |
| --- | --- | --- |
| **`ConcurrentExecutions`** | Number of invocations executing simultaneously. | Analyze peaks and quota pressure. |
| **`UnreservedConcurrentExecutions`** | Concurrency drawn from the Regional unreserved pool. | Spot capacity contention across functions. |
| **`ClaimedAccountConcurrency`** | Account capacity currently claimed per AWS definition. | Gauge risk of hitting account concurrency quota. |
| **`ProvisionedConcurrentExecutions`** | Active concurrency running inside a version/alias provisioned pool. | Track provisioned capacity utilization. |
| **`ProvisionedConcurrencyUtilization`** | Fraction of provisioned capacity actively busy. | Decide when to scale provisioned capacity up or down. |
| **`ProvisionedConcurrencyInvocations`** | Invocations served by provisioned concurrency. | Measure value of provisioned capacity. |
| **`ProvisionedConcurrencySpilloverInvocations`** | Invocations spilling to on-demand when provisioned capacity is full. | Spot spikes and spillover cold starts. |

Use **Maximum** for peak concurrency; `Sum(ConcurrentExecutions)` across periods does **not** mean “total invocations in the hour” like `Sum(Invocations)`.

### 3.5. Metric Dimensions and Time Windows

CloudWatch returns distinct time series for:

- **`FunctionName`:** overall function view across that dimension.
- **`Resource`:** function name paired with an alias or version qualifier.
- **`ExecutedVersion`:** the actual version that executed.

During a weighted-alias canary, inspecting only `FunctionName` can mask errors isolated to the **new version**. Split metrics by alias/version while comparing against overall traffic.

**Never blindly sum across multiple dimensions** as a single total: the same invocation can appear in multiple time series. Pick the right dimension and statistic before aggregating.

## 4. Choosing the Right Statistic: Sum, Average, Maximum, p95

CloudWatch metrics aggregate datapoints per period; picking the wrong statistic yields wrong conclusions.

| Question | Right metric/statistic | Avoid |
| --- | --- | --- |
| How many invocations ran in 5 minutes? | **`Invocations` — Sum**, 300 s period. | Using Average as total request count. |
| How many invocations threw exceptions in 5 minutes? | **`Errors` — Sum**, 300 s period. | Using Maximum as total errors. |
| Did the function hit peak concurrency? | **`ConcurrentExecutions` — Maximum**. | Summing concurrency samples. |
| What is p95 handler duration? | **`Duration` — p95** over the right window. | Looking only at Average and assuming no outliers. |
| Is a stream holding unprocessed records too long? | **`IteratorAge` — Maximum** or matching stat. | Watching only rising `Invocations`. |
| Is the Lambda async queue backing up? | **`AsyncEventAge` — Maximum/p95**, `AsyncEventsDropped`. | Assuming `Errors=0` means zero lag. |

### 4.1. Example: Average Hides Tail Latency

A function runs 100 invocations:

- 95 invocations take **100 ms**.
- 5 invocations take **5,000 ms**.

Average duration is roughly:

\[
\frac{95\times100+5\times5000}{100}=345 \text{ ms}
\]

Some users still wait **5 seconds** even though the average looks like 345 ms. **p95/p99 and Maximum** expose tail-latency pain far better.

Watch out: **p95 `Duration`** measures handler execution, not end-to-end API latency. If API Gateway, networking, or init adds delay, add request-level metrics and traces.

### 4.2. Missing Data Does Not Equal Zero

When Lambda receives no invocations, certain metrics emit zero datapoints in that interval. Alarms must configure **missing data treatment** intentionally:

- For error rate on a rarely invoked function, Missing is normal.
- For a job that must run every minute, **zero `Invocations`** signals an outage.
- For provisioned utilization, zero traffic may omit datapoints rather than proving zero capacity is allocated.

Never equate missing data with healthy state; configure treatment around your **workload's SLO**.

## 5. CloudWatch Logs: From `REPORT` to Application Logs

Lambda sends logs to **Amazon CloudWatch Logs** as configured. The default log group for a traditional Event Function is typically:

~~~text
/aws/lambda/<function-name>
~~~

This is an illustrative naming pattern; Lambda supports custom log groups and additional log destinations per current features.

### 5.1. `START`, `END`, `REPORT`

In text logs, each invocation typically prints:

- **`START`:** request ID and executed version.
- **`END`:** completion of invocation.
- **`REPORT`:** Duration, Billed Duration, Memory Size, Max Memory Used, and additional platform fields.

**JSON-formatted** logs emit structured events rather than necessarily printing those exact three text lines. If log-level filtering is enabled, some system log events may be filtered out per level.

**`RequestId`** is a critical correlation key. Include it in key application log steps to trace a single invocation, while keeping PII and access tokens out of logs.

### 5.2. Structured Application Logging

Instead of:

~~~text
Got error. Try again.
~~~

emit logs rich enough for operations, such as:

~~~json
{
  "timestamp": "2026-11-20T03:15:00Z",
  "level": "ERROR",
  "service": "invoice-worker",
  "operation": "process-invoice",
  "awsRequestId": "example-request-123",
  "correlationId": "example-correlation-456",
  "errorType": "DatabaseTimeout",
  "durationMs": 3200,
  "attempt": 2
}
~~~

**This is an illustrative JSON application log.** With the managed Java runtime, AWS supports structured logging for **`LambdaLogger`** or **Log4j2** under supported setups, configurable via Lambda `LoggingConfig` (`JSON` format). Simply printing a JSON string from an arbitrary logging library won't always make Lambda parse severity levels automatically; verify your runtime and logger integration.

Ensure you:

- Propagate **Correlation IDs** across API Gateway/SQS/EventBridge whenever possible.
- Log **event type** and approved business IDs — never raw payloads containing PII.
- Never log authorization headers, cookies, access keys, passwords, Secrets Manager responses, or full customer records.
- On error, log controlled **error type/stack traces** without duplicating identical stack dumps across layers.
- Maintain a **consistent log schema** so queries are easy and per-request log volume does not explode into hundreds of KB.

### 5.3. Advanced Logging Controls

Lambda supports configuration fields such as:

~~~json
{
  "LoggingConfig": {
    "LogFormat": "JSON",
    "ApplicationLogLevel": "INFO",
    "SystemLogLevel": "INFO",
    "LogGroup": "/aws/lambda/invoice-worker"
  }
}
~~~

This is an **illustrative config snippet** from the Lambda API, not a full `CreateFunction` payload.

- **`LogFormat`:** `JSON` or `Text`.
- **`ApplicationLogLevel`:** `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`, `FATAL` per supported logger/runtime.
- **`SystemLogLevel`:** `DEBUG`, `INFO`, `WARN`.
- **`LogGroup`:** target log group per configuration.

Lowering log level from `DEBUG` to `INFO`/`WARN` trims log volume and CloudWatch spend, yet **never silence critical error or audit logs** just to cut bills. Enable `DEBUG` temporarily under controlled access during investigations, then revert.

### 5.4. Log Retention and Permissions

CloudWatch Logs charges for ingestion, storage, and queries per active pricing. Without a retention policy, log groups can retain data far longer than needed.

Sample retention policy:

| Environment | Reference retention | Conditions |
| --- | --- | --- |
| Dev/sandbox | 7–14 days. | Short-term debugging only; verify company policy. |
| Staging | 14–30 days. | Supports regression and deployment triage. |
| Production | 30–90 days or per policy. | Meets compliance, audit, and forensic needs. |
| Long-term mandatory audit | Dedicated archive/retention store. | Enforce access control, encryption, and immutability where required. |

These are **policy examples**, not AWS defaults or legal advice. Data owners, legal, and security teams must approve retention windows.

Separate IAM permissions:

- Runtime role writing logs: **`logs:CreateLogStream`**, **`logs:PutLogEvents`**, and matching permissions; log groups can be pre-created via IaC.
- Dev/support reading logs: **`logs:DescribeLogGroups`**, **`logs:FilterLogEvents`**, **`logs:StartQuery`**, **`logs:GetQueryResults`** scoped to approved groups.
- Admin altering retention/log destinations: separate privileged role with review.

Never grant **`logs:*`** across every log group just so one handler can log.

## 6. CloudWatch Logs Insights: Investigating Requests, Errors, and Duration

CloudWatch Logs Insights queries log data across chosen time ranges. Narrow **Region, log groups, time window**, and fields to avoid scanning huge volumes unnecessarily.

### 6.1. Find Recent Errors

~~~text
fields @timestamp, @message, @logStream
| filter @message like /ERROR|Exception|Task timed out/
| sort @timestamp desc
| limit 50
~~~

Queries depend on log format; with JSON structured logs, filter on parsed fields like **`level`**, **`errorType`**, and **`awsRequestId`** when emitted by your schema.

### 6.2. Analyze Execution Time from `REPORT` (Text Format)

~~~text
filter @type = "REPORT"
| stats count(*) as requests,
        avg(@duration) as avgDurationMs,
        pct(@duration, 95) as p95DurationMs,
        max(@duration) as maxDurationMs,
        max(@maxMemoryUsed / 1024 / 1024) as peakMemoryMB
  by bin(5m)
| sort bin(5m) desc
~~~

This is a **sample Logs Insights query** using fields auto-discovered by Logs Insights in matching Lambda system log formats. Verify active field discovery and your function's log format; if fields are missing, adapt to JSON fields or regex parsing.

Do not confuse **`@duration`** with **`@billedDuration`**, nor `Max Memory Used` with configured memory. Lambda bills on **configured memory** and **billed duration**, not peak memory used.

### 6.3. Search by `requestId`

~~~text
fields @timestamp, @message, @requestId
| filter @requestId = "example-request-123"
| sort @timestamp asc
| limit 100
~~~

If your application logs **`awsRequestId`** inside JSON, the field name may differ from Logs Insights' **`@requestId`**. Confirm actual discovered fields in the target log group before relying on a query in production.

### 6.4. Metric Filters and Custom Alarms

You can use **CloudWatch Logs metric filters** or **Embedded Metric Format (EMF)** to turn application log events into custom metrics.

For example, a business metric **`InvoicesProcessed`** tracks successfully completed invoices — distinct from **`Lambda Invocations`**. Keep in mind metric filters and EMF incur CloudWatch custom metric and log ingestion charges.

Strictly avoid **high-cardinality dimensions** like `requestId`, `userId`, or `orderId`: every distinct dimension value spawns a new metric time series, inflating bills and cluttering dashboards.

## 7. AWS X-Ray, Lambda Insights, and Telemetry Layers

### 7.1. AWS X-Ray: Analyzing Request Paths

X-Ray provides distributed tracing showing every leg a request traverses, e.g.:

~~~mermaid
flowchart LR
    API["API Gateway"] --> L["Lambda invoice-api"]
    L --> DDB[("DynamoDB")]
    L --> EXT["External payment API"]
    API -.->|"Trace context"| XR["X-Ray"]
    L -.-> XR
    DDB -.-> XR
    EXT -.-> XR
~~~

- **Active tracing** tells Lambda to sample and emit traces to X-Ray where supported.
- **PassThrough** forwards trace context from supported upstream integrations instead of initiating active sampling itself.
- Lambda tracing requires execution role permissions to emit traces (e.g., **`AWSXRayDaemonWriteAccess`** or equivalent scoped policy).
- Add SDK instrumentation or **OpenTelemetry** to trace database queries, AWS SDK calls, and custom code spans in depth.
- **Sampling** means not every single invocation gets a trace; never treat tracing as a complete audit log of every request.

If an API takes 500 ms end-to-end while Lambda handler `Duration` is only 120 ms, traces reveal the split across **API Gateway integration, cold initialization, SDK calls, and downstream latency** when properly instrumented.

### 7.2. Lambda Insights: Runtime and Resource Telemetry

**CloudWatch Lambda Insights** adds execution-environment diagnostics covering **memory, CPU time, disk, network, and cold starts** where supported.

AWS distributes an extension/layer for supported runtimes; enabling it emits extra metrics and performance log events. While valuable for deep triage, it increases:

- Log ingestion and storage.
- CloudWatch custom metric charges.
- Extension overhead that can affect duration and billed time.

Enable Lambda Insights selectively on workloads or windows needing deep resource visibility, watch its cost, and avoid blindly turning on every extension across every function.

### 7.3. CloudWatch Application Signals, Telemetry API, and Powertools

Additional options:

- **CloudWatch Application Signals:** application/service/SLO observability where supported.
- **Lambda Telemetry API:** lets extensions subscribe directly to lifecycle, platform, function log, and trace streams.
- **Powertools for AWS Lambda (Java/Python/TypeScript/.NET):** practical utilities for logging, tracing, metrics, idempotency, and batch processing.
- **OpenTelemetry / ADOT:** cross-service instrumentation exporting traces and metrics via supported collectors.

Do not turn on every tool at once. Each extension or library adds **operational overhead, maintenance, IAM surface, and cost**. Start with solid SLI/SLO coverage and layer deeper telemetry during real investigations.

## 8. Three Invocation Mechanisms and How Observability Differs

Lambda receives events under distinct invocation models. Diagnosing retries or costs fails if you mix them up.

| Type | Who invokes Lambda? | Error/retry behavior | Key signals |
| --- | --- | --- | --- |
| **Synchronous** | API Gateway, ALB, Invoke API `RequestResponse`. | Caller receives response/error directly and decides retries. | End-to-end latency, Lambda `Errors`, API 4xx/5xx, throttles. |
| **Asynchronous** | S3, SNS, EventBridge, or Invoke API `Event`. | Lambda internal queue retries per async rules; supports DLQ/destinations. | `AsyncEventsReceived`, `AsyncEventAge`, `AsyncEventsDropped`, destination failures. |
| **Event source mapping (ESM)** | Lambda polls SQS, DynamoDB Streams, Kinesis, MSK/Kafka, etc. | Retries, batches, visibility/iterator behavior depend on source. | SQS backlog, `IteratorAge`, ESM metrics, partial batch failures, mapping state. |

### 8.1. Synchronous: Handler Succeeds Yet API Fails

Suppose a Java handler catches an exception and returns:

~~~json
{
  "statusCode": 500,
  "body": "{\"error\":\"database unavailable\"}"
}
~~~

At the Lambda runtime layer, the invocation **succeeded** because the handler returned a normal object. **`Errors` stays 0**, even though API Gateway/ALB returns HTTP 500 to the client.

**Conclusion:** track **business/API errors** separately from **Lambda runtime execution errors**. Never measure API availability solely by Lambda `Errors`.

### 8.2. Asynchronous: Event Accepted Does Not Mean Executed

With async invocations, Lambda:

1. Accepts the event into its internal queue.
2. Waits for execution capacity.
3. Invokes the handler.
4. Retries on handler errors or throttles/system errors.
5. Sends failed records to a configured destination/DLQ if eligible, or drops them once retries/age expire.

Default retry behavior depends on error class. Per AWS docs, **function errors** in async mode default to up to **two retries**; for **throttling/system errors**, Lambda uses backoff and retries until the event exceeds max age (default up to six hours depending on settings).

Metrics to watch:

- **`AsyncEventsReceived`**: events successfully queued by Lambda.
- **`AsyncEventAge`**: queue wait time before handler invocation.
- **`AsyncEventsDropped`**: events discarded without succeeding.
- **`DestinationDeliveryFailures`/`DeadLetterErrors`**: failures delivering failure records themselves.

**Never expect `AsyncEventsReceived` to equal `Invocations` in the exact same minute.** Queue delays, retries, and dropped events create divergence.

### 8.3. Event Source Mapping from SQS

~~~mermaid
flowchart LR
    P["Producer"] --> Q["SQS Standard"]
    Q -->|"Lambda poller fetches batch"| L["Lambda worker"]
    L -->|"Write output"| S3[("S3/DynamoDB")]
    Q -.->|"Redrive after retry threshold"| DLQ["SQS DLQ"]
    Q --> M["ApproximateAgeOfOldestMessage"]
    L --> CW["Errors, Duration, concurrency"]
~~~

For SQS:

- Lambda polls the queue and invokes the handler **synchronously with a batch** — it is **not** Lambda's internal async queue like S3 → Lambda.
- **One Invocation can carry many SQS messages**.
- Duplicate processing can occur due to **at-least-once** delivery semantics.
- Throwing an unhandled exception for the whole batch can reprocess already-succeeded messages once visibility expires.
- Enable **`ReportBatchItemFailures`** to fail individual messages without retrying the whole batch.
- With SQS FIFO, stop at the first error and return both failed and unprocessed subsequent messages in that group to preserve order.

Alongside `AWS/Lambda` metrics, watch:

| SQS metric | Meaning |
| --- | --- |
| **`ApproximateNumberOfMessagesVisible`** | Messages currently available to receive. |
| **`ApproximateNumberOfMessagesNotVisible`** | Messages in-flight / hidden during visibility timeout. |
| **`ApproximateAgeOfOldestMessage`** | Wait age of the oldest message per SQS semantics. |
| **`NumberOfMessagesSent` / `Received` / `Deleted`** | Enqueue, poll, and delete rates; not identical to unique business jobs. |
| **DLQ visible/age** | Failed work awaiting triage and replay. |

A Lambda worker showing **`Errors = 0`** while queue age climbs may be **starved for concurrency, using a disabled/broken ESM, failing to receive messages, or running too slowly**.

### 8.4. Stream Event Sources

For DynamoDB Streams and Kinesis, Lambda processes batches per shard under specific semantics:

- Rising **`IteratorAge`** warns that the consumer is falling behind the producer.
- Retrying a failing batch can stall shard progress depending on error policies.
- Partial batch, batch bisection, max record age, max retries, and on-failure destinations vary by source and config.
- Raising concurrency does not always raise throughput when **shards, parallelization factor, or downstream capacity** are the true bottleneck.

Never treat **SQS queue age** and **Kinesis `IteratorAge`** as interchangeable metrics across all situations.

## 9. Concurrency, Throttling, and Downstream Limits

### 9.1. Concurrency from Request Rate and Duration

Common estimation formula:

\[
\text{Average concurrent executions}
\approx
\text{Requests per second}
\times
\text{Average duration (seconds)}
\]

For example, an API at **120 requests/second** averaging **0.4 seconds**:

\[
120\times0.4=48
\]

Average concurrency sits around **48** under steady load without bursts or overhead. Real peaks run higher due to spikes, retries, cold starts, tail latency, and duration variance.

This is an **estimate**, not an API telling you exact environment reservations. Also check **`Maximum ConcurrentExecutions`** and Lambda's Regional scaling rates.

### 9.2. Reserved Concurrency

**Reserved concurrency** serves two purposes:

- Sets aside dedicated concurrency from the account quota for a critical function.
- Caps maximum concurrency so the function cannot run away and overwhelm downstream services.

If Function A has reserved concurrency **50**, once 50 invocations run simultaneously, additional calls are **throttled** per invocation mode. Those 50 units stay reserved for A even while idle, reducing the shared pool for other functions.

**Reserved concurrency carries no separate capacity charge**, yet setting it too low can increase throttles, retries, and availability impact.

**`Reserved concurrency = 0`** can intentionally pause invocations operationally, though for async/SQS/event streams you must still account for **retries, backlogs, event age, and drops** — never treat it as a zero-consequence pause button.

### 9.3. Provisioned Concurrency

**Provisioned concurrency** keeps pre-initialized execution environments ready for a **published version or alias** where supported.

Benefit: cuts cold starts for latency-sensitive workloads.

Trade-offs:

- Incurs **provisioned concurrency charges for the entire duration provisioned**, even when traffic is low.
- Compute/invocation rates under provisioned concurrency follow a distinct pricing schedule; check current pricing docs.
- Traffic above provisioned capacity can **spill over** to on-demand within remaining concurrency limits, hitting cold starts there.
- Requires managing account quotas, reserved concurrency, alias/version deploys, and allocation lead time.

Enable it only when **end-to-end p95/p99 latency** proves cold starts are the bottleneck and the business gain outweighs idle capacity cost.

### 9.4. Concurrency as a Database Safeguard

Suppose each Lambda invocation opens one DB connection, and RDS tolerates at most 100 connections for this workload. Letting Lambda scale to 1,000 concurrent invocations will crush the database even while Lambda scales effortlessly.

Mitigations:

- Set appropriate reserved concurrency / ESM maximum concurrency.
- Safely reuse DB connections across warm invocations.
- Use **RDS Proxy** or suitable pooling for RDS.
- Add backpressure via SQS/batching and idempotent retries.
- Monitor **`DatabaseConnections`**, throttling, latency, failovers, and transaction duration.

Never react to every timeout by raising reserved concurrency: that often piles extra pressure onto an already overloaded dependency.

## 10. Designing Operational Dashboards and Alerts

A Lambda dashboard can be organized into four areas:

~~~mermaid
flowchart TB
    SLO["SLO / Business health"] --> D["Lambda Dashboard"]
    R["Requests, Errors, Throttles"] --> D
    P["Duration p95/p99, ConcurrentExecutions"] --> D
    Q["AsyncEventAge / SQS age / IteratorAge"] --> D
    C["GB-s, requests, logs, Cost Explorer"] --> D
    D --> AL["CloudWatch Alarms / SNS / incident workflow"]
~~~

### 10.1. Reference Alert Matrix

| Signal | Example threshold | Priority | What to investigate |
| --- | --- | --- | --- |
| Lambda Errors ratio | Above **1%** for several minutes with sufficient traffic. | High. | Exceptions, timeouts, recent version. |
| Lambda Throttles | `Sum > 0` repeatedly on critical APIs. | High. | Account/reserved limits, spikes, caller retries. |
| Duration p95 | Exceeds **80% of timeout** or latency SLO persistently. | High/medium. | Cold starts, SDK/DB/network calls, memory. |
| `ConcurrentExecutions` | Near **80–90% of cap** for sustained windows. | Medium/high. | Headroom, bursts, quotas, downstream load. |
| `AsyncEventsDropped` | Any value **> 0** when events are mandatory. | Critical. | Retries/age, destination config, replay path. |
| `DeadLetterErrors` / `DestinationDeliveryFailures` | Any value **> 0**. | High. | Resource/KMS permissions, target availability. |
| SQS `ApproximateAgeOfOldestMessage` | **> 3 minutes** when queue SLO is 2 minutes. | High. | Worker backlog, throttles, consumer failures. |
| DynamoDB/Kinesis `IteratorAge` | Continuously climbing past allowed lag. | High. | Shards, consumer retries, batch size. |
| Monthly cost forecast | Projected to exceed budget. | Finance/ops. | Traffic growth, retries, logs, provisioned capacity. |

**Thresholds are illustrative.** On a function running only a few times a day, one error spikes error rate to 100%; pair ratios with **minimum sample counts**, CloudWatch metric math, or absolute `Errors` counts.

### 10.2. Alarms Alone Are Not an Incident Strategy

Every good alarm specifies:

1. **Owner:** responsible team and notification channel.
2. **Impact:** which users or workflows degrade.
3. **Runbook:** exact CLI/Console/metrics checks and safe rollback path.
4. **Severity:** separates informational warnings from urgent pages.
5. **Missing data handling:** aligned with steady vs. sporadic workloads.
6. **Tuning:** reviewed post-incident to eliminate false positives.

AWS Budgets and Cost Anomaly Detection alert on spend; **a budget alert is not a hard spending cap** blocking AWS charges by default. Strict spend caps require explicit quotas, IAM guardrails, concurrency limits, and cleanup automation.

## 11. Observing Java Lambda: Handler and Correlated Logging Example

Because this module covers AWS with Java applications, the example below uses the **AWS Lambda Java runtime** with **`RequestHandler`** from **`aws-lambda-java-core`**.

### 11.1. Illustrative Java Handler

~~~java
package com.example.lambda;

import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import java.util.Map;

public class InvoiceHandler
        implements RequestHandler<Map<String, Object>, Map<String, Object>> {

    @Override
    public Map<String, Object> handleRequest(
            Map<String, Object> event, Context context) {

        String requestId = context.getAwsRequestId();
        long started = System.nanoTime();

        try {
            Object value = (event == null) ? null : event.get("invoiceId");
            if (!(value instanceof String invoiceId) || invoiceId.isBlank()) {
                throw new IllegalArgumentException("invoiceId is required");
            }

            // Never log full payloads or sensitive data.
            context.getLogger().log(
                "operation=invoice.validate status=started requestId=" + requestId
            );

            // TODO: Delegate real business logic to an idempotent service.
            // TODO: Reuse AWS SDK clients with proper timeouts and retries.
            context.getLogger().log(
                "operation=invoice.validate status=completed requestId=" + requestId
            );

            return Map.of("status", "accepted");
        } catch (RuntimeException ex) {
            context.getLogger().log(
                "operation=invoice.validate status=failed requestId=" + requestId
                    + " errorType=" + ex.getClass().getSimpleName()
            );
            throw ex; // Ensure Lambda Errors reflects failed invocations.
        } finally {
            long durationMs =
                (System.nanoTime() - started) / 1_000_000L;
            context.getLogger().log(
                "operation=invoice.validate elapsedMs=" + durationMs
                    + " requestId=" + requestId
            );
        }
    }
}
~~~

**Note:** This is an observability illustration, **not a production-ready invoice processor**. For a real project, declare a compatible version of **`aws-lambda-java-core`**, package the JAR/ZIP properly, write unit tests, configure IAM, validate inputs, and implement idempotency.

Key practices in the code:

- Uses **`Context.getAwsRequestId()`** for correlation.
- Avoids logging raw events that could hold customer PII.
- Rethrows runtime exceptions so **`Errors`** accurately tracks failed executions.
- Logs **internal method timing** for debugging without treating it as a substitute for CloudWatch `Duration`/`Billed Duration`.
- For JSON structured logging, pick compatible `LambdaLogger`/Log4j2 + `LoggingConfig` — never assume plain `key=value` text becomes JSON automatically just because Lambda has a log group.

### 11.2. Protecting Logs from Injection and High Cardinality

When logging business identifiers, never concatenate unsanitized user strings straight into log lines, as newlines or special characters can forge log entries or break queries. Use structured loggers with proper encoding/sanitization, and verify which identifiers privacy policies allow logging.

Never add **`invoiceId`** as a CloudWatch metric dimension. Error rates by environment/version/service belong in metrics; individual IDs belong in **access-controlled logs and traces**.

### 11.3. Custom Business Metrics with Embedded Metric Format

Example EMF log event emitting two metrics:

~~~json
{
  "_aws": {
    "Timestamp": 1795144500000,
    "CloudWatchMetrics": [
      {
        "Namespace": "Shop/Invoices",
        "Dimensions": [["Service", "Environment"]],
        "Metrics": [
          {"Name": "InvoicesCompleted", "Unit": "Count"},
          {"Name": "ProcessingLatency", "Unit": "Milliseconds"}
        ]
      }
    ]
  },
  "Service": "invoice-worker",
  "Environment": "prod",
  "InvoicesCompleted": 1,
  "ProcessingLatency": 186
}
~~~

CloudWatch EMF extracts custom metrics asynchronously from validly formatted logs. The **`Timestamp`** above is illustrative, not a live timestamp. EMF incurs both log ingestion and custom metric charges — never emit a new metric time series per invoice ID.

In production Java services, consider **Powertools for AWS Lambda Java Metrics** to emit standardized EMF events cleanly instead of hand-rolling formatters in every handler.

## 12. Lambda Event Functions Cost Model

For **on-demand Lambda Event Functions**, core cost drivers are:

1. **Request charges:** billed by eligible invocations/request units per pricing schedule (large async payloads can consume multiple request units per pricing rules).
2. **Compute duration:** based on **configured memory**, **billed duration**, architecture, and applicable **GB-second** pricing per Region/tier.
3. **Provisioned Concurrency:** charges for maintaining pre-initialized capacity plus compute/request rates if enabled.
4. **Extra ephemeral storage:** configured `/tmp` capacity above the free baseline tier.
5. **Additional features:** SnapStart pricing/rules vary by runtime; tenant isolation or specialized Lambda modes carry their own pricing.
6. **Integrated services:** CloudWatch Logs/metrics/queries, X-Ray, API Gateway, SQS, EventBridge, S3, RDS, KMS, NAT, data transfer, and storage.

**Important:** AWS offers multiple Lambda compute primitives with distinct billing rules. Never apply the formula below to **Lambda Managed Instances, MicroVMs, Web Functions, or specialized modes** without verifying their pricing tables.

### 12.1. GB-Seconds Estimation Formula

For an on-demand Event Function, excluding discounts and exceptions:

\[
\text{GB-seconds}
=
N_{\text{invocations}}
\times
\frac{\text{memory configured (MB)}}{1024}
\times
\text{billed duration (seconds)}
\]

And:

\[
\text{Compute charge}
\approx
\text{GB-seconds}\times\text{Price per GB-second}
\]

Estimated total cost:

\[
C_{\text{total}}
\approx C_{\text{requests}}
+C_{\text{compute}}
+C_{\text{provisioned}}
+C_{\text{extra tmp}}
+C_{\text{observability}}
+C_{\text{downstream/network}}
\]

Real billing incorporates **AWS Free Tier, Region, architecture, pricing tiers, credits, Savings Plans, duration rounding, and provisioned concurrency rules** per active pricing. Use this formula to compare optimization options, not to replace your AWS invoice.

### 12.2. Comparing Three Memory Configurations

Suppose Lambda runs **1,000,000 invocations** per month and benchmark runs show:

| Config | Memory | Average billed duration | GB-s per 1M invocations |
| --- | ---: | ---: | ---: |
| A | 512 MB | 400 ms | **200,000 GB-s** |
| B | 1,024 MB | 190 ms | **190,000 GB-s** |
| C | 2,048 MB | 120 ms | **240,000 GB-s** |

Calculation:

- A: `1,000,000 × 0.5 GB × 0.4 s` = **200,000 GB-s**.
- B: `1,000,000 × 1 GB × 0.19 s` = **190,000 GB-s**.
- C: `1,000,000 × 2 GB × 0.12 s` = **240,000 GB-s**.

Config B runs faster than A and consumes **fewer compute GB-seconds** than A. Config C is fastest yet burns more GB-seconds than B. Therefore raising memory is **not always pricier**, and cutting memory is **not always cheaper**.

These numbers are **hypothetical** for instruction, not AWS benchmarks. In real tuning, always measure **`Billed Duration`** (not just `Duration`) across representative samples with consistent payloads, cold-start ratios, and CPU architecture.

### 12.3. Request Counts Can Differ from “Business Events”

One batched message can carry 100 business items in one invocation, or one item can retry multiple times across separate invocations. Never assume:

~~~text
1 order = 1 AWS Lambda request = 1 billed execution
~~~

Depending on the source:

- **Synchronous API:** one HTTP call typically triggers one invocation, yet retries, authorizers, and downstream Lambdas multiply the count.
- **Async events:** request unit counts can scale with payload size and retries.
- **SQS event source mapping:** one invocation processes a batch of multiple SQS messages.
- **Fan-out:** one event triggering three functions creates three separate compute streams.

Track financial efficiency with **cost per successful business outcome**, such as cost per 1,000 images processed successfully.

### 12.4. Free Tier and Credits

AWS Lambda Event Functions include an AWS-published Free Tier of monthly requests and GB-seconds under current terms. Keep in mind:

- Free Tier has scope conditions and can be shared across an AWS Organization/account.
- Never assume every compute mode, provisioned concurrency tier, or add-on is covered like on-demand.
- Rates and policies vary by Region, architecture, time, account, and credit programs.

In practice, verify numbers with **AWS Pricing Calculator** and **AWS Cost Explorer / Cost and Usage Report (CUR)** instead of hardcoding global USD/million-request rates.

## 13. Optimizing Memory, CPU, and Duration

### 13.1. Memory Also Controls CPU

Lambda allocates **CPU power proportionally to configured memory** within supported limits. Memory configuration governs both RAM headroom and compute speed.

Example for a Java function:

- 128 MB: slow JVM startup; CPU-bound code drags or hits OOM.
- 512 MB: sufficient RAM and more CPU; `Duration` drops.
- 1,024 MB or higher: `Duration` may drop further, though marginal returns must be measured.
- Too high: duration stops falling because the function blocks on DB/network I/O, inflating GB-seconds.

Pick memory along the **cost-performance frontier**, rather than blindly picking the minimum tier.

### 13.2. Memory Tuning Experiment

Recommended steps:

1. Hold **application version**, handler logic, and representative dataset constant.
2. Benchmark tiers such as **256, 512, 1,024, 2,048 MB** where the workload runs cleanly.
3. Send equal request volumes per tier, separating cold and warm invocations where possible.
4. Record **`Billed Duration`, `Duration` p50/p95/p99, `Max Memory Used`, error rate, and concurrency**.
5. Compute **GB-seconds** and estimate request + compute spend in a comparison table.
6. Choose the config meeting **latency SLOs and stability** at the lowest valid cost.
7. Re-benchmark whenever Java/runtime/library versions, ARM architecture, or workload shapes change.

**AWS Lambda Power Tuning** uses Step Functions to test multiple memory tiers automatically; remember it **actually invokes your function** and can trigger side effects and charges. Never run it on non-idempotent handlers without sandbox isolation.

### 13.3. Optimizing Java Initialization and SDK Calls

Key opportunities in Java Lambda:

- **Initialize AWS SDK clients once** outside the handler to reuse across warm invocations.
- Set sensible **HTTP connect/read timeouts** and bounded retries/backoff so slow dependencies don't consume the entire duration budget.
- Keep dependency injection and framework bootstrapping minimal; strip unused modules.
- Avoid re-downloading large configs/models from S3 on every invocation when safe caching works.
- Optimize JSON serialization, redundant network calls, DNS lookups, and database queries.
- Eliminate unnecessary AWS API calls, as each call adds both latency and API fees.
- Manage connection keep-alive, credential refreshes, and expiry so reused environments never hold stale connections or expired secrets forever.

**Caches are optimizations, never durable storage.** Execution environments can disappear anytime; code must recover cleanly on cache misses or expiry.

### 13.4. Timeout Is a Latency Boundary, Not the Only Tuning Knob

Too short a timeout spikes **`Errors`** by aborting healthy work. Too long a timeout lets stuck dependencies burn compute dollars for minutes.

Sound timeout design:

- Base it on p99 of valid business work plus deliberate headroom.
- Keep HTTP, SDK, and DB query timeouts **shorter than the Lambda timeout** so the handler can handle errors and clean up.
- For SQS workers, coordinate Lambda timeout, **SQS visibility timeout**, and retries.
- For user-facing APIs, end-to-end timeouts are also bounded by **API Gateway/ALB/client limits**.

Never keep bumping timeouts without diagnosing why calls are slow.

## 14. Cold Starts, SnapStart, and Provisioned Concurrency

### 14.1. Diagnose Cold Starts with Evidence

A slow request can stem from:

- Java runtime INIT, class loading, or dependency initialization.
- VPC/network setup or establishing downstream connections.
- CPU-bound handler work or insufficient memory.
- API Gateway/ALB/client path latency.
- RDS locks/queries or slow external APIs.
- Extension, instrumentation, or logging overhead.

If handler `Duration` is low while end-to-end p95/p99 is high, inspect **`Init Duration`**, X-Ray traces, proxy/API metrics, and SDK spans before buying Provisioned Concurrency.

### 14.2. AWS Lambda SnapStart

**SnapStart** optimizes initialization by booting the function at version publish time, saving an encrypted snapshot of the initialized environment, and restoring snapshots to cut startup latency. Availability depends on runtime, package format, Region, and AWS limits.

For Java:

- Supported on designated **Java managed runtimes** under service conditions.
- Applies only to eligible **published versions/aliases**, not **`$LATEST`**.
- Snapshots preserve Init-time state; you must ensure **uniqueness**, PRNG safety, fresh temporary credentials, connection validation, timestamps, and external connections are handled safely after restore.
- Never assume **every layer, EFS, large `/tmp`, architecture, or container image** is compatible; check current feature docs.

On supported runtimes and ZIP packages, SnapStart cuts cold starts without paying to keep idle execution environments running continuously like Provisioned Concurrency.

### 14.3. SnapStart Pricing and Limits

Per AWS documentation, **SnapStart pricing** differs by runtime — Java managed runtimes have different fee rules compared to other runtimes. Never assume SnapStart is free across every runtime or equivalent to Provisioned Concurrency pricing.

Published feature constraints to remember:

- Cannot enable **SnapStart and Provisioned Concurrency simultaneously** on the same function version.
- Does not support **EFS** or **ephemeral storage above 512 MB** within SnapStart constraints per service rules.
- Differs across ZIP vs. container image packages; read current platform docs.
- Design and test **`beforeCheckpoint`/`afterRestore` hooks** when state needs refreshing after restore.

**Never use a snapshot to persist session or user state across invocations.**

### 14.4. When Does Provisioned Concurrency Make Sense?

A Java API with strict low p99 SLOs and predictable traffic can benefit from provisioned concurrency:

1. Prove cold starts cause the tail latency.
2. Size provisioned capacity from concurrent demand and real utilization.
3. Separate staging and production using **aliases/versions**.
4. Use scheduled or target-tracking auto scaling where supported.
5. Monitor end-to-end p99, **`ProvisionedConcurrencyUtilization`**, **`SpilloverInvocations`**, and cost.
6. Scale down idle capacity off-hours if SLAs allow.

For batch ETL or async workers insensitive to a few hundred milliseconds of cold start, Provisioned Concurrency is rarely cost-justified.

## 15. Ephemeral Storage, Networking, and Auxiliary Costs

### 15.1. Lambda `/tmp`

Lambda provides `/tmp` scratch space inside each execution environment, encrypted at rest by the platform. Standard Event Functions support configuring ephemeral storage from **512 MB to 10,240 MB** within quotas.

Use cases:

- Downloading large S3 images for processing.
- Extracting temporary files for ETL.
- Caching ML models/auxiliary data during an invocation.
- Generating PDFs/videos before uploading results to S3.

**Never store durable data in `/tmp`** or expect two execution environments to share files. Once an environment is reclaimed, temporary files vanish.

### 15.2. Billing for Extra `/tmp`

Configured ephemeral storage **above 512 MB** is billed per GB-second of additional allocated storage multiplied by billed duration per active pricing.

Example configuring `/tmp` to **2,048 MB**:

- Free baseline: 512 MB.
- Additional storage: **1,536 MB** = **1.5 GB**.
- At a 2-second billed duration under billing rules, illustrative extra storage usage is **3 GB-seconds** per invocation.

Billing uses **configured storage capacity**, not how many bytes of files actually sit in `/tmp`.

### 15.3. VPCs and NAT Gateways

A VPC-attached Lambda can reach private databases in private subnets. When calling other services, plan the network path:

- AWS SDK calls to **S3/DynamoDB/CloudWatch/Secrets Manager** require VPC endpoints or NAT depending on architecture.
- NAT Gateways charge hourly plus per-GB data processing; heavy S3/API traffic through NAT can cost far more than Lambda compute itself.
- VPC Interface Endpoints charge per endpoint-hour and GB processed by service/Region — they are not free.
- Check security group egress, subnet routes, DNS resolution, KMS/secret access, and destination timeouts.

Never assume a VPC-attached Lambda gets **Internet egress automatically** just by choosing a subnet inside the VPC.

### 15.4. S3, RDS, API Gateway, and Data Transfer

A function invoked 1 million times might:

- Read 1 million S3 objects and write 1 million output objects.
- Emit millions of log events.
- Execute 1 million DynamoDB transactions.
- Open/close huge numbers of DB connections.
- Route requests through NAT to external APIs.

Combined auxiliary service spend often **exceeds Lambda compute charges**. Optimization must evaluate **whole-pipeline TCO**, not just shrinking `Billed Duration`.

### 15.5. CloudWatch Logs, X-Ray, and Extension Overhead

If a function logs 10 KB per invocation across 5 million invocations/month, raw ingestion hits roughly **50 GB** before overhead and retention. Leaving `DEBUG` enabled on full payloads explodes log bills and leaks sensitive data.

Controls:

- Use **structured logging**, concise messages, and appropriate severity levels.
- Never log huge event payloads or binary blobs.
- Log full stack traces only on real errors without duplicating across layers.
- Set intentional CloudWatch Logs retention policies.
- Scope Logs Insights queries tightly by time range and log group.
- Use X-Ray sampling and Lambda Insights deliberately where needed.
- Measure extension overhead and remove unused extensions.

**Never disable error logs and alarms completely to save money** — recovery and data-loss costs during an outage dwarf log savings.

## 16. Optimizing Event Flows to Lower Cost and Boost Resilience

### 16.1. Filter Unneeded Events Before Invocation

If every S3 upload triggers Lambda yet 80% of objects need no processing:

- Use S3 Event Notifications **prefix/suffix filters**.
- Or use EventBridge event patterns for richer filtering.
- For SQS/Kinesis/DynamoDB event source mappings, apply **event filtering** where supported by source and schema.

Filtering before invocation saves **Invocations, compute, logs, and downstream calls**. Because bad filters silently drop business events, test with sample payloads and watch metrics like **`FilteredOutEventCount`** where available.

### 16.2. Batch Size: Fewer Invocations Does Not Always Mean Lower Total Cost

Suppose SQS holds **10,000 messages**:

| Batch size | Theoretical Lambda invocations | Trade-off |
| --- | ---: | --- |
| 1 message/batch | 10,000 | High per-invocation overhead; easy per-message error isolation. |
| 10 messages/batch | 1,000 | Lower request overhead; one failure may retry the batch unless partial responses are enabled. |
| 100 messages/batch | 100 | Fewest invocations; higher duration/memory, timeout risk, and replay blast radius. |

Table shows **idealized estimates**; batching windows, payload sizes, available messages, and retries shift real counts. SQS also enforces batch size and payload limits.

**Cutting Lambda `Invocations`** helps, yet oversized batches that amplify retries, duplicate work, or queue dwell time can raise total cost and end-to-end latency.

### 16.3. Partial Batch Responses for SQS

When a batch contains messages A, B, and C — A and C succeed while B fails — use **`ReportBatchItemFailures`** on the ESM so only B retries.

Illustrative response:

~~~json
{
  "batchItemFailures": [
    {
      "itemIdentifier": "message-B-id"
    }
  ]
}
~~~

This response format is not for Lambdas invoked directly by S3. For FIFO queues, preserve ordering by stopping on error and returning all unprocessed subsequent messages in the group.

To control retry costs:

- Keep handlers **idempotent**.
- Set **SQS visibility timeout** comfortably above batch execution + retry time.
- Use DLQs and alerts to isolate poison messages.
- Distinguish transient errors (throttling) from permanent errors (bad schema).
- Never stack unbounded retries across **SDK, function code, SQS, and callers** simultaneously.

### 16.4. Cut Redundant Downstream Calls

Often bigger than memory tuning:

- Combine SDK calls into batch APIs where supported.
- Safely cache metadata across warm invocations or within a single invocation.
- Skip redundant **`HeadObject`** calls before **`GetObject`** when no precondition is needed.
- Replace racy read-then-write patterns with DynamoDB conditional writes and idempotency keys.
- Use S3 multipart or byte-range reads on large objects when only a slice is needed.
- Co-locate functions and datastores in the same Region to eliminate cross-Region latency and transfer fees.

**Never sacrifice correctness just to cut API calls**; batch operations must preserve error handling and transactional invariants.

## 17. Cost Analysis with Cost Explorer, CUR, and Tagging

### 17.1. Why Metrics Are Not the Final Bill

CloudWatch **`Invocations × Billed Duration × configured memory`** approximates compute usage, while actual AWS billing also reflects:

- **`x86_64` vs. `arm64`** architecture and pricing tiers.
- Free Tier/credits and account/organization consolidated billing.
- Provisioned Concurrency and add-on features.
- Async request unit rules for large payloads.
- Usage recording timestamps and rounding rules.
- Data transfer, NAT, log ingestion, X-Ray, KMS, API Gateway, and storage.

Never build a “to-the-cent” billing dashboard purely from `Duration`.

### 17.2. Financial Tools

| Tool | When to use | Notes |
| --- | --- | --- |
| **AWS Cost Explorer** | View spend by service, usage type, Region, time, and activated tags. | Aggregated data lags; not a real-time per-invoke alert. |
| **Cost and Usage Report (CUR) / Data Exports** | Deep usage/cost analysis via SQL/Athena/BI. | Requires storage, access controls, and query cost governance. |
| **AWS Budgets** | Track actual and forecasted spend with alerts. | Alerts do not hard-block spend by default. |
| **Cost Anomaly Detection** | Spot unusual spend spikes automatically. | Supplements, does not replace, baselines/SLOs and root-cause triage. |
| **AWS Pricing Calculator** | Estimate costs before deploying or migrating architectures. | Depends on assumptions; update with real measured usage. |
| **CloudWatch metrics/logs** | Pinpoint technical drivers behind rising spend. | Does not display exact discounts or full billing totals. |

### 17.3. Tagging and Cost Allocation

Suggested tags across related resources:

~~~text
Application = invoice-platform
Environment = prod
Team        = payments
CostCenter  = backend-services
Owner       = platform-team
~~~

Activate cost allocation tags in AWS Billing before expecting Cost Explorer/CUR to group spend by tag. Not every shared Lambda, CloudWatch, or NAT charge splits cleanly per function by tag alone; sometimes you need an **allocation model** backed by logs, metrics, and usage types.

### 17.4. Cost per Successful Outcome

Monthly example:

- Lambda compute + requests: hypothetical 30 currency units.
- API Gateway + SQS/S3 + Logs + KMS + NAT: hypothetical 70 units.
- Completed successfully: **100,000 invoices**.

Cost per 1,000 successful invoices:

\[
\frac{30+70}{100000}\times1000
=1\text{ currency unit}
\]

If 10,000 invoices fail and retry 4 times, total invocations jump without increasing completed invoices. **Cost per successful outcome** exposes inefficiency far better than unit cost per invocation.

Numbers above are **not AWS unit prices**. Real calculations must use exact service rates, currency conversions, discounts, overhead, and shared-cost allocation rules.

## 18. Security for Observability and Access Control

### 18.1. The Execution Role Is Not the Log-Viewer Role

| Principal | Typical required permissions | Should not be over-granted |
| --- | --- | --- |
| **Lambda execution role** | Write logs, access S3/DynamoDB/KMS for business logic, send X-Ray traces if enabled. | `AdministratorAccess` or access to all buckets. |
| **Developer read-only** | View function configs, CloudWatch metrics/logs, and traces for assigned apps. | `UpdateFunctionCode`/Configuration or reading production secrets. |
| **Deployment role** | Update functions, aliases, versions, and ESMs via IaC. | Account-wide IAM wildcards where scoping is possible. |
| **Finance/FinOps** | Cost Explorer/CUR and usage reports per policy. | Permissions to alter networking or production resources. |
| **Security/Audit** | CloudTrail, log retention policies, encryption, access reviews. | Uncontrolled modification/deletion of audit logs. |

The execution role lets running Lambda code **access AWS services**. Never conflate it with a developer's CloudWatch viewing permissions or a CI/CD deployment role.

### 18.2. PII, Secrets, and Sensitive Data

A common mistake is debug-printing:

- Full request bodies containing addresses, national IDs, or payment cards.
- `Authorization`/JWT headers and API tokens.
- Database connection strings with embedded passwords.
- Secrets Manager / SSM Parameter Store responses.
- Customer S3 object contents.

Those values flow into CloudWatch Logs, log subscriptions, archives, and SIEMs — dramatically expanding exposure and compliance risk.

Best practices:

1. Define a **log schema and data classification**.
2. Log only the minimal fields required for triage.
3. Mask or pseudonymize identifiers per policy.
4. Enforce tight IAM/KMS policies and bounded log retention.
5. Audit metric dimensions so user IDs never leak into metric names.
6. Audit read access to logs, traces, and billing data across the organization.

### 18.3. Permissions and Networking Impact Cost

When Lambda sits inside a VPC to reach RDS, VPC endpoints and NAT Gateways become both network prerequisites and cost lines. Never open full Internet egress for every function just to patch a timeout; identify exact required endpoints and configure matching egress rules, routes, SGs, and KMS policies.

If Lambda enters an invocation loop, triggers can rack up **massive bills and corrupt data** even with valid IAM permissions. Guard with prefix filters, idempotency, reserved concurrency caps, throttle/cost alarms, and controlled kill switches.

## 19. Read-Only AWS CLI: Inspecting Lambda and CloudWatch

The commands below **never create, deploy, invoke, modify, or delete resources**. Run with a read-only profile and replace function names, Regions, and ARNs with authorized lab resources. Avoid running mutating commands like `update-function-configuration`, `put-function-concurrency`, or `put-log-events` here.

### 19.1. Confirm Account and Region

~~~bash
aws sts get-caller-identity
aws configure get region
~~~

Always confirm the target account and Region before comparing CloudWatch metrics with billing; Lambda functions are Regional resources.

### 19.2. List and Inspect Function Configuration

~~~bash
aws lambda list-functions \
  --region ap-southeast-1 \
  --query "Functions[].{Name:FunctionName,Runtime:Runtime,MemoryMB:MemorySize,Timeout:Timeout,Updated:LastModified}"

aws lambda get-function-configuration \
  --function-name invoice-worker \
  --region ap-southeast-1 \
  --query "{Name:FunctionName,Runtime:Runtime,MemoryMB:MemorySize,TimeoutSec:Timeout,EphemeralMB:EphemeralStorage.Size,Architecture:Architectures,Tracing:TracingConfig,Logging:LoggingConfig,Role:Role,State:State}"
~~~

When investigating cost or performance, inspect **`MemorySize`, `Timeout`, `EphemeralStorage`, `Architectures`, `Layers`, `VpcConfig`, `TracingConfig`, `LoggingConfig`**, and which version/alias receives live traffic.

### 19.3. Inspect Concurrency

~~~bash
# Function reserved concurrency (if configured).
aws lambda get-function-concurrency \
  --function-name invoice-worker \
  --region ap-southeast-1

# Provisioned concurrency across aliases/versions.
aws lambda list-provisioned-concurrency-configs \
  --function-name invoice-worker \
  --region ap-southeast-1

# Regional Lambda account quotas and usage.
aws lambda get-account-settings \
  --region ap-southeast-1
~~~

If a function has no reserved concurrency configured, `get-function-concurrency` returns an object without a reserved count — never mistake “unset” for `Reserved = 0`. `Reserved = 0` is an explicit throttling setting.

### 19.4. Inspect Async Invoke Config and Event Source Mappings

~~~bash
# Async invoke configurations, if configured.
aws lambda get-function-event-invoke-config \
  --function-name invoice-worker \
  --region ap-southeast-1

# Triggers polled via event source mappings.
aws lambda list-event-source-mappings \
  --function-name invoice-worker \
  --region ap-southeast-1
~~~

If a function lacks async config or ESMs, these commands return empty or `ResourceNotFoundException`; note that direct **S3/SNS/EventBridge** push triggers do not appear in **`list-event-source-mappings`**.

For SQS ESMs, inspect **`BatchSize`, `MaximumBatchingWindowInSeconds`, `FunctionResponseTypes`, `ScalingConfig`, `State`, `FilterCriteria`**, and metrics config where applicable.

### 19.5. CloudWatch: `Invocations` and `Errors` Statistics

~~~bash
# Fixed UTC historical window example; replace with your investigation window.
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=invoice-worker \
  --start-time 2026-11-19T00:00:00Z \
  --end-time 2026-11-20T00:00:00Z \
  --period 3600 \
  --statistics Sum \
  --region ap-southeast-1

aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=invoice-worker \
  --start-time 2026-11-19T00:00:00Z \
  --end-time 2026-11-20T00:00:00Z \
  --period 3600 \
  --statistics Sum \
  --region ap-southeast-1
~~~

Notes:

- **`Sum`** for `Invocations`/`Errors` is a raw count, not an error rate.
- CLI datapoints are not guaranteed sorted chronologically; sort before analyzing.
- The UTC window **2026-11-19 to 2026-11-20** is illustrative; use your incident window.
- Empty datapoints warrant checking account/Region, `FunctionName`, dimensions, time window, and permissions — never assume the function is healthy.

### 19.6. CloudWatch: Inspect p95 `Duration`

~~~bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=invoice-worker \
  --start-time 2026-11-19T00:00:00Z \
  --end-time 2026-11-20T00:00:00Z \
  --period 300 \
  --extended-statistics p95 \
  --region ap-southeast-1
~~~

5-minute **p95 `Duration`** buckets are not equal to “whole-day p95.” Never average 5-minute p95 buckets and call it the daily p95; query raw distribution/histograms or wider period aggregations when needed.

### 19.7. CloudWatch Logs and Retention

~~~bash
aws logs describe-log-groups \
  --log-group-name-prefix "/aws/lambda/invoice-worker" \
  --region ap-southeast-1

aws logs filter-log-events \
  --log-group-name "/aws/lambda/invoice-worker" \
  --filter-pattern "ERROR" \
  --limit 20 \
  --region ap-southeast-1
~~~

Text filter pattern **`ERROR`** may miss specific JSON log schemas or events filtered at source; adjust filter syntax to your JSON fields/severity. When inspecting log groups, verify **`retentionInDays`**, encryption, `storedBytes`, and log destinations.

### 19.8. Inspect CloudWatch Alarms

~~~bash
aws cloudwatch describe-alarms \
  --alarm-name-prefix "invoice-worker" \
  --region ap-southeast-1
~~~

If an alarm shows **`INSUFFICIENT_DATA`**, inspect missing-data treatment and metric availability instead of assuming zero errors.

### 19.9. Financial Tooling

In AWS Cost Explorer:

- Compare identical **time windows** before and after optimizations.
- Group by Service, Usage Type, Region, and Cost Allocation Tags when available.
- Inspect **AWS Lambda** alongside CloudWatch, API Gateway, SQS, S3, NAT, and KMS.
- Review **Amortized, Unblended, and Net costs** as appropriate when discounts or credits apply.

Never grant Finance teams production mutation rights just to inspect billing. Remember billing updates lag behind technical CloudWatch telemetry.

## 20. Runbook for Triaging Errors and Cost Spikes

### 20.1. Decision Tree

~~~mermaid
flowchart TD
    START["Degraded SLO or rising Lambda cost"] --> Q{"Spike in Invocations?"}
    Q -->|"Yes"| A["Inspect traffic sources, retries, fan-out, loops"]
    Q -->|"No"| B{"Billed Duration / Memory / Provisioned rose?"}
    B -->|"Yes"| C["Diff versions, memory, init, SDK, DB, extensions"]
    B -->|"No"| D["Inspect Logs, X-Ray, NAT, S3, KMS, SQS, and auxiliary fees"]
    A --> E{"Errors / Throttles / EventAge rose?"}
    E -->|"Yes"| F["Separate async vs. SQS vs. sync, DLQ/retries"]
    E -->|"No"| G["Verify business outcomes and new behavior"]
    C --> H["Compare before/after with p95 and GB-s"]
    D --> H
    F --> H
    G --> H
~~~

### 20.2. Scenario 1 — `Errors` Spikes After Deploy

1. Identify the **deployment timestamp and active alias/version** serving traffic.
2. Inspect **`Errors` Sum**, `Duration` p95, throttles, concurrency, and traffic share.
3. Search **`requestId`/logs** for `Runtime.ExitError`, exceptions, timeouts, or permission denials.
4. Check X-Ray traces to pinpoint slow dependencies.
5. Diff memory, timeout, environment variables, and secrets against the prior version.
6. If the release clearly caused the outage, execute your approved alias rollback / traffic shift.
7. Check data migrations and event replays; rolling back code does not roll back data.

### 20.3. Scenario 2 — `Throttles` Spikes

1. Check **`ConcurrentExecutions` Maximum** and function **reserved concurrency**.
2. Check Regional account concurrency quota and **`ClaimedAccountConcurrency`**.
3. Check trigger sources, traffic bursts, and retry loops.
4. For SQS, inspect mapping max concurrency, queue age, and DLQ.
5. Verify downstream capacity before raising concurrency.
6. If raising quotas or reserved concurrency, ensure budgets and DB connection limits hold.

**Never raise concurrency blindly just because throttles appeared**; Lambda might be shielding a connection-constrained database.

### 20.4. Scenario 3 — `Duration` Climbs While `Errors = 0`

1. Verify you are comparing the exact same metric, dimension, Region, and alias/version.
2. Inspect p95/p99 and MAX, not just Average.
3. Check logs and traces for slow calls.
4. Inspect memory, CPU, GC/Java init, and networking.
5. Check dependencies: RDS locks, S3 latency, external API rate limits.
6. Even before timeouts trigger, `Errors` stays 0 while **users wait unacceptably long**.
7. Measure API Gateway/ALB latency separately to spot bottlenecks outside the handler.

### 20.5. Scenario 4 — Async Backlog Grows and Events Are Lost

1. Inspect **`AsyncEventsReceived`**, **`AsyncEventAge`**, and **`AsyncEventsDropped`**.
2. Check `Errors`, `Throttles`, reserved concurrency, and async error handling config.
3. Inspect destination/DLQ policies, KMS, retention, and delivery failure metrics.
4. Check whether the event source is emitting duplicates or spikes.
5. Plan replay from a durable source or failure destination where available; never assume every dropped event is recoverable.
6. Fix poison events and idempotency — never disable retries just to make `Errors` look pretty.

### 20.6. Scenario 5 — Bill Rises Without Traffic Growth

Check at least these drivers:

| Cost driver | Evidence to inspect |
| --- | --- |
| **Higher configured memory** | Function configs/version history and `Billed Duration`. |
| **Longer duration** | p95/avg/`REPORT` logs, SDK/DB calls. |
| **Idle Provisioned Concurrency** | Provisioned pools per alias/version with low utilization. |
| **Excessive logging** | CloudWatch log ingestion/storage/queries, log-level edits. |
| **Retries/duplicate runs** | `Invocations` outpacing business transactions, SQS receives/deletes, DLQ. |
| **Recursive event loops** | S3/EventBridge/SQS fan-out, `RecursiveInvocationsDropped` if emitted. |
| **Network/NAT** | Data transfer/NAT usage types, VPC routes, S3 requests. |
| **Extra `/tmp`** | `EphemeralStorage.Size > 512` MB. |
| **Extra tracing/Insights** | X-Ray traces, Insights layer, custom metrics/log volume. |
| **Extra downstream API calls** | S3/DynamoDB/KMS/API Gateway usage metrics. |

Post-incident findings should capture **technical root cause, business impact, remediation, rollback criteria, and verification in the next billing cycle**.

## 21. Case Study: Image Processing Pipeline S3 → SQS → Lambda

### 21.1. Requirements

A platform processes **200,000 images/day**, generating a thumbnail and writing metadata for each:

- Users upload images to S3.
- S3 emits notifications for prefix **`incoming/`**.
- Notifications enter an **SQS Standard queue**.
- A Java Lambda worker consumes messages, processes images, writes outputs to S3, and updates DynamoDB metadata.
- Business SLO: **99% of images processed within 2 minutes**.
- Zero duplicate side effects when S3/SQS retry.
- Predictable cost per completed image.

~~~mermaid
flowchart LR
    USER["Image upload"] --> S3[("S3 incoming/")]
    S3 --> SQS["SQS Standard"]
    SQS --> L["Lambda Java worker"]
    L --> OUT[("S3 thumbnails/")]
    L --> DDB[("DynamoDB status")]
    SQS -.-> DLQ["DLQ"]
    L --> CW["CloudWatch + X-Ray"]
    CW --> OPS["SLO & cost dashboard"]
~~~

### 21.2. Minimum Metrics and Alarms

| Category | Metrics |
| --- | --- |
| S3/SQS ingestion | `NumberOfMessagesSent`, `ApproximateNumberOfMessagesVisible`/`NotVisible`. |
| Timeliness | `ApproximateAgeOfOldestMessage` and custom **`ImagesCompleted`**. |
| Failures | Lambda `Errors`, DLQ depth, error types, failed-message counters. |
| Performance | `Duration` p95/p99, `Max Memory Used` from `REPORT`, duration by image size. |
| Capacity | `ConcurrentExecutions`/`Throttles` and ESM limits. |
| Cost | Lambda invocations/GB-s, S3 GET/PUT, SQS requests, CloudWatch logs, KMS if enabled. |

### 21.3. Step-by-Step Optimization

1. **Prefix/suffix filtering:** emit events only for valid image uploads, never thumbnail outputs.
2. **Workload profiling:** 50 KB and 20 MB images have very different durations; benchmark across size buckets.
3. **Memory tuning:** benchmark 512 / 1,024 / 2,048 MB; choose the point hitting p95 SLA with lowest GB-s.
4. **Batch size:** evaluate 1, 5, and 10 SQS records/batch alongside timeouts and partial batch responses.
5. **Idempotency:** track state by S3 object key + `versionId` (or business key) so stale retries never overwrite newer thumbnails/metadata.
6. **Concurrency control:** prevent overwhelming image libraries, S3/DynamoDB throughput, and quotas.
7. **DLQ/alarms:** catch unprocessable files and support controlled post-fix replays.
8. **Separate output bucket/prefix:** prevent S3 `ObjectCreated` recursion loops from new thumbnails.
9. **Cut log noise:** log safe input metadata, `errorType`, `requestId`, duration, and outcome only.
10. **Evaluate cost per completed image**, not raw Lambda duration alone.

### 21.4. Expected Outcome

An optimization succeeds only when **all hold together**:

- p95/p99 processing time improves or stays within SLO.
- Oldest message age and DLQ counts do not climb unexpectedly.
- Correctness and zero-duplication targets hold.
- Total **cost per successfully processed image** drops after counting S3/SQS/Logs/KMS.
- No security regressions appear in logging, IAM, or temporary storage.

If raising memory cuts invocation duration from 400 ms to 190 ms yet triggers more timeouts and retries against another API, total pipeline cost can still climb.

## 22. Case Study: Java Lambda API with Cold Starts and Spikes

### 22.1. Requirements

A Java API runs API Gateway → Lambda → RDS with spiky traffic:

- Normal days: 10 requests/second.
- Flash sales: 100 requests/second for several minutes.
- End-to-end p99 latency must stay under 1 second.
- RDS has strict connection limits.

### 22.2. Investigation

1. Inspect **API Gateway latency/integration latency** alongside Lambda `Duration` p95/p99.
2. Measure cold-start rate via `Init Duration`/X-Ray/Insights samples.
3. Estimate concurrency: `100 RPS × 0.4 s ≈ 40 concurrent` before bursts and tail effects.
4. If each invocation opens a fresh DB connection, DB connection-storm risk may outweigh cold starts.
5. Compare three levers: memory tuning, Java SnapStart (if compatible), and Provisioned Concurrency.
6. Evaluate RDS Proxy, connection pooling, VPC endpoints, timeouts, and cancellation behavior.
7. Weigh **idle provisioned capacity cost** against p99 gains and revenue impact.

### 22.3. Reasonable Choices

- On compatible Java runtimes, evaluate SnapStart to trim initialization while auditing limits and state uniqueness.
- Provisioned Concurrency can fit **scheduled sale windows** if p99 is strict and init tuning falls short — pair with scheduled scaling and monitor utilization.
- Reserved concurrency reserves capacity and caps DB pressure, yet too tight a ceiling throttles flash-sale bursts.
- Increasing memory cuts compute duration, though it won't fix slow SQL queries.

**Never adopt an expensive feature purely for its label.** Compare real p99, success rate, and total cost under identical load.

## 23. Misconceptions to Avoid

| Misconception | Accurate understanding |
| --- | --- |
| “Lambda `Invocations` equals total HTTP requests.” | One request can call multiple functions; batches and retries diverge from business request counts. |
| “`Errors = 0` means the API returned zero HTTP 500s.” | Handlers can return `statusCode=500` cleanly without failing the runtime invocation. |
| “`Duration` includes all cold start time.” | Standard `Duration` omits cold init; `Billed Duration` and `REPORT` show additional components. |
| “Lambda bills based on `Max Memory Used`.” | Compute billing uses **configured memory** and billed duration. |
| “Halving memory always halves the bill.” | Memory controls CPU too, so duration can spike dramatically. |
| “p95 `Duration` equals user-facing p95 latency.” | API Gateway/ALB/network, init, and client overhead still add latency. |
| “CloudWatch `Sum(ConcurrentExecutions)` is total requests.” | Concurrency measures in-flight executions; use `Maximum` and utilization metrics. |
| “No datapoints means the system is healthy.” | Metrics may emit nothing during zero traffic or misconfiguration. |
| “Enabling Reserved Concurrency incurs a reservation fee.” | Reserved concurrency has no separate charge; Provisioned Concurrency does. |
| “Provisioned Concurrency and SnapStart are the same thing.” | One holds pre-initialized capacity; the other uses snapshot restoration with separate limits. |
| “SnapStart supports every runtime and config.” | Depends on runtime, package format, Region, and limits like EFS, `/tmp`, and provisioned capacity. |
| “SQS queue age equals Lambda `IteratorAge`.” | `IteratorAge` applies to stream sources; SQS uses queue age metrics. |
| “One SQS message equals one Lambda invocation.” | Lambda batches multiple messages into a single invocation. |
| “Retries are free.” | Retries drive up invocations, GB-s, SQS/S3/API fees, and side-effect risk. |
| “Having a DLQ means failures heal automatically.” | You still must monitor, fix root causes, and run controlled redrives/replays. |
| “Short CloudWatch Logs retention isn't needed because Lambda cleans up.” | Log groups have independent retention lifecycles that must be configured per policy. |
| “Logging everything always makes debugging best.” | Excessive logging adds noise, PII exposure, and cost; use selective structured logs. |
| “CloudTrail logs every Lambda invocation payload by default.” | CloudTrail management/data events have separate scopes and settings; it doesn't replace app logging/tracing. |
| “Cost Explorer is real-time per invocation.” | Billing aggregates lag; use technical metrics for early anomaly triage. |
| “Cutting Lambda duration alone shrinks the whole AWS bill.” | API Gateway, S3, SQS, NAT, KMS, CloudWatch, and RDS often dominate total spend. |
| “Setting reserved concurrency to 0 pauses compute risk-free.” | Triggers throttles, async retries, event expiration/drops, and growing backlogs. |
| “Lambda inside a VPC automatically gets Internet access.” | Requires routes and NAT/VPC endpoints; broken networking raises duration and timeouts. |
| “A \$100 budget alert blocks spending past \$100.” | Budget alerts notify only; they are not hard spend caps by default. |
| “All Lambda compute types share Event Function pricing.” | Managed Instances, MicroVMs, Web Functions, and add-ons follow their own pricing rules. |

## 24. Practice Exercises and Suggested Answers

### Exercise 1 — Calculating Error Rate

A Lambda function records **12,000 `Invocations`**, **180 `Errors`**, and **30 `Throttles`** in one hour.

**Question:** compute the invocation error rate and assess system health.

**Solution:** Error rate = `180 / 12,000 × 100%` = **1.5%**. **`Throttles`** are invocation attempts rejected before the handler runs, so they **are excluded from both `Invocations` and `Errors`**. To measure end-to-end failure rate, also inspect upstream trigger/API metrics and retries.

### Exercise 2 — Concurrency

A function receives **80 requests/second** with an average `Duration` of **0.25 seconds**.

**Solution:** Average concurrency is approximately **20**. Leave headroom for bursts and tail latency, monitor `Maximum ConcurrentExecutions`, and protect backends — never reserve exactly 20 assuming throttles won't happen.

### Exercise 3 — Comparing GB-Seconds

Two configurations:

- A: 512 MB, billed duration 300 ms.
- B: 1,024 MB, billed duration 120 ms.

**Per-invocation calculation:**

- A: `0.5 × 0.3` = **0.15 GB-s**.
- B: `1 × 0.12` = **0.12 GB-s**.

B consumes fewer GB-seconds despite double the memory allocation. Still compare p95, errors, architecture, and auxiliary costs.

### Exercise 4 — API Returns 500 Yet `Errors` Stays 0

**Question:** A Lambda handler catches an exception and returns JSON with `statusCode=500`. Why is CloudWatch `Errors=0`?

**Answer:** The Lambda runtime sees a normal return object from the handler; this is a **business/API failure**, not a Lambda runtime invocation error. Monitor API Gateway/ALB 5xx and custom business error metrics.

### Exercise 5 — Batch Worker Failure

SQS delivers 10 messages to Lambda. Only the 7th message fails, yet the handler throws an exception for the whole batch.

**Answer:** All 10 messages can be reprocessed after visibility timeout expires, duplicating the 9 succeeded items. Enforce idempotency, enable **`ReportBatchItemFailures`**, and isolate errors per record.

### Exercise 6 — Unexpected Log Bill Spike

A function jumps from 100 bytes of logs/invocation to 20 KB/invocation while invocation count stays flat.

**Answer:** CloudWatch log ingestion jumps roughly **200×** in raw payload size before overhead. Audit log-level changes, payload logging, retention, sensitive data exposure, and Logs Insights scan costs. Trim noisy logs without dropping error/operational signals.

### Exercise 7 — Climbing `AsyncEventAge`

An async Lambda receives events normally, yet **`AsyncEventAge` p95** climbs to several minutes alongside rising **`Throttles`**.

**Answer:** Function or account concurrency is likely constrained, leaving events queued internally. Inspect reserved/account quotas, duration, retries, `AsyncEventsDropped`, and DLQs/destinations; raise concurrency only after checking downstream capacity.

### Exercise 8 — Cold Starts and Cost

A Java API shows high p99 latency only during traffic spikes; handler `Duration` stays flat while `REPORT` shows high `Init Duration` on slow requests.

**Answer:** Trace cold starts with X-Ray/Insights; test Java SnapStart if compatible, tune memory, and consider Provisioned Concurrency during peak hours. Weigh idle capacity cost against p99 gains instead of running 24/7 provisioned capacity without checking utilization.

### Exercise 9 — 5 GB `/tmp`

A video-processing Lambda needs 3 GB of temporary file scratch space.

**Answer:** Default 512 MB `/tmp` is insufficient; raise ephemeral storage within Lambda's supported range. Capacity above 512 MB incurs charges; still verify file cleanup, memory, timeout, and S3 upload confirmation since `/tmp` is non-durable.

### Exercise 10 — Raising Concurrency Increases RDS Errors

A function with reserved concurrency 100 calls RDS, and total DB connections exceed limits during traffic spikes.

**Answer:** Tune concurrency/connection pooling, evaluate RDS Proxy, safely reuse connections, reduce DB calls, and assess DB capacity. Raising reserved concurrency further would worsen the outage.

## 25. Self-Check Questions

**Question 1.** Which two Lambda metrics are the starting point for calculating runtime error rate?  
**Answer:** **`Errors`** and **`Invocations`**, using `Sum` over matching time windows and dimensions.

**Question 2.** Why shouldn't error rate be computed when `Invocations = 0`?  
**Answer:** There are zero observations (denominator is zero); treat as undefined/missing data.

**Question 3.** When evaluating peak concurrency, should you use `Sum` or `Maximum`?  
**Answer:** **`Maximum`** of `ConcurrentExecutions` over the relevant period.

**Question 4.** Does p95 `Duration` include cold-start initialization?  
**Answer:** Standard `Duration` omits cold init; inspect `REPORT`/`Init Duration`, traces, and end-to-end latency.

**Question 5.** Does Lambda compute billing use configured memory or actual memory used?  
**Answer:** **Configured memory**, multiplied by billed duration and the GB-second rate.

**Question 6.** If raising memory cuts duration by more than half, is cost per invoke guaranteed to increase?  
**Answer:** No; compare the product **`memory × billed duration`**, request fees, and supporting costs.

**Question 7.** How do Reserved Concurrency and Provisioned Concurrency differ in cost?  
**Answer:** Reserved concurrency has no capacity surcharge; Provisioned Concurrency charges continuously for pre-initialized capacity and related invoke pricing.

**Question 8.** What does `AsyncEventAge` measure?  
**Answer:** How long an event waits in Lambda's async queue before invocation; climbs during backlogs, retries, and throttles.

**Question 9.** Which queue metric should an SQS worker watch for processing delay?  
**Answer:** **`ApproximateAgeOfOldestMessage`**, alongside visible/invisible counts and DLQ depth.

**Question 10.** Which sources typically emit `IteratorAge`?  
**Answer:** Supported stream sources like DynamoDB Streams, Kinesis, and DocumentDB — not SQS queue age.

**Question 11.** Does Lambda `Errors = 0` guarantee an API returned zero HTTP 500s?  
**Answer:** No. A handler can return HTTP 500 normally without throwing an exception.

**Question 12.** Can `/tmp` serve as long-term durable storage?  
**Answer:** No. `/tmp` is per-environment ephemeral storage with no durability guarantee.

**Question 13.** Why shouldn't loggers print access tokens or raw request bodies?  
**Answer:** Sensitive data persists and propagates into logs and downstream systems, creating leaks and compliance violations.

**Question 14.** What does the provisioned concurrency spillover metric tell you?  
**Answer:** Invocations spilled over to on-demand capacity after provisioned capacity became saturated.

**Question 15.** Why must reducing invocations via batching always be tested against retries?  
**Answer:** Batch failures can reprocess many items, raising duplicates, latency, and cost without partial failure handling.

**Question 16.** How do you detect dropped events in async invocations?  
**Answer:** Check **`AsyncEventsDropped`**, async config, DLQs/on-failure destinations, `Errors`/`Throttles`, and replay paths.

**Question 17.** What costs can enabling Lambda Insights introduce?  
**Answer:** Extra CloudWatch metrics and performance logs, plus slight extension duration overhead.

**Question 18.** Why can Lambda code inside a VPC hit network timeouts?  
**Answer:** Missing routes, NAT, VPC endpoints, DNS, or SG paths to dependencies; VPC attachment does not grant Internet egress automatically.

**Question 19.** When AWS spend rises, is checking Lambda Pricing alone enough?  
**Answer:** No; include CloudWatch, S3, API Gateway, SQS, KMS, NAT, RDS, data transfer, and related resources.

**Question 20.** What is a better KPI for comparing two thumbnail pipelines with different retry rates?  
**Answer:** **Cost per successful image**, evaluated alongside p95 processing time, errors/retries, backlog, and output correctness.

## 26. Summary and Implementation Checklist

**Lambda observability** means far more than watching `Errors` or opening CloudWatch Logs. Sound operations tie together:

- **Metrics:** `Invocations`/`Errors`/`Throttles`, `Duration` p95/p99, concurrency, and async/ESM backlogs.
- **Logs:** `START`/`END`/`REPORT`, application logs with `requestId`/`correlationId`, free of sensitive data.
- **Traces:** AWS X-Ray or OpenTelemetry instrumentation to break down cross-service latency.
- **Alerts/SLOs:** user impact, queue age, availability, latency, error budgets, and runbooks.
- **Billing:** requests, memory × billed duration, provisioned concurrency, `/tmp`, SnapStart where applicable, logs, networking, and downstream services.
- **Reliability:** idempotency, bounded retries, DLQs/on-failure destinations, timeouts, concurrency caps, and replayability.

### Production Checklist

1. Define **SLOs** around users and event sources, not just handler metrics.
2. Build dashboards with **`Errors`/`Invocations` ratio**, `Throttles`, p95 `Duration`, and `Maximum` concurrency on the right dimensions.
3. For async flows: track **`AsyncEventAge`, `AsyncEventsDropped`, and destinations/DLQs**.
4. For SQS/streams: track **queue age / `IteratorAge` / `OffsetLag`** matching the exact source.
5. Enforce structured logs, log-group retention, and proper IAM/KMS with zero secrets or PII in logs.
6. Enable Tracing/Insights deliberately where diagnostics justify their overhead and cost.
7. Tune memory via **GB-seconds + latency + errors** benchmarks, never guesswork.
8. Validate cold starts with evidence before investing in SnapStart or Provisioned Concurrency.
9. Tune batching, filtering, SDK retries, and concurrency to preserve business correctness.
10. Analyze costs across the **entire pipeline**, not just the Lambda line item.
11. Enable AWS Budgets and Cost Anomaly Detection without mistaking alerts for hard spend caps.
12. Periodically load-test, audit IAM, drill DLQ replays, practice rollbacks, and verify RPO/RTO recovery targets.

The highest-leverage skill is **measuring root causes** and **making evidence-backed changes**: faster Lambda isn't always cheaper; low Lambda `Errors` doesn't guarantee a healthy app; fewer requests don't guarantee correctness. Pairing technical observability with business outcomes keeps AWS systems secure, resilient, and cost-efficient over the long haul.

### Official AWS References

- [Monitoring Lambda metrics](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-metrics.html) — monitoring Lambda with CloudWatch.
- [Types of metrics for Lambda](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-metrics-types.html) — `Invocations`, `Errors`, `Throttles`, `Duration`, and source-specific metrics.
- [Viewing Lambda logs](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-cloudwatchlogs-view.html) — `START`/`END`/`REPORT` and log access.
- [Advanced logging controls](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-logs.html) — JSON, log levels, and destinations.
- [AWS X-Ray for Lambda](https://docs.aws.amazon.com/lambda/latest/dg/services-xray.html) — distributed tracing.
- [CloudWatch Lambda Insights](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-insights.html) — runtime CPU/memory/network telemetry.
- [Understanding Lambda concurrency](https://docs.aws.amazon.com/lambda/latest/dg/lambda-concurrency.html) — concurrency, reserved/provisioned, and throttles.
- [Configuring Lambda memory](https://docs.aws.amazon.com/lambda/latest/dg/configuration-memory.html) — CPU scaling with memory.
- [Configuring ephemeral storage](https://docs.aws.amazon.com/lambda/latest/dg/configuration-ephemeral-storage.html) — `/tmp` and configurable limits.
- [Lambda SnapStart](https://docs.aws.amazon.com/lambda/latest/dg/snapstart.html) — initialization snapshots, runtimes, and limits.
- [Asynchronous invocation error handling](https://docs.aws.amazon.com/lambda/latest/dg/invocation-async-error-handling.html) — retries and event age.
- [SQS error handling and partial batch](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html) — failed message handling.
- [AWS Lambda pricing](https://aws.amazon.com/lambda/pricing/) — compute modes, requests, duration, provisioned concurrency, and options.
- [AWS Cost Explorer](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-what-is.html) — analyzing AWS usage and spend.
- [AWS Pricing Calculator](https://calculator.aws/) — estimating costs by architecture and Region.
