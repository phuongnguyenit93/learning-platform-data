# Avoiding Duplicate Instrumentation in Spring Boot Observability

In a Spring Boot application, a single request can traverse multiple layers and multiple pre-instrumented libraries. If each layer creates its own metric, span, or log for the same operation, the observability system records duplicate data: request counts or durations are doubled, traces contain identical spans, logs repeat, and collection costs rise. As a result, dashboards and alerts can lead to wrong conclusions.

Proper design starts by identifying the boundary of each operation and choosing one instrumentation source responsible for that boundary. A single Observation can be turned into multiple signals by different handlers; that is how one operation produces both metrics and tracing simultaneously, rather than duplicate instrumentation.

## Objectives and Principles

In Spring Boot Observability, maintain three properties:

- Every technical boundary or business operation has one clear instrumentation owner.
- Signals produced from the same Observation link together via trace context and consistent attributes.
- Nested spans represent distinct pieces of work with causal relationships; they do not repeat the same work at the same boundary.

You can use this design rule: **one operation, one primary Observation; multiple handlers may process that Observation**. There is no need to create one Observation for metrics and a separate span for tracing if both describe the same operation.

## Distinguishing Multiple Signals from Duplicate Instrumentation

Micrometer Observation is the shared integration point. `ObservationRegistry` receives Observations; appropriate `ObservationHandler` instances can record timers or meters, create spans via the Micrometer Tracing bridge, and populate context for log correlation. Thus, one Observation can appear across multiple observability systems while still being instrumented only once.

| Scenario | Is It Duplicate? | Interpretation |
|---|---|---|
| One Observation emits both a timer and a span | No | Two signals describe the same operation and can be correlated. |
| An HTTP server span contains a business span, an HTTP client span, and a JDBC span | No, if each span describes distinct work | This is a parent-child hierarchy following the execution flow. |
| Spring Boot creates an HTTP server Observation and a custom filter creates another Observation for the same request | Possibly | Two instrumentations share ownership of the same HTTP server boundary. |
| A business Observation and a manual Timer measure the exact same method | Possibly | Risk of recording the same duration or invocation count twice. |
| Micrometer instrumentation and the OpenTelemetry Java agent both instrument an HTTP client | Possibly | Two mechanisms may emit two spans for the same library call. |
| The same metric is sent through two pipelines and the backend merges them as two independent sources | Not duplicate app instrumentation, but duplicate pipeline | Inspect export configuration and how the backend identifies series. |

A well-structured trace might look like this:

~~~text
HTTP request
└── HTTP server Observation
    └── inventory.reserve Observation
        ├── HTTP client Observation
        └── JDBC Observation
~~~

HTTP server, business operation, outbound service call, and database query are distinct boundaries. Child spans pinpoint where time was consumed. Problems only arise when two instrumentations describe the exact same boundary and unit of work.

## Instrumentation Sources to Inventory

Before adding manual instrumentation, identify what the application already has. In a Spring Boot application, common sources include:

1. **Spring Boot and Micrometer**: Actuator, `ObservationRegistry`, Spring MVC or WebFlux integrations, HTTP clients, datasources, and supported libraries. Exact integrations depend on Spring Boot, Micrometer, starter versions, and libraries in use.
2. **Micrometer Tracing bridge**: translates Observations into spans and connects tracing with the configured exporter ecosystem.
3. **OpenTelemetry Java agent**: instruments libraries at runtime, such as HTTP clients, JDBC, or messaging. Exact coverage depends on agent version and configuration.
4. **Application-authored instrumentation**: servlet filters, interceptors, aspects, decorators, wrappers, manual Timers, or Observations created directly in services.
5. **Annotations and AOP**: annotations like `@Observed` or `@Timed` may be processed by aspects if the application enables the corresponding mechanism.

Document the boundary each source owns. Never assume a library is definitely instrumented based solely on dependency names; verify versions, configuration, and actual application output.

| Boundary | Source to Check First | When Manual Addition Is Needed |
|---|---|---|
| Inbound HTTP request | Spring Web Observation and Actuator configuration | When a distinct business operation is needed, not re-measuring the full request |
| Outbound HTTP request | `RestClient`, `WebClient`, or client Observation; Java agent if present | When measuring a business operation around the call with a different name and meaning |
| JDBC access | Datasource instrumentation or Java agent | When measuring a high-level data business flow, without recreating spans per SQL statement |
| Business processing | Application-defined Observation | When a business boundary is meaningful and not yet measured elsewhere |
| Log correlation | Trace context and MDC managed by tracing integration | When adding bounded business fields, without duplicating lifecycle logs |

## Designing So Each Boundary Has One Owner

### 1. Keep Auto-Instrumentation at Library Boundaries

If Spring Boot already creates an Observation for the HTTP server, leverage that Observation to measure requests. Avoid adding a filter solely to create another timer or span with the same meaning. If you need to enrich route names, endpoint groups, or attributes, prefer extending existing Observation conventions or customizers.

Similarly, when an HTTP client or datasource is already instrumented, do not create another span with equivalent name and scope around the library call itself. Inspect traces first to see what existing spans already carry and what is missing.

### 2. Reserve Manual Instrumentation for Business Boundaries

Auto-instrumentation typically describes technical boundaries: receiving an HTTP request, calling an HTTP client, querying JDBC. The application can add Observations for business operations with distinct meaning, such as reserving inventory, calculating fees, or confirming an order.

The example below creates an Observation for inventory reservation. `ObservationRegistry` is configured by Spring Boot and may have handlers for both metrics and tracing:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {

    private final ObservationRegistry observationRegistry;

    public InventoryService(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    public Reservation reserve(String sku, String warehouse) {
        return Observation.createNotStarted(
                        "inventory.reserve",
                        observationRegistry
                )
                .lowCardinalityKeyValue("warehouse", warehouse)
                .observe(() -> reserveInternal(sku, warehouse));
    }

    private Reservation reserveInternal(String sku, String warehouse) {
        // Apply business rules and update inventory.
        return new Reservation(sku, warehouse);
    }
}
~~~

This business Observation does not replace the HTTP server Observation or JDBC Observation. It adds a perspective with a different name and scope. When the inner call reaches an instrumented datasource, the JDBC span can become a child span in the same trace.

Include in low-cardinality keys only values with bounded, controlled domains, such as operation type, normalized outcome, or deployment region. Never use SKU, order ID, user ID, or URLs containing dynamic IDs as metric tags. If an identifier is needed for trace investigation, evaluate high-cardinality attributes and appropriate data policies; such attributes should not become metric labels.

### 3. Do Not Wrap the Same Method with Multiple Mechanisms

A method can be instrumented multiple times if it has both an aspect-handled annotation and manually created Observations inside. For example, when `ObservedAspect` is enabled, placing `@Observed` on a method and also creating an Observation with the same name inside the method body can produce two nested Observations for the same operation.

A similar situation occurs when combining `@Timed`, manual Timers, and Observations with a meter handler. Before keeping multiple mechanisms, define what each measures. If they all measure the same invocation count or duration, pick one mechanism as the canonical source.

### 4. Do Not Create a Manual Timer If an Observation Already Records That Metric

The example below risks recording the duration of `inventory.reserve` twice if `ObservationRegistry` already has a meter handler emitting the corresponding timer:

~~~java
public Reservation reserve(String sku, String warehouse) {
    Timer.Sample sample = Timer.start(meterRegistry);
    try {
        return Observation.createNotStarted(
                        "inventory.reserve",
                        observationRegistry
                )
                .observe(() -> reserveInternal(sku, warehouse));
    } finally {
        sample.stop(meterRegistry.timer("inventory.reserve"));
    }
}
~~~

Here, the Observation may already emit a meter, while `Timer.Sample` records another timer for the same invocation. A simpler approach is letting the Observation serve as the single recording source:

~~~java
public Reservation reserve(String sku, String warehouse) {
    return Observation.createNotStarted(
                    "inventory.reserve",
                    observationRegistry
            )
            .lowCardinalityKeyValue("warehouse", warehouse)
            .observe(() -> reserveInternal(sku, warehouse));
}
~~~

If a metric with different aggregation rules is needed, design a separate metric name, unit, tags, and purpose; verify it does not re-measure the exact same quantity under the same semantics. Cases genuinely requiring an independent Timer must be clearly documented and tested so dashboards do not sum or confuse the two quantities.

### 5. Avoid Two Agents Instrumenting the Same Library

The OpenTelemetry Java agent can automatically instrument libraries that Micrometer or Spring Boot also support. When both enable instrumentation for the same HTTP client or JDBC driver, traces may exhibit nearly identical spans.

Choose one mechanism as the owner for each library or boundary. You can keep Spring Boot/Micrometer for application integrations and selectively disable the corresponding agent instrumentation, or choose the agent for that boundary and avoid creating overlapping manual spans. Specific enable/disable configuration depends on agent and library versions, so check documentation for your running version before changing settings.

Do not disable the entire agent or all Observations merely because you see a pair of duplicate spans. Pinpoint which instrumentation created the redundant span, then adjust at the smallest scope possible.

## Customizing Existing Instrumentation

When existing instrumentation already measures the right boundary but lacks attributes, enrich it rather than creating a new instrumentation.

Common approaches:

- Use `ObservationConvention` or Spring-specific conventions to normalize names and key-values on existing Observations.
- Use `ObservationRegistry` customizers or `ObservationFilter` when applying shared rules.
- Add business attributes with bounded value sets for metric grouping.
- Use trace context and MDC to correlate logs with traces, instead of creating a span solely to obtain a trace ID.
- Normalize route templates instead of full URLs containing dynamic IDs.

Observation names should describe the work and follow consistent conventions. For instance, `inventory.reserve` describes a business operation; an HTTP client Observation describes an outbound call. Avoid assigning the same generic name across every layer, as reading traces makes it hard to tell which span represents which piece of work.

## Checking for Signs of Duplication

You can detect redundant instrumentation by cross-checking traces, metrics, and logs.

**In traces:**

- Look for two spans with the same name, same span kind, same attributes, and nearly identical start times.
- Check whether two spans cover the exact same HTTP call, SQL query, or request.
- Inspect parent-child relationships. Two nested spans only make sense when the child represents a distinct sub-step; two spans describing the same call often signal duplication.
- Inspect instrumentation scope or library metadata on spans if the exporter/backend displays it.

**In metrics:**

- Compare request counts before and after enabling an agent or aspect.
- Look for metrics sharing the same meaning, unit, and tag set emitted from two sources.
- Watch for metric counts or durations nearly doubling after adding instrumentation.
- Distinguish measuring two genuinely different quantities from recording the same quantity twice.

**In logs:**

- Check whether the same business event is logged in a filter, an aspect, and a service.
- Verify logs carry `traceId` and `spanId` matching the active trace.
- Avoid logging start/stop across multiple layers if those lines add no investigative value.

A single sign is not conclusive on its own. For example, two spans with the same name may stem from two valid retries. Cross-check parent span, timestamps, attributes, attempt counts, and instrumentation source code before disabling a source.

## Decision Workflow Before Adding Instrumentation

1. **Identify the question to answer.** Do you need timing for an HTTP request, an external service call, a DB query, or a business operation like inventory reservation?
2. **Identify boundaries already measured.** Inspect Spring Boot, Micrometer, agent, annotation/aspect configurations, and actual traces.
3. **Choose the owner.** For library boundaries, prefer existing integrations. For unrepresented business boundaries, create one business Observation.
4. **Reuse the existing Observation when only metadata is needed.** Use conventions or filters instead of creating a new span with the same scope.
5. **Check cardinality.** Metric tags must have bounded value sets; identifying data must not enter low-cardinality tags.
6. **Verify after changes.** Compare traces, metric recording counts, and logs before and after. One sample operation should emit the exact expected number of spans and metrics.

## Testing and Completion Criteria

Integration-level tests should cover critical boundaries. For a request flowing through controller, service, and repository, verify that:

- The HTTP server is recorded once.
- The business Observation appears once per business execution.
- HTTP client or JDBC spans appear only when corresponding calls occur and are not doubled by both an agent and application instrumentation.
- Metrics generated from Observations have expected names, units, and tags.
- When business logic throws an exception, the Observation still completes its lifecycle properly and the error is recorded.
- Logs correlate with traces without generating multiple identical lifecycle logs.

Test registries or test exporters can be used to capture Observations, meters, and spans in test environments. Do not merely assert "data exists"; assert counts, names, parent-child relationships, and key attributes. When upgrading Spring Boot, Micrometer, or Java agent versions, re-run these tests because auto-instrumentation coverage may change.

A design meets requirements when every boundary has a clear owner, traces depict genuinely distinct processing steps, metrics are never double-recorded, and logs remain correlated with traces. This keeps measurements faithful to application behavior and lets development teams investigate errors, latency, and production behavior reliably.
