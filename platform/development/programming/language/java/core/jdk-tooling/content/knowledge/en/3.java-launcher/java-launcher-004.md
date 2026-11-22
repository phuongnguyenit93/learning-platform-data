# Running a Module with the Java Launcher

The Java launcher is the `java` program used to launch Java applications. For applications organized into modules under the Java Platform Module System (JPMS), the launcher identifies the module, resolves dependent modules, and invokes the `main` method of the startup class. Since Java 9, you can run a compiled module from a directory, run a modular JAR, or combine multiple modules on the module path.

This guide uses Java 17 or later syntax and focuses on how to launch a module with `java`, how to select the main class, how dependencies are resolved, and how to troubleshoot common errors.

## 1. Module Launch Syntax

General syntax:

~~~text
java [VM options] --module-path <module-path> --module <module-name>[/<main-class>] [application-args...]
~~~

Components:

- `java`: invokes the Java launcher from the JDK or runtime currently configured on `PATH`.
- `VM options`: JVM options, such as `-Dname=value`, `-Xmx512m`, `-ea`, or `--enable-preview`.
- `--module-path` (`-p`): specifies where the launcher looks for modules.
- `--module` (`-m`): selects the root module to run; `/main-class` can be appended to specify the main class explicitly.
- `application-args`: arguments passed to the application's `main(String[] args)` method.

The following two forms are equivalent:

~~~powershell
java --module-path mods --module com.example.greeter/com.example.greeter.Main
java -p mods -m com.example.greeter/com.example.greeter.Main
~~~

If you omit the main class after `/`, the launcher looks for the main class information recorded in the module descriptor. If the module does not contain this information, specify the full main class name in the command.

## 2. Preparing a Module to Run

A Java module has a name and dependency declarations in the `module-info.java` file. For example, create the following structure:

~~~text
project/
├── src/
│   ├── module-info.java
│   └── com/
│       └── example/
│           └── greeter/
│               └── Main.java
├── mods/
└── mlib/
~~~

Contents of `src/module-info.java`:

~~~java
module com.example.greeter {
    exports com.example.greeter;
}
~~~

Contents of `src/com/example/greeter/Main.java`:

~~~java
package com.example.greeter;

public class Main {
    public static void main(String[] args) {
        String target = args.length == 0 ? "module" : String.join(" ", args);
        System.out.println("Hello, " + target + "!");
    }
}
~~~

The `Main` class has a `public static void main(String[] args)` method, which is the familiar entry point of a Java application. The module descriptor names the module `com.example.greeter`. The `exports` declaration allows other modules to access public types in this package; this simple example does not yet have another module calling it, but the declaration demonstrates how a module exposes its API.

## 3. Running an Exploded Compiled Module Directory

When compiling a module, the output directory must preserve the package structure and have `module-info.class` at the root of the module directory.

From the `project` directory, run in PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path mods/com.example.greeter | Out-Null
javac -d mods/com.example.greeter src/module-info.java src/com/example/greeter/Main.java
java --module-path mods --module com.example.greeter/com.example.greeter.Main Java 17
~~~

Output:

~~~text
Hello, Java 17!
~~~

Explanation:

1. `javac -d mods/com.example.greeter ...` compiles both the module descriptor and the `Main` class.
2. `mods` is the module path. Inside it is the `com.example.greeter` module directory.
3. `--module com.example.greeter/com.example.greeter.Main` instructs the launcher to run the `com.example.greeter` module using `com.example.greeter.Main` as the main class.
4. The arguments `Java` and `17` appear after the module specification, so they are passed into the application's `args`.

You can use the shorthand command:

~~~powershell
java -p mods -m com.example.greeter/com.example.greeter.Main Java 17
~~~

On Linux or macOS, the `javac` and `java` commands are identical; only the directory creation command differs if needed. You can use `mkdir -p mods/com.example.greeter` instead of `New-Item`.

## 4. Running a Module from a Modular JAR

After compiling, you can package the module into a modular JAR. A modular JAR contains `module-info.class`, so the launcher can determine the module name and declared dependencies.

From the `project` directory, run:

~~~powershell
New-Item -ItemType Directory -Force -Path mlib | Out-Null
jar --create --file mlib/com.example.greeter.jar --main-class com.example.greeter.Main -C mods/com.example.greeter .
jar --describe-module --file mlib/com.example.greeter.jar
~~~

The `--main-class` option records the main class in the modular JAR's metadata. The `jar --describe-module` command lets you inspect the module name, exported packages, requirements, and declared main class.

Launch the modular JAR by module name:

~~~powershell
java --module-path mlib --module com.example.greeter Java 17
~~~

Output:

~~~text
Hello, Java 17!
~~~

Because the main class was recorded with `jar --main-class`, the launcher can run the module without specifying the class name after `/`. If the modular JAR does not declare a main class, specify it in the command:

~~~powershell
java --module-path mlib --module com.example.greeter/com.example.greeter.Main Java 17
~~~

You can shorten `--module-path` to `-p` and `--module` to `-m`:

~~~powershell
java -p mlib -m com.example.greeter Java 17
~~~

Note: a modular JAR contains `module-info.class` and is located via the module path. A regular JAR that only has `Main-Class` in its manifest does not automatically become an explicit module; running regular JARs is covered in Section 7.

## 5. Module Path and Module Resolution

The module path is a list of locations where Java searches for modules. Each entry can be a modular JAR or a directory containing exploded modules. For applications with multiple modules, placing all modular JARs in a shared directory is often convenient.

Example structure:

~~~text
project/
├── mlib/
│   ├── com.example.greeter.jar
│   ├── com.example.formatter.jar
│   └── com.example.config.jar
└── ...
~~~

Running the application:

~~~powershell
java --module-path mlib --module com.example.greeter/com.example.greeter.Main
~~~

The launcher locates the root module `com.example.greeter`, reads the `requires` declarations in `module-info.class`, and resolves the necessary dependent modules. If the module requires `com.example.formatter`, that module must be present on the module path and its module name must match the declaration.

Example descriptor with a dependent module:

~~~java
module com.example.greeter {
    requires com.example.formatter;
    exports com.example.greeter;
}
~~~

A `requires` declaration defines a module-level dependency. Simply placing a JAR in the same directory does not automatically make one module a dependency of another; the module must declare the appropriate dependency.

### 5.1. Multiple Locations on the Module Path

The module path can contain multiple paths. The path separator depends on the operating system:

| Operating System | Separator | Example |
|---|---|---|
| Windows | `;` | `-p "mlib;extra-modules"` |
| Linux/macOS | `:` | `-p "mlib:extra-modules"` |

Example on Windows:

~~~powershell
java --module-path "mlib;extra-modules" --module com.example.greeter/com.example.greeter.Main
~~~

Enclose the path list in quotes if it contains spaces or characters that the shell might interpret specially.

### 5.2. Observing the Resolution Process

When you need to see which modules the launcher selected, use `--show-module-resolution`:

~~~powershell
java --show-module-resolution --module-path mlib --module com.example.greeter/com.example.greeter.Main
~~~

This option prints information about the resolved modules before the application runs. It is useful for diagnosing missing modules, wrong versions being selected, or multiple module sources on the module path.

You can inspect a module's descriptor inside a JAR with:

~~~powershell
jar --describe-module --file mlib/com.example.greeter.jar
~~~

And list the modules available in the current runtime:

~~~powershell
java --list-modules
~~~

## 6. Common Launcher Options When Running Modules

JVM options must be placed before `-m` or `--module`. Arguments placed after the module and main class are passed to the application.

### 6.1. Setting System Properties and Memory

Example passing an environment configuration and heap limits:

~~~powershell
java -Dapp.env=dev -Xms128m -Xmx512m --module-path mlib --module com.example.greeter/com.example.greeter.Main
~~~

- `-Dapp.env=dev` sets a system property that can be read via `System.getProperty("app.env")`.
- `-Xms128m` sets the initial heap size.
- `-Xmx512m` sets the maximum heap size.

Memory values should match the needs of the application and deployment environment. `-X` options may depend on the JVM version.

### 6.2. Enabling Assertions

If the program uses `assert`, enable assertions at runtime with `-ea`:

~~~powershell
java -ea --module-path mlib --module com.example.greeter/com.example.greeter.Main
~~~

Assertions are typically used to verify assumptions during development and testing. You should not rely on assertions to replace input validation or error handling required in production.

### 6.3. Adding Root Modules with `--add-modules`

Normally, the module specified by `-m` is the application's root module, and the launcher automatically resolves the modules it requires. `--add-modules` lets you add other modules to the set of root modules to resolve.

Example:

~~~powershell
java --module-path mlib --add-modules com.example.config --module com.example.greeter/com.example.greeter.Main
~~~

This option is useful when a module needs to be included in the observable module set even though it is not directly required by the root module. It does not replace a `requires` declaration when code in a named module needs to read another named module.

### 6.4. Enabling Resolution Logging and Preview Features

- `--show-module-resolution`: displays the module resolution process.
- `--enable-preview`: enables preview features for the exact Java version being run; when using this, the code must also be compiled with the corresponding preview option of the same JDK version.
- `-Dkey=value`: passes a system property.
- `-ea`: enables assertions.

Combined example:

~~~powershell
java -Dapp.mode=test -ea --show-module-resolution --module-path mlib --module com.example.greeter/com.example.greeter.Main sample
~~~

The `sample` argument is passed to the application. JVM options appear before the module selection.

## 7. Running a Module vs. Classpath and Executable JARs

The Java launcher supports multiple execution modes. Choosing the right mode helps avoid confusion between module names, class names, and JAR paths.

| Mode | Sample Command | How Code Is Located |
|---|---|---|
| Running a class on the classpath | `java -cp out com.example.greeter.Main` | Searches for classes via the classpath; code belongs to the unnamed module |
| Running a regular JAR | `java -jar app.jar` | Reads the main class from `Main-Class` in the manifest |
| Running a module | `java -p mlib -m com.example.greeter/com.example.greeter.Main` | Resolves a named module on the module path |
| Running a modular JAR with main class metadata | `java -p mlib -m com.example.greeter` | Reads the module descriptor and declared main class |

The classpath and module path serve different roles:

- The classpath (`-cp`, `-classpath`, `--class-path`) is where classes and JARs belonging to the unnamed module are located.
- The module path (`-p`, `--module-path`) is where named modules and modular JARs are located.
- A regular JAR placed on the classpath does not become an explicit module merely by changing `-cp` to `-p`.
- A JAR without `module-info.class` can be treated as an automatic module when placed on the module path; the automatic module name is typically derived from the JAR filename or metadata. Automatic modules have their own limitations and are not equivalent to explicitly designed modules.

If your application is a traditional classpath application, use `-cp` or `-jar`. If your application has a module descriptor and needs module boundaries, use `--module-path` with `--module`.

## 8. Passing Arguments to the Program

Application arguments must be placed after the main class specification, or after the module name if the module already has main class metadata.

Example:

~~~powershell
java --module-path mlib --module com.example.greeter/com.example.greeter.Main "Java platform" "module system"
~~~

With the `Main` class from Section 2, the program receives two arguments. `String.join(" ", args)` joins them into `Java platform module system`, so the output is:

~~~text
Hello, Java platform module system!
~~~

Quotes tell the shell to keep a phrase with spaces as a single argument. How special characters are escaped can differ between PowerShell, Command Prompt, Bash, and Zsh.

If you want to check arguments in code, use `args.length` before accessing elements. Do not assume the user will always provide enough arguments.

## 9. Common Errors When Running Modules

| Message or Symptom | Common Cause | How to Fix |
|---|---|---|
| `Module com.example.greeter not found` | Incorrect module path or it does not contain a module with that name | Check the `-p` path, directory structure, and the name in `module-info.java` |
| `Module ... does not contain ...` or main class not found | Wrong main class name or the module has no main class declared when `/Main` is omitted | Use `-m module/package.Main` or package the modular JAR with `jar --main-class` |
| `Could not find or load main class` | Incorrect classpath syntax, wrong package name, or misplaced arguments | Verify the `-m` command, module name, main class, and package structure |
| `FindException` or `ResolutionException` | Missing dependent module, incompatible module, or invalid descriptor | Place the required module on the module path; check `requires` and `jar --describe-module` |
| `Package ... is not visible` or error accessing a type in another module | The package is not exported or the module has not declared reading the target module | Check `exports` and `requires` in the module descriptors |
| Application does not receive arguments as expected | Arguments were placed before `-m` or the shell split phrases containing spaces | Place arguments after the module/main class and use quotes appropriate for your shell |
| Changing `-cp` does not fix the module error | The classpath does not replace the module path for named modules | Place named modules on `--module-path` and declare dependencies properly |

When troubleshooting errors, check in this order: whether the module path points to the right location; whether the module name matches the descriptor; whether the module has all required dependencies; whether the main class exists and has a valid `main` method; and finally, check JVM options and application arguments.

## 10. Pre-Launch Checklist for Modules

- [ ] Use the exact Java runtime/JDK version required by the application.
- [ ] Compile the module with `module-info.java` if an explicit module is needed.
- [ ] Ensure the module path contains the root module and all dependent named modules.
- [ ] Verify the module name after `-m` matches the name declared in the module descriptor.
- [ ] Specify the main class via `/package.Main` or ensure it is recorded in the modular JAR's metadata.
- [ ] Place JVM options before `-m`; place application arguments after the module specification.
- [ ] Inspect module resolution when errors occur using `--show-module-resolution`.
- [ ] Test on the target Java version and deployment environment.

The Java launcher provides a unified entry point for running classes, JARs, and modules. When running a module, specify the right module path, select the module with `-m`, and ensure the main class can be found. When an application has multiple dependent modules, the module descriptor and the launcher's resolution output are the two most important places to inspect.
