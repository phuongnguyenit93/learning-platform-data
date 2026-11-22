# Thread Pools and Context May Differ from the Submitting Thread

When a Java application hands off work from one thread to an `ExecutorService` or thread pool, **the thread that actually executes the work may have a different context class loader (TCCL) from the submitting thread**. Calling `submit()` has no contract to automatically propagate `Thread.currentThread().getContextClassLoader()` from the submitter to the worker on each invocation. A worker may be created beforehand, be long-lived, and execute multiple tasks belonging to different components.

This affects libraries that look up classes, resources, or providers based on the TCCL: a program may work when called directly yet lose providers when running in the background; a worker retaining an old plugin's TCCL can also cause a class loader leak after hot redeploy. This lesson explains the mechanism, presents a standalone Java 17 example, and shows how to safely **capture → set → execute → restore**.

## 1. What Is the TCCL?

Every `Thread` has a **thread context class loader**. Two important APIs:

~~~java
ClassLoader current =
        Thread.currentThread().getContextClassLoader();

Thread.currentThread().setContextClassLoader(current);
~~~

This is an **illustrative fragment**; it reads and then sets the same value back, so it does not change behavior. The TCCL can be `null`, and not every API uses it.

The TCCL typically helps library code locate implementations provided by an application or plugin. Some scenarios:

- `ServiceLoader.load(MyService.class)` typically uses the current TCCL to discover service providers according to the API rules.
- Frameworks read `META-INF/services/...`, resources, or configuration through `Thread.currentThread().getContextClassLoader().getResource(...)`.
- Application servers set the appropriate TCCL before invoking web application or plugin code.

**Distinguishing the TCCL from the defining loader.** `SomeClass.class.getClassLoader()` tells you which class loader **defined** `SomeClass`; changing the TCCL does not change that class's defining loader or fix a `ClassCastException` between two type definitions with the same name.

| Scenario | Which class loader is used? |
| --- | --- |
| `ServiceLoader.load(Service.class)` | Defaults to relying on the calling thread's TCCL. |
| `ServiceLoader.load(Service.class, chosenLoader)` | Uses the explicitly passed loader, within module/provider rules. |
| `Class.forName(name, true, chosenLoader)` | Uses the passed-in loader. |
| `Class.forName(name)` | Uses the caller's mechanism and does not default to the TCCL. |
| `MyClass.class` | A type reference linked by the JVM; it does not change automatically with the TCCL. |
| `ClassLoader.getSystemClassLoader()` | The system/application class loader, not necessarily the TCCL. |

To understand why a thread pool produces a different result, you need to determine **which lookup API the code inside the task is actually using**.

## 2. When the Context Loader Is Inherited

When creating a new `Thread` under normal conditions, the initial TCCL is **inherited from the thread that creates it**, unless the application, a `ThreadFactory`, or the environment explicitly changes it. Inheritance happens at **thread creation**, not when executing each `Runnable` or receiving each `Callable`.

~~~text
Submitter S                    Worker W in thread pool
TCCL = PluginLoader              previously created
      |                           TCCL = BaseLoader
      |                                    |
      +-- executor.submit(job) ----------> |
                                           v
                                        job runs
                                           |
                                           v
                                   TCCL = BaseLoader
                                (differs from submitter)
~~~

At the time of `submit`:

1. The executor accepts and schedules the work. It may place the task into a queue instead of creating a thread.
2. The selected worker may have already run other tasks, or may have been created by a `ThreadFactory` on a completely different thread.
3. If the task calls `Thread.currentThread().getContextClassLoader()`, the value is **the worker's current TCCL**; it is not automatically copied from the submitter.
4. If a task changes the worker's TCCL and forgets to restore it, **the next task** may see an unrelated loader.
5. `Future.get()` only waits for the result or an exception; it does not propagate the TCCL from the calling thread to the worker.

### Does the Default Thread Factory Solve This?

`new Thread(...)` and the default `ThreadFactory` typically inherit the TCCL **at the time the worker is created**. A pool may create workers when receiving the first task or when it needs to expand, but **it does not guarantee a new worker for every submission**. If a pool has a worker created while Thread A held PluginA, a task submitted later by Thread B may continue to see PluginA instead of PluginB. You should not rely on the first submitter, because the pool may initialize workers early, recreate workers, or use a custom factory.

## 3. A Runnable Java 17 Example with Deterministic Output

This example creates a `URLClassLoader` representing a plugin and a single-worker executor. The `ThreadFactory` sets the worker's TCCL **fixed to the system class loader**, which demonstrates the difference without depending on when the thread was created.

Create the file **`ThreadPoolContextDemo.java`**:

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;

public class ThreadPoolContextDemo {
    private static <T> Callable<T> withContextLoader(
            ClassLoader desired, Callable<T> action) {

        return () -> {
            Thread worker = Thread.currentThread();
            ClassLoader previous = worker.getContextClassLoader();
            worker.setContextClassLoader(desired);

            try {
                return action.call();
            } finally {
                worker.setContextClassLoader(previous);
            }
        };
    }

    public static void main(String[] args) throws Exception {
        ClassLoader baseLoader = ClassLoader.getSystemClassLoader();

        try (URLClassLoader pluginLoader =
                     new URLClassLoader(new URL[0], baseLoader)) {

            ThreadFactory factory = job -> {
                Thread worker = new Thread(job, "context-worker");
                worker.setContextClassLoader(baseLoader);
                return worker;
            };

            ExecutorService pool =
                    Executors.newSingleThreadExecutor(factory);

            Thread submitter = Thread.currentThread();
            ClassLoader previousSubmitterLoader =
                    submitter.getContextClassLoader();

            try {
                submitter.setContextClassLoader(pluginLoader);

                System.out.println("Submitter uses plugin: "
                        + (submitter.getContextClassLoader() == pluginLoader));

                boolean plain = pool.submit(() ->
                        Thread.currentThread().getContextClassLoader()
                                == pluginLoader).get();
                System.out.println("Plain task uses plugin: " + plain);

                boolean wrapped = pool.submit(
                        withContextLoader(pluginLoader, () ->
                                Thread.currentThread().getContextClassLoader()
                                        == pluginLoader)).get();
                System.out.println("Wrapped task uses plugin: " + wrapped);

                boolean restored = pool.submit(() ->
                        Thread.currentThread().getContextClassLoader()
                                == baseLoader).get();
                System.out.println("Worker restored base: " + restored);

            } finally {
                submitter.setContextClassLoader(previousSubmitterLoader);
                pool.shutdown();

                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    pool.shutdownNow();
                }
            }
        }
    }
}
~~~

Run with JDK 17 or newer:

~~~bash
javac --release 17 ThreadPoolContextDemo.java
java ThreadPoolContextDemo
~~~

**Exact stdout:**

~~~text
Submitter uses plugin: true
Plain task uses plugin: false
Wrapped task uses plugin: true
Worker restored base: true
~~~

Explanation of each result:

1. `pluginLoader` and `baseLoader` are two distinct objects. `new URL[0]` means the example **does not actually load plugin classes**, and instead only checks TCCL identity in an independent, reproducible way.
2. The submitter sets its TCCL to `pluginLoader`. Therefore, the first line is `true`.
3. The `ThreadFactory` creates the worker with a fixed TCCL of `baseLoader`; a task submitted via a plain `submit` still sees the base loader, so the second line is `false`.
4. `withContextLoader` saves the worker's previous context, temporarily sets the plugin context, and then runs `action.call()`. The third line is `true`.
5. The wrapper's `finally` block restores the exact previous TCCL even if the action throws an exception. The next task sees the base loader, and the final line is `true`.
6. The `finally` block in `main` restores the submitter's TCCL, shuts down the pool, and waits for the worker to stop. `try-with-resources` closes the `URLClassLoader` resource. Closing the loader **does not force the JVM to unload all classes immediately**.

**Practical implication:** A worker's TCCL can differ from the submitter's even when the task was submitted by that submitter. If a library calls `ServiceLoader` or looks up resources using the TCCL inside a worker, it may receive a different result.

## 4. The capture → set → execute → restore Pattern

When a task **requires the submitter's TCCL** by design, capture it at the submission boundary:

~~~text
SUBMITTER
    captured = currentThread.getContextClassLoader()
    executor.submit(wrap(captured, task))

WORKER
    previous = currentThread.getContextClassLoader()
    currentThread.setContextClassLoader(captured)
    try:
        task.call()
    finally:
        currentThread.setContextClassLoader(previous)
~~~

In Java, you can use the same `withContextLoader` function from the previous example. The following fragment assumes `ExecutorService executor` and `Callable<T> task` are already available inside a generic method:

~~~java
ClassLoader captured =
        Thread.currentThread().getContextClassLoader();

Future<T> result = executor.submit(
        withContextLoader(captured, task));
~~~

This is a **fragment**, so appropriate declarations/imports for `Future`, `T`, `task`, and `executor` are required. Important points:

- **Capture at submission time** if that is the context to propagate, rather than capturing once when creating a singleton pool.
- **Set on the worker when the task starts**, rather than only setting it on the submitter before calling `submit`.
- **Restore the exact previous value**, including `null`, using `finally`. Do not arbitrarily replace any previous loader with the system loader.
- Use a separate wrapper for `Runnable` if the task does not return a result, preserving the executor's exception handling.
- Do not propagate the TCCL indiscriminately to every task; general system tasks should sometimes use the base loader.
- Passing the loader via an explicit argument when the API supports it (`Class.forName(name, true, loader)`, `ServiceLoader.load(service, loader)`) usually involves less hidden state.
- A captured loader is a **strong reference** inside the task/queue. When a plugin reaches the end of its lifecycle, pending tasks must be cancelled and these references released.

If the wrapper only restores the TCCL while the task also modifies a `ThreadLocal`, logging MDC, security context, or transaction context, those states **are not automatically cleaned up**. They have their own mechanisms and lifecycles.

## 5. Why ServiceLoader and Resources Can Produce Different Results

Suppose the provider class and `META-INF/services/com.acme.Service` metadata exist only on the plugin loader's search path. When called directly on the submitter (TCCL=plugin), discovery can find the provider; when called in a worker (TCCL=base), the provider may not be found.

~~~text
Submitter TCCL=PluginLoader
  ServiceLoader.load(Service.class)
      └─ sees the plugin's provider

Worker TCCL=BaseLoader
  ServiceLoader.load(Service.class)
      └─ may not see the plugin provider
~~~

The Java example below is a **fragment**; it requires a `MyService` interface and a valid provider declaration, so it **is not yet a standalone program**:

~~~java
ServiceLoader<MyService> providers =
        ServiceLoader.load(MyService.class);

for (MyService provider : providers) {
    provider.execute();
}
~~~

The single-argument call above uses the TCCL according to the API rules. You can choose the explicit overload to avoid depending on worker state:

~~~java
ServiceLoader<MyService> providers =
        ServiceLoader.load(MyService.class, pluginLoader);
~~~

This fragment requires `pluginLoader` and the corresponding types/imports. Using an explicit loader does not guarantee a valid provider if the `MyService` interface was defined separately by the host and the plugin: the provider must still implement **the exact same interface definition** that the consumer expects. The module graph, visibility, and `uses`/`provides` can also affect discovery in JPMS.

Similarly, APIs can differ:

| API in worker | Does it use the TCCL? |
| --- | --- |
| `Thread.currentThread().getContextClassLoader().getResource(name)` | Yes, it uses the worker's loader. |
| `ServiceLoader.load(Service.class)` | Normally uses the TCCL per the API. |
| `SomeClass.class.getResource("config.properties")` | Based on the associated class/package/module; **does not default to the TCCL**. |
| `Class.forName(name, true, loader)` | Uses the explicitly passed loader. |

Therefore, **a resource returning `null` is not necessarily caused by the thread pool**: it could be an incorrect path name, module encapsulation, a loader that cannot see the JAR, missing provider metadata, or code looking it up with a different API.

## 6. ThreadFactory, Shared Pools, and Plugin-Specific Pools

A `ThreadFactory` can create workers with the desired TCCL right from the start:

~~~java
ThreadFactory factory = job -> {
    Thread worker = new Thread(job, "plugin-worker");
    worker.setContextClassLoader(pluginLoader);
    return worker;
};
~~~

This is a **fragment**; `pluginLoader` must be declared where it is used. It makes sense when **the pool belongs to a single plugin** and has a matching lifecycle. However, for a pool **shared across multiple plugins**, a single fixed TCCL is not enough: a task from plugin B could be processed using loader A. In that case, a per-task wrapper or passing the class loader explicitly is usually more suitable.

There is another issue: a task can change the TCCL while running. If it forgets to restore it, even a worker that was properly created by the factory becomes "dirty" for subsequent tasks. You should not attempt to change a running worker's TCCL **from another thread**: concurrent changes can cause hard-to-reproduce context bugs. Set and restore it in code executed on the worker itself.

## 7. CompletableFuture and Callbacks Do Not Necessarily Run on the Submitter

`CompletableFuture.supplyAsync(...)` or `runAsync(...)` without a passed executor typically uses `ForkJoinPool.commonPool()` when appropriate (with a fallback depending on conditions), so the stage runs on a thread managed by the framework/pool.

~~~java
CompletableFuture<Result> future =
        CompletableFuture.supplyAsync(() -> queryProvider());
~~~

This is an **illustrative fragment**: `Result` and `queryProvider()` are not declared. You cannot infer a stage's TCCL from the thread that created the future.

Points to note:

- `thenApply(...)` is not async: the action may run on the thread that completes the preceding stage or when registering on a stage that has already completed.
- `thenApplyAsync(...)` schedules on the associated executor; the TCCL is that of the thread executing that stage.
- Multiple stages can run on **multiple different threads**. If individual stages require the plugin's TCCL, the context must be ensured at **each boundary where it is actually needed**.
- Scheduled executors, event loops, or background callbacks follow the same principle: determine **who owns the thread**, rather than assuming it is the thread that submitted the work.

Frameworks sometimes provide task decorators/context propagation. Check carefully whether that feature propagates the **TCCL** or only MDC, security context, or tracing context. These contexts must not be treated as identical.

## 8. Class Loader Leaks After Undeploy
If a long-lived worker forgets to restore its TCCL, it holds a strong reference to the old plugin loader after the plugin stops. Similarly, tasks waiting in a queue or a `Future`/callback can also retain the loader via a closure. This both causes incorrect provider lookups and delays class unloading.

```text
Host executor → live worker → contextClassLoader → old PluginLoader
```

During unload, block new tasks, let current tasks complete or cancel according to policy, restore the TCCL in `finally`, clean up queues/callbacks/`ThreadLocal`, and shut down the pool **if owned by the plugin**. `URLClassLoader.close()` does not automatically release all classes immediately. The lesson "Memory Leaks..." covers GC roots, metaspace, and how to measure across multiple redeploy cycles in depth.
## 9. Common Programming Mistakes

**Only setting the TCCL on the submitter:**

~~~java
Thread.currentThread().setContextClassLoader(pluginLoader);
executor.submit(task);
~~~

This is an **anti-pattern fragment**; it does not restore the TCCL and does not guarantee that the worker sees the plugin loader. The submitter itself can carry the wrong context after the call.

**Setting the TCCL in the worker without restoring it:**

~~~java
executor.submit(() -> {
    Thread.currentThread().setContextClassLoader(pluginLoader);
    runPluginJob();
});
~~~

This is also just an **illustrative error fragment**. When `runPluginJob()` returns or throws an exception, the worker may retain that loader for the next task.

**Confusing `InheritableThreadLocal` with per-task propagation:** `InheritableThreadLocal` also primarily passes data when creating a child thread. It does not update the value each time a thread pool picks up a task. The TCCL has its own `Thread` inheritance mechanism, which likewise does not automatically update when submitting.

**Mistaking an SPI error for solely a loader issue:** A `ServiceConfigurationError` can be caused by missing metadata, an unloadable class/provider, module access, or a provider not implementing the right interface. Having the right TCCL is not necessarily enough.

**Forgetting to clean up state outside the TCCL:** `ThreadLocal`, MDC, transaction context, or application objects are not automatically restored by a wrapper that only handles the `ClassLoader`.

## 10. Debugging Workflow

1. Right at the submitter, log `Thread.currentThread().getName()`, the TCCL, and the class loader of the service type being used.
2. Right inside the worker when the task runs, log **the exact same information** and compare; avoid logging before enqueueing and assuming the pool thread is similar.
3. Check where the worker is created and whether the `ThreadFactory` sets the TCCL.
4. Check whether an earlier task called `setContextClassLoader` without a `finally` block.
5. For `ServiceLoader`, print the actual providers or discovery errors and verify which loader defined the interface.
6. For resources, check the URL from `getResource()` using the right loader and path, including module access.
7. Use a capture/set/restore wrapper or pass the loader explicitly, then verify that **a task after the wrapper sees the original loader**.
8. For hot redeploys, check queues and threads that still retain the old deployment's class loader.

## 11. Self-Check

**Question 1.** Thread S has TCCL=PluginA, and pool worker W already has TCCL=Base. After `submit`, which loader does the task see if there is no propagation?

**Answer:** It sees **Base**, which is W's current TCCL.

**Question 2.** A worker was created while thread A held PluginA; the next day, thread B holds PluginB and submits a task to that same worker. Does the worker's TCCL automatically become PluginB?

**Answer:** No. Inheritance at thread creation time is not a data propagation mechanism on every submit.

**Question 3.** Why does the wrapper need `finally`?

**Answer:** To restore the previous TCCL when the task completes or throws an exception, avoiding affecting other tasks or retaining the old loader.

**Question 4.** Can `ServiceLoader.load(Service.class)` produce different results when called on the submitter versus the worker?

**Answer:** Yes, because different TCCLs can change which providers are visible.

**Question 5.** Does `Class.forName(name, true, loader)` implicitly use the TCCL?

**Answer:** No; this overload uses the explicitly passed `loader`.

**Question 6.** Why can a `ClassCastException` still occur on a provider even when the TCCL is correct?

**Answer:** It can happen because the provider and consumer use two interface definitions with the same name but different defining loaders; the TCCL does not automatically unify types.

## Key Takeaways

**The TCCL belongs to the executing thread and is not automatically attached to a task upon `submit`.** Workers are created and reused at a different time from the submitter, so they may look up different classes, resources, and providers. If the submitter's context is truly needed, **capture → set on the worker → execute → restore in finally**, or pass the `ClassLoader` explicitly when the API supports it. Queues and workers must be managed when a plugin stops to avoid using the wrong loader and retaining an old deployment.

**Official Documentation:**

- `Thread` (Java SE 17): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
- `ClassLoader` (Java SE 17): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- `ExecutorService`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- `Executors` and `ThreadFactory`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executors.html
- `ServiceLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- `CompletableFuture`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
