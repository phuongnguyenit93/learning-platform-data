# Module closure in jlink

When creating a runtime image with `jlink`, you select one or more root modules. The tool resolves the modules they depend on and links the required set of modules into the image. This set is called the module closure.

Understanding module closure helps you control the contents of a runtime image, detect missing dependencies, and avoid bundling too many modules into your distribution. It also explains why an application that declares only a single root module still ends up with many JDK and application modules in its runtime image.

This guide uses JDK 17 or later and explains how to choose root modules, how `requires` directives and service binding affect the closure, how to analyze dependencies with `jdeps`, and how to inspect the runtime image after linking.

## 1. What is module closure?

A Java module declares its dependencies using `requires` directives in `module-info.java`. When a module is chosen as a root module, the module system must locate and resolve the modules it needs to operate.

For example, an application module `com.example.app` declares:

~~~java
module com.example.app {
    requires com.example.lib;
    requires java.logging;
}
~~~

When `com.example.app` is the root module, the module resolver needs to find:

- `com.example.app`: the selected root module.
- `com.example.lib`: a dependency declared by the application.
- `java.logging`: another dependency declared by the application.
- `java.base`: the foundational module that every normal Java module implicitly depends on.

Those dependencies can in turn declare their own dependencies. Resolution continues until all required dependencies have been resolved. The set of modules reachable from the root modules and their resolved dependencies forms the module graph; the module closure is the set of modules that must be included in the runtime image according to that graph.

An overview looks like this:

~~~text
com.example.app
├── com.example.lib
│   └── java.base
├── java.logging
│   └── java.base
└── java.base
~~~

This diagram only illustrates direct and transitive dependency relationships. In an actual module graph, a module may be required by multiple modules, yet it is resolved only once.

## 2. Root modules determine the starting point

`jlink` uses the `--add-modules` option to specify the root modules to link.

Syntax:

~~~text
jlink --module-path <module-path> --add-modules <module>[,<module>...] --output <directory>
~~~

Example selecting a single application module:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --output runtime
~~~

Where:

- `--module-path` specifies where to find modules, including the JDK system JMODs and application modules.
- `--add-modules` selects the root module(s).
- `--output` specifies the runtime image directory.

You can select multiple root modules, separated by commas:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app,com.example.tool --output runtime
~~~

Each root module can pull in its own dependencies. If two roots both depend on `java.logging`, that module only needs to appear once in the image.

A special value is `ALL-MODULE-PATH`, which selects all observable modules on the module path as roots:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules ALL-MODULE-PATH --output runtime
~~~

This approach is convenient when experimenting or when you need to link all available modules, but it typically produces a larger image because modules not needed by the application also become roots. For production, start from the application modules that actually need to run.

## 3. How requires directives affect the closure

### 3.1. requires

`requires` declares a module dependency. When module A requires module B, B must be found and resolved for A to work.

~~~java
module com.example.app {
    requires com.example.lib;
}
~~~

If `com.example.lib` is not on the module path or cannot be resolved, compilation or linking will report an error accordingly.

### 3.2. requires transitive

`requires transitive` both declares a dependency and allows modules that read the current module to also read the required module under readability rules.

~~~java
module com.example.api {
    requires transitive com.example.model;
    exports com.example.api;
}
~~~

If another module requires `com.example.api`, the `com.example.model` dependency also becomes part of the module graph to be resolved. The `transitive` modifier primarily affects module readability for dependent modules; it is not a command to add arbitrary modules outside the dependency graph.

### 3.3. requires static

`requires static` indicates a dependency that is required at compile time but may be absent at runtime:

~~~java
module com.example.app {
    requires static com.example.optional;
}
~~~

This dependency is optional at runtime. If the optional module is present and resolved, it can participate in the graph; if absent, this directive alone does not force the runtime to include it.

Be careful if the application actually loads classes from the optional module via reflection, configuration, or class names read at runtime. When that feature is enabled, the module must be present in the runtime image and resolved. You can add it explicitly with `--add-modules`.

### 3.4. requires static transitive

Both modifiers can be combined:

~~~java
module com.example.api {
    requires static transitive com.example.optional.api;
}
~~~

The dependency remains optional at runtime, while readability is propagated to dependent modules according to `transitive` rules. When packaging, verify whether the optional module is actually used in your runtime configuration.

## 4. Module closure and module readability are different concepts

Module closure tells you which modules are resolved and present in the graph. Readability determines whether one module can read public types from another module under JPMS rules.

Having a module in the runtime image does not automatically make all of its packages accessible.

Different directives serve different roles:

| Directive | Role |
|---|---|
| `requires` | Declares a dependency and readability of the required module |
| `requires transitive` | Propagates readability of the dependency to dependent modules |
| `exports` | Allows other modules to access public types in the exported package |
| `opens` | Allows deep reflective access to the package within the opened scope |
| `uses` | Declares that the module uses a service |
| `provides ... with ...` | Declares that the module provides an implementation for a service |

For example, module A may be in the closure, yet its internal package is not exported to module B. B still cannot access types in that package through normal access.

If an error occurs because a package is not exported or opened, adding the module to `--add-modules` will not solve the problem. You need to check the module descriptor and package access permissions.

## 5. Service binding can expand the module closure

Java `ServiceLoader` allows an application to discover service implementations at runtime. A module that consumes a service declares `uses`; a module that supplies an implementation declares `provides`.

For example, an application module can declare:

~~~java
module com.example.app {
    requires com.example.spi;
    uses com.example.spi.Greeting;
}
~~~

A provider module declares:

~~~java
module com.example.provider {
    requires com.example.spi;
    provides com.example.spi.Greeting
        with com.example.provider.DefaultGreeting;
}
~~~

If the provider is not directly required by any root module, normal dependency resolution alone may not include the provider in the image.

The `--bind-services` option instructs `jlink` to link provider modules for services used by modules in the graph, along with their required dependencies:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --bind-services --output runtime
~~~

When to use it:

- The application uses `ServiceLoader`.
- The provider is found on the module path.
- The provider is not pulled into the graph by a regular `requires`.
- The runtime image needs to contain the implementation for service discovery to work.

`--bind-services` can make the image larger because it adds provider modules and their dependencies. Enable it only when the application needs service binding or when you want the runtime image to include the corresponding providers.

You can ask `jlink` which modules provide a service:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --suggest-providers com.example.spi.Greeting
~~~

The service name must be the fully qualified class name of the service interface. This command helps locate available providers on the module path.

## 6. Hands-on example: two modules and dependency closure

The following example creates two modules:

- `com.example.lib`: provides the `MessageService` class.
- `com.example.app`: calls that library and uses `java.logging`.

Project structure:

~~~text
project/
├── src/
│   ├── com.example.lib/
│   │   ├── module-info.java
│   │   └── com/example/lib/MessageService.java
│   └── com.example.app/
│       ├── module-info.java
│       └── com/example/app/Main.java
├── mods/
└── runtime/
~~~

Contents of `src/com.example.lib/module-info.java`:

~~~java
module com.example.lib {
    exports com.example.lib;
}
~~~

Contents of `src/com.example.lib/com/example/lib/MessageService.java`:

~~~java
package com.example.lib;

public class MessageService {
    public String message() {
        return "Hello from module closure!";
    }
}
~~~

Contents of `src/com.example.app/module-info.java`:

~~~java
module com.example.app {
    requires com.example.lib;
    requires java.logging;
}
~~~

Contents of `src/com.example.app/com/example/app/Main.java`:

~~~java
package com.example.app;

import com.example.lib.MessageService;
import java.util.logging.Logger;

public class Main {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger(Main.class.getName());
        logger.fine("Application started");
        System.out.println(new MessageService().message());
    }
}
~~~

From the `project` root directory, compile the library first:

~~~powershell
New-Item -ItemType Directory -Force -Path mods/com.example.lib, mods/com.example.app | Out-Null
javac -d mods/com.example.lib src/com.example.lib/module-info.java src/com.example.lib/com/example/lib/MessageService.java
~~~

Compile the application with the module path containing the library module:

~~~powershell
javac --module-path mods -d mods/com.example.app src/com.example.app/module-info.java src/com.example.app/com/example/app/Main.java
~~~

Run directly from the compiled module directory:

~~~powershell
java --module-path mods --module com.example.app/com.example.app.Main
~~~

Output:

~~~text
Hello from module closure!
~~~

Create the runtime image specifying the application module as the root:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --output runtime
~~~

Even though only `com.example.app` is selected, the image must include its required dependencies, namely `com.example.lib`, `java.logging`, and `java.base`. Transitive dependencies of these modules are also resolved.

Run the application using the newly created Java runtime:

~~~powershell
.\runtime\bin\java.exe -m com.example.app/com.example.app.Main
~~~

Output:

~~~text
Hello from module closure!
~~~

On Linux/macOS, use a colon in the module path and invoke the `runtime/bin/java` executable:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --output runtime
./runtime/bin/java -m com.example.app/com.example.app.Main
~~~

This example shows that `--add-modules` chooses the starting point; `jlink` automatically resolves declared dependencies instead of requiring you to list every JDK module manually.

## 7. Analyzing dependencies before linking with jdeps

`jdeps` is a class-level and module-level dependency analysis tool. It is useful for inspecting a compiled JAR or application to see which platform modules are referenced.

For an application JAR and its dependent libraries:

~~~powershell
jdeps --print-module-deps --module-path "lib/*" app.jar
~~~

The command prints the required modules based on static dependency analysis, typically as a comma-separated list. The output can help guide root module selection or review your linking configuration.

To view detailed dependencies:

~~~powershell
jdeps --list-deps --module-path "lib/*" app.jar
~~~

For a multi-release JAR, specify the release to analyze:

~~~powershell
jdeps --multi-release 17 --print-module-deps --module-path "lib/*" app.jar
~~~

Keep the limitations of `jdeps` in mind:

- Analysis is primarily based on identifiable references in bytecode.
- Class names constructed from configuration, reflection, or dynamic loading may not be fully detected.
- Service providers, plugins, or conditionally loaded runtime modules must be checked separately.
- Dependencies of external libraries must be provided on the appropriate classpath or module path for complete results.

Use `jdeps` as analytical evidence, then test against the actual runtime image.

## 8. Inspecting the module closure in a runtime image

After `jlink` finishes, use the Java launcher inside the image to list the linked modules:

~~~powershell
.\runtime\bin\java.exe --list-modules
~~~

On Linux/macOS:

~~~bash
./runtime/bin/java --list-modules
~~~

For the two-module example, look for these names:

~~~text
com.example.app
com.example.lib
java.base
java.logging
~~~

Displayed versions may vary by JDK, and a real-world image may contain additional modules required by other components. Use this list to confirm that critical modules are present.

You can inspect the module descriptor of the application module with:

~~~powershell
.\runtime\bin\java.exe --describe-module com.example.app
~~~

`java --describe-module` displays the module description in the runtime environment being invoked. Use the launcher inside the image to verify the module linked in that image itself.

Check for the launcher and runtime directories:

~~~powershell
Get-ChildItem runtime
Get-ChildItem runtime/bin
~~~

Do not rely solely on `jlink` exiting without errors. Run the application and test service providers, reflection, resources, native libraries, and dynamically loaded features.

## 9. Restricting the module set with --limit-modules

`--limit-modules` limits the set of modules observable to the tool during resolution. This option can be useful when you want to control the module environment and prevent unwanted modules from entering the graph.

Example:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --limit-modules java.base,java.logging,com.example.lib,com.example.app --output runtime
~~~

The limited list must include the required modules along with their dependencies. If you exclude a module needed by a mandatory dependency, linking will fail because the graph cannot be resolved.

`--limit-modules` is not a substitute for declaring dependencies properly in `module-info.java`. Before applying it, determine the actual graph using `jdeps`, module descriptors, and trial linking. When there is no clear need to restrict observability, specifying root modules with `--add-modules` is usually sufficient.

## 10. Static dependencies and dynamic dependencies

Not every runtime dependency is fully expressed by `requires` directives.

Cases to watch out for:

| Usage | Why it may be missing from the static closure | How to handle |
|---|---|---|
| `requires static` | Dependency may be absent at runtime | Add the module explicitly if the runtime feature needs it |
| `ServiceLoader` | Provider is not necessarily required directly | Consider `--bind-services` or add the provider module |
| Reflection with class names from configuration | Class name does not appear as a normal symbolic reference | Add the module and test the reflection code path |
| Configuration-loaded plugins | Plugin is only known at runtime | Identify plugin modules and include them on the module path/image |
| JNI or native libraries | Native dependencies do not always appear in the Java module graph | Package appropriate native content and test per OS/architecture |
| Resources loaded by name | Resource may not be discovered from class dependencies | Verify the resource is in the image at the expected path |

If the application uses dynamic class names, plugins, or native code, compile a list of required components based on deployment configuration and real testing. `jlink` can only link modules that are observable on the module path.

## 11. Reducing image size while keeping the closure correct

Module closure determines which modules are required. Image optimization options adjust content or storage format, but do not replace choosing the right dependencies.

Useful options include:

| Option | Effect |
|---|---|
| `--strip-debug` | Strips debug information from class files in the image |
| `--no-header-files` | Excludes header files from the image |
| `--no-man-pages` | Excludes man pages from the image |
| `--compress=1` | Compresses resources with ZIP-level compression |
| `--compress=2` | Compresses resources with ZIP and higher compression as supported by the JDK |

Example:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --strip-debug --no-header-files --no-man-pages --compress=2 --output runtime
~~~

Measure the image size and re-run tests after changing options. Never remove a module just to shrink the image if the application or a runtime feature still needs it.

## 12. Common errors when working with module closure

| Symptom | Common cause | How to fix |
|---|---|---|
| `Module ... not found` | Dependency module is missing from the module path | Check `--module-path`, module names, and input artifacts |
| `Module ... does not read ...` | Missing `requires` or incorrect module readability | Check `module-info.java` and `requires transitive` |
| `package ... is not visible` | Package is not exported to the calling module | Check `exports` or the API module |
| `jlink` reports missing dependency | Root module pulls in an unavailable or unresolvable dependency | Add the required dependency module to the module path |
| Service provider not found | Provider module was not linked | Check `uses`/`provides`, use `--bind-services`, or add the provider explicitly |
| Application throws `ClassNotFoundException` in the image | Dynamically loaded class is missing from the image or unresolved | Add the required module/plugin and test dynamic loading paths |
| Unusually large runtime image | Too many roots selected or `ALL-MODULE-PATH` used | Specify minimal root modules; analyze dependencies with `jdeps` |
| `--limit-modules` causes linking to fail | Limit excluded a mandatory dependency | Add the required module or remove the inappropriate limit |
| Runs on full JDK but fails in the image | Full JDK has more modules than the custom image | Check `--list-modules`, services, reflection, resources, and native dependencies |

## 13. Workflow for building and verifying a closure

Follow these steps in order:

1. Identify the application module(s) to use as roots.
2. Inspect `module-info.java` of each module, especially `requires`, `requires transitive`, `requires static`, `uses`, and `provides`.
3. Analyze application and library dependencies with `jdeps`.
4. Identify dynamic dependencies, service providers, plugins, reflection, and native libraries needed at runtime.
5. Use `jlink --add-modules` to select root modules; enable `--bind-services` if service provider binding is needed.
6. Use `--limit-modules` only when there is a clear reason and you have confirmed the graph has no missing dependencies.
7. Build the runtime image and inspect it with `java --list-modules`.
8. Run the application and integration tests on the runtime image, including dynamically loaded features and services.
9. Measure image size; apply strip/compress options only after functionality is verified.

## 14. Checklist before releasing a runtime image

- [ ] Root modules are selected accurately for the application being run.
- [ ] `requires` and `requires transitive` directives have been reviewed.
- [ ] `requires static` dependencies have been evaluated against actual runtime features.
- [ ] Service consumers and providers are declared and fully linked.
- [ ] Dependencies analyzed by `jdeps` have been cross-checked with the runtime configuration.
- [ ] Reflection, plugins, JNI, native libraries, and dynamic resources have been tested.
- [ ] `--bind-services` is enabled when provider binding is required.
- [ ] `--limit-modules` does not exclude any mandatory dependencies.
- [ ] `java --list-modules` on the image shows all required modules.
- [ ] The application and integration tests pass on the runtime image itself.
- [ ] The image is built and tested for the target OS/architecture.

Module closure is the set of modules resolved from the root modules together with their dependencies. In `jlink`, choose appropriate roots, check `requires` and service binding, then verify the result with `jdeps`, `java --list-modules`, and tests on the runtime image. Dynamically loaded or environment-dependent components must be added and tested separately so the custom runtime remains fully functional.
