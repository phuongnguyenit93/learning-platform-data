# Selecting Modules with --add-modules

## Objectives

After this lesson, you will be able to explain the role of the --add-modules option in JPMS, distinguish between the module path and the set of resolved modules, use the special values ALL-DEFAULT, ALL-SYSTEM, and ALL-MODULE-PATH, and apply this option when compiling, running applications, and creating runtime images with jlink.

## 1. What Is --add-modules Used For?

In the Java Platform Module System (JPMS), Java does not automatically bring every discoverable module into the runtime. The system starts from a set of root modules, then resolves dependencies declared via requires to build the module graph.

The --add-modules option allows adding one or more modules to the initial set of root modules. When a module is added as a root, it is included in the resolution process along with the dependencies it requires.

General syntax:

~~~bash
--add-modules module-name[,module-name...]
~~~

Example:

~~~bash
java --add-modules java.sql -cp app.jar com.acme.Main
~~~

The command above instructs the launcher to add the java.sql module to the set of root modules when starting the application. If this module requires other modules, those dependencies are also resolved according to the module graph.

The key point to remember is that --add-modules selects modules to be resolved. It does not automatically add packages to exports, does not establish a read relationship between two named modules, and does not load or initialize every class in the module immediately.

## 2. How Do Module Path and Root Modules Differ?

These two concepts are often confused:

- The module path is where the tool looks for observable modules. It can contain modular JARs, exploded modules, and automatic modules.
- Root modules are the modules chosen as starting points for resolving the module graph.
- The dependency graph is formed from the roots and the modules they require.

For example, the mods directory has three JARs:

~~~text
mods/
  com.acme.app.jar
  com.acme.logging.jar
  com.acme.metrics.jar
~~~

The application module declares:

~~~java
module com.acme.app {
    requires com.acme.logging;
}
~~~

When running:

~~~bash
java --module-path mods \
     --module com.acme.app/com.acme.app.Main
~~~

The launcher resolves com.acme.app and its dependency com.acme.logging. The com.acme.metrics module is present on the module path, but it is not automatically resolved just because its JAR exists there.

If you want to add metrics as an independent root module, you can run:

~~~bash
java --module-path mods \
     --add-modules com.acme.metrics \
     --module com.acme.app/com.acme.app.Main
~~~

At this point, com.acme.metrics is added to the module graph alongside the application and its dependencies. However, if code in com.acme.app needs to directly access public types of com.acme.metrics, the application must still have an appropriate read relationship, usually declared via requires in module-info.java.

## 3. --add-modules Does Not Replace requires

Suppose the application module wants to call the library module's API directly:

~~~java
package com.acme.app;

import com.acme.metrics.Counter;

public class Main {
    public static void main(String[] args) {
        Counter counter = new Counter();
        counter.increment();
    }
}
~~~

The module descriptor needs to declare the dependency:

~~~java
module com.acme.app {
    requires com.acme.metrics;
}
~~~

The requires declaration both creates a dependency in the module graph and establishes a readability relationship between the application module and the metrics module.

If you only run with:

~~~bash
java --module-path mods \
     --add-modules com.acme.metrics \
     --module com.acme.app/com.acme.app.Main
~~~

then com.acme.metrics is resolved, but that does not automatically create a readability edge from com.acme.app to com.acme.metrics. If the source needs to reference types from metrics, declare requires.

This can be summarized as:

| Mechanism | Effect |
|---|---|
| --module-path | Locates modules |
| --add-modules | Adds modules to the root set for resolution |
| requires | Declares a dependency and readability between named modules |
| --add-reads | Adds a read relationship at runtime or compile time via tool option |
| exports | Allows other modules to access public types in a package |
| --add-exports | Opens access to a package for a target module via tool option |

Therefore, when the error is that a module is not resolved, check the module path and root modules. When the error is that a module cannot read a package or type, check requires, exports, or the corresponding access options.

## 4. Special Values of --add-modules

Besides specific module names, this option supports several special values:

| Value | Meaning |
|---|---|
| ALL-DEFAULT | Adds all default root modules |
| ALL-SYSTEM | Adds all observable system modules |
| ALL-MODULE-PATH | Adds all observable modules on the module path |

Examples:

~~~bash
java --add-modules ALL-DEFAULT -cp app.jar com.acme.Main
~~~

~~~bash
java --module-path mods \
     --add-modules ALL-MODULE-PATH \
     --module com.acme.app/com.acme.app.Main
~~~

~~~bash
java --add-modules ALL-SYSTEM -cp app.jar com.acme.Main
~~~

A few notes:

- ALL-DEFAULT uses the tool's default root set in the current configuration.
- ALL-SYSTEM can cause the module graph to contain more platform modules than the application needs.
- ALL-MODULE-PATH can pull all observable modules from the module path into the graph, including modules unnecessary for the main functionality.
- The special values are written in uppercase and used as an element in the comma-separated module list.

You should not choose ALL-MODULE-PATH just because you want to make sure a needed module is found. In controlled builds and runtimes, explicitly specifying the names of the modules to add usually keeps the module graph easier to understand and leaner.

## 5. Using --add-modules with the java Launcher

When running an application on the classpath, --add-modules can add a system module that the application needs to use. For example, a program using the JDK's Vector API:

~~~java
import jdk.incubator.vector.IntVector;

public class VectorDemo {
    public static void main(String[] args) {
        int[] values = {1, 2, 3, 4};
        IntVector vector = IntVector.fromArray(
            IntVector.SPECIES_128,
            values,
            0
        );
        System.out.println(vector);
    }
}
~~~

Compile:

~~~bash
javac --add-modules jdk.incubator.vector VectorDemo.java
~~~

Run:

~~~bash
java --add-modules jdk.incubator.vector VectorDemo
~~~

The jdk.incubator.vector module is an incubator module, so it must be explicitly added in commands that use this API. The option must be applied at both the compile step and the run step so the module is present in each process's module graph.

The example above uses the unnamed module because the source is compiled and run on the default classpath. For modular applications, an appropriate requires declaration must be added in the module descriptor if the source code directly references that module's API.

## 6. Using --add-modules When Compiling with javac

Javac also supports --add-modules to add modules to the root set when resolving modules for compilation.

Example:

~~~bash
javac \
    --module-path mods \
    --add-modules com.acme.annotation.api \
    -d out \
    src/com/acme.tool/com.acme.tool/module-info.java \
    src/com/acme.tool/com.acme.tool/Main.java
~~~

In the example, the com.acme.annotation.api module resides on the module path and is added to the root set. The source module being compiled still needs to declare requires if it directly reads that module's API.

For sources organized by module, you can use the module source path:

~~~bash
javac \
    --module-source-path src \
    --module-path mods \
    --add-modules com.acme.annotation.api \
    -d out \
    -m com.acme.tool
~~~

Points to distinguish:

- --module-source-path points to the location of the source code of the modules being compiled.
- --module-path points to the location of compiled or packaged dependency modules.
- --add-modules adds root modules for the resolution process.
- -m or --module selects the source module to compile.

If a dependency module is already pulled into the graph through a requires declaration of the source module, adding it again with --add-modules is usually unnecessary. This option is useful when you need to bring an independent module into the graph or when the tool needs to observe that module during compilation.

## 7. Using --add-modules with jlink

jlink creates a custom runtime image from a set of root modules and their dependencies. jlink's --add-modules option specifies the root modules to include in the image.

For example, an application has the module com.acme.app and depends on java.sql:

~~~bash
jlink \
    --module-path "$JAVA_HOME/jmods:mods" \
    --add-modules com.acme.app \
    --output runtime-image
~~~

jlink resolves the com.acme.app module and its required dependencies, then creates the runtime image at runtime-image.

You can add multiple root modules:

~~~bash
jlink \
    --module-path "$JAVA_HOME/jmods:mods" \
    --add-modules com.acme.app,com.acme.admin \
    --output runtime-image
~~~

Or add all observable modules on the module path:

~~~bash
jlink \
    --module-path "$JAVA_HOME/jmods:mods" \
    --add-modules ALL-MODULE-PATH \
    --output runtime-image
~~~

Choosing ALL-MODULE-PATH can produce a significantly larger image, because many unrelated modules are also pulled into the graph. When creating a runtime image for production, start from the application module and the root modules that are truly needed.

After creating the image, you can run the application using the launcher inside the image:

~~~bash
runtime-image/bin/java \
    --module com.acme.app/com.acme.app.Main
~~~

On Windows, the launcher is located at runtime-image\\bin\\java.exe.

## 8. Distinguishing --add-modules from --bind-services

When packaging modular applications, especially applications using ServiceLoader, you need to distinguish adding root modules from binding service providers.

- --add-modules specifies the root modules to resolve.
- --bind-services tells jlink to bind service providers for services used in the module graph, bringing matching provider modules into the runtime image.

Example:

~~~bash
jlink \
    --module-path "$JAVA_HOME/jmods:mods" \
    --add-modules com.acme.app \
    --bind-services \
    --output runtime-image
~~~

Suppose com.acme.app declares uses com.acme.spi.Formatter and another module declares provides com.acme.spi.Formatter with com.acme.impl.HtmlFormatter. With --bind-services, jlink can find and link matching providers in the set of observable modules.

If you know the exact provider module and want to include it in the image as an independent root, you can name the provider in --add-modules. --bind-services is useful when you want jlink to handle service relationships automatically based on uses/provides.

The important condition remains that provider modules must be observable on the module path, have a valid descriptor, and declare provides with the correct service type.

## 9. Combining with --limit-modules

--limit-modules restricts the set of modules that the tool can observe when resolving the module graph. It is often used to simulate a smaller runtime environment or restrict which modules are allowed to participate in resolution.

Example:

~~~bash
java \
    --module-path mods \
    --limit-modules java.base,java.logging,com.acme.app \
    --add-modules com.acme.app \
    --module com.acme.app/com.acme.app.Main
~~~

In this case, the set of observable modules is restricted according to the specified list. If a required dependency is not in the observable set, resolution will fail.

The two options have different roles:

| Option | Role |
|---|---|
| --limit-modules | Restricts which modules can be observed and participate in resolution |
| --add-modules | Selects root modules from the set of observable modules |

If a module is added with --add-modules but cannot be observed due to module limits, the tool cannot resolve it. Therefore, check both options when troubleshooting module not found errors.

## 10. When to Use Specific Module Names and When to Use ALL-*

Prefer specific module names when:

- The application needs an optional JDK module or incubator module.
- You need to add an independent module to the graph without pulling in the entire module path.
- You are creating a runtime image whose size needs to be controlled.
- You want the build command to be readable and reproducible across environments.

Use ALL-DEFAULT when you need to add the default root set according to the tool's policy. Use ALL-SYSTEM when intentionally bringing all observable system modules into the graph. Use ALL-MODULE-PATH when you want all modules on the module path to participate in resolution, such as in a test environment or a composite image.

Do not use ALL-* values as a general bug-fixing measure. They can hide undeclared dependencies, bloat the module graph, and make the runtime image larger.

## 11. Common Errors

| Symptom | Common Cause | Resolution |
|---|---|---|
| FindException: Module ... not found | Wrong module name or module is not on the module path | Check the name with jar --describe-module and check --module-path |
| Module is on the module path but not resolved | Module is neither a root nor a dependency of any root | Add the module name to --add-modules or declare requires if it is a direct dependency |
| Module is resolved but application cannot access API | Missing readability relationship or package is not exported | Declare requires, check exports; only use --add-reads/--add-exports when truly needed |
| javac cannot find module when compiling | Wrong module path or module is restricted by --limit-modules | Check the module path and the set of observable modules |
| Runtime image is missing a provider | Service provider is not bound or provider is not observable | Check uses/provides, module path, and consider --bind-services or adding the provider to --add-modules |
| Runtime image is too large | Unnecessary use of ALL-SYSTEM or ALL-MODULE-PATH | Select only the root modules the application truly needs |
| Incubator API is unavailable | Incubator module was not added at compile or runtime step | Add the corresponding module with --add-modules at both steps |

When encountering an error, determine whether it belongs to one of three categories: module cannot be found, module is not resolved, or module is resolved but lacks API access permission. These three cases require different handling.

## Key Takeaways

--add-modules adds modules to the set of root modules for JPMS to resolve the module graph. --module-path specifies where to find modules; requires declares dependencies and readability between named modules; exports controls which packages are accessible. The values ALL-DEFAULT, ALL-SYSTEM, and ALL-MODULE-PATH respectively select the default root set, all observable system modules, and all modules on the module path. When using jlink, --add-modules selects root modules for the runtime image, while --bind-services handles binding service providers.
