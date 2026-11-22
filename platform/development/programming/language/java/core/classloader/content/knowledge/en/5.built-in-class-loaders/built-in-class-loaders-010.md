# Limitations of the Three-Loader Diagram When Working with Named Modules

## 1. The Problem: What Does the Three-ClassLoader Diagram Explain?

In introductory Java tutorials, ClassLoaders are often drawn as a chain:

~~~text
Bootstrap ClassLoader
          ^
          |
Platform ClassLoader
          ^
          |
Application / System ClassLoader
~~~

This diagram is **useful for identifying the three built-in loaders** in Java 9+ and visualizing the common *parent* relationship. However, when a program uses **named modules** (modules with names, part of the Java Platform Module System — JPMS), this diagram is **not sufficient** to explain which class belongs to which module, which module can read which module, which packages are accessible, or which ClassLoader actually defines a class.

Key limitations:

1. **A module is not synonymous with a ClassLoader.** One ClassLoader can define classes for multiple named modules; a named module has a corresponding ClassLoader, but it is not required to have its own dedicated loader.
2. **There are not only three ClassLoaders in the entire JVM.** The three names in the diagram are the **built-in** loaders. Additional `ModuleLayer`s created by an application can use new loaders; an application can also use custom ClassLoaders outside this mechanism.
3. **The module graph differs from the loader parent hierarchy.** `requires`/readability, `exports`, `opens`, and `ModuleLayer` configurations are not described by those three arrows.
4. **Being a named module in the boot layer does not mean all classes are defined by the same loader.** Modules are assigned to built-in loaders depending on their role and runtime configuration; you should not infer the loader of every module solely from the module name.
5. **“Finding a class” and “being allowed to access a class” are two different questions.** Loaders handle lookup and definition; JPMS adds readability and package accessibility rules.

The goal of this article is to know when the three-loader diagram is still useful, when to expand your mental model to **module + layer + loader + access rules**, and how to inspect runtime evidence in Java 17+.

## 2. Reviewing Concepts Before Examining the Limitations

### 2.1. The Three Built-in Loaders Describe Class Definition Mechanics

| Built-in loader | Common role | API observation |
|---|---|---|
| **Bootstrap** | JVM built-in loader; defines fundamental classes, such as `java.lang.String` from `java.base` | `String.class.getClassLoader() == null` typically returns `true`; `null` is how the API represents bootstrap |
| **Platform** | Defines many classes belonging to platform modules; sometimes needs non-strictly-unidirectional delegation to support upgradeable modules | `ClassLoader.getPlatformClassLoader()` |
| **Application/System** | Typically defines classes on the application classpath, application module path, and related JDK tool classes | `ClassLoader.getSystemClassLoader()` |

In a typical Java launch environment, the application loader has the platform loader as its parent or ancestor, and the platform loader relates to bootstrap. However, **parent delegation** is only one dimension explaining class lookup, not a module map.

Specifically, the [Java 21 `ClassLoader` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html) notes that the platform loader may need to delegate to other loaders, including the application loader, in certain cases involving upgradeable modules. Therefore, stating that “every class lookup strictly traverses three tiers from bottom to top and back down” is an oversimplification for JPMS.

### 2.2. Named Module, Unnamed Module, and Automatic Module

- A **Named module** is a module with a name in JPMS, such as `java.base` or `lab.app`. It has a module descriptor, which may be explicitly declared via `module-info.java` or synthesized for an **automatic module** from a JAR on the module path.
- An **Unnamed module** is associated with a ClassLoader and contains classes that the loader defines from the classpath, outside of named modules. Each ClassLoader has its own unnamed module; `Class.getModule().isNamed()` helps determine whether a class belongs to a named or unnamed module.
- An **Automatic module** is still a **named module**. It is not an “anonymous module,” and it should not be understood as a new loader. Automatic modules have their own rules in JPMS for reading and exporting packages.

Two common class-loading paths:

~~~text
Classpath
  -> regular application classes
  -> unnamed module of the defining loader

Module path + module resolution
  -> resolved named modules
  -> each module maps to a ClassLoader in the layer
  -> readability / exports / opens determine access permissions
~~~

`--module-path` does not automatically guarantee that **every** module on the path is resolved. The runtime must build a module configuration from root modules and their dependencies. A modular JAR present on disk that is not resolved does not automatically become a module in the running graph.

### 2.3. Two Types of “Trees” to Keep Separate

**Loader delegation** describes the search/delegation path when loading a class. **Module readability** describes whether one module is allowed to read another module; `exports` and `opens` control which packages are usable.

For example, module A declaring `requires module.b;` expresses a dependency/readability relationship. It **does not mean** A’s loader must be a direct child of B’s loader, nor does it create a new ClassLoader for module B.

## 3. A Better Model: ModuleLayer + Module + ClassLoader

### 3.1. ModuleLayer Maps Modules to Loaders

`ModuleLayer` is the class representing a **layer of modules**. Each layer is created from a `Configuration` (the resolved module graph) and a mapping of each module to a ClassLoader.

A Java 9+ JVM has a **boot layer** (obtained via `ModuleLayer.boot()`). The boot layer contains `java.base` and the modules resolved at JVM startup. Modules in the boot layer are mapped to the bootstrap or other built-in loaders.

Applications can create additional layers. In Java 17+, key APIs include:

| API | Practical meaning |
|---|---|
| `ModuleLayer.boot()` | The layer created when the JVM starts |
| `ModuleLayer.findModule("name")` | Finds a module in the layer or its parent layers; returns `Optional<Module>` |
| `ModuleLayer.findLoader("name")` | Finds the ClassLoader of the corresponding named module in the layer or parent layers |
| `ModuleLayer.defineModulesWithOneLoader(...)` | Creates a layer with **one new loader** for all modules in the configuration |
| `ModuleLayer.defineModulesWithManyLoaders(...)` | Creates a layer with **one new loader per module** |
| `ModuleLayer.defineModules(...)` | Creates a layer with an application-provided module→ClassLoader mapping, for advanced scenarios |
| `Module.getLayer()` | Returns the layer containing a named module; may be `null` for modules not in a layer |
| `Class.getModule()` | Returns the runtime `Module` of the class; applies to both named and unnamed modules |

The `defineModulesWithOneLoader` API itself proves that **multiple named modules can share a single loader**; `defineModulesWithManyLoaders` proves that **there can be many additional loaders beyond the three built-in loaders**.

### 3.2. Illustrating Two Ways to Create a Layer

~~~text
Boot layer
  java.base --> bootstrap loader
  ...       --> built-in loaders (according to runtime mapping)

                    |
                    v
          Additional application-created layer

Approach A: defineModulesWithOneLoader
  plugin.alpha ---------+
                        +--> loader L (new loader)
  plugin.beta ----------+

Approach B: defineModulesWithManyLoaders
  plugin.alpha ------------> loader L1 (new loader)
  plugin.beta -------------> loader L2 (new loader)
~~~

This diagram illustrates the **mapping rules of the two APIs**, not a prediction of the exact configuration of every JDK. `L`, `L1`, and `L2` are placeholder names; Java does not guarantee that loader classes will have fixed names or `toString()` outputs like these.

### 3.3. Layer Parent Is Not Synonymous with ClassLoader Parent

A layer has a **parent layer** in terms of configuration/module lookup semantics. A loader has `getParent()` in terms of delegation semantics. These two relationships can be designed to align, but they are **not the same relationship**.

Specifically, `defineModulesWithOneLoader(cf, parentLoader)` explicitly takes a `parentLoader` to assign to the **newly created** loader, while the parent layer is determined by the layer creation context. Do not infer that “because a module layer is a child, every loader in it must be a child of the loader assigned to a module in the parent layer.”

## 4. Practical Limitations of the Three-Loader Diagram

### Limitation 1 — Cannot Determine Which Module Contains a Class

`Class#getClassLoader()` tells you the defining loader; it **does not by itself answer** which named module the class belongs to.

For example, if `lab.app.Main` and `lab.app.Helper` are both defined by the application loader, that alone is not enough to conclude they belong to the same named module. Conversely, two different modules in the boot layer or a custom layer can be mapped to the same loader.

Inspect **both**:

~~~java
Class<?> type = java.lang.String.class;
Module module = type.getModule();
ClassLoader loader = type.getClassLoader();
System.out.println(module.getName());
System.out.println(module.isNamed());
System.out.println(loader == null);
~~~

The snippet above is an **illustration placed inside a Java method**, not a standalone program. For `String` on common JDKs: the module is `java.base`, the module is named, and the bootstrap loader is represented as `null`.

### Limitation 2 — Does Not Express Readability, Exports, and Opens

The three loaders do not tell you whether a module has permission to use a public API in another module. For example:

~~~java
module lab.service {
    exports lab.service.api;
}
~~~

Another module wanting to use that API must have appropriate readability, such as `requires lab.service;` in its descriptor and a resolved dependency. A non-exported package like `lab.service.internal` does not become an accessible public API just because a loader can locate the class.

Summary:

- `requires` creates module-level readability (with variants such as `transitive`/`static`).
- `exports` permits access to the corresponding public/protected API in the package under JPMS rules; it can also be conditionally exported to specific modules.
- `opens` permits appropriate **deep reflection** on the package; it is not equivalent to granting static compile-time access like `exports`.
- **ClassLoader** handles finding/defining classes; **JPMS** adds access control rules.

An `IllegalAccessError` or `InaccessibleObjectException` related to modules/packages should not be blindly fixed by changing the parent loader. You need to inspect `requires`, `exports`, `opens`, and how the application is launched.

### Limitation 3 — Does Not Show Module Layers Created by Frameworks/Plugins

A JVM can have **multiple layers**; newly created layers are commonly used for plugins, modularized applications, or systems that dynamically manage sets of modules. The three-built-in-loaders diagram has no place for the loaders of these layers.

It is possible to have:

- Modules in the **same layer** sharing one loader.
- Modules in the **same layer** each assigned their own loader.
- Different layers containing modules with the same name under their own configurations, which are distinct runtime module objects; you should not conclude two classes are the same type solely based on module name or binary class name.

At runtime, class identity is tied to **binary name + defining class loader**. Module membership and layer are additional pieces of information to check when debugging, especially when two plugins contain classes with the same name.

### Limitation 4 — No Fixed Mapping of “Module A → Platform, Module B → System”

In the boot layer, platform/JDK/application modules are defined by loaders corresponding to the actual configuration. **There is no reliable rule that all named modules belong to the system loader, or that all modules prefixed with `java.` belong to the bootstrap loader.** Exact loader selection also depends on the platform, JDK version, module resolution, and upgradeable module mechanisms.

Do not assume a loader based on the module name. Instead, query the runtime:

~~~java
Class<?> clazz = java.sql.Driver.class;
System.out.println(clazz.getModule().getName());
System.out.println(clazz.getClassLoader());
~~~

The snippet above is **illustrative code**. The string printed by `getClassLoader()` is an implementation detail; it is not guaranteed to be identical across JDKs or vendors. In addition, the `java.sql` module must be present in the runtime configuration using this class.

### Limitation 5 — Parent-First Is the Default Principle, Not All of JPMS

The default `ClassLoader.loadClass` model typically checks already-loaded classes, delegates to the parent, and then calls `findClass`. However, module-to-loader mapping and special cases in built-in loaders add nuances beyond “just search tier by tier through three boxes.”

For instance, the Java 21 `ClassLoader` documentation explicitly states that **the platform loader may need to delegate to another loader, including the application loader**, when an upgradeable module reads a module defined by loaders outside the usual ancestor chain. Custom loaders can also be designed with non-default strategies.

Therefore, do not use the three-loader diagram to prove the loading order of every class in a modular application.

## 5. Practice A — A Named Module in the Boot Layer

This exercise demonstrates that **named module + boot layer + loader mapping** are three distinct pieces of information that can be observed directly.

Create the structure:

~~~text
project/
  src/
    lab.app/
      module-info.java
      lab/
        app/
          Main.java
~~~

File **`src/lab.app/module-info.java`**:

~~~java
module lab.app {
}
~~~

File **`src/lab.app/lab/app/Main.java`**:

~~~java
package lab.app;

public class Main {
    public static void main(String[] args) {
        Module module = Main.class.getModule();

        System.out.println("module=" + module.getName());
        System.out.println("named=" + module.isNamed());
        System.out.println("bootLayer="
                + (module.getLayer() == ModuleLayer.boot()));
        System.out.println("loaderMatches="
                + (Main.class.getClassLoader()
                == ModuleLayer.boot().findLoader("lab.app")));
        System.out.println("javaBase="
                + String.class.getModule().getName());
    }
}
~~~

From the **`project`** directory, compile and run with JDK 17+:

~~~sh
javac --release 17 -d mods/lab.app src/lab.app/module-info.java src/lab.app/lab/app/Main.java
java --module-path mods --module lab.app/lab.app.Main
~~~

Note: `javac -d` creates the output directory tree as needed; here `mods/lab.app` holds the classes of module `lab.app` in an *exploded module* layout.

**Verified stdout from the program above:**

~~~text
module=lab.app
named=true
bootLayer=true
loaderMatches=true
javaBase=java.base
~~~

**Explanation:**

1. `module=lab.app` comes from **`Main.class.getModule().getName()`**, not the class loader's name.
2. `named=true` shows that `Main` belongs to a named module declared by `module-info.java`.
3. When launched with `--module lab.app/...`, this main module belongs to the **boot layer**.
4. `findLoader("lab.app")` returns the loader mapped to module `lab.app`; comparing it with `Main`'s defining loader evaluates to `true`.
5. `java.base` is also a named module, yet that **does not require** it to use a separate loader just because it has a module name; in this environment `String` is defined by bootstrap.

You do not need to assert a specific printed string for `lab.app`’s loader. The example relies on verifiable **identity comparisons**.

## 6. Practice B — Creating a Loader Outside the Three-Built-in-Loaders Diagram

This second exercise demonstrates that creating a **named module in a child layer** can produce a ClassLoader **different from the system loader**. It also illustrates that a resolved module is not necessarily in the boot layer.

Create the structure:

~~~text
project/
  src/
    plugin.one/
      module-info.java
      plugin/
        one/
          Feature.java
    launcher/
      LayerDemo.java
~~~

File **`src/plugin.one/module-info.java`**:

~~~java
module plugin.one {
    exports plugin.one;
}
~~~

File **`src/plugin.one/plugin/one/Feature.java`**:

~~~java
package plugin.one;

public class Feature {
    public static String label() {
        return "feature";
    }
}
~~~

File **`src/launcher/LayerDemo.java`** (a launcher running from the classpath, i.e., in the unnamed module of its corresponding loader):

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public class LayerDemo {
    public static void main(String[] args) throws Exception {
        ModuleLayer boot = ModuleLayer.boot();

        ModuleFinder finder = ModuleFinder.of(Path.of("build/mods"));
        Configuration cf = boot.configuration().resolve(
                finder, ModuleFinder.of(), Set.of("plugin.one"));

        ModuleLayer child = boot.defineModulesWithOneLoader(
                cf, ClassLoader.getSystemClassLoader());
        ClassLoader loader = child.findLoader("plugin.one");
        Class<?> feature = loader.loadClass("plugin.one.Feature");

        System.out.println("name=" + feature.getModule().getName());
        System.out.println("inChild="
                + (feature.getModule().getLayer() == child));
        System.out.println("loaderMatches="
                + (feature.getClassLoader() == loader));
        System.out.println("differentFromSystem="
                + (loader != ClassLoader.getSystemClassLoader()));
    }
}
~~~

From the **`project`** directory, run the exact commands:

~~~sh
javac --release 17 -d build/mods/plugin.one src/plugin.one/module-info.java src/plugin.one/plugin/one/Feature.java
javac --release 17 -d build/launcher src/launcher/LayerDemo.java
java -cp build/launcher LayerDemo
~~~

**Verified stdout:**

~~~text
name=plugin.one
inChild=true
loaderMatches=true
differentFromSystem=true
~~~

### How the Example Works

1. `ModuleFinder.of(Path.of("build/mods"))` discovers the exploded module `plugin.one` at the build path; the finder **does not load classes by itself**.
2. `boot.configuration().resolve(...)` creates a configuration for the named module `plugin.one` with the boot configuration as its parent; `Set.of("plugin.one")` selects the root module to resolve.
3. `boot.defineModulesWithOneLoader(cf, systemLoader)` creates a **child module layer** along with a **new loader** for the modules resolved in the configuration. The `systemLoader` argument is the **parent** of the new loader, not the loader containing `plugin.one` itself.
4. `child.findLoader("plugin.one")` retrieves the loader assigned to the module. `loader.loadClass("plugin.one.Feature")` locates the class; we do not yet need to instantiate or trigger initialization of `Feature`.
5. `feature.getModule().getLayer() == child` proves the module resides in the new layer; `loader != systemLoader` proves there is a loader **outside the three names in the built-in diagram**.

When using `defineModulesWithManyLoaders(cf, systemLoader)` with a configuration containing **multiple** named modules, the API creates **one new loader per module**. In contrast, `defineModulesWithOneLoader` creates **one loader** shared by the modules in the configuration. You do not need to write a custom ClassLoader subclass to observe this effect.

> **Runnability note:** `LayerDemo` uses the relative path `build/mods`; make sure to run the commands from the `project` directory. If running from another directory, adjust the paths accordingly. This experiment is a standalone Java 17+ example requiring no Maven, Gradle, or IDE.

## 7. Which Information to Use When Diagnosing Issues?

| Practical question | Appropriate observation | Why the three-loader diagram is insufficient |
|---|---|---|
| Which loader defined the class? | `clazz.getClassLoader()` | Identifies the loader, but not the JPMS module |
| Which module does the class belong to, and is it named? | `clazz.getModule()`, `isNamed()`, `getName()` | One loader can be associated with multiple modules |
| Which layer does the module belong to? | `clazz.getModule().getLayer()` | The boot layer is only one of the possible layers |
| Which loader does a module in a layer use? | `layer.findLoader(moduleName)` | Module-to-loader mapping cannot be inferred from `requires` relationships |
| Why can't module A use a public class from B? | Module readability (`requires`), package `exports`, and resolution | Class loading and package access are two separate mechanisms |
| Why is framework reflection blocked? | Check package `opens` and reflective access permissions | Having the class in a loader is not enough for deep reflection |
| Why do two plugins have the same binary name but cannot be cast to each other? | Compare `getName()` **and** `getClassLoader()`, plus module/layer | They may be two classes with different defining loaders |
| Why is a modular JAR present but not loaded? | Module path, root modules, `Configuration`, resolution, and mapping | Having the file on disk does not mean the module was resolved |
| Why is adding `--module-path` not enough? | Check whether the module is resolved from roots/`requires` | The module path provides locations, not automatic graph resolution |

### Common Inspection APIs

~~~java
static void inspect(Class<?> clazz) {
    Module module = clazz.getModule();
    ClassLoader loader = clazz.getClassLoader();

    System.out.println("class=" + clazz.getName());
    System.out.println("module=" + module.getName());
    System.out.println("named=" + module.isNamed());
    System.out.println("layer=" + module.getLayer());
    System.out.println("loader=" + loader);
}
~~~

This is an **illustrative method**, not a standalone Java file. For unnamed modules, `module.getName()` returns `null`; for bootstrap-defined classes, `loader` can be `null`. Do not treat those `null` values as exceptions. Printing `ModuleLayer` or `ClassLoader` may produce JVM/JDK-dependent strings, so do not use those strings as fixed assertions.

### Useful Command-Line Tools

- `java --list-modules`: lists available system modules; **does not** prove all of them are resolved for the running application.
- `java --show-module-resolution --module-path mods --module lab.app/lab.app.Main`: observes the module resolution process at startup (line order and count depend on the JDK; do not rely on fixed stdout).
- `jar --describe-module --file mylib.jar`: displays the module descriptor of a compatible JAR.
- `jdeps --module-path mods --module lab.app`: analyzes dependencies in a modular context; adjust paths according to your actual build structure.

These tools provide evidence about the **module graph**; `Class.getClassLoader()` and `ModuleLayer.findLoader()` provide evidence about **loader mapping**.

## 8. Common Misconceptions and How to Correct Them

1. **“Java has exactly three class loaders.”** False. The three loaders in the diagram are the **built-in loaders**; custom loaders and loaders for module layers can also exist.
2. **“Every named module has its own classloader.”** False. `defineModulesWithOneLoader` allows multiple modules to share a single loader.
3. **“All named modules run on the system loader.”** False. Mapping depends on the layer and configuration; there are bootstrap, platform, application, and other loaders.
4. **“`requires` means module A’s loader is a child of module B’s loader.”** False. That is a **module readability** relationship, not a classloader parent relationship.
5. **“If a loader can find a class, code in another module can naturally use it.”** False. JPMS enforces readability and package accessibility rules.
6. **“`exports` and `opens` are equivalent.”** False. `exports` grants normal access according to JPMS rules; `opens` grants appropriate reflective access, especially deep reflection.
7. **“A modular JAR on the module path is loaded immediately.”** False. The module must be resolved; individual classes are loaded when the JVM needs them. Resolution does not mean every class in the module is initialized.
8. **“Same module name or same class name means the same class object.”** False. Modules can exist in multiple layers; class identity considers the binary name together with the defining loader.
9. **“`getClassLoader() == null` is a bug.”** False for bootstrap-defined classes like `String`.
10. **“Parent-first is always enough to explain class lookup order in a modular application.”** False. Built-in loaders have additional delegation cases; module mapping and custom strategies must be verified at runtime.

## 9. Self-Check

1. Why is the bootstrap → platform → application diagram still useful, yet not a complete map of JPMS?
2. Can a single loader define multiple named modules? Which API in `ModuleLayer` demonstrates this?
3. If you create a child layer with `defineModulesWithManyLoaders` for three modules, how many new loaders are created according to the API contract?
4. How do the `requires` relationship and `ClassLoader.getParent()` differ fundamentally?
5. If a class is found by a loader but the current module cannot access its package, which JPMS rules should you check?
6. Which APIs tell you whether a class belongs to a named/unnamed module and which layer it is in?
7. Is `ClassLoader.getSystemClassLoader()` necessarily the loader for every class on the module path?
8. Why does `loader.loadClass("plugin.one.Feature")` in Practice B not prove that the module belongs to the boot layer?
9. In Practice B, what does `differentFromSystem=true` prove? Is it necessary to write a custom ClassLoader subclass?
10. Why must you check module resolution before concluding that a named module is “present” in an application?
11. If two plugins load two classes named `plugin.api.Service` in different loaders, does having the same class name guarantee they can be cast to each other?
12. Are `Module.getLayer() == null` or `Class.getClassLoader() == null` always errors? Give a valid case for each result.

**Completion criteria:** You can accurately explain the difference between **module graph**, **module layer**, and **loader delegation**; run both experiments yourself, predict the stdout accurately, and combine `Class#getModule`, `ModuleLayer.findLoader`, and `Class#getClassLoader` for practical diagnostics.

## 10. Official References

- [Java SE 21 — `ClassLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): the three built-in loaders, parent delegation, and delegation exceptions in modular applications.
- [Java SE 21 — `ModuleLayer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html): boot layer, module configuration, module→ClassLoader mapping, and single/many-loader APIs.
- [Java SE 21 — `Module`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): module identity, named/unnamed, layer, readability, exports/opens.
- [Java SE 21 — `Configuration`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/Configuration.html): module resolution and dependency relationships.
- [Java SE 21 — `ModuleFinder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleFinder.html): discovering module definitions on paths.

The API links are Java 21 reference sources; both examples compile with Java 17 compatibility and do not depend on the `toString()` output of any loader.