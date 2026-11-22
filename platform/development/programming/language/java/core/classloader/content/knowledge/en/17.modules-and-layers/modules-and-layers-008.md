# defineModulesWithOneLoader and defineModulesWithManyLoaders

## 1. Objective: choosing a ClassLoader strategy for a ModuleLayer

Since Java 9, the Java Platform Module System (JPMS) allows an application to create a new **ModuleLayer** at runtime. This is a common scenario in plugin runtimes, IDE tools, containers, or applications that want to load a set of **named modules** independently of the module layer initialized at JVM startup.

The two convenience APIs on **java.lang.ModuleLayer** are:

- **defineModulesWithOneLoader**: creates **one new ClassLoader** and assigns **all modules of the configuration** to that loader.
- **defineModulesWithManyLoaders**: creates **one new ClassLoader per module** in the configuration.

The core difference is the **mapping from module to defining loader**. Both create a new layer, create runtime Module objects, and establish the corresponding module graph. They do not merely create a wrapper layer around existing Class objects.

### What will you learn?

After this lesson, you will be able to:

1. Explain **ModuleFinder → Configuration → ModuleLayer** in the right order.
2. Distinguish **parent layer** from **parent ClassLoader**.
3. Know when to choose one-loader and when to choose many-loaders.
4. Use **findLoader**, **findModule**, **Class.getModule**, and **Class.getClassLoader** to inspect the runtime.
5. Create two Java 17+ named modules and load them using both strategies.
6. Understand **direct delegation**, package overlap, split delegation, readability, and class identity.
7. Know the difference between the **instance overload** and the **static overload returning Controller**.
8. Diagnose resolve/define/load errors and design a module layer lifecycle for plugins.

## 2. Three objects that cannot be equated

### 2.1 ModuleFinder: finding module artifacts

**java.lang.module.ModuleFinder** helps find module definitions from sources such as exploded module directories or modular JARs.

~~~java
ModuleFinder finder = ModuleFinder.of(Path.of("mods"));
~~~

This is a snippet placed in a method with appropriate imports. **Path.of("mods")** points to the directory containing the compiled modules. A ModuleFinder provides information for resolution to select modules; it **does not create a ModuleLayer itself** and is not a ClassLoader.

### 2.2 Configuration: the resolved module graph

**java.lang.module.Configuration** contains the resolved modules and requires/readability relationships at the configuration level.

~~~java
ModuleLayer parent = ModuleLayer.boot();
Configuration cf = parent.configuration().resolve(
        finder,
        ModuleFinder.of(),
        Set.of("demo.beta"));
~~~

The snippet above assumes that finder has been declared, imports are present, and the demo.beta module exists in finder. **resolve** takes the boot-layer configuration as the parent and uses finder to locate the demo.beta module and its appropriate dependencies.

**Configuration does not yet mean the classes have been loaded into the JVM.** It is a description of the resolved graph; defining named modules at runtime still requires the layer creation step.

### 2.3 ModuleLayer: the module graph defined in the JVM runtime

A layer contains the actual **java.lang.Module** objects recognized by the JVM, accompanied by the module → ClassLoader mapping.

~~~java
ModuleLayer layer =
        parent.defineModulesWithOneLoader(
                cf, ClassLoader.getSystemClassLoader());
~~~

Then:

~~~java
ClassLoader loader = layer.findLoader("demo.beta");
Module module = layer.findModule("demo.beta").orElseThrow();
~~~

**findLoader** indicates the loader corresponding to the module; **findModule** returns an Optional Module by name. These methods do not automatically run a module's main or constructors.

### Summary of the three steps

~~~text
Modular JARs / exploded modules
               |
               v
       ModuleFinder.of(...)
               |
               v
Configuration.resolve(... roots ...)
               |
               v
       Configuration cf
               |
               v
ModuleLayer.defineModulesWithOneLoader(...)
or defineModulesWithManyLoaders(...)
               |
               v
        ModuleLayer runtime
           /         \
       Module       ClassLoader mapping
~~~

## 3. Exact API: instance and static overloads

With the same method names, the API has **two different overload groups**.

### 3.1 Instance overload: one parent layer

~~~java
ModuleLayer defineModulesWithOneLoader(
        Configuration cf, ClassLoader parentLoader);

ModuleLayer defineModulesWithManyLoaders(
        Configuration cf, ClassLoader parentLoader);
~~~

These are API declarations, not a standalone Java class. When called as follows:

~~~java
ModuleLayer parent = ModuleLayer.boot();
ModuleLayer child =
        parent.defineModulesWithManyLoaders(cf, parentLoader);
~~~

**parent** will be the parent layer of **child**. Configuration must have exactly **one parent configuration corresponding to parent.configuration()**; otherwise, the call may throw IllegalArgumentException.

### 3.2 Static overload: one or more parent layers and Controller

~~~java
static ModuleLayer.Controller defineModulesWithOneLoader(
        Configuration cf,
        List<ModuleLayer> parentLayers,
        ClassLoader parentLoader);

static ModuleLayer.Controller defineModulesWithManyLoaders(
        Configuration cf,
        List<ModuleLayer> parentLayers,
        ClassLoader parentLoader);
~~~

They return **ModuleLayer.Controller**, rather than returning ModuleLayer directly. Obtain the layer with:

~~~java
ModuleLayer.Controller controller =
        ModuleLayer.defineModulesWithOneLoader(
                cf, List.of(parent), parentLoader);

ModuleLayer child = controller.layer();
~~~

With one parent, the resulting layer in terms of module creation corresponds to the instance overload:

~~~java
parent.defineModulesWithOneLoader(cf, parentLoader);
~~~

The static overloads are suitable when you need **multiple parent layers** or the ability to adjust module edges with **Controller.addReads/addExports/addOpens** after creating the layer.

**Important:** the parentLayers list must match the **count, order, and configuration parents** of cf according to the API contract. Do not arbitrarily include another layer just because it has the same module names.

### 3.3 Comparison table

| Property | OneLoader | ManyLoaders |
| --- | --- | --- |
| Number of loaders created | **1 new loader** for all modules in cf | **1 new loader/module** in cf |
| Module → loader mapping | Multiple modules share one loader | Each module has its own loader |
| findLoader of two different modules | **Same ClassLoader object** | **Two different ClassLoader objects** |
| Parent loader | The parentLoader parameter | Same parentLoader parameter for each new loader |
| Delegation between modules | Module-aware direct delegation, including to parent layers | Module-aware direct delegation between the modules' loaders |
| Resource lookup | Searches resources from the layer's modules managed by that loader before parent | Searches resources belonging to the module managed by that loader before parent |
| Package overlap in cf | **Invalid** if multiple modules have the same package | Possible regarding loader mapping, though resolution/readability still imposes constraints |
| Split delegation | May prevent the layer from being created | Distributing modules across multiple loaders may avoid specific one-loader constraints |
| Instance API version | Returns ModuleLayer | Returns ModuleLayer |
| Static API version | Returns Controller | Returns Controller |

**One loader does not mean one module.** A ClassLoader created by OneLoader can define classes from multiple separate named modules. Conversely, ManyLoaders has multiple loaders yet still resides in **one ModuleLayer** and the same configuration graph.

## 4. Parent layer differs from parent ClassLoader

Both parameters contain the word parent, but they **do not have the same effect**:

- **Parent layer** determines **module graph ancestry**: which modules are in parent layers, and which Module objects can be read or looked up along ancestry.
- **parentLoader** is the **parent ClassLoader of the new loader or loaders**, used when a class/resource name does not map to modules that have an appropriate direct delegation path.

Example:

~~~java
ModuleLayer boot = ModuleLayer.boot();

ModuleLayer child =
        boot.defineModulesWithManyLoaders(
                cf,
                ClassLoader.getSystemClassLoader());
~~~

Here:

- The parent **layer** of child is **boot**.
- The parent **loader** of each new loader is the **system/application ClassLoader**.
- A new loader in child can **direct delegate** to another module's loader according to the module graph, rather than only querying parentLoader in the usual parent-first manner.

### 4.1 parentLoader can be null

The Javadoc allows **parentLoader = null**, corresponding to the bootstrap loader. This does not mean newly created loader = null; the API itself still **creates a new ClassLoader**, only with its parent loader being bootstrap.

~~~java
ModuleLayer child =
        boot.defineModulesWithOneLoader(cf, null);
~~~

This is a snippet where cf and boot already exist. **child.findLoader("demo.beta")** still returns a new loader for that module; it does not return null just because null is passed for parentLoader.

### 4.2 parentLoader is not the loader used to define the new modules

A very common misconception:

~~~java
ModuleLayer child =
        boot.defineModulesWithOneLoader(
                cf,
                ClassLoader.getSystemClassLoader());
~~~

From this, it is concluded: “The new modules are defined by the system loader.” **Wrong.** The method creates **a new loader whose parent is the system loader**. Check:

~~~java
ClassLoader created = child.findLoader("demo.beta");
boolean same = created == ClassLoader.getSystemClassLoader();
// same is false for modules defined in the child layer
~~~

When you want to use loaders you created yourself and provide the module → loader mapping, that is a task for **ModuleLayer.defineModules** with a mapping function, not the two convenience methods we are studying.

## 5. How do they handle delegation?

### 5.1 Direct delegation based on module and package

The loaders created by the two convenience APIs **do not rely solely on the traditional parent-first chain**.

When loadClass receives a class name, the loader inspects the **package name** to find the module owning the package in the module graph it knows. If the class maps to another module in the same layer or a module in a parent layer that is appropriately exported according to the graph, it can **direct delegate to that module's ClassLoader**.

If the class name **cannot be mapped to any module**, the loader uses parentLoader.

~~~text
Module loader wants to load "alpha.api.Greeter"
            |
            v
Package "alpha.api" maps to demo.alpha?
            |
            +-- Yes: find loader of demo.alpha
            |          |
            |          v
            |      direct delegation
            |
            +-- No: fallback to parent ClassLoader
~~~

This mechanism allows modules in the layer to read classes from other modules in accordance with **requires/readability and exports** without forcing the loader tree to mirror the module graph identically.

### 5.2 OneLoader still has multiple Module objects

With OneLoader, classes from demo.alpha and demo.beta all have the same defining loader, but:

~~~text
Class alpha.api.Greeter
  -> getModule().getName() = demo.alpha

Class beta.api.Consumer
  -> getModule().getName() = demo.beta

The two Class objects have the same defining loader,
but belong to two different runtime named modules.
~~~

**The same loader does not erase module boundaries.** Readability, exports, opens, and access permissions under JPMS are still enforced.

### 5.3 ManyLoaders: module A calls code of module B

When demo.beta has:

~~~java
requires demo.alpha;
~~~

and demo.alpha exports the package containing Greeter, the loader of demo.beta knows how to delegate to the loader of demo.alpha. There is no need to override loadClass yourself to perform module-aware delegation in the standard case.

**Do not infer that getParent() of demo.beta's loader is demo.alpha's loader.** The two new loaders can share the same parentLoader, while reading classes between modules uses direct delegation based on module mapping.

## 6. Java 17+ Example 1: compiling two named modules

Create the directory structure:

~~~text
project/
├── src/
│   ├── demo.alpha/
│   │   ├── module-info.java
│   │   └── alpha/api/Greeter.java
│   └── demo.beta/
│       ├── module-info.java
│       └── beta/api/Consumer.java
└── LayerCompareDemo.java
~~~

**src/demo.alpha/module-info.java**:

~~~java
module demo.alpha {
    exports alpha.api;
}
~~~

**src/demo.alpha/alpha/api/Greeter.java**:

~~~java
package alpha.api;

public final class Greeter {
    public String hello() {
        return "hello";
    }
}
~~~

**src/demo.beta/module-info.java**:

~~~java
module demo.beta {
    requires demo.alpha;
    exports beta.api;
}
~~~

**src/demo.beta/beta/api/Consumer.java**:

~~~java
package beta.api;

import alpha.api.Greeter;

public final class Consumer {
    public String call() {
        return new Greeter().hello();
    }
}
~~~

In the project directory, using JDK 17+:

~~~bash
javac --module-source-path src -d mods -m demo.alpha,demo.beta
~~~

After this command, the **mods** output directory has two exploded named modules:

~~~text
mods/
├── demo.alpha/
│   ├── module-info.class
│   └── alpha/api/Greeter.class
└── demo.beta/
    ├── module-info.class
    └── beta/api/Consumer.class
~~~

**Do not** add mods to the classpath like **-cp mods** and expect the JVM to treat each subdirectory as a named module. The example will use **ModuleFinder.of(Path.of("mods"))** to resolve the modules at runtime.

### 6.1 Why must module-info.java exist?

Module demo.beta declares **requires demo.alpha**, so Configuration will resolve both modules when the root is demo.beta. Module demo.alpha **exports alpha.api**, allowing Consumer to use Greeter. In the Consumer code, the statement **new Greeter().hello()** is normal Java interaction, but the JVM needs a valid loader mapping and module graph to load Greeter from module alpha.

Simply placing classes in two directories does not create a module dependency; the module descriptor and configuration resolution are what decide it.

## 7. Java 17+ Example 2: same graph, two loader policies

Create the file **LayerCompareDemo.java** right in the project directory:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public class LayerCompareDemo {
    static String runConsumer(ModuleLayer layer) throws Exception {
        ClassLoader loader = layer.findLoader("demo.beta");

        Class<?> type = loader.loadClass("beta.api.Consumer");
        Object instance = type.getConstructor().newInstance();

        return (String) type.getMethod("call").invoke(instance);
    }

    public static void main(String[] args) throws Exception {
        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));
        ModuleLayer parent = ModuleLayer.boot();

        Configuration cf = parent.configuration().resolve(
                finder,
                ModuleFinder.of(),
                Set.of("demo.beta"));

        ModuleLayer one = parent.defineModulesWithOneLoader(
                cf, ClassLoader.getSystemClassLoader());

        ModuleLayer many = parent.defineModulesWithManyLoaders(
                cf, ClassLoader.getSystemClassLoader());

        ClassLoader oneAlpha = one.findLoader("demo.alpha");
        ClassLoader oneBeta = one.findLoader("demo.beta");
        ClassLoader manyAlpha = many.findLoader("demo.alpha");
        ClassLoader manyBeta = many.findLoader("demo.beta");

        System.out.println("one same loader = "
                + (oneAlpha == oneBeta));
        System.out.println("many same loader = "
                + (manyAlpha == manyBeta));

        Class<?> alphaOne = oneAlpha.loadClass("alpha.api.Greeter");
        Class<?> alphaMany = manyAlpha.loadClass("alpha.api.Greeter");

        System.out.println("one alpha module = "
                + alphaOne.getModule().getName());
        System.out.println("many alpha module = "
                + alphaMany.getModule().getName());

        System.out.println("one consumer = " + runConsumer(one));
        System.out.println("many consumer = " + runConsumer(many));

        System.out.println("alpha Class equal across layers = "
                + (alphaOne == alphaMany));

        System.out.println("one loader is new = "
                + (oneAlpha != ClassLoader.getSystemClassLoader()));
    }
}
~~~

Compile and run the **host launcher** in the unnamed module:

~~~bash
javac -d host-out LayerCompareDemo.java
java -cp host-out LayerCompareDemo
~~~

Expected stdout when there are exactly two module artifacts in mods and no competing versions of the classes on the classpath:

~~~text
one same loader = true
many same loader = false
one alpha module = demo.alpha
many alpha module = demo.alpha
one consumer = hello
many consumer = hello
alpha Class equal across layers = false
one loader is new = true
~~~

### 7.1 Explaining each result

**one same loader = true:** both demo.alpha and demo.beta in layer **one** are defined by the same new ClassLoader.

**many same loader = false:** in layer **many**, each named module has its own ClassLoader. The two modules are two elements of the same Configuration, but are mapped to two different loaders.

**one/many alpha module = demo.alpha:** despite the different loader policy, the Greeter class still belongs to the named module demo.alpha. The module → loader mapping does not erase Module identity.

**one/many consumer = hello:** Consumer of demo.beta calls Greeter of demo.alpha successfully. The **requires + exports** module graph is valid. With ManyLoaders, module-aware direct delegation enables the beta loader to retrieve Greeter from the alpha loader.

**alpha Class equal across layers = false:** you created **two separate new layers**, each with its own loader for demo.alpha. Even though the name and bytes of Greeter are the same, the defining loaders are different, so those are two different runtime Classes.

**one loader is new = true:** the system loader parameter is the **parent** of the newly created loader. The layer itself creates a new loader to define its modules.

### 7.2 Why does the code use reflection?

LayerCompareDemo is run in the **unnamed module** on the host classpath and is not compiled with requires demo.beta. Using ClassLoader + reflection helps the launcher find and invoke Consumer after creating the layer at runtime.

**Conditions for reflection to invoke it:** package beta.api is **unconditionally exported** by module demo.beta; Consumer, its constructor, and the call method are public. If the package is not exported or the method is not accessible, reflection from the unnamed module may throw IllegalAccessException or InaccessibleObjectException depending on the operation. This is a module access rule, not a bug caused by OneLoader/ManyLoaders.

### 7.3 Limitations of stdout

The result above applies to the specified files and compile/run commands. If you:

- Rename a package/class or module.
- Place another version of demo.alpha/demo.beta on the module path at JVM launch.
- Add split packages or a new unresolvable dependency.
- Modify module-info exports/requires.

then the result or exception may differ. Do not treat the example as a guarantee that every module graph can be created with both strategies.

## 8. Placing two layers side by side does not automatically make Classes compatible

One ClassLoader is created for layer one and another ClassLoader is created for layer many. The pair:

~~~text
("alpha.api.Greeter", oneLoader)
            !=
("alpha.api.Greeter", manyAlphaLoader)
~~~

represents two class identities.

Consequences:

- A Greeter instance belonging to layer one cannot be automatically cast to Greeter defined by layer many.
- A host type and a type with the same binary name defined by a module in the layer are not automatically compatible.
- Reflection, ServiceLoader, and APIs may need a shared class identity at the boundary.
- Using a **shared Interface/DTO** from a parent/shared loader can help the host and plugins communicate safely, if the module graph/readability/exports allow it.

**Do not confuse two questions:**

1. Within **the same layer**, do two modules have **the same defining loader**?
2. Between **two independent layers**, are the Class objects equal?

OneLoader returns true for question (1) in layer one, but does not make the result of question (2) true.

## 9. Choosing OneLoader: benefits and limitations

### 9.1 When is it suitable?

**defineModulesWithOneLoader** may make sense if:

- A set of modules in the layer is deployed/retired in its lifecycle as **a unified group**.
- There are no overlapping packages among the modules in the configuration.
- The module graph does not create a prohibited split delegation situation.
- You want fewer ClassLoaders and do not need loader isolation between the modules of the group.
- Classes in the same group must still preserve module access boundaries via JPMS.

**One loader can still define multiple modules, and each class still has its own Class.getModule.** Therefore, using OneLoader does not mean losing module names or losing exports/opens.

### 9.2 Overlapping packages are a specific blocker for OneLoader

The Javadoc states that OneLoader **cannot create the layer** if **two or more modules in the configuration contain the same package name**. The fundamental reason: one loader cannot have one package name ambiguously mapped to two modules within that same layer.

Conceptual example:

~~~text
module plugin.a
  contains package plugin.shared

module plugin.b
  contains package plugin.shared

OneLoader for both:
  package plugin.shared -> which module?
  => LayerInstantiationException under OneLoader rules
~~~

**Do not conclude that ManyLoaders always solves every split package.** The resolver may reject the configuration if readability leads to package conflicts, and the module graph/security has other constraints. Mapping each module to its own loader only resolves part of the conflict at the loader level.

### 9.3 Split delegation is another blocker for OneLoader

The Javadoc notes that OneLoader can also fail when the resulting loader would have to **delegate to multiple different loaders for the same package** in parent layers.

~~~text
New layer, ONE loader
       |
       +-- needs package p from parentLoader X
       |
       +-- simultaneously needs package p from parentLoader Y

Cannot consistently map one package p
to two delegation targets in that loader
=> split delegation case, the layer cannot be created
~~~

This is a separate condition distinct from **overlapping packages** within the new configuration itself. When designing a layer, you need to inspect the parent layers' graph, exported packages, and the loader mapping of the modules that the graph will read.

### 9.4 Do not equate fewer ClassLoaders with guaranteed memory savings

OneLoader creates fewer loader objects. However, total application memory also depends on the number of classes, metadata, code, objects, caches, and GC. Do not infer that OneLoader certainly has better throughput/latency/memory across all workloads without actual measurement.

## 10. Choosing ManyLoaders: benefits and limitations

### 10.1 When is it suitable?

**defineModulesWithManyLoaders** is useful when:

- You want each named module to have its **own defining loader**.
- You need to distinguish class ownership by module.
- You want to use multiple loaders while still relying on the JDK's official module-aware delegation.
- You want to avoid having a single loader map multiple incompatible packages/modules.
- You want to design intentional unloading/retention boundaries, while still needing to control the module layer and object references.

**Do not interpret “each module has its own loader” as meaning that all classes in the layer are completely isolated from each other.** Modules still read one another when the requires/exports graph permits, and loaders direct delegate according to the package mapping.

### 10.2 The parent loader is still shared

ManyLoaders creates one loader/module, and **the parent of every new loader is the parentLoader passed in**.

~~~text
parentLoader (e.g. AppLoader)
     ^
     | parent        ^ parent
     |               |
Loader demo.alpha  Loader demo.beta
     |               |
  Greeter            Consumer
       <--- module-aware delegation when needed --->
~~~

In some cases loadClass can direct delegate to another module's loader in the layer; that is not a parent-child relationship between the two new loaders.

### 10.3 When is ManyLoaders unsuitable?

If you want the entire group of modules to use **the exact same loader** for architectural reasons or want a group to form a unified loader scope, ManyLoaders does not meet that requirement.

If the need is simply to use a **custom ClassLoader that you manage yourself**, neither convenience API is an API that directly accepts that ClassLoader as the defining loader. In that case, look at **ModuleLayer.defineModules** with a module name → ClassLoader mapping function and manage delegation yourself in accordance with module readability.

## 11. Instance overload and Controller in real projects

ModuleLayer has both convenient overloads and advanced static overloads.

### 11.1 Only need the layer: instance overload

~~~java
ModuleLayer child =
        ModuleLayer.boot().defineModulesWithOneLoader(
                cf, ClassLoader.getSystemClassLoader());
~~~

Appropriate when you have a suitable parent layer and do not need to hold a Controller.

### 11.2 Need to adjust module edges: static overload

Create the file **LayerControllerDemo.java**, reusing the two modules in the mods directory compiled in section 6:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;

public class LayerControllerDemo {
    public static void main(String[] args) {
        ModuleLayer parent = ModuleLayer.boot();

        Configuration cf = parent.configuration().resolve(
                ModuleFinder.of(Path.of("mods")),
                ModuleFinder.of(),
                Set.of("demo.beta"));

        ModuleLayer.Controller controller =
                ModuleLayer.defineModulesWithManyLoaders(
                        cf,
                        List.of(parent),
                        ClassLoader.getSystemClassLoader());

        ModuleLayer layer = controller.layer();

        Module alpha = layer.findModule("demo.alpha").orElseThrow();
        Module beta = layer.findModule("demo.beta").orElseThrow();
        Module host = LayerControllerDemo.class.getModule();

        System.out.println("layer has 2 modules = "
                + (layer.modules().size() == 2));
        System.out.println("beta reads alpha = "
                + beta.canRead(alpha));

        controller.addReads(beta, host);
        System.out.println("beta reads host after addReads = "
                + beta.canRead(host));

        System.out.println("two different loaders = "
                + (layer.findLoader("demo.alpha")
                        != layer.findLoader("demo.beta")));
    }
}
~~~

Run:

~~~bash
javac -d host-out LayerControllerDemo.java
java -cp host-out LayerControllerDemo
~~~

Expected stdout:

~~~text
layer has 2 modules = true
beta reads alpha = true
beta reads host after addReads = true
two different loaders = true
~~~

**Explanation:** demo.beta requires demo.alpha via requires, so beta.canRead(alpha) is true. **controller.addReads(beta, host)** adds a read edge to the launcher's unnamed module, after which beta.canRead(host) is true. This is an operation that **increases runtime readability** of a module in the layer; it does not redefine classes or change the loader mapping.

**Note on limitations:** only call Controller methods with the modules/conditions permitted by the API. Adding reads/exports/opens affects module encapsulation; do not open packages or add read edges arbitrarily as a way to “fix reflection errors” without intentional design.

### 11.3 Controller.addExports and addOpens differ from addReads

- **addReads(source, target)**: the source module is permitted to read target.
- **addExports(source, packageName, target)**: exports source's package to target at runtime to access public types according to the rules.
- **addOpens(source, packageName, target)**: opens the package to target for deep reflection according to module rules.
- **None of these methods** turns an existing Class into a Class defined by a different loader.
- An added edge does not mean all reflective access automatically becomes valid; member permissions, readability/exports/opens, and the calling code must still be considered.

These methods reside on the **Controller** of a layer defined via the static overload. The instance overload does not return a Controller, so you cannot use a controller from that call itself.

## 12. Combining ModuleFinder, Configuration, and ModuleLayer properly

A standard workflow in a plugin manager:

~~~text
[1] Select module artifact sources
        |
        v
[2] ModuleFinder.of(pluginDirs...)
        |
        v
[3] Choose parent layers and Configuration parents
        |
        v
[4] resolve roots + transitive dependencies
        |
        v
[5] Check module names, packages, graph constraints
        |
        v
[6] Choose OneLoader / ManyLoaders / custom mapping
        |
        v
[7] Define new ModuleLayer
        |
        v
[8] layer.findLoader(moduleName) + loadClass(...)
        |
        v
[9] Start plugin according to its own API/lifecycle
        |
        v
[10] Manage unload/redeployment and references
~~~

**The resolve step before the define step** is important: errors such as missing dependencies, duplicate module names, or package conflicts in the graph usually surface early during module resolution. Loader mapping errors such as OneLoader overlapping packages or split delegation can surface at the layer definition step.

**Do not call defineModulesWithManyLoaders and infer that it automatically downloads module dependencies.** The API uses an already resolved Configuration and the corresponding configuration's finder; the module artifacts must exist and be valid.

## 13. Layer isolation and class identity

These methods are commonly used to create different plugin versions:

~~~text
Host / boot layer
       |
       +-- PluginLayer V1
       |      +-- ClassLoader V1 or loader/module V1
       |
       +-- PluginLayer V2
              +-- ClassLoader V2 or loader/module V2
~~~

A class with the same name in two layers but defined by two different defining loaders **is not the same runtime type**.

This affects:

- **cast/instanceof** between host and plugin objects.
- Reflection when comparing Class objects.
- Method signatures and loader constraints.
- ServiceLoader providers if the service type is not shared via the proper loader.
- Serialization and caches holding objects from an older version.

**Do not use layers as a complete security sandbox.** Module layers and class-loader boundaries provide namespace organization, readability, exports, and loader isolation; they do not by themselves guarantee that untrusted code is isolated from all dangerous APIs.

### 13.1 Shared API boundary

A plugin runtime typically places the shared communication API in a parent/shared module, and plugin implementations in child layers:

~~~text
Shared parent module:
    plugin.api (interface Plugin)

Plugin layer:
    plugin.impl.one -> requires plugin.api
    plugin.impl.two -> requires plugin.api
~~~

The goal is for the host and plugin to see **the same Class plugin.api.Plugin** if the plugin object needs to be cast to the host interface. Do not place a duplicate copy of the API interface into the plugin module/layer and expect the JVM to treat them as one Class merely because their binary names are identical.

## 14. Resource lookup and ModuleLayer

Both types of convenience loaders support resource lookup according to the mechanism stated in the Javadoc:

- **OneLoader:** the new loader searches resources in **the layer's modules** that it defines before searching in parentLoader.
- **ManyLoaders:** each loader searches resources in the **individual module** that it defines before searching in parentLoader.

**Do not equate class delegation with resource search.** Module encapsulation can still restrict non-class resources in named modules. A resource existing in a modular JAR does not necessarily mean ClassLoader.getResource can return a URL if the resource's package does not satisfy the appropriate openness.

For code directly attached to a named module, **Module.getResourceAsStream** or **Class.getResourceAsStream** have their own module-aware rules and may be more suitable than looking up resources arbitrarily from the loader.

If two modules contain a resource with the same name, OneLoader searches across multiple modules it defines; the return order may not be suitable as a configuration policy. You should avoid duplicate names or use an API that identifies the resource's owning module to increase determinism.

## 15. Common errors and causes

### 15.1 ResolutionException when Configuration is invalid

**Source:** the parent.configuration().resolve(...) step, not yet the loader creation step.

May be caused by a required module not being found, unsatisfiable dependency requirements, package conflicts in the graph, or invalid module artifacts.

**How to check:** is the root module name correct, does ModuleFinder.of point to the exact exploded modules/JARs, and are module-info.requires/exports appropriate?

### 15.2 IllegalArgumentException due to mismatched Configuration parent

The instance overload requires cf to have exactly one parent configuration, which is the configuration of the **layer receiver**. The static overload requires parentLayers to match the parents of cf in **order** as well.

This is not an error loading a class from a file, but a **mismatch error between the descriptive graph and the runtime graph**.

### 15.3 LayerInstantiationException due to overlapping packages

If two modules in cf both contain package p and OneLoader is chosen, a single loader cannot map that package to two modules in the same layer. Fix the module packaging/graph or consider ManyLoaders if other readability constraints allow it.

### 15.4 LayerInstantiationException due to split delegation

When a new OneLoader loader must delegate the same package to multiple different loaders in parent layers, the API may refuse to create the layer. Check the package distribution and module exports/reads in the parent graph, rather than looking only at module names in the new layer.

### 15.5 ClassNotFoundException after creating the layer

- Did you use **layer.findLoader with the wrong module name**?
- Is the binary class name missing its package or using slashes?
- Does the class actually reside in that resolved module?
- Is the code loading the class not exported/readable along the appropriate delegation path?
- Are you querying the system loader instead of the new loader returned by findLoader?

Use **Class.getClassLoader** and **Class.getModule** once a Class has been loaded to check its owner.

### 15.6 IllegalAccessException / InaccessibleObjectException

The methods still respect JPMS access. If a package does not export public types to the caller or is not open for reflection, code can load the Class but cannot invoke the constructor/method via reflection as intended. Adjust **module-info** or Controller edges according to the contract; do not treat this as evidence that you need to switch from OneLoader to ManyLoaders.

### 15.7 LinkageError, loader constraints, and ClassCastException

If the host and plugin do not share the API Class properly, identical names can still lead to two different runtime types. Inspect the defining loaders and the module graph. When the JVM needs to unify a type in a signature, a linkage error may surface.

### 15.8 Module name in configuration already present in parent?

ModuleLayer.findModule searches in the layer and parent layers, but resolution also has its own policies regarding module names. You should not assume that to get a new module version you just reuse a module name already on the parent graph regardless of constraints. Clearly define parent configurations, artifact versions, and layering intent; avoid conflicts during graph resolution.

### 15.9 Classes do not unload even after dropping references to the layer

Creating a ModuleLayer can create loader objects holding many definitions. **Class unloading depends on the reachability of the defining loaders**; merely clearing the local layer variable does not automatically guarantee GC/unloading. If a Thread context loader, plugin instances, service providers, callbacks, or caches still hold references to the loaders/modules, old versions may remain alive.

## 16. When to choose OneLoader, when ManyLoaders?

| Design question | Primary consideration |
| --- | --- |
| Multiple modules, but you want them to share one loader? | **OneLoader** |
| Want clear ownership per module, one loader/module? | **ManyLoaders** |
| Multiple modules have the same package in the configuration? | **OneLoader is invalid**; ManyLoaders depends on the graph/readability |
| Risk of split delegation in a single loader? | Consider **ManyLoaders** or redesign the graph |
| Want to use your existing custom ClassLoaders directly? | **defineModules** with a mapping function, not the two convenience APIs |
| Need to adjust reads/exports/opens after creating the layer? | Use the **static overload returning Controller** |
| Want the boot parent layer, but with the application loader as the parent loader? | Both methods support this |
| Just want to load a simple modular JAR at startup? | Consider **--module-path** and the JPMS launcher before creating a layer yourself |
| Want to manage plugin versions/redeploy? | New layer, loader identity, API boundary, and clear lifecycle |
| Want guaranteed memory reduction? | Measure in practice; fewer loaders do not automatically guarantee better performance |

**Rule:** choose based on the **module-to-loader mapping you actually want**, not based on the number of modules or a feeling that “many seems better”.

## 17. Knowledge self-check

**Question 1.** What loader does defineModulesWithOneLoader create?

**Answer:** Creates one **new ClassLoader** for all modules in Configuration, with the passed parentLoader as its parent.

**Question 2.** Does defineModulesWithManyLoaders make demo.beta use demo.alpha's loader as its parent?

**Answer:** No. Each new loader has the passed parentLoader as its parent; cross-module communication uses direct delegation according to the package/module graph.

**Question 3.** Why is one.findLoader("demo.alpha") == one.findLoader("demo.beta") true?

**Answer:** Both modules are defined into the same new loader in layer one.

**Question 4.** If they share the same loader, are the two modules still independent regarding JPMS exports/reads?

**Answer:** Yes. Separate Module objects and the module graph are still enforced by the JVM.

**Question 5.** Why is alphaOneClass == alphaManyClass false?

**Answer:** Two different layers have different defining loaders even though the binary name/bytes are identical.

**Question 6.** What do the instance overload and the static overload return?

**Answer:** Instance returns ModuleLayer; static returns ModuleLayer.Controller, from which you get the layer via controller.layer().

**Question 7.** Is parentLoader the loader that defines classes in the new layer?

**Answer:** No. The method creates a new loader whose parent is parentLoader.

**Question 8.** Why can OneLoader fail when two modules use the same package p?

**Answer:** One loader cannot map the same package to two modules of the same layer; the Javadoc specifies that overlapping packages cause LayerInstantiationException.

**Question 9.** Does ManyLoaders guarantee that every split package is valid?

**Answer:** No. Configuration resolution/readability may still reject conflicts; giving each module its own loader only changes part of the conditions.

**Question 10.** How does a loader from ManyLoaders find a class in another module?

**Answer:** Direct delegation based on the package-to-module mapping and the exports/reads graph, not necessarily via getParent().

**Question 11.** What should you use if you want to add a read edge at runtime?

**Answer:** The static overload taking parentLayers and returning Controller, followed by controller.addReads according to the contract.

**Question 12.** Why can ModuleFinder.of(...) not be viewed as having already loaded classes?

**Answer:** ModuleFinder only finds module definitions, Configuration resolves the graph, ModuleLayer defines runtime modules, and class loading occurs when a class is requested.

## 18. Key takeaways

~~~text
MODULE ARTIFACTS
       |
       v
ModuleFinder.of(...)
       |
       v
Configuration.resolve(... roots ...)
       |
       v
ModuleLayer.boot()
       |
       +-- defineModulesWithOneLoader
       |      -> 1 new ClassLoader for N modules
       |
       +-- defineModulesWithManyLoaders
              -> N new ClassLoaders for N modules
                   |
                   +-- direct delegation between modules
                       per graph when needed
~~~

- **ModuleLayer** is a runtime graph of named modules and a module-to-loader mapping.
- **OneLoader**: multiple modules share a loader, yet still have separate modules and JPMS access rules.
- **ManyLoaders**: each module has its own loader, and can still delegate directly according to the module graph.
- **parentLayer** determines module ancestry, while **parentLoader** is the parent of the new loaders.
- **The instance API returns ModuleLayer; the static API returns Controller.**
- One loader holding multiple modules must avoid **overlapping packages** and prohibited **split delegation**.
- Use **findLoader** and **Class.getModule/getClassLoader** to inspect the runtime, instead of guessing from file/JAR paths.
- A new layer does not automatically guarantee unloading of the old layer; you must manage strong references, threads, and the plugin lifecycle.

### Official sources

- Java SE 21 **ModuleLayer API**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html
- Java SE 21 **ModuleLayer.Controller API**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.Controller.html
- Java SE 21 **Configuration API**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/Configuration.html
- Java SE 21 **ModuleFinder API**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleFinder.html
- Java SE 21 **Module API**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html
- Java SE 21 **JPMS specification (JLS §7)**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html
