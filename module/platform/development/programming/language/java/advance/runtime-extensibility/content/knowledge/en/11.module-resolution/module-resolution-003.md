# Selecting Root Modules and Parent Configuration from ModuleLayer.boot()

In the **Java Platform Module System (JPMS)**, an application can resolve new modules from a set of JARs or module directories and create a child **module layer** without placing all plugins into the boot layer up front when the JVM starts. The first two decisions in this process are:

1. **Root modules**: the modules whose names are specified as the starting points for resolution.
2. **Parent configuration**: the resolved module graph that the new layer is allowed to reference, typically obtained from `ModuleLayer.boot().configuration()`.

A wrong choice at this step can cause modules not to be found, dependencies not to be resolved, the wrong version to be selected, or the new layer to fail to build. This lesson focuses on **how to choose roots and parent configurations, how Java resolves dependencies, and the relationship between `Configuration` and `ModuleLayer`**.

## 1. Separating Four Key Concepts

| Concept | Java API | Role |
|---|---|---|
| **Root modules** | `Set<String> roots` | Set of module names where resolution should start, e.g. `Set.of("plugin.greeting")` |
| **Module finder** | `java.lang.module.ModuleFinder` | Finds observable module definitions, typically from directories/JARs |
| **Configuration** | `java.lang.module.Configuration` | Resolution result: set of `ResolvedModule` instances with module read edges (`reads`) and parent configuration references |
| **Module layer** | `java.lang.ModuleLayer` | Materializes a configuration into runtime `Module` objects and binds modules to class loaders |

**Key takeaway:** `Configuration.resolve(...)` only builds and validates the **module graph**. It **does not yet define the new modules in the JVM and does not load classes**. Only afterward do you call `ModuleLayer.defineModulesWithOneLoader(...)`, `defineModulesWithManyLoaders(...)`, or another layer-creation mechanism.

A typical workflow:

```text
JAR / exploded modules
        |
        v
ModuleFinder.of(paths...) ----- Set<String> roots
        |                              |
        +------------+-----------------+
                     |
                     v
ModuleLayer.boot() -> parent Configuration
                     |
                     v
Configuration.resolve(before, after, roots)
                     |
                     v
Child Configuration + readability graph
                     |
                     v
bootLayer.defineModulesWithOneLoader(childConfig, parentLoader)
                     |
                     v
Child ModuleLayer -> ClassLoader -> plugin class/provider
```

Two kinds of “parent” must be distinguished:

- **Parent `Configuration`**: where the resolver looks for already-resolved modules, carrying the `reads` relationships of the module graph.
- **Parent `ClassLoader`**: the loader passed when creating a layer to establish delegation for the new loader.

These two objects are **not the same**. Having the right loader still cannot fix a `requires` graph with a missing dependency; conversely, a successful configuration resolution does not guarantee the class loader fits every package/module.

## 2. What Does ModuleLayer.boot() Provide?

`ModuleLayer.boot()` returns the JVM's **boot layer**, created during JVM startup. The boot layer contains `java.base` and the **named modules that were actually resolved at startup**, with their corresponding class loaders. It is usually the convenient parent layer when creating additional layers.

```java
ModuleLayer bootLayer = ModuleLayer.boot();
Configuration parentConfig = bootLayer.configuration();
```

The snippet above is illustrative code inside a Java method; `import java.lang.module.Configuration;` is needed when placed in a standalone file.

Two different levels can be observed:

```java
// Module actually defined in the boot layer:
boolean hasBase = bootLayer.findModule("java.base").isPresent();

// Resolution graph and known modules in the boot configuration:
boolean baseResolved =
        parentConfig.findModule("java.base").isPresent();
```

Here `java.base` is always present in a standard JVM boot layer. However, **the boot layer is not equivalent to every module in the JDK or on disk**. A module present in the JDK image that was not resolved at startup does not automatically appear in `bootLayer.configuration()`. Likewise, plugin JARs placed in a `plugins` directory do not automatically join the boot layer merely because that directory exists.

**Why use the boot configuration as parent?** A plugin resolved after the JVM is running typically needs `requires java.base` and may need library modules already present in the boot layer. Setting `bootLayer.configuration()` as the parent allows the resolver to reuse appropriate modules in the parent graph instead of re-resolving them into the child configuration.

## 3. Selecting Root Modules Matching Requirements

A root is a **module name** in the `module-info.java` descriptor or an automatic module name (if using automatic JARs), **not a package name, class name, or path to a JAR**.

Example:

```java
Set<String> roots = Set.of("plugin.greeting");
```

If `module-info.java` contains:

```java
module plugin.greeting {
    requires java.logging;
    exports plugin.greeting;
}
```

then the root is `plugin.greeting`. The `java.logging` module is brought into the graph when the resolver processes `requires` if it is found under the lookup rules; **there is no need to manually add every dependency to `roots`**.

### 3.1. Principles for Selecting Roots

- Choose **the module containing the extension/entry point to be used**, based on metadata and the list of permitted modules.
- Use **explicit names** per use case. For example, `Set.of("plugin.csv", "plugin.json")` when actively needing both modules.
- Do not take all module names on disk as roots merely because they can be discovered: that can load unwanted extensions and increase conflicts.
- Do not guess module names from JAR filenames. For explicit modules, trust the name from the descriptor; for automatic modules, the derived name can change with the manifest/filename and should not be a long-term plugin contract.
- Control the source/version of each module and its `requires` demands before publishing the configuration.
- For mandatory plugins, do not leave `roots` empty as a fake “success”; for optional features, an empty list can be a state handled separately per application policy.

If a root is missing, the resolver typically reports `FindException`. If a root is already in the parent configuration, choosing between the module in the finder and the parent module depends on the **lookup order** explained in the next section; do not use `findModule()` on the result without distinguishing new modules from inherited ones.

### 3.2. Roots and Dependencies Are Not the Same Set

Suppose:

```text
plugin.report      (root)
  requires plugin.api
  requires java.logging
plugin.api         (module dependency)
java.logging       (may be in the boot configuration)
```

The appropriate input is usually `Set.of("plugin.report")`. The resolver will follow `requires` to find `plugin.api` and `java.logging`. If `plugin.api` is not in the finder or parent, resolution fails. If `java.logging` is already in the boot configuration, that module is reused from the parent and **is not defined again in the child configuration**.

`requires transitive` affects readability along the chain; `requires static` has special compile/runtime semantics. They do not change the principle: **roots define the starting points, and the resolver processes the module graph according to descriptors**.

## 4. Choosing Parent Configuration and Module Lookup Order

Common Java 17 pattern:

```java
ModuleLayer parentLayer = ModuleLayer.boot();

ModuleFinder before = ModuleFinder.of(Path.of("mods"));
ModuleFinder after = ModuleFinder.of(); // Empty finder
Set<String> roots = Set.of("plugin.greeting");

Configuration childConfig = parentLayer.configuration()
        .resolve(before, after, roots);
```

This is an illustrative snippet inside a method, requiring imports for `java.lang.module.Configuration`, `java.lang.module.ModuleFinder`, `java.nio.file.Path`, and `java.util.Set`.

For each root or dependency, `Configuration.resolve(...)`'s resolver uses the lookup order:

1. **`before` finder**: looks up the module in the priority source (e.g., `mods` directory or selected JAR set).
2. **Parent configurations**: searches in the order parents are supplied; with the instance method above, the only parent is `parentLayer.configuration()`.
3. **`after` finder**: searches when neither of the previous two sources has the corresponding module.

Precisely because `before` is checked first, it can supply a module with the same name as one already in the parent. Therefore, avoid arbitrarily letting plugins replace host library names/versions; decide clearly which source is authoritative, check for duplicate module names, and test with the exact runtime configuration.

`ModuleFinder.of()` **with no arguments** creates an empty finder, not one that searches the working directory. When system modules need to be looked up, Java also provides `ModuleFinder.ofSystem()`, but do not blindly add it to every pipeline: check which modules boot already resolved and how loaders/layers should be created for new modules. Not every JDK module absent from boot can arbitrarily be defined via a plugin loader.

### 4.1. Instance Method and Static Method Equivalent for a Parent

If `parent` is a `Configuration`:

```java
Configuration child = parent.resolve(before, after, roots);
```

then in terms of parent configuration it is equivalent to:

```java
Configuration child = Configuration.resolve(
        before, List.of(parent), after, roots);
```

The static syntax accepts a **list of parent configurations** and is useful when building a graph with multiple parents. Both snippets are separate illustrations inside a method with variables already declared; the second snippet requires `import java.util.List;`.

**Do not blindly substitute `Configuration.empty()` for the boot configuration** to “start clean” if the plugin must read host modules. An empty parent changes the entire set of available modules, may omit modules needed during resolution, and can cause layer creation to violate runtime module constraints.

## 5. Runnable JDK 17 Example: One Root and a Boot Parent

The following complete example has:

- A plugin module named `plugin.greeting` compiled as an **exploded module** in the `mods` directory.
- Host program `LayerRootsDemo` running on the classpath; the host explicitly selects root `plugin.greeting` from the `mods` directory.
- The host obtains the parent configuration via `ModuleLayer.boot().configuration()`, resolves the new module, and defines a child layer.
- Finally, the host obtains the module's class loader and invokes a public method in an `exports`ed package.

**Do not put the `mods` directory on `--module-path` when running the host in this example**: the host locates it via `ModuleFinder.of(Path.of("mods"))`.

### 5.1. Directory Structure

```text
project/
  LayerRootsDemo.java
  src/
    plugin.greeting/
      module-info.java
      plugin/
        greeting/
          Greeting.java
```

File `src/plugin.greeting/module-info.java`:

```java
module plugin.greeting {
    exports plugin.greeting;
}
```

File `src/plugin.greeting/plugin/greeting/Greeting.java`:

```java
package plugin.greeting;

public final class Greeting {
    private Greeting() {}

    public static String message() {
        return "Hello from plugin.greeting";
    }
}
```

File `LayerRootsDemo.java`:

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.lang.module.ResolvedModule;
import java.nio.file.Path;
import java.util.Set;

public class LayerRootsDemo {
    public static void main(String[] args) throws Exception {
        String rootName = "plugin.greeting";

        // 1. Boot layer is the parent layer; it does not auto-load this lesson's plugin.
        ModuleLayer boot = ModuleLayer.boot();
        Configuration parentConfig = boot.configuration();

        // 2. Only accept modules from the mods directory as a new source.
        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));
        if (finder.find(rootName).isEmpty()) {
            throw new IllegalStateException("Root missing: " + rootName);
        }

        // 3. Module name, not a path or class name.
        Set<String> roots = Set.of(rootName);

        // 4. Resolve the module graph, using the boot config as parent.
        Configuration childConfig = parentConfig.resolve(
                finder,
                ModuleFinder.of(),
                roots);

        // 5. Inspect what was actually resolved in the new configuration.
        var newModules = childConfig.modules().stream()
                .map(ResolvedModule::name)
                .sorted()
                .toList();

        // 6. Define the module at runtime using a new loader.
        ModuleLayer childLayer = boot.defineModulesWithOneLoader(
                childConfig,
                ClassLoader.getSystemClassLoader());

        // 7. Use the child layer's loader to get the plugin class.
        ClassLoader pluginLoader = childLayer.findLoader(rootName);
        Class<?> greeting = pluginLoader.loadClass(
                "plugin.greeting.Greeting");
        String message = (String) greeting
                .getMethod("message")
                .invoke(null);

        System.out.println("Boot has java.base: "
                + boot.findModule("java.base").isPresent());
        System.out.println("Boot has plugin.greeting: "
                + boot.findModule(rootName).isPresent());
        System.out.println("New modules: " + newModules);
        System.out.println("Child config sees java.base: "
                + childConfig.findModule("java.base").isPresent());
        System.out.println("Child layer owns plugin: "
                + childLayer.modules().stream()
                    .anyMatch(m -> m.getName().equals(rootName)));
        System.out.println("Message: " + message);
    }
}
```

### 5.2. Compile and Run

From the `project` directory, with JDK 17 or later:

```bash
javac --module-source-path src -d mods -m plugin.greeting
javac -d out LayerRootsDemo.java
java -cp out LayerRootsDemo
```

The first command creates `mods/plugin.greeting/module-info.class` and `mods/plugin.greeting/plugin/greeting/Greeting.class`. `ModuleFinder.of(Path.of("mods"))` can locate compiled exploded modules. The host is compiled separately and only `out` is put on the classpath when running.

**Exact** stdout with the structure above, when the application starts without preloading `plugin.greeting` into the boot layer:

```text
Boot has java.base: true
Boot has plugin.greeting: false
New modules: [plugin.greeting]
Child config sees java.base: true
Child layer owns plugin: true
Message: Hello from plugin.greeting
```

### 5.3. Reading the Output and Understanding Which Module Belongs to Which Layer

- `Boot has java.base: true`: `java.base` is placed into the boot layer by the JVM.
- `Boot has plugin.greeting: false`: the host runs only from classpath `out`; the plugin module was not resolved when the JVM started.
- `New modules: [plugin.greeting]`: `childConfig.modules()` returns **the modules belonging to the new configuration itself**, excluding `java.base` inherited from the parent.
- `Child config sees java.base: true`: `childConfig.findModule("java.base")` finds it in the **parent configuration**. This does not mean `java.base` was defined again in the child layer.
- `Child layer owns plugin: true`: the new layer actually owns a `Module` for `plugin.greeting`.
- `Message: ...`: the child layer's loader loads the class, and package `plugin.greeting` is `exports`ed by the module so its public method can be called from the host via reflection.

A very important check: **`Configuration.findModule(name)` can find modules in parent configurations**, whereas `Configuration.modules()` lists only the modules of the current configuration. Similarly, `ModuleLayer.findModule(name)` can search parent layers, while `ModuleLayer.modules()` lists only modules in that layer. When you need to know whether a module is **truly new**, do not rely solely on `findModule(...).isPresent()`.

### 5.4. What If the Root Does Not Exist?

Suppose `rootName` is changed to `plugin.unknown` while the `mods` directory does not contain that module:

- In the example, `finder.find(rootName)` returns `Optional.empty()` and the application reports `Root missing: plugin.unknown`.
- If you skip the separate preflight and call `resolve(...)` with a root not found across `before`, parents, and `after`, the API throws `FindException`.
- If the module exists but is missing a `requires` dependency, `resolve(...)` can also fail with `FindException` or report another error according to graph consistency.

This is a **module resolution** error, occurring **before** code calls `pluginLoader.loadClass(...)`. Therefore, distinguish it from `ClassNotFoundException`, access errors caused by `exports`/`opens`, and class initialization errors at a later stage.

## 6. Selecting Multiple Roots and Determining Inherited Dependencies

### 6.1. Two Modules Need to Be Activated

If the host independently needs two extensions:

```java
Set<String> roots = Set.of("plugin.greeting", "plugin.reporting");
Configuration childConfig = boot.configuration()
        .resolve(finder, ModuleFinder.of(), roots);
```

This is an illustrative snippet using the already-declared `boot` and `finder` variables; both modules must be observable in the finder or parent configuration per resolution rules. If `plugin.reporting` has `requires plugin.greeting`, specifying only `plugin.reporting` as the root can be sufficient to resolve both modules; there is no need to duplicate the root if `plugin.greeting` is merely a technical dependency. Conversely, if two modules provide two independent features with no `requires` between them, specifying only `plugin.reporting` as root will not automatically pull in `plugin.greeting`.

### 6.2. The Parent Already Has a Module Needed by the Plugin

Suppose `plugin.reporting` declares `requires java.logging;`. If `java.logging` is in the boot configuration, the new module can use the version already resolved there. If it is not in the boot configuration, the resolver must still find this module from `before` or `after`. **Do not assume `ModuleLayer.boot()` contains all Java SE modules.**

In a real deployment environment, verify:

- Does the runtime image include the required modules (`jlink` can produce minimal images)?
- At startup, which modules were actually placed in the boot layer?
- Does the extension require a host API module defined in the boot layer or another parent layer?
- Which modules must reside in the child configuration to avoid creating multiple incompatible copies of a shared API?
- Are the module path and versions pinned/controlled?

When a JDK module absent from boot is needed, consider startup configuration (`--add-modules`) or an appropriate finder/layer design instead of letting all system modules into the plugin layer indiscriminately.

### 6.3. Root Modules and Service Providers Are Two Different Concepts

`resolve(...)` relies on **roots and `requires`**. It does not automatically treat every provider declared with `provides ... with ...` as a root.

If a host module declares `uses some.api.Service` and you want the resolver to automatically add modules providing implementations from the finder, you can use:

```java
Configuration childConfig = boot.configuration()
        .resolveAndBind(finder, ModuleFinder.of(), roots);
```

`resolveAndBind` performs an additional **service binding** step, which can bring into the graph modules that provide services via `provides` without being explicitly listed as roots. This can expand the set of resolved modules, so finder sources and trust scope must be controlled. To know which provider is actually chosen at runtime, a separate service loading/selection contract is still required; `resolveAndBind` does not replace business-level provider selection policies.

## 7. When There Are Multiple Parent Layers

The most common form is a single parent: `ModuleLayer.boot()`. However, JPMS also supports a child configuration having **multiple parent configurations**:

```java
Configuration newConfig = Configuration.resolve(
        finder,
        List.of(parentA.configuration(), parentB.configuration()),
        ModuleFinder.of(),
        roots);
```

And when creating a layer with multiple parents, the corresponding static variant must be used:

```java
ModuleLayer.Controller controller =
        ModuleLayer.defineModulesWithOneLoader(
                newConfig,
                List.of(parentA, parentB),
                ClassLoader.getSystemClassLoader());
ModuleLayer newLayer = controller.layer();
```

Both snippets are **illustrative only**, inside a method where `finder`, `roots`, `parentA`, and `parentB` are already defined; `import java.util.List` and `java.lang.module.Configuration` are needed.

The `Configuration` parent list must match **the exact order and configuration objects** of the parent layers when creating the layer; otherwise, layer creation may throw `IllegalArgumentException`. Module name conflicts, target operating system, and class loader delegation must be controlled. This is why a **single boot parent** should be used unless a complex layer graph is genuinely needed.

## 8. Validating Roots, Checking the Graph, and Distinguishing Error Types

A serious plugin system should have a **preflight** phase before `resolve(...)`:

1. **Read trusted metadata:** module name, version/build identity, API requirements, list of permitted plugins.
2. **Determine roots:** which modules genuinely need to be activated; avoid taking all modules in a directory by default.
3. **Check the finder:** do the roots/modules appear at expected paths; do JAR files have valid descriptors; are artifacts protected from modification during use?
4. **Select parent:** boot layer or a layer containing the shared API needed by plugins; document why that parent is used.
5. **Resolve the graph:** use `resolve` or `resolveAndBind` depending on whether service binding is needed.
6. **Inspect results:** print/log `childConfig.modules()`; confirm the modules to be created truly belong to the new graph; evaluate duplicate packages/modules and compatibility.
7. **Define the layer:** choose an appropriate loader and distinguish errors at layer-creation time.
8. **Initialize extensions:** load classes, look up services, execute health checks, and register/rollback at clear boundaries.

### 8.1. Different Error Categories

| Stage | Common Error/Symptom | What to Check |
|---|---|---|
| `ModuleFinder` | `FindException` or module not found | Path, descriptor, JAR, module name/automatic module |
| `Configuration.resolve` | `FindException` | Unobservable root/dependency, invalid module descriptor, artifact read failure |
| `Configuration.resolve` | `ResolutionException` | Cycle in `requires`, module name conflict, or package/readability graph conflict |
| `defineModulesWithOneLoader` | `LayerInstantiationException` | Duplicate package across modules sharing a loader, split delegation, disallowed name/package |
| `defineModules...` | `IllegalArgumentException` | `Configuration` has parents not matching parent layers, or wrong API variant used for configuration |
| Class loading | `ClassNotFoundException` | Class missing from module, wrong loader, or wrong binary class name |
| Reflection/access | `IllegalAccessException` or `InaccessibleObjectException` | `exports`/`opens`, runtime access rights |
| Running plugin | Business error or other linkage error | API compatibility, version, dependencies, and lifecycle state |

`Configuration` is the result of consistency checks at the **module graph** level; it does not replace testing class loading, constructors, service providers, I/O operations, or business logic.

### 8.2. Reading What Was Actually Resolved

To inspect roots and dependencies, you can list the modules in the **child configuration**:

```java
childConfig.modules().stream()
        .map(ResolvedModule::name)
        .sorted()
        .forEach(System.out::println);
```

This is an illustrative snippet requiring `import java.lang.module.ResolvedModule;` and an existing `childConfig` variable. Sort the output so logs are easy to compare, since the iteration order of the module set is not a business contract.

If you need to see which modules the current module reads, `ResolvedModule.reads()` gives the set of `ResolvedModule` instances with readability edges. Those nodes may belong to **the current configuration or a parent configuration**. For example, a plugin with `requires java.base` will have a read edge to `java.base` even though `java.base` is not in `childConfig.modules()`.

## 9. Common Design Mistakes

1. **Using JAR filenames instead of module names as roots.** The resolver takes module names; inspect `module-info.java` or `ModuleReference.descriptor().name()`.
2. **Assuming every module in `mods` will automatically be resolved.** `ModuleFinder` only tells you what is **findable**; the root set and dependencies determine the graph.
3. **Confusing the boot layer with all modules present in the JDK.** Boot contains only modules resolved when the JVM starts.
4. **Using `Configuration.empty()` for “more freedom”.** That drops the parent graph the extension expects to use; it is not a fix for missing dependencies.
5. **Putting every dependency into roots.** `requires` already expresses dependency relationships; roots should reflect intentionally activated entry points/features.
6. **Assuming `resolve` has loaded JARs/classes.** It builds the graph; you still need to create a `ModuleLayer` and invoke classes/services afterward.
7. **Assuming `findModule` on a child configuration means the module is new.** That method can search in parents; compare against `modules()`.
8. **Misunderstanding the `before -> parents -> after` order.** A different version than expected may resolve when the finder prioritizes a module with the same name as one in the host.
9. **Defining a child layer with parent layers that do not match parent configurations.** This is an API/lifecycle error; use matching configuration–layer pairs.
10. **Believing `resolve` automatically pulls in all service providers.** Only `resolveAndBind` adds service binding per JPMS rules.
11. **Assuming adding a JAR to a directory makes the module appear immediately.** Existing finders/configurations/layers do not automatically become a file watcher and hot-swap system.
12. **Treating a module layer as a sandbox.** JPMS organizes and controls module readability/access; it does not establish a process-level security boundary for untrusted plugin code.

## 10. Practical Application Checklist

| Question | Evidence to Have |
|---|---|
| Which module is the root? | Explicit module name from descriptor, extension ID/version |
| Is the root in a permitted plugin source? | `finder.find(root)` returns a valid module reference; artifact verified |
| Which host modules need to be shared? | Present in the selected parent configuration/layer |
| How are dependency modules found? | `before` finder, parents, or `after` in the declared order |
| Which modules belong to the new configuration itself? | `childConfig.modules()` |
| Which modules are only inherited from parents? | `childConfig.findModule(name)` present, but not in `childConfig.modules()` |
| When are class loaders and runtime `Module`s created? | When calling `defineModules...` |
| One loader or many loaders? | Evaluate split packages/delegation, isolation, and lifecycle |
| Should service providers be added to the graph automatically? | Decide between `resolve` and `resolveAndBind` |
| Which errors must be reported clearly? | Missing root/dependency, resolution conflict, layer instantiation, class loading, access |
| What happens when updating a plugin? | Create new configuration/layer, switch references, manage resources/rollback |

### Java 17 API References

- [ModuleLayer — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html)
- [Configuration — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/Configuration.html)
- [ModuleFinder — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html)

**Remember:** choose **roots** using the names of modules you actually want to activate; choose **parent configuration** to inherit the host's resolved graph, typically via `ModuleLayer.boot().configuration()`; call `resolve(...)` to build the graph, and **only then** define the child layer and load classes. Distinguishing modules **new in the child** from modules **findable in the parent** keeps a Java extensibility system predictable and diagnosable.