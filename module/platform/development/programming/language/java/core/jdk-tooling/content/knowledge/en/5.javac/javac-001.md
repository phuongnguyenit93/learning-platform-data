# The javac Command

`javac` is the Java compiler included with the JDK. This command reads `.java` source code, checks syntax and data types, and then generates bytecode in `.class` files so the JVM can load and execute them. When working with Java, it is important to distinguish between three things:

- `javac` compiles source code into bytecode.
- `java` launches a program on the JVM.
- The JDK provides both commands along with other development tools.

A successful compilation command typically prints no output; the `.class` files are created in the output directory. If errors occur, `javac` displays the location and description so the developer can fix the source code or compilation configuration.

## 1. Checking javac and Command Syntax

Before compiling, confirm that the compiler is available on your machine:

```sh
javac --version
```

For example, with JDK 21, the output looks like:

```text
javac 21
```

How patch version numbers are displayed may vary across distributions. If the system reports that the command is not found, verify that the JDK is fully installed and that the JDK's `bin` directory is in `PATH`.

General syntax:

```text
javac [options] source-files
javac [options] @argfiles
```

Where:

- `options` are flags controlling language version, output directory, classpath, encoding, warnings, and other processing steps.
- `source-files` are one or more Java source files to compile.
- `@argfiles` are text files containing a list of options and source file names, useful when the input list is long.

You can view the help for your installed JDK version:

```sh
javac --help
javac -X
javac --help-extra
```

`--help` lists commonly used options; `-X` and `--help-extra` display additional advanced options. Some options starting with `-X` may change between JDK versions, so check the help output of the specific JDK you are using.

## 2. Compiling a Simple Java Program

Create a file named `Hello.java`:

```java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello, Java!");
    }
}
```

Open a Terminal in the directory containing the file and run:

```sh
javac Hello.java
```

If there are no errors, the compiler creates `Hello.class` in the current directory. Run the program using the `java` command:

```sh
java Hello
```

Output:

```text
Hello, Java!
```

Notes:

- When invoking `javac`, pass the source file name with the `.java` extension.
- When invoking `java`, pass the fully qualified class name (in this example, `Hello`), without `.java` or `.class`.
- The file name must match the top-level `public` class name exactly. `public class Hello` must reside in `Hello.java`.
- If the compilation command succeeds but `.class` is not visible, check the working directory and the `-d` option if used.

## 3. Compiling Source Code with Packages

In real-world projects, classes usually reside in packages. Example source structure:

```text
project/
└── src/
    └── com/
        └── example/
            └── Hello.java
```

Contents of `src/com/example/Hello.java`:

```java
package com.example;

public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello from package!");
    }
}
```

From the `project` directory, compile with the `-d` option:

```sh
javac -d out src/com/example/Hello.java
```

`-d out` specifies the root directory for the generated `.class` files. The compiler automatically creates subdirectories matching the package:

```text
project/
├── src/
│   └── com/example/Hello.java
└── out/
    └── com/
        └── example/
            └── Hello.class
```

Run the class using its fully qualified name and put the output directory on the classpath:

```sh
java -cp out com.example.Hello
```

Output:

```text
Hello from package!
```

The package name in the source code, directory structure, and fully qualified class name must be consistent. For projects with packages, use `-d` to keep source code and bytecode in separate areas. If `-d` is omitted, `.class` files are typically placed next to their corresponding source files.

## 4. Compiling Multiple Files and Dependent Classes

A program can consist of multiple classes. For example, with two files:

`src/com/example/Greeter.java`:

```java
package com.example;

public class Greeter {
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

`src/com/example/Main.java`:

```java
package com.example;

public class Main {
    public static void main(String[] args) {
        Greeter greeter = new Greeter();
        System.out.println(greeter.greet("Java"));
    }
}
```

Compile both files in a single command:

```sh
javac -d out src/com/example/Greeter.java src/com/example/Main.java
```

Run the class containing the `main` method:

```sh
java -cp out com.example.Main
```

Output:

```text
Hello, Java!
```

You can pass multiple source paths to a single `javac` invocation. The compiler checks relationships between classes within the same compilation pass, avoiding errors caused by missing a directly dependent class.

If the source code depends on pre-compiled classes or JAR libraries, declare them on the classpath. If you want the compiler to search for additional dependent source code in a separate directory, you can specify `-sourcepath`. Do not confuse the source code directory with the bytecode or library directory.

## 5. Commonly Used javac Options

| Option | Purpose |
|---|---|
| `-d <dir>` | Specify the destination directory for generated `.class` files |
| `-cp <path>`, `-classpath <path>`, `--class-path <path>` | Specify the classpath to locate dependent classes and libraries during compilation |
| `-sourcepath <path>`, `--source-path <path>` | Specify where to find dependent source files |
| `--release <version>` | Compile for the specified Java platform version, including language rules, bytecode format, and corresponding public APIs |
| `-source <version>` | Specify the source language/syntax version |
| `-target <version>` | Specify the output bytecode format version |
| `-encoding <encoding>` | Specify the character encoding used to read source files, e.g., `UTF-8` |
| `-g` | Generate debugging information |
| `-g:none` | Do not generate debugging information |
| `-parameters` | Store method parameter names so they can be queried via reflection |
| `-Xlint:all` | Enable all compiler warning categories |
| `-Werror` | Treat warnings as errors and fail the compilation |
| `-verbose` | Print additional information about compilation and class loading |
| `-proc:none` | Disable annotation processing |
| `-processor <class>` | Specify the annotation processor to run |
| `-processorpath <path>` | Specify where to find annotation processors |
| `-s <dir>` | Specify the directory for source files generated by annotation processors |
| `@<file>` | Read options and source file names from an argument file |

The short and long forms of the classpath option serve the same purpose. You can use the long form in scripts for readability, or the short form in interactive commands.

### 5.1. Selecting the Output Directory with -d

Example:

```sh
javac -d build/classes src/com/example/Main.java
```

Compiled classes will be placed under `build/classes`, following the package structure. The output directory can be created if it does not already exist. When running the program, pass this exact directory to the classpath:

```sh
java -cp build/classes com.example.Main
```

`-d` does not package the program into a JAR. To create a JAR, use the `jar` tool after compiling.

### 5.2. Using External Libraries with classpath

Suppose the project uses a library at `lib/example.jar`. When compiling, add the library to the classpath:

```sh
javac -cp "lib/example.jar" -d out src/com/example/Main.java
```

If there are multiple JARs in the `lib` directory, you can use a wildcard:

```sh
javac -cp "lib/*" -d out src/com/example/Main.java
```

The classpath is a list of directories and JAR files where tools search for classes. The separator character between entries differs by operating system:

| Operating System | Classpath Separator |
|---|---|
| Windows | Semicolon `;` |
| macOS and Linux | Colon `:` |

For example, when two classpath entries are needed:

```text
Windows:       out;lib/example.jar
macOS/Linux:   out:lib/example.jar
```

The classpath must be configured for both compilation and runtime when the program needs those libraries. `javac -cp` only affects the current compilation pass; it does not save the library into the JVM's runtime configuration. Example on macOS/Linux:

```sh
java -cp "out:lib/*" com.example.Main
```

On Windows:

```powershell
java -cp "out;lib/*" com.example.Main
```

When paths contain spaces, wrap them in quotes so the shell passes them as a single argument. Do not use the Linux separator on Windows or vice versa.

### 5.3. Selecting the Platform Version with --release

A newer JDK can compile source code for an older Java version. For example, using JDK 21 to compile for the Java 17 platform:

```sh
javac --release 17 -d out src/com/example/Main.java
```

`--release 17` simultaneously controls:

- The allowed Java language syntax.
- The generated bytecode version.
- The set of public Java SE APIs available in version 17.

This is the generally recommended way to ensure a program is compatible with a target Java version. If you only use `-source 17 -target 17`, the compiler may still see APIs from the newer JDK and generate code referencing APIs that do not exist on Java 17.

You cannot use `--release` together with `-source` or `-target`. The target version also cannot be newer than the JDK running the compiler. For example, JDK 17 cannot compile with `--release 21`.

If the project requires preview features, you must enable preview when compiling with the exact JDK for that version, e.g., `--enable-preview --release 21`; at runtime, you also need to enable `--enable-preview`. Preview features are not stable APIs meant for default use in regular applications.

### 5.4. Selecting Source Code Encoding

To avoid differing results across machines with different default configurations, you can specify UTF-8:

```sh
javac -encoding UTF-8 -d out src/com/example/Main.java
```

This option specifies how the compiler reads `.java` file contents. It does not change the encoding the program uses when reading or writing data at runtime. If source code contains non-ASCII characters (such as Vietnamese) and the declared encoding does not match the actual file encoding, compilation errors or garbled characters may occur.

### 5.5. Enabling Warnings and Debugging Information

When you want to detect more potential issues:

```sh
javac -Xlint:all -d out src/com/example/Main.java
```

To treat warnings as errors in a strict build process:

```sh
javac -Xlint:all -Werror -d out src/com/example/Main.java
```

Do not suppress warnings wholesale just to make a build appear successful. Read the warning category, identify the source code or library causing it, and fix it or configure an intentional exception.

The `-g` option generates information to assist debuggers, such as source line numbers and local variables. `-parameters` stores method parameter names in bytecode; this is useful for frameworks or libraries that use reflection to read parameter names. The two options serve different purposes.

## 6. Compiling Projects Using the Java Module System

Modular projects have a `module-info.java` file declaring the module name and relationships such as `requires` and `exports`. When compiling, you can use `--module-path` to specify where to find dependent modules.

Example structure:

```text
src/
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
```

File `src/com.example.app/module-info.java`:

```java
module com.example.app {
}
```

File `src/com.example.app/com/example/app/Main.java`:

```java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Modular Java");
    }
}
```

Compile the module:

```sh
javac --module-source-path src -d out -m com.example.app
```

Run the module:

```sh
java --module-path out -m com.example.app/com.example.app.Main
```

Output:

```text
Modular Java
```

When a module depends on other modules, add the dependent module locations using `--module-path`. Classpath and module path have different roles: classpath primarily locates classes on the unnamed module's classpath, whereas module path locates defined modules. Do not blindly move all libraries onto the module path; understand whether a library is a modular JAR, an automatic module, or a classpath library.

## 7. Using Argument Files for Long Input Lists

When a project has many source files or the command is too long, save the arguments into a file, such as `sources.txt`:

```text
-d
out
-encoding
UTF-8
--release
21
src/com/example/Greeter.java
src/com/example/Main.java
```

Run:

```sh
javac @sources.txt
```

The compiler reads options and file names from the argument file. Each line in the example above is a separate argument. For paths containing spaces, wrap the path in quotes according to argument file rules. This is a convenient way to keep build commands clean and avoid exceeding command-line length limits in some environments.

An argument file only holds arguments for the compiler; it does not replace a full project build configuration. For Gradle or Maven projects, let the build tool manage source lists, libraries, and compiler options instead of maintaining a manual command file in parallel.

## 8. Annotation Processing

During compilation, `javac` can run annotation processors to read annotations and generate additional source code or resources. Some libraries use this mechanism to generate helper classes, metadata, or data-access code.

Common options:

- `-processorpath`: specifies where to find processors.
- `-processor`: selects specific processors to run.
- `-s`: specifies the directory to receive generated source files.
- `-proc:none`: disables annotation processing.

Example command structure when a processor is in a JAR:

```sh
javac -processorpath "lib/processor.jar" -s generated-sources -d out src/com/example/Main.java
```

This command assumes the processor and required libraries are fully provided. If a project uses processors, follow the official configuration of the library or build tool. Disabling annotation processing may cause the build to fail if the source code requires the generated classes.

## 9. Sample Compilation Command for a Small Project

For a Java 21 project with a `src` structure that places bytecode in `out`, a usable command is:

```sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/com/example/Greeter.java src/com/example/Main.java
```

After compiling, run:

```sh
java -cp out com.example.Main
```

If the project depends on JARs, add the classpath to both steps. On Windows use a semicolon; on macOS/Linux use a colon. For larger projects with multiple source sets, dependencies, annotation processors, or modules, use Gradle/Maven to manage configuration and invoke `javac` with the proper parameters generated by the build tool.

In a Gradle project, `javac` is typically invoked by the Java compiler task. Run `./gradlew compileJava` (Windows: `gradlew.bat compileJava`) so the build tool applies the project's toolchain, dependencies, and compiler options. Do not replace the project's build command with a simplified `javac` command if the project requires additional configuration.

## 10. Troubleshooting Common Errors

| Message or Symptom | Common Cause | Resolution |
|---|---|---|
| `javac: command not found` or `javac is not recognized` | JDK is not installed or the `bin` directory is not in `PATH` | Check JDK installation, `JAVA_HOME`, and `PATH`; open a new Terminal after changing environment variables |
| `error: file not found: ...` | Incorrect source path or wrong current working directory | Check file location, file name, and relative path; try using an absolute path |
| `error: no source files` | No source files passed or argument file contains no valid input | Check arguments after `javac` and the contents of the argument file |
| `cannot find symbol` | Class, variable, or method name does not exist in scope; missing import or missing dependency | Check spelling, declarations, imports, API version, and classpath |
| `package ... does not exist` | Missing library or package is not on the source path/classpath | Add the correct JAR or directory to `-cp`, or configure the source path |
| `class X is public, should be declared in a file named X.java` | File name does not match the public class name | Rename the file to match the public class name exactly |
| `invalid source release` or unsupported release version | The JDK running `javac` is older than the target version | Install or select a sufficiently new JDK, or use `--release` no higher than the JDK version |
| `duplicate class` | The same class is declared or compiled multiple times from conflicting sources | Check packages, source sets, classpath, and duplicate source files |
| `module not found` | Dependent module is missing from the module path or module name is incorrect | Check `--module-path`, module name, and how the library is packaged |
| Compilation succeeds but JVM cannot find the main class | Runtime classpath is missing the output directory or wrong class name is used | Use the correct `-cp` and fully qualified class name, e.g., `com.example.Main` |
| `UnsupportedClassVersionError` at runtime | The JVM running the application is older than the compiled bytecode version | Run with a sufficiently new JDK/JRE or compile with an appropriate `--release` |

You can increase verbosity when investigating:

```sh
javac -Xdiags:verbose -Xlint:all -verbose -d out src/com/example/Main.java
```

`-Xdiags:verbose` displays more detailed diagnostics; `-verbose` prints additional compiler activity. There is no need to enable verbose logging routinely in normal builds because the output can be very long.

When encountering errors, read the first message and the line/column position reported by the compiler. Subsequent errors are sometimes just consequences of an earlier syntax or declaration error. Fix the root error first and recompile to avoid chasing cascading messages that no longer exist.

## 11. Verifying Results After Compilation

After `javac` completes successfully, verify:

1. The command exit code indicates success and there are no compilation errors.
2. The `.class` files are in the expected output directory.
3. Package names and directory structure match.
4. The classpath or module path contains all required dependencies.
5. The program runs on the intended target JVM version.

For the example in section 4, you can list the bytecode files using an OS command or use the `javap` tool to inspect class information:

```sh
javap -classpath out com.example.Main
```

`javap` is a tool included with the JDK for reading compiled class structures, such as method signatures and bytecode. It is useful when you want to confirm a class was generated or investigate differences between source code and bytecode.

## 12. Distinguishing javac from Related Tools

| Tool | Role |
|---|---|
| `javac` | Compiles `.java` source code into `.class` bytecode |
| `java` | Launches a Java application or class on the JVM |
| `jar` | Creates, views, or manipulates JAR files |
| `javap` | Analyzes class structure and bytecode |
| `javadoc` | Generates API documentation from comments and declarations in source code |
| `jshell` | Interactive environment for testing Java expressions and statements |

A basic manual workflow is typically: use `javac` to compile, `java` to run, and `jar` if packaging is needed. In real-world projects, Gradle or Maven usually orchestrates these steps to ensure the same configuration is used on developer machines and in CI.

## 13. Checklist When Using javac

- Correct JDK selected and `javac --version` verified.
- Paths to all source files are accurate.
- File names match public class names.
- Packages and directory structures are consistent.
- `-d` specified to separate bytecode from source code when needed.
- Classpath or module path declared for dependencies.
- `--release` chosen to match the Java version supported by the project.
- Encoding declared, typically UTF-8, when cross-environment consistency is needed.
- Warnings and errors reviewed before running the application.
- Correct classpath/module path and compatible JVM used at runtime.

Understanding `javac` helps distinguish compile-time errors from runtime errors, while giving you control over Java versions, dependencies, and bytecode output. It is also the foundation for understanding how Gradle and Maven configure the compiler in large Java projects.