# Selecting Sources When Generating Documentation with Javadoc

When running the `javadoc` tool, you need to specify **which Java sources will be included in the API documentation**. This is the source selection step. Javadoc can accept a list of specific `.java` files, package names, a package tree to scan recursively, or a list of modules.

Selecting sources properly ensures that documentation only includes the public API you intend to publish, avoids missing packages, prevents internal code from leaking into public documentation, and makes build commands reproducible.

## 1. Ways to Select Sources

Javadoc supports three common ways to select inputs:

1. **Select specific source files:** pass the paths to `.java` files directly.
2. **Select packages:** pass package names and use `-sourcepath` so Javadoc can locate the source code.
3. **Select a package tree:** use `-subpackages` to scan a root package along with its subpackages.

For projects using the Java Platform Module System (JPMS), you can select modules with `--module-source-path` and `--module`.

General syntax:

```text
javadoc [options] [packagenames] [sourcefiles] [@argfiles]
```

- `options`: options such as output directory, source path, encoding, and visibility level.
- `packagenames`: names of one or more packages to document.
- `sourcefiles`: paths to the source files to document.
- `@argfiles`: files containing a list of arguments to avoid overly long commands.

Source selection determines the scope of classes and packages to be processed. It is independent of member visibility levels such as public, protected, or private.

## 2. Selecting Specific .java Files

When you only want to generate documentation for a few specific classes, pass the source file paths directly.

Example structure:

```text
project/
  src/
    com/
      example/
        math/
          package-info.java
          Calculator.java
          internal/
            BigMath.java
```

Generate documentation for the package comment and the `Calculator` class:

```bash
javadoc -d docs -encoding UTF-8 -sourcepath src src/com/example/math/package-info.java src/com/example/math/Calculator.java
```

Meaning:

- `-d docs`: writes HTML output to the `docs` directory.
- `-encoding UTF-8`: reads source files using UTF-8.
- `-sourcepath src`: allows Javadoc to locate related source files in the `src` directory.
- The last two paths are the explicitly selected source files.

This approach is suitable when:

- You only want to publish part of an API.
- You want to generate documentation for a few standalone classes.
- You are testing a single class or a small group of classes.
- There is internal source code you do not want to include in public documentation.

If you want package documentation, include `package-info.java` in the list when a package description is needed. Do not assume that passing a single class will automatically select all subpackages or all source files in the same directory.

## 3. Selecting Packages by Package Name

Instead of listing individual files, you can pass package names. Javadoc locates the package source files based on the source path.

Example:

```bash
javadoc -d docs -encoding UTF-8 -sourcepath src com.example.math
```

Where:

- `-sourcepath src` specifies the root directory containing the source tree.
- `com.example.math` is the Java package name, using dots to separate components.
- Javadoc locates the source files belonging to the specified package and generates documentation using the default visibility level.

Given the structure:

```text
src/
  com/
    example/
      math/
        package-info.java
        Calculator.java
        internal/
          BigMath.java
```

The package `com.example.math` corresponds to the directory:

```text
src/com/example/math/
```

The package name passed to Javadoc is not a directory path. Use `com.example.math`, not `src/com/example/math`.

Selecting packages directly is suitable when a project has many packages and you only want to document specific ones.

## 4. Selecting a Package and Its Subpackages with -subpackages

If you want to generate documentation for an entire package hierarchy, use `-subpackages`.

Example:

```bash
javadoc -d docs -encoding UTF-8 -sourcepath src -subpackages com.example
```

The command above instructs Javadoc to find the `com.example` package and its subpackages on the source path, for example:

```text
com.example
com.example.math
com.example.math.internal
com.example.app
com.example.persistence
```

Key points to remember:

- `-subpackages` takes a root package name, not a directory path.
- Javadoc scans for subpackages on the source path.
- Only packages found on the source path are processed.
- Selecting a broad root package may cause the documentation to include more APIs than intended.

Use `-subpackages` when you want to document a library with many related packages and want to avoid listing each package manually.

## 5. Excluding Packages with -exclude

When scanning recursively with `-subpackages`, you sometimes need to skip internal or experimental packages. Use `-exclude` to exclude a package and its subpackages from the selected set.

Example:

```bash
javadoc -d docs -encoding UTF-8 -sourcepath src -subpackages com.example -exclude com.example.internal
```

Suppose the source tree contains:

```text
com.example
com.example.api
com.example.model
com.example.internal
com.example.internal.codegen
com.example.test
```

The command above excludes `com.example.internal` and its sub-branch `com.example.internal.codegen` from the selected package set. Other packages under `com.example` can still be processed.

You can use `-exclude` to keep public documentation focused on the API that library users need to know.

Notes:

- `-exclude` is used together with the `-subpackages` option.
- Package names must be spelled accurately and are case-sensitive.
- Excluding a package from documentation does not delete the source code or prevent the application from compiling that package.
- If an internal package is separately selected via a source file list or another package option, double-check the overall input scope.

## 6. How Source Path Differs from Classpath

These two options serve different purposes:

| Option | Used to locate | Purpose |
| --- | --- | --- |
| `-sourcepath` | `.java` source files | Locate source code for selected packages/types or types to resolve |
| `-classpath` / `--class-path` | Class files and JARs | Locate compiled types referenced by the source code |

For example, suppose a project has:

```text
project/
  src/
    com/example/api/Client.java
  lib/
    helper.jar
```

Generate documentation for sources in `src`, while using the JAR to resolve dependent types:

```bash
javadoc -d docs -sourcepath src --class-path lib/helper.jar com.example.api
```

`lib/helper.jar` helps Javadoc locate compiled types referenced in the source code. It does not mean Javadoc will automatically generate documentation for every class in that JAR.

If you want documentation for a library's source code, you must provide the corresponding source files or packages via source selection. If you only have a JAR without sources, you can use the JAR to resolve types, but you cannot generate full documentation from that library's source doc comments in the standard way.

When `-sourcepath` is not specified, Javadoc may use the classpath to search for sources according to default rules. In real-world projects, you should explicitly specify the source path to keep documentation commands clear and consistent.

## 7. Selecting Multiple Packages or Multiple Source Files

You can select multiple packages by listing their package names:

```bash
javadoc -d docs -sourcepath src com.example.api com.example.model
```

Or pass multiple source files:

```bash
javadoc -d docs -sourcepath src src/com/example/api/Client.java src/com/example/model/User.java
```

Use this approach when you only want to generate documentation for explicitly chosen parts of the API. Check package comments and related types if they also need to appear in the documentation.

For large projects, listing all source files in a single command can make the command hard to read. You can use an argument file to manage the list.

## 8. Using an Argument File (@file)

Javadoc supports reading options and arguments from a file using the `@filename` syntax. This is useful when the list of source files or packages is long.

Example **`javadoc.args`** file:

```text
-d
docs
-encoding
UTF-8
-sourcepath
src
com.example.api
com.example.model
```

Run:

```bash
javadoc @javadoc.args
```

You can store a list of source files instead of package names:

```text
-d
docs
-sourcepath
src
src/com/example/api/package-info.java
src/com/example/api/Client.java
src/com/example/model/User.java
```

Advantages:

- Shorter terminal commands.
- The input list is stored in the repository and reviewed alongside changes.
- Easy to reuse in CI.
- Avoids errors when a command contains too many arguments.

When using an argument file, check relative paths against the working directory where the command is run, and use proper quoting if paths contain spaces. Avoid letting the package and source file lists accidentally point to multiple versions of the same source tree.

## 9. Selecting Sources for Modular Projects

With JPMS, each module's source code typically resides in its own directory under the module source path.

Example:

```text
project/
  src/
    com.example.math/
      module-info.java
      com/example/math/
        package-info.java
        Calculator.java
    com.example.app/
      module-info.java
      com/example/app/
        Main.java
```

Use `--module-source-path` to specify the root of the module source tree and `--module` to select the modules to document.

Example generating documentation for the math module:

```bash
javadoc --module-source-path src -d docs --module com.example.math
```

Generate documentation for both modules:

```bash
javadoc --module-source-path src -d docs --module com.example.math,com.example.app
```

Meaning:

- `--module-source-path src`: specifies where the module source directories are located.
- `--module com.example.math`: selects the module with the matching name.
- `-d docs`: saves the HTML documentation.

If a module needs compiled modules or other dependencies to resolve types, you can specify the appropriate module path using `--module-path`.

Distinction:

- `--module-source-path`: where to find module source code.
- `--module-path`: where to find compiled modules to resolve dependencies.

Do not use a package name instead of a module name in the `--module` option. The module name comes from the `module` declaration in `module-info.java`.

## 10. Complete Example: Selecting Sources in a Library

The following example generates documentation for the public API in the `com.example.math` package while excluding the internal package.

Project structure:

```text
project/
  src/
    com/example/math/
      package-info.java
      Calculator.java
      internal/
        BigMath.java
    com/example/app/
      Main.java
  docs/
```

File **`src/com/example/math/package-info.java`**:

```java
/**
 * Provides arithmetic operations for the application.
 */
package com.example.math;
```

File **`src/com/example/math/Calculator.java`**:

```java
package com.example.math;

/**
 * Provides basic integer arithmetic operations.
 */
public final class Calculator {
    private Calculator() {
    }

    /**
     * Adds two integers.
     *
     * @param left the first operand
     * @param right the second operand
     * @return the sum of the two numbers
     */
    public static int add(int left, int right) {
        return left + right;
    }
}
```

File **`src/com/example/math/internal/BigMath.java`**:

```java
package com.example.math.internal;

/**
 * Internal implementation utilities.
 */
public final class BigMath {
    private BigMath() {
    }

    /**
     * Returns the square of a number.
     *
     * @param value the input value
     * @return the square
     */
    public static long square(long value) {
        return value * value;
    }
}
```

File **`src/com/example/app/Main.java`**:

```java
package com.example.app;

import com.example.math.Calculator;

public class Main {
    public static void main(String[] args) {
        System.out.println("sum=" + Calculator.add(7, 5));
    }
}
```

### Step 1: Select only the API package

Run from the `project` root directory:

```bash
javadoc -d docs-api -encoding UTF-8 -sourcepath src com.example.math
```

Javadoc generates documentation for the `com.example.math` package. The `com.example.math.internal` package is not automatically selected just because it is a subpackage; this command selects only the explicitly named package.

### Step 2: Select the entire package tree while excluding internal

Run:

```bash
javadoc -d docs-public -encoding UTF-8 -sourcepath src -subpackages com.example -exclude com.example.math.internal
```

This command scans the `com.example` tree, but excludes the `com.example.math.internal` package and its sub-branches from the selected set.

### Step 3: Select a single source file

If you only need documentation for `Calculator` and the package summary:

```bash
javadoc -d docs-single -encoding UTF-8 -sourcepath src src/com/example/math/package-info.java src/com/example/math/Calculator.java
```

### Step 4: Compile and run the application separately

Javadoc generates HTML, not bytecode. To test the program:

```bash
javac -d out -sourcepath src src/com/example/app/Main.java
java -cp out com.example.app.Main
```

Exact output:

```text
sum=12
```

This example shows that source selection determines which source code is included in the documentation, while `javac` remains responsible for compiling the program.

## 11. Member Visibility Is Not Source Selection

A common misconception is treating `-private` or `-public` as a form of source selection. In reality, these options determine which member visibility levels are included in the generated documentation pages after the sources/packages have been selected.

| Option | Members shown |
| --- | --- |
| `-public` | Public only |
| `-protected` | Public and protected; default level |
| `-package` | Public, protected, and package-private |
| `-private` | All, including private |

Example:

```bash
javadoc -d docs-internal -private -sourcepath src com.example.math
```

The command still selects the `com.example.math` package, but the documentation includes private members as well.

Conversely:

```bash
javadoc -d docs-public -public -sourcepath src com.example.math
```

The command selects the same package but only displays public members.

When generating public API documentation, you should usually use the default level or `-public`. Only use `-private` for internal documentation when there is a valid reason.

## 12. Selecting Sources in Maven and Gradle

In projects using build tools, source selection is usually based on source sets or plugin configuration.

### Maven

The Maven Javadoc Plugin typically pulls source code from the Maven project's source roots. You can generate documentation with:

```bash
mvn javadoc:javadoc
```

If you only want documentation for a specific set of packages or a custom source configuration, pass Javadoc options through the plugin configuration, such as `sourcepath`, `subpackages`, or parameters appropriate for your plugin version. Check the plugin documentation because parameter names may differ from direct CLI options.

### Gradle

With the Gradle Java plugin, the `javadoc` task uses the main source set's sources by default. You can inspect or customize the task's sources:

```groovy
tasks.named('javadoc', Javadoc) {
    source = sourceSets.main.allJava
    options.encoding = 'UTF-8'
}
```

Run:

```bash
./gradlew javadoc
```

On Windows:

```powershell
.\gradlew.bat javadoc
```

In multi-module builds, each module typically has its own Javadoc task. Clearly specify which source sets are included in the documentation to avoid accidentally including test sources or unwanted generated sources.

## 13. Common Source Selection Errors

| Symptom | Common cause | How to fix |
| --- | --- | --- |
| Javadoc reports package not found | Incorrect package name or source path does not point to source root | Check the package declaration and `-sourcepath` |
| Subpackages are missing | Passed only the parent package name without `-subpackages` | Use `-subpackages` when you want recursive scanning |
| Documentation includes internal packages | Root package selected is too broad | Use `-exclude` or select specific packages |
| Missing package summary | `package-info.java` was not included in the source file list or the package was not selected properly | Select the package or add `package-info.java` |
| Javadoc cannot resolve dependent types | Missing classpath or module path | Add `--class-path` or `--module-path` |
| Documentation shows too many members | Used `-private` unintentionally | Use `-public` or the default level |
| No documentation for JAR dependencies | Only added the JAR to the classpath | Provide the corresponding sources/packages if you want to document the library |
| Module not found | Confused module source path with module path or wrong module name | Check `--module-source-path`, `--module-path`, and `--module` |
| Command is too long or easy to miss files | Listing many source files directly | Use an argument file `@javadoc.args` |

## 14. Recommended Source Selection Workflow

Before running Javadoc, determine:

1. **Documentation goal:** public API, internal documentation, or a set of experimental classes?
2. **Project type:** standard source tree or modular project?
3. **Package scope:** a single package, multiple packages, or an entire package hierarchy?
4. **Source input:** specific files, package names, `-subpackages`, or `--module`?
5. **Packages to exclude:** are there internal, generated, or test packages to skip?
6. **Dependencies to resolve:** do you need `--class-path` or `--module-path`?
7. **Visibility level:** public/protected, or are package-private/private members needed?
8. **Reproducibility:** should the input list be saved in an argument file or build script?

After selecting sources, run Javadoc, inspect the generated package/class pages, and verify that no packages are missing or unexpectedly included compared to the intended scope.

## 15. Key Takeaways

- Javadoc can accept specific source files, package names, or an argument file list.
- Use `-sourcepath` to specify the root of the source tree when selecting packages.
- Use `-subpackages` to select a package and its subpackages.
- Use `-exclude` to exclude packages and their sub-branches when scanning with `-subpackages`.
- Use `--module-source-path` and `--module` to select modules in JPMS projects.
- Use `--class-path` or `--module-path` to resolve dependencies; they do not automatically select sources to document.
- `-public`, `-protected`, `-package`, and `-private` control member visibility, not source scope.
- Use `@argfile` to manage long and reusable input lists.

Explicit source selection ensures that Javadoc documentation accurately reflects the intended public API, is easy to verify in code reviews, and can be reproduced consistently in the build process.
