# Synchronous vs. Asynchronous Communication and Module Boundaries

In a microservices system, one service often needs to call another service to fetch data or request a business operation. Calls can be synchronous, asynchronous over HTTP, or mediated through a message broker. Each approach handles waiting for results, error handling, and resource management differently.

In the **Spring Cloud LoadBalancer** module, the focus is selecting a target service instance on the client side. Load balancing supports HTTP clients communicating with services by service ID, but does not dictate the entire communication architecture. To design properly, distinguish synchronous and asynchronous mechanisms while drawing clear boundaries for the client, discovery, load balancer, transport, and target service.

## 1. Two Dimensions of Distinction: Execution Model and Message Exchange Style

Two concepts often confused are *synchronous/asynchronous* and *blocking/non-blocking*.

- **Synchronous** describes how the caller waits for the result: the execution flow invokes a function and needs the result before proceeding.
- **Asynchronous** describes the caller continuing other work while the result completes or arrives later.
- **Blocking** describes a thread being held while waiting for I/O.
- **Non-blocking** describes a thread being able to handle other work while I/O is pending.

A synchronous HTTP call is usually blocking, for example calling with `RestClient`. `WebClient` enables building reactive, non-blocking HTTP calls. A message broker typically creates asynchronous communication by sending events or commands that a consumer processes later.

Do not equate "using WebClient" with "communicating via a message broker". `WebClient` still sends an HTTP request to an endpoint and typically still receives an HTTP response. The main difference is how the application organizes waiting and continuing execution.

| Style | How the Caller Proceeds | Typical Channel | Characteristics |
|---|---|---|---|
| Synchronous HTTP | Waits for response before returning result to caller flow | RestClient, OpenFeign | Easy to read sequentially; thread may be held while waiting |
| Reactive HTTP | Returns a publisher; result is processed when data arrives | WebClient | Can be non-blocking; easy to compose multiple I/O operations |
| Asynchronous messaging | Sends message then proceeds; consumer processes independently | Kafka, RabbitMQ | Decouples send time from processing time; often requires handling eventual consistency |

Which style to choose depends on business requirements, latency, throughput capacity, and how the system needs to handle errors. A load balancer does not automatically turn a synchronous call into an asynchronous one.

## 2. Where Does Spring Cloud LoadBalancer Sit in the Communication Flow?

A client typically knows the logical name of the service to call, such as `inventory-service`, rather than knowing each instance's IP address and port in advance. Service discovery provides the list of registered instances. Spring Cloud LoadBalancer receives the appropriate list, applies an instance selection policy, and returns the chosen instance for the HTTP client to execute the request.

Overall flow:

~~~mermaid
flowchart LR
    A["Application service"] --> B["Service client"]
    B --> C{"HTTP client"}
    C -->|"RestClient"| D["Blocking load-balancer integration"]
    C -->|"WebClient"| E["Reactive load-balancer integration"]
    D --> F["ServiceInstance supplier / discovery"]
    E --> F
    F --> G["Select ServiceInstance"]
    G --> H["HTTP transport"]
    H --> I["Target service"]
~~~

Components have distinct responsibilities:

1. **Application service** decides which business workflow needs data or action from another service.
2. **Service client** encapsulates endpoints, requests, responses, and error mapping for the target service.
3. **Service discovery** supplies instance information, such as host, port, and metadata.
4. **Spring Cloud LoadBalancer** chooses a `ServiceInstance` from the supplied list.
5. **HTTP client and transport** open connections, send requests, receive responses, apply timeout settings, and handle protocol details.
6. **Target service** authenticates the request, executes business logic, and returns the result.

When a URI uses a service ID like `http://inventory-service/api/items/42`, a load-balanced client can resolve that logical name to a concrete instance. Passing a URI containing a specific instance's host and port directly bypasses the load balancer's service-ID-based selection.

Service discovery and load balancing are related but separate steps. Discovery answers the question "which instances exist?", whereas the load balancer answers "which instance will this request go to?". The instance list may come from a registry or another configuration source; LoadBalancer operates through the corresponding `ServiceInstance` supplier mechanism.

## 3. Synchronous HTTP Calls with RestClient

`RestClient` suits imperative applications where the calling method typically needs to return data immediately to the current execution flow. The HTTP call blocks the thread until a response arrives or an error/timeout occurs.

Configure a `RestClient.Builder` supporting load balancing:

~~~java
@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Create a client dedicated to communicating with the inventory service:

~~~java
@Service
public class InventoryClient {

    private final RestClient restClient;

    public InventoryClient(
            @LoadBalanced RestClient.Builder builder) {
        this.restClient = builder
                .baseUrl("http://inventory-service")
                .build();
    }

    public InventoryResponse getInventory(String sku) {
        return restClient.get()
                .uri("/api/inventory/{sku}", sku)
                .retrieve()
                .body(InventoryResponse.class);
    }
}
~~~

When `getInventory` is called, the application waits for the HTTP response and receives an `InventoryResponse`. The name `inventory-service` is the service ID; the load balancing integration layer selects a suitable instance before the request is sent.

A typical call flow:

~~~text
OrderService
    |
    | getInventory("SKU-001")
    v
InventoryClient
    |
    | GET http://inventory-service/api/inventory/SKU-001
    v
LoadBalancer selects instance
    |
    | e.g.: inventory-2.internal:8080
    v
HTTP transport sends request
    |
    v
Inventory service returns response
    |
    v
OrderService continues processing
~~~

`RestClient` keeps code sequential and easy to follow. In return, network wait time occupies the calling thread. If a business request calls several services sequentially, total wait times can add up. Configure appropriate connect and read timeouts on the HTTP request factory/transport in use; instance selection itself does not replace timeout configuration.

For applications already using `RestTemplate`, Spring Cloud also supports load balancing integration via a `RestTemplate` bean annotated with `@LoadBalanced`. For new development on platforms supporting `RestClient`, consider `RestClient` for a more modern imperative style.

## 4. Reactive Asynchronous HTTP Calls with WebClient

`WebClient` provides a reactive API. A method can return a `Mono` or `Flux` instead of waiting for a response and returning an object directly. When the application uses reactive pipelines properly, threads do not need to be held while waiting for I/O.

Configure a `WebClient.Builder` supporting load balancing:

~~~java
@Configuration
public class ReactiveHttpClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

Client calling the inventory service:

~~~java
@Service
public class ReactiveInventoryClient {

    private final WebClient webClient;

    public ReactiveInventoryClient(
            @LoadBalanced WebClient.Builder builder) {
        this.webClient = builder
                .baseUrl("http://inventory-service")
                .build();
    }

    public Mono<InventoryResponse> getInventory(String sku) {
        return webClient.get()
                .uri("/api/inventory/{sku}", sku)
                .retrieve()
                .bodyToMono(InventoryResponse.class);
    }
}
~~~

The method returns a `Mono` immediately as the pipeline is constructed. The request executes when the publisher is subscribed to. When the response arrives, data continues flowing through the reactive pipeline:

~~~java
public Mono<OrderSummary> createOrder(CreateOrderRequest request) {
    return inventoryClient.getInventory(request.sku())
            .flatMap(inventory -> orderService.create(request, inventory));
}
~~~

`WebClient` still makes an HTTP call to a specific service. Load balancing still picks a `ServiceInstance` from the service ID's instance list. The difference is that a reactive client represents results with publishers and enables composing I/O operations without blocking a thread at every step.

Inside a WebFlux handler flow, avoid calling `block()` to wait for a `Mono` or `Flux`. `block()` turns that segment into a synchronous wait and can stall event-loop threads if misused. If the application does not need end-to-end reactivity, `RestClient` is usually simpler and naturally fits an imperative model.

Also remember that `WebClient` does not automatically make all surrounding code non-blocking. If a pipeline invokes blocking JDBC, blocking file reads, or a blocking library on an event-loop thread, non-blocking benefits can be lost. Choose drivers and execution models matching the entire pipeline's model.

## 5. How Does Asynchronous Messaging Differ from Reactive HTTP?

Reactive HTTP is still a request/response model: the client sends a request to an endpoint and typically awaits a response to continue the pipeline. Asynchronous messaging decouples when a message is sent from when the consumer processes it.

For example, when the Order service creates an order, it can emit an `OrderCreated` event. The Inventory service receives the event and updates stock afterward. The producer does not hold an HTTP connection open to the Inventory service waiting for processing to finish. Both sides coordinate via a broker and a message contract.

~~~mermaid
sequenceDiagram
    participant O as Order service
    participant B as Message broker
    participant I as Inventory service
    O->>B: Publish OrderCreated
    B-->>O: Acknowledge message receipt
    Note over O: Continue own execution flow
    B->>I: Deliver message
    I->>I: Process and update inventory
    I-->>B: Acknowledge
~~~

This reduces temporal coupling between producer and consumer, while introducing concerns such as duplicate delivery, message ordering, retries, dead-letter queues, idempotency, and eventual consistency. The producer can receive broker acknowledgment without knowing whether business processing at the consumer has completed.

Spring Cloud LoadBalancer focuses on instance selection for clients communicating via the service-instance model, most commonly HTTP. It does not select consumers for a Kafka topic, balance partitions, or replace broker routing mechanisms. If the system uses messaging, configure and operate the broker/clients according to the corresponding messaging platform's mechanisms.

## 6. Responsibility Boundaries Between Modules

A maintainable design lets each component manage the right kind of decision.

| Component | Responsible For | Should Not Take On |
|---|---|---|
| Calling service's domain/application layer | Business rules, when to call other services, handling business outcomes | Picking instance IP/port, querying the registry directly |
| Service client/adapter | API contract, service-ID endpoints, DTOs, remote error mapping | Deciding physical instances for individual requests |
| Service discovery | Registration, discovery, and providing instance metadata | Business decisions of the request |
| Spring Cloud LoadBalancer | Selecting a `ServiceInstance` per configured policy and supplied data | Executing business logic, managing distributed transactions |
| HTTP transport | Connections, TLS, connection pools, timeouts, sending/receiving HTTP | Deciding which service owns data |
| Resilience components | Retries, circuit breakers, rate limiting, bulkheads per config | Replacing service discovery or fixing business bugs |
| Called service | API and data owned by that service; authentication and business execution | Depending on instance addresses cached manually by callers |

You can place the service client in the adapter/infrastructure layer. The application layer calls an interface expressing business needs, while the adapter implements that interface using `RestClient` or `WebClient`. This keeps the domain free from depending on `@LoadBalanced`, `DiscoveryClient`, or Spring Cloud classes.

Example boundary:

~~~java
public interface InventoryGateway {
    InventoryResult findBySku(String sku);
}
~~~

An adapter in the infrastructure layer can implement this interface using `RestClient`:

~~~java
@Component
public class HttpInventoryGateway implements InventoryGateway {

    private final InventoryClient client;

    public HttpInventoryGateway(InventoryClient client) {
        this.client = client;
    }

    @Override
    public InventoryResult findBySku(String sku) {
        InventoryResponse response = client.getInventory(sku);
        return InventoryResult.from(response);
    }
}
~~~

This is an illustrative organization. In a reactive system, the interface can return a `Mono` or equivalent asynchronous result type. The key is choosing a consistent model at module boundaries and not letting business code arbitrarily mix blocking and reactive calls.

Each service client should represent one API or group of operations with the same owner. Avoid creating a monolithic HTTP utility class holding URLs, DTOs, and logic for every service. A client with clear responsibilities makes it easier to change one service's contract, timeouts, and error policy with minimal impact elsewhere.

## 7. How Do Load Balancing, Timeouts, and Retries Work Together?

Selecting an instance does not guarantee the request will succeed. An instance can stop between selection and connection, the network can be slow, or the service can be overloaded or return a business error.

Distinguish the following mechanisms:

- **Load balancing** picks an instance for a request.
- **Timeout** limits how long to wait for a connection or response.
- **Retry** repeats an operation after an eligible failure.
- **Circuit breaker** temporarily halts calls to a service that is failing continuously.
- **Bulkhead** caps resources allocated to a group of calls.
- **Health check/instance filtering** excludes instances not meeting configured criteria from the selectable list.

These mechanisms can work together, but do not automatically replace one another. For instance, a timeout prevents a request from waiting forever, yet does not select another instance on its own. Retries can generate additional requests and must be configured explicitly. Do not assume every HTTP client automatically retries when an instance fails.

A safe retry policy should consider:

1. **Idempotency:** read operations are usually safer to retry than creating payments or deducting stock. If an operation can be executed twice, require an idempotency key or duplicate-prevention mechanism.
2. **Error type:** transient connection errors or certain status codes may be retryable; validation or business errors generally should not be retried.
3. **Count and time limits:** set attempt limits, backoff, and an overall deadline so requests do not exceed the caller's time budget.
4. **Load on the target service:** simultaneous retries can worsen load on an already overloaded service. Coordinate with circuit breakers, rate limiting, or backoff.
5. **Instance selection on retry:** understand which layer applies retries and whether it asks the load balancer to pick a new instance; do not assume every retry goes to a different instance.

With synchronous communication, the external request's deadline must be large enough for the sum of internal calls plus remaining processing. With reactive flows, propagate and bound time within the pipeline under that same budget. In either model, log or trace the service ID, selected instance when appropriate, call duration, outcome, and error cause for incident investigation.

## 8. Choosing a Communication Model by Need

| Need | Typically Suitable Option | Reason |
|---|---|---|
| Internal API needing immediate result to finish request | RestClient or OpenFeign | Sequential execution flow, easy to follow |
| WebFlux app needing to call multiple I/O services | WebClient | Composes publishers and avoids blocking threads in pipeline |
| Emitting events for other services to process later | Kafka or RabbitMQ | Decouples send time from processing time |
| Long-running task needing status and result lookup | Request-accepting API plus job/event or workflow | Avoids holding an HTTP request open for the entire processing duration |
| Communication needing immediate business feedback | HTTP request/response | Caller needs the result to decide the next step |

No single option is always better. One system can use synchronous HTTP for queries needing immediate responses, `WebClient` for reactive I/O pipelines, and messaging for business events. Choose based on business semantics first, then pick the matching client and load balancing policy.

## 9. Common Design Mistakes

**Hardcoding instance addresses in code.** When instances change or scale, callers must edit configuration or redeploy. Use a service ID and let discovery and the load balancer manage the instance list.

**Letting the business layer select instances itself.** Calling `DiscoveryClient` and picking host/port manually leaks infrastructure details into business logic and easily leads to inconsistent selection logic. Keep instance selection inside the client integration.

**Using WebClient yet calling block inside WebFlux.** This can occupy event-loop threads and reduce concurrency capacity. Return and compose `Mono`/`Flux` throughout the reactive pipeline; switch to blocking only at controlled boundaries when truly necessary.

**Assuming reactive HTTP is messaging.** `WebClient` still requires an HTTP endpoint and response. If the business requires decoupling producer and consumer execution times, use a message broker with suitable delivery semantics.

**Retrying every error.** Retrying non-idempotent operations can create duplicate data or execute business logic multiple times. Classify errors and design idempotency before enabling retries.

**Putting all service-call logic into one shared HTTP utility.** An overly generic utility mixes contracts and error handling across services. Create clearly named clients with focused responsibility per service or API.

## 10. Checklist When Designing Service-to-Service Communication

- [ ] Determine whether the caller needs an immediate response, a reactive pipeline, or just to emit a message.
- [ ] Use a service ID in URIs of HTTP clients configured with load balancing.
- [ ] Ensure discovery supplies the accurate `ServiceInstance` list for the service ID.
- [ ] Choose `RestClient`/`OpenFeign` for imperative flows or `WebClient` for reactive flows.
- [ ] Set timeouts aligned with the business request's deadline.
- [ ] Retry only eligible errors and ensure safety under repeated execution.
- [ ] Define clear responsibility for API contracts, DTOs, and error mapping in the service client.
- [ ] Keep the domain/application layer free from direct dependencies on discovery and load balancing details.
- [ ] For messaging, define acknowledgments, retries, idempotency, ordering, and dead-letter handling.
- [ ] Monitor service IDs, latency, errors, and selected instances to operate the system.

Spring Cloud LoadBalancer provides a key integration point for HTTP communication between services: the application calls by logical name, while the client integration selects a suitable instance to send the request to. Understanding communication styles and module boundaries keeps load balancing at the right layer, keeps business code independent of infrastructure, and ensures errors are handled according to each call's semantics.
