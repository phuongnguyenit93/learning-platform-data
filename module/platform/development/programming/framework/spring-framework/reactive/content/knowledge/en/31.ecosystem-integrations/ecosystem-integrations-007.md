# ReactiveAdapterRegistry and Integrating Other Reactive Libraries in Spring WebFlux

## 1. Why does Spring WebFlux need an adapter layer?

Spring WebFlux is built on Reactive Streams and Project Reactor. Internal APIs typically use `Mono<T>` for 0..1 results and `Flux<T>` for 0..N streams. However, Java/Kotlin applications may already use other asynchronous types:

- JDK's `CompletableFuture<T>` or `CompletionStage<T>`.
- JDK Flow API's `java.util.concurrent.Flow.Publisher<T>`.
- RxJava 3's `Flowable<T>`, `Single<T>`, `Maybe<T>`, `Completable`, or `Observable<T>`.
- Kotlin's `Deferred<T>` and coroutines.
- SmallRye Mutiny's `Uni<T>` and `Multi<T>`.
- A reactive/async type defined by an application or internal library.

If every library were forced to change its entire public API to Mono/Flux, integration would become expensive. `org.springframework.core.ReactiveAdapterRegistry` solves this problem by storing a set of adapters capable of converting **from a reactive type to a Reactive Streams Publisher and back**.

~~~text
          Library A                    Spring WebFlux
       CompletableFuture<T>                 |
       RxJava3 Flowable<T>                  |
       RxJava3 Single<T>                    |
       Kotlin Deferred<T>                   |
       Mutiny Uni<T>/Multi<T>               |
       Custom AsyncType<T>                  |
                |                           |
                v                           |
       ReactiveAdapterRegistry              |
                |                           |
         ReactiveAdapter                    |
             /       \                      |
      toPublisher  fromPublisher            |
             \       /                      |
                v                           v
        org.reactivestreams.Publisher<T>
                      |
               Mono<T> / Flux<T>
                      |
             HTTP body / controller
~~~

The registry is a **type-conversion mechanism** and stream-semantics metadata store, not a replacement runtime for Reactor, a new scheduler, a thread pool, or a message broker.

## 2. Key components

| Component | Responsibility |
| --- | --- |
| `ReactiveAdapterRegistry` | Stores, looks up, and registers adapters for reactive/async types |
| `ReactiveAdapter` | Converts an instance to a `Publisher` or from a `Publisher` |
| `ReactiveTypeDescriptor` | Describes the type's cardinality, empty completion, and deferred behavior |
| `org.reactivestreams.Publisher<T>` | The standard Reactive Streams interface Spring uses as the bridge |
| `Mono<T>` | Reactor Publisher with at most one element |
| `Flux<T>` | Reactor Publisher with zero or more elements |

Primary APIs of the registry:

~~~java
ReactiveAdapterRegistry registry = new ReactiveAdapterRegistry();

ReactiveAdapter adapter =
        registry.getAdapter(CompletableFuture.class);

ReactiveAdapter sharedAdapter =
        ReactiveAdapterRegistry.getSharedInstance()
                .getAdapter(CompletableFuture.class);
~~~

`new ReactiveAdapterRegistry()` creates a new registry and auto-registers default adapters depending on the classpath. `getSharedInstance()` returns a lazily created shared default registry. Per the JavaDoc, applications needing customization should pass around a configured, long-lived registry rather than mutating the shared registry arbitrarily.

## 3. Reactive Streams Publisher as the intermediate interface

`org.reactivestreams.Publisher<T>` is the contract between publisher and subscriber. It is not synonymous with Reactor's `Flux<T>`, even though both Mono and Flux implement Publisher.

A Publisher source emits signals:

~~~text
subscribe
   |
   v
onSubscribe(Subscription)
   |
   +-- request(n) --> onNext(value) ... (up to demand)
   |
   +-- onComplete()
   |
   +-- onError(error)
   |
   +-- cancel()
~~~

Reactive Streams sets rules for backpressure, signal serialization, terminal signals, and cancellation. When an adapter turns another source into a Publisher, it must maintain behavior compliant with this contract.

Example bridging from another library's Publisher to Reactor:

~~~java
Publisher<String> source = obtainPublisher();

Flux<String> flux = Flux.from(source);
Mono<String> first = Mono.from(source);
~~~

**Do not treat those two approaches as equivalent.** `Flux.from(source)` represents 0..N, whereas `Mono.from(source)` takes at most the first element and cancels upstream when appropriate. If the source contains multiple elements and business logic needs all of them, using Mono will drop the remaining elements.

In functional endpoints and WebClient, Spring often accepts an input Publisher, but if you pass a plain Publisher alone, the framework may not know its cardinality clearly. Once you know whether the type is a single result or multiple results, wrap it with `Mono` or `Flux` to express intent.

## 4. Cardinality metadata: 0..1, 1, 0..N, and no value

`ReactiveTypeDescriptor` describes how many elements a reactive type can emit.

| Descriptor factory | Semantics | Conceptual examples |
| --- | --- | --- |
| `multiValue(type, emptySupplier)` | 0..N | Flux, RxJava Flowable, Mutiny Multi |
| `singleOptionalValue(type, emptySupplier)` | 0..1 | Mono, RxJava Maybe, Mutiny Uni depending on implementation |
| `singleRequiredValue(type)` | Must emit one value to complete successfully | RxJava Single |
| `noValue(type, emptySupplier)` | 0 values, only signals complete/error | RxJava Completable |
| `nonDeferredAsyncValue(type, emptySupplier)` | Single optional, though computation may already have started before subscribe | CompletableFuture |

Key properties to remember:

- `isMultiValue()`: the source can emit multiple values.
- `isNoValue()`: the source only signals completion and carries no data values.
- `supportsEmpty()`: the type allows completing with no value.
- `isDeferred()` on the descriptor: indicates deferred subscription/lazy evaluation per the type description.

For example, a controller returning one object is not the same as returning a list. Spring uses cardinality to decide how to process and write the HTTP response. A multi-element stream may be serialized as a JSON array if the media type is non-streaming, whereas NDJSON/SSE lets each element be written individually.

**Do not pick a descriptor based on “I want to return one result” if the actual type can emit multiple values.** Wrong cardinality can lose data, cause unnecessary buffering, or complete the response differently than expected.

## 5. Default adapters registered when libraries are present

In Spring Framework 7.0.x, `ReactiveAdapterRegistry` inspects the classpath at initialization. It has built-in support for:

| Platform | Notable types | Condition |
| --- | --- | --- |
| Reactor | `Mono`, `Flux` | reactor-core is on the classpath |
| JDK asynchronous | `CompletableFuture`, Java `Flow.Publisher` | Corresponding bridge registered when supporting library is present |
| RxJava 3 | `Flowable`, `Observable`, `Single`, `Maybe`, `Completable` | RxJava 3 is on the classpath |
| Kotlin Coroutines | `Deferred` | Reactor and the corresponding coroutine-Reactor bridge library are present |
| SmallRye Mutiny | `Uni`, `Multi` | A Mutiny version recognized by Spring is on the classpath |

According to Spring Framework 7.0.10's documentation, Mutiny support in the registry targets 1.x/2.x. When an application uses a different major version, verify real compatibility rather than assuming the adapter will be registered.

Java `Flow.Publisher` support differs from the `org.reactivestreams.Publisher` interface: they are **two separate interfaces**, even though their protocol structures are closely aligned. Reactor provides the corresponding JDK Flow bridge.

### 5.1. The classpath determines whether an adapter appears

~~~java
ReactiveAdapterRegistry registry = new ReactiveAdapterRegistry();

ReactiveAdapter rxAdapter =
        registry.getAdapter(
                io.reactivex.rxjava3.core.Flowable.class);
~~~

The snippet above only compiles if the project has RxJava 3. When RxJava 3 is on the runtime classpath, the registry can auto-detect and register the adapter. If the library is absent, do not hard-code the assumption that every type will be recognized.

A safe pattern is:

~~~java
ReactiveAdapter adapter = registry.getAdapter(type);

if (adapter == null) {
    throw new IllegalArgumentException(
            "No reactive adapter for " + type.getName());
}
~~~

`getAdapter(...)` can return `null`. Never call `toPublisher` on a null adapter.

### 5.2. RxJava 1/2 differs from RxJava 3

Older Spring documentation described adapters for RxJava 1 or RxJava 2. Those examples should not be copied as default supported APIs in Spring 7.0.x. When integrating RxJava, prefer RxJava 3 and verify the `io.reactivex.rxjava3.core` package.

## 6. ReactiveAdapter: bidirectional conversion

Once you obtain a `ReactiveAdapter`:

~~~java
ReactiveAdapter adapter = registry.getAdapter(SomeType.class);
~~~

There are two directions:

### 6.1. toPublisher: from an external type to Reactive Streams

~~~java
Publisher<String> publisher =
        adapter.toPublisher(externalAsyncValue);

Flux<String> flux = Flux.from(publisher);
~~~

The adapter takes an instance of the reactive/async type and creates a corresponding Publisher. This is the common direction when you receive data from another SDK and feed it into a Reactor pipeline.

### 6.2. fromPublisher: from Publisher to the library's type

~~~java
Object externalValue =
        adapter.fromPublisher(Flux.just("alpha", "beta"));
~~~

The adapter creates an instance of the external type. It returns `Object` because the registry handles many different types. The caller must know which type the adapter is bound to and cast safely.

### 6.3. Do not invent conversion boilerplate if a library bridge already exists

When you only need to work with Reactor, direct APIs are often clearer:

~~~java
Mono<String> mono = Mono.fromFuture(
        CompletableFuture.completedFuture("ready"));

Flowable<String> flowable =
        Flowable.fromPublisher(Flux.just("a", "b"));
~~~

`Mono.fromFuture` and `Flowable.fromPublisher` are dedicated bridges. `ReactiveAdapterRegistry` is useful when a framework must handle many types dynamically, such as receiving a Class or Object from a library/extension.

## 7. CompletableFuture and CompletionStage

`CompletableFuture<T>` is the JDK's asynchronous type. Spring includes an adapter when Reactor is present.

~~~java
CompletableFuture<String> future =
        CompletableFuture.completedFuture("ready");

ReactiveAdapter adapter =
        registry.getAdapter(CompletableFuture.class);

Publisher<String> publisher =
        adapter.toPublisher(future);

String text = Mono.from(publisher).block();
~~~

The result is `ready`.

### 7.1. A Future does not mean a lazy Publisher

A CompletableFuture may already be running before being converted to a Publisher:

~~~java
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(this::loadData);
~~~

The code inside `supplyAsync` is already scheduled independently of downstream subscription. Converting a future into a Mono does not magically make the work lazy or non-blocking.

If you want to defer creating the future until subscription:

~~~java
Mono<String> lazy = Mono.defer(() ->
        Mono.fromFuture(
                CompletableFuture.supplyAsync(this::loadData)));
~~~

This is an illustrative example assuming `loadData()` exists. In production, provide an explicit Executor and bounded concurrency rather than relying on the Common ForkJoinPool for everything.

### 7.2. Empty/null and exceptions

Reactive Streams does not allow `onNext(null)`. If a CompletableFuture completes with null, the bridge typically represents the result as an empty completion rather than emitting null.

If the future completes exceptionally, the Publisher emits `onError`. The actual root cause may be wrapped in `CompletionException` or an intermediate exception class; preserve the cause when mapping to domain errors.

### 7.3. Cancellation

Cancelling a Publisher does not necessarily cancel work running inside another SDK. A future may support cancellation, yet the underlying I/O operation might keep running. Test cancellation propagation whenever the application uses futures to call HTTP, databases, or expensive tasks.

Do not assume converting to a Mono brings multi-element backpressure: a future represents a single result.

## 8. RxJava 3: Flowable, Single, Maybe, Completable, and Observable

RxJava 3 has several types with different semantics.

| RxJava 3 type | Value count | Backpressure | Common Reactor bridge |
| --- | --- | --- | --- |
| `Flowable<T>` | 0..N | Yes | `Flux.from(flowable)` |
| `Single<T>` | Exactly one value or error | Not multi-item demand | `Mono.from(single.toFlowable())` |
| `Maybe<T>` | 0..1 | Not multi-item demand | `Mono.from(maybe.toFlowable())` |
| `Completable` | No value | Completion/error | `Mono.from(completable.toFlowable())` |
| `Observable<T>` | 0..N | No direct Reactive Streams backpressure | Needs a strategy to convert to Flowable |

When using `ReactiveAdapterRegistry`, Spring provides the corresponding default conversions if the library is on the classpath.

### 8.1. Flowable: Reactive Streams-compatible interface

~~~java
Flowable<String> rx = Flowable.just("a", "b");

Flux<String> flux = Flux.from(rx);

List<String> values = flux.collectList().block();
~~~

`Flowable` implements Reactive Streams Publisher, so it can be passed directly into `Flux.from`. For a small finite stream, the result is `[a, b]`.

If you need to return it from an annotated Spring WebFlux controller, you can declare `Flowable<Dto>` directly; the registry recognizes it as a multi-value reactive type.

### 8.2. Single and Maybe

~~~java
Single<String> single = Single.just("ready");
Maybe<String> maybe = Maybe.empty();

Mono<String> one = Mono.from(single.toFlowable());
Mono<String> optional = Mono.from(maybe.toFlowable());
~~~

Single cannot complete empty successfully; Maybe can be empty. This matters when a route represents “record not found” or an optional field.

### 8.3. Completable emits no data

~~~java
Completable done = Completable.complete();

Mono<Void> completion =
        Mono.from(done.toFlowable()).then();
~~~

`Mono<Void>` is suitable for describing an operation with no response body. Do not try to map a Completable to a DTO because it emits no value.

### 8.4. Observable lacks backpressure

RxJava 3's `Observable<T>` does not implement Reactive Streams demand the way Flowable does. Converting an Observable to a Flowable requires choosing a `BackpressureStrategy`.

Example:

~~~java
Flowable<String> bridge =
        Observable.just("a", "b")
                .toFlowable(BackpressureStrategy.BUFFER);
~~~

Per Spring Framework 7.0.10 source, the default adapter for Observable uses `BackpressureStrategy.BUFFER` to create a Flowable. For high-rate or infinite sources, the buffer can grow rapidly if downstream processes slowly.

If load regulation is needed, prefer Flowable or convert with an intentional backpressure strategy, cap queues, and monitor overflows. An adapter cannot conjure true backpressure capability on an upstream that does not support it.

## 9. Kotlin coroutines: Deferred and Flow

Kotlin has two API groups to distinguish:

- `Deferred<T>`: a single asynchronous result, close to single-value.
- `kotlinx.coroutines.flow.Flow<T>`: a multi-value stream based on coroutines/suspension.

Spring WebFlux supports Kotlin controllers with `suspend fun` and Flow types through coroutine integration. Specific bridges use `kotlinx-coroutines-reactor` and `kotlinx-coroutines-reactive`.

The Spring 7.0.x registry documents a classpath-registered adapter for Kotlin `Deferred` via the Reactor bridge. **Do not assume every Kotlin Flow is registered inside ReactiveAdapterRegistry just because Spring supports Kotlin Flow at the controller layer.** Kotlin Flow support may go through dedicated Kotlin/coroutine mechanisms outside the adapter registry.

Illustrative Kotlin controller example:

~~~kotlin
@RestController
@RequestMapping("/api/kotlin")
class KotlinController {

    @GetMapping("/one")
    suspend fun one(): Greeting =
        Greeting("hello")

    @GetMapping("/events", produces = ["text/event-stream"])
    fun events(): Flow<Greeting> =
        flow {
            emit(Greeting("a"))
            emit(Greeting("b"))
        }
}
~~~

This is an illustrative Kotlin example requiring the Kotlin plugin, spring-webflux, kotlinx-coroutines-reactor, and matching dependencies; it is not part of the standalone Java program below.

When bridging between Reactor and Kotlin coroutines, pay attention to cancellation, context propagation, and dispatchers. Never use `runBlocking` inside a WebFlux handler to “wait” for a coroutine because it can block the event-loop.

## 10. SmallRye Mutiny: Uni and Multi

SmallRye Mutiny provides:

- `Uni<T>`: a single asynchronous result or failure.
- `Multi<T>`: a multi-element stream.

Spring Framework 7.0.x includes a registrar for Mutiny when the library is detected on the classpath. However, the major version range documented in the JavaDoc is Mutiny 1.x/2.x; verify separately when using Mutiny 3.x or newer versions.

Conceptual example:

~~~java
// Illustrative example requiring compatible SmallRye Mutiny dependencies.
Uni<String> uni = Uni.createFrom().item("ready");
Multi<String> multi =
        Multi.createFrom().items("a", "b");
~~~

`ReactiveAdapterRegistry` can convert them to Publishers if the adapter is registered. There is no need to wrap every business service in Reactor unless Reactor operators genuinely add value within your application boundary.

Do not use `Uni.await().indefinitely()` on the WebFlux event-loop. A blocking wait negates reactive benefits and can stall other requests.

## 11. Annotated controllers and functional APIs differ

Spring WebFlux documentation highlights two API groups.

### 11.1. Annotated controllers

With `@RestController` and `@RequestMapping`, WebFlux can recognize reactive return types via `ReactiveAdapterRegistry`:

~~~java
@RestController
@RequestMapping("/api/examples")
class ExampleController {

    @GetMapping("/future")
    CompletableFuture<String> future() {
        return CompletableFuture.completedFuture("ready");
    }

    @GetMapping("/rx")
    Flowable<String> rx() {
        return Flowable.just("alpha", "beta");
    }
}
~~~

This is an illustrative snippet requiring RxJava 3 on the classpath. Spring recognizes CompletableFuture as a single async value and Flowable as a multi-value Publisher.

When the response media type is regular JSON, a multi-value source may be serialized into a JSON array. With `text/event-stream` or `application/x-ndjson`, values can be emitted/flushed as a stream. Do not casually use a multi-value type for a response expecting a single DTO.

### 11.2. Functional endpoints and WebClient

Functional APIs primarily use `Mono`/`Flux` to represent results and accept `Publisher` for input.

~~~java
HandlerFunction<ServerResponse> handler = request -> {
    Publisher<String> source = obtainPublisher();

    return ServerResponse.ok()
            .body(Flux.from(source), String.class);
};
~~~

This is an illustrative snippet assuming `obtainPublisher()`. When the source has single-value semantics, use `Mono.from(source)`; when it has multiple values, use `Flux.from(source)`.

### 11.3. Why does cardinality affect HTTP encoding?

A single-value result usually corresponds to one JSON object:

~~~json
{"id":42,"name":"WebFlux"}
~~~

A multi-value source under `application/json` can become a JSON array:

~~~json
[
  {"id":42,"name":"WebFlux"},
  {"id":43,"name":"Reactor"}
]
~~~

With streaming media types, each item can be sent as soon as it is ready. If a library reports the wrong item count (e.g., actually 0..N while the descriptor reports single), the HTTP output can violate the contract.

## 12. Registering an adapter for a custom type

Suppose an application has a `Batch<T>` type wrapping a Publisher without directly implementing `Publisher`. The registry will not automatically understand `Batch` unless registered.

An adapter needs three parts:

1. `ReactiveTypeDescriptor` describing cardinality and an empty instance.
2. `toAdapter`: converts the custom type to `Publisher<?>`.
3. `fromAdapter`: converts `Publisher<?>` to the custom type.

~~~java
registry.registerReactiveType(
        ReactiveTypeDescriptor.multiValue(
                Batch.class,
                () -> new Batch(Flux.empty())),
        source -> ((Batch) source).publisher(),
        publisher -> new Batch(publisher));
~~~

`Batch` itself can be defined as:

~~~java
record Batch(Publisher<?> publisher) {
}
~~~

After registration:

~~~java
ReactiveAdapter adapter =
        registry.getAdapter(Batch.class);

Publisher<?> publisher =
        adapter.toPublisher(
                new Batch(Flux.just("a", "b")));

Batch restored =
        (Batch) adapter.fromPublisher(
                Flux.just(1, 2));
~~~

These are two bridge functions containing no blocking or subscription side effects. The Publisher is subscribed to by downstream on demand.

### 12.1. registerReactiveType and registerReactiveTypeOverride

There are two APIs:

- `registerReactiveType(...)`: registers an adapter after existing ones; suitable for new types.
- `registerReactiveTypeOverride(...)`: places the adapter first so it can override an existing adapter.

The registry checks for an exact match before considering assignability. For complex overrides involving interfaces/base classes and subtypes, test specifically: registering a common interface does not necessarily override an existing exact match for each subtype.

Avoid overriding Spring's default adapters unless you have a very clear reason. Changing the cardinality or lifecycle of a common type can affect controller argument/return handling and other components.

### 12.2. Do not turn a custom registry into a global side effect

~~~java
ReactiveAdapterRegistry registry = new ReactiveAdapterRegistry();
registry.registerReactiveType(...);
~~~

Registering on a new instance only affects that instance. It does **not automatically** replace every registry Spring WebFlux has already configured in the application.

If controllers need to recognize the custom type automatically, you must ensure the custom registry is wired into the right components handling handler arguments/return values and response bodies. Spring provides `RequestMappingHandlerAdapter.setReactiveAdapterRegistry(...)`, though related return-value/result handlers must also share the same semantics.

In many projects, a lower-risk approach is converting the custom type to Mono/Flux at the controller boundary. Only customize the registry when multiple components/framework extensions genuinely need that type understood consistently across the framework.

## 13. Runnable Java 17+ program: default and custom adapters

A standalone example without starting a server, requiring only JDK 17+, Maven, and Spring/Reactor/RxJava3 dependencies. The program demonstrates:

1. The registry auto-detects an adapter for CompletableFuture.
2. The registry auto-detects an adapter for RxJava 3 Flowable when RxJava is on the classpath.
3. The app registers a new adapter for Batch.
4. Bidirectional conversion between the custom type and Publisher.
5. Results are verified with assertions before printing to stdout.

Selected versions: Spring Boot **4.1.2** (stable Oct/2026) with Spring Framework **7.0.10** per BOM, and RxJava **3.1.12**.

### 13.1. Project structure

~~~text
reactive-adapter-demo/
  pom.xml
  src/main/java/example/adapter/RegistryDemo.java
~~~

### 13.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>reactive-adapter-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>

        <dependency>
            <groupId>io.reactivex.rxjava3</groupId>
            <artifactId>rxjava</artifactId>
            <version>3.1.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 13.3. RegistryDemo.java

~~~java
package example.adapter;

import java.time.Duration;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.CompletableFuture;

import io.reactivex.rxjava3.core.Flowable;
import org.reactivestreams.Publisher;
import org.springframework.core.ReactiveAdapter;
import org.springframework.core.ReactiveAdapterRegistry;
import org.springframework.core.ReactiveTypeDescriptor;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class RegistryDemo {

    record Batch(Publisher<?> publisher) {
    }

    private static ReactiveAdapter required(
            ReactiveAdapterRegistry registry, Class<?> type) {

        return Objects.requireNonNull(
                registry.getAdapter(type),
                "Missing adapter for " + type.getName());
    }

    public static void main(String[] args) {
        ReactiveAdapterRegistry registry =
                new ReactiveAdapterRegistry();

        // 1) CompletableFuture -> Publisher -> Mono.
        ReactiveAdapter futureAdapter =
                required(registry, CompletableFuture.class);

        String futureValue = Mono.from(
                        futureAdapter.<String>toPublisher(
                                CompletableFuture.completedFuture("ready")))
                .block(Duration.ofSeconds(5));

        if (!"ready".equals(futureValue)) {
            throw new AssertionError("Wrong future value");
        }

        // 2) RxJava3 Flowable -> Publisher -> Flux.
        ReactiveAdapter rxAdapter =
                required(registry, Flowable.class);

        List<Integer> rxValues = Flux.from(
                        rxAdapter.<Integer>toPublisher(
                                Flowable.just(1, 2, 3)))
                .collectList()
                .block(Duration.ofSeconds(5));

        if (!List.of(1, 2, 3).equals(rxValues)) {
            throw new AssertionError("Wrong RxJava values");
        }

        // 3) Register a custom 0..N type.
        registry.registerReactiveType(
                ReactiveTypeDescriptor.multiValue(
                        Batch.class,
                        () -> new Batch(Flux.empty())),
                source -> ((Batch) source).publisher(),
                publisher -> new Batch(publisher));

        ReactiveAdapter batchAdapter =
                required(registry, Batch.class);

        // 4) Custom type -> Publisher.
        List<?> fromCustom = Flux.from(
                        batchAdapter.toPublisher(
                                new Batch(Flux.just("a", "b"))))
                .collectList()
                .block(Duration.ofSeconds(5));

        if (!List.of("a", "b").equals(fromCustom)) {
            throw new AssertionError("Wrong custom values");
        }

        // 5) Publisher -> custom type.
        Batch restored = (Batch) batchAdapter.fromPublisher(
                Flux.just(7, 9));

        List<?> toCustom = Flux.from(restored.publisher())
                .collectList()
                .block(Duration.ofSeconds(5));

        if (!List.of(7, 9).equals(toCustom)) {
            throw new AssertionError("Wrong round-trip");
        }

        System.out.println("future=" + futureValue);
        System.out.println("rxjava=" + rxValues);
        System.out.println("custom-toPublisher=" + fromCustom);
        System.out.println("custom-fromPublisher=" + toCustom);
    }
}
~~~

### 13.4. Running the program

From the directory containing `pom.xml`:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=example.adapter.RegistryDemo
~~~

**Exact expected stdout:**

~~~text
future=ready
rxjava=[1, 2, 3]
custom-toPublisher=[a, b]
custom-fromPublisher=[7, 9]
~~~

Explanation:

- `CompletableFuture.completedFuture` has one value, so Mono emits `ready`.
- `Flowable.just(1,2,3)` has three values, so Flux emits the entire list.
- Batch does not implement Publisher, yet the registry knows both bridge functions.
- `fromPublisher` creates a Batch holding the new Publisher source; when downstream subscribes via Flux.from, it emits 7 and 9.
- No manual subscribe call is needed; `block` is only used at the boundary of the standalone command-line program.

This is an illustrative standalone Java example with assertions. In reactive WebFlux controllers/services, do not use `block()`; return Mono/Flux so the framework manages subscriptions.

## 14. Spring Boot controller example returning RxJava 3 directly

To observe Spring using adapters in an annotated controller, you can create a minimal WebFlux app.

### 14.1. Application class

~~~java
package example.adapter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AdapterWebApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                AdapterWebApplication.class, args);
    }
}
~~~

### 14.2. Controller class

~~~java
package example.adapter;

import java.util.concurrent.CompletableFuture;

import io.reactivex.rxjava3.core.Flowable;
import io.reactivex.rxjava3.core.Single;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/reactive")
public class ReactiveController {

    public record Item(String source, int value) {
    }

    @GetMapping("/future")
    public CompletableFuture<Item> future() {
        return CompletableFuture.completedFuture(
                new Item("future", 1));
    }

    @GetMapping("/single")
    public Single<Item> single() {
        return Single.just(new Item("rx-single", 2));
    }

    @GetMapping("/flowable")
    public Flowable<Item> flowable() {
        return Flowable.just(
                new Item("rx-flowable", 3),
                new Item("rx-flowable", 4));
    }
}
~~~

This is an additional app using the same `pom.xml` from section 13. Place both classes at the exact paths:

~~~text
src/main/java/example/adapter/AdapterWebApplication.java
src/main/java/example/adapter/ReactiveController.java
~~~

Run the app with:

~~~bash
mvn spring-boot:run -Dspring-boot.run.main-class=example.adapter.AdapterWebApplication
~~~

Call:

~~~bash
curl -s http://localhost:8080/api/reactive/future
curl -s http://localhost:8080/api/reactive/single
curl -s http://localhost:8080/api/reactive/flowable
~~~

Expected JSON responses:

~~~json
{"source":"future","value":1}
~~~

~~~json
{"source":"rx-single","value":2}
~~~

~~~json
[
  {"source":"rx-flowable","value":3},
  {"source":"rx-flowable","value":4}
]
~~~

JSON whitespace may vary by serializer; what matters is the single object vs. array structure. For `Flowable` with multiple items, Spring recognizes the multi-value return type via the registry.

You must add `spring-boot-maven-plugin` to the build section of `pom.xml` if your Maven project lacks this plugin in inherited configuration:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
</plugin>
~~~

In a real application, separate controller/service, use dependency injection, and add appropriate validation, security, and error handling.

## 15. Backpressure, cancellation, and lifecycle when switching libraries

Converting types does not mean every operational characteristic is preserved unconditionally.

### 15.1. Backpressure

`Flowable` and `Flux` follow Reactive Streams `request(n)`, so demand can propagate across the bridge.

However, `Observable` can emit rapidly without respecting downstream demand. If Spring converts Observable using buffering, queues grow when consumers are slow. Consider:

- Use Flowable whenever possible.
- Bound the emitting source, size, and queue.
- Choose a backpressure policy fitting the business domain.
- Monitor overflows, dropped events, and memory pressure.
- Avoid turning an infinite stream into `collectList()`.

### 15.2. Cancellation

When an HTTP client disconnects, downstream can cancel the Publisher. A standard adapter should forward cancel to the source if the source supports it. However:

- A CompletableFuture may already be executing.
- A Coroutine has its own Job lifecycle.
- Custom callback APIs may not expose cancellation.
- An SDK may continue working even after the Subscriber cancels.

When writing a custom adapter, verify whether the source truly supports unsubscribe/dispose/cancel and clean up resources per its contract.

### 15.3. Error propagation

Exceptions from the source library must be routed to `onError`, not swallowed or converted to normal values unintentionally. When bridging a failed future, a `CompletionException` wrapper may be present; when bridging RxJava, errors already travel in the Publisher chain.

Do not use:

~~~java
// Wrong when only intending type conversion: loses the original error.
source.onErrorResume(error -> Mono.empty());
~~~

unless an empty fallback is an intentional business decision.

### 15.4. Thread scheduling

`ReactiveAdapterRegistry` does not turn blocking tasks into non-blocking ones and does not create a dedicated scheduler per source.

If a blocking SDK is called directly on the event loop, wrapping its result in a Mono does not fix the blocking.

Example if the API is genuinely blocking:

~~~java
Mono<Result> safe = Mono.fromCallable(
                () -> blockingClient.fetch())
        .subscribeOn(Schedulers.boundedElastic());
~~~

This is an illustrative snippet requiring `blockingClient` and `Result`. Use an appropriate executor/scheduler and cap concurrency. Never run blocking I/O on the default event-loop.

### 15.5. Context propagation

Reactor `Context`, Kotlin `CoroutineContext`, thread-local MDC, and tracing contexts are not automatically one unified system. When crossing libraries, verify whether trace IDs/security contexts still propagate. Use the context-propagation mechanisms supported by Spring/Reactor and the target library; do not guess that registering an adapter alone is sufficient.

## 16. Configuring a custom registry in large applications

If an application has an SDK using a custom reactive type across many controllers, you may want to share a pre-configured registry.

Recommended design:

1. Create a new `ReactiveAdapterRegistry`.
2. Register the type after built-in adapters.
3. Configure that registry into the WebFlux components that need it.
4. Test argument resolution, return-value handling, and HTTP encoding.
5. Test errors, empty, multi-value, and cancellation.

Example registration in a factory method:

~~~java
static ReactiveAdapterRegistry newRegistry() {
    ReactiveAdapterRegistry registry =
            new ReactiveAdapterRegistry();

    registry.registerReactiveType(
            ReactiveTypeDescriptor.multiValue(
                    Batch.class,
                    () -> new Batch(Flux.empty())),
            source -> ((Batch) source).publisher(),
            Batch::new);

    return registry;
}
~~~

Merely creating a `ReactiveAdapterRegistry` bean does not guarantee every Spring WebFlux component automatically uses that bean. Check framework configuration for your version. `RequestMappingHandlerAdapter.setReactiveAdapterRegistry` is one configuration point, though related result handlers and codec paths must also align.

If the custom type does not need to be a direct controller return/argument type, converting `Batch` to Mono/Flux in the controller is usually simpler and easier to maintain.

## 17. Testing adapters properly

Whenever a custom adapter is added, test at minimum:

| Test case | What to verify |
| --- | --- |
| 0 values | Empty completion matches semantics |
| 1 value | Neither adds nor drops values |
| N values | Does not truncate when type is multi-value |
| Error | `onError` and cause are preserved |
| Cancellation | Upstream disposes/cancels per contract |
| Backpressure | Does not emit beyond demand if source supports it |
| Null value | Does not violate Reactive Streams `onNext(null)` |
| Deferred source | Does not run eagerly before subscription if descriptor is deferred |
| Eager future | Behavior already running before subscription is understood |
| Runtime classpath missing dependency | `getAdapter` returns null; clear error |
| Override adapter | Exact/assignable precedence is correct |
| HTTP controller | JSON object/array/stream matches cardinality |
| Thread/context | Does not block event loop; trace/security context has clear policy |

### 17.1. StepVerifier test for a Reactor bridge

~~~java
ReactiveAdapter adapter =
        registry.getAdapter(Flowable.class);

StepVerifier.create(
        Flux.from(adapter.<Integer>toPublisher(
                Flowable.just(1, 2, 3))))
        .expectNext(1, 2, 3)
        .verifyComplete();
~~~

This is an illustrative test snippet requiring the `reactor-test` dependency in test scope.

### 17.2. Testing errors

~~~java
Flowable<Integer> failed =
        Flowable.error(new IllegalStateException("boom"));

StepVerifier.create(Flux.from(
        adapter.<Integer>toPublisher(failed)))
        .expectErrorMessage("boom")
        .verify();
~~~

Do not test only the happy path, because the biggest differences between adapters show up in error/cancel/backpressure behavior.

## 18. Common misconceptions and errors

| Misconception/error | Why it is wrong | How to handle |
| --- | --- | --- |
| ReactiveAdapterRegistry is a Reactor scheduler | The registry only manages type conversion | Use a dedicated scheduler for blocking APIs |
| Having an RxJava3 dependency means every API accepts RxJava types | Behavior depends on the boundary; controllers and functional APIs differ | Check the API contract and use Mono/Flux when needed |
| Adapter not found means Spring does not support reactive | The library may be missing from the runtime classpath | Check dependencies and `getAdapter` |
| Using Mono.from with a multi-element Publisher | Takes at most the first element | Use Flux.from for multi-value |
| Using Flux for single-value without describing semantics | Framework may treat it as 0..N | Use Mono or the right descriptor |
| CompletableFuture automatically becomes lazy when converted to Mono | The future may already be running | Use `defer` if you want to delay creating the future |
| Observable always has backpressure | Observable does not follow Reactive Streams demand | Choose Flowable/BackpressureStrategy |
| Adapters automatically bound memory | Unbounded buffers can grow | Bound queues and test slow consumers |
| Adapters automatically propagate all trace context | Context models differ | Configure context propagation explicitly |
| A custom registry instance automatically applies to every controller | Framework components may use a different registry | Wire the right components or convert at the boundary |
| `registerReactiveTypeOverride` always overrides every subtype | Exact match is checked before assignability | Test precedence with each type |
| Switching types means switching threads | Adapters do not switch schedulers on their own | Choose an appropriate scheduler/dispatcher |
| Swallowing all errors to empty | Loses root cause and breaks contract | Preserve `onError` unless fallback is intentional |
| Wrapper retry/cancel definitely cancels side effects | Source may not support cancellation | Test end-to-end and use idempotency |
| Using RxJava 2 examples in Spring 7 | API/package is no longer the default baseline | Prefer RxJava 3 |

## 19. Checklist for integrating reactive libraries

- [ ] Identify the Spring Framework version and the library to integrate.
- [ ] Identify whether APIs work with Mono, Flux, Publisher, Future, or another type.
- [ ] Check the runtime classpath and `getAdapter`.
- [ ] Understand 0..1, 1, 0..N, or no-value semantics.
- [ ] Use `Mono.from` for single and `Flux.from` for multi.
- [ ] Prefer built-in adapters or official bridges before writing your own.
- [ ] For Observable, choose a backpressure policy and bound queues.
- [ ] For Future, understand eager evaluation and cancellation.
- [ ] For coroutines, verify dispatcher and context.
- [ ] For custom types, register descriptor + `toPublisher` + `fromPublisher`.
- [ ] Ensure any custom registry is wired into the right components if needed.
- [ ] Do not block the event-loop; handle blocking APIs on a dedicated scheduler.
- [ ] Preserve exception causes and terminal signals.
- [ ] Test empty, error, cancel, backpressure, null, and concurrency.
- [ ] Verify HTTP JSON object/array/stream via integration tests.
- [ ] Monitor latency, memory, dropped signals, and context propagation.

## 20. Self-check

**Question 1.** What is ReactiveAdapterRegistry used for?

Managing adapters that convert other reactive/async types into Reactive Streams Publishers and from Publishers back to the corresponding types.

**Question 2.** How do ReactiveAdapter and ReactiveTypeDescriptor differ?

ReactiveAdapter holds the conversion functions; the descriptor describes the reactive type and its cardinality/deferred/empty semantics.

**Question 3.** Does the registry auto-register RxJava 3 when the library is not on the classpath?

No. Default adapters are registered depending on which libraries are present on the runtime classpath.

**Question 4.** Why are Mono and Flux not completely interchangeable?

Mono carries 0..1 semantics and Flux carries 0..N semantics; cardinality affects processing, termination, and writing the HTTP response.

**Question 5.** Is a CompletableFuture always lazy when converted to Mono?

No. The CompletableFuture may have already started running before the Mono is subscribed to.

**Question 6.** How do RxJava Flowable and Observable differ in backpressure?

Flowable adheres to Reactive Streams demand; Observable lacks direct demand/backpressure like Flowable.

**Question 7.** Does Spring 7 integrate RxJava 1 and RxJava 2 by default like older releases?

Do not assume so. Spring 7.0.x documents adapter integration for RxJava 3.

**Question 8.** Why must you check if getAdapter returns null?

Because the library may be absent from the classpath or the type may not be registered.

**Question 9.** When should registerReactiveTypeOverride be used?

When you intentionally need to replace an existing adapter, after understanding exact-match/assignability precedence and thoroughly testing.

**Question 10.** Does instantiating a new registry in a service automatically apply to Spring controllers?

No. A new registry only affects code using that instance; integrating with WebFlux requires wiring it into the right components.

**Question 11.** Why shouldn't Observable be converted unconditionally to Flowable BUFFER on high-volume streams?

Because the buffer can grow very large if upstream emits faster than downstream consumes.

**Question 12.** Do Kotlin Flow and Deferred share the same integration mechanism?

Not necessarily. Deferred has a classpath-based adapter; Kotlin Flow/coroutine controllers also rely on other coroutine integration mechanisms.

**Question 13.** Does an adapter turn a blocking API into a non-blocking one on its own?

No. Blocking APIs still need an appropriate thread/scheduler or replacement with a genuinely non-blocking API.

**Question 14.** Why test cancellation and errors, not just values?

Because a flawed bridge can leak resources, swallow exceptions, or fail to cancel upstream per contract.

## 21. Official references

- [Spring Framework — Reactive Libraries](https://docs.spring.io/spring-framework/reference/web/webflux-reactive-libraries.html): reactive libraries, WebFlux annotated controllers, functional APIs, and Mono/Flux semantics.
- [ReactiveAdapterRegistry JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/ReactiveAdapterRegistry.html): default registration, `getAdapter`, `registerReactiveType`, and `registerReactiveTypeOverride`.
- [ReactiveAdapter JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/ReactiveAdapter.html): `toPublisher`/`fromPublisher`, descriptor, and cardinality metadata.
- [ReactiveTypeDescriptor JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/ReactiveTypeDescriptor.html): `multiValue`, `singleOptionalValue`, `singleRequiredValue`, `noValue`, and `nonDeferredAsyncValue` factories.
- [Spring Framework — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): reactive stack, annotated and functional endpoints.
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/): Mono, Flux, Reactive Streams, and backpressure.
- [RxJava 3 — GitHub](https://github.com/ReactiveX/RxJava): Flowable, Observable, Maybe, Single, and Completable.
- [Kotlin Coroutines — Reactor Integration](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-reactor/): bridges between coroutines and Reactor.
- [SmallRye Mutiny — Guides](https://smallrye.io/smallrye-mutiny/latest/): Uni/Multi and integration patterns.
- [Reactive Streams Specification](https://www.reactive-streams.org/): Publisher, Subscriber, Subscription, backpressure, and cancellation.
- [Spring Boot 4.1.2 release](https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/): stable Boot release used in the example.

**Key takeaway:** ReactiveAdapterRegistry is a type/semantics bridge, not a scheduler. Check the runtime classpath, identify the right cardinality, and use built-in adapters or bridges to integrate. Mono/Flux remains the clearest choice at the WebFlux boundary; custom adapters should only be registered when an external type genuinely needs framework-wide support. When switching libraries, always verify backpressure, empty/error signals, cancellation, context propagation, and blocking behavior.