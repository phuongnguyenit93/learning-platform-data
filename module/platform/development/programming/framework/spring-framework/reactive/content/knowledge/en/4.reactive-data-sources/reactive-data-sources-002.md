# justOrEmpty for Potentially Absent Values (Project Reactor / Spring WebFlux)

## 1. Objectives and Problem Statement

In Java, looking up a key, reading a configuration, or integrating a legacy API may return `null` or `Optional.empty()` when no value is present. In Reactive Streams, a `Publisher` must not call `onNext(null)`. Project Reactor's `Mono.justOrEmpty(...)` turns a **potentially absent** single datum into a valid `Mono<T>` source: if an element is present, it emits that element; if not, it completes empty.

Objectives after this lesson: know how to use the two overloads accepting a nullable value and an `Optional`; distinguish empty from error; understand value evaluation timing; choose fallbacks; avoid blocking in WebFlux; and test both data-present and data-absent cases.

`Mono<T>` emits at most one element. Three main scenarios:

~~~text
Value present:  onSubscribe → onNext(value) → onComplete
Absent:         onSubscribe → onComplete
Failure:        onSubscribe → onError(cause)
~~~

**Completing empty is not an error.** `Mono.empty()` emits no `onNext`, whereas `Mono.error(...)` emits `onError`. Meanwhile, `Mono.never()` emits neither data nor a terminal signal, so it is completely different from empty.

## 2. Syntax and Mechanics

Two forms of the Reactor API:

~~~java
static <T> Mono<T> justOrEmpty(T data)
static <T> Mono<T> justOrEmpty(Optional<? extends T> data)
~~~

These are simplified signatures, omitting nullable annotations across Reactor versions. They both return `Mono<T>`, without creating a `null` element or an `Optional` wrapper inside the stream.

### 2.1. Nullable Values

~~~java
String nickname = "Linh";
Mono<String> present = Mono.justOrEmpty(nickname);

String missingNickname = null;
Mono<String> missing = Mono.justOrEmpty(missingNickname);
~~~

`present` will emit `onNext("Linh")` then `onComplete` when subscribed. `missing` only emits `onComplete`, because the passed value is `null`. You should not write `Mono.just(missingNickname)`: `just` requires non-`null` data and throws `NullPointerException` immediately upon source creation if the input is `null`.

### 2.2. Optional

~~~java
Optional<String> name = Optional.of("Mai");
Optional<String> absent = Optional.empty();

Mono<String> first = Mono.justOrEmpty(name);
Mono<String> second = Mono.justOrEmpty(absent);
~~~

With `Optional.of("Mai")`, the source emits `"Mai"`. With `Optional.empty()`, the source has no `onNext` and completes normally.

Compare two easily confused expressions:

~~~java
Mono<Optional<String>> boxed = Mono.just(Optional.empty());
Mono<String> unboxed = Mono.justOrEmpty(Optional.<String>empty());
~~~

`boxed` **still emits one element**, which is the `Optional.empty()` object. `unboxed` emits no elements. Therefore, the `map`, `zip`, `hasElement`, and fallback operators will handle the two sources differently.

### 2.3. Comparison Table

| Source Creation | Data | Result |
| --- | --- | --- |
| `Mono.just("A")` | Non-null | Emits `"A"` then completes |
| `Mono.just(null)` | Null | Throws `NullPointerException` upon source creation |
| `Mono.justOrEmpty("A")` | Non-null | Emits `"A"` then completes |
| `Mono.justOrEmpty((String) null)` | Null | Only completes |
| `Mono.justOrEmpty(Optional.of("A"))` | Non-empty Optional | Emits `"A"` then completes |
| `Mono.justOrEmpty(Optional.empty())` | Empty Optional | Only completes |
| `Mono.empty()` | Explicitly empty source | Only completes |
| `Mono.error(exception)` | Error | `onError` |

If you pass a `null` literal directly, the overloads can make type inference ambiguous. When demonstrating, use a typed variable or a cast such as `(String) null`. Do not use `null` as an element sent down to a Subscriber.

## 3. Complete Example with Java 17+ and Reactor

The following example uses synchronous `Mono` sources for deterministic output. In a Spring Boot project that already has `spring-boot-starter-webflux`, you can run the class from your IDE with Reactor on the classpath. Or create a small Gradle project:

~~~text
just-or-empty-demo/
├── build.gradle
└── src/main/java/JustOrEmptyDemo.java
~~~

Contents of `build.gradle` (using Gradle with Java toolchain support):

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.8'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'JustOrEmptyDemo'
}
~~~

Contents of `src/main/java/JustOrEmptyDemo.java`:

~~~java
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;

import reactor.core.publisher.Mono;

public class JustOrEmptyDemo {

    private static void observe(String label, Mono<String> mono) {
        System.out.println("[" + label + "]");
        mono.subscribe(
                value -> System.out.println("onNext=" + value),
                error -> System.out.println(
                        "onError=" + error.getClass().getSimpleName()),
                () -> System.out.println("onComplete")
        );
    }

    public static void main(String[] args) {
        observe("present", Mono.justOrEmpty("Linh"));
        observe("null", Mono.justOrEmpty((String) null));
        observe("optional", Mono.justOrEmpty(Optional.of("Mai")));
        observe("optional empty",
                Mono.justOrEmpty(Optional.<String>empty()));

        observe("default", Mono.justOrEmpty((String) null)
                .defaultIfEmpty("Guest"));

        observe("required", Mono.justOrEmpty((String) null)
                .switchIfEmpty(
                    Mono.error(new IllegalArgumentException("missing"))));

        AtomicReference<String> value = new AtomicReference<>("before");
        Mono<String> snapshot = Mono.justOrEmpty(value.get());
        Mono<String> fresh = Mono.defer(
                () -> Mono.justOrEmpty(value.get()));
        value.set("after");

        observe("snapshot", snapshot);
        observe("fresh", fresh);
    }
}
~~~

Run in the directory containing `build.gradle` with Gradle installed; if the project has a wrapper, replace `gradle` with `./gradlew`:

~~~bash
gradle -q run
~~~

The **program's** stdout lines (excluding Gradle logs):

~~~text
[present]
onNext=Linh
onComplete
[null]
onComplete
[optional]
onNext=Mai
onComplete
[optional empty]
onComplete
[default]
onNext=Guest
onComplete
[required]
onError=IllegalArgumentException
[snapshot]
onNext=before
onComplete
[fresh]
onNext=after
onComplete
~~~

There is no `onNext=null` line in any case. `required` emits an error, so it does not invoke the `onComplete` callback. In these synchronous sources, callbacks run in the order shown above. Do not apply that assumption to log ordering across multiple concurrently active subscriptions or sources with different schedulers.

## 4. When Is the Value Read: Eager Snapshot vs. Lazy Lookup

Writing:

~~~java
Mono<String> source = Mono.justOrEmpty(readCurrentNickname());
~~~

causes Java to call `readCurrentNickname()` **immediately when evaluating the expression** to build the source. `justOrEmpty` receives an already-computed value and does not defer work by itself. Every subsequent subscription sees the stored snapshot (or sees an empty source).

This is demonstrated in the example above: the initial value is `"before"`, then changed to `"after"`. `snapshot` still emits `"before"` while `fresh` emits `"after"`, because it re-reads via `Mono.defer` upon subscription.

When you want to fetch data at subscription time, there are several options:

~~~java
// These illustrative snippets assume readCurrentNickname() already exists.
Mono<String> fromSupplier =
        Mono.fromSupplier(() -> readCurrentNickname());

Mono<String> fromCallable =
        Mono.fromCallable(() -> readCurrentNickname());

Mono<String> fromDefer =
        Mono.defer(() -> Mono.justOrEmpty(readCurrentNickname()));
~~~

- `fromSupplier` invokes the `Supplier` on subscribe; a `null` result is interpreted as an empty Mono.
- `fromCallable` runs the `Callable` on subscribe; a `null` result is empty, and an exception from the Callable becomes `onError`.
- `defer` lets you defer **choosing or creating an entire Mono**, which is very useful when each subscription needs a different source.
- `justOrEmpty` is suitable when you already have a `nullable T`/`Optional<T>` in hand, such as a value read immediately from memory.

**Laziness does not mean running asynchronously or non-blocking.** Lazy factories by default do not move blocking I/O operations to another thread. If a lookup needs to wait on synchronous JDBC, files, or HTTP, you must consider the appropriate scheduler and architecture.

## 5. What Happens to Operators When a Mono Is Empty?

Example:

~~~java
Mono<String> result =
        Mono.justOrEmpty((String) null)
            .map(String::trim)
            .doOnNext(System.out::println);
~~~

Because there is no element, `map` does not call `String.trim` and `doOnNext` prints nothing. Similarly, `flatMap`, `filter`, or `zipWhen` branches that require an input element will not produce new data from an empty source if no replacement source is provided.

Specifically:

- `doOnNext` only runs when an element is emitted.
- `Mono`'s `doOnSuccess` **still runs on empty completion**; the callback parameter is `null` in this case. Do not use `doOnSuccess(value -> value.toString())` without handling `value == null`.
- `Mono.zip(a, b)` needs data from both sources to produce a result; if one Mono is empty, there is no complete pair of values to emit. Do not assume zip will wait or emit a partial result.
- `Mono.empty()` has already emitted a normal completion signal, unlike `Mono.never()` which never terminates.
- `block()` in tests may return `null` when a Mono is empty, but `block()` should not be used in WebFlux HTTP processing flows.

Before choosing an operator, clearly identify the semantics: `nullable input → empty`, `empty → fallback`, `error → exception handling`.

## 6. Handling the Case of No Value

### 6.1. A Fallback Value: defaultIfEmpty

~~~java
Mono<String> displayName =
        Mono.justOrEmpty((String) null)
            .defaultIfEmpty("Guest");
~~~

When the source is empty, the result emits `"Guest"`. When the source has a value, the original value is preserved. Suitable for display names, optional labels, or configurations with valid defaults.

### 6.2. A Fallback Source: switchIfEmpty

~~~java
// primaryName and backupLookup() are provided by the application.
Mono<String> displayName =
        Mono.justOrEmpty(primaryName)
            .switchIfEmpty(
                Mono.defer(() -> backupLookup())
            );
~~~

`switchIfEmpty` subscribes to the fallback Mono **only when the primary source completes empty**. It does not run to handle `onError`. Use `Mono.defer` if the fallback source should only be **created or computed** when data is genuinely missing, avoiding expensive work while assembling the pipeline.

### 6.3. Missing Data Is a Business Error: switchIfEmpty + error

~~~java
Mono<String> requiredName =
        Mono.justOrEmpty((String) null)
            .switchIfEmpty(
                Mono.error(new IllegalArgumentException("name required"))
            );
~~~

The result is now `onError(IllegalArgumentException)`. This decision depends on business logic; not finding an optional nickname may be normal, whereas missing a required identifier may need to be converted into an error.

### 6.4. Error Differs from Empty

`onErrorResume` and `onErrorReturn` are mechanisms for handling **error signals**; they do not run when `Mono.justOrEmpty(null)` completes empty. Conversely, `defaultIfEmpty` and `switchIfEmpty` handle **missing elements**, and do not mask errors arising from connections, timeouts, or validation.

Purpose table:

| Need | Operator |
| --- | --- |
| Missing value -> use a default element | `defaultIfEmpty(value)` |
| Missing value -> try another source | `switchIfEmpty(fallbackMono)` |
| Missing value -> report a business error | `switchIfEmpty(Mono.error(...))` |
| Source actually emits an error and needs recovery | `onErrorResume(...)` |

## 7. Practical Application in Spring WebFlux

### 7.1. In-Memory Cache: Turning a Nullable Result into HTTP 200/404

The controller snippet below is placed **inside a Spring Boot WebFlux project**, not a standalone `main` application:

~~~java
import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
class AliasController {
    private final Map<String, String> aliases = Map.of(
            "u1", "Linh",
            "u2", "Mai"
    );

    @GetMapping("/aliases/{id}")
    Mono<ResponseEntity<String>> findAlias(@PathVariable String id) {
        return Mono.justOrEmpty(aliases.get(id))
                .map(ResponseEntity::ok)
                .defaultIfEmpty(ResponseEntity.notFound().build());
    }
}
~~~

`Map.get(id)` returns `null` when the key is absent, so `Mono.justOrEmpty` creates an empty source. The `map` branch does not run; `defaultIfEmpty` creates a 404 response. When the key exists, the `map` branch returns 200 with the name.

~~~text
GET /aliases/u1       → HTTP 200, body: Linh
GET /aliases/missing  → HTTP 404, empty body
~~~

Do not call `subscribe()` or `block()` yourself in the controller: Spring WebFlux takes the Publisher and manages the subscription when processing the request.

### 7.2. Already-Reactive Repository: Do Not Re-wrap

A reactive data repository may return `Mono<User>` directly:

~~~java
// Illustrative snippet; User and repository belong to the application:
Mono<User> user = reactiveUserRepository.findById(id);
~~~

Use this `Mono<User>` directly and chain the necessary operators onto it. Wrapping it with `Mono.justOrEmpty(user)` creates a nested `Mono<Mono<User>>` source or breaks the expected type. With a reactive API, there is no need to force data back into `Optional` just to call `justOrEmpty`.

### 7.3. Adapting Legacy Blocking APIs with fromCallable and a Scheduler

Suppose `legacyRepository.findById(id)` accesses synchronous JDBC and returns `Optional<User>`. The following approach will block immediately when assembling the pipeline (dangerous on the event loop):

~~~java
Mono<User> wrong =
        Mono.justOrEmpty(legacyRepository.findById(id));
~~~

If you cannot yet replace it with a reactive client/database driver, you can create a safer boundary:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

// Illustrative snippet; User, id, and legacyRepository exist in the application.
Mono<User> user =
        Mono.fromCallable(
                () -> legacyRepository.findById(id).orElse(null))
            .subscribeOn(Schedulers.boundedElastic());
~~~

`fromCallable` waits until subscription to execute the lookup; `subscribeOn(boundedElastic())` schedules the potentially blocking operation onto an appropriate scheduler. When not found, the callable returns `null`, so it completes empty; when the DAO throws an exception, the source emits `onError`. Bounded elastic is only a bridge for blocking APIs and does not make JDBC operations truly non-blocking I/O.

## 8. Testing Behavior with StepVerifier

In a project with `reactor-test` and JUnit 5 in test scope, you can verify directly:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class JustOrEmptyTest {

    @Test
    void presentEmitsOneValue() {
        StepVerifier.create(Mono.justOrEmpty(Optional.of("Linh")))
                .expectNext("Linh")
                .verifyComplete();
    }

    @Test
    void nullCompletesAndMapDoesNotRun() {
        AtomicInteger calls = new AtomicInteger();
        Mono<String> source = Mono.justOrEmpty((String) null)
                .map(value -> {
                    calls.incrementAndGet();
                    return value.toUpperCase();
                });

        StepVerifier.create(source).verifyComplete();
        assertEquals(0, calls.get());
    }

    @Test
    void emptyOptionalUsesFallback() {
        StepVerifier.create(
                    Mono.justOrEmpty(Optional.<String>empty())
                        .defaultIfEmpty("Guest"))
                .expectNext("Guest")
                .verifyComplete();
    }

    @Test
    void missingCanBecomeError() {
        StepVerifier.create(
                    Mono.justOrEmpty((String) null)
                        .switchIfEmpty(
                            Mono.error(new IllegalArgumentException("missing"))))
                .expectError(IllegalArgumentException.class)
                .verify();
    }
}
~~~

`verifyComplete()` on an empty Mono proves there is no `onNext` while `onComplete` still occurs. `expectNext` checks the exact single value. `expectError` confirms that converting absence into an error actually emits `onError`, not completion.

## 9. Common Mistakes and Fixes

| Mistake | Why It Is Wrong | Right Approach |
| --- | --- | --- |
| `Mono.just(nullable)` | Throws NPE when input is null. | `Mono.justOrEmpty(nullable)` if a missing value is valid. |
| `Mono.just(Optional.empty())` expecting an empty source | Mono emits an Optional object. | `Mono.justOrEmpty(optional)` to unbox. |
| `Mono.justOrEmpty(expensiveLookup())` thinking lookup runs later | The argument is evaluated before the factory call. | `fromSupplier`/`fromCallable` or `defer`. |
| Expecting `map` to receive null to handle itself | Empty does not trigger `map`. | `defaultIfEmpty` / `switchIfEmpty` for absence. |
| Using `onErrorResume` to handle empty | Empty completion is not an error. | Choose an empty-handling operator. |
| Using `doOnSuccess(v -> v.length())` unconditionally | `v` is null when Mono is empty. | Check for null or use `doOnNext` when a real element is needed. |
| `Mono.justOrEmpty(mono)` when input is already a Mono | Creates a nested Mono and breaks pipeline semantics. | Chain operators onto the original Mono. |
| Putting a blocking lookup in `justOrEmpty` in WebFlux | Blocking already happened before subscribe, potentially blocking the event loop. | Reactive API or `fromCallable(...).subscribeOn(boundedElastic())`. |
| Treating missing data as equivalent to an exception | Breaks optional processing flows. | Clearly distinguish absent conditions and error conditions per business rules. |

To observe, add `.log("lookup")` to the source before subscribing. With null input, the log will show a terminal `onComplete` with no `onNext`. When diagnosing data-read timing bugs, remember to distinguish pipeline *assembly* time from *subscribe* time.

## 10. Self-Check

1. What signal does `Mono.justOrEmpty((String) null)` emit? **Only `onComplete`.**
2. Is `Mono.just(Optional.empty())` empty? **No; it emits an `Optional.empty()` as a value.**
3. Does `Mono.justOrEmpty(cache.get(key))` call `cache.get` on every subscribe? **No; the call happens when building the Mono.**
4. If the source is empty, does `map(String::trim)` run? **No.**
5. When data is missing and you want to call a fallback API, which operator should you choose? **`switchIfEmpty`; add `defer` if you need to defer creating the fallback source.**
6. If a lookup throws an exception, does `defaultIfEmpty` recover from it? **No; it only handles empty completion.**
7. Does `fromCallable` automatically move a blocking JDBC call off the event loop? **No; you must arrange a scheduler or use a truly non-blocking API.**

**Key takeaway:** `Mono.justOrEmpty` is the bridge between Java's `null` / `Optional.empty()` and a Reactive Streams source with **0 or 1 element**. If a value is present, it emits `onNext` and completes; if absent, it completes empty. When read timing or the blocking nature of the source is the issue, use lazy factories and an appropriate scheduler, while keeping empty-handling and error-handling logic separate.

## References

- [Project Reactor Mono Javadoc — justOrEmpty, fromSupplier, fromCallable, doOnSuccess](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html).
- [Project Reactor Reference Guide — Which operator do I need?](https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html).
- [Reactive Streams JVM specification](https://github.com/reactive-streams/reactive-streams-jvm).
- [Spring Framework WebFlux Reference](https://docs.spring.io/spring-framework/reference/web/webflux.html).
