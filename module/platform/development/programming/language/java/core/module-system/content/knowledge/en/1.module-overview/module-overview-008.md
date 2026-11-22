# Learning roadmap from module descriptors to custom ModuleLayers

The Java Platform Module System (JPMS) introduced module structure to the Java platform in JDK 9. To learn JPMS solidly, proceed from module descriptions in module-info.java, understand how the compiler and JVM resolve modules, and only then move on to services and creating ModuleLayers via API. This sequence lets each new concept build on an already understood model, rather than starting immediately with custom class loaders or complex configuration APIs.

The goal of this roadmap is to be able to read and design module descriptors, compile and run a modular application, explain the module graph, use ServiceLoader, and then load a group of plugin modules into a separate ModuleLayer when the application needs runtime extensibility.

## 1. Overall map

A modular application can be viewed along the following processing chain:

~~~text
module-info.java and source code
          |
          v
Compiler checks dependencies and access permissions
          |
          v
Module descriptor in compiled module
          |
          v
ModuleFinder locates modules on the module path
          |
          v
Module resolution creates Configuration / module graph
          |
          v
ModuleLayer defines modules and binds class loaders
          |
          v
Application uses classes, reflection, or ServiceLoader
~~~

These concepts are related but serve different roles:

- **Module descriptor** describes the module name, dependencies, exported or opened packages, and services the module uses or provides.
- **Module path** is where modules eligible to participate in resolution are searched.
- **Module resolution** determines the set of required modules and readability relationships among them.
- **ModuleLayer** is a runtime region holding defined modules, with parent relationships to other layers.
- **ClassLoader** loads class definitions. A layer can associate modules with a single class loader or with class loaders chosen by another strategy.

Do not equate a module with a package, a JAR, or a class loader. A package is a way to organize names and classes; a JAR is a packaging format; a module is a platform-level unit of dependency and API encapsulation; a class loader is the class-loading mechanism in the JVM.

## 2. Stage 1 — Grasp the module model and encapsulation boundaries

Before writing descriptors, understand the problem JPMS solves. With the traditional classpath, libraries are typically combined into a single search list. Packages and classes can be accessed more broadly than intended, dependencies are hard to express clearly at the platform level, and duplicate classes can cause hard-to-trace errors.

JPMS adds boundaries at the module level:

- A **named module** has a name and a descriptor.
- A module can declare other modules it needs to read using the **requires** directive.
- A package is only accessible to other modules as public API when appropriately exported.
- Deep reflection into a package may require the package to be opened.
- Services can be declared using **uses** and **provides**.

Named modules are typically located on the module path. Classes and JARs placed on the classpath belong to the unnamed module of the corresponding class loader. Java still supports the classpath, so an application can migrate incrementally, yet once running on the module path, module readability and package access rules are enforced.

At this stage, be able to answer three questions:

1. Which packages belong to which module?
2. Which module needs to read which module?
3. Which packages are public API, and which packages need to stay closed?

## 3. Stage 2 — Read and write module descriptors

The module-info.java file sits at the source root of a module. Example:

~~~java
module com.example.billing {
    requires java.logging;

    exports com.example.billing.api;
    opens com.example.billing.model;
}
~~~

The descriptor above declares a module named **com.example.billing**, depends on the platform module **java.logging**, exports the API package, and opens the model package for appropriate reflection mechanisms.

Learn the directives in the following order:

| Directive | Meaning | Design question |
| --- | --- | --- |
| requires | Declares a dependency module the current module needs to read | Which modules does this module need types or APIs from? |
| requires transitive | Propagates readability of the dependency to modules that depend on the current module | Which dependencies are part of the API that consumers of this module must read? |
| requires static | Dependency needed at compile time that may be absent at runtime | Are there optional dependencies needed only at compile-time? |
| exports | Allows other modules to access public types in the exported package | Which packages are public API? |
| exports ... to | Exports the package only to specific named modules | Are there APIs meant only for a trusted group of modules? |
| opens | Permits deep reflective access into the package | Does a framework need to read or write non-public fields or constructors? |
| opens ... to | Opens the package only to specific modules | Which framework genuinely needs reflection permission? |
| uses | Declares that the module consumes a service | Which service implementations does this module need to discover? |
| provides ... with | Declares an implementation provided for a service | Which implementation does this module supply? |

Key points to remember:

- **requires** creates a module readability relationship; it does not automatically export all packages of the dependency.
- **exports** allows access to public types of the named package, but does not mean opening all private members for reflection.
- **opens** serves deep reflection; it is not a replacement for exports when code in another module needs to call public APIs in the ordinary way.
- **requires transitive** should be used when types from a dependency appear in the current module's public API and API consumers need to read that dependency.
- **requires static** still creates a compile-time dependency. The application must ensure the dependency is present if runtime actually needs it.
- A module cannot export part of a package class-by-class. Export boundaries are declared at the package level.

Practice by creating two small modules: an API module exporting a package containing a public class, and an application module that requires the API module and calls that class. Then remove exports or requires to observe compiler errors. This exercise shows that JPMS checks readability and access permissions right during compilation.

## 4. Stage 3 — Compile and run on the module path

After understanding descriptors, learn how to organize a source tree and use the Java launcher. With two modules:

~~~text
project/
└── src/
    ├── com.example.greeting.api/
    │   ├── module-info.java
    │   └── com/example/greeting/api/Greeting.java
    └── com.example.greeting.app/
        ├── module-info.java
        └── com/example/greeting/app/Main.java
~~~

Descriptor of the API module:

~~~java
module com.example.greeting.api {
    exports com.example.greeting.api;
}
~~~

Descriptor of the application module:

~~~java
module com.example.greeting.app {
    requires com.example.greeting.api;
}
~~~

Compile both modules from the project directory:

~~~bash
javac -d out --module-source-path src -m com.example.greeting.api,com.example.greeting.app
~~~

After compilation, the out directory contains compiled module directories. Run the application:

~~~bash
java --module-path out -m com.example.greeting.app/com.example.greeting.app.Main
~~~

Here:

- **--module-source-path** tells the compiler the directory structure containing sources of multiple modules.
- **-m** during compilation selects the modules to compile.
- **-d** specifies where to write the output.
- **--module-path** tells the Java launcher where to find compiled modules or modular JARs.
- **-m module/class** selects the module and main class to launch.

Module source paths must match module names in the source structure. Once a module is packaged into a JAR, that JAR can also be placed on the module path. A JAR with an explicit module descriptor is an explicit module; an old JAR without a descriptor can be treated as an automatic module when placed on the module path. Automatic modules are useful during migration, but should not be treated as the target design for every dependency.

Run the same example on both the classpath and the module path to see the difference. On the classpath, packages are not exported by descriptor and requires relationships are not used to build a module graph. On the module path, the compiler and JVM enforce JPMS rules.

## 5. Stage 4 — Understand module resolution and the module graph

The module path only supplies locations to search for modules. It does not mean every module located there is automatically loaded. When launching a modular application, the JVM starts from root modules, reads requires directives, and locates dependencies via the module path or platform modules. That process produces a resolved configuration.

The module graph describes modules and readability relationships among them. It helps answer:

- Which modules actually participate in the application?
- Which dependencies are required directly or indirectly?
- Which module reads which module?
- Why is a public package still inaccessible from a specific module?

Several useful commands when investigating:

~~~bash
java --show-module-resolution --module-path mods -m com.example.app/com.example.app.Main
~~~

~~~bash
jar --describe-module --file libs/example.jar
~~~

~~~bash
jdeps --module-path mods --module com.example.app
~~~

The first command displays module resolution information at startup. The second reads a JAR's descriptor. The third analyzes a module's dependencies. These commands help test hypotheses about dependencies before moving to runtime APIs.

At this stage, clearly distinguish the **module path** from the **module graph**: the module path is the lookup source; the module graph is the resulting set of resolved module relationships for a specific configuration.

## 6. Stage 5 — Understand exports, opens, and reflection

One module can read another module yet still not access a package if that package is not exported. This is a core encapsulation mechanism of JPMS.

For example, module A declares:

~~~java
module com.example.domain {
    exports com.example.domain.api;
}
~~~

Module B can require module A and use public types in the api package. However, the com.example.domain.internal package is not exported, so module B cannot use public classes in that package as ordinary module API.

Frameworks using reflection may need access to non-public constructors, fields, or methods. In this case, the corresponding package may need to be opened:

~~~java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.model to com.example.persistence;
}
~~~

Choose the right directive according to the need:

- Other modules' source code calls public APIs: use **exports**.
- A framework needs deep reflection: use **opens**.
- Only one framework needs reflection: consider **opens ... to** to limit the authorized modules.

Command-line options such as **--add-exports** and **--add-opens** can help with legacy library compatibility or diagnostics. They should be treated as deliberate deployment measures, not long-term substitutes for properly designed descriptors.

## 7. Stage 6 — Use services and ServiceLoader

Services are the step from static dependencies to discovering implementations by contract. The consuming module declares **uses**; the module providing an implementation declares **provides ... with**.

For example, the API module defines the service:

~~~java
package com.example.greeting.api;

public interface GreetingProvider {
    String message();
}
~~~

Descriptor of the API module:

~~~java
module com.example.greeting.api {
    exports com.example.greeting.api;
}
~~~

Application module using the service:

~~~java
module com.example.greeting.app {
    requires com.example.greeting.api;
    uses com.example.greeting.api.GreetingProvider;
}
~~~

Plugin module providing the implementation:

~~~java
module com.example.greeting.hello {
    requires com.example.greeting.api;

    provides com.example.greeting.api.GreetingProvider
        with com.example.greeting.hello.HelloGreetingProvider;
}
~~~

The application can discover providers using ServiceLoader:

~~~java
ServiceLoader<GreetingProvider> providers =
    ServiceLoader.load(GreetingProvider.class);

for (GreetingProvider provider : providers) {
    System.out.println(provider.message());
}
~~~

ServiceLoader decouples the API contract from implementations. The application module depends only on the service API; provider modules can be added or swapped per deployment configuration. This is a useful foundation for plugin architectures, adapters, or selectable implementations.

Verify three things before debugging services:

1. The consuming module declared uses for the service.
2. The provider module declared provides with a valid implementation.
3. The relevant modules were resolved and reside within the scope of the layer ServiceLoader is searching.

When using a custom ModuleLayer, choose the right ServiceLoader overload to find providers in the desired layer. **ServiceLoader.load(ServiceType.class)** is tied to the standard class loader context; **ServiceLoader.load(layer, ServiceType.class)** searches for providers in a layer and its parent layers.

## 8. Stage 7 — From module graph to ModuleLayer

When an application needs to load plugins or independent module groups while running, simply putting all JARs on the module path at startup may not suffice. JPMS provides APIs to find descriptors, resolve modules, and define modules in a new layer.

Key components:

- **ModuleFinder** finds module descriptors in one or more locations, such as a plugin directory or a set of JARs.
- **Configuration** represents the result of module resolution: which modules are selected and their dependencies.
- **ModuleLayer** defines modules from a configuration into the JVM and links them to parent layers.
- **defineModulesWithOneLoader** creates a layer in which the new modules share one class loader created by the API.
- **defineModules** lets you supply a custom module-to-class-loader mapping strategy when the architecture needs finer control.

The basic sequence is:

~~~text
ModuleFinder
    |
    v
Configuration.resolve(...)
    |
    v
ModuleLayer.defineModulesWithOneLoader(...)
    |
    v
ServiceLoader.load(layer, ServiceType.class)
~~~

For example, an application already running in the boot layer wants to load a plugin from the plugins directory:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

ModuleLayer parent = ModuleLayer.boot();

ModuleFinder finder = ModuleFinder.of(Path.of("plugins"));

Configuration configuration =
    parent.configuration().resolve(
        finder,
        ModuleFinder.of(),
        Set.of("com.example.greeting.hello")
    );

ModuleLayer pluginLayer =
    parent.defineModulesWithOneLoader(
        configuration,
        ClassLoader.getSystemClassLoader()
    );
~~~

Here, **ModuleFinder.of(Path.of("plugins"))** locates modules in the plugin directory. The **resolve** call uses the parent's configuration as context, finding the requested root module and its required dependencies. Then **defineModulesWithOneLoader** defines the resolved modules in a child layer.

For the example to work, the plugin must have a valid descriptor, the root module name must match, API modules that the plugin requires must be readable from the parent or from the discovered module set, and the plugins directory must contain the right JARs or module structure. The service API module should be defined in a parent layer so the application and plugin reference the exact same service type.

After creating the layer, discover providers in that layer:

~~~java
ServiceLoader<GreetingProvider> providers =
    ServiceLoader.load(pluginLayer, GreetingProvider.class);

for (GreetingProvider provider : providers) {
    System.out.println(provider.message());
}
~~~

The snippet illustrates the plugin loading concept, not a complete plugin system. A real-world application must handle errors when modules are missing, API versions mismatch, providers fail to instantiate, or plugins are incompatible. If a plugin has its own dependencies, those dependencies must also be resolvable from the provided module path.

## 9. Stage 8 — Creating a controlled custom ModuleLayer

After getting the single-loader example working, learn when a custom class loader is needed. A layer can use one shared loader for all modules in the layer, or a different loader mapping strategy when class loading needs isolation by plugin group.

Before writing a custom loader, determine actual requirements:

- Do plugins need to share a single copy of the API provided by the parent layer?
- Can a plugin contain an internal library with the same name as another plugin?
- Do plugin groups need to be loaded or unloaded on independent lifecycles?
- Is explicit control needed over which module is visible from which module?
- Is using a shared loader sufficient for deployment requirements?

If per-module loader mapping is needed, **ModuleLayer.defineModules(Configuration, List<ModuleLayer>, Function<String, ClassLoader>)** allows supplying a function that selects a class loader by module name. This function must return an appropriate class loader for each module in the configuration. ModuleLayer remains responsible for defining modules and establishing layer relationships; the class loaders perform class loading according to the supplied strategy.

Do not treat a custom ModuleLayer as a security sandbox. Module encapsulation and class loaders help manage dependencies, readability, and class-loading scope, but they do not replace process security mechanisms, OS permissions, or resource isolation. If plugins are untrusted code, design appropriate process boundaries or secure execution mechanisms.

Also remember that a class's identity in the JVM depends on both the class name and the class loader that defined it. Two plugins can load two classes with the same name defined by two different loaders; they are not automatically type-compatible with each other. For shared APIs, let plugin modules read and use the same API module from the parent layer.

## 10. Exercises by milestone

| Milestone | Exercise | Proof of completion |
| --- | --- | --- |
| 1. Model | Sketch two modules, API and app, showing packages and dependencies | Able to explain which module reads which module |
| 2. Descriptor | Write requires, exports, opens and try toggling each directive | Able to predict and explain compile/access errors |
| 3. Build | Compile and run a two-module application using javac/java | Build and run commands are reproducible |
| 4. Resolution | Use --show-module-resolution, jar --describe-module, and jdeps | Able to identify root modules and dependencies |
| 5. Encapsulation | Attempt accessing an unexported package and reflecting into an unopened package | Able to distinguish ordinary access errors from deep reflection |
| 6. Service | Create a service API and at least two providers | Able to swap providers without editing consumer code |
| 7. ModuleLayer | Load a provider from a plugin directory into a child layer | ServiceLoader finds the provider in the selected layer |
| 8. Custom loader | Try mapping separate loaders per module group if required | Able to explain class identity and parent layer relationships |

## 11. Common learning and debugging mistakes

**Module not found** usually indicates the root module or dependency is not in the lookup locations used by the compiler/JVM, the module name does not match, or the module path points to the wrong directory.

**Package is not visible** usually involves a module missing a requires on the package-owning module, or the package not being exported to the calling module.

**IllegalAccessException** or reflection errors can indicate a package has not been opened in the way the framework requires. Check the descriptor of the class-owning module and the module performing reflection.

**ServiceLoader finds no providers** should be checked across all three layers: uses/provides, module resolution, and the layer/class loader that ServiceLoader is searching.

**ClassCastException across plugins** can happen when an API is loaded into two different class definitions by two loaders. Place shared APIs in a parent layer and have plugins require that API module.

When debugging, record the module name, module path, root modules, layer used, and the class loader defining the relevant types. These facts help distinguish descriptor errors, resolution errors, and runtime class-loading errors.

## 12. Roadmap completion criteria

You have mastered this roadmap when you can build an application consisting of an API module, an application module, and a provider module on your own; compile, run, and observe the module graph; explain why exports differs from opens; discover services with ServiceLoader; and load providers from a plugin directory using a child ModuleLayer.

At an advanced level, you should be able to explain the distinct roles of ModuleFinder, Configuration, ModuleLayer, and ClassLoader, as well as determine when a shared loader is sufficient and when custom loader mapping is truly needed. Once you can do that, you can design modular plugin systems while maintaining control over dependencies, public APIs, and the sources of loaded classes.