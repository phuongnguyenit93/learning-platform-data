# Configuration resolves the module graph

The Java Platform Module System (JPMS) does not just need to know module names and declared dependencies. Before a modular application runs, Java must determine exactly which modules participate in the configuration and how they depend on each other. That process is called **module resolution**.

The resolution result is represented by a `Configuration` object. A Configuration contains the set of resolved modules along with their dependency relationships. From this configuration, Java can create a `ModuleLayer` to load and run the modules in a specific runtime environment.

Understanding how the module graph is resolved helps you analyze why a module is included in an application, why a dependency is missing, and how to create dynamic module configurations for plugins or extensions.

## Objectives

After this lesson, you will be able to:

- Explain module resolution and the role of the module graph.
- Distinguish root modules from indirectly discovered dependencies.
- Understand the roles of `ModuleFinder`, `Configuration`, and `ModuleLayer`.
- Use `Configuration.resolve()` to resolve a set of modules.
- Distinguish `resolve()` from `resolveAndBind()` when `ServiceLoader` is involved.
- Read resolution errors and inspect configurations using JDK tools.

## 1. Module graph and module resolution

A modular application consists of multiple named modules. Each module can declare dependencies using `requires` in `module-info.java`.

Example:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

And the service module:

~~~java
module com.acme.service {
    requires com.acme.model;
}
~~~

Directed dependency graph:

~~~text
com.acme.app ──requires──> com.acme.service
                                  |
                                  └──requires──> com.acme.model
~~~

When the application launches with the `com.acme.app` module as the root module, Java must locate the app, service, and model modules. The set of discovered modules and valid dependency relationships form the module graph of that configuration.

**Module resolution** is the process of determining the required set of modules and checking dependencies to produce a valid configuration.

Resolution is not simply finding a JAR file. It must also determine module names, recursively resolve dependencies, check module system constraints, and construct the set of modules that can participate in the configuration.

## 2. Root modules and dependency closure

### 2.1. A root module is the starting point

A root module is a module chosen as a starting point for the resolution process.

When running an application with the launcher:

~~~bash
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

The `com.acme.app` module is the root module specified by the `-m` option.

When compiling multiple modules with `javac`, the `-m` option also specifies the root modules to compile:

~~~bash
javac --module-source-path src -d out -m com.acme.app
~~~

Modules required by app will be searched for next during the resolution process.

Additional root modules can be added using the `--add-modules` option:

~~~bash
java --module-path mods --add-modules com.acme.plugin -m com.acme.app/com.acme.app.Main
~~~

At this point `com.acme.plugin` is also included in the root module set for resolution, along with the app module selected as the main module.

The `--add-modules` option also supports special values like `ALL-MODULE-PATH` and `ALL-SYSTEM`. Use them only when the application genuinely needs to bring the entire corresponding group of modules into the configuration.

### 2.2. Dependency closure

After determining the root modules, Java follows `requires` directives to find the required dependencies.

Example:

~~~text
Roots:
  com.acme.app

Dependency declarations:
  app     requires service
  service requires model
  model   requires java.base
~~~

The resolved module set may include:

~~~text
com.acme.app
com.acme.service
com.acme.model
java.base
~~~

This set is the dependency closure starting from the root modules: the required modules found by following dependencies.

A module can be resolved into a configuration even if a root module does not directly declare `requires` on it. This happens when the module lies in the dependency chain of another module.

However, **being resolved into a configuration does not mean every root module can read that module**. Readability also depends on `requires` relationships and the `transitive` modifier. This is an important distinction when analyzing the module graph and readability graph.

### 2.3. Observable modules

For a module to be resolved, Java must be able to find it in the appropriate module sources. The set of modules that can be found is called the observable modules in the resolution context.

Common sources:

- JDK system modules.
- Directories or JARs on the module path.
- Module finders provided via the API.
- Parent configurations when creating a new configuration.

A module may exist on disk yet not belong to the observable module set of the current resolution if the path or module finder does not include it in the search scope.

## 3. ModuleFinder: finding modules for resolution

The `java.lang.module.ModuleFinder` API represents a source that can locate modules.

Create a finder from a directory:

~~~java
ModuleFinder finder = ModuleFinder.of(Path.of("mods"));
~~~

Create a finder for system modules:

~~~java
ModuleFinder systemFinder = ModuleFinder.ofSystem();
~~~

Find a module by name:

~~~java
Optional<ModuleReference> reference =
    finder.find("com.acme.app");
~~~

If found, `ModuleReference` represents the module and provides descriptor information along with module contents for subsequent steps to process.

Related components:

| API | Role |
|---|---|
| `ModuleFinder.of(path)` | Finds modules in the specified locations |
| `ModuleFinder.ofSystem()` | Finds runtime system modules |
| `ModuleReference` | Represents a discovered module |
| `ModuleDescriptor` | Describes module name, requires, exports, opens, uses, and provides |

ModuleFinder only helps locate modules. It does not resolve the entire dependency graph on its own. That belongs to `Configuration.resolve()` or `resolveAndBind()`.

## 4. Configuration: the result of module resolution

`java.lang.module.Configuration` represents a resolved module configuration.

A Configuration contains:

- The set of `ResolvedModule` instances present in the configuration.
- Dependency relationships among the resolved modules.
- Parent configurations on which the current configuration depends.

Some commonly used APIs:

~~~java
Configuration configuration = ModuleLayer.boot().configuration();

Set<ResolvedModule> modules = configuration.modules();

Optional<ResolvedModule> app =
    configuration.findModule("com.acme.app");
~~~

These methods help inspect the module set and look up modules by name after resolution succeeds.

Configuration is an immutable object. Once created, dependencies cannot be added or removed directly from it. To obtain a different configuration, a new resolution must be performed.

### 4.1. Configuration.resolve()

The `resolve()` method resolves root modules and their dependencies.

Example:

~~~java
Path modsPath = Path.of("mods");

ModuleFinder finder = ModuleFinder.of(modsPath);

Configuration parent = ModuleLayer.boot().configuration();

Configuration configuration = parent.resolve(
    finder,
    ModuleFinder.of(),
    Set.of("com.acme.app")
);
~~~

Meaning of the parameters:

- `finder`: additional module source to search, here the `mods` directory.
- `ModuleFinder.of()`: empty additional finder after the parent configurations.
- `Set.of("com.acme.app")`: set of root modules starting resolution.
- `parent`: parent configuration, usually the boot layer's configuration.

In the three-parameter overload, the current configuration serves as the parent configuration. When multiple parent configurations are needed, the overload accepting a list of `parents` can be used:

~~~java
Configuration configuration = Configuration.resolve(
    finder,
    List.of(ModuleLayer.boot().configuration()),
    ModuleFinder.of(),
    Set.of("com.acme.app")
);
~~~

The result is a new configuration containing the modules resolved from the roots and their dependencies, along with relationships to the parent configuration.

### 4.2. Finders before and after parent configurations

The resolution API allows supplying finders before and after the list of parent configurations:

~~~java
Configuration configuration = parent.resolve(
    beforeFinder,
    afterFinder,
    roots
);
~~~

In principle, these sources determine the module lookup order during resolution:

- The before finder is checked before the parent configurations.
- Parent configurations provide modules already present in parent layers.
- The after finder is checked after the parent configurations.

This mechanism is useful when creating a configuration with additional module sources or when controlling how modules are found in a multi-layer system. It should not be used to mask duplicate module names or replace an inconsistent dependency configuration.

### 4.3. Reading resolution results

After resolving successfully:

~~~java
for (ResolvedModule module : configuration.modules()) {
    System.out.println(module.name());
}
~~~

A specific module can be checked:

~~~java
configuration.findModule("com.acme.service")
    .ifPresent(module ->
        System.out.println(module.name())
    );
~~~

If a root module or dependency cannot be found, resolution may throw `ResolutionException`. If a module name is invalid, the configuration has conflicts, or the dependency graph violates constraints, creating the configuration can also fail.

## 5. resolve() and resolveAndBind()

In addition to `resolve()`, Configuration also has `resolveAndBind()`.

The two methods have similar purposes but differ in service binding:

| Method | Behavior |
|---|---|
| `resolve()` | Resolves root modules and dependencies declared via requires |
| `resolveAndBind()` | Resolves dependencies and additionally performs service binding to find matching providers |

Service binding relates to `ServiceLoader` and the `uses` and `provides` declarations in module descriptors.

Example of an app module consuming a service:

~~~java
module com.acme.app {
    uses com.acme.spi.GreetingProvider;
}
~~~

Provider module:

~~~java
module com.acme.greeting.impl {
    requires com.acme.spi;

    provides com.acme.spi.GreetingProvider
        with com.acme.greeting.impl.DefaultGreetingProvider;
}
~~~

If an application needs to automatically bring matching provider modules into the configuration based on the services used by already resolved modules, `resolveAndBind()` can be used.

This is especially useful for plugins and service providers. Providers are searched in the relevant module finders, and the provider's dependencies can also be resolved.

Not every application needs service binding. If the module graph is already fully determined by roots and requires, `resolve()` is usually sufficient.

## 6. How is Configuration different from ModuleLayer?

These two concepts are often used together, yet they are not the same.

- **Configuration** describes the resolved module graph.
- **ModuleLayer** is a runtime layer containing modules that have been defined and associated with class loaders.

You can visualize it as:

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
ModuleLayer.defineModules(...)
    |
    v
Runtime modules + class loaders
~~~

Configuration answers which modules were resolved and how they depend on one another. ModuleLayer answers how those modules are loaded and organized at runtime.

The boot layer is the initial layer created by the JVM launcher. System modules and application modules resolved at startup reside in the boot layer's corresponding configuration.

### 6.1. Creating a new layer for plugins

An application can create a new module layer to load plugins without placing all plugins in the boot layer.

Code skeleton example:

~~~java
Path pluginPath = Path.of("plugins");

ModuleFinder finder = ModuleFinder.of(pluginPath);

Configuration parent = ModuleLayer.boot().configuration();

Configuration cf = parent.resolve(
    finder,
    ModuleFinder.of(),
    Set.of("com.acme.plugin")
);

ModuleLayer.Controller controller =
    ModuleLayer.defineModulesWithOneLoader(
        cf,
        List.of(ModuleLayer.boot()),
        ClassLoader.getSystemClassLoader()
    );

ModuleLayer pluginLayer = controller.layer();
~~~

In the example:

1. ModuleFinder locates plugins in the `plugins` directory.
2. Configuration.resolve resolves the root module `com.acme.plugin` along with its dependencies.
3. ModuleLayer creates a new runtime layer with the boot layer as parent.
4. The new modules are defined using a shared class loader in that layer.

This is the foundational technique for modular plugin architecture. Real-world applications also need to determine how to discover providers, manage plugin lifecycles, handle errors, and communicate over stable APIs.

## 7. Launcher options that affect the module graph

When running an application, several options can affect root modules or the observable module set.

### 7.1. --module-path

Specifies locations containing modules:

~~~bash
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

The module path is the source from which Java locates modules to resolve.

### 7.2. --add-modules

Adds root modules beyond the main module:

~~~bash
java --module-path mods --add-modules com.acme.plugin -m com.acme.app/com.acme.app.Main
~~~

The added module becomes a root for resolution. From there, its dependencies are also searched according to the corresponding declarations.

### 7.3. --limit-modules

Restricts the set of observable system modules in the configuration:

~~~bash
java --limit-modules java.base,java.logging --module-path mods -m com.acme.app/com.acme.app.Main
~~~

This option is useful when you want to create a smaller runtime image or execution environment with fewer modules. If a required module is excluded from the observable set, resolution may fail.

### 7.4. --show-module-resolution

Displays information about the resolved modules:

~~~bash
java --show-module-resolution --module-path mods -m com.acme.app/com.acme.app.Main
~~~

This is a quick way to inspect roots and dependencies when an application does not run as expected.

## 8. Common errors when resolving the module graph

### 8.1. Module not found

Common causes:

- The module name in requires does not match.
- The module is not on the module path or in the finder.
- The JAR was placed on the classpath instead of the module path.
- The automatic module name inferred from the filename differs from the name used in the descriptor.

How to handle: check the name with `jar --describe-module` and verify the module path in the compile or run command.

### 8.2. Cyclic dependence

Example:

~~~text
A requires B
B requires C
C requires A
~~~

A named module dependency graph must not contain cycles. Find the reverse dependency and extract a shared API or abstraction into a third module if appropriate.

### 8.3. Module name conflict

If multiple sources provide modules with the same name, Java may be unable to determine a unique module reference or may report an error during resolution. Check the module path, module finders, and parent configurations to avoid bringing multiple alternatives with the same name into the configuration.

### 8.4. Package conflict or split package

A package split across multiple named modules can create conflicts in the module configuration, especially when the modules are read together or defined in the same layer/class loader.

When encountering a split package error, identify which modules contain the overlapping package and consider merging the package into one module or changing package boundaries. Do not add more requires to work around a package conflict.

### 8.5. Resolution succeeds but API access fails

A module may be resolved successfully, yet source code still cannot access a package. Also check `exports`, qualified exports, and Java access modifiers of the types/members.

Resolution and package accessibility are related but distinct checks.

## 9. Module graph debugging workflow

When the application reports a module error, proceed step by step:

1. Identify the root modules selected by the launcher or compiler.
2. Confirm the module path and module finders contain the required dependencies.
3. Check the actual module names with `jar --describe-module` or `java --list-modules`.
4. Read `module-info.java` of the roots and direct dependencies.
5. Follow requires to construct the dependency closure.
6. Check for cycles, duplicate module names, and conflicting packages.
7. Use `--show-module-resolution` to observe the configuration created by the launcher.
8. If resolution succeeds but imports fail, check exports and access permissions.
9. If the error involves ServiceLoader, check `uses`, `provides`, and consider service binding.

Do not assume every module error is caused by the module path. An error may lie in the module name, root set, dependency descriptor, package exports, or service configuration.

## 10. Module graph design principles

- Choose explicit root modules for the application or plugins.
- Declare direct dependencies in the module that actually needs them.
- Keep the dependency graph directed and acyclic.
- Use `requires transitive` only when the dependency is part of the API contract that clients need to read.
- Use `requires static` for compile-time dependencies that may be absent at runtime.
- Keep the module path consistent across compile, test, and runtime.
- Distinguish resolution from readability and package exports.
- Use configurations and layers when dynamic module groups or plugins need to be loaded.
- Observe module resolution before changing module descriptors to avoid fixing the wrong root cause.

## 11. Self-check

**Scenario 1:** The app module declares `requires com.acme.service;`. Which module depends on which?

**Answer:** App depends on service. The dependency edge is directed from app to service.

**Scenario 2:** Root module app requires service, and service requires model. Why does model appear in the configuration?

**Answer:** Because model lies in the dependency closure of root app. Java must resolve the required dependencies of the selected modules.

**Scenario 3:** Model is resolved, yet app does not read model. Is that a contradiction?

**Answer:** No. Including a module in the configuration does not mean every other module can read it. Readability requires checking requires and requires transitive.

**Scenario 4:** How do Configuration.resolve() and ModuleLayer differ?

**Answer:** Configuration describes the resolved module graph; ModuleLayer defines those modules at runtime and associates them with class loaders.

**Scenario 5:** When should resolveAndBind() be used?

**Answer:** When resolution needs the additional step of finding and including matching service providers in the configuration based on the services used by already resolved modules.

**Scenario 6:** Resolution succeeds, yet importing a package still fails. What should be checked?

**Answer:** Check whether the package is exported to the current module and whether the type/member has sufficient Java access visibility.

When reading a module graph, start from the root modules, follow each requires edge to determine the dependency closure, and then distinguish resolved modules, readable modules, and exported packages. These are the three layers of information that accurately explain configuring and running a modular application.