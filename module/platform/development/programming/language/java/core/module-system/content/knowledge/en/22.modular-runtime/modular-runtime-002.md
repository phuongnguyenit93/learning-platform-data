# Running a Modular Application with `java -m module/main-class`

## Objectives

After this lesson, you can read and write the `java -m module/main-class` syntax correctly, choose the module path for a JPMS application, understand how the launcher resolves the root module and dependencies before invoking `main`, pass arguments to the program, package a modular JAR with a main class, and diagnose common errors when running modular applications.

## 1. Syntax of the Modular Launch Command

General syntax:

~~~bash
java [launcher-options] --module module-name[/main-class] [application-args...]
~~~

Short form:

~~~bash
java [launcher-options] -m module-name[/main-class] [application-args...]
~~~

Where:

- `java` invokes the JDK's Java launcher.
- `--module-path` or `-p` specifies where the launcher searches for named modules.
- `--module` or `-m` requests running a module as the root module.
- `module-name` is the module name, for example `com.acme.app`.
- `main-class` is the fully qualified name of the class with the entry-point method, for example `com.acme.app.Main`.
- `application-args` are the arguments passed into `main(String[] args)`.

Basic example:

~~~bash
java --module-path mods --module com.acme.app/com.acme.app.Main
~~~

Shortened form:

~~~bash
java -p mods -m com.acme.app/com.acme.app.Main
~~~

The two commands above are equivalent. `-p` is the short form of `--module-path`, and `-m` is the short form of `--module`.

The part before the slash is the module name. The part after the slash is the fully qualified class name, including the package. Do not include the `.class` filename extension, do not use directory paths instead of the class name, and do not write the module name in package/class format.

## 2. What Does the Module Path Contain?

The module path is where the launcher searches for named modules. It can contain modular JARs and compiled exploded modules. Example structure:

~~~text
project/
  mods/
    com.acme.app/
      module-info.class
      com/acme/app/Main.class
    com.acme.greeter/
      module-info.class
      com/acme/greeter/Greeter.class
~~~

These are two exploded modules located under the `mods` directory. Another common structure stores modules as JARs:

~~~text
project/
  mods/
    com.acme.app.jar
    com.acme.greeter.jar
~~~

Both approaches can be discovered via the module path:

~~~bash
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

The launcher looks up the `com.acme.app` module on the module path, then resolves the dependencies declared in that module's descriptor.

If the module path has multiple entries, separate them using the operating system's path separator character:

- Windows: semicolon `;`.
- Linux and macOS: colon `:`.

Example on Windows:

~~~powershell
java --module-path "mods;lib/extra-modules" -m com.acme.app/com.acme.app.Main
~~~

Example on Linux/macOS:

~~~bash
java --module-path "mods:lib/extra-modules" -m com.acme.app/com.acme.app.Main
~~~

Enclose paths in quotes when they contain spaces or special shell characters.

## 3. Complete Example with Two Modules

We have a library module `com.acme.greeter` and an application module `com.acme.app`.

### Source Structure

~~~text
src/
  com.acme.greeter/
    module-info.java
    com/acme/greeter/Greeter.java
  com.acme.app/
    module-info.java
    com/acme/app/Main.java
~~~

Library module:

~~~java
// src/com.acme.greeter/module-info.java
module com.acme.greeter {
    exports com.acme.greeter;
}
~~~

~~~java
// src/com.acme.greeter/com/acme/greeter/Greeter.java
package com.acme.greeter;

public final class Greeter {
    private Greeter() {
    }

    public static String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

Application module:

~~~java
// src/com.acme.app/module-info.java
module com.acme.app {
    requires com.acme.greeter;
}
~~~

~~~java
// src/com.acme.app/com/acme/app/Main.java
package com.acme.app;

import com.acme.greeter.Greeter;

public final class Main {
    public static void main(String[] args) {
        String name = args.length > 0 ? args[0] : "Java";
        System.out.println(Greeter.greet(name));
    }
}
~~~

### Compiling the Modules

From the `project` directory, run:

~~~bash
javac -d out --module-source-path src -m com.acme.greeter,com.acme.app
~~~

Where:

- `-d out` places the compiled output in the `out` directory.
- `--module-source-path src` tells the compiler the root directory containing module sources.
- `-m com.acme.greeter,com.acme.app` specifies the modules to compile.

After compilation, the output structure looks like:

~~~text
out/
  com.acme.greeter/
    module-info.class
    com/acme/greeter/Greeter.class
  com.acme.app/
    module-info.class
    com/acme/app/Main.class
~~~

### Running the Application Module

~~~bash
java --module-path out --module com.acme.app/com.acme.app.Main
~~~

Output:

~~~text
Hello, Java
~~~

Passing an argument to the program:

~~~bash
java --module-path out -m com.acme.app/com.acme.app.Main Ada
~~~

Output:

~~~text
Hello, Ada
~~~

Arguments appearing after the module/main-class part are passed into `String[] args`. In the example, `args[0]` has the value `Ada`.

## 4. How Does the Launcher Resolve Modules?

When running:

~~~bash
java --module-path out -m com.acme.app/com.acme.app.Main
~~~

the launcher performs the main tasks before calling the `main` method:

1. Finds the root module `com.acme.app` on the module path.
2. Reads the module descriptor of the root module.
3. Resolves required dependencies, such as `requires com.acme.greeter`.
4. Constructs a valid module graph from observable modules and required dependencies.
5. Creates the runtime layer for the application when starting a modular application in the standard way.
6. Loads the main class and invokes the `main` method with the application arguments.

Therefore, the module path must provide all required modules before the program begins. If a required dependency is missing, the launcher stops during resolution; code inside `main` is not executed yet.

`requires transitive` also affects graph readability: if module A requires module B via `requires transitive`, modules reading A can read B according to readability rules. The launcher still resolves dependencies based on module descriptors rather than inferring dependencies from class imports.

JDK modules such as `java.base` are normally already present in the boot layer and are resolved from the parent configuration. You do not need to manually add `java.base` to the module path.

## 5. When Can You Omit the Main Class?

Normally, the launch command specifies both the module and the main class:

~~~bash
java -p mods -m com.acme.app/com.acme.app.Main
~~~

You can specify only the module name if the module descriptor already stores the application's main class in the `ModuleMainClass` attribute:

~~~bash
java -p mods -m com.acme.app
~~~

This attribute is usually set when creating a modular JAR using the `--main-class` option of the `jar` tool.

For example, after compiling the modules into `out/com.acme.app` and `out/com.acme.greeter`, you can package each module:

~~~bash
jar --create --file mods/com.acme.greeter.jar -C out/com.acme.greeter .
jar --create --file mods/com.acme.app.jar --main-class com.acme.app.Main -C out/com.acme.app .
~~~

Launch command without specifying the main class:

~~~bash
java --module-path mods --module com.acme.app
~~~

If the modular JAR does not have a main class recorded in its descriptor and the command also omits `/main-class`, the launcher does not know which class to launch. In that case, add the main class to the command or recreate the JAR with `jar --main-class`.

## 6. Distinguishing `-m` from `-cp` and `-jar`

The three common launch modes have different meanings.

### Running a Class on the Class Path

~~~bash
java -cp "classes;lib/*" com.acme.app.Main
~~~

The class path places classes and JARs into the class loader's unnamed module. This command runs under the traditional class path model; it does not select a root named module using `-m`.

### Running a Named Module

~~~bash
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

The module path and module descriptors are used to determine the module graph, dependencies, and JPMS access boundaries.

### Running an Executable JAR

~~~bash
java -jar application.jar
~~~

`-jar` selects the JAR as the launch source for an executable JAR. When you need explicit control over named modules, the module path, and the root module, use `--module-path` with `--module`. Do not replace `-m module/main-class` with `-jar` if the goal is to test how the launcher starts a named module.

## 7. Useful Launcher Options When Running Modular Applications

| Option | Effect |
| --- | --- |
| `--module-path`, `-p` | Specifies where to look for modules. |
| `--module`, `-m` | Selects the root module and optionally the main class. |
| `--show-module-resolution` | Prints module resolution details at startup. |
| `--list-modules` | Lists observable modules in the launcher configuration. |
| `--describe-module` | Displays the descriptor of a module. |
| `--add-modules` | Adds the specified modules as additional root modules. |
| `--limit-modules` | Limits the set of observable modules during resolution. |
| `--add-reads` | Adds a readability edge between modules. |
| `--add-exports` | Exports a module's package to target modules at runtime. |
| `--add-opens` | Opens a module's package for deep reflection from target modules. |

To observe the resolved module graph at startup:

~~~bash
java --show-module-resolution --module-path mods -m com.acme.app/com.acme.app.Main
~~~

To view a module's descriptor:

~~~bash
java --module-path mods --describe-module com.acme.app
~~~

To see the modules that the runtime can list:

~~~bash
java --module-path mods --list-modules
~~~

Options such as `--add-reads`, `--add-exports`, and `--add-opens` are useful for diagnostics or compatibility support. For a stable application configuration, declare dependencies and access boundaries in `module-info.java` instead of relying long-term on runtime overrides.

## 8. Common Errors When Using `java -m`

### Module Not Found

Example:

~~~text
Error occurred during initialization of boot layer
java.lang.module.FindException: Module com.acme.app not found
~~~

Common causes:

- The module name in the command does not match the name in the descriptor.
- The directory or JAR containing the module is not on the module path.
- A subdirectory was mistakenly used as the module path.
- The module has not been compiled or packaged.

Check the directory structure, `module-info.class`, and the module name value. Try:

~~~bash
java --module-path mods --list-modules
~~~

### Missing Required Module

If the application module has `requires com.acme.greeter` but the module path does not contain that dependency, resolution fails before entering `main`.

Add the corresponding JAR or exploded module to the module path. If there are multiple entries, use the correct operating system path separator.

### Main Class Not Found

Check the part after the slash:

~~~bash
java -p mods -m com.acme.app/com.acme.app.Main
~~~

`com.acme.app.Main` must be the fully qualified class name, in the right package, and inside the selected module. Do not add a `.class` suffix and do not replace package dots with directory slashes.

If you omit the main class, make sure the modular JAR has `ModuleMainClass` recorded using `jar --main-class`.

### Class or Package Not Accessible

Check:

- Whether the application module has `requires` for the module containing the used type.
- Whether the module owning the package has `exports` for that package to the application module.
- If the error comes from deep reflection, whether the package has `opens` for the module performing reflection.

Readability, exports, and opens are three separate conditions. Simply having the right module path does not automatically make every public or private package accessible.

### Running the Wrong Java Runtime

You can check the Java version and path used by the shell:

~~~bash
java -version
~~~

On Windows PowerShell, you can see the executable found:

~~~powershell
Get-Command java
~~~

Ensure the runtime used for execution is compatible with the bytecode and compiled modules. JPMS is available starting in Java 9.

## 9. Checklist Before Running a Modular Application

1. The application module has `module-info.class` and the correct module name.
2. The main class resides in the application module and has a valid entry point.
3. All required dependencies can be found on the module path or in parent layers.
4. The command uses `--module-path` to point to the exact location of the modules.
5. The command uses `-m module/main-class`, or the module descriptor already records the main class.
6. Application arguments appear after the module/main-class part.
7. If you encounter resolution errors, use `--show-module-resolution` and `--describe-module` to inspect the module graph and descriptor.

## Takeaways

`java -m module/main-class` instructs the Java launcher to run a named module and invoke the main class inside that module. `--module-path` specifies where to locate modules; the launcher resolves the root module along with its dependencies before executing the program. You can omit the main class from the command when the module descriptor already stores `ModuleMainClass`, typically set with `jar --main-class`. Use `--show-module-resolution` and `--describe-module` to understand which modules the launcher is resolving when debugging.
