# Composing Function with Consumer

## 1. Learning Objectives

Spring Cloud Function lets you develop business logic as reusable `Supplier`, `Function`, and `Consumer` components, independent of whether the logic is invoked from Java, HTTP, events, or serverless platforms. In the **Function Composition** chapter, the **Function ending in a Consumer** pattern is especially useful when data needs to be normalized, validated, and then handed off to a final action, such as recording an order or publishing an event.

Example processing flow:

~~~text
Input data A
      |
      v
Function<A, B>  --apply(A)--> B
      |
      v
Consumer<B>     --accept(B)--> final action, returns no value
~~~

The overall behavior is **`Consumer<A>`**: it receives a value of type `A`, transforms it into `B`, and passes `B` to the `Consumer`. In plain Java, you can express this as `input -> sink.accept(transform.apply(input))`. Spring Cloud Function also supports composing function beans registered in `FunctionCatalog` by name.

After this lesson, you will be able to:

- Recognize the type contracts of `Function<A, B>` and `Consumer<B>`, along with `apply`/`accept`.
- Predict processing order, when side effects occur, and the resulting type of the composed pipeline.
- Write the composition in plain Java, then compose beans using `FunctionCatalog.lookup("transform|sink")`.
- Select the pipeline with `spring.cloud.function.definition` and understand the difference between logic configuration and HTTP/message/serverless adapters.
- Distinguish `Consumer.andThen` from `Function → Consumer` composition.
- Test transformation results, verify `Consumer` invocation, handle errors, and assess retry risks.

## 2. The Two Interfaces and Their Input/Output Contracts

### 2.1. Function Transforms Data and Returns a Result

The Java interface `java.util.function.Function<T, R>` has the method:

~~~java
R apply(T input);
~~~

Example:

~~~java
import java.util.Locale;
import java.util.function.Function;

Function<String, String> normalize =
        value -> value.trim().toUpperCase(Locale.ROOT);

String result = normalize.apply("  ord-42  ");
System.out.println(result); // ORD-42
~~~

This `Function` takes a `String` and returns a new `String`. It does not perform any data persistence or event emission.

### 2.2. Consumer Receives Data to Perform an Action

The interface `java.util.function.Consumer<T>` has the method:

~~~java
void accept(T value);
~~~

Example:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

List<String> received = new ArrayList<>();
Consumer<String> record = received::add;

record.accept("ORD-42");
System.out.println(received); // [ORD-42]
~~~

`Consumer.accept(...)` **does not return a business value**. The `boolean` return value from `List.add` does not become the output of the `Consumer`; the method reference is used in a `Consumer<String>` context with its return value discarded. In real applications, a `Consumer` typically sends commands, writes to a database, writes logs, or emits messages.

### 2.3. What Contract Does Composing Function with Consumer Produce?

Given:

~~~text
transform: Function<A, B>
sink:      Consumer<B>
~~~

the final component receives the `B` produced by `transform`. The composed flow has no return value:

~~~text
Consumer<A> composite

composite.accept(a):
    b = transform.apply(a)
    sink.accept(b)
~~~

| Component | Input | Output | Method |
|---|---|---|---|
| `Function<A, B>` | `A` | `B` | `apply(A)` |
| `Consumer<B>` | `B` | `void` | `accept(B)` |
| Function followed by Consumer | `A` | None | `accept(A)` |

This is a **terminal composition**: a `Consumer` is normally placed at the **end** of the flow because after `accept` there is no `B` value left to pass to another `Function`.

## 3. Composing in Plain Java

Suppose an application receives an order code that may contain whitespace and lowercase letters, and records the normalized code:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.function.Consumer;
import java.util.function.Function;

public class FunctionConsumerExample {

    public static void main(String[] args) {
        Function<String, String> normalize =
                value -> value.trim().toUpperCase(Locale.ROOT);

        List<String> acceptedOrders = new ArrayList<>();
        Consumer<String> save = acceptedOrders::add;

        Consumer<String> pipeline = raw ->
                save.accept(normalize.apply(raw));

        pipeline.accept("  ord-42  ");

        System.out.println(acceptedOrders); // [ORD-42]
    }
}
~~~

Trace `pipeline.accept("  ord-42  ")` in order:

1. `normalize.apply("  ord-42  ")` produces `"ORD-42"`.
2. `save.accept("ORD-42")` adds the string to the list.
3. `pipeline.accept(...)` finishes with return type `void`.

**Creating the lambda** `pipeline` does not call `normalize` or `save`. Both steps run when `accept(...)` is executed.

### 3.1. Generic Helper for Reusing the Composition

Java does not provide a built-in `Function.andThen(Consumer)`. If you need to reuse this pattern, you can write a helper:

~~~java
import java.util.function.Consumer;
import java.util.function.Function;

public final class FunctionConsumerComposition {

    private FunctionConsumerComposition() {}

    public static <A, B> Consumer<A> combine(
            Function<? super A, ? extends B> transform,
            Consumer<? super B> sink) {

        return value -> sink.accept(transform.apply(value));
    }
}
~~~

Usage:

~~~java
Function<String, Integer> parseAmount =
        text -> Integer.parseInt(text.trim());

Consumer<Number> showNumber =
        number -> System.out.println("Quantity: " + number);

Consumer<String> parseAndShow =
        FunctionConsumerComposition.combine(
                parseAmount, showNumber);

parseAndShow.accept(" 12 "); // Quantity: 12
~~~

Here, `parseAmount` returns `Integer`, while `showNumber` takes `Number`. The two types are compatible because `Integer` is a subtype of `Number`. The `? super B` wildcard lets the `Consumer` accept a suitable supertype of the result.

### 3.2. Why Can't You Call function.andThen(consumer)?

This is a **compile-time error**:

~~~java
Function<String, Integer> parse = Integer::parseInt;
Consumer<Integer> print = System.out::println;

// Does not compile: andThen on Function requires a Function,
// whereas print is a Consumer.
// Function<String, ?> invalid = parse.andThen(print);
~~~

`Function.andThen` and `Function.compose` accept `Function` instances. `Consumer` has its own `andThen` method to chain **two Consumers that accept the same compatible input type**, but does not have `compose` like `Function`.

You could create a `Function<Integer, Void>` that returns `null` after calling the `Consumer`, but that turns a terminal action into a function with a dummy `Void` return. When the intent is to accept data and perform a side effect, `Consumer<String>` and `accept` express the contract more clearly.

## 4. Distinguishing Function → Consumer from Consumer.andThen

Two compositions that are easily confused:

| Expression | Meaning | Output contract |
|---|---|---|
| `Function<A, B>` followed by `Consumer<B>` | Transform `A → B`, then consume `B` | `Consumer<A>` |
| `consumer1.andThen(consumer2)` | Pass **the same input** to two Consumers in order | `Consumer<T>` |
| `function1.andThen(function2)` | Transform data through two Functions | `Function<A, C>` |

`Consumer.andThen` example:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

List<String> events = new ArrayList<>();

Consumer<String> log = text -> events.add("LOG:" + text);
Consumer<String> audit = text -> events.add("AUDIT:" + text);

Consumer<String> both = log.andThen(audit);
both.accept("ORD-42");

System.out.println(events);
// [LOG:ORD-42, AUDIT:ORD-42]
~~~

In this example, `audit` receives **the exact same string `"ORD-42"`** that `log` received. No return value from `log` is passed to `audit`, because both are `Consumer` instances.

By contrast, `normalize → save` passes **transformed** data from the `Function` to the `Consumer`.

> If the first `Consumer` throws an exception during synchronous execution, the second `Consumer` in `andThen` is not invoked normally. Chaining two side effects with `andThen` also does not automatically create a transaction or rollback mechanism.

## 5. Complete Business Example in Spring Cloud Function

An application receives order data as a string, such as `" ord-42 , 2 "`. We want to:

1. Normalize casing and whitespace.
2. Parse the string into a strongly typed order object.
3. Record the normalized object into a result store.

Diagram:

~~~text
" ord-42 , 2 "                  String
      |
      v
normalizeOrderInput              Function<String, String>
      |
      | "ORD-42 , 2"
      v
parseOrder                       Function<String, OrderCommand>
      |
      | OrderCommand("ORD-42", 2)
      v
saveOrder                        Consumer<OrderCommand>
      |
      v
Records the order; no return value
~~~

To run the example without a database, we use an **in-memory** store. This is only a test adapter to make side effects observable, not a durable storage design.

### 5.1. Declaring Beans with Compatible Types

Java 17 and Spring Boot example:

~~~java
package example.functions;

import java.util.List;
import java.util.Locale;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.function.Consumer;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderFunctions {

    public record OrderCommand(String orderId, int quantity) {}

    public static final class ReceivedOrderStore {
        private final Queue<OrderCommand> orders =
                new ConcurrentLinkedQueue<>();

        public void save(OrderCommand order) {
            orders.add(order);
        }

        public List<OrderCommand> snapshot() {
            return List.copyOf(orders);
        }
    }

    @Bean
    public ReceivedOrderStore receivedOrderStore() {
        return new ReceivedOrderStore();
    }

    @Bean
    public Function<String, String> normalizeOrderInput() {
        return raw -> raw.trim().toUpperCase(Locale.ROOT);
    }

    @Bean
    public Function<String, OrderCommand> parseOrder() {
        return raw -> {
            String[] parts = raw.split(",", -1);
            if (parts.length != 2) {
                throw new IllegalArgumentException(
                        "Expected format is orderId,quantity");
            }

            String orderId = parts[0].trim();
            int quantity = Integer.parseInt(parts[1].trim());

            if (!orderId.matches("ORD-[0-9]+")
                    || quantity <= 0) {
                throw new IllegalArgumentException(
                        "Invalid order ID/quantity");
            }

            return new OrderCommand(orderId, quantity);
        };
    }

    @Bean
    public Consumer<OrderCommand> saveOrder(
            ReceivedOrderStore store) {
        return store::save;
    }
}
~~~

The function bean names created by `@Bean` are `normalizeOrderInput`, `parseOrder`, and `saveOrder`. The `ReceivedOrderStore` bean is only a dependency of the `Consumer`; it **is not a Function/Consumer/Supplier defined for composition**.

| Step name | Kind | Input | Output |
|---|---|---|---|
| `normalizeOrderInput` | Function | `String` | `String` |
| `parseOrder` | Function | `String` | `OrderCommand` |
| `saveOrder` | Consumer | `OrderCommand` | `void` |
| Full pipeline | Composed Consumer | `String` | `void` |

`normalizeOrderInput` and `parseOrder` process data; `saveOrder` is the **terminal point with side effects**. This separation lets you unit-test normalization/parsing logic without accessing real storage.

### 5.2. Composing by Name with FunctionCatalog.lookup

When Spring Cloud Function is on the classpath and the beans are registered by the application, `FunctionCatalog` can be injected into a service:

~~~java
package example.functions;

import java.util.function.Consumer;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Service;

@Service
public class OrderIngestionService {

    private final FunctionCatalog catalog;

    public OrderIngestionService(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    public void receive(String rawOrder) {
        Consumer<String> pipeline =
                catalog.lookup(
                    "normalizeOrderInput|parseOrder|saveOrder");

        if (pipeline == null) {
            throw new IllegalStateException(
                    "Order ingestion pipeline not found");
        }

        pipeline.accept(rawOrder);
    }
}
~~~

`FunctionCatalog.lookup(...)` here returns a processing flow with contract **`Consumer<String>`** according to the supported composition chain. Therefore, the right invocation is `pipeline.accept(rawOrder)`.

Sample usage in Spring:

~~~java
orderIngestionService.receive(" ord-42 , 2 ");

// Store receives:
// new OrderFunctions.OrderCommand("ORD-42", 2)
~~~

To observe it in practice, you can inject `OrderFunctions.ReceivedOrderStore` and call `snapshot()`. After the call above, the list contains `OrderCommand("ORD-42", 2)`.

### 5.3. Application Entry Class

~~~java
package example.functions;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Place the classes in the same `example.functions` package (or component-scanned packages) and declare the Spring Cloud Function dependency matching your project's Spring Boot version.

**Note:** `ReceivedOrderStore` only keeps data in memory and loses it on restart. In a real application, the `Consumer` can call a repository or producer to save/publish events, along with proper error handling and idempotency.

## 6. Configuring Composition with spring.cloud.function.definition

When an adapter needs to use a pipeline by name, you can specify:

~~~yaml
spring:
  cloud:
    function:
      definition: "normalizeOrderInput|parseOrder|saveOrder"
~~~

Or in `application.properties`:

~~~properties
spring.cloud.function.definition=normalizeOrderInput|parseOrder|saveOrder
~~~

The `|` symbol defines the order **normalize → parse → save**. Since `saveOrder` is at the end, the entire pipeline only **consumes input** and does not return a business result.

Distinguish between:

- `catalog.lookup("normalizeOrderInput|parseOrder|saveOrder")`: Java code looks up the pipeline to invoke with `accept(...)`.
- `spring.cloud.function.definition`: selects the pipeline name for the adapter/integration to use.
- HTTP, Spring Cloud Stream, or serverless adapter: determines how input enters the pipeline and handles the absence of a result payload.

The `definition` property **does not automatically create an HTTP endpoint or broker binding** if the application does not yet have the corresponding adapter and configuration.

### 6.1. Consumer Is the Terminal Point in the Pipeline

In an application, the following pipelines behave differently:

~~~text
normalizeOrderInput|parseOrder
    Function<String, OrderCommand>

normalizeOrderInput|parseOrder|saveOrder
    Consumer<String>
~~~

Adding `saveOrder` as the final step changes the overall contract from **returning data** to **returning no value**.

An expression `"saveOrder|parseOrder"` does not describe a normal valid flow: `saveOrder` accepts `OrderCommand` and returns `void`, so there is no output object for `parseOrder` to process.

Spring Cloud Function supports various composition shapes in specific cases, but **never assume a Consumer can be placed in the middle and followed by an arbitrary Function**. If you want to both persist data and produce a response, design an explicit pipeline/architecture rather than assuming a `Consumer` supplies data to the next step.

## 7. Java Type Compatibility and Business Compatibility

Suppose:

~~~text
parse:     Function<String, OrderCommand>
save:      Consumer<OrderCommand>
~~~

This is a compatible pair: `parse` produces `OrderCommand` and `save` accepts `OrderCommand`.

Conversely:

~~~text
parse:     Function<String, OrderCommand>
sendEmail: Consumer<EmailAddress>
~~~

These cannot be chained directly under Java generics because `OrderCommand` is not `EmailAddress`. You need a meaningful intermediate `Function`, such as `extractEmail: Function<OrderCommand, EmailAddress>`, or redesign the processing steps.

### 7.1. Matching Types Do Not Mean Matching Semantics

Two steps that both use `String` can still be semantically incompatible:

~~~text
extractCustomerId: Function<Order, String>
sendEmail:         Consumer<String> // treats String as an email address
~~~

The chain above might run, yet the `Consumer` receives a **customer ID**, not an email. When designing the domain, you can use explicit records:

~~~java
record CustomerId(String value) {}
record EmailAddress(String value) {}
~~~

As a result, `Function<Order, CustomerId>` cannot be mistakenly composed with `Consumer<EmailAddress>` when writing direct generic Java code.

### 7.2. Name-Based Composition Requires Runtime Testing

In plain Java, type errors are usually caught at compile time:

~~~java
Function<String, Integer> parseInt = Integer::parseInt;
Consumer<Boolean> storeFlag = value -> {};

// Does not compile: Integer cannot be used as Boolean.
// Consumer<String> bad = raw -> storeFlag.accept(parseInt.apply(raw));
~~~

In Spring Cloud Function, the string `"parseInt|storeFlag"` is just text resolved by the catalog at runtime. Receiving a `Consumer<String>` from `lookup` in code does not prove that the bean names and intermediate types are compatible.

At lookup and execution time, failures can include missing beans, incompatible types, payload conversion failures, or internal logic throwing exceptions. Write real integration tests with a Spring context.

### 7.3. Avoid Arbitrary Casting

You could force every value to `Object` or `String` so steps appear compatible, but doing so strips the compiler of the chance to catch bugs. Before connecting a new `Consumer`, write a contract table: **produced type**, **data meaning**, **accepted Consumer type**, and **action performed by the Consumer**.

## 8. Consumer and Side Effects: What to Watch Out For?

A `Consumer` is often the first point in a pipeline that performs an action altering the outside world: writing to a database, publishing a message, sending an API request, or creating an audit log. Because there is no output, the caller receives no object indicating what happened other than whether the `Consumer` returned normally or threw an exception.

### 8.1. Order Before and After the Action

With synchronous composition:

~~~text
Input → validate → transform → save
~~~

If `validate` fails, `save` is not called. If `save` fails, `validate` and `transform` have already run, and any side effects in earlier steps (if present) do not roll back automatically.

Therefore, organize stateless data checks **before** the terminal `Consumer`; critical side effects need dedicated reliability mechanisms when business requirements demand them.

### 8.2. Retries and the Risk of Duplicate Processing

Suppose the `Consumer` writes to the database successfully, but the adapter loses acknowledgment due to a network error. When the message is retried, the `Consumer` may run again with the same data.

Composition **does not automatically provide** exactly-once delivery, distributed transactions, or idempotency. Depending on the system, you can use:

- A unique business key, such as `orderId`, and duplicate-checked writes.
- Upserts or state-transition guards managed at the repository layer.
- Transactions/outbox pattern when consistency between database updates and event publishing is required.
- Retry, dead-letter, and acknowledgment policies appropriate for the adapter.

This must be evaluated alongside the broker's delivery semantics rather than assuming everything is safe just because `Consumer.accept(...)` did not throw.

### 8.3. Thread Safety of Consumer Beans

A `Consumer` registered as a Spring bean can be invoked many times, and in some environments invocations may be concurrent. Therefore, do not store unsynchronized mutable state in a shared lambda without protection. Using an `ArrayList` in a single-run plain Java test is fine, but unsuitable as storage for concurrent requests. The `ReceivedOrderStore` example above uses `ConcurrentLinkedQueue` to illustrate basic thread-safe operations.

## 9. Handling Errors and Special Data

### 9.1. An Exception in Function Prevents Consumer from Being Called

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;
import java.util.function.Function;

Function<String, Integer> parse = Integer::parseInt;

List<Integer> stored = new ArrayList<>();
Consumer<Integer> save = stored::add;

Consumer<String> pipeline =
        raw -> save.accept(parse.apply(raw));

pipeline.accept("12");

try {
    pipeline.accept("invalid");
} catch (NumberFormatException expected) {
    System.out.println("Invalid quantity");
}

System.out.println(stored); // [12]
~~~

`parse.apply("invalid")` throws `NumberFormatException` before `save.accept(...)` is invoked, so the list receives no new element.

### 9.2. Exceptions from Consumer Still Propagate to the Caller

~~~java
Function<String, String> normalize = String::trim;

Consumer<String> failingSink = value -> {
    throw new IllegalStateException("Failed to save data");
};

Consumer<String> pipeline =
        raw -> failingSink.accept(normalize.apply(raw));

// pipeline.accept("  ORD-42  ") throws IllegalStateException.
~~~

Normalization completed before the `Consumer` threw, but composition has no automatic recovery step. How an adapter reports errors over HTTP, messaging, or serverless handlers depends on the integration configuration.

### 9.3. Null Is Not Automatically Treated as Skipping Data

~~~java
Function<String, String> sometimesNull =
        value -> value.isBlank() ? null : value;

Consumer<String> printUpper =
        value -> System.out.println(value.toUpperCase());

Consumer<String> pipeline =
        raw -> printUpper.accept(sometimesNull.apply(raw));

// pipeline.accept("") leads to NullPointerException.
~~~

A `Consumer` can accept `null` at the Java reference-type level, but most business logic needs a clear contract for missing data. If you want to skip blank input, use an explicitly defined condition or a stateful result model (such as `Optional`), rather than assuming composition will skip it automatically.

### 9.4. Consumer Has No Return Value

You cannot capture a return value from `accept` the way you can from `apply`:

~~~java
Consumer<String> audit = System.out::println;

// Does not compile because accept returns void.
// String result = audit.accept("ORD-42");
~~~

To return information after performing an action, design a `Function<T, R>` that returns an explicit result or an appropriate orchestration flow. Do not force `Void` or add `return null` just to work around the difference between the two contracts.

## 10. The Message and Headers Case

When moving a pipeline to event-driven systems, besides the payload there are headers such as content-type, correlation ID, and transport metadata. These two signatures differ:

~~~text
Function<String, OrderCommand>
Consumer<OrderCommand>
~~~

and:

~~~text
Function<Message<String>, Message<OrderCommand>>
Consumer<Message<OrderCommand>>
~~~

`Message<T>` includes both payload and headers. If a `Consumer` needs headers for auditing or routing, define the appropriate contract or design an explicit transformation step.

Example creating a new message from an object:

~~~java
import java.util.function.Function;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Function<OrderFunctions.OrderCommand,
         Message<OrderFunctions.OrderCommand>> toMessage =
        order -> MessageBuilder
                .withPayload(order)
                .setHeader("source", "order-ingestion")
                .build();
~~~

A `Consumer` receiving a message:

~~~java
import java.util.function.Consumer;
import org.springframework.messaging.Message;

Consumer<Message<OrderFunctions.OrderCommand>> auditMessage =
        message -> System.out.println(
                message.getHeaders().get("source")
                + ": " + message.getPayload().orderId());
~~~

The data flow can be depicted as:

~~~text
Function<String, OrderCommand>
             |
             v
Function<OrderCommand, Message<OrderCommand>>
             |
             v
Consumer<Message<OrderCommand>>
             ⇒ Consumer<String>
~~~

In Spring Cloud Function, adapters may support payload conversion and working with `Message` based on type metadata. However, do not assume every header is automatically preserved across `Function` steps or every payload automatically turns into a semantically valid POJO. When integrating a broker, test with real messages, payload types, serialization, and critical metadata.

## 11. The Reactive Consumer Case

With Reactor, type contracts can operate over an entire `Flux`:

~~~java
import java.util.function.Consumer;
import java.util.function.Function;

import reactor.core.publisher.Flux;

Function<Flux<String>, Flux<Integer>> parseNumbers =
        flux -> flux.map(String::trim)
                    .map(Integer::parseInt);

Consumer<Flux<Integer>> printNumbers =
        flux -> flux.subscribe(System.out::println);

Consumer<Flux<String>> pipeline =
        source -> printNumbers.accept(parseNumbers.apply(source));
~~~

At the Java generics level, `Function<Flux<String>, Flux<Integer>>` connects to `Consumer<Flux<Integer>>`. When invoking:

~~~java
pipeline.accept(Flux.just(" 4 ", " 9 "));
~~~

`Flux` is a **lazy** stream: `map` operations only execute once there is a subscription. The example above uses an explicit `subscribe` for illustration. In production applications, calling `subscribe` arbitrarily can make error management, backpressure, and stream lifecycle hard to manage; follow the subscription model of the framework and adapter in use.

Do not treat `Function<String, Integer>` and `Consumer<Flux<Integer>>` as directly compatible under generics simply because each individual item ends up as `Integer`. The input contract of the `Consumer` is `Flux<Integer>`, not `Integer`.

### 11.1. Imperative and Reactive Consumers Differ in How They Are Triggered

- `Consumer<OrderCommand>` receives one `OrderCommand` per `accept` call.
- `Consumer<Flux<OrderCommand>>` receives **one Publisher**; many records may be processed as the `Publisher` emits elements.
- Spring Cloud Function/adapters may adjust triggering and subscriptions depending on the version, so do not assume each message always corresponds to a single `accept` call on a reactive `Consumer`.

When connecting to Spring Cloud Stream, verify your framework version's contract, error handling policy, retries, backpressure, and how subscriptions are managed.

## 12. Function → Consumer Across Invocation Environments

A pipeline with the same Java logic can be attached to multiple environments, though the triggering and response mechanisms differ.

| Environment | Incoming data | Meaning when Consumer completes |
|---|---|---|
| Internal Java | Code calls `pipeline.accept(input)` | Method finishes, returns no object |
| HTTP adapter | Adapter receives request/body and maps to Consumer as supported by version | HTTP response decided by adapter; no business value from Consumer |
| Events/Stream | Message from binder's input binding | Consumer was invoked; ack/retry depends on framework/broker |
| Serverless | Event converted to input by handler/adapter | Response/error reporting depends on platform and adapter |

For example, a pipeline ending in `saveOrder` typically fits receiving **inbound** messages from a broker. Because it produces no `R` value, do not assume there will be an output binding containing a business result like `Function<T,R>`.

Overview diagram:

~~~text
HTTP body / Event payload / Java input
                |
                v
        Appropriate adapter
                |
                v
      Function<String, String>
                |
                v
      Function<String, OrderCommand>
                |
                v
      Consumer<OrderCommand>
                |
                v
        Database / log / side effect
~~~

This diagram illustrates logic reusability. For real deployment, you need dependencies, serializer configuration, message mapping, handlers, retries, database/broker connections, and corresponding adapter tests. `spring.cloud.function.definition` only selects the pipeline name.

## 13. Testing the Pipeline

### 13.1. Unit Tests Verifying Order and Data Passed to Consumer

In plain Java with JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;
import java.util.function.Function;

import org.junit.jupiter.api.Test;

class FunctionConsumerOrderTest {

    @Test
    void transformRunsBeforeSinkAndPassesResult() {
        List<String> calls = new ArrayList<>();

        Function<String, Integer> length = raw -> {
            calls.add("transform");
            return raw.trim().length();
        };

        List<Integer> received = new ArrayList<>();
        Consumer<Integer> sink = value -> {
            calls.add("sink");
            received.add(value);
        };

        Consumer<String> pipeline =
                raw -> sink.accept(length.apply(raw));

        pipeline.accept("  Java  ");

        assertEquals(List.of("transform", "sink"), calls);
        assertEquals(List.of(4), received);
    }
}
~~~

The test verifies **both call order and the data received by the Consumer**, which is stronger than merely checking that a call does not throw an exception.

### 13.2. Unit Tests Ensuring Earlier Step Errors Block the Consumer

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;
import java.util.function.Function;

import org.junit.jupiter.api.Test;

class FunctionConsumerFailureTest {

    @Test
    void parseFailureDoesNotCallSink() {
        Function<String, Integer> parse = Integer::parseInt;

        List<Integer> saved = new ArrayList<>();
        Consumer<Integer> sink = saved::add;

        Consumer<String> pipeline =
                raw -> sink.accept(parse.apply(raw));

        assertThrows(NumberFormatException.class,
                () -> pipeline.accept("invalid"));

        assertEquals(List.of(), saved);
    }
}
~~~

For real side-effect scenarios, add tests for errors inside the `Consumer`, duplicate invocations, and retry policies at the appropriate layer.

### 13.3. Integration Tests Looking Up via FunctionCatalog

Requires a Spring Boot context containing `OrderFunctions`, `OrderApplication`, and the Spring Cloud Function dependency:

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.List;
import java.util.function.Consumer;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(classes = OrderApplication.class)
class OrderCompositionIntegrationTest {

    @Autowired
    private FunctionCatalog catalog;

    @Autowired
    private OrderFunctions.ReceivedOrderStore store;

    @Test
    void functionAndConsumerComposeByName() {
        Consumer<String> pipeline = catalog.lookup(
                "normalizeOrderInput|parseOrder|saveOrder");

        assertNotNull(pipeline);
        pipeline.accept(" ord-42 , 2 ");

        assertEquals(
                List.of(new OrderFunctions.OrderCommand(
                        "ORD-42", 2)),
                store.snapshot());
    }
}
~~~

This test verifies **the looked-up names**, **transformation order**, **output types of Function steps**, and **observable side effects of the Consumer** inside the Spring environment.

If an application has multiple tests sharing the Spring context, isolate or clear the test store's data between tests. When moving to a real database, use fixtures/test containers or an appropriate isolation strategy.

### 13.4. Testing with Adapters

When running over HTTP, events, or serverless, also verify:

- The adapter actually selects the pipeline from `spring.cloud.function.definition`.
- Raw input is deserialized into the exact `String` or POJO type expected by the first step.
- Invalid data does not cause the `Consumer` to perform side effects.
- Retries/duplicates do not create duplicate records violating business requirements.
- The adapter forwards/records correlation IDs and headers as designed.
- Responses/acks and environment error handling do not rely on assuming `Consumer.accept` returns a result.

## 14. Common Mistakes

| Symptom | Possible cause | How to fix |
|---|---|---|
| `function.andThen(consumer)` fails to compile | `Function.andThen` accepts a Function, not a Consumer | Create `Consumer<A>` via lambda or use catalog composition |
| Calling `pipeline.apply(...)` fails | Pipeline ends with a Consumer | Look up the `Consumer<A>` contract and call `accept(...)` |
| `"saveOrder|parseOrder"` is invalid | Consumer produces no output for a subsequent Function | Place the Consumer at the end of the pipeline |
| `catalog.lookup(...)` returns nothing | Wrong bean name or unregistered bean | Check `@Bean`, dependencies, component scan |
| Pipeline looked up, fails at runtime | Incompatible intermediate type or data | Test `accept(...)` with real values |
| No output message | Consumer has no business return value | Design as input-only or create a Function returning a result when needed |
| An order is saved multiple times | Retries/duplicate input, non-idempotent Consumer | Use business keys, processing state, retry policy |
| No side effect observed | Adapter never invoked pipeline or Consumer failed | Check definition, bindings, logs, errors, and integration tests |

## 15. Practice Exercises

**Exercise 1 — Plain Java Composition.** Given `Function<String, Integer> parse = Integer::parseInt` and `Consumer<Integer> save` that adds to a list, write a `Consumer<String>` calling both steps. For input `"21"`, determine the final list.

**Exercise 2 — Three-Step Composition.** Given `trim: Function<String, String>`, `parse: Function<String, Integer>`, and `save: Consumer<Integer>`, write the lambda forming the overall pipeline and the Spring Cloud Function composition-by-name expression. In what form does input `" 7 "` reach the `Consumer`?

**Exercise 3 — Distinguishing Two Kinds of andThen.** Why does `Function<String,Integer>.andThen(Consumer<Integer>)` fail to compile in Java? Write an example of `Consumer<Integer>.andThen(Consumer<Integer>)` and explain whether any output is passed from the first `Consumer` to the second.

**Exercise 4 — Intermediate Types.** A function `parseOrder: Function<String, OrderCommand>` needs to connect to `sendEmail: Consumer<EmailAddress>`. Propose an intermediate step and explain why specific domain type contracts are needed.

**Exercise 5 — Error Scenario.** In the pipeline `normalizeOrderInput|parseOrder|saveOrder`, what happens when the input is `"ORD-42,0"` or `"ORD-42,abc"`? Is `saveOrder` invoked? Describe a test that proves it.

**Exercise 6 — Events and Retries.** A `Consumer` saves an order to a database. After saving succeeds, the broker connection fails before acknowledging the message. If the broker redelivers it, what can happen? Propose a way to handle duplicates using `orderId`.

### Solution Hints

- **Exercise 1:** `Consumer<String> combined = input -> save.accept(parse.apply(input));`; the list contains `21`.
- **Exercise 2:** `raw -> save.accept(parse.apply(trim.apply(raw)))`; composed name `"trim|parse|save"`; the `Consumer` receives an `Integer` with value `7`.
- **Exercise 3:** `Function`'s `andThen` requires a `Function`; `Consumer.andThen` passes the same input sequentially to both Consumers without forwarding any result.
- **Exercise 4:** For example, `extractEmail: Function<OrderCommand, EmailAddress>`.
- **Exercise 5:** An error in `parseOrder` stops the chain before `saveOrder`; verify the receiving store remains empty.
- **Exercise 6:** Duplicate saves can occur; use a unique key constraint or idempotent handling keyed by `orderId`, coordinated with proper retry/ack design.

## 16. Key Takeaways

- `Function<A, B>` produces result `B`; `Consumer<B>` receives `B` and returns no business value.
- Composing in the order **Function → Consumer** produces the behavior of `Consumer<A>`: `input -> sink.accept(transform.apply(input))`.
- Java's `Function.andThen` does not accept a `Consumer`; `Consumer.andThen` composes **two Consumers** sharing the same input.
- Spring Cloud Function allows composition by name, such as `catalog.lookup("normalizeOrderInput|parseOrder|saveOrder")`; this pipeline is invoked with `accept(...)`.
- Place the `Consumer` at the end of a transformation chain and check both **intermediate types and data semantics** before triggering side effects.
- When deploying over HTTP, events, or serverless, you need appropriate adapters and error/ack/retry mechanisms; composition alone does not guarantee transactions or deduplication.
