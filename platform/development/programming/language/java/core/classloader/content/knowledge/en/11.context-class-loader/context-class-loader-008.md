# Memory Leak When a Long-Lived Thread Holds a Plugin Loader

## 1. Symptom

A long-running Java application may load a plugin with its own ClassLoader, run the plugin's code, and then unload/redeploy it. If cleanup completes, the old ClassLoader and the classes it defined may become eligible for reclamation.

However, a long-lived host thread may be holding a **Thread Context ClassLoader (TCCL)** pointing to the old loader. This is a strong reference:

~~~text
GC root / live thread
       |
       v
Host worker thread (still alive)
       |
       v
Thread.contextClassLoader
       |
       v
PluginClassLoader (old version)
       |
       +-- class metadata and related objects

=> Loader remains reachable even though the plugin has stopped
=> Plugin classes might not be unloaded
~~~

After multiple deployments, multiple retained versions of PluginClassLoader can cause heap and metaspace growth and occasionally OutOfMemoryError: Metaspace. Not every memory increase is caused by TCCL; this article clarifies this mechanism and how to diagnose other retention paths.

**Goals:** distinguish TCCL from the defining loader; understand reachability; reproduce a strong reference using Java 17+; restore the loader in finally; control context inheritance in child threads; manage executors, ThreadLocal, and the plugin lifecycle; find GC roots in a heap dump.

## 2. TCCL Is Not the Defining Loader

The java.lang.Thread API:

~~~java
Thread t = Thread.currentThread();
ClassLoader previous = t.getContextClassLoader();
t.setContextClassLoader(pluginLoader);
~~~

This is illustrative code placed inside a method that has a pluginLoader variable; it is not yet a standalone program.

TCCL is **a mutable property of a Thread**. Some frameworks use it to find classes, resources, or providers. According to the JDK API, when a new thread is created without specific configuration, the context loader is usually inherited from the thread that created it.

| API / Concept | Meaning |
| --- | --- |
| Thread.currentThread().getContextClassLoader() | The thread's current context loader. |
| Thread.setContextClassLoader(loader) | Changes the context for this thread; does not redefine classes. |
| SomeClass.class.getClassLoader() | The class's defining loader; does not change because TCCL changes. |
| ClassLoader.getSystemClassLoader() | The system/application loader; does not automatically match every thread's TCCL. |
| ServiceLoader.load(service) | An example of an API that uses the context loader according to this overload's contract. |
| ServiceLoader.load(service, loader) | An overload that allows passing a loader explicitly. |

**TCCL does not change a class's identity.** Ordinary runtime type identity involves the binary name together with the defining loader. Changing TCCL does not move an existing Class from the plugin to the host or vice versa.

## 3. Why Can TCCL Become a Memory Leak?

### 3.1 GC Sees References, Not Business State

When the host marks a plugin STOPPED, the ClassLoader object is not necessarily collectible. If the worker is still alive, the JVM can still keep the Thread; the contextClassLoader field in Thread holds a reference to PluginLoader.

~~~text
Host ExecutorService
    |
    +-- worker (waiting to receive the next task)
           |
           +-- contextClassLoader = oldPluginLoader

Plugin Registry has removed the old plugin
JAR handle has been closed
But oldPluginLoader still has a strong reference path
~~~

In a continuously running server, a worker can outlive every plugin version it has ever served.

### 3.2 Class Unloading Conditions

According to JLS §12.7, a class/interface may be unloaded only if its **defining ClassLoader** can be reclaimed by the garbage collector. If a long-lived thread holds the loader, this condition is not met.

However, **clearing the reference path does not guarantee that the JVM will unload immediately**. GC and class unloading are performed according to demand, configuration, and implementation. It is necessary to distinguish:

1. The plugin has stopped accepting work.
2. All tasks, callbacks, threads, and registries have been cleaned up.
3. The ClassLoader is no longer strongly reachable.
4. The JVM has actually reclaimed/unloaded the classes (which may happen later).

**System.gc() is not a decisive measurement:** it is a request/hint, not a promise that the loader will disappear immediately.

### 3.3 Heap and Metaspace

The ClassLoader and objects holding references reside on the heap. The HotSpot JVM uses metaspace to manage various kinds of class metadata. If the old loader is not collectible, class metadata may also continue to exist; repeated redeploys can put pressure on metaspace. Symptoms also depend on the number of classes, GC, memory limits, and other references.

## 4. Common Scenario: A Plugin Task Changes TCCL on a Host Pool

An application creates a shared pool:

~~~text
Host starts
    |
    +-- ExecutorService hostPool
           |
           +-- host-worker-1 (lives for hours)
~~~

Plugin v1 runs inside the worker:

~~~java
Thread.currentThread().setContextClassLoader(pluginLoader);
invokePlugin();
// Forgot to restore
~~~

If the task returns successfully, the worker can still be reused by the pool with **contextClassLoader = PluginLoaderV1**. The host unloads v1 and then loads v2 with a new loader, yet loader v1 still remains on the worker.

Twofold consequence:

- **Retention:** the old loader remains reachable.
- **Wrong context:** a subsequent task may mistakenly use the old plugin's loader to look up providers, classes, or resources.

The issue typically surfaces when the application redeploys multiple times rather than on the first startup.

## 5. Java 17+ Example 1: Observing a Strong Reference in a Long-Lived Thread

Create the file **ContextRetentionDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;

public class ContextRetentionDemo {
    static final class PluginLoader extends ClassLoader {
        PluginLoader(ClassLoader parent) {
            super(parent);
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader host = ContextRetentionDemo.class.getClassLoader();
        PluginLoader plugin = new PluginLoader(host);

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            started.countDown();
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "host-worker");

        worker.setContextClassLoader(plugin);
        worker.start();
        started.await();

        System.out.println("worker alive = " + worker.isAlive());
        System.out.println("worker holds plugin = "
                + (worker.getContextClassLoader() == plugin));

        worker.setContextClassLoader(host);
        System.out.println("worker restored host = "
                + (worker.getContextClassLoader() == host));

        release.countDown();
        worker.join();
        System.out.println("worker stopped = " + !worker.isAlive());
    }
}
~~~

Run:

~~~bash
javac ContextRetentionDemo.java
java ContextRetentionDemo
~~~

Deterministic stdout in the example:

~~~text
worker alive = true
worker holds plugin = true
worker restored host = true
worker stopped = true
~~~

**Analysis:** the worker is waiting on the latch and is still alive. Before the reset, the worker's TCCL field holds the exact plugin object. Replacing it with host severs **the retention path through TCCL**, and then the program releases the latch and joins to terminate the thread.

**Limitation:** the example does not prove that GC occurred. The local variable plugin in main still holds the loader, and the loader in the example has not been used to define plugin classes. It only confirms the strong reference mechanism and does not measure metaspace usage. In production, it is customary to have **the worker restore the context itself in finally** rather than having another thread replace the context while it is running work.

## 6. The Core Fix: Save and Restore the Previous TCCL

The preferred pattern:

~~~java
Thread current = Thread.currentThread();
ClassLoader previous = current.getContextClassLoader();

current.setContextClassLoader(pluginLoader);
try {
    invokePlugin();
} finally {
    current.setContextClassLoader(previous);
}
~~~

This is a snippet placed inside a method that has an appropriate pluginLoader and invokePlugin().

Why is **finally** needed?

- The task may return early or throw an exception.
- The thread pool keeps the worker alive after the task completes.
- Restoration must happen before the worker accepts the next task.
- **previous** may be the host's loader, another framework's loader, or null. Do not assume that the system loader is always correct.

**setContextClassLoader(null) is not equivalent to restoring previous.** Null has the API's fallback semantics, but it may not restore the exact thread context from before the plugin ran.

If the setContextClassLoader operation fails before entering try (for example, due to runtime security constraints), do not conclude that the scope used the new loader. Handle the error according to the framework contract.

**If TCCL is not needed, do not change it.** When an API supports passing a ClassLoader explicitly, using that parameter can avoid modifying shared thread state.

## 7. Java 17+ Example 2: Executor Restores TCCL Even When Callable Fails

Create **ScopedContextDemo.java**:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ScopedContextDemo {
    static final class PluginLoader extends ClassLoader {
        PluginLoader(ClassLoader parent) {
            super(parent);
        }
    }

    static <T> Callable<T> withContext(
            ClassLoader pluginLoader,
            Callable<T> action) {

        return () -> {
            Thread current = Thread.currentThread();
            ClassLoader previous = current.getContextClassLoader();

            current.setContextClassLoader(pluginLoader);
            try {
                return action.call();
            } finally {
                current.setContextClassLoader(previous);
            }
        };
    }

    public static void main(String[] args) throws Exception {
        ClassLoader host = ScopedContextDemo.class.getClassLoader();
        PluginLoader plugin = new PluginLoader(host);

        ExecutorService pool = Executors.newSingleThreadExecutor(task -> {
            Thread worker = new Thread(task, "host-pool-1");
            worker.setContextClassLoader(host);
            return worker;
        });

        try {
            System.out.println("before = " + pool.submit(
                    () -> Thread.currentThread()
                            .getContextClassLoader() == host
            ).get());

            System.out.println("during = " + pool.submit(
                    withContext(plugin, () ->
                            Thread.currentThread()
                                    .getContextClassLoader() == plugin)
            ).get());

            System.out.println("after = " + pool.submit(
                    () -> Thread.currentThread()
                            .getContextClassLoader() == host
            ).get());

            try {
                pool.submit(withContext(plugin, () -> {
                    throw new IllegalStateException("boom");
                })).get();
            } catch (ExecutionException expected) {
                System.out.println("failure = "
                        + expected.getCause()
                                .getClass().getSimpleName());
            }

            System.out.println("after failure = " + pool.submit(
                    () -> Thread.currentThread()
                            .getContextClassLoader() == host
            ).get());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Run:

~~~bash
javac ScopedContextDemo.java
java ScopedContextDemo
~~~

Stdout:

~~~text
before = true
during = true
after = true
failure = IllegalStateException
after failure = true
~~~

Explanation:

1. The host ThreadFactory creates the worker with its TCCL set to the host loader, independent of the submitting thread's context.
2. The **withContext** wrapper switches to the plugin loader for the scope of the work.
3. After the job finishes, **finally** restores previous.
4. When the job throws **IllegalStateException**, Future.get wraps it in **ExecutionException**, yet cleanup still runs.
5. The final task sees the host TCCL, showing that no plugin context remains on that worker.

**This is not yet a solution for all reference leaks.** A Callable may capture the plugin loader and still remain in a task queue, Future, or callback registry held by the host. Those references must be canceled/removed during the unload lifecycle.

## 8. The Second Risk: Child Threads Inherit TCCL at Creation Time

The JDK Thread API specifies that the default context loader of a new thread is inherited from the thread that created it, unless configured otherwise.

~~~text
Thread A (host): TCCL = PluginLoader
        |
        | new Thread(...)
        v
Thread B: inherited TCCL = PluginLoader
        |
Thread A restores HostLoader
        |
Thread B still has its own TCCL pointing to PluginLoader
~~~

Merely restoring A does not cause B to restore itself. If B lives for hours, it can retain the old loader.

### Java 17+ Example 3

Create the file **InheritedContextDemo.java**:

~~~java
public class InheritedContextDemo {
    static final class PluginLoader extends ClassLoader {
        PluginLoader(ClassLoader parent) {
            super(parent);
        }
    }

    public static void main(String[] args) throws Exception {
        Thread parent = Thread.currentThread();
        ClassLoader previous = parent.getContextClassLoader();
        PluginLoader plugin = new PluginLoader(previous);
        Thread child;

        try {
            parent.setContextClassLoader(plugin);

            child = new Thread(() -> {
                System.out.println("child inherited plugin = "
                        + (Thread.currentThread()
                                .getContextClassLoader()
                                instanceof PluginLoader));
            }, "background-child");

            System.out.println("before start = "
                    + (child.getContextClassLoader() == plugin));
        } finally {
            parent.setContextClassLoader(previous);
        }

        child.start();
        child.join();

        System.out.println("parent restored = "
                + (parent.getContextClassLoader() == previous));
    }
}
~~~

Run:

~~~bash
javac InheritedContextDemo.java
java InheritedContextDemo
~~~

Stdout:

~~~text
before start = true
child inherited plugin = true
parent restored = true
~~~

**before start = true** proves that the child received the context before starting. In the example, the child terminates, so it does not demonstrate a long-lived leak; in practice, if the child runs indefinitely, it can retain PluginLoader.

### Why Can a Thread Pool Inherit Unintentionally?

**Executors.newSingleThreadExecutor** is not required to create the worker immediately when constructing the executor; the worker may be created when submitting the first task. If the submitting thread at that moment carries a plugin TCCL, the default ThreadFactory can cause the worker to inherit the plugin loader. A host-owned ThreadFactory should **set an explicit baseline context loader** for all workers.

## 9. Proper Ownership When Managing Executors

| Component | Owner | When Unloading a Plugin |
| --- | --- | --- |
| Shared host ExecutorService | Host | Do not shut down the whole pool; stop/cancel tasks belonging to the plugin, wait for cleanup, and reset TCCL on the worker. |
| Plugin-owned ExecutorService | Plugin/container | Stop accepting tasks, shutdown, awaitTermination, and cancel if necessary. |
| Plugin ScheduledExecutorService | Plugin | Cancel scheduled jobs, shut down, and drop references to the plugin's Runnable/Callable. |
| Dedicated thread created by the plugin | Plugin | Stop cooperatively via interrupt/stop flag, unblock, and join appropriately. |
| Host ThreadFactory | Host | Set a safe baseline TCCL for workers. |
| Host registry of listeners/callbacks | Host + plugin | Unregister callbacks and references before finishing unload. |
| ThreadLocal on shared worker | Scope owning key/value | Remove in finally when the scope ends. |

**Do not use Thread.stop** to forcibly stop a worker: it is dangerous and can break invariants. Interrupt is only a signal and does not prove that the thread has died. A task that does not respond to interrupts requires a timeout and an appropriate stop protocol, and should not be reported unconditionally as a successful teardown.

**Do not change the TCCL of a busy worker from another thread** in production without coordination; doing so can affect ongoing lookups. The safe sequence is to stop accepting new tasks, wait for/cancel tasks, let cleanup execute on the thread running the task itself, and then manage references.

## 10. ThreadLocal Is a Separate Retention Path

TCCL is a field on Thread. ThreadLocal uses a **ThreadLocalMap** structure, where the value may be an instance defined by the plugin loader.

~~~text
Live Thread
  |
  +-- contextClassLoader -> PluginLoader
  |
  +-- threadLocals / ThreadLocalMap
         |
         +-- Entry.value -> PluginObject
                                 |
                                 +-- defining PluginLoader
~~~

Keys in ThreadLocalMap are weak, but **values can still be retained** on a long-lived worker if the scope does not remove them. Forgetting TCCL and forgetting ThreadLocal can simultaneously create two strong retention paths.

Cleanup pattern for a scope-owned ThreadLocal:

~~~java
ThreadLocal<Object> state = new ThreadLocal<>();

try {
    state.set(pluginObject);
    runPluginTask();
} finally {
    state.remove();
}
~~~

This is an illustrative snippet, not a complete program; it requires an appropriate pluginObject and runPluginTask.

**Restoring TCCL does not automatically call state.remove().** Conversely, removing a ThreadLocal does not automatically reset the context loader. When using both, clean up both in finally (and handle ordering/errors if cleanup can throw an exception).

Do not use reflection into Thread internals to "clear out all ThreadLocals" of a framework without clear ownership.

## 11. Safe Unload/Redeploy Procedure

~~~text
1. Transition the plugin into the STOPPING state
         |
         v
2. Block new tasks/callbacks belonging to the plugin
         |
         v
3. Cancel/drain the queue and running tasks with a timeout
         |
         v
4. In every task/plugin callback:
   - restore TCCL in finally
   - remove scope-owned ThreadLocal values
   - close streams/sessions/resources
         |
         v
5. Shut down and wait for plugin-owned threads/executors
         |
         v
6. Unregister listeners, schedulers, drivers, MBeans,
   logging/service hooks, and caches/callbacks still holding the plugin
         |
         v
7. Clear host references to plugin objects and loader
         |
         v
8. Observe class-loader retention across multiple redeploys
~~~

**Race conditions to watch out for:**

- A new task slips into the queue right after stop begins.
- A running task spawns an additional Thread that inherits the plugin TCCL.
- The pool replaces a worker with a new thread while the context is incorrect.
- A Future/cache still holds a Callable that captures the plugin loader.
- Another callback is still running when the registry has already marked the plugin stopped.
- An exception causes the cleanup branch not to execute.

Therefore, unloading may require an explicit **quiescing/draining** state, rather than merely deleting the plugin object from a map and hoping GC handles it.

## 12. URLClassLoader.close Is Not a Command to Unload All Classes

Some loaders such as **URLClassLoader** have **close()** to close resources and file handles. However, if a Thread still has a TCCL pointing to the closed URLClassLoader, that loader remains reachable.

It is necessary to distinguish:

- **Closing resource handles**.
- **Stopping background work**.
- **Removing references** to the ClassLoader and plugin objects.
- **JVM reclamation when eligible**.

Do not arbitrarily close a loader shared among multiple active plugins.

## 13. Diagnosing with Heap Dump, JFR, and jcmd

If a leak is suspected after a redeploy, you need to find **the reference path retaining the old loader**, not just look at a RAM chart.

### 13.1 Tools

For the HotSpot JVM, there are suitable commands:

~~~bash
jcmd
jcmd <PID> help
jcmd <PID> VM.classloader_stats
jcmd <PID> GC.class_histogram
jcmd <PID> GC.heap_dump /path/to/heap.hprof
~~~

Syntax and availability depend on the JDK/JVM; run **jcmd <PID> help** to confirm. A heap dump can be large, time-consuming, and contain sensitive data; do not generate one in production without operational procedures/authorization.

- **JFR (Java Flight Recorder)**: track class load/unload events, GC, and resources when enabled with an appropriate configuration.
- **Eclipse Memory Analyzer (MAT)**: open a heap dump and use **Path to GC Roots**, incoming references, and retained size.
- **Thread dump**: find workers that are alive, stuck, or still holding old callbacks.
- **Metaspace/classloader metrics**: compare multiple deploy cycles against a baseline.

### 13.2 Path to GC Roots Patterns

If the cause is TCCL, the heap analyzer may show a path:

~~~text
GC Root: Java Thread
   |
   -> java.lang.Thread
        |
        -> contextClassLoader
             |
             -> PluginClassLoader (old deployment)
~~~

If the cause is something else:

~~~text
GC Root
   |
   -> host ExecutorService / listener registry / cache
        |
        -> Future / Runnable / callback / PluginObject
             |
             -> plugin class / PluginClassLoader
~~~

When both exist, fixing one path may still not be enough. **A strong path to a GC root** is the valid evidence; merely seeing an object in the heap does not by itself prove a leak if GC has not yet occurred.

### 13.3 Avoid Tests That Rely on System.gc

You can use WeakReference<ClassLoader> in diagnostic experiments, but do not conclude with certainty that the loader must disappear after **System.gc()**. GC may be delayed/disabled depending on options, class unloading does not necessarily happen immediately, and stack local variables/debuggers can also hold references.

The three Java examples above intentionally verify the values **TCCL==plugin**, **restore==host**, and **thread inheritance**, without requiring GC to occur at an exact moment.

### 13.4 Measuring Across Multiple Redeploy Cycles

1. Record the number of loaders/classes/metaspace after warm-up.
2. Deploy the plugin and run a representative workload.
3. Unload using the same procedure, without skipping timeouts.
4. Repeat for multiple cycles and compare how many old plugin loaders remain reachable.
5. When the number of old loaders grows abnormally, take a heap dump and inspect Path to GC Roots.
6. Cross-reference the task/callback source code to identify where TCCL is set without restoring or where a strong reference is held.

Do not conclude there is a leak merely because metaspace usage is higher right after a deploy before GC has had a chance to run.

## 14. Common Misconceptions

- **"The plugin has stopped, so the classes will definitely unload."** False: class unloading depends on the reachability of the defining loader and the JVM's decisions.
- **"TCCL is just a String loader name."** False: it is a reference to a ClassLoader object.
- **"A thread pool automatically discards the worker after each task."** False: workers are typically reused.
- **"Restoring the context to null is always right."** False: you must restore the previous context, even though previous may be null.
- **"Restoring the parent TCCL also restores all children."** False: a child has its own separate context once created.
- **"A pool created early cannot inherit the plugin loader."** There is no guarantee that workers are also created early.
- **"Cleaning up TCCL also cleans up ThreadLocal."** False: they are two different mechanisms.
- **"Daemon threads do not hold objects."** False: while the JVM is alive, a daemon thread can still hold references.
- **"Once a worker is interrupted, it will definitely terminate."** False: the task must cooperate.
- **"URLClassLoader.close automatically releases all classes."** False: it does not remove references from the host.
- **"System.gc did not unload = definitely a leak."** Insufficient evidence; a heap path and measurements over time are needed.

## 15. Knowledge Self-Check

**Question 1.** A long-lived host worker holds TCCL = PluginLoaderV1 after the plugin stops. Why might the loader not yet be collectible?

**Answer:** Thread.contextClassLoader still holds a strong reference to PluginLoaderV1 from a live thread.

**Question 2.** Why use try/finally instead of calling setContextClassLoader(plugin), invoking the task, and then resetting afterward?

**Answer:** The task may throw an exception or return early; finally restores previous along the applicable execution paths.

**Question 3.** Main has the plugin TCCL at the time of new Thread, and then main restores before child.start. Can the child still carry the plugin loader?

**Answer:** Yes, because a new Thread typically inherits the context at the time the Thread is created.

**Question 4.** A host Future holds a Runnable capturing a plugin object, while TCCL has already been restored. Can a leak still occur?

**Answer:** Yes, the Runnable/Future is a separate retention path; the queue/registrations/host references need to be cleaned up.

**Question 5.** Since ThreadLocalMap uses weak keys, does the plugin value disappear automatically when the key is no longer held?

**Answer:** There is no immediate guarantee; the value may remain in a long-lived thread, so it needs to be removed in finally.

**Question 6.** Why is classloader.close not enough to prove that classes are unloaded?

**Answer:** Close cleans up resources/handles rather than removing all references, and it does not force GC.

**Question 7.** Which tool shows what is holding the old plugin loader?

**Answer:** A heap dump with Path to GC Roots/dominator tree; JFR, jcmd, thread dumps, and metrics assist with diagnosis.

**Question 8.** A plugin owns a ScheduledExecutorService. What do the cleanup steps require?

**Answer:** Cancel scheduled tasks, shut down and wait for termination with a timeout, and clean up callbacks, TCCL/ThreadLocal, and references.

**Question 9.** If you only need to load a provider and the API accepts an explicit loader, do you always have to change TCCL?

**Answer:** No. Passing the loader explicitly often avoids modifying shared state when appropriate.

**Question 10.** After clearing all strong references, must the JVM unload immediately?

**Answer:** No. Being eligible for reclamation does not mean immediate reclamation is guaranteed.

## 16. Key Takeaways

~~~text
TCCL leak:
Long-lived host Thread
      -> contextClassLoader
      -> PluginLoader (old version)
      -> class metadata/objects retained

Prevention:
Save previous TCCL
      -> set plugin TCCL within a short scope
      -> invoke plugin
      -> finally restore previous
      -> clean up ThreadLocal, callbacks, queued tasks,
         plugin threads/executors, and host references
~~~

**A single long-lived thread can retain the entire ClassLoader lifecycle of an old plugin simply from forgetting to restore TCCL.** However, fixing TCCL only addresses one retention path; reliable unloading requires thoroughly managing workers, tasks, registries, and resources, as well as verifying GC roots across multiple redeploy cycles.

### References

- Thread API Java SE 17: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
- ClassLoader API Java SE 17: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- ExecutorService API Java SE 17: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- ServiceLoader API Java SE 17: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- JLS §12.7 Unloading of Classes and Interfaces: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.7
- IBM — Class loader memory leaks in enterprise Java: https://www.ibm.com/docs/en/was-nd/8.5.5?topic=cmlp-memory-leaks-in-java-platform-enterprise-edition-applications
