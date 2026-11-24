# Specifying Resource Ownership, State, and Concurrency in Java Extension Contracts

In runtime extensibility architectures (dynamically loaded SPIs, plugins, adapters, hooks, or handlers), the host invokes extension code, yet both sides can have different lifecycles, execution threads, and resources. An interface declaring only method signatures is insufficient. An extension contract must explicitly answer: **who owns each resource**, **at what scope state exists**, and **how the host may invoke the extension concurrently**.

The goal of this article is to design a contract concrete enough that the host can initialize, reuse, stop, reload, and test extensions without leaking resources, corrupting data, or introducing race conditions.

## 1. Distinguishing Actors and Scopes of Responsibility

- **Host (runtime/container):** the application coordinating provider discovery, instance creation, execution context provisioning, request dispatch, load limits, and deciding when to start/stop extensions.
- **Provider/extension:** the implementation registered with or loaded into the host; executes business logic per the agreed interface and releases resources it owns.
- **Caller:** code asking the host to use an extension. A caller may be external to the host or an internal component; the caller does not necessarily manage the provider instance lifecycle.

For example, the host uses `ServiceLoader<Transformer>` to locate a provider. `ServiceLoader` supplies the provider discovery/instantiation mechanism; **it does not define whether the provider is thread-safe, does not stop background tasks, and does not call `close()` on the provider**. Those responsibilities belong to the contract between host and provider. `ServiceLoader` itself is also not designed for arbitrary concurrent manipulation by multiple threads; iteration/loading should be managed by the host separately from invoking provider instances.

A solid specification must state rules per **instance** and per **active session**. Registering a provider once does not imply only one instance exists: the host may create one shared instance, one instance per tenant, or one instance per request.

## 2. Specifying Resource Ownership

**Ownership** is the responsibility for managing a resource's lifecycle: creating/allocating, valid usage, stopping usage, closing, and handling errors during close. Permission to *borrow and use* does not automatically grant permission to *close or reconfigure*.

| Resource | Typical owner | Responsibility to state in the contract |
| --- | --- | --- |
| `ExecutorService`/scheduler passed by the host | Host | Extension only submits tasks within quota; never calls `shutdown()` on a borrowed executor |
| Connection pools, shared HTTP clients, metrics registries, host config | Host or shared management component | Extension must not close or mutate global state unless explicitly permitted by the API |
| Files/sockets/background threads/caches opened and held by the provider | Provider | Provider closes/cancels them on time; unregisters listeners, jobs, and references upon unload |
| Buffers, parsers, or objects created for a single call | Creator, or receiver if ownership is explicitly transferred | Closed within call scope or transferred via explicit documentation/API |
| `InputStream`/`Stream`/cursor returned from an API | Must be explicitly named by the contract | Who closes it, when, and whether it may be read after the method returns |
| Dedicated `ClassLoader` used to load a plugin | Creator/manager of the loader, usually the host | Close the loader only after the extension stops and related references are released |

### 2.1. Three Common Ownership Models

**Host-owned, provider-borrowed:** the host passes an `Executor`, `Clock`, configuration, logger, or shared client to the provider. The provider may use them during the permitted window; it must never close those resources. If the provider must store a reference for asynchronous execution, the contract must permit and bound how long the reference may be held.

**Provider-owned:** the provider opens its own sockets, registers listeners, or creates private caches and threads. When stopping the provider, it must stop accepting new work, complete or cancel in-flight work, unregister callbacks, close resources, and clear long-lived references. If initialization fails partway through, any already-opened resources must also be released.

**Ownership transfer:** a method returns a resource-backed object, such as an `InputStream`. You must specify that the receiver is responsible for `close()`, its valid lifetime, and what happens if the result is ignored. If you prefer not to transfer closing obligations to the caller, return a DTO or materialized value instead.

Both sides calling `close()` can cause premature closing or double-close; both sides waiting on the other causes leaks. `AutoCloseable` provides a standard close hook in Java, but **does not automatically guarantee `close()` is idempotent or thread-safe**. If repeated closing must be allowed, document and implement that explicitly in the contract.

### 2.2. Minimum Clause Checklist

For every extension API, publish:

1. Who creates and owns extension instances; how many requests/tenants a single instance spans.
2. Which resources are borrowed from the host, for how long; whether the provider may retain them after the method returns.
3. Which resources the provider must close itself; the order of stopping tasks, unregistering callbacks, and closing resources.
4. Whether returned results transfer ownership to the caller.
5. Behavior on initialization failure, error handling, timeouts, task cancellation, and repeated closing.
6. When the host may remove the provider from the registry and release its class loader.

Do not rely on method names like `getClient()` or `open()` to guess ownership: document it explicitly in Javadoc, SPI specs, and lifecycle tests.

## 3. Specifying State and Lifetime Scope

**State** includes configuration data, caches, counters, sessions, lookup maps, and objects that can change across calls. Before declaring a provider "thread-safe", identify which state is shared.

| Scope | Example | How to manage |
| --- | --- | --- |
| Immutable per instance | Validated config, routing rules, `Clock` | Initialize completely then safely publish; never mutate while running |
| Per-call only | Request DTO, temporary buffer, trace ID | Create inside the call; do not store in instance fields unnecessarily |
| Shared within one instance | Cache, counters, listener list | Use concurrent data structures or synchronization and close rules |
| Per-tenant/session | Credentials, per-tenant cache, session state | Partition by identifier with capacity bounds and cleanup policies |
| JVM/process-wide | `static` registries, threads, global singletons | Avoid by default; requires explicit multi-tenant, classloader, and cleanup contracts |

**Prefer minimizing shared mutable state:** immutable configuration, immutable requests/responses, and temporary data scoped to the invocation. Java `record` helps model DTOs, but provides only shallow immutability: a `record` containing a `List` can still be mutated unless the inner data is copied or frozen.

When shared state is unavoidable, choose primitives based on the invariant to protect:

- `AtomicInteger`/`LongAdder` for suitable counters; `LongAdder` performs well under high contention, though an instantaneous sum is not a strict linearizable snapshot across concurrent updates.
- `ConcurrentHashMap` for concurrent map access per its contract; compound operations across multiple keys may still require locking or dedicated transaction design.
- `synchronized`/`Lock` when multiple fields must change together to preserve one invariant; avoid invoking external provider callbacks while holding locks.
- `volatile` to publish/read simple state like a stop flag—it does **not** make `count++` atomic. `count++` is read-add-write, so updates can be lost even if `count` is declared `volatile`.

Initial state must be **safely published**: never let `this` escape the constructor, use `final` fields appropriately, and register the instance only after construction completes. Never allow background tasks to read partially constructed configuration.

**Hot-reload warning:** `static` caches, `ThreadLocal`, listeners, timers, threads, and lambdas retained by host singletons can pin old classes or class loaders, preventing the plugin from being garbage-collected. Unregister callbacks, release objects, and call `ThreadLocal.remove()` on the right threads whenever possible; do not use `ThreadLocal` as request state storage across executor/asynchronous boundaries without explicit context propagation.

## 4. Specifying Concurrency Guarantees

"Callable from multiple threads" can mean several different things. The contract must pick **one invocation model per instance** and separate concurrency from reentrancy.

| Model | What may the host do? | What must the provider guarantee? |
| --- | --- | --- |
| **Concurrent shared instance** | Invoke `execute()` concurrently from multiple threads on the same instance | All shared data and side effects preserve published consistency guarantees |
| **Serialized per instance** | At most one active call per instance at a time | Provider may use sequential state; host is responsible for queuing/locking per instance |
| **Thread-confined** | Invoke only from a designated thread/dispatcher | Host maintains affinity; never switch threads arbitrarily across callbacks |
| **Per-call instance** | Create a dedicated instance per request or unit of work | No shared mutable state across instances unless explicitly designed with concurrent structures |

**Do not confuse "serialized" with "always the same thread":** the host may execute sequential calls on different threads one after another. A provider relying on `ThreadLocal` or thread affinity must explicitly require the thread-confined model.

**Do not confuse "thread-safe" with "reentrant":** a provider may safely handle independent concurrent calls yet break if one call invokes back into the same provider before the first call completes. Specify whether host callbacks can happen synchronously/asynchronously, whether nesting is allowed, and whether locks may be held during callbacks. Hosts are advised to avoid calling extension code while holding global locks to reduce deadlock and lock-inversion risks.

For asynchronous APIs, the contract must additionally state:

- Whether results use `CompletionStage`, `Future`, callbacks, or publishers; who chooses the executor for continuation steps.
- Maximum number of in-flight calls; queuing/backpressure policy under overload to avoid unbounded threads and queues.
- What timeouts apply to; whether the provider must cooperate by checking interrupts/cancellation tokens upon cancellation.
- Whether requests/results may be accessed concurrently or mutated after submission.
- Whether retries may re-run a call that already had side effects; whether idempotency keys or deduplication are needed.

In Java, `Thread.interrupt()` is a cooperative signal, not a forced kill for all I/O or tasks. Providers must handle `InterruptedException` properly and avoid swallowing interrupts. The host must not close resources still in use by a task solely because cancellation was requested.

## 5. Lifecycle: Initialize, Run, Stop, and Reload

A simple state machine **per instance**:

~~~text
CREATED -> STARTED -> QUIESCING -> CLOSED
             |
             +---- failure ----> QUIESCING -> CLOSED
~~~

- **CREATED:** host constructs the provider and passes valid config/context; provider does not receive requests yet. If construction or startup fails, clean up partially created resources.
- **STARTED:** instance is ready; host publishes it in the registry and may dispatch requests per the declared concurrency model.
- **QUIESCING:** host stops admitting new work to the instance, awaits or cancels in-flight work per published policy, and only then runs cleanup.
- **CLOSED:** provider-owned resources are released; host drops references, listeners, registry entries, and finally disposes of a host-owned class loader once no longer used.

A safe shutdown sequence typically follows:

1. **Stop dispatching new requests** and close callback entry points into the old instance; swap registry entries atomically during hot swaps.
2. **Track in-flight calls** and wait for completion, or issue cancellation and confirm they have stopped. If a timeout expires while tasks still use resources, apply a policy to retain/quarantine the instance or isolate the process; never arbitrarily free in-use resources.
3. **Let the provider close its own resources**, ideally in reverse order of opening. Log close failures without skipping cleanup of remaining resources.
4. **Unregister and drop references**, and only then let the host release its own resources once no consumers remain.

Never invoke `close()` concurrently with `execute()` unless the interface explicitly declares and implements that model. A `closed` flag only catches requests arriving after close; **it does not replace draining in-flight calls**.

When modules reload frequently, the new version can be instantiated and validated first, after which the host switches routing to the new version and drains the old version. Do not reuse old provider state if formats, class loaders, or versions are incompatible; state transfer must be a separate explicit contract.

## 6. Runnable Java 17 Example: Host Owning the Pool and Provider Lifecycle

The following example demonstrates an extension handling multiple concurrent requests. The host owns the `ExecutorService`, creates and closes the extension instance; the extension owns an `AtomicInteger` counter and lifecycle flag. The contract of `apply()` allows concurrent calls **while the instance is active**; `close()` is called only after the host has stopped submitting and awaited completion of all tasks. Both results are read in submission order, so stdout is deterministic.

Save as `ExtensionOwnershipDemo.java`:

~~~java
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class ExtensionOwnershipDemo {
    record Request(String text) {
        Request {
            Objects.requireNonNull(text, "text");
        }
    }

    interface TextExtension extends AutoCloseable {
        // May run concurrently with other apply calls on this instance.
        // close() is called only after the host has drained all calls.
        String apply(Request request);

        int calls();
        boolean isClosed();

        @Override
        void close();
    }

    static final class UppercaseExtension implements TextExtension {
        private final AtomicInteger calls = new AtomicInteger();
        private final AtomicBoolean closed = new AtomicBoolean();

        @Override
        public String apply(Request request) {
            Objects.requireNonNull(request, "request");
            if (closed.get()) {
                throw new IllegalStateException("Extension already closed");
            }
            calls.incrementAndGet();
            return request.text().toUpperCase(Locale.ROOT);
        }

        @Override
        public int calls() {
            return calls.get();
        }

        @Override
        public boolean isClosed() {
            return closed.get();
        }

        @Override
        public void close() {
            closed.set(true); // Idempotent by this implementation's contract.
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        UppercaseExtension extension = new UppercaseExtension();

        try {
            List<Future<String>> results = List.of(
                pool.submit(() -> extension.apply(new Request("java"))),
                pool.submit(() -> extension.apply(new Request("spi")))
            );

            // Await each task; printing in submission order is deterministic.
            for (Future<String> result : results) {
                System.out.println(result.get());
            }
        } finally {
            // The host stops its own executor before closing the provider.
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                        "Tasks still running: provider cannot close safely"
                    );
                }
            }

            extension.close();
            System.out.println("calls=" + extension.calls());
            System.out.println("closed=" + extension.isClosed());
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~text
javac ExtensionOwnershipDemo.java
java ExtensionOwnershipDemo
~~~

Stdout of the `java` command:

~~~text
JAVA
SPI
calls=2
closed=true
~~~

**Key takeaways from the example:**

- `Request` holds only an immutable `String`; two independent requests have no input memory contention.
- `AtomicInteger` protects the call count when `apply()` runs from multiple threads; using `int calls` with `calls++` would not guarantee accurate results under concurrent increments.
- `AtomicBoolean` tracks closed state and makes `close()` idempotent in **this specific implementation**. It does not prevent a race between `apply()` and `close()` if the host violates lifecycle ordering.
- The host keeps the `Future` handles, shuts down the executor, awaits termination, and only then invokes the provider's `close()`. The provider never calls `shutdown()` on a host-owned pool.
- When tasks fail to stop after the timeout, the example **does not close the provider** because tasks may still be using it; a real system needs additional logging, quarantine, or process isolation. If the `main` thread is interrupted while waiting, a real system also needs an appropriate cancellation/interrupt-restoration policy before releasing resources; that recovery branch is omitted from this normal-execution scenario.

This is a simple lifecycle-synchronization example, not a complete plugin framework. When adding `start()`, callbacks, or hot reload, extend the state machine and in-flight tracking accordingly.

## 7. Common Design Mistakes

| Symptom | Why it is wrong | How to fix |
| --- | --- | --- |
| Provider calls `shutdown()` on a host-supplied executor | Breaks work of other extensions | Specify borrowed resources: providers have no permission to close them |
| Provider stores the request in a singleton `currentRequest` field | Later calls overwrite earlier requests | Use local variables or per-request partitioned state |
| Using `volatile int count` then `count++` | Provides visibility but not atomicity | Use `AtomicInteger` or a lock |
| Calling `close()` immediately upon registry swap, ignoring in-flight calls | Resources close while tasks still use them | Transition to QUIESCING, drain, then close |
| Relying on `ThreadLocal` to pass context across executors | New threads do not inherit context; pooled threads retain stale data | Pass context explicitly and clean up on the right thread |
| Registering listeners/schedulers in `start()` without unregistering | Leaks instances/class loaders after reload | Clean up symmetrically with registration |
| Documenting "thread-safe" without mentioning `close()` | Host might close while processing is active | Explicitly document relationships among execute, callback, cancel, and close |
| Retrying every failure without considering side effects | Can duplicate writes, payments, or notifications | Design idempotency or classify non-retryable operations |
| Provider holds a lock and calls back into host; host holds another lock and calls provider | Easily causes deadlocks from inconsistent lock ordering | Shrink lock scope; invoke callbacks outside critical sections |
| Mixing multi-tenant state in a `static HashMap` | Introduces both races and cross-tenant/session data leaks | Partition, synchronize access, and clean up per tenant |

## 8. Template Clauses for SPI Documentation

For a specific extension point, you can document rules using the following template, adjusting values to match the actual design:

| Attribute | Example clear contract |
| --- | --- |
| Instance scope | Host creates **one instance per tenant** and reuses it across that tenant's requests |
| Host-provided resources | `Executor` and `Clock` are borrowed; provider must not close or retain them past `close()` |
| Provider-owned resources | Local cache and listeners; registered in `start()`, unregistered in `close()` |
| State | Immutable configuration; bounded concurrent cache; request state strictly in local variables |
| Concurrency | `execute()` may run concurrently on the same instance; callbacks may run on different threads |
| Reentrancy | Synchronous callbacks calling back into `execute()` on the same instance are disallowed, or support must be explicitly declared |
| Blocking | `execute()` must not block host threads beyond the published budget; long work must use the async API |
| Cancel/timeout | Host signals cancellation; provider cooperates to stop and returns errors/cancellation per convention |
| Shutdown | Host blocks new requests, awaits all in-flight calls, and then invokes `close()` once |
| Failure | Exceptions are categorized; resources opened during a failed start must be closed |
| Hot reload | Old instance drains and unregisters callbacks before the host releases the class loader |
| Testing | Concurrency, close under load, failed start, retry, timeout, tenant isolation, and unload |

This template is an **example for writing contracts**, not an implicit rule of every Java SPI. Each extension point must select the model suited to its purpose and clearly note any differences.

## 9. Testing the Contract Before Admitting Plugins

An integration test suite should verify all three groups of obligations:

1. **Ownership:** providers never close host-owned resources; all provider files/connections/listeners/threads are cleaned up on normal shutdown and startup failure; repeated start/stop/reload cycles do not increase live thread or resource counts.
2. **State:** identical inputs yield correct results; per-request/per-tenant state never leaks across boundaries; counters/caches remain valid under load; no mutable state is published during partial construction.
3. **Concurrency:** issue hundreds or thousands of concurrent requests according to the declared model; test nested callbacks if allowed; test timeouts, interrupts, cancellations, retries, draining, and errors during close. Run repeatedly to catch races; never treat a single passing run as proof of thread safety.
4. **Lifecycle:** stop accepting new requests before close; ensure no task accesses resources after close; ensure reloads do not pin old class loaders via listeners, threads, caches, or `ThreadLocal`. When using thread dumps, heap dumps, or metrics to verify, compare snapshots across multiple cycles.
5. **Compatibility:** swap the provider for another implementation of the same interface while ensuring the host still honors scope, ownership, and concurrency contracts without accidentally relying on implementation details of the previous provider.

When designing a new extension point, write down ownership, state scope, concurrency/reentrancy, and shutdown rules **before implementing the interface**. Valid Java signatures only guarantee type compatibility; these rules are what make extensions operate safely in a real runtime.