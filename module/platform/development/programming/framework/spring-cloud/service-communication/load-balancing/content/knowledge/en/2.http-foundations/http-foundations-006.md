# Blocking and Non-Blocking Communication

In inter-service communication, an application sends an HTTP request and waits for the target service to process it and return an HTTP response. How the application waits for that response directly affects thread usage, concurrency capacity, and how source code is structured.

In the **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING** module, this topic forms the foundation for choosing and using **RestClient**, **WebClient**, or **OpenFeign** when Spring Cloud LoadBalancer routes requests to a service instance. The load balancer decides which instance a request goes to; blocking versus non-blocking determines how application threads handle I/O wait time.

## 1. What Are Blocking and Non-Blocking Communication?

HTTP is a request/response protocol. A request still travels across the network, gets processed by the server, and receives a response regardless of whether the client uses a blocking or non-blocking model. These two concepts describe how the caller's code manages work while waiting for I/O.

### Blocking communication

A blocking call only returns a result once the operation finishes or throws an error. While waiting for the connection, data, or response, the calling thread is held and cannot proceed to other work.

For example, when calling a synchronous method to fetch product details, the execution thread must wait for the server to reply before running the next statement:

~~~java
ItemDto item = catalogClient.getItem(itemId);
orderService.continueProcessing(item);
~~~

If the request takes 400 ms, the thread calling the method spends that time waiting. The thread does not necessarily consume CPU continuously during the wait, yet it remains occupied and cannot serve another request.

### Non-blocking communication

A non-blocking call initiates the I/O operation and immediately returns control to the current thread. When data becomes ready, the network library signals completion; the program continues processing the result through a callback, future, or reactive data stream.

For example, with **WebClient**, the method can return a **Mono<ItemDto>** before the response arrives:

~~~java
Mono<ItemDto> itemPublisher = webClient.get()
    .uri("http://catalog-service/api/items/{id}", itemId)
    .retrieve()
    .bodyToMono(ItemDto.class);
~~~

A `Mono` is a publisher representing a result that may arrive later. Creating the publisher does not mean the request has already been sent. With Reactor, the request executes when the publisher is subscribed to; in a WebFlux application, the framework usually handles subscribing at the request-handling boundary.

Non-blocking does not mean the request finishes instantaneously, uses zero threads, or is always faster. It means the calling thread does not have to sit idle waiting for the response throughout the I/O duration.

### Distinguishing from synchronous and asynchronous

In Java applications, these concepts often appear together but are not strictly synonymous:

- **Synchronous** describes how control flow receives the result: the call returns the result directly in the current execution flow.
- **Asynchronous** describes how the result is delivered after work begins, such as via a callback or publisher.
- **Blocking** describes whether the current thread must wait for the operation to complete.
- **Non-blocking** describes whether the thread can continue doing other work while I/O is in progress.

An asynchronous API can still be used in a blocking way if the program calls **block()** or waits for the result with an equivalent mechanism. Conversely, offloading a synchronous call onto a thread pool merely shifts where blocking occurs to another thread; the underlying I/O operation itself remains blocking.

## 2. Lifecycle of a Blocking HTTP Request

With a synchronous client, processing proceeds through these steps in order:

1. The application invokes the client method.
2. Spring Cloud LoadBalancer receives the service ID, fetches the list of available instances, and selects one instance.
3. The HTTP client establishes or reuses a connection and sends the request.
4. The calling thread waits for a response from the target service.
5. The client reads the response, converts the data into a Java object, and returns the result to the application.
6. Statements following the call are then executed.

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Calling application
    participant T as Request thread
    participant LB as Spring Cloud LoadBalancer
    participant S as Service instance

    App->>T: Call synchronous method
    T->>LB: Resolve service ID
    LB-->>T: Return selected instance
    T->>S: Send HTTP request
    Note over T: Thread waits for response
    S-->>T: HTTP response
    T-->>App: Return DTO or error
    App->>T: Continue processing
~~~

### Example with RestClient

In Spring Cloud versions that support load balancing integration for **RestClient**, you can register a builder marked with **@LoadBalanced**:

~~~java
@Configuration
class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

The client uses the service ID in the URL:

~~~java
@Service
class CatalogClient {

    private final RestClient restClient;

    CatalogClient(@LoadBalanced RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    public ItemDto getItem(String itemId) {
        return restClient.get()
            .uri("http://catalog-service/api/items/{id}", itemId)
            .retrieve()
            .body(ItemDto.class);
    }
}
~~~

**catalog-service** is the logical service name. Spring Cloud LoadBalancer resolves this name to the address of the chosen instance before sending the request. The **getItem()** method returns **ItemDto** directly, so the caller waits until the response is read and decoded.

### Example with OpenFeign

Spring Cloud OpenFeign provides a declarative way to define clients using interfaces. Typical OpenFeign calls are synchronous and blocking:

~~~java
@FeignClient(name = "catalog-service")
public interface CatalogFeignClient {

    @GetMapping("/api/items/{id}")
    ItemDto getItem(@PathVariable("id") String itemId);
}
~~~

When **getItem()** is called, the current thread waits for the result. The value in the **name** attribute specifies the service ID to integrate with service discovery and Spring Cloud LoadBalancer. Callers do not need to fetch individual instance IP addresses themselves.

## 3. Lifecycle of a Non-Blocking HTTP Request

With a non-blocking client, the thread initiating the request does not wait for the response. The I/O library manages connections and notifies when data arrives. In Spring WebFlux's reactive model, Reactor Netty typically uses a group of event loops to handle many I/O connections.

High-level processing flow:

1. The application creates and returns a publisher.
2. When the publisher is subscribed to, WebClient begins executing the request.
3. The load balancing filter resolves the service ID and picks an instance.
4. The event loop manages sending and receiving network data. While waiting for data, the event loop can handle events for other connections.
5. When the response arrives, the publisher emits data or an error for downstream operators to process.

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Application
    participant P as Mono / Flux
    participant E as Event loop
    participant LB as Spring Cloud LoadBalancer
    participant S as Service instance

    App->>P: Create publisher
    P->>E: Subscribe and start request
    E->>LB: Resolve service ID
    LB-->>E: Return selected instance
    E->>S: Send HTTP request
    Note over App,E: Calling thread is freed for other work
    S-->>E: HTTP response
    E-->>P: Emit data or error
    P-->>App: Execute next processing step
~~~

### Example with WebClient

You can create a builder for requests to load-balanced services:

~~~java
@Configuration
class ReactiveHttpClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }

    @Bean
    WebClient catalogWebClient(
            @LoadBalanced WebClient.Builder builder) {
        return builder.build();
    }
}
~~~

The client returns **Mono<ItemDto>** instead of an already-materialized object:

~~~java
@Service
class ReactiveCatalogClient {

    private final WebClient webClient;

    ReactiveCatalogClient(WebClient catalogWebClient) {
        this.webClient = catalogWebClient;
    }

    public Mono<ItemDto> getItem(String itemId) {
        return webClient.get()
            .uri("http://catalog-service/api/items/{id}", itemId)
            .retrieve()
            .bodyToMono(ItemDto.class);
    }
}
~~~

The method above describes a processing pipeline. It does not need to block a thread waiting for data yet. Upon subscription, WebClient sends the request and emits the result once the response is ready.

Multiple requests can be composed in the same pipeline. If the second request depends on data from the first, use **flatMap**:

~~~java
public Mono<OrderView> getOrderView(String orderId) {
    return orderClient.getOrder(orderId)
        .flatMap(order ->
            catalogClient.getItem(order.itemId())
                .map(item -> new OrderView(order, item))
        );
}
~~~

If two requests are independent and both results are needed, combine them with **Mono.zip**:

~~~java
return Mono.zip(
        customerClient.getCustomer(customerId),
        catalogClient.getItem(itemId)
    )
    .map(tuple ->
        new CheckoutView(tuple.getT1(), tuple.getT2())
    );
~~~

These operators express dependencies and how results are combined. They do not automatically guarantee that target services have enough capacity; connection limits, concurrency limits, and timeouts still need proper configuration.

## 4. Comparing the Two Models

| Criterion | Blocking | Non-blocking |
|---|---|---|
| Thread while waiting for response | Held until I/O completes | Can handle other work while I/O waits |
| Typical API style | RestClient, RestTemplate, OpenFeign | WebClient with Mono or Flux |
| How results are received | Direct return value or exception | Publisher, callback, or completion signal |
| Code structure | Sequential, easy to read for simple business flows | Operator chains, requires understanding composition and reactive semantics |
| Resources to manage | Thread pool, connection pool, timeouts | Event loop, connection pool, concurrency, backpressure |
| Common risks | Thread exhaustion when many requests wait on I/O | Blocking the event loop or creating unbounded pipelines |
| Best-suited cases | Imperative applications, moderate load, sequential logic | High concurrent I/O, end-to-end reactive pipelines |

Do not conclude that non-blocking is always faster than blocking. Under light load, a synchronous client can be simpler and plenty efficient. When many requests concurrently wait on external services, the non-blocking model can reduce the number of threads needed. Actual performance still depends on network latency, server processing time, connection pool configuration, CPU, and downstream service limits.

## 5. Where Does Spring Cloud LoadBalancer Fit in Both Models?

Spring Cloud LoadBalancer is a client-side load balancing mechanism. The application calls a service using a logical service ID, such as **catalog-service**. The load balancer obtains **ServiceInstance** entries from an instance supplier, applies filters or a selection policy, and returns an instance for the client to send the request to.

High-level process:

~~~mermaid
flowchart TD
    A["Application calls catalog-service"] --> B["HTTP client"]
    B --> C["Spring Cloud LoadBalancer"]
    C --> D["ServiceInstance supplier"]
    D --> E["Available instance list"]
    E --> F["Select instance by policy"]
    F --> G["Replace service ID with instance address"]
    G --> H["Send HTTP request"]
    H --> I["Receive HTTP response"]
~~~

The key point is that load balancing and blocking/non-blocking belong to two separate layers of responsibility:

- LoadBalancer answers **which instance to send the request to**.
- The HTTP client answers **how to send the request and manage waiting for the response**.
- **RestClient** and **OpenFeign** provide synchronous, typically thread-blocking calls.
- **WebClient** supports non-blocking I/O when used in a reactive pipeline.
- Adding **@LoadBalanced** enables a client to resolve service IDs via Spring Cloud LoadBalancer; this annotation does not automatically turn a synchronous client into a non-blocking one.

Thus, the same service ID can be called from different client types if the application configures the corresponding integration properly. The instance list can come from service discovery or an instance supplier configured in the application. Instance selection policies and instance filters affect the destination of the request, while the client's threading model is still determined by the API and underlying I/O library.

## 6. Timeouts, Errors, and Retries in Both Models

Non-blocking does not eliminate network latency. A request can still wait for a long time due to DNS, TCP connections, overloaded services, or an unresponsive server. Therefore, both models require wait limits.

Types of timeouts to consider:

- **Connect timeout**: maximum time to establish a connection to an instance.
- **Response timeout**: maximum time to wait for a response or response data per HTTP client configuration.
- **Connection-pool acquire timeout**: maximum time to wait for a connection from the pool when the pool is busy.
- **Business deadline**: total maximum time the business flow allows an operation to complete, encompassing multiple sequential requests.

Exact property names and configuration depend on the underlying HTTP client and Spring version. Configure timeouts for each client actually in use, while ensuring the overall business deadline is greater than or equal to the time budget allocated to sub-steps.

### Handling response errors

With WebClient, HTTP statuses can be mapped to application errors:

~~~java
public Mono<ItemDto> getItem(String itemId) {
    return webClient.get()
        .uri("http://catalog-service/api/items/{id}", itemId)
        .retrieve()
        .onStatus(
            status -> status.value() == 404,
            response -> Mono.error(
                new ItemNotFoundException(itemId)
            )
        )
        .bodyToMono(ItemDto.class);
}
~~~

Whether using RestClient, OpenFeign, or WebClient, the application must distinguish connection errors, timeouts, HTTP errors from the server, and response decoding errors. These failures carry different implications when deciding whether to retry or propagate an error to the caller.

### Retries must be bounded

Retries can help when an instance is temporarily unavailable or a connection encounters a transient glitch. However, retries increase actual request volume. If every client retries simultaneously while a service is overloaded, the extra traffic can worsen the outage.

A retry policy should:

- Cap the maximum number of attempts and total retry duration.
- Retry only recoverable errors, such as certain connection errors or transient server errors.
- Favor idempotent operations. For write operations, require an idempotency key mechanism or equivalent business guarantee before retrying.
- Use backoff and jitter to avoid many clients retrying at the exact same moment.
- Coordinate HTTP client retries with Spring Cloud LoadBalancer retries to avoid multiplying attempts unexpectedly.

Retrying does not automatically guarantee switching to a different instance. Instance selection on the next attempt depends on retry configuration and the load balancing policy. Verify the actual behavior of the running version and configuration.

## 7. Common Mistakes When Using WebClient

### Calling block() inside a reactive pipeline

~~~java
ItemDto item = webClient.get()
    .uri("http://catalog-service/api/items/{id}", itemId)
    .retrieve()
    .bodyToMono(ItemDto.class)
    .block();
~~~

**block()** waits for the publisher to complete and holds the calling thread. If called on an event loop, it can prevent the event loop from handling other connections or raise an error in a Reactor runtime. Once you choose WebClient for a reactive pipeline, return **Mono** or **Flux** and compose steps with reactive operators. Only bridge to blocking at an intentional imperative boundary on an appropriate thread.

### Calling subscribe() inside a service and returning immediately

~~~java
public void refreshItem(String itemId) {
    webClient.get()
        .uri("http://catalog-service/api/items/{id}", itemId)
        .retrieve()
        .bodyToMono(ItemDto.class)
        .subscribe(this::updateCache);
}
~~~

This creates an execution flow detached from the method's lifecycle. The caller does not know when the work finishes, struggles to receive errors, cannot coordinate transactions, and loses control over request cancellation. For business logic needing a result, return the publisher so the caller composes it and decides when to subscribe. Use fire-and-forget only when the business logic explicitly accepts independent execution and proper error tracking is in place.

### Wrapping a blocking call in Mono without changing how I/O executes

~~~java
Mono.fromCallable(() -> restClient.get()
        .uri("http://catalog-service/api/items/{id}", itemId)
        .retrieve()
        .body(ItemDto.class));
~~~

The snippet above creates a publisher from a callable, yet the RestClient operation inside remains blocking when the callable runs. If a blocking library must temporarily be integrated into a reactive application, offload the work to a scheduler meant for blocking tasks, typically **Schedulers.boundedElastic()**, with an appropriate load limit:

~~~java
Mono.fromCallable(() -> legacyClient.getItem(itemId))
    .subscribeOn(Schedulers.boundedElastic());
~~~

This isolates the blocking portion; it does not turn it into non-blocking I/O. If most of the communication chain is blocking, consider keeping an imperative model end-to-end rather than building a reactive pipeline solely to wrap blocking calls.

### Blocking the event loop with CPU work or blocking I/O

Event loops need to return quickly to process network events. Avoid running blocking JDBC queries, blocking API calls, long lock waits, or heavy CPU computations directly on an event loop. Offload such work to an appropriate scheduler or executor with bounded concurrency and monitoring.

### Creating unbounded concurrency

Non-blocking makes it possible to manage many concurrent I/O operations, but that does not mean an application should fire an unlimited number of requests. Too many in-flight requests can exhaust connection pools, increase memory held for responses, overload target services, and build large queues. Bound concurrency, apply backpressure where appropriate, and monitor active request counts.

## 8. Which Model Should You Choose for a Service?

Choose a synchronous client such as RestClient or OpenFeign when business code is primarily imperative, concurrent request volume stays within thread pool limits, and straightforward sequential control flow is valuable. This is also typically easier to integrate with synchronous libraries like JDBC and imperative transactions.

Choose WebClient with the non-blocking model when the application must handle high concurrent I/O, can maintain a reactive pipeline from controller through service to HTTP client, and the team is equipped to operate Reactor/WebFlux. The benefits shrink considerably if every reactive step ends up calling a blocking API or frequently invoking **block()**.

Before deciding, answer the following questions:

1. How many services does a single business request call, and are those calls dependent or independent?
2. What are the average and high-percentile latencies of those services?
3. What is the expected concurrency, and what limits exist on current thread pools or connection pools?
4. Are the libraries accessing databases, caches, and message brokers blocking or non-blocking?
5. Does the application need backpressure, request cancellation, and combining multiple data streams?
6. Does the system already have timeouts, retries, concurrency limits, and metrics to detect overload?

Whichever model you choose, call services using a service ID so Spring Cloud LoadBalancer can select instances as configured, set explicit timeouts, and ensure requests are observable. During load testing, measure throughput, latency, active threads, connection pools, timeout rates, and request distribution across instances. These metrics reveal how the model uses resources and whether the load balancer distributes requests as expected.
