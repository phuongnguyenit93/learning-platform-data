# Dependency Analysis with jdeps

## 1. What is jdeps?

`jdeps` is a command-line tool included with the JDK for analyzing dependencies in Java class files, class directories, JARs, and modules. It reads bytecode and metadata to determine which classes or packages reference other classes, packages, or modules.

Dependency analysis helps answer questions such as:

- Which packages or modules does a library depend on?
- Does the application use any JDK internal APIs?
- Which dependencies are missing when analyzing an artifact?
- How can a legacy JAR be converted into a JPMS module?
- Which JDK modules need to be included in a runtime image created with `jlink`?
- Does a module descriptor declare redundant or missing dependencies?

`jdeps` performs **static analysis**. It reads identifiable references from bytecode and module descriptors; it does not run the application and does not record every class loaded during an actual execution.

This tool is especially useful when upgrading the JDK, migrating an application to JPMS, reducing runtime image size, auditing third-party libraries, and finding dependencies on JDK internal APIs.

## 2. What Does Dependency Mean in Java?

A class depends on another class when it uses a type, field, method, or member of that class. For example:

```java
package com.example;

import java.time.LocalDate;
import java.util.List;

public class Report {
    private final List<LocalDate> dates;

    public Report(List<LocalDate> dates) {
        this.dates = dates;
    }
}
```

The `Report` class has identifiable dependencies on `java.time.LocalDate` and `java.util.List`. These types belong to the `java.base` module.

Dependencies can be observed at multiple levels:

| Analysis Level | What It Shows |
|---|---|
| Class | Which class references which class |
| Package | Which source package depends on which target package |
| Archive/JAR | Which JAR depends on another archive or library |
| Module | Which module reads or requires which module |
| Public API | Types appearing in public/protected API signatures |

A dependency can appear in method signatures, field types, superclasses, interfaces, annotations, exceptions, or method bytecode. Depending on the options used, `jdeps` can analyze the entire class or only dependencies appearing in the public API.

## 3. Installing and Checking jdeps

`jdeps` is distributed with the JDK. Open Terminal, Command Prompt, or PowerShell and run:

```bash
jdeps --version
jdeps --help
```

If the system does not recognize `jdeps`, verify that the JDK is installed and that the JDK's `bin` directory is in your `PATH`.

You can locate the tool with:

Linux/macOS:

```bash
command -v jdeps
echo "$JAVA_HOME"
```

Windows PowerShell:

```powershell
Get-Command jdeps -All
$env:JAVA_HOME
```

`JAVA_HOME` should point to the JDK root directory. The `bin` directory inside the JDK contains `jdeps`, `javac`, `java`, and related tools.

The JDK version used to run `jdeps` can affect which system modules and class files the tool recognizes. When comparing results between a CI machine and a developer machine, record the JDK version.

## 4. General jdeps Syntax

Basic syntax:

```bash
jdeps [options] <path...>
```

`<path...>` can be a path to:

- A `.class` file.
- A directory containing class files.
- A JAR file.
- Multiple input paths provided in the same command.

Examples:

```bash
jdeps app.jar
jdeps -summary app.jar
jdeps -verbose:class app.jar
```

If no options are specified, `jdeps` displays package-level dependencies by default. You can add options to view a summary, specific classes, modules, missing dependencies, or graphs.

View all options supported by the current JDK with:

```bash
jdeps --help
```

Some option names have both long and short forms. For example, `-s` is equivalent to `--summary`; `-v` is equivalent to `--verbose`.

## 5. Analyzing a JAR or Class Directory

For a built library, pass the JAR path:

```bash
jdeps app.jar
```

For a directory containing class files:

```bash
jdeps build/classes
```

For a specific class file:

```bash
jdeps build/classes/com/example/Report.class
```

The output shows which source packages depend on which target packages. The format and number of lines depend on the artifact structure, available dependencies, and filter options.

An illustrative example of package-level output format:

```text
Report.class -> java.base
   com.example -> java.time
   com.example -> java.util
```

This is how to read it conceptually: the application class or package references the corresponding Java packages. Actual output may include additional packages, archives, or modules.

`jdeps` does not require extracting the JAR beforehand. If the goal is to inspect dependencies, passing the JAR path directly is usually simpler.

## 6. Viewing Dependencies at Different Detail Levels

`jdeps` supports multiple verbosity levels. Choosing the right level makes the output easier to read and narrow down.

### 6.1. Summary with --summary

`--summary` (short form `-s`) displays dependencies at a high-level summary:

```bash
jdeps --summary app.jar
```

This command is suitable for quickly checking which archives or modules a JAR depends on without reading every class.

### 6.2. Viewing Package-Level Dependencies

`--verbose:package` displays dependencies between packages:

```bash
jdeps --verbose:package app.jar
```

The package level is useful when you want to understand the overall structure of a library, such as which business packages depend on which utility or framework packages.

### 6.3. Viewing Class-Level Dependencies

`--verbose:class` displays class-to-class dependencies:

```bash
jdeps --verbose:class app.jar
```

This is a more detailed level, suitable when you need to find the specific class creating a dependency or investigate a reference to an unwanted API.

The short form `-v` is equivalent to class-level verbose mode and typically produces large output:

```bash
jdeps -v app.jar
```

### 6.4. Restricting Analyzed Classes

The `-include` option accepts a regular expression to restrict which classes are included in the analysis:

```bash
jdeps -include 'com\.example\..*' app.jar
```

This option filters the input classes to be analyzed. It differs from `--package` or `--regex`, which filter the discovered dependencies.

## 7. Analyzing Module Dependencies

`jdeps` can analyze JPMS modules on the module path or JDK system modules.

Example analyzing the `java.sql` module in the current JDK:

```bash
jdeps --module java.sql
```

Short form:

```bash
jdeps -m java.sql
```

If you need to specify a module path:

```bash
jdeps --module-path lib --module com.example.app
```

Where:

- `--module-path lib` specifies where to find application or dependency modules.
- `--module com.example.app` selects the root module to analyze.
- Modules declared via `requires` are considered when building the module graph.

For JDK modules, `jdeps` uses the system modules corresponding to the running JDK. You can specify another system image with `--system` if you need to analyze against a different Java runtime.

## 8. Listing Module Dependencies with --list-deps

`--list-deps` lists the detected module dependencies. For example:

```bash
jdeps --list-deps --module java.sql
```

On JDK 24.0.2 in the test environment, the output is:

```text
   java.base/jdk.internal.reflect
   java.logging
   java.transaction.xa
   java.xml
```

Specific output may vary by JDK version. The first line shows an internal package reference inside the `java.base` module; the remaining lines are the identified module dependencies.

You can request a reduced dependency list with:

```bash
jdeps --list-reduced-deps --module java.sql
```

Reduced mode omits module readability edges that are already implied by `requires transitive` relationships in the module graph.

If you only need a comma-separated list of modules to pass to `jlink`, use `--print-module-deps`:

```bash
jdeps --print-module-deps --module java.sql
```

Verified output on JDK 24.0.2:

```text
java.base,java.logging,java.transaction.xa,java.xml
```

This is a comma-separated list of module names, suitable as input for `jlink --add-modules` when configured with the corresponding module path.

## 9. Checking Module Descriptors with --check

For modules that already have a descriptor, `--check` analyzes dependencies and module declaration information:

```bash
jdeps --check java.sql
```

On JDK 24.0.2, the beginning of the output looks like:

```text
java.sql (jrt:/java.sql)
  [Module descriptor]
    requires mandated java.base;
    requires transitive java.logging;
    requires transitive java.transaction.xa;
    requires transitive java.xml;
```

`--check` can display the descriptor, the analyzed dependencies, and the module graph after reducing implied edges. It also identifies certain unused qualified exports.

You can check multiple modules by separating module names with commas:

```bash
jdeps --check java.sql,java.xml
```

When a module has a descriptor, compare the actual detected dependencies with the declared `requires` directives. A descriptor may declare redundant dependencies or need adjustments as APIs and implementations evolve.

Do not automatically remove every dependency the tool suggests is redundant. Verify API requirements, service loading, reflection, and runtime behavior before modifying the module descriptor.

## 10. Finding Dependencies on JDK Internal APIs

JDK internal APIs are internal classes or packages that are not guaranteed to be public, stable APIs. Applications that depend on them risk breaking when upgrading the JDK.

Use:

```bash
jdeps --jdk-internals app.jar
```

Or analyze a module:

```bash
jdeps --jdk-internals --module java.sql
```

In JDK 24.0.2, analyzing `java.sql` detects references to `jdk.internal.reflect` from `java.sql.DriverManager`. The output also displays a warning that JDK internal APIs are unsupported and may change incompatibly.

When an internal dependency is detected:

1. Identify the referenced internal class and package.
2. Find the recommended public replacement API.
3. Update the source code or upgrade the library causing the dependency.
4. Rebuild and run tests on the target JDK.
5. Re-run `jdeps --jdk-internals` to confirm the dependency has been removed.

Do not address warnings by merely adding flags to open or export internal packages. Those options may temporarily alter accessibility, but they do not turn an internal API into a supported API.

`--jdk-internals` cannot be used simultaneously with certain filter options such as `--package`, `--regex`, and `--summary`. Check `jdeps --help` for your JDK before combining options.

## 11. Finding Missing Dependencies

When an artifact references a class not present in the analyzed locations, `jdeps` can report missing dependencies.

Use:

```bash
jdeps --missing-deps app.jar
```

If you need to resolve dependencies outside the JDK, provide the classpath:

```bash
jdeps --class-path "lib/*" --missing-deps app.jar
```

`--class-path` has short forms `-cp` or `-classpath`. On Windows, use a semicolon between multiple path elements; on Linux/macOS, use a colon.

You can use `--ignore-missing-deps` to continue analysis when there are unresolvable dependencies:

```bash
jdeps --ignore-missing-deps --summary app.jar
```

This option ignores missing dependencies during analysis; it does not supply the missing libraries and does not fix runtime errors. Do not use it to conclude that an artifact is complete without first determining why a dependency could not be found.

`--missing-deps` cannot be combined with certain filter options such as `--package`, `--regex`, and `--summary`. If the command reports conflicting options, check the help output for your exact JDK version.

## 12. Filtering Dependencies by Package, Regex, or Module

For large applications, you can restrict the output based on specific criteria.

| Option | Purpose |
|---|---|
| `--package <package>` | Find only dependencies matching the package name |
| `--regex <pattern>` | Filter dependencies by regular expression |
| `--require <module>` | Filter dependencies by module name |
| `--inverse` | Find artifacts that directly or indirectly depend on nodes matching the filter |
| `-include <regex>` | Restrict which input classes are analyzed |

Example finding dependencies on the `java.sql` package:

```bash
jdeps --package java.sql app.jar
```

Finding dependencies by module:

```bash
jdeps --require java.sql app.jar
```

Inversely finding artifacts that depend on a package:

```bash
jdeps --inverse --package java.sql app.jar
```

`--inverse` must be paired with a filter such as `--require`, `--package`, or `--regex`. It helps answer the question "which parts depend on this package or module?" rather than only listing outgoing dependencies from the input.

The `--package`, `--regex`, and `--require` filters are mutually exclusive in a single command. Use one criterion at a time or run separate analyses.

## 13. Analyzing Public API Dependencies Only

A library may use many internal dependencies in its implementation while exposing only a small subset through its public/protected API.

Use `--api-only`:

```bash
jdeps --api-only app.jar
```

This option restricts analysis to dependencies appearing in the public and protected signatures of public classes, including field types, method parameters, return types, and checked exceptions.

It is useful when:

- Evaluating the dependencies that consumers of the library need to see.
- Auditing the public API before modularizing.
- Finding types from other libraries that are leaking into public signatures.
- Distinguishing API dependencies from implementation-only dependencies.

`--api-only` does not replace a full analysis. A library may not expose a dependency in its API and still require that dependency to execute internal methods.

## 14. Recursive Dependency Analysis

By default, `jdeps` analyzes dependencies within the scope of the specified inputs and options. You can instruct the tool to continue traversing runtime dependencies with `--recursive` or `-R`:

```bash
jdeps --recursive --class-path "lib/*" app.jar
```

Recursive mode helps reveal transitive dependencies through libraries referenced by the application.

If you only want direct analysis without traversing further dependencies, use:

```bash
jdeps --no-recursive --class-path "lib/*" app.jar
```

Recursion can make the output significantly larger, especially when the classpath contains frameworks and many libraries. Choose the mode based on the question you need to answer, and ensure all dependencies to be analyzed are present on the classpath or module path.

## 15. Exporting Dependency Graphs in DOT Format

`jdeps` can write dependency graphs to DOT files for visualization:

```bash
jdeps --dot-output dependency-graphs app.jar
```

The legacy short form is `-dotoutput`. The target directory will contain DOT files generated from the analysis, typically including archive-level or module-level graphs depending on the input.

You can use Graphviz to convert DOT into an image:

```bash
dot -Tpng dependency-graphs/app.jar.dot -o dependency-graph.png
```

Exact DOT filenames depend on the artifact and tool version; list the output directory to identify the generated files.

Graphs are useful for:

- Visualizing cross-dependent packages.
- Identifying densely connected module clusters.
- Finding circular dependencies at the package or archive level.
- Explaining library architecture in technical documentation.

DOT is only a graph description format; `jdeps` does not generate PNG images itself. You need Graphviz or a compatible tool to render them.

## 16. Inspecting Legacy JARs and Generating Suggested Module Descriptors

When migrating a non-modular JAR to JPMS, `jdeps` can generate a suggested module descriptor.

Use:

```bash
jdeps --generate-module-info generated-modules legacy-library.jar
```

The tool analyzes the JAR and creates a `module-info.java` file in the target directory. The generated descriptor serves as a starting point for developers to review and refine.

You can generate a suggestion for an open module:

```bash
jdeps --generate-open-module generated-open-modules legacy-library.jar
```

An open module allows deep reflection into the module's packages under JPMS rules. Choose this option only when a framework or application genuinely requires broad reflective access.

Do not ship an auto-generated descriptor to production without reviewing it. Check:

- `requires` directives and dependency versions.
- Which packages need `exports`.
- Which packages actually need `opens`.
- Service providers and service consumers.
- Whether the public API exposes types from other dependencies.
- Whether the module name is stable and follows project conventions.

Module descriptor generation options have combination restrictions with `--dot-output` and `--class-path`. When generating descriptors, run a dedicated command and check the help output of your running JDK.

## 17. Dependencies and Multi-Release JARs

A multi-release JAR can contain alternative classes for different Java versions under `META-INF/versions/`.

When analyzing a specific version, use `--multi-release`:

```bash
jdeps --multi-release 17 --summary library.jar
```

The value can be a Java version number of 9 or higher, or `base` to analyze the base content. This is important when a class's dependencies change across runtime versions.

If you omit the target version, the output may not accurately reflect the classes the JVM will select when running on a specific Java version. Analyze the exact version your application supports.

## 18. Using jdeps Output to Build a Runtime Image with jlink

A modular application can use `jdeps --print-module-deps` to obtain the list of required modules and pass that list to `jlink`.

Example with a JDK module:

```bash
jdeps --print-module-deps --module java.sql
```

The comma-separated output can be passed to `--add-modules`:

```bash
jlink --module-path "$JAVA_HOME/jmods" --add-modules java.base,java.logging,java.transaction.xa,java.xml --output sql-runtime
```

This example command creates a runtime image containing the listed modules. In a real project, use the list generated from your own artifact and add the module path containing application dependencies if needed.

Common workflow:

1. Build the application and its modular dependencies.
2. Analyze dependencies with `jdeps` using the proper module path and classpath.
3. Extract the module list with `--print-module-deps`.
4. Audit services, reflection, and dynamically loaded resources.
5. Use `jlink` to build the runtime image.
6. Run tests and smoke tests on the new image to confirm no modules are missing.

The list from static analysis is a good starting point, but it does not replace runtime testing. Service loading, reflection, plugins, or class names constructed from configuration can introduce requirements that bytecode does not fully reveal.

## 19. Limitations of Static Analysis

`jdeps` is very useful, but it cannot know everything that happens at runtime.

Cases that may not be fully detected include:

- Reflection using class or method names constructed from strings.
- `Class.forName` receiving class names from configuration or runtime data.
- `ServiceLoader` and providers discovered via metadata.
- Plugins loaded from external directories or JARs.
- Dynamically generated classes or classes loaded by custom class loaders.
- Dependencies that only appear in configuration files, scripts, or resources.
- Code branches executed only in specific environments.

Therefore, a "no dependencies found" result does not prove an application does not need a library. Combine static analysis with tests, runtime logs, configuration checks, and knowledge of the frameworks in use.

Likewise, a dependency appearing in the report is not necessarily an error. It may be a valid relationship, an intentionally used API, or a dependency required only in a specific environment.

## 20. Common Errors When Using jdeps

| Symptom | Common Cause | Resolution |
|---|---|---|
| `jdeps` is not recognized | JDK not installed or `PATH` is missing the `bin` directory | Check `JAVA_HOME`, `PATH`, and `jdeps --version` |
| Class dependencies not found | Missing libraries on classpath or module path | Add the required dependencies via `--class-path` or `--module-path` |
| Missing dependencies reported | Artifact references classes outside the analysis scope | Use `--missing-deps`, verify dependencies and JAR versions |
| Output is too long | Viewing class-level or recursive dependencies | Use `--summary`, `--verbose:package`, or filter the output |
| Reflection-loaded dependencies not shown | Static analysis cannot resolve dynamically constructed runtime class names | Check configuration, service metadata, and runtime tests |
| JDK internal API warning | Code or library references internal packages | Find public replacement APIs and upgrade dependencies |
| Module cannot be resolved | Module path is missing modules or descriptor is invalid | Use `--module-path`, `--check`, and verify module names |
| Conflicting options | Combining incompatible filters | Check `jdeps --help` and split into separate runs |
| DOT output has no image | `jdeps` only writes DOT files | Use Graphviz or a DOT rendering tool |
| Runtime image missing classes/services | Relying solely on the static dependency list | Audit reflection, service loaders, plugins, and test on the image |

Do not use `--ignore-missing-deps` to suppress warnings without understanding the cause. A missing dependency can cause the application to fail on startup or only when a specific feature is executed.

## 21. Project Dependency Analysis Workflow

A practical workflow can follow this sequence:

1. Identify the JDK and artifact version to analyze.
2. Build the JAR or class directory from the exact commit and configuration.
3. Determine whether dependencies reside on the classpath or module path.
4. Run `jdeps --summary` to get an overview.
5. Use `--verbose:package` or `--verbose:class` to locate the source of specific dependencies.
6. Use `--missing-deps` to check for unresolved references.
7. Use `--jdk-internals` to find dependencies on internal APIs.
8. For modular applications, use `--check` and `--list-deps` to inspect the module graph.
9. Use `--api-only` when evaluating dependencies exposed through the public API.
10. Use `--dot-output` if graphs are needed for documentation or architecture reviews.
11. Use `--print-module-deps` when preparing to build a runtime image.
12. Re-check reflection, service loading, plugins, and runtime configuration.
13. Run tests on the exact target JDK or runtime image.
14. Record the commands, JDK version, and analysis results for reproducibility.

Do not remove a dependency based on a single report line. Verify compile-time relationships, public APIs, and runtime behavior before changing the build configuration.

## 22. Summary

`jdeps` is a JDK tool for static dependency analysis of Java classes, packages, JARs, and modules. It helps understand library structure, find missing dependencies, detect JDK internal API usage, and determine required modules for runtime images.

Key options:

- `jdeps --summary`: view a dependency summary.
- `jdeps --verbose:package`: view package-level dependencies.
- `jdeps --verbose:class`: view class-level dependencies.
- `jdeps --module-path ... --module ...`: analyze modules on the module path.
- `jdeps --list-deps` and `--print-module-deps`: list module dependencies.
- `jdeps --check`: check module descriptors and module graphs.
- `jdeps --jdk-internals`: find references to JDK internal APIs.
- `jdeps --missing-deps`: find missing dependencies.
- `jdeps --api-only`: analyze dependencies in public/protected APIs only.
- `jdeps --dot-output`: export dependency graphs in DOT format.
- `jdeps --generate-module-info`: generate suggested module descriptors for legacy JARs.

Combining `jdeps` with `javac`, `jar`, `jlink`, and runtime testing improves dependency management, prepares for JPMS migration, and reduces risks when upgrading the JDK.

**Official Documentation:**

- [The jdeps Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeps.html)
- [The jlink Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jlink.html)
