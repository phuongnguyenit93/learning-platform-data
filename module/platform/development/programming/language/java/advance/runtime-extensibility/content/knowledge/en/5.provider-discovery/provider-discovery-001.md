# Selecting ServiceLoader.load by Class Loader or Thread Context (TCCL)

## 1. The Problem to Solve When Discovering Providers

A Java application can publish a **Service Provider Interface (SPI)**, for example `Greeting`, and let other JARs/plugins supply implementations. `java.util.ServiceLoader<S>` locates providers from deployment metadata (on the class path or in modules), instead of forcing the host to invoke each implementation's constructor directly.

The critical issue in runtime extensibility is **which class-loading space the provider lives in**. In a single-classpath application, `ServiceLoader.load(Greeting.class)` usually finds the provider and makes it look as though choosing a class loader does not matter. In applications using plugin JARs, application servers, module layers, multiple applications in the same JVM, or thread pools, the exact same SPI can produce different results when different loaders are chosen.

This lesson focuses on the decision between two overloads:

```java
ServiceLoader<S> ServiceLoader.load(Class<S> service);
ServiceLoader<S> ServiceLoader.load(Class<S> service, ClassLoader loader);
```

These are **illustrative signatures** for comparison; the complete program and run commands are in Section 5. In real Java code, type `S` is inferred from `Class<S>`, for example `ServiceLoader<Greeting> providers = ServiceLoader.load(Greeting.class);`.

**Core idea:** Choose the loader according to the *provider deployment boundary you intentionally allow to be visible*, and ensure that both the service type and the provider belong to a compatible class-loading model. TCCL is a way to pass context from the caller down to a shared library; the overload taking `ClassLoader` is the way to decide the discovery context explicitly.

## 2. How Do the Two Overloads Actually Select a Loader?

### 2.1. `load(Class<S> service)` Reads the Thread's Context Class Loader

Java 17 defines:

```java
ServiceLoader.load(service)
```

as equivalent to:

```java
ServiceLoader.load(service, Thread.currentThread().getContextClassLoader())
```

The **Thread Context Class Loader (TCCL)** is a value attached to a thread, read via `getContextClassLoader()` and temporarily changeable via `setContextClassLoader(loader)`. It does **not necessarily** equal the loader that defined the class calling `ServiceLoader`, the SPI's loader, or the system class loader.

Four points to remember:

1. TCCL is captured **at the moment `ServiceLoader.load(service)` is called**. An already-created `ServiceLoader` does not automatically switch to a new loader just because the thread's TCCL changes afterward.
2. TCCL is the context of the *current thread*, not a property of `Greeting.class` or of a plugin. Two threads can discover different providers if their TCCLs differ.
3. A framework/container may proactively set TCCL so that libraries in a shared layer can find providers belonging to an application/plugin. Thread pools reuse threads, so you cannot assume the existing TCCL is the right context for a new task.
4. When `getContextClassLoader()` returns `null`, the two-argument overload receiving `null` uses the **system class loader** (or the bootstrap loader if unavailable) per the JDK contract. Do not interpret `null` as "search only bootstrap classes".

The one-argument overload is concise when **the runtime/container has clearly documented who sets TCCL, within what scope, and when the previous value is restored**. If no such contract exists, discovery results can depend on whichever thread happens to run.

### 2.2. `load(Class<S> service, ClassLoader loader)` Selects Explicitly

```java
ClassLoader pluginLoader = /* class loader owned by the runtime */;
ServiceLoader<Greeting> providers =
        ServiceLoader.load(Greeting.class, pluginLoader);
```

This is an illustrative snippet using a loader pre-created by the runtime, not a standalone program. The `loader` parameter is the **starting point** for `ServiceLoader` to locate providers, `META-INF/services` configurations, and provider classes.

Practical differences:

- Discovery does not depend on the TCCL attached to the calling thread. It works from scheduler, executor, or request handler threads whenever the runtime knows the exact loader of the plugin.
- It makes ownership and lifecycle clear: plugin A's registry uses loader A, plugin B's registry uses loader B.
- It does not mean "see only classes defined by this loader itself": parent delegation allows seeing classes/resources from the parent; with **named modules** in a module layer, provider lookup also follows JDK-specific rules.
- `load(service, null)` does not mean creating an empty loader. The JDK uses the system class loader, or bootstrap when no system loader is available.

**Note on naming:** `Greeting.class.getClassLoader()` returns the loader *that defined the SPI class*, whereas `Thread.currentThread().getContextClassLoader()` returns the current context loader. These two values may be identical in a simple program, yet differ in a plugin architecture.

### 2.3. Quick Selection Table

| Context | Call to Consider | Reason and Conditions |
|---|---|---|
| Standard Java class-path application, TCCL already managed | `ServiceLoader.load(Spi.class)` | Concise, though still depends on TCCL |
| Host knows the exact class loader of a plugin | `ServiceLoader.load(Spi.class, pluginLoader)` | Explicit, avoids depending on which thread calls it |
| Shared framework invoked inside an app whose TCCL is set by a container | `ServiceLoader.load(Spi.class)` | Allows the shared library to discover application providers per the container contract |
| Work running in a thread pool where TCCL might belong to a previous task | Overload taking an explicit loader; or manage TCCL in `try/finally` | Avoids reading the wrong provider and avoids retaining old class loaders |
| Host only wants providers on its own class path | `ServiceLoader.load(Spi.class, hostLoader)` | True only within actual class loader delegation and configuration |
| Providers reside in a custom **named module layer** | `ServiceLoader.load(layer, Spi.class)` | Selects the layer and its ancestors; distinct from the class path/TCCL problem |
| Find only providers visible to the platform loader | `ServiceLoader.loadInstalled(Spi.class)` | Java 17 uses the platform class loader; not for finding plugins on the application class path |

This table is a design guide, not a substitute for verifying the specific runtime's class-loading model.

## 3. Relationship Between SPI, Provider, Loader, and TCCL

Suppose there are three parts:

- **Host/API:** interface `demo.spi.Greeting` and application class `demo.app.LoaderDemo`, loaded by the application class loader.
- **Plugin:** class `demo.plugin.EnglishGreeting` together with configuration `META-INF/services/demo.spi.Greeting`, located outside the application class path.
- **Plugin class loader:** runtime's `URLClassLoader` pointing to the plugin directory/JAR and taking the SPI's loader as its parent.

Then:

```text
Application/host loader
   ├── demo.spi.Greeting         (shared SPI)
   └── demo.app.LoaderDemo
            ^
            | parent delegation
            |
Plugin URLClassLoader
   ├── demo.plugin.EnglishGreeting
   └── META-INF/services/demo.spi.Greeting
```

In this layout, `ServiceLoader.load(Greeting.class, pluginLoader)` can find the provider, while `ServiceLoader.load(Greeting.class)` depends on the current TCCL. If TCCL is still the host loader and the host cannot see the plugin's metadata, discovery returns empty.

**Class identity is especially important.** In the JVM, having the same binary name is not enough for two classes to be treated as the same type: the defining loader of a class is also part of its runtime identity. If a plugin bundles its own copy of `demo.spi.Greeting` defined by the child loader instead of using the host's `Greeting.class`, the provider may not be assignable to the host's SPI, resulting in `ServiceConfigurationError`. Therefore, place the shared API in a parent visible to both host and plugin, and let the plugin loader load the implementation and its private dependencies.

A `ClassLoader` is not a reliable security sandbox mechanism. Parent delegation, visibility, module access, resource lookup, and lifecycle are decisions that must be verified; using a separate loader by itself does not isolate CPU, memory, file, or network access.

## 4. When and Where Does Provider Discovery Work?

For providers in an **unnamed module/class path**, the JDK reads the UTF-8 file:

```text
META-INF/services/<fully.qualified.binary.name.of.SPI>
```

For example, service `demo.spi.Greeting` has the file `META-INF/services/demo.spi.Greeting`, with each line declaring a provider class name, such as `demo.plugin.EnglishGreeting`. The provider class must be visible to the relevant loader, implement the SPI, and have a `public` no-argument constructor for conventional class-path providers.

With **named modules**, the consumer module declares `uses`, and the provider module declares `provides ... with ...`. `ServiceLoader.load(service, loader)` has rules for locating providers in named modules, including certain providers in the same layer defined by a different loader; that is why the loader parameter should not be treated as a "strictly one JAR only" filter. If the primary goal is to scope to a specific module layer, use the overload `load(ModuleLayer layer, Class<S> service)`: this overload finds providers in that layer and its ancestor layers, and does not scan unnamed modules.

A `ServiceLoader` **does not necessarily read and instantiate all providers immediately when `load(...)` is called**. Only the iterator, `findFirst()`, and terminal operations on `stream()` trigger on-demand discovery and instantiation. Consequently, successfully creating a `ServiceLoader` does not prove providers are usable; configuration errors may surface during iteration.

## 5. Complete Java 17+ Example: Plugin Discovered via Explicit Loader and TCCL

This example runs on the **class path**, without using `module-info.java`. Important: **do not put `build/plugin` on the application class path when running the host**; if you add it to `java -cp`, the experiment will no longer test visibility differences.

### 5.1. Directory Tree

Create the following files from the working directory `demo/`:

```text
demo/
├── src/
│   ├── api/demo/spi/Greeting.java
│   ├── host/demo/app/LoaderDemo.java
│   └── plugin/
│       ├── demo/plugin/EnglishGreeting.java
│       └── META-INF/services/demo.spi.Greeting
└── build/                         (created by the commands below)
```

**File `src/api/demo/spi/Greeting.java`:**

```java
package demo.spi;

public interface Greeting {
    String greet(String name);
}
```

**File `src/plugin/demo/plugin/EnglishGreeting.java`:**

```java
package demo.plugin;

import demo.spi.Greeting;

public final class EnglishGreeting implements Greeting {
    public EnglishGreeting() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

**UTF-8 file `src/plugin/META-INF/services/demo.spi.Greeting` containing exactly one line:**

```text
demo.plugin.EnglishGreeting
```

The file name identifies the **SPI**, while its content is the **provider** class name. This file is a resource and must be copied to the plugin output alongside the compiled classes; `javac` does not copy resources automatically.

**File `src/host/demo/app/LoaderDemo.java`:**

```java
package demo.app;

import demo.spi.Greeting;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ServiceLoader;

public final class LoaderDemo {
    private static String describe(ServiceLoader<Greeting> loader) {
        return loader.findFirst()
                .map(provider -> provider.greet("Java"))
                .orElse("(none)");
    }

    public static void main(String[] args) throws Exception {
        Thread thread = Thread.currentThread();
        ClassLoader originalTccl = thread.getContextClassLoader();
        ClassLoader hostLoader = Greeting.class.getClassLoader();

        // Set TCCL to host so output does not depend on the launcher.
        thread.setContextClassLoader(hostLoader);
        try {
            System.out.println("host-default=" +
                    describe(ServiceLoader.load(Greeting.class)));

            URL pluginUrl = Path.of("build/plugin")
                    .toAbsolutePath().toUri().toURL();

            // Parent loads SPI, child looks up provider and its own metadata.
            try (URLClassLoader pluginLoader =
                    new URLClassLoader(new URL[] { pluginUrl }, hostLoader)) {
                System.out.println("explicit-plugin=" +
                        describe(ServiceLoader.load(
                                Greeting.class, pluginLoader)));

                thread.setContextClassLoader(pluginLoader);
                try {
                    System.out.println("tccl-plugin=" +
                            describe(ServiceLoader.load(Greeting.class)));
                } finally {
                    // Do not leak plugin loader into subsequent work.
                    thread.setContextClassLoader(hostLoader);
                }

                System.out.println("after-restore=" +
                        describe(ServiceLoader.load(Greeting.class)));
            }
        } finally {
            thread.setContextClassLoader(originalTccl);
        }
    }
}
```

No provider class is imported in the host. The host only knows `Greeting`, while the provider name lives in the `META-INF/services` resource.

### 5.2. Compiling and Running on Windows PowerShell

From the `demo/` directory, with JDK 17+ on `PATH`:

```powershell
New-Item -ItemType Directory -Force -Path build/api,build/host,build/plugin/META-INF/services | Out-Null
javac -d build/api src/api/demo/spi/Greeting.java
javac -cp build/api -d build/plugin src/plugin/demo/plugin/EnglishGreeting.java
Copy-Item src/plugin/META-INF/services/demo.spi.Greeting build/plugin/META-INF/services/demo.spi.Greeting
javac -cp build/api -d build/host src/host/demo/app/LoaderDemo.java
java -cp "build/api;build/host" demo.app.LoaderDemo
```

### 5.3. Equivalent Commands on Linux/macOS

```bash
mkdir -p build/api build/host build/plugin/META-INF/services
javac -d build/api src/api/demo/spi/Greeting.java
javac -cp build/api -d build/plugin src/plugin/demo/plugin/EnglishGreeting.java
cp src/plugin/META-INF/services/demo.spi.Greeting build/plugin/META-INF/services/demo.spi.Greeting
javac -cp build/api -d build/host src/host/demo/app/LoaderDemo.java
java -cp "build/api:build/host" demo.app.LoaderDemo
```

Note the class path separator: `;` on Windows, `:` on Linux/macOS. Run from the `demo/` directory because `Path.of("build/plugin")` is resolved relative to the working directory.

### 5.4. Exact Expected Stdout

```text
host-default=(none)
explicit-plugin=Hello, Java
tccl-plugin=Hello, Java
after-restore=(none)
```

**Line-by-line explanation:**

1. `host-default=(none)`: the host does not include `build/plugin` on the application class path; TCCL is temporarily set to `hostLoader`, so it cannot see the plugin resource/provider.
2. `explicit-plugin=Hello, Java`: the two-argument overload uses `pluginLoader`, which has a URL pointing to `build/plugin`. This loader sees the service configuration and loads `EnglishGreeting`; the `Greeting` class is shared via the parent.
3. `tccl-plugin=Hello, Java`: TCCL is temporarily set to `pluginLoader`; from there, the one-argument overload is equivalent to the two-argument overload using that same loader.
4. `after-restore=(none)`: TCCL has been restored to `hostLoader`, so the new discovery once again does not see the plugin. The two `finally` blocks guarantee thread context cleanup even on errors; `try-with-resources` closes `URLClassLoader`.

The program creates only **one provider** so stdout does not depend on multi-provider ordering. If an API allows multiple providers, you must define selection criteria based on metadata, capabilities, or priority; do not assume the first provider is stable across all environments.

## 6. Why Not Mechanically Choose the Loader Based on the "Current Class"?

In a framework, shared library classes may be defined by a parent loader, while service implementations belong to a child application. These three choices below can differ:

```java
// Loader that defines the API, usually suitable as parent to share the SPI.
ClassLoader apiLoader = Greeting.class.getClassLoader();

// Loader that defines the calling library class (may be at another layer).
ClassLoader libraryLoader = LoaderDemo.class.getClassLoader();

// Context loader attached to the thread by the caller / container.
ClassLoader contextLoader =
        Thread.currentThread().getContextClassLoader();
```

This is an **illustrative snippet** using class names from Section 5's example; it does not replace the program in Section 5. In the simple class-path example, `apiLoader` and `libraryLoader` are both the application loader. In a multi-tier container, `libraryLoader` might not be able to find plugin JARs; using it blindly causes the library to see fewer providers than the runtime intends.

**Clearly distinguish two questions:**

- *Which class counts as the same SPI?* Depends on the `Class<?>` passed in and its runtime identity (class name + defining loader).
- *Where to look for resources and implementations?* Depends on the class loader chosen for discovery, plus the JVM's delegation/module rules.

Both decisions must be compatible. Placing a duplicate copy of the API inside a plugin can make `EnglishGreeting` not a subtype of the `Greeting` seen by the host even though the class names look identical in logs.

## 7. Rules for Safely Setting and Restoring TCCL

TCCL is mutable per-thread state. If the runtime truly needs to set it temporarily (for example, a third-party API that only calls `ServiceLoader.load(Spi.class)`), make sure to **save the old value, set the context in the narrowest possible scope, and restore it with `finally`**.

An illustrative helper (place inside an appropriate class and import `java.util.function.Supplier`):

```java
static <T> T withContextLoader(
        ClassLoader selected,
        java.util.function.Supplier<T> action) {
    Thread thread = Thread.currentThread();
    ClassLoader previous = thread.getContextClassLoader();
    thread.setContextClassLoader(selected);
    try {
        return action.get();
    } finally {
        thread.setContextClassLoader(previous);
    }
}
```

Usage:

```java
String result = withContextLoader(pluginLoader, () ->
        ServiceLoader.load(Greeting.class)
                .findFirst()
                .map(g -> g.greet("Java"))
                .orElse("(none)"));
```

These two code blocks are **integration illustrations** within a scope that has `Greeting` and `pluginLoader`; the complete example in Section 5 compiles and runs standalone.

Do not use `setContextClassLoader` as a JVM-wide setting. With an executor that reuses threads, a task that forgets to restore will cause subsequent tasks to discover the wrong provider or hold references to an expired plugin loader. If your code already holds `pluginLoader`, the explicit overload is usually easier to control than mutating TCCL just to call a shorter overload.

**Note:** Java `ThreadLocal` and TCCL are two different mechanisms. A `CompletableFuture`, executor, or scheduler does not automatically guarantee propagating the right TCCL from one request to another task. Pass the loader explicitly or wrap the task in a restore scope when needed.

### TCCL Is Captured When Creating ServiceLoader

```java
// TCCL is currently hostLoader:
ServiceLoader<Greeting> captured =
        ServiceLoader.load(Greeting.class);

// Changing TCCL to pluginLoader afterward does not change the loader
// selected inside captured. To discover via pluginLoader, call
// ServiceLoader.load(Greeting.class, pluginLoader) again.
```

Do not assume the iterator reads the new TCCL each time `hasNext()` or `next()` is called. The `ServiceLoader` object already saved the loader context chosen at creation time.

## 8. Named Modules: Class Loader and Module Layer Are Not the Same Axis

Section 5's class-path example declares no modules. When moving to the Java Platform Module System (JPMS), a consumer in an **explicit named module** must declare `uses` for the service, and the provider module must declare `provides`.

Directional example (illustrative *module descriptors* only, not a standalone compilable source set):

```java
// module-info.java of the module containing the host
module demo.host {
    requires demo.spi;
    uses demo.spi.Greeting;
}
```

```java
// module-info.java of the module containing the provider
module demo.plugin {
    requires demo.spi;
    provides demo.spi.Greeting with demo.plugin.EnglishGreeting;
}
```

Module `demo.spi` in this layout needs `exports demo.spi;` so the host/provider can access the service type. In named modules, providers are specified via `provides`; do not assume the `META-INF/services` file from the class-path example fully replaces module configuration.

If the application creates plugins with their own `ModuleLayer`, you can choose:

```java
ServiceLoader<Greeting> providers =
        ServiceLoader.load(pluginLayer, Greeting.class);
```

This is a sketch assuming an existing `pluginLayer` variable and valid modules. This call finds providers in **named modules of the layer and its ancestors**, and does not find providers in unnamed modules. Conversely, the overload taking `ClassLoader` in JDK 17 can find named-module providers belonging to module layers related via loader/parent under JDK rules; it is not guaranteed to find only providers defined solely by that loader.

**When to use which?** If the runtime boundary is a URL/JAR loader for class-path plugins, the explicit-loader overload is more natural. If the boundary is a module layer created and managed by the runtime, consider the overload taking `ModuleLayer`. TCCL can still be useful for code using the default overload, but it is not a substitute name for a module layer.

## 9. Caching, Reloading, and Plugin Lifecycle

`ServiceLoader` caches the providers it has found/loaded inside **its own instance**. `iterator()` may return providers already instantiated in a previous traversal; `reload()` clears the cache and requests re-discovery on subsequent traversals.

Common misconceptions:

- `reload()` **does not turn an old class loader into one that can reload a different version of an already-defined class**. For hot-swapping plugin JARs, true hot reload may require a new loader/new layer and migrating all registrations, caches, resources, and references to the new version.
- After `reload()`, previous iterators/streams of the same `ServiceLoader` may become invalid; create a new iterator/stream. The Javadoc allows `ConcurrentModificationException` if an iterator is used after the cache has been cleared.
- A `ServiceLoader` instance is **not thread-safe**. Do not share and traverse the same instance across multiple threads without proper synchronization; it is usually easier to create an instance per discovery session.
- Do not cache `ServiceLoader.load(Spi.class)` in a singleton shared across all applications in the JVM when those applications have different TCCLs. That can return the wrong provider and retain class loader references long-term.
- `URLClassLoader.close()` closes resources owned by the loader such as open JARs/files; it **does not destroy provider instances**, does not close the plugin's business resources, and does not unload classes already defined by the JVM.
- On unload, the runtime must cancel provider callbacks/subscriptions, release references to providers/`ServiceLoader`/loader, restore TCCL to its previous context, and close the loader within the appropriate scope. A class loader can only be garbage-collected once no relevant strong references remain.

Because discovery is lazy, failures can occur during `findFirst()`, `iterator().hasNext()/next()`, `stream()` processing, or `Provider.get()`. Log enough detail—service type, loader identity, provider name, and metadata path if possible—rather than collapsing every failure into "provider not found".

## 10. Handling Discovery Errors and Distinguishing "Empty" from "Broken Configuration"

Three outcomes have different meanings:

1. **No valid provider found**: the iterator is exhausted, `findFirst()` returns `Optional.empty()`; the application picks a fallback or reports a missing feature depending on its contract.
2. **Provider configuration exists, but loading/instantiation fails**: you may receive a `ServiceConfigurationError` (for example wrong class name, unusable constructor, provider does not properly implement the SPI, corrupted metadata).
3. **Provider loads, but business logic fails**: callbacks/service methods throw their own exceptions; `ServiceLoader` is not an automatic business-error handling mechanism.

`ServiceConfigurationError` is a subclass of `Error`, so a normal `catch (RuntimeException)` **does not catch** it. When the runtime wants to report a configuration error with context, it can catch it specifically at the discovery boundary:

```java
try {
    Greeting provider = ServiceLoader
            .load(Greeting.class, pluginLoader)
            .findFirst()
            .orElseThrow(() ->
                    new IllegalStateException("No Greeting provider"));
    System.out.println(provider.greet("Java"));
} catch (java.util.ServiceConfigurationError failure) {
    throw new IllegalStateException(
            "Invalid Greeting provider configuration", failure);
}
```

This is an integration snippet using an existing `pluginLoader`, not a standalone program. Do not broadly catch `Throwable` to silently ignore failing providers; an invalid SPI configuration usually needs the deployment to be fixed. If you want to isolate a broken plugin so others can continue, publish a clear policy and test the iterator's recovery behavior, as the JDK does not guarantee the iterator can always skip a broken provider after every failure.

### Diagnosing Error Causes by Symptom

| Symptom | What to Check |
|---|---|
| `findFirst()` is empty even though JAR exists | Can TCCL/loader see the right resource? Is `build/plugin` actually on the URL/class path of the loader being used? |
| `ServiceConfigurationError: Provider ... not found` | Wrong provider name, missing class file, wrong package, missing dependency, visibility through parent |
| `... not a subtype` | Is there a duplicate SPI copy in another loader? Does the provider implement the host's exact `Greeting` class? |
| Constructor/provider method error | Check public no-args constructor requirement for class-path providers, init dependencies, root exception |
| Works from CLI, fails to see provider in executor/container | Print each thread's TCCL and the loader chosen when calling `ServiceLoader.load` |
| Still sees old provider after redeploy | Lingering `ServiceLoader` cache/reference to old loader? Was a new loader created and the old lifecycle closed? |
| `ConcurrentModificationException` after `reload()` | Iterators/streams created before reload must be discarded and recreated |
| Provider loads but fails cast | Verify shared SPI `Class` object and classloader delegation; do not just compare class names |

For diagnostics, you can print `Greeting.class.getClassLoader()`, `Thread.currentThread().getContextClassLoader()`, and the explicit loader in use. Do not rely on a loader's `toString()` string to judge unique identity; compare references or use identity in contextual logs.

## 11. Testing the Class Loader Selection Contract

For a plugin-capable runtime, you should have integration cases verifying the exact boundaries:

| Scenario | Expected Result |
|---|---|
| Host class path contains only API/host, plugin is in a separate loader | Default overload with host TCCL does not see the plugin |
| `load(Spi.class, pluginLoader)` with accurate metadata | Plugin provider is loaded; casting to host SPI succeeds |
| Set TCCL to plugin loader then use default overload | Provider matches explicit loader in a simple layout |
| Restore TCCL then call default overload again | Does not mistakenly retain the plugin loader |
| Create `ServiceLoader` before changing TCCL | Old instance still discovers according to the loader chosen at creation |
| Service resource exists but provider class is not visible | Reports configuration error, does not treat as a normal empty provider set |
| Plugin carries duplicate API copy defined by another loader | Detects class identity / assignability error |
| Multiple independent plugin loaders | Each discovery pass uses the right loader, without mixing providers outside the intended boundary |
| Reload/hot swap | Creates a new lifecycle and class loader when needed; does not retain old instances/resources |
| Thread pool handling multiple tasks | TCCL is restored even if a provider throws; no context leaks across tasks |

Do not assert a general ordering of providers across multiple modules/JARs when the JDK does not guarantee one; with multiple providers, sort or select using application rules after discovery.

## 12. Practical Implementation Rules

- **Choose the loader owner:** The runtime creates/manages plugin loaders; libraries should not arbitrarily use `ClassLoader.getSystemClassLoader()` if the container provides a different boundary.
- **Choose the overload by contract:** Pass explicitly if you hold the loader; rely on TCCL only when you know who sets and restores it; use `ModuleLayer` for discovery scoped to a named module layer.
- **Keep one shared SPI:** Host and plugin must see the same contract class; provider implementations may live in separate loaders/layers.
- **Verify packaging:** Correct `META-INF/services/<SPI>` in the class-path output or `uses/provides` in the module descriptor, provider actually loadable, compatible constructor/provider method.
- **Manage lifecycle:** `ServiceLoader` caches and is not thread-safe; hot reload requires handling references, active subscriptions, resources, and class loaders, not just calling `reload()`.
- **Make results measurable:** Test found, not-found, misconfigured, thread-pool context-switching, and unload/redeploy cases.

Standard references to check against: [Java SE 17 `ServiceLoader` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html) and [Java SE 17 `ClassLoader` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html). These two APIs define the exact overloads, module discovery, caching, errors, and TCCL contract.
