# ServiceLoader.load with ModuleLayer in Java

## 1. Why Do We Need an Overload Accepting ModuleLayer?

In a Java architecture with a host and plugins, the host wants to work with a shared **service interface**, while the implementation may reside in a **named module** loaded into a new `ModuleLayer` after the application is already running. Java 9+ provides the overload:

~~~java
public static <S> ServiceLoader<S> load(
        ModuleLayer layer, Class<S> service)
~~~

This is an API signature, not a complete Java program. It creates a `ServiceLoader<S>` to discover providers registered in **named modules of the passed-in layer and its ancestor layers**.

Unlike loading an arbitrary class via `ClassLoader.loadClass("pkg.Type")`, ServiceLoader finds implementations registered for **a service contract**; the consumer does not have to import the implementation name directly.

~~~text
           ModuleLayer.boot()
      +-----------------------------+
      | com.acme.host               |
      | com.acme.spi                |
      | Greeter (service interface) |
      +-----------------------------+
                    ^
                    | parent layer
                    |
        Child ModuleLayer
      +-----------------------------+
      | com.acme.greeter            |
      | HelloGreeter (provider)     |
      +-----------------------------+

ServiceLoader.load(childLayer, Greeter.class)
          -> searches child layer
          -> then ancestor layers
          -> does not search providers belonging to an unnamed module
             just because they are on the classpath
~~~

Distinguish four concepts:

- **`ClassLoader`**: responsible for locating and defining classes.
- **`ModuleLayer`**: a set of resolved modules with a configuration and mappings to class loaders.
- **`ServiceLoader`**: the API for discovering/instantiating providers of a service.
- **`ModuleFinder`**: discovers modules on specified paths; by itself, it does **not** create a layer or automatically load providers.

For a plugin running as an **explicit named module**, you can proactively resolve a new module into a child layer and then call `ServiceLoader.load(childLayer, Greeter.class)` without placing the plugin module on the boot module path from the start.

## 2. Contract Between the Three Modules

As an example, we have:

| Module | Role | Essential directives |
| --- | --- | --- |
| `com.acme.spi` | Contains the `Greeter` interface | `exports com.acme.spi;` |
| `com.acme.host` | Consumer looking up providers | `requires com.acme.spi;`, **`uses com.acme.spi.Greeter;`** |
| `com.acme.greeter` | Provider module | `requires com.acme.spi;`, **`provides com.acme.spi.Greeter with com.acme.greeter.HelloGreeter;`** |

Shared interface:

~~~java
package com.acme.spi;

public interface Greeter {
    String greet();
}
~~~

A caller that is an explicit named module must **declare `uses`** for the service it requests through ServiceLoader. Having only `requires com.acme.spi;` is not enough: requires grants readability, whereas uses declares the need to use the service. Without a matching uses, the API may throw `ServiceConfigurationError`.

In the provider module:

~~~java
module com.acme.greeter {
    requires com.acme.spi;
    provides com.acme.spi.Greeter
            with com.acme.greeter.HelloGreeter;
}
~~~

The `provides ... with ...` keyword registers the provider according to the descriptor. **`exports com.acme.greeter;` is not needed just for ServiceLoader to instantiate the provider**. The host only needs the `Greeter` type from the SPI module, while the implementation class can remain encapsulated internally.

A service/interface type must have a **consistent runtime identity**. If the host has `com.acme.spi.Greeter` defined by loader A, while the plugin uses a copy of Greeter defined by loader B, they may not be the same interface despite having the same name, leading to cast/linkage errors. Placing the SPI module in the parent layer and sharing the same module is a common choice.

## 3. Scope of load(layer, service)

According to the Java SE API:

1. Searches for providers in **the passed-in layer**.
2. Continues searching for providers in **ancestor layers** of that layer.
3. **Does not search providers belonging to unnamed modules** through this overload.
4. When there are multiple parent layers, traversal is **depth-first**; each ancestor layer is visited at most once.
5. **There is no deterministic order among modules within the same layer**. If results need prioritization, the application must explicitly select/sort them.
6. Within a module declaring multiple providers, the order in the module descriptor matters according to the API rules; providers added dynamically by instrumentation have separate rules.
7. Only modules actually **resolved into the layer graph** are in scope. Having a JAR on disk does not mean the layer contains that module.

Suppose `L0` is boot, `L1` and `L2` have `L0` as their parent, and `L3` is created with two parents `L1` and `L2`:

~~~text
         L0
       /    \
      L1     L2
        \   /
         L3
~~~

Calling `load(L3, Service.class)` searches L3 first, then its ancestors using depth-first rules while avoiding processing any layer multiple times. Another **sibling layer** in the JVM is not automatically searched if it is not an ancestor of the passed-in layer.

**Specifically:** `ServiceLoader.load(ModuleLayer.boot(), Greeter.class)` does not automatically descend into all descendant layers. If the provider only resides in a child layer, pass that child layer.

## 4. Workflow for Creating a Child Layer for a Plugin

A simple example choosing the boot layer as the parent:

~~~java
ModuleLayer parent = ModuleLayer.boot();

ModuleFinder finder = ModuleFinder.of(
        Path.of("build/plugins"));

Configuration config = parent.configuration().resolve(
        finder,
        ModuleFinder.of(),
        Set.of("com.acme.greeter"));

ModuleLayer pluginLayer = parent.defineModulesWithOneLoader(
        config, ClassLoader.getSystemClassLoader());

ServiceLoader<Greeter> services =
        ServiceLoader.load(pluginLayer, Greeter.class);
~~~

The snippet above only illustrates the core API; imports and a full runnable project are in Section 5.

**Explanation:**

1. `ModuleLayer.boot()` retrieves the boot layer containing the named modules resolved by the launcher/JVM.
2. `ModuleFinder.of(Path.of(...))` discovers exploded modules or modular JARs placed in the specified location.
3. `Configuration.resolve` creates a new configuration based on the parent configuration. The set `Set.of("com.acme.greeter")` specifies the root module; the resolver handles resolving the appropriate required modules as well.
4. `parent.defineModulesWithOneLoader(config, parentLoader)` defines the child layer. This method creates **one new class loader** for the modules in the child layer's configuration. The argument `ClassLoader.getSystemClassLoader()` is the **parent of the new loader**, not the defining loader of the plugin classes itself.
5. `ServiceLoader.load(pluginLayer, Greeter.class)` discovers providers based on the metadata of named modules in the plugin layer and its ancestors.

If a plugin JAR is in the finder path but **not in the resolved graph**, `ServiceLoader` does not automatically add that module to the layer. For auto-discovery scenarios with service-binding resolution, the `Configuration.resolveAndBind` API is an alternative option worth studying; this example intentionally specifies the provider explicitly as a root so that the behavior is reproducible.

### How Do One Loader and Many Loaders Differ?

- `defineModulesWithOneLoader` creates one class loader for all modules in the child configuration.
- `defineModulesWithManyLoaders` creates a separate class loader for each module according to the API contract.
- Both create **named modules in the layer**; neither is simply adding a JAR to the classpath.
- The decision requires considering the number of modules, split packages, module/loader relationships, and delegation rules. With a single plugin module, `oneLoader` is sufficient to clearly learn ServiceLoader.

## 5. Runnable Java 17+ Example: 3 Modules, 1 Provider

This exercise compiles three modules, but when **running** it separates them:
- `com.acme.host` and `com.acme.spi` sit on the launcher's module path, belonging to the boot layer.
- `com.acme.greeter` sits in a separate plugin path and is only brought into a **child layer** via `ModuleFinder`/`Configuration`.

### Source Structure

~~~text
example/
└── src/
    ├── com.acme.spi/
    │   ├── module-info.java
    │   └── com/acme/spi/Greeter.java
    ├── com.acme.host/
    │   ├── module-info.java
    │   └── com/acme/host/Main.java
    └── com.acme.greeter/
        ├── module-info.java
        └── com/acme/greeter/HelloGreeter.java
~~~

### File src/com.acme.spi/module-info.java

~~~java
module com.acme.spi {
    exports com.acme.spi;
}
~~~

### File src/com.acme.spi/com/acme/spi/Greeter.java

~~~java
package com.acme.spi;

public interface Greeter {
    String greet();
}
~~~

### File src/com.acme.greeter/module-info.java

~~~java
module com.acme.greeter {
    requires com.acme.spi;
    provides com.acme.spi.Greeter
            with com.acme.greeter.HelloGreeter;
}
~~~

### File src/com.acme.greeter/com/acme/greeter/HelloGreeter.java

~~~java
package com.acme.greeter;

import com.acme.spi.Greeter;

public final class HelloGreeter implements Greeter {
    @Override
    public String greet() {
        return "Hello from child layer";
    }
}
~~~

The public provider class has no explicit constructor, so it has an implicit public default constructor fitting the constructor-based provider model in this case. The implementation package does not need to be exported to the host.

### File src/com.acme.host/module-info.java

~~~java
module com.acme.host {
    requires com.acme.spi;
    uses com.acme.spi.Greeter;
}
~~~

### File src/com.acme.host/com/acme/host/Main.java

~~~java
package com.acme.host;

import com.acme.spi.Greeter;
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.List;
import java.util.ServiceLoader;
import java.util.Set;

public class Main {
    public static void main(String[] args) {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "plugin module directory required");
        }

        ModuleLayer parent = ModuleLayer.boot();
        ModuleFinder plugins = ModuleFinder.of(Path.of(args[0]));

        Configuration config = parent.configuration().resolve(
                plugins,
                ModuleFinder.of(),
                Set.of("com.acme.greeter"));

        ModuleLayer child = parent.defineModulesWithOneLoader(
                config, ClassLoader.getSystemClassLoader());

        System.out.println("child has provider: "
                + child.findModule("com.acme.greeter").isPresent());
        System.out.println("host in boot: "
                + (Main.class.getModule().getLayer() == parent));

        List<Greeter> services =
                ServiceLoader.load(child, Greeter.class)
                    .stream()
                    .map(ServiceLoader.Provider::get)
                    .toList();

        System.out.println("provider count: " + services.size());

        for (Greeter greeter : services) {
            Module module = greeter.getClass().getModule();

            System.out.println("provider module: "
                    + module.getName());
            System.out.println("provider in child: "
                    + (module.getLayer() == child));
            System.out.println("message: "
                    + greeter.greet());
        }
    }
}
~~~

Meaning of the steps:
- The host declares `uses` in its module descriptor and does not call the implementation directly.
- The `com.acme.spi` module in the parent layer establishes the shared contract.
- The finder locates the plugin module, the configuration resolves the root, and the new layer is defined.
- `ServiceLoader.load(child, Greeter.class)` searches for providers in the child/ancestors.
- `stream().map(ServiceLoader.Provider::get)` requests the provider instance; provider instantiation is lazy during traversal.
- A single provider keeps stdout stable; if there are multiple modules, do not rely on the unguaranteed iteration order.

### Compile and Run: Linux/macOS

From inside the example directory containing the six Java files:

~~~bash
mkdir -p build/all build/base build/plugins

javac --release 17 --module-source-path src \
    -d build/all $(find src -name '*.java')

cp -R build/all/com.acme.spi build/base/
cp -R build/all/com.acme.host build/base/
cp -R build/all/com.acme.greeter build/plugins/

java --module-path build/base \
    --module com.acme.host/com.acme.host.Main build/plugins
~~~

Make sure `build/base` contains **only** the host and SPI, and `build/plugins` contains **only** the provider. At runtime, do not put the provider on `--module-path build/base`. The plugin is discovered and resolved after the application has entered the `main` method.

### Compile and Run: Windows PowerShell

Use single-line commands to avoid line-continuation character mistakes:

~~~powershell
New-Item -ItemType Directory -Force build\all, build\base, build\plugins | Out-Null
$sources = @(Get-ChildItem -Path src -Recurse -Filter *.java | ForEach-Object { $_.FullName })
javac --release 17 --module-source-path src -d build\all $sources
Copy-Item build\all\com.acme.spi build\base\com.acme.spi -Recurse
Copy-Item build\all\com.acme.host build\base\com.acme.host -Recurse
Copy-Item build\all\com.acme.greeter build\plugins\com.acme.greeter -Recurse
java --module-path build\base --module com.acme.host/com.acme.host.Main build\plugins
~~~

Compilation must succeed before copying the module outputs. If re-running, delete the appropriate old outputs or build in a new directory to prevent stale modules from interfering.

### Verified Actual Stdout

~~~text
child has provider: true
host in boot: true
provider count: 1
provider module: com.acme.greeter
provider in child: true
message: Hello from child layer
~~~

The source code above was compiled with `javac --release 17` and ran successfully on OpenJDK 21.

**Output analysis:**
1. The child layer actually contains the `com.acme.greeter` module.
2. The host remains in the boot layer.
3. Only one provider is loaded because there is one matching `provides` declaration.
4. The `HelloGreeter` instance belongs to the `com.acme.greeter` module.
5. The module containing the provider class belongs to the child layer rather than boot.
6. The host calls `greeter.greet()` through the shared interface and receives the expected string.

## 6. Replacing the Exploded Module with a Modular JAR

`ModuleFinder` can read a **modular JAR** containing `module-info.class`. Once Section 5 has been compiled, package the provider:

~~~bash
mkdir -p build/plugin-jars
jar --create --file build/plugin-jars/com.acme.greeter.jar \
    -C build/all/com.acme.greeter .
java --module-path build/base \
    --module com.acme.host/com.acme.host.Main build/plugin-jars
~~~

On PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build\plugin-jars | Out-Null
jar --create --file build\plugin-jars\com.acme.greeter.jar -C build\all\com.acme.greeter .
java --module-path build\base --module com.acme.host/com.acme.host.Main build\plugin-jars
~~~

The `Main` class does not need to be modified because it receives the plugin path via `args[0]`. ModuleFinder detects the JAR file, the resolver creates the child configuration, and ServiceLoader finds the provider from the named module in the child layer.

You can inspect the JAR via:

~~~bash
jar --describe-module --file build/plugin-jars/com.acme.greeter.jar
~~~

The modular JAR variant was also tested in a separate test run on OpenJDK and returned the expected provider. Note: adding a JAR file after the layer has been created **does not update the existing layer**; a new layer must be resolved/created if you want a new module set.

## 7. Comparing ServiceLoader Overloads

| API | Provider lookup source | When appropriate |
| --- | --- | --- |
| `ServiceLoader.load(ModuleLayer layer, Class<S> service)` | Named modules in the **layer and ancestors**, not unnamed modules. | JPMS plugin/module layers. |
| `ServiceLoader.load(Class<S> service)` | Uses the current thread's **thread context class loader**. | Applications or frameworks managing services via TCCL. |
| `ServiceLoader.load(Class<S> service, ClassLoader loader)` | Uses the specified class loader according to ServiceLoader rules. | Explicitly selecting a loader to locate services based on the environment. |
| `ServiceLoader.loadInstalled(Class<S> service)` | Uses the platform class loader. | Platform/installed provider scope according to the API. |

**Key point:** The `load(layer, service)` overload is not an alternative syntax for `load(service, classLoader)`. A Layer defines the graph of named modules, whereas a ClassLoader determines the loading mechanism and resource/provider lookup under the corresponding API. Changing the TCCL does not turn a layer-based ServiceLoader into a scanner for all unnamed providers.

### How META-INF/services Differs from provides

With the traditional classpath, providers are typically registered via:

~~~text
META-INF/services/com.acme.spi.Greeter
~~~

The content is the provider's binary name, for example `com.acme.greeter.HelloGreeter`. That is the service configuration for the classpath/unnamed module. For explicit named modules, the `provides ... with ...` declaration in the module descriptor is the JPMS model.

Do not place a provider only in `META-INF/services` on the classpath and expect `load(childLayer, Greeter.class)` to discover it automatically: the layer-based overload **does not search for providers in unnamed modules**.

## 8. Provider, Constructor, and Factory Method Rules

For a named module:

- The provider is listed in the `provides service with provider;` directive of the **module containing the provider**.
- The provider class/declared provider is valid according to JLS rules.
- If using a **provider constructor**, the provider class is a subtype of the service and has a public no-arg constructor (explicit or implicit).
- A named-module provider can use a public static no-arg method named exactly **`provider()`** with a compatible return type. With this approach, the provider class is not required to directly implement the service if the method returns an appropriate service instance.
- The consumer module needs `uses` if it belongs to an explicit named module.
- The service API must be accessible and have a consistent class identity across modules.

Illustrative example for a provider factory method:

~~~java
package com.acme.greeter;

import com.acme.spi.Greeter;

public final class GreeterFactory {
    public static Greeter provider() {
        return new HelloGreeter();
    }
}
~~~

With this illustrative code, the descriptor can be written as:

~~~java
provides com.acme.spi.Greeter
        with com.acme.greeter.GreeterFactory;
~~~

This is an **alternative approach**, not applied simultaneously in the runnable exercise in Section 5. The factory method must conform to the specification; do not freely rename it to `create()` and expect ServiceLoader to recognize it automatically.

## 9. Lazy Discovery, Cache, Reload, and Ordering

A `ServiceLoader` instantiates providers **only when needed** during iterator traversal or when accessing `Provider.get()` on a stream:

~~~java
ServiceLoader<Greeter> services =
        ServiceLoader.load(layer, Greeter.class);

for (Greeter service : services) {
    System.out.println(service.greet());
}
~~~

This snippet assumes the `layer` variable already exists and the code resides in a valid consumer. It helps avoid instantiating all providers immediately upon calling `ServiceLoader.load`.

When you only want to inspect the provider type before creating an instance, use `ServiceLoader.stream()` and `ServiceLoader.Provider::type`. When you need an instance, use `Provider::get`. Do not conflate querying type metadata with intentionally running the provider's constructor.

**Cache:** ServiceLoader maintains a cache of discovered/instantiated providers according to its contract. `reload()` clears the cache so the next traversal starts over. However, `reload()` does **not**:

- Recompile modules.
- Resolve newly copied JARs.
- Create a new child `ModuleLayer`.
- Replace the bytecode of already defined classes.
- Unload all objects/classes/providers currently held by the application.

To add a new plugin module to the graph, you typically must **create a new Configuration/ModuleLayer** with the appropriate root/plugin paths, and then create a new ServiceLoader for that layer.

**Ordering:** The API does not guarantee the ordering of modules within the same layer. Do not use the first provider as the "default" if the result must be stable across multiple plugins, unless you design an explicit selection/sorting rule after traversal.

## 10. Troubleshooting

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Provider not found | The plugin module is not yet in the layer or is missing `provides`. | Inspect `child.modules()`, descriptor, and root modules. |
| `ServiceConfigurationError` | Caller named module is missing `uses`; provider violates the contract/cannot be created; service is not accessible. | Inspect `uses`/`provides`, cause, and module boundaries. |
| Resolver cannot find module | Wrong root name/module path or missing requires dependency. | Check `ModuleFinder`, `Configuration.resolve`, and the exception. |
| `LayerInstantiationException` | Split packages or invalid loader/module mapping. | Check package ownership and loader strategy choice. |
| `ClassCastException` | The SPI is defined as two different runtime classes. | Compare `Greeter.class.getClassLoader()` and the service class used by the provider. |
| Provider from classpath does not appear | The layer overload does not scan unnamed modules. | Use the classloader/TCCL API or move the provider to a named module. |
| `reload()` does not see newly added plugin JAR | The old graph/layer is not updated. | Resolve and create a new layer. |
| Iteration order changes | There are multiple modules in the same layer with no guaranteed order. | Select providers according to explicit configuration/priority. |
| Module loads successfully but reflection on implementation fails | The provider package is not exported/opened to the caller. | Use the SPI contract instead of reflecting directly on internal implementation classes. |

### Checklist

1. Does the consumer have `uses service;` in its descriptor?
2. Does the SPI module `exports` the interface package to the consumer and provider?
3. Does the provider module have `provides service with impl;` and a valid implementation?
4. Has the provider module actually been **resolved into the layer**, rather than merely existing on disk?
5. Is `ServiceLoader.load` passed **the layer containing the provider or a descendant**?
6. Is it being confused with unnamed modules or a `META-INF/services` file on the classpath?
7. Are there multiple providers causing the result order to be non-deterministic?
8. Is `ServiceLoader.reload()` being mistaken for reloading the ModuleLayer?
9. Does the exception occur during resolution, layer creation, or when the iterator instantiates the provider?
10. Is a single service interface class identity preserved between host/plugin?

## 11. Self-Check Questions

**Question 1.** A provider resides separately in a child layer. If the host calls `ServiceLoader.load(ModuleLayer.boot(), Greeter.class)`, will it find that provider?

**Answer:** No. The API traverses the passed-in layer and its ancestors; it does not automatically traverse descendants.

**Question 2.** If the consumer already has `requires com.acme.spi;`, does it still need `uses com.acme.spi.Greeter;`?

**Answer:** Yes, for an explicit named module calling ServiceLoader. `requires` provides readability, while `uses` declares the service to be consumed.

**Question 3.** Must the provider package declare `exports` to the host for ServiceLoader to instantiate the object?

**Answer:** No. `provides ... with ...` allows ServiceLoader to instantiate a validly declared provider; the host communicates through the exported SPI.

**Question 4.** A JAR containing only `META-INF/services` is placed on the classpath. Will the ModuleLayer overload find it?

**Answer:** No, it does not search for providers from unnamed modules.

**Question 5.** After copying a new JAR into the plugin folder once the layer is created, is calling `reload()` sufficient?

**Answer:** No. The layer/configuration is already defined. Create a new layer if you want a different module graph.

**Question 6.** When multiple named modules in the same layer provide a provider, is the order always by module name?

**Answer:** No. The order of modules within a layer is not guaranteed.

## Official Documentation

- [ServiceLoader, Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html): `load(ModuleLayer, Class)` overload, lazy providers, cache, uses/provides.
- [ModuleLayer, Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html): layer creation and loader mapping.
- [Configuration, Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/Configuration.html): resolve/resolveAndBind.
- [ModuleFinder, Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleFinder.html): locating modular JARs/exploded modules.
- [JLS Java SE 21 §7.7.4](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7.4): rules of service provision.
