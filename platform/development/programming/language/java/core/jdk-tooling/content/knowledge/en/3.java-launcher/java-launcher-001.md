# The `java` Command

`java` is the command used to launch Java applications. Provided in the JDK's `bin` directory, it initializes the Java Virtual Machine (JVM), loads the class or module to run, and invokes the application's entry point. Once you have bytecode in `.class` files or a suitable JAR, you use `java` to execute the program. Since Java 11, this command also supports running a `.java` source file directly in source-file mode.

It is important to distinguish three things: `javac` compiles source code into bytecode; `java` launches the program; the JVM executes the bytecode. The `java` command is the command-line interface for configuring and starting the JVM.

## 1. Checking the `java` Command

Open a terminal or Command Prompt and run:

~~~text
java --version
~~~

This command prints the Java runtime version found by the current terminal. For example, a Java 17 environment might display output similar to:

~~~text
openjdk 17.0.x 202x-xx-xx
OpenJDK Runtime Environment ...
OpenJDK 64-Bit Server VM ...
~~~

Patch numbers and description lines depend on the vendor and installed update.

To view the syntax and supported options:

~~~text
java --help
java --help-extra
~~~

`--help` lists common launcher options; `--help-extra` lists additional advanced options. The `-X` option displays non-standard `-X` options specific to the JVM in use:

~~~text
java -X
~~~

The list of options depends on the JVM version and implementation. When you need to verify a configuration flag, check the help output or the documentation for the exact JDK version you are running.

## 2. General Syntax

The Java launcher supports several ways to specify the program to run:

~~~text
java [options] mainclass [args ...]
java [options] -jar jarfile [args ...]
java [options] -m module[/mainclass] [args ...]
java [options] --module module[/mainclass] [args ...]
java [options] source-file [args ...]
~~~

Meaning:

- `options`: options for the Java launcher or JVM, such as classpath, module path, system properties, and memory configuration.
- `mainclass`: fully qualified name of the class containing the `main` method, for example `com.example.Main`.
- `jarfile`: path to a JAR file that declares a launch class in its manifest.
- `module`: name of the module to launch; you can optionally specify the main class after `/`.
- `source-file`: path to a `.java` file when using source-file mode.
- `args`: application arguments passed to the program.

**Option placement matters.** Options intended for the launcher/JVM must be placed before the class name, `-jar`, `-m`, or source file. Values placed after the launch target are treated as application arguments and appear in `String[] args`.

Example:

~~~text
java -Dapp.mode=dev -Xmx512m -cp out com.example.Main input.txt --verbose
~~~

In this command:

- `-Dapp.mode=dev` sets a system property for the JVM.
- `-Xmx512m` sets the maximum heap size to 512 MB.
- `-cp out` specifies where to look for classes.
- `com.example.Main` is the main class.
- `input.txt` and `--verbose` are application arguments, not JVM options.

If you place `-Xmx512m` after `com.example.Main`, it is passed to the program as a text argument; the JVM will not use it to configure the heap.

## 3. Running a Compiled Class

This is the common way to run a program when learning Java or when the program has already been compiled into class files.

Create `Main.java`:

~~~java
import java.util.Arrays;

public class Main {
    public static void main(String[] args) {
        String mode = System.getProperty("app.mode", "default");
        System.out.println("Mode: " + mode);
        System.out.println("Arguments: " + Arrays.toString(args));
    }
}
~~~

Compile into the `out` directory:

~~~text
javac -d out Main.java
~~~

After compilation, `out` contains `Main.class`. Launch the class:

~~~text
java -cp out Main
~~~

Output:

~~~text
Mode: default
Arguments: []
~~~

Pass a system property and application arguments:

~~~text
java -Dapp.mode=dev -cp out Main "hello world" 42
~~~

Output:

~~~text
Mode: dev
Arguments: [hello world, 42]
~~~

The string `"hello world"` is enclosed in quotes so the shell passes it as a single argument. Quoting syntax can differ slightly between PowerShell, Command Prompt, Bash, and Zsh; the goal is for Java to receive the exact two arguments: `hello world` and `42`.

If the class belongs to a package, you must use the fully qualified class name. For example, with `package com.example;` and the file located at `out/com/example/Main.class`, run:

~~~text
java -cp out com.example.Main
~~~

The class name does not include the `.class` extension. The classpath points to the root directory of the package tree—in this example, `out`.

When `-cp` or `-classpath` is not specified, the Java launcher uses the default classpath. For consistent execution across environments, explicitly specify the classpath whenever the application depends on an output directory or external libraries.

## 4. Running a JAR with `-jar`

An application can be packaged into a JAR file. To run a JAR as an executable JAR, its manifest must have a `Main-Class` attribute pointing to the main class.

For example, create a JAR from `Main.class`:

~~~text
jar --create --file app.jar --main-class Main -C out .
~~~

Then run:

~~~text
java -jar app.jar
~~~

Pass arguments to the application:

~~~text
java -jar app.jar --mode dev input.txt
~~~

Arguments after the JAR name are passed to `main(String[] args)`.

A few points to remember:

- `Main-Class` in the manifest must be the fully qualified class name if the class is in a package, for example `com.example.Main`.
- When using `java -jar`, the specified JAR serves as the source of application classes and resources for launching.
- External classpath settings such as `-cp` are not used to supplement the classpath the way they are when running a regular class once `-jar` mode is selected. If the application needs dependency libraries, package them appropriately, use the manifest `Class-Path` attribute according to your deployment layout, or choose another launch method.
- If the JAR has no `Main-Class`, the launcher does not know which class is the entry point and will report an error.

To inspect a JAR's manifest, you can list its contents with `jar` or extract the JAR and open `META-INF/MANIFEST.MF`. The manifest should contain lines similar to:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main
~~~

## 5. Running a Modular Application

A modular Java application can be launched by module name. The `--module-path` (short form `-p`) option specifies where the JVM looks for modules.

Example:

~~~text
java --module-path mods -m com.example.app/com.example.Main
~~~

Where:

- `mods` is the directory containing compiled modules or modular JARs.
- `com.example.app` is the module name declared in `module-info.java`.
- `com.example.Main` is the main class in the module.

If the module declares a single main class in its module descriptor, you can launch the module without specifying the class after `/`:

~~~text
java --module-path mods -m com.example.app
~~~

The `--module` option is equivalent to `-m`. The module name and main class name must match the application structure. The module path and classpath serve two different class-resolution mechanisms: the classpath places classes into the unnamed module, whereas the module path locates modules that have module descriptors.

Some common module options:

| Option | Meaning |
|---|---|
| `--module-path`, `-p` | Specifies where to find modules |
| `--module`, `-m` | Specifies the module to launch |
| `--add-modules` | Adds root modules to the set of resolved modules |
| `--show-module-resolution` | Displays module resolution output during startup |

Only use extended module options when your application structure requires them; a simple classpath application does not need module path configuration.

## 6. Running a Source File Directly — Source-File Mode

Since Java 11, the Java launcher supports running a source file directly:

~~~text
java Main.java
~~~

This is source-file mode. The launcher compiles the source file to run the program without requiring you to invoke `javac` separately beforehand. This is convenient for small examples, learning scripts, and quick experiments.

The `Main.java` file must still have a valid entry point for the Java version in use. You can pass application arguments:

~~~text
java Main.java alpha "two words"
~~~

In source-file mode, options for the source launcher can be placed before the file name. For example, to select the source language version:

~~~text
java --source 17 Main.java
~~~

The `--source` option selects the source language level for source-file mode. It is not a general replacement for a project build process. For projects with multiple classes, dependencies, tests, and packaging, use a build tool or an appropriate `javac`/`jar` workflow.

## 7. Classpath: `-cp` and `--class-path`

The classpath is the list of locations where the Java launcher/JVM looks for classes and resources in a non-modular application. It can be specified with `-cp`, `-classpath`, or `--class-path`.

Example:

~~~text
java -cp out com.example.Main
~~~

A classpath can contain multiple directories or JARs. Entries are separated by an operating-system-dependent character:

| Operating System | Separator |
|---|---|
| Windows | Semicolon `;` |
| macOS/Linux | Colon `:` |

Windows example:

~~~text
java -cp "out;lib/*" com.example.Main
~~~

macOS/Linux example:

~~~text
java -cp "out:lib/*" com.example.Main
~~~

The `lib/*` pattern includes all JAR files in the `lib` directory on the classpath. The `*` in this classpath syntax is expanded by the Java launcher; you should not assume a stable expansion order for the JARs.

Classpath errors usually stem from specifying the wrong root directory, missing a dependency JAR, or mistyping the class name. If the class is `com.example.Main`, the classpath must point to the directory containing the `com` directory, not directly to `com/example`.

If you need to check the current path or working directory, remember that relative paths are resolved against the process's **working directory**, not necessarily the directory containing the `.java` file or JAR.

## 8. Common JVM Options

The options below are placed before the class name, `-jar`, `-m`, or source file.

### 8.1. Setting a System Property with `-D`

Syntax:

~~~text
-Dname=value
~~~

Example:

~~~text
java -Dapp.env=production -cp out Main
~~~

The application reads the value using:

~~~java
String env = System.getProperty("app.env");
~~~

System properties are suitable for JVM or application configuration that needs to be read at runtime. Do not use them to pass passwords or sensitive secrets on the command line, as process arguments can be observed by system administration tools or written to logs.

### 8.2. Configuring the Heap with `-Xms` and `-Xmx`

- `-Xms`: initial heap size.
- `-Xmx`: maximum heap size the JVM is allowed to use.

Example:

~~~text
java -Xms256m -Xmx1g -cp out Main
~~~

This command sets the initial heap to 256 MB and the maximum heap to 1 GB. This is a limit on the heap, not on the process's total memory. The JVM also needs native memory, thread stacks, metadata, code cache, and other areas.

Do not pick a fixed heap size without measuring. Base it on available RAM, container limits, thread count, data size, GC behavior, and real workload characteristics.

### 8.3. Enabling Assertions with `-ea`

Assertions in Java are disabled by default. They can be enabled with:

~~~text
java -ea -cp out Main
~~~

When enabled, `assert` statements in the program are evaluated. Assertions are useful for checking assumptions during development and testing. Do not use assertions as a substitute for input validation or error handling that must always run in production.

### 8.4. Viewing Logs and Diagnostic Information

Modern JDKs provide unified logging. For example, to view class loading information:

~~~text
java -Xlog:class+load=info -cp out Main
~~~

Logs can be very verbose. Enable only the log tags you need, and avoid leaving overly detailed diagnostic logging active in high-load environments without evaluating its impact.

Other common JVM options relate to garbage collection, threads, JIT, and crash dumps. Option names and behavior may vary across versions or implementations; check `java -X` and the documentation for your JDK before applying them.

## 9. Passing Arguments to the Program

All arguments placed after the launch target are passed to the `main` method as `String[] args`.

Example:

~~~text
java -cp out Main --file data.csv --limit 10
~~~

With this command, the application receives four elements:

1. `--file`
2. `data.csv`
3. `--limit`
4. `10`

The launcher does not parse the meaning of application flags such as `--file` or `--limit`; your application or CLI library must handle them.

If a value contains spaces, enclose it in quotes according to the shell syntax in use:

~~~text
java -cp out Main "quarter one.csv"
~~~

To pass special characters such as quotes, backslashes, or shell metacharacters, escape them according to your shell. Java only receives the arguments after the shell has parsed the command line. When a bug involves how arguments are split, inspect the actual `args` values before looking for bugs in application logic.

## 10. Argument Files and Environment Variables

### Argument Files

When a command line has too many options or a long classpath, you can save the options in a file and pass them to the launcher using `@`.

Example `java.args` file:

~~~text
-Dapp.env=dev
-Xmx512m
--class-path
out;lib/*
~~~

Launch on Windows:

~~~text
java @java.args com.example.Main
~~~

On macOS/Linux, use `:` instead of `;` in the file's classpath. Argument files help shorten commands and avoid command-line length limits in some environments. File contents are parsed by the Java launcher according to argument file syntax; when whitespace or special characters are present, follow the quoting and escaping rules described in the launcher documentation.

### Related Environment Variables

Several variables can affect the `java` command:

- `JDK_JAVA_OPTIONS`: contains options prepended by the launcher before the options on the command line. Useful when you want to apply common settings across runs in an environment.
- `JAVA_TOOL_OPTIONS`: inspected by the JVM when initializing the VM; can add options to processes that start a JVM.
- `CLASSPATH`: can provide a default classpath when the command does not explicitly specify one.

Environment variables can cause a command to behave differently from what is visible on the command line. When investigating unexpected behavior, check these variables as well as your IDE or build tool configuration. Prefer passing required configuration explicitly in run scripts so others can reproduce the behavior.

## 11. Troubleshooting Common Errors

### `java` is not recognized

**Cause:** The JDK is not installed, its `bin` directory is not in `PATH`, or the terminal is using an outdated `PATH`.

**Solution:** Check the JDK installation location, add the appropriate `bin` directory to `PATH`, and open a new terminal. On Windows you can run `where.exe java`; on macOS/Linux you can run `which -a java` to see which executable is found.

### `Could not find or load main class`

**Cause:** Wrong class name, wrong package, or the classpath does not contain the root directory of the class.

**Solution:** Check the fully qualified class name, the output directory structure, and the `-cp` value. For example, if the class file is at `out/com/example/Main.class`, run `java -cp out com.example.Main`.

### `Main method not found`

**Cause:** The specified class does not have an entry point matching the kind of application being run, or the `main` declaration has the wrong signature.

**Solution:** For a traditional Java application, check for `public static void main(String[] args)` in the main class and ensure the class file was compiled from the current source code.

### `Unable to access jarfile`

**Cause:** Wrong JAR path, the file does not exist, or the process lacks read permissions for the file.

**Solution:** Check the working directory, file name, and path. If the path contains spaces, wrap the entire path in quotes according to your shell.

### `no main manifest attribute`

**Cause:** The JAR does not have a `Main-Class` attribute in its manifest.

**Solution:** Repackage the JAR with an appropriate `Main-Class` or run the main class directly using `java -cp ... package.Main`.

### `UnsupportedClassVersionError`

**Cause:** The class file was compiled with a newer Java version than the runtime currently executing it.

**Solution:** Use a compatible runtime or recompile with `javac --release` targeting your deployment version. Check the actual version with `java --version`, not just the IDE's configured version.

### Application cannot find a library

**Cause:** The dependency is not on the classpath/module path, a dependency JAR is missing, or the manifest is misconfigured.

**Solution:** Verify that the library is packaged or added to the appropriate path. For modular applications, check the module path and `requires` declarations; for classpath applications, check `-cp` and the required JARs.

### JVM does not recognize an option or the option has no effect

**Cause:** The option was placed after the class name/JAR, has invalid syntax, or is not supported in the version being used.

**Solution:** Place JVM options before the launch target, and check `java --help`/`java -X` and the documentation for your exact version.

## 12. Choosing How to Launch

| Scenario | Recommended Command |
|---|---|
| Run a compiled class | `java -cp out com.example.Main` |
| Run a JAR with `Main-Class` | `java -jar app.jar` |
| Run a modular application | `java --module-path mods -m module/name.Main` |
| Quickly test a Java 11+ source file | `java Main.java` |
| Pass configuration to the JVM | `java -Dkey=value -Xmx512m ...` |
| Pass arguments to the application | Place them after the class name, JAR, module, or source file |

When choosing a command, determine whether the application is packaged as a classpath application, an executable JAR, or a module. Then place JVM options before the launch target and application arguments after it. Record the working directory, Java version, classpath/module path, and required environment variables so the command can run consistently on other machines.

`java` is the starting point for executing Java applications: it selects the launch mode, configures the JVM, locates program code, and passes arguments to the application. Mastering its syntax, option ordering, classpath, JARs, and modules helps you run programs accurately and diagnose environment issues quickly.