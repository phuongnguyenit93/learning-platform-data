# Testing Business Functions Independently from Spring and the Broker

In a Spring Cloud Stream application, `Supplier`, `Function`, and `Consumer` are the connectors between application code and message streams. They tell the framework how data is produced, transformed, or consumed. However, the business decisions inside those functions still require explicit verification: whether an order qualifies for stock reservation, which input data is rejected, or which persistence action a result translates into.

An effective way to organize this is to separate business logic from integration plumbing. Business functions receive normalized data, perform calculations, and return predictable results. The integration layer is responsible for receiving messages, invoking the business logic, accessing the database, or publishing results through the binder. Because of this boundary, most rules can be tested with JUnit without starting a Spring ApplicationContext or running Kafka, RabbitMQ, or Pulsar.

## 1. Separating Business Logic from Integration

An event-processing flow typically has three layers of responsibility:

| Layer | Responsibility | Appropriate Testing Approach |
|---|---|---|
| Business logic | Checking conditions, computing decisions, determining results | Direct unit tests on plain Java objects or functions |
| Application adapter | Reading data sources, invoking use cases, translating results into port calls | Unit tests with fake or mock dependencies |
| Spring Cloud Stream and binder | Receiving/sending messages, mapping bindings, converting payloads, applying broker settings | Test Binder and integration tests against a broker |

For example, upon receiving `OrderSubmitted`, an inventory service must decide whether stock can be reserved. Rules such as quantity must be greater than 0 and available stock must be sufficient belong to business logic. Reading the message from a topic, converting JSON into a Java record, and issuing a reservation command against the warehouse system belong to integration responsibilities.

If everything is crammed into one large Consumer function, tests often have to initialize many dependencies and become sensitive to infrastructure. When the decision logic is extracted into a plain Java object, valid, invalid, and boundary cases can be tested using only input data.

## 2. Designing Business Logic with Clear Inputs and Outputs

An easily testable function typically has these traits:

- Accepts explicit input data carrying everything required to make a decision.
- Returns an explicit result instead of silently mutating external state.
- Does not directly read the system clock, generate random numbers, or make network calls during calculation.
- Has no dependencies on Spring Context, `MessageChannel`, `KafkaTemplate`, or broker APIs.
- Clearly specifies how invalid data is handled.

The following example models a stock reservation request and business decision using Java records:

~~~java
public record ReservationRequest(
    String orderId,
    String sku,
    int quantity,
    int availableQuantity
) {}

public enum DecisionReason {
    APPROVED,
    INSUFFICIENT_STOCK
}

public record ReservationDecision(
    String orderId,
    String sku,
    int quantity,
    boolean accepted,
    DecisionReason reason
) {}
~~~

The rules live in `ReservationPolicy`. This class does not know whether messages come from Kafka or a direct Java call:

~~~java
import java.util.Objects;

public final class ReservationPolicy {

    public ReservationDecision decide(ReservationRequest request) {
        Objects.requireNonNull(request, "request must not be null");

        if (request.orderId() == null || request.orderId().isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }
        if (request.sku() == null || request.sku().isBlank()) {
            throw new IllegalArgumentException("sku is required");
        }
        if (request.quantity() <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (request.availableQuantity() < 0) {
            throw new IllegalArgumentException(
                "availableQuantity must not be negative"
            );
        }

        if (request.availableQuantity() < request.quantity()) {
            return new ReservationDecision(
                request.orderId(),
                request.sku(),
                request.quantity(),
                false,
                DecisionReason.INSUFFICIENT_STOCK
            );
        }

        return new ReservationDecision(
            request.orderId(),
            request.sku(),
            request.quantity(),
            true,
            DecisionReason.APPROVED
        );
    }
}
~~~

Given the same `ReservationRequest`, `decide` always returns the same `ReservationDecision` or the same validation exception. This determinism keeps tests independent of execution timing or broker state.

## 3. Testing a Function Directly with JUnit

`Function` fits logic that has clear inputs and outputs. You can turn the `decide` method into a `Function` using a method reference:

~~~java
import java.util.function.Function;

Function<ReservationRequest, ReservationDecision> decideReservation =
    new ReservationPolicy()::decide;
~~~

The snippet above uses only standard Java APIs. No Spring startup is required to invoke the function. Only when Spring Cloud Stream registers a `Function` bean does the framework connect the function's input and output to bindings.

Example test with JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class ReservationPolicyTest {

    private final ReservationPolicy policy = new ReservationPolicy();

    @Test
    void approvesReservationWhenStockIsEnough() {
        var request = new ReservationRequest(
            "order-101", "BOOK-01", 2, 5
        );

        var result = policy.decide(request);

        assertEquals(
            new ReservationDecision(
                "order-101",
                "BOOK-01",
                2,
                true,
                DecisionReason.APPROVED
            ),
            result
        );
    }

    @Test
    void rejectsReservationWhenStockIsInsufficient() {
        var request = new ReservationRequest(
            "order-102", "BOOK-01", 4, 3
        );

        var result = policy.decide(request);

        assertEquals(false, result.accepted());
        assertEquals(
            DecisionReason.INSUFFICIENT_STOCK,
            result.reason()
        );
    }

    @Test
    void rejectsInvalidQuantity() {
        var request = new ReservationRequest(
            "order-103", "BOOK-01", 0, 10
        );

        assertThrows(
            IllegalArgumentException.class,
            () -> policy.decide(request)
        );
    }
}
~~~

These three cases test approval, business rejection, and invalid data. You can add boundary cases such as available stock equal to requested quantity, zero stock, blank order ID, and invalid SKU. Each test should describe one concrete rule so that when it fails, the root cause is immediately clear.

With Java records, `equals` is generated automatically from data components. Therefore, comparing record results verifies all output fields. If results contain lists or complex structures, AssertJ can make assertions easier to read.

## 4. Testing a Supplier with a Fake Data Source

A `Supplier` takes no arguments and returns a value each time it is called. In a real application, the data source may read a work queue, query a repository, or pull from an external system. To test fetching without a broker, place the read operation behind a small interface.

~~~java
import java.util.Optional;

@FunctionalInterface
public interface PendingOrderSource {
    Optional<OrderSubmitted> next();
}

public record OrderSubmitted(
    String orderId,
    String sku,
    int quantity
) {}
~~~

The Supplier adapter converts `Optional` into an emitted value. When no data is available, it returns `null` to signal that this poll produces no message:

~~~java
import java.util.function.Supplier;

public final class PendingOrderSupplier
        implements Supplier<OrderSubmitted> {

    private final PendingOrderSource source;

    public PendingOrderSupplier(PendingOrderSource source) {
        this.source = source;
    }

    @Override
    public OrderSubmitted get() {
        return source.next().orElse(null);
    }
}
~~~

Testing the Supplier with an in-memory fake source:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class PendingOrderSupplierTest {

    @Test
    void returnsNextOrderAndThenReturnsNullWhenSourceIsEmpty() {
        var order = new OrderSubmitted(
            "order-201", "BOOK-02", 1
        );
        Deque<OrderSubmitted> queue =
            new ArrayDeque<>(List.of(order));

        PendingOrderSource source =
            () -> Optional.ofNullable(queue.pollFirst());
        var supplier = new PendingOrderSupplier(source);

        assertEquals(order, supplier.get());
        assertNull(supplier.get());
    }
}
~~~

This test verifies that the adapter retrieves the next element properly and signals an empty source. It does not test polling intervals, threads, bindings, or broker message delivery. Those behaviors belong to the Spring Cloud Stream and binder testing layer.

If a Supplier generates fresh data using timestamps or random numbers, consider injecting a `Clock`, ID generator, or data source via the constructor. Tests can then supply deterministic implementations so results are repeatable. Avoid tests that depend on wall-clock time or unpredictable random values.

## 5. Testing a Consumer Through a Business Port

A `Consumer` typically ends a flow with a side effect: writing to a database, calling another service, or emitting a follow-up command. That side effect is not a pure computation. You can isolate it behind an interface to test whether the call is made without connecting to real external systems.

Declaring the port that executes stock reservation:

~~~java
@FunctionalInterface
public interface ReservationPort {
    void reserve(String orderId, String sku, int quantity);
}
~~~

Consumer handling the decision:

~~~java
import java.util.function.Consumer;

public final class ReservationDecisionConsumer
        implements Consumer<ReservationDecision> {

    private final ReservationPort reservationPort;

    public ReservationDecisionConsumer(ReservationPort reservationPort) {
        this.reservationPort = reservationPort;
    }

    @Override
    public void accept(ReservationDecision decision) {
        if (decision.accepted()) {
            reservationPort.reserve(
                decision.orderId(),
                decision.sku(),
                decision.quantity()
            );
        }
    }
}
~~~

Test using a fake port that records invocations:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class ReservationDecisionConsumerTest {

    record Reservation(String orderId, String sku, int quantity) {}

    @Test
    void sendsAcceptedDecisionToReservationPort() {
        List<Reservation> calls = new ArrayList<>();
        ReservationPort fakePort = (orderId, sku, quantity) ->
            calls.add(new Reservation(orderId, sku, quantity));
        var consumer = new ReservationDecisionConsumer(fakePort);

        consumer.accept(new ReservationDecision(
            "order-301",
            "BOOK-03",
            2,
            true,
            DecisionReason.APPROVED
        ));

        assertEquals(
            List.of(new Reservation("order-301", "BOOK-03", 2)),
            calls
        );
    }

    @Test
    void doesNotReserveWhenDecisionIsRejected() {
        List<Reservation> calls = new ArrayList<>();
        ReservationPort fakePort = (orderId, sku, quantity) ->
            calls.add(new Reservation(orderId, sku, quantity));
        var consumer = new ReservationDecisionConsumer(fakePort);

        consumer.accept(new ReservationDecision(
            "order-302",
            "BOOK-03",
            2,
            false,
            DecisionReason.INSUFFICIENT_STOCK
        ));

        assertEquals(List.of(), calls);
    }
}
~~~

The fake port reveals what operation the Consumer requested without requiring a database or broker. For more complex logic, Mockito can verify invocation counts and arguments. A fake is often ideal when you want to model simple business behavior with directly inspectable state.

## 6. Wiring Layers with Spring Cloud Stream Beans

After testing the plain Java classes independently, register them as beans so Spring Cloud Stream can connect them to bindings. For example, a decision service can declare:

~~~java
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ReservationStreamConfiguration {

    @Bean
    Function<ReservationRequest, ReservationDecision> reservationDecision(
            ReservationPolicy policy) {
        return policy::decide;
    }
}
~~~

If the application uses a Consumer, the bean can return an instance of `ReservationDecisionConsumer`. If it uses a Supplier, the bean can return `PendingOrderSupplier`. In an application with multiple function beans, declare `spring.cloud.function.definition` to specify which functions are activated or which combinations are composed. The services illustrated above can be deployed separately, with each service registering only the beans it needs.

The key point is that `ReservationPolicy`, `PendingOrderSupplier`, and `ReservationDecisionConsumer` have explicit constructors and do not pull dependencies from `ApplicationContext`. Unit tests can instantiate them directly. Spring simply handles creating beans, applying configuration, and connecting adapters at runtime.

## 7. Controlling Determinism and External Dependencies

A function becomes hard to test when its result varies with the environment. Common sources of non-determinism include:

| Dependency Source | How to Make Test Outcomes Stable |
|---|---|
| Current time | Inject `java.time.Clock` and supply `Clock.fixed` in tests |
| UUIDs or random numbers | Inject an ID generator or a `Random` with a fixed seed |
| Database | Place reads/writes behind a repository or port; use a fake in unit tests |
| HTTP or external services | Place behind a client interface; test logic with fake responses |
| Environment variables and config | Pass required values through constructors or parameters |
| Broker and message headers | Translate business-relevant data into explicit inputs; test bindings at the integration layer |

For example, if a reservation decision depends on order expiration time, do not scatter `Instant.now()` calls inside the policy. Pass the current timestamp inside `ReservationRequest` or inject a `Clock` into the use case. Tests can then fix time and verify exact expiration boundaries.

Not every class must be completely pure. A Supplier reading data and a Consumer writing data inherently have external effects. The goal is to keep side effects at clear boundaries while core rules have verifiable inputs and outputs.

## 8. Testing Errors and Redelivery Safety

In distributed systems, a message may be redelivered if a consumer completes a side effect before confirming acknowledgment with the broker. Therefore, business-logic tests should cover input edge cases, while adapter tests should verify error and replay handling.

Scenarios worth including in your test suite:

- Payloads missing an identifier or containing invalid required fields.
- Zero quantities, negative quantities, or quantities exceeding business limits.
- Stock levels exactly equal to the requested quantity and one unit below it.
- Storage port throwing a transient error vs. an unrecoverable error.
- The same message ID delivered repeatedly.
- Consumer invoked again after a previous attempt failed.
- A side effect completes, but the process crashes before acknowledging the message.

Idempotency usually belongs at the state persistence boundary or business port. For instance, `ReservationPort` might provide a `reserveIfAbsent` operation keyed by `orderId` or an idempotency key. Unit tests can verify the application layer's deduplication rules using a fake store; integration tests must verify transactions and unique constraints against the real storage system.

Never claim that a Consumer function guarantees exactly-once delivery on its own based solely on a unit test. Delivery semantics result from coordination across the broker, binder, acknowledgment settings, transactions, and how target systems record effects. Isolated tests only verify the responsibilities controlled by application code.

## 9. Choosing the Right Testing Level

Unit tests and integration tests answer different questions. Spinning up a Spring Context for every small rule makes the test suite slow and harder to diagnose. Conversely, unit tests alone will not catch wrong binding names, payload conversion issues, or broker misconfiguration.

| Testing Level | Question Answered | Components Used |
|---|---|---|
| Business unit test | Given this data, what decision does the policy return? | JUnit, AssertJ; plain Java objects |
| Adapter unit test | Given this result, what arguments does the adapter pass to the port? | Fakes or Mockito |
| Spring Cloud Stream Test Binder | Does the payload enter/exit the right bindings and convert properly? | Test Binder, `InputDestination`, `OutputDestination` |
| Broker integration test | How do groups, partitions, acknowledgments, retries, DLQs, and live connections behave? | Real Kafka, RabbitMQ, or Pulsar; optionally via Testcontainers |
| End-to-end test | Does the service chain produce the expected business outcome? | Integrated environment with required components |

For instance, unit testing `ReservationPolicy` does not need to know the destination is `inventory.requested`. The Test Binder verifies that the application wires the right bindings and sends/receives payloads. Integration tests with Kafka verify consumer groups, partition assignment, and retry behavior under your broker configuration.

The Test Binder does not replace a real broker. It is very useful for testing message routing within application scope, but it does not fully simulate all behaviors of Kafka, RabbitMQ, or Pulsar.

## 10. Organizing a Maintainable Test Suite

Place tests close to the classes they verify:

~~~text
src/
  main/
    java/
      .../
        domain/
          ReservationPolicy.java
          ReservationRequest.java
          ReservationDecision.java
        application/
          ReservationDecisionConsumer.java
          PendingOrderSupplier.java
        messaging/
          ReservationStreamConfiguration.java
  test/
    java/
      .../
        domain/
          ReservationPolicyTest.java
        application/
          ReservationDecisionConsumerTest.java
          PendingOrderSupplierTest.java
        messaging/
          ReservationBindingTest.java
~~~

This layout is a reference structure. Smaller projects can keep a simpler package structure as long as business logic does not have to depend on the binder or Spring in order to be tested.

A well-structured test typically has three parts:

1. **Arrange:** construct input data and fake dependencies with deterministic state.
2. **Act:** invoke the single behavior under test.
3. **Assert:** verify the returned result or observable side effect.

Test names should describe both condition and outcome, such as `rejectsReservationWhenStockIsInsufficient`. Avoid generic names like `test1` or testing unrelated rules inside a single method.

Do not mock every object. For pure policies and data records, instantiating real instances is usually simpler. Use fakes or mocks for boundaries such as repositories, HTTP clients, clocks, ID generators, and storage ports. This keeps tests closer to real behavior and reduces coupling to internal implementation details.

## 11. Practice Workflow

When developing a new event-processing function, follow this sequence:

1. Define the business data required in the input and the expected output result.
2. Write a plain Java policy or use case without referencing Spring or broker APIs.
3. Add tests for approval, rejection, boundary values, and invalid inputs.
4. Extract time, IDs, repositories, and external services into replaceable dependencies.
5. Write a `Supplier` or `Consumer` adapter to read from a source or execute side effects through a port.
6. Unit-test the adapter using fakes or mocks to verify dependency calls.
7. Register the `Supplier`, `Function`, or `Consumer` bean and configure the function definition and bindings.
8. Use the Test Binder to verify payload conversion and binding wiring.
9. Use the target broker to test groups, partitions, retries, DLQs, and required delivery behavior.

When business logic is verified independently, changing brokers or binding configurations has minimal impact on tested rules. At the same time, when a test fails, developers can quickly isolate whether the issue lies in business decisions, the adapter, or the messaging integration layer.
