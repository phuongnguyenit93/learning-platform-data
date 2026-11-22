# javac --module and Compiling a Single Module

Since Java 9, the Java Platform Module System (JPMS) allows compiling and running applications by named modules. When compiling a module, the compiler needs to know three things: **where the module's source is located**, **which module needs to be compiled**, and **where the precompiled dependency modules are located**.

The `javac --module` command (abbreviated as `javac -m`) selects the module to compile. It is usually paired with `--module-source-path` to locate module sources and `--module-path` to locate compiled dependencies. Understanding these three options clearly helps you compile a single module without putting the entire project on the classpath.

The examples below use JDK 21 and a project consisting of two modules: `com.acme.api` and `com.acme.app`.

## 1. Source Structure of a Modular Project

Each module has a `module-info.java` file in the module's root directory. Java packages reside underneath that directory.

Example:

~~~text
project/
├── src/
│   ├── com.acme.api/
│   │   ├── module-info.java
│   │   └── com/acme/api/Greeter.java
│   └── com.acme.app/
│       ├── module-info.java
│       └── com/acme/app/Main.java
└── out/
~~~

The module directory names here are `com.acme.api` and `com.acme.app`; they must match the module names declared in `module-info.java`.

API module:

~~~java
module com.acme.api {
    exports com.acme.api;
}
~~~

File `src/com.acme.api/com/acme/api/Greeter.java`:

~~~java
package com.acme.api;

public class Greeter {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

Application module:

~~~java
module com.acme.app {
    requires com.acme.api;
}
~~~

File `src/com.acme.app/com/acme/app/Main.java`:

~~~java
package com.acme.app;

import com.acme.api.Greeter;

public class Main {
    public static void main(String[] args) {
        Greeter greeter = new Greeter();
        System.out.println(greeter.greet("JPMS"));
    }
}
~~~

Here:

- `com.acme.api` exports the `com.acme.api` package, so other modules can use the public API in this package.
- `com.acme.app` declares `requires com.acme.api`, creating an explicit module dependency.
- `com.acme.app` does not need to copy the API's source files or classes into its own packages.

A regular module automatically reads `java.base`; there is no need to write `requires java.base`.

## 2. Meaning of javac --module

General syntax:

~~~bash
javac --module-source-path <source-root> -d <output-directory> --module <module-name>
~~~

Options:

| Option | Meaning |
|---|---|
| `--module` or `-m` | Selects the module(s) to compile; multiple module names can be passed, separated by commas |
| `--module-source-path` | Specifies the source root containing module directories |
| `--module-path` or `-p` | Specifies where to find compiled or packaged dependency modules |
| `-d` | Specifies the directory for output class files |
| `--release` | Compiles against the API and language level of a specific Java release |

Example of compiling an independent module:

~~~bash
javac --module-source-path src -d out --module com.acme.app
~~~

This command instructs `javac` to look for the source of module `com.acme.app` in `src` and write the output to `out`. The example above only compiles if the module's dependencies are already available to resolve or the module has no uncompiled application dependencies.

`-m` is an equivalent short form:

~~~bash
javac --module-source-path src -d out -m com.acme.app
~~~

The name after `--module` is the **module name**, not a package name, class name, or directory path.

## 3. Compiling a Module with Dependencies

In the example, `com.acme.app` requires `com.acme.api`. There are two clear ways to compile.

### Approach A: Compile the Required Modules Together

~~~bash
javac --module-source-path src -d out --module com.acme.api,com.acme.app
~~~

`javac` finds both modules on the source path, compiles them, and writes the results to the output directory. This is convenient when the sources of both the dependency and the target module are in the same project.

The output has the structure:

~~~text
out/
├── com.acme.api/
│   ├── module-info.class
│   └── com/acme/api/Greeter.class
└── com.acme.app/
    ├── module-info.class
    └── com/acme/app/Main.class
~~~

Each module is placed in its own directory under the output directory. There is no need to manually create an output directory for each module.

### Approach B: Compile the Dependency First, Then Compile the Target Module Separately

Step 1 — compile the API module:

~~~bash
javac --module-source-path src -d out --module com.acme.api
~~~

Step 2 — compile the application module, using the existing output as the module path:

~~~bash
javac --module-path out --module-source-path src -d out --module com.acme.app
~~~

In Step 2:

- `--module-path out` tells `javac` that the compiled `com.acme.api` module is in `out`.
- `--module-source-path src` tells `javac` where the source of `com.acme.app` is located.
- `--module com.acme.app` selects the exact module to compile.
- `-d out` writes the application's class files into `out/com.acme.app`.

This approach is useful when you only modify the application module while the API module is already compiled or provided as a modular JAR.

If the dependency is in a JAR file, place that JAR file on the module path, for example:

~~~bash
javac --module-path "lib/com.acme.api.jar" --module-source-path src -d out --module com.acme.app
~~~

If there are multiple entries on the module path, separate them with the operating system's path separator: a colon on Linux/macOS and a semicolon on Windows.

## 4. Compiling and Running Modules on Windows PowerShell

In PowerShell, the command structure is the same. If you are at the project root directory:

~~~powershell
javac --module-source-path src -d out --module com.acme.api,com.acme.app
~~~

After compiling, run the main class using module syntax:

~~~powershell
java --module-path out --module com.acme.app/com.acme.app.Main
~~~

Short form:

~~~powershell
java -p out -m com.acme.app/com.acme.app.Main
~~~

Output:

~~~text
Hello, JPMS
~~~

The `module-name/main-class` syntax specifies which module the main class belongs to. If a module has multiple classes with the same name in different packages, the fully qualified main class name eliminates ambiguity.

If the module descriptor declares a main class in the JAR metadata, some launch forms can be shortened; in this lesson, explicitly specifying `module/main-class` makes it easy to understand and works consistently.

## 5. Distinguishing module-source-path and module-path

The two options have similar names, but serve two different data sources:

| Option | What Does It Contain? | When to Use? |
|---|---|---|
| `--module-source-path` | Module sources, including `module-info.java` and `.java` files | When `javac` needs to locate module sources to compile |
| `--module-path` | Compiled modules in exploded module or modular JAR form | When `javac` needs to resolve dependencies of the module being compiled |

For example, with:

~~~bash
javac --module-path out --module-source-path src -d out --module com.acme.app
~~~

- `src` is the source input.
- `out` is where `javac` looks for precompiled dependencies and also where it writes output.
- `com.acme.app` is the module selected to compile.

Do not use `--module-path` to point to a raw source directory that has not been built into compiled modules. Conversely, do not use `--module-source-path` in place of a directory containing modular JAR dependencies.

### Module Path vs. Classpath

The classpath serves classes and JARs on the classpath, typically belonging to the unnamed module. The module path provides named modules with descriptors and dependencies checked by JPMS.

If `module-info.java` has:

~~~java
requires com.acme.api;
~~~

then `javac` needs to find a module named `com.acme.api` on the module path or among the module sources selected for compilation. A JAR placed only on the classpath does not automatically become a named module `com.acme.api`.

For legacy libraries without a module descriptor, Java can treat some JARs as automatic modules when placed on the module path. The automatic module name depends on naming rules derived from the JAR; inspect it with JDK tools before using it in `requires`.

## 6. Compiling a Single Module in a Large Project

In a multi-module project, you often do not want to compile all modules every time. Specifying a single module with `--module` limits the compilation scope.

Suppose the source tree has:

~~~text
src/
├── com.acme.api/
├── com.acme.app/
├── com.acme.cli/
└── com.acme.testkit/
~~~

If compiling only `com.acme.cli`, the command can be:

~~~bash
javac --module-path out --module-source-path src -d out --module com.acme.cli
~~~

The condition is that the dependencies declared by `com.acme.cli` in `requires` are already available on the module path or provided in this compilation pass. If the CLI module requires `com.acme.api` and `com.acme.testkit`, and those two modules have not been compiled yet, compile them first or specify all required modules:

~~~bash
javac --module-source-path src -d out --module com.acme.api,com.acme.testkit,com.acme.cli
~~~

`javac` should not be treated as a build system that automatically infers the entire project's build order. In multi-module projects, Gradle or Maven typically manages the dependency graph and incremental compilation; `javac` is the compiler invoked by the build tool with predetermined inputs.

## 7. Inspecting the Module Descriptor and Compilation Output

After compiling, inspect the generated module:

~~~bash
java --module-path out --describe-module com.acme.app
~~~

This command asks the runtime to describe the `com.acme.app` module found on the module path. The output may show:

~~~text
com.acme.app
requires com.acme.api
requires java.base mandated
~~~

To inspect the descriptor class file:

~~~bash
javap -v out/com.acme.app/module-info.class
~~~

In the detailed output, look at the `Module` attribute: it contains the module name, `requires`, `exports`, `opens`, `uses`, and `provides` entries accordingly.

To see the modules present in the output directory:

~~~bash
java --module-path out --list-modules
~~~

Note: `--list-modules` lists the modules that the runtime finds on the module path along with system modules. If you only want to inspect a specific descriptor, `--describe-module` is usually easier to read.

## 8. Using --release to Pin the Target Java API

If the project needs compatibility with a specific Java release, you can add `--release`:

~~~bash
javac --release 21 --module-source-path src -d out --module com.acme.api,com.acme.app
~~~

`--release 21` instructs the compiler to use the language rules, bytecode, and platform APIs of Java 21. Only use releases supported by the installed JDK.

Do not combine `--release` with `--source` or `--target` in the same command. When using `--release`, the compiler already receives complete information about the target Java level.

If the project uses preview features, you need to add the corresponding preview configuration and ensure the same release is used for compile and run; that is a special case and does not need to be enabled for ordinary Java modules.

## 9. Common Errors and How to Handle Them

**Module not found on the module source path.** Check the directory structure: `src/com.acme.app/module-info.java`. The module directory name must match the name declared in the descriptor and the name after `--module`.

**Package does not exist or is not readable.** Check whether the module declares `requires` for the right API module, and whether the API module is on `--module-path` or compiled in the same pass. Also check whether the API package has been `exports`-ed.

**`module not found: com.acme.api`.** The API module may not be compiled yet, the module path may point to the wrong directory, or the JAR may not be a modular/automatic module with the name you requested. Run `java --module-path out --describe-module com.acme.api` to inspect the module path.

**`package ... is not visible`.** The module may have been resolved, but the package containing the needed type has not been exported. Add `exports package.name` to the descriptor of the module owning the package if it is intended to be public API.

**Compiles successfully but cannot run with `java -m`.** Check whether the runtime module path contains all required modules and whether `module/main-class` is specified accurately. Successful compilation does not guarantee the runtime path is configured properly.

**Passing a package name after `--module` by mistake.** `--module` accepts a module name such as `com.acme.app`, not `com.acme.app.Main`. The main class name is only passed in the run command after the slash.

**Putting multiple modules into the same output package tree.** With modular compilation, `javac` creates separate output directories by module name. Do not manually merge classes from multiple modules into a shared package directory; doing so breaks module boundaries and can cause split packages.

## 10. Practice

1. Create the source tree for `com.acme.api` and `com.acme.app` as shown in the example.
2. Compile both modules with `javac --module-source-path src -d out --module com.acme.api,com.acme.app`.
3. Delete the output directory, then compile the API separately first and compile the app separately using `--module-path out`.
4. Run the application with `java --module-path out --module com.acme.app/com.acme.app.Main`.
5. Try changing the name after `--module` to a package name or class name to observe the error, then fix it back to the module name.
6. Try removing `exports com.acme.api` from the API descriptor and recompiling to see the difference in package accessibility.
7. Use `java --describe-module com.acme.app` and `javap -v` to compare the descriptor after compilation.

When compiling modularly, identify the target module first, ensure the source tree is organized by module name, and provide compiled dependencies on the module path. `--module` limits which modules are compiled; `--module-source-path` locates sources; `--module-path` resolves dependencies; `-d` keeps each module's output in its own directory. Those four pieces form a repeatable and verifiable single-module compilation workflow.
