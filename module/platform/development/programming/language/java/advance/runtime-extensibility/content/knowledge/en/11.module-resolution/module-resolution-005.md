# Distinguishing resolve and resolveAndBind When Binding Service Providers

In a Java system using the **Java Platform Module System (JPMS)**, a module can declare that it **uses** a service without directly depending on the module that **provides** the service. This benefits plugins, codecs, adapters, processors, and extension points: the core knows only the service interface, while providers are implemented and distributed separately.

However, at the step of creating a **module configuration** for plugins, there is a critical difference between two APIs on `java.lang.module.Configuration`:

- **`resolve(...)`**: resolves root modules along with their module dependencies following `requires` relationships.
- **`resolveAndBind(...)`**: performs the step above **while also performing service binding** to add provider modules found for services declared with `uses` into the graph.

If you only call `resolve` with the consumer module as root, a provider present on the module path that is not in the `requires` chain may **not be included in the configuration**. Then, creating a `ModuleLayer` from that configuration means `ServiceLoader` will not find that provider in the layer. `resolveAndBind` handles this situation by bringing matching provider modules into the resolution result.

This lesson focuses on the mechanism, applicability conditions, boundaries of service binding, and a runnable Java 17 example comparing the two configurations.

## 1. Four Concepts to Distinguish First

| Concept | Role | Example |
| --- | --- | --- |
| **Service type** | Interface or abstract class describing the contract | `demo.api.Greeting` |
| **Consumer module** | Module calling the service, using `requires` to read the API and `uses` to declare consumption | `demo.app` |
| **Provider module** | Module publishing an implementation via `provides ... with ...` | `demo.provider` |
| **Module configuration** | Set of `ResolvedModule` instances and readability graph produced by resolution | Result of `Configuration.resolve/resolveAndBind` |

Add two runtime concepts:

- **`ModuleLayer`**: brings a `Configuration` into the JVM as real `Module` objects, attaching them to appropriate class loaders. **Creating a configuration** and **defining a module layer** are two separate operations.
- **`ServiceLoader`**: discovers and optionally instantiates providers at runtime, e.g. `ServiceLoader.load(layer, Greeting.class)`. Including a provider in a configuration **does not mean a provider instance has been created**.

Therefore, separate three milestones: **resolve module graph → define layer → discover/instantiate provider**. `resolveAndBind` sits at the first milestone, whereas `ServiceLoader` operates at the last.

## 2. requires, uses, and provides Are Different Relationships

Consider three modules:

```text
demo.api
  exports demo.api;
  interface demo.api.Greeting

demo.app
  requires demo.api;
  uses demo.api.Greeting;

demo.provider
  requires demo.api;
  provides demo.api.Greeting with demo.provider.HelloGreeting;
```

Meaning:

1. `requires demo.api` in `demo.app` is a **module dependency** so the compiler/runtime allows the consumer to read the `Greeting` API (within export rules).
2. `uses demo.api.Greeting` is a **service consumption declaration**. It informs the service binding mechanism and `ServiceLoader` that this module uses the service, but it **is not equivalent to `requires demo.provider`**.
3. `provides demo.api.Greeting with demo.provider.HelloGreeting` registers the implementation with JPMS. The provider module typically needs `requires demo.api` to see the service interface.
4. The consumer **does not need to know the name** of the implementation module at compile time. Adding `requires demo.provider` to the consumer just to “force the provider to be present” gives up part of plugin substitutability.

Diagram:

```text
               requires (readability)
demo.app -------------------------------> demo.api
    |                                        ^
    | uses demo.api.Greeting                 | requires
    |                                        |
    +---- service-use relation ----> demo.provider
                     (provides demo.api.Greeting)

No requires demo.app -> demo.provider.
```

The service-use edge here is a **relationship for finding providers during binding**, not a `requires` edge or a guarantee that the consumer module automatically gains access to every implementation package. Normally the consumer only needs the API type and uses `ServiceLoader`.

## 3. resolve(): From Roots to the Module Dependency Graph

Java 17 provides the instance method:

```java
Configuration child = parentConfiguration.resolve(
        beforeFinder, afterFinder, roots);
```

And the static overload to support multiple parent configurations:

```java
Configuration child = Configuration.resolve(
        beforeFinder, parentConfigurations, afterFinder, roots);
```

These are **illustrative API snippets**; variables must be appropriate `Configuration`, `ModuleFinder`, and `Collection<String>` instances.

The algorithm takes **root module names**, then finds the roots and their direct/indirect `requires` dependencies. When locating a module, the lookup order in the API above is:

1. `beforeFinder`;
2. parent configurations in order;
3. `afterFinder` if not yet found.

Modules satisfied by a parent configuration **are not added to `child.modules()` again**; they belong to the parent configuration. After locating and validating dependencies, the resolver builds the module readability graph. `Configuration.modules()` returns the set of modules resolved in **that configuration itself**, while `findModule(name)` can continue searching parent configurations.

With `demo.app` as root:

```text
roots = {"demo.app"}

resolve:
  demo.app --requires--> demo.api
  demo.provider: not requested by any requires edge

Result in new configuration:
  demo.app, demo.api
```

Merely because `ModuleFinder` **can see** the `demo.provider` JAR does not mean `resolve` will bring that JAR into the graph. “Observable” and “resolved” are two different states. `uses` by itself does not cause `resolve` to collect provider modules.

## 4. resolveAndBind(): Resolution Augmented with Service Binding

The instance API has the same parameter types:

```java
Configuration child = parentConfiguration.resolveAndBind(
        beforeFinder, afterFinder, roots);
```

The static API takes `List<Configuration>` as parents:

```java
Configuration child = Configuration.resolveAndBind(
        beforeFinder, parentConfigurations, afterFinder, roots);
```

**Actual mechanism** (Java 17):

1. Start by resolving root modules just like `resolve`, including `requires` edges.
2. Examine services declared in `uses` by the newly resolved modules **and modules in parent configurations**.
3. Among modules observable by `beforeFinder`/`afterFinder`, find modules that have `provides` implementations for those services.
4. **Add the matching provider modules** to the graph, then resolve the dependencies of those provider modules themselves.
5. If the newly added modules declare `uses` for other services, continue **iterating** until no new modules need to be added.

With the example:

```text
roots = {"demo.app"}

resolveAndBind:
  demo.app  --requires--> demo.api
      |                       ^
      | uses Greeting         | requires
      v                       |
  demo.provider --provides----+

Result in new configuration:
  demo.app, demo.api, demo.provider
```

A point often overlooked: service binding also inspects `uses` in **parent configurations**, not only root modules of the child layer. If the before/after finders contain multiple valid providers, `resolveAndBind` may pull in **more modules than expected**. Do not treat this as an algorithm that “picks the single best implementation” or “takes only the provider directly used by the application”. It is meant to resolve the **presence of provider modules** in the graph.

### Comparison Table

| Criterion | `resolve` | `resolveAndBind` |
| --- | --- | --- |
| Root modules | Yes | Yes |
| Transitively resolves `requires` | Yes | Yes |
| Adds provider modules solely because they match `uses`/`provides` | No | Yes |
| Resolves dependencies of added providers | No such addition step | Yes |
| Inspects parent configurations' service-use for binding | No | Yes |
| Can pull in multiple providers for the same service | Only if already brought in by roots/`requires` | Yes, from observable modules |
| Creates a `ModuleLayer` | No | No |
| Loads classes or instantiates providers | No | No |
| Guarantees `ServiceLoader` finds a provider absent from the module graph | No | No; requires visible module and proper configuration |

Do not think of `resolveAndBind` as replacing `ServiceLoader`: binding builds the **module graph**, while `ServiceLoader` discovers and instantiates instances based on a runtime layer or class loader.

## 5. Complete Example: A Provider That Appears Only with Service Binding

We create three named modules:

- `demo.api`: publishes the service interface.
- `demo.app`: consumer that has `uses` but does not `requires demo.provider`.
- `demo.provider`: implements and registers the service using `provides`.

Then a launcher running on the classpath uses the same `ModuleFinder` and same roots to compare `resolve` with `resolveAndBind`. The launcher creates **two separate layers** and counts the providers found by `ServiceLoader.load(layer, serviceType)`. The example uses Java 17+ and requires no libraries outside the JDK.

### 5.1. Directory Structure

```text
module-binding-demo/
├── src/
│   ├── demo.api/
│   │   ├── module-info.java
│   │   └── demo/api/Greeting.java
│   ├── demo.app/
│   │   ├── module-info.java
│   │   └── demo/app/App.java
│   └── demo.provider/
│       ├── module-info.java
│       └── demo/provider/HelloGreeting.java
└── LayerResolutionDemo.java
```

### 5.2. Module Contents

**`src/demo.api/module-info.java`**

```java
module demo.api {
    exports demo.api;
}
```

**`src/demo.api/demo/api/Greeting.java`**

```java
package demo.api;

public interface Greeting {
    String greet(String name);
}
```

**`src/demo.app/module-info.java`**

```java
module demo.app {
    requires demo.api;
    uses demo.api.Greeting;
}
```

**`src/demo.app/demo/app/App.java`**

```java
package demo.app;

public final class App {}
```

The `App` class is simply a marker so the consumer module has code; the crucial part of the example is in `module-info.java`: the consumer both `requires demo.api` to read the interface and `uses demo.api.Greeting` to participate in service binding.

**`src/demo.provider/module-info.java`**

```java
module demo.provider {
    requires demo.api;
    provides demo.api.Greeting with demo.provider.HelloGreeting;
}
```

**`src/demo.provider/demo/provider/HelloGreeting.java`**

```java
package demo.provider;

import demo.api.Greeting;

public final class HelloGreeting implements Greeting {
    public HelloGreeting() {}

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

`demo.provider` **does not export** its implementation package. `ServiceLoader` can still instantiate a valid provider under `provides` rules; the consumer never needs to call `new HelloGreeting()` directly. The public no-arg constructor supports the provider constructor mechanism in named modules. Other provider method forms are also supported by `ServiceLoader`, though unnecessary for this example.

### 5.3. Launcher Comparing Both Branches

**`LayerResolutionDemo.java`** (located at project root, runs on classpath):

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;
import java.util.ServiceLoader;
import java.util.stream.Collectors;

public final class LayerResolutionDemo {
    private static String names(Configuration config) {
        return config.modules().stream()
                .map(m -> m.name())
                .sorted()
                .collect(Collectors.joining(","));
    }

    private static long providerCount(ModuleLayer layer) throws Exception {
        Class<?> type = layer.findLoader("demo.api")
                .loadClass("demo.api.Greeting");
        return ServiceLoader.load(layer, type).stream().count();
    }

    public static void main(String[] args) throws Exception {
        ModuleFinder finder = ModuleFinder.of(Path.of(args[0]));
        Configuration boot = ModuleLayer.boot().configuration();
        Set<String> roots = Set.of("demo.app");

        Configuration resolved =
                boot.resolve(finder, ModuleFinder.of(), roots);
        Configuration bound =
                boot.resolveAndBind(finder, ModuleFinder.of(), roots);

        System.out.println("resolve=" + names(resolved));
        System.out.println("resolveAndBind=" + names(bound));

        ModuleLayer plainLayer =
                ModuleLayer.boot().defineModulesWithOneLoader(
                    resolved, ClassLoader.getSystemClassLoader());
        ModuleLayer boundLayer =
                ModuleLayer.boot().defineModulesWithOneLoader(
                    bound, ClassLoader.getSystemClassLoader());

        System.out.println(
            "resolve providers=" + providerCount(plainLayer));
        System.out.println(
            "resolveAndBind providers=" + providerCount(boundLayer));
    }
}
```

**Why does the launcher obtain `Class<?>` from the layer?** The launcher does not require a compile-time dependency on `demo.api`; it retrieves the exact service type defined by `demo.api`'s loader in each layer. This is also how you avoid class identity confusion when creating module layers dynamically. Even though two layers use the same module name and interface, classes defined by different layers' loaders must not be cast across one another.

**Why use `ServiceLoader.load(layer, type)`?** This API searches for providers in **the specified layer and its ancestor layers**, rather than relying implicitly on the thread context class loader. It does not scan providers in unnamed modules. Calling `stream().count()` here counts discovered provider descriptors **without forcing service instantiation**, so the output compares the provider sets exposed by the layers.

### 5.4. Compile and Run

In the `module-binding-demo` directory, run with PowerShell on Windows:

```powershell
New-Item -ItemType Directory -Force mods, launcher | Out-Null

javac --release 17 --module-source-path src -d mods --module demo.api,demo.app,demo.provider

javac --release 17 -d launcher LayerResolutionDemo.java

java -cp launcher LayerResolutionDemo mods
```

Similar `javac` and `java` commands can be used on macOS/Linux after creating the two output directories `mods`, `launcher` with `mkdir -p mods launcher`. `--module-source-path src` specifies where the named modules' source directories live; `-d mods` outputs each module into `mods/demo.api`, `mods/demo.app`, `mods/demo.provider`; `ModuleFinder.of(Path.of(args[0]))` reads those modules directly from the `mods` directory.

**Exact stdout, compiled with `javac --release 17` and run with `java`:**

```text
resolve=demo.api,demo.app
resolveAndBind=demo.api,demo.app,demo.provider
resolve providers=0
resolveAndBind providers=1
```

These numbers and names have clear meanings:

1. With `roots = Set.of("demo.app")`, `resolve` adds `demo.api` due to `requires`; the provider is not a root and is not requested by any module in that branch.
2. `resolveAndBind` observes `uses demo.api.Greeting` on `demo.app` and `provides ... with ...` on `demo.provider`, so it adds `demo.provider` to `Configuration`.
3. `defineModulesWithOneLoader` creates runtime layers from each graph. These two layers differ despite using the same boot parent layer and identical module files.
4. `ServiceLoader.load(plainLayer, type)` finds no providers because `demo.provider` is not present in that layer or its ancestors.
5. `ServiceLoader.load(boundLayer, type)` finds one provider in the named module brought in by service binding.

**Example scope limitation:** the `mods` directory contains only these three modules and the boot layer has no provider for `demo.api.Greeting`. In a real system, a provider might already be resolved because it is a root, via another `requires` edge, or already present in a parent layer; in that case `resolve` can also yield an available provider. Therefore, do not conclude “`resolve` always returns 0 providers”.

## 6. When Can resolve Still Find a Provider?

Comparing the two APIs can lead to an overgeneralized conclusion that **`resolve` is incompatible with `ServiceLoader`**. In reality, it still works whenever the provider has already been brought into the configuration by another mechanism.

### Provider Is in roots

If an operator explicitly selects plugins:

```java
Set<String> roots = Set.of("demo.app", "demo.provider");
Configuration explicit = boot.resolve(
    finder, ModuleFinder.of(), roots);
```

This snippet uses the `boot` and `finder` variables from the example. `resolve` can now bring both consumer and provider into the graph because `demo.provider` is an **explicit root**, without needing inference from `uses`. This approach fits when a product needs a fixed or administrator-approved provider list.

### Provider Is Already in a Parent Layer

A provider may already be resolved in `ModuleLayer.boot()` or a parent layer. `ServiceLoader.load(layer, type)` searches the specified layer and its ancestors, so it can still find the provider even if the child configuration does not list the provider name in `modules()`. `Configuration.findModule(...)` can also locate modules from parent configurations when applicable, whereas `modules()` lists only new modules.

### Provider Is an Explicit Dependency

If another root has `requires demo.provider`, `resolve` will resolve that dependency. However, for plugin architectures, forcing the consumer at compile time to depend on a specific provider typically sacrifices substitutability. Use a `requires` edge only when there is a genuine API/module dependency, not to compensate for missing service binding.

Key distinction: **`resolveAndBind` is the mechanism that automatically pulls in observable providers matching `uses`/`provides`; `resolve` does so only if another dependency path or root causes that module to be resolved.**

## 7. “Present on the Module Path” Is Not Enough: The Role of ModuleFinder

`ModuleFinder` defines which **module definitions are observable** for resolving dependencies and services. When using:

```java
ModuleFinder before = ModuleFinder.of(Path.of("plugins"));
ModuleFinder after = ModuleFinder.of();
Configuration result = ModuleLayer.boot().configuration()
        .resolveAndBind(before, after, Set.of("demo.app"));
```

This is a conceptually standalone snippet: the `plugins` directory must contain appropriate module files; if `demo.app` or its dependencies are missing, resolution may fail.

Understand the limits:

- If a provider JAR **is not in any appropriate finder**, `resolveAndBind` cannot conjure it up.
- The resolver looks up roots/dependencies in `before` → parent configurations → `after` order; wrong configuration/paths can select an unintended module/version.
- When the same module name appears in multiple sources, you must know the finder/parent rules and verify the selected artifact/version. `resolveAndBind` **is not a dependency conflict resolver**.
- Binding can pull in **all modules providing a relevant service that the finder discovers**; it does not guarantee a single provider or a stable priority order among modules.
- The resolver must also satisfy readability, package consistency, and constraint requirements; because service binding adds modules, configuration errors can arise that `resolve` did not hit.

If multiple plugins exist, do not rely on service binding picking the “first provider”. Put selection policy (capabilities, version, provider ID, permissions, priority order) in a registry and inspect `ServiceLoader.Provider.type()`/metadata per contract. When only one provider is allowed, check the count and report a configuration error if violated.

### Service Binding Does Not Bypass Encapsulation

The consumer module should `requires` the module exporting the service API, as well as `uses` the service. The provider module must have a valid `provides` declaration. `exports`, accessibility, and package/module consistency rules are still enforced; resolving a provider module does not turn all of its packages into public API for the consumer.

## 8. When to Use resolve vs. resolveAndBind?

| Need | Sensible Choice | Reason |
| --- | --- | --- |
| Build a graph from selected roots and explicit module dependencies | `resolve` | Exact module scope per roots/`requires` |
| Load extension providers via `uses`/`provides` without the consumer knowing implementation modules | `resolveAndBind` | Attaches service-use to module resolution |
| Plugin deployment already has an allowlist and operator-selected root modules | `resolve` with explicit roots, or `resolveAndBind` on a restricted finder | Keeps selection policy in the plugin management tier |
| Need to automatically discover multiple available providers in a plugin repository | `resolveAndBind` | Adds provider modules and their dependencies by services |
| Want to discover/instantiate service instances | `ServiceLoader` after the layer exists | Resolution does not automatically instantiate providers |
| Want to swap a running plugin | Create a new configuration/layer/snapshot per lifecycle | `ServiceLoader.reload()` does not add unresolved modules into an old layer |

**Extensibility consideration:** in systems with many untrusted plugins, avoid using `resolveAndBind` with an overly broad finder just to “auto-scan everything”. Service binding can bring additional modules/dependencies into the graph; you must verify artifact provenance, API compatibility, versions, permissions, and provider instantiation. If plugins must be constrained, configure finders/roots/policies in a controlled way.

## 9. Common Errors and Misconceptions

### “The provider JAR is present, yet ServiceLoader returns empty”

Ask these questions in order:

1. Is the JAR a valid **named module** with `module-info.java` declaring `provides`?
2. Does the consumer named module declare `uses` for the service, and does it have `requires` to the module exporting the service API?
3. Does `ModuleFinder` actually see the provider JAR?
4. Was the configuration created with `resolve` or `resolveAndBind`, and is the provider another root/dependency?
5. Does `Configuration.modules()` contain the provider? Is the provider in a parent layer?
6. Was the runtime `ModuleLayer` created from the right configuration?
7. Does `ServiceLoader.load(layer, serviceType)` receive **the right service `Class`** belonging to the matching layer/module identity?

For a named module, omitting `uses` on the module calling `ServiceLoader` can cause `ServiceConfigurationError`; with the module layer API, an unnamed launcher like in the example can call the service validly. Additionally, the provider must be instantiable or supply a valid provider method; instantiation errors are detected **when `ServiceLoader` actually loads/instantiates**, not at resolution time.

### “resolveAndBind automatically creates provider objects”

Wrong. Binding only adds **module definitions** to the graph. Only after defining the layer does `ServiceLoader` handle discovery and lazy instantiation. With `stream()`, you can read `Provider.type()` without calling `Provider.get()`; with `iterator()`, iteration instantiates providers. Do not rely on side effects in provider constructors during resolve/configuration.

### “ServiceLoader will automatically pick up a plugin just dropped into the directory”

Not inside a fixed layer. `ServiceLoader.reload()` clears that loader's cache; it does not mutate `Configuration` or define new named modules. For a new plugin absent from the graph, you generally need a new `ModuleFinder`/configuration/layer along with a cutover and lifecycle management process.

### “resolveAndBind forces the consumer to read the implementation directly”

Wrong. Bringing a provider into the graph and **reading packages/classes via module readability** are two separate relationships. The consumer typically keeps `requires demo.api` and `uses demo.api.Greeting`; it needs neither `requires demo.provider` nor exported implementation packages.

### “resolveAndBind always adds exactly one provider”

Wrong. Binding depends on **service-use of new modules and parents**, along with the providers available in the finder. There might be zero providers; there might be multiple providers; the process can iterate and pull in extra modules via other dependencies/services. Inspect the result and enforce selection policies in your registry.

### “If resolve succeeds, the layer will definitely build and the provider will run”

Not enough. `resolve`/`resolveAndBind` can throw `FindException` or `ResolutionException` for an invalid graph; **defining the layer** can fail due to loader/package errors; **`ServiceLoader`** can throw `ServiceConfigurationError` when locating or instantiating providers. Log causes by exact stage.

## 10. Step-by-Step Diagnosis Without Confusing the Three Phases

```text
ModuleFinder
   |
   | discovers module definitions
   v
Configuration.resolve / resolveAndBind
   |
   | graph: roots, requires, [service binding]
   | potential: FindException / ResolutionException
   v
ModuleLayer.defineModulesWithOneLoader / WithManyLoaders
   |
   | runtime modules and class loader mapping
   | potential: layer/class loader errors
   v
ServiceLoader.load(layer, Service.class)
   |
   | lazy discover and instantiate providers
   | potential: ServiceConfigurationError
   v
Registry / application uses service instance
```

Observation tips:

- Before resolution, record **root names**, finder paths, and approved module versions; avoid automatically logging sensitive paths.
- After resolution, inspect `configuration.modules().stream().map(ResolvedModule::name)` and the `reads()` graph when needed; remember `modules()` excludes parent configurations.
- After creating the layer, inspect `layer.modules()` and `layer.findModule(name)`; distinguish “resolved module” from “module in the actual layer”.
- With `ServiceLoader`, use `stream().map(ServiceLoader.Provider::type)` to inspect provider types before selecting and calling `get()`. Do not rely on counts from `ServiceLoader.load(Class)` using a TCCL that differs from the layer under inspection.
- If adding service binding causes an error, check which new provider modules were selected and which of their dependencies are missing or conflicting; do not immediately blame the interface.

In runtime configurations with reload/hot deployment, **do not reuse classes and provider instances from an old layer as if they belonged to the new layer**: the same fully qualified class name can be a distinct type if defined by a different loader. Manage snapshots/provider ownership, in-flight requests, and resources when switching layers.

## 11. Pre-Production Checklist

- [ ] Consumer declares `requires` for the service API and `uses` for the consumed service.
- [ ] Provider has exact `provides ... with ...` and dependency on the service API.
- [ ] Roots and `ModuleFinder` scope are clearly defined; providers must be observable.
- [ ] Choose `resolve` if you want to keep only roots/requirements; choose `resolveAndBind` if provider modules should be added via service binding.
- [ ] Remember service binding also checks `uses` in parent configurations and can iteratively add multiple modules.
- [ ] Verify `configuration.modules()`, parent configurations, and module versions before defining the layer.
- [ ] Define the layer from the right configuration, pick an appropriate class loader, and use the right service `Class<S>` in that context.
- [ ] Verify providers with `ServiceLoader` on the exact layer; handle 0, 1, or multiple providers per policy.
- [ ] Catch and classify resolution, layer definition, and service discovery/instantiation errors separately.
- [ ] For dynamic plugins, manage layer versions, resources, and in-flight calls when swapping providers.

### Official Java 17 Documentation

- [`Configuration.resolve` and `Configuration.resolveAndBind`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/Configuration.html)
- [`ModuleLayer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html)
- [`ServiceLoader.load(ModuleLayer, Class)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
- [`ModuleFinder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html)

**Remember:** `resolve` follows **roots + requires**, whereas `resolveAndBind` expands the result with **service-use/service-provider binding**; both only build a `Configuration`. Afterward you still must **define a layer and use `ServiceLoader`** to get actual providers. Separating these steps cleanly makes plugin design flexible, keeps scope easy to control, and makes it straightforward to debug when a provider fails to appear.