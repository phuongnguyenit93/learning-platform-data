# The Role of the Thread Context Class Loader in SPI and Integration Libraries

## 1. What Problem Does the TCCL Solve?

In a plugin-extensible application, the service interface (SPI) is typically loaded by the host's classloader, while the service implementation class resides in a JAR loaded later by a different classloader. A shared library does not know the list of plugins in advance, and the library's own classloader may not be able to see the new JARs.

The **Thread Context Class Loader (TCCL)** is a `ClassLoader` reference attached to the current thread. Java provides two methods:

```java
ClassLoader context = Thread.currentThread().getContextClassLoader();
Thread.currentThread().setContextClassLoader(context);
```

This is an illustrative snippet, not a standalone program. The host can set the TCCL to a classloader that sees the plugin when calling a library that needs to discover providers. If the library uses the TCCL, discovery operates based on the **caller's context** instead of relying solely on the classloader that originally loaded the library.

Keep in mind: the TCCL **does not automatically load all plugins**, does not change which loader defined a class, and does not automatically invoke plugin activation methods. It merely specifies a lookup source when the corresponding API chooses to use that reference.

## 2. Relationship Between Host, SPI, Plugin, and Classloaders

```text
Thread calling the library
    |
    +---- TCCL ----------------------+
                                      |
                                      v
                    pluginLoader (URLClassLoader)
                    - plugin.jar
                    - provider implementation
                    - META-INF/services/...
                                      |
                                  parent-first
                                      |
                                      v
                    host/application loader
                    - service interface (SPI)
                    - host
                    - library using SPI
```

With a parent-first delegation structure, a child loader can ask the parent loader to locate the SPI type, whereas the parent loader generally cannot see provider classes sitting inside the child's JAR. If a library on the parent side looks up only through its own classloader, providers will be missed. The TCCL is the mechanism for the host to hand the library a different loader that can see the providers.

Separate three concepts:

- **Defining classloader of a type:** the JVM identifies a class by its binary name and the loader that defined it. Two classes with the same name defined by two different loaders can be two distinct types.
- **Lookup classloader:** when `loadClass` or `getResources` is called, the delegation chain determines what is found.
- **TCCL:** a reference stored on a thread; a library may choose to retrieve it as its lookup loader.

Changing the TCCL does not change the result of `Greeter.class.getClassLoader()`. The SPI contract must be properly shared so the provider can be cast to the type expected by the host.

## 3. How Do SPI APIs Use the TCCL?

In Java SE 17, the call:

```java
ServiceLoader<Greeter> services = ServiceLoader.load(Greeter.class);
```

uses the **calling thread's context class loader**. For classpath SPI, the corresponding loader must see the registration resource named:

```text
META-INF/services/demo.spi.Greeter
```

and the UTF-8 file content listing the fully qualified binary name of the provider:

```text
demo.plugin.WelcomeGreeter
```

The filename follows the **service type**, not the provider. The classloader must see both the registration resource and all required dependency classes.

If the host already knows which loader it wants to use, it can call the explicit overload:

```java
ServiceLoader<Greeter> services =
        ServiceLoader.load(Greeter.class, pluginLoader);
```

Both snippets are isolated examples assuming `Greeter` and `pluginLoader` already exist.

| Call Form | Loader Used for Discovery | Points to Note |
|---|---|---|
| `ServiceLoader.load(Greeter.class)` | TCCL at the time the ServiceLoader is created | Depends on the current thread's context |
| `ServiceLoader.load(Greeter.class, pluginLoader)` | Directly passed loader | Explicit, easy to control when the host owns the loader |
| `Greeter.class.getClassLoader()` | Loader that defined the SPI type | May be a parent loader, unable to see providers in child loaders |
| `ClassLoader.getSystemClassLoader()` | System classloader | Does not automatically know about dynamically loaded JARs |

`ServiceLoader.load(...)` creates a discovery object; providers are usually located and instantiated **lazily** when iterating, calling `findFirst()`, or using `stream()`. A `ServiceLoader` caches discovered providers and holds onto its own loader. Changing the TCCL after creating the `ServiceLoader` object does not cause that object to switch to the new loader. `reload()` clears the provider cache inside `ServiceLoader`, but does not automatically add JARs to a classloader.

With **named modules** in JPMS, `uses`/`provides ... with ...` and module layers also participate in discovery. The hands-on section below uses the classpath to isolate and clarify the effect of the TCCL.

## 4. Runnable Java 17 Example: One SPI, Two Contexts

We place `Greeter` and the host on the application classpath; the provider's JAR is **not** on the application classpath. The host opens the JAR itself using `URLClassLoader`, then compares three lookups: default TCCL, TCCL switched to `pluginLoader`, and an explicitly passed loader.

### Project Structure

```text
tccl-demo/
├── api/src/demo/spi/Greeter.java
├── host/src/demo/host/Main.java
└── plugin/
    ├── src/demo/plugin/WelcomeGreeter.java
    └── resources/META-INF/services/demo.spi.Greeter
```

**Contract** at `api/src/demo/spi/Greeter.java`:

```java
package demo.spi;

public interface Greeter {
    String greet(String name);
}
```

**Provider** at `plugin/src/demo/plugin/WelcomeGreeter.java`:

```java
package demo.plugin;

import demo.spi.Greeter;

public final class WelcomeGreeter implements Greeter {
    public WelcomeGreeter() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

**Registration file** `plugin/resources/META-INF/services/demo.spi.Greeter` with exact content:

```text
demo.plugin.WelcomeGreeter
```

The provider class is `public`, has a `public` no-arg constructor, and implements the service interface to conform to classpath SPI rules.

**Host** at `host/src/demo/host/Main.java`:

```java
package demo.host;

import demo.spi.Greeter;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ServiceLoader;

public final class Main {
    private static String status() {
        return ServiceLoader.load(Greeter.class)
                .findFirst()
                .isPresent() ? "found" : "none";
    }

    public static void main(String[] args) throws Exception {
        Path jar = Path.of("plugins", "greeter-plugin.jar").toAbsolutePath();
        Thread current = Thread.currentThread();
        ClassLoader previous = current.getContextClassLoader();

        try (URLClassLoader pluginLoader = new URLClassLoader(
                new URL[] {jar.toUri().toURL()},
                Greeter.class.getClassLoader())) {

            System.out.println("before=" + status());
            System.out.println("descriptor=" + (pluginLoader.getResource(
                    "META-INF/services/demo.spi.Greeter") != null));

            current.setContextClassLoader(pluginLoader);
            try {
                Greeter provider = ServiceLoader.load(Greeter.class)
                        .findFirst()
                        .orElseThrow();
                System.out.println("context=" + provider.greet("Java"));
            } finally {
                current.setContextClassLoader(previous);
            }

            Greeter explicit = ServiceLoader.load(
                    Greeter.class, pluginLoader).findFirst().orElseThrow();
            System.out.println("explicit=" + explicit.greet("Java"));
            System.out.println("restored=" + status());
        }
    }
}
```

The host uses `Greeter.class.getClassLoader()` as the **parent loader** of `pluginLoader` so both sides share the same `Greeter` class. Thus returning a provider of type `Greeter` works. `getResource` verifies the descriptor is visible before instantiating the provider. The `finally` block restores the TCCL even if plugin discovery/instantiation fails. `try-with-resources` closes the `URLClassLoader` upon leaving scope.

### Compile and Run Commands on Windows PowerShell with JDK 17+

Run from the `tccl-demo` directory:

```powershell
New-Item -ItemType Directory -Force -Path out\api,out\host,out\plugin,plugins | Out-Null

javac -d out\api api\src\demo\spi\Greeter.java
javac -cp out\api -d out\plugin plugin\src\demo\plugin\WelcomeGreeter.java
javac -cp out\api -d out\host host\src\demo\host\Main.java

Copy-Item -Path plugin\resources\META-INF -Destination out\plugin -Recurse
jar --create --file plugins\greeter-plugin.jar -C out\plugin .

java -cp "out\api;out\host" demo.host.Main
```

**Stdout output** with the exact example structure:

```text
before=none
descriptor=true
context=Hello, Java
explicit=Hello, Java
restored=none
```

- `before=none`: the application thread's default TCCL does not yet see the plugin JAR outside `-cp`.
- `descriptor=true`: the new `pluginLoader` sees `META-INF/services/demo.spi.Greeter` inside the JAR.
- `context=Hello, Java`: after setting TCCL to `pluginLoader`, the default `ServiceLoader` overload discovers the provider.
- `explicit=Hello, Java`: the overload taking `pluginLoader` directly still works even after TCCL has been restored.
- `restored=none`: the host returns to its old context, and a new lookup using the old TCCL does not see the provider.

On macOS/Linux, replace the classpath separator `;` with `:` and use equivalent shell syntax for creating directories and copying. Do not add `plugins/greeter-plugin.jar` to `-cp` in this experiment: adding it would let the default loader see the provider too, obscuring the distinction between the two contexts.

### Three Modifications to Observe Yourself

1. **Remove `setContextClassLoader(pluginLoader)`:** `ServiceLoader.load(Greeter.class).findFirst().orElseThrow()` cannot find the provider in the example and throws `NoSuchElementException`. The overload taking `pluginLoader` still works.
2. **Change the parent loader to one that cannot see `Greeter`:** even if the provider class is found, dependency errors or SPI type mismatches can arise. Sharing the contract classloader is a separate requirement from setting the TCCL.
3. **Remove `META-INF/services` from the JAR:** `descriptor=false`, and no provider is declared to classpath `ServiceLoader` even though `WelcomeGreeter.class` exists.

These modifications only verify how **provider discovery** works; they do not represent the full plugin lifecycle or hot JAR updates.

## 5. Which Integration Libraries Use the TCCL?

TCCL was designed to be useful for discovery mechanisms orchestrated by a **shared library** where the **application** supplies implementations. Besides `ServiceLoader`, a classic example is `javax.script.ScriptEngineManager`:

```java
// Illustrative snippet; assumes pluginLoader is already declared.
var managerA = new javax.script.ScriptEngineManager();
var managerB = new javax.script.ScriptEngineManager(pluginLoader);
```

The no-arg constructor of `ScriptEngineManager` uses the context class loader to discover script engine factories; the other constructor uses the provided loader. JDK 17 does not guarantee a built-in JavaScript engine, so the example above **does not claim** a specific engine will be found. Availability depends on actual providers in the runtime environment.

In integration platforms and application servers, frameworks may temporarily set the TCCL before invoking a library or extension and restore it afterward. However:

- Not **every** library, resource lookup API, or logging library reads the TCCL.
- A library may prioritize system properties, config files, modules, its own classloader, or an overload taking an explicit loader.
- `Class.getResource(...)`, `ClassLoader.getResources(...)`, and `ServiceLoader` are not three equivalent lookup mechanisms.
- You must read the **specific library's** contract to determine when the TCCL is sampled and whether it caches results.

TCCL is not an API for passing business data between host and plugin. It only adjusts the **class/resource loading context** for components that choose to use it.

## 6. Thread Inheritance and Reuse: Why Must You Restore the TCCL?

The TCCL belongs to the **execution thread**, not automatically to a specific request, task, or session. Newly created threads typically inherit the context class loader from their creator thread; thread pools reuse a single thread across many tasks.

If task A switches the TCCL to plugin A's loader and forgets to restore it, task B running on the same worker thread may mistakenly see plugin A's providers. The TCCL also retains a reference to the old classloader, making plugin reclamation harder.

A small pattern using `try/finally`:

```java
// Illustrative helper; place inside a class and import java.util.function.Supplier.
static <T> T withContextLoader(
        ClassLoader wanted,
        java.util.function.Supplier<T> action) {
    Thread thread = Thread.currentThread();
    ClassLoader old = thread.getContextClassLoader();
    thread.setContextClassLoader(wanted);
    try {
        return action.get();
    } finally {
        thread.setContextClassLoader(old);
    }
}
```

Use this pattern **inside the task itself running on the thread that performs the lookup**. Setting the TCCL on a submitting thread does not automatically propagate to executor threads that were already created. `CompletableFuture` and asynchronous callbacks do not automatically guarantee loader context propagation across every boundary either.

If a library allows passing a classloader such as `ServiceLoader.load(service, loader)`, passing it explicitly is usually easier to understand and test than mutating the thread's TCCL. When forced to use the TCCL, keep its scope very short and always restore the original context.

## 7. Diagnosing Failures When a Plugin Is Not Discovered

| Symptom | What to Check |
|---|---|
| `ServiceLoader.load(service)` returns empty | Current TCCL; `META-INF/services` name/path; whether the JAR is visible to the loader |
| Overload passing `pluginLoader` finds provider, default overload does not | TCCL differs from `pluginLoader`; set it at the right call site |
| Descriptor exists but throws `ServiceConfigurationError` | Provider class name, constructor/factory, bytecode, dependencies, SPI compatibility |
| `ClassCastException` or "not a subtype" error | Provider and host may be using two copies of the same-named interface defined by different loaders |
| `NoClassDefFoundError` or `NoSuchMethodError` | Missing dependency classes/libraries or incompatible runtime versions |
| Subsequent task sees the wrong provider | TCCL on thread pool was not restored; unmanaged provider cache |
| Old plugin JAR is hard to reclaim | `URLClassLoader`, threads, `ThreadLocal`, caches, callbacks, or instances still hold references |

A diagnostic snippet inside a method handling `IOException`:

```java
ClassLoader tccl = Thread.currentThread().getContextClassLoader();
System.out.println("TCCL=" + tccl);

String path = "META-INF/services/" + Greeter.class.getName();
if (tccl != null) {
    var urls = tccl.getResources(path);
    while (urls.hasMoreElements()) {
        System.out.println(urls.nextElement());
    }
}
```

This snippet assumes `Greeter` is in scope; it is not a standalone program. URL contents and classloader `toString()` representations vary by environment. `getResources` may find multiple descriptors with the same name from different JARs.

Merely checking `getResource(...) != null` **does not prove** the provider is valid: the file may declare a non-existent class or one that cannot be instantiated. Conversely, not seeing the descriptor with **one** loader does not prove every loader fails to see it.

## 8. Limitations and Design Principles

- **Separate discovery from activation:** finding a provider does not mean the host has called `start()` or accepted it for business use. Static initializers and the provider's constructor may run when actually instantiating it.
- **Type compatibility:** ensure host and plugin share the same service type identity; do not package a private copy of the API and expect the host to cast to another copy.
- **Lifecycle management:** `URLClassLoader.close()` does not immediately unload all loaded classes. If references to the loader, providers, `ThreadLocal`, caches, or threads remain, they can continue to stay alive.
- **Keep context scoped to the thread:** set the TCCL where calling the library and restore it via `finally`, even if errors occur.
- **Do not use TCCL as an isolation mechanism:** TCCL does not grant permissions, check trust, or automatically resolve library version conflicts. Those require dedicated plugin management mechanisms.
- **Prefer explicit parameters:** when you control the code calling `ServiceLoader`, use the overload accepting a loader to avoid relying on implicit thread state.

## 9. Questions and Practice

1. **Why can't a parent loader usually see providers in a child loader?** Because parent-first delegation lets the child look up to the parent, without automatically creating reverse lookup from parent to child. The TCCL tells a library which loader sees the plugin when the library chooses to read the TCCL.
2. **Does changing the TCCL change `Greeter.class.getClassLoader()`?** No; the defining loader is an immutable property of an already-defined class.
3. **Which `ServiceLoader` overload depends less on hidden context?** `load(service, loader)` because the loader is passed directly.
4. **Why does the example print `descriptor=true` while `before=none`?** Because the two checks use two different loaders: `pluginLoader` sees the resource, while the default TCCL does not yet see the plugin JAR.
5. **What happens if a task in a thread pool fails to restore the TCCL?** Subsequent tasks may mistakenly use the old `pluginLoader` and keep that loader alive longer.
6. **Does `reload()` automatically add new JARs to `URLClassLoader`?** No. It refreshes `ServiceLoader`'s internal cache, while the classpath/classloader must be managed separately.
7. **Should TCCL be considered a fix for `ClassCastException` between two copies of a service interface?** No. You must fix the API boundary and class identity.

**Practice:** run the example, try removing the `setContextClassLoader` call, try calling the loader-accepting overload in different places, and then move the discovery step into a task on an `ExecutorService`. Print the TCCL **inside the task** to clearly observe the worker thread's actual context.

## References

- Java SE 17 — `Thread.getContextClassLoader`, `Thread.setContextClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
- Java SE 17 — `ServiceLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Java SE 17 — `URLClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- Java SE 17 — `ScriptEngineManager`: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html