# Micrometer, Metrics, and Tracing in Native Executables

A Spring Boot application running on the JVM or as a GraalVM Native Image needs to answer the same operational questions: how long do requests take, where is the error rate rising, which service is slow, and which components did a request pass through. Micrometer provides a unified instrumentation API; Spring Boot Actuator auto-configures many meters and `Observation`s; and Micrometer Tracing connects observations with distributed traces.

When building native, these APIs still work because the instrumentation is compiled with the application. What matters is that a native executable is not a full JVM: there is no JIT compiler or HotSpot-style Java agent loading mechanism, some JVM metrics may differ or be absent, and any exporter/custom instrumentation library must be compatible with closed-world analysis.

This lesson builds an observability configuration for a native Spring Boot service using Actuator, Micrometer Metrics, Micrometer Observation, OpenTelemetry, and OTLP. The examples use Spring Boot 4.x; if your project is on Boot 3.x, use the dependency and property references for that exact minor version instead of mixing configurations across major versions.

## 1. The Three Observability Signals and the Role of Micrometer

Observability is commonly organized into three complementary signals:

| Signal | Key question | Example |
| --- | --- | --- |
| Logs | What event occurred and what details accompanied it? | Exceptions, processing state, logs with trace ID |
| Metrics | How is the system performing over time? | Request rate, latency, error count, memory |
| Traces | Which services/spans did a request pass through? | HTTP server → service → database → HTTP client |

Metrics aggregate activity into time series. Tracing preserves parent-child relationships between operations within a request. Logs record detailed events. When all three signals share the same context, you can locate a trace and then open the related logs or view metrics at the time of a slow trace.

Spring Boot uses Micrometer for metrics and tracing:

- `MeterRegistry` holds meters such as `Counter`, `Timer`, `Gauge`, and `DistributionSummary`.
- `ObservationRegistry` coordinates an observation and the handlers processing its lifecycle.
- `Micrometer Tracing` provides a backend-independent tracer API.
- Registries/exporters ship data to Prometheus, OTLP, Zipkin, or other monitoring systems.

`Observation` is a convenient API layer when one operation needs to produce both a metric and a span. When you only need a simple measurement, you can use `MeterRegistry` directly.

## 2. What Changes When an Application Runs on Native Image?

Native Image is analyzed and compiled ahead of time. The executable contains the code reachable from entry points and the metadata recognized during the build. There is no bundled JVM to load classes and run a JIT like a `java -jar` application.

For observability, distinguish between:

1. **In-code instrumentation:** calls like `Counter.increment()`, `Timer.record()`, or `Observation.observe()` are compiled into the executable. This is the native-friendly way to use Micrometer.
2. **Spring auto-configuration:** Actuator and integrations supported by Spring Boot are processed via AOT; the framework contributes the required code and hints.
3. **Exporters and third-party libraries:** must be on the classpath at build time and compatible with Native Image. If a library uses reflection, resources, or proxies in ways static analysis cannot infer, reachability metadata may be needed.
4. **Runtime Java agents:** agents based on `java.lang.instrument`, `ClassFileTransformer`, or JVMTI are not the instrumentation mechanism for a native executable. Do not treat JVM `-javaagent` commands as the way to configure Micrometer for native.

One common point of confusion: **Micrometer Tracing is an observability library compiled with the application; the GraalVM Native Image Tracing Agent is a tool that runs on the JVM to collect metadata for a native build.** Both have "Tracing Agent" in their names, but they serve two different purposes.

### Data Flow Diagram

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Spring MVC / WebFlux"]
    B --> C["Micrometer Observation"]
    C --> D["Meter handler"]
    C --> E["Tracing handler"]
    D --> F["MeterRegistry"]
    E --> G["Tracer / Span"]
    F --> H["Prometheus or OTLP metrics"]
    G --> I["OTLP or Zipkin traces"]
    B --> J["Application logs"]
    G --> K["Trace ID / Span ID in MDC"]
    K --> J
~~~

## 3. Adding Dependencies for Actuator, Metrics, and Tracing

Spring Boot manages compatible dependency versions via dependency management/BOM. Do not specify a separate Micrometer version manually unless you have an intentional upgrade requirement.

### Maven with OTLP

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-opentelemetry</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-otlp</artifactId>
    </dependency>
</dependencies>
~~~

`spring-boot-starter-actuator` provides endpoints and auto-configuration for Micrometer. `spring-boot-starter-opentelemetry` provides Micrometer Tracing integration with OpenTelemetry in Spring Boot 4.x. `micrometer-registry-otlp` registers the OTLP metrics exporter.

### Gradle with OTLP

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("org.springframework.boot:spring-boot-starter-opentelemetry")
    implementation("io.micrometer:micrometer-registry-otlp")
}
~~~

### If Using Prometheus

You can replace the OTLP metrics registry with the Prometheus registry:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

~~~groovy
dependencies {
    implementation("io.micrometer:micrometer-registry-prometheus")
}
~~~

You can configure multiple registries simultaneously if you want to send the same meters to multiple backends. When doing so, actively monitor export overhead, number of time series, and duplicate data. Pick a primary export path in your test environment to verify first.

## 4. Configuring Actuator Endpoints and Exporters

Example `application.yml` configuration for OTLP:

~~~yaml
spring:
  application:
    name: orders-api

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics

  endpoint:
    health:
      probes:
        enabled: true

  metrics:
    tags:
      application: orders-api
      environment: staging

  otlp:
    metrics:
      export:
        url: http://otel-collector:4318/v1/metrics
        step: 30s

  opentelemetry:
    resource-attributes:
      service.name: orders-api
      deployment.environment: staging
    tracing:
      export:
        otlp:
          endpoint: http://otel-collector:4318/v1/traces

  tracing:
    sampling:
      probability: 0.1
~~~

Meaning:

- `management.endpoints.web.exposure.include` determines which endpoints are exposed over HTTP.
- `/actuator/metrics` allows inspecting registered meters.
- `/actuator/health` and health probes serve application health checks.
- `management.metrics.tags` adds low-cardinality tags to meters.
- `management.otlp.metrics.export.url` is the endpoint receiving OTLP metrics.
- `management.opentelemetry.tracing.export.otlp.endpoint` is the endpoint receiving OTLP traces.
- `service.name` and `deployment.environment` distinguish the service and environment in the backend.
- `management.tracing.sampling.probability` controls the proportion of requests sampled for tracing.

If using a shared OTLP endpoint, Spring Boot provides the `management.opentelemetry.otlp.endpoint` property; signal-specific endpoints take precedence when configured. The metrics exporter still has the signal-specific property `management.otlp.metrics.export.url`.

### Configuring the Prometheus Endpoint

If using Prometheus, add `prometheus` to the endpoint exposure list:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

The `/actuator/prometheus` endpoint returns data in Prometheus scrape format. A minimal scrape configuration:

~~~yaml
scrape_configs:
  - job_name: orders-api
    metrics_path: /actuator/prometheus
    static_configs:
      - targets:
          - orders-api:8080
~~~

Prometheus actively scrapes each instance. The OTLP registry typically pushes data periodically. Choose the model that fits your monitoring system and service deployment style.

### Do Not Expose All of Actuator to Public Networks

Metrics endpoints can reveal information about resources, throughput, dependencies, and internal state. Expose only the endpoints you truly need, restrict network access with network policies/security, and protect endpoints with Spring Security or a separate management interface. Do not use `include: "*"` as a default production configuration.

## 5. Creating Business Metrics with MeterRegistry

Spring Boot automatically registers many meters for HTTP server/client, JVM, system, datasource, task executors, and supported integrations. Applications should still create dedicated metrics for business-meaningful behavior.

Example component recording the number of orders created and payment authorization duration:

~~~java
package com.example.orders.observability;

import java.util.function.Supplier;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import org.springframework.stereotype.Component;

@Component
public class OrderMetrics {

    private final MeterRegistry registry;
    private final Counter createdOrders;
    private final Timer paymentAuthorization;

    public OrderMetrics(MeterRegistry registry) {
        this.registry = registry;

        this.createdOrders = Counter.builder("orders.created")
                .description("Number of orders created")
                .register(registry);

        this.paymentAuthorization = Timer.builder("payment.authorization")
                .description("Time spent authorizing a payment")
                .publishPercentileHistogram()
                .register(registry);
    }

    public void orderCreated() {
        this.createdOrders.increment();
    }

    public <T> T measurePaymentAuthorization(Supplier<T> operation) {
        Timer.Sample sample = Timer.start(this.registry);
        try {
            return operation.get();
        }
        finally {
            sample.stop(this.paymentAuthorization);
        }
    }
}
~~~

Using the component in a service:

~~~java
@Service
public class OrderService {

    private final OrderMetrics metrics;
    private final PaymentGateway paymentGateway;
    private final OrderRepository orderRepository;

    public OrderService(
            OrderMetrics metrics,
            PaymentGateway paymentGateway,
            OrderRepository orderRepository) {
        this.metrics = metrics;
        this.paymentGateway = paymentGateway;
        this.orderRepository = orderRepository;
    }

    public Order createOrder(CreateOrderCommand command) {
        PaymentResult result = this.metrics.measurePaymentAuthorization(
                () -> this.paymentGateway.authorize(command)
        );

        Order saved = this.orderRepository.save(Order.from(command, result));
        this.metrics.orderCreated();
        return saved;
    }
}
~~~

The example illustrates where to place instrumentation; in a real application, only increment `orders.created` after the order has been persisted successfully. Do not place a counter before an operation that may roll back and still record success.

### Choosing the Right Meter for the Question

| Meter | Use when | Example |
| --- | --- | --- |
| Counter | Counting monotonically increasing events | Orders created, declined payment attempts |
| Timer | Measuring duration and execution count | Time spent calling payment gateway |
| Gauge | Reading a current value | Number of messages waiting in a queue |
| DistributionSummary | Tracking the distribution of a numeric value | Payload size, items per batch |
| LongTaskTimer | Tracking an operation still in progress | Long-running report or batch job |

Do not create a new meter per request. Register the meter once, then update its value through the saved reference.

## 6. Using Observation to Emit Metrics and Traces Together

`ObservationRegistry` lets an application describe an operation with a unified lifecycle. When Spring Boot registers `DefaultMeterObservationHandler`, a completed observation can produce timers/counters. When Micrometer Tracing is configured, the tracing handler can also create the corresponding span.

Example observing the payment authorization step:

~~~java
package com.example.orders.observability;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.stereotype.Component;

@Component
public class PaymentObservation {

    private final ObservationRegistry registry;

    public PaymentObservation(ObservationRegistry registry) {
        this.registry = registry;
    }

    public <T> T observeAuthorization(
            String paymentMethod,
            String orderId,
            java.util.function.Supplier<T> operation) {

        return Observation.createNotStarted(
                        "payment.authorization",
                        this.registry
                )
                .lowCardinalityKeyValue("payment.method", paymentMethod)
                .highCardinalityKeyValue("order.id", orderId)
                .observe(operation);
    }
}
~~~

The two key-value types serve different roles:

- `lowCardinalityKeyValue` is used for both metrics and traces. Values should belong to a finite set such as `card`, `bank-transfer`, `success`, `failed`.
- `highCardinalityKeyValue` is only for traces or signals that can tolerate high cardinality. Examples include `order.id`, `user.id`, or request identifiers.

Micrometer excludes high-cardinality key-values from meter tags because each unique value can create a new time series. Attaching `order.id` to a metric can make the number of meters grow with the number of orders and increase memory and backend costs.

### Avoid Duplicate Observations

Spring Boot already instruments many components such as the HTTP server, HTTP client, and repositories. Adding `@Observed` or manually creating an observation around a component that is already auto-instrumented can cause the backend to receive two observations for the same operation.

Only add observations for business boundaries not yet observed. If you need annotations such as `@Observed`, `@Timed`, `@Counted`, `@MeterTag`, or `@NewSpan`, enable `management.observations.annotations.enabled=true` and add an appropriate AspectJ Weaver. Annotation-based instrumentation requires AOP support; verify both proxy behavior and native compatibility.

## 7. Configuring Tracing with OpenTelemetry and OTLP

Spring Boot supports Micrometer Tracing with OpenTelemetry/OTLP and OpenZipkin Brave/Zipkin. Examples in this lesson use OpenTelemetry and OTLP.

In a container environment, you can configure the collector using environment variables:

~~~bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://otel-collector:4318/v1/traces
OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://otel-collector:4318/v1/metrics
OTEL_SERVICE_NAME=orders-api
OTEL_RESOURCE_ATTRIBUTES=deployment.environment=staging
~~~

Spring Boot maps several OpenTelemetry environment variables to configuration properties. Signal-specific endpoints for traces/metrics take precedence over the general endpoint. If using HTTP and only providing the general endpoint, Spring Boot appends signal-specific paths such as `/v1/traces` or `/v1/metrics`.

You can configure this directly in `application.yml` as shown in the previous section. For production, obtain endpoints, headers, and tokens from your environment's secret/configuration management. Do not commit access tokens or API keys into source control.

### Sampling

By default, Spring Boot samples 10% of requests to avoid sending too many traces. You can change this with:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.05
~~~

Do not enable `1.0` for all requests in high-traffic production without evaluating the cost. You can raise the rate in staging for debugging and lower it in production. When using OpenTelemetry, the sampler also supports parent-based mode so child traces respect the parent trace's sampling decision.

### Span Limits

Spans can contain attributes, events, links, and string values. Limit them to avoid oversized payloads:

~~~yaml
management:
  opentelemetry:
    tracing:
      limits:
        max-attributes: 64
        max-attribute-value-length: 256
~~~

If the backend enforces its own limits, configure compatible values. Never record request bodies, access tokens, passwords, or personal data in span attributes.

## 8. Propagating Traces Across HTTP Clients, Async, and Reactive Pipelines

A trace is only useful when the relationship between operations is properly propagated across thread and service boundaries.

### Using Builders Configured by Spring Boot

To automatically propagate trace context over HTTP, create `RestClient` or `WebClient` using the builders auto-configured by Spring Boot:

~~~java
@Configuration(proxyBeanMethods = false)
public class PartnerClientConfiguration {

    @Bean
    RestClient partnerRestClient(RestClient.Builder builder) {
        return builder
                .baseUrl("http://partner-service")
                .build();
    }
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
public class ReactivePartnerClientConfiguration {

    @Bean
    WebClient partnerWebClient(WebClient.Builder builder) {
        return builder
                .baseUrl("http://partner-service")
                .build();
    }
}
~~~

If you instantiate a client using a constructor or a builder not managed by Spring, automatic instrumentation and trace propagation may not be attached. In that case, apply the appropriate customizers or use the auto-configured builder.

### Context Propagation with Reactive

In reactive pipelines, `ThreadLocal` is not automatically restored across every operator. You can enable automatic context propagation:

~~~yaml
spring:
  reactor:
    context-propagation: auto
~~~

This enables observation/tracing context to be propagated across reactive operators via the Context Propagation mechanism.

### Context Propagation with @Async

With the `AsyncTaskExecutor` auto-configured by Spring Boot, enable:

~~~yaml
spring:
  task:
    execution:
      propagate-context: true
~~~

If configuring an executor yourself, register `ContextPropagatingTaskDecorator`:

~~~java
@Configuration(proxyBeanMethods = false)
public class AsyncConfiguration {

    @Bean
    ContextPropagatingTaskDecorator contextPropagatingTaskDecorator() {
        return new ContextPropagatingTaskDecorator();
    }
}
~~~

Without context propagation, traces can break across new threads: logs lack trace IDs or child spans are detached from the parent trace.

## 9. Correlating Trace IDs with Logs

When Micrometer Tracing is configured, Spring Boot adds trace ID and span ID to MDC so logs can be correlated with traces. The default log pattern includes a correlation ID from these two values.

You can customize the format, for example:

~~~yaml
logging:
  pattern:
    correlation: "[orders-api,%X{traceId:-},%X{spanId:-}] "
  include-application-name: false
~~~

A log line can then include the service name, trace ID, and span ID. When investigating an error in the tracing backend, you can grab the trace ID to filter the corresponding logs.

Baggage can carry additional context across service boundaries. Only propagate fields that are genuinely needed, keep sizes bounded, and avoid unnecessary secrets/PII. Baggage can also be added to MDC or span tags if configured, so tightly control which fields are propagated.

## 10. Inspecting Metric Endpoints and Exporters

Actuator provides two useful endpoints:

- `/actuator/metrics`: lists meters and inspects a single meter by name.
- `/actuator/prometheus`: exports data in Prometheus format when the registry and endpoint are configured.

Example inspecting a meter:

~~~bash
curl http://localhost:8080/actuator/metrics/orders.created
~~~

Inspecting a timer:

~~~bash
curl http://localhost:8080/actuator/metrics/payment.authorization
~~~

Inspecting a meter by tag:

~~~bash
curl "http://localhost:8080/actuator/metrics/http.server.requests?tag=method:POST"
~~~

Meter names in the metrics endpoint match the Micrometer names registered in code. The Prometheus backend may normalize names to snake case; do not use normalized names to query the Actuator endpoint.

With Prometheus:

~~~bash
curl http://localhost:8080/actuator/prometheus
~~~

With OTLP, the metrics registry sends batches on the configured interval. Check exporter logs, collector endpoints, and backend data. Having `/actuator/metrics` return a meter only proves the meter was recorded in the process; it does not prove the exporter succeeded in delivering it to the backend.

## 11. Differences to Check Between JVM and Native Executables

A native executable is not simply a faster JVM. Therefore, do not mechanically compare every JVM meter between the two binary types.

| Metric group | JVM executable | Native executable |
| --- | --- | --- |
| Custom business metrics | Present if the code executes | Present if the code is reachable and executes |
| HTTP server/client metrics | Present when integration is configured | Present when server/client integration is compatible and included in the image |
| Database/connection pool metrics | Depends on driver/pool integration | Depends on driver/pool integration and reachability support |
| Process/system metrics | Depends on OS and Micrometer binders | Depends on OS, native runtime, and supported binders |
| JVM memory/GC metrics | Based on JVM MXBeans | May differ or be absent; native runtime is not a HotSpot heap |
| Class loading/JIT metrics | Has class loader/JIT-related metrics | No JIT compilation at runtime; do not expect the same set of metrics |
| Application startup/ready time | Present | Can be used to measure native application startup/ready time |

When benchmarking observability for native, record:

- `application.started.time` and `application.ready.time`.
- Process CPU, memory, and thread count if provided by binders/OS.
- Request rate, error rate, and latency.
- Exporter queue, export duration, and telemetry send errors.
- Number of meters, number of series, and number of spans generated.
- Sampling rate and span size.

Do not use JIT compilation time to evaluate a native executable since native code is compiled ahead of time. For memory, distinguish heap/process RSS/container memory and how the backend collects each value; they do not necessarily mean the same thing between JVM and native.

## 12. Testing Observability on JVM and Native

Tests should be split into three layers.

### Unit Tests for Instrumentation

Use `SimpleMeterRegistry` to verify that Counters/Timers are updated properly without connecting to a backend. For `Observation`, use `TestObservationRegistry` to verify observation names, lifecycles, and key-values.

These tests verify instrumentation code, not exporters or the native image.

### Integration Tests on the JVM

Verify:

- Actuator endpoints are exposed properly.
- The registry is auto-configured when the dependency is on the runtime classpath.
- The metrics endpoint contains business meters.
- Traces are exported to a test collector/backend.
- `RestClient`/`WebClient` propagates trace context.
- Context propagation works across `@Async` or Reactor.
- Logs contain correlation IDs when traces are sampled.

Note: Spring Boot does not auto-configure reporting tracing components when using `@SpringBootTest` under the default test configuration. If a test needs to verify the exporter, configure test tracing explicitly or use an integration test running the application with a test collector. Do not conclude that the production exporter is broken just because the test context does not initialize reporting components.

### Native Smoke/Integration Tests

After building the executable:

~~~bash
# Maven project configured with the native profile.
./mvnw -Pnative native:compile

# Gradle project configured with Native Build Tools.
./gradlew nativeCompile
~~~

Run the native executable in an environment with a test collector/backend. Send an order creation request, an error request, and a request calling another service. Verify:

1. The Actuator health endpoint returns the expected status.
2. The metrics endpoint lists application meters.
3. Prometheus scrape or the OTLP collector receives metrics.
4. The collector receives traces with the correct service name and resource attributes.
5. Child spans are linked to parent traces across HTTP.
6. Logs contain the matching correlation ID.
7. No missing class, resource, or exporter initialization errors occur in the native runtime.

Do not stop at confirming the binary starts successfully. You must execute requests to trigger instrumentation and exporters.

## 13. Reachability, AOT, and Third-Party Observability Libraries

Actuator/Micrometer integrations supported by Spring Boot usually have appropriate auto-configuration and AOT contributions. However, you cannot assume every third-party registry, exporter, or instrumentation agent works in native.

If a custom exporter uses reflection, `ServiceLoader`, resources, or dynamic proxies:

1. Check whether the library documents GraalVM Native Image support or provides reachability metadata.
2. Verify the implementation is included on the runtime classpath at build time.
3. Check whether Spring AOT recognizes the beans and auto-configuration.
4. If metadata is missing, run the application on the JVM with the GraalVM Tracing Agent and exercise the export flow.
5. Review the generated metadata, then rebuild native.
6. Run native integration tests to confirm the exporter works.

Do not confuse the GraalVM Tracing Agent with Micrometer Tracing. The Tracing Agent only collects reflection/resource/proxy metadata on the JVM; it does not export business metrics or traces to a backend.

If an APM product requires `-javaagent` or JVMTI to instrument bytecode at runtime, confirm vendor-specific native support. A native executable does not have HotSpot-style Java Instrumentation; choose an SDK or integration designed for native if available.

## 14. Protecting Telemetry Cost and Quality

An observability system can increase CPU, memory, network, and storage costs if misconfigured.

### Keep Metric Cardinality Low

Do not attach unbounded values to metric tags:

| Avoid as metric tag | Prefer instead |
| --- | --- |
| `order.id` | `payment.method` |
| `user.email` | `customer.tier` |
| `request.id` | `http.method` |
| Full URL with ID | URI template such as `/orders/{id}` |
| Timestamp | `region`, `environment` |

Request IDs are useful in traces or logs, but should not create a new time series per request.

### Control Sampling and Span Size

- Choose sampling appropriate for traffic volume.
- Limit attributes/events/links on spans.
- Avoid recording large payloads or objects on spans.
- Do not emit the same observation twice.
- Use `ObservationPredicate` if you need to exclude a group of observations from reporting.
- Check exporter timeouts, queues, and batch sizes to prevent backlogs when the collector is unreachable.

### Handling Short-Lived Applications

Prometheus scrapes each instance and may miss batch jobs or processes that exit before the next scrape. For short-lived tasks, consider OTLP push or Prometheus Pushgateway according to your operational model. Do not use Pushgateway in place of standard scraping for long-running services without a clear need.

## 15. Troubleshooting Common Errors

| Symptom | Possible cause | Check |
| --- | --- | --- |
| `/actuator/metrics` returns 404 | Endpoint not exposed or Actuator missing from classpath | Check dependencies and `management.endpoints.web.exposure.include` |
| Meters exist but Prometheus cannot scrape | Missing Prometheus registry or endpoint not exposed | Check registry dependency and `/actuator/prometheus` |
| Metrics endpoint has data but OTLP backend is empty | Exporter not auto-configured, wrong endpoint, or network blocked | Check dependencies, URL properties, exporter logs, and collector |
| JVM has metrics but native lacks some `jvm.*` | Native runtime does not expose the same MXBean/JIT metrics | Compare specific metrics; use appropriate process/container metrics |
| Traces do not appear | Tracing exporter not configured, sampling drops traces, or collector not receiving | Check starter, sampling, endpoint, and collector |
| Traces break when calling another service | Client created without auto-configured builder or context not propagated | Use Spring's `RestClient.Builder`/`WebClient.Builder` and check propagation |
| Logs lack trace ID | Trace not sampled, MDC/correlation or context propagation disabled | Check tracing config and logging pattern |
| `@Async` loses trace context | Executor does not propagate context | Enable property or use `ContextPropagatingTaskDecorator` |
| Native build misses exporter class/resource | Library uses dynamic access without metadata | Check reachability metadata and Tracing Agent output |
| Telemetry lost in short-lived apps | Export interval exceeds process lifetime or abrupt shutdown | Use batch-friendly exporter and verify graceful shutdown |
| Time series count keeps growing | High-cardinality metric tag or dynamic meter name | Remove IDs/requests/full URLs from metric tags |
| Duplicate timer/span for one operation | Auto instrumentation and custom observation overlap | Remove annotation or disable corresponding automatic observation |

## 16. Lab: Observing a Native Order API Service

Create a Spring Boot REST API with a `POST /orders` endpoint, an order processing service, and a `PaymentGateway` calling a partner service.

Steps:

1. Add Actuator, the OpenTelemetry starter, and the OTLP metrics registry.
2. Configure resource attributes including `service.name`, `deployment.environment`, and application version.
3. Expose `health`, `info`, and `metrics`; expose `prometheus` only if the Prometheus registry is added.
4. Create Counter `orders.created` and Timer `payment.authorization`.
5. Create Observation `payment.authorization` with `payment.method` as low-cardinality and `order.id` as high-cardinality.
6. Create `RestClient` using the auto-configured builder to propagate trace context to the payment service.
7. Configure sampling and the OTLP collector endpoint.
8. Run on JVM, send success and error requests; check metrics, traces, and log correlation.
9. Build the native executable and send the same requests again.
10. Compare meters appearing on JVM/native; note which metrics differ because the runtime is not HotSpot.
11. Verify the exporter, collector, and context propagation when running native.
12. Increase test load and observe cardinality, sampling, export queue, and memory overhead.

### Self-Check Questions

1. What different questions do metrics, traces, and logs answer?
2. How does `MeterRegistry` differ from `ObservationRegistry` in role?
3. Why can `Observation` produce both a timer and a span?
4. When should you use Counter, Timer, and Gauge?
5. Why should `order.id` be a high-cardinality trace attribute rather than a metric tag?
6. Why can native Spring Boot still use Micrometer without a Java agent?
7. How does the GraalVM Native Image Tracing Agent differ from Micrometer Tracing?
8. Why shouldn't you expect JIT compilation metrics on a native executable?
9. Why must you use the auto-configured builder when creating `RestClient` or `WebClient`?
10. What should you check when metrics appear on Actuator but the OTLP backend receives no data?
11. Why might a `@SpringBootTest` test not automatically export tracing data?
12. In which cases do you need to add reachability metadata for a third-party exporter?

**Success criteria:** able to configure Actuator and a metrics registry; create business metrics with Micrometer; use `Observation` to combine metrics and tracing; configure OTLP sampling/resource attributes; propagate traces through HTTP clients and async/reactive contexts; distinguish JVM metrics from native metrics; and verify metrics, traces, and log correlation on the native executable without relying on a runtime Java agent.

## Official Documentation

- Spring Boot — Observability: https://docs.spring.io/spring-boot/reference/actuator/observability.html
- Spring Boot — Metrics: https://docs.spring.io/spring-boot/reference/actuator/metrics.html
- Spring Boot — Tracing: https://docs.spring.io/spring-boot/reference/actuator/tracing.html
- Spring Boot — Advanced Native Images Topics: https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html
- Spring Boot — Introducing GraalVM Native Images: https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html
- Micrometer — Observation Introduction: https://docs.micrometer.io/micrometer/reference/observation/introduction.html
- Micrometer — Observation Components: https://docs.micrometer.io/micrometer/reference/observation/components.html
- Micrometer — OTLP Registry: https://docs.micrometer.io/micrometer/reference/implementations/otlp.html
- Micrometer — High Cardinality Tags Detector: https://docs.micrometer.io/micrometer/reference/concepts/high-cardinality-tags-detector.html
