# Threads, ThreadLocal, Context Class Loader, and Unstopped Tasks During Plugin Unloading

> **Java Core → ClassLoader → Class Unloading and Memory.** Creating a new `ClassLoader` to load a different plugin version is only the beginning of the lifecycle. A **live thread**, an uncleaned `ThreadLocal` value, a `Thread.contextClassLoader` (TCCL) still pointing to the plugin, or an unfinished task can hold a **strong reference** to the old class loader. When that happens, even if the host has removed the plugin from its registry and called `URLClassLoader.close()`, the loader and the classes it defined may not yet be eligible for garbage collection. This article presents the reference graph, how to reproduce the issue, the distinction between "task completion" and "thread termination," the proper cleanup procedure, and how to diagnose it on Java 17+.

## 1. Practical Question: Why Does the Heap Keep Growing After the Plugin Stops?

A plugin manager that supports hot reload typically does:

```text
1. Load plugin-v1.jar using PluginClassLoader V1
2. Create plugin objects and run tasks
3. User upgrades the plugin
4. Call plugin.stop(), close(V1)
5. Load plugin-v2.jar using PluginClassLoader V2
6. Expect V1 and old class metadata to be reclaimed by GC
```

However, after multiple cycles, heap/metaspace may grow and multiple older-generation loaders still appear in a heap dump. A common reason is that **the host forgot a root reference**:

```text
Live thread / global executor / registry
      |
      +--> Thread.contextClassLoader --> PluginClassLoader V1
      |
      +--> ThreadLocalMap (of the thread)
      |         '--> plugin object --> Class<?> --> PluginClassLoader V1
      |
      +--> Live Runnable / Future / callback
                '--> plugin object or plugin Class<?> --> V1
```

This is a common pattern of reference paths, not a claim that **every** reference path exists on every JVM. The garbage collector decides based on actual reachability: if a loader is still reachable from GC roots, it cannot be reclaimed merely because the application called a method named `stop` or `close`.

**Key Definitions:**

- **Class unloading**: The JVM may remove class metadata when appropriate reachability/lifecycle conditions are met; there is no guarantee on exact timing.
- **Class loader leak**: Code no longer needs a loader, yet references accidentally keep it reachable.
- **Resource leak**: A file descriptor, socket, thread, memory buffer, or task that is not closed/stopped. It may be related to or independent of a loader leak.
- **Proper plugin unload**: The host has stopped accepting new work, stopped/isolated old work, cleared references in the host and threads, closed resources, and **given GC the opportunity** to reclaim it when no other references remain.

Do not use "closed the JAR" as proof of "unloaded the classes."

## 2. Live Threads Are a Critical Part of the Reference Graph

A running `Thread` can hold several kinds of plugin-related data:

1. **TCCL**: `thread.getContextClassLoader()` holds a reference to a `ClassLoader`.
2. **ThreadLocal values**: Thread-specific data, which may be an object defined by the plugin loader.
3. **Stack frames/local variables**: An executing plugin method has locals, `this`, `Class<?>`, or callbacks.
4. **Runnable/Callable**: The target task holds fields or lambda captures leading back to the plugin.
5. **`UncaughtExceptionHandler` and custom handlers/listeners**: May hold plugin objects or classes.
6. **Inherited state**: `InheritableThreadLocal` and TCCL are propagated at thread creation time according to `Thread` rules.
7. **Thread pool bookkeeping**: Queued `Runnable`, `FutureTask`, `ScheduledFuture`, or the executor holds plugin-related data.

A plugin background thread that keeps looping retains its execution stack and can indirectly retain the loader through the running class/method. A thread in the `WAITING` state has **not necessarily terminated** either: it may be waiting on a queue, latch, socket, or timer while still holding references.

**Not every object holding a `Class<?>` is a bug:** while the host still actively needs to run the plugin, holding references is expected. A "leak" only forms after the lifecycle has declared the plugin no longer in use, yet references are not released.

## 3. What Is Context Class Loader (TCCL) and Why Does It Easily Retain Old Loaders?

`Thread` has two methods:

```java
ClassLoader cl = Thread.currentThread().getContextClassLoader();
Thread.currentThread().setContextClassLoader(cl);
```

This is an in-method snippet. TCCL allows a framework running in host classes/libraries to ask for an appropriate loader to locate plugin provider classes/resources. For example, `ServiceLoader` and certain SPI/framework technologies can use the appropriate context loader to discover implementations.

TCCL is **not necessarily the defining loader** of the currently executing code:

```text
Thread running a method of a host class
          |
          | getContextClassLoader()
          v
PluginClassLoader A

The host method is still defined by the host loader
TCCL is only the context selected for the corresponding lookup
```

Because `Thread` stores TCCL as a reference, when a thread pool outlives the plugin and TCCL still points to `PluginClassLoader V1`:

```text
GC root -> pooled Thread -> contextClassLoader -> PluginLoader V1
```

Loader V1 remains reachable. Even without any `ThreadLocal`, **TCCL alone** can be enough to retain the loader.

### TCCL Is Inherited at Thread Creation Time

According to Java SE 21 `Thread`, the default context loader is normally **inherited from the parent thread when a child Thread is constructed**. That means:

- If the host sets TCCL to the plugin loader when creating a thread pool, pool workers may **accidentally inherit** the plugin's loader.
- After the host restores TCCL on the thread that created the pool, TCCL in the already-created workers **does not automatically change**.
- A thread pool can reuse the same platform thread across many tasks. A TCCL left behind by a previous task can become the context for the next task.
- Do not rely on "the main thread reset the loader" to conclude that pool threads have been cleaned up.

To avoid creating workers with the wrong context loader, configure an appropriate `ThreadFactory` and always restore TCCL on **the worker thread itself** after running a task.

### Pattern for Switching TCCL with try/finally

```java
Thread current = Thread.currentThread();
ClassLoader old = current.getContextClassLoader();

try {
    current.setContextClassLoader(pluginLoader);
    // Invoke the plugin / ServiceLoader / framework API that needs this context.
} finally {
    current.setContextClassLoader(old);
}
```

This is a snippet requiring a `pluginLoader` variable and the actual plugin invocation. Restoring TCCL must be in `finally` because the plugin may throw an exception. If you only call `current.setContextClassLoader(pluginLoader)` and forget to restore it, a pooled worker can still retain the loader after the task finishes.

**Do not blindly restore to `null` unless `null` was actually the previous value.** `null` has the semantics "use the system class loader (or bootstrap if needed)" per the API and may not be equivalent to the framework's original context.

## 4. How Does ThreadLocal Retain Data?

`ThreadLocal<T>` is a way to store **a separate value per thread**. Even if the variable is declared in a host class, the worker thread itself holds its own value:

```java
private static final ThreadLocal<Object> CURRENT_PLUGIN =
        new ThreadLocal<>();
```

`CURRENT_PLUGIN.set(value)` stores a value for **the currently running thread**. `CURRENT_PLUGIN.get()` in another thread does not return the same value just because it uses the same `ThreadLocal` key.

If the value is an object whose class was defined by the plugin loader:

```text
Host static ThreadLocal key
      |
Live pooled thread
      '--> ThreadLocal value: plugin.Instance
                      |
                      v
                Class<?> of plugin.Instance
                      |
                      v
              PluginClassLoader V1
```

A `ThreadLocal` key placed in a long-lived host class together with a value created by the plugin can retain the old loader until the worker calls `remove()`, replaces the value, or the thread dies (and no other references remain).

Main API:

- `set(value)`: writes the value for the **current thread**.
- `get()`: retrieves the value for the **current thread**; may use `initialValue()` to create a value.
- `remove()`: deletes the value belonging to the **current thread**.

In particular: **calling `CURRENT_PLUGIN.remove()` on the main thread does not delete the value held by a pool worker**. Cleanup must run on the exact worker that set it, or there must be a corresponding thread replacement/termination policy.

### "ThreadLocal Has Weak Keys So It Won't Leak" Is a Misconception

In common HotSpot/OpenJDK implementations, `ThreadLocalMap` has keys that are weak references to `ThreadLocal` instances, but **values can be strongly held**. If the key is GC'd, the entry can become stale in the map, and the value is not necessarily reclaimed immediately until map cleanup runs.

Therefore:

- A weak key does not guarantee the plugin value will be GC'd immediately.
- Losing the reference to the `ThreadLocal` variable does not replace calling `remove()`.
- Do not create `new ThreadLocal<>()` per request without cleaning up on long-lived workers.
- Do not rely on the thread pool "cleaning up all ThreadLocals after each task" unless **the specific executor/framework has a contract to do so**.

The internal structure of `ThreadLocalMap` is an implementation detail, not an API for applications to access or mutate via reflection. **The proper approach** is to design ownership, use `try/finally`/`remove()`, and let workers terminate when a plugin is unloaded if uncontrolled state may remain.

## 5. Task Completion Is Different from Thread Termination

`ExecutorService.submit(Runnable)` returns a `Future` that may have `isDone() == true`, but this does **not** mean the executor has stopped or the worker thread has died.

For example:

```text
t0: Thread pool creates worker-1
t1: worker-1 runs Task A of plugin-v1
t2: Task A completes, Future A = done
t3: worker-1 returns to wait in the task queue
t4: Task B runs on the same worker-1
t5: pool shuts down, workers can terminate according to executor rules
```

If Task A leaves behind plugin-v1's TCCL or `ThreadLocal`, worker-1 can carry it from t2 to t4, even when Task B belongs to a different plugin.

There are multiple states that must be checked separately:

| State | Meaning | What Cannot Be Inferred |
| --- | --- | --- |
| `future.isDone()` | The task completed/was cancelled per the `Future` contract. | The thread pool has died or TCCL/TL has been cleaned up. |
| `executor.isShutdown()` | The executor is no longer accepting new tasks. | All currently running tasks have finished. |
| `executor.isTerminated()` | After shutdown, all tasks have completed per the executor contract. | There are no **remaining** plugin references in host caches/TCCL threads outside the pool. |
| `thread.isAlive()` | The thread has started and has not yet terminated. | It is doing useful work; it may be waiting on a queue. |
| `loader.close()` | `URLClassLoader` closes its resources/loading sources per the API. | Classes have unloaded, threads/tasks stopped on their own, or all references were cleared. |

**`shutdownNow()` is not "kill all code."** It typically attempts to stop via interruption and returns unstarted tasks; code can ignore interrupts, block on uninterruptible I/O, or hold other references. For arbitrary untrusted plugin code, merely attempting to interrupt threads within the same JVM is not a safety boundary equivalent to killing a process.

## 6. Java 17+ Example Verifying TCCL and ThreadLocal Retention

This example keeps a **worker thread in a pool** alive after the initial task completes. The worker holds two references to the plugin loader: TCCL and a `ThreadLocal<Object>` whose value class is defined by the plugin loader.

Then, the host **submits a cleanup task to that same worker**, calls `ThreadLocal.remove()`, and restores TCCL to a known baseline. Only after that does it shut down the pool and close the URL loader.

The demo **does not call `System.gc()`** and does not require inferring that class unloading happens immediately. It verifies **retained/cleared references** and lifecycle, which has deterministic results.

### Source Structure

```text
src/
  plugin/
    sample/
      plugin/
        Payload.java
  app/
    RetainedLoaderDemo.java
plugin-classes/  (generated by javac)
app-classes/     (generated by javac)
```

**File `src/plugin/sample/plugin/Payload.java`:**

```java
package sample.plugin;

public final class Payload {
    public String label() {
        return "plugin-value";
    }
}
```

**File `src/app/RetainedLoaderDemo.java`:**

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public final class RetainedLoaderDemo {
    private static final ThreadLocal<Object> HOLDER = new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        URL source = Path.of("plugin-classes").toAbsolutePath()
                .toUri().toURL();
        Class<?> loaded;

        try (URLClassLoader loader = new URLClassLoader(
                new URL[]{source}, ClassLoader.getPlatformClassLoader())) {
            loaded = Class.forName(
                    "sample.plugin.Payload", true, loader);
            Object value = loaded.getDeclaredConstructor().newInstance();

            AtomicReference<Thread> worker = new AtomicReference<>();
            ExecutorService pool =
                    Executors.newSingleThreadExecutor(action -> {
                        Thread thread =
                                new Thread(action, "reusable-worker");
                        thread.setContextClassLoader(
                                ClassLoader.getPlatformClassLoader());
                        return thread;
                    });

            try {
                pool.submit(() -> {
                    worker.set(Thread.currentThread());
                    Thread.currentThread()
                            .setContextClassLoader(loader);
                    HOLDER.set(value);
                }).get();

                System.out.println("defined by plugin loader: "
                        + (loaded.getClassLoader() == loader));
                System.out.println("worker stays alive: "
                        + worker.get().isAlive());
                System.out.println("TCCL retains loader: "
                        + pool.submit(
                                () -> Thread.currentThread()
                                        .getContextClassLoader()
                                        == loader).get());
                System.out.println("ThreadLocal retains plugin value: "
                        + pool.submit(
                                () -> HOLDER.get() != null
                                        && HOLDER.get().getClass()
                                           .getClassLoader() == loader).get());
            } finally {
                pool.submit(() -> {
                    HOLDER.remove();
                    Thread.currentThread().setContextClassLoader(
                            ClassLoader.getPlatformClassLoader());
                }).get();

                System.out.println("TCCL restored: "
                        + pool.submit(
                                () -> Thread.currentThread()
                                        .getContextClassLoader()
                                        == ClassLoader.getPlatformClassLoader()).get());
                System.out.println("ThreadLocal cleared: "
                        + pool.submit(() -> HOLDER.get() == null).get());

                pool.shutdown();
                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    pool.shutdownNow();
                }
            }
        }

        System.out.println("class usable after close: "
                + loaded.getName().equals("sample.plugin.Payload"));
    }
}
```

### Compile and Run

From the root directory containing `src`:

```bash
javac --release 17 -d plugin-classes src/plugin/sample/plugin/Payload.java
javac --release 17 -d app-classes src/app/RetainedLoaderDemo.java
java -cp app-classes RetainedLoaderDemo
```

The code is Java 17 compatible; `ClassLoader.getPlatformClassLoader()` has been available since Java 9 and `URLClassLoader` supports try-with-resources. Do not put `plugin-classes` on the application classpath: `sample.plugin.Payload` must be defined by the URL loader in the demo.

**Exact stdout verified on OpenJDK 24 after compiling with `javac --release 17`:**

```text
defined by plugin loader: true
worker stays alive: true
TCCL retains loader: true
ThreadLocal retains plugin value: true
TCCL restored: true
ThreadLocal cleared: true
class usable after close: true
```

### Result Analysis

1. `defined by plugin loader: true`: `Payload` was defined by the new URL loader rather than the application/platform loader.
2. `worker stays alive: true`: The first task has finished and `Future.get()` returned, yet `newSingleThreadExecutor` keeps the worker alive for subsequent tasks.
3. `TCCL retains loader: true`: The worker thread itself has `contextClassLoader == loader` **after** the previous task. This is a strong reference.
4. `ThreadLocal retains plugin value: true`: The `HOLDER` value belonging to the worker thread is a plugin object. Without calling `remove`, it can stay on the worker across subsequent tasks.
5. `TCCL restored: true`: The cleanup task runs on the same worker and resets the loader to the platform baseline configured by the `ThreadFactory`. In a real application, you should save `old = thread.getContextClassLoader()` and restore that exact value.
6. `ThreadLocal cleared: true`: The worker no longer holds the value set by the first task. The host did **not** call `HOLDER.remove()` in main expecting it to clean up the worker.
7. `class usable after close: true`: `URLClassLoader.close()` does not "erase" an already-defined Class object; the `loaded` variable in the host still holds a reference. This is **not a GC test**. The class can only be reclaimed after no references prevent collection and GC actually processes it.

**Test scope:** The example uses a single-thread executor, so the inspection/cleanup tasks execute on **the same worker**. With a fixed pool of multiple workers, submitting a single cleanup task does not guarantee it runs on all workers that ever processed the plugin. You must manage state per thread/task, or shut down and replace the plugin's pool entirely.

**Production caution:** The example focuses on observation, so the cleanup task is simple and `get()` can block per contract. In a real system, ensure cleanup/shutdown still happens even if another task throws an exception, is cancelled, the executor rejects submission, or a worker is stuck; do not treat a `finally` block containing fallible operations as an absolute solution for every scenario.

## 7. Pattern for Restoring TCCL + ThreadLocal Properly in Each Task

For a **host-owned** worker pool, wrap every plugin execution:

```java
// Snippet inside a Runnable with variables pluginLoader,
// pluginContext, and HOST_CONTEXT provided by the application:
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    HOST_CONTEXT.set(pluginContext);

    // invokePlugin();
} finally {
    HOST_CONTEXT.remove();
    thread.setContextClassLoader(previous);
}
```

`HOST_CONTEXT` should have type `ThreadLocal<PluginContext>` or an appropriate type; this is a **snippet**, not a standalone runnable program. The most important point is that `remove()` and TCCL restoration happen **inside the task, on the worker itself**.

If the plugin or framework has **other ThreadLocals** that it created itself, cleaning only `HOST_CONTEXT` in the host is **not enough**. The plugin/framework must have its own lifecycle cleanup or be run in a dedicated pool that you can shut down, await completion, and discard all threads from.

### Nested Tasks / TCCL Stack

A task may change TCCL multiple times:

```text
Host TCCL H
   -> plugin A TCCL A
      -> library loads provider B, TCCL B
      <- restore A
   <- restore H
```

Each layer must **restore its own previous value**, not hardcode the whole system back to the system loader. If a layer forgets to restore, outer code may behave incorrectly or retain B longer than intended.

When a framework uses `ServiceLoader.load(SomeService.class)` (the overload that uses the appropriate context loader per API), the wrong TCCL can cause it to find the wrong provider version or retain an old provider loader; it is not just a memory issue.

## 8. ThreadLocal in Thread Pools: Two Common Retention Patterns

### Pattern A — ThreadLocal Key in the Host, Value Created by the Plugin

```text
GC root -> pooled Thread
                 |
                 '--> ThreadLocal value (plugin instance)
                                |
                                '--> plugin Class<?> / loader
```

This pattern easily occurs when the host stores `currentTenant`, `pluginContext`, or transaction context in a `ThreadLocal` and inadvertently writes an object belonging to the plugin. The key in the host can live for the lifetime of the JVM, so a value remaining on a worker can retain the plugin for a very long time.

### Pattern B — ThreadLocal Key Created by the Plugin

The plugin declares:

```java
package sample.plugin;

public final class PluginContext {
    static final ThreadLocal<Object> CURRENT = new ThreadLocal<>();
}
```

This is a valid Java class if placed in the proper `PluginContext.java` file. If plugin code calls `CURRENT.set(...)` on a host pool worker without calling `CURRENT.remove()` before returning the thread:

- The worker retains a per-thread entry that may hold plugin objects/metadata.
- The static field and the `ThreadLocal` key itself belong to a class defined by the plugin loader.
- Even if the static reference/key becomes unreachable, a **stale ThreadLocalMap entry** in JDK implementations can still hold a strong reference to the value until cleanup.

Merely setting `CURRENT = null` or clearing references to the plugin does not guarantee clearing values already stored across all worker threads. You should not use reflection to open `java.lang.Thread.threadLocals` and "manually" clear it: the internal layout is not public API, JPMS enforces encapsulation, and cross-thread access/mutation risks races or corrupting framework state.

### InheritableThreadLocal and Plugin-Spawned Threads

`InheritableThreadLocal` can propagate values from parent to child **when a thread is created**. TCCL is also inherited per the Java `Thread` API. If a plugin spawns a child thread while TCCL/values point to the plugin, the child can retain them after the parent completes.

**Executor reuse is different from inheritance:** `InheritableThreadLocal` is not designed as safe "per-task context propagation" for thread pools. Workers are usually created once and then receive many tasks; values inherited at creation time do not automatically update for each request. If a framework provides dedicated context propagation, read that framework's own contract and cleanup rules.

## 9. Unstopped Tasks: More Than Just ThreadLocal

Other common retention paths:

| Retention Source | Path to Loader | Appropriate Cleanup |
| --- | --- | --- |
| Still-running `new Thread(pluginRunnable).start()` | Thread → Runnable/stack → plugin code or object. | Request cooperative stop, cancel I/O, `join`, verify not alive. |
| `ScheduledExecutorService.scheduleAtFixedRate` | Executor → recurring `ScheduledFuture`/Runnable → plugin closure. | `cancel` scheduled tasks, shut down executor per ownership. |
| `ExecutorService` queue | Queue → `Runnable/FutureTask` → plugin captures. | Stop accepting new tasks, cancel/purge tasks, drain/terminate per API. |
| Incomplete `CompletableFuture` | Completion chain/lambda → plugin values/functions. | Complete/cancel per contract, clear chain references, handle source work. |
| Host event bus/listener registry | Host singleton → listener object created by plugin. | `unsubscribe/unregister` listeners/callbacks. |
| Registered shutdown hook | JVM hook registry → plugin Thread/Runnable. | `removeShutdownHook` during lifecycle when appropriate. |
| `Timer` / background scheduler | Timer thread and tasks holding callbacks. | `Timer.cancel()`, clear task refs, use standard schedulers when possible. |
| Framework cache / SPI provider | Cache or service registry → plugin `Class<?>`/instance. | Evict caches properly, unregister providers, clear TCCL. |
| Host static field | Host class → plugin instance / `Class<?>`. | Clear references/callbacks, manage ownership. |
| Open sockets/streams | Resource and async callbacks still active. | Close/cancel operations, unregister handlers. |

A plugin may keep a thread running code in the plugin package even if the host never stored the plugin loader in a `ThreadLocal`. It can still retain class metadata through the stack and runnable. Therefore, **scanning only TCCL/ThreadLocal is not enough** if the plugin creates other tasks and callbacks.

### Interrupted Does Not Mean Terminated

`Future.cancel(true)` or `ExecutorService.shutdownNow()` typically only attempts to **interrupt** the running thread; Java does not guarantee that a task cooperates. A task may:

- Catch `InterruptedException` and continue looping.
- Block on I/O or a third-party call with no deadline.
- Hold a monitor in a deadlock.
- Spawn a helper thread and leave it behind.
- Register a callback/lambda into a global host singleton.

Therefore, shutdown needs **deadlines, completion verification, and a failure handling policy**. Do not use `Thread.stop()` as a way to kill a class loader; it is deprecated/unsafe because it can corrupt invariants and monitors.

## 10. Closing URLClassLoader Does Not Force the JVM to Unload Classes

`URLClassLoader.close()` handles resource lookups and JAR handles belonging to the loader; it **does not stop worker threads**, clear `ThreadLocal`, restore TCCL, or cancel pending tasks. Already-loaded classes remain usable after close while references still exist.

To retire thread-related state, perform cleanup on the proper thread/executor owner before releasing the generation; unload logging is only a JVM-dependent observation step.

## 11. A Responsible Plugin Unload Procedure

A plugin manager should have explicit states, for example:

```text
ACTIVE -> QUIESCING -> STOPPING -> CLEANING -> CLOSED -> RETIRED
```

Reference sequence:

1. **Block new invocations**: Remove the plugin from routes/dispatchers and reject new tasks, preventing concurrent unloads.
2. **Stop scheduled/background work**: Cancel periodic tasks, stop subscriptions, halt task producers.
3. **Wait for or cancel running tasks**: Use reasonable deadlines, record unfinished tasks, and do not declare success while they are still alive.
4. **Run in-worker cleanup**: Restore TCCL and call `ThreadLocal.remove` on the exact threads that set them; clean up framework-specific request contexts.
5. **Close plugin resources**: Streams, sockets, watchers, database handles, files, timers, JAR handles.
6. **Stop plugin-owned executors/threads**: `shutdown`, `awaitTermination`; if that fails, use `shutdownNow` per contract, continue verifying, and classify blockers.
7. **Unregister references from the host**: Listeners, MBeans, caches, service registries, logging appenders, callbacks, static maps, shutdown hooks.
8. **Close the class loader** if supported by the API; avoid doing so while other class loading is still in progress.
9. **Drop host references**: Manager state no longer holds plugin instances, `Class<?>`, loaders, lambdas, or `Future`s of the old generation.
10. **Verify with tools**: Inspect thread dumps/heap dumps/classloader statistics over time; do not assert immediate GC.

You can split cleanup into idempotent steps, logging errors per step while still attempting to clean up the remaining parts. For uncooperative platform threads/tasks, in practice you may need to **restart the worker process or host process** if they cannot be stopped safely.

### Standard Executor Shutdown (Illustration)

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

// Snippet inside a method with a known executor:
executor.shutdown();
try {
    if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
        executor.shutdownNow();
        if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
            System.err.println("Tasks remain active");
        }
    }
} catch (InterruptedException e) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
```

This is illustrative lifecycle-handling code; `executor` is managed by the caller. It does not automatically release all `ThreadLocal`s if tasks wrote them without removing them, and `shutdownNow` does not guarantee every task stops. For a shared host executor, **do not call `shutdown`** just to unload one plugin; you need a mechanism to cancel/clean up **the tasks belonging to that plugin** without breaking other plugins.

## 12. ThreadFactory and Preventing Unintended Loader Inheritance

When creating a shared thread pool, a `ThreadFactory` that sets an explicit baseline TCCL helps prevent accidentally inheriting a loader at the time workers are created:

```java
import java.util.concurrent.ThreadFactory;

ThreadFactory factory = task -> {
    Thread thread = new Thread(task, "host-shared-worker");
    thread.setContextClassLoader(
            ClassLoader.getPlatformClassLoader());
    return thread;
};
```

This is a snippet that uses `factory` when creating an executor; it is not a class with `main`. Choose the baseline loader based on your architecture: `ClassLoader.getPlatformClassLoader()` is only appropriate if the work does not need host application classes from TCCL; many frameworks need the system/application loader. A factory that hardcodes the platform loader can cause host plugin providers not to be found — **this is not a universal default choice for every application**.

More importantly, even when the factory sets a baseline, **every task must still restore TCCL** after temporarily switching to a plugin loader. A task can pollute a pooled thread's state regardless of what the initial context was.

For framework-managed thread pools, do not create threads manually or replace the `ThreadFactory` outside the contract; consult the container's context propagation/lifecycle mechanism.

## 13. Diagnosing ClassLoader Leaks and Retention Graphs

Do not call `System.gc()` in a test and print "GC reclaimed the loader" as a repeatable assertion. `System.gc()` is only a **request**; the JVM may not perform GC immediately, or unseen references may remain.

### Recommended Tools

- **Thread dump** (`jcmd <pid> Thread.print` or equivalent tool): Inspect thread names, stacks, WAITING/BLOCKED states, plugin method frames, and unstopped pool workers. Distinguish a legitimate long-lived idle thread from a leak retaining an old TCCL/value.
- **JFR (Java Flight Recorder):** Inspect thread activity, allocations, class loading/unloading, and related events depending on JDK/JFR configuration; interpret alongside heap evidence.
- **Heap dump + Eclipse MAT/VisualVM:** Find old class loader instances, retained size, **path to GC roots**, `Thread.contextClassLoader`, `ThreadLocalMap` entries, `FutureTask`, and listener registries.
- **`jcmd <pid> VM.classloader_stats`**: Check loader/class statistics if supported by the JVM; statistics alone are not a root-cause graph.
- **Native Memory Tracking/metaspace metrics** where appropriate: Observe memory by region; do not assume growth is solely caused by class loaders.

Reference commands (replace PID with the actual process):

```bash
jcmd <pid> Thread.print
jcmd <pid> VM.classloader_stats
jcmd <pid> GC.heap_dump /tmp/plugin-heap.hprof
```

The lines above are **tool syntax examples**, not a verbatim runnable script: `<pid>` is a placeholder, subject to JVM attach permissions and disk space. A heap dump can contain **sensitive data** and must be handled as a security artifact and never uploaded publicly.

### Reading "Path to GC Roots" Correctly

Example of a path retaining a loader:

```text
GC Root
  -> Thread "host-executor-3"
  -> contextClassLoader
  -> PluginClassLoader#v17
```

Another path:

```text
GC Root
  -> Thread "host-executor-3"
  -> threadLocals / ThreadLocalMap entry
  -> value: PluginContext
  -> class sample.plugin.PluginContext
  -> defining PluginClassLoader#v17
```

If the path goes through `CompletableFuture`, `ScheduledThreadPoolExecutor` queue, `ServiceLoader` cache, or a host static map, you must fix **the owner of that reference**, not just TCCL.

**Do not treat a rising class loader count over a few cycles as automatic proof of a leak.** GC and class unloading are not instantaneous, and JIT/runtime lifecycles are complex. Measure after controlled load/unload cycles and inspect remaining references via heap snapshots.

### How to Test with WeakReference?

You can hold a `WeakReference<ClassLoader>` in a test to observe whether the loader disappears after the host drops strong references. However:

- `ref.get() != null` at a single point in time **does not by itself prove a leak**.
- `ref.get() == null` also does not confirm all resources/tasks were cleaned up properly.
- Do not retain the loader in a local variable, lambda, or debugger inspection while testing reachability.
- Do not demand a `null` result after a fixed number of `System.gc()` calls, as such a check can be flaky.

A more reliable way to find root causes is heap dumps, GC roots, and lifecycle checks built into unit/integration tests for each registration/unregistration.

## 14. Is It Different for Java 21+ Virtual Threads?

Java 21 introduced production virtual threads, though this article prioritizes running on Java 17. Key distinctions:

- Virtual threads also have `ThreadLocal` and context class loader semantics, but their lifecycle is typically **short and task-scoped** compared to traditional pooled platform threads.
- If each task uses **its own virtual thread** and that thread actually terminates, thread-local values are normally not retained long-term by **that terminated thread itself**.
- However, plugin objects can still be retained by **unfinished tasks**, scheduler/framework references, `Future`s, callbacks, or other threads.
- Do not treat "using virtual threads" as a cure-all for loader leaks. Context propagation/inheritance and unstopped plugin tasks still require analysis.

Do not mix `Executors.newVirtualThreadPerTaskExecutor()` (Java 21) semantics into `javac --release 17` examples; that API does not exist in Java 17.

## 15. Common Pitfalls

| Mistake | Consequence | Solution |
| --- | --- | --- |
| Assuming a pool worker died because the plugin task finished | The worker stays alive and retains the old TCCL/ThreadLocal. | Distinguish task lifecycle from pool/thread lifecycle. |
| Calling `ThreadLocal.remove()` in main to clean a worker's value | Has no effect on values belonging to the worker. | Remove inside the worker/task itself. |
| `System.setProperty("java.class.path", ...)` to "swap plugins" | Does not automatically update loaders/runtime classes. | Manage loader generations and dependency graphs. |
| Setting plugin TCCL without restoring it | The old loader remains referenced by the thread. | `try/finally` to restore the previous TCCL. |
| Creating a pool while TCCL is the plugin loader | New workers may inherit the plugin loader. | Use an appropriate `ThreadFactory`/baseline context. |
| Believing `ThreadLocal` weak keys don't retain values | Values can still be strongly held in the map. | Explicit `remove()` and worker lifecycle management. |
| Calling `URLClassLoader.close()` before stopping tasks | Loader closes while tasks still run or fail loading new classes/resources. | Quiesce, stop, clean up, then close. |
| Assuming `Future.cancel(true)` definitely kills a task | Interruption requires task cooperation. | Deadlines, monitoring, process isolation for untrusted code. |
| Cleaning up only one task in a multi-worker fixed pool | Other workers still hold TL/TCCL values. | Per-task cleanup or shut down the plugin-generation pool. |
| Keeping `Class<?>`/plugin instances in a host cache | The defining loader remains reachable. | Evict caches and unregister listeners. |
| Using `System.gc()` as proof of immediate unloading | No timing guarantee. | Heap dump/path-to-roots and statistics over time. |
| Leaving `ScheduledExecutorService` recurring tasks unbounded | Scheduled callbacks can retain the plugin indefinitely. | Cancel futures, shut down according to ownership. |
| Trying `Thread.stop()` to stop a plugin | Can corrupt invariants/monitors; unsafe API. | Cooperative cancellation or separate worker processes. |

## 16. Self-Check Exercises

1. **A task has `Future.isDone() == true`; can the pool worker still be alive?** Yes. The executor may keep the worker waiting for new tasks.
2. **Why can a TCCL still pointing to an old plugin loader prevent loader collection?** A live thread holds a strong reference to the loader.
3. **A host static `ThreadLocal<Object>` holds a plugin value on a worker; does calling `remove()` in main delete that value?** No; `remove` only affects the current thread.
4. **Does `ThreadLocalMap` having weak keys mean all values are GC'd immediately when the key is lost?** No; the value can remain strongly held until cleanup.
5. **Does `URLClassLoader.close()` stop background threads or clear static host registries?** No.
6. **Is a plugin currently executing on the stack guaranteed to be eligible for unloading?** It cannot be assumed so; the task's stack frames/objects/class metadata can keep the loader reachable.
7. **Must TCCL always be restored to the system loader?** No. Restore **the value from before the temporary switch**, do not hardcode.
8. **If a `ThreadFactory` sets a baseline TCCL, do tasks still need `finally` restoration?** Yes; workers can be reused.
9. **Will a single cleanup task clear all TL values in a 10-thread fixed pool?** There is no guarantee; it only runs on one specific worker.
10. **Why is `shutdownNow()` insufficient to confirm a plugin has stopped?** Because tasks may not cooperate with interruption, and queued/callback references may still exist.
11. **Do the demo's outputs prove that GC has unloaded the class?** No. The demo only checks TCCL/TL references and that the class remains usable after close.
12. **What should be done when a plugin is untrusted and cannot be stopped cooperatively?** Place the plugin in a process with quotas/timeouts and restricted OS privileges, so the process can be terminated if uncooperative.

## 17. Official Documentation

- [Java SE 21 — Thread](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): `getContextClassLoader`, `setContextClassLoader`, context inheritance, thread lifecycle.
- [Java SE 21 — ThreadLocal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadLocal.html): per-thread values, `set`, `get`, `remove`.
- [Java SE 21 — InheritableThreadLocal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/InheritableThreadLocal.html): inheritance at thread creation time.
- [Java SE 21 — URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): `close` semantics and usability of already-loaded classes.
- [Java SE 21 — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): `shutdown`, `shutdownNow`, and `awaitTermination`.
- [Java SE 21 — Future](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html): `isDone` and `cancel`.
- [Java SE 21 — ServiceLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html): selecting class loader for provider lookup.
- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): defining loader/class identity and delegation.
- [Java SE 21 — jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): thread dumps, VM classloader stats, and heap dump depending on command/JVM.
- [Oracle Java SE 21 — Core Libraries, Thread-Local Variables](https://docs.oracle.com/en/java/javase/21/core/java-core-libraries-developer-guide.pdf): ThreadLocal mechanism.
