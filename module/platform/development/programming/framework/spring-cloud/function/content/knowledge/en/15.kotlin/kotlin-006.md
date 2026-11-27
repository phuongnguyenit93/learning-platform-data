# Using Mono or Flux from Kotlin Functions

## 1. Why Does Spring Cloud Function Pair Well with Reactor?

**Spring Cloud Function** (the `SPRING_CLOUD_FUNCTION` module) lets you organize business logic into `Supplier`, `Function`, and `Consumer` beans. These functions are managed by `FunctionCatalog` for lookup, message conversion, composition, and deployment with adapters such as HTTP, Spring Cloud Stream, or serverless environments. The core idea is that **a function contract is not tightly coupled to how it is invoked**.

When handling asynchronous data, a function can return a **publisher** instead of returning a value immediately. Spring Cloud Function supports two Project Reactor types:

- `Mono<T>`: a publisher emitting **0 or 1** value of type `T`, then completing; or terminating with an error.
- `Flux<T>`: a publisher emitting **0 to many** values of type `T`, either finite or long-lived; or terminating with an error.

Example in Kotlin:

~~~kotlin
val one: Mono<String> = Mono.just("O-101")
val many: Flux<String> = Flux.just("O-101", "O-102", "O-103")
~~~

The crucial point is that `Mono` and `Flux` **are not the `String` or `List` values themselves**. They describe a signal-emitting pipeline once there is a **subscriber**.

~~~text
Kotlin function bean
      |
      v
Function<Flux<Order>, Flux<Decision>>
      |
      +---- source Publisher<Order>
      |          |
      |          v
      |     map/filter/flatMap...
      |          |
      +---- target Publisher<Decision>
                 |
          adapter subscribes
                 |
          only then does data flow
~~~

This guide focuses on: how to declare reactive functional beans in Kotlin, distinguishing `Mono`/`Flux`, handling nulls and errors, differences between HTTP and messaging invocation, subscription/backpressure, and testing with `StepVerifier`.

## 2. Mono and Flux: Return Types Different from Collections

| Characteristic | `Mono<T>` | `Flux<T>` |
| --- | --- | --- |
| Number of `onNext` signals | 0 or 1 | 0 to N |
| Can complete with no value? | Yes, `Mono.empty()` | Yes, `Flux.empty()` |
| Can run continuously? | Waits long for a result, but at most 1 value | Can be unbounded |
| Examples | Look up a single order, verify access rights | Order event stream, search result stream |
| Typical operators | `map`, `flatMap`, `switchIfEmpty`, `then` | `map`, `filter`, `flatMap`, `concatMap`, `buffer` |
| Is it a `List`? | No | No |

A `Mono<List<Order>>` emits **one list**; a `Flux<Order>` emits **individual `Order` objects**. Both models can represent the same data, yet carry different contracts:

~~~kotlin
val batch: Mono<List<String>> =
    Mono.just(listOf("A", "B", "C"))

val events: Flux<String> =
    Flux.fromIterable(listOf("A", "B", "C"))
~~~

`batch` emits **one `onNext` containing a three-element `List`**. `events` emits **three `onNext` signals**, each carrying one string. An HTTP response returning a JSON array, a single message carrying an array, and three messages on a broker are not synonymous either; the adapter decides how data is emitted.

### 2.1. Reactive Streams Signals

~~~text
Mono.just("A"):       onSubscribe -> onNext("A") -> onComplete
Mono.empty():         onSubscribe -> onComplete
Mono.error(error):    onSubscribe -> onError(error)

Flux.just("A","B"):   onSubscribe -> onNext("A")
                                    -> onNext("B") -> onComplete
Flux.never():         onSubscribe -> ... never completes
~~~

`onComplete` and `onError` are **mutually exclusive** terminal signals within a subscription. Reactor does not emit `null` elements via `onNext`.

## 3. Preparing Dependencies for a Kotlin Application

The following `build.gradle.kts` snippet highlights the required parts, assuming the project already manages Spring Boot, Spring Cloud Function, and Kotlin versions with compatible plugins/BOMs:

~~~kotlin
plugins {
    kotlin("jvm")
    kotlin("plugin.spring")
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    implementation("org.springframework.cloud:spring-cloud-function-context")

    implementation(kotlin("stdlib"))
    implementation(kotlin("reflect"))

    // reactor-core typically comes from the Spring Cloud Function/Spring stack;
    // only declare directly when explicit dependency control is needed.
    implementation("io.projectreactor:reactor-core")
    testImplementation("io.projectreactor:reactor-test")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

This is not a complete standalone build script. `kotlin("plugin.spring")` helps proxy Spring classes in Kotlin (which are `final` by default); `kotlin-stdlib` provides the Kotlin runtime, while `reactor-core` provides `Mono`, `Flux`, and operators. When JSON support for Kotlin `data class` types is needed, add the Jackson Kotlin module matching your Spring Boot/Jackson version; when using messaging, add **Spring Cloud Stream and the corresponding binder**.

### 3.1. Reactor Kotlin Extensions Is Optional

Reactor's Java methods are **directly usable from Kotlin**. If you prefer shorter Kotlin syntax, Reactor provides an optional module:

~~~kotlin
dependencies {
    implementation("io.projectreactor.kotlin:reactor-kotlin-extensions")
}
~~~

Example:

~~~kotlin
import reactor.core.publisher.Flux
import reactor.kotlin.core.publisher.toFlux

val withoutExtensions: Flux<Int> =
    Flux.fromIterable(listOf(1, 2, 3))

val withExtensions: Flux<Int> =
    listOf(1, 2, 3).toFlux()
~~~

`toFlux()` is only available with the extension dependency and import. Reactor Kotlin Extensions is not required to declare `Function<Flux<I>, Flux<O>>`.

## 4. Complete Example: Kotlin Functions with Mono and Flux

Suppose an order classification system treats orders of 1,000,000 VND or more as `PRIORITY`, and all others as `STANDARD`. The business rule is written independently of transport protocols:

~~~kotlin
package example.reactive

import java.util.function.Function
import org.springframework.boot.autoconfigure.SpringBootApplication
import org.springframework.boot.runApplication
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import reactor.core.publisher.Flux
import reactor.core.publisher.Mono

data class Order(
    val id: String,
    val totalVnd: Long
)

data class Decision(
    val orderId: String,
    val category: String
)

fun decide(order: Order): Decision {
    require(order.id.isNotBlank()) { "id must not be blank" }
    require(order.totalVnd >= 0L) { "totalVnd must not be negative" }
    return Decision(
        orderId = order.id,
        category = if (order.totalVnd >= 1_000_000L)
            "PRIORITY" else "STANDARD"
    )
}

@SpringBootApplication
class ReactiveOrdersApplication

fun main(args: Array<String>) {
    runApplication<ReactiveOrdersApplication>(*args)
}

@Configuration
class ReactiveOrderFunctions {

    // One input value, one asynchronous result.
    @Bean
    fun classifyOne(): Function<Order, Mono<Decision>> =
        Function { order ->
            Mono.fromSupplier { decide(order) }
        }

    // One input Flux, one output Flux: event pipeline.
    @Bean
    fun classifyStream(): Function<Flux<Order>, Flux<Decision>> =
        Function { orders ->
            orders.map { order -> decide(order) }
        }
}
~~~

`decide` is a regular Kotlin function and can be unit tested on its own. The two functional beans differ only in **how incoming/outgoing data is represented**:

| Bean | Signature | Processing Unit |
| --- | --- | --- |
| `classifyOne` | `Function<Order, Mono<Decision>>` | A single `Order` is transformed into an asynchronous result with at most one value |
| `classifyStream` | `Function<Flux<Order>, Flux<Decision>>` | A publisher of orders is transformed into a publisher of decisions |

**Do not assume the two beans behave identically across all adapters.** `Function<Order, Mono<Decision>>` is useful when the environment supports a reactive result per invocation (such as a compatible web adapter); `Function<Flux<Order>, Flux<Decision>>` is the common pattern for a stream pipeline bound by Spring Cloud Stream. Each adapter has its own subscription and result contract that must be verified.

### 4.1. Writing the Bean with a Kotlin Function Type Instead of Java `Function`

Spring Cloud Function also recognizes Kotlin lambdas registered as beans:

~~~kotlin
// Place method inside a loaded @Configuration class.
@Bean
fun uppercaseStream(): (Flux<String>) -> Flux<String> = { input ->
    input
        .map { it.trim().uppercase() }
        .filter { it.isNotEmpty() }
}
~~~

The return type `(Flux<String>) -> Flux<String>` is a Kotlin function type, mapped to the functional bean model once normalized by Spring Cloud Function. When integrating with Java APIs or needing an explicit JVM contract, choosing `java.util.function.Function<Flux<I>, Flux<O>>` is equally appropriate.

## 5. Mono: Present, Absent, or Error Results

`Mono<T>` has three common termination outcomes:

~~~kotlin
import reactor.core.publisher.Mono

val found: Mono<String> = Mono.just("O-101")
val missing: Mono<String> = Mono.empty()
val failed: Mono<String> =
    Mono.error(IllegalArgumentException("Invalid ID"))
~~~

### 5.1. `Mono.just` and `Mono.fromSupplier` Evaluate at Different Times

~~~kotlin
val eager: Mono<Decision> =
    Mono.just(decide(Order("O-101", 500_000L)))

val lazy: Mono<Decision> =
    Mono.fromSupplier {
        decide(Order("O-101", 500_000L))
    }
~~~

`Mono.just(...)` accepts a **precomputed value** at publisher creation time; `Mono.fromSupplier { ... }` defers calling the supplier until subscription time. For functions performing expensive work or capable of throwing, execution timing affects where errors are thrown and the processing lifecycle.

If you need to construct **a fresh publisher per subscription**, you can use `Mono.defer { ... }`:

~~~kotlin
val deferred: Mono<String> = Mono.defer {
    Mono.just("READY")
}
~~~

Not every publisher executes only once automatically: many Reactor publishers are **cold** by default and can re-run their logic for each subscription. Avoid placing important side effects inside a publisher that may be subscribed to repeatedly without an idempotency policy.

### 5.2. Never Emit `null`: Use `Mono.justOrEmpty`

Kotlin allows nullable strings `String?`, but Reactor forbids a `null` element:

~~~kotlin
fun normalizedCode(raw: String?): Mono<String> {
    val value: String? = raw
        ?.trim()
        ?.takeIf { it.isNotEmpty() }

    return Mono.justOrEmpty(value)
}
~~~

Results:

- `normalizedCode("  SAVE10 ")` emits `"SAVE10"` and completes.
- `normalizedCode(null)` completes **without emitting a value**.
- `normalizedCode("   ")` also completes empty because the string has no content.

`Mono.empty()` means **no data in this subscription**, which does not automatically mean HTTP 404, HTTP 204, or an error message. How an adapter represents this must be verified per environment.

### 5.3. Clearly Separate Empty Values from Errors

~~~kotlin
fun lookupOrderId(id: String?): Mono<String> {
    if (id == null) return Mono.empty()
    if (id.isBlank()) {
        return Mono.error(IllegalArgumentException("id must not be blank"))
    }
    return Mono.just(id.trim())
}
~~~

Here we deliberately choose:

- `null` input: no data found.
- Whitespace-only input: validation error.
- Other input: one result.

That is **this example's rule**, not a mandatory Spring Cloud Function convention.

### 5.4. `Mono<Void>` Differs from `Mono<Unit>`

In Kotlin:

~~~kotlin
val hasUnitValue: Mono<Unit> = Mono.just(Unit)
val noPayload: Mono<Void> = Mono.empty()
~~~

`Mono<Unit>` in the first example **actually emits one `Unit` element**. `Mono<Void>` is commonly used in Reactor/Java APIs to represent **completion without data**.

The `then()` operator on a publisher produces a `Mono<Void>`, ignoring upstream elements and emitting only completion/error signals:

~~~kotlin
fun auditAll(orders: Flux<Order>): Mono<Void> =
    orders
        .doOnNext { order -> println("AUDIT: " + order.id) }
        .then()
~~~

**Warning:** if `orders` is an event stream that **never terminates**, `then()` will never emit a normal `onComplete` either. `doOnNext` only illustrates a side effect, not a durable audit mechanism; in production, design storage, error handling, and acknowledgment to fit the environment.

## 6. Flux: Transforming Event Streams in Kotlin

`Flux<T>` is appropriate when a function needs to observe multiple data items or act as a stream processor.

~~~kotlin
val input: Flux<String> =
    Flux.just(" O-101 ", "", " O-102 ")

val output: Flux<String> = input
    .map { value -> value.trim() }
    .filter { value -> value.isNotEmpty() }
    .map { value -> value.uppercase() }
~~~

The result emits two `onNext` values: `"O-101"`, `"O-102"`.

### 6.1. `map`, `filter`, `flatMap`, and `concatMap`

| Operator | Effect | When to Choose |
| --- | --- | --- |
| `map { }` | Synchronous, one element to one element | Converting `Order` to `Decision` |
| `filter { }` | Keeps/drops elements by predicate | Selecting matching messages |
| `flatMap { Mono/Flux }` | Merges inner publishers, may process concurrently | Async I/O, one input producing 0..N outputs |
| `concatMap { Mono/Flux }` | Processes inner publishers sequentially, preserving source order | When business ordering is required |
| `flatMapSequential { }` | Subscribes concurrently while emitting in source order | Balancing concurrency and ordering |
| `buffer(n)` | Batches elements into `List<T>` | Bounded batch processing |
| `take(n)` | Takes at most `n` elements then cancels subscription | Testing, limiting streams |

Example where one order has multiple SKUs and you want to emit each SKU on the same `Flux`:

~~~kotlin
data class OrderWithSkus(
    val id: String,
    val skus: List<String>
)

val extractSkus: (Flux<OrderWithSkus>) -> Flux<String> = { orders ->
    orders.flatMapIterable { order ->
        order.skus.map { sku -> order.id + ":" + sku }
    }
}
~~~

A single `OrderWithSkus` input with three SKUs emits **three elements on the same output publisher**. It does not cause Spring Cloud Stream to create three output bindings automatically.

### 6.2. Ordering and Concurrency

When performing async I/O, `flatMap` can emit results out of source order:

~~~kotlin
import java.time.Duration

val processed: Flux<String> = Flux.just("A", "B")
    .flatMap { value ->
        val wait = if (value == "A")
            Duration.ofMillis(100) else Duration.ofMillis(10)
        Mono.just(value).delayElement(wait)
    }
~~~

Under normal timing this example can emit `B` before `A`. If ordering is a business requirement, use `concatMap` or another suitable operator instead of assuming `flatMap` preserves order.

### 6.3. Cold Publishers and Subscriptions

~~~kotlin
val source = Flux.defer {
    println("New subscriber")
    Flux.just("A", "B")
}
~~~

The logging inside `Flux.defer` executes when subscribed. If subscribed twice, the publisher-creation block can run twice. With a source performing database queries or side effects, repeated subscriptions can increase load or re-execute work.

Declaring a bean in Spring Cloud Function **registers the function**; it does not mean every publisher produced by the function has already been subscribed to. The adapter manages connecting and consuming the publisher according to its own contract.

## 7. Spring Cloud Stream: Reactive Functions Are Set Up Once

In Spring Cloud Stream, there is a major difference between:

~~~kotlin
Function<Order, Decision>

Function<Flux<Order>, Flux<Decision>>
~~~

An **imperative** function is typically called by the framework **for each message**. A **reactive** function is typically called **once to build the pipeline**, after which messages flow through that pipeline.

~~~text
IMPERATIVE
  message A ---> apply(A) ---> decision A
  message B ---> apply(B) ---> decision B

REACTIVE
  input Flux  ---> apply(input Flux) ---> output Flux
                       |
           pipeline connected/subscribed
                       |
             multiple messages flow through
~~~

This is why per-invocation retry/error handling designed for imperative functions **does not automatically** govern individual elements inside a reactive pipeline. The framework/binder must be evaluated under the chosen model.

### 7.1. `application.yml` for `classifyStream`

Assuming the application already has Spring Cloud Stream and a suitable binder configured:

~~~yaml
spring:
  cloud:
    function:
      definition: classifyStream
    stream:
      bindings:
        classifyStream-in-0:
          destination: orders.created
          group: order-classifiers
          content-type: application/json
        classifyStream-out-0:
          destination: orders.classified
          content-type: application/json
~~~

Spring Cloud Stream connects `classifyStream-in-0` to the input topic/queue and `classifyStream-out-0` to the output destination. Spring Cloud Function knows the generic types `Flux<Order>` and `Flux<Decision>`; `content-type` helps determine message formatting.

**No second output binding is created** merely because `Flux<Decision>` emits many elements. Port count is determined by the function signature; the number of messages emitted on a port depends on the data.

If the application has multiple beans (such as `classifyOne` and `classifyStream`), explicitly set `spring.cloud.function.definition` to avoid binding the wrong bean.

### 7.2. Does a `Flux` Provide Backpressure All the Way to the Broker?

**Not by default.** Reactor supports backpressure at the Reactive Streams layer, but end-to-end propagation to sources/sinks depends on the **binder**. With a regular non-reactive binder, the application can still use `map`, `filter`, `flatMap`, etc., but you should not claim end-to-end backpressure.

Check: binder backpressure capabilities, memory limits, concurrency, consumer/producer throughput, retries, DLQs, and how the adapter handles publisher errors. These questions matter far more than simply seeing `Flux` in the signature.

## 8. Web Adapter: A Response Can Carry a Publisher

With a suitable web adapter, a bean can handle an HTTP call and return a `Mono` representing an asynchronous result. For instance, `classifyOne` in section 4 has the contract `Function<Order, Mono<Decision>>`, without directly depending on Spring MVC or WebFlux in business code.

However, distinguish carefully:

| Return Pattern | Business Meaning | What the Adapter Must Decide |
| --- | --- | --- |
| `OrderDecision` | One DTO | JSON and HTTP status code |
| `Mono<OrderDecision>` | At most one async DTO | When to subscribe; serialize when result arrives |
| `Mono.empty<OrderDecision>()` | Completes with no data | HTTP status/response body depending on adapter |
| `Flux<OrderDecision>` | Multiple results | Collect as JSON array or stream/SSE per content negotiation |
| `Mono.error(...)` | Async error | Map exception to response |

Do not assume every HTTP adapter automatically opens an infinite stream or two HTTP endpoints because a function returns a `Flux` or a tuple of `Flux` instances. HTTP has its own request/response model; if complex API behavior is needed, you can write a Spring WebFlux controller delegating to your business service/function.

The same applies to serverless: a single invocation is subject to the platform's timeout, payload, and trigger contract; do not return `Flux.never()` merely because Reactor allows infinite publishers.

## 9. `Supplier<Flux<T>>` and Event Sources

Not every reactive bean is a `Function`. You can declare a **`Supplier`** that takes no input and returns a `Flux`:

~~~kotlin
import java.time.Duration
import java.util.function.Supplier
import org.springframework.context.annotation.Bean
import reactor.core.publisher.Flux

data class Heartbeat(val sequence: Long)

// Place @Bean inside an appropriate @Configuration class.
@Bean
fun heartbeatEvents(): Supplier<Flux<Heartbeat>> =
    Supplier {
        Flux.interval(Duration.ofSeconds(1))
            .map { count -> Heartbeat(count) }
    }
~~~

When used as a stream source in a supporting adapter, a reactive `Supplier<Flux<T>>` is typically invoked to obtain the publisher and then **subscribed to**; for an unbounded source like `Flux.interval`, you should not think of the framework as calling `get()` every second like an imperative poller.

If a reactive supplier returns **a finite `Flux`** and needs to be polled repeatedly, Spring Cloud Function provides the `@PollableBean` annotation to supply **metadata** to the integration framework; the annotation itself does not perform scheduling. When choosing this approach, check your SCF/Stream version, poller mechanism, and what "each poll" means in the actual application.

### 9.1. Why Not Use `Flux.interval` Indiscriminately?

`Flux.interval` is time-driven and creates a continuous emission source. If downstream cannot consume fast enough or a sink/binder fails, you need explicit policies for backpressure, subscription cancellation, and lifecycle. The heartbeat example only teaches how to write the signature; production systems should not treat it as a reliable scheduling mechanism in place of a proper scheduler or managed message source.

## 10. `Consumer<Flux<T>>` and `Mono<Void>`

Reactive consumers have an important limitation: `Consumer<Flux<T>>` (or a Kotlin function returning `Unit`) returns no result publisher for the framework to subscribe to.

~~~kotlin
import java.util.function.Consumer
import reactor.core.publisher.Flux

val riskyConsumer: Consumer<Flux<Order>> =
    Consumer { orders ->
        // Manually subscribing; from here the code owns the lifecycle.
        orders.subscribe { order -> println(order.id) }
    }
~~~

This is an example **to be cautious with**, not a default recommendation. When subscribing manually, errors, stream cancellation, and shutdown can become hard to control, especially in messaging systems.

Spring Cloud Stream recommends considering a function that returns a completion publisher, for example:

~~~kotlin
import java.util.function.Function
import reactor.core.publisher.Flux
import reactor.core.publisher.Mono

val auditStream: Function<Flux<Order>, Mono<Void>> =
    Function { orders ->
        orders
            .doOnNext { order -> println("AUDIT: " + order.id) }
            .then()
    }
~~~

`then()` converts the stream into `Mono<Void>`: it can signal **completion or error** without emitting an output value. If the input `Flux` lives for the entire application lifetime, `Mono<Void>` may **never complete**; this is a property of the stream, not necessarily a bug.

Do not switch to `Mono<Unit>` expecting identical behavior: `Mono.just(Unit)` emits an actual `Unit` element, whereas `Mono<Void>` represents completion with no elements.

## 11. Error Handling: One Bad Element Can Stop the Entire Flux

Consider the `classifyStream` bean:

~~~kotlin
orders.map { order -> decide(order) }
~~~

`decide` calls `require`. If one order has `totalVnd < 0`, the `map` operator emits `onError`. Under Reactive Streams semantics, a terminal error **terminates the subscription**, rather than skipping one record and continuing automatically.

### 11.1. Outer `onErrorResume` Does Not Preserve Subsequent Upstream Elements

~~~kotlin
val recovered: Flux<Decision> =
    orders
        .map { decide(it) }
        .onErrorResume { error ->
            Flux.just(Decision("UNKNOWN", "FAILED"))
        }
~~~

When an error occurs, the upstream chain is cancelled and `onErrorResume` switches to the fallback publisher. It **does not** automatically resume unprocessed messages from the upstream publisher. Do not use this pattern if the requirement is "one record fails, yet all subsequent records keep running".

### 11.2. Handling Errors per Element

You can wrap each order in an inner publisher:

~~~kotlin
import java.util.function.Function
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import reactor.core.publisher.Flux
import reactor.core.publisher.Mono

@Configuration
class SafeOrderFunctions {

    @Bean
    fun classifySafely(): Function<Flux<Order>, Flux<Decision>> =
        Function { orders ->
            orders.concatMap { order ->
                Mono.fromCallable { decide(order) }
                    .onErrorResume(IllegalArgumentException::class.java) {
                        Mono.just(Decision(order.id, "REJECTED"))
                    }
            }
        }
}
~~~

In this example, an `IllegalArgumentException` for one order is converted into `Decision(REJECTED)` inside the **inner publisher**; the outer stream can keep processing other orders. `concatMap` preserves ordering. This is a **specific business policy**: for transient database or downstream failures, retries or a DLQ may be needed instead of returning `REJECTED`.

### 11.3. Retry at the Right Scope

Placing `retryWhen(...)` around the **entire `Flux`** can resubscribe to the source and reprocess already-handled data, causing repeated side effects or duplicate events. When retrying an I/O operation for individual records, prefer applying retry **inside the inner publisher**, with attempt limits, backoff, and idempotency controls.

Spring Cloud Stream's per-message error-handling/retry features for **imperative message handlers** do not automatically apply in the same way to reactive pipelines. Use Reactor operators (`onErrorResume`, `retryWhen`, `doOnError`, etc.) and verify actual binder behavior.

Do not use `onErrorContinue` as a "cure-all for errors" without understanding which operators support it and the risks of data loss or hard-to-trace failures.

## 12. Blocking I/O and Schedulers

**Reactive does not automatically mean non-blocking.** Calling traditional JDBC, synchronous file access, or a blocking HTTP client directly inside `map` can pin a thread for too long.

Conceptual pattern for offloading blocking work to a suitable scheduler:

~~~kotlin
import reactor.core.publisher.Mono
import reactor.core.scheduler.Schedulers

// blockingLookup is a synchronous function from a legacy system.
fun lookupAsync(id: String, blockingLookup: (String) -> String): Mono<String> =
    Mono.fromCallable { blockingLookup(id) }
        .subscribeOn(Schedulers.boundedElastic())
~~~

`Schedulers.boundedElastic()` is a common choice for isolating bounded blocking work; it **does not turn** blocking database access into a true reactive driver. Under high load, bound concurrency and evaluate thread and connection pool resources.

Comparison:

| Execution Approach | Characteristics |
| --- | --- |
| `map { blockingCall() }` | Risks blocking the current signal-processing thread |
| `Mono.fromCallable { blockingCall() }.subscribeOn(boundedElastic())` | Offloads blocking work to an appropriate scheduler |
| Using WebClient/R2DBC/reactive drivers | Leverages non-blocking I/O when the driver truly supports it |

In Kotlin, `suspend fun` and `Flow<T>` belong to the coroutine model and are **not identical** to Reactor `Mono`/`Flux`. You can convert between them with bridge libraries such as `kotlinx-coroutines-reactor` when needed, but you cannot assume every `suspend` function automatically acts as a `Function<I, Mono<O>>` functional bean.

## 13. Testing with StepVerifier

`reactor-test` provides `StepVerifier` to assert `onNext`, `onComplete`, and `onError` signals precisely. This is the proper way to test publisher-returning functions, instead of calling `subscribe()` manually and hoping the test finishes on time.

### 13.1. Unit Tests for `Mono`

~~~kotlin
import org.junit.jupiter.api.Test
import reactor.test.StepVerifier

class MonoFunctionTest {

    @Test
    fun classifyOneEmitsExactlyOneDecision() {
        val bean = ReactiveOrderFunctions().classifyOne()
        val publisher = bean.apply(Order("O-101", 1_500_000L))

        StepVerifier.create(publisher)
            .expectNext(Decision("O-101", "PRIORITY"))
            .verifyComplete()
    }

    @Test
    fun optionalCodeCanCompleteEmpty() {
        StepVerifier.create(normalizedCode("   "))
            .verifyComplete()

        StepVerifier.create(normalizedCode(" SAVE10 "))
            .expectNext("SAVE10")
            .verifyComplete()
    }
}
~~~

`verifyComplete()` on an empty `Mono` must **not** be interpreted as "sent an empty response"; the test only asserts the Reactor signal.

### 13.2. Unit Tests for `Flux`

~~~kotlin
import org.junit.jupiter.api.Test
import reactor.core.publisher.Flux
import reactor.test.StepVerifier

class FluxFunctionTest {

    @Test
    fun classifiesEveryEvent() {
        val input = Flux.just(
            Order("O-101", 1_000_000L),
            Order("O-102", 250_000L)
        )
        val output = ReactiveOrderFunctions()
            .classifyStream()
            .apply(input)

        StepVerifier.create(output)
            .expectNext(Decision("O-101", "PRIORITY"))
            .expectNext(Decision("O-102", "STANDARD"))
            .verifyComplete()
    }

    @Test
    fun invalidOrderTerminatesRawPipeline() {
        val input = Flux.just(
            Order("O-103", -10L),
            Order("O-104", 500_000L)
        )
        val output = ReactiveOrderFunctions()
            .classifyStream()
            .apply(input)

        StepVerifier.create(output)
            .expectError(IllegalArgumentException::class.java)
            .verify()
    }
}
~~~

The second test illustrates that **one error terminates the `Flux`**. Do not expect `O-104` to still be processed after `onError` on the same subscription.

### 13.3. Testing Per-Element Error Policies

~~~kotlin
import org.junit.jupiter.api.Test
import reactor.core.publisher.Flux
import reactor.test.StepVerifier

class SafeFluxFunctionTest {

    @Test
    fun badOrderDoesNotStopFollowingOrders() {
        // Configuration class defined in section 11.2.
        val output = SafeOrderFunctions()
            .classifySafely()
            .apply(Flux.just(
                Order("O-201", -1L),
                Order("O-202", 500_000L)
            ))

        StepVerifier.create(output)
            .expectNext(Decision("O-201", "REJECTED"))
            .expectNext(Decision("O-202", "STANDARD"))
            .verifyComplete()
    }
}
~~~

The test calls `SafeOrderFunctions` defined in section 11.2. In a real project, ensure this configuration class is loaded by Spring when using the bean in an adapter environment.

### 13.4. Testing Time-Based Publishers with Virtual Time

There is no need to wait for wall-clock time when testing `Flux.interval`:

~~~kotlin
import java.time.Duration
import org.junit.jupiter.api.Test
import reactor.core.publisher.Flux
import reactor.test.StepVerifier

class HeartbeatTest {

    @Test
    fun emitsTwoTicksWithVirtualTime() {
        StepVerifier.withVirtualTime {
            Flux.interval(Duration.ofSeconds(1)).take(2)
        }
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(2))
            .expectNext(0L, 1L)
            .verifyComplete()
    }
}
~~~

Here the publisher is created **inside the `withVirtualTime` supplier** so Reactor uses a virtual scheduler where applicable. This is a unit-level Reactor test and says nothing about external broker message delivery timing.

### 13.5. `FunctionCatalog` Test

With a Spring Boot application that has loaded `ReactiveOrderFunctions`, you can inspect the bean via `FunctionCatalog`:

~~~kotlin
import java.util.function.Function
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.cloud.function.context.FunctionCatalog
import reactor.core.publisher.Flux

@SpringBootTest(classes = [ReactiveOrdersApplication::class])
class CatalogReactiveFunctionTest {

    @Autowired
    lateinit var catalog: FunctionCatalog

    @Test
    fun findsReactiveFunction() {
        val function = catalog.lookup<
            Function<Flux<Order>, Flux<Decision>>
        >("classifyStream")

        assertNotNull(function)
    }
}
~~~

Unit tests prove the `Mono`/`Flux` processing logic, while the catalog test proves Spring registered and recognized the bean. To verify JSON/topic/destination behavior works, you must have **integration tests for the web/stream/serverless adapter**.

## 14. Limitations and Common Mistakes

| Mistake or Misconception | Why It Is Wrong | Correct Approach |
| --- | --- | --- |
| Treating `Mono<T>` like `T` | `Mono` only emits data when subscribed | Use operators, return the publisher to the adapter, and test with `StepVerifier` |
| Treating `Flux<T>` as `List<T>` | `Flux` can be unbounded and has error/cancellation signals | Do not call `collectList()` on an unbounded stream |
| Using `Mono.just(null)` | Reactor forbids null elements | Use `Mono.justOrEmpty(...)` or `Mono.empty()` |
| Assuming `Mono.empty()` is always HTTP 404 | HTTP mapping depends on the adapter | Define and test the HTTP contract |
| Treating `Mono<Unit>` like `Mono<Void>` | `Unit` is a real element; `Void` usually signals completion | Choose the completion type matching the intent |
| Calling `subscribe()` inside every function | Detaches lifecycle from the framework, makes errors hard to track | Return the publisher; subscribe manually only when genuinely managing lifecycle |
| Placing `retryWhen` indiscriminately on the entire stream | Can resubscribe and repeat side effects | Retry per unit of work, with idempotency and limits |
| Using outer `onErrorResume` to continue processing all messages | Switches to fallback once the source has errored | Handle errors in an inner publisher per element |
| Assuming backpressure across Kafka/RabbitMQ | Binders may not be reactive | Check binder capabilities and resource limits |
| Calling blocking APIs inside `map` | Can block processing threads for too long | Use reactive drivers or controlled `boundedElastic` |
| Assuming reactive functions are invoked per message | In Spring Cloud Stream they typically build the pipeline once | Understand lifecycle/subscription and corresponding retries |
| Confusing `Flux<Tuple2<A,B>>` with two ports | That is a single stream of pairs | Multiple outputs require `Tuple2<Flux<A>,Flux<B>>` and adapter support |
| Treating Kotlin `Flow` like Reactor `Flux` | Different APIs and coroutine models | Use compatible bridges when needed |

### Checklist Before Deploying Reactive Kotlin Functions to Production

1. Clear bean type: `Function<Flux<I>,Flux<O>>`, `Function<I,Mono<O>>`, or `Supplier<Flux<O>>`.
2. Identify **who subscribes**, when, and whether the publisher is finite or unbounded.
3. Explicitly define the meaning of **0 elements**, **1 element**, and **`onError`**.
4. Handle nulls at the JSON/Java boundary instead of passing null through `Mono`/`Flux`.
5. Bound concurrency and evaluate blocking sources.
6. Separately test per-element errors if the stream must continue after a bad record.
7. Verify whether the binder supports backpressure/retries/DLQs as required.
8. Keep business logic independent; leave transport/serialization to adapters.
9. Test with `StepVerifier`, `FunctionCatalog`, and an end-to-end flow in a real environment.

## 15. Self-Check Questions

**Question 1.** `Mono<List<Order>>` and `Flux<Order>` can both hold three orders. What is the difference?

**Answer:** `Mono<List<Order>>` emits **one `List` element**; `Flux<Order>` emits each `Order` as multiple `onNext` signals. The two types have different streaming/serialization contracts.

**Question 2.** Why is `Mono.justOrEmpty(null)` not equivalent to `Mono.just(null)`?

**Answer:** `justOrEmpty(null)` creates a publisher that **completes empty**. Reactor forbids `onNext(null)`, so `Mono.just(null)` is not a valid way to emit a null value.

**Question 3.** Is a `Function<Flux<Order>, Flux<Decision>>` in Spring Cloud Stream normally invoked again for each `Order`?

**Answer:** No. It is normally invoked once to set up the pipeline; elements flow through the subscribed stream. This is a key difference from an imperative `Function<Order, Decision>`.

**Question 4.** If inside `orders.map(::decide)` one order fails and `decide` throws an exception, do subsequent orders continue on the same subscription?

**Answer:** Not by default: an exception produces a terminal `onError`. You need a **per-element** recovery policy or an error-branch design if the stream must not stop.

**Question 5.** Are `Mono.just(Unit)` and `orders.then()` the same?

**Answer:** No. `Mono.just(Unit)` emits a `Unit`, whereas `then()` returns `Mono<Void>` signaling only completion/error without emitting `Unit`.

**Question 6.** Does using `Flux` with a regular Kafka binder guarantee backpressure from broker to consumer?

**Answer:** No. Backpressure support depends on the binder and the actual source/sink components.

**Question 7.** Why does a unit test calling `classifyStream().apply(Flux.just(...))` not prove the broker received messages?

**Answer:** A unit test only verifies the Reactor pipeline; it does not test bindings, serialization, the broker, partitions, retries, or delivery.

**Question 8.** When should `flatMap` be used instead of `map`?

**Answer:** When each element must produce an **inner publisher** such as a `Mono` due to async I/O, or can yield 0..N results. For simple synchronous `T -> R` transformations, `map` is clearer.

## References

- [Spring Cloud Function — Programming Model: Reactor, FunctionCatalog, Supplier, and Function Arity](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Stream — Producing and Consuming Messages: Reactive Functions/Suppliers/Consumers](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Error Handling: differences between imperative and reactive](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html)
- [Project Reactor — Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [Project Reactor — Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)
- [Project Reactor — Kotlin Support and Reactor Kotlin Extensions](https://projectreactor.io/docs/core/release/reference/kotlin.html)
- [Project Reactor — Testing with StepVerifier and VirtualTime](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Kotlin — Coroutines and Flow](https://kotlinlang.org/docs/flow.html)
