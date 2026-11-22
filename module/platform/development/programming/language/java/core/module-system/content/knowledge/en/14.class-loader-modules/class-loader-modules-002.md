# ModuleLayer Determines the Class Loader for Modules in Java

`ModuleLayer` is the mechanism of the Java Platform Module System (JPMS, since Java 9) used to create a set of modules whose dependencies have been resolved and **associate each module with a specific class loader**. To find out which class loader is responsible for loading classes of a module in a layer, call `layer.findLoader(moduleName)`; to find out which module a loaded class actually belongs to, inspect `clazz.getModule()`.

This lesson focuses on the relationship among `ModuleLayer`, `Configuration`, `Module`, and `ClassLoader`; how to define child layers; how to retrieve the right loader; and the limitations when applying them to plugins or applications that need to isolate sets of modules.

## 1. Distinguishing the Four Components

| Component | Responsibility |
| --- | --- |
| `module-info.java` / `ModuleDescriptor` | Declares the module name, `requires`, `exports`, `opens`, `uses`, `provides`. |
| `Configuration` | Describes the set of **resolved modules** and the dependency graph after resolution; does not yet create the actual runtime `Module` objects. |
| `ModuleLayer` | Contains the runtime modules along with parent layer relationships; when defining the layer, Java establishes which module goes with which class loader. |
| `ClassLoader` | Loads `Class` objects; one loader can be associated with multiple modules, or each module can have its own loader, depending on how the layer is created. |

You can visualize it as:

```text
ModuleLayer.boot()                     (parent layer, containing platform modules)
       |
       | defines child layer from Configuration
       v
ModuleLayer pluginLayer                (child layer)
  +-- module com.demo.api    -------> ClassLoader L
  +-- module com.demo.impl   -------> ClassLoader L  (one-loader)
```

The **parent relationship graph between layers** and the **parent delegation chain between class loaders** are two different relationships. When you pass `parentLoader` to a layer creation method, you specify the parent of the newly created loader, rather than turning all loaders in the parent layer into a single loader.

## 2. From Module Path to Class Loader: Sequence of Operations

1. **Find modules:** `ModuleFinder` reads modular JARs or compiled module directories.
2. **Resolve dependencies:** `Configuration.resolve(...)` determines the required modules for the set of root modules and links them with the parent configuration.
3. **Define the layer:** One of the `defineModules...` methods creates the runtime modules and establishes the `module name → class loader` mapping.
4. **Query the mapping:** `layer.findLoader("module.name")` returns the loader associated with a module defined **in that layer**.
5. **Load classes:** Use this loader to load a class belonging to the module, then inspect `Class.getModule()` and `Module.getLayer()` to see the result.

Abbreviated API flow example:

```java
ModuleLayer parent = ModuleLayer.boot();
ModuleFinder finder = ModuleFinder.of(Path.of("build/modules"));

Configuration config = parent.configuration().resolve(
    finder,
    ModuleFinder.of(),
    Set.of("com.example.greeting")
);

ModuleLayer child = parent.defineModulesWithOneLoader(
    config,
    ClassLoader.getSystemClassLoader()
);

ClassLoader loader = child.findLoader("com.example.greeting");
Class<?> greetingClass =
    loader.loadClass("com.example.greeting.api.Greeter");
```

`Configuration` determines **which modules** participate and whom they depend on; `defineModulesWithOneLoader` determines **which loader** is used to define those modules. Calling `resolve` alone does not yet create a child layer or new class loaders for the modules.

## 3. Three Ways to Specify Loaders for a Layer

| API | Mapping module → loader | Suitable when |
| --- | --- | --- |
| `defineModulesWithOneLoader(config, parentLoader)` | New modules of the layer **share a single new loader** whose parent is `parentLoader`. | A group of modules can share a class-loading namespace within a plugin or feature. |
| `defineModulesWithManyLoaders(config, parentLoader)` | **Each new module has its own loader**; the new loaders all delegate up to `parentLoader`. | Separate loaders are needed for individual modules within the same layer. |
| `defineModules(config, moduleName -> loader)` | The program supplies a loader for **each module name** via a mapping function. | You already have a custom class loader strategy and control class loading for the modules. |

The instance overloads in the table above use the receiving layer as the parent layer. Java also has static factories that take a `List<ModuleLayer>` to configure multiple parent layers; they return a `ModuleLayer.Controller`, from which you obtain the layer via `controller.layer()` and can adjust certain read, export, and open relationships when truly necessary.

Keep in mind:

- **One loader** does not mean all modules are merged into a single module. Each module still retains its own name, descriptor, `requires`, `exports`, and access rules.
- **Many loaders** do not turn each module into a separate process or security sandbox. It is a way to partition the class-loading namespace, not an OS resource isolation mechanism.
- **Custom mapping** requires that the class loader you provide can actually load the classes belonging to the modules assigned to it, while satisfying JPMS constraints. Do not arbitrarily assign multiple modules with conflicting packages to the same loader.

## 4. Complete Compilable and Runnable Example

This example uses Java 17+ (the layer APIs have been available since Java 9). We create a `com.example.greeting` module and load it from an application running on the classpath.

Directory structure:

```text
src/
├── com.example.greeting/
│   ├── module-info.java
│   └── com/example/greeting/api/Greeter.java
└── app/
    └── Main.java
```

**File `src/com.example.greeting/module-info.java`**

```java
module com.example.greeting {
    exports com.example.greeting.api;
}
```

**File `src/com.example.greeting/com/example/greeting/api/Greeter.java`**

```java
package com.example.greeting.api;

public final class Greeter {
    private Greeter() {}

    public static String message() {
        return "Hello from module "
            + Greeter.class.getModule().getName();
    }
}
```

**File `src/app/Main.java`**

```java
package app;

import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public class Main {
    public static void main(String[] args) throws Exception {
        // 1. Select the active parent layer.
        ModuleLayer boot = ModuleLayer.boot();

        // 2. Find the compiled modules.
        ModuleFinder finder = ModuleFinder.of(Path.of("build/modules"));

        // 3. Resolve com.example.greeting along with its dependencies.
        Configuration config = boot.configuration().resolve(
            finder,
            ModuleFinder.of(),
            Set.of("com.example.greeting")
        );

        // 4. Create a child layer; the layer's modules share a new loader.
        ModuleLayer child = boot.defineModulesWithOneLoader(
            config,
            ClassLoader.getSystemClassLoader()
        );

        // 5. Retrieve the loader through the layer instead of guessing the system loader.
        ClassLoader loader = child.findLoader("com.example.greeting");

        // 6. Use the corresponding loader to load the module's class.
        Class<?> clazz =
            loader.loadClass("com.example.greeting.api.Greeter");

        Module module = clazz.getModule();

        System.out.println("Module: " + module.getName());
        System.out.println("Correct layer: " + (module.getLayer() == child));
        System.out.println("Correct loader: "
            + (module.getClassLoader() == loader));
        System.out.println(clazz.getMethod("message").invoke(null));
    }
}
```

From the root directory of the example, compile and run:

```bash
javac --module-source-path src -d build/modules -m com.example.greeting
javac -d build/app src/app/Main.java
java -cp build/app app.Main
```

Expected output:

```text
Module: com.example.greeting
Correct layer: true
Correct loader: true
Hello from module com.example.greeting
```

Point-by-point explanation:

- `ModuleFinder.of(Path.of("build/modules"))` locates compiled modules in the directory containing the sub-modules.
- `boot.configuration().resolve(...)` uses the boot layer's configuration as the parent; the required platform modules are resolved according to dependency relationships.
- `boot.defineModulesWithOneLoader(...)` creates the child layer and a new class loader. `ClassLoader.getSystemClassLoader()` here is the **parent loader**, which is not synonymous with the loader returned by `child.findLoader(...)`.
- `clazz.getModule()` returns the module that defined that class. `module.getLayer() == child` and `module.getClassLoader() == loader` confirm the actual mapping.
- The reflective call `getMethod("message").invoke(null)` is valid because the class and method are `public`, and the `com.example.greeting.api` package is `exports`-ed.

In this example, calling `Class.forName("com.example.greeting.api.Greeter")` from `app.Main` using the default loader can fail: the loader running the application on the classpath does not automatically search into the child loader of a `ModuleLayer`. Obtain the loader from the right layer.

## 5. Module and Loader Lookup Rules

```java
ModuleLayer layer = /* created layer */;

Module module = layer.findModule("com.example.greeting")
    .orElseThrow();
ClassLoader loader = layer.findLoader("com.example.greeting");

System.out.println(module.getName());
System.out.println(module.getClassLoader() == loader);
```

`findModule(name)` searches for a module in the layer and can traverse up to parent layers. `findLoader(name)` requires the module name **to be defined directly in the receiving layer**; if the module name is not in that layer, the method throws `IllegalArgumentException`. Therefore, if you need the loader of a module belonging to a parent layer, look it up on the layer that actually defined that module.

Not every module uses an application-created class loader. Platform modules may be loaded by the bootstrap class loader; in that case, `Module.getClassLoader()` or `findLoader(...)` can return `null`. `null` in this context does not mean the module has not been loaded.

A layer can contain multiple modules; a module belongs to exactly one layer at the time it is defined. Two different layers can contain modules **with the same name**, yet they are distinct `Module` objects with separate classes and loaders. Consequently, when managing plugins, keying solely by a single module name is often insufficient: you must consider the layer containing the module.

## 6. Distinguishing Class Loading, Module Readability, and Package Access

Having the right loader only solves **locating and defining the class**. Whether the program is allowed to use the class or its members also depends on JPMS rules:

- `requires` establishes the relationship where one module reads another; `Configuration` resolves that graph.
- `exports p` allows code in other modules to access `public` types in package `p` according to module rules.
- `opens p` enables deep reflective access to package `p`; ordinary `exports` does not grant access to `private` members.
- `uses` and `provides ... with ...` declare service interactions. `ServiceLoader.load(layer, ServiceType.class)` is one way to find providers located in the given layer.

Therefore, `loader.loadClass("a.b.C")` can find the `Class` object, yet operations accessing `C` still fail when the package is not appropriately exported or opened. Successful class loading does not bypass module access control.

## 7. When Should You Create a Separate Layer?

**Plugin systems.** Each group of plugins can be resolved into a `Configuration` and then defined in a child layer. The application retains the layer and calls `findLoader` when it needs to load a plugin's entry point. To receive implementations according to the standard service pattern, prefer `ServiceLoader` rather than hard-coding class names.

**Multiple library versions.** Sets of modules in different layers can share the same names without sharing the same class identities. This is a tool for designing dependency isolation, provided that dependencies and loader delegation are organized properly. Two classes with the same binary name defined by two different loaders are not the same type to the JVM.

**Applications split into feature groups.** You can use `defineModulesWithOneLoader` to group related modules or `defineModulesWithManyLoaders` to separate loaders per module. The choice must reflect requirements for type compatibility, dependency resolution, and resources.

A `ModuleLayer` does not perform hot reload on its own. To replace an already loaded module version, an application typically creates a new configuration/layer/loader and switches references to the new objects. The old layer and class loaders can only be garbage-collected when the application no longer holds references preventing collection.

## 8. Common Errors and How to Diagnose Them

| Symptom | Possible cause | How to address |
| --- | --- | --- |
| `FindException`: module not found | Wrong module path, wrong root module name, or missing module artifact. | Check `ModuleFinder.of(...)`, output directories, and the name in `module-info.java`. |
| `ResolutionException` during `resolve` | Invalid dependency graph or module set. | Check `requires`, participating modules, and the specific resolution message. |
| `LayerInstantiationException` when defining a layer | Invalid module → loader mapping, such as conflicting packages in the same loader. | Check for duplicate packages and the `one/many/custom loader` strategy. |
| `IllegalArgumentException` from `findLoader` | Looking up a module that does not belong to the current layer. | Retrieve the exact layer that defined the module; verify with `module.getLayer()`. |
| `ClassNotFoundException` | Wrong loader or wrong fully qualified class name. | Obtain the loader via `layer.findLoader(moduleName)` and use the fully qualified class name in `package.ClassName` form. |
| `IllegalAccessException` / `InaccessibleObjectException` | `exports`/`opens` rules or member/class visibility do not allow the operation. | Check the public API, module descriptor, and type of reflection being used. |
| `ClassCastException` between two classes with the same name | Two loaders defined two different `Class` objects. | Use a shared API with the same class identity and design clear loader boundaries. |

Do not fix access errors by blindly opening every package or moving every module into the same loader. First determine whether the issue belongs to **resolution**, **loader mapping**, **class identity**, or **module access**.

## 9. Implementation Takeaways

1. `ModuleFinder` locates modules, `Configuration` resolves dependencies, `ModuleLayer` defines modules and attaches loaders, and `ClassLoader` loads classes.
2. To get the loader of a module defined in a layer: `layer.findLoader(moduleName)`. To inspect a loaded class: `clazz.getModule().getClassLoader()`.
3. Choose `defineModulesWithOneLoader` when you want new modules to share a loader; choose `defineModulesWithManyLoaders` when you want each module to have its own loader; use custom mapping only when you control the class loaders.
4. Distinguish **layer parent**, **loader parent**, **readability**, and **exports/opens** because they solve different problems.
5. When debugging, print `clazz.getName()`, `clazz.getModule().getName()`, `clazz.getModule().getLayer()`, and `clazz.getClassLoader()`; this data shows which module/layer/loader actually defined the class.

**APIs for further reference:** `java.lang.ModuleLayer`, `java.lang.ModuleLayer.Controller`, `java.lang.Module`, `java.lang.ClassLoader`, `java.lang.module.Configuration`, `java.lang.module.ModuleFinder`, and `java.util.ServiceLoader` in the documentation for the JDK you are using.
