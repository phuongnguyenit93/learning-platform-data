# Terminal Signals, Unsubscribing, and the No-`null` Rule in Reactive Streams

## 1. Context and Objectives

In Spring WebFlux, Project Reactor's `Mono<T>` (0 or 1 item) and `Flux<T>` (0 to many items) types implement the Reactive Streams protocol. This protocol defines not only how data is delivered, but also **when a subscription ends, when a receiver stops receiving, and which values are allowed to flow through a stream**.

After this lesson, you should be able to distinguish:

- `onComplete()`: the source finished **successfully**, possibly after 0 items.
- `onError(Throwable)`: the source terminated due to an **error**.
- `Subscription.cancel()`: the receiver **no longer wants to receive data**; this is not a terminal signal sent to the `Subscriber`.
- `onNext(null)`: a **protocol violation**; do not use `null` to represent an empty stream.

## 2. Lifecycle of a Subscription

The four foundational components are `Publisher<T>` (source), `Subscriber<T>` (receiver), `Subscription` (registration relationship controlling demand/cancellation), and `Processor` (both receiver and producer). For a single subscription, the valid sequence is typically:

~~~text
Publisher.subscribe(subscriber)
           |
           v
Subscriber.onSubscribe(subscription)  [exactly once]
           |
           +---- subscription.request(n > 0) ----> Publisher
           |
           +<--- onNext(item)  [0..N items, non-null item]
           |
           +<--- onComplete()  [success, terminal]
           | OR
           +<--- onError(error) [failure, terminal]

Alternative branch: Subscriber -> subscription.cancel() -> Publisher
                                      (eventually stops emitting; onComplete not required)
~~~

Key rules:

1. `onSubscribe` must arrive before `onNext`, `onError`, or `onComplete`; signals sent to a `Subscriber` must be **serialized**, even when processing runs across multiple threads.
2. Each `request(n)` with `n > 0` adds permission to receive up to `n` `onNext` items. Total `onNext` emissions must not exceed total unfulfilled demand. `request(0)` or `request(n < 0)` is an invalid request; an active `Subscription` must emit `onError(IllegalArgumentException)`.
3. `onComplete` and `onError` **do not need to wait for a data request**: an empty source or immediate failure can still terminate right after `onSubscribe`.
4. `onComplete` and `onError` are **mutually exclusive**. After a terminal signal, no further signals may be sent on the same subscription, including `onNext` or a second terminal signal.
5. An infinite publisher may never terminate on its own. Do not assume every `subscribe` is guaranteed to receive `onComplete` or `onError`.

| Event | Who initiates it? | Meaning | Is it a terminal signal sent to the Subscriber? |
| --- | --- | --- | --- |
| `onNext(value)` | Publisher | A non-null item, counted against requested demand | No |
| `onComplete()` | Publisher | Out of data, succeeded | Yes |
| `onError(error)` | Publisher | Terminated due to error, with a non-null `Throwable` | Yes |
| `cancel()` | Subscriber / downstream operator | No more demand; requests upstream to stop emitting and release resources | No |

## 3. The Two Terminal Signals: `onComplete` and `onError`

**`onComplete()`** carries no data and does not imply that at least one item was emitted earlier:

~~~java
Flux.just("A", "B");            // onNext("A"), onNext("B"), onComplete()
Flux.<String>empty();           // onComplete(), no onNext
Mono.<String>empty();           // onComplete(), no onNext
~~~

**`onError(Throwable)`** reports a failure, ends the current stream, and cannot be followed by `onComplete` on the same subscription:

~~~java
Flux.just(1, 2)
    .concatWith(Mono.error(new IllegalStateException("boom")));
// onNext(1), onNext(2), onError(IllegalStateException)
// NO onComplete()
~~~

These are source expression snippets; a complete compilable and runnable program is in section 6.

Error-handling operators such as `onErrorResume` or `onErrorReturn` **replace the failed stream segment with a fallback path**, rather than reviving the terminated source. For example:

~~~java
Mono.<String>error(new IllegalStateException("DB down"))
    .onErrorResume(error -> Mono.just("cache"));
// The final subscriber sees onNext("cache"), onComplete().
// The source before onErrorResume still terminated with onError.
~~~

Avoid using `onErrorComplete()` merely to swallow errors silently. Only convert an error into an empty completion if business logic genuinely treats that error as absence of data.

## 4. `cancel()` and How It Differs from Terminal Signals

When a `Subscriber` no longer needs data, it calls `Subscription.cancel()`. `cancel()` must be safe to call from multiple threads, be idempotent (repeated calls have no extra effect), and ask the source to **eventually stop emitting** to that subscriber. It does not guarantee every in-flight operation halts instantaneously: due to latency/asynchronous races, a few `onNext` signals that were already requested and in flight may still arrive while cancellation is being processed.

**Do not equate `cancel()` with `onComplete()`**:

- With `Flux.range(1, 100).take(2)`, the `take(2)` operator receives 2 values and then **cancels the upstream subscription** so it does not fetch more; at the same time it can send **`onComplete` downstream**. What you observe depends on which side of `take` you attach a hook to.
- With a `BaseSubscriber` that explicitly calls `cancel()`, that subscriber must not expect the source to call `onComplete()` after cancellation.
- When an HTTP request is cancelled or the client disconnects in WebFlux, cancellation can propagate back up the pipeline. Actual cleanup still depends on the publisher and integrated resources.

To observe or clean up in Reactor:

- `doOnComplete(...)`: runs only when the source completes successfully.
- `doOnError(...)`: runs only when an error occurs.
- `doOnCancel(...)`: observes the cancel action at the hook's position.
- `doFinally(signalType -> ...)`: observes **`ON_COMPLETE`, `ON_ERROR`, or `CANCEL`** at the operator's position; suitable for recording metrics and end-of-lifecycle handling.

`doFinally` is a Reactor callback after termination/cancellation, **not a Reactive Streams `onComplete` signal**. Use `using`/`usingWhen` or an appropriate lifecycle management mechanism when resources (connections, files, transactions) must be closed properly across completion, error, and cancellation paths; avoid relying on `doOnComplete` to release resources upon cancellation.

## 5. Why Does Reactive Streams Disallow `null`?

A call to `onNext(null)` is invalid; the `Subscription` parameter of `onSubscribe` and the `Throwable` parameter of `onError` must also not be `null`. A `null` value is neither an "empty item" nor a "terminal signal." Reserving `onComplete` as the end-of-stream signal keeps data, success, and failure cleanly separated in an asynchronous protocol.

In Project Reactor:

| Purpose | Correct Approach | Incorrect or Misleading Approach |
| --- | --- | --- |
| Exactly one value | `Mono.just(nonNullValue)` | `Mono.just(null)`: fails when creating the Mono |
| Potentially null value from a legacy API | `Mono.justOrEmpty(nullableValue)` | Passing `null` directly into `onNext` |
| No value | `Mono.empty()` | `Mono.just(null)` |
| Skip an item during transformation | `flatMap(v -> condition ? Mono.just(v) : Mono.empty())` or `handle` | `map(v -> null)` |
| Genuine error | `Mono.error(new IllegalStateException("..."))` | `onError(null)` |
| Only need to know an operation finished | `Mono<Void>` completes without emitting data | Using `null` as a "done" item |

Example with a value from a traditional Java method:

~~~java
String email = null; // Simulate legacy source not finding an email

Mono<String> optionalEmail = Mono.justOrEmpty(email);
optionalEmail
    .defaultIfEmpty("no email yet")
    .subscribe(System.out::println);
// Prints: no email yet
~~~

If you want to **skip** a specific value (without treating it as an error), return an empty publisher:

~~~java
Flux.just("A", "SKIP", "B")
    .flatMap(value -> "SKIP".equals(value)
        ? Mono.<String>empty()
        : Mono.just(value));
// Emits "A", "B", then onComplete; does not emit null.
~~~

If you need to represent a data field that is *present but empty*, you can emit `Optional.empty()` **as a non-null object**. That differs from `Mono.empty()`, which emits no items at all. Choose the clearest model according to your business contract.

In Reactor, a mapper returning `null` usually causes the pipeline to receive a `NullPointerException` via `onError`. Do not try to patch it by filtering `null` after `map`: the error has already happened before `filter` gets a chance to run. Use `flatMap`/`handle` or normalize null to `Mono.empty()` right at the integration boundary.

## 6. Runnable Java 17+ Example: Completion, Error, Cancellation, and Empty Source

Create a Maven project with the two files below. It uses Reactor Core `3.8.8`, a stable release on Maven Central; the application runs synchronously so log order is easy to verify.

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactive-signals-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>example.ReactiveSignalsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**`src/main/java/example/ReactiveSignalsDemo.java`**

~~~java
package example;

import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class ReactiveSignalsDemo {
    public static void main(String[] args) {
        System.out.println("1. COMPLETE");
        Flux.just("A", "B").subscribe(
            value -> System.out.println("onNext: " + value),
            error -> System.out.println("onError: " + error.getMessage()),
            () -> System.out.println("onComplete")
        );

        System.out.println("2. ERROR");
        Flux.just(1, 2)
            .concatWith(Mono.error(new IllegalStateException("boom")))
            .subscribe(
                value -> System.out.println("onNext: " + value),
                error -> System.out.println("onError: " + error.getMessage()),
                () -> System.out.println("onComplete")
            );

        System.out.println("3. CANCEL");
        Flux.range(1, 5)
            .doFinally(type ->
                System.out.println("upstream finally: " + type.name()))
            .subscribe(new BaseSubscriber<Integer>() {
                @Override
                protected void hookOnSubscribe(Subscription subscription) {
                    request(2);
                }

                @Override
                protected void hookOnNext(Integer value) {
                    System.out.println("onNext: " + value);
                    if (value == 2) {
                        cancel();
                    }
                }
            });

        System.out.println("4. EMPTY");
        Mono.justOrEmpty((String) null)
            .defaultIfEmpty("fallback")
            .subscribe(
                value -> System.out.println("onNext: " + value),
                error -> System.out.println("onError: " + error.getMessage()),
                () -> System.out.println("onComplete")
            );
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java
~~~

**Expected stdout output** (all publishers in the example run synchronously without a scheduler):

~~~text
1. COMPLETE
onNext: A
onNext: B
onComplete
2. ERROR
onNext: 1
onNext: 2
onError: boom
3. CANCEL
onNext: 1
onNext: 2
upstream finally: CANCEL
4. EMPTY
onNext: fallback
onComplete
~~~

Explanation: case 1 has two `onNext` calls followed by `onComplete`; case 2 has two `onNext` calls followed by `onError` and **no** `onComplete`. In case 3, `BaseSubscriber` requests only 2 items and then calls `cancel()`; the upstream `doFinally` observes `CANCEL`, with no `onComplete` sent to the cancelled subscriber. Case 4 creates a `Mono.empty()` from `null` via `justOrEmpty`, then `defaultIfEmpty` substitutes **a non-null value** and completes.

## 7. Applying in Spring WebFlux and Common Mistakes

- **Record not found:** For a repository returning `Mono<User>`, use `switchIfEmpty(Mono.error(new ResponseStatusException(HttpStatus.NOT_FOUND)))` when the API convention requires HTTP 404. `Mono.empty()` by itself only expresses the absence of an item; HTTP mapping must be decided explicitly at the controller/handler layer.
- **Client cancellation / timeout:** Record cancellations and release resources; do not assume `doOnComplete` will run. A downstream timeout can trigger `onError` downstream while cancelling the upstream subscription; observing signals must consider **hook placement**.
- **Callback subscribe missing error handling:** When calling `subscribe` manually in application code, provide an error consumer or build an explicit error-handling path. In standard WebFlux handlers, prefer **returning `Mono`/`Flux`** so the framework manages subscription and lifecycle.
- **Calling `block()` on the event loop:** This can block the request-processing thread and degrade responsiveness; compose publishers using `map`, `flatMap`, `zip`, etc., within the reactive chain.
- **Assuming `request(n)` guarantees exactly n items:** A Publisher may complete or signal an error after fewer than n items; demand is an **upper bound**, not a guaranteed record count.
- **Treating cancel as an error:** Cancellation can be normal behavior (for example, a user leaving a page or `take` having collected enough items); use separate metrics for `CANCEL`, `ON_ERROR`, and `ON_COMPLETE` for accurate analysis.

Quick knowledge check: (1) Does `Mono.empty()` call `onNext`? **No**, only `onComplete`. (2) Can `onComplete` occur after `onError`? **No**. (3) Does `cancel()` mean downstream receives `onComplete`? **No**. (4) Does a `map` function returning `null` validly represent absent data? **No**; use operators for empty streams.

## 8. Authoritative References

- [Reactive Streams Specification for the JVM](https://github.com/reactive-streams/reactive-streams-jvm#specification): Publisher rules 1.1–1.9, Subscriber rules 2.1–2.13, and Subscription rules 3.5–3.12.
- [Project Reactor – Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): errors are terminal; fallback operators replace the failed stream.
- [Reactor Core API – Mono](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): `justOrEmpty`, `empty`, `doFinally`, `doOnCancel`, and empty-value conventions.