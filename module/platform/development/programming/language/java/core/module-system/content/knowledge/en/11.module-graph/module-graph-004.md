# Full dependency graph and redundant modules

In the Java Platform Module System (JPMS), the **module graph** is the graph of resolved modules for a runtime configuration or a module layer. This graph is formed from root modules, dependency directives such as `requires`, and service binding rules. It is not synonymous with all JARs sitting in the module path directory.

Therefore, when analyzing a modularized application, three sets should be distinguished:

- **Observable modules:** modules that module finders can locate from the module path and configured module sources.
- **Resolved modules:** modules actually brought into the configuration after starting from the roots and following dependencies/service binding.
- **Unnecessary or redundant modules:** modules that are observable or even already included in the configuration, yet the application does not actually need for the functionality under consideration.

Properly distinguishing these sets helps find missing dependencies, detect unnecessary modules, reduce runtime image size, and avoid adding options that make the runtime configuration larger than intended.

## 1. What does the module graph consist of?

You can picture the module graph as a set of nodes and module reading relationships:

~~~text
com.acme.app
    |
    | requires
    v
com.acme.service
    |
    | requires transitive
    v
com.acme.api
~~~

In the example, `com.acme.app` directly depends on `com.acme.service`. The service module depends on `com.acme.api` and passes readability of that dependency to modules using it via `requires transitive`.

When the application is launched with `com.acme.app` as the main module, the JVM resolves the app module and its required dependencies. The necessary modules are pulled into the configuration according to dependency relationships. The result is not merely a list of JARs; it is a module configuration with readability relationships defined according to JPMS.

Readability and package access permissions are two different conditions. One module can read another module yet still be unable to access types in an unexported package. Thus, when reading the graph, both module relationships and `exports`/`opens` directives must be checked.

## 2. Root modules determine the starting point

Resolution begins from a set of **root modules**. When running a modularized application:

~~~bash
java --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

The `com.acme.app` module is the specified root. The JVM reads this module's descriptor, finds the modules it requires, and continues following their dependencies.

Example descriptors:

~~~java
// com.acme.app
module com.acme.app {
    requires com.acme.service;
}
~~~

~~~java
// com.acme.service
module com.acme.service {
    requires transitive com.acme.api;
}
~~~

~~~java
// com.acme.api
module com.acme.api {
    exports com.acme.api;
}
~~~

If all three modules can be found, the graph will contain app, service, and api. The api module is pulled in because service requires it. There is no need to add each dependency to the run command if they are already declared accurately and can be found.

For an application running a main class on the classpath, root modules can be added using `--add-modules`:

~~~bash
java --module-path mods \
     --add-modules com.acme.service \
     -cp out \
     com.acme.app.Main
~~~

This option specifies the service module as an additional root. The dependencies of service continue to be resolved according to their descriptors.

## 3. The module path can contain modules not in the graph

Suppose a directory contains several JARs:

~~~text
mods/
├── com.acme.api.jar
├── com.acme.service.jar
├── com.acme.metrics.jar
├── com.acme.debug.tools.jar
└── com.acme.unused.adapter.jar
~~~

If the application only requires service and service only requires api, the graph may only need:

~~~text
com.acme.app
    └── com.acme.service
            └── com.acme.api
~~~

The metrics, debug tools, and unused adapter JARs can be found on the module path yet are not included in the configuration if they are not roots and are not pulled in by dependencies or service binding.

This means:

- Having a JAR file on the module path does not mean the module has been resolved.
- A module not in the graph cannot be assumed usable in the current layer.
- Adding a module as a root can cause that module and its dependencies to enter the configuration.
- Observe the actual graph rather than inferring from the file list in the directory.

A "redundant" module may simply be a module not used in the current run. If a module is added as a root or pulled in by service binding, it can become part of the graph even if the application does not call its APIs directly.

## 4. requires and dependency types

`requires` directives directly affect the dependency graph.

### Standard requires

~~~java
module com.acme.service {
    requires com.acme.api;
}
~~~

The service module needs to read the api module. If a required dependency cannot be found, resolution can fail before the application runs.

### requires transitive

~~~java
module com.acme.service {
    requires transitive com.acme.api;
}
~~~

Modules that read service are also granted readability to api. Use `transitive` only when service's public API exposes types belonging to api and consumers of service genuinely need to read that module.

### requires static

~~~java
module com.acme.annotations.integration {
    requires static com.acme.annotations;
}
~~~

A static dependency is mandatory at compile time but may be absent at runtime. If the required module is present in the runtime configuration, the readability relationship is established according to JPMS rules. If it is absent, the `requires static` directive alone does not force runtime resolution to fail.

Do not use `requires static` for dependencies where an execution path must load classes at runtime. If code invokes functionality needing that dependency, missing classes can still cause runtime errors.

## 5. Service binding can pull additional modules into the graph

JPMS supports service providers via `uses` and `provides ... with ...`. When resolution performs service binding, modules providing matching services can be included in the configuration.

Example application module:

~~~java
module com.acme.app {
    uses com.acme.spi.Formatter;
}
~~~

Provider module:

~~~java
module com.acme.formatter.json {
    requires com.acme.spi;

    provides com.acme.spi.Formatter
        with com.acme.formatter.json.JsonFormatter;
}
~~~

The provider can be pulled into the graph during service binding. With the Java launcher, the `--bind-services` option instructs resolution to perform binding:

~~~bash
java --module-path mods \
     --bind-services \
     -m com.acme.app/com.acme.app.Main
~~~

Therefore, a module that does not appear in the direct `requires` chain can still enter the graph if it provides a matching service and service binding is performed. When checking for redundant modules, service providers must also be accounted for rather than looking only at static dependencies.

Merely having a provider JAR on the module path does not automatically include it in every graph. Check `uses`, `provides`, observable modules, and the service binding option of the run.

## 6. Adding all modules on the module path can enlarge the graph

The `--add-modules` option allows adding root modules. Individual modules can be specified:

~~~bash
java --module-path mods \
     --add-modules com.acme.metrics,com.acme.debug.tools \
     -m com.acme.app/com.acme.app.Main
~~~

Or all observable modules on the module path can be requested as roots:

~~~bash
java --module-path mods \
     --add-modules ALL-MODULE-PATH \
     -m com.acme.app/com.acme.app.Main
~~~

`ALL-MODULE-PATH` causes all observable modules on the module path to be added as roots. This is useful for certain testing or exploratory scenarios, but it can pull extra modules and dependencies into the graph that the application does not need.

Consequences may include:

- Increasing the number of modules that must be resolved and checked.
- Exposing module conflicts or split packages that had not appeared in a smaller configuration.
- Pulling additional providers into the configuration when service binding is performed.
- Making the runtime image or execution environment larger in scope than necessary.
- Making actual dependencies harder to distinguish because many modules were explicitly added as roots.

In production configurations, select root modules according to the features that need to run. Do not use `ALL-MODULE-PATH` as a catch-all fix for missing-dependency errors; identify which modules are actually needed first.

## 7. Limiting the observable module set

`--limit-modules` restricts the set of modules that module resolution can observe. Example:

~~~bash
java --module-path mods \
     --limit-modules java.base,java.logging,com.acme.app \
     -m com.acme.app/com.acme.app.Main
~~~

This list limits the modules that can be used in the configuration. If a required dependency is not in the permitted observable set, resolution may fail with a module-not-found error.

This option is useful when testing a small configuration or verifying whether an application accidentally depends on an unexpected module. However, transitive dependencies and provider modules must be accounted for if the configuration uses service binding.

`--limit-modules` is not an operation that deletes JARs or removes modules from a directory. It adjusts the module finder/resolution scope for the launched process.

## 8. Detecting redundant modules with JDK tools

### Observing actual resolution

Use `--show-module-resolution`:

~~~bash
java --show-module-resolution \
     --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

The output helps identify which modules are resolved, which modules are roots, and where dependencies are found from. Comparing configurations with and without `--add-modules` or `--bind-services` reveals which modules are added to the graph.

### Analyzing dependencies with jdeps

`jdeps` analyzes dependencies at the bytecode level and can help identify the modules an application needs:

~~~bash
jdeps --module-path mods \
      --print-module-deps \
      app.jar
~~~

Or view a more detailed dependency list:

~~~bash
jdeps --module-path mods \
      --list-deps \
      app.jar
~~~

These commands assist static dependency analysis from bytecode. They may not fully detect dependencies loaded dynamically via reflection, class names generated from configuration, plugins, or runtime service mechanisms. Results should be combined with deployment configuration and testing of actual execution paths.

### Inspecting a JAR's descriptor

~~~bash
jar --describe-module --file mods/com.acme.service.jar
~~~

This command displays the module name and packaged directives. It helps distinguish which modules declare direct dependencies, which packages are exported, and which modules are automatic modules. The descriptor output alone does not prove that module participated in a specific process's graph.

## 9. Module graph and runtime images with jlink

When creating a custom runtime image, `jlink` uses the module graph to determine which modules need to be in the image. Example:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
      --add-modules com.acme.app \
      --output runtime-image
~~~

`--add-modules com.acme.app` selects the root module; its dependency closure is included in the image. If unnecessary roots are added, the image may contain more modules than expected.

Service binding can be combined when matching provider modules need to be included in the image:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
      --add-modules com.acme.app \
      --bind-services \
      --output runtime-image
~~~

When optimizing an image, explicitly determine the root modules and genuinely needed providers. A dynamically loaded dependency or class name constructed from configuration may not be recognized by bytecode analysis tools; the generated image must be tested with the features the application deploys.

## 10. Example distinguishing necessary and redundant modules

Suppose an application has dependencies:

~~~text
com.acme.app
    requires com.acme.service

com.acme.service
    requires com.acme.api

com.acme.api
    exports com.acme.api
~~~

The module path additionally has:

~~~text
com.acme.metrics
com.acme.debug.tools
com.acme.unused.adapter
~~~

If no dependency or service binding pulls the extra modules in, the minimal graph can be:

~~~text
com.acme.app
    └── com.acme.service
            └── com.acme.api
~~~

When running with `--add-modules ALL-MODULE-PATH`, the metrics, debug tools, and unused adapter modules are also added as roots. In that case, the graph is larger even though application code does not directly use them.

Analysis approach:

1. Run the normal configuration with `--show-module-resolution`.
2. Record the resolved modules.
3. Run `jdeps` to analyze bytecode dependencies.
4. Inspect descriptors and service declarations of the additional modules.
5. Check whether plugins or dynamically loaded features need those modules.
6. Only remove a module from the configuration after confirming no execution path needs it.

A module with no direct bytecode dependency may still be needed for service providers, plugins, or reflection. Therefore, do not remove a module solely because `jdeps` does not list it.

## 11. Common errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `FindException: Module ... not found` | Required module is not observable or is restricted by `--limit-modules` | Check the module path, module name, and permitted module set |
| Module is in the directory but missing from resolution output | Not a root, not pulled in by a dependency, or service binding did not run | Check roots, `requires`, `uses`/`provides`, and `--bind-services` |
| Split package error when adding ALL-MODULE-PATH | Additional modules create package conflicts | Narrow root modules and inspect packages of each JAR |
| Runtime image missing plugin/provider | Static dependency analysis missed dynamic loading paths or service binding | Add necessary roots/providers and test the image |
| Application runs in IDE but fails when run via launcher | IDE may configure extra module paths, roots, or JVM options | Compare the actual run command and `--show-module-resolution` output |

## 12. Graph optimization workflow

When looking for redundant modules or shrinking a runtime image, follow this workflow:

1. Identify the application module as the root.
2. Read all `requires` and transitive dependencies.
3. Review provider modules needed via `uses`/`provides`.
4. Run `--show-module-resolution` to observe the actual graph.
5. Use `jdeps` to find bytecode dependencies and cross-check against reflection/plugins/runtime config.
6. Test a minimal root configuration, avoiding adding `ALL-MODULE-PATH` unless needed.
7. Use `--limit-modules` or `jlink` when testing/creating a restricted module set.
8. Run functional tests on the final configuration to confirm no dynamically loaded modules or providers were omitted.

## 13. Key takeaways

The module graph is formed from root modules, dependencies, and service binding. The module path only supplies observable modules; it does not automatically put all modules into the configuration. `--add-modules ALL-MODULE-PATH` can add every observable module as a root, whereas `--limit-modules` restricts the observable module set.

To identify redundant modules, combine `--show-module-resolution`, `jdeps`, descriptors, and knowledge of the application's plugins/reflection/services. Keep only the graph needed for actual features; re-test the runtime image and dynamic paths before release.