# findLoader and Selecting a ClassLoader for a Module

## 1. The Problem: When a ModuleLayer Has Multiple Modules, How Do You Get the Right Loader?

Since Java 9, the Java Platform Module System (**JPMS**) not only organizes classes into packages on the classpath, but also introduces **named modules**, **module descriptors**, **Configuration**, and **ModuleLayer**. An application can resolve plugin modules at runtime, create a new module layer, and then want to load classes belonging to a specific module.

In that situation, the question "is getting the system ClassLoader and calling `loadClass` enough?" can be wrong. **Modules and loaders do not have a fixed 1:1 relationship.** A layer can map multiple named modules to the same loader or assign a separate loader for each module.

Primary API:

~~~java
ClassLoader loader = layer.findLoader("demo.alpha");
~~~

**`ModuleLayer.findLoader(String moduleName)` returns the ClassLoader into which the named module is defined**. It can look up the module in the current layer **or parent layers**. It does **not** load classes by name and does **not** create new layers or loaders itself.

Decision points:

- `layer.findLoader("demo.alpha")` selects **the loader by module name**, not by class name.
- The module is searched in that layer or its parent layers, following the search rules of `findModule`.
- If there is no named module with the requested name in the layer/parents, the method throws **`IllegalArgumentException`**.
- If the module is defined by the **bootstrap loader**, a **`null` result is valid** — it does not mean the module is missing.
- A module can be defined into a shared loader with other modules. Do not infer that "every module always has its own loader".
- Obtaining a `ClassLoader` does not prove that a specific class exists, is exported, is initialized, or that the caller has permission to access all members of the class.

**Learning outcomes:** understand `findLoader`, create layers using `defineModulesWithOneLoader`/`defineModulesWithManyLoaders`, compare `Class.getClassLoader`/`Module.getClassLoader`, handle nonexistent modules and the bootstrap loader, distinguish parent layer relationships from parent ClassLoader relationships, and select the right loader when loading classes/plugins.

## 2. Foundations: Module, Configuration, ModuleLayer, and ClassLoader

### 2.1. What Is a Named Module?

A named module, for example `demo.alpha`, is usually declared in `module-info.java`:

~~~java
module demo.alpha {
    exports demo.alpha;
}
~~~

This descriptor defines the module name and relationships such as `requires`, `exports`, `opens`, `uses`, or `provides`. The module is **resolved** in a `Configuration` and **defined** into a runtime `Module` when creating a `ModuleLayer`.

These are two distinct steps:

~~~text
ModuleFinder (finds module artifacts)
    |
    v
Configuration.resolve(...) (resolves the module graph)
    |
    v
ModuleLayer.defineModules...(...) (creates runtime Module objects
                                    and assigns ClassLoader)
    |
    v
layer.findModule("demo.alpha") -> Module
layer.findLoader("demo.alpha") -> ClassLoader (may be null)
    |
    v
Class.forName(module, binaryName) or loader.loadClass(binaryName)
~~~

There is no rule that "if a JAR is in `--module-path`, all classes are automatically loaded". A module must be resolved and present in an appropriate runtime configuration. Creating a layer only declares the module/loader mapping; classes are still loaded on demand.

### 2.2. What Information Does a Layer Store?

`ModuleLayer` represents the runtime named modules created from a configuration, together with the module → loader mapping. A layer can have one or more **parent layers**.

Useful APIs:

| API | Role |
|---|---|
| `ModuleLayer.boot()` | Gets the boot layer once the JVM has started |
| `layer.configuration()` | Gets the corresponding `Configuration` |
| `layer.modules()` | Set of modules **defined directly in this layer** |
| `layer.parents()` | List of parent layers in search order |
| `layer.findModule(name)` | Searches for `Module` in the layer or parent layers, returning `Optional<Module>` |
| `layer.findLoader(name)` | Looks up the loader of a named module in the layer/parents; returns `ClassLoader` or `null` for bootstrap |
| `module.getLayer()` | Layer of the runtime module, if any |
| `module.getClassLoader()` | Defining ClassLoader of the module, which may be `null` for bootstrap |
| `SomeType.class.getModule()` | Runtime module containing that class |
| `SomeType.class.getClassLoader()` | Defining loader of the runtime class itself |

**Important:** `layer.modules()` only lists modules **directly** in the layer; `findModule` and `findLoader` can find modules **belonging to a parent layer**. Do not use `layer.modules().contains(...)` as the sole condition for allowing a call to `findLoader`.

### 2.3. ModuleLoader Mapping Is Not Module Readability

A module A that `requires` module B means the JPMS graph has the appropriate readability edge. Whether A and B share the same ClassLoader is a mapping choice made when creating the layer.

Independent conditions:

- **Module resolution/readability:** which module reads which module according to `requires` and valid modifications.
- **Exports:** which module's public packages are accessible to another module.
- **Opens:** conditions for opening packages for deep reflection.
- **ClassLoader mapping:** which loader defines the classes belonging to which module.
- **Java visibility:** `public`, `protected`, package-private, and `private` remain in effect.

Do not replace `requires`, `exports`, or `opens` by merely changing the loader. Conversely, opening a module does not automatically change its defining loader.

## 3. The Exact Contract of `ModuleLayer.findLoader(String)`

Signature:

~~~java
public ClassLoader findLoader(String name)
~~~

According to the [Java SE 21 ModuleLayer API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html#findLoader(java.lang.String)):

1. Searches for the named module with name `name` **in the current layer**.
2. If it is not in the current layer, continues searching in **parent layers** in the same way `findModule` searches (in parent order, along with their parents).
3. Returns the loader into which the found module was defined.
4. If there is no module with that name in the layer **and all parent layers**, throws `IllegalArgumentException`.
5. For a module defined by the **bootstrap ClassLoader**, returns `null`. That is why the return type is not `Optional<ClassLoader>`.
6. Following the general rules of `ModuleLayer`, `name == null` causes a `NullPointerException`. In environments with a legacy SecurityManager, checking the `RuntimePermission("getClassLoader")` permission may cause a `SecurityException`.

### 3.1. Distinguishing the Three Return Cases

~~~java
ModuleLayer boot = ModuleLayer.boot();

ClassLoader baseLoader = boot.findLoader("java.base");
// baseLoader == null: java.base is defined by bootstrap, not missing.

ClassLoader appLoader = boot.findLoader("java.sql");
// In a boot layer configuration that includes java.sql, this may return a built-in loader.
// Do not hardcode that all modules share the same loader.
~~~

The lines above are an **illustrative snippet**, not standalone; the `java.sql` module must be present in the current boot layer to call `findLoader("java.sql")`. `java.base` is the mandatory base module of the boot layer.

If the module does not exist:

~~~java
try {
    boot.findLoader("module.that.does.not.exist");
} catch (IllegalArgumentException ex) {
    System.out.println("No such module in the layer hierarchy");
}
~~~

This is not `ClassNotFoundException` because we are **looking up a module**, not yet calling `loadClass`.

### 3.2. Looking Up a Module in a Parent Layer Is Still Valid

~~~java
ModuleLayer child = /* a layer created with boot as parent */;
ClassLoader bootstrap = child.findLoader("java.base");
~~~

The code above is an illustrative snippet; the `child` variable must be created beforehand. At that point, `java.base` is found in the **boot parent layer**, and the loader is `null`.

The reasoning "`child.modules()` does not contain `java.base`, so `child.findLoader("java.base")` must throw an exception" is **wrong**. The API is designed to continue searching parent layers.

### 3.3. `null` Means Bootstrap, Not "Module Missing"

Two "not found" paths must be kept separate:

~~~text
layer.findModule("no.such.module")
    -> Optional.empty()

layer.findLoader("no.such.module")
    -> IllegalArgumentException

layer.findLoader("java.base")
    -> null (bootstrap loader; valid module)
~~~

If the application needs to represent an optional result, **check the module first**:

~~~java
String name = "java.base";
Module found = layer.findModule(name).orElse(null);
if (found == null) {
    System.out.println("Module not found");
} else {
    ClassLoader loader = layer.findLoader(name);
    System.out.println(loader == null ? "bootstrap" : "non-bootstrap");
}
~~~

This pattern avoids conflating the bootstrap loader with a missing module.

## 4. Who Decides Which Loader a Module Is Assigned To?

**The module → loader mapping is decided when creating the layer**, not when calling `findLoader`. Common options:

| Layer creation method | Mapping | When to use |
| --- | --- | --- |
| `parent.defineModulesWithOneLoader(cf, parentLoader)` | One **new** loader for all modules in `cf` | Module packages do not overlap and a shared loader is needed |
| `parent.defineModulesWithManyLoaders(cf, parentLoader)` | Each module in `cf` uses its own separate **new** loader | Clear loader/module separation is needed |
| `parent.defineModules(cf, mapping)` | Application chooses the `moduleName -> ClassLoader` mapping | A custom loader with sufficient understanding of JPMS/module ownership is available |

`parentLoader` is the parent **class loader** for the new loader; it does not replace the parent `ModuleLayer`. `WithOneLoader` and `WithManyLoaders` must comply with the module graph and package constraints. If multiple modules with the same package name are assigned to a shared loader, the layer definition step may throw `LayerInstantiationException`. A loader may also delegate directly by package/module differently from a simple parent-first chain.

Within the same layer created using `WithOneLoader`:

~~~java
ClassLoader alpha = layer.findLoader("demo.alpha");
ClassLoader beta = layer.findLoader("demo.beta");
System.out.println(alpha == beta);  // true
~~~

If the layer is created using `WithManyLoaders` with those two modules, the comparison above is `false`. This is an **illustrative snippet** requiring `layer` to actually contain the two named modules; classes named `demo.alpha` and `demo.beta` must belong to the resolved configuration.

The **instance** variants return `ModuleLayer` directly; the static overloads `ModuleLayer.defineModulesWithOneLoader(cf, parents, parentLoader)` or `defineModulesWithManyLoaders` return `ModuleLayer.Controller`, obtaining the layer via `controller.layer()`. Use the static variants when multiple parent layers are needed or when you want to adjust read/export/open edges via Controller. The dedicated article on the two methods `defineModulesWithOneLoader/ManyLoaders` explains build commands, direct delegation, and strategy selection in detail; this section keeps the focus on how `findLoader` reads the existing mapping.

## 5. How Does a Parent Layer Differ from a Parent ClassLoader?

This is one of the most common misconceptions when designing plugins:

~~~text
           JPMS ModuleLayer hierarchy
       ModuleLayer.boot()
             |
             v
       Child ModuleLayer
          |        |
          v        v
       Module A   Module B

           ClassLoader relationships
       System ClassLoader (parentLoader argument)
          |             |
          v             v
       Module loader A  Module loader B
       (if using WithManyLoaders)
~~~

The two kinds of relationships are declared in **two different places**:

- **Parent `ModuleLayer`**: describes where parent modules can be found and the module resolution graph.
- **Parent `ClassLoader`**: the `parentLoader` parameter controls the API-level relationship between the created loader and its parent loader; however, loaders created by layer methods may implement **direct delegation by module/package** in accordance with JPMS.

**Do not conflate them:** "`ModuleLayer.boot()` is the parent" does not mean every class loader of the child layer uses a single parent corresponding to the entire boot layer; the boot layer can use bootstrap, platform, or application loaders.

Specifying `ClassLoader.getSystemClassLoader()` as `parentLoader` does **not** put new modules into the system/application loader. `WithOneLoader`/**`WithManyLoaders` create new loaders** and configure them with the passed parent loader.

If the Java API returns `null` for `java.base`, that is the bootstrap loader, **not a null object that needs to be fixed with `new URLClassLoader`**. Bootstrap is specially implemented by the JVM.

## 6. Standalone Java 17+ Example: `findLoader` with One and Many Loaders

Practice: create two named modules `demo.alpha`, `demo.beta`, resolve them from the `mods` directory, and create **two independent child layers** on the same boot layer:

- A `single` layer with **one loader for both modules**.
- A `many` layer with **two separate loaders**.
- Compare the module loader, the ClassLoader of the actual class, and the module identity.
- Look up `java.base` from a child layer to demonstrate **parent search + bootstrap null**.
- Call `findLoader` with a missing module name to demonstrate `IllegalArgumentException`.
- Demonstrate that two runtime `Module` objects with the same name in **two sibling layers** are not the same object.

### 6.1. Directory Structure

~~~text
demo/
├── src/
│   ├── demo.alpha/
│   │   ├── module-info.java
│   │   └── demo/alpha/Alpha.java
│   ├── demo.beta/
│   │   ├── module-info.java
│   │   └── demo/beta/Beta.java
│   └── app/
│       └── LayerDemo.java
├── mods/
│   ├── demo.alpha/         # exploded named module
│   └── demo.beta/
└── out/
    └── app/                # Launcher in the unnamed module
~~~

The launcher program `LayerDemo` resides on the classpath and does not import `Alpha`/`Beta`. It only knows the module/class names at runtime, separating the launcher's compile classpath from module resolution.

### 6.2. File `src/demo.alpha/module-info.java`

~~~java
module demo.alpha {
    exports demo.alpha;
}
~~~

### 6.3. File `src/demo.alpha/demo/alpha/Alpha.java`

~~~java
package demo.alpha;

public class Alpha {
    public static String id() {
        return "alpha";
    }
}
~~~

### 6.4. File `src/demo.beta/module-info.java`

~~~java
module demo.beta {
    exports demo.beta;
}
~~~

### 6.5. File `src/demo.beta/demo/beta/Beta.java`

~~~java
package demo.beta;

public class Beta {
    public static String id() {
        return "beta";
    }
}
~~~

`Beta` is compiled into a valid module to test multiple modules/loaders; the launcher does not need to call the `Beta.id()` method directly.

### 6.6. File `src/app/LayerDemo.java`

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public class LayerDemo {
    public static void main(String[] args) throws Exception {
        ModuleLayer boot = ModuleLayer.boot();
        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));
        Configuration config = boot.configuration().resolve(
                finder, ModuleFinder.of(),
                Set.of("demo.alpha", "demo.beta"));

        ClassLoader parentLoader =
                ClassLoader.getSystemClassLoader();

        ModuleLayer single =
                boot.defineModulesWithOneLoader(config, parentLoader);
        System.out.println("singleSharedLoader="
                + (single.findLoader("demo.alpha")
                        == single.findLoader("demo.beta")));

        ModuleLayer many =
                boot.defineModulesWithManyLoaders(config, parentLoader);
        ClassLoader aMany = many.findLoader("demo.alpha");
        ClassLoader bMany = many.findLoader("demo.beta");
        System.out.println("manyDistinctLoaders="
                + (aMany != bMany));

        Module alphaModule =
                many.findModule("demo.alpha").orElseThrow();
        Class<?> alpha =
                Class.forName(alphaModule, "demo.alpha.Alpha");
        System.out.println("classFromSelectedLoader="
                + (alpha != null
                        && alpha.getClassLoader() == aMany));

        System.out.println("correctModuleIdentity="
                + (alpha.getModule() == alphaModule));
        System.out.println("parentModuleVisible="
                + many.findModule("java.base").isPresent());
        System.out.println("parentLoaderLookupWorks="
                + (many.findLoader("java.base")
                        == boot.findLoader("java.base")));
        System.out.println("bootBaseUsesBootstrap="
                + (boot.findLoader("java.base") == null));

        try {
            many.findLoader("module.that.does.not.exist");
            System.out.println("missingModuleRejected=false");
        } catch (IllegalArgumentException expected) {
            System.out.println("missingModuleRejected=true");
        }

        System.out.println("sameModuleDifferentLayers="
                + (single.findModule("demo.alpha").orElseThrow()
                        != alphaModule));
    }
}
~~~

### 6.7. Build and Run Commands

On Linux/macOS, from inside the `demo` directory:

~~~sh
mkdir -p mods/demo.alpha mods/demo.beta out/app

javac --release 17 -d mods/demo.alpha \
    src/demo.alpha/module-info.java \
    src/demo.alpha/demo/alpha/Alpha.java

javac --release 17 -d mods/demo.beta \
    src/demo.beta/module-info.java \
    src/demo.beta/demo/beta/Beta.java

javac --release 17 -d out/app src/app/LayerDemo.java
java -cp out/app LayerDemo
~~~

The trailing `\` is POSIX shell line continuation. If using Windows PowerShell, write each `javac` command on a single line:

~~~powershell
New-Item -ItemType Directory -Force mods/demo.alpha, mods/demo.beta, out/app | Out-Null
javac --release 17 -d mods/demo.alpha src/demo.alpha/module-info.java src/demo.alpha/demo/alpha/Alpha.java
javac --release 17 -d mods/demo.beta src/demo.beta/module-info.java src/demo.beta/demo/beta/Beta.java
javac --release 17 -d out/app src/app/LayerDemo.java
java -cp out/app LayerDemo
~~~

**Note:** do not add `mods` to `-cp`. `ModuleFinder.of(Path.of("mods"))` reads the module artifacts to create a separate configuration; the `Alpha`/`Beta` classes do not need to appear on the system classpath.

**Exact stdout**, compiled with `javac --release 17` and run with the JDK:

~~~text
singleSharedLoader=true
manyDistinctLoaders=true
classFromSelectedLoader=true
correctModuleIdentity=true
parentModuleVisible=true
parentLoaderLookupWorks=true
bootBaseUsesBootstrap=true
missingModuleRejected=true
sameModuleDifferentLayers=true
~~~

### 6.8. Analysis of the Nine Results

| Line | Meaning |
|---|---|
| `singleSharedLoader=true` | `defineModulesWithOneLoader` maps the two new modules to the same loader |
| `manyDistinctLoaders=true` | `defineModulesWithManyLoaders` creates a separate loader for each module |
| `classFromSelectedLoader=true` | `Class.forName(Module,String)` returns a class whose defining loader matches `findLoader("demo.alpha")` |
| `correctModuleIdentity=true` | The `Alpha` class truly belongs to the runtime `Module` returned by `many.findModule` |
| `parentModuleVisible=true` | The child layer finds `java.base` in the boot parent layer |
| `parentLoaderLookupWorks=true` | The child's `findLoader` **searched parent layers**; the result matches `boot.findLoader` |
| `bootBaseUsesBootstrap=true` | `java.base` uses the bootstrap loader, represented by `null` |
| `missingModuleRejected=true` | A module not in the layer or its parents causes `findLoader` to throw `IllegalArgumentException` |
| `sameModuleDifferentLayers=true` | Named modules with the same name in two sibling layers are two independent runtime `Module` objects |

**Key takeaway:** you cannot tell which ClassLoader a module uses solely from its name or the three built-in loaders. You must query the **context-appropriate ModuleLayer**, and also consider which layer the module belongs to when multiple sibling layers exist.

### 6.9. Why Obtaining `Class<?>` and Comparing Loaders Is Not Enough to Check Access

In the example above, `Class.forName(alphaModule, "demo.alpha.Alpha")` uses the module-based overload. It returns `Class<?>` when a class belonging to the requested module is found, or `null` if the class is not in that module. This API does **not automatically link/initialize** the class and does not check caller access to the class.

If the code proceeds to use reflection, constructors, fields, or methods, it must check `exports`/`opens`, `requires`, and Java access rules separately. Successfully querying a loader does not automatically open a module.

## 7. Selecting a Loader When Real Code Needs to Load a Class

### 7.1. You Know the Module Name and the Binary Class Name

Simple pattern:

~~~java
static Class<?> locate(ModuleLayer layer,
                       String moduleName,
                       String binaryName) {
    Module module = layer.findModule(moduleName)
            .orElseThrow(() -> new IllegalArgumentException(
                    "Module not in layer hierarchy: " + moduleName));
    return Class.forName(module, binaryName);
}
~~~

**This is an illustrative method** that must be placed inside a class; it is not a standalone runnable program. It verifies the actual `Module` and then calls the module-based overload to ensure the resulting class belongs to the specified module.

Caller:

~~~java
Class<?> type = locate(layer, "demo.alpha", "demo.alpha.Alpha");
if (type == null) {
    System.out.println("Named module không cung cấp class đó");
}
~~~

Using `Class.forName(Module,String)` is meaningful when a layer's loader may define multiple modules; it avoids assuming that "the loader found the class" means the class belongs to **the requested module**.

### 7.2. You Have the Module Name and Want to Use an Explicit Loader

~~~java
ClassLoader loader = layer.findLoader("demo.alpha");
Class<?> type = loader.loadClass("demo.alpha.Alpha");
~~~

The snippet above is appropriate when the named module is assigned to a **non-null loader**. If the named module uses the bootstrap loader, `loader == null`; you **cannot** call `loader.loadClass`. Choose the appropriate API:

~~~java
Module module = layer.findModule(moduleName).orElseThrow();
Class<?> type = Class.forName(module, binaryName);
~~~

The module-based lookup handles the bootstrap loader case; `Class.forName(Module,String)` returns null for a class not in the module, and has separately documented exceptions/errors.

### 7.3. A Shared Loader Can Define Multiple Modules

In the `single` layer of the demo, both `demo.alpha` and `demo.beta` use the same loader. Therefore:

~~~text
single.findLoader("demo.alpha") == single.findLoader("demo.beta")
=> true
~~~

Looking only at `ClassLoader` does not distinguish which module a class belongs to. When an exact check is needed:

~~~java
Module expected = layer.findModule("demo.alpha").orElseThrow();
boolean rightModule = clazz.getModule() == expected;
~~~

This is a snippet that requires the `layer`/`clazz` variables. Avoid comparing only the `clazz.getModule().getName()` string if the application has multiple sibling layers with the same module name: **Module object identity** matters.

### 7.4. You Need to Determine the Loader of an Existing Class

If you already have a `Class<?>`, usually use directly:

~~~java
ClassLoader loader = actualClass.getClassLoader();
Module owner = actualClass.getModule();
ModuleLayer ownerLayer = owner.getLayer();
~~~

- `getClassLoader()` reflects the defining loader of the class.
- `getModule()` identifies the actual module containing the class.
- `getLayer()` indicates the layer of a **named module** created in a layer; it may be `null` in cases where the module does not belong to a typical layer.
- If `ownerLayer != null` and the module is named, you can compare `ownerLayer.findLoader(owner.getName())` against the defining loader.

This is a practical diagnostic approach that is better than "just printing `ClassLoader.getSystemClassLoader()`".

## 8. Other Cases and Limitations

### 8.1. Unnamed Modules and the Classpath

Every `ClassLoader` has an **unnamed module** associated with classes that do not belong to a named module. However, `ModuleLayer.findLoader` takes a **named module name**, not a binary class name and not a selector for an unnamed module.

If the class's module has `isNamed() == false`, `module.getName()` is `null`. Do not call `layer.findLoader(module.getName())`; use `clazz.getClassLoader()` or `module.getClassLoader()` directly when you want to know the actual loader.

### 8.2. Being on the Module Path Does Not Mean Resolved

`ModuleFinder.of(Path.of("mods"))` finds module artifacts on the path, but a module only appears in the runtime layer after an appropriate `Configuration.resolve(...)` and `defineModules...` step.

Scenario:

~~~text
foo.jar on disk -> finder can recognize foo
configuration does not resolve foo -> layer does not have foo
layer.findLoader("foo") -> searches parent; if also absent -> IllegalArgumentException
~~~

Therefore, `findLoader` does not load module artifacts or open unresolved JARs on its own. Check roots, `requires`, and graph resolution first.

### 8.3. Same Module Name in Sibling Layers

Two child layers created independently on the same boot layer can each define a module named `demo.alpha`. Result:

~~~text
Layer S -> Module demo.alpha (Module object S)
Layer M -> Module demo.alpha (Module object M)

Module object S != Module object M
Module loader S != Module loader M (in the demo)
~~~

You must keep the exact layer reference corresponding to the plugin/application. If you accidentally use `layerS.findLoader("demo.alpha")` to handle a class from `layerM`, the loader matches the name but has the **wrong runtime module identity**, which can cause `ClassCastException`, reflection failures, or loss of JPMS access.

### 8.4. Named Modules in the Boot Layer

`ModuleLayer.boot()` contains `java.base` and the startup resolved modules. These modules may belong to the JVM's bootstrap, platform, or application loaders.

There is no rule that "all boot modules have `ClassLoader == null`". The demo intentionally checks **`java.base`**, a case with the bootstrap loader. For other modules, do not hardcode; query `findLoader` or `module.getClassLoader()`.

### 8.5. You Cannot "Move a Module to Another Loader" Using `findLoader`

`findLoader` is a read operation. There is no `layer.setLoader(module, anotherLoader)` API to swap the loader of an already defined runtime named module. Changing the mapping usually requires creating **another layer** with a different configuration and policy, or using an appropriate launcher/plugin design.

Creating a new layer can create **new class identities**. Code must handle the plugin lifecycle, old class references, service instances, threads, caches, and the old `ModuleLayer` to avoid memory leaks.

### 8.6. Resource Lookup and TCCL Are Also Different

`Thread.currentThread().getContextClassLoader()` is the Thread Context ClassLoader, which may differ from the module's loader in the layer. Only when an API is designed to use the TCCL does that value apply.

`ServiceLoader.load(service)` typically uses the TCCL as a convenience overload, whereas `ServiceLoader.load(layer, service)` selects providers according to layer/module semantics. Do not change the TCCL and infer that `layer.findLoader(name)` will return a different loader: module mapping is not altered by the thread context.

## 9. Common Errors When Using `findLoader`

| Symptom | Cause to check | How to handle |
|---|---|---|
| `IllegalArgumentException` from `findLoader("foo")` | `foo` is not in the layer or its ancestors | Check `findModule`, `configuration`, roots, and the layer reference |
| `NullPointerException` when calling `loader.loadClass` | The loader validly returns `null` for a bootstrap module | Handle null; consider `Class.forName(Module,String)` |
| Have a loader but get `ClassNotFoundException` | Incorrect class name, class missing, or mapping/delegation cannot find it | Check binary name, package, module artifact, and use the module-based overload when appropriate |
| `Class.forName(Module,name) == null` | The class is not in the **specified module**; it may be in another module | Compare `clazz.getModule()` and the module path |
| `LayerInstantiationException` with `WithOneLoader` | Overlapping packages or split delegation that cannot be resolved | Adjust the module graph/mapping; consider multiple loaders |
| Layer has the module name but the class belongs to the wrong module | Wrong layer, shared loader, or sibling layer mix-up | Compare `clazz.getModule() == expectedModule` |
| `ClassCastException` when type names are identical | Two classes have different defining loaders | Use a shared API module that is consistently mapped and read |
| `IllegalAccessError`/`InaccessibleObjectException` | Java/JPMS accessibility, incompatible `exports`/`opens` | Analyze permissions separately; do not merely change the loader |
| Module is in `--module-path` but lookup cannot find it | Module is not resolved or not in the right layer | Check `ModuleFinder`, roots, and `Configuration` |
| Deadlock when using custom `defineModules` loaders | Delegation does not follow readability or class loading locks | Design loaders to be parallel-capable and avoid dependency cycles |
| TCCL points to an old plugin while `findLoader` returns the current loader | The two mechanisms are completely independent | Restore TCCL and manage the layer/plugin lifecycle |

### Diagnostic Checklist

1. Do you have the right **ModuleLayer instance**, or just another layer in the plugin system?
2. Is the named module in `layer.modules()`, or is it only a parent module visible via `findModule`?
3. If `findLoader` returns `null`, is it a bootstrap module?
4. If an exception is thrown, does the module exist in the layer **and all parents**?
5. Was the layer created with `WithOneLoader`, `WithManyLoaders`, or custom `defineModules`?
6. Which ClassLoader is `parentLoader`, and which layer is the parent `ModuleLayer`?
7. If you already have the class, what are `clazz.getModule()` and `clazz.getClassLoader()`?
8. Is the name passed to `findLoader` a module name, rather than a package/class name?
9. Are there conflicts with packages, readability, exports/opens, or custom delegation?
10. Does the module being used belong to the classpath unnamed module or an actual named module?
11. When reloading a plugin, is the old loader/layer still referenced by caches or threads?

## 10. Common Misconceptions

1. **"Every named module always has its own loader."** False: `WithOneLoader` allows multiple named modules to share one loader.
2. **"`findLoader` only searches in the direct layer."** False: it continues searching parent layers.
3. **"A null loader means the module is missing."** False: `null` is how the API represents the bootstrap loader.
4. **"`findLoader` returns null when a module is missing."** False: it throws `IllegalArgumentException` when missing from both the layer and its ancestors.
5. **"`findLoader("pkg.Class")` looks up the loader for that class."** False: the input is a **module name**.
6. **"Adding a JAR to the module path makes `findLoader` automatically recognize the module."** False: you must resolve it and create a layer.
7. **"Having the same loader means classes belong to the same module."** False: one loader can define multiple named modules.
8. **"The parent ModuleLayer is the parent ClassLoader."** False: they are two different relationships.
9. **"Changing the TCCL will change `layer.findLoader`."** False: layer mapping is independent of the TCCL.
10. **"If the loader can find the class, the caller is allowed to invoke all methods."** False: JPMS + Java visibility are still enforced.
11. **"Two modules with the same name in two sibling layers are the same runtime Module."** False: object identity and mapping may differ.
12. **"`findLoader` loads classes itself and runs static initializers."** False: it only returns the loader.
13. **"Calling the static `defineModulesWithOneLoader` returns a ModuleLayer directly."** False: the static variant returns a `ModuleLayer.Controller`.
14. **"Using a custom loader with `defineModules` automatically satisfies module delegation rules."** False: the application is responsible for that.
15. **"The boot layer only has the bootstrap loader."** False: boot modules can be defined by multiple built-in loaders.
16. **"Comparing only the module name String is enough to identify the right layer."** False when there are sibling layers with the same name.

## 11. Exercises and Self-Check Questions

1. Does `ModuleLayer.findLoader` take a module name or a class name?
2. When the module is absent from the layer and all parent layers, what does `findLoader` throw?
3. Why can `findLoader("java.base")` return `null` without being an error?
4. How do `findModule(name)` and `findLoader(name)` differ in return type and in the not-found case?
5. Does `layer.modules()` list modules that only appear in parent layers?
6. Why does `many.findLoader("java.base")` in the demo not throw an error?
7. How many ClassLoaders does `defineModulesWithOneLoader` create for the new modules?
8. How does `defineModulesWithManyLoaders` handle each named module?
9. Is the `parentLoader` parameter a `ModuleLayer`? What is its purpose?
10. Does `ModuleLayer.defineModulesWithOneLoader(cf, parents, loader)` return a `ModuleLayer` or a `Controller`?
11. When should you use `defineModules` with `Function<String,ClassLoader>` instead of the two convenience methods?
12. Why can the `Alpha` class in a child module layer still belong to a loader different from the system loader, even when passing the system loader as `parentLoader`?
13. How do `Class.forName(Module,String)` and `loader.loadClass(binaryName)` differ when one loader defines multiple modules?
14. Why is `alpha.getClassLoader() == many.findLoader("demo.alpha")` a useful check?
15. When `demo.alpha` has the same name in two sibling layers, should you compare `Module.getName()` or compare the `Module` objects directly?
16. Which rules besides class loader mapping affect invoking a public class/method under JPMS?
17. Can you change the loader assigned to an already defined module using only `findLoader`?
18. When `ClassNotFoundException` occurs, why is it necessary to verify that the module has been resolved and that the loader actually sees the binary name?
19. Why should you not assume that the TCCL is the same as `findLoader` of a named module?
20. If the loader of `java.base` is null, how do you obtain the `Class<?>` of a class in that module in a contract-compliant way?

**Completion criteria:** run the demo and explain all nine stdout lines; know how to use `findLoader` to select a loader by module; distinguish lookups across parent layers, the bootstrap `null` result, and exceptions when a module is missing; and understand that module mapping is decided at layer creation time.

## 12. Official Documentation

- [Java SE 21 — `ModuleLayer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html): layers, parent layers, `findLoader`, `findModule`, and layer creation methods.
- [Java SE 21 — `ModuleLayer.findLoader(String)`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html#findLoader(java.lang.String)): how modules are looked up in the layer/parents, bootstrap null, and exceptions.
- [Java SE 21 — `Module`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): `getClassLoader()`, `getLayer()`, and module identity.
- [Java SE 21 — `Configuration`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/Configuration.html): module graph resolution.
- [Java SE 21 — `ModuleFinder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleFinder.html): reading module artifacts from directories/JARs.
- [Java SE 21 — `Class.forName(Module,String)`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#forName(java.lang.Module,java.lang.String)): locating/loading by runtime module, distinguished from the ClassLoader-based overload.
- [Java SE 21 — `ClassLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): defining loader, delegation, and `loadClass`.

**Scope:** Java 17+ and JPMS. The example was compiled with `javac --release 17` and executed successfully, with no Maven/Gradle or framework dependencies. For custom module layers in plugin systems, cross-check the runtime `Module` object along with the actual loader, rather than drawing conclusions based on name strings or a simplified three-loader diagram.
