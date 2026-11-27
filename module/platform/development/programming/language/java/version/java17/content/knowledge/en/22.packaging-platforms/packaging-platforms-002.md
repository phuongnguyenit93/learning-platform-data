# Analyzing Required Modules with jdeps in Java 17

## 1. What Is jdeps Used For?

`jdeps` is a command-line tool included with the JDK for analyzing dependencies expressed in Java bytecode. The tool can read class files, class directories, JARs, and modules to tell you:

- Which packages a class or package references.
- Which JARs or modules a JAR depends on.
- Which Java Platform Module System (JPMS) modules an application needs.
- How a module descriptor declares dependencies and how it might be simplified.
- Whether application code depends on JDK internal APIs.
- Which dependencies cannot be found on the class path or module path supplied to the tool.

In Java 17, `jdeps` is especially useful when preparing to migrate an application from the classpath to the module path, writing `module-info.java`, determining the set of modules needed for a custom runtime with `jlink`, or identifying dependencies on internal APIs that should be replaced.

`jdeps` performs **static bytecode analysis**. It does not run the application and does not observe every dependency loaded dynamically at runtime. Therefore, its output is a starting point for investigation and module design; you still need to cross-check how the application actually uses reflection, service loading, resources, and plugins.

## 2. The Java Platform Module System and Dependencies

Since Java 9, the JDK has been organized into modules. For example:

| Module | Typical Contents |
|---|---|
| `java.base` | Foundational types such as `String`, `Object`, basic collections, basic I/O, and many core APIs. |
| `java.logging` | Java logging API such as `java.util.logging`. |
| `java.sql` | JDBC API. |
| `java.net.http` | HTTP Client API. |
| `java.xml` | XML API. |
| `java.desktop` | AWT, Swing, and certain desktop APIs. |
| `jdk.unsupported` | Certain internal/discouraged APIs such as `sun.misc.Unsafe` via the corresponding module export. |

An application module declares dependencies using the `requires` directive in `module-info.java`:

~~~java
module com.example.orders {
    requires java.sql;
    requires java.net.http;
}
~~~

The `java.base` module is implicitly required by every normal Java module; there is no need to write `requires java.base` in an application descriptor.

If a module uses an API from another module without declaring the required dependency, compilation or module resolution may fail. `jdeps` helps discover the dependencies referenced by bytecode so you have a concrete basis for writing the descriptor.

## 3. Preparing Inputs for jdeps

`jdeps` analyzes compiled bytecode; it does not directly parse `.java` files like a source import checker.

### 3.1. Checking the Tool and Version

Open a terminal with JDK 17 on `PATH`:

~~~text
java -version
jdeps --version
jdeps --help
~~~

Verify that `java` and `jdeps` come from the same JDK or from a compatible toolchain version. If you have multiple JDKs installed on your machine, invoke the tool using the absolute path to JDK 17's `bin` directory.

### 3.2. Analyzing a Class Directory

Suppose source files are compiled into the `out` directory:

~~~text
javac -d out src/com/example/Main.java
jdeps out
~~~

`jdeps` reads the class files inside the input directory. When a project has multiple packages or modules, pass the exact output directory corresponding to the bytecode you want to analyze.

### 3.3. Analyzing a JAR

For a packaged application:

~~~text
jdeps app.jar
~~~

Or request a dependency summary:

~~~text
jdeps --summary app.jar
~~~

`--summary` provides a more concise view by archive/package dependency instead of listing every class. When investigating further, you can increase the level of detail.

### 3.4. Analyzing Multiple JARs

You can pass multiple archives in the same command:

~~~text
jdeps app.jar lib/domain.jar lib/client.jar
~~~

This lets you see relationships among the input artifacts. If the JARs depend on each other but are missing from the input list or class path, the output may report unfound dependencies. Supply all relevant libraries to avoid misreading the results.

## 4. Viewing Dependencies at the Package and Class Levels

Choose the level of detail based on the question you are investigating.

### 4.1. Package-Level Dependencies

~~~text
jdeps -verbose:package app.jar
~~~

The output shows relationships between source packages and target packages. This level is suitable for understanding overall structure, such as which business package depends on JDBC, HTTP, or logging.

Illustrative output example:

~~~text
com.example.orders -> java.lang
com.example.orders -> java.sql
com.example.orders -> java.net.http
com.example.orders -> com.example.domain
~~~

The lines above only illustrate how to read the output, not the fixed output of a specific JAR.

### 4.2. Class-Level Dependencies

~~~text
jdeps -verbose:class app.jar
~~~

Class-level mode shows which class references which class. It is useful when a package contains many classes and you need to pinpoint exactly where a dependency originates.

Illustrative example:

~~~text
com.example.orders.OrderClient
  -> java.net.http.HttpClient
  -> java.net.http.HttpRequest
  -> java.net.http.HttpResponse

com.example.orders.OrderRepository
  -> java.sql.Connection
  -> java.sql.PreparedStatement
~~~

Class-level output is usually significantly longer. Use it when package-level output is not specific enough to locate what needs to be changed.

### 4.3. Analyzing Public APIs

The `--api-only` option restricts analysis to public and protected APIs:

~~~text
jdeps --api-only -verbose:package app.jar
~~~

This mode is useful for seeing dependencies that a library exposes through its public API, such as parameter types, return types, or superclasses/interfaces. A dependency appearing only in private implementation details may not show up in `--api-only` results.

If your goal is packaging an executable application, do not rely solely on `--api-only` because dependencies inside implementation details are still required at runtime.

## 5. Recursive Analysis

By default, `jdeps` analyzes the specified inputs. To traverse their dependencies recursively, use `--recursive`:

~~~text
jdeps --recursive app.jar
~~~

You can combine it with summary mode:

~~~text
jdeps --recursive --summary app.jar
~~~

Recursive analysis helps explore multiple layers of dependencies, but the results depend on whether the tool can locate the relevant archives and modules. Be sure to provide the appropriate class path or module path.

### 5.1. Class Path for External Libraries

If the application depends on JARs located in the `lib` directory:

~~~text
jdeps --recursive --class-path "lib/*" app.jar
~~~

`--class-path` (alias `-cp`) specifies where to find classes on the classpath. On Windows, when listing multiple classpath entries manually with a separator, the system uses a semicolon; a directory wildcard such as `lib/*` is often more convenient when all JARs reside in the same directory.

If a required library is omitted from the class path, `jdeps` may report missing dependencies or fail to analyze completely. Do not treat the output module list as complete if there are warnings about unfound dependencies.

### 5.2. Module Path for Packaged Modules

When dependencies are already modules or automatic modules, use `--module-path`:

~~~text
jdeps --module-path mods --module com.example.orders
~~~

`--module-path` (alias `-p`) specifies the path containing modules. `--module` (alias `-m`) selects the module to analyze.

With multiple modules, supply the complete module path that the application needs so the tool resolves the graph accurately.

## 6. Finding Required JDK Modules

A common task when packaging an application is identifying which Java Platform modules the application needs.

### 6.1. Listing Module Dependencies

~~~text
jdeps --list-deps app.jar
~~~

This command lists the module dependencies that `jdeps` infers from bytecode. For example, an application using JDBC and HTTP Client might depend on `java.base`, `java.sql`, and `java.net.http`.

The exact output depends on the referenced classes and whether all dependencies can be found.

### 6.2. Reduced Dependency List

~~~text
jdeps --list-reduced-deps app.jar
~~~

This option displays reduced module dependencies, removing relationships already implied by other dependencies in the graph. It provides a shorter list when modules have transitive dependency relationships.

### 6.3. Printing Module List as CSV

~~~text
jdeps --print-module-deps app.jar
~~~

`--print-module-deps` prints a comma-separated list of modules, suitable for feeding into a custom runtime packaging step.

Illustrative output example:

~~~text
java.base,java.net.http,java.sql
~~~

Do not copy this example blindly for every application. Run it on your actual artifact with the full class path, and inspect any missing-dependency warnings before using the list.

### 6.4. Combining with jlink

`jlink` creates a runtime image containing only the required modules. You can use the output of `jdeps --print-module-deps` as input to `--add-modules`:

~~~text
jdeps --print-module-deps --class-path "lib/*" app.jar
~~~

Suppose the result is:

~~~text
java.base,java.logging,java.sql
~~~

Then create the runtime image:

~~~text
jlink --add-modules java.base,java.logging,java.sql --output runtime
~~~

These are two separate steps: `jdeps` analyzes bytecode and suggests module dependencies; `jlink` resolves the modules and builds the image. If the application uses providers, reflection, resources, or dynamically loaded modules that static analysis cannot detect, you may need to add modules to the list.

## 7. Checking a Module Descriptor with --check

When an application already has a `module-info.java`, you can use `jdeps --check` to inspect its dependencies and descriptor:

~~~text
jdeps --check com.example.orders --module-path mods
~~~

`--check` analyzes the specified module, displaying its module descriptor and dependencies. The tool can also show a suggested descriptor or reduced dependencies to help identify redundant or inappropriate `requires` directives.

### 7.1. Module Descriptor Example

Suppose the module is:

~~~java
module com.example.orders {
    requires java.base;
    requires java.sql;
    requires java.logging;
    requires java.net.http;

    exports com.example.orders.api;
}
~~~

`java.base` is an implicit dependency, so `requires java.base` is unnecessary in a normal descriptor. The remaining dependencies should be verified against the bytecode and APIs used by the module.

After packaging the modules into the `mods` directory, run:

~~~text
jdeps --check com.example.orders --module-path mods
~~~

Review the current descriptor, suggested descriptor, and dependency graph. If the tool suggests reducing a `requires`, check whether that dependency is already provided transitively by another module and whether the module's public API exposes types from it.

### 7.2. Distinguishing Regular requires and requires transitive

`jdeps` can help uncover dependency relationships, but the module designer still decides API semantics:

- `requires X`: the current module needs module `X` for its implementation or compilation.
- `requires transitive X`: the current module uses types from `X` in its public API in a way that requires dependent modules to read `X`.
- `requires static X`: a dependency needed at compile time but not necessarily at runtime; use only when the contract and usage match.

For instance, if a module's public method returns `java.sql.Connection`, consumers of the module may need to read `java.sql` to compile code using that API. When designing the module API, consider `requires transitive java.sql` if the public contract genuinely requires it.

Do not turn every dependency found by `jdeps` into `requires transitive`. Only dependencies that must be propagated to consumers by API semantics should use this directive.

## 8. Detecting Dependencies on JDK Internal APIs

An important reason to run `jdeps` is to locate usage of JDK internal APIs.

Packages such as `sun.*`, `com.sun.*`, or packages that are not publicly exported may change across JDK releases. Depending on them makes applications fragile during upgrades or when running under module encapsulation.

Run:

~~~text
jdeps --jdk-internals app.jar
~~~

Or combine with class-level output to see the exact call sites:

~~~text
jdeps --jdk-internals -verbose:class app.jar
~~~

Example output may point out a class using an internal API and suggest a public replacement API if the JDK has one recorded.

### 8.1. Why Remove Internal APIs?

- Internal APIs are not public compatibility contracts.
- The module system restricts access to unexported packages.
- Internal APIs may be modified or removed between releases.
- Adding flags to open packages/modules can mask design issues and complicate deployment configuration.

When internal usage is reported, look for supported public alternatives in Java SE or supported libraries. After fixing it, re-run `jdeps --jdk-internals` to verify the dependency is gone.

### 8.2. No Internal APIs Detected Is Not Absolute Proof

`jdeps` analyzes dependencies inferable from bytecode. If an application loads internal class names via strings, reflection, JNI, or runtime libraries, static analysis may not see every code path. Combine source inspection, testing on the target JDK, and observing actual runtime behavior.

## 9. Finding Missing Dependencies

When libraries are not on the class path or module path, the tool may fail to resolve certain references. You can use:

~~~text
jdeps --missing-deps app.jar
~~~

This option lists dependencies not found during analysis. To suppress missing-dependency warnings when you only want to view the rest, there is an option:

~~~text
jdeps --ignore-missing-deps app.jar
~~~

The two serve different purposes:

- `--missing-deps` actively helps locate unfound class/package dependencies.
- `--ignore-missing-deps` lets analysis continue without stopping on missing dependencies; it does not fix or supply the missing libraries.

Do not use `--ignore-missing-deps` to generate a final module list for a runtime without investigating the warnings. A missing dependency can cause the printed module list to be incomplete.

### 9.1. Checking Class Path and Module Path

If a class from an external library cannot be found:

1. Identify the JAR containing that class.
2. If the library belongs on the classpath, add it to `--class-path`.
3. If the library is a module, add it to `--module-path`.
4. Re-run `--missing-deps` to check for remaining missing dependencies.
5. Only rely on the module output after important dependencies are resolved.

`jdeps` does not replace Maven or Gradle dependency resolution. The tool analyzes bytecode based on the artifacts and paths you provide; it does not automatically download dependencies from repositories.

## 10. Generating module-info.java for Non-Modular JARs

A library JAR without `module-info.class` can become an automatic module when placed on the module path. To begin migrating to an explicit module, `jdeps` can generate a draft descriptor.

Use:

~~~text
jdeps --generate-module-info generated-modules lib/customer-domain.jar
~~~

`jdeps` creates a directory containing `module-info.java` for the corresponding module. The generated file is a starting point; review and edit it before official use.

### 10.1. Generating an Open Module Descriptor

If you need a descriptor with the `open module` keyword:

~~~text
jdeps --generate-open-module generated-open-modules lib/legacy-model.jar
~~~

An open module opens its packages for deep reflection under module system rules. This is a broad choice; use it only when frameworks truly need deep reflection across many packages. If only specific packages need reflection, consider targeted `opens` directives instead of opening the entire module.

### 10.2. Why Generated Descriptors Must Be Reviewed

`jdeps` can infer dependencies from bytecode, but it does not fully understand design intent:

- Which packages should be `exports` to consumers.
- Which packages need `opens` for framework reflection.
- Which services the module `uses` or `provides`.
- Which dependencies should be `requires transitive`.
- Which dependencies are compile-time only or optional configuration.
- Which APIs are internal and should not be exported.

Therefore, a generated module descriptor is not a final architectural decision. Edit it to match your desired APIs and module boundaries.

### 10.3. Workflow to Convert a JAR to an Explicit Module

1. Run `jdeps --summary` and `jdeps --verbose:class` to understand dependencies.
2. Use `--print-module-deps` to determine required JDK modules.
3. Run `--generate-module-info` to create an initial descriptor.
4. Edit `module-info.java`: `requires`, `exports`, `opens`, `uses`, and `provides`.
5. Recompile the JAR with the descriptor.
6. Place the JAR and dependencies on the module path.
7. Run `jdeps --check` and test the application using the module path.

## 11. Analyzing Multi-Release JARs

A Multi-Release JAR can hold multiple versions of classes in the same archive, such as base classes and alternate versions under `META-INF/versions/`. The runtime picks the class matching the running Java version.

To analyze contents targeting a specific version:

~~~text
jdeps --multi-release 17 app-mr.jar
~~~

`--multi-release` lets you specify which version in a multi-release JAR to analyze. When evaluating an application for Java 17, analyze version 17 explicitly rather than looking only at base classes.

This matters because classes under `META-INF/versions/17` may use different APIs or modules than the base classes. Dependency results can vary depending on the target runtime version.

## 12. Exporting Dependency Graphs as DOT

When the dependency graph is large, text output can be hard to follow. `jdeps` can export graph data for use with Graphviz:

~~~text
jdeps --dot-output dot-output app.jar
~~~

The `dot-output` directory contains DOT files representing dependencies. You can render them with Graphviz:

~~~text
dot -Tsvg dot-output/summary.dot -o dependency-graph.svg
~~~

The exact DOT file names depend on the analyzed archives/modules. List the contents of the output directory before invoking Graphviz.

### 12.1. When to Use Graphs

- Identifying packages that create cyclic dependencies or excessive coupling.
- Finding modules with too many direct dependencies.
- Presenting module structure to a development team.
- Comparing dependency graphs before and after modularization.

The graph shows dependencies detected by the tool; it does not evaluate design quality on its own. A graph with fewer edges is not automatically better if APIs are fragmented or dependencies are hidden behind reflection.

## 13. Example Workflow from JAR to Module List

Suppose the project layout is:

~~~text
orders-app/
  app.jar
  lib/
    customer-domain.jar
    reporting-client.jar
~~~

The application uses JDBC, HTTP Client, and logging. We proceed step by step:

### Step 1 — Analyze Package Dependencies

~~~text
jdeps -verbose:package --class-path "lib/*" app.jar
~~~

Inspect which application packages depend on which library and JDK packages.

### Step 2 — Recursive Analysis

~~~text
jdeps --recursive --summary --class-path "lib/*" app.jar
~~~

Inspect dependencies across multiple archive layers. Check warnings if any libraries are not found.

### Step 3 — Print the JDK Module List

~~~text
jdeps --print-module-deps --class-path "lib/*" app.jar
~~~

Save the module list inferred by the tool. If the output includes unexpected modules, return to class-level analysis to locate the class introducing that dependency.

### Step 4 — Find Internal APIs

~~~text
jdeps --jdk-internals --class-path "lib/*" app.jar
~~~

If any are found, identify public API replacements and update the libraries/application if possible.

### Step 5 — Generate a Descriptor if the Application Should Become a Module

~~~text
jdeps --generate-module-info generated --class-path "lib/*" app.jar
~~~

Review the generated descriptor, adjust the module name and directives to match your actual architecture.

### Step 6 — Check the Module Descriptor

After compiling and packaging the modules into the `mods` directory:

~~~text
jdeps --check com.example.orders --module-path "mods;mods/lib"
~~~

On Windows, a multi-directory module path uses semicolons; on Linux/macOS, it uses colons. Replace the illustrative paths with your project's actual module path.

### Step 7 — Create the Runtime Image

Once module dependencies are confirmed, use the appropriate module list with `jlink`:

~~~text
jlink --module-path "%JAVA_HOME%/jmods;mods" --add-modules com.example.orders --output runtime
~~~

This is an example for Windows Command Prompt; on Linux/macOS, use the corresponding path syntax and environment variable syntax. `jlink` resolves dependencies of the selected root modules on the module path.

## 14. Limitations of Static Analysis

`jdeps` is very helpful, but it cannot infer every runtime dependency from bytecode alone.

### 14.1. Reflection and String Class Names

For example:

~~~java
String implementation = config.getProperty("handler.class");
Class<?> type = Class.forName(implementation);
~~~

If a class name exists only in a configuration file or is constructed dynamically, the bytecode may contain no static type reference to that class. `jdeps` may not detect the required module from this path.

### 14.2. ServiceLoader and Providers

An application may discover implementations via `ServiceLoader`:

~~~java
ServiceLoader<PaymentProvider> providers =
        ServiceLoader.load(PaymentProvider.class);
~~~

Providers can be declared in the descriptor with `provides ... with ...` or equivalent metadata. When modularizing, review both service provider modules and consumer modules:

~~~java
module com.example.payment.api {
    exports com.example.payment;
}

module com.example.payment.app {
    requires com.example.payment.api;
    uses com.example.payment.PaymentProvider;
}

module com.example.payment.provider {
    requires com.example.payment.api;
    provides com.example.payment.PaymentProvider
            with com.example.payment.provider.DefaultProvider;
}
~~~

Do not rely solely on class-level dependencies to determine which providers must be present in a runtime image.

### 14.3. JNI and Native Libraries

Native dependencies loaded via `System.loadLibrary()` or similar mechanisms are not necessarily represented as Java modules in bytecode. Inspect native libraries, CPU architecture, operating system, and deployment configuration separately.

### 14.4. Resources and Configuration

Applications may read resources, configuration files, scripts, or templates to determine which classes/plugins to load. `jdeps` is not a substitute for reviewing these resources and configurations.

### 14.5. Dependencies Loaded by Frameworks

Some frameworks rely on reflection, annotation scanning, classpath scanning, or plugin registries. Consult the framework documentation and run integration tests on the intended module path/runtime image.

### 14.6. Analyzing One JAR Version Does Not Represent Every Runtime

With a multi-release JAR, the dependencies of the selected class can vary by Java version. Use `--multi-release` matching your target runtime and verify the final artifact you intend to deploy.

## 15. Common jdeps Options

| Option | Purpose |
|---|---|
| `--summary` | Summarize dependencies by archive/package. |
| `-verbose:package` | Show dependencies by package. |
| `-verbose:class` | Show dependencies by class. |
| `--recursive` | Traverse dependencies recursively. |
| `--class-path` | Provide classpath to resolve libraries. |
| `--module-path` | Provide module path. |
| `--module` | Select the module to analyze. |
| `--list-deps` | List module dependencies. |
| `--list-reduced-deps` | List reduced module dependencies. |
| `--print-module-deps` | Print module dependencies as a comma-separated list. |
| `--check` | Check module descriptor and dependencies. |
| `--jdk-internals` | Find dependencies on JDK internal APIs. |
| `--missing-deps` | List unfound dependencies. |
| `--ignore-missing-deps` | Ignore missing dependencies during analysis. |
| `--generate-module-info` | Generate a module descriptor for a non-modular JAR. |
| `--generate-open-module` | Generate an open module descriptor. |
| `--multi-release` | Select which version of a multi-release JAR to analyze. |
| `--api-only` | Analyze only public/protected APIs. |
| `--dot-output` | Export the dependency graph in DOT format. |

You do not need to memorize all options. Use `jdeps --help` and `jdeps --version` to check exact syntax on the JDK you are using.

## 16. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| External library class not found | Missing JAR on classpath or module path. | Add `--class-path` or `--module-path`. |
| Module list appears incomplete | Dynamic dependencies or unprovided libraries. | Check missing dependencies, reflection, service providers, and resources. |
| Output is too long | Using class-level or recursive across many JARs. | Start with `--summary` or package-level. |
| Internal API dependency not shown | Loaded via reflection/JNI or not in input bytecode. | Combine source inspection, configuration review, and runtime tests. |
| Generated descriptor fails to run | `jdeps` does not fully infer exports/opens/uses/provides intent. | Edit descriptor according to module architecture and test. |
| Module path fails to resolve | Missing module or incorrect module name. | Check module name, module path, and `java --list-modules`. |
| Results differ between Java 11 and Java 17 | Multi-release JAR or version-specific APIs/modules. | Use `--multi-release 17` when appropriate and analyze the target artifact. |
| `jlink` reports missing module | Incomplete module list or module path. | Re-check dependencies and add needed modules/providers. |
| Assuming `jdeps` downloads dependencies | The tool only analyzes supplied artifacts. | Use Maven/Gradle to resolve dependencies beforehand. |

## 17. Practice Exercises

### Exercise 1 — Analyze a JAR

Choose a JAR in your project. Run `jdeps --summary`, `jdeps -verbose:package`, and `jdeps -verbose:class`. Compare the levels of detail and identify which package introduces dependencies on JDK modules.

### Exercise 2 — Print Module Dependencies

Run `jdeps --list-deps` and `jdeps --print-module-deps` on the same artifact. Note the required JDK modules and explain why the comma-separated output is useful for `jlink`.

### Exercise 3 — Find Internal APIs

Run `jdeps --jdk-internals` on your application and third-party libraries. If any are reported, look up public replacement APIs and record the relevant modules/packages.

### Exercise 4 — Check Missing Dependencies

Run `jdeps --missing-deps` while intentionally omitting a JAR from the class path. Then add the JAR via `--class-path` and compare the results.

### Exercise 5 — Generate a Module Descriptor

Use `--generate-module-info` on a JAR without a module descriptor. Read the generated file, remove `requires java.base` if present, and review `exports`, `opens`, and `requires transitive` according to the library's API.

### Exercise 6 — Check a Declared Module

Place the module on the module path and run `jdeps --check`. Compare the current descriptor and suggested descriptor; explain which dependencies can be reduced and why.

### Exercise 7 — Analyze a Multi-Release JAR

Pick a Multi-Release JAR and run analysis with `--multi-release 17`. Compare the output with the base version or another target version if supported by the artifact.

### Exercise 8 — Build a Runtime Image

Use `--print-module-deps` to obtain the module list. Build a runtime image with `jlink` and run the application on that image. If the application fails due to a provider or dynamically loaded class, identify the missing module and explain why static analysis did not detect it.

## 18. Workflow for Using jdeps in Real Projects

When preparing to modularize or create a runtime image for a Java 17 application, you can follow this sequence:

1. **Resolve dependencies first.** Use Maven/Gradle to download and place all artifacts into a build directory.
2. **Select the right artifact.** Analyze the class directory or exact JAR version to be deployed.
3. **Start with a summary.** Use `jdeps --summary` to grasp the overall structure.
4. **Drill down by package/class.** Use `-verbose:package` or `-verbose:class` to locate dependency sources.
5. **Supply library paths.** Use `--class-path` or `--module-path` to resolve dependencies.
6. **Identify JDK modules.** Use `--list-deps` and `--print-module-deps`.
7. **Check internal APIs and missing dependencies.** Use `--jdk-internals` and `--missing-deps`.
8. **Generate or verify descriptors.** Use `--generate-module-info` for non-modular JARs and `--check` for existing modules.
9. **Cross-check dynamic dependencies.** Review reflection, `ServiceLoader`, JNI, resources, and framework plugins.
10. **Create and test the runtime image.** Run `jlink` with the full module path, then execute integration tests on the final image.

`jdeps` reduces guesswork when designing modules. The best results come from combining bytecode analysis with knowledge of your public APIs, runtime configuration, and how the application actually loads components.

## 19. Key Principles to Remember

- `jdeps` performs static dependency analysis on class files, JARs, directories, and modules; it does not run the application.
- `--summary` gives a high-level overview; `-verbose:package` and `-verbose:class` help trace details.
- `--recursive` traverses multiple layers of dependencies; supply a complete class path/module path.
- `--list-deps`, `--list-reduced-deps`, and `--print-module-deps` help identify modules needed at runtime.
- `--print-module-deps` produces a comma-separated list of modules that can be fed into `jlink --add-modules`.
- `--check` helps verify module descriptors and dependencies.
- `--jdk-internals` detects usage of JDK internal APIs that should be considered for replacement.
- `--generate-module-info` produces a draft descriptor; review `requires`, `exports`, `opens`, `uses`, and `provides` before using it.
- `--multi-release` analyzes the classes selected for a specific version inside a Multi-Release JAR.
- `--missing-deps` helps locate unresolved dependencies; `--ignore-missing-deps` only ignores warnings and does not supply missing libraries.
- Static analysis can miss dependencies loaded via reflection, string class names, `ServiceLoader`, JNI, resources, and plugins.
- `jdeps` does not replace Maven/Gradle dependency resolution, runtime testing, or module design.
- Build a runtime image only after reviewing dynamic dependencies and testing the application on the target image.

### References

- [Oracle Java 17 — jdeps Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html).
- [Oracle Java 17 — Java Platform Module System](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/package-summary.html).
- [Oracle Java 17 — jlink Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html).
- [JEP 261 — Module System](https://openjdk.org/jeps/261).
