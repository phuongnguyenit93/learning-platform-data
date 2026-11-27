# @NewSpan in Spring Boot Observability

In the **Annotation observability** chapter of the **SPRING_BOOT_OBSERVABILITY** module, `@NewSpan` is a Micrometer Tracing annotation used to mark a method that should create a new span when called through the configured tracing/AOP integration. A span represents an operation with a start/end time, name, context, and attributes; when an active trace exists, the new span is typically created within the current trace to add detail to the distributed trace.

`@NewSpan` is useful when automatic HTTP, database, or messaging instrumentation does not sufficiently describe a business step. For example, a method for calculating fees, checking quotas, or verifying policies may need its own span to observe latency and errors. The annotation does not send traces to a backend by itself: the application still needs a Micrometer Tracing bridge, tracer implementation, sampling policy, and appropriate exporter.

In the **SPRING_BOOT_OBSERVABILITY** module, annotation-based tracing is a complement to the Micrometer Observation API. Choose span boundaries deliberately: a span should describe a meaningful operation, not every tiny method. Too many spans make traces hard to read, increase costs, and can expose data if attributes are uncontrolled.

## 1. What Is a Span and What Does @NewSpan Do?

A distributed trace typically consists of multiple spans connected via parent-child relationships or span links. Each span describes an operation, with start/end times and context such as Trace ID, Span ID, parent context, attributes, and status.

```text
HTTP server span: POST /orders
    |
    +--> order.validate
    |
    +--> order.calculate-price
    |       |
    |       +--> HTTP client span: pricing-service
    |
    +--> database span: INSERT order
```

Spring/Micrometer can automatically create spans for certain integration points such as HTTP server/client or databases depending on dependencies/version. `@NewSpan` lets you mark an additional business method to create a span at that boundary.

What the annotation does not do:

- Does not enable distributed tracing automatically if tracing is not configured in the application.
- Does not create an exporter or OTLP endpoint by itself.
- Does not guarantee every method call creates a span if the call bypasses the AOP proxy or required integration.
- Does not replace context propagation across HTTP/JMS/executors.
- Does not turn a method into a transaction or retry boundary.
- Does not guarantee a span is stored if sampling drops the trace or export fails.

## 2. Dependencies and Versions

In Spring Boot, Micrometer Tracing can be configured with an appropriate bridge, such as OpenTelemetry or Brave, along with the corresponding exporter. The Spring Boot BOM should manage compatible versions.

Example dependencies for an application using Actuator, Micrometer Tracing with the OpenTelemetry bridge, and the OTLP exporter:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-tracing-bridge-otel</artifactId>
    </dependency>
    <dependency>
        <groupId>io.opentelemetry</groupId>
        <artifactId>opentelemetry-exporter-otlp</artifactId>
    </dependency>
</dependencies>
```

This is an example dependency set; specific auto-configuration details vary by Spring Boot version. Do not mix the Brave bridge and OpenTelemetry bridge in the same tracing setup without a clear integration architecture. Check the documentation/metadata of the version you use before choosing imports or annotation packages.

`@NewSpan` is typically imported from `io.micrometer.tracing.annotation.NewSpan` in Micrometer Tracing. Verify the package/API against your actual dependencies, because annotations and interception capabilities can differ across Spring Cloud Sleuth and Micrometer Tracing generations.

## 3. Configuring Annotation Interception

An annotation only takes effect when a component reads the annotation and intercepts method invocations. In some Spring Boot/Micrometer Tracing setups, annotation support is auto-configured when appropriate dependencies and AOP infrastructure are present; in other setups, you must enable the annotation handler/AOP integration according to the version's documentation.

Illustrative configuration with Spring AOP:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy
class TracingAopConfiguration {
}
```

Enabling `@EnableAspectJAutoProxy` alone does not supply the Micrometer span aspect if the corresponding library/integration is missing. Verify that the annotation aspect/handler is registered. Do not create a second aspect intercepting `@NewSpan` when auto-configuration has already registered one, as doing so can produce unintended nested spans.

If a method is called internally from another method in the same bean (self-invocation), the call may bypass the Spring proxy and the annotation will not be intercepted. Move the operation to another Spring bean or call through the proxy according to an explicit design when AOP interception is needed.

## 4. Using @NewSpan on Business Methods

Example marking a pricing step in a service:

```java
import io.micrometer.tracing.annotation.NewSpan;
import org.springframework.stereotype.Service;

@Service
class PricingService {

    @NewSpan("order.calculate-price")
    Price calculate(Order order) {
        return pricingEngine.calculate(order);
    }
}
```

The span name should describe the operation concisely, stably, and meaningfully. Avoid generating span names from order IDs, usernames, full URLs, or free-form input; span names can be used in queries/indexing and should remain low-cardinality.

If the annotation does not accept a name parameter in a specific version, use the supported API or default naming convention. Do not copy examples across versions without checking the compile-time API.

### Span Name and Operation Boundary

A span should cover an operation significant enough to measure latency or understand relationships in a trace. Examples:

- `order.validate` — validate order rules.
- `order.calculate-price` — calculate price.
- `payment.authorize` — execute payment authorization logic.
- `inventory.reserve` — reserve inventory.
- `invoice.render` — generate invoice document.

There is no need to create separate spans for getters, setters, simple mappings, or every private helper. Overly small spans increase overhead and fragment traces.

## 5. Creating Spans from Methods and Setting Attributes

`@NewSpan` may support declaring the span name and parameters to include on the span depending on the version's annotation/API. However, do not assume every method parameter is safe to export. For identifiers or sensitive data, prefer explicitly allow-listed attributes or use the Observation API for controlled key-values.

Example using the Observation API when finer metadata control is needed:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
class OrderPolicyService {
    private final ObservationRegistry registry;

    OrderPolicyService(ObservationRegistry registry) {
        this.registry = registry;
    }

    PolicyResult evaluate(Order order, String channel) {
        return Observation.createNotStarted("order.policy.evaluate", registry)
                .lowCardinalityKeyValue("channel", normalize(channel))
                .observe(() -> policyEngine.evaluate(order));
    }

    private String normalize(String channel) {
        if ("mobile".equals(channel)) return "mobile";
        if ("partner".equals(channel)) return "partner";
        return "web";
    }
}
```

`Observation` is appropriate when you want a single instrumentation to feed both metrics and tracing handlers by convention. `lowCardinalityKeyValue` is intended for dimensions with a bounded set of values. If a detailed identifier is needed on a trace, evaluate privacy, sampling, and retention; do not turn it into a metric label.

## 6. Parent Span and Active Trace Context

When an HTTP server request has already opened a trace context and a method is called within the same execution context, the span created by `@NewSpan` is normally linked to the active span by the tracing integration. The trace may look like this:

```text
Trace ID: 4bf92f3577b34da6a3ce929d0e0e4736
  Span: HTTP POST /orders
    Span: order.validate
    Span: order.calculate-price
      Span: HTTP GET pricing-service
    Span: database INSERT order
```

If the method is called when there is no active span, the integration may create a new root span or behave according to configuration. Do not assume a span always has a parent. To link across service boundaries, a tracing propagator must inject/extract context over the respective protocol.

A span annotation does not automatically propagate context to thread pools, `CompletableFuture`, Reactor schedulers, or message brokers. Asynchronous boundaries require explicit context propagation; otherwise, spans may lose their parent or logs may lack Trace IDs.

## 7. Exceptions and Span Status

When an intercepted method throws an exception, the tracing integration may record an exception event and mark the span as an error depending on the handler/convention. Exceptions must still be handled per application semantics; the annotation does not retry, swallow exceptions, or alter business results.

Example:

```java
@NewSpan("payment.authorize")
PaymentResult authorize(PaymentCommand command) {
    return paymentGateway.authorize(command);
}
```

If `paymentGateway` throws an exception, the span may finish with an error status and exception event. Check the trace backend to confirm the instrumentation/version actually records errors. Do not put the verbatim exception message into the span name or a metric tag; messages may contain URLs, user data, or tokens.

If code catches the exception and returns a fallback result, the span may be marked successful if the instrumentation only checks whether an exception escaped the method. If a fallback is a business outcome that must be observed separately, add a low-cardinality outcome or create an `Observation`/business metric representing the fallback.

## 8. Async Methods and Context Propagation

With `@Async`, an executor, or `CompletableFuture`, a method may run on another thread. ThreadLocal-based tracing context does not automatically follow every executor. You need context propagation integration compatible with Spring/Micrometer and ensure a task decorator/accessor is configured.

Example configuring an executor with a context-propagating task decorator in a supported Spring Framework version:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
class AsyncTracingConfiguration {

    @Bean(name = "applicationExecutor")
    ThreadPoolTaskExecutor applicationExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
```

Tasks must actually be submitted through the configured executor. `ContextPropagatingTaskDecorator` only captures/restores contexts for which a corresponding accessor is registered; do not assume it propagates arbitrary `ThreadLocal` values automatically. Verify Trace ID/Span ID in logs and parent/links in traces on worker threads.

For reactive code, Reactor Context and Micrometer context-propagation integration must be properly configured. Do not leave a span open on one thread expecting a callback running on another scheduler to inherit the context automatically.

## 9. Sampling and Span Cost

`@NewSpan` creates an additional span when a method is intercepted, but whether the span is exported depends on sampling and the exporter pipeline. Head sampling can decide to keep or drop a trace up front; tail sampling can be performed in the collector/backend pipeline if the architecture supports it.

A frequently invoked method can generate a large volume of spans. Before adding the annotation, consider:

- Is the operation meaningful enough to appear in traces?
- Does the span duration help explain latency?
- Is there already an automatic span covering the same operation?
- Do attributes have appropriate cardinality and sensitivity?
- Can sampling/export capacity handle the volume?

Do not use `@NewSpan` to replace metrics for counts/rates. Spans describe selected individual operations; metrics aggregate workloads at lower cost for long-term dashboards.

## 10. When to Use @NewSpan, @Observed, or the Observation API?

| Mechanism | Purpose | When Appropriate |
| --- | --- | --- |
| @NewSpan | Create a new span around a method via tracing annotation integration | Want to add a specific span within the current trace |
| @Observed | Create an Observation around a method per Micrometer observation aspect/convention | Want an observation that can produce both metrics and tracing handlers |
| Observation API | Create an observation programmatically with explicit lifecycle and metadata | Need dynamic control, low/high-cardinality values, or scopes |
| Tracer API | Create spans directly via the tracing implementation | Need low-level, specific span/context manipulation |

Do not enable multiple mechanisms wrapping the same method unintentionally. For example, intercepting both `@NewSpan` and `@Observed` can create two nested spans/observations, lengthening traces and skewing metric counts.

`@Observed` also requires the observation annotation aspect to be configured; simply adding the annotation to a method does not guarantee it works in every project. Check AOP/proxy support and your version's conventions.

## 11. AOP Limitations to Remember

Annotation-based instrumentation typically depends on proxies/interception. Common reasons a span fails to appear:

- The method is called internally within the same bean (self-invocation).
- The object is instantiated with `new` instead of being managed by the Spring container.
- The method or class cannot be proxied under the active AOP mechanism.
- The annotation aspect/handler is not registered.
- The method runs on another thread without context propagation.
- Tracing is not configured or the trace was dropped by sampling.

When a span is missing, check in order: whether the bean is Spring-managed; whether the call goes through the proxy; whether annotation integration is enabled; whether an active context exists; whether sampling kept the trace; and whether the exporter/collector/backend receives the data.

## 12. Testing @NewSpan

A test should verify that a span is actually created when the method is called through the Spring proxy, rather than merely checking that the annotation exists on the class.

Suggested workflow:

1. Initialize a Spring application context with tracing test setup and an in-memory/test span exporter compatible with your version.
2. Obtain the service bean from `ApplicationContext` instead of creating it with `new`.
3. Call the method through the bean proxy inside an active parent span if testing parent-child relationships.
4. Verify span name, parent context, and start/end lifecycle.
5. Call a method that throws an exception; verify error status/event per convention.
6. Verify there are no duplicate spans when multiple annotations/aspects are enabled.
7. For async, submit tasks through the configured executor and verify context on the worker thread.
8. Do not rely on traces being saved by a production backend in tests; use a test exporter or an observable observation handler.

Test span exporter APIs vary by OpenTelemetry/Micrometer version. Pick an exporter/testing utility compatible with the BOM rather than copying imports from another version.

### Test Matrix

| Scenario | Outcome to Verify |
| --- | --- |
| Call Spring bean via proxy | New span created if integration is enabled |
| Call internal method in same bean | Confirm whether self-invocation bypasses the aspect |
| No active span | Root/new span per configured semantics |
| Active parent span present | Child/link relationship matches convention |
| Method throws exception | Span records error per handler |
| Method runs async | Context captured/restored or span link is explicit |
| Sampling drops trace | Do not conclude the annotation is broken just because the backend has no span |
| Two aspects intercept together | No unintended duplicate spans generated |
| Attribute contains sensitive ID | Not exported unless permitted by policy |

## 13. Scenario Exercise

A developer adds `@NewSpan("order.calculate-price")` to a method in `OrderService`. Running locally, no new span appears. The method is called from another method in the same class. The application has Micrometer Tracing dependencies and HTTP server spans still appear normally.

**Questions:**

1. Why is there an HTTP server span but no span from `@NewSpan`?
2. How does self-invocation affect the Spring AOP proxy?
3. How should the annotation aspect/handler and bean lifecycle be verified?
4. If the method is moved to an executor, what else needs to be checked?
5. Does adding `@NewSpan` guarantee the span will appear in the backend?

**Analysis Hints:**

- HTTP instrumentation can work independently of annotation interception. Having tracing dependencies does not by itself prove the `@NewSpan` aspect is registered.
- An internal call within the same bean may bypass the Spring proxy, so the aspect does not run.
- Obtain the bean from `ApplicationContext`, invoke it via proxy, verify annotation integration/auto-configuration, and check the annotation version/package.
- Async requires context propagation through the executor; without context, spans may lack parents or logs may lack trace IDs.
- Sampling can drop traces and the exporter/backend can fail. Use a test exporter to isolate annotation interception issues from export issues.

### Completion Checklist

| Topic | Can Explain / Verify |
| --- | --- |
| Role of @NewSpan | Creates a span around a method when annotation integration intercepts it |
| Micrometer Tracing | Appropriate bridge, tracer, and exporter configured |
| AOP/proxy | Understands self-invocation and Spring-managed beans |
| Span naming | Stable names, free of request/business IDs |
| Parent context | Span links to active trace per convention |
| Error handling | Knows how exceptions affect span status |
| Async/reactive | Context propagation across threads/schedulers |
| Sampling/export | Distinguishes span not created, sampled out, and export failure |
| Cardinality/privacy | No sensitive data in attributes/tags |
| Alternative APIs | Knows when to use `@Observed`, Observation API, or `Tracer` |
| Testing | Verifies spans via proxy and test exporter |

**Takeaway:** `@NewSpan` adds a span around a business method when Micrometer Tracing annotation integration and AOP interception are configured. The annotation does not enable tracing, exporters, or context propagation on its own. Choose meaningful span boundaries, stable names, and controlled attributes; watch out for self-invocation, Spring proxies, async/reactive contexts, and sampling. Use the Observation API or `@Observed` when you need tighter control over lifecycle and metrics/tracing handlers, and test using a Spring bean proxy and test exporter to confirm spans are actually produced.
