# Analyzing Dependencies with jdeps in Java

jdeps is a static dependency analysis tool bundled with the JDK. It reads class files, JARs, or class directories to report which packages, classes, and modules an application depends on. jdeps is useful when auditing libraries before upgrading the JDK, finding references to JDK internal APIs, preparing to migrate an application to the Java Platform Module System (JPMS), determining the modules required for jlink, and investigating missing dependencies.

jdeps analyzes references observable from bytecode and metadata. It does not execute the program, does not prove that all runtime branches work, and cannot reliably detect every dependency loaded via reflection, class names in configuration, JNI, or runtime-generated code. Therefore, combine jdeps reports with builds, tests, and smoke tests on the target runtime.

This article walks through a sample JAR to commands for analyzing classes/packages/modules, missing dependencies, JDK internal APIs, DOT graphs, and module descriptors. The examples were tested with jdeps 24.0.2; output may vary slightly across JDK versions.

## 1. What is jdeps used for?

jdeps answers questions about static dependencies:

- Which packages and classes is a JAR referencing?
- Which JDK modules does the application use?
- Are there any dependencies not found on the classpath/module path?
- Does the source or any dependency reference JDK internal APIs?
- Which packages depend on other packages?
- When migrating to JPMS, which `requires` directives does the module descriptor need to declare?
- Which modules are required to build a minimal runtime image with jlink?
- Which modules depend on a specific package or module?

For example, an application might import `java.sql`, `java.net.http`, and `java.time`. jdeps can aggregate these references into dependencies on `java.sql`, `java.net.http`, and `java.base`.

jdeps is an analysis tool, not a compiler, dependency resolver, or test runner. It does not replace `javac`, Maven/Gradle dependency analysis, unit tests, or integration tests.

## 2. Where is jdeps located and how to check its version?

jdeps is distributed with the JDK, located in the `bin` directory:

Windows:

~~~powershell
where.exe jdeps
jdeps --version
~~~

Linux/macOS:

~~~bash
command -v jdeps
jdeps --version
~~~

If the command is not found, check `JAVA_HOME` and `PATH`. You can invoke it directly:

Windows:

~~~powershell
& "$env:JAVA_HOME\bin\jdeps.exe" --version
~~~

Linux/macOS:

~~~bash
"$JAVA_HOME/bin/jdeps" --version
~~~

Use jdeps from a JDK that matches the class-file version and module metadata being analyzed. An older jdeps version may not be able to read class files compiled by a newer JDK. Record the versions of `java`, `javac`, and `jdeps` in CI so results can be explained and reproduced.

View the options supported by the running version:

~~~powershell
jdeps --help
~~~

Option names and analysis capabilities may be added across JDK releases. When writing long-lived scripts, check the help output of the pinned JDK instead of assuming every machine has the same set of options.

## 3. Inputs that jdeps can analyze

jdeps accepts one or more inputs:

- A single `.class` file.
- A directory containing compiled packages/classes.
- A regular JAR.
- A JAR with a module descriptor.
- A multi-release JAR.
- A module or set of modules when using module analysis options.

Examples:

~~~powershell
jdeps out\demo\App.class
jdeps out
jdeps app.jar
~~~

For a class directory, jdeps scans the classes within that directory. For a JAR, the tool reads the classes and metadata inside the archive. Multiple JARs can be passed in the same command to inspect relationships between artifacts.

It is best to analyze the artifact after building, as that is the actual content that will be packaged and released. Analyzing `target/classes` or `build/classes` is also useful during development, but it does not replace checking the final JAR.

## 4. Creating a sample project for practice

The example uses a small library named `dependency.jar` and an application `app.jar`. The application references a class from the library while also using several JDK modules.

Source structure:

~~~text
jdeps-demo/
  src/
    dep/
      api/
        Marker.java
    app/
      demo/
        App.java
~~~

File `src/dep/api/Marker.java`:

~~~java
package dep.api;

public final class Marker {
    public String name() {
        return "marker";
    }
}
~~~

File `src/app/demo/App.java`:

~~~java
package demo;

import dep.api.Marker;
import java.net.http.HttpClient;
import java.sql.Connection;
import java.time.Instant;

public final class App {
    public static void main(String[] args) {
        Marker marker = new Marker();
        Class<?>[] types = { Connection.class, HttpClient.class };

        System.out.println(marker.name());
        System.out.println("JDK types: " + types.length);
        System.out.println(Instant.EPOCH);
    }
}
~~~

Compile and package on Windows PowerShell, Linux, or macOS from the `jdeps-demo` directory:

~~~powershell
javac -d dep-classes src\dep\api\Marker.java
jar --create --file dependency.jar -C dep-classes .

javac -cp dependency.jar -d app-classes src\app\demo\App.java
jar --create --file app.jar -C app-classes .
~~~

On Linux/macOS, replace backslashes in source paths with `/`:

~~~bash
javac -d dep-classes src/dep/api/Marker.java
jar --create --file dependency.jar -C dep-classes .

javac -cp dependency.jar -d app-classes src/app/demo/App.java
jar --create --file app.jar -C app-classes .
~~~

The result is two artifacts:

- `dependency.jar` containing `dep.api.Marker`.
- `app.jar` containing `demo.App`, referencing `dep.api.Marker`, `java.sql`, `java.net.http`, and `java.time`.

The application is compiled with `dependency.jar` on the classpath. When analyzing `app.jar`, you must provide that dependency again so jdeps can resolve references outside the JDK.

## 5. Basic dependency analysis

Run:

~~~powershell
jdeps app.jar
~~~

By default, the command displays dependency relationships at the package level. The output may look like:

~~~text
app.jar -> dependency.jar
app.jar -> java.base
app.jar -> java.net.http
app.jar -> java.sql
demo -> dep.api
demo -> java.net.http
demo -> java.sql
~~~

The exact output depends on the classpath, the JDK, and the referenced packages. If `dependency.jar` is not passed on the classpath, jdeps may report a package as not found instead of showing the relationship to that JAR.

Specify the classpath:

~~~powershell
jdeps --class-path dependency.jar app.jar
~~~

`--class-path` also has the aliases `-cp` and `-classpath`. Use it when analyzing non-modular JARs or when you need to supply the libraries referenced by class files.

## 6. Distinguishing classpath and module path

The classpath contains traditional classes and JARs. The module path contains modules that can be identified via a module descriptor or the automatic module mechanism.

| Option | When to use |
|---|---|
| `--class-path` | Analyzing classes/JARs on the classpath |
| `--module-path` | Analyzing named modules and the module graph |
| `--module` | Specifying the root module to analyze |
| `--upgrade-module-path` | Providing replacement modules for system modules during module resolution |
| `--system` | Specifying a different system module image for analysis |

A classpath can contain multiple entries. On Windows, the separator is typically a semicolon `;`; on Linux/macOS, it is a colon `:`.

Windows example:

~~~powershell
jdeps --class-path "lib\alpha.jar;lib\beta.jar" app.jar
~~~

Linux/macOS example:

~~~bash
jdeps --class-path "lib/alpha.jar:lib/beta.jar" app.jar
~~~

You can use JAR wildcards according to Java's classpath rules, such as `lib/*`; quote the entire value so the shell does not expand wildcard characters unexpectedly.

Do not place a JAR on the module path just because it has a `.jar` extension. First determine whether the JAR has a `module-info.class`, is an automatic module, or is simply a classpath library. Placing it on the wrong path can make the analysis results differ from how the application is actually launched.

## 7. Viewing dependencies at the package or class level

Common levels of detail:

~~~powershell
jdeps -summary app.jar
jdeps -verbose:package --class-path dependency.jar app.jar
jdeps -verbose:class --class-path dependency.jar app.jar
jdeps -v --class-path dependency.jar app.jar
~~~

Meaning:

- `-summary` or `-s`: displays only a dependency summary.
- `-verbose:package`: displays dependencies at the package level.
- `-verbose:class`: displays dependencies at the class level.
- `-v`: verbose mode, equivalent to class-level and disables default dependency filtering.

Use summary when you need a quick report for a JAR. Use package-level to understand the architecture between packages. Use class-level to pinpoint the exact class creating an unwanted dependency.

By default, jdeps filters out certain dependencies within the same package or archive to keep the output shorter. You can use `-filter:none` to display relationships that are normally filtered:

~~~powershell
jdeps -verbose:class -filter:none app.jar
~~~

## 8. Analyzing transitive dependencies and filtering results

`-R` or `--recursive` instructs jdeps to follow transitive runtime dependencies. `--no-recursive` analyzes only direct dependencies.

~~~powershell
jdeps --recursive --class-path "lib/*" app.jar
~~~

Filter by package:

~~~powershell
jdeps --package java.sql app.jar
~~~

Filter by regular expression:

~~~powershell
jdeps --regex "java\..*" app.jar
~~~

Filter by module:

~~~powershell
jdeps --require java.sql app.jar
~~~

Filter classes to analyze using `--include`:

~~~powershell
jdeps --include "demo\..*" -verbose:class app.jar
~~~

`--package`, `--regex`, and `--require` are dependency filters, not input file filters. `--include` restricts which classes are analyzed. Read the help output of the jdeps version in use to confirm valid option combinations; some modes like `--jdk-internals` and `--missing-deps` have specific restrictions on filters.

## 9. Viewing JDK module dependencies

To see which JDK modules an application requires, use:

~~~powershell
jdeps --list-deps --class-path dependency.jar app.jar
~~~

With the sample JAR created earlier, actual output on JDK 24.0.2:

~~~text
java.base
java.net.http
java.sql
~~~

`--list-deps` lists module dependencies and can transitively analyze libraries on the classpath/module path if they are referenced. Use `--no-recursive` when you only want to see non-transitive dependencies.

To get a comma-separated list of modules:

~~~powershell
jdeps --print-module-deps --class-path dependency.jar app.jar
~~~

Actual output:

~~~text
java.base,java.net.http,java.sql
~~~

`--print-module-deps` prints a reduced module dependency list. This list can be used as input to `jlink --add-modules` when creating a custom runtime image, but you should also verify service bindings, reflection, native libraries, and runtime configuration of the application before releasing a minimal image.

Related options:

- `--list-deps`: lists module dependencies.
- `--list-reduced-deps`: omits edges implied by `requires transitive` relationships.
- `--print-module-deps`: prints a reduced, comma-separated list of modules.
- `--add-modules`: adds root modules to the analysis set.

## 10. Detecting missing dependencies with --missing-deps

When a class references a type that is not present on the classpath/module path, jdeps can report the missing dependency.

With the example above, running without providing `dependency.jar`:

~~~powershell
jdeps --missing-deps app.jar
~~~

Actual output:

~~~text
app.jar -> not found
   demo.App -> dep.api.Marker not found
~~~

Providing the dependency:

~~~powershell
jdeps --missing-deps --class-path dependency.jar app.jar
~~~

When the dependency is resolved, the command prints no missing dependencies.

An important detail for CI: jdeps may return exit code `0` even when `--missing-deps` prints not-found dependencies. Therefore, if your build policy requires zero missing dependencies, the pipeline must inspect the output content or use a check step with explicit failure rules. Do not rely solely on the exit code.

Do not use `--ignore-missing-deps` to hide dependency errors in normal builds. This option is only useful when intentionally analyzing a partial artifact and it is already known that certain dependencies are absent from the analysis set. Document the reason clearly when using it.

`--missing-deps` has restrictions with certain filters such as package, regex, and summary. Check `jdeps --help` before combining options.

## 11. Finding JDK internal APIs with --jdk-internals

JDK internal APIs are internal packages/classes that are not guaranteed to be compatible like the public Java SE API. Depending on them can cause an application to break when upgrading the JDK, due to module encapsulation, implementation changes, or API removal.

Example source intentionally using `sun.misc.Unsafe`:

~~~java
package demo;

import sun.misc.Unsafe;

public final class UnsafeUse {
    private static Unsafe unsafe;

    public static void main(String[] args) {
        System.out.println(unsafe == null);
    }
}
~~~

Compiling on a JDK that provides this API may emit warnings about proprietary/internal APIs. Then package the class into `unsafe.jar` and run:

~~~powershell
jdeps --jdk-internals unsafe.jar
~~~

Illustrative output from JDK 24.0.2:

~~~text
unsafe.jar -> jdk.unsupported
   demo.UnsafeUse -> sun.misc.Unsafe JDK internal API (jdk.unsupported)
~~~

jdeps also warns that JDK internal APIs are unsupported and may be modified or removed. `sun.misc.Unsafe` is associated with the `jdk.unsupported` module; the fact that the class still compiles or the module exists does not mean this API is a stable contract.

Some replacement directions depending on the use case:

- Use `VarHandle` for variable and memory access operations with standardized semantics.
- Use `java.lang.invoke` for method handles and dynamic invocation.
- Use `ByteBuffer` or standard APIs for buffer operations.
- Use standard concurrency/atomic APIs instead of internal primitives where appropriate.

There is no single replacement for every use of `Unsafe`. Analyze the actual operation and choose the appropriate public API.

`--jdk-internals` is a specialized mode; according to JDK 24 help, it cannot be used together with `-p`, `-e`, or `-s`. It analyzes classes in the input and classpath unless restricted with `-include`. For CI, inspect the output as well, because the tool may print warnings while still returning exit code `0`.

## 12. Analyzing public APIs with --api-only

`--api-only` restricts analysis to dependencies that appear in the public/protected API of public classes, for example:

- Public/protected field types.
- Method parameter types.
- Return types.
- Declared checked exceptions.
- Other types appearing in public signatures.

~~~powershell
jdeps --api-only -verbose:class app.jar
~~~

This mode is useful when designing a library or module API: which dependencies become part of the public contract? A dependency used only inside an implementation may have different implications than one exposed in a public signature.

`--api-only` is not a full API compatibility check. It only narrows the scope of static dependencies examined; combine it with compiler/API checks, Javadoc, module reviews, and compatibility tests.

## 13. Generating dependency graphs with DOT

To save the dependency graph:

~~~powershell
jdeps --dot-output reports\jdeps app.jar
~~~

jdeps creates DOT files in the target directory. For the sample JAR, the generated files include:

~~~text
app.jar.dot
summary.dot
~~~

You can use Graphviz to render them:

~~~powershell
dot -Tpng reports\jdeps\summary.dot -o reports\jdeps\summary.png
~~~

The diagram helps visualize how packages/modules connect, spot mutually dependent package clusters, and identify unexpected dependencies. For multi-module projects, use the graph to discuss architecture and find ways to split modules.

DOT is only a representation of static analysis results. If the graph is too large, filter packages/classes or analyze module by module before rendering to keep the diagram readable.

## 14. Analyzing modules and JPMS

The Java Platform Module System describes dependencies explicitly in `module-info.java`. A module declares the modules it needs to read with `requires`, public packages with `exports`, and services with `uses`/`provides`.

A simple module descriptor:

~~~java
module com.example.app {
    requires java.sql;
    requires java.net.http;
    exports com.example.app.api;
}
~~~

Analyze a module on the module path:

~~~powershell
jdeps --module-path mods --module com.example.app
~~~

`--module` specifies the root module to analyze. The module path must contain the modules that the tool needs to resolve.

Use `--check` to inspect the module descriptor and dependency graph after analysis:

~~~powershell
jdeps --check com.example.app --module-path mods
~~~

This option helps detect module dependencies, the graph after removing implied edges, and certain unused qualified exports. Read the output alongside `module-info.java` and the module path configuration to understand why a module is required.

## 15. Generating module-info.java for non-modular JARs

For traditional JARs without `module-info.class`, jdeps can suggest a module descriptor:

~~~powershell
jdeps --generate-module-info generated-modules dependency.jar
~~~

For libraries that need an open module:

~~~powershell
jdeps --generate-open-module generated-modules dependency.jar
~~~

The tool generates `module-info.java` in the target directory based on the static dependencies it detects. This is a starting point for migrating a library to JPMS, not a production-ready descriptor.

Before using the generated descriptor, review:

- Whether the module name is stable and follows naming conventions.
- Which packages need `exports`.
- Which dependencies need `requires transitive`.
- Whether there are split packages across JARs.
- Whether service providers need `uses` or `provides`.
- Whether frameworks using reflection need `opens`.
- Whether the public API makes a dependency part of the contract.
- Whether the module depends on JDK internal APIs.

`--generate-module-info` and `--generate-open-module` have restrictions when combined with certain options, such as `--dot-output` and `--class-path`. Check the help output of your current JDK before combining multiple modes.

## 16. Analyzing multi-release JARs

A multi-release JAR can contain multiple versions of classes in the same archive, such as base classes and specific implementations in `META-INF/versions/17/`.

Use `--multi-release` to select the version to analyze:

~~~powershell
jdeps --multi-release 17 --list-deps library.jar
~~~

You can specify `base` to analyze the base classes:

~~~powershell
jdeps --multi-release base library.jar
~~~

The specified version must be `base` or an integer greater than or equal to `9`. If a library has different implementations per Java release, analysis results may differ by version. You must select the product's actual target runtime.

Do not analyze a multi-release JAR without recording the version used if the results are stored as release evidence.

## 17. Finding reverse dependencies with --inverse

Normally jdeps shows what an artifact depends on. `--inverse` answers the reverse question: which artifacts directly or indirectly depend on the package/module/class of interest?

Example:

~~~powershell
jdeps --inverse --require java.sql --recursive app.jar
~~~

Or find reverse dependencies by package:

~~~powershell
jdeps --inverse --package sun.misc --recursive "lib/*"
~~~

`--inverse` must be paired with an appropriate filter such as `--require`, `--package`, or `--regex`. Use it when you need to find which modules would be affected if a dependency is removed or changed.

## 18. Automating checks in CI

A pipeline can run the following steps after packaging:

~~~bash
jdeps --version
jdeps -summary app.jar
jdeps --list-deps --class-path 'lib/*' app.jar
jdeps --missing-deps --class-path 'lib/*' app.jar
jdeps --jdk-internals --class-path 'lib/*' app.jar
~~~

For strict policies, capture the output and inspect its content:

~~~bash
missing="$(jdeps --missing-deps --class-path 'lib/*' app.jar 2>&1)"
if [[ -n "$missing" ]]; then
  printf '%s\n' "$missing" >&2
  exit 1
fi

internals="$(jdeps --jdk-internals --class-path 'lib/*' app.jar 2>&1)"
if [[ -n "$internals" ]]; then
  printf '%s\n' "$internals" >&2
  exit 1
fi
~~~

The example above treats any output from those two modes as requiring review. For projects with approved exceptions, replace this with an explicit parser/policy and an allowlist with an owner; do not filter by ignoring all output.

PowerShell can capture output and check similarly:

~~~powershell
$missing = & jdeps --missing-deps --class-path 'lib/*' app.jar 2>&1
if ($missing) {
    $missing
    throw 'Missing dependencies detected by jdeps.'
}

$internals = & jdeps --jdk-internals --class-path 'lib/*' app.jar 2>&1
if ($internals) {
    $internals
    throw 'JDK internal API references detected by jdeps.'
}
~~~

With PowerShell, run in the appropriate artifact directory and check `$LASTEXITCODE` after native commands when needed. The examples above inspect diagnostic content; log both the output and exit code to distinguish jdeps execution errors from analysis results with warnings.

Do not run `--jdk-internals` on every JDK library or a huge entire classpath if you only want to evaluate the application's own artifact. Scope the input and classpath appropriately so the output remains easy to review.

## 19. Limitations of static analysis

jdeps only sees dependencies it can infer from class files and metadata. Several cases require additional verification:

- Reflection with class names constructed from strings.
- `Class.forName()` with values retrieved from configuration or a database.
- Service loading and plugins discovered at runtime.
- Dependencies dynamically loaded from a URL or external directory.
- JNI/native libraries and native configuration files.
- Bytecode generated or transformed at runtime.
- Code paths executed only under production data or feature flags.
- Modules/packages opened via command-line flags.
- Dependencies added by containers, application servers, or frameworks.

Therefore, having no dependencies listed by jdeps does not mean the application needs no runtime dependencies. Verify deployment configurations, service descriptors, reflection configurations, integration tests, and smoke tests.

jdeps also does not evaluate licenses, CVEs, dependency quality, performance, or business correctness. Use dedicated tools for those requirements.

## 20. Common errors when running jdeps

| Symptom | Common Cause | Resolution |
|---|---|---|
| `not found` | Missing JAR on classpath/module path | Add the right dependency and re-run |
| Transitive dependencies not shown | Recursive analysis not enabled | Use `-R`/`--recursive` |
| Output too long | Viewing class-level or unfiltered output | Use `-summary`, a package filter, or `--include` |
| Cannot resolve module | Module path missing a module or invalid descriptor | Check `--module-path`, module name, and `module-info` |
| `--jdk-internals` reports internal API | Source/dependency uses JDK internal APIs | Find a standard replacement API or isolate the exception |
| No output from `--missing-deps` | No missing dependencies detected in analyzed scope | Verify classpath and input scope |
| Dynamically loaded classes not visible | Dependency only appears via reflection/config | Add runtime and configuration checks |
| Different multi-release results | Analyzing a different version | Specify the appropriate `--multi-release` |
| New JAR cannot be analyzed | jdeps is too old for the new class-file version | Use jdeps from a compatible JDK |
| DOT graph too large | Too many classes/packages | Filter by package/module or analyze per artifact |

If jdeps reports missing dependencies while the exit code is still `0`, inspect the diagnostic output. Do not treat exit code `0` as the sole proof of a complete dependency graph.

## 21. Workflow for analyzing an artifact before release

A workflow that can be used in a pull request or release review:

1. Build the artifact from clean source.
2. Record the JDK, jdeps, Maven/Gradle, and dependency versions.
3. Run `-summary` for an overview.
4. Run `-verbose:package` or `-verbose:class` when tracing is needed.
5. Run `--missing-deps` with the proper classpath/module path.
6. Run `--jdk-internals` on the application artifact.
7. Run `--list-deps` and `--print-module-deps` if a module inventory is needed.
8. If migrating to JPMS, inspect the module graph and review the suggested module descriptor.
9. If using a multi-release JAR, specify the release to analyze.
10. Run unit/integration/smoke tests on the minimum supported runtime.
11. Save the report, commands, tool versions, and warning handling decisions.
12. Re-review the results when upgrading the JDK or major dependencies.

Each report should be tied to a specific commit/artifact. If you only save a `jdeps.txt` file without versions, commands, and commit info, it is difficult for others to know which build the report still represents.

## 22. jdeps checklist

- [ ] Identified the artifact or class directory to analyze.
- [ ] jdeps version is compatible with the input class-file version.
- [ ] Provided a complete classpath/module path.
- [ ] Checked `-summary` before diving into detailed analysis.
- [ ] Chose package-level or class-level appropriately for the goal.
- [ ] Used recursive analysis when transitive dependencies are needed.
- [ ] Checked missing dependencies and diagnostic output.
- [ ] Checked for JDK internal APIs.
- [ ] Reviewed module dependencies if building a runtime image.
- [ ] Reviewed auto-generated `module-info.java` before using it.
- [ ] Specified multi-release version if analyzing a multi-release JAR.
- [ ] Understood limitations with reflection, service loading, and JNI.
- [ ] Combined jdeps with build/test/runtime verification.
- [ ] Saved commands, versions, artifacts, and reports in CI.

jdeps makes a Java application's static dependencies visible, finds JDK internal APIs, detects missing references, and assists in module design. Results are only reliable when analyzing the right artifact with the proper classpath/module path and target release. Use jdeps as a verification layer in build/release, then confirm dynamic dependencies and actual behavior with tests on the supported runtime.

## References

- Oracle Java SE 24 — The jdeps Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeps.html
- Oracle Java SE 17 — The jdeps Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html
- Oracle Java SE 24 — The jar Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html
- Oracle Java SE 24 — The jlink Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jlink.html
- Oracle — JDK Internal APIs and JEP 260: https://openjdk.org/jeps/260
- Oracle Java Platform Module System — Module Dependences: https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html
