# Distinguishing Blocking and Reactive Calls

A Spring Cloud application often needs to call other services over HTTP or a similar network protocol. Calls can be made in a **blocking** model: the calling thread waits until a result arrives; or in a **reactive** model: the application describes an asynchronous pipeline, threads do not block waiting for I/O completion, and results are emitted via `Mono` or `Flux`.

This difference lies in how the application organizes waiting and result handling. It is independent of where the service is discovered. Spring Cloud Discovery provides the instance list; Spring Cloud LoadBalancer selects an instance; the HTTP client executes the request. Both a blocking client and a reactive client can use a service ID to call a service through LoadBalancer.

In the Spring ecosystem, `RestClient` is the synchronous HTTP client with a fluent API; `WebClient` is the non-blocking, reactive client supporting Reactive Streams backpressure. `RestTemplate` still appears in many existing applications, though Spring Framework 7.0 has marked it deprecated in favor of `RestClient`. When choosing an API, verify against your project's Spring Boot and Spring Cloud release train.

This lesson belongs to the **Service Calls** chapter of the **SPRING_CLOUD_CORE** module. Learners will understand execution models, how Spring Cloud LoadBalancer integrates with blocking/reactive clients, how to handle timeouts, errors, retries, and cancellation, and how to test service calls in distributed systems.

## 1. Learning objectives

After this lesson, learners can:

1. Explain how a blocking call holds a thread while waiting for I/O.
2. Describe `Mono`, `Flux`, subscription, and backpressure in reactive calls.
3. Distinguish `RestClient`, `RestTemplate`, and `WebClient`.
4. Choose a call model matching Spring MVC, Spring WebFlux, and the libraries used by the application.
5. Integrate blocking and reactive clients with Spring Cloud LoadBalancer using service IDs.
6. Avoid blocking the event loop with `.block()` or blocking library calls.
7. Design timeouts, error mapping, retries, cancellation, and deadlines for downstream calls.
8. Compose multiple service calls sequentially or concurrently.
9. Test responses, HTTP errors, timeouts, and load balancing behavior.
10. Identify operational issues such as thread pool exhaustion, retry storms, and calling the wrong instance.

## 2. What steps make up a service call?

Suppose `orders-service` needs to fetch stock levels from `inventory-service`. In an environment with multiple instances, the client typically does not call a fixed hostname. It uses a logical service ID, and Spring Cloud LoadBalancer collaborates with discovery to choose an instance.

~~~mermaid
flowchart TD
    A[Orders service] --> B[HTTP client]
    B --> C{Execution model}
    C -->|Blocking| D[RestClient / RestTemplate]
    C -->|Reactive| E[WebClient]
    D --> F[Spring Cloud LoadBalancer]
    E --> F
    F --> G[DiscoveryClient / ServiceInstanceListSupplier]
    G --> H[Select instance]
    H --> I[HTTP request over network]
    I --> J[Inventory instance]
    J --> K[HTTP response]
    K --> B
~~~

There are three separate responsibilities:

| Component | Responsibility |
| --- | --- |
| `DiscoveryClient` | Read `ServiceInstance` objects advertised by the registry |
| Spring Cloud LoadBalancer | Choose an appropriate instance for the request |
| HTTP client | Send the request, receive the response, and convert the body |

Blocking or reactive describes how the HTTP client coordinates threads and results. It does not determine which registry is used or how many instances a service has.

### 2.1. Service ID instead of a fixed address

A request can use the URL:

~~~text
http://inventory-service/api/items/SKU-100
~~~

`inventory-service` is the service ID. When the client is configured as load-balanced, LoadBalancer finds the matching instances, for example:

~~~text
inventory-service
  ├── 10.0.1.12:8080
  ├── 10.0.1.13:8080
  └── 10.0.1.14:8080
~~~

If code calls `http://10.0.1.12:8080` directly, it bypasses instance selection by service ID. Service ID URLs are only resolved when the client has a matching LoadBalancer integration.

## 3. How does a blocking call work?

### 3.1. Thread waits for the result

With a blocking client, the calling thread initiates the request and waits until it receives a response, error, or timeout. While waiting on the network, that thread cannot process any other work.

Example:

~~~java
StockResponse response = restClient.get()
        .uri("http://inventory-service/api/items/{sku}", sku)
        .retrieve()
        .body(StockResponse.class);
~~~

When `body(...)` returns, the response has already been read and converted into `StockResponse`, or the call threw an exception. Control flow continues sequentially as usual.

### 3.2. Blocking puts pressure on the thread pool

Suppose a request needs to call a downstream service taking 800 ms. If 100 concurrent requests all wait on a slow downstream, many threads will be held during that time.

In Spring MVC with a servlet container, the thread pool can absorb blocking I/O, yet the number of threads remains finite. If all threads are waiting on downstream services, incoming requests may have to queue or be rejected.

A simplified model:

~~~mermaid
flowchart TD
    A[Request 1] --> T1[Servlet thread 1]
    B[Request 2] --> T2[Servlet thread 2]
    C[Request 3] --> T3[Servlet thread 3]
    T1 --> W1[Wait for HTTP response]
    T2 --> W2[Wait for HTTP response]
    T3 --> W3[Wait for HTTP response]
    W1 --> R[Continue processing]
    W2 --> R
    W3 --> R
~~~

Blocking is not inherently bad. With moderate load, sequential business flows, and synchronous libraries, it is easy to read, debug, and integrate. What matters is setting timeouts, bounding concurrency, and sizing the thread pool properly.

### 3.3. Blocking APIs in Spring

**`RestClient`** is the synchronous option with a fluent API, introduced in Spring Framework 6.1. It suits applications that need imperative HTTP calls.

~~~java
RestClient restClient = RestClient.builder()
        .baseUrl("https://inventory.internal")
        .build();

StockResponse stock = restClient.get()
        .uri("/api/items/{sku}", sku)
        .retrieve()
        .body(StockResponse.class);
~~~

**`RestTemplate`** is the long-standing template-style synchronous client. It is still present in many legacy Spring Boot systems. Per Spring Framework 7.0 documentation, `RestTemplate` is deprecated in favor of `RestClient`; for projects on Framework 5.x or 6.x, check the API and upgrade path for that version.

~~~java
StockResponse stock = restTemplate.getForObject(
        "http://inventory-service/api/items/{sku}",
        StockResponse.class,
        sku
);
~~~

Do not confuse whether a client has a fluent API or template methods with network behavior. Both make synchronous calls.

## 4. How does a reactive call work?

### 4.1. Returning a publisher instead of an immediate result

`WebClient` is a non-blocking, reactive HTTP client. Call methods typically return `Mono<T>` or `Flux<T>` rather than returning the object directly.

~~~java
Mono<StockResponse> stockMono = webClient.get()
        .uri("http://inventory-service/api/items/{sku}", sku)
        .retrieve()
        .bodyToMono(StockResponse.class);
~~~

`Mono<StockResponse>` represents a result that may arrive later, may complete with no value, or may terminate with an error. `Flux<StockResponse>` represents a sequence that can emit zero, one, or multiple elements.

| Type | Meaning |
| --- | --- |
| `Mono<T>` | Zero or one value of type `T`, then complete or error |
| `Flux<T>` | Zero, one, or many values of type `T`, then complete or error |

### 4.2. Subscription triggers the pipeline

With WebClient, the pipeline executes when there is a subscriber. Creating a `Mono` only describes the work; it does not necessarily send the request immediately at the line where the variable is created.

~~~java
Mono<StockResponse> stockMono = webClient.get()
        .uri("http://inventory-service/api/items/{sku}", sku)
        .retrieve()
        .bodyToMono(StockResponse.class);

// The request executes when the pipeline is subscribed to.
return stockMono;
~~~

In a WebFlux controller, returning the publisher to the framework is standard practice:

~~~java
@GetMapping("/items/{sku}/stock")
Mono<StockResponse> getStock(@PathVariable String sku) {
    return inventoryClient.getStock(sku);
}
~~~

Do not call `subscribe()` manually inside a controller. The framework subscribes and manages the result according to the request lifecycle.

### 4.3. Non-blocking I/O and the event loop

In WebFlux, request-handling threads are typically fewer than in the servlet thread-per-request model. The event loop handles many connections by registering interest in I/O events and moving on to other work instead of holding a thread waiting on each socket.

~~~mermaid
sequenceDiagram
    participant App as WebFlux handler
    participant Loop as Event-loop
    participant Net as Network
    participant Remote as Inventory service

    App->>Loop: Create and subscribe WebClient pipeline
    Loop->>Net: Send request
    Loop-->>App: Yield control, continue other work
    Net->>Remote: HTTP request
    Remote-->>Net: HTTP response
    Net-->>Loop: I/O completion event
    Loop->>App: Resume pipeline
    App-->>App: Return reactive result
~~~

Threads do not sit waiting for responses throughout network round-trips. This improves resource utilization under high concurrent I/O, though it does not magically make downstream services faster.

### 4.4. Backpressure

Reactive Streams includes backpressure so subscribers signal how much data they are ready to receive. This matters when responses are large streams or producers outpace consumers.

Example:

~~~java
Flux<ServerSentEvent<StockUpdate>> updates =
        webClient.get()
                .uri("http://inventory-service/api/stock/stream")
                .retrieve()
                .bodyToFlux(new ParameterizedTypeReference<>() {});
~~~

Consumers can process items incrementally rather than loading the entire content into a collection. However, backpressure only works when components along the pipeline and transport propagate demand signals appropriately; it is not an automatic response-size cap.

### 4.5. Reactive does not mean everything runs in parallel

A reactive pipeline can execute steps sequentially, concurrently, or in a dataflow. Using `Mono` does not automatically spawn a new thread for each operation. Reactor determines threads based on the source, schedulers, and coordinating operators.

Do not add `subscribeOn` or `publishOn` everywhere out of habit. Switch schedulers only for a concrete reason, such as isolating a blocking library.

## 5. Comparing blocking and reactive

| Criterion | Blocking | Reactive |
| --- | --- | --- |
| Return value | Direct object/`ResponseEntity` | `Mono<T>` or `Flux<T>` |
| While waiting for I/O | Calling thread is held | Thread can handle other work |
| Processing model | Imperative, sequential | Pipeline, callbacks, and signals |
| Concurrency | Typically thread-pool based | Non-blocking I/O, event loop, and backpressure |
| Error handling | Exception at call site | Error signal in publisher |
| Call cancellation | Depends on interruption and HTTP client | Cancellation signal can propagate upstream through pipeline |
| Debugging | Direct control flow | Requires understanding subscriptions, operators, and schedulers |
| Best fit | Synchronous apps, MVC, blocking libraries | WebFlux and end-to-end reactive I/O systems |

### 5.1. There is no single best choice for every application

Choose blocking when:

- The application uses Spring MVC and most libraries are blocking.
- Concurrent load fits comfortably within a thread pool.
- Simple, maintainable business control flow is a priority.
- The team uses JDBC or synchronous SDKs.

Choose reactive when:

- The application uses WebFlux and many dependencies offer non-blocking APIs.
- There are many concurrent I/O connections or streaming requirements.
- You want to compose multiple asynchronous calls without holding threads waiting.
- You are prepared to manage schedulers, cancellation, context, and backpressure.

Do not rewrite an entire application to WebFlux just because one downstream needs `WebClient`. Spring MVC can use WebClient. Conversely, if a WebFlux application calls blocking JPA/JDBC on the event loop, non-blocking benefits can be negated.

### 5.2. Costs of the reactive model

Reactive can reduce the number of threads held during I/O, but comes with design costs:

- Must understand publishers and subscription timing.
- Must handle error signals inside the pipeline.
- Must account for cancellation and timeouts.
- Thread-local context does not automatically propagate as in imperative code.
- Debugging stack traces and operator chains can be harder.
- A single blocking library can stall the event loop if not isolated.

Choose reactive when workload characteristics and the library ecosystem yield clear benefits, not just because an API returns `Mono`.

## 6. Blocking service calls via Spring Cloud LoadBalancer

Spring Cloud LoadBalancer provides blocking integration for `RestClient` and `RestTemplate`. When a client is marked with `@LoadBalanced`, URLs using a service ID can be resolved to a `ServiceInstance`.

### 6.1. Dependencies

With Maven, add the LoadBalancer starter compatible with the Spring Cloud BOM:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
~~~

A matching discovery provider, such as Eureka or Consul, is required if fetching instances from a dynamic registry. In tests or locally, `SimpleDiscoveryClient` can be used with a static instance list.

### 6.2. Configuring RestClient

In Spring Boot versions supporting `RestClient.Builder`, declare a load-balanced builder:

~~~java
@Configuration(proxyBeanMethods = false)
class InventoryHttpConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Create a client using that builder:

~~~java
@Component
class InventoryBlockingClient {

    private final RestClient restClient;

    InventoryBlockingClient(
            @LoadBalanced RestClient.Builder builder
    ) {
        this.restClient = builder.build();
    }

    StockResponse getStock(String sku) {
        return restClient.get()
                .uri("http://inventory-service/api/items/{sku}", sku)
                .retrieve()
                .body(StockResponse.class);
    }
}
~~~

`@LoadBalanced` is the qualifier telling Spring Cloud to apply LoadBalancer integration to the builder. `inventory-service` is a service ID, not a standard DNS hostname. `BlockingLoadBalancerClient` handles instance selection before the HTTP request is sent.

For older Spring Boot/Spring Cloud versions without `RestClient` integration support, use `RestTemplate` following the guide for that release train. Do not manually set a custom version on the starter; let a compatible BOM manage it.

### 6.3. RestTemplate in existing applications

Legacy configuration example:

~~~java
@Bean
@LoadBalanced
RestTemplate restTemplate(RestTemplateBuilder builder) {
    return builder.build();
}
~~~

Then call by service ID:

~~~java
StockResponse response = restTemplate.getForObject(
        "http://inventory-service/api/items/{sku}",
        StockResponse.class,
        sku
);
~~~

This is still a blocking call. `@LoadBalanced` adds service ID resolution and instance selection; it does not turn `RestTemplate` into a reactive client.

## 7. Reactive service calls via Spring Cloud LoadBalancer

### 7.1. Configuring WebClient.Builder

For `WebClient`, Spring Cloud LoadBalancer provides a reactive integration. The common approach is a builder annotated with `@LoadBalanced`:

~~~java
@Configuration(proxyBeanMethods = false)
class InventoryReactiveHttpConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

Create a client:

~~~java
@Component
class InventoryReactiveClient {

    private final WebClient webClient;

    InventoryReactiveClient(
            @LoadBalanced WebClient.Builder builder
    ) {
        this.webClient = builder.build();
    }

    Mono<StockResponse> getStock(String sku) {
        return webClient.get()
                .uri("http://inventory-service/api/items/{sku}", sku)
                .retrieve()
                .bodyToMono(StockResponse.class);
    }
}
~~~

Spring Cloud integrates `ReactorLoadBalancerExchangeFilterFunction` into the WebClient builder to select instances by service ID. The request returns a `Mono`; the caller composes further or returns the publisher to the framework.

### 7.2. Explicit filter function configuration

When WebClient must be configured manually, you can use the filter function provided by Spring Cloud:

~~~java
@Bean
WebClient loadBalancedWebClient(
        ReactorLoadBalancerExchangeFilterFunction loadBalancerFilter
) {
    return WebClient.builder()
            .filter(loadBalancerFilter)
            .build();
}
~~~

This is a reactive integration. Do not use `BlockingLoadBalancerClient` inside a WebFlux pipeline to replace this filter.

### 7.3. Where do Discovery and LoadBalancer run?

When `WebClient` sends a request to `http://inventory-service/...`:

1. The LoadBalancer filter receives the request.
2. It identifies the service ID `inventory-service`.
3. It fetches the instance list from `ServiceInstanceListSupplier`, typically backed by DiscoveryClient.
4. It picks an instance per the configured strategy.
5. It replaces the service ID with the selected instance's host/port.
6. The HTTP connector performs non-blocking I/O.
7. The response enters the reactive pipeline.

Selecting an instance and sending the HTTP request are two separate steps. If no instance is found, LoadBalancer cannot construct a request to a valid address; handle that error accordingly.

## 8. Do not block the event loop with blocking calls

### 8.1. Why is `.block()` dangerous in WebFlux?

The snippet:

~~~java
StockResponse stock = webClient.get()
        .uri("http://inventory-service/api/items/{sku}", sku)
        .retrieve()
        .bodyToMono(StockResponse.class)
        .block();
~~~

turns a reactive call into a synchronous wait. If executed on a non-blocking thread such as a Reactor Netty event loop, it can throw a runtime exception or stall other requests.

Do not call `.block()`, `.blockFirst()`, or `.blockLast()` in WebFlux handlers or pipelines running on non-blocking threads.

### 8.2. Returning publishers to the web boundary

Instead of blocking:

~~~java
@GetMapping("/items/{sku}/stock")
Mono<StockResponse> getStock(@PathVariable String sku) {
    return inventoryClient.getStock(sku);
}
~~~

Spring WebFlux manages subscription and response lifecycles. Errors propagate through the reactive pipeline and can be handled with `onErrorResume`, `onErrorMap`, or appropriate exception handlers.

### 8.3. When a blocking library must be called

If a legacy library only offers a blocking API and cannot yet be replaced, isolate the call off the event loop:

~~~java
Mono<LegacyResult> callLegacy(LegacyRequest request) {
    return Mono.fromCallable(() -> legacyClient.execute(request))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

`boundedElastic` is better suited than the event loop for bounded blocking work. However:

- Set a timeout for the blocking library.
- Cap concurrency and work size.
- Handle interruption if the library supports it.
- Do not create a new scheduler per request.
- Do not assume wrapping in `Mono.fromCallable` makes blocking I/O non-blocking.

If most of the system depends on JDBC/JPA and blocking SDKs, Spring MVC may be a simpler choice than WebFlux.

## 9. Composing multiple service calls

A business request may need to call multiple downstream services. Reactive lets you express dependencies between calls without blocking threads waiting for each response.

### 9.1. Sequential calls when there is a dependency

For example, fetching order details first and then fetching stock:

~~~java
Mono<Order> orderMono = orderClient.getOrder(orderId);

return orderMono.flatMap(order ->
        inventoryClient.getStock(order.sku())
                .map(stock -> new OrderView(order, stock))
);
~~~

`flatMap` calls inventory only after receiving the order. This is a sequential flow dictated by data dependency.

### 9.2. Independent calls can run concurrently

If pricing and stock can be fetched independently:

~~~java
Mono<Price> priceMono = pricingClient.getPrice(sku);
Mono<StockResponse> stockMono = inventoryClient.getStock(sku);

return Mono.zip(priceMono, stockMono)
        .map(tuple -> new ProductView(
                tuple.getT1(),
                tuple.getT2()
        ));
~~~

`Mono.zip` subscribes to the publishers and combines results when both complete. Both I/O calls can proceed concurrently; total duration is typically governed by the slower call rather than the sum of both, provided the transport and downstream allow parallel execution.

If one publisher errors, `zip` typically terminates with that error and cancels the remaining publishers per reactive rules. Clarify whether business rules require a fallback for partial results.

### 9.3. Multiple items with `flatMap`

When processing a list of SKUs:

~~~java
Flux<StockResponse> stocks =
        Flux.fromIterable(skus)
                .flatMap(inventoryClient::getStock, 8);
~~~

The parameter `8` limits how many inner publishers this operator subscribes to concurrently. Do not set concurrency too high if downstream services or connection pools have tight limits.

If input order must be preserved, consider `concatMap` or an appropriate operator. `flatMap` can emit results in completion order and does not guarantee initial ordering.

### 9.4. Blocking composition

With `RestClient`, imperative code usually calls sequentially:

~~~java
Order order = orderClient.getOrder(orderId);
Price price = pricingClient.getPrice(order.sku());
StockResponse stock = inventoryClient.getStock(order.sku());

return new OrderView(order, price, stock);
~~~

This is easy to read and fits when later calls depend on earlier data. If two calls are independent and need parallel execution, an executor or another concurrency mechanism can be used, but thread pools, timeouts, and errors must be managed explicitly.

## 10. Timeouts and deadlines

### 10.1. There is more than one kind of timeout

An HTTP call can involve multiple stages:

| Timeout | Scope |
| --- | --- |
| DNS resolution | Resolving the hostname |
| Connection timeout | Establishing the TCP connection |
| TLS handshake timeout | Completing the TLS handshake |
| Connection pool acquire timeout | Waiting for an available connection |
| Response/read timeout | Waiting for response data |
| Overall deadline | Total business time budget allowed |

A request might connect cleanly yet fail because the downstream takes too long to process. Conversely, it can time out while acquiring a connection from the pool even when the server is healthy.

### 10.2. Timeouts for WebClient pipelines

You can limit the total duration of a publisher:

~~~java
Mono<StockResponse> getStock(String sku) {
    return webClient.get()
            .uri("http://inventory-service/api/items/{sku}", sku)
            .retrieve()
            .bodyToMono(StockResponse.class)
            .timeout(Duration.ofSeconds(2));
}
~~~

Reactor's `timeout` bounds waiting for publisher signals. It does not replace connect/read/response timeouts on the HTTP connector. In production, configure both transport timeouts and business-level deadlines.

### 10.3. Timeouts for the HTTP connector

If using Reactor Netty, several transport timeouts can be configured:

~~~java
HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1000)
        .responseTimeout(Duration.ofSeconds(2));

WebClient webClient = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();
~~~

This example illustrates Reactor Netty. With Jetty or another connector, the configuration API differs. For a load-balanced WebClient, attach the custom connector to the LoadBalancer-integrated builder instead of accidentally creating a WebClient without the filter.

### 10.4. Timeouts for RestClient

`RestClient` uses `ClientHttpRequestFactory` to execute requests. Timeouts must be configured on the chosen request factory or underlying HTTP library.

~~~java
RestClient restClient = RestClient.builder()
        .requestFactory(requestFactoryConfiguredWithTimeouts)
        .build();
~~~

`requestFactoryConfiguredWithTimeouts` represents a factory configured with connect/read timeouts for a specific HTTP client. There is no single universal timeout number that applies automatically across every factory.

### 10.5. Propagating deadlines across service chains

If `orders-service` has a 3-second deadline, it should not grant each downstream call 3 independent seconds. For example:

- Fetching profile takes 1 second.
- Fetching inventory is granted 2 seconds.
- Calling pricing still waits 3 seconds.

Total elapsed time can exceed the original request's deadline. Track the remaining time budget and set per-step timeouts accordingly.

## 11. Handling HTTP and transport errors

### 11.1. Blocking client

With `RestClient.retrieve()`, 4xx/5xx response statuses are converted by default into exceptions under the `RestClientResponseException` hierarchy if no custom status handler is present.

~~~java
try {
    return restClient.get()
            .uri("http://inventory-service/api/items/{sku}", sku)
            .retrieve()
            .body(StockResponse.class);
}
catch (RestClientResponseException ex) {
    // Handle HTTP status and response body according to policy.
    throw new InventoryCallException(ex.getStatusCode(), ex);
}
catch (ResourceAccessException ex) {
    // Transport, connection, or timeout error from the request factory.
    throw new InventoryUnavailableException(ex);
}
~~~

Do not forward raw downstream response bodies to external clients if bodies may contain internal details or secrets.

### 11.2. Reactive client

With WebClient, `retrieve()` converts 4xx/5xx into `WebClientResponseException` by default. You can map errors:

~~~java
Mono<StockResponse> getStock(String sku) {
    return webClient.get()
            .uri("http://inventory-service/api/items/{sku}", sku)
            .retrieve()
            .onStatus(
                    HttpStatusCode::is4xxClientError,
                    response -> response.createException()
            )
            .onStatus(
                    HttpStatusCode::is5xxServerError,
                    response -> response.createException()
            )
            .bodyToMono(StockResponse.class)
            .onErrorMap(
                    WebClientRequestException.class,
                    InventoryUnavailableException::new
            );
}
~~~

This snippet shows how to categorize errors. In production projects, use a dedicated domain exception carrying status, correlation ID, and root cause without leaking the response body.

### 11.3. Error classification

| Error group | Examples | How to handle |
| --- | --- | --- |
| HTTP 4xx | 400, 401, 403, 404 | Usually do not retry automatically; check request, permissions, and resource |
| HTTP 5xx | 500, 502, 503, 504 | Conditional retry if the operation is safe |
| Connection failure | DNS, refused, TLS | Distinguish misconfiguration from transient errors |
| Timeout | Connect or response overdue | Cap retries and enforce deadlines |
| No instance | LoadBalancer finds no instances | Check discovery and readiness |
| Decode error | Response body violates schema | Record contract mismatch; do not retry blindly |
| Cancellation | Caller cancels request | Release resources and stop abortable work |

Do not lump every error into a generic HTTP 500. Accurate classification makes observability, retries, and circuit breakers meaningful.

## 12. Retries, idempotency, and circuit breakers

### 12.1. Retries do not make requests safer

If a POST creating an order reaches the server but the response is lost, the client does not know whether the operation succeeded. Retrying can create a second order.

Only retry when:

- The failure is likely transient.
- The operation is idempotent or carries an idempotency key.
- Time remains within the deadline.
- Retry attempts and backoff are bounded.
- The downstream still has capacity to accept requests.

GET is generally safer to retry than a POST with side effects, though business semantics must still be checked.

### 12.2. Reactive retries

Illustrative example with Reactor:

~~~java
Mono<StockResponse> getStockWithRetry(String sku) {
    return inventoryClient.getStock(sku)
            .retryWhen(
                    Retry.backoff(2, Duration.ofMillis(100))
                            .maxBackoff(Duration.ofSeconds(1))
                            .filter(this::isTransientFailure)
            );
}
~~~

`isTransientFailure` is an application-defined predicate. Do not retry authentication failures, validation errors, or decode errors that will not resolve on their own.

Backoff eases pressure when a downstream is failing. With multiple instances, add jitter or a suitable distribution policy to avoid all clients retrying simultaneously.

### 12.3. LoadBalancer retries and HTTP client retries

Spring Cloud LoadBalancer has its own retry policies for blocking/reactive clients depending on integrations and dependencies. Additionally, applications may have retries in Reactor, Resilience4j, or the HTTP client itself.

If each layer retries 3 times, actual requests can multiply manyfold. Pick one primary layer responsible for retries, define the total attempt budget, and observe retry attempts.

Per current LoadBalancer documentation, reactive retries can be enabled via `spring.cloud.loadbalancer.retry.enabled`; the blocking path with `RestTemplate` has separate Spring Retry requirements. Check the configuration for your exact client and release train before enabling.

### 12.4. Circuit breakers

A circuit breaker stops the application from repeatedly calling a consistently failing downstream. When the circuit opens, calls fail fast or return a fallback instead of generating continued load.

Retries and circuit breakers solve different problems:

- Retries handle occasional transient failures by trying again.
- Circuit breakers prevent repeated calls to a degraded dependency.
- Timeouts bound waiting time.
- Bulkheads cap resources allocated to a dependency.

Do not use infinite retries as a substitute for a circuit breaker or fixing downstream incidents.

## 13. Cancellation and the request lifecycle

### 13.1. Reactive cancellation

When a subscriber cancels a subscription, the cancellation signal can propagate back up the pipeline to WebClient and the transport. The client gets a chance to stop reading/writing and release resources.

However, cancellation does not guarantee the server has not already executed side effects. The request may have reached the server and committed a transaction before the client canceled.

### 13.2. Blocking cancellation

In the blocking model, a thread can be interrupted when a request is canceled or the application shuts down, but whether the request aborts depends on the HTTP client and request factory. Not all libraries immediately stop I/O when a thread is interrupted.

Configure clear timeouts and shutdown policies. Do not assume interruption automatically rolls back an operation on a remote service.

### 13.3. Avoid detaching requests from their lifecycle

In WebFlux, avoid calling `subscribe()` inside a service just to kick off work and discard the publisher. Doing so can swallow errors from the caller, leave work running after the request finishes, and detach cancellation from request tracking.

Instead, return the publisher or compose it into the pipeline. If an independent background task is needed, offload it to a job or message queue with its own lifecycle and retry handling.

## 14. Context propagation, tracing, and logging

### 14.1. Correlation ID

A service call should carry a trace context or correlation ID so logs for a request can be stitched together across services. With compatible tracing instrumentation, client interceptors/filters can propagate trace headers automatically.

Do not invent a custom header at every layer if the system already uses W3C Trace Context or a tracing bridge. Standardize formats and avoid putting tokens or personal data into headers/logs.

### 14.2. ThreadLocal and Reactor Context

In imperative code, many frameworks store state such as security context or tracing context in `ThreadLocal`. In a reactive pipeline, threads can switch between operators, so you cannot assume the same thread handles the entire request.

Reactor provides a subscription-bound `Context` to pass data across pipelines. Modern Spring integrations can support context propagation, though configuration and behavior depend on versions.

Do not read `ThreadLocal` directly inside arbitrary operators assuming its value is always valid. Use the context propagation mechanisms provided by Spring/Reactor.

### 14.3. Metrics

Monitor at minimum:

- Request count by downstream/service ID.
- Latency and percentiles.
- HTTP 4xx/5xx rates.
- Timeouts and connection failures.
- LoadBalancer instance-not-found counts.
- Retry attempts and circuit breaker states.
- Active connections and pending pool acquisitions.
- Cancellations and discarded requests.

Avoid using high-cardinality order IDs, user IDs, or SKUs as metric tags. Use traces/logs for fine-grained details and keep metric tag cardinality bounded.

## 15. Testing blocking and reactive calls

### 15.1. Testing RestClient

You can use `MockRestServiceServer` to mock HTTP responses for `RestClient.Builder`:

~~~java
RestClient.Builder builder = RestClient.builder();

MockRestServiceServer server =
        MockRestServiceServer.bindTo(builder).build();

RestClient client = builder.build();

server.expect(requestTo("http://inventory.test/api/items/SKU-100"))
        .andRespond(withSuccess(
                """
                {"sku":"SKU-100","available":12}
                """,
                MediaType.APPLICATION_JSON
        ));

StockResponse response = client.get()
        .uri("http://inventory.test/api/items/{sku}", "SKU-100")
        .retrieve()
        .body(StockResponse.class);

assertThat(response.available()).isEqualTo(12);
server.verify();
~~~

The example uses a Java text block and assumes `StockResponse` is a record with an `available` field. Add test dependencies appropriate for your Spring Framework version.

### 15.2. Testing WebClient with StepVerifier

`StepVerifier` subscribes to the publisher and asserts emitted signals:

~~~java
StepVerifier.create(inventoryClient.getStock("SKU-100"))
        .assertNext(response ->
                assertThat(response.available()).isEqualTo(12))
        .verifyComplete();
~~~

To test real HTTP, use MockWebServer, WireMock, or an equivalent test server. `StepVerifier` tests publishers; it does not spin up a mock HTTP server on its own.

### 15.3. Essential test cases

| Case | What to verify |
| --- | --- |
| HTTP 200 | Body is decoded properly |
| HTTP 4xx | Error is classified, no improper retry |
| HTTP 5xx | Retry/circuit breaker policy behaves properly |
| Connect timeout | Request ends within the bound |
| Response timeout | Resources are not held indefinitely |
| No service instance | LoadBalancer error is handled |
| Malformed body | Decode error is observed |
| Cancellation | Pipeline stops and releases resources |
| Multiple instances | Requests go to instances chosen by LoadBalancer |
| Retry | Total attempts stay within budget |

### 15.4. Testing LoadBalancer

You can configure `SimpleDiscoveryClient` with two test URIs or use an equivalent test provider. Verify:

- Service ID is resolved.
- LoadBalancer selects an instance.
- Scheme and port are preserved accurately.
- When no instance exists, the client receives a clear error.
- Retries do not exceed the expected count.
- Instance list cache refreshes according to policy.

Do not merely mock `DiscoveryClient` and conclude LoadBalancer integration works. Include at least one integration test verifying the filter/interceptor and URI translation.

## 16. Common errors

| Symptom | Possible cause | How to resolve |
| --- | --- | --- |
| WebFlux request is slow despite using WebClient | Blocking call on the event loop | Look for `.block()`, JDBC/JPA, or blocking SDKs |
| Reactive request never executes | Publisher was never subscribed to or returned | Return the publisher to the framework or compose into pipeline |
| HTTP request sent twice | Multiple subscriptions to a cold publisher or retries | Check subscription sites and retry policies |
| `block()` throws error on non-blocking thread | Blocking the event loop | Return the publisher or isolate the blocking API |
| Cannot resolve service ID | Client lacks LoadBalancer integration or missing provider | Check starters, qualifiers, and discovery |
| Requests always hit one instance | Cache, policy, or supplier configuration | Check LoadBalancer strategy and instance list |
| Thread pool exhausted | Blocking downstream too slow or concurrency too high | Set timeouts, cap concurrency, and inspect pools |
| Retries create heavy load | Multi-layer nested retries or missing backoff | Define one total retry budget |
| POST creates duplicate data | Retrying a non-idempotent operation | Use idempotency keys or disable retries |
| Cancellation does not stop side effects | Server already processed before receiving cancellation | Design for idempotency and business state transitions |
| Response timeout does not behave as expected | Only Reactor timeout set without transport timeout | Configure the HTTP connector/request factory too |
| Tracing lost in reactive flow | Relying on ThreadLocal or missing context propagation | Use Reactor Context and compatible instrumentation |

## 17. Workflow for choosing a service call model

Use these questions when designing a new client:

1. Does the current application use Spring MVC or WebFlux?
2. Are downstream libraries blocking or non-blocking?
3. What are the concurrent call volume and downstream latency?
4. Is streaming or backpressure needed?
5. Are there multiple independent calls to compose in parallel?
6. At which layer are timeouts, retries, and cancellation managed?
7. Is Spring Cloud LoadBalancer integrated with the client matching the model?
8. Can both HTTP and LoadBalancer behavior be tested in the pipeline?
9. Are metrics/tracing in place to identify slow dependencies?
10. Does the Spring Boot/Spring Cloud version support the intended client API?

Example decisions:

| Context | Typically suitable choice |
| --- | --- |
| Spring MVC + JDBC/JPA + synchronous HTTP calls | `RestClient` |
| Spring MVC needing one streaming/async call | Can use `WebClient` just for that client |
| Spring WebFlux + reactive data access + many reactive downstreams | `WebClient` |
| Legacy app using `RestTemplate` | Maintain cautiously or migrate gradually to `RestClient` by version |
| Using service IDs in a multi-replica environment | Integrate Spring Cloud LoadBalancer with the matching client |
| Single blocking library inside WebFlux | Isolate on bounded elastic or consider MVC |

## 18. Practice exercises

**Exercise 1 — Comparing the two clients.** Call the same Inventory endpoint with `RestClient` and `WebClient`. Measure timings, observe threads, and explain the difference in how responses are awaited.

**Exercise 2 — Load-balanced blocking call.** Configure `@LoadBalanced RestClient.Builder`, use the URL `http://inventory-service/...`, and verify requests are routed to instances selected by LoadBalancer.

**Exercise 3 — Load-balanced reactive call.** Configure `@LoadBalanced WebClient.Builder`, return `Mono<StockResponse>` from a WebFlux controller, and test the publisher with StepVerifier.

**Exercise 4 — Blocking on the event loop.** Intentionally invoke a blocking library inside a WebFlux handler. Observe the held thread; then move the call to `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` and compare.

**Exercise 5 — Composing calls.** Call Pricing and Inventory independently with `Mono.zip`; then create another flow that calls Order first and Inventory afterward using `flatMap`.

**Exercise 6 — Timeouts.** Configure connect timeout and response timeout. Simulate a slow server and verify the request does not exceed the business deadline.

**Exercise 7 — Retries and idempotency.** Create a downstream returning 503 on the first few attempts. Try retrying GET and POST; demonstrate how POST can cause duplicate side effects without an idempotency key.

**Exercise 8 — Cancellation.** Cancel a subscription while WebClient is awaiting a response. Observe the client connection and server processing state; explain why cancellation does not imply rollback.

**Exercise 9 — Testing no instances.** Configure discovery with no instances for a service ID. Verify LoadBalancer reports an error and the application returns an appropriate response.

**Exercise 10 — Production observability.** Add latency, timeout, retry, and LoadBalancer discard metrics. Verify tags do not introduce excessive cardinality.

## 19. Takeaways and reference sources

- Blocking clients hold the calling thread while waiting for I/O; `RestClient` and `RestTemplate` are synchronous APIs.
- `WebClient` returns `Mono`/`Flux`, uses non-blocking I/O, and supports Reactive Streams backpressure.
- Reactive pipelines require a subscription; in WebFlux, return the publisher to the framework instead of calling `subscribe()` or `block()` yourself.
- Spring Cloud LoadBalancer integrates blocking clients via `BlockingLoadBalancerClient` and reactive WebClient via `ReactorLoadBalancerExchangeFilterFunction`.
- Service IDs resolve to instances; discovery, instance selection, and sending HTTP requests are three distinct responsibilities.
- Do not call blocking APIs on the event loop; if a replacement is not yet possible, isolate them with an appropriate scheduler and timeout.
- Configure connect/read/response timeouts at the transport; Reactor's `timeout` limits publisher wait time but does not replace all transport timeouts.
- Retries require transient-failure conditions, deadlines, backoff, and idempotency; avoid nested multi-layer retries.
- Cancellation can stop a pipeline but does not guarantee remote side effects are rolled back.
- Choose blocking or reactive based on the entire dependency stack and load profile, not merely the return type of a single API.

Official sources to cross-check for your project's Spring Boot/Spring Cloud versions:

1. [Spring Framework – REST Clients (`RestClient`, `WebClient`, `RestTemplate`)](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
2. [Spring Cloud Commons – Spring Cloud LoadBalancer integrations](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
3. [Spring Framework – WebFlux and the non-blocking model](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html)
4. [Spring Framework – WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
5. [Reactor Core – Reference Guide](https://projectreactor.io/docs/core/release/reference/)
6. [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
7. [Spring Cloud – Release trains and Spring Boot compatibility](https://spring.io/projects/spring-cloud/)