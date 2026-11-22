# Analyzing Package Dependencies with jdeps

**jdeps** is Java's dependency analysis tool, shipped with the JDK. It reads class files, class directories, or JARs to identify the classes and packages that an artifact depends on. The results help developers understand which packages use which packages, which libraries require which modules, and which dependencies may cause issues when upgrading or migrating an application to the Java Platform Module System (JPMS).

A common command to view package-level dependencies:

~~~bash
jdeps -verbose:package -filter:none build/classes
~~~

This command analyzes the classes in build/classes and displays source package → target package relationships. The -filter:none option requests displaying internal dependencies within the same archive or package as well; if omitted, some internal relationships are filtered out by default.

jdeps performs static analysis on available bytecode and metadata. It does not run the application, does not measure method call frequency, and cannot detect all dependencies loaded dynamically via reflection, string-based class names, external configuration, or native code.

## 1. What Is a Package Dependency?

A package dependency exists when a class in one package references a class in another package. References can appear in:

- A superclass or implemented interface.
- Field types.
- Method parameter types or return types.
- Declared exception types.
- Object creation, method invocation, or field access instructions.
- Annotations, generic signatures, and other metadata stored in the class file.

Example:

~~~java
package com.example.app;

import com.example.data.Customer;
import com.example.format.NameFormatter;

public class Main {
    public static void main(String[] args) {
        Customer customer = Customer.sample();
        System.out.println(NameFormatter.format(customer.name()));
    }
}
~~~

Class Main in package com.example.app uses type Customer from com.example.data and NameFormatter from com.example.format. Therefore, package com.example.app has dependencies on those two packages.

You can visualize the graph:

~~~text
com.example.app
    |--------------------|
    v                    v
com.example.data    com.example.format
~~~

The arrow indicates that the source package depends on the target package. It does not mean the target package depends back on the source.

Package dependencies help answer architectural questions:

- Which packages are depending on which packages?
- Is an internal package being used from many places?
- Are there circular dependencies between packages?
- Which packages might be affected by changing a given package?
- Which modules or JDK packages does a library require?
- Are any JDK internal APIs being used?

## 2. What Does jdeps Analyze?

jdeps reads compiled class files. It finds references expressed in bytecode and metadata, then groups or filters dependencies at the package, class, archive, or module level.

There are three commonly used levels:

| Level | Option | Content |
|---|---|---|
| Package | -verbose:package | Source package and target package relationships |
| Class | -verbose:class | Source class and target class relationships |
| Summary | -summary | Dependency summary at the archive/module level |

### Package Analysis

~~~bash
jdeps -verbose:package build/classes
~~~

This is the right choice when you want to see the dependency structure between packages. By default, internal dependencies within the same package are usually filtered out so the output focuses on inter-package relationships.

### Class Analysis

~~~bash
jdeps -verbose:class build/classes
~~~

The output is more detailed, showing which class references which class. The class level is useful when you need to trace a specific dependency or find the class causing an unexpected dependency.

The -v or --verbose option is equivalent to class-level analysis with filtering disabled. It can produce significantly larger output.

### Summary

~~~bash
jdeps -summary build/classes
~~~

Summary aggregates dependencies at the archive/module level, giving you an overview before diving into packages or classes.

Do not use summary to conclude which specific package is calling which package; it aggregates information at a higher level.

## 3. Inputs That jdeps Can Analyze

jdeps accepts one or more paths:

- A .class file.
- A directory containing class files.
- A JAR file.
- A modular JAR or a module that can be found on the module path.

Example analyzing a JAR:

~~~bash
jdeps -verbose:package lib/customer-service.jar
~~~

Analyzing an entire output directory:

~~~bash
jdeps -verbose:package build/classes
~~~

Analyzing multiple JARs:

~~~bash
jdeps -summary lib/customer-api.jar lib/customer-impl.jar
~~~

For a class directory, jdeps reads the classes inside and identifies dependencies between them and external packages. For a JAR, it analyzes the archive contents and displays the archive name as the dependency source.

If a dependency is not in the inputs or search paths, jdeps may report that the class or dependency cannot be found. Provide an appropriate classpath/module path for more complete results.

## 4. How to Read Package-Level Output

An output line typically has the structure:

~~~text
source.package -> target.package target-location
~~~

Example:

~~~text
classes -> java.base
   com.example.app    -> com.example.data    classes
   com.example.app    -> com.example.format  classes
   com.example.app    -> java.lang           java.base
   com.example.data   -> java.time           java.base
   com.example.format -> java.util           java.base
~~~

Meaning:

- classes is the input archive or directory being analyzed.
- com.example.app is the source package.
- com.example.data is the target package.
- classes in the last column indicates the target package resides in the same input directory/archive.
- java.base indicates the target package belongs to the java.base module.

A package can depend on multiple other packages. A target package can also be used by multiple source packages.

### Internal and External Dependencies

Internal dependencies are relationships between packages located in the same input archive or directory. External dependencies point to packages in other archives, JARs, or modules.

jdeps's default filter may hide internal dependencies within the same package or archive. Use -filter:none when you need a more complete view.

### Dependencies Are Unidirectional

If the output contains:

~~~text
com.example.app -> com.example.data
~~~

it shows that app references data. You cannot infer that data references app. To check for reverse dependencies, you must look for a separate line or run inverse analysis.

## 5. Hands-On Java 17+ Example: Three Packages

The example consists of three packages:

- com.example.app contains the entry point.
- com.example.data contains the Customer record.
- com.example.format contains name formatting logic.

Source structure:

~~~text
jdeps-demo/
└── src/
    └── com/
        └── example/
            ├── app/
            │   └── Main.java
            ├── data/
            │   └── Customer.java
            └── format/
                └── NameFormatter.java
~~~

### Customer.java

~~~java
package com.example.data;

import java.time.LocalDate;

public record Customer(String name, LocalDate since) {
}
~~~

Customer depends on LocalDate in java.time.

### NameFormatter.java

~~~java
package com.example.format;

import java.util.Locale;

public final class NameFormatter {
    private NameFormatter() {
    }

    public static String format(String name) {
        return name.toUpperCase(Locale.ROOT);
    }
}
~~~

NameFormatter depends on Locale in java.util.

### Main.java

~~~java
package com.example.app;

import com.example.data.Customer;
import com.example.format.NameFormatter;
import java.time.LocalDate;

public final class Main {
    public static void main(String[] args) {
        Customer customer =
                new Customer("Ada", LocalDate.of(2020, 1, 1));

        System.out.println(
                NameFormatter.format(customer.name())
                        + " since " + customer.since());
    }
}
~~~

Main depends on Customer, NameFormatter, and LocalDate.

### Compilation

From the jdeps-demo root directory:

~~~bash
mkdir -p build/classes

javac --release 17 -d build/classes \
    src/com/example/data/Customer.java \
    src/com/example/format/NameFormatter.java \
    src/com/example/app/Main.java
~~~

### Running the Application

~~~bash
java -cp build/classes com.example.app.Main
~~~

Output:

~~~text
ADA since 2020-01-01
~~~

### Analyzing Package Dependencies

~~~bash
jdeps -verbose:package -filter:none build/classes
~~~

On JDK 24, the example output looks like:

~~~text
classes -> java.base
   com.example.app    -> com.example.data    classes
   com.example.app    -> com.example.format  classes
   com.example.app    -> java.io             java.base
   com.example.app    -> java.lang           java.base
   com.example.app    -> java.lang.invoke    java.base
   com.example.app    -> java.time           java.base
   com.example.data   -> java.lang           java.base
   com.example.data   -> java.lang.invoke    java.base
   com.example.data   -> java.lang.runtime   java.base
   com.example.data   -> java.time           java.base
   com.example.format -> java.lang           java.base
   com.example.format -> java.util           java.base
~~~

Some bytecode or output details may vary by compiler/JDK, but the two key application relationships remain:

- com.example.app → com.example.data.
- com.example.app → com.example.format.

Packages such as java.lang, java.time, and java.util belong to the java.base module. Packages like java.lang.invoke may appear due to compiler-generated bytecode, such as string concatenation or record support.

### Summary

~~~bash
jdeps -summary build/classes
~~~

Output observed on JDK 24:

~~~text
classes -> java.base
~~~

Summary shows that the entire class directory depends on java.base. It does not list individual packages; use -verbose:package when you need details.

## 6. Classpath and External Dependencies

If the classes being analyzed reference external libraries, include those libraries on jdeps's classpath.

Example:

~~~bash
jdeps --class-path "lib/customer-api.jar;lib/common.jar" \
    -verbose:package \
    build/classes
~~~

On Windows, the classpath element separator is a semicolon. On Linux/macOS, the separator is a colon:

~~~bash
jdeps --class-path "lib/customer-api.jar:lib/common.jar" \
    -verbose:package \
    build/classes
~~~

If required dependencies are not provided, the output may contain warnings or report missing classes. Do not ignore those warnings when the goal is mapping complete dependencies.

### Specifying Classpath with -cp

The following forms are equivalent:

~~~bash
jdeps -cp lib/common.jar build/classes
jdeps -classpath lib/common.jar build/classes
jdeps --class-path lib/common.jar build/classes
~~~

Prefer the long form --class-path in build scripts so readers can clearly understand the intent.

The classpath specifies where to find classes of non-modular libraries. It does not establish JPMS module relationships and does not replace the module path.

## 7. Analyzing via Module Path

For modular applications, use --module-path to specify where to find modular JARs or exploded modules.

~~~bash
jdeps --module-path mlib \
    --module com.example.app \
    -verbose:package
~~~

Where:

- --module-path mlib specifies where to find modules.
- --module com.example.app selects the root module to analyze.
- -verbose:package displays dependencies at the package level.

You can add additional modules to the root set with --add-modules:

~~~bash
jdeps --module-path mlib \
    --add-modules com.example.app,com.example.provider \
    -verbose:package
~~~

To analyze JDK modules, jdeps can read modules from the current runtime image.

Example analyzing the java.sql module:

~~~bash
jdeps --module java.sql --summary
~~~

To view module dependencies:

~~~bash
jdeps --list-deps --module java.sql
~~~

Output observed on JDK 24:

~~~text
   java.base/jdk.internal.reflect
   java.logging
   java.transaction.xa
   java.xml
~~~

The list shows that the java.sql module depends on the listed modules. A line containing an internal package such as java.base/jdk.internal.reflect is a signal to examine carefully when evaluating APIs or compatibility.

## 8. Module Dependency Analysis Modes

jdeps provides several dedicated modes for the module graph.

### --list-deps

~~~bash
jdeps --list-deps --module java.sql
~~~

Lists module dependencies. If a class references a JDK internal package, the output may also show that internal package.

### --list-reduced-deps

~~~bash
jdeps --list-reduced-deps --module java.sql
~~~

This option removes readability edges already implied by requires transitive. It shows the reduced graph instead of listing every implied edge.

### --print-module-deps

~~~bash
jdeps --print-module-deps --module java.sql
~~~

The output is a comma-separated list of modules:

~~~text
java.base,java.logging,java.transaction.xa,java.xml
~~~

This list can be used as input to jlink --add-modules when creating a custom runtime image, after evaluating the application's module graph and actual dependencies.

### --check

~~~bash
jdeps --check java.sql
~~~

This command analyzes the module descriptor, the analyzed dependencies, and the graph after transition reduction. It can also point out unused qualified exports.

Actual output on JDK 24 begins as follows:

~~~text
java.sql (jrt:/java.sql)
  [Module descriptor]
    requires mandated java.base;
    requires transitive java.logging;
    requires transitive java.transaction.xa;
    requires transitive java.xml;
~~~

This is an example from the JDK module java.sql; your application modules will have their own descriptors and dependencies.

## 9. Direct Dependencies and Transitive Dependencies

When one package uses another package, that is a direct dependency in bytecode detected by jdeps.

Example:

~~~text
app -> service -> repository -> database
~~~

If app references service, service references repository, and repository references database, app has a direct dependency on service and indirect dependencies on the downstream parts if analyzed recursively.

The --recursive or -R option instructs jdeps to traverse runtime dependencies. This option also implies -filter:none, so the output can be much larger.

~~~bash
jdeps --recursive -verbose:package build/classes
~~~

If you only want to see dependencies of the initial inputs without following external dependencies:

~~~bash
jdeps --no-recursive -verbose:package build/classes
~~~

It is important to distinguish:

- **Direct dependency:** an input class/package directly references the target package.
- **Transitive dependency:** appears when continuing to analyze the dependencies of the target package.
- **Module requires transitive:** a JPMS directive that exposes a dependency on a required module; this is a module-level concept and is not identical to every transitive path in the package graph.

Do not call every transitive dependency requires transitive. The two concepts belong to different levels of analysis.

## 10. Filtering Dependencies to Find the Right Issue

jdeps provides filters to help reduce output.

### Filtering by Package

~~~bash
jdeps --package java.time -verbose:package build/classes
~~~

Or:

~~~bash
jdeps -p java.time -verbose:package build/classes
~~~

The package option finds dependencies matching the specified package. Multiple package options can be passed. Use this when you want to focus on a specific package.

### Filtering by Regular Expression

~~~bash
jdeps --regex "java\..*" -verbose:package build/classes
~~~

Regex filters dependencies by pattern, such as packages under java.*. Pay attention to how the shell handles backslashes and quotes on each platform.

### Filtering by Module

~~~bash
jdeps --require java.base -verbose:package build/classes
~~~

The --require option filters dependencies by module name.

The --package, --regex, and --require options are mutually exclusive in a single invocation according to jdeps help. Choose one appropriate filter per command.

### Limiting Analyzed Classes

~~~bash
jdeps -include "com\.example\.app\..*" \
    -verbose:package \
    build/classes
~~~

-include restricts the list of classes to analyze using a regex. Unlike -p and -e, which filter the discovered dependencies, -include selects the source classes included in the analysis.

### Internal Filtering

Common modes:

| Option | Meaning |
|---|---|
| -filter:package | Filter dependencies within the same package; default |
| -filter:archive | Filter dependencies within the same archive |
| -filter:module | Filter dependencies within the same module |
| -filter:none | Do not apply default package/archive filters |

Example:

~~~bash
jdeps -verbose:package -filter:none build/classes
~~~

Use -filter:none when you also need to see relationships between packages in the same archive. When the output is too large, revert to the default filter or restrict the input with -include.

## 11. Inverse Dependency Analysis

Normally, jdeps shows which source packages or classes depend on which target packages or classes.

Sometimes the question to answer is: which packages are using this package?

You can use --inverse combined with a package, regex, or module filter:

~~~bash
jdeps --inverse --package java.sql \
    --recursive \
    build/classes
~~~

This command finds artifacts that directly or indirectly depend on dependencies matching package java.sql, within the selected analysis scope.

Another example:

~~~bash
jdeps --inverse --require java.sql \
    --recursive \
    mlib
~~~

Inverse analysis is useful when:

- Preparing to replace a library.
- Assessing the impact of removing a package.
- Finding modules or archives that depend on an API.
- Investigating why a dependency is still being pulled in at runtime.

--inverse must be used with --require, --package, or --regex. Do not use it as an arbitrary graph-inversion command without a search criterion.

## 12. Generating Dependency Diagrams with DOT

You can export graphs to view with Graphviz or DOT-compatible tools.

~~~bash
jdeps --dot-output build/dependency-graphs \
    -verbose:package \
    build/classes
~~~

jdeps creates DOT files in the specified directory. File names and counts depend on the inputs; typically there is a summary graph and a graph for each archive.

A conceptual DOT snippet:

~~~dot
digraph "classes" {
    "com.example.app" -> "com.example.data";
    "com.example.app" -> "com.example.format";
    "com.example.data" -> "java.time";
    "com.example.format" -> "java.util";
}
~~~

This is a structural illustration, not the exact fixed DOT file content emitted by jdeps. Actual graphs may contain archive/module, package, or class nodes depending on the mode and inputs.

You can render DOT files into images using Graphviz:

~~~bash
dot -Tpng build/dependency-graphs/classes.dot \
    -o build/dependency-graphs/classes.png
~~~

If the actual DOT filename differs from classes.dot, use the exact filename in the output directory. For large graphs, filter packages or classes before exporting to keep the diagram readable.

Diagrams help reveal:

- Packages with too many outgoing dependencies.
- Packages depended on by many components.
- Circular dependencies.
- Unclear package boundaries.
- Internal packages being used across multiple modules.

jdeps detects and displays relationships; deciding how to refactor still requires evaluating the application's design.

## 13. Finding Missing Dependencies

Use --missing-deps to find dependencies that jdeps cannot resolve:

~~~bash
jdeps --missing-deps build/classes
~~~

If you need to ignore missing dependencies during an analysis run, you can use:

~~~bash
jdeps --ignore-missing-deps -verbose:package build/classes
~~~

Do not use --ignore-missing-deps to hide build errors or conclude that dependencies are complete. Record which classes were not found and add the proper JAR/module path if needed.

A missing dependency may occur because:

- The JAR is not on the classpath.
- The module is not on the module path.
- The dependency version does not contain the referenced class.
- The artifact was packaged with missing classes.
- Only part of a source tree is being analyzed without the remaining modules.

When the goal is an audit or migration, keep warnings and resolve the root cause rather than ignoring them.

## 14. Finding JDK Internal API Usage

The JDK contains internal packages that are not public APIs with compatibility guarantees. Applications using classes such as sun.* or jdk.internal.* may break when upgrading the JDK.

jdeps supports:

~~~bash
jdeps --jdk-internals build/classes
~~~

This option finds class-level dependencies on JDK internal APIs. For example, the output may state the referenced internal class and the module containing it.

When a dependency is found:

1. Identify the internal API being used.
2. Find a public replacement API in Java SE or a supported API.
3. Replace the implementation.
4. Compile and run tests on the target JDK.
5. Re-run jdeps --jdk-internals to verify.

According to jdeps help, --jdk-internals cannot be used with -p, -e, and -s. Run this audit command separately.

Do not rely on --add-exports as a long-term solution for an application using internal APIs. That option can open a package in a given runtime configuration, but it does not turn an internal API into a stable API.

## 15. Analyzing Only Dependencies in the Public API

A library may use many packages in its implementation, but only a subset of them appears in its public/protected API.

The --api-only option restricts analysis to dependencies appearing in the signatures of public/protected members of public classes. This includes field types, method parameters, return types, and checked exceptions.

~~~bash
jdeps --api-only -verbose:package build/classes
~~~

Compare with a full analysis:

~~~bash
jdeps -verbose:package build/classes
~~~

If a package is only called inside a method body, that dependency may appear in the full analysis but not in API-only.

API-only is useful when:

- Evaluating dependencies that library consumers need to read.
- Designing module descriptors.
- Determining whether a dependency becomes part of the public contract.
- Analyzing the feasibility of changing an implementation without affecting the API.

It does not replace binary compatibility checks. An API can change in a way that breaks compatibility even if the package dependency graph does not change.

## 16. Package Dependencies and Module Dependencies

Packages and modules are two different levels of organization:

- A package groups classes sharing a namespace.
- A module groups packages and declares dependencies, exports, opens, and services.
- A module can contain multiple packages.
- A package in a named module is not exported automatically.

For example, module com.example.app may contain:

~~~text
com.example.app
├── com.example.app
├── com.example.app.cli
└── com.example.app.internal
~~~

The module descriptor declares:

~~~java
module com.example.app {
    requires com.example.data;
    exports com.example.app;
}
~~~

jdeps package analysis shows which packages reference which packages. Module analysis shows which modules require which modules. A single module dependency can arise from many underlying package dependencies.

Do not infer that a referenced package is properly exported. In JPMS, readability and exports must still be satisfied at compile/run time.

## 17. Supporting Library Migration to JPMS

Legacy libraries may not yet have a module-info.class. jdeps helps survey dependencies before adding a descriptor.

You can ask jdeps to generate a suggested module descriptor:

~~~bash
jdeps --generate-module-info build/module-info \
    lib/legacy-library.jar
~~~

For libraries requiring an open module:

~~~bash
jdeps --generate-open-module build/module-info \
    lib/legacy-library.jar
~~~

The tool generates module-info.java under the specified directory based on the dependencies it can analyze.

This is a starting point for migration, not a finished descriptor guaranteed to be architecturally sound. After generation, review:

- Whether the module name is stable and follows conventions.
- Whether requires includes any unnecessary dependencies.
- Whether requires transitive is truly needed for the public API.
- Which packages should be exported.
- Whether any packages need opens for framework reflection.
- Whether uses/provides declarations are needed.
- Whether any dynamic dependencies were missed.
- Whether the descriptor compiles and runs on the target JDK.

--generate-module-info and --generate-open-module analyze the specified JAR. According to the tool's help, these options cannot be combined with --dot-output or --class-path in the same invocation. Check jdeps --help for the JDK you are using.

## 18. Multi-Release JARs and Version Selection

A multi-release JAR can contain multiple class versions per Java release. When analyzing, select the appropriate view.

~~~bash
jdeps --multi-release base -verbose:package lib/library.jar
~~~

Or select a specific release:

~~~bash
jdeps --multi-release 17 -verbose:package lib/library.jar
~~~

--multi-release accepts base or an integer of 9 or greater. This analyzes the actual classes that a given runtime release will see in the MR-JAR.

If the right release is not selected, the reported dependencies may not reflect the implementation used by the target runtime.

## 19. Integrating jdeps into Build and CI Workflows

jdeps is useful as an audit step after compilation or packaging.

A simple pipeline:

1. Compile sources into class files.
2. Run unit tests.
3. Run jdeps -verbose:package to inspect package dependencies.
4. Run jdeps --missing-deps to find unresolved classes.
5. Run jdeps --jdk-internals to find internal APIs.
6. For modular apps, run --list-deps or --print-module-deps.
7. Save DOT graphs as artifacts if architectural review is needed.
8. Compare results against the project's dependency baseline.

Example commands:

~~~bash
jdeps -verbose:package -filter:none build/classes

jdeps --missing-deps build/classes

jdeps --jdk-internals build/classes

jdeps --print-module-deps --module-path mlib \
    --module com.example.app
~~~

If integrated into CI, you can save the output to compare across builds. jdeps does not enforce your project's architectural policies on its own; the pipeline needs its own rules to decide which package dependencies are allowed.

For example, a domain module might be forbidden from depending on web or persistence packages. You can use jdeps output and a check script to detect when a dependency edge violates the rules.

Do not treat every new dependency as an error. Evaluate dependencies against architecture, API, and operational requirements before blocking a build.

## 20. Limitations of Static Analysis

jdeps analyzes references present in bytecode. Some dependencies may not appear in the results:

- Classes loaded via Class.forName with class names read from configuration.
- Reflection based on method/field names.
- Service providers selected from configuration files or the runtime environment.
- Classes generated or loaded via a custom class loader.
- Native code calling into Java or vice versa.
- Dependencies produced by code generation after the analysis step.
- Resources or scripts containing class names not directly referenced by bytecode.

Therefore, jdeps output is a static dependency map, not absolute proof of every class that will be used at runtime.

To increase confidence, combine:

- Source and module descriptor analysis.
- Framework configuration checks.
- Integration tests in the deployment environment.
- Runtime tracing or logging when needed.
- Service loader and reflection configuration reviews.
- Inspecting the final JAR contents rather than only the source tree.

## 21. Common Errors

**Class or dependency not found**

Add the proper classpath/module path. Verify that the JAR contains the class and that the dependency version is compatible.

**Output too large**

Switch from -verbose:class to -verbose:package or -summary. Use -include, -p, or -e to narrow the scope.

**Internal dependencies not shown**

The default filter may hide relationships within the same package/archive. Try -filter:none.

**Confusing package dependencies with module dependencies**

Package dependencies show relationships between packages. Module dependencies show relationships between modules. Use the right analysis mode for the question you need to answer.

**Reflection dependencies do not appear**

jdeps cannot fully infer class names constructed from strings or configuration. Check framework and runtime configuration.

**Unsure why java.base appears multiple times**

java.base contains many foundational packages such as java.lang, java.io, java.time, and java.util. Packages in this module can be referenced from many application packages.

**--jdk-internals does not run with filters**

This option cannot be combined with -p, -e, and -s according to jdeps help. Run the internal API audit separately.

**--print-module-deps does not show packages**

This is module-level output, not package-level. Use -verbose:package if you need inter-package dependencies.

**DOT graph does not render an image properly**

Check the actual .dot file path and Graphviz syntax. jdeps generates DOT; Graphviz or an equivalent tool is responsible for rendering the image.

## 22. Package Dependency Analysis Workflow

1. Build class files or identify the JARs to analyze.
2. Provide the complete classpath/module path for external dependencies.
3. Run -verbose:package to inspect package-level dependencies.
4. Use -filter:none if you also need internal relationships.
5. Use -verbose:class when you need to trace specific classes.
6. Use -summary to get an archive/module-level overview.
7. Use --recursive when you need to analyze transitive dependencies.
8. Use --inverse when you want to find artifacts depending on a target package/module.
9. Use --missing-deps and --jdk-internals for auditing.
10. Use --api-only to analyze dependencies in the public API.
11. Use --dot-output when you need graph visualization.
12. For modular apps, check --list-deps, --check, and --print-module-deps.
13. Cross-check results against the intended architecture and test at runtime.

jdeps turns bytecode references into a readable, analyzable dependency map. When you choose the right package, class, or module level, provide complete dependency paths, and understand the limits of static analysis, developers can use this tool to inspect architecture, prepare for JPMS migration, and reduce risk when changing libraries.

## References

- [The jdeps Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeps.html)
- [Java Platform Module System — JEP 261](https://openjdk.org/jeps/261)
- [jdeps tool documentation — Oracle Java Platform](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeps.html)
