# Class-Level Dependency Analysis with jdeps

`jdeps` is a dependency analysis tool included with the JDK. It reads class files, class directories, or JARs to identify which classes, packages, or modules bytecode references. When you need to see which class depends on which class, the key option is `-verbose:class`.

Class-level dependency analysis helps trace relationships between classes in an application, detect unexpected dependencies, find unresolved classes, and understand why a library is required on the classpath or module path. The output is static analysis data from bytecode; `jdeps` does not run the program and does not generate a method-level call graph.

## 1. What is a Class Dependency?

A class has a dependency on another class when its bytecode references a type or member belonging to that class. For example, class `Main` instantiates `GreetingService`, calls its method, and uses `String`. These references can appear in the constant pool, descriptors, superclass, interfaces, annotations, or other class file structures.

Example relationship among three classes:

~~~text
com.acme.app.Main
        |
        v
com.acme.service.GreetingService
        |
        v
com.acme.util.TextFormatter
~~~

In the example above, `Main` depends on `GreetingService`; `GreetingService` depends on `TextFormatter`. This is a class-level relationship. It indicates that one class references another, not the full call chain, call order, or call count at runtime.

It is important to distinguish:

- **Class dependency**: reference relationship between classes.
- **Package dependency**: relationship between packages containing classes.
- **Module dependency**: module-level relationship, typically associated with the Java Platform Module System (JPMS).
- **Call graph**: method call relationship; `jdeps` is not a full call-graph generator.

Imports in source code are not an accurate dependency report. An unused import may not produce a reference in bytecode; conversely, code can use a fully qualified class name without an import statement. `jdeps` analyzes compiled class files, so its results reflect references in the artifact.

## 2. Installing and Checking jdeps

`jdeps` is a JDK tool. Check the active JDK and the tool version:

~~~sh
java -version
jdeps --version
jdeps --help
~~~

If the shell cannot find `jdeps`, check whether the JDK `bin` directory is in your PATH. `jdeps` usually sits alongside `java`, `javac`, and `javap` in the JDK directory.

On Windows PowerShell, you can check the tool path:

~~~powershell
Get-Command jdeps
jdeps --version
~~~

On macOS/Linux:

~~~sh
command -v jdeps
jdeps --version
~~~

Use `jdeps` from the JDK matching the build or runtime environment you want to analyze. The tool version can affect its support for class-file versions, modules, and newer options.

## 3. Viewing Class-Level Dependencies with -verbose:class

Basic syntax:

~~~sh
jdeps -verbose:class path/to/classes
~~~

For a directory containing class files:

~~~sh
jdeps -verbose:class -filter:none build/classes
~~~

For a JAR:

~~~sh
jdeps -verbose:class -filter:none app.jar
~~~

`-verbose:class` requests class-level dependency output. `-filter:none` disables dependency filtering so the output does not omit edges under the default filter. This is useful when you want to inspect all relationships between classes within the same package or archive.

The output format typically has the structure:

~~~text
source.class -> target.class module-or-archive
~~~

Illustrative example:

~~~text
com.acme.app.Main -> com.acme.service.GreetingService build/classes
com.acme.service.GreetingService -> com.acme.util.TextFormatter build/classes
com.acme.app.Main -> java.io.PrintStream java.base
~~~

The archive name or module label in the last column depends on the artifact and JDK version. Actual output also depends on the compiled source, classpath, module path, and filters. Do not rely on a fixed output string when writing scripts; interpret the output by the meaning of its columns.

## 4. Complete Example with Multiple Classes

Create the source structure:

~~~text
src/
└── com/acme/
    ├── app/
    │   └── Main.java
    ├── service/
    │   └── GreetingService.java
    └── util/
        └── TextFormatter.java
~~~

`TextFormatter.java`:

~~~java
package com.acme.util;

public class TextFormatter {
    public String format(String name) {
        return "Hello, " + name + " dependencies!";
    }
}
~~~

`GreetingService.java`:

~~~java
package com.acme.service;

import com.acme.util.TextFormatter;

public class GreetingService {
    private final TextFormatter formatter = new TextFormatter();

    public String greet(String name) {
        return formatter.format(name);
    }
}
~~~

`Main.java`:

~~~java
package com.acme.app;

import com.acme.service.GreetingService;

public class Main {
    public static void main(String[] args) {
        GreetingService service = new GreetingService();
        System.out.println(service.greet("Java"));
    }
}
~~~

Compile the classes into the output directory:

~~~sh
mkdir -p build/classes
javac -d build/classes \
  src/com/acme/util/TextFormatter.java \
  src/com/acme/service/GreetingService.java \
  src/com/acme/app/Main.java
~~~

On Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/classes | Out-Null
javac -d build/classes src/com/acme/util/TextFormatter.java src/com/acme/service/GreetingService.java src/com/acme/app/Main.java
~~~

Run the application:

~~~sh
java -cp build/classes com.acme.app.Main
~~~

Stdout output:

~~~text
Hello, Java dependencies!
~~~

Analyze the classes:

~~~sh
jdeps -verbose:class -filter:none build/classes
~~~

You will see the main relationships between `com.acme.app.Main`, `com.acme.service.GreetingService`, and `com.acme.util.TextFormatter`. In addition to application classes, the output may include references to Java SE classes such as `java.lang.String`, `java.lang.System`, or `java.io.PrintStream`.

The command to run the application only needs the classpath root `build/classes`. Do not point the classpath directly to a package subdirectory if you want to use fully qualified class names.

## 5. Analyzing JARs and External Dependencies

`jdeps` can analyze packaged JARs:

~~~sh
jdeps -verbose:class -filter:none app.jar
~~~

If the JAR references classes from other libraries, provide those dependencies so the tool can resolve them:

~~~sh
jdeps -verbose:class --class-path "lib/alpha.jar:lib/beta.jar" app.jar
~~~

On Windows, the classpath separator is a semicolon:

~~~powershell
jdeps -verbose:class --class-path "lib\alpha.jar;lib\beta.jar" app.jar
~~~

On macOS/Linux, the separator is a colon. If a dependency is missing, the output may mark it as `not found` or report a warning depending on the situation. Add the appropriate JAR to the analysis classpath and re-run to verify whether the dependency can be resolved.

A JAR can contain many packages and classes. `-verbose:class` helps pinpoint the exact class making a reference to another class, which is more useful than a package-level report when tracing a direct dependency.

Make sure you inspect the right artifact. A class in the build directory may differ from a class with the same name in an older JAR. If the results do not match the current source, verify the JAR/directory path, build output, and classpath that the tool is reading.

## 6. Filters and Detail Levels

`jdeps` provides different reporting levels:

| Option | Output |
|---|---|
| `-summary` or `-s` | Summarizes dependencies instead of listing every class edge |
| `-verbose:package` | Package-level dependencies |
| `-verbose:class` | Class-level dependencies |
| `-verbose` | Verbose class mode; usually combined with an appropriate filter |
| `-filter:none` | Applies no dependency filter |
| `-filter:package` | Filters out dependencies within the same package |
| `-filter:archive` | Filters out dependencies within the same archive |

For example, compare package-level and class-level dependencies:

~~~sh
jdeps -verbose:package app.jar
jdeps -verbose:class -filter:none app.jar
~~~

Package reports are suited for viewing overall architecture. Class reports are suited when you need to know the exact source and target classes of each relationship.

Filters only change which edges are displayed; they do not modify bytecode or remove dependencies from the artifact. For a comprehensive check, re-run with `-filter:none` before concluding that no dependencies exist.

## 7. Recursive Analysis and Missing Dependencies

By default, `jdeps` reports dependencies of the specified target. The `-R` or `--recursive` option instructs the tool to traverse resolved dependencies as well, which is useful when you want to inspect the dependency chain more deeply:

~~~sh
jdeps -R -verbose:class -filter:none --class-path "lib/*" app.jar
~~~

Recursive analysis can produce a large volume of output because the tool follows external dependencies. Use it when you genuinely need to understand an extended dependency chain; for a direct error, starting with non-recursive class-level analysis is usually easier to read.

You can request a report of missing dependencies:

~~~sh
jdeps --missing-deps --class-path "lib/*" app.jar
~~~

The output helps identify classes referenced by the application's dependencies that cannot be found in the provided inputs and classpath. If you need to continue analysis despite unresolved dependencies, `--ignore-missing-deps` can ignore missing errors in certain operations. Ignoring them does not fix the dependency and does not prove the application can run.

When encountering a missing dependency, check:

1. Whether the JAR was actually built or downloaded.
2. Whether the classpath points to the correct file location.
3. Whether that JAR version contains the class required by bytecode.
4. Whether the class belongs to an optional dependency, profile, or separate module.
5. Whether the dependency is provided at runtime by a container or application server.

## 8. Dependencies on the Module Path

For modular Java applications, classes are organized into modules with a `module-info.java` declaration. When analyzing modules, provide the module path instead of only the classpath:

~~~sh
jdeps --module-path mods -verbose:class app.jar
~~~

To view the list of modules the application depends on:

~~~sh
jdeps --print-module-deps --module-path mods app.jar
~~~

`--module-path` tells `jdeps` where to find dependent modules. `--print-module-deps` prints the list of required modules according to the tool's analysis, commonly used when preparing a runtime image configuration with `jlink`.

A module can contain many classes. Module reports are useful for runtime configuration and module boundaries; `-verbose:class` reports are useful when tracing specific classes inside a module.

## 9. Detecting Dependencies on JDK Internal APIs

You can check whether classes or a JAR reference JDK internal APIs:

~~~sh
jdeps --jdk-internals app.jar
~~~

The output can highlight classes using internal packages such as `sun.*` or `com.sun.*` that are not guaranteed public Java SE APIs. These APIs may change or be encapsulated across JDK versions.

If the tool reports internal API dependencies:

- Find a public API provided by Java SE or a supported library.
- Check the migration guide for the JDK version in use.
- Update outdated dependencies if a third-party library relies on internal APIs.
- Do not use `--add-exports` as a default long-term solution; only consider it when you understand the risks and have a removal plan.

## 10. Limitations of Static Analysis

`jdeps` analyzes references that can be found in class files. It does not observe full runtime behavior. Some dependencies may not appear explicitly in bytecode:

- **Reflection**: the application constructs class names as strings and calls `Class.forName`.
- **Service loading**: providers are declared in metadata or configuration and loaded dynamically.
- **Configuration/resources**: XML, JSON, properties files, or scripts contain class names or library names.
- **JNI/native libraries**: Java code loads native libraries or calls native code that depends on external components.
- **Dependency injection/frameworks**: frameworks scan the classpath and instantiate objects based on annotations or configuration.
- **Custom class loading**: classloaders fetch bytecode from the network, databases, plugin directories, or dynamic sources.

Therefore, `jdeps` does not replace integration testing, runtime checks, or application dependency documentation. When a system uses reflection, plugins, or service providers, cross-check the analysis results with configuration and actual runtime scenarios.

The tool also does not tell you which classes are guaranteed to execute in a given run. A reference in bytecode does not mean that path is always called; conversely, dynamically loaded classes may not appear in the static report.

## 11. Common Errors and Troubleshooting

| Symptom | Common Cause | Resolution |
|---|---|---|
| `jdeps: command not found` | JDK is not installed or PATH is missing JDK bin | Check `JAVA_HOME`, PATH, and `jdeps --version` |
| `not found` in report | Missing dependency or incorrect classpath | Add the right JAR to `--class-path` and re-run |
| Missing edge between two classes in the same package | Filter hides intra-package or intra-archive dependencies | Re-run with `-filter:none` |
| Report only shows packages | Using `-verbose:package` or summary mode | Use `-verbose:class` |
| Output is too long | Recursive analysis or archive with many dependencies | Drop `-R`, narrow the input, or use summary |
| Dependency loaded via reflection is missing | Reference is not in bytecode in a form `jdeps` detects | Check configuration, service metadata, and runtime logs |
| Report differs from current source | Analyzing an old class/JAR or wrong build output | Verify artifact path, clean/rebuild, and re-analyze |
| Module dependency not resolved | Missing module path or wrong module selected | Provide `--module-path` and verify module names |

## 12. Class Dependency Analysis Workflow

When you need to find which class depends on which class, follow this order:

1. Identify the artifact to analyze: class directory, class file, or JAR.
2. Check the tool version with `jdeps --version`.
3. Start with `jdeps -verbose:class -filter:none` on the artifact.
4. Add `--class-path` or `--module-path` to resolve external dependencies.
5. Use `--missing-deps` to find unresolved classes.
6. Enable `-R` only when you need to trace transitive dependencies.
7. Use `--jdk-internals` to check for references to JDK internal APIs.
8. Cross-check results against reflection config, service loading, resources, and runtime tests.
9. Record required dependencies in build and deployment setups so the artifact runs in the target environment.

### Checklist

- [ ] Selected the right class directory or JAR.
- [ ] Used `-verbose:class` to view class-level relationships.
- [ ] Understood filter behavior; used `-filter:none` when all edges are needed.
- [ ] Provided classpath/module path for external dependencies.
- [ ] Checked for missing dependencies if warnings appeared.
- [ ] Used `-R` only when recursive analysis was needed.
- [ ] Checked JDK internal APIs when necessary.
- [ ] Accounted for reflection, service loading, and dynamic runtime dependencies.
- [ ] Verified that the analyzed artifact is the latest build.

`jdeps -verbose:class` shows which source class references which target class in bytecode. Combining the right classpath, filters, and missing-dependency checks helps you trace a Java application's dependency structure while recognizing the limits of static analysis before drawing runtime conclusions.