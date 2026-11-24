# Releasing Discarded Elements with doOnDiscard in Project Reactor

## 1. Context: An Element Can Vanish Before Reaching the Subscriber

In Spring WebFlux, many reactive elements are ordinary Java values that can be reclaimed by the garbage collector. However, some elements hold **resources that must be released explicitly**: off-heap memory, reference-counted Netty `ByteBuf`, pooled-memory Spring `DataBuffer`, file handles, or application-managed objects.

Suppose a source emits five objects, yet `filter` lets only three pass. The two dropped objects **never reach the Subscriber**. If they hold resources, processing callbacks at the Subscriber cannot close them. Similarly, an operator with a prefetch queue can hold undelivered elements when downstream cancels or an error occurs. Without cleanup, those resources linger even though the stream has stopped.

Project Reactor provides `Flux.doOnDiscard(Class<R>, Consumer<? super R>)` and `Mono.doOnDiscard(...)` to register a release callback when **an upstream operator with discard support** drops an element from the data path.

After this lesson, you can explain the difference between discard, terminal, and cancellation; place `doOnDiscard` in the right spot; write safe/idempotent callbacks; handle `DataBuffer` across ownership boundaries; recognize when another hook is needed; and test with Java 17+ and `StepVerifier`.

## 2. What Is Discard?

In a flow:

~~~text
Source → filter/skip/queue → Subscriber
              |
              +→ an element is not forwarded
                    |
                    └→ discard (when the operator supports it)
                          |
                          └→ doOnDiscard(Resource.class, cleanup)
~~~

An element is **discarded** when an operator proactively drops it or clears elements held in an internal structure without forwarding them downstream, for example:

- `filter`: elements that do not match the predicate.
- `skip`: elements falling inside the skipped range.
- Variants of `buffer` with gaps between windows: some elements belong to no buffer.
- Certain operators with a **prefetch queue**: elements already pulled from upstream but not yet delivered downstream may be cleared upon `cancel` or `onError`.

According to the Reactor Javadoc, **not every operator supports `doOnDiscard`**. Check the **Discard Support** section in each operator's Javadoc, especially in chains involving `flatMap`, `publishOn`, `buffer`, `filterWhen`, or third-party operators.

### 2.1. Discard Differs from Completion, Cancellation, and Errors

| Event | Meaning | Does it automatically invoke a release callback for every element? |
| --- | --- | --- |
| `onNext(value)` delivered downstream | Subscriber received permission to process a value | No. The receiver/owner must release per contract |
| A `filter` drops `value` | Value does not reach downstream | An operator with Discard Support may invoke `doOnDiscard` |
| `onComplete` | Source finished successfully | Does not automatically release objects already delivered downstream |
| `onError` | Source terminated with an error | May trigger queue clearing if the operator supports discard, but does not replace all cleanup paths |
| `cancel()` | Downstream requests to stop receiving | May clear elements waiting in discard-supporting queues; timing depends on pipeline |
| A protocol-violating Publisher emits `onNext` after terminal | Signal arrives too late with no valid downstream path | Falls under `onNextDropped`, not normal discard by default |

**Key point:** `doOnDiscard` handles **elements dropped before reaching downstream** along paths supported by operators. It does not replace resource ownership for objects already delivered successfully to the Subscriber.

## 3. Syntax, Element Type, and Effective Scope

Simplified signature:

~~~java
<R> Flux<T> doOnDiscard(
        Class<R> type,
        Consumer<? super R> discardHook
);
~~~

`Mono` has an analogous method. `type` selects matching elements at discard time via a runtime check similar to `instanceof`. `discardHook` receives the dropped object itself and performs cleanup.

Example:

~~~java
Flux<Packet> filtered = packets
        .filter(packet -> packet.id() % 2 == 1)
        .doOnDiscard(Packet.class, Packet::release);
~~~

This is an **illustrative snippet**: `Packet` has `id()` and `release()`, and `packets` is an application `Flux<Packet>`. The hook is invoked only when an upstream operator actually drops a `Packet` and supports discard.

With the chain above, if `filter` drops `Packet(2)`, the hook gets a chance to release it. However, if `Packet(1)` reaches the Subscriber, `doOnDiscard` does **not** release `Packet(1)` simply because the pipeline ends later.

### 3.1. Place the Hook After Operators That May Discard

`doOnDiscard` is **pipeline-local** and callbacks are propagated **to eligible upstream operators**. Therefore placement changes effectiveness:

~~~java
// RIGHT: filter is upstream of doOnDiscard.
Flux<Packet> a = packets
        .filter(Packet::valid)
        .doOnDiscard(Packet.class, Packet::release);

// WRONG if the goal is to clean up elements dropped by the filter below:
// filter is downstream, so it does not see this hook.
Flux<Packet> b = packets
        .doOnDiscard(Packet.class, Packet::release)
        .filter(Packet::valid);
~~~

A sensible placement is **immediately after the segment of operators that may discard**, far enough downstream to affect the relevant upstream operators. If additional downstream operators later can also drop elements, ensure an appropriate hook sits **after those operators as well**.

### 3.2. Composable Hooks and Callback Ordering

Per Reactor Javadoc, multiple `doOnDiscard` calls along the same processing path are **additive**; hooks are invoked in declaration order for type-matching elements:

~~~java
Flux<Integer> result = Flux.range(1, 3)
        .filter(n -> n == 2)
        .doOnDiscard(Integer.class, n -> audit("first", n))
        .doOnDiscard(Number.class, n -> audit("second", n));
~~~

`audit` is an illustrative application function. For 1 and 3 dropped by `filter`, both `Integer.class` and `Number.class` callbacks match. **Do not register two callbacks that both release the same resource** unless double invocation is designed to be safe; use one cleanup callback and another strictly for metrics/logging if needed.

### 3.3. Match the Exact Object Type at the Discard Point

If a pipeline transforms element types, choose the type **as it exists when dropped**:

~~~java
Flux<String> labels = packets
        .filter(Packet::valid) // drops Packet objects
        .map(Packet::label)    // only remaining Packets become String
        .doOnDiscard(Packet.class, Packet::release);
~~~

The `Packet.class` hook still helps the upstream `filter` if supported, even though the final output type is `String`. Registering only `doOnDiscard(String.class, ...)` cannot release `Packet` instances dropped before `map`. Always distinguish an operator's input type from the post-transform type.

## 4. Crucial Rule: Callbacks Must Be Idempotent and Safe

The `doOnDiscard` Javadoc requires hooks to be **idempotent** and safe to call with any type-matching instance. *Idempotent* means even if multiple cleanup paths exist or the hook triggers more than once for the same object, resource release remains correct without causing double-free.

A simple way to guard custom resources is an atomic flag:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

final class TrackedResource {
    private final AtomicBoolean released = new AtomicBoolean();

    void release() {
        if (released.compareAndSet(false, true)) {
            // Perform cleanup exactly once.
        }
    }

    boolean isReleased() {
        return released.get();
    }
}
~~~

`AtomicBoolean.compareAndSet` ensures one thread wins the right to perform cleanup. If an external library's `release` is **not idempotent** (such as reference-counted buffers), analyze *ownership*: release only once for **each genuinely owned reference**, or use an appropriate wrapper/tracking mechanism; do not blindly call release twice and catch/ignore errors.

Hooks should be **fast, non-blocking, and exception-free**. They may run on a signal-emitting thread or a thread clearing queues on cancel/error; blocking work inside a hook can stall the pipeline. If cleanup must be asynchronous, `doOnDiscard` provides no `Mono<Void>` return mechanism to await completion; design resource lifecycles with `usingWhen` or workflows with explicit ownership.

### 4.1. Why Not Use doFinally to Release Every Element?

`doFinally(signalType -> ...)` observes subscription termination across complete/error/cancel. It fits cleaning up **subscription-level resources** (given clear ownership and mechanisms), yet it does not receive individual elements dropped by filters or prefetch queues.

Conversely, `doOnDiscard` receives the **specific element instance** needing cleanup. Both hooks serve distinct purposes and may coexist when managing both subscription-level and element-level resources, provided they do not double-release.

## 5. Runnable Java 17+ Example: Cleaning Up Both Kept and Discarded Elements

This example builds a `Packet` model with an `AtomicBoolean` so each object is released only once. Even-numbered `Packet` instances dropped by `filter` are released by `doOnDiscard`; odd-numbered `Packet` instances reaching the Subscriber are released **by the Subscriber itself** after use.

Create a Gradle project:

~~~text
reactor-discard-demo/
├── build.gradle
└── src/main/java/DiscardDemo.java
~~~

Contents of `build.gradle` (Java 17, Reactor Core):

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
    mainClass = 'DiscardDemo'
}
~~~

Contents of `src/main/java/DiscardDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

import reactor.core.publisher.Flux;

public class DiscardDemo {

    static final class Packet {
        private final int id;
        private final AtomicBoolean released = new AtomicBoolean();

        Packet(int id) {
            this.id = id;
        }

        int id() {
            return id;
        }

        void release() {
            if (released.compareAndSet(false, true)) {
                System.out.println("release=" + id);
            }
        }
    }

    public static void main(String[] args) {
        Flux.range(1, 5)
            .map(Packet::new)
            .filter(packet -> packet.id() % 2 != 0)
            .doOnDiscard(Packet.class, Packet::release)
            .subscribe(
                packet -> {
                    System.out.println("use=" + packet.id());
                    packet.release();
                },
                error -> System.out.println(
                        "error=" + error.getClass().getSimpleName()),
                () -> System.out.println("complete")
            );
    }
}
~~~

Run from the project directory using an installed Gradle:

~~~bash
gradle -q run
~~~

If the project has a Gradle wrapper, you can run `./gradlew -q run` on Linux/macOS or `gradlew.bat -q run` on Windows.

Stdout emitted by **the program** with the synchronous `Flux.range` source:

~~~text
use=1
release=1
release=2
use=3
release=3
release=4
use=5
release=5
complete
~~~

Explanation:

1. `Packet(1)` passes `filter`, reaches the Subscriber, is used, and then released.
2. `Packet(2)` is dropped by `filter`, and `doOnDiscard` releases it directly; the Subscriber never sees 2.
3. `Packet(3)` passes `filter` and is released by the Subscriber.
4. `Packet(4)` is discarded and released.
5. `Packet(5)` is used and released; finally downstream receives `onComplete`.

There is no second `release` because `AtomicBoolean` preserves single-cleanup semantics. **This custom Packet example is only to illustrate ownership**; real `DataBuffer`/`ByteBuf` instances have reference counts and their own rules, and you cannot blindly copy the boolean-flag approach when multiple valid references exist.

## 6. Cancellation and Queues: Prefetched but Undelivered Elements

Operators such as `publishOn`, `flatMap`, and `buffer` can hold elements in queues to regulate backpressure. When downstream cancels, elements already pulled from upstream but not yet consumed still need to be released:

~~~text
Upstream emitted:    A   B   C   D
Operator holding:        [B C D]
Downstream received: A
Downstream cancels
Unsent queue:            B C D → discard if operator supports it
~~~

Therefore, when data holds resources, place `doOnDiscard` downstream of operators that may buffer and drain elements. Illustrative example:

~~~java
// packetSource is an application-provided Flux<Packet>.
Flux<Packet> pipeline = packetSource
        .publishOn(scheduler, 16)
        .doOnDiscard(Packet.class, Packet::release)
        .take(1);
~~~

In the snippet above, `scheduler` is also application-provided. **This is not a standalone program.** `publishOn` may have prefetched several `Packet` items; if downstream receives one element and `take(1)` cancels, queued items may be discarded. **Do not predict exact release counts or ordering in a multi-threaded environment** without controlling the scheduler and demand; elements may not yet be created, may be in flight, or may already have been handed to downstream.

Placing the hook after `publishOn` lets the upstream operator see the handler, though if elements dropped by **another downstream operator** must also be cleaned up, place another hook after that operator too. With source-combining operators, multiple points and resource types may need checking.

**Cancellation is not automatically an error.** `cancel` is a control signal from Subscriber to Subscription, neither `onError` nor `onComplete`. `doOnCancel` can observe the cancellation action, whereas `doOnDiscard` handles **individual elements** cleared by operators.

## 7. Spring WebFlux Application: DataBuffer and Pooled Memory

Spring `DataBuffer` is an abstraction for data buffers. With pooled variants, data can live in off-heap memory managed by Netty or a similar backend; Java object garbage collection is insufficient to ensure resources are released on time.

Spring advises calling `DataBufferUtils.release(dataBuffer)` when code finishes using a buffer it owns, as well as using:

~~~java
.doOnDiscard(DataBuffer.class, DataBufferUtils::release)
~~~

if a pipeline contains operators that may drop buffers or queues that may be drained on cancel/error.

### 7.1. Example: Converting Flux<DataBuffer> to byte[] with Clear Ownership

The following illustrates a method in a Spring WebFlux application with `spring-web`, `spring-core`, and Reactor. It converts each retained buffer into an independent `byte[]`:

~~~java
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import reactor.core.publisher.Flux;

public final class BufferReader {

    public static Flux<byte[]> readNonEmpty(Flux<DataBuffer> incoming) {
        return incoming
            .filter(buffer -> buffer.readableByteCount() > 0)
            .doOnDiscard(DataBuffer.class, DataBufferUtils::release)
            .map(buffer -> {
                try {
                    byte[] bytes = new byte[buffer.readableByteCount()];
                    buffer.read(bytes);
                    return bytes;
                } finally {
                    // Only release buffers that were passed into map and
                    // belong to the ownership of this processing path.
                    DataBufferUtils.release(buffer);
                }
            });
    }
}
~~~

This is an **integration snippet**, without `main`, assuming `incoming` transfers buffer ownership to the method. If the source/framework still owns the buffers or an API dictates different ownership transfer rules, adjust releasing accordingly.

- Empty buffers dropped by `filter`: released by `doOnDiscard`.
- Non-empty buffers entering `map`: read into `byte[]` and released in `finally`.
- `finally` also handles exceptions thrown during reading/conversion.
- The copied `byte[]` no longer depends on `DataBuffer` lifetime.

**Do not add `doOnNext(DataBufferUtils::release)` before a step that needs to read the buffer**: releasing too early invalidates the data. Nor should you release the same owned reference in both `doOnDiscard` and another cleanup path without preventing double-release. Real release callbacks must adhere to the reference counts and ownership of each buffer type.

### 7.2. When Using WebClient, Request Bodies, or Decoders

In Spring WebFlux, codecs and the HTTP stack can manage `DataBuffer` automatically in higher-level APIs. For instance, `bodyToMono(String.class)` hands the decoded `String` to the application without requiring you to release the `DataBuffer` already consumed by the codec. Conversely, when working directly with low-level `Flux<DataBuffer>`, read the ownership/release contract carefully.

For `DataBufferUtils.join`, `DataBufferUtils.write`, `DataBufferUtils.read`, or releasing-consumer variants, check each API's Javadoc because retaining, joining, re-emitting, or transferring ownership can differ. Do not apply a blanket rule of “always release immediately inside onNext” to every pipeline.

In high-load systems, failing to release `DataBuffer` instances can drive up **direct memory usage** even when Java heap does not grow correspondingly. Conversely, double release can cause exceptions or use-after-free bugs. Therefore, the question to answer is: **who allocates, who holds, who transfers, and who must release this buffer?**

## 8. Paths That doOnDiscard Does Not Cover

The Reactor Reference Guide distinguishes several cleanup scenarios:

| Scenario | Related mechanism | Notes |
| --- | --- | --- |
| `filter`/`skip` drops valid values by design | `doOnDiscard` | Local hook; operator must have Discard Support |
| Prefetch queue cleared on cancel/error | `doOnDiscard` at an appropriate downstream position | Not every operator supports it; check Javadoc |
| Non-compliant Publisher emits `onNext` late after terminal | `Hooks.onNextDropped` | Global hook, not the normal discard path |
| Operator fails while processing `onNext` | `Hooks.onOperatorError` and operator handling | May need dedicated error-path cleanup |
| Grouping/key-holding or specialized collection operators | Operator-specific cleanup handlers | E.g., state in certain `distinct` variants |
| Subscription-scoped resources like sessions/files/cursors | `using` / `usingWhen` | Cleaned on complete/error/cancel per resource contract |
| Elements already delivered to the Subscriber | Cleanup at owner/downstream | `doOnDiscard` does not auto-release consumed values |

Global hooks `Hooks.onNextDropped`/`Hooks.onOperatorError` have broader impact and require controlled configuration, especially when running multiple tests or libraries in the same JVM. Do not set global hooks casually per WebFlux request. For a specific stream, prefer local hooks whenever they solve the problem.

### 8.1. Overlapping Buffers and Complex Ownership

Some operators such as `bufferWhen` can produce **overlapping buffers**, meaning the exact same element object appears in multiple buffers. When one buffer is discarded, immediately releasing objects inside it can leave remaining buffers holding **already-freed references**.

With such structures, do not mechanically attach `doOnDiscard(List.class, list -> list.forEach(DataBufferUtils::release))` if buffers can share elements. Determine ownership, copy or retain when multiple owners are allowed, or use specialized handling per data contract. Idempotent cleanup is not the only solution: an object with **multiple valid owning references** must be released once per retain, and never freed while another owner still holds it.

### 8.2. When a Cleanup Callback Itself Throws

A cleanup hook that throws an exception can complicate an operator's error path and obscure the root cause. Keep callbacks stable, fast, instrumented with logs/metrics, and handle exceptions according to application resource rules. Never turn `doOnDiscard` into a place for network API calls or blocking DB writes.

## 9. Testing with StepVerifier

In a Java 17 project that already has `reactor-test` and JUnit 5, add test dependencies matching Reactor Core (for example Gradle):

~~~groovy
dependencies {
    testImplementation 'io.projectreactor:reactor-test:3.8.8'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

File `src/test/java/DiscardTest.java`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class DiscardTest {

    @Test
    void filterDiscardsElementsBeforeSubscriber() {
        List<Integer> discarded = new ArrayList<>();

        Flux<Integer> source = Flux.range(1, 5)
                .filter(n -> n % 2 == 1)
                .doOnDiscard(Integer.class, discarded::add);

        StepVerifier.create(source)
                .expectNext(1, 3, 5)
                .verifyComplete();

        assertEquals(List.of(2, 4), discarded);
    }

    @Test
    void discardHookBeforeFilterDoesNotObserveFilterDiscard() {
        List<Integer> discarded = new ArrayList<>();

        Flux<Integer> source = Flux.range(1, 4)
                .doOnDiscard(Integer.class, discarded::add)
                .filter(n -> n % 2 == 0);

        StepVerifier.create(source)
                .expectNext(2, 4)
                .verifyComplete();

        assertTrue(discarded.isEmpty());
    }

    @Test
    void matchingHooksAreAdditiveInDeclarationOrder() {
        List<String> calls = new ArrayList<>();

        Flux<Integer> source = Flux.range(1, 3)
                .filter(n -> n == 2)
                .doOnDiscard(Integer.class, n -> calls.add("one:" + n))
                .doOnDiscard(Number.class, n -> calls.add("two:" + n));

        StepVerifier.create(source)
                .expectNext(2)
                .verifyComplete();

        assertEquals(List.of(
                "one:1", "two:1", "one:3", "two:3"), calls);
    }
}
~~~

These three tests verify **observable discard paths**, the upstream scope of hooks, and the ordering of multiple hooks. Using `ArrayList` in tests is valid because `Flux.range`/`filter` are synchronous with no scheduler involved. If switching to an asynchronous source, use a concurrent collection or assert on the test thread after the work completes; avoid inferring callback ordering across multiple threads.

Tests for `doOnDiscard` with real resources should additionally check: every owned resource is eventually released according to ownership; elements reaching the Subscriber remain usable before release; cancellation/error leaves no backlog; cleanup does not run twice causing double-free. Such tests should control schedulers and sources rather than relying on `Thread.sleep` and random timing.

## 10. Designing Cleanup by Ownership: Engineering Checklist

Before passing a resource type through `Flux`/`Mono`, determine:

1. **Which resource?** `DataBuffer`, `ByteBuf`, file handle, native memory, or application resource? Pure Java objects like `String`/`Integer` need no release.
2. **Who allocates?** Does the source create the resource and transfer usage rights downstream, or only lend it?
3. **Who processes successful elements?** The final receiver must release at the right moment, or explicitly transfer ownership to the next layer.
4. **Which operators can discard?** `filter`, `skip`, `publishOn`, `flatMap`, `take`, or others; read the Discard Support notes for your Reactor version.
5. **Where are hooks placed?** After the upstream operators they apply to; if there are multiple drop points, verify each hook's scope and the resource type at each segment.
6. **Is the callback idempotent and thread-safe?** Non-blocking, no unsynchronized shared-state mutation, no double-release.
7. **What happens on cancel/error?** Queues may drain; resources already delivered to the Subscriber must be managed by the Subscriber; subscription-scoped resources use other mechanisms.
8. **Are references shared across buffers/subscribers?** If so, use retain/release or copying according to proper ownership.
9. **Have normal, filtered, cancelled, error, and concurrent paths been tested?** Especially critical for pooled direct memory and production loads.

By nature, `doOnDiscard` is a **local cleanup mechanism**, not a garbage collector or a global exactly-once guarantee for every resource in a pipeline. When multiple ownership branches exist, design an explicit lifecycle beyond a single callback.

## 11. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Releasing only inside `subscribe(onNext)` | Elements dropped by filter/skip never reach Subscriber and may leak | Place `doOnDiscard` after element-dropping operators |
| Placing `doOnDiscard` before the `filter` you want to observe | Hook does not see discards occurring downstream | Move the hook after `filter` |
| Assuming every operator invokes the hook | Some operators lack Discard Support | Read version-matched Javadoc and test |
| Calling release in `doOnNext` before another layer uses the data | Use-after-release or corrupted data | Release at the final owner after use |
| Having multiple hooks both release the same reference | Double-free / negative reference count | One owner handles cleanup; other hooks only audit/metric |
| Non-idempotent cleanup | Cancel/error and multiple hooks can cause bad cleanup | Guard release rights, obey reference counts |
| Using `doFinally` with a list of elements without knowing which were delivered | May mistakenly release elements belonging to downstream | Use `doOnDiscard` for discards and manage delivered element ownership separately |
| Using `Hooks.onNextDropped` instead of normal discard | Global hook is not a local mechanism for `filter` | Use `doOnDiscard` with supporting operators |
| Holding objects in overlapping buffers and releasing when one buffer drops | Another buffer still references freed resource | Copy or retain/release per owner count |
| Calling blocking I/O inside a release callback | Stalls emission or cleanup threads | Keep cleanup fast; use `usingWhen` for async resources |
| Confusing completion with all elements being released | Elements already delivered downstream may still be owned by the receiver | Define an explicit ownership protocol |
| Monitoring only Java heap without measuring direct memory | Leaked Netty pooled buffers go unnoticed | Track allocator/direct memory, unreleased buffer counts, and test cancellation |

## 12. Self-Check

1. `filter` drops a `DataBuffer` before the Subscriber receives it. What cleans it up? **`doOnDiscard(DataBuffer.class, DataBufferUtils::release)` if the hook is placed properly and ownership permits release.**
2. Does placing `doOnDiscard` **before** `filter` see elements dropped by that later filter? **No.**
3. Does `onComplete` mean all resources delivered to the Subscriber have been released? **No.**
4. Does `doOnDiscard` automatically clean up every element across every Reactor operator? **No; the operator must provide Discard Support.**
5. When downstream calls `cancel`, why is `doOnDiscard` helpful? **Some prefetch-queue operators clear elements already received from upstream but not yet pushed downstream.**
6. Why must the callback be idempotent? **Multiple cleanup paths may exist or hooks may reapply; double release causes errors.**
7. How does `Hooks.onNextDropped` differ from `doOnDiscard`? **It is a global hook for signals dropped outside normal flow, such as a Publisher emitting after terminal; `doOnDiscard` is local cleanup for operators supporting discard.**
8. Once a `DataBuffer` reaches downstream, does `doOnDiscard` automatically release it immediately? **No; the owner on the successful processing path must release it at the right time.**
9. Overlapping buffers hold the same `ByteBuf` in two lists. May you release it immediately when one list is dropped? **Only when ownership/reference-count permits; do not break the remaining owner.**
10. Why is testing only `onNext` data insufficient? **You must verify resources never delivered downstream are still released, including during cancel/error.**

**Key takeaway:** `doOnDiscard` helps clean up elements dropped by **upstream operators with discard support**, including many queue-draining cases on cancel/error. Place hooks accurately, match the right resource type, and keep callbacks idempotent and fast. For `DataBuffer`/`ByteBuf`, always define clear ownership and handle elements already delivered downstream separately.

## References

- [Project Reactor Reference: Dealing with Objects that Need Cleanup](https://projectreactor.io/docs/core/release/reference/advancedFeatures/cleanup.html).
- [Project Reactor Flux Javadoc: doOnDiscard and Discard Support](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- [Project Reactor Mono Javadoc: doOnDiscard](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html).
- [Spring Framework: Data Buffers and Codecs — release and doOnDiscard](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html).
- [Spring DataBufferUtils Javadoc — release, join, read, write](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html).
- [Reactor Reference: Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html).
