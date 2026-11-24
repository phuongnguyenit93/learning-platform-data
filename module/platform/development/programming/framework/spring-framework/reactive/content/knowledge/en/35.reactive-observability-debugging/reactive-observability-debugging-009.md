# Detecting Dropped Errors, Buffer Leaks, and Unsubscribed Chains

## 1. Three Distinct Failures in a Reactor Application

A reactive application can return wrong results, log errors of unclear origin, climb in direct memory usage, or fail to execute SQL/HTTP calls that a developer assumed were invoked. The three concepts in the title are related, not synonymous:

1. **Dropped error:** an error that arrives too late or no longer has a valid delivery path to the subscriber, usually because the sequence has already completed, errored, or been cancelled. That error can no longer be delivered through the chain's normal onError signal.
2. **Buffer leak:** a DataBuffer/Netty ByteBuf whose reference count remains greater than 0 after no one needs it anymore. Native/direct memory is never returned to the pool.
3. **Unsubscribed chain:** a Mono/Flux has been created and perhaps composed with several operators, yet no subscriber ever starts executing it. For a cold Publisher, side effects such as database calls, HTTP calls, or file reads have not happened yet.

| Symptom | Question to Ask | Tool / Checkpoint |
| --- | --- | --- |
| Dropped error log or error arriving after timeout | Did an error signal arrive after complete/cancel? | Hooks.onErrorDropped, doFinally, callback lifecycle |
| Netty reports LEAK: ByteBuf.release() was not called | Who owns the buffer and who must release it? | DataBufferUtils, doOnDiscard, Netty leak detector |
| No SQL/HTTP requests, doOnSubscribe does not run | Has the Publisher been subscribed to? | StepVerifier, PublisherProbe, doOnSubscribe |
| Direct memory climbs while heap is normal | Are pooled buffers unreleased, or is the pool just holding reusable regions? | Active direct memory metric, leak detector, ref count |

**Diagnostic principle:** determine the lifecycle first, then determine resource ownership. Do not use a global hook to mask business errors, do not release a buffer merely because you saw it in a log, and do not call subscribe() to force a Publisher to run without understanding who manages the subscription.

## 2. Publisher Lifecycle: Assembly, Subscription, and Termination

### 2.1. Creating a Chain Does Not Mean the Chain Has Run

Reactor operators usually create a new Publisher. A cold Publisher executes only when there is a subscriber:

~~~java
AtomicInteger executions = new AtomicInteger();

Mono<Integer> source = Mono.defer(() -> {
    executions.incrementAndGet();
    return Mono.just(21);
});

Mono<Integer> result = source.map(value -> value * 2);

System.out.println(executions.get()); // 0
~~~

Before subscribing, Mono.defer has not run. When a subscriber requests data:

~~~java
StepVerifier.create(result)
    .expectNext(42)
    .verifyComplete();

System.out.println(executions.get()); // 1
~~~

In Spring WebFlux, the framework subscribes to the Publisher returned from a handler/controller. With Spring Data R2DBC, the SQL query usually begins when the repository Publisher is subscribed to. You do not need to call subscribe() yourself in a controller/service and return Mono.empty().

Not every Publisher is cold: Sinks.Many, event listeners, and some hot sources can emit data independently of subscribers. Understand your source's semantics rather than assuming every Publisher is lazy.

### 2.2. Main Phases

~~~text
ASSEMBLY
  Flux.just(...).map(...).filter(...).checkpoint(...)
      |
      | only creates the Publisher structure
      v
SUBSCRIBE
  subscriber registers, source starts executing
      |
      v
REQUEST(n)
  downstream requests the number of items it can receive
      |
      +------ onNext(item) ------> 0..n times
      |
      +------ onError(error) ----> normal error
      |
      +------ onComplete --------> completes successfully
      |
      +------ cancel ------------> downstream no longer needs data
~~~

A chain can be created without being subscribed to; it can also be subscribed to and then cancelled before the source finishes. The two cases have different lifecycles and resource impacts.

### 2.3. doOnSubscribe and doFinally

~~~java
Mono<String> pipeline = remoteCall()
    .doOnSubscribe(subscription -> log.info("subscribed"))
    .doOnError(error -> log.error("pipeline failed", error))
    .doFinally(signal -> log.info("terminated: {}", signal));
~~~

- doOnSubscribe runs when a subscriber registers.
- doOnError observes the error signal while still letting the error continue downstream.
- doFinally runs when the sequence terminates or is cancelled; SignalType distinguishes ON_COMPLETE, ON_ERROR, and CANCEL.

These are useful lifecycle diagnostic tools. Do not put logs containing tokens, personal payloads, or sensitive data inside shared callbacks.

## 3. Dropped Errors: Errors With No Delivery Path Left to the Subscriber

### 3.1. Normal Errors Differ from Dropped Errors

An error inside a normal operator can still be delivered through Reactive Streams onError:

~~~java
Mono<Integer> result = Mono.just("not-a-number")
    .map(Integer::parseInt)
    .doOnError(error -> log.warn("parse failed", error))
    .onErrorResume(NumberFormatException.class, error -> Mono.just(0));
~~~

map produces NumberFormatException; doOnError observes the error; onErrorResume replaces the error with 0. This is normal error handling, not a dropped error.

Hooks.onOperatorError is a hook for exceptions raised while an operator processes a signal. Reactor can transform/observe the exception and continue propagating it via onError. It differs from Hooks.onErrorDropped.

### 3.2. When Is an Error Dropped?

Once a subscriber has received onComplete or onError, a second terminal signal must not be sent. Similarly, if a subscriber has cancelled, a late asynchronous callback may try to emit an error when downstream is no longer receiving signals.

Example of a contract-violating source:

~~~java
Flux<String> malformed = Flux.create(sink -> {
    sink.complete();
    sink.error(new IllegalStateException("late callback error"));
});
~~~

complete() already terminated the sequence. The error(...) arriving afterward cannot become a second onError for the subscriber. Reactor routes that error through its dropping strategy; this is a fitting case to observe via Hooks.onErrorDropped.

Real-world origins:

- A third-party SDK callback emits an error after the request has already timed out or been cancelled.
- A bridge between a callback API and Flux.create fails to stop its listener after downstream cancels.
- A Publisher/custom operator violates the single-terminal-signal rule.
- Resource cleanup or an async callback emits an error after downstream has already terminated.
- Multiple racing sources; one wins and terminates the sequence while another emits a late error.

Cancellation itself is not an error. A Publisher that honors cancellation stops emitting signals; only late or contract-violating signals create dropped situations.

### 3.3. Hooks.onErrorDropped

~~~java
Hooks.onErrorDropped(error ->
    log.error("Reactor dropped a late error", error)
);
~~~

This hook is global to Reactor in the JVM. It can be used to record late errors, collect statistics, or clean up resources attached to a dropped error. Points to keep in mind:

- It is not a replacement for onErrorResume for business errors.
- It cannot deliver the error back to a subscriber that has already terminated.
- Register once at bootstrap/configuration; avoid repeated registration that duplicates logs.
- Hooks are global state; tests must clean up global hooks after running.
- Never log raw payloads/secrets.
- When cleaning up reference-counted objects, check the exact type and ensure cleanup is idempotent.

In Reactor 3.7, dropped errors are typically logged at ERROR level by default if no custom consumer is set. Default behavior can vary by version; check the Javadoc of the Reactor version your application runs.

### 3.4. Distinguishing Three Hooks

| Hook | Invoked When | Role |
| --- | --- | --- |
| Hooks.onErrorDropped | Error cannot be forwarded because already terminal/cancelled or source emitted invalid signal | Observe/clean up late errors |
| Hooks.onNextDropped | Item arrives when operator no longer expects items, usually after terminal signal or cancellation | Observe/clean up dropped items |
| Hooks.onOperatorError | Exception thrown while operator processes onNext/onError/onComplete | Observe/transform error that can still propagate via onError |
| doOnDiscard | Operator intentionally drops items per normal semantics or drains queue on cancel/error | Clean up discarded items in a specific chain |

onNextDropped is not a hook for every item rejected by filter. For normal filter/skip cases, use doOnDiscard if the data type needs cleanup.

### 3.5. Do Not Confuse Dropped Errors with subscribe() Missing an Error Consumer

~~~java
Mono.error(new IllegalStateException("failure"))
    .subscribe();
~~~

This subscribe() overload supplies no error consumer. Reactor must use its default error handling strategy; thus the error may be logged or bubbled depending on configuration/version. Do not conclude that every error from subscribe() without an error consumer is onErrorDropped.

Clearer when you genuinely own a subscription at an imperative boundary:

~~~java
Disposable task = operation.subscribe(
    value -> handle(value),
    error -> log.error("background task failed", error)
);
~~~

The caller must manage the Disposable, cancellation, shutdown, and error policy. In business services/controllers, prefer returning the Publisher to the caller/framework rather than subscribing manually.

## 4. Handling Late Callbacks and Proper Lifecycle Cleanup

### 4.1. Bridging Callback APIs

When turning a callback API into a Flux, you must tie Reactor cancellation/disposal to stopping the callback listener:

~~~java
Flux<Event> events = Flux.create(sink -> {
    ExternalListener listener = externalApi.register(
        event -> {
            if (!sink.isCancelled()) {
                sink.next(event);
            }
        },
        error -> {
            if (!sink.isCancelled()) {
                sink.error(error);
            } else {
                log.warn("Late callback error after cancellation", error);
            }
        }
    );

    sink.onDispose(listener::close);
});
~~~

This is an illustrative snippet; ExternalListener and externalApi represent an external API. In real code:

- close()/cancel() must unregister the listener and release resources.
- Cleanup should be idempotent since it may be invoked along multiple lifecycle paths.
- Never emit onNext or onError after a terminal signal.
- If the API has concurrent callbacks, serialize signals or use the appropriate sink flavor.
- Do not merely check isCancelled() and silently drop the error without recording it; late errors still need proper observability.

### 4.2. onCancel and onDispose

FluxSink.onCancel(...) is only for cancellation. onDispose(...) runs when the sink terminates or is cancelled. Choose callbacks according to resource lifecycle; if both close the same resource, the close implementation must be safe when called repeatedly.

~~~java
Flux<String> bridge = Flux.create(sink -> {
    ExternalSubscription subscription = externalApi.subscribe(sink::next);

    sink.onCancel(subscription::cancel);
    sink.onDispose(subscription::close);
});
~~~

The snippet above is illustrative structure only. If cancel() and close() act on the same resource, ensure the two calls do not cause a double-free or double-close failure.

### 4.3. doFinally Does Not Replace Ownership-Based Resource Cleanup

doFinally is suitable for measuring duration, recording signal types, or triggering idempotent cleanup. For resources with explicit ownership rules, prefer using, usingWhen, doOnDiscard, or a dedicated resource-management API. Never rely on a logging callback to replace buffer release.

### 4.4. Error Recovery Must Be Intentional

- doOnError: observes, then the error continues downstream.
- onErrorMap: changes the exception type and still emits an error.
- onErrorResume: subscribes to a fallback Publisher and replaces the error.
- onErrorComplete: turns an error into completion; use only if business logic genuinely permits ignoring the error.
- Hooks.onErrorDropped: observes errors that no longer have a delivery path; not recovery.

Swallowing errors with onErrorComplete or onErrorResume(... -> Mono.empty()) can hide business failures. Logs, metrics, and return values should clearly reflect when an item was skipped.

## 5. Buffer Leaks: DataBuffer, ByteBuf, and Direct Memory

### 5.1. Why Do Buffers Require Manual Management?

Netty uses reference-counted ByteBufs to reuse memory regions, especially direct/off-heap memory for network I/O. Spring WebFlux provides the DataBuffer abstraction; an implementation such as NettyDataBuffer can wrap a pooled ByteBuf.

Basic reference-count rules:

~~~text
allocate buffer
    refCnt = 1
       |
       +-- retain()  -> refCnt = 2
       |
       +-- release() -> refCnt = 1
       |
       +-- release() -> refCnt = 0
                         |
                         v
                 buffer is deallocated/returned to pool
~~~

- retain() increments the reference count when a component needs to hold additional ownership.
- release() decrements the reference count.
- When the count reaches 0, the memory region is returned to the allocator/pool.
- Reading a buffer after the count reaches 0 can throw IllegalReferenceCountException.
- Never release a buffer still owned by the framework or another consumer.
- Never forget to release a buffer for which custom code took final ownership.

An object no longer reachable on the Java heap whose reference count is still greater than 0 can still hold native memory; the garbage collector does not replace release.

### 5.2. When Does a WebFlux Application Need to Care?

Standard codecs normally manage DataBuffers automatically when converting to DTOs, Strings, or byte arrays. Applications usually need to pay attention only when:

- Reading/writing DataBuffers directly.
- Writing custom encoders/decoders.
- Holding buffers in fields, collections, or queues.
- Using filter, skip, prefetch, or operators that can discard items.
- Cancelling a stream while buffers have been prefetched but not emitted downstream.
- Manually allocating buffers or calling retain().

Do not release a buffer already consumed by a codec/framework or whose ownership was transferred elsewhere. Double-release is also a bug.

### 5.3. DataBufferUtils.release and retain

~~~java
DataBufferUtils.release(buffer);
DataBufferUtils.retain(buffer);
~~~

These utilities apply reference counting only when the DataBuffer supports pooled lifecycles (PooledDataBuffer). They avoid casting and calling Netty ByteBuf directly in most application code.

Ownership principle: the last component that uses a buffer without transferring ownership must release it. If keeping a buffer beyond the current lifecycle, retain before keeping and release exactly once per owned reference.

### 5.4. Reading Multiple DataBuffers with DataBufferUtils.join

~~~java
Mono<String> readUtf8(Publisher<? extends DataBuffer> source) {
    return DataBufferUtils.join(source)
        .map(buffer -> {
            try {
                byte[] bytes = new byte[buffer.readableByteCount()];
                buffer.read(bytes);
                return new String(bytes, StandardCharsets.UTF_8);
            } finally {
                DataBufferUtils.release(buffer);
            }
        });
}
~~~

DataBufferUtils.join combines the source into one buffer (possibly composite/zero-copy depending on implementation). Source buffers are managed as components of the composite; the caller is responsible for releasing the resulting buffer after reading. If the source errors or is cancelled during join, the utility has mechanisms to release accumulated buffers.

Do not call release on each input buffer after join has taken ownership of them; that can cause a double-release.

### 5.5. Buffers Dropped by filter or Discard

~~~java
Flux<DataBuffer> nonEmpty =
    incoming
        .filter(buffer -> buffer.readableByteCount() > 0)
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
~~~

filter removes empty buffers from downstream. If the removed buffer is pooled, it must be released. doOnDiscard is a local cleanup hook; it also helps when upstream operators prefetched/queued items and must discard them due to cancellation or error.

**Position matters:** place doOnDiscard downstream of operators that can discard, so upstream operators see the cleanup hook. Not every operator supports discard; check the Discard Support section in the Javadoc of the operator in use.

### 5.6. Cleanup Must Be Idempotent

Reactor may invoke the discard hook across multiple cleanup paths. The cleanup function should be safe if the same object passes through multiple handling paths or is invoked multiple times per hook semantics.

Do not use doOnDiscard to release an object whose ownership the application already transferred to the framework. Likewise, do not add retain() "just in case" without a matching release().

## 6. Distinguishing Discard, Dropped Items, and Operator Processing Errors

| Scenario | Example | Appropriate Mechanism |
| --- | --- | --- |
| filter drops an item normally | Buffer does not meet condition | doOnDiscard |
| skip drops initial items | Byte stream with header stripped | doOnDiscard if items need cleanup |
| Operator prefetched then cancelled | Queue still holds unemitted buffers | doOnDiscard if operator supports it |
| Source emits onNext after complete | Publisher violates Reactive Streams contract | Hooks.onNextDropped |
| Source emits onError after complete/cancel | Late-arriving callback | Hooks.onErrorDropped |
| map lambda throws exception | Error while processing item | onOperatorError, then error continues via onError |
| Business service returns normal error | DB/API failure | onError, onErrorResume, retry, or propagate |

### 6.1. doOnDiscard Is Not Universal Cleanup

doOnDiscard only affects operators that support discard and items matching the registered type. It does not automatically find every dropped object in every library or custom operator.

~~~java
source
    .filter(this::isUseful)
    .doOnDiscard(DataBuffer.class, DataBufferUtils::release)
    .map(this::decode);
~~~

If a custom operator holds DataBuffers in its own collection, that custom operator must define cleanup for its collection on error/cancel. Never assume Reactor knows where objects are stored.

### 6.2. onNextDropped and onErrorDropped Are Global Hooks

Global hooks are JVM-wide and can affect multiple modules. Use them for observability or genuinely necessary protocol-level cleanup, not as a substitute for local cleanup in filter, skip, or queues.

~~~java
Hooks.onNextDropped(value -> {
    if (value instanceof DataBuffer buffer) {
        DataBufferUtils.release(buffer);
    }
});
~~~

This is an advanced example, used only when the application truly owns DataBuffers that may arrive late. The consumer must check the exact type, handle ownership accurately, and be idempotent. In normal flows, prefer per-chain doOnDiscard.

### 6.3. onOperatorError Is Not onErrorDropped

~~~java
Flux<Integer> values = Flux.just(1, 2, 0)
    .map(value -> 10 / value);
~~~

When map encounters 0, ArithmeticException can be turned into onError sent to the subscriber. If the subscriber had already cancelled earlier or the source emitted a contract-violating terminal signal, a late error may be dropped. The two situations require different diagnoses.

### 6.4. Use onErrorContinue with Caution

onErrorContinue is a specialized operator that acts upstream and works only with operators that support it. It can make error-handling scope hard to read and surprise library code that did not expect continuation. It is usually clearer to handle errors inside the inner Publisher itself:

~~~java
Flux<Result> results = ids.flatMap(id ->
    repository.findById(id)
        .doOnError(error -> log.warn("Cannot load {}", id, error))
        .onErrorResume(NotFoundException.class, error -> Mono.empty())
);
~~~

Skip NotFoundException only if the business contract permits it. Other errors still continue downstream.

## 7. Unsubscribed Chains: Common Assembly Mistakes

### 7.1. Calling an Operator and Ignoring the Returned Publisher

Wrong:

~~~java
Mono<Void> saveAndAudit(Mono<Void> save, Mono<Void> audit) {
    save.then(audit); // The new Publisher is discarded
    return Mono.empty();
}
~~~

then returns a new Publisher; it does not mutate the source in place. Because the new Publisher is neither returned nor subscribed to, no subscriber ever runs save or audit.

Right:

~~~java
Mono<Void> saveAndAudit(Mono<Void> save, Mono<Void> audit) {
    return save.then(audit);
}
~~~

### 7.2. Creating an Inner Publisher Without Returning It from the Callback

Wrong:

~~~java
return orders.flatMap(order -> {
    auditRepository.save(toAudit(order)); // cold Publisher is discarded
    return Mono.just(order);
});
~~~

Right:

~~~java
return orders.flatMap(order ->
    auditRepository.save(toAudit(order))
        .thenReturn(order)
);
~~~

An inner Publisher must be returned to operators like flatMap, concatMap, or then. Merely calling a method that returns a Mono does not mean the database operation was subscribed to.

### 7.3. Internal subscribe() Creates a Detached Stream

~~~java
public Mono<Order> create(Order order) {
    auditRepository.save(toAudit(order)).subscribe();
    return orderRepository.save(order);
}
~~~

The audit starts on a separate subscription while the caller only manages the order-saving Publisher. Consequences:

- Audit errors do not follow the returned chain.
- The caller cannot coordinate ordering, cancellation, or retries.
- Tests may finish before the audit completes.
- Transactions/reactive context are not automatically shared across two subscriptions.
- Shutdown can occur while the detached task is still running.

Better:

~~~java
public Mono<Order> create(Order order) {
    return orderRepository.save(order)
        .flatMap(saved ->
            auditRepository.save(toAudit(saved))
                .thenReturn(saved)
        );
}
~~~

### 7.4. subscribe() Is Not a Chaining Operator

subscribe() starts execution and returns a Disposable; it does not return a Mono/Flux for further composition. Normally, an application boundary such as a command-line runner, listener, or imperative integration owns the subscription.

In WebFlux controllers/reactive services, return the Publisher to the framework/caller. If an independent background task is genuinely needed, design its owner, error consumer, cancellation, lifecycle, and metrics explicitly.

### 7.5. Do Not Confuse No onNext with Not Subscribed

A Mono<Void> can run completely without emitting any item; it simply completes. To verify subscription, use doOnSubscribe, PublisherProbe, or a test probe. Do not infer non-subscription just from seeing no onNext.

### 7.6. publishOn/subscribeOn Do Not Trigger Subscription

These two operators change the execution scheduler of a chain once subscribed. They do not start a cold Publisher on their own. Adding subscribeOn(Schedulers.boundedElastic()) to a chain that nobody subscribes to still runs nothing.

### 7.7. Spring WebFlux Subscribes to the Returned Publisher Automatically

~~~java
@GetMapping("/orders/{id}")
public Mono<Order> getOrder(@PathVariable long id) {
    return orderRepository.findById(id);
}
~~~

The framework subscribes to the returned Publisher within the HTTP lifecycle. If the method subscribes manually and returns Mono.empty(), the framework sees only an empty Publisher and does not manage the detached work.

## 8. Diagnosing Non-Running Chains and Late-Arriving Errors

### 8.1. Add Lifecycle Probes at the Right Positions

~~~java
return repository.findById(id)
    .doOnSubscribe(subscription -> log.debug("findById subscribed"))
    .doOnNext(value -> log.debug("findById emitted"))
    .doOnError(error -> log.error("findById failed", error))
    .doFinally(signal -> log.debug("findById finished: {}", signal))
    .checkpoint("OrderService.findById");
~~~

If no subscribed log appears, check whether the Publisher is actually returned to the framework/caller. If subscribed appears without onNext, check whether the source can complete empty, is waiting for demand, timed out, or was cancelled.

### 8.2. checkpoint to Attach Assembly Markers

checkpoint("OrderService.findById") attaches a description to the traceback when an error passes through the chain. It is lighter than enabling global full assembly tracing.

~~~java
return service.loadOrder(id)
    .checkpoint("OrderController.loadOrder");
~~~

Variant:

~~~java
return service.loadOrder()
    .checkpoint("OrderController.loadOrder", true);
~~~

Passing true requests a full stack trace at the checkpoint, useful when pinpointing the assembly site at higher cost.

### 8.3. Hooks.onOperatorDebug()

~~~java
Hooks.onOperatorDebug();
~~~

Enables global assembly tracing. It must be enabled before creating the chains to debug; if enabled afterward, already-assembled chains lack the corresponding stack info.

This diagnostic mode carries overhead because Reactor captures stack traces when assembling operators. Use it under control in debug/test environments; do not enable it unconditionally in production without evaluating cost.

### 8.4. log() and doOnEach

~~~java
Flux<String> traced = source
    .log("orders.pipeline")
    .doOnEach(signal -> log.debug("signal: {}", signal.getType()));
~~~

log() can print subscriptions, requests, and signals. Enable it only temporarily or on narrow chains; avoid logging payloads/tokens and avoid spiking log volume.

### 8.5. StepVerifier and TestPublisher

- StepVerifier creates a subscription and verifies signals step by step.
- TestPublisher lets you emit controlled onNext, onComplete, and onError signals, including intentionally creating contract-violating sources.
- PublisherProbe verifies whether a Publisher branch was subscribed/requested/cancelled.

Do not call subscribe() in a test and assert immediately without awaiting lifecycle completion. Use verifyComplete(), verify(), or verify(Duration) for a deterministic completion point.

### 8.6. Analyzing Dropped Error Logs

When a dropped error occurs, record the exception type/message and stack trace, route/operation/correlation id (without logging secrets), timing of complete/error/cancel, timeouts/client disconnects/retries, which callback emitted the error, and whether that callback was deregistered.

Do not merely raise the log level and consider the issue handled. Use the findings to fix lifecycle or cancellation management.

## 9. Diagnosing Netty DataBuffer Leaks and Direct Memory

### 9.1. Enabling the Netty Leak Detector

During error reproduction or dedicated tests, you can run the JVM with:

~~~bash
java -Dio.netty.leakDetection.level=advanced -jar app.jar
~~~

Common levels:

| Level | Behavior | Use When |
| --- | --- | --- |
| DISABLED | Disables leak detection | Not recommended |
| SIMPLE | Light sampling, usually the default | Routine monitoring |
| ADVANCED | Also reports where the buffer was recently accessed | Investigating leaks |
| PARANOID | Tracks every allocation, very high overhead | Short/dedicated tests |

Do not enable PARANOID on high-traffic production workloads. The leak detector uses sampling and has overhead; seeing no leak logs does not prove an application has zero leaks.

### 9.2. Reactor Netty Leak Logger

~~~properties
logging.level._reactor.netty.channel.LeakDetection=DEBUG
~~~

This logger helps distinguish whether a leak lies inside Reactor Netty or after buffer ownership was transferred to the application/framework. Combine with the Netty leak detector to trace allocations/accesses.

### 9.3. Tracking Active Memory Metrics

When Reactor Netty metrics are enabled, useful gauges include:

- reactor.netty.bytebuf.allocator.active.heap.memory
- reactor.netty.bytebuf.allocator.active.direct.memory

These represent bytes currently in use inside pooled heap/direct buffers. If active memory grows steadily under similar load and does not drop after requests/streams end, that is a signal to investigate.

Distinguish:
- Pools may retain allocated regions for reuse; RSS/direct memory does not necessarily drop immediately.
- Active memory measures buffers still in use; this signal is closer to an actual leak.
- A traffic spike or large response can produce a legitimate peak.
- Compare after workload finishes, pool stabilizes, and across multiple load cycles.

### 9.4. Heap Dumps Are Not Enough for Direct Buffer Leaks

Netty direct memory can live outside the Java heap. Heap dumps do not always reveal improper ByteBuf ownership. Combine leak detectors, allocator metrics, native memory metrics, and request/connection tracing.

### 9.5. IllegalReferenceCountException

This error usually indicates a buffer was already released to 0 yet code still reads/writes it, or it was released multiple times. It differs from a leak:

- Leak: ref count fails to reach 0 when no owner remains.
- Use-after-release: code accesses the buffer after ref count reaches 0.
- Double-release: an ownership is released more times than its matching retains.

Inspect ownership transfers, retain(), release(), and which callbacks execute on both error and cancel paths.

## 10. Common Design Mistakes and Fixes

**1 — Calling a repository and discarding the Publisher.** A method returning Mono does not run by itself. Return or compose that Publisher.

**2 — Calling an operator and ignoring the return value.** Reactor chains are immutable; store/return the newly created chain.

**3 — Creating an inner Publisher without returning it from flatMap.** The inner cold Publisher is not subscribed to. Return it or chain with then.

**4 — Calling subscribe() in a service/controller.** Creates a detached flow; return the Publisher for the caller/framework to manage.

**5 — Thinking publishOn/subscribeOn starts work by itself.** They only adjust execution once subscribed.

**6 — Omitting an error consumer on a background subscription.** Errors may go to the default handler and become hard to observe. If you truly own a subscription, provide an error consumer and manage the Disposable.

**7 — Using onErrorDropped to replace onErrorResume.** Global hooks do not restore results for subscribers; handle business errors inside the chain.

**8 — Treating every onError as a dropped error.** Normal errors pass through onError. Dropped errors are signals with no delivery path left after terminal/cancel or from contract-violating sources.

**9 — Using doOnDiscard as a hook for all errors.** The hook only runs in operators with discard support. Check Javadoc and place the hook in the right position.

**10 — Releasing a DataBuffer after transferring ownership.** Can cause double-release. Only release when the current component owns the reference to return.

**11 — Forgetting to release DataBuffers when a custom decoder holds buffers.** Native memory stays pinned. Use try/finally, DataBufferUtils.join, or doOnDiscard as appropriate.

**12 — Using filter on DataBuffers without cleaning up discarded items.** Buffers removed from downstream still retain references. Add doOnDiscard if the operator supports it.

**13 — Retaining without releasing.** Reference count never drops to 0. Pair every retain with a release.

**14 — Releasing the same buffer in multiple non-idempotent callbacks.** Error/cancel may invoke cleanup repeatedly. Design ownership and cleanup cleanly.

**15 — Assuming heap dumps show every Netty leak.** Direct memory can sit off-heap. Enable the leak detector and monitor active direct memory.

**16 — Enabling PARANOID leak detection in production.** Overhead is very high. Use SIMPLE/ADVANCED per goal and reserve PARANOID for short tests.

**17 — Confusing still-reserved pooled memory with a leak.** Pools can retain memory for reuse. Track active memory, not just RSS.

**18 — Ignoring cancellation in callback bridges.** Listeners keep emitting after downstream leaves. Unregister, close resources, and block late signals.

**19 — Setting global Hooks per request.** Global hooks accumulate and affect the whole JVM. Configure once, and reset in tests.

**20 — Logging only errors without context.** Missing correlation id, route, and lifecycle makes tracing hard. Attach checkpoints and safe metadata.

## 11. Complete Maven Project: Java 17, Spring Boot 3.5.7, and Reactor Test

This project demonstrates three parts: an ignored Publisher, a dropped error after a terminal signal, and pooled DataBuffer cleanup. The project uses JUnit 5 + StepVerifier; no HTTP server startup or database connection is needed.

### 11.1. Structure

~~~text
reactor-diagnostics-demo/
├── pom.xml
├── src/main/java/example/diagnostics/
│   └── ReactiveDiagnostics.java
└── src/test/java/example/diagnostics/
    └── ReactiveDiagnosticsTest.java
~~~

### 11.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>reactor-diagnostics-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Boot 3.5.7 manages versions of Spring Framework, Reactor Core, Reactor Netty, and Netty. reactor-test is used only in test scope. The Spring WebFlux starter provides the Spring Core DataBuffer API and Netty buffer implementation.

### 11.3. ReactiveDiagnostics.java

~~~java
package example.diagnostics;

import java.nio.charset.StandardCharsets;

import org.reactivestreams.Publisher;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class ReactiveDiagnostics {

    // Deliberately broken: the composed Publisher is ignored.
    public Mono<Void> brokenSequence(
        Mono<Void> save,
        Mono<Void> audit
    ) {
        save.then(audit);
        return Mono.empty();
    }

    // Correct: the caller receives the complete chain.
    public Mono<Void> correctSequence(
        Mono<Void> save,
        Mono<Void> audit
    ) {
        return save.then(audit);
    }

    // A local discard hook releases pooled buffers filtered out upstream.
    public Flux<DataBuffer> keepNonEmpty(
        Publisher<? extends DataBuffer> source
    ) {
        return Flux.from(source)
            .filter(buffer -> buffer.readableByteCount() > 0)
            .doOnDiscard(
                DataBuffer.class,
                DataBufferUtils::release
            );
    }

    // join owns the source buffers; this method releases the joined result.
    public Mono<String> readUtf8(
        Publisher<? extends DataBuffer> source
    ) {
        return DataBufferUtils.join(source)
            .map(buffer -> {
                try {
                    byte[] bytes =
                        new byte[buffer.readableByteCount()];
                    buffer.read(bytes);
                    return new String(
                        bytes, StandardCharsets.UTF_8);
                } finally {
                    DataBufferUtils.release(buffer);
                }
            });
    }

    public Mono<String> withCheckpoint(Mono<String> source) {
        return source.checkpoint("ReactiveDiagnostics.withCheckpoint");
    }
}
~~~

brokenSequence deliberately assembles save.then(audit) without returning the new Publisher. correctSequence returns the full chain. These two methods let tests clearly show the difference between assembly and subscription.

keepNonEmpty uses doOnDiscard to release buffers removed by filter. readUtf8 uses DataBufferUtils.join, reads the content, and releases the aggregated buffer in finally.

### 11.4. ReactiveDiagnosticsTest.java

~~~java
package example.diagnostics;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;

import io.netty.buffer.UnpooledByteBufAllocator;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.core.io.buffer.NettyDataBuffer;
import org.springframework.core.io.buffer.NettyDataBufferFactory;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Hooks;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;

class ReactiveDiagnosticsTest {

    private final ReactiveDiagnostics diagnostics =
        new ReactiveDiagnostics();

    private final NettyDataBufferFactory bufferFactory =
        new NettyDataBufferFactory(
            UnpooledByteBufAllocator.DEFAULT);

    @AfterEach
    void afterEach() {
        // Global Reactor hooks must not leak into another test.
        Hooks.resetOnErrorDropped();
    }

    private NettyDataBuffer buffer(String value) {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        NettyDataBuffer result =
            bufferFactory.allocateBuffer(bytes.length);
        result.write(bytes);
        return result;
    }

    @Test
    void coldPublisherDoesNotExecuteBeforeSubscription() {
        AtomicInteger executions = new AtomicInteger();

        Mono<Integer> source = Mono.defer(() -> {
            executions.incrementAndGet();
            return Mono.just(21);
        });

        Mono<Integer> result = source.map(value -> value * 2);

        assertEquals(0, executions.get());

        StepVerifier.create(result)
            .expectNext(42)
            .verifyComplete();

        assertEquals(1, executions.get());
    }

    @Test
    void ignoredChainLeavesBothPublishersUnsubscribed() {
        PublisherProbe<Void> save = PublisherProbe.empty();
        PublisherProbe<Void> audit = PublisherProbe.empty();

        StepVerifier.create(
                diagnostics.brokenSequence(
                    save.mono(), audit.mono()))
            .verifyComplete();

        save.assertWasNotSubscribed();
        audit.assertWasNotSubscribed();
    }

    @Test
    void returnedChainSubscribesBothPublishers() {
        PublisherProbe<Void> save = PublisherProbe.empty();
        PublisherProbe<Void> audit = PublisherProbe.empty();

        StepVerifier.create(
                diagnostics.correctSequence(
                    save.mono(), audit.mono()))
            .verifyComplete();

        save.assertWasSubscribed();
        audit.assertWasSubscribed();
    }

    @Test
    void errorAfterCompleteIsSentToDroppedErrorHook() {
        List<Throwable> dropped =
            new CopyOnWriteArrayList<>();

        Hooks.onErrorDropped(dropped::add);

        Flux<String> malformed = Flux.create(sink -> {
            sink.complete();
            sink.error(
                new IllegalStateException("late callback error"));
        });

        StepVerifier.create(malformed)
            .verifyComplete();

        assertEquals(1, dropped.size());
        assertEquals(
            "late callback error",
            dropped.get(0).getMessage()
        );
    }

    @Test
    void filteredDataBufferIsReleasedByDiscardHook() {
        NettyDataBuffer kept = buffer("keep");
        NettyDataBuffer discarded =
            bufferFactory.allocateBuffer(8);

        StepVerifier.create(
                diagnostics.keepNonEmpty(
                    Flux.<DataBuffer>just(kept, discarded)))
            .expectNext(kept)
            .verifyComplete();

        assertEquals(0, discarded.getNativeBuffer().refCnt());

        // The emitted buffer is now owned by this test.
        DataBufferUtils.release(kept);
        assertEquals(0, kept.getNativeBuffer().refCnt());
    }

    @Test
    void joinedDataBuffersAreReleasedAfterReading() {
        NettyDataBuffer first = buffer("reactive ");
        NettyDataBuffer second = buffer("buffers");

        StepVerifier.create(
                diagnostics.readUtf8(Flux.just(first, second)))
            .expectNext("reactive buffers")
            .verifyComplete();

        assertEquals(0, first.getNativeBuffer().refCnt());
        assertEquals(0, second.getNativeBuffer().refCnt());
    }
}
~~~

**Key points of the tests:**

- coldPublisherDoesNotExecuteBeforeSubscription confirms the source runs only after StepVerifier subscribes.
- ignoredChainLeavesBothPublishersUnsubscribed catches calling an operator while discarding the new Publisher.
- returnedChainSubscribesBothPublishers confirms both steps are actually subscribed to.
- errorAfterCompleteIsSentToDroppedErrorHook creates a source that intentionally emits an error after complete; the global hook captures the late error.
- filteredDataBufferIsReleasedByDiscardHook verifies the reference count of the filtered-out buffer drops to 0.
- joinedDataBuffersAreReleasedAfterReading confirms input buffers are released when the aggregate is released.

Hooks.onErrorDropped is global, so the test resets it in @AfterEach. Do not run tests that mutate global hooks in parallel with other tests using the same hook.

### 11.5. Running Tests

Requires JDK 17+ and Maven:

~~~bash
java -version
mvn test
~~~

Expected result when all tests pass:

~~~text
Tests run: 6, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

This is the expected result from the example, not an executed log. The project requires no HTTP server, database, or Internet connection; tests run directly on Reactor and Netty DataBuffers.

## 12. Symptom-Driven Investigation Workflows

### 12.1. No Database or HTTP Request Observed

1. Locate the method creating the Mono/Flux.
2. Check whether the method returns the new Publisher after operators.
3. Check whether inner Publishers are returned from flatMap/concatMap.
4. Attach doOnSubscribe and doFinally.
5. Use PublisherProbe or StepVerifier to confirm subscription.
6. Search for internal subscribe() calls or a discarded chain.

### 12.2. Dropped Error Observed

1. Determine whether the error was on the normal onError path or dropped.
2. Look for timeouts, cancellations, client disconnects, and competing sources.
3. Check whether an external callback continues emitting errors after dispose.
4. Attach Hooks.onErrorDropped in an investigation environment.
5. Check whether a source/custom Publisher emits multiple terminal signals.
6. Fix lifecycle or deregister callbacks; do not just add a global logger.

### 12.3. LEAK: ByteBuf.release() was not called Observed

1. Enable Netty advanced leak detection.
2. Enable Reactor Netty leak detection logger at DEBUG.
3. Search for code directly using DataBuffer/ByteBuf or custom codecs.
4. Map ownership: allocate → retain → transfer → release.
5. Check whether filter/skip/prefetch/cancel discards buffers.
6. Add doOnDiscard or release in finally at the right spots.
7. Monitor active direct/heap memory across equivalent workloads.
8. Double-check to avoid double-release and use-after-release.

### 12.4. Direct Memory Grows Without Leak Logs

- Default leak detection uses sampling, so it does not catch every allocation.
- Pools can hold memory for reuse; active memory and allocated/reserved memory are two different concepts.
- Raise the leak detection level in a reproduction environment.
- Compare active direct memory after requests/streams complete.
- Apply repeated load and check whether memory grows linearly or plateaus.

### 12.5. Reactive Test Hangs

- Is there a source that never completes (such as Flux.never)?
- Was initial request set to 0 without calling thenRequest(n)?
- Was a Publisher left unsubscribed?
- Is a callback waiting for a signal from the very chain currently blocked?
- Is there a blocking call on the event loop?
- Add verify(Duration) so tests fail within a bounded time instead of hanging indefinitely.

## 13. Production Prevention Checklist

### Publisher lifecycle

1. Reactive methods return complete Publishers, never discarding operator results.
2. Inner Publishers are returned/composed, not merely constructed via factories.
3. Controllers/services do not call subscribe() when the framework/caller must manage execution.
4. Background subscriptions have an owner, error consumer, Disposable, and shutdown lifecycle.
5. Callback bridges stop on cancel/dispose.
6. doOnSubscribe/doFinally are placed at key boundaries.

### Error handling

7. Business errors are propagated or recovered via onErrorResume per policy.
8. doOnError is not mistaken for having handled the error.
9. onErrorDropped is used only for errors outside normal signal paths.
10. Global Hooks are registered once, reset in tests, and never log sensitive data.
11. Late callbacks are deregistered/cancelled or recorded separately.
12. Checkpoints have business-meaningful names for readable tracebacks.

### Buffer ownership

13. Every DataBuffer/ByteBuf has a clear owner.
14. Every retain() has a matching release().
15. Custom decoders/encoders handle buffers on error and cancellation paths.
16. Buffers discarded by filter/skip/prefetch are cleaned up if the operator supports it.
17. Buffers are never released after ownership transfers to the framework.
18. No double-release or use after ref count reaches 0.
19. Direct memory is monitored alongside active memory metrics.
20. Leak detectors are used appropriately for the environment and cost.

### Testing and operations

21. StepVerifier tests complete/error/cancel cases and includes timeouts.
22. Tests verify subscription, not just final values.
23. Tests assert DataBuffer reference counts to verify cleanup where applicable.
24. Tests cover late errors and global hook isolation.
25. Load tests check for buffers/queues holding memory over time.
26. onBackpressureBuffer has capacity limits and clear overflow policies.
27. Logs/metrics include correlation IDs without sensitive tokens/payloads.
28. Full operator stack traces or PARANOID leak detection are not left enabled long-term without evaluating overhead.

## 14. Self-Check Questions

1. Does creating a Mono execute SQL immediately? **No; cold Publishers run upon subscription.**
2. How do assembly and subscription differ? **Assembly builds the operator chain; subscription starts execution and propagates demand.**
3. Why can `source.map(...); return source;` drop the map logic? **map returns a new Publisher and the original source is unchanged.**
4. What problem does internal subscribe() cause? **It creates a detached subscription, isolating errors/cancellation/lifecycle from the caller.**
5. How does a dropped error differ from a normal onError? **A dropped error arrives when the subscriber can no longer receive terminal signals; a normal onError still flows through the chain.**
6. Which hook observes dropped errors? **Hooks.onErrorDropped.**
7. Which hook observes dropped items after termination? **Hooks.onNextDropped.**
8. What does Hooks.onOperatorError do? **Observes/transforms exceptions raised during operator processing that can still propagate via onError.**
9. Which scenario does doOnDiscard handle? **Cleaning up items dropped by discard-supporting operators or queues drained on cancel/error.**
10. Does doOnError replace the error? **No; it observes, and the error continues downstream.**
11. How does onErrorResume differ from onErrorDropped? **onErrorResume recovers inside the chain; onErrorDropped handles errors with no delivery path left.**
12. Why can DataBuffer cause a direct-memory leak? **Pooled buffer reference count never reaches 0.**
13. What does retain() do? **Increments the reference count.**
14. What does release() do? **Decrements the reference count and returns the buffer to the pool when the count reaches 0.**
15. When is doOnDiscard(DataBuffer.class, DataBufferUtils::release) needed? **When the operator supports discard and buffers may be dropped by filter/skip/prefetch/cancel.**
16. Does DataBufferUtils.join require releasing inputs separately after joining? **Inputs are managed as components of the aggregate; the caller releases the resulting buffer.**
17. What does IllegalReferenceCountException usually indicate? **Use-after-release or double-release.**
18. Why is a heap dump insufficient to find Netty direct buffer leaks? **Direct memory resides outside the Java heap.**
19. Which metric tracks active direct buffer memory? **reactor.netty.bytebuf.allocator.active.direct.memory.**
20. How does checkpoint("name") help? **Attaches an assembly marker to the traceback when an error occurs.**
21. When should Hooks.onOperatorDebug() be used? **Investigations needing global assembly stacks; must be enabled before creating chains and its overhead accepted.**
22. Why must global Hooks be reset in tests? **Hooks are JVM-wide and can interfere with other tests.**
23. Should PARANOID leak detection be left on long-term in production? **No; overhead is very high, making it suitable for dedicated tests.**
24. Is a buffer pool still holding memory always a leak? **No; check active memory and trends after the workload finishes.**

## 15. Summary and References

- **Dropped error** is an error arriving when the sequence can no longer forward onError, typically after termination/cancellation or from a contract-violating source. Hooks.onErrorDropped only aids observation/cleanup; normal business errors must be handled inside the chain.
- **Discard** refers to items dropped by operators per normal semantics or drained from queues on cancel/error. Use doOnDiscard with resource types needing cleanup and operators that support discard.
- **Buffer leak** occurs when a pooled DataBuffer/ByteBuf's reference count fails to reach 0. Determine ownership and pair retain/release properly.
- **Unsubscribed chain** is an assembled Publisher with no subscriber; cold side effects have not executed. Return/compose Publishers instead of discarding results or calling detached subscribe.
- StepVerifier, TestPublisher, PublisherProbe, checkpoint, doOnSubscribe, and doFinally are useful tools for verifying lifecycle.
- Netty leak detector, Reactor Netty leak logger, and active memory gauges help investigate direct memory.
- Never use global Hooks as error recovery, never use subscribe() to force chains to run, and never release a buffer whose ownership was already transferred.

**Official Documentation**

1. [Project Reactor 3.7 — Using Global Hooks](https://docs.spring.io/projectreactor/reactor-core/docs/3.7.x/reference/html/advancedFeatures/hooks.html): onErrorDropped, onNextDropped, onOperatorError, and assembly hooks.
2. [Project Reactor 3.7 — Dealing with Objects that Need Cleanup](https://projectreactor.io/docs/core/3.7.x/reference/html/advancedFeatures/cleanup.html): doOnDiscard, onOperatorError, onNextDropped, and operator-specific cleanup.
3. [Project Reactor 3.7 — Debugging Reactor](https://projectreactor.io/docs/core/3.7.x/reference/html/debugging.html): checkpoint, Hooks.onOperatorDebug, and assembly tracebacks.
4. [Project Reactor 3.7 — Testing](https://projectreactor.io/docs/core/3.7.x/reference/html/testing.html): StepVerifier, TestPublisher, and subscription verification.
5. [Spring Framework 6.2 — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/6.2/core/databuffer-codec.html): PooledDataBuffer, DataBufferUtils, retain/release, and cleanup on discard/cancel.
6. [Spring Framework 6.2 — WebFlux Reactive Core](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html): DataBuffer ownership in WebFlux.
7. [Netty — Reference Counted Objects](https://netty.io/wiki/reference-counted-objects.html): ByteBuf lifecycle, retain/release, and troubleshooting buffer leaks.
8. [Reactor Netty — Frequently Asked Questions: Memory Leak](https://docs.spring.io/projectreactor/reactor-netty/docs/current/reference/html/index.html#faq.memory): leak detector, _reactor.netty.channel.LeakDetection_ logger, and active memory metrics.
