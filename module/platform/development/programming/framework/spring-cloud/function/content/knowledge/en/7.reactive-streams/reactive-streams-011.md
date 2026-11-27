# Per-Element Error Handling vs. Stream-Terminating Errors

## 1. The Problem: Should One Bad Order Halt All Remaining Orders?

Suppose a system processes three events sequentially: **A, B, C**. A is valid, B has missing information or hits an external service failure, and C is valid. The desired outcome depends on business rules:

- **Halt the whole stream:** if processing B is unsafe, stop so C's state is not corrupted.
- **Mark B failed and continue:** if events are independent and failures are recorded reliably, still process C.
- **Retry B then decide:** if the failure is a transient network/system error, retry with bounds before halting or routing B to a dead-letter store.
- **Return a business result for B:** if B is simply rejected under valid rules, represent it as a data status rather than necessarily emitting `onError`.

In **Spring Cloud Function**, logic can be packaged into `Supplier`, `Function`, and `Consumer`, looked up via `FunctionCatalog`, chained via composition, and deployed identically across HTTP, message/event binders, or serverless environments. With the `Function<Flux<T>, Flux<R>>` signature, deciding whether to place an error-handling operator **inside or outside the inner publisher** determines whether C still gets processed.

This lesson belongs to the **Reactive Streams** chapter and centers on a critical distinction:

> **A business failure on one element does not have to become an `onError` signal that terminates the entire subscription.** Once a `Flux` actually emits `onError`, that subscription ends. To continue, you must design recovery scope before the error escapes into a pipeline-wide terminal signal.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish **business failure outcomes** from the Reactive Streams **`onError` signal**.
2. Explain why `onErrorResume` placed after an entire `Flux` does not continue remaining elements of the failed source.
3. Use `concatMap`/`flatMap` and inner `Mono`s to isolate errors per element.
4. Choose appropriately among `onErrorReturn`, `onErrorResume`, `onErrorMap`, `onErrorComplete`, `retryWhen`, and `delayError` variants.
5. Recognize the risks of `onErrorContinue`, silent fallbacks, and retrying an entire stream.
6. Organize dead-lettering, idempotency, timeouts, acknowledgments, and error observability at the right unit of work.
7. Test fail-fast policies, continue-on-error behavior, and retries with `StepVerifier`.

## 2. Reactive Streams: onError Is a Terminal Signal

In Reactive Streams, a publisher can emit:

~~~text
onSubscribe
  └── onNext(T) × 0..N
        └── onComplete
        or
        └── onError(Throwable)
~~~

`onComplete` and `onError` are **mutually exclusive terminal signals** for a single subscription. A source that has emitted `onError` will never emit another `onNext` to that same subscriber as though nothing happened.

Example:

~~~java
Flux<String> source = Flux.concat(
    Flux.just("A"),
    Flux.error(new IllegalStateException("Cannot read B")),
    Flux.just("C")
);
~~~

The subscriber receives A and then `onError`; `Flux.just("C")` is never reached in that subscription because `concat` encountered an error on the preceding publisher.

~~~mermaid
flowchart LR
    A["onNext(A)"] --> B["onError(B)"]
    B --> STOP["Subscription terminates"]
    STOP -.-> C["C is not emitted"]
~~~

### 2.1. Error Termination Differs from Cancellation

- `onComplete`: publisher ends normally.
- `onError`: publisher ends with an error.
- `cancel()`: subscriber no longer wants more items and asks upstream to stop; **not** an `onError` or `onComplete` emitted downstream.

An error may prompt the framework or downstream to cancel running inner publishers, yet you should never equate *cancellation* with *business failure*. With external I/O, a canceled task may still have sent a request or committed earlier.

### 2.2. Where Do Errors Occur?

| Location | Example | Consequence if unhandled |
| --- | --- | --- |
| Source creation | `Flux.error(exception)` | Stream emits `onError` |
| Synchronous mapper | `map(order -> validateOrThrow(order))` | Exception is converted into `onError` |
| Inner publisher | `flatMap(order -> client.call(order))` | One inner error can fail the entire `Flux` |
| Payload conversion | Converter cannot deserialize data | Adapter-dependent: error happens before or inside the function |
| Binder/broker | Message send/ack fails | May lie outside the scope of the Reactor operators you wrote |
| Cleanup | Closing connection/commit fails | May alter the observed terminal signal |

**A Java exception inside a function does not necessarily share the same retry or acknowledgment mechanics as a transport error.** When exposing a function over HTTP, Spring Cloud Stream, or serverless, distinguish Reactor pipeline errors from adapter-level errors.

## 3. The Most Common Mistake: Outer onErrorResume Over the Whole Stream

Suppose the input has three numbers, and 2 triggers an error:

~~~java
Flux<Integer> source = Flux.just(1, 2, 3)
    .map(n -> {
        if (n == 2) {
            throw new IllegalArgumentException("bad item: 2");
        }
        return n * 10;
    });
~~~

If you just subscribe, downstream receives `10` and then `onError("bad item: 2")`; `30` never appears.

Someone adds:

~~~java
Flux<Integer> recovered = source
    .onErrorResume(error -> Flux.just(-1));
~~~

The output is:

~~~text
10, -1, onComplete
~~~

**Not**:

~~~text
10, -1, 30, onComplete
~~~

Because `onErrorResume` here **replaces the entire terminated upstream with a fallback publisher**. It does not “go back into `map` to skip 2 and continue with 3.”

### 3.1. Recovery Scope Diagram

~~~mermaid
flowchart TD
    S["Flux: 1, 2, 3"] --> MAP["map: 1→10; 2→exception"]
    MAP --> ERROR["onError"]
    ERROR --> RESUME["Outer onErrorResume"]
    RESUME --> FALLBACK["Flux.just(-1)"]
    FALLBACK --> DONE["onComplete"]
    MAP -.-> LOST["Element 3 is never processed"]
~~~

**Rule:** to prevent B's failure from killing the entire A–B–C stream, create an **inner publisher boundary dedicated to B** and recover *inside* that boundary.

### 3.2. A Fallback Does Not Mean Success

`-1` in the snippet above is a simple technical placeholder, but in business logic you need a meaningful outcome: `REJECTED` (validly rejected), `UNAVAILABLE` (could not check), `FAILED` (error recorded), or a dead-letter record.

Never return `true`, `APPROVED`, or `Mono.empty()` for every error just to keep the pipeline running. Doing so hides unprocessed data.

## 4. Isolating Errors Per Element with concatMap and Inner Monos

Instead of throwing inside a shared `map`, build an independent publisher for each element:

~~~java
Flux<Integer> safe = Flux.just(1, 2, 3)
    .concatMap(n ->
        Mono.fromCallable(() -> {
            if (n == 2) {
                throw new IllegalArgumentException("bad item: 2");
            }
            return n * 10;
        })
        .onErrorResume(error -> Mono.just(-1))
    );
~~~

When subscribed, the output is:

~~~text
10, -1, 30, onComplete
~~~

Explanation:

1. `concatMap` receives 1 and subscribes to the `Mono` handling 1; the result is 10.
2. For 2, `Mono.fromCallable` emits `onError`.
3. `onErrorResume` **inside** 2's publisher replaces the error with `Mono.just(-1)`.
4. 2's inner publisher completes normally; `concatMap` moves on to 3.
5. The outer stream sees no unhandled `onError`, so it emits 30 and completes.

### 4.1. Why Use an Inner Publisher?

`Mono.fromCallable` converts an exception thrown in `Callable` into an `onError` signal **of that specific `Mono`** upon subscription. Thus `onErrorResume` handles only a single element's failure.

~~~java
Function<Integer, Mono<Integer>> perItem = n ->
    Mono.fromCallable(() -> validateAndConvert(n))
        .onErrorResume(error -> Mono.just(-1));

Flux<Integer> all = Flux.just(1, 2, 3)
    .concatMap(perItem);
~~~

`validateAndConvert` is a hypothetical synchronous business method. When a function returns an asynchronous inner publisher, the pattern is identical:

~~~java
Flux<Decision> decisions = events.concatMap(event ->
    riskClient.check(event)
        .onErrorResume(error ->
            Mono.just(Decision.unavailable(event.eventId()))
        )
);
~~~

`riskClient.check(event)` returns `Mono<Decision>`; `Decision.unavailable` is an illustrative factory method. What matters is where `onErrorResume` sits: inside the lambda for **each event**.

### 4.2. concatMap or flatMap?

| Operator | How it processes | Preserves output order | Can run multiple tasks concurrently |
| --- | --- | --- | --- |
| `concatMap` | Subscribes to each inner publisher sequentially | Yes, in source order | Does not run multiple inner tasks concurrently |
| `flatMap` | Subscribes to multiple inner publishers, merges results | Not guaranteed | Yes |
| `flatMapSequential` | Subscribes to multiple inner publishers, emits in source order | Yes at output | Yes |

When events are independent and throughput takes priority:

~~~java
Flux<Decision> decisions = events.flatMap(event ->
    riskClient.check(event)
        .onErrorResume(error ->
            Mono.just(Decision.unavailable(event.eventId()))
        ),
    8
);
~~~

`8` limits concurrent inner publishers within **one subscription** to the operator. Errors are recovered per inner publisher, though **output order can change**. For strictly sequential updates to the same aggregate, `concatMap` is easier to reason about.

### 4.3. Wrong Scope Even When Using flatMap

~~~java
// The whole Flux can halt when any inner publisher errors.
Flux<Decision> wrong = events
    .flatMap(riskClient::check, 8)
    .onErrorResume(error ->
        Flux.just(Decision.unavailable("unknown"))
    );
~~~

An error from inner publisher B causes `flatMap` to signal an error downstream, cancel other active tasks under default policy, and switch to the global fallback. This is **not** per-event error isolation.

## 5. Distinguishing “Invalid” from “Infrastructure Failure”

Not every failure scenario should be represented by an exception. For example:

- Negative order amount: **business validation rejection**; return a `REJECTED` result.
- Risk service timed out: **infrastructure could not reach a decision**; retry and then mark `UNAVAILABLE`.
- Database write failed: **no guarantee the outcome was saved**; halt the stream or write durably to a dead-letter store.
- Malformed payload at HTTP/binder: may be rejected by the adapter **before** the function ever receives an event.

An explicit result type:

~~~java
public enum ProcessingStatus {
    APPROVED,
    REJECTED,
    UNAVAILABLE
}

public record ProcessingResult(
    String eventId,
    ProcessingStatus status,
    String reasonCode
) {}
~~~

`REJECTED` can be a completely normal business outcome: the publisher emits `onNext(ProcessingResult)` and keeps going. `UNAVAILABLE` expresses a controlled infrastructure failure; never conflate it with `APPROVED`.

### 5.1. Why Are Explicit Business Results Helpful?

| Contract | What the receiver understands | Consequence |
| --- | --- | --- |
| `onNext(APPROVED)` | Approved decision reached | Continue workflow |
| `onNext(REJECTED)` | Rejected decision reached | Record rejection reason |
| `onNext(UNAVAILABLE)` | No decision could be reached | Reconcile, retry later, or dead-letter |
| `onError(IllegalStateException)` | Publisher cannot continue normally | Caller/adapter handles terminal error |
| `onComplete` | Subscription ended normally | Does not prove all external side effects committed |

If downstream expects **one result per event**, choose `Function<Flux<Event>, Flux<Result>>` instead of using `Mono.empty()` and losing failure details.

## 6. Complete Spring Cloud Function Example: Per-Order Recovery

An order-checking application has three requirements:

1. Every valid event is evaluated via a reactive API.
2. If evaluation fails, the failure record must be persisted to a retry store before emitting `UNAVAILABLE`.
3. If **saving the failure record also fails**, never pretend processing succeeded: let the error propagate through the pipeline so operations can intervene.

The configuration below uses Java 17+ and Reactor. These interfaces are illustrative application contracts, not built-in Spring Cloud Function APIs.

~~~java
package demo.reactive.errors;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Configuration
public class OrderErrorFunctions {

    public record OrderEvent(
        String eventId,
        String orderId,
        long amountCents
    ) {}

    public enum DecisionStatus {
        APPROVED, REJECTED, UNAVAILABLE
    }

    public record ProcessingResult(
        String eventId,
        DecisionStatus status,
        String reasonCode
    ) {}

    public interface RiskService {
        Mono<DecisionStatus> evaluate(OrderEvent event);
    }

    public interface FailedEventStore {
        // Mono completes once the failure has been durably saved
        // per the real implementation contract.
        Mono<Void> save(OrderEvent event, Throwable cause);
    }

    @Bean
    public Function<Flux<OrderEvent>, Flux<ProcessingResult>> processOrders(
            RiskService riskService,
            FailedEventStore failedEventStore) {

        return incoming -> incoming.concatMap(event ->
            riskService.evaluate(event)
                .map(status -> new ProcessingResult(
                    event.eventId(),
                    status,
                    status == DecisionStatus.REJECTED
                        ? "BUSINESS_REJECTED"
                        : "CHECKED"
                ))
                .onErrorResume(error ->
                    failedEventStore.save(event, error)
                        .thenReturn(new ProcessingResult(
                            event.eventId(),
                            DecisionStatus.UNAVAILABLE,
                            "RISK_SERVICE_FAILED"
                        ))
                )
        );
    }
}
~~~

### 6.1. Why Are FailedEventStore Errors Still Propagated?

`failedEventStore.save(event, error).thenReturn(result)` emits `result` **only after the failure-persistence publisher completes successfully**. If the dead-letter/audit store returns `onError`, the inner publisher also fails; `concatMap` by default propagates that error to the whole pipeline.

In other words, this pattern intentionally enforces **a two-tier policy**:

- Errors from `RiskService`: recovered per element if persisting the failure state succeeds.
- Errors from `FailedEventStore`: critical incidents that can halt the stream to avoid reporting false success.

**Durability boundary:** the comment in the interface specifies that `save` completes after durable persistence; actual durability still depends on the database/queue implementation, transactions, and acknowledgments. `thenReturn` does not automatically turn a “fire-and-forget” API into a durable commit.

### 6.2. Processing Flow

~~~mermaid
flowchart TD
    EVENT["onNext(OrderEvent)"] --> CHECK["RiskService.evaluate(event)"]
    CHECK --> OK{"Signal from RiskService?"}
    OK -->|onNext DecisionStatus| RESULT["ProcessingResult approved / rejected"]
    OK -->|onError| STORE["FailedEventStore.save"]
    STORE --> STORED{"Error write succeeded?"}
    STORED -->|Yes| UNAVAILABLE["ProcessingResult UNAVAILABLE"]
    STORED -->|Error| ABORT["onError terminates stream"]
    RESULT --> NEXT["concatMap: next event"]
    UNAVAILABLE --> NEXT
~~~

### 6.3. Using flatMap for Higher Throughput

You can swap `concatMap` for `flatMap(..., 8)` when events are independent:

~~~java
return incoming -> incoming.flatMap(event ->
    riskService.evaluate(event)
        .map(status -> new ProcessingResult(
            event.eventId(), status, "CHECKED"
        ))
        .onErrorResume(error ->
            failedEventStore.save(event, error)
                .thenReturn(new ProcessingResult(
                    event.eventId(),
                    DecisionStatus.UNAVAILABLE,
                    "RISK_SERVICE_FAILED"
                ))
        ),
    8
);
~~~

When one event fails in `FailedEventStore`, the terminal error can cancel other already-subscribed inner publishers. Some external tasks may already have finished prior to cancellation, so idempotency and state tracking remain necessary.

### 6.4. When Validation Is a Predictable Business Failure

Instead of throwing an exception for a negative amount, return a result:

~~~java
Mono<ProcessingResult> validate(OrderEvent event) {
    if (event.amountCents() <= 0) {
        return Mono.just(new ProcessingResult(
            event.eventId(),
            DecisionStatus.REJECTED,
            "INVALID_AMOUNT"
        ));
    }
    return Mono.empty(); // No terminal decision yet; proceed to next step.
}
~~~

This shows a standalone validation step. When wiring it into a pipeline, be explicit about whether `Mono.empty()` means “proceed” or “no result”; never replace the whole stream with `empty` and accidentally drop elements. A cleaner model is usually `validateAndEvaluate(event)` returning **exactly one `ProcessingResult`** per event by contract.

## 7. Common Error-Handling Operators and Their Scopes

| Operator | Mechanism | Watch out for |
| --- | --- | --- |
| `doOnError(callback)` | Observes error and lets it continue propagating | **Not** recovery |
| `onErrorReturn(value)` | Replaces terminal error with a fixed value | Does not resume the old upstream |
| `onErrorResume(fn)` | Switches to a fallback publisher | Placement determines the error scope |
| `onErrorMap(fn)` | Translates one exception into another | Does not keep the stream running |
| `onErrorComplete()` | Converts an error into completion | Can mask errors and lose data |
| `retry(n)` | Re-subscribes on error | Can repeat side effects |
| `retryWhen(Retry)` | Retries with conditional/backoff rules | Requires bounds, error filtering, and idempotency |
| `onErrorContinue(...)` | Drops the failing element in certain supporting operators | **Not** a safe default strategy |
| `concatMapDelayError` / `flatMapDelayError` | Delays error emission to process remaining inner publishers | Still emits terminal error; does not turn failure into success |

### 7.1. doOnError Is Strictly for Observation

~~~java
Flux<ProcessingResult> traced = results
    .doOnError(error ->
        logger.error("Processing stream failed", error)
    );
~~~

The error still propagates to the subscriber. If recovery is needed, add a dedicated recovery operator.

### 7.2. onErrorReturn Easily Hides the Cause

~~~java
Flux<Integer> mapped = Flux.just(1, 2, 3)
    .map(n -> {
        if (n == 2) throw new IllegalStateException("failed");
        return n * 10;
    })
    .onErrorReturn(-1);
~~~

The output is 10, -1, completion. There is no 30, and `-1` tells you nothing about which event failed if it lacks metadata. In business streams, a result DTO carrying `eventId` and `reasonCode` is usually far better.

### 7.3. onErrorMap Keeps Errors as Errors

~~~java
Mono<Decision> normalized = riskClient.check(event)
    .onErrorMap(java.io.IOException.class,
        cause -> new RiskServiceUnavailableException(cause)
    );
~~~

`RiskServiceUnavailableException` is an application-defined exception with a constructor taking a cause. This translates an I/O error into a clearer domain/infrastructure exception, while the publisher still ends with `onError` unless followed by recovery.

This helps callers classify errors for retries, metrics, or HTTP status mapping; avoid using `onErrorMap` to turn ordinary validation rejections into heavy exceptions unnecessarily.

### 7.4. onErrorComplete Is a Choice to Drop Errors, Not Fix Them

~~~java
Flux<String> hidden = failingSource.onErrorComplete();
~~~

When an error occurs, output completes normally. If the failure happens midway through events, consumers may mistakenly believe the whole batch succeeded. Use this only when **ignoring failures** is explicitly approved, metrics/alerts exist, and processing obligations are not violated.

## 8. Why Should onErrorContinue Rarely Be Your First Choice?

`onErrorContinue` lets supporting operators *drop the failing element and keep going*. It looks deceptively simple:

~~~java
Flux<Integer> result = Flux.just(1, 2, 3)
    .map(n -> {
        if (n == 2) throw new IllegalArgumentException("bad 2");
        return n * 10;
    })
    .onErrorContinue((error, value) ->
        logger.warn("Skipping {}: {}", value, error.toString())
    );
~~~

With `map` supporting this behavior, you may see outputs 10, 30. Yet **never treat this as a universal contract for every pipeline or error**.

Key hazards:

1. `onErrorContinue` works only on operators that explicitly support it; not every publisher handles errors this way.
2. The policy can propagate **back upstream** into operators you do not own, making behavior hard to reason about across composed functions/libraries.
3. Certain errors from asynchronous inner publishers cannot safely “drop an element and continue.”
4. When elements hold resources, discard/cleanup semantics require separate care.
5. Skipped errors can silently omit critical events without downstream noticing.
6. Refactoring a pipeline by adding `flatMap`/retries/other operators can unpredictably alter behavior.

**Preferred approach:** isolate per-element work into inner `Mono`/`Flux` publishers, place `onErrorResume` inside the lambda of `concatMap` or `flatMap`, and emit an explicit failure outcome.

### 8.1. When Is onErrorStop Used?

Reactor provides `onErrorStop` to restore standard error semantics for a pipeline segment when downstream has `onErrorContinue` active. It is an advanced escape hatch to shield a section of operators from upstream propagation, not a primary error-recovery tool.

If you do not genuinely need `onErrorContinue`, you do not need `onErrorStop`. Structuring inner publishers with explicit boundary policies is much easier to test.

### 8.2. When Is Dropping an Element Reasonable?

For telemetry or ephemeral sensor readings, dropping a bad item can be acceptable if:

- Rules clearly define which error types may be skipped.
- Metrics count dropped items and reasons.
- No business obligation is violated.
- Reconciliation or backfill data is available if needed.
- Operator and Reactor-version behavior have been verified.

For orders, payments, invoices, or auditable events, default to persisting the failed record or halting in a controlled way rather than silently dropping data.

## 9. Retrying Per Element vs. Retrying the Entire Source

`retry` and `retryWhen` do not “re-run the line of code that threw an exception.” They **re-subscribe to the publisher upstream of the retry operator**. Placement is therefore critical.

### 9.1. Outer Retry: Can Re-Process A as Well

~~~java
Flux<Decision> retriedAll = events
    .concatMap(riskClient::check)
    .retry(2);
~~~

If A succeeded and B fails, the outer publisher emits `onError`. The outer `retry(2)` can re-subscribe to **`events`**, causing A to be checked again before reaching B.

With cold sources like `Flux.just(A, B, C)`, input replay happens routinely. With hot sources or brokers, replay, offsets, and acknowledgments depend on the adapter/source.

### 9.2. Retry Inside Each Inner Publisher

~~~java
Flux<Decision> retryEach = events.concatMap(event ->
    riskClient.check(event)
        .retryWhen(
            reactor.util.retry.Retry.backoff(
                2,
                Duration.ofMillis(200)
            )
        )
);
~~~

Here retry targets **the check for the current event**, instead of re-subscribing to all of `events` just because B failed.

Still, retrying B can call `riskClient.check(B)` multiple times. If an earlier call triggered a side effect on the remote system and only its response was lost, duplicate execution can occur.

### 9.3. Retry Transient Errors, Not Business Errors

A sound policy classifies errors:

~~~java
Retry retryTransient = Retry.backoff(
        3,
        Duration.ofMillis(200)
    )
    .filter(error ->
        error instanceof TransientRiskServiceException
    );
~~~

`TransientRiskServiceException` is a hypothetical application exception. Retry transient timeouts or network errors; never pointlessly retry `INVALID_AMOUNT` or missing required fields.

Even with bounded retries, add timeouts and concurrency caps to avoid “retry storms” when many events fail simultaneously. For critical operations, pass an idempotency key across attempts.

### 9.4. Combining Per-Item Retry Then Fallback

~~~java
Flux<Decision> processed = events.concatMap(event ->
    riskClient.check(event)
        .retryWhen(retryTransient)
        .onErrorResume(error ->
            persistFailure(event, error)
                .thenReturn(Decision.unavailable(event.eventId()))
        )
);
~~~

In this pattern, `persistFailure` returns `Mono<Void>` and `Decision.unavailable` is an application-provided factory method.

- Transient errors are retried within bounds.
- Remaining errors are persisted before emitting the failure result.
- If `persistFailure` fails, the pipeline does not report false success.
- `concatMap` advances to the next event once the current publisher completes.

## 10. Delaying Errors with concatMapDelayError and flatMapDelayError

Some use cases require **processing as much work as possible before reporting a stream-end error**. Reactor provides *delay-error* variants for several flattening operators.

Example:

~~~java
Flux<Integer> delayed = Flux.just(1, 2, 3)
    .concatMapDelayError(n ->
        n == 2
            ? Mono.error(new IllegalStateException("bad 2"))
            : Mono.just(n * 10)
    );
~~~

With this finite source and inner publishers, downstream receives `10`, `30`, and then **the terminal error**. The error is not discarded; it is reported **after** the remaining allowed items finish.

### 10.1. Delay-Error Is Not Per-Item Recovery

| Goal | Implementation to consider |
| --- | --- |
| B fails; emit `Result(B, FAILED)` and process C | `onErrorResume` **inside** the inner publisher |
| B fails; still process C but fail the batch at the end | `concatMapDelayError` or an error-aggregating design |
| B fails; must stop immediately to avoid corrupt state | Default `concatMap`/`flatMap`, letting errors propagate |
| Process A–B–C concurrently, delay errors | `flatMapDelayError` with configured concurrency/prefetch |
| Ignore errors completely | Only if business policy allows, with audit/metrics |

### 10.2. Costs of Delay-Error

- Errors must be retained/aggregated for later emission, adding memory and observability overhead.
- An infinite source may never reach the point of emitting delayed errors.
- With `flatMapDelayError`, output order can still differ from source order.
- If earlier operations already committed data, a delayed error at the end does not automatically roll them back.
- The final error may combine multiple causes; downstream must log all of them rather than keeping only a short message and dropping the rest.

**Never use delay-error as a way to “guarantee all events processed successfully.”** It controls **when errors are reported**, not recovery.

## 11. Timeouts and Cancellation: Which Errors Belong to the Element vs. the Stream?

Requests to external services can hang. Two `timeout` placements carry different meanings.

### 11.1. Timeout Per Event

~~~java
Flux<Decision> decisions = events.concatMap(event ->
    riskClient.check(event)
        .timeout(Duration.ofSeconds(2))
        .onErrorResume(java.util.concurrent.TimeoutException.class,
            error -> Mono.just(
                Decision.unavailable(event.eventId())
            )
        )
);
~~~

If the call for B exceeds two seconds, B's inner publisher times out and is replaced with `UNAVAILABLE`. `concatMap` can still proceed to C.

If the system must persist failed events, never return a fallback while forgetting the durable store. Chain the failure-recording publisher before emitting the result.

### 11.2. Timeout for the Whole Batch

~~~java
Mono<java.util.List<Decision>> batch = events
    .concatMap(riskClient::check)
    .collectList()
    .timeout(Duration.ofSeconds(30));
~~~

The outermost `timeout` applies to **receiving the final batch list**, not setting two seconds per `riskClient.check`. If the batch does not complete within 30 seconds, downstream receives a timeout error and upstream is canceled.

**Warning:** cancellation does not guarantee external I/O requests rolled back; commands already started may finish on the target service. Therefore, for operations with side effects, combine client timeouts, idempotency, transaction control, and reconciliation.

### 11.3. Observing doFinally at the Right Boundary

~~~java
Mono<Decision> checked = riskClient.check(event)
    .doFinally(signal -> metrics.recordInner(signal.name()))
    .timeout(Duration.ofSeconds(2))
    .doFinally(signal -> metrics.recordOuter(signal.name()));
~~~

Depending on placement, the hook on the inner publisher can observe `CANCEL` caused by timeout, while the downstream hook observes `ON_ERROR`. Both reflect distinct boundaries without contradiction.

`doFinally` is good for measuring terminal signals; **do not** convert errors into fallbacks there or replace `usingWhen` when asynchronous cleanup is required.

## 12. Issues in Long-Lived Streams: One onError Can Halt Consumption

Suppose a reactive function receives a long-lived `Flux<OrderEvent>` from an event adapter:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<Decision>> assess(
        RiskService riskService) {

    return incoming -> incoming.flatMap(
        riskService::check,
        8
    );
}
~~~

If one `riskService.check` emits an unhandled `onError`, default `flatMap` terminates the entire output publisher with an error. Consequently, subsequent events **do not automatically continue within that subscription**.

In a long-lived event pipeline, this has far bigger consequences than in a finite HTTP request: one unchecked bad event can stop stream processing altogether.

### 12.1. Inner Recovery When You Want to Keep the Stream Alive

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<Decision>> assessResilient(
        RiskService riskService,
        FailedEventStore failures) {

    return incoming -> incoming.flatMap(
        event -> riskService.check(event)
            .onErrorResume(error ->
                failures.save(event, error)
                    .thenReturn(
                        Decision.unavailable(event.eventId())
                    )
            ),
        8
    );
}
~~~

This is a common pattern when events are independent. It still preserves a **stream-failing branch** when writing to `FailedEventStore` itself fails. That policy must be chosen deliberately.

### 12.2. Retrying the Whole Stream Is Not Resuming from the Exact Offset

~~~java
Flux<Decision> risky = incoming
    .flatMap(riskService::check)
    .retryWhen(retryPolicy);
~~~

With hot sources or brokers carrying their own offsets/acks, re-subscribing does not automatically mean “resume from the next unprocessed event.” It may replay items, drop events, or create a fresh pipeline depending on source/transport.

When reliability matters for critical events, design broker mechanics, checkpoints, partitions, transactions, idempotency, and dead-lettering under the binder contract—never rely on a trailing `retry` operator on the `Flux` for exactly-once delivery.

## 13. Consumer<Flux<T>> and Function<Flux<T>, Mono<Void>> on Errors

With a reactive `Consumer<Flux<T>>`:

~~~java
@Bean
Consumer<Flux<OrderEvent>> unsafeConsumer() {
    return incoming ->
        incoming.doOnNext(this::persistOrder).subscribe();
}
~~~

`accept` returns `void`. The consumer self-subscribes without retaining the `Disposable` or providing an explicit error handler. If `persistOrder` blocks or throws, the entire subscription can terminate; the framework has no resulting publisher to observe failures or completions.

A better approach when the caller/adapter supports a returned publisher:

~~~java
@Bean
Function<Flux<OrderEvent>, Mono<Void>> persistAll(
        ReactiveOrderRepository repository) {

    return incoming -> incoming
        .concatMap(repository::save)
        .then();
}
~~~

`Mono<Void>` emits no payload, yet provides `onComplete` or `onError` for the caller to manage.

**Note:** If the input is a long-lived `Flux` that never completes, `Mono<Void>` also will not emit normal completion for the entire stream. Pipeline completion **does not replace** per-message acknowledgment.

### 13.1. If Consumer<Flux<T>> Is Unavoidable

Manage subscription, errors, and lifecycle explicitly:

~~~java
Consumer<Flux<OrderEvent>> consumer = incoming -> {
    Disposable handle = incoming
        .concatMap(event ->
            repository.save(event)
                .onErrorResume(error ->
                    failures.save(event, error)
                )
        )
        .subscribe(
            ignored -> {},
            error -> logger.error("Consumer stream stopped", error),
            () -> logger.info("Consumer stream completed")
        );

    subscriptionRegistry.register(handle);
};
~~~

`repository.save` and `failures.save` are hypothetical APIs returning compatible publishers, and `subscriptionRegistry` is an application component tracking `Disposable` handles for shutdown cancellation. This is a sketch, not a standalone program.

If failure persistence also fails, the subscriber receives `onError` in its callback, requiring operational recovery/reconciliation rather than merely logging and ignoring it.

## 14. Errors in FunctionCatalog and Composition

Suppose we have two beans:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderEvent>> validEvents() {
    return input -> input.filter(event ->
        event.amountCents() > 0
    );
}

@Bean
Function<Flux<OrderEvent>, Flux<Decision>> evaluate(
        RiskService service) {
    return input -> input.concatMap(service::check);
}
~~~

You can select the composition:

~~~properties
spring.cloud.function.definition=validEvents|evaluate
~~~

An error in `evaluate` can terminate the composed publisher. If input arrives from a broker, how the framework handles errors outside the pipeline also depends on Spring Cloud Stream and the binder.

### 14.1. Never Use filter to Hide Errors Business Logic Needs to Record

For instance, if `validEvents` filters out `amountCents <= 0`, those events vanish from output. That is **not** fully auditable error handling. If rejected orders must be audited or generate rejection messages, change validation into `Function<Flux<OrderEvent>, Flux<ValidationResult>>` emitting an explicit outcome for each event.

For compositions, separate roles cleanly:

- **Normalization/validation step:** returns a business status for invalid input.
- **External service call step:** applies bounded retries and per-event transient error handling.
- **Persistence step:** signals completion only once the contracted storage milestone is reached.
- **Adapter:** payload/header mapping, transport errors, and acknowledgments.

A `FunctionCatalog` wrapper does not automatically turn a failing pipeline into multiple valid outputs or construct a dead-letter mechanism.

### 14.2. Isolating Error Mapping in a Dedicated Function

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<ProcessingResult>> safeEvaluate(
        RiskService service,
        FailedEventStore failures) {

    return input -> input.concatMap(event ->
        service.evaluate(event)
            .map(status -> new ProcessingResult(
                event.eventId(), status, "CHECKED"
            ))
            .onErrorResume(error ->
                failures.save(event, error)
                    .thenReturn(new ProcessingResult(
                        event.eventId(),
                        DecisionStatus.UNAVAILABLE,
                        "FAILED"
                    ))
            )
    );
}
~~~

This example uses the records and interfaces defined in Section 6. Error handling lives inside the function and is reusable across adapters, while dead-letter persistence and status codes must still fit business requirements.

## 15. HTTP, Brokers, and Serverless: Which Errors Does the Adapter See?

Spring Cloud Function decouples Java logic from protocols, **without giving every environment identical error semantics**.

| Environment | Primary error boundary | What to verify |
| --- | --- | --- |
| Direct Java call | Caller subscribes to publisher | Does it observe `onError` and handle cancellation properly? |
| `FunctionCatalog` | Catalog lookup, wrapping, and composition | Did the error occur during type conversion or inside the publisher? |
| HTTP adapter | Request/response, serialization, timeouts | Which status/body does the adapter map `onError` to? Is one result returned per item? |
| Spring Cloud Stream | Binding, binder, message delivery | Ack, retry, DLQ, offsets/partitions, and errors inside reactive pipelines |
| Serverless adapter | Single invocation with deadline | Does the runtime wait for the publisher to finish? Do errors/timeouts trigger re-invocation? |

### 15.1. HTTP: Stream Errors May Arrive After the Response Starts

In a streaming response, several elements may already be written to the connection before the publisher emits `onError`. At that point the server **cannot necessarily replace the entire response with a clean error JSON or change the HTTP status**, because headers/body chunks may already have been sent.

If the API requires a single atomic error response for a finite batch, collect results within memory/time limits before responding, trading off latency and buffering cost. Choose the API contract explicitly.

### 15.2. Spring Cloud Stream: Reactive Errors Differ from Per-Message Imperative Errors

An imperative `Function<T,R>` typically runs once per message supplied by the adapter. A reactive `Function<Flux<T>, Flux<R>>` may be invoked **once for an entire long-lived `Flux`**; errors surface later through the subscription.

Therefore, **never assume** the retry/DLQ mechanism a binder uses for imperative handler exceptions applies identically to an `onError` inside a reactive publisher. Consult binder/version docs and run integration tests.

If input is `Flux<Message<OrderEvent>>`, retain `eventId` and correlation ID in every result or failure record; avoid matching output positions to input events, especially with concurrent `flatMap`.

### 15.3. Serverless: Fallbacks Must Finish Within the Invocation Deadline

A function may retry several times while the serverless runtime enforces a hard timeout. If the publisher has not finished when the invocation ends, the platform can cancel or terminate execution without awaiting Java cleanup. Bound total duration, retries, concurrency, and items per invocation.

Never rely on fire-and-forget `subscribe()` after the handler has returned. Background errors may not be treated by the runtime as failed invocations, breaking expected redelivery behavior.

## 16. Dead-Lettering, Idempotency, and Recovery Reliability

When errors happen per element, choosing to “continue” is only safe if you know **exactly what happens to the failing element**.

### 16.1. Three Clear Strategies

| Policy | Suitable conditions | Risks to control |
| --- | --- | --- |
| **Fail-fast** | Events depend on one another; errors corrupt state | Entire stream halts; requires replay/restart support |
| **Persist error and continue** | Independent events with a durable failure store | Must never report success before saving the error |
| **Bounded retry, then persist error** | Recoverable transient failures | Duplicate side effects on retry, overload, missing idempotency |

### 16.2. Idempotency by eventId

Suppose a broker redelivers an event due to a disconnect right after the database committed. If the consumer re-processes without checking `eventId`, duplicate writes can occur.

Common design elements:

- Each event carries an immutable ID.
- The database enforces a unique constraint or an ID-keyed processing status table.
- Event processing and status updates run inside a matching transaction.
- Commit/ack messages only after reaching the defined business milestone.
- Separate validly rejected events, unprocessed events, and processed events.

`onErrorResume` by itself provides **no** exactly-once guarantee. It only transforms signals inside one subscription.

### 16.3. Never Write Dead-Letters via “Fire-and-Forget”

~~~java
// Wrong: does not await the dead-letter write publisher.
.onErrorResume(error -> {
    failedEventStore.save(event, error).subscribe();
    return Mono.just(Decision.unavailable(event.eventId()));
})
~~~

The returned publisher can emit `UNAVAILABLE` before the failure write finishes; if saving the failure fails, the caller never sees it on the same pipeline.

Better:

~~~java
.onErrorResume(error ->
    failedEventStore.save(event, error)
        .thenReturn(Decision.unavailable(event.eventId()))
)
~~~

This ties the error branch directly to **completion of the failure-persistence operation**.

### 16.4. Broker DLQ Differs from Application FailedEventStore

`FailedEventStore` in the examples is an application-implemented business mechanism. A binder may have its own dead-letter topic/queue, though error handling mode and when the broker routes a message to DLQ depend on the binder and configuration. Never assume calling `onErrorResume` inside a function triggers the binder's DLQ; once an error is recovered inside the pipeline, the adapter may no longer see an `onError`.

## 17. Observing Errors at Both Element and Stream Levels

If a pipeline successfully recovers every `RiskService` error, the stream-wide **terminal errors** counter may stay at 0 even while thousands of events failed operationally. Thus you must measure **two layers**:

| Metric group | Examples | Purpose |
| --- | --- | --- |
| Per-event | `event.processed`, `event.rejected` | Event counts by outcome |
| Per-event | `event.retry_count`, `event.fallback` | Rate of transient errors/recoveries |
| Dead-letter | `event.failed_store.success/error` | Confirm failed events were persisted |
| Stream | `stream.on_error`, `stream.on_complete`, `stream.cancel` | Subscription lifecycle |
| I/O | Timeouts, p95/p99 latency, connection saturation | Spot unstable downstream services |
| Transport | Redeliveries, acks, lag, DLQ counts | Cross-check against broker/binder |

A pattern:

~~~java
Flux<ProcessingResult> observed = incoming
    .concatMap(event -> processOne(event)
        .doOnError(error ->
            metrics.recordItemFailure(event.eventId(), error)
        )
        .onErrorResume(error ->
            recordFailure(event, error)
        )
    )
    .doOnError(error ->
        logger.error("Whole stream failed", error)
    )
    .doFinally(signal ->
        metrics.recordStreamTermination(signal.name())
    );
~~~

`processOne` and `recordFailure` are hypothetical methods returning `Mono<ProcessingResult>`. If `recordFailure` fails, the terminal error escapes outward and is captured by the outer `doOnError`.

Do not log payloads containing sensitive data merely for debugging; log `eventId`, error type, and correlation ID in a controlled manner. Avoid emitting per-ID metric tags that cause cardinality explosions; put IDs in traces/logs and keep metric tags bounded by error category or business group.

### 17.1. An onError at One Boundary Is Not Necessarily Terminal at Another

~~~java
Mono<Decision> one = riskClient.check(event)
    .doOnError(error -> metrics.innerError())
    .onErrorResume(error ->
        Mono.just(Decision.unavailable(event.eventId()))
    );
~~~

`doOnError` before `onErrorResume` observes the API error, yet the `one` publisher completes normally via the fallback. Logging “stream failed” from an inner error hook without accounting for recovery policy will mislead operators.

## 18. Testing with StepVerifier: Per-Item Errors vs. Terminal Errors

`reactor-test` provides `StepVerifier` to verify signal sequences. The tests below use JUnit 5, Java 17+, and Project Reactor without needing a real broker.

### 18.1. Outermost: Error Halts Source and Fallback Does Not Continue C

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class ErrorScopeTest {

    @Test
    void outerResumeReplacesFailedSequence() {
        AtomicInteger executed = new AtomicInteger();

        Flux<Integer> source = Flux.just(1, 2, 3)
            .map(n -> {
                executed.incrementAndGet();

                if (n == 2) {
                    throw new IllegalStateException("bad 2");
                }
                return n * 10;
            })
            .onErrorResume(error -> Flux.just(-1));

        StepVerifier.create(source)
            .expectNext(10, -1)
            .verifyComplete();

        // Number 3 never passes through the mapper.
        assertEquals(2, executed.get());
    }
}
~~~

This test proves that an outermost `onErrorResume` switches to the fallback instead of resuming the old upstream.

### 18.2. Inside Inner Publisher: C Still Gets Processed

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class PerItemRecoveryTest {

    @Test
    void recoversOnlyTheFailedItem() {
        Flux<Integer> source = Flux.just(1, 2, 3)
            .concatMap(n ->
                Mono.fromCallable(() -> {
                    if (n == 2) {
                        throw new IllegalStateException("bad 2");
                    }
                    return n * 10;
                })
                .onErrorResume(error -> Mono.just(-1))
            );

        StepVerifier.create(source)
            .expectNext(10, -1, 30)
            .verifyComplete();
    }
}
~~~

### 18.3. Continue When Dead-Letter Succeeds

Test for `OrderErrorFunctions` from Section 6:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class OrderErrorFunctionsTest {

    @Test
    void recordsFailedOrderAndContinues() {
        OrderErrorFunctions config = new OrderErrorFunctions();
        AtomicInteger failedWrites = new AtomicInteger();

        OrderErrorFunctions.RiskService service = event ->
            "B".equals(event.eventId())
                ? Mono.error(new IllegalStateException("unavailable"))
                : Mono.just(
                    OrderErrorFunctions.DecisionStatus.APPROVED
                );

        OrderErrorFunctions.FailedEventStore store =
            (event, error) -> Mono.fromRunnable(
                failedWrites::incrementAndGet
            );

        var function = config.processOrders(service, store);

        var events = Flux.just(
            new OrderErrorFunctions.OrderEvent("A", "O-1", 100),
            new OrderErrorFunctions.OrderEvent("B", "O-2", 200),
            new OrderErrorFunctions.OrderEvent("C", "O-3", 300)
        );

        StepVerifier.create(function.apply(events))
            .expectNext(
                new OrderErrorFunctions.ProcessingResult(
                    "A",
                    OrderErrorFunctions.DecisionStatus.APPROVED,
                    "CHECKED"
                ),
                new OrderErrorFunctions.ProcessingResult(
                    "B",
                    OrderErrorFunctions.DecisionStatus.UNAVAILABLE,
                    "RISK_SERVICE_FAILED"
                ),
                new OrderErrorFunctions.ProcessingResult(
                    "C",
                    OrderErrorFunctions.DecisionStatus.APPROVED,
                    "CHECKED"
                )
            )
            .verifyComplete();

        assertEquals(1, failedWrites.get());
    }
}
~~~

`Mono.fromRunnable` on the failed store is subscribed as part of the pipeline, so the test observes one failure write. With a real store, integration tests are needed to confirm that when the publisher signals complete, data is durable as designed.

### 18.4. Halt the Whole Stream When Dead-Letter Fails

~~~java
@Test
void failedDeadLetterStoreTerminatesStream() {
    OrderErrorFunctions config = new OrderErrorFunctions();

    OrderErrorFunctions.RiskService service = event ->
        "B".equals(event.eventId())
            ? Mono.error(new IllegalStateException("risk down"))
            : Mono.just(
                OrderErrorFunctions.DecisionStatus.APPROVED
            );

    OrderErrorFunctions.FailedEventStore brokenStore =
        (event, error) -> Mono.error(
            new IllegalStateException("failed store down")
        );

    var function = config.processOrders(service, brokenStore);

    StepVerifier.create(function.apply(Flux.just(
            new OrderErrorFunctions.OrderEvent("A", "O-1", 100),
            new OrderErrorFunctions.OrderEvent("B", "O-2", 200),
            new OrderErrorFunctions.OrderEvent("C", "O-3", 300)
        )))
        .expectNext(
            new OrderErrorFunctions.ProcessingResult(
                "A",
                OrderErrorFunctions.DecisionStatus.APPROVED,
                "CHECKED"
            )
        )
        .expectErrorMessage("failed store down")
        .verify();
}
~~~

This method can be added to `OrderErrorFunctionsTest` with the imports from the previous test. It confirms that the function **does not report false success** when the failure store also fails.

### 18.5. Delay-Error: Continue Emitting Values and Report Error at the End

~~~java
@Test
void concatMapDelayErrorReportsAtEnd() {
    Flux<Integer> source = Flux.just(1, 2, 3)
        .concatMapDelayError(n -> n == 2
            ? Mono.<Integer>error(
                new IllegalStateException("bad 2")
              )
            : Mono.just(n * 10)
        );

    StepVerifier.create(source)
        .expectNext(10, 30)
        .expectErrorMessage("bad 2")
        .verify();
}
~~~

This tests a finite source and simple inner publishers. `concatMapDelayError` emits the error after processing the remaining inner publishers, without **turning the failure into a successful outcome**.

## 19. Testing Backoff Retries with Virtual Time

Waiting real seconds in unit tests is slow and error-prone. `StepVerifier.withVirtualTime` lets you drive compatible Reactor schedulers when the publisher is created **inside the test supplier**.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

class RetryPerItemTest {

    @Test
    void retriesOnlyBThenContinuesC() {
        AtomicInteger bAttempts = new AtomicInteger();

        StepVerifier.withVirtualTime(() ->
                Flux.just("A", "B", "C")
                    .concatMap(id ->
                        Mono.defer(() -> {
                            if ("B".equals(id)
                                    && bAttempts.incrementAndGet() == 1) {
                                return Mono.<String>error(
                                    new IllegalStateException("temporary")
                                );
                            }
                            return Mono.just(id);
                        })
                        .retryWhen(
                            Retry.fixedDelay(
                                1,
                                Duration.ofSeconds(5)
                            )
                        )
                    )
            )
            .expectNext("A")
            .thenAwait(Duration.ofSeconds(5))
            .expectNext("B", "C")
            .verifyComplete();

        assertEquals(2, bAttempts.get());
    }
}
~~~

B fails on its first attempt and retries after five seconds of **virtual time**; A and C need no retry. This test does not simulate real HTTP client responses, databases, or broker retries/acks.

### 19.1. What StepVerifier Does Not Prove

Unit tests over pure publishers do not by themselves prove:

- Which messages the broker actually acknowledged.
- Whether an HTTP response was sent and errors mapped to the right status codes.
- Whether a dead-letter topic durably persisted records.
- Whether cancellation rolled back a database transaction.
- Whether multiple instances processing the same `eventId` are safely coordinated.

Supplement them with integration tests using production-like adapters, binders/drivers, and configurations.

## 20. Error-Policy Decision Checklist

~~~mermaid
flowchart TD
    START["An event fails"] --> CLASS{"Expected business failure?"}
    CLASS -->|Yes| DATA["Return Result(REJECTED) with eventId"]
    CLASS -->|No| RETRY{"Transient infra error,\nretry permitted?"}
    RETRY -->|Yes| TRY["Bounded retryWhen + timeout"]
    RETRY -->|No or retries exhausted| DEP{"Independent events,\nsafe to continue?"}
    TRY --> DEP
    DEP -->|Yes| STORE["Persist failure durably"]
    STORE --> OK{"Failure write succeeded?"}
    OK -->|Yes| CONTINUE["Return UNAVAILABLE and process next event"]
    OK -->|No| FAIL["onError: controlled stream halt"]
    DEP -->|No| FAIL
    DATA --> CHECK["Verify ack/retry/idempotency"]
    CONTINUE --> CHECK
    FAIL --> CHECK
~~~

Before deciding where to place `onErrorResume` or `retryWhen`, answer:

1. **What is the unit of work?** One event, one batch, or the whole stream?
2. **Is the error predictable?** Should it return a `REJECTED` result or emit `onError`?
3. **Are events independent?** If B fails, is C still safe to run?
4. **Do retries repeat side effects?** Are idempotency keys / unique constraints in place?
5. **Can events be dropped?** If not, is the failure store sufficiently durable?
6. **Is recovery placed inside the inner publisher?** Or will an outer `onErrorResume` terminate the old upstream?
7. **What if dead-lettering fails?** Should the entire stream fail loudly?
8. **When a long-lived stream fails:** who recreates the subscription and from which offset/checkpoint?
9. **Where does ack happen?** Does the broker truly know when work committed?
10. **Do converter/transport errors** enter the function or get handled separately by the adapter?
11. **Do metrics** separate per-item fallbacks from stream-level terminal errors?
12. **Do tests cover** A succeeds – B fails – C succeeds, retries, DLQ failure, timeouts, and restarts?

## 21. Common Misconceptions

| Misconception | Fact to remember |
| --- | --- |
| “`onErrorResume` at the end of a Flux skips B and continues with C.” | It replaces the failed upstream publisher with a fallback; C from the old source never runs in that subscription. |
| “If one event fails, the entire stream must stop.” | Errors can be isolated in inner publishers and recovered per event if business rules permit. |
| “`doOnError` fixes errors.” | It only observes them; the error keeps propagating. |
| “`onErrorMap` keeps the stream going.” | It translates the exception, yet still emits a terminal error without further recovery. |
| “`onErrorComplete` is always safe.” | It can hide errors and mislead downstream into thinking the batch succeeded. |
| “`onErrorContinue` works with every operator.” | Only certain operators support it, and its upstream behavior can be hard to reason about. |
| “`concatMapDelayError` ignores all errors.” | It delays the terminal error rather than turning failures into success. |
| “An outer retry only retries event B.” | It can re-subscribe to the whole source, re-processing A as well. |
| “Per-event retry never causes duplicates.” | Each attempt can repeat side effects; idempotency is required. |
| “A `Mono.empty()` fallback always means handled.” | It can make events vanish from output without any record. |
| “Sending to DLQ with `subscribe()` and returning success is enough.” | It fails to await or observe the DLQ write within the same pipeline. |
| “Stream completion means the broker acked every message.” | Reactor completion and transport acknowledgments obey separate contracts. |
| “A reactive function has the same retry behavior as an imperative handler.” | Invocation and error boundaries differ; verify with the binder. |
| “Timeouts definitely roll back sent requests.” | Cancellation may not abort or roll back external operations. |
| “Logging the final `onError` counts all failed events.” | Errors recovered per event never surface as stream-level terminal errors. |

## 22. Self-Assessment Questions

1. How does `onError` differ from `ProcessingResult(REJECTED)` at the contract level?
2. Given `Flux.just(1,2,3)` where the mapper throws at 2 and `onErrorResume` is placed at the outermost level, why is 3 never processed?
3. How can you make B fail while explicitly continuing to process C?
4. When `concatMap` processes an inner `Mono` that recovered from an error, what is the terminal outcome of the overall `Flux`?
5. How do `flatMap(..., 8)` and `concatMap` differ in ordering, concurrency, and error reactions?
6. Should `RiskService` errors and `FailedEventStore` errors follow the same policy? Why or why not?
7. When is `onErrorReturn` reasonable, and when does it lose the correlation ID?
8. Why can `onErrorContinue` cause surprises in compositions or when libraries change operators?
9. How does an outer `retry(2)` over the whole stream differ from `retryWhen` inside an inner publisher?
10. Does `concatMapDelayError` make a stream succeed after an item fails?
11. Why can a publisher timeout cause an inner hook to see `CANCEL` while downstream sees `ON_ERROR`?
12. In a long-lived stream, how can an unhandled `onError` affect reception of subsequent events?
13. Why must you wait for `FailedEventStore.save(...)` to complete before emitting `UNAVAILABLE`?
14. If a binder redelivers an event after a crash, how do you prevent duplicate side effects?
15. Why can the stream-wide terminal `onError` metric be 0 even when many items used fallbacks?
16. What `StepVerifier` test would you write to prove A succeeds, B fails and is recorded, and C still processes?
17. Why does a passing Reactor unit test not prove Spring Cloud Stream DLQ/ack behavior is right?
18. When a streaming HTTP response has already sent several items, can the server always change the status to an error?

## 23. References

- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/) — Reactive Streams, terminal signals, `onErrorResume`, `retryWhen`, and flattening operators.
- [Project Reactor — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html) — distinguishing error-handling forms, fallbacks, retries, and notes on `onErrorContinue`.
- [Project Reactor — Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html) — contracts of `concatMap`, `concatMapDelayError`, `flatMapDelayError`, and error operators.
- [Project Reactor — Testing](https://projectreactor.io/docs/test/release/reference/) — `StepVerifier` and virtual time.
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html) — imperative/reactive functions, `FunctionCatalog`, and composition.
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html) — reactive function handling and binder boundaries.

Examples use Java 17+, Spring Cloud Function, and Reactor. Specific HTTP adapter, binder, retry/DLQ, transaction, and acknowledgment behaviors must be verified against your active library versions and protocols.

**Key takeaway:** `onError` is a **subscription-terminating signal**, not a notice saying “this element failed, move along.” To recover errors **per element**, wrap each event in an inner publisher via `concatMap`/`flatMap` and place `onErrorResume`, retries, or dead-letter writes **inside** that boundary. When a failure breaks consistency or recording the failure itself fails, let the error propagate and halt the stream cleanly. In Spring Cloud Function, a publisher that handles errors does not automatically imply proper broker acknowledgments or committed transactions; design idempotency, observability, integration tests, and recovery policies tailored to each adapter.
