# Separating Business Telemetry and Framework Telemetry

A Spring Boot application needs two distinct observability perspectives. **Business telemetry** shows what business operations the system is executing and their business outcomes. **Framework telemetry** shows how the application, server, and technical components are processing that work.

These two perspectives must correlate during an incident investigation, yet each requires clear naming, semantics, ownership, and usage guidelines. Mixing them into an undifferentiated pool of metrics leads to dashboards that reflect technical health without answering user impact; conversely, a drop in a business metric might be misattributed to an infrastructure component.

This article focuses on establishing instrumentation boundaries in Spring Boot with Micrometer Observation, metrics, logs, and distributed tracing.

## 1. Two Different Operational Questions

Consider an order processing service. A request passes through the HTTP server, controller, order placement use case, repository, connection pool, and an HTTP client calling a payment gateway.

Within that flow, there are two sets of questions:

- Business perspective: How many orders were accepted? Is the payment decline rate rising or falling? How long does an order placement operation take from start to business outcome? Which sales channel is having issues?
- Technical perspective: Is the HTTP server returning errors or experiencing increased latency? Does the connection pool have enough connections? Is the JVM encountering long GC pauses? Are requests to the payment gateway timing out? Is consumer lag growing?

An HTTP 200 response does not mean the order was accepted: the payment gateway may return a valid decline result, and the application may represent that outcome inside a protocol-level success response. Similarly, an HTTP 500 response indicates the business operation failed, yet the HTTP code alone is insufficient to classify the business cause. Therefore, never use HTTP metrics as a substitute for business outcome metrics.

## 2. Defining the Boundary of Each Telemetry Type

**Business telemetry** is emitted at the use case or domain operation boundary. It expresses semantics that product and business stakeholders care about: an order was created, a payment was accepted, a reservation was rejected, a transaction completed, or a workflow expired.

**Framework telemetry** is typically emitted by Spring Boot, Actuator, Micrometer, and library instrumentation. It describes protocol, runtime, and dependency behavior: HTTP server/client, JDBC, connection pools, JVM, thread pools, messaging clients, and underlying platform components.

| Aspect | Business Telemetry | Framework Telemetry |
|---|---|---|
| Observation unit | Use case, domain operation, business outcome | Request, query, connection, thread, JVM, client call |
| Primary question | What are users and business workflows experiencing? | How are the application and dependencies performing? |
| Instrumentation placement | Application service, use case, domain boundary, or business event handler | Spring Boot auto-configuration, web server, client, datasource, runtime |
| Metric examples | `business.orders.outcomes`, `business.order.place` | `http.server.requests`, `http.client.requests`, `jvm.memory.used`, HikariCP metrics |
| Common labels | `outcome`, `channel`, `payment_method` with bounded value sets | `method`, `status`, normalized `uri`, `exception`, `client_name` |
| Consumers | Product, business owners, application teams, on-call | Application, platform, SRE, and on-call |
| Dashboards | Success rate, rejection rate, business throughput, use case latency | HTTP latency, dependency errors, pool saturation, CPU, memory, GC |

This is a boundary of **semantics and responsibility**, not merely how a metric is constructed. A custom metric is still framework telemetry if it measures open connections on a client. An Observation created by a developer is still business telemetry if it wraps the order placement use case.

Nor is every log written by the application business telemetry. A log recording a database connection error is a technical signal; a log recording that an order was accepted is a business signal. Classify according to what the signal describes.

## 3. Placing Instrumentation by Architectural Layer

Spring Boot already provides instrumentation for many common components. Keep framework signals at the exact layers they describe, then add business telemetry at the use case boundary. There is no need to manually recreate HTTP, JDBC, or JVM metrics when built-in instrumentation already meets operational needs.

Example flow:

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Spring MVC / HTTP server instrumentation"]
    B --> C["Controller"]
    C --> D["Use case: Place order"]
    D --> E["Business Observation and outcome metric"]
    D --> F["Order repository"]
    F --> G["JDBC / datasource instrumentation"]
    D --> H["Payment gateway client"]
    H --> I["HTTP client instrumentation"]
    E --> J["Metrics, traces, and logs backend"]
    G --> J
    I --> J
~~~

In this flow:

- HTTP server instrumentation measures request processing time and status at the web layer.
- Business Observation measures the duration of the order placement operation with business semantics.
- JDBC instrumentation measures database access activity.
- HTTP client instrumentation measures calls to the payment gateway.
- Traces connect spans under a shared trace context, making it possible to follow the request path.

A use case may be invoked from HTTP, a message consumer, a scheduler, or another use case. Measuring only at the controller leaves non-HTTP paths without business telemetry and may measure the same business flow differently depending on the entry point. Placing Observations at the application service or use case boundary keeps semantics consistent.

There is no need to create business Observations for every internal method. Choose operations with operational meaning that can be interpreted independently, such as `business.order.place`, `business.payment.authorize`, or `business.reservation.confirm`. Getters, mappers, or utility calls generally do not need separate spans or metrics.

## 4. Using Micrometer Observation for Business Operations

Micrometer Observation provides a single abstraction for recording an operation. Depending on handlers registered in `ObservationRegistry`, an Observation can emit metrics, tracing spans, or integrate with other components. Spring Boot can auto-configure the registry and instrumentation for supported libraries when matching dependencies are present.

The example below wraps an order placement use case with an Observation. `channel` comes from an enum with a controlled set of choices; `outcome` describes the final result of the use case.

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import java.util.Locale;

public class PlaceOrderService {

    private final ObservationRegistry observationRegistry;
    private final MeterRegistry meterRegistry;

    public PlaceOrderService(
            ObservationRegistry observationRegistry,
            MeterRegistry meterRegistry) {
        this.observationRegistry = observationRegistry;
        this.meterRegistry = meterRegistry;
    }

    public OrderResult place(PlaceOrder command) {
        String channel = command.channel()
                .name()
                .toLowerCase(Locale.ROOT);

        Observation observation = Observation
                .createNotStarted("business.order.place", observationRegistry)
                .lowCardinalityKeyValue("channel", channel)
                .start();

        try (Observation.Scope scope = observation.openScope()) {
            OrderResult result = executePlacement(command);

            observation.lowCardinalityKeyValue("outcome", "accepted");
            recordOutcome(channel, "accepted");
            return result;
        } catch (BusinessRuleRejectedException exception) {
            observation.lowCardinalityKeyValue("outcome", "rejected");
            recordOutcome(channel, "rejected");
            throw exception;
        } catch (RuntimeException exception) {
            observation.lowCardinalityKeyValue("outcome", "error");
            recordOutcome(channel, "error");
            throw exception;
        } finally {
            observation.stop();
        }
    }

    private void recordOutcome(String channel, String outcome) {
        Counter.builder("business.orders.outcomes")
                .tag("channel", channel)
                .tag("outcome", outcome)
                .register(meterRegistry)
                .increment();
    }

    private OrderResult executePlacement(PlaceOrder command) {
        // Execute use case: validate rules, persist the order, and coordinate payment.
        throw new UnsupportedOperationException("Illustrative example");
    }
}
~~~

This is an illustrative example of instrumentation placement and lifecycle; types `OrderResult`, `PlaceOrder`, and `BusinessRuleRejectedException` belong to the application model. In production code, ensure `accepted`, `rejected`, and `error` classification accurately reflects the use case contract. If additional statuses like `pending` or `cancelled` exist, add them only when they represent meaningful outcomes with a controlled value set.

Points to keep consistent:

1. The Observation wraps the entire business operation being measured. Its duration includes steps the use case actively waits on to produce a result, such as rule validation, repository access, and synchronous dependency calls.
2. Outcomes are recorded once the final result is known. Do not increment counters at the start of a request, because the request may not complete or may be rejected before producing an outcome.
3. Counters share the same name and distinguish cases via bounded tags. Total outcomes can be queried by grouping or filtering on `outcome` and `channel`.
4. If an Observation handler already exports a timer for `business.order.place`, do not create another manual Timer for the same operation just to capture identical data. Duplicate instrumentation adds overhead and causes confusion on dashboards.
5. If the application uses `@Observed` or an AOP mechanism to create Observations, do not simultaneously wrap the same method with manual Observations. Choose one mechanism per boundary.

`ObservationRegistry` and `MeterRegistry` should be injected from Spring Boot configuration. Ensure the appropriate dependencies and exporters for your target stack are present; creating an Observation alone does not guarantee data reaches a backend if the registry lacks matching handlers or exporters.

## 5. Designing Metric Names and Tags with Stable Semantics

Metric names should indicate which domain a signal belongs to and what it measures. A readable convention uses the `business` prefix for application-defined business metrics while preserving standard names from framework instrumentation provided by Spring Boot and Micrometer.

Examples:

| Signal | Metric Name or Group | Meaning |
|---|---|---|
| Order outcomes | `business.orders.outcomes` | Outcome counts by channel and outcome type |
| Order placement duration | `business.order.place` | Execution duration of the use case |
| HTTP server | `http.server.requests` | Request duration and status at the web layer |
| HTTP client | `http.client.requests` | Outbound HTTP call duration and status |
| JVM | `jvm.memory.used`, `jvm.gc.pause` | Memory and garbage collection activity |
| Connection pool | HikariCP metrics | Active, idle, pending connections and pool limits |

Display names in backends may be normalized according to the registry/exporter's naming convention. For instance, Prometheus typically converts dots in Micrometer names into underscores. Therefore, distinguish between metric names in application code and names transformed by the exporter.

### Low-Cardinality and High-Cardinality

For metrics, time series counts multiply across tag combinations. A metric with three tags having 5, 10, and 20 values respectively can generate up to 1,000 time series combinations. Adding a tag with hundreds of thousands of values sharply increases storage, query, and collection costs.

Suitable tags for business metrics are typically:

- `outcome`: `accepted`, `rejected`, `error`.
- `channel`: `web`, `mobile`, `partner`.
- `payment_method`: `card`, `bank_transfer`, `wallet`, if the value set is controlled.
- `region`: region codes from a finite list with operational meaning.

Never put the following values into metric tags:

- `order_id`, `user_id`, `account_id`, or transaction IDs.
- Emails, phone numbers, tokens, session IDs, or personal data.
- Full URLs containing path variables or query strings.
- Exception messages, SQL statements, arbitrary prose, or user-submitted filenames.

`uri` in HTTP metrics should also be normalized to route templates, such as `/orders/{id}`, instead of keeping `/orders/928374`. Spring Boot and web instrumentation usually provide route patterns when the framework recognizes the route; inspect configuration if dynamic URLs appear in metrics.

Micrometer Observation distinguishes low-cardinality and high-cardinality key-values. Low-cardinality values are suitable for metrics. High-cardinality values can be helpful on spans or logs when properly governed, but should not become metric dimensions. For example, an order ID helps locate a specific trace, yet access rights, data policies, and personal identifiability must be reviewed before placing it in traces or logs. Do not assume every backend treats high-cardinality attributes the same way.

Shared resource attributes such as `service.name`, `deployment.environment`, `service.instance.id`, or deployment region can distinguish services and environments. They describe where the signal originated rather than replacing tags that express business outcomes.

## 6. Correlating Metrics, Logs, and Traces While Preserving Semantics

The three signals complement one another:

- **Metrics** answer trends and magnitude: order acceptance rate, error counts, throughput, p95/p99 latency, connection pool utilization.
- **Traces** show which components a specific execution traversed, where time was spent, and which span produced an error.
- **Logs** record contextual details at a point in time, such as rejection reasons, business error codes, or approved diagnostic details.

Business telemetry can appear across all three signals. For example, the order placement use case emits an Observation/span `business.order.place`, counter `business.orders.outcomes`, and log event `order.placement.completed`. Framework telemetry can emit HTTP server, JDBC, and HTTP client spans, along with HTTP, datasource, and JVM metrics.

A structured business log can be represented as:

~~~json
{
  "event.name": "order.placement.completed",
  "order.channel": "web",
  "order.outcome": "accepted",
  "trace_id": "value-provided-by-tracing",
  "span_id": "value-provided-by-tracing"
}
~~~

The `trace_id` and `span_id` fields in this example are illustrative values. When Micrometer Tracing is configured with the corresponding logging integration, trace context can be injected into MDC so log patterns or structured logging record them automatically. Verify your actual configuration before assuming these fields are always present.

Log events should describe what happened without copying entire requests or domain objects. If looking up a specific order is necessary, record only an approved identifier protected by appropriate access, retention, and masking policies. Never place sensitive data into metric tags or spans merely because the backend allows storing that attribute.

Do not use logs as primary counters. Logs can be filtered, sampled, delayed, or dropped in the pipeline. Metrics are better suited for calculating ratios and aggregate alerts. Conversely, do not force every diagnostic detail into metrics, as metrics have cardinality constraints and do not preserve per-occurrence context.

## 7. Organizing Exporters, Dashboards, and Ownership

Business telemetry and framework telemetry can flow through the same `MeterRegistry`, `ObservationRegistry`, OTLP exporter, or backend. Separation should first be established through semantics, naming conventions, tag schemas, dashboards, and ownership.

A practical organization:

- Business dashboards display outcome counts, acceptance/rejection rates, throughput, and use case latency.
- Technical dashboards display HTTP server/client, JVM, datasource, thread pools, messaging, and dependency health.
- Trace views display both business spans and framework spans within the same trace to link impact to root cause.
- Business alerts fire when use case success rates or latencies breach SLOs.
- Technical alerts fire when pools approach exhaustion, HTTP client timeouts rise, consumer lag grows, or runtime resources near limits.

Split into separate registries, exporters, or tenants only when concrete requirements demand it for security, retention, cost, ownership, or operational isolation. Splitting pipelines prematurely increases configuration overhead, raises the risk of losing cross-signal correlation, and forces on-call engineers to query multiple places. If separation is needed, explicitly define which signals go where, which resource attributes are preserved, how trace context remains linked, and who owns each pipeline.

Do not create a dedicated exporter for business telemetry solely because metric names start with `business`. Prefixes and schemas suffice for categorization in most systems. Separate infrastructure boundaries only add value when solving concrete operational or governance requirements.

## 8. Sampling and Business Data

Metrics are typically aggregated over collection intervals and do not apply trace sampling in the usual sense. If trace sampling retains only a fraction of requests, a specific trace may not appear in the backend even though the business counter incremented accurately. Therefore:

- Use metrics to track totals, ratios, trends, and SLOs.
- Use sampled traces to investigate request paths and analyze latency.
- Tune sampling policies based on load, cost, and flow criticality. You can prioritize retaining error traces or traces matching investigative criteria if the tracing backend supports such mechanisms.
- Never treat traces as a transaction ledger. If the business requires persisting every transaction, every decision, or audit evidence, use a database, audit log, or event store with matching durability guarantees.

Especially for payments, reconciliation, and financial transactions, observability counters and traces do not replace durable transaction records. Sampling, retention limits, or telemetry pipeline failures must never lose mandatory business records.

## 9. Using Both Perspectives in an Investigation

Suppose a dashboard shows order acceptance rate dropping from 98% to 84%.

Start with business telemetry to confirm blast radius: which outcome increased, which channel is impacted, when it started, and whether use case latency changed. Then pivot to framework telemetry to check the payment gateway HTTP client, timeouts, connection pools, HTTP server, and JVM resources.

You may encounter scenarios like:

| Observation | Possible Interpretation | Next Verification Step |
|---|---|---|
| `rejected` rate rises, HTTP 5xx does not rise | Valid business rejections or changed business rules | Analyze bounded-value reason codes; cross-check product and provider changes |
| `error` rate rises, `http.client.requests` shows rising timeouts | Dependency may be failing to respond on time | Open sample traces to inspect dependency call spans, timeouts, and retries |
| Business latency rises, active DB pool near limit | Use case may be waiting for connections or slow queries | Check pool metrics, JDBC spans, and associated queries |
| HTTP latency rises while business latency stays steady | Added time may sit outside the measured use case | Check filters, serialization, gateway, network, or post-use-case processing |
| Business throughput drops alongside rising consumer lag | Asynchronous processing pipeline may be backed up | Check consumer framework metrics, processing speed, and message errors |

This table only suggests investigative directions. A single metric does not prove causality. Use timestamps, service identity, trace context, and compatible dimensions to correlate signals. When a trace is absent due to sampling, metrics still narrow down scope and timing.

## 10. Verifying Instrumentation Quality

Before wiring telemetry into dashboards and alerts, verify that names, units, tags, and recording points match the business contract.

- One completed business operation increments an outcome counter exactly once, even when retries occur at the technical layer.
- HTTP client retries are not misinterpreted as multiple orders or multiple use case completions.
- `accepted`, `rejected`, and `error` are clearly defined; technical errors are not lumped together with valid business rejections.
- Observations wrap the exact use case boundary and stop in every success or exception branch.
- Metrics have no tags containing IDs, dynamic URLs, emails, or unbounded values.
- Framework metrics continue to be exported with standard names and meanings after configuring exporters.
- Traces connect business spans with HTTP, JDBC, or messaging spans when the same trace context propagates correctly.
- Logs contain no sensitive payloads and correlate with traces when tracing is enabled.
- Business dashboards and technical dashboards have clear owners, alert thresholds, and runbooks.

You can use `SimpleMeterRegistry` in unit tests to verify metric names, tags, and counter increments. For Observations, lifecycle can be verified using an appropriate test registry and handler. Integration tests should verify propagation across the HTTP or messaging boundaries the application actually uses. There is no need to test internal details of every framework-generated metric inside every business unit test; verify those at the configuration or integration test level.

## 11. Common Pitfalls That Cause Confusion

**Using HTTP status as business outcome.** HTTP status describes protocol outcome. A declined transaction may be returned as HTTP 200 or 4xx depending on the API contract. Record outcomes at the use case.

**Placing business metrics in controllers.** This misses invocations from messages, schedulers, or other use cases and couples results to the transport layer. Placing metrics at the application/domain boundary is cleaner.

**Putting identifiers into metric tags.** Every order or user spawns a new time series, making backends hard to operate and query. Use bounded dimensions for metrics; keep identifiers in traces/logs only when permitted and controlled.

**Creating manual metrics duplicating auto-instrumentation.** Duplicate metrics cause dashboards to double-count or lead different readers to interpret the same quantity differently. Leverage framework instrumentation and add only signals where the framework lacks business semantics.

**Measuring every method as a business operation.** Excessive Observations/spans make traces hard to read and increase overhead. Select meaningful use cases or domain operations; let framework instrumentation measure fine-grained technical calls.

**Splitting exporters based solely on naming.** Separate pipelines add operational overhead without guaranteed benefit. Start with bounded schemas and dashboards; split infrastructure only for explicit requirements.

**Treating telemetry as audit data.** Metrics are aggregated, traces are sampled, and logs expire under retention. Audit data requires dedicated storage and integrity guarantees.

## 12. Architectural Conventions a Team Should Standardize

A Spring Boot team can agree on the following rules so every service emits consistent telemetry:

1. Keep framework instrumentation provided by Spring Boot/Micrometer for HTTP, JVM, database, messaging, and clients.
2. Place business Observations at use case boundaries with names describing the business action.
3. Use low-cardinality key-values for bounded dimensions; never put identifiers or personal data into metric tags.
4. Use counters for business outcomes and Observations/timers for processing duration; define recording points clearly to prevent double-counting on retries.
5. Use structured logs for events needing detail and trace context for correlation; never log full payloads.
6. Keep business and framework telemetry in the same trace when possible, while organizing dashboards, alerts, and ownership by intended purpose.
7. Use metrics for SLOs and trends; use sampled traces for investigation; use dedicated business storage for audits.
8. Add separate pipelines only when concrete requirements exist around security, retention, cost, or operational responsibility.

When these two telemetry layers are properly separated, product teams can see what impact users are experiencing, and engineering teams can trace from that impact to the component causing the issue. Micrometer Observation bridges both perspectives within a single execution flow; consistent conventions for naming, tags, sampling, and ownership keep telemetry understandable as the system grows.
