# Using auto-configured builders to preserve context propagation in Spring Boot

In the **Context propagation** chapter of the **SPRING_BOOT_OBSERVABILITY** module, a common cause of broken traces across services is manually constructing HTTP clients via constructors or raw builders, bypassing the customizers configured by Spring Boot. When that happens, outbound requests may remain uninstrumented, create no client span, and fail to inject W3C trace context into headers.

Spring Boot provides **auto-configured builders** such as `RestClient.Builder`, `RestTemplateBuilder`, and `WebClient.Builder`. Injecting them from the Spring Application Context lets clients receive application-wide settings, including observation/tracing instrumentation when the corresponding dependencies and configuration are enabled. For async tasks, a task executor builder paired with `ContextPropagatingTaskDecorator` helps capture/restore context across threads.

The goal is not merely building a working HTTP client. The goal is preserving **Trace ID, parent-child span relationships, and log correlation** across boundaries controlled by the application, while avoiding manual header copying or accidentally creating two instrumentation layers measuring the same call.

## 1. What does an auto-configured builder retain?

When an application uses Spring Boot Actuator and an appropriate Micrometer Tracing bridge, auto-configuration can prepare `ObservationRegistry`, conventions, and customizers for supported components. Spring-managed builders receive these configurations before building the client.

```text
Spring Application Context
    |
    +--> ObservationRegistry
    |       |
    |       +--> Observation handlers / tracing bridge
    |
    +--> RestClient.Builder / RestTemplateBuilder
    |       |
    |       +--> observation instrumentation
    |       +--> client observation convention/customizers
    |
    +--> WebClient.Builder
    |       |
    |       +--> observation instrumentation
    |       +--> reactive observation support
    |
    +--> ThreadPoolTaskExecutorBuilder
            |
            +--> TaskDecorator (when configured)

When the client sends a request inside an active context:
current span --> client observation/span --> inject traceparent
                                            |
                                            v
                                      downstream service
```

A builder is not a tracer or propagator. It is **the client assembly point**; the customizers/observation registry/tracing bridge supply the instrumentation. If the application has no tracing SDK/bridge/exporter, or the sampler drops traces, using an auto-configured builder still will not make spans appear in the backend.

| Component | Responsibility |
| --- | --- |
| Auto-configured builder | Holds Spring Boot customizers and applied settings |
| `ObservationRegistry` | Receives observations and dispatches to registered handlers |
| Micrometer Tracing bridge | Connects observations/spans to the tracer implementation |
| Propagator | Injects/extracts context, e.g., W3C `traceparent` |
| Exporter/collector | Sends and receives recorded spans |
| Tracing backend | Stores, searches, and displays traces per system capabilities |

## 2. Baseline dependencies and configuration

The example below assumes a Spring Boot application using Actuator and Micrometer Tracing with the OpenTelemetry bridge plus an OTLP exporter; versions should be managed consistently via the appropriate Spring Boot BOM.

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
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

If the application uses the reactive stack, add the appropriate WebFlux starter. Configuration example:

```yaml
spring:
  application:
    name: orders-service

management:
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
```

`probability: 1.0` is only for testing in a development environment to easily observe traces. Production must choose a sampling policy based on load, diagnostic needs, and cost. The OTLP/HTTP endpoint and port `4318` are illustrative only; in containers/Kubernetes, `localhost` usually does not point to a collector in another container. Verify the right protocol, DNS, TLS/auth, and collector receiver.

There is no need to create a second `ObservationRegistry` or `SdkTracerProvider` if Spring Boot already auto-configures the pipeline. A single configuration source ensures HTTP clients, server instrumentation, and custom observations share the same resource, sampler, propagator, and exporter.

## 3. Using `RestClient.Builder` provided by Spring Boot

In modern Spring Framework, `RestClient` is the synchronous HTTP API. Spring Boot auto-configures a `RestClient.Builder` for applications to inject and customize before building.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class InventoryClientConfiguration {

    @Bean
    RestClient inventoryRestClient(RestClient.Builder builder) {
        return builder
                .baseUrl("http://inventory-service")
                .build();
    }
}
```

Service using the assembled client:

```java
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
class InventoryGateway {
    private final RestClient client;

    InventoryGateway(RestClient inventoryRestClient) {
        this.client = inventoryRestClient;
    }

    InventoryResponse reserve(ReserveRequest request) {
        return client.post()
                .uri("/api/inventory/reservations")
                .body(request)
                .retrieve()
                .body(InventoryResponse.class);
    }
}
```

`ReserveRequest` and `InventoryResponse` are domain/DTO types defined by the application. When `reserve(...)` is called inside an active trace context with client observation/tracing enabled, the auto-configured client can:

1. Create a client observation/span for the HTTP request.
2. Use the active context as parent.
3. Inject trace context via the configured propagator, typically W3C `traceparent`.
4. Record duration/status and end the observation/span.

There is no need to read `Tracer.currentSpan()` and manually concatenate `traceparent` into headers. Client instrumentation is responsible for creating the span and injecting the right context.

## 4. Using `RestTemplateBuilder` to preserve observation configuration

For codebases still using `RestTemplate`, inject `RestTemplateBuilder` from the Spring context:

```java
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration(proxyBeanMethods = false)
class LegacyInventoryClientConfiguration {

    @Bean
    RestTemplate inventoryRestTemplate(RestTemplateBuilder builder) {
        return builder
                .rootUri("http://inventory-service")
                .build();
    }
}
```

`RestTemplateBuilder` can carry customizers registered by Boot, including observation configuration depending on version and dependencies. Avoid `new RestTemplate()` if the goal is to reuse the application's auto-configuration.

Be careful not to attach an additional custom interceptor recording the exact same HTTP metric/span if the builder already configures client observation. Doing so can create duplicate spans or measure duration twice. If you need interceptors for authentication, business correlation, or other non-sensitive headers, keep responsibilities separate and never overwrite trace headers managed by the propagator.

## 5. Using `WebClient.Builder` in reactive applications

With WebFlux, inject the auto-configured `WebClient.Builder`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
class PaymentClientConfiguration {

    @Bean
    WebClient paymentWebClient(WebClient.Builder builder) {
        return builder
                .baseUrl("http://payment-service")
                .build();
    }
}
```

Calling downstream through this client:

```java
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
class PaymentGateway {
    private final WebClient client;

    PaymentGateway(WebClient paymentWebClient) {
        this.client = paymentWebClient;
    }

    Mono<PaymentResponse> authorize(PaymentRequest request) {
        return client.post()
                .uri("/api/payments/authorize")
                .bodyValue(request)
                .retrieve()
                .bodyToMono(PaymentResponse.class);
    }
}
```

`PaymentRequest` and `PaymentResponse` are application DTOs. In reactive pipelines, context should not be treated like a ThreadLocal fixed to one thread. Reactor has its own context mechanism; corresponding instrumentation must integrate context propagation so trace context follows subscriptions and operators. Using the auto-configured `WebClient.Builder` preserves observation integration, yet code still needs to maintain the reactive chain and avoid offloading work to incompatible executors or calling `.block()` arbitrarily in reactive flows.

If you need multiple distinct `WebClient` instances, you can create multiple beans from the auto-configured builder with different base URLs/customizers. Do not call raw `WebClient.builder()` where Spring Boot customizers are needed if the goal is to preserve observation/tracing configuration.

## 6. What happens when creating raw builders manually?

Example that easily bypasses auto-configuration:

```java
// Do not use this approach when you need to preserve Spring Boot customizers.
RestClient client = RestClient.builder()
        .baseUrl("http://inventory-service")
        .build();

WebClient webClient = WebClient.builder()
        .baseUrl("http://payment-service")
        .build();
```

Static builder APIs can construct HTTP-valid clients, yet do not automatically ensure they receive `RestClientCustomizer`, `RestTemplateCustomizer`, or `WebClientCustomizer` beans registered by Spring Boot. Consequences can include:

- No observation for the HTTP call.
- No client span or outbound trace headers.
- HTTP client metrics missing, even while server metrics exist.
- Downstream logs cannot correlate Trace ID with upstream.
- Dashboards show slow HTTP requests, yet traces lack outbound spans to pinpoint the dependency.

This does not mean raw builders can never be instrumented. You can manually configure the appropriate observation registry/customizers/interceptors. However, when using Spring Boot auto-configuration, injecting the builder is the clear path to inherit centralized configuration.

## 7. Using builders properly when multiple clients exist

Do not mutate a shared builder across multiple places after creating a client, as configuration changes can unexpectedly affect other beans. Some Spring Boot builders are provided with prototype scope or support cloning to create independent configurations; use the approach matching your running builder/version.

Example creating two clients with different base URLs:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class DownstreamClients {

    @Bean
    RestClient inventoryClient(RestClient.Builder builder) {
        return builder.clone()
                .baseUrl("http://inventory-service")
                .build();
    }

    @Bean
    RestClient paymentClient(RestClient.Builder builder) {
        return builder.clone()
                .baseUrl("http://payment-service")
                .build();
    }
}
```

If the builder is provided by Spring as a prototype, each injection point may already receive its own instance; `clone()` still communicates the intent to create isolated configurations. Verify the client builder's `clone()` API in your Spring Framework version. Never hold a mutable builder in a static field or mutate it arbitrarily after multiple beans have used it.

## 8. Preserving context when switching to an executor

HTTP client builders preserve instrumentation on HTTP calls. However, when a request thread hands work off to a thread pool, **cross-thread context propagation is a separate concern**. Injecting `RestClient.Builder` or `WebClient.Builder` alone does not automatically copy context to an executor.

Spring Framework provides `ContextPropagatingTaskDecorator` in versions supporting Micrometer Context Propagation. It can be paired with Spring Boot's `ThreadPoolTaskExecutorBuilder`:

```java
import org.springframework.boot.task.ThreadPoolTaskExecutorBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
class BackgroundTaskConfiguration {

    @Bean
    ThreadPoolTaskExecutor orderExecutor(
            ThreadPoolTaskExecutorBuilder builder) {
        return builder
                .corePoolSize(4)
                .maxPoolSize(8)
                .queueCapacity(100)
                .taskDecorator(new ContextPropagatingTaskDecorator())
                .build();
    }
}
```

The auto-configured builder retains Boot-managed pool/customizer settings; context propagation is explicitly added via the task decorator. Tasks must actually be submitted to the `orderExecutor` bean:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
class OrderAsyncService {
    private final Executor orderExecutor;

    OrderAsyncService(@Qualifier("orderExecutor") Executor orderExecutor) {
        this.orderExecutor = orderExecutor;
    }

    CompletableFuture<Void> persistAsync() {
        return CompletableFuture.runAsync(
                this::persistOrder,
                orderExecutor);
    }

    private void persistOrder() {
        // Context is restored if the matching accessors/integrations are registered.
    }
}
```

If multiple `Executor` beans exist in the application, use `@Qualifier("orderExecutor")` at the injection point to ensure the right bean is selected; or inject the exact `ThreadPoolTaskExecutor` type with the matching bean name. The abbreviated snippet assumes only one matching executor exists.

`ContextPropagatingTaskDecorator` does not start a new trace, does not send headers automatically, and does not extend a span's lifecycle indefinitely. It captures/restores registered context accessors when tasks are submitted/run. For background work starting after the request ends, evaluate semantics: starting an independent trace/job span and linking it to the prior workflow via correlation/links may be more appropriate than using an already-ended parent span.

## 9. Why not copy `traceparent` manually?

A common temptation is reading the Trace ID from `Tracer`, assembling a header string, and adding it to every HTTP request. This approach is incomplete because:

- The W3C header has **Trace ID, parent Span ID, and trace flags**; each client call needs an appropriate new span ID, not just a copied Trace ID.
- Sampling decisions and parent relationships must stay consistent.
- There may be `tracestate`, baggage, and other propagators depending on the stack.
- Headers from external clients must be validated against the specification and trust boundaries.
- Retries/redirects/async calls have different lifecycles; manual header copying can keep the wrong parent span.

With instrumented HTTP clients, let the propagator inject/extract. An illustrative `traceparent`:

```text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
             ^^ -------------------------------- ---------------- ^^
             |          trace-id (32 hex)       parent-id (16 hex) flags
             version
```

When the downstream service receives the request, it creates a new span with the same Trace ID if the context is accepted and continues the same trace; the parent ID in the header is the client's Span ID. Never hardcode the header above into application code.

## 10. Verifying propagation end-to-end

To prove an auto-configured builder preserves tracing, do not just check that the bean initializes. Run a two-service scenario in a test environment:

```text
Client
  |
  v
orders-service
  HTTP server span (Trace ID = T)
    |
    +-- order.confirm
          |
          +-- RestClient inventory call
                 HTTP client span (Trace ID = T, Span ID = C)
                      |
                      v
               inventory-service
                 HTTP server span
                 (Trace ID = T, Parent Span ID = C)
```

Verification steps:

1. **Check dependencies/bridge:** Actuator, Micrometer Tracing bridge, SDK/exporter, and collector have compatible versions.
2. **Check injected builder:** the client bean is built from `RestClient.Builder`, `RestTemplateBuilder`, or `WebClient.Builder` in the Spring context.
3. **Create a request within a trace context:** call an `orders-service` endpoint so the server span has an active context.
4. **Call downstream:** use the built client bean, without creating a new client outside the Spring context.
5. **Inspect the trace backend:** verify both the client span and downstream server span exist with the same Trace ID and appropriate parent-child relationship.
6. **Check logs:** if MDC correlation is configured, logs from both services carry matching Trace ID and Span ID.
7. **Test downstream errors:** verify status/error, span duration, and logs help identify the right dependency.
8. **Test async separately:** submit a task through a decorated executor, verify context inside the worker, and call the HTTP client from the worker if applicable.

If no trace appears, check in order:

| Symptom | Likelihood | What to check |
| --- | --- | --- |
| Server span exists but no client span | Raw client builder or missing instrumentation | Was builder injected? Is observation registry attached to client? |
| Client span exists yet downstream has new Trace ID | Header not injected/extracted or proxy alters headers | Propagator, HTTP client/server instrumentation, gateway |
| Client span not exported | Sampling, processor/exporter, or collector error | SDK, sampled decision, OTLP receiver/queue |
| Trace exists yet logs lack Trace ID | MDC/logging correlation not configured | Encoder/pattern and active scope |
| Sync request has context, worker thread does not | Executor lacks context propagation | TaskDecorator, context accessors, right executor bean |
| Metrics exist yet traces are missing | Metric handler runs independently, tracing bridge/sampling issue | Tracing pipeline; do not infer from metrics endpoint |

A missing trace due to sampling does not prove the builder was not auto-configured. To test propagation, use a test environment with an appropriate sampling policy and verify both client and server spans.

## 11. Avoiding duplicate instrumentation and high cardinality

An auto-configured builder may already attach observation instrumentation to the HTTP client. If you also add an interceptor or filter creating a span for the same call, traces may contain two spans measuring the exact same scope. Before instrumenting manually, inventory:

- Which HTTP clients are created by Spring Boot and receive customizers?
- Which libraries are already auto-instrumented by an OpenTelemetry Java agent?
- Does a custom `Observation` wrap a **business** boundary or merely duplicate the entire HTTP call?
- Are any interceptors creating extra spans with no distinct meaning?

Custom observations remain useful to represent boundaries such as `inventory.reserve` or `payment.authorize`, while the client span measures the actual network call. The two layers complement each other because they answer different questions.

Tags/attributes must be controlled. Use low-cardinality values like `provider=bank_a/bank_b`, `outcome=success/error`; avoid `traceId`, `orderId`, email, raw URLs, or exception messages as metric labels. Trace ID has very high cardinality; logs/tracing backends are the right place to look up a specific request under proper access controls.

Propagation does not mean stuffing the entire payload into baggage. Only propagate small allowlisted metadata, never tokens, cookies, customer data, or request bodies. Oversized headers can be rejected by proxies/gateways.

## 12. Case study exercise

An `orders-service` uses Spring Boot with a tracing bridge. Its controller has a server span and logs contain Trace IDs. The application calls `inventory-service` using two different clients:

```java
@Bean
RestClient inventoryClient(RestClient.Builder builder) {
    return builder.baseUrl("http://inventory-service").build();
}

// In an older service:
private final RestClient rawClient =
        RestClient.builder()
                .baseUrl("http://inventory-service")
                .build();
```

The team observes that calls from the `inventoryClient` bean have a client span and downstream shares the same Trace ID, whereas calls from `rawClient` have no client span and inventory logs use a new Trace ID.

**Question:** Why do the two calls behave differently? Should you quickly fix `rawClient` by manually adding a `traceparent` header?

**Analysis hints:**

1. The `inventoryClient` bean was built from the Spring-injected builder, so it inherits Boot's customizers and observation instrumentation.
2. `rawClient` uses the static builder, bypassing customizers attached to the Spring context; it may neither create a client observation/span nor inject trace context.
3. Do not manually copy `traceparent`: you need a new client span, accurate parent ID, flags/tracestate, and a compatible propagator.
4. Fix it by constructing the client via the auto-configured builder, checking the bridge/registry, and verifying the trace end-to-end.
5. If a raw client must be created outside Spring, the owner must explicitly configure observation/tracing instrumentation on that client and verify propagation.

### Completion checklist

| Test | Expected result |
| --- | --- |
| Inject auto-configured `RestClient.Builder` | Client bean inherits Spring Boot customizers |
| Inject `RestTemplateBuilder` | `RestTemplate` receives Boot-managed builder configuration |
| Inject `WebClient.Builder` in WebFlux | Client retains observation integration/appropriate reactive context |
| Use unconfigured raw builder | Does not receive customizers/propagation by default |
| Call downstream inside current span | Client span uses parent trace context if instrumented |
| Downstream receives valid `traceparent` | Server span has same Trace ID and right parent |
| Offload work to executor | Context preserved when task uses decorated executor with matching accessors |
| Sampling drops trace | Not mistaken for builder bug or propagation bug |
| Concurrent HTTP agent instrumentation | No unintended duplicate spans for the same boundary |
| Metrics/logs/traces verified | Bounded tags, correlated logs, traces exported when sampled/exported |

**Takeaway:** When Spring Boot has configured observability, **inject auto-configured builders from the Application Context** to construct `RestClient`, `RestTemplate`, or `WebClient`. This preserves observation/tracing customizers and lets the propagator handle trace headers. For work switching threads, a dedicated context-propagating executor is required; HTTP builders do not replace task decorators. Verify client/server spans, Trace IDs, logs, and exporters end-to-end to ensure traces never break between services.
