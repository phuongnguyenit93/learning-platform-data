# ModuleLayer.boot and Dynamically Created Layers

Since **Java 9**, the Java Platform Module System (JPMS) organizes **named modules** along with their dependency relationships and access rules through one or more **module layers**. `ModuleLayer.boot()` returns the **boot layer** created when the JVM starts up to hold the named modules resolved for the current run. When a program needs to discover and load modules **after the JVM is already running** — such as a plugin system or an extensible tool — we can create a **dynamic module layer** based on the boot layer or other layers.

These two are related, yet **not equivalent**:

- **Boot layer** reflects the set of modules *resolved into the boot layer at startup*. It is not every module that may exist in the JDK or on disk.
- **Dynamic layer** creates an additional module space with a `Configuration` and assigned class loader. Creating a new layer **does not directly modify the boot layer**, does not automatically turn the new module into a global classpath, and does not automatically grant all existing modules permission to read the new module.
- **Module, configuration, layer, class loader** are distinct objects. The module graph determines readability/exports/opens; the defining class loader still participates in the **type identity** of a class/interface.

This lesson builds a **fully runnable Java 17** project, compiles a named module into the `mods` directory, creates **two dynamic layers** from the same module, and then observes classes that have the same name but different identities.

## 1. Understanding the Four Concepts: Module, Configuration, Layer, and Loader

| Concept | Meaning | Key API |
| --- | --- | --- |
| **Module descriptor** | Metadata of a named module: name, `requires`, `exports`, `opens`, `uses`, `provides`, and related information. | `module-info.java` / `module-info.class`, `ModuleDescriptor` |
| **Resolved module configuration** | Result of resolving the set of root modules and dependencies from one or more `ModuleFinder` instances, on the basis of parent configurations. | `Configuration`, `resolve(...)`, `ResolvedModule` |
| **Module layer** | Set of named modules defined for a configuration, associated with loaders and parent layers. | `ModuleLayer`, `ModuleLayer.boot()`, `defineModules...` |
| **Class loader** | Defines classes/interfaces and helps the JVM load them by name. A layer can use one or more loaders. | `ClassLoader`, `ModuleLayer.findLoader(...)` |

Conceptual diagram:

~~~text
               module-info.class + module artifacts
                          |
                          v
          ModuleFinder / Configuration.resolve(...)
                          |
                          v
          Resolved Configuration (module graph)
                          |
                          v
             ModuleLayer.defineModules...
                          |
                    ModuleLayer
                          |
                named Module objects
                          |
            loader(s) assigned to modules
                          |
               Class<?> of each type
~~~

**Resolution** is not yet **definition**: `Configuration.resolve` establishes modules and dependency relationships at the configuration level, but does not yet turn the classes inside a module into Class objects of a dynamic layer. Only after the layer definition step can the program use the corresponding loader to load each class on demand.

A **layer** is also not a class loader. A layer can contain multiple named modules, and different layer creation methods determine how loaders are assigned:

- `defineModulesWithOneLoader(...)`: modules of the new layer use **a single loader created for the layer**.
- `defineModulesWithManyLoaders(...)`: each module in the new layer is assigned **its own created loader**.
- `defineModules(...)`: the caller supplies a function mapping module names to loaders; it must satisfy the conditions and constraints specified by the API.

Depending on the configuration, classes of a module in a parent layer remain defined by the previously established loader; creating a child layer does not automatically “reload” all parent modules.

## 2. Boot Layer: What Does ModuleLayer.boot() Contain?

In a typical Java program:

~~~java
ModuleLayer boot = ModuleLayer.boot();
System.out.println(boot.findModule("java.base").isPresent());
~~~

This is a **valid fragment when placed inside a method**. `java.base` is the foundational module of all modules and is present in the boot layer of standard Java 17, so the second line prints `true`.

To understand the output, distinguish the following three sets:

1. **Observable modules**: modules that the resolver can find from system modules, the module path, and the corresponding module sources.
2. **Modules resolved for the boot layer**: modules that the JVM places into the boot layer's configuration at startup, depending on the entry point, root modules, `--add-modules`, and resolution rules.
3. **Modules in dynamic layers**: named modules resolved and defined **afterward** by the program via the `ModuleLayer` API.

`java --list-modules` reports modules that are **observable** to the Java launcher in the corresponding environment; it should not be treated as a command that accurately lists every module currently resolved in `ModuleLayer.boot()`. To inspect the actual contents of the boot layer at runtime, use `ModuleLayer.boot().modules()` or `findModule(...)`.

### Listing Boot Modules

The following Java 17 fragment (placed inside a method):

~~~java
ModuleLayer boot = ModuleLayer.boot();

boot.modules().stream()
        .map(Module::getName)
        .sorted()
        .forEach(System.out::println);
~~~

The result depends on how the program is run and the runtime image, so no fixed stdout is listed for the entire list. `boot.modules()` returns only modules defined **directly in the boot layer**. If `boot.findModule(name)` is used, the API searches the target layer and **its parent layers** according to its contract; the boot layer is typically the root, so it has no parent.

### Important Properties

- `ModuleLayer.boot()` returns **the same existing boot layer** in the runtime; it does not create a new layer on each call.
- The boot layer is an object managing modules that have already been defined, not a copy of all contents of `$JAVA_HOME/jmods` or any arbitrary directory.
- Application classes on the regular classpath belong to the **unnamed module** of their defining loader; they do not become named modules in `boot.modules()` merely by running on JDK 17.
- When starting with `java --module-path ... -m my.module/...`, application modules resolved for startup may reside in the **boot layer**. Do not claim that the boot layer only contains `java.*` modules.
- `ModuleLayer.boot()` is not passively altered when the program later creates child layers.

## 3. Dynamic Layer: Creating New Modules While the JVM Is Running

Suppose initially the program only needs the host and foundational modules, and then discovers a plugin module named `dev.demo.greeter`. Instead of requiring a JVM restart and resolving the module from startup, we can:

~~~text
JVM startup
    |
    v
ModuleLayer.boot()
    |
    | Application finds the plugin module in the mods/ directory
    v
ModuleFinder.of(Path.of("mods"))
    |
    v
boot.configuration().resolve(...)
    |
    v
Resolved Configuration for the plugin
    |
    v
boot.defineModulesWithOneLoader(...)
    |
    v
Dynamic layer: dev.demo.greeter
    |
    v
layer.findLoader("dev.demo.greeter")
    |
    v
loadClass("dev.demo.greeter.Greeter")
~~~

Core steps:

**Step 1 — find modules:** `ModuleFinder` can observe modular JARs or exploded module directories in the passed-in path, depending on the contents and module path rules. `ModuleFinder.of(Path.of("mods"))` asks to search from a specific location rather than automatically scanning everywhere on the system.

**Step 2 — resolve configuration:** `boot.configuration().resolve(before, after, roots)` resolves the set of root modules and dependencies; modules already present in the parent configuration are typically referenced in the parent instead of being redefined in the child. The result is a new `Configuration`, not yet a layer.

**Step 3 — define layer:** use a `defineModules...` method to turn the configuration into named modules known to the JVM and assign the corresponding class loaders.

**Step 4 — use module:** `layer.findModule(name)` finds the `Module`, `layer.findLoader(name)` returns the loader of the module defined in that layer, and then `loadClass` or a framework mechanism is used to work with the type.

**Step 5 — protect boundaries:** even though the new module has been loaded, checks for **readability, exports, opens, service binding, and type identity** still exist; do not assume that having a `Class<?>` means every method can legally be invoked via reflection.

## 4. Standalone Java 17 Project: Boot and Two Dynamic Layers

To produce output that does not depend on external modules, create **exactly three files** with the following structure:

~~~text
layer-demo/
├── LayerDemo.java
├── src/
│   └── dev.demo.greeter/
│       ├── module-info.java
│       └── dev/
│           └── demo/
│               └── greeter/
│                   └── Greeter.java
└── mods/                      (created automatically by javac after the compilation step)
~~~

### File 1: src/dev.demo.greeter/module-info.java

~~~java
module dev.demo.greeter {
    exports dev.demo.greeter;
}
~~~

This module **exports package** `dev.demo.greeter` so that code outside the module can access its public API according to JPMS rules. `requires java.base;` is not needed because every named module implicitly reads `java.base`.

### File 2: src/dev.demo.greeter/dev/demo/greeter/Greeter.java

~~~java
package dev.demo.greeter;

public final class Greeter {
    public static String message() {
        return "hello from plugin module";
    }
}
~~~

A public class, public method, and exported package allow the host part on the classpath to invoke the method via reflection after obtaining the Class using the layer's loader.

### File 3: LayerDemo.java

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public class LayerDemo {
    public static void main(String[] args) throws Exception {
        ModuleLayer boot = ModuleLayer.boot();
        System.out.println("Boot contains java.base: "
                + boot.findModule("java.base").isPresent());
        System.out.println("Boot contains plugin: "
                + boot.findModule("dev.demo.greeter").isPresent());

        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));
        Configuration configuration = boot.configuration().resolve(
                finder, ModuleFinder.of(), Set.of("dev.demo.greeter"));

        ModuleLayer layer1 = boot.defineModulesWithOneLoader(
                configuration, ClassLoader.getSystemClassLoader());
        ModuleLayer layer2 = boot.defineModulesWithOneLoader(
                configuration, ClassLoader.getSystemClassLoader());

        Class<?> first = layer1.findLoader("dev.demo.greeter")
                .loadClass("dev.demo.greeter.Greeter");
        Class<?> second = layer2.findLoader("dev.demo.greeter")
                .loadClass("dev.demo.greeter.Greeter");

        System.out.println("Layer1 has plugin: "
                + layer1.findModule("dev.demo.greeter").isPresent());
        System.out.println("Layer1 parent is boot: "
                + (layer1.parents().get(0) == boot));
        System.out.println("Defined in layer1: "
                + (first.getModule().getLayer() == layer1));
        System.out.println("Same binary name: "
                + first.getName().equals(second.getName()));
        System.out.println("Same Class identity: "
                + (first == second));
        System.out.println("Greeting: "
                + first.getMethod("message").invoke(null));
    }
}
~~~

**Compile with JDK 17 or later**, standing inside the `layer-demo` directory:

~~~bash
javac --release 17 -d mods --module-source-path src -m dev.demo.greeter
javac --release 17 LayerDemo.java
java LayerDemo
~~~

Do not pass `--module-path mods` to the `java LayerDemo` step: we intentionally keep `dev.demo.greeter` **not yet a startup root module**, and then the application's resolver finds it using `ModuleFinder.of(...)`. The first compilation command creates the `mods/dev.demo.greeter/...` structure containing `module-info.class` and `Greeter.class`; `LayerDemo` is compiled as an ordinary class on the classpath.

**Exact stdout** for the project created as instructed on standard JDK 17:

~~~text
Boot contains java.base: true
Boot contains plugin: false
Layer1 has plugin: true
Layer1 parent is boot: true
Defined in layer1: true
Same binary name: true
Same Class identity: false
Greeting: hello from plugin module
~~~

### Explaining the Output and Execution

1. `ModuleLayer.boot()` already exists when `LayerDemo.main` begins and contains `java.base`, so the first line is `true`.
2. `dev.demo.greeter` is not yet in the boot layer because the application is run as a class on the classpath without adding the plugin as a root on the command line, so the second line is `false`.
3. `ModuleFinder.of(Path.of("mods"))` discovers the compiled exploded named module. `Configuration.resolve` finds the root `dev.demo.greeter`; the dependency on `java.base` is resolved through the boot layer's parent configuration.
4. Two calls to `boot.defineModulesWithOneLoader(configuration, systemLoader)` create **two corresponding new layers**; each layer has the `dev.demo.greeter` module defined by that layer.
5. `layer1.findModule(...)` has the plugin module, while `layer1.parents().get(0) == boot` indicates that layer 1 uses boot as its parent.
6. `layer1.findLoader(...)` returns **the class loader assigned to layer 1's plugin module**. `first.getModule().getLayer() == layer1` is true because this Class belongs to the module defined in layer 1.
7. `first` and `second` both have the binary name `dev.demo.greeter.Greeter`, but because they are defined in **two different loaders** (each defineModulesWithOneLoader call creates a loader for the layer), `first == second` is `false`.
8. `Greeter.message` is public inside an exported package, so the reflection call from the host correctly prints `hello from plugin module`.

**Important:** This example intentionally created **two identities of the same module/class** to learn about isolation. In a real application, do not create duplicate layers if you want to directly exchange implementation objects between plugins or between the host and a plugin. Two modules with the same name in two layers **do not turn two Classes into one**.

### If You Want to Know the Actual Loader

In the `main` method, you can add this fragment:

~~~java
System.out.println(first.getClassLoader()
        == layer1.findLoader("dev.demo.greeter"));

System.out.println(first.getModule().getName());
System.out.println(first.getModule().isNamed());
~~~

If the program is kept unchanged, these three lines print `true`, `dev.demo.greeter`, and `true` respectively. This is an **additional fragment**, not included in the stdout published above.

## 5. The Boot Layer Does Not Receive New Modules When Creating Child Layers

The following architecture diagram matches the program:

~~~text
                              ModuleLayer.boot()
                              ├── java.base
                              ├── ... named modules
                              └── parent configuration
                                  /           \
                                 /             \
                                v               v
                      dynamic layer 1     dynamic layer 2
                       dev.demo.greeter    dev.demo.greeter
                            |                   |
                         loader 1            loader 2
                            |                   |
                       Greeter #1           Greeter #2
                              \                 /
                               same name, distinct identity
~~~

After creating layers 1 and 2, querying `boot.findModule("dev.demo.greeter")` still returns `Optional.empty()` in the context of this example, because no module is attached to the boot layer. To obtain the new module, you must keep references to `layer1`/`layer2` and look it up from the corresponding layer.

### How Does findModule Differ from findLoader?

- `layer.findModule(name)` searches for a `Module` in the specified layer and across its parent layers. Returns `Optional<Module>`.
- `layer.findLoader(name)` requires the name of a module **defined in the layer on which the method is called**, returning the assigned defining class loader; if no module with that name exists in that layer, it may throw `IllegalArgumentException`. If you need the loader of a module in a parent, query the **parent layer** containing that module; do not assume child.findLoader can be used the same way as child.findModule.
- `module.getLayer()` indicates the layer containing that named module (for module layers defined via the API). This is very useful when debugging lookup or reflection issues.
- `type.getModule()` returns the `Module` that actually defines the type; `type.getClassLoader()` returns the defining loader. The two APIs answer **two different questions**.

A common issue is finding a module via `child.findModule("java.base")` and assuming `child.findLoader("java.base")` works similarly: `java.base` is in the boot layer and is not redefined by the child. Therefore, `child.findLoader("java.base")` is not the way to look up the loader of a parent module.

## 6. Resolution and Module Dependencies: Not Just a Name in a Directory

The example has only one new module. In complex applications, a plugin might have a descriptor:

~~~java
module acme.plugin {
    requires acme.contract;
    requires java.logging;
    exports acme.plugin.api;
}
~~~

This is a **`module-info.java` fragment**, not a standalone module with complete source/build scripts in this lesson. It states that `acme.plugin` needs to read `acme.contract` and `java.logging`. Before creating a layer, the resolver must find those modules in the finders or parent configurations. If `acme.contract` belongs to the boot/parent layer, the dynamic layer can use the module already resolved in the parent without redefining it.

Resolving a module **does not mean all classes are loaded immediately**. The JVM can load each Class when needed; `Configuration` describes the resolved graph, while the class loader determines the actual definition when a class is used.

### ModuleFinder Is a Module Finder, Not a ClassLoader

`ModuleFinder.of(Path.of("mods"))` supplies `ModuleReference`/descriptors to serve resolution. It does not have a `loadClass` method like ClassLoader and does not define JVM types on its own. You must proceed through the **define layer** step and then obtain the loader of the named module.

### before and after Finders in resolve

The `Configuration.resolve(before, after, roots)` API prioritizes module lookup order and references parent configurations according to its contract. From an application standpoint, what matters is that root modules and all dependencies must be resolved **from trustworthy, consistent sources**. It should not be described simplistically as “before/after will load ClassFiles in turn”: they participate in **module resolution**, not executing `ClassLoader.loadClass`.

If a module is missing, descriptors conflict, the graph is invalid, or a root name is wrong, resolution may fail before defining the layer. If resolution succeeds but constraints on loader assignment or package conflicts are not satisfied, the layer definition step can still fail separately.

## 7. One Loader or Many Loaders for a Layer?

Two common `ModuleLayer` APIs determine how named modules are bound to defining class loaders.

| API | Loader policy | When to consider |
| --- | --- | --- |
| `defineModulesWithOneLoader(configuration, parentLoader)` | Every module in the new layer uses **a single new class loader** created by the API. | A plugin consisting of multiple modules that need to share the same loader space, packaged uniformly. |
| `defineModulesWithManyLoaders(configuration, parentLoader)` | Each module in the new layer has **its own separate new loader** created by the API. | When loader spaces need to be separated per module. |
| `defineModules(configuration, parents, mapper)` | The caller provides a **module-name-to-class-loader function**, using the static API to create a layer/controller. | Need for custom loader integration or complex module mapping. |

Do not interpret the name `WithOneLoader` as “using the existing system loader directly to define all modules”. `parentLoader` is the **parent loader of the new loader**, not an instruction to define the new modules directly into `ClassLoader.getSystemClassLoader()`.

Therefore, even though the program in section 4 passes the same `ClassLoader.getSystemClassLoader()` to two calls of `defineModulesWithOneLoader`, it still creates **two different defining loaders**, resulting in two distinct Greeter identities.

### Multiple Loaders Do Not Mean Dependencies Cannot Be Read

Module readability and class loader mapping must be compatible. With the methods provided by the JDK, the JVM creates the loader and sets up the corresponding class lookup mechanism. With a custom mapper, the author must ensure that the loaders support loading the module's classes, package restrictions, and JVM/API conditions. A valid `requires` graph should not be treated as permission to define duplicate copies of an API class across multiple loaders.

## 8. Class Identity, Shared APIs, and Two Independent Layers

A class `dev.demo.greeter.Greeter` in layer 1 and the same binary name in layer 2 can be **different `Class<?>` objects**. The JVM uses the pair:

~~~text
type identity = (binary name, defining class loader)
~~~

Scenarios to consider:

- **Independently loaded plugins:** multiple dynamic layers for the same module allow isolating two versions/module deployments, but do not automatically allow casting an implementation object from layer A to the implementation Class of layer B.
- **Host–plugin communication:** requires an interface/DTO contract with an appropriate shared defining loader/layer; typically, a stable API module is placed in a **shared parent layer/loader** for plugins to reference.
- **ServiceLoader:** can discover providers from named modules via `ServiceLoader.load(layer, Service.class)` when the service configuration is appropriate. In this case, the service API type must still be compatibly defined across both host and provider.
- **Hot redeploy:** creating a new layer does not automatically make objects from the old layer disappear. If caches, threads, service registries, or the TCCL hold the old object/class/loader, class unloading may not occur yet.

If an API module `com.acme.contract` is defined separately twice in sibling layers, the host may encounter an error like “class A cannot be cast to class A”. A generally better design is to place the contract in a shared parent/loader for both children to reference, while the implementations reside in each child.

### No Direct API to Unload a ModuleLayer

`ModuleLayer` has no `close()` method to detach a layer from the JVM directly. For the JVM to reclaim classes/class loaders, the corresponding reachability and garbage collection conditions must be met, so lifecycle management is required: stop plugin tasks, release `ServiceLoader`/providers, listeners, caches, TCCL, method handles, and references to the layer/loader. Do not treat setting `layer = null` as an immediate unload command.

## 9. Readability, exports, and opens Still Apply

Successfully creating a layer does not mean code in any module can access every package of the new module.

**Concepts to distinguish:**

- `requires`: the module depends on and typically establishes a **readability** relationship with the required module.
- `exports`: allows external access to **public types/members** in the exported package, according to module system rules.
- `opens`: allows access via **deep reflection** where appropriate (for example using `setAccessible(true)`), which is not synonymous with a public compile-time API.
- `uses` / `provides ... with ...`: declares consumers/providers for service binding and discovery.

In the example, `exports dev.demo.greeter;` allows the host to invoke the public method `Greeter.message()` via reflection. If exports is omitted, you can still locate the Class through the layer loader in permitted situations, but a reflective call from a module lacking access permission may encounter `IllegalAccessException` or the corresponding access error.

### What If the Host Wants to Directly Import a Class in a Dynamic Module?

`LayerDemo.java` is code on the classpath and uses `Class<?>`/reflection, **without** an `import dev.demo.greeter.Greeter;` statement. This is intentional: the module is only defined **after the program has started**, so the host's compiler/loader does not automatically recognize it as a static dependency.

If the host wants direct compile-time access, you must design an appropriate module graph/runtime from the start; a common choice for plugins is a **shared API module** known to both the host and plugins at startup, and then pass implementations via that API or `ServiceLoader`. A dynamic layer does not automatically add a `requires` edge to the host's `module-info` or turn plugin packages into an unrestricted classpath.

## 10. Controller and Runtime Adjustments

In addition to the instance method `boot.defineModulesWithOneLoader(...)` that directly returns a `ModuleLayer`, static APIs like `ModuleLayer.defineModulesWithOneLoader(configuration, List.of(boot), parentLoader)` or other variants can return a `ModuleLayer.Controller`. The controller lets you retrieve `layer()` and perform scoped adjustments:

~~~java
// Fragment: placed inside a method where variables cf, boot, and parentLoader already exist.
ModuleLayer.Controller controller =
        ModuleLayer.defineModulesWithOneLoader(
                cf, java.util.List.of(boot), parentLoader);

ModuleLayer layer = controller.layer();
~~~

This is a **fragment that depends on the variables** `cf`, `boot`, and `parentLoader`; it is not a standalone compilable program. The controller has methods such as `addReads`, `addExports`, and `addOpens` subject to conditions regarding the modules in the layer managed by the controller.

These methods alter **runtime access relationships** via the API; they do not modify `module-info.java` source code, do not rewrite `module-info.class`, and do not enable loading modules that have not been resolved/defined.

Avoid reflexively using the controller to “open all packages to everywhere”. For plugins, keep the minimal necessary boundaries and only open packages that genuinely serve the API/reflection.

## 11. Common Errors When Working with Dynamic Layers

| Symptom | Common cause | How to check |
| --- | --- | --- |
| `boot.findModule("my.plugin")` is empty after creating a child layer | The boot layer does not have new modules added to it. | Use `child.findModule("my.plugin")`; keep a reference to the child layer. |
| `LayerInstantiationException` | Configuration/loader mapping or layer rules cannot be satisfied. | Read the message and check package/module/loader constraints. |
| `FindException` or `ResolutionException` | The resolver cannot find a module or the dependency graph is invalid. | Check `ModuleFinder`, roots, dependency descriptors, and parent configs. |
| `ClassNotFoundException` even though `findModule` returns the module | Wrong loader used, wrong class name, or the class does not exist in the module. | Obtain the loader via `layer.findLoader(moduleName)` and check the binary name/JAR contents. |
| `IllegalArgumentException` on `findLoader` | Querying a module name not defined in the layer being called. | Determine which layer defines the module and use that layer. |
| `IllegalAccessException` or `InaccessibleObjectException` | Package is not properly exported/opened for the caller/reflection. | Check `module-info.java`, `isExported`, `isOpen`, and access permissions. |
| `ServiceConfigurationError` | Provider not found/invalid or interface identity mismatch. | Check `uses`/`provides`, the service layer, and the shared API type. |
| `ClassCastException` between two classes with the same name | Two layers/loaders define two independent types. | Compare `Class<?> ==`, `getClassLoader()`, `getModule()`, and `getLayer()`. |
| Old plugin is not reclaimed | References still hold onto the layer/loader/instances or threads are still alive. | Clean up the plugin lifecycle and monitor references. |

**Note:** Not every error in the table is caused directly by module layers. `ClassNotFoundException` may simply be a wrong binary name; `IllegalAccessException` can also result from other Java reflection access checks; `ServiceConfigurationError` has multiple causes. Read the message, cause, and actual configuration.

### The Trap: “Same Module Name” Does Not Mean Same Module Object

Example:

~~~java
Module m1 = layer1.findModule("dev.demo.greeter").orElseThrow();
Module m2 = layer2.findModule("dev.demo.greeter").orElseThrow();

System.out.println(m1 == m2);
~~~

This is a **fragment depending on layer1/layer2 from the program in section 4**. It prints `false` because those are two named Module objects belonging to two different layers. Similarly, the `Greeter` classes of the two layers have different defining loaders. **Do not rely solely on the `module.getName()` string to assert the same runtime module instance.**

## 12. Checklist When Designing Plugins with ModuleLayer

1. **Identify which modules belong to the boot/parent layer** and which modules need to be loaded dynamically.
2. **Separate the shared API contract from the implementation:** shared APIs/modules should live in a stable parent layer/loader if the host and plugins need to communicate directly.
3. **Prepare module artifacts** with valid `module-info.class`; distinguish between modular JARs, exploded modules, and regular classpath JARs.
4. **Use an appropriate ModuleFinder** and specify the exact root module names; do not turn a file path into a module name.
5. **Resolve the configuration** with all required dependencies, checking for conflicts and exception messages.
6. **Choose a loader strategy** (one loader, many loaders, custom mapping) according to isolation/type identity requirements.
7. **Define the layer with the right parent layer**, and then keep a reference for module/loader lookup.
8. **Check module readability/exports/opens**, not merely whether the Class has been loaded.
9. **Test two layers containing the same module** to properly identify split-identity scenarios if the design requires coexistence.
10. **Service providers and resources:** verify that the loader/TCCL/ServiceLoader in use actually sees the providers and shared API classes.
11. **Manage lifecycle:** stop threads, cancel callbacks, and clear caches and references if a plugin is disabled/redeployed.
12. **Do not modify the boot layer** under the assumption that creating a dynamic layer will make every class loader in the JVM see the new module.

## 13. Knowledge Self-Check

**Question 1.** Does `ModuleLayer.boot()` contain every module present in `$JAVA_HOME`?

**Answer:** No. The boot layer contains the **named modules that have been resolved and defined for the boot layer** at startup; other observable modules may not have been resolved into it.

**Question 2.** Does `ModuleFinder.of(Path.of("mods"))` load plugin classes on its own yet?

**Answer:** Not yet. It finds **module references/descriptors** for resolution; you must resolve, define the layer, and use the new loader when you want to load classes.

**Question 3.** Does creating `layer1` from `boot.defineModulesWithOneLoader` cause `boot.findModule("plugin")` to automatically return a value?

**Answer:** No. The child layer is a new object and does not automatically add modules to the boot layer.

**Question 4.** Two layers both resolve a module named `dev.demo.greeter` and use `defineModulesWithOneLoader` separately. Do their `Greeter.class` objects necessarily have the same identity?

**Answer:** No. In the example, each layer creates its own loader, so the `Class<?>` objects differ even though the binary name is identical.

**Question 5.** `layer.findModule("java.base")` finds the module in the parent; should you immediately call `layer.findLoader("java.base")` to get the corresponding loader?

**Answer:** Do not infer that. `findModule` can search parent layers; `findLoader` requires the name of a module defined directly in the layer on which it is called. For `java.base`, use the layer that actually defines it (typically the boot layer).

**Question 6.** Once a dynamic layer has loaded a plugin, is the host allowed to invoke every private member via reflection?

**Answer:** No. It is still subject to `exports`/`opens` rules and reflection conditions; finding a module does not mean unrestricted deep reflection is permitted.

**Question 7.** Does `defineModulesWithOneLoader(cf, parentLoader)` mean using parentLoader directly to define all new modules?

**Answer:** No. This API **creates a new loader for the layer's modules** with parentLoader passed as the parent; this explains why two separate definitions have different class identities.

## Key Takeaways

`ModuleLayer.boot()` represents the **boot module graph** at JVM startup. When plugin modules are needed at runtime, we **find modules → resolve `Configuration` → define a dynamic `ModuleLayer` → obtain the module loader → load/discover classes**. A dynamic layer does not modify the boot layer and does not automatically grant global access rights. Class identity still depends on the defining loader; for safe host–plugin interaction, place the **shared API contract** in a parent layer/loader, configure module access properly, and manage the lifecycle of dynamic layers/loaders.

**Official documentation:**

- Java SE 17 API, `ModuleLayer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- Java SE 17 API, `Configuration`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/Configuration.html
- Java SE 17 API, `ModuleFinder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html
- Java SE 17 API, `Module`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- Java SE 17 API, `ServiceLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Java Virtual Machine Specification, Java SE 17 `5.3 (*Creation of Classes and Interfaces*): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
