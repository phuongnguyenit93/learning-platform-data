# Correlating Logs, Metrics, Traces, and CloudTrail for Root Cause Analysis

When an API on AWS returns a 500 error, a Lambda function slows down, or a message stalls in a queue, each service typically shows only one piece of the incident. CloudWatch Logs may hold the stack trace, CloudWatch Metrics reveals a rising error rate, AWS X-Ray pinpoints which dependency slowed down the request, and AWS CloudTrail records who changed a policy or configuration right before the outage began. Without correlating these signals, engineers must search system by system, align timestamps manually, and risk missing root causes sitting at boundaries between services.

Observability is the ability to infer a system's internal state from the telemetry it emits. Three signals are commonly used: logs, metrics, and traces. Logs capture discrete events; metrics aggregate behavior over time; traces map a request's path across components. CloudTrail adds an audit perspective over AWS account API activity, which is especially valuable when investigating configuration changes, API calling identities, and resource mutations.

No single signal explains an entire incident on its own. A metric shows errors climbed yet does not identify which requests failed. A trace reveals wait time at a database yet does not explain why a security group was just edited. A CloudTrail event logs an IAM role update yet does not show which business requests broke. Finding root cause requires consistent end-to-end identifiers, synchronized time, structured logging, trace context propagation, audit event retention, and a disciplined investigation workflow.

This lesson sits within the `CLOUD_PROVIDERS_AWS` scope: selecting and operating observable, resilient, and cost-controlled services. The focus is on combining CloudWatch Logs, Metrics, Alarms, AWS X-Ray, OpenTelemetry, and CloudTrail to tie symptoms to requests, dependencies, configuration changes, and root causes.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish logs, metrics, traces, and audit events.
- Explain the roles of CloudWatch, AWS X-Ray, OpenTelemetry, and CloudTrail.
- Design structured logging and correlation IDs for distributed applications.
- Propagate trace context across API Gateway, Lambda, queues, and service-to-service calls.
- Use CloudWatch Logs Insights to find errors and correlate logs per request.
- Use metrics, alarms, dashboards, and anomaly detection to detect symptoms.
- Read traces, spans, and service maps to identify slow or failing dependencies.
- Locate CloudTrail management events and data events tied to AWS resource changes.
- Combine timestamps, resource IDs, principals, request IDs, and deployment versions to construct timelines.
- Protect observability data, restrict access, and manage retention and cost.
- Apply an investigation workflow from detection through root-cause verification and post-fix monitoring.

## 2. Observability and the Four Signal Types

### 2.1. Logs

A log is an immutable record of an event at a point in time. Logs can capture:

- Request start or completion.
- Validation and authorization results.
- Exceptions or timeouts.
- Execution duration of an operation.
- Request, trace, or message IDs.
- Resource identifiers and application versions.

Logs answer "what happened during this specific execution?". Logs are most useful when structured with explicit timestamps, severity levels, and filterable identifiers.

### 2.2. Metrics

A metric is a numeric time series, typically organized by namespace, metric name, and dimensions. Examples:

- Requests per minute.
- HTTP 5xx rate.
- Lambda duration p95.
- SQS `ApproximateAgeOfOldestMessage`.
- Database connection count.
- CPU utilization.

Metrics answer "how is the system performing and how is it trending?". Metrics drive alarms and dashboards yet rarely carry enough detail to explain a single request.

### 2.3. Traces

A trace represents the journey of a request or transaction across multiple components. A trace consists of spans; each span represents an operation such as an API handler, Lambda invocation, database query, or HTTP call.

Traces answer:

- Which services did the request pass through?
- Which component consumed the most time?
- Which dependency returned an error?
- Were there retries or fan-out calls?
- Do these spans belong to the same request?

Traces illuminate latency breakdowns and causal flow across requests, though sampling means not every request produces a complete trace.

### 2.4. Audit Events

Audit events record actions against systems or resources, typically capturing principal, API action, timestamp, source, and outcome. On AWS, CloudTrail is the primary source for investigating control-plane activity and configured data events.

CloudTrail answers:

- Who called the API?
- Which action was performed?
- Which resources were affected?
- Did the API call succeed or get denied?
- Did the configuration change happen before or after errors began?

CloudTrail does not replace application logs, packet captures, or traces. It records AWS API activity according to event types and trail/event data store settings.

### 2.5. Quick Comparison

| Signal | Unit of Observation | Primary Question | Common AWS Tools |
|---|---|---|---|
| Logs | Events/records | What happened? | CloudWatch Logs |
| Metrics | Values over time | When and how severe? | CloudWatch Metrics |
| Traces | Requests and spans | Where did it go and where did it slow down? | AWS X-Ray, OpenTelemetry |
| Audit events | Actions on resources | Who changed or called which API? | AWS CloudTrail |

### 2.6. From Monitoring to Observability

Monitoring tracks known conditions, such as high CPU or 5xx rates crossing thresholds. Observability enables investigating previously unknown questions by combining logs, metrics, traces, metadata, and audit events.

A system with dozens of dashboards yet no correlation IDs remains hard to debug. A system with traces yet inadequate retention loses evidence during prolonged incidents. Therefore, design observability around how operations teams will actually diagnose root causes, not merely around toggling services on.

## 3. Observability Architecture on AWS

### 3.1. End-to-End Telemetry Flow

A distributed application can emit telemetry along this flow:

1. API Gateway receives the request and creates request context.
2. Lambda or ECS service processes it, writes structured logs, and emits metrics.
3. Trace context propagates to downstream services.
4. X-Ray or OpenTelemetry collector/exporter ships spans to the observability backend.
5. CloudWatch ingests logs, metrics, alarms, and dashboards.
6. CloudTrail records API calls against AWS resources.
7. On-call engineers correlate using request IDs, trace IDs, resource ARNs, and timestamps.

~~~mermaid
flowchart LR
    U[Client] --> A[API Gateway]
    A --> S[Lambda / ECS services]
    S --> D[(DynamoDB / RDS)]
    S --> Q[SQS / EventBridge]
    Q --> C[Consumers]
    A -. logs .-> L[CloudWatch Logs]
    S -. logs .-> L
    C -. logs .-> L
    S -. metrics .-> M[CloudWatch Metrics]
    C -. metrics .-> M
    A -. trace context .-> X[X-Ray / OpenTelemetry]
    S -. spans .-> X
    C -. spans .-> X
    AWS[AWS API activity] --> T[CloudTrail]
    L --> O[Investigation]
    M --> O
    X --> O
    T --> O
~~~

This diagram shows telemetry sources and analysis convergence. Depending on architecture, logs and traces may flow through subscriptions, collectors, or partner tools; CloudTrail can deliver to S3, CloudWatch Logs, or CloudTrail Lake.

### 3.2. CloudWatch as the Operational Telemetry Layer

Amazon CloudWatch provides:

- Logs: collect, store, query, and analyze logs.
- Metrics: store time-series and custom metrics.
- Alarms: evaluate metrics or math expressions to trigger alerts.
- Dashboards: aggregate health across services.
- Logs Insights: query logs via an interactive query language.
- Synthetics: run canaries testing endpoints or user journeys.
- Application Signals: monitor application performance and service dependencies for supported workloads.

CloudWatch ingests automatic metrics from many AWS services. Applications can emit custom metrics or Embedded Metric Format (EMF) logs when tracking business metrics.

### 3.3. AWS X-Ray and OpenTelemetry

AWS X-Ray collects and displays traces, service maps, and span details. Applications can be instrumented with appropriate SDKs/agents or OpenTelemetry with compatible exporters/collectors.

OpenTelemetry is an open framework for generating, collecting, and exporting traces, metrics, and logs. AWS Distro for OpenTelemetry (ADOT) provides an AWS-supported distribution and collector for supported environments. CloudWatch, X-Ray, or other observability backends can serve as destinations.

Do not mix multiple instrumentations that emit duplicate spans for the same operation. Choose one consistent instrumentation strategy, define service names and propagation formats, and test traces end-to-end.

### 3.4. CloudTrail Adds the Audit View

CloudTrail records API activity across AWS accounts. Event history lets you browse recent management events per Region; trails can deliver events to S3 and optionally CloudWatch Logs; CloudTrail Lake supports storing and SQL-querying events in event data stores.

During investigations, CloudTrail shows which principal modified a policy, security group, route table, Lambda configuration, KMS key, or other resource. Correlate those events with application traces and metrics to determine whether the change aligns with symptoms.

## 4. Designing Identifiers to Link Signals

### 4.1. Why Correlation IDs Are Needed

A single request can generate logs across multiple services and trigger asynchronous events. If each service invents its own independent ID, tying records back to one business journey becomes very difficult.

A correlation ID is an application-level identifier linking logs and events across a single business workflow. It can reuse a gateway-assigned request ID or be generated at the entry service when requests arrive from elsewhere.

Example:

~~~json
{
  "timestamp": "2026-11-20T10:15:30.123Z",
  "level": "INFO",
  "service": "order-api",
  "environment": "production",
  "event": "order.created",
  "request_id": "req-7f2a",
  "correlation_id": "corr-91bd",
  "trace_id": "1-673ecb36-2a1b4c8d5e6f789012345678",
  "span_id": "4a1b2c3d4e5f6789",
  "order_id": "order-123",
  "duration_ms": 42
}
~~~

Values above are illustrative only. Never embed emails, phone numbers, access tokens, or personal data in IDs.

### 4.2. Distinguishing Identifiers

| ID | Scope | Purpose |
|---|---|---|
| `requestId` | Single API call or invocation | Locate the request in the receiving component's logs |
| `correlationId` | One business flow across multiple requests/services | Link logs and events across workflows |
| `traceId` | One distributed trace | Group spans belonging to a single execution path |
| `spanId` | One operation within a trace | Pinpoint a specific operation |
| `messageId`/`eventId` | Single message/event | Deduplicate and trace processing |
| `deploymentId`/`buildId` | Single release/build | Tie incidents to code/config versions |

Never collapse all these concepts into one ID. Trace IDs often change when starting new traces or crossing async boundaries; correlation IDs can persist across multiple traces belonging to the same business workflow.

### 4.3. Propagating Over HTTP

When one service calls another, propagate trace context using instrumentation-supported standards—typically W3C Trace Context via `traceparent` and optionally `tracestate`. Some AWS components use or recognize the `X-Amzn-Trace-Id` header.

Applications can also propagate correlation IDs via a dedicated header, e.g.:

~~~http
X-Correlation-Id: corr-91bd
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

When accepting correlation IDs from clients, validate allowed characters and cap length. Never allow clients to inject huge strings or sensitive payloads into logs. You can generate a fresh ID at the gateway and store any external ID in a separate field if needed.

### 4.4. Propagating Over Queues and Events

With SQS, EventBridge, or Kinesis, include the correlation ID, event ID, and trace context in message attributes or the event envelope per your application contract.

Example event:

~~~json
{
  "eventId": "evt-8831",
  "eventType": "OrderCreated",
  "correlationId": "corr-91bd",
  "traceContext": {
    "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
  },
  "detail": {
    "orderId": "order-123"
  }
}
~~~

In asynchronous flows, consumers can start a new span and link it to the producer's context via parent context or span links as supported by the instrumentation. Not every trigger automatically forwards custom headers; verify envelopes and SDK/agent propagation configs.

### 4.5. Propagating in Lambda

Lambda provides a context object carrying a unique request ID per invocation. Log that request ID alongside trace context from triggers or instrumentation. With Lambda active tracing enabled, X-Ray creates an invocation segment and links instrumented downstream calls.

For SQS batches, one invocation can process multiple messages. Log the message ID and correlation ID per record; never treat one invocation request ID as the sole identifier for every business item in a batch.

### 4.6. Trace ID Is Not Correlation ID

Traces typically focus on a single technical execution path. An order may span an API request, async consumer, retries, and a multi-minute workflow. Each stage may have its own trace yet share the same correlation ID and business ID.

When designing systems:

- Trace IDs link spans.
- Correlation IDs link business flows.
- Event IDs identify specific messages.
- Resource IDs identify AWS resources.

This separation enables investigating both synchronous requests and long-running asynchronous workflows.

## 5. Structured Logging with CloudWatch Logs

### 5.1. Structured Logs

Structured logging writes records in JSON or an explicit key-value format. Unlike free-form text logs, JSON is easily filtered by service, level, request ID, trace ID, pseudonymized tenant, and error code.

A record should include:

- UTC timestamp.
- Level: `DEBUG`, `INFO`, `WARN`, `ERROR`.
- Service and environment.
- Event name or operation.
- Relevant request/correlation/trace IDs.
- Duration and outcome.
- Error type/code and stack trace when needed.
- Target resource or dependency called.
- Application version.

Do not log full request/response payloads by default. Log only classified fields needed for diagnostics.

### 5.2. Python Logging Example

~~~python
import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def log_event(level, event, **fields):
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "service": os.environ.get("SERVICE_NAME", "order-api"),
        "environment": os.environ.get("ENVIRONMENT", "test"),
        "event": event,
        **fields,
    }
    logger.log(getattr(logging, level), json.dumps(record))
~~~

Example call:

~~~python
log_event(
    "INFO",
    "order.created",
    correlation_id="corr-91bd",
    order_id="order-123",
    duration_ms=42,
)
~~~

In production, use a logging library supporting context management and redaction. Never allow arbitrary fields to overwrite `timestamp`, `level`, or `service` in ways that corrupt log structure.

### 5.3. Log Levels

| Level | When to Use |
|---|---|
| `DEBUG` | Detailed diagnostics for development or controlled investigations |
| `INFO` | Significant normal lifecycle events |
| `WARN` | Recoverable anomalies or non-critical degradation |
| `ERROR` | Failed operations requiring investigation |
| `FATAL`/`CRITICAL` | Component unable to continue normal operation |

Avoid logging the exact same exception at multiple layers, which duplicates noise. Log full details at the layer with complete context; lower layers can attach state or rethrow.

### 5.4. CloudWatch Log Groups and Streams

A log group typically represents an application or component; log streams partition writers, such as Lambda execution environments or containers. Adopt predictable naming conventions including environment.

Examples:

~~~text
/aws/lambda/order-api-prod
/ecs/commerce/checkout-prod
/aws/apigateway/commerce-prod
~~~

Set retention according to operational, audit, and regulatory needs. Never leave log groups set to retain indefinitely without a requirement. For sensitive logs, consider KMS encryption, scoped access permissions, and subscription filters to controlled storage.

### 5.5. CloudWatch Logs Insights

Logs Insights queries logs by time range, fields, filters, parsing, stats, and sorting. With JSON structured logs, fields are typically discovered automatically.

Find recent errors:

~~~text
fields @timestamp, service, event, correlation_id, trace_id, error_code, @message
| filter level = "ERROR"
| sort @timestamp desc
| limit 100
~~~

Count errors by service:

~~~text
fields service, level
| filter level = "ERROR"
| stats count() as errorCount by service
| sort errorCount desc
~~~

Trace a single business flow:

~~~text
fields @timestamp, service, event, correlation_id, order_id, trace_id, duration_ms
| filter correlation_id = "corr-91bd"
| sort @timestamp asc
~~~

Calculate p95 latency:

~~~text
filter ispresent(duration_ms)
| stats pct(duration_ms, 95) as p95, avg(duration_ms) as average by service
~~~

Exact field names and data types depend on actual logs. Start with a narrow time range and widen only as needed; scanning large log volumes takes time and incurs cost.

### 5.6. Metric Filters and Embedded Metric Format

Metric filters turn log patterns into CloudWatch metrics. EMF lets applications write JSON logs containing metric definitions so CloudWatch extracts metrics asynchronously without calling `PutMetricData` for every datapoint.

EMF is helpful when measuring business metrics such as:

- `orders_created`.
- `payment_declined`.
- `inventory_conflict`.
- `workflow_duration`.

Never put request IDs, user IDs, or order IDs into metric dimensions due to high cardinality. Keep those IDs in logs/traces; reserve metric dimensions for bounded attributes like `service`, `environment`, `operation`, or `region`.

### 5.7. Correlation in Logs

Each log record should include linking fields where available:

~~~json
{
  "service": "payment-worker",
  "event": "payment.authorized",
  "correlation_id": "corr-91bd",
  "event_id": "evt-8831",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "deployment_id": "release-2026-11-20.3"
}
~~~

This allows engineers to start from a correlation ID, pull logs across services, jump to the matching trace, and verify the deployed release version.

## 6. Metrics, Alarms, and Dashboards

### 6.1. Metric Namespaces and Dimensions

CloudWatch metrics are organized by namespace, metric name, and dimensions. AWS services publish metrics under their own namespaces; custom applications can use custom namespaces like `Commerce/Orders`.

Dimensions should represent bounded attributes. Examples:

- `ServiceName`.
- `Environment`.
- `Operation`.
- `Region`.
- `QueueName`.

Avoid dimensions such as request ID, trace ID, email, or order ID. High cardinality multiplies metric time series and costs while making dashboards hard to aggregate.

### 6.2. Golden Signals

Four standard signals for services:

1. **Latency:** time to process requests.
2. **Traffic:** request or message rate.
3. **Errors:** failed request rate.
4. **Saturation:** resource utilization or queue backlogs.

API example:

| Signal | Metrics to Track |
|---|---|
| Latency | `IntegrationLatency`, `Duration`, p95/p99 |
| Traffic | `Count`, `Invocations`, requests/sec |
| Errors | `5xx`, `Errors`, `Throttles` |
| Saturation | `ConcurrentExecutions`, queue age, DB connections |

Low CPU alone does not prove a service is healthy. Rising queue backlogs can indicate consumers are falling behind even while API CPU stays normal.

### 6.3. Percentiles vs. Averages

Averages hide slow tail requests. For instance, 99 requests at 50 ms plus one request at 5 seconds can still yield a low average. Monitor p50, p90, p95, and p99 according to SLAs.

For distribution metrics, pick appropriate statistics and periods. Never compute percentiles by averaging pre-aggregated averages when accurate percentiles are needed; use proper metric types/histograms.

### 6.4. CloudWatch Alarms

Alarms evaluate metrics by period and static thresholds or anomaly bands. Configurable options include:

- Static thresholds.
- Metric math.
- Anomaly detection.
- M-of-N evaluation.
- Missing data treatment.
- Alarm actions via SNS, Incident Manager, or integrated automation.

A good alarm needs:

- Signals tied directly to user impact.
- Thresholds grounded in baselines/SLOs.
- Evaluation periods that filter out transient noise.
- Clear owners and runbooks.
- Defined actions on `ALARM`/`OK` transitions.

Never create alarms for every metric without someone responsible to act on them. Alarm fatigue degrades response to real incidents.

### 6.5. SLOs and Error Budgets

A Service Level Objective (SLO) defines a reliability target, such as success rate or latency below a threshold over a time window. An error budget is the tolerable level of failure within the SLO.

Examples:

- 99.9% successful requests over 30 days.
- 95% of requests completing under 300 ms.
- 99% of events processed within 2 minutes.

Tracking SLOs distinguishes brief minor blips from user-impacting degradation trends. Burn-rate alerts warn when error budgets are depleting too rapidly.

### 6.6. Dashboards

Operational dashboards should answer:

- Is the service serving users successfully?
- When did errors and latency start?
- Which dependencies show anomalies?
- Are queues or concurrency saturating?
- Which version is running?
- Did any configuration change near incident onset?

An overview dashboard can organize rows for API, compute, databases, queues/events, dependencies, and deployments. Build dashboards around service ownership and link directly to Logs Insights queries, trace searches, and runbooks.

### 6.7. Anomaly Detection

CloudWatch anomaly detection models expected value bands from historical metrics. This helps with workloads having daily/weekly cycles or metrics where fixed thresholds are hard to pick.

Anomaly bands do not automatically understand business impact. A traffic spike might be normal during peak hours; conversely, values inside the band might still breach SLOs. Pair anomaly detection with error rates, latency, and business metrics.

## 7. Distributed Tracing with AWS X-Ray

### 7.1. Traces and Spans

A trace is a collection of spans belonging to a single request or workflow. A span records:

- Operation name.
- Start time and duration.
- Parent/child relationship.
- Service/resource identity.
- Status/errors.
- Attributes or annotations.

Example request tree:

~~~text
API Gateway
  └── Order Lambda
       ├── DynamoDB PutItem
       └── EventBridge PutEvents
            └── Payment Consumer
                 └── Payment API
~~~

Traces pinpoint which segment consumed latency and which dependency returned errors.

### 7.2. X-Ray Segments and Subsegments

Segments represent work done by a service handling a request. Subsegments represent internal operations, such as AWS SDK calls, HTTP dependencies, or database queries. X-Ray automatically instruments several AWS integrations and SDK calls when properly configured.

Good traces have consistent service names, meaningful span names, and clear error/status flags. Never embed user IDs or high-cardinality values inside span names.

### 7.3. Enabling Tracing for Lambda

Lambda supports active tracing with AWS X-Ray, configurable in function settings or IaC. When enabled, Lambda emits a trace segment per invocation and links instrumented downstream calls.

Abbreviated CloudFormation example:

~~~yaml
Resources:
  OrderFunction:
    Type: AWS::Lambda::Function
    Properties:
      TracingConfig:
        Mode: Active
~~~

The execution role needs appropriate trace-writing permissions, typically added via managed policies or least-privilege equivalents. Verify trace sampling and IAM permissions after deployment; enabling tracing without permissions or proper instrumentation will fail to produce expected traces.

### 7.4. X-Ray Trace Headers

X-Ray uses the `X-Amzn-Trace-Id` header to pass trace context in supported integrations, containing fields such as `Root`, `Parent`, and `Sampled`. W3C Trace Context uses `traceparent` and `tracestate`.

When combining OpenTelemetry and X-Ray, use compatible propagators and verify trace IDs stitch cleanly across services. Never fabricate parent headers without understanding sampling and trace relationships.

### 7.5. Sampling

Sampling limits collected trace volume to control cost and overhead. X-Ray sampling rules select percentages or reservoirs by service, host, path, and supported conditions.

Trade-offs:

- Low sampling cuts cost yet can miss rare errors.
- High sampling increases visibility yet raises data volume and cost.
- Tail sampling at collectors in supported OpenTelemetry architectures can prioritize keeping error/slow traces.

For rare incidents, pair sampled traces with full structured error logs and metrics so failures never go undetected.

### 7.6. Service Maps

The X-Ray service map visualizes services and dependencies inferred from traces. It highlights:

- Services with elevated latency.
- Dependencies with rising error rates.
- Requests stalling downstream.
- Relationships across APIs, Lambda, and AWS services.

Service maps depend on uploaded traces and how instrumentation identifies dependencies. Missing spans or broken context propagation result in incomplete maps.

### 7.7. Annotations and Metadata

X-Ray annotations are indexed fields for filtering traces; metadata stores extra unindexed context. Annotate only high-value, bounded attributes such as operation, environment, tenant tier, or error category.

Never place PII, secrets, full request bodies, or tokens into annotations or metadata. Traces may be viewed by multiple operators and have different retention than logs.

## 8. OpenTelemetry and CloudWatch Application Signals

### 8.1. OpenTelemetry

OpenTelemetry provides APIs, SDKs, semantic conventions, and collectors to instrument applications without locking code to a single observability backend.

Signals:

- Traces: spans and context propagation.
- Metrics: counters, gauges, and histograms.
- Logs: context-enriched records.

Applications instrumented with OpenTelemetry SDKs export via OTLP to a collector, which forwards telemetry to the target backend.

### 8.2. AWS Distro for OpenTelemetry

AWS Distro for OpenTelemetry (ADOT) is an AWS-supported OpenTelemetry distribution for published environments and integrations. The ADOT Collector receives OTLP, runs processors, and exports telemetry to CloudWatch, X-Ray, or compatible backends.

Conceptual collector pipeline example:

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
      http:

processors:
  batch:

exporters:
  awsxray:
  awsemf:

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [awsxray]
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [awsemf]
~~~

Actual configurations depend on collector version, exporters, IAM roles, and runtime environment. Verify component availability and schemas against the deployed ADOT release.

### 8.3. CloudWatch Application Signals

Application Signals provides application performance monitoring for supported services and dependencies, including service maps, latency, errors, and availability signals. It reduces manual dashboard construction when runtimes and instrumentation are supported.

Before enabling, check language/runtime support, deployment models, IAM permissions, and Region availability. Application Signals does not automatically instrument every custom protocol or external component; still add custom spans/metrics for specialized business operations.

### 8.4. Choosing X-Ray SDK vs. OpenTelemetry

| Criterion | X-Ray Instrumentation | OpenTelemetry/ADOT |
|---|---|---|
| AWS integration | Direct with X-Ray and AWS services | Exporters/collectors available for AWS |
| Openness | Tied to X-Ray APIs/formats in places | Open standard supporting multiple backends |
| Portability | Best for AWS-centric stacks | Ideal when multi-backend portability is needed |
| Instrumentation | Via X-Ray SDK/agent | Via OTel SDK/auto-instrumentation |
| Operations | Manage X-Ray segments and sampling | Manage collectors, pipelines, and exporters |

Standardize on one propagation format and avoid duplicate instrumentation. For greenfield systems, consider OpenTelemetry if portability matters; for existing X-Ray workloads, continue or migrate incrementally per plan.

## 9. AWS CloudTrail for Investigating Changes and API Activity

### 9.1. What Does CloudTrail Record?

CloudTrail records AWS account activity as events. An event typically includes:

- `eventTime`: API call timestamp.
- `eventSource`: AWS service called.
- `eventName`: API operation name.
- `awsRegion`: Region.
- `userIdentity`: acting principal or session.
- `sourceIPAddress`: caller source.
- `requestParameters`: request parameters, when recorded.
- `responseElements`: response details, if recorded.
- `errorCode` and `errorMessage`: failure details if rejected.
- `resources`: involved resources.
- `eventID` and `requestID`: event/API request identifiers.

CloudTrail helps verify whether an IAM policy, route table, security group, Lambda configuration, or KMS key was modified. Exact detail depends on the API, event type, and service redaction rules.

### 9.2. Management Events

Management events capture control-plane operations such as creating, updating, or deleting AWS resources, modifying policies, and changing service settings. CloudTrail Event history provides recent regional management events.

Examples:

- `UpdateFunctionConfiguration`.
- `PutRolePolicy`.
- `AuthorizeSecurityGroupIngress`.
- `PutBucketPolicy`.
- `UpdateTable`.

Exact event names depend on the service and API operation. Search by event source, event name, principal, and resource during investigations.

### 9.3. Data Events

Data events record data-plane operations on supported resource types, such as S3 object-level APIs or Lambda invocations per supported configurations. Data events are generally off by default due to high volume and cost.

If you must audit who read S3 objects or invoked functions, configure data event selectors for the specific buckets, prefixes, or functions. Scope selectors narrowly and verify events are captured.

### 9.4. Event History, Trails, and CloudTrail Lake

| View Option | Purpose | Notes |
|---|---|---|
| Event history | Browse recent management events in Console/API | Limited history window; not a long-term archive |
| Trail | Deliver events to S3 and optionally CloudWatch Logs | Suited for audit/retention and external analytics |
| CloudTrail Lake | Store events in event data stores and query with SQL | Ingest/retention/query costs apply per service pricing |
| EventBridge integration | React near real-time to matching events | Use rules to route and trigger automation |

Organizations often combine centralized trails, a dedicated log archive account, and CloudTrail Lake for advanced policy-driven investigations. Define owners, retention, encryption, and read permissions for audit data.

### 9.5. Log File Integrity Validation

CloudTrail supports log file integrity validation using digest files to detect whether delivered S3 log files were modified or deleted after CloudTrail wrote them. Enable validation when audits require integrity proof; store digests and logs in tightly restricted buckets.

Integrity validation does not prove every action was logged if trails/event selectors were misconfigured. Verify event coverage first, then verify file integrity.

### 9.6. CloudTrail Insights

CloudTrail Insights detects unusual API activity for supported event types and conditions, such as sudden spikes in API call rates. It is a supplementary investigative signal, not a replacement for CloudTrail events or application metrics.

### 9.7. Example CloudTrail Event

~~~json
{
  "eventTime": "2026-11-20T10:12:00Z",
  "eventSource": "lambda.amazonaws.com",
  "eventName": "UpdateFunctionConfiguration",
  "awsRegion": "ap-southeast-1",
  "userIdentity": {
    "type": "AssumedRole",
    "arn": "arn:aws:sts::123456789012:assumed-role/DeploymentRole/build-482"
  },
  "requestParameters": {
    "functionName": "order-api"
  },
  "responseElements": null,
  "eventID": "example-event-id",
  "requestID": "example-request-id"
}
~~~

This illustrates an abbreviated structure; real events contain additional fields and sensitive values may be redacted. When investigating, do not depend on a single field if a given API or service omits it.

## 10. Searching CloudTrail Events via Queries

### 10.1. Searching Event History

Filter by:

- Event name.
- Event source.
- User name or principal.
- Resource name.
- Time range.

Start with the window immediately preceding the error metric spike. If no events appear, verify Region, account, event type, and trail resource coverage.

### 10.2. CloudTrail Lake SQL

CloudTrail Lake lets you query event data stores with SQL. Example searching for Lambda configuration updates:

~~~sql
SELECT
    eventTime,
    eventSource,
    eventName,
    userIdentity.arn,
    sourceIPAddress,
    requestParameters
FROM event_data_store
WHERE eventSource = 'lambda.amazonaws.com'
  AND eventName = 'UpdateFunctionConfiguration'
  AND eventTime > '2026-11-20 09:00:00'
ORDER BY eventTime DESC;
~~~

Table/event data store names and field paths must match your CloudTrail Lake schema. This example illustrates the pattern; verify SQL dialect and field mappings in your environment.

### 10.3. EventBridge for Change Detection

Create EventBridge rules matching CloudTrail API events—such as IAM policy or security group edits—and route them to SNS, Lambda, or remediation workflows.

Include guardrails on automation:

- Match only critical events.
- Validate principal and resource.
- Record event IDs.
- Avoid auto-rolling back legitimate changes.
- Require human review for high-impact actions.

### 10.4. Missing Expected Events

Common causes:

- Viewing the wrong Region or account.
- Event is a data event without an active selector.
- Trail does not capture that event category.
- Event history retention window expired.
- Wrong resource ARN or event source filter.
- Delivery/ingestion delay.

Never conclude "nothing changed" simply because Event history returned zero matches. Confirm audit configuration coverage first.

## 11. Workflow for Correlating Logs, Metrics, Traces, and CloudTrail

### 11.1. Start from Symptoms

When an alarm fires or users report issues:

1. Identify the service, operation, and onset time.
2. Scope impact: affected requests, tenants, Regions, or business flows.
3. Open dashboards to inspect traffic, errors, latency, and saturation.
4. Pick a representative failing request or correlation ID.
5. Pull matching logs.
6. Open the trace if available and locate slow/failing spans.
7. Identify affected dependencies and resource ARNs.
8. Search CloudTrail for resource or permission changes in the relevant window.
9. Build a timeline and test hypotheses against evidence.

### 11.2. Unified Timeline

A timeline might look like:

| UTC Time | Source | Evidence |
|---|---|---|
| 10:00:00 | Deployment system | Release `build-482` started |
| 10:02:15 | CloudTrail | Lambda configuration updated |
| 10:03:00 | CloudWatch Metrics | Lambda `Errors` began climbing |
| 10:03:12 | API Gateway | HTTP 5xx increased |
| 10:03:15 | X-Ray | Dependency span reported error |
| 10:03:16 | CloudWatch Logs | `AccessDenied` for correlation ID |
| 10:05:00 | Operator | Rolled back configuration |
| 10:06:00 | Metrics | Error rate returned to baseline |

This example is hypothetical. Chronology suggests correlation yet does not prove causation on its own; verify the exact request, principal, resource, policy, and mutation.

### 11.3. Example: Lambda Suddenly Gets AccessDenied

Symptoms:

- API 5xx rises.
- Lambda `Errors` rises.
- Logs record `AccessDeniedException` reading a secret.
- Traces show failures on the Secrets Manager call.

Investigation:

1. Grab a correlation ID from API access logs.
2. Find Lambda logs by correlation ID and invocation request ID.
3. Open the trace to confirm Secrets Manager is the failing dependency.
4. Note the secret ARN and execution role ARN.
5. Search CloudTrail for `PutRolePolicy`, `AttachRolePolicy`, or related changes right beforehand.
6. Identify the acting principal and changed policy version.
7. Diff the current IAM policy against the prior version.
8. Restore approved least-privilege permissions.
9. Run smoke tests and monitor error metrics.

Never add `secretsmanager:*` just to clear the error. Grant exact `GetSecretValue` on the required secret ARN plus KMS permissions if using a customer managed key.

### 11.4. Example: Slow API Without Higher Error Counts

Symptoms:

- p95 latency jumps from 200 ms to 2 seconds.
- Error rate remains low.
- Traffic is steady.

Investigation:

1. Open traces for slow requests.
2. Identify whether DynamoDB/RDS/HTTP spans dominate duration.
3. Cross-check service maps and dependency metrics.
4. Inspect queue age, DB connections, throttling, or downstream latency.
5. Check CloudTrail for recent instance class, security group, route, or configuration changes.
6. Search logs for retries or timeouts occurring before eventual success.

A successful request can still be very slow due to internal retries. Watching only error counts misses this failure mode.

### 11.5. Example: Consumer Processing Duplicate Events

Symptoms:

- One order generates two notifications.
- SQS consumer logs show the same order ID multiple times.
- Queue depth rises after a wave of downstream timeouts.

Investigation:

1. Find event IDs and correlation IDs in producer/consumer logs.
2. Inspect traces or span links for message processing.
3. Check `ApproximateReceiveCount` and DLQ metrics.
4. Check whether consumers committed side effects before acking/deleting messages.
5. Check CloudTrail for changes to queue visibility timeouts or event source mappings.
6. Inspect idempotency records and transaction boundaries.

CloudTrail may reveal queue configuration changes; logs and traces pinpoint the exact message and code path. Remedies typically involve idempotent processing, proper visibility timeouts, and partial batch responses for Lambda event source mappings.

## 12. Sample Investigation Queries

### 12.1. Finding Logs by Correlation ID

~~~text
fields @timestamp, service, event, level, request_id, trace_id, message_id, @message
| filter correlation_id = "corr-91bd"
| sort @timestamp asc
| limit 500
~~~

### 12.2. Finding Errors by Service and Error Code

~~~text
fields @timestamp, service, error_code, error_type, correlation_id
| filter level = "ERROR"
| stats count() as failures by service, error_code
| sort failures desc
~~~

### 12.3. Finding Slow Requests

~~~text
fields @timestamp, service, operation, duration_ms, correlation_id, trace_id
| filter duration_ms > 1000
| sort duration_ms desc
| limit 100
~~~

### 12.4. Analyzing Error Trends per Minute

~~~text
filter level = "ERROR"
| stats count() as errors by bin(1m)
| sort bin(1m) asc
~~~

### 12.5. Finding CloudTrail Events by Principal

In CloudTrail Lake, query events performed by an assumed role:

~~~sql
SELECT
    eventTime,
    eventSource,
    eventName,
    userIdentity.arn,
    sourceIPAddress,
    errorCode,
    resources
FROM event_data_store
WHERE userIdentity.arn LIKE '%DeploymentRole%'
  AND eventTime > '2026-11-20 09:00:00'
ORDER BY eventTime DESC;
~~~

Data types and nested field syntax vary by event data store schema. Query narrow time windows first to avoid unnecessary data scans.

## 13. Correlating Telemetry for Specific AWS Services

### 13.1. API Gateway and Lambda

API Gateway provides access logs and execution logs depending on API type and settings. Lambda emits application logs and metrics including `Invocations`, `Errors`, `Duration`, `Throttles`, and `ConcurrentExecutions`. X-Ray links API requests to Lambda segments when tracing is enabled.

When investigating:

- Use API request ID to locate access logs.
- Use Lambda request ID to locate invocation logs.
- Use trace ID to open the distributed trace.
- Use CloudTrail to find changes to APIs, integrations, stages, or Lambda settings.

API Gateway request IDs and Lambda request IDs are distinct identifiers; log mappings or correlation IDs to connect them.

### 13.2. SQS and Lambda Event Source Mapping

SQS metrics detect backlogs; Lambda metrics reveal consumer errors or throttling; logs capture message IDs and receive counts; traces show per-message or per-batch processing.

Helpful metrics:

- `ApproximateNumberOfMessagesVisible`.
- `ApproximateAgeOfOldestMessage`.
- `NumberOfMessagesSent`/`Received`/`Deleted`.
- Lambda `Errors`, `Duration`, and `Throttles`.

CloudTrail reveals edits to queue policies, redrive policies, event source mappings, or visibility timeouts.

### 13.3. DynamoDB

DynamoDB emits metrics such as `ConsumedReadCapacityUnits`, `ConsumedWriteCapacityUnits`, `ThrottledRequests`, and latency metrics per configuration/namespace. Application logs should capture operation, table/index, and error codes; traces should instrument SDK/database calls.

CloudTrail records management events like `CreateTable`/`UpdateTable`; item-level data events require configuring supported event selectors. Never assume `GetItem`/`PutItem` calls appear in Event history unless data events are enabled.

### 13.4. RDS and Aurora

Combine:

- CloudWatch metrics: CPU, connections, free storage, latency, and replication lag.
- Database logs: error logs, slow query logs, or audit logs per engine/config.
- Application traces: connection acquisition and query timings.
- CloudTrail: changes to DB instances/clusters, parameter groups, subnet groups, and security groups.

Traces reveal slow queries; database engine logs and Performance Insights/Database Insights supply wait events, SQL statements, and lock contention details. CloudTrail alone cannot explain why a specific SQL query ran slowly.

### 13.5. ECS and EKS

For ECS, collect container logs, task/service events, CPU/memory, restarts, and deployment events. For EKS, combine application logs, Container Insights, Kubernetes events, configured control-plane audit logs, and traces.

CloudTrail records AWS API activity and integrated control-plane calls yet does not replace Kubernetes audit logs for every in-cluster action. Enable the right audit sources and manage retention.

### 13.6. EventBridge and Step Functions

EventBridge metrics and target invocation errors expose routing failures. Step Functions execution history shows which states failed, retried, or timed out. Logs/traces from Lambda/tasks supply execution detail; CloudTrail shows who edited state machines, rules, or targets.

For long workflows, preserve correlation IDs inside state machine inputs/outputs to link multiple executions and downstream events.

## 14. Incident Response Workflow

### 14.1. Classify the Incident

Before changing anything, classify:

- Availability: service unreachable.
- Latency: slow requests.
- Correctness: wrong results or duplicate/lost data.
- Security: unauthorized access or unexpected changes.
- Capacity: quotas, concurrency, or queue backlogs.
- Configuration: bad endpoints, policies, routes, or deployments.

Classification directs which telemetry signals to inspect first.

### 14.2. Scope Impact

Record:

- Start time and whether ongoing.
- Region/account/environment.
- Service and operation.
- Affected requests/tenants/devices.
- Error rates and latency.
- Whether data was lost or duplicated.
- Recent deployments or configuration changes.

Avoid jumping to root-cause conclusions from symptoms alone.

### 14.3. Build the Timeline

Normalize all timestamps to UTC. Align:

- Alert timestamps.
- API access logs.
- Application logs.
- Trace span timestamps.
- CloudTrail `eventTime`.
- Deployment/build events.
- Queue/database metrics.

Device or host clocks can drift; trust managed-service timestamps first and record client-measured times separately.

### 14.4. Verify Hypotheses

A strong hypothesis is testable. Example: "Errors began after the execution role lost permission to read the secret." Required evidence:

- `AccessDenied` logs naming the exact secret ARN.
- Traces pointing to failed Secrets Manager calls.
- CloudTrail events showing a prior policy or role edit.
- Current policy missing the required action/resource.
- Restoring least-privilege permission clears errors in smoke tests.

If any piece is missing, note confidence levels explicitly and keep gathering data.

### 14.5. Remediate and Verify

After fixing:

1. Run smoke tests on impacted flows.
2. Monitor error/latency metrics.
3. Inspect traces and logs for fresh requests.
4. Confirm no secondary regressions appeared.
5. Inspect remaining backlogs or queued data.
6. Confirm user experience has recovered.
7. Document changes and supporting evidence.

Never close an incident solely because an alarm returned to `OK`; verify business outcomes and data integrity.

## 15. Security and Access Control for Observability Data

### 15.1. Logs and Traces Are Sensitive Data

Logs can contain request payloads, customer identifiers, tokens, URL query strings, or stack traces. Traces can contain SQL statements, HTTP headers, or annotations. CloudTrail events can contain principal ARNs, IP addresses, and request parameters.

Apply:

- Data classification.
- Pre-log redaction.
- Encryption at rest and in transit.
- Least-privilege IAM access.
- Purpose-aligned retention.
- Access auditing on logs and traces.
- Separation between operational access and sensitive data inspection.

### 15.2. Avoid Logging Secrets

Never log:

- Passwords, access keys, session tokens.
- `Authorization` headers or cookies.
- Private keys and certificate private material.
- Secret Manager secret values.
- PII unnecessary for troubleshooting.

When user identification is required, use pseudonymized internal subject IDs. When payloads are needed for debugging, create masked reproductions in test environments.

### 15.3. IAM for CloudWatch and X-Ray

Scope permissions to read logs, query Logs Insights, view metrics, alarms, and traces by service/team. Permissions to create subscription filters, alter retention, delete log groups, or edit alarms can tamper with evidence and operations; never grant them broadly to all developers.

CloudTrail data is often centralized in a dedicated log archive account. Restrict bucket deletion, bucket policy edits, and lifecycle changes; use organization trails and appropriate controls for org-wide auditing.

### 15.4. Retention and Archiving

Choose retention based on:

- Incident investigation windows.
- Audit/compliance mandates.
- Storage and query costs.
- Access frequency.
- Data sensitivity.

Operational logs can use shorter retention than audit events. Archive CloudWatch Logs to S3 via subscription/export patterns or deliver CloudTrail trails directly to S3. Plan how archived data will be queried later and manage KMS decryption permissions.

### 15.5. Sampling and Data Minimization

Trace sampling and concise logging reduce costs without losing critical error visibility:

- Retain full error logs.
- Sample successful request traces at a fixed rate.
- Prioritize error or high-latency traces when using tail sampling.
- Use metrics for overall trends.
- Store minimal payloads.

## 16. Observability Cost and FinOps

### 16.1. Cost Drivers

Costs can arise from:

- CloudWatch Logs ingestion and storage.
- Logs Insights query scans.
- Custom metrics and high-cardinality dimensions.
- Large-scale alarms and dashboards.
- X-Ray trace ingestion/retrieval.
- OpenTelemetry collector compute and networking.
- CloudTrail data events and CloudTrail Lake ingestion/retention/queries.
- S3 archive storage and requests.
- KMS requests and data transfer.

Pricing varies by Region, volume, retention, and enabled features. Use the AWS Pricing Calculator and billing/CUR data to track actual spend.

### 16.2. Reducing Log Costs

- Use structured logs while logging only necessary fields.
- Never leave `DEBUG` permanently enabled in production.
- Set explicit retention on every log group.
- Filter or suppress noisy application logs.
- Avoid logging full payloads and responses.
- Enable verbose logging only during controlled investigation windows.

### 16.3. Reducing Metric Costs

- Avoid high-cardinality dimensions.
- Use appropriate metric aggregation.
- Never generate unique metrics per request or user.
- Retire unused metrics systematically.
- Design dashboards to query only essential metrics.

### 16.4. Reducing Trace Costs

- Tune sampling rates by traffic and criticality.
- Avoid creating spans for trivial operations with little diagnostic value.
- Avoid high-cardinality attributes.
- Tune collector batching and retries.
- Use error/slow traces for deep dives and metrics for overall health.

### 16.5. CloudTrail Coverage and Cost

Data events can generate huge volumes. Enable selectors only for buckets, prefixes, functions, or resource types requiring audit. CloudTrail Lake requires intentional retention and query patterns. Never disable mandatory auditing solely to save money; instead scope selectors, storage tiers, and access controls to real requirements.

### 16.6. Cost per Incident

Track observability spend per service or team alongside investigation time, incident counts, and MTTR. The goal is not minimizing telemetry at all costs, but keeping sufficient evidence to detect and resolve incidents within target SLAs.

## 17. Practical Walkthrough: Investigating a Checkout API

### 17.1. Architecture

A Checkout API uses API Gateway, Lambda, DynamoDB, EventBridge, and SQS. Lambda writes orders and emits events; a consumer calls a payment provider and updates status. CloudWatch collects logs/metrics, X-Ray traces requests, and CloudTrail audits AWS config changes.

~~~mermaid
flowchart TB
    U[Customer] --> A[API Gateway]
    A --> L[Checkout Lambda]
    L --> D[(DynamoDB Orders)]
    L --> E[EventBridge]
    E --> Q[SQS Payment Queue]
    Q --> P[Payment Worker]
    P --> X[Payment Provider]
    P --> D
    A -. request ID .-> C[Correlation ID]
    L -. structured logs .-> CW[CloudWatch]
    P -. structured logs .-> CW
    L -. spans .-> XR[X-Ray / OTel]
    P -. spans .-> XR
    AWS[AWS configuration API] --> CT[CloudTrail]
    CW --> INV[Incident investigation]
    XR --> INV
    CT --> INV
~~~

### 17.2. Standardizing Logs

Every service logs:

- `service` and `environment`.
- `correlation_id`.
- `trace_id` and `span_id` when available.
- `request_id` or `message_id`.
- `order_id`.
- `operation` and `outcome`.
- `duration_ms`.
- `deployment_id`.

The payment worker also logs SQS receive count and event ID without logging payment credentials or card data.

### 17.3. Defining Metrics

Business metrics:

- `checkout_started`.
- `checkout_succeeded`.
- `checkout_failed`.
- `payment_authorization_latency`.
- `orders_waiting_for_payment`.

Technical metrics:

- API 5xx.
- Lambda `Errors`/`Duration`/`Throttles`.
- SQS `ApproximateAgeOfOldestMessage`.
- DynamoDB `ThrottledRequests`.
- Payment provider latency/error rate.

### 17.4. Failure Scenario

Suppose checkout returns 500 while payment provider metrics look normal:

1. CloudWatch alarm alerts on API 5xx.
2. Logs Insights finds the `correlation_id` of a failing request.
3. Logs show Lambda hit `AccessDenied` publishing to EventBridge.
4. Traces confirm the DynamoDB write succeeded while `PutEvents` failed.
5. CloudTrail shows the event bus resource policy was just updated.
6. Inspection confirms the policy dropped permission for Checkout Lambda's role.
7. Restore `events:PutEvents` permission on the exact event bus.
8. Smoke test creates a test order and confirms the consumer receives the event.
9. Monitor error rates, queue age, and business success metrics.

This scenario shows logs supplying the error code, traces pinpointing where inside the request failure occurred, CloudTrail revealing the config mutation, and metrics confirming broad recovery.

## 18. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Enabling only application logs | Blind to trends and dependency latencies | Combine logs, metrics, and traces |
| Each service generating separate correlation IDs | Cannot stitch a single business flow | Propagate correlation context across HTTP/events |
| Confusing request IDs with trace IDs | Searching wrong records or traces | Store each ID type separately |
| Unstructured text logging | Hard to filter and aggregate | Use JSON structured logging |
| Logging full requests/responses | Exposes PII/secrets and spikes cost | Apply redaction and data minimization |
| Using user IDs as metric dimensions | Cardinality and cost explosion | Put IDs in logs/traces; keep dimensions bounded |
| Enabling tracing without testing propagation | Traces break across service boundaries | Verify trace context end-to-end |
| Sampling set too low | Misses rare errors | Pair full error logs/metrics with tuned sampling |
| Using CloudTrail instead of app logs | Misses business execution details | Use CloudTrail for audit, logs for app behavior |
| Omitting needed data event selectors | Blind to object-level activity | Configure selectors on critical resources |
| Treating Event history as an audit archive | Loses long-term lookup capability | Use trails or CloudTrail Lake with retention |
| Inferring root cause from timeline alone | Confuses correlation with causation | Verify requests, resources, policies, and diffs |
| Infinite retention | Growing storage costs and data risk | Set purpose-based retention/archival |

## 19. Observability Implementation Checklist

### Design

1. Identify service owners, SLOs, and critical business flows.
2. Standardize log schemas and identifier fields.
3. Separate request IDs, correlation IDs, trace IDs, and event IDs.
4. Design trace propagation across HTTP, queues, and workflows.
5. Select metrics and bounded-cardinality dimensions.
6. Define CloudTrail management/data event coverage.
7. Classify data and set retention.

### Implementation

1. Emit structured logs with UTC timestamps.
2. Enable CloudWatch metrics, dashboards, and alarms.
3. Instrument traces via X-Ray or OpenTelemetry/ADOT.
4. Test propagation across service boundaries.
5. Configure CloudTrail trails/event data stores per audit needs.
6. Test Logs Insights and audit queries.
7. Apply least-privilege read access to observability data.

### Operations

1. Start from alarms and scope impact.
2. Query logs by correlation/request ID.
3. Open traces to locate failing or slow spans/dependencies.
4. Cross-check metrics and queue/database health.
5. Search CloudTrail for changes near incident onset.
6. Build timelines and validate hypotheses.
7. Remediate, run smoke tests, and monitor metrics.
8. Archive incident evidence and update runbooks.
9. Periodically review retention, sampling, and cost.

## 20. Conclusion

Logs, metrics, and traces answer distinct questions: logs detail discrete events, metrics track trends and magnitude, and traces map request execution paths. AWS CloudTrail adds audit visibility into acting principals and API changes on AWS resources. When applications adopt structured logging, consistent correlation IDs, and trace context propagation, engineers can pivot from an alarm to an exact request, pinpoint failing dependencies, and cross-check configuration changes.

CloudWatch centralizes logs, metrics, alarms, dashboards, and queries; X-Ray and OpenTelemetry illuminate distributed traces; CloudTrail investigates API actions and mutations. Every tool requires proper coverage, permissions, sampling, and retention. Absence of a CloudTrail event does not guarantee no change occurred if that event type was not captured; absence of a trace does not prove a request never ran if sampling or propagation was incomplete.

An effective investigation starts from symptoms, scopes impact, queries logs by identifiers, inspects traces, correlates metrics, and aligns CloudTrail events on a timeline. Post-fix verification requires smoke tests, business metrics, and fresh telemetry. Designing observability this way makes AWS systems easier to diagnose, shortens recovery times, and keeps telemetry costs under control.

## 21. Official References

- [Amazon CloudWatch documentation](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/WhatIsCloudWatch.html)
- [CloudWatch Logs Insights query syntax](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_QuerySyntax.html)
- [CloudWatch Embedded Metric Format](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Embedded_Metric_Format.html)
- [CloudWatch Application Signals](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Application-Monitoring-Sections.html)
- [AWS X-Ray concepts](https://docs.aws.amazon.com/xray/latest/devguide/xray-concepts.html)
- [AWS X-Ray trace header](https://docs.aws.amazon.com/xray/latest/devguide/xray-concepts.html#xray-concepts-tracingheader)
- [AWS Distro for OpenTelemetry](https://aws-otel.github.io/)
- [OpenTelemetry documentation](https://opentelemetry.io/docs/)
- [AWS CloudTrail user guide](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-user-guide.html)
- [CloudTrail event history](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/view-cloudtrail-events.html)
- [CloudTrail data events](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/logging-data-events-with-cloudtrail.html)
- [CloudTrail Lake](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-lake.html)
- [CloudTrail log file integrity validation](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-log-file-validation-intro.html)
- [AWS Well-Architected Framework – Operational Excellence](https://docs.aws.amazon.com/wellarchitected/latest/operational-excellence-pillar/welcome.html)
