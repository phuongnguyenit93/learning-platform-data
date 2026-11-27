# Annotations on Service Methods in Spring Boot

In a Spring Boot application, a service method typically represents a business operation such as creating an order, calculating shipping fees, or confirming a payment. When a method runs slowly or raises an error, HTTP server metrics alone are often insufficient to pinpoint which business step consumed the time. Annotation observability lets you attach measurement metadata and lifecycle tracking to methods, helping monitor duration, outcomes, metrics, and distributed traces without writing boilerplate around every call.

In the `SPRING_BOOT_OBSERVABILITY` module, annotation observability connects Micrometer Observation, metrics, logs, and distributed tracing. This lesson belongs to the Annotation observability chapter and focuses on annotations on service methods: how to use `@Observed`, auto-configuration/AOP prerequisites, how annotations create `Observation`s, naming and cardinality, self-invocation, async/reactive boundaries, testing, and troubleshooting.

## Learning Objectives

1. Explain the role of annotations on service methods in observability.
2. Distinguish `@Observed` from `@Transactional`, `@Async`, and business-control annotations.
3. Configure Spring Boot/Micrometer so annotations create `Observation`s.
4. Understand AOP proxies, method visibility, and self-invocation.
5. Choose safe observation names and low/high-cardinality key-values.
6. Link service `Observation`s with HTTP/JDBC/client spans.
7. Understand annotation behavior in async, reactive, and exception paths.
8. Test metrics, tracing, tags, and proxy behavior.

## 1. Why Instrument Service Methods?

An HTTP request typically flows through controllers, services, and repositories. The server span reports the total request processing time, but does not necessarily show which service operation took the bulk of that time. Observations on service methods establish meaningful business boundaries in traces.

~~~text
HTTP server span: POST /orders
  └─ Observation: orders.create
       ├─ Observation: pricing.calculate
       ├─ HTTP client span: inventory.reserve
       └─ JDBC span: INSERT orders
~~~

A service method can represent a stable use case. The trace viewer will display the operation name, duration, errors, and child spans created while the method executes.

### 1.1. An Annotation Does Not Automatically Mean Tracing

An annotation only generates telemetry when the runtime has a mechanism to process it—typically a Spring AOP interceptor/aspect and Observation infrastructure. If dependencies, auto-configuration, or proxy application are missing, the method still runs but no `Observation` is created.

You must check all of the following:
- The annotation is present on the method.
- AOP/Observation integration is configured.
- `ObservationRegistry` and handlers are in the application context.
- Tracing bridge/sampler/exporter are configured if spans are wanted.
- `MeterRegistry` is configured if metrics are wanted.

### 1.2. Observation Is an Abstraction

Micrometer Observation provides the lifecycle and context for an operation. Observation handlers can emit metrics and tracing. Annotations help declare start/end points; they do not replace the registry, handlers, tracer, meter registry, or exporter.

## 2. @Observed on Service Methods

Micrometer provides the `@Observed` annotation to mark a method or type to be observed. Example:

~~~java
import io.micrometer.observation.annotation.Observed;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    @Observed(name = "orders.create")
    public OrderResult createOrder(CreateOrderCommand command) {
        validate(command);
        reserveInventory(command);
        return persist(command);
    }

    private void validate(CreateOrderCommand command) {
        // Validate business rules.
    }

    private void reserveInventory(CreateOrderCommand command) {
        // Call inventory service.
    }

    private OrderResult persist(CreateOrderCommand command) {
        // Persist order.
        return new OrderResult("accepted");
    }
}
~~~

When the method is called through the Spring proxy and annotation infrastructure is enabled, an `Observation` named `orders.create` wraps the method invocation. Depending on handlers, the operation can produce timers/metrics and spans.

### 2.1. Configuring Annotation Support

In Spring Boot, use the dependencies and auto-configuration matching your version. Baseline dependency example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-observation'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

In a Boot application, several Micrometer dependencies are pulled in via Actuator/BOM. Do not add explicit versions if the Boot BOM already manages them. Annotation support requires the corresponding AOP module, typically `spring-boot-starter-aop` in proxy-based setups.

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
~~~

Check your specific Spring Boot/Micrometer version: property names for enabling annotations and auto-configuration can differ between releases. Do not guess property names; verify against the documentation for the version in use and test with a real method.

### 2.2. Enabling the Observed Aspect

Micrometer/Spring Boot provides configuration to enable the aspect handling `@Observed`. In Spring Boot versions that provide the corresponding property, configuration is typically placed under `management.observations.annotations`. Illustrative example:

~~~yaml
management:
  observations:
    annotations:
      enabled: true
~~~

This property depends on the Boot version. Check configuration metadata/reference docs for your exact version before applying it. If the application manually configures an `ObservationAspect`, avoid registering both the auto-configured aspect and a custom aspect simultaneously.

### 2.3. Stable Observation Names

Observation names should reflect a use case or operation:
- `orders.create`
- `payment.authorize`
- `inventory.reserve`
- `pricing.calculate`

Do not attach dynamic data to names like `orders.create.12345` or `payment.authorize.customer-9`. Dynamic names cause high cardinality and make dashboards/trace searches hard to aggregate.

## 3. How Does an Annotation Create an Observation?

~~~mermaid
sequenceDiagram
    participant Caller
    participant Proxy as Spring AOP proxy
    participant Aspect as Observed aspect
    participant Method as Service method
    participant Handler as Observation handlers
    Caller->>Proxy: createOrder(command)
    Proxy->>Aspect: Intercept invocation
    Aspect->>Handler: Start Observation
    Aspect->>Method: Invoke target method
    Method-->>Aspect: Result or exception
    Aspect->>Handler: Stop Observation / record error
    Aspect-->>Caller: Return result or rethrow
~~~

General flow:
1. The caller invokes the bean through the Spring proxy.
2. The aspect recognizes the annotation and creates an `Observation`.
3. The `Observation` starts before the target method runs.
4. The method executes within the `Observation` scope.
5. The result or exception is recorded.
6. The `Observation` stops after the invocation.
7. Handlers update metrics/tracing according to configuration.

Specific names and key-values are determined by the annotation, convention, and implementation. Observe actual telemetry rather than assuming every version emits the exact same set of tags.

## 4. AOP Proxy and Important Limitations

Proxy-based annotations only work when calls go through the proxy. This requirement is easy to overlook.

### 4.1. Self-Invocation

~~~java
@Service
public class InvoiceService {

    public void closePeriod() {
        calculateTotals(); // Internal call on this, bypasses proxy.
    }

    @Observed(name = "invoice.calculate-totals")
    public void calculateTotals() {
        // Business calculation.
    }
}
~~~

In proxy-based AOP, calling `calculateTotals` from `closePeriod` invokes the target object directly without passing through the proxy. The aspect may not fire. The usual fix is to move the instrumented method into another Spring bean and invoke it across the bean boundary. Avoid injecting a bean into itself solely to bypass self-invocation, as that easily creates dependency cycles and makes the design harder to follow.

### 4.2. Method Visibility and Proxy Type

Whether a method can be intercepted depends on the Spring AOP proxy strategy, interface/class proxying, `final` classes/methods, and framework version. With class-based proxies, `final` methods cannot be overridden to intercept; `private` methods are not normal join points for Spring proxy AOP.

Placing annotations on `public` service methods invoked from other beans is the most predictable approach. Check the proxy configuration and actual method when an annotation emits no telemetry.

### 4.3. The Bean Must Be Managed by Spring

If you instantiate a service with `new OrderService()` instead of injecting the bean from `ApplicationContext`, the Spring proxy/aspect does not wrap that instance. The annotation is not processed. Services needing instrumentation must be created and managed by the Spring container.

## 5. Observation Metadata and Cardinality

An `Observation` can carry low-cardinality and high-cardinality key-values. The two groups serve different handlers.

| Type | Purpose | Example |
| --- | --- | --- |
| Low-cardinality | Metrics and tracing | `channel=web`, `operation=checkout` |
| High-cardinality | Detailed trace metadata | approved `order.reference` |
| Should not collect | Secrets/PII or unnecessary dynamic values | token, email, raw payload |

Annotations may support declaring metadata via attributes provided by the version; check exact syntax against your Micrometer version. Do not assume every annotation version has the same attributes.

### 5.1. Low-Cardinality

Low-cardinality tags must have a small, bounded set of values:
- `payment.method`: `card`, `bank-transfer`, `wallet`;
- `order.channel`: `web`, `mobile`, `partner`;
- `operation.result`: `accepted`, `rejected`.

Do not use customer ID, order ID, request ID, email, or raw URL as metric tags. Values growing with traffic cause time series explosions.

### 5.2. High-Cardinality

High-cardinality metadata can be useful in traces to investigate a specific operation, yet it still increases payload/indexing costs and can expose information. Add only genuinely needed fields, cap lengths, and undergo privacy review. Do not dump all method arguments into the `Observation` context.

### 5.3. Do Not Record Payloads Automatically

Method arguments can contain request bodies, payment details, or personal data. Avoid annotations/aspects that automatically serialize every argument/result into tags. Select a few normalized, permitted metadata fields.

## 6. Metrics and Tracing from the Same Annotation

When `Observation` has both meter and tracing handlers:
- Metrics can aggregate counts/durations by operation and low-cardinality tags;
- The tracing handler can create a span for each recorded invocation;
- Exceptions/outcomes can be recorded per convention;
- The current trace context can act as parent for the service span.

Sampling applies to traces and should not be used to decide whether request metrics are recorded. A method can be measured in metrics even when the request's trace is dropped by the sampler.

### 6.1. Metrics Query Example

Actual meter names depend on the `Observation` convention and registry. If an application observation's timer is exported as `application.task` or `orders.create` per naming policy, check `/actuator/metrics` for the real meter name before building dashboards.

General PromQL example for a timer exported as a histogram:

~~~promql
sum by (operation) (
  rate(application_observation_seconds_count[5m])
)
~~~

p95 latency if histograms and the corresponding label are enabled:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, operation) (
    rate(application_observation_seconds_bucket[5m])
  )
)
~~~

These are illustrative queries; do not assume default meter names or `operation` labels across all versions. Inspect the scrape output and adjust accordingly.

### 6.2. Do Not Double Metrics with Nested Annotations

If service method A calls service method B and both are instrumented, metrics record two operations. That may be intentional to break down time. However, do not attach the same `Observation` in an aspect, a wrapper, and the method body if they describe the same boundary.

## 7. Exceptions and Outcomes

An `Observation` normally stops when the method finishes, whether it succeeds or throws an exception. Exceptions can be recorded on the `Observation` and tracing span per the handler. Verify the semantics:
- Exception is thrown out of the method;
- Exception is caught and converted into a business result;
- Whether validation failure is error telemetry or a business outcome;
- Exception occurs in a child operation but is handled in the parent.

If a method catches an exception and returns a fallback, the aspect may only see the method finishing normally. When failures must be reflected, record the outcome explicitly via a convention/custom `Observation` rather than expecting the aspect to infer a handled exception.

~~~java
@Observed(name = "payment.authorize")
public PaymentResult authorize(PaymentCommand command) {
    try {
        return gateway.authorize(command);
    } catch (GatewayUnavailableException ex) {
        log.warn("Payment gateway unavailable");
        throw ex;
    }
}
~~~

Do not record exception messages containing tokens, account details, or sensitive data into tags.

## 8. Combining @Observed with @Transactional and @Async

Different annotations serve different purposes:
- `@Observed`: creates an `Observation` for a method invocation.
- `@Transactional`: manages the transaction boundary.
- `@Async`: offloads invocation to an executor.

They can be combined, but advisor/interceptor ordering affects scope. For example, an `Observation` outside the transaction may include transaction begin/commit time; an `Observation` inside may only measure the method body depending on advisor ordering.

~~~java
@Service
public class SettlementService {

    @Observed(name = "settlement.execute")
    @Transactional
    public void settle(SettlementCommand command) {
        // Update ledger and settlement state.
    }
}
~~~

Do not infer transaction duration by default from a method `Observation` without checking advisor order and transaction completion behavior. If commit happens when the transaction interceptor finishes after the method body, the observation boundary may or may not include the commit depending on advisor order.

### 8.1. @Async

~~~java
@Async("applicationTaskExecutor")
@Observed(name = "report.generate")
public CompletableFuture<Report> generateReport() {
    return CompletableFuture.completedFuture(buildReport());
}
~~~

This combination depends on the proxy chain and how the framework instruments asynchronous return values. Verify whether the span covers actual execution or only the time to create the `Future`. Use executor context propagation to keep tracing/MDC accurate on worker threads.

### 8.2. Reactive Return Types

With `Mono`/`Flux`, a method may return the publisher before the pipeline actually runs. If the `Observation` aspect only wraps publisher creation time, duration will not reflect subscription/terminal signal time. Use appropriate reactive instrumentation/context propagation and test the lifecycle through complete/error/cancel. Do not apply synchronous-method assumptions to reactive pipelines.

## 9. Annotations vs. Custom Observation

`@Observed` is suitable when marking a stable operation. If you need controlled dynamic metadata, business-specific events, or complex lifecycles, the custom Observation API can be clearer.

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class PricingService {
    private final ObservationRegistry registry;

    public PricingService(ObservationRegistry registry) {
        this.registry = registry;
    }

    public Price calculate(PriceRequest request) {
        return Observation.createNotStarted("pricing.calculate", registry)
                .lowCardinalityKeyValue("pricing.channel", request.channel())
                .observe(() -> calculateInternal(request));
    }

    private Price calculateInternal(PriceRequest request) {
        // Calculate price.
        return new Price(100);
    }
}
~~~

This example assumes `channel` is validated into a bounded set before being passed as a low-cardinality tag. If `channel` comes directly from a caller, normalize/allow-list it first.

### 9.1. Custom Aspects

Only write a custom aspect when behavior is needed that `@Observed`/Observation API cannot satisfy. A custom aspect must:
- Define an explicit method pointcut;
- Avoid intercepting the same method twice alongside `ObservedAspect`;
- Preserve return values/exceptions;
- Close the `Observation` on all branches;
- Handle checked exceptions;
- Not serialize arguments/results by default;
- Test proxy ordering and async behavior.

If you only need an `Observation` around a method, prefer the built-in annotation/aspect over inventing a custom framework.

## 10. Testing Annotation Observability

Test annotation activation, AOP proxies, `Observation` lifecycle, metrics/tracing handlers, and exception behavior separately.

### 10.1. Testing ObservationRegistry

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.tck.TestObservationRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class ServiceObservationTest {
    @Test
    void recordsObservationLifecycle() {
        TestObservationRegistry registry = TestObservationRegistry.create();

        Observation.createNotStarted("orders.create", registry)
                .lowCardinalityKeyValue("order.channel", "web")
                .observe(() -> { });

        assertThat(registry.getCompletedObservationContexts()).hasSize(1);
    }
}
~~~

This test checks the Observation API directly; it does not prove annotation AOP is enabled.

### 10.2. Integration Testing Through the Spring Proxy

Create a `@SpringBootTest` with the service bean injected via `ApplicationContext`, invoke the annotated method, and use a test Observation handler/registry to verify the observation starts and stops. Call the method through the bean proxy, not a manually `new`'d instance.

Also test self-invocation: a public method calling an annotated method internally. Verify behavior matches your active proxy strategy; move the method to a separate bean if interception is needed.

### 10.3. Testing Exceptions

Make the method throw a controlled exception. Assert that the exception still propagates per contract, the `Observation` is stopped, and the error is recorded per handler. After the exception, invoke another method and verify the current observation/span context has been restored.

### 10.4. Testing Metrics and Tracing Independently

- `MeterRegistry`: verify timer/count and low-cardinality tags.
- Tracing test exporter: verify span name, parent relationship, and error status.
- Log appender: verify `traceId`/`spanId` in MDC if logging correlation is enabled.
- Sampling tests: do not treat a missing span as proof the annotation failed to run; metrics/`Observation` may still be active.

## 11. Troubleshooting Annotations on Service Methods

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| @Observed creates no telemetry | Aspect/annotation support not enabled | Check dependencies, property, and auto-configuration version |
| Only metrics exist, no spans | Missing tracing handler/bridge/sampler/exporter | Check tracing pipeline |
| Internal method not instrumented | Self-invocation bypasses proxy | Move method to a separate bean |
| Object created with `new` has no Observation | Bypasses Spring proxy | Inject bean from ApplicationContext |
| Final/private method not intercepted | Proxy strategy/visibility limitation | Use public non-final method through proxy |
| Observation name differs from expected | Different convention/name config | Check annotation and completed context |
| Tag unexpectedly appears in metrics | Key-value declared as low-cardinality | Move/remove metadata, review convention |
| Cardinality grows per request | Tag/name contains ID or dynamic URL | Use stable names and allow-list |
| Exception not recorded | Method catches and returns fallback | Record outcome/error explicitly |
| @Async span too short | Measures only method creating Future | Check async instrumentation/lifecycle |
| Mono/Flux duration too short | Measures publisher assembly instead of subscription | Use reactive observation integration |
| Two identical spans | Custom aspect and ObservedAspect both intercept | Choose one instrumentation owner |
| Wrong context after method | Scope not closed/restored | Check `finally` and handler lifecycle |

### 11.1. Investigation Workflow

1. Verify the service is a Spring bean.
2. Check whether callers invoke via proxy or self-invocation.
3. Check annotation support and `ObservationRegistry`.
4. Inspect the completed `Observation` context.
5. Check `MeterRegistry` and Tracing handlers independently.
6. Check sampler/exporter if spans were created but are missing in the backend.
7. Check tags, naming, and cardinality.
8. Test exceptions, async/reactive completion, and context restoration.

## 12. Production Checklist

| Criterion | Evidence |
| --- | --- |
| Annotation support enabled | Version/property/AOP config verified |
| Service bean via proxy | Integration test calls through Spring context |
| Stable operation name | Contains no dynamic IDs |
| Low-cardinality metrics | Tags are bounded value sets |
| Tracing bridge working | Span appears when sampled |
| Correct parent context | Service span is proper child/link |
| Clear exception semantics | Errors/outcomes are recorded |
| Self-invocation handled | Method boundary placed in appropriate bean |
| Async/reactive tested | Duration covers execution lifecycle |
| No duplicate instrumentation | One aspect per method boundary |
| Privacy controlled | No arguments/secrets serialized |
| Scope restored | No context leakage after invocation |

## 13. Hands-On Exercise: Instrumenting Service Methods in order-service

**Context:** `order-service` has service methods `createOrder`, `calculatePricing`, and `reserveInventory`. Operations needs to know which operation is slow, metrics grouped by operation, and traces linked to the HTTP request.

**Tasks:**

1. Enable Actuator and AOP/Observed annotation support per your Spring Boot version.
2. Annotate `createOrder` with `@Observed` using a stable name.
3. Invoke the service through the Spring bean proxy and verify an `Observation` is created.
4. Create a nested operation `calculatePricing` and inspect the span hierarchy.
5. Add a low-cardinality `channel` tag with an allow-list.
6. Keep `orderId`/`customerId`/request bodies out of metric tags.
7. Trigger an exception path and verify the error is recorded while the exception still propagates.
8. Combine with `@Transactional` and determine whether the `Observation` includes transaction completion per advisor order.
9. Combine with `@Async` or reactive return types if used; verify duration through task completion/terminal signal.
10. Test self-invocation and move the boundary to a separate bean to verify proxy behavior.
11. Verify there are no duplicate spans when a custom aspect and `@Observed` coexist.
12. Write a runbook for missing observations, missing spans, growing cardinality, and incorrect async span durations.

**Expected Result:** service methods have clear `Observation`s/traces, metrics with safe tags, proxy/exception/async tests, and troubleshooting guidance.

## 14. Key Takeaways

Annotations on service methods help declare business boundaries to observe. `@Observed` can create a Micrometer `Observation` when annotation support and Spring AOP proxies are configured properly. Observation handlers determine which metrics/tracing signals are emitted; tracing bridges/exporters do not replace the annotation aspect on their own.

Invoke methods through Spring bean proxies, avoiding self-invocation and manually instantiated objects. Use stable operation names and low-cardinality tags with bounded value sets, and never record raw arguments/secrets into telemetry. With `@Transactional`, `@Async`, and reactive return types, verify interceptor ordering and actual lifecycles. Test proxy behavior, `Observation` context, metrics, spans, exceptions, and context restoration. Metrics show trends, spans show relationships between operations, and logs capture events tied to correlation IDs.

**References:**
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot — AOP](https://docs.spring.io/spring-boot/reference/features/aop.html)
- [Micrometer Observation — Annotations](https://docs.micrometer.io/micrometer/reference/observation/instrumenting.html)
- [Micrometer Observation — Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/)
- [Spring Framework — AOP Proxies](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
