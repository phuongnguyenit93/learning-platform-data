# Analyzing Module Dependencies with jdeps

`jdeps` is a command-line tool included with the JDK for analyzing dependencies at the class file, package, archive, and Java module levels. The tool reads bytecode along with module metadata to determine which types a class or module references, which modules those references belong to, and which JDK modules an application needs to run or to create a custom runtime image with `jlink`.

In the Java Platform Module System (JPMS), a module explicitly declares dependencies using the `requires` directive in `module-info.java`. However, when migrating a legacy application from the classpath to the module path or preparing a runtime image, looking only at source code and `requires` declarations may not be enough. `jdeps` helps cross-check the actual dependencies reflected in class files against the module descriptor, find missing references, and suggest the list of required modules.

`jdeps` performs static analysis. It does not run the application and does not observe every class loaded dynamically at runtime. Therefore, its output serves as a baseline for understanding dependencies and preparing configuration, after which you still need to test the application in a real environment.

## 1. What Is a Module Dependency?

A Java module can use public types exported by another module. The consuming module declares its dependency using `requires`:

```java
module com.example.app {
    requires java.sql;
}
```

In this example, `com.example.app` needs the `java.sql` module to compile and run code that references JDBC APIs.

A module graph is a directed graph consisting of modules and their dependency relationships. If module A requires B, and B requires C, then C is part of the dependency graph that must be resolved when linking A. The module system checks these relationships to determine which modules can read and use types from other modules.

Some important keywords in a module descriptor:

| Directive | Meaning |
|---|---|
| `requires` | Declares a module dependency |
| `requires transitive` | Allows dependent modules to transitively receive the dependency when reading this module |
| `requires static` | A dependency needed at compile time that may be optional at runtime |
| `exports` | Allows other modules to access public types in the exported package |
| `opens` | Allows deep reflective access to a package according to module rules |
| `uses` | Declares a service that the module consumes |
| `provides ... with ...` | Declares an implementation provided for a service |

`jdeps` helps inspect module dependencies and the references found in bytecode. It does not replace designing the module descriptor: developers still decide which dependencies should be `transitive`, which packages should be exported, and which services need to be declared.

## 2. What Does jdeps Analyze?

`jdeps` can analyze several types of inputs:

- A `.class` file.
- A directory containing class files, typically an exploded module or compiler output.
- A JAR.
- A JMOD.
- A module resolvable on the module path.

The tool can report dependencies at the following levels:

| Analysis Level | Content |
|---|---|
| Class | Which class references which class |
| Package | Which package depends on which package |
| Archive | Which JAR/JMOD depends on another archive |
| Module | Which module depends on which module |
| JDK module | Which Java platform modules are required |

A reference can appear because a type is used in a field, method signature, superclass, interface, annotation, exception, or bytecode inside a method. Depending on the options, `jdeps` can print dependencies only at the module level or show details down to the package/class level.

Module dependency results are especially useful when:

- Identifying the JDK modules needed for an application.
- Preparing inputs for `jlink`.
- Verifying whether a modular JAR's `requires` declarations make sense.
- Analyzing a legacy library before creating a module descriptor.
- Finding references to JDK internal APIs.
- Investigating missing dependencies or an incorrect module path.

## 3. Checking the Version and Basic Syntax

`jdeps` is located in the JDK. Check the version:

```sh
jdeps --version
```

View help:

```sh
jdeps --help
```

General syntax:

```text
jdeps [options] <path>...
```

Multiple files or archives can be passed. Commonly used options:

| Option | Effect |
|---|---|
| `--list-deps` | Lists module dependencies |
| `--list-reduced-deps` | Lists reduced dependencies based on the module graph |
| `--print-module-deps` | Prints a comma-separated list of modules |
| `--module-path` | Specifies where to find modules |
| `--class-path` | Specifies where to find dependencies on the classpath |
| `--recursive` or `-R` | Recursively analyzes dependencies |
| `-verbose:package` | Displays dependencies at the package level |
| `-verbose:class` | Displays dependencies at the class level |
| `-summary` | Summarizes dependencies by archive |
| `--missing-deps` | Finds unresolved dependencies |
| `--check` | Checks module dependencies and the module descriptor |
| `--jdkinternals` | Finds usage of JDK internal APIs |
| `--multi-release` | Selects the version in a multi-release JAR to analyze |

The detailed list of options may vary by JDK version. Always check `jdeps --help` for the exact JDK used in your build.

## 4. Example of a Modular Application with a java.sql Dependency

Create the source structure:

```text
project/
└── src/
    └── com.example.app/
        ├── module-info.java
        └── com/
            └── example/
                └── app/
                    └── Main.java
```

Contents of `module-info.java`:

```java
module com.example.app {
    requires java.sql;
}
```

Contents of `Main.java`:

```java
package com.example.app;

import java.sql.Connection;
import java.sql.SQLException;

public class Main {
    public static String databaseName(Connection connection)
            throws SQLException {
        return connection.getMetaData().getDatabaseProductName();
    }

    public static void main(String[] args) {
        System.out.println("Module dependency analysis");
    }
}
```

Class `Main` references `Connection` and `SQLException` from the `java.sql` module. The `databaseName` method only illustrates how to use the JDBC API; the main program does not need to open a database connection, so the example can run without a JDBC driver.

Compile the module:

```sh
mkdir -p mods
javac --module-source-path src -d mods -m com.example.app
```

The result is an exploded module:

```text
mods/
└── com.example.app/
    ├── module-info.class
    └── com/
        └── example/
            └── app/
                └── Main.class
```

Run the module on the module path:

```sh
java --module-path mods -m com.example.app/com.example.app.Main
```

Stdout:

```text
Module dependency analysis
```

This example uses module syntax and tools available since Java 9; the commands remain applicable on JDK 17+.

## 5. Listing Module Dependencies with --list-deps

To see which modules a modular application needs, use:

```sh
jdeps --module-path "$JAVA_HOME/jmods:mods" \
      --module com.example.app \
      --list-deps
```

On Windows PowerShell, the module path separator is a semicolon:

```powershell
jdeps --module-path "$env:JAVA_HOME\jmods;mods" --module com.example.app --list-deps
```

In this example, the module path includes:

- `$JAVA_HOME/jmods`: the JMODs of the JDK being used.
- `mods`: the directory containing the exploded `com.example.app` module.
- `--module com.example.app`: the module being analyzed.
- `--list-deps`: requests printing module dependencies.

The output list may include `java.base`, `java.sql`, and modules pulled in by dependency relationships within the JDK. The exact output can vary depending on the JDK version and dependency structure; do not copy a sample module list as a fixed configuration.

`java.base` is the foundational module that every Java module depends on directly or indirectly. When an application uses JDBC APIs, `java.sql` is a key dependency that must be present in the module graph.

## 6. Printing the Module List for jlink with --print-module-deps

When preparing a custom runtime image, a useful option is `--print-module-deps`:

```sh
jdeps --module-path "$JAVA_HOME/jmods:mods" \
      --module com.example.app \
      --print-module-deps
```

This option prints module names as a comma-separated list, which is convenient to pass to `jlink --add-modules` or store in a build script.

Example workflow:

```sh
jdeps --module-path "$JAVA_HOME/jmods:mods" \
      --module com.example.app \
      --print-module-deps

jlink --module-path "$JAVA_HOME/jmods:mods" \
      --add-modules com.example.app \
      --output app-image
```

`jlink` automatically resolves dependencies of the root module `com.example.app`. The list from `jdeps --print-module-deps` is useful for understanding required modules and building runtime configurations, but it does not replace testing. If the application loads modules via reflection, plugins, or class names read from configuration, you must add the corresponding modules using appropriate link options.

Do not automatically assume that every module found in a single static analysis pass represents the complete set of runtime dependencies. In particular, modules loaded only in rare functional branches may require separate testing.

## 7. Differences Between --list-deps, --list-reduced-deps, and --print-module-deps

These three options serve similar purposes but produce different output formats:

| Option | Use When |
|---|---|
| `--list-deps` | You want a readable list of module dependencies |
| `--list-reduced-deps` | You want a reduced list based on transitive relationships in the module graph |
| `--print-module-deps` | You want a comma-separated string of modules for scripting/linking |

For modules with `requires transitive`, a dependency may already be implied through another module in the graph. The reduced list can omit redundant relationships according to module resolution rules. That does not mean the dependency does not exist; it simply means the graph can be represented more concisely.

When diagnosing issues, start with `--list-deps` for readability. When preparing a module list for a build pipeline, look at `--print-module-deps`. When comparing graph representations, check `--list-reduced-deps`.

## 8. Analyzing a JAR Running on the Classpath

Legacy applications may not have a `module-info.java` yet. `jdeps` can still analyze the JAR and map references to JDK modules.

Suppose you have:

```text
app.jar
lib/
├── client.jar
└── common.jar
```

Analyze the JAR's dependencies:

```sh
jdeps --class-path "lib/*" --list-deps app.jar
```

`--class-path` specifies dependencies that `jdeps` can use to resolve class references outside the JAR. The `lib/*` wildcard is a common classpath syntax to include JARs in a directory.

To view detailed dependencies by package:

```sh
jdeps --class-path "lib/*" -verbose:package app.jar
```

To view each class:

```sh
jdeps --class-path "lib/*" -verbose:class app.jar
```

When analyzing a classpath application, the JDK module dependency output can guide modularization. However, third-party JARs do not automatically become JDK modules. They may still need to be distributed on the classpath, converted into modular JARs, or placed on the module path according to the appropriate rules.

## 9. Recursive Analysis and Filters

`jdeps` can analyze dependent archives more deeply. Use `--recursive` or `-R` when you want to follow dependencies across archives found on the classpath/module path:

```sh
jdeps --recursive --class-path "lib/*" --list-deps app.jar
```

Recursion is useful when you want to understand what additional dependencies are pulled in by the libraries your application uses. However, it can produce longer reports and broaden the analysis scope.

To adjust the level of detail:

```sh
jdeps -verbose:package --class-path "lib/*" app.jar
jdeps -verbose:class --class-path "lib/*" app.jar
```

Filters can help focus on the specific dependencies you want to inspect. For example, `-filter:archive`, `-filter:package`, `-filter:module`, and `-filter:none` control how internal or external dependencies are displayed at the corresponding level. Exact syntax should be confirmed with `jdeps --help` for your current JDK.

If the report is too long, start at the module or package level and only switch to class-level when you need to pinpoint the exact class creating a dependency.

## 10. Finding Missing Dependencies with --missing-deps

When a JAR references a class that cannot be resolved, you can use:

```sh
jdeps --missing-deps --class-path "lib/*" app.jar
```

This option focuses on missing dependencies. It is useful when:

- A JAR depends on another library, but that library is not on the classpath.
- A dependency version no longer contains a class referenced by the application.
- The build or packaging missed an artifact.
- The application runs on a developer machine but is missing classes in the deployment environment.

If you do not provide the correct classpath/module path, the tool may report missing classes even though the dependency actually exists elsewhere. Before concluding a library is missing, verify the paths and artifact versions.

`--ignore-missing-deps` can suppress warnings about unresolved dependencies in certain analysis scenarios. This is an option to continue inspecting the remaining dependencies; it does not fix missing dependencies and should not be used to declare the application ready to run.

## 11. Checking the Module Descriptor with --check

For modular applications, `--check` helps verify module dependencies and the current descriptor:

```sh
jdeps --module-path "$JAVA_HOME/jmods:mods" \
      --check com.example.app
```

The tool displays the relevant dependency graph and can suggest a descriptor with the dependencies evaluated as necessary. This helps detect redundant `requires` declarations or dependencies that need review.

When reading the output:

1. Check the module being inspected.
2. Compare the modules required in the descriptor.
3. Check which modules are used directly through bytecode.
4. Review the tool's suggested descriptor.
5. Evaluate the API implications before modifying `module-info.java`.

Do not remove a `requires` directive simply because it does not appear in a static report. A dependency may be needed for reflection, service binding, runtime configuration, or code paths not present in the analyzed class files. Conversely, redundant declarations can widen the module graph and increase coupling.

After editing the descriptor, recompile and run tests on the module path to confirm.

## 12. Generating a Module Descriptor for Legacy Libraries

A legacy library JAR may not have `module-info.class`. `jdeps` can suggest a module descriptor using `--generate-module-info`.

Example:

```sh
jdeps --generate-module-info generated-modules legacy-library.jar
```

The tool creates an output structure under the `generated-modules` directory with a suggested `module-info.java` file for the archive.

If the library needs to be treated as an open module to support deep reflective access for compatibility requirements, consider `--generate-open-module`:

```sh
jdeps --generate-open-module generated-open-modules legacy-library.jar
```

The generated descriptor is a starting point, not an approved design. Review and edit:

- The suggested module name.
- The `requires` directives.
- Packages that need `exports`.
- Packages that need `opens` for reflection.
- Any `uses` and `provides` services if the library uses them.
- Optional or compile-time-only dependencies.

After finalizing the descriptor, compile `module-info` and repackage according to the appropriate modular JAR/JMOD workflow. Do not assume `jdeps` automatically understands all API rules or compatibility goals of the library.

## 13. Finding JDK Internal APIs with --jdk-internals

One risk when upgrading Java is that an application depends on JDK internal APIs, such as classes in `sun.*` or `com.sun.*` packages that are not guaranteed as stable public APIs.

Use:

```sh
jdeps --jdk-internals app.jar
```

The tool can report the referenced internal classes or packages and suggest public API replacements if available.

Why this needs to be addressed:

- Internal APIs may change or be removed between JDK releases.
- Module encapsulation restricts access to internal packages.
- The application may need module-opening flags at runtime if legacy dependencies remain.
- Temporary package-opening flags are not a substitute for migrating to public APIs.

If the results point to internal dependencies, look for supported APIs in Java SE or official libraries. Only use module-opening mechanisms such as `--add-exports` or `--add-opens` when you understand the scope and have a compatibility reason; treat them as transitional measures, not long-term solutions.

## 14. Analyzing Public APIs with --api-only

`--api-only` restricts analysis to dependencies appearing in the exported public API, such as types in public/protected signatures. This is useful when you want to understand which dependencies become part of the API contract provided by the module.

Example:

```sh
jdeps --api-only --module-path "$JAVA_HOME/jmods:mods" \
      --module com.example.app
```

Compare API-only results with a full analysis:

- API-only shows dependencies that can affect consumers of the module when compiling dependent code.
- Full analysis also includes internal references within the implementation.
- A module may need an internal dependency to run without necessarily exposing that dependency in its public API.

This provides the basis for considering `requires transitive`. If module A's public API uses types exported by module B, consumers of A may need to read B to compile. However, do not automatically make every dependency transitive; evaluate the API contract and module design.

## 15. Multi-Release JARs and --multi-release

A multi-release JAR can contain different class files for different Java versions in the `META-INF/versions/N` directory. When analyzing, you need to select the appropriate version:

```sh
jdeps --multi-release 17 --list-deps library.jar
```

The `--multi-release` option tells `jdeps` to analyze the class entries targeting the specified Java release. This is useful when:

- A library has separate implementations for Java 9, 11, 17, or other releases.
- Dependencies of version-specific implementations may differ.
- You need to inspect the JAR against a specific target runtime.

Use the version corresponding to the runtime supported by your product and verify that the JAR is actually marked as multi-release in its manifest with `Multi-Release: true`. Analyzing base entries and analyzing versioned entries can yield different results.

Do not use an analysis result for Java 17 to claim that all implementations in the JAR have the same dependencies on Java 21 or another release.

## 16. Static Dependencies vs. Dynamically Loaded Dependencies

`jdeps` analyzes references that can be inferred from class files and module metadata. There are runtime dependencies that do not appear as simple static class references:

- Class names read from a configuration file and loaded via `Class.forName`.
- Plugins discovered from a directory or custom registry.
- Frameworks generating proxies or classes via bytecode generation.
- JNI loading native libraries by name.
- Service providers discovered through service loading mechanisms.
- Dependencies activated only by a feature flag or business branch.

Example:

```java
String implementation = configuration.get("driver.class");
Class<?> type = Class.forName(implementation);
Object driver = type.getDeclaredConstructor().newInstance();
```

`jdeps` can see references to `Class` and the reflection API, but it does not necessarily know the runtime value of `implementation`. Therefore, it cannot automatically infer every module or JAR needed for class strings obtained from configuration.

How to handle this:

1. Locate configurations containing class names and providers.
2. Check whether the module descriptor declares `uses`/`provides` services.
3. Identify the modules required across functional flows.
4. Add the appropriate modules to the module path or as root modules in `jlink`.
5. Run integration tests on the generated runtime image.

For service binding, consider `jlink --bind-services` when the application uses `ServiceLoader` and needs providers in the image. `jdeps` is part of the analysis, not proof that every dynamic dependency has been found.

## 17. jdeps vs. Maven/Gradle Dependency Trees

`jdeps` and build tools both help understand dependencies, but they analyze different data:

| Tool | Primary Data | Question Answered |
|---|---|---|
| `jdeps` | Class files, archives, and module descriptors | Which types or modules are referenced by the bytecode/module? |
| Maven dependency tree | Dependency declarations and Maven resolution rules | Which artifacts are pulled into the build, and through which dependency? |
| Gradle dependencies | Gradle configurations and dependency graph | Which dependencies belong to compile/runtime/test configurations? |
| `jlink` | Resolved module graph | Which modules are included in the created runtime image? |

A dependency present in the Maven/Gradle graph might not be referenced in the bytecode of a specific execution path. Conversely, a class loaded via reflection might not show up as a static dependency in `jdeps` output.

When removing a library from an application, combine the build-tool dependency tree with bytecode analysis and tests. Do not remove a dependency just because `jdeps` does not display it; it may be used at runtime through configuration, a service provider, or a framework.

## 18. From jdeps Results to a Custom Runtime with jlink

A common workflow:

```text
Source code
    |
    v
javac
    |
    v
Class files / modular JAR
    |
    v
jdeps
    |
    v
Module dependency report
    |
    v
Review dynamic dependencies
    |
    v
jlink
    |
    v
Custom runtime image
```

Complete command example:

```sh
jdeps --module-path "$JAVA_HOME/jmods:mods" \
      --module com.example.app \
      --print-module-deps

jlink --module-path "$JAVA_HOME/jmods:mods" \
      --add-modules com.example.app \
      --output app-image

app-image/bin/java --list-modules
app-image/bin/java -m com.example.app/com.example.app.Main
```

On Windows, replace the module path separator with a semicolon and invoke the executable in the `app-image\bin` directory.

`jlink` automatically resolves dependencies declared in the module graph. The list from `jdeps` helps verify analysis results and prepare configuration, while dynamically loaded modules must be handled separately. After linking, run tests on the image rather than only running on the full development JDK.

## 19. Exporting Dependency Reports in DOT Format

`jdeps` can export dependency graph data for viewing with Graphviz/DOT tools.

Example:

```sh
jdeps --dot-output dependency-report \
      --module-path "$JAVA_HOME/jmods:mods" \
      --module com.example.app
```

The output directory contains files describing dependency relationships in DOT format. You can render them as images using Graphviz if the tool is installed:

```sh
dot -Tpng dependency-report/com.example.app.dot \
    -o dependency-report/com.example.app.png
```

Graphs are useful when a module has many dependencies or when you want to spot coupling between packages. The names and number of generated DOT files depend on the input and tool version.

When inspecting the graph, pay attention to arrow directions and the module/package scope. A large graph does not necessarily mean the application runs slowly; it describes reference relationships, not a runtime performance profile.

## 20. Common Errors When Using jdeps

| Symptom | Common Cause | Resolution |
|---|---|---|
| Module not found | Module path is missing JMODs/JARs or module name is wrong | Check `--module-path` and descriptor with `jar --describe-module`/`jmod describe` |
| Missing dependency | Missing JAR on the classpath or incompatible dependency | Add the right artifact/version and re-run |
| Dynamically loaded module not shown | Static analysis cannot know class names from configuration/reflection | Check configuration, ServiceLoader, and runtime tests |
| Output too long | Using class-level or recursive analysis across many archives | Start with `--list-deps` or `-summary`, then increase detail |
| Different results across JDKs | Module graph or multi-release entries differ by release | Specify the JDK and use the appropriate `--multi-release` |
| `--check` suggests removing requires | Dependency not seen in static references of the analyzed set | Check reflection, services, and API contract before editing |
| `--generate-module-info` creates unusable descriptor | Library has special dependencies or package export/open needs | Review descriptor, add directives, and recompile |
| JDK internal API reported | Library references non-public packages | Find replacement APIs and upgrade dependencies |
| `jlink` missing module after using jdeps output | Unaccounted dynamic runtime dependencies | Add required modules/providers and test on the image |
| `jdeps` cannot analyze archive | Corrupted file, unsupported format, or class version newer than the tool | Use a compatible JDK and verify the archive is valid |

When troubleshooting, verify the inputs first: the right files, the right JDK, the right classpath/module path, and the right release for multi-release JARs. Only then conclude that a dependency is missing or a descriptor is wrong.

## 21. Repeatable Dependency Analysis Workflow

1. Record the JDK version with `jdeps --version` and `java -version`.
2. Identify whether the input is a class directory, JAR, JMOD, or module.
3. Provide the complete required classpath or module path.
4. Run `--list-deps` to view module dependencies at an overview level.
5. Run `--print-module-deps` if a list is needed for a `jlink` pipeline.
6. Use `-verbose:package` or `-verbose:class` to locate specific reference sources.
7. Run `--missing-deps` to detect unresolved dependencies.
8. For explicit modules, use `--check` to review `requires`.
9. For legacy JARs, consider `--generate-module-info` and refine the descriptor manually.
10. Run `--jdkinternals` to detect dependencies on internal APIs.
11. Inspect dynamic dependencies, service providers, reflection, JNI, and configuration.
12. Create a runtime image with `jlink` and run tests on that image.
13. Save the commands, JDK version, and reports so results can be reproduced.

When running in CI, record the JDK version, `jdeps` command, module path, and artifact checksums. This helps compare results when dependencies or the JDK are upgraded.

## 22. Checklist

- [ ] Confirmed the correct JDK and `jdeps` version.
- [ ] Identified the input to analyze.
- [ ] Provided the correct classpath/module path.
- [ ] Used `--list-deps` to inspect module dependencies.
- [ ] Used `--print-module-deps` if preparing `jlink`.
- [ ] Inspected package/class details when needed.
- [ ] Checked for missing dependencies.
- [ ] Reviewed the module descriptor with `--check`.
- [ ] Reviewed generated module descriptors for legacy libraries.
- [ ] Checked for JDK internal APIs.
- [ ] Selected the right release for multi-release JARs.
- [ ] Accounted for dynamic dependencies and service providers.
- [ ] Tested the application on the final runtime image.

## 23. References

- Oracle JDK 21 Tool Reference — The `jdeps` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html
- Oracle JDK 21 Tool Reference — The `jlink` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html
- Java Platform Module System — Java Language and JVM Specifications: https://docs.oracle.com/javase/specs/

`jdeps` makes the relationships between bytecode, archives, and Java modules visible. By combining dependency lists, descriptor checks, internal API detection, and a review of dynamically loaded components, you can build a reliable module graph and prepare a custom runtime image suited to your application.