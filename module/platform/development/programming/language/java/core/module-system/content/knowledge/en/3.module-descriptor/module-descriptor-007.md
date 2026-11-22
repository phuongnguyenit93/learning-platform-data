# Static Descriptors and the Runtime Module Graph

In the Java Platform Module System (JPMS), a **module descriptor** describes the contract and dependencies declared by a module; the **runtime module graph** is the graph of modules actually resolved by the JVM for a given run. The two concepts are closely related yet distinct: the descriptor is metadata packaged with the module, whereas the graph is formed when the JVM combines descriptors with observable modules, selected root modules, and launch configuration.

Understanding this difference helps explain why a module can compile successfully yet fail to run, why a library on the module path is not guaranteed to be included in the runtime configuration, and why options such as `--add-modules` or `--add-reads` can alter runtime behavior without modifying `module-info.java`.

## 1. A Module Descriptor Is a Static Description

A named module typically declares its descriptor in the `module-info.java` source file. When compiled, `javac` generates the binary file `module-info.class`. This file sits at the root of a modular JAR and is read by the JVM when resolving modules.

Example descriptor of a library:

~~~java
module com.acme.service {
    requires transitive com.acme.api;
    exports com.acme.service.api;
    uses com.acme.service.spi.Engine;
}
~~~

The descriptor above declares static information:

- The module name is `com.acme.service`.
- The module depends on `com.acme.api` and propagates readability of this dependency to modules using it via `requires transitive`.
- The `com.acme.service.api` package is the exported API.
- The module uses a service of type `com.acme.service.spi.Engine`.

A descriptor can contain other directives such as `requires static`, `exports ... to ...`, `opens`, `provides ... with ...`. These declarations describe the module's requirements, access permissions, and service relationships.

The descriptor does not store a list of all JARs present on the machine, does not record which modules were loaded by the JVM in a specific process, and does not contain the complete runtime module graph. It is an input for the compiler and the JVM to resolve configurations.

## 2. What Is the Runtime Module Graph?

When launching an application via the module path, the JVM locates observable modules, selects root modules, and then follows dependency directives to resolve a configuration. The result is a set of resolved modules together with module readability relationships among them.

You can picture this simply:

~~~text
module descriptor (.class)
        |
        |  module path + root modules + runtime options
        v
module resolution
        |
        v
resolved configuration / module graph
        |
        v
module layer in the JVM
        |
        v
class loading, access checks, and execution
~~~

In the graph, modules are the nodes. `requires` relationships establish module readability according to JPMS rules. Modules chosen as roots pull in the required modules along the dependency graph. Modules that merely happen to sit in the module path directory without belonging to the resolved configuration may not become members of the running layer.

The module graph is tied to a specific configuration and module layer. An application can create additional module layers at runtime; therefore, not every module present in the entire process necessarily belongs to the initial boot layer.

## 3. Example: From Descriptors to the Runtime Graph

Suppose there are three modules:

~~~text
com.acme.api
    exports com.acme.api

com.acme.service
    requires transitive com.acme.api
    exports com.acme.service.api

com.acme.app
    requires com.acme.service
~~~

The corresponding descriptors can be written as follows:

~~~java
// com.acme.api/module-info.java
module com.acme.api {
    exports com.acme.api;
}
~~~

~~~java
// com.acme.service/module-info.java
module com.acme.service {
    requires transitive com.acme.api;
    exports com.acme.service.api;
}
~~~

~~~java
// com.acme.app/module-info.java
module com.acme.app {
    requires com.acme.service;
}
~~~

Compile all three modules with JDK 21:

~~~bash
javac --module-source-path src -d out \
      -m com.acme.api,com.acme.service,com.acme.app
~~~

Launch the application module:

~~~bash
java --module-path out \
     -m com.acme.app/com.acme.app.Main
~~~

When `com.acme.app` is the main module being launched, it is the root of the application configuration. The JVM resolves `com.acme.service` because the application declares `requires com.acme.service`. The service module in turn requires `com.acme.api`, so the API module is also brought into the graph.

The readability relationships mean the following:

- `com.acme.service` reads `com.acme.api` because it has `requires transitive com.acme.api`.
- `com.acme.app` reads `com.acme.service` because it has `requires com.acme.service`.
- `com.acme.app` also reads `com.acme.api` because the service's dependency is declared `transitive`.

If the directive in the service module is changed to a regular `requires com.acme.api`, `com.acme.app` does not automatically gain permission to read `com.acme.api` just because it reads service. If the application's code needs to import types from the API module, the application should declare a direct dependency or service should expose the dependency relationship with `requires transitive` when appropriate for the API contract.

Reading a module and accessing a package are two separate steps. Even though `com.acme.app` reads `com.acme.api`, the application can only access public types in packages that the API module has exported to the application under JPMS rules.

## 4. How the JVM Forms the Runtime Configuration

You can view the module resolution process in steps:

1. **Identify module sources:** the JVM gathers modules from the module path, the JDK runtime image, and other configured module sources.
2. **Select root modules:** the main module being launched and additional roots selected by runtime options.
3. **Follow dependencies:** the JVM reads `requires` directives of the roots and pulled-in modules, then locates the corresponding modules.
4. **Resolve services when requested:** the service binding process can bring matching service-provider modules into the configuration.
5. **Create the module layer:** resolved modules are defined in a layer for the JVM to load classes and execute the program.

If a required dependency cannot be found or the graph has a conflict, resolution can fail before the main class runs. A common example is `FindException: Module ... not found`.

### Root Modules and Observable Modules

The module path is where the JVM looks for modules, not a guarantee that every module in it will be placed into the graph. Root modules determine the starting point of the resolution process. When running with `-m module/class`, the specified module is the main application module.

The `--add-modules` option adds root modules:

~~~bash
java --module-path mods \
     --add-modules com.acme.tools \
     -m com.acme.app/com.acme.app.Main
~~~

In this example, `com.acme.tools` is requested as an additional root even though the application module has no direct `requires` dependency on it. The module must still be locatable and the graph must be valid.

The `--limit-modules` option limits the set of observable modules during resolution. It is useful when you want to restrict the runtime configuration, provided you ensure required dependencies remain within the set of observable modules.

## 5. Descriptors and Runtime Options Act Differently

A descriptor is metadata packaged inside a module. Certain JVM options can adjust the graph or access permissions for a single run without modifying the compiled descriptor.

| Component | Role |
|---|---|
| `requires` | Declares a module's mandatory dependency |
| `requires transitive` | Propagates dependency readability to modules depending on the current module |
| `requires static` | Dependency needed at compile time that may be absent at runtime |
| `--add-modules` | Adds modules as roots for resolution |
| `--limit-modules` | Limits the set of observable modules |
| `--add-reads` | Adds module readability relationships in the runtime configuration |
| `--add-exports` | Adds access to an exported package for target modules |
| `--add-opens` | Opens a package for deep reflection at runtime |
| `--bind-services` | Instructs resolution to perform service binding to locate matching provider modules |

For example, while migrating a legacy application, read access can be granted from a named module to the unnamed module:

~~~bash
java --add-reads com.acme.app=ALL-UNNAMED \
     --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

This option adds the readability relationship for that run. It does not write a new directive back into `module-info.class`. Similarly, `--add-exports` and `--add-opens` adjust access permissions at launch time without altering descriptors inside JARs.

These options should be treated as intentional runtime configuration, compatibility tools, or diagnostics. If a relationship is a stable requirement of the module, express it in the descriptor whenever JPMS supports the corresponding directive.

## 6. requires static and the Difference Between Compile Time and Runtime

`requires static` is commonly used for compile-time support dependencies, such as annotations or APIs needed only in certain execution modes:

~~~java
module com.acme.domain {
    requires static com.acme.annotations;
    exports com.acme.domain.api;
}
~~~

At compile time, the `com.acme.annotations` module must be locatable to resolve the types and annotations used by the source code. At runtime, the static dependency may be absent. If that module is present in the runtime configuration, the corresponding readability relationship is still established per JPMS rules; if absent, the `requires static` directive alone does not force the runtime to fail.

This does not mean every dependency can be declared static. If executing code needs to load a dependency's class to run a feature, the absence of that module or class can still lead to errors when that execution path is invoked. Distinguish compile-time-only dependencies from dependencies needed for runtime behavior.

## 7. Service Binding Can Expand the Runtime Graph

Descriptors support services with two directives:

- `uses` declares that a module consumes a service.
- `provides ... with ...` declares that a module supplies an implementation.

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

Having a provider on the module path does not mean it is always included in every graph. When resolution performs service binding, modules providing requested services can be pulled into the configuration. With the Java launcher, the `--bind-services` option requests this binding behavior:

~~~bash
java --module-path mods \
     --bind-services \
     -m com.acme.app/com.acme.app.Main
~~~

When using `ServiceLoader`, check the `uses` and `provides` declarations, the presence of the provider module, and how the runtime configuration performs service binding. This avoids assuming that merely copying the provider JAR into the `mods` directory guarantees the implementation will be discovered.

## 8. Observing the Module Graph at Runtime

The JDK provides tools to view resolved modules and inspect the actual configuration.

### Displaying the Resolution Process

Add `--show-module-resolution` to the launch command:

~~~bash
java --show-module-resolution \
     --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

The JVM prints information about resolved modules and the dependency relationships it detects. This is a quick way to determine which modules were included in the configuration and from which source dependencies were found.

### Inspecting Modules with the jar Tool

To view the descriptor packaged in a JAR:

~~~bash
jar --describe-module --file mods/com.acme.service.jar
~~~

This command describes the module declared by the JAR. It helps inspect static metadata of the JAR, but does not replace observing the graph of a specific running process.

### Observing the Boot Layer from Java Code

You can view modules in the boot layer via the API:

~~~java
import java.util.Comparator;

public class ModuleGraphInspection {
    public static void main(String[] args) {
        ModuleLayer.boot()
            .modules()
            .stream()
            .map(Module::getName)
            .sorted(Comparator.naturalOrder())
            .forEach(System.out::println);
    }
}
~~~

`ModuleLayer.boot().modules()` returns the modules belonging to the boot layer. This set is useful for observing the initial layer configuration, but does not represent every observable module on the module path, nor does it include modules defined only in other custom layers.

You can check a specific readability relationship:

~~~java
Module appModule = ModuleGraphInspection.class.getModule();
Module apiModule = ModuleLayer.boot()
    .findModule("com.acme.api")
    .orElseThrow();

System.out.println(appModule.canRead(apiModule));
~~~

A result of `true` indicates that the module containing the running class can read the API module in the current configuration. If the API module does not belong to the boot layer, search in the corresponding layer instead of assuming it resides in the boot layer.

## 9. Common Errors When Analyzing the Runtime Graph

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| `FindException: Module ... not found` | Required dependency is missing from observable module sources | Check module path, module name, and `requires` |
| Module is in the `mods` directory but absent from the graph | Module is not a root and is not pulled in by a dependency or service binding | Check roots, `requires`, `--add-modules`, and `--bind-services` |
| Application cannot read a module even though the JAR is present | Module was not resolved into the configuration or lacks a readability relationship | Check graph, `requires`, and `--add-reads` |
| Module is readable but types are inaccessible | Package has not been exported to the consuming module | Check `exports` or `--add-exports` |
| Framework is blocked during reflection | Package has not been opened for deep reflection | Check `opens` or `--add-opens` |
| Compiles successfully but runtime is missing classes | Dependency is compile-time only or module/class is missing at runtime | Distinguish `requires static` from genuinely required runtime dependencies |
| Service provider is not found | Missing `uses`/`provides`, unobservable provider, or service binding not performed | Check descriptor and `--bind-services` |

## 10. Practical Diagnostic Workflow

When a modularized application runs differently than expected, check step by step:

1. **Read descriptors:** run `jar --describe-module` on the application JAR and related libraries to confirm module names, `requires`, `exports`, `opens`, `uses`, and `provides`.
2. **Check module sources:** confirm the module path points to the right directories/JARs and required modules are observable.
3. **Check root modules:** identify which module is launched and any additional roots passed via `--add-modules`.
4. **Observe resolution:** run with `--show-module-resolution` to view the actual graph.
5. **Check readability and exports:** distinguish an unreadable-module error from an unexported-package error.
6. **Check service binding:** if using ServiceLoader, confirm providers are found and binding is enabled when the configuration needs it.
7. **Compare runtime options:** check whether `--add-reads`, `--add-exports`, `--add-opens`, or `--limit-modules` alter the intended configuration.

Do not look solely at the contents of the module path directory to conclude that a module is active in the process. Check the resolved configuration and actual layer.

## 11. Key Takeaways

A module descriptor is a **static description** compiled and packaged with a module. It declares what the module wants to depend on, which packages it exposes, and how it participates in services. The runtime module graph is the **actual configuration** that the JVM constructs from descriptors, observable module sources, root modules, and launch options.

Descriptors shape the relationships a module requests; runtime resolution decides which modules actually participate in a run's configuration. When you need to find out why a module is or is not in a process, inspect root modules, the dependency graph, service binding, and the output of `--show-module-resolution` instead of reading `module-info.java` alone.