# Loose Coupling Between Components

## 1. Objectives and Context

In Spring Integration Core, an integration flow typically consists of multiple components: receiving requests, transforming data, validating conditions, routing, and calling target systems. If each component directly knows how to instantiate, invoke, and handle errors for the next component, a small change can ripple across the entire flow.

**Loose coupling** is a design in which each component depends only on necessary, stable contracts. Components do not need to know too much about how other components are implemented or wired together.

After this lesson, you will be able to:

- Identify different forms of dependencies between processing steps.
- Explain the roles of `Message`, `MessageChannel`, endpoints, and gateways in reducing coupling.
- Use Java DSL to separate business logic from flow wiring.
- Distinguish coupling across source code, data, timing, and operations.
- Choose appropriate test boundaries when changing a component.

The running example is order intake: receiving a request, normalizing the product code, and returning an intake receipt. This is an example within a single Java application; sending messages to a broker or to another service is an additional architectural decision.

## 2. How Does Tight Coupling Appear?

Consider the following style:

```java
public class OrderController {
    private final OrderService orderService;
    private final EmailClient emailClient;
    private final AuditRepository auditRepository;

    public OrderController(OrderService orderService,
                           EmailClient emailClient,
                           AuditRepository auditRepository) {
        this.orderService = orderService;
        this.emailClient = emailClient;
        this.auditRepository = auditRepository;
    }

    public OrderReceipt submit(OrderRequest request) {
        OrderReceipt receipt = orderService.place(request);
        emailClient.sendConfirmation(receipt);
        auditRepository.save(receipt);
        return receipt;
    }
}
```

Dependency injection allows swapping dependency implementations, yet `OrderController` still knows the entire chain of actions. When you need conditional notifications, retries, or a different audit order, the controller must change.

This does not mean direct method calls are always wrong. For a simple local operation, it may be the easiest approach to read. Problems arise when one class both handles business logic and coordinates multiple integration tasks whose change lifecycles differ.

Signs that component boundaries need reconsideration:

- Changing where data is stored forces edits to the request-intake class.
- Changing a notification format forces edits to pricing logic.
- Testing a single transformation requires instantiating an HTTP client and a repository.
- Each step must know the class names, call order, and error policies of all remaining steps.

## 3. Loose Coupling Does Not Mean Zero Dependencies

Two components can only collaborate when they share a contract. Spring Integration turns many direct dependencies into message contracts and wiring configuration; it does not eliminate all constraints.

| Dimension | Sign of Tight Coupling | How to Reduce Coupling | What Must Still Be Agreed Upon |
|---|---|---|---|
| Implementation | Producer calls a concrete class directly | Send via channel, place handling in an endpoint | Expected behavior of the processing step |
| Data structure | Steps arbitrarily read one another's internal state | Use payload and headers with clear contracts | Data types, semantics, and compatibility rules |
| Topology | Every step knows the next step | Place wiring inside Java DSL configuration | The person configuring still must know the flow topology |
| Timing | Caller must wait for the entire chain to finish | Consider a queue or executor | Timeouts, capacity, and how results are received |
| Errors | Downstream errors always dictate caller behavior | Define error-handling boundaries | Retries, transactions, and deduplication |
| Operational deployment | Steps must run together | Split processes only when clearly justified | Messaging infrastructure and version compatibility |

A flow using `DirectChannel` can be loosely coupled in implementation yet still coupled in time: the sender runs on the same thread as the handler and waits for the handler to finish.

Conversely, adding a queue decouples send timing from processing timing, yet the payload might still be overly coupled to the producer's internal data structure.

## 4. Core Components That Help Reduce Coupling

### 4.1. Message: The Exchange Contract

`Message<T>` consists of payload and headers. The payload represents the data to be processed; headers carry supplementary metadata such as correlation IDs or reply-routing information.

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderRequest> message = MessageBuilder
    .withPayload(new OrderRequest("REQ-001", " book-01 ", 2))
    .setHeader("sourceSystem", "web")
    .build();
```

Neither side needs to know the other's internal class structure, but both must understand `OrderRequest` and the meaning of `sourceSystem` if they share that header.

The `Message` structure is immutable at the API level; this does not automatically make the payload object deeply immutable. If the payload contains a mutable `List`, multiple consumers can still observe mutated data. For shared messages, prefer immutable values or copy data at appropriate boundaries.

### 4.2. MessageChannel: The Connection Point

Producers send to a channel rather than calling a specific consumer by name. Application configuration determines which endpoint receives the message.

```text
Producer -> Channel -> Consumer endpoint -> Business handler
```

A channel is an abstraction in Spring Messaging/Spring Integration. A channel may operate solely in memory within the same JVM; the presence of a channel does not mean Kafka, RabbitMQ, or another message broker is being used.

### 4.3. Endpoint: Connecting Handlers to the Message Flow

An endpoint binds a processing step to a message-receiving mechanism. Depending on the endpoint, the step can transform payloads, filter, route, or invoke business logic.

For example, a service activator can call a Java method that accepts `PreparedOrder` and returns `OrderReceipt`. That method does not need to interact with `MessageChannel` or look up the next consumer itself.

With a subscribable channel like `DirectChannel`, the consumer is subscribed to receive messages. With a pollable channel like `QueueChannel`, the consumer needs a poller to pull messages for processing. The intake mechanism is part of flow assembly.

### 4.4. Gateway: Hiding Messaging APIs at the Calling Boundary

A messaging gateway lets callers work through a business interface:

```java
OrderReceipt receipt = orderGateway.submit(request);
```

The caller does not have to build a `Message`, send it to a channel, and figure out how to receive a reply. The gateway converts method calls into messaging interactions according to configuration.

A gateway reduces dependence on messaging APIs, yet the method signature remains a contract. If you change the return type or the meaning of the result, callers are still affected.

### 4.5. Java DSL: Centralizing Wiring Configuration

Java DSL expresses flow structure in one place rather than scattering next-step calls across individual handlers:

```text
Gateway -> orderRequests -> Transformer -> Service activator -> Reply
```

Flow configuration knows how steps connect. Business handlers focus on their domain logic. Consequently, topology changes are usually confined to flow configuration and its associated tests.

## 5. Example: Separating Order Normalization from Intake Business Logic

### 5.1. Prerequisites and Data Contract

The example uses Spring Boot, the `spring-boot-starter-integration` dependency, and Java 17 or higher for `record`. Let Spring Boot manage compatible Spring library versions rather than manually mixing different versions.

Place the public types below in separate Java files in the same package, such as `example.orders`. Place the application class in a root package covering the configuration classes. The snippets focus strictly on the integration flow; no HTTP controller or database is implemented.

```java
package example.orders;

public record OrderRequest(
    String requestId,
    String productCode,
    int quantity
) {}
```

```java
package example.orders;

public record PreparedOrder(
    String requestId,
    String productCode,
    int quantity
) {}
```

```java
package example.orders;

public record OrderReceipt(
    String requestId,
    String productCode,
    String status
) {}
```

`requestId` identifies the business request. `PreparedOrder` represents data that has passed normalization so intake business logic does not have to repeat that step.

These records contain only strings and integers, suitable for demonstrating immutable data exchange. When extending payloads with collections or mutable objects, re-evaluate immutability.

### 5.2. Declaring the Gateway

```java
package example.orders;

import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(
    defaultRequestChannel = "orderRequests",
    defaultRequestTimeout = "1000",
    defaultReplyTimeout = "3000"
)
public interface OrderGateway {
    OrderReceipt submit(OrderRequest request);
}
```

Timeout values are expressed in milliseconds. They bound the corresponding waiting phases of the gateway; do not treat `defaultReplyTimeout` as a mechanism that automatically interrupts a synchronous handler running on the caller's thread.

In the example using `DirectChannel`, if business logic hangs inside the handler, setting a reply timeout does not automatically turn that call into a task that gets canceled after three seconds. Timeouts for HTTP clients, JDBC, or background tasks must be designed where the work actually runs.

### 5.3. Writing a Business Handler Independent of Messaging

```java
package example.orders;

public class OrderService {
    public OrderReceipt place(PreparedOrder order) {
        if (order.quantity() <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        return new OrderReceipt(
            order.requestId(),
            order.productCode(),
            "ACCEPTED"
        );
    }
}
```

`OrderService` knows nothing about channels, gateways, or downstream consumers. You can test this class with plain Java, or reuse it from another adapter.

The `ACCEPTED` result in the example only means the handler accepted the data per its written logic. It does not prove the order was stored durably, paid for, or shipped.

### 5.4. Assembling the Flow with Java DSL

```java
package example.orders;

import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
public class OrderIntegrationConfiguration {

    @Bean
    public MessageChannel orderRequests() {
        return new DirectChannel();
    }

    @Bean
    public OrderService orderService() {
        return new OrderService();
    }

    @Bean
    public IntegrationFlow orderFlow(OrderService orderService) {
        return IntegrationFlow.from("orderRequests")
            .transform(OrderRequest.class, request -> new PreparedOrder(
                request.requestId(),
                request.productCode().trim().toUpperCase(Locale.ROOT),
                request.quantity()
            ))
            .handle(orderService, "place")
            .get();
    }
}
```

```java
package example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.integration.annotation.IntegrationComponentScan;

@SpringBootApplication
@IntegrationComponentScan
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
```

`@IntegrationComponentScan` enables discovery of interfaces annotated with `@MessagingGateway` within the scan scope. In the Spring Boot example, the starter and auto-configuration provide the necessary Integration infrastructure.

Suppose the caller sends:

```java
OrderRequest request = new OrderRequest("REQ-001", " book-01 ", 2);
OrderReceipt receipt = orderGateway.submit(request);
```

The expected result has `productCode` equal to `BOOK-01`, `requestId` equal to `REQ-001`, and `status` equal to `ACCEPTED`.

The reply flow uses the request/reply context established by the gateway. The example needs no separately named reply channel; nor does `OrderService` need to send results back to the gateway itself.

To keep the example concise, input data is assumed to have valid, non-`null` `requestId` and `productCode`. In a real application, you need an explicit validation contract at the intake boundary; data errors should not accidentally become a `NullPointerException` inside a transformer.

### 5.5. How Dependencies Changed

| Component | Must Know | Does Not Need to Know |
|---|---|---|
| Caller | `OrderGateway`, request and reply data | Transformer name, handler method, how the flow is wired |
| Gateway | Input channel and request/reply contract | Internal business steps |
| Transformer | `OrderRequest`, `PreparedOrder`, normalization rules | How the caller receives the result |
| `OrderService` | `PreparedOrder`, `OrderReceipt`, business rules | Channel APIs and how messages are received |
| Java DSL configuration | Topology and connected components | Internal processing details of each step |

If you change the product-code normalization rule, changes stay mostly inside the transformer and that step's tests. If you change the `OrderReceipt` contract, you must evaluate callers too because it is the gateway's public contract.

## 6. Choosing a Channel Also Means Choosing Timing Constraints

### 6.1. DirectChannel: Fewer Intermediaries, Still Synchronous

`DirectChannel` invokes one subscriber to process the message on the sending thread. It does not broadcast the same message to all subscribers like a publish-subscribe mechanism.

The advantages are an easy-to-follow execution flow, low thread-switching overhead, and the ability to participate in a transaction context on the current thread if transaction infrastructure is configured appropriately.

The limitation is that the caller remains coupled to the handler's execution time and outcome. Downstream errors can return to the send or gateway call, often as a messaging exception wrapping the cause.

Do not attach a second subscriber to `DirectChannel` expecting both to receive every order. To broadcast to multiple branches, design publish-subscribe and a corresponding error-handling policy.

### 6.2. QueueChannel: Decoupling Send and Processing with a Queue

You can replace the input channel declaration with:

```java
@Bean
public MessageChannel orderRequests() {
    return new QueueChannel(100);
}
```

This snippet requires importing `org.springframework.integration.channel.QueueChannel`. When a flow starts from a pollable channel, the consuming endpoint must be configured with a poller. For example, the beginning of the flow can change to:

```java
IntegrationFlow.from(
        "orderRequests",
        endpoint -> endpoint.poller(
            Pollers.fixedDelay(100).maxMessagesPerPoll(10)
        )
    )
    // Subsequent transform and handle steps.
```

The snippet above is a configuration replacement, requiring `org.springframework.integration.dsl.Pollers` to be imported while keeping the remaining flow steps. It demonstrates a consumer polling the queue periodically with a maximum number of messages per poll.

Producers can finish sending before business logic processes the message. However, with a gateway returning `OrderReceipt`, the caller still waits for a reply. A queue only changes the execution mechanism; it does not automatically turn a request/reply API into an acknowledgment-only intake API.

Several consequences must be designed explicitly:

- The queue has a capacity of 100; when full, sending may have to wait or fail depending on timeout and invocation method.
- The default in-memory `QueueChannel` does not guarantee messages survive process stops.
- A message may enter the queue and the caller may time out waiting for a reply; processing can still continue.
- If the caller resends, business logic may receive the same request multiple times.

Therefore, `requestId` and an idempotency policy become critical when operations produce side effects. Adding a `requestId` field alone does not create idempotency; you need checking and processing-record mechanisms aligned with the business transaction.

### 6.3. ExecutorChannel: Handing Execution Off to an Executor

`ExecutorChannel` uses an executor to dispatch handler calls. With a typical executor offloading tasks to other threads, it separates the sending thread from the processing thread, though it is not a durable queue.

Actual behavior also depends on the executor and task-rejection policy; for example, a policy running tasks on the calling thread when overloaded can alter expectations of asynchrony.

Do not assume transactions or data in `ThreadLocal` automatically cross executor boundaries. Any business data that must be propagated needs an explicit mechanism; observability context such as traces also requires properly configured propagation.

| Channel Type | Primary Consumption Mode | What the Caller Must Still Care About |
|---|---|---|
| `DirectChannel` | Invokes subscriber on sending thread | Processing duration, synchronous errors |
| `QueueChannel` | Consumer polls queued messages | Capacity, send timeout, latency, data loss if not persisted |
| `ExecutorChannel` | Dispatches via executor | Executor capacity, overload, errors, and cross-thread context |

## 7. How Do Transformer, Router, Filter, and Aggregator Affect Contracts?

These endpoints help separate responsibilities, yet each adds a condition that the flow designer must understand.

- **Transformer** separates data conversion from business logic. Input and output types must be published; downstream should not rely on internal fields outside the contract.
- **Router** separates path selection from handlers. Define the data used for routing and what happens when no route matches.
- **Filter** separates message-acceptance rules. In a request/reply flow, dropping a message without producing an appropriate reply or error can leave the caller waiting until timeout.
- **Aggregator** combines multiple messages into one result. The contract must define correlation rules, group release conditions, and handling for groups that never receive all items.

For example, if you add a filter dropping orders with zero quantity before `OrderService`, do not only verify that the handler did not run. Also verify what the caller observes: receiving a business error, receiving a rejection result, or timing out by design.

Separating components only helps when behavior across steps remains explainable and testable.

## 8. Data Contracts Determine the Real Level of Coupling

### 8.1. Shape Data for the Flow's Purpose

Do not pass an entire JPA entity with lazy associations into every step just because the entity is handy. Consumers can inadvertently become coupled to the persistence context, mutable state, or database table structure.

A DTO or record containing just the data needed for the task usually creates a clearer boundary. However, introducing a DTO does not automatically provide compatibility: changing field semantics or turning an optional field into a required one can still break consumers.

### 8.2. Use Headers Intentionally

Headers fit orchestration details and metadata, such as source system or correlation IDs. Core business data like product lists, quantities, and currency should have an explicit place in the payload contract.

Avoid having handlers implicitly depend on a header created only by an endpoint far upstream. If a header is required, document where it is created, where it is validated, its data type, and how missing values are handled.

Technical objects such as an in-JVM reply channel are not contracts that can be arbitrarily serialized over a network. When moving to a broker, redesign transport boundaries and reply correlation accordingly.

### 8.3. Distinguish Acceptance from Completion

An API returning `ACCEPTED` may only confirm that work was handed off for processing. An API returning `COMPLETED` may require all business work to be finished. Switching between these two meanings while keeping the same interface still misleads callers.

If a flow becomes long-running and asynchronous, you may need to return a request ID and provide status queries or emit outcome events. That is a product-contract change, not merely swapping `DirectChannel` for `QueueChannel`.

## 9. Loose Coupling Must Be Paired with an Error Contract

In the initial example using `DirectChannel`, a quantity validation error raised while the gateway invokes the flow can propagate back to the caller. Do not assume a bean named `errorChannel` automatically intercepts and swallows every synchronous exception in the application.

At poller or asynchronous task boundaries, errors can no longer simply be thrown back up the original sending thread. Spring Integration provides mechanisms to wrap errors as `ErrorMessage` and route them to an error channel depending on the context, component, and configuration.

A complete design must answer:

1. Does the caller receive a direct error, a business response, or an outcome later?
2. Should data errors be retried, or rejected immediately?
3. Does retry wrap only the failing step or the entire chain containing side effects?
4. If the gateway times out while the handler still finishes, how does the system recognize the late result?
5. If database persistence succeeds but notification fails, can you retry without creating a duplicate order?

Retrying an entire flow can repeat operations that already succeeded. A dedicated endpoint for the notification step helps place retries at the right boundary, though idempotency or appropriate tracking is still required when side effects can repeat.

Beyond errors, message paths must be observable. Use consistent business correlation IDs, give endpoints meaningful names where needed, and monitor latency, error counts, and queue depth. Otherwise, a flow with many independent components becomes hard to operate even if the source code is cleanly decoupled.

## 10. Testing Along Dependency Boundaries

### 10.1. Unit Testing the Business Handler

The JUnit Jupiter example below requires no Spring startup:

```java
package example.orders;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class OrderServiceTest {
    private final OrderService service = new OrderService();

    @Test
    void acceptsPositiveQuantity() {
        OrderReceipt receipt = service.place(
            new PreparedOrder("REQ-001", "BOOK-01", 2)
        );

        assertEquals("REQ-001", receipt.requestId());
        assertEquals("ACCEPTED", receipt.status());
    }

    @Test
    void rejectsNonPositiveQuantity() {
        assertThrows(IllegalArgumentException.class, () -> service.place(
            new PreparedOrder("REQ-002", "BOOK-01", 0)
        ));
    }
}
```

This test verifies business rules; it does not verify that the transformer or channel configuration works properly.

### 10.2. Testing the Contract Through the Gateway

With Spring Boot's test dependency, you can test wiring and observable outcomes from the gateway:

```java
package example.orders;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest
class OrderFlowTest {
    @Autowired
    private OrderGateway gateway;

    @Test
    void normalizesProductCodeAndReturnsReceipt() {
        OrderReceipt receipt = gateway.submit(
            new OrderRequest("REQ-001", " book-01 ", 2)
        );

        assertNotNull(receipt);
        assertEquals("REQ-001", receipt.requestId());
        assertEquals("BOOK-01", receipt.productCode());
        assertEquals("ACCEPTED", receipt.status());
    }
}
```

This test catches an unscanned gateway, misnamed channels, a skipped transformer, or a flow failing to produce the expected reply.

When adding queues, executors, routers, or filters, add tests for the new behaviors: overload, timeouts, rejected messages, late results, and duplicate handling. For asynchronous flows, use bounded wait mechanisms instead of arbitrary `Thread.sleep()`; avoid asserting ordering unless the design guarantees that ordering.

## 11. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| Having dependency injection means full loose coupling | DI reduces instantiation coupling; data contracts, timing, and orchestration still need design |
| Every channel is asynchronous | `DirectChannel` executes on the sending thread |
| A gateway is always a remote call | A gateway can simply enter a flow inside the same JVM |
| Switching to a queue means callers never wait | A request/reply gateway still waits for results per contract |
| `Message` is immutable so the payload cannot change | The payload object itself can still be mutable |
| Every subscriber on `DirectChannel` receives the same message | It is point-to-point delivery, not broadcast to all subscribers |
| Having `errorChannel` means all errors are handled uniformly | Error paths depend on synchronous/asynchronous boundaries and configuration |
| Splitting into more endpoints always improves the system | Each boundary must help isolate changes, testing, or operations |

You do not need to turn every method call into a message. A small local calculation is often clearer as an ordinary method. Spring Integration adds value when you need to explicitly model boundaries for transformation, routing, integration, and orchestration.

## 12. Practice Exercises

1. Extract product-code normalization into a separate class and test it without Spring. Keep the gateway test to confirm the flow still uses that normalization.
2. Add a request validation step before business logic. Specify clearly what callers observe for `quantity = 0`; do not let the exercise end with the message simply disappearing.
3. Replace the input channel with a bounded `QueueChannel` and add a poller. Explain why callers of `submit()` may still have to wait.
4. Simulate slow processing and describe the case where the caller times out while business logic continues. Propose how to use `requestId` to recognize repeated requests.
5. Identify where changes belong when adding a notification step: caller, business handler, or flow configuration. Also explain the error contract and the meaning of the return value if the notification step fails.

The evaluation criterion is whether you can point out each dependency that was reduced, each contract that remains, and the behavior callers observe. The number of channels or endpoints is not a direct measure of loose coupling.