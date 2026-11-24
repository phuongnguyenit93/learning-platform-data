# `when`, `and`, and Coordinating Completion Signals in Reactor

## 1. Problem: Waiting for Multiple Reactive Tasks to Finish

In Spring WebFlux, there are **independent** tasks that must all finish before the system proceeds to the next step. For example: writing an audit log and updating an index, deleting multiple temporary objects, sending update requests to several services, or running a set of tasks without needing to collect returned data.

The business condition is **"signal completion only when all sources have completed successfully"**. This is the classic scenario for two APIs in Project Reactor:

- **Mono.when(Publisher<?>... sources)**: coordinates **multiple Publishers**; returns **Mono<Void>**, completing when all sources complete successfully.
- **someMono.and(Publisher<?> other)**: combines the completion signal of **a current Mono and another Publisher**; also returns **Mono<Void>**.

Both focus on **terminal signals**, without using emitted data to build a new value. If you need the values produced by the sources, use another mechanism such as **Mono.zip**; if you need to start task B **after A finishes**, use **then**. These are three distinct needs where mixing them up can break execution flow.

This lesson explains **onComplete/onError** signals, the differences among **when**, **and**, **whenDelayError**, **then**, and **zip**, subscription mechanics, errors/cancellation, how to apply them in WebFlux, and a runnable Java 17 example.

## 2. Foundation: What Does Completing a Publisher Mean?

In Reactive Streams, a Publisher communicates with a Subscriber through a sequence of signals:

~~~text
onSubscribe(Subscription)
  ├── onNext(value) ... [zero or more times]
  └── onComplete()  or  onError(error)
~~~

- **onComplete**: the source has no more elements and has ended **successfully**.
- **onError**: the source ended due to an **error**; no onComplete follows.
- **cancel()**: a cancellation request from downstream; this is a control operation, **not equivalent** to onComplete.
- **Mono<T>** emits at most one element then terminates. **Flux<T>** can emit multiple elements.
- **Mono<Void>** emits no meaningful value; on success it sends only **onComplete**. On failure, it sends **onError**.

Example:

~~~java
Mono<Void> save = repository.save(entity).then();
~~~

This is a snippet inside a service where **repository** and **entity** already exist. **save** completes successfully after the save Mono completes, while the saved result value is discarded by **then()**. If the source errors, the **onError** signal is still propagated.

When we say "wait for all", Reactor waits for the **completion signals of the Publishers passed in**, not guessing the state of a task launched separately via **subscribe()** or a Future running outside the pipeline.

## 3. Mono.when: Coordinating Completion of Multiple Sources

Common syntax:

~~~java
Mono<Void> allDone = Mono.when(taskA, taskB, taskC);
~~~

Here **taskA/taskB/taskC** can be **Mono<?>** or **Flux<?>**. When someone subscribes to **allDone**, Reactor subscribes to the provided sources and coordinates their terminal signals. **allDone**:

1. Emits **onComplete** only when all sources have completed successfully.
2. Does not emit the sources' onNext values downstream; the result is **Mono<Void>**.
3. If one source signals **onError**, in default mode it forwards the error downstream immediately and requests cancellation of remaining active sources.
4. If downstream calls **cancel**, it requests cancellation of the subscribed sources.
5. If one source **never completes** and there is no error/cancellation/timeout, **allDone** will also never complete successfully.

Illustration of two independent tasks:

~~~text
taskA:      subscribe ────── onComplete ──────┐
                                              ├── when ── onComplete
taskB:      subscribe ───────────── onComplete┘
~~~

One source finishing first is **not enough** to complete **when**. Which source finishes earlier or later does not change the success condition: **every source** must finish.

### 3.1. Does `when` run in parallel?

**`when` can allow sources to run concurrently**, because it does not chain them step-by-step like **then**. However, **`when` itself does not create threads, switch schedulers, or turn synchronous blocking code into asynchronous I/O**. When the sources are asynchronous Monos (WebClient, timers, reactive I/O), their progress can usually overlap. If sources run synchronously and block during subscribe, whether they actually run in parallel depends on the sources and schedulers.

Do not interpret **Mono.when(A,B)** as "two Java functions always run in parallel on two threads". What is guaranteed is the **completion condition of the returned Mono** and the error/cancellation policy described above.

### 3.2. Emitted data is discarded

~~~java
Mono<Void> done = Mono.when(
    Mono.just("alpha"),
    Mono.just("beta")
);
~~~

When **done** completes, it has no **Tuple2<String,String>** or list of strings as a result. The values **alpha** and **beta** are just internal signals dropped from the combined output. If you need both values returned, use **Mono.zip**:

~~~java
Mono<Tuple2<String, String>> values = Mono.zip(
    Mono.just("alpha"),
    Mono.just("beta")
);
~~~

The snippet above requires importing **reactor.util.function.Tuple2**. **zip** waits for sources to emit **values**, so it differs from **when** when a source succeeds empty. Do not mechanically convert a **Mono<Void>** workflow to **zip**.

## 4. Mono.and: Combining the Completion Condition of Two Sources

**and** is an instance method on a Mono:

~~~java
Mono<Void> bothDone = taskA.and(taskB);
~~~

Meaning: **bothDone** completes when both **taskA** and **taskB** complete successfully; it does not forward data from either source. Example:

~~~java
Mono<Void> refreshCache = cache.refresh(key);
Mono<Void> writeAudit = auditStore.append(event);

return refreshCache.and(writeAudit);
~~~

This is a service snippet assuming both calls return **Mono<Void>**. Both tasks can progress independently; the combined result succeeds only after both finish. An error causes the combined result to error and requests cancellation of the remaining source, matching **when**'s coordination semantics.

Equivalent in intent:

~~~java
Mono<Void> bothByAnd = taskA.and(taskB);
Mono<Void> bothByWhen = Mono.when(taskA, taskB);
~~~

**The main difference is call style**:

- **and** is convenient when you already have a Mono and want to combine one more source.
- **when** is clearer when aggregating 3, 4, or more independent sources, or a dynamic list of Publishers.
- With many sources, **Mono.when(taskA, taskB, taskC)** is usually more readable than a chain **taskA.and(taskB).and(taskC)**.

**`and` does not mean sequential order "A then B"**. Here *and* expresses the logical relation **both A and B finish**, not execution order.

## 5. Signal Coordination Diagrams: Success, Error, and Cancellation

### 5.1. All sources succeed

~~~text
Source A: onSubscribe ── onNext(A) ── onComplete ───┐
                                                    ├── when/and ── onComplete
Source B: onSubscribe ────────────── onComplete ────┘
~~~

Because **when/and** only cares about terminal signals, onNext(A) is not emitted on the **Mono<Void>** result. Source B can be **Mono.empty()**; completing empty still counts as successful completion.

### 5.2. One source fails

~~~text
Source A: onSubscribe ─────────── onError(A failed)
                                              │
Source B: onSubscribe ── processing ──────────┼── cancel requested
                                              │
when/and:            onError(A failed) <──────┘
~~~

This is **fail-fast**: the first error is propagated downstream immediately, and Reactor requests cancellation of other active sources. Because cancellation is a request, side effects **already sent over the network**, **already committed to a database**, or **not supporting immediate cancellation** may still finish. **when/and is not a distributed transaction and provides no automatic rollback.**

A source failing synchronously very early can prevent another source from running its expected work. Therefore, do not use **when** to guarantee "every source definitely ran at least once" when errors occur.

### 5.3. Cancellation from downstream

When an HTTP client disconnects, a downstream timeout triggers, or a Disposable owner calls **dispose()**, the combined subscription can be cancelled; **when/and** requests cancellation of the source subscriptions. No **onComplete** is synthesized. Observe **doFinally(signalType)** if you need to distinguish **ON_COMPLETE**, **ON_ERROR**, and **CANCEL** at the right point in the pipeline.

## 6. `whenDelayError`: Waiting for Remaining Sources After an Error

**Mono.whenDelayError(...)** shares the same goal of "coordinating completion" but uses a different error policy:

~~~java
Mono<Void> allAttempted = Mono.whenDelayError(taskA, taskB, taskC);
~~~

- If all sources succeed, the result is **onComplete**.
- If one or more sources fail, Reactor **defers emitting onError** until the remaining sources also finish. Other sources are **not cancelled early merely because one source failed**, unlike `when`'s fail-fast policy.
- If multiple sources fail, errors are combined so not all information is lost; inspect the root exception and **suppressed exceptions** according to your Reactor version.
- If one source hangs forever, **the result can hang forever even after an error was recorded on another source**. Apply an appropriate deadline/timeout.
- Downstream self-cancellation is still a cancel operation; **DelayError does not prevent cancellation from downstream**.

Comparison:

| Scenario | **Mono.when** / **and** | **Mono.whenDelayError** |
| --- | --- | --- |
| All succeed | Completes after all finish | Completes after all finish |
| One source errors | Fails early; requests cancel on the rest | Waits for remaining sources to finish before reporting error |
| Multiple sources error | Does not guarantee collecting all errors after the first | Can aggregate errors to report afterward |
| One source never completes | Can wait indefinitely if no error/cancel | Can wait indefinitely even when another source has errored |
| Is source data retained? | No, returns Mono<Void> | No, returns Mono<Void> |

**`whenDelayError` does not recover from errors automatically**. If one source fails and the others finish, the final result is still **onError**. If the business tolerates a failure in one step and still considers the overall workflow successful, handle the error explicitly on that source, such as **onErrorResume(... -> Mono.empty())**, while recording the failure state where it can be inspected.

## 7. Distinguishing `when`, `and`, `then`, `zip`, and `merge`

| Operator | Goal | Execution coordination | Result |
| --- | --- | --- | --- |
| **Mono.when(A,B,C)** | Wait for multiple sources to complete | Does not require A to finish before B starts | **Mono<Void>** |
| **A.and(B)** | Wait for A and B to complete | Does not require sequential execution | **Mono<Void>** |
| **Mono.whenDelayError(A,B,C)** | Wait for all sources even if one errors | Defers error until sources finish | **Mono<Void>** or onError |
| **A.then(B)** | **B starts after A completes successfully** | Two-step sequential | **Mono<V>** per B's result |
| **Mono.zip(A,B)** | Wait and **combine values** from A/B | Can coordinate independent sources | **Mono<Tuple2<...>>**; needs values from both |
| **Flux.merge(A,B)** | Mix **elements** emitted from sources | Elements can interleave | **Flux<T>** |

Ask these questions before choosing:

1. **Need to keep results from A and B?** Use **zip** (or an appropriate value-combining operator).
2. **Only need confirmation that every step finished?** Use **when** or **and**.
3. **Need to run step B after A finishes?** Use **then**.
4. **Need every step attempted even if one step fails?** Consider **whenDelayError** with a timeout and error-reporting policy.
5. **Need to gather and emit elements from multiple Fluxes?** Consider **merge**, **concat**, or a corresponding operator; do not use when to forward onNext.

### 7.1. `then` guarantees order; `when` does not

~~~java
Mono<Void> sequential = updateDatabase()
    .then(sendNotification());

Mono<Void> coordinated = Mono.when(
    updateDatabase(),
    sendNotification()
);
~~~

The methods in the snippet are hypothetical examples returning **Mono<Void>** and creating work under a cold/deferred model. With **sequential**, Reactor subscribes to the notification after the update succeeds. With **coordinated**, both sources are coordinated by terminal signal with no ordering dependency. If the notification requires committed data, use **then**, not **when**.

**Watch out for eager side effects:** if a method creates and starts a **CompletableFuture** as soon as it is called, passing its result into **then(...)** does not stop the work from having already started. Wrap the launch inside **Mono.defer(...)** or use an appropriate cold publisher so execution begins only at subscription time.

### 7.2. `zip` does not replace `when` for `Mono<Void>`

~~~java
Mono<Void> save = repository.save(record).then();
Mono<Void> notify = notifier.send(event).then();

// Need to wait for completion, no value needed:
// Mono.when(save, notify)

// Unsuitable if trying to wait for two Void tasks to get a tuple:
// Mono.zip(save, notify)
~~~

Each Mono<Void> completes **without emitting an element**; **zip** requires a value from every source to combine. When one branch is empty, zip can terminate early and cancel the other branch, sometimes before all sources are even subscribed. **when** is the operator designed for waiting on completion without data.

## 8. Runnable Java 17+ Example: `when`, `and`, Errors, and Delay Error

The Maven example below uses Reactor Core 3.6.6. It demonstrates **waiting for two async Monos**, **combining two tasks**, **fail-fast cancelling an unfinished source**, and **delay error**. The program uses **AtomicInteger/AtomicBoolean** counters to avoid depending on log ordering across schedulers.

Directory structure:

~~~text
completion-coordination-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── CompletionCoordinationDemo.java
~~~

File **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>completion-coordination-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-core</artifactId>
      <version>3.6.6</version>
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
        <version>3.3.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

File **src/main/java/CompletionCoordinationDemo.java**:

~~~java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Mono;

public class CompletionCoordinationDemo {

    public static void main(String[] args) {
        AtomicInteger completed = new AtomicInteger();

        Mono<Void> slow = Mono.delay(Duration.ofMillis(100))
            .doOnNext(tick -> completed.incrementAndGet())
            .then();

        Mono<Void> fast = Mono.delay(Duration.ofMillis(20))
            .doOnNext(tick -> completed.incrementAndGet())
            .then();

        Mono.when(slow, fast).block(Duration.ofSeconds(5));
        System.out.println("when finished = " + completed.get());

        AtomicInteger pairCount = new AtomicInteger();
        Mono<Void> first = Mono.fromRunnable(
            () -> pairCount.incrementAndGet()
        );
        Mono<Void> second = Mono.fromRunnable(
            () -> pairCount.incrementAndGet()
        );

        first.and(second).block();
        System.out.println("and finished = " + pairCount.get());

        AtomicBoolean cancelSeen = new AtomicBoolean();
        Mono<Void> pending = Mono.<Void>never()
            .doOnCancel(() -> cancelSeen.set(true));
        Mono<Void> failed = Mono.error(
            new IllegalStateException("boom")
        );

        Mono.when(pending, failed)
            .onErrorResume(error -> Mono.empty())
            .block();

        System.out.println(
            "when cancelled remaining = " + cancelSeen.get()
        );

        AtomicInteger delayedCount = new AtomicInteger();
        Mono<Void> otherWork = Mono.fromRunnable(
            () -> delayedCount.incrementAndGet()
        );

        Mono.whenDelayError(
                Mono.error(new IllegalArgumentException("invalid")),
                otherWork
            )
            .onErrorResume(error -> Mono.empty())
            .block();

        System.out.println(
            "whenDelayError other finished = " + delayedCount.get()
        );
    }
}
~~~

Run with JDK 17+ and Maven in the project directory:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=CompletionCoordinationDemo
~~~

**Expected stdout** (excluding Maven-specific output):

~~~text
when finished = 2
and finished = 2
when cancelled remaining = true
whenDelayError other finished = 1
~~~

Explanation of each section:

1. **when**: two Monos use timers with 100 ms and 20 ms delays. The counter increments when each timer emits; **then()** turns each chain into a completion signal. When **when** succeeds, both have finished, so the counter equals 2. Do not infer that total completion time is an exact 100 ms; the scheduler can affect timing.
2. **and**: two Monos use **fromRunnable** and return **Mono<Void>**. Subscribing to the **and** result runs both and completes only when the counter reaches 2.
3. **when fail-fast**: the **pending** source will never complete on its own. The **failed** source errors immediately; **when** then requests cancellation of **pending**. **doOnCancel** sets the flag to true. **onErrorResume** is used only at the demo boundary to avoid crashing the program on the exception.
4. **whenDelayError**: even though one source errors immediately, Reactor lets **otherWork** finish before propagating the error. After error handling at the demo boundary, the otherWork counter is 1.
5. **block(...)** is used solely in the **main** method of this CLI application to wait for completion and print results. **Never use block on the WebFlux event loop**.

Key verification point: both final cases involve a source error. The difference is not **whether an error exists**, but that **when requests cancellation of remaining work** while **whenDelayError continues waiting for remaining work to finish**.

## 9. Usage in Spring WebFlux

### 9.1. Wait for multiple independent tasks then return an HTTP response

Suppose an endpoint needs to trigger two tasks returning **Mono<Void>**. If it should only return success when both finish:

~~~java
@PostMapping("/orders/{id}/refresh")
public Mono<Void> refresh(@PathVariable String id) {
    Mono<Void> refreshCache = cacheService.refresh(id);
    Mono<Void> publishEvent = eventService.publishRefresh(id);

    return Mono.when(refreshCache, publishEvent);
}
~~~

This is a snippet in a Spring controller assuming **cacheService** and **eventService** exist and both methods return **Mono<Void>**. Spring WebFlux will subscribe to the Mono returned by the controller during HTTP request handling. If both complete successfully, the response can complete. If one source errors, the error is passed into the framework's error-handling pipeline, and the other source may be requested to cancel.

**Business consideration:** if publishing the event is only valid after the cache update succeeds, the two tasks **depend on each other**; in that case use **refreshCache.then(eventService.publishRefresh(id))** to reflect the required order.

### 9.2. When all tasks must be attempted even if one fails

For example, checking/cleaning up multiple independent resources while still waiting for the remaining operations even if one fails:

~~~java
public Mono<Void> cleanup(String id) {
    return Mono.whenDelayError(
        sessionStore.delete(id),
        cacheStore.evict(id),
        auditStore.markCleanup(id)
    );
}
~~~

The snippet assumes all three services return completable Publishers. **whenDelayError** ensures the final result is reported after all three sources finish, even when an error occurs. It **does not guarantee all operations succeeded**: if there is an error, the response can still fail. To return a detailed per-step report, **convert successes and errors into structured status data** for each source and aggregate them properly rather than relying solely on **Mono<Void>**.

### 9.3. Do not subscribe to individual tasks manually in a controller

Pattern that easily loses control:

~~~java
@PostMapping("/bad-refresh")
public Mono<Void> refreshWrong() {
    cacheService.refreshAll().subscribe();
    eventService.publishAll().subscribe();
    return Mono.empty();
}
~~~

**Design flaw:** the controller launched two subscriptions on its own, then returned **Mono.empty()**, which completes immediately. Spring cannot await them via the returned Mono; errors may not be handled in the proper context, and HTTP request cancellation no longer covers those two tasks.

Proper composition:

~~~java
@PostMapping("/refresh")
public Mono<Void> refreshCorrect() {
    return Mono.when(
        cacheService.refreshAll(),
        eventService.publishAll()
    );
}
~~~

In a WebFlux environment, prefer **returning the pipeline** so the framework owns the subscription. Do not call **subscribe()** nested inside a Mono and expect **when** to track work that has been detached from the chain.

### 9.4. Choose appropriate transaction boundaries

**Mono.when** does not provide transactions and does not coordinate atomic commits across multiple services. If one write commits and a second write fails, Reactor can report the error and cancel remaining work, yet **it does not automatically roll back already-completed side effects**. For operations sharing a single reactive transactional connection or state dependencies, non-sequential coordination may be inappropriate. When order is needed, use **then**; when multi-service consistency is needed, design idempotency, outbox/saga, or compensating actions according to business needs.

## 10. Timeout, Cancellation, and Backpressure

### 10.1. A source never completes

~~~java
Mono<Void> all = Mono.when(
    Mono.<Void>never(),
    Mono.delay(Duration.ofMillis(100)).then()
);
~~~

The second source completes, but the first source **never** emits no terminal signal. **all** will wait forever without a cancellation/timeout mechanism.

You can set a deadline:

~~~java
Mono<Void> bounded = Mono.when(taskA, taskB)
    .timeout(Duration.ofSeconds(5));
~~~

When 5 seconds elapse without completion, **timeout** emits an error and cancels the combined upstream per protocol. Cancellation **does not guarantee** immediately stopping an external HTTP request, blocking task, or side effect in an external system. The timeout in the example is illustrative only; choose it based on SLAs and service characteristics.

### 10.2. Observing status after composition

~~~java
Mono<Void> coordinated = Mono.when(taskA, taskB)
    .doOnSuccess(ignored -> log("all complete"))
    .doOnError(error -> logError(error))
    .doFinally(signal -> log("finished with " + signal));
~~~

This snippet uses hypothetical logging functions. **doOnSuccess** on Mono<Void> is invoked on successful completion, and its argument is **null** because there is no value; this is **not onNext(null)**. **doFinally** observes **ON_COMPLETE**, **ON_ERROR**, and **CANCEL**, making it useful for pipeline monitoring. Note that doFinally can run after the terminal signal has already been delivered downstream, so do not use it in place of synchronization/waiting mechanisms.

### 10.3. Demand and discarded data

**when/and** subscribes to source Publishers and tracks completion; if a source is a multi-element **Flux**, the Flux's values are not carried into the **Mono<Void>** result. That does not mean the Flux is unsubscribed or skips executing side effects; the source still runs through to completion. Therefore, passing an infinite Flux into **when** can prevent the result from ever succeeding.

Because the goal is **terminal coordination**, users should not rely on **when** as a backpressure or value-forwarding mechanism. If you need to emit data at downstream's pace, choose a **Flux**-managing operator such as **concatMap**, **flatMap**, **merge**, or **zip** depending on requirements instead of returning a Mono<Void> that drops the payload.

## 11. Common Misconceptions

| Statement/symptom | Correct understanding |
| --- | --- |
| "when(A,B) runs A first, then B" | when coordinates **independent** sources without guaranteeing dependency order. Use **A.then(B)** when sequential execution is required. |
| "and differs from when because it keeps data" | **and** and **when** both return **Mono<Void>** and only coordinate completion. |
| "when returns a list of results" | No; onNext values are discarded. Use **Mono.zip** or a result-collecting mechanism if you need values. |
| "Mono.empty is an error for when" | **Mono.empty()** completes successfully; it provides no payload yet still satisfies the completion condition. |
| "zip can replace when when both sources are Mono<Void>" | Zip needs each source to emit a value; with Mono<Void>, it can terminate early and cancel the other source. |
| "when automatically creates two threads running in parallel" | when allocates no threads or schedulers. Concurrency depends on the Publishers and schedulers. |
| "If one source errors, the other always completes" | With when/and, Reactor requests cancellation of the remaining source; completion is not guaranteed. |
| "whenDelayError swallows errors" | It defers the error, **not deleting it**; the final result still errors if a source errored. |
| "cancel is onComplete" | Cancellation is a stop request, not a terminal success signal. |
| "when guarantees rollback if one task fails" | Reactor does not automatically undo side effects that already occurred. |
| "One Mono.never has no effect" | when can wait forever if a source never ends; timeout/cancellation is required. |
| "subscribe each task separately then return Mono.when(...)" | Only Publishers inside the pipeline are coordinated. Do not subscribe manually outside the chain. |
| "whenDelayError always finishes everything even if the client cancels" | Downstream cancellation can still cancel sources; delayError only changes the reaction to **source errors**. |

## 12. Exercises and Self-Check

**Question 1.** You have two independent Mono<Void> tasks: **writeAudit()** and **evictCache()**. The HTTP request should only complete when both finish. Which operator should you use?  
**Answer:** **Mono.when(writeAudit(), evictCache())** or **writeAudit().and(evictCache())**.

**Question 2.** If sending an email requires data to be saved successfully first, should you use `when`?  
**Answer:** No. Use **save().then(sendEmail())**, with the email-sending work represented as a cold/deferred Publisher.

**Question 3.** One Mono.empty() and one Mono.delay(...).then() are passed to Mono.when. When does the result complete?  
**Answer:** When the delay source also completes; **Mono.empty()** already completed successfully, but it cannot make `when` finish before the remaining source.

**Question 4.** In Mono.when(A,B), A fails early while B is still processing. Is B guaranteed to finish?  
**Answer:** No. `when` requests cancellation of B and propagates the error downstream. External I/O may not stop immediately, yet you must not rely on B finishing in the pipeline.

**Question 5.** You want all tasks attempted before reporting an error, without needing detailed per-task results. What should you use?  
**Answer:** **Mono.whenDelayError(...)**, combined with a timeout if any source could hang.

**Question 6.** Why is Mono.zip(Mono<Void>, Mono<Void>) unsuitable for waiting on all tasks to complete?  
**Answer:** `zip` requires a value from every source. Mono<Void> completes with no onNext; `zip` can finish early and does not guarantee subscribing to or running all branches.

**Practice exercise:** replace **Mono.when** in section 8 with **Mono.whenDelayError** for the pending/failed example. Because pending is Mono.never(), what happens? The result will not finish on its own. Add **timeout(Duration.ofMillis(200))** and observe the timeout/cancellation error. Then replace pending with a Mono completing after 100 ms to compare the behavior on error.

## 13. Application Rules

To pick the right operator, start from the **business completion condition**:

- If steps are **independent** and **all must complete successfully**, use **Mono.when** for multiple sources or **and** for a Mono + Publisher pair.
- If steps are **order-dependent**, use **then**.
- If you need **values** to combine, use **zip** and verify empty-source behavior.
- If you need to **give every source a chance to finish before reporting an error**, use **whenDelayError** and handle timeouts proactively.
- If you need a **detailed per-step report**, produce structured results for each Publisher capturing both success and failure states before aggregating.

A **Mono<Void>** result expresses a pipeline's "finished" condition. For the pipeline to reflect business rules accurately, add clear subscription boundaries, error/cancellation handling, and ensure the operations being awaited live **inside** the coordinated Publishers.

## 14. References

- Project Reactor, **Mono API** (when, whenDelayError, and, then, zip): https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Reactor Reference Guide, **Operator Choice**: https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html
- Reactor Reference Guide, **Handling Errors**: https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html
- Reactor Reference Guide, **Mono.zipWith or zipWhen is never called**: https://projectreactor.io/docs/core/release/reference/faq.html
- Spring Framework, **Reactive Core**: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
