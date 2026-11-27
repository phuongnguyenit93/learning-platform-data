# Composing Imperative Functions with Reactive Functions

## 1. Introduction

Spring Cloud Function helps you develop reusable business logic with `Supplier`, `Function`, and `Consumer`, independent of invocation via HTTP, events, or serverless environments. When building pipelines, sometimes one step processes individual values in a synchronous Java (**imperative**) style, while another step processes an asynchronous data stream using Reactor (**reactive**).

For example, an application already has a function that normalizes product codes:

~~~java
Function<String, String> normalizeSku =
        sku -> sku.trim().toUpperCase(Locale.ROOT);
~~~

A new feature needs to process a stream of codes:

~~~java
Function<Flux<String>, Flux<Integer>> measureLengths =
        flux -> flux.map(String::length);
~~~

If you simply connect the two functions with `andThen`, the type contracts will not match: `String` is not `Flux<String>`. However, Spring Cloud Function and Reactor provide mechanisms to reuse existing logic within a reactive pipeline.

This lesson belongs to the **Function Composition** chapter and focuses on:

- Recognizing the difference between an imperative `Function` and a `Function` accepting/returning `Mono` or `Flux`.
- Understanding why direct composition with Java generics can be invalid.
- Using `map` or `flatMap` to create an explicit reactive bridge.
- Understanding the role of `FunctionCatalog.lookup` and `spring.cloud.function.definition`.
- Analyzing subscriptions, backpressure, element ordering, errors, and blocking risks.
- Writing JUnit 5 tests with `StepVerifier`.

> **Version note:** Spring Cloud Function has composition and adaptation mechanisms when looking up functions through the catalog. The level of automatic composition support between imperative and reactive functions may depend on the version and adapter. This lesson favors **explicit bridges** so Java types stay clear and easy to test; implicit mixed-composition variants must be verified on the actual runtime.

## 2. Contract of an Imperative Function

A standard `Function<T,R>` takes one value of type `T` and returns one value of type `R` via `apply`:

~~~java
import java.util.Locale;
import java.util.function.Function;

Function<String, String> normalize =
        input -> input.trim().toUpperCase(Locale.ROOT);

System.out.println(normalize.apply(" sku-42 "));
// SKU-42
~~~

In this example, processing occurs immediately when `apply` is called and returns a `String`. Such a `Function` is easy to unit-test and reuse in a single request or processing step.

However, the `Function<T,R>` signature **does not guarantee** that the implementation is always non-blocking: it could run JDBC queries, make synchronous API calls, or perform CPU-heavy work. Whether it is synchronous or blocking must be evaluated based on what the implementation actually does.

## 3. Contract of a Reactive Function

Reactor provides `Mono<T>` and `Flux<T>`, the `Publisher` types commonly used in the Spring ecosystem.

- `Mono<T>` represents 0 or 1 element, or an error signal.
- `Flux<T>` represents 0 to many elements, or an error signal.
- Both provide operators such as `map`, `filter`, and `flatMap` to build data streams declaratively.

Example:

~~~java
import java.util.function.Function;
import reactor.core.publisher.Flux;

Function<Flux<String>, Flux<Integer>> lengths =
        flux -> flux
                .map(String::trim)
                .map(String::length);
~~~

The contract is `Flux<String> → Flux<Integer>`. Do not confuse it with `Function<String,Integer>`.

| Interface/contract | Input of `apply` | Output of `apply` |
|---|---|---|
| `Function<String,Integer>` | One `String` | One `Integer` |
| `Function<Mono<String>,Mono<Integer>>` | One `Mono<String>` | One `Mono<Integer>` |
| `Function<Flux<String>,Flux<Integer>>` | One `Flux<String>` | One `Flux<Integer>` |

### 3.1. Calling apply May Only Build the Publisher

~~~java
Flux<Integer> result =
        lengths.apply(Flux.just("  ab ", " cde "));
~~~

When using lazy Reactor operators such as `map`, per-element transformation usually happens **upon subscription**, not necessarily right when `apply` is invoked.

To test in a synchronous program:

~~~java
import java.util.List;

List<Integer> values = result.collectList().block();
System.out.println(values); // [2, 3]
~~~

`block()` is used here for demonstration in a standalone program/test; never block a reactive thread serving requests or events.

## 4. Why Can't You Use andThen Directly?

Suppose:

~~~java
Function<String, String> normalize = String::trim;

Function<Flux<String>, Flux<Integer>> measure =
        flux -> flux.map(String::length);
~~~

The following Java composition does not compile:

~~~java
// Invalid: normalize returns String,
// while measure expects Flux<String>.
// var invalid = normalize.andThen(measure);
~~~

`Function.andThen` is only valid when the output type of the preceding function can be passed as the input of the next function.

~~~text
normalize:  String       → String
measure:   Flux<String> → Flux<Integer>

String differs from Flux<String> → incompatible connection point.
~~~

Reversing the order does not solve it either:

~~~java
Function<Integer, String> describe =
        value -> "length=" + value;

// Invalid: measure returns Flux<Integer>,
// while describe takes Integer.
// var invalid = measure.andThen(describe);
~~~

**Do not use raw types, cast to `Object`, or cast arbitrarily** to bypass generic checks. Instead, lift the imperative function to operate on each element inside `Mono`/`Flux`.

## 5. Lifting an Imperative Function to Flux with map

Given:

~~~java
import java.util.Locale;

Function<String, String> normalize =
        sku -> sku.trim().toUpperCase(Locale.ROOT);
~~~

Create a `Function` with a reactive contract:

~~~java
Function<Flux<String>, Flux<String>> normalizeStream =
        flux -> flux.map(normalize);
~~~

Then chain it with another reactive `Function`:

~~~java
Function<Flux<String>, Flux<Integer>> measureStream =
        flux -> flux.map(String::length);

Function<Flux<String>, Flux<Integer>> pipeline =
        normalizeStream.andThen(measureStream);
~~~

Diagram:

~~~text
Flux<String>               Flux<String>          Flux<Integer>
" sku-42 " --normalizeStream--> "SKU-42" --measureStream--> 6
" sku-7 "  --normalizeStream--> "SKU-7"  --measureStream--> 5
~~~

A quick run:

~~~java
List<Integer> values = pipeline
        .apply(Flux.just(" sku-42 ", " sku-7 "))
        .collectList()
        .block();

System.out.println(values); // [6, 5]
~~~

`Flux.map` applies a `Function<T,R>` to each element while preserving the stream structure. This is the natural bridge for **fast, non-blocking** synchronous transformations.

### 5.1. Creating a Generic liftFlux Helper

~~~java
import java.util.function.Function;
import reactor.core.publisher.Flux;

public final class ReactiveAdapters {

    private ReactiveAdapters() {}

    public static <T, R> Function<Flux<T>, Flux<R>> liftFlux(
            Function<? super T, ? extends R> mapper) {

        return flux -> flux.map(mapper);
    }
}
~~~

Using the helper:

~~~java
Function<String, String> trim = String::trim;
Function<String, Integer> count = String::length;

Function<Flux<String>, Flux<String>> trimFlux =
        ReactiveAdapters.liftFlux(trim);

Function<Flux<String>, Flux<Integer>> countFlux =
        ReactiveAdapters.liftFlux(count);

Function<Flux<String>, Flux<Integer>> pipeline =
        trimFlux.andThen(countFlux);
~~~

No step needs to cast `Flux` to `String`. The Java compiler verifies the full contract from `Flux<String>` to `Flux<Integer>`.

### 5.2. Where Is the Imperative Logic Used?

The `trim` function can still be called independently:

~~~java
String single = trim.apply("  abc  "); // "abc"
~~~

The `trimFlux` function reuses that exact same rule across many elements. The benefit is **no duplicated business logic**, while the pipeline still clearly expresses reactive stream processing.

## 6. When the Reactive Function Precedes the Imperative Function

Example:

~~~java
Function<Flux<String>, Flux<String>> sanitize =
        flux -> flux.map(String::trim)
                    .filter(text -> !text.isBlank());

Function<String, Integer> lengthOne =
        String::length;
~~~

Writing `sanitize.andThen(lengthOne)` fails type checking because `sanitize` returns `Flux<String>`, while `lengthOne` accepts `String`.

Fix it by creating a bridge at the **downstream step**:

~~~java
Function<Flux<String>, Flux<Integer>> lengthStream =
        flux -> flux.map(lengthOne);

Function<Flux<String>, Flux<Integer>> pipeline =
        sanitize.andThen(lengthStream);
~~~

General formula:

~~~text
Reactive first: Function<Flux<A>, Flux<B>>
Imperative after: Function<B, C>

Bridge after:    Function<Flux<B>, Flux<C>>
Result:          Function<Flux<A>, Flux<C>>
~~~

Whether the imperative function comes first or second, the connection point must always match the **entire type**.

## 7. Spring Cloud Function Example: Processing SKU Codes

Suppose the system receives a stream of product codes and needs to:

1. Normalize each code using imperative Java.
2. Validate the code as a reactive stream.
3. Format the result into strings for downstream recipients.

A clear pipeline:

~~~text
Flux<String>
     |
     v
normalizeSkuStream   Flux<String> → Flux<String>
     |
     v
validateSkuStream    Flux<String> → Flux<Sku>
     |
     v
formatSkuStream      Flux<Sku> → Flux<String>
     |
     v
Flux<String>
~~~

### 7.1. Declaring the Beans

Java 17+ example:

~~~java
package example.functions;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;

@Configuration
public class SkuFunctions {

    public record Sku(String code) {}

    // Imperative business function remains independently reusable.
    @Bean
    public Function<String, String> normalizeSku() {
        return sku -> sku.trim().toUpperCase(Locale.ROOT);
    }

    // Bridge: applies normalizeSku to each Flux element.
    @Bean
    public Function<Flux<String>, Flux<String>> normalizeSkuStream(
            @Qualifier("normalizeSku")
            Function<String, String> normalizeSku) {

        return flux -> flux.map(normalizeSku);
    }

    @Bean
    public Function<Flux<String>, Flux<Sku>> validateSkuStream() {
        return flux -> flux.map(code -> {
            if (!code.matches("SKU-[0-9]+")) {
                throw new IllegalArgumentException(
                        "Invalid SKU code: " + code);
            }
            return new Sku(code);
        });
    }

    @Bean
    public Function<Flux<Sku>, Flux<String>> formatSkuStream() {
        return flux -> flux.map(
                sku -> "accepted:" + sku.code());
    }
}
~~~

The default bean names are `normalizeSku`, `normalizeSkuStream`, `validateSkuStream`, and `formatSkuStream`. In Spring Cloud Function, these `Function` beans can be registered in `FunctionCatalog`, provided the application is configured and component-scanned properly.

| Bean | Type | Role |
|---|---|---|
| `normalizeSku` | `String → String` | Reusable imperative rule |
| `normalizeSkuStream` | `Flux<String> → Flux<String>` | `map` bridge |
| `validateSkuStream` | `Flux<String> → Flux<Sku>` | Validates and builds record |
| `formatSkuStream` | `Flux<Sku> → Flux<String>` | Prepares output |

These beans contain no endpoint names, broker topics, or serverless handlers.

### 7.2. Looking Up Composition with FunctionCatalog

~~~java
package example.functions;

import java.util.function.Function;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;

@Service
public class SkuPipelineService {

    private final FunctionCatalog catalog;

    public SkuPipelineService(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    public Flux<String> process(Flux<String> input) {
        Function<Flux<String>, Flux<String>> pipeline =
                catalog.lookup(
                    "normalizeSkuStream|validateSkuStream|formatSkuStream");

        if (pipeline == null) {
            throw new IllegalStateException(
                    "SKU pipeline not found");
        }

        return pipeline.apply(input);
    }
}
~~~

If `Flux.just(" sku-42 ", " sku-7 ")` is passed in, the pipeline is expected to emit:

~~~text
accepted:SKU-42
accepted:SKU-7
~~~

Note that calling `process(...)` returns a `Publisher`; it does not automatically push data to a client/broker. The consumer of the `Publisher` or the adapter orchestrates subscription.

### 7.3. Selecting the Pipeline with spring.cloud.function.definition

In `application.yml`:

~~~yaml
spring:
  cloud:
    function:
      definition: "normalizeSkuStream|validateSkuStream|formatSkuStream"
~~~

In `application.properties`:

~~~properties
spring.cloud.function.definition=normalizeSkuStream|validateSkuStream|formatSkuStream
~~~

This property selects the **pipeline name** for integration. It does not automatically create an HTTP endpoint or event bindings. Running over a real transport requires the right adapter, dependencies, payload conversion, and configuration.

## 8. Automatic Mixed Composition in FunctionCatalog: Needs Verification

In some versions/scenarios, Spring Cloud Function supports **adaptation** when composing imperative and reactive functions via `FunctionCatalog`.

Intended example:

~~~text
normalizeSku:      Function<String, String>
validateSkuStream: Function<Flux<String>, Flux<Sku>>

Name expression: "normalizeSku|validateSkuStream"
~~~

Do not deduce from the syntax that the expression above is guaranteed to return `Function<Flux<String>,Flux<Sku>>` across every version/adapter. Wrapper types and adaptation behavior depend on the version, configuration, and invocation context.

**Better control:** register an explicit `normalizeSkuStream` bridge as in section 7 and use `"normalizeSkuStream|validateSkuStream"`. The pipeline then has a consistent `Flux` contract, can be checked by the compiler, and is easy to test.

If a project intentionally relies on automatic adaptation, write integration tests on the real runtime to verify:

- The function is looked up successfully by the catalog.
- Actual inputs/outputs have the right types and element counts.
- The imperative function runs in the right order and the right number of times.
- Exceptions and `onError` signals are handled properly.
- Headers/payloads remain intact if the adapter uses `Message`.

Success with an explicit bridge **does not prove** implicit mixed composition will behave identically.

## 9. Using Mono When There Is Only One Reactive Result

For a source producing at most one element, `Mono<T>` is usually more appropriate than `Flux<T>`.

~~~java
import java.util.function.Function;
import reactor.core.publisher.Mono;

record Order(String id, int quantity) {}
record Receipt(String orderId, long totalVnd) {}

Function<Order, Receipt> priceOne =
        order -> new Receipt(
                order.id(),
                order.quantity() * 125_000L);

Function<Mono<Order>, Mono<Receipt>> priceMono =
        mono -> mono.map(priceOne);
~~~

Contract:

~~~text
Mono<Order> → map(Function<Order,Receipt>) → Mono<Receipt>
~~~

Example:

~~~java
Mono<Receipt> result =
        priceMono.apply(
                Mono.just(new Order("ORD-42", 2)));
~~~

You can verify the result with `StepVerifier`, or with `block()` in a synchronous test environment. Never block inside a WebFlux chain serving requests.

### 9.1. Distinguishing map and flatMap

When a `Function` returns a **plain value** `Receipt`, use `map`.

When a `Function` returns `Mono<Receipt>`:

~~~java
Function<Order, Mono<Receipt>> priceAsync =
        order -> Mono.just(new Receipt(
                order.id(),
                order.quantity() * 125_000L));
~~~

then `flatMap` is required if you want the final output to remain `Mono<Receipt>`:

~~~java
Function<Mono<Order>, Mono<Receipt>> pricePipeline =
        mono -> mono.flatMap(priceAsync);
~~~

If you use `mono.map(priceAsync)`, the output type becomes `Mono<Mono<Receipt>>`. This is a common mistake when mixing code that returns plain values with code that returns a `Publisher`.

### 9.2. Null Is Not the Same as an Empty Stream

`Mono.just(null)` is invalid. When a value might be `null`, you can use `Mono.justOrEmpty(value)` to represent 0 or 1 element.

~~~java
String maybeMissing = null;
Mono<String> value = Mono.justOrEmpty(maybeMissing);
~~~

However, a `Mono.empty()` does not automatically guarantee that every HTTP/message adapter will translate it to the same status code or "no message emitted" behavior. Test at the real boundary.

## 10. Exceptions: Inside apply Directly or as onError?

### 10.1. An Imperative Function Can Throw Directly

~~~java
Function<String, Integer> parse = Integer::parseInt;

// parse.apply("bad") throws NumberFormatException immediately.
~~~

Lifting that `Function` into `Flux`:

~~~java
Function<Flux<String>, Flux<Integer>> parseAll =
        flux -> flux.map(Integer::parseInt);

Flux<Integer> numbers =
        parseAll.apply(Flux.just("10", "bad", "30"));
~~~

When the subscriber requests data, `10` is emitted, `"bad"` causes `NumberFormatException`, and Reactor turns the mapper exception into an `onError` signal. The stream terminates by default, so `30` is not emitted.

### 10.2. try/catch Outside apply May Not Catch Per-Element Errors

~~~java
try {
    Flux<Integer> values =
            parseAll.apply(Flux.just("bad"));
    // Only creates Publisher; mapper may not have run yet.
} catch (NumberFormatException ex) {
    // Not guaranteed to catch errors occurring at subscribe time.
}
~~~

Use Reactor operators or verify the error signal:

~~~java
Flux<Integer> safe =
        parseAll.apply(Flux.just("10", "bad", "30"))
                .onErrorResume(ex -> Flux.just(-1));
~~~

In this example, the output is `10` then `-1`. `onErrorResume` replaces **the remainder of the stream after the error** with a fallback; it does not resume processing `"30"`.

### 10.3. When a Function Throws While Constructing the Publisher

~~~java
Function<Flux<String>, Flux<String>> brokenFactory = flux -> {
    throw new IllegalStateException("Failed to create Flux");
};
~~~

The exception here occurs immediately inside `brokenFactory.apply(...)`. That differs from an error arising inside `map` during subscription. When designing retry policies, do not assume every failure occurs on the same channel.

## 11. Blocking I/O Remains Blocking Even Inside Reactive map

A simple `Function` like string normalization typically fits inside `map`. A `Function` executing blocking JDBC calls is a different case:

~~~java
// Conceptual code: repository is an application-provided dependency.
Function<String, Customer> loadCustomerBlocking =
        id -> repository.loadById(id);
~~~

`Customer` and `repository` in this example are domain types/dependencies that must be declared in real code.

Putting `loadCustomerBlocking` inside `flux.map(...)` **does not turn a blocking query into a non-blocking one**. If executed on an event-loop thread, blocking operations can stall many requests.

One way to isolate blocking calls in Reactor is:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Function<String, Mono<Customer>> loadCustomer =
        id -> Mono.fromCallable(
                    () -> loadCustomerBlocking.apply(id))
                .subscribeOn(Schedulers.boundedElastic());
~~~

For multiple IDs:

~~~java
Function<Flux<String>, Flux<Customer>> loadAll =
        flux -> flux.flatMap(loadCustomer);
~~~

This is a thread-management solution for blocking I/O; it does not make the database client itself reactive. You still need appropriate concurrency limits, connection pool management, timeouts, and retries.

## 12. Element Ordering in Reactive Pipelines

The `|` symbol defines the order of **Function steps**, not a default guarantee of **output element ordering** during asynchronous processing.

~~~text
Step A | Step B  = A produces data for B

Elements 1, 2, 3 may be processed concurrently if flatMap is used.
~~~

- Synchronous `map` normally preserves element order for ordered sources.
- `flatMap` may run multiple inner `Publisher` instances concurrently and interleave emitted results.
- `concatMap` processes each inner `Publisher` sequentially without running inner publishers concurrently.
- `flatMapSequential` can process concurrently while emitting results in source order, at the cost of buffering.

If business logic requires transactions to be processed in order, operator choice and concurrency policy matter just as much as the order of function names.

### 12.1. Backpressure and Slow Streams

Reactive Streams allow a subscriber to signal demand. However, do not treat backpressure as an automatic cure-all for every external data source. Binders or adapters may have their own buffering, polling, message-acknowledgment, or error policies.

Questions to verify include:

1. If the consumer processes slowly, can the source actually slow down?
2. If data is buffered, what are the buffer limits and overflow policy?
3. When one element fails, does the whole stream stop or is each element handled individually?
4. Are multiple concurrent I/O operations allowed?
5. What happens when a subscription is canceled?

## 13. Composing with Message and Headers

In event-driven systems, `Message<T>` carries payload and headers. A function accepting `Flux<Message<String>>` has a different contract from one accepting `Flux<String>`.

~~~text
Function<String, String>
Function<Flux<Message<String>>, Flux<Message<String>>>
~~~

When you need to reuse an imperative `Function` for each payload, you can write an explicit bridge:

~~~java
import java.util.function.Function;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import reactor.core.publisher.Flux;

Function<String, String> normalize = String::trim;

Function<Flux<Message<String>>,
         Flux<Message<String>>> normalizeMessages =
        flux -> flux.map(message ->
                MessageBuilder
                        .withPayload(
                                normalize.apply(message.getPayload()))
                        .copyHeaders(message.getHeaders())
                        .build());
~~~

This code explicitly copies headers into the new `Message`. It does not guarantee every transport header is preserved or retains the same meaning when adapters change. With HTTP, Spring Cloud Stream, and serverless, test payloads, content-type, correlation IDs, and data conversion errors.

**Do not** treat Spring Cloud Function's message conversion capabilities as a reason to ignore generic contracts or assume every JSON/POJO conversion happens automatically.

## 14. Deploying the Same Logic via HTTP, Events, and Serverless

The pipeline `normalizeSkuStream|validateSkuStream|formatSkuStream` only describes processing logic. How it connects to the outside world is determined by the adapter:

| Environment | Needed beyond function beans | What to test |
|---|---|---|
| Internal Java | Spring context or direct Functions | Subscription, generics, order, errors |
| HTTP | Web adapter and route/request mapping | Body, reactive response, error status |
| Events/messaging | Binder, bindings, destination, and converters | Headers, serialization, retry/ack |
| Serverless | Adapter/handler and trigger configuration | Event mapping, errors, cold start |

`spring.cloud.function.definition` selects the **pipeline by name**; it does not automatically create an HTTP endpoint or configure a broker.

### 14.1. When Is Reactive Not Needed?

If business logic simply computes one `Order` into one `Quote` with no streams or asynchronous I/O, `Function<Order,Quote>` is usually simpler. Do not convert every step to `Flux` merely to "match the style" of an adapter.

Use `map` as a bridge when you need to reuse per-value logic inside a reactive pipeline; use genuinely reactive `Function` beans when the domain needs `Publisher` handling, combining multiple sources, backpressure, or asynchronous operations.

## 15. Testing Reactive Java Pipelines with StepVerifier

### 15.1. Unit Test for Bridge and Ordering

~~~java
import java.util.function.Function;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class MixedCompositionTest {

    @Test
    void imperativeMapperRunsForEachElement() {
        Function<String, String> trim = String::trim;

        Function<Flux<String>, Flux<String>> trimStream =
                flux -> flux.map(trim);

        Function<Flux<String>, Flux<Integer>> lengths =
                flux -> flux.map(String::length);

        Function<Flux<String>, Flux<Integer>> pipeline =
                trimStream.andThen(lengths);

        StepVerifier.create(
                pipeline.apply(Flux.just("  ab ", " cde ")))
                .expectNext(2, 3)
                .verifyComplete();
    }
}
~~~

This test verifies both element values and ordering. `verifyComplete` ensures the stream terminates normally.

### 15.2. Unit Test for Error Signals

~~~java
import java.util.function.Function;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class ReactiveErrorTest {

    @Test
    void parseErrorIsPublishedDuringSubscription() {
        Function<Flux<String>, Flux<Integer>> parseAll =
                flux -> flux.map(Integer::parseInt);

        Flux<Integer> result =
                parseAll.apply(Flux.just("10", "bad", "30"));

        StepVerifier.create(result)
                .expectNext(10)
                .expectError(NumberFormatException.class)
                .verify();
    }
}
~~~

The test checks not just that `apply` runs, but also confirms that the error actually surfaces when the subscriber processes the data.

## 16. Integration Testing via FunctionCatalog

A Spring Boot application placed in the same `example.functions` package as `SkuFunctions`:

~~~java
package example.functions;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SkuApplication {

    public static void main(String[] args) {
        SpringApplication.run(SkuApplication.class, args);
    }
}
~~~

Testing bean lookup by name:

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@SpringBootTest(classes = SkuApplication.class)
class SkuCompositionCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void namedPipelineTransformsFlux() {
        Function<Flux<String>, Flux<String>> pipeline =
                catalog.lookup(
                    "normalizeSkuStream|validateSkuStream|formatSkuStream");

        assertNotNull(pipeline);

        StepVerifier.create(
                pipeline.apply(Flux.just(" sku-42 ", " sku-7 ")))
                .expectNext(
                        "accepted:SKU-42",
                        "accepted:SKU-7")
                .verifyComplete();
    }

    @Test
    void invalidSkuTerminatesWithError() {
        Function<Flux<String>, Flux<String>> pipeline =
                catalog.lookup(
                    "normalizeSkuStream|validateSkuStream|formatSkuStream");

        assertNotNull(pipeline);

        StepVerifier.create(
                pipeline.apply(Flux.just(" sku-42 ", "bad")))
                .expectNext("accepted:SKU-42")
                .expectError(IllegalArgumentException.class)
                .verify();
    }
}
~~~

This test requires Spring Cloud Function context, Spring Boot Test, and `reactor-test` compatible with your project version. It verifies **bean names**, **type contracts**, **composition order**, and **reactive errors** inside Spring.

If HTTP/message adapters use separate wrappers/converters, add an integration test layer at the adapter boundary instead of assuming catalog tests prove the entire system works.

## 17. Common Mistakes

| Symptom | Possible cause | How to fix |
|---|---|---|
| `andThen` fails to compile | `T` differs from `Flux<T>` or `Mono<T>` | Lift the `Function` using `map` |
| Result is `Mono<Mono<R>>` | Using `map` with a mapper returning `Mono` | Use `flatMap` to flatten |
| No elements are processed | `Publisher` has no subscription yet | Use `StepVerifier` or inspect adapter |
| `try/catch` around `apply` misses errors | Mapper errors emit as `onError` | Inspect error signals |
| Event loop blocked | Blocking I/O placed inside `map` | Isolate blocking calls or use reactive client |
| Out-of-order results | `flatMap` runs concurrently | Consider `concatMap`/`flatMapSequential` |
| `lookup` succeeds, adapter fails | Wrong converter, wrapper, or binding | Test real input/output |
| Headers lost or unexpected | Conversion between `Message` and payload | Design explicit header preservation |
| No HTTP endpoint or messages | Only `definition` was configured | Add adapter, routes/bindings, and config |
| Implicit pipeline breaks on upgrade | Automatic adaptation changed | Use integration tests or explicit bridges |

Avoid using raw types, `Object`, or `block()` as quick patches for type errors. They obscure design flaws or break the reactive nature of the application.

## 18. Practice Exercises

**Exercise 1 — Basic Bridge.** Given `Function<String,String> normalize` and `Function<Flux<String>,Flux<Integer>> countStream`, why does `normalize.andThen(countStream)` not compile? Write `normalizeFlux` to compose them validly.

**Exercise 2 — Reactive First, Imperative Second.** Given `cleanStream: Function<Flux<String>,Flux<String>>` and `parseOne: Function<String,Integer>`, build `parseStream` and chain it after `cleanStream`.

**Exercise 3 — Nested Mono.** Given `findCustomer: Function<String,Mono<Customer>>`, if you use `mono.map(findCustomer)` on a `Mono<String>`, what is the resulting type? Which operator yields `Mono<Customer>`?

**Exercise 4 — Error on Subscribe.** Given `Flux.just("3","bad","5").map(Integer::parseInt)`, when is the error emitted? Write a `StepVerifier` test verifying `3` is emitted followed by `NumberFormatException`.

**Exercise 5 — Event Ordering.** A pipeline uses `flatMap` to call an asynchronous API for each input. If business logic requires results in source order, choose another operator and state the trade-off.

**Exercise 6 — Blocking.** A `Function` using blocking JDBC is placed inside `Flux.map`. Why does this risk slowing down the application? Name one technique to deliberately isolate blocking work.

**Exercise 7 — Spring Configuration.** Write `spring.cloud.function.definition` for the chain `normalizeSkuStream|validateSkuStream|formatSkuStream`. Why is that configuration alone not enough to receive Kafka messages?

**Exercise 8 — Testing Mixed Composition.** If a project wants to compose `normalizeSku|validateSkuStream` directly instead of using an explicit bridge, what should be verified before deploying?

### Solution Hints

- **Exercise 1:** `Function<Flux<String>,Flux<String>> normalizeFlux = flux -> flux.map(normalize);`; then `normalizeFlux.andThen(countStream)`.
- **Exercise 2:** `Function<Flux<String>,Flux<Integer>> parseStream = flux -> flux.map(parseOne);`.
- **Exercise 3:** `Mono<Mono<Customer>>` if using `map`; use `flatMap` to obtain `Mono<Customer>`.
- **Exercise 4:** Error emits upon subscription; use `expectNext(3).expectError(NumberFormatException.class).verify()`.
- **Exercise 5:** `concatMap` processes sequentially; `flatMapSequential` allows concurrency while preserving emission order.
- **Exercise 6:** Blocking stalls processing threads; you can use `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` and limit concurrency.
- **Exercise 7:** That property only selects the function; you need a Kafka binder, bindings/destinations, converters, and error policies.
- **Exercise 8:** Actual wrapper types, mapper invocation count, subscription behavior, ordering, errors, headers, and adapter behavior on that specific version.

## 19. Key Takeaways

- `Function<T,R>` processes a single value; `Function<Flux<T>,Flux<R>>` or `Function<Mono<T>,Mono<R>>` processes a `Publisher` and typically executes upon subscription.
- Java `andThen` only connects when **the entire output type** matches **the entire input type**; `T` is not identical to `Flux<T>`.
- Use `flux.map(imperativeFunction)` or `mono.map(imperativeFunction)` to lift per-element synchronous transformations onto a clear reactive contract.
- Use `flatMap` when a mapper returns a `Publisher` that needs flattening; watch ordering, concurrency, and backpressure.
- Spring Cloud Function provides `FunctionCatalog` and composition, but automatic adaptation between imperative and reactive forms must be verified per version and adapter.
- Do not place blocking I/O into a reactive stream without an appropriate scheduler/client strategy.
- `spring.cloud.function.definition` selects logic; it does not replace HTTP, event, or serverless adapter configuration, nor does it replace testing subscriptions, error signals, and `Message` conversion.
