# Setting and Restoring the Thread Context Class Loader with try/finally at Call Boundaries

In a Java application supporting plugins, a call into a library or plugin sometimes needs to look up classes, service providers, or resources from the **plugin's ClassLoader**, rather than only from the host's classpath. The **Thread Context Class Loader (TCCL)** mechanism lets running code ask "what is the current thread's class loader context?" and use that loader for lookups.

The TCCL is very useful at the host → plugin → library boundary, yet it is **mutable state attached to a Thread**. If the host sets the TCCL to a plugin's loader and forgets to restore it, the next request on the same thread may see the wrong classes/resources, while the old class loader risks being kept alive longer than intended. The foundational rule is: **save the old loader, set the needed loader, perform the work inside `try`, and restore the old loader in `finally`**.

This lesson focuses on synchronous call boundaries, explains what actually uses the TCCL, provides a self-compilable Java 17+ example, covers common pitfalls, and shows how to apply the same principle to tasks running on a thread pool.

## 1. Distinguishing the TCCL from a Class's Defining ClassLoader

Java has multiple ways to choose a loader. Not every class-loading operation consults the TCCL:

| Access Path | Loader Involved | Meaning |
| --- | --- | --- |
| Thread.currentThread().getContextClassLoader() | Current context of the **running thread** | Libraries may use it to look up classes, providers, and resources |
| Thread.currentThread().setContextClassLoader(loader) | Replaces the TCCL of the **current thread** | Does not load classes itself; does not change which loader defined existing classes |
| ServiceLoader.load(MyService.class) | Per Java 17: uses the calling thread's TCCL | Providers in the plugin loader can be found when the TCCL points to the right loader |
| ServiceLoader.load(MyService.class, loader) | Uses the explicitly passed loader | Useful when only a single lookup needs the plugin loader, rather than the entire call chain |
| SomeType.class.getClassLoader() | Loader that defined SomeType | Does not change simply because the thread switches its TCCL |
| SomeType.class.getResourceAsStream("/path") | Looks up resource via SomeType's loader | Suitable when the resource belongs to the implementation itself |
| contextLoader.getResourceAsStream("path") | Looks up resource via the designated loader | Suitable when a framework loads plugin resources by context |

**Class identity** depends on the binary name **and the loader that defined the class**. Setting the TCCL does not turn a class loaded by the host into a class defined by the plugin loader. If the host and plugin exchange objects via an SPI interface, that interface must share a common class identity; typically the plugin loader has a parent that sees the SPI provided by the host.

The TCCL is neither a JVM-wide classpath nor a security sandbox. The TCCL only affects APIs that **actually consult the TCCL**; many other class/resource loading calls choose a loader in their own way. Do not assume every `ClassNotFoundException` will disappear once the TCCL is set.

## 2. Why Set at the Call Boundary and Restore Immediately?

Suppose the host has two plugins, A and B. Both are loaded by different `URLClassLoader` instances; both contain `config/defaults.properties`, but with different data. When the framework calls plugin A's code, an internal library uses `Thread.currentThread().getContextClassLoader()` to locate resources. If the TCCL still points to the host loader, the library may fail to see A's resource. If the host sets TCCL = `loaderA` and forgets to revert it, a subsequent call to B on the same thread may mistakenly find A's resource.

The proper pattern for **synchronous work on the same thread**:

~~~java
Thread current = Thread.currentThread();
ClassLoader previous = current.getContextClassLoader();
current.setContextClassLoader(pluginLoader);

try {
    // All calls requiring the plugin context reside inside this scope.
    invokePlugin();
} finally {
    current.setContextClassLoader(previous);
}
~~~

The snippet above is **illustrative call-boundary code**, assuming `pluginLoader` and `invokePlugin()` are already defined by the host. `finally` runs whether the `try` body returns normally, returns early, throws a checked exception, a `RuntimeException`, or an `Error` as long as the JVM continues normal execution. This is why restoration must not be placed only at the end of the success branch.

Execution order to preserve:

1. Capture the **exact previous loader**; the value may be `null`, and `null` must also be restored verbatim.
2. Set the plugin's loader right before the call requiring that context.
3. Keep all operations needing the TCCL, including lazy provider instantiation steps, inside the **`try` scope**.
4. In `finally`, restore the saved loader; do not default to replacing it with `ClassLoader.getSystemClassLoader()` or the host loader.
5. Close the loader and release plugin resources **only after** all calls using it have completed.

Note: `setContextClassLoader` can throw `SecurityException` in environments using a `SecurityManager` policy (especially relevant to Java 17 and legacy applications). If **setting** the loader fails before entering `try`, the host must treat that as a context-setup failure; do not proceed to invoke the plugin while assuming the TCCL was changed. The pattern above does not attempt to handle forcible process termination or cases where the JVM can no longer execute `finally`.

## 3. A Reusable Method for All Synchronous Calls

Instead of scattering set/restore pairs across many controllers and adapters, the host can provide a small helper. Using `Callable<T>` preserves the return value and allows checked exceptions to propagate:

~~~java
import java.util.concurrent.Callable;

static <T> T withContextClassLoader(ClassLoader next, Callable<T> action)
        throws Exception {
    Thread thread = Thread.currentThread();
    ClassLoader previous = thread.getContextClassLoader();
    thread.setContextClassLoader(next);
    try {
        return action.call();
    } finally {
        thread.setContextClassLoader(previous);
    }
}
~~~

This is a member method snippet for a class, not a standalone Java file. The lab in the next section puts this method into a compilable program.

Key properties:

- The helper runs **`action` on the same thread that called the helper**. It does not spawn a new thread or offload work to an `Executor`.
- If `action.call()` throws an exception, `finally` still restores the loader before the exception continues propagating to the caller.
- If an inner call also switches the TCCL using the standard pattern, the two `try/finally` layers **restore in reverse order** (LIFO).
- The helper **does not close** the `ClassLoader`. Ownership and lifecycle of `pluginLoader` belong separately to the plugin manager.
- If code inside `action` changes the TCCL on its own, `finally` still reverts the thread back to `previous`. Therefore, place the boundary cleanly around the call the host truly owns.

In Java, `finally` itself can throw an error, for example if the restore operation is denied. In that case, the restore error can suppress the original error; this is an environment/configuration fault to observe at the host management layer, not a condition to silently ignore.

## 4. Java 17+ Lab: Host Sees the Plugin After Switching TCCL

The experiment below builds **two independent artifacts**: `api.jar` on the host classpath and `hello-plugin.jar` loaded only into a `URLClassLoader` at runtime. Inside `hello-plugin.jar` are a `ServiceLoader` provider and a dedicated resource file. The host uses the exact `withContextClassLoader` method to invoke the provider, read the resource, and simulate an exception.

### 4.1. Directory Structure

From the root directory **lab/**:

~~~text
lab/
├── src/
│   ├── api/dev/example/spi/Greeter.java
│   ├── plugin/dev/example/impl/HelloGreeter.java
│   └── host/dev/example/host/Demo.java
├── resources/
│   ├── META-INF/services/dev.example.spi.Greeter
│   └── config/message.txt
├── build/             (created during compilation)
└── dist/              (created during packaging)
~~~

Only JDK 17 or later with `javac`, `jar`, and `java` is needed. Build commands are shown in bash/POSIX syntax; on Windows use a compatible bash shell or adapt directory creation and classpath separators for your shell.

### 4.2. SPI Interface in the Shared API

File **src/api/dev/example/spi/Greeter.java**:

~~~java
package dev.example.spi;

public interface Greeter {
    String greet(String name);
}
~~~

Both the host and the plugin reference this interface. When creating the `URLClassLoader`, the host chooses the loader that defined `Greeter` as the parent, so the provider sees the **same SPI type**, avoiding `ClassCastException` or `ServiceConfigurationError` caused by two copies of the SPI across different loaders.

### 4.3. Provider Supplied by the Plugin

File **src/plugin/dev/example/impl/HelloGreeter.java**:

~~~java
package dev.example.impl;

import dev.example.spi.Greeter;

public final class HelloGreeter implements Greeter {
    public HelloGreeter() {}

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

File **resources/META-INF/services/dev.example.spi.Greeter** contains exactly one line:

~~~text
dev.example.impl.HelloGreeter
~~~

File **resources/config/message.txt**:

~~~text
plugin-message
~~~

`META-INF/services` must be at the **root of the JAR**. The descriptor filename is the binary name of the SPI; its content is the binary name of the provider. The resource `config/message.txt` must also be an entry at the root of the JAR, without a `resources/` prefix. To make the TCCL effect clear, the host will read the resource using the loader retrieved from the thread rather than using a file path on disk.

### 4.4. Host Creates Plugin Loader, Sets TCCL, Invokes, and Restores

File **src/host/dev/example/host/Demo.java**:

~~~java
package dev.example.host;

import dev.example.spi.Greeter;
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ServiceLoader;
import java.util.concurrent.Callable;

public final class Demo {
    private static <T> T withContextClassLoader(
            ClassLoader next, Callable<T> action) throws Exception {
        Thread current = Thread.currentThread();
        ClassLoader previous = current.getContextClassLoader();
        current.setContextClassLoader(next);
        try {
            return action.call();
        } finally {
            current.setContextClassLoader(previous);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: Demo <path-to-plugin-jar>");
        }

        Thread current = Thread.currentThread();
        ClassLoader original = current.getContextClassLoader();
        System.out.println("before original: "
                + (current.getContextClassLoader() == original));

        long withoutPlugin = ServiceLoader.load(Greeter.class)
                .stream()
                .count();
        System.out.println("providers outside: " + withoutPlugin);

        URL pluginUrl = Path.of(args[0]).toAbsolutePath().toUri().toURL();
        try (URLClassLoader pluginLoader = new URLClassLoader(
                new URL[] {pluginUrl}, Greeter.class.getClassLoader())) {

            withContextClassLoader(pluginLoader, () -> {
                System.out.println("inside plugin loader: "
                        + (Thread.currentThread().getContextClassLoader()
                                == pluginLoader));

                int count = 0;
                for (Greeter provider : ServiceLoader.load(Greeter.class)) {
                    System.out.println("provider: " + provider.greet("Java"));
                    count++;
                }
                if (count != 1) {
                    throw new IllegalStateException(
                            "Expected one provider, got " + count);
                }

                ClassLoader context =
                        Thread.currentThread().getContextClassLoader();
                try (InputStream input =
                        context.getResourceAsStream("config/message.txt")) {
                    if (input == null) {
                        throw new IllegalStateException("Missing plugin resource");
                    }
                    String message = new String(
                            input.readAllBytes(), StandardCharsets.UTF_8).strip();
                    System.out.println("resource: " + message);
                }
                return null;
            });

            System.out.println("after success: "
                    + (current.getContextClassLoader() == original));

            try {
                withContextClassLoader(pluginLoader, () -> {
                    throw new IllegalArgumentException("simulated failure");
                });
            } catch (IllegalArgumentException expected) {
                System.out.println("caught: " + expected.getMessage());
            }

            System.out.println("after failure: "
                    + (current.getContextClassLoader() == original));
        }

        System.out.println("after close: "
                + (current.getContextClassLoader() == original));
    }
}
~~~

**Key points of the program:**

- The runtime classpath of the command **does not contain `hello-plugin.jar`**. The host cannot find the plugin provider through the default application loader; before switching the TCCL, `ServiceLoader` sees no plugin provider.
- `new URLClassLoader(..., Greeter.class.getClassLoader())` opens a class/resource search space containing the plugin JAR while delegating the SPI to the shared loader. Creating a plugin loader **does not automatically change the TCCL**.
- Once `withContextClassLoader` sets TCCL = `pluginLoader`, `ServiceLoader.load(Greeter.class)` uses the context loader and can locate the descriptor inside `hello-plugin.jar`.
- `ClassLoader context.getResourceAsStream("config/message.txt")` looks up the resource using that very loader from the TCCL. The path passed to `ClassLoader` has no leading `/`.
- Both normal return and `IllegalArgumentException` run `finally` to restore the exact `original` loader.
- `try-with-resources` closes `URLClassLoader` **after** the calls using it have finished and the TCCL has been restored.

Note that closing a `URLClassLoader` does not forcibly unload classes or destroy all instances/providers. A real plugin manager only closes a loader after no requests, tasks, callbacks, caches, or objects belonging to the plugin remain active.

### 4.5. Compiling and Running

From the **lab/** directory, run these bash commands:

~~~bash
mkdir -p build/api build/plugin build/host dist

javac -encoding UTF-8 -d build/api src/api/dev/example/spi/Greeter.java
jar --create --file build/api.jar -C build/api .

javac -encoding UTF-8 -cp build/api.jar -d build/plugin src/plugin/dev/example/impl/HelloGreeter.java
jar --create --file dist/hello-plugin.jar -C build/plugin . -C resources .

javac -encoding UTF-8 -cp build/api.jar -d build/host src/host/dev/example/host/Demo.java
java -cp "build/host:build/api.jar" dev.example.host.Demo dist/hello-plugin.jar
~~~

**Expected stdout when running the exact structure above, with no other provider for the same SPI on the host classpath:**

~~~text
before original: true
providers outside: 0
inside plugin loader: true
provider: Hello, Java
resource: plugin-message
after success: true
caught: simulated failure
after failure: true
after close: true
~~~

The line `providers outside: 0` appears because the host runtime classpath of the demo command contains only host classes and `api.jar`. If you **manually add the plugin JAR to the host classpath**, the experimental conditions no longer hold and external discovery results may differ.

On Windows, separate entries in the `-cp` argument with **;** instead of **:**; specifically `mkdir -p` is bash syntax. When using PowerShell, create directories with `New-Item -ItemType Directory -Force` and keep the `javac`, `jar`, and `java` commands using semicolon classpath separators.

Inspect the JAR before running:

~~~bash
jar --list --file dist/hello-plugin.jar
~~~

The output must contain the key entries:

~~~text
dev/example/impl/HelloGreeter.class
META-INF/services/dev.example.spi.Greeter
config/message.txt
~~~

These are the **three entries to verify**, not the entire stdout of `jar`; the tool may also list the manifest and directory entries. If the descriptor is missing, `ServiceLoader` will not find the provider. If the resource is missing, the host will report `Missing plugin resource` even though the provider might load successfully. These two errors are completely different from forgetting to restore the TCCL.

## 5. Step-by-Step Analysis of the Call Boundary

The timeline of the example can be visualized as:

~~~text
Thread main
    TCCL = original
       |
       | create pluginLoader (TCCL unchanged yet)
       v
    withContextClassLoader(pluginLoader)
       | save previous = original
       | set TCCL = pluginLoader
       |  ServiceLoader.load(Greeter.class)
       |  plugin resource lookup
       |  invoke provider.greet(...)
       | finally: TCCL = original
       v
    Thread main: TCCL = original
       |
       | enter second call
       | set pluginLoader
       | throw IllegalArgumentException
       | finally: TCCL = original
       v
    Thread main: TCCL = original
       |
       | finish work and close pluginLoader
       v
    Thread main: TCCL still = original
~~~

At the moment `finally` runs, **`action` may not have returned its result to the caller yet** or may be propagating an exception. `finally` still restores before the caller resumes execution. If the caller uses a thread pool, this is critical: the worker thread can immediately pick up work for another plugin.

This principle also helps prevent **class loader retention**. The TCCL is a reference from a `Thread` to a `ClassLoader`. If the thread lives long, keeping an unloaded plugin's loader in the TCCL can keep all associated classes and objects alive for a long time. Restoring the TCCL clears one major reference path; you still must handle other references such as child threads, registries, `ThreadLocal`, and caches.

## 6. Nested Calls: Restoring in Exact LIFO Order

Suppose the host calls plugin A, and inside A it calls an adapter requiring plugin B. Scope B must restore back to **A**, and then scope A restores back to `original`:

~~~java
// Illustrative code, assuming withContextClassLoader,
// loaderA, loaderB, and methods callA()/callB() already exist.
withContextClassLoader(loaderA, () -> {
    callA(); // TCCL = loaderA
    withContextClassLoader(loaderB, () -> {
        callB(); // TCCL = loaderB
        return null;
    });
    callA(); // TCCL returns to loaderA
    return null;
});
// Here TCCL returns to the loader prior to calling A.
~~~

Each scope saves the actual loader at the **entry of that scope**. Do not use a global "default loader" variable to restore, because it cannot accurately represent nested contexts.

If `callB()` throws an exception, B's `finally` still runs, returning the TCCL to `loaderA`, and then the exception can pass through A's `finally` and return the TCCL to `original`. This is a property of the stack model for synchronous call boundaries. Avoid calling `setContextClassLoader` in conditional branches without a corresponding `finally`.

## 7. Moving to Executors and Asynchronous Tasks

**The TCCL belongs to the thread**, not to the request, `CompletableFuture`, or plugin object. Setting the TCCL on the thread submitting work does not guarantee the work runs on that thread.

Anti-pattern:

~~~java
// Anti-pattern: executor may run the task on a different thread.
Thread.currentThread().setContextClassLoader(pluginLoader);
try {
    executor.submit(task);
} finally {
    Thread.currentThread().setContextClassLoader(previous);
}
~~~

If the executor already has worker threads, the task will run with the **worker's** TCCL, which may not be `pluginLoader`. A newly created thread might inherit the TCCL of its creator thread, but that inheritance mechanism does not solve long-lived workers, thread reuse, or context switching between tasks. Worse, spawning a new thread inside a temporary TCCL scope can cause the child thread to retain the plugin loader long after the parent has restored it.

Better: **set and restore right inside the task when the worker actually runs**:

~~~java
// Illustrative code: executor, pluginLoader, task, and previous are defined.
// Callable<T> helper is the method from section 3.
Future<?> future = executor.submit(() -> {
    withContextClassLoader(pluginLoader, () -> {
        task.run();
        return null;
    });
    return null;
});
future.get(); // Wait for the task to complete before closing pluginLoader.
~~~

In this snippet, the lambda runs on the worker thread; `withContextClassLoader` reads **the worker's** TCCL at task start and restores it in `finally`. `Future.get()` transfers the result/exception back to the calling thread without altering the calling thread's TCCL. In production code, you must handle `InterruptedException`, `ExecutionException`, timeouts, and task cancellation per lifecycle; do not wait indefinitely without bounds.

To compile the snippet above standalone inside its enclosing class, you need `import java.util.concurrent.Future;` and appropriately typed `executor`, `task`, and `pluginLoader` variables; this is an **integration illustration**, not a second complete program.

**CompletableFuture:** `supplyAsync`/`runAsync` and `Async` callbacks normally execute on an executor or another thread. If a callback needs the plugin's TCCL, wrap **the callback itself** with the set/restore boundary on the thread executing the callback. Do not assume the context propagates automatically. For non-Async callbacks, cases exist where the callback runs on whichever thread completes the stage, so be especially clear about which thread executes the code.

**Long-lived executors:** keep references to `pluginLoader` only in tasks belonging to the plugin's lifecycle. Do not cache wrappers or lambdas holding an unloaded plugin's loader in queues indefinitely; when stopping/reloading, stop accepting new tasks, cancel/await old tasks, unregister callbacks, and only then close the loader.

## 8. When to Use the TCCL vs. an Explicit Loader?

If an API allows passing a loader explicitly, that is usually the solution least dependent on hidden state:

~~~java
// When only ServiceLoader needs to find providers:
ServiceLoader<Greeter> services =
        ServiceLoader.load(Greeter.class, pluginLoader);
~~~

This snippet is **illustrative**, using the variables introduced in the lab. Calling `ServiceLoader.load(service, loader)` uses `pluginLoader` for provider discovery without mutating the thread's TCCL. However, if a provider's constructor or methods call into a library that **itself reads the TCCL**, passing a loader to one `ServiceLoader` call is not enough to establish context for the whole call chain.

Choosing by layer:

- **Local query with an API taking `ClassLoader`:** pass the loader argument when appropriate, avoiding unnecessary TCCL changes.
- **Library/framework consulting TCCL by contract:** wrap the host-owned synchronous call with TCCL using `try/finally`.
- **Resource belonging to a specific implementation:** consider `SomeProvider.class.getResourceAsStream("/path")` to look up via the implementation's defining loader rather than relying on the ambient TCCL.
- **Multiple plugins with separate loaders:** keep the SPI loaded by a shared loader; TCCL only helps frameworks pick a lookup path and cannot fix class identity issues between SPI copies in different loaders.
- **Asynchronous business logic:** move the boundary into the task-executing thread rather than setting it on the submitting thread and assuming propagation.

One easily missed detail: `ServiceLoader` is **lazy**. If the host sets the TCCL, calls `ServiceLoader.load(...)`, and restores it before iterating, provider discovery may rely on the loader captured by `ServiceLoader` at creation time. Yet the provider implementation may still use the TCCL during instantiation or execution, so you must still identify the **actual boundary running code that needs the TCCL**, rather than wrapping only `ServiceLoader` creation and assuming everything else is covered.

## 9. Common Errors and How to Handle Them

| Symptom | Likely Cause | How to Fix |
| --- | --- | --- |
| Plugin A finishes, request B sees A's resources | Forgot to restore or restored to the wrong loader | Save `previous` right at the start of the boundary; restore with `finally` |
| ServiceLoader finds no provider even though JAR has descriptor | TCCL is still the host loader; plugin is not in its search path | Specify `pluginLoader` via overload or wrap lookup with TCCL |
| Provider found, but throws error during callback | Callback runs on another thread or framework reads resource using different TCCL | Set/restore TCCL inside the thread executing the callback |
| Plugin loads, but host hits ClassCastException | SPI was redefined by another loader | Share one SPI copy with unified class identity; check parent/delegation |
| Plugin removed, yet loader is not freed | Thread pool, TCCL, tasks, caches, or provider instances still hold references | Stop lifecycle in proper order, clean up, then close loader |
| Restoring with system class loader still breaks nested calls | `previous` may be loader A or `null`, not the system loader | Restore the **saved `previous` value** |
| Called setContextClassLoader outside try and action throws | Missing `finally`; thread retains old context | Wrap action inside `try/finally`; test error paths too |
| TCCL set, yet class loader still cannot find class | API uses defining/caller loader or JAR/dependency missing from plugin loader | Identify actual lookup API and dependency graph |
| SecurityException on setContextClassLoader | Permission to change TCCL denied under security controls | Report context setup error; do not proceed as if switch succeeded |
| URLClassLoader closed too early | Tasks/providers/resources are still active | Wait for task completion and lifecycle cleanup before closing |

**Do not catch `Throwable` just to "guarantee restoration."** `finally` will restore along normal Java exit paths, including when `action` throws a `RuntimeException` or `Error`, as long as the JVM still executes `finally`. Broadly catching `Throwable` and swallowing errors can hide severe failures. If you need to catch business errors, catch meaningful exception types **outside** the `withContextClassLoader` boundary, after the TCCL has already been restored.

## 10. Testing Restoration Behavior and Isolation Between Plugins

A good TCCL test verifies **loader identity using the `==` operator**, not merely comparing class names or `toString()`. In the lab, the lines `inside plugin loader`, `after success`, `after failure`, and `after close` all print `true`. That proves that on the exact execution thread, the boundary switched and restored the TCCL as intended.

Valuable tests:

1. **Success path:** invoke provider and resource inside the plugin scope; verify everything is resolved with the expected loader, and TCCL upon return equals `original`.
2. **Exception path:** action throws `IllegalArgumentException` or a business exception; caller catches the error and verifies TCCL equals `original`. Never place restore only in `catch` or the success branch.
3. **Nested calls:** set `loaderA`, nest `loaderB`, verify after B it returns to A, and after A it returns to `original`, even when B throws.
4. **Reused worker thread:** submit tasks for plugin A and B consecutively to the same worker; after each task, it must return to the TCCL prior to task start. Avoid using shared thread pools in ways that let a plugin spawn worker threads inside a temporary context scope.
5. **Absent plugin resource:** omit `config/message.txt` from the JAR, verify a clear error is reported while `finally` still restores the TCCL.
6. **Plugin unload:** stop tasks, cancel callbacks, drop references, and close `pluginLoader`; verify living threads do not retain the old loader via TCCL. Do not infer that a loader has unloaded immediately simply because `close()` was called.

Example assertion without JUnit in a local test snippet:

~~~java
Thread thread = Thread.currentThread();
ClassLoader before = thread.getContextClassLoader();

try {
    withContextClassLoader(pluginLoader, () -> {
        throw new IllegalStateException("check");
    });
} catch (IllegalStateException expected) {
    if (!"check".equals(expected.getMessage())) {
        throw expected;
    }
}
if (thread.getContextClassLoader() != before) {
    throw new AssertionError("TCCL was not restored");
}
~~~

This is **illustrative member code** within a scope where `withContextClassLoader` and `pluginLoader` exist. It demonstrates a crucial check: if the working code fails, the test still verifies the TCCL after the error propagates out.

## 11. Rules to Apply in a Host / Plugin Manager

A host can encapsulate TCCL logic in a single place, such as the adapter layer invoking plugins. That design must clearly define: **who owns the plugin loader, which calls genuinely need context, which thread runs the call, and when the loader can close**.

A sound execution sequence:

1. Initialize or select a verified plugin loader whose parent shares the API/SPI and correct dependencies.
2. Identify the synchronous boundary invoking providers, callbacks, or frameworks that use the TCCL; prefer passing an explicit loader if the API supports it.
3. On the thread executing the call, save the current TCCL and set `pluginLoader`.
4. Run all operations needing the context (lazy lookup, provider construction, method invocation, resource read).
5. Restore `previous` in `finally`, regardless of outcome or exception.
6. When hopping to another thread, repeat the boundary **inside the executing task**, rather than relying on the submitting thread's TCCL.
7. When removing a plugin, stop accepting new work, finish tasks and callbacks, drop remaining loader references, and then close the loader.

The TCCL is a mechanism for **routing class/resource loading context per thread**, not a global classpath mutation or a security barrier. Further Java SE 17 reading: [Thread.getContextClassLoader/setContextClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html), [ServiceLoader.load](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html).

Always uphold the rule: **save exact `previous` → set exact `pluginLoader` → run exact scope → restore `previous` via `finally`**. It is the strictness of this boundary that lets multiple plugins share a thread pool without leaking context and reduces the risk of retaining class loaders after a plugin shuts down.