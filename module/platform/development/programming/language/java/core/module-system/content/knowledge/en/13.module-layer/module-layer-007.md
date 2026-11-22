# Parent Layers and Module Readability

In the Java Platform Module System (JPMS), `ModuleLayer` allows an application to define additional named modules after the JVM has started. A new layer can have one or more parent layers. This organization is very useful for plugin systems, developer tools, applications that extend functionality on demand, and systems that need to separate modules into runtime groups.

An important point that is often misunderstood is: **Having a parent layer does not mean every module in the child layer automatically reads every module in the parent.**

Let us distinguish three kinds of relationships:

- **Parent layer:** which parent layers' configurations is the child layer built on top of?
- **Module readability:** does module A have a read relationship to module B?
- **Class loader and accessibility:** where are classes loaded from, and have packages been properly exported or opened?

The parent relationship enables modules in the child layer to reference modules already defined in ancestor layers when the graph permits. However, read permission is not determined merely by two modules belonging to parent and child layers.

## Objectives

After this lesson, you can:

- Explain `ModuleLayer.boot()` and the difference between parent and child layers.
- Distinguish `layer.parents()`, `layer.modules()`, and `layer.findModule()`.
- Understand `Configuration.resolve()` and a readability graph with read edges to modules in parent configurations.
- Distinguish a successful lookup from actual read permission via `Module.canRead()`.
- Create a plugin layer with `defineModulesWithOneLoader()`.
- Use `ModuleLayer.Controller.addReads()` within its proper scope.
- Separate the roles of `requires`, `requires transitive`, `exports`, `opens`, and class loaders.
- Diagnose errors that occur when loading modules from another layer.

## 1. What Is a ModuleLayer?

A `ModuleLayer` contains `Module` objects defined from a resolved `Configuration`. Each named module belongs to a specific layer at runtime.

The JVM has a boot layer created at startup:

~~~java
ModuleLayer boot = ModuleLayer.boot();
~~~

The boot layer contains `java.base` and other modules resolved for that launch. When an application needs to load a plugin, it can create a new layer using the boot layer as its parent:

~~~text
              BOOT LAYER (parent)
          +-------------------------+
          | java.base               |
          | java.logging            |
          | java.sql                |
          | ...                     |
          +-------------------------+
                      ^
                      | parent layer
                      |
          +-------------------------+
          | CHILD PLUGIN LAYER      |
          | com.acme.plugin         |
          +-------------------------+
~~~

The diagram above only describes the **placement** of modules. It does not yet say which modules `com.acme.plugin` can read.

### 1.1. Why Do We Need a Parent Layer?

A plugin may depend on APIs that already exist in the boot layer, such as `java.logging` or an SPI module provided by the main application. When resolving the plugin, Java can reuse the modules already present in the parent configuration instead of redefining them in the child.

The parent layer also provides an ancestor lookup chain so the application can query modules by name.

### 1.2. A Layer Is a Set of Modules, Not a Class Loader

A layer can define all modules with a single loader or map each module to its own loader. Conversely, a class loader is not a module layer.

The three common factories are:

~~~java
parent.defineModulesWithOneLoader(configuration, parentLoader);

parent.defineModulesWithManyLoaders(configuration, parentLoader);

parent.defineModules(configuration, moduleNameToLoader);
~~~

Sharing a loader does not merge modules into a single module. Each module still has its own descriptor, name, and access permissions.

## 2. From Configuration to ModuleLayer

`Configuration` is the result of module resolution and describes the readability graph among resolved modules. This graph has `ResolvedModule` nodes and edges indicating read relationships.

One way to resolve a plugin based on the boot configuration:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

ModuleLayer boot = ModuleLayer.boot();

ModuleFinder pluginFinder =
    ModuleFinder.of(Path.of("plugins"));

Configuration childConfig =
    boot.configuration().resolve(
        pluginFinder,
        ModuleFinder.of(),
        Set.of("com.acme.plugin")
    );
~~~

The components:

- `boot.configuration()` is the parent configuration.
- `pluginFinder` locates new modules from the JAR directory.
- `ModuleFinder.of()` in the example is an empty finder in the `after` position.
- `Set.of("com.acme.plugin")` contains the new root module to resolve.

If the plugin declares `requires java.logging;` and logging is already in the parent configuration, the resolver creates a read edge from the plugin to logging in the parent. Java does not need to create a duplicate copy of the logging module in the child configuration.

### 2.1. Inspecting the Graph at the Configuration Level

Before creating the layer, you can list the new modules and their read edges:

~~~java
childConfig.modules().forEach(module -> {
    System.out.println("Module: " + module.name());

    module.reads().forEach(target ->
        System.out.println("  reads: " + target.name())
    );
});
~~~

The modules being read may reside in the child configuration **or** in a parent configuration.

### 2.2. Parent Configuration Must Match Parent Layer

When defining a layer with the static API:

~~~java
ModuleLayer.Controller controller =
    ModuleLayer.defineModulesWithOneLoader(
        childConfig,
        List.of(boot),
        ClassLoader.getSystemClassLoader()
    );
~~~

`List.of(boot)` must correspond to the parent configuration used during resolution. If a configuration has multiple parents, the order of parent layers must match the order of parent configurations.

If the parent layers do not match, the API may throw `IllegalArgumentException`.

## 3. Parent Layer and Read Edge Are Two Different Things

Suppose:

~~~text
Parent configuration:
  java.base
  java.logging
  java.sql

Child configuration:
  com.acme.plugin
~~~

The plugin descriptor is:

~~~java
module com.acme.plugin {
    requires java.logging;
}
~~~

The runtime read graph is essentially:

~~~text
com.acme.plugin  --->  java.logging
         |
         +------->     java.base
~~~

Meanwhile `java.sql` may belong to the boot layer, yet the plugin does **not** have a read edge to SQL.

There is no contradiction here. Parent refers to **layer structure**; readability refers to the **module graph**.

### 3.1. ModuleLayer.findModule()

~~~java
Module sql = childLayer.findModule("java.sql")
    .orElseThrow();
~~~

`findModule` searches the current layer and then the parent layers. If SQL is in the boot layer and boot is the parent of child, the call above can succeed.

However, finding the module does not mean the plugin module is allowed to reference SQL types in ordinary Java bytecode.

### 3.2. Module.canRead()

~~~java
boolean readable = pluginModule.canRead(sqlModule);
~~~

`canRead()` checks readability from the calling module to the target module at runtime.

Example:

~~~text
child.findModule("java.sql").isPresent()  -> true

plugin.canRead(javaSqlModule)             -> false
~~~

This is the core example: **a module is found from the parent, yet is not read by the child module**.

### 3.3. Readability Is Directional

`A.canRead(B)` is a directional relationship; it does not imply `B.canRead(A)`.

~~~text
com.acme.plugin ---> java.logging

plugin.canRead(logging)  = true
logging.canRead(plugin)  = false (unless there is a reverse relationship)
~~~

A parent module does not automatically read new modules defined in a child layer.

## 4. Runnable Example: A Plugin Layer Reading Part of the Boot Layer

The example uses:

- A host running on the classpath, without directly importing plugin classes.
- An explicit named module `com.acme.plugin` packaged as a JAR.
- The boot layer containing `java.logging` and `java.sql`.
- The plugin requiring logging, but not requiring SQL.

Directory structure:

~~~text
layer-demo/
├── Host.java
├── src/
│   └── com.acme.plugin/
│       ├── module-info.java
│       └── com/acme/plugin/api/PluginEntry.java
├── plugins/
└── out/
~~~

### 4.1. Plugin Module Descriptor

File `src/com.acme.plugin/module-info.java`:

~~~java
module com.acme.plugin {
    requires java.logging;
    exports com.acme.plugin.api;
}
~~~

The plugin is permitted to read the `java.logging` module, and its API package is exported. There is no `requires java.sql;` line.

### 4.2. PluginEntry Code

File `src/com.acme.plugin/com/acme/plugin/api/PluginEntry.java`:

~~~java
package com.acme.plugin.api;

import java.util.logging.Logger;

public final class PluginEntry {
    private PluginEntry() {
    }

    public static void start() {
        Logger.getLogger(PluginEntry.class.getName())
              .info("Plugin started");
    }
}
~~~

This class shows that the plugin genuinely depends on logging's public API.

### 4.3. Host.java

Create file `Host.java` in the `layer-demo` directory:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;

public class Host {
    public static void main(String[] args) {
        ModuleLayer boot = ModuleLayer.boot();

        ModuleFinder finder =
            ModuleFinder.of(Path.of("plugins"));

        Configuration config =
            boot.configuration().resolve(
                finder,
                ModuleFinder.of(),
                Set.of("com.acme.plugin")
            );

        ModuleLayer.Controller controller =
            ModuleLayer.defineModulesWithOneLoader(
                config,
                List.of(boot),
                ClassLoader.getSystemClassLoader()
            );

        ModuleLayer child = controller.layer();

        Module plugin = child.findModule("com.acme.plugin")
            .orElseThrow();

        Module logging = boot.findModule("java.logging")
            .orElseThrow();

        Module sql = boot.findModule("java.sql")
            .orElseThrow();

        System.out.println("Parent is boot: "
            + (child.parents().get(0) == boot));

        System.out.println("Child finds SQL: "
            + child.findModule("java.sql").isPresent());

        System.out.println("Boot finds plugin: "
            + boot.findModule("com.acme.plugin").isPresent());

        System.out.println("Plugin reads logging: "
            + plugin.canRead(logging));

        System.out.println("Plugin reads SQL before: "
            + plugin.canRead(sql));

        System.out.println("Logging reads plugin: "
            + logging.canRead(plugin));

        controller.addReads(plugin, sql);

        System.out.println("Plugin reads SQL after: "
            + plugin.canRead(sql));
    }
}
~~~

The application uses `child.findModule()` and `Module.canRead()` to separate the two kinds of checks. At the end of the example, the controller adds a read edge from the plugin to SQL.

### 4.4. Compiling and Packaging

From the `layer-demo` directory:

~~~bash
javac --module-source-path src -d out -m com.acme.plugin
~~~

Create the plugin directory if it does not exist yet:

~~~bash
mkdir plugins
~~~

Package the modular JAR:

~~~bash
jar --create --file plugins/com.acme.plugin.jar \
    -C out/com.acme.plugin .
~~~

If using Windows PowerShell, you can write it on one line:

~~~powershell
jar --create --file plugins/com.acme.plugin.jar -C out/com.acme.plugin .
~~~

Compile Host:

~~~bash
javac -d host-out Host.java
~~~

### 4.5. Running the Example

~~~bash
java --add-modules java.logging,java.sql \
     -cp host-out Host
~~~

On Windows PowerShell:

~~~powershell
java --add-modules java.logging,java.sql -cp host-out Host
~~~

`--add-modules java.logging,java.sql` ensures the two JDK modules are resolved into the boot layer, so `boot.findModule()` can find them.

The plugin JAR is **not** placed on the module path of this launch command. Host will locate the plugin in the `plugins` directory using `ModuleFinder.of()` and define the new layer at runtime.

### 4.6. Illustrative Output

~~~text
Parent is boot: true
Child finds SQL: true
Boot finds plugin: false
Plugin reads logging: true
Plugin reads SQL before: false
Logging reads plugin: false
Plugin reads SQL after: true
~~~

Interpretation:

1. Child has boot as its parent.
2. Child finds SQL because `findModule()` searches in the parent.
3. Boot does not automatically look downward into child.
4. Plugin reads logging thanks to `requires java.logging;`.
5. Plugin does not automatically read SQL even though SQL is in the parent.
6. Logging does not automatically read back to plugin.
7. `addReads(plugin, sql)` adds a read edge at runtime.

This output shows precisely why you must distinguish **finding a module** from **module readability**.

## 5. How Does ModuleLayer.Controller.addReads() Work?

When creating a layer via a static factory, the return value is `ModuleLayer.Controller`:

~~~java
ModuleLayer.Controller controller =
    ModuleLayer.defineModulesWithOneLoader(
        config,
        List.of(boot),
        ClassLoader.getSystemClassLoader()
    );

ModuleLayer layer = controller.layer();
~~~

The controller can adjust certain runtime relationships of the modules defined in the layer it controls.

Important APIs:

| API | Meaning |
|---|---|
| `controller.layer()` | Gets the new layer |
| `controller.addReads(source, target)` | Adds a read edge from source to target |
| `controller.addExports(source, packageName, target)` | Exports a package of source to target |
| `controller.addOpens(source, packageName, target)` | Opens a package of source for deep reflection from target |

`source` must be a module belonging to the layer managed by the controller when making the corresponding changes. A child layer's controller does not automatically have permission to modify every module in the boot layer.

### 5.1. addReads Does Not Modify module-info.java

Example:

~~~java
controller.addReads(plugin, sql);
~~~

This can flip `plugin.canRead(sql)` from `false` to `true`.

However:

- The `module-info.class` file inside the JAR does not change.
- The compiler is not re-run.
- New dependencies are not automatically added to the build.
- Code importing SQL APIs at compile time still requires valid compile-time readability.

If SQL is a fixed dependency that the plugin uses directly, the sustainable design is to declare:

~~~java
module com.acme.plugin {
    requires java.sql;
}
~~~

rather than relying on a runtime patch for a dependency that belongs in the descriptor.

### 5.2. addReads Does Not Fix Every Error

A new read edge does not automatically:

- Find and resolve a module that does not exist in the configuration.
- Export internal packages of the target module.
- Open private fields for deep reflection.
- Fix class loader errors or missing classes/JARs.
- Replace a security mechanism for running untrusted plugins.

That is why `addReads` should be used for intentional dynamic integration scenarios.

## 6. Requires and requires transitive Across Layer Boundaries

Suppose the parent layer contains:

~~~text
com.acme.spi
com.acme.model
~~~

The SPI module has the descriptor:

~~~java
module com.acme.spi {
    requires transitive com.acme.model;
    exports com.acme.spi;
}
~~~

The plugin in the child layer has:

~~~java
module com.acme.plugin {
    requires com.acme.spi;
}
~~~

Readability can propagate from plugin to model thanks to `requires transitive` in the SPI descriptor.

~~~text
com.acme.plugin
       |
       | requires
       v
com.acme.spi
       |
       | requires transitive
       v
com.acme.model
~~~

The propagation can cross into the parent configuration; it does not require all modules to be in the same layer.

### 6.1. Additional Condition: exports

If the plugin uses a public type from `com.acme.model`, the package containing that type must still be appropriately exported. `requires transitive` grants readability to the module, **not automatic export of every package** in the read module.

### 6.2. requires static

With:

~~~java
module com.acme.plugin {
    requires static com.acme.optional;
}
~~~

the optional module is needed at compile time, but may not be resolved at runtime if not actually required. The parent layer is not guaranteed to contain the optional module. Inspect the actual graph rather than assuming the parent always provides every dependency seen in the build environment.

## 7. Read Relationships Differ from exports and opens

Two modules can have a read edge and still fail class access.

Suppose a contract module in the parent has:

~~~java
module com.acme.contract {
    exports com.acme.contract.api;
}
~~~

Plugin:

~~~java
module com.acme.plugin {
    requires com.acme.contract;
}
~~~

The plugin can use eligible public types in `com.acme.contract.api`. However, if it imports a class from `com.acme.contract.internal` and contract does not export that package, the compiler can reject it.

### 7.1. Qualified export

A parent module can export a package only to the plugin:

~~~java
module com.acme.contract {
    exports com.acme.contract.spi to com.acme.plugin;
}
~~~

The list after `to` consists of **module names**, not layer names or class loaders. A qualified export does not automatically create readability, so the plugin still needs a valid read relationship.

### 7.2. Opens for Deep Reflection

If a framework needs to access non-public members:

~~~java
module com.acme.contract {
    opens com.acme.contract.model to com.acme.framework;
}
~~~

`opens` serves reflective access; `exports` serves public API access. Both are independent of the parent/child layer structure.

### 7.3. Comparison Table

| Question | Mechanism that answers it |
|---|---|
| Which parents does layer A have? | `ModuleLayer.parents()` |
| Is module named X in this layer/ancestor? | `ModuleLayer.findModule(name)` |
| Can module A read B? | `Module.canRead(B)` |
| Is a package exposed for modules to use? | `exports` and access modifiers |
| Is deep reflection into a package allowed? | `opens` or opening the package appropriately |
| Which loader loaded a class? | `Module.getClassLoader()` / `ModuleLayer.findLoader()` |

Do not substitute one check for another.

## 8. Parent Layer Differs from Parent Class Loader

In the factory:

~~~java
ModuleLayer.defineModulesWithOneLoader(
    config,
    List.of(boot),
    ClassLoader.getSystemClassLoader()
);
~~~

The last two arguments serve different purposes:

- `List.of(boot)` specifies the parent layer.
- `ClassLoader.getSystemClassLoader()` specifies the parent class loader of the newly created loader.

The layer hierarchy belongs to the JPMS model. Class-loader delegation belongs to the class-loading mechanism. The two mechanisms interact at runtime, but they are not the same graph.

For example, a class loader may locate a class belonging to a parent loader, yet that does not mean the running module always has permission to access that class under JPMS.

### 8.1. One-loader and many-loaders

| Method | Module mapping |
|---|---|
| `defineModulesWithOneLoader` | New modules share one class loader |
| `defineModulesWithManyLoaders` | Each new module has its own class loader |
| `defineModules` | Application provides a module name → loader mapping |

Whether using one loader or many loaders, modules still preserve their own readability and package access boundaries.

### 8.2. Class Loading Errors Are Not the Same as Missing Read Edges

`ClassNotFoundException` can come from a loader failing to find a class. `NoClassDefFoundError` can appear when the runtime cannot load/link a dependent class. `IllegalAccessError` can relate to module access rights or Java access modifiers.

When debugging, separate the order:

1. Was the module resolved?
2. Does the class exist in the right artifact?
3. Which loader is being used?
4. Does the module have appropriate readability?
5. Is the package appropriately exported/opened?

## 9. Instance Method vs Static Method for Creating a Layer

There are two common ways when using only one parent.

### 9.1. Instance Method

~~~java
ModuleLayer child =
    boot.defineModulesWithOneLoader(
        config,
        ClassLoader.getSystemClassLoader()
    );
~~~

This method returns a `ModuleLayer` directly, and the receiver `boot` is the parent layer.

### 9.2. Static Method

~~~java
ModuleLayer.Controller controller =
    ModuleLayer.defineModulesWithOneLoader(
        config,
        List.of(boot),
        ClassLoader.getSystemClassLoader()
    );

ModuleLayer child = controller.layer();
~~~

The static method lets you pass a list of parent layers and returns a controller for managing runtime module relationships.

If you do not need to adjust reads/exports/opens, the instance method is usually more concise in the single-parent case.

## 10. Multi-Level and Multi-Parent Layers

The layer graph can have multiple levels:

~~~text
        Boot
          ^
          |
    Shared API layer
          ^
          |
      Plugin layer
~~~

In this case, the plugin can look up modules from both the shared API layer and the boot layer using `findModule()` because the lookup traverses the chain of ancestor layers.

However, whether the plugin reads a specific ancestor module still depends on the readability graph or a valid runtime change.

### 10.1. More Than One Parent

The static factories accept:

~~~java
List<ModuleLayer> parents =
    List.of(firstParent, secondParent);
~~~

When there are multiple parents, the configuration must be created with the corresponding parent configurations in the exact same order. You cannot arbitrarily add a parent layer at define time if the configuration was not resolved from that parent.

A layer with multiple parents does not cause all modules of those parents to be merged into one module.

### 10.2. Search Goes from Child Up to Parent

~~~java
child.findModule("com.acme.plugin");
child.findModule("java.logging");
~~~

This can find the plugin and logging modules if they lie in the appropriate child/ancestor.

Conversely:

~~~java
boot.findModule("com.acme.plugin");
~~~

does not automatically search all descendant layers. An application managing plugins should retain references to the layers it creates.

## 11. ServiceLoader in a Child Layer

A practical pattern is placing the SPI module in the parent layer and the implementation in the child layer:

~~~text
Parent layer:
  com.acme.spi (interface Greeter)

Child layer:
  com.acme.greeter.impl (provider implementation)
~~~

Provider descriptor:

~~~java
module com.acme.greeter.impl {
    requires com.acme.spi;

    provides com.acme.spi.Greeter
        with com.acme.greeter.impl.DefaultGreeter;
}
~~~

The host can use:

~~~java
ServiceLoader<Greeter> providers =
    ServiceLoader.load(childLayer, Greeter.class);
~~~

With an appropriate design, ServiceLoader can discover providers defined in the child layer without the host needing to import the implementation class directly.

Conditions to watch:

- The SPI API is exported by the module that owns it.
- The provider module has a read relationship to the SPI.
- The provider is defined in the appropriate layer.
- The caller's module declares `uses` if it is a named module and consumes the service via the corresponding API.
- Avoid confusing “parent does not read child” with not being able to discover providers via ServiceLoader.

## 12. Common Errors When Creating Parent/Child Layers

### 12.1. Configuration Does Not Match Parent

Symptom: `IllegalArgumentException` when calling the factory.

Cause: the configuration was resolved with parent configuration A, yet at define time a layer with a different configuration was passed.

Fix: track the exact parent configurations at resolution time and pass the corresponding parent layers, preserving order if there are multiple parents.

### 12.2. Module Not Found During Resolution

Example:

~~~text
java.lang.module.FindException:
Module com.acme.contract not found,
required by com.acme.plugin
~~~

Check:

- Is the contract module in the parent configuration?
- Does the finder search the contract in the supplied module path/directory?
- Is the module name exact?
- Does the artifact contain a valid `module-info.class`?

You cannot use `addReads()` to fix an error when the configuration has not resolved successfully.

### 12.3. findModule Succeeds but canRead Is False

This is not necessarily a bug. It simply shows that the module can be located through the layer structure, yet has no read edge in the current graph.

Check `requires`, `requires transitive`, and whether a runtime read edge needs to be added.

### 12.4. Reading the Module but Unable to Access the Package

If the target module does not export the package to the plugin, `canRead() == true` is not enough.

Check descriptors and access modifiers. If deep reflection is needed, verify the package/module is opened via `opens` or an equivalent mechanism.

### 12.5. Module Loader Cannot Find Class

If the factory creates the layer successfully but cannot load the entry point:

- Check whether the JAR file contains the class under the package path.
- Check the loader returned by `child.findLoader("com.acme.plugin")`.
- Check that you are using the right layer/loader instead of accidentally using the system class loader.
- Distinguish class loading errors from readability and package accessibility errors.

## 13. Diagnostic Tools and APIs

### 13.1. Inspecting the Descriptor of a Plugin JAR

~~~bash
jar --describe-module --file plugins/com.acme.plugin.jar
~~~

This tool helps confirm the module name, `requires`, and `exports` actually contained in the artifact.

### 13.2. Viewing Module Resolution in the Boot Layer

~~~bash
java --show-module-resolution \
     --add-modules java.logging,java.sql \
     -cp host-out Host
~~~

This option displays the graph during startup. Graphs created later inside `Host.main()` do not automatically appear in full in the initial startup output.

### 13.3. Viewing Modules Belonging Directly to Child

~~~java
child.modules().forEach(module ->
    System.out.println(module.getName())
);
~~~

`child.modules()` only returns modules defined directly in child, not all modules in the parent.

### 13.4. Viewing Modules Read by the Child Configuration

~~~java
child.configuration().modules().forEach(module -> {
    System.out.println(module.name());

    module.reads().forEach(target ->
        System.out.println("  -> " + target.name())
    );
});
~~~

This is the graph from the resolution phase, useful for comparing against `Module.canRead()` at runtime.

### 13.5. Viewing Class Loader and Layer

~~~java
System.out.println(plugin.getLayer());
System.out.println(plugin.getClassLoader());
System.out.println(child.parents());
~~~

These APIs help determine which layer a module belongs to and which class loader it uses. They do not replace readability checks.

## 14. Workflow for Designing a Plugin Layer

To design a manageable module layer system:

1. Identify shared APIs/SPIs and place them in stably managed modules in a parent layer.
2. Write the plugin descriptor with `requires` pointing to the right API modules.
3. Export only the plugin API packages that truly need to be exposed.
4. Package the plugin as a modular JAR with a clear module name.
5. Create a `ModuleFinder` from the directory containing plugins.
6. Resolve the child configuration based on the intended parent layer's configuration.
7. Define the layer using the appropriate factory and corresponding parent layers.
8. Verify `layer.modules()`, `layer.parents()`, and `Module.canRead()`.
9. Check exports/opens and how the host locates the entry point or service providers.
10. Only use Controller to adjust runtime relationships when there is a clear architectural reason.

Do not create layers solely to bypass module encapsulation. Layers help organize and dynamically load modules; they are not a security sandbox.

## 15. Misconceptions to Avoid

| Misconception | Correct understanding |
|---|---|
| Child layer reads every module in parent | No. Readability follows the graph or runtime changes |
| `findModule()` succeeding means `canRead()` is true | No. Lookup differs from readability |
| Class loader finding a class means permission to use it | No. Accessibility can still be denied by JPMS |
| One class loader for multiple modules makes the module graph meaningless | No. Named modules still have their own descriptors |
| `addReads()` fixes every module path error | No. It cannot find missing modules |
| `addReads()` automatically exports all packages | No. Exports/opens are separate mechanisms |
| Parent module automatically reads child modules | No. Readability is directional |
| ModuleLayer automatically isolates untrusted plugins | No. Proper security architecture is needed |

## 16. Self-Check Questions

**Question 1.** A child layer has boot as its parent, and `child.findModule("java.sql")` returns a module. Can the plugin definitely read SQL?

**Answer:** No. `findModule()` looks up the module; `plugin.canRead(sql)` checks readability.

**Question 2.** A plugin declares `requires java.logging;` and logging is in the parent configuration. Can the plugin read logging?

**Answer:** Yes. Graph resolution creates a read relationship to the logging module in the parent.

**Question 3.** Does the plugin being able to read logging mean logging reads the plugin back?

**Answer:** No. Readability is a directional relationship.

**Question 4.** To get the set of modules belonging directly to the child layer, what should you use?

**Answer:** `child.modules()`, rather than `child.findModule()`, because findModule can also search ancestors.

**Question 5.** What does the static factory `ModuleLayer.defineModulesWithOneLoader` return?

**Answer:** `ModuleLayer.Controller`; call `controller.layer()` to obtain the created layer.

**Question 6.** Does `controller.addReads(plugin, sql)` modify the plugin's `module-info.java`?

**Answer:** No. It creates a read edge at runtime, does not modify the descriptor, and does not make source that originally lacked `requires` compile beforehand.

**Question 7.** The plugin can read contract, yet the compiler/runtime rejects an internal package. Why?

**Answer:** Contract may not have exported that package to the plugin, or the class/member may lack sufficient access permissions. Readability does not replace exports.

**Question 8.** Are parent class loader and parent layer the same?

**Answer:** No. Parent layer relates to the structure of module configurations; parent class loader relates to delegation when loading classes.

**Question 9.** Why must you keep the exact order of parent layers when creating a multi-parent layer?

**Answer:** Because the list must correspond to the parent configurations used during resolution.

**Question 10.** Can a provider module in a child supply a service to a host using an SPI in the parent without the host directly importing the provider class?

**Answer:** It can be designed via `ServiceLoader.load(childLayer, ServiceType.class)` with proper module/SPI/provider configuration.

## Summary

When working with multiple `ModuleLayer` instances in JPMS, clearly distinguish:

- **Parent layer:** organizes groups of modules and allows searching across ancestors.
- **Readability graph:** determines which module has read edges to which modules, including edges from child to parent.
- **Package accessibility:** `exports`, `opens`, and Java rules govern API usage and reflection.
- **Class loading:** determines where classes are loaded from, without automatically replacing module access rules.

A useful diagnostic workflow is: **identify the layer containing the module → check parent configurations → check whether the module is resolved → check `findModule()` → check `canRead()` → check exports/opens → check class loader**. Understanding these layers properly helps build stable plugin layers without relying on false assumptions about parent–child layer relationships.