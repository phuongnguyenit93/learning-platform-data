# Split Package Restrictions and ModuleLayer Configuration Errors in Java

## 1. What Is a Split Package, and Why Does It Cause Problems in JPMS?

A **split package** occurs when classes belonging to the **same package name** are distributed across two or more different modules or artifacts. For example, two modules both contain `com.example.shared`:

~~~text
module alpha                       module beta
├── module-info.class              ├── module-info.class
└── com/example/shared/            └── com/example/shared/
    └── Alpha.class                    └── Beta.class

Same package name: com.example.shared
Different module names: alpha and beta
~~~

On the traditional Java classpath, classes with the same package across multiple JARs can be found in order by a class loader. This easily hides conflicts and depends on configuration. The **Java Platform Module System (JPMS, Java 9+)** requires explicit module configuration, so it enforces stricter checks regarding packages, readability, exports, and **loader mapping**.

Split packages should not be understood through a simple rule like "two named modules both having package p is always forbidden". The key rules **depend on the phase and how they are used**:

1. **During module resolution:** a module **must not read two different modules that both export the same package to it**. A module itself that contains package p can also conflict with package p exported to it by a module it reads.
2. **During layer creation:** two modules with overlapping packages **cannot both be defined in the same class loader**. `ModuleLayer.defineModulesWithOneLoader` rejects overlapping packages even in some configurations where resolution succeeded.
3. **When using multiple loaders:** `defineModulesWithManyLoaders` gives each module its own loader, so they can contain the same package name if the module configuration is already valid and there are no other readability/exports conflicts.
4. **When running on the classpath:** classes belong to the unnamed module of their respective loader; multiple JARs having the same package does not automatically equate to the same kind of JPMS layer configuration error.

This article helps distinguish **graph resolution errors**, **layer definition errors**, **visibility errors during class access**, and **type identity errors**, along with a compilable/runnable Java 17+ experiment.

## 2. Four Concepts You Must Distinguish

### 2.1. Module Path Is Not the Module Graph

`--module-path` only tells JPMS the locations from which to observe modules. A JAR residing on the module path is **not necessarily resolved** into the running configuration. Java starts from the **root modules**, follows `requires` relationships, and then computes readability.

Placing two JARs containing the same package on the module path is not enough to conclude that runtime must fail: you need to determine **whether they are selected into the graph, who they export to, and how they are mapped to loaders**.

### 2.2. Configuration Is the Result of Dependency Resolution

`java.lang.module.Configuration` represents a set of **resolved modules** and the corresponding readability graph. For example, `ModuleLayer.boot().configuration()` is the configuration of the boot layer. The `Configuration.resolve` and `resolveAndBind` APIs can create a new configuration based on module finders, parent configurations, and a set of root names.

Resolution can throw `FindException` if a module cannot be found, or `ResolutionException` if a valid graph cannot be built due to dependency/package-export constraints.

### 2.3. ModuleLayer Represents Runtime Modules Bound to ClassLoaders

`ModuleLayer` holds the runtime `Module` objects for a configuration and a mapping from **module name to ClassLoader**. A layer has parent layer(s), and class loading must respect module membership/delegation.

Two important factory methods:

- `defineModulesWithOneLoader(cf, parentLoader)`: creates **one new loader** used for all modules in the configuration. It can fail if the modules contain overlapping packages.
- `defineModulesWithManyLoaders(cf, parentLoader)`: creates **a separate loader for each module**. It does not have the same prohibition on overlapping packages *solely due to sharing a loader*.
- `defineModules(cf, classLoaderFunction)`: advanced mapping that allows controlling the loader; it enforces strict checks on package conflicts and ownership.

Both the `WithOneLoader` and `WithManyLoaders` methods return a **new layer**; they do not modify the contents of the boot layer or turn an existing class loader into a different loader.

### 2.4. Runtime Package and Class Identity

A runtime package involves the **package name and defining loader**. For named modules, a class also belongs to a runtime module (`Class.getModule()`). Two classes with the same textual package name but belonging to different loaders **are not automatically in the same runtime package** for package-private access.

Two classes with the **same binary name** defined by two different loaders can also be **two different runtime types**; they cannot be cast to one another merely because their names/bytes match.

## 3. Constraints at Module Resolution Time

One principle of the Java 17 specification is: **resolution fails if two or more modules export the same package to a module that reads both of them**.

Suppose:

~~~text
module consumer
    requires alpha
    requires beta

module alpha exports com.example.api
module beta  exports com.example.api
~~~

If consumer reads both alpha and beta and both export `com.example.api` to consumer, Java cannot choose a single meaning for the public types of that package. Module resolution will reject the configuration, typically as a `ResolutionException` or a corresponding module resolution error in the launcher.

Two modules do not need to have the same **class name** to run into this problem: having the same **package name** is enough for a readability/export conflict.

### 3.1. Case of Conflict with consumer's Own Package

It is also invalid when module `consumer` contains package `com.example.api` **and** reads another module that exports that same package to consumer under the resolution rules. This is a package conflict in the readability graph, not an error caused by the Java compiler failing to find a class file.

### 3.2. Exports Can Be Qualified

`exports com.example.api to consumer;` only exports to the specified consumer module. Therefore, you must examine the **actual export target**, not merely whether the descriptor contains the `exports` keyword.

A module `other` that does not read or is not exported that package will not necessarily see the same conflict as consumer. A module graph analysis tool needs to consider both qualified exports and `requires transitive`, rather than simply counting duplicate package names across all files on disk.

### 3.3. Automatic Modules Have Additional Effects

A JAR without `module-info.class` can become an **automatic module** on the module path. The packages of an automatic module are broadly exported, and the module has special readability rules. When the resolver brings an automatic module into the graph, observable automatic modules may all be enumerated together according to JPMS rules, causing split packages from legacy libraries to turn into seemingly unexpected conflicts.

During migration, check the automatic module names (which can be derived from the JAR file name or from `Automatic-Module-Name`) and package exports, rather than just adjusting the `requires` list by guesswork.

## 4. Constraints at ModuleLayer Creation Time

Valid resolution still does not prove that a layer can be created using **every way of mapping class loaders**.

### 4.1. defineModulesWithOneLoader

~~~java
ModuleLayer layer = ModuleLayer.boot()
        .defineModulesWithOneLoader(configuration, parentLoader);
~~~

This is an **illustrative snippet**, assuming `configuration` is a valid Configuration and `parentLoader` is an appropriate ClassLoader.

This method creates a new loader for all modules in the configuration. According to the Java 17 Javadoc, layer construction can fail when:

- **Overlapping packages:** two or more modules in the configuration have the same package.
- **Split delegation:** the created loader needs to delegate to **more than one other loader** to load the classes of a particular package.
- Module `java.base` must not be recreated in the new configuration.
- A module containing package `java` or a package starting with `java.` must not be defined in this way.

Applicable cases can throw `LayerInstantiationException`. Note that a **configuration that is valid at resolution** can still have overlapping packages that are not exported to the same consumer; with the one-loader strategy, that is still enough to cause layer creation to be rejected.

### 4.2. defineModulesWithManyLoaders

~~~java
ModuleLayer layer = ModuleLayer.boot()
        .defineModulesWithManyLoaders(configuration, parentLoader);
~~~

In this approach, Java creates one loader per module. If alpha and beta both contain package `com.example.internal` but they are in two different loaders, this model **can** be valid as long as the configuration has passed resolution and does not violate other constraints.

Do not infer that `ManyLoaders` is a tool to "bypass all module conflicts": it **does not fix a Configuration that has readability/exports conflicts**. Only after `Configuration.resolve` succeeds does execution reach the layer definition step.

### 4.3. defineModules: Manual Mapping

With `ModuleLayer.defineModules`, the caller provides a function that determines the loader for each module. The Javadoc lists important error cases:

- Two modules with the same package are mapped to the **same ClassLoader**.
- A module is mapped to a loader that has already defined a module with the **same name**.
- A module is mapped to a loader that has already defined classes belonging to one of the new module's packages.
- Package names `java.*` are prohibited in the new module configuration.
- The ClassLoader function may return an inappropriate loader, and Java throws the corresponding error.

This is an advanced area; the mapping must be consistent with **readability**, direct delegation, and lifecycle. Do not "turn off split package checks" by arbitrarily returning an existing loader.

## 5. Runnable Java 17 Experiment: Split Package Valid with Many Loaders, Failing with One Loader

This experiment demonstrates the exact difference between **resolution** and **layer construction**. We compile **two named modules** without `exports`, each containing package `clash` but with different class names.

### 5.1. Create the Project Structure

~~~text
layer-split-demo/
├── src/
│   ├── alpha/
│   │   ├── module-info.java
│   │   └── clash/
│   │       └── Alpha.java
│   └── beta/
│       ├── module-info.java
│       └── clash/
│           └── Beta.java
└── LayerDemo.java
~~~

**There is no `requires alpha` or `requires beta`** and `clash` is not exported. Therefore, the mere fact that both modules have that package **does not cause an export-readability error during resolution**.

### 5.2. Module alpha

File **src/alpha/module-info.java**:

~~~java
module alpha {
}
~~~

File **src/alpha/clash/Alpha.java**:

~~~java
package clash;

public final class Alpha {
}
~~~

### 5.3. Module beta

File **src/beta/module-info.java**:

~~~java
module beta {
}
~~~

File **src/beta/clash/Beta.java**:

~~~java
package clash;

public final class Beta {
}
~~~

The class names Alpha and Beta are different; we are testing **package overlap**, not duplicate binary class names.

### 5.4. Host Program LayerDemo.java

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public class LayerDemo {
    public static void main(String[] args) throws Exception {
        ModuleLayer boot = ModuleLayer.boot();
        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));

        Configuration cf = boot.configuration().resolve(
                finder, ModuleFinder.of(), Set.of("alpha", "beta"));

        System.out.println("alpha resolved: "
                + cf.findModule("alpha").isPresent());
        System.out.println("beta resolved: "
                + cf.findModule("beta").isPresent());

        ClassLoader parent = ClassLoader.getSystemClassLoader();
        try {
            boot.defineModulesWithOneLoader(cf, parent);
            System.out.println("one loader: success");
        } catch (LayerInstantiationException expected) {
            System.out.println(
                    "one loader: LayerInstantiationException");
        }

        ModuleLayer layer =
                boot.defineModulesWithManyLoaders(cf, parent);

        Class<?> alpha = layer.findLoader("alpha")
                .loadClass("clash.Alpha");
        Class<?> beta = layer.findLoader("beta")
                .loadClass("clash.Beta");

        System.out.println("separate loaders: "
                + (alpha.getClassLoader() != beta.getClassLoader()));
        System.out.println("alpha module: "
                + alpha.getModule().getName());
        System.out.println("beta module: "
                + beta.getModule().getName());
    }
}
~~~

Technical points:

- `ModuleFinder.of(Path.of("mods"))` reads the exploded modules compiled under `mods`.
- `resolve` uses the boot layer's configuration as the parent and a root set consisting of `alpha` and `beta`.
- Since neither module exports the overlapping package to the same consumer, **resolution succeeds**.
- When `defineModulesWithOneLoader` tries to map both alpha/beta into one loader, JPMS detects the **overlapping package `clash`** and throws `LayerInstantiationException`. The program catches the error by **type**, without depending on the message text.
- `defineModulesWithManyLoaders` uses a separate loader for each module, so the layer can be created in this setup.
- Calling `loadClass` directly on each module's loader returns the Class objects without requiring classes from package `clash` to be exported to the host unnamed module; the example only reads metadata and **does not call public methods of the classes via cross-module Java source**.
- `Class.getModule().getName()` shows that the two classes belong to the right named modules.

### 5.5. Compile and Run Commands

Run from the `layer-split-demo` directory with JDK 17 or later. **Compile each module separately** to avoid imposing additional compiler checks when compiling modules containing overlapping packages at the same time:

~~~bash
javac --release 17 --module-source-path src -d mods -m alpha
javac --release 17 --module-source-path src -d mods -m beta
javac --release 17 -d host LayerDemo.java
java -cp host LayerDemo
~~~

These commands work on Windows PowerShell, Linux, or macOS once the files/directories are created according to the tree above; there are no path list separators that need to be changed.

**Exact expected stdout:**

~~~text
alpha resolved: true
beta resolved: true
one loader: LayerInstantiationException
separate loaders: true
alpha module: alpha
beta module: beta
~~~

If your build environment automatically puts alpha/beta onto the global classpath or module path, avoid placing duplicate-named artifacts in locations outside `mods` so the exercise does not unintentionally alter the root graph.

### 5.6. Why Is This Not a Trick to Bypass All JPMS Restrictions?

The experiment shows that **two modules with an overlapping package that do not export it to the same consumer** can form a layer with multiple class loaders. If you modify the descriptors so that a consumer module reads **two modules that both export `clash`**, resolution can fail **before** choosing between one-loader and many-loaders. You cannot use many-loaders to turn an invalid readability graph into a valid one.

## 6. Conceptual Example of ResolutionException Due to Duplicate Exports

Suppose there are three module descriptors:

~~~java
// alpha/module-info.java
module alpha {
    exports clash;
}
~~~

~~~java
// beta/module-info.java
module beta {
    exports clash;
}
~~~

~~~java
// consumer/module-info.java
module consumer {
    requires alpha;
    requires beta;
}
~~~

**These three code blocks illustrate module descriptors, not a standalone example that can compile/run in the same project.** If consumer must read both modules that export the same package `clash`, the validity of the module graph violates the `java.lang.module` rule on overlapping exported packages. Depending on whether the check is caught by javac, the linker, or during runtime graph resolution, you may see a compiler error or a `ResolutionException`/launcher failure.

Learners should not expect a fixed stdout for this *invalid* set of descriptors. Identify the error as belonging to **module resolution**, as opposed to `LayerInstantiationException` after resolution succeeds.

### Why Is export Different from opens?

- `exports p` allows access to public types in package p according to module readability.
- `opens p` allows deep reflection into the package under module access conditions; **it is not equivalent to exporting p for compile-time imports**.
- A package may not be exported yet still exist in the module descriptor/class files; it is still an overlapping package when trying to assign two modules to the same loader.
- `exports p to q` takes effect conditionally for consumer q; package conflicts should not be counted as a global rule without considering targets.
- The `--add-exports` or `--add-opens` options adjust access, but **they are not a general solution for resolving overlapping packages in a single loader**.

## 7. Exception Categories and Their Corresponding Phases

| Error / exception | Typical phase | Typical cause |
| --- | --- | --- |
| `FindException` | Module discovery/resolution | Root module or dependency cannot be found, unsuitable module reference |
| `ResolutionException` | Module graph resolution | Invalid readability graph, exported package conflict, module cycle |
| `LayerInstantiationException` | Layer creation | Overlapping package in the same loader, split delegation, loader/module ownership conflict |
| `IllegalArgumentException` | Incorrect layer API call | Parent configuration does not correspond to parent layer(s), invalid argument |
| `ClassNotFoundException` | Class loading | The module's loader cannot find the requested class |
| `IllegalAccessException` / `InaccessibleObjectException` | Reflection/access | Not appropriately exported/opened or access is restricted |
| `IllegalAccessError` | JVM linkage/access | Bytecode attempts to access a disallowed class/member |
| `LinkageError` | Linking/defining classes | Type/loader constraints or invalid bytecode definition depending on the situation |
| `ServiceConfigurationError` | Service loading | Missing service/provider configuration or subtype/type identity mismatch |

**Do not catch a generic `Exception` and assume everything is a split package.** The root cause might simply be a missing module, wrong root set, wrong parent layer, or package visibility. In tests, catch the **exact exception type** to identify the phase.

`FindException` and `ResolutionException` belong to `java.lang.module`, whereas `LayerInstantiationException` belongs to `java.lang`. They are not interchangeable.

## 8. Why Do Parent Layers Make the Situation More Complex?

A `ModuleLayer` can be created from a configuration that has **parent configuration(s)**; the runtime layer must have the **corresponding parent layer(s) in the correct order**.

Example of a valid pattern:

~~~java
ModuleLayer boot = ModuleLayer.boot();
Configuration cf = boot.configuration().resolve(
        finder, ModuleFinder.of(), roots);
ModuleLayer child =
        boot.defineModulesWithManyLoaders(
                cf, ClassLoader.getSystemClassLoader());
~~~

This is an **illustrative snippet** that requires declaring `finder`/`roots` and importing the appropriate types.

A call like `otherLayer.defineModulesWithManyLoaders(cf, parentLoader)` can throw `IllegalArgumentException` if the **parent of cf** does not correspond to `otherLayer.configuration()`. This is distinct from a package conflict: even modules with no overlapping packages can fail due to wiring the wrong parent.

### Modules with the Same Name in Two Layers

A child layer can have a module with the same name as one in another layer in certain configurations, but these are **two runtime Module objects**, not automatically the same identity. You need to distinguish:

- `ModuleLayer.findModule(name)` may search in the current layer or parent layers according to its contract.
- `Class.getModule()` returns the actual runtime module of the class.
- `ClassLoader` defines the type, and the same binary name can lead to different types.
- Mapping a module to a class loader that already has a previously defined module with the same name can be rejected.
- Plugin loader/layer design must account for where the **shared API** is placed so as not to redefine the host's interfaces/DTOs/annotations/exceptions.

Adding a layer is not an operation that "modifies the boot layer's module graph"; it creates a new runtime region with a parent relationship.

## 9. Split Delegation: When One Loader Must Delegate the Same Package to Multiple Loaders

Another confusing error of `defineModulesWithOneLoader` is **split delegation**. Conceptual example:

~~~text
Parent layer:
    module baseA exports p.api to child modules; loader LA
    module baseB exports p.api to child modules; loader LB

Child layer:
    a single class loader C for multiple modules
    C needs to find classes in package p.api from both LA and LB
    -> package -> target loader mapping is not unique
~~~

This is a **conceptual diagram**, not a verified valid/runnable configuration. If module readability/exports cause an early conflict, the error already occurs at resolution. When a configuration is valid but the created loader needs to resolve the same package via more than one target loader, `defineModulesWithOneLoader` can reject it with `LayerInstantiationException` due to split delegation.

Therefore, you must inspect the **entire module graph and loader mapping**, not merely scan for duplicate class names across two JARs in the child layer.

## 10. Same Package in Two Loaders Does Not Grant Package-Private Access

In the JVM, a **runtime package** involves the package name and the defining loader; merely sharing the same `package p;` declaration is not enough for classes to belong to the same runtime package.

If Module A and Module B each contain `p.Helper` or `p.Worker`, defined in different loaders, code in A cannot automatically access package-private members in B merely because they share the same package name.

JPMS also enforces module-level access rules:

- A class in module X wishing to use a public type from Y generally must have the appropriate readability relationship, and Y must export the package containing that type to X.
- Deep reflection generally requires appropriate `opens`.
- Runtime package and module ownership are not synonymous with the package name in source code.
- Two classes in two loaders with the same binary name have different runtime identities; casting between them can throw `ClassCastException`.

Therefore, `defineModulesWithManyLoaders` helps avoid **overlapping packages in the same loader**, but it does not turn them into a single shared package with equal access rights.

## 11. Runnable Code to Observe Which Module a Class Belongs To

In `LayerDemo.java`, the two statements:

~~~java
Class<?> a = layer.findLoader("alpha")
        .loadClass("clash.Alpha");
Class<?> b = layer.findLoader("beta")
        .loadClass("clash.Beta");
~~~

only load Class metadata. Printing:

~~~java
System.out.println(a.getModule().getName());
System.out.println(b.getModule().getName());
~~~

reveals the runtime module. If you want to instantiate or invoke a public method of a class located in a non-exported package from a host unnamed module via reflection, **module access checks can reject it**. To demonstrate split packages without bypassing module access permissions: only use `getName()`/`getModule()`/`getClassLoader()` as in the complete demo.

If you genuinely want to publish an API across a module boundary, place the API package once in a shared module and `exports` it appropriately, rather than keeping duplicate API packages in multiple modules.

## 12. Common Fixes by Root Cause

### Scenario A: Two JARs Share an API Package

Bad structure:

~~~text
api-v1.jar: com.vendor.api.*
api-v2.jar: com.vendor.api.*
both on module path, both resolved/read
~~~

Fix: choose one shared API module version; remove one duplicate, and normalize the dependency tree. If a plugin needs a private copy of a different version, use package relocation/an adapter/a process boundary by design, **do not let both modules export the same contract package to the consumer**.

### Scenario B: A Library Contains Both API and Implementation and Needs to Be Split into Modules

One module can export `com.example.api`, while another module contains `com.example.impl`. **Do not put both into `com.example.api`** just because legacy source code used the same package. Separate the package names clearly or keep them in one module if a module boundary is not needed.

### Scenario C: One-Loader Layer Fails, Many-Loaders Succeeds

This is evidence that **loader mapping** is the cause, not necessarily an invalid module graph. Inspect the overlapping packages and then decide:

- If the split package is accidental due to a dependency/version mismatch: fix the artifact/module packaging.
- If the overlapping package name is intentional and unexported, multiple loaders may be valid, though you need to evaluate the risks around readability, reflection, and type identity.
- Do not automatically switch all plugins to many-loaders if a shared API is still being redefined; the shared contract must be provided by a common module/loader.

### Scenario D: FindException Because a Root Module Is Missing

Add the right module to the module path or fix the root name. Do not tweak `opens` or swap the class loader to fix a module **that has not been found by the finder**.

### Scenario E: IllegalAccessError/InaccessibleObjectException

Check whether the module is **read** and the package is **exported/opened** in the right direction. Do not randomly delete class files with the same name when the actual error is simply module access permissions.

### Scenario F: Hot Reload / Module Layers

A new layer with new loaders can create distinct runtime types. When the host wants to maintain a shared API interface, it should reside in a shared parent layer/module. If each plugin layer bundles its own API JAR, even without a split package **within each individual layer**, the host can still encounter duplicated API Class identity across layers.

## 13. Inspecting Artifacts and the Module Graph

Useful JDK tools include:

~~~bash
jar --describe-module --file alpha.jar
jar --list --file alpha.jar
jdeps --module-path mods --check alpha
java --show-module-resolution --module-path mods -m alpha/your.Main
~~~

**These are illustrative commands**, requiring alpha.jar, mods, and the main class to actually exist. Do not use the `-m alpha/your.Main` line in the previous demo because module alpha does not declare a `Main`. `jar --list` helps view package entries; `jar --describe-module` inspects the descriptor; `jdeps` assists in analyzing dependencies by artifact and Java version; `--show-module-resolution` displays the modules resolved by the launcher.

Observing runtime code:

~~~java
System.out.println(someClass.getModule());
System.out.println(someClass.getClassLoader());
System.out.println(someClass.getModule().getLayer());
~~~

This is an **illustrative snippet**, requiring a `someClass` variable. It answers what the actual module/loader/layer are, rather than guessing solely from where the JAR is placed.

When using Java 17 on the module path, `java --validate-modules` can help check observable modules and detect certain issues such as duplicate module names or conflicts; **do not treat this as a substitute for resolving and running the application's actual root configuration**.

## 14. Why Not Resolve Split Packages with Arbitrary Child-First Loading?

A child-first `ClassLoader` can load the same binary name into its own loader and create two runtime types, but that is **not** a general solution for JPMS module layer errors:

1. A `Configuration.resolve` that fails due to a module readability/export conflict does not automatically become valid by overriding `loadClass`.
2. A `defineModulesWithOneLoader` call with package overlap still cannot validly map two modules containing the same package into the same loader.
3. If you switch to separate loaders, type identity issues for API/shared classes may appear.
4. A plugin should only isolate **implementation/private dependencies**, while shared APIs/annotations/exceptions/DTOs should be unified in a parent/common module if shared at the boundary.
5. Module `java.base` and `java.*` names have special protection; you should not attempt to redefine core packages.
6. Namespace isolation is not a security sandbox: a classloader does not prevent plugin code from performing I/O or accessing process resources according to its permissions.

Proper design starts with **module ownership for each package**, followed by choosing the module graph and loader mapping; it does not start by overriding delegation and hoping JPMS accepts it.

## 15. Layer Configuration Error Diagnostic Checklist

1. **Identify the phase:** discovery, resolution, layer creation, class loading, or reflective access.
2. **Print/log module roots:** are you requesting the right module names?
3. **List packages of each resolved module:** is there any package overlap?
4. **Inspect exports and qualified exports:** which module reads two providers for the same package?
5. **Inspect requires / requires transitive:** is there a cycle or missing dependency?
6. **Distinguish one loader vs. many loaders:** one-loader prohibits overlapping packages right at layer construction; many-loaders does not fix an invalid graph.
7. **Check parent configurations:** do they match the corresponding parent layers?
8. **Check loader ownership:** does custom `defineModules` map two modules with the same package to one loader, or reuse a loader that already has a module/class?
9. **Check runtime identity:** `Class.getModule()` and `getClassLoader()` of APIs/DTOs/annotations/exceptions.
10. **Check module path vs. classpath:** was a modular JAR placed in the wrong location, and have the root modules been resolved?
11. **Check automatic modules:** do legacy JARs have derived module names and broad exports causing conflicts?
12. **Fix at the source:** remove duplicate packages, restructure API/impl modules, fix requires/exports/opens, or choose an appropriate loader mapping — then re-run tests.
13. **Do not force the compiler/runtime to ignore errors with random flags:** `--add-reads`/`--add-exports` are not the answer for every overlap; they can even expose read/export conflicts more starkly.

## 16. Common Misconceptions

| Misconception | Accurate fact |
| --- | --- |
| "Two modules with the same package are always forbidden as soon as they sit on disk together" | It depends on whether the modules are resolved, the graph/exports, and the loader mapping |
| "If resolution succeeds, any kind of layer can be created" | One-loader mapping still prohibits overlapping packages and split delegation |
| "Switching to many-loaders fixes ResolutionException" | No. An invalid graph must be fixed at the resolution step |
| "A split package requires matching class names as well" | No. Only the package name needs to overlap; class names can differ |
| "Since the classpath allows split packages, the module path allows them in the exact same way" | JPMS adds readability, exports, and package ownership |
| "Using opens eliminates exported package conflicts" | Opens and exports have different semantics and do not cure all overlaps |
| "Same source package grants package-private access across modules" | Runtime packages and module access are not automatically unified across different loaders |
| "Each named module JAR gets its own separate loader" | It depends on layer mapping; one-loader can manage multiple modules |
| "Every exception from the module system is FindException" | ResolutionException, LayerInstantiationException, and access errors occur at different phases |
| "A custom child-first loader will always make JPMS accept it" | Module graph/layer constraints still must be satisfied |
| "Two layers with the same module name refer to the same module" | Runtime Module objects and class identities still depend on configurations/layers/loaders |
| "Having a JAR on the module path means its classes are automatically usable" | Modules must be selected/resolved and the package must be accessible |

## 17. Self-Check Exercises

**1. What is a split package?**  
Two or more modules/artifacts have classes with the same package name, without necessarily having duplicate class names.

**2. Two modules alpha/beta both contain package p but do not export p. Does Configuration necessarily fail?**  
No. You need to consider the module graph; they can coexist in a valid configuration.

**3. Why can defineModulesWithOneLoader fail even though Configuration.resolve succeeded?**  
Because one-loader requires no overlapping packages among the modules defined together in that loader; split delegation can also occur.

**4. Does defineModulesWithManyLoaders always resolve a split package conflict?**  
No. It only chooses a different loader mapping; the resolution graph still must be valid.

**5. What happens if consumer reads two modules that both export package p to it?**  
Resolution fails due to an exported package conflict in the readability graph.

**6. Do exports p and opens p have the same meaning?**  
No. Exports grants access to public types according to module rules; opens is for conditional deep reflection.

**7. If a root module is not found by ModuleFinder, what error typically occurs?**  
FindException at the discovery/resolution step, not LayerInstantiationException.

**8. Can two classes with the same package name but different defining loaders access each other's package-private members merely because their names match?**  
No, runtime packages do not automatically match when the defining loaders differ.

**9. What happens if custom defineModules maps two modules with the same package to the same loader?**  
LayerInstantiationException can occur due to a package ownership conflict.

**10. How can you observe which layer/module a class actually belongs to?**  
Use `clazz.getModule()`, `clazz.getClassLoader()`, and `clazz.getModule().getLayer()`.

**11. When a new layer redefines a shared API interface, can the host reliably cast the plugin object to the host's version?**  
No. A single shared runtime Class is needed at the boundary.

**12. Why is checking only the JAR names on the module path not enough?**  
You need to know the root modules, configuration resolution, readability graph, package exports, loader mapping, and parent layers.

## 18. Official Documentation

- Java SE 17, **ModuleLayer API** (overlapping packages, split delegation, one-loader/many-loaders, and custom mapping): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- Java SE 17, **java.lang.module package specification** (module resolution and exported-package conflicts): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/package-summary.html
- Java SE 17, **Configuration API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/Configuration.html
- Java SE 17, **ModuleFinder API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html
- Java SE 17, **ModuleDescriptor API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleDescriptor.html
- Java SE 17, **Module API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- Java SE 17, **java launcher**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Java Language Specification 17, [§7.7 Module Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7)
