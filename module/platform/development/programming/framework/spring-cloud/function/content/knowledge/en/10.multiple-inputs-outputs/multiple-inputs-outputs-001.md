# Concept of Function Input and Output Arity

## 1. Why care about the number of inputs and outputs?

In **Spring Cloud Function** (module `SPRING_CLOUD_FUNCTION`), business logic is represented by Java functions with explicit input and output contracts. A function can receive data to transform, generate data without inputs, or simply process data without returning a result. When integrating with HTTP, event systems, or serverless environments, this contract helps the framework know how to deliver data to the function and handle the result.

**The number of inputs and outputs** (also called *arity*) answers two questions:

- How many **logical input sources/ports** does the function require?
- How many **logical output streams/ports** does the function produce?

This is an important concept when designing event-processing pipelines, especially when a function needs to consume multiple streams or route results to multiple destinations. It is important to distinguish the number of ports from the **number of data items** passing through each port: a single port can carry thousands of messages.

Example in an order system:

| Business requirement | Input → output model | Interpretation |
| --- | --- | --- |
| Generate a new order ID | `0 → 1` | Receives no data from the caller, returns one ID |
| Normalize an order ID | `1 → 1` | Receives one ID, returns the normalized ID |
| Log order processing | `1 → 0` | Receives one ID, performs a side effect, returns no value |
| Merge order and invoice streams | `2 → 1` | Receives two event streams, emits one stream |
| Route VIP and regular orders | `1 → 2` | Receives one stream, emits to two destination streams |

> **Convention:** In this lesson, `m → n` denotes **m input ports, n output ports at the function contract or binding level**, not the number of parameters appearing in Java syntax, nor the number of records processed in a single run.

## 2. Three basic function types in Spring Cloud Function

Spring Cloud Function uses standard Java functional interfaces: `Supplier<O>`, `Function<I, O>`, and `Consumer<I>`. They are registered as Spring beans and discovered by `FunctionCatalog` for invocation across different execution mechanisms.

| Functional interface | Inputs | Outputs | Method | Role |
| --- | ---: | ---: | --- | --- |
| `Supplier<O>` | 0 | 1 | `O get()` | Produces data |
| `Function<I, O>` | 1 | 1 | `O apply(I input)` | Transforms data |
| `Consumer<I>` | 1 | 0 | `void accept(I input)` | Receives and processes data |

Illustrative example with standalone beans:

~~~java
import java.util.Locale;
import java.util.UUID;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderFunctions {

    // 0 -> 1: generates an ID each time the Supplier is invoked.
    @Bean
    public Supplier<String> generateOrderId() {
        return () -> UUID.randomUUID().toString();
    }

    // 1 -> 1: receives one ID, returns one normalized ID.
    @Bean
    public Function<String, String> normalizeOrderId() {
        return id -> id.trim().toUpperCase(Locale.ROOT);
    }

    // 1 -> 0: processes the ID, returns no payload.
    @Bean
    public Consumer<String> auditOrderId() {
        return id -> System.out.println("Processed order: " + id);
    }
}
~~~

For example, `normalizeOrderId` receives `" ord-42 "` and returns `"ORD-42"`. `auditOrderId` may write logs, update a database, or call another service; the `accept` method still has a `void` return type. In production applications, use a logging framework instead of `System.out.println`.

A `Supplier` having no input arguments **does not mean** it only runs once during the application lifecycle: invocation frequency is determined by the trigger mechanism. Similarly, a `Consumer` having no return value **does not mean** its work produces no side effects.

## 3. Port count differs from item count and field count

### 3.1. An object with multiple fields is still one input

The function `Function<Order, Result>` receives a single `Order` object, even if that object has fields `id`, `customerId`, `items`, and `total`. Those fields do not automatically become independent input ports.

Similarly, `Function<Message<Order>, Result>` receives **one** message consisting of `payload` and `headers`. Business data and metadata reside together in a single `Message` object.

Spring Cloud Function also supports the special cases `BiFunction<T, Map, R>` and `BiConsumer<T, Map>`: when invoked through `FunctionCatalog`, the framework can extract the **payload** and **headers** of the same `Message` and pass them as two Java arguments. The second argument must be of type `Map`. This represents **one message with metadata**, not two independent event sources; you should not assume that every `BiFunction<A, B, R>` automatically creates two input bindings.

### 3.2. A `Flux` contains multiple items but can still be a single port

In Project Reactor's reactive model:

~~~java
@Bean
public Function<Flux<Integer>, Flux<Integer>> duplicateValues() {
    return input -> input.flatMap(number ->
            Flux.just(number, number * 10));
}
~~~

Given inputs `2, 3`, the output stream may emit `2, 20, 3, 30`. The number of **items** increased from 2 to 4, but the function signature is still **one input stream, one output stream** (`1 → 1`). Note that the order between items may change when using `flatMap` with asynchronous operations.

Commonly confused cases:

| Signature or behavior | Correct interpretation |
| --- | --- |
| `Function<Order, List<Result>>` | One Java output value containing a list of results |
| `Function<Flux<Order>, Flux<Result>>` | One input stream and one output stream; each stream can carry multiple items |
| `Flux.empty()` in a reactive function | Emits no items for that execution; does **not** remove the declared output port |
| `flatMap` emitting multiple items | Changes the number of emitted items, does **not** create extra output bindings |
| `Consumer<Order>` writing to two database tables | Still `1 → 0` in the functional bean contract; two side effects are not two return ports |

A specific adapter may handle collections according to its own rules. For example, Spring Cloud Stream supports returning a `List<Message<T>>` and sending each `Message` as a separate message. This is **multiple messages on a single output**, which differs from multiple output bindings.

### 3.3. The number of Java parameters does not always equal the number of logical ports

The signature `Function<Tuple2<Flux<A>, Flux<B>>, Flux<C>>` has only **one Java parameter** in the `apply` method: a `Tuple2`. However, Spring Cloud Function can recognize the two `Flux` elements of the tuple as **two logical input ports** in the function arity model. This is why you must inspect the inner types rather than simply counting commas in the method signature.

## 4. Multiple inputs and multiple outputs with reactive functions

When a problem requires **multiple independent streams**, Spring Cloud Function provides the *Function Arity* mechanism based on `Flux` and Reactor tuples such as `Tuple2`. The elements inside the tuple carry information about **the number of ports** and **the data type of each port**.

Common patterns:

| Signature | Logical arity | Use case |
| --- | --- | --- |
| `Function<Flux<A>, Flux<B>>` | `1 → 1` | Transform a single event stream |
| `Function<Tuple2<Flux<A>, Flux<B>>, Flux<C>>` | `2 → 1` | Merge two source streams |
| `Function<Flux<A>, Tuple2<Flux<B>, Flux<C>>>` | `1 → 2` | Route events to two streams |
| `Function<Tuple2<Flux<A>, Flux<B>>, Tuple2<Flux<C>, Flux<D>>>` | `2 → 2` | Process two sources and emit two streams |

A key limitation to remember: **multi-port support via function arity focuses on reactive functions**. Writing an imperative function that returns `Tuple2<Value1, Value2>` does not automatically create two output bindings. Mapping these ports to specific topics/queues also depends on the adapter, typically Spring Cloud Stream.

### 4.1. `2 → 1` example: merging two streams

Suppose one stream carries order IDs (`String`) and the other stream carries invoice IDs (`Long`). The `combineEvents` function tags each type and merges both into a single result stream:

~~~java
@Bean
public Function<Tuple2<Flux<String>, Flux<Long>>, Flux<String>>
        combineEvents() {
    return sources -> Flux.merge(
            sources.getT1().map(id -> "ORDER:" + id),
            sources.getT2().map(id -> "INVOICE:" + id));
}
~~~

`getT1()` accesses the first input stream, and `getT2()` accesses the second input stream. `Flux.merge` emits events from both streams into one result stream as they arrive; it does **not** automatically pair an order with an invoice having the same ID. If key-based correlation is needed, you must design appropriate correlation rules, time synchronization, or processing windows.

Stream diagram:

~~~text
Order stream    ──> [ input 0 ] ┐
                                ├── combineEvents ──> [ output 0 ] ──> Unified event stream
Invoice stream  ──> [ input 1 ] ┘
~~~

### 4.2. `1 → 2` example: classifying orders

The following function splits order IDs into a VIP group (IDs starting with `VIP-`) and a regular group:

~~~java
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;
import reactor.util.function.Tuples;

@Configuration
public class MultiPortFunctions {

    @Bean
    public Function<Flux<String>, Tuple2<Flux<String>, Flux<String>>>
            classifyOrders() {
        return incoming -> {
            // Share one source across two branches, waiting for both subscribers.
            Flux<String> shared = incoming.publish().autoConnect(2);

            Flux<String> vip = shared.filter(id -> id.startsWith("VIP-"));
            Flux<String> regular = shared.filter(id -> !id.startsWith("VIP-"));

            return Tuples.of(vip, regular);
        };
    }
}
~~~

If the input stream contains `VIP-101`, `ORD-102`, `VIP-103`, then the VIP stream receives `VIP-101` and `VIP-103`, while the regular stream receives `ORD-102`. These are two **independent outputs**: the integration layer can wire each output to a different destination.

`publish().autoConnect(2)` allows both branches to share a single subscription to the source and connects only once both branches have a subscriber, preventing each branch from subscribing independently to the source. This example assumes **both outputs are subscribed to**; if one subscriber is missing, the connection will not start. When building real-world systems, check subscription lifecycle, backpressure, and error handling according to the adapter/binder in use.

Stream diagram:

~~~text
                     ┌── [ output 0: VIP ] ─────> orders.vip
orders.in ──> classifyOrders
                     └── [ output 1: regular ] ─> orders.regular
~~~

## 5. How are ports mapped to bindings?

`FunctionCatalog` is responsible for discovering, normalizing, and looking up functional beans; it supports composition and data conversion according to declared types. **Spring Cloud Stream** is an example adapter that turns logical ports into *bindings* connected to topics/queues in a messaging system.

For the `classifyOrders` function above, the default binding naming convention is:

| Binding name | Meaning |
| --- | --- |
| `classifyOrders-in-0` | The single input stream |
| `classifyOrders-out-0` | First output stream: VIP orders |
| `classifyOrders-out-1` | Second output stream: regular orders |

Example configuration in `application.yml` (when the application includes Spring Cloud Stream and a suitable binder):

~~~yaml
spring:
  cloud:
    function:
      definition: classifyOrders
    stream:
      bindings:
        classifyOrders-in-0:
          destination: orders.in
        classifyOrders-out-0:
          destination: orders.vip
        classifyOrders-out-1:
          destination: orders.regular
~~~

Correspondingly, the `2 → 1` `combineEvents` function has the default bindings: `combineEvents-in-0`, `combineEvents-in-1`, and `combineEvents-out-0`.

**Note:** For this configuration to run, the project needs the Spring Cloud Function, Reactor, Spring Cloud Stream dependencies, and an appropriate messaging binder. Declaring a functional bean **does not by itself create topics/queues**. The binding name describes the logical port, while `destination` configures the specific target.

## 6. Does composition change the number of inputs and outputs?

Spring Cloud Function allows composing functions in `spring.cloud.function.definition` using the `|` symbol. For example:

~~~properties
spring.cloud.function.definition=normalizeOrderId|auditOrderId
~~~

The output of `normalizeOrderId` (a `String`) becomes the input of `auditOrderId`. The resulting chain has a `1 → 0` contract because it ends with a `Consumer`. If you compose two compatible `Function<I, O>` beans, the chain typically remains `1 → 1`; if you compose a `Supplier` with a `Function`, the chain still requires no direct input.

~~~text
" ord-42 " ──> normalizeOrderId ──> "ORD-42" ──> auditOrderId
      1 input                                    no return value
~~~

Composition with `|` represents **sequential chaining** between functions, not a mechanism that automatically creates extra output branches. When the requirement is to send data to multiple different channels, explicitly design the number of ports using reactive tuples or use appropriate routing/integration components.

Some combinations do not make sense sequentially: a `Consumer` does not return a value for a subsequent `Function` to process. Check the output type of the preceding step and the input type of the following step before defining a pipeline.

## 7. Decoupling function logic from invocation protocols

The design goal of Spring Cloud Function is to write reusable logic without coupling it tightly to HTTP, a broker, or a serverless platform. The same `Function<I, O>` bean can be looked up by `FunctionCatalog` and wrapped with type/message conversion, after which a specific adapter decides how to invoke it:

| Environment | How a function contract can be used |
| --- | --- |
| HTTP | Web adapter maps requests to inputs and turns results into responses |
| Events/message broker | Spring Cloud Stream binds input/output bindings to destinations |
| Serverless | Platform adapter converts invocation events to inputs and handles outputs |

Support for **specific signatures** may vary across adapters. In particular, the reactive multi-port model requires appropriate stream and binding support; a `2 → 2` function cannot automatically be treated as four independent HTTP endpoints.

When data passes through messages, pay attention to **payload**, **headers**, and **content type**. A `Function<Message<Order>, Result>` can use metadata beyond the payload, and `FunctionCatalog` can support input/output conversion based on type information when the adapter supplies compatible data. Type conversion does not change the designed number of ports.

## 8. How to choose a function contract and common mistakes

Start from the business flow diagram and identify **independent data sources** and **independent processing destinations**:

| Design question | Recommendation |
| --- | --- |
| Need to generate data without an input message? | `Supplier<O>` |
| One input item needs one result? | `Function<I, O>` |
| Only need a side effect such as saving or logging? | `Consumer<I>` |
| One source can emit multiple records on the same channel? | `Function<Flux<I>, Flux<O>>` with `flatMap`/`concatMap` as appropriate |
| Two independent input streams need to be merged/processed together? | Reactive function with `Tuple2<Flux<A>, Flux<B>>` as input |
| Need to emit events to two different destinations? | Reactive function returning `Tuple2<Flux<A>, Flux<B>>` and mapping each output binding |

Common mistakes:

1. **Counting object fields as ports.** An object with multiple properties is still a single input if the function takes one payload.
2. **Counting items in a `List`/`Flux` as ports.** A stream can have an infinite number of items while still occupying only one binding.
3. **Confusing `BiFunction` with two message sources.** The `BiFunction<T, Map, R>` case is for the payload and headers of the same message.
4. **Using an imperative tuple expecting two output bindings.** Multi-port function arity is supported in the reactive model.
5. **Forgetting the technical constraints of reactive branches.** Splitting a `Flux` into multiple branches can lead to duplicate subscriptions, dropped events, or failure to start if connections/subscriptions are not managed properly.
6. **Confusing composition with branching.** `a|b` calls `b` after `a`; it does not mean a single input is broadcast simultaneously to both functions.

### Quick self-check examples

- `Supplier<Flux<Order>>`: **0 → 1** (one stream provided by the Supplier).
- `Function<Message<Order>, Result>`: **1 → 1** (one message carrying payload and headers).
- `Function<Flux<Order>, Flux<Result>>`: **1 → 1** (number of items may vary).
- `Function<Tuple2<Flux<Order>, Flux<Invoice>>, Flux<Report>>`: **2 → 1** (two independent sources merged into one stream).
- `Function<Flux<Order>, Tuple2<Flux<Accepted>, Flux<Rejected>>>`: **1 → 2** (two output ports).
- `Consumer<Order>`: **1 → 0** (returns no payload).

Once the number of ports is correctly identified, designing `FunctionCatalog` usage, composition, message conversion, and deploying the same logic over HTTP, events, or serverless becomes much clearer: **the function signature defines the logical contract; the adapter defines how that contract connects to the outside world**.

### References

- [Spring Cloud Function — Programming model and Function Arity](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
