# `ReactiveAdapterRegistry` and Reactive Types Supported by Spring

## 1. The problem the registry solves

In a Spring WebFlux application, a controller or an API client can return asynchronous data from many different libraries. Project Reactor provides `Mono<T>` and `Flux<T>`, but the Java ecosystem also has `CompletableFuture<T>`, JDK `Flow.Publisher<T>`, Reactive Streams `Publisher<T>`, RxJava, and Kotlin Coroutines.

If every Spring component had to write handling branches itself for each library, the code would be complex and hard to extend. **`ReactiveAdapterRegistry`** in the `org.springframework.core` package solves this by storing adapters that convert between a specific async/reactive type and the Reactive Streams `Publisher` standard.

Spring can use the registry to recognize the reactive type returned by an API, convert that type to a `Publisher` for processing in the internal pipeline, and when needed convert back to the original type.

```text
Mono<T> ----------------------┐
Flux<T> ----------------------┤
CompletableFuture<T> ---------┤
JDK Flow.Publisher<T> --------┤
RxJava type ------------------┼── ReactiveAdapterRegistry
Kotlin Deferred<T> -----------┤             |
Mutiny Uni / Multi -----------┘             |
                                            v
                                 Reactive Streams Publisher<T>
                                            |
                              Spring WebFlux / Spring APIs
```

The registry is a **type lookup and conversion mechanism**, not a scheduler, thread pool, event loop, HTTP server, or data processor. It does not turn a blocking function into a non-blocking one on its own, does not create threads, and does not start a `Publisher` just because an adapter exists.

## 2. Concepts and the three API classes

Three classes usually work together:

| Component | Role |
|---|---|
| `ReactiveAdapterRegistry` | Registers, looks up, and manages adapters by Java type |
| `ReactiveAdapter` | Performs conversion from a specific type to `Publisher` and vice versa |
| `ReactiveTypeDescriptor` | Describes value cardinality, emptiness capability, and whether the source is deferred or not |

### 2.1. `ReactiveAdapterRegistry`

Important APIs:

```java
ReactiveAdapterRegistry registry = new ReactiveAdapterRegistry();

ReactiveAdapter adapter = registry.getAdapter(Mono.class);
ReactiveAdapter bySource =
        registry.getAdapter(null, someAsyncObject);

boolean hasAdapters = registry.hasAdapters();
ReactiveAdapterRegistry shared =
        ReactiveAdapterRegistry.getSharedInstance();
```

- `new ReactiveAdapterRegistry()` creates a registry and automatically registers the default adapters usable on the current classpath.
- `getAdapter(Class<?>)` looks up an adapter by reactive type. If there is no matching adapter, the result is `null`.
- `getAdapter(Class<?>, Object)` allows supplying the type or the actual source instance for lookup. When `source` is passed, Spring can use the object's runtime type.
- `hasAdapters()` indicates whether the registry has any adapters.
- `getSharedInstance()` returns the shared default registry, lazily initialized when needed.

The Javadoc recommends passing a configured, long-lived registry when customization is needed. `getSharedInstance()` is suitable as a fallback where a default registry is needed; do not assume modifying a registry you created yourself will automatically affect every other registry in the application.

### 2.2. `ReactiveAdapter`

An adapter provides two conversion directions:

```text
Specific async/reactive type
          |
          | adapter.toPublisher(source)
          v
Reactive Streams Publisher
          |
          | adapter.fromPublisher(publisher)
          v
Specific async/reactive type
```

Commonly used methods:

```java
Publisher<?> publisher = adapter.toPublisher(source);

Object originalStyle = adapter.fromPublisher(publisher);

ReactiveTypeDescriptor descriptor = adapter.getDescriptor();

Class<?> type = adapter.getReactiveType();
boolean multiValue = adapter.isMultiValue();
boolean noValue = adapter.isNoValue();
boolean supportsEmpty = adapter.supportsEmpty();
```

- `toPublisher(source)` converts an instance of the registered type to a Reactive Streams `Publisher`.
- `fromPublisher(publisher)` converts a Publisher to the adapter's target reactive type.
- `getDescriptor()` returns the type descriptor.
- `getReactiveType()` returns the class supported by the adapter.
- `isMultiValue()`, `isNoValue()`, and `supportsEmpty()` are shortcuts for reading properties on the descriptor.

Do not treat `fromPublisher` as a conversion that always preserves all characteristics of the source. For example, if the target type only holds at most one value, converting a `Flux` with multiple elements must have a clear policy in the adapter; a single-value adapter might take only the first value or reject improper use. Preserve the semantics of both the source and target types.

### 2.3. `ReactiveTypeDescriptor`

The descriptor describes the data-emission contract of a reactive type. Important factory methods:

| Factory | Meaning | Suitable example |
|---|---|---|
| `multiValue(type, emptySupplier)` | Can emit 0..N values | Stream types such as `Flux<T>` |
| `singleOptionalValue(type, emptySupplier)` | Can emit 0..1 values | Promise types that can complete empty |
| `singleRequiredValue(type)` | Must emit exactly one value to complete | Single types requiring a result |
| `noValue(type, emptySupplier)` | Only complete/error, emits no values | Completion-only types |
| `nonDeferredAsyncValue(type, emptySupplier)` | Single-value async type triggered before/independently of subscription | `CompletableFuture<T>` |

Properties:

- `isMultiValue()`: the type can emit more than one value, fitting representations such as `Flux`.
- `isNoValue()`: the type emits no values, only complete/error.
- `supportsEmpty()`: the type can complete without emitting an element.
- `isDeferred()`: indicates whether work is deferred until a consumer subscribes/registers or has already started independently.
- `getEmptyValue()`: creates an instance representing the empty state if the descriptor supports empty.

**Choosing the right descriptor is very important.** If you declare a type that can be empty as `singleRequiredValue`, the adapter will misdescribe the contract. If a `CompletableFuture` is created and starts running immediately, do not describe it as a deferred source just because you convert it to a `Publisher` later.

## 3. Default supported reactive types

The default registered adapters **depend on the classpath and the Spring Framework version**. For Spring Framework 6.1.x, the Javadoc of `ReactiveAdapterRegistry` describes the following groups:

| Library / type | Adapter group | Condition or note |
|---|---|---|
| Project Reactor | `Mono`, `Flux`, and related adapters | Reactor is on the classpath |
| `CompletableFuture` | Single-value async | Registered together with Reactor integration |
| JDK `Flow.Publisher` | Adapter between JDK Flow and Reactive Streams | With Reactor integration; if Reactor is absent, Spring has a simple bridge for `Flow.Publisher` |
| RxJava 3 | Supported RxJava 3 reactive types | RxJava 3 is on the classpath |
| Kotlin Coroutines `Deferred` | Single-value async, bridged via Reactor | Corresponding coroutine/reactor dependencies are present |
| SmallRye Mutiny | Mutiny 1.x and 2.x in Spring 6.1.x | Mutiny is on the classpath |

From Spring 5.3.11 onward, support for RxJava 1.x and 2.x has been deprecated in favor of RxJava 3. When starting a new project, choose RxJava 3 if RxJava integration is needed.

### 3.1. Distinguishing JDK `Flow.Publisher` and Kotlin `Flow`

Two names are very easy to confuse:

- `java.util.concurrent.Flow.Publisher<T>` is a JDK interface introduced in Java 9 with its own publisher/subscriber contract in the `java.util.concurrent.Flow` package.
- `kotlinx.coroutines.flow.Flow<T>` is a stream type in Kotlin Coroutines. It has a `collect` API and coroutine-based suspension/backpressure mechanisms.

The `ReactiveAdapterRegistry` 6.1.x Javadoc explicitly lists the JDK `Flow.Publisher` bridge. Spring also supports Kotlin Coroutines `Flow` in Kotlin/WebFlux integrations when the necessary dependencies are present, but that is **Kotlin coroutine integration depending on the Spring version and component**; do not equate it with JDK `Flow.Publisher`, and do not assume every Java API treats these two types the same.

For Kotlin Coroutines, the dependencies typically required are:

```kotlin
dependencies {
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-reactor")
}
```

Spring supports `Deferred` and `Flow` in WebFlux controllers when coroutines are configured appropriately. The chosen coroutine version must be compatible with the project's Spring/Kotlin versions.

### 3.2. `CompletableFuture` does not have backpressure like `Flux`

`CompletableFuture<T>` represents a single async result. It is not a multi-element stream and does not have a `request(n)` protocol like Reactive Streams. The adapter helps Spring work with it through the Publisher abstraction, but **cannot create backpressure for a future that has already started**.

Similarly, different reactive libraries have their own semantics. RxJava `Flowable` supports backpressure, whereas `Observable` does not have a similar demand protocol. Conversion must follow how the adapter/library handles that discrepancy; you should not assume every type after adaptation has identical characteristics to `Flux`.

## 4. Where does Spring use the registry?

`ReactiveAdapterRegistry` is shared infrastructure across many Spring APIs. Some typical places:

### 4.1. WebFlux annotated controllers

Spring WebFlux can accept reactive types from controller methods and pass them into the response-processing mechanism. Example:

```java
@RestController
class PersonController {

    @GetMapping("/person")
    Mono<Person> one() {
        return Mono.just(new Person(1, "An"));
    }

    @GetMapping(value = "/people", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<Person> many() {
        return Flux.just(
                new Person(1, "An"),
                new Person(2, "Binh")
        );
    }
}
```

Reactor types are supported directly by WebFlux. For reactive types from other libraries, the registry lets the framework find an adapter to normalize how the Publisher is consumed. Then `HttpMessageWriter`/codecs are responsible for serializing the data into the HTTP response.

The adapter **does not serialize JSON** and does not decide the media type. It only helps the framework recognize and convert the async/reactive type to the appropriate abstraction.

### 4.2. WebClient request body

`WebClient` has APIs that accept a producer that can be a Publisher or another async type supported by the registry. For example, `BodyInserters.fromProducer(...)` can adapt the producer to a Publisher before writing the request body.

```java
Mono<Void> result = webClient.post()
        .uri("/people")
        .contentType(MediaType.APPLICATION_JSON)
        .body(personPublisher, Person.class)
        .retrieve()
        .bodyToMono(Void.class);
```

For a producer type that is not a Publisher but has an adapter, the appropriate body API can use `ReactiveAdapterRegistry` to convert it. If you already have a concrete object in memory rather than an async source, using `bodyValue(object)` makes the intent clearer.

### 4.3. Other Spring infrastructure

The registry is also used by components that handle method return values, messaging, and reactive integrations. When a framework component receives an unknown async type, it can ask the registry whether a corresponding adapter exists.

This lets many Spring APIs share one mechanism for recognizing reactive types instead of rewriting converters for each library.

## 5. Example checking the default adapters

The following Java 17+ program creates a default registry and checks a few types. It requires `spring-core` and `reactor-core` on the classpath.

```java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Flow;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import org.springframework.core.ReactiveAdapterRegistry;

public final class Main {
    public static void main(String[] args) {
        ReactiveAdapterRegistry registry =
                new ReactiveAdapterRegistry();

        System.out.println(
                "Mono adapter: "
                        + (registry.getAdapter(Mono.class) != null)
        );

        System.out.println(
                "Flux adapter: "
                        + (registry.getAdapter(Flux.class) != null)
        );

        System.out.println(
                "CompletableFuture adapter: "
                        + (registry.getAdapter(CompletableFuture.class) != null)
        );

        System.out.println(
                "JDK Flow.Publisher adapter: "
                        + (registry.getAdapter(Flow.Publisher.class) != null)
        );
    }
}
```

Maven structure:

```text
reactive-adapter-defaults/
├── pom.xml
└── src/main/java/demo/Main.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>reactive-adapter-defaults</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-core</artifactId>
            <version>6.1.11</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

From the project directory, run with JDK 17+ and Maven:

```bash
mvn -q compile exec:java
```

Expected stdout with exactly these two dependencies:

```text
Mono adapter: true
Flux adapter: true
CompletableFuture adapter: true
JDK Flow.Publisher adapter: true
```

This result checks that Reactor is currently on the classpath, so the registry registers the corresponding adapters. If you remove Reactor from the classpath, do not expect the same result by default for every type; the Spring 6.1.x Javadoc describes a simple JDK `Flow.Publisher` bridge when Reactor is not present.

## 6. Registering a custom reactive type yourself

If an internal library has its own async type, Spring does not automatically understand that type just because it contains a `CompletableFuture` or a Publisher inside. You can register an adapter using `registerReactiveType(...)`.

Suppose the application has an `AsyncValue<T>` type wrapping a `CompletableFuture<T>`:

```java
final class AsyncValue<T> {
    private final CompletableFuture<T> future;

    private AsyncValue(CompletableFuture<T> future) {
        this.future = future;
    }

    static <T> AsyncValue<T> from(CompletableFuture<T> future) {
        return new AsyncValue<>(future);
    }

    static AsyncValue<?> empty() {
        return new AsyncValue<>(
                CompletableFuture.completedFuture(null)
        );
    }

    CompletableFuture<T> future() {
        return future;
    }
}
```

Because the future starts independently of a subscriber calling `request`, the appropriate descriptor is `nonDeferredAsyncValue`. Two-way adapter:

```java
ReactiveAdapterRegistry registry = new ReactiveAdapterRegistry();

registry.registerReactiveType(
        ReactiveTypeDescriptor.nonDeferredAsyncValue(
                AsyncValue.class,
                AsyncValue::empty
        ),
        source -> Mono.fromCompletionStage(
                ((AsyncValue<?>) source).future()
        ),
        publisher -> AsyncValue.from(
                Mono.from(publisher).toFuture()
        )
);
```

Explanation:

1. `ReactiveTypeDescriptor.nonDeferredAsyncValue(...)` declares `AsyncValue` as a single-value async type that can be empty and is non-deferred.
2. The `toAdapter` function receives an `AsyncValue` object, gets the `CompletableFuture`, and converts it to a `Mono` with `Mono.fromCompletionStage`.
3. The `fromAdapter` function receives a Publisher and converts it back to `AsyncValue` with `Mono.from(publisher).toFuture()`.
4. `Mono.from(publisher)` matches the single-value descriptor: takes at most one value or completes empty.
5. If the future completes exceptionally, the error is preserved as an async error; if the future completes with `null`, it represents the no-value state in the way `Mono` handles a completion stage.

This is an example adapter for a **single-value type**. Do not use the same descriptor if `AsyncValue` can actually emit multiple values.

### 6.1. Complete program for the custom adapter

```java
package demo;

import java.util.concurrent.CompletableFuture;

import org.springframework.core.ReactiveAdapter;
import org.springframework.core.ReactiveAdapterRegistry;
import org.springframework.core.ReactiveTypeDescriptor;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class Main {

    static final class AsyncValue<T> {
        private final CompletableFuture<T> future;

        private AsyncValue(CompletableFuture<T> future) {
            this.future = future;
        }

        static <T> AsyncValue<T> from(CompletableFuture<T> future) {
            return new AsyncValue<>(future);
        }

        static AsyncValue<?> empty() {
            return new AsyncValue<>(
                    CompletableFuture.completedFuture(null)
            );
        }

        CompletableFuture<T> future() {
            return future;
        }
    }

    public static void main(String[] args) {
        ReactiveAdapterRegistry registry =
                new ReactiveAdapterRegistry();

        registry.registerReactiveType(
                ReactiveTypeDescriptor.nonDeferredAsyncValue(
                        AsyncValue.class,
                        AsyncValue::empty
                ),
                source -> Mono.fromCompletionStage(
                        ((AsyncValue<?>) source).future()
                ),
                publisher -> AsyncValue.from(
                        Mono.from(publisher).toFuture()
                )
        );

        ReactiveAdapter adapter =
                registry.getAdapter(AsyncValue.class);

        System.out.println("Custom adapter: " + (adapter != null));

        AsyncValue<String> input = AsyncValue.from(
                CompletableFuture.completedFuture("hello")
        );

        Object value = Mono.from(adapter.toPublisher(input)).block();
        System.out.println("toPublisher: " + value);

        AsyncValue<?> output = (AsyncValue<?>) adapter.fromPublisher(
                Flux.just("world")
        );

        System.out.println("fromPublisher: " + output.future().join());
    }
}
```

Put the code in the same `src/main/java/demo/Main.java` file of the Maven project:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>reactive-adapter-custom</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-core</artifactId>
            <version>6.1.11</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Run:

```bash
mvn -q compile exec:java
```

Stdout:

```text
Custom adapter: true
toPublisher: hello
fromPublisher: world
```

`block()` and `join()` in this program only serve to print results in the console demo. Do not call them in a WebFlux controller or inside a reactive pipeline handling requests; return a Publisher for the framework to consume.

## 7. `registerReactiveType` and `registerReactiveTypeOverride`

The two registration methods differ in priority order:

| Method | Behavior |
|---|---|
| `registerReactiveType(...)` | Registers the adapter after existing adapters; suitable when adding a new type |
| `registerReactiveTypeOverride(...)` | Registers the adapter at the head of the list to override an existing adapter for the corresponding type |

Example:

```java
registry.registerReactiveType(
        descriptor,
        source -> toPublisher(source),
        publisher -> fromPublisher(publisher)
);
```

If you need to change how an existing type is converted, you can use:

```java
registry.registerReactiveTypeOverride(
        descriptor,
        source -> customToPublisher(source),
        publisher -> customFromPublisher(publisher)
);
```

Overriding requires caution. Adapters already registered for concrete types may still be checked before a new adapter that only matches via an assignability relationship. If you want to change all subtypes, register adapters for each concrete type involved rather than relying solely on matching by superclass/interface.

Do not use override to alter application-wide behavior without first identifying every component using that registry.

## 8. Using a custom registry in Spring WebFlux

A registry you create yourself only affects code that is passed that exact instance. The following snippet **does not automatically make Spring Boot controllers accept the new type** if WebFlux is still using the default registry:

```java
ReactiveAdapterRegistry registry = new ReactiveAdapterRegistry();
registry.registerReactiveType(...);
```

To have Spring WebFlux use a custom adapter, the registry must be supplied to the WebFlux infrastructure that handles return values. In Java configuration based on `WebFluxConfigurationSupport`, the `webFluxAdapterRegistry()` bean is the common configuration point used by result handlers such as `RequestMappingHandlerAdapter`, `ResponseBodyResultHandler`, and `ResponseEntityResultHandler`.

Example of the configuration approach:

```java
@Configuration
class CustomWebFluxConfiguration extends WebFluxConfigurationSupport {

    @Override
    @Bean
    public ReactiveAdapterRegistry webFluxAdapterRegistry() {
        ReactiveAdapterRegistry registry =
                new ReactiveAdapterRegistry();

        // Register custom adapters here.
        registerApplicationAdapters(registry);

        return registry;
    }
}
```

`registerApplicationAdapters` is a method defined by the application; the snippet above illustrates the extension point, not a standalone program. If the application uses Spring Boot auto-configuration or `@EnableWebFlux`, integrate according to the project's existing configuration model and make sure the result handlers actually receive the same customized registry. Avoid declaring a separate registry bean that WebFlux does not use.

When replacing the default WebFlux configuration, you need to understand the other configuration beans that also belong to `WebFluxConfigurationSupport`; do not create an additional standalone configuration that drops existing codec, filter, exception handler, or content negotiation customizations.

## 9. What adapters do not do

`ReactiveAdapterRegistry` helps convert types, but cannot erase fundamental differences between libraries:

- **Does not create non-blocking I/O on its own.** If a `CompletableFuture` was created from a blocking call on the event loop, converting it to a Publisher does not undo the blocking that already occurred.
- **Does not create backpressure on its own.** A single-value future has no `request(n)`. An Observable type that does not support demand does not automatically become a stream with full backpressure after conversion.
- **Does not create a scheduler on its own.** Thread/scheduler selection depends on the source and operators.
- **Does not handle business errors on its own.** Exceptions in the source still need to be propagated or recovered from using operators such as `onErrorResume`.
- **Does not serialize HTTP bodies.** `HttpMessageWriter` and codecs take care of converting objects into JSON, text, or byte streams.
- **Does not guarantee preserving every library-specific semantic.** Cancellation, laziness, empty values, errors, and concurrency can differ between types.
- **Does not replace clear data types.** If an API only needs to return `Mono<T>`/`Flux<T>`, using Reactor directly is usually simpler and more consistent than creating your own reactive abstraction.

A good adapter must preserve what the source type can express, or explicitly document its policy when something cannot be preserved.

## 10. Common mistakes when using it

| Mistake | Consequence | How to handle |
|---|---|---|
| `getAdapter(type)` returns `null` yet methods are still called on it | `NullPointerException` | Check that the adapter exists; add the dependency or register an adapter |
| Assuming every library is supported automatically | Runtime cannot find an adapter | Check the Javadoc for your version and the actual classpath |
| Confusing JDK `Flow.Publisher` with Kotlin `Flow` | Choosing the wrong dependency or adapter | Distinguish packages and integrations |
| Declaring the wrong descriptor | Spring misunderstands single/multi/empty/no-value | Choose the right factory in `ReactiveTypeDescriptor` |
| Describing `CompletableFuture` as deferred | Wrong semantics: a future has usually already started before subscribe | Use `nonDeferredAsyncValue` |
| Converting a multi-value Publisher to a single-value type | Can drop elements or error due to incompatible semantics | Use a multi-value descriptor or change the target API |
| Registering only in a local registry | WebFlux still uses a different registry | Pass the registry into the right infrastructure/result handlers |
| Using `registerReactiveTypeOverride` without control | Changes adapters that other code relies on | Only override after identifying the affected types and scope |
| Wrapping a blocking call in `CompletableFuture` and thinking it is reactive | The event loop may still be blocked where the future was created | Move the blocking call to an appropriate scheduler before creating the async result |
| Creating a new registry per request | Unnecessary cost, inconsistent configuration | Create a long-lived registry per application context |
| Calling `.block()` in a controller | Blocks the thread and breaks the reactive flow | Return a Publisher for WebFlux to manage |
| Thinking the adapter handles JSON | Missing corresponding codec or wrong response format | Configure `HttpMessageReader`/`HttpMessageWriter` separately if needed |

## 11. How to check in a real project

When a reactive type does not work in a controller or WebClient, check in order:

1. Determine the **exact runtime class** of the return type. For example `CompletableFuture`, `Single`, `Flowable`, `Deferred`, or an internal wrapper.
2. Confirm the dependency containing that type is on the runtime classpath, not just the compile classpath.
3. Determine the Spring Framework version and read the corresponding Javadoc; the default adapter list can vary by version.
4. Obtain the exact registry being used by the Spring component, rather than creating another registry and inspecting only that one.
5. Call `getAdapter(returnType)` and handle the case where it returns `null`.
6. Check the descriptor: multi-value, single-value, empty, no-value, and deferred.
7. Test normal values, empty, errors, cancellation, and multi-value cases.
8. For custom adapters, test both directions `toPublisher` and `fromPublisher`.
9. For WebFlux, check whether response handlers and codecs handle the element type after adaptation.
10. Measure the blocking, concurrency, and cancellation behavior of the underlying library; the registry does not replace operational testing.

A simple diagnostic snippet:

```java
ReactiveAdapter adapter = registry.getAdapter(MyAsyncType.class);

if (adapter == null) {
    throw new IllegalStateException(
            "No reactive adapter for MyAsyncType"
    );
}

ReactiveTypeDescriptor descriptor = adapter.getDescriptor();

System.out.println("multiValue = " + descriptor.isMultiValue());
System.out.println("noValue = " + descriptor.isNoValue());
System.out.println("supportsEmpty = " + descriptor.supportsEmpty());
System.out.println("deferred = " + descriptor.isDeferred());
```

This is diagnostic code where `MyAsyncType` must be replaced with the actual class. Avoid printing whole objects or sensitive payloads in logs.

## 12. Self-check exercises

**Question 1.** What is the main responsibility of `ReactiveAdapterRegistry`?

**Answer:** Looking up and converting between specific async/reactive types and Reactive Streams `Publisher`.

**Question 2.** What can `getAdapter(UnknownType.class)` return if the registry does not support that type?

**Answer:** `null`. The caller must explicitly handle the case where no adapter exists.

**Question 3.** How do `ReactiveAdapter.toPublisher` and `fromPublisher` differ?

**Answer:** `toPublisher` converts the specific type into a Publisher; `fromPublisher` converts a Publisher into the type the adapter represents.

**Question 4.** Which descriptor fits a stream that can emit 0..N values?

**Answer:** `ReactiveTypeDescriptor.multiValue(...)`.

**Question 5.** Which descriptor fits a `CompletableFuture` that has already started running independently of subscription and may complete with no value?

**Answer:** `ReactiveTypeDescriptor.nonDeferredAsyncValue(...)`.

**Question 6.** Is JDK `Flow.Publisher` the same as Kotlin `kotlinx.coroutines.flow.Flow`?

**Answer:** No. They belong to two different packages, contracts, and ecosystems. Spring has integrations for the appropriate forms depending on version, but the dependencies/APIs must be configured correctly.

**Question 7.** If you called `registerReactiveType` on a registry you created yourself, will WebFlux automatically recognize the new type?

**Answer:** Not necessarily. That registry must be passed into the WebFlux/result-handler infrastructure processing controller return values.

**Question 8.** Does an adapter make a blocking `CompletableFuture` non-blocking?

**Answer:** No. It only converts types. Blocking that occurred beforehand is still blocking; you must choose an appropriate execution context for the original call.

## 13. Application rules

- Use `ReactiveAdapterRegistry` when Spring needs to work with multiple different async/reactive types via Reactive Streams.
- Check adapters against the **Spring version and runtime classpath**, not a generic list on the Internet.
- Use `ReactiveAdapter` for two-way conversion and `ReactiveTypeDescriptor` to describe semantics accurately.
- Choose single/multi/no-value, empty, and deferred correctly.
- Register custom types with `registerReactiveType`; use override only when you need to replace an existing adapter.
- Create a long-lived registry and pass it into the right Spring component that uses it.
- Distinguish JDK `Flow.Publisher` from Kotlin `Flow`.
- Do not expect an adapter to create a scheduler, backpressure, non-blocking I/O, or serialization.

**Key takeaway:** `ReactiveAdapterRegistry` helps Spring recognize and convert async/reactive types to Reactive Streams `Publisher`. Integration quality depends on choosing the right adapter, accurately describing the semantics of the source type, and ensuring the right registry is used where Spring handles results.

## 14. Official references

- [Spring Framework 6.1.11 — ReactiveAdapterRegistry Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/core/ReactiveAdapterRegistry.html)
- [Spring Framework 6.1.11 — ReactiveAdapter Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/core/ReactiveAdapter.html)
- [Spring Framework 6.1.11 — ReactiveTypeDescriptor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/core/ReactiveTypeDescriptor.html)
- [Spring Framework — WebFlux annotated controller return values](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html)
- [Spring Framework — Kotlin Coroutines](https://docs.spring.io/spring-framework/reference/languages/kotlin/coroutines.html)
- [Spring Framework 6.1 — WebFluxConfigurationSupport Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/reactive/config/WebFluxConfigurationSupport.html)
- [Spring Framework 6.1 — BodyInserters Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/reactive/function/BodyInserters.html)
