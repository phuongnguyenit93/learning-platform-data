# Class Loaders in a Module Layer

## <a id="tong-quan">What Role Does a Class Loader Play in ModuleLayer?</a>

In the Java Platform Module System (JPMS), a **module** groups packages, declares dependencies, and decides which parts of its API are public. A **module layer** (`ModuleLayer`) is a set of modules whose dependencies have been resolved so they can work together. Meanwhile, a **class loader** is the component that locates and defines classes (`Class<?>`) in the JVM.

Three related but distinct concepts:

- `Configuration` describes *which modules are resolved and which modules they read*.
- `ModuleLayer` brings that configuration into the runtime environment, binds each module to a class loader, and may have one or more parent layers.
- `ClassLoader` is responsible for loading class bytecode and also participates in determining class identity in the JVM.

Imagine an application with foundational modules in the boot layer and two plugins loaded later:

```text
ModuleLayer.boot()                (parent layer)
  ├─ java.base                     → bootstrap loader
  └─ application modules           → corresponding loaders
            │
            │ parent configuration + parent class loader
            ▼
ModuleLayer pluginLayer           (child layer)
  ├─ demo.greeter                  → pluginLoader
  └─ demo.report                   → pluginLoader or another loader
```

The arrow between layers represents the **layer** parent relationship; the arrow from a module to a loader represents the mapping used to load classes. These are two separate relationships. A layer can contain many modules, and many modules can share a single loader.

**Learning path:** understand the difference between modules and loaders → see how a layer creates mappings → practice creating a child layer → observe class identity and access permissions → choose a suitable loader strategy.

## <a id="vi-sao-can-class-loader">Why Does a Layer Need to Map Modules to Class Loaders?</a>

Before JPMS, a class loader typically looked up classes by binary name such as `com.example.Service` on the classpath. With JPMS, the JVM also knows which **named module** a class belongs to; that module can expose packages with `exports`, open packages for reflection with `opens`, and declare dependencies with `requires`.

Layers help applications implement scenarios such as:

- Loading a set of plugin modules discovered at runtime, outside the startup module set.
- Creating two layers with different versions or implementations of the same module name, when the dependency structure allows it.
- Choosing a policy of sharing one loader or giving each module its own loader.
- Querying which layer a class belongs to and which loader is used to load the class.

Not every module has its own loader. Conversely, a class loader does not create `requires`/`exports` rules by itself. **Ability to locate bytecode** and **module-level access rights** are two different conditions.

A class's identity at runtime is bound to **binary name + defining loader**. Thus, two classes with the same name defined by two different loaders are two different types in the JVM. Casting between them can throw `ClassCastException`, even when the source code looks identical.

## <a id="anh-xa-module-loader">From Configuration to Module–Loader Mapping</a>

A typical workflow consists of four steps:

1. Use `ModuleFinder` to locate modular JARs or exploded modules.
2. Use `Configuration.resolve(...)` to resolve the root modules and their dependencies, based on the parent layer's configuration.
3. Call one of the `defineModules...` methods to create the layer and bind loaders to each module in the new configuration.
4. Use `layer.findLoader(moduleName)` to retrieve the loader of a module defined **directly in that layer**, then use the loader to load classes.

Example data relationships:

| Component | Answers the question | Example |
|---|---|---|
| `ModuleFinder` | Where is the module code located? | `plugin-mods/` directory |
| `Configuration` | Which modules are needed, and whom do they read? | `demo.greeter`, `java.base` |
| `ModuleLayer` | In which layer are the modules defined? | `pluginLayer` |
| `ClassLoader` | Which loader defined this class? | `pluginLayer.findLoader("demo.greeter")` |

A module in the new configuration can read modules from parent layers. That does not mean every class is loaded by a parent layer's loader: JPMS still uses loader delegation links and checks accessibility according to the module configuration.

**Two kinds of “parent” to distinguish:**

- **Parent layer:** provides existing modules/configurations to resolve dependencies for the child layer.
- **Parent loader:** the `parentLoader` argument when Java creates new loaders; used to delegate loading of appropriate classes.

`parentLoader` is a `ClassLoader`, not a `ModuleLayer`; passing the system loader into a layer-creation method does not make the new layer part of the boot layer.

## <a id="ba-cach-gan-loader">Three Ways to Attach Class Loaders When Creating a Layer</a>

### 1. One Loader for All New Modules

```java
ModuleLayer child = ModuleLayer.boot()
    .defineModulesWithOneLoader(config, ClassLoader.getSystemClassLoader());
```

`defineModulesWithOneLoader` creates **one new loader** to define the modules in `config`. The argument passed in is the **parent loader of the new loader**, not a request to use the system loader directly as the plugin's loader.

Advantage: simple organization, with the new modules sharing the same loader. Limitation: lower class-identity separation; incompatible packages cannot arbitrarily be defined in the same loader.

### 2. A Separate Loader per New Module

```java
ModuleLayer child = ModuleLayer.boot()
    .defineModulesWithManyLoaders(config, ClassLoader.getSystemClassLoader());
```

`defineModulesWithManyLoaders` creates a new loader for each module defined in the configuration. Modules still use JPMS to read each other according to dependency relationships; do not assume separate loaders automatically prevent all interaction between modules.

Advantage: clearer per-module class namespace separation, convenient when designing plugin systems. Trade-off: more loaders, so API sharing and reference retention must be managed carefully.

### 3. Choosing a Loader per Module Name Yourself

```java
Map<String, ClassLoader> mapping = Map.of(
    "demo.greeter", greeterLoader,
    "demo.report", reportLoader
);

ModuleLayer child = ModuleLayer.boot()
    .defineModules(config, mapping::get);
```

`defineModules` accepts a `Function<String, ClassLoader>` returning the loader for each module in the configuration. This is an advanced option: the application is responsible for the loaders, how classes are loaded, delegation, and package compatibility. The snippet assumes `greeterLoader` and `reportLoader` have been properly initialized; writing custom class loaders is outside this introductory example.

| Strategy | Loaders for new modules | Best suited when |
|---|---|---|
| `defineModulesWithOneLoader` | One new shared loader | Small set of modules, wanting simple setup |
| `defineModulesWithManyLoaders` | One new loader per module | Wanting clear loader boundaries per module |
| `defineModules` | Supplied by the application | Needing a custom class-loading policy |

With static overloads accepting a `List<ModuleLayer>` of parents, the method returns `ModuleLayer.Controller`; call `controller.layer()` to retrieve the layer. In this lesson, examples use the instance overload on a single parent `ModuleLayer`, which returns `ModuleLayer` directly.

## <a id="vi-du-tao-layer">Complete Example: Loading a Modular JAR in a Child Layer</a>

Suppose the host application runs on the classpath, while the plugin is packaged as the modular JAR `plugin-mods/demo.greeter.jar`.

**1. Plugin module descriptor — `module-info.java`:**

```java
module demo.greeter {
    exports demo.greeter.api;
}
```

**2. Public API class inside the plugin — `demo/greeter/api/Greeter.java`:**

```java
package demo.greeter.api;

public final class Greeter {
    public Greeter() {}

    public String hello(String name) {
        return "Hello, " + name + "!";
    }
}
```

**3. Host application — `Host.java`:**

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public class Host {
    public static void main(String[] args) throws Exception {
        ModuleLayer boot = ModuleLayer.boot();

        // Specify where the plugin modular JARs are located.
        ModuleFinder finder = ModuleFinder.of(Path.of("plugin-mods"));

        // Create a child configuration based on modules already in the boot layer.
        Configuration config = boot.configuration().resolve(
            finder,
            ModuleFinder.of(),
            Set.of("demo.greeter")
        );

        // One new loader is created for the modules in config.
        ModuleLayer pluginLayer = boot.defineModulesWithOneLoader(
            config,
            ClassLoader.getSystemClassLoader()
        );

        Module pluginModule = pluginLayer.findModule("demo.greeter")
            .orElseThrow();
        ClassLoader pluginLoader = pluginLayer.findLoader("demo.greeter");

        Class<?> type = pluginLoader.loadClass("demo.greeter.api.Greeter");
        Object instance = type.getConstructor().newInstance();
        Object result = type.getMethod("hello", String.class)
            .invoke(instance, "JPMS");

        System.out.println(result);
        System.out.println(type.getModule() == pluginModule);
        System.out.println(type.getClassLoader() == pluginLoader);
    }
}
```

To run the example yourself with JDK 17+ and the file layout above, compile and package:

```bash
javac -d out/plugin src/demo.greeter/module-info.java src/demo.greeter/demo/greeter/api/Greeter.java
jar --create --file plugin-mods/demo.greeter.jar -C out/plugin .
javac -d out/host Host.java
java -cp out/host Host
```

Create the `plugin-mods` directory before running the `jar` command. The commands above show relative paths; you can adjust them to fit your project directory.

Main output:

```text
Hello, JPMS!
true
true
```

The first `true` confirms the class belongs to the module obtained from the layer. The second confirms that the loader mapped by the layer to the module is indeed the loader that defined `Greeter`. The example works because the `demo.greeter.api` package is `exports`; if a class can only be loaded but its package is not properly exported, invoking it from the host application may not be permitted.

## <a id="truy-van-loader">Finding Loaders and Identifying Which Layer a Module Belongs To</a>

```java
ModuleLayer boot = ModuleLayer.boot();

ClassLoader javaBaseLoader = boot.findLoader("java.base");
System.out.println(javaBaseLoader == null); // true: bootstrap loader

// With a pluginLayer created as in the example:
Module plugin = pluginLayer.findModule("demo.greeter").orElseThrow();
ClassLoader loader = pluginLayer.findLoader("demo.greeter");
System.out.println(plugin.getClassLoader() == loader);
```

Practical rules to follow:

- `ModuleLayer.findLoader(name)` only accepts names of modules defined **in the layer receiving the call itself**; a name not in that layer throws `IllegalArgumentException`.
- A `null` value from `findLoader` can be valid: the module is loaded by the **bootstrap class loader**, such as `java.base` in the boot layer.
- `ModuleLayer.findModule(name)` can continue searching in parent layers. Therefore, `findModule` finding a module does not guarantee `findLoader` on the current layer will accept that name. If you want the loader of the found module, use `module.getClassLoader()`.
- `Class.forName("demo.greeter.api.Greeter")` from the host application may not see a class in a child layer: this method uses the loader associated with the caller according to the corresponding rules. Retrieve the loader from the layer or use `Class.forName(module, className)` when you have the appropriate `Module`.

With `Class.forName(Module, String)`, the result is `null` if the class is not found in the specified module. This API differs from the `Class.forName(String)` overload, which throws `ClassNotFoundException` when a class is not found.

## <a id="loader-va-quyen-truy-cap">Being Able to Load a Class Does Not Mean Being Able to Use It</a>

Consider a plugin with the descriptor:

```java
module demo.greeter {
    requires demo.contract;
    exports demo.greeter.api;
    opens demo.greeter.internal to demo.host;
}
```

- `requires demo.contract`: declares that the plugin reads the contract module. The module configuration resolves the dependency; the loader must have an appropriate path to load the required classes.
- `exports demo.greeter.api`: allows other modules to access `public` types in the API package, provided module readability conditions are satisfied.
- `opens demo.greeter.internal to demo.host`: allows deep reflection into the internal package for the module named `demo.host`; does not make that package a public compile-time API.
- `ClassLoader.loadClass(...)`: locates or loads `Class<?>`; does not automatically grant access to constructors, fields, or methods restricted by JPMS/Java visibility.

Distinguishing errors by layer/stage:

| Symptom | Where to check |
|---|---|
| Module not found during `resolve` | `ModuleFinder`, JAR path, module name, `requires` |
| `LayerInstantiationException` when creating layer | Loader mapping, overlapping packages, module definition constraints |
| `IllegalArgumentException` in `findLoader` | Module name is not defined directly in the queried layer |
| `ClassNotFoundException` | Binary name, JAR contents, loader being used |
| `IllegalAccessException` or `InaccessibleObjectException` | `public`, `exports`, `opens`, module readability |
| `ClassCastException` despite same class name | Two copies of the class came from two different defining loaders |

In plugin systems, a shared API should live in a module belonging to a parent layer and be referenced by the plugins together. If each plugin carries and loads its own copy of the API, objects of the same interface name may fail to cast between them.

## <a id="mot-hay-nhieu-loader">Observing the Difference Between One Loader and Many Loaders</a>

Suppose `config` resolves two new modules: `demo.greeter` and `demo.report`. You can compare:

```java
ClassLoader parentLoader = ClassLoader.getSystemClassLoader();
ModuleLayer boot = ModuleLayer.boot();

ModuleLayer one = boot.defineModulesWithOneLoader(config, parentLoader);
boolean sameOne = one.findLoader("demo.greeter")
    == one.findLoader("demo.report");

ModuleLayer many = boot.defineModulesWithManyLoaders(config, parentLoader);
boolean sameMany = many.findLoader("demo.greeter")
    == many.findLoader("demo.report");

System.out.println(sameOne);  // true
System.out.println(sameMany); // false
```

The example assumes both modules belong to `config` and can be defined successfully. Each call creates a new child layer, so `one` and `many` are two different layers.

Separate loaders change **class identity**, delegation, and reference lifetimes. They do not replace module dependency checks or encapsulation. The decision to use multiple loaders should be based on isolation needs, version management, and the shared interface between plugins and the host application.

## <a id="ung-dung-dong">Class Loaders and Plugin Systems</a>

When you need to discover service implementations, `ServiceLoader` is often more convenient than reflection by hard-coded class names:

```java
// ContractService is an interface from a shared API module in the parent layer.
// The plugin module must declare provides ... with ... in module-info.java.
ServiceLoader<ContractService> services =
    ServiceLoader.load(pluginLayer, ContractService.class);

for (ContractService service : services) {
    System.out.println(service.getClass().getModule().getName());
}
```

The example assumes `ContractService` is already defined and visible from the host application. `ServiceLoader.load(layer, serviceType)` looks up providers in the specified layer and parent layers according to JPMS rules; plugins can advertise providers using `provides ... with ...`. This reduces the need to know implementation class names ahead of time and to use manual reflection.

**Lifecycle:** JPMS does not provide an `unloadModule` or `unloadLayer` button. When no live references retain the layer, class loader, `Class<?>`, plugin objects, and related components, the JVM *may* garbage-collect them. Simply dropping the `pluginLayer` variable does not guarantee the modules or classes have been freed; watch out for static caches, threads, thread context class loaders, and live services/providers.

**Class loaders are not an absolute security boundary.** Use layers/plugins to organize code and manage dependencies; do not treat them as a sandbox sufficient for running untrusted code.

## <a id="sai-lam-pho-bien">Common Misconceptions</a>

1. **“Every module has one class loader.”** False: `defineModulesWithOneLoader` binds multiple modules to the same loader.
2. **“Passing the system loader means plugins are loaded by the system loader.”** False for both `defineModulesWith...` methods: Java creates a **new** loader with the system loader as its parent.
3. **“If `findModule` succeeds, `findLoader` on the same layer will surely succeed.”** Not necessarily: `findModule` can look in parent layers, whereas `findLoader` only looks up modules defined directly in that layer.
4. **“If a loader can find a class, any method can be called.”** False: `exports`/`opens` boundaries and Java access rules still apply.
5. **“Two classes with the same package and same name are the same type.”** Only true when the defining loader identity matches; different loaders can produce two distinct types.
6. **“Dropping the layer unloads it immediately.”** The JVM can only collect it when no references retain the classes, loaders, or related objects.

## <a id="thuc-hanh">Practice and Self-Check</a>

**Exercise 1 — Tracing loaders.** Run the `demo.greeter` example, print the module name of `Greeter`, compare `type.getClassLoader()` with `pluginLayer.findLoader("demo.greeter")`, and observe `ModuleLayer.boot().findLoader("java.base")`. Explain why the loader of `java.base` can be `null`.

**Exercise 2 — Comparing policies.** Create an additional modular JAR `demo.report` (it does not need to depend on `demo.greeter`). Resolve both module names, then use `defineModulesWithOneLoader` and `defineModulesWithManyLoaders` in turn. Compare the `==` result between the two loaders in the same layer, and explain which classes are shared and which loaders belong only to the new layer.

**Exercise 3 — Separating class loading and access.** Try removing `exports demo.greeter.api` from `module-info.java`, repackaging, and running `Host`. Note which step still finds `Class<?>` and which step no longer has sufficient access rights. Then restore `exports`. Analyze with two questions: *did the loader find the bytecode?* and *does the calling module have permission to access the type/member?*

**Self-check questions:**

- In what responsibilities do `ModuleLayer`, `Configuration`, and `ClassLoader` differ?
- Why can an application have multiple child layers with the same module name, yet should not arbitrarily mix objects from different loaders?
- When should you choose one loader, many loaders, or a custom loader mapping?
- Why can a module be found by `findModule` from a child layer while `findLoader` on the child layer reports an error?

**Takeaway:** configuration resolves module relationships; a layer defines modules into the runtime environment; a class loader defines classes. To verify where a class came from, inspect both `type.getModule()` and `type.getClassLoader()`, and compare them against the module and loader of the corresponding layer.