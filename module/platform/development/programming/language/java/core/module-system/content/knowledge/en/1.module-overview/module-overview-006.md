# Relationship between compile-time, run-time, and the module graph

In the Java Platform Module System (JPMS), an application does not consist solely of `.class` files and JARs. It also has a **module graph**: the set of selected named modules and the dependency relationships among them. This graph directly affects two key phases:

- **Compile-time:** `javac` needs to locate modules and APIs to check source code, types, and access permissions.
- **Run-time:** the Java launcher and JVM need to resolve required modules, create module layers, load classes, and execute the application.

Successful compilation is a necessary condition, but it does not guarantee that runtime has all modules, matching versions, and the same configuration as build time. Conversely, a module present in the JDK runtime but not resolved into the startup graph may not be usable in the way the source code assumes.

This article connects the three concepts **compile-time, run-time, and the module graph**, then illustrates them with a multi-module JPMS application.

## Objectives

After this lesson, you will be able to:

- Distinguish compile-time and run-time dependencies in JPMS.
- Explain how module resolution builds a graph from root modules and `requires` relationships.
- Understand the role of `module-info.java` in both `javac` and the Java launcher.
- Distinguish **observable modules**, **resolved modules**, **readability**, and **accessibility**.
- Explain `requires`, `requires transitive`, and `requires static` across both phases.
- Compile and run a multi-module example using `--module-source-path` and `--module-path`.
- Use `--show-module-resolution` and Java APIs to observe the runtime graph.
- Recognize "compiles fine but fails at runtime" and "module is present but unreadable/inaccessible" errors.

## 1. Three layers in a modular Java application

Imagine an application consisting of:

~~~text
com.acme.app
      |
      | requires
      v
com.acme.service
      |
      | requires transitive
      v
com.acme.model
~~~

Each node is a **named module**, not simply a JAR. Each edge represents a module relationship declared or inferred according to JPMS rules.

To understand the graph, separate three layers of information:

| Layer | Question to answer | Where to check |
|---|---|---|
| Artifact | Where do classes/JARs actually reside? | Source tree, output folder, module path |
| Module resolution | Which named modules participate in the configuration? | `module-info.java`, root modules, resolver |
| Module access | Which module reads which module and which packages are accessible? | `requires`, `exports`, `opens`, and Java rules |

A JAR can exist on disk without being on the module path. A module can be found on the module path without being selected into the graph. A resolved module can still not export the package that source code wants to import.

That is why you need to diagnose the right layer instead of treating every error as "missing dependency".

## 2. How does compile-time work?

At compile-time, `javac` reads source files and module descriptors to check:

1. What is the name of the module being compiled?
2. Which modules does it declare it needs to read?
3. Can the dependency modules be found?
4. Are the imported packages exported to the consuming module?
5. Do classes, constructors, and methods have sufficient access permissions under the Java language?

Descriptor example:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

This declaration states that `com.acme.app` depends on `com.acme.service` at the module level. When compiling app, the compiler must be able to locate the service module, for example via a compiled module directory or modular JAR on `--module-path`.

An IDE showing a dependency in a project does not automatically guarantee that the compiler running in CI or a terminal also sees that module.

### 2.1. The module path is a lookup source, not the final graph

Example:

~~~bash
javac --module-path mods -d out/app \
    src/com.acme.app/module-info.java \
    src/com.acme.app/com/acme/app/Main.java
~~~

`--module-path mods` specifies where to search for dependency modules. The resolver still relies on roots and `requires` to build the configuration used for compilation.

Do not interpret "JAR is on the module path" as "the application automatically reads all packages of that JAR".

### 2.2. Readability differs from package export

Suppose app already has:

~~~java
requires com.acme.service;
~~~

But the service descriptor is:

~~~java
module com.acme.service {
}
~~~

If app tries to import a public class from `com.acme.service.api`, the compiler may report that the package is not exported.

In that case:

- `requires` in app creates the readability relationship.
- `exports com.acme.service.api;` in the service module publishes the API package.
- `public` on the class allows code outside the package to reference the class under standard Java rules.

**Having readability without exports can still fail to compile.** Similarly, an exported package without app reading the module containing it is also insufficient.

## 3. How does runtime work?

When running a modular application:

~~~bash
java --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

The Java launcher identifies the main module `com.acme.app` as a root. The module system finds this module, reads its descriptor, and resolves mandatory dependencies. The result is a **resolved module graph** used to define the modules in the boot layer and execute the application.

Overall flow:

~~~text
Command java -m com.acme.app/...
               |
               v
       Root: com.acme.app
               |
               v
    Find modules from runtime image
    and --module-path
               |
               v
       Resolve dependencies
         from module-info
               |
               v
       Runtime configuration
               |
               v
       Boot ModuleLayer
               |
               v
       Class loading + execution
~~~

Some dependencies present at compile-time may validly be absent at runtime if declared with `requires static` and the executing application does not actually need those types at runtime. Mandatory dependencies from plain `requires` must still be present for the graph to resolve.

### 3.1. A present module is not necessarily resolved

Distinguish two questions:

- Does the runtime image **contain** `java.sql`?
- Has the process's boot layer **resolved** `java.sql`?

You can check in code:

~~~java
import java.lang.module.ModuleFinder;

public class ModuleState {
    public static void main(String[] args) {
        String moduleName = "java.sql";

        boolean present =
            ModuleFinder.ofSystem()
                        .find(moduleName)
                        .isPresent();

        boolean resolved =
            ModuleLayer.boot()
                       .findModule(moduleName)
                       .isPresent();

        System.out.println("Present in runtime image: " + present);
        System.out.println("Resolved in boot layer: " + resolved);
    }
}
~~~

`ModuleFinder.ofSystem()` looks up system modules present in the runtime image; `ModuleLayer.boot().findModule()` looks up modules in the boot layer. Results can differ because **an available module** does not mean it **participated in the startup graph**.

Do not use the result of one check to infer the result of the other.

## 4. Where is the module graph built from?

The graph is not built by "loading every JAR into the JVM". Resolution starts from **root modules** and follows declared dependencies.

Key sources of information:

- `module-info.class` of explicit named modules.
- Root modules chosen by the launch mode, such as the main module with `-m`.
- Additional roots via `--add-modules`.
- System modules from the runtime image.
- Application modules from `--module-path`.
- Certain launcher options or service binding configurations as applicable.

When the main module requires service and service requires model:

~~~text
Root com.acme.app
    |
    +-- requires com.acme.service
              |
              +-- requires transitive com.acme.model
~~~

The resolver finds required dependencies, verifies consistency, and forms the graph before calling `Main.main()`.

### 4.1. Nodes and edges have distinct meanings

A **Node** is a resolved module. An **Edge** represents a dependency/readability relationship according to descriptors or supplemental mechanisms.

With:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

App has a direct dependency edge to service. Yet whether app can use a public type inside service still depends on whether that package is exported.

### 4.2. Readability is not arbitrary access permission

One module reading another module does not mean every internal package becomes accessible. JPMS also enforces strong encapsulation:

~~~java
module com.acme.service {
    exports com.acme.service.api;
}
~~~

The `com.acme.service.internal` package is not automatically exported just because app has `requires com.acme.service;`.

If a framework needs deep reflection, the providing module may need to use `opens` or qualified opens for the exact package and framework module. This is a different mechanism from compile-time access to public APIs.

### 4.3. The runtime graph is not necessarily the entire system

The boot layer's graph does not encompass every module that can exist in the JVM. A plugin application can create a new `ModuleLayer` from a separately resolved `Configuration`, or some classes may still belong to the unnamed module on the classpath.

Therefore, when speaking of "the application's module graph", specify whether you mean the **compile-time configuration**, the **boot layer**, or **a dynamic layer**.

## 5. Complete three-module example

Let us create:

~~~text
project/
└── src/
    ├── com.acme.model/
    │   ├── module-info.java
    │   └── com/acme/model/api/Message.java
    ├── com.acme.service/
    │   ├── module-info.java
    │   └── com/acme/service/api/GreetingService.java
    └── com.acme.app/
        ├── module-info.java
        └── com/acme/app/Main.java
~~~

The example uses JDK 17 or higher.

### 5.1. Model module

`src/com.acme.model/module-info.java`:

~~~java
module com.acme.model {
    exports com.acme.model.api;
}
~~~

`src/com.acme.model/com/acme/model/api/Message.java`:

~~~java
package com.acme.model.api;

public record Message(String text) {
}
~~~

Model exposes the package containing `Message`. This is the public API other modules can use once they have an appropriate readability relationship.

### 5.2. Service module

`src/com.acme.service/module-info.java`:

~~~java
module com.acme.service {
    requires transitive com.acme.model;
    exports com.acme.service.api;
}
~~~

`src/com.acme.service/com/acme/service/api/GreetingService.java`:

~~~java
package com.acme.service.api;

import com.acme.model.api.Message;

public final class GreetingService {
    public Message greet(String name) {
        return new Message("Hello, " + name);
    }
}
~~~

Service returns `Message` from model in a public method signature. Therefore, declaring `requires transitive com.acme.model;` enables modules reading service to also read model. This is a reasonable choice when model is part of service's API contract.

### 5.3. App module

`src/com.acme.app/module-info.java`:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

`src/com.acme.app/com/acme/app/Main.java`:

~~~java
package com.acme.app;

import com.acme.model.api.Message;
import com.acme.service.api.GreetingService;

public class Main {
    public static void main(String[] args) {
        GreetingService service = new GreetingService();
        Message message = service.greet("JPMS");
        System.out.println(message.text());
    }
}
~~~

App directly declares a dependency on service; readability to model is propagated via service's `requires transitive`. Both service and model export the required API packages.

### 5.4. Compiling all modules together

From the `project` directory:

~~~bash
javac --module-source-path src \
      -d mods \
      -m com.acme.model,com.acme.service,com.acme.app
~~~

On Windows PowerShell:

~~~powershell
javac --module-source-path src -d mods -m com.acme.model,com.acme.service,com.acme.app
~~~

The compiler reads the module source path, finds sources by module name, and places compiled outputs per module:

~~~text
mods/
├── com.acme.model/
│   ├── module-info.class
│   └── com/acme/model/api/Message.class
├── com.acme.service/
│   ├── module-info.class
│   └── com/acme/service/api/GreetingService.class
└── com.acme.app/
    ├── module-info.class
    └── com/acme/app/Main.class
~~~

### 5.5. Running with the module path

~~~bash
java --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

Single-line command:

~~~bash
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Output:

~~~text
Hello, JPMS
~~~

The application runs only after the launcher finds the main module and its mandatory dependencies. Runtime here relies on the compiled module descriptors and the supplied `mods` directory.

## 6. From compile graph to runtime graph

With the example above, both phases use the same module declarations:

~~~text
COMPILE TIME

javac
  |
  +-- com.acme.model
  +-- com.acme.service ---> com.acme.model
  +-- com.acme.app     ---> com.acme.service
                             |
                             +-- transitive readability to model

RUNTIME

java -m com.acme.app
  |
  +-- resolve com.acme.app
        |
        +-- com.acme.service
                |
                +-- com.acme.model
  |
  +-- define modules in boot layer
  |
  +-- load Main and invoke main()
~~~

Similarity: module descriptors define dependencies and API boundaries at both compile time and runtime.

Difference: the compiler works with sources/compiled artifacts in a build environment; the launcher resolves modules present in the **process's runtime image and module path**. If the two environments do not align, results can differ.

| Aspect | Compile-time | Run-time |
|---|---|---|
| Tools | `javac`, Maven/Gradle compiler tasks | Java launcher and JVM |
| Inputs | Sources, descriptors, compile module path | Compiled descriptors/JARs, runtime image, and runtime module path |
| Root modules | Modules requested for compilation or roots chosen by tools | Main module and roots per launch mode |
| Goal | Check types, readability, accessibility; produce bytecode | Resolve configuration, create layers, load classes, execute |
| Typical errors | `module not found`, `package is not visible` | `FindException`, `LayerInstantiationException`, `NoClassDefFoundError`, runtime access errors |

Do not assume the two graphs always contain the exact same set of nodes just because source code and `module-info.java` files have not changed. Modules outside mandatory dependencies or additionally selected plugins/service providers can vary by environment.

## 7. requires, requires transitive, and requires static

These three directives affect graph reading differently.

### 7.1. requires: mandatory dependency

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

App needs the service module to compile against service's API; service is also a mandatory dependency when resolving app at runtime.

If the service module is missing on the runtime module path, the launcher can fail **before calling main()**:

~~~text
java.lang.module.FindException:
Module com.acme.service not found, required by com.acme.app
~~~

The exact message depends on the JDK and launch command, but the cause is an unresolved mandatory dependency.

### 7.2. requires transitive: propagating readability

~~~java
module com.acme.service {
    requires transitive com.acme.model;
    exports com.acme.service.api;
}
~~~

Modules reading service also read model through the transitive relationship. This is needed in the example because service's public API returns `Message` from model.

If replaced with:

~~~java
requires com.acme.model;
~~~

then app with only `requires com.acme.service;` does not automatically gain readability to model. If app directly uses `Message`, it should declare a dependency reading model or redesign the API appropriately.

**`requires transitive` propagates readability; it does not automatically export packages kept internal by the model module.**

### 7.3. requires static: compile-time mandatory, runtime optional dependency

Annotation library example:

~~~java
module com.acme.app {
    requires static com.acme.annotations;
}
~~~

At compile time, the compiler needs to see the annotations module. However, this module is permitted to be absent at runtime, provided executing code does not need to load types from that module at runtime.

A common situation is annotations used solely at compile time without needing runtime reflection.

Distinction:

| Directive | Required at compile-time | Mandatory at runtime? | Readability to dependent clients? |
|---|---|---|---|
| `requires M;` | Yes | Yes | Not automatically propagated |
| `requires transitive M;` | Yes | Yes | Yes, per transitive rules |
| `requires static M;` | Yes | Not mandatory | Not automatically propagated like transitive |

For optional dependencies, verify whether runtime actually uses those classes. `requires static` does not make classes magically appear; if code directly loads a type from an absent module, runtime errors can still occur.

### 7.4. When static and transitive combine

JPMS also permits:

~~~java
requires static transitive com.acme.annotations;
~~~

This is a dependency relevant to compilation and readability propagation where applicable, yet still does not require the module to be present at runtime in the sense of a static dependency. Only use this combination when a public API genuinely exposes types from an optional dependency; do not use it to "patch over" every missing-module error.

## 8. Three states a module can have

Consider the `java.sql` module on a runtime image:

1. **Present in the image:** the JDK/runtime has packaged this module.
2. **Observable:** the module finder/resolution can see the module in the current context.
3. **Resolved:** the module is selected into the application's configuration.

A module can be **present in the image** without participating in the boot layer. A module JAR can exist in a directory yet not be observable if it is not placed on the module path.

List system modules:

~~~bash
java --list-modules
~~~

Inspect a module descriptor:

~~~bash
java --describe-module java.sql
~~~

Inspect the resolved graph when running the application:

~~~bash
java --module-path mods \
     --show-module-resolution \
     -m com.acme.app/com.acme.app.Main
~~~

`--show-module-resolution` is suited for confirming which modules were selected and the resolution relationships for that specific launch command. By contrast, `--list-modules` reports observable modules, not the list of nodes guaranteed to be resolved.

## 9. When compile succeeds but runtime fails

This is a very important category of errors when migrating from the classpath to JPMS or deploying to another environment.

### 9.1. Runtime module path missing a dependency

Compilation succeeds:

~~~bash
javac --module-source-path src -d mods \
      -m com.acme.model,com.acme.service,com.acme.app
~~~

Then a runtime environment is created containing only app, without service or model.

The run command looks valid but will fail during dependency resolution:

~~~bash
java --module-path runtime-only-app \
     -m com.acme.app/com.acme.app.Main
~~~

The issue is no longer in the source code, but in the **runtime artifacts/module path**. All required modules must be included in the deployment or a properly configured runtime image must be built.

### 9.2. Runtime library version differs from compile time

Compile time has a new version of `com.acme.service`, while production uses an older JAR with the same module name. At runtime, the module may still resolve, yet its bytecode is incompatible with the compile-time API.

Errors that can appear:

- `NoSuchMethodError` when a method existed at compile time but is absent at runtime.
- `NoSuchFieldError` when a field was changed or is missing.
- `IncompatibleClassChangeError` when class/interface shapes are incompatible.
- `IllegalAccessError` when bytecode attempts to access an API or package no longer permitted.

The solution is to check actual artifacts, module descriptors, and the source of loaded classes, not merely module names.

### 9.3. Class initialization failure

A module can be fully resolved yet a class inside it can still fail in a static initializer:

~~~java
public final class Configuration {
    static final String ENDPOINT =
        System.getenv("SERVICE_ENDPOINT");

    static {
        if (ENDPOINT == null) {
            throw new IllegalStateException("Missing SERVICE_ENDPOINT");
        }
    }
}
~~~

This error does not prove the module graph is wrong. It occurs after resolution, when the class is initialized. In some cases you may see `ExceptionInInitializerError` or `NoClassDefFoundError: Could not initialize class ...`.

### 9.4. Reflection into a closed package

App compiles against public APIs cleanly; a runtime framework tries deep reflection into a private field of another module and is rejected.

In that case check:

~~~java
module com.acme.model {
    exports com.acme.model.api;
    opens com.acme.model.internal to some.framework.module;
}
~~~

`opens` opens only the exact package to the designated framework if there is a genuine need. Do not switch to `open module` just to silence diagnostics.

## 10. When compile fails even though JARs/modules are present

### 10.1. Module not found

Compiler example:

~~~text
error: module not found: com.acme.service
~~~

The module path may be wrong, the module name incorrect, or the dependency artifact not yet built. Check:

~~~bash
jar --describe-module --file libs/service.jar
~~~

If the project uses compiled module directories, verify that the directory containing `module-info.class` is supplied on the module path at the right level.

### 10.2. Module does not read another module

Example:

~~~text
package com.acme.service.api is not visible
  (module com.acme.app does not read com.acme.service)
~~~

Look for `requires com.acme.service;` in app's `module-info.java`.

### 10.3. Package not exported

Example:

~~~text
package com.acme.service.internal is not visible
  (module com.acme.service does not export it)
~~~

App may already read service, but the internal package is not exposed. Switch to a supported API or intentionally export the package if it is genuinely a public contract.

### 10.4. Split package

Two modules both containing the `com.acme.shared` package with app reading both can cause an error:

~~~text
module com.acme.app reads package com.acme.shared
from both com.acme.alpha and com.acme.beta
~~~

Fix by deciding which module owns the package, moving classes, or changing namespaces; adding `requires` or `--add-exports` does not change package ownership.

## 11. Maven/Gradle graph differs from the JPMS graph

In a multi-project build, two graphs typically exist simultaneously:

~~~text
Maven/Gradle project dependencies
    -> determine build order
    -> place artifacts onto compile/runtime paths

JPMS module-info.java
    -> describe named module
    -> determine readability and exports
    -> serve compile/runtime resolution
~~~

Gradle example:

~~~groovy
dependencies {
    implementation project(':service')
}
~~~

and JPMS:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

These two declarations support each other but **do not replace** each other. If only the Gradle dependency is present, app does not automatically read the named service module under JPMS. If only `requires` is present without Gradle supplying the service artifact, the compiler may fail to find the module.

With Maven:

~~~xml
<dependency>
  <groupId>com.acme</groupId>
  <artifactId>service</artifactId>
  <version>1.0.0</version>
</dependency>
~~~

Maven's dependency block brings the artifact into the build graph, while `requires com.acme.service;` still needs the exact actual module name in the descriptor.

A build tool can use different compile module paths and runtime module paths. Compare both when app compiles successfully yet fails at runtime.

## 12. Where do the classpath and unnamed module fit in?

Before JPMS, the classpath was the common mechanism for supplying classes to an application:

~~~bash
java -cp "app.jar:libs/*" com.acme.app.Main
~~~

On Windows:

~~~powershell
java -cp "app.jar;libs/*" com.acme.app.Main
~~~

Classes on the classpath belong to the unnamed module of the corresponding class loader. When migrating to JPMS, understand:

- Named modules declare `requires` on **named modules**, not ordinarily on the unnamed module.
- An automatic module is a traditional JAR placed on the module path and assigned a module name by JPMS rules.
- Automatic modules provide a migration bridge, but lack an explicit descriptor and exhibit broad export behavior.
- Moving a JAR from the classpath to the module path can surface split packages or previously hidden dependencies.

Do not assume every codebase running cleanly on the classpath will compile immediately after adding `module-info.java`. Builds may need to migrate dependencies incrementally and update API boundaries.

## 13. --add-modules, --limit-modules, and roots

Launcher options can make the runtime graph differ from what you would predict from source code alone.

### 13.1. --add-modules

~~~bash
java --module-path mods \
     --add-modules com.acme.tools \
     -m com.acme.app/com.acme.app.Main
~~~

`--add-modules` adds root modules to resolve. It fits when a module is not a direct mandatory dependency from the main graph but needs to be present for a run configuration.

### 13.2. --limit-modules

~~~bash
java --limit-modules java.base --list-modules
~~~

`--limit-modules` limits the universe of observable modules. The flag does not delete modules from the runtime image, and universe calculation also considers the dependency closure plus rules for the main module/added roots. Do not use this flag as a security sandbox mechanism.

### 13.3. --show-module-resolution

~~~bash
java --show-module-resolution \
     --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

This is a good option for verifying the actual graph rather than guessing from a list of JARs.

### 13.4. --add-reads, --add-exports, --add-opens

In legacy migrations, you may encounter options that add special compile/runtime permissions. They can help with diagnostics or transition, but should not be used in place of a clean module design:

- `--add-reads`: adds a readability relationship.
- `--add-exports`: widens export of a package.
- `--add-opens`: permits deep reflection into a package.

Do not use these flags to mask missing dependencies, split packages, or misdeployed artifacts.

## 14. ServiceLoader and the runtime module graph

A plugin/service provider might not be referenced directly from app source code. Thus, the module graph serving services may need provider modules added at runtime.

Contract example:

~~~java
package com.acme.spi;

public interface Greeter {
    String greet(String name);
}
~~~

SPI module:

~~~java
module com.acme.spi {
    exports com.acme.spi;
}
~~~

App module:

~~~java
module com.acme.app {
    requires com.acme.spi;
    uses com.acme.spi.Greeter;
}
~~~

Provider module:

~~~java
module com.acme.greeter.impl {
    requires com.acme.spi;

    provides com.acme.spi.Greeter
        with com.acme.greeter.impl.DefaultGreeter;
}
~~~

App can compile with only the SPI module, because at compile time it does not directly reference the `DefaultGreeter` class. However, for `ServiceLoader` to find the provider in a module layer, the provider module must be included in the appropriate configuration/layer (for example via root configuration, service binding, or a plugin layer).

Usage example:

~~~java
ServiceLoader<Greeter> providers =
    ServiceLoader.load(Greeter.class);

for (Greeter provider : providers) {
    System.out.println(provider.greet("JPMS"));
}
~~~

Point to remember: having the interface present at compile-time does not automatically guarantee providers exist at runtime. This is another form of divergence between the compile graph and the runtime configuration.

## 15. Dynamic ModuleLayer and separate graphs

Not every module appears in the boot layer at startup. An application can resolve a group of plugin modules later and create a separate layer.

Idea:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;

ModuleLayer boot = ModuleLayer.boot();

ModuleFinder finder =
    ModuleFinder.of(Path.of("plugins"));

Configuration configuration =
    boot.configuration().resolve(
        finder,
        ModuleFinder.of(),
        Set.of("com.acme.plugin")
    );

ModuleLayer.Controller controller =
    ModuleLayer.defineModulesWithOneLoader(
        configuration,
        List.of(boot),
        ClassLoader.getSystemClassLoader()
    );

ModuleLayer pluginLayer = controller.layer();
~~~

The example is a snippet placed in a valid context, such as inside an executable method. It demonstrates:

1. Finding plugin modules from a specific location.
2. Resolving a new configuration based on the boot configuration.
3. Defining those modules in a new `ModuleLayer`.

When debugging plugins, ask **which layer the module was resolved into**, rather than only checking `ModuleLayer.boot().findModule()`.

The new layer does not replace the boot layer, and the layer's class loader also affects class loading behavior.

## 16. How to inspect the compile graph and runtime graph

An effective diagnostic workflow:

### Step 1: Identify the JDK and Java executable

~~~bash
java --version
javac --version
~~~

If the IDE, build server, and production use different Java versions, check the actual executable and `java.home` inside the process.

### Step 2: Inspect the module descriptor

~~~bash
jar --describe-module --file libs/service.jar
~~~

Confirm module name, `requires`, and exports. For outputs compiled into directories, verify `module-info.class` is at the right level.

### Step 3: Check the compile module path

Compare compiler flags in Maven/Gradle or the `javac` command:

~~~bash
javac --module-path mods -d out \
    src/com.acme.app/module-info.java \
    src/com.acme.app/com/acme/app/Main.java
~~~

Find the exact artifact of the dependency module. A `module not found` error at this stage is usually unrelated to package permissions.

### Step 4: Check the runtime module path

~~~bash
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Runtime must see all mandatory modules in the configuration. Check deployed paths, not just the build directory on a development machine.

### Step 5: Display module resolution

~~~bash
java --show-module-resolution \
     --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

Use the log to verify roots, dependencies, and the actual graph.

### Step 6: Distinguish missing module from missing class

If module resolution succeeds yet runtime reports `ClassNotFoundException` or `NoClassDefFoundError`, check further:

- Which JAR contains the class?
- Is the actual JAR the right version?
- Which class loader issued the request?
- Was the module resolved in the layer containing the class?
- Is there a transitive dependency issue or failed static initialization?

A `ClassNotFoundException` from calling `Class.forName()` does not automatically mean the module graph failed to resolve.

### Step 7: Inspect runtime class loading

You can use:

~~~bash
java -Xlog:class+load=info \
     --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

The log helps locate the source of loaded classes. If the module is resolved yet a class comes from an unexpected JAR, the bug may lie in build/deploy artifacts rather than `requires`.

## 17. Frequently asked questions

### Does a successful compile mean the runtime graph is guaranteed to match the compile graph?

No. Runtime has its own module path, runtime image, root selection, service providers, and artifact versions. Those differences can cause module resolution or class loading to fail.

### Is a module listed in java --list-modules guaranteed to be in the boot layer?

No. The command lists observable modules in the invocation context; whether a module is resolved into the boot layer depends on roots and dependencies.

### Does a resolved module automatically export all of its packages?

No. An explicit named module only exports packages advertised by its descriptor (or adjusted by an appropriate mechanism). Having a readability relationship does not mean internal implementations are accessible.

### Does requires static mean the dependency is not needed at compile time?

No. The `static` keyword here makes the dependency optional at runtime; the compiler still needs the module to check source code referencing it.

### Does requires transitive turn model into an optional runtime dependency?

No. If only `requires transitive` is used without `static`, model remains a mandatory dependency at runtime. `transitive` primarily changes readability propagated to consuming modules.

### Should you put every JAR on the module path and assume the graph is sufficient?

No. The module path only provides places to search for modules. The graph still depends on roots, descriptors, resolution feasibility, and module design.

### If only one plugin fails, should you check the boot layer?

You need to know whether the plugin is resolved in the boot layer or a dynamic layer. If loaded in a separate `ModuleLayer`, check the corresponding configuration/layer and class loader.

## 18. Self-check

**Scenario 1:** App has `requires com.acme.service;`, but the runtime module path only contains app. The compiler succeeded earlier. What can happen at runtime?

**Answer:** Runtime can fail during module resolution because the mandatory service module is not found.

**Scenario 2:** Service exports its API package, yet app has no `requires` and no indirect readability. Can app import classes from service?

**Answer:** No. Exporting a package does not create a readability relationship; app needs appropriate readability.

**Scenario 3:** App uses `Message` from model via service's API. What should service declare if model is part of the public API?

**Answer:** `requires transitive com.acme.model;` can be used so consumers reading service also read model; model still must export the package containing `Message`.

**Scenario 4:** An annotations module is declared with `requires static` and compiles successfully. Must it be present at runtime?

**Answer:** Not mandatory solely because of the static directive. However, if runtime code actually needs classes from that module, errors can still arise when the module is absent.

**Scenario 5:** `ModuleFinder.ofSystem().find("java.sql")` is present, yet `ModuleLayer.boot().findModule("java.sql")` is empty. Do the two results contradict each other?

**Answer:** No. A module can exist in the runtime image without being resolved into the boot layer.

**Scenario 6:** The service module is resolved, yet a framework cannot reflect on a private field. What is the likely cause?

**Answer:** The package has not been opened for deep reflection; check `opens`, qualified opens, or framework configuration.

**Scenario 7:** App compiles against a new API version, yet runtime uses an older service JAR missing a method. What kind of error can appear?

**Answer:** `NoSuchMethodError` or other binary linkage errors may appear; do not conclude that `requires` is missing.

**Scenario 8:** Two modules both contain `com.acme.shared` and app reads both. What graph-related error can occur?

**Answer:** Split package; package ownership must be reorganized rather than just adding more `exports`.

**Scenario 9:** Why is `--show-module-resolution` more helpful than `--list-modules` when debugging a specific run command?

**Answer:** Because it shows the actual module graph resolved for that launch, whereas `--list-modules` only lists observable modules.

**Scenario 10:** A plugin does not appear in the boot layer yet is loaded into a separate layer. Is this abnormal?

**Answer:** No. Modules can be resolved and defined in a new `ModuleLayer` after the application starts.

## Summary

**Compile-time**, **run-time**, and **module graph** are three connected perspectives:

- At **compile-time**, `javac` relies on sources, module descriptors, and the compile module path to validate dependencies, types, and access permissions.
- At **run-time**, the Java launcher and JVM rely on the runtime image, module path, root modules, and descriptors to resolve a configuration, create layers, load classes, and run code.
- The **module graph** connects the two stages through module nodes and `requires`/readability relationships. However, the sets of modules found, selected, and actually present can differ across environments.

When encountering errors, do not rush to add flags or JARs. Check in order whether **the module exists**, **is observable**, **is resolved**, **has readability**, **the package is exported**, and **the class loads/initializes successfully**. This separation makes JPMS diagnostics clear and supports building resilient modular applications.