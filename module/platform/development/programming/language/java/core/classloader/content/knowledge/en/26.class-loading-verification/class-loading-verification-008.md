# Verifying the Loader Closure, Plugin Shutdown, and Reference Release Lifecycle

## 1. Goal: Proving Proper Teardown, Not Just Calling close()

In a Java application with plugins or hot redeploy, a proper lifecycle typically looks like:

~~~text
Create ClassLoader for the plugin
           |
           v
Load class / create plugin instance
           |
           v
Register listener, task, scheduler, threads, resources
           |
           v
Plugin running
           |
           v
STOPPING: block new tasks and callbacks
           |
           v
Remove registrations, stop workers, close resources
           |
           v
Close URLClassLoader if the plugin owns it
           |
           v
Drop strong references from host/plugin
           |
           v
Loader may become eligible for GC collection
           |
           v
JVM may unload classes at a later time
~~~

The following three events are **distinct** and must be verified separately:

1. **The plugin has stopped functionally**: it accepts no further callbacks/tasks, executors are no longer running, and resources owned by the plugin have been closed.
2. **The loader has been closed**: for example, **URLClassLoader.close()** releases JAR/file handles opened by the loader and that loader is no longer used to look up *new classes/resources* of its own.
3. **No strong references remain retaining the loader**: host registries, threads, thread context class loader (TCCL), ThreadLocal, instances, Class objects, Futures, and caches no longer retain the old version.

**Closing a loader does not mean the JVM has unloaded its classes.** A loader being eligible for GC collection is a necessary condition for unloading ordinary classes defined by that loader; the GC/unloading process may occur later or may not occur during the observation window. This lesson focuses on **evidence-based verification**, rather than claiming that "calling System.gc() is a PASS".

### Learning Outcomes

After this lesson, you will know how to:

- Properly define the **STARTING/RUNNING/STOPPING/STOPPED/CLOSED/RELEASED** states.
- Build a test for **URLClassLoader.close()** and understand what still works after closing.
- Create a small plugin with a **listener registered on the host** and a **dedicated ExecutorService**, then perform deterministic teardown.
- Demonstrate that a shared thread pool can retain an old loader via **TCCL**; restore it properly using **try/finally**.
- Use **WeakReference/ReferenceQueue** as a diagnostic probe without creating flaky GC tests.
- Inspect **Path to GC Roots**, threads, queued tasks, and class loading/unloading metrics.
- Distinguish **sufficient conditions to report STOPPED** from **GC observation**.
- Design negative tests and run repeated checks across multiple reloads.

## 2. What Does URLClassLoader.close() Actually Do?

According to the Java SE 17 Javadoc for **java.net.URLClassLoader**:

- **close()** closes the loader so that it can no longer find/load **new classes or resources defined by this loader itself**.
- Classes/resources previously found/loaded by the loader **remain accessible**.
- Classes/resources defined by **parent loaders** can still be used via delegation.
- For JAR/file URLs, it attempts to close the loader's opened files.
- If one thread is loading a class while another thread calls close, **the outcome of that concurrent load is undefined**.
- If closed multiple times, subsequent calls on an already-closed loader have no further effect.
- close() can throw **IOException**, because closing file handles can fail.

Therefore, you cannot use:

~~~java
loader.close();
~~~

to replace all the operations of **stopping the plugin**, **canceling tasks**, **unregistering callbacks**, **clearing ThreadLocal**, **releasing references**, or **class unloading**. It is only one step in the closing cycle.

### 2.1 Four Properties to Separate

| Verification Item | Method | Appropriate Conclusion |
| --- | --- | --- |
| Are already-loaded classes still usable after close? | Keep an instance/Class before close, then invoke a method after close. | Closing does not invalidate existing instances/Class objects. |
| Can new classes present only in the JAR still be loaded after close? | Attempt to load a class not loaded before close and catch ClassNotFoundException. | The loader has stopped looking up new classes of its own. |
| Are parent classes still available? | loader.loadClass("java.lang.String"). | Parent/bootstrap delegation still works. |
| Have file/JAR handles been closed? | Record that close() succeeded and verify environment-appropriate file operations. | Resource handles owned by URLClassLoader have been handled; do not infer GC/unloading. |

**Do not use the fact that already-loaded classes still run after close as evidence that close failed.** That is API-specified behavior.

### 2.2 Who Owns the URLClassLoader?

- The **host/container** typically creates and owns the loader for a deployment.
- The **plugin** owns the resources/tasks/listeners that it creates itself.
- The host only calls **loader.close()** after the plugin has stopped cooperatively and in-flight work has been drained/canceled according to policy.
- Do not close a loader that is shared by multiple plugins that are still active.
- Do not close the **system/application loader** as if it were a plugin loader that you own.
- A custom ClassLoader other than URLClassLoader may **not have close()** and may not be AutoCloseable.

## 3. A Testable Teardown State Machine

A plugin manager should define clear states:

~~~text
NEW
 |
 v
STARTING -> RUNNING
             |
             v
          STOPPING
             |
             +-- block new submissions/callbacks
             +-- unregister listeners and schedulers
             +-- await/cancel running tasks
             +-- close sockets, streams, files, sessions
             +-- clean up TCCL and ThreadLocal on owner threads
             |
             v
           STOPPED
             |
             +-- URLClassLoader.close()
             |
             v
           CLOSED
             |
             +-- remove references from registries/caches/futures
             +-- drop remaining references held by the host
             |
             v
       RELEASED / GC-ELIGIBLE (reachability assessment only)
             |
             v
       Observed unload/GC (timing not guaranteed)
~~~

**STOPPED is not equal to RELEASED.** You may have stopped every task while a static map in the host still retains the plugin instance. Conversely, dropping the reference from the registry while workers are still executing plugin code does not mean teardown is safe.

**GC-ELIGIBLE is not a state the JVM guarantees to report immediately.** It is a design/analysis state: you have severed all strong reference paths managed within the system and no plugin work remains running. A heap analyzer/ReferenceQueue can provide supporting evidence, but no universal API guarantees an immediate answer that all classes have been unloaded.

## 4. Designing PASS/FAIL Criteria by Level

| Level | Question | Reliable Way to PASS |
| --- | --- | --- |
| **Functional stop** | Has the plugin stopped processing new requests/events? | Block intake, unregister callbacks; verify zero active registrations. |
| **Thread shutdown** | Have the plugin's executors/workers terminated? | Call shutdown or shutdownNow as appropriate; awaitTermination succeeds and threads have stopped. |
| **Context cleanup** | Does the host worker still carry the plugin TCCL after the task? | Verify that context is restored to the previous ClassLoader on the worker. |
| **Resource cleanup** | Have streams/sockets/handles been closed? | Use close or try-with-resources; verify state/appropriate I/O checks. |
| **Loader close** | Has the URLClassLoader been closed? | close succeeds; it is not reused to load new classes defined by it. |
| **Reference cleanup** | Does the host still have callbacks, queues, caches, Futures, or Class<?> retaining the loader? | Verify owner registries are empty; heap Path to GC Roots no longer has expected retention paths. |
| **GC observation** | Is the weak ref cleared, and do class unload events/metrics appear? | Conditional supporting evidence; not required for a deterministic teardown unit test to PASS. |

**Avoid a self-reported boolean "unloaded=true" just because the plugin has stopped.** Only state clearly which parts have been confirmed and which parts still depend on GC.

## 5. Java 17+ Example 1 — close() Does Not Remove Loaded Classes

This simple example separates **resource close** behavior from **Class identity and lifetime**.

### 5.1 Directory Structure

~~~text
project/
├── plugin-src/lab/plugin/
│   ├── Ready.java
│   └── Later.java
└── CloseDemo.java
~~~

**plugin-src/lab/plugin/Ready.java**:

~~~java
package lab.plugin;

public class Ready {
    public String text() {
        return "ready";
    }
}
~~~

**plugin-src/lab/plugin/Later.java**:

~~~java
package lab.plugin;

public class Later {
    public String text() {
        return "later";
    }
}
~~~

**CloseDemo.java**:

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class CloseDemo {
    public static void main(String[] args) throws Exception {
        URL jar = Path.of("plugin.jar").toUri().toURL();

        URLClassLoader loader = new URLClassLoader(
                new URL[]{jar},
                ClassLoader.getPlatformClassLoader());

        Class<?> ready = loader.loadClass("lab.plugin.Ready");
        Object object = ready.getConstructor().newInstance();

        System.out.println("before close = "
                + ready.getMethod("text").invoke(object));

        loader.close();

        System.out.println("after close = "
                + ready.getMethod("text").invoke(object));

        System.out.println("parent available = "
                + (loader.loadClass("java.lang.String")
                        == String.class));

        try {
            loader.loadClass("lab.plugin.Later");
            System.out.println("unexpected load");
        } catch (ClassNotFoundException expected) {
            System.out.println("new plugin class rejected = true");
        }
    }
}
~~~

From the **project** directory, using JDK 17+:

~~~bash
javac --release 17 -d plugin-out plugin-src/lab/plugin/Ready.java plugin-src/lab/plugin/Later.java
jar --create --file plugin.jar -C plugin-out .
javac --release 17 CloseDemo.java
java CloseDemo
~~~

On Windows PowerShell, the commands above also work because the classpath in this example contains only one root; there is **no need** to change the classpath separator.

**Actual compiled/executed stdout on OpenJDK 21:**

~~~text
before close = ready
after close = ready
parent available = true
new plugin class rejected = true
~~~

### 5.2 Why Is the Output Correct?

1. **Ready** is defined from plugin.jar and an instance is created **before close**.
2. The loader closes JAR/file handles via close.
3. The already-available **Ready.text()** method still runs. **close does not invalidate the object or the Class object**.
4. **java.lang.String** is defined by the bootstrap loader and can still be found via delegation.
5. **Later** was not loaded before close and only exists in plugin.jar. Since the URLClassLoader has been closed, lookup of the new class fails with **ClassNotFoundException**.

**Testing pitfall:** If you call **loader.loadClass("lab.plugin.Later")** before close, it is already cached/initiated and may still be accessible after close. You must choose **a class guaranteed not to have been loaded yet** to test the condition properly.

**Limitations:** The demo holds strong references in variables **loader**, **ready**, and **object** inside main while printing output. It does **not** verify class unloading. It only demonstrates close semantics and the usability of already-loaded classes/resources.

## 6. Java 17+ Example 2 — Stopping the Plugin, Removing Listeners, and Terminating the Executor

This example uses a shared **host API contract**, with the plugin implementation loaded by a dedicated URLClassLoader. The plugin owns:

- A **Runnable listener** registered in the host registry; it holds a reference to the plugin instance via a method reference.
- A **single-thread ExecutorService** created by the plugin, with its worker carrying the **plugin ClassLoader as its TCCL**.
- A **start → stop** protocol that closes retention paths on the host and waits for worker termination.

### 6.1 Project Structure

~~~text
lifecycle/
├── host-src/
│   ├── host/api/Plugin.java
│   ├── host/api/Registry.java
│   └── HostLifecycleDemo.java
└── plugin-src/
    └── plug/PluginImpl.java
~~~

Output directories:

~~~text
host-out/          class files of the host and shared API
plugin-out/        implementation class files of the plugin
plugin-impl.jar    plugin JAR, containing no copy of host.api.*
~~~

**Important:** The **host.api.Plugin** interface must be defined by the host loader. The plugin implementation uses the **same Class object** when casting. Do not package a separate copy of host.api.Plugin into plugin-impl.jar and child-first redefine the shared interface.

### 6.2 Shared Interface

**host-src/host/api/Plugin.java**:

~~~java
package host.api;

public interface Plugin {
    void start(Registry registry) throws Exception;
    boolean stop(Registry registry) throws Exception;
}
~~~

The **stop** method returns true when the plugin-owned worker has terminated within the timeout. This example simplifies the lifecycle; real applications typically have a status object containing error details, timeouts, and cleanup status for each resource.

### 6.3 Host Registry

**host-src/host/api/Registry.java**:

~~~java
package host.api;

import java.util.HashSet;
import java.util.Set;

public final class Registry {
    private final Set<Runnable> listeners = new HashSet<>();

    public void add(Runnable listener) {
        listeners.add(listener);
    }

    public void remove(Runnable listener) {
        listeners.remove(listener);
    }

    public int count() {
        return listeners.size();
    }
}
~~~

Registry is a simple synchronous example because all add/remove/count calls in the fixture come from a single host thread. In a multithreaded application, you need to add synchronization or a concurrent data structure and a protocol to prevent new callbacks after STOPPING.

**The registry can retain the plugin longer than intended:** Because the listener is an object created by the plugin and can capture the plugin instance, a host registry that keeps the listener becomes a **strong reference path** to the plugin and its defining loader.

### 6.4 Plugin Implementation

**plugin-src/plug/PluginImpl.java**:

~~~java
package plug;

import host.api.Plugin;
import host.api.Registry;
import java.util.concurrent.*;

public final class PluginImpl implements Plugin {
    private ExecutorService pool;
    private Runnable callback;

    private void onEvent() {
        // A plugin callback.
    }

    @Override
    public void start(Registry registry) throws Exception {
        callback = this::onEvent;
        registry.add(callback);

        pool = Executors.newSingleThreadExecutor(task -> {
            Thread worker = new Thread(task, "plugin-worker");
            worker.setContextClassLoader(
                    getClass().getClassLoader());
            return worker;
        });

        // Future.get(): ensures the worker has been created/started
        // before the host proceeds with testing stop.
        pool.submit(() -> {}).get();
    }

    @Override
    public boolean stop(Registry registry) throws Exception {
        registry.remove(callback);
        callback = null;

        pool.shutdownNow();
        boolean terminated = pool.awaitTermination(
                5, TimeUnit.SECONDS);

        pool = null;
        return terminated;
    }
}
~~~

### 6.5 Host Launcher

**host-src/HostLifecycleDemo.java**:

~~~java
import host.api.Plugin;
import host.api.Registry;
import java.lang.ref.WeakReference;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class HostLifecycleDemo {
    static WeakReference<ClassLoader> cycle(
            Registry registry) throws Exception {

        URL url = Path.of("plugin-impl.jar").toUri().toURL();

        try (URLClassLoader loader = new URLClassLoader(
                new URL[]{url},
                HostLifecycleDemo.class.getClassLoader())) {

            Class<?> pluginClass =
                    loader.loadClass("plug.PluginImpl");

            Plugin plugin = (Plugin) pluginClass
                    .getConstructor().newInstance();

            plugin.start(registry);

            System.out.println("listeners while active = "
                    + registry.count());

            System.out.println("worker terminated = "
                    + plugin.stop(registry));

            System.out.println("listeners after stop = "
                    + registry.count());

            // WeakReference does not keep the loader alive.
            return new WeakReference<>(loader);
        } // URLClassLoader.close() via try-with-resources.
    }

    public static void main(String[] args) throws Exception {
        Registry registry = new Registry();

        WeakReference<ClassLoader> probe = cycle(registry);

        System.out.println("cleanup checks passed = "
                + (registry.count() == 0));

        // Only confirms that we have the probe, does NOT assert that GC has run.
        System.out.println("probe installed = "
                + (probe != null));
    }
}
~~~

### 6.6 Compile/Run

From the **lifecycle** directory:

~~~bash
javac --release 17 -d host-out host-src/host/api/Plugin.java host-src/host/api/Registry.java host-src/HostLifecycleDemo.java
javac --release 17 -cp host-out -d plugin-out plugin-src/plug/PluginImpl.java
jar --create --file plugin-impl.jar -C plugin-out .
java -cp host-out HostLifecycleDemo
~~~

**Actual executed stdout on OpenJDK 21:**

~~~text
listeners while active = 1
worker terminated = true
listeners after stop = 0
cleanup checks passed = true
probe installed = true
~~~

### 6.7 Why Does This Example Verify Teardown?

**RUNNING step:**

- The plugin object is created from a Class defined by the new URLClassLoader.
- The host receives a Runnable callback as the method reference **this::onEvent**, so the registry holds a reference path to the plugin instance.
- The plugin-owned executor creates a thread whose worker TCCL points to the plugin loader.
- **submit(...).get()** ensures the worker has received the task; if you only call newSingleThreadExecutor without submitting, the worker might not be created yet.

**STOPPING/STOPPED step:**

- **registry.remove(callback)** severs the host listener reference.
- **callback = null** clears the plugin's internal reference.
- **shutdownNow()** signals shutdown via interrupt and cancels queued tasks as appropriate.
- **awaitTermination(5s)** confirms the worker terminated within the timeout. With the no-op task fixture, it returns true.
- **pool = null** drops the plugin's reference to the executor after stopping.
- **try-with-resources** closes the loader after stop returns.

**RELEASE CANDIDATE step:**

- The **cycle** method returns a **WeakReference** instead of returning a strong instance/Class/loader.
- After cycle returns, the local variables **plugin**, **pluginClass**, and **loader** of that frame are no longer used by the host launcher.
- The host registry still exists, but **count() = 0**, so no callbacks managed by the example remain.

This is **evidence that the retention paths created by the fixture have been cleaned up**. Do not infer that no strong references exist anywhere in the JVM or that the loader is unloaded immediately. WeakReference may still return non-null for some time because GC has not run yet or the runtime holds other references.

### 6.8 Additional Conditions Required for Production

The fixture prioritizes brevity and deterministically verifiable stdout. A real system requires:

- If **stop() throws an exception partway through**, registry, executor, and resource cleanup must still run in a finally block or compensating path.
- If **awaitTermination returns false**, do not drop the reference and report that the worker has died. Keep the **STOP_TIMEOUT/BLOCKED** state, capture a thread dump, and handle it according to policy.
- **InterruptedException** while the host waits for shutdown must restore the interrupt flag or follow the cancellation contract.
- **shutdownNow** does not force a thread to stop immediately; tasks must cooperate with interrupts.
- Must clean up **queued tasks/Futures/listeners** in both the host and the plugin, not just the variables present in the fixture.
- A plugin may also own **ScheduledExecutorService, ThreadLocal, sockets, file handles, JDBC connections, MBeans, drivers, timers, and JMX/logging hooks**.
- If **close()** throws an IOException, resource close must not be considered PASS by default; the JDK may attach multiple failures in suppressed exceptions.
- **Block new registrations before draining**, otherwise the plugin could add a new listener right after the host clears the registry.
- Do not call close on the loader while threads are loading classes. The URLClassLoader Javadoc states that the behavior of concurrent load and close is undefined.

## 7. Verifying TCCL: A Shared Host Worker Can Retain an Old Plugin

In a long-lived server environment, a thread's **Thread Context ClassLoader** can be a strong retention path:

~~~text
GC root -> live Host worker Thread
                 |
                 +-- contextClassLoader
                           |
                           v
                      OldPluginLoader
                           |
                           +-- related class metadata/objects
~~~

A plugin task may set the TCCL to the plugin's loader to use ServiceLoader, resource loading, or framework APIs. If the task returns without **restoring the previous context**, the host pool keeps the long-lived worker alive and continues retaining the old loader.

### 7.1 Bad Pattern

~~~java
Thread.currentThread()
        .setContextClassLoader(pluginLoader);
invokePlugin();
// If the task throws or returns early -> not restored.
~~~

This is a snippet assuming pluginLoader/invokePlugin already exist. It is **not a standalone program** and is an intentional anti-pattern.

A subsequent task may run with the **TCCL of the old plugin version**, causing both **memory retention** and **incorrect class/provider/resource lookup**.

### 7.2 Correct Pattern

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

**Always restore the exact previous value**; do not assume the system loader is right and do not default to setting null. Previous may be a host loader, a framework loader, or null.

If an API accepts a loader explicitly (for example, some ServiceLoader overloads), you can **pass the loader explicitly** to avoid mutating shared thread state when appropriate.

## 8. Java 17+ Example 3 — Host Pool TCCL Leak and Restoration with finally

Create the file **TcclPoolDemo.java** in the same directory containing plugin.jar from Example 1:

~~~java
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.concurrent.*;

public class TcclPoolDemo {
    public static void main(String[] args) throws Exception {
        ClassLoader host =
                TcclPoolDemo.class.getClassLoader();

        URLClassLoader plugin = new URLClassLoader(
                new java.net.URL[]{
                        Path.of("plugin.jar").toUri().toURL()
                },
                host);

        ExecutorService pool =
                Executors.newSingleThreadExecutor(job -> {
            Thread t = new Thread(job, "host-worker");
            t.setContextClassLoader(host);
            return t;
        });

        try {
            // Intentionally forget to restore in one task.
            pool.submit(() -> Thread.currentThread()
                    .setContextClassLoader(plugin)).get();

            System.out.println("after unsafe task = "
                    + pool.submit(() -> Thread.currentThread()
                        .getContextClassLoader() == plugin).get());

            // Clean up the old context on the SAME host worker.
            pool.submit(() -> Thread.currentThread()
                    .setContextClassLoader(host)).get();

            System.out.println("restored baseline = "
                    + pool.submit(() -> Thread.currentThread()
                        .getContextClassLoader() == host).get());

            try {
                pool.submit(() -> {
                    Thread thread = Thread.currentThread();
                    ClassLoader prior =
                            thread.getContextClassLoader();

                    thread.setContextClassLoader(plugin);
                    try {
                        throw new IllegalStateException(
                                "task failed");
                    } finally {
                        thread.setContextClassLoader(prior);
                    }
                }).get();
            } catch (ExecutionException expected) {
                System.out.println("error = "
                        + expected.getCause()
                                .getClass().getSimpleName());
            }

            System.out.println("after failed task = "
                    + pool.submit(() -> Thread.currentThread()
                        .getContextClassLoader() == host).get());
        } finally {
            pool.shutdown();

            if (!pool.awaitTermination(
                    5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                pool.awaitTermination(5, TimeUnit.SECONDS);
            }

            plugin.close();
        }

        System.out.println("pool terminated = "
                + pool.isTerminated());
    }
}
~~~

Compile and run (in the directory of plugin.jar from Example 1):

~~~bash
javac --release 17 TcclPoolDemo.java
java TcclPoolDemo
~~~

**Actual executed stdout on OpenJDK 21:**

~~~text
after unsafe task = true
restored baseline = true
error = IllegalStateException
after failed task = true
pool terminated = true
~~~

### 8.1 Explaining the Output

- **after unsafe task = true:** The single-thread executor reuses the worker; the first task set the TCCL to the plugin loader without restoring it. The next task sees the plugin context still present.
- **restored baseline = true:** A cleanup task running **on the same worker** restores the host loader. Do not arbitrarily change a busy worker's TCCL from another thread.
- **error = IllegalStateException:** The test task intentionally throws an error. When Future.get() detects the failure, it wraps the cause in an ExecutionException.
- **after failed task = true:** **finally** still executes to restore the TCCL when the task fails.
- **pool terminated = true:** Host shutdown and await in the fixture succeeded.

**Key point:** The example does not use GC as a PASS condition. It checks **a retention path directly**, so the result is deterministic under the proper runtime environment.

### 8.2 Inherited TCCL When Creating New Threads

According to the Thread API, a new thread typically **inherits the contextClassLoader of the thread that created it**, unless configured otherwise. If a plugin worker is created while the creating thread is carrying the plugin TCCL, the child thread may retain the plugin loader **even after the parent has restored it**.

Therefore:

- A host **ThreadFactory** for shared pools should set an appropriate baseline TCCL, rather than accidentally inheriting a plugin context.
- A plugin-owned thread may use the plugin TCCL throughout the plugin's lifecycle, but **must stop and be released** when the plugin stops.
- Do not rely on the thread name or daemon flag to conclude that the loader is not retained. A live daemon thread can still hold references in a running JVM.
- An executor may create its worker **when the first task is submitted**, not necessarily when the executor constructor is called.

## 9. ThreadLocal and Other Reference Paths

**TCCL is only one strong retention path**. In production, there may also be:

~~~text
Live Thread
    +-- contextClassLoader -> OldPluginLoader
    +-- ThreadLocalMap value -> PluginObject
    +-- Runnable/Future currently executing -> PluginObject

Host static Registry
    +-- callback/listener -> PluginObject
    +-- service cache -> Plugin Class
    +-- plugin metadata -> URLClassLoader

Scheduler / Executor queue
    +-- Delayed task -> Plugin Runnable
    +-- Future -> Callable / result / class from plugin
~~~

### 9.1 Cleaning Up ThreadLocal on the Owner Thread

~~~java
ThreadLocal<Object> local = new ThreadLocal<>();

try {
    local.set(pluginScopedValue);
    executePluginTask();
} finally {
    local.remove();
}
~~~

This is an illustrative snippet assuming pluginScopedValue and executePluginTask already exist.

**Restoring TCCL does not call ThreadLocal.remove().** Conversely, removing ThreadLocal does not clear TCCL. Both must be cleaned up if the scope uses both.

ThreadLocalMap has weak keys, but values can still be retained in a long-lived thread when the entry has not been cleared. No longer having a reference to the ThreadLocal key is **not** immediate proof that the value has been collected.

### 9.2 Commonly Forgotten Retention Sources

- **ScheduledFuture** of a periodic task, even after the plugin "is no longer doing anything".
- A host-managed **ExecutorService** still holding queued tasks submitted by the plugin.
- **CompletableFuture** chains or callbacks capturing plugin state.
- Global **Map/Set/caches** containing Class, Method, MethodHandle, or objects created by plugin classes.
- Logging handlers, metrics listeners, event bus registrations, MBeans/JMX, JDBC drivers, ShutdownHooks.
- Thread-created **TCCL inheritance** and custom ThreadFactory.
- ThreadLocal values on shared workers.
- Class<?> and instances **stored in static fields belonging to the host**.
- Resources opened outside URLClassLoader such as FileInputStream, ZipFile, Socket, and native libraries.

These retention sources **are not automatically closed just because URLClassLoader.close() returns**.

## 10. WeakReference/ReferenceQueue: Using Them Properly for Observation Without Turning GC into a Hard Assertion

One diagnostic tool is:

~~~java
WeakReference<ClassLoader> weak =
        new WeakReference<>(pluginLoader);
~~~

A WeakReference does not itself keep the referenced object alive, unlike a strong reference. However, **merely creating a weak reference while still holding a strong pluginLoader variable proves nothing**.

### 10.1 The Most Important Condition

You must place the process of **creating the loader + loading classes + instantiating the plugin + stopping + closing** inside a separate method and return only a **weak reference** after that frame exits; at the same time, the host must unregister all references it manages.

The pattern in Example 2:

~~~text
static WeakReference<ClassLoader> cycle(...) {
    URLClassLoader loader = new URLClassLoader(...);
    try {
        ... start ...
        ... stop/drain/unregister ...
        return new WeakReference<>(loader);
    } finally {
        loader.close();
    }
}

WeakReference<ClassLoader> probe = cycle(...);
~~~

This is pseudocode illustrating the structure; the complete runnable program in Section 6 uses try-with-resources.

**Purpose:** reduce the chance that local variables in the caller accidentally retain the loader while you check reachability.

### 10.2 ReferenceQueue for a One-Way Signal

If you want to receive a notification when GC processes the reference:

~~~java
ReferenceQueue<ClassLoader> queue =
        new ReferenceQueue<>();

WeakReference<ClassLoader> probe =
        new WeakReference<>(loader, queue);
~~~

The snippet above requires importing **java.lang.ref.ReferenceQueue/WeakReference** and assumes the loader variable already exists.

- When **probe is cleared/enqueued** by the GC mechanism, that is useful evidence that the referent is no longer held by the weak reference and that GC has processed it.
- **queue.poll() == null** does not prove that the loader is leaked; GC may not have processed or enqueued it yet.
- **probe.get() != null** does not prove there is an abnormal strong reference path; the JVM may simply not have collected the object yet.
- Even when the loader is collected, observing **class unloading** is still a separate JVM event that is not synchronized immediately with user code.
- ReferenceQueue does not carry exact metadata about which **GC root** was retaining the loader; if you observe retention, use a heap analyzer.

### 10.3 Why Not Write a Unit Test That "Calls System.gc and Asserts null"?

~~~java
System.gc();
assert weak.get() == null;
~~~

This is a **counterexample**: this check is unreliable.

**System.gc() is a request/hint**, with no timing guarantee that the loader will be collected at that moment. GC may not execute on request, may defer class unloading, or test/debugger/JIT code may still hold temporary references. Consequently, the test easily becomes **flaky** across JDK/JVM/CI environments.

If you need a stress/probe loop for observation, you can try multiple iterations with a finite timeout and print:

~~~text
OBSERVED: weak reference cleared
~~~

or:

~~~text
INCONCLUSIVE: not collected within observation window
~~~

These are **two alternative outcomes**, not fixed stdout. **INCONCLUSIVE does not mean FAILED** unless the test has controlled and clearly defined GC assumptions/conditions.

### 10.4 A Negative Control Helps Validate the Probe Properly

In a separate lab test:

1. Keep an **intentional strong reference** from the host registry to the plugin/loader.
2. Confirm via a registry check that the reference still exists.
3. Perform cleanup and drop the reference.
4. Use WeakReference/ReferenceQueue or a heap snapshot to observe.
5. If you only use a GC signal without measuring root paths, do not definitively claim the negative control is proof of an actual leak.

**The decisive factor is diagnosing the specific retention path**, not counting how many times System.gc is called.

## 11. Testing Repeated Reloads and Identifying Real Memory Leaks

A loader leak is usually clearest after multiple reloads:

~~~text
Deploy #1 -> Loader1 -> RUNNING -> STOP
Deploy #2 -> Loader2 -> RUNNING -> STOP
Deploy #3 -> Loader3 -> RUNNING -> STOP

If host registry/thread still retains:
GC roots -> Loader1, Loader2, Loader3 ...

If cleanup is correct:
references owned by the host to old loaders are dropped
-> loaders can be collected by GC later
~~~

### 11.1 A Sound Measurement Plan

1. **Warm-up baseline:** measure classloader counts/metaspace after host startup stabilizes.
2. **Deploy:** record module/plugin version, loader identity, loaded class count, and the number of callbacks/tasks.
3. **Run:** generate a representative workload, including async tasks, resources, ServiceLoader, and callbacks.
4. **Stop:** stop intake; cancel pending tasks; wait for running tasks to finish within the timeout.
5. **Close/release:** unregister; close resources; close loader; clear host refs.
6. **Observe:** measure after multiple cycles using JVM tools; use a heap dump if old loaders accumulate.
7. **Investigate GC roots:** find the **Reference path from a GC root to the old loader**, rather than just looking at a heap chart.
8. **Regression test:** add assertions specifically for the listener registry, executor termination, TCCL, and closure policies.

Do not conclude there is a memory leak solely because metaspace is high right after deploy: HotSpot may retain/commit memory and unload at an appropriate time. However, **a steadily increasing number of old plugin loaders that remain strongly reachable** along with specific paths through threads/caches is a signal worth investigating.

### 11.2 Meaningful Metrics and Their Limitations

| Observation | What It Tells You | What It Does Not Tell You |
| --- | --- | --- |
| **ClassLoadingMXBean.getLoadedClassCount()** | Number of classes currently loaded in the JVM according to the metric | Does not indicate which specific loader holds which classes. |
| **ClassLoadingMXBean.getUnloadedClassCount()** | Cumulative total of unloaded classes | Does not guarantee that the loader that just stopped has been unloaded. |
| **JFR class load/unload events** | JVM events when configured with appropriate collection settings | Does not necessarily identify the GC root causing retention. |
| **jcmd VM.classloader_stats** | Classloader/class metadata statistics, depending on JVM support | Does not itself indicate which callback/ThreadLocal is retaining the loader. |
| **Heap dump + MAT** | Path to GC Roots, dominator tree, retained objects | Snapshot depends on the capture timing and prior GC. |
| **Thread dump** | Worker threads, stack, blocking state | Not sufficient to prove all Java object retention paths. |
| **OS file handles** | Whether any JAR/file handles remain open | Not proof that classes have been unloaded. |

**Multiple perspectives should be used** because close, GC eligibility, class unloading, and OS resource handles are distinct state layers.

## 12. Diagnosing with jcmd, JFR, and Heap Dumps

On an appropriate HotSpot JDK, some commonly used commands are:

~~~bash
jcmd
jcmd <PID> help
jcmd <PID> VM.classloader_stats
jcmd <PID> GC.class_histogram
jcmd <PID> GC.heap_dump /path/to/heap.hprof
~~~

**<PID>** above is a process ID placeholder, not literal characters to type. Command names may vary by JDK/JVM, so run **jcmd <PID> help** before applying them.

**Operational warning:** A heap dump can be very large, cause pauses/I/O, and contain sensitive data (tokens, PII, business objects). Only capture one when authorized and with an appropriate retention/deletion policy.

### 12.1 Common GC Root Paths

If a live worker holds the TCCL:

~~~text
GC Root: Java Thread
   |
   +-- Thread.contextClassLoader
         |
         +-- URLClassLoader (old plugin)
~~~

If a host registry holds a callback:

~~~text
GC Root: host static field
   |
   +-- ListenerRegistry
         |
         +-- Runnable callback
             |
             +-- PluginImpl instance
                  |
                  +-- Class PluginImpl / defining loader
~~~

If an executor queue holds a task:

~~~text
GC Root: Host ExecutorService
   |
   +-- workQueue
         |
         +-- FutureTask / Runnable
              |
              +-- captured plugin object
                    |
                    +-- defining loader
~~~

**Multiple root paths can exist at the same time**. Fixing TCCL while forgetting the listener registry still retains the loader; fixing the listener while tasks remain in the queue is also not enough.

### 12.2 MAT/JFR Workflow

- Heap dump: search for instances of URLClassLoader/custom PluginLoader, especially old loader versions.
- Inspect **Incoming references** and **Path to GC Roots**; exclude weak/soft refs in the analysis to focus on relevant strong paths.
- Check retained size and the number of loader versions after multiple deploy cycles.
- Compare before/after cleanup under equivalent workloads.
- Use JFR/class unloading events if you want to know whether the JVM actually unloaded classes, but do not turn the absence of an event within a short window into a teardown failure.
- Use thread dumps to identify live/blocked plugin-owned threads and troubleshoot shutdown hangs.

### 12.3 Do Not Confuse close with File-Deletion Portability

**URLClassLoader.close()** helps close file/JAR handles opened by the loader, which is useful when replacing/deploying JARs, especially on operating systems that lock files. However, a process with **other file streams/JarFiles** opened directly outside the loader can still hold a handle; closing the loader does not close every resource outside it.

In addition, OS/file-system behavior varies; the ability to replace a file successfully does not prove the JVM has unloaded classes from the previous version.

## 13. Minimum Recommended Lifecycle for Production

A lifecycle manager can be expressed in pseudocode:

~~~java
// Structural pseudocode, not a standalone runnable class.
stopAcceptingNewWork(pluginId);

try {
    unregisterHostCallbacks(pluginId);
    cancelOrDrainQueuedTasks(pluginId);
    stopPluginOwnedExecutors(pluginId);
    awaitWorkersStopped(pluginId, timeout);

    closePluginOwnedStreamsSocketsAndResources(pluginId);
    verifyThreadLocalsAndTcclCleanup(pluginId);

    // Only when no active class/resource loading remains.
    pluginLoader.close();

    clearHostReferences(pluginId);
} finally {
    recordShutdownOutcome(pluginId);
}
~~~

**Do not treat this snippet as sufficient for every case:** it illustrates the conceptual ordering. A real implementation must include error-handling paths for each step, timeouts, idempotence, reentrancy, concurrent stop/start handling, an interrupt policy, and resource ownership.

### 13.1 Idempotent stop

Plugin.stop may be called twice due to retries or repeated shutdown signals. A robust lifecycle needs:

- No re-registration while STOPPING.
- Idempotent unregistration, or safe handling when the listener has already been removed.
- Shutting down the executor multiple times does not cause inconsistent state.
- Closing the loader multiple times does not cause further issues.
- Persist/report the state so the host does not mistake a timeout for STOPPED.

### 13.2 When stop Hangs

If a plugin thread blocks on I/O without responding to interrupts:

- **shutdownNow does not guarantee termination**.
- Do not use **Thread.stop()** to force termination because it is dangerous and can break invariants.
- Use I/O timeouts, cooperative cancel/callback protocols, socket closure to unblock, thread dumps, and an escalation policy.
- Do not close the loader while threads might still need to load new classes or resources; the Javadoc considers concurrent close/load undefined.
- When a safe state cannot be reached, report **STOP_TIMEOUT/BLOCKER**, and do not mark it as RELEASED.

## 14. Anti-Patterns That Commonly Cause Loader Leaks

### 14.1 Closing URLClassLoader Without Stopping the Plugin

~~~java
loader.close();
plugin.stop();
~~~

This order can close the source of classes/resources **while plugin tasks are still running**. If a task later needs an unloaded class or a new resource, it may fail. Quiesce/stop workers first, then close when ownership is clear.

### 14.2 Marking the Plugin STOPPED and Forgetting the Registry

~~~text
plugin.state = STOPPED
registry.listeners still contains plugin callback
~~~

The host still holds the plugin object, meaning the loader may not be collectible yet. Use symmetric register/unregister tied to the lifecycle.

### 14.3 Changing TCCL Without Restoring It

A host worker belonging to a long-lived thread pool will continue carrying the plugin loader after the task returns. Use try/finally on the worker; test a task **throwing an exception** as in Example 3.

### 14.4 Believing That Daemon Threads Do Not Hold References

A daemon thread is still a live Thread while the JVM is running and can still retain the plugin loader/TCCL/ThreadLocals. Daemon status only affects JVM exit rules; it does not turn references into weak references.

### 14.5 Calling System.gc() and Treating weak.get()!=null as FAIL

GC does not guarantee immediate collection. Such a test can be flaky across CI, different JVM flags, different GC algorithms, and debuggers.

### 14.6 Testing Only the Clean STOP Case

Lifecycle bugs commonly occur when:

- Plugin.start fails **after already registering a callback**.
- A running task throws an exception.
- Executor shutdown times out.
- Closing a stream throws IOException.
- Two threads call stop concurrently.
- A new callback arrives while unregistering.
- A worker spawns a child Thread that inherits the plugin TCCL.
- Repeated plugin hot reloads cause old instances to accumulate.

There must be negative tests for these failure paths, not just the happy path.

### 14.7 Keeping ClassLoader in Metrics/Test Harnesses

A test creates a list:

~~~java
static final java.util.List<ClassLoader> history =
        new java.util.ArrayList<>();
~~~

and appends each deploy's loader without removing it. That list becomes a **test-induced strong reference leak**. If you need statistics on loader lifecycles, store only string IDs, deployment timestamps, or appropriate WeakReferences.

### 14.8 Host Static Fields Retaining Class/Method/MethodHandle

Even after the plugin has stopped, a host reflection cache may retain a plugin Class. Since the runtime Class of an ordinary class is linked to its defining loader, these references can prevent unloading. Clear caches by plugin ID/version.

### 14.9 Inspecting Only the Heap and Forgetting Native/File Resources

It is possible to have no loader leak yet still have a file/socket/native leak; and conversely, a loader leak can exist even when OS handles are closed. Track both separately.

## 15. Automated Verification Checklist

### 15.1 Before stop

- [ ] The new loader defines the plugin class properly (not mistakenly a parent-defined class).
- [ ] The plugin API type comes from the appropriate shared loader.
- [ ] The plugin has registered listeners/tasks/schedulers with the expected count.
- [ ] The plugin-owned executor has created workers as actually needed.
- [ ] TCCL is used properly within the scope of work; the host worker baseline is saved.
- [ ] A clear deployment/plugin ID exists to trace references across reloads.

### 15.2 During STOPPING

- [ ] Block new callbacks/tasks before draining.
- [ ] Fully unregister listeners/subscriptions/metrics hooks.
- [ ] Cancel queued tasks and finish running tasks according to a cooperative policy.
- [ ] awaitTermination succeeds or reports timeout clearly, without faking PASS.
- [ ] Call ThreadLocal.remove() on the appropriate workers.
- [ ] Restore TCCL to the previous ClassLoader on shared host workers.
- [ ] Close plugin-owned streams/sockets/JDBC/JMX/resources.
- [ ] No thread is still executing plugin code when closing the loader.

### 15.3 After stop/close

- [ ] Close the deployment-owned URLClassLoader and record any IOException if thrown.
- [ ] Drop references from registries, caches, Futures, and metrics.
- [ ] Verify that the host registry count matches the baseline.
- [ ] Verify executor isTerminated/threads have ended.
- [ ] Verify that the host worker context no longer holds the old plugin loader.
- [ ] If a GC probe is present, report **OBSERVED/INCONCLUSIVE** based on actual results rather than asserting immediately.
- [ ] Have a heap dump/JFR plan if repeated reloads cause retained old loaders to grow.

This checklist is a **recommended verification contract**; not every item applies to every plugin. However, every component that a plugin **actually owns** must have symmetric cleanup.

## 16. A Test Matrix for Real-World Scenarios

| Test | Setup | Expected Outcome to Verify |
| --- | --- | --- |
| **Close loaded class** | Load Ready, create an instance, close the loader, call Ready.text. | The already-loaded instance still runs. |
| **Close new class** | Keep Later unloaded, close first, then request Later. | No new class can be looked up from the closed loader. |
| **Parent after close** | Close the plugin loader, then request String. | Parent/bootstrap classes remain usable. |
| **Listener unregister** | Plugin start registers a callback. | Host registry count returns to baseline after stop. |
| **Executor termination** | Plugin worker is started via submit. | awaitTermination succeeds or reports timeout. |
| **Unsafe TCCL negative** | Host worker runs a task that changes TCCL without restoring it. | Subsequent task sees the plugin TCCL still retained. |
| **finally on exception** | Plugin task throws after setting TCCL. | Host worker's TCCL returns to previous. |
| **ThreadLocal cleanup** | Task sets a plugin-sourced value on a shared worker. | Call remove() on the worker inside finally. |
| **Partial start failure** | start throws an error after registering. | Startup rollback removes listeners/stops workers. |
| **Repeated reload** | Deploy/stop 20-100 times in the lab. | Registries/threads match baseline; retention paths do not accumulate. |
| **GC probe** | Return WeakReference after cleanup and drop strong refs. | Observe GC if it happens; timeout is INCONCLUSIVE. |
| **Forced stalled task** | Task does not respond to interrupts (lab only). | Stop reports timeout; do not arbitrarily close/mark safe. |

**Do not hardcode a fixed number of GC runs or a universal collection timeout for all JVMs** in the test matrix. Verify deterministic cleanup first, and then use GC observations for supplemental analysis.

## 17. Knowledge Self-Check

**Question 1.** After calling URLClassLoader.close(), an instance of a previously loaded class still runs. Did close fail?

**Answer:** No. The Javadoc permits continued use of already-loaded classes/resources.

**Question 2.** Does Loader.close() shut down threads created by the plugin itself?

**Answer:** No. Threads/executors must be managed separately by the plugin/container, stopped/canceled, and awaited for termination.

**Question 3.** The plugin has unregistered its listener, yet a host worker still has contextClassLoader=oldPluginLoader. Can the loader still be retained?

**Answer:** Yes. A live Thread holds a strong reference through its TCCL.

**Question 4.** Why must the previous TCCL be restored inside finally?

**Answer:** Because a task can return early or throw; the host pool reuses the same worker after the task completes.

**Question 5.** If a new thread is created while its parent thread is carrying the plugin TCCL, and the parent later restores its TCCL, does the child automatically restore as well?

**Answer:** No. The child thread has its own context inherited at creation time, unless configured otherwise.

**Question 6.** awaitTermination returns false while the registry is empty. Should the plugin be reported as fully stopped?

**Answer:** No. The worker may still be running; the timeout must be handled and resource/thread ownership inspected.

**Question 7.** WeakReference.get() is not yet null after System.gc(). Does that prove a memory leak?

**Answer:** No. GC/unloading has no guarantee of occurring immediately; the outcome is INCONCLUSIVE without further evidence.

**Question 8.** Why can keeping a plugin's Class<?> in a host static Map prevent class unloading?

**Answer:** A Class object of an ordinary class is linked to its defining loader; a strong reference keeping the Class alive can keep the loader reachable.

**Question 9.** Does a successful close() mean every FileInputStream opened by the plugin is closed?

**Answer:** No. URLClassLoader closes resources that it owns; streams opened directly by the plugin must be closed separately.

**Question 10.** When should the loader be closed in the lifecycle sequence?

**Answer:** After blocking new work, stopping/draining threads, unregistering callbacks, closing resources, and ensuring no unsafe concurrent loading remains.

**Question 11.** Why do repeated reloads detect leaks more easily than a single stop?

**Answer:** Old loaders/callbacks/threads can accumulate across each cycle, making retention paths and metaspace pressure more visible.

**Question 12.** Which tools answer who is retaining an old ClassLoader?

**Answer:** Heap dumps with Path to GC Roots/dominator tree, combined with thread dumps, JFR/jcmd metrics, and code ownership.

## 18. Conclusion

~~~text
CLOSING LOADER != STOPPING PLUGIN != CLASS UNLOADING

STOP/QUIESCE:
  stop accepting work -> unregister -> drain/cancel tasks
  -> await worker termination -> cleanup TCCL/ThreadLocal
  -> close plugin resources

CLOSE:
  URLClassLoader.close()
  -> close handles owned by the loader
  -> do not look up new classes/resources of the loader
  -> old Class/instances remain usable

RELEASE:
  clear host registries/caches/Futures/Class references
  -> loader may no longer be strongly reachable
  -> GC may collect it at an unspecified time
  -> JVM may unload classes afterward

VERIFY:
  deterministic: state/tasks/threads/context/resources
  diagnostic: WeakReference, ReferenceQueue, JFR, jcmd, heap roots
~~~

**The best test suite does not force GC to conform to an arbitrary deadline.** It proves the cleanup steps under the application's control with deterministic assertions, while using heap/GC observations to investigate remaining references or subsequent unloading.

### References

- Java SE 17 **URLClassLoader.close()**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- Java SE 17 **ClassLoader API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 **Thread context ClassLoader**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
- Java SE 17 **ExecutorService shutdown/awaitTermination**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Java SE 17 **WeakReference / ReferenceQueue**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html
- Java SE 17 **ClassLoadingMXBean**: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html
- Java SE 17 **JLS §12.7 Class Unloading**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.7
- Java SE 17 **jcmd**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
