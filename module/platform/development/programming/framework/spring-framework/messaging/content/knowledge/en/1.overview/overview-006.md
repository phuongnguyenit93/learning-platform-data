# Distinguishing Direct Method Calls, HTTP, and Messaging

> Objective: recognize three ways software components communicate with one another, understand their differences in execution flow, coupling, and error handling, and know when to choose each in a Spring application.

## 1. Context: Three Communication Styles Solving Three Different Needs

In a system, one component often needs to ask another component to perform work or announce that an event has occurred. There are three common approaches:

- **Direct method call:** running code invokes a method on another object in the same process.
- **HTTP:** one component sends a request to another component's endpoint and typically receives a response over the network.
- **Messaging:** one component sends a message to a channel or broker; one or more consumers receive and process the message.

HTTP also has a message structure at the protocol level. However, in the context of system design and Spring Messaging, "messaging" usually refers to a producer–consumer model through a message channel or message broker, which can process asynchronously and separate when a message is sent from when it is handled.

No single approach is always better than the other two. The choice depends on whether the sender needs an immediate result, whether the components live in the same process, the degree of independence required, and how the system must recover when a component fails.

## 2. Direct Method Calls

### How It Works

One object holds a reference to another object and calls a method on it. In a typical Spring application, Spring creates beans and injects dependencies via constructors. When one bean calls a method on another bean in the same application, it is still a Java call inside the same JVM.

The snippets below are illustrative code assuming `OrderService` and `InventoryService` are two beans in the same application:

```java
@Service
class InventoryService {
    void reserve(String sku, int quantity) {
        // Check and reserve inventory quantity in stock.
    }
}

@Service
class OrderService {
    private final InventoryService inventoryService;

    OrderService(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    void placeOrder(String sku, int quantity) {
        inventoryService.reserve(sku, quantity);
    }
}
```

The execution flow typically proceeds as follows:

1. `OrderService` calls `placeOrder`.
2. `placeOrder` calls `inventoryService.reserve`.
3. `reserve` runs immediately on the calling thread, unless its implementation explicitly offloads work to an asynchronous mechanism.
4. When `reserve` returns, the calling flow continues; unhandled exceptions propagate back up the call stack.

### Characteristics

- **Low latency:** no need to build an HTTP request, transmit over a network, or traverse a broker.
- **Immediate feedback:** the caller receives the return value or exception on the same control flow.
- **Runtime coupling:** the caller requires the target object and its corresponding method; both components usually must share the same process.
- **Hard to split deployments:** if `InventoryService` needs to move to a separate process, a direct Java call does not turn into a remote call automatically. It must be replaced by another protocol or adapter.
- **Shared context:** two beans can share transactions, security context, or in-memory application state, depending on configuration.

Spring AOP may wrap beans in proxies, for instance to apply `@Transactional`, logging, or security. Such proxies do not imply HTTP or messaging communication; if the call executes within the same JVM, it remains a local call.

### When to Use

Use direct calls when both components belong to the same application, an immediate result is needed, and deployment coupling between them is acceptable. This is usually the right fit for internal services in a modular monolith or business steps that must coordinate synchronously.

## 3. Communication Over HTTP

### How It Works

HTTP enables processes to communicate over a network via requests and responses. A client sends a request to a URL; a request typically includes a method, path, headers, and optionally a body. The server processes it and returns a response with a status code, headers, and optionally a body.

For example, an ordering application calls the inventory service via `POST /inventory/reservations`. The inventory service may return `200 OK` or `204 No Content` on completion, `400 Bad Request` on invalid input, or `503 Service Unavailable` when temporarily unable to serve requests.

In Spring MVC, the endpoint can be declared with a controller:

```java
@RestController
@RequestMapping("/inventory")
class InventoryController {
    private final InventoryService inventoryService;

    InventoryController(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @PostMapping("/reservations")
    ResponseEntity<Void> reserve(@RequestBody ReserveRequest request) {
        inventoryService.reserve(request.sku(), request.quantity());
        return ResponseEntity.noContent().build();
    }
}

record ReserveRequest(String sku, int quantity) {}
```

A client using `RestClient` from Spring Framework 6.1 or newer can invoke that endpoint as follows:

```java
RestClient client = RestClient.builder()
        .baseUrl("http://inventory-service")
        .build();

client.post()
        .uri("/reservations")
        .body(new ReserveRequest("BOOK-01", 2))
        .retrieve()
        .toBodilessEntity();
```

These are illustrative snippets, not a ready-to-run standalone application. A real application requires Spring MVC configuration, client setup, service addresses, DTOs, and proper error handling. On Spring versions older than 6.1, projects can use `RestTemplate` or `WebClient` depending on needs and version.

### Characteristics

- **Clear process boundary:** client and server can run on different machines or containers.
- **Contract expressed via HTTP:** URLs, methods, status codes, headers, and body schemas form the API both sides must agree upon.
- **Convenient request–response:** suits cases where the client needs to query data or know the processing outcome immediately in one interaction.
- **Temporal coupling:** in typical synchronous calls, the client must wait for the server to reply or time out. A slow server or dropped connection directly affects the client's request.
- **Requires network error handling:** a timeout does not prove the server failed to execute the action. The server might have completed processing while the response was lost; retrying a write operation can cause duplicate side effects.
- **Can be used asynchronously:** HTTP clients offer non-blocking or asynchronous APIs, and servers can return `202 Accepted` to indicate a request was accepted. That does not create a message broker or guarantee background execution on its own.

HTTP is commonly used to build REST APIs, integrate systems, serve web/mobile clients, and call services requiring immediate replies. HTTP communication does not inherently provide a durable queue for work that must proceed after the client disconnects.

### When to Use

Use HTTP when one component needs to invoke functionality or query data from another component across a process boundary, and the business flow needs the response to continue. It is the natural choice for public APIs, internal inter-service APIs, and operations requiring immediate feedback.

## 4. Communication via Messaging

### How It Works

In the messaging model, a producer creates a message and sends it to a destination or message channel. A broker or messaging infrastructure receives the message; consumers subscribe to receive and process messages. Producers and consumers do not need to be running at the same time.

General flow:

1. The producer creates a message with a payload and necessary metadata.
2. The producer sends the message to a queue, topic, or channel.
3. The messaging infrastructure receives and routes the message per configuration.
4. The consumer receives the message and performs the work.
5. The consumer confirms processing according to the platform's acknowledgement mechanism. If processing fails, the message may be redelivered or routed to a dead-letter queue depending on configuration.

A message typically expresses one of two intents:

- **Command:** requests a consumer to perform an action, such as `ReserveInventory`. A command is usually directed to one responsible party.
- **Event:** announces that something has occurred, such as `OrderCreated`. An event describes a past occurrence; multiple independent consumers may be interested in it.

Queues are typically used for a pattern where one message is processed by one consumer in a group; multiple consumers can share the load. Topics or publish–subscribe models allow multiple subscribers to receive copies of events according to the platform's mechanism. Exact distribution behavior depends on the broker and configuration.

### Example with Spring JMS

Spring JMS provides `JmsTemplate` to send messages and `@JmsListener` to receive messages from a JMS destination. The following example assumes the application has configured a connection factory, listener container, and an appropriate `MessageConverter` for `OrderCreated` (such as a JSON converter):

```java
@Configuration
@EnableJms
class JmsConfiguration {
}

@Service
class OrderPublisher {
    private final JmsTemplate jmsTemplate;

    OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    void publish(OrderCreated event) {
        jmsTemplate.convertAndSend("orders.created", event);
    }
}

@Component
class BillingListener {
    @JmsListener(destination = "orders.created")
    public void handle(OrderCreated event) {
        // Validate the event and execute the billing workflow.
    }
}
```

The producer sends `OrderCreated` to the `orders.created` destination. The consumer processes the message when it is delivered to the listener. The send method may wait for the broker to confirm acceptance depending on configuration, yet the producer does not wait for the entire billing business workflow to complete.

Spring also has messaging abstractions such as `Message<T>`, `MessageChannel`, and `MessageHandler` in the `org.springframework.messaging` package. They represent payloads, headers, sending channels, and message-handling components; Spring Integration and other integrations can use these abstractions to build processing flows. JMS is one specific messaging integration, not a generic name for every broker.

### Characteristics

- **Decouples send time from processing time:** the producer can finish sending once the infrastructure accepts the message, while consumers process it later.
- **Reduces direct coupling:** producers typically do not need to know which consumer instance will handle the message or where consumers are deployed.
- **Absorbs traffic spikes:** queues can store messages for consumers to process at their current capacity, provided queue capacity and broker policies support the load.
- **Supports multiple consumers:** one event can trigger multiple independent workflows, depending on destination type and subscription configuration.
- **Non-immediate business feedback:** producers normally do not immediately receive the consumer's final result. If a result is needed, the system must design request–reply, callbacks, or a status lookup API.
- **Requires message lifecycle management:** schemas, versions, retention periods, retries, dead-letter handling, ordering, acknowledgements, and duplicate message handling must all be designed.

Messaging does not guarantee "exactly once" by default. Platforms may provide different delivery guarantees such as at-most-once or at-least-once; some platforms offer stronger guarantees within specific scopes and conditions. Applications should still design idempotent consumers to handle message redelivery safely.

### When to Use

Use messaging for background jobs, event-driven processing, multi-consumer integration, queue-based load buffering, or when producers and consumers must be independent in deployment and operational timing. It is a strong choice when processing can complete later and the sender does not need the final outcome immediately.

## 5. Direct Comparison

| Criterion | Direct Method Call | HTTP | Messaging |
|---|---|---|---|
| Typical scope | Same process/JVM | Across processes over a network | Between producers and consumers via channel/broker |
| Exchange mechanism | Method call, arguments, and return value | Request and response | Message with payload and headers |
| Response timing | Usually immediate on the call stack | Usually waits for response; async clients possible | Usually only needs send/acceptance confirmation; consumer processes later |
| Dependency on receiver | Needs target object or proxy | Needs endpoint and API contract | Needs message contract and destination; no need to know consumer instances |
| Business outcome | Direct return value or exception | Status/body or communication error | Usually tracked via events, state, or separate request–reply |
| When receiver is temporarily down | Call usually fails if object is unavailable | Request may time out or fail to connect | Broker can hold messages for later processing, depending on config and durability |
| Best suited for | Internal logic needing immediate results | APIs and synchronous network interactions | Events, background jobs, queues, and multiple consumers |

The table above describes common usage patterns. A system might use asynchronous HTTP on the client, request–reply over messaging, or method calls through proxies. Distinguish the underlying protocol nature and actual runtime mechanics rather than judging solely by API names.

## 6. Key Design Differences

### 6.1. Coupling and Independent Deployment

Direct method calls create the strongest coupling to code structure and object lifecycle. HTTP separates the two sides into distinct processes yet retains temporal coupling: the client needs the server available to accept requests and return responses. Messaging reduces temporal coupling because the broker can retain messages while consumers are offline; in exchange, both sides must agree on message schemas and semantics.

Separating processes does not mean completely eliminating contract coupling. Changing field names, data types, or message meanings can break older consumers. Both HTTP APIs and message events require backwards-compatibility management, versioning, and coordinated deployment practices.

### 6.2. Timeouts, Retries, and Duplicate Operations

With HTTP, if a client times out, it cannot conclude the server did nothing. With messaging, a broker may redeliver a message when no acknowledgement is received. Both situations can cause an operation to run more than once.

To reduce risk:

- Use idempotency keys or stable business identifiers for critical write operations.
- Record processed messages/events within an appropriate transaction boundary so redeliveries do not repeat side effects.
- Retry only recoverable errors; apply attempt limits, backoff, and jitter to avoid amplifying load during outages.
- For messages that still fail after retries, route them to a dead-letter queue and provide an operational workflow to inspect, fix data, or replay safely.

### 6.3. Ordering and Consistency

Do not assume every message is processed in global order. Ordering may only be guaranteed within a specific queue, session, partition, or key group. If per-order ordering matters, choose an appropriate routing key and design consumers to detect out-of-order states.

A database transaction does not automatically span an HTTP call or a broker publish. If an application updates a database and then publishes an event, a failure between the two steps can leave data and events inconsistent. For strong consistency requirements, consider the transactional outbox pattern: write the business change and an outbox record in the same database transaction, then have a separate process publish events from the outbox. Consumers can use an inbox or deduplication table to prevent duplicate processing.

### 6.4. Observability and Tracing

When calls cross multiple processes, isolated logs are insufficient to reconstruct the full flow. Propagate correlation IDs or trace context across HTTP headers and message headers; log message ID, event type, send/receive timestamps, retry count, and processing outcome. Avoid putting secrets or unnecessary personal data into logs.

## 7. Combining All Three in One System

All three communication styles can complement one another. For example, when a customer places an order:

1. `OrderController` receives an HTTP request from the client app and returns a response to the client.
2. `OrderService` directly calls internal components within the same application to validate data and persist the order.
3. After the order is successfully saved, the system emits an `OrderCreated` event so consumers such as billing, email, and analytics process it independently.
4. The client app can later make an HTTP call to query the order status.

Here HTTP fits the API boundary and status queries; direct calls fit logic inside the same process; messaging fits announcing events and triggering workflows that can complete later.

Do not convert every internal call into a message merely to use a broker. If the caller must know the result right away to decide the next step, a direct call or HTTP is usually clearer. Conversely, do not build long chains of synchronous HTTP calls for independent background tasks, because failure or latency in one service can cascade across the whole chain.

## 8. Common Design Mistakes

- **Treating Java calls as remote communication:** injecting another bean in the same JVM does not provide network fault tolerance or deployment separation.
- **Treating an HTTP timeout as proof of failure:** the server may already have processed the request; retrying writes requires idempotency.
- **Using `202 Accepted` as proof of business completion:** this status only indicates the request was accepted for processing, not the final outcome.
- **Assuming sending a message means the consumer finished processing:** successful send and successful handling are two different milestones.
- **Assuming a broker never delivers duplicate messages:** consumers must withstand retries and redelivery.
- **Neglecting event schema management:** payload changes can break older running consumers.
- **Lacking dead-letter handling or operational workflows:** failing messages may loop infinitely or be silently forgotten.
- **Using messaging for queries needing instant answers:** request–reply over a broker is possible but adds complexity; HTTP usually suits synchronous queries better.
- **Not monitoring latency and queue depth:** a steadily growing queue signals that consumers cannot keep up with send rates or are failing.

## 9. Decision Process for Choosing Communication Style

You can use the following questions to decide:

1. Are both components in the same process and deployment lifecycle? If yes, and an immediate result is needed, consider direct method calls.
2. Do the two sides run in separate processes and does the caller need a response to continue? Consider HTTP.
3. Can the work be processed later, does it need load buffering, event fan-out to multiple consumers, or independent producer/consumer operation? Consider messaging.
4. If retries are needed, determine whether the operation is idempotent, what timeouts/acknowledgements mean, and where failed messages go.
5. If consistency between database and messages is required, define transaction boundaries and consider outbox/inbox patterns.
6. If multiple versions of producers and consumers run concurrently, define schema compatibility rules and rollout procedures.

## 10. Conclusion

- **Direct method calls** are the simple, fast choice for internal components within the same process when a result is needed on the calling flow.
- **HTTP** is the standard choice for processes communicating via request–response APIs, especially when callers need direct replies.
- **Messaging** suits events and background tasks when you want to decouple send time from processing time, buffer load, or allow multiple consumers to react independently.

When designing a Spring system, start from requirements around results, latency, deployment boundaries, resilience, and consistency. Choose the communication mechanism that satisfies those requirements, then design contracts, timeouts, retries, idempotency, and operational observability accordingly.