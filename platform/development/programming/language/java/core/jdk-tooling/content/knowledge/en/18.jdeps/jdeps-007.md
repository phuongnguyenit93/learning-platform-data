# Recursive Analysis with jdeps

**jdeps** is a static dependency analysis tool included with the JDK. It reads class files, class directories, or JARs to determine the packages, classes, and modules that a Java component references. **Recursive analysis** mode extends the analysis from direct dependencies to dependencies at subsequent levels, helping reveal the dependency graph needed to understand an application's structure.

For example, application A calls library B, B uses library C, and C depends on module D. Direct analysis only shows that A needs B. Recursive analysis continues from B to C and from C to D, helping developers see transitive dependencies that can affect packaging, upgrades, security, or module migration.

In jdeps, the **-R** or **--recursive** option instructs the tool to recursively traverse runtime dependencies. This option also implicitly enables **-filter:none**, so the output can be significantly larger than the default analysis.

## 1. Direct Dependencies and Transitive Dependencies

A direct dependency occurs when the bytecode of a class in the application references another class or package.

For example:

- Main calls CustomerService.
- CustomerService creates Customer.
- Customer uses String from java.base.

Dependency graph:

~~~text
app.jar
  |
  v
service.jar
  |
  v
model.jar
  |
  v
java.base
~~~

If you only analyze app.jar without requesting recursive traversal, jdeps focuses on the direct dependencies referenced by the bytecode of app.jar. When using -R, jdeps continues analyzing dependency archives found on the classpath/module path and expands the graph.

Distinction:

| Dependency type | Meaning | Example |
|---|---|---|
| Direct dependency | Directly referenced by the input component | app.jar uses service.jar |
| Transitive dependency | A dependency used by another dependency | service.jar uses model.jar |
| JDK dependency | A dependency on a JDK module/package | Class uses java.base or java.sql |
| Missing dependency | A referenced class that cannot be resolved in the analysis environment | Missing a library on the classpath |

Transitive dependencies can still affect the application: changing their version can cause conflicts, missing classes, or runtime behavior changes.

## 2. Recursive Analysis Syntax

General syntax:

~~~bash
jdeps --recursive [options] path...
~~~

Short form:

~~~bash
jdeps -R [options] path...
~~~

`path` can be:

- A `.class` file.
- A directory containing class files.
- A JAR.
- A fully qualified class name to analyze the corresponding class file.

Simple example:

~~~bash
jdeps -R app.jar
~~~

Recursive analysis with package-level output:

~~~bash
jdeps -R -verbose:package app.jar
~~~

Recursive analysis at the class level:

~~~bash
jdeps -R -verbose:class app.jar
~~~

Dependency summary:

~~~bash
jdeps -R -summary app.jar
~~~

The `-R` and `--recursive` options are equivalent. Use the long form in new scripts for clarity; the short form commonly appears in documentation and existing commands.

## 3. How Does -R Change the Analysis Scope?

According to the JDK manual, `-R` recursively traverses runtime dependencies and implicitly applies `-filter:none`. By default, jdeps filters out certain intra-package dependencies; verbose modes also have their own default filters. When recursive mode is enabled, the tool displays dependency edges that default filters might hide.

| Configuration | Scope |
|---|---|
| jdeps app.jar | Analyzes direct dependencies in default mode |
| jdeps -R app.jar | Traverses runtime dependencies at subsequent levels |
| jdeps --no-recursive app.jar | Does not recursively traverse dependencies |
| jdeps -R -filter:none app.jar | Recursively traverses and shows unfiltered dependencies |
| jdeps -R -filter:archive app.jar | Recursively traverses but filters dependencies within the same archive according to the filter option |

Because `-R` already implicitly enables `-filter:none`, there is no need to add `-filter:none` in ordinary commands. You can use a different filter when you want to limit output; the specified filter option still takes effect.

Recursive results can contain many more lines, including intra-archive dependencies, intra-package dependencies, and dependencies from resolved libraries. When the output is too large, choose package mode, summary mode, or filter by the package/class under investigation.

## 4. Recursive Analysis Requires a Proper Classpath or Module Path

Recursive analysis can only proceed when jdeps finds dependencies to analyze. The `-R` option does not download libraries from Maven Central, guess versions, or replace build tool dependency configuration.

### Classpath-based applications

Use **--class-path** to specify JARs or class directories to resolve:

~~~bash
jdeps -R --class-path "lib/service.jar:lib/model.jar" app.jar
~~~

On Windows, use a semicolon as the path separator:

~~~powershell
jdeps -R --class-path "lib\service.jar;lib\model.jar" app.jar
~~~

If there are multiple dependencies, list all required libraries. You can specify directories containing compiled classes alongside JARs.

### Modular applications

Use **--module-path** to specify where named modules or automatic modules are located:

~~~bash
jdeps -R --module-path mods --module com.acme.app
~~~

You can specify additional root modules with `--add-modules` when the analysis requires a specific set of modules:

~~~bash
jdeps -R --module-path mods --add-modules com.acme.app,com.acme.reporting
~~~

With the module system, check the module name in `module-info.class` or the JAR's automatic module name. The JAR filename does not necessarily match the module name.

### Other paths

jdeps also supports:

- **--upgrade-module-path**: specifies the upgrade module path.
- **--system**: selects the system module path of a different Java home.
- **--multi-release**: selects the entry version when analyzing a multi-release JAR.

These options are useful when analyzing artifacts built for a specific runtime or Java release.

## 5. Complete Example: An App Depending Across Multiple JAR Layers

Create a small project with three JARs:

~~~text
project/
  src/
    model/com/acme/model/Customer.java
    service/com/acme/service/CustomerService.java
    app/com/acme/app/Main.java
  lib/
  build/
~~~

### The model JAR

File `src/model/com/acme/model/Customer.java`:

~~~java
package com.acme.model;

public record Customer(String name) {
}
~~~

Compile and package:

~~~bash
javac --release 17 -d build/model src/model/com/acme/model/Customer.java
jar --create --file lib/model.jar -C build/model .
~~~

### The service JAR

File `src/service/com/acme/service/CustomerService.java`:

~~~java
package com.acme.service;

import com.acme.model.Customer;

public class CustomerService {
    public Customer load() {
        return new Customer("Ada Lovelace");
    }
}
~~~

Compile with `model.jar` on the classpath:

~~~bash
javac --release 17 --class-path lib/model.jar -d build/service src/service/com/acme/service/CustomerService.java
jar --create --file lib/service.jar -C build/service .
~~~

### The app JAR

File `src/app/com/acme/app/Main.java`:

~~~java
package com.acme.app;

import com.acme.service.CustomerService;

public class Main {
    public static void main(String[] args) {
        var customer = new CustomerService().load();
        System.out.println(customer.name());
    }
}
~~~

Compile `app` with `service.jar` and `model.jar`:

Linux/macOS:

~~~bash
javac --release 17 --class-path "lib/service.jar:lib/model.jar" -d build/app src/app/com/acme/app/Main.java
~~~

Windows PowerShell:

~~~powershell
javac --release 17 --class-path "lib\service.jar;lib\model.jar" -d build\app src\app\com\acme\app\Main.java
~~~

Package `app`:

~~~bash
jar --create --file lib/app.jar -C build/app .
~~~

Run the application to confirm the dependencies work:

Linux/macOS:

~~~bash
java --class-path "lib/app.jar:lib/service.jar:lib/model.jar" com.acme.app.Main
~~~

Windows PowerShell:

~~~powershell
java --class-path "lib\app.jar;lib\service.jar;lib\model.jar" com.acme.app.Main
~~~

Stdout:

~~~text
Ada Lovelace
~~~

### Direct vs. recursive analysis

Analyze `app.jar`:

~~~bash
jdeps --verbose:package --class-path "lib/service.jar:lib/model.jar" lib/app.jar
~~~

Recursive analysis:

~~~bash
jdeps -R --verbose:package --class-path "lib/service.jar:lib/model.jar" lib/app.jar
~~~

The second command starts from `app.jar`, then analyzes `service.jar` and `model.jar` as these dependencies are resolved. The output may show edges such as:

~~~text
app.jar -> service.jar
service.jar -> model.jar
app.jar -> java.base
service.jar -> java.base
model.jar -> java.base
~~~

This is an illustrative archive relationship diagram, not fixed verbatim output. Actual output depends on the JDK, verbose mode, analyzed classes, library paths, and dependencies generated by the compiler.

Detailed class-level analysis:

~~~bash
jdeps -R --verbose:class --class-path "lib/service.jar:lib/model.jar" lib/app.jar
~~~

This mode is useful when you want to know exactly which class references which class. If you only need the big picture, use `-verbose:package` or `-summary` to reduce output volume.

## 6. Recursive Analysis at the Module Level

For modular applications, jdeps can list module dependencies and analyze transitive dependencies of libraries on the module path if they are referenced.

Example:

~~~bash
jdeps --list-deps --module-path mods --module com.acme.app
~~~

`--list-deps` lists module dependencies and packages of JDK internal APIs if referenced. This option already recursively analyzes libraries on the classpath/module path when referenced.

If you only want direct dependencies, use:

~~~bash
jdeps --list-deps --no-recursive --module-path mods --module com.acme.app
~~~

To view dependencies after removing module reads edges implied by `requires transitive`:

~~~bash
jdeps --list-reduced-deps --module-path mods --module com.acme.app
~~~

To print a comma-separated list of modules:

~~~bash
jdeps --print-module-deps --module-path mods --module com.acme.app
~~~

The output of `--print-module-deps` can be used as input to `jlink`:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --output runtime
~~~

When using this result, you still need to check root modules and the application's service/runtime requirements. A static dependency list does not replace testing the custom runtime image.

## 7. Choosing the Output Detail Level

jdeps provides several display modes:

| Option | Output |
|---|---|
| Default | Package-level dependencies |
| -verbose:package | Package-level dependencies |
| -verbose:class | Class-level dependencies |
| -v or -verbose | All class-level dependencies; equivalent to `-verbose:class -filter:none` |
| -s or -summary | Dependency summary by archive |
| --list-deps | List of module dependencies |
| --list-reduced-deps | Module dependencies after removing implied reads |
| --print-module-deps | Comma-separated list of modules |

Example:

~~~bash
jdeps -R -summary --class-path "lib/service.jar:lib/model.jar" lib/app.jar
~~~

Use summary to answer "which archives/modules does this application pull in?". Use package-level to find the API groups being used. Use class-level when you need to investigate a specific dependency or trace a reference path.

## 8. Filtering Dependencies in Recursive Analysis

Recursive analysis can produce large output. jdeps supports filtering by package, regex, module, or class.

### Filtering by package

~~~bash
jdeps -R --package com.acme.model --class-path "lib/service.jar:lib/model.jar" lib/app.jar
~~~

You can use `-p` or `--package`. This option finds dependencies matching the specified package and can be repeated for multiple packages. It cannot be used together with `-e`/`--regex`.

### Filtering by regular expression

~~~bash
jdeps -R --regex "com\.acme\..*" --class-path "lib/service.jar:lib/model.jar" lib/app.jar
~~~

`-e` or `--regex` filters dependencies by pattern. Use it when you want to match multiple packages belonging to the same namespace.

### Filtering by module

~~~bash
jdeps -R --require java.sql --module-path mods --module com.acme.app
~~~

`--require` finds dependencies matching a module name. It cannot be used together with `--package` or `--regex`.

### Restricting analyzed classes with -include

~~~bash
jdeps -R -include "com\.acme\.app\..*" --class-path "lib/service.jar:lib/model.jar" lib/app.jar
~~~

`-include` restricts the set of classes to analyze. It differs from `--package` and `--regex`, which filter the discovered dependencies. You can combine `-include` with `-p` or `-e` when you want to restrict both source classes and reported dependencies.

### Filtering dependency edges

Common filter modes:

| Option | Meaning |
|---|---|
| -filter:package | Filters dependencies within the same package; this is the default |
| -filter:archive | Filters dependencies within the same archive |
| -filter:module | Filters dependencies within the same module |
| -filter:none | No package/archive filtering |
| -filter regex | Filters dependencies matching a regular expression |

`-R` implicitly enables `-filter:none`. If you add a specific filter, that filter is still applied. When results are too broad, filter intentionally and record the options used so others can reproduce the analysis.

## 9. Recursive Analysis and Inverse Analysis

**Recursive analysis** traverses forward from the input component to its dependencies:

~~~text
app -> service -> model -> java.base
~~~

**Inverse analysis** goes in the opposite direction: it finds artifacts that directly or indirectly depend on a target module, package, or regex.

Use **-I** or **--inverse** together with `--require`, `--package`, or `--regex`.

Example finding artifacts that depend on the `model` package:

~~~bash
jdeps --inverse --package com.acme.model --class-path "lib/model.jar:lib/service.jar" lib/app.jar lib/service.jar
~~~

Example finding modules that depend on `java.sql`:

~~~bash
jdeps --inverse --require java.sql --module-path mods
~~~

Inverse analysis is useful when:

- You want to know which libraries are affected if a package is removed.
- Preparing to upgrade or replace a dependency.
- Finding consumers of an internal module.
- Investigating the impact of moving an API to another module.

Do not confuse `-R` with `--inverse`: `-R` expands dependencies in the direction used by the input; `--inverse` finds artifacts that use the filtered target.

## 10. Generating a Dependency Graph with DOT

You can instruct jdeps to export a graph to visualize dependencies:

~~~bash
jdeps -R --dot-output build/jdeps-dot --class-path "lib/service.jar:lib/model.jar" lib/app.jar
~~~

The `--dot-output` option creates a directory containing a DOT file for each analyzed archive and an aggregate **summary.dot** file describing dependencies between archives.

Illustrative output structure:

~~~text
build/
  jdeps-dot/
    app.jar.dot
    service.jar.dot
    model.jar.dot
    summary.dot
~~~

The exact filenames depend on the input archives and resolved dependencies.

If Graphviz is installed, convert `summary.dot` to SVG:

~~~bash
dot -Tsvg build/jdeps-dot/summary.dot -o build/jdeps-summary.svg
~~~

Or generate a PNG image:

~~~bash
dot -Tpng build/jdeps-dot/summary.dot -o build/jdeps-summary.png
~~~

Graphs help identify:

- Multi-layer dependencies.
- Archives with too many outgoing dependencies.
- Circular dependencies between archives.
- Libraries shared by many components.
- Points where modules can be split or dependencies replaced.

The graph represents dependencies detected by jdeps from bytecode and module metadata. It does not by itself prove initialization order or runtime execution flow.

## 11. Finding Missing Dependencies

When a class references another class that jdeps cannot resolve, the output may include a missing dependency warning.

Use:

~~~bash
jdeps --missing-deps --class-path "lib/service.jar" lib/app.jar
~~~

`--missing-deps` finds unresolved dependencies. This option cannot be used with `-p`, `-e`, or `-s`.

If you need to analyze an archive in isolation, you can use:

~~~bash
jdeps --ignore-missing-deps -R app.jar
~~~

`--ignore-missing-deps` ignores missing dependencies in certain forms of analysis. It does not fix the classpath, add missing libraries, or prove the application can run. Only use it when you clearly understand why the dependency is absent from the analysis environment.

How to handle missing dependencies:

1. Read the source class and target class mentioned in the warning.
2. Identify the JAR or module providing the target class.
3. Add the correct artifact to `--class-path` or `--module-path`.
4. Check package paths and module exports.
5. Re-run jdeps.
6. Run application tests with the same set of dependencies.

If a dependency is genuinely missing from packaging, fix the build configuration or dependency declaration rather than hiding the warning.

## 12. Finding JDK Internal APIs in the Dependency Graph

A library may depend on JDK internal APIs, such as packages under `jdk.internal.*` or `com.sun.*`. These APIs are not stable public contracts and may change or have access restricted between JDK releases.

Use:

~~~bash
jdeps -R --jdk-internals --class-path "lib/service.jar:lib/model.jar" lib/app.jar
~~~

The `--jdk-internals` option finds class-level dependencies on JDK internal APIs. The manual warns that internal APIs may become inaccessible. Check transitive dependencies as well, because an internal API might be used in an external library rather than appearing directly in your application's source code.

When detected:

- Identify the artifact and class containing the reference.
- Find a replacement public API provided by Oracle/JDK.
- Upgrade the third-party library if the vendor has fixed it.
- Re-test on the target JDK.
- Avoid using `--add-exports` as a long-term solution if a public API alternative exists.

The `--jdk-internals` option cannot be used with `-p`, `-e`, or `-s` per the manual. If you need class-level results, leave this option's default mode or use combinations supported by jdeps.

## 13. Recursive Analysis for Multi-Release JARs

Multi-release JARs contain different class implementations per Java release, typically located under `META-INF/versions/N/`.

Use `--multi-release` to specify the version to analyze:

~~~bash
jdeps -R --multi-release 17 --class-path "lib/dependency.jar" app.jar
~~~

The value can be a release number of 9 or higher, or `base` to analyze the base entries. Use the same target release as the runtime where the application will run so the results reflect the selected class implementations.

When comparing two releases:

~~~bash
jdeps -R --multi-release 17 --class-path "lib/dependency.jar" app.jar
jdeps -R --multi-release 21 --class-path "lib/dependency.jar" app.jar
~~~

Differences may come from the classes selected inside the multi-release JAR. Do not conclude that dependencies changed without confirming the same artifacts, module path, and analysis configuration.

## 14. API-Only and Compile-Time Dependencies

Not every dependency in bytecode is part of the public API. jdeps has the **--api-only** option to restrict analysis to API signatures, such as field types, method parameters, return types, and checked exceptions in public/protected members of public classes.

Example:

~~~bash
jdeps -R --api-only --class-path "lib/service.jar:lib/model.jar" lib/app.jar
~~~

This mode is useful when you want to know which dependencies are exposed through the public API and could affect consumers when the library changes.

The **--compile-time** option analyzes the compile-time view of transitive dependencies. It is suitable when you need to understand the dependencies required during compilation, especially when analyzing a directory, JAR, or module with many classes.

Example:

~~~bash
jdeps --compile-time --class-path "lib/service.jar:lib/model.jar" lib/app.jar
~~~

Distinguishing API-only and compile-time:

- API-only focuses on dependencies appearing in public/protected API signatures.
- Compile-time examines dependencies needed for the compile-time view.
- Recursive runtime analysis with `-R` traverses runtime dependencies.

Choose the mode based on the question you need to answer; they do not replace one another.

## 15. Limitations of Recursive Analysis

jdeps is a static analyzer. It reads class files and module metadata; it does not run the application to observe every actual execution path.

Cases that may not be fully reflected:

- Loading classes via reflection from names constructed at runtime.
- `Class.forName` with strings loaded from configuration files or databases.
- Plugins discovered and dynamically loaded from directories.
- Bytecode generated at runtime.
- Dependencies selected via environment variables or feature flags.
- Resources/services located through mechanisms that do not manifest as ordinary class dependencies.

Therefore:

1. Use jdeps to understand static dependencies.
2. Check Maven/Gradle build descriptors for declared dependencies.
3. Review runtime configuration, plugins, and reflection usage.
4. Run integration tests on the target runtime.
5. Monitor class-loading and module errors at runtime.

A clean jdeps result does not guarantee the application needs no dynamic dependencies. Conversely, a detected dependency is not necessarily executed on every code path.

## 16. Recursive Dependency Analysis Workflow

1. **Select inputs**: identify the JAR, class directory, or module to analyze.
2. **Prepare paths**: provide all dependencies needed for resolution using `--class-path` or `--module-path`.
3. **Run a baseline**: use default jdeps to inspect direct dependencies.
4. **Enable recursive mode**: use `-R` or `--recursive` to traverse runtime dependencies.
5. **Choose detail level**: package, class, or summary depending on your goal.
6. **Filter results**: use `--package`, `--regex`, `--require`, or `-include` when needed.
7. **Find missing dependencies**: run `--missing-deps` and resolve any unresolved classes.
8. **Check internal APIs**: run `--jdk-internals` if preparing for a JDK upgrade.
9. **Export graphs**: use `--dot-output` when you need to visualize relationships between archives.
10. **Check module dependencies**: use `--list-deps` or `--print-module-deps` for modular applications.
11. **Verify against runtime**: check reflection, plugins, services, and dynamic dependencies.
12. **Record command and environment**: document the JDK version, classpath/module path, and options so the analysis can be reproduced.

## 17. Common Errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| Transitive dependencies not shown | `-R` not enabled or dependencies not resolved | Use `-R` and provide classpath/module path |
| Output too large | `-R` implicitly uses `-filter:none` | Use summary/package output or filter intentionally |
| Missing dependency reported | Missing JAR/module or wrong path | Add the missing artifact and re-run |
| Only packages shown instead of classes | Using default/package output | Use `-verbose:class` |
| Intra-archive edges not shown | Default filter removes those dependencies | Use `-R` or `-filter:none` |
| Module name not recognized | Wrong module path or module name | Check `module-info.class` and `--module-path` |
| Different results across Java releases | Multi-release JAR selects different classes | Specify `--multi-release` explicitly |
| Library loaded via reflection not found | Dependency does not appear as a static bytecode reference | Check runtime configuration and integration tests |
| DOT graph missing archives | Dependency unresolved or outside input scope | Check classpath/module path and inputs |
| Internal API warning from third-party library | Transitive dependency uses a JDK internal API | Identify the artifact and upgrade/replace the library |

## 18. Key Takeaways

- jdeps analyzes static dependencies from class files, directories, JARs, or modules.
- `-R` and `--recursive` traverse runtime dependencies across multiple layers.
- `-R` implicitly enables `-filter:none`, so output can be very large.
- `--no-recursive` limits analysis to direct dependencies.
- Recursive analysis requires a proper classpath/module path to locate libraries at subsequent layers.
- `--list-deps` automatically analyzes transitive library dependencies on the classpath/module path; `--no-recursive` can be used to restrict it.
- `--inverse` finds artifacts that directly or indirectly depend on a specified package, regex, or module.
- `--dot-output` generates DOT graphs and `summary.dot` to visualize dependencies between archives.
- `--missing-deps` finds unresolved dependencies; `--ignore-missing-deps` only suppresses warnings and does not fix the root cause.
- `--jdk-internals` detects dependencies on JDK internal APIs.
- `--multi-release` selects which implementation inside a multi-release JAR to analyze.
- jdeps does not fully detect dynamically or reflectively loaded dependencies; combine it with runtime checks and tests.

## Official References

- [The jdeps Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html)
- [Java Platform Module System — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [jlink Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html)
- [Java SE 17 API Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/)
