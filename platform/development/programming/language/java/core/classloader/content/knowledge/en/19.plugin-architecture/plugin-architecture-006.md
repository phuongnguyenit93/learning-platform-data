# Plugin Shutdown, Unregistration, and Resource Release Workflow in a ClassLoader Architecture

## 1. Why does a “stopped” plugin still occupy memory?

A Java application can install a plugin using a dedicated `URLClassLoader`, look up an implementation through a shared API/SPI, call `start()` to register events, initialize an executor, and open files or connections. When the plugin is no longer needed, the application calls `URLClassLoader.close()` and assumes all classes, threads, and resources of the plugin have disappeared.

In reality, **closing a ClassLoader does not mean stopping plugin code or unloading classes immediately**. A plugin can still be kept alive by:

- Callbacks/listeners registered in the host's event bus.
- Scheduled tasks, executors, threads, timers, task queues, `Future` instances, or runnable objects.
- A Thread Context ClassLoader (TCCL) held by a long-lived thread.
- `ThreadLocal` entries on a thread pool, especially when the value is defined in the plugin loader.
- A host static registry or singleton holding the plugin's instance, `Class<?>`, `Method`, `MethodHandle`, lambda, proxy, or ClassLoader.
- An MBean, shutdown hook, logging handler, JDBC driver, service provider, or third-party registry that was not unregistered.
- Unclosed resources: sockets, file streams, watchers, JAR handles, connection pools, native handles.
- In-flight requests or incomplete callbacks that still reference the code/plugin instance.

Therefore, **plugin shutdown is a coordinated lifecycle protocol**, not a single command. You must stop work-producing sources, remove references from the host, wait for in-flight work according to policy, close resources owned by the plugin, and only then close the ClassLoader and drop remaining references.

## 2. Distinguishing stop, close, unload, and GC

| Concept | Actual Behavior | What Does It Not Guarantee? |
| --- | --- | --- |
| **Quiesce / stop accepting** | Prevents new requests/events/jobs from entering the plugin | Does not automatically cancel all running tasks |
| **Unregister** | Removes callbacks, command handlers, routes, providers, or listeners from external registries | Does not automatically close executors and opened sockets |
| **Stop** | Requests the plugin to stop serving, and may wait for/cancel work per contract | Does not necessarily close the class loader |
| **Close / dispose** | Releases owned resources: executors, streams, connections, timers, watchers | Does not prove that runtime classes have been GC'd |
| **`URLClassLoader.close()`** | Closes resources managed by URLClassLoader (e.g., opened JAR handles) and blocks loading new classes/resources per the API contract | Does not automatically terminate threads/callbacks, nor unload already defined classes |
| **Unload class** | The JVM may reclaim class metadata when reachability and GC conditions allow | Not guaranteed to happen right at `close()` |
| **Garbage collection** | Can reclaim objects/loaders that are no longer reachable | Not a synchronous “force unload” API safe for applications |

**Key takeaway:** after calling `close()` on a `URLClassLoader`, an already defined class can still exist, and its instances and methods can still be executed. Close acts on the sources/resources the loader manages, not as a “kill switch” for code.

If you need to guarantee stopping **untrusted or uncooperative code**, a separate ClassLoader is not a strong enough isolation boundary. Executing plugins in a separate process/container with an appropriate IPC contract and permissions is generally easier to forcibly terminate.

## 3. The plugin lifecycle should be modeled with explicit states

A practical design can use:

```text
       install / load
NEW --------------------> LOADED
                           |
                         start()
                           v
                         ACTIVE
                           |
                    stop requested
                           v
                       QUIESCING
                           |
                no new work; drain/cancel
                           v
                       STOPPING
                           |
              unregister; close resources
                           v
                        STOPPED
                           |
                close loader; drop refs
                           v
                        DISPOSED
```

There may be error states such as `FAILED_START`, `FAILED_STOP`, or `LEAK_SUSPECTED`. The important thing is **not to make the state look completely stopped while threads/callbacks are still active**.

Conditions that must be defined:

1. **Idempotency:** calling `stop()` or `close()` multiple times must not cause broken double-closes or negative registrations; if an exception occurs, still attempt to clean up whatever can be cleaned up.
2. **Concurrency:** do not allow concurrent start and stop calls to leave state inconsistent; locks, atomic state, or a tested state machine are needed.
3. **Ownership:** whichever component creates a resource is responsible for closing it, or the ownership-transfer contract must be explicit.
4. **Deadline:** shutdown should not wait indefinitely; define timeouts for draining/awaiting, a cancel/fallback policy, and a clear way to report errors.
5. **Failure isolation:** a cleanup failure in one plugin must not block cleanup of the remaining plugins/resources.
6. **No resurrection:** late-arriving callbacks must not automatically restart a plugin that is shutting down.

There is no “single standard” order applicable to every framework; the order must be based on the plugin's dependency flow. However, a useful stop workflow prioritizes **blocking new work before closing the resources that the work is using**.

## 4. Recommended shutdown sequence for a running plugin

### Step 1 — Announce the stop request

Set the plugin state to `QUIESCING` or `STOPPING` using an appropriate synchronized operation. The state transition API must be specified as **one-way** for this stop cycle.

From that point on:

- The dispatcher does not send new requests to the plugin.
- The scheduler/command router does not issue any more new jobs.
- Health/readiness checks no longer treat the plugin as an instance serving normal requests.
- Loading or creating a new instance of the same plugin version is rejected according to policy.

If the host itself continues issuing commands after the plugin's `close()`, a “clean stop” of the plugin is impossible.

### Step 2 — Unregister from systems external to the plugin

Remove subscriptions/listeners, HTTP routes, command handlers, job scheduler entries, ServiceRegistry entries, and any registrations issued by the host. A good pattern is for the `register(...)` API to return an **`AutoCloseable`/`Registration` handle** so unregistration uses that exact handle.

```java
Registration subscription = eventBus.subscribe(listener);
try {
    // Use the subscription while the plugin is ACTIVE.
} finally {
    subscription.close();  // unregister on the host
}
```

This is an illustrative snippet (assuming `Registration` and `eventBus` are already defined). You should not merely call `listeners.clear()` **inside the plugin** if the host still holds a reference to the original listener.

### Step 3 — Stop running tasks

- Executor: `shutdown()` to stop accepting new tasks; wait via `awaitTermination(timeout, unit)`.
- If the deadline is exceeded: consider `shutdownNow()` (sends an interrupt to running tasks per contract), then wait again.
- Tasks must cooperate with interruption/cancellation; `shutdownNow()` **cannot forcibly stop** a thread blocked in uncooperative code.
- Custom-created threads must have a stop flag, interrupt, or appropriate signaling mechanism and have `join` called with a deadline.
- Scheduled executor: cancel periodic jobs and check the policy for delayed tasks.

Do not use `Thread.stop()` to forcibly stop threads; this API is unsafe. Do not hold a registry lock across `awaitTermination` if tasks need the registry to complete, as this can cause a deadlock.

### Step 4 — Close resources in reverse order of initialization

For example, initialization: open socket → create worker → register listener; shutdown usually does the reverse: unregister listener → stop worker → close socket. If tasks currently need the socket, drain tasks **before** the socket is closed; if closing the socket itself is the signal to break blocking I/O, the workflow must explicitly describe this.

Apply `try-with-resources` or `finally` for partial cleanup and preserve `suppressed exceptions` when multiple errors occur. Resources may include:

- `InputStream`, `OutputStream`, `WatchService`, `JarFile`.
- `Socket` / HTTP client/connection pool.
- JDBC connections, registered listeners/drivers, timers/schedulers.
- Logging/appenders, metrics instrument callbacks, exporters.
- Native library handles or plugin-specific unmanaged state.

### Step 5 — Clean up context and long-lived registries

Remove plugin-owned `ThreadLocal` entries on the right thread when processing finishes; restore the TCCL when temporarily changed:

```java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    // Execute the API that requires the plugin's context loader.
} finally {
    thread.setContextClassLoader(previous);
}
```

This snippet requires the `pluginLoader` variable. The TCCL is a strong reference; a thread pool that outlives the plugin can retain the loader via the TCCL if it is not restored. `ThreadLocal.remove()` only affects the **calling thread**; the host cannot arbitrarily and safely clear all ThreadLocal entries of other threads remotely.

### Step 6 — Close the ClassLoader and drop references

Once operations have finished:

- Call `URLClassLoader.close()` using try-with-resources or in the manager's dispose step.
- Remove plugin entries from the host's registries/routes/caches.
- Drop references to instances, classes, reflection metadata, threads, module layers, and related plugin objects when they are no longer needed.
- Transition the state to `DISPOSED` according to the cleanup conditions actually guaranteed.

After this step, the loader/classes **may** become unreachable and be GC'd/unloaded when the JVM decides. Do not report that “classes are unloaded” simply because `close()` returned normally.

## 5. Self-contained Java 17 example: stopping callback intake, shutting down the executor, closing URLClassLoader

We separate the code into a **shared API defined by the host**, an **implementation defined by the plugin loader**, and the **host responsible for orchestration**. The example uses a simple single-threaded event bus to keep stdout deterministic. The plugin registers a callback holding a reference to `this`, creates a worker executor, and has an idempotent stop/close API.

### 5.1. Directory structure

```text
src/
├── example/spi/
│   ├── HostServices.java
│   └── Plugin.java
├── example/impl/
│   └── EchoPlugin.java
└── PluginShutdownDemo.java

out/
├── host/         (host + shared SPI)
└── plugin/       (plugin implementation)
```

**Important:** at runtime, `out/plugin` is **not** on the application classpath. The implementation must be loaded via a separate `URLClassLoader`, while the `example.spi.*` interfaces are provided by the parent application loader.

### 5.2. File `src/example/spi/HostServices.java`

```java
package example.spi;

public interface HostServices {
    Registration subscribe(Runnable listener);

    interface Registration extends AutoCloseable {
        @Override
        void close();
    }
}
```

This is the callback contract: calling `subscribe` returns a `Registration` that the plugin must close when stopping. The host owns the registry, so unregistering through a host-issued handle reduces the risk of the host still retaining the plugin's lambda.

### 5.3. File `src/example/spi/Plugin.java`

```java
package example.spi;

public interface Plugin extends AutoCloseable {
    void start(HostServices services) throws Exception;
    void stop();

    @Override
    void close() throws Exception;
}
```

Separation of responsibilities:

- `start`: creates resources and registers work at startup.
- `stop`: transitions to a non-serving state and cancels/removes callbacks/entries from the host.
- `close`: calls `stop` if needed and closes the plugin's own resources.

In a real system, the manager may additionally have separate `quiesce()`, `awaitIdle()`, or `dispose()` methods. The example intentionally keeps the API small for easy observation.

### 5.4. File `src/example/impl/EchoPlugin.java`

```java
package example.impl;

import example.spi.HostServices;
import example.spi.Plugin;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public final class EchoPlugin implements Plugin {
    private HostServices.Registration registration;
    private ExecutorService worker;
    private boolean running;

    private void handleEvent() {
        if (running) {
            System.out.println("event=handled");
        }
    }

    @Override
    public void start(HostServices services) throws Exception {
        if (worker != null) {
            throw new IllegalStateException("Already started");
        }

        worker = Executors.newSingleThreadExecutor(task -> {
            Thread thread = new Thread(task, "echo-plugin-worker");
            // Worker does not retain the plugin TCCL after initialization.
            thread.setContextClassLoader(
                    ClassLoader.getSystemClassLoader());
            return thread;
        });

        try {
            // Force worker creation, then wait for a short task to finish.
            worker.submit(() -> {}).get();
            registration = services.subscribe(this::handleEvent);
            running = true;
            System.out.println("plugin=started");
        } catch (Exception failure) {
            if (registration != null) {
                registration.close();
                registration = null;
            }
            worker.shutdownNow();
            worker = null;
            throw failure;
        }
    }

    @Override
    public void stop() {
        if (!running) {
            return;
        }
        running = false;

        if (registration != null) {
            registration.close();
            registration = null;
        }
        System.out.println("plugin=stopped");
    }

    @Override
    public void close() throws InterruptedException {
        stop();
        if (worker == null) {
            return;
        }

        worker.shutdown();
        if (!worker.awaitTermination(2, TimeUnit.SECONDS)) {
            worker.shutdownNow();
            if (!worker.awaitTermination(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Worker did not terminate");
            }
        }
        worker = null;
        System.out.println("plugin=resources-closed");
    }
}
```

**What this makes clear:**

- The callback `this::handleEvent` holds a reference to the plugin instance. If the host does not remove the callback, the registry can retain the instance as well as the associated loader.
- `stop()` does not just set `running=false`; it also calls `registration.close()`.
- `close()` stops intake if needed, then shuts down the executor and waits with a bounded timeout.
- The worker thread is assigned the system loader's TCCL per the demo policy, avoiding long-term retention of the plugin loader solely via the TCCL.
- Calling `close()` repeatedly after the worker has been closed returns immediately; calling `stop()` repeatedly does not log or deregister again.

**Limitations:** `running` here is only modified and read along a single orchestration thread in the demo; in a multithreaded callback environment, `volatile`/atomic state or appropriate synchronization is needed to avoid data races. The `shutdownNow()` mechanism still depends on tasks cooperating with interruption.

### 5.5. File `src/PluginShutdownDemo.java`

```java
import example.spi.HostServices;
import example.spi.Plugin;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public final class PluginShutdownDemo {

    static final class EventBus implements HostServices {
        private final List<Runnable> listeners = new ArrayList<>();

        @Override
        public Registration subscribe(Runnable listener) {
            listeners.add(listener);
            return new Registration() {
                private boolean closed;

                @Override
                public void close() {
                    if (!closed) {
                        closed = true;
                        listeners.remove(listener);
                    }
                }
            };
        }

        void publish() {
            for (Runnable listener : List.copyOf(listeners)) {
                listener.run();
            }
        }

        int subscribers() {
            return listeners.size();
        }
    }

    public static void main(String[] args) throws Exception {
        EventBus bus = new EventBus();
        URL pluginUrl = Path.of("out/plugin").toUri().toURL();

        try (URLClassLoader loader = new URLClassLoader(
                new URL[]{pluginUrl},
                PluginShutdownDemo.class.getClassLoader())) {

            Class<?> implementation =
                    loader.loadClass("example.impl.EchoPlugin");

            Plugin plugin = (Plugin) implementation
                    .getDeclaredConstructor().newInstance();

            try {
                plugin.start(bus);
                bus.publish();
                System.out.println("subscribersBeforeStop="
                        + bus.subscribers());
            } finally {
                try {
                    plugin.stop();
                } finally {
                    plugin.close();
                }
            }

            System.out.println("subscribersAfterStop="
                    + bus.subscribers());
            bus.publish(); // No plugin listeners remain.
        }

        System.out.println("loader=closed");
    }
}
```

The host holds references to `plugin` and `implementation` within a bounded scope; closing the loader at the end of the `try` block does not guarantee immediate GC. In a production version, the registry/manager needs to remove all long-lived references upon disposal and distinguish a successful plugin stop from potential unloading.

### 5.6. Compiling and running

From the root directory of the example, using a shell that supports `mkdir -p` (Linux/macOS/Git Bash):

```bash
mkdir -p out/host out/plugin
javac --release 17 -d out/host src/example/spi/HostServices.java src/example/spi/Plugin.java src/PluginShutdownDemo.java
javac --release 17 -cp out/host -d out/plugin src/example/impl/EchoPlugin.java
java -cp out/host PluginShutdownDemo
```

On Windows PowerShell, create the directories using `New-Item -ItemType Directory -Force out/host,out/plugin`, then run the remaining `javac` and `java` commands. The classpath here has only **one root**, so neither the `:` nor `;` separator is needed.

**Expected stdout on JDK 17+ upon successful execution:**

```text
plugin=started
event=handled
subscribersBeforeStop=1
plugin=stopped
plugin=resources-closed
subscribersAfterStop=0
loader=closed
```

### 5.7. Why is this output meaningful?

1. `plugin=started`: the implementation was loaded and instantiated by a separate loader, the worker ran the short task, and the callback was registered.
2. `event=handled`: the host published an event while the plugin was active.
3. `subscribersBeforeStop=1`: the registry external to the plugin still held exactly one callback.
4. `plugin=stopped`: the plugin transitioned state and closed the registration handle.
5. `plugin=resources-closed`: the executor stopped and the plugin cleared its reference to the worker.
6. `subscribersAfterStop=0`: the host no longer holds the callback; this is **a necessary condition** to eliminate a source of reference leaks.
7. `loader=closed`: the loader was closed via try-with-resources, which **does not assert** that all classes have been unloaded.

This exercise intentionally **does not use** `System.gc()` to demonstrate that “unloading has completed,” because GC/unloading does not occur at a deterministic time upon application request.

## 6. Cleanup even when start fails

Startup can fail at multiple points:

```text
load class -> instantiate -> create executor -> open socket
           -> register listener -> schedule job -> ACTIVE
```

If an exception occurs mid-sequence, already created resources **must still be reclaimed**, even though the plugin has not reached the ACTIVE state. Therefore, every allocation/registration step should have a corresponding rollback, or be managed in a stack of cleanup actions.

Illustrative pattern:

```java
Deque<AutoCloseable> cleanup = new ArrayDeque<>();
try {
    AutoCloseable resource = openResource();
    cleanup.push(resource);

    AutoCloseable subscription = registerCallback();
    cleanup.push(subscription);

    markActive();
} catch (Exception failure) {
    while (!cleanup.isEmpty()) {
        try {
            cleanup.pop().close();
        } catch (Exception cleanupFailure) {
            failure.addSuppressed(cleanupFailure);
        }
    }
    throw failure;
}
```

This is **Java pseudocode with hypothetical APIs** (`openResource`, `registerCallback`, `markActive`, and undefined imports), not a standalone program. For a real implementation, ensure that if startup succeeds, ownership of the cleanup stack is explicitly transferred to the plugin/manager rather than leaving objects forgotten.

The demo in Section 5 handles startup failure in `EchoPlugin.start` by deregistering and shutting down the worker. However, production code must also consider exceptions from closing the registration, worker shutdown, external side effects, and the possibility that `start()` had partially initialized before throwing.

## 7. Unregistering means removing references where they were registered

A common design mistake:

```text
Host singleton EventBus
    └── List<Listener>
           └── lambda -> PluginInstance
                            └── PluginClass
                                  └── PluginClassLoader
```

Even when the application removes the entry `PluginManager.plugins.remove(pluginId)`, the event bus still holds the listener => the plugin remains reachable. Simply setting `plugin = null` in a local variable is not enough.

**Principles:**

- Every `subscribe/register/addListener` needs a symmetric `unsubscribe/unregister/removeListener` operation.
- Return a **registration token/handle** rather than forcing the plugin to guess which object needs to be removed.
- If the framework uses annotations to auto-scan/register, there must be an unregister API for the plugin scope upon stop.
- If the registry is partitioned by pluginId, the manager can invoke `unregisterAll(pluginId)` to reclaim registrations when a plugin fails.
- If a callback is executing during unregistration, clearly define **drain semantics**: does unsubscribing block new callbacks or wait for currently executing callbacks? Those are two different possibilities.
- If a plugin has a lambda listener, do not create a new lambda when calling remove and expect the two instances to always be equal; keep **the exact handle or listener instance** that was registered.

### Registries beyond the event bus

| Registry or Integration | Typical Action Needed on Stop | Reason |
| --- | --- | --- |
| HTTP route / servlet filter | Unregister route/filter, wait for in-flight requests | Avoid invoking a disposed plugin |
| Scheduler/cron | Cancel job, wait/cancel executing tasks | The job may hold references to plugin code |
| Event listener / message consumer | Unsubscribe/close consumer, drain queue | Avoid callbacks into a stopped instance |
| JDBC driver | Deregister drivers registered by the plugin when ownership matches | DriverManager may retain the class/loader |
| JMX MBean | Unregister MBeans registered by the plugin | A long-lived MBean server retains the implementation |
| Logging handler/appender | Remove handler and then close it | Threads/streams/caches retain the plugin |
| Service registry | Remove service implementations and cached provider metadata | Host stops looking up the old provider |
| Metrics observer | Remove callback/instrument listener, close exporter | Avoid retaining lambdas/the plugin |
| Shutdown hook | Remove hook if permitted by the API and shutdown has not started | The hook Thread can retain the loader |
| GUI/desktop listener | Remove listener/observer | The host UI has a longer lifecycle than the plugin |

Not every plugin uses every registry. **The cleanup list must reflect actual ownership**, avoiding calling deregister on resources managed by the shared host and affecting other plugins.

## 8. Executors, threads, and running tasks

Executors are often the reason a plugin fails to stop:

```java
ExecutorService executor = Executors.newFixedThreadPool(2);
// If not shut down, the worker may stay alive after the plugin "closes".
```

This is a snippet. Basic cleanup pattern (can be extracted into a helper with a clear owner):

```java
executor.shutdown();
try {
    if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
        executor.shutdownNow();
        if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
            // Report FAILED_STOP status; do not claim cleanup completed.
        }
    }
} catch (InterruptedException interrupted) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
```

The snippet assumes an `executor` variable, the `TimeUnit` import, and a context permitted to intervene on the executor. If a task is waiting on network I/O or an application lock and ignores interruption, calling `shutdownNow()` does **not** guarantee the thread has died.

### Stopping requests and draining

A drain-capable shutdown can:

1. Cancel route/consumer intake or prevent new requests from entering the plugin.
2. Track the number of in-flight requests using a counter/phaser.
3. Wait until the counter reaches 0 up to the deadline.
4. If the deadline is exceeded, cancel/abort according to policy; distinguish idempotent requests from non-idempotent ones.
5. Close connections/resources only after requests have left the code paths that need them.

**Do not arbitrarily kill threads** to meet a shutdown SLA. If a hard kill is required for uncooperative plugins, isolate the plugin into a separate process with appropriate permission/runtime limits.

### Controlling the worker's TCCL

A thread created while its parent's TCCL points to the plugin loader can **inherit** that context loader. If the thread outlives the plugin, it continues holding a strong reference to the loader. The plugin's thread factory should set the TCCL according to host policy or restore it after each task, and must ensure it does not break APIs that need the plugin loader while the plugin is active.

**Note:** merely setting the TCCL back to the system loader does not resolve other references (lambdas, ThreadLocal, runnable queues). You must stop the thread and clean up all reference-holding channels.

## 9. ThreadLocal, static caches, and class loader leaks

`ThreadLocal<T>` is easy to overlook. If a **host** thread pool lives for the entire process while a ThreadLocal value has a class defined by the plugin loader, it can keep the plugin loader reachable even after the manager has removed the plugin.

Practices:

- When a plugin sets a ThreadLocal, it should call `remove()` in a `finally` block on **the same thread** executing the task.
- Do not keep plugin-defined objects in a host worker's ThreadLocal without explicit teardown.
- For a temporary TCCL, restore the TCCL in `finally` on each thread.
- If the plugin uses a global static cache from a shared library, check for a clear/deregister API by pluginId or loader scope.
- If a framework uses weak keys, do not jump to concluding it is safe: **strong values** or other reference paths can still retain the loader.

Snippet illustrating a plugin task (assuming `context` is an appropriate `ThreadLocal<?>`):

```java
try {
    // Bind context to the thread while handling a request.
} finally {
    context.remove();
}
```

This is a non-standalone snippet; do not call `ThreadLocal.remove` from another thread and expect the value on the worker to be cleared.

### Should WeakReference be used to verify unloading?

`WeakReference<ClassLoader>` can be used to observe **reclaimability** in leak tests, however:

- All strong references from tests, event buses, threads, caches, and reflection artifacts must be dropped.
- GC makes no commitment to complete within a specific time window.
- `System.gc()` is only a hint depending on the VM environment; it is not a certification that classes have been unloaded.
- A weak reference not yet cleared **does not by itself prove** a leak if GC has not reclaimed it yet; and its being cleared does not prove all external resources have been closed.

To prove a leak, combine heap dumps, class histograms, reference chains, thread dumps, and observations across multiple load–unload cycles.

## 10. ServiceLoader, module layers, and plugin reloading

`ServiceLoader` maintains a provider cache for that specific instance: `reload()` clears the cache, it does **not** replace class bytes of the old loader. When retiring a plugin, the host must drop registered provider instances/descriptors and caches holding the old generation. If changing the binary implementation, create a new loader/layer; the **shared API/SPI** must still be defined by the shared loader/layer. With JPMS, check service declarations and references to `ModuleLayer`, and do not treat closing a URLClassLoader as a module unloading mechanism.

## 11. Error handling during shutdown: best effort without masking failures

In practice, multiple steps can throw exceptions: unsubscribe failures, threads failing to stop, stream close failures, `URLClassLoader.close` throwing `IOException`.

A shutdown manager needs to avoid “fail-fast that abandons the rest of cleanup.” Common approaches:

1. Set the STOPPING state even while callbacks are running.
2. Invoke cleanup for all independent resources in an appropriate order.
3. Collect errors; keep the primary exception and add subsequent errors as suppressed exceptions or report an aggregate.
4. When the deadline expires, report `FAILED_STOP`/`PARTIAL_CLEANUP` instead of returning a false success.
5. Ensure closed handles are marked so they are not double-closed.
6. Only declare `DISPOSED` when the contract's required conditions have been met; if a worker is still alive, state this explicitly.
7. Provide a mechanism forcing administrators to evaluate/restart the process when the state is unrecoverable.

### Pattern for aggregating resource-closing errors

```java
Exception primary = null;
for (AutoCloseable resource : ownedResources) {
    try {
        resource.close();
    } catch (Exception error) {
        if (primary == null) {
            primary = error;
        } else {
            primary.addSuppressed(error);
        }
    }
}
if (primary != null) {
    throw primary;
}
```

This is an illustrative snippet (assuming `ownedResources` is a list with cleanup order already determined), not a standalone program. In production, serious `Error`s must also be handled according to system strategy—do not broadly catch `Throwable` and continue as if no error occurred. The important thing is **not letting an error when closing the first resource obscure the remaining resources**.

### Closing the loader when plugin stop fails

If `stop()` misses its deadline, you may still need to close JAR handles and stop routing new requests. However, do not treat `URLClassLoader.close()` as a way to kill running threads. The system state should report remaining activity/potential leaks; for untrusted or uncooperative plugins, restarting the process or using an isolation boundary is a more reliable management measure.

## 12. Designing a plugin API with good shutdown support

A larger contract can clearly separate roles:

```java
public interface ManagedPlugin extends AutoCloseable {
    void prepare(PluginContext context) throws Exception;
    void start() throws Exception;
    void quiesce();
    boolean awaitIdle(long timeout, TimeUnit unit)
            throws InterruptedException;
    void stop();
    @Override
    void close() throws Exception;
}
```

This is an **illustrative interface**; it requires importing `TimeUnit` and defining `PluginContext` to compile, and is not a standard JDK API.

Additional elements you can include:

- `PluginHandle` holding ID/version, loader, registrations, and resource ownership.
- `PluginContext.register(...)` returning a cleanup token supervised by the manager.
- A host event bus capable of unregistering by pluginId and draining.
- A router applying an atomic switch from the old version to the new one.
- A manager maintaining transition state and monotonic timeouts.
- Metrics: active requests, remaining listeners, alive threads, executor termination, open handles, dispose latency.
- Audit logs: pluginId, version, loader identity, shutdown reason, cleanup errors.

**Idempotency should be tested**, not merely documented: calling stop twice, close twice, stop after a start failure, stop while a callback is running, and concurrent start/stop.

## 13. How to detect a “classloader leak” after multiple reloads

Seeing no exceptions does not prove a clean shutdown. Common symptoms:

- The number of `URLClassLoader` or dedicated loader instances grows with each reload.
- Metaspace increases steadily and does not stabilize after full GC cycles.
- Multiple threads still carry the old plugin's name.
- Registries contain listeners/routes/services belonging to old versions.
- JAR files cannot be replaced/deleted on some platforms because open handles remain.
- Thread dumps show stacks containing classes from the old plugin.
- Heap dumps point out reference chains from GC roots to the old loader.

### Investigation procedure

1. **Measure a baseline** before loading: thread count, subscriptions, file handles, Metaspace, and loaders.
2. Load the plugin, run several requests, and observe the defined classes/loaders.
3. Invoke shutdown in the sequence described; verify that registry counts return to baseline.
4. Check for still-alive executor threads, queued jobs, TCCL on long-lived workers, ThreadLocal entries, and shutdown hooks.
5. Check `ServiceLoader` caches, MBean/JDBC/logging registrations, and whether URLClassLoader has been closed.
6. Drop all intentional references to the plugin/loader in the manager.
7. Repeat load–stop–dispose for multiple cycles; look for abnormal cumulative growth.
8. Use heap dumps/histograms and GC-root paths to see what is retaining the old loader. Do not treat a single `System.gc()` call as a conclusive measurement.

You can inspect JVM information using these reference commands:

```bash
jcmd <pid> Thread.print
jcmd <pid> GC.class_histogram
jcmd <pid> VM.classloader_stats
```

These commands depend on the JDK version, attach permissions, and JVM support. Replace `<pid>` with the actual process; do not run large heap dumps in production without evaluating the cost.

You can enable unified logging when your JVM/JDK is suitable:

```bash
java -Xlog:class+unload=info -cp app/classes com.example.Main
```

This is reference syntax; unload events only appear when the VM actually unloads classes, and are not tightly bound to when `URLClassLoader.close()` runs. Logs do not replace checking resources outside the JVM.

## 14. Common mistakes

| Mistake | Consequence | How to Fix |
| --- | --- | --- |
| Calling only `URLClassLoader.close()` and concluding the plugin has stopped | Callbacks/threads remain active, and the loader may still be reachable | Stop ingress, unregister, drain/close, then close the loader |
| Removing the plugin only from a management `Map` | Event buses/static caches still hold references | Unregister **at the registration site** using a handle |
| Using `System.gc()` as a shutdown operation | Does not guarantee class unloading; external resources remain open | Explicitly close resources and drop references |
| Delaying stopping new requests until closing the socket | In-flight/new requests see broken resource state | Quiesce ingress first, drain, then close |
| Using `shutdownNow()` and always treating it as stopped | Tasks may ignore interrupts | Wait for a deadline, report partial failure, and isolate the plugin when needed |
| Not cleaning up TCCL in a host thread pool | Long-lived threads retain the old loader | Restore the TCCL in `finally` |
| Cleaning up ThreadLocal from the wrong thread | Values on the worker still remain | Remove within the right worker/task lifecycle |
| Setting `running=false` while keeping the callback in the registry | The host still holds the plugin instance | Unregister; handle in-flight callback races |
| Letting stop throw an error and skipping the remaining cleanup | Leaks other resources | Aggregate errors and perform responsible best-effort cleanup |
| Reusing the same loader to “reload classes” | Already defined binary names are not automatically replaced | Create a new loader/module layer when needed |
| Redefining the API/SPI inside the plugin | The host cannot cast the provider/plugin | Place shared APIs in a shared parent/module |
| Plugin closing host-owned resources | Breaks other plugins | Track ownership and use per-plugin tokens |

## 15. Self-check exercises

**Question 1.** Calling `URLClassLoader.close()` succeeds. Is it guaranteed that the classes it defined have been unloaded by the JVM?

**Answer:** No. Close releases resources managed by the loader and is not a command forcing the JVM to unload classes; reachability and GC determine whether unloading occurs.

**Question 2.** Why can an event bus callback cause a ClassLoader leak?

**Answer:** A long-lived host event bus retains the callback; the callback/lambda can retain the plugin instance; the plugin instance is tied to a class defined by the plugin loader, keeping the loader reachable.

**Question 3.** Should a callback be unregistered before or after closing the database connection that the callback uses?

**Answer:** Usually quiesce/unregister new callbacks first, wait for or cancel running callbacks per contract, and then close the connection. In-flight semantics must be clearly defined.

**Question 4.** Does `ExecutorService.shutdownNow()` always kill worker threads immediately?

**Answer:** No. It attempts to stop tasks and sends interrupts; tasks may not cooperate. You must wait for a bounded timeout and report the actual status.

**Question 5.** Does `ThreadLocal.remove()` on the main thread clear the value on a worker thread?

**Answer:** No. ThreadLocal state is bound to each thread; cleanup must happen on the right thread/task.

**Question 6.** Why is setting the TCCL back to the host loader before a plugin thread ends useful?

**Answer:** It can eliminate a strong reference from a long-lived thread to the plugin loader. However, it does not replace stopping the thread or cleaning up other references.

**Question 7.** A new plugin has a class with the same name and the JAR has changed. Can you reuse the old loader and call `loadClass` again to get the new bytes?

**Answer:** Not under normal class-loading mechanisms. The same defining loader does not automatically redefine a class with the same binary name; a new loader and lifecycle handoff are typically required.

**Question 8.** One plugin stop fails, but other resources can still be closed. What should the manager do?

**Answer:** Continue appropriate cleanup, collect/record the errors, do not report a false completed disposal, and mark a partial failure or require operational intervention.

**Question 9.** What does `subscribersAfterStop=0` in the example prove, and what does it not prove?

**Answer:** It proves the demo's event bus no longer holds that callback after stopping; it does not prove that every reference in the JVM is gone or that classes have been unloaded.

**Question 10.** Why is a dedicated ClassLoader not enough to kill an arbitrary plugin when it runs an infinite loop?

**Answer:** A loader only manages defining/finding classes and certain loaded resources; it provides no mechanism to forcibly stop uncooperative threads/code. An isolation/process boundary is needed for a hard stop.

## 16. Implementation and operations checklist

- [ ] Each plugin has explicit states: ACTIVE → QUIESCING → STOPPING → STOPPED → DISPOSED.
- [ ] Close ingress before plugin resources are released.
- [ ] Every registration has an unsubscribe handle; host registries hold no remaining references after stop.
- [ ] Handle in-flight requests/callbacks and define a timeout/drain policy.
- [ ] Shut down executors/workers and wait for a bounded timeout; accurately reflect partial failures.
- [ ] Clean up ThreadLocal/TCCL on the right thread; do not leave long-lived workers retaining the plugin loader.
- [ ] Close files/sockets/connections/watchers/logging/MBeans/JDBC registrations owned by the plugin.
- [ ] Manage exceptions during cleanup, preserving causes/suppressed errors.
- [ ] Plugin stop/close is idempotent across error paths and repeated calls.
- [ ] Close URLClassLoader after cleanup; do not treat close as equivalent to unload.
- [ ] Remove old plugin/class/loader/service provider references from all host registries/caches.
- [ ] Test restart/hot reload over multiple cycles and check that threads/listeners/resources return to baseline.
- [ ] Inspect heap/thread dumps and GC root paths when a loader leak is suspected.
- [ ] For untrusted/uncooperative plugins, use process isolation and an appropriate forced-termination policy.

## 17. Conclusion and references

Stopping a plugin properly is **a process of reversing the dependencies created at start**: stop accepting new work → unregister → complete/cancel running activities → close resources → close the loader → drop all remaining references. Unregistration is the most critical step so the host does not retain the plugin via callbacks or registries; shutting down executors and cleaning up context prevents threads from keeping the class loader alive long-term.

**`URLClassLoader.close()` is not a class-unload command.** It is only one part of reclaiming loader resources; whether the JVM unloads classes depends on reachability and GC. Distinguishing a plugin's shutdown state from class metadata reclamation helps write applications with accurate, easier-to-debug, and safer lifecycles.

Official documentation:

- Java SE 17 `URLClassLoader` (`close()` and class-loading behavior): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- Java SE 17 `ClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 `ExecutorService` (`shutdown`, `shutdownNow`, `awaitTermination`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Java SE 17 `ThreadLocal` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html
- Java SE 17 `ServiceLoader` (`reload()` and provider cache): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- JVMS 17 §5, *Loading, Linking, and Initializing*: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
