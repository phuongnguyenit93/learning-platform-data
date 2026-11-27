# Observability across Federation with Spring for GraphQL

In a GraphQL Federation system, a client request can pass through the router/supergraph, query planner, and multiple subgraphs before a response is returned. Measuring duration only at the router or inspecting logs from a single subgraph makes it hard to pinpoint whether latency originates in query planning, network calls, resolvers, DataLoaders, or databases.

Observability across federation must connect signals across multiple layers: the router, each Spring for GraphQL subgraph, and dependencies behind subgraphs. Distributed tracing shows steps belonging to the same request; metrics reveal trends and error rates; logs provide details for investigating a specific trace.

In this lesson, we use Spring for GraphQL's Micrometer Observation in subgraphs and OpenTelemetry (OTel) across service boundaries. Examples use Apollo Router, though the principles of trace context, service identity, cardinality, and correlation apply to other gateways/routers as well.

## 1. Observability architecture of a federated graph

Suppose a supergraph has two subgraphs:

- `catalog-subgraph` provides Product and product information.
- `review-subgraph` provides Product Reviews.
- Apollo Router receives an operation from a client, builds a query plan, and calls one or both subgraphs.

A request can follow this flow:

~~~mermaid
flowchart TD
    C[GraphQL Client] -->|HTTP + traceparent| R[Apollo Router / Supergraph]
    R -->|HTTP + trace context| P[Catalog Subgraph - Spring GraphQL]
    R -->|HTTP + trace context| V[Review Subgraph - Spring GraphQL]
    P --> PS[Product Service]
    V --> VS[Review Service]
    PS --> DB1[(Catalog DB)]
    VS --> DB2[(Review DB)]
    R -. OTLP traces and metrics .-> O[OpenTelemetry Collector / APM]
    P -. OTLP traces and metrics .-> O
    V -. OTLP traces and metrics .-> O
~~~

The goal is to open a single trace and see the request traverse services, for example:

1. HTTP request arrives at the router.
2. The router parses, validates, and builds a query plan.
3. The router calls `catalog-subgraph` and `review-subgraph`.
4. Each subgraph runs GraphQL execution.
5. Resolvers and DataLoaders call services/databases.
6. The router aggregates results and returns the response.

Each service still emits its own metrics to track throughput, latency, and errors. Trace ID links spans belonging to the same request; `service.name` distinguishes spans originating from the router or each subgraph.

## 2. Three layers to observe

| Layer | What to measure | Operational questions |
| --- | --- | --- |
| Router / Supergraph | HTTP requests, query planning, subgraph fetches, response aggregation, GraphQL errors | Is the router slow? Which subgraph is slowing down the request? Does the query plan have high fan-out? |
| Spring GraphQL subgraph | `graphql.request`, `graphql.datafetcher`, `graphql.dataloader`, HTTP server | Which subgraph requests are failing? Which field or batch loader is slow? |
| Dependency | Databases, caches, downstream REST/gRPC, message brokers | Is the resolver slow due to code, connection pools, or a dependency? |

Do not rely on a single metric to conclude root cause. For example, increased router request duration could stem from query planning, subgraph wait time, networking, or response aggregation. Open the trace and inspect child spans to isolate each segment.

## 3. Distinguishing OpenTelemetry traces and Apollo Federated Traces (FTV1)

In the Apollo ecosystem, two concepts are easily confused:

| Mechanism | Purpose | Transport path |
| --- | --- | --- |
| OpenTelemetry distributed tracing | Connects spans across HTTP/service boundaries, observing router, subgraphs, and dependencies in APM | W3C Trace Context / OTLP to Collector or APM |
| Apollo Federated Trace (FTV1) | Sends field-level timing/error info from subgraphs back to the router so it can aggregate and report to GraphOS | Router requests `apollo-federation-include-trace: ftv1`; subgraph returns trace in `extensions.ftv1` |

The two mechanisms can complement each other, yet they are not the same format. Spring for GraphQL's Micrometer Observation produces observations exportable as metrics/traces via Micrometer Tracing; that does not automatically make a subgraph FTV1-compatible. If you want GraphOS to display field-level federated traces, verify that your federation library/runtime supports FTV1 and configure it per that library's guide.

For Spring for GraphQL, this lesson focuses primarily on propagating trace context over HTTP and exporting GraphQL observations to an OTel-compatible backend. Do not assume enabling `GraphQlObservationInstrumentation` alone causes the router to receive `extensions.ftv1`.

## 4. Which observations does Spring for GraphQL create?

Spring for GraphQL integrates with Micrometer Observation. When `ObservationRegistry` is configured and `GraphQlObservationInstrumentation` is registered, the framework creates three primary observation types:

| Observation | Scope | Some low-cardinality keys |
| --- | --- | --- |
| `graphql.request` | A GraphQL execution request | `graphql.operation.type`, `graphql.outcome` |
| `graphql.datafetcher` | A non-trivial data fetcher | `graphql.field.name`, `graphql.outcome`, `graphql.error.type` |
| `graphql.dataloader` | A batch loader execution | `graphql.loader.name`, `graphql.outcome`, `graphql.error.type` |

`graphql.request` can have outcomes `SUCCESS`, `REQUEST_ERROR`, or `INTERNAL_ERROR`. Data fetchers and DataLoaders have outcomes `SUCCESS` or `ERROR`. Property fields read directly from a Java object are typically trivial fetches and do not emit separate observations.

High-cardinality keys such as `graphql.operation.name`, `graphql.execution.id`, `graphql.field.path`, or `graphql.loader.size` are useful to inspect inside traces, but should not all be turned into metric tags.

## 5. Enabling Micrometer Observation in each Spring GraphQL subgraph

When using Spring Boot, add Actuator and the Micrometer Tracing bridge for OpenTelemetry. Applications already using the Spring for GraphQL starter keep their existing GraphQL dependency.

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("io.micrometer:micrometer-tracing-bridge-otel")

    runtimeOnly("io.opentelemetry:opentelemetry-exporter-otlp")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Let Spring Boot dependency management manage compatible versions. If not using Spring Boot, configure `ObservationRegistry`, `MeterRegistry`, the tracing bridge/exporter, and GraphQL instrumentation manually.

Give each subgraph a distinct service name. You can use standard configuration properties:

~~~yaml
spring:
  application:
    name: catalog-subgraph
~~~

In another subgraph:

~~~yaml
spring:
  application:
    name: review-subgraph
~~~

`service.name` is the resource attribute identifying a service in traces and metrics. Do not assign one shared `service.name` across all subgraphs, or APM tools will struggle to distinguish which service emitted each span.

Spring Boot can auto-configure GraphQL observation instrumentation when an `ObservationRegistry` is present and auto-configuration conditions for your Boot version are met. If your application builds `GraphQlSource` manually or does not use Boot auto-configuration, register `GraphQlObservationInstrumentation`:

~~~java
import io.micrometer.observation.ObservationRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.observation.GraphQlObservationInstrumentation;
import org.springframework.graphql.execution.GraphQlSource;

@Configuration(proxyBeanMethods = false)
class GraphQlObservationConfiguration {

    @Bean
    GraphQlObservationInstrumentation graphQlObservationInstrumentation(
            ObservationRegistry observationRegistry
    ) {
        return new GraphQlObservationInstrumentation(observationRegistry);
    }
}
~~~

With the Spring Boot GraphQL starter, `Instrumentation` beans are detected when building `GraphQlSource`. If building `GraphQlSource` manually without auto-configuration, pass the instrumentation directly to the builder:

~~~java
import java.util.List;

import io.micrometer.observation.ObservationRegistry;
import org.springframework.core.io.ClassPathResource;
import org.springframework.graphql.execution.GraphQlSource;
import org.springframework.graphql.observation.GraphQlObservationInstrumentation;

GraphQlSource graphQlSource = GraphQlSource.schemaResourceBuilder()
        .schemaResources(new ClassPathResource("graphql/schema.graphqls"))
        .instrumentation(List.of(
                new GraphQlObservationInstrumentation(observationRegistry)
        ))
        .build();
~~~

Pick one configuration style matching how your application creates `GraphQlSource`; avoid registering duplicate instrumentation if Boot already auto-configures it. Check startup conditions and actual observations to confirm instrumentation is running.

## 6. Configuring sampling and trace export in a subgraph

A Boot configuration typically sets sampling probability and exporter endpoints per environment:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.10
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
~~~

The example uses 10% sampling in production to bound cost. Development environments can use higher sampling for easier debugging. The configuration above illustrates Spring Boot 3.x OTLP tracing properties; property names can vary across Boot lines, so cross-check documentation for your exact project version. `spring.application.name` sets service identity; you can use `OTEL_SERVICE_NAME` or `management.opentelemetry.resource-attributes` when configuring OpenTelemetry Resources directly per your Boot version.

In distributed tracing, subgraph samplers should honor the parent sampled flag. When the router decides to trace a request, subgraphs should continue the same trace from parent context; do not start an independent trace for every HTTP request if the goal is viewing the full call tree.

Metrics and traces are distinct signal types. Prometheus registry exports metrics; Micrometer Tracing bridge and OTLP exporter export traces. Having Actuator `/actuator/metrics` working does not mean traces are reaching the Collector.

## 7. Propagating trace context from router to subgraph

W3C Trace Context uses standard HTTP headers:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
tracestate: vendor=value
~~~

`traceparent` carries the trace ID, parent span ID, and trace flags. When the router calls a subgraph over HTTP, the router must continue or create trace context and send the corresponding headers. HTTP server instrumentation in Spring Framework receives this context and creates a child server observation/span.

Spring for GraphQL places the request observation inside the transport layer. Spring GraphQL documentation specifies that the parent observation must be placed into the GraphQL context under the `micrometer.observation` key; over HTTP, Spring Framework has dedicated instrumentation handling trace context propagation across network boundaries.

If a subgraph receives HTTP requests yet traces are disconnected from the router, check in this order:

1. Does the router receive `traceparent` from clients or create a new trace?
2. Does the router send `traceparent` to the subgraph endpoint?
3. Is Spring Boot HTTP server observation/tracing enabled?
4. Does the subgraph use the same trace backend and exporter?
5. Does the subgraph pick up the parent context or start a new trace?
6. Is any proxy/load balancer stripping or altering tracing headers?

When a subgraph calls another REST or GraphQL service, use auto-configured `RestClient.Builder`, `WebClient.Builder`, or `RestTemplateBuilder` from Spring Boot so trace context propagates automatically. Creating clients manually and bypassing those builders can break outbound trace propagation.

For non-HTTP or custom transports, provide the corresponding parent observation/context propagation mechanism. Do not assume HTTP propagation applies automatically to WebSocket, RSocket, or message brokers.

## 8. Enabling telemetry in Apollo Router

Apollo Router has its own telemetry for the request lifecycle. Typical spans include:

| Span | Scope |
| --- | --- |
| `router` | HTTP request from the router's perspective |
| `supergraph` | GraphQL operation after parse/validate and query plan execution |
| `subgraph` | HTTP call to a subgraph |

The router supports exporting telemetry via OTLP. The example configuration below enables spans for each stage and the OTLP tracing exporter. The endpoint must point to a Collector supporting the exporter protocol configured on the Router.

~~~yaml
telemetry:
  instrumentation:
    spans:
      mode: spec_compliant
      router:
        attributes:
          otel.name: router
          operation.name: "router"
      supergraph:
        attributes:
          otel.name: supergraph
          operation.name: "supergraph"
      subgraph:
        attributes:
          otel.name: subgraph
          operation.name: "subgraph"
  exporters:
    tracing:
      otlp:
        enabled: true
        endpoint: "${env.OTEL_GRPC_ENDPOINT}"
~~~

For example, `OTEL_GRPC_ENDPOINT` can be set to `otel-collector:4317` when the Collector ingests OTLP over gRPC. Use the endpoint and port matching the exporter protocol configured on the Router; HTTP OTLP typically uses port `4318` and signal-specific paths.

You can enable the Prometheus exporter for the Router:

~~~yaml
telemetry:
  exporters:
    metrics:
      prometheus:
        enabled: true
        listen: "127.0.0.1:9090"
        path: "/metrics"
~~~

These two configuration blocks can be merged under the same root `telemetry` key in the router file. Restrict metrics endpoints to internal networks or protect them via deployment infrastructure; do not expose metrics endpoints to the public Internet carelessly.

The router can also emit JSON logs:

~~~yaml
telemetry:
  exporters:
    logging:
      stdout:
        enabled: true
        format: json
~~~

Only enable verbose logging in environments where needed. Instrumenting too many events or attributes can increase CPU usage, telemetry volume, and router latency.

## 9. Distinguishing router latency from subgraph latency

Example trace with spans:

~~~text
HTTP POST /graphql                         420 ms
  router                                    420 ms
    supergraph                              410 ms
      subgraph catalog                      120 ms
        HTTP server catalog                 105 ms
          graphql.request                    92 ms
            graphql.datafetcher Product.id    2 ms
            graphql.datafetcher Product.price 35 ms
              JDBC query                     30 ms
      subgraph review                       250 ms
        HTTP server review                  235 ms
          graphql.request                   220 ms
            graphql.dataloader reviews      180 ms
              SQL query                     170 ms
~~~

In this example, the review subgraph has a slow batch query and is the longer branch. Optimizing catalog first might not significantly reduce end-to-end latency. Open the child spans of `graphql.dataloader` or the database to find the root cause.

When subgraphs are called in parallel, do not sum all subgraph durations to infer request duration. End-to-end latency is usually dominated by the slowest branch plus planning, network, and response aggregation overhead. Trace timelines make this parallel relationship visible.

## 10. Using GraphQL observations to locate slow fields

In Spring GraphQL, `graphql.datafetcher` measures non-trivial resolvers. Useful default keys:

| Key | Cardinality | Used for |
| --- | --- | --- |
| `graphql.field.name` | Low | Grouping duration/errors by field name |
| `graphql.outcome` | Low | Distinguishing `SUCCESS` and `ERROR` |
| `graphql.error.type` | Low | Grouping exception types |
| `graphql.field.path` | High | Pinpointing a specific field location in a trace |

If `Product.price` is frequently slow, open the trace to inspect underlying service or database spans. If simple property fields lack separate observations, check the request span or instrument the corresponding service/repository.

For DataLoader:

| Key | Cardinality | Used for |
| --- | --- | --- |
| `graphql.loader.name` | Low | Identifying the running loader |
| `graphql.outcome` | Low | Distinguishing batch success/failure |
| `graphql.error.type` | Low | Grouping batch errors |
| `graphql.loader.size` | High | Inspecting batch sizes in traces |

Combine batch duration and batch size to spot batches that are too small, too large, or slowed by downstream services. If you need aggregated metrics by size range, build finite buckets rather than putting arbitrary size values into metric tags.

## 11. Setting consistent service identity and metadata

Each process should have clear resource attributes:

~~~text
service.name = catalog-subgraph
service.namespace = commerce
deployment.environment = production
service.version = 1.8.0
~~~

The router has its own `service.name`, such as `apollo-router`. The review subgraph has `service.name=review-subgraph`. You can add `service.namespace`, `deployment.environment`, and `service.version` to compare across environments and release versions.

Do not attach subgraph name as a dynamic tag on every metric if each subgraph already runs as a separate service and `service.name` captures that. In router spans, subgraph name is a useful attribute to show which downstream call is executing.

Do not put the following values into low-cardinality metrics:

- Trace IDs, span IDs, or request IDs.
- Unbounded user IDs, emails, customer IDs, or tenant IDs.
- Raw GraphQL queries or full variables.
- Field paths containing list indices or input data.
- Dynamic error message text.

These values inflate cardinality or may contain sensitive data. If you need them for investigations, consider controlled trace attributes, redaction, and retention policies.

## 12. Correlating logs with traces

Router and subgraph logs should contain trace ID/span ID so you can pivot from logs to traces. When Micrometer Tracing integrates with logging frameworks, MDC correlation can be added to log patterns or structured logging.

Spring Boot includes correlation IDs based on MDC `traceId` and `spanId` by default when Micrometer Tracing is active. You can customize `logging.pattern.correlation` if you want logs to also display `spring.application.name` or another format.

Example JSON log:

~~~json
{
    "timestamp": "2026-11-20T06:30:00Z",
    "level": "ERROR",
    "service": "review-subgraph",
    "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
    "spanId": "00f067aa0ba902b7",
    "message": "Review batch lookup failed",
    "loader": "reviewsByProductId"
}
~~~

Do not log entire raw GraphQL request bodies just to capture operation names or variables. Use normalized operation names, field names, and trace IDs instead. When logging error details, strip tokens, passwords, personal data, and sensitive query payloads.

When investigating a request:

1. Find the trace using the trace ID from logs or response correlation.
2. Inspect the router span to see which subgraphs were called and wait times.
3. Open the corresponding subgraph server span.
4. Locate `graphql.request`, `graphql.datafetcher`, or `graphql.dataloader` with abnormal latency or errors.
5. Drill down into JDBC, Redis, or HTTP client spans.
6. Use logs sharing the same trace ID to view redacted error details.

## 13. GraphQL outcome is not the same as HTTP status

GraphQL can return HTTP `200 OK` alongside partial `data` and `errors`. Therefore, monitor both transport and GraphQL execution.

| Signal | Example | Meaning |
| --- | --- | --- |
| HTTP server status | `200`, `400`, `500` | Result at the HTTP transport layer |
| `graphql.outcome` | `SUCCESS`, `REQUEST_ERROR`, `INTERNAL_ERROR` | GraphQL request outcome in Spring GraphQL |
| `graphql.datafetcher` outcome | `SUCCESS`, `ERROR` | Whether a resolver succeeded |
| `graphql.dataloader` outcome | `SUCCESS`, `ERROR` | Whether a batch load succeeded |

If HTTP is 200 but `graphql.outcome=REQUEST_ERROR`, the request reached the GraphQL server and produced non-internal GraphQL errors. If the HTTP request fails before GraphQL execution starts, no corresponding `graphql.request` observation may exist. When dashboards filter only by HTTP 5xx, GraphQL errors can go unnoticed.

## 14. Apollo Federated Trace Data and GraphOS

When using GraphOS Insights, the router can aggregate field-level trace data from subgraphs that support FTV1. High-level flow:

1. The router receives an operation and builds a query plan.
2. The router sends sub-queries to each subgraph.
3. When collecting FTV1, the router sends the `apollo-federation-include-trace: ftv1` header.
4. Compatible subgraphs return trace data in response `extensions.ftv1`.
5. The router merges sub-traces according to the query plan and reports the federated trace to GraphOS.

This is how GraphOS displays field-level timing/errors across the entire supergraph. FTV1 capability depends on the subgraph library and its configuration. For a Spring GraphQL subgraph, verify whether your Federation adapter/runtime supports this format; do not expect a standard Micrometer observation to add `extensions.ftv1` on its own.

Apollo Router can also export OpenTelemetry traces directly to an OTLP backend. If your target is Jaeger, Tempo, Zipkin, or Datadog, use the Router OTEL exporter and subgraph Micrometer/OTel exporter to link trace context. If your target is GraphOS field-level traces, check FTV1 support and configure reporting separately.

Both pipelines can run together, but sampling and privacy policies must be designed consistently. Federated trace payloads can increase subgraph response size and latency; enable only the level of detail required.

## 15. Sampling across router and subgraphs

Sampling reduces trace storage and processing costs. A simple strategy:

- Development: high sampling to inspect every branch while debugging.
- Staging: high enough sampling to verify query plans and field behavior.
- Production: parent-based sampling at a rate fitting traffic load and telemetry budget.
- Error/high-latency tail: consider tail-based sampling at the Collector to retain error or slow traces if infrastructure supports it.

If each subgraph performs independent random sampling, traces can miss child spans even when the router recorded the parent span. Use a parent-based sampler to respect the sampled flag in trace context. If using tail sampling, the Collector must receive all spans of a trace before deciding whether to keep or drop it; configure exporters and batching accordingly.

Do not raise sampling to 100% in production without evaluating traffic volume, span size, overhead, and retention. You can increase it temporarily while investigating an incident and revert afterward.

## 16. Dashboards and alerts for a federated graph

An operational dashboard should be organized into sections:

| Dashboard section | Suggested metrics/attributes | Question |
| --- | --- | --- |
| Supergraph traffic | Router request rate, active requests, HTTP status | Is traffic spiking or is the router saturating? |
| End-to-end latency | p50/p95/p99 router request duration | What latency are clients experiencing? |
| Subgraph latency | Subgraph span duration by subgraph name | Which subgraph dominates the critical path? |
| GraphQL errors | `graphql.outcome`, field/DataLoader error rates | Are errors occurring in requests, resolvers, or batches? |
| Query planning | Supergraph/query planning span duration | Do operations have complex query plans? |
| Dependency | JDBC, Redis, HTTP client spans | Which dependency are resolvers waiting on? |
| Saturation | CPU, memory, connection pool, thread/worker utilization | Are services nearing resource limits? |

Alerts should be based on SLOs and realistic baselines. For example:

- Supergraph p95 latency breaches the SLO over a sustained window.
- `graphql.outcome=INTERNAL_ERROR` rate spikes sharply.
- One subgraph exhibits higher p95 than peers or exceeds its own budget.
- DataLoader error rate rises or batch duration stays elevated.
- Router active requests climb while subgraph throughput fails to rise proportionally.

Do not configure alerts on individual trace IDs or arbitrary operation names. Use bounded dimensions such as service, environment, operation type, and outcome.

## 17. Allocating latency budgets across subgraphs

Suppose an operation's end-to-end SLO is 500 ms. A reference budget breakdown might look like:

| Component | Illustrative budget |
| --- | ---: |
| Router parse/validate/query plan | 40 ms |
| Network + subgraph fetch overhead | 40 ms |
| Catalog subgraph critical path | 150 ms |
| Review subgraph critical path | 200 ms |
| Response aggregation/serialization | 40 ms |
| Headroom | 30 ms |

This is only a budgeting example, not default values. When the router calls two subgraphs in parallel, total duration is not the sum of both subgraph budgets; the slower branch typically determines most of the wait time. When subgraphs are called sequentially due to dependencies, durations add up.

When an operation breaches its SLO, use traces to identify the critical path branch, then set dedicated SLOs/alerts for the corresponding subgraph or dependency.

## 18. Testing trace propagation across federation

Do not only verify that metrics endpoints return data. Verify that trace context actually links end-to-end:

1. Send a request with a valid `traceparent` to the router.
2. Confirm the router creates/continues a trace with the expected trace ID.
3. Confirm requests arriving at subgraphs carry the corresponding parent trace context.
4. Confirm subgraphs create child server spans and GraphQL request observations.
5. Confirm data fetcher/DataLoader observations appear inside that request's trace.
6. Confirm spans are exported to the same Collector/backend.

In integration tests, you can use an in-memory exporter or test observation handler to assert parent/child span relationships. In live environments, send an operation through the router and inspect the trace in the backend. Tests may use a fixed trace ID only in test environments; never hardcode trace IDs in production requests.

A valuable check is sending a request through the router versus calling a subgraph directly. Direct requests should start a new trace when no parent context exists; requests via the router must link to a parent span. This helps distinguish working subgraph instrumentation from broken propagation from the router.

## 19. Testing GraphQL observations in a subgraph

`GraphQlTester` can verify GraphQL responses, while Micrometer `MeterRegistry`/Observation test handlers verify recorded observations.

Scenarios to test:

| Scenario | Request observation | Field/DataLoader observation |
| --- | --- | --- |
| Successful query | `SUCCESS` | Field/batch succeeds |
| Resolver returns business error | Usually `REQUEST_ERROR` if error is non-internal | Data fetcher `ERROR` |
| Resolver throws internal error | `INTERNAL_ERROR` | Data fetcher `ERROR` |
| Batch loader fails | Request outcome per ErrorType in response | DataLoader `ERROR` |

Metrics tests should isolate `MeterRegistry` or compare counts before and after requests to avoid coupling to prior tests. Do not use `GraphQlTester` response assertions as a substitute for trace propagation tests; the two tests verify different contracts.

## 20. Troubleshooting observability across federation

| Symptom | Possible cause | How to investigate |
| --- | --- | --- |
| Router has traces but subgraphs do not appear | Router does not propagate `traceparent`, subgraph lacks HTTP tracing, or exporter is inactive | Check outbound headers, server instrumentation, and OTLP exporter |
| Subgraph has its own trace with a different trace ID from router | Parent context not received or replaced | Check W3C Trace Context and proxies/load balancers |
| HTTP metrics exist but no `graphql.request` | GraphQL instrumentation not configured or `ObservationRegistry` missing | Check GraphQlObservationInstrumentation/Boot auto-configuration |
| `graphql.request` exists but no data fetcher spans | Fields are trivial property accesses or instrumentation does not record resolvers | Check field mappings and GraphQL instrumentation |
| Router span shows slow subgraph but subgraph request is fast | Latency is in network, queues, connections, or router waiting/reading response | Compare router subgraph span, HTTP server span, and network metrics |
| GraphQL returns HTTP 200 yet dashboards show no errors | Dashboards filter only HTTP 5xx | Monitor `graphql.outcome` and field/DataLoader errors |
| Metrics have too many time series | Operation names, paths, IDs, or user data used as metric tags | Reduce to low-cardinality tags; move detailed data to traces where appropriate |
| GraphOS lacks field-level federated traces | Subgraph does not support FTV1 or is not configured to return traces | Check FTV1 support and header/request flow |
| OTLP traces exist but GraphOS Studio shows nothing | OTLP APM traces and GraphOS federated trace reporting are separate pipelines | Configure GraphOS reporting/FTV1 separately if Studio Insights is needed |
| Traces intermittently miss child spans | Independent sampling or context lost across async boundaries | Use parent-based sampling and inspect context propagation |
| Traces/logs contain sensitive data | Raw queries, variables, or exception messages logged | Redact payloads, restrict attributes, and check retention |
| Router slows down after enabling telemetry | Collecting too many spans/events or excessive sampling | Lower sampling, drop redundant attributes, and measure overhead |

## 21. Implementation checklist

When enabling observability for a federated graph with Spring GraphQL subgraphs:

1. Assign distinct `service.name` values to the router and each subgraph.
2. Enable Micrometer Observation in every Spring GraphQL service.
3. Configure the Micrometer Tracing bridge and OTLP exporter for subgraphs.
4. Enable Router telemetry and export traces/metrics to the Collector.
5. Ensure W3C `traceparent` propagates from the router to HTTP subgraphs.
6. Verify GraphQL observations nest under the right HTTP server spans.
7. Monitor `graphql.request`, `graphql.datafetcher`, and `graphql.dataloader`.
8. Use resource attributes to distinguish environment, service, and version.
9. Keep metric tags low-cardinality; avoid IDs, raw queries, and variables.
10. Correlate structured logs with trace ID/span ID.
11. Set appropriate sampling and prefer parent-based propagation.
12. Distinguish OTEL traces from Apollo FTV1 federated trace data.
13. Enable FTV1 only when your federation runtime/subgraph adapter supports it and GraphOS field traces are needed.
14. Build dashboards covering router, subgraph, GraphQL outcomes, and dependency latency.
15. Test trace propagation and GraphQL observations with a real operation.
16. Review privacy, retention, and telemetry overhead before production rollout.

Observability across federation succeeds when a single request can be traced from the router down to the exact subgraph, field resolver, and dependency. Spring for GraphQL provides GraphQL observations inside each subgraph; OpenTelemetry connects them across service boundaries; router telemetry reveals query plans and subgraph fetches. By distinguishing these layers properly and controlling cardinality and sampling, operations teams can pinpoint failing or slow branches without enabling excessive payload logging.

## References

- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Apollo Router — Router Telemetry](https://www.apollographql.com/docs/graphos/routing/observability/router-telemetry-otel)
- [Apollo Router — OpenTelemetry in Apollo Federation](https://www.apollographql.com/docs/graphos/routing/observability/router-telemetry-otel/enabling-telemetry/usage-guides/subgraph-instrumentation)
- [Apollo GraphOS — Federated Trace Data](https://www.apollographql.com/docs/graphos/routing/observability/graphos/federated-trace-data)
- [W3C — Trace Context](https://www.w3.org/TR/trace-context/)
