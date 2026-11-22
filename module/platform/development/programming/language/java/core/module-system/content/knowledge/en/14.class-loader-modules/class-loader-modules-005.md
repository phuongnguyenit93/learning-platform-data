# Split Packages with Multiple ModuleLayers in Java

## 1. Objectives

When a Java application uses JPMS (Java Platform Module System) to load multiple plugins, library versions, or sets of modules per `ModuleLayer`, two modules may contain classes belonging to the same package, such as `com.example.plugin.internal`. This phenomenon is called a **split package**.

After this lesson, you will be able to:

- Distinguish package names, modules, class loaders, and layers when analyzing conflicts.
- Know when a split package causes an error during module resolution or during layer creation.
- Create two independent layers with the same package name while keeping their classes isolated.
- Choose an appropriate fix for a modular application or plugin system.

**Core idea:** a package does not necessarily need to have a globally unique name across the entire JVM. What matters is which modules are read together, and which class loader each module is mapped to. `ModuleLayer` establishes the module configuration scope; `ClassLoader` actually defines the classes.

## 2. Key Concepts to Understand

| Concept | Role |
| --- | --- |
| Package | A group of classes sharing a common name, such as `com.example.shared`. |
| Named module | A JPMS unit declared by `module-info.java`; contains a set of packages, `requires`, `exports`, `opens`, and services. |
| `Configuration` | The module graph after resolving dependencies and readability relationships. |
| `ModuleLayer` | A collection of modules defined from a `Configuration`, which can be linked to parent layers. |
| Class loader | Defines classes from bytecode. Two classes with the same fully qualified name defined by two different loaders are two different types. |
| Split package | The same package name appearing in two or more different modules or class sources. |

Two questions must be kept separate:

1. **Module resolution:** Can a module read two modules that both export the same package? If there is a readability conflict, resolution may fail.
2. **Class loader mapping:** Are multiple named modules containing the same package assigned to a single class loader? If so, Java cannot define them as separate modules in the same loader.

Do not assume "two layers having overlapping package names will always fail." Nor should you assume "using different layers guarantees no errors": dependency configuration, readability relationships, and loader selection still matter.

## 3. Where Do Split Packages Appear?

Consider two modules with the structure:

```text
module demo.plugin.alpha
  └── demo.plugin.impl.Greeter

module demo.plugin.beta
  └── demo.plugin.impl.Greeter
```

Both contain package `demo.plugin.impl`. The outcome depends on the configuration:

| Scenario | Outcome to note |
| --- | --- |
| Both modules are assigned to **one class loader** | Cannot both own that package in the loader; layer creation may throw `LayerInstantiationException`. |
| Both modules are in the same layer but assigned to **two separate loaders** | Can be defined if the module configuration is valid and no readability/export conflict arises. |
| Each module is in a **sibling layer**, each layer creating its own loader | Can share the same package name and even the same class name, while the two classes have different type identities. |
| One module reads two modules that both `exports` the same package to it | The resolver may throw `ResolutionException`, even if multiple loaders were intended. |
| Two classes have the same name but are loaded from different loaders | Different `Class<?>` objects; cannot be cast to each other merely because of the same class name. |

In particular, `defineModulesWithOneLoader(...)` **creates a new class loader** to define the modules in that layer configuration. The `parentLoader` parameter is only the parent loader for delegation. Two independent calls typically create two different defining loaders, even when passing the same `parentLoader`.

## 4. Runnable Example: Two Sibling Layers with the Same Package

We create two named modules with different names, the same package, and the same class name. They are loaded into two independent `ModuleLayer` instances sharing the boot layer as their parent layer.

### 4.1. Directory Structure

```text
project/
├── src/
│   ├── alpha/
│   │   ├── module-info.java
│   │   └── demo/plugin/impl/Greeter.java
│   ├── beta/
│   │   ├── module-info.java
│   │   └── demo/plugin/impl/Greeter.java
│   └── host/
│       └── LayerDemo.java
└── mods/                         # compiled output
```

File `src/alpha/module-info.java`:

```java
module demo.plugin.alpha {
    exports demo.plugin.impl;
}
```

File `src/alpha/demo/plugin/impl/Greeter.java`:

```java
package demo.plugin.impl;

public final class Greeter {
    public String message() {
        return "Hello from alpha";
    }
}
```

File `src/beta/module-info.java`:

```java
module demo.plugin.beta {
    exports demo.plugin.impl;
}
```

File `src/beta/demo/plugin/impl/Greeter.java`:

```java
package demo.plugin.impl;

public final class Greeter {
    public String message() {
        return "Hello from beta";
    }
}
```

Here, having both modules declare `exports demo.plugin.impl` is intentional: we want to observe the same package name in two isolated layer scopes. In real-world design, keep implementation packages unexported if the host does not need direct access.

### 4.2. Host Loading Each Module into a Layer

File `src/host/LayerDemo.java`:

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public final class LayerDemo {
    private static ModuleLayer loadLayer(String moduleName, Path modulePath) {
        ModuleLayer parent = ModuleLayer.boot();
        ModuleFinder finder = ModuleFinder.of(modulePath);

        Configuration config = parent.configuration().resolve(
                finder,
                ModuleFinder.of(),
                Set.of(moduleName)
        );

        // Each call creates a new loader for the newly defined layer.
        return parent.defineModulesWithOneLoader(
                config, ClassLoader.getSystemClassLoader()
        );
    }

    public static void main(String[] args) throws Exception {
        ModuleLayer alphaLayer = loadLayer(
                "demo.plugin.alpha", Path.of("mods", "demo.plugin.alpha")
        );
        ModuleLayer betaLayer = loadLayer(
                "demo.plugin.beta", Path.of("mods", "demo.plugin.beta")
        );

        Class<?> alphaClass = alphaLayer
                .findLoader("demo.plugin.alpha")
                .loadClass("demo.plugin.impl.Greeter");
        Class<?> betaClass = betaLayer
                .findLoader("demo.plugin.beta")
                .loadClass("demo.plugin.impl.Greeter");

        System.out.println(alphaClass.getName().equals(betaClass.getName()));
        System.out.println(alphaClass == betaClass);
        System.out.println(alphaClass.getClassLoader()
                == betaClass.getClassLoader());
        System.out.println(alphaClass.getModule().getName());
        System.out.println(betaClass.getModule().getName());
    }
}
```

`ModuleFinder.of(modulePath)` points to the compiled module directory containing `module-info.class`. Each `resolve(...)` selects only one plugin as the root; `defineModulesWithOneLoader(...)` on each load creates a loader for its respective layer.

### 4.3. Compiling and Running

Example commands for Bash (Java 11 and later; Java 17 or 21 LTS are both suitable):

```bash
mkdir -p mods/demo.plugin.alpha mods/demo.plugin.beta out/host

javac -d mods/demo.plugin.alpha \
  src/alpha/module-info.java src/alpha/demo/plugin/impl/Greeter.java

javac -d mods/demo.plugin.beta \
  src/beta/module-info.java src/beta/demo/plugin/impl/Greeter.java

javac -d out/host src/host/LayerDemo.java
java -cp out/host LayerDemo
```

Expected output:

```text
true
false
false
demo.plugin.alpha
demo.plugin.beta
```

Explanation:

- `true`: both classes have the same binary name `demo.plugin.impl.Greeter`.
- First `false`: they are two different `Class` objects.
- Second `false`: they were defined by two different loaders.
- Module names show that they genuinely belong to two different named modules.

This is a way to isolate two implementations with overlapping package names without renaming packages in the example. However, a `Greeter` object created by the alpha layer cannot be cast to `Greeter` from the beta layer.

## 5. What Happens If Both Modules Are Combined into the Same Layer?

If you put both modules into the same `Configuration` and try to assign **one** loader:

```java
ModuleLayer parent = ModuleLayer.boot();
ModuleFinder finder = ModuleFinder.of(
        Path.of("mods", "demo.plugin.alpha"),
        Path.of("mods", "demo.plugin.beta")
);
Configuration config = parent.configuration().resolve(
        finder,
        ModuleFinder.of(),
        Set.of("demo.plugin.alpha", "demo.plugin.beta")
);

// Both modules contain demo.plugin.impl:
ModuleLayer layer = parent.defineModulesWithOneLoader(
        config, ClassLoader.getSystemClassLoader()
);
```

With a configuration not rejected earlier at the resolution step, attempting to define one loader for both modules will fail with `LayerInstantiationException` due to the duplicate package. The exact message string depends on the JDK version.

You can switch to:

```java
ModuleLayer layer = parent.defineModulesWithManyLoaders(
        config, ClassLoader.getSystemClassLoader()
);
```

This method creates a separate loader for each module in the configuration, thereby resolving the **same package in the same loader** constraint. However, it does **not** eliminate module graph conflicts: if a module reads two modules that both export the same package to it, `Configuration.resolve(...)` can still fail before creating the layer.

The many-loaders option also carries costs: more class loaders, separated class versions, and difficulty sharing implementation types or static state. Do not use it merely to mask an unnecessary overlapping package design.

## 6. Why Can Resolution Fail Even with Different Loaders?

Suppose `demo.consumer` has:

```java
module demo.consumer {
    requires demo.plugin.alpha;
    requires demo.plugin.beta;
}
```

If both plugins `exports demo.plugin.impl` to `demo.consumer`, the consumer sees two modules providing the same package. JPMS does not allow a readability graph that results in one module seeing two exported packages with the same name. The resolver may report `java.lang.module.ResolutionException` with details about the conflicting modules and package.

Thus, you must distinguish:

- **Conflict at resolution:** invalid `requires`/`exports` relationships; a valid `Configuration` cannot be created.
- **Conflict at layer instantiation:** the configuration may be valid, yet mapping modules with duplicate packages to a shared loader is invalid.
- **Conflict when using classes:** even if both layers load successfully, classes from two loaders are not the same type; casts, reflection, or passing objects of the wrong type can fail.

Splitting layers is suitable when each plugin is resolved and loaded independently; the host only interacts with a stable shared API rather than directly `requires`-ing all plugin modules that contain overlapping packages.

## 7. Designing Plugins in the Right Direction

A generally easier-to-maintain architecture:

```text
Boot/parent layer
  └── demo.plugin.api
       └── demo.plugin.api.Plugin  (shared interface)
          ↑                    ↑
          │                    │
Child layer A             Child layer B
  demo.plugin.alpha         demo.plugin.beta
  loader A                  loader B
  demo.plugin.impl          demo.plugin.impl
```

Place the `Plugin` interface in an API module supplied by the parent layer; each plugin can use its own implementation package, or keep overlapping package names only in cases where isolation is truly needed. Each plugin declares its API dependency and provides an implementation:

```java
module demo.plugin.alpha {
    requires demo.plugin.api;
    provides demo.plugin.api.Plugin
        with demo.plugin.impl.AlphaPlugin;
}
```

In the other plugin, you can use:

```java
module demo.plugin.beta {
    requires demo.plugin.api;
    provides demo.plugin.api.Plugin
        with demo.plugin.impl.BetaPlugin;
}
```

The host can locate providers in each layer via `ServiceLoader.load(layer, Plugin.class)`, with `Plugin.class` loaded from the shared API module. Because the interface belongs to the same parent API module/loader, the host communicates through the stable `Plugin` type without casting between identically named implementation classes.

Some principles:

1. Place shared APIs, DTOs, and service contracts in the parent module/layer. Types passed across layer boundaries must have a unified class identity.
2. Keep overlapping package names only in implementation regions that are genuinely isolated. If you have access to edit the source code, giving each module unique package names is usually simpler.
3. Use `ModuleLayer.findLoader(moduleName)` to load classes of the right module; avoid assuming `ClassLoader.getSystemClassLoader()` can find every plugin.
4. Release references to `Class`, instances, threads, caches, `ServiceLoader`, and loaders when you want to unload a plugin. A layer has no `unload()` command; reclamation depends on the garbage collector and live references.
5. Do not treat `--add-reads`, `--add-exports`, or `--add-opens` as a fix for split packages. They adjust access, not turn two modules with duplicate packages into a single valid package in one loader.

## 8. Diagnosing Errors by Stage

| Symptom | Check first | How to address |
| --- | --- | --- |
| `ResolutionException` during `resolve` | Which module `requires` or simultaneously reads two sources exporting the same package? | Fix the module graph, split plugins across layers, or consolidate the package into one shared module. |
| `LayerInstantiationException` during `defineModulesWithOneLoader` | Do two modules in the configuration share the same package? | Use separate loaders if the architecture permits, or eliminate the split package. |
| `ClassNotFoundException` when loading a plugin | Are you invoking the loader of the right module/layer and is the module path correct? | Obtain the loader via `layer.findLoader(moduleName)`, verify the module name and compiled artifacts. |
| `ClassCastException` despite identical class names | Do both types have the same defining class loader? | Share interfaces/DTOs from the parent layer; do not cast across two copies of implementation classes. |
| `IllegalAccessException` or `InaccessibleObjectException` | Does the package have appropriate `exports`/`opens`? | Adjust access permissions according to actual need; do not confuse with split-package conflicts. |

To quickly inspect a class's origin at runtime:

```java
System.out.println(type.getName());
System.out.println(type.getModule());
System.out.println(type.getClassLoader());
System.out.println(type.getModule().getLayer());
```

When debugging, cross-check **(class name + module + loader + layer)**. Looking at only the package name or class name is usually not enough to explain why two objects are incompatible.

## 9. When Should You Use Which Solution?

- **Ordinary modular libraries and applications:** avoid split packages; consolidate the package into one named module, or rename packages by module. This is the easiest option to maintain.
- **Multiple plugins or multiple dependency versions needing to coexist:** consider sibling layers with separate loaders, keeping shared APIs in a parent layer and communicating via services/interfaces.
- **Multiple modules in one layer with overlapping packages:** `defineModulesWithManyLoaders` can help at the class-definition step, provided the resolution configuration has no readability conflicts; carefully weigh the cost of type isolation.
- **Packages present on both classpath and module path:** also check unnamed module behavior and delegation mechanisms. Do not assume you can move JARs from the classpath to the module path while keeping duplicate packages intact.

There is no single JVM flag that automatically resolves every split-package case. Determine whether the error lies in the **module readability graph** or **how classes are defined into class loaders** before choosing a fix.

## 10. Self-Check Questions

1. Two modules in two different layers both contain `com.example.util`: must this fail? **No**; examine the configuration and loaders as well.
2. Two modules contain the same package and are assigned to one loader: is this valid? **No**, for named modules defining the layer will hit a conflict.
3. Does `defineModulesWithManyLoaders` fix an error where a consumer reads two modules exporting the same package? **No**; a resolution error can still occur.
4. Are two classes named `demo.plugin.impl.Greeter` with different loaders the same type? **No**.
5. To pass data safely between two plugin layers, what should you do? **Use interfaces/DTOs from a shared API module in a parent layer**, or transfer data via an intermediate format such as JSON if full isolation is desired.

## 11. Key Takeaways

In JPMS, a split package can be an error at **resolution**, at **loader mapping when creating a layer**, or a source of confusion in **runtime type identity**. Splitting plugins into separate `ModuleLayer` instances with separate loaders can allow overlapping package names, yet it does not make two identically named classes the same class. The most stable design is to keep shared APIs in a parent layer and isolate implementations in child layers.
