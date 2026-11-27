# Monitoring Lambda with CloudWatch, X-Ray, and Lambda Insights

In the **AWS Serverless Integrations** chapter, observability helps operations teams understand what a function is doing, how long request processing takes, and where failures occur. A Lambda function may succeed on one invocation and fail on another due to cold starts, slow dependencies, concurrency limits, or redelivered messages. Reading fragmented logs alone makes it very hard to connect symptoms to root causes.

AWS provides several complementary observability tools:

- **Amazon CloudWatch** centralizes logs, metrics, dashboards, and alarms.
- **AWS X-Ray** traces the request path across functions and dependent services.
- **Lambda Insights** adds system and performance metrics at the execution environment level.

This lesson belongs to the **CLOUD_SERVERLESS** module, focusing on developing and deploying serverless applications—especially Java functions triggered by HTTP, messages, or events. Learners must track triggers, state, access permissions, retries, idempotency, cold starts, scaling, and cost to make sound FaaS operational decisions. This lesson combines logs, metrics, and traces into a diagnostic workflow applicable to Java Lambda in production.

## 1. Observability: Logs, Metrics, and Traces

The three observability signals answer three different questions:

| Signal | Answers the question | Example |
|---|---|---|
| Log | What happened during a single execution? | Request missing customerId, database timeout |
| Metric | How is the system performing over time? | Error rate, p95 duration, concurrency |
| Trace | Which components did a request pass through and where was it slow? | API Gateway → Lambda → database → event bus |

No signal can replace the other two. Logs explain a specific event in detail, but make it hard to spot trends without aggregation. Metrics show rising error counts, but do not necessarily pinpoint the cause. Traces illustrate relationships between steps, but are only useful when trace context propagates across boundaries and enough sampled data is collected.

~~~mermaid
flowchart TD
    INV["Lambda invocation"] --> LOG["CloudWatch Logs"]
    INV --> MET["CloudWatch Metrics"]
    INV --> TRACE["AWS X-Ray trace"]
    INV --> INS["Lambda Insights extension"]
    LOG --> DASH["Dashboard / Alarm / Logs Insights"]
    MET --> DASH
    TRACE --> MAP["Trace map / latency analysis"]
    INS --> DASH
    MAP --> FIX["Diagnose and improve"]
    DASH --> FIX
~~~

A solid observability workflow links signals via function name, version, request ID, event ID, correlation ID, and trace ID. When an alarm fires, the on-call engineer can move from metrics to logs, from logs to a specific invocation, and then open the trace to see which dependency caused latency.

## 2. CloudWatch Logs for Lambda

### 2.1. Log Groups and Log Streams

By default, Lambda sends function logs to CloudWatch Logs. The log group is typically named:

~~~text
/aws/lambda/<function-name>
~~~

Each execution environment or initialization can create its own log stream. A function produces multiple streams as it scales out across multiple environments. Therefore, never assume all logs for a function live in a single file or stream.

To write logs, the execution role needs corresponding CloudWatch Logs permissions, typically:

- `logs:CreateLogGroup`
- `logs:CreateLogStream`
- `logs:PutLogEvents`

These can be granted via an appropriate AWS managed policy or a custom policy scoped to the required log group. Do not grant broader CloudWatch administrative permissions than necessary. If the log group is pre-created via IaC, you can restrict log group creation permissions depending on your deployment setup.

### 2.2. Structured Logging

Free-form text logs are hard to filter across many functions. Emit structured logs, typically JSON, with consistent fields:

- `timestamp`: time the log was written.
- `level`: INFO, WARN, ERROR, or DEBUG.
- `message`: concise description.
- `functionName` and `functionVersion`.
- `requestId`: invocation ID provided by Lambda.
- `correlationId` or `eventId`: business identifiers.
- `operation`: operation name.
- `durationMs`: execution duration if available.
- `errorCode`: stable error code, independent of stack traces.

Example log:

~~~json
{
  "level": "INFO",
  "message": "Order accepted",
  "function": "place-order",
  "requestId": "7b6f4d2a-example",
  "correlationId": "checkout-2026-001",
  "eventId": "evt-1001",
  "orderId": "ORD-1001",
  "durationMs": 84
}
~~~

Never write passwords, tokens, session cookies, payment details, or full payloads containing personal data into logs. Logs are often centralized, retained, and accessible to multiple teams; log only the minimum data required for investigation.

### 2.3. Logging in Java Lambda

Java Lambda can use Lambda Logger, SLF4J with a suitable logging backend, or the application's logging framework. The following example writes JSON using Jackson to illustrate structured logging:

~~~java
import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.LambdaLogger;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;

public final class OrderHandler {
    private static final ObjectMapper JSON = new ObjectMapper();

    public OrderResult handleRequest(OrderEvent event, Context context) {
        LambdaLogger logger = context.getLogger();

        try {
            OrderResult result = process(event);

            logger.log(toJson(Map.of(
                    "level", "INFO",
                    "message", "Order accepted",
                    "requestId", context.getAwsRequestId(),
                    "orderId", result.orderId())) + "\n");

            return result;
        } catch (RuntimeException failure) {
            logger.log(toJson(Map.of(
                    "level", "ERROR",
                    "message", "Order processing failed",
                    "requestId", context.getAwsRequestId(),
                    "errorType", failure.getClass().getSimpleName())) + "\n");
            throw failure;
        }
    }

    private String toJson(Object value) {
        try {
            return JSON.writeValueAsString(value);
        } catch (Exception serializationFailure) {
            return "{\"level\":\"ERROR\",\"message\":\"Log serialization failed\"}";
        }
    }

    private OrderResult process(OrderEvent event) {
        // Invoke business use case here.
        return new OrderResult(event.orderId(), "ACCEPTED");
    }
}
~~~

`OrderEvent` and `OrderResult` are illustrative DTOs. In real applications, configure the logging framework once, avoid creating a new `ObjectMapper` per invocation, and ensure the logger never emits sensitive data. When using a logging framework, configure a JSON encoder or structured logging per runtime and framework capabilities.

Lambda can also configure system log formats and log levels for certain supported runtimes. Check the capabilities of your Java runtime and framework; do not assume every logger automatically emits JSON merely because the application writes JSON strings.

### 2.4. Log Retention

CloudWatch Logs applies retention policies per log group. Without configured retention, logs can persist indefinitely until manually deleted. This incurs ongoing costs and may conflict with data governance policies.

Choose retention based on:

- Time needed for incident investigation.
- Audit and compliance requirements.
- Sensitivity level of the data.
- Ingestion and storage costs.
- Need to export to long-term archives.

Use IaC to create log groups and set retention before functions run. Do not use logs as a long-term business data store.

## 3. Searching Logs with CloudWatch Logs Insights

CloudWatch Logs Insights lets you query logs by field, keyword, and time range. With JSON logs, fields can be extracted automatically for filtering and aggregation.

Example finding recent errors:

~~~sql
fields @timestamp, level, message, requestId, errorType
| filter level = "ERROR"
| sort @timestamp desc
| limit 50
~~~

Finding slow requests if the application logs `durationMs`:

~~~sql
fields @timestamp, requestId, operation, durationMs
| filter durationMs >= 1000
| sort durationMs desc
| limit 30
~~~

Counting errors by type:

~~~sql
fields errorType
| filter level = "ERROR"
| stats count() as failures by errorType
| sort failures desc
~~~

Finding invocations by correlation ID:

~~~sql
fields @timestamp, @message, requestId, correlationId, eventId
| filter correlationId = "checkout-2026-001"
| sort @timestamp asc
~~~

Field names must match the actual log format. If logs are plain text, use appropriate parsers or expressions. Overly broad queries across wide time ranges take longer and cost more; scope time ranges and log groups during investigations.

## 4. Key CloudWatch Metrics for Lambda

CloudWatch receives standard metrics in the **AWS/Lambda** namespace. Metrics show how many invocations a function receives, whether it encounters errors or throttling, how long it runs, and how much concurrency it uses.

| Metric | Meaning | Used to monitor |
|---|---|---|
| `Invocations` | Number of times the function was invoked | Traffic and load trends |
| `Errors` | Number of invocations ending with a function/runtime error | Error rate |
| `Duration` | Handler/invocation execution time as measured by Lambda | Latency, p95/p99 |
| `Throttles` | Number of invocations rejected due to concurrency limits | Concurrency pressure |
| `ConcurrentExecutions` | Number of invocations running concurrently | Concurrency utilization |
| `UnreservedConcurrentExecutions` | Concurrency used outside provisioned/reserved allocations | Account-level concurrency tracking |
| `ProvisionedConcurrencyUtilization` | Utilization of provisioned concurrency | Tuning provisioned configuration |
| `AsyncEventAge` | Age of asynchronous events when Lambda processes them | Backlog delay |
| `AsyncEventsDropped` | Number of asynchronous events dropped | Delivery failures or exhausted retries |
| `IteratorAge` | Lag of stream records relative to when they are read | Stream consumer backlog |

Metrics can appear with different dimension sets, such as `FunctionName`, `Resource`, or `ExecutedVersion`. When creating alarms, pick the dimension matching your target: the whole function, an alias, or a specific version.

### 4.1. Errors and Error Rate

Looking solely at `Errors` counts can be misleading when traffic fluctuates. 10 errors out of 100 invocations represents a very different error rate than 10 errors out of 100,000 invocations.

You can track the ratio:

\[
ErrorRate = \frac{Errors}{Invocations} \times 100\%
\]

When implementing alarms, avoid division by zero during periods with no invocations. Use metric math or monitor both absolute error counts and error rates.

`Throttles` should be tracked separately. A throttled invocation is not the same as an invocation that ran and threw an exception. With queues/event source mappings, throttling can cause backlogs to grow and message age to rise.

### 4.2. Duration and Percentiles

`Duration` is commonly aggregated using statistics such as Average, Maximum, and percentiles. Averages can hide a cluster of very slow requests. For latency-sensitive APIs, track p95 or p99 to catch tail latency.

The `Duration` metric reflects function execution time, not the entire execution environment initialization phase. For cold starts, inspect `Init Duration` in the CloudWatch Logs `REPORT` line or initialization telemetry supported by your observability tools. Looking only at `Duration` can cause operations teams to miss delays happening before the handler even starts.

Do not enforce the same duration threshold across every function. Thresholds must reflect SLAs, function timeouts, normal processing time, and trigger characteristics. A batch consumer may legitimately have longer duration than a simple HTTP handler.

### 4.3. Trigger-Specific Metrics

For functions processing queues or streams, also monitor source metrics:

- `ApproximateAgeOfOldestMessage` or equivalent queue age metrics.
- `ApproximateNumberOfMessagesVisible` and queued message counts.
- `IteratorAge` for stream event source mappings.
- DLQ depth or messages moved to dead-letter queues.
- Batch failures and retry counts per platform capabilities.

A function with low `Errors` while message age climbs steadily may still be falling behind load. Observability must cover both the function and the message-producing/broker layer.

## 5. Custom Metrics and Embedded Metric Format

Standard Lambda metrics have no awareness of business concepts such as accepted orders, failed payments, or rejected inventory holds. Applications can emit custom metrics to track those outcomes.

CloudWatch Embedded Metric Format (EMF) lets you write a JSON log entry containing metric metadata; CloudWatch parses that log and extracts metrics automatically.

EMF example:

~~~json
{
  "_aws": {
    "Timestamp": 1763374530000,
    "CloudWatchMetrics": [
      {
        "Namespace": "Orders/Serverless",
        "Dimensions": [["Service", "Function"]],
        "Metrics": [
          {"Name": "OrdersAccepted", "Unit": "Count"},
          {"Name": "ProcessingLatency", "Unit": "Milliseconds"}
        ]
      }
    ]
  },
  "Service": "orders",
  "Function": "place-order",
  "OrdersAccepted": 1,
  "ProcessingLatency": 84
}
~~~

Dimensions should have bounded cardinality. Never use `orderId`, `requestId`, `email`, or `userId` as a dimension because each unique value creates a distinct metric time series, driving up cardinality and cost. Per-invocation identifiers belong in logs or traces.

Custom metrics are useful for building business dashboards, such as order success rates or rejected event counts. Emit custom metrics only when answering a specific operational question; avoid duplicating standard metrics.

## 6. Dashboards and Alarms

### 6.1. Operations-Oriented Dashboards

A Lambda dashboard should quickly answer:

- Is the function receiving normal traffic?
- Are error rates and throttling rising?
- Are p95/p99 durations exceeding targets?
- Is concurrency approaching limits?
- Are queue age or iterator age rising?
- Are cold starts, memory, or CPU behaving abnormally?
- Which function version started producing errors?

Dashboards can be organized into rows:

1. **Traffic:** Invocations, event counts, and concurrency.
2. **Reliability:** Errors, throttles, async events dropped, and DLQs.
3. **Latency:** p50/p95/p99 duration and message age.
4. **Resources:** Memory utilization, CPU, network, and `/tmp` from Lambda Insights.
5. **Dependencies:** Database latency, timeouts, external API errors, and trace durations.

### 6.2. Service-Objective-Driven Alarms

Alarms should map to concrete actions. Examples:

- Error rate exceeds threshold across multiple evaluation periods.
- Sustained throttles occur.
- p95 duration exceeds SLA.
- Queue age or `IteratorAge` exceeds acceptable thresholds.
- New messages arrive in a DLQ.
- `ConcurrentExecutions` approaches quotas or reserved concurrency.
- `AsyncEventsDropped` is greater than 0.

Do not alarm simply because a metric is non-zero if that is normal behavior. For instance, `Errors` may tick up slightly in workloads receiving invalid external input; separate expected business errors from system failures.

Example creating an alarm on `Errors` count:

~~~bash
aws cloudwatch put-metric-alarm \
  --alarm-name place-order-errors \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=place-order \
  --statistic Sum \
  --period 60 \
  --evaluation-periods 3 \
  --threshold 1 \
  --comparison-operator GreaterThanOrEqualToThreshold \
  --treat-missing-data notBreaching \
  --alarm-actions arn:aws:sns:ap-southeast-1:123456789012:ops-alerts
~~~

This example uses an illustrative threshold, not a configuration suitable for every workload. For low-volume functions, a single error may warrant attention; for functions processing millions of messages, use error rates or categorized error metrics.

### 6.3. Missing Data

Absence of metrics during an interval can mean the function was not invoked, metrics were not emitted, or the telemetry pipeline failed. Choose `treatMissingData` based on intent:

- `notBreaching` if having zero invocations is a normal idle state.
- `breaching` if missing metrics can itself indicate the system has stopped operating.
- `ignore` or `missing` when preserving the previous alarm state is desired.

Do not apply the same missing-data policy to every metric. For example, silent traffic metrics may be normal overnight, whereas a heartbeat metric for a mandatory every-minute job is not.

## 7. AWS X-Ray and Distributed Tracing

CloudWatch tells you a function is slow or failing; X-Ray helps pinpoint which components a request traversed and how much time was spent at each hop.

A trace can include:

- **Trace:** the end-to-end journey of a request or workflow.
- **Segment:** the work done by one service, such as a Lambda function.
- **Subsegment:** a sub-operation such as a database call, HTTP API call, or AWS service call.
- **Trace ID:** shared identifier linking segments together.
- **Parent ID:** parent-child relationship between execution segments.

Order flow example:

~~~mermaid
flowchart LR
    C["Client"] --> A["API Gateway"]
    A --> L["Order Lambda"]
    L --> D["Database"]
    L --> E["EventBridge"]
    E --> I["Inventory Lambda"]
    I --> S["Inventory database"]
~~~

In the X-Ray service map, nodes and edges represent services and the calls between them. The trace timeline helps isolate time spent inside Lambda, databases, or HTTP dependencies.

X-Ray does not automatically know about every internal operation. Code must be instrumented or use appropriate integrations/instrumentation to create subsegments/spans for dependencies.

## 8. Enabling Active Tracing for Lambda

Lambda has a tracing mode configuration. When Active tracing is enabled, Lambda integrates with X-Ray to collect invocation traces according to the service's sampling rules.

It can be enabled in the console or via the AWS CLI:

~~~bash
aws lambda update-function-configuration \
  --function-name place-order \
  --tracing-config Mode=Active
~~~

The execution role needs permission to write traces. You can use an appropriate AWS managed policy, commonly `AWSXRayDaemonWriteAccess`, or a least-privilege policy containing required actions such as `xray:PutTraceSegments` and `xray:PutTelemetryRecords` depending on the deployment model.

When tracing is set to `Active`, Lambda creates a segment for the invocation. Instrumented code can add details about sub-operations. With `PassThrough`, the function does not actively instruct Lambda to record traces; trace context propagation depends on how callers and integrations pass metadata.

Enabling active tracing does not mean every request is recorded in full. X-Ray uses sampling to limit trace volume. When investigating rare bugs, account for sampling rules, metrics, and logs rather than relying on whether one specific request happened to be sampled.

## 9. Trace Context and Propagation Across Asynchronous Boundaries

Distributed tracing is only useful when context propagates from one service to the next. Over HTTP, trace context travels in headers. Over queues or event buses, context must be carried in message attributes, envelope extensions, or tracing mechanisms supported by the integration.

Identifiers play distinct roles:

- **Trace ID:** links spans within a single trace.
- **Correlation ID:** links business steps, even when they do not belong to one continuous trace.
- **Event ID:** identifies a specific event.
- **Request ID:** identifies a specific Lambda invocation.

Do not collapse all of them into a single ID. A business process can span hours across multiple retries and multiple distinct traces; a correlation ID is often more stable than a trace ID.

With asynchronous invocations, queues, or streams, automatic trace linking depends on the integration and event source type. If continuity is required, propagate trace context explicitly and verify with real traces. Do not assume every event bus or queue preserves a single continuous trace across all retries and replays.

## 10. Instrumenting Java with OpenTelemetry

Java functions can be instrumented with OpenTelemetry (OTel) to emit spans and propagate trace context. AWS Distro for OpenTelemetry (ADOT) provides components and integrations tailored to the AWS ecosystem.

Instrumentation can be applied at several layers:

- Handler: a span wrapping an invocation or use case.
- HTTP client: spans for requests to external services.
- AWS SDK: instrumentation for AWS service calls if supported by version and configuration.
- JDBC: instrumentation for database operations if compatible drivers/instrumentation are used.
- Message producer/consumer: injecting and extracting trace context across messages.

Conceptual example creating a span with the OpenTelemetry API:

~~~java
import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.Tracer;

public final class OrderUseCase {
    private static final Tracer TRACER =
            GlobalOpenTelemetry.getTracer("orders-service");

    public OrderResult execute(OrderCommand command) {
        Span span = TRACER.spanBuilder("OrderUseCase.execute").startSpan();

        try (var scope = span.makeCurrent()) {
            span.setAttribute("order.channel", command.channel());
            return processOrder(command);
        } catch (RuntimeException failure) {
            span.recordException(failure);
            span.setStatus(
                    io.opentelemetry.api.trace.StatusCode.ERROR);
            throw failure;
        } finally {
            span.end();
        }
    }

    private OrderResult processOrder(OrderCommand command) {
        // Business logic.
        return new OrderResult(command.orderId(), "ACCEPTED");
    }
}
~~~

This example assumes the SDK and exporter have already been configured by the appropriate instrumentation or layer. Do not instantiate exporters on every invocation. Review how ADOT is deployed for Java runtimes, how wrappers/extensions are attached, and how the collector is configured per current AWS guidance.

Avoid enabling multiple instrumentation mechanisms simultaneously for the same library if they produce duplicate spans. When using an auto-instrumentation agent or layer, clearly delineate what is instrumented automatically vs. where manual spans are added.

## 11. Sampling and Trace Costs

Traces can generate large volumes of data when functions receive heavy traffic. Sampling determines which requests are recorded in detail.

Common sampling strategies:

- **Reservoir sampling:** retains a minimum number of samples within a time interval.
- **Rate sampling:** captures a percentage of requests.
- **Custom sampling rules:** prioritizes or excludes requests by service, resource, or matching attributes.

Sampling controls cost and reduces data volume, but may miss rare failing requests. Therefore, combine traces with metrics and logs. Metrics reveal whether errors are rising; logs preserve failure details; traces reveal dependency behavior for sampled requests.

Do not set sampling rates overly high in production without factoring in traffic and cost. Conversely, do not set them so low that no useful traces exist during an incident. Tune based on traffic, SLA requirements, and storage capacity.

## 12. Lambda Insights

Lambda Insights is a performance observability feature for Lambda that adds metrics at the execution environment level. It is deployed via a Lambda extension and layer matching the runtime and architecture, sending telemetry to CloudWatch.

Observable data includes:

- Memory used and memory utilization percentage.
- CPU time and CPU activity level.
- Network bytes received/sent.
- Ephemeral `/tmp` filesystem usage.
- Initialization duration and execution environment details per service capabilities.
- Additional diagnostic performance metrics.

Standard Lambda metrics do not report detailed actual memory usage per invocation. Lambda Insights fills this gap, helping detect functions approaching their memory limit or exhibiting abnormal CPU/network consumption.

### 12.1. Enabling Lambda Insights

Lambda Insights can be enabled from the console or by attaching the corresponding layer. The execution role needs permissions for the extension to send telemetry to CloudWatch. AWS provides a managed policy such as **CloudWatchLambdaInsightsExecutionRolePolicy** for this use case; verify policies and actual permissions in your organization's environment.

The layer must match the exact Region, runtime, and architecture. If the function uses `arm64`, select the `arm64`-compatible layer. When deploying with IaC, manage the layer ARN and role policy in configuration rather than toggling manually without an audit trail.

### 12.2. Reading Metrics from Lambda Insights

Example questions it helps answer:

- Is memory utilization approaching the configured limit?
- Is CPU time rising due to large payload processing or a dependency?
- Is `/tmp` filling up due to downloaded files or caches?
- Is network throughput spiking from external service calls?
- Did init duration increase after adding dependencies or layers?

If memory usage routinely nears the limit, you may need to allocate more memory or shrink the memory footprint. In Lambda, configured memory also scales allocated CPU; increasing memory can lower duration and total cost for CPU-bound workloads, though you should benchmark first.

Lambda Insights supplements system telemetry and does not replace CloudWatch Logs, standard metrics, or X-Ray. Nor does it explain business logic inside code on its own.

## 13. Combining CloudWatch, X-Ray, and Lambda Insights

The three tools can be used in a unified diagnostic workflow:

1. A CloudWatch alarm detects rising `Errors` or p95 `Duration`.
2. The dashboard shows whether the issue began after deploying a new version or when concurrency spiked.
3. CloudWatch Logs Insights filters failing invocations by `requestId` or `correlationId`.
4. X-Ray opens the matching trace to identify which database or HTTP dependency is slow.
5. Lambda Insights shows whether memory, CPU, network, or `/tmp` is abnormal.
6. The operations team correlates findings with configuration changes, dependencies, and traffic.
7. After fixing, monitor metrics and alarms to confirm errors drop.

Example: p95 `Duration` climbs after adding a PDF processing library. X-Ray shows time inside Lambda increased while database call duration remained unchanged. Lambda Insights shows CPU time and memory utilization surged. Logs show large file payloads. Combining the three signals, the development team can evaluate file size limits, processing algorithms, memory configuration, or offloading large files to a more suitable workflow.

## 14. Monitoring Retries, Queues, and Event Source Mappings

For message-processing Lambdas, observability must cover both the function and the message source. A function can show a low `Errors` rate while queue backlog still climbs because concurrency is capped or batches process slowly.

Monitor:

- Queue depth and age of oldest message.
- `AsyncEventAge` and `AsyncEventsDropped` for asynchronous invocations.
- `IteratorAge` for stream event source mappings.
- Messages moved to DLQs.
- Retry counts and batch failures from source metrics/logs.
- `Throttles` and `ConcurrentExecutions`.
- `Duration` relative to batch size.
- Message processing success rate.

When a message fails repeatedly, logs should record event ID, receive count, or attempt metadata if supplied by the trigger. Do not log the entire payload. Use an idempotency key to prevent duplicate business processing when messages are redelivered.

For streams, rising `IteratorAge` indicates the consumer is not keeping up with the record production rate. Check partition count, batch size, function concurrency, processing time, and record errors. For queues, rising message age can stem from backlog, visibility timeouts, throttling, or slow dependencies.

## 15. Security and Access Control for Observability

Logs, traces, and metrics can contain sensitive information or reveal internal topology. Manage access following least privilege.

Key points:

- Execution roles have only the permissions to write logs, metrics, or traces that the function actually needs.
- Operations teams have read access to logs and traces scoped by function or account.
- Do not grant every developer read access to all production logs unnecessarily.
- Never write secrets, tokens, personal data, or payment payloads into logs or spans.
- Apply appropriate retention and storage policies.
- Protect dashboards, alarm actions, and SNS topics receiving alerts.
- Restrict permissions to create or modify sampling rules.
- Review trace data access controls when sharing across teams.

If using X-Ray active tracing, grant trace-writing permissions to the execution role. If using Lambda Insights, add the corresponding telemetry permissions for the extension. Log-writing permissions do not automatically grant log-reading permissions; dashboard and query read permissions should be granted separately.

## 16. Observability Cost and Data Limits

Observability costs can come from:

- Log ingestion and log storage.
- CloudWatch Logs Insights queries.
- Custom metrics and dimension counts.
- Dashboards, alarms, and metric APIs under current pricing models.
- X-Ray traces recorded and queried.
- Lambda Insights telemetry.
- Data exported to or stored in other services.

Control costs by:

- Choosing appropriate log levels; limiting `DEBUG` in production.
- Setting explicit retention on every log group.
- Avoiding logging entire payloads repeatedly.
- Using sampling for traces.
- Keeping custom metric dimension cardinality low.
- Creating only purposeful dashboards and alarms.
- Using aggregated metrics instead of logging every operation as a separate metric.
- Reviewing telemetry volume after traffic growth or enabling new instrumentation.

Do not cut observability to the point where incidents cannot be diagnosed. The goal is collecting enough data to protect SLAs at predictable cost.

## 17. Process for Building Observability for Java Lambda

Implement in this sequence:

1. **Define operational targets:** latency SLAs, error rates, throughput, backlog, and availability.
2. **Standardize logs:** JSON fields, `requestId`, `eventId`, `correlationId`, `level`, and `errorCode`.
3. **Enable standard metrics:** track `Invocations`, `Errors`, `Duration`, `Throttles`, and concurrency.
4. **Add essential custom metrics:** measure only business outcomes absent from standard metrics.
5. **Build dashboards:** traffic, reliability, latency, dependencies, and resources.
6. **Configure alarms:** tied to concrete actions and SLO-based thresholds.
7. **Enable X-Ray or OTel:** trace invocations and critical dependencies.
8. **Propagate trace context:** across HTTP headers or message metadata per integration.
9. **Enable Lambda Insights:** when system metrics and resource diagnostics are needed.
10. **Verify permissions and retention:** roles, policies, log groups, sampling, and retention windows.
11. **Test failure modes:** timeouts, throttles, cold starts, duplicate messages, and slow dependencies.
12. **Measure cost:** log volume, trace sampling, custom metrics, and Insights telemetry.

## 18. Common Mistakes

**Logging only unstructured free text:** Hard to filter and correlate invocations. Standardize JSON logs and identifiers.

**Logging entire events:** Easily exposes sensitive data and inflates costs. Log only required metadata.

**Omitting retention settings:** Logs persist longer than needed and accumulate cost. Set retention based on investigation and compliance needs.

**Watching only `Errors`:** Misses throttling or backlogs. Also watch `Throttles`, concurrency, queue age, and `IteratorAge`.

**Watching only Average `Duration`:** Tail latency gets hidden. Use p95/p99 where SLAs require.

**Failing to propagate correlation/trace context:** Traces break across queues or other services. Propagate context explicitly and test integrations.

**Assuming active tracing captures every invocation:** Sampling drops some traces. Combine with logs and metrics.

**Duplicate instrumentation:** Auto-instrumentation and manual instrumentation can emit duplicate spans. Define instrumentation scope clearly.

**Ignoring memory:** Functions can approach memory limits even though standard metrics do not expose granular usage. Use Lambda Insights when needed.

**Alarms detached from SLOs:** Too many noisy alerts or missed real incidents. Pick thresholds based on service behavior and objectives.

**Excessive dimension cardinality:** Using `requestId` or `orderId` as a dimension spawns numerous distinct metrics. Keep IDs in logs/traces and keep dimensions bounded.

**Ignoring the event source:** The function looks healthy while the queue backlog grows. Monitor the broker, event source mapping, and DLQ too.

## 19. Pre-Production Observability Checklist for Lambda

- [ ] Log group is properly created and the execution role has least-privilege log-writing permissions.
- [ ] Logs are structured and include `requestId` or `eventId` as appropriate.
- [ ] Secrets, tokens, and sensitive payloads are never logged.
- [ ] Log retention is explicitly configured.
- [ ] `Invocations`, `Errors`, `Duration`, and `Throttles` are monitored.
- [ ] Concurrency metrics and queue/stream-specific metrics are in place.
- [ ] Dashboards cover traffic, reliability, latency, and resources.
- [ ] Alarms are tied to SLOs with clear owners/teams responsible.
- [ ] Custom metrics use reasonable namespaces and bounded dimension cardinality.
- [ ] Active tracing or OTel is configured where needed.
- [ ] Trace context propagates across critical boundaries.
- [ ] Sampling balances diagnostic coverage and cost.
- [ ] Lambda Insights is enabled when CPU, memory, network, and `/tmp` metrics are needed.
- [ ] Execution role has matching permissions to emit traces/telemetry.
- [ ] Logs, metrics, traces, and alarms have been tested under failure scenarios.
- [ ] A single invocation can be traced via `requestId`/`correlationId` across all signals.
- [ ] Costs for logs, metrics, traces, and telemetry are reviewed periodically.

## Conclusion

CloudWatch provides logs, metrics, dashboards, and alarms to track Lambda behavior over time. X-Ray illuminates request paths and latency across dependent services. Lambda Insights adds system-level metrics such as memory, CPU, network, and ephemeral filesystem usage. When linked by request ID, event ID, correlation ID, and trace context, these three tools move operations teams from anomaly detection to root-cause identification.

For Java Lambda, standardize structured logs, select SLO-reflecting metrics, instrument key dependencies, propagate trace context across messages, and enable Lambda Insights when resource telemetry is needed. Combine least-privilege access, retention, sampling, and cardinality control so observability is deep enough for production while keeping costs manageable.
