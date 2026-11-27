# @Timed

In the **Annotation observability** chapter of the **SPRING_BOOT_OBSERVABILITY** module, Micrometer's `@Timed` annotation helps measure the execution duration of a method and record the result into a `Timer`. When a Spring Boot application is properly configured with Micrometer metrics, the `Timer` can be exported to a registry to track invocation count, total time, max, and histogram/percentiles if enabled.

`@Timed` is suitable when you need to measure a method with clear operational significance, such as processing a report, calculating a price, or executing a business step. However, the annotation does not automatically measure every piece of code: it requires an appropriate interception mechanism, typically Spring AOP/proxy or correspondingly configured instrumentation. Self-invocation, private/final methods, objects instantiated outside the Spring context, and async execution can prevent measurements from running as expected.

This lesson explains how to use `@Timed` in Spring Boot, how to configure metric names/tags/histograms, proxy limitations, differences between synchronous and asynchronous methods, how to test, and how to avoid high cardinality.

## 1. Learning Objectives

After this lesson, you can:
1. Explain how `@Timed` creates a `Timer` and where the data is recorded.
2. Distinguish method timing from HTTP server/client observations.
3. Configure Micrometer and the AOP/instrumentation required for `@Timed`.
4. Choose stable metric names and tags.
5. Enable histograms/percentiles appropriate for latency analysis.
6. Understand Spring proxy limitations: self-invocation, private/final methods, and objects not managed by Spring.
7. Evaluate `@Timed` with async/reactive methods and completion lifecycle.
8. Test count, duration, and tags using `MeterRegistry`.
9. Avoid using request/user identifiers as metric tags.
10. Know when to use the Observation API or a manual `Timer` instead of the annotation.

## 2. What Is @Timed?

`@Timed` is a Micrometer annotation used to measure the execution duration of a method. When processed by the corresponding instrumentation/AOP, each time the method is called it is recorded into a `Timer` with the configured name and tags.

~~~java
@Service
class PricingService {

    @Timed(value = "pricing.calculate", description = "Time spent calculating price")
    public Price calculate(PriceRequest request) {
        return pricingEngine.calculate(request);
    }
}
~~~

A `Timer` can provide:
- `count`: the number of times the method was measured.
- `totalTime`: the total duration across all calls.
- `max`: the maximum duration within the corresponding window/implementation.
- Histogram buckets if enabled.
- Percentiles if supported by the registry and configuration.

Not all registries store or query the same set of statistics. Prometheus typically uses histogram buckets to compute quantiles server-side; some registries may compute client-side percentiles. Understand the backend's semantics before using percentiles in alerts.

### How Does @Timed Differ from @Observed?

| Annotation/API | Primary Purpose | Signal |
| --- | --- | --- |
| @Timed | Measure method duration/count. | Micrometer Timer. |
| @Observed | Describe an operation for multiple Observation handlers to process. | Metrics and tracing depending on handlers. |
| HTTP Observation | Measure an HTTP exchange at the framework layer. | HTTP metrics and spans. |
| Manual Timer API | Measure a code block with a custom lifecycle. | Micrometer Timer. |

If you want a method to produce both metrics and span/correlation context, `Observation` is usually a better abstraction. Do not add both `@Timed` and `@Observed` around the same method unintentionally, as this can produce duplicate metrics or two similar spans.

## 3. Dependencies and Enablement in Spring Boot

Spring Boot manages Micrometer through Actuator and registry dependencies. Example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

For `@Timed` to be processed via Spring AOP, the application needs an AOP mechanism compatible with the Boot version and annotation usage. In traditional annotation-based Micrometer configuration, AspectJ support and registering a `TimedAspect` are required:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
~~~

`TimedAspect` is the Micrometer AOP component that supports processing `@Timed` on Spring beans. Do not assume that simply adding Actuator causes the annotation to be intercepted automatically across all versions/configurations. Check the reference docs and project bean configuration.

~~~java
@Configuration(proxyBeanMethods = false)
class MetricsAnnotationConfiguration {

    @Bean
    TimedAspect timedAspect(MeterRegistry registry) {
        return new TimedAspect(registry);
    }
}
~~~

Depending on the Boot/Micrometer version, auto-configuration may be available or you may need to declare the aspect manually. Avoid registering two `TimedAspect` beans at the same time. Check the application context and metric counts to confirm only one instrumentation is active.

## 4. Naming Timers and Tags

The metric name should describe a stable operation and must not contain per-request values.

~~~java
@Timed(
    value = "order.validation",
    description = "Time spent validating an order",
    extraTags = {"operation", "validate"}
)
public ValidationResult validate(OrderRequest request) {
    return validator.validate(request);
}
~~~

Guidelines:
- Use a metric name that reflects the operation, such as `order.validation`.
- Tags should have a bounded set of values, such as `operation`, `outcome`, `channel`.
- Do not put order ID, user ID, email, request ID, or raw URL into tags.
- Do not put the exception message as a tag.
- Avoid setting tag values from caller-controlled input.

| Tag | Example Value | Remarks |
| --- | --- | --- |
| operation | validate | Bounded set. |
| outcome | success / failure | Bounded set. |
| channel | web / batch | Bounded set if controlled. |
| order.id | 1001 | High cardinality, unsuitable. |
| customer.email | alice@example.com | PII and high cardinality. |
| exception.message | Connection timeout to host... | Unstable, may contain sensitive data. |

`extraTags` are fixed key/value pairs declared on the annotation. If you need dynamic tags, consider an `Observation` convention or the `Timer` API with an allowlist; do not turn arbitrary method arguments into tags.

## 5. Configuring Histograms and Percentiles

A `Timer` can be configured to export histogram buckets or percentiles. In Spring Boot, configure distribution statistics by metric name:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        order.validation: true
      percentiles:
        order.validation: 0.5, 0.95, 0.99
      slo:
        order.validation: 100ms, 250ms, 500ms
~~~

Supported properties and export behavior depend on the registry/version. Histograms are useful when you want to compute percentiles in a centralized backend; client-side percentiles may not aggregate accurately across multiple instances. With Prometheus, histogram buckets are usually the better choice for aggregated quantiles.

Choose bucket/SLO boundaries based on real latency objectives. Too many buckets increase series count and storage cost. Do not blindly enable histograms for every `Timer`.

## 6. Spring AOP Proxy and Limitations of @Timed

Spring AOP typically intercepts method invocations through a proxy. This introduces several important limitations.

### Self-invocation

~~~java
@Service
class ReportService {

    public void runReport() {
        generate(); // internal call on this, bypasses proxy
    }

    @Timed("report.generate")
    public void generate() {
        // expensive work
    }
}
~~~

If `runReport()` calls `generate()` directly on the same object, the invocation may not go through the proxy, so `@Timed` is not applied. How to address this:
- Place the measured method in another Spring bean and inject that bean.
- Call through the proxy bean from an external caller.
- Use the manual `Timer`/Observation API if the operation does not fit a proxy model.

Do not use self-injection as a default workaround if cleaner boundaries can be designed.

### Private and final methods

Proxy-based AOP only intercepts methods compatible with the proxy strategy and override/interface capabilities. Private methods cannot be called through a proxy like public service methods. `final` classes/methods can also restrict subclass-based proxies. Check the proxy type (JDK interface proxy or class-based proxy) and method visibility.

### Objects not managed by Spring

If code creates an object via `new PricingService(...)`, Spring AOP does not manage that object; annotations are not intercepted. Use the Spring bean lifecycle and dependency injection.

## 7. Synchronous vs. Asynchronous

For synchronous methods, a `Timer` typically measures from when the method is intercepted until it returns or throws an exception.

For async methods returning `CompletableFuture`, `CompletionStage`, or Reactor `Mono`/`Flux`, verify whether the instrumentation measures until the method returns the wrapper object or until the computation completes. A simple AOP annotation may not accurately measure asynchronous completion time if the aspect does not support that return type/lifecycle.

~~~java
@Timed("report.generate.async")
public CompletableFuture<Report> generateAsync() {
    return CompletableFuture.supplyAsync(reportGenerator::generate);
}
~~~

This method can return the `CompletableFuture` almost immediately while the work continues afterwards. Do not assume the `Timer` by default covers the full future completion time. For async/reactive work, use the Observation/`Timer` API with an explicit completion lifecycle or instrumentation that supports that return type; stop the measurement in the callback/terminal signal.

For Reactor, do not block the pipeline just to measure duration. Use instrumentation/context propagation compatible with the reactive stack.

## 8. Exceptions and Outcome

If a method throws an exception out of the proxy, the aspect can record the exception according to the Micrometer version's semantics. If the method catches the exception and returns a fallback, the aspect may treat the invocation as having completed normally.

~~~java
@Timed("inventory.lookup")
public Inventory find(String sku) {
    try {
        return repository.find(sku);
    } catch (DataAccessException ex) {
        log.warn("Inventory lookup failed, errorType={}",
                ex.getClass().getSimpleName());
        throw ex;
    }
}
~~~

Do not put exception messages into tags. If you need to distinguish success/failure in metrics, add an `outcome` tag with a bounded set of values via `Observation`/custom instrumentation, or intentionally separate timers. Do not create a separate tag value for each exception instance.

An HTTP 404 or business rejection is not necessarily an exception. Define outcomes according to operation semantics rather than solely on whether a Java method throws.

## 9. @Timed and HTTP/Database Observations

Spring Boot already provides framework-level observations for HTTP server/client and certain database/client integrations. `@Timed` is suitable for measuring an additional business method, such as `order.validation`, `report.generation`, `pricing.calculate`, or `inventory.reconciliation`.

You should not add `@Timed` to every controller method if `http.server.requests` already measures the full request duration. Doing so can make sense when isolating a specific business phase, but the metric must have a distinct name and clear purpose.

Similarly, `@Timed` on a repository method does not replace JDBC spans. The `Timer` reports total method duration; JDBC spans show each SQL call. One repository method may execute multiple queries, so the two signals answer different questions.

~~~mermaid
flowchart TD
    Request["HTTP server observation"]
    Request --> Service["OrderService"]
    Service --> Timed["Business @Timed: order.validation"]
    Timed --> Repo["Repository method"]
    Repo --> JDBC["JDBC/database spans"]
    Request --> Metrics["HTTP timer"]
    Timed --> BusinessMetric["Business method timer"]
    JDBC --> Trace["Trace backend"]
~~~

## 10. Inspecting the Timer via Actuator

If the Actuator metrics endpoint is exposed in a secured environment, query:

~~~http
GET /actuator/metrics/order.validation
~~~

Illustrative response example:

~~~json
{
  "name": "order.validation",
  "measurements": [
    { "statistic": "COUNT", "value": 42.0 },
    { "statistic": "TOTAL_TIME", "value": 1.26 },
    { "statistic": "MAX", "value": 0.084 }
  ],
  "availableTags": [
    { "tag": "operation", "values": ["validate"] }
  ]
}
~~~

Actual payload depends on the registry, meter filters, and distribution settings. If the meter does not appear:
- Check the `TimedAspect` bean.
- Verify the method is called through the Spring proxy.
- Verify the right `MeterRegistry`.
- Verify metric name/tag values.
- Check meter filters or registry configuration.
- Verify the annotation is imported from `io.micrometer.core.annotation.Timed`.

Do not expose the Actuator metrics endpoint publicly just to inspect it; protect it with authentication and network policy.

## 11. Testing @Timed

You can use `SimpleMeterRegistry` in unit/integration tests to verify that the `Timer` is registered:

~~~java
@SpringBootTest
class PricingServiceTimedTest {

    @Autowired
    PricingService pricingService;

    @Autowired
    MeterRegistry meterRegistry;

    @Test
    void recordsMethodExecution() {
        pricingService.calculate(new PriceRequest("SKU-1"));

        Timer timer = meterRegistry.find("pricing.calculate").timer();

        assertThat(timer).isNotNull();
        assertThat(timer.count()).isEqualTo(1);
    }
}
~~~

Tests must invoke the Spring bean from the application context so the call goes through the proxy. Calling a method on a manually constructed object in a test can bypass AOP.

Test cases:
1. Method success records count and duration.
2. Method throwing an exception still records timer/error per convention.
3. Self-invocation is detected or avoided by design.
4. Private/final method behavior is verified.
5. Tags do not contain dynamic identifiers.
6. Async completion duration is tested against actual semantics.
7. No duplicate `Timer` due to multiple aspects.
8. Histograms/percentiles are exported properly to the registry.

## 12. Troubleshooting

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| No Timer | Missing TimedAspect/AOP or method bypasses proxy. | Check AOP dependency, bean, and call path. |
| Timer count is 0 | Method not called or test calls object outside Spring context. | Inject bean and invoke through proxy. |
| Self-invocation not measured | Internal call via `this`. | Extract bean or use Timer/Observation API. |
| Private/final method not intercepted | Proxy strategy does not support the method. | Use an appropriate public method or manual instrumentation. |
| Duration too short for CompletableFuture | Aspect measures when method returns future instead of completion. | Measure future/async lifecycle with an appropriate API. |
| Timer appears twice | Multiple TimedAspects or overlapping custom instrumentation. | Check bean and AOP configuration. |
| Tag values grow continuously | Dynamic values added to tags. | Use allowlist and remove identifiers. |
| Percentiles do not aggregate properly | Using client-side percentiles across multiple instances. | Use histogram buckets and backend aggregation. |
| Timer without tracing span | @Timed only records metrics; no Observation/tracing integration. | Use @Observed or Observation API if spans are needed. |
| Metric name differs from expected | Naming convention/registry renames it. | Check Actuator and exported series. |

## 13. Runbook: @Timed Creates No Metrics

1. Confirm the annotation is imported from Micrometer.
2. Check Spring Boot/Micrometer version and dependency management.
3. Check the AOP starter and `TimedAspect` bean.
4. Verify the service is a Spring bean.
5. Verify the caller goes through the proxy; check for self-invocation.
6. Verify method visibility and proxy strategy.
7. Invoke the method once in a test.
8. Query Actuator `/actuator/metrics/{metric-name}`.
9. Check tags and meter filters.
10. If the method is async, verify the `Timer` stops when computation completes.
11. Check for duplicate aspects/custom instrumentation.
12. If distributed tracing is needed, check Observation/Tracing integration separately; `Timer` alone does not guarantee a span.

## 14. Self-Check Exercises

### Exercise 1 — Self-invocation

Method `run()` calls method `calculate()` annotated with `@Timed` in the same class. Why might no `Timer` be created?

**Answer:** An internal call via `this` does not go through the Spring proxy, so AOP advice may not run. Move the method to another bean or measure manually using `Timer`/`Observation`.

### Exercise 2 — Async duration

A method with `@Timed` returns a `CompletableFuture` immediately, while the computation runs for 5 seconds. What might the `Timer` record?

**Answer:** If the aspect only measures synchronous invocation, the `Timer` may only measure the time to create/return the future, not the 5-second completion. Instrumentation wrapping async completion is required.

### Exercise 3 — Cardinality

Should `orderId` be added to dynamic `extraTags` to look up a specific order?

**Answer:** No. A metric tag creates a time series per order and increases cardinality. Use logs/traces with controlled identifiers instead.

### Exercise 4 — Timer exists but no span

A method with `@Timed` shows up in Actuator, but no span is visible. Does this necessarily mean tracing is broken?

**Answer:** No. `@Timed` focuses on `Timer` metrics. If you need a span, use `@Observed` or the Observation API and configure a tracing handler.

### Exercise 5 — HTTP request already has a timer

A controller has `@Timed` while `http.server.requests` already measures the entire request. Should both be kept?

**Answer:** Only if the additional timer measures a distinct, meaningful business operation. If it measures the exact same full request, it can create a duplicate metric and confuse dashboards.

### Exercise 6 — Percentiles

A team enables percentiles on each application instance and then adds up the P95 values across replicas to calculate the system-wide P95. Is this approach valid?

**Answer:** No. Percentiles cannot simply be summed or averaged to produce an aggregate percentile. Use histogram buckets and appropriate backend aggregation.

## 15. Implementation Checklist

- [ ] `@Timed` is imported from Micrometer.
- [ ] Micrometer registry and AOP/`TimedAspect` are configured for the right version.
- [ ] Only one `TimedAspect` processes the annotation.
- [ ] The method resides in a Spring bean and invocations go through the proxy.
- [ ] Self-invocation is avoided or measured with the manual API.
- [ ] Method visibility/`final` modifiers match the proxy strategy.
- [ ] Metric name and `extraTags` are stable and low-cardinality.
- [ ] Request/user/order IDs, PII, or exception messages are not put into tags.
- [ ] Histograms/percentiles/SLO buckets are enabled intentionally.
- [ ] Async/reactive methods are measured through completion per true semantics.
- [ ] Metrics do not duplicate HTTP/Database observations without a clear goal.
- [ ] `@Observed`/`Observation` is used when both metrics and tracing spans are needed.
- [ ] Tests invoke the Spring bean via proxy and verify `Timer` count/duration.
- [ ] Actuator metrics endpoint is secured.
- [ ] Dashboards/alerts use histogram semantics matching the registry/backend.

**Takeaway:** `@Timed` measures the duration/count of a method when instrumentation can intercept the invocation. In Spring Boot, verify AOP/`TimedAspect`, the proxy path, and method kind; keep metric names/tags stable; and specifically verify async completion and histogram semantics. Use `@Timed` for supplemental business timing, while `Observation`/`@Observed` is better suited when you need to correlate metrics with tracing and other signals.
