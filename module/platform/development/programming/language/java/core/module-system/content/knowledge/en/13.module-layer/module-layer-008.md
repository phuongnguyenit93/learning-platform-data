# Querying `ModuleLayer` with `findModule` and `modules`

## Objectives

After this lesson, you can:

- Look up a module defined in a `ModuleLayer` by name using `findModule(String)`.
- List the modules belonging to **the current layer itself** using `modules()`.
- Distinguish searching across parent layers from listing the modules of a single layer.
- Handle `Optional<Module>` results safely and recognize the limitations of both APIs when working with the Java Platform Module System (JPMS).

## 1. What Is `ModuleLayer`?

In JPMS (Java 9+), `ModuleLayer` represents a group of modules that have been **defined at runtime** along with parent relationships between layers. Each named module belonging to a layer is a `java.lang.Module` object. Layers help applications organize groups of modules, such as plugins loaded into a child layer, while still relying on system modules in a parent layer.

The JVM's startup layer can be obtained via:

```java
ModuleLayer boot = ModuleLayer.boot();
```

Which modules are present in `boot` depends on runtime configuration, the module graph resolved at startup, and the JDK distribution; `java.base` is an example guaranteed to belong to a normal modular Java environment. You should not assume every JDK module appears in a layer under every launch configuration.

Two APIs commonly used to inspect a layer are:

```java
Optional<Module> findModule(String name);
Set<Module> modules();
```

Both query modules already present in the layer; they **do not search for JARs on disk, do not resolve configurations, and do not create new layers**.

## 2. `findModule(String name)` — Looking Up a Module by Name

`findModule` takes a **module name** (`String`) and returns an `Optional<Module>`:

```java
ModuleLayer boot = ModuleLayer.boot();

Optional<Module> maybeBase = boot.findModule("java.base");
Module base = maybeBase.orElseThrow();
System.out.println(base.getName()); // java.base

Optional<Module> missing = boot.findModule("com.example.does.not.exist");
System.out.println(missing.isPresent()); // false
```

Safe usage depending on your goal:

- `ifPresent(...)` when the module is optional and only needs handling if it exists.
- `orElseThrow(...)` when a missing module is a business/application error.
- `map(...)` or `flatMap(...)` when transforming the value while preserving presence/absence semantics.
- `isPresent()` or `isEmpty()` to check existence; `isEmpty()` has been available since Java 11.

Example avoiding calling `Optional.get()` without checking:

```java
String requestedName = "java.sql";
ModuleLayer boot = ModuleLayer.boot();

boot.findModule(requestedName).ifPresentOrElse(
    module -> System.out.println("Found: " + module.getName()),
    () -> System.out.println("Module is not yet in this layer or its parent layers")
);
```

`Optional.ifPresentOrElse` has been available since Java 9. The argument must be a **module name** such as `java.base` or `com.example.payment`, not a package name, class name, or file path.

### Search Scope: Current Layer and Parent Layers

`layer.findModule(name)` first searches for the module in the `layer` being queried. When not found there, the API continues searching in **parent layers**. Therefore, the result may be a module belonging to a parent layer, not belonging to `layer.modules()`.

Visualizing the structure:

```text
Boot layer
  ├── java.base
  └── ...modules resolved at startup
        ↑
Plugin layer
  └── com.example.plugin
```

When querying from the plugin layer:

- `pluginLayer.findModule("com.example.plugin")` can return the plugin layer's module.
- `pluginLayer.findModule("java.base")` can return `java.base` from the parent boot layer.
- `pluginLayer.modules()` contains only the modules defined in the plugin layer.

For layers with multiple parents, do not rely on duplicate module names across parent branches to infer a single module by name. When you need to know which layer a module actually belongs to, check `module.getLayer()` or work directly with `modules()` on the desired layer.

## 3. `modules()` — Listing Modules Belonging to the Layer Itself

`modules()` returns an **unmodifiable** `Set<Module>` consisting of the modules defined in the layer on which it is called.

```java
ModuleLayer boot = ModuleLayer.boot();
Set<Module> bootModules = boot.modules();

System.out.println("Number of modules in boot layer: " + bootModules.size());

bootModules.stream()
    .map(Module::getName)
    .sorted()
    .forEach(System.out::println);
```

Points to remember:

1. The set does not include modules present only in parent layers.
2. Iteration order of `Set` is not module-name order. Use `sorted()` if you need deterministic, readable, or testable output.
3. The returned set does not allow `add`/`remove`. To filter or accumulate, create another collection.
4. A valid layer may contain **0 modules**; in that case `modules().isEmpty()` is `true`.
5. `Set<Module>` holds the actual `Module` objects; when printing information, extract the name with `Module::getName` or access metadata via `getDescriptor()` if needed.

Example filtering modules by name prefix:

```java
List<String> javaModules = ModuleLayer.boot().modules().stream()
    .map(Module::getName)
    .filter(name -> name.startsWith("java."))
    .sorted()
    .toList(); // Stream.toList() available since Java 16

System.out.println(javaModules);
```

For Java 9–15, replace `.toList()` with `.collect(Collectors.toList())` and import `java.util.stream.Collectors`.

## 4. Quick Comparison of the Two Methods

| Question | `findModule(String)` | `modules()` |
|---|---|---|
| What is it for? | Looking up **one** module by name | Getting **all** modules defined in the layer |
| Return type | `Optional<Module>` | `Set<Module>` |
| Module in current layer | Can be found | Included in set |
| Module only in parent layer | Can be found | Not included in set |
| Not found / empty layer | `Optional.empty()` | Empty `Set` |
| Modifies module graph? | No | No |
| Suitable scenario | Checking a module by name, obtaining a `Module` object | Counting, filtering, listing a layer's modules |

**Common reasoning mistake:** seeing `layer.findModule("java.base").isPresent() == true` and concluding that `layer.modules()` contains `java.base`. That is only true if `java.base` is actually defined in that layer itself. For a child layer, the module may come from a parent.

## 5. Standalone Runnable Example: Boot Layer and Empty Layer

Save as `LayerQueryDemo.java`:

```java
import java.util.Optional;
import java.util.Set;

public class LayerQueryDemo {
    public static void main(String[] args) {
        ModuleLayer boot = ModuleLayer.boot();

        // Look up a specific module.
        Optional<Module> javaBase = boot.findModule("java.base");
        System.out.println("Is java.base in boot? " + javaBase.isPresent());

        // List boot modules, printing at most 10 names.
        Set<Module> bootModules = boot.modules();
        System.out.println("Number of modules in boot: " + bootModules.size());
        bootModules.stream()
            .map(Module::getName)
            .sorted()
            .limit(10)
            .forEach(name -> System.out.println(" - " + name));

        // Special empty layer has no modules and no parents.
        ModuleLayer empty = ModuleLayer.empty();
        System.out.println("empty.modules().isEmpty(): "
            + empty.modules().isEmpty());
        System.out.println("empty.findModule(\"java.base\").isPresent(): "
            + empty.findModule("java.base").isPresent());

        // A Module object knows which layer owns it.
        javaBase.ifPresent(module ->
            System.out.println("java.base belongs to boot: "
                + (module.getLayer() == boot)));
    }
}
```

Run with JDK 9 or later:

```bash
javac LayerQueryDemo.java
java LayerQueryDemo
```

Conclusions you can confirm from the example:

- `boot.findModule("java.base")` finds `java.base`.
- `boot.modules()` gives the set of modules defined in boot, with the count depending on the environment.
- `ModuleLayer.empty()` contains no modules and has no parents to continue searching: both queries yield empty results.
- `module.getLayer() == boot` checks the definition location of the returned module.

## 6. Distinguishing Parent-Traversing Lookup from Listing the Entire Layer Tree

Suppose the application has a `pluginLayer` created from a `Configuration` with `boot` as its parent layer. Then:

```java
// pluginLayer is a valid child ModuleLayer created earlier.
Optional<Module> baseFromParent = pluginLayer.findModule("java.base");
Set<Module> localOnly = pluginLayer.modules();

boolean javaBaseDefinedHere = localOnly.stream()
    .anyMatch(m -> "java.base".equals(m.getName()));
```

`baseFromParent` can contain `java.base` even though `javaBaseDefinedHere` is `false`. This is especially important when writing a plugin system, where you want to distinguish plugin modules from foundational modules.

If the requirement is to **list every module of the layer and all parent layers**, calling `modules()` once is not enough. Traverse `parents()` and combine the module sets:

```java
import java.util.ArrayDeque;
import java.util.Collections;
import java.util.Deque;
import java.util.IdentityHashMap;
import java.util.LinkedHashSet;
import java.util.Set;

public class ModuleLayerTree {
    public static Set<Module> collectModules(ModuleLayer start) {
        Set<ModuleLayer> visited =
            Collections.newSetFromMap(new IdentityHashMap<>());
        Set<Module> collected = new LinkedHashSet<>();
        Deque<ModuleLayer> queue = new ArrayDeque<>();
        queue.add(start);

        while (!queue.isEmpty()) {
            ModuleLayer layer = queue.removeFirst();
            if (!visited.add(layer)) {
                continue;
            }
            collected.addAll(layer.modules());
            queue.addAll(layer.parents());
        }

        return Collections.unmodifiableSet(collected);
    }
}
```

Reason for using `visited`: parent relationships can form a **directed acyclic graph** with multiple branches pointing to the same ancestor, so a parent layer may be encountered along multiple paths. `IdentityHashMap` here marks each `ModuleLayer` object already visited. If you only want to count the modules of **a single layer**, use `layer.modules().size()` directly—no traversal helper is needed.

## 7. What the APIs Do Not Do for You

### Do Not Automatically Load Modules

`findModule("com.example.plugin")` returns empty if that module has not yet been defined in the layer or its parent layers, even if a JAR with the corresponding name exists on disk. To create a new layer with application modules, the general workflow is:

1. Identify module artifacts using `ModuleFinder`.
2. Resolve a `Configuration` from root modules and parent configurations.
3. Define a new `ModuleLayer` with suitable class loaders.
4. Only then use `findModule` and `modules` on the created layer.

### Not Equivalent to Access Permissions

Finding a `Module` does not prove the calling module **can read** that module or access packages inside it. When you need to check at the module level:

```java
Module caller = LayerQueryDemo.class.getModule();

boot.findModule("java.base").ifPresent(target -> {
    System.out.println("Can caller read java.base? "
        + caller.canRead(target));
    System.out.println("Is package java.lang exported to caller? "
        + target.isExported("java.lang", caller));
});
```

In the snippet above, `boot` is an initialized variable (`ModuleLayer.boot()`). `canRead` checks the readability relationship; `isExported` checks whether a package is exported to the calling module. Checks for whether a package is opened for reflection use `isOpen` accordingly. These are distinct concepts from whether **a module exists in a layer**.

### Do Not Confuse with `Configuration.findModule`

- `ModuleLayer.findModule(String)` returns `Optional<Module>`, representing the runtime module after definition.
- `Configuration.findModule(String)` returns `Optional<ResolvedModule>` and belongs to the module graph resolution stage.

Use `Configuration` when you need to work with the resolved configuration; use `ModuleLayer` when you want to inspect runtime modules.

## 8. Common Errors and How to Handle Them

| Symptom | Common cause | What to do |
|---|---|---|
| `findModule(...)` is empty despite JAR file on disk | The JAR has not been resolved/defined into an appropriate layer | Check the `Configuration` and `ModuleLayer` creation steps |
| `findModule(...)` has a value but `modules()` does not contain it | The module is in a parent layer | Compare `module.getLayer()` with the layer being inspected |
| `modules().add(...)` throws `UnsupportedOperationException` | The returned set is unmodifiable | Copy into a `HashSet`/`LinkedHashSet` if needed |
| Listing order changes | `Set` does not guarantee presentation order | `map(Module::getName).sorted()` |
| Calling `optional.get()` throws `NoSuchElementException` | No module was found | Use `orElseThrow` with a message or `ifPresent` |
| Searching a class/package name fails to find a module | `findModule` only accepts module names | Determine the module name from `module-info.java` or the descriptor |

## 9. Practice

1. Using `ModuleLayer.boot()`, look up `java.base` and a nonexistent module name; print distinct messages for the two cases.
2. Print the names of all modules starting with `java.` in the boot layer, in lexicographical order.
3. Write a function `boolean isLocalModule(ModuleLayer layer, String name)` to check whether a module belongs to **the layer itself**, based on `modules()`. Compare with the result of `layer.findModule(name).isPresent()` when you have a child layer.
4. Given a layer with a parent, try `collectModules(layer)` and compare the number of collected modules with `layer.modules().size()`; explain why the two numbers can differ.

Hint for Exercise 3:

```java
static boolean isLocalModule(ModuleLayer layer, String name) {
    return layer.modules().stream()
        .anyMatch(module -> name.equals(module.getName()));
}
```

## Takeaways

- `findModule(name)` searches for a module by name in the current layer **and parent layers**; the result is `Optional<Module>`.
- `modules()` returns an unmodifiable `Set<Module>` of **the current layer itself**.
- To determine which layer a module resides in, use `module.getLayer()`; to list across parent layers, traverse `parents()` yourself.
- Both APIs support **querying the runtime state** of JPMS; they do not automatically resolve, load modules, or grant module read/access permissions.

JDK API reference: `java.lang.ModuleLayer`, `java.lang.Module`, `java.lang.module.Configuration`, and `java.lang.module.ModuleFinder`.