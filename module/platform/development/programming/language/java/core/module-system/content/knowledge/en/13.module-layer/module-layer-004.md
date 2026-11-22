# defineModulesWithOneLoader

In the Java Platform Module System (JPMS), a Configuration describes a set of resolved modules and their dependency relationships. For those modules to participate at runtime, Java must define them in a ModuleLayer and associate them with class loaders.

The ModuleLayer.defineModulesWithOneLoader() method creates a new layer and defines all modules in the supplied configuration using a single shared class loader. This organization is suitable when loading a closely related group of modules, such as a plugin together with its supporting modules.

## Objectives

After this lesson, you can:

- Explain the role of defineModulesWithOneLoader() in the module layer creation workflow.
- Distinguish parent configuration, parent module layer, and parent class loader.
- Create a configuration from a module finder and then define a layer with one loader.
- Retrieve modules and the class loader from the new layer.
- Understand the role of ModuleLayer.Controller.
- Compare one-loader with many-loaders and choose an appropriate approach for plugins.

## 1. ModuleLayer and Class Loaders

A resolved module graph does not mean the modules' classes have been loaded into the runtime. Once you have a Configuration, the application can define the modules in a ModuleLayer.

~~~text
ModuleFinder
    |
    v
Configuration.resolve(...)
    |
    v
Resolved module graph
    |
    v
ModuleLayer.defineModulesWithOneLoader(...)
    |
    v
New ModuleLayer
    |
    v
Modules defined with one class loader
~~~

Three concepts to distinguish:

- **Configuration:** the set of resolved modules along with dependencies and parent configurations.
- **ModuleLayer:** the set of Module objects defined at runtime, with relationships to parent layers.
- **ClassLoader:** the class loading mechanism. A module defined in a layer is bound to the class loader chosen when creating the layer.

ModuleLayer uses a Configuration to define modules at runtime. Configuration describes the module graph; the layer organizes the resolved modules at runtime.

## 2. The defineModulesWithOneLoader API

The static API has the form:

~~~java
ModuleLayer.defineModulesWithOneLoader(
    Configuration cf,
    List<ModuleLayer> parents,
    ClassLoader parentLoader
);
~~~

| Parameter | Meaning |
|---|---|
| cf | The Configuration containing the modules to define in the new layer |
| parents | List of parent module layers corresponding to the parent configurations of cf |
| parentLoader | The parent class loader of the class loader created for the new layer |

The return value is ModuleLayer.Controller. Call controller.layer() to obtain the newly created layer.

Key characteristics:

- The modules belonging to the new configuration are defined with the same class loader.
- Modules already in parent layers continue to belong to their parent layer and class loader.
- Each module remains a distinct named module with its own descriptor and access rules.
- Sharing a class loader does not merge modules into a single module.

Distinguish two kinds of parents:

- The parents list determines the relationship between module layers.
- parentLoader determines the parent class loader in the delegation mechanism when loading classes.

These are two parameters serving two different mechanisms.

## 3. Resolving a Configuration Before Creating a Layer

Before calling defineModulesWithOneLoader(), you must resolve the module graph. For example, plugins packaged in a directory:

~~~text
plugins/
├── com.acme.plugin.alpha.jar
├── com.acme.plugin.beta.jar
└── com.acme.plugin.common.jar
~~~

Suppose module alpha depends on beta and common. You can locate the modules and resolve from the boot layer:

~~~java
Path pluginPath = Path.of("plugins");
ModuleFinder finder = ModuleFinder.of(pluginPath);

ModuleLayer parentLayer = ModuleLayer.boot();

Configuration configuration =
    parentLayer.configuration().resolve(
        finder,
        ModuleFinder.of(),
        Set.of("com.acme.plugin.alpha")
    );
~~~

In this example:

- ModuleFinder.of(pluginPath) finds modules in the plugin directory.
- The boot layer is the parent layer.
- resolve() starts from root com.acme.plugin.alpha and locates required dependencies.
- The resulting Configuration contains the newly resolved modules together with their relationship to the parent configuration.

If a dependency is missing from the module path or not provided by the parent configuration, resolution can fail before layer creation.

## 4. Creating a Layer with One Class Loader

After resolving successfully, call the API:

~~~java
ModuleLayer.Controller controller =
    ModuleLayer.defineModulesWithOneLoader(
        configuration,
        List.of(parentLayer),
        ClassLoader.getSystemClassLoader()
    );

ModuleLayer pluginLayer = controller.layer();
~~~

ClassLoader.getSystemClassLoader() is used as the parent class loader for the new loader. The new layer's loader can delegate loading of classes it does not define to the parent loader via delegation.

Parent layer configuration and parent class loader are not the same:

- List.of(parentLayer) indicates that the new layer has the boot layer as its parent.
- ClassLoader.getSystemClassLoader() indicates that the new loader has the system class loader as its parent.

When there are multiple parent layers, the configuration must be resolved from the corresponding parent configurations and the passed-in layer list must match them.

### 4.1. Retrieving Modules and Inspecting the Class Loader

From the controller, obtain the layer:

~~~java
ModuleLayer pluginLayer = controller.layer();
~~~

Find a module:

~~~java
Module pluginModule = pluginLayer.findModule("com.acme.plugin.alpha")
    .orElseThrow();

System.out.println(pluginModule.getName());
ClassLoader pluginLoader = pluginModule.getClassLoader();
~~~

Modules in the new configuration created with one-loader will return the same class loader:

~~~java
Module alpha = pluginLayer.findModule("com.acme.plugin.alpha")
    .orElseThrow();

Module beta = pluginLayer.findModule("com.acme.plugin.beta")
    .orElseThrow();

System.out.println(alpha.getClassLoader() == beta.getClassLoader());
~~~

If both modules belong to the configuration defined by that one-loader call, the result is true.

ModuleLayer.findModule() can find modules in the current layer and parent layers. When checking new modules, use a module name belonging to the new configuration to avoid confusing it with a module already existing in a parent layer.

## 5. Complete Plugin Example

The example below loads a plugin module from the plugins directory. The plugin is resolved and then defined in a new layer with a shared loader.

Structure:

~~~text
application/
├── app/
│   └── com.acme.app/
│       ├── module-info.java
│       └── com/acme/app/Main.java
└── plugins/
    └── com.acme.plugin/
        ├── module-info.java
        └── com/acme/plugin/PluginEntry.java
~~~

### 5.1. Plugin Module

File module-info.java:

~~~java
module com.acme.plugin {
    exports com.acme.plugin;
}
~~~

File PluginEntry.java:

~~~java
package com.acme.plugin;

public class PluginEntry {
    public String name() {
        return "Sample plugin";
    }
}
~~~

The plugin exports the package containing the entry class so external code can access this public class.

### 5.2. App Module

File module-info.java:

~~~java
module com.acme.app {
}
~~~

File Main.java:

~~~java
package com.acme.app;

import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.lang.reflect.Method;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;

public class Main {
    public static void main(String[] args) throws Exception {
        Path pluginPath = Path.of("plugins");
        ModuleLayer parentLayer = ModuleLayer.boot();
        ModuleFinder finder = ModuleFinder.of(pluginPath);

        Configuration configuration =
            parentLayer.configuration().resolve(
                finder,
                ModuleFinder.of(),
                Set.of("com.acme.plugin")
            );

        ModuleLayer.Controller controller =
            ModuleLayer.defineModulesWithOneLoader(
                configuration,
                List.of(parentLayer),
                ClassLoader.getSystemClassLoader()
            );

        ModuleLayer pluginLayer = controller.layer();

        Module pluginModule = pluginLayer
            .findModule("com.acme.plugin")
            .orElseThrow();

        ClassLoader pluginLoader = pluginModule.getClassLoader();

        Class<?> entryClass = Class.forName(
            "com.acme.plugin.PluginEntry",
            true,
            pluginLoader
        );

        Object entry = entryClass.getConstructor().newInstance();
        Method nameMethod = entryClass.getMethod("name");

        System.out.println(nameMethod.invoke(entry));
    }
}
~~~

The example uses reflection to illustrate that the class is loaded by the plugin's loader. Because the package is exported, the public class and public constructor can be accessed in the usual way.

### 5.3. Compiling and Running

Compile the plugin into a modular JAR and place the JAR in the plugins directory. Then compile the app module and run the app with a module path containing app. At runtime, app uses ModuleFinder to locate the plugin in the plugins directory.

Example JAR creation:

~~~bash
jar --create --file plugins/com.acme.plugin.jar -C plugins-out/com.acme.plugin .
~~~

Running the application:

~~~bash
java --module-path app-out -m com.acme.app/com.acme.app.Main
~~~

Output:

~~~text
Sample plugin
~~~

The plugin is discovered in the plugins directory that app passes to ModuleFinder, without needing to put the plugin in the boot layer. The new layer defines the plugin and binds the plugin module to the class loader created for that layer.

## 6. ModuleLayer.Controller

defineModulesWithOneLoader() returns a ModuleLayer.Controller. The controller provides permission to adjust certain module relationships after the layer has been defined.

| Method | Effect |
|---|---|
| layer() | Gets the newly created ModuleLayer |
| addReads(source, target) | Adds a read relationship from the source module to the target module |
| addExports(source, package, target) | Exports a package of the source module to the target module |
| addOpens(source, package, target) | Opens a package of the source module for deep reflection from the target module |

Example:

~~~java
Module source = pluginLayer.findModule("com.acme.plugin")
    .orElseThrow();

Module target = ModuleLayer.boot()
    .findModule("com.acme.app")
    .orElseThrow();

controller.addReads(source, target);
~~~

This example adds a read relationship from the plugin to the app. Use this only when there is a specific runtime requirement and you understand the impact on module boundaries.

A Controller adjusts the modules it created. These changes only take effect at runtime and do not modify module-info.java inside the JAR. Prefer declaring stable dependencies and exports in descriptors; use the controller for intentional dynamic integration.

## 7. Comparing one-loader and many-loaders

| Creation method | Class loader mapping |
|---|---|
| defineModulesWithOneLoader | All modules in the new configuration share one loader |
| defineModulesWithManyLoaders | Each module in the new configuration gets its own loader |
| defineModules | The application supplies a function mapping module name to class loader |

### 7.1. When Is one-loader Suitable?

Use defineModulesWithOneLoader() when:

- A group of modules belongs to the same application or plugin suite.
- The modules need to share a unified class loading mechanism.
- There is no need to separate class loaders per module.
- You want to reduce the number of class loaders to manage.

### 7.2. When Is many-loaders Suitable?

Use defineModulesWithManyLoaders() when each module needs its own class loader, for example to manage class loading or module lifecycles more independently.

Multiple class loaders do not automatically create a security sandbox. Do not treat class loaders as a safety boundary for running untrusted code.

### 7.3. One Loader Does Not Merge Modules

Even when modules share a class loader:

- Each module still has its own name and Module object.
- requires, exports, opens, and access rules still apply.
- Non-exported packages do not become public API.
- Modules can still be looked up individually in the layer by name.

Sharing a loader does not mean every class in the layer can access one another.

## 8. Conditions and Limitations

### 8.1. Configuration Must Match Parent Layers

The supplied Configuration must be resolved with the corresponding parent configurations. The parent layers list when defining the layer must accurately reflect those parent configurations.

If the configuration was resolved from the boot configuration, the parent list is typically:

~~~java
List.of(ModuleLayer.boot())
~~~

Do not pass a parent layer that does not correspond to the configuration used for resolution.

### 8.2. Overlapping Packages Between Modules

Modules in the same configuration/layer must obey JPMS package constraints. If two modules in the same layer contain the same package, defining the layer can fail with LayerInstantiationException.

When encountering a split package error:

1. Identify the modules containing the duplicate package.
2. Choose one module to own that package.
3. Move the related classes into the same module or redesign the packages.
4. Re-resolve the configuration and define the layer.

### 8.3. Distinguishing Resolution Errors from Layer Creation Errors

- Configuration.resolve() can fail if a module is missing, dependencies are invalid, or the graph has a cycle.
- defineModulesWithOneLoader() can fail when it cannot define the modules into the layer under the corresponding class loader/package constraints.

Determine whether the error occurs before or after obtaining a Configuration. Do not edit requires if the actual cause is a package conflict or loader constraint.

## 9. Common Misconceptions

**Does one-loader mean all modules in the JVM share one loader?** No. Only the modules belonging to the new configuration defined by that call share the loader. Modules in parent layers continue using their parent layer's loaders.

**Are parent layer and parent class loader the same?** No. Parent layer determines module relationships between layers. Parent class loader determines class loading delegation.

**Does a new layer modify the boot layer?** No. The new layer is a child layer; modules already in the boot layer remain in the boot layer.

**Does using one-loader bypass exports?** No. Each module still preserves its JPMS access boundaries.

**Can one-loader be used as a sandbox for plugins?** No. Untrusted plugins must be isolated at the process level or with an appropriate security mechanism.

## 10. Workflow for Implementing Plugins with one-loader

1. Define a stable API in a parent module or shared module.
2. Package the plugin and its dependencies as named modules.
3. Select the plugin root modules to load.
4. Use ModuleFinder to find modules in the plugin directory.
5. Resolve a Configuration against the boot layer or an appropriate parent layer.
6. Use defineModulesWithOneLoader() to create the layer.
7. Retrieve modules from the layer and identify the class loader.
8. Load the entry point or locate service providers via ServiceLoader.
9. Manage initialization errors, state, and plugin lifecycle.
10. Only use Controller to adjust runtime relationships when there is a clear requirement.

If the plugin provides a service, design the API with uses and provides so you do not depend on concrete implementation class names.

## 11. Self-Check

**Scenario 1:** A Configuration contains three plugin modules A, B, and C. When calling defineModulesWithOneLoader(), does each module get its own class loader?

**Answer:** No. The modules in the new configuration are defined using the same class loader. Modules in parent layers still use their parent layer's loaders.

**Scenario 2:** A Configuration is resolved from the boot layer. When creating the layer, why pass List.of(ModuleLayer.boot())?

**Answer:** Because the boot layer is the parent layer corresponding to the parent configuration used during resolution.

**Scenario 3:** What does defineModulesWithOneLoader() return?

**Answer:** A ModuleLayer.Controller. Call controller.layer() to obtain the newly created layer.

**Scenario 4:** Two modules in a configuration have a package with the same name. Does one-loader automatically resolve the conflict?

**Answer:** No. A package conflict can cause layer creation to fail. You need to reorganize the packages or which module owns the package.

**Scenario 5:** Does one-loader cause modules to ignore exports rules?

**Answer:** No. Module identity and access rules are still enforced even though the modules share a class loader.

**Scenario 6:** When should you choose many-loaders?

**Answer:** When each module needs its own class loader to manage class loading or module lifecycles more independently. This approach still does not automatically create a security sandbox.

When designing plugins with JPMS, clearly separate three steps: resolve the module graph into a Configuration, define the Configuration in a ModuleLayer, and then use classes or services from the new layer. defineModulesWithOneLoader() handles defining the layer with a shared loader, while module descriptors continue to govern dependencies and access permissions between modules.