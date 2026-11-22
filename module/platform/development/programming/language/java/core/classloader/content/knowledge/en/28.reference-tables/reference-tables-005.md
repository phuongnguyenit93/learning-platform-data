# Defining loader, initiating loader, runtime package, and layer terminology

## 1. Four terms that must not be conflated

In Java, a class name or package name string is not sufficient to identify an entity at JVM runtime. The terms are explicitly specified in JVMS 17, sections 5.3 and 5.3.6:

| Term | Definition | Characteristics |
|---|---|---|
| **Defining loader** | The loader that actually **defines** a runtime class/interface from the class representation | Determines the class's identity together with the binary name |
| **Initiating loader** | The loader that **initiates** the loading process of a class, directly or through delegation | May differ from the defining loader; used by the JVM in loading constraints |
| **Run-time package** | The pair **(package name, defining loader)** | Not identical to the package name in Java source |
| **Module layer** | A set of runtime modules created from a `Configuration` and a mapping from module name to loader | One loader can serve multiple named modules |

Three conceptual equations:

~~~text
Runtime class identity = (binary name, defining ClassLoader)
Run-time package      = (package name, defining ClassLoader)
Module layer          = (runtime modules, module-to-loader mapping)
~~~

Therefore, two classes both named `demo.plugin.Worker` can have completely different runtime identities; two packages named `demo.plugin` can also be different run-time packages; a ModuleLayer does not necessarily contain only one ClassLoader.

## 2. Defining loader

A loader L that actually creates a runtime class C by loading the appropriate representation and having the JVM define C is called the **defining loader**. Given `Class<?> clazz`, the method `clazz.getClassLoader()` returns the defining loader; a `null` result represents the bootstrap loader when appropriate.

~~~text
PluginLoader L1 defines demo.plugin.Worker v1 → C1
PluginLoader L2 defines demo.plugin.Worker v2 → C2

C1.getName().equals(C2.getName()) == true
C1 == C2                              == false
C1.getClassLoader() != C2.getClassLoader()
~~~

Class identity is not directly determined by the JAR name, URL, or file name. The same binary name with different defining loaders represents two runtime classes; an object of implementation v1 cannot simply be cast to implementation v2. Conversely, two plugins can interact through an interface defined in common by the parent loader.

**Distinction from `ClassLoader.getParent()`:** a loader's parent is only a reference used for certain delegation paths. Defining loader is a role tied to a specific runtime class. A child can define the implementation class while asking the parent to define the public API class.

## 3. Initiating loader and delegation chain

A loader may be requested by the JVM to load a class named N, and then delegate to another loader. The loader initially requested is an **initiating loader** in the JVM concept; the loader that ultimately defines the class is the **defining loader**, and is also an initiating loader.

~~~text
JVM needs demo.api.Api via loader CHILD
             |
             v
CHILD.loadClass("demo.api.Api")
             |
        delegate parent
             |
             v
PARENT defines demo.api.Api
             |
             v
Return defined Class<?> to CHILD

Defining loader: PARENT
Initiating loaders in this model: CHILD, PARENT
~~~

JVMS states clearly: if a request starts at L1 and loader L2 defines the class, both L1 and L2 are initiating loaders. **Loaders that are merely intermediaries in the delegation chain are not automatically recorded as initiating loaders**; therefore, do not infer that every intermediate parent holds that role.

### Why does the JVM need the initiating loader?

It helps the JVM maintain **loading constraints** to check type safety when two classes from two loaders interact through method descriptors and field descriptors. The JVM notations:

- `<N, Ld>`: a type with binary name N, defined by defining loader Ld.
- `N^Li`: type name N considered via initiating loader Li.
- A constraint such as `N^L1 = N^L2` requires the two related name resolutions to represent the same runtime type. A violation can cause `LinkageError`.

**Observation limitation:** Java SE 17 does not have a standard public API `Class.getInitiatingLoaders()`. `Class.getClassLoader()` reports the **defining loader**, not the set of initiating loaders recorded by the VM. Calling `child.loadClass` and receiving the parent's Class object proves **delegation/defining loader**, but not a direct read of VM initiating-loader records.

## 4. A run-time package is the pair of package name and defining loader

According to JVMS, a runtime package is not merely the text `package com.example;` in source. It is identified by:

~~~text
(package name, defining ClassLoader)
~~~

Example:

~~~text
L1 defines demo.same.A → run-time package (demo.same, L1)
L2 defines demo.same.B → run-time package (demo.same, L2)

Same package name?          Yes
Same run-time package?      No
~~~

Package-private access requires a matching runtime package, not just the same FQCN prefix. If bytecode from L2 attempts to access a package-private member of a class defined by L1, the JVM may throw `IllegalAccessError`, even if both source files write `package demo.same;`.

Practical check:

~~~java
// Illustrative code, once Class<?> a, b are available.
boolean sameRuntimePackage =
        a.getPackageName().equals(b.getPackageName())
        && a.getClassLoader() == b.getClassLoader();
~~~

`Class.getPackageName()` returns only the **name**, while `Class.getPackage()` returns `Package` metadata, not the JVMS run-time package identifier. To verify package-private access, one must consider **both the package name and the defining loader**, along with the relevant module/access control rules.

**Relationship with JPMS:** A run-time package belongs to exactly one runtime module. When multiple named modules share a ClassLoader, the JVM does not allow a run-time package to be "split" across multiple modules; therefore, mapping two modules with the same package to one loader can cause `LayerInstantiationException`. However, the same package name in two different loaders can still exist because they are two different run-time packages.

## 5. Java 17+ example 1: two JARs, one binary name

An example comparing two classes both named `demo.plugin.Worker` defined by two different `URLClassLoader` instances, both using a shared API defined by the parent.

### 5.1. Structure

~~~text
loader-glossary/
├── api-src/demo/api/Api.java
├── v1-src/demo/plugin/Worker.java
├── v2-src/demo/plugin/Worker.java
└── host-src/LoaderGlossaryDemo.java
~~~

**api-src/demo/api/Api.java**:

~~~java
package demo.api;

public interface Api {
    String message();
}
~~~

**v1-src/demo/plugin/Worker.java**:

~~~java
package demo.plugin;

import demo.api.Api;

public final class Worker implements Api {
    public Worker() {
    }

    @Override
    public String message() {
        return "v1";
    }
}
~~~

**v2-src/demo/plugin/Worker.java**:

~~~java
package demo.plugin;

import demo.api.Api;

public final class Worker implements Api {
    public Worker() {
    }

    @Override
    public String message() {
        return "v2";
    }
}
~~~

**host-src/LoaderGlossaryDemo.java**:

~~~java
import demo.api.Api;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class LoaderGlossaryDemo {
    private LoaderGlossaryDemo() {
    }

    private static boolean sameRuntimePackage(
            Class<?> left, Class<?> right) {
        return left.getPackageName().equals(right.getPackageName())
                && left.getClassLoader() == right.getClassLoader();
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: LoaderGlossaryDemo <v1.jar> <v2.jar>");
        }

        ClassLoader parent = Api.class.getClassLoader();

        URL url1 = Path.of(args[0]).toUri().toURL();
        URL url2 = Path.of(args[1]).toUri().toURL();

        try (URLClassLoader l1 =
                     new URLClassLoader(new URL[]{url1}, parent);
             URLClassLoader l2 =
                     new URLClassLoader(new URL[]{url2}, parent)) {

            Class<?> c1 = l1.loadClass("demo.plugin.Worker");
            Class<?> c2 = l2.loadClass("demo.plugin.Worker");

            Api p1 = (Api) c1.getConstructor().newInstance();
            Api p2 = (Api) c2.getConstructor().newInstance();

            Class<?> delegatedApi = l1.loadClass("demo.api.Api");

            System.out.println("Same binary name: "
                    + c1.getName().equals(c2.getName()));
            System.out.println("Same Class object: " + (c1 == c2));
            System.out.println("Different defining loaders: "
                    + (c1.getClassLoader() != c2.getClassLoader()));
            System.out.println("Same package name: "
                    + c1.getPackageName().equals(c2.getPackageName()));
            System.out.println("Same runtime package: "
                    + sameRuntimePackage(c1, c2));
            System.out.println("API delegated to parent: "
                    + (delegatedApi == Api.class));
            System.out.println("API defining loader is parent: "
                    + (delegatedApi.getClassLoader() == parent));
            System.out.println("Shared API cast works: "
                    + (p1 instanceof Api && p2 instanceof Api));
            System.out.println("Plugin values: "
                    + p1.message() + "," + p2.message());
            System.out.println("Distinct unnamed modules: "
                    + (c1.getModule() != c2.getModule()));
            System.out.println("Unnamed modules have no layer: "
                    + (c1.getModule().getLayer() == null
                    && c2.getModule().getLayer() == null));
        }
    }
}
~~~

**Why must the two plugin JARs not be placed on the host classpath?** Because `URLClassLoader` is parent-first by default. If the parent already has `demo.plugin.Worker`, both child loaders may receive the parent's version instead of defining two runtime classes themselves. The two JARs contain only the implementation; do **not** package `Api.class` inside them.

### 5.2. Bash: build and run

From the `loader-glossary` directory with JDK 17+:

~~~bash
mkdir -p build/api build/host build/v1 build/v2 dist

javac -encoding UTF-8 -d build/api api-src/demo/api/Api.java

javac -encoding UTF-8 -cp build/api \
  -d build/v1 v1-src/demo/plugin/Worker.java

javac -encoding UTF-8 -cp build/api \
  -d build/v2 v2-src/demo/plugin/Worker.java

javac -encoding UTF-8 -cp build/api \
  -d build/host host-src/LoaderGlossaryDemo.java

jar --create --file dist/v1.jar -C build/v1 .
jar --create --file dist/v2.jar -C build/v2 .

java -cp "build/api:build/host" \
  LoaderGlossaryDemo dist/v1.jar dist/v2.jar
~~~

### 5.3. Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force build/api,build/host,build/v1,build/v2,dist | Out-Null

javac -encoding UTF-8 -d build/api api-src/demo/api/Api.java

javac -encoding UTF-8 -cp build/api -d build/v1 v1-src/demo/plugin/Worker.java
javac -encoding UTF-8 -cp build/api -d build/v2 v2-src/demo/plugin/Worker.java
javac -encoding UTF-8 -cp build/api -d build/host host-src/LoaderGlossaryDemo.java

jar --create --file dist/v1.jar -C build/v1 .
jar --create --file dist/v2.jar -C build/v2 .

java -cp "build/api;build/host" LoaderGlossaryDemo dist/v1.jar dist/v2.jar
~~~

### 5.4. Exact stdout

~~~text
Same binary name: true
Same Class object: false
Different defining loaders: true
Same package name: true
Same runtime package: false
API delegated to parent: true
API defining loader is parent: true
Shared API cast works: true
Plugin values: v1,v2
Distinct unnamed modules: true
Unnamed modules have no layer: true
~~~

These lines verify **the same binary name but different runtime classes**, **the same package name but different run-time packages**, **the parent defining the shared API**, and **each plugin loader having its own unnamed module**.

It only observes defining-loader/delegation via public APIs; it does not itself read initiating-loader records inside the JVM.

## 6. ModuleLayer and Module are not ClassLoaders

Java 9+ has JPMS, in which a `ModuleLayer` is a group of runtime named modules created from a `Configuration` and a **module name → ClassLoader** mapping.

~~~text
LAYER ONE                            LAYER MANY

demo.alpha ──┐                       demo.alpha → Loader LA
             ├── Loader L
demo.beta ───┘                       demo.beta  → Loader LB
~~~

Representative APIs:

| API | Meaning |
|---|---|
| `ModuleLayer.boot()` | Boot layer of the JVM |
| `layer.findModule("demo.alpha")` | The corresponding Module object |
| `layer.findLoader("demo.alpha")` | The loader associated with the module |
| `module.getClassLoader()` | The loader of the runtime module |
| `module.getLayer()` | The layer of the named module |
| `layer.parents()` | Parent ModuleLayers |
| `layer.defineModulesWithOneLoader(cf, parentLoader)` | One **new** loader for multiple modules |
| `layer.defineModulesWithManyLoaders(cf, parentLoader)` | One **new** loader per module |
| `layer.defineModules(cf, mapper)` | Framework-provided mapping |

**Important:** `parentLoader` in the convenience APIs refers to the **parent of the new loader**, not the loader that directly defines the modules. `layer.parents()` is not equivalent to `loader.getParent()`: these are two different relationships.

Modules sharing a loader still have their own `requires`, `exports`, and `opens` boundaries. One loader can be associated with multiple named modules and still have its own `ClassLoader.getUnnamedModule()`. A class belongs to exactly one runtime module through its corresponding runtime package.

## 7. Java 17+ example 2: named modules and layers

Create two named modules: `demo.alpha` exports a public API; `demo.beta` has `requires demo.alpha` and calls alpha. The host creates two layers: one layer using a shared loader, and one layer using separate loaders.

### 7.1. Structure

~~~text
module-layer-glossary/
├── src/demo.alpha/module-info.java
├── src/demo.alpha/demo/alpha/Alpha.java
├── src/demo.beta/module-info.java
├── src/demo.beta/demo/beta/Beta.java
└── host-src/ModuleLayerGlossary.java
~~~

**src/demo.alpha/module-info.java**:

~~~java
module demo.alpha {
    exports demo.alpha;
}
~~~

**src/demo.alpha/demo/alpha/Alpha.java**:

~~~java
package demo.alpha;

public final class Alpha {
    private Alpha() {
    }

    public static String value() {
        return "ALPHA";
    }
}
~~~

**src/demo.beta/module-info.java**:

~~~java
module demo.beta {
    requires demo.alpha;
    exports demo.beta;
}
~~~

**src/demo.beta/demo/beta/Beta.java**:

~~~java
package demo.beta;

import demo.alpha.Alpha;

public final class Beta {
    private Beta() {
    }

    public static String call() {
        return Alpha.value() + ":BETA";
    }
}
~~~

**host-src/ModuleLayerGlossary.java**:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public final class ModuleLayerGlossary {
    private ModuleLayerGlossary() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: ModuleLayerGlossary <jar-dir>");
        }

        ModuleLayer boot = ModuleLayer.boot();
        ModuleFinder finder = ModuleFinder.of(Path.of(args[0]));
        Configuration cf = boot.configuration().resolve(
                finder, ModuleFinder.of(), Set.of("demo.beta"));

        ClassLoader parent = ClassLoader.getSystemClassLoader();

        ModuleLayer one =
                boot.defineModulesWithOneLoader(cf, parent);
        ClassLoader oneAlpha = one.findLoader("demo.alpha");
        ClassLoader oneBeta = one.findLoader("demo.beta");
        Class<?> alphaOne = oneAlpha.loadClass("demo.alpha.Alpha");
        Class<?> betaOne = oneBeta.loadClass("demo.beta.Beta");

        ModuleLayer many =
                boot.defineModulesWithManyLoaders(cf, parent);
        ClassLoader manyAlpha = many.findLoader("demo.alpha");
        ClassLoader manyBeta = many.findLoader("demo.beta");
        Class<?> alphaMany =
                manyAlpha.loadClass("demo.alpha.Alpha");
        Class<?> betaMany =
                manyBeta.loadClass("demo.beta.Beta");

        System.out.println("One loader shared: "
                + (oneAlpha == oneBeta));
        System.out.println("One modules distinct: "
                + (alphaOne.getModule() != betaOne.getModule()));
        System.out.println("Alpha module named: "
                + alphaOne.getModule().isNamed());
        System.out.println("Alpha belongs to one layer: "
                + (alphaOne.getModule().getLayer() == one));
        System.out.println("Boot parent layer: "
                + one.parents().contains(boot));
        System.out.println("Many loaders distinct: "
                + (manyAlpha != manyBeta));
        System.out.println("Many class loaders mapped: "
                + (alphaMany.getClassLoader() == manyAlpha
                && betaMany.getClassLoader() == manyBeta));

        String result = (String) betaMany.getMethod("call")
                .invoke(null);
        System.out.println("Beta calls alpha: " + result);

        System.out.println("Alpha Class same across layers: "
                + (alphaOne == alphaMany));
        System.out.println("Alpha Module same across layers: "
                + (alphaOne.getModule() == alphaMany.getModule()));
    }
}
~~~

### 7.2. Bash

Run from the `module-layer-glossary` directory:

~~~bash
mkdir -p mods host dist

javac -encoding UTF-8 --module-source-path src -d mods \
  src/demo.alpha/module-info.java \
  src/demo.alpha/demo/alpha/Alpha.java \
  src/demo.beta/module-info.java \
  src/demo.beta/demo/beta/Beta.java

javac -encoding UTF-8 -d host host-src/ModuleLayerGlossary.java

jar --create --file dist/demo.alpha.jar -C mods/demo.alpha .
jar --create --file dist/demo.beta.jar -C mods/demo.beta .

java -cp host ModuleLayerGlossary dist
~~~

### 7.3. Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force mods,host,dist | Out-Null

javac -encoding UTF-8 --module-source-path src -d mods src/demo.alpha/module-info.java src/demo.alpha/demo/alpha/Alpha.java src/demo.beta/module-info.java src/demo.beta/demo/beta/Beta.java

javac -encoding UTF-8 -d host host-src/ModuleLayerGlossary.java

jar --create --file dist/demo.alpha.jar -C mods/demo.alpha .
jar --create --file dist/demo.beta.jar -C mods/demo.beta .

java -cp host ModuleLayerGlossary dist
~~~

The host does not place modular JARs on `-cp`, but uses `ModuleFinder.of(dist)` to resolve and create a new layer.

### 7.4. Stdout

~~~text
One loader shared: true
One modules distinct: true
Alpha module named: true
Alpha belongs to one layer: true
Boot parent layer: true
Many loaders distinct: true
Many class loaders mapped: true
Beta calls alpha: ALPHA:BETA
Alpha Class same across layers: false
Alpha Module same across layers: false
~~~

Reading the results:

- Layer `one` places both named modules into **one loader**, yet the modules are still two different runtime objects.
- Layer `many` places each module into a new loader; beta still calls alpha thanks to `requires`/exports and the direct delegation supported by the layer's loader.
- The two layers are created independently; the alpha class and the alpha runtime module in each layer have different identities.
- Layer creation does not automatically mean the JVM eager-loads all classes; `loadClass` is what requests a specific type.

## 8. Package, module, and layer levels in JPMS

The relationship should be read as follows:

~~~text
Runtime class
  |
  | binary name + defining loader
  v
Run-time package
  |
  | package name + defining loader
  v
Runtime Module (named/unnamed)
  |
  v
ModuleLayer (for named modules of the layer)
~~~

A run-time package belongs to **one runtime module**. A runtime module is associated with exactly one loader, whereas one loader can serve multiple runtime modules. A loader can also be associated with modules from multiple layers in a valid custom mapping.

If two modules with overlapping packages are grouped into the same loader, `defineModulesWithOneLoader` may throw `LayerInstantiationException`. Split delegation (a loader having to look up the same package in more than one target loader) is also a limitation. These constraints do not mean every JVM forbids two different loaders from defining the same package name.

It is necessary to distinguish:

- **Package-private**: relates to the run-time package.
- **Module readability/exports/opens**: controls access across a named-module boundary.
- **Loader visibility**: whether a loader can find bytecode or a class via delegation.
- **Authorization** of the end user: application policy; finding a class/resource does not mean the user is permitted to use it.

## 9. Error diagnosis table

| Error or symptom | Possible issue |
|---|---|
| `ClassCastException` between two identical class names | Two different defining loaders created two runtime types |
| `IllegalAccessError` when calling a package-private member | Two classes are not in the same run-time package despite matching package names |
| `LinkageError` related to a loader constraint | Inconsistent initiating-loader type resolutions |
| `NoClassDefFoundError` in a plugin | The resolving loader cannot see the proper dependency |
| `LayerInstantiationException` | Overlapping packages/split delegation/module mapping |
| `InaccessibleObjectException` | Missing module `opens` for reflection |
| `IllegalAccessError` with a named module's public API | Improper `requires` or `exports` |
| `Class.getClassLoader() == null` | The class was defined by the bootstrap loader |
| Two Module objects with the same name but not `==` | Two runtime modules (possibly belonging to different layers) |

Do not fix by catching `LinkageError` and continuing unconditionally. Inspect the classloader topology, runtime API identity, module graph, and packaging.

## 10. Misconceptions to eliminate

| Misconception | Correct explanation |
|---|---|
| A loader that calls `loadClass` always defines the class | It may delegate to its parent |
| `Class.getClassLoader()` returns the initiating loader | It returns the defining loader |
| Every intermediate loader is an initiating loader | The JVMS does not automatically count all intermediaries |
| Same binary name means same runtime type | The defining loader is also required |
| Same package name means same run-time package | The defining loader is also required |
| One loader serves only one module | One loader can have multiple named modules |
| A ModuleLayer is itself a ClassLoader | A layer contains modules, mapped to one/multiple loaders |
| Parent layer equals parent ClassLoader | Two different relationships |
| Creating a layer loads every class in it | Module definition and class loading are different |
| A named module causes a loader to lose its unnamed module | The loader still has its own unnamed module |
| TCCL determines a class's identity | The defining loader determines runtime class identity |

## 11. Self-check questions

**1.** The child requests Api, and the parent defines it. Which is the defining loader?

**Answer:** The parent. The child can be an initiating loader in the loading process via delegation.

**2.** Do two `demo.plugin.Worker` Classes with the same name and different defining loaders have the same type?

**Answer:** No. Class identity is binary name + defining loader.

**3.** Two Classes have `package demo.same;` but are defined by two loaders; are they in the same run-time package?

**Answer:** No. Both the package name and the defining loader must match.

**4.** Does `getClassLoader()` report all initiating loaders of a class?

**Answer:** No. It returns the defining loader, whereas initiating records belong to JVM semantics.

**5.** Can one layer have two modules using a single loader?

**Answer:** Yes, if the mapping is valid, for example `defineModulesWithOneLoader`.

**6.** Can two modules with different loaders still communicate?

**Answer:** Yes, if readability/exports are valid and loader delegation is properly arranged.

**7.** Are two Module objects with the same name in two layers necessarily equal?

**Answer:** No. Compare runtime identity by object reference.

**8.** Why can package-private access fail even when the source package is the same?

**Answer:** Because different defining loaders create different run-time packages.

## 12. Official documentation

- [JVMS 17 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3): defining and initiating loaders, runtime identities.
- [JVMS 17 — User-defined Loader](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3.2): initiating loader rules.
- [JVMS 17 — Loading Constraints](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3.4): type safety across loaders.
- [JVMS 17 — Modules and Layers](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3.6): runtime module/package/layer.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): delegation and unnamed module.
- [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): defining loader/package/module introspection.
- [Java SE 17 — ModuleLayer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html): module-to-loader mapping.
- [Java SE 17 — Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): runtime module identity.

**Summary:** The defining loader creates the runtime class; the initiating loader initiates loading and may differ from the defining loader. A run-time package consists of the package name **and** the defining loader. A ModuleLayer groups runtime modules with a loader mapping; it is not a ClassLoader and does not require one module per loader.
