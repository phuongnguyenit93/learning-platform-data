# The jdeps Command in Java

## Objectives

After this lesson, you can use `jdeps` to analyze dependencies of `.class` files, class directories, and JARs; read dependencies at the package, class, and module levels; find missing dependencies and JDK internal APIs; analyze module graphs; generate module lists for `jlink`; export dependency graphs in DOT format; handle multi-release JARs; and understand the limitations of static analysis when investigating real-world applications.

## 1. What is jdeps?

**jdeps** is a command-line tool bundled with the JDK for analyzing Java bytecode dependencies. The tool can display dependency relationships at the package or class level, and also supports module analysis in the Java Platform Module System (JPMS).

`jdeps` is commonly used to:

- Check which packages/classes a library depends on.
- Identify required JDK modules before creating a runtime image with `jlink`.
- Find missing dependencies on the classpath or module path.
- Detect whether an application is calling unsupported JDK internal APIs.
- Prepare to convert a JAR without a module descriptor into a modular JAR.
- Review module graphs and redundant `requires` directives.
- Understand the impact of a package or module on other components.

`jdeps` analyzes compiled class files, not source code like `javac`. The results show the references expressed in the bytecode; they do not prove that every execution path of the program has been tested.

## 2. Checking the JDK and Basic Syntax

`jdeps` is provided with the JDK. Open a terminal and check:

~~~bash
jdeps --version
~~~

View help:

~~~bash
jdeps --help
~~~

General syntax:

~~~bash
jdeps [options] path...
~~~

The `path` argument can be:

- A `.class` file.
- A directory containing class files.
- A JAR file.
- A fully qualified class name to analyze the corresponding class files.

Examples:

~~~bash
jdeps build/classes
jdeps build/classes/com/example/Main.class
jdeps app.jar
~~~

If analyzing a class name instead of a path, you must provide where to find the class via the appropriate classpath or module path.

Use `jdeps` from the JDK corresponding to the release you want to inspect. For multi-release JARs, you must select the class version to analyze using the `--multi-release` option.

## 3. Viewing Dependencies at Different Levels

### Dependency Summary

The `-summary` or `-s` option prints a dependency summary:

~~~bash
jdeps -summary app.jar
~~~

The output format typically shows which modules or archives an archive depends on. This is a good starting point when you only need the big picture.

### Package-Level Dependencies

~~~bash
jdeps -verbose:package app.jar
~~~

This command displays relationships between packages. By default, dependencies within the same package are filtered out of the results.

This view is useful when designing packages, separating layers, or checking whether one package has a reverse dependency on another.

### Class-Level Dependencies

~~~bash
jdeps -verbose:class app.jar
~~~

This command displays the source class referencing the target class. By default, dependencies within the same archive are filtered out of the results.

### Displaying All Class-Level Dependencies

~~~bash
jdeps -verbose app.jar
~~~

The `-verbose` option is equivalent to `-verbose:class` combined with `-filter:none`. The output can be very long for large applications.

| Option | Result |
|---|---|
| -summary or -s | Dependency summary |
| -verbose:package | Package-level dependencies |
| -verbose:class | Class-level dependencies |
| -verbose | All class-level dependencies, including dependencies within the same archive |

When reading the output, an arrow from A to B indicates that A depends on B. This is a reference relationship and does not necessarily mean B is called on every run.

## 4. Analyzing Dependencies of Applications with External Libraries

If a JAR depends on other libraries, specify the classpath so `jdeps` can resolve external types.

For example, if dependency libraries are in the `lib` directory:

~~~bash
jdeps --class-path "lib/*" app.jar
~~~

This can be combined with module analysis:

~~~bash
jdeps --class-path "lib/*" --print-module-deps app.jar
~~~

On Windows, the classpath element separator is a semicolon; on Linux/macOS, it is a colon. A wildcard in the classpath such as `lib/*` allows loading JARs in the directory according to Java classpath rules.

For modular applications, use the module path:

~~~bash
jdeps --module-path mods --module com.example.app
~~~

Some related options:

- `--class-path`: where to find class files and libraries on the classpath.
- `--module-path`: where to find modules.
- `--upgrade-module-path`: module path containing replacement or upgraded modules.
- `--system`: specifies an alternate Java home as the system module path.
- `--add-modules`: adds modules to the root set being analyzed.

If libraries are missing when running `jdeps`, check the classpath/module path before concluding that the application has broken dependencies. Analyzing with incomplete inputs can produce `not found` results or `missing` warnings.

## 5. Analyzing Dependencies at the Module Level

`jdeps` provides specialized options for JPMS.

### --list-deps

~~~bash
jdeps --list-deps app.jar
~~~

Lists module dependencies and JDK internal API packages if referenced. This option transitively analyzes libraries on the classpath/module path if they are referenced.

To avoid traversing transitive dependencies, use:

~~~bash
jdeps --list-deps --no-recursive app.jar
~~~

### --list-reduced-deps

~~~bash
jdeps --list-reduced-deps app.jar
~~~

The output omits module read edges implied by `requires transitive` relationships. For example, if M1 reads M2 and M2 `requires transitive` M3, then the read relationship from M1 to M3 is implied and does not need to be displayed again.

### --print-module-deps

~~~bash
jdeps --print-module-deps app.jar
~~~

This option prints a comma-separated list of module dependencies. The result corresponds to the reduced dependency list and can be used as input for `jlink --add-modules`.

Example output might look like:

~~~text
java.base,java.logging,java.sql
~~~

The actual list depends on the bytecode and libraries analyzed; do not copy this example list for every application.

### Distinguishing the Three Options

| Option | Use when |
|---|---|
| --list-deps | You want to see module dependencies and internal API packages |
| --list-reduced-deps | You want to see dependencies after removing implied reads edges |
| --print-module-deps | You need a comma-separated module list for jlink |

For modular applications, use `--module` to select the root module:

~~~bash
jdeps --module-path mods --module com.example.app --list-deps
~~~

If the application requires service providers discovered through service binding, review the services/providers separately along with the `jlink --bind-services` option. A static dependency list does not replace testing `ServiceLoader` in the runtime image.

## 6. Using jdeps to Assist Creating Runtime Images with jlink

One common use of `jdeps` is identifying the JDK modules an application needs before creating a runtime image.

For a classpath application:

~~~bash
jdeps --class-path "lib/*" --print-module-deps app.jar
~~~

Suppose the output is:

~~~text
java.base,java.logging,java.sql
~~~

You can use those modules to create a runtime image:

~~~bash
jlink --add-modules java.base,java.logging,java.sql --output runtime
~~~

Then run the application using the runtime image, keeping `app.jar` and its dependencies on the classpath:

Linux/macOS:

~~~bash
runtime/bin/java -cp "app.jar:lib/*" com.example.Main
~~~

Windows PowerShell:

~~~powershell
.\runtime\bin\java.exe -cp "app.jar;lib/*" com.example.Main
~~~

Notes:

- `jdeps` does not create the runtime image; `jlink` performs that task.
- `jdeps` only suggests modules based on the bytecode dependencies it observes.
- Classpath applications still need the application JAR and external libraries at runtime.
- For modular applications, you must include the application module on the module path and select it as the root module when using `jlink`.
- Reflection, service loading, resources, native libraries, and configuration-driven dependencies may need to be added after review.

Do not remove a module from the image simply because `jdeps` does not report a dependency on it. Before releasing, run the application using the actual runtime image and execute integration tests.

## 7. Finding Dependencies on JDK Internal APIs

JDK internal APIs are internal classes/packages that are not supported, stable Java SE APIs. Using them can break applications when upgrading the JDK or when module encapsulation is enforced more strictly.

Find references to internal APIs:

~~~bash
jdeps --jdk-internals app.jar
~~~

If there are external dependency libraries:

~~~bash
jdeps --jdk-internals --class-path "lib/*" app.jar
~~~

`jdeps` can display classes using internal APIs and suggest replacement APIs when known. This output is especially useful when upgrading from an older JDK to a newer JDK.

For example, if a library accesses internal `sun.*` or `com.sun.*` packages, check whether a public API in `java.*` or `javax.*` meets the requirement.

**Do not treat `--add-exports` or `--add-opens` as a long-term fix.** These options can temporarily allow access in a specific configuration, but they do not turn an internal API into a supported API. Prefer replacing them with public, documented APIs.

The `--jdk-internals` option cannot be used together with the `-p`, `-e`, and `-s` filters. Run a separate command when you need to check internal APIs.

## 8. Finding Missing Dependencies

Use `--missing-deps` to find dependencies that `jdeps` cannot resolve:

~~~bash
jdeps --missing-deps app.jar
~~~

If external libraries are in the `lib` directory:

~~~bash
jdeps --missing-deps --class-path "lib/*" app.jar
~~~

Common causes:

- Dependency JAR is missing from the classpath/module path.
- Analyzing the wrong library version.
- Class files were compiled against an API not present in the target JDK.
- Dependencies were excluded from the build output or packaged incompletely.
- Analyzing a partial artifact instead of the entire application.

The `--ignore-missing-deps` option tells `jdeps` to ignore unfound dependencies:

~~~bash
jdeps --ignore-missing-deps app.jar
~~~

This is only a reporting adjustment option. It does not download libraries, add dependencies, or fix the application. Do not use it to hide a dependency that is actually required.

`--missing-deps` cannot be combined with `-p`/`--package`, `-e`/`--regex`, and `-s`/`--summary`. When investigating missing dependencies, run a separate command without those mutually exclusive options.

## 9. Filtering Dependencies and Limiting Analysis Scope

When the output is too large, you can filter by package, regex, or module.

### Filtering by Package

~~~bash
jdeps --package java.sql app.jar
~~~

You can specify `--package` multiple times to check multiple packages. This option cannot be used at the same time as `--regex`.

### Filtering by Regular Expression

~~~bash
jdeps --regex 'java\..*' app.jar
~~~

The regex is applied to the target dependencies to find. Use appropriate shell quoting to prevent special characters from being interpreted before being passed to `jdeps`.

### Filtering by Module

~~~bash
jdeps --require java.sql app.jar
~~~

The `--require` option finds dependencies matching the specified module. It can be used multiple times.

### Filtering Analyzed Classes

~~~bash
jdeps --include 'com\.example\..*' app.jar
~~~

`--include` restricts which classes are included in the analysis. It differs from `--package` or `--regex`: `include` filters the source classes being analyzed, whereas `package`/`regex` filters the dependencies being searched.

### Filter Modes

| Option | Meaning |
|---|---|
| -filter:package | Filter dependencies within the same package; default |
| -filter:archive | Filter dependencies within the same archive |
| -filter:module | Filter dependencies within the same module |
| -filter:none | Do not filter dependencies within the same package/archive |
| -filter regex | Filter dependencies matching a regular expression |

When you need to see all relationships within an archive:

~~~bash
jdeps -verbose:class -filter:none app.jar
~~~

### Recursive Analysis

~~~bash
jdeps -R app.jar
~~~

`-R` or `--recursive` traverses runtime dependencies and implicitly enables `-filter:none`. Use this when you need to look deep into transitive dependencies.

To analyze only direct dependencies, use:

~~~bash
jdeps --no-recursive app.jar
~~~

Recursive analysis can significantly increase output size, especially when the classpath contains many libraries.

## 10. Reverse Dependency Analysis and Compile-Time View

### Reverse Dependencies with --inverse

`--inverse` finds artifacts that directly or indirectly depend on the selected dependency. It must be paired with a `--require`, `--package`, or `--regex` filter.

Example:

~~~bash
jdeps --inverse --require java.sql app.jar
~~~

This is useful when you need to know which modules/packages are affected if a dependency is changed or removed.

### Compile-Time Dependency View

~~~bash
jdeps --compile-time --module-path mods --module com.example.app
~~~

`--compile-time` analyzes the compile-time view of transitive dependencies. It can help understand which types are needed at compile time and the dependency relationships represented by the module graph.

The compile-time view and runtime view serve different purposes. Do not use one result as a substitute for the other when investigating linking or deployment issues.

## 11. Exporting Dependency Graphs in DOT Format

`jdeps` can export graphs in DOT format to visualize dependencies.

~~~bash
jdeps --dot-output deps-dot app.jar lib/parser.jar lib/common.jar
~~~

The `deps-dot` directory may contain:

- One `.dot` file for each analyzed archive.
- `summary.dot` showing dependency relationships between archives.

You can convert `summary.dot` to SVG using Graphviz:

~~~bash
dot -Tsvg deps-dot/summary.dot -o deps.svg
~~~

Graphviz is an external tool outside the JDK; `jdeps` only generates the DOT files. For large applications, filter packages/modules before generating the graph so the diagram remains readable and focused on the area under investigation.

## 12. Analyzing Multi-Release JARs

A multi-release JAR can contain multiple versions of classes in the same archive, such as base classes and alternative classes under `META-INF/versions`.

When analyzing this type of JAR, select a specific release:

~~~bash
jdeps --multi-release 17 app.jar
~~~

You can use another release, for example:

~~~bash
jdeps --multi-release 21 app.jar
~~~

Or analyze the base section:

~~~bash
jdeps --multi-release base app.jar
~~~

The version value must be `base` or an integer of `9` or greater. Selecting the right target release is important because implementations in `META-INF/versions` may depend on different modules/APIs than the base classes.

When releasing a multi-release library, analyze and test each release the product supports rather than running only once on `base`.

## 13. Checking the Module Graph with --check

For named modules, `--check` analyzes the module's dependencies and prints:

- The module descriptor.
- Analyzed dependencies.
- The module graph after reducing implied edges.
- Unused qualified exports, if detected.

Example:

~~~bash
jdeps --module-path mods --check com.example.app
~~~

You can check multiple modules in the same command:

~~~bash
jdeps --module-path mods --check com.example.app,com.example.api
~~~

The output helps review `module-info.java` and detect unnecessary `requires` or unused qualified exports.

This is a module graph analysis tool; it does not modify the module descriptor itself. Review the results before removing `requires` or changing `exports`, especially when public APIs are used by external consumers.

## 14. Generating module-info.java for Non-Modular JARs

An older JAR may not have a module descriptor yet. `jdeps` supports generating a draft `module-info.java` from observed dependencies:

~~~bash
jdeps --generate-module-info generated-modules library.jar
~~~

For modules that need to be open for reflection:

~~~bash
jdeps --generate-open-module generated-open-modules library.jar
~~~

The tool generates the `module-info.java` file in the specified directory. This is a starting point for modularization, not a reviewed and release-ready module descriptor.

After generation:

1. Open the generated `module-info.java`.
2. Verify the module name and `requires` directives.
3. Verify which packages actually need `exports`.
4. Add `uses`/`provides` if the library has service contracts.
5. Review reflection, serialization, frameworks, and resources.
6. Recompile the module descriptor along with the sources or classes.
7. Verify with `jar --describe-module` and run tests on the module path.

`--generate-module-info` cannot be used together with `--dot-output` or `--class-path`. If you need to analyze external dependencies, prepare an appropriate module path and follow the constraints of this option.

Do not export every package just to make the module compile. Export only the APIs that consumers need to access; keep implementation packages encapsulated whenever possible.

## 15. Complete Hands-On Example

This example creates a small program with dependencies on `java.sql` and `java.logging` to read `jdeps` output.

Create `src/com/example/DependencyDemo.java`:

~~~java
package com.example;

import java.sql.Connection;
import java.util.logging.Logger;

public class DependencyDemo {

    private static final Logger LOG =
            Logger.getLogger(DependencyDemo.class.getName());

    public static void main(String[] args) {
        System.out.println("class=" + DependencyDemo.class.getSimpleName());
        System.out.println("sqlApi=" + Connection.class.getSimpleName());
        System.out.println("logger=" + LOG.getName());
    }
}
~~~

Compile with JDK 17 or later:

~~~bash
javac --release 17 -d build/classes src/com/example/DependencyDemo.java
~~~

Run the program:

~~~bash
java -cp build/classes com.example.DependencyDemo
~~~

Exact output:

~~~text
class=DependencyDemo
sqlApi=Connection
logger=com.example.DependencyDemo
~~~

Analyze package-level dependencies:

~~~bash
jdeps -verbose:package -filter:none build/classes
~~~

Analyze class-level dependencies:

~~~bash
jdeps -verbose:class -filter:none build/classes
~~~

Print the module dependency list:

~~~bash
jdeps --print-module-deps build/classes
~~~

For this example, verify that the output includes the JDK modules required by the bytecode, including `java.base`, `java.logging`, and `java.sql`. Output details and formatting may vary across JDKs.

Find internal APIs:

~~~bash
jdeps --jdk-internals build/classes
~~~

Find unresolved dependencies:

~~~bash
jdeps --missing-deps build/classes
~~~

Generate the graph:

~~~bash
jdeps --dot-output build/dependency-graph build/classes
~~~

This example illustrates that the same input can be analyzed from multiple perspectives. The fact that a program runs does not mean all dynamic or native dependencies have been detected.

## 16. Common Errors and How to Handle Them

### Class or Dependency Not Found

**Symptom:** output shows `not found` or `jdeps` cannot resolve a type.

**Cause:** missing JAR on the classpath, missing module on the module path, or analyzing a partial artifact.

**Resolution:** add `--class-path` or `--module-path`; check dependency paths and versions.

### Analyzing the Wrong Multi-Release JAR Version

**Symptom:** reported dependencies do not match the runtime the application supports.

**Cause:** `--multi-release` was not specified or the wrong release was selected.

**Resolution:** re-run with the correct target release number or `base`.

### Output Too Long

**Symptom:** results contain thousands of lines of class dependencies.

**Cause:** using `-verbose` or `-R` across the entire application and transitive dependencies.

**Resolution:** start with `-summary`, `--list-deps`, or `-verbose:package`; use `--include`, `--package`, `--regex`, or `--require` to narrow the scope.

### Misinterpreting --print-module-deps Output

**Symptom:** a runtime image is created, but the application is still missing classes or providers.

**Cause:** treating the bytecode analysis result as a complete list of all runtime components.

**Resolution:** review reflection, `ServiceLoader`, resources, JNI/JNA, native libraries, and configuration; run integration tests on the actual image.

### Confusing Internal APIs with Supported APIs

**Symptom:** the application runs on an older JDK but fails after upgrading.

**Cause:** depending on internal packages such as `sun.*` or `com.sun.*`.

**Resolution:** run `--jdk-internals` and replace with supported public APIs. Only use temporary export/open options when there is a clear removal plan.

### Errors When Generating a Module Descriptor

**Symptom:** the generated `module-info.java` fails to compile or fails to run.

**Cause:** the auto-generated descriptor does not fully handle services, reflection, package exports, or dynamic dependencies.

**Resolution:** treat the generated file as a draft, edit the module descriptor, recompile, and run tests on the module path.

### Using Incompatible Options

**Symptom:** `jdeps` reports that options cannot be combined.

**Cause:** for example, `--missing-deps` with `--package`/`--regex`/`--summary`, or `--generate-module-info` with `--class-path`/`--dot-output`.

**Resolution:** split into separate analysis runs according to supported option groups.

## 17. Limitations of jdeps

`jdeps` performs static analysis based on class files. It cannot guarantee detection of everything an application may load or use at runtime.

Cases that require additional verification:

- Classes loaded via `Class.forName` or names read from configuration files.
- Reflection and member access determined at runtime.
- `ServiceLoader`, plugins, and providers selected by configuration or environment.
- Native libraries via JNI/JNA and operating system libraries.
- Resources, template files, locale data, certificates, and configuration files.
- Dynamically generated classes or classes loaded from the network/external paths.
- File, network, process permissions, and deployment environment conditions.

`jdeps` is also not a vulnerability scanner, does not verify business logic, does not measure performance, and does not prove that an application runs correctly.

The best results come from combining:

1. Static analysis with `jdeps`.
2. Reviewing module/classpath and declared dependencies.
3. Runtime testing with the exact target JDK or runtime image.
4. Integration testing for services, resources, databases, TLS, and native code.
5. Monitoring actual logs and errors in the deployment environment.

## 18. jdeps Usage Checklist

- [ ] Run `jdeps --version` to confirm the JDK.
- [ ] Analyze the right class file, directory, or JAR.
- [ ] Use `-summary` for a high-level overview.
- [ ] Use `-verbose:package` or `-verbose:class` when detail is needed.
- [ ] Provide a complete classpath/module path.
- [ ] Use `--list-deps` or `--print-module-deps` when analyzing modules.
- [ ] Review the results before using them with `jlink`.
- [ ] Run `--jdk-internals` before upgrading the JDK.
- [ ] Run `--missing-deps` to find unresolved dependencies.
- [ ] Use filters/`--include` to narrow the output.
- [ ] Use `--multi-release` with the correct version for multi-release JARs.
- [ ] Use `--check` to review the module graph.
- [ ] Treat generated `module-info.java` as a draft requiring review.
- [ ] Combine static analysis with runtime tests for dynamic dependencies.
- [ ] Save analysis results in build/CI when tracking dependency changes.

## 19. Official References

- [The jdeps Command — Java SE 26 Tool Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html) — command syntax, class/package-level dependencies, module analysis, filters, recursive/inverse analysis, and examples.
- [Java Platform Module System — JLS Chapter 7](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-7.html) — module rules, `requires`, `exports`, `uses`, and `provides`.
- [The jlink Command — Java SE 26 Tool Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html) — creating runtime images and using module dependency lists.
- [The jar Command — Java SE 26 Tool Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jar.html) — inspecting a JAR's module descriptor with `jar --describe-module`.
- [JEP 261: Module System](https://openjdk.org/jeps/261) — design and principles of the Java Platform Module System.

`jdeps` helps turn hidden dependencies in bytecode into inspectable information that can be integrated into the build process. Choose the right classpath/module path and release, read the results at the appropriate analysis level, and verify dynamic dependencies with runtime tests before modifying the module graph or creating a runtime image.
