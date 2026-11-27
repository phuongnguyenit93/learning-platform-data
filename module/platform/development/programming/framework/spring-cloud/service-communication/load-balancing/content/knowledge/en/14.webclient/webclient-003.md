# ReactorLoadBalancerExchangeFilterFunction in the Filter Chain

When `WebClient` sends a request to `http://inventory-service`, the `ExchangeFilterFunction` chain can intercept it before it goes through the HTTP connector. **`ReactorLoadBalancerExchangeFilterFunction`** is the filter that integrates Spring Cloud LoadBalancer with WebClient: it takes a URI whose hostname is a **service ID**, obtains a `ServiceInstance` from the corresponding selector, and forwards the request to the selected instance's URI.

The key point of this lesson is the **position of the filter in the chain**, not just how to add an annotation. Authentication, context-propagation, and logging filters can run *before or after* resolving the service ID into an actual address. This changes the URL seen by each filter, the scope of measured durations, how requests are logged, and the boundary between a single logical call and retry attempts.

In the **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING** module, WebClient is one of the options for business-synchronous communication whose I/O executes under a reactive model, alongside RestClient and OpenFeign. The principles of discovery, health checks, routing, retries, and timeouts still need to be understood independently of which HTTP client is used.

## 1. What Does WebClient Use a Filter Chain For?

`WebClient` is an HTTP client with a reactive API in Spring WebFlux. `ExchangeFilterFunction` has the conceptual signature:

~~~java
Mono<ClientResponse> filter(
        ClientRequest request,
        ExchangeFunction next
);
~~~

- `ClientRequest` represents the method, URL, headers, cookies, attributes, and request body.
- `ExchangeFunction next` represents the remainder of the filter chain or the HTTP execution layer.
- `Mono<ClientResponse>` describes the asynchronous result of the HTTP exchange.
- Each filter can build a new request with `ClientRequest.from(request)`, invoke `next.exchange(...)`, and handle responses, errors, or cancellations in the reactive chain.

Example flow:

~~~mermaid
flowchart LR
    A["OrderService"] --> B["WebClient"]
    B --> C["Correlation filter"]
    C --> D["Authentication filter"]
    D --> E["ReactorLoadBalancerExchangeFilterFunction"]
    E --> F["HTTP logging filter"]
    F --> G["ExchangeFunction / connector"]
    G --> H["Inventory replica"]
~~~

The diagram illustrates the order when filters are registered in that sequence. **Not every WebClient has the same filters**, nor are framework-supplied auto-configured filters guaranteed to appear in the exact same position across all release trains. When using `@LoadBalanced`, Spring Cloud automatically adds the integration to the builder; when calling `.filter(lbFunction)` manually, the application is responsible for its position.

### Why Does WebClient Differ from RestTemplate Here?

| Aspect | RestTemplate | WebClient |
|---|---|---|
| HTTP client extension point | `ClientHttpRequestInterceptor` | `ExchangeFilterFunction` |
| Typical return value | Object or `ResponseEntity` after a blocking call | `Mono<T>`, `Flux<T>`, or `Mono<ClientResponse>` |
| How to continue the chain | `execution.execute(request, body)` | `next.exchange(request)` |
| Suitable context-propagation mechanism | ThreadLocal/MDC in controlled blocking flows | Reactor `Context` and reactive instrumentation |
| LoadBalancer integration | Interceptor/`@LoadBalanced RestTemplate` | `ReactorLoadBalancerExchangeFilterFunction` or `@LoadBalanced` builder |

Using WebClient inside Spring MVC is valid; you do not have to convert all controllers to WebFlux. However, do not call `block()` on an event-loop thread, as this can cause thread starvation, bottlenecks, or runtime errors.

## 2. From Service ID to ServiceInstance: What Does the Filter Do?

Suppose discovery provides:

| Service ID | Instance ID | Host | Port |
|---|---|---|---:|
| `inventory-service` | `inventory-a` | `127.0.0.1` | 8081 |
| `inventory-service` | `inventory-b` | `127.0.0.1` | 8082 |

Business code builds a logical URL:

~~~text
http://inventory-service/api/stock/SKU-100
~~~

When the load-balancing filter runs, it reads the hostname `inventory-service` from the URL, asks Spring Cloud LoadBalancer to select an instance, and constructs the URL based on that instance:

~~~text
Original ClientRequest:
    GET http://inventory-service/api/stock/SKU-100

ReactorLoadBalancerExchangeFilterFunction:
    service ID = inventory-service
    -> ServiceInstanceListSupplier
    -> LoadBalancer selects inventory-b

ClientRequest forwarded to HTTP connector:
    GET http://127.0.0.1:8082/api/stock/SKU-100
~~~

~~~mermaid
sequenceDiagram
    participant B as Business
    participant F as WebClient filter chain
    participant L as Reactor LoadBalancer
    participant S as Instance supplier
    participant I as Inventory instance B

    B->>F: GET http://inventory-service/api/stock
    F->>L: Select ServiceInstance for inventory-service
    L->>S: Fetch eligible instances
    S-->>L: [inventory-a, inventory-b]
    L-->>F: inventory-b :8082
    F->>I: GET http://127.0.0.1:8082/api/stock
    I-->>F: 200 + JSON
    F-->>B: Mono<ClientResponse> / body
~~~

The default algorithm is typically Round Robin; Random or a custom strategy can be configured via `@LoadBalancerClient`. The WebClient filter **does not decide on its own** about health, zones, or weights: the candidate list and algorithm come from the service ID's LoadBalancer context.

If there is only one instance, the filter always picks that instance. If there are no candidates, load balancing cannot pick a backend. In current integrations, the request can be represented by a `503 Service Unavailable` response, though how the error surfaces at the caller layer depends on the version and how `retrieve()` or `exchangeToMono()` is used.

## 3. Prerequisites for ReactorLoadBalancerExchangeFilterFunction to Work

The caller needs the following components:

1. `spring-boot-starter-webflux` (or corresponding Spring WebFlux) for WebClient and the reactive HTTP stack.
2. `spring-cloud-starter-loadbalancer` for Spring Cloud LoadBalancer and its HTTP client integration.
3. A list of `ServiceInstance`s for the service ID, obtained from a discovery registry, `SimpleDiscoveryClient`, or a custom supplier.
4. A WebClient configured to use the LoadBalancer filter.
5. Real backends listening on the hosts/ports provided by discovery.

Example Maven dependencies in a Spring Boot application using a compatible Spring Cloud BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>
</dependencies>
~~~

If the application also has `spring-boot-starter-web`, WebClient can still be used in the service layer. Having WebClient on the classpath does not by itself cause the application to run on a reactive server instead of Spring MVC.

Manage Spring Boot/Spring Cloud versions using a compatible combination. Do not copy an arbitrary library version just because a snippet compiles in another project.

## 4. Approach 1: Using `@LoadBalanced WebClient.Builder`

This is the convenient and commonly used approach in Spring Cloud applications:

~~~java
package com.example.order.config;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class WebClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }

    @Bean
    WebClient inventoryWebClient(
            @LoadBalanced WebClient.Builder loadBalancedBuilder) {

        return loadBalancedBuilder
                .clone()
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

`@LoadBalanced` marks the builder so Spring Cloud integrates the LoadBalancer filter. `clone()` reduces the risk of mutating the configuration of a builder shared with another WebClient. You do not need to manually add `ReactorLoadBalancerExchangeFilterFunction` again to this builder.

Caller:

~~~java
package com.example.order.inventory;

import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class InventoryClient {

    private final WebClient inventoryWebClient;

    public InventoryClient(WebClient inventoryWebClient) {
        this.inventoryWebClient = inventoryWebClient;
    }

    public Mono<InventoryResponse> findStock(String sku) {
        return inventoryWebClient.get()
                .uri("/api/stock/{sku}", sku)
                .retrieve()
                .bodyToMono(InventoryResponse.class);
    }

    public record InventoryResponse(String sku, int available) {
    }
}
~~~

The method returns `Mono<InventoryResponse>` and only executes the request when subscribed to. Calling `findStock(sku)` without subscribing or having the framework consume the Mono will not necessarily send a request.

**Note on bean injection:** if the system has multiple WebClient beans, use `@Qualifier("inventoryWebClient")` on the constructor to pick the right client. Do not rely on accidental bean ordering.

### When to Use This Approach?

When you only need to use a service ID as a logical URL and do not need fine-grained control over the LoadBalancer filter's exact position in the chain, `@LoadBalanced WebClient.Builder` is a clean solution. Additional features like authentication, correlation, and logging can still use `.filter(...)`, though the overall ordering should be verified if it affects your requirements.

## 5. Approach 2: Attaching `ReactorLoadBalancerExchangeFilterFunction` Manually

If you need control over filter order, inject the `ReactorLoadBalancerExchangeFilterFunction` provided by Spring Cloud and attach it to WebClient as an `ExchangeFilterFunction`.

**This is an alternative to Approach 1; do not use both simultaneously on the same builder.**

~~~java
package com.example.order.config;

import org.springframework.cloud.client.loadbalancer.reactive.ReactorLoadBalancerExchangeFilterFunction;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class ExplicitLoadBalancerConfiguration {

    @Bean("inventoryWebClient")
    WebClient inventoryWebClient(
            WebClient.Builder ordinaryBuilder,
            ReactorLoadBalancerExchangeFilterFunction lbFunction) {

        return ordinaryBuilder
                .clone()
                .baseUrl("http://inventory-service")
                .filter(lbFunction)
                .build();
    }
}
~~~

The snippet above intentionally takes the plain `WebClient.Builder ordinaryBuilder` provided by Spring Boot, **not a builder annotated with `@LoadBalanced`**. If another builder bean in the system carries that annotation, use an explicit qualifier or configure a separate builder to avoid attaching the LoadBalancer filter twice.

A variant with additional filters:

~~~java
@Bean("inventoryWebClient")
WebClient inventoryWebClient(
        WebClient.Builder builder,
        ReactorLoadBalancerExchangeFilterFunction lbFunction,
        ExchangeFilterFunction correlationFilter,
        ExchangeFilterFunction logicalRequestLogFilter,
        ExchangeFilterFunction physicalRequestLogFilter) {

    return builder.clone()
            .baseUrl("http://inventory-service")
            .filter(correlationFilter)
            .filter(logicalRequestLogFilter)
            .filter(lbFunction)
            .filter(physicalRequestLogFilter)
            .build();
}
~~~

Assuming these are separate `ExchangeFilterFunction` beans defined by the application. Design intent:

- `correlationFilter` adds a request identification header from Reactor Context.
- `logicalRequestLogFilter` sees the URL containing the service ID before LoadBalancer.
- `lbFunction` selects an instance and rewrites the URL to the target address.
- `physicalRequestLogFilter` can see the physical URL of the selected instance.

If the application needs to protect internal addresses from logs, do not write physical hosts or sensitive data into production logs. Prefer tracing/lifecycle metrics and proper redaction policies.

## 6. What Does Filter Ordering Change?

`WebClient.Builder.filter(...)` registers filters into the chain; typically outer filters are called first, and subsequent filters are called when `next.exchange(...)` executes.

Example configuration:

~~~text
F1 = correlation
F2 = logical request logging
F3 = ReactorLoadBalancerExchangeFilterFunction
F4 = physical request logging
F5 = HTTP connector
~~~

Sequence before receiving the response:

~~~text
Business code
  -> F1: add X-Correlation-Id
    -> F2: see URL http://inventory-service/...
      -> F3: select ServiceInstance
        -> F4: see URL http://127.0.0.1:8082/...
          -> F5: perform network I/O
~~~

Responses, errors, and cancellations flow back toward outer filters depending on the Reactor operators attached by each filter. This affects:

| Position | Visible URL | Measurement Semantics |
|---|---|---|
| Before LoadBalancer | Logical URL containing service ID | Can observe LoadBalancer selection and subsequent network I/O |
| After LoadBalancer | URL resolved to host/port | Can measure transport for a single attempt, depending on retry placement |
| Wrapping outside auth filter | Request gets token added at a downstream step | May include token acquisition time if auth filter makes network calls |
| Inside auth filter | Request usually already carries authentication info | Does not necessarily include token acquisition time |

The actual sequence may also include filters registered by Spring Boot, observability, or other frameworks. Do not assume an optimal order solely from snippet order; verify with integration tests or controlled logging.

## 7. Writing a Correlation ID Filter Properly with Reactor Context

With WebClient, you should not rely by default on `MDC.get("correlationId")` to propagate request context. MDC is typically tied to `ThreadLocal`, whereas Reactor signals can execute across different threads. Reactor `Context` propagates with the subscription and is the right choice for asynchronous context.

Example filter:

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import reactor.core.publisher.Mono;

@Bean
ExchangeFilterFunction correlationIdFilter() {
    return (request, next) -> Mono.deferContextual(context -> {
        String correlationId =
                context.getOrDefault("correlationId", "");

        ClientRequest updated = ClientRequest.from(request)
                .headers(headers -> {
                    if (!correlationId.isBlank()) {
                        headers.set(
                                "X-Correlation-Id",
                                correlationId
                        );
                    }
                })
                .build();

        return next.exchange(updated);
    });
}
~~~

How to invoke it:

~~~java
public Mono<InventoryResponse> getInventory(
        String sku,
        String correlationId) {

    return inventoryWebClient.get()
            .uri("/api/stock/{sku}", sku)
            .retrieve()
            .bodyToMono(InventoryResponse.class)
            .contextWrite(context ->
                    context.put("correlationId", correlationId)
            );
}
~~~

In this example, the filter executes within a subscription whose `Context` contains the `correlationId` key. `Mono.deferContextual(...)` reads the value **at subscription time**, avoiding capturing context too early at assembly time.

Principles to uphold:

1. Only propagate correlation IDs validated/sanitized at a trusted boundary.
2. Do not generate a new ID on every retry if the goal is to correlate attempts back to the same logical request.
3. Do not treat `X-Correlation-Id` as proof of authentication or access rights.
4. Do not copy all inbound headers blindly to outbound requests.
5. If Micrometer Tracing/OpenTelemetry is enabled, let instrumentation manage `traceparent` and standard trace headers.

If the filter does not see the key, check `contextWrite` ordering, intermediate publishers, and subscriber placement. `Context` flows along the subscription rather than being a global variable shared across all requests.

## 8. Asynchronous Authentication Filter Without Blocking the Event Loop

If `inventory-service` requires a Bearer token, a filter can call a token provider returning `Mono<String>`. Use an OAuth2 client or workload identity mechanism suited to your system architecture; do not hardcode tokens in source code.

Example interface for the lab:

~~~java
public interface InventoryTokenProvider {
    Mono<String> accessToken();
}
~~~

Filter:

~~~java
@Bean
ExchangeFilterFunction inventoryAuthenticationFilter(
        InventoryTokenProvider tokenProvider) {

    return (request, next) ->
            tokenProvider.accessToken()
                    .flatMap(token -> {
                        ClientRequest authorized =
                                ClientRequest.from(request)
                                        .headers(headers ->
                                                headers.setBearerAuth(token)
                                        )
                                        .build();

                        return next.exchange(authorized);
                    });
}
~~~

This is a **reactive token provider** pattern: the implementation must handle token issuance, caching, expiration, and authorization server errors itself. In real systems, `ReactiveOAuth2AuthorizedClientManager` with an appropriate `client_credentials` configuration can be used; do not assume a blocking manager is safe to invoke directly on the event loop.

If an HTTP call is needed to obtain a token, perform it asynchronously via a client **that does not carry the inventory load-balancing filter**, unless the token endpoint is also a discovered service. Avoid circular dependencies where the inventory WebClient needs a token from a WebClient that itself requires that same token.

### Do Not Leak Bearer Tokens to Other Services

Attach the authentication filter to a WebClient dedicated to `inventory-service` or use a policy that selects credentials based on verified targets. If a WebClient has a dynamic base URL, a target-unaware token filter could send the inventory token to an unauthorized hostname.

A controllable design looks like:

~~~text
inventoryWebClient:
    correlationFilter -> inventoryAuthFilter -> lbFilter

paymentWebClient:
    correlationFilter -> paymentAuthFilter -> lbFilter

publicExternalWebClient:
    correlationFilter -> (do not attach internal service token)
~~~

Do not use `ClientRequest.url()` unchecked to trust a user-supplied hostname. For dynamic URLs, enforce allowlists, SSRF protections, and token decisions at the application boundary, not only inside the filter.

## 9. Logging Filter: Distinguishing HTTP Responses from Error Signals

A timing filter can use `Mono.defer` to start measuring at subscription time:

~~~java
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import reactor.core.publisher.Mono;

private static final Logger LOG =
        LoggerFactory.getLogger("outbound.inventory");

@Bean
ExchangeFilterFunction safeOutboundLoggingFilter() {

    return (request, next) -> Mono.defer(() -> {
        long started = System.nanoTime();
        String method = request.method().name();
        String host = request.url().getHost();

        return next.exchange(request)
                .doOnNext(response -> {
                    long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - started
                    );

                    LOG.info(
                            "outbound_http method={} targetHost={} status={} elapsedMs={}",
                            method,
                            host,
                            response.statusCode().value(),
                            elapsedMs
                    );
                })
                .doOnError(error -> {
                    long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - started
                    );

                    LOG.warn(
                            "outbound_http_failed method={} targetHost={} errorType={} elapsedMs={}",
                            method,
                            host,
                            error.getClass().getSimpleName(),
                            elapsedMs
                    );
                });
    });
}
~~~

This is an illustrative `@Bean` factory method inside a `@Configuration` class; `LOG` must be a static field of the class containing the bean.

Key points to understand:

- An HTTP 500 or 503 response is still a normal **ClientResponse** at the `ExchangeFilterFunction` layer; it does not necessarily trigger `doOnError` right here.
- `retrieve()` later converts 4xx/5xx statuses into `WebClientResponseException` by default if the caller decodes the body.
- Connection, DNS, timeout, or filter exceptions can enter `doOnError`.
- Cancellation may not trigger `doOnNext` or `doOnError`; if you need to measure all completions, use `doFinally` and distinguish `SignalType`.
- Do not read the response body inside a logging filter unless you thoroughly understand `DataBuffer` consumption, replay, backpressure, and memory costs.

Do not log full URL queries, request bodies, `Authorization`, cookies, or tokens. Name metrics/labels by route template where possible to avoid excessive cardinality.

## 10. LoadBalancer Filter, Health Checks, and Instance Selection Policies

`ReactorLoadBalancerExchangeFilterFunction` does not contain all discovery/health-check logic internally. It delegates instance selection to Spring Cloud LoadBalancer. The processing chain can look like:

~~~mermaid
flowchart LR
    A["ServiceInstance supplier from Discovery"] --> B["Cache (if enabled)"]
    B --> C["Health / zone / hint filtering"]
    C --> D["Candidate ServiceInstances"]
    D --> E["Round Robin / Random / custom ReactorLoadBalancer"]
    E --> F["ReactorLoadBalancerExchangeFilterFunction"]
    F --> G["HTTP connector"]
~~~

If `ServiceInstanceListSupplier` returns only one instance, WebClient will always use that instance regardless of Round Robin or Random algorithms. If all instances are filtered out, how responses behave depends on the supplier's and filter's fallback mechanisms.

Do not confuse the three kinds of components:

| Component | Input | Responsibility |
|---|---|---|
| `ExchangeFilterFunction` | `ClientRequest`/`ClientResponse` | Intercepts WebClient HTTP requests/responses |
| `ServiceInstanceListSupplier` | Service ID and LoadBalancer request | Supplies/filters the list of candidate instances |
| `ReactorLoadBalancer<ServiceInstance>` | Instance list and selection request | Selects one instance from the candidate set |

For example, `HealthCheckServiceInstanceListSupplier` is a **supplier**, not a WebClient `ExchangeFilterFunction` that you attach directly to `WebClient.Builder`.

Zone, hint, weighted selection, and retry-aware suppliers also belong to Spring Cloud's selection mechanism, not HTTP filters that can be reordered arbitrarily within WebClient.

## 11. Retries: One Logical Call May Select an Instance Multiple Times

WebClient returns a publisher. For standard requests, each subscription or re-subscription can start a new HTTP exchange, including instance selection. Example:

~~~java
import java.time.Duration;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import reactor.util.retry.Retry;

public Mono<InventoryResponse> findStockWithBoundedRetry(String sku) {
    return inventoryWebClient.get()
            .uri("/api/stock/{sku}", sku)
            .retrieve()
            .bodyToMono(InventoryResponse.class)
            .retryWhen(
                    Retry.backoff(2, Duration.ofMillis(150))
                            .filter(error ->
                                    error instanceof WebClientRequestException
                            )
            );
}
~~~

Two retries mean at most three attempts (the initial call plus two retries) if consecutive errors match the filter. This example only retries `WebClientRequestException`; it **does not automatically retry 503 responses** converted by `retrieve()` into `WebClientResponseException`.

Notes:

- A retry may pick **the same failed instance again** without an appropriate retry-aware/avoid-previous-instance mechanism.
- If Spring Cloud LoadBalancer also enables internal retries, adding `retryWhen` on WebClient can result in multi-layer retries, multiplying request counts beyond expectations.
- Retrying business POST/PUT operations with side effects requires idempotency policies and deadlines; do not blindly apply GET examples to payments.
- A token acquisition filter may run again when the publisher is re-subscribed. The token provider needs caching and throttling to avoid duplicate token requests.
- Re-subscribing to a streaming request body is not automatically safe; ensure payloads are replayable before retrying.

This example illustrates retry scoping only. In production, include error classification, an overall deadline, backoff/jitter, and metrics distinguishing logical requests from HTTP attempts.

## 12. Where Do Timeouts Sit When Requests Cross Multiple Filters?

In WebClient using Reactor Netty, connect timeout and response timeout can be configured on the HTTP transport:

~~~java
import java.time.Duration;
import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 500)
        .responseTimeout(Duration.ofSeconds(2));

WebClient client = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .filter(lbFunction)
        .baseUrl("http://inventory-service")
        .build();
~~~

Here `lbFunction` is the `ReactorLoadBalancerExchangeFilterFunction` bean provided by Spring Cloud. This is a standalone snippet and does not use `@LoadBalanced` at the same time. In a Spring Boot application with an auto-configured `WebClient.Builder`, integrate the connector via Boot's builder/customizer when you want to retain observation/tracing customization.

Distinguish between:

- **Connect timeout**: waiting to establish the TCP connection.
- **Response timeout**: waiting for a response under Reactor Netty semantics.
- **Reactive `Mono.timeout(...)`**: maximum duration for the publisher at the operator's position; can encompass filters, instance selection, token lookup, and retries if placed appropriately.
- **Discovery timeout**: limit when querying the instance list if supported by the discovery mechanism.

For example, to limit the entire publisher to 3 seconds:

~~~java
return inventoryWebClient.get()
        .uri("/api/stock/{sku}", sku)
        .retrieve()
        .bodyToMono(InventoryResponse.class)
        .timeout(Duration.ofSeconds(3));
~~~

When `retryWhen` is present, the placement of `timeout` relative to `retryWhen` changes whether it bounds each attempt or the total across attempts. For a total deadline, wrap the entire retry chain with the timeout operator and test actual timing behavior.

## 13. Practice: Two Inventory Replicas and LoadBalanced WebClient

To observe the filter chain in action, build a simple lab:

~~~text
order-service :8080
  |
  | WebClient "http://inventory-service/whoami"
  v
Spring Cloud LoadBalancer
  |
  +--- inventory instance 1 :8081
  |
  +--- inventory instance 2 :8082
~~~

On the caller, use `SimpleDiscoveryClient`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: order-service

  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

On `inventory-service`, add an endpoint returning the current port:

~~~java
import java.util.Map;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InstanceController {

    private final Environment environment;

    public InstanceController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/whoami")
    public Map<String, String> whoAmI() {
        return Map.of(
                "instance", "inventory:" +
                        environment.getProperty("server.port", "unknown")
        );
    }
}
~~~

Run two inventory processes from the same codebase on ports 8081 and 8082 using `--server.port=8081` and `--server.port=8082`. Call `http://localhost:8081/whoami` and `http://localhost:8082/whoami` directly first to ensure both backends work.

On the caller, define the WebClient using either approach above. Example reactive controller:

~~~java
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@RestController
public class InventoryProxyController {

    private final WebClient inventoryWebClient;

    public InventoryProxyController(WebClient inventoryWebClient) {
        this.inventoryWebClient = inventoryWebClient;
    }

    @GetMapping("/proxy/whoami")
    public Mono<Map> proxyWhoAmI() {
        return inventoryWebClient.get()
                .uri("/whoami")
                .retrieve()
                .bodyToMono(Map.class);
    }
}
~~~

The controller above is suitable for a lab only; in production code, use a strongly typed DTO instead of raw `Map`.

Send 20 requests in PowerShell:

~~~powershell
1..20 | ForEach-Object {
    Invoke-RestMethod "http://localhost:8080/proxy/whoami"
}
~~~

If the instance list is stable and Round Robin is used, you will commonly see ports 8081 and 8082 alternate across selections; actual order/evenness can be affected by concurrency, retries, or caching. If Random is configured, the same port may repeat consecutively.

### Observing Logical URL and Physical URL

When using manual filter attachment, add two logging filters on either side of `lbFunction`:

~~~java
@Bean
ExchangeFilterFunction logicalUrlLog() {
    return (request, next) -> {
        // For diagnostics only, do not log query strings containing sensitive data.
        System.out.println("logical host = " + request.url().getHost());
        return next.exchange(request);
    };
}

@Bean
ExchangeFilterFunction physicalUrlLog() {
    return (request, next) -> {
        System.out.println("physical host = " + request.url().getHost()
                + ":" + request.url().getPort());
        return next.exchange(request);
    };
}
~~~

Attach in order:

~~~java
builder
    .filter(logicalUrlLog)
    .filter(lbFunction)
    .filter(physicalUrlLog);
~~~

Expect the logical filter to see `inventory-service`; the filter after LoadBalancer can see `localhost:8081` or `localhost:8082`. **This is a lab diagnostic technique**, not sole proof of the algorithm: correlate with backend access logs and Spring Cloud lifecycle metrics when production observability is needed.

## 14. Testing the Filter Chain Without Relying on Distribution Luck

A brittle test assumes every pair of requests always hits two different replicas. With Random, that is not guaranteed; with Round Robin, concurrency and retries can make the order differ from what a naive test expects.

Two testing layers are recommended:

**Pure unit test for filters:** pass a mock `ExchangeFunction` to correlation/auth/logging filters. Verify the filter adds expected headers, does not corrupt URLs, does not leak tokens, returns `ClientResponse` properly, and propagates errors/cancellation. No registry startup needed.

**LoadBalancer integration test:** run two test backends and a Spring context with `SimpleDiscoveryClient`, verifying that a request using a service ID resolves to a physical host/port and receives a response from the backend. Use `StepVerifier` or `WebTestClient` to subscribe to the publisher. You can measure across multiple requests to verify distribution without mandating a rigid order.

One way to test the no-instance error:

1. Configure a service ID `missing-service` with no instances.
2. Use the load-balanced WebClient to call `http://missing-service/whoami`.
3. Verify the result is not a 200 success; typically it is an error corresponding to `503` after `retrieve()`.
4. Confirm logs contain no tokens and the error handler returns an appropriate business message.

If the response body is streaming, verify `DataBuffer` release in custom filters; reading a body for logging or discarding `ClientResponse` without releasing resources can leak memory or connection pool slots.

## 15. Common Issues and Diagnostics

| Symptom | Common Cause | Diagnostic Direction |
|---|---|---|
| `UnknownHostException: inventory-service` | Plain WebClient used without LoadBalancer filter | Check injected builder bean, `@LoadBalanced`, or `.filter(lbFunction)` |
| HTTP 503 from service ID | No eligible instances or backend failure | Check discovery, health supplier, and actual status |
| One request logged twice | Multiple logging filters registered or multi-layer retries | Check filter order and attempt count |
| LoadBalancer invoked twice | Manually attached `lbFunction` to a `@LoadBalanced` builder | Choose one integration approach |
| Logs only show service ID, not replica | Logging filter sits before LoadBalancer | Place diagnostic filter after `lbFunction` or use backend logs/lifecycle |
| Filter reads empty correlation ID | Using ThreadLocal MDC or missing Reactor Context | Check `contextWrite` and `deferContextual` |
| Token sent to wrong service | Token filter used on a WebClient calling multiple hostnames | Use per-downstream clients and target allowlists |
| 500 does not enter logging filter's `doOnError` | 500 is a `ClientResponse` at the filter layer | Inspect `response.statusCode()` in `doOnNext` |
| `block()` causes stalls | Blocking calls on the event loop | Keep filters and token providers reactive |
| `retryWhen` does not switch instances | No retry-aware routing or randomly picked same backend | Check retry/avoid-previous mechanism and supplier |
| One logical request triggers many HTTP attempts | Internal retries and `retryWhen` overlapping | Set a shared budget and separate metrics |
| Changing timeout still leaves requests waiting long | Transport timeout differs from overall pipeline timeout | Set a suitable total deadline; check retry/timeout ordering |
| Missing traces even though WebClient works | Manually created builder bypassed instrumentation | Use Boot-managed builder/observation customization |

## 16. Production Readiness Checklist

- [ ] Determine whether WebClient uses **service IDs** or standard DNS/VIP hostnames.
- [ ] If client-side load balancing is required, include `spring-cloud-starter-loadbalancer` and a `ServiceInstance` source.
- [ ] Use `@LoadBalanced WebClient.Builder` **or** attach `ReactorLoadBalancerExchangeFilterFunction` manually; avoid attaching both.
- [ ] Use custom filters only for HTTP requests/responses; configure suppliers/strategies at the Spring Cloud LoadBalancer layer.
- [ ] Register filters in an intentional order and verify logical URL vs. physical URL if needed.
- [ ] Use Reactor Context or tracing instrumentation instead of relying solely on ThreadLocal MDC.
- [ ] Keep token filters asynchronous without calling `block()` on the event loop; scope tokens strictly to intended targets.
- [ ] Never log bearer tokens, raw bodies, cookies, full URIs/queries, or sensitive data.
- [ ] Distinguish HTTP 4xx/5xx responses from reactive `onError` signals at the filter layer.
- [ ] Bound total retries and timeouts; consider idempotency for write operations.
- [ ] Cross-check health checks and discovery when 503s or skewed distribution occur.
- [ ] Use a Boot-managed builder when Micrometer Observation/tracing is needed.
- [ ] Unit-test filters independently and integration-test across at least two replicas.
- [ ] Verify cancellation, response body resource cleanup, and connection pooling when deploying custom filters.

## References

- [Spring Cloud Commons — Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): `@LoadBalanced WebClient.Builder` integration, reactive filters, suppliers, selection, and retries.
- [Spring Framework — WebClient Filters](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-filter.html): `ExchangeFilterFunction`, `ClientRequest`, `ClientResponse`, and body-handling responsibilities.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): reactive HTTP client, status handling, request bodies, and codecs.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): instrumentation/tracing from Spring-managed WebClient builders.

**Conclusion:** `ReactorLoadBalancerExchangeFilterFunction` is the bridge between the **WebClient filter chain** and **Spring Cloud LoadBalancer**. It extracts the service ID from a logical URI, delegates `ServiceInstance` selection to LoadBalancer, and passes the resolved request to the HTTP connector. Placing filters in the right order ensures consistent authentication, context propagation, and logging, while cleanly separating instance selection from retries, timeouts, health checks, and observability in the reactive pipeline.
