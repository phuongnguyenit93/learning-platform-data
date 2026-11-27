# @Counted in Spring Boot

Spring Boot applications often need to know how many times an operation is called. Metrics such as request rate, job execution count, or service method call count help track load and detect abnormal behavior. Micrometer provides the `@Counted` annotation to count how many times a method is executed via AOP instrumentation.

`@Counted` creates a `Counter` for method invocations. Each time the method is intercepted, the counter increments; if the method throws an exception, the invocation still occurred and is typically still counted. The annotation does not automatically define a successful business event, does not measure execution duration, and does not replace HTTP request metrics or tracing spans.

This lesson **“@Counted”** belongs to the **Annotation observability** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module teaches how to set up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; you will learn context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

## 1. What Is @Counted?

`@Counted` is a Micrometer annotation used to count how many times a method is called. The corresponding aspect intercepts the method invocation and updates a `Counter` in `MeterRegistry`.

```java
import io.micrometer.core.annotation.Counted;
import org.springframework.stereotype.Service;

@Service
public class InvoiceService {

    @Counted(value = "invoice.generate.calls",
             description = "Number of invoice generation method calls")
    public Invoice generate(String orderId) {
        // Generate invoice
        return new Invoice(orderId);
    }
}
```

The metric name is `invoice.generate.calls` in the example. The registry may normalize the name according to the backend's naming convention. Each time an invocation is intercepted, the `Counter` increments by one.

A `Counter` is suitable for answering how many times a method was called, whether an operation's frequency is increasing or decreasing, or whether a scheduled task is running as expected. A counter is a cumulative value, typically queried with `rate`/`increase` to observe call counts over a time window.

## 2. Dependencies and Enabling the Counted Aspect

`@Counted` does not work just because the annotation appears in source code. Micrometer annotation support and the aspect must be registered in the application context.

Gradle example:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
    implementation 'io.micrometer:micrometer-core'
}
```

If the BOM/starter already provides the dependency, avoid duplicate declarations or overriding the version. Check the dependency tree to see the managed Micrometer version.

Registering the aspect:

```java
import io.micrometer.core.aop.CountedAspect;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CountedConfiguration {

    @Bean
    CountedAspect countedAspect(MeterRegistry registry) {
        return new CountedAspect(registry);
    }
}
```

When the aspect is present, Spring AOP can intercept annotated methods. Verify the proxy type and method visibility according to the application's AOP configuration. Do not assume Spring Boot registers `CountedAspect` automatically in every setup.

## 3. Annotations Work Through an AOP Proxy

Spring annotation-based AOP is typically proxy-based. Calls from another bean go through the proxy and can be intercepted; internal calls from one method to another within the same object typically bypass the proxy.

```java
@Service
public class ReportService {

    public void runDailyReport() {
        calculateTotals(); // Self-invocation: may bypass the proxy
    }

    @Counted("report.calculate.calls")
    public void calculateTotals() {
        // Calculate report totals
    }
}
```

If `runDailyReport()` calls `calculateTotals()` directly on the same instance, the invocation may not be intercepted by the aspect. A more controllable design is to move the counted operation into a separate Spring bean and invoke it via an injected dependency.

```java
@Service
public class ReportCalculationService {

    @Counted("report.calculate.calls")
    public void calculateTotals() {
        // Calculate report totals
    }
}

@Service
public class ReportService {

    private final ReportCalculationService calculationService;

    public ReportService(ReportCalculationService calculationService) {
        this.calculationService = calculationService;
    }

    public void runDailyReport() {
        calculationService.calculateTotals();
    }
}
```

Do not call methods via `this` expecting them to go through the proxy. Also avoid self-injecting a bean into itself solely to bypass self-invocation when responsibilities can be separated cleanly.

## 4. @Counted Counts Invocations, Not Business Outcomes

Suppose `chargeCard()` is called 100 times: 92 succeed, 5 are declined due to insufficient funds, and 3 time out. The counter `payment.charge.calls` may record 100 invocations; it does not by itself tell you that 92 succeeded.

| Metric | Meaning |
| --- | --- |
| `payment.charge.calls` | Number of times the method was called |
| `payment.charge.success` | Number of successful operations, if recorded separately by the application |
| `payment.charge.failure` | Number of failed operations, if recorded separately by the application |
| `payment.charge.duration` | Execution duration, typically using a Timer |

Do not name an invocation counter `payment.success` if it also increments when the method throws an exception. Metric names must accurately describe their semantics.

If you need to count business outcomes, record a `Counter` at the point where the outcome is determined:

```java
@Service
public class PaymentService {

    private final Counter successfulPayments;

    public PaymentService(MeterRegistry registry) {
        this.successfulPayments = Counter.builder("payment.operations")
                .tag("outcome", "success")
                .register(registry);
    }

    public Receipt charge(Command command) {
        Receipt receipt = performCharge(command);
        successfulPayments.increment();
        return receipt;
    }
}
```

This is an explicit way to record business outcomes. For different outcomes, use a bounded set of tag values such as `success`, `declined`, `error`; do not use exception messages or customer IDs as tags.

## 5. Counting Exceptions and Failures

An invocation can either complete normally or throw an exception. `@Counted` counts method calls according to the aspect's semantics; it does not automatically classify exceptions into business failure categories.

If you need to separate total invocations from error counts, you can combine `@Counted` to count total method calls, a dedicated `Counter` at the exception/error handling boundary to count failures, a `Timer` to measure duration, trace spans to inspect root causes, and logs with trace/span correlation to read exception details.

Example:

```java
@Service
public class ShippingService {

    private final Counter failures;

    public ShippingService(MeterRegistry registry) {
        this.failures = Counter.builder("shipping.create.failures")
                .register(registry);
    }

    public Shipment create(CreateShipmentCommand command) {
        try {
            return callCarrier(command);
        }
        catch (CarrierException ex) {
            failures.increment();
            throw ex;
        }
    }
}
```

Place the counter at the boundary where failure can be accurately determined. If an exception is caught and retried across multiple layers, decide whether to count each attempt or only the final failure; otherwise, the metric can be misinterpreted.

## 6. Tags and Cardinality

`@Counted` supports configuring tags via annotation attributes depending on the Micrometer version. Only use tags with a bounded, stable set of values.

```java
@Counted(
    value = "catalog.lookup.calls",
    extraTags = {"operation", "lookup", "channel", "web"}
)
public Product lookup(String productCode) {
    // Lookup product
}
```

Tags `operation=lookup` and `channel=web` are static values. Do not put method parameters such as `productCode` into a tag. Each product code can create a separate time series, causing cardinality to grow with the number of products.

| Suitable Tag | Unsuitable Tag |
| --- | --- |
| operation=lookup | product.id=SKU-123 |
| channel=web/mobile | user.id |
| result=success/failure | request.id |
| region=ap-southeast-1 | raw URL/query |
| payment.type=card/bank | exception.message |

If you need per-identifier analysis, consider logs/traces with redaction and access control. Do not turn the metric registry into a per-entity data store.

## 7. How Do @Counted and @Timed Differ?

`@Counted` counts invocations. `@Timed` measures duration and also provides the count of timing samples. The two annotations can complement each other, but should not be placed indiscriminately on the same method without understanding how the aspects and registry create meters.

| Criterion | @Counted | @Timed |
| --- | --- | --- |
| Primary goal | Count invocations | Measure duration and time distribution |
| Count | Yes | Yes, number of timing samples |
| Total time | No | Yes |
| Histogram/percentiles | Not the primary goal | Configurable |
| Latency analysis | No | Yes |
| Simple method call counting | Suitable | Usable if duration is also needed |

If you only need the call count, use `@Counted`. If you need latency, use `@Timed` or an appropriate `Observation`/`Timer`. Avoid creating two counters with the same meaning, which leads to double-counting on dashboards.

## 8. @Counted and Observation

Micrometer Observation provides a unified model for metrics and tracing. `@Counted` is specialized instrumentation for method invocations; it does not create distributed spans or propagate trace context by itself.

You can combine `@Counted` for method call counts, `@Observed` or the Observation API for operations needing both metrics and tracing, `@Timed` for latency, and logs within an active trace context for event details.

Do not attach every annotation to every method. Choose the right signals and boundaries to avoid duplicate metrics, unnecessary nested spans, and overhead.

## 9. Counter Lifecycle and Registry

`CountedAspect` uses `MeterRegistry` to register/update the `Counter`. In Spring Boot, prefer the Boot auto-configured `MeterRegistry` so meters flow through the configured registry/exporter.

If you create a separate `MeterRegistry` that is not connected to an exporter, the counter may increment in that registry without appearing in the backend you are viewing.

- Use consistent meter names by domain/operation.
- Keep tag keys stable.
- Do not re-register the same meter with conflicting metadata.
- Do not create a new registry per request.
- Check whether filters exclude this meter.
- Check the exporter/Actuator endpoint separately if the meter does not appear.

## 10. Inspecting the Metric via Actuator

If the Actuator metrics endpoint is exposed and accessible, you can inspect the meter:

```text
GET /actuator/metrics
GET /actuator/metrics/invoice.generate.calls
```

The endpoint may normalize dots or metric names according to naming conventions. Exposure and security configuration must match the environment; do not expose management endpoints publicly just for debugging.

The metrics endpoint response can show the meter name, measurements, and available tag keys/values. Use it to verify that the counter is registered and increments after an invocation.

## 11. Testing @Counted

Integration tests should verify that the aspect actually intercepts the method through the Spring bean proxy.

```java
@SpringBootTest
class InvoiceServiceTests {

    @Autowired
    InvoiceService invoiceService;

    @Autowired
    MeterRegistry registry;

    @Test
    void countsInvocations() {
        Counter counter = registry.find("invoice.generate.calls")
                .counter();

        double before = counter == null ? 0 : counter.count();

        invoiceService.generate("order-1");
        invoiceService.generate("order-2");

        double after = registry.get("invoice.generate.calls")
                .counter()
                .count();

        assertThat(after - before).isEqualTo(2.0);
    }
}
```

This is a structural test example; add the corresponding imports, fixtures, and application configuration. If the counter does not yet exist before invocation, take 0 as the baseline; when tests run in parallel, use distinct meter names/tags or an isolated test registry to avoid interference.

Cases to test: method called through the Spring bean proxy; multiple invocations; exceptions; self-invocation; tags; aspect not registered twice; meter appearing in the right registry. For async/reactive methods, verify the annotation's semantics in the specific version; do not assume method return means task completion.

## 12. Common Limitations

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Annotation does not increment counter | Missing CountedAspect or AOP proxy | Register aspect and check proxy |
| Some calls are not counted | Self-invocation or object outside Spring | Invoke through Spring bean proxy |
| Counter increments twice | Duplicate aspect/bean/interceptor | Check AOP configuration |
| Counter missing in backend | Different registry used or exporter/filter | Check MeterRegistry and filters |
| Cardinality spikes | Tag contains method argument/dynamic value | Switch to allowlist/static tags |
| Incorrect success count | Using invocation counter as business success | Count at the outcome boundary |
| No latency data | Using only @Counted | Use @Timed or Observation |
| Async task measures wrong boundary | Method returns before task completes | Create Observation/Timer for task execution |

## 13. Hands-On Exercise: Counting Method Calls

Perform locally/in tests:

1. Create a Spring Boot service with Actuator, AOP, and Micrometer.
2. Register `CountedAspect` with `MeterRegistry`.
3. Annotate the invoice generation method with `@Counted`.
4. Invoke the method via a bean injected from the Spring context.
5. Verify the counter increments by the exact number of invocations.
6. Trigger an invocation that throws an exception and verify the count per the aspect's semantics.
7. Add static tags such as `operation` and `channel`.
8. Try self-invocation to observe proxy limitations.
9. Compare `@Counted` with `@Timed` when latency is needed.
10. Verify the metric appears in Actuator and the exporter backend.
11. Verify there are no dynamic IDs or sensitive data in tags.

Expected outcome: method invocations are counted accurately, metric names/tags are stable, business success/failure are represented by separate metrics if needed, and there are no duplicate counters.

## 14. Self-Check Questions

1. Does `@Counted` measure method invocations or business success?
2. Which component intercepts the annotated method?
3. Why doesn't the annotation work just by adding it to the source code?
4. How does self-invocation affect the Spring AOP proxy?
5. Is a method that throws an exception still an invocation?
6. When should you record a separate business success counter?
7. Why shouldn't method arguments be put into extra tags?
8. How does `@Counted` differ from `@Timed`?
9. Does `@Counted` automatically create a distributed span?
10. Why should you use the `MeterRegistry` managed by Spring Boot?
11. How do you verify the counter via Actuator?
12. What test proves the aspect actually intercepts the bean call?
13. Why is counting every retry attempt different from counting the final business outcome?
14. How can an async method have a different measurement boundary than task completion?

## References

- [Micrometer — @Counted annotation](https://docs.micrometer.io/micrometer/reference/concepts/counters.html): Counter semantics and annotation-based counting.
- [Micrometer — CountedAspect Javadoc](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/aop/CountedAspect.html): AOP aspect for @Counted.
- [Spring Boot — AOP](https://docs.spring.io/spring-boot/reference/features/aop.html): AOP auto-configuration and proxy behavior.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): MeterRegistry, Actuator metrics, and registry integration.
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): Timer semantics and differences from Counter.
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation.html): Observation API for metrics/tracing correlation.

## Conclusion

**`@Counted` is a simple way to count how many times a Spring bean method is called via AOP instrumentation.** You need to register `CountedAspect`, use the application-managed `MeterRegistry`, and ensure calls go through the proxy. The counter reflects invocations; it does not automatically distinguish business success/failure and does not measure latency.

Name metrics according to their semantics, use only low-cardinality tags, and record business outcomes at the appropriate boundary. When duration or distributed tracing is needed, combine `Timer`/`Observation` rather than expecting `@Counted` to provide all signals. Test proxies, exceptions, self-invocation, and exporters to ensure the numbers accurately reflect application behavior.
