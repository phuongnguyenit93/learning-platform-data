# ModuleLayer and the Set of Defined Modules in Java (JPMS)

`ModuleLayer` is the object that represents a **runtime module layer** in the Java Platform Module System (JPMS). Each layer contains a set of *defined* modules, associated with a `Configuration` and the corresponding class loaders. Understanding this set properly helps you determine which modules actually belong to a layer, which modules are found through a parent layer, and why a module present on disk is not necessarily present at runtime.

> Examples use JDK 17 or later. The `ModuleLayer` API appeared in Java 9; some snippets use `Stream.toList()`, so choose JDK 17+ to run them as written.

## 1. Lesson Objectives

After this lesson, you can:

- Distinguish between *discovered*, *resolved*, and *defined* modules in a layer.
- Retrieve a layer's direct `Set<Module>` using `modules()`.
- Use `findModule()` to look up a module in the current layer or ancestor layers, and know when the result differs from `modules()`.
- Inspect `Module.getLayer()`, `ModuleLayer.parents()`, and `ModuleLayer.configuration()`.
- Create a child layer and observe its set of defined modules with a runnable JPMS example.

## 2. What Does “Defined Module” Mean?

The lifecycle of bringing a module into existence can be viewed across three levels:

1. **Discovery:** `ModuleFinder` locates modules on the module path or another module source and provides `ModuleReference` objects. Being found does not mean a module has joined the application.
2. **Resolution:** `Configuration` represents the resolved module graph, consisting of `ResolvedModule` entries and dependency relationships. Resolution determines a valid configuration.
3. **Definition:** when creating a `ModuleLayer` from a `Configuration`, the JVM creates `java.lang.Module` objects and maps them to class loaders. Those `Module` objects are the **defined modules in the layer**.

Types to distinguish:

| Object | Role | Example of how to obtain it |
| --- | --- | --- |
| `ModuleReference` | Information about a module discovered by a finder | `ModuleFinder.find("com.example.greeter")` |
| `ResolvedModule` | A module in the resolution graph | `configuration.modules()` |
| `Module` | A runtime module, bound to a class loader and possibly belonging to a layer | `layer.modules()` |
| `ModuleLayer` | A group of runtime `Module` instances along with parent layer relationships | `ModuleLayer.boot()` |

Key point: `ModuleLayer.modules()` returns **the `Module` objects defined directly in that layer**. It does not list every JAR in a directory, does not return every JDK module, and does not automatically merge modules from parent layers.

Model example:

```text
Child layer
└── com.example.greeter       ← belongs to child.modules()
         │
         │ parent layer
         ▼
Boot layer
├── java.base                 ← belongs to boot.modules()
├── java.logging              ← if resolved in the boot layer
└── ...                       ← depends on how the application is launched
```

When you call `child.modules()`, you only get the modules defined in the child layer. When you call `child.findModule("java.base")`, you can still find `java.base` in the boot layer through the chain of parent layers.

## 3. Important APIs

| API | Return value and meaning |
| --- | --- |
| `ModuleLayer.boot()` | The boot layer set up by the JVM when the program starts |
| `layer.modules()` | An unmodifiable `Set<Module>`, containing only modules defined **in the current layer** |
| `layer.findModule(name)` | `Optional<Module>`; searches the current layer, then parent layers |
| `layer.parents()` | List of direct parent layers; a layer can have multiple parents |
| `layer.configuration()` | The `Configuration` used to define the layer's modules |
| `layer.findLoader(name)` | The class loader of the named module defined in the layer; a name not belonging to the layer may cause `IllegalArgumentException` |
| `module.getLayer()` | The layer containing that `Module`; may be `null` if the module does not belong to any layer |
| `module.getName()` | The module name; modules defined in a layer are named modules |
| `module.getDescriptor()` | Metadata of a named module, including name, packages, exports, requires, etc. |
| `module.getClassLoader()` | The class loader associated with the module; may be `null` when using the bootstrap class loader |

Distinguish carefully: `layer.configuration().modules()` is the set of `ResolvedModule` instances of the configuration, whereas `layer.modules()` is the set of `Module` instances at runtime. The two sets represent two different stages even though they may correspond by module name.

## 4. Inspecting Modules in the Boot Layer

The following example runs as an ordinary Java class without needing a `module-info.java`:

```java
import java.lang.Module;
import java.lang.ModuleLayer;
import java.util.Comparator;
import java.util.Set;

public class InspectBootLayer {
    public static void main(String[] args) {
        ModuleLayer boot = ModuleLayer.boot();
        Set<Module> defined = boot.modules();

        System.out.println("Number of modules in boot layer: " + defined.size());

        defined.stream()
               .sorted(Comparator.comparing(Module::getName))
               .forEach(module -> System.out.printf(
                   "%-35s | in boot layer: %s%n",
                   module.getName(),
                   module.getLayer() == boot
               ));

        Module javaBase = boot.findModule("java.base").orElseThrow();
        System.out.println("Name: " + javaBase.getName());
        System.out.println("Layer: " + javaBase.getLayer());
        System.out.println("Descriptor: " + javaBase.getDescriptor().name());
    }
}
```

Run:

```bash
javac InspectBootLayer.java
java InspectBootLayer
```

Explanation:

- `boot.modules()` provides the set of runtime modules in the boot layer.
- `getLayer() == boot` confirms the modules being iterated are actually defined in the boot layer.
- `findModule("java.base").orElseThrow()` makes sense because `java.base` is the mandatory foundational module.
- The module count and printed list may differ across runs: it depends on the JDK, runtime image, module path, root modules, and how the JVM resolves modules at startup.

Do not equate the output of `java --list-modules` with `ModuleLayer.boot().modules()`. The first command shows modules observable in the runtime image/module path; the second call shows modules actually defined in the boot layer of the **running process**.

## 5. How Do `modules()` and `findModule()` Differ?

Suppose `child` is a child layer that only defines the module `com.example.greeter`, while `java.base` belongs to the boot layer:

```java
Set<Module> local = child.modules();

boolean baseDefinedHere = local.stream()
        .anyMatch(module -> module.getName().equals("java.base"));
// false: java.base is not defined in child

boolean baseFoundThroughParents =
        child.findModule("java.base").isPresent();
// true: found in an ancestor layer

Module greeter = child.findModule("com.example.greeter").orElseThrow();
boolean greeterDefinedHere = greeter.getLayer() == child;
// true
```

These are two different questions:

- **“Which modules does this layer itself define?”** Use `layer.modules()` or filter by `module.getLayer() == layer`.
- **“From this layer, can a module named X be looked up in the layer hierarchy?”** Use `layer.findModule("X")`.

`findModule()` checks the current layer and then searches through parent layers. In diagrams with multiple parents, layers should be understood as a **directed acyclic graph (DAG)**, not necessarily a simple tree. If you need to know exactly where a module belongs, check `module.getLayer()` after finding it.

Modules with the same name can appear as different `Module` objects when defined in independent layers. Therefore, when comparing runtime modules, **a module name cannot substitute for layer and class loader context**.

## 6. Complete Example: Creating a Child Layer and Retrieving Its Module Set

This example builds a named module `com.example.greeter` into a modular JAR, resolves it, and defines it in a child layer. This layer uses the boot layer as its parent.

### 6.1. Directory Structure

```text
module-layer-demo/
├── src/
│   └── com.example.greeter/
│       ├── module-info.java
│       └── com/
│           └── example/
│               └── greeter/
│                   └── Greeter.java
└── LayerDemo.java
```

File `src/com.example.greeter/module-info.java`:

```java
module com.example.greeter {
    exports com.example.greeter;
}
```

File `src/com.example.greeter/com/example/greeter/Greeter.java`:

```java
package com.example.greeter;

public final class Greeter {
    private Greeter() {}

    public static String hello() {
        return "Hello from a module in the child layer!";
    }
}
```

Use a separate program to define the child layer. File `LayerDemo.java`:

```java
import java.lang.Module;
import java.lang.ModuleLayer;
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public class LayerDemo {
    public static void main(String[] args) throws Exception {
        // 1) Parent layer: modules already initialized at boot time.
        ModuleLayer parent = ModuleLayer.boot();

        // 2) Discover modular JARs in the mlib directory.
        ModuleFinder finder = ModuleFinder.of(Path.of("mlib"));

        // 3) Resolve the root module and its dependencies.
        Configuration configuration = parent.configuration().resolve(
                finder,
                ModuleFinder.of(),
                Set.of("com.example.greeter")
        );

        // 4) Define the configuration's modules in a child layer.
        ModuleLayer child = parent.defineModulesWithOneLoader(
                configuration,
                ClassLoader.getSystemClassLoader()
        );

        // 5) modules() only lists modules defined in child.
        System.out.println("Modules in child:");
        child.modules().stream()
                .map(Module::getName)
                .sorted()
                .forEach(System.out::println);

        Module greeterModule = child.findModule("com.example.greeter")
                .orElseThrow();
        System.out.println("Greeter belongs to child: "
                + (greeterModule.getLayer() == child));

        // java.base is in parent, but child.findModule can still find it.
        boolean baseDefinedInChild = child.modules().stream()
                .anyMatch(m -> m.getName().equals("java.base"));
        boolean baseFound = child.findModule("java.base").isPresent();
        System.out.println("Child itself defines java.base: "
                + baseDefinedInChild);
        System.out.println("Child finds java.base: " + baseFound);
        System.out.println("Direct parents contain boot layer: "
                + child.parents().contains(parent));

        // 6) Load the class using the class loader bound to the child's module.
        ClassLoader loader = child.findLoader("com.example.greeter");
        Class<?> type = loader.loadClass("com.example.greeter.Greeter");
        System.out.println(type.getMethod("hello").invoke(null));
    }
}
```

Steps to run in the `module-layer-demo` directory (create the two output directories beforehand):

```bash
mkdir out
mkdir mlib
javac -d out src/com.example.greeter/module-info.java src/com.example.greeter/com/example/greeter/Greeter.java
jar --create --file mlib/com.example.greeter.jar -C out .
javac LayerDemo.java
java LayerDemo
```

Typical output:

```text
Modules in child:
com.example.greeter
Greeter belongs to child: true
Child itself defines java.base: false
Child finds java.base: true
Direct parents contain boot layer: true
Hello from a module in the child layer!
```

Why is there this difference?

1. `ModuleFinder` discovers `com.example.greeter` in `mlib`.
2. `resolve(...)` creates a configuration based on `parent.configuration()`. The dependency on `java.base` is satisfied by the parent configuration; therefore `java.base` does not need to be defined again in `child`.
3. `defineModulesWithOneLoader(...)` defines the modules belonging to the new configuration in `child` and binds them to the class loader created for the layer.
4. `child.modules()` only has `com.example.greeter` in this example, while `child.findModule("java.base")` can look down into the parent layer hierarchy.

Note: the program is run with `java LayerDemo`, without adding the JAR in `mlib` as a root module of the boot layer. This approach makes it clear that the module is loaded via the child layer.

## 7. Getting the Direct Module List and the List from Parent Layers

To collect module names **only for the current layer**, you can write:

```java
Set<String> localNames = child.modules().stream()
        .map(Module::getName)
        .collect(java.util.stream.Collectors.toUnmodifiableSet());
```

If the goal is actually to gather modules defined in the current layer **and all ancestors**, traverse through `parents()`. The example below avoids duplicate visits when multiple branches share a parent layer:

```java
import java.lang.Module;
import java.lang.ModuleLayer;
import java.util.ArrayDeque;
import java.util.Collections;
import java.util.Deque;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.Set;

public class LayerModules {
    public static Set<Module> collectIncludingParents(ModuleLayer start) {
        Set<ModuleLayer> visitedLayers = new HashSet<>();
        Set<Module> result = new LinkedHashSet<>();
        Deque<ModuleLayer> queue = new ArrayDeque<>();
        queue.add(start);

        while (!queue.isEmpty()) {
            ModuleLayer layer = queue.removeFirst();
            if (!visitedLayers.add(layer)) {
                continue;
            }
            result.addAll(layer.modules());
            queue.addAll(layer.parents());
        }

        return Collections.unmodifiableSet(result);
    }
}
```

Usage:

```java
Set<Module> local = child.modules();
Set<Module> acrossLayers = LayerModules.collectIncludingParents(child);

System.out.println("Direct module count: " + local.size());
System.out.println("Module count including ancestors: " + acrossLayers.size());
```

Notes when representing results:

- A `Set<Module>` preserves runtime module identity. If you only collect a `Set<String>` by `getName()`, you may accidentally merge distinct modules that share the same name across different layers.
- `parents()` returns direct parent layers; you must keep traversing if you want to inspect all ancestors.
- Collecting modules across multiple layers is only for **observation/inventory**; it does not mean every module shares the same readability relationships, the same class loader, or the same package accessibility.

## 8. Relation to Configuration, Class Loaders, and Accessibility

### `Configuration` Determines What Gets Resolved

`configuration.modules()` contains the set of `ResolvedModule` instances for the corresponding configuration. It describes the selected dependency graph, not the runtime `Module` objects.

```java
Configuration cf = child.configuration();

System.out.println("Resolved in child's configuration:");
cf.modules().stream()
        .map(resolved -> resolved.name())
        .sorted()
        .forEach(System.out::println);

System.out.println("Defined in child:");
child.modules().stream()
        .map(Module::getName)
        .sorted()
        .forEach(System.out::println);
```

In a simple example, the two lists of names may be identical, but their object types and meanings differ. When searching in a configuration with a parent, `Configuration.findModule(name)` also allows querying through ancestor configurations; that does not cause ancestor modules to appear in `configuration.modules()` of the current configuration.

### Class Loaders Bound to Modules

When a layer is defined, JPMS establishes a module → class loader mapping. Some API options:

- `defineModulesWithOneLoader(...)`: the new layer's modules are defined with a single class loader.
- `defineModulesWithManyLoaders(...)`: a different class loader model, typically one loader per module.
- `defineModules(...)`: lets you provide a function mapping module names to class loaders according to a specific design.

To load a class from a module in a child layer, get the loader from the right place:

```java
ClassLoader loader = child.findLoader("com.example.greeter");
Class<?> greeter = loader.loadClass("com.example.greeter.Greeter");
```

Do not assume that `Class.forName("com.example.greeter.Greeter")` using the application class loader will see every module in a custom layer. Beyond whether a class can be loaded, member access also depends on `exports`, `opens`, and proper module readability rules.

### Having a Module in a Layer Does Not Mean “Permission to Use Every Class”

`modules()` and `findModule()` serve to inspect runtime structure, not to replace JPMS access control:

- `requires` expresses dependencies and affects module readability.
- `exports` allows access to public types in exported packages.
- `opens` relates to deep reflection, according to the opened scope.
- `Module.canRead(other)` checks the runtime read relationship toward another module.

Therefore, finding a `Module` does not guarantee that the current code can directly import every package or reflect into private members of that module.

## 9. Common Misconceptions

**Misconception 1: `ModuleLayer.boot().modules()` is all modules installed in the JDK.**

In reality, it only reflects modules defined in the boot layer of the current run. Modules present in the runtime image or on the module path that are not resolved/defined will not appear automatically.

**Misconception 2: `child.modules()` includes the parent's modules.**

False. Use `child.findModule(name)` to look up across ancestors, or actively traverse `parents()` if you want to inventory multiple layers.

**Misconception 3: If `ModuleFinder` sees a JAR, the layer already has the module.**

False. Discovery, resolution, and definition are distinct steps. There must be an appropriate `Configuration` and a layer definition step before you obtain the runtime `Module` instances of that layer.

**Misconception 4: If a module is in `modules()`, default `Class.forName()` will work.**

Not necessarily. A module in a custom layer may belong to another loader. Obtain the proper loader with `findLoader()` for the module in the layer, then also consider JPMS access rules.

**Misconception 5: Having the same `getName()` guarantees it is the same `Module`.**

Not true in a multi-layer system. Always also consider the layer, class loader, and `Module` object identity when determining runtime identity.

**Misconception 6: You can add modules into `layer.modules()`.**

No. The returned value is an unmodifiable set. An already-defined layer is not updated by adding elements to the set; to get a new set of modules, build an appropriate configuration and layer.

## 10. Practice Exercises

**Exercise 1.** Run `InspectBootLayer` twice: once normally and once with a launch configuration that has different root modules. Compare the module names in `boot.modules()` and explain the differences in terms of the modules resolved at boot.

**Exercise 2.** In `LayerDemo`, add these lines:

```java
System.out.println(child.modules().contains(
        child.findModule("java.base").orElseThrow()));
System.out.println(child.findModule("java.base")
        .orElseThrow().getLayer() == ModuleLayer.boot());
```

The results are `false` and `true`, respectively: finding `java.base` through the parent does not make that module part of the child layer's directly defined set.

**Exercise 3.** Write a method `printLocalModules(ModuleLayer layer)` that prints the name and class loader name of each module in the layer in alphabetical order. For modules managed by the bootstrap loader, handle `getClassLoader() == null`.

**Exercise 4.** Create two separate child layers from the same modular JAR, both using the boot layer as parent. Retrieve the `com.example.greeter` module from each layer and compare `getName()`, `getLayer()`, and object identity. Through this, observe that module name and runtime module identity are two different concepts.

## 11. Takeaways

- `ModuleLayer` is a **runtime** structure containing defined named modules and relationships with parent layers.
- `layer.modules()` returns **only** the `Set<Module>` defined directly in the layer, without automatically aggregating ancestors.
- `layer.findModule(name)` searches both the current layer and parent layers; use `module.getLayer()` to know the exact place of definition.
- `Configuration.modules()` contains `ResolvedModule` entries; `ModuleFinder` discovers modules; `ModuleLayer.modules()` contains runtime `Module` objects.
- Finding a module does not automatically grant read access, exports, opens, or the ability to load classes with an arbitrary loader.

**API reference:** `java.lang.ModuleLayer`, `java.lang.Module`, `java.lang.module.Configuration`, `java.lang.module.ModuleFinder`, and `java.lang.module.ResolvedModule` in the JDK documentation.
