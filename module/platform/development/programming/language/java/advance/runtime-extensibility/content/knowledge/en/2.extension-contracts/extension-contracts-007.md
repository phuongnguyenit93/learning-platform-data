# Designing Callbacks, Events, and Unsubscription Rules in Java Runtime Extensibility

## 1. The Problem of an Extension Contract

A runtime may allow plugins to register logic at extension points: after configuration changes, before a task runs, when a resource is updated, or when a component changes state. The runtime acts as the *publisher* (emitting notifications); extensions act as *subscribers/listeners* (receiving notifications). The contract must clearly answer **who may register, when callbacks run, how errors are handled, and when registration ends**.

- **Callback** is a function invoked by the runtime under a contract (for example, `onFileChanged(event)`); it may be part of a processing request or a notification.
- **Event** is data describing something that happened, usually immutable, typed, and without requiring the publisher to know specific plugins.
- **Listener/handler** is a callback registered to receive a category of events.
- **Subscription/registration** is a specific registration instance with its own identity and lifecycle. The registration result should be an object that can be `close()`d to unsubscribe.
- **Unsubscribe** means stopping receipt of subsequent publications according to published semantics. It does not inherently cancel an in-progress task, revoke already-processed events, or wait for all running callbacks to finish.

In an extension contract, **never provide only `addListener(listener)` without an unsubscription mechanism**. A long-lived registry holds strong references to listeners, lambdas, and plugin objects; a "stopped" plugin can still receive events, and the plugin's class loader may never be released.

## 2. Designing the API and Deciding Semantics Before Writing Code

Minimal API interface example:

```java
@FunctionalInterface
interface Subscription extends AutoCloseable {
    @Override void close(); // does not declare checked exceptions
}

Subscription subscribe(Consumer<? super Event> listener);
void publish(Event event);
```

This is a **signature sketch**, not a standalone Java file; a runnable program is in Section 4. A clear contract needs to specify:

| Aspect | Rule for this article's example | Why it must be published |
|---|---|---|
| Registration | `subscribe` rejects `null`; each call creates a distinct token | The same handler may hold multiple independent registrations |
| Event publishing | `publish` rejects `null`; no history storage or replay | Users will not mistake this for an event log or message broker |
| Callback timing | Invoked **synchronously on the thread calling `publish`** | Slow handlers will slow down the publisher |
| Ordering | A publication walks registrations present in that round's snapshot in order | Does not promise global order when multiple threads subscribe/publish concurrently |
| On error | Catch `RuntimeException` per handler, forward to `onError`, and continue to other listeners | One failing plugin does not cause subsequent plugins to be skipped |
| Unsubscription | `Subscription.close()` is idempotent and removes exactly one registration | Safe to invoke multiple times during cleanup |
| Unsubscribing during publish | Loop iterates the snapshot; checks active state before each callback | Unsubscribing does not necessarily prevent a callback that already started or just passed the active check |
| Concurrency | Registry supports concurrent subscribe/close/publish; distinct `publish` calls may run callbacks concurrently | Listeners must ensure safety of their own internal state |
| Ownership | Subscriber holds the token and closes it when the plugin/object ends | Prevents "orphaned" callbacks and reference leaks |

Not every system uses these choices. With *interceptors*, "before processing" is typically an ordered callback with rejection rights and different error policies than notification events. For message delivery needing retries, acknowledgements, durable logs, or backpressure, a small event bus API like this example is insufficient.

### Callback or Event?

Use a **result-returning callback** when the runtime needs an answer to proceed (validate, authorize, transform, choose strategy). Specify deadlines, errors, ordering, and rejection rights explicitly; do not treat it as a "fire-and-forget notification".

Use a **notification event** when the runtime announces something that happened without requiring handlers to return a result. Name events in the past tense (`FileChanged`, `PluginStopped`), use typed payloads, and avoid letting listeners mutate shared data. If an "event" is actually a requirement that every handler must succeed before committing, redesign it as a synchronous workflow/contract with explicit results.

## 3. Subscription Lifecycle

A sound sequence for an extension:

1. Runtime creates the registry and publishes the event contract.
2. Plugin initializes, calls `subscribe(handler)`, and **stores the returned token** within the plugin's ownership scope.
3. Publisher constructs a complete payload and calls `publish(event)`; the registry selects active listeners and invokes callbacks per published policy.
4. When the plugin shuts down, unloads, restarts, or no longer needs notifications, the plugin calls `subscription.close()` **before releasing resources used by the callback**.
5. Runtime can continue publishing to other plugins. A second `close()` call makes no state changes.

This lifecycle must be handled on both success and startup-failure paths. If a plugin creates three subscriptions and the fourth step fails, it must close all three tokens already created. Never rely on the garbage collector to decide when to unsubscribe.

```text
Runtime / Publisher       Registry                  Plugin
        |                    |                        |
        |                    |<-- subscribe(handler) --|
        |                    |--- Subscription ------->|
        |--- publish(event) ->|                        |
        |                    |--- handler(event) ----->|
        |                    |<--- return / failure ---|
        |                    |<------ close() ---------|
        |--- publish(next) -->|   does not invoke closed subscription
```

## 4. Standalone Java 17+ Example

Save the following code to **`EventBusDemo.java`**. The example chooses `CopyOnWriteArrayList` assuming publications vastly outnumber registrations/unsubscriptions. Each registration is wrapped in a distinct `Slot` so registering the same handler multiple times never collides.

```java
import java.util.Objects;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Consumer;

public final class EventBusDemo {
    record FileChanged(String path, long revision) {
        FileChanged {
            Objects.requireNonNull(path, "path");
        }
    }

    @FunctionalInterface
    interface Subscription extends AutoCloseable {
        @Override
        void close();
    }

    static final class EventBus<E> {
        private static final class Slot<E> {
            final Consumer<? super E> handler;
            final AtomicBoolean active = new AtomicBoolean(true);

            Slot(Consumer<? super E> handler) {
                this.handler = handler;
            }
        }

        private final CopyOnWriteArrayList<Slot<E>> slots =
                new CopyOnWriteArrayList<>();
        private final Consumer<? super RuntimeException> onError;

        EventBus(Consumer<? super RuntimeException> onError) {
            this.onError = Objects.requireNonNull(onError, "onError");
        }

        Subscription subscribe(Consumer<? super E> handler) {
            Objects.requireNonNull(handler, "handler");
            Slot<E> slot = new Slot<>(handler);
            slots.add(slot);

            return () -> {
                if (slot.active.compareAndSet(true, false)) {
                    slots.remove(slot);
                }
            };
        }

        void publish(E event) {
            Objects.requireNonNull(event, "event");
            for (Slot<E> slot : slots) {
                if (!slot.active.get()) {
                    continue;
                }
                try {
                    slot.handler.accept(event);
                } catch (RuntimeException failure) {
                    onError.accept(failure);
                }
            }
        }
    }

    public static void main(String[] args) {
        EventBus<FileChanged> events =
                new EventBus<>(e -> System.out.println("ERROR " + e.getMessage()));

        Subscription audit = events.subscribe(e ->
                System.out.println("AUDIT " + e.path() + "#" + e.revision()));

        Subscription plugin = events.subscribe(e -> {
            if (e.revision() == 2) {
                throw new IllegalStateException("plugin unavailable");
            }
            System.out.println("PLUGIN " + e.revision());
        });

        Subscription metric = events.subscribe(e ->
                System.out.println("METRIC " + e.revision()));

        events.publish(new FileChanged("config.yml", 1));

        audit.close();
        audit.close(); // closing multiple times is still safe
        events.publish(new FileChanged("config.yml", 2));

        plugin.close();
        metric.close();
        events.publish(new FileChanged("config.yml", 3));
    }
}
```

Compile and run (Java 17 or later):

```bash
javac EventBusDemo.java
java EventBusDemo
```

Exact stdout for the program above:

```text
AUDIT config.yml#1
PLUGIN 1
METRIC 1
ERROR plugin unavailable
METRIC 2
```

Output explanation:

- At revision 1, all three listeners are active and run in registration order.
- `audit.close()` sets `active=false` and removes the `audit` slot from the registry; repeated calls are no-ops. Thus revision 2 has no `AUDIT` line.
- The `plugin` callback throws `IllegalStateException` at revision 2. `publish` catches it, calls `onError` to print the `ERROR` line, and still continues to `metric`.
- After closing the remaining two tokens, revision 3 produces no output. That only proves the behavior of sequential calls in `main`; **it does not prove no callback is running concurrently in a multithreaded application**.

### Why Does This Implementation Work?

`CopyOnWriteArrayList` snapshots for iterators, so adding/removing listeners never breaks an active traversal loop. `AtomicBoolean.compareAndSet(true, false)` ensures repeated token closes (even across multiple threads) run the removal logic only once. Each slot is a distinct object, so two `subscribe` calls with the same lambda yield two independently closeable tokens. `Objects.requireNonNull` surfaces invalid inputs clearly at the API boundary.

The example chooses per-listener error handling. That is a **design policy**, not something Java enforces automatically. If `onError` throws an exception, the `publish` round is aborted; if a handler throws an `Error`, the example does not catch it and it propagates. Real runtimes must decide error ownership, logging levels, metrics, alerts, and whether to report failure status to the publisher.

## 5. Unsubscription Rules: What Is Guaranteed?

### Unsubscribing Before the Next Publication

If execution is sequential—`close()` finishes before `publish(event)`—the closed slot will not be invoked. This is the easiest case to reason about and matches the example.

### Unsubscribing Inside a Callback

With `CopyOnWriteArrayList` snapshots, listener A can close its own or B's subscription while handling an event. The publication loop will not throw `ConcurrentModificationException`. When the loop reaches B, the `active` check skips B if cancellation completed before that check. A listener newly subscribed inside a callback does not appear in the currently iterating snapshot.

### Unsubscribing Concurrently with Publication

Across two threads, the interleaving can be: publisher reads `active=true`, another thread calls `close()`, and then publisher enters `handler.accept(event)`. Therefore, **`close()` does not guarantee "after returning, no callback will start or be running"** in this implementation. It guarantees the token is deactivated and removed from the registry, not that all in-flight tasks are *drained*.

If the contract requires "no callbacks still running when unload finishes", you must design additional coordination (tracking in-flight callbacks, blocking new callbacks, awaiting completion of existing ones, or appropriate locking). Handle the case where a callback itself calls `close()` carefully to avoid waiting on itself and deadlocking. A clean approach is separating `unsubscribe()` and `awaitQuiescence()`, specifying who may call the wait operation.

### Unsubscribing in Asynchronous Systems

With executors/queues, separate clearly:

- **Subscription cancellation**: stops receiving future scheduled/published events per chosen rules.
- **Canceling queued work**: requires marking items, removing them from the queue, or checking the token before execution.
- **Canceling running work**: requires coordination flags or interruption; there is no guarantee a callback stops immediately.
- **Delivery guarantees**: at-most-once/at-least-once, retries, ordering, and deduplication are independent contracts. An in-memory synchronous event bus has neither retries nor durability.

Avoid writing vague API docs claiming "unsubscribe guarantees the callback will never be called again" if the implementation only prevents future registrations/publications.

## 6. Threading, Ordering, and Performance Contracts

**Synchronous:** Every callback runs on the thread that called `publish`; no background threads are added. Simple to debug and preserves order *within a single publication*, though callbacks that sleep or block on I/O prolong the publish call. Enforce SLAs on callbacks or offload heavy work to another processing channel when needed.

**Concurrent:** Two threads can call `publish` at the same time and invoke the same handler in parallel. A thread-safe registry structure does not make handler logic automatically thread-safe. Listeners using shared state must use proper synchronization, immutable types, or concurrent data structures. If global ordering is required, add a dedicated serializer and define queuing semantics.

**Reentrancy:** A handler may call `publish` again, creating nested publications on the call stack. Without limits, self-triggering event chains can loop infinitely or overflow the stack. You can forbid reentrancy, use bounded/regulated queues, or detect cycles as needed.

**Cost of `CopyOnWriteArrayList`:** Lock-free iteration safe against concurrent edits; however, every add/remove copies the underlying array, costing CPU and allocations when the list is large or plugin churn is high. Use it only when the workload is genuinely "read-heavy, write-rare". For frequent mutations, consider concurrent maps with controlled snapshots, per-event-type partitioned registries, or other structures. Do not pick it merely because its name sounds concurrent.

**Backpressure:** A synchronous event bus pushes waiting time onto the publisher. When moving to async, producers can emit events faster than consumers handle them: you need bounded queues, block/drop/coalesce/reject policies, and metrics. Plain `ExecutorService.execute` neither imposes queue bounds nor guarantees ordering on multi-thread pools. Java's `Flow.Publisher`/`Subscriber` offers a request/demand model if a formal backpressure contract is needed, though you still must choose an appropriate implementation.

| Need | Design direction |
|---|---|
| Small callbacks, rare registration changes | Registry + synchronous dispatch + `close()` token |
| Callbacks needing to return flow-control results | Dedicated callback interface, explicit error and result policy |
| Long-running handlers, bursty traffic | Bounded queue, executor, latency and drop observability |
| Global ordering or replay required | Sequencer/event log/broker with explicit delivery contract |
| Plugin hot reload | Plugin-owned tokens, disciplined unregister, quiescence coordination if needed |

## 7. Payloads and Stability of the Extension Contract

Use meaningful event types, ideally immutable snapshot data. For instance, `record FileChanged(String path, long revision)` prevents reassigning record fields after construction; however, if a field points to a mutable collection, a record **does not automatically deep-copy the collection**. When publishing a public plugin API:

- State the meaning of each field, whether `null` is valid, whether revision ordering exists, and when the data snapshot was taken.
- Never pass mutable runtime internals and let plugins mutate them. If payloads contain lists/maps, create defensive copies such as `List.copyOf(items)`/`Map.copyOf(values)` where appropriate.
- Preserve source/binary compatibility for plugins, or version the API when changing callback types/signatures. Adding abstract methods to a public plugin interface can break older implementers; consider default methods, adapters, or a new contract version as needed.
- Never let listeners silently assume thread-local, transaction, or security contexts will persist when switching from sync to async. That is a major behavioral change.
- Bound resource access, execution time, and failure behavior for third-party plugins. Catching exceptions only isolates ordinary failures; it does not provide security, CPU, or memory isolation within the same JVM.

## 8. Managing Ownership: Plugins Must Clean Up Their Own Registrations

Using a token to bind listener lifecycle to extension lifecycle (the snippet below uses the nested types from `EventBusDemo` in Section 4 and can be placed in the same package):

```java
final class PluginAdapter implements AutoCloseable {
    private final EventBusDemo.Subscription subscription;

    PluginAdapter(EventBusDemo.EventBus<EventBusDemo.FileChanged> bus) {
        this.subscription = bus.subscribe(this::onChanged);
    }

    private void onChanged(EventBusDemo.FileChanged event) {
        System.out.println("PLUGIN ADAPTER " + event.path());
    }

    @Override
    public void close() {
        subscription.close();
    }
}
```

The core idea lies in the `subscription` field and the plugin's `close()`. If `close()` is omitted, the registry still holds a reference to the plugin instance via `this::onChanged`. With dynamic class loaders, retained objects can keep old class loaders and plugin code alive. For multiple registrations, keep a list of tokens, close them in reverse order on shutdown, and handle cleanup errors so remaining tokens are never skipped.

`try-with-resources` also fits short-scoped registrations: acquire `Subscription` in a `try (...)` block, and exiting the scope invokes `close()` automatically. For long-lived plugins, tokens normally live in fields of lifecycle-managed objects rather than a short block.

Do not use `finalize()` or rely solely on `WeakReference` to replace cleanup. Weak listeners can vanish at unpredictable times, making lost subscriptions hard to reason about; explicit ownership is a far more controllable and testable contract.

## 9. Contract Test Checklist

| Test case | What to assert |
|---|---|
| Register 2–3 handlers | Each publication invokes active handlers; verify order in a sequential run |
| Call `close()` twice | No errors, no events received after closing in sequential cases |
| Register the same handler twice | Two independent subscriptions; closing one token does not close the other |
| Handler A closes B inside callback | Does not corrupt iteration; B is skipped/run according to active and snapshot rules |
| Handler registers C inside callback | C can only receive publications starting after the current snapshot finishes |
| Handler throws `RuntimeException` | Error handler is invoked and subsequent handlers still run; also test when error handler fails |
| Multiple concurrent publishers/closers | Registry stays uncorrupted; verify exact race semantics without falsely asserting "zero in-flight" |
| Plugin unload/reload | All tokens from the old session are closed; no stale listeners remain in registry |
| Slow/self-publishing handler | Observe latency, recursion, and queue/time-budget policies |
| Payload with mutable objects | No shared data can be mutated outside the contract |

In multithreaded tests, use `CountDownLatch`/`Phaser` to coordinate contention points instead of timing guesses with `Thread.sleep`. Tests must assert the API's actual guarantees; never assert an arbitrary order decided by the OS scheduler. When strict quiescence is required, write tests proving `close-and-drain` waits for already-started callbacks to finish.

## 10. Common Design Mistakes and How to Avoid Them

1. **Having only `void addListener(...)`:** Returns no token, leaving cleanup ownership unclear. Return `Subscription`/`AutoCloseable` to express ownership.
2. **Unsubscribing via `listeners.remove(handler)` with duplicate registrations:** May remove the wrong entry or depend on `equals`. Create a dedicated slot/token per registration.
3. **Iterating an `ArrayList` and mutating it during a callback:** Risks `ConcurrentModificationException` or unpredictable behavior. Choose snapshots, synchronization, or a concurrent structure per contract.
4. **Catching exceptions and ignoring them:** Events appear to succeed while plugins silently break. Define an error channel, contextual logging, metrics, and a propagate-vs-isolate policy.
5. **Claiming "close stops all callbacks" without awaiting in-flight calls:** Creates races during resource unloading. State clearly that close only unregisters, and add quiescence when genuinely needed.
6. **Calling plugin code while holding a registry lock:** Callbacks might subscribe/unsubscribe/re-enter or wait on another lock, causing deadlocks. Avoid holding structural locks across external code calls; if locks are needed, design a strict lock order.
7. **Pushing all events onto an unbounded thread pool:** Loses control over queues, ordering, shutdown, and memory. Choose bounds and backpressure policies from the start.
8. **Letting plugins use mutable runtime objects or internal APIs:** Breaks encapsulation and harms compatibility. Provide immutable payloads and stable public interfaces.
9. **Forgetting to unsubscribe on reload:** Registry retains lambdas and old class loaders, potentially causing duplicate handling. Bind unregistration to plugin lifecycle and test unloading.
10. **Equating events with commands that must succeed:** Notification events normally have no return value; behavior requiring results/rollback should be modeled as an explicit control-flow contract.

## 11. Closing Criteria for an Extension Point

A solid contract can concretely answer: where events are emitted from; which thread callbacks run on; who owns the token; how ordering and exceptions are handled; whether `close()` awaits in-flight callbacks; whether replay/retry/backpressure exist; whether data is immutable and versioned; and what is cleaned up when a plugin unloads. Put these clauses into the API's JavaDoc and contract tests. Choose implementations so **every promise is verifiable**, especially under dynamic plugin changes and concurrent threads in the same runtime.