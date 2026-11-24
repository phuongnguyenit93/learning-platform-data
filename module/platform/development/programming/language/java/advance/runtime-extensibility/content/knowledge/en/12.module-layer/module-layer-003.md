# Creating a ModuleLayer with defineModulesWithManyLoaders or Custom ClassLoader Mapping

When a Java application needs to load additional **named modules** after the JVM has started, the Java Platform Module System (JPMS) allows the application to create a new **ModuleLayer** from a resolved module configuration. A key decision is **which ClassLoader will define each module**. Java provides the convenient `defineModulesWithManyLoaders` to create a separate loader for each module, while also allowing custom module-name-to-loader mapping via `defineModules`.

This article explains the APIs on Java 17+, the `ModuleFinder` → `Configuration` → `ModuleLayer` sequence, the difference between automatic and custom mapping, a runnable lab with two modular JARs, limitations regarding readability, exports, resources, and class identity, and how to handle plugin lifecycles.

## 1. What Is a Layer, and What Is It Not?

A **ModuleLayer** is a set of `Module` objects defined by the JVM from a graph of resolved modules in a `Configuration`, along with relationships to one or more parent layers. A layer can be created at runtime so the host can see new plugins without placing all plugins on the process's startup module path.

Distinguish the participating objects:

| Object | Function | What It Does Not Do Automatically |
| --- | --- | --- |
| ModuleFinder | Discovers module descriptors in JAR/JMOD/module directories | Does not load or initialize classes |
| Configuration | Resolves the `requires` graph, determines the set of resolved modules | Does not yet create runtime `Module` objects or loaders |
| ModuleLayer | Defines runtime `Module` instances and binds modules to loaders | Does not automatically invoke `main`, constructors, or service providers |
| ClassLoader | Defines/looks up classes; participates in delegation | Does not automatically create `requires`/`exports`/`opens` edges |
| ModuleLayer.Controller | Provides authority to adjust certain reads/exports/opens relationships when using static factories | Does not re-resolve the dependency graph or turn a class loader into a sandbox |

A `Module` belongs to **one layer** and is bound to **one class loader**. Conversely, **one class loader can serve multiple modules** if package and loading model conditions are met. Class identity is still based on **binary name + defining class loader**; module readability and exports are **additional** access checks.

Basic model:

~~~text
ModuleFinder.of(pluginDirectory)
         |
         v
parent.configuration().resolve(finder, before, roots)
         |
         v
Configuration (determines which module reads which)
         |
         +---- defineModulesWithManyLoaders(cf, parentLoader)
         |           each module → JDK-created loader
         |
         +---- defineModules(cf, moduleName -> loader)
                     each module → host-selected loader
         |
         v
ModuleLayer
         |
         +---- findModule("demo.alpha")
         +---- findLoader("demo.alpha")
~~~

**ModuleLayer does not guarantee safety for untrusted code.** Modules/plugins in the same JVM still execute within that JVM process; layers and class loaders organize namespaces and control access, rather than replacing process isolation, artifact verification, or OS-level permission controls.

## 2. Important Java 17 APIs

All methods belong to `java.lang.ModuleLayer`:

| Creation Mode | Method | Return Value | Meaning |
| --- | --- | --- | --- |
| Many loaders, one parent layer | parent.defineModulesWithManyLoaders(cf, parentLoader) | ModuleLayer | JDK creates **a separate loader for each module** in `cf` |
| Many loaders, multiple parents or controller needed | ModuleLayer.defineModulesWithManyLoaders(cf, parentLayers, parentLoader) | ModuleLayer.Controller | Static factory; call `controller.layer()` to get the layer |
| Custom mapping, one parent layer | parent.defineModules(cf, nameToLoader) | ModuleLayer | `Function<String, ClassLoader>` selects a loader by module name |
| Custom mapping, multiple parents or controller needed | ModuleLayer.defineModules(cf, parentLayers, nameToLoader) | ModuleLayer.Controller | Host owns the mapping and gets a `Controller` |
| One shared JDK-created loader | parent.defineModulesWithOneLoader(cf, parentLoader) | ModuleLayer | All modules in `cf` share one new loader |

**Easy to confuse:** the `parentLoader` parameter of `defineModulesWithManyLoaders` is the **parent ClassLoader of the new loaders**, not a shared loader that **defines** all modules. To get the loader that actually defines a module, call `layer.findLoader(moduleName)` rather than grabbing `parentLoader` and guessing.

Instance factories require `Configuration` to have exactly one parent configuration matching the configuration of the receiver layer. Static factories accept a `parentLayers` list in the exact order of `cf`'s parent configurations; a mismatch or wrong order can throw `IllegalArgumentException`. In this lab we only use `ModuleLayer.boot()` as the parent, so we choose the instance form for readability.

**ModuleLayer.Controller** is the management handle returned by static factories, useful when a framework needs `addReads`, `addExports`, or `addOpens` under controller authority. These operations have preconditions and require explicit governance; they do not modify `module-info.java` on disk and must not be treated as a way to bypass all module checks.

## 3. Choosing a Loader Model Based on Needs

### 3.1. defineModulesWithManyLoaders: One Loader per Module

The JDK automatically creates a corresponding loader for each module in `Configuration`. The new loaders have the passed `parentLoader` as their parent. Loaders provided by the JDK know **direct delegation** by package/module: when code needs a type from another module where read/export edges permit, it can forward the request to the loader containing that module. Thus, a module is not necessarily completely isolated from modules it is allowed to read.

Advantages:

- The host does not have to write its own loader that understands the module path, resource lookup, and delegation between named modules.
- Easy to inspect `layer.findLoader(name)` and identify package/class boundaries per module.
- Avoids forcing multiple modules to share one defining loader, useful when modules want separate class identity and lifecycles.

Limitations:

- Creating extra loaders incurs memory, metadata, and operational overhead; large module counts require management.
- Module readability/exports still apply. Having a separate loader **does not allow** a module to access unexported packages.
- The loaders share a parent, and JDK-created loaders can delegate to readable modules; this is **not** security isolation or a fully automatic dependency versioning mechanism.
- Each module having its own loader **does not mean** automatic unload/reload when replacing JARs; live references will keep the loader/module alive.

### 3.2. defineModules: Custom Mapping

When calling `defineModules(cf, name -> loader)`, the JVM **does not create loaders on the host's behalf**. The function must return a valid `ClassLoader` for each module name in `Configuration`. For example, the host may want to:

- Pick per-plugin loaders according to policy;
- Map a group of modules to the same loader when packages do not conflict;
- Combine existing loaders with loaders from a plugin management system;
- Custom-control resource lookup, bytecode instrumentation, delegation, or metrics.

In return, **responsibility for class loading and module delegation shifts to the host**. The Java 17 documentation requires host-implemented loaders to respect module readability; loaders should be registered as **parallel-capable** to avoid deadlocks during concurrent class loading. Before a module is used, the loader must be ready to read classes and resources of the mapped module.

Returning `null` or the platform class loader from the mapping function is invalid; mapping multiple modules with the **same package** to the same loader, using a loader that already defined a module of the same name, or using a loader that already defined a type in a package belonging to a new module can cause `LayerInstantiationException`. **Do not build the mapping by guessing loaders by resolution order**; the module name is the mandatory key.

## 4. Workflow from Modular JARs to a Layer

The host needs artifacts containing **module-info.class** or valid module descriptors. For explicit named modules:

1. Package modules into modular JARs in a plugin directory.
2. Use `ModuleFinder.of(pathToDirectory)` so the host reads the module descriptors.
3. Choose a parent layer (usually `ModuleLayer.boot()`).
4. Resolve from `parent.configuration().resolve(finder, ModuleFinder.of(), roots)`, where `roots` are the module names to bring into the graph.
5. Choose `defineModulesWithManyLoaders` or `defineModules` with a prepared mapping.
6. Obtain loaders via `layer.findLoader(moduleName)`, load classes/instantiate providers via the host's contract.
7. Manage lifecycle, exceptions, tasks, resources, and references while the plugin remains active.

**ModuleFinder does not scan arbitrary JARs on the classpath and turn them into modules in a layer.** It reads the paths supplied by the host. The process module path and runtime `ClassLoader` URL search are separate mechanisms; do not mix classpath-based SPI with explicit module declarations.

Distinguishing errors:

| Stage | Example Error | What to Check |
| --- | --- | --- |
| Finder | Unreadable artifact, invalid module descriptor, duplicate name | JAR files, `module-info.class`, directory contents, `ModuleFinder` |
| Resolution | Missing `requires` or unresolvable graph | Module names, `requires`, parent/before `ModuleFinder` |
| Define layer | Invalid mapping, loader contains already-defined package, package conflict | Name → loader mapping, package ownership, and relationship with parent |
| Load class | Class not in module/loader or wrong name | `layer.findLoader`, JAR path, package |
| Link/access | `NoClassDefFoundError`, `IllegalAccessError`, or reflective access error | `requires`, `exports`/`opens`, dependencies/versions, and class identity |
| Invoke | Plugin constructor or method throws exception | Plugin lifecycle, configuration, resources, and business logic |

An important point is that **successful `Configuration` resolution does not mean plugin code has loaded successfully**. Much of class loading can remain lazy and occur only when the host first uses the implementation.

## 5. Java 17+ Lab with Two Independent Named Modules

The lab builds two modular JARs: `demo.alpha.jar` and `demo.beta.jar`. They only depend implicitly on `java.base`, with **no `requires` between each other**. This is an intentional choice so the `URLClassLoader` mapping model in the lab is easy to follow; when complex inter-module dependencies exist, the host must implement proper delegation instead of mechanically copying a minimal loader snippet.

Structure:

~~~text
lab/
├── src/
│   ├── demo.alpha/
│   │   ├── module-info.java
│   │   └── demo/alpha/api/Alpha.java
│   ├── demo.beta/
│   │   ├── module-info.java
│   │   └── demo/beta/api/Beta.java
│   └── host/LayerDemo.java
├── build/               (created during compilation)
└── modules/             (contains the two modular JARs)
~~~

### 5.1. Module demo.alpha

File **src/demo.alpha/module-info.java**:

~~~java
module demo.alpha {
    exports demo.alpha.api;
}
~~~

File **src/demo.alpha/demo/alpha/api/Alpha.java**:

~~~java
package demo.alpha.api;

public final class Alpha {
    private Alpha() {}

    public static String message() {
        return "alpha";
    }
}
~~~

Declaring `exports demo.alpha.api` grants code in the host's unnamed module access to **public types and public methods** in this package. Without `exports`, public reflective calls such as `getMethod(...).invoke(...)` from the host can fail with `IllegalAccessException` even when the class was found by the loader.

### 5.2. Module demo.beta

File **src/demo.beta/module-info.java**:

~~~java
module demo.beta {
    exports demo.beta.api;
}
~~~

File **src/demo.beta/demo/beta/api/Beta.java**:

~~~java
package demo.beta.api;

public final class Beta {
    private Beta() {}

    public static String message() {
        return "beta";
    }
}
~~~

The two modules use non-overlapping packages, helping the lab clearly illustrate module-to-loader mapping. They are not automatic modules inferred from filenames; `module-info.java` defines the names `demo.alpha` and `demo.beta`.

### 5.3. Host Creating Two Layers in Two Ways

File **src/host/LayerDemo.java**:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.Map;
import java.util.Set;

public final class LayerDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: LayerDemo <modules-directory>");
        }

        Path dir = Path.of(args[0]).toAbsolutePath();
        ModuleLayer parent = ModuleLayer.boot();

        ModuleFinder finder = ModuleFinder.of(dir);
        Configuration configuration = parent.configuration()
                .resolve(finder, ModuleFinder.of(),
                        Set.of("demo.alpha", "demo.beta"));

        // Approach 1: let the JDK create a separate ClassLoader for each module.
        ModuleLayer many = parent.defineModulesWithManyLoaders(
                configuration, ClassLoader.getSystemClassLoader());
        show("many", many);

        // Approach 2: host selects a loader per module name.
        URL alphaUrl = dir.resolve("demo.alpha.jar").toUri().toURL();
        URL betaUrl = dir.resolve("demo.beta.jar").toUri().toURL();

        try (URLClassLoader alphaLoader = new URLClassLoader(
                     new URL[] {alphaUrl}, ClassLoader.getSystemClassLoader());
             URLClassLoader betaLoader = new URLClassLoader(
                     new URL[] {betaUrl}, ClassLoader.getSystemClassLoader())) {

            Map<String, ClassLoader> byName = Map.of(
                    "demo.alpha", alphaLoader,
                    "demo.beta", betaLoader);

            ModuleLayer custom = parent.defineModules(
                    configuration, name -> {
                        ClassLoader loader = byName.get(name);
                        if (loader == null) {
                            throw new IllegalArgumentException(
                                    "No loader mapped for " + name);
                        }
                        return loader;
                    });

            show("custom", custom);
        }
    }

    private static void show(String label, ModuleLayer layer)
            throws ReflectiveOperationException {
        ClassLoader alphaLoader = layer.findLoader("demo.alpha");
        ClassLoader betaLoader = layer.findLoader("demo.beta");

        Class<?> alpha = Class.forName(
                "demo.alpha.api.Alpha", true, alphaLoader);
        Class<?> beta = Class.forName(
                "demo.beta.api.Beta", true, betaLoader);

        System.out.println(label + " alpha="
                + alpha.getMethod("message").invoke(null));
        System.out.println(label + " beta="
                + beta.getMethod("message").invoke(null));
        System.out.println(label + " distinct="
                + (alphaLoader != betaLoader));
        System.out.println(label + " named="
                + (alpha.getModule().isNamed()
                   && beta.getModule().isNamed()));
    }
}
~~~

Explanation:

- `ModuleFinder.of(dir)` finds the two modular JARs packaged inside `modules/`.
- The boot layer's `configuration()` is the parent `Configuration`; `resolve` uses both module names as roots.
- `many` creates two new loaders; `layer.findLoader("demo.alpha")` and `layer.findLoader("demo.beta")` return the loaders actually bound to the modules.
- `custom` maps **exact module names** to two independent `URLClassLoader` instances, created and configured with URLs before defining the layer. To illustrate mapping, each loader contains only its respective module JAR.
- The host does not compile-time import `Alpha`/`Beta`: it loads classes by binary name and the loader returned from the layer, then invokes the public static methods via reflection.
- Packages `demo.alpha.api` and `demo.beta.api` are exported in `module-info`; therefore the host can invoke public members via ordinary reflection.
- Both layers are created from the **same Configuration**, yet with **different loaders**. The `Module` objects of the two layers are distinct; do not share implementation instances across two loaders without a common contract.
- `try-with-resources` closes the `URLClassLoader` instances of the **custom example** after finishing. The JDK-created loaders in `many` are not application-owned `URLClassLoader` instances; do not assume you can close them by casting.

**Important note on custom example scope:** the two modules only need `java.base`, so the system parent loader suffices to resolve the JDK types used. If `demo.beta` had `requires demo.alpha` and needed to load `Alpha` directly, two simple `URLClassLoader`s with separate URLs **do not automatically guarantee cross-delegation according to module readability**; for real problems, use JDK-created loaders or write proper loader/module routing and test thoroughly.

### 5.4. Compiling Modular JARs and the Host

Run from the `lab/` directory on bash/POSIX with JDK 17 or higher:

~~~bash
mkdir -p build/alpha build/beta build/host modules

javac -encoding UTF-8 -d build/alpha src/demo.alpha/module-info.java src/demo.alpha/demo/alpha/api/Alpha.java
jar --create --file modules/demo.alpha.jar -C build/alpha .

javac -encoding UTF-8 -d build/beta src/demo.beta/module-info.java src/demo.beta/demo/beta/api/Beta.java
jar --create --file modules/demo.beta.jar -C build/beta .

javac -encoding UTF-8 -d build/host src/host/LayerDemo.java
java -cp build/host LayerDemo modules
~~~

These are **two explicit named modules**; the JARs are packaged with `module-info.class` and implementation classes. The host runs on a classpath containing only `build/host` and receives the directory of modular JARs as an argument. Do not place `modules/*.jar` onto the host `-cp`; the host finds them via `ModuleFinder` at runtime.

Expected stdout when files and commands match the above:

~~~text
many alpha=alpha
many beta=beta
many distinct=true
many named=true
custom alpha=alpha
custom beta=beta
custom distinct=true
custom named=true
~~~

The `distinct=true` lines prove that **within each layer**, the two modules use two different loaders. `named=true` shows the loaded classes belong to named modules rather than merely residing in the classpath's unnamed module.

To inspect the artifacts:

~~~bash
jar --describe-module --file modules/demo.alpha.jar
jar --describe-module --file modules/demo.beta.jar
~~~

The output of `jar --describe-module` can include module name, packages, exports, and `requires java.base`; do not copy tool stdout verbatim across different JDK versions and treat the formatting as a stable contract. What needs verification is that `demo.alpha`/`demo.beta`, exported packages, and `module-info.class` are indeed packaged in the JARs.

On Windows use **;** if `-cp` has multiple entries; in the host command above there is only one entry so no change is needed. `mkdir -p` is bash syntax; in PowerShell you can create directories with `New-Item -ItemType Directory -Force`.

## 6. Grouping Modules into the Same Loader with Custom Mapping

A practical reason to use `defineModules` is grouping modules with separate packages into a shared host-managed loader. Example **illustrative code, not a complete program**:

~~~java
// Assumes parent, configuration, alphaJar, and betaJar are already defined.
// The host must close sharedLoader after all modules stop using it.
URLClassLoader sharedLoader = new URLClassLoader(
        new URL[] {alphaJar.toUri().toURL(), betaJar.toUri().toURL()},
        ClassLoader.getSystemClassLoader());

ModuleLayer shared = parent.defineModules(configuration,
        name -> switch (name) {
            case "demo.alpha", "demo.beta" -> sharedLoader;
            default -> throw new IllegalArgumentException(name);
        });
~~~

This approach uses **one loader** for two modules with distinct packages. If the goal is simply "one new loader for all modules" without needing custom handling, `defineModulesWithOneLoader` is usually simpler and performs JDK-provided direct delegation. Do not use manual mapping merely to mimic an already-provided API.

**Package constraint:** two modules sharing a package cannot be validly defined when mapped to the **same ClassLoader**. This is one reason to keep plugin namespaces clearly separated. Mapping to different loaders can change intra-loader conflict conditions, yet does not fix mismatches in `requires`, `exports`, `opens`, or class identity.

**Live plugin data:** even when layer definition succeeds, once the host calls `close()` on a `URLClassLoader`, loading additional classes/resources from the URLs may stop working. Therefore, the plugin manager must keep the loader alive for the duration of the active session; close it only after stopping related tasks, providers, listeners, and resources. Calling `close()` does not prove classes are immediately unloaded.

## 7. Readability, Exports, Opens, and Delegation

Having separate loaders is only half the problem. JPMS also controls **which module may read which module** and **which packages are exported**:

| Mechanism | Practical Meaning | How to Verify |
| --- | --- | --- |
| `requires demo.alpha` in `demo.beta`'s `module-info` | `demo.beta` reads `demo.alpha` in compile/runtime module graph | Configuration resolution and `Module.canRead` |
| `exports demo.alpha.api` | Allows other modules to access public types in the exported package | `Module.isExported` and access errors |
| `exports demo.alpha.api to demo.beta` | Grants qualified exports only to the named module | Not public to other hosts by default |
| `opens demo.alpha.internal` | Grants appropriate deep reflection to the package; not the same as exporting types at compile time | `Module.isOpen` and reflection permissions |
| loader delegation | If a type belongs to another readable module, the loader must know to delegate to the loader actually defining that type | Testing `Class.forName` and cross-module invocations |
| `layer.findLoader(name)` | Finds the loader bound to a module defined in the layer or parent layers | Do not equate it with TCCL or system loader |

For example, when `demo.beta` needs a public type from `demo.alpha`, update beta's `module-info.java` to:

~~~java
module demo.beta {
    requires demo.alpha;
    exports demo.beta.api;
}
~~~

This is an **illustrative descriptor change**, not a complete runnable lab yet: you still need to update beta's classes, compile with a module path containing `demo.alpha`, and test delegation. With `defineModulesWithManyLoaders`, JDK-created loaders support direct delegation for readable packages/modules. With custom loaders, the host must design the corresponding delegation paths and avoid delegation cycles that cause deadlocks.

**Do not confuse TCCL with the defining loader.** `Thread.currentThread().setContextClassLoader(...)` only changes the thread's context class loader for APIs that use it; it does not alter `ModuleLayer` mappings or the class identity of already-defined classes. To obtain the exact loader of a named module, use `layer.findLoader(moduleName)`.

**Do not confuse `opens` with `exports`.** Deep reflection into non-public members requires corresponding `opens` permissions, whereas accessing public module APIs in the lab is supported via `exports`. Obtaining a `Class` object by the host does not guarantee every method can be invoked if the module does not open/export the package.

## 8. ServiceLoader in a Plugin Layer

If an application uses SPI instead of reflection to select classes by name, a named module usually declares the service in `module-info.java`:

~~~java
module demo.plugin {
    requires demo.api;
    provides demo.api.PluginService with demo.plugin.PluginServiceImpl;
}
~~~

On the consumer named module side, declare `uses demo.api.PluginService` when using service binding. With a defined layer, the host can use the explicit layer overload:

~~~java
// Integration illustration: assumes layer and PluginService already exist.
ServiceLoader<PluginService> providers =
        ServiceLoader.load(layer, PluginService.class);
for (PluginService provider : providers) {
    provider.run();
}
~~~

The snippets here **are not part of the full lab build** because the lab uses reflection and does not define `demo.api.PluginService`. They clarify the extension path for real SPI plugin integration.

`ServiceLoader.load(layer, service)` finds providers via the module layer mechanism, differing from `ServiceLoader.load(service)` which uses the thread context class loader. Pay attention to module graph scope, `uses`/`provides`, shared SPI class identity, and checking providers extended in dependent layers. Do not drop a JAR into a module layer and assume `ServiceLoader` will scan every class implementing an interface without service configuration.

In systems containing both classpath plugins and named modules, distinguish **`META-INF/services` on the classpath** from `provides` in explicit named modules; provider identification and discovery depend on module/loader type. Do not mix the two discovery mechanisms haphazardly.

## 9. Common Mistakes with Custom Loader Mapping

**Mistake 1 — confusing `parentLoader` with the module's loader.**

~~~java
// Incorrect when checking the loader that defines the module:
ClassLoader assumed = ClassLoader.getSystemClassLoader();

// Correct:
ClassLoader actual = layer.findLoader("demo.alpha");
~~~

In many-loader mode, `actual` is the new loader created by the JDK; the system loader is only the parent passed in.

**Mistake 2 — merely returning a `URLClassLoader` whose URLs lack dependencies.** If a module requires classes from another module, Java must both permit the `requires`/`exports` relationship and locate the class via proper delegation. A `URLClassLoader` containing only its own JAR does not automatically coordinate every named module dependency. Do not treat `LayerInstantiationException` or `NoClassDefFoundError` as proof to abandon JPMS; inspect the graph and mapping.

**Mistake 3 — incomplete mapping across all modules in the `Configuration`.** `Function<String, ClassLoader>` receives module names requested by the JVM. If a mapping is missing, returning `null` will be rejected; if you proactively throw `IllegalArgumentException`, the error surfaces immediately during `defineModules`. Build a complete map from resolved module names before defining the layer.

**Mistake 4 — reusing a loader that has already defined classes in a package about to be assigned.** Runtime package identity by defining loader/module can render the new module definition invalid. Prepare fresh loaders before loading plugin classes and do not add a module to a loader that already has a module of the same name.

**Mistake 5 — module is readable, but package is not exported.** Reflection may see the class name yet fail when invoking methods. Check `exports`/`opens` instead of just tweaking loader URLs.

**Mistake 6 — closing a loader too early.** `URLClassLoader.close()` restricts loading new classes/resources from its URLs while running code may still be active. When updating a plugin, stop work, clean up references, create a next-generation layer/loader, and only then switch the registry; do not promise "in-place class hot swap" inside the existing layer.

**Mistake 7 — thinking a class loader is a sandbox.** Plugin code can still execute with the process's privileges. Untrusted plugins require artifact provenance policies and proper process/container isolation.

**Mistake 8 — ignoring the risk of partial failure with custom mapping.** The Java 17 documentation notes that `defineModules` with a custom mapping may **not be atomic depending on implementation**: some modules may already be defined in the JVM even if the method fails on another module. Do not retry with the same loaders after a failure without assessing state; design to allocate fresh loaders and roll back resource ownership at the plugin manager layer.

## 10. Choosing a Solution, Validation, and Operations

| Criterion | withManyLoaders | defineModules with mapping |
| --- | --- | --- |
| Who creates the loaders? | JDK | Host |
| One loader per module? | Yes | Depends on mapping |
| Delegation per module graph | JDK-provided loaders perform direct delegation | Host is responsible for implementing it properly |
| Choosing parent loader | Pass `parentLoader` for the new loaders | Choose parent when host creates loaders |
| Control over `findClass`/resources | Follows JDK-created loader behavior | Customizable if host truly implements it |
| Maintenance cost | Usually lower | Higher; requires concurrency and linkage testing |
| Typical use case | Loading multiple named plugin modules with JPMS dependencies | Plugin manager with custom loaders/routing/policies |
| Lifecycle | Still must manage references/providers/tasks | Host also manages `close()` on loaders it created |

When building a real system, add:

1. **Artifact preflight:** module identity, version, source/checksum, `module-info`, overlapping packages, `requires` list, and runtime dependencies.
2. **Resolution before definition:** clearly report `FindException`/`ResolutionException` and the offending module name; avoid uncontrolled duplicate module names at different versions in the graph.
3. **Verifiable mapping:** module → loader table, loader classpath/resources, parent chain, delegation paths for required modules, and package ownership policy.
4. **Startup validation:** create the layer, verify `findModule`/`findLoader`, actually load classes/provide services, and confirm `exports`/`opens` and key API calls.
5. **Failure isolation:** distinguish resolve, define, class loading, reflection, and provider runtime errors. If custom definition fails, do not assume the operation rolled back atomically.
6. **Lifecycle:** keep loaders alive while the plugin is active; stop accepting tasks, stop threads/callbacks, release references, and only then close host-owned loaders.
7. **Isolation and security:** verify plugin trust and consider out-of-JVM execution when true sandboxing is needed; a module layer is not an OS permission mechanism.

**Extension exercises:** (a) change `beta`'s mapping to the same `alphaLoader` after ensuring `URLClassLoader` has both JARs and two separate packages, then compare `distinct`; (b) add `requires demo.alpha` to `beta`, design a custom loader with accurate delegation, and compare with `withManyLoaders`; (c) remove `exports demo.alpha.api` and observe the reflection error; (d) try defining two modules with the same package into one custom loader; (e) trace the lifecycle of two generations of plugin loaders during an artifact update.

**API Sources:** [Java SE 17 — ModuleLayer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html), [Java SE 17 — ModuleFinder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html), [Java SE 17 — Configuration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/Configuration.html).

Technical principle: **use `defineModulesWithManyLoaders` when you need a JDK-managed loader per module; use `defineModules` when you genuinely need a custom mapping policy and are ready to own loading/delegation, package ownership, concurrency, and lifecycle**. Both must start from a valid `Configuration` and be verified with actual class-loading behavior.