# Scope of `ServiceLoader.loadInstalled` and How It Differs from Application Providers

## 1. The Problem: "Installed" Does Not Mean "Added to the Application"

`ServiceLoader` is Java's API for **discovering providers** of a service (typically an interface or abstract class). Providers can live in the JDK/runtime, in an application dependency, on the application module path, or in plugin JARs loaded by the application itself. Where a provider is "present" determines the appropriate lookup method.

In Java 17+, `ServiceLoader.loadInstalled(Service.class)` has a **very narrow** meaning: it creates a `ServiceLoader` using the **platform class loader**. By API contract, it only searches for providers installed into the Java runtime environment within this loader's scope; **providers placed solely on the application classpath or application module path are not found by this method**.

These two expressions are equivalent:

~~~java
ServiceLoader.loadInstalled(MyService.class);

ServiceLoader.load(
    MyService.class,
    ClassLoader.getPlatformClassLoader()
);
~~~

Meanwhile:

~~~java
ServiceLoader.load(MyService.class);
~~~

uses the **thread context class loader (TCCL)** at the time of the call, which is typically the application/system class loader when an application runs normally. Therefore, `load` usually finds application providers that `loadInstalled` intentionally skips.

> **Key point:** `loadInstalled` does **not** mean "scan every dependency installed by Maven/Gradle", "scan every running JAR", "scan the `plugins/` folder", or "automatically find every application provider". It is a specific **class loader scope** choice.

## 2. Which Class Loader Is Used?

Under a typical startup configuration, the delegation relationship is usually visualized as follows:

~~~text
Bootstrap class loader (often represented as null)
          |
Platform class loader
          |
Application/System class loader
          |
Custom/plugin class loader (if created by the app, usually parent-first)
~~~

This is an intuitive diagram of common parent relationships, not the sole rule for all custom class loaders. With JPMS, `ServiceLoader` also has rules for finding providers from **named modules** and **module layers**; you should not reason solely from the legacy model's class-lookup order.

- **Bootstrap:** loads essential foundational classes; in Java a class's loader can be inspected via `Class#getClassLoader()`, which may return `null`.
- **Platform:** `ClassLoader.getPlatformClassLoader()`, provides most classes belonging to appropriate platform modules; **not** the application/system loader.
- **Application/System:** `ClassLoader.getSystemClassLoader()`, usually the loader for application code launched via `java -cp`; also plays a role for application named modules in the boot layer.
- **TCCL:** `Thread.currentThread().getContextClassLoader()`, a property of the thread. Its value **can vary by thread/framework**, so you should not assume every call to `load(Service.class)` uses the system loader.
- **Custom/plugin loader:** created by the application to bring JARs into class lookup; for `ServiceLoader` to discover providers via this loader, the application must pick the appropriate overload.

For Java 17+, this can be summarized as:

| Call | Primary Search Source | Providers on Application Classpath | Application Named-Module Providers |
|---|---|---|---|
| `ServiceLoader.load(S.class)` | Current thread's TCCL | Yes, **if** TCCL sees the service configuration and provider | Yes, if the loader/module layer scope permits |
| `ServiceLoader.load(S.class, loader)` | Specified loader and corresponding provider discovery mechanism | Yes, if the loader sees them | Yes, per named-module rules and layers associated with the loader |
| `ServiceLoader.loadInstalled(S.class)` | **Platform class loader** | **No** | **No** for providers on the application module path |
| `ServiceLoader.load(layer, S.class)` | Named modules in `layer` and parent layers | **No** lookup for providers in unnamed modules/classpath | Yes, if the named module has been resolved in the traversed layers |

This table describes **discoverability**, not a guarantee that a provider exists. Even with the right overload, `ServiceLoader` requires provider registration metadata, resolved modules, compatible types, and proper access permissions.

### Misleading Terminology

- "JAR installed into the application" does not mean an "installed provider" for `loadInstalled`.
- "Provider in the boot layer" does not mean "provider in the platform loader": the boot layer can contain application modules defined by the application loader.
- "JAR is already on the module path" does not automatically ensure that module is **resolved**; `requires`, `--add-modules`, or another binding mechanism may be needed.
- "Provider is in the plugin directory" does not mean the class loader in use is configured to read that directory.

## 3. How Are Application Providers Declared?

### 3.1. Providers on the Classpath (Unnamed Module)

A service such as:

~~~java
package demo.spi;

public interface GreetingService {
    String greet();
}
~~~

can have an implementation in a JAR or classpath directory. The provider is registered via the resource:

~~~text
META-INF/services/demo.spi.GreetingService
~~~

The file contains implementation class names (one per line):

~~~text
demo.impl.LocalGreetingService
~~~

`ServiceLoader.load(GreetingService.class)` usually finds this file via TCCL. `ServiceLoader.load(GreetingService.class, loader)` searches via the specified loader. Conversely, `loadInstalled` does not search resources/providers present only on the application classpath.

Note: merely **implementing the interface** is not enough to be discovered; valid metadata is required. Conversely, if the provider configuration resource is present but the provider class cannot be loaded by the loader, or is incompatible with the service, iteration may fail with `ServiceConfigurationError`.

### 3.2. Providers on the Application Module Path (Named Module)

For named modules, the service and provider are declared using `module-info.java`:

~~~java
// Host / consumer module
module demo.host {
    requires demo.spi;
    uses demo.spi.GreetingService;
}
~~~

~~~java
// Provider module
module demo.provider {
    requires demo.spi;
    provides demo.spi.GreetingService
        with demo.provider.LocalGreetingService;
}
~~~

`uses` declares that the module needs to discover the service; `provides ... with ...` declares the provider. The provider module must be **resolved** into the module graph. `ServiceLoader.load(...)` or `load(ModuleLayer.boot(), ...)` can find this provider if the respective conditions are met, but `loadInstalled` still ignores providers present only on the **application module path**.

When the caller is an explicit named module, missing `uses` for the service can cause the `ServiceLoader` call to throw `ServiceConfigurationError`. Do not try to work around this error by blindly switching to `loadInstalled`.

## 4. Runnable Example: Application Provider on the Classpath

This example uses Java 17+ and has only **one provider**, so the output has a deterministic order. It demonstrates on the very same service: `load` sees the provider, `loadInstalled` does not.

Create the following directory structure:

~~~text
demo-classpath/
  src/
    demo/
      spi/
        GreetingService.java
      impl/
        LocalGreetingService.java
      App.java
  out/
    META-INF/
      services/
        demo.spi.GreetingService
~~~

`src/demo/spi/GreetingService.java`:

~~~java
package demo.spi;

public interface GreetingService {
    String greet();
}
~~~

`src/demo/impl/LocalGreetingService.java`:

~~~java
package demo.impl;

import demo.spi.GreetingService;

public final class LocalGreetingService implements GreetingService {
    @Override
    public String greet() {
        return "Hello from application";
    }
}
~~~

`src/demo/App.java`:

~~~java
package demo;

import demo.spi.GreetingService;
import java.util.ServiceLoader;

public final class App {
    public static void main(String[] args) {
        System.out.println("context=" + names(
                ServiceLoader.load(GreetingService.class)));

        System.out.println("system=" + names(ServiceLoader.load(
                GreetingService.class, ClassLoader.getSystemClassLoader())));

        System.out.println("installed=" + names(
                ServiceLoader.loadInstalled(GreetingService.class)));

        System.out.println("platform=" + names(ServiceLoader.load(
                GreetingService.class, ClassLoader.getPlatformClassLoader())));
    }

    private static String names(ServiceLoader<GreetingService> services) {
        return services.stream()
                .map(provider -> provider.type().getName())
                .toList()
                .toString();
    }
}
~~~

Create the file `out/META-INF/services/demo.spi.GreetingService` with **exact** content:

~~~text
demo.impl.LocalGreetingService
~~~

From the `demo-classpath/` directory, using Bash (Linux/macOS or Git Bash):

~~~bash
mkdir -p out/META-INF/services

printf '%s\n' 'demo.impl.LocalGreetingService' \
  > out/META-INF/services/demo.spi.GreetingService

javac -d out \
  src/demo/spi/GreetingService.java \
  src/demo/impl/LocalGreetingService.java \
  src/demo/App.java

java -cp out demo.App
~~~

Output with this example setup:

~~~text
context=[demo.impl.LocalGreetingService]
system=[demo.impl.LocalGreetingService]
installed=[]
platform=[]
~~~

**Line-by-line explanation:**

1. `context`: `load(S.class)` uses TCCL. The standard Java launcher assigns the system/application loader as TCCL, so it finds the `META-INF/services/...` resource in `out`.
2. `system`: explicitly passes the system class loader, still finds the provider.
3. `installed`: uses the platform class loader. The provider is only on the application classpath, so the result is empty.
4. `platform`: uses the platform loader itself explicitly; the result matches `loadInstalled`, demonstrating equivalence of the two calls.

`stream().map(provider -> provider.type().getName())` here lists **provider types** without calling `Provider.get()` to instantiate them. If you want to invoke provider behavior, iterate `GreetingService` objects with `iterator()` or call `Provider.get()`.

**Important condition for this output:** the descriptor file must be placed into `out/META-INF/services/` before running and classpath `out` must be used; the example uses a custom application provider and does not assume the JDK has a built-in provider for this service. If `META-INF/services/...` is missing, both `context` and `system` will also be empty.

On Windows CMD/PowerShell, the multi-line `javac` command must be converted to a single line or the corresponding shell's line-continuation syntax. The example above uses a single classpath entry, so no `:`/`:` vs `;` separator difference arises.

## 5. Runnable Example: Application Provider on the Module Path

Not just classpath: `loadInstalled` is also **not** for discovering providers on the application module path. This example uses three named modules to separate the service API from the host and provider.

Directory tree:

~~~text
demo-modules/
  src/
    demo.spi/
      module-info.java
      demo/spi/GreetingService.java
    demo.provider/
      module-info.java
      demo/provider/LocalGreetingService.java
    demo.host/
      module-info.java
      demo/host/Main.java
~~~

`src/demo.spi/module-info.java`:

~~~java
module demo.spi {
    exports demo.spi;
}
~~~

`src/demo.spi/demo/spi/GreetingService.java`:

~~~java
package demo.spi;

public interface GreetingService {
    String greet();
}
~~~

`src/demo.provider/module-info.java`:

~~~java
module demo.provider {
    requires demo.spi;
    provides demo.spi.GreetingService
        with demo.provider.LocalGreetingService;
}
~~~

`src/demo.provider/demo/provider/LocalGreetingService.java`:

~~~java
package demo.provider;

import demo.spi.GreetingService;

public final class LocalGreetingService implements GreetingService {
    @Override
    public String greet() {
        return "Hello from application module";
    }
}
~~~

`src/demo.host/module-info.java`:

~~~java
module demo.host {
    requires demo.spi;
    uses demo.spi.GreetingService;
}
~~~

`src/demo.host/demo/host/Main.java`:

~~~java
package demo.host;

import demo.spi.GreetingService;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        System.out.println("load=" + names(
                ServiceLoader.load(GreetingService.class)));

        System.out.println("installed=" + names(
                ServiceLoader.loadInstalled(GreetingService.class)));

        System.out.println("bootLayer=" + names(
                ServiceLoader.load(ModuleLayer.boot(), GreetingService.class)));
    }

    private static String names(ServiceLoader<GreetingService> loader) {
        return loader.stream()
                .map(p -> p.type().getName())
                .toList()
                .toString();
    }
}
~~~

Compile and run at `demo-modules/` on Bash:

~~~bash
mkdir -p mods
javac --module-source-path src -d mods \
  $(find src -type f -name '*.java')

java --module-path mods \
  --add-modules demo.provider \
  --module demo.host/demo.host.Main
~~~

Output:

~~~text
load=[demo.provider.LocalGreetingService]
installed=[]
bootLayer=[demo.provider.LocalGreetingService]
~~~

**Why are they different?**

- `demo.provider` is placed on the application module path and is **resolved** thanks to `--add-modules demo.provider`. `module-info.java` supplies the `provides` metadata; the host declares `uses`.
- `load(S.class)` runs with the default TCCL in this example and discovers the application module provider.
- `load(ModuleLayer.boot(), S.class)` traverses named modules in the boot layer and parent layers. Because the provider was resolved into the boot layer, it is found. This overload **does not** find providers in unnamed modules/classpath.
- `loadInstalled(S.class)` selects the **platform class loader**, and does not accept application module-path providers merely because the provider is present in the boot layer.

Take care to distinguish the **boot layer** from the **bootstrap/platform class loader**: the two concepts are module graph scope and class-loading mechanism, and are not interchangeable. An application module can reside in the boot layer while still falling outside the discovery scope of `loadInstalled`.

If `--add-modules demo.provider` is omitted and nothing else causes the provider module to be resolved, do not assume the provider module joined the graph just because its files sit in `mods/`. Root selection and service binding affect the outcome.

## 6. What to Use When Discovering Dynamically Loaded Plugins at Runtime?

An application with a `plugins/` directory can scan JARs itself, create the appropriate loader/layer, and use the corresponding provider discovery overload. `loadInstalled` **does not** scan this directory and **does not** create new class loaders.

### Classpath-Style Plugin JARs

If the host loads JARs with `URLClassLoader` and the `GreetingService` service API is provided by a shared parent loader:

~~~java
// Integration snippet example, not a standalone program.
// pluginUrls is a URL[] of plugin JARs already validated by the host.
try (URLClassLoader pluginLoader =
             new URLClassLoader(pluginUrls,
                                GreetingService.class.getClassLoader())) {
    ServiceLoader<GreetingService> discovered =
            ServiceLoader.load(GreetingService.class, pluginLoader);

    for (GreetingService provider : discovered) {
        System.out.println(provider.greet());
    }
}
~~~

You need to import `java.net.URLClassLoader` and `java.util.ServiceLoader`, as well as use the shared API and configured `pluginUrls`. A real host must keep the loader alive while providers remain active; `close()` should only be called after stopping the plugin and releasing resources.

Prefer specifying the loader explicitly when providers belong to a dedicated plugin. If `load(S.class)` is used while TCCL is a different loader, failing to see the plugin is expected to happen. Changing TCCL yourself may be necessary in some frameworks, but you must restore the old state in `finally` and consider the impact on other code running on the same thread.

### Plugins as Named Modules in a New Module Layer

If the host resolves plugins into an application-created `ModuleLayer`:

~~~java
// Integration snippet, assuming pluginLayer has been created and
// GreetingService is the shared API used by both host and plugin.
ServiceLoader<GreetingService> discovered =
        ServiceLoader.load(pluginLayer, GreetingService.class);
~~~

The `load(layer, service)` overload discovers providers only in **named modules** of the layer and its parent layers; it does not replace reading `META-INF/services` in JARs that are unnamed modules. The host must control module resolution, shared APIs, dependencies, class identity, and plugin lifecycle.

### Purpose Comparison

| Requirement | Appropriate Approach |
|---|---|
| Find providers present on the application's classpath | `ServiceLoader.load(S.class)` when TCCL is right, or `load(S.class, applicationLoader)` |
| Find providers in JARs loaded by a custom loader | `ServiceLoader.load(S.class, pluginLoader)` |
| Find providers of named modules in an existing layer | `ServiceLoader.load(layer, S.class)` |
| Intentionally restrict search to "installed" providers visible through the platform loader | `ServiceLoader.loadInstalled(S.class)` |
| Directory scanning, version checks, install/uninstall, isolation, and replacing plugins | **Application plugin manager**; using the overloads above as one step in the process |

A plugin manager typically needs to separate **JAR discovery**, **code loading**, **service discovery**, **provider instantiation**, **host registration**, and **stopping and unloading**. `ServiceLoader` solves the metadata-based provider discovery/instantiation part; it does not supply a full plugin installation lifecycle.

## 7. Why Is It Still Named `loadInstalled`? Perspective from Java 8 to Java 9+

In JDK 8 and earlier, Java had the **extension mechanism** (for example the `jre/lib/ext` directory). The interpretation of "installed provider" back then was tied to the extension class loader and extension JARs installed into the runtime.

Since JDK 9, the extension mechanism has been removed and the Java runtime is organized around modules. `loadInstalled` **still exists**, but in Java 17+ it is specified in terms of the **platform class loader**:

~~~java
ClassLoader.getPlatformClassLoader()
~~~

Thus two false inferences must be avoided:

1. **Do not** copy JARs into `JAVA_HOME/lib/ext` or configure `java.ext.dirs` to "install providers" on modern JDKs. The old extension mechanism is no longer supported; application libraries need classpath/module path declarations or a plugin manager.
2. **Do not** treat `loadInstalled` as a list of all providers loaded by the JVM. It restricts the search to the platform loader; in a normal Java application, the result can be empty even when `load(S.class)` returns an active provider.

The name "installed" is a historical API term; technical decisions must rely on the current class-loader contract, not on the everyday meaning of the word "installed".

## 8. Lazy Search, Caching, and Errors

`ServiceLoader` overloads first **create a service loader object**. Providers are located and/or instantiated **on demand** while traversing `iterator()`, `stream()`, `findFirst()`, or `Provider.get()`. This has the following consequences:

- Calling `loadInstalled(S.class)` without iterating does not let you accurately conclude how many providers were found. When testing, consume the results.
- `stream()` returns `ServiceLoader.Provider<S>` so you can inspect `type()` and then select a provider; only `get()` retrieves or creates the instance. `iterator()` directly returns provider instances.
- `ServiceLoader` caches loaded providers. `reload()` clears **the cache of the `ServiceLoader` object itself**; it does not add new JARs to the classpath, does not turn the platform loader into the application loader, does not mutate the module graph, and does not unload classes.
- Provider ordering across named modules is not uniformly guaranteed between modules; a system with multiple providers should not pick one just by "the first element" if ordering is a business requirement.
- Finding no providers and **provider failure** are two different situations: the first can return an empty list; a bad descriptor, missing class, invalid constructor/provider method, or initialization failure can throw `ServiceConfigurationError` during traversal.
- `ServiceLoader` and providers should not be arbitrarily shared across threads while concurrently mutating the cache. Design initialization, reload, and instance management according to the application's own lifecycle.

A common mistake is trying `reload()` when the real cause is **the wrong class loader scope**. For a provider located only on the application classpath/module path, calling `reload()` on an object created via `loadInstalled` still will not find that provider.

## 9. Diagnosing When `loadInstalled` Returns Empty

| Symptom | What to Verify | Appropriate Action |
|---|---|---|
| `load(S.class)` has providers, `loadInstalled(S.class)` is empty | Does the provider belong to the application classpath/module path? | This is a normal scope difference; use the appropriate `load` |
| Both are empty | Are `META-INF/services` or `provides` metadata correct? Is the module resolved? | Check descriptors, module graph, and actual loader |
| `load(S.class)` misses providers in a plugin JAR | Does TCCL see the JAR and the service resource? | Pass the plugin loader explicitly or redesign TCCL |
| `load(layer, S.class)` misses providers | Is the provider in a named module of the layer or a parent layer? | Resolve the module into the right layer, check `uses`/`provides` |
| `ServiceConfigurationError` occurs | Are service/implementation compatible? Are constructor, provider method, and module declarations valid? | Fix configuration or implementation; read the root cause of the error |
| Old version still seen after replacing JAR | Do the old loader/layer and old provider instances still exist? | Stop the plugin, drop references, create a new loader/layer, and reinitialize |
| Provider is found but throws `ClassCastException` | Did host/plugin load two copies of the service API through different loaders? | Place the shared SPI in an appropriate parent loader/module; control class identity |

Some useful values to log when debugging:

~~~java
System.out.println("TCCL: " +
        Thread.currentThread().getContextClassLoader());
System.out.println("system: " + ClassLoader.getSystemClassLoader());
System.out.println("platform: " + ClassLoader.getPlatformClassLoader());
System.out.println("service loader: " + GreetingService.class.getClassLoader());
~~~

This is an illustrative snippet requiring the `GreetingService` class from the previous examples. In real systems, also log the **provider name, containing module, defining class loader, and JAR path** when possible. Logs help determine exactly which scope a provider lives in, rather than guessing by directory name.

## 10. Self-Check Quiz

1. **A dependency containing a provider was added to Maven/Gradle and the application can call the service. Must `loadInstalled` find that provider?** No. A dependency added only to the application scope is not discovered by `loadInstalled`.
2. **Can you write `ServiceLoader.load(S.class, ClassLoader.getPlatformClassLoader())` instead of `loadInstalled(S.class)`?** Yes, that is equivalent in Java 17+.
3. **Why can `load(S.class)` work on thread A yet fail to see the provider on thread B?** Two threads can have different TCCLs, especially in application servers or framework/plugin hosts.
4. **Is `load(ModuleLayer.boot(), S.class)` always equivalent to `loadInstalled(S.class)`?** No. The boot layer can contain application named modules, whereas `loadInstalled` relies on the platform loader; the two methods have different scopes.
5. **Will a provider in `plugins/hello.jar` appear automatically when calling `loadInstalled`?** No. The host must load the JAR or module with an appropriate loader/layer and discover providers in that scope.
6. **Can `ServiceLoader.reload()` install a new JAR into the runtime?** No. It only clears `ServiceLoader`'s provider cache; class/module lookup paths and plugin lifecycle are managed by other mechanisms.
7. **For an application's explicit named module, is `uses` required?** Yes. A module using `ServiceLoader` must declare `uses` for the corresponding service per the JPMS contract.

**Takeaway:** `loadInstalled` = discovery with the **platform class loader**, intentionally ignoring providers in the application scope. For providers on the classpath, application module path, or plugin loaders/layers, choose `load` with the corresponding TCCL, loader, or module layer. Do not use the name "installed" to infer that the API automatically scans every provider deployed by the application.

## References

- [Java SE 17 — `ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): specification of `load`, `loadInstalled`, `load(ModuleLayer, ...)`, lazy/caching mechanics, and provider errors.
- [Java SE 17 — `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `getPlatformClassLoader()`, `getSystemClassLoader()`, and class loader relationships.
- [Oracle JDK Migration Guide — Removed Extension Mechanism](https://docs.oracle.com/en/java/javase/21/migrate/migrating-jdk-8-later-jdk-releases.html): `lib/ext` and `java.ext.dirs` were removed as of Java 9.
