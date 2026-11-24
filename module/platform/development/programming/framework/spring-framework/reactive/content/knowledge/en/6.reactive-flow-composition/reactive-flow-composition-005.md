# `defaultIfEmpty` and `switchIfEmpty` in Reactor

In **Spring WebFlux** and **Project Reactor**, a `Mono<T>` or `Flux<T>` can **complete successfully without emitting any elements**. The two operators `defaultIfEmpty` and `switchIfEmpty` handle that exact case, yet they do two different things:

- **`defaultIfEmpty(defaultValue)`**: if the source is empty, emit **a single default value** that was provided; if the source has data, keep the source's elements unchanged.
- **`switchIfEmpty(alternatePublisher)`**: if the source is empty, **switch to subscribing to a fallback publisher**; that publisher can perform its own asynchronous work and emit 0, 1, or multiple elements depending on its type.

Both trigger the fallback only when **the source completes without any `onNext`**. Neither catches errors automatically, retries automatically, or decides HTTP 404/204 on behalf of your application.

## 1. Learning Objectives

After this lesson, you can:

1. Identify an **empty** stream via Reactive Streams signals and distinguish it from a `null` element, an error, or a source that never completes.
2. Choose `defaultIfEmpty` when you have a replacement value, or `switchIfEmpty` when you have an alternative operation or data source.
3. Explain when the fallback publisher is constructed and when it is **subscribed to**, using `Mono.defer` when publisher construction must be deferred.
4. Understand the scope of these operators on `Mono` and `Flux`, as well as the effects of `filter`, `flatMap`, `then`, and `Mono<Void>`.
5. Apply missing-data handling in Spring WebFlux, distinguishing empty data from HTTP 4xx/5xx errors.
6. Test non-empty, empty, error, and demand branches using `StepVerifier`.

## 2. What Does “Empty” Mean in Reactive Streams?

Reactor is built on the `Publisher`/`Subscriber` model. A publisher can send the following signals:

~~~text
With data:  onSubscribe -> onNext(value) -> onComplete
Empty:      onSubscribe ---------------------> onComplete
Errored:    onSubscribe ---------------------> onError(error)
Cancelled:  subscriber calls cancel() (not equivalent to onComplete)
~~~

For a `Mono<T>`, the number of successful elements is 0 or 1. For a `Flux<T>`, the count is 0 to many, potentially unbounded if the source never terminates.

**Empty is a terminal state of a publisher:** completing successfully **with no `onNext`**. A source waiting forever such as `Mono.never()` is not a publisher that completed empty. A source signaling failure via `onError` is also not a publisher that completed empty.

`null` is not a valid element in Reactor `onNext` signals:

~~~java
Mono<String> none = Mono.empty();            // Empty: valid.
String nullable = null;
Mono<String> optional = Mono.justOrEmpty(nullable); // Empty: valid.
Mono<String> invalid = Mono.just(null);     // Wrong: NullPointerException.
~~~

The last line **intentionally illustrates an error**; do not put it in runnable code. Use `Mono.justOrEmpty(value)` when converting a nullable Java value into a 0-or-1-element publisher; never emit `null` directly.

The table below clarifies how each operator behaves:

| Source | Source signals | `defaultIfEmpty("guest")` | `switchIfEmpty(Mono.just("guest"))` |
| --- | --- | --- | --- |
| `Mono.just("Alice")` | `onNext("Alice")`, `onComplete` | Emits `"Alice"` | Emits `"Alice"`, does not subscribe fallback |
| `Mono.empty()` | `onComplete` | Emits `"guest"`, then completes | Subscribes fallback, emits `"guest"`, then completes |
| `Mono.error(ex)` | `onError(ex)` | Still emits error `ex` | Still emits error `ex` |
| `Mono.never()` | No terminal signal | Produces no default value | Does not switch to fallback |

“Non-empty source” simply requires **at least one** `onNext` before completion. With `Flux.just("A", "B")`, both operators pass `"A"`, `"B"`, and completion through normally.

## 3. `defaultIfEmpty`: Replacing an Empty Source with a Single Value

Common syntax:

~~~java
Mono<String> displayName = Mono.<String>empty()
    .defaultIfEmpty("Guest");

Flux<Integer> numbers = Flux.<Integer>empty()
    .defaultIfEmpty(0);
~~~

The results are a `Mono` emitting `"Guest"` and a `Flux` emitting a single element `0`, respectively.

If the source is not empty, `defaultIfEmpty` adds no extra data:

~~~java
Flux<Integer> original = Flux.just(2, 4, 6);
Flux<Integer> result = original.defaultIfEmpty(0);
// Result: 2, 4, 6 — no 0 element is appended.
~~~

**Characteristics:**

- Only needs a fallback **value**, without an extra repository or HTTP call.
- The default value must match type `T` and cannot be `null`.
- If the fallback value is produced by a method call, the argument expression is evaluated by Java **immediately when assembling the pipeline**. Thus `defaultIfEmpty(expensiveValue())` can execute costly work even when the source has data. When the fallback requires asynchronous computation or should only be built when needed, use `switchIfEmpty` with a lazy source.
- If the source errors, the error is forwarded. If the source never completes, the default value never appears.
- When the source is empty and downstream has not requested an element yet, the default value must wait for sufficient demand before being emitted; normal completion does not consume an element of demand.

Example where a user has no display name:

~~~java
Mono<String> shownName = userRepository.findById(userId)
    .map(User::displayName)
    .defaultIfEmpty("Anonymous user");
~~~

This is an **integration snippet**, with `User` and `userRepository` defined by the application. It is appropriate if the business contract allows showing a default value when the user is not found (or when transformation steps return an empty publisher). If “not found” must raise an error, see section 9.

### Effect of preceding operators

A publisher that originally had data can still become **empty after filtering**:

~~~java
Mono<Integer> source = Mono.just(3);

Mono<Integer> result = source
    .filter(n -> n % 2 == 0)
    .defaultIfEmpty(-1);

// result emits -1, because filter drops element 3.
~~~

`defaultIfEmpty` checks the **signal stream at its exact position**, not whether the original source ever contained an element. Placing it before or after `filter` can produce different results:

~~~java
Mono<Integer> a = Mono.<Integer>empty()
    .defaultIfEmpty(3)
    .filter(n -> n % 2 == 0);   // Empty: 3 is filtered out.

Mono<Integer> b = Mono.<Integer>empty()
    .filter(n -> n % 2 == 0)
    .defaultIfEmpty(3);         // Emits 3.
~~~

That is why you must read a pipeline sequentially from top to bottom rather than treating `defaultIfEmpty` as an application-wide rule.

## 4. `switchIfEmpty`: Switching to a Fallback Publisher

When a constant cannot substitute and you need to read from a cache, query another service, or invoke a reactive operation, use `switchIfEmpty`:

~~~java
Mono<User> user = primaryRepository.findById(id)
    .switchIfEmpty(backupRepository.findById(id));
~~~

This is an integration snippet. If the publisher from the primary store emits a user, the fallback source **is not subscribed to**. If the primary store **completes empty**, Reactor subscribes to the fallback publisher and takes signals from it. If the primary store reports an error, `switchIfEmpty` does **not** treat that error as “not found”.

### How do `switchIfEmpty` and `defaultIfEmpty` differ?

| Criterion | `defaultIfEmpty(value)` | `switchIfEmpty(publisher)` |
| --- | --- | --- |
| Argument | One valid value of type `T` | A suitable `Publisher<? extends T>` |
| Output when source is empty | Emits exactly one fallback value | Emits signals from the fallback publisher |
| Can call another async source? | Not directly | Yes, when the fallback publisher is subscribed to |
| Can a fallback `Flux` emit multiple elements? | No, only one value | Yes, the fallback publisher can emit multiple elements |
| Original source emits `onNext`? | Keeps source data | Does not subscribe to the fallback publisher |
| Original source emits `onError`? | Propagates error | Propagates error |
| Replaces `onErrorResume`? | No | No |

When the source is an empty `Flux`, the fallback can be an entire Flux:

~~~java
Flux<String> events = Flux.<String>empty()
    .switchIfEmpty(Flux.just("cached-A", "cached-B"));
// Emits cached-A, cached-B.
~~~

Meanwhile:

~~~java
Flux<String> events = Flux.<String>empty()
    .defaultIfEmpty("cached-A");
// Emits only cached-A.
~~~

Remember: `switchIfEmpty` **switches sources only once when the first source completes empty**; it is not a mechanism to “switch per missing element”, does not check each key in a list, and does not automatically retry across multiple publishers.

## 5. Important: Lazy Publishers and When the Fallback Is Built

A common misconception is: “`switchIfEmpty` only runs the fallback-creation code when the source is empty”. More accurately, separate **two moments**:

1. **Creating the publisher object:** Java evaluates the expression passed to `switchIfEmpty(...)` immediately when you assemble the pipeline.
2. **Subscribing to the fallback publisher:** `switchIfEmpty` only subscribes to it when the primary source completes empty.

For Reactor publishers built lazily, constructing the object typically performs no immediate I/O; however, side effects inside a publisher-building method can happen right at assembly time.

Example of **what not to do** when `createBackupNow()` has costly side effects:

~~~java
Mono<String> result = primary
    .switchIfEmpty(Mono.just(createBackupNow()));
// createBackupNow() is executed by Java right when this line runs,
// even if primary later emits data.
~~~

This is an illustrative snippet with `primary` and `createBackupNow()` defined by the application. If you do not want to compute the fallback value when the primary source has data, defer its creation:

~~~java
Mono<String> result = primary
    .switchIfEmpty(Mono.defer(
        () -> Mono.just(createBackupNow())
    ));
~~~

`Mono.defer` takes a supplier that creates a new `Mono` **when the deferred publisher is subscribed to**. Combined with `switchIfEmpty`, this supplier is invoked only when execution actually enters the fallback branch.

If `createBackupNow()` performs **blocking** I/O, putting it inside `Mono.defer` only defers when it is called; it **does not automatically move blocking I/O onto an appropriate thread**. When you must call a blocking API, consider `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` with concurrency bounds; in WebFlux, prefer non-blocking reactive APIs.

A repository-based form:

~~~java
Mono<User> user = cache.find(id)
    .switchIfEmpty(Mono.defer(
        () -> repository.findById(id)
    ));
~~~

Constructing the repository publisher is deferred until the fallback is needed. If `repository.findById(id)` already returns a cold publisher and the builder method has no side effects, you can pass it directly; `defer` is the clear choice when you want to control when the publisher is **created** or read state as of subscription time.

**Remember:** `switchIfEmpty` already makes **subscribing** to the fallback conditional; `defer` also makes **creating** the fallback publisher conditional.

## 6. Runnable Java 17 Example with Deterministic Stdout

Create a simple Gradle project with Reactor Core.

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.6.8'
    testImplementation 'io.projectreactor:reactor-test:3.6.8'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.3'
}

application {
    mainClass = 'EmptyFallbackDemo'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

File `src/main/java/EmptyFallbackDemo.java`:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class EmptyFallbackDemo {
    public static void main(String[] args) {
        Mono<String> defaultValue = Mono.<String>empty()
            .defaultIfEmpty("anonymous");

        System.out.println("default = " + defaultValue.block());

        Mono<String> primary = Mono.<String>empty()
            .doOnSubscribe(s -> System.out.println("subscribe primary"))
            .doOnTerminate(() -> System.out.println("primary completed"));

        Mono<String> backup = Mono.defer(() -> {
            System.out.println("create fallback");
            return Mono.just("backup");
        });

        Mono<String> chosen = primary.switchIfEmpty(backup);

        System.out.println("before switch subscription");
        System.out.println("switch = " + chosen.block());

        Flux<String> sequence = Flux.<String>empty()
            .switchIfEmpty(Flux.just("cached", "default"));

        System.out.println("flux = " + sequence.collectList().block());

        Mono<String> present = Mono.just("live")
            .switchIfEmpty(Mono.defer(() -> {
                System.out.println("unexpected fallback");
                return Mono.just("backup");
            }));

        System.out.println("present = " + present.block());
    }
}
~~~

Run from the project directory using `gradle run`. If Gradle Wrapper is present, use `./gradlew run` (on Windows: `gradlew.bat run`). Stdout printed by the program, excluding Gradle logs:

~~~text
default = anonymous
before switch subscription
subscribe primary
primary completed
create fallback
switch = backup
flux = [cached, default]
present = live
~~~

**Explanation in order:**

1. `defaultValue.block()` subscribes to the empty Mono, so `defaultIfEmpty` emits `"anonymous"`.
2. Creating the `chosen` variable does not subscribe to the pipeline yet, so `before switch subscription` appears before the primary source's logs.
3. When `chosen.block()` subscribes, the primary source prints two lines: subscribed, then completed empty.
4. Only afterward does `switchIfEmpty` subscribe to `backup`; the `Mono.defer` supplier prints `create fallback` and returns `Mono.just("backup")`.
5. For the empty `Flux`, the fallback emits **two elements**, which `collectList()` collects into a list. Because this is a finite source, collecting into a list is safe.
6. `present` emits `"live"`; the fallback **is not subscribed to**, so `unexpected fallback` does not appear.

`block()` in this example is used only in a **command-line application** to print results synchronously. In a Spring WebFlux controller/service running on the event loop, return the publisher for WebFlux to subscribe to; never call `block()` inside a handler.

The Reactor version was chosen so the standalone project is reproducible. In a Spring Boot project, let the Spring Boot BOM manage compatible Reactor dependencies rather than pinning a version separately from this example.

## 7. Error Cases: Empty Differs from Error

Example:

~~~java
Mono<String> failed = Mono.<String>error(
    new IllegalStateException("database unavailable")
);

Mono<String> result = failed.switchIfEmpty(Mono.just("cached"));
// result still emits onError(IllegalStateException).
~~~

`switchIfEmpty` does not handle errors because upstream did not end with an empty `onComplete`. `defaultIfEmpty` behaves the same way.

To route an error to a fallback publisher, use `onErrorResume` when **business rules genuinely permit it**:

~~~java
Mono<String> recovered = failed.onErrorResume(
    error -> Mono.just("cached")
);
~~~

If both policies are needed:

~~~java
Mono<String> resolved = source
    .switchIfEmpty(Mono.defer(() -> lookupSecondary()))
    .onErrorResume(error -> recoverFromFailure(error));
~~~

This is an integration snippet: `source`, `lookupSecondary`, and `recoverFromFailure` are defined by the application with compatible `Mono<String>` return types. Behavior:

- Primary source has a value: use that value.
- Primary source is empty: try the secondary source.
- Primary or secondary source emits an error: `onErrorResume` handles the error per policy.

**Operator order changes meaning.** If you write:

~~~java
Mono<String> resolved = source
    .onErrorResume(error -> Mono.empty())
    .switchIfEmpty(Mono.just("cached"));
~~~

Any error converted by `onErrorResume` into an empty completion triggers `switchIfEmpty`; in other words, errors are turned into “no data”. This approach can hide severe database/network failures. Distinguish “not found” (empty) from “system failure” (error) before deciding how to recover.

### Cancellation is not empty

When a subscriber cancels a `Subscription`, that does not make `switchIfEmpty` run its fallback. The fallback is selected only after receiving an empty completion signal from upstream. If a publisher hangs, add an appropriate timeout:

~~~java
Mono<String> bounded = source
    .timeout(java.time.Duration.ofSeconds(3))
    .switchIfEmpty(Mono.just("not-found"));
~~~

In the example above, a timeout produces **`onError`**, not an empty completion, so `not-found` is not emitted simply on timeout. If business logic needs to turn a timeout into another value or publisher, configure `onErrorResume` conditionally for that error type.

## 8. With `Flux`: Fallback Triggers Only When the Entire Source Emits Zero Elements

A `Flux` can emit multiple elements before completing. These two operators do not check individual elements; they check **whether the entire source has ever emitted any element**:

~~~java
Flux<String> main = Flux.just("A", "B");

Flux<String> withDefault = main.defaultIfEmpty("X");
Flux<String> withBackup = main.switchIfEmpty(Flux.just("X", "Y"));

// Both emit only A, B.
~~~

With a source that becomes empty after filtering:

~~~java
Flux<Integer> even = Flux.just(1, 3, 5)
    .filter(n -> n % 2 == 0)
    .switchIfEmpty(Flux.just(2, 4));

// even emits 2, 4, because filter dropped all elements.
~~~

If even a single element passes the filter, the fallback is not subscribed to:

~~~java
Flux<Integer> even = Flux.just(1, 2, 3)
    .filter(n -> n % 2 == 0)
    .switchIfEmpty(Flux.just(4, 6));

// Emits only 2; does not emit 4 or 6.
~~~

**Do not use `switchIfEmpty` to automatically fill in “missing IDs” in a list.** If a Flux contains results for ID 1 and ID 3 while missing ID 2, it is still a **non-empty** Flux. To handle each ID individually, create a separate publisher per key:

~~~java
Flux<User> users = Flux.fromIterable(userIds)
    .concatMap(id -> repository.findById(id)
        .switchIfEmpty(Mono.defer(() -> backupRepository.findById(id))));
~~~

The snippet above is an integration example: `userIds`, `User`, and the repositories must be declared. It applies fallback **per individual ID** because each `findById(id)` returns a separate `Mono`. `concatMap` preserves input order for the emitted results while subscribing to each inner publisher sequentially. If you want multiple async lookups to run concurrently, consider `flatMap` with appropriate concurrency and accept that output order may vary.

## 9. Applying in Spring WebFlux: Found, Not Found, and Fallback

Suppose an endpoint looks up a profile by ID using a reactive repository. When the repository returns `Mono.empty()` because no record exists, the API typically needs HTTP **404 Not Found**. You can use `switchIfEmpty(Mono.error(...))`:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
public class ProfileController {
    private final ProfileRepository repository;

    public ProfileController(ProfileRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/profiles/{id}")
    public Mono<ProfileDto> getProfile(@PathVariable String id) {
        return repository.findById(id)
            .map(profile -> new ProfileDto(
                profile.id(), profile.displayName()
            ))
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Profile not found"
                )
            ));
    }
}
~~~

This is a **Spring WebFlux integration snippet**, not a self-running Java file: the application needs `spring-boot-starter-webflux`, a `ProfileRepository` returning `Mono<Profile>`, and the corresponding `ProfileDto` type. If you do not have a DTO yet, you can use:

~~~java
public record ProfileDto(String id, String displayName) {}
~~~

API behavior:

- Repository emits a profile: `map` transforms it into `ProfileDto`, and WebFlux serializes the response.
- Repository completes empty: `switchIfEmpty` selects `Mono.error` so WebFlux translates `ResponseStatusException` into a 404.
- Repository reports an I/O error: the original error propagates; it is **not** turned into a 404.

If you want to check fallback data before returning 404:

~~~java
public Mono<ProfileDto> getProfile(String id) {
    return repository.findById(id)
        .switchIfEmpty(Mono.defer(() -> cache.findById(id)))
        .map(profile -> new ProfileDto(
            profile.id(), profile.displayName()
        ))
        .switchIfEmpty(Mono.error(
            new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Profile not found"
            )
        ));
}
~~~

This is an illustrative method inside a service/controller with `repository`, `cache`, and `ProfileDto` declared. The cache source is subscribed to only if the repository completes empty. Only when both are empty is 404 emitted. The evaluation and fallback order is expressed directly in the pipeline.

### Watch out for WebClient and HTTP 404

A WebClient call using `retrieve().bodyToMono(...)` converts HTTP **4xx/5xx** into **error signals** by default, rather than turning every 404 into `Mono.empty()`:

~~~java
Mono<ProfileDto> remote = webClient.get()
    .uri("/profiles/{id}", id)
    .retrieve()
    .bodyToMono(ProfileDto.class);
~~~

Therefore:

~~~java
Mono<ProfileDto> incorrectAssumption = remote
    .switchIfEmpty(cache.findById(id));
~~~

In the snippet above (assuming `webClient` and `cache` exist), the fallback triggers only when the HTTP response is interpreted as an empty Mono, **not when WebClient raises its default 404 error**. If the application contract treats 404 as “no data”, convert that specific error type to empty before falling back:

~~~java
import org.springframework.web.reactive.function.client.WebClientResponseException;

Mono<ProfileDto> resolved = webClient.get()
    .uri("/profiles/{id}", id)
    .retrieve()
    .bodyToMono(ProfileDto.class)
    .onErrorResume(
        WebClientResponseException.NotFound.class,
        error -> Mono.empty()
    )
    .switchIfEmpty(Mono.defer(() -> cache.findById(id)));
~~~

This is an **integration snippet**, requiring configured WebClient and cache beans. The 404 error is intentionally converted to empty; 500 errors, connection errors, or timeouts still propagate unless a separate policy exists. Be mindful of the business meaning when a successful HTTP response has no body: it can also produce an empty Mono and trigger the fallback, depending on the API.

## 10. Special Trap: `Mono<Void>` and `then()`

`Mono<Void>` is commonly used to represent **successful completion carrying no data** (such as delete, write, or resource release operations). Because it emits no `onNext` on success, `switchIfEmpty` treats that completion as **empty**:

~~~java
Mono<Void> save = Mono.fromRunnable(
    () -> System.out.println("Saved")
);

Mono<Void> chain = save.switchIfEmpty(
    Mono.fromRunnable(
        () -> System.out.println("Fallback also runs")
    )
);
~~~

When subscribing to `chain`, both actions can run: `save` completes empty so Reactor switches to the fallback. This is signal-accurate behavior, yet **usually wrong for the intent “run fallback if save fails”**.

For a follow-up action after a successful save, use:

~~~java
Mono<Void> correct = save.then(
    Mono.fromRunnable(
        () -> System.out.println("Audit after save")
    )
);
~~~

`then` waits for successful completion before subscribing to the next task; if `save` errors, the error propagates and the next task is not run along this path.

**`then()` also intentionally discards all source values and returns `Mono<Void>`:**

~~~java
Mono<Void> completionOnly = Mono.just("value").then();

Mono<Void> surprising = completionOnly.switchIfEmpty(
    Mono.fromRunnable(
        () -> System.out.println("always after successful empty completion")
    )
);
~~~

`completionOnly` completes empty; therefore, after successful completion, `switchIfEmpty` always selects the fallback publisher. Do not place `switchIfEmpty` after `then()` if you meant to check whether the source **before discarding its value** was empty.

`defaultIfEmpty` on `Mono<Void>` also makes no normal sense: there is no valid `Void` instance to pass as a non-`null` fallback value. To turn completion into a business value, use `thenReturn(result)`; to run a next task, use `then(nextPublisher)`.

## 11. When Is a Default Value Dangerous for Business Logic?

Default values are convenient for UI/APIs, yet you must avoid masking missing-data situations:

| Scenario | Generally sensible approach |
| --- | --- |
| Missing display name used only for UI | `defaultIfEmpty("Guest")` if product rules allow it. |
| Cache miss with another reliable data source | `switchIfEmpty(Mono.defer(...))` to query the next source. |
| Required record not found in a REST API | `switchIfEmpty(Mono.error(new ResponseStatusException(...)))`. |
| No items in an optional list | `Flux.empty()` can be a valid result; fall back only if business rules require it. |
| Payment order not found | Do not return a “fake order” via `defaultIfEmpty`. |
| Database connection lost or authorization error | Do not convert to “empty”; let the error surface or recover in a controlled way. |

If you use `-1`, an empty string, or a dummy DTO as a sentinel value, callers must have an explicit contract so they do not mistake it for real data. When you need to distinguish found / not found / error states, consider `Mono<Optional<T>>` or a domain result type, while remembering that `Mono.empty()` itself already represents 0 elements.

### Note when combining with `zip`

`Mono.zip(a, b)` requires each Mono to emit **one value** to build a tuple. If one source is empty, zip does not have enough values and can complete empty (and whether other sources are subscribed/cancelled depends on execution).

If valid defaults exist:

~~~java
Mono<String> name = findName().defaultIfEmpty("Guest");
Mono<Integer> age = findAge().defaultIfEmpty(0);

Mono<String> label = Mono.zip(name, age)
    .map(tuple -> tuple.getT1() + " (" + tuple.getT2() + ")");
~~~

This is an integration snippet where `findName()` and `findAge()` are defined in the application. Use `0` as a default age only if it is meaningful in your domain; otherwise, use an optional type or an explicit status result.

## 12. Testing with `StepVerifier`

Add `src/test/java/EmptyFallbackTest.java` to the project from section 6. The `reactor-test` and JUnit dependencies are already in `build.gradle`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class EmptyFallbackTest {

    @Test
    void defaultValueEmitsOnlyAfterDemand() {
        Mono<String> result = Mono.<String>empty()
            .defaultIfEmpty("guest");

        StepVerifier.create(result, 0)
            .thenRequest(1)
            .expectNext("guest")
            .verifyComplete();
    }

    @Test
    void switchDoesNotSubscribeFallbackForNonEmptySource() {
        AtomicInteger calls = new AtomicInteger();

        Mono<String> fallback = Mono.defer(() -> {
            calls.incrementAndGet();
            return Mono.just("backup");
        });

        StepVerifier.create(
                Mono.just("live").switchIfEmpty(fallback))
            .expectNext("live")
            .verifyComplete();

        assertEquals(0, calls.get());

        StepVerifier.create(
                Mono.<String>empty().switchIfEmpty(fallback))
            .expectNext("backup")
            .verifyComplete();

        assertEquals(1, calls.get());
    }

    @Test
    void switchDoesNotSwallowErrors() {
        Mono<String> source = Mono.error(
            new IllegalStateException("db error")
        );

        StepVerifier.create(
                source.switchIfEmpty(Mono.just("backup")))
            .expectErrorMatches(error ->
                error instanceof IllegalStateException
                    && "db error".equals(error.getMessage()))
            .verify();
    }

    @Test
    void fluxFallbackMayEmitMultipleValues() {
        Flux<String> result = Flux.<String>empty()
            .switchIfEmpty(Flux.just("cache-1", "cache-2"));

        StepVerifier.create(result)
            .expectNext("cache-1", "cache-2")
            .verifyComplete();
    }
}
~~~

Run `gradle test` (or `./gradlew test`/`gradlew.bat test` if using Gradle Wrapper). All four tests are expected to **PASS**.

The first test uses an initial demand of 0 to confirm the default element still obeys Reactive Streams rules: it emits only once the subscriber grants sufficient demand. The second test verifies **the exact moment the fallback is subscribed to**, avoiding confusion between publisher construction and execution. The third test ensures errors are not treated as empty. The fourth test demonstrates that `switchIfEmpty` on a Flux can emit multiple fallback elements.

If the source or fallback uses real schedulers, networking, or timers, add tests for timeouts, cancellation, and dependency call counts with proper mocks/stubs; do not use `Thread.sleep` to “wait until it has probably run”.

## 13. Common Mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Treating `Mono.empty()` as `Mono.just(null)` | Misunderstands the signal model; Reactor forbids emitting `null`. | Use `Mono.empty()` / `Mono.justOrEmpty`. |
| Using `defaultIfEmpty` to call a fallback API | Does not accept a publisher as fallback; leads to nested types or eager execution. | Use `switchIfEmpty(publisher)`. |
| Putting `Mono.just(expensiveMethod())` inside `switchIfEmpty` | `expensiveMethod()` is evaluated immediately when building the pipeline. | Use `Mono.defer` or an appropriate lazy source. |
| Expecting `switchIfEmpty` to run on upstream `onError` | Errors still travel as `onError`. | Use `onErrorResume` if business rules allow. |
| Thinking `switchIfEmpty` falls back per missing element in a Flux | Falls back only when the **entire Flux** emits zero elements. | Place fallback inside the per-ID publisher if needed. |
| Putting `switchIfEmpty` after `then()` to check the prior source | `then()` already dropped the data, making the success stream empty. | Put the fallback before `then()` or use `then` for the next task. |
| Putting `switchIfEmpty` after `Mono<Void>` expecting error handling | Successful completion of `Mono<Void>` is still empty. | Use `then` for success chaining and `onErrorResume` for errors. |
| Using a business-invalid default value | Hides missing data or fabricates dummy records. | Use errors/Optional/Result when absence must be preserved. |
| Using `switchIfEmpty` for WebClient's default 404 | `retrieve()` turns 404 into an error, so the fallback never runs. | Handle the specific HTTP error type and map to empty if needed. |
| Calling `subscribe()` or `block()` manually in a WebFlux handler | Breaks lifecycle and can block the event loop. | Return `Mono`/`Flux` for the framework to subscribe to. |

## 14. How to Choose in Real Work

Before adding a fallback to a pipeline, check yourself:

1. **What is the trigger condition?** If it is completion with no `onNext`, use the `...IfEmpty` operators. If it is an error, use `onError...`. If it is a timeout, decide whether to turn timeouts into a fallback or propagate an error.
2. **What type must the fallback return?** For a ready value, use `defaultIfEmpty`; for a publisher that queries data or emits multiple elements, use `switchIfEmpty`.
3. **Are there side effects when constructing the fallback?** If so, defer with `defer` or a properly configured lazy publisher; avoid blocking I/O on the event loop.
4. **Where is the operator placed?** After `filter`, `flatMap`, `then()`, or any step that can emit empty, the meaning of “empty” differs from the original source.
5. **Do you need to distinguish missing from failure?** Do not convert every error into empty without an explicit policy; choose 404, cache miss, and system error behavior according to the API contract.
6. **Have all branches been tested?** Test non-empty, empty, error, multi-element fallback, and non-completing sources where relevant.

**Remember:** `defaultIfEmpty` replaces a publisher that completed empty with **one value**; `switchIfEmpty` switches to **another publisher** when the first source completes empty. In both cases, “empty” is defined by **zero `onNext` signals before `onComplete`**, not by `null`, errors, or timeouts.

## References

- Reactor Core Reference Guide: https://projectreactor.io/docs/core/release/reference/
- Reactor Mono API — `defaultIfEmpty`, `switchIfEmpty`, `defer`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Reactor Flux API — `defaultIfEmpty` and `switchIfEmpty`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Spring Framework — WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Spring Framework — WebClient: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
- Reactive Streams specification: https://www.reactive-streams.org/
