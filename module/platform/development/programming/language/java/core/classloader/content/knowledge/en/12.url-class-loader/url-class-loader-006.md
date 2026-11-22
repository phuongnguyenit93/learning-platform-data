# Managing URLClassLoader Lifecycle with close and try-with-resources

## 1. Why Does URLClassLoader Have a Resource Lifecycle?

`java.net.URLClassLoader` is a `ClassLoader` implementation capable of locating classes and resources from a set of URLs: directories, JAR files, and supported URL sources. It commonly appears in **plugin systems**, dynamic code execution tools, compilers/test runners, and environments that need to load libraries at runtime.

When looking up a class in a JAR, the loader may open the JAR file and maintain access structures to serve subsequent loads. Therefore, beyond its responsibility of defining classes, `URLClassLoader` also holds **I/O resources that must be closed**.

Since Java 7, `URLClassLoader` implements `java.io.Closeable` (and thereby `AutoCloseable`):

```java
public class URLClassLoader
        extends SecureClassLoader
        implements Closeable {

    public void close() throws IOException;
}
```

This is an **API declaration excerpt**, not code for redefining the JDK class yourself.

**The most important rule:** calling `close()` **closes the ability to find new classes/resources from the URLs managed by the loader, while attempting to release opened files**. It **does not mean** destroying all already-defined classes, stopping threads, running object finalizers, or forcing the JVM to unload classes.

## 2. What Exactly Does close() Do?

According to the official `URLClassLoader.close()` contract:

1. **Closes the loader for finding new classes/resources defined by this loader itself**: after closing, classes or resources not previously found/loaded by this loader can no longer be newly loaded from its URL search path in the normal way.
2. **Classes/resources belonging to the parent loader remain accessible** through the delegation chain when applicable.
3. **Already-loaded classes/resources remain usable**. `Class<?>` objects, already-defined classes, and existing instances do not disappear simply because the loader is closed.
4. For `jar:` and `file:` sources, the loader attempts to **close files that were opened** while serving lookups. This is especially important to avoid keeping file handles/JARs locked on the operating system.
5. **A subsequent close on an already-closed loader has no effect**; there is no need to write custom state flags just to ensure `close()` is called only once.
6. `close()` **may throw `IOException`**. When multiple I/O errors occur during closing, the first exception is thrown, and subsequent errors are attached to `getSuppressed()`.

There is a very important concurrency limitation: if another thread **is actively loading a class at the exact moment `close()` is called**, the Java documentation states that **the result of that load is undefined**. Therefore, proper lifecycle management must **prevent new loading work and wait for in-flight work to finish before closing**; do not use `close()` as a mechanism to forcibly interrupt an active class-loading operation.

### Effect Comparison Table

| Action | Does `close()` guarantee it? |
|---|---|
| Closing JAR/file handles opened by URLClassLoader | **Attempts to perform**, may throw `IOException` |
| Preventing the loader from defining new classes from its own URLs | **Yes**, per the `close()` contract |
| Automatically deleting already-loaded `Class<?>` objects | **No** |
| Invalidating objects already created from plugin classes | **No** |
| Stopping threads, executors, or timers started by the plugin | **No** |
| Removing TCCL from threads still holding the plugin loader | **No** |
| Clearing `static` caches, listener registrations, or ThreadLocals | **No** |
| Forcing the JVM to garbage-collect or unload classes immediately | **No** |
| Guaranteeing the JAR can be deleted in all circumstances | **No**; other code/processes may still hold the file |
| Automatically making another class loader switch versions of a loaded class | **No** |

In short: `close()` addresses **one part of the I/O resource lifecycle**, while the plugin/application lifecycle is a broader responsibility.

## 3. How Does URLClassLoader Look Up Classes Before and After Closing?

For a `URLClassLoader` using the default `ClassLoader.loadClass` mechanism, the order is typically:

```text
loadClass("plugin.Greeter")
       │
       ▼
findLoadedClass(name)
       │ already loaded → use existing class
       │ not yet loaded
       ▼
parent.loadClass(name) / bootstrap
       │ parent found → use parent's class
       │ not found
       ▼
URLClassLoader.findClass(name)
       │ before close: search from URL search path
       │ after close: cannot find new class from these URLs
       ▼
Class<?> or ClassNotFoundException
```

Therefore:

- If **the class was already loaded before closing**, `loader.loadClass(name)` may still return **the same `Class<?>` object** after closing.
- If **the class exists only in the plugin JAR and has never been loaded**, after closing, the loader no longer has a normal path to define that new class; `loadClass` may end with `ClassNotFoundException`.
- If **the class is provided by the parent or bootstrap loader**, such as `java.lang.String`, parent delegation can continue to work after the URLClassLoader is closed.

Do not misunderstand `close()` as setting a flag that makes **every `loadClass` call** fail. It primarily blocks the **new lookup and loading handled by the URLClassLoader itself**.

Conversely, do not misunderstand “loaded classes remain usable” as meaning every operation on them will **always** succeed: an already-loaded method may later reference **an unloaded dependency class**, require a new resource, or attempt to reopen a resource inside the JAR. Those operations can fail because the loader is closed. Therefore, plugin work must still be stopped **before** closing the loader.

## 4. Complete Example: Closing the Loader While Loaded Classes Still Exist

We create a plugin JAR containing two classes: `demo.Greeter` and `demo.Later`. The host program only loads `Greeter` before closing. Then we try reusing `Greeter`, loading `Later`, accessing `String` from the parent, and calling `close()` a second time.

### 4.1. File src/demo/Greeter.java

```java
package demo;

public final class Greeter {
    static {
        System.out.println("Greeter initialized");
    }

    public static String say() {
        return "hello from plugin";
    }
}
```

### 4.2. File src/demo/Later.java

```java
package demo;

public final class Later {
    public static String name() {
        return "late class";
    }
}
```

The `Later` class is intentionally **not loaded before closing**. It exists in the archive to verify the case where the loader is no longer permitted to look up new classes from the JAR.

### 4.3. File LoaderLifecycleDemo.java

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class LoaderLifecycleDemo {
    public static void main(String[] args) throws Exception {
        Path pluginJar = Path.of("plugin.jar").toAbsolutePath();
        URL[] urls = {pluginJar.toUri().toURL()};

        URLClassLoader loader = new URLClassLoader(
                urls,
                LoaderLifecycleDemo.class.getClassLoader()
        );

        Class<?> greeter;
        try (loader) {
            System.out.println("inside scope");

            greeter = Class.forName("demo.Greeter", false, loader);
            System.out.println("defined by child: "
                    + (greeter.getClassLoader() == loader));

            System.out.println("before invocation");
            System.out.println(
                    greeter.getMethod("say").invoke(null)
            );
        }

        System.out.println("after close");

        Class<?> same = loader.loadClass("demo.Greeter");
        System.out.println("loaded class reused: " + (same == greeter));

        System.out.println("existing method still callable: "
                + greeter.getMethod("say").invoke(null));

        System.out.println("parent String available: "
                + (loader.loadClass("java.lang.String") == String.class));

        try {
            loader.loadClass("demo.Later");
            System.out.println("unexpected");
        } catch (ClassNotFoundException expected) {
            System.out.println("new plugin class unavailable");
        }

        loader.close();
        System.out.println("second close completed");
    }
}
```

`try (loader)` is Java 9+ syntax for a resource variable **already declared outside**, provided that the variable is final or effectively final. In the example, the `loader` variable is never reassigned, so the code compiles on Java 17+. If Java 7/8 source-level compatibility is required, use the `try (URLClassLoader loader = new URLClassLoader(...))` form, though in that case you cannot access the `loader` variable outside the `try` scope by that name alone.

### 4.4. Building the JAR and Running

From a working directory containing `LoaderLifecycleDemo.java` and the two `src/demo/*.java` files, run with JDK 17+.

On Bash:

```bash
mkdir -p plugin-classes
```

On Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force plugin-classes | Out-Null
```

Then:

```bash
javac -d plugin-classes src/demo/Greeter.java src/demo/Later.java
jar --create --file plugin.jar -C plugin-classes .
javac LoaderLifecycleDemo.java
java -cp . LoaderLifecycleDemo
```

Directory structure after building:

```text
project/
├── LoaderLifecycleDemo.java
├── LoaderLifecycleDemo.class
├── plugin.jar
├── src/
│   └── demo/
│       ├── Greeter.java
│       └── Later.java
└── plugin-classes/
    └── demo/
        ├── Greeter.class
        └── Later.class
```

**Important condition for accurate results:** run the host with `-cp .`, and **do not** add `plugin.jar` or `plugin-classes` to the application classpath. If the parent loader sees the plugin classes first, parent-first delegation may return the classes from the parent and invalidate the experiment.

Stdout on JDK 17+ under the above condition:

```text
inside scope
defined by child: true
before invocation
Greeter initialized
hello from plugin
after close
loaded class reused: true
existing method still callable: hello from plugin
parent String available: true
new plugin class unavailable
second close completed
```

### 4.5. Result Analysis

1. `Class.forName("demo.Greeter", false, loader)` requests finding/loading `Greeter` but **does not request running its static initializer**. `defined by child: true` indicates that the `URLClassLoader` in the example is the defining loader of `Greeter`.
2. `getMethod("say").invoke(null)` invokes a static method, so the JVM initializes `Greeter` and prints `Greeter initialized` once.
3. At the end of the `try (loader)` block, Java automatically calls `loader.close()`. There is no need to call `close()` manually in a `finally` block.
4. Afterward, `loader.loadClass("demo.Greeter")` returns the recorded class. `same == greeter` is `true`: a closed loader **does not delete runtime classes**.
5. The `say()` method was already loaded and requires no new dependencies or plugin resources, so the example can still invoke it after close. This is **not a recommendation to keep running plugins after close**.
6. `java.lang.String` is provided by the bootstrap loader, so lookup via parent/boot still works.
7. `demo.Later` was present in the JAR but **had not been loaded** before close. `URLClassLoader` can no longer locate/define it from the JAR and therefore throws `ClassNotFoundException`.
8. Calling `close()` a second time is a **no-op** per the contract. There is no second `Greeter initialized` line.

This example illustrates the boundary between **the “closed loader” state** and **the “already-defined class” state**. They are two separate concepts.

## 5. Standard Pattern: try-with-resources

When a program creates a `URLClassLoader` to execute a task with a bounded scope, the standard approach is:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class ScopedLoaderDemo {
    public static void main(String[] args) throws Exception {
        URL jarUrl = Path.of("plugin.jar").toUri().toURL();
        ClassLoader parent = ScopedLoaderDemo.class.getClassLoader();

        try (URLClassLoader pluginLoader =
                     new URLClassLoader(new URL[] {jarUrl}, parent)) {
            Class<?> type = pluginLoader.loadClass("demo.Greeter");
            System.out.println("loaded: " + type.getName());
        }
    }
}
```

With `plugin.jar` from the previous example, compile and run:

```bash
javac ScopedLoaderDemo.java
java -cp . ScopedLoaderDemo
```

Stdout:

```text
loaded: demo.Greeter
```

Merely loading the class does not trigger `Greeter.<clinit>`, so `Greeter initialized` is not printed. When the `try` block exits normally or via an exception, `close()` is invoked automatically.

Benefits:

- Makes it clear **who owns the loader** and **when it must be closed**.
- Ensures an attempt is made to close the resource at the end of the scope, even if logic inside the block throws an exception.
- Avoids repeating `close()` in every `return`, `throw`, or `catch` branch.
- Reduces the risk of forgetting to close the loader when a build tool, plugin host, or test runner encounters an error.

**Do not wrap a URLClassLoader in try-with-resources too early if the plugin must outlive that scope.** For example, a `createPlugin()` method that loads a class using `try (URLClassLoader loader = ...)` and returns a plugin object to the caller may close the loader before the caller uses other classes or resources of the plugin. Bugs from this may only surface when executing rarely used features.

## 6. When Does try-with-resources Close?

The structure:

```java
try (URLClassLoader loader = new URLClassLoader(urls, parent)) {
    usePlugin(loader);
}
// At this point close() has already been called.
```

is **illustrative code**; the variables `urls`, `parent`, and the `usePlugin` method must be defined in the application.

Java closes the resource **after the `try` body finishes and before control passes to the code that follows**. Whether the `try` body executes a `return` or throws an exception, Java still attempts to close the resource.

With multiple resources:

```java
try (
    URLClassLoader loader = new URLClassLoader(urls, parent);
    java.io.InputStream stream = loader.getResourceAsStream("settings.txt")
) {
    // Use loader and stream.
}
```

This is an **excerpt**: `urls` and `parent` are existing values, and `stream` may be `null` if the resource does not exist. When there are multiple resources, they are closed in **reverse order of their declaration**: `stream.close()` first, `loader.close()` second. This is the logical order so that reading the resource finishes before closing the loader/JAR itself.

For `URLClassLoader.getResourceAsStream`, the documentation also notes that input streams opened through this method may be closed when the loader is closed. However, **you should not rely on the loader to clean up every stream for you**: closing streams right where they are used (with their own `try-with-resources`) keeps resource management explicit and avoids holding resources longer than necessary.

Do not continue reading from an `InputStream` that has already been closed and expect its contents to remain intact. Opening a resource URL obtained before close via `url.openStream()` also has no guarantee that all underlying handles remain usable after the loader has released its resources.

## 7. Handling IOException When Closing the Loader

`URLClassLoader.close()` declares:

```java
public void close() throws IOException
```

It attempts to close opened files. If one or more close operations fail, an `IOException` may be thrown. If multiple I/O errors are detected, the first error is thrown, and subsequent ones may be found in `getSuppressed()`.

There are two types of exceptions to consider:

1. **Exceptions from logic running in the `try` body**: for example, provider initialization fails or processing code throws an exception.
2. **Exceptions from `close()`**: I/O errors while releasing JAR/file resources.

With `try-with-resources`, if both occur, Java keeps the exception from **the `try` body as the primary exception**, and attaches the close error to the **suppressed** list. This prevents the original root cause from being masked.

### Runnable Example Demonstrating Suppressed Exceptions

This is a simulated resource, **not a reimplementation of URLClassLoader**. It solely demonstrates the general semantics of `try-with-resources` when `close()` fails.

Create `SuppressedDemo.java`:

```java
import java.io.IOException;

public final class SuppressedDemo {
    static final class FailingResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("closing");
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) {
        try (FailingResource resource = new FailingResource()) {
            throw new IllegalStateException("work failed");
        } catch (Exception ex) {
            System.out.println("primary: " + ex.getMessage());
            System.out.println("suppressed count: "
                    + ex.getSuppressed().length);
            System.out.println("first suppressed: "
                    + ex.getSuppressed()[0].getMessage());
        }
    }
}
```

Run:

```bash
javac SuppressedDemo.java
java SuppressedDemo
```

Stdout:

```text
closing
primary: work failed
suppressed count: 1
first suppressed: close failed
```

Key takeaway: the original error `work failed` is not overwritten by the close error `close failed`. When diagnosing issues, inspect both `getCause()` and `getSuppressed()`.

**If the `try` body succeeds without error but `close()` throws `IOException`**, the close error becomes the primary exception and must be handled or declared. For simple programs, you can declare `main(String[] args) throws Exception` as in the section 4 example. In real applications, decide how to report, log, or roll back according to an explicit policy.

### Catching Errors When Closing Manually

In a lifecycle manager with a `stop()` method, you sometimes need to close the loader after multiple cleanup steps:

```java
// Snippet: loader is a URLClassLoader owned by the manager.
try {
    loader.close();
} catch (java.io.IOException ex) {
    System.err.println("Failed to close plugin loader: " + ex);
    for (Throwable suppressed : ex.getSuppressed()) {
        System.err.println("Suppressed close error: " + suppressed);
    }
}
```

Do not silently swallow `IOException`: if the JAR file is still held open, subsequent JAR replacement or deletion operations may fail, especially on operating systems with strict file locking.

## 8. Closing the Loader Does Not Mean Unloading Classes

Four concepts must be distinguished:

| Concept | Meaning |
|---|---|
| **Closing the loader** | `URLClassLoader.close()` closes URL/JAR sources and prevents finding new classes/resources from it |
| **Stopping the plugin** | The application stops tasks, unregisters listeners, closes plugin resources, and stops invoking the plugin |
| **Loader becomes unreachable** | The program drops strong references to the loader/classes/instances so the loader can no longer be reached from GC roots |
| **Class unloading** | The JVM may reclaim the corresponding metadata/classes during GC when eligible |

**`close()` does not instruct the JVM to unload immediately**. Class unloading is managed by the JVM depending on reachability and GC policy; even `System.gc()` is only a hint, not a guarantee.

Examples of sources keeping a loader alive:

```text
Thread pool worker
     │
     └── thread.contextClassLoader ───────┐
                                         ▼
Global static registry ──> Plugin object ──> PluginClassLoader
                                         ▲
Cached Class<?> / Method ────────────────┘
```

This diagram illustrates **possible reference paths**; not every object necessarily has this exact reference chain.

A thread pool holding a TCCL pointing to a closed plugin loader can still prevent GC from collecting the loader. A cache storing `Class<?>`, `java.lang.reflect.Method`, constructors, proxies, callbacks, or plugin objects can also extend the lifetime of the corresponding runtime classes. A plugin that spawns its own threads and does not stop them can retain the classloader via targets/contexts or static fields.

**Therefore:** for true redeployment/reloading, you must both **close I/O sources** and **clean up references and work** associated with the plugin. Never use a successful `URLClassLoader.close()` call as proof that the JVM has freed all class metadata memory.

## 9. Plugin Lifecycle: create → start → use → stop → close

For a loader serving a **long-lived** plugin, wrapping the entire lifecycle in `try-with-resources` makes more sense than wrapping **only the initial class-loading step**.

```text
[1] Create URLClassLoader
           │
           ▼
[2] Load/initialize plugin entry point
           │
           ▼
[3] Start plugin; register tasks/listeners
           │
           ▼
[4] Use plugin across requests
           │
           ▼
[5] Stop accepting new requests
           │
           ▼
[6] Wait for running tasks to finish (graceful shutdown)
           │
           ▼
[7] Unregister listeners, stop executor,
    close plugin's streams/sockets/db connections,
    clean up caches/TCCL/references
           │
           ▼
[8] URLClassLoader.close()
           │
           ▼
[9] Drop references to classes/loader;
    JVM can unload when eligible
```

The order of **stopping work before closing the loader** is critical because class loading concurrent with `close()` has undefined results. Do not use `close()` to force all tasks to terminate immediately.

### High-Level Lifecycle Scope Pattern

```java
// PSEUDOCODE / excerpt: PluginRuntime and the methods
// stopAcceptingWork, awaitQuiescence, ... are provided by the application.
try (URLClassLoader loader = createPluginLoader(pluginJar)) {
    PluginRuntime runtime = startPlugin(loader);
    try {
        runtime.serve();
    } finally {
        runtime.stopAcceptingWork();
        runtime.awaitQuiescence();
        runtime.unregisterCallbacks();
        runtime.closeOwnedResources();
    }
}
// Loader is only closed after work/plugin has been cleaned up.
```

Do not copy the snippet above as a standalone file: the `PluginRuntime` class and methods represent a design pattern, **not a standard Java API**.

If one cleanup step fails, the system still needs to attempt cleaning up **the remaining resources**, and then report errors appropriately. You can use a plugin-management object implementing `AutoCloseable` whose `close()` cleans up each resource in order; or in complex systems, use a lifecycle manager with explicit state tracking and logging.

### Why Shouldn't You Return a Plugin Object Outside a Short-Lived Loader Scope?

Problematic pattern:

```java
// PSEUDOCODE — illustrates an anti-pattern
Object createPlugin(Path jar) throws Exception {
    try (URLClassLoader loader = new URLClassLoader(
            new URL[] {jar.toUri().toURL()},
            getClass().getClassLoader())) {
        return loader.loadClass("demo.Plugin")
                .getDeclaredConstructor()
                .newInstance();
    }
}
// The loader is already closed when the object is returned!
// The object is still alive, but may need new dependencies/resources later.
```

Do not assume that returning a plugin object from a method means the loader is no longer needed. The created object may still call an unloaded class, read configuration, or look up a provider from the JAR during subsequent use.

The right design is a **lifecycle-managing object** that owns both the plugin object and the `URLClassLoader`, stopping and closing them together when the session ends.

## 10. TCCL and Thread Pools: A Commonly Forgotten Part of Lifecycle Cleanup

If the application sets the **Thread Context ClassLoader (TCCL)** to the plugin loader for `ServiceLoader` or framework SPIs, it must restore the TCCL after processing.

```java
// Snippet used in a method running on a worker thread.
// pluginLoader is the appropriate URLClassLoader instance.
Thread current = Thread.currentThread();
ClassLoader previous = current.getContextClassLoader();

try {
    current.setContextClassLoader(pluginLoader);
    // Invoke framework/service-discovery that uses TCCL if needed.
} finally {
    current.setContextClassLoader(previous);
}
```

If a long-lived worker thread retains an old plugin's TCCL after `close()`, it can hold a **strong reference** to the loader and prevent class unloading. It can also cause other requests to accidentally use the stopped plugin's context.

For executors:

- Stop accepting new tasks before closing the loader.
- Wait for or cancel existing tasks according to the system's contract.
- Clean up `ThreadLocal`s and TCCLs set by the plugin or caller.
- Ensure subsequent tasks do not continue using classes/resources from the closed plugin.
- Do not assume that changing the TCCL in the task-submitting thread automatically changes the TCCL of all pre-existing worker threads.

**Do not arbitrarily clear the TCCL with `setContextClassLoader(null)`.** The previous state may be the host or container loader; you must restore **the exact previous value**.

## 11. Close and JAR File Access on Windows/Linux

On Windows, a JAR with an open handle may not be renameable, overwritable, or deletable. On Unix, a file can be unlinked while a descriptor is still open, but the descriptor continues consuming resources until closed. `URLClassLoader.close()` attempts to close handles belonging to **that loader itself**; another `JarFile`, stream, IDE, or process may continue holding the file.

When replacing a plugin, first stop running work, clean up callbacks/resources, call `close()` and handle `IOException`, and then deploy the new artifact. Being able to delete the file after close does not prove the JVM has unloaded the classes.

## 12. Opening a New Loader Does Not Make Same-Named Classes the Same Type

Two `URLClassLoader`s **independently defining** `demo.Greeter` create two distinct runtime types, even if their binary names and bytecode are identical. Closing the old loader does not turn old instances or `Class<?>` objects into definitions of the new loader; the host must not cast implementations across two generations.

Place shared APIs/DTOs in a common parent loader and implementations in generation-specific loaders; verify `type.getClassLoader()` in reload tests. If the parent defines the implementation as well, parent-first delegation may shadow the new version.

## 13. Monitoring, Debugging, and Verifying Cleanup

### 13.1. Signs of Unreleased Resources

- The JAR cannot be replaced or deleted after the plugin stops.
- The number of open file descriptors grows with each plugin reload.
- After multiple redeployments, memory used for class metadata/metaspace or the number of class loader instances increases.
- Plugin threads continue running after stop.
- New tasks fail to find classes/resources because the loader was closed too early.
- `ClassNotFoundException` only occurs when first entering a rarely used feature after the plugin startup phase.

Do not jump to conclusions from a single symptom: a JAR lock may be held elsewhere; metaspace growth can have multiple causes; class unloading does not have to happen immediately once a loader becomes unreferenced.

### 13.2. Using JVM Tools

On HotSpot JDKs supporting unified logging, you can observe class loading/unloading with:

```bash
java -Xlog:class+load=info,class+unload=info -cp . LoaderLifecycleDemo
```

Logs can be verbose, different JDK versions have different formats, and a short run **is not guaranteed** to record class unloading. Do not treat the absence of unload lines as conclusive proof that `close()` failed.

Tools like `jcmd <pid> VM.classloader_stats` (if provided by the JDK/VM) and thread dumps help inspect live loaders and threads, though they must be interpreted in the context of GC and the actual application. Do not repeatedly call `System.gc()` automatically as an operational workaround to “close loaders.”

### 13.3. Verifying Close in Tests

A useful unit/integration test should separate what needs to be checked:

1. **Loaded before close:** load a plugin class and verify its defining loader.
2. **Closed resource path:** in a test free of races or external caches, new plugin classes are no longer defined by the old loader.
3. **Parent delegation:** standard classes defined by the parent/bootstrap loader remain usable.
4. **Cleanup:** executors, callbacks, and streams are stopped/closed, and TCCL is restored.
5. **Reload:** a new loader uses the new JAR; shared APIs maintain proper runtime identity.
6. **Failure path:** throw an exception while using the plugin; verify `close` is still called; if `close` fails, verify suppressed exceptions are preserved.

Tests **should not** assert that the JVM must unload classes immediately after `close()` or immediately after `System.gc()`: that is not a portable guarantee.

## 14. Common Mistakes

| Mistake | Consequence | Correct Approach |
|---|---|---|
| Not closing the loader after a bounded job | JARs/files may remain held open | Use `try-with-resources` or explicit lifecycle close |
| Closing right after loading the entry point while the plugin still runs | Lazy dependency/resource loads can fail | Keep the loader alive for the entire active plugin duration |
| Treating `close` as “deleting classes” | Misusing type identity/lifecycle, unfounded unload expectations | Distinguish close, stop, dereference, and GC |
| Calling `close` concurrently with a thread loading classes | Loading result is undefined | Stop/await quiescence before closing |
| Calling `loadClass` again on the old loader to get a new version | Returns already-loaded `Class<?>` or throws CNFE | Create a new defining loader and design for migration |
| Forgetting to restore TCCL in a thread pool | Wrong provider resolution, `ClassLoader` leak | Use `try/finally` to restore the previous value |
| Closing only the loader without closing plugin streams/sockets/executors | Resource and thread leaks | Clean up all plugin-owned resources |
| Swallowing `IOException` on close | Masks file handle errors, hard to diagnose | Log/propagate and inspect suppressed exceptions |
| Testing only on Linux and assuming Windows can replace the JAR | File handle behavior differs by OS | Test file lifecycle on the target deployment OS |
| Opening a JAR via `JarFile` or `JarURLConnection` outside the loader and expecting the loader to close it | Another handle remains open | Close resources in their actual owner |
| Putting the loader into a long-lived static cache | Loader/class metadata is never freed | Scope caches to the plugin session and evict on stop |

## 15. URLClassLoader Lifecycle Design Checklist

Before creating a loader:

- Determine **who owns the `URLClassLoader`** and **when its lifecycle ends**.
- Identify which JARs/directories the URLs can point to and whether isolation between plugins is needed.
- Place shared APIs in the appropriate parent loader to avoid class identity conflicts.

While the plugin is active:

- Do not close the loader while work that needs to load classes/resources from it is still running.
- Track streams, JDBC connections, sockets, executors, listeners, timers, and caches opened/created by the plugin.
- If TCCL is needed, set and restore it within the exact usage scope.

When stopping:

- Stop accepting new tasks; wait for active tasks to reach a safe state.
- Unregister callbacks/listeners, shut down executors, and close plugin resources.
- Restore TCCL and remove references from host caches if any.
- Call `URLClassLoader.close()`, handling `IOException` and suppressed failures.
- Drop references that are no longer needed, but **do not assume GC/unloading happens immediately**.

When reloading:

- Create a **new `URLClassLoader`** for the new generation.
- Keep shared API boundaries clear and do not mix implementation classes between two loaders.
- Test both functional behavior and file/classloader release in integration tests.

## 16. Self-Check Questions

1. **Which interface does `URLClassLoader` implement to be used in `try-with-resources`?** `Closeable`, which is also an `AutoCloseable`.
2. **Does `close()` prevent the loader itself from loading new classes from its URLs?** Yes, per the `URLClassLoader` contract.
3. **Does an already-loaded class disappear after close?** No; already-loaded classes and existing objects remain accessible.
4. **After close, can the parent loader still provide `java.lang.String`?** Yes.
5. **Will `loader.loadClass("demo.Greeter")` after close always fail?** No; if the loader already initiated that class, it can return the existing class.
6. **Should you keep running a plugin after close just because an old method is still callable?** No; lazily loaded dependencies/resources may no longer be available.
7. **Does `close()` wait for all threads currently loading classes to finish?** There is no guarantee; closing concurrently with class loading has undefined results.
8. **If both the `try` body and `close()` throw an exception, which one is the primary exception?** The exception from the `try` body; the close exception is preserved as suppressed.
9. **Does calling `close()` twice on an already-closed `URLClassLoader` break the loader?** No; subsequent calls have no effect per the contract.
10. **Why might a plugin not unload even after `close()`?** Strong references may still exist from TCCL, `ThreadLocal`, caches, callbacks, `Class` objects, or instances.
11. **Does replacing `plugin.jar` and calling `loadClass` on the old loader create new classes?** Not automatically; you need a new-generation loader/runtime classes per a reload architecture.
12. **For a long-lived plugin, what scope should `try-with-resources` cover?** The entire plugin lifecycle, closing only after work has stopped and plugin resources have been cleaned up.
13. **Does `URLClassLoader.close()` automatically close every `JarFile` opened anywhere in the application?** No; only the files/resources that the loader is responsible for per the API.
14. **Why might a JVM test show no class-unload logs even when `close()` succeeds?** Unloading is driven by GC and is not required to happen immediately after close.

## Official References

- [Java SE 21 — URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): `Closeable`, `close()`, post-close class/resource access, error/concurrency behavior, and `getResourceAsStream`.
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): API compatible with the Java 17 examples in this article.
- [Java SE 21 — AutoCloseable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/AutoCloseable.html): resource-closing contract.
- [Java Language Specification — `14.20.3 try-with-resources](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.3): closing order and suppressed exceptions.
- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, `findLoadedClass`, and class loading.
- [Java Virtual Machine Specification — `5.3–5.5](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html): class loading, defining loader, linking, and initialization.

**Conclusion:** **`close()` closes the `URLClassLoader`'s I/O sources, rather than “closing” existing Java classes.** Use **`try-with-resources`** when the loader's ownership scope is clear; for long-lived plugins, use a lifecycle manager to **stop → clean up → close → drop references**. Distinguishing these four steps helps prevent JARs from remaining locked, dependency-loading errors after close, and classloader leaks during redeployment.
