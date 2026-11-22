# Boot Layer and the Default Module Layer in Java (JPMS)

## 1. Objectives

After this lesson, you can:
- Explain what `ModuleLayer` is and why the JVM needs a boot layer when starting an application with modules.
- Determine which modules have been resolved into the boot layer; distinguish modules that are *present on the module path* from modules that have been *brought into the runtime module graph*.
- Use `ModuleLayer.boot()`, `modules()`, `findModule()`, `configuration()`, and `Module.getLayer()` to inspect module structure.
- Distinguish the boot layer from the unnamed module on the classpath and from an additional module layer created at runtime.
- Understand the limitations of the boot layer when designing a plugin system or dynamic module loading.

**Scope:** Java 9 and later; command and source code examples are compatible with Java 21.

## 2. Three Foundational Concepts

JPMS (Java Platform Module System) groups source code into **modules** with names, dependencies, and access boundaries declared via `module-info.java`. When a program runs, the following entities are related but not synonymous:

| Concept | Role | Example |
| --- | --- | --- |
| **Module** (`java.lang.Module`) | Represents a module at runtime; holds name, packages, loaded classes, and containing layer information | `java.base`, `java.logging`, `vn.demo.boot` |
| **Configuration** (`java.lang.module.Configuration`) | The result of resolving module dependencies; a set of `ResolvedModule` objects and read relationships among them | A configuration resolving `vn.demo.boot → java.logging → java.base` |
| **Module layer** (`java.lang.ModuleLayer`) | Binds resolved modules to class loaders at runtime and links to parent layers | The boot layer or a dedicated layer for plugins |

You can visualize the relationship as:

~~~text
module-info.java + module path + root modules set
                  |
                  v
           Module resolver
                  |
                  v
            Configuration
                  |
                  v
ModuleLayer (modules + class loaders + parent layers)
                  |
                  v
      Loaded classes / access control
~~~

**Core point:** `Configuration` describes the resolved graph; `ModuleLayer` realizes that graph inside the JVM. A layer is not simply a directory containing JAR files, and a class loader is not synonymous with a layer either.

## 3. What Is the Boot Layer?

The **boot layer** is the module layer set up by the JVM at startup. It is the initial layer containing **named modules resolved during startup**, including the required foundational modules and the application modules chosen as roots along with their resolved dependencies.

Access this layer via:

~~~java
ModuleLayer boot = ModuleLayer.boot();
~~~

Properties to remember:

1. Within a JVM, `ModuleLayer.boot()` returns the boot layer established during startup. An application can *query* this layer, but cannot attach more modules to it by directly modifying the `modules()` set.
2. The boot layer has the **empty layer** as its parent. `ModuleLayer.empty()` contains no modules and has no parent.
3. `java.base` is the mandatory foundational module and is present in the boot layer. The presence of other JDK modules depends on launch configuration and the runtime environment.
4. For applications launched with `-m` / `--module`, the resolved launch module resides in the boot layer.
5. The boot layer can contain both system modules and named modules taken from the application module path, provided they are actually resolved at startup.

A simple view:

~~~text
                 ModuleLayer.empty()
                         |
                         v
                 Boot module layer
                 +------------------+
                 | java.base        |
                 | java.logging     |  (when resolved)
                 | vn.demo.boot     |  (modular application)
                 | ...              |
                 +------------------+
                         |
           A new layer can be
            defined at runtime
~~~

The diagram is an illustrative example: the actual set of modules depends on the launch configuration. **The name “default module layer” in the context of JPMS usually refers to the boot layer**; it does not mean that every JAR or every available module automatically belongs to this layer.

### When Is the Boot Layer Formed?

Before calling `main()`, the runtime determines the set of *root modules*, locates dependencies according to `requires` declarations, resolves the graph, and sets up the boot layer. The root set is influenced by how the program is launched together with module options.

For example, when running:

~~~text
java --module-path out --module vn.demo.boot/vn.demo.boot.Main
~~~

`vn.demo.boot` is the root module. If `module-info.java` has `requires java.logging;`, the `java.logging` module must be resolved along with any required dependencies. Any module that is not selected or not in the resolution graph does not automatically appear in the boot layer just because its JAR file is on the module path.

## 4. APIs for Inspecting the Boot Layer

| API | Meaning |
| --- | --- |
| `ModuleLayer.boot()` | Gets the boot layer of the current JVM |
| `boot.modules()` | Gets the set of **modules directly in this layer** (`Set<Module>`) |
| `boot.findModule("java.base")` | Looks up a module by name, returning `Optional<Module>`; lookup also checks parent layers |
| `boot.configuration()` | Gets the corresponding `Configuration` to inspect `ResolvedModule` entries |
| `boot.parents()` | Gets parent layers; for the boot layer, the parent is the empty layer |
| `SomeClass.class.getModule()` | Gets the module containing that class |
| `someModule.getLayer()` | Gets the layer containing the module, or `null` if the module is not in any layer |
| `boot.findLoader(name)` | Finds the class loader associated with the module of a given name; the bootstrap loader may be represented by `null` |

`modules()` only lists modules belonging to **that layer itself**. By contrast, `findModule()` can search in parent layers when called from a child layer. These two behaviors are especially important when an application creates additional module layers itself.

Do not call `findModule("x").get()` without verifying existence: module `x` may not have been resolved in the current launch. Prefer `isPresent()`, `ifPresent(...)`, or `orElseThrow(...)` with an appropriate message.

## 5. Example 1 — Inspecting the Boot Layer When Running on the Classpath

Create file `BootInspector.java`:

~~~java
import java.lang.Module;
import java.lang.ModuleLayer;
import java.util.Comparator;

public class BootInspector {
    public static void main(String[] args) {
        ModuleLayer boot = ModuleLayer.boot();
        Module current = BootInspector.class.getModule();

        System.out.println("java.base present: "
                + boot.findModule("java.base").isPresent());
        System.out.println("Number of boot modules: "
                + boot.modules().size());
        System.out.println("Current class in named module: "
                + current.isNamed());
        System.out.println("Current module inside boot: "
                + boot.modules().contains(current));

        System.out.println("Boot layer parents: "
                + boot.parents().size());
        System.out.println("Parent is empty: "
                + boot.parents().get(0).modules().isEmpty());

        boot.modules().stream()
                .map(Module::getName)
                .sorted(Comparator.naturalOrder())
                .limit(10)
                .forEach(name -> System.out.println("  " + name));
    }
}
~~~

Compile and run:

~~~bash
javac BootInspector.java
java BootInspector
~~~

Things you can reliably observe:

- `java.base present: true`.
- `Current class in named module: false` because `BootInspector` is run via the classpath, so it belongs to an **unnamed module**.
- `Current module inside boot: false`: the classpath's unnamed module is not placed in `boot.modules()`.
- The boot layer has one empty parent layer; the list of module names and module count depend on the JDK and launch configuration.

**Note:** Running on the classpath **does not make the boot layer disappear**. Resolved JDK modules still reside in the boot layer, while this example's application class belongs to the unnamed module.

## 6. Example 2 — An Application Module Inside the Boot Layer

Create the project structure:

~~~text
src/
└── vn.demo.boot/
    ├── module-info.java
    └── vn/
        └── demo/
            └── boot/
                └── Main.java
~~~

File `src/vn.demo.boot/module-info.java`:

~~~java
module vn.demo.boot {
    requires java.logging;
}
~~~

File `src/vn.demo.boot/vn/demo/boot/Main.java`:

~~~java
package vn.demo.boot;

import java.lang.Module;
import java.lang.ModuleLayer;

public class Main {
    public static void main(String[] args) {
        ModuleLayer boot = ModuleLayer.boot();
        Module app = Main.class.getModule();

        System.out.println("App module: " + app.getName());
        System.out.println("App is named: " + app.isNamed());
        System.out.println("App layer is boot: "
                + (app.getLayer() == boot));
        System.out.println("App found in boot: "
                + boot.findModule("vn.demo.boot").isPresent());
        System.out.println("java.logging found in boot: "
                + boot.findModule("java.logging").isPresent());
        System.out.println("java.base found in boot: "
                + boot.findModule("java.base").isPresent());

        boot.configuration()
                .findModule("vn.demo.boot")
                .ifPresent(resolved -> System.out.println(
                        "Resolved name: " + resolved.name()));
    }
}
~~~

At the project root directory, compile and run:

~~~bash
javac --module-source-path src -d out -m vn.demo.boot
java --module-path out -m vn.demo.boot/vn.demo.boot.Main
~~~

Expected output lines:

~~~text
App module: vn.demo.boot
App is named: true
App layer is boot: true
App found in boot: true
java.logging found in boot: true
java.base found in boot: true
Resolved name: vn.demo.boot
~~~

Because the program is launched as a **named module**, `vn.demo.boot` belongs to the boot layer. Declaring `requires java.logging;` makes `java.logging` part of the graph to be resolved. `java.base` is the foundational dependency used by every module, even when `requires java.base;` is not declared explicitly.

You can add the option:

~~~bash
java --show-module-resolution --module-path out -m vn.demo.boot/vn.demo.boot.Main
~~~

This option displays information about which modules and dependency relationships the JVM resolves during startup. Exact contents and ordering may vary across JDK versions.

## 7. What Determines the Contents of the Boot Layer?

The **module path** is where the runtime finds module candidates; **module resolution** is what decides which modules enter the initial graph. A module present on the module path is not necessarily in the boot layer.

| Launch style / option | Main effect |
| --- | --- |
| `java -cp ... Main` | Application classes on the classpath belong to the unnamed module; the boot layer still contains resolved named modules |
| `java --module-path mods -m app.mod/pkg.Main` | `app.mod` is the root module resolved into the boot layer along with required dependencies |
| `--add-modules m1,m2` | Adds root modules to startup resolution |
| `--limit-modules m1,m2` | Limits the set of observable modules during resolution; may affect the resulting graph |
| `--show-module-resolution` | Prints module resolution info to observe the startup process |

Commonly confused points:

- `java --list-modules` primarily lists system modules present in the runtime image, **not a direct measurement of the entire `ModuleLayer.boot().modules()` of an application**.
- A JDK module such as `java.sql` may exist in the runtime image without being resolved into the boot layer for a specific launch configuration.
- If using a slimmed-down runtime image created with `jlink`, the number of available modules also depends on what that image contains.
- The same boot-layer inspection code can yield different lists across runs with different module options; do not hard-code module counts.

## 8. How Does the Boot Layer Differ from a Dynamically Created Layer?

The boot layer is established at startup. An application that needs to load a new set of modules after already running can **create a child layer** from a resolved `Configuration`, instead of trying to modify the boot layer.

As an illustration, suppose the `plugins/` directory already contains valid modules and has a module named `vn.demo.plugin`:

~~~java
import java.lang.ModuleLayer;
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

ModuleLayer boot = ModuleLayer.boot();
ModuleFinder plugins = ModuleFinder.of(Path.of("plugins"));

Configuration pluginConfig = boot.configuration().resolve(
        plugins,
        ModuleFinder.of(),
        Set.of("vn.demo.plugin"));

ModuleLayer pluginLayer = boot.defineModulesWithOneLoader(
        pluginConfig,
        ClassLoader.getSystemClassLoader());

System.out.println(
        pluginLayer.modules().stream()
                .anyMatch(m -> "vn.demo.plugin".equals(m.getName())));
System.out.println(
        boot.findModule("vn.demo.plugin").isPresent());
~~~

This snippet illustrates the layer setup inside a method; to run it, you need to prepare the plugin module and a valid dependency graph. `pluginLayer` is defined with `boot` as its parent layer. The module `vn.demo.plugin` resides in the child layer; creating a child layer **does not add this module to the boot layer**.

Comparing the two kinds of layers:

| Criterion | Boot layer | Application-created layer |
| --- | --- | --- |
| Creation time | At JVM startup | While the program is running |
| How to access | `ModuleLayer.boot()` | Return value from `defineModulesWithOneLoader`, `defineModulesWithManyLoaders`, or related APIs |
| Configuration | Based on the graph resolved at startup | Based on a `Configuration` resolved by the application |
| Parent relationship | Empty layer | One or more specified parent layers |
| Typical purpose | Running foundational modules and initial application | Plugins, extensions, separating how modules are loaded |

When calling `pluginLayer.findModule("java.base")`, the API can find `java.base` from the parent layer. However, `pluginLayer.modules()` contains only the modules **directly defined** in `pluginLayer`.

**Important about class loaders:** layers and class loaders are two related axes. A layer can map multiple modules to the same loader or to different loaders; classes in the boot layer can also be loaded by the bootstrap, platform, or application class loader. Therefore, “same layer” does not mean “same class loader”.

## 9. Common Misunderstandings

**“I put a JAR on the module path, why does `findModule()` return empty?”**  
Because the module path only provides candidates. A module must be resolved by a root module, dependency relationships, or appropriate launch options. First check how the app is launched and `module-info.java`.

**“If I run an app with `-cp`, is there no boot layer?”**  
Incorrect. The JVM still creates a boot layer; only the application code on the classpath belongs to an unnamed module rather than a named module in the boot layer.

**“Is the boot layer where all modules are stored?”**  
No. Modules loaded into a new layer can reside in a child layer. Modules that have not been resolved are not in the boot layer's graph.

**“Is one layer one class loader?”**  
No. `ModuleLayer` organizes modules and parent relationships; each module is mapped to an appropriate class loader. Multiple modules can share a single class loader.

**“Can I add a module directly to the set returned by `boot.modules()`?”**  
No. The returned set is not a structure that allows mutating the boot layer's graph. To use new modules after startup, you must build a new configuration and layer using JPMS mechanisms.

**“Does `Module.getLayer()` always return the boot layer?”**  
No. For a module in a child layer, it returns the layer containing that module; for an unnamed module, it may return `null` because it does not belong to any layer.

## 10. Practice Exercises

1. Run `BootInspector` with the classpath, record the number of modules listed and the result of checking `current.isNamed()`. Explain why the application class does not belong to the boot layer.
2. Run the `vn.demo.boot` module in Example 2, then remove `requires java.logging;` while keeping the statements that check `java.logging`. Observe the result in your environment and explain why you cannot draw a fixed conclusion about the presence of every JDK module from a single run.
3. Add the `--show-module-resolution` option and compare the list of resolved modules against the result of `boot.modules()`. Point out the roles of root modules and dependencies.
4. Write a method `boolean isInBootLayer(Class<?> type)` based on `type.getModule()` and `ModuleLayer.boot().modules()`, then test it with an application class and `String.class`.
5. Explain why a plugin application might need a separate module layer when plugins are only discovered after the program has already started.

Hint for Exercise 4:

~~~java
static boolean isInBootLayer(Class<?> type) {
    return ModuleLayer.boot().modules().contains(type.getModule());
}
~~~

With `String.class`, the result is `true` because this class belongs to `java.base`. With `BootInspector.class` run on the classpath, the result is `false`.

## 11. Takeaways

- **Boot layer** is the initial module layer created by the JVM at startup, accessed via `ModuleLayer.boot()`.
- The boot layer contains **resolved named modules**, not automatically every module found on the module path.
- Applications launched with `-m` have their main named module in the boot layer; applications run on the classpath use an unnamed module.
- `modules()` lists modules belonging to the layer itself; `findModule()` searches by name, including through parent layers.
- The boot layer is not “expanded in place” when defining a child layer. A child layer is a distinct `ModuleLayer` object with its own configuration and class loader mapping.
- When troubleshooting, combine `--show-module-resolution`, `ModuleLayer.boot()`, `Class.getModule()`, and `Module.getLayer()` to see where a module actually resides.

## References

- [Java SE 21 — ModuleLayer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html)
- [Java SE 21 — Module](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html)
- [Java SE 21 — Configuration](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/Configuration.html)
- [JEP 261 — Module System](https://openjdk.org/jeps/261)
