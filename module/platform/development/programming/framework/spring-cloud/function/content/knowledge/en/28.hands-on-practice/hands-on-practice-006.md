# Splitting and Combining Multiple Streams with Reactor Tuple

## 1. Practice Problem

In **Spring Cloud Function** (`SPRING_CLOUD_FUNCTION`), business logic is declared as `Supplier`, `Function`, or `Consumer` beans and managed by `FunctionCatalog`. In event-driven applications, a function sometimes needs to consume **multiple data streams simultaneously** or emit **multiple output streams**. Spring Cloud Function uses **Reactor Tuple** to represent the arity and type of each stream, while Project Reactor provides operators to combine or split publishers.

We will build an event-processing application solving three scenarios:

1. **Combine two sources:** receive a stream of order notifications and a stream of customer notifications, add labels, and merge them into a single unified event stream.
2. **Pair two streams:** receive a stream of quantities and a stream of unit prices, pairing corresponding elements to calculate line totals.
3. **Split one stream:** receive integers and classify even and odd numbers into two independent output streams.

~~~text
MULTIPLE INPUTS

orders: Flux<String> -----\
                           +--> Tuple2<Flux<String>, Flux<String>>
customers: Flux<String> --/                 |
                                            v
                                       mergeLabels
                                            |
                                            v
                                  Flux<String> merged


SINGLE INPUT, MULTIPLE OUTPUTS

numbers: Flux<Integer>
          |
          v
      splitParity
          |
          v
Tuple2<Flux<String>, Flux<String>>
          |                 |
          v                 v
      even stream       odd stream
          |                 |
          v                 v
    even-events        odd-events
~~~

**Goal:** understand `TupleN<Flux<...>>` signatures, use `Tuples.of(...)`, pick the right Reactor operator (`merge`, `zip`, `concat`, `combineLatest`), test with `StepVerifier`, and configure multiple Spring Cloud Stream bindings.

After this lesson, you will be able to:

- Distinguish a tuple holding multiple publishers from a single publisher emitting tuples.
- Declare reactive functions with two or three input streams.
- Declare reactive functions producing two output streams.
- Understand `-in-0`, `-in-1`, `-out-0`, and `-out-1` indices.
- Choose merge or pairing operators based on data semantics.
- Test using `StepVerifier` and `FunctionCatalog`.
- Recognize limitations around subscriptions, backpressure, cancellation, and errors across multiple branches.

> **Important condition:** Spring Cloud Function's function arity support (multiple inputs/outputs) targets **reactive functions** with signatures like `Function<TupleN<Flux<?>...>, TupleN<Flux<?>...>>`. Do not confuse this tuple with a mechanism for declaring multiple plain Java parameters on an imperative `Function<A,B>`.

## 2. What Does Reactor Tuple Represent?

Project Reactor provides `Tuple2`, `Tuple3`, etc., along with the `Tuples.of(...)` factory. A tuple has a fixed **arity** (element count) and **static type** per slot.

Example:

~~~java
Tuple2<Flux<String>, Flux<Integer>> inputs =
        Tuples.of(
                Flux.just("order-A", "order-B"),
                Flux.just(10, 20));
~~~

The tuple above contains:

- `getT1()`: a `Flux<String>`.
- `getT2()`: a `Flux<Integer>`.

It does not mean a single `Flux` emitting a pair of `String` and `Integer` on each `onNext`.

### 2.1. Distinguishing Two Easily Confused Types

| Type | Meaning |
| --- | --- |
| `Tuple2<Flux<A>, Flux<B>>` | A tuple holding **two independent publishers**; each publisher can emit multiple items |
| `Flux<Tuple2<A, B>>` | **A single publisher** emitting `(A, B)` pairs |
| `Tuple2<A, B>` | A single pair of values, not two streams |
| `Flux<A>` | A single stream of A items |

~~~text
Tuple2<Flux<A>, Flux<B>>
   +--------------------+
   | Flux<A>: A1, A2... |
   | Flux<B>: B1, B2... |
   +--------------------+

Flux<Tuple2<A, B>>
   +--------------------+
   | (A1, B1)           |
   | (A2, B2)           |
   | (A3, B3)           |
   +--------------------+
~~~

These two contracts differ in subscription behavior, data pairing, and binding count. Choose the type to fit the problem: multiple independent sources use a tuple of publishers; one source already emitting pairs uses `Flux<Tuple2<A,B>>`.

### 2.2. Tuple2, Tuple3, and Stream Count

Two-source example:

~~~java
Function<Tuple2<Flux<String>, Flux<Integer>>, Flux<String>>
~~~

Three-source example:

~~~java
Function<
    Tuple3<Flux<OrderEvent>, Flux<PaymentEvent>, Flux<CustomerEvent>>,
    Flux<String>
>
~~~

With `Tuple3`, access slots via `getT1()`, `getT2()`, and `getT3()`. The tuple's arity tells the framework **how many input/output bindings** to create; the generic type at each slot provides payload conversion metadata.

Do not replace tuples with `List<Flux<?>>` or `Object[]` just to shorten type declarations. Those types erase the arity and per-slot type information that the framework requires.

## 3. Choosing Operators to Combine Streams

Reactor offers several ways to coordinate publishers. They are not interchangeable.

| Operator | Behavior | When to Use |
| --- | --- | --- |
| `Flux.merge(a, b)` | Emits items from sources as they arrive; relative order across sources may interleave | Combining independent events into one stream |
| `Flux.concat(a, b)` | Waits for A to complete before subscribing/emitting B | Processing sources sequentially |
| `Flux.zip(a, b)` | Pairs the nth element of A with the nth element of B | Two sources correlated by position/order |
| `a.zipWith(b)` | Instance form of zip | Pairing two publishers |
| `Flux.combineLatest(a, b, fn)` | Once every source has emitted at least once, combines the latest value of each source on any update | Snapshot / latest-state streams |

### 3.1. merge Does Not Pair Items

~~~java
Flux<String> orders = Flux.just("O-1", "O-2");
Flux<String> customers = Flux.just("C-1", "C-2");

Flux<String> merged = Flux.merge(
        orders.map(value -> "ORDER:" + value),
        customers.map(value -> "CUSTOMER:" + value));
~~~

Output has four items, but interleaving between the two sources depends on emission timing. `merge` does not guarantee that `O-1` pairs with `C-1`.

### 3.2. zip Pairs by Position

~~~java
Flux<String> skus = Flux.just("PEN", "BOOK");
Flux<Integer> quantities = Flux.just(2, 3);

Flux<String> lines = Flux.zip(
        skus,
        quantities,
        (sku, quantity) -> sku + ":" + quantity);
~~~

Output:

~~~text
PEN:2
BOOK:3
~~~

`zip` waits for one item from each source to form a pair. Once any source completes, the zipped publisher normally completes and emits no more pairs. If two streams differ in speed or length, excess items from the longer stream do not form pairs.

**Business warning:** positional zipping is only valid when both sources guarantee matching order. If `skus` and `quantities` arrive from two independent topics, you cannot assume the first item on topic A belongs to the same entry as the first item on topic B. Join by a key such as `orderId`, `sku`, or event ID using an explicit join/state strategy instead.

### 3.3. combineLatest Is Not zip

`combineLatest` retains the most recent value from each source. Once both sources have emitted at least one item, each update from either source can emit a new output paired with the other source's latest value.

~~~java
Flux<String> price = Flux.just("P10", "P12");
Flux<String> stock = Flux.just("S5", "S4");

Flux<String> snapshots = Flux.combineLatest(
        price,
        stock,
        (p, s) -> p + "/" + s);
~~~

With synchronous sources like `Flux.just`, subscription timing and scheduling may cause intermediate snapshots to differ from simple illustrations. In real systems, test with actual schedulers and emission rates. `combineLatest` fits **latest state** views, not pairing one transaction with its exact matching event.

### 3.4. Quick Selection Guide

- To combine independent events: choose `merge`.
- To run one source completely before another: choose `concat`.
- To pair items correlated by position: choose `zip`.
- To react to the latest state across multiple sources: choose `combineLatest`.
- To join by ID or time window: use a dedicated join/state/window strategy; never substitute positional zip.

## 4. Preparing the Maven Project

The lab uses **JDK 17**, **Maven 3.9+**, **Spring Boot 3.5.0**, and **Spring Cloud 2025.0.0** as an example baseline. This release train pair manages Spring Cloud Function/Stream versions via the BOM. For new projects, pick supported patches within a compatible release train rather than mixing individual versions.

Create the directory `reactor-tuple-lab`:

~~~text
reactor-tuple-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/tuplelab/
    │   │   ├── TupleLabApplication.java
    │   │   └── StreamFunctions.java
    │   └── resources/application.yml
    └── test/
        └── java/com/example/tuplelab/
            ├── TupleFunctionUnitTest.java
            └── TupleFunctionCatalogTest.java
~~~

To stay focused on `FunctionCatalog` and Reactor, the core tests do not require a broker. Spring Cloud Stream dependencies are added in the multi-binding deployment section.

### 4.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>reactor-tuple-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>reactor-tuple-lab</name>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>2025.0.0</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-function-context</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

| Dependency | Role |
| --- | --- |
| `spring-boot-starter` | Spring context and auto-configuration |
| `spring-cloud-function-context` | `FunctionCatalog` and functional beans |
| `spring-boot-starter-test` | JUnit 5, Spring Boot Test, assertions |
| `reactor-test` | `StepVerifier`, virtual time, and Reactor testing utilities |

Reactor Core is normally already on the classpath via Spring Cloud Function. If your code needs an explicit dependency for `Flux`, `Tuple2`, and `Tuples`, you can declare `io.projectreactor:reactor-core` while letting the BOM manage its version.

## 5. Declaring Functions with Multiple Inputs and Outputs

Create `StreamFunctions.java`:

~~~java
package com.example.tuplelab;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;
import reactor.util.function.Tuples;
import reactor.util.function.Tuple3;

@Configuration(proxyBeanMethods = false)
public class StreamFunctions {

    // Two input streams -> one output stream.
    @Bean
    public Function<
            Tuple2<Flux<String>, Flux<String>>,
            Flux<String>> mergeLabels() {

        return tuple -> {
            Flux<String> orders = tuple.getT1()
                    .map(value -> "ORDER:" + value);
            Flux<String> customers = tuple.getT2()
                    .map(value -> "CUSTOMER:" + value);

            return Flux.merge(orders, customers);
        };
    }

    // Two input streams -> pair by position -> one output.
    @Bean
    public Function<
            Tuple2<Flux<Integer>, Flux<Integer>>,
            Flux<String>> zipQuantitiesAndPrices() {

        return tuple -> Flux.zip(
                tuple.getT1(),
                tuple.getT2(),
                (quantity, unitPrice) ->
                        "LINE_TOTAL:" + Math.multiplyExact(
                                quantity.longValue(),
                                unitPrice.longValue()));
    }

    // One input stream -> two output streams.
    @Bean
    public Function<
            Flux<Integer>,
            Tuple2<Flux<String>, Flux<String>>> splitParity() {

        return numbers -> {
            // Both output bindings must observe the same upstream source.
            // autoConnect(2) waits for both branches to subscribe before connecting upstream.
            Flux<Integer> shared = numbers.publish().autoConnect(2);

            Flux<String> even = shared
                    .filter(number -> number % 2 == 0)
                    .map(number -> "EVEN:" + number);

            Flux<String> odd = shared
                    .filter(number -> number % 2 != 0)
                    .map(number -> "ODD:" + number);

            return Tuples.of(even, odd);
        };
    }

    // Three input streams -> one output stream.
    @Bean
    public Function<
            Tuple3<Flux<String>, Flux<String>, Flux<String>>,
            Flux<String>> mergeThreeSources() {

        return tuple -> Flux.merge(
                tuple.getT1().map(value -> "A:" + value),
                tuple.getT2().map(value -> "B:" + value),
                tuple.getT3().map(value -> "C:" + value));
    }
}
~~~

### 5.1. mergeLabels: Multiple Inputs, One Output

Signature:

~~~java
Function<Tuple2<Flux<String>, Flux<String>>, Flux<String>>
~~~

`Tuple2` holds two streams. The function extracts each stream with `getT1()` and `getT2()`, attaches labels, and calls `Flux.merge(...)`.

Example input:

~~~text
Input 0: ["O-1", "O-2"]
Input 1: ["C-1", "C-2"]
~~~

Output produces four values:

~~~text
ORDER:O-1
ORDER:O-2
CUSTOMER:C-1
CUSTOMER:C-2
~~~

Interleaving order between the two sources is not guaranteed. `merge` emits as signals arrive; do not use output position to infer an order/customer pairing.

### 5.2. zipQuantitiesAndPrices: Pairing by Position

Signature:

~~~java
Function<Tuple2<Flux<Integer>, Flux<Integer>>, Flux<String>>
~~~

The first input is quantity; the second is unit price. `Flux.zip` pairs items positionally:

~~~text
quantity:  [2, 3, 1]
unitPrice: [100, 50, 200]
               |
               v
        zip(quantity, unitPrice)
               |
               v
LINE_TOTAL:200
LINE_TOTAL:150
LINE_TOTAL:200
~~~

`Math.multiplyExact` catches overflow instead of silently producing wrong numbers. In real applications, pass keyed records and join by `sku`/`orderId` if the two streams lack ordering guarantees.

### 5.3. splitParity: One Input, Two Outputs

Signature:

~~~java
Function<Flux<Integer>, Tuple2<Flux<String>, Flux<String>>>
~~~

The input is split into two branches:

- `getT1()`: even numbers prefixed with `EVEN:`.
- `getT2()`: odd numbers prefixed with `ODD:`.

Because the two outputs are subscribed independently by two output bindings, you should not attach two independent transformations directly to a hot or unicast source without sharing it. `publish().autoConnect(2)` in the example waits for two subscribers to connect before subscribing upstream once.

**Condition:** this mechanism assumes the adapter will subscribe to both outputs. If one output is unbound or unsubscribed, upstream may never start. This is a trade-off to test in your actual configuration, not the only sharing pattern for every application.

### 5.4. mergeThreeSources: Three Inputs

`Tuple3<Flux<String>, Flux<String>, Flux<String>>` represents three independent inputs. Use `getT1()`, `getT2()`, `getT3()`, and `Flux.merge(...)`.

For even more streams, Reactor provides `Tuple4`, `Tuple5`, etc., though signatures grow long and hard to maintain. Consider a unified event schema or a clearer ingress model as the number of sources grows.

## 6. Spring Boot Startup and Default Configuration

Create `TupleLabApplication.java`:

~~~java
package com.example.tuplelab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TupleLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(TupleLabApplication.class, args);
    }
}
~~~

Create `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: reactor-tuple-lab
  cloud:
    function:
      single-function-fallback-enabled: false
~~~

In catalog tests, we look up each function by name. When enabling Spring Cloud Stream later, explicitly configure `spring.cloud.function.definition` to choose which functions get bindings.

## 7. Testing Each Function with StepVerifier

`StepVerifier` asserts Reactive Streams signals: `onNext`, `onComplete`, and `onError`. For multi-output streams, tests must subscribe to **both branches** when the function shares upstream via `autoConnect(2)`.

Create `TupleFunctionUnitTest.java`:

~~~java
package com.example.tuplelab;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.function.Function;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.util.function.Tuple2;
import reactor.util.function.Tuples;

class TupleFunctionUnitTest {

    private final StreamFunctions functions = new StreamFunctions();

    @Test
    void mergesTwoInputStreams() {
        Function<
                Tuple2<Flux<String>, Flux<String>>,
                Flux<String>> function = functions.mergeLabels();

        Tuple2<Flux<String>, Flux<String>> input = Tuples.of(
                Flux.just("O-1", "O-2"),
                Flux.just("C-1", "C-2"));

        StepVerifier.create(function.apply(input).collectList())
                .assertNext(values -> assertEquals(
                        Set.of(
                                "ORDER:O-1",
                                "ORDER:O-2",
                                "CUSTOMER:C-1",
                                "CUSTOMER:C-2"),
                        new HashSet<>(values)))
                .verifyComplete();
    }

    @Test
    void zipsQuantitiesAndPricesByPosition() {
        Function<
                Tuple2<Flux<Integer>, Flux<Integer>>,
                Flux<String>> function =
                functions.zipQuantitiesAndPrices();

        Tuple2<Flux<Integer>, Flux<Integer>> input = Tuples.of(
                Flux.just(2, 3, 1),
                Flux.just(100, 50, 200));

        StepVerifier.create(function.apply(input))
                .expectNext(
                        "LINE_TOTAL:200",
                        "LINE_TOTAL:150",
                        "LINE_TOTAL:200")
                .verifyComplete();
    }

    @Test
    void zipCompletesWhenTheShortestInputCompletes() {
        Function<
                Tuple2<Flux<Integer>, Flux<Integer>>,
                Flux<String>> function =
                functions.zipQuantitiesAndPrices();

        Tuple2<Flux<Integer>, Flux<Integer>> input = Tuples.of(
                Flux.just(2, 3, 1),
                Flux.just(100));

        StepVerifier.create(function.apply(input))
                .expectNext("LINE_TOTAL:200")
                .verifyComplete();
    }

    @Test
    void splitsOneInputIntoEvenAndOddOutputs() {
        Function<
                Flux<Integer>,
                Tuple2<Flux<String>, Flux<String>>> function =
                functions.splitParity();

        Tuple2<Flux<String>, Flux<String>> outputs =
                function.apply(Flux.range(1, 6));

        // Subscribe to both outputs simultaneously so autoConnect(2) starts the source.
        Flux<Tuple2<List<String>, List<String>>> both =
                Flux.zip(
                        outputs.getT1().collectList(),
                        outputs.getT2().collectList());

        StepVerifier.create(both)
                .assertNext(tuple -> {
                    assertEquals(
                            List.of("EVEN:2", "EVEN:4", "EVEN:6"),
                            tuple.getT1());
                    assertEquals(
                            List.of("ODD:1", "ODD:3", "ODD:5"),
                            tuple.getT2());
                })
                .verifyComplete();
    }

    @Test
    void mergesThreeInputStreams() {
        var input = Tuples.of(
                Flux.just("1"),
                Flux.just("2"),
                Flux.just("3"));

        StepVerifier.create(
                        functions.mergeThreeSources()
                                .apply(input)
                                .collectList())
                .assertNext(values -> assertEquals(
                        Set.of("A:1", "B:2", "C:3"),
                        new HashSet<>(values)))
                .verifyComplete();
    }
}
~~~

### 7.1. Why Does the merge Test Compare Sets?

`Flux.merge` can interleave sources depending on emission timing. Tests should assert **which elements are present**, without asserting strict ordering if the contract does not guarantee order.

### 7.2. Why Does the zip Test Check the Shortest Stream?

Once a publisher completes, `zip` can no longer form pairs without a corresponding element from that publisher. The test `zipCompletesWhenTheShortestInputCompletes` proves the output emits one pair and completes even though the quantity stream has three items.

### 7.3. Why Must the split Test Subscribe to Both Outputs?

The function uses:

~~~java
Flux<Integer> shared = numbers.publish().autoConnect(2);
~~~

It only connects to the source after two subscribers subscribe. `Flux.zip(outputs.getT1().collectList(), outputs.getT2().collectList())` subscribes to both branches at once. Testing only `getT1()` while `autoConnect(2)` is waiting could hang or time out.

## 8. Testing Reactive Functions Through FunctionCatalog

Direct unit tests verify Reactor logic. Next, start the Spring context to verify that the beans are registered in `FunctionCatalog` and can be looked up by name.

Create `TupleFunctionCatalogTest.java`:

~~~java
package com.example.tuplelab;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.util.function.Tuple2;
import reactor.util.function.Tuples;

@SpringBootTest(
        classes = TupleLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class TupleFunctionCatalogTest {

    @Autowired
    private FunctionCatalog catalog;

    @Test
    void looksUpFunctionWithTwoInputs() {
        Function<
                Tuple2<Flux<String>, Flux<String>>,
                Flux<String>> function =
                catalog.lookup("mergeLabels");

        assertNotNull(function);

        var input = Tuples.of(
                Flux.just("O-10"),
                Flux.just("C-10"));

        StepVerifier.create(function.apply(input).collectList())
                .assertNext(values -> assertEquals(
                        Set.of("ORDER:O-10", "CUSTOMER:C-10"),
                        new HashSet<>(values)))
                .verifyComplete();
    }

    @Test
    void looksUpFunctionWithMultipleOutputs() {
        Function<
                Flux<Integer>,
                Tuple2<Flux<String>, Flux<String>>> function =
                catalog.lookup("splitParity");

        assertNotNull(function);

        Tuple2<Flux<String>, Flux<String>> output =
                function.apply(Flux.range(1, 4));

        Flux<Tuple2<List<String>, List<String>>> both =
                Flux.zip(
                        output.getT1().collectList(),
                        output.getT2().collectList());

        StepVerifier.create(both)
                .assertNext(tuple -> {
                    assertEquals(
                            List.of("EVEN:2", "EVEN:4"),
                            tuple.getT1());
                    assertEquals(
                            List.of("ODD:1", "ODD:3"),
                            tuple.getT2());
                })
                .verifyComplete();
    }
}
~~~

This test proves:

- Spring registered `mergeLabels` and `splitParity`.
- The catalog can look up functions accepting tuples of multiple publishers.
- Multi-output functions return tuples with the expected output ordering.
- Both outputs can be verified concurrently using `StepVerifier`.

**Limitation:** this is still a `FunctionCatalog` test inside the application context. It does not prove Spring Cloud Stream creates the bindings or that a broker actually delivers two input streams to the function.

## 9. Multiple Inputs and Outputs in Spring Cloud Stream

Spring Cloud Stream generates binding names from the function name and input/output index:

- Input: `<functionName>-in-<index>`
- Output: `<functionName>-out-<index>`

Indices start at 0. For functions with multiple inputs or outputs, each tuple slot maps to its own binding.

### 9.1. Bindings for mergeLabels

Signature:

~~~java
Function<Tuple2<Flux<String>, Flux<String>>, Flux<String>>
~~~

There are two inputs and one output:

| Tuple Slot | Binding | Example Destination |
| --- | --- | --- |
| `getT1()` | `mergeLabels-in-0` | `orders.events` |
| `getT2()` | `mergeLabels-in-1` | `customers.events` |
| Output | `mergeLabels-out-0` | `activity.events` |

### 9.2. Bindings for splitParity

Signature:

~~~java
Function<Flux<Integer>, Tuple2<Flux<String>, Flux<String>>>
~~~

There is one input and two outputs:

| Tuple Slot | Binding | Example Destination |
| --- | --- | --- |
| Input | `splitParity-in-0` | `numbers.in` |
| `getT1()` | `splitParity-out-0` | `numbers.even` |
| `getT2()` | `splitParity-out-1` | `numbers.odd` |

The order of `getT1()`/`getT2()` must match the output binding order. Swapping tuple slots sends even/odd items to the wrong destinations.

### 9.3. application.yml Configuration for Both Functions

To bind both functions simultaneously, add Spring Cloud Stream and an appropriate binder in Maven, then configure:

~~~yaml
spring:
  cloud:
    function:
      definition: mergeLabels;splitParity
    stream:
      bindings:
        mergeLabels-in-0:
          destination: orders.events
          group: tuple-lab
          content-type: text/plain
        mergeLabels-in-1:
          destination: customers.events
          group: tuple-lab
          content-type: text/plain
        mergeLabels-out-0:
          destination: activity.events
          content-type: text/plain

        splitParity-in-0:
          destination: numbers.in
          group: tuple-lab
          content-type: application/json
        splitParity-out-0:
          destination: numbers.even
          content-type: text/plain
        splitParity-out-1:
          destination: numbers.odd
          content-type: text/plain
~~~

Here, `;` in `spring.cloud.function.definition` selects **two independent functions** to bind in the application. It is not the `|` composition operator. Each function retains its own bindings by name and index.

This example is only the binding configuration; to actually run it, you also need:

- BOM-compatible `spring-cloud-stream` and a binder (Kafka or RabbitMQ).
- Broker addresses, credentials, and topics/queues configured.
- Header/content-type and serialization tests for that binder.
- Retry, DLQ, concurrency, and monitoring policies.

### 9.4. Bindings for a Three-Input Function

For `mergeThreeSources`, the three inputs are named:

~~~text
mergeThreeSources-in-0
mergeThreeSources-in-1
mergeThreeSources-in-2
~~~

Output:

~~~text
mergeThreeSources-out-0
~~~

This is how tuples express cardinality. Each input can map to its own destination and have separate content-type and consumer properties.

## 10. Subscription Notes for Multiple Outputs

A function returning two `Flux` streams is not simply creating two collections and returning them. Each output binding normally subscribes to its own output publisher. Carefully consider how both outputs observe the incoming source.

### 10.1. Two Branches Can Trigger Two Upstream Subscriptions

Error-prone example:

~~~java
return Tuples.of(
        input.filter(value -> value % 2 == 0),
        input.filter(value -> value % 2 != 0));
~~~

If `input` is a cold publisher, two branches may subscribe separately and execute upstream twice. If the source is a unicast/hot publisher, a second subscription might fail or receive different data.

### 10.2. Sharing the Source with publish

The lab uses:

~~~java
Flux<Integer> shared = input.publish().autoConnect(2);
~~~

`publish()` enables sharing the upstream subscription; `autoConnect(2)` connects once two subscribers have registered. Each branch receives a view of the same source:

~~~text
                 input Flux
                     |
              publish/autoConnect(2)
                     |
             +-------+-------+
             |               |
           even            odd
             |               |
             v               v
          output 0         output 1
~~~

The count `2` must match the number of output subscribers. With three outputs, re-evaluate the subscriber count and lifecycle. Never hardcode a magic count and reuse it blindly across every function.

### 10.3. Cancellation and Errors

With multiple outputs:

- If one output cancels, decide whether the remaining branch should continue.
- If upstream emits `onError`, all branches sharing that source may receive the error.
- If one branch processes slowly, backpressure and buffering affect the shared source.
- If the binder subscribes to only one output, `autoConnect(2)` may never connect to the source.

That is why you must test with both outputs in unit tests and test the binder in deployment.

## 11. Backpressure and Stream Processing Strategies

Reactive Streams uses backpressure for downstream to signal demand. However, how backpressure propagates from a broker through a binder to a publisher depends on the binder and adapter.

With multiple inputs:

- A slow input can stall `zip`, while a fast input buffers elements.
- `merge` can interleave multiple sources; limit concurrency/buffering for large streams.
- `combineLatest` keeps only the latest value from each source.
- `concat` processes sequentially, which can increase latency for trailing sources.

With multiple outputs:

- A slow output branch can throttle the shared source.
- Operators like `onBackpressureBuffer`, `onBackpressureDrop`, or `onBackpressureLatest` have distinct semantics; picking the wrong one can lose events or exhaust memory.
- Never add unbounded buffers just to "fix" a slow output.

Example limiting in-flight items when calling an async service:

~~~java
Flux<String> results = input.flatMap(
        value -> callRemoteService(value),
        8);
~~~

The `8` argument caps `flatMap` concurrency; this is just a Reactor example, not a universal guarantee for every adapter. In production, tune concurrency to match connection pools, brokers, latency, and downstream service limits.

## 12. How Does an Error in One Stream Affect Others?

Reactive publishers emit `onError` as a terminal signal. With `merge`, `zip`, or `combineLatest`, an error from one source normally terminates the combined publisher and cancels the remaining sources unless you explicitly apply another error-handling policy.

### 12.1. Handling Errors per Source Before Merging

~~~java
Flux<String> safeOrders = orders.onErrorResume(error ->
        Flux.just("ORDER_SOURCE_FAILED"));

Flux<String> safeCustomers = customers.onErrorResume(error ->
        Flux.just("CUSTOMER_SOURCE_FAILED"));

return Flux.merge(safeOrders, safeCustomers);
~~~

This is an illustrative policy: replacing a source error with a sentinel event. Real systems should use a structured error schema and correlation IDs; never use sentinel strings if they might collide with valid data.

### 12.2. zip and Errors

`zip` requires one element from each source to produce a pair. If one source errors, `zip` normally errors and cancels the other sources. If one source completes early, `zip` may complete without consuming excess items from other sources.

If data must be joined by key, using `onErrorResume` followed by `zip` can create mismatched pairs. Keep transport errors separate from data correlation logic.

### 12.3. Single-Output Failure in a Fan-Out Function

When two outputs split from one upstream:

- An error occurring before the split point typically affects both outputs.
- An error inside one branch's private transformation may affect only that branch, depending on error handling and subscriptions.
- The adapter/binder also governs retries, DLQ routing, or binding failure.

Never assume one failing output automatically rolls back the other output. If two outputs represent a transaction requiring consistency, design an outbox/transaction or event choreography pattern.

## 13. Testing Errors and Cancellation

You can add a test for `zip` when one source errors:

~~~java
@Test
void zipPropagatesInputError() {
    Flux<Integer> quantities = Flux.just(2, 3);
    Flux<Integer> prices = Flux.concat(
            Flux.just(100),
            Flux.error(new IllegalStateException("price source failed")));

    Flux<String> result = Flux.zip(
            quantities,
            prices,
            (quantity, price) -> "TOTAL:" + quantity * price);

    StepVerifier.create(result)
            .expectNext("TOTAL:200")
            .expectError(IllegalStateException.class)
            .verify();
}
~~~

This test proves that an error from one source propagates through the combined publisher. It does not test broker retries or DLQs.

To test cancellation, use `doOnCancel` or `TestPublisher` in a dedicated test. What matters is identifying **who cancels the publisher**: downstream client, output binding, timeout, or an error on another source.

## 14. Tuple Is Not a Key-Based Join Tool

Tuples express stream count and types, but **do not define how events correlate**. Choosing `zip` does not mean two events at the same index share the same order ID.

Suppose:

~~~text
orders:
  O-1, O-2, O-3

payments:
  payment(O-2), payment(O-1), payment(O-3)
~~~

Positional `zip` will pair:

~~~text
O-1 <-> payment(O-2)  (wrong)
O-2 <-> payment(O-1)  (wrong)
O-3 <-> payment(O-3)  (right)
~~~

To join by `orderId`, you must:

- Include an explicit correlation key in every event.
- Choose a proper join/state/window mechanism.
- Define rules for late events, duplicates, timeouts, and missing data.
- Enforce state cleanup policies to prevent unbounded memory growth.

In pure Reactor, logic can be built with `groupBy`, `window`, `buffer`, or a proper state store. For complex event-time or windowed joins, consider a dedicated stream-processing engine rather than writing an unchecked custom operator.

## 15. Extending Binder Configuration and Integration Testing

Once unit and catalog tests pass, add Spring Cloud Stream with the appropriate binder. You can use the Test Binder to verify bindings without an external broker, or run Kafka/RabbitMQ in an integration test environment.

An adapter test should verify:

1. Both input bindings of `mergeLabels` are created.
2. Messages from both destinations arrive in the right tuple slots.
3. `mergeLabels` output goes to `mergeLabels-out-0`.
4. `splitParity` creates both output bindings.
5. Even events go to `splitParity-out-0`; odd events go to `splitParity-out-1`.
6. Input errors follow configured retry/DLQ behavior.
7. When one output slows down or stops, the other branch's behavior is well-defined.

**Never substitute catalog tests for binder tests:** catalog tests do not create topics/queues, verify transport serialization, or prove broker header mapping.

## 16. Extension Exercises

### Exercise A — Using Tuple3 to Merge Three Event Types

Create a function:

~~~java
Function<
    Tuple3<Flux<OrderEvent>, Flux<PaymentEvent>, Flux<ShipmentEvent>>,
    Flux<String>
>
~~~

**Requirements:**

- Label each event type.
- Use `Flux.merge`.
- Test all three inputs.
- Compare result sets rather than assuming interleaving order.

### Exercise B — Pairing Quantity and Unit Price with zip

Use `Tuple2<Flux<Integer>, Flux<Long>>`:

- Input 0 is quantity.
- Input 1 is unit price.
- Output is each line total.

**Requirements:** test two streams of equal length, one shorter stream, and an overflow case. Document the assumption that both streams must maintain matching order.

### Exercise C — Splitting Events by Status

Replace even/odd with:

~~~text
Flux<OrderEvent>
    -> Tuple2<Flux<OrderEvent>, Flux<OrderEvent>>
    -> approved / rejected
~~~

**Requirements:** only one branch receives each event; subscribe to both outputs in tests. Add an `orderId` field to verify no events are lost or duplicated.

### Exercise D — Comparing merge and concat

Create two sources using `delayElements`. Apply `merge` and `concat` and observe emission ordering.

**Requirements:** explain why `concat` emits all of the first source before the second, while `merge` interleaves according to emission timing.

### Exercise E — Handling a Failing Source

Create two inputs where one may emit an error. Try three policies:

- Let the error propagate out.
- Use `onErrorResume` to substitute an error event.
- Route errors to a separate output stream.

**Requirements:** test `onError` and `onComplete`; state clearly which data may be lost or replayed.

### Exercise F — Creating Bindings for Multiple Inputs/Outputs

Add the Spring Cloud Stream Test Binder:

- Send messages to `mergeLabels-in-0` and `mergeLabels-in-1`.
- Read from `mergeLabels-out-0`.
- Send messages to `splitParity-in-0`.
- Read from both `splitParity-out-0` and `splitParity-out-1`.

**Requirements:** verify binding counts and tuple slot ordering. Do not test only one output and assume the other works.

## 17. Common Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Function not recognized as multi-input | Used `Tuple2<String,String>` instead of tuple of `Flux` | Use reactive arity `Tuple2<Flux<A>,Flux<B>>` |
| Only one input binding created | Signature does not expose a multi-stream tuple | Check tuple generics and Stream dependencies |
| Second output binding not created | Return type is not a tuple of publishers | Return `Tuple2<Flux<A>,Flux<B>>` |
| Confusing `Tuple2<Flux<A>,Flux<B>>` with `Flux<Tuple2<A,B>>` | Tuple of streams differs from stream of tuples | Inspect generic types and cardinality |
| `zip` drops trailing items | One source is shorter | Pick different semantics or handle unmatched events |
| `zip` pairs wrong orders | Two sources lack aligned ordering | Join by key instead of positional index |
| Flaky `merge` tests | Tests assume fixed interleaving order | Assert set membership or per-source order only |
| `splitParity` emits nothing | `autoConnect(2)` has only one subscriber | Subscribe to both outputs; verify binder creates both bindings |
| Upstream executes twice | Two branches subscribe directly to a cold source | Share upstream intentionally or ensure idempotency |
| One output misses early items | Hot publisher subscribed late by second branch | Synchronize subscriptions or design replay/buffering |
| Error in one source stops all sources | Combining operator propagates terminal `onError` | Define error policy before merge/zip |
| Buffer grows continuously | One branch consumes slowly | Cap buffers/concurrency and monitor backpressure |
| Catalog test passes but binder fails | Bindings/serialization not tested | Write Test Binder or broker integration tests |
| Tuple grows too large | Function takes too many sources, hard to read | Introduce a unified event model or split pipelines |

### 17.1. Debugging Sequence

1. Verify the function's generic types.
2. Confirm the tuple holds the right number of publishers.
3. Invoke the function directly with `Tuples.of(...)`.
4. Use `StepVerifier` to test each output; for fan-out, subscribe to all branches under test.
5. Verify whether the operator should be `merge`, `zip`, `concat`, or `combineLatest`.
6. Check completion, error, and cancellation behavior of each source.
7. Verify binding names by index.
8. Only then test against the real binder and broker.

## 18. Completion Criteria

| Criterion | Evidence |
| --- | --- |
| Understand Tuples | Distinguish `Tuple2<Flux<A>,Flux<B>>` from `Flux<Tuple2<A,B>>` |
| Multiple inputs | `mergeLabels` accepts two streams via a tuple |
| Positional pairing | `zipQuantitiesAndPrices` pairs items by position |
| Multiple outputs | `splitParity` returns two streams via a tuple |
| Tuple3 | `mergeThreeSources` processes three inputs |
| Reactive semantics | Explain `merge`/`zip`/`concat`/`combineLatest` |
| Subscriptions | Fan-out test subscribes to both branches concurrently |
| Catalog | Look up multi-input/output functions via `FunctionCatalog` |
| Bindings | Correctly identify `-in-0`, `-in-1`, `-out-0`, `-out-1` |
| Adapter | Distinguish catalog tests from binder integration tests |

**Summary:** Reactor Tuple supplies arity and type metadata for reactive functions with multiple inputs and outputs. `Tuple2<Flux<A>,Flux<B>>` represents two input streams; `Tuple2<Flux<A>,Flux<B>>` in the return position represents two output streams. Use `merge` to combine independent events, `zip` to pair positionally aligned items, and `publish` to share one source across multiple outputs. Spring Cloud Stream maps each tuple slot to its own binding; adapters and binders still require dedicated tests to verify real transport behavior.

## 19. Self-Check Questions

**Question 1.** What does `Tuple2<Flux<String>,Flux<Integer>>` represent?

**Answer:** A tuple holding two independent publishers: the first emits `String`, and the second emits `Integer`.

**Question 2.** How does `Flux<Tuple2<String,Integer>>` differ from the type above?

**Answer:** It is a single publisher emitting String/Integer pairs, not two separate input streams.

**Question 3.** Why does Spring Cloud Function's function arity support target reactive functions?

**Answer:** The tuple holds actual publishers so the framework sees multiple streams and knows the count and types of input/output bindings. Arity support targets reactive signatures `Function<TupleN<Flux<...>>,TupleN<Flux<...>>>`.

**Question 4.** Does `Flux.merge(a,b)` pair the first item of `a` with the first item of `b`?

**Answer:** No. It merges signals from two sources; it does not form positional pairs.

**Question 5.** When does `zip` complete if one source has fewer elements?

**Answer:** Once that source completes and no element remains to form another pair, `zip` can complete; remaining items in the longer source produce no output.

**Question 6.** Why is `publish().autoConnect(2)` needed in the split example?

**Answer:** So two output subscribers share one upstream subscription; the source connects only after both branches subscribe.

**Question 7.** Which tuple slots correspond to `splitParity-out-0` and `splitParity-out-1`?

**Answer:** `out-0` maps to `getT1()` (even numbers), and `out-1` maps to `getT2()` (odd numbers).

**Question 8.** Does a passing `FunctionCatalog` test prove Kafka has created all required topics?

**Answer:** No. You must test with bindings/binders or a real broker.

**Question 9.** If `orders` and `payments` streams are not in matching order, is `zip` safe to use?

**Answer:** No. `zip` pairs by position; you need a key-based join such as by `orderId` or a state/window strategy.

## References

- [Spring Cloud Function — Programming Model and Function Arity](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Stream — Multiple Input and Output Arguments](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream.html)
- [Spring Cloud Stream — Functional Binding Names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Project Reactor — Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)
- [Project Reactor — Tuple2 API](https://projectreactor.io/docs/core/release/api/reactor/util/function/Tuple2.html)
- [Project Reactor — Tuples factory API](https://projectreactor.io/docs/core/release/api/reactor/util/function/Tuples.html)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
