# switchMap for Switching to the Latest Work in Project Reactor

**Context:** Spring Framework – Reactive, topic **Data Transformation**. This lesson focuses on Project Reactor's `Flux.switchMap(...)`: whenever the source emits a new request, switch to the publisher corresponding to the latest request and cancel the previous task's subscription if it is still running.

## 1. The Problem: Stale Results Arriving After Newer Results

Imagine a search UI: the user types “jav”, then edits it to “java”. The two searches can take different amounts of time:

- The “jav” request is sent first, and upstream processes it slowly.
- The “java” request is sent later, yet responds faster.
- If we simply accept all results regardless of order, the result for “jav” can arrive late and overwrite the result for “java”. The UI then displays data that does not match the user's latest intent.

Within an event stream on a single subscription, `switchMap` expresses the **latest-wins** rule: each new event is mapped to an *inner publisher*, and the previous inner subscription is canceled so only signals from the currently selected task continue to be received.

For example, a `Flux<String>` of search terms emits “jav” followed by “java”. The mapper creates a `Mono<SearchResult>` for each term. When “java” arrives before the “jav” query finishes, `switchMap` cancels the “jav” query's subscription and switches to awaiting the “java” result.

**Two important limitations:** `switchMap` cannot erase old signals **already emitted downstream**; nor does it guarantee successfully canceling a remote operation that has already started or rolling back side effects. It controls **downstream subscriptions and signals**, not a distributed business cancellation protocol.

## 2. How `Flux.switchMap` Works

The API is used in this form:

```java
Flux<R> output = input.switchMap(value -> publisherFor(value));
```

Here, `input` is a `Flux<T>`, and the mapper function takes each `T` element and returns a `Publisher<? extends R>` (usually a `Mono<R>` or `Flux<R>`). Each time `input` emits a new value, the operator proceeds as follows:

1. Receives the new element from the outer stream (*outer Flux*).
2. Stops listening to the old inner publisher by **canceling the old subscription**, if still active.
3. Subscribes to the new inner publisher created by the mapper.
4. Forwards signals from the active inner to the downstream subscriber.
5. Once outer completes, waits for the current inner to finish in order to complete (unless an error or cancellation occurs).

This is a conceptual model, not a guarantee of exact callback or thread ordering:

```text
Outer Flux:
  term A -------- term B --------------- term C ---- complete
      |               |                      |
      v               v                      v
  inner A         inner B                inner C
  ...waiting      ...waiting             ...finished
      X cancel        X cancel                 |
                                                   
Output:
  [signals from A emitted in time, if any]  [signals from B emitted in time, if any]  [signals from C]
```

If A has emitted no results before B arrives, downstream receives no result from A. If A **already emitted element A1** before B appeared, A1 has already been forwarded and cannot be recalled; only signals **after A is canceled** are no longer forwarded as the selected work.

With a `Mono` inner, typically at most one result is received. With a `Flux` inner, an inner can emit multiple elements before a new event arrives. Therefore, **“only receiving the final result of the entire outer Flux” is not the right definition of `switchMap`**. The accurate definition is “whenever a new outer element arrives, switch to the latest inner and cancel the previous inner”.

### 2.1. Does the Outer Source Have to Wait for the Inner to Complete?

No. This is the key difference from `concatMap`. `switchMap` does not delay new input just to wait for old work. It is the arrival of a new outer element that causes the operator to shift priority to the new inner.

If outer keeps emitting continuously faster than an inner's completion time, many inners can be canceled before producing a result. That behavior makes sense for **typeahead search, previews, or latest-view state**, yet is dangerous if every single task must complete.

### 2.2. Subscriptions, Cancellation, and Real-World Work

`switchMap` creates a subscription to the child publisher and sends a *cancel* signal to the old subscription when switching. For publishers that support cancellation, a timeout, timer, or HTTP client can stop waiting and release the corresponding resources. However:

- An HTTP request may have already reached the server; the server may continue processing even though the client canceled waiting for the response.
- A blocking JDBC call, file I/O, or CPU-bound function may not stop immediately even after the subscription is canceled.
- A shared or cached publisher may still have other subscribers, so canceling one subscriber does not necessarily stop the shared source.
- Side effects already executed—such as creating an order, charging a payment, or sending an email—are not rolled back simply because `switchMap` switched to a new inner.

Accordingly, using `switchMap` to **avoid displaying stale results** makes sense; using it as a mechanism for **transaction rollback, exactly-once guarantees, or canceling work in another system** is wrong.

## 3. Runnable Java 17+ Example Independent of Timing

The following example intentionally uses `Mono.never()` to represent an old task that never completes. When a new element arrives, `switchMap` must cancel this task; thus both the output and the cancellation count can be verified **deterministically**, independent of schedulers, network, or machine speed.

File `src/main/java/demo/SwitchMapDemo.java`:

```java
package demo;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class SwitchMapDemo {
    public static void main(String[] args) {
        AtomicInteger cancelledOld = new AtomicInteger();

        Flux<String> results = Flux.just("old", "new")
                .switchMap(query -> {
                    if ("old".equals(query)) {
                        return Mono.<String>never()
                                .doOnCancel(cancelledOld::incrementAndGet);
                    }
                    return Mono.just("result-new");
                });

        List<String> values = results
                .collectList()
                .block(Duration.ofSeconds(3));

        System.out.println("results = " + values);
        System.out.println("cancelled old = " + cancelledOld.get());
    }
}
```

You can run `main` from an IDE in a project that already has the `io.projectreactor:reactor-core` dependency, such as a Spring Boot project with `spring-boot-starter-webflux`. If running directly with `javac/java`, you need the compatible `reactor-core` and `reactive-streams` JARs in a `lib/` directory:

```bash
# Linux / macOS, run from the root directory containing src/ and lib/
javac -cp "lib/*" -d . src/main/java/demo/SwitchMapDemo.java
java -cp ".:lib/*" demo.SwitchMapDemo
```

With Windows PowerShell, the classpath separator for the `java` command is a semicolon:

```powershell
javac -cp "lib/*" -d . src/main/java/demo/SwitchMapDemo.java
java -cp ".;lib/*" demo.SwitchMapDemo
```

**Exact stdout:**

```text
results = [result-new]
cancelled old = 1
```

Why?

1. `Flux.just("old", "new")` is a synchronous cold source. When a subscriber triggered by `block(...)` attaches, it emits “old”, then “new”.
2. “old” creates `Mono.never()`. This task gets subscribed, yet emits no value and never terminates on its own.
3. “new” is emitted next. `switchMap` cancels the “old” subscription once, causing `doOnCancel` to increment the counter.
4. The new inner `Mono.just("result-new")` emits one value and completes; `collectList()` collects that sole element.
5. Outer finishes and the final inner has completed, so `block(...)` returns the list to print the result.

**To test the hypothesis**, replacing `switchMap` with `concatMap` in the example above prevents the pipeline from waiting for “old” to complete to process the next element in the same way; `Mono.never()` will cause the example to exceed `block(Duration...)` and throw an exception. Do not run that variant expecting the same stdout as the original.

This is an **illustration of subscription-level cancellation**, not a simulation of a real HTTP request. When using real I/O, you must measure and monitor whether cancellation actually frees connections/workers.

## 4. Comparing `map`, `flatMap`, `concatMap`, and `switchMap`

All four appear frequently in Reactor data processing, yet serve different purposes.

| Operator | Mapper returns | How multiple outer elements are handled | Best suited for |
| --- | --- | --- | --- |
| `map` | Plain value `R` | Transforms each element synchronously without creating a subscription to an inner publisher | DTO conversion, string normalization, simple calculations |
| `flatMap` | `Mono/Flux` Publisher | Allows multiple inners to run concurrently; results may interleave, outer order not preserved by default | Independent I/O calls where all results are needed |
| `concatMap` | `Mono/Flux` Publisher | Processes inners sequentially, typically waiting for the current inner to complete before moving to the next | Tasks that must run/emit in order and must not be dropped |
| `switchMap` | `Mono/Flux` Publisher | When a new outer element arrives, cancels the previous inner and switches to the latest inner | Live search, previews, refreshing latest data |
| `flatMapSequential` | `Mono/Flux` Publisher | Can subscribe to multiple inners concurrently, yet schedules result emission in outer order with buffering cost | Concurrent work where result order must still be preserved |

Meaningful examples:

- **Need to persist every business change:** normally do not use `switchMap`; a dropped event can mean data loss. Consider `concatMap` or a durable queue mechanism depending on requirements.
- **Independently calling a pricing API and an inventory API:** use `Mono.zip` or `flatMap` when both results are needed; `switchMap` is only appropriate if a newer request renders data from the previous request obsolete.
- **User switching rapidly between profiles:** `switchMap` fits if you only want to display data for the currently selected profile.
- **Processing payments / recording orders:** do not use `switchMap` just because a new event arrives; each command must be processed according to the business contract, even if the client disconnects.

**Remember the distinction:** `switchMap` does not mean a “faster” `flatMap`. It **changes result semantics** by abandoning old inners, so it is only valid when old work is permitted to have no displayed result.

## 5. Spring WebFlux Example: Live Search over a Keyword Stream

Suppose an application has a `Flux<String>` containing keyword changes within the same interactive session. Keywords may arrive via WebSocket, a streaming session, or an adapter in the application layer. For each keyword, the service calls a search HTTP API using `WebClient` and builds a result snapshot. This is exactly the situation `switchMap` solves: the new search intent replaces the old intent.

The code below is a **complete service class inside a Spring Boot/WebFlux application**, requiring an HTTP upstream at `http://localhost:8081/search?q=...` returning matching JSON items; it is not a standalone application with a `main` method. Use Java 17+ and the `spring-boot-starter-webflux` and `spring-context` dependencies managed by your project.

File `src/main/java/demo/LiveSearchService.java`:

```java
package demo;

import java.time.Duration;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class LiveSearchService {
    private final WebClient catalogClient;

    public LiveSearchService(WebClient.Builder builder) {
        this.catalogClient = builder
                .baseUrl("http://localhost:8081")
                .build();
    }

    public Flux<SearchSnapshot> search(Flux<String> terms) {
        return terms
                .map(String::trim)
                .distinctUntilChanged()
                .switchMap(term -> {
                    if (term.isBlank()) {
                        return Mono.just(
                                new SearchSnapshot(term, List.of(), false));
                    }

                    return Mono.delay(Duration.ofMillis(250))
                            .then(Mono.defer(() -> catalogClient.get()
                                    .uri(uriBuilder -> uriBuilder
                                            .path("/search")
                                            .queryParam("q", term)
                                            .build())
                                    .retrieve()
                                    .bodyToFlux(Item.class)
                                    .collectList()
                                    .map(items -> new SearchSnapshot(
                                            term, items, false))))
                            .timeout(Duration.ofSeconds(2))
                            .onErrorResume(error -> Mono.just(
                                    new SearchSnapshot(
                                            term, List.of(), true)));
                });
    }

    public record Item(String id, String name) {}

    public record SearchSnapshot(
            String term,
            List<Item> items,
            boolean failed) {}
}
```

How the service works:

1. `map(String::trim)` normalizes strings; `distinctUntilChanged()` drops **consecutive** duplicate keywords.
2. `switchMap` receives **every distinct change**, including clearing the search box, so it immediately cancels the old inner. If the user clears the keyword, an empty `SearchSnapshot` is emitted. **Do not place `filter(term -> !term.isBlank())` before `switchMap`** if clearing the keyword must cancel the old query, because then the blank event would never reach `switchMap`.
3. `Mono.delay(250 ms)` puts a *quiet wait interval* **inside the inner**. If the keyword changes again within 250 ms, `switchMap` cancels both the timer and the old inner, so the old request is not even sent over the network. No `Thread.sleep` or thread blocking is needed.
4. `Mono.defer(...)` ensures building the HTTP publisher happens when the timer completes and the subscription is still active. `WebClient` supports non-blocking I/O streams; `bodyToFlux(Item.class).collectList()` produces **one snapshot** per search instead of emitting item-by-item and mixing batches in the UI.
5. `timeout(2 s)` bounds waiting time; `onErrorResume(...)` converts an error of **a specific query** into a snapshot with `failed=true` so the keyword stream can continue. Do not confuse an error with a valid empty result list: `failed` lets the presentation layer tell them apart. In production, add logging/metrics, classify errors before falling back, and do not lose track of important failures.
6. When a new keyword arrives, `switchMap` cancels the previous inner's subscription; results from the old inner after cancellation are no longer used for the output stream. If the old inner already emitted a snapshot earlier, that snapshot already exists downstream and only the new snapshot updates the UI next.

**Architecture must be in the right place:** the service receives `Flux<String> terms` representing **one event stream**. If the UI sends independent HTTP GETs and Spring creates a separate controller invocation each time, placing `switchMap` inside each invocation **does not automatically cancel the previous invocation's request**, because they do not share a single outer Flux/subscription. In systems using independent HTTP GETs, the requester (such as the frontend search stream) must coordinate latest-wins, or the application needs a shared channel/server-side stream with an explicit lifecycle.

**It is discouraged** to call `subscribe()` inside the `search(...)` method just to “start” requests. Return the publisher to the subscriber at the appropriate boundary (WebFlux, WebSocket handler, or stream consumer) so the framework/consumer manages lifecycle, errors, and cancellation.

### 5.1. Why Does Putting Debounce Inside vs. Outside `switchMap` Differ?

The following two patterns look similar, yet have different cancellation windows:

**Approach A – debounce first, only switch after the keyword stabilizes:**

```java
Flux<SearchSnapshot> a = terms
        .debounce(Duration.ofMillis(250))
        .switchMap(term -> searchMono(term));
```

**Approach B – switch immediately, delay starting the search in the inner:**

```java
Flux<SearchSnapshot> b = terms
        .switchMap(term ->
                Mono.delay(Duration.ofMillis(250))
                        .then(Mono.defer(() -> searchMono(term))));
```

Both snippets are merely **illustrative code**, requiring `terms` and `searchMono(String)` provided by the application. With A, the new event does not reach `switchMap` until it passes `debounce`: during the 250 ms wait, the previous query **may still remain active**. With B, `switchMap` receives the change right away and cancels the old inner immediately; the new inner's timer waits 250 ms before running the search.

Which approach is right depends on UX requirements: whether you want to keep old results until the new query stabilizes, whether old I/O must be canceled the moment a new character is typed, and whether clearing the input box needs an immediate update. Do not treat `debounce` and `switchMap` as two names for the same functionality.

## 6. Monitoring Cancellation and Handling Errors Properly

### 6.1. Observing `doOnCancel` and `doFinally`

To debug cancellation on the inner publisher:

```java
return terms.switchMap(term ->
        searchMono(term)
                .doOnCancel(() ->
                        log.debug("Cancelled search: {}", term))
                .doFinally(signal ->
                        log.debug("Finished search {} with {}", term, signal)));
```

This is an **illustrative snippet in a service**; `terms`, `searchMono`, and `log` must be defined by the application. `doOnCancel` is invoked when the subscriber cancels the publisher; `doFinally` receives `SignalType.CANCEL`, `ON_COMPLETE`, or `ON_ERROR` to identify the termination type. **Seeing a CANCEL event does not prove the HTTP server stopped processing**; it is a signal on the observed publisher. For tracing, also attach a correlation ID/keyword in the proper context so logs across multiple users do not mix.

Do not rely on log ordering across multiple schedulers to assert exact network ordering. Use metrics: count of new events, inner starts, cancels, completes/errors, wait latency, connection pool usage, and actual requests sent.

### 6.2. An Inner Error Can Terminate the Entire Outer Flux

If an inner emits an unhandled `onError`, the operator can propagate the error downstream and **terminate the entire stream**. For typeahead, a single upstream error could stop subsequent keywords from being processed. If business requirements want the stream to stay alive, handle errors **inside each inner**, like the `onErrorResume` example inside `switchMap`, to turn errors into a distinguishable display state.

However, do not catch every `Throwable` and pretend the search simply had no results: authentication errors, misconfigurations, schema mismatches, or programming bugs may require a different policy. Design logging, alerting, and fallbacks according to your API contract.

### 6.3. `retry` Can Re-Create Work

When retrying a cold publisher, Reactor typically **resubscribes** to the source. This can resend HTTP requests, recreate I/O, or repeat side effects. For read-only searches, bounded retries with backoff may be acceptable if load and latency are bounded; for data writes, you must evaluate idempotency, transactions, and retry safety.

`switchMap` can cancel an inner that is retrying; if upstream does not honor cancellation, old attempts can still consume resources. Do not rely on cancellation as a substitute for timeouts, concurrency limits, and circuit breakers.

## 7. Canceling a Subscription Does Not Mean Canceling All Business Work

Place tasks into the right decision category:

| Type of work | Should old inner be dropped on new input? | Reason |
| --- | --- | --- |
| Image preview, typeahead search, filtering a list from an input box | Usually yes | Old results are no longer relevant to the current UI state |
| Viewing details of a selected item, map for a new location | Possibly | Only want to show the latest item/location |
| Status polling solely to refresh the screen | Possibly | Stale data fetches do not matter if only the latest snapshot is needed |
| Recording orders, payments, sending emails | Usually no | Each command is a side effect that must complete, needing tracking and idempotency |
| Ledger event processing, syncing changes that must not be lost | No | Dropping an inner means risking lost business operations |
| Heavy CPU-bound task already running | Only when true cancellation support exists | Reactive subscription cancellation does not force a CPU task to stop immediately |

Even for a state-saving API like “change UI theme”, consider what happens if the server receives two commands and executes them concurrently: canceling waiting for the old command on the client **does not guarantee** the old command won't reach the server or execute after the new command. If update order truly matters, the server needs versioning/check-and-set, sequence numbers, idempotency keys, or proper synchronization.

**Decision rule:** `switchMap` is appropriate when **it is acceptable to discard the result of old work**. That is different from claiming **the old work definitely did not happen**.

## 8. Testing Behavior with Reactor Test

Beyond inspecting logs, write tests proving two properties: the old inner receives cancellation, and downstream receives only the new inner's result if the old inner has not emitted in time.

The test below is a JUnit 5 class usable in a project with `reactor-test`, `reactor-core`, and JUnit Jupiter. File `src/test/java/demo/SwitchMapTest.java`:

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SwitchMapTest {
    @Test
    void cancelsPreviousInnerAndKeepsLatest() {
        AtomicInteger cancelled = new AtomicInteger();

        Flux<String> result = Flux.just("first", "second")
                .switchMap(term -> {
                    if ("first".equals(term)) {
                        return Mono.<String>never()
                                .doOnCancel(cancelled::incrementAndGet);
                    }
                    return Mono.just("second-result");
                });

        StepVerifier.create(result)
                .expectNext("second-result")
                .verifyComplete();

        assertEquals(1, cancelled.get());
    }
}
```

JUnit requires `org.junit.jupiter:junit-jupiter`, and `StepVerifier` requires `io.projectreactor:reactor-test` on the test classpath; in a Spring Boot project, these test dependencies can follow the project BOM. Run via `./gradlew test` or your IDE's JUnit runner. This synchronous test has deterministic results and does not depend on `Thread.sleep(...)`.

For search logic requiring a 250 ms timing check, use `StepVerifier.withVirtualTime(...)` and construct the publisher inside the supplier required by that API; virtual time lets you assert timer/debounce/switch behavior accurately without waiting on wall-clock time. With a real HTTP client, use a mock server and appropriate request/cancellation assertions; **do not assume client cancellation means the server never receives the request**.

To test work with side effects, add assertions on upstream call counts, retry counts, final server state, and disallowed updates. Testing Reactor signals alone is not enough to guarantee out-of-process business consistency.

## 9. Common Mistakes

### 9.1. Confusing `switchMap` with “Take the Last Element”

`switchMap` can emit data from an earlier inner before outer emits a new element. If you only need **the last element of a finite Flux after it completes**, look at `last()` or `takeLast(...)` depending on requirements, though those operators have different contracts for completion timing and data retention. `switchMap` is a way to **switch the actively observed task** per input, not a general last-element selector.

### 9.2. Using `switchMap` on an Outer Flux with No New Events

If outer emits only a single element, `switchMap` cannot “switch to newer work” because there is no next element. For single-item `Mono` processing, `flatMap` is usually enough; `switchMap` is useful when there is genuinely a **stream of changes** over time.

### 9.3. Filtering Out the Cancellation Signal

If you write:

```java
terms.filter(term -> !term.isBlank())
     .switchMap(term -> searchMono(term));
```

then clearing the search box **produces no event reaching `switchMap`**, allowing the old inner to keep running until another keyword arrives. If clearing must cancel the task and emit an empty result, move that logic into the `switchMap` mapper instead of filtering beforehand.

### 9.4. Assuming a New Keyword Always Cancels the Upstream Server Immediately

The operator sends cancellation to the inner subscription. Across the network, connections, databases, drivers, and servers have many layers; some still execute and persist results. You need timeouts, resource limits, and appropriate side-effect safeguards. Do not run unskippable business operations through `switchMap`.

### 9.5. Ignoring Hot Sources, `cache`, and `share`

With a cold publisher, cancellation can usually stop the source from continuing to emit to that subscriber. With a hot publisher or `cache()`/`share()`, upstream may keep running due to other subscribers or caching. A hot `Sinks.Many` source can also emit events before subscription or faster than downstream consumes them. Verify actual cancellation and replay/buffering policies of the source rather than guessing from the operator name alone.

### 9.6. Confusing `switchMap` with `debounce` or Backpressure Control

- `debounce` limits how many **outer events** are forwarded after a quiet period.
- `distinctUntilChanged` drops **consecutive duplicate** events.
- `switchMap` manages the **latest inner subscription** whenever an outer event arrives.
- `onBackpressureLatest` applies a strategy keeping the latest element at a demand pressure point, without replacing `switchMap`'s inner-task cancellation semantics.

Compose them in the right order for your business goal while bounding I/O, connection pools, and buffer sizes. `switchMap` is not an automatic cure-all for every overly fast source.

### 9.7. Forgetting Error Handling and Stream Lifecycle

An unhandled error inside an inner can terminate the entire output stream; if a downstream subscriber cancels, both outer and the current inner can be canceled as well. When using WebSockets or long-lived interactive streams, design resource cleanup, reconnection, request/response tracking, error handling, and final state when the channel closes.

## 10. Checklist for Choosing and Applying `switchMap`

1. **Business semantics:** is it genuinely acceptable to drop old results? If not, do not choose `switchMap`.
2. **Real outer Flux:** do old and new inputs belong to the same stream/subscription? Independent HTTP requests do not create latest-wins automatically.
3. **Mapper returns a lazy publisher:** use `WebClient`/async APIs and avoid `Mono.just(blockingCall())`. Blocking work must be isolated, not occupying the event loop.
4. **Empty state is meaningful:** must a clear/empty event cancel an in-flight search? Do not filter it out before the operator if it must cancel.
5. **Switching timing:** choose debounce before `switchMap` or delay inside the inner depending on whether you want immediate cancellation or cancellation after a quiet period.
6. **Error strategy:** should a single search failure kill the entire stream? If not, recover per inner and represent errors explicitly.
7. **Measure resources and cancellation:** monitor actual requests sent, latency, canceled inners, active work, connection pools, and memory.
8. **Consistency:** if work has already been sent to another system, cancellation does not guarantee rollback. Critical side effects need dedicated protection.
9. **Testing:** include tests for rapidly changing input, cleared input, inner errors, out-of-order responses, downstream cancellation, and load limits.

## 11. Summary

`Flux.switchMap(mapper)` is designed for **streams of changing intent**, where each new value makes the previous task's result unnecessary. The operator maps each outer element to an inner publisher, **cancels the previous inner when a new element arrives**, and continues emitting from the latest inner. It differs from `flatMap` (keeps inners concurrent) and `concatMap` (processes each inner in order).

Typical applications include live search, previews, and UI item selection. Three facts must always hold true: **already-emitted signals cannot be recalled; cancellation is not rollback; and `switchMap` only coordinates tasks within the same outer Flux/subscription**. When these conditions match business requirements, `switchMap` directly expresses the principle that “the result of the latest intent wins”.
