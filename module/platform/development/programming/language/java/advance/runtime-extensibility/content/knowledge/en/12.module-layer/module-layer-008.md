# Using a New ModuleLayer for a New Plugin Group and Understanding Mutation Limits of an Existing Layer

## 1. The Plugin Runtime Problem with JPMS

In the Java Platform Module System (JPMS), a `ModuleLayer` is a set of resolved named modules associated with a `Configuration` and classloaders. A layer can have one or more parent layers. When a host needs to add or replace a group of plugins **after the application is already running**, the appropriate approach is to create a **new child layer**, rather than attempting to mutate the module list inside an existing layer.

For example, suppose a host is running plugin `report.plugin.v1`. When releasing `report.plugin.v2` or deploying a new group of providers, the host can:

1. Place the new modular JARs in an artifact repository or an authorized load directory.
2. Use `ModuleFinder` to locate modules and create a new `Configuration` based on the parent configuration.
3. Define a **new module layer** with corresponding classloaders.
4. Use `ServiceLoader.load(layer, Service.class)` to discover providers in that layer.
5. Route **new** requests to the new registry/providers after health checks pass.
6. Stop or drain old requests, close resources, and drop references to the old layer/loader when safe.

**Key takeaway:** this is a mechanism of *replacing by creating a new configuration/layer*, not mutating the old layer's module graph in place.

## 2. Distinguishing Module Path, Configuration, and ModuleLayer

| Concept | Function | Does It Automatically Change When Adding a JAR? |
| --- | --- | --- |
| JAR directory / module path | Artifact source for `ModuleFinder` | Files on disk may change, yet Java does not automatically reload |
| `ModuleFinder` | Discovers module descriptors from specified sources | Not a file watcher or hot-reload engine |
| `Configuration` | Describes the resolved module graph (module names, requirements, readability) | Does not add or remove modules after resolution |
| `ModuleLayer` | Binds a configuration to runtime modules and classloaders | Has no API to arbitrarily add or remove modules |
| `ServiceLoader` | Finds matching providers in a loader/layer | A loader must re-discover per API; does not turn an old module graph into a new one |
| Host registry | Decides which providers handle requests | Can be designed to swap via references/versions |

Java has bounded adjustment APIs such as `Module.addReads`, `Module.addExports`, and `Module.addOpens` for permitted cases. They are **not equivalent** to adding a new module to a `Configuration` or replacing bytecode of an already-defined module. Do not treat these APIs as hot-swapping a module graph.

## 3. Java 17+ Example: Creating a Dedicated Layer and Discovering Plugins

The example consists of three named modules: `demo.api` containing the service contract; `demo.host` running in the boot layer; and `demo.plugin` as a provider loaded from the `plugins/` directory into a **child layer**.

Structure:

```text
demo/
  src/
    demo.api/
      module-info.java
      demo/api/Greeter.java
    demo.host/
      module-info.java
      demo/host/Main.java
    demo.plugin/
      module-info.java
      demo/plugin/HelloGreeter.java
  plugins/
```

### 3.1. Contract Module

`src/demo.api/module-info.java`:

```java
module demo.api {
    exports demo.api;
}
```

`src/demo.api/demo/api/Greeter.java`:

```java
package demo.api;

public interface Greeter {
    String id();
    String greet(String name);
}
```

### 3.2. Host Module

`src/demo.host/module-info.java`:

```java
module demo.host {
    requires demo.api;
    uses demo.api.Greeter;
}
```

`src/demo.host/demo/host/Main.java`:

```java
package demo.host;

import demo.api.Greeter;
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        Path pluginDir = Path.of("plugins");
        ModuleFinder pluginFinder = ModuleFinder.of(pluginDir);
        ModuleLayer parent = ModuleLayer.boot();

        Configuration configuration = parent.configuration().resolve(
                pluginFinder, ModuleFinder.of(), Set.of("demo.plugin"));

        ModuleLayer layer = parent.defineModulesWithOneLoader(
                configuration, ClassLoader.getSystemClassLoader());

        List<Greeter> plugins = ServiceLoader.load(layer, Greeter.class)
                .stream()
                .map(ServiceLoader.Provider::get)
                .toList();

        if (plugins.size() != 1) {
            throw new IllegalStateException(
                    "Expected one provider, got " + plugins.size());
        }

        Greeter greeter = plugins.get(0);
        System.out.println("Plugin: " + greeter.id());
        System.out.println(greeter.greet("Java"));
        System.out.println("Plugin layer is boot: "
                + (greeter.getClass().getModule().getLayer() == parent));
    }
}
```

Here `resolve(pluginFinder, ModuleFinder.of(), roots)` uses `pluginFinder` as the **before finder**, an empty after finder, while the parent configuration supplies previously resolved modules (including `demo.api`). `defineModulesWithOneLoader` places the modules **of the new configuration** into a child loader whose parent is the system classloader. With the API module already in the boot layer, the plugin is instantiated and used through the same `Greeter` class identity.

### 3.3. Provider Module

`src/demo.plugin/module-info.java`:

```java
module demo.plugin {
    requires demo.api;
    provides demo.api.Greeter with demo.plugin.HelloGreeter;
}
```

`src/demo.plugin/demo/plugin/HelloGreeter.java`:

```java
package demo.plugin;

import demo.api.Greeter;

public final class HelloGreeter implements Greeter {
    public HelloGreeter() {}

    @Override
    public String id() {
        return "hello";
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

The provider package does not need `exports` solely to be instantiated by `ServiceLoader` via `provides ... with ...`. The host does not write `requires demo.plugin`; compile-time dependencies point only to the contract.

### 3.4. Compiling, Packaging, and Running

In the `demo` directory on a bash shell, using JDK 17+:

```bash
mkdir -p mods plugins
javac --module-source-path src -d mods --module demo.api,demo.host,demo.plugin
jar --create --file plugins/demo.plugin.jar -C mods/demo.plugin .
java --module-path mods/demo.api:mods/demo.host --module demo.host/demo.host.Main
```

Expected output:

```text
Plugin: hello
Hello, Java
Plugin layer is boot: false
```

On Windows, the module path separator is `;`, for example `--module-path "mods/demo.api;mods/demo.host"`. Crucially, **do not add `demo.plugin` to the boot module path in the final command**; the provider JAR is read via `ModuleFinder.of(Path.of("plugins"))` and lives in the child layer. In the compile command, `mods` is the output directory containing all three module directories.

**Why check for `false`?** The provider belongs to the named module `demo.plugin` defined in the child layer; `greeter.getClass().getModule().getLayer()` is not the boot layer. This result proves the host is using the module in the new layer rather than a provider copy accidentally present on the classpath/boot module path.

## 4. Creating a New Layer for the Next Version or Plugin Group

Suppose the host maintains an `ActivePlugins` registry referencing providers from layer A. When plugin B is deployed, the replacement flow can be:

```text
Release A                           Release B
Configuration A                     Configuration B
     |                                    |
ModuleLayer A                       ModuleLayer B
     |                                    |
Providers A                         Providers B
     |                                    |
active registry -------- atomic swap --> active registry
     |
drain A -> close A -> drop references
```

In an application, each artifact group/version should have its own directory, such as `plugins/release-001/` and `plugins/release-002/`. This reduces the risk of `ModuleFinder` or a classloader reading a JAR whose bytes are being overwritten mid-flight.

Java pseudo-code illustrating the handoff point (not a standalone program):

```java
record PluginSet(ModuleLayer layer, List<Greeter> providers) {}

AtomicReference<PluginSet> active = new AtomicReference<>();

void publish(PluginSet next) {
    PluginSet previous = active.getAndSet(next);
    // Coordinate so requests using previous complete,
    // then invoke plugin stop/close and drop references.
}
```

This snippet requires appropriate imports, fields, and lifecycle implementations; `AtomicReference` alone **does not guarantee draining**. Requests that already obtained `previous` may still be invoking old providers. To avoid stopping while requests remain in flight, use reference counting, leases, read-write coordination, or appropriate scheduling/quiescence.

### Can the Same Module Name Be Reused in Another Layer?

In many designs, **the same module name can exist in different module layers**, each layer having its own configuration/runtime module identity and classloader. This is useful when two plugin versions share the module name `demo.plugin`. However, it depends on parent/layer relationships and module resolution; you must never put **two copies with the same name** into **the same configuration** and expect the JVM to pick one by version. Separate artifacts/versions by finder and create distinct layers.

Keeping the service contract in a parent layer ensures both the new provider and the host share the same API identity. If each plugin layer carries its own copy of the service interface, classloader/type identities can mismatch and `ServiceLoader` will not return providers as expected.

## 5. Limitations of an Already-Created Layer

### 5.1. Cannot Add or Remove Named Modules in an Existing Layer

There is no `layer.addModule(jar)` or `layer.removeModule(name)` API. Once defined, a layer is tied to its resolved graph. Adding a JAR to `plugins/` **does not automatically bring the new module into layer A**. `ServiceLoader.reload()` only resets the discovery cache of a **`ServiceLoader` instance**; it does not cause the old layer to gain new modules.

To see new modules, you must resolve another configuration and define **another layer**, or use a separate classpath/classloader mechanism if the architecture does not rely on named modules.

### 5.2. Cannot Replace Already-Loaded Classes/Bytecode by Editing a JAR

Classes already defined by the JVM are not updated simply by overwriting a JAR file. A new module layer with a new classloader can load the new version, yet old objects, old classes, and in-flight requests using them still persist as long as references remain.

Even Java instrumentation/redefinition has its own constraints and is not a mechanism for altering a layer's module graph. For plugin upgrades, use a new layer + lifecycle handoff rather than assuming overwriting a JAR file equals hot reload.

### 5.3. Module Graph and Classloader Constraints

Module resolution can fail with `FindException` if a required module cannot be found or `ResolutionException` when the graph conflicts. Layer definition can throw `LayerInstantiationException` if the modules/classloaders mapping strategy is invalid (for example, package conflicts per loader).

Distinguish the APIs:

- `defineModulesWithOneLoader`: modules in the new configuration are placed on one loader; corresponding package conflicts must be avoided.
- `defineModulesWithManyLoaders`: each module in the new configuration receives its own loader.
- `defineModules`: callback mapping module names to classloaders; used when specific loader control is needed.

Do not arbitrarily use `defineModulesWithManyLoaders` to “ignore all split-package conflicts”: the resolver still checks the graph, and the classloader design must preserve service contracts and runtime type identity.

### 5.4. A Layer Is Not a Security Sandbox

Code across all plugins running in the same JVM still shares system properties, the heap, thread pools, file/network permissions, and native libraries; module encapsulation/readability alone does not grant different process permissions. Untrusted plugins require separate processes/containers and OS restrictions. Nor does a separate layer prevent a plugin from crashing the JVM or exhausting resources.

### 5.5. No Immediate Unload or close(ModuleLayer)

`ModuleLayer` **does not implement `AutoCloseable`** and has no `close()` to unload all modules; garbage collection can reclaim loader/class metadata only when no relevant references remain. Threads, thread-context-classloaders, `ThreadLocal`s, singleton registries, static state in parent loaders, callbacks, schedulers, and provider references can keep the old layer alive.

Lifecycle management should include stopping/closing providers, unregistering listeners, closing executor/file/network resources, dropping references, and checking for memory leaks. Do not promise “immediate unload succeeds” upon dropping references.

## 6. ServiceLoader Across Multiple Layers

`ServiceLoader.load(layer, Service.class)` searches for providers in the specified layer and its ancestors per the API mechanism; do not mistake this for a way to arbitrarily pick all providers from **every sibling layer**. If the host creates two sibling layers A and B, manage a separate registry for each group or combine them explicitly.

Example when switching to layer B:

```java
ServiceLoader<Greeter> loader = ServiceLoader.load(layerB, Greeter.class);
List<Greeter> selected = loader.stream()
        .map(ServiceLoader.Provider::get)
        .toList();
```

This illustrative snippet sits inside a method where `layerB` is a `ModuleLayer` with corresponding imports. `ServiceLoader` keeps its own cache; it does not turn layer A into B. When provider prioritization is needed, apply the host's policy over the loaded providers rather than relying on discovery order.

Because the host holds references to provider instances, wrapper/registry classes should associate each provider with its **version/layer** to avoid mixing objects across different class identities. If a plugin returns classes from plugin-private packages, avoid exposing those classes as shared public API unless a clear data-conversion contract exists.

## 7. Issues with Dependencies and Service APIs

A new plugin group may comprise multiple mutually dependent modules. The new modules must be resolved in **the same appropriate configuration** if they need to use one another in the same graph. When `rootSet` is incomplete, dependencies absent from the module finder/parent can cause resolution to fail.

Place each kind of dependency as follows:

| Component | Appropriate Location | Reason |
| --- | --- | --- |
| Shared service interfaces / standard DTOs | Parent layer (`demo.api`) | Preserve shared class identity |
| Host implementation | Boot/host layer | Prevent plugins from owning host lifecycle |
| Plugin-private dependencies | New layer if modularized, or dedicated custom classloader | Reduce version conflicts |
| Plugin providers | New layer | Can be replaced per group/version |
| Registry selecting active plugin | Host | Orchestrate requests and version switchover policy |

JPMS named modules do not automatically resolve all library conflicts, especially when legacy libraries are automatic modules with split packages or improperly modularized dependencies. Inspect module descriptors with `jar --describe-module`, run the final artifacts, and test resolution of the exact layer.

## 8. Common Errors

| Symptom | Cause | Fix |
| --- | --- | --- |
| Added plugin JAR yet old layer still does not see it | Layer graph does not change after creation | Resolve and define a new layer |
| `ServiceLoader` returns 0 providers | Missing `provides`, wrong root/layer, module not resolved | Check descriptor, finder, layer, and use the right overload |
| `FindException: Module ... not found` | Module/dependency not visible to finder or parent | Fix module path/finder, module name, and root set |
| `ResolutionException` | Module graph has conflicting constraints | Fix split packages, readability, and graph |
| New plugin throws `ClassCastException` with API | Plugin has a duplicate copy of service API or different classloader identity | Keep contract in parent and unify type identity |
| Closed JAR yet loader/layer is not GC'd | Threads, caches, listeners, or object references retain it | Stop providers and drop all references |
| Requests run wrong version after swap | Registry swapped before in-flight requests drained | Use leases/ref-counts and lifecycle handoff |
| Replaced JAR file yet old bytecode still runs | JVM already defined classes in the old layer | Load the new version in a new layer/classloader |

## 9. Safe Implementation Checklist

- [ ] Keep shared service contracts in a parent layer.
- [ ] Separate artifacts by release/version and verify actual modular JARs.
- [ ] Create `ModuleFinder` with explicit artifact sources.
- [ ] Resolve a new `Configuration` from the parent configuration with the right root modules.
- [ ] Choose an appropriate loader strategy (`one`, `many`, custom).
- [ ] Use `ServiceLoader.load(newLayer, Service.class)` and verify provider identity.
- [ ] Verify health/compatibility of the new group before publishing.
- [ ] Swap registry/routing in a thread-safe manner; drain old requests.
- [ ] Invoke stop/close and clean up `ThreadLocal`, TCCL, listeners, executors, and caches.
- [ ] Do not expect `reload()` or swapping JAR files to mutate an existing layer.
- [ ] Use process isolation if strong permission, CPU/memory, or fault isolation is required.

**Conclusion:** `ModuleLayer` supports an architecture with **multiple plugin versions/groups via distinct layers**. Each layer is a resolved and defined module configuration; when you want to change module composition, create a new layer and transition consumers to it in a controlled manner. You cannot update an old layer's module graph by adding or removing JARs in place.