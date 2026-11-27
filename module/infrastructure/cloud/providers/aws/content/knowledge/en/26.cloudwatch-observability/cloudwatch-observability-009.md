# AWS X-Ray, Service Maps, and Distributed Trace Analysis

An ordering request in a Java Spring Boot system may traverse API Gateway, Application Load Balancer, orders-api, DynamoDB, SQS, and an email-sending Lambda worker. Users only see a 4-second request or an HTTP 500; logs from each service might all say "request failed" without showing which hop caused the error.

**Distributed tracing** records the path of a request across multiple components. AWS X-Ray ingests trace data, stitches together parts sharing the same trace ID, and builds a service graph depicting services, dependencies, latency, and errors. In CloudWatch, you can open Trace Map, inspect an individual trace, read segment/span timelines, and filter requests with errors or high processing times.

For Java, note an important change: effective **25/02/2026**, the AWS X-Ray SDK and X-Ray Daemon entered maintenance mode, receiving updates primarily for security fixes. AWS recommends using **OpenTelemetry (OTel) or AWS Distro for OpenTelemetry (ADOT)** to instrument new applications and send traces to X-Ray. X-Ray remains the place to view traces, trace maps, and call X-Ray APIs; the main shift is in how trace data is generated and shipped.

This lesson belongs to the **Observability with CloudWatch** chapter of the **CLOUD_PROVIDERS_AWS** module. Content focuses on the trace data model, Java/Spring Boot instrumentation, sampling, propagation, service maps/trace maps, filter expressions, and root-cause workflows in distributed systems.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain what problems distributed tracing solves in multi-service architectures.
2. Distinguish trace, trace ID, segment, subsegment, span, and span context.
3. Describe how X-Ray constructs a service graph from segments sharing a trace ID.
4. Explain inferred segments and the relationship between upstream edges and downstream nodes.
5. Distinguish X-Ray Trace Map from CloudWatch Application Map in Application Signals.
6. Instrument Java/Spring Boot using ADOT or the OpenTelemetry Java agent.
7. Create custom spans and attributes for business logic requiring analysis.
8. Propagate trace context across HTTP and AWS services.
9. Choose a sampling strategy and evaluate its impact on cost and coverage.
10. Distinguish X-Ray annotations from metadata.
11. Interpret nodes, edges, timelines, response time distributions, and error flags.
12. Use X-Ray filter expressions to find faults, throttles, latency, and root causes.
13. Analyze traces across SQS, Lambda, and AWS dependencies.
14. Integrate traces with metrics, logs, and Application Signals.
15. Diagnose missing segments, broken context propagation, and instrumentation gaps.
16. Plan a migration from X-Ray SDK/Daemon to OpenTelemetry.

## 2. What Is Distributed Tracing?

In monolithic applications, a request usually executes inside a single process, so logs and stack traces are often sufficient to pinpoint bugs. In microservice architectures, a request can cross multiple processes, containers, AWS services, and queues. Each component maintains its own logs, clocks, and request ID conventions.

Distributed tracing creates an end-to-end identifier that links the activities of all components participating in the same logical request.

Example:

    Browser
       |
       v
    API Gateway
       |
       v
    orders-api (Spring Boot)
       |                 \
       v                  v
    DynamoDB              SQS
                             |
                             v
                       invoice-worker (Lambda)
                             |
                             v
                         S3 / SES

A trace for an order request can capture API Gateway forwarding time, orders-api validation time, DynamoDB call time, SQS message publish time, and a linked trace to the Lambda consumer when propagation is supported and configured properly.

Traces help answer: which service is slow, which dependency is failing, where wait time sits, and where an error originated.

### 2.1. Logs, Metrics, and Traces Complement Each Other

| Signal | Answers the Question | Example |
|---|---|---|
| Logs | What happened? | Exceptions, business events, masked request data |
| Metrics | What is the trend and blast radius? | Error rate, request count, p95 latency |
| Traces | Where did a request go and where did it spend time? | orders-api waited 1.8 seconds on DynamoDB |
| Events | What changes occurred around the same time? | Deployments, scaling, configuration changes |

Metrics/Alarms detect issues; traces map the request path; logs supply details to understand why. No single signal completely replaces the others.

## 3. AWS X-Ray Data Model

X-Ray uses the following core concepts:

| Concept | Meaning |
|---|---|
| Trace | Collection of data for one logical request, linked by trace ID |
| Trace ID | Shared identifier for a request across multiple services |
| Segment | Data sent by a service about the work that service performed |
| Subsegment | Detailed part of a segment, usually describing a downstream call or processing block |
| Service graph | Graph of services/resources and connections inferred from traces |
| Trace Map | UI visualizing the service graph and operational signals |
| Annotation | Indexed key-value pair used to filter traces |
| Metadata | Additional non-indexed data not used for search |

A segment typically records service/resource name, request/response details, start/end timestamps, subsegments, and error/exception information. A subsegment can record calls to AWS services, external HTTP APIs, SQL databases, or custom-instrumented application code blocks.

### 3.1. Trace ID and Parent-Child Relationships

Trace IDs connect all segments/spans belonging to the same request. Each segment or span has its own ID and can reference a parent to represent invocation hierarchy.

    Trace: request-123
       |
       +-- API Gateway segment
       |
       +-- orders-api segment
              |
              +-- validate-order span
              |
              +-- DynamoDB subsegment/span
              |
              +-- SQS SendMessage subsegment/span

If context propagation is lost, downstream services may start a new trace or produce spans with broken parents. The trace map then no longer displays the complete business flow.

## 4. Segments, Subsegments, and Inferred Segments

**Segments** represent the work performed by a service while handling a request. For an HTTP server, a segment records method, URL, response status, duration, and exceptions.

**Subsegments** capture the caller's perspective of downstream calls. For instance, when orders-api calls DynamoDB via the AWS SDK, instrumentation records a subsegment for that call. A subsegment can include AWS service/operation, round-trip time, outcome, throttling, or exceptions.

**Inferred segments** appear when a downstream service/resource does not emit its own segment. X-Ray can construct an inferred segment from the caller's subsegment to depict that dependency on the trace map.

If the downstream service is instrumented and emits its own segment, the service graph node uses the downstream segment's data while the edge between the two nodes uses the caller's subsegment data. Both views complement each other:

- The downstream segment shows how long the service actually spent processing.
- The upstream subsegment shows the full round-trip time the caller waited, including network and queuing delays.

Do not mistake an inferred segment for proof that you instrumented internal code inside an AWS service.

## 5. Service Graph and Trace Map

X-Ray groups segments sharing a trace ID to build a service graph. Each node represents a service or resource; edges represent call relationships between them.

Trace Map helps operators inspect topology and dependencies, spot services with errors/faults/throttles, detect high-latency edges, filter traces passing through specific nodes/edges, and open individual request timelines.

Service names should be stable and meaningful. If each instance invents a different name, the map explodes into too many nodes and becomes hard to read. Use logical service names like orders-api, payment-service, and invoice-worker; capture instance, pod, task, or version details via appropriate resource attributes.

### 5.1. Colors and States

In CloudWatch X-Ray Trace Map, node borders indicate problem types:

| Color | Meaning |
|---|---|
| Red | Server fault, HTTP 5xx |
| Yellow | Client error, HTTP 4xx |
| Purple | Throttling, HTTP 429 |

The legacy X-Ray console service map could show green for successful requests. When working in CloudWatch Trace Map, follow the legend of the current UI to interpret colors. Node colors are directional cues; open nodes/edges, inspect metrics, and examine specific traces to verify root cause.

## 6. How Do Trace Map and Application Map Differ?

CloudWatch has two related map experiences serving different perspectives:

| Interface | Purpose |
|---|---|
| **X-Ray Trace Map** | Service graph built from trace data; drills down from nodes/edges to traces and segment timelines |
| **Application Signals Application Map** | Application map organized by services, clients, canaries, and dependencies; shows SLI/SLO health and operational metrics |

Trace Map centers on trace data and request paths. Application Map belongs to Application Signals and suits tracking service health, SLOs, and topology from an application perspective.

Application Signals correlates service operation metrics with X-Ray traces, CloudWatch logs, and Container Insights. From an anomalous metric point, operators can jump straight to correlated traces to find root cause.

Do not assume every node in Application Map has detailed traces. An uninstrumented service may appear with limited telemetry.

## 7. Status of AWS X-Ray SDK and Daemon in 2026

AWS announced that X-Ray SDKs and X-Ray Daemon entered **maintenance mode on 25/02/2026**. In maintenance mode, AWS restricts releases primarily to security fixes; the legacy SDKs/Daemon are no longer the recommended path for new instrumentation.

AWS recommends:

- Using OpenTelemetry SDKs or ADOT instrumentation to generate traces.
- Using OpenTelemetry Collector or CloudWatch Agent to receive, process, and export traces.
- Continuing to use X-Ray as the trace backend and viewing data in CloudWatch Trace Map/Traces.
- Using Application Signals when service health, metrics, and SLO views are needed.

This does not mean the X-Ray service is shutting down. Trace data from OpenTelemetry can still be converted into X-Ray segments/subsegments and displayed in CloudWatch.

### 7.1. Mapping X-Ray Concepts to OpenTelemetry

| X-Ray | OpenTelemetry |
|---|---|
| Recorder | Tracer Provider and Tracer |
| Segment | Server span |
| Subsegment | Non-server span |
| Annotation/Metadata | Span attributes |
| Sampling rules | Sampler |
| Emitter | Span exporter |
| Trace context | Span context |
| X-Ray Daemon | OpenTelemetry Collector or CloudWatch Agent |
| Service plugin | Resource detector |

When exporting traces to X-Ray, server spans become segments and other spans become subsegments. OpenTelemetry attributes map to metadata in raw X-Ray data by default. Selected attributes can be marked as annotations via X-Ray exporter configuration.

## 8. Modern Java Tracing Architecture on AWS

A common deployment pattern:

    Spring Boot application
       |
       | OpenTelemetry Java agent / SDK
       | HTTP + OTLP
       v
    ADOT Collector or CloudWatch Agent
       |
       | Batch / process / export
       v
    AWS X-Ray
       |
       +--> CloudWatch X-Ray Trace Map
       +--> CloudWatch Traces
       +--> Application Signals (if enabled)

The application creates spans and attaches context. The Collector receives OTLP, batches spans, and exports traces to X-Ray. The Collector can run alongside the application or centrally depending on compute platform, network, and operations.

### 8.1. Choosing Auto-Instrumentation vs. Manual Instrumentation

| Approach | Advantage | Best Suited When |
|---|---|---|
| ADOT/OpenTelemetry Java agent | Instruments supported HTTP servers, clients, JDBC, and frameworks with minimal code changes | Getting Spring Boot tracing running quickly |
| OpenTelemetry Spring Boot starter | Integrates via application dependencies and configuration | Wanting instrumentation managed inside the application |
| OpenTelemetry SDK API | Creates spans for custom business logic | Measuring specific code blocks or custom business workflows |
| Legacy X-Ray SDK | Compatible with existing instrumented apps | Maintaining during a controlled migration |

For new projects, prefer ADOT/OpenTelemetry. Add manual spans only for business logic not covered by auto-instrumentation; avoid creating duplicate spans for the same HTTP/DB call.

## 9. Java Auto-Instrumentation with ADOT

ADOT provides a Java auto-instrumentation agent built on OpenTelemetry. The agent automatically instruments supported frameworks/libraries using bytecode instrumentation.

Example running a Spring Boot JAR with the agent:

    java \
      -javaagent:/opt/aws-opentelemetry-agent.jar \
      -Dotel.service.name=orders-api \
      -Dotel.resource.attributes=deployment.environment.name=prod,service.version=1.4.2 \
      -Dotel.exporter.otlp.endpoint=http://127.0.0.1:4317 \
      -Dotel.exporter.otlp.protocol=grpc \
      -jar orders-api.jar

This example assumes the Collector/CloudWatch Agent listens for OTLP gRPC on localhost:4317. If the collector runs on another host or task, replace the endpoint with a network-reachable address.

Key properties:

- service.name: logical name of the service.
- deployment.environment.name: deployment environment.
- service.version: application version.
- OTLP endpoint/protocol: destination where the agent sends spans.
- Propagators: context format injected/extracted across services.

Actual agent filename, version, and configuration depend on the ADOT Java agent distribution you package. Pin agent versions and verify compatibility with your JDK, Spring Boot, and instrumentation libraries.

### 9.1. Propagators

OpenTelemetry typically uses W3C Trace Context with `traceparent` and `tracestate` headers. X-Ray uses the `X-Amzn-Trace-Id` header.

When interacting with AWS services or systems already using X-Ray headers, configure the appropriate X-Ray propagator in your ADOT/OpenTelemetry setup. A configuration may require propagators such as `tracecontext,baggage,xray`; confirm your agent/distribution includes the corresponding extensions.

Do not generate a new root trace ID in every service. Extract parent context from incoming requests, create child spans, and inject context into outgoing requests.

## 10. Collector Receiving and Exporting Traces to X-Ray

ADOT Collector or OpenTelemetry Collector can receive OTLP and use the AWS X-Ray exporter.

Abbreviated collector configuration example:

    receivers:
      otlp:
        protocols:
          grpc:
            endpoint: 0.0.0.0:4317
          http:
            endpoint: 0.0.0.0:4318

    processors:
      batch:

    exporters:
      awsxray:

    service:
      pipelines:
        traces:
          receivers: [otlp]
          processors: [batch]
          exporters: [awsxray]

This is a skeleton configuration. Available components, endpoints, Region, TLS, and authentication depend on the deployed Collector/ADOT release. Validate configs against your exact version's schema before deploying.

The Collector can also perform resource detection to add ECS/EC2/EKS metadata, batch processing to cut export overhead, filtering to drop health checks or noise, retry/queuing to handle export failures gracefully, and tail sampling when keeping traces requires inspecting the complete trace first.

### 10.1. IAM for the Trace Exporter

The Collector/CloudWatch Agent role needs permissions to ship traces to X-Ray, typically:

- `xray:PutTraceSegments`
- `xray:PutTelemetryRecords`

If remote sampling via X-Ray sampling rules is configured, add permissions to read sampling rules/targets/statistics as required. Grant only the permissions actually used by the exporter/sampler.

Prefer EC2 IAM roles, ECS task roles, EKS workload identities, or Lambda execution roles over long-lived access keys. Never place credentials inside collector configs.

## 11. Manual Instrumentation in Java

Auto-instrumentation does not understand every business step. You can create spans for key business logic such as reserving inventory, calculating shipping, or validating payments.

Example using the OpenTelemetry API:

    import io.opentelemetry.api.GlobalOpenTelemetry;
    import io.opentelemetry.api.trace.Span;
    import io.opentelemetry.api.trace.StatusCode;
    import io.opentelemetry.context.Scope;

    public class OrderService {
        private final Tracer tracer =
            GlobalOpenTelemetry.getTracer("orders-api");

        public void reserveInventory(String orderType) {
            Span span = tracer.spanBuilder("inventory.reserve").startSpan();

            try (Scope scope = span.makeCurrent()) {
                span.setAttribute("order.type", orderType);
                inventoryClient.reserve();
            } catch (RuntimeException ex) {
                span.recordException(ex);
                span.setStatus(StatusCode.ERROR, "Inventory reservation failed");
                throw ex;
            } finally {
                span.end();
            }
        }
    }

This snippet creates a child span within the active context. In real applications, inject Tracer via configuration/beans where appropriate and avoid initializing a separate TracerProvider if the Java agent already manages the global provider.

### 11.1. Meaningful Span Naming

Span names should describe the operation without embedding variable data:

- Good: `orders.reserve`, `payment.authorize`, `inventory.lookup`.
- Poor: `orders/12345`, `GET /users/987654` when paths contain dynamic IDs, `query-customer-email@example.com`.

Stable names let you aggregate latency and errors by operation while avoiding cardinality explosion.

### 11.2. Attributes, Annotations, and Metadata

OpenTelemetry span attributes are key-value metadata. When exported to X-Ray:

- Attributes default to metadata.
- Attributes listed in `aws.xray.annotations` become indexed annotations for filtering.
- Choose annotations for searchable fields like order tier or region group.
- Use metadata for extra details that do not need indexing.

Example marking an attribute as an X-Ray annotation:

    import io.opentelemetry.api.common.AttributeKey;
    import java.util.List;

    span.setAttribute("order.tier", "premium");
    span.setAttribute(
        AttributeKey.stringArrayKey("aws.xray.annotations"),
        List.of("order.tier")
    );

X-Ray indexes up to 50 annotations per trace. Pick keys valuable for investigation while keeping cardinality bounded. Never put passwords, access tokens, email addresses, card numbers, or sensitive payloads into annotations or metadata.

## 12. Propagating Trace Context over HTTP

A trace is useful only when services link their spans together. Over HTTP, instrumentation usually injects and extracts context automatically.

    orders-api
       |
       | traceparent / X-Amzn-Trace-Id
       v
    payment-service
       |
       | trace context
       v
    fraud-check-service

Key points:

- Both services must use compatible propagators.
- Proxies and load balancers must preserve the required headers.
- HTTP clients must be instrumented or inject context explicitly.
- Do not start a new root trace when a valid parent context already exists.
- Do not overwrite context mid-flight without clear justification.
- For async execution, propagate context across executor and reactive boundaries.

Trace context is not an authentication mechanism. Never use trace IDs to authorize requests or identify users.

### 12.1. Trusting Headers from External Clients

X-Ray tracing headers can arrive from SDKs, AWS services, or client requests. An untrusted client could forge trace IDs or sampling decisions. For public requests, ingress design must control whether client-supplied headers are accepted or stripped per AWS guidance and system tracing requirements.

Do not let external clients dictate sampling arbitrarily or inject spoofed trace contexts to skew telemetry. Keep internal trace context consistent once ingress establishes the root/parent context.

## 13. Trace Context in SQS and Asynchronous Processing

HTTP requests and message queues have different lifecycles. A message may be produced in service A and processed seconds or minutes later by Lambda or worker B.

When a service sends a message:

1. Instrumentation creates a span for the publish operation.
2. Trace context is carried via whatever propagation mechanism the integration supports.
3. The consumer extracts context upon receiving the message.
4. The consumer creates a processing span linked to the parent trace or via a span link per the chosen model.
5. Trace Map can depict producer/consumer relationships when integrations and trace data support it.

CloudWatch X-Ray Trace Map can render a connected view for event-driven flows using SQS and Lambda; producer/consumer links may appear as dashed edges.

If the consumer fails to receive context, traces split apart. Check message attributes/system attributes and the propagation capabilities of your SDK/runtime; never assume every queue and client version passes context identically.

## 14. Sampling: Choosing Which Requests to Trace

Tracing every request increases cost, export bandwidth, and telemetry storage. Sampling selects a representative subset of requests.

Two common approaches:

- **Head sampling:** decides at the start of the trace before knowing the final outcome. Fast and low-memory.
- **Tail sampling:** the collector waits for the full trace and decides to keep or drop based on errors, latency, or attributes. Captures failing/slow traces preferentially, but requires state, memory, and trace-aware routing.

### 14.1. Legacy X-Ray SDK Default Sampling

X-Ray SDK documentation describes the legacy default sampling rule as:

- Record the first request each second.
- Record 5% of additional requests.

That is the legacy X-Ray SDK default, not a universal default across OpenTelemetry SDKs or ADOT agents. With OTel, sampling depends on the sampler and configuration you deploy.

### 14.2. Parent-Based Sampling

Sampling usually respects the root/parent span's decision. If the entry service sets sampled=false, downstream services normally inherit that decision.

A sampling rule configured only on a downstream service may have no effect if requests always arrive with an upstream sampling decision. Set sampling policies at trace entry points or configure a parent-based sampler intentionally.

### 14.3. Designing a Sampling Policy

| Traffic | Consideration |
|---|---|
| State-changing transactions | Higher rate or prioritized by business risk |
| Very high-volume read APIs | Lower rate, still statistically representative |
| Health checks/heartbeats | Sample very low or exclude entirely |
| Error/latency anomalies | Tail sampling can retain failing/slow traces |
| Internal background jobs | Sample based on volume and investigative value |

Sampling must never replace metrics. Even when traces are sampled, keep full request/error/latency metrics to measure SLOs accurately.

## 15. Reading Trace Map in CloudWatch

In the AWS Console:

1. Select the correct account and Region.
2. Open CloudWatch.
3. Under X-Ray traces, select **Trace Map**.
4. Choose a time range covering the incident.
5. Select the service node or edge to investigate.
6. Inspect metrics, alerts, and response time distribution.
7. Click View traces or View filtered traces to open the trace list.
8. Select a trace ID to open Trace details.
9. Use View logs if supported by the node to pivot to correlated logs.

Nodes represent services/resources. Edges represent calls between two nodes. If a node is red while outbound edges look normal, the fault likely lies inside the service's internal logic. If an edge to a dependency shows high latency or throttling, investigate that dependency.

Trace Map supports cross-account tracing when CloudWatch/X-Ray cross-account observability and permissions are properly configured.

### 15.1. Selecting a Node or an Edge?

- Select a **node** to inspect requests passing through a specific service.
- Select an **edge** when you suspect a specific dependency call is failing.
- Filter by error status to isolate failed requests.
- Filter by response time distribution to isolate slow request cohorts.
- Pivot from the map to trace details to inspect exact segments and subsegments.

A large service map can be overwhelming. Zoom in, filter by group, and narrow the time range to focus on the relevant topology slice.

## 16. Reading Trace Details and Timelines

Trace details typically include a mini Trace Map of nodes involved in the request, a trace summary with URL/operation, response code, duration, and timestamp, a segments timeline showing each segment/subsegment duration, and details containing metadata, annotations, exceptions, and downstream calls.

Example timeline:

    0 ms       orders-api server span starts
    12 ms      validate-order finishes
    20 ms      DynamoDB GetItem starts
    1,420 ms   DynamoDB GetItem finishes
    1,440 ms   SQS SendMessage starts
    1,470 ms   SQS SendMessage finishes
    1,510 ms   orders-api returns HTTP 201

If DynamoDB accounts for nearly the entire duration, inspect latency, throttling, retries, hot partitions, connection pools, and networking. If an internal span consumes significant time without child spans, add instrumentation inside that code path.

Do not sum the durations of nested spans to calculate total request duration. Parent spans already encompass child span durations; adding them double-counts time.

## 17. X-Ray Filter Expressions

X-Ray provides a filter expression language to filter traces by errors, duration, services, edges, annotations, and request attributes.

### 17.1. Filtering Errors

Find traces with server faults:

    fault

Find client errors:

    error

Find throttling:

    throttle

Find unsuccessful traces:

    !ok

These keywords reflect request-level trace status. A downstream error caught and handled by the application without failing the root request may not appear when filtering only for error. In that case, filter on the specific service or edge.

### 17.2. Filtering by Duration and Status

Find requests with response time over 2 seconds:

    responsetime > 2

Find requests with total duration between 3 and 8 seconds:

    duration >= 3 AND duration <= 8

Find status codes other than 200:

    http.status != 200

Find URL paths:

    http.url CONTAINS "/orders/"

X-Ray filter expressions express responsetime and duration in seconds. Check syntax documentation before copying operators into live queries.

### 17.3. Filtering by Service and Edge

Find traces with a fault at orders-api:

    service("orders-api") { fault }

Find traces with throttling on the edge between caller and dependency:

    edge("orders-api", "DynamoDB") { throttle }

Service and destination names must match node names in your environment's trace graph. When a node uses an AWS service type or ARN, select the exact displayed name and verify filter expression syntax.

### 17.4. Filtering by Annotation

If the application records a `tenantTier` annotation, find traces for the premium tier:

    annotation.tenantTier = "premium"

For annotation keys containing dots, use bracket syntax per filter expression documentation.

Only fields recorded as annotations can be filtered as annotations. Metadata is not indexed and cannot substitute for annotations in searches.

### 17.5. Root Cause Filters

You can filter by root cause service or exception. For example, find fault traces whose root cause involves a specific service:

    rootcause.fault.service { name = "payment-service" }

Root cause analysis narrows down which node or exception contributed to a fault or latency spike. Always confirm findings using timelines and logs.

## 18. X-Ray Groups

Groups define subsets of traces via filter expressions. Each group generates its own service graph, trace summaries, and CloudWatch metrics.

Example grouping requests with payment errors:

    service("payment-service") { fault OR error }

Groups are useful for tracking specific business flows or dependency subsets that operations teams watch closely.

Notes:

- Groups evaluate new traces as X-Ray ingests them.
- Updating a filter expression does not rewrite previously stored data.
- Changing filters can blend old and new criteria in group graphs.
- Groups may incur costs based on matching traces retrieved.

Avoid creating too many overlapping groups. Maintain only groups with clear owners and investigative purposes.

## 19. Latency Analysis: Finding the Critical Path

When requests slow down, start from total duration and follow the longest spans/subsegments.

1. Pick a trace with high duration or an SLO breach.
2. Inspect the root/server span and total request duration.
3. Identify the child span consuming the largest share of time.
4. Determine whether time was spent in CPU work, network wait, connection pool wait, or downstream services.
5. Open subsegments/edges to inspect AWS operations and resources.
6. Cross-reference metrics and logs at the exact timestamp.
7. Compare a fast trace against a slow trace for the same operation.

Common patterns:

| Pattern in Trace | Investigation Direction |
|---|---|
| Single very long DynamoDB subsegment | Throttling, hot keys, retries, network, or capacity |
| Repeated calls to the same API | N+1 calls, nested retries, or loops |
| Long HTTP client span but short server span | Network delay, queuing, or client-side waits |
| Long JDBC span | Query plan, locks, connection pool, DB load |
| Lambda span with large init phase | Cold start, runtime initialization, package size |
| Long parent span with missing child spans | Instrumentation gap or uninstrumented code path |
| Multiple services slow simultaneously | Shared dependency, network path, or system-wide load |

Do not assume the longest span is automatically the root cause. A span can include queue/network wait or wrap nested child spans. Reconcile timestamps and compare caller vs. callee perspectives.

## 20. Error Analysis: Fault, Error, and Throttle

X-Ray categorizes error states:

| Status | Meaning |
|---|---|
| Error | Client error, typically HTTP 4xx |
| Fault | Server fault, typically HTTP 5xx |
| Throttle | Throttling, typically HTTP 429 |

A downstream error may be caught and retried successfully before returning a response. The root trace may show no fault even though a subsegment reveals failed dependency calls. Therefore:

- Inspect both root segments and subsegments.
- Look for services/edges showing errors or throttles.
- Inspect exceptions and AWS error codes.
- Cross-reference retry metrics and logs.
- Check whether requests retried multiple times before succeeding.

Filtering only by root fault misses handled dependency failures hidden inside successful requests.

## 21. Analyzing AWS SDK Calls

In Java services calling AWS SDK for Java 2.x, instrumentation can emit spans/subsegments for DynamoDB, S3, SQS, Secrets Manager, and other supported AWS services.

When a dependency span looks abnormal, check service/operation name, AWS Region/endpoint, resource ARN/table/bucket/queue if recorded, error code/HTTP status/request ID if captured, retry attempts/total latency, throttling/service-side errors, credential refreshes, DNS, VPC endpoints, and connection pools.

Never record request/response bodies or credentials just to enrich traces. Attributes should capture just enough detail to classify errors and trace flows.

## 22. Combining Traces with CloudWatch Application Signals

Application Signals delivers a service-centric view of application health:

- Services page highlights services with elevated latency or faults.
- Service details show volume, availability, latency, faults/errors, and dependencies.
- Application Map visualizes clients, services, and dependency topology.
- SLOs/SLIs show whether services meet reliability objectives.
- Correlated traces let you launch X-Ray trace details from anomalous metric points.
- Correlated logs display logs tied to a service operation.

Investigation workflow:

    Application Signals Services
          |
          v
    Service operation with abnormal latency/errors
          |
          v
    Select metric data point
          |
          v
    Correlated traces + logs
          |
          v
    Open X-Ray Trace details
          |
          v
    Analyze segment timeline and dependency edges

Application Signals supports Java and several other runtimes on AWS-documented compute platforms. Check platform, Region, and setup requirements before enabling. Application Signals carries separate pricing and may require additional agents/permissions.

## 23. CLI and X-Ray APIs

You can search traces via AWS CLI or invoke X-Ray APIs in automation.

Fetch trace summaries by time range and filter expression:

    aws xray get-trace-summaries \
      --start-time <START_EPOCH_SECONDS> \
      --end-time <END_EPOCH_SECONDS> \
      --filter-expression 'fault'

Output includes trace IDs and summary fields. Use those trace IDs to fetch full traces:

    aws xray batch-get-traces \
      --trace-ids <TRACE_ID_1> <TRACE_ID_2>

Key APIs:

| API | Purpose |
|---|---|
| GetTraceSummaries | Find trace IDs and summaries by time range/filter |
| BatchGetTraces | Retrieve segment documents for one or more traces |
| GetServiceGraph | Retrieve service graph by time range/group |
| GetTraceGraph | Retrieve the graph for a single trace |
| GetGroups | List X-Ray groups |
| GetSamplingRules | Read sampling rules |

X-Ray APIs accept start/end times as Unix epoch seconds. Handle pagination tokens and result limits; never assume a single API response returns all traces in the window.

IAM roles need matching read-only permissions such as xray:GetTraceSummaries, xray:BatchGetTraces, xray:GetServiceGraph, or xray:GetTraceGraph per workflow. Grant only the APIs your automation actually calls.

## 24. Trace ID Formats and W3C Compatibility

X-Ray trace IDs follow the format:

    1-<8-hex-timestamp>-<24-hex-unique-id>

W3C Trace Context uses a 32-hex-character trace ID alongside the traceparent header. OpenTelemetry can generate W3C-format trace IDs, and the X-Ray console can display W3C trace IDs in their equivalent X-Ray format when querying.

Example W3C trace ID:

    4efaaf4d1e8720b39541901950019ee5

X-Ray equivalent:

    1-4efaaf4d-1e8720b39541901950019ee5

When correlating logs, traces, and support tickets, preserve the exact format returned by your system. Never truncate trace IDs to short substrings that risk collisions.

## 25. Cross-Account and Event-Driven Tracing

Traces can span multiple AWS accounts when cross-account observability and permissions are properly configured. Trace Map/Traces can display multi-account telemetry in a unified view.

In event-driven architectures:

- Producer emits a message with trace context.
- SQS stores and delivers the message.
- Lambda or a worker processes the message.
- Consumer creates spans for processing and downstream calls.
- Trace map links producer and consumer when instrumentation and propagation support it.

If traces stop at SQS, check consumer instrumentation, message context, trace write permissions, and export timing. Do not blame the queue for dropping traces simply because an edge is missing on the map; sampling or integration gaps may be the reason.

## 26. Reasons Traces Are Incomplete

A trace may miss segments or spans because:

1. A service is not instrumented.
2. A library or protocol is unsupported by auto-instrumentation.
3. Trace context was not injected or extracted properly.
4. Sampling dropped the trace at the root.
5. An async task failed to propagate context.
6. The Collector failed to receive or export spans.
7. The application or collector exited before flushing.
8. IAM permissions or network rules blocked export.
9. Resource/service names are inconsistent.
10. Query time range or filter expression excluded the trace.

### 26.1. Ordered Verification Steps

- Confirm the application emits spans in a local/test environment.
- Inspect agent startup logs and version compatibility.
- Verify the OTLP receiver endpoint and protocol.
- Verify the Collector pipeline includes traces receiver, processor, and exporter.
- Verify IAM permissions on the collector role.
- Verify network paths, security groups, and VPC endpoints to the collector or AWS.
- Check the sampling decision at the root.
- Inspect `traceparent`/`X-Amzn-Trace-Id` headers between services.
- Verify time range and Region in CloudWatch.

Do not leave full debug logging enabled in production long-term; telemetry exporters can log internal details and inflate log volume.

## 27. Security and Trace Data Quality

Trace data can include URLs, user IDs, resource ARNs, exception messages, and custom attributes. Therefore:

- Never record passwords, tokens, cookies, authorization headers, or private keys.
- Never put email addresses, phone numbers, or payment data into annotations.
- Mask or pseudonymize identifiers when business correlation is required.
- Use least-privilege service roles for PutTraceSegments/telemetry and read APIs.
- Restrict who can view traces/logs containing sensitive data.
- Govern X-Ray groups/filters to prevent unnecessary data access.
- Align retention and sampling with audit and incident requirements.
- Never use trace context for authentication or authorization.

X-Ray may record client IP from X-Forwarded-For when requests pass through proxies or load balancers. This header can be spoofed if trust boundaries are misconfigured; never treat it as proof of identity.

## 28. Cost, Retention, and Sampling

Tracing incurs ingestion and retrieval costs and can increase collector, CloudWatch, and X-Ray spend. Before enabling 100% tracing, evaluate request volume, spans per request, sampling, retention, and viewer access needs.

Principles:

- Start with controlled sampling.
- Retain higher trace rates for high-risk business flows if budget permits.
- Reduce tracing on health checks and repetitive low-value traffic.
- Use tail sampling when prioritizing errors/slow traces and collector resources allow.
- Avoid creating excessive custom spans for trivial functions.
- Limit attributes and metadata size.
- Monitor dropped spans, exporter errors, and collector queues.
- Rely on metrics to measure total traffic; traces are sampled when sampling is under 100%.

Per X-Ray documentation, trace data is retained for 30 days. If long-term storage or auditing is required, design a separate archive/analytics solution suited to data policies and budgets.

## 29. Migration Plan from X-Ray SDK/Daemon to OpenTelemetry

For Java applications currently using the X-Ray SDK, migrate incrementally:

1. Inventory services using the X-Ray SDK, Java agent, and Daemon.
2. Document existing instrumentation: HTTP, Spring, AWS SDK v2, JDBC, and custom subsegments.
3. Choose the ADOT Java agent or OpenTelemetry Java agent/SDK.
4. Choose Collector or CloudWatch Agent as the trace receiver/exporter.
5. Configure resource attributes, propagators, sampling, and exporters.
6. Verify IAM permissions and networking.
7. Run in staging, comparing trace coverage, latency, and service graphs.
8. Roll out service by service.
9. Verify trace propagation across mixed legacy and migrated services.
10. Remove X-Ray SDK/Daemon once dependencies are gone and confirm no port conflicts remain.

### 29.1. Avoiding Dual Instrumentation

Running both the legacy X-Ray Java agent and the OTel Java agent simultaneously on the same HTTP/JDBC/AWS SDK calls can produce duplicate spans or broken parent-child hierarchies. During migration, assign one clear instrumentation owner per library.

When replacing X-Ray Daemon with CloudWatch Agent or OTel Collector, shut down the legacy Daemon cleanly to prevent port/receiver conflicts. Do not run two collectors ingesting the same trace stream without an explicit goal.

### 29.2. Compatibility During Transition

X-Ray and OpenTelemetry can coexist in a distributed system. What matters is that services understand each other's context formats and avoid spawning unintended root traces. Configure W3C/X-Ray propagators at each boundary and verify trace IDs with end-to-end tests.

## 30. Runbook When Latency or Faults Spike

When dashboards report rising p95 or 5xx:

1. Identify the affected service and time range.
2. Open Application Signals/CloudWatch metrics to gauge blast radius.
3. Open X-Ray Trace Map and select anomalous nodes or edges.
4. Filter traces by fault, throttle, or response time.
5. Select representative traces and open Trace details.
6. Identify the span/subsegment consuming the most time or raising exceptions.
7. Cross-reference CloudWatch Logs using the trace ID.
8. Check dependency metrics, AWS service errors, and deployment events.
9. Check retries, timeouts, connection pools, and sampling.
10. After mitigation, compare traces and metrics against baseline.

If Trace Map shows no data, check instrumentation, export, permissions, and sampling before concluding the app has zero traffic.

## 31. Real-World Scenarios

### Scenario A — orders-api Slow Due to DynamoDB

Trace summary shows a request took 2.8 seconds. Timeline shows the DynamoDB subsegment took 2.3 seconds.

**Resolution:** check throttling/retries, hot partitions, table/index capacity, SDK attempt latency, VPC endpoints, and connection pools. Cross-reference CloudWatch DynamoDB metrics and application logs.

### Scenario B — payment-service Returns 500

The Trace Map node payment-service is red. Trace details show an exception on the span calling the payment provider.

**Resolution:** filter by fault, open the failing span, inspect HTTP status, masked error message, downstream latency, and deployment version. Distinguish internal failures from external provider outages.

### Scenario C — Trace Shows Only orders-api

Orders-api invokes invoice-worker via SQS, yet the trace map does not connect the two services.

**Resolution:** check message trace context propagation, Lambda instrumentation, sampling decisions, exporters, and IAM. Verify whether the integration supports producer/consumer linking in your architecture.

### Scenario D — Service Has Faults Yet Root Trace Succeeds

A downstream call fails, yet the application retries and succeeds.

**Resolution:** inspect subsegments/edges for throttles or errors; do not filter solely on root fault. Evaluate retry counts and dependency health.

### Scenario E — Duplicate Nodes with Varying Names

Multiple deployments or service instances appear as fragmented nodes, bloating the graph.

**Resolution:** standardize logical service names, use resource attributes for instance/task/version, and avoid embedding request IDs or pod IDs in service names.

### Scenario F — Trace Splits into Two Trace IDs

Service A calls service B, yet B creates a new root trace.

**Resolution:** check propagators, HTTP instrumentation, proxy headers, and async context propagation. Ensure B extracts parent context before creating its server span.

### Scenario G — Error Appears Only in Production

Staging does not reproduce the latency; production traces reveal a slow JDBC span.

**Resolution:** compare DB connection pools, query plans, lock contention, network paths, data volume, and traffic shape. Use traces to pinpoint timestamps and correlated logs instead of capturing sensitive payloads.

## 32. Scenario Exercises

### Exercise A — Trace, Segment, and Subsegment

A request enters orders-api and then calls DynamoDB.

**Answer:** the trace represents the full request; orders-api has a server segment/span; the DynamoDB call is recorded as a subsegment/client span.

### Exercise B — Inferred Segment

DynamoDB does not emit its own segment in the trace.

**Answer:** X-Ray builds an inferred segment/node from the caller's subsegment to depict the dependency.

### Exercise C — High Edge Latency

The orders-api node looks healthy, yet the edge to payment-service shows high latency.

**Answer:** open the edge and trace, inspect round-trip time, networking, retries, downstream processing, and connection pools.

### Exercise D — Red Trace Map Node

The payment-service node has a red border.

**Answer:** red indicates server faults/5xx in Trace Map; open traces to inspect segments/exceptions and downstream dependencies.

### Exercise E — Rising Throttles

The edge to DynamoDB shows many throttled traces.

**Answer:** investigate throttling, capacity, hot keys, retry policies, and workload bursts; do not merely increase sampling.

### Exercise F — Unfilterable Annotation

The application wrote order.tier as metadata, and annotation filters cannot find it.

**Answer:** configure the attribute as an X-Ray annotation in the exporter; metadata is not indexed.

### Exercise G — Downstream Sampling Rule

Service B has a 100% sampling rule, yet traces remain unsampled because service A decided sampled=false.

**Answer:** sampling is typically parent-based; downstream services honor the root/parent decision. Adjust sampling at the root or configure an appropriate sampler.

### Exercise H — X-Ray SDK in Java

A new application begins development on X-Ray SDK/Daemon in late 2026.

**Answer:** prefer OpenTelemetry/ADOT because X-Ray SDK/Daemon entered maintenance mode on 25/02/2026.

### Exercise I — Lost Trace Context Across SQS

The producer records a trace, yet the Lambda consumer is unlinked.

**Answer:** check propagation inside message metadata, Lambda instrumentation, consumer context extraction, and sampling/export.

### Exercise J — Parent Span Much Longer Than Child Spans

Total request duration is 3 seconds, yet child spans sum to only 1 second.

**Answer:** uninstrumented work/waits exist or the parent includes time outside child spans. Add spans and inspect thread/queue/network waits.

### Exercise K — Service Map vs. Application Map

An operator wants to monitor SLO health, but is looking at X-Ray Trace Map.

**Answer:** use Application Signals Application Map/Services for SLOs and operational health; use X-Ray Trace Map to drill into trace/service graphs.

### Exercise L — Downstream Failures Returning HTTP 200

Filtering for fault finds no traces.

**Answer:** inspect subsegments/edges and service-specific filters; retried/handled downstream errors may leave the root trace without a fault.

### Exercise M — Querying by Annotation

You want to find traces for premium-tier customers.

**Answer:** attach a low-cardinality, PII-free annotation, then filter with annotation.tenantTier = "premium".

### Exercise N — X-Ray Daemon and CloudWatch Agent Running Together

After migration, the collector receives traces intermittently.

**Answer:** check for receiver/port conflicts, stop the legacy Daemon once cut over to CloudWatch Agent/Collector, and verify exporters send only one trace stream.

### Exercise O — Trace Contains Email Data

Trace attributes contain customer email addresses.

**Answer:** remove or pseudonymize PII, tighten access permissions, and review processors/filters prior to export.

## 33. Review Questions

1. What problem does distributed tracing solve in microservices?
2. What is the role of a trace ID?
3. What does a segment represent?
4. What activities do subsegments typically record?
5. When is an inferred segment created?
6. From what data is a service graph constructed?
7. What does an edge represent?
8. Why can caller and callee durations differ?
9. What is X-Ray Trace Map used for?
10. How does Application Signals Application Map differ from Trace Map?
11. On what date did X-Ray SDK/Daemon enter maintenance mode?
12. What does AWS recommend for new instrumentation?
13. Which X-Ray concepts correspond to OpenTelemetry spans?
14. What do OTel attributes map to by default in X-Ray?
15. How do annotations differ from metadata?
16. Up to how many annotations per trace does X-Ray index?
17. What is the name of the X-Ray tracing header?
18. Which headers does W3C Trace Context use?
19. Why must services use compatible propagators?
20. What role does the ADOT Java agent play?
21. Which protocols does an OTLP Collector typically accept?
22. Which permissions does an exporter need to ship traces to X-Ray?
23. What problem does sampling solve?
24. Which mechanism uses the 1 request/second plus 5% default?
25. How does parent-based sampling affect downstream services?
26. Where must tail sampling be executed?
27. What do red, yellow, and purple indicate in Trace Map?
28. How do fault, error, and throttle differ?
29. What unit do responsetime and duration use in filter expressions?
30. When should you filter by service/edge instead of root fault?
31. Why shouldn't nested span durations be added directly?
32. What distinct goals do Trace Map and Application Map support?
33. Why might a trace miss segments?
34. How long is X-Ray trace data retained per current documentation?
35. During migration, why shouldn't two auto-instrumentation agents run simultaneously on the same libraries?

**Quick answers:** (1) connects request paths across processes; (2) links spans/segments of the same request; (3) work performed by a service; (4) downstream calls/processing blocks; (5) downstream does not emit its own segment; (6) segments sharing a trace ID; (7) call relationship and round-trip latency; (8) caller measures round-trip, callee measures processing time; (9) viewing topology and traces; (10) SLO/service health vs. trace graph; (11) 25/02/2026; (12) OTel/ADOT; (13) server spans and non-server spans; (14) metadata; (15) annotations are indexed, metadata is not; (16) 50; (17) X-Amzn-Trace-Id; (18) traceparent/tracestate; (19) preserve parent-child context; (20) auto-instrument Java; (21) OTLP gRPC/HTTP; (22) PutTraceSegments and PutTelemetryRecords; (23) control volume/cost; (24) legacy X-Ray SDK default; (25) downstream inherits parent decision; (26) Collector; (27) 5xx/4xx/429; (28) server fault/client error/throttling; (29) seconds; (30) when downstream errors are handled and root succeeds; (31) parent already includes child time; (32) Trace Map analyzes traces, Application Map tracks SLOs/topology; (33) sampling, instrumentation, or propagation/export gaps; (34) 30 days; (35) avoid duplicate spans and broken hierarchies.

## 34. Production Checklist

- [ ] Service names are stable and meaningful per logical service.
- [ ] Java applications use pinned versions of ADOT/OpenTelemetry instrumentation.
- [ ] HTTP server/client, AWS SDK, and JDBC instrumentation are verified.
- [ ] Custom spans cover only needed business operations.
- [ ] Resource attributes include service name, environment, and version.
- [ ] Trace context propagates across HTTP and async boundaries.
- [ ] X-Ray/W3C propagators align across service boundaries.
- [ ] Sampling policy is configured at the root and tuned to traffic.
- [ ] Metrics still cover 100% of requests when trace sampling is below 100%.
- [ ] Annotations hold only filter-needed, low-cardinality, PII-free fields.
- [ ] Metadata contains no secrets or sensitive payloads.
- [ ] Collector/CloudWatch Agent has valid trace pipelines and exporters.
- [ ] IAM role has least-privilege PutTraceSegments/PutTelemetryRecords permissions.
- [ ] Collector configures batching, retries/queues, and monitors dropped spans.
- [ ] X-Ray Trace Map drills down cleanly to trace details.
- [ ] Application Signals is enabled if service health/SLO maps are required.
- [ ] CloudWatch logs include trace IDs for correlation.
- [ ] Queries/filter expressions exist for faults, throttles, latency, and dependencies.
- [ ] Metric dashboards/alarms cover SLOs without relying on sampled traces for alerting.
- [ ] End-to-end trace testing covers SQS/Lambda or async workers if queues are used.
- [ ] Migration plan exists to move off maintenance-mode X-Ray SDK/Daemon.
- [ ] No duplicate instrumentation agents remain running post-migration.
- [ ] Appropriate trace/log access permissions and retention/cost policies are enforced.
- [ ] Runbooks distinguish instrumentation gaps, sampling, propagation, exporters, and dependency failures.

## 35. Summary

AWS X-Ray observes request paths in distributed systems using traces, segments, subsegments, and service graphs:

- Trace IDs link data from the same request; segments describe a service's work; subsegments capture downstream calls or detailed processing steps.
- Inferred segments represent dependencies that do not emit their own segments; edges provide the caller's round-trip perspective.
- X-Ray Trace Map visualizes the service graph, errors, and latency; Application Signals Application Map focuses on topology, service health, and SLOs.
- Effective 25/02/2026, X-Ray SDK/Daemon entered maintenance mode. For new Java apps, prefer OpenTelemetry/ADOT and Collector/CloudWatch Agent to ship traces to X-Ray.
- Auto-instrumentation captures spans for frameworks/libraries; manual spans add business context.
- Sampling controls volume and cost; parent-based sampling should be set at the root; tail sampling can prioritize failing/slow traces.
- Annotations are indexed for filtering; metadata stores unindexed context.
- Filter expressions locate faults, errors, throttles, latency, services, edges, and root causes.
- Trace details/timelines isolate critical paths; logs and metrics provide corroborating evidence.
- Migrations require validating context propagation, collectors, IAM, sampling, and eliminating dual instrumentation.

Distributed tracing works best when every service emits structured telemetry, preserves parent-child context, and links topology back to individual requests. Traces do not explain every outage on their own; they point you to the exact logs, metrics, dependencies, and code paths that need investigation.

### Official AWS and OpenTelemetry Documentation

1. AWS X-Ray concepts: https://docs.aws.amazon.com/xray/latest/devguide/xray-concepts.html
2. Using the X-Ray trace map: https://docs.aws.amazon.com/xray/latest/devguide/xray-console-servicemap.html
3. Viewing traces and trace details: https://docs.aws.amazon.com/xray/latest/devguide/xray-console-traces.html
4. Using filter expressions: https://docs.aws.amazon.com/xray/latest/devguide/xray-console-filters.html
5. Configuring sampling rules: https://docs.aws.amazon.com/xray/latest/devguide/xray-console-sampling.html
6. Migrating from X-Ray instrumentation to OpenTelemetry: https://docs.aws.amazon.com/xray/latest/devguide/xray-sdk-migration.html
7. Migrating to OpenTelemetry Java: https://docs.aws.amazon.com/xray/latest/devguide/xray-migration-opentelemetry.html
8. AWS X-Ray SDK and Daemon: https://docs.aws.amazon.com/xray/latest/devguide/xray-sdk-java.html
9. AWS X-Ray daemon: https://docs.aws.amazon.com/xray/latest/devguide/xray-daemon.html
10. CloudWatch Application Signals: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Services.html
11. CloudWatch Application Map: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/ServiceMap.html
12. CloudWatch Agent and Application Signals: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Agent-Application_Signals.html
13. CloudWatch integration with X-Ray: https://docs.aws.amazon.com/xray/latest/devguide/xray-services-cloudwatch.html
14. AWS X-Ray GetTraceSummaries API: https://docs.aws.amazon.com/xray/latest/api/API_GetTraceSummaries.html
15. AWS X-Ray BatchGetTraces API: https://docs.aws.amazon.com/xray/latest/api/API_BatchGetTraces.html
16. AWS Distro for OpenTelemetry: https://aws-otel.github.io/
17. OpenTelemetry Java instrumentation: https://opentelemetry.io/docs/zero-code/java/agent/
18. OpenTelemetry traces: https://opentelemetry.io/docs/concepts/signals/traces/
19. OpenTelemetry context propagation: https://opentelemetry.io/docs/concepts/context-propagation/
20. AWS Well-Architected Reliability Pillar: https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/welcome.html
