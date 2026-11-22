# java.base and Platform Modules in the Java Module System

## 1. Lesson Objectives

After this lesson, you will understand:

- Why `java.base` is a special module that is always required for every modular Java application.
- Which common APIs reside in `java.base` and which APIs must be obtained from other Java SE modules.
- The relationship between `java.*` modules, `jdk.*` modules, application modules, and the **module resolution** process.
- When to declare `requires` in `module-info.java`, how to determine which module contains a package, and how to read a module descriptor.
- How to use `java --list-modules`, `java --describe-module`, `jdeps`, and the `ModuleFinder` API to inspect the current runtime.
- The impact of runtime images created with `jlink` on which modules are available at deployment time.

This lesson targets Java 17 and later, while explaining JPMS principles introduced in Java 9. The list of modules and APIs may vary across JDK versions or runtime images.

## 2. How Does the Java Platform Module System (JPMS) Organize the Standard Library?

Before Java 9, learners often thought of the Java library as a collection of packages always residing on the classpath. Starting in Java 9, the Java Platform Module System divides the platform and JDK into **named modules** with clear boundaries. Each named module has:

1. A **module name** unique within a configuration, such as `java.base` or `java.logging`.
2. A **module descriptor** describing dependencies with `requires`, public packages with `exports`, packages opened for reflection via `opens`, and service contracts.
3. A **set of packages/classes/resources** contained within the module.

Platform modules are typically packaged in Java's **runtime image**. When running `java --list-modules`, you see the modules provided by that runtime; these are not necessarily all the modules loaded into the boot layer of a specific application.

Examples of representative module names:

| Module | Example features / packages |
| --- | --- |
| `java.base` | `java.lang`, `java.util`, `java.io`, `java.nio`, `java.time`, `java.net`, `java.security` |
| `java.logging` | `java.util.logging`, standard logging API |
| `java.xml` | XML parsing, SAX, DOM, StAX |
| `java.sql` | JDBC API, `java.sql`, `javax.sql` |
| `java.net.http` | HTTP Client API, WebSocket client |
| `java.management` | JMX/management API |
| `java.naming` | JNDI |
| `java.desktop` | AWT, Swing, Java 2D, and related desktop APIs |
| `java.compiler` | Java language model and standard compiler tools |
| `java.scripting` | `javax.script` Scripting API; a concrete engine must be provided separately |
| `java.instrument` | Instrumentation API and Java agents |
| `java.security.jgss` | GSS-API and related Kerberos APIs |
| `jdk.compiler` | JDK compiler implementation, including corresponding tools |
| `jdk.jfr` | Java Flight Recorder |
| `jdk.httpserver` | Lightweight HTTP server included in the JDK |

These modules are examples, not an exhaustive catalog. The `java.*` group mainly represents Java SE APIs; the `jdk.*` group provides JDK-specific capabilities. A runtime image may omit many of the modules listed above.

## 3. Why Is `java.base` Special?

`java.base` is the foundation of JPMS. It contains the core components that every Java program needs to define objects, run threads of control, handle strings, collections, exceptions, and many other fundamental operations.

Key properties:

- **Every named module reads `java.base` implicitly.** You do not need to add `requires java.base;` to the descriptor.
- **`java.base` has no dependencies on other platform modules.** This establishes a stable starting point for the module dependency graph.
- **A valid Java runtime must contain `java.base`.** You cannot use `jlink` to create a working Java runtime while excluding this module.
- **`java.base` is not synonymous with the entire JDK.** JDBC, standard logging, XML, the modern HTTP Client, desktop APIs, and others are placed in separate modules.
- **Not every package in `java.base` is exported.** Internal implementation packages may be strongly encapsulated; you should only use supported and exported APIs.

Example code using only APIs from `java.base`:

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class BaseOnly {
    public static void main(String[] args) {
        List<String> names = List.of("Lan", "Minh", "An");
        Map<Integer, List<String>> byLength = names.stream()
                .collect(Collectors.groupingBy(String::length));

        System.out.println(LocalDate.now());
        System.out.println(byLength);
    }
}
~~~

`LocalDate` belongs to `java.time`, `List` and `Map` belong to `java.util`, and Stream/Collectors belong to `java.util.stream`: all of them reside in `java.base`. A modular application using only these APIs does not need to declare `requires` for any other Java SE module.

### 3.1. Notable Foundation Packages

| Category | Packages in `java.base` | Examples |
| --- | --- | --- |
| Language and type system | `java.lang`, `java.lang.annotation`, `java.lang.reflect` | `String`, `Object`, `Thread`, `Record`, reflection API |
| Dynamic invocation | `java.lang.invoke` | `MethodHandle`, `MethodHandles` |
| Collections and utilities | `java.util`, `java.util.stream`, `java.util.function` | `List`, `Map`, `Optional`, Stream |
| Concurrency | `java.util.concurrent`, `java.util.concurrent.atomic` | `ExecutorService`, `CompletableFuture`, atomics |
| Input/Output | `java.io`, `java.nio`, `java.nio.file` | `InputStream`, `Path`, `Files` |
| Basic networking | `java.net` | `URI`, `URL`, `Socket` |
| Date and time | `java.time`, `java.time.format` | `Instant`, `LocalDateTime`, `DateTimeFormatter` |
| Math and text | `java.math`, `java.text` | `BigDecimal`, `NumberFormat` |
| Security | `java.security`, `javax.crypto`, `javax.net.ssl` | `MessageDigest`, `Cipher`, TLS API |
| Module metadata | `java.lang.module` | `ModuleFinder`, `ModuleDescriptor` |

Two easily confused package names:

- `java.net` in `java.base` contains basic networking. `java.net.http` resides in the **`java.net.http`** module, so a named module wishing to use `HttpClient` must declare `requires java.net.http;`.
- `java.util` is in `java.base`, whereas `java.util.logging` belongs to **`java.logging`**. Merely importing `java.util.logging.Logger` does not automatically grant the application module read access to `java.logging`.

A package having a similar name or sharing a prefix does not mean it belongs to the same module. JPMS manages access according to the actual module descriptor.

## 4. From `java.base` to Other Java SE Modules

To minimize an application's dependencies, treat standard modules as functional components added only when needed.

### 4.1. `java.logging`: Standard Logging

This module provides the Java Util Logging (JUL) API. Example:

~~~java
import java.util.logging.Logger;

public class LogDemo {
    private static final Logger LOG =
            Logger.getLogger(LogDemo.class.getName());

    public static void main(String[] args) {
        LOG.info("Application started");
    }
}
~~~

In the **unnamed module** or a simple classpath program, users typically do not have to write `module-info.java`. However, if `LogDemo` resides in the named module `com.example.app`, the descriptor must explicitly state:

~~~java
module com.example.app {
    requires java.logging;
}
~~~

`java.base` is still read implicitly. Conversely, read access to `java.logging` does not arise automatically just because a class uses `java.lang` or `java.util`.

### 4.2. `java.sql` and `java.xml`

Applications that need the JDBC API typically declare:

~~~java
module com.example.database {
    requires java.sql;
}
~~~

Applications processing standard DOM/SAX/XML can declare:

~~~java
module com.example.xml {
    requires java.xml;
}
~~~

Dependencies of these modules are handled by JPMS through module resolution. If a module has `requires transitive`, readability can propagate according to the descriptor contract. Inspect the actual descriptor with `java --describe-module java.sql` rather than assuming all dependencies are identical across every Java version.

### 4.3. `java.net.http`: HTTP Client Since Java 11

The modern standard HTTP Client API belongs to `java.net.http`, not `java.base`:

~~~java
module com.example.client {
    requires java.net.http;
}
~~~

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;

public class ClientDemo {
    public static void main(String[] args) {
        try (HttpClient client = HttpClient.newHttpClient()) {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create("https://example.com"))
                    .GET()
                    .build();
            System.out.println(request.uri());
        }
    }
}
~~~

**Version note:** `HttpClient` only implements `AutoCloseable` in newer Java versions; the `try-with-resources` example above is only suitable for Java 21 and later. For Java 17, create the client normally as follows:

~~~java
HttpClient client = HttpClient.newHttpClient();
~~~

For the `java.net.http` module, the API has been standardized since Java 11. Use syntax and APIs appropriate for the Java version your project runs on.

### 4.4. `java.desktop` and `java.management`

Swing/AWT applications or management via JMX require the corresponding modules:

~~~java
module com.example.desktoptool {
    requires java.desktop;
    requires java.management;
}
~~~

Including `java.desktop` in a server-side application can increase the size of the runtime image. When creating a minimal runtime, you should only include the modules the application actually needs.

## 5. Distinguishing Java SE Modules from JDK-Specific Modules

A JDK distribution can provide both:

- **`java.*` modules**: many modules describing standardized Java SE APIs.
- **`jdk.*` modules**: providing JDK-specific tools or capabilities, such as the compiler, Java Flight Recorder, the lightweight HTTP server, or implementation modules.

Do not assume that every package in a `jdk.*` module is a stable public API. Even though a module can be found, a package that is not `exports`ed still cannot be imported normally from another module.

For example, `jdk.compiler` provides packages intended for compiler components, but does not by default allow access to every class in `com.sun.tools.javac.*`. You can inspect what is publicly exposed with:

~~~bash
java --describe-module jdk.compiler
~~~

Some runtimes include the aggregate module `java.se`. This is an **aggregator module** with transitive dependencies on the appropriate Java SE modules, not a container holding all classes in Java SE, nor an alias for `java.base`. When clear dependency control is needed, declare the modules actually used instead of relying on an aggregate module by default.

## 6. Reading `module-info.java` and Module Access Rights

### 6.1. What Is `requires`?

`module-info.java` is the source declaring a named module's descriptor. Example:

~~~java
module com.example.foundation {
    requires java.logging;
    requires java.net.http;
}
~~~

Readability relationships are formed via `requires` and other module rules. `java.base` in particular is read automatically:

~~~text
com.example.foundation
   +-- java.base         (implicit)
   +-- java.logging      (direct requires)
   +-- java.net.http     (direct requires)
         +-- ...         (dependencies per descriptor)
~~~

**Finding a module is not enough to access an API**. For module A to use a public type from module B, module A must read B and the package containing the type must be exported by B to an appropriate scope.

### 6.2. How Do `exports` and `opens` Differ?

- `exports com.example.api;` exposes public types in the package to code in other modules at both compile time and runtime according to access rules.
- `exports com.example.internal to com.example.friend;` exports the package only to the specified modules.
- `opens com.example.model;` allows deep reflection into the package at runtime; it does not mean every public type in the package automatically becomes an API importable from other modules.
- `open module com.example.app { ... }` opens all packages in the module for deep reflection under the open module model, though encapsulation implications should be considered.

`java.base` exports many fundamental APIs but also contains unexported internal packages. Using `--add-exports` or `--add-opens` to bypass module boundaries should be an exception for specific compatibility reasons, not the default rule.

### 6.3. `requires transitive` and `requires static`

A library can use:

~~~java
module com.example.facade {
    requires transitive java.logging;
}
~~~

Another module declaring `requires com.example.facade;` will gain readability to `java.logging` under the `requires transitive` rule.

`requires static module.name;` only requires the dependency at compile time; at runtime that dependency may be absent. If code actually invokes an optional API, the program still needs to design an appropriate execution path when the dependency is missing.

## 7. Complete Example: A Modular Application Using `java.base` and `java.logging`

Create the directory structure:

~~~text
src/
  com.example.foundation/
    module-info.java
    com/
      example/
        foundation/
          Main.java
mods/
  (directory generated after compilation)
~~~

File `src/com.example.foundation/module-info.java`:

~~~java
module com.example.foundation {
    requires java.logging;
}
~~~

File `src/com.example.foundation/com/example/foundation/Main.java`:

~~~java
package com.example.foundation;

import java.time.LocalDate;
import java.util.List;
import java.util.logging.Logger;

public class Main {
    private static final Logger LOG = Logger.getLogger(Main.class.getName());

    public static void main(String[] args) {
        List<String> messages = List.of("java.base", "java.logging");
        LOG.info("Running with " + messages);

        System.out.println("Today: " + LocalDate.now());
        System.out.println("Current module: " + Main.class.getModule().getName());

        Module ownModule = Main.class.getModule();
        Module base = Object.class.getModule();
        Module logging = Logger.class.getModule();

        System.out.println("Base module: " + base.getName());
        System.out.println("Logging module: " + logging.getName());
        System.out.println("Reads java.base: " + ownModule.canRead(base));
        System.out.println("Reads java.logging: " + ownModule.canRead(logging));
    }
}
~~~

Compile from the project directory:

~~~bash
javac -d mods/com.example.foundation src/com.example.foundation/module-info.java src/com.example.foundation/com/example/foundation/Main.java
~~~

Launch:

~~~bash
java --module-path mods --module com.example.foundation/com.example.foundation.Main
~~~

Example output (date, logger formatting, or layout may vary):

~~~text
... INFO: Running with [java.base, java.logging]
Today: 2026-11-11
Current module: com.example.foundation
Base module: java.base
Logging module: java.logging
Reads java.base: true
Reads java.logging: true
~~~

`LocalDate`, `List`, `Object`, and `Module` are all in `java.base`; `Logger` is in `java.logging`. Therefore, the descriptor only needs `requires java.logging;`.

If you remove the line `requires java.logging;` and recompile, the compiler will report that package `java.util.logging` is not visible to the named module due to a missing readability relationship. Adding the proper dependency to the descriptor is the fundamental fix.

Run again to observe resolution:

~~~bash
java --show-module-resolution --module-path mods --module com.example.foundation/com.example.foundation.Main
~~~

The `root ...`, `requires ...`, and other relationship lines help visualize how the JVM selects modules; exact output details also depend on launch options and the JDK version.

## 8. Inspecting Modules Directly with JDK Tools

### 8.1. Common Commands

~~~bash
java -version
java --list-modules
java --describe-module java.base
java --describe-module java.logging
java --describe-module java.net.http
java --describe-module jdk.compiler
~~~

Each command answers a question:

| Command | What does it tell you? |
| --- | --- |
| `java -version` | Which exact Java version/runtime is running? |
| `java --list-modules` | Which modules does the current runtime image provide? |
| `java --describe-module X` | Which `requires`, `exports`, `uses`, and `provides` does module `X`'s descriptor contain? |
| `java --show-module-resolution ...` | Which modules/relationships did the JVM select when running the application? |
| `jdeps --print-module-deps app.jar` | Module dependencies inferred from analyzing the JAR's bytecode. |

In `--list-modules` output, modules are usually printed in the form `module.name@version`. The version may differ or not appear in some circumstances. Do not hardcode a specific version into the application.

### 8.2. Determining Which Module Contains a Class

From Java code:

~~~java
import java.net.http.HttpClient;
import java.time.Instant;
import java.util.logging.Logger;

public class WhereIsMyClass {
    public static void main(String[] args) {
        System.out.println(String.class.getModule().getName());
        System.out.println(Instant.class.getModule().getName());
        System.out.println(Logger.class.getModule().getName());
        System.out.println(HttpClient.class.getModule().getName());
    }
}
~~~

Run on the classpath with Java 17+:

~~~bash
javac WhereIsMyClass.java
java WhereIsMyClass
~~~

Output:

~~~text
java.base
java.base
java.logging
java.net.http
~~~

This approach is very useful when you are unsure which module a class belongs to. It checks the module of a type in the runtime that the program actually loaded, and does not replace reading the descriptor to know whether the package is exported.

### 8.3. Listing via the `ModuleFinder.ofSystem()` API

In addition to the CLI, Java provides the module API in `java.lang.module` inside `java.base`:

~~~java
import java.lang.module.ModuleFinder;
import java.util.Comparator;

public class PlatformModules {
    public static void main(String[] args) {
        ModuleFinder finder = ModuleFinder.ofSystem();

        finder.findAll().stream()
                .sorted(Comparator.comparing(ref -> ref.descriptor().name()))
                .forEach(ref -> {
                    String name = ref.descriptor().name();
                    String location = ref.location()
                            .map(Object::toString)
                            .orElse("(unknown)");
                    System.out.println(name + " -> " + location);
                });

        System.out.println("java.base available: "
                + finder.find("java.base").isPresent());
    }
}
~~~

An example URI of a system module has the form `jrt:/java.base`. `jrt:/` is the URI scheme for runtime image contents and does not need to correspond to a JAR file on disk.

**Distinguish three layers of information:**

- `ModuleFinder.ofSystem().findAll()`: the modules the runtime exposes to the finder.
- `ModuleLayer.boot().configuration()`: the resolved module graph for the boot layer.
- `ModuleLayer.boot().modules()`: the modules actually defined in the boot layer.

A module appearing in the finder does not prove that it was selected into the application's boot layer.

### 8.4. Printing a Descriptor via the API

~~~java
import java.lang.module.ModuleFinder;

public class BaseDescriptor {
    public static void main(String[] args) {
        var base = ModuleFinder.ofSystem().find("java.base")
                .orElseThrow()
                .descriptor();

        System.out.println("Module: " + base.name());
        System.out.println("Requires: " + base.requires());
        System.out.println("Exported package count: " + base.exports().size());

        base.exports().stream()
                .map(export -> export.source())
                .sorted()
                .forEach(System.out::println);
    }
}
~~~

This code reads metadata rather than maintaining a package list from an older JDK release. Typically `java.base` does not depend on other modules; the remaining modules are described through module resolution relationships.

## 9. When Does the System Automatically Resolve Platform Modules?

Each time a modular application launches, the JVM determines the **root modules** and uses the resolver to trace dependent modules. High-level flow:

~~~text
Root: com.example.foundation
             |
             | requires java.logging
             v
       java.logging
             |
             +-----> java.base (foundation)
             ^
             |
com.example.foundation --(implicit read)--> java.base
~~~

The diagram above only illustrates the dependency portion needed to understand the example. Each runtime may have additional resolution details.

There are two important notes:

1. `java.base` is always the base module; for a named module, the read relationship to `java.base` is automatic even if `module-info.java` does not write it out.
2. An **observable module** is not necessarily resolved. `java --list-modules` shows the source of system modules, whereas `--show-module-resolution` helps observe which modules are selected when running a specific application.

If a required module is not present in the observable sources, the JVM can report an error like:

~~~text
java.lang.module.FindException: Module java.logging not found, required by com.example.foundation
~~~

This often occurs with an overly minimal runtime image or when the configured module path does not contain a module the application needs. You should verify using the actual Java executable used to launch the application.

## 10. Minimal Runtime Images and the Meaning of `java.base`

`jlink` (included in the JDK) creates a custom runtime image from selected modules and their required dependencies.

Example on a system with a full JDK, using a non-existent output directory:

~~~bash
jlink --module-path /path/to/jdk/jmods --add-modules java.base,java.logging --output runtime-small
~~~

On Linux/macOS, `/path/to/jdk/jmods` can be replaced with `$JAVA_HOME/jmods` when the environment variable is properly set. On Windows, use the path to the `jmods` directory of the actual JDK installation, such as `C:\Java\jdk-17\jmods`.

Check:

~~~bash
runtime-small/bin/java --list-modules
~~~

On Windows, this is typically invoked as `runtime-small\bin\java.exe --list-modules`.

The generated runtime image will contain `java.base`, `java.logging`, and the dependencies `jlink` needs to package. Many other modules from the full JDK may not be present.

Practical impact:

- `java.base` cannot be omitted because it is the foundation of the runtime.
- If the application uses `java.net.http`, `java.sql`, or `java.desktop`, the image must include the corresponding modules.
- The JDK used at build time and the image used at deploy time may differ. Compiling cleanly on a full JDK does not guarantee a minimal runtime has all required modules.
- Use `jdeps` to suggest static dependencies, while also checking reflection, service loading, and dynamically determined call paths.

Example command analyzing a modular JAR:

~~~bash
jdeps --print-module-deps my-app.jar
~~~

`jdeps` can only analyze information appearing in the bytecode and provided configuration; it cannot perfectly infer every dynamic dependency of an application.

## 11. Common Misconceptions

### Misconception 1: "`java.base` contains the entire standard library"

Incorrect. `java.base` contains a large set of core APIs, but logging, JDBC, XML, management, desktop, the modern HTTP Client, and many other capabilities reside in separate modules. When writing `module-info.java`, accurately identify the module containing the package being used.

### Misconception 2: "Seeing `java.util.logging` means it is in `java.base`"

A package having the `java.util` prefix is not enough to determine its module. `java.util.logging` belongs to `java.logging`, whereas `java.util.concurrent` is in `java.base`. Use `Class.getModule()` or the descriptor to verify.

### Misconception 3: "Every module in `java --list-modules` is already loaded"

`--list-modules` shows the modules available in the runtime, while which modules are resolved depends on roots, dependencies, and runtime options. To inspect the graph, use `--show-module-resolution` or check the boot layer.

### Misconception 4: "If a module is in the runtime, its packages can always be imported"

Being present in the runtime is a necessary condition, not a sufficient one. The application module must have appropriate **readability**, and the target package must be exported; deep reflection may require `opens`. Internal packages like `jdk.internal.*` should not be treated as public APIs simply because the JVM uses them.

### Misconception 5: "JDK-specific modules appear in every Java runtime"

An image generated by `jlink` can omit many `jdk.*` modules and even unnecessary `java.*` modules. Cross-check the deployment runtime against the application's module dependencies.

### Misconception 6: "`java.se` is a larger copy of `java.base`"

`java.se` is an aggregate module on runtimes that provide it; it uses dependencies to group Java SE modules rather than storing all classes itself. `java.base` is an independent foundational module with a different role.

### Misconception 7: "Declaring `requires` replaces all runtime configuration"

`requires` expresses required module relationships, but does not synthesize missing modules in a runtime image, does not replace `--module-path`, and does not solve cases where packages must be opened for reflection.

## 12. Practice Exercises

**Exercise 1 — Identify modules by class.** Print the module names of `Object`, `Path`, `Logger`, `HttpClient`, `DocumentBuilderFactory`, and `Connection` using `SomeClass.class.getModule().getName()`. Group the classes into those belonging to `java.base` and those outside `java.base`. Where imports are needed, identify the corresponding module.

**Exercise 2 — Describe `java.base`.** Run `java --describe-module java.base` and answer: how many `exports` does this module have? Does it declare `requires` on any other module? Can an internal package not appearing in the `exports` list be imported normally by application code?

**Exercise 3 — Design a descriptor.** Given an application using `LocalDate`, `List`, `Logger`, `HttpClient`, and JDBC `Connection`, write a minimal `module-info.java` based solely on the modules containing these APIs. Explain why `requires java.base;` is not needed.

**Exercise 4 — Observe module resolution.** Run the `com.example.foundation` example from section 7 with `--show-module-resolution`. Identify the root module, directly required modules, and the presence of `java.base`.

**Exercise 5 — Compare runtimes.** Run `java --list-modules` on a full JDK and on the `runtime-small` runtime image created with `jlink`. Explain why the results differ and why `java.base` still appears in both.

**Exercise 6 — Test module boundaries.** Try removing `requires java.logging;` in the example and re-running `javac`. Read the compiler message and restore the dependency to its proper place in `module-info.java`.

Record the Java version and executed commands while doing the exercises. Module list outputs may vary across machines and JDK distributions.

## 13. Summary

- `java.base` is the core module of JPMS and is read implicitly by every named module.
- Not every Java SE API resides in `java.base`. Features such as logging, JDBC, HTTP Client, XML, desktop, and management live in functional modules.
- `module-info.java` uses `requires` for dependencies outside `java.base`; permission to use public APIs also depends on `exports` and readability relationships.
- `java --list-modules` and `ModuleFinder.ofSystem()` inspect modules provided by the runtime; `--show-module-resolution` and `ModuleLayer.boot()` help inspect the modules selected for execution.
- `jlink` allows minimizing a runtime by module, but cannot omit `java.base`.
- Always check modules on the exact version and runtime image, avoiding the assumption that a full JDK and a deployment runtime share the same module list.

## 14. References

- Java Language Specification, Modules and Module Declarations sections.
- Java Platform Module System — JEP 261.
- Java SE API: `java.lang.Module`, `java.lang.ModuleLayer`, `java.lang.module.ModuleDescriptor`, `java.lang.module.ModuleFinder`.
- JDK Tools Reference: `java`, `javac`, `jdeps`, `jlink` for the Java version in use.
