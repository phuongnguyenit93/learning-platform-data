# Relationship Between One Loader and One or Many Modules

## 1. Overview

In Java 9+ (JPMS), **a ClassLoader does not have a mandatory one-to-one relationship with a Module**. One loader can define classes belonging to **multiple named modules**; however, each runtime class belongs to **one specific module**. This means:

- The same `ClassLoader` **does not mean** two classes reside in the same `Module`.
- Two modules with **different ClassLoaders** can still call each other's public APIs if the module graph/`exports` are valid and the loaders perform the corresponding delegation.
- The **parent ModuleLayer** relationship is not synonymous with the **parent ClassLoader** relationship.
- `ClassLoader.getUnnamedModule()` still exists even when the loader also defines named modules.

A `ModuleLayer` associates runtime `Module` objects with loaders through a module → loader mapping. Java 17 provides `ModuleLayer.defineModulesWithOneLoader` (one loader for multiple modules), `defineModulesWithManyLoaders` (one loader per module), and `defineModules` (custom mapping).

## 2. Concepts to Distinguish

| Concept | Role | Observation API |
|---|---|---|
| Class | Runtime type defined by a loader, belonging to a module | `clazz.getClassLoader()`, `clazz.getModule()` |
| ClassLoader | Loads/defines classes and resources; can be associated with multiple modules | `ClassLoader`, `getUnnamedModule()` |
| Module | A set of packages, a module descriptor, and access permissions | `Module.getName()`, `getClassLoader()`, `getLayer()` |
| ModuleLayer | Runtime modules defined from a configuration together with a loader mapping | `findModule(name)`, `findLoader(name)` |
| Configuration | Resolved modules and `requires` relationships | `Configuration.resolve(...)` |
| ModuleFinder | Finds modules from modular JARs or exploded modules | `ModuleFinder.of(...)` |

A class `example.alpha.Alpha` can have defining loader L and belong to module `demo.alpha`. A class `example.beta.Beta` can **also be defined by L** while belonging to module `demo.beta`. Both still have different module identities and are subject to `requires`, `exports`, and `opens`.

## 3. Two Module–Loader Mapping Approaches

~~~text
ONE LOADER
ModuleLayer ONE
  demo.alpha ────┐
                 ├────> ClassLoader L
  demo.beta  ────┘

Module alpha != Module beta
Defining loader alpha == defining loader beta


MANY LOADERS
ModuleLayer MANY
  demo.alpha ─────────> ClassLoader LA
  demo.beta  ─────────> ClassLoader LB

LA != LB
Beta can read/call Alpha via requires + direct delegation.
~~~

With `defineModulesWithOneLoader(cf,parentLoader)`, Java creates **one new loader** associated with every module in the configuration. With `defineModulesWithManyLoaders(cf,parentLoader)`, Java creates **one new loader for each module**.

The `parentLoader` parameter in these two APIs is **only the parent of the created loader** — not the loader directly responsible for defining the modules. To find the actual loader, call `layer.findLoader(moduleName)`.

## 4. The Boot Layer Also Illustrates the Many-Modules–One-Loader Relationship

`ModuleLayer.boot()` exists when the JVM starts, containing `java.base` and the resolved system modules. The named modules of the boot layer are distributed across the **bootstrap, platform, and system loaders** according to the runtime configuration. Multiple modules can share one loader; the bootstrap loader is represented by `null` in `Class.getClassLoader()` or `Module.getClassLoader()`.

Therefore, the rule “one loader defines only one named module” is not true even in the standard environment.

`ModuleLayer.boot().configuration()` is a common starting point for resolving new modules. The new layer has boot as its parent **layer**, while the new loader has a parent **ClassLoader** depending on the parameter chosen by the caller; these two relationships are not the same.

## 5. What Steps Does Creating a Layer Involve?

~~~text
Modular JARs in the dist/ directory
              |
              v
ModuleFinder.of(dist)
              |
              v
boot.configuration().resolve(...)
              |
              v
Configuration with requires dependencies
              |
              v
boot.defineModulesWithOneLoader(...)
              or
boot.defineModulesWithManyLoaders(...)
              |
              v
New ModuleLayer, new modules, new loaders
              |
              v
layer.findLoader(name).loadClass(binaryName)
~~~

`ModuleFinder` reads module descriptors; `Configuration.resolve` determines the module graph; `ModuleLayer` defines the runtime modules and mapping. A module having been resolved/defined **does not mean** all of its classes have already been loaded: loading can happen on demand.

The layer-creation methods also have static variants for multiple parent layers and `ModuleLayer.Controller`; the example in this article uses the simple instance variant with one parent layer.

## 6. Complete Java 17+ Example: Two Named Modules

Create the structure:

~~~text
module-loader-demo/
├── src/
│   ├── demo.alpha/
│   │   ├── module-info.java
│   │   └── example/alpha/Alpha.java
│   └── demo.beta/
│       ├── module-info.java
│       └── example/beta/Beta.java
└── host-src/
    └── LayerMappingDemo.java
~~~

### 6.1. Module alpha

File **`src/demo.alpha/module-info.java`**:

~~~java
module demo.alpha {
    exports example.alpha;
}
~~~

File **`src/demo.alpha/example/alpha/Alpha.java`**:

~~~java
package example.alpha;

public final class Alpha {
    private Alpha() {
    }

    public static String value() {
        return "ALPHA";
    }
}
~~~

### 6.2. Module beta

File **`src/demo.beta/module-info.java`**:

~~~java
module demo.beta {
    requires demo.alpha;
    exports example.beta;
}
~~~

File **`src/demo.beta/example/beta/Beta.java`**:

~~~java
package example.beta;

import example.alpha.Alpha;

public final class Beta {
    private Beta() {
    }

    public static String call() {
        return "BETA->" + Alpha.value();
    }
}
~~~

The two modules have **non-overlapping packages**, making them suitable for using one loader in the test. `demo.beta` declares `requires demo.alpha`, so module beta reads module alpha. `demo.alpha` exports the package containing public `Alpha` so beta can call it.

### 6.3. Host Creating Two Different Layers

File **`host-src/LayerMappingDemo.java`**:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Set;

public final class LayerMappingDemo {
    private LayerMappingDemo() {
    }

    private static String invokeBeta(Class<?> beta)
            throws ReflectiveOperationException {
        Method method = beta.getMethod("call");
        return (String) method.invoke(null);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: LayerMappingDemo <module-directory>");
        }

        Path dir = Path.of(args[0]).toAbsolutePath().normalize();
        if (!Files.isDirectory(dir)) {
            throw new IllegalArgumentException("Missing module directory");
        }

        ModuleLayer boot = ModuleLayer.boot();
        ModuleFinder finder = ModuleFinder.of(dir);
        Configuration cf = boot.configuration().resolve(
                finder, ModuleFinder.of(), Set.of("demo.beta"));

        ClassLoader parentLoader = ClassLoader.getSystemClassLoader();
        ModuleLayer one =
                boot.defineModulesWithOneLoader(cf, parentLoader);

        ClassLoader oneALoader = one.findLoader("demo.alpha");
        ClassLoader oneBLoader = one.findLoader("demo.beta");
        Class<?> oneA =
                oneALoader.loadClass("example.alpha.Alpha");
        Class<?> oneB =
                oneBLoader.loadClass("example.beta.Beta");

        System.out.println("Boot has java.base: "
                + boot.findModule("java.base").isPresent());
        System.out.println("Host unnamed: "
                + !LayerMappingDemo.class.getModule().isNamed());
        System.out.println("One loader shared: "
                + (oneALoader == oneBLoader));
        System.out.println("One modules distinct: "
                + (oneA.getModule() != oneB.getModule()));
        System.out.println("One Alpha module mapped: "
                + (oneA.getModule()
                == one.findModule("demo.alpha").orElseThrow()));
        System.out.println("One Beta module mapped: "
                + (oneB.getModule()
                == one.findModule("demo.beta").orElseThrow()));
        System.out.println("One Beta calls Alpha: "
                + invokeBeta(oneB));
        System.out.println("One loader has unnamed module: "
                + !oneALoader.getUnnamedModule().isNamed());

        ModuleLayer many =
                boot.defineModulesWithManyLoaders(cf, parentLoader);
        ClassLoader manyALoader = many.findLoader("demo.alpha");
        ClassLoader manyBLoader = many.findLoader("demo.beta");
        Class<?> manyA =
                manyALoader.loadClass("example.alpha.Alpha");
        Class<?> manyB =
                manyBLoader.loadClass("example.beta.Beta");

        System.out.println("Many loaders distinct: "
                + (manyALoader != manyBLoader));
        System.out.println("Many Alpha mapped: "
                + (manyA.getClassLoader() == manyALoader));
        System.out.println("Many Beta mapped: "
                + (manyB.getClassLoader() == manyBLoader));
        System.out.println("Many Beta calls Alpha: "
                + invokeBeta(manyB));
        System.out.println("Alpha Class same across layers: "
                + (oneA == manyA));
        System.out.println("Alpha Module same across layers: "
                + (oneA.getModule() == manyA.getModule()));
        System.out.println("Both Alpha modules named: "
                + (oneA.getModule().isNamed()
                && manyA.getModule().isNamed()));
    }
}
~~~

The host does not import `Alpha`/`Beta` and does not need to place the two modular JARs on the application classpath at startup. `ModuleFinder`, `Configuration`, and `ModuleLayer` themselves manage them.

### 6.4. Compiling, Packaging JARs, and Running

**Bash (Linux/macOS/Git Bash):**

~~~bash
mkdir -p mods host dist

javac -encoding UTF-8 --module-source-path src -d mods \
  src/demo.alpha/module-info.java \
  src/demo.alpha/example/alpha/Alpha.java \
  src/demo.beta/module-info.java \
  src/demo.beta/example/beta/Beta.java

javac -encoding UTF-8 -d host host-src/LayerMappingDemo.java

jar --create --file dist/demo.alpha.jar -C mods/demo.alpha .
jar --create --file dist/demo.beta.jar -C mods/demo.beta .

java -cp host LayerMappingDemo dist
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force mods,host,dist | Out-Null

javac -encoding UTF-8 --module-source-path src -d mods src/demo.alpha/module-info.java src/demo.alpha/example/alpha/Alpha.java src/demo.beta/module-info.java src/demo.beta/example/beta/Beta.java

javac -encoding UTF-8 -d host host-src/LayerMappingDemo.java

jar --create --file dist/demo.alpha.jar -C mods/demo.alpha .
jar --create --file dist/demo.beta.jar -C mods/demo.beta .

java -cp host LayerMappingDemo dist
~~~

Requires JDK **17 or higher** with `javac`, `jar`, and `java` on `PATH`. Each module JAR contains `module-info.class` and the corresponding class. You can verify this with:

~~~bash
jar --describe-module --file dist/demo.alpha.jar
jar --describe-module --file dist/demo.beta.jar
~~~

**Stdout with the correct configuration:**

~~~text
Boot has java.base: true
Host unnamed: true
One loader shared: true
One modules distinct: true
One Alpha module mapped: true
One Beta module mapped: true
One Beta calls Alpha: BETA->ALPHA
One loader has unnamed module: true
Many loaders distinct: true
Many Alpha mapped: true
Many Beta mapped: true
Many Beta calls Alpha: BETA->ALPHA
Alpha Class same across layers: false
Alpha Module same across layers: false
Both Alpha modules named: true
~~~

This result is determined by object comparisons and the `Alpha/Beta` logic, not based on internal loader names or filesystem paths.

## 7. Explaining the One-Loader Layer

~~~java
ModuleLayer one =
        boot.defineModulesWithOneLoader(cf, parentLoader);
~~~

The method creates **one new ClassLoader** for the modules in the configuration. Therefore, `one.findLoader("demo.alpha") == one.findLoader("demo.beta")` is `true`. However, `oneA.getModule() != oneB.getModule()` still holds: sharing a loader does not merge modules.

Java still enforces `requires`, `exports`, and `opens` rules based on module identity. For example, a package-private member in module alpha cannot be accessed by beta merely because they share a loader. Both module access permissions and Java access control must be satisfied.

One loader can host multiple modules; that does not mean the modules are treated like merged JARs on the classpath.

## 8. Explaining the Many-Loaders Layer

~~~java
ModuleLayer many =
        boot.defineModulesWithManyLoaders(cf, parentLoader);
~~~

The method creates **one loader per module**. The loader for `demo.beta` can perform **direct delegation** to the loader of `demo.alpha` according to the module/package mapping. Therefore, `Beta.call()` still calls `Alpha.value()` even though the loaders are different.

The two loaders of modules beta and alpha do not need to have a direct parent–child relationship. Both new loaders have the caller-supplied `parentLoader` as their parent, in addition to the direct delegation mechanism based on the module graph.

**Do not infer that an ordinary ClassLoader automatically understands `requires`.** If you create custom loaders yourself and use `defineModules(cf, mapping)`, you must implement delegation compatible with module readability and resource loading as required.

## 9. Two Layers with the Same Module Name Can Have Different Runtime Identities

For example, creating two layers from the same modular JARs:

~~~text
Layer one:
  Module demo.alpha → oneALoader → Class Alpha#one

Layer many:
  Module demo.alpha → manyALoader → Class Alpha#many
~~~

The two `Class<?>` instances are not equal under `==` because their defining loaders are different. The two `Module` objects are also different because they are defined for two separate layers.

Do not use the `Class.getName()` or `Module.getName()` string alone to determine runtime identity. Compare the class/module/loader objects when debugging.

## 10. The Unnamed Module Still Exists

Every loader has a `getUnnamedModule()`; even a loader used to define named modules still has its own unnamed module.

~~~java
// Illustration once oneALoader is available:
Module unnamed = oneALoader.getUnnamedModule();
System.out.println(unnamed.isNamed()); // false
~~~

A class loaded by the loader into a named module **is not moved to the unnamed module** because the above method exists. `Class.getModule()` of `Alpha` is still `demo.alpha`.

The host running via `java -cp host` belongs to the unnamed module of the **host loader**, which is distinct from the new named modules in the layer. That is why `LayerMappingDemo.class.getModule().isNamed()` returns `false` in the program.

## 11. Limitations When Grouping Multiple Modules into One Loader

`defineModulesWithOneLoader` cannot be used for every configuration. According to Java SE 17, cases that can cause layer creation to fail include:

- **Overlapping packages:** two modules in the configuration declare the same package while both are assigned to one loader.
- **Split delegation:** the shared loader must delegate looking up classes belonging to a package to **more than one** different loader in the module graph.
- General restrictions regarding `java.base` or the `java` and `java.*` packages.

For example, if both `demo.alpha` and `demo.beta` contain `example.shared`, a one-loader layer will not have a unique package owner and may throw `LayerInstantiationException`.

The usual solution is to clearly separate packages or move shared types into a separate API module that both modules `requires`. Do not mechanically apply the classpath's “whichever JAR comes first wins” behavior to JPMS.

## 12. Finding Resources in Named Modules

The Javadoc for loaders created by `ModuleLayer` notes that resource lookup can **differ from a parent-first URLClassLoader**:

- A one-loader layer searches for resources in **the modules of the layer** before the parent loader.
- A many-loaders layer searches for resources in **the module associated with that loader** before the parent loader.
- Resources belonging to a named module are also subject to encapsulation and package `opens` rules; not every file in a JAR is open to every caller.

The `Module.getResourceAsStream(name)` API helps work with resources of a specific module when appropriate access permissions exist. Do not guess the resource precedence order of a module layer solely based on standard classpath/URLClassLoader behavior.

## 13. Readability, exports, opens Differ from Class Loader Visibility

| Relationship | Example | Meaning |
|---|---|---|
| Module readability | `requires demo.alpha` | `demo.beta` reads module alpha |
| Export public API | `exports example.alpha` | Allows access to public types in the package |
| Deep reflection | `opens example.internal` | Allows appropriate reflective access |
| Defining loader | `clazz.getClassLoader()` | Loader that defines the runtime class |
| Runtime module | `clazz.getModule()` | Module containing the runtime class |
| Parent ClassLoader | `loader.getParent()` | Loader fallback/delegation relationship |
| Parent ModuleLayer | `layer.parents()` | Layer configuration relationship |

A loader **being able to find a `Class<?>`** does not guarantee that code from another module has permission to call every member of the class. Modules sharing the same ClassLoader are still subject to `exports`/`opens` and Java access control. Having different loaders does not automatically block access to an exported public API.

## 14. When Using Custom Module Loaders

`ModuleLayer.defineModules(cf, name -> loader)` allows an application to map modules itself. In a plugin system, you must ensure:

1. Each module name is mapped to a valid loader.
2. Modules with overlapping packages are not placed into the same loader.
3. A module with the same name is not redefined in a loader that already has that module.
4. Each loader can locate the bytecode/resources corresponding to the modules it owns.
5. Delegation obeys module readability and does not cause circular waits between loaders.
6. The loader handles concurrent class loading safely; consider a parallel-capable loader.
7. The lifecycle of the loader, resources, tasks/threads, and reloading is coordinated.

`registerAsParallelCapable()` does not automatically make a loader's mutable state thread-safe. If a loader implements its own `findClass`, it must still handle caching and concurrent I/O properly.

## 15. Common Pitfalls

| Symptom | Correct Understanding |
|---|---|
| Two classes have the same loader but belong to different modules | One loader can serve multiple named modules |
| Two-module layer raises a package overlap error | Cannot combine two modules with overlapping packages into the same loader |
| Beta can call Alpha even though the two loaders are different | JPMS direct delegation follows the module graph |
| Calling `findLoader` returns something different from the `parentLoader` parameter | The method creates a **new** loader; the parameter is only the parent |
| Same module name in two layers are not object-equal | Their runtime Module identities are different |
| `IllegalAccessError` even though the class is already loaded | Check `requires`/`exports` and access control |
| Reflection fails | Check `opens` and caller context |
| Host `getModule().getName()` returns null | A classpath host resides in the unnamed module |
| Resource in a module is not found | Check module resource encapsulation and lookup |
| Custom loader cannot find a readable dependency | Mapping and direct delegation are not yet compatible |
| Assuming a parent layer has a single parent loader | Layer and loader are two distinct structures |

## 16. Self-Check Questions

**Question 1.** Can a single ClassLoader define classes belonging to two named modules?

**Answer:** Yes. `defineModulesWithOneLoader` creates one loader for multiple modules, provided the configuration is valid.

**Question 2.** Are two classes with the same ClassLoader guaranteed to have the same `Class.getModule()`?

**Answer:** No. Classes of `demo.alpha` and `demo.beta` belong to two different modules.

**Question 3.** Does `defineModulesWithManyLoaders` use a new loader for each module or take the loader directly from `parentLoader`?

**Answer:** It creates a new loader for each module, with `parentLoader` as their parent.

**Question 4.** Why can beta call alpha even though their loaders are different?

**Answer:** `requires`, `exports`, and direct delegation of the layer-created loaders align properly.

**Question 5.** Does having the same module name in two layers guarantee the same Module object?

**Answer:** No. In the example, each layer creates different Module objects.

**Question 6.** Why do overlapping packages cause a one-loader layer to fail?

**Answer:** A single loader cannot associate two modules that share the same package under that layer creation rule.

**Question 7.** Does `getUnnamedModule()` mean a loader cannot serve named modules?

**Answer:** No. A loader still has its own unnamed module even when it serves named modules.

## 17. Official Documentation

- [Java SE 17 — ModuleLayer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html) — one/many/custom loader mappings and layer creation conditions.
- [Java SE 17 — Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html) — loader, layer, and module identity.
- [Java SE 17 — Class.getModule](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getModule()) — runtime module of a class.
- [Java SE 17 — ModuleFinder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html) — locating modules.
- [Java SE 17 — Configuration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/Configuration.html) — module graph resolution.
- [JVMS 17 — Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html) — class identity and module membership.

**Conclusion:** **One loader can serve one or many modules**; classloader mapping does not erase module boundaries. When designing Java module layers, always consider the module graph, package ownership, exports/opens, loader identity, and direct delegation together.
