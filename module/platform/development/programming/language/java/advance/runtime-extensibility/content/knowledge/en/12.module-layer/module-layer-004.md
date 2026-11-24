# Looking Up Modules, Loaders, and Parent Layer Relationships

## 1. Context: ModuleLayer in a Plugin System

A `ModuleLayer` is a set of modules resolved and defined at runtime, along with relationships to parent layers. The boot layer is created when the JVM starts; a host can create additional layers to load plugins later. Each layer has a `Configuration` (the resolved module graph) and the actual modules defined with one or more class loaders.

Three questions must be distinguished:

1. **Which modules are in a layer?** Use `layer.modules()` or `layer.findModule(name)`.
2. **Which class loader is used to load a module?** Use `layer.findLoader(name)` when the module belongs to that exact layer; use `Module.getClassLoader()` when you already have the `Module` object.
3. **Is a module found in the current layer or a parent layer?** Use `layer.parents()` to traverse the tree/graph of relationships; `findModule` can search across ancestors.

A layer is not synonymous with a class loader. Multiple modules can be defined in one loader or split across multiple loaders, depending on the choice made when creating the layer. Named modules have their own identity and readability; a new layer is not by default a security sandbox or a hot-unload mechanism.

## 2. Important Lookup APIs

| API | Result | Key Things to Remember |
|---|---|---|
| `ModuleLayer.boot()` | Boot layer of the current JVM | Does not automatically change when plugins are loaded later |
| `layer.modules()` | `Set<Module>` directly belonging to the layer | Does not return all modules of ancestors |
| `layer.findModule("name")` | `Optional<Module>` | Searches in the layer and ancestor layers |
| `layer.findLoader("name")` | `ClassLoader` for a module defined in the layer | Can throw `IllegalArgumentException` if the module is not defined **in this layer** |
| `layer.parents()` | `List<ModuleLayer>` of direct parents | A layer can have multiple parents; do not assume a single one |
| `layer.configuration()` | Resolved `Configuration` | Different from loading classes or creating instances |
| `module.getLayer()` | Layer containing the named module (if any) | For an unnamed module, the value is `null` |
| `module.getClassLoader()` | Defining loader of the module | Can be `null` for modules defined by the bootstrap loader |
| `Class.getModule()` | Module owning the class | Useful when debugging which class was actually loaded |

**Common pitfall:** `layer.findModule(name)` searches parent layers as well; however, `layer.findLoader(name)` requires the module name to belong to **the layer itself**. Therefore, a module obtained via `findModule` is not guaranteed to be valid for calling `findLoader` on the layer being inspected. Obtain the `Module` object, check `module.getLayer()`, and call `module.getClassLoader()` if needed.

## 3. Runnable Example on Java 17+: Inspecting the Boot Layer

Create the file `BootLayerInspect.java`:

```java
import java.lang.ModuleLayer;
import java.util.Comparator;

public final class BootLayerInspect {
    public static void main(String[] args) {
        ModuleLayer boot = ModuleLayer.boot();
        Module javaBase = boot.findModule("java.base").orElseThrow();

        System.out.println("java.base present: " + boot.modules().contains(javaBase));
        System.out.println("java.base layer is boot: " + (javaBase.getLayer() == boot));
        System.out.println("java.base loader is bootstrap: "
                + (javaBase.getClassLoader() == null));
        System.out.println("boot parent count: " + boot.parents().size());

        boot.modules().stream()
                .map(Module::getName)
                .filter(name -> name.startsWith("java."))
                .sorted(Comparator.naturalOrder())
                .limit(3)
                .forEach(name -> System.out.println("sample: " + name));
    }
}
```

Compile and run:

```bash
javac BootLayerInspect.java
java BootLayerInspect
```

The output has these stable lines:

```text
java.base present: true
java.base layer is boot: true
java.base loader is bootstrap: true
boot parent count: 1
```

The `sample:` list depends on the set of modules resolved by the launcher and environment, so do not hardcode the entire stdout. The boot layer has `ModuleLayer.empty()` as its parent; this is a special empty layer. Do not conclude that every system module resides in the boot layer: only resolved modules appear in `modules()`.

## 4. Complete Example: Creating a Plugin Layer and Tracing Parent Layers

We create `demo.api` containing an interface, `demo.plugin` containing a provider, and a host that creates a new layer. The main goal is to observe layer, module, and class loader relationships; no network or framework is needed.

Directory tree:

```text
layer-demo/
├── src-api/
│   ├── module-info.java
│   └── demo/api/Greeter.java
├── src-plugin/
│   ├── module-info.java
│   └── demo/plugin/HelloGreeter.java
└── Host.java
```

`src-api/module-info.java`:

```java
module demo.api {
    exports demo.api;
}
```

`src-api/demo/api/Greeter.java`:

```java
package demo.api;

public interface Greeter {
    String greet(String name);
}
```

`src-plugin/module-info.java`:

```java
module demo.plugin {
    requires demo.api;
    provides demo.api.Greeter with demo.plugin.HelloGreeter;
}
```

`src-plugin/demo/plugin/HelloGreeter.java`:

```java
package demo.plugin;

import demo.api.Greeter;

public final class HelloGreeter implements Greeter {
    public HelloGreeter() {}
    @Override public String greet(String name) {
        return "Hello, " + name;
    }
}
```

`Host.java` (host application running on the class path):

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;
import java.util.ServiceLoader;

public final class Host {
    public static void main(String[] args) {
        ModuleLayer parent = ModuleLayer.boot();
        ModuleFinder finder = ModuleFinder.of(Path.of("mods/plugin"));
        Configuration config = parent.configuration().resolve(
                finder, ModuleFinder.of(), Set.of("demo.plugin"));

        ModuleLayer child = parent.defineModulesWithOneLoader(
                config, ClassLoader.getSystemClassLoader());

        Module plugin = child.findModule("demo.plugin").orElseThrow();
        Module api = child.findModule("demo.api").orElseThrow();

        System.out.println("child owns plugin: " + child.modules().contains(plugin));
        System.out.println("child owns api: " + child.modules().contains(api));
        System.out.println("plugin layer is child: " + (plugin.getLayer() == child));
        System.out.println("api layer is parent: " + (api.getLayer() == parent));
        System.out.println("child parent is boot: " + (child.parents().get(0) == parent));
        System.out.println("plugin loader matches: "
                + (child.findLoader("demo.plugin") == plugin.getClassLoader()));

        // The API resides in the boot layer; DO NOT call child.findLoader("demo.api").
        ServiceLoader<demo.api.Greeter> services =
                ServiceLoader.load(child, demo.api.Greeter.class);
        for (demo.api.Greeter service : services) {
            System.out.println(service.greet("JPMS"));
        }
    }
}
```

**Configuration condition:** For `demo.api` to be present in the boot layer when running the class path host, the API module must be added to the module path and resolved via `--add-modules demo.api`. The host is code belonging to the unnamed module and is allowed to use public APIs exported from `demo.api`. The plugin resides in a separate JAR not on the boot module path; `ModuleFinder` only reads that JAR when creating the child layer.

Compile and package with JDK 17+ from the `layer-demo/` directory (POSIX shell commands):

```bash
mkdir -p build/api build/plugin mods/api mods/plugin
javac -encoding UTF-8 -d build/api \
  src-api/module-info.java src-api/demo/api/Greeter.java
jar --create --file mods/api/demo.api.jar -C build/api .
javac -encoding UTF-8 --module-path mods/api -d build/plugin \
  src-plugin/module-info.java src-plugin/demo/plugin/HelloGreeter.java
jar --create --file mods/plugin/demo.plugin.jar -C build/plugin .
javac --module-path mods/api --add-modules demo.api Host.java
java --module-path mods/api --add-modules demo.api -cp . Host
```

Exact output in the model above:

```text
child owns plugin: true
child owns api: false
plugin layer is child: true
api layer is parent: true
child parent is boot: true
plugin loader matches: true
Hello, JPMS
```

`child.findModule("demo.api")` finds the API module from the parent layer even though `child.modules()` does not contain it. This is an important distinction between **visible via ancestors** and **defined in this layer**.

With a different design, for example not resolving the API in the parent, `resolve(...)` might place the API into the child's configuration if the finder has the API module. In that case, ownership results differ. Always inspect the actual graph and class loader rather than applying a rigid assumption.

## 5. Parent Layer Relationships and Configuration Graphs

`ModuleLayer` is organized as a directed acyclic graph by parent relationships. Parent layers can share modules across branches; a layer can have multiple parents if created with the corresponding API.

Distinguish:

- `layer.parents()`: list of **direct parents** of the runtime layer.
- `layer.configuration().parents()`: list of parent **configurations** used during resolution, reflecting the configuration graph.
- `layer.modules()`: modules defined directly in the layer.
- `layer.findModule(name)`: can return a module in the layer or ancestors, depending on the set of modules examined.

If you only need a specific module, `findModule` is the direct API. If you need to display the entire tree, you can traverse `parents()`, but you must avoid revisiting layers in a graph that has multiple paths to the same ancestor.

Sample utility illustrating ancestor traversal (placed inside a Java class that has imported `java.util.*`):

```java
static void printLayers(ModuleLayer root) {
    Set<ModuleLayer> seen = java.util.Collections.newSetFromMap(
            new java.util.IdentityHashMap<ModuleLayer, Boolean>());
    java.util.ArrayDeque<ModuleLayer> queue = new java.util.ArrayDeque<>();
    queue.add(root);
    while (!queue.isEmpty()) {
        ModuleLayer layer = queue.removeFirst();
        if (!seen.add(layer)) continue;
        System.out.println("modules=" + layer.modules().size());
        queue.addAll(layer.parents());
    }
}
```

This is an **illustrative code snippet**, not a standalone program. It uses an identity set to avoid repeatedly traversing the same layer in the graph.

## 6. Class Loaders and Module Types

JPMS allows multiple strategies for defining modules in a child layer:

| Creation Method | Characteristics |
|---|---|
| `defineModulesWithOneLoader` | Modules in the child configuration are defined using one loader managed by the layer creation mechanism; suitable when plugin dependencies can share a loader |
| `defineModulesWithManyLoaders` | Each module in the configuration is loaded via its own loader managed by the layer creation mechanism |
| `defineModules` | Allows mapping module names to loaders according to a custom policy |

The `ClassLoader` passed to `defineModulesWithOneLoader` is the **parent loader** of the new loader used by the layer creation mechanism; it does not mean the new loader is the exact object passed in. Therefore, the example checks `child.findLoader("demo.plugin") == plugin.getClassLoader()` and does not compare against `ClassLoader.getSystemClassLoader()`.

In a plugin model, the API contract should be defined once in a parent layer/loader visible to both the host and the provider. If the same binary name of an interface is defined by multiple loaders, casting or `ServiceLoader` can fail even when package and class names match.

Do not design host-plugin communication around package-private members across different loaders. A runtime package depends on the package name and the defining loader; named modules are also subject to `exports`/`opens` constraints.

## 7. Common Errors and Limitations

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `findModule(...)` returns empty | Module is not in the layer or searched ancestors | Check the root set, `ModuleFinder`, resolution, and layer parents |
| `findLoader(...)` throws `IllegalArgumentException` | Module resides in a parent layer or does not belong to the queried layer | Use `module.getLayer()` then query the loader on the owning layer, or `module.getClassLoader()` |
| Provider not found | Provider module not resolved, missing `provides`, inconsistent service API, wrong layer | Check the descriptor, `ServiceLoader.load(layer, ...)`, and the graph |
| `LayerInstantiationException` | Invalid loader/package/module configuration when defining the layer | Check for split packages, package mapping, and loader creation |
| `FindException` / `ResolutionException` | Module descriptor missing/wrong dependency, duplicate module, or invalid graph | Check module path, module names, and `requires` |
| `ClassCastException` / `ServiceConfigurationError` | Host and plugin see different copies of the API or provider has wrong type | Keep the API in the parent, avoid duplicate contracts |

**Correct observation:** `module.getClassLoader()` returning `null` is normal for modules defined by the bootstrap loader (such as `java.base`) and does not by itself indicate an error. `module.getLayer()` returns `null` for classes belonging to an unnamed module. Avoid using a loader's display name as an absolute identity.

## 8. Checklist When Adding a New Plugin

1. Identify which JARs are named modules, automatic modules, or class path artifacts.
2. Verify that `ModuleFinder.of(...)` sees the correct module names and version metadata.
3. Resolve the graph from `parentLayer.configuration()` with the right roots; verify required dependencies exist.
4. Create the child layer with the appropriate number of loaders; record the owner layer of each module.
5. Look up modules with `findModule`, and only use `findLoader` on the layer that directly defines them.
6. Use `ServiceLoader.load(layer, serviceApiClass)` and verify the provider is assignable to the shared API.
7. Have tests for missing providers, missing dependencies, duplicate module names, split packages, and activation failures.
8. Manage closing/stopping plugins, threads, and resources explicitly; creating a layer does not automatically unload or sandbox code.

**Remember:** `findModule` answers *where the module is in the layer graph*; `findLoader` answers *which loader belongs to a module directly in this layer*; `parents()` shows the path to preceding layers. Seeing a module in an ancestor does not mean it belongs to the current layer. Distinguishing these three accurately helps the host avoid loading duplicate APIs, picking the wrong loader, and losing providers in a plugin system.