# Service Provider Interface (SPI) and the Role of ServiceLoader in Java

When building an extensible application, **the host should not have to modify its source code whenever a new implementation appears**. Java supports the **Service Provider Interface (SPI)** model: an interface or abstract class defines the contract; multiple **service providers** implement the contract; code that uses the service (consumer) discovers those providers at runtime.

`java.util.ServiceLoader<S>` is the standard API to **find and create providers** without requiring the host to hard-code implementation class names. This mechanism is directly tied to **ClassLoader**, because finding providers and loading bytecode also depend on where the JAR is placed, the thread context class loader (TCCL), the classpath, or JPMS module layers.

Three core points:

1. **The SPI is the contract**, for example `GreetingService`; a provider is an implementation, for example `FriendlyGreeting`. `ServiceLoader` is the discovery/instantiation tool, **not the SPI itself**.
2. **ServiceLoader does not randomly scan every class on the classpath**. In a classpath environment, it reads the descriptor at `META-INF/services/<SPI binary name>`; in **named modules**, it uses JPMS `uses`/`provides`.
3. **Having the class on disk is not enough**: the provider and SPI must have a compatible runtime type identity; the loader chosen for discovery must be able to see both the descriptor and the provider. In the default mode, `ServiceLoader.load(SPI.class)` uses **the current thread's TCCL**.

This article presents the model, operating principles, classloader boundaries, lifecycle, common errors, and a Java 17+ example that works even when the provider **is not on the host's application classpath**.

## 1. The SPI Model: Consumer, Service Contract, and Provider

~~~text
                 Host / Consumer
                       |
                  uses SPI API
                       |
                       v
                 GreetingService
                    /       \
                   /         \
       FriendlyGreeting    FormalGreeting
       (provider A)        (provider B)
                   \         /
                    \       /
                     ServiceLoader
                     discovery
~~~

In Java, a service is typically represented by an `interface` or `abstract class`. A provider is a type that supplies an implementation for the service; how the provider is created depends on the classpath or named module mechanism.

~~~java
package spi;

public interface GreetingService {
    String greet(String name);
}
~~~

This is the **SPI contract**. The consumer can call `greet` without needing to know which plugin JAR the service provider comes from.

Example provider:

~~~java
package ext;

import spi.GreetingService;

public final class FriendlyGreeting implements GreetingService {
    public FriendlyGreeting() { }

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

For a provider to be discovered by `ServiceLoader`, **merely having `implements GreetingService` is not enough**: there must be a valid provider registration configuration.

### Comparison with Dependency Injection (DI)

| Criterion | ServiceLoader/SPI | DI container/framework |
|---|---|---|
| How implementations are selected | Based on Java's provider registration | According to component/configuration/annotations/container rules |
| Runtime provider discovery | Yes, based on class loader/module metadata | Depends on the framework |
| Constructor injection and scopes | Not its primary responsibility | Usually strongly supported |
| API included in the JDK | `java.util.ServiceLoader` | Not required |
| Complexity | Small, convenient for extension points | Can offer more features, but involves more lifecycle overhead |

Do not treat `ServiceLoader` as a full-fledged DI container: it **does not automatically inject all dependencies**, configure transactions, manage HTTP request lifecycles, or proxy providers. If a provider's constructor requires configuration parameters, consider using a **factory** SPI with a no-argument constructor, and let the factory create the object according to the configuration.

## 2. How Does ServiceLoader Discover Providers on the Classpath?

For providers in an **unnamed module/classpath**, each JAR or directory contains a provider configuration file:

~~~text
META-INF/services/spi.GreetingService
~~~

**The file name** after `META-INF/services/` must be **the fully qualified binary name of the service**, here `spi.GreetingService`. Inside it is **the fully qualified binary name of each provider**, one name per line:

~~~text
ext.FriendlyGreeting
~~~

If there are multiple providers:

~~~text
ext.FriendlyGreeting
ext.FormalGreeting
~~~

Rules:

- The provider configuration file is **UTF-8** encoded.
- Use **dots in class names** (`ext.FriendlyGreeting`), not `ext/FriendlyGreeting.class`.
- Blank lines and spaces/tabs around names are ignored.
- The `#` character starts a comment until the end of the line.
- If the same provider name appears multiple times across configuration files, duplicate declarations are ignored according to ServiceLoader rules.
- The provider must be loadable from the class loader used for discovery, and at the same time **assignable to the exact runtime service type**.
- For a provider in an unnamed module/classpath, the provider class must be `public` and have an appropriate **public no-argument constructor**; the provider must be a subtype of the service.

`ServiceLoader` uses `ClassLoader.getResources("META-INF/services/spi.GreetingService")` (and related mechanisms) to locate provider-configuration files within the loader's visibility; it does not automatically traverse all `.class` files or retrieve all subclasses via reflection.

### Proper JAR Structure

~~~text
greeting-plugin.jar
  META-INF/
    MANIFEST.MF
    services/
      spi.GreetingService
  ext/
    FriendlyGreeting.class
~~~

The `META-INF/services/spi.GreetingService` file must be present **in the artifact being run**, not just in the project's `src/resources` directory. `javac` does not automatically copy that resource config file when compiling Java sources.

No `Main-Class` is required: the plugin is discovered by `ServiceLoader`, and there is no need to run `java -jar greeting-plugin.jar`.

## 3. Key `ServiceLoader` APIs

~~~java
import java.util.ServiceLoader;

// Obtain a loader based on the current thread's TCCL.
ServiceLoader<GreetingService> a =
        ServiceLoader.load(GreetingService.class);

// Explicitly specify a loader to find providers.
ServiceLoader<GreetingService> b =
        ServiceLoader.load(GreetingService.class, pluginLoader);
~~~

This is an **illustrative API snippet**: `GreetingService` and `pluginLoader` must exist in scope along with the corresponding imports.

| API | Role |
|---|---|
| `ServiceLoader.load(Service.class)` | Creates a service loader using the **thread context class loader** |
| `ServiceLoader.load(Service.class, loader)` | Creates a service loader using the specified class loader |
| `ServiceLoader.load(layer, Service.class)` | Finds providers in the module layer and appropriate parent layers |
| `iterator()` / `for-each` loop | **Lazily** discovers and instantiates providers |
| `stream()` | Accesses `Provider<S>`, allowing `type()` to be inspected before requesting `get()` |
| `findFirst()` | Finds and retrieves the first provider as an `Optional<S>` |
| `reload()` | Clears cached providers so they are discovered again on the next iteration |

**Do not confuse this:** `ServiceLoader.load(...)` creates **a service loader object**; it does not guarantee that all providers are found/instantiated immediately at that call. In many cases, configuration errors only surface when iterating over the iterator/stream.

### Lazy Discovery and Caching

~~~text
ServiceLoader.load(GreetingService.class)
                |
                v
       ServiceLoader<GreetingService>
                |
             iterator()
                |
        +-------+---------+
        |                 |
  cached providers    Find next provider
        |                 |
        v                 v
 return instance       load + instantiate
                          |
                          v
                   add to cache of
                  ServiceLoader instance
~~~

- Providers already loaded/instantiated within the **ServiceLoader instance** are cached so that subsequent iterations can return them again.
- `reload()` clears the cache of discovered/instantiated providers. It **does not cause the ClassLoader to unload or redefine classes**.
- After `reload()`, a new iterator/stream should be created; an iterator currently in use may no longer be valid.
- ServiceLoader is **not thread-safe**. Do not share a single instance and simultaneously call `reload` and iterate from multiple threads without proper synchronization.
- Do not store a **JVM-wide** ServiceLoader instance for all applications/plugins; TCCL and provider visibility may differ, and cached providers can also keep old loaders alive for a long time.

### `stream()` and Provider Metadata

~~~java
ServiceLoader<GreetingService> services =
        ServiceLoader.load(GreetingService.class);

services.stream().forEach(provider -> {
    Class<? extends GreetingService> type = provider.type();
    System.out.println(type.getName());
    GreetingService service = provider.get();
    System.out.println(service.greet("Java"));
});
~~~

This is an **illustrative snippet**; the SPI package and provider must be configured. `Provider.type()` gives the type that `ServiceLoader` knows as the provider; `get()` requests the instance. Do not assume that merely calling `stream()` will create every service object.

With a **JPMS provider factory method** (covered later), the provider class containing the factory method may differ from the service type represented by `Provider.type()`; therefore, do not rely on this metadata to identify the implementation class across all modes without reading the JDK contract.

## 4. Why Is TCCL Important in Plugin Architecture?

A thread has a **context class loader**:

~~~java
ClassLoader tccl =
        Thread.currentThread().getContextClassLoader();
~~~

`ServiceLoader.load(GreetingService.class)` is equivalent in terms of class loader selection to:

~~~java
ServiceLoader.load(
    GreetingService.class,
    Thread.currentThread().getContextClassLoader()
);
~~~

TCCL solves the case where **the API/host library is loaded by a parent** yet needs to discover providers visible to a child plugin loader. If the API code only used its own defining loader, it might not see the plugin bytecode/config in the child.

~~~text
                  Application class loader
                        |
                  spi.GreetingService
                        |
                  Host application
                        |
             creates plugin URLClassLoader
                        |
                        +--> ext.FriendlyGreeting
                        +--> META-INF/services/spi.GreetingService

Thread Context ClassLoader = plugin URLClassLoader
                        |
                        v
     ServiceLoader.load(GreetingService.class)
                        |
               finds plugin provider
~~~

An application can set the TCCL temporarily:

~~~java
Thread current = Thread.currentThread();
ClassLoader previous = current.getContextClassLoader();

try {
    current.setContextClassLoader(pluginLoader);
    for (GreetingService provider
            : ServiceLoader.load(GreetingService.class)) {
        // Call the provider.
    }
} finally {
    current.setContextClassLoader(previous);
}
~~~

This is an illustrative snippet; `pluginLoader` must have an appropriate lifecycle. **Always restore the TCCL in `finally`**: thread pools reuse threads, and forgetting to restore it can cause other requests to use the wrong plugin loader or keep a stopped loader alive for a long time.

If `pluginLoader` is already available and there is no need to change the TCCL for another framework, the `ServiceLoader.load(SPI.class, pluginLoader)` overload is usually clearer and has a more limited impact.

## 5. Complete Java 17+ Example: SPI in the Host, Provider in a Plugin Directory

This experiment creates an API contract, a provider class, a provider-configuration file, and a host consumer. The key point is that **the classpath of the run command contains only the host and the SPI**, while the provider is loaded via a new `URLClassLoader`.

### 5.1. Project Structure

~~~text
project/
  src/
    api/
      spi/
        GreetingService.java
    plugin/
      ext/
        FriendlyGreeting.java
    host/
      ServiceLoaderDemo.java
  resources/
    META-INF/
      services/
        spi.GreetingService
  out/
    api/
    plugin/
    host/
~~~

Output directories are created during the build. The service configuration file in `resources` must be **copied** to `out/plugin/META-INF/services/spi.GreetingService`.

### 5.2. `src/api/spi/GreetingService.java`

~~~java
package spi;

public interface GreetingService {
    String greet(String name);
}
~~~

### 5.3. `src/plugin/ext/FriendlyGreeting.java`

~~~java
package ext;

import spi.GreetingService;

public final class FriendlyGreeting implements GreetingService {
    public FriendlyGreeting() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

The public no-argument constructor serves `ServiceLoader` under the classpath mechanism. The provider class needs to load/instantiate successfully and must implement **the exact runtime interface `spi.GreetingService`**.

### 5.4. `resources/META-INF/services/spi.GreetingService`

~~~text
ext.FriendlyGreeting
~~~

This is a **text file**, not a Java class. The file name is **exactly** `spi.GreetingService`; the content is **exactly** the binary class name `ext.FriendlyGreeting`.

### 5.5. `src/host/ServiceLoaderDemo.java`

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ServiceLoader;
import spi.GreetingService;

public final class ServiceLoaderDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: ServiceLoaderDemo <plugin-directory>");
        }

        ClassLoader parent = GreetingService.class.getClassLoader();
        URL source = Path.of(args[0]).toAbsolutePath()
                .toUri().toURL();

        // The parent cannot see the plugin directory's config/provider.
        boolean viaParent = ServiceLoader
                .load(GreetingService.class, parent)
                .iterator().hasNext();
        System.out.println("provider through parent: " + viaParent);

        try (URLClassLoader pluginLoader =
                new URLClassLoader("greeting-plugin",
                        new URL[] {source}, parent)) {

            Thread current = Thread.currentThread();
            ClassLoader previous = current.getContextClassLoader();

            try {
                current.setContextClassLoader(pluginLoader);

                // Convenience overload obtains the TCCL that was just set.
                ServiceLoader<GreetingService> services =
                        ServiceLoader.load(GreetingService.class);

                int count = 0;
                for (GreetingService service : services) {
                    System.out.println("provider says: "
                            + service.greet("Java"));
                    System.out.println("same service API: "
                            + (service instanceof GreetingService));
                    System.out.println("provider defined by plugin: "
                            + (service.getClass().getClassLoader()
                               == pluginLoader));
                    count++;
                }

                System.out.println("providers: " + count);
            } finally {
                current.setContextClassLoader(previous);
            }
        }
    }
}
~~~

**Why does the example use `GreetingService`'s loader as the parent?** Because the host and the provider must refer to **the same runtime interface**, namely `(spi.GreetingService, parent)`. The plugin loader defines `ext.FriendlyGreeting` itself, while delegating loading of `spi.GreetingService` to the parent.

**Why must the TCCL be set?** The host program is loaded via the app loader, which does not include the plugin directory. When temporarily setting the TCCL to the URLClassLoader, `ServiceLoader.load(GreetingService.class)` finds the provider-configuration file and implementation class visible to the plugin loader.

### 5.6. Compiling and Running (Bash / Linux / macOS)

Run from the `project` directory:

~~~bash
mkdir -p out/api out/plugin/META-INF/services out/host

javac -d out/api src/api/spi/GreetingService.java

javac -cp out/api -d out/plugin src/plugin/ext/FriendlyGreeting.java

cp resources/META-INF/services/spi.GreetingService \
   out/plugin/META-INF/services/spi.GreetingService

javac -cp out/api -d out/host src/host/ServiceLoaderDemo.java

java -cp "out/api:out/host" ServiceLoaderDemo out/plugin
~~~

On Windows, you can create directories with `New-Item -ItemType Directory -Force`, copy the file with `Copy-Item`, and use `;` as the classpath separator:

~~~powershell
java -cp "out/api;out/host" ServiceLoaderDemo out/plugin
~~~

Note: **do not add `out/plugin` to the host's `-cp`**. It is only the URL source for the custom loader. If `out/plugin` is added to the application classpath, the `ServiceLoader.load(SPI.class, parent)` call may find the provider before changing the TCCL, making the comparison invalid.

**Deterministic stdout in the described configuration:**

~~~text
provider through parent: false
provider says: Hello, Java
same service API: true
provider defined by plugin: true
providers: 1
~~~

### 5.7. Explaining the Output

- `provider through parent: false`: the parent only sees the host + API, and does not see the `META-INF/services` descriptor/config in `out/plugin`.
- `provider says: Hello, Java`: ServiceLoader read the descriptor, loaded `ext.FriendlyGreeting`, and instantiated the provider.
- `same service API: true`: the provider implements **the exact** runtime `spi.GreetingService` used by the host.
- `provider defined by plugin: true`: the `ext.FriendlyGreeting` class is defined by the custom-created URLClassLoader, not found earlier by the parent.
- `providers: 1`: only one provider is registered and found in the experiment configuration.

### 5.8. Packaging the Plugin as a JAR

From the output above, package the plugin class together with the descriptor:

~~~bash
mkdir -p dist

jar --create --file dist/greeting-plugin.jar -C out/plugin .

jar --list --file dist/greeting-plugin.jar
~~~

The main entries that must be present:

~~~text
ext/FriendlyGreeting.class
META-INF/services/spi.GreetingService
~~~

Run again using the JAR path instead of the directory:

~~~bash
java -cp "out/api:out/host" ServiceLoaderDemo dist/greeting-plugin.jar
~~~

Because the code converts the path to a `URL` using `Path.toUri().toURL()`, `URLClassLoader` supports both directory URLs and JAR URLs. When both entries are present, **stdout is identical to section 5.6**.

Note: the plugin JAR does not need a `Main-Class`. ServiceLoader uses the `META-INF/services` descriptor and binary names.

## 6. ServiceLoader Must Not Blur Type Identity Boundaries

A common plugin mistake: the plugin JAR packages **a duplicate copy of the SPI** `spi.GreetingService` and is then loaded child-first for `spi.*` as well. Even though the provider declares `implements spi.GreetingService`, the JVM may treat it as **a different interface** from the host's SPI:

~~~text
Host:    (spi.GreetingService, AppLoader)
Plugin:  (spi.GreetingService, PluginLoader)

Same binary name but different defining loaders
=> two different runtime interfaces
~~~

When ServiceLoader tries to check whether the provider is assignable to the service type, a provider with a boundary mismatch can cause a `ServiceConfigurationError`; a manual cast operation can encounter a `ClassCastException`.

**The right way:** have the SPI, public callbacks/DTOs/shared exceptions live in a shared parent loader. The plugin loader uses parent delegation for that API and only defines its own implementation/dependencies.

Having `GreetingService.class` with identical bytecode in both places is not enough; the JVM distinguishes them by the **defining loader object**.

### Errors Caused by the Wrong TCCL

A framework running in a thread pool might use the TCCL of a thread created before the plugin loader existed. In that case:

~~~java
ServiceLoader.load(GreetingService.class)
~~~

may return an empty result even though `pluginLoader.loadClass("ext.FriendlyGreeting")` succeeds. This is not a contradiction: ServiceLoader may **not find the provider configuration file** from the current thread's TCCL.

Diagnosis:

~~~java
System.out.println(Thread.currentThread()
        .getContextClassLoader());

System.out.println(GreetingService.class.getClassLoader());
~~~

These two values are not required to be equal. Try `ServiceLoader.load(GreetingService.class, pluginLoader)` to explicitly request the target loader and compare.

## 7. The SPI Mechanism in JPMS: `uses` and `provides`

Since Java 9, **named modules** use module descriptors instead of relying entirely on `META-INF/services`.

Example of a module defining an SPI:

**`greeting.api/module-info.java`**

~~~java
module greeting.api {
    exports spi;
}
~~~

The contents of the `spi.GreetingService` interface are compiled and packaged inside the `greeting.api` module.

Consumer module:

**`greeting.consumer/module-info.java`**

~~~java
module greeting.consumer {
    requires greeting.api;
    uses spi.GreetingService;
}
~~~

Code in the `greeting.consumer` module can call `ServiceLoader.load(GreetingService.class)`. A **`uses`** declaration for the service type is required for a named module using ServiceLoader; `requires` grants access to the module exporting the SPI.

Provider module:

**`greeting.provider/module-info.java`**

~~~java
module greeting.provider {
    requires greeting.api;
    provides spi.GreetingService
        with ext.FriendlyGreeting;
}
~~~

When the provider module is **resolved and present in the searched module layer**, ServiceLoader can locate the provider via `provides`. Appropriate module path/resolution configuration is required, rather than merely copying `module-info.class` into a JAR and assuming the provider will appear.

An illustrative consumer class in `greeting.consumer`:

~~~java
package app;

import java.util.ServiceLoader;
import spi.GreetingService;

public final class Main {
    public static void main(String[] args) {
        ServiceLoader.load(GreetingService.class)
                .forEach(service ->
                        System.out.println(service.greet("Java")));
    }
}
~~~

These are **illustrative file snippets specific to JPMS**; do not copy them into the same place as the classpath demo without organizing a modular structure. You must create a module source tree, compile/resolve the modules, and ensure the provider module is in the module graph; the number of providers also depends on the environment.

### Why Is `uses` Not Equivalent to `requires provider.module`?

- `requires greeting.api` allows the consumer to reference the service interface exported by `greeting.api`.
- `uses spi.GreetingService` declares **the intent to consume the service** so JPMS/ServiceLoader can perform discovery under the module model.
- `provides spi.GreetingService with ext.FriendlyGreeting` in the provider module registers the implementation.
- The consumer **does not need** to depend directly on the implementation module to call the service. That is the loose coupling goal of SPI.

Avoid forcing the consumer to write `requires greeting.provider` just to have the provider class name on the compile classpath; doing so defeats the idea of changing implementations independently.

### Provider Constructor and Provider Factory Method

According to the JDK API, a provider in the **classpath/unnamed module** is instantiated via an appropriate **public no-argument constructor**.

In an **explicit named module**, a provider can be created via:

1. An appropriate no-argument **provider constructor**; or
2. A **public static no-arg factory method named `provider`**, returning an instance of a type assignable to the service.

Example of a provider factory method (illustrative):

~~~java
package ext;

import spi.GreetingService;

public final class GreetingFactories {
    private GreetingFactories() { }

    public static GreetingService provider() {
        return name -> "Hello from factory, " + name;
    }
}
~~~

With an explicit module declaring `provides spi.GreetingService with ext.GreetingFactories;`, the API can use the provider method to create the service. **Do not apply this provider method mechanism to provider-configuration files in an unnamed module**: on the classpath, the listed class must directly be a subtype of the service and have an appropriate constructor.

The benefit of a provider factory method: it can hide the actual implementation or return a pre-configured factory/service, rather than forcing the service object to be identical to the provider class declared in the module descriptor.

### Providers in Module Layers

`ServiceLoader.load(ModuleLayer layer, SPI.class)` finds providers from the specified layer and appropriate ancestor layers. This approach suits plugin modules created via their own `ModuleLayer`.

Things to note:

- Discovering module providers involves the **module graph/layer**, not just looking at a classpath URL.
- A layer can use multiple classloaders; do not infer the loader passed to a given overload merely by looking at thread context.
- Module readability/exports/opens and provider resolution must be properly designed.
- `ServiceLoader.load(layer, service)` **does not find providers from unnamed modules** according to the API contract.

## 8. Multiple Providers: Selection, Ordering, and Conflicts

When there are multiple providers for the same SPI:

~~~java
ServiceLoader<GreetingService> all =
        ServiceLoader.load(GreetingService.class);

for (GreetingService g : all) {
    System.out.println(g.greet("Java"));
}
~~~

This is an illustrative snippet. **Provider ordering should not be treated as stable business behavior across all environments**. With classpath descriptors, the order depends on the order in which the classloader finds resource files and the configuration lines. With named modules, there are specific rules and certain orderings are not guaranteed.

You should not rely on "the first provider that appears is always the best provider" when multiple JARs are present. It is better to:

- Design the interface with metadata such as `id()`, `priority()`, `supports(...)`.
- Collect all providers and then **select according to an explicit policy**.
- Handle failing providers according to the product contract; do not silently ignore serious configuration errors.
- For extensions that are deployed/redeployed, associate the provider list with the plugin generation/lifecycle.

### Difference Between `findFirst()` and `stream().findFirst()`

`findFirst()` returns `Optional<S>` and may instantiate the first provider to obtain the service instance.

`stream()` returns a stream of `ServiceLoader.Provider<S>`, allowing `type()` to be inspected before calling `get()`. This is a useful difference if you want to select a provider based on metadata without having to create all instances.

However, `stream()` still performs lazy discovery and can throw `ServiceConfigurationError` when a provider config/class is invalid. Do not treat it as a static check that always succeeds.

## 9. `ServiceConfigurationError` and How to Diagnose It

`ServiceLoader` reports errors via `java.util.ServiceConfigurationError` (a subtype of `Error`). It can occur during `hasNext()`, `next()`, stream operations, or `Provider.get()` when a provider needs to be loaded/instantiated.

Common causes:

| Error | Example | Resolution |
|---|---|---|
| Wrong descriptor name | `META-INF/services/GreetingService` instead of `.../spi.GreetingService` | Use the **fully qualified binary name of the SPI** |
| Wrong provider name | `ext/FriendlyGreeting.class` | One line `ext.FriendlyGreeting` |
| Provider config not in runtime artifact | `resources/` was not copied | Verify with `jar --list` |
| Provider class not visible | Wrong plugin URL/TCCL or missing dependency | Check the chosen loader, classpath, and parent chain |
| Not a subtype of the same runtime SPI | Plugin redefines `spi.GreetingService` | Share the SPI from the parent defining loader |
| Unsuitable constructor on classpath | Missing `public` no-arg constructor | Add a valid constructor or switch to a module provider method when the design fits |
| Abstract/uninstantiable class | Provider has no concrete implementation | Fix the provider implementation |
| Constructor/provider method fails | Runtime exception during instantiation | Inspect stack trace/cause |
| Incompatible version/linkage | `NoClassDefFoundError`, `NoSuchMethodError` | Check the actual JARs, defining loader, and binary compatibility |
| Invalid UTF-8/syntax in config file | Invalid class name line | Fix descriptor structure, encoding/comments |
| Module missing `uses` | Consumer in an explicit named module has not declared service use | Add `uses SPI;` |
| Provider module not resolved | JAR is on the module path but not in the execution graph | Adjust module resolution/module layer |

Because `ServiceConfigurationError` is an `Error`, you should not habitually catch and ignore it as if there were no providers. If the system genuinely allows optional plugins to fail, there should be an isolation policy, logging of the cause, and assurance that application-wide errors are not masked.

### Ordered Diagnostic Checklist

**Step 1 — Verify the service type:**

~~~java
System.out.println(GreetingService.class.getName());
System.out.println(GreetingService.class.getClassLoader());
~~~

**Step 2 — Verify the TCCL or explicit loader:**

~~~java
ClassLoader loader =
        Thread.currentThread().getContextClassLoader();
System.out.println(loader);
~~~

**Step 3 — Verify the provider descriptor resource:**

~~~java
var configs = loader.getResources(
        "META-INF/services/spi.GreetingService");

while (configs.hasMoreElements()) {
    System.out.println(configs.nextElement());
}
~~~

These are **illustrative snippets**; they require `IOException` exception handling and a non-`null` loader variable. Being able to see the descriptor does not by itself guarantee that the class/provider loads validly, but it helps distinguish discovery errors from instantiation errors.

**Step 4 — Verify that the provider class can be loaded:**

~~~java
Class<?> impl = loader.loadClass("ext.FriendlyGreeting");
System.out.println(impl.getClassLoader());
System.out.println(GreetingService.class.isAssignableFrom(impl));
~~~

If `isAssignableFrom` is `false`, check for **two copies of the SPI in different loaders**, package/module access, and binary incompatibility.

**Step 5 — Inspect the artifact:**

~~~bash
jar --list --file dist/greeting-plugin.jar
~~~

Look specifically for `META-INF/services/spi.GreetingService` and `ext/FriendlyGreeting.class`, rather than only checking the Maven dependency declaration.

**Step 6 — Read the cause of `ServiceConfigurationError`:** when an error is due to provider bytecode/constructor issues, the root cause may lie inside `getCause()` or another exception chain. Do not fix it by adding every JAR to the global classpath if isolation is the goal.

## 10. ServiceLoader, ClassLoader, and Plugin Lifecycle

### 10.1. ServiceLoader Retains an Instance-Scoped Cache

After a provider has been discovered/instantiated, ServiceLoader can retain references to the instance and class metadata. If the host retains a `ServiceLoader` longer than the plugin lifecycle, the old plugin loader may **not be garbage-collected/unloaded**.

Example during redeploy:

~~~text
Generation A: pluginLoader-A -> providers-A
        |
        +-- Host still holds ServiceLoader<A> / provider instance
        |
        +-- Loader A has no chance to unload

Generation B: pluginLoader-B -> providers-B
        |
        +-- New ServiceLoader instance for B
~~~

When stopping a plugin, you should:

1. Stop the plugin's tasks/threads, cancel callbacks, and close resources.
2. Stop using the old provider objects.
3. Clear references to ServiceLoader/provider instances and any TCCL pointing to the old loader.
4. Close the URLClassLoader or bytecode/JAR source according to its lifecycle.
5. Let the JVM/GC determine when actual class unloading occurs.

`ServiceLoader.reload()` **does not replace** all of the steps above; it only clears the loader instance's provider cache and does not automatically reload class definitions.

### 10.2. Thread Safety

ServiceLoader is not a concurrent-ready container by default. An instance being iterated/reloaded concurrently has no thread-safety guarantees. When multithreading is needed:

- Discover providers in a controlled phase.
- Create a snapshot of the list of service instances or factories according to each provider's thread-safety contract.
- Publish the snapshot safely (for example, an immutable list + a volatile/atomic reference).
- Only share provider instances across threads if the **provider's implementation** is thread-safe.
- For plugin reloads, swap generation snapshots atomically instead of modifying the same list shared across threads.

ServiceLoader does not guarantee on its own that all providers have immutable or reentrant state.

### 10.3. Trust Boundary

Reading a descriptor and instantiating a provider means the application executes code released by the plugin vendor. `ServiceLoader` and `ClassLoader` **do not create a security sandbox**. If a plugin is untrusted, you need signature/artifact-source verification processes, process permissions, appropriate sandbox/process isolation, and update/deployment policies.

Do not print configuration files containing secrets just to debug service discovery; log the provider name, loader, version/hash, and artifact location when needed.

## 11. Common Misconceptions

1. **"SPI and ServiceLoader are the same thing."** False: SPI is the contract; ServiceLoader is the provider discovery/instantiation mechanism.
2. **"Just implementing the interface is enough for ServiceLoader to find it automatically."** False: classpath requires `META-INF/services`; named modules require `provides`.
3. **"ServiceLoader automatically scans all `.class` files."** False: it relies on provider configuration and module metadata.
4. **"`load(SPI.class)` always uses the system class loader."** False: it uses **the current TCCL**.
5. **"Creating a URLClassLoader automatically changes the TCCL."** False: you must pass an explicit loader or set/restore the TCCL in a controlled manner.
6. **"A provider and SPI with the same class name in two loaders can be cast to each other."** False: runtime type identity includes the defining loader.
7. **"The provider file must be named after the provider class."** False: the file name is the **service binary name**; the file contents list the provider binary names.
8. **"The provider file only needs to be in the source resources folder."** False: it must be present in the artifact/runtime search path.
9. **"`ServiceLoader.load` always instantiates every provider immediately."** False: discovery/instantiation is lazy.
10. **"`reload()` will unload classes and hot-replace the plugin."** False: it only resets the provider cache; classloader lifecycle is a separate matter.
11. **"`ServiceLoader` is thread-safe."** False: you must manage synchronization yourself when sharing an instance across multiple threads.
12. **"A classpath provider method `public static provider()` can replace the constructor."** False: provider factory methods belong to explicit module rules; classpath providers need a proper constructor.
13. **"A consumer module must `requires` the provider module."** False: `uses`/`provides` enable loose coupling; only the SPI type needs to be accessible.
14. **"A provider JAR must have a `Main-Class`."** False: that is a `java -jar` rule, not a service discovery rule.
15. **"The first provider is always the preferred implementation."** False: ordering is not a business selection contract across all environments.
16. **"A single global ServiceLoader used for all threads/plugins is safe."** False: TCCL visibility differs and cached providers can keep old loaders alive.
17. **"`ServiceLoader.load(layer, service)` automatically finds unnamed-module classpath providers too."** False: the layer overload searches within named modules in the layer/ancestors according to the contract.

## 12. Self-Check Questions

**Question 1.** What is the difference between SPI, provider, and `ServiceLoader`?

**Answer:** SPI defines the contract, the provider implements the service, and ServiceLoader discovers/instantiates registered providers without the consumer needing to know implementation names in advance.

**Question 2.** The service is `com.demo.Codec`; the provider is `com.demo.impl.FastCodec` running on the classpath. What must the descriptor be named and what must it contain?

**Answer:** The file `META-INF/services/com.demo.Codec`, containing the line `com.demo.impl.FastCodec`. The provider class must be loadable and have an appropriate public no-arg constructor.

**Question 3.** Why does ServiceLoader from the host fail to find a provider located in a plugin URLClassLoader even though `pluginLoader.loadClass` succeeds?

**Answer:** `ServiceLoader.load(SPI.class)` uses the TCCL; the TCCL may be the host loader, which cannot see the descriptor/provider. Pass the explicit pluginLoader or temporarily set and then restore the TCCL.

**Question 4.** A plugin defines its own copy of `spi.GreetingService`; the host has an interface with the same name. What is the consequence?

**Answer:** They are two runtime interfaces with different defining loaders; the provider may not be assignable to the host's SPI, leading to `ServiceConfigurationError` or a cast error.

**Question 5.** Does `reload()` reload new provider bytecode within the same ClassLoader?

**Answer:** No. It only resets ServiceLoader's provider cache; class definitions already loaded by the JVM remain under their own lifecycle.

**Question 6.** In a named module, what must be declared so that the consumer finds the provider without needing to import the implementation class?

**Answer:** The consumer declares `uses spi.GreetingService;`, the provider module declares `provides spi.GreetingService with ext.FriendlyGreeting;`, and the module graph/readability for the service type is properly configured.

**Question 7.** Should the same ServiceLoader and provider instances be shared across multiple threads?

**Answer:** ServiceLoader itself is not thread-safe; snapshot the providers or synchronize access. A provider instance should only be shared if the provider implementation meets the required thread-safety guarantees.

## 13. Workflow for Applying SPI in a Plugin System

~~~text
Define shared SPI (host/shared API)
                 |
                 v
Build provider implementation
                 |
     +-----------+------------+
     |                        |
Classpath/unnamed         Named modules
     |                        |
META-INF/services/...    provides SPI with Impl
     |                        |
     +-----------+------------+
                 |
                 v
Select classloader/TCCL/module layer
                 |
                 v
ServiceLoader.load(...)
                 |
                 v
Iterator/stream: lazy discovery
                 |
                 v
Verify provider contract + lifecycle
                 |
                 v
Select provider by application policy
                 |
                 v
Use -> controlled shutdown/reload
~~~

**Key takeaway:** `ServiceLoader` is **the bridge between a service contract and multiple runtime providers**, not a tool that automatically changes classloaders. Provider discovery must satisfy **the `META-INF/services` or JPMS `uses`/`provides` configuration**, **loader visibility/TCCL**, and **the same runtime SPI type**. When those three conditions are met, implementations can be added without modifying the consumer; when they are not, the error usually lies in the descriptor, the module graph, or the defining loader boundary.

### Official References

- [Java SE 17 — ServiceLoader API: service providers, classpath/JPMS, lazy loading](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
- [Java SE 17 — ClassLoader API: getResources, delegation, defining loader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 17 — URLClassLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html)
- [JLS 17 §7.7 — Module declarations, uses and provides](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7)
