# The javac -Werror Option

`-Werror` is an option for the Java compiler `javac`. When enabled, if compilation produces any warnings, `javac` exits with a failure status. This allows development teams to prevent new source code from introducing warnings into a project and makes the CI build pipeline enforce stricter quality checks.

`-Werror` itself does not generate warnings. It changes how the compiler handles warnings that have already been detected. To control which types of warnings are detected, `-Werror` is commonly combined with `-Xlint` options.

## 1. Distinguishing Warnings and Errors

During compilation, `javac` can detect several kinds of issues:

- **Error:** an issue that prevents source code from compiling successfully, such as invalid syntax or referencing a nonexistent method.
- **Warning:** a noteworthy issue that does not necessarily prevent the program from compiling, such as using raw types, unsafe generic operations, or calling a deprecated API.
- **Note:** additional compiler information; a note is not always a warning.

Without `-Werror`, some warnings still allow `javac` to compile successfully and generate bytecode. With `-Werror`, if any warning occurs, the compilation is treated as failed and returns a non-zero exit code.

This is useful in automation: CI can mark a build as failed instead of letting new warnings pass through unhandled.

## 2. Syntax and Combining Options

Basic syntax:

```bash
javac -Werror ClassName.java
```

In practice, it should be combined with `-Xlint` to enable the warning categories you want to check.

| Option | Purpose |
| --- | --- |
| `-Werror` | Fail compilation if any warning is generated |
| `-Xlint` | Enable additional warning categories supported by the compiler |
| `-Xlint:all` | Enable recommended warning categories |
| `-Xlint:unchecked` | Show detailed warnings about unchecked operations |
| `-Xlint:deprecation` | Show detailed warnings when using deprecated APIs |
| `-Xlint:rawtypes` | Warn when using generic types as raw types |

Example:

```bash
javac -Xlint:all -Werror Main.java
```

This command instructs the compiler to enable the recommended warning categories and treat any generated warning as a build error.

**Note:** `-Werror` does not automatically enable all warning categories. If you only use `-Werror`, warnings that the compiler does not detect or has not enabled may still not appear. Therefore, the standard policy is to combine it with an appropriate `-Xlint` set.

## 3. Example: Generating a Warning with a Raw Type

A common cause of warnings is using a collection without declaring its element type (a raw type).

Create the file **`WarningDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class WarningDemo {
    public static void main(String[] args) {
        List values = new ArrayList();
        values.add("Java");

        System.out.println(values.get(0));
    }
}
```

In this example, `List` and `ArrayList` are used without specifying an element type. As a result, the `add()` call can produce an unchecked warning.

Compile with unchecked warnings enabled:

```bash
javac -Xlint:unchecked WarningDemo.java
```

The compiler will display a warning pointing to the unchecked operation on the line that adds the element. The exact wording and line number depend on the JDK version.

Run the program:

```bash
java WarningDemo
```

Output:

```text
Java
```

The program can still run correctly in this small example, but raw types lose compile-time type checking and can lead to casting errors as the program grows.

## 4. Using -Werror to Block Warnings

Try compiling the same file with:

```bash
javac -Xlint:unchecked -Werror WarningDemo.java
```

Because the source code produces an unchecked warning, `javac` terminates the compilation with a failure status. The message typically indicates that warnings were found and `-Werror` was specified. Exact diagnostic wording may vary by JDK.

Key points:

- No warnings: `-Werror` alone does not cause compilation to fail.
- Warnings detected: compilation fails.
- Warnings still need to be fixed at the root cause or handled with an intentional suppression.
- `-Werror` applies to warnings detected by the compiler during compilation; it does not automatically turn every message from every build tool into an error.

## 5. Fixing Warnings with Generic Types

The best fix in the example above is to declare the element type for the collection.

Replace the contents of `WarningDemo.java` with:

```java
import java.util.ArrayList;
import java.util.List;

public class WarningDemo {
    public static void main(String[] args) {
        List<String> values = new ArrayList<>();
        values.add("Java");

        System.out.println(values.get(0));
    }
}
```

Compile with a stricter policy:

```bash
javac -Xlint:all -Werror WarningDemo.java
java WarningDemo
```

Output:

```text
Java
```

With the `List<String>` declaration, the compiler knows the collection only accepts strings and can perform safer type checking. The example no longer has a raw type or the corresponding unchecked warning.

This is the preferred approach: fix the root cause of the warning rather than disabling warnings just to let the build pass.

## 6. Using -Werror with Other Warning Categories

Besides unchecked warnings, `javac` can detect many other issues.

### Deprecated APIs

An API marked with `@Deprecated` may still exist and compile, but developers are informed that it is no longer recommended for use.

Use:

```bash
javac -Xlint:deprecation -Werror Main.java
```

If the source code uses a deprecated API and the compiler emits the corresponding warning, compilation will fail. Consult the API documentation to find the replacement method or class.

### Raw Types

Use:

```bash
javac -Xlint:rawtypes -Werror Main.java
```

This warning helps detect declarations like `List`, `Map`, or `Set` without type parameters. For Java code using generics, explicitly declare the element type or key/value types.

### Enabling Multiple Warning Categories

Use:

```bash
javac -Xlint:all -Werror Main.java
```

This approach suits projects that want to enforce a broad warning policy. Before enabling it across an entire legacy codebase, run a trial build to see the number and types of existing warnings.

## 7. When Should You Use -Werror?

`-Werror` is especially useful in the following scenarios:

- **CI/CD:** prevents a build from succeeding when source code produces warnings disallowed by project policy.
- **New projects:** establishes quality standards from the start so warnings are addressed as soon as they appear.
- **Shared libraries:** catches deprecated APIs, unsafe generics, and issues that could affect library consumers early.
- **Code review:** helps the team focus on resolving warnings before merging changes.
- **JDK upgrades:** surfaces new warnings added or changed by a newer compiler version.

For legacy codebases with many existing warnings, enabling `-Werror` immediately can cause widespread build failures. Inventory existing warnings, fix them by category, and enable the strict policy once the baseline is clean.

## 8. Integration with Maven

If your project uses the Maven Compiler Plugin, you can pass compiler options via the plugin configuration in `pom.xml`.

Example:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <compilerArgs>
                    <arg>-Xlint:all</arg>
                    <arg>-Werror</arg>
                </compilerArgs>
            </configuration>
        </plugin>
    </plugins>
</build>
```

When running:

```bash
mvn clean compile
```

Maven passes these options to the compiler when compiling source code. If the compiler emits a warning, the compile step fails and Maven reports a build failure.

The plugin version in the example is a specific version to illustrate configuration; projects should use a version approved by their organization and compatible with their current Maven/JDK setup.

## 9. Integration with Gradle

With Gradle using the Groovy DSL, you can configure Java compilation tasks:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-Xlint:all', '-Werror']
}
```

With the Kotlin DSL in `build.gradle.kts`:

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.addAll(listOf("-Xlint:all", "-Werror"))
}
```

These examples assume the project has applied the Java plugin so the `JavaCompile` task type is available.

When running:

```bash
./gradlew clean compileJava
```

On Windows:

```powershell
.\gradlew.bat clean compileJava
```

If the compiler emits a warning, the Java compile task will fail. For multi-module projects, standardize the configuration across modules to avoid having one module enforce strict checks while another ignores warnings.

## 10. Handling Intentional Warnings

Not every warning can be eliminated immediately. Some cases have valid technical reasons to be accepted, such as interacting with legacy APIs, external libraries, or backward-compatibility code.

Once you have verified that a warning is acceptable, you can use `@SuppressWarnings` at the smallest possible scope:

```java
@SuppressWarnings("unchecked")
private static void legacyBridge() {
    // Only place exceptions on code that has been verified to be safe.
}
```

This example illustrates annotation scope; in real code, only use the annotation when a specific operation actually produces that exact warning type.

Guidelines:

- Read and understand the cause of the warning before suppressing it.
- Suppress only the exact warning category needed.
- Place the annotation on the narrowest appropriate method, variable, or code block.
- Explain the reason in a comment or documentation when a warning is intentionally unavoidable.
- Do not use `@SuppressWarnings("all")` to hide warnings wholesale.

`-Werror` remains valuable even when a project has carefully reviewed exceptions: all remaining warnings continue to be blocked.

## 11. Considerations When Adopting -Werror

### Warnings Can Change Across JDK Versions

Newer JDK versions may add warnings, change detail levels, or detect cases that older compilers did not report. As a result, a project that builds cleanly with `-Werror` may fail after switching JDKs even if the source code has not changed.

When upgrading the JDK:

1. Run the build with the new JDK in a test environment.
2. Collect and categorize the new warnings.
3. Determine whether warnings originate from project code, generated code, annotation processors, or build tools.
4. Fix the source code or update dependencies/plugins as appropriate.
5. Adjust lint or suppression settings only when there is a clear technical reason.

### Generated Code and Dependencies

Auto-generated source code can emit warnings that the development team did not write directly. Consider how to configure tasks or the compiler for generated code, while avoiding disabling warnings for the entire codebase just because of one problematic directory.

Warnings from already-compiled library code generally differ from warnings in source code being compiled. `-Werror` does not replace dependency management and quality checks for external libraries.

### Do Not Confuse javac Warnings with Runtime Warnings

`-Werror` is an option for the `javac` compiler. It is not a general flag that turns every warning log while an application is running into an error. Logging frameworks, the JVM runtime, Maven, Gradle, and plugins each have their own warning policies.

If you want a build to fail when another tool emits a warning, configure that tool's own policy separately.

## 12. Recommended Adoption Process

A safe process for rolling out `-Werror`:

1. Run `javac -Xlint:all` or the equivalent build tool configuration to collect current warnings.
2. Categorize warnings by root cause and impact.
3. Fix issues in source code: use generics, replace deprecated APIs, fix resource handling, or address other compiler-reported issues.
4. For unavoidable warnings, evaluate and suppress them in a narrow scope with an explanation.
5. Enable `-Werror` in modules that are clean of warnings.
6. Run the full build and test suite in CI.
7. Maintain this policy when updating the JDK, compiler plugins, or dependencies.

For legacy projects, you can roll it out gradually by module or for new source code, then expand as existing warnings are resolved.

## 13. Common Issues

| Symptom | Cause | Solution |
| --- | --- | --- |
| Build fails after adding `-Werror` | The compiler detected at least one warning | Read the first warning and fix its root cause |
| Using `-Werror` but expected warnings still do not appear | The corresponding lint category is not enabled, or the warning is outside javac's scope | Enable the appropriate `-Xlint` option and check which tool emits the warning |
| Upgrading the JDK breaks an existing build | The new compiler emits additional warnings or changes diagnostics | Categorize new warnings and intentionally update code or configuration |
| Using `@SuppressWarnings` but the build still fails | The annotation does not match the warning type or scope | Check the warning key, annotation placement, and compiler message |
| Disabling all lint checks to pass the build | Warnings are hidden and risks go undetected | Re-enable necessary categories and fix warnings group by group |
| Maven/Gradle still reports warnings | Warnings may come from plugins or other tasks, not javac | Identify the exact tool emitting the warning and configure its policy |

## 14. Key Takeaways

- `-Werror` instructs `javac` to exit with a failure status when warnings occur.
- `-Werror` does not automatically enable all warning categories; combine it with `-Xlint` to specify what to check.
- `-Xlint:all -Werror` is a common strict configuration for Java source code.
- Fixing the root cause of a warning is the preferred option; only use `@SuppressWarnings` with a clear reason and narrow scope.
- New warnings can appear when upgrading the JDK, so re-run builds and tests after updates.
- `-Werror` only controls compiler warnings; other tools require their own policies.

Applying `-Werror` alongside appropriate lint checks keeps Java source code free of warnings and lets CI catch issues early for the development team to address.
