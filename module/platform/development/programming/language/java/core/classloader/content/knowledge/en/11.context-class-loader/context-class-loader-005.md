# Passing and Inheriting the Context Class Loader When Creating Threads

> **Java Core → ClassLoader → Context Class Loader.** This lesson explains how the **thread context class loader (TCCL)** is inherited when creating a thread, how to set and restore the loader, the difference between creating a new thread and running a task in a thread pool, and considerations for virtual threads. The standalone examples use Java 17+; the virtual threads section requires Java 21+.

## 1. What Is a Context Class Loader?

Each `Thread` object has a **context class loader** that can be read and updated:

~~~java
Thread thread = Thread.currentThread();
ClassLoader context = thread.getContextClassLoader();
thread.setContextClassLoader(context);
~~~

Common purpose: library/framework code loaded by a parent-level loader can use the context loader to find classes, resources, or service providers belonging to the application/plugin calling it. This is a way to **invert the lookup direction** compared to always relying solely on the library's own defining loader.

Distinguishing three concepts:

| Term | Meaning | Automatically the same as TCCL? |
| --- | --- | --- |
| **Defining class loader** | The loader that directly defines the runtime class; a component of class identity | No |
| **Initiating class loader** | The loader that the JVM records as having initiated a successful load of the class, possibly via delegation | No |
| **Thread context class loader (TCCL)** | A `ClassLoader` reference attached to each `Thread` that code can choose to use when looking up classes/resources | No |

`Thread.currentThread().getContextClassLoader()` does not necessarily equal `SomeLibrary.class.getClassLoader()`, `ClassLoader.getSystemClassLoader()`, or the loader that created the `Runnable`. A `null` value from this API means falling back to the system class loader (or the bootstrap loader if there is no system loader) according to the `Thread` documentation; do not arbitrarily infer that `null` means an error.

**Important:** The TCCL **does not move** a class to a new defining loader. It is only a reference that APIs which actively use the TCCL can query. `SomeClass.class` and method bytecode resolution do not change loaders just because you set the TCCL.

## 2. Default Rule: Inheritance at **Thread Creation** Time

For standard public `Thread` constructors, **the new thread inherits the context class loader from the thread that creates it**. This is a special case of the inheritance mechanism for initial values of inheritable-thread-locals described in the `Thread` documentation.

~~~text
Thread A running
    TCCL = loaderA
          |
          | new Thread(task)  <-- captures state at creation time
          v
Thread B created
    Initial TCCL = loaderA
          |
          | B.start()          <-- only schedules execution; does not re-fetch TCCL
          v
Thread B runs task under initial TCCL
~~~

The key point is **when `new Thread(...)` occurs**, not when `start()` is called or when the scheduler actually runs the thread.

If thread A changes its TCCL **after** creating B but **before** starting B, B does not automatically change along with A. If A changes it again later, B does not automatically update either. Threads store their own TCCL references separately and do not share a single TCCL variable.

### 2.1. Example Verifying Creation-Time Inheritance, Java 17+

File **TcclAtCreation.java**:

~~~java
public class TcclAtCreation {
    public static void main(String[] args)
            throws InterruptedException {
        Thread parent = Thread.currentThread();
        ClassLoader original = parent.getContextClassLoader();
        ClassLoader marker = new ClassLoader(original) { };

        try {
            parent.setContextClassLoader(marker);
            Thread child = new Thread(() -> {
                System.out.println("child inherited marker="
                    + (Thread.currentThread()
                        .getContextClassLoader() == marker));
            });

            // Change on the parent thread AFTER child has been created.
            parent.setContextClassLoader(original);
            System.out.println("parent restored="
                + (parent.getContextClassLoader() == original));

            child.start();
            child.join();
        } finally {
            parent.setContextClassLoader(original);
        }
    }
}
~~~

~~~bash
javac --release 17 TcclAtCreation.java
java -cp . TcclAtCreation
~~~

Stdout:

~~~text
parent restored=true
child inherited marker=true
~~~

Explanation: creating `child` under the `marker` TCCL captured this value into the child's initial context. Restoring the parent's loader before `start()` does not change the TCCL that the child already has. `join()` makes the program wait for `child` to finish so the output has a consistent order.

`new ClassLoader(original) { }` only creates a loader **as a marker** to compare identity; it does not actually load classes from a plugin JAR. A demonstration of passing a loader reference should not be confused with an experiment in defining new classes.

### 2.2. Explicitly Assigning a TCCL to the Target Thread

Instead of relying on creation time, you can set it on the new thread object before starting:

~~~java
Thread worker = new Thread(task);
worker.setContextClassLoader(pluginLoader);
worker.start();
~~~

This is a snippet that requires `task` and `pluginLoader` variables in an appropriate scope. It illustrates a **clearer policy** for applications that need a consistent loader. If the worker is already running, changing the TCCL mid-execution can cause a race around when the library inside calls `getContextClassLoader()`; configuring it before `start()` is usually easier to control.

### 2.3. Differences from Regular `ThreadLocal`

- A regular `ThreadLocal<T>` holds a separate value per thread and **is not propagated by default** to a child.
- `InheritableThreadLocal<T>` copies/creates initial child values at **thread construction**, and does not dynamically propagate subsequent updates.
- **TCCL** is handled by `Thread` as a special inheritable thread-local value; understanding the inheritance timing rule helps avoid confusing it with a regular ThreadLocal.
- Inheriting the TCCL **does not mean copying the entire state of the classloader**. Two threads can hold the same loader reference, sharing the classes already defined by that loader.

**Note:** A ClassLoader is an object reference; “passing” the TCCL does not clone bytecode, does not create a new loader, and does not change Java module access permissions.

## 3. In What Cases Is the TCCL Used?

Many libraries intentionally use the TCCL to locate resources/SPI/providers. For example:

~~~java
ClassLoader loader =
        Thread.currentThread().getContextClassLoader();

Class<?> providerClass =
        loader.loadClass("example.plugin.Provider");
~~~

This is a **snippet** and will throw a `NullPointerException` if `loader` is actually null and an instance method is called directly on it; the application needs to decide on a fallback before using it. The binary name is illustrative and is not a built-in class in Java SE.

### 3.1. `ServiceLoader`

The `ServiceLoader.load(Service.class)` API in typical contexts uses **the current thread's TCCL** as the class loader to search for providers. Overloaded APIs such as `ServiceLoader.load(Service.class, explicitLoader)` allow explicitly choosing a loader, and JPMS also provides `ServiceLoader.load(layer, Service.class)` when working with a module layer.

If the host and plugin have two loaders:

- The `Service` contract/interface should be shared with the **same runtime class identity**; if each loader independently defines an interface with the same name, the provider may be rejected due to a type mismatch.
- The TCCL can help a parent-level library locate a plugin implementation according to the caller context.
- Packaging the provider into the JAR or configuring `META-INF/services`/module `provides` must be correct; the TCCL will not make a missing provider appear.
- If a thread in a pool retains plugin A's TCCL while processing a request for plugin B, provider discovery may look at the wrong plugin.

### 3.2. Resource Lookup

~~~java
ClassLoader tccl =
        Thread.currentThread().getContextClassLoader();
var url = tccl == null
        ? ClassLoader.getSystemResource("config/app.properties")
        : tccl.getResource("config/app.properties");
~~~

This is an illustrative snippet, not a standalone Java file. `getResource` uses a logical resource name that typically uses `/` separators. Resources in named modules are also subject to module encapsulation; the fact that the TCCL can see a class does not guarantee that every resource is accessible. A resource returning `null` may be due to non-existence or module/loader permissions, not necessarily an incorrect physical path.

### 3.3. Do Not Confuse TCCL with Java Module Access

Changing the TCCL **does not automatically grant** `requires`/`exports`/`opens` to a named module. A class may be found by a loader, yet the caller is still constrained by accessibility rules or class identity constraints. For plugin isolation, the loader boundary, module graph, and shared API must all be designed together.

## 4. Thread Pool: A New Task Does Not Mean a New Thread

An executor typically reuses pre-existing workers. If a caller switches its TCCL to plugin A and then submits a task, the worker may still hold an old context (base or plugin B). `submit()` has no contract to re-capture the TCCL for each task; even if a worker was created while the caller held plugin A, it may continue holding A for subsequent tasks.

```text
creator TCCL=A → new Thread(worker) → worker initially has TCCL=A
creator changes TCCL=B → executor.submit(job) → worker may still hold A
```

Changing a worker's TCCL and forgetting to restore it also causes context contamination between tasks and prolongs references to the plugin. To genuinely propagate context, capture the loader at the submit boundary according to task ownership, and then apply it inside the worker using the wrapper in Section 5; or use an API that explicitly takes a `ClassLoader`. The lesson “Thread pool and context that may differ from the submitting thread” has a Java 17 program verifying plain/wrapped/restored tasks.

## 5. How to Pass the TCCL into a Task and Restore It Safely

When work must run via an executor with reused workers, **capture the desired loader at submission time** and execute the task under that loader with a wrapper. Here is an example of a standard helper for Java 17+:

~~~java
import java.util.concurrent.Callable;

public final class ContextTasks {
    private ContextTasks() {}

    public static <T> Callable<T> withLoader(
            ClassLoader desired, Callable<T> operation) {
        return () -> {
            Thread current = Thread.currentThread();
            ClassLoader previous = current.getContextClassLoader();
            try {
                current.setContextClassLoader(desired);
                return operation.call();
            } finally {
                current.setContextClassLoader(previous);
            }
        };
    }
}
~~~

The `ContextTasks.java` file compiles standalone. Usage from application code that already has an `ExecutorService executor`:

~~~java
ClassLoader desired = Thread.currentThread().getContextClassLoader();

var result = executor.submit(ContextTasks.withLoader(desired, () -> {
    ClassLoader actual = Thread.currentThread().getContextClassLoader();
    return actual == desired;
}));
System.out.println(result.get());
~~~

This is a **caller snippet**, requiring an `executor` variable and appropriate `Exception` handling. When the task executes, the wrapper sets the TCCL and always restores the previous loader in `finally`. Even if `operation.call()` throws an exception, the worker is not left behind with the desired context.

### 5.1. `Runnable` Variant

~~~java
static Runnable withLoader(ClassLoader desired, Runnable operation) {
    return () -> {
        Thread worker = Thread.currentThread();
        ClassLoader old = worker.getContextClassLoader();
        try {
            worker.setContextClassLoader(desired);
            operation.run();
        } finally {
            worker.setContextClassLoader(old);
        }
    };
}
~~~

This is an **illustrative method** that needs to be placed in an appropriate class. Create the wrapper at the task-receiving site/framework boundary so the policy is consistent. If the system has a context propagation API already supported by the framework, prefer using that shared mechanism to avoid missing nested tasks and other contexts such as tracing, tenant, and security.

**Avoid capturing the wrong loader:** `getContextClassLoader()` at the submitter may already have been polluted by another task. In a plugin system, determine the loader from the explicit **plugin/request owner** and restore the caller as well if the caller itself has also changed it.

### 5.2. ThreadFactory Setting a Fixed TCCL for Workers

If every task in a pool belongs to **one plugin**, you can choose the worker's TCCL directly in the ThreadFactory:

~~~java
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;

class PluginFactoryExample {
    static ThreadFactory factory(ClassLoader pluginLoader) {
        ThreadFactory base = Executors.defaultThreadFactory();
        return command -> {
            Thread thread = base.newThread(command);
            thread.setContextClassLoader(pluginLoader);
            return thread;
        };
    }
}
~~~

The snippet is a standalone Java class for creating a factory; it has no `main`. `Executors.newFixedThreadPool(2, factory(pluginLoader))` can be used when the loader shares the lifetime of the pool. However, for a pool shared across multiple plugins, **do not permanently attach one plugin's loader to all tasks**; use a wrapper with per-task restoration or design clearly partitioned pools.

When stopping a plugin, you need to shut down the pool/workers, cancel callbacks, and clear references; an active worker whose TCCL points to pluginLoader can keep the old plugin in memory.

## 6. Virtual Threads (JDK 21+) and Inheritance

Since Java 21, virtual threads are officially supported. The `Thread.ofVirtual()`/`Thread.ofPlatform()` builder has the method:

~~~java
inheritInheritableThreadLocals(boolean inherit)
~~~

According to the API, the default is typically **inherit=true**, and the TCCL is one of the inherited context values at **thread creation time**. Inheritance can be explicitly disabled:

~~~java
Thread child = Thread.ofVirtual()
    .inheritInheritableThreadLocals(false)
    .unstarted(task);
~~~

This is a snippet that requires a `task` variable. When choosing false, do not rely on the TCCL automatically equaling the parent's loader; if a deterministic policy is needed, explicitly set the TCCL or wrap the task.

### 6.1. Example of Virtual Thread Inheriting TCCL (Java 21+)

File **VirtualTccl.java**:

~~~java
public class VirtualTccl {
    public static void main(String[] args) throws InterruptedException {
        Thread creator = Thread.currentThread();
        ClassLoader saved = creator.getContextClassLoader();
        ClassLoader marker = new ClassLoader(saved) { };

        try {
            creator.setContextClassLoader(marker);
            Thread child = Thread.ofVirtual().unstarted(() ->
                System.out.println("virtualInherited=" +
                    (Thread.currentThread()
                        .getContextClassLoader() == marker)));

            creator.setContextClassLoader(saved);
            child.start();
            child.join();
        } finally {
            creator.setContextClassLoader(saved);
        }
    }
}
~~~

~~~bash
javac --release 21 VirtualTccl.java
java -cp . VirtualTccl
~~~

Stdout:

~~~text
virtualInherited=true
~~~

Similar to a platform thread, a virtual thread **does not take its TCCL from the carrier thread** each time it is mounted onto a carrier by the scheduler. `Thread.currentThread()` inside the task returns the virtual thread, so the TCCL belongs to the virtual thread. If the carrier changes or the virtual thread unmounts and then remounts, the virtual thread's context class loader does not become the carrier's TCCL because of that.

For tasks run via `Executors.newVirtualThreadPerTaskExecutor()`, each task gets a new virtual thread, yet the inheritance/capture policy should still be explicit. Virtual threads help avoid reusing the same thread across tasks, but do not eliminate all risks of retaining a loader when a task lives too long or when other async boundaries use pools.

## 7. When Should You Not Inherit by Default?

In some multi-tenant systems, plugin sandboxes, extension runtimes, or long-lived background jobs, inheriting the TCCL from the creator may be inappropriate because:

- The creator may be handling a specific plugin while the background thread is intended to serve the entire system.
- You do not want the worker to hold a strong reference to the plugin loader after plugin unload.
- You want the worker to see only host/shared APIs or a specific module layer.
- You need to avoid “context leakage” across requests in pools and async pipelines.

How to handle it depends on the design:

1. When creating a worker, explicitly set the TCCL in the ThreadFactory; use the **host loader** if the worker belongs to the host.
2. When running a callback/plugin operation, wrap it with the desired loader and restore in `finally`.
3. With a suitable JDK Thread.Builder, consider `inheritInheritableThreadLocals(false)` and then set the TCCL according to the defined policy.
4. Do not pass a `ClassLoader` solely to use as a security access-control mechanism: the TCCL does not replace Java access checks, module rules, or verified isolation.
5. When unloading a plugin, shut down workers, unregister callbacks/listeners, release caches and class/loader references; inspect thread dumps if the loader is still retained.

**Specifically:** `setContextClassLoader(null)` has a clear API meaning (system loader or fallback), yet it does not guarantee that every library handles null consistently when it directly calls `getContextClassLoader().loadClass(...)`; libraries need to handle null intentionally.

## 8. Common Issues and How to Diagnose Them

| Symptom | Possible Cause | How to Check/Fix |
| --- | --- | --- |
| Child thread sees old loader even though parent changed it before start | Inheritance happens at construction | Set TCCL before `new Thread` or set it on child |
| Executor task does not see submitter's loader | Worker was created earlier or reused | Wrap task or use a ThreadFactory policy |
| Task B finds plugin A's provider | Task A forgot to restore | Use `try/finally` in every context switch |
| Plugin hot reload fails to unload class metadata | Worker/ThreadLocal/TCCL retains old loader | Shut down worker and clean up references |
| `ClassNotFoundException` in ServiceLoader/resource lookup | Wrong TCCL or missing service config | Verify TCCL, SPI metadata, module layer |
| Cast error despite classes having the same name | Two different defining loaders | Check class identity; share host interface |
| Named module still blocked from access after setting TCCL | TCCL does not modify readability/exports/opens | Inspect JPMS graph |
| Virtual thread has a different TCCL than expected | Builder inheritance setting or capture timing | Check builder/factory and set explicitly |

### Minimal Logging

~~~java
Thread current = Thread.currentThread();
ClassLoader tccl = current.getContextClassLoader();

System.out.println("thread=" + current.getName());
System.out.println("TCCL=" + tccl);
System.out.println("definingLoader="
    + getClass().getClassLoader());
~~~

This is a **snippet inside an instance method**; when used in a static context, replace `getClass()` with an appropriate class literal. `ClassLoader.toString()` is diagnostic, not a stable ID or proof that two loaders loaded the same bytecode. When needed, also inspect `clazz.getModule()`, the runtime jar/version, and context propagation boundaries.

## 9. Self-Check Questions

1. When is the TCCL of a child `new Thread(...)` captured? **When the Thread object is created**, before `start()`.
2. If the parent changes its TCCL after creating the child, does the child automatically change? **No**.
3. Are a class's TCCL and defining loader always the same? **No**.
4. Does an executor that reuses workers automatically receive the caller's TCCL on each `submit`? **No**.
5. Why is `finally` mandatory when a task wrapper changes the TCCL? **So the worker does not retain the previous task's context when an exception occurs**.
6. Is the TCCL inherited like any regular ThreadLocal? **No**, it is described as a special inheritable thread-local.
7. Does a thread having no TCCL and returning null mean classloading is impossible? **No**, the API has a fallback rule.
8. Does setting the TCCL allow module A to read an unexported package of B? **No**.
9. Does a virtual thread take the TCCL from its carrier each time it is scheduled? **No**, the TCCL belongs to the virtual Thread object.
10. What should you use if you want a thread not to inherit inherited context with the JDK 21 builder? **`inheritInheritableThreadLocals(false)`**.
11. A hot-reloaded plugin fails to unload even after closing its URLClassLoader: why? **A thread/pool may be holding a strong reference via the TCCL**.
12. In which loader should the plugin interface be placed when using ServiceLoader across host/plugin? **In a shared defining loader to avoid two runtime types with the same name**.

## 10. Authoritative References

1. [Thread — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html): `getContextClassLoader`, `setContextClassLoader`, and inheritance rules at thread creation.
2. [Thread.Builder — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.Builder.html): `inheritInheritableThreadLocals`, platform/virtual thread builders.
3. [InheritableThreadLocal — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/InheritableThreadLocal.html): inherited initial values.
4. [Executors — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Executors.html): thread pools, ThreadFactory, virtual thread-per-task.
5. [ServiceLoader — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.html): loader selection/provider discovery.
6. [ClassLoader — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): defining loader, resource lookup, delegation, and module encapsulation.

**Key takeaway:** `new Thread` normally inherits the TCCL **at creation time**, thread pools reuse the **worker's** context, and virtual threads follow the inheritance policy of their builder/factory. For async code and plugin systems, determine the desired loader, pass it into the execution boundary, and always **restore it in `finally`**.
