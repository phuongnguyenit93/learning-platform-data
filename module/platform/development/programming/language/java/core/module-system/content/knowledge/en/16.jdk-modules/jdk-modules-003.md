# jdk.* Modules and Development Tools

Since Java 9, the Java Platform Module System (JPMS) divides the JDK into many **named modules**. One group consists of modules whose names start with `java.` (for example `java.base`, `java.compiler`, `java.sql`); another group consists of modules whose names start with `jdk.` (for example `jdk.compiler`, `jdk.javadoc`, `jdk.jdeps`, `jdk.jlink`, `jdk.jshell`).

Many `jdk.*` modules provide **developer tools**, the compiler implementation, dependency analysis tools, runtime image creation tools, the JShell environment, or JVM observability capabilities. Understanding them helps configure builds properly, recognize which APIs are supported, and avoid errors when running on a Java runtime image that does not include the full JDK toolset.

**Principle:** the `jdk.` prefix only indicates that the module name belongs to the group of modules provided by the JDK; it does not prove that every package inside is a stable public API. Check **exports**, the API documentation, and the module's specific purpose before depending directly on any class.

## 1. How Do java.* and jdk.* Differ?

In the modular JDK:

- `java.*` modules include standard Java SE APIs such as collections, networking, JDBC, XML, logging, and the Java Compiler API. For example, `java.base` is always present in every Java runtime.
- `jdk.*` modules provide JDK-defined capabilities, including certain public JDK APIs as well as implementations or developer tools.
- A module can **exports** public packages while keeping internal packages unexported.
- The actual set of modules can vary across JDK versions, JDK vendors, and custom runtime images.

Example:

    module com.example.app {
        requires java.compiler;
    }

The declaration above allows the application to use the standard Java Compiler API in `javax.tools` and `javax.annotation.processing`. It is **not equivalent** to:

    module com.example.app {
        requires jdk.compiler;
    }

`jdk.compiler` contains the compiler implementation along with certain JDK-specific tool APIs; whereas `java.compiler` defines standard interfaces and types that applications can use when appropriate.

You should also distinguish **module name** from **package name**. A package named `com.sun.source.tree` can be exported from `jdk.compiler`, even though the package name does not start with `jdk.`. Conversely, a package starting with `jdk.internal.` is usually not a supported API for direct application use.

## 2. Commonly Encountered jdk.* Modules

| Module | Primary purpose | Related tool or API |
|---|---|---|
| `jdk.compiler` | JDK Java compiler implementation and source structure analysis API | `javac`, `com.sun.source.tree`, `com.sun.source.util` |
| `jdk.javadoc` | Java documentation generation tool implementation | `javadoc`, `jdk.javadoc.doclet` |
| `jdk.jdeps` | Class/JAR dependency analysis and module dependency suggestions | `jdeps` |
| `jdk.jlink` | Module linking and runtime image packaging tools | `jlink`, `jmod` |
| `jdk.jshell` | JShell API and implementation | `jshell`, `jdk.jshell` |
| `jdk.jfr` | Java Flight Recorder (JFR) | `jdk.jfr.FlightRecorder`, `Recording` |
| `jdk.attach` | Attach API for interacting with another JVM when supported | `com.sun.tools.attach.VirtualMachine` |
| `jdk.management` | JDK Management API extensions | `com.sun.management` |
| `jdk.httpserver` | Lightweight HTTP server provided by the JDK | `com.sun.net.httpserver.HttpServer` |
| `jdk.unsupported` | Certain legacy non-standard APIs retained for compatibility | Should not be chosen for new applications if a standard alternative exists |

The table describes familiar modules in modern JDK releases; **it is not a guarantee that every Java distribution contains the entire list**. Modules providing tools may be absent in a minimal runtime image created with `jlink`.

`jdk.*` also does not mean every module is compile-time only: for example, `jdk.jfr`, `jdk.attach`, `jdk.management`, or `jdk.httpserver` can be used while the program is running.

## 3. A Module Is a Runtime Component; the javac Command Is a Tool

There are two layers to separate:

**Module layer:** `jdk.compiler` is a named module with a specific descriptor, packages, dependencies, and exports.

**Tool layer:** `javac` is a command-line tool used to compile Java source. When you run `javac`, you are invoking the JDK's compiler functionality; the shell command is not a module name.

Similarly:

    Tool:     javac       -> related module: jdk.compiler
    Tool:     javadoc     -> related module: jdk.javadoc
    Tool:     jdeps       -> related module: jdk.jdeps
    Tool:     jlink       -> related module: jdk.jlink
    Tool:     jshell      -> related module: jdk.jshell

Not every command-line launcher shares the same mechanism for providing an API inside a Java program. When writing Java code, look up the appropriate public API and declare `requires` if your source module needs to use types from that module.

The executables in the JDK's `bin` directory and the runtime modules stored in the JDK image are related components, not the exact same entity.

## 4. Viewing Modules Present in the JDK

The easiest way to see which system modules a Java runtime recognizes is:

    java --list-modules

Output may include:

    java.base@...
    java.compiler@...
    jdk.compiler@...
    jdk.javadoc@...
    jdk.jdeps@...
    jdk.jlink@...

The `...` indicates shortened version numbers in the example. The actual list depends on the JDK.

Filter module names on Linux/macOS:

    java --list-modules | grep '^jdk\.'

On Windows with Command Prompt:

    java --list-modules | findstr /B jdk.

View a module's descriptor:

    java --describe-module jdk.compiler

The descriptor can show:

- Module name and version.
- `requires` directives, indicating which modules it reads.
- Packages that are `exports`ed.
- Packages that are `opens`ed, if any.
- `uses` and `provides` service declarations.

If `java --describe-module jdk.compiler` reports that the module is not found, check which JDK/runtime image the running `java` command belongs to rather than assuming the bug is in application source code.

## 5. Observing Modules via the Java API

The `ModuleFinder` API lets you locate available system modules:

    import java.lang.module.ModuleFinder;
    import java.lang.module.ModuleReference;

    public class InspectJdkModule {
        public static void main(String[] args) {
            ModuleFinder finder = ModuleFinder.ofSystem();

            finder.find("jdk.compiler").ifPresentOrElse(
                reference -> {
                    System.out.println(reference.descriptor().name());
                    System.out.println(reference.descriptor().exports());
                    System.out.println(reference.location());
                },
                () -> System.out.println("jdk.compiler unavailable")
            );
        }
    }

`ModuleFinder.ofSystem()` describes the system modules that the current runtime can locate. It is not a scanner for every Maven or Gradle JAR.

Do not confuse "module present in the system module finder" with "module resolved into the boot layer". You can check:

    boolean resolved = ModuleLayer.boot()
            .findModule("jdk.compiler")
            .isPresent();

The result depends on launch configuration, root modules, and resolution. A module may be observable yet not part of the current program's module graph.

If you need to look for an optional dependent module, check its presence and resolution configuration rather than relying solely on JAR filenames.

## 6. java.compiler: Standard API for the Compiler

The `java.compiler` module defines standard APIs for compilation and annotation processing:

    javax.tools.JavaCompiler
    javax.tools.ToolProvider
    javax.tools.JavaFileObject
    javax.annotation.processing.Processor
    javax.lang.model.element.Element
    javax.lang.model.type.TypeMirror

If an application wants to ask the system to compile a Java file through the Java Compiler API, it can declare:

    module com.example.buildhelper {
        requires java.compiler;
    }

Then:

    import javax.tools.JavaCompiler;
    import javax.tools.ToolProvider;

    public class CompileSample {
        public static void main(String[] args) {
            JavaCompiler compiler =
                    ToolProvider.getSystemJavaCompiler();

            if (compiler == null) {
                System.err.println(
                    "No system Java compiler in current runtime");
                return;
            }

            int code = compiler.run(
                    null,
                    System.out,
                    System.err,
                    "-d", "out",
                    "src/demo/Hello.java"
            );

            System.out.println("Compiler exit code: " + code);
        }
    }

`getSystemJavaCompiler()` returns `null` if the runtime does not provide a system compiler. For instance, a custom runtime image containing only the modules needed to run the application might lack a compiler.

The key point is that **source code calls standard APIs from `java.compiler`**, while the actual compiler implementation is typically provided by `jdk.compiler` in a full JDK. If the program needs a compiler at runtime, the runtime must include an appropriate implementation.

## 7. When Is requires jdk.compiler Needed?

Not every application compiled with `javac` needs to declare:

    requires jdk.compiler;

If the application is **merely compiled by javac**, the app module does not need `requires jdk.compiler` because it only uses the compiler as an external tool.

If the application uses the standard `javax.tools` or `javax.lang.model` APIs, it typically uses:

    requires java.compiler;

If the application genuinely imports APIs from the `jdk.compiler` module, such as the Tree API or Trees utility:

    import com.sun.source.tree.CompilationUnitTree;
    import com.sun.source.util.JavacTask;
    import com.sun.source.util.Trees;

then the module may need:

    module com.example.analysis {
        requires jdk.compiler;
    }

Some `com.sun.source.*` packages are public APIs exported by `jdk.compiler` to support source analysis. In contrast, `com.sun.tools.javac.*` packages contain many implementation details that are not broadly exported and are not stable APIs.

**Do not infer from the `com.sun` prefix that all APIs are alike**: check the exports in the descriptor and the corresponding API documentation.

## 8. Example Using javac's Source Analysis API

If you need to analyze an AST (Abstract Syntax Tree), you can use `JavacTask` and `CompilationUnitTree` instead of accessing unsupported compiler internals.

Example:

    import com.sun.source.tree.CompilationUnitTree;
    import com.sun.source.util.JavacTask;
    import javax.tools.JavaCompiler;
    import javax.tools.StandardJavaFileManager;
    import javax.tools.ToolProvider;
    import java.util.List;

    public final class AstReader {
        public static void main(String[] args) throws Exception {
            JavaCompiler compiler =
                    ToolProvider.getSystemJavaCompiler();

            if (compiler == null) {
                throw new IllegalStateException(
                    "Compiler implementation unavailable");
            }

            try (StandardJavaFileManager files =
                    compiler.getStandardFileManager(
                        null, null, null)) {

                var source = files.getJavaFileObjects(
                        "src/demo/Hello.java");

                JavacTask task = (JavacTask) compiler.getTask(
                        null, files, null, List.of(), null, source);

                for (CompilationUnitTree unit : task.parse()) {
                    System.out.println(
                        unit.getSourceFile().getName());
                }
            }
        }
    }

This is an example of using the JDK API for ASTs. The module providing the implementation is still tied to `jdk.compiler`; when packaged as a named module, `requires jdk.compiler;` matches the `com.sun.source.*` imports.

Use the public Tree API before touching internal `com.sun.tools.javac.*` structures. Public APIs have better support guarantees when upgrading the JDK.

## 9. Annotation Processors Do Not Always Need jdk.compiler

A typical annotation processor usually uses:

    javax.annotation.processing.AbstractProcessor
    javax.annotation.processing.RoundEnvironment
    javax.lang.model.element.TypeElement

Those APIs belong to `java.compiler`.

A processor module can be written as:

    module com.example.processor {
        requires java.compiler;

        provides javax.annotation.processing.Processor
            with com.example.processor.MyProcessor;
    }

When compiling with a processor module, place the implementation on the appropriate processor path or processor module path so the compiler discovers and executes the processor.

Do not assume every annotation processor must `requires jdk.compiler`. Only add that dependency if the processor actually uses APIs exported by `jdk.compiler`.

Legacy processors may depend on internal `com.sun.tools.javac` packages and hit `IllegalAccessError` or package visibility errors on newer JDKs. The sustainable fix is usually updating the processor or switching to standard APIs, rather than opening all internal packages of `jdk.compiler`.

## 10. jdk.javadoc and the Documentation Generation Tool

The `jdk.javadoc` module contains the implementation of the `javadoc` tool. When running:

    javadoc -d docs -sourcepath src com.example.api

Javadoc analyzes the source and generates HTML documentation, depending on source layout and command options.

Some APIs for extending the Javadoc tool reside in packages such as:

    jdk.javadoc.doclet

If you write a custom doclet and import APIs from the `jdk.javadoc` module, the source module needs the appropriate readability relationship, such as:

    module com.example.doclet {
        requires jdk.javadoc;
    }

This differs from simply running the `javadoc` command to generate documentation for an application. An application **does not need** `requires jdk.javadoc` just because its build pipeline includes a Javadoc generation step.

In a custom runtime image without `jdk.javadoc`, features requiring the Javadoc implementation may be unavailable. Keep documentation generation tasks in the build JDK environment if production does not need them.

## 11. jdk.jdeps: Analyzing Dependencies When Modularizing

`jdeps` is an important tool when migrating legacy projects to JPMS. The module supporting this tool is `jdk.jdeps`.

Example listing module-level dependencies:

    jdeps --print-module-deps app.jar

If dependencies are not in the sources the tool sees, you may need to supply the corresponding classpath or module path.

Check dependencies on JDK internals:

    jdeps --jdk-internals app.jar

This command is especially useful when an older application or library uses internal JDK APIs that used to be accessible from the classpath.

For JARs requiring a separate module path:

    jdeps --module-path libs --print-module-deps app.jar

`jdeps` supports static analysis of dependencies represented in class files; it **does not guarantee visibility into dependencies created dynamically via reflection or service discovery**.

An application that only uses reflection by class names in strings may need runtime modules that `jdeps` does not detect through static analysis. Therefore, `jdeps` output is a starting point for the module graph, not a complete inventory of every runtime component.

## 12. jdk.jlink: Creating Modular Runtime Images

`jlink` lets you create a Java runtime image containing only the requested modules and their required dependencies. The tool corresponds to the `jdk.jlink` module.

Example:

    jlink --add-modules java.base,java.logging
          --output image

This runtime image can suit an application that needs only a small set of APIs. However, it will not necessarily include the compiler, Javadoc, JShell, or other development tools.

If the application genuinely needs the compiler at runtime:

    jlink --add-modules java.base,jdk.compiler
          --output image-with-compiler

The module graph of `jdk.compiler` pulls in the appropriate dependent modules when the image is built.

In production deployments, **do not include every `jdk.*` module just because it exists in a full JDK**. Include only the modules the application truly needs to reduce image size and dependency surface.

Also note that **JMOD** and **modular JAR** formats differ: `.jmod` files in the JDK's `jmods` directory support tools like `jlink`; they are not JAR artifacts for programs to load arbitrarily on the application module path via the Java launcher.

## 13. jdk.jshell: Experimenting with Code and the JShell API

JShell provides a REPL (Read-Eval-Print Loop) environment for running short Java snippets:

    jshell

Inside JShell you can try:

    jshell> 1 + 2

Beyond the command-line tool, the `jdk.jshell` module provides public APIs such as `jdk.jshell.JShell`.

An application building a Java learning interface or IDE plugin might use:

    module com.example.repl {
        requires jdk.jshell;
    }

Example creating a JShell instance:

    import jdk.jshell.JShell;

    public class MiniRepl {
        public static void main(String[] args) {
            try (JShell shell = JShell.create()) {
                shell.eval("int total = 3 + 4;");
                shell.eval("System.out.println(total);");
            }
        }
    }

If an application is merely built using a JDK that includes the `jshell` tool without importing the JShell API, there is **no need** to add `requires jdk.jshell`.

Keep in mind that JShell has its own execution environment mechanism; using the JShell API inside an embedded application requires considering resource lifecycles and the snippet execution environment.

## 14. Some jdk.* Modules Have Runtime APIs

Not every `jdk.*` module is strictly for build time:

**`jdk.jfr` — Java Flight Recorder**

Provides APIs for performance observation and runtime events:

    module com.example.monitoring {
        requires jdk.jfr;
    }

You can use `jdk.jfr.Recording` or appropriate event APIs when the application needs JFR.

**`jdk.attach` — Attach API**

Provides types such as `com.sun.tools.attach.VirtualMachine`. Attach capability depends on platform, process permissions, security policies, and the runtime image; an application is not always permitted to attach to another JVM.

**`jdk.management` — JVM Management Extensions**

Provides extended management APIs in the `com.sun.management` package. Distinguish this from standard JMX APIs such as `java.management`.

**`jdk.httpserver` — Small HTTP Server**

Provides `com.sun.net.httpserver.HttpServer`, sometimes handy for development tools, tests, or demos. When source imports types from this package, a named module needs:

    requires jdk.httpserver;

Do not assume every `jdk.*` module is an unusable implementation detail; several export public JDK APIs. What matters is **right API, right module, right runtime**.

## 15. jdk.unsupported and Internal API Boundaries

`jdk.unsupported` exists to support certain non-standard APIs that were once widely used by software, such as certain `sun.misc` types.

The existence of this module **does not turn every internal JDK API into a standard API**. An API exported from `jdk.unsupported` may still carry compatibility constraints different from Java SE APIs.

For example:

- Do not replace `java.util.concurrent`, `VarHandle`, or other standard APIs with `Unsafe` merely for convenience.
- Do not treat `--add-exports` into `jdk.internal.*` as a long-term architectural solution.
- When seeing a library depend on `sun.*` or `com.sun.tools.javac.*`, check the library version and upgrade options.

Use `jdeps --jdk-internals` to spot references to JDK internals when planning a migration.

## 16. When Is --add-modules Used?

When running a Java program on the classpath or with specific module roots, not every available system module is automatically resolved into the boot layer.

The launcher option:

    --add-modules module.name

adds the specified modules to the set of root modules to resolve.

Example:

    java --add-modules jdk.compiler -cp app.jar com.example.Main

If a program needs a tool provider supplied by `jdk.compiler` and the runtime is not resolving that module under default configuration, `--add-modules` can be part of an appropriate configuration.

However, **`--add-modules` does not create a missing module inside a Java image**. If a custom runtime does not contain `jdk.compiler`, adding the root module name still cannot restore the implementation.

For a named module containing:

    requires jdk.compiler;

JPMS resolves the dependency via `requires` if the module is actually available; normally you do not need to repeat that module name in `--add-modules`.

## 17. ToolProvider: Two APIs with the Same Name

Java has two ways to access tools that are easily confused:

1. `javax.tools.ToolProvider` in `java.compiler`, used to obtain the compiler or documentation tool via standard APIs.
2. `java.util.spi.ToolProvider` in `java.base`, a service-provider abstraction for command-line tools exposed by the JDK via the tool providers mechanism.

Example with the Java compiler API:

    JavaCompiler compiler =
        javax.tools.ToolProvider.getSystemJavaCompiler();

Example finding a command-line tool:

    import java.util.spi.ToolProvider;

    public class ToolDemo {
        public static void main(String[] args) {
            ToolProvider.findFirst("javac").ifPresentOrElse(
                tool -> {
                    int code = tool.run(
                        System.out, System.err, "--version");
                    System.out.println("Exit: " + code);
                },
                () -> System.out.println("javac tool not available")
            );
        }
    }

Although both share the name `ToolProvider`, they differ in package, API, and purpose.

Whether a tool provider is found depends on which modules/tools are present and resolved in the Java runtime image. If not found, an empty `Optional` does not mean the application's source files are broken.

## 18. Module Path and System Modules Are Not the Same

An application can have:

    --module-path libs:mods

to locate **application/library modules**. Meanwhile, JDK modules such as `java.base`, `jdk.compiler`, and `jdk.jfr` normally come from the runtime's **system module image**.

Points to remember:

- The module path provides additional application modules and libraries.
- System modules are supplied by the runtime according to the running JDK image.
- The same source code can run on a full JDK yet fail on a custom runtime image missing a required `jdk.*` module.
- Putting a JAR on the classpath is not a way to add `jdk.compiler` into a stripped-down system image.

When inspecting a packaged application, run:

    java --list-modules

using **the Java executable of the actual image**, not merely `java` from a globally installed JDK.

## 19. Common Errors with jdk.* Modules

| Error or symptom | Cause to investigate | How to resolve |
|---|---|---|
| `error: module not found: jdk.compiler` | Compile JDK/toolchain lacks the module, or configuration uses the wrong JDK | Check which JDK `javac` runs from; verify `java --list-modules` |
| `FindException: Module jdk.compiler not found` | Runtime image lacks `jdk.compiler` | Use a JDK/image with the module or rebuild the image with `jlink` |
| `getSystemJavaCompiler() == null` | No system compiler implementation present | Check the `jdk.compiler` module and the actual runtime |
| `IllegalAccessError` with `com.sun.tools.javac.*` | Processor/tool depends on encapsulated compiler internals | Update the tool, migrate to standard APIs, or use publicly exported APIs |
| `package com.sun.source... is not visible` | Not reading `jdk.compiler`, or incorrect module path/exports setup | Check `requires jdk.compiler` and the descriptor |
| `jdeps` unavailable in the image | The image does not package the relevant tool/module | Use a full JDK build image or a runtime containing the tool if genuinely needed |
| JShell fails to start | Missing module/tool in image or wrong Java executable | Check module list, launcher, and execution permissions |
| `ClassNotFoundException` with `jdk.*` API | Module unresolved, image missing module, or incorrect classpath/module setup | Identify the actual module, add `requires`, or configure roots properly |

Do not assume every error comes from `--module-path` missing a JAR. With system modules, the issue may be that the Java image omitted the module, or the project is running on a different JDK/toolchain than the one used for compilation.

## 20. Maven, Gradle, and Multiple JDK Versions

In Maven, the compiler plugin and test plugin can use a JDK/toolchain different from the JVM running Maven:

- The Maven process may run on one JDK.
- `maven-compiler-plugin` may use a separate toolchain.
- Surefire/Failsafe may launch a separate test JVM.
- The production image may be a custom runtime without developer modules.

With Gradle, you also need to distinguish the JVM running the Gradle daemon, the Java toolchain for compilation, the JVM for tests, and the application JVM.

Code importing `jdk.jshell` might compile successfully with a full JDK yet fail to run on an image built with only `java.base` and application module dependencies if `jdk.jshell` is not included.

To reduce discrepancies across environments, verify:

1. The exact JDK version used by each tool.
2. Whether `jdk.*` modules reside in the runtime image used at each step.
3. Whether build/test tools use the standard `java.compiler` API or import implementation internals.
4. Whether test and production JVMs have the same set of required modules.
5. Whether custom image packaging includes actual runtime dependencies.

**Developer tools** should stay in the build environment if production does not need them. Not every application runtime needs to carry a compiler, Javadoc, or JShell.

## 21. Diagnostic Workflow When a jdk.* Module Is Missing

When encountering errors related to `jdk.compiler`, `jdk.jlink`, `jdk.jfr`, or other JDK modules, follow these steps:

**Step 1 — Identify which tool is failing.**

Did the error occur while running `javac`, a Maven/Gradle build, unit tests, or inside the Java runtime image?

**Step 2 — Identify the exact module name.**

Inspect `requires` in `module-info.java` or the module name in the stack trace.

**Step 3 — Inspect the Java executable of the exact environment.**

    java --version
    java --list-modules

If you need to inspect a descriptor:

    java --describe-module jdk.compiler

**Step 4 — Distinguish a missing module from missing readability or exports.**

If the module is not in the image, `--add-exports` or `--add-opens` will not make it appear. If the module is present but the package is not exported, check whether that API is supported.

**Step 5 — Inspect the resolved module graph.**

    java --show-module-resolution -m com.example.app/com.example.Main

The command above is an example of launching a named module. Adjust the module path and main class for your actual application.

**Step 6 — Choose the minimal fix.**

- Need the Java Compiler API: use `requires java.compiler` and ensure a compiler implementation is present at runtime.
- Need the public Tree API: use `requires jdk.compiler`.
- Need the JFR API: use `requires jdk.jfr`.
- Only need to run `jdeps` in CI: use a build JDK with `jdeps`; do not add that dependency to the production module.
- Missing in a custom image: reconfigure `jlink` or remove the runtime need for that module.

## 22. Common Misconceptions

- **Assuming every `jdk.*` module is internal and never usable.** Several modules export public APIs such as `jdk.jfr`, `jdk.jshell`, and `com.sun.source.*`.
- **Assuming every package in `jdk.compiler` is public.** Many implementation packages are not exported and carry no stability guarantee.
- **Assuming an application compiled with `javac` must `requires jdk.compiler`.** A build tool invoking an external compiler does not create a runtime dependency automatically.
- **Assuming `java.compiler` and `jdk.compiler` are the same module.** One module holds standard APIs, while the other primarily provides the implementation and certain JDK tool APIs.
- **Assuming having the `jdeps` command means the application needs `requires jdk.jdeps`.** Build tools and application dependencies are two separate layers.
- **Assuming `--add-modules` reloads a module stripped out by jlink.** If the image lacks the module, you must choose another image or rebuild the image.
- **Assuming a module being present means it is always in the boot layer.** Distinguish observable system modules from resolved modules.
- **Assuming `com.sun.source.*` is the same as internal `com.sun.tools.javac.*` packages.** Check exports, API docs, and package intent.
- **Assuming a classpath containing a JAR is how to supply the compiler in a custom image.** The compiler implementation is a runtime image module, not a regular JAR.
- **Assuming production, test, and build JVMs always use the same JDK.** Toolchains or deployment configurations can differ.

## Takeaways

- `jdk.*` modules provide many tools and JDK-specific capabilities, such as the compiler, Javadoc, dependency analysis, runtime-image creation, JShell, and monitoring.
- `java.compiler` is the standard Java Compiler API; `jdk.compiler` provides the implementation and JDK-exported source analysis APIs.
- Only declare `requires jdk.*` when **the source module genuinely uses APIs or runtime services of that module**; do not add it just because build commands invoke JDK tools.
- Use `java --list-modules`, `java --describe-module`, `ModuleFinder.ofSystem()`, and `jdeps` for diagnosis.
- Custom runtime images may omit developer modules; `--add-modules` does not restore non-existent modules.
- Prefer standard APIs and publicly exported JDK APIs, avoiding dependencies on internal implementation packages whenever possible.

Clearly understanding the boundary between **Java SE APIs**, **JDK implementation modules**, and **command-line build tools** helps keep modular applications' dependencies accurate while avoiding failures when switching JDKs, upgrading toolchain versions, or deploying with minimal runtime images.
