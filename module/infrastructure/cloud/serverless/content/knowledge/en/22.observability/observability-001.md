# Designing Structured Logs for Functions and Workflows

In a serverless application, a single request may pass through an API gateway, a Java function, a queue, multiple workers, and a workflow spanning many executions. Each function typically lives only for a single invocation; a workflow may pause, wait for an event, and then resume in a different execution environment. If logs are just scattered lines of text like “started”, “failed”, or “done”, operations teams struggle to piece the events together into a complete story.

Structured logging solves this problem by recording each event as fields with stable names and data types, typically emitted as JSON. Logs can be searched by service, function, invocation, trace, correlation ID, workflow run, step, event type, and outcome. When designed properly, teams can answer critical questions: where a request went, which step was slow, how many times a message was retried, where a workflow is paused, whether a function cold start or a dependency was the cause, and which deployment version introduced an error.

In the **CLOUD_SERVERLESS** module, learners develop Java functions triggered by HTTP, messages, or events while handling state, permissions, retries, idempotency, cold starts, scaling, and cost. This lesson focuses on how to design a log schema, emit logs in Java functions, propagate context across queues, and observe multi-step workflows.

## 1. Why Do Functions and Workflows Need Structured Logs?

A single function may process a request in tens of milliseconds. However, a serverless process can span multiple components:

1. The API gateway receives an HTTP request.
2. A function authenticates and records the request.
3. The function sends a message to a queue.
4. A worker receives the message and calls a database.
5. The worker calls an external service.
6. A workflow waits for a callback or a timer.
7. Another function continues and completes the business operation.

Each step has its own invocation ID, timestamp, runtime, and possibly even its own Region. A log line containing only “payment failed” is insufficient to identify which payment, which workflow, which retry attempt, or which dependency caused the failure.

Structured logs help:

- Find all events belonging to the same request or workflow.
- Distinguish a new invocation from a retry of the same message.
- Measure duration by function, step, and dependency.
- Build dashboards and alerts from stable fields.
- Compare behavior across deployment versions or Regions.
- Investigate errors without logging the entire request/event payload.
- Aggregate throughput, retries, failures, and operational cost.

Structured logs do not replace traces, metrics, audit logs, or business databases. Each type of telemetry serves a different purpose and needs to be linked using appropriate IDs.

## 2. Distinguishing Logs, Metrics, Traces, and Audit Events

| Data Type | Question Answered | Examples |
|---|---|---|
| Log | What happened at a point in time? | Function received message, workflow step failed |
| Metric | How often or how long did it happen? | Invocation count, p95 duration, retry rate |
| Trace | Which services/spans did a request pass through? | API → function → queue producer → worker → database |
| Audit event | Who performed a critical action and what was it? | User changed permissions, administrator deleted a resource |

A log event typically has a timestamp, severity, service, and event name. Metrics aggregate many executions into a series of numerical measurements. Traces describe parent-child relationships between spans. Audit events require integrity, retention, and access controls according to audit requirements.

Do not use logs as the source of truth to decide whether an order has been paid. Logs can arrive late, be sampled, hit volume limits, or fail to reach the sink when the runtime terminates. Business state must reside in a database, event store, or workflow engine with appropriate durability.

## 3. Designing a Consistent JSON Schema

A log event should be an object with stable fields. Commonly used fields:

| Field | Meaning | Example |
|---|---|---|
| timestamp | Time the event occurred in UTC | 2026-11-17T10:15:30.123Z |
| severity | Log level | INFO, WARN, ERROR |
| service.name | Service name | orders-service |
| service.version | Deployment version | 2.4.1 |
| deployment.environment | Environment | production |
| cloud.region | Execution Region | ap-southeast-1 |
| faas.name | Function name | ProcessOrder |
| faas.invocation_id | ID of the function invocation | inv-8f21 |
| event.name | Log event name | order.processing.started |
| trace_id | Distributed trace ID | 4bf92f... |
| span_id | Current span ID | 00f067... |
| correlation_id | ID linking a business flow | corr-72a1 |
| workflow.id | Workflow identifier | order-fulfillment |
| workflow.run_id | A single workflow run | run-9c12 |
| workflow.step | Step name | reserve-inventory |
| message.id | Transport message ID | msg-183 |
| event.id | Stable business event ID | evt-720 |
| outcome | Processing step outcome | success, failure, retry |
| duration_ms | Processing duration | 84 |
| retry.attempt | Attempt count | 2 |
| error.code | Stable error code | INVENTORY_TIMEOUT |

Not every log needs every field. Emit only the fields that are meaningful for that event; non-applicable fields can be omitted instead of producing objects containing dozens of null values.

### JSON Example

~~~json
{
  "timestamp": "2026-11-17T10:15:30.123Z",
  "severity": "INFO",
  "schema_version": 1,
  "service": {
    "name": "orders-service",
    "version": "2.4.1"
  },
  "deployment": {
    "environment": "production"
  },
  "cloud": {
    "region": "ap-southeast-1"
  },
  "faas": {
    "name": "ProcessOrder",
    "invocation_id": "inv-8f21"
  },
  "event": {
    "name": "order.processing.started",
    "id": "evt-720"
  },
  "correlation_id": "corr-72a1",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "workflow": {
    "id": "order-fulfillment",
    "run_id": "run-9c12",
    "step": "reserve-inventory"
  },
  "retry": {
    "attempt": 2
  },
  "message": "Order processing started"
}
~~~

A schema can use nested objects or flat fields. What matters is standardizing naming and data types across functions so queries do not have to handle multiple variations.

## 4. Naming Events by Convention

An event name should describe what happened, not a vague phrase. Use a consistent convention such as domain.object.action or domain.operation.outcome.

Examples:

| Event name | Meaning |
|---|---|
| function.invocation.started | An invocation started |
| function.invocation.completed | Invocation completed |
| function.invocation.failed | Invocation failed |
| order.validation.completed | Order validation completed |
| order.processing.started | Order processing started |
| inventory.reservation.failed | Inventory reservation failed |
| message.received | Consumer received a message |
| message.retry.scheduled | Message will be retried |
| workflow.started | Workflow started |
| workflow.step.completed | A step completed |
| workflow.waiting | Workflow is waiting for an event/timer |
| workflow.completed | Workflow completed |
| workflow.failed | Workflow failed |

Do not use event names that vary with data, such as order.12345.created. Dynamic values belong in separate fields, such as order.id or event.id. Embedding IDs in event names makes querying harder and creates unnecessary event types.

### Event Name and Message

An event name is a machine-readable code that remains stable across versions. A message is a human-readable descriptive sentence. For example, event.name can be inventory.reservation.failed while message is “Inventory service did not respond before deadline”.

Do not use free-form message text as the primary alerting criterion because the text can change across code versions or languages. Use event.name, error.code, outcome, and severity.

## 5. Severity and Rules for Choosing Log Levels

| Level | When to Use | Examples |
|---|---|---|
| TRACE | Very fine-grained detail, enabled only for controlled diagnostics | An internal branching decision |
| DEBUG | Development or diagnostic details not needed routinely in production | Cache key selection decision |
| INFO | Normal lifecycle milestones with operational value | Invocation started, workflow completed |
| WARN | Abnormal situation that was handled or is recoverable | Retry scheduled, fallback used |
| ERROR | An operation or invocation did not complete as requested | Database write failed, workflow step errored |
| FATAL (if supported by the platform) | Application cannot continue initializing or serving | Critical runtime bootstrap failure |

Do not log every request as ERROR just because the HTTP status is 4xx. A malformed request may be normal client behavior. Similarly, a retry that succeeds after a transient error can be logged as WARN rather than ERROR at the invocation level, while still emitting a retry metric.

Choose levels based on impact and actionability. If every line is ERROR, alerts lose meaning and log costs increase.

Standard SLF4J has the levels TRACE, DEBUG, INFO, WARN, and ERROR; FATAL is not a standard SLF4J level. If a system needs to distinguish fatal events, log ERROR with a field such as error.severity=fatal or use a custom convention supported by the backend.

## 6. Java Structured Logging with SLF4J

SLF4J 2.x provides a fluent logging API that lets you attach key-value pairs to an event. The logging backend and encoder must be configured to emit those pairs as JSON fields. Simply writing a string with equals signs does not automatically turn a log into structured JSON.

Example:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class OrderFunction {
    private static final Logger log =
            LoggerFactory.getLogger(OrderFunction.class);

    public void process(
            String invocationId,
            String correlationId,
            String eventId) {

        log.atInfo()
            .addKeyValue("event.name", "order.processing.started")
            .addKeyValue("faas.name", "ProcessOrder")
            .addKeyValue("faas.invocation_id", invocationId)
            .addKeyValue("correlation_id", correlationId)
            .addKeyValue("event.id", eventId)
            .log("Order processing started");
    }
}
~~~

Use this API with SLF4J 2.x and a compatible backend. If the project still uses SLF4J 1.x, choose an appropriate logging library or adapter rather than copying the example verbatim.

### Configuring the JSON Encoder

A Java application can use Logback together with a compatible JSON encoder to output timestamp, level, logger, message, and key-value fields as JSON. Conceptual configuration example:

~~~xml
<configuration>
  <appender name="JSON_CONSOLE"
            class="ch.qos.logback.core.ConsoleAppender">
    <encoder class="net.logstash.logback.encoder.LogstashEncoder">
      <includeMdc>true</includeMdc>
    </encoder>
  </appender>

  <root level="INFO">
    <appender-ref ref="JSON_CONSOLE"/>
  </root>
</configuration>
~~~

You need to add an encoder dependency compatible with your Logback version and verify the actual output. Some encoders include MDC in JSON while handling SLF4J fluent key-value pairs according to their own configuration/version. Write integration tests for the output format instead of assuming the XML above automatically covers every field.

### Expected JSON Output

The result should be one JSON object per line, for example:

~~~json
{
  "@timestamp": "2026-11-17T10:15:30.123Z",
  "level": "INFO",
  "logger_name": "OrderFunction",
  "message": "Order processing started",
  "event.name": "order.processing.started",
  "faas.name": "ProcessOrder",
  "faas.invocation_id": "inv-8f21",
  "correlation_id": "corr-72a1",
  "event.id": "evt-720"
}
~~~

Do not use pretty-printed multi-line JSON for the production console if the collector expects one event per line. A multi-line record can be split into multiple log events or merged incorrectly during collection.

## 7. Emitting Logs at Function Lifecycle Milestones

An invocation typically has these milestones:

1. The runtime receives an event and starts the invocation.
2. The function parses and validates input.
3. The function executes business logic.
4. The function calls dependencies or sends messages.
5. The function returns a result or fails.
6. The runtime ends the invocation.

It is not necessary to emit a log for every line of code. Choose milestones that help operations understand progress and measure duration. A short function may only need started/completed/failed and dependency failures; a complex function may need events for each phase.

### Function Example with Duration

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class OrderHandler {
    private static final Logger log =
            LoggerFactory.getLogger(OrderHandler.class);

    public OrderResponse handle(
            OrderRequest request,
            String invocationId,
            String correlationId) {

        long startedAt = System.nanoTime();
        String outcome = "success";

        log.atInfo()
            .addKeyValue("event.name", "function.invocation.started")
            .addKeyValue("faas.name", "CreateOrder")
            .addKeyValue("faas.invocation_id", invocationId)
            .addKeyValue("correlation_id", correlationId)
            .log("Invocation started");

        try {
            validate(request);
            OrderResponse response = createOrder(request);

            log.atInfo()
                .addKeyValue("event.name", "order.created")
                .addKeyValue("faas.invocation_id", invocationId)
                .addKeyValue("correlation_id", correlationId)
                .addKeyValue("outcome", "success")
                .log("Order created");

            return response;
        } catch (RuntimeException ex) {
            outcome = "failure";

            log.atError()
                .setCause(ex)
                .addKeyValue("event.name", "function.invocation.failed")
                .addKeyValue("faas.invocation_id", invocationId)
                .addKeyValue("correlation_id", correlationId)
                .addKeyValue("error.type", ex.getClass().getSimpleName())
                .addKeyValue("error.code", "ORDER_PROCESSING_FAILED")
                .log("Invocation failed");

            throw ex;
        } finally {
            long durationMs =
                    (System.nanoTime() - startedAt) / 1_000_000;

            log.atInfo()
                .addKeyValue("event.name", "function.invocation.finished")
                .addKeyValue("faas.invocation_id", invocationId)
                .addKeyValue("outcome", outcome)
                .addKeyValue("duration_ms", durationMs)
                .log("Invocation finished");
        }
    }

    private void validate(OrderRequest request) {
        // Validate request.
    }

    private OrderResponse createOrder(OrderRequest request) {
        // Execute business operation.
        return new OrderResponse();
    }
}
~~~

This is a log design example; the request, response, and business types are illustrative classes. Logging exception causes must comply with data protection policies because stack traces or exception messages may contain sensitive information. If this cannot be guaranteed, log only error type/code to the general-purpose sink and route redacted details to a separate diagnostic sink.

Use System.nanoTime() to measure duration because it is a monotonic clock. Do not subtract two wall-clock values if the system clock may synchronize or adjust while the invocation is running.

## 8. Differences Between Invocation ID, Correlation ID, and Trace ID

These three IDs solve three different problems:

| ID | Scope | Used For |
|---|---|---|
| Invocation ID | A single function execution | Finding logs of one exact invocation |
| Correlation ID | A business request/flow across multiple services | Grouping events belonging to the same business flow |
| Trace ID | A distributed trace | Linking spans by tracing relationships |

An HTTP request may create an invocation ID for an API function, which then enqueues a message. The worker receiving the message will have a different invocation ID. The correlation ID can be preserved throughout to connect the business flow. The trace ID is typically propagated via W3C Trace Context or the platform's tracing mechanism; a workflow spanning hours or days may have multiple traces or trace segments linked to the same workflow run.

Do not use the invocation ID in place of the correlation ID because every retry is a new invocation. Do not construct a trace ID by reusing an order ID; trace IDs must follow the tracing format and carry no business meaning.

### Where Should Correlation ID Be Generated?

Prefer generating a random ID at the gateway or first service if the request does not already have a trusted ID. If a client sends a correlation ID, validate its format/length and apply a policy to prevent clients from intentionally polluting logs. A correlation ID is not a credential and does not prove user identity.

### W3C Trace Context

W3C Trace Context uses headers such as traceparent and tracestate to propagate trace information between compliant services. OpenTelemetry instrumentation can automatically inject/extract context. For queues, context can be passed through message attributes or SDK propagation mechanisms.

Do not put access tokens, emails, or payloads into trace baggage. Trace context links telemetry; authorization must still rely on separate credentials and policies.

## 9. Propagating Context Through Queues and Events

An HTTP request and a queue consumer do not run in the same call stack. The producer needs to pass required metadata in message attributes or an envelope so the consumer can correlate logs.

A message envelope might look like:

~~~json
{
  "event_id": "evt-720",
  "event_type": "OrderCreated",
  "schema_version": 2,
  "correlation_id": "corr-72a1",
  "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
  "occurred_at": "2026-11-17T10:15:30Z",
  "data": {
    "order_ref": "order-42"
  }
}
~~~

The envelope illustrates metadata and a single business reference. Do not embed credentials or full customer data in logs. If using separate message attributes, keep the same field names and conventions across producer and consumer.

The consumer should log:

- The transport's message.id.
- The business event's event.id.
- correlation_id.
- trace_id/span_id if the context is valid.
- retry attempt or receive count if provided by the source.
- event.name, outcome, and duration.

If a message is redelivered, the message ID may stay the same during queue redelivery, while the event ID remains the stable key to identify the business event across different transport messages.

## 10. Managing MDC and Thread Reuse

SLF4J/Logback MDC allows attaching fields such as invocation ID, correlation ID, and function name to multiple log statements. However, in a serverless environment, a thread may be reused for the next invocation. If the context is not cleaned up, logs from the new invocation may carry IDs from the previous invocation.

Context management example:

~~~java
import org.slf4j.MDC;

public final class InvocationLogging {

public Response handle(Request request, String invocationId) {
    String previousInvocation = MDC.get("faas.invocation_id");
    String previousCorrelation = MDC.get("correlation_id");

    try {
        MDC.put("faas.invocation_id", invocationId);
        MDC.put("correlation_id", request.correlationId());

        return process(request);
    } finally {
        restoreMdc("faas.invocation_id", previousInvocation);
        restoreMdc("correlation_id", previousCorrelation);
    }
}

private static void restoreMdc(String key, String previousValue) {
    if (previousValue == null) {
        MDC.remove(key);
    } else {
        MDC.put(key, previousValue);
    }
}
}
~~~

Saving and restoring previous values works well when code is called inside an existing context. If the framework provides a dedicated request-scoped context or logging context, prefer the framework's official mechanism.

### Async Execution

MDC is typically bound to a thread. When offloading work to another executor, context may not propagate automatically. Use an executor with context propagation or capture/restore MDC around the task. With OpenTelemetry, use the Context propagation API or corresponding instrumentation.

Do not copy the entire context uncontrollably to other threads. Propagate only the required fields and ensure cleanup in finally to prevent context leakage between tasks.

## 11. Structured Logs for Multi-Step Workflows

A workflow can run longer than the lifetime of a single function invocation. It may pause waiting for a timer, callback, or message, and then resume in another function. Therefore, invocation ID alone is not enough to link the entire workflow.

Use dedicated fields:

- workflow.id: workflow type or definition identifier.
- workflow.run_id: a specific execution.
- workflow.step: current step name.
- workflow.state: before/after state if applicable.
- workflow.attempt: step attempt count.
- workflow.correlation_id: business flow ID.
- workflow.parent_run_id: parent run if there is a subworkflow.
- workflow.event_id: event that resumed the workflow.

Common event names:

| Event | Additional Fields | Purpose |
|---|---|---|
| workflow.started | input_ref, definition_version | Execution started |
| workflow.step.started | step, attempt | A step started |
| workflow.step.completed | step, duration_ms, outcome | Step completed |
| workflow.step.failed | step, error.code, retryable | Step failed |
| workflow.retry.scheduled | step, attempt, next_attempt_at | Retry scheduled |
| workflow.waiting | wait_type, deadline | Waiting for timer/callback/event |
| workflow.resumed | resume_event_id | Resumed after waiting |
| workflow.compensation.started | compensation_step | Compensation started |
| workflow.completed | duration_ms, outcome | Workflow ended |
| workflow.failed | failed_step, error.code | Workflow failed |

### State Transition Example

~~~json
{
  "timestamp": "2026-11-17T10:16:02.400Z",
  "severity": "INFO",
  "event.name": "workflow.step.completed",
  "workflow.id": "order-fulfillment",
  "workflow.run_id": "run-9c12",
  "workflow.step": "reserve-inventory",
  "workflow.state.from": "RESERVING",
  "workflow.state.to": "INVENTORY_RESERVED",
  "workflow.attempt": 1,
  "correlation_id": "corr-72a1",
  "duration_ms": 126,
  "outcome": "success"
}
~~~

State transition logs should reflect results already committed by the workflow engine or state store. Do not log “completed” before a durable state transition is confirmed. If you log before the transaction and the transaction rolls back, telemetry will describe a state that never existed.

## 12. Workflow Logs and Workflow Execution History

Many workflow engines maintain a separate execution history or event history. For example, the engine may record state entered, task scheduled, task succeeded, retry, and execution failed. This data is useful to see where orchestration went.

Application logs are still needed to record business details that the workflow engine does not know, such as validation rules, dependency operations, error categories, and business outcomes. Both sources should be linked via workflow run ID, step name, correlation ID, and trace context if available.

Do not duplicate the entire execution history into application logs. Select business events that need searching or alerting; use workflow engine history to inspect detailed orchestration progress.

### Logs Are Not Workflow State

Do not use the last log line to determine whether a workflow completed. Logs can be delayed or missing. Use execution status or the state store as the source of truth. Logs serve observability and investigation.

## 13. Logging Retries, Timeouts, and Idempotency

A message or workflow step may execute multiple times. Logs need to show which attempt it is, which errors are retryable, and what the final outcome is.

Example:

~~~json
{
  "timestamp": "2026-11-17T10:17:11.200Z",
  "severity": "WARN",
  "event.name": "message.retry.scheduled",
  "service.name": "orders-worker",
  "faas.invocation_id": "inv-b190",
  "message.id": "msg-183",
  "event.id": "evt-720",
  "correlation_id": "corr-72a1",
  "retry.attempt": 3,
  "retry.max_attempts": 5,
  "retry.delay_ms": 4000,
  "error.code": "PAYMENT_PROVIDER_TIMEOUT",
  "outcome": "retry"
}
~~~

Key fields:

- retry.attempt: attempt number with a clear definition, e.g., current attempt starting at 1.
- retry.max_attempts: configured limit.
- error.code: stable error code, not an exception message.
- retry.delay_ms or next_attempt_at: time until retry.
- event.id/idempotency reference: links the same business operation.
- outcome: retry, success, quarantined, or terminal_failure.

Do not log an idempotency key if it contains identifying data. Use a normalized reference or pseudonymous key. Log duplicate detected when a consumer receives an already completed event again; distinguish it from a new business event for the same aggregate.

## 14. Batch Logging: One Log for the Batch, One Log for Each Failed Record

A batch consumer may process thousands of records. Logging INFO for every successful record creates high log volume and increases cost. A practical strategy:

- One INFO log when the batch starts, including batch size and source.
- One INFO log when the batch finishes, including success count, failure count, and duration.
- One WARN/ERROR log per failed record requiring investigation, with message reference, event type, and error code.
- One log for duplicate detection if the duplicate rate needs measurement.
- Separate metrics for succeeded/failed record counts; do not use logs as the primary counter.

Batch summary example:

~~~json
{
  "event.name": "batch.processing.completed",
  "faas.name": "ProcessOrders",
  "faas.invocation_id": "inv-8f21",
  "batch.size": 100,
  "batch.succeeded": 97,
  "batch.failed": 3,
  "batch.duplicate": 2,
  "duration_ms": 1840,
  "outcome": "partial_failure"
}
~~~

Record failure:

~~~json
{
  "event.name": "message.processing.failed",
  "message.id": "msg-183",
  "event.id": "evt-720",
  "error.code": "INVENTORY_TIMEOUT",
  "retry.attempt": 2,
  "outcome": "retry"
}
~~~

Do not log the message body. With partial batch responses, an invocation may be considered successful even though some records are marked for retry; custom record-level metrics are necessary.

## 15. Cold Start and Startup Logging

Cold start is the time spent initializing the runtime, class loading, dependency injection, SDK clients, and application context before handling the first invocation of an execution environment. If you only log invocation duration, it can be hard to distinguish startup latency from business processing time.

You can log separate milestones:

- runtime.initialization.started
- application.bootstrap.completed
- dependency.client.initialized
- function.invocation.started
- function.invocation.finished

If the platform provides init/cold start metrics or logs, use that source. Do not infer cold start solely from high duration because slow dependencies or network issues can produce similar latency. If using a static flag to detect the first call in an environment, explicitly document that this is only a runtime lifecycle heuristic and must be verified against the platform.

Startup event example:

~~~json
{
  "event.name": "application.bootstrap.completed",
  "service.name": "orders-function",
  "service.version": "2.4.1",
  "duration_ms": 420,
  "outcome": "success"
}
~~~

Do not log full client initialization details containing endpoints/credentials. Startup logs should help identify slow initialization phases and application version.

## 16. Correlating Logs with OpenTelemetry Traces and Metrics

Structured logs can include trace_id and span_id so operators can open the corresponding trace. Traces show relationships between services; logs provide event details; metrics reveal trends and impact severity.

A typical flow:

~~~mermaid
flowchart LR
    A[HTTP Gateway] --> B[Java Function]
    B --> C[Queue]
    C --> D[Worker Function]
    D --> E[Database]
    D --> F[External API]
    B -. log + trace IDs .-> L[Log platform]
    D -. log + trace IDs .-> L
    B -. spans .-> T[Trace backend]
    D -. spans .-> T
    B -. metrics .-> M[Metrics backend]
    D -. metrics .-> M
~~~

When investigating latency, use metrics to find when p95 increased, traces to locate the slow span, and logs to read the error code or workflow state. Keep trace ID/span ID in logs when instrumentation provides a valid context.

Do not generate trace IDs manually if the OpenTelemetry SDK already manages context. Do not put user IDs or order IDs into metric labels just to find logs; use trace/log search or protected fields instead.

## 17. Schema Evolution and Compatibility

Log schemas change over time as teams add, rename, or change field types. If dashboards depend on old fields, a small change can break queries.

Principles:

- Use schema_version or a versioning convention for critical events.
- Do not silently change field types, such as changing duration_ms from number to string.
- Prefer adding optional fields instead of renaming existing fields.
- Keep event.name stable and do not embed dynamic values in the name.
- Document the meaning of retry.attempt, duration_ms, and outcome.
- Have tests verifying schema output.
- When deprecating a field, maintain a compatibility period for dashboards and consumers to update.

For example, duration is always an integer in milliseconds; timestamp is always UTC ISO-8601; severity uses a fixed set of values. These simple conventions keep queries and alerts resilient.

## 18. Log Pipelines in Serverless

In serverless environments, applications typically write to stdout/stderr or a provider logging API. A runtime/agent collects logs and forwards them to a log service. From there, logs can be filtered, enriched, indexed, archived, or forwarded to a SIEM.

~~~mermaid
flowchart TD
    A[Java function / workflow step] --> B[Structured JSON]
    B --> C[Runtime log capture]
    C --> D[Cloud log service]
    D --> E[Parse / enrich / redact]
    E --> F[Search and dashboard]
    E --> G[Alerting]
    E --> H[Archive / SIEM]
~~~

Points to verify:

- Each invocation can produce many log records; avoid excessive logging on the hot path.
- Log delivery and ingestion may be asynchronous; do not assume records appear immediately.
- The runtime may enforce event size limits or truncate long logs.
- Log aggregators may parse JSON differently depending on format and multiline handling.
- Structured output should be one JSON object per line.
- Sampling or filtering must preserve critical errors and workflow terminal events.
- You may need to enrich service/version/region from runtime metadata rather than hardcoding them.

Do not wait for log export to complete before returning an HTTP response if doing so increases latency. The logging path should not block business logic under normal conditions, but you must understand the runtime's buffering/flushing policy to avoid losing logs if the process terminates abruptly.

## 19. Sampling, Volume, and Cost

Serverless charges by invocation and duration, and observability services may charge by ingestion, retention, query, or trace volume. Overly verbose logs both increase cost and make important signals harder to find.

Control measures:

- INFO for operationally valuable milestones.
- DEBUG enabled only temporarily or within a narrow scope.
- Batch summaries instead of per-record success logs.
- Do not log polling heartbeats too frequently unless necessary.
- Limit field sizes and exception details.
- Use deliberate sampling for high-frequency repetitive events.
- Retain all terminal failures, security-relevant events, and key workflow state transitions per policy.
- Monitor bytes ingested, retention, and query costs.

Log sampling is not the same as trace sampling. Randomly dropping every event can break the workflow trail needed for investigation. Prefer keeping start/end events, failures, retries, and important state transitions; reduce repetitive detail in high-volume success events.

## 20. Ensuring Logging Does Not Impede Functions

Logging is an operational dependency. If a synchronous log appender waits on the network or a slow backend, the function can suffer increased latency or timeouts. If an async appender uses a small buffer, logs may be dropped during bursts; if the buffer is too large, memory pressure increases.

Evaluate:

- Are console logging and the platform collector the recommended path?
- Does the encoder serialize JSON synchronously with significant overhead?
- What queue limit and drop policy does the async appender have?
- When the buffer is full, are logs dropped or is the thread blocked?
- Does process shutdown flush buffers within runtime limits?
- Do large exception logs increase memory/serialization time?

Do not log large payloads inside tight loops. Do not make synchronous network calls to a log service in every invocation unless the architecture and latency budget allow it.

## 21. Testing Structured Logs

Unit tests should verify event names and key fields; integration tests should verify the actual JSON output of the logging backend and runtime collector.

Logger/appender-level test example:

~~~java
@Test
void writesStructuredInvocationFields() {
    handler.handle(testRequest, "inv-test-1", "corr-test-1");

    String output = testAppender.lastJsonEvent();

    assertJsonField(output, "event.name", "function.invocation.started");
    assertJsonField(output, "faas.invocation_id", "inv-test-1");
    assertJsonField(output, "correlation_id", "corr-test-1");
}
~~~

This is pseudocode for a project's test appender. Verify:

- Output is valid JSON.
- Each event is on its own line.
- UTC timestamp and severity match the schema.
- Invocation ID and correlation ID do not leak between two requests.
- MDC is cleaned up after both success and exception paths.
- Async tasks receive the correct context.
- Workflow run ID and step name are logged accurately.
- Retry attempt increments properly.
- Batch summary matches actual record counts.
- Error logs include error code/type and do not expose sensitive data.
- Schema version and field types do not change unexpectedly.

### Testing Thread/Context Reuse

Run two consecutive invocations on the same thread in a test or appropriate runtime environment. The second invocation must not contain the correlation ID, workflow ID, or request ID from the first invocation. Also test the exception branch to confirm cleanup always runs.

### Testing Workflows

Run a workflow through multiple steps, retries, and wait/resume cycles. Confirm all events share the same workflow.run_id and correlation_id; invocation ID changes properly per function call; trace ID/span ID follow the propagation strategy; state transition logs reflect committed state.

## 22. Dashboards and Alerts from Structured Fields

A dashboard can group by:

- service.name and service.version.
- faas.name and cloud.region.
- event.name and severity.
- outcome and error.code.
- workflow.id, workflow.step, and workflow.run_id.
- retry.attempt and message source.
- duration_ms and dependency name.

Alerts should be based on actionable conditions:

| Signal | Example Condition | Action |
|---|---|---|
| Function failure rate | Failed invocation rate exceeds threshold | Check version, dependencies, and runtime |
| Workflow terminal failure | New workflow.failed event detected | Open execution history and trace |
| Increasing retries | Retry rate rises continuously | Check downstream and poison messages |
| Step latency | p95 of a workflow step increases | Check the step's dependencies |
| Queue backlog | Oldest message age exceeds SLA | Check consumer capacity |
| Cold start/init | Init duration increases after deploy | Check artifact and initialization |
| Log ingestion drop | Collector reports drops or quota limit | Reduce volume or increase capacity |

Alerts should not send entire log messages or payloads to chat/email. Send the event name, error code, service, Region, timestamp, and a controlled link to the log/trace.

## 23. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Logging only free-form text | Hard to filter and aggregate | Use a stable JSON schema |
| Using invocation ID for the whole workflow | Cannot connect retries/resumes | Separate invocation, correlation, and workflow run IDs |
| Embedding order ID in event name | Creates dynamic event types and hard queries | Put IDs in separate fields |
| Logging full requests/events | High log volume and increased data risk | Allowlist metadata |
| Logging INFO for every record | Increases cost and noise | Batch summaries and record-level failures |
| Not logging retry attempts | Hard to distinguish duplicates from new operations | Log attempt, event ID, and message reference |
| Not clearing MDC | Old context leaks into another invocation | Restore/clear in finally |
| Assuming MDC propagates automatically across executors | Async logs have missing or wrong correlation | Use context propagation |
| Keeping one trace span across a multi-day workflow | Long spans, hard to manage and runtime-dependent | Span per step, linked by workflow run ID |
| Logging completed before commit | Telemetry reports unpersisted state | Log after the transition is confirmed |
| Using logs as the source of truth | Wrong state when logs are delayed or dropped | Database/workflow engine is the source of truth |
| Not versioning the schema | Dashboards break when fields change | Schema version and compatibility tests |
| Logging too much on the hot path | Increases latency and cost | Reduce volume, deliberate sampling |
| Monitoring only invocation Errors | Misses partial batch record failures | Custom record-level metrics |

## 24. Structured Logging Design Process

When designing logs for a Java function or workflow:

1. **Define operational goals:** do you need request investigation, latency measurement, retry tracking, or state transitions?
2. **Choose a common schema:** timestamp, severity, service, environment, Region, event name, and version.
3. **Define IDs:** invocation ID, correlation ID, trace ID, workflow run ID, event/message ID.
4. **Set stable event names:** use event names describing action/outcome, keeping IDs in separate fields.
5. **Select levels:** INFO for key milestones, WARN for retries/fallbacks, ERROR for failures.
6. **Configure JSON encoder:** verify key-value pairs are actually emitted as JSON.
7. **Propagate context:** across HTTP, queues, events, and workflow resumes.
8. **Manage MDC:** cleanup/restore and propagate context across async executors.
9. **Design workflow events:** started, step transition, waiting, resumed, retry, completed/failed.
10. **Control volume:** batch summaries, sampling, and purpose-driven retention.
11. **Test the schema:** JSON format, field types, context isolation, retries, and workflow correlation.
12. **Set up dashboards/alerts:** use stable fields and actionable signals.

## 25. Production Checklist

- **Schema:** includes UTC timestamp, severity, service, version, environment, Region, and event name.
- **Naming:** stable event names; dynamic IDs placed in separate fields.
- **Invocation:** every invocation-related log event has the accurate invocation ID.
- **Correlation:** business flows preserve correlation ID across functions, queues, and workflows.
- **Tracing:** trace ID/span ID propagated via W3C/OpenTelemetry or provider mechanisms.
- **Workflow:** includes workflow run ID, step, attempt, and state transitions.
- **Retry:** includes retry attempt, error code, outcome, and message/event reference.
- **Batch:** includes batch summary and record-level failure metrics.
- **Java:** SLF4J/backend/JSON encoder compatible; fluent key-values actually become JSON fields.
- **MDC:** context cleaned up/restored after both success and failure; async propagation verified.
- **Cold start:** startup/init telemetry separated from business duration.
- **Privacy:** do not log tokens, secrets, raw payloads, or PII outside policy.
- **Delivery:** understand buffering, flushing, truncation, and log collector behavior.
- **Cost:** volume, sampling, retention, and ingestion monitored.
- **Testing:** includes schema tests, context reuse tests, async tests, and workflow resume tests.
- **Operations:** dashboards and alerts use stable fields, without sending payloads in notifications.

## 26. Conclusion

Structured logging enables Java functions and serverless workflows to produce operational data that can be searched, correlated, and aggregated. A stable schema must distinguish invocation ID, correlation ID, trace ID, message/event ID, and workflow run ID; the event name describes the event, while dynamic IDs belong in separate fields.

In functions, log invocation, business, and dependency milestones with appropriate duration/outcome fields. In long-running workflows, log state transitions by workflow run and step; do not rely on invocation ID to connect resumes. Propagate context through queues/events, manage MDC when threads are reused, and use OpenTelemetry to correlate logs with traces.

Logs must support observability rather than replace business state. Combine structured logs with metrics, traces, execution history, and audit stores; test schemas, context propagation, retries, and workflow resumes before production. When fields are stable, volume is controlled, and every event carries sufficient correlation context, teams can diagnose cold starts, dependency errors, duplicates, and workflow failures while keeping logs readable and costs reasonable.
