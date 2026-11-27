# Composing Supplier with Consumer and the Runnable Equivalent

## 1. Learning Objectives

In Spring Cloud Function, business logic is modeled with Java interfaces such as `Supplier<T>`, `Function<T, R>`, and `Consumer<T>`. These functions can be registered in `FunctionCatalog`, composed, and used from Java or through HTTP, event, and serverless adapters. The goal is to **reuse the same logic without coupling it tightly to how it is triggered**.

In the **Function Composition** chapter, a special case is connecting a data-producing source to a data-consuming step:

~~~text
Supplier<T> ──get()──> T ──accept(T)──> Consumer<T>
                            |
                            v
                      Final action
~~~

The input of the entire chain **does not need to be passed from outside**, because the `Supplier` generates the data itself. The output of the entire chain also **has no return value**, because the `Consumer` only performs an action. Therefore, the overall behavior is equivalent to Java's `Runnable` interface:

~~~text
Supplier<T> | Consumer<T>  ⇒  Runnable

runnable.run():
    value = supplier.get()
    consumer.accept(value)
~~~

After this lesson, you will know how to:

- Distinguish the contracts of `Supplier`, `Consumer`, and `Runnable`.
- Create a `Runnable` from a `Supplier` and `Consumer` in plain Java.
- Compose by name via `FunctionCatalog.lookup("source|sink")`.
- Analyze how `spring.cloud.function.definition` is configured and why you must not assume a `Runnable` will be triggered automatically by every adapter.
- Identify issues around type compatibility, exceptions, side effects, retries, empty data, and reactive streams.
- Write unit tests and integration tests verifying invocation order, side-effect outcomes, and error cases.

## 2. Contracts of Supplier, Consumer, and Runnable

`Supplier<T>` has the method `T get()`: it creates or fetches a value of type `T` without taking arguments. `Consumer<T>` has the method `void accept(T value)`: it receives a value, performs an action, and returns no result. `Runnable` has the method `void run()`: it takes no arguments and returns no result.

~~~java
import java.util.function.Supplier;
import java.util.function.Consumer;

Supplier<String> source = () -> "ORDER-42";
Consumer<String> sink = value -> System.out.println(value);

String orderId = source.get(); // "ORDER-42"
sink.accept(orderId);          // prints ORDER-42
~~~

Based on those two components, you can create a `Runnable`:

~~~java
Runnable job = () -> sink.accept(source.get());
job.run(); // prints ORDER-42
~~~

| Interface | Method | Has input parameter? | Has return value? |
|---|---|---|---|
| `Supplier<T>` | `T get()` | No | Yes, of type `T` |
| `Consumer<T>` | `void accept(T)` | Yes, of type `T` | No |
| `Runnable` | `void run()` | No | No |
| Composed Supplier + Consumer | `void run()` | No | No |

**`Runnable` does not mean creating a thread or running in parallel automatically.** In Java, calling `job.run()` executes on the current thread. To run asynchronously, you must use an appropriate scheduling/execution mechanism, such as an `Executor`. Having Spring Cloud Function produce a `Runnable` also does not automatically schedule it to run.

### 2.1. Why Not Return the Consumer Type?

A normal `Consumer` requires the caller to pass a value to `accept(value)`. However, in a `Supplier<T> → Consumer<T>` chain, the value is already produced internally by the `Supplier`, so the caller no longer provides an argument.

Similarly, the chain cannot be reasonably described as a `Supplier<T>` outputting `T`: the `T` value has already been passed into the final `Consumer`, and the overall task has no return result.

Thus, `Runnable` accurately expresses the **no-input, no-output** nature of this combination.

## 3. Composing Manually in Plain Java

Consider an example where a source generates an event code and a `Consumer` records processed codes:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;
import java.util.function.Supplier;

public class SupplierConsumerExample {

    public static void main(String[] args) {
        Supplier<String> nextEvent =
                () -> "EVENT-1001";

        List<String> processed = new ArrayList<>();
        Consumer<String> recordEvent = processed::add;

        Runnable processOneEvent =
                () -> recordEvent.accept(nextEvent.get());

        System.out.println(processed); // []
        processOneEvent.run();
        System.out.println(processed); // [EVENT-1001]
    }
}
~~~

Creating the `processOneEvent` lambda **does not invoke** `nextEvent.get()` or `recordEvent.accept(...)`. During a single synchronous `run()`:

1. Java calls `nextEvent.get()` to obtain `"EVENT-1001"`.
2. Java calls `recordEvent.accept("EVENT-1001")`.
3. The `Consumer` saves the event in the list, and then `run()` finishes without returning an object.

### 3.1. Generic Helper for Composing Various Sources and Sinks

Java's `Supplier` does not have `andThen(Consumer)`. If you need to compose them frequently in plain Java, you can write:

~~~java
import java.util.function.Consumer;
import java.util.function.Supplier;

public final class RunnableComposition {

    private RunnableComposition() {}

    public static <T> Runnable combine(
            Supplier<? extends T> source,
            Consumer<? super T> sink) {

        return () -> sink.accept(source.get());
    }
}
~~~

Usage:

~~~java
Supplier<Integer> source = () -> 5;
Consumer<Number> output =
        value -> System.out.println("Value: " + value);

Runnable task = RunnableComposition.combine(source, output);
task.run(); // Value: 5
~~~

`Integer` is a subtype of `Number`, so the `Integer` result from the `Supplier` works for a `Consumer` accepting `Number`. The `? extends T` and `? super T` wildcards in the helper express this flexibility using Java generics.

### 3.2. How It Differs from Consumer.andThen

The `Consumer<T>` interface has an `andThen` method to invoke **two Consumers** sequentially with the same value:

~~~java
Consumer<String> first =
        text -> System.out.println("FIRST: " + text);

Consumer<String> second =
        text -> System.out.println("SECOND: " + text);

Consumer<String> both = first.andThen(second);
both.accept("DATA");
~~~

Here both `first` and `second` receive the `"DATA"` supplied by the caller. The result remains `Consumer<String>`. By contrast, composing `Supplier<String>` with `Consumer<String>` creates `Runnable` behavior: **the input comes from the Supplier and no argument is needed at the final call**.

You cannot write `source.andThen(sink)` on a standard Java `Supplier`; nor should you treat `Runnable` as `Function<Void, Void>` and arbitrarily call `apply(null)`.

## 4. Call Order and Execution Count

The execution formula is:

~~~text
Runnable.run()
   |
   v
Supplier.get()
   |
   | Value T
   v
Consumer.accept(T)
   |
   v
Ends (void)
~~~

An example clearly showing invocation counts:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;
import java.util.function.Supplier;

AtomicInteger sequence = new AtomicInteger();
List<String> accepted = new ArrayList<>();

Supplier<String> nextCode =
        () -> "CODE-" + sequence.incrementAndGet();

Consumer<String> save = accepted::add;

Runnable task = () -> save.accept(nextCode.get());

task.run();
task.run();
task.run();

System.out.println(accepted);
// [CODE-1, CODE-2, CODE-3]
~~~

Each `run()` in this example calls the source **once**, then calls the sink **once**. However, this is synchronous execution with the lambda we wrote, not a guarantee that every adapter will automatically trigger a `Runnable` the same number of times.

If the source always returns the same value, three `run()` calls may cause the `Consumer` to process the same data three times. For a `Consumer` that writes to a database or emits events, this is an **idempotency** and source-state concern, not a composition syntax issue.

## 5. Business Example in Spring Cloud Function

Suppose the system needs to generate a shipment request and record it. Two independent steps:

- `nextShipment: Supplier<Shipment>`: fetches or creates a shipment request to process.
- `recordShipment: Consumer<Shipment>`: records the request.

We use an in-memory source and ledger so we can illustrate the behavior without a real database.

### 5.1. Registering Supplier and Consumer Beans

The following example uses Java 17 and Spring Boot:

~~~java
package example.functions;

import java.util.List;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.function.Consumer;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ShipmentFunctions {

    public record Shipment(String shipmentId, int packageCount) {}

    public static final class ShipmentLedger {

        private final Queue<Shipment> records =
                new ConcurrentLinkedQueue<>();

        public void record(Shipment shipment) {
            records.add(shipment);
        }

        public List<Shipment> snapshot() {
            return List.copyOf(records);
        }
    }

    @Bean
    public ShipmentLedger shipmentLedger() {
        return new ShipmentLedger();
    }

    @Bean
    public Supplier<Shipment> nextShipment() {
        return () -> new Shipment("SHP-204", 2);
    }

    @Bean
    public Consumer<Shipment> recordShipment(
            ShipmentLedger ledger) {

        return shipment -> {
            if (shipment == null
                    || shipment.shipmentId() == null
                    || shipment.shipmentId().isBlank()
                    || shipment.packageCount() <= 0) {
                throw new IllegalArgumentException(
                        "Invalid shipment");
            }
            ledger.record(shipment);
        };
    }
}
~~~

The default bean names will be `nextShipment` and `recordShipment`. When Spring Cloud Function is present and they are within discovery scope, the framework can register both functions into `FunctionCatalog`.

`ShipmentLedger` is a dependency bean of the `Consumer` used to store test records, not a `Function`/`Supplier`/`Consumer` component of the pipeline. Data in `ConcurrentLinkedQueue` exists only in memory, with no transactions, durability, or duplicate write protection.

| Bean name | Java type | Purpose |
|---|---|---|
| `nextShipment` | `Supplier<Shipment>` | Creates a request |
| `recordShipment` | `Consumer<Shipment>` | Validates and records the request |
| Composed beans | `Runnable` by contract | Fetches data itself and records it |

### 5.2. Composing with FunctionCatalog.lookup

Spring Cloud Function provides composition by name: `|` connects beans from left to right. In the `Supplier → Consumer` case supported by the framework, the resulting contract is `Runnable`:

~~~java
package example.functions;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Service;

@Service
public class ShipmentProcessingService {

    private final FunctionCatalog catalog;

    public ShipmentProcessingService(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    public void processOneShipment() {
        Runnable task =
                catalog.lookup("nextShipment|recordShipment");

        if (task == null) {
            throw new IllegalStateException(
                    "Shipment pipeline not found");
        }

        task.run();
    }
}
~~~

The behavior of `task.run()` is equivalent to:

~~~java
ShipmentFunctions.Shipment shipment = nextShipment.get();
recordShipment.accept(shipment);
~~~

The two variables `nextShipment` and `recordShipment` in the illustration are existing function objects; when using the catalog, code looks them up by bean name instead of holding those variables directly.

**Do not call `task.get()` or `task.accept(...)`** in the example above: the overall result is `Runnable`, so the appropriate method to call is `run()`.

> Version note: the example relies on Spring Cloud Function's `Supplier + Consumer → Runnable` composition mechanism. Verify this with an integration test on the exact framework version you are using; adapter support for this kind of composition may differ from direct lookup via `FunctionCatalog`.

### 5.3. Spring Boot Application Class

Place the application class in the same package as the beans for straightforward component scanning:

~~~java
package example.functions;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShipmentApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShipmentApplication.class, args);
    }
}
~~~

Once the application has a Spring Cloud Function context and the proper dependencies, the service can use the Spring-injected `FunctionCatalog`.

## 6. Inserting a Function in the Middle

A real-world pipeline may need to normalize or enrich data before the `Consumer` performs an action. For example:

~~~text
Supplier<Shipment>
         |
         v
Function<Shipment, String>
         |
         v
Consumer<String>
         |
         v
Runnable
~~~

Add two beans to the configuration class:

~~~java
import java.util.function.Consumer;
import java.util.function.Function;

@Bean
public Function<Shipment, String> shipmentLabel() {
    return shipment ->
            shipment.shipmentId() + ":"
            + shipment.packageCount();
}

@Bean
public Consumer<String> auditLabel() {
    return value -> System.out.println("AUDIT " + value);
}
~~~

When declaring these methods inside `ShipmentFunctions`, the `Shipment` type is the record defined in section 5.1. If written in another class, import it or use `ShipmentFunctions.Shipment`.

Looking up the chain:

~~~java
Runnable task =
        catalog.lookup("nextShipment|shipmentLabel|auditLabel");

if (task == null) {
    throw new IllegalStateException("Missing audit pipeline");
}

task.run(); // AUDIT SHP-204:2
~~~

Intermediate contracts:

| Step | Input type | Output type |
|---|---|---|
| `nextShipment` | None | `Shipment` |
| `shipmentLabel` | `Shipment` | `String` |
| `auditLabel` | `String` | None |
| Full chain | None | None — `Runnable` |

A chain starting with a `Supplier`, passing through multiple `Function` steps, and ending with a `Consumer` still has **no-input, no-output** behavior, provided intermediate pairs have compatible contracts and the framework version supports the composition.

### 6.1. Order Cannot Be Reversed Arbitrarily

Do not flip it to `"recordShipment|nextShipment"`: a `Consumer` at the beginning does not produce data for a downstream `Supplier`, while a `Supplier` accepts no input from an earlier step. Nor can you compose `nextShipment|auditLabel` without a step converting `Shipment` to the `String` expected by that `Consumer`.

Do not rely on two types technically converting into strings to bypass business design. The signatures `Supplier<Shipment>`, `Function<Shipment, String>`, and `Consumer<String>` confirm the intent of each connection point.

## 7. Configuring spring.cloud.function.definition

You can specify the chain name in `application.yml`:

~~~yaml
spring:
  cloud:
    function:
      definition: "nextShipment|recordShipment"
~~~

Or in `application.properties`:

~~~properties
spring.cloud.function.definition=nextShipment|recordShipment
~~~

The configuration value describes **the names of the functions to compose**, similar to calling `catalog.lookup("nextShipment|recordShipment")` directly.

Distinguish between:

- `FunctionCatalog.lookup(...)`: Java code explicitly retrieves the composed `Runnable` and calls `run()`.
- `spring.cloud.function.definition`: selects the function/chain name for the integration layer or adapter, if the adapter supports that type.
- Actual trigger mechanism: determined by the Java call, scheduler, HTTP, message binder, or appropriate serverless handler.

The `definition` property **does not automatically schedule a Runnable, create an HTTP endpoint, or connect to a message broker**.

### 7.1. Is Runnable Automatically Triggered by Every Adapter?

No. A `Function<A,B>` pipeline has input/output, `Supplier<T>` is a data-producing source, and `Consumer<T>` is a data sink; they have contracts suited to many transport models. A `Runnable`, however, **has neither input nor output**. Therefore, an adapter designed to map a request body or inbound/outbound bindings may have no natural rule for triggering it.

In Spring Cloud Stream, do not assume a `Supplier|Consumer` chain will be configured by the binder into a message flow like an ordinary `Supplier` or `Consumer`. Depending on the version/integration, a composed `Runnable` may not be a suitable definition for automatic binding.

If the goal is "each incoming broker event passes through a transformation step and is then saved," use `Function<T,R>|Consumer<R>` starting with the input received from the broker. If the goal is "periodically produce data and send it to a broker," a `Supplier` (optionally composed with `Function` steps) is usually more suitable, letting the adapter handle the output binding. For a `Runnable` with no input/output, you may need an **explicit Java call or trigger schedule**.

### 7.2. Example Triggering Runnable from Java

A clear approach is to use a service and invoke it when business logic requires execution:

~~~java
@Service
public class ShipmentJobFacade {

    private final ShipmentProcessingService service;

    public ShipmentJobFacade(ShipmentProcessingService service) {
        this.service = service;
    }

    public void processOne() {
        service.processOneShipment();
    }
}
~~~

This snippet illustrates a synchronous call. If the application needs periodic execution, you need an actual scheduling mechanism (such as `@Scheduled` with scheduling configuration) along with rules for duplicates, errors, and source state. `Runnable` or `spring.cloud.function.definition` alone does not handle those responsibilities.

## 8. Data Types and Business Semantics Between Two Steps

### 8.1. Compatible Pair

~~~java
Supplier<Integer> count = () -> 7;
Consumer<Number> display =
        number -> System.out.println("Count: " + number);

Runnable job = () -> display.accept(count.get());
job.run(); // Count: 7
~~~

`Integer` is a subtype of `Number`, so data from the source fits the `Consumer`.

### 8.2. Incompatible Pair

~~~java
Supplier<String> nextOrderId = () -> "ORD-42";
Consumer<Integer> updateQuantity = value -> {};

// Does not compile because String cannot be passed to Consumer<Integer>.
// Runnable invalid = () ->
//         updateQuantity.accept(nextOrderId.get());
~~~

When using name chains such as `"nextOrderId|updateQuantity"`, the Java compiler cannot see the beans' contracts from a string name. Errors may surface at `lookup` or execution time at runtime. Therefore, inspect the generic types of each bean and write integration tests with the catalog.

### 8.3. Matching Types, Wrong Semantics

Two beans may both use `String` yet represent two different concepts: the `Supplier` produces an **order ID** while the `Consumer` accepts a `String` treating it as an **email**. The pipeline can run, but it writes or sends the wrong data. You can use dedicated records:

~~~java
record OrderId(String value) {}
record EmailAddress(String value) {}
~~~

Then `Supplier<OrderId>` and `Consumer<EmailAddress>` are directly incompatible, catching some design errors early.

## 9. Empty Data, null, and Exceptions

### 9.1. When Supplier Has No New Data

A `Supplier` reading from a queue or database may temporarily have no records. If it returns `null` directly, the downstream `Consumer` may receive an invalid value:

~~~java
Supplier<String> source = () -> null;
Consumer<String> consumer =
        text -> System.out.println(text.length());

Runnable task = () -> consumer.accept(source.get());

// task.run() will throw NullPointerException in Consumer.
~~~

`Runnable` has no built-in "no data, so skip" mechanism. The `Supplier`'s return contract must clearly specify this case. In internal Java code, you can use `Optional<T>` and a matching `Consumer`:

~~~java
import java.util.Optional;
import java.util.function.Consumer;
import java.util.function.Supplier;

Supplier<Optional<String>> source = Optional::empty;

Consumer<Optional<String>> sink =
        value -> value.ifPresent(System.out::println);

Runnable task = () -> sink.accept(source.get());

task.run(); // Prints nothing, no error
~~~

If exposed via a messaging adapter, `Optional.empty()` does not automatically mean "do not emit a message" in every framework. Follow the adapter's specific contract rather than applying the plain Java example verbatim.

### 9.2. If Supplier Throws an Error, Consumer Does Not Run

~~~java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger accepted = new AtomicInteger();

Supplier<String> broken = () -> {
    throw new IllegalStateException("Source not ready");
};

Consumer<String> sink = value -> accepted.incrementAndGet();

Runnable task = () -> sink.accept(broken.get());

try {
    task.run();
} catch (IllegalStateException expected) {
    System.out.println("Could not retrieve data");
}

System.out.println(accepted.get()); // 0
~~~

Because the source failed, the `Consumer` was not invoked. In synchronous Java, the exception normally propagates from `run()` unless handled.

### 9.3. If Consumer Throws an Error, Data May Already Have Been Consumed from Source

~~~java
Supplier<String> source = () -> "ORD-42";

Consumer<String> failingSink = value -> {
    throw new IllegalStateException("Could not record result");
};

Runnable task = () -> failingSink.accept(source.get());

// task.run() throws IllegalStateException.
~~~

The source may already have read, marked, or removed the record before the `Consumer` failed. Composition **does not automatically roll back** source state changes. Design acknowledgments, transactions, retries, or recovery mechanisms suited to the actual source type.

## 10. Side Effects, Retries, and Duplicate Handling

Suppose `nextShipment` reads a record from a queue and `recordShipment` saves the result to a database. Several situations can occur:

1. `Supplier` fails to fetch data: `Consumer` does not run.
2. `Supplier` fetches data successfully, `Consumer` fails to write: you need to know whether the data can be retried.
3. `Consumer` writes successfully, but an error occurs before the system acknowledges it: on retry, there is a risk of recording the same request again.
4. `Runnable` is triggered multiple times concurrently: concurrent runs may process the same record if the source lacks proper locking/claiming mechanisms.

`Supplier|Consumer` **does not automatically provide** cross-system transactions, exactly-once guarantees, or idempotency. Common measures include unique keys on `shipmentId`, idempotent writes, claim/ack states, transactional outbox when needed, and suitable retry policies.

### 10.1. Do Not Assume Runnable Runs Asynchronously

~~~java
Runnable task = () -> System.out.println(
        Thread.currentThread().getName());

task.run(); // Runs on the calling thread.
~~~

Only using `new Thread(task).start()` or an `ExecutorService` moves work to another thread; in a Spring system, managing executors, concurrency limits, and errors must also fit the application architecture. Composing into a `Runnable` only creates an **execution contract**, not a new thread.

### 10.2. Avoid Unsafe Mutable State

Function beans are objects that may be shared across the Spring context. If a `Supplier` or `Consumer` holds mutable state, consider concurrent invocations and appropriate synchronization. `ConcurrentLinkedQueue` in this lesson is a queue-safe test store; it still does not solve transactions, deduplication, or durable persistence.

## 11. The Reactive Supplier and Consumer Case

In Reactor, you must distinguish **element types** from **Publisher types**. A source might have the signature:

~~~text
Supplier<Flux<String>>
~~~

while the sink might accept:

~~~text
Consumer<Flux<String>>
~~~

If written directly in Java, you can construct:

~~~java
import java.util.function.Consumer;
import java.util.function.Supplier;
import reactor.core.publisher.Flux;

Supplier<Flux<String>> source =
        () -> Flux.just("A", "B");

Consumer<Flux<String>> sink =
        flux -> flux.subscribe(System.out::println);

Runnable task = () -> sink.accept(source.get());

task.run(); // Prints A and B in this simple example.
~~~

Here, `run()` hands a `Flux` to the `Consumer`; elements `A` and `B` are processed after subscription. In Reactor's model, when elements are processed depends on schedulers, demand, and operators, not necessarily matching when the `Publisher` was created.

### 11.1. Why Not Assume Every Reactive Combination Becomes a Runnable?

A `Supplier<Flux<T>>` outputs type `Flux<T>`. A normal `Consumer<T>` accepts **a single element `T`**, not an entire `Flux<T>`. Those two signatures differ from `Consumer<Flux<T>>`.

Spring Cloud Function and adapters may have reactive/imperative adaptation depending on the version and function kind, but do not assume `Supplier<Flux<T>>|Consumer<T>` is always automatically supported or preserves subscription properties. Check the framework's actual contract and test at the adapter boundary.

### 11.2. Managing Subscriptions and Errors

The `flux.subscribe(...)` example illustrates the concept; in production applications, calling `subscribe` manually inside a `Consumer` can make error handling, backpressure, and subscription lifecycles harder to manage. Let the appropriate reactive/adapter layer manage subscriptions when the framework prescribes it. Also, a single `run()` call only creates the `Publisher` or initiates subscription, which does not necessarily mean all elements have finished processing.

## 12. FunctionCatalog and Adapters Are Two Separate Layers

| Need | How to implement | Things to note |
|---|---|---|
| Java calls a composed Runnable | `catalog.lookup("nextShipment|recordShipment")` then `run()` | Check version, bean names, and types |
| Java manually composes Supplier/Consumer | `() -> sink.accept(source.get())` | Does not require Spring Cloud Function |
| Select pipeline for an adapter | `spring.cloud.function.definition` | Adapter must support the pipeline type |
| Emit events from a source | `Supplier<T>` and appropriate outbound binding | Poll schedule, retries, serializer |
| Receive events and persist data | `Consumer<T>` or `Function<T,R>|Consumer<R>` | Input binding, ack, errors |
| Run periodically without input/output | Runnable invoked via scheduler/service | Explicit trigger configuration |

Conceptual diagram:

~~~text
                   Spring Cloud Function
               +---------------------------+
Supplier bean ─┤                           │
               │       FunctionCatalog     ├──> Runnable
Consumer bean ─┤        "source|sink"      │        │
               +---------------------------+        │ run()
                                                    ▼
                                            Final side effect
                                                    ▲
                                        Java call / appropriate
                                        trigger schedule
~~~

If an HTTP, event, or serverless adapter is present, verify how that adapter discovers, selects, and triggers functions. **There is no universal automatic connection between Runnable and HTTP requests/message brokers.**

## 13. Testing the Composition

### 13.1. Unit Tests for Order and Invocation Count

The following JUnit 5 test runs purely in Java:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;
import java.util.function.Supplier;

import org.junit.jupiter.api.Test;

class SupplierConsumerOrderTest {

    @Test
    void runsSupplierBeforeConsumerOnEveryRun() {
        List<String> calls = new ArrayList<>();

        Supplier<String> source = () -> {
            calls.add("get");
            return "ORD-42";
        };

        Consumer<String> sink = value -> {
            calls.add("accept:" + value);
        };

        Runnable task = () -> sink.accept(source.get());

        assertEquals(List.of(), calls);

        task.run();
        assertEquals(
                List.of("get", "accept:ORD-42"),
                calls);

        task.run();
        assertEquals(
                List.of(
                    "get", "accept:ORD-42",
                    "get", "accept:ORD-42"),
                calls);
    }
}
~~~

This test confirms that creating the `Runnable` does not trigger the steps, and each `run()` of this lambda executes `get` then `accept`.

### 13.2. Testing That Source Errors Block the Consumer

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;
import java.util.function.Supplier;
import org.junit.jupiter.api.Test;

class SupplierConsumerFailureTest {

    @Test
    void doesNotCallConsumerWhenSourceFails() {
        AtomicInteger accepted = new AtomicInteger();

        Supplier<String> source = () -> {
            throw new IllegalStateException("missing source");
        };

        Consumer<String> sink =
                value -> accepted.incrementAndGet();

        Runnable task = () -> sink.accept(source.get());

        assertThrows(IllegalStateException.class, task::run);
        assertEquals(0, accepted.get());
    }
}
~~~

### 13.3. Integration Tests with FunctionCatalog

When the Spring Boot context has `ShipmentApplication`, `ShipmentFunctions`, and Spring Cloud Function, you can test actual composition by name:

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(classes = ShipmentApplication.class)
class SupplierConsumerCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Autowired
    ShipmentFunctions.ShipmentLedger ledger;

    @Test
    void catalogComposesSupplierAndConsumerAsRunnable() {
        Runnable task =
                catalog.lookup("nextShipment|recordShipment");

        assertNotNull(task);
        task.run();

        assertEquals(
                List.of(
                    new ShipmentFunctions.Shipment(
                        "SHP-204", 2)),
                ledger.snapshot());
    }
}
~~~

This test checks name registration, composition into `Runnable`, and side effects in the Spring context. It requires `spring-boot-starter-test` and a compatible Spring Cloud Function setup. If the store is shared across multiple tests, reset or isolate the context/data to prevent order-dependent tests.

### 13.4. Real-World Testing When Integrating a Transport

If the application has a schedule, broker, or specific adapter, also verify:

- Is the `Runnable` triggered as designed, and the **expected number of times**?
- How does the system behave when the `Supplier` has no data or fails?
- If the `Consumer` writes successfully and the connection drops, does a retry cause duplicate writes?
- Are concurrency limits, timeouts, and error observability in place?
- Does the adapter actually support a `Runnable` definition, or is separate orchestration required?
- With reactive streams, are subscriptions, errors, and stream lifecycles managed properly?

Plain Java tests only verify the `get → accept` principle; catalog tests verify framework composition by name; adapter tests verify operational behavior in the deployment environment.

## 14. Common Mistakes

| Symptom | Possible cause | How to fix |
|---|---|---|
| `supplier.andThen(consumer)` fails to compile | Standard Java `Supplier` has no `andThen` | Use a lambda or Spring composition by name |
| Calling `pipeline.get()` fails | Supplier + Consumer pipeline has a `Runnable` contract | Look up `Runnable` and call `run()` |
| Calling `pipeline.accept(input)` fails | `Runnable` takes no input parameter | Call `run()`, pass no data |
| `lookup` returns nothing | Wrong bean name or unsupported version/config | Check `@Bean`, catalog, and dependencies |
| Task does not run automatically | `Runnable` has no built-in scheduler | Call explicitly from Java or set up an appropriate schedule |
| No HTTP/broker binding appears | Adapter does not bind `Runnable` like Function/Supplier/Consumer | Choose a fitting architecture or use explicit orchestration |
| Consumer processes duplicate records | Source returns same data or retries re-run task | Use business keys, idempotency, source state tracking |
| Runtime type error | Supplier returns a type incompatible with Consumer | Verify intermediate contracts and test catalog |
| Reactive stream emits no results | Not subscribed or stream errored | Check Publisher, subscription, and backpressure |

## 15. Practice Exercises

**Exercise 1 — Plain Java Composition.** Write a `Supplier<Integer>` returning `7` and a `Consumer<Integer>` appending values to a `List<Integer>`. Compose them into a `Runnable`, call `run()` twice, and state the final list.

**Exercise 2 — Distinguishing Contracts.** Explain why `Supplier<String>|Consumer<String>` is equivalent to `Runnable`, whereas `Function<String,Integer>|Consumer<Integer>` is equivalent to `Consumer<String>`.

**Exercise 3 — Inserting a Function.** Given `Supplier<String> raw`, `Function<String,Integer> parse`, and `Consumer<Number> sink`, write a Java expression to create a `Runnable`; determine the corresponding name string if the three beans are registered in `FunctionCatalog`.

**Exercise 4 — Type Compatibility.** Why can't `Supplier<OrderId>` be directly composed with `Consumer<EmailAddress>`? Propose a semantically meaningful transformation step if an email needs to be sent based on an order ID.

**Exercise 5 — Event-Driven Deployment.** You want each message from a broker to trigger a `Consumer` to persist data. Should you select `Supplier|Consumer` and expect the broker to call `run()` for each message? State which contract fits inbound messages better.

**Exercise 6 — Source with No Data.** A `Supplier` occasionally returns `null`. Describe the risk when the `Consumer` does not check for `null`; design a way to represent and pass empty cases in Java.

**Exercise 7 — Repetition and Retries.** A source repeatedly returns the same `Shipment("SHP-204", 2)`, a `Consumer` saves it to a database, and the job runs every minute. Identify two possible problems and ways to prevent duplicate data.

### Solution Hints

- **Exercise 1:** `Runnable task = () -> sink.accept(source.get());`; final list is `[7, 7]`.
- **Exercise 2:** `Supplier` needs no input and `Consumer` produces no output, so the overall chain has neither input nor output. `Function` takes input from the caller, so the overall chain remains a `Consumer`.
- **Exercise 3:** `() -> sink.accept(parse.apply(raw.get()))`; the catalog expression takes the form `"raw|parse|sink"`.
- **Exercise 4:** Needs a step converting `OrderId` to `EmailAddress` based on real data and appropriate business rules.
- **Exercise 5:** Use `Consumer<MessageType>` or `Function<MessageType,R>|Consumer<R>` with the adapter's input binding.
- **Exercise 6:** Avoid uncontrolled `null`; you can use `Optional<T>` with a `Consumer` accepting `Optional<T>` in plain Java.
- **Exercise 7:** Duplicate emissions via schedule/retries and duplicate writes during concurrent runs; requires idempotency, unique keys, source claim/ack, and an appropriate schedule.

## 16. Key Takeaways

- `Supplier<T>` produces data via `get()`, `Consumer<T>` receives data via `accept(T)` and returns no result.
- Composing `Supplier<T> → Consumer<T>` yields **`Runnable`** behavior: `() -> sink.accept(source.get())`.
- In Spring Cloud Function, `FunctionCatalog.lookup("source|sink")` can supply a composed `Runnable` when that composition type is supported; the corresponding call is `run()`.
- `Runnable.run()` does not automatically run in parallel, schedule itself, or trigger on application startup.
- `spring.cloud.function.definition` selects the chain name for integration, but the adapter must support the `Runnable` type; do not assume every HTTP or message binder can bind this composition.
- Type compatibility is a necessary condition; you must also explicitly design for empty data, source errors, side effects, retries, and deduplication for real-world systems.
