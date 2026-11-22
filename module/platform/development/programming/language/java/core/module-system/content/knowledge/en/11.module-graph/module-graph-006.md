# Duplicate module names and resolution errors

## 1. Module names as identifiers in JPMS

In the Java Platform Module System (JPMS), each named module has a name declared in its module descriptor. This name is used to link requires, qualified exports, opens, uses, and provides directives across modules.

Example:

~~~java
module com.acme.orders {
    requires com.acme.customer.api;
}
~~~

Here, com.acme.orders and com.acme.customer.api are module names. Module names must be stable and unique within a resolved module configuration.

A module name is distinct from:

- A JAR filename, such as customer-api-2.1.jar.
- Maven or Gradle dependency coordinates.
- A Java package name, such as com.acme.customer.api.
- A library version, such as 2.1.0.

A module can record a version in its descriptor, yet the requires directive links by module name; it is not syntax for selecting a dependency version like Maven or Gradle.

Therefore, if two artifacts both declare the module name com.acme.customer.api, the module system treats them as two candidates for the same module identifier, even if their filenames or artifact versions differ.

## 2. Where do duplicate module names come from?

Module name conflicts commonly arise in the following situations:

- Two versions of the same library are both placed on the module path.
- Two different JARs declare the same Automatic-Module-Name attribute.
- Two legacy JARs have filenames that normalize to the same automatic module name.
- A library is packaged as both a modular JAR and an exploded module, and both appear on the search path.
- A dependency is brought onto the module path via multiple dependency branches or via both the application directory and a plugin directory.
- A JAR is copied into multiple configuration directories, causing the module finder to see multiple candidates with the same name.

Example:

~~~text
project/
├── mods/
│   ├── customer-api-1.8.jar
│   └── customer-api-2.1.jar
└── app/
~~~

If both JARs declare:

~~~java
module com.acme.customer.api {
    exports com.acme.customer.api;
}
~~~

then their module names are identical despite differing versions or filenames.

For JARs without module-info.class, Java can use the Automatic-Module-Name attribute in the manifest. If this attribute does not exist, the automatic module name is derived from the normalized JAR filename. Consequently, renaming files or placing two JARs with the same derived name onto the module path can cause a collision.

## 3. Why do two modules with the same name cause problems?

The module name is the key the module system uses to locate dependencies. When a module declares:

~~~java
module com.acme.application {
    requires com.acme.customer.api;
}
~~~

the resolver needs to find one module definition named com.acme.customer.api. The requires directive does not state whether the application wants version 1.8 or 2.1.

A module configuration cannot contain two independent definitions with the same name as if they were two different dependencies. If two copies with the same name are discovered in search locations, one copy can shadow the other according to the module finder's lookup rules; with invalid or indistinguishable inputs, discovery can raise a FindException.

The danger is that the application may resolve successfully yet use the wrong artifact compared to what the developer intended. When APIs differ across versions, errors may appear only at compile time or runtime, such as missing methods, changed data types, or incompatible behavior.

Therefore, a duplicate module name is not merely a naming issue. It is an issue of determining exactly which artifact represents a module identifier in the configuration.

## 4. Module path order and shadowing

The module path can contain multiple entries: modular JARs, exploded modules, or directories containing modules. Entries are supplied to the module finder in order.

With standard module finders, when the same module name appears in multiple entries on the module path, the candidate found first can be used and shadow candidates in later entries. Thus, module path order can affect which module is selected.

Example:

~~~bash
java --module-path "mods-v1:mods-v2" --module com.acme.application/com.acme.application.Main
~~~

If both mods-v1 and mods-v2 contain module com.acme.customer.api, the lookup result may depend on entry order. On Windows, the path separator is a semicolon:

~~~powershell
java --module-path "mods-v1;mods-v2" --module com.acme.application/com.acme.application.Main
~~~

Do not use module path order as a version management mechanism. The safe approach is to ensure each module name has only one intended artifact in the observable module set, and let Maven/Gradle manage the dependency graph and library versions.

If a custom ModuleFinder is used, lookup behavior also depends on that finder's implementation. Do not assume every finder follows the same policy as the Java launcher's default finder.

## 5. Automatic modules can cause name collisions

Legacy JARs without a module descriptor can still be placed on the module path. Java treats them as automatic modules.

An automatic module's name is determined in order:

1. If the manifest has a valid Automatic-Module-Name, use that name.
2. Otherwise, Java derives the name from the JAR filename according to normalization rules.

Example manifest:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.acme.legacy.logging
~~~

Two JARs can have different filenames yet declare the same Automatic-Module-Name:

~~~text
legacy-logging-1.0.jar
legacy-logging-2.0.jar
~~~

If both declare com.acme.legacy.logging, they produce candidates with the same module name.

For libraries transitioning to JPMS, set a stable Automatic-Module-Name starting with releases that do not yet have module-info.class. When releasing an official modular JAR, keep the module name consistent so consumers do not need to change requires.

Do not manually rename dependency files to mask a collision if the dependency graph still contains multiple incompatible versions. Remove redundant versions or choose one uniformly managed version.

## 6. Distinguishing duplicate module names from split packages

These two concepts are easily confused because both involve multiple artifacts, yet their causes differ.

**Duplicate module name**: multiple candidates declare the same module name, for example two JARs both named com.acme.customer.api.

**Split package**: two differently named modules both contain or export a package with the same name, for example:

~~~text
com.acme.customer.api
    package com.acme.shared.model

com.acme.order.api
    package com.acme.shared.model
~~~

When a module reads both modules and both export package com.acme.shared.model, the module graph is inconsistent. Resolution can fail with a ResolutionException due to a split package.

Example:

~~~java
module com.acme.customer.api {
    exports com.acme.shared.model;
}

module com.acme.order.api {
    exports com.acme.shared.model;
}

module com.acme.application {
    requires com.acme.customer.api;
    requires com.acme.order.api;
}
~~~

Module com.acme.application reads both modules and sees the same package from two sources. This is a package conflict, not a duplicate module name.

Typical resolutions include:

- Moving the shared package into a single owning module.
- Moving types into distinct packages per owning module.
- Adjusting API boundaries so two modules do not export the same package to a single consumer.
- Removing duplicate classes from artifacts if they are unintended copies.

Renaming a module does not solve a split package if the package remains shared and read together.

## 7. The module graph and resolution steps

Module resolution builds a module configuration based on the root module set and required dependencies.

The process can be described as:

1. **Find observable modules**: module finders locate modules by name from the module path, system modules, or configured sources.
2. **Select root modules**: the launcher determines root modules from the launched module, --add-modules, or corresponding launch rules.
3. **Read requires**: for each root, the resolver reads the module descriptor and gathers direct dependencies.
4. **Find dependencies recursively**: each resolved module continues pulling in the modules it requires.
5. **Check consistency**: the resolver verifies module names, required dependencies, conflicting packages, and module graph constraints.
6. **Create configuration**: if the graph is valid, Java creates a Configuration containing the resolved modules and readability relationships among them.
7. **Define modules in a runtime layer**: the module layer associates resolved modules with class loaders according to how the app launches or creates layers.

Example:

~~~text
Root: com.acme.application
       |
       +-- requires com.acme.customer.api
       |        |
       |        +-- requires com.acme.model
       |
       +-- requires com.acme.logging.api
                |
                +-- requires com.acme.model
~~~

Module com.acme.model is shared by two branches. This is a valid graph as long as there is only one module definition with that name and packages/dependencies do not conflict.

If a required dependency cannot be found, the graph cannot be completely resolved. If the graph contains two modules exporting the same package to a consumer that reads both, the graph is also invalid.

## 8. Common resolution errors

### FindException

FindException belongs to the module discovery stage. It can appear when:

- A required module is not found.
- The module finder cannot read or parse the module descriptor.
- A modular JAR is corrupted or its descriptor is invalid.
- Search inputs contain a module candidate that cannot be processed under finder rules.

Common example message:

~~~text
java.lang.module.FindException: Module com.acme.customer.api not found
~~~

Check the module path, actual module name, whether the JAR file exists, and whether the descriptor is readable.

### ResolutionException

ResolutionException occurs when modules are found, yet the dependency configuration cannot form a valid module graph.

A classic example is a split package: two modules read by a consumer both export an identically named package.

An example message may indicate a package exported from multiple modules:

~~~text
java.lang.module.ResolutionException:
Modules com.acme.customer.api and com.acme.order.api
export package com.acme.shared.model to module com.acme.application
~~~

Identify the two involved modules, the conflicting package, and the consumer module reading both. Then fix package boundaries or the dependency graph.

### InvalidModuleDescriptorException

This error relates to an invalid or unparseable module descriptor. Check module-info.java and the packaged artifact: module name, requires/exports syntax, declared packages, and JAR structure.

### LayerInstantiationException

This error can appear when the runtime cannot define a module layer from the resolved configuration. Causes may relate to how modules are mapped to class loaders, packages, or runtime state. If resolution succeeded yet layer creation failed, examine the stack trace at the defineModules step rather than only checking requires.

## 9. Module versions do not automatically resolve duplicate names

A module descriptor can carry version metadata:

~~~java
module com.acme.customer.api {
    exports com.acme.customer.api;
}
~~~

A module's version, if recorded into the descriptor during packaging, is metadata. Standard requires syntax only specifies the module name:

~~~java
module com.acme.application {
    requires com.acme.customer.api;
}
~~~

There is no expression such as requires com.acme.customer.api version 2.1.

Therefore, JPMS does not replace a dependency manager. Maven or Gradle is responsible for selecting artifacts/versions according to the project's dependency graph; the module system uses module names in artifacts to link modules at compile/runtime.

A project can choose the right Maven coordinates and still hit a module name collision if two different artifacts declare the same module name. Conversely, two artifacts having different filenames does not guarantee they have different module names.

Check both layers of information:

- Dependency manager: which artifacts and versions are brought into runtime.
- Module descriptor: by which module name each artifact is identified.

## 10. How to detect duplicate module names and unwanted artifacts

First, list the contents and descriptors of suspect JARs:

~~~bash
jar --describe-module --file libs/customer-api-1.8.jar
jar --describe-module --file libs/customer-api-2.1.jar
~~~

If both report the name com.acme.customer.api, the dependency graph contains two artifacts with the same module name.

To view JDK system modules:

~~~bash
java --list-modules
~~~

This command lists modules of the runtime image; it does not replace checking all non-JDK dependencies on the application's module path.

To observe modules resolved at runtime:

~~~bash
java --show-module-resolution \
     --module-path mods \
     --module com.acme.application/com.acme.application.Main
~~~

The resolution log shows which modules are found and which dependencies are included in the configuration. Combine this with jar --describe-module to cross-reference module names against specific artifacts.

If using Maven or Gradle, inspect the runtime dependency report to find multiple versions or multiple paths pulling in the same library. After removing redundant dependencies, re-run with --show-module-resolution to verify the new configuration.

## 11. Resolution error handling workflow

When an application fails to start due to module resolution, handle it in order:

1. **Read the initial error**: determine whether it is a module discovery, descriptor, graph, or layer creation error.
2. **Identify the involved module names**: take the names from the error message or module-info.java.
3. **Inspect artifacts**: run jar --describe-module on each suspect JAR.
4. **Inspect the dependency graph**: determine which modules pull the artifact into runtime and whether multiple versions exist.
5. **Check package exports**: if the error is a split package, find the package exported from multiple modules and the consumer reading those modules.
6. **Fix dependencies or module boundaries**: choose one artifact per module name, consolidate shared packages into one module, or adjust requires/exports to match the actual API.
7. **Re-run and observe**: use --show-module-resolution to confirm the module graph is constructed properly.

Do not fix by adding a slew of --add-reads, --add-exports, or --add-opens when the root error is a duplicate module or split package. Those options neither remove duplicate-named candidates nor merge split packages.

## 12. Example illustrating an error from duplicate dependencies

Suppose an application has two dependency branches:

~~~text
com.acme.application
    |
    +-- com.acme.order
    |       |
    |       +-- com.acme.customer.api 1.x
    |
    +-- com.acme.reporting
            |
            +-- com.acme.customer.api 2.x
~~~

If both versions of the customer API are packaged as modules named com.acme.customer.api, the module path has multiple candidates for the same name.

The solution is to align dependency versions so both com.acme.order and com.acme.reporting use one compatible version, or upgrade an intermediate module to eliminate the old dependency.

Do not rename the JAR file and assume the problem is solved: the module name inside the descriptor remains the identifier JPMS uses.

If two versions genuinely must coexist independently, isolate them using separate class loaders or module layers and handle API compatibility explicitly. Putting both into the same module configuration under the same module name does not create two independent versions.

## 13. Key takeaways

- The module name is the identifier used in requires and module resolution; JAR filenames and dependency versions do not replace that name.
- Two artifacts can have different filenames yet still declare the same module name.
- Automatic modules can collide in name via Automatic-Module-Name or normalized filenames.
- Module path order and module finder behavior can affect which candidate is found; do not use shadowing to manage versions.
- Duplicate module names differ from split packages: one error is colliding module identifiers, the other is overlapping packages among read modules.
- FindException usually relates to finding or reading modules; ResolutionException usually relates to an inconsistent module graph.
- Module version metadata is not a version selection mechanism in requires; use Maven/Gradle to manage dependencies.
- Use jar --describe-module, dependency reports, and java --show-module-resolution to identify which artifacts and modules are actually resolved.

When troubleshooting resolution errors, trace from the module name in the message to the corresponding descriptor and artifact. Correctly identifying duplicate candidates, the dependency pulling them in, or shared packages lets you fix the graph in a controlled way.