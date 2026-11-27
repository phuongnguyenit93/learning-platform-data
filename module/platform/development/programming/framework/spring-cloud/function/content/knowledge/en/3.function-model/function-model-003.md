# Consumer<T>: Processing Data and Side Effects

In **SPRING_CLOUD_FUNCTION**, **Consumer<T>** represents a block of logic that **receives data of type T, performs work, and returns no business result**. This model fits tasks such as writing audit logs, storing events, updating state, or sending notifications. Spring Cloud Function allows declaring this logic as a functional bean, registering it in **FunctionCatalog**, and using it via HTTP, event-driven systems, or serverless adapters depending on the environment.

This lesson belongs to the **Function Model** chapter, focusing on the core question: **How does a Consumer process data, how are side effects controlled, and what must be done when the same data may be processed again?**

## 1. What is Consumer<T>?

In Java, **java.util.function.Consumer<T>** is a functional interface with the abstract method **accept(T value)**:

~~~java
@FunctionalInterface
public interface Consumer<T> {
    void accept(T value);
}
~~~

Meaning of the contract:

- **T** is the input type that the Consumer receives on each invocation.
- **accept(T value)** executes processing on that value.
- **void** means the method returns no result to pass to a next step; **it does not mean processing is guaranteed to succeed**.
- Each call to **accept(...)** can produce side effects: writing to a database, calling an API, emitting metrics, saving a file, or sending an email.
- A Consumer can still throw exceptions. The caller or adapter decides how to handle the error.

Plain Java example:

~~~java
import java.util.function.Consumer;

Consumer<String> audit = message ->
    System.out.println("AUDIT: " + message);

audit.accept("ORDER_CREATED");
// Prints: AUDIT: ORDER_CREATED
~~~

Printing to the console is a **side effect**: it affects the environment outside the function call rather than producing an output value.

### Comparing Models in Spring Cloud Function

| Interface | Signature | Primary Task | Example |
| --- | --- | --- | --- |
| **Supplier<R>** | () → R | Generate data | Generate heartbeat |
| **Function<T, R>** | T → R | Transform data into a result | Calculate a quote |
| **Consumer<T>** | T → void | Receive and process data | Write order history |

If the task needs to return a quote or transformed information, consider **Function<T, R>**. If you want to receive events and record history without emitting a business result, **Consumer<T>** is the natural choice.

## 2. What Are Side Effects and Why Do They Matter?

A pure transformation function computes its result solely from input, whereas a Consumer typically causes external changes:

~~~mermaid
flowchart LR
    A["OrderPlacedEvent"] --> B["Consumer.accept(event)"]
    B --> C["Write audit to database"]
    B --> D["Increment metric"]
    B --> E["Call external service"]
~~~

These changes do not necessarily succeed together. For instance, the database write might succeed while the email call fails; if the system retries **accept(...)**, the event could be written twice.

Therefore, Consumer design needs to answer at least four questions:

1. **Which side effect is the source of truth?** For example, the completed order record in the database.
2. **What happens if the same event arrives twice?** Should it be ignored, updated, or re-executed?
3. **How are failures detected and handled?** Throw an exception for the adapter to handle, or store failure outcomes elsewhere?
4. **Do ordering and atomicity matter?** Is a saved record with an unsent notification an acceptable state, or is a compensating mechanism needed?

**Consumer does not automatically guarantee exactly-once, transactions, or retries.** Those properties depend on business requirements, the data store, and the transport mechanism. Spring Cloud Function provides the function invocation contract; Spring Cloud Stream/binders or the HTTP adapter handle the corresponding protocol layer.

## 3. Complete Example: Receiving and Recording Order Events

Suppose the **order-audit** service receives an event indicating an order has been created. Each event has its own **eventId** so duplicate deliveries can be detected, an **orderId**, and a **total** amount.

In a Spring Boot application using Java 17+ and a compatible Spring Cloud Function version, declare the Consumer bean:

~~~java
package example.function;

import java.math.BigDecimal;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.function.Consumer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OrderConsumerApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderConsumerApplication.class, args);
    }

    @Bean
    AuditStore auditStore() {
        return new AuditStore();
    }

    @Bean
    Consumer<OrderPlacedEvent> recordOrder(AuditStore store) {
        return event -> {
            validate(event);
            store.recordIfAbsent(event);
        };
    }

    static void validate(OrderPlacedEvent event) {
        if (event == null
                || event.eventId() == null
                || event.eventId().isBlank()
                || event.orderId() == null
                || event.orderId().isBlank()
                || event.total() == null
                || event.total().signum() < 0) {
            throw new IllegalArgumentException("Invalid order event");
        }
    }

    public record OrderPlacedEvent(
        String eventId,
        String orderId,
        BigDecimal total
    ) {}

    public record AuditEntry(
        String orderId,
        BigDecimal total
    ) {}

    public static class AuditStore {
        private final ConcurrentMap<String, AuditEntry> entries =
            new ConcurrentHashMap<>();

        public boolean recordIfAbsent(OrderPlacedEvent event) {
            AuditEntry entry =
                new AuditEntry(event.orderId(), event.total());

            return entries.putIfAbsent(event.eventId(), entry) == null;
        }

        public int size() {
            return entries.size();
        }
    }
}
~~~

**How to read the example:**

- **recordOrder** is the functional bean name that Spring Cloud Function can detect and look up.
- The **Consumer<OrderPlacedEvent>** type states that each call must supply a structured event.
- **validate(...)** rejects data violating the contract before causing side effects.
- **AuditStore.recordIfAbsent(...)** illustrates preventing duplicate writes using the **eventId** key.
- Because **accept(...)** returns **void**, the caller does not receive the **boolean** value from **recordIfAbsent(...)**. Success or failure is reflected through side effects or exceptions.

**Intentional limitation of the example:** **AuditStore** uses an **in-memory ConcurrentHashMap** to illustrate idempotency logic and testing, **not durable storage**. Data is lost when the application restarts and is not shared across instances. In a real deployment, replace it with durable storage with a unique constraint on **eventId**, appropriate transaction handling, and a policy for cases where the same ID has a different payload.

### Running the Logic Without HTTP or a Broker

The Java contract allows direct invocation:

~~~java
var app = new OrderConsumerApplication();
var store = new OrderConsumerApplication.AuditStore();

Consumer<OrderConsumerApplication.OrderPlacedEvent> consumer =
    app.recordOrder(store);

consumer.accept(new OrderConsumerApplication.OrderPlacedEvent(
    "evt-1001", "ORD-1001", new BigDecimal("250000")
));

System.out.println(store.size()); // 1
~~~

Calling **accept(...)** requires no transport protocol. This is why a Consumer can remain decoupled from HTTP and messaging.

## 4. Triggering a Consumer via HTTP

An HTTP adapter can turn a request into an **OrderPlacedEvent** input and then invoke the Consumer. In a Spring Boot application with the Spring Cloud Function web starter:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-function-web</artifactId>
</dependency>
~~~

When the application runs on the default port 8080 and the **recordOrder** bean is exposed via the web adapter, you can send:

~~~bash
curl -i -X POST http://localhost:8080/recordOrder \
  -H "Content-Type: application/json" \
  -d '{"eventId":"evt-1001","orderId":"ORD-1001","total":250000}'
~~~

Processing path:

~~~text
HTTP request JSON
  -> HTTP adapter / conversion
  -> OrderPlacedEvent
  -> recordOrder.accept(event)
  -> AuditStore
  -> HTTP adapter completes response
~~~

A Consumer **returns no business data**. Therefore, do not design clients to expect an **OrderQuote**, a result JSON payload, or assume a specific HTTP status code solely from the Consumer signature. Status codes and exception mapping depend on the adapter, framework version, and application configuration.

A state-changing endpoint should use an appropriate HTTP method such as **POST**, along with authentication, authorization, request validation, and protection against client retries. Avoid exposing a Consumer as a data-modifying action over GET.

If the API must return a result object according to the business contract, consider a **Function<Request, Response>** or an HTTP controller wrapping the service layer. Do not try to return results from **Consumer<T>** by mutating the request body or using shared state.

## 5. Registering, Looking Up, and Invoking with FunctionCatalog

Spring Cloud Function manages **Supplier**, **Function**, and **Consumer** beans through **FunctionCatalog**, allowing adapters to invoke logic by function name.

~~~mermaid
flowchart TD
    A["Spring bean: recordOrder"] --> B["FunctionCatalog"]
    C["HTTP adapter"] --> B
    D["Stream binder"] --> B
    E["Serverless adapter"] --> B
    B --> F["Consumer.accept(OrderPlacedEvent)"]
    F --> G["Side effect: AuditStore"]
~~~

To illustrate calling from Java code within the same Spring application:

~~~java
import java.util.function.Consumer;
import org.springframework.cloud.function.context.FunctionCatalog;

public class CatalogInvoker {
    private final FunctionCatalog catalog;

    public CatalogInvoker(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    public void invoke(OrderConsumerApplication.OrderPlacedEvent event) {
        Consumer<OrderConsumerApplication.OrderPlacedEvent> handler =
            catalog.lookup("recordOrder");

        if (handler == null) {
            throw new IllegalStateException("Consumer not found");
        }

        handler.accept(event);
    }
}
~~~

To receive **FunctionCatalog** from Spring, the caller class must be registered in the application context (e.g., via **@Component** or **@Bean**). The catalog may return a wrapper that supports type conversion and composition; do not assume the looked-up object has the exact same implementation class as the original lambda.

When an application has multiple functional beans, explicitly declare the definition to expose or bind:

~~~yaml
spring:
  cloud:
    function:
      definition: recordOrder
~~~

The name **recordOrder** must match the bean/function definition name. A misspelled name, missing adapter, or mismatched binding configuration can prevent the adapter from finding the intended Consumer.

## 6. Composition and Consumer Limitations

Java provides **Consumer.andThen(...)** to execute two Consumers sequentially:

~~~java
Consumer<String> validateCode = code -> {
    if (code == null || code.isBlank()) {
        throw new IllegalArgumentException("Code must not be blank");
    }
};

Consumer<String> logCode =
    code -> System.out.println("Accepted: " + code);

Consumer<String> pipeline = validateCode.andThen(logCode);

pipeline.accept("ORDER_CREATED");
~~~

The second Consumer runs only if the first completes normally. If the first step throws an exception, the next step is not executed. However, if the first step already caused a side effect and the next step fails, **andThen does not roll back the first side effect**.

In Spring Cloud Function, composition often pairs a **Function<T, R>** step to normalize data with a **Consumer<R>** at the end of the chain.

Example adding a raw input type and a transformation bean:

~~~java
public record RawOrderEvent(
    String eventId,
    String orderId,
    String total
) {}

@Bean
java.util.function.Function<RawOrderEvent, OrderPlacedEvent>
        parseOrder() {
    return raw -> new OrderPlacedEvent(
        raw.eventId(),
        raw.orderId(),
        new BigDecimal(raw.total())
    );
}
~~~

Declare **RawOrderEvent** and **parseOrder** within the application configuration class context where **OrderPlacedEvent** and required imports are available. Then select the chain:

~~~yaml
spring:
  cloud:
    function:
      definition: parseOrder|recordOrder
~~~

Data flows in order:

~~~mermaid
flowchart LR
    A["RawOrderEvent"] --> B["parseOrder"]
    B --> C["OrderPlacedEvent"]
    C --> D["recordOrder"]
    D --> E["AuditStore"]
~~~

**Because a Consumer has no output**, placing a Consumer at the end of a **Function → Consumer** pipeline makes sense; you cannot take business output from a Consumer to pass directly to a subsequent Function. The output type of **parseOrder** must be compatible with the input type of **recordOrder**.

This **parseOrder** example uses **BigDecimal(String)** and can throw an exception if the amount string is malformed or null. In a real application, define validation rules, digit limits, and appropriate error messages before producing side effects.

## 7. Consumer in Event-Driven Systems with Spring Cloud Stream

Using **Consumer<T>** is a common way to process **incoming events without emitting output events**. With Spring Cloud Stream and an appropriate binder, the **recordOrder** bean can be bound to a topic or queue.

~~~yaml
spring:
  cloud:
    function:
      definition: recordOrder
    stream:
      bindings:
        recordOrder-in-0:
          destination: orders.placed
          group: order-audit
~~~

Explanation:

- **recordOrder-in-0** is the input binding name of the **recordOrder** Consumer.
- **destination: orders.placed** specifies the logical destination receiving events; actual mapping depends on the binder/broker.
- **group: order-audit** establishes a consumer group identity according to the binder's semantics. This can help instances in the same group share load instead of every instance receiving every event.
- There is no **recordOrder-out-0**, because a Consumer creates no business output binding.

Processing flow:

~~~mermaid
flowchart LR
    A["Broker: orders.placed"] --> B["Stream binder"]
    B --> C["Message conversion"]
    C --> D["recordOrder.accept(event)"]
    D --> E["Audit database"]
~~~

The configuration above is only the routing part. The application still requires **Spring Cloud Stream**, the corresponding binder (Kafka, RabbitMQ, etc.), an available broker, and connection configuration. To send a result to another topic, **Function<T, R>** fits the one-input/one-output model better; Consumer is used when the side effect is the final processing destination.

**Difference from HTTP:** brokers can redeliver messages upon errors, timeouts, rebalances, or according to system delivery policies. The Consumer must handle duplicates properly; you cannot conclude each event invokes **accept(...)** exactly once solely from the binding configuration.

## 8. Consumer<Message<T>> When Headers and Metadata Are Needed

A standard Consumer only needs the business payload:

~~~java
Consumer<OrderPlacedEvent> recordOrder
~~~

If the logic needs to read a correlation ID, source name, or other headers, you can use:

~~~java
Consumer<org.springframework.messaging.Message<OrderPlacedEvent>>
~~~

Example message-handling bean added to the configuration class:

~~~java
import org.springframework.messaging.Message;

@Bean
Consumer<Message<OrderPlacedEvent>> recordOrderMessage(AuditStore store) {
    return message -> {
        OrderPlacedEvent event = message.getPayload();
        Object correlationId =
            message.getHeaders().get("correlationId");

        validate(event);
        store.recordIfAbsent(event);

        // Use correlationId for logging/tracing if needed.
        // Do not treat sender-supplied headers as verified data.
    };
}
~~~

**Message<T>** wraps **payload** and **headers**. Headers support observability, routing, or business processing when a clear data contract exists. However, brokers and adapters may map, filter, or alter header representations; do not assume all headers are automatically preserved across HTTP, Kafka, RabbitMQ, and serverless.

In particular, **framework-generated message IDs** do not replace the business idempotency key **eventId**. A message can be reconstructed with different metadata during retries, while the side effect relates to the same business event.

## 9. Idempotency: The Foundation for Controlling Side Effects

A Consumer invoked twice with the same event **must not accidentally create two audit records, two charges, or two identical emails**, if business rules require executing only once.

Timeline example:

~~~text
T1: Broker delivers evt-1001 to Consumer
T2: Consumer writes audit successfully
T3: Processing acknowledgment to broker is interrupted
T4: Broker redelivers evt-1001
T5: Consumer checks eventId, skips duplicate write
~~~

**Idempotency** is the property where repeating an operation with the same business request causes no further change to the desired outcome after the first success. In the in-memory example, **putIfAbsent(eventId, entry)** writes to the map only when the key does not yet exist. Real-world solutions must be durable:

| Scenario | Common Approach | Notes |
| --- | --- | --- |
| Write a business record by eventId | Unique constraint + INSERT with conflict handling | Writing and marking processed should be in an appropriate transaction |
| Execute a money transfer | Idempotency key at the transaction service | Must verify matching payload and previous result |
| Send email or call external API | Idempotency key supported by target service; store send state | No automatic shared transaction with local database |
| Update order status | Version, valid state transitions, optimistic locking | Prevent older events from overwriting newer events |
| Write audit log | Unique record by event ID | Decide clearly how to handle same ID with different payload |

Do not build durable idempotency using separate **SELECT then INSERT** operations without a unique constraint: two concurrent consumers can both read "does not exist" and both insert. Use constraints/transactions or atomic operations guaranteed by the data store.

When a Consumer both writes to a database and emits another event, consider the **transactional outbox** pattern: save the business state and the outbound event record in the same database transaction, then have a separate process publish it to the broker. This reduces the risk of "saved successfully but failed to publish"; the receiving system should still support idempotency.

## 10. Errors, Retries, and Dead-Letter Handling

If **accept(event)** throws an exception, the Consumer has no return value to describe the error itself. The adapter decides how to map it: fail the HTTP request, broker retry, move the message to a dead-letter destination, or report failure to the serverless runtime.

Distinguish three error categories:

1. **Contract-violating data:** missing eventId, negative total, unreadable JSON. Usually pointless to retry indefinitely with an unchanged payload.
2. **Transient errors:** overloaded database, external service timeout. Can be retried with limits and backoff.
3. **Stateful business errors:** order already canceled, out-of-order data, transaction already processed. Requires clear policies to reject, ignore, compensate, or record the error.

Example Consumer with transparent error reporting:

~~~java
@Bean
Consumer<OrderPlacedEvent> strictRecordOrder(AuditStore store) {
    return event -> {
        validate(event);
        store.recordIfAbsent(event);
        // If store throws an exception due to infrastructure failure,
        // allow the adapter to detect it and apply the error policy.
    };
}
~~~

**Do not swallow every exception** with a **catch (Exception e)** block just to log and exit: from the binder or adapter's perspective, the task may be mistaken for successful, losing the chance to retry properly.

Conversely, uncontrolled retries can also cause overload. With Spring Cloud Stream, retries, dead-letter queues, acknowledgments, and error policies **depend on the binder and configuration**; verify the exact binder in use before setting retry thresholds and conditions. With HTTP, an exception in a Consumer also **does not by default** become a specific status code without verifying how the adapter maps errors.

### Distinguishing Idempotency and Transactions

- **Transactions** protect the consistency of operations that can be managed within the same transactional boundary.
- **Idempotency** protects against *repeated requests* or *redelivery of the same event*.
- **Retries** help recover from transient failures while simultaneously increasing the chance that side effects execute again.

These three mechanisms complement one another and cannot arbitrarily replace each other.

## 11. The Same Consumer in a Serverless Environment

A serverless runtime can receive a payload, convert it to **OrderPlacedEvent**, look up **recordOrder** via FunctionCatalog, and invoke **accept(event)** using a compatible adapter.

~~~text
Cloud event / invocation
  -> serverless adapter
  -> OrderPlacedEvent
  -> Consumer.accept(event)
  -> side effect (database, API...)
~~~

The Java function can remain unchanged, but deployment still requires configuring the handler, packaging, dependencies, triggers, timeouts, and resource permissions for the specific platform.

Do not rely on an in-memory **ConcurrentHashMap** inside a serverless instance to enforce idempotency: instances may be created fresh, run in parallel, shut down, or share no memory. For critical side effects, use durable storage with proper concurrency control.

If a handler receives multiple records in a single invocation, per-record error handling, batch retries, and acknowledgment policies must follow the adapter's contract. There is no universal ack rule across all serverless environments.

## 12. Synchronous, Asynchronous, and Reactive Consumers

In the common **Consumer<OrderPlacedEvent>** form, **accept(...)** executes synchronously according to its implementation. If the Consumer performs long blocking I/O inside, adapter processing time and throughput will be affected.

Distinguish the variants:

| Consumer Form | What Does the Function Receive? | Things to Watch |
| --- | --- | --- |
| **Consumer<T>** | A single value T | Timeouts, blocking I/O, exceptions, and concurrency |
| **Consumer<Message<T>>** | Payload and headers | Metadata conversion and reliable headers |
| **Consumer<Flux<T>>** | A reactive publisher | Must manage subscription, errors, and stream lifecycle |

With Project Reactor, you may encounter the signature:

~~~java
Consumer<reactor.core.publisher.Flux<OrderPlacedEvent>>
~~~

However, a reactive Consumer **returns no result publisher to the framework**. If you call **subscribe()** manually inside the Consumer body, you take responsibility for asynchronous errors, lifecycle, subscription cancellation, and signaling completion to the adapter. Long-running side effects using only **doOnNext(...)** also need to be triggered by an appropriate subscription; otherwise, the pipeline may not run.

If you need a reactive pipeline where the framework explicitly manages output streams and errors, consider **Function<Flux<T>, Flux<R>>** or a reactive integration model supported by the adapter, rather than creating ad-hoc subscriptions inside a Consumer.

### Thread Safety and Shared State

Functional Spring beans are typically reused across multiple invocations, potentially on different threads. Never let **Consumer<T>** write to an unsynchronized mutable variable:

~~~java
// Not thread-safe if multiple threads call accept concurrently:
int[] processed = {0};
Consumer<String> unsafe = value -> processed[0]++;
~~~

For per-instance statistics you can use **AtomicLong/LongAdder**, though production metrics should integrate an appropriate observability library. For critical business data, in-JVM synchronization does not solve multi-instance concurrency either: concurrency control must live in the shared data store.

## 13. Testing Consumers and Side Effects

Unlike a Function that returns a value, a Consumer requires testing **the state after accept(...)** or interactions with dependencies. Unit tests do not need to start an HTTP server or broker.

JUnit 5 example for the **OrderConsumerApplication** class already defined:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.util.function.Consumer;

import org.junit.jupiter.api.Test;

class OrderConsumerApplicationTest {

    private final OrderConsumerApplication app =
        new OrderConsumerApplication();

    private final OrderConsumerApplication.AuditStore store =
        new OrderConsumerApplication.AuditStore();

    private final Consumer<OrderConsumerApplication.OrderPlacedEvent> consumer =
        app.recordOrder(store);

    @Test
    void recordsOneEvent() {
        consumer.accept(event("evt-1"));

        assertEquals(1, store.size());
    }

    @Test
    void ignoresDuplicateEventId() {
        consumer.accept(event("evt-1"));
        consumer.accept(event("evt-1"));

        assertEquals(1, store.size());
    }

    @Test
    void rejectsInvalidEventWithoutRecordingIt() {
        var invalid = new OrderConsumerApplication.OrderPlacedEvent(
            "evt-2", "ORD-2", new BigDecimal("-1")
        );

        assertThrows(IllegalArgumentException.class,
            () -> consumer.accept(invalid));

        assertEquals(0, store.size());
    }

    private static OrderConsumerApplication.OrderPlacedEvent event(String id) {
        return new OrderConsumerApplication.OrderPlacedEvent(
            id, "ORD-1", new BigDecimal("250000")
        );
    }
}
~~~

The test suite verifies three contracts:

- A valid event creates exactly one record.
- Repeating the same **eventId** does not increase the record count in the store.
- An invalid event creates no side effects.

This only tests at the **single-instance, in-memory** level. Before deploying to production, add integration tests with a real database or suitable test environment to verify unique constraints, transactions, and behavior when multiple instances write concurrently. For Spring Cloud Stream, add tests for input binding, content type, retries, and dead-letter/error message handling. For HTTP, test POST, payload errors, and status code policies. For serverless, verify event mapping and trigger behavior under the specific runtime.

## 14. Common Deployment Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Events not received | Wrong bean name, function definition, or input binding | Check **recordOrder**, **recordOrder-in-0**, binder, and destination |
| HTTP call succeeds but no durable data appears | Consumer only writes in memory or lacks a real repository | Inspect side effects and replace the demo store with durable storage |
| Same event creates two records | Broker redelivery, retries, missing idempotency key | Create a unique constraint on eventId and design duplicate handling |
| Failing events are silently lost | Catching exceptions only to log them | Define clear reject/retry rules and propagate errors to the adapter when needed |
| Task is slow or hangs | **accept(...)** performs long blocking I/O | Set timeouts, limit concurrency, measure latency, and monitor errors |
| Results differ across instances | Using mutable variables or local memory as the source of truth | Move business state to a shared data store |
| Important metadata lost | Converting **Message<T>** to **T** without preserving needed info | Define a header contract and retain metadata at the appropriate layer |
| Two side effects only partially succeed | No transaction/outbox or compensating mechanism | Define transaction boundaries and use outbox where appropriate |

## 15. Practice Exercises

**Exercise 1 — Basic Consumer.** Create a **Consumer<PaymentEvent>** that stores payment history. Choose an in-memory storage type for a demo, then write unit tests checking the record count after one and two invocations with the same **eventId**.

**Exercise 2 — Validation and errors.** Add rules requiring a non-blank transaction ID and an amount greater than 0. Test that invalid events leave no side effects. Explain why throwing an exception in a Consumer is not sufficient by itself to guarantee HTTP always returns a desired status code.

**Exercise 3 — Composition.** Write a **Function<RawPaymentEvent, PaymentEvent>** to normalize data, and connect it to **Consumer<PaymentEvent>** using the definition **parsePayment|storePayment**. Draw a diagram of the data types passing through each step.

**Exercise 4 — Messages and tracing.** Define **Consumer<Message<PaymentEvent>>**, read the **correlationId** header, log according to project standards, and still use **eventId** in the payload as the idempotency key. Identify the risks of blindly trusting a client-supplied header.

**Exercise 5 — Production scenario analysis.** A Consumer writes a database record and then calls an email API. The database write succeeds, the API times out, and the broker redelivers the event. Design a solution that prevents duplicate writes, distinguishes transient errors from data errors, and proposes a way to avoid losing emails. Describe the roles of unique constraints, idempotency keys, and the transactional outbox.

### Key Takeaways

- **Consumer<T>** has the signature **T → void**; the **accept(T)** method processes input, typically producing side effects.
- **Spring Cloud Function** registers Consumers in **FunctionCatalog** and allows HTTP, Stream, or serverless adapters to trigger the same logic with appropriate configuration.
- **Consumers return no business result**; composition with a Consumer should end at the processing step, such as **Function<T, R> → Consumer<R>**.
- For Consumers with side effects, you must design **validation, idempotency, transactions, retries, error handling, and observability** around real boundaries.
- Unit tests verify state/interactions after **accept(...)**; integration tests verify conversion, bindings, transactions, and adapter behavior.
