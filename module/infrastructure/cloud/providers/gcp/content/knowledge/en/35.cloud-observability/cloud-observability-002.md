# Cloud Logging, Log Entries, and Structured Logging

When a Java application runs on Google Cloud, logs are one of the first data sources that help operations teams understand what happened during a request, a deployment, or a background job. However, logs are only useful when they have a consistent structure, clearly identify their origin, and retain enough context for searching. A free-form line like "An error occurred" rarely helps investigation; a log entry with severity, event name, order ID, service, and trace can guide an operator to the exact request in just a few actions.

This lesson belongs to the **CLOUD_PROVIDERS_GCP** module. The module explores Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage, and databases. Learners practice selecting services, protecting resources, automating releases, and tracking reliability and cost. Within the scope of this lesson, we focus on Cloud Logging, the structure of a log entry, and how to emit structured logs from a Java application to support searching, analysis, and alerting.

## Objectives

After this lesson, you will be able to:

- Explain how Cloud Logging collects, stores, and routes logs.
- Identify the key components of a LogEntry.
- Distinguish between text logs, structured logs, and audit logs.
- Design JSON logs with clear severity, event names, and business context.
- Emit structured logs from a Java application and link logs with traces.
- Query logs in Logs Explorer and use logs for operational monitoring.
- Control sensitive data, access permissions, and log storage costs.

## 1. What Problem Does Cloud Logging Solve?

Cloud Logging is Google Cloud's managed logging service. It ingests logs from applications, infrastructure resources, and many Google Cloud services; and provides searching, querying, time-ordered log viewing, and routing logs to other storage or processing destinations.

An application can run across multiple environments:

- **Cloud Run:** logs written to container stdout and stderr are collected by the platform.
- **Google Kubernetes Engine (GKE):** container logs and system logs are collected according to the cluster's logging configuration.
- **Compute Engine:** Ops Agent can be installed to collect application logs, OS logs, and monitoring data from VMs.
- **Google Cloud services:** many services automatically generate platform logs and audit logs in Cloud Logging.

Cloud Logging centralizes these sources into a unified interface. Operators can filter by project, resource type, service name, severity level, timestamp, or fields inside the payload. This makes it possible to investigate an incident across multiple components without logging into individual machines to read separate log files.

### High-Level Log Flow

~~~mermaid
flowchart TD
    A["Java application and Google Cloud services"]
    B["stdout / stderr / agent / API"]
    C["Cloud Logging"]
    D["Log Router"]
    E["Log buckets and Logs Explorer"]
    F["BigQuery / Pub/Sub / Cloud Storage"]
    G["Log-based metrics and alerts"]
    A --> B --> C --> D
    D --> E
    D --> F
    E --> G
~~~

The application generates log events; the runtime or agent forwards events to Cloud Logging; Log Router applies routing configurations and filters to decide where to store or forward them. Logs Explorer is used to search and analyze stored logs. Log-based metrics can convert log patterns into time series for monitoring and alerting.

Not all logs come from the application. For example, audit logs record administrative activities or resource access, while application logs describe business and technical events emitted by the application. Distinguishing log sources helps answer the right question during an investigation.

## 2. The Log Entry as the Fundamental Data Unit

Cloud Logging represents each event as a **LogEntry**. A log entry has metadata describing the source, timestamp, and severity level, along with a payload containing the event details.

Common fields:

| Field | Meaning | Example or Note |
|---|---|---|
| logName | Name of the log within the project | projects/PROJECT_ID/logs/stdout |
| resource | Resource that produced the log | cloud_run_revision, k8s_container, gce_instance |
| timestamp | When the event occurred | Should reflect when the log originated |
| receiveTimestamp | When Cloud Logging received the log | Recorded by the ingestion system |
| severity | Severity level | INFO, WARNING, ERROR |
| insertId | Entry identifier within a log | Helps detect duplicate entries |
| labels | Metadata labels | Use for attributes with a bounded set of values |
| trace | Trace ID linked to Cloud Trace | Formatted as projects/PROJECT_ID/traces/TRACE_ID |
| spanId | Related span in the trace | Supports navigating from log to span |
| httpRequest | HTTP request details | Method, URL, status, latency, and size |
| operation | Information about a multi-log operation | Can group steps of the same operation |
| sourceLocation | Source code location | File, line, and function if provided |
| jsonPayload | Structured JSON payload | Suitable for application logs |
| textPayload | Plain text payload | Common for plain text log lines |
| protoPayload | Protocol buffer payload | Typically used for audit logs |

A LogEntry has one corresponding payload type; an application does not need to populate all three of jsonPayload, textPayload, and protoPayload for the same entry. With structured logging, the application emits JSON so Cloud Logging can parse it into fields. With standard text logs, the content typically resides in textPayload.

### How Metadata Differs from Payload

Metadata answers "where did the log come from?", "when did it happen?", and "how severe is it?". Payload answers "what event happened?" and carries business context.

For example, a Cloud Run log entry might have resource set to cloud_run_revision, severity set to ERROR, and timestamp reflecting when the request failed. The JSON payload might contain event set to payment.authorization_failed, orderId, and the payment gateway error code. By separating these two layers of data, operators can first filter all errors for a revision, and then narrow down errors belonging to a specific business event type.

### Monitored Resource

The resource field describes the monitored resource that emitted the log. The resource type determines which resource labels are available. Examples:

| Environment | Common Resource Type | Labels Available for Filtering |
|---|---|---|
| Cloud Run | cloud_run_revision | project_id, service_name, revision_name, location |
| GKE | k8s_container | project_id, location, cluster_name, namespace_name, pod_name, container_name |
| Compute Engine | gce_instance | project_id, instance_id, zone |

When logs are collected via platform integrations, resource information is usually attached automatically. Therefore, applications do not need to embed pod or revision names into every log line just to identify the source. If an application runs outside an integrated environment, choose an appropriate log delivery method and declare the resource properly so Cloud Logging classifies it accurately.

## 3. Severity and Choosing Log Levels

Severity indicates the importance of an event. Cloud Logging supports levels ranging from DEFAULT, DEBUG, INFO, NOTICE, WARNING, ERROR, CRITICAL, ALERT, to EMERGENCY.

| Severity | When to Use | Example |
|---|---|---|
| DEBUG | Detailed information for troubleshooting | Internal state values with sensitive data removed |
| INFO | Normal activity worth recording | Order accepted |
| NOTICE | Normal event that warrants attention | Maintenance task switched to standby mode |
| WARNING | Recoverable anomaly or issue not yet causing a direct failure | A dependency call was retried |
| ERROR | An operation failed and requires investigation | Failed to write order to database |
| CRITICAL | Severe error with major impact on functionality | Core component stopped serving |
| ALERT | Immediate action required | Primary protection mechanism is no longer operating |
| EMERGENCY | System or service cannot continue operating | Widespread outage requiring immediate action |

Use severity consistently across the entire application. Do not log every event as ERROR just to make logs stand out; doing so renders dashboards and alerts meaningless. A request rejected due to invalid user input may be WARNING or INFO depending on convention, whereas a database connection error preventing request completion is typically ERROR.

Severity also does not replace business status. A payment declined according to bank rules can be a normal business outcome, even though the application should explicitly log the event payment.declined. Choose severity based on operational impact and log an event name to express business meaning.

## 4. Text Logging vs. Structured Logging

### Text Logging

Example of a text log:

~~~text
2026-11-19 09:42:18 ERROR PaymentService - Could not authorize payment for order ord-1042
~~~

This log is human-readable, but machines struggle to reliably extract the event, order ID, error code, and other fields. To find all payment errors for an order, operators may have to rely on plain text strings and brittle search expressions.

### Structured Logging

The same event can be represented as JSON:

~~~json
{
  "severity": "ERROR",
  "message": "Could not authorize payment",
  "event": "payment.authorization_failed",
  "orderId": "ord-1042",
  "paymentProvider": "example-payments",
  "errorCode": "UPSTREAM_TIMEOUT",
  "retryable": true
}
~~~

Each attribute has a clear name and data type. Cloud Logging can store custom attributes in jsonPayload; operators can filter by event, orderId, paymentProvider, or retryable without parsing prose sentences.

Structured logging is more than just "printing JSON." For data to remain usable over the long term, keep schemas stable, field names consistent, data types accurate, and each event on a single valid JSON line. Do not rename orderId to order_id in another service without a valid reason and shared convention.

### Special Fields in JSON Logs

When Cloud Logging receives structured logs from environments that support JSON parsing, certain special fields are mapped to LogEntry metadata instead of remaining as ordinary payload attributes.

| JSON Field | Effect |
|---|---|
| severity | Sets the log entry severity |
| message | Human-readable summary shown in the log viewer |
| logging.googleapis.com/trace | Links the entry to a trace |
| logging.googleapis.com/spanId | Links the entry to a span within the trace |
| logging.googleapis.com/trace_sampled | Indicates whether the trace was sampled |
| logging.googleapis.com/labels | Attaches labels to the log entry |
| logging.googleapis.com/sourceLocation | Provides source code location |

Special fields must have exact names and formats. For example, trace must be the full trace resource name, including project ID and trace ID. Simply writing a trace ID string into a custom attribute will not automatically link the entry to Cloud Trace.

## 5. Emitting Structured Logs from a Java Application

There are several ways to send Java logs into Cloud Logging. For Cloud Run, the simplest and usually most suitable approach is writing JSON to stdout; the platform collects container logs and parses supported JSON fields. For GKE, the cluster's log collection configuration must be enabled and functioning properly. For Compute Engine, Ops Agent can be used to collect log files or data from applications.

Applications can also send logs directly using the Cloud Logging API or the Google Cloud Logging client library. Direct sending is useful in some architectures, but requires managing the client, batching, retries, and IAM permissions. Choose a single appropriate collection path per log stream to avoid duplicating the same event via both stdout and the API.

### Step 1: Add the JSON Library

The example below uses Jackson to serialize data into JSON. Your project can manage the Jackson version via a BOM or your existing dependency management setup.

~~~xml
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
</dependency>
~~~

### Step 2: Create a Structured Logger

The class below demonstrates creating a JSON object per event and writing a single line to stdout. The application does not concatenate JSON strings manually, ensuring special characters in data are properly escaped by the serializer.

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

public final class StructuredLog {
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private StructuredLog() {
    }

    public static void orderAccepted(
            String orderId,
            String traceId,
            String spanId,
            boolean traceSampled) {

        ObjectNode entry = MAPPER.createObjectNode();
        entry.put("severity", "INFO");
        entry.put("message", "Order accepted");
        entry.put("event", "order.accepted");
        entry.put("orderId", orderId);

        addTraceContext(entry, traceId, spanId, traceSampled);
        write(entry);
    }

    public static void paymentFailed(
            String orderId,
            String errorCode,
            boolean retryable) {

        ObjectNode entry = MAPPER.createObjectNode();
        entry.put("severity", "ERROR");
        entry.put("message", "Could not authorize payment");
        entry.put("event", "payment.authorization_failed");
        entry.put("orderId", orderId);
        entry.put("errorCode", errorCode);
        entry.put("retryable", retryable);
        write(entry);
    }

    private static void addTraceContext(
            ObjectNode entry,
            String traceId,
            String spanId,
            boolean traceSampled) {

        String projectId = System.getenv("GOOGLE_CLOUD_PROJECT");
        if (projectId == null || projectId.isBlank()
                || traceId == null || traceId.isBlank()) {
            return;
        }

        entry.put(
                "logging.googleapis.com/trace",
                "projects/" + projectId + "/traces/" + traceId);

        if (spanId != null && !spanId.isBlank()) {
            entry.put("logging.googleapis.com/spanId", spanId);
        }

        entry.put(
                "logging.googleapis.com/trace_sampled",
                traceSampled);
    }

    private static void write(ObjectNode entry) {
        try {
            System.out.println(MAPPER.writeValueAsString(entry));
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException(
                    "Unable to serialize structured log", exception);
        }
    }
}
~~~

In this example, orderId and errorCode are custom attributes stored in jsonPayload. severity and message are recognized by Cloud Logging. The addTraceContext method only writes trace fields when both project ID and trace ID are present; in a real application, retrieve trace ID and span ID from the active tracing library rather than generating random IDs per log line.

Trace ID and span ID must follow the format expected by the tracing system. For Cloud Trace, a trace ID is typically 32 hexadecimal characters and a span ID is 16 hexadecimal characters. The trace value written to the special field must include the full resource name, such as projects/my-project/traces/TRACE_ID.

### Step 3: Call the Logger at Meaningful Points

~~~java
public final class OrderService {
    public Order createOrder(CreateOrderCommand command) {
        Order order = repository.save(Order.from(command));

        // Identifiers are logged alongside the event.
        // Do not log tokens, passwords, or full payment details.
        StructuredLog.orderAccepted(
                order.getId(),
                tracing.currentTraceId(),
                tracing.currentSpanId(),
                tracing.isCurrentTraceSampled());

        return order;
    }
}
~~~

The snippet above assumes the application has a tracing component that provides the current request's trace ID and span ID. The exact API of the tracing component depends on the integrated library; wire it to OpenTelemetry or your project's actual tracing mechanism. If tracing is not yet in place, you can still emit structured logs with event and orderId first, then add trace correlation later.

In production applications, you can use SLF4J/Logback or your existing logging framework with a JSON encoder to retain familiar features such as MDC, logger name, thread, and exception handling. What matters is that the final output is valid JSON, one event per line, with Cloud Logging's special fields named accurately.

### Step 4: Verify on Cloud Run

When the application runs on Cloud Run and writes JSON to stdout, open Logs Explorer in the target project and filter by resource type and service name:

~~~text
resource.type="cloud_run_revision"
resource.labels.service_name="orders-api"
~~~

To find payment errors:

~~~text
resource.type="cloud_run_revision"
resource.labels.service_name="orders-api"
severity>=ERROR
jsonPayload.event="payment.authorization_failed"
~~~

To find a specific order:

~~~text
resource.type="cloud_run_revision"
resource.labels.service_name="orders-api"
jsonPayload.orderId="ord-1042"
~~~

If the fields are parsed properly, they appear as individual fields in the log entry details. If the entire JSON sits inside textPayload or appears as a plain text string, check whether the application outputs exactly one JSON object per line, whether output is wrapped with an extra text prefix, and whether the runtime is collecting stdout properly.

## 6. Designing a Long-Lived Log Schema

A good schema lets multiple services produce logs that can be queried in the same way. Define a shared core set of fields, then add domain-specific attributes.

| Group | Suggested Fields | Purpose |
|---|---|---|
| Event | event, eventVersion | Classify events and manage schema changes |
| Service | service, environment, version | Identify application and release |
| Business | orderId, internal customerId, paymentId | Link logs to business entities |
| Correlation | requestId, correlationId, trace | Follow a request across multiple services |
| Outcome | outcome, errorCode, retryable | Analyze success, failure, and retryability |
| Time | eventTime | Business timestamp if different from log write time |

Principles for keeping a schema stable:

1. Use meaningful field names that are consistent across services. Choose orderId or order_id according to system convention and stick with it.
2. Use appropriate data types. retryable is boolean; attempt is numeric; event and orderId are strings.
3. Use stable event names such as order.accepted or payment.authorization_failed. Avoid generating event names from dynamic values.
4. Include eventVersion when changing payload structure or semantics in a way that could affect consumers.
5. Do not use message as the sole field representing an event. message is for human readers; event and structured fields are for queries.
6. Keep payloads compact enough to search and read quickly. Do not attach large business objects or full request bodies.

The labels field can be used for metadata with a bounded set of values, such as environment or component. Do not put orderId, user ID, request ID, or per-request unique values into labels. High-cardinality values increase indexing and querying complexity; they usually belong in jsonPayload instead.

## 7. Linking Logs with Requests and Traces

A request can pass through an API gateway, a Cloud Run service, Pub/Sub, and a worker running on GKE. Each component may emit its own logs. When logs share a request ID or trace context, operators can trace the entire processing flow.

Distinguish between two types of identifiers:

- **Request ID or correlation ID:** an identifier used by the application or gateway to link logs belonging to the same business flow. It can be passed via an agreed internal header.
- **Trace ID and span ID:** identifiers of a distributed trace. A trace represents the entire path; a span represents a single operation or processing segment within the trace.

When an application has OpenTelemetry or Cloud Trace instrumentation, propagate trace context across service-to-service calls and include the current trace ID/span ID in structured logs. Cloud Logging can link log entries to traces when the trace field is formatted properly. This enables jumping from a log to a trace to inspect latency and parent-child span relationships.

Do not generate a new trace ID in each service if the goal is to track the same request. Continue the context passed over the protocol while creating a new span for each operation you want to measure. For requests without trace context, use a dedicated request ID to correlate logs.

Do not include full URLs with query strings, authorization headers, or cookies in HTTP logs. When HTTP details are needed, log only method, route template, status code, latency, and approved fields. For instance, a route template like /orders/{orderId} is safer and more useful than a URL containing user data.

## 8. Querying Logs in Logs Explorer

Logs Explorer supports filtering by metadata and payload fields. A query typically starts with resource type, then adds conditions on resource labels, severity, and jsonPayload.

**Find ERROR logs for a Cloud Run service:**

~~~text
resource.type="cloud_run_revision"
resource.labels.service_name="orders-api"
severity>=ERROR
~~~

**Find errors by event type:**

~~~text
resource.type="cloud_run_revision"
jsonPayload.event="payment.authorization_failed"
~~~

**Search by order ID:**

~~~text
jsonPayload.orderId="ord-1042"
~~~

**Find logs for a GKE namespace:**

~~~text
resource.type="k8s_container"
resource.labels.namespace_name="production"
severity>=WARNING
~~~

**Find logs by trace:**

~~~text
trace="projects/my-project/traces/0123456789abcdef0123456789abcdef"
~~~

Conditions can be combined using AND, OR, and NOT, or grouped with parentheses. During an investigation, narrow by time range and resource first; then filter by severity, event, error code, or trace. This is generally much more effective than searching a generic keyword across the entire project.

If a query returns no results, verify the selected project, time range, resource type, and actual field names. A field inside jsonPayload must be queried with the jsonPayload prefix; metadata fields such as severity or trace are queried directly.

## 9. From Logs to Monitoring and Alerting

Logs help explain events that happened. When you need to track trends or detect operational conditions, you can use log-based metrics to count or measure matching events.

For example, suppose an application emits the event payment.authorization_failed with severity ERROR. You can create a counter metric based on the matching filter, then use that metric in charts or alerting policies. When the error count exceeds a threshold within a time window, the operations team receives an alert.

Basic workflow:

1. Identify an operationally meaningful event and ensure the application emits a stable event name.
2. Write a filter in Logs Explorer that matches only that exact event.
3. Create a log-based metric from the verified filter.
4. Verify that the metric increments accurately when the event occurs.
5. Create an alerting policy with appropriate thresholds, evaluation duration, and notification channels.
6. Test the alert in a staging environment and tune it to reduce false positives.

Do not rely on logs as the sole source for all reliability indicators. Latency, request count, error rate, and saturation are usually better collected via proper metrics; logs supplement them with root cause and per-event context. Combining metrics, logs, and traces allows operators to detect anomalies, locate affected requests, and identify failing components.

## 10. Protecting Data and Controlling Log Costs

Logs are often shared across teams and may be exported to external systems. Therefore, treat everything logged as data accessible to authorized readers and retained according to organizational policy.

### Never Log Secrets or Sensitive Data

Do not log:

- Passwords, API keys, access tokens, session cookies, or authorization headers.
- Private keys, secret payloads, or connection strings containing credentials.
- Payment card numbers, unnecessary personal data, or full request/response bodies.
- Exception details if the error message might contain SQL statements, tokens, or user data.

Filter and mask sensitive data inside the application before serialization. Stripping fields after logs reach Cloud Logging does not guarantee that all copies, sinks, or downstream systems are free of that data.

### Limiting Log Volume

- Use INFO for significant operational events; enable DEBUG only for the required duration and scope.
- Do not log a line for every small step inside a high-throughput loop unless there is an explicit investigative need.
- Do not log full request bodies or response bodies. Log identifiers and the minimal attributes needed for troubleshooting.
- Avoid repeating stack traces across multiple layers for the same error. Choose a single layer with sufficient context to log the error.
- Use deliberate sampling for very high-volume success events; retain full error logs and required security events.
- Define retention periods and log buckets aligned with operational, legal, and cost requirements.

### Access Permissions and Routing

Use IAM to restrict who can view logs, configure buckets, create sinks, or modify routing policies. Separate log-reading permissions from logging administration permissions whenever possible. For sensitive or audit logs, adhere to organizational access control and retention policies.

Log Router can route logs to log buckets or external destinations such as BigQuery, Pub/Sub, and Cloud Storage through sinks. Before creating a sink, define its purpose, filter scope, sink writer permissions, and destination retention policy. An overly broad sink can duplicate more data than needed and increase costs.

Exclusion filters can drop unneeded logs from applicable storage streams. Test filters carefully and review their impact on incident investigation before dropping logs. Never exclude audit logs or mandatory security events solely to reduce cost.

## 11. Distinguishing Application Logs and Audit Logs

Application logs are generated by applications to describe business or technical processing, such as an order being created, a payment failing, or a worker retrying a message.

Audit logs record access and modifications on Google Cloud resources or services. Cloud Audit Logs include categories such as Admin Activity, Data Access, System Event, and Policy Denied. These logs have specialized payload structures and typically contain information about the principal, method, resource, and operation outcome.

Examples:

- A Java service logging the event order.created is an application log.
- An administrator modifying a project's IAM policy generates an Admin Activity audit log.
- A principal reading data from a service with Data Access audit logging enabled can generate a corresponding audit log.

Do not log application events and treat them as a substitute for audit logs. The two log types serve different purposes and differ in origin, access control, structure, and retention policies.

## 12. Hands-On Scenario: Investigating a Payment Failure

A system consists of an API running on Cloud Run and a payment-processing worker. Users report that some orders are stuck in a pending state. The operations team needs to determine whether the failure originates in the API, the message queue, or the worker.

Implement a shared log schema for both services:

- event: stable event names such as order.accepted, payment.requested, payment.authorization_failed, and payment.completed.
- orderId: order identifier used to correlate business events.
- correlationId: correlation identifier carried across the API and worker.
- trace: trace ID if distributed tracing is enabled.
- severity: INFO for normal flow, WARNING for recoverable retries, and ERROR for failed operations requiring investigation.
- errorCode and retryable: stable error code and flag indicating whether retry is possible.

After deploying, perform the following steps:

1. Create a test order and note the orderId.
2. Confirm that the API emits event order.accepted and the worker emits event payment.requested with the same orderId/correlationId.
3. Simulate a timeout error from the payment service in a test environment.
4. Open Logs Explorer, filter by orderId, and inspect the sequence of events.
5. Filter severity>=ERROR and event payment.authorization_failed to locate the error log.
6. If tracing is enabled, open the linked trace to inspect latency on spans calling the payment service.
7. Create a log-based metric counting payment.authorization_failed and confirm the metric increments when the failure is simulated.
8. Verify that logs contain no tokens, cookies, or sensitive payment data.

The expected outcome is that an operator can go from a single orderId to logs from both the API and the worker, identify the failure point, and view the associated trace without manually searching across multiple servers.

## 13. Pre-Production Structured Logging Checklist

- [ ] Every log entry is a valid single-line JSON object.
- [ ] Severity is chosen based on operational impact and applied consistently.
- [ ] Event names are stable, meaningful, and contain no dynamic values.
- [ ] Field names and data types are consistent across services.
- [ ] Resource type and resource labels are attached accurately for the deployment environment.
- [ ] Request ID, correlation ID, or trace context is propagated end to end where appropriate.
- [ ] Trace and span fields are formatted as required by Cloud Logging.
- [ ] No passwords, tokens, cookies, private keys, or unnecessary personal data are logged.
- [ ] Log volume, sampling, retention, and sinks match operational needs and budget.
- [ ] Log viewing and logging administration permissions are restricted via IAM.
- [ ] Logs Explorer queries and log-based metrics have been verified with test events.

## Self-Check Questions

**1. What are the main parts of a LogEntry?**

A LogEntry has metadata such as logName, resource, timestamp, severity, and trace; as well as an appropriate payload such as jsonPayload, textPayload, or protoPayload.

**2. How does structured logging help compared to text logs?**

JSON has explicit fields and data types, enabling queries by event, orderId, errorCode, or other attributes without parsing free-form prose.

**3. Why should requestId or orderId not be placed in labels?**

These are typically high-cardinality values. They fit better inside jsonPayload; labels should be reserved for metadata with a bounded set of values.

**4. How does Cloud Logging link logs to traces?**

By writing trace context in the proper format, where the logging.googleapis.com/trace field contains the full trace resource name alongside the corresponding span field if available.

**5. How does Cloud Run collect structured logs in this lesson's example?**

The application writes JSON to stdout; the platform collects container logs and parses supported JSON fields.

**6. Can application logs replace audit logs?**

No. Application logs describe application processing; audit logs record access or changes to resources and services through Google Cloud's auditing mechanism.

## Conclusion

Cloud Logging provides a centralized place to search and analyze logs from Java applications, infrastructure, and Google Cloud services. Understanding the LogEntry structure helps distinguish metadata from payload, select the right severity, and filter by monitored resource. Structured logging puts events into JSON with a stable schema, allowing Logs Explorer to query by fields and link logs to traces. When designing schemas, pay attention to protecting sensitive data, controlling cardinality, log volume, IAM permissions, and retention policies so your observability setup remains both useful and cost-effective.
