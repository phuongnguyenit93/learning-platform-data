# Plugin Initialization and Context Class Loader Management in Java

An application with a plugin system typically has to **load the plugin's bytecode with a dedicated loader**, create a plugin instance, invoke lifecycle hooks such as `start()`/`stop()`, and allow the plugin to discover implementations or resources within its own scope. The issue is that many platform APIs and frameworks may be **defined in a parent loader**, whereas the plugin's providers, configuration, or resources reside in a **child loader**. Parent-first delegation helps the child find APIs in the parent, but the parent does not automatically look down into every child loader.

**Thread Context ClassLoader (TCCL)** is a mechanism that allows code running on **a thread** to specify "which loader APIs that support context-based lookup should use for the current task." During plugin initialization, the host can **temporarily set TCCL = plugin loader**, invoke the constructor/start hooks, and then **restore the previous TCCL in `finally`**. More importantly, you must accurately determine **when context is needed**, avoid leaks across thread pools, and ensure the loader is not closed while the plugin still needs to load classes/resources.

This article belongs to the **Plugin Architecture** group in Java core – classloader. The objective is to design a plugin initialization and teardown cycle with clear boundaries, understand the difference between the defining loader and TCCL, implement a compilable/runnable Java 17+ sample, analyze plugin SPI discovery, executors/threads, JPMS, and hot reload, and handle lifecycle errors in a verifiable manner.

## 1. Three Loader Contexts to Keep Separate

There are three relationships that are often conflated into one:

| Concept | What is it tied to? | What is it used for? |
| --- | --- | --- |
| **Defining loader** | Each `Class<?>` defined by the JVM | Determines runtime type identity and class origin; `type.getClassLoader()` |
| **Parent loader** | Delegation relationship of a `ClassLoader` | Child queries parent first under the parent-first model; `loader.getParent()` |
| **Thread context class loader** | Each `Thread` | APIs that actively read TCCL can use it to find providers/classes/resources for the current context |

Keep in mind:

- **Changing TCCL does not change the defining loader of an already loaded class.** If `host.PluginManager` is defined by the system loader, changing TCCL does not cause that class to be reloaded by the plugin loader.
- **Changing TCCL does not alter `getParent()`.** The plugin loader still has the parent specified when the loader was created.
- **Not every API reads TCCL.** `ServiceLoader.load(Service.class)` uses TCCL according to the Java 17 contract; `Class.forName(String)` uses the defining loader of the class containing the call, while `Class.forName(name, boolean, loader)` uses the loader passed in.
- **TCCL is thread-scoped.** A request on thread A does not automatically change the TCCL of thread B running in an executor.
- **The loader chosen during discovery differs from the loader that actually defines the resulting class.** The plugin loader may delegate `api.Plugin` to the parent, even though it defines `plugin.Entry` itself.

Therefore, when a class is not found, you need to identify the **specific lookup API** and the **class/thread calling it**, rather than defaulting to always changing TCCL.

## 2. A Practical Plugin Architecture Problem

Suppose the host provides two interfaces:

- `api.Plugin`: a contract consisting of `start()` and `stop()`.
- `api.Greeting`: an SPI for which a plugin can provide a provider.

A plugin contains:

- `plugin.Entry` implements `api.Plugin`.
- `plugin.GreetingProvider` implements `api.Greeting`.
- Descriptor `META-INF/services/api.Greeting` containing the name `plugin.GreetingProvider`.

Classloader graph:

```text
             [Application/System Loader]
               |               |
           api.Plugin       api.Greeting
               |               |
               +-------+-------+
                       ^
                       | parent-first
                       |
               [Plugin URLClassLoader]
                       |
                       +-- plugin.Entry
                       +-- plugin.GreetingProvider
                       +-- META-INF/services/api.Greeting
```

The host **must** share `api.Plugin`/`api.Greeting` between the host and the plugin, because the JVM identifies a type by **binary name + defining loader**. If each plugin defines a different copy of `api.Plugin`, casting the plugin instance to the host's `api.Plugin` may fail even if the interface name and source code are identical.

Why is TCCL useful? Because `plugin.Entry.start()` may call `ServiceLoader.load(Greeting.class)` to find an implementation that exists only in the plugin loader. If TCCL at that time is still the host loader, discovery may not see the plugin's `META-INF/services/api.Greeting`. If TCCL is temporarily set to the plugin loader, ServiceLoader has the right path to find the metadata/provider.

**However**, TCCL should not be turned into a "global variable" for the entire JVM; if the host runs multiple plugins, each task needs to use the loader **belonging to the plugin currently being served**, and then must restore the context before the thread is reused.

## 3. What Should the Plugin Initialization Sequence Look Like?

A simple cycle:

```text
Read/inspect plugin artifact
       |
       v
Create a new ClassLoader, parent = shared API loader
       |
       v
Load entrypoint class with plugin loader
       |
       v
Verify entrypoint implements the right api.Plugin
       |
       v
Save original TCCL of the current thread
       |
       v
Set TCCL = plugin loader
       |
       +-- create entrypoint instance
       |   (constructor, class initialization when required by JVM)
       |
       +-- invoke plugin.start()
       |   (SPI, resources, framework initialization)
       |
       +-- register listener/task/provider when start succeeds
       |
       v
Restore original TCCL in finally
       |
       v
Plugin RUNNING; host retains loader + instance + lifecycle handle
```

**Do not close `URLClassLoader` immediately after constructor/start** if the plugin still has to run afterward. `close()` prevents loading new classes/resources from the loader's URLs; already loaded classes may continue to work, but dependencies lazy-loaded later may fail.

Clearly separate the phases:

1. **Prepare:** verify the JAR source, version/API compatibility, execution permissions, dependencies, and resource paths; establish the plugin namespace.
2. **Load/verify:** use the created loader to find the entrypoint, check `Plugin.class.isAssignableFrom(entryClass)`.
3. **Initialize/start:** set the appropriate context, create the instance, and call the `start()` hook; include rollback on failure.
4. **Active:** manage requests/tasks calling into the plugin, always carrying the correct context within the necessary scope.
5. **Stop/dispose:** stop accepting new work, wait for/cancel tasks, set the right context to call `stop()`, unregister listeners/providers/caches, close the loader, and then drop strong references.

A **loaded** entrypoint class is not necessarily **initialized**. `ClassLoader.loadClass` typically only loads the class; the `<clinit>` initializer may run when code actually creates an instance or performs a Java operation requiring initialization. If the initializer uses a TCCL-based API, **set TCCL before creating the instance**, not after the constructor.

## 4. Runnable Java 17+ Sample: Host and Plugin on Separate Classpaths

This is a standalone program using `URLClassLoader`, `ServiceLoader`, two shared interfaces, and a provider descriptor. The example has been compiled with `javac --release 17` and run successfully.

### 4.1 Structure

Create the `plugin-context-demo` directory:

```text
plugin-context-demo/
├── host-src/
│   ├── api/
│   │   ├── Plugin.java
│   │   └── Greeting.java
│   └── host/
│       └── Launcher.java
├── plugin-src/
│   └── plugin/
│       ├── Entry.java
│       └── GreetingProvider.java
├── host-classes/                         (host output)
└── plugin-classes/
    ├── plugin/
    │   ├── Entry.class
    │   └── GreetingProvider.class
    └── META-INF/
        └── services/
            └── api.Greeting                (UTF-8 service descriptor)
```

Create `host-classes` and `plugin-classes/META-INF/services` before running the commands. **Do not add `plugin-classes` to the host's runtime classpath**, because we want to prove that plugin classes/resources exist only in the dedicated loader.

### 4.2 Shared API Contract

File `host-src/api/Plugin.java`:

```java
package api;

public interface Plugin {
    void start();
    void stop();
}
```

File `host-src/api/Greeting.java`:

```java
package api;

public interface Greeting {
    String text();
}
```

The host compiles and defines the two interfaces. The plugin is compiled **against** `host-classes` and at runtime delegates to the parent to use the exact same copy of `api.Plugin`/`api.Greeting`.

### 4.3 Plugin Provider

File `plugin-src/plugin/GreetingProvider.java`:

```java
package plugin;

import api.Greeting;

public final class GreetingProvider implements Greeting {
    @Override
    public String text() {
        return "Hello from provider";
    }
}
```

File **`plugin-classes/META-INF/services/api.Greeting`** contains exactly one line:

```text
plugin.GreetingProvider
```

This is a **text file without a `.txt` extension**, not a Java source file. The path must be under the **classpath/resource root of the plugin loader**. `ServiceLoader` uses the binary service name `api.Greeting` to look up the descriptor, and then reads the provider class name `plugin.GreetingProvider`.

### 4.4 Plugin Entrypoint Dependent on TCCL

File `plugin-src/plugin/Entry.java`:

```java
package plugin;

import api.Plugin;
import api.Greeting;
import java.util.ServiceLoader;

public final class Entry implements Plugin {
    public Entry() {
        System.out.println("entry sees plugin TCCL="
                + (Thread.currentThread().getContextClassLoader()
                    == Entry.class.getClassLoader()));
    }

    @Override
    public void start() {
        Greeting service = ServiceLoader.load(Greeting.class)
                .findFirst().orElseThrow();

        System.out.println("plugin started: " + service.text());
    }

    @Override
    public void stop() {
        System.out.println("plugin stopped");
    }
}
```

Why does the constructor print TCCL? To verify that **the host switched the context before initializing the plugin**. The `start()` method calls `ServiceLoader.load(Greeting.class)`, an API that under Java 17 **selects TCCL**, not necessarily the defining loader of `Entry`.

`findFirst().orElseThrow()` forces `ServiceLoader` to find and instantiate the first provider. If the descriptor is missing or the loader cannot see the provider, this method throws `NoSuchElementException`; if the metadata/provider is invalid, `ServiceConfigurationError` may appear during iteration.

### 4.5 Launcher Creating the Loader, Temporarily Setting TCCL, and Restoring It

File `host-src/host/Launcher.java`:

```java
package host;

import api.Plugin;
import api.Greeting;
import java.net.URLClassLoader;
import java.net.URL;
import java.nio.file.Path;
import java.util.ServiceLoader;

public class Launcher {
    public static void main(String[] args) throws Exception {
        Thread thread = Thread.currentThread();
        ClassLoader original = thread.getContextClassLoader();

        System.out.println("host providers="
                + ServiceLoader.load(Greeting.class).stream().count());

        URL url = Path.of("plugin-classes").toUri().toURL();

        try (URLClassLoader pluginLoader =
                new URLClassLoader(
                        new URL[]{url},
                        ClassLoader.getSystemClassLoader())) {

            Class<?> clazz = pluginLoader.loadClass("plugin.Entry");

            System.out.println("same API="
                    + Plugin.class.isAssignableFrom(clazz));

            thread.setContextClassLoader(pluginLoader);
            try {
                Plugin plugin = (Plugin) clazz
                        .getDeclaredConstructor()
                        .newInstance();

                plugin.start();
                plugin.stop();
            } finally {
                thread.setContextClassLoader(original);
            }
        }

        System.out.println("restored="
                + (thread.getContextClassLoader() == original));

        System.out.println("host providers after="
                + ServiceLoader.load(Greeting.class).stream().count());
    }
}
```

Explanation of design choices:

- `Plugin.class.isAssignableFrom(clazz)` confirms that the entrypoint class implements **the exact interface that the host uses**, not a duplicate copy defined by the child.
- `pluginLoader.loadClass("plugin.Entry")` finds the class via the URL/plugin namespace; this operation does not automatically guarantee that the static initializer has run. TCCL is set **before invoking the constructor**.
- `ClassLoader.getSystemClassLoader()` acts as the parent so that the plugin can resolve the `api.Plugin` and `api.Greeting` APIs.
- `thread.setContextClassLoader(pluginLoader)` binds the context to the current thread; APIs that use TCCL such as `ServiceLoader` will use the right plugin loader when `start()` runs.
- `finally` restores the original even if the constructor/`start()`/`stop()` throws an exception.
- `try-with-resources` closes the loader **after** `stop()` has been called in the short-lived demo.
- The purpose of the demo is to observe context, **not a complete production plugin manager**. For a real plugin that exists for many hours, the host must keep the loader open throughout the RUNNING state and only close it after all cleanup.

### 4.6 Compile and Run

From the `plugin-context-demo` directory, use JDK 17 or later:

```bash
javac --release 17 -d host-classes host-src/api/Plugin.java host-src/api/Greeting.java host-src/host/Launcher.java
javac --release 17 -cp host-classes -d plugin-classes plugin-src/plugin/GreetingProvider.java plugin-src/plugin/Entry.java
java -cp host-classes host.Launcher
```

The commands only need one classpath entry at a time, so the syntax works on Windows/Linux/macOS. The SPI descriptor file needs to be created with the **exact name and path** before running.

Exact verified stdout:

```text
host providers=0
same API=true
entry sees plugin TCCL=true
plugin started: Hello from provider
plugin stopped
restored=true
host providers after=0
```

### 4.7 Meaning of Each Output Line

- `host providers=0`: the host's loader does not find an `api.Greeting` provider because the provider is only in `plugin-classes`, which is not on the host classpath.
- `same API=true`: the plugin's `Entry` implements the exact `api.Plugin` defined by the parent/system loader, allowing the host to cast.
- `entry sees plugin TCCL=true`: right when the constructor runs, the thread context is the plugin loader.
- `plugin started: Hello from provider`: `ServiceLoader.load(Greeting.class)` reads `META-INF/services/api.Greeting` via TCCL, locates the provider, and invokes the implementation.
- `plugin stopped`: the stop hook is called before the host closes the loader.
- `restored=true`: the thread TCCL has returned to its initial value.
- `host providers after=0`: after restoring, discovery on the host side uses the original context again and does not automatically "see" the plugin's provider.

**Do not confuse the final result with unloading:** `host providers after=0` only proves that context discovery has been restored. It does **not** prove that the JVM immediately unloads the classes/plugin loader or reclaims metaspace.

### 4.8 What Happens If You Forget to Switch TCCL?

If `Launcher` does not call `thread.setContextClassLoader(pluginLoader)` while `Entry.start()` still uses `ServiceLoader.load(Greeting.class)`, the discovery call may use the **host/system loader** (according to the example's initial context). It does not see the plugin's descriptor, so `findFirst()` has no elements and `orElseThrow()` throws `NoSuchElementException`.

If the `finally` restore is omitted, the `restored` line can become `false`, and subsequent host tasks may be directed toward the provider namespace of the stopped plugin. This is an isolation/lifecycle bug, not a hot reload feature.

## 5. TCCL in Constructors, Static Initializers, and Start Hooks

When initializing a plugin, three points can run custom code:

1. **Class initialization:** the JVM runs static field initializers/`static { ... }` when the class is first initialized.
2. **Constructor:** creates the plugin object, and may read configuration, register callbacks, or call service discovery.
3. **Start hook:** starts threads/schedulers, service providers, connections, or other resources.

If any of these points actively uses `Thread.currentThread().getContextClassLoader()` or an API that reads TCCL, then the context must be selected **before that operation begins**.

Example plugin class:

```java
package plugin;

public final class ContextCheck {
    static {
        System.out.println("TCCL in clinit = "
                + Thread.currentThread().getContextClassLoader());
    }

    public ContextCheck() {
        System.out.println("TCCL in constructor = "
                + Thread.currentThread().getContextClassLoader());
    }
}
```

This is an **illustrative class** and does not include a `main` program. If the host only calls `pluginLoader.loadClass("plugin.ContextCheck")` before setting TCCL, the static block **will not necessarily run**. If the host calls `Class.forName(name, true, pluginLoader)` or the constructor before setting TCCL, the static block may execute with the wrong context and have already caused side effects that cannot be undone merely by switching the loader afterward.

How the host chooses the loader and initialization timing can be written as:

```java
Thread t = Thread.currentThread();
ClassLoader previous = t.getContextClassLoader();
try {
    t.setContextClassLoader(pluginLoader);
    Class<?> entry = Class.forName(
            "plugin.Entry", true, pluginLoader);
    Object instance = entry.getDeclaredConstructor().newInstance();
    // Invoke plugin.start() and framework initialization here.
} finally {
    t.setContextClassLoader(previous);
}
```

This is an **illustrative snippet inside a method that handles reflection exceptions**, assuming `pluginLoader` is available. Setting `initialize=true` is intentional when you want the class initializer to run immediately within the managed context. If you do not want static initialization to happen too early, you can use `false` and initialize only when actually creating the instance.

**Selecting TCCL does not replace class initialization policies.** `Class.forName(String)` defaults to the loader of **the class containing the call site** and does not automatically use TCCL. When the host needs a class defined by the plugin, pass the loader explicitly or use `pluginLoader.loadClass`.

## 6. Writing a Helper to Avoid Forgetting to Restore

In code with many entrypoints, duplicating `try/finally` everywhere makes it easy to forget. It can be encapsulated into a helper taking a `ClassLoader` and a `Callable<T>`:

```java
import java.util.concurrent.Callable;

public final class ContextLoaders {
    private ContextLoaders() { }

    public static <T> T withContext(
            ClassLoader loader, Callable<T> action)
            throws Exception {
        Thread thread = Thread.currentThread();
        ClassLoader original = thread.getContextClassLoader();

        try {
            thread.setContextClassLoader(loader);
            return action.call();
        } finally {
            thread.setContextClassLoader(original);
        }
    }
}
```

This is a **complete class compilable with Java 17**. Usage, assuming `pluginLoader` and `Plugin plugin` already exist:

```java
ContextLoaders.withContext(pluginLoader, () -> {
    plugin.start();
    return null;
});
```

This helper provides several guarantees:

- The original TCCL saved is **that of the very thread executing the action**.
- There is no global variable holding the context.
- Restoration occurs even if the action throws a checked exception, runtime exception, or error; `finally` is still executed according to Java semantics (except in cases of abnormal JVM/process termination).
- Nested calls are supported: the outer call sets loader A, the inner sets B, the inner restores to A, and the outer restores to the original.

Limitations:

- `Callable<T>` is **synchronous**: it sets TCCL for the duration that `action.call()` runs on the current thread.
- If the action **launches an asynchronous task** and returns immediately, the context of the future task must be managed separately; the helper does not automatically "propagate context across an executor".
- If the thread has a special `SecurityManager` or a runtime policy restricting `setContextClassLoader`, a `SecurityException` may be thrown; this needs to be handled according to the specific Java 17 environment.
- Do not let plugin code retain references to threads/loaders in a way that causes leaks.

### Why Not Modify `Thread.currentThread()` Once at Startup?

Because a thread pool uses multiple worker threads and serves many different plugins/requests. TCCL is per-thread state and may be modified by frameworks at various points. Setting it once on the main thread **does not guarantee** that every running background worker has the right TCCL when processing work.

## 7. ExecutorService and Context Propagation Bugs

A regular `Thread` can **inherit TCCL** from the thread that creates it at thread creation time. However, thread pool workers are **created and reused**; a worker may already have existed **before** the host set TCCL for a request/plugin, or its context may have been altered by a prior task without being restored.

This is the problem:

```java
Thread.currentThread().setContextClassLoader(pluginLoader);
executor.submit(() -> {
    // Do NOT assume TCCL == pluginLoader.
    useServices();
});
```

This is an **illustrative snippet**, assuming `executor`/`pluginLoader`/`useServices()` exist. Setting TCCL on the **submitting thread** does not modify the context of an **already existing worker thread**.

A proper pattern:

```java
executor.submit(() -> {
    Thread t = Thread.currentThread();
    ClassLoader before = t.getContextClassLoader();
    try {
        t.setContextClassLoader(pluginLoader);
        return ServiceLoader.load(Greeting.class)
                .findFirst().orElseThrow().text();
    } finally {
        t.setContextClassLoader(before);
    }
});
```

This is an **illustrative snippet** inside host code that already has `executor`, `pluginLoader`, and `Greeting`. It uses the `Callable<String>` overload of `submit` and returns a `Future<String>`. If you want to observe exceptions, you must call `Future.get()` or set up an error-reporting mechanism; simply calling `submit` and discarding the Future can hide start/discovery failures.

**Important:** to avoid lifecycle deadlocks/races, the plugin manager needs to track futures/tasks belonging to the plugin. Do not close the loader while another task is using it to load classes or read resources.

### Threads Created by the Plugin Itself

If a plugin creates its own thread in `start()`, the new thread may **inherit the TCCL of the thread creating it**. This makes provider lookups inside the plugin's thread appear to work — yet upon undeployment, a still-alive thread can keep its TCCL pointing to the plugin loader indefinitely.

A formal lifecycle is required:

- The host or plugin tracks thread/executor ownership.
- `stop()` requests cancellation/interruption and waits for a reasonable termination.
- Thread pool/task wrappers restore TCCL.
- Clean up `ThreadLocal` variables, callbacks, and schedulers holding plugin objects.
- Do not rely solely on `URLClassLoader.close()` or `System.gc()`.

**Creating unmanaged infinite threads is discouraged** inside a plugin. Even daemon threads can still hold references to the plugin loader, although they do not prevent JVM exit.

## 8. What Does the Host Need to Retain While a Plugin Is Running?

A plugin in the RUNNING state typically needs a management handle:

```text
PluginHandle
  |
  +-- pluginId / version / lifecycleState
  +-- URLClassLoader
  +-- api.Plugin instance
  +-- registered services/listeners/callbacks
  +-- owned tasks/executor references
  +-- configuration/module/layer context (if any)
  +-- cleanup actions
```

This is a design diagram, not a built-in Java SE class.

**Do not close the loader at the end of a factory method** when returning an instance for long-term use by the host:

```java
Plugin createPlugin() throws Exception {
    try (URLClassLoader loader =
            new URLClassLoader(urls, parent)) {
        Class<?> clazz = loader.loadClass("plugin.Entry");
        return (Plugin) clazz.getDeclaredConstructor().newInstance();
    }
}
```

This is **illustrative code**, where `urls`/`parent`/`Plugin` are hypothetical components. Because `try-with-resources` ends upon return, the loader closes prematurely. Already loaded classes/objects may work along existing code paths, but the first time a new dependency/resource is needed from the plugin URL afterward, it may fail.

Instead, the host retains the loader and instance inside `PluginHandle`; close the loader only after `stop`/unregistering/canceling tasks.

## 9. Initialization Failure and Rollback

Startup can fail at any stage:

- Wrong plugin artifact name/missing class → `ClassNotFoundException`.
- Entrypoint does not implement the API → `ClassCastException` or failed `isAssignableFrom` check.
- Constructor/`<clinit>` error → `InvocationTargetException`, `ExceptionInInitializerError`, or linkage errors.
- `ServiceLoader` reads a malformed descriptor → `ServiceConfigurationError` during iteration.
- Provider missing a dependency → `NoClassDefFoundError`/`ServiceConfigurationError` depending on the context.
- `start()` throws a runtime exception after already registering some listeners.
- The plugin starts tasks that fail to complete within the timeout.

A rollback procedure should follow a clear order:

1. Transition the state to **RUNNING** only after startup conditions succeed.
2. Record each resource/registration created during start so there is a corresponding cleanup.
3. On error, **stop created tasks/registrations**, rather than waiting for a stop phase that might never be called.
4. Invoke the plugin's cleanup if the object was created and the contract allows cleanup even when start did not complete.
5. Always restore the current thread's TCCL.
6. Once there is no remaining work for the loader to serve, close the loader and release host references.
7. Report the original error along with suppressed cleanup exceptions; **do not swallow the start error** just because cleanup failed.

### State Management Pseudocode Example

```java
// The PluginHandle, Registry, and CleanupRegistry types are host-defined.
PluginHandle handle = preparePlugin(artifact);
boolean started = false;
try {
    withPluginContext(handle.loader(), () -> {
        handle.instance().start();
        return null;
    });
    started = true;
    publishRunning(handle);
} catch (Throwable startupFailure) {
    try {
        stopTasksAndUnregister(handle);
        if (handle.instance() != null) {
            withPluginContext(handle.loader(), () -> {
                handle.instance().stop();
                return null;
            });
        }
    } catch (Throwable cleanupFailure) {
        startupFailure.addSuppressed(cleanupFailure);
    } finally {
        handle.loader().close();
    }
    throw startupFailure;
}
```

**Illustrative pseudocode, not a complete Java class**: methods and types such as `preparePlugin`/`publishRunning` are not declared. The pattern shows the rollback idea and avoids letting a cleanup exception mask the initial root cause.

In production code, state conflicts/races must be avoided; use `try/finally` and a more robust cleanup structure to ensure **every operation requiring cleanup is attempted**, even if one cleanup step has already failed. `close()` can also throw `IOException`, so suppressed exceptions must be managed.

**Subtlety:** If `start()` failed halfway through, a `stop()` method not designed for a partially initialized state may throw further errors. The plugin API should clearly specify whether it supports rollback or requires each registration to return a handle for safe cleanup.

## 10. Context-Setting Rules for Lifecycle Hooks

| Operation | How should TCCL be chosen? | Why? |
| --- | --- | --- |
| Host safely reads metadata before loading | Usually no plugin TCCL needed | Artifact can be validated outside the execution scope |
| Host calls `pluginLoader.loadClass` | Switching TCCL is not required for `loadClass` itself | The loader is already explicit; however, class initialization may not have occurred yet |
| Plugin class/constructor initialization | **Plugin loader**, if the initializer uses a context-aware API | Static init/constructor may discover resources/providers |
| `plugin.start()` | **Plugin loader** | SPI discovery and framework initialization |
| Host processes its own pure business logic | **Previous host context** | Prevents the plugin from leaking into unrelated requests |
| Plugin callback/event handler | **Plugin loader** for the duration of the callback | Provider/resource lookup may occur later |
| Plugin task/executor | Set TCCL **inside the worker thread when running the task** | TCCL does not automatically propagate across a thread pool |
| `plugin.stop()`/cleanup hook | **Plugin loader** when resources/providers are still needed for cleanup | Cleanup may use plugin classes/resources |
| Close loader | After tasks and cleanup finish | Avoids races with class/resource loading |
| Actual unloading | Not controlled via TCCL | Depends on strong references and GC/JVM |

The table represents **design principles**, not a rule that **every method is required to read TCCL**. If a plugin only uses an explicit loader or non-context-based APIs, keeping the host's TCCL may be appropriate. However, if the plugin contract requires context, this should be stated clearly and consistently.

## 11. One Java API Does Not Equal One Kind of Lookup

Comparison of common APIs used during startup:

| API | Default loader/source chosen | Does TCCL affect it directly? |
| --- | --- | --- |
| `ServiceLoader.load(Service.class)` | TCCL of the calling thread | **Yes**, by contract |
| `ServiceLoader.load(Service.class, loader)` | The passed-in loader | Does not depend on TCCL for the initial selection |
| `ServiceLoader.load(layer, Service.class)` | Named modules of the layer and ancestors | Relies on ModuleLayer, not solely TCCL |
| `Class.forName("pkg.Impl")` | Defining loader of **the class containing the call statement** | **No** |
| `Class.forName("pkg.Impl", true, loader)` | The passed-in loader | No, unless you explicitly pass the TCCL value yourself |
| `pluginLoader.loadClass(name)` | `pluginLoader` itself and parent delegation | Not by default |
| `ClassLoader.getSystemResource(...)` | System loader | Not by default |
| `Thread.currentThread().getContextClassLoader().getResource(...)` | Loader returned by TCCL | **Yes**, because the code chooses it explicitly |
| `Main.class.getResource("config.json")` | Module/package/defining loader of `Main` | Does not automatically choose TCCL |

This explains a familiar bug:

```java
// Code running in host.FrameworkHelper defined by the system loader:
Class<?> type = Class.forName("plugin.Entry");
```

Even though the thread currently has TCCL = plugin loader, the **single-parameter** overload does not automatically use it. If the host needs to target the plugin namespace, write:

```java
ClassLoader context =
        Thread.currentThread().getContextClassLoader();

Class<?> type = Class.forName("plugin.Entry", true, context);
```

Both are **illustrative snippets**, requiring the caller to handle `ClassNotFoundException`. In a production plugin manager, it is usually better to **pass `PluginHandle.loader()` directly** rather than relying indirectly on a TCCL that may change.

## 12. ModuleLayer and JPMS-Based Plugins

Since Java 9, a plugin can be packaged as a **named module** and resolved in its own `ModuleLayer`, rather than only as a classpath JAR/`URLClassLoader`. In that case, you must distinguish between **loader mapping** and **module service discovery**.

The APIs:

- `ModuleLayer.defineModulesWithOneLoader(...)`: modules in the new layer share a loader.
- `ModuleLayer.defineModulesWithManyLoaders(...)`: each module in the new layer gets its own loader.
- `layer.findLoader("m.plugin")`: retrieves the loader assigned to a specific named module.
- `ServiceLoader.load(layer, Service.class)`: locates providers in the layer and ancestor layers per JPMS; **not classpath SPI discovery from unnamed modules**.
- `module-info.java` with `uses`/`provides ... with ...`: declares service consumption/provision in explicit named modules.

Illustrative descriptor example:

```java
module m.plugin {
    requires m.api;
    provides api.Greeting with plugin.GreetingProvider;
}
```

This is an **illustrative `module-info.java` file**; it requires module `m.api` containing/exporting `api.Greeting` and proper module path configuration.

When a plugin operates in a custom layer, **do not assume simply setting TCCL resolves all service discovery**. You may need to use `ServiceLoader.load(pluginLayer, Greeting.class)`; you must also consider module `uses` (for the appropriate caller module), exports/opens, read edges, and package-to-loader mapping.

A host can use TCCL to integrate legacy libraries **while simultaneously** using an explicit `ModuleLayer` for JPMS providers. They are two complementary mechanisms and cannot replace each other in every context.

### Should TCCL Be Assigned to a Layer Loader?

If a legacy framework only supports TCCL-based lookup while the plugin is created in a custom ModuleLayer, the host can choose the module's appropriate loader as TCCL within the scope of the framework call. However, that loader may contain one or more modules, and there is no guarantee it will see **all** modules/providers in the layer as the `ServiceLoader.load(layer, ...)` overload does. When accurate discovery by module layer is desired, prefer module-aware APIs.

## 13. Plugin Isolation, Security, and Shared APIs

During startup, check **shared API identity** before casting; if the child redefines `api.*`, TCCL cannot fix a type identity error. Choose the right loader when looking up resources/SPIs, but inspect resource URLs separately because parent-first may return a host configuration file with the same name. `ClassLoader` and TCCL do not create a sandbox for untrusted plugins; JPMS access rules still apply. Verify artifacts/versions and use process boundaries when security isolation is required.

## 14. Plugin Hot Reload and TCCL-Induced Memory Leaks

A very common reason a custom classloader is not reclaimed by GC after undeployment is that **a thread still holds a TCCL pointing to the old loader**.

Example reference path:

```text
GC root
   |
   v
Thread pool worker still alive
   |
   +-- Thread.contextClassLoader
              |
              v
        OldPluginLoader
              |
              v
       plugin classes / metadata
```

If a worker from plugin A's task **forgets to restore TCCL**, the host may close A's URLClassLoader and even drop the reference in its registry, yet the thread still holds a strong reference to loader A. Consequently, the loader and the classes it defined **cannot be reclaimed as expected** until the retained reference is released.

Other retention sources that require cleanup:

- Host static maps holding providers/`Class<?>`/reflection `Method` objects.
- `ServiceLoader` caches or provider instances shared beyond the deployment scope.
- ThreadLocal values, `InheritableThreadLocal`, and executor queues containing objects/plugin classes.
- Event listeners, scheduled tasks, callbacks, MBeans, JDBC driver registrations, logging bridges.
- Threads created by the plugin that are still running after the plugin has stopped.
- JNI global references or native resources if the plugin contains native code.

**`URLClassLoader.close()` does not force class unloading.** Closing the loader releases URL/JAR source handles and prevents the loader from defining new classes from those URLs; metadata of already loaded classes can remain alive. The JLS specifies that unloading depends on GC's ability to reclaim the defining loader and JVM discretion, with no deadline.

### A Safer Undeploy/Redeploy Procedure

```text
RUNNING
    |
    +-- reject new requests
    +-- stop/await in-flight tasks
    |
    v
STOPPING (correct plugin TCCL when calling stop hooks)
    |
    +-- unregister listeners/providers
    +-- cancel schedulers/threads
    +-- clear deployment-owned caches/ThreadLocals
    |
    v
CONTEXT_CLEANUP
    |
    +-- restore TCCL on every involved worker
    |
    v
CLOSE_LOADER
    |
    +-- URLClassLoader.close()
    |
    v
RELEASE_REFS
    |
    +-- drop PluginHandle/instances/Classes/Method references
    |
    v
GC_ELIGIBLE (if no strong references remain)
    |
    v
MAY_UNLOAD (when performed by the JVM)
```

Hot reloading a new version typically requires a **new ClassLoader**. Replacing `plugin.jar` on disk does not cause the old loader to "redefine" the same binary class name. If the parent already contains a plugin class with the same name, the new loader may delegate back to the parent and fail to actually pick up the new code — check `getClassLoader()`.

## 15. Risks When Multiple Plugins Run Concurrently

Suppose the host has `PluginA` and `PluginB` with two separate loaders. A request A and a request B may run on two threads; each thread may only have its TCCL set to the corresponding plugin for the duration of that plugin's work.

**Do not store the active loader in a global static field** and switch it for every request:

```java
// Anti-pattern illustration; DO NOT use:
static ClassLoader CURRENT_PLUGIN_LOADER;
```

Because request A could change the value to loader A while request B needs loader B. Even with synchronized, the concept of a "current loader for the entire JVM" is unsuitable for multiple concurrent plugins.

Per-task selection pattern:

```java
// Pseudocode using host-defined PluginHandle.
PluginHandle h = registry.resolve(pluginId);
executor.submit(() -> {
    return ContextLoaders.withContext(h.loader(), () -> {
        return h.instance().process(input);
    });
});
```

Here `PluginHandle`, `registry`, `process`, and `input` are **hypothetical application components**; this snippet illustrates the context-per-task model. Beyond TCCL, locking/lifecycle management is required to prevent tasks from using `h` after the plugin has stopped/the loader has closed.

### Is It Necessary to Create Dedicated Threads per Plugin?

Not mandatory. A shared thread pool can work if the host wraps every invocation in a context scope and manages task ownership. A dedicated thread pool per plugin can simplify isolation/lifecycle, but consumes more resources and still must shut down and restore TCCL properly.

**More important than thread count is scope:** every callback, task, SPI lookup, and cleanup must establish the proper loader/module context for the duration it runs.

## 16. Debugging: Where to Look When a Plugin Fails to Start

### 16.1 Print Loader, Module, and Context at the Exact Moment

You can add the snippet below to the constructor or `start()` when you have the `Entry` class:

```java
ClassLoader defining = Entry.class.getClassLoader();
ClassLoader context =
        Thread.currentThread().getContextClassLoader();

System.out.println("defining=" + defining);
System.out.println("context=" + context);
System.out.println("same=" + (defining == context));
System.out.println("module=" + Entry.class.getModule());
```

This is an **illustrative snippet inside class `Entry`**; the loader `toString()` output depends on the implementation, so no fixed stdout is shown. `same=false` is not always an error; it is simply a signal to inspect if the plugin contract requires context = entry's loader.

### 16.2 Verify Which SPI Resources Are Visible

```java
ClassLoader loader =
        Thread.currentThread().getContextClassLoader();

java.util.Enumeration<java.net.URL> resources =
        loader.getResources("META-INF/services/api.Greeting");

while (resources.hasMoreElements()) {
    System.out.println(resources.nextElement());
}
```

This is an **illustrative snippet inside a method that handles `IOException`**, assuming `loader` is non-null and the application uses classpath SPI. Finding a resource proves the descriptor **is visible**; it does not prove that the provider class/constructor/dependencies are all valid.

### 16.3 Error and Troubleshooting Table

| Symptom | Possible Cause | Fix at the Right Layer |
| --- | --- | --- |
| `ClassNotFoundException: plugin.Entry` | Wrong URL/classpath root, wrong binary name, or unsuitable parent policy | Verify `plugin/Entry.class` under the plugin root and the loader being used |
| `ClassCastException` to `api.Plugin` | Plugin defines its own copy of `api.Plugin` | Place shared API in the parent, check `isAssignableFrom` |
| `ServiceLoader` returns 0 providers | Wrong TCCL or missing `META-INF/services` / wrong resource root | Select the explicit plugin loader, check the descriptor |
| `ServiceConfigurationError` | Malformed descriptor, provider missing constructor/subtype, or initialization error | Inspect the cause, metadata/provider class |
| Constructor runs with host context | TCCL was set after `newInstance` | Set context **before** initialization |
| Startup throws exception, TCCL not restored | Missing `finally` | Use a context helper and lifecycle rollback |
| Thread pool occasionally sees another plugin's provider | Worker still holds TCCL from a previous request | Scope TCCL within the worker task and restore it |
| Plugin starts fine, but later callback fails on resources | Callback invoked by the host outside plugin context | Wrap each callback in the plugin scope |
| `NoClassDefFoundError` after close | Loader closed early, new dependency lazy-resolved, or plugin init previously failed | Keep the loader open until the end of the lifecycle, inspect cause |
| Hot reload increases metaspace | Old loader still reachable via threads/caches/registries | Inspect retaining paths, TCCL, lifecycle cleanup |
| Module service does not see provider | Mismatched layer/`uses`/`provides` | Use module-aware discovery and graph |
| `InaccessibleObjectException` during reflection | Missing `opens` on named module | Fix module access, not just TCCL |

Quick procedure:

1. Print the defining loader of `api.Plugin` and `plugin.Entry`; confirm the API is shared.
2. Print TCCL **directly inside the failing constructor/start/callback/worker**, not only on the main thread.
3. If using ServiceLoader: confirm `META-INF/services` is at the root and the proper discovery loader is used.
4. If using `Class.forName`: confirm the overload and caller defining loader; choose the explicit plugin loader when needed.
5. If using the module path: inspect the layer, named-module service declarations, and exports/opens.
6. If errors occur only after undeployment: check whether the loader was closed while callbacks/tasks were still active.
7. If the loader does not unload: analyze strong references from threads/TCCL/caches/registries, rather than inferring from `System.gc()` not freeing it immediately.

## 17. Distinguishing Initialization Errors from Class Loading Errors

When debugging, remember that "plugin initialization" encompasses multiple operations:

**Load class**:

```java
Class<?> clazz = pluginLoader.loadClass("plugin.Entry");
```

Usually does not yet require the static initializer to run.

**Initialize class**:

```java
Class<?> clazz = Class.forName("plugin.Entry", true, pluginLoader);
```

Requires the class initializer (if not already initialized); may cause side effects and throw `ExceptionInInitializerError` if the initializer fails.

**Create instance**:

```java
Object instance = clazz.getDeclaredConstructor().newInstance();
```

Requires a valid constructor and a class accessible under Java/module rules, and will initialize the class if needed. Reflection may wrap exceptions thrown by the constructor inside `InvocationTargetException`.

**Start plugin**:

```java
((Plugin) instance).start();
```

Invokes business code that may create resources/threads/providers and requires rollback on error.

The four snippets above are **illustrative code inside a method** with `pluginLoader`/`Plugin` already declared and exceptions handled. If `clazz` and `instance` are declared in the same scope, do not repeat variable declarations; each step is separated solely to explain the operation.

On the first static initialization error, the JVM may report `ExceptionInInitializerError`; subsequent uses of the erroneous class may report `NoClassDefFoundError`. Do not try to resolve this merely by changing TCCL after the class is already in an initialization failure state — you must fix the root cause and typically create a new loader/deployment to obtain a fresh class definition in a valid reload.

## 18. Common Misconceptions

| Misconception | Explanation |
| --- | --- |
| "`setContextClassLoader` changes the loader of the running class." | No; the class's defining loader does not change. |
| "TCCL is a new parent loader." | No; `getParent()` still preserves the structural relationship. |
| "If the host sets TCCL once at boot, it will be right for every plugin." | No; different plugins/threads have different contexts. |
| "Once the plugin finishes loading, changing TCCL is no longer needed." | It may be needed during constructors, start, callbacks, tasks, and stop hooks. |
| "`Class.forName(String)` always reads TCCL." | No; it defaults to the caller class's loader. |
| "`ServiceLoader.load(Service.class)` uses the system loader." | Under the Java 17 contract, it uses the **current thread's TCCL**. |
| "The submitting thread's TCCL automatically enters every executor worker." | Not guaranteed; the worker may already exist with a different context. |
| "Changing TCCL and forgetting to restore it causes no harm." | It can mix providers, cause multi-tenant bugs, and keep the loader alive. |
| "`close()` of URLClassLoader immediately unloads all classes." | No; class unloading depends on GC's ability to reclaim the defining loader. |
| "Seeing same API=true means the plugin is completely compatible." | It only proves interface assignability; version/linking/behavior/resource and access checks still remain. |
| "`ServiceLoader.reload()` reloads plugin bytecode." | No; it resets the provider cache of the ServiceLoader instance. |
| "TCCL is sufficient to sandbox malicious plugins." | No; plugins require separate trust/isolation controls. |
| "Every named module discovers SPIs the same way as the classpath." | No; `uses`/`provides`/ModuleLayer have their own rules. |

## 19. Self-Check Questions with Answers

**1.** Why should the plugin loader have the loader containing `api.Plugin` as its parent?

**Answer:** So that the plugin and the host resolve the same `Class<api.Plugin>`. If each loader defines its own API copy with the same name, the class identities differ and the host may be unable to cast.

**2.** If `Entry.start()` calls `ServiceLoader.load(Greeting.class)`, what loader is chosen by default?

**Answer:** The thread's TCCL at the time of the call. It does not default to `Entry`'s defining loader or the system loader, unless the current context actually points to that loader.

**3.** Why must TCCL be set before the plugin's constructor?

**Answer:** The constructor and class initializer may use TCCL or SPI APIs. If the context is only switched after the constructor, side effects/discovery during the initialization phase have already executed under the old context.

**4.** If the host switches TCCL = plugin loader but calls `Class.forName("plugin.Entry")` directly inside a host helper, is it guaranteed to find it?

**Answer:** No. The single-parameter overload uses the defining loader of the host caller class. To select the plugin loader, use `Class.forName(name, initialize, pluginLoader)` or `pluginLoader.loadClass`.

**5.** Why is `try/finally` important when calling `plugin.start()`?

**Answer:** Start can throw errors. `finally` still restores the original TCCL, preventing the thread from retaining the plugin context across other host/tenant tasks.

**6.** When an `ExecutorService` has pre-existing workers, is setting TCCL on the submitting thread enough?

**Answer:** No. It must be set/restored inside the **worker thread executing the task**, or an executor/task wrapper with an explicit propagation contract must be used.

**7.** If a plugin creates a new thread while the current thread's TCCL is the plugin loader, what can happen?

**Answer:** The new thread typically inherits the creator's TCCL, so it may keep the plugin loader alive beyond its lifecycle if the thread is not stopped. Task/thread management and cleanup are required.

**8.** Why does the example output `host providers after=0` after restoring TCCL?

**Answer:** Host discovery once again selects the original context, which does not see the SPI descriptor located under the child plugin loader. The result does not prove that the loader has been GC'd/unloaded.

**9.** Should `URLClassLoader.close()` be called immediately after `plugin.start()` if the plugin continues serving requests?

**Answer:** Not under general design. Future code paths may require classes/resources not yet loaded. Close after stop/cleanup and when no tasks are still using the loader.

**10.** Can a `ClassCastException` between plugin `Entry` and host `Plugin` be solved using TCCL?

**Answer:** Not directly. That is usually a type identity/loader sharing issue. You need to fix the classpath/delegation so the plugin uses the same API class as the host.

**11.** For a named-module plugin, must you always use `ServiceLoader.load(service, pluginLoader)` instead of the layer overload?

**Answer:** No. You need to consider the module graph and APIs. `ServiceLoader.load(pluginLayer, Service.class)` has semantics for finding providers in the layer and its ancestors, suited for module-aware discovery; TCCL does not completely replace it.

**12.** After the host has closed the plugin loader and metaspace still does not decrease, what could the causes be?

**Answer:** Threads/TCCL, plugin instances, class metadata, callback registries, caches, or native roots may still hold strong references; the JVM may also not have performed unloading yet. Inspect retaining paths and GC behavior, rather than assuming close must unload immediately.

## 20. Production Checklist for Plugin Startup and Context

1. **Artifact:** Have the JAR/plugin bytecode, dependencies, version, and source been verified?
2. **Shared contract:** Are `api.Plugin`, DTOs, and service interfaces located in the appropriate parent loader?
3. **Entrypoint:** Did the host load the right binary name through the right plugin loader and check assignability?
4. **Init timing:** If static initialization/constructors use SPI, was TCCL set **before init**?
5. **Start hook:** Did the host call `start()` under the right context and mark RUNNING only after it succeeded?
6. **Restore:** Is there a `try/finally` in **every** context scope, including exception paths?
7. **Executor:** Is context set inside the executing worker rather than only on the submitting thread?
8. **Callbacks:** Are the plugin's listeners/timers/scheduled tasks wrapped with the right context?
9. **Resource lookup:** Are provider descriptors/configs at the right root; does the API use the defining loader or TCCL?
10. **Error/rollback:** If constructor/start partially fails, is cleanup of registrations/tasks/resources thoroughly attempted?
11. **Stop order:** Are new requests rejected, tasks awaited, and `stop()` called with the right context before close?
12. **Cleanup:** Have TCCL, ThreadLocal, ServiceLoader caches, static registries, and callbacks been properly removed for the deployment?
13. **Close timing:** Is `URLClassLoader.close()` called only after there is no concurrent class/resource loading?
14. **Reload:** Does a new plugin version have a new loader, the right shared APIs, and no duplicate classes in the parent?
15. **Modules:** If using ModuleLayer, have service discovery and `uses`/`provides`/exports/opens been resolved?
16. **Isolation:** Is there a trust policy, and are class loaders/TCCL not treated as a security sandbox?
17. **Tests:** Are there tests for provider visibility before/during/after context, error paths, and thread pool reuse?
18. **Observability:** Are pluginId, lifecycle phase, defining/context loader, and cause logged for diagnostics?

## Conclusion

**Plugin initialization** is not just `loadClass` and calling a constructor. The host must coordinate **shared API identity, entrypoint class loading, class initialization, SPI discovery, context management, start/stop lifecycle, and cleanup**.

**TCCL is a per-thread context**, useful when APIs such as `ServiceLoader.load(Service.class)` need to locate providers beneath the plugin loader rather than the framework/host loader. Always **set the right TCCL before operations that need context**, **restore it with `finally`**, reset it inside the actual executing worker/callback, and manage the loader's lifecycle as a resource living alongside the plugin. Do not confuse TCCL with the parent/defining loader or expect it to solve every classloading and JPMS error.

Official Java 17 documentation:

- [Thread API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `getContextClassLoader`, `setContextClassLoader`, context inheritance for new threads.
- [ServiceLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): TCCL-selecting overload, SPI, lazy discovery, and `reload()`.
- [ClassLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): defining loader, parent delegation, and `getParent()`.
- [Class API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `Class.forName` and class initialization.
- [URLClassLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): `close()`, loader URL/JAR lifetime.
- [ModuleLayer API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html): named modules and module-to-loader mapping.
