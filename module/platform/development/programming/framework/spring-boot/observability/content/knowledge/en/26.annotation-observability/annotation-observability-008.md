# Spring Boot Starter AspectJ

A Spring Boot service has an order-processing method whose execution duration, call count, and outcome need to be measured to investigate latency or errors. You could manually create an `Observation` around each method, but repetitive boilerplate can easily lead teams to record things inconsistently. Micrometer provides annotations such as `@Observed`, `@Timed`, `@Counted`, and `@NewSpan`; Spring Boot can enable AOP to intercept annotated methods and turn them into `Observation`s, metrics, or tracing spans.

This **Spring Boot starter aspectj** lesson belongs to the **Annotation observability** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module covers setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; understanding context propagation, tags/cardinality, exporters, sampling, and correlating signals to investigate errors, latency, and application behavior in production environments.

> **Core takeaway:** Annotation-based observability requires the AspectJ weaver dependency matching the Spring Boot version and the property `management.observations.annotations.enabled=true`. Spring Boot 4 renamed the starter from `spring-boot-starter-aop` to `spring-boot-starter-aspectj`; Boot 3.x still uses the older AOP starter. The starter enables Spring AOP proxies/AspectJ annotation style for aspects; it does not mean all code has been compile-time or load-time woven with AspectJ.

## 1. Learning Objectives

After this lesson, you can:
1. Explain the role of the AspectJ starter in annotation-based observability.
2. Choose the right dependency for Spring Boot 3.x or 4.x.
3. Enable annotation scanning with `management.observations.annotations.enabled`.
4. Distinguish Spring AOP proxies from AspectJ compile-time/load-time weaving.
5. Use `@Observed`, `@Timed`, `@Counted`, `@MeterTag`, and `@NewSpan` for their intended purposes.
6. Understand how annotation interceptors create `Observation`s, metrics, and tracing spans.
7. Recognize self-invocation, method visibility, and proxy limitations.
8. Avoid duplicate observations when a method is already auto-instrumented.
9. Control low-cardinality tags and keep sensitive data out of metrics.
10. Test annotation interception and troubleshoot when annotations do not work.

## 2. What Does the AspectJ Starter Solve?

Micrometer Observation is a unified API for instrumenting operations. `ObservationRegistry` coordinates handlers; depending on configured handlers, an `Observation` can produce Micrometer metrics and/or tracing spans.

Annotation observability lets you declare instrumentation close to a method/class:
- `@Observed`: creates an `Observation` around an operation.
- `@Timed`: records execution duration using a `Timer`.
- `@Counted`: counts how many times a method is called.
- `@MeterTag`: adds a tag to a meter based on a method parameter when the corresponding annotation support is enabled.
- `@NewSpan`: creates a new span via Micrometer Tracing.

Annotations do not execute just because their classes are imported. The application needs an aspect/interceptor scanning annotations and the necessary runtime dependencies. The Spring Boot AspectJ starter puts the AspectJ weaver on the classpath and its auto-configuration supports the proxy infrastructure; Micrometer annotation scanning must be enabled explicitly.

~~~mermaid
flowchart TD
    A["Annotated Spring bean method"] --> B["Spring AOP proxy"]
    B --> C["Micrometer annotation aspect"]
    C --> D["Observation / Timer / Span"]
    D --> E["ObservationRegistry"]
    E --> F["MeterObservationHandler"]
    E --> G["TracingObservationHandler"]
    F --> H["MeterRegistry"]
    G --> I["Tracer / exporter"]
~~~

The annotation only declares the intent to instrument. A proxy/aspect must intercept the invocation; `ObservationRegistry` and handlers then decide which signals are created and exported.

## 3. Choosing the Right Starter by Spring Boot Version

The starter name changed in major version 4:

| Spring Boot version | Dependency |
|---|---|
| 3.x | `org.springframework.boot:spring-boot-starter-aop` |
| 4.x | `org.springframework.boot:spring-boot-starter-aspectj` |

Spring Boot 4 renamed the AOP starter to the AspectJ starter during modularization. Use Spring Boot's BOM/dependency management to select compatible versions; do not pin the AspectJ weaver version manually without a specific reason.

### 3.1 Gradle with Spring Boot 3.x

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
~~~

### 3.2 Gradle with Spring Boot 4.x

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-aspectj'
}
~~~

If using Maven, declare the corresponding starter in dependencies. Do not add both starters at the same time just to be safe; pick the right artifact for your major version.

### 3.3 Why Is Actuator Needed?

The AspectJ starter provides the AOP/AspectJ infrastructure. Actuator brings Spring Boot's observability/metrics auto-configuration into the application. Having aspect support alone without `MeterRegistry`/`ObservationRegistry` and appropriate handlers will not automatically produce complete backend telemetry from annotations.

## 4. Enabling Annotation Scanning

Configure in `application.yml`:

~~~yaml
management:
  observations:
    annotations:
      enabled: true
~~~

This property enables scanning for Micrometer observability annotations such as `@Observed`, `@Timed`, `@Counted`, `@MeterTag`, and `@NewSpan`. According to Spring Boot documentation, annotation support is not enabled by default; it must be enabled explicitly.

To produce metrics and traces:
- Have an `ObservationRegistry` in the application context.
- Have a `MeterRegistry` and meter observation handler for metrics.
- Have a Micrometer Tracing bridge/handler and exporter if spans should be sent out.
- Have annotation aspects/interceptors on the classpath and a proxy able to intercept the method.

An annotation can be intercepted yet lack an exporter. Therefore, verify annotation scanning, `Observation` creation, handlers, registry/tracer, and the export pipeline separately.

## 5. Spring AOP Proxy vs. AspectJ Weaving

| Mechanism | How It Works | Scope |
|---|---|---|
| Spring AOP proxy | Creates a proxy for a Spring bean and intercepts method calls going through the proxy | Join points supported by Spring AOP |
| AspectJ compile-time weaving | Compiler weaves aspects into bytecode at build time | Join points per the AspectJ language |
| AspectJ load-time weaving | Agent/classloader weaves bytecode when classes are loaded | Join points per the AspectJ language |

Spring Boot auto-configuration typically uses Spring AOP proxies. AspectJ annotation style uses `@Aspect`/`@Around` syntax, yet aspects can still run on the Spring AOP proxy runtime. Having AspectJ weaver on the classpath does not by itself prove that compile-time or load-time weaving is active.

Full AspectJ weaving is not required merely to use Micrometer annotation observability in Spring Boot. Use the documented starter, enable the property, and let Spring manage proxies/aspects.

### 5.1 CGLIB and JDK Proxies

Spring AOP can use CGLIB class-based proxies or JDK interface-based proxies. Spring Boot defaults to CGLIB; JDK proxies can be selected via `spring.aop.proxy-target-class=false`.

With JDK proxies, invocations must go through the interface proxy. With class-based proxies, classes/methods must be proxyable under subclass constraints. `final` classes/methods cannot be overridden for interception under subclass proxying. Check the actual proxy type when annotations fail to run.

## 6. Using @Observed for Business Operations

`@Observed` is suitable for instrumenting operationally meaningful actions, such as reserving inventory or submitting an order.

~~~java
import io.micrometer.observation.annotation.Observed;
import org.springframework.stereotype.Service;

@Service
class OrderApplicationService {

    @Observed(name = "order.submit", contextualName = "submit-order")
    public OrderResult submit(CreateOrder command) {
        return createOrder(command);
    }

    private OrderResult createOrder(CreateOrder command) {
        // Business logic simplified.
        return new OrderResult();
    }
}
~~~

When the method is called through the Spring proxy, the annotation aspect can create an `Observation` with the configured `name` and contextual name. The `Observation` is converted into metrics/traces depending on handlers.

The `Observation` name should be stable and describe the operation. Do not put order IDs, customer emails, raw URLs, or request data into the `Observation` name.

### 6.1 @Observed Does Not Automatically Create Every Metric

`@Observed` creates an `Observation`; handlers determine metrics/spans. Measuring duration requires a meter observation handler. Spans require a tracing handler/bridge. Exporting requires a registry/exporter.

Do not assume adding the annotation automatically sends data to Prometheus or OTLP if no exporter is configured.

## 7. Using @Timed and @Counted

`@Timed` records method execution duration using a Micrometer `Timer`. `@Counted` records how many times the method is called using a `Counter`.

~~~java
import io.micrometer.core.annotation.Counted;
import io.micrometer.core.annotation.Timed;
import org.springframework.stereotype.Service;

@Service
class ReportService {

    @Timed(value = "report.generate.duration", description = "Time to generate report")
    @Counted(value = "report.generate.calls", description = "Report generation calls")
    public Report generate(String reportType) {
        return new Report();
    }
}
~~~

Meter names should be stable. Additional tags need bounded values. If `@Observed` and `@Timed` are both placed on a method, multiple instruments/observations may be created; do so only intentionally and check for duplicate measurements.

Choose the annotation by intent:
- `@Observed` when you want an operation `Observation` that can produce multiple signals.
- `@Timed` when the goal is measuring duration.
- `@Counted` when the goal is counting invocations/events.
- Custom `Observation` when you need context, low/high-cardinality key-values, or fine-grained lifecycle control.

Do not attach every annotation to every method. Over-instrumentation increases noise, cost, and duplicate signals.

## 8. @MeterTag and Controlling Cardinality

`@MeterTag` lets you create a meter tag from a method parameter under annotation-based metrics support. Values must be normalized and have bounded cardinality.

~~~java
import io.micrometer.core.annotation.MeterTag;
import io.micrometer.core.annotation.Timed;
import org.springframework.stereotype.Service;

@Service
class CatalogService {

    @Timed(value = "catalog.lookup")
    public Item find(@MeterTag(key = "channel") String channel) {
        return lookupItem();
    }

    private Item lookupItem() {
        return new Item();
    }
}
~~~

This snippet illustrates annotation usage; you need a resolver/configuration matching your Micrometer version to map the parameter to a tag value. Only use an allow-listed set of channels such as `web`, `mobile`, `partner`.

Do not tag `orderId`/`customerId`/`userId`, email, phone, account number, token, session cookie, SQL statement, exception message, or raw search query. If a value is outside the allowed set, map it to `other`/`unknown` instead of generating a new series.

## 9. @NewSpan in Tracing

`@NewSpan` belongs to Micrometer Tracing and creates a new span around a method when tracing annotation support is configured. It differs from `@Observed`: `@Observed` creates an `Observation`, whereas `@NewSpan` asks the tracing bridge to create a span via the tracing API.

~~~java
import io.micrometer.tracing.annotation.NewSpan;
import org.springframework.stereotype.Service;

@Service
class PaymentGatewayService {

    @NewSpan("payment.authorize")
    public AuthorizationResult authorize(PaymentCommand command) {
        return new AuthorizationResult();
    }
}
~~~

The new span normally attaches to the current trace context via the tracing integration. If the method does not run inside a trace context, the span may become a root span or start a new trace depending on the active context.

Do not record card numbers, CVVs, tokens, or raw provider responses into span attributes. Use normalized operation names, outcomes, and error categories.

## 10. Proxy Limitation: Self-Invocation

Spring AOP proxies only intercept invocations passing through the proxy. If a method in the same bean calls another method directly on `this`, the internal call bypasses the proxy.

~~~java
@Service
class BillingService {

    public void checkout() {
        charge(); // self-invocation: typically bypasses proxy advice
    }

    @Observed(name = "billing.charge")
    public void charge() {
        // Charge payment.
    }
}
~~~

In this example, `checkout` calls `charge` on the same target object; the annotation on `charge` may not be intercepted.

How to fix:
- Move the annotated operation to another Spring bean and inject that bean.
- Invoke the method through the bean proxy from the caller.
- If semantics must not depend on a proxy, create a manual `Observation` around the operation.

## 11. Method Visibility and Final Methods

With proxy-based AOP:
- `private` methods cannot be called externally through a proxy.
- `final` methods cannot be overridden in a CGLIB subclass proxy.
- `final` classes cannot be CGLIB-subclassed.
- JDK dynamic proxies intercept methods exposed via an interface.
- Invocations must go through the Spring-managed proxy bean.

Placing annotations on `public` service methods is usually clearest. If an annotation is not applied, verify whether the class is a Spring bean, whether the bean is injected via proxy, and whether the method is called through that proxy.

True AspectJ weaving has broader join-point coverage, but requires configuring the compiler/weaver separately; the starter alone does not enable full-program weaving.

## 12. Async and Reactive Boundaries

Annotation method observation measures invocations via the interceptor mechanism. For methods returning `CompletableFuture`, `Mono`, or `Flux`, verify whether the observation/span lifecycle covers asynchronous execution or only creation of the publisher/future, depending on the annotation aspect and integration version.

Do not assume method return time equals task completion time. For asynchronous work:
- Measure submit-to-start separately if queue wait is needed.
- Measure start-to-terminal completion/error/cancel for processing duration.
- Propagate `Observation`/trace context across executors/reactive contexts.
- Use native framework integrations where available rather than creating overlapping custom aspects.

Reactive subscription is normally when execution begins; a publisher may be subscribed to multiple times. Instrumentation must reflect each subscription/operation according to desired semantics.

## 13. Avoiding Duplicate Observations

Spring Boot and the Spring ecosystem already auto-instrument many boundaries such as Spring MVC, `RestTemplate`, Spring Data, and messaging integrations. Adding `@Observed` onto an already auto-instrumented method can create nested observations/spans or double-counted metrics.

Spring Boot documentation warns that annotating already auto-instrumented methods/classes can produce duplicate observations. Options include:
- Remove the annotation from methods that already have automatic instrumentation.
- Disable the corresponding automatic instrumentation via property if appropriate.
- Use an `ObservationPredicate` to filter observations by name/context.
- Annotate only business boundaries that are not yet instrumented.

Example predicate filtering out an observation name:

~~~java
import io.micrometer.observation.ObservationPredicate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ObservationFilterConfiguration {

    @Bean
    ObservationPredicate ignoreDuplicateOperation() {
        return (name, context) -> !name.equals("duplicate.operation");
    }
}
~~~

This example only illustrates a predicate; do not filter with broad strings that drop useful observations. Before disabling instrumentation, check the impact on metrics/traces and dashboards.

## 14. Testing Annotation Observability

Tests must verify that the proxy/aspect intercepted the method and signals were created. Do not merely assert that the method returns the right business result.

~~~java
@SpringBootTest
class ObservedServiceTest {

    @Autowired
    OrderApplicationService service;

    @Autowired
    MeterRegistry meterRegistry;

    @Test
    void recordsObservedOperation() {
        service.submit(validCommand());

        Timer timer = meterRegistry.find("order.submit").timer();
        assertThat(timer).isNotNull();
        assertThat(timer.count()).isGreaterThan(0);
    }
}
~~~

This is a test skeleton. Metric names and meter presence depend on conventions/handlers; tests need an Observation metrics handler configured and must confirm annotation scanning is enabled. If the meter name differs from expectations, check the observation name and handler mapping.

### 14.1 Testing Self-Invocation and Duplicate Instrumentation

Write tests for two cases: calling the method from another bean through the proxy, and calling the annotated method internally within the same bean. Assert observation counts or `Timer` count to demonstrate the difference.

If a controller/repository already has auto-observation, adding an annotation can double counts/spans. Inspect observation counts, the span tree, meter counts, instrumentation scope/names, and `ObservationPredicate` after adjustments.

### 14.2 Testing Cardinality

Call the method with many different customer IDs while tagging only an allow-listed channel. Verify that meter IDs do not grow with customer IDs and no PII appears in tags.

## 15. Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| @Observed creates no observation | Annotation scanning disabled or missing AspectJ weaver starter | Check dependencies and property |
| Boot 4 fails to resolve `spring-boot-starter-aop` | Starter was renamed | Use `spring-boot-starter-aspectj` |
| Annotation compiles but does not intercept | Bean not Spring-managed or call bypasses proxy | Inject bean proxy and check invocation |
| Self-invocation produces no timer | Internal call bypasses proxy | Extract bean or create manual Observation |
| Private/final method not intercepted | Proxy limitations | Use public non-final method or explicitly configured weaving |
| Observation exists but no metric | Meter handler/registry not configured | Check Actuator, `ObservationRegistry`, and `MeterRegistry` |
| Metric exists but no span | Tracing handler/bridge/exporter missing | Check Micrometer Tracing pipeline |
| Two spans/timers for one operation | Annotation overlaps auto-instrumentation | Remove annotation or filter one instrumentation path |
| @MeterTag creates many series | Parameter has high cardinality | Normalize/allow-list tag values |
| @NewSpan does not link parent | Current trace context not propagated | Check tracing bridge and context propagation |
| Async timer is too short | Measures only Future/Publisher creation time | Instrument terminal completion or use native async integration |
| Test sees no meter | Test context lacks handler/registry or aspect | Check dependencies, property, and proxy bean |

## 16. Playbook: @Observed Does Not Appear in Metrics

**Scenario:** A method has `@Observed` but `/actuator/metrics` does not display the timer.

1. Identify the Spring Boot major version.
2. Check the dependency: Boot 3.x uses `spring-boot-starter-aop`; Boot 4.x uses `spring-boot-starter-aspectj`.
3. Verify `aspectjweaver` is on the runtime classpath.
4. Confirm `management.observations.annotations.enabled=true`.
5. Confirm the class is a Spring bean and callers obtain it from the Spring container.
6. Check whether the method suffers from self-invocation, `private`/`final`, or proxy limitations.
7. Check `ObservationRegistry` and `MeterObservationHandler`.
8. Check the actual meter name and convention.
9. Check whether an `ObservationPredicate` or property excludes that observation.
10. Check whether another auto-instrumentation on the method causes duplication/filtering.
11. Write an integration test calling through the proxy and asserting `Observation`/`Timer` creation.

Do not just keep adding dependencies. Pinpoint whether the gap is in scanning, proxy interception, the Observation handler, or the export registry.

## 17. Self-Check Exercises

**Exercise 1 — Dependency.** A Boot 3.5 project needs annotation observability. Which starter should it use? When upgrading to Boot 4, how does the dependency change?

**Exercise 2 — Property.** Why is adding the AspectJ starter alone insufficient for Micrometer to scan `@Observed` and `@Timed`?

**Exercise 3 — Proxy vs. Weaving.** How does a Spring AOP proxy differ from AspectJ compile-time weaving? Does having the weaver library on the classpath mean code has been woven?

**Exercise 4 — Self-Invocation.** A public method with `@Observed` is called from another method in the same bean. Why might no observation appear? Give two ways to fix it.

**Exercise 5 — Duplicate.** A Spring Data repository is already auto-instrumented, yet a developer adds `@Observed` to a repository method. What is the risk?

**Exercise 6 — @MeterTag.** Why shouldn't a `customerId` parameter be annotated as a meter tag? Choose a bounded dimension instead.

**Exercise 7 — Async.** A method returns a `CompletableFuture` immediately after submitting a task. Why might the `Timer` fail to reflect task execution time?

**Exercise 8 — Signal Pipeline.** `@Observed` created an `Observation`, but there is no span. Which components need to be checked?

### Answer Hints

1. Boot 3.5 uses `spring-boot-starter-aop`; Boot 4 uses `spring-boot-starter-aspectj`.
2. Annotation scanning requires setting `management.observations.annotations.enabled=true`; runtime also requires appropriate registry/handlers.
3. Proxies intercept calls through a Spring bean proxy; compile-time weaving modifies bytecode at build time. Having the weaver library does not prove weaving is enabled.
4. Internal calls bypass the proxy. Move the method to another bean or create a manual `Observation`.
5. It can create duplicate observations/spans/timers and skew counts/latency.
6. Customer ID creates per-customer series and may be personal data; use allow-listed `channel`/`region`/`operation` type.
7. The method timer may stop when the `Future` is returned, before the task finishes. Measure terminal completion or use async-aware instrumentation.
8. Check the tracing observation handler, Micrometer Tracing bridge, tracer, and exporter.

## 18. Official References

- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): annotation scanning property, AspectJ starter requirement, and duplicate observations.
- [Spring Boot 3.5 — Observability](https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html): AOP starter and annotation support for Boot 3.x.
- [Spring Boot — Aspect-Oriented Programming](https://docs.spring.io/spring-boot/reference/features/aop.html): AOP auto-configuration and proxy behavior.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): `starter-aop` renamed to `starter-aspectj`.
- [Micrometer Observation Annotations](https://docs.micrometer.io/micrometer/reference/observation/annotations.html): `@Observed`, annotation aspects, and Observation behavior.
- [Micrometer Core Annotations](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): `@Timed`, `@Counted`, and meter annotation support.
- [Micrometer Tracing](https://docs.micrometer.io/tracing/reference/): `@NewSpan`, span lifecycle, and context propagation.
- [Spring Framework — AOP Proxies](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): self-invocation, proxy types, and method limitations.
- [Spring Framework — AspectJ Integration](https://docs.spring.io/spring-framework/reference/core/aop/using-aspectj.html): `@AspectJ` syntax, Spring AOP, and weaving distinctions.

**Takeaway:** Annotation observability requires dependency/aspect support, annotation scanning, and `ObservationRegistry` handlers. Boot 3.x uses `spring-boot-starter-aop`; Boot 4 uses `spring-boot-starter-aspectj`. Spring AOP proxies only intercept invocations passing through the proxy, so self-invocation and `final`/`private` methods have limitations. `@Observed` creates an `Observation`; metrics/traces depend on handlers and exporters. Avoid annotating boundaries already auto-instrumented by Spring, keep tags low-cardinality, and test method invocations through the proxy.
