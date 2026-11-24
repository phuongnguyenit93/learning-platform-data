# Canceling Callbacks, Schedules, Executors, and Closing Plugin-Owned Resources

## 1. Why Is Stopping a Plugin Not as Simple as Calling stop()?

A plugin in an application can be dynamically loaded, initialized, enabled, and then disabled or replaced by the host **without restarting the JVM**. While active, the plugin may register listeners on the host's event bus, schedule recurring tasks, create threads/executors, open connections, or hold other `AutoCloseable` resources. Merely changing state from `ACTIVE` to `STOPPED` does not automatically cancel those things.

If a callback remains in the host's registry, the registry can keep calling into a “stopped” plugin. If a task or thread is still running, it can retain the plugin object, `Class<?>`, or old classloader. Removing a JAR from the plugin list does not mean the JVM has freed its classes. Therefore, **lifecycle management must include deregistration, work cancellation, and actual resource closing**.

Four categories to control:

| Plugin-Owned Category | Mechanisms That Can Create It | Appropriate Termination Action |
|---|---|---|
| Callbacks / listeners / subscriptions | `eventBus.register(...)`, `addListener(...)`, host callbacks | Invoke corresponding `unsubscribe()` / `close()` / `removeListener(...)` handle |
| Schedules / deferred tasks | `ScheduledExecutorService.schedule(...)`, `scheduleAtFixedRate(...)`, host timers | Retain `ScheduledFuture<?>` or token and call `cancel(...)` |
| Executors / worker threads | `ExecutorService`, `ScheduledExecutorService`, self-created threads | Stop accepting tasks, `shutdown()` or `shutdownNow()` per policy, `awaitTermination(...)`, ensure workers actually exit |
| I/O resources and external registrations | Files, streams, sockets, watchers, DB connections, `AutoCloseable`, hooks/registries | `close()`/`dispose()`/`unregister()` per API, usually in reverse order of allocation |

**Ownership principle:** whichever component **creates or is delegated management authority over a resource** is responsible for closing/reclaiming that resource. Plugins must not arbitrarily close **shared host-owned** executors or connections; instead, plugins cancel their own tasks/subscriptions and return control to the host.

## 2. Safe Shutdown Order

A practical sequence:

```text
Host requests STOP / UNLOAD
          |
          v
Mark STOPPING, block new work
          |
          v
Unregister listeners/callbacks on host
          |
          v
Cancel schedules and queued tasks
          |
          v
Stop plugin-owned executors/workers
          |
          v
Wait for running work to finish (bounded wait)
          |
          v
Close I/O resources, sessions, connections, watchers
          |
          v
Drop references from host/registry/cache, state STOPPED
          |
          v
Only once references are gone can GC/classloader unloading occur
```

The exact sequence depends on resource dependencies. The key is **never closing an object while a task is still using it** and letting that task keep running. Sometimes a resource must be closed early to wake up a worker blocked on I/O; the host should design an explicit stop protocol for that case.

### 2.1. Block New Work First

Upon receiving a stop signal, set `accepting=false` (for example with an `AtomicBoolean`), transition state to `STOPPING`, and reject new task submissions. If done in the reverse order, a running callback can keep scheduling new work right after the host cancels old tasks.

A minimal check inside a callback:

```java
if (!accepting.get()) {
    return;
}
handleEvent(event);
```

This is an **illustrative snippet**: `accepting` is an `AtomicBoolean`, while `event` and `handleEvent` are application-defined. Checking a flag is not enough to prove no callbacks are currently executing: a callback may have passed the check just before the host set the flag to false. For plugins with strict stop requirements, you must **wait for or coordinate in-flight callbacks** before closing resources they use.

### 2.2. Unregister Where Registered

If a plugin registers on the host's event bus:

```java
AutoCloseable subscription = eventBus.register(listener);
```

retain the **registration handle** so you can call `subscription.close()` when stopping. This is an illustrative host-defined API, not a universal API across all event buses.

Real APIs vary: `removeListener(listener)`, `unsubscribe()`, `Disposable.dispose()`, `Registration.close()`. Crucially, retain the exact listener/registration token; creating a new lambda with identical code **is not guaranteed** to remove the previously registered lambda.

```java
// NOT guaranteed to remove the registered listener:
bus.addListener(event -> onEvent(event));
bus.removeListener(event -> onEvent(event)); // different lambda object!
```

This is an **intentionally wrong** example solely illustrating lambda identity. The right way is to store the listener or handle:

```java
Consumer<Event> listener = event -> onEvent(event);
bus.addListener(listener);
// ... on stop:
bus.removeListener(listener);
```

This snippet assumes `Event`, `bus`, and `onEvent` exist in the host API.

**Unregistering does not always mean drained:** if the system copied the listener list for dispatch, an invocation can still run after `removeListener` is called. The plugin manager must combine blocking new work, draining in-flight invocations, or a policy allowing completion before resources are closed.

## 3. Canceling ScheduledFuture: cancel Is a Request, Not Forced Termination

When creating a task:

```java
ScheduledFuture<?> heartbeat = scheduler.scheduleAtFixedRate(
        this::sendHeartbeat, 0, 10, TimeUnit.SECONDS);
```

save `heartbeat`. When stopping:

```java
heartbeat.cancel(true);
```

`Future.cancel(mayInterruptIfRunning)` semantics:

- `cancel(false)`: attempts to cancel runs that have not started; if the task is running, does not request interrupting its thread.
- `cancel(true)`: also **requests interruption** of the thread running the task; there is no guarantee task code will exit immediately. Some tasks do not support interrupts, ignore interrupts, or handle I/O differently.
- `cancel` returns a `boolean` reflecting the Future's cancellation state; `true` does not mean all task side effects were rolled back or task code has stopped completely.
- `isCancelled()` and `isDone()` help observe Future state, yet a task that received an interrupt may still need time for cleanup.

Task code should **cooperate with cancellation**, such as checking `Thread.currentThread().isInterrupted()` in loops; if catching `InterruptedException` without propagating it, restore the interrupt flag via `Thread.currentThread().interrupt()` and exit at a safe point.

```java
try {
    Thread.sleep(1000);
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    return;
}
```

This is an example inside a `void` method, not a standalone program. Never catch `InterruptedException` and continue an infinite loop as if no stop command occurred.

**Difference between canceling one Future and stopping an entire executor:** `heartbeat.cancel(true)` affects only that task; `scheduler.shutdown()` / `shutdownNow()` affects the plugin-owned executor. If a plugin registers multiple schedules, manage all Futures/tokens, not just the last one.

For `ScheduledThreadPoolExecutor`, retaining canceled tasks in the queue can impact memory; configuring `setRemoveOnCancelPolicy(true)` is helpful when canceling and re-registering frequently at runtime. This API belongs to **`ScheduledThreadPoolExecutor`**, not every `ScheduledExecutorService`.

## 4. ExecutorService: shutdown(), shutdownNow(), and awaitTermination()

| API | Effect | Pitfalls |
|---|---|---|
| `shutdown()` | Accepts no new tasks; tries to finish previously submitted tasks | Long/infinite tasks can prevent the executor from terminating |
| `shutdownNow()` | Attempts to stop running tasks (usually via interrupt), skips queued tasks, and returns unstarted tasks | Does not guarantee running tasks have stopped; task code must cooperate |
| `awaitTermination(timeout, unit)` | Waits for the executor to terminate or the timeout to expire | `false` means not terminated within the deadline; must not be treated as quiescent |
| `isShutdown()` | Indicates shutdown was requested | Does not prove all tasks have stopped |
| `isTerminated()` | Indicates all tasks completed after shutdown | Can be checked before closing resources used by tasks |

A common two-phase shutdown pattern (depending on how strongly graceful shutdown is prioritized):

```java
// Illustrative snippet inside a method that may throw InterruptedException.
executor.shutdown();
if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
    executor.shutdownNow();
    if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
        throw new IllegalStateException("Executor still running");
    }
}
```

This code stops a **plugin-owned executor**; never apply it to a shared host executor. If the stopping thread is interrupted, real code typically falls back to `shutdownNow()`, restores the interrupt flag, and reports back for the host to handle. Never use `Thread.stop()` as a “guaranteed stop”: that mechanism is unsafe and deprecated.

**Scheduled executors have a special caveat:** with `ScheduledThreadPoolExecutor`, the default policy after `shutdown()` can allow previously registered delayed tasks to continue running under certain conditions; periodic tasks have different continuation rules. If a plugin must immediately stop all schedules, **cancel each Future by ownership** and then shut down the executor. Never assume calling `shutdown()` alone cancels every schedule immediately.

## 5. Closing Resources with AutoCloseable and Dependency Order

Many resources—such as `InputStream`, `OutputStream`, `Socket`, `WatchService`, JDBC `Connection`, `ExecutorService` via shutdown, or host-supplied registration handles—must be released according to their specific contract.

### 5.1. Use try-with-resources When Scope Is Clear

```java
try (InputStream input = Files.newInputStream(path)) {
    // Read plugin-owned data.
}
```

This is an illustrative snippet assuming `path` and imports for `java.nio.file.Files` and `java.io.InputStream`. Java calls `close()` as soon as control exits the block, even on exception. With multiple resources in the same `try`, Java closes them **in reverse order of declaration** and records close errors as suppressed exceptions when needed.

### 5.2. Plugins Living Longer Than a Single Method

Plugins usually live across many calls; you cannot wrap the entire plugin in `try-with-resources` inside `start()` and close it immediately. Instead, the plugin **stores handles** until `stop/close`. Release them in reverse order of allocation when dependencies allow.

Example:

```text
start(): open DB connection -> create watcher -> register listener -> schedule task
stop():  block new tasks -> unregister listener -> cancel task
         -> wait for workers to stop -> close watcher -> close DB connection
```

If the watcher needs the DB connection to stop or flush, reverse order makes sense. If a task is blocked waiting on a socket, closing the socket early may be required to unblock the task before finishing shutdown; that exception must be explicitly designed.

**Every handle should have one clear owner.** If the host passes a shared connection or shared executor into the plugin, the plugin does not close it on its own, and instead returns only its own subscription/task handles.

### 5.3. Continue Cleaning Up When One close() Fails

Suppose a plugin owns three resources: a listener, an executor, and a file. If the listener's `close()` throws an exception, you must not skip stopping the executor and closing the file. Use `try/finally` blocks or an error-aggregation mechanism to **continue cleanup**, reporting the primary error with subsequent errors attached as `suppressed`.

In a larger design, resources can be managed in a “cleanup stack” of `AutoCloseable`s, closing them one by one in reverse order on stop. However, do not assume every `AutoCloseable.close()` is idempotent on its own: some implementations may throw if closed twice; the plugin management layer must guard stop state.

## 6. Runnable Java 17 Example: Listener + Schedule + Executor + Resource

This example fits in **one Java file** with no external libraries. The host manages a simple event bus; the plugin owns a scheduler and a resource. The plugin retains the `AutoCloseable` registration token and the heartbeat `ScheduledFuture`, then closes everything when the host calls `close()`.

To keep stdout **deterministic and easy to compare**, the heartbeat is scheduled with an initial delay of **1 day**; the program stops the plugin right after the first event. This is solely a testing choice, not a recommended heartbeat interval for real systems.

**File `PluginCleanupDemo.java`:**

```java
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Consumer;

public final class PluginCleanupDemo {
    static final class EventBus {
        private final CopyOnWriteArrayList<Consumer<String>> listeners =
                new CopyOnWriteArrayList<>();

        AutoCloseable register(Consumer<String> listener) {
            listeners.add(listener);
            return () -> listeners.remove(listener);
        }

        void publish(String event) {
            for (Consumer<String> listener : listeners) {
                listener.accept(event);
            }
        }

        int listenerCount() {
            return listeners.size();
        }
    }

    static final class DemoResource implements AutoCloseable {
        private boolean closed;

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                System.out.println("resource=closed");
            }
        }
    }

    static final class DemoPlugin implements AutoCloseable {
        private final EventBus bus;
        private final ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();
        private final AtomicBoolean accepting = new AtomicBoolean(false);
        private final DemoResource resource = new DemoResource();

        private AutoCloseable registration;
        private ScheduledFuture<?> heartbeat;
        private boolean started;
        private boolean closed;

        DemoPlugin(EventBus bus) {
            this.bus = bus;
        }

        synchronized void start() throws Exception {
            if (closed) {
                throw new IllegalStateException("Already closed");
            }
            if (started) {
                return;
            }

            try {
                accepting.set(true);
                registration = bus.register(event -> {
                    if (accepting.get()) {
                        System.out.println("callback=" + event);
                    }
                });

                heartbeat = scheduler.scheduleAtFixedRate(() -> {
                    if (accepting.get()) {
                        System.out.println("heartbeat");
                    }
                }, 1, 1, TimeUnit.DAYS);

                started = true;
                System.out.println("plugin=active");
            } catch (RuntimeException | Error failure) {
                try {
                    close();
                } catch (Exception cleanup) {
                    failure.addSuppressed(cleanup);
                }
                throw failure;
            }
        }

        @Override
        public synchronized void close() throws Exception {
            if (closed) {
                return;
            }
            closed = true;
            accepting.set(false);
            System.out.println("plugin=stopping");

            Exception unregisterFailure = null;
            try {
                if (registration != null) {
                    registration.close();
                }
            } catch (Exception ex) {
                unregisterFailure = ex;
            }

            if (heartbeat != null) {
                heartbeat.cancel(true);
            }
            scheduler.shutdownNow();

            boolean terminated;
            try {
                terminated = scheduler.awaitTermination(3, TimeUnit.SECONDS);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                if (unregisterFailure != null) {
                    interrupted.addSuppressed(unregisterFailure);
                }
                throw interrupted;
            }

            if (!terminated) {
                IllegalStateException failure =
                        new IllegalStateException("Executor still running");
                if (unregisterFailure != null) {
                    failure.addSuppressed(unregisterFailure);
                }
                throw failure;
            }

            resource.close();
            System.out.println("plugin=stopped");

            if (unregisterFailure != null) {
                throw unregisterFailure;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        EventBus bus = new EventBus();
        DemoPlugin plugin = new DemoPlugin(bus);
        try {
            plugin.start();
            bus.publish("first");
            System.out.println("listeners.before=" + bus.listenerCount());
        } finally {
            plugin.close();
        }

        plugin.close(); // Second call does not repeat cleanup.
        System.out.println("listeners.after=" + bus.listenerCount());
        bus.publish("second"); // Listener has been removed.
        System.out.println("done");
    }
}
```

**Compile/run with JDK 17+** in the directory containing the file:

```powershell
javac PluginCleanupDemo.java
java PluginCleanupDemo
```

**Stdout of the example during a normal run:**

```text
plugin=active
callback=first
listeners.before=1
plugin=stopping
resource=closed
plugin=stopped
listeners.after=0
done
```

Analyzing what happened:

1. `start()` enables event acceptance, registers the listener, and schedules the heartbeat; no heartbeat fires due to the 1-day delay.
2. The host publishes the `first` event; the listener sees `accepting=true` and prints `callback=first`.
3. The host calls `close()` in `finally`. The plugin sets `accepting=false` **before** unregistering.
4. The registration token triggers `listeners.remove(...)`; the event bus no longer holds the plugin's callback.
5. `heartbeat.cancel(true)` cancels the schedule; `shutdownNow()` and `awaitTermination(...)` finish stopping the scheduler before the resource is closed.
6. The resource prints `resource=closed` exactly once; the plugin prints `plugin=stopped`.
7. The second `plugin.close()` does not repeat cleanup. Listener count is `0`, publishing `second` no longer invokes the callback, and `done` is printed at the end.

The example intentionally keeps all publishing and stopping on **the same main thread** for deterministic stdout; when the host dispatches callbacks concurrently on other threads, additional draining mechanisms are needed. The `AutoCloseable` token in the example is **an API designed by the demo event bus**; real frameworks will have their own token/unregistration types.

**Demo limitations:** if `awaitTermination` times out, the example **throws an error instead of closing a resource that may still be in use by a worker**; in production, the host must record an incomplete-cleanup state, have a retry/escalation mechanism, or isolate the process. If `close()` is interrupted, it must proceed per stop policy and never claim the plugin unloaded cleanly. The example also aggregates errors only from `registration.close()`; real systems should wrap and aggregate errors from **every** cleanup step.

## 7. Avoiding In-Flight Callbacks and Race Conditions on Unload

### 7.1. Unregistering Does Not Wait for Running Callbacks

Suppose the event bus uses `CopyOnWriteArrayList` as in the example. While thread A is iterating a listener snapshot, thread B calls `remove(listener)`. Thread A **can still hold a reference and invoke the listener** from the old snapshot. Likewise, if a callback already started before `accepting` became false, it can continue operating on resources.

Therefore, “listener count equals 0” only proves **no new registrations remain** in the live list; it does not prove **no callbacks are in-flight**. For callbacks touching files/sockets/DBs, the host needs one of these mechanisms:

- An event bus API such as `unregisterAndDrain(...)` or waiting for active invocations.
- The plugin using an `inFlight` counter, a `Phaser`, locks/counters, or a lifecycle gate to wait for already-admitted callbacks to finish.
- Routing all callbacks through a plugin-owned executor, rejecting new tasks and waiting for the executor to quiesce before closing resources.
- Defining a deadline: if a callback refuses to stop, the host records an incomplete unload rather than pulling closed resources out from under it.

### 7.2. When Shutdown Races with schedule()

A task may try calling `scheduler.schedule(...)` at the exact time the host calls shutdown. Set the `STOPPING` flag first, then prevent or reject new schedules. If a race still occurs, `RejectedExecutionException` after shutdown is an expected condition to handle—do not automatically spin up a new executor to “rescue” a stopping plugin.

If the plugin creates additional `CompletableFuture`s or callback chains outside its own scheduler, inventory **every** source of work and its corresponding cancellation/coordination mechanism. `CompletableFuture.cancel(true)` has its own semantics and does not guarantee interrupting running code; check the contract of each abstraction.

### 7.3. Blocking Post-Stop Calls at Public APIs

Host-invoked entry points such as `handleRequest()` or `onMessage()` should check state to avoid accessing closed resources. A typical state enum:

```text
NEW -> STARTING -> ACTIVE -> STOPPING -> STOPPED
          |
          +---------> FAILED -> CLEANUP_ATTEMPTED
```

This is a state machine **defined by the host/plugin manager**, not a lifecycle automatically provided by the JVM. If `start()` fails midway, previously created registrations/executors/resources must still be reclaimed. If `stop()` fails, the state must reflect cleanup failure rather than always labeling `STOPPED` and forgetting running tasks.

## 8. Ownership and Cleanup by Resource Type

| Object / Handle | Typical Owner | What the Plugin Should Do on Stop |
|---|---|---|
| Host-provided event bus | Host | Only close the plugin's subscription token or remove its listener |
| Dedicated executor created by plugin | Plugin | Block submissions, cancel Futures, shut down, bounded await, drop references |
| Shared executor supplied by host | Host | Cancel **only the plugin's tasks**; never shut down the host's executor |
| Heartbeat `ScheduledFuture` | Plugin or registration owner | `cancel(...)` and confirm scheduler/task quiescence |
| File stream / socket / watcher opened by plugin | Plugin | `close()` after tasks using it have stopped; check errors |
| DB/HTTP client shared by host | Host or assigned scope | Do not close the shared client; return lease/handle if any |
| Worker threads created by plugin | Plugin | Request termination; prevent threads outliving unload |
| `ThreadLocal` on long-lived workers | Worker owner | Clear value on task exit; avoid retaining old instances/classloaders |
| `Thread.contextClassLoader` | Thread/executor owner | Restore context classloader after calling plugin code if modified |
| MBeans, registries, OS/GUI listeners | Registrant or plugin | Unregister/dispose appropriately; do not leave host holding plugin refs |

**Cleaning up host metadata and registries:** when a plugin stops, the host must remove entries from routing tables, lookup caches, service registries, or command lists if they hold old plugin instances, callbacks, or provider classes. These can cause leaks even after the plugin closes every file.

**Never close shared resources:** plugin A must not call `hostExecutor.shutdownNow()` while plugin B still uses that executor. Enforce ownership in API design from the start—for example, pass an `Executor` without shutdown methods or issue a dedicated `TaskHandle` for plugin-submitted tasks.

## 9. Risk of ClassLoader Leaks When Closing a Plugin

In systems using a dedicated `URLClassLoader` or `ModuleLayer` per plugin, Java provides no “instant class unload” merely by deleting a JAR from a directory or calling `close()` on the loader. Class unloading depends on garbage collection of the classloader that defined the classes and all related objects.

Common reference-retention sources:

1. **Still-running threads**: stack frames, target `Runnable`s, `ThreadLocal`s, or context classloaders can retain plugin classes/loaders.
2. **`ScheduledFuture` and executor queues**: task lambdas/`Runnable`s may capture the plugin's `this`; an un-shutdown scheduler keeps the task alive.
3. **Host event bus/registries**: listener lambdas capture plugin instances and are retained long-term by the host.
4. **Static caches or singletons on the host side**: maps retaining `Class`, `Method`, callbacks, or provider objects from the plugin.
5. **ServiceLoader/provider caches, logging hooks, MBeans, file watchers**: integration points retaining callbacks or old classes.
6. **Thread context class loader (TCCL)**: a host-owned thread pool had its TCCL switched to `pluginLoader` and forgot to restore it.

`URLClassLoader.close()` closes resources managed by the loader, yet does not stop workers on its own and does not guarantee classes are GC'd. Never close the loader **before** tasks/plugin callbacks needing classes/resources from that loader have finished. The usual sequence is: **stop plugin → stop background work → unregister → close I/O → drop references → close loader**. When GC/unloading occurs is up to the JVM, with no instant guarantee.

### Checking for Leaks

You can run looped integration tests:

- Load a plugin with a dedicated classloader.
- Create sample listeners, schedules, and resources.
- Stop/unload the plugin.
- Verify the registry holds no remaining listeners/tasks, the executor terminated, and resources report closed.
- Repeat across multiple cycles to observe thread counts, heap usage, file handles, and retained classloaders.
- If using `WeakReference<ClassLoader>` to observe reclamation, do not treat a single `System.gc()` call as complete proof: GC is not guaranteed on demand.

## 10. Error Handling and Stop Duration

### 10.1. Never Stop Cleanup at the First Error

A `registration.close()` call may throw while the scheduler and files still need closing. Production code should aggregate errors:

```text
- Stop accepting new work.
- Attempt to unregister callbacks; record failure if any.
- Attempt to cancel schedules; record failure if any.
- Shut down executor; wait within deadline and record timeout.
- If no tasks remain using the resource, attempt to close the resource; record error.
- Report cleanup status and errors with suppressed exceptions.
```

Never swallow exceptions and print “stopped” while workers are still running. `InterruptedException` in the cleanup thread must be handled per policy: usually exit promptly, restore the interrupt flag, notify the host, and do not claim clean unloading.

### 10.2. Timeout Is Not Success

When `awaitTermination(5, TimeUnit.SECONDS)` returns `false`, the host knows **executor termination has not been proven**. Depending on policy, it can extend the wait, alert, isolate the plugin process, or refuse to unload to avoid operating on closed resources. Never force-kill via `Thread.stop()`.

For systems hosting untrusted plugins, running plugins in **isolated processes** allows the host to enforce time and resource limits cleanly. Classloaders or TCCL are not a security sandbox.

### 10.3. Graceful Shutdown vs. Immediate Shutdown Are Two Policies

A transaction-processing plugin may need **graceful shutdown**: reject new requests, wait for in-flight transactions within a deadline, flush data, then close connections. A pure compute plugin may prefer immediate **cancel/interrupt**. Do not apply the exact same order/timeouts mechanically to every plugin; the lifecycle contract must specify in-flight task semantics.

## 11. Checklist Before Treating a Plugin as Stopped

- [ ] State transitioned to `STOPPING` before tearing down registries/tasks?
- [ ] No new calls arriving from host to plugin?
- [ ] All listeners/subscriptions unregistered, and in-flight callbacks drained or explicitly handled?
- [ ] All scheduled tasks / timers / retry loops canceled?
- [ ] Plugin-owned executors shut down; `isTerminated()` or `awaitTermination(...)` verified?
- [ ] Task code cooperates with `interrupt`; no stray workers still alive?
- [ ] Plugin-created resources closed, even when another close failed?
- [ ] Shared resources owned by host or other plugins left untouched?
- [ ] Host registries/caches/TCCL/ThreadLocals no longer retaining the plugin?
- [ ] `close()` is idempotent and handles startup failures?
- [ ] Final state accurately reflects `STOPPED` vs. `FAILED_TO_STOP`, with logs/causes?

This list is an **acceptance criterion** for a plugin manager, not behavior the JVM performs automatically.

## 12. Exercises and Review Questions

1. **Why isn't unregistering a listener enough to close resources immediately?** Because a callback that already started or sits in a dispatch snapshot may still execute.
2. **Does `ScheduledFuture.cancel(true)` guarantee the task has stopped?** No. It requests cancellation/interruption; the task must cooperate and may need awaiting termination.
3. **When do you use `shutdown()` vs. `shutdownNow()`?** Depends on graceful vs. immediate policy; in both cases, you still must verify tasks terminated.
4. **May a plugin given a host-shared executor call `shutdownNow()`?** Normally no; the plugin only cancels work it owns.
5. **Why can't Java unload a plugin solely by closing `URLClassLoader`?** Because threads, registries, tasks, caches, providers, or other objects may still retain references to the loader/classes.
6. **Why should `close` be idempotent?** The host may call stop multiple times or call cleanup after a startup failure; repeated cleanup can throw errors, close the wrong resources, or corrupt state.
7. **If `awaitTermination` times out, should `STOPPED` be marked successful?** No; incomplete shutdown must be recorded and appropriate escalation or isolation applied.

**Practice 1:** change the heartbeat delay to `0` and period to `100` milliseconds; observe a few heartbeats while the plugin is active. For deterministic tests, use latches instead of relying on `Thread.sleep`, and verify no new ticks occur after stop.

**Practice 2:** simulate an error in `registration.close()`. Update cleanup so it still stops the scheduler and closes the resource, ultimately throwing the original error with secondary errors attached as `suppressed`.

**Practice 3:** create two plugins sharing the host event bus, each with its own scheduler. Stop plugin A and verify plugin B still receives events; then stop B and verify listener count reaches 0.

**Practice 4:** pass a shared executor from the host instead of creating one per plugin. Design an API returning only a `cancelTask()` token; confirm stopping plugin A does not shut down B's executor.

## References

- Oracle Java SE 17 — `ExecutorService`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Oracle Java SE 17 — `ScheduledExecutorService`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html
- Oracle Java SE 17 — `Future` and `cancel(boolean)`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
- Oracle Java SE 17 — `ScheduledThreadPoolExecutor`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html
- Oracle Java SE 17 — `AutoCloseable`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html
- Oracle Java SE 17 — `URLClassLoader` and `close()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
