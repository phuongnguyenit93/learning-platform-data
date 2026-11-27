# Type Information and Indexing of Each Input and Output

## 1. The problem: knowing exactly which port receives and emits which data type

In **Spring Cloud Function** (module `SPRING_CLOUD_FUNCTION`), `Supplier`, `Function`, and `Consumer` beans represent business logic that can be reused independently of the invocation protocol. `FunctionCatalog` enables function lookup, signature normalization, composition, and message conversion. Suitable adapters then connect the function to HTTP, event systems, or serverless platforms.

In the **Multiple Inputs/Outputs** chapter, a function can receive two independent streams and emit two result streams. When that happens, **two separate questions** must be answered:

1. **Index:** which ordinal input/output port is under consideration, and which tuple element does it correspond to?
2. **Type information:** what Java type do items passing through that port carry, and how should the adapter convert the payload?

Suppose a service receives order creation and payment confirmation events, then emits two separate result streams:

~~~text
orders.created ──> input 0 ──┐
                            │
                            ├── mapChannels ──> output 0 ──> orders.indexed
                            │
payments.confirmed -> input 1 ┘          └─────> output 1 ──> payments.indexed

input 0: OrderCreated            output 0: OrderIndex
input 1: PaymentConfirmed        output 1: PaymentIndex
~~~

A misconfigured index can feed payment JSON into a port expecting `OrderCreated`. A signature with inaccurate type declarations can prevent the framework from determining how to convert the data. Therefore, **port ordering and payload types are part of the integration contract**.

## 2. Two numbering schemes to distinguish

### 2.1. Binding names use 0-based indices

In **Spring Cloud Stream** with the functional binding model, default names follow this convention:

~~~text
<functionName>-in-<index>
<functionName>-out-<index>
~~~

Where:

- `functionName` is the name of the bound function/bean, such as `mapChannels`.
- `in` or `out` specifies the data direction.
- `index` is numbered **starting from 0** separately for input ports and output ports.

For example:

| Binding name | Meaning |
| --- | --- |
| `mapChannels-in-0` | First input port |
| `mapChannels-in-1` | Second input port |
| `mapChannels-out-0` | First output port |
| `mapChannels-out-1` | Second output port |

An ordinary single-input, single-output function still uses the `-in-0` and `-out-0` suffixes. Seeing `-0` does not mean a function has multiple ports. Conversely, **`-out-1` is not the first output**, but the **second** output.

### 2.2. Reactor Tuples use accessor names starting at T1

Project Reactor provides `Tuple2<A, B>`, `Tuple3<A, B, C>`, etc. in the `reactor.util.function` package. The accessor methods are `getT1()`, `getT2()`, `getT3()`, etc. — meaning **1-based numbering**.

When each tuple element is a `Flux` in a multi-port reactive function, the correspondence is:

| Position in tuple | Reactor method | Binding index | Example binding |
| --- | --- | ---: | --- |
| First element | `getT1()` | 0 | `mapChannels-in-0` or `mapChannels-out-0` |
| Second element | `getT2()` | 1 | `mapChannels-in-1` or `mapChannels-out-1` |
| Third element | `getT3()` | 2 | `example-in-2` or `example-out-2` |

**Rule of thumb:** `getT(n)` corresponds to binding index `n - 1`; count strictly in the order elements are declared in `TupleN`. There is no `getT0()` accessor.

~~~java
import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;
import reactor.util.function.Tuples;

Tuple2<Flux<String>, Flux<Integer>> sources = Tuples.of(
        Flux.just("ORDER-101"),   // getT1() -> input index 0
        Flux.just(100_000));      // getT2() -> input index 1

Flux<String> first = sources.getT1();
Flux<Integer> second = sources.getT2();
~~~

Variable names like `orders`, `payments`, `first`, or `second` in code help human readers; the framework determines port positions from **type structure and element order**. If you change the order in the tuple, the meaning of the corresponding bindings changes too.

> Do not confuse a **binding** index with a **list element** index, a **broker partition** index, or indices written inside headers. They serve entirely different purposes.

## 3. At which layers does type information exist?

Consider the signature:

~~~java
Function<
    Tuple2<Flux<OrderCreated>, Flux<PaymentConfirmed>>,
    Tuple2<Flux<OrderIndex>, Flux<PaymentIndex>>
>
~~~

There are multiple nested type layers:

| Layer | Example | What does it convey? |
| --- | --- | --- |
| Functional interface | `Function<I, O>` | Has input and output |
| Multi-port container | `Tuple2<..., ...>` | Two elements on each side |
| Publisher | `Flux<T>` | Each port carries a sequence of `T` items |
| Concrete payload type | `OrderCreated`, `PaymentConfirmed` | What data structure the framework and logic expect |
| Message wrapper (if present) | `Message<T>` | Payload `T` accompanied by headers and metadata |

By declaring full generics, each port gets its own type. Both are inputs, yet input 0 can carry `OrderCreated` while input 1 carries `PaymentConfirmed`; there is no need to force everything to `Object`.

### 3.1. Why not use a Collection or Object[] to represent ports?

~~~java
List<Flux<Object>> sources;             // Cannot express each position's type clearly.
Object[] outputs;                       // Size and types are unclear in the signature.
Tuple2<Flux<String>, Flux<Long>> ports; // Two ports, each with a concrete type.
~~~

`List<Flux<Object>>` can hold multiple streams, but element type information at each position collapses to `Object`. Moreover, a list's size can change at runtime. `Tuple2<Flux<String>, Flux<Long>>`, by contrast, captures **both the fixed count and each port's type directly in the signature** — information the framework uses to understand function arity and select appropriate payload conversions.

Java has *type erasure*, so full generics cannot be recovered merely by inspecting a running `Flux` instance. Spring typically infers types from **method/bean declarations** and function signature metadata. Therefore, keep concrete generics directly on the `@Bean` method return type instead of using raw `Function` types or casting all inputs to `Object`.

### 3.2. Item count and port count are not directly related

`Flux<OrderCreated>` can emit 0, 1, or thousands of records and still be **one port**. `Flux<List<OrderCreated>>` is also one port, where each emitted item is a list. Conversely, `Tuple2<Flux<OrderCreated>, Flux<PaymentConfirmed>>` is two independent ports even if each stream is empty at a given moment.

**Port count** is determined by the reactive type contract; **message count** and **payload item count** are determined by the data flow, adapter, and business logic.

## 4. Complete example: 2 inputs with different types, 2 outputs with different types

The following example uses **Java 17+** (`record`), Spring Cloud Function, and Project Reactor. Two inputs flow through two independent processing branches: orders are mapped to order indexes, while payments are mapped to payment summaries.

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;
import reactor.util.function.Tuples;

@Configuration
public class MultiPortTypeConfiguration {

    public record OrderCreated(String orderId, long totalVnd) {}

    public record PaymentConfirmed(String orderId, long paidVnd) {}

    public record OrderIndex(String orderId, long totalVnd) {}

    public record PaymentIndex(String orderId, boolean hasPayment) {}

    @Bean
    public Function<
            Tuple2<Flux<OrderCreated>, Flux<PaymentConfirmed>>,
            Tuple2<Flux<OrderIndex>, Flux<PaymentIndex>>
    > mapChannels() {
        return sources -> {
            // getT1() is input port index 0: OrderCreated.
            Flux<OrderCreated> orders = sources.getT1();

            // getT2() is input port index 1: PaymentConfirmed.
            Flux<PaymentConfirmed> payments = sources.getT2();

            Flux<OrderIndex> orderIndexes =
                    orders.map(order -> new OrderIndex(
                            order.orderId(), order.totalVnd()));

            Flux<PaymentIndex> paymentIndexes =
                    payments.map(payment -> new PaymentIndex(
                            payment.orderId(), payment.paidVnd() > 0));

            // First element -> output 0, second -> output 1.
            return Tuples.of(orderIndexes, paymentIndexes);
        };
    }
}
~~~

Read the signature as a **four-port contract**:

| Direction | Binding index | Java element | Payload type | Example |
| --- | ---: | --- | --- | --- |
| Input | 0 | `sources.getT1()` | `OrderCreated` | `{"orderId":"O-101","totalVnd":250000}` |
| Input | 1 | `sources.getT2()` | `PaymentConfirmed` | `{"orderId":"O-101","paidVnd":250000}` |
| Output | 0 | `result.getT1()` | `OrderIndex` | `{"orderId":"O-101","totalVnd":250000}` |
| Output | 1 | `result.getT2()` | `PaymentIndex` | `{"orderId":"O-101","hasPayment":true}` |

This example does **not** perform a key-based join between orders and payments. One message on input 0 produces one `OrderIndex`; one message on input 1 produces one `PaymentIndex`. That is the business design of this example, **not a rule that input index 0 must always go to output index 0**. Another function can merge two inputs into one stream or split each source across multiple outputs.

## 5. Mapping types and indices in Spring Cloud Stream

For the `mapChannels` bean, Spring Cloud Stream by default convention provides:

~~~text
                           Java bean: mapChannels
                         ┌──────────────────────────┐
orders.created ─────────►│ mapChannels-in-0          │
OrderCreated              │  sources.getT1()         │
                         │                          │
payments.confirmed ─────►│ mapChannels-in-1          │
PaymentConfirmed          │  sources.getT2()         │
                         │                          │
orders.indexed ◄─────────│ mapChannels-out-0         │
OrderIndex                │  result.getT1()          │
                         │                          │
payments.indexed ◄───────│ mapChannels-out-1         │
PaymentIndex              │  result.getT2()          │
                         └──────────────────────────┘
~~~

Correspondingly, you can configure `application.yml`:

~~~yaml
spring:
  cloud:
    function:
      definition: mapChannels
    stream:
      bindings:
        mapChannels-in-0:
          destination: orders.created
          content-type: application/json
        mapChannels-in-1:
          destination: payments.confirmed
          content-type: application/json
        mapChannels-out-0:
          destination: orders.indexed
          content-type: application/json
        mapChannels-out-1:
          destination: payments.indexed
          content-type: application/json
~~~

The generic signature gives the framework the **target payload type**; `content-type` adds context about the **wire data format**. Both inputs can use `application/json`, yet **the POJO types must be specified per port**: port 0 expects `OrderCreated`, port 1 expects `PaymentConfirmed`.

Appropriate dependencies are required for Spring Cloud Function, Spring Cloud Stream, Reactor, and the **binder** for the messaging system in use. Declaring a bean or setting `destination` in YAML does not automatically create a message broker.

### 5.1. Does renaming a binding change the Tuple index?

Spring Cloud Stream supports declaring human-friendly binding names via `spring.cloud.stream.function.bindings`. For example:

~~~yaml
spring:
  cloud:
    function:
      definition: mapChannels
    stream:
      function:
        bindings:
          mapChannels-in-0: incomingOrders
          mapChannels-out-0: indexedOrders
      bindings:
        incomingOrders:
          destination: orders.created
        indexedOrders:
          destination: orders.indexed
~~~

This snippet illustrates **two renamed mappings only**; in a complete application, you must still configure `mapChannels-in-1` and `mapChannels-out-1` as needed.

Renaming does **not** shift `getT1()` to the second element. Mapping only affects how bindings are named and configured. It can make configuration harder to trace, so the default naming convention is usually clearer when no special naming is required.

## 6. How do Java types and content types work together?

In Spring Cloud Function, input conversion typically relies on **two sources of information**:

1. **Target type**: the Java type declared in the function signature, such as `OrderCreated` or `PaymentConfirmed`.
2. **Content type**: format information in the message header or binding configuration, such as `application/json` or `text/plain`.

For example, content received at `mapChannels-in-0` is:

~~~json
{"orderId":"O-101","totalVnd":250000}
~~~

When the payload arrives as JSON bytes or a JSON string, a suitable converter can construct an `OrderCreated` for input 0. If you send the string `"O-101"` with `text/plain` to a port expecting `OrderCreated`, you cannot assume the framework will infer `totalVnd`; a converter may fail to convert it and throw an error.

Setting `content-type: application/json` is **not enough** to disambiguate among arbitrary Java classes. The target type in the function signature is essential; the content type only guides decoding/serialization.

| Scenario | Interpretation |
| --- | --- |
| Input 0: `application/json` + `OrderCreated` | JSON must match the `OrderCreated` structure |
| Input 1: `application/json` + `PaymentConfirmed` | JSON must match the `PaymentConfirmed` structure |
| Output 0: `OrderIndex` + `application/json` | Result can be serialized to JSON by the configured converter |
| Output 1: `PaymentIndex` + `application/json` | Serializes a different payload on a different binding |
| Input declared as raw `Flux<Object>` | Loses specific target type info; conversion may not yield the desired type |
| Wrong `content-type` header or config | Selects an unsuitable converter or causes conversion failure |

Precedence details between message headers, binding configuration, and conversion mechanisms can depend on the Spring Cloud Function/Stream version, binder, and how the adapter constructs `Message` objects. When troubleshooting, inspect **the actual payload, content type, and Java signature of the exact port** rather than only tweaking topic names.

### 6.1. Message<T> adds metadata, not another input

A function may need to read a `correlationId` header or tracing info:

~~~java
import org.springframework.messaging.Message;
import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;

// Two input bindings; each message has its own payload and headers.
Function<
    Tuple2<
        Flux<Message<OrderCreated>>,
        Flux<Message<PaymentConfirmed>>
    >,
    Flux<String>
> auditMessages;
~~~

Here, input 0 is `Message<OrderCreated>`, and input 1 is `Message<PaymentConfirmed>`. Wrapping in `Message<T>` does **not** increase the binding count: payload and headers belong to the same message on one port. `auditMessages` illustrates the signature; a function body must be implemented to use it.

For headers that must be preserved across multiple transformation steps, operate explicitly on `Message<T>` and build output messages with the appropriate headers. Do not assume all headers are automatically copied across every type conversion or adapter.

### 6.2. Type erasure and bean declarations

When working with generics and lambdas:

~~~java
// Recommended: @Bean method declares full generics on both sides.
@Bean
public Function<Flux<String>, Flux<Long>> parseNumbers() {
    return texts -> texts.map(Long::parseLong);
}
~~~

Avoid writing:

~~~java
// Avoid: raw types deprive the framework of an explicit payload contract.
@Bean
@SuppressWarnings({"rawtypes", "unchecked"})
public Function rawFunction() {
    return value -> value;
}
~~~

When type information is lost, a converter may not know whether to produce `OrderCreated`, `Long`, or another target type. Explicitly declaring generics on the public bean method gives the compiler, `FunctionCatalog`, and adapters a concrete basis for determining the contract.

## 7. Do not infer types or ports from variable names

The following pair can look similar at a glance:

~~~java
// One input carrying pairs of data.
Function<Flux<Tuple2<OrderCreated, PaymentConfirmed>>, Flux<String>>

// Two independent inputs.
Function<
    Tuple2<Flux<OrderCreated>, Flux<PaymentConfirmed>>,
    Flux<String>>
~~~

In the first signature, **each item** of a single `Flux` is an already-paired tuple of events, so there is only **one input**. In the second signature, there are **two independent inputs**; the function itself must decide whether to use `merge`, `zip`, `join`, or another correlation mechanism. The signature does not automatically join orders and payments by `orderId`.

Similarly, two return types:

~~~java
Flux<Tuple2<OrderIndex, PaymentIndex>>
Tuple2<Flux<OrderIndex>, Flux<PaymentIndex>>
~~~

are respectively **one stream of pairs** and **two separate streams**. Naming variables `firstOutput` or `secondOutput` does not change the port count; the **generic structure** is what determines it.

### 7.1. When adding a new input

Suppose the function initially uses:

~~~java
Tuple2<Flux<OrderCreated>, Flux<PaymentConfirmed>>
~~~

Later the system adds an inventory update stream:

~~~java
Tuple3<
    Flux<OrderCreated>,
    Flux<PaymentConfirmed>,
    Flux<InventoryUpdated>>
~~~

When appending `InventoryUpdated` at the **end** of the tuple, the existing bindings keep indices `0` and `1`, and the new input becomes `-in-2`. However, if you insert `InventoryUpdated` in the middle, subsequent ports will **shift indices**. You must update the signature, `getTn()` calls, binding configuration, and tests in sync.

General rule: **tuple ordering is part of the public configuration contract** in a Spring Cloud Stream application; changing positions can cause mapping bugs even while the code still compiles.

## 8. Testing port order and result types

The following unit test uses JUnit 5 and `reactor-test` to verify `mapChannels` directly. It requires no broker because it only verifies Java logic and tuple ordering.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.function.Tuples;

class MultiPortTypeConfigurationTest {

    @Test
    void preservesInputAndOutputTypesByTuplePosition() {
        var configuration = new MultiPortTypeConfiguration();

        var result = configuration.mapChannels().apply(Tuples.of(
                Flux.just(new MultiPortTypeConfiguration.OrderCreated(
                        "O-101", 250_000L)),
                Flux.just(new MultiPortTypeConfiguration.PaymentConfirmed(
                        "O-101", 250_000L))));

        // Collect data from both independent outputs.
        StepVerifier.create(Mono.zip(
                        result.getT1().collectList(),
                        result.getT2().collectList()))
                .assertNext(outputs -> {
                    assertEquals(
                            List.of(new MultiPortTypeConfiguration.OrderIndex(
                                    "O-101", 250_000L)),
                            outputs.getT1());
                    assertEquals(
                            List.of(new MultiPortTypeConfiguration.PaymentIndex(
                                    "O-101", true)),
                            outputs.getT2());
                })
                .verifyComplete();
    }
}
~~~

This test proves that the **first output tuple element** contains `OrderIndex` and the **second element** contains `PaymentIndex`, while verifying that data from the two inputs is processed by the right branches. It does not prove that external topics/queues are wired properly.

To verify binding configuration and real payload conversion, add an **integration test** with the Spring Cloud Stream Test Binder or an appropriate binder:

1. Send `OrderCreated` JSON to the destination of `mapChannels-in-0`.
2. Send `PaymentConfirmed` JSON to the destination of `mapChannels-in-1`.
3. Read outputs from the destinations corresponding to `mapChannels-out-0` and `mapChannels-out-1`.
4. Verify payload types, content types, message counts, important headers, and that messages did not swap ports.

`collectList()` fits finite `Flux.just(...)` sources in unit tests; for unbounded message broker streams, do not collect all items into memory waiting for completion.

## 9. Detecting index and type mismatch errors

| Symptom | Cause to check | How to fix |
| --- | --- | --- |
| Payment data enters the order branch | `-in-0` / `-in-1` mapped to wrong destinations | Cross-check `getT1()` and `getT2()` against the binding table |
| Output has right payload but goes to wrong topic | `Tuples.of(...)` order was swapped | Verify output 0 ↔ `getT1()`; output 1 ↔ `getT2()` |
| JSON deserialization error | Payload mismatches target POJO or content type is wrong | Inspect JSON, schema, per-input generics, and `content-type` |
| One port receives no messages | Wrong binding name, destination, binder, or group | Check `definition`, `-in-n` names, and binder config |
| Framework handles payload as `Object`/`Map` instead of desired POJO | Bean declared with raw or overly broad generics | Declare concrete types on the `@Bean` method |
| Errors after changing Tuple2 to Tuple3 | Added/inserted element without updating all indices | Check `-in-0`, `-in-1`, `-in-2`, accessors, and unit tests |
| Both inputs use `application/json` yet types behave unexpectedly | Confusing wire format with Java target type | Use exact `OrderCreated`/`PaymentConfirmed` generics per port |

**Protocol note:** Spring Cloud Function decouples logic from invocation mechanisms. Spring Cloud Stream defines input/output *bindings* and routing to topics/queues, whereas HTTP typically follows a request/response model. Do not assume a tuple with two `Flux` elements automatically creates two HTTP endpoints or two responses. Multi-port deployment depends on the environment's adapter and configuration.

**Composition note:** composing `a|b` connects the output of `a` to the input of `b` according to compatible contracts. Composition can change the externally visible binding names/contract types; evaluate based on the **composed bound function** rather than guessing names from individual inner beans. Composition itself does not reorder tuple elements by variable name.

## 10. Self-check exercises

**Question 1.** How many input/output ports does the following function have, and what type does `-in-1` carry?

~~~java
Function<
    Tuple3<Flux<String>, Flux<Long>, Flux<Boolean>>,
    Tuple2<Flux<Integer>, Flux<String>>>
~~~

**Answer:** **3 inputs, 2 outputs**. `-in-1` is the second input, corresponding to `getT2()`, carrying `Long` payloads. Output `-out-0` carries `Integer`; output `-out-1` carries `String`.

**Question 2.** If the `mapChannels` bean returns `Tuples.of(paymentIndexes, orderIndexes)` while keeping the output bindings in the YAML above, what happens?

**Answer:** The two outputs are **swapped in order**. With the return generic signature still `Tuple2<Flux<OrderIndex>, Flux<PaymentIndex>>`, that code will **fail type checking at compile time** (without unsafe casting). If the signature were updated to match without updating the bindings, data would go to the wrong destinations.

**Question 3.** Both ports are configured with `content-type: application/json`. Can you send `PaymentConfirmed` JSON to input 0 and expect the converter to turn it into `OrderCreated`?

**Answer:** No. `application/json` only specifies the format; input 0 still requires the `OrderCreated` structure. The JSON must satisfy that type's contract; missing/mismatched fields can cause errors or invalid data depending on the converter and validation.

**Question 4.** Does `Flux<Tuple2<A, B>>` have two output bindings because `Tuple2` holds two elements?

**Answer:** No. That is **one Flux** emitting pairs of `A` and `B`, meaning one logical output port. Two separate reactive ports require a structure like `Tuple2<Flux<A>, Flux<B>>` and an adapter supporting function arity.

**Question 5.** If you need to preserve the `correlationId` header on processed events, do you need to add an extra input binding for the header?

**Answer:** No. Use `Message<T>` to access both payload and headers within the same message, and process or copy headers to the result message as needed.

## References

- [Spring Cloud Stream — Functional binding names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
- [Spring Cloud Stream — Functions with multiple input and output arguments](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Function — Programming model and Type conversion](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Project Reactor — Tuple2 API](https://projectreactor.io/docs/core/release/api/reactor/util/function/Tuple2.html)
