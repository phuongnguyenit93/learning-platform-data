# Dependency Summary with jdeps

**jdeps** is a static dependency analysis tool included with the JDK. The tool reads class files, class directories, or JARs to determine which packages, classes, and modules Java code references. The **summary** mode aggregates dependency relationships into a concise report, giving a quick overview of which libraries or modules depend on which components.

Dependency summaries are useful when auditing libraries before an upgrade, determining the impact scope of a module, preparing a runtime image with jlink, and detecting unexpected dependencies. jdeps only analyzes bytecode and metadata; it does not run the application and does not modify dependencies automatically.

## 1. jdeps and Dependency Summary

A dependency is a relationship in which the code of one component references types or packages provided by another component. For example, a class in com.example.app might call java.sql.Connection, so the application has a dependency on the java.sql package.

jdeps can analyze at multiple levels:

- **Archive/module level:** summarizes relationships between JARs, archive directories, or modules.
- **Package level:** lists source packages depending on target packages.
- **Class level:** lists source classes referencing target classes.
- **Module graph:** analyzes requires relationships between named modules.

Depending on the input and options, a report may use JAR names, packages, or modules as the two ends of a relationship.

### When to Use Summary?

Use summary when you need quick answers to:

- Which archives or modules does this JAR or module depend on?
- Which JDK modules does a library pull in?
- After changing a dependency, has the overall dependency graph changed?
- Which modules need to be included in a custom runtime image?
- Should a dependency be investigated further before upgrading or removing it?

If you need to know the exact class or package creating the relationship, switch to verbose mode or package-level analysis.

## 2. Syntax and Summary Options

General syntax:

~~~bash
jdeps [options] <path ...>
~~~

path can be a path to a class file, a directory containing class files, or a JAR. For module analysis, you can specify a module using --module.

Two ways to enable summary:

~~~bash
jdeps -s app.jar
jdeps --summary app.jar
~~~

-s is the short form of --summary. This option instructs jdeps to print only the dependency summary instead of per-class details.

Some options commonly used with summary:

| Option | Meaning |
|---|---|
| -s, --summary | Print dependency summary only |
| --class-path, -cp | Specify where to find non-modular classes and libraries |
| --module-path | Specify the module path |
| --module, -m | Specify the root module to analyze |
| --system | Use the system module path of another JDK |
| --add-modules | Add modules to the root set during analysis |
| --recursive, -R | Recursively analyze runtime dependencies |
| --no-recursive | Do not traverse further through dependencies |
| --dot-output | Write the dependency graph in DOT format |
| --multi-release | Select the version when analyzing a multi-release JAR |

Check the toolchain version and syntax:

~~~bash
jdeps --version
jdeps --help
~~~

Options may vary across JDK versions. Use jdeps --help from the exact JDK in your build pipeline to verify before adding commands to CI.

## 3. Reading Summary Output

For the JDK module java.sql, run:

~~~bash
jdeps -s --module java.sql
~~~

On OpenJDK 24.0.2, the verified output is:

~~~text
java.sql -> java.base
java.sql -> java.logging
java.sql -> java.transaction.xa
java.sql -> java.xml
~~~

How to read it:

- java.sql is the module being analyzed.
- The -> arrow indicates a dependency relationship.
- The name on the right is the module referenced by java.sql.
- Each line is an aggregated dependency relationship.

Results may differ between JDK versions because module descriptors or implementations can change. When comparing reports across two machines, record the JDK vendor and version.

### Summary Is Not a Class List

The report above does not state which specific class in java.sql references java.xml. It only shows relationships at the module level. To trace the source of a dependency, use -verbose:package or -verbose:class.

## 4. Analyzing a JAR or Application Directory

For non-modular applications, you can pass the JAR directly:

~~~bash
jdeps --summary build/app.jar
~~~

If the application uses external libraries, add the class path:

~~~bash
jdeps --summary --class-path "lib/*" build/app.jar
~~~

On Windows PowerShell, wildcards in the class path can also be enclosed in quotes:

~~~powershell
jdeps --summary --class-path "lib/*" build/app.jar
~~~

If libraries reside outside the lib directory, include their paths in the class path using the operating system's path separator syntax. On Linux/macOS, the separator is typically :; on Windows, it is ;.

You can analyze a compiled classes directory:

~~~bash
jdeps --summary build/classes
~~~

This is useful when you want to analyze compiler output before packaging it into a JAR.

### Why Is the Right Class Path Necessary?

If jdeps cannot find a referenced class, the output may contain warnings or unresolved dependencies. A report missing libraries on the class path can result in an incomplete dependency summary.

When analyzing a JAR, provide the dependencies that the JAR needs to resolve types. Do not arbitrarily add every library on your machine, as that can cause the report to include dependencies that are not part of the actual build.

## 5. Summary for Named Modules

For modular applications, provide the module path and module name:

~~~bash
jdeps --summary --module-path "$JAVA_HOME/jmods:mods" --module com.example.app
~~~

In the example above:

- JAVA_HOME/jmods contains the JMODs of the JDK in use.
- mods contains the application's exploded modules or modular JARs.
- --module com.example.app selects the module to analyze.
- --summary aggregates the results into module relationships.

On Windows PowerShell, the module path separator is a semicolon:

~~~powershell
jdeps --summary --module-path "$env:JAVA_HOME\jmods;mods" --module com.example.app
~~~

Using the correct module path is critical. If a module is not found, check the name in module-info.java, the artifact location, and the corresponding JDK. The JAR file name does not necessarily match the module name.

## 6. Distinguishing Module Reporting Modes

jdeps has several related module-level modes that are not identical.

### --summary

~~~bash
jdeps -s --module java.sql
~~~

Summarizes source → target relationships. This is the appropriate mode for viewing high-level dependencies.

### --list-deps

~~~bash
jdeps --list-deps --module java.sql
~~~

Lists resolved module dependencies. Depending on the input, the output may also display packages belonging to JDK internal APIs if the code references them.

For example, with OpenJDK 24.0.2, --list-deps --module java.sql displays:

~~~text
   java.base/jdk.internal.reflect
   java.logging
   java.transaction.xa
   java.xml
~~~

The line java.base/jdk.internal.reflect is a referenced internal package and should not be mistaken for a standalone module name.

### --list-reduced-deps

~~~bash
jdeps --list-reduced-deps --module java.sql
~~~

Lists dependencies after removing readability edges inferred from requires transitive in the module graph. This view helps focus on relationships that need to be declared directly after graph reduction.

### --print-module-deps

~~~bash
jdeps --print-module-deps --module java.sql
~~~

Prints a comma-separated list of modules. With OpenJDK 24.0.2, the verified output is:

~~~text
java.base,java.logging,java.transaction.xa,java.xml
~~~

This list can be used as input to jlink --add-modules to create a runtime image containing the required modules and their corresponding transitive dependencies.

### --check

~~~bash
jdeps --check java.sql
~~~

Analyzes the module descriptor, resolved dependencies, and the reduced graph. Depending on the module, the output also points out unused qualified exports.

In summary:

| Mode | Purpose |
|---|---|
| --summary | Dependency relationships in summary form |
| --list-deps | List of module dependencies |
| --list-reduced-deps | List of dependencies after removing inferred edges |
| --print-module-deps | Comma-separated module list for use with jlink |
| --check | Inspect module descriptor and module graph |

Do not treat these modes as having the same output or the same purpose. Choose based on the question you need to answer.

## 7. From Summary to Detailed Analysis

Summary shows that a dependency relationship exists, but it is often not enough to decide which code to change. You can increase the level of detail step by step.

### Package-level

~~~bash
jdeps -verbose:package app.jar
~~~

This command displays relationships between source and target packages. By default, dependencies within the same package are filtered out of the output.

### Class-level

~~~bash
jdeps -verbose:class app.jar
~~~

Displays relationships between classes. This mode is useful when you need to find which specific class references a library.

### All Class Dependencies

~~~bash
jdeps -verbose app.jar
~~~

-verbose is equivalent to -verbose:class -filter:none, so it can produce large output. Use it only when deep investigation is needed.

### Filtering by Package or Module

Find only dependencies matching a package:

~~~bash
jdeps --package java.sql app.jar
~~~

Find only dependencies on a module:

~~~bash
jdeps --require java.sql app.jar
~~~

Filter using a regular expression:

~~~bash
jdeps --regex "javax\\..*" app.jar
~~~

--package, --require, and --regex are mutually exclusive filters; choose one filter type per run. Use --include if you want to restrict the set of source classes analyzed.

## 8. Recursion and Dependency Filters

By default, jdeps may filter internal dependencies within the same package. Useful filters include:

| Option | Meaning |
|---|---|
| -filter:package | Filter dependencies within the same package; this is the default |
| -filter:archive | Filter dependencies within the same archive |
| -filter:module | Filter dependencies within the same module |
| -filter:none | Do not apply default package/archive filters |
| -R, --recursive | Recursively traverse runtime dependencies; implies -filter:none |
| --no-recursive | Do not traverse further through dependencies |

Recursive analysis example:

~~~bash
jdeps -R --summary --class-path "lib/*" build/app.jar
~~~

Use recursion when you want to see transitive dependencies referenced through other libraries as well. The output can be much larger than direct analysis.

If you need to know the direct dependencies of the application itself, use --no-recursive or omit -R, then compare with the recursive report to determine which dependencies come from dependent libraries.

### Inverse Analysis

--inverse finds artifacts that directly or indirectly depend on the selected node. This option must be paired with a criterion such as --require, --package, or --regex.

Example of finding artifacts that depend on a package:

~~~bash
jdeps --inverse --package java.sql --class-path "lib/*" build/app.jar
~~~

Inverse analysis is useful when evaluating the impact of replacing or removing a package or library.

## 9. Finding Missing Dependencies and JDK Internal APIs

### Unresolved Dependencies

Use:

~~~bash
jdeps --missing-deps --class-path "lib/*" build/app.jar
~~~

This option finds dependencies that jdeps cannot resolve within the provided inputs and paths. It is especially useful when inspecting third-party JARs or when dependencies are missing from build packaging.

--missing-deps cannot be combined with -p/--package, -e/--regex, or -s/--summary. Run it as a separate analysis step.

You can use --ignore-missing-deps to ignore unresolved dependencies in some analysis workflows, but doing so does not make the library magically appear at runtime. Only ignore them when you understand and accept that the dependency is provided by other means.

### JDK Internal APIs

Use:

~~~bash
jdeps --jdk-internals app.jar
~~~

This option finds class-level dependencies on JDK internal APIs. Internal APIs are not part of the public compatibility contract; the application may break when upgrading the JDK or when access to those APIs is encapsulated.

--jdk-internals cannot be combined with -p, -e, or -s. Therefore, run it separately when checking for internal APIs instead of trying to combine it into a summary command.

When internal dependencies are detected, prefer replacing them with supported Java SE APIs. Do not treat --add-exports or --add-opens as a long-term solution for libraries depending on internal APIs.

## 10. Generating Dependency Graphs

You can instruct jdeps to output DOT files:

~~~bash
jdeps --dot-output build/dependency-graphs app.jar
~~~

DOT is a graph description format that can be used with Graphviz to generate images. Output typically includes an overall summary graph file and per-archive/module files depending on the input.

You can convert a DOT file into an image using Graphviz:

~~~bash
dot -Tpng build/dependency-graphs/summary.dot -o build/dependency-graphs/summary.png
~~~

Specific DOT file names depend on the input and tool version; check the output directory after running jdeps. Visual graphs are helpful for multi-module projects, whereas for a small application, text-based summaries are usually easier to read.

## 11. Combining Dependency Summary with jlink

A modular application needs a runtime image containing the application modules and their dependent modules. --print-module-deps can generate the module list to pass to jlink.

Example workflow:

~~~bash
jdeps --print-module-deps \
  --module-path "$JAVA_HOME/jmods:mods" \
  --module com.example.app
~~~

Assuming the output is a comma-separated list of modules, use that list in:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app,java.sql,java.logging \
  --output runtime
~~~

The module list in the jlink command above only illustrates the syntax. In a real build, replace it with the actual analyzed and tested module output. Do not use the arrow-formatted --summary output as the value for --add-modules; use --print-module-deps instead.

After creating the runtime image, verify which modules were included:

~~~bash
runtime/bin/java --list-modules
~~~

On Windows, use runtime\bin\java.exe --list-modules.

jdeps helps identify static dependencies; the application still needs to be smoke-tested on the runtime image because dynamically loaded components may not appear in the report.

## 12. Multi-Release JARs and Alternative JDKs

For multi-release JARs, you can select the version to analyze:

~~~bash
jdeps --multi-release 17 --summary library.jar
~~~

The value can be an integer from 9 upwards or base. Choose the version matching your target runtime; results may differ if the JAR contains separate implementations for different Java releases.

You can select the system module path of another JDK:

~~~powershell
jdeps --system "C:\Java\jdk-21" --summary app.jar
~~~

The --system option allows analyzing against the system modules of the specified JDK. Use the same JDK release as your deployment environment to reduce discrepancies when evaluating module dependencies.

## 13. Limitations of jdeps

jdeps analyzes static dependencies from class files and module metadata. As a result, certain dependencies may not appear in the summary:

- Classes loaded via reflection with class names obtained from configuration or runtime strings.
- Plugins or providers discovered through custom mechanisms.
- Class names concatenated dynamically and passed to a class loader.
- Native libraries and dependencies outside the JVM.
- Configuration files, scripts, or resources containing class/module names read by the program at runtime.

For example, if an application calls Class.forName(configuredClassName), jdeps may not know what value configuredClassName will hold at runtime. Supplement dynamic dependency information in build configurations, integration tests, and by testing the runtime image in an environment close to production.

jdeps also does not prove that a dependency is required for business logic; it only reports relationships found in the analyzed data.

## 14. Common Errors

### Warning: Path does not exist

The JAR, directory, or class path is incorrect. Check the current working directory, file names, and relative/absolute paths.

### Class not found

A dependency is missing from --class-path or the module path. Add the required JAR/module and run again. Do not confuse the class path with the module path.

### Module not found

The module name or artifact location is incorrect. Use jar --describe-module to view the module name of a modular JAR and check --module-path.

### Summary Missing Transitive Dependencies

-R may not be enabled, or the dependency is provided through another library. Compare direct analysis with --recursive/--list-deps and check the class path.

### Output Too Large

-verbose, -filter:none, or -R is being used. Fall back to --summary, use --no-recursive, or filter with --package, --require, --regex, and --include.

### Dependency Does Not Appear Even Though the Application Loads the Class at Runtime

The class may be loaded via reflection or plugin discovery. Supplement dynamic dependencies from configuration and verify at runtime with integration tests.

### Cannot Combine --missing-deps with --summary

This is an option restriction enforced by jdeps. Run two separate commands: one for summary and one for --missing-deps.

### Cannot Combine --jdk-internals with --summary

--jdk-internals is incompatible with -s. Run jdeps --jdk-internals separately to find references to internal APIs.

## 15. Recommended Dependency Analysis Workflow

1. Run jdeps --summary on the JAR or module to get an overall picture.
2. Provide the correct --class-path or --module-path so dependencies can be resolved.
3. Use --list-deps or --print-module-deps if a list of modules is needed.
4. Use -verbose:package or -verbose:class to locate the source of a specific dependency.
5. Run --missing-deps to find unresolved dependencies.
6. Run --jdk-internals separately to detect internal APIs.
7. Use --recursive when evaluating transitive dependencies.
8. Generate a DOT graph if the module graph is too large to read in text form.
9. Use --print-module-deps as input for jlink when creating a runtime image.
10. Test the application on the runtime image because reflection and dynamic dependencies may fall outside static analysis results.

## 16. Key Terms to Remember

| Term | Meaning |
|---|---|
| jdeps | Static dependency analysis tool in the JDK |
| Dependency summary | Summary report of dependency relationships |
| -s, --summary | Print dependency summary only |
| Class path | Location to find non-modular classes and libraries |
| Module path | Location to find named modules |
| Direct dependency | Dependency referenced directly by the analyzed component |
| Transitive dependency | Dependency appearing through another dependency |
| --list-deps | List module dependencies |
| --print-module-deps | Print module list suitable for passing to jlink |
| --missing-deps | Find unresolved dependencies |
| JDK internal API | Internal API not part of the public compatibility contract |
| DOT | Text format describing a graph |
| Multi-release JAR | JAR containing content targeting multiple Java releases |

Dependency summary helps you quickly understand the dependency structure of JARs and modules. Use --summary for an overview, switch to package/class reports when tracing root causes, and use --print-module-deps when preparing a runtime image with jlink.

## References

- Oracle JDK 24 — The jdeps Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeps.html
- Oracle — Java Dependency Analysis Tool: https://docs.oracle.com/javase/8/docs/technotes/tools/unix/jdeps.html
- OpenJDK — jdeps source and tool documentation: https://github.com/openjdk/jdk/tree/master/src/jdk.jdeps