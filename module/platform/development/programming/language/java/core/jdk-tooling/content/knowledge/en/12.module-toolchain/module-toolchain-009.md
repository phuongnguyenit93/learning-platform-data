# Module Path in Java

## 1. What is the module path?

The **module path** is the list of locations where the compiler or JVM searches for Java modules. It is a component of the Java Platform Module System (JPMS), introduced in Java 9.

In the module system, each named module declares its name and dependencies in a `module-info.java` file. The module path enables Java tools to locate modules, read module descriptors, resolve `requires` declarations, and determine which packages are exposed via `exports`.

The module path typically contains:

- **Modular JAR:** A JAR containing a `module-info.class` module descriptor.
- **Automatic module JAR:** A JAR without a module descriptor that is placed on the module path; its module name is derived from its manifest or filename.
- **Exploded module:** A compiled module directory containing `module-info.class` at its root.
- **Module directory:** A directory containing modular JARs or exploded module directories inside it.

For example, a project might place compiled modules in `mods` or modular JARs in `lib`. At runtime, the JVM receives these locations via the `--module-path` option.

## 2. Why is the module path needed?

The module path gives Java applications a clear structure when a project consists of multiple modules or uses modular libraries.

Key benefits:

- **Dependency resolution:** The JVM locates modules declared via `requires`.
- **Access control:** A module only exposes packages declared via `exports`; deep reflection may require `opens`.
- **Conflict detection:** The module system can detect duplicate module names, split packages across modules, or invalid dependencies.
- **Selective deployment:** `jlink` uses the module path to create a runtime image containing only the required modules.
- **Separation of source code and libraries:** Source modules, compiled modules, and modular libraries can reside in separate locations.

The module path is not merely a directory of JARs. The JVM uses it to locate modules and build the module graph based on descriptors and dependency relationships.

## 3. Distinguishing the module path and classpath

The classpath is the traditional class lookup mechanism. The module path is used to locate and resolve named modules.

| Criterion | Classpath | Module path |
|---|---|---|
| Option | `--class-path`, `-classpath`, or `-cp` | `--module-path` or `-p` |
| Contents | Class directories, regular JARs | Modular JARs, automatic module JARs, exploded modules, or directories containing modules |
| Organization | Classes belong to the unnamed module | Named modules are located and resolved |
| Package control | No JPMS boundaries between JARs | Descriptors control `requires`, `exports`, and `opens` |
| Launching | Main class name or `-jar` | Module name via `-m` or `--module` |

Classpath example:

```bash
java -cp "out:lib/*" com.example.Main
```

Module path example:

```bash
java --module-path lib --module com.example.app/com.example.app.Main
```

On Windows, the path element separator is a semicolon (`;`). On Linux and macOS, the separator is a colon (`:`).

You cannot simply change `-cp` to `-p` and expect a classpath application to automatically become modular. A named module application requires a module descriptor and proper dependency configuration.

### 3.1. Named modules and unnamed modules

Classes loaded from the classpath belong to the unnamed module of their respective class loader. Classes in a modular JAR or exploded module can belong to a named module.

A named module cannot declare `requires` directly on an unnamed module. Therefore, if a modular application needs a legacy library without a module descriptor, that JAR can be placed on the module path so Java treats it as an automatic module, provided the library is compatible with this mechanism.

## 4. Structure of the module path

The module path consists of one or more path elements. Each element can point to a single module or a directory containing multiple modules.

Example with compiled modules:

```text
project/
├── mods/
│   ├── com.example.app/
│   │   ├── module-info.class
│   │   └── com/example/app/Main.class
│   └── com.example.greeter/
│       ├── module-info.class
│       └── com/example/greeter/Greeter.class
└── src/
```

Here, `mods` is a directory containing exploded modules. When `--module-path mods` is passed, the JVM searches for each module inside that directory.

Example with modular JARs:

```text
project/
├── lib/
│   ├── com.example.app.jar
│   └── com.example.greeter.jar
└── src/
```

`lib` is a directory containing modular JARs. You can pass the `lib` directory itself to the module path.

A path element can also be a direct path to a modular JAR or the root directory of an exploded module. Avoid placing multiple versions with the same module name in different locations, as the module found first can shadow later versions.

## 5. Declaring a module with module-info.java

Each named module has a module descriptor declared in `module-info.java`. During compilation, the compiler generates `module-info.class` at the root of the module.

Example library module:

```java
module com.example.greeter {
    exports com.example.greeter;
}
```

This declaration means:

- The module name is `com.example.greeter`.
- The package `com.example.greeter` is exposed to other modules.
- Other packages in the module, if any, are not exported automatically.

An application module can declare a dependency:

```java
module com.example.app {
    requires com.example.greeter;
}
```

`requires` indicates that the application module needs the library module. When the compiler or JVM resolves the module graph, it looks for `com.example.greeter` on the module path.

Common directives:

| Directive | Meaning |
|---|---|
| `requires` | Declares a module dependency |
| `requires transitive` | Passes readability of the dependency module to modules that read the current module |
| `requires static` | Dependency required at compile time but optional at runtime |
| `exports` | Exposes a package to other modules |
| `exports ... to` | Exposes a package only to the named modules |
| `opens` | Allows deep reflective access to a package |
| `uses` | Declares that the module uses a service |
| `provides ... with` | Declares an implementation provided for a service |

The module name is determined by the descriptor or automatic module rules, and does not necessarily match the directory name or JAR filename.

## 6. The --module-path and -p options

The `--module-path` option specifies where to find application modules. Its shorthand form is `-p`.

Syntax:

```bash
java --module-path <module-path> ...
javac --module-path <module-path> ...
```

Example:

```bash
java --module-path mods --module com.example.app/com.example.app.Main
```

Components:

- `--module-path mods`: searches for modules in the `mods` directory.
- `--module`: selects the module to launch.
- `com.example.app/com.example.app.Main`: module name, forward slash, and main class name.

Shorthand form:

```bash
java -p mods -m com.example.app/com.example.app.Main
```

`-p` is equivalent to `--module-path`; `-m` is equivalent to `--module` in the launcher command.

### 6.1. Multiple locations on the module path

You can provide multiple path elements so modules can reside in different directories or archives.

Windows PowerShell:

```powershell
java --module-path "mods;lib" --module com.example.app/com.example.app.Main
```

Linux/macOS:

```bash
java --module-path "mods:lib" --module com.example.app/com.example.app.Main
```

Paths containing spaces should be enclosed in double quotes. Use the correct separator for your operating system; mixing up `;` and `:` is a common configuration error.

### 6.2. Direct path to a single module

If you only have a single modular JAR, you can specify that file directly:

```bash
java --module-path lib/com.example.greeter.jar --describe-module com.example.greeter
```

If multiple modules depend on one another, include all required locations on the module path, typically a directory containing the modular JARs or a list of path elements.

## 7. Module path when compiling with javac

`javac` also supports the module path. During compilation, the compiler needs to locate modules declared in source code via `requires` to verify types and access permissions.

Example when the library module is already packaged in `lib`:

```bash
javac --module-path lib -d out --module-source-path src --module com.example.app
```

In the command above:

- `--module-path lib` locates compiled or packaged modules, such as `com.example.greeter`.
- `--module-source-path src` specifies where to find the source code of the modules being compiled.
- `-d out` specifies the output directory.
- `--module com.example.app` selects the source module to compile.

Distinguish between the two options:

| Option | Used to locate |
|---|---|
| `--module-path` | Compiled or packaged dependency modules |
| `--module-source-path` | Source code of the modules being compiled |

`--module-source-path` is useful when compiling multiple modules at once. It does not replace the module path used to locate compiled dependencies.

## 8. Complete example: two modules sharing a module path

The following example creates a library module and an application module. This is a Java 17+ program that can be compiled and run with a full JDK.

### 8.1. Creating the source structure

```text
module-path-demo/
└── src/
    ├── com.example.greeter/
    │   ├── module-info.java
    │   └── com/example/greeter/Greeter.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java
```

File `src/com.example.greeter/module-info.java`:

```java
module com.example.greeter {
    exports com.example.greeter;
}
```

File `src/com.example.greeter/com/example/greeter/Greeter.java`:

```java
package com.example.greeter;

public final class Greeter {
    private Greeter() {
    }

    public static String message() {
        return "Hello from module path";
    }
}
```

File `src/com.example.app/module-info.java`:

```java
module com.example.app {
    requires com.example.greeter;
}
```

File `src/com.example.app/com/example/app/Main.java`:

```java
package com.example.app;

import com.example.greeter.Greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.message());
    }
}
```

The application declares `requires com.example.greeter`. The library module declares `exports com.example.greeter` so the application can access the package containing the `Greeter` class.

### 8.2. Compiling both modules into exploded modules

From the `module-path-demo` root directory, create the output directory.

Linux/macOS:

```bash
mkdir -p mods
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force mods
```

Compile both modules:

```bash
javac --module-source-path src -d mods --module com.example.greeter,com.example.app
```

After compilation, the output structure looks like:

```text
mods/
├── com.example.greeter/
│   ├── module-info.class
│   └── com/example/greeter/Greeter.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
```

Each subdirectory is an exploded module. `mods` is a directory containing modules, so it can be used as the module path.

### 8.3. Running the application from the module path

Run:

```bash
java --module-path mods --module com.example.app/com.example.app.Main
```

Exact stdout:

```text
Hello from module path
```

The JVM locates the `com.example.app` module in `mods`, reads its descriptor, resolves `requires com.example.greeter`, and then launches the `com.example.app.Main` class.

You can write this more concisely:

```bash
java -p mods -m com.example.app/com.example.app.Main
```

Both commands have the same meaning.

### 8.4. Packaging modules into modular JARs

From the project root directory, create the `lib` directory:

```bash
mkdir -p lib
```

Create modular JARs for the library and the application:

```bash
jar --create --file lib/com.example.greeter.jar -C mods/com.example.greeter .
jar --create --file lib/com.example.app.jar -C mods/com.example.app .
```

Each JAR retains `module-info.class` at its root. Therefore, they remain modular JARs.

Inspect the library module descriptor:

```bash
jar --describe-module --file lib/com.example.greeter.jar
```

Run the application using the directory containing the two JARs:

```bash
java --module-path lib --module com.example.app/com.example.app.Main
```

Stdout remains:

```text
Hello from module path
```

This example shows that the module path can point to a directory containing modular JARs or a directory containing exploded modules.

## 9. Modular JARs and automatic modules

Not every JAR has a `module-info.class`. When a JAR without a descriptor is placed on the module path, Java can treat it as an **automatic module**.

The automatic module name is determined in the following order:

1. Use the `Automatic-Module-Name` attribute in the manifest if present.
2. Otherwise, derive the name from the JAR filename according to JPMS rules.

Example:

```text
lib/
└── legacy-utils-2.4.jar
```

If a JAR lacks `module-info.class` and does not declare `Automatic-Module-Name`, the module name is derived from the filename. The exact name should be verified using a JDK tool rather than guessed.

Automatic modules have broad compatibility behavior to support legacy libraries, such as exporting all of their packages and reading all observable modules. However, automatic modules should not be treated as a complete modular design.

When a stable module name is needed, library maintainers should declare `Automatic-Module-Name` in the manifest or publish a modular JAR with an official module descriptor.

## 10. Module resolution rules on the module path

When launching a named module, the JVM performs module resolution to determine the module graph.

Conceptually:

1. The main module is selected as the root module.
2. The JVM reads the root's module descriptor.
3. Modules declared via `requires` are searched on the module path or in the runtime image.
4. The process continues for transitive dependencies.
5. The JVM validates the graph, including module names and package exports.
6. Resolved modules become part of the runtime configuration.

Important rules:

- Module names must be unique within the module graph.
- Two modules must not create a conflicting split package in the graph.
- A module must export a package for another module to access public types in that package.
- `requires transitive` affects module readability along the dependency chain.
- Module path order can affect which module is found first if duplicate names exist; avoid keeping multiple versions with the same name on the path.

The module path does not automatically add every discovered module to the graph. Which modules get resolved depends on the root module, `requires` directives, and additional options such as `--add-modules`.

## 11. Related module options

In addition to `--module-path`, the Java launcher provides options to control the module graph.

| Option | Purpose |
|---|---|
| `--module` or `-m` | Runs the main class in a module |
| `--add-modules` | Adds root modules to the resolution process |
| `--limit-modules` | Limits the set of observable modules |
| `--upgrade-module-path` | Provides replacements for upgradeable system modules |
| `--patch-module` | Supplements or overrides classes/resources in a specific module |
| `--show-module-resolution` | Prints module resolution diagnostic output |
| `--validate-modules` | Validates all observable modules |
| `--list-modules` | Lists observable modules and exits |
| `--describe-module` | Displays the descriptor of the specified module |

Example of adding a root module:

```bash
java --module-path lib --add-modules com.example.greeter --list-modules
```

`--add-modules` is useful when a module is not pulled into the graph solely by existing dependencies yet still needs to be resolved, such as a service provider module.

Viewing module resolution when running an application:

```bash
java --show-module-resolution --module-path lib --module com.example.app/com.example.app.Main
```

The `--show-module-resolution` option prints information about resolved modules. The program still executes and prints its output.

Validating modules on the module path:

```bash
java --validate-modules --module-path lib
```

`--upgrade-module-path` and `--patch-module` are specialized options. They are not the standard way to add application libraries; application dependencies should be placed on the module path and declared with `requires`.

## 12. Module path when using jlink

`jlink` creates a custom runtime image from resolved modules. This tool also accepts a module path via `--module-path` or `-p`.

Example of creating a runtime image containing the modular application in `lib`.

Linux/macOS:

```bash
jlink --module-path "$JAVA_HOME/jmods:lib" --add-modules com.example.app --output app-runtime
```

Windows PowerShell:

```powershell
jlink --module-path "$env:JAVA_HOME\jmods;lib" --add-modules com.example.app --output app-runtime
```

Here:

- `$JAVA_HOME/jmods` provides the JDK JMODs.
- `lib` provides the application's modular JARs.
- `--add-modules com.example.app` selects the application module as the root; dependencies are resolved according to descriptors.
- `--output app-runtime` specifies the directory for the generated runtime image.

`jlink` can use JMODs at link time. When running an application with the regular `java` command, use modular JARs or exploded modules on the module path in formats supported by the launcher; do not assume JMODs can be used like modular JARs at runtime.

## 13. Module path in IDEs and build tools

In real-world projects, the module path can be configured in an IDE or build tool instead of typing launcher commands directly.

### 13.1. IntelliJ IDEA

For modular projects:

- Ensure the directory containing `module-info.java` is recognized as an appropriate source root.
- Select a JDK that supports JPMS.
- Verify module dependencies and the module descriptor.
- Check that the Run Configuration selects the right module or module path.
- Confirm that modular libraries are placed on the module path if the project requires JPMS.

If running from the terminal works but the IDE reports that a module cannot be found, check the Run Configuration's module settings and the libraries attached to the module.

### 13.2. Eclipse

Eclipse supports Java modules in projects using a compatible JDK. Check:

- The JRE System Library points to a suitable JDK.
- `module-info.java` is recognized within a source folder.
- Module dependencies are declared properly.
- The Run Configuration uses the module path when launching a named module.

### 13.3. Maven and Gradle

Maven and Gradle can compile, test, and package modular projects. Exact configuration depends on plugins and build tool versions.

Points to verify:

- Source code has `module-info.java` and properly structured packages.
- Dependencies are placed on the module path if they are modular dependencies.
- The compiler release and the JDK running the build tool are compatible.
- The test runner uses the proper module path or configures the necessary module openings.
- The packaged JAR artifact retains the module descriptor.

Do not look only at Maven/Gradle dependency configuration and assume the runtime module path is correct. Verify the actual build, test, and launch commands.

## 14. Diagnosing and inspecting the module path

When the JVM cannot find a module or resolution fails, inspect each layer of configuration.

Useful commands:

```bash
java --list-modules
java --module-path lib --list-modules
java --module-path lib --describe-module com.example.greeter
jar --describe-module --file lib/com.example.greeter.jar
```

You can use `jdeps` to analyze an application's module dependencies:

```bash
jdeps --module-path lib --check com.example.app
```

When troubleshooting, verify:

1. The path exists and the shell passed the intended value to Java.
2. The module path points to the right module directory or module file.
3. The modular JAR has `module-info.class` in a valid location.
4. Any automatic module has a valid module name.
5. Names in `requires` match actual module names.
6. Required packages are exported.
7. No two versions of the same module name cause shadowing or conflicts.
8. Source modules are compiled properly with `--module-source-path`.
9. The JDK used for compiling and running supports the project's module/class file version.

## 15. Common errors when configuring the module path

| Symptom | Common cause | Resolution |
|---|---|---|
| `Module ... not found` | Incorrect module path or missing module dependency | Check directories, module names, and JAR files |
| `Module ... does not read ...` | The module graph lacks the required readability edge | Declare `requires` properly in the module descriptor |
| `package ... is not visible` | The package is not exported by its owning module | Add the appropriate `exports` or use a public API |
| `FindException` at startup | Corrupted module archive, invalid descriptor, or duplicate name | Inspect the JAR with `jar --describe-module` and remove duplicates |
| `ResolutionException` | Dependency or package conflict in the module graph | Check `requires`, split packages, and modules with identical names |
| Works with `-cp` but fails with `-p` | Legacy library on classpath not yet adapted as a valid module | Move compatible JARs to the module path or redesign module boundaries |
| `java -jar` does not run as a named module | `-jar` is a classpath-based JAR launch mode | Use `--module-path` and `--module` for modular applications |
| Source module not found | `--module-path` used by mistake instead of `--module-source-path` | Set the source root properly and use the source option |
| Multiple versions of the same name on module path | Multiple artifacts with the same module name across path elements | Keep one chosen version and check path ordering |

A common mistake is confusing the module name with the JAR filename. Use `jar --describe-module` or `java --describe-module` to determine the module name rather than inferring it solely from the filename.

## 16. Standard workflow for configuring the module path

When adding a dependency or running a modular application:

1. Identify the application module and read `module-info.java`.
2. List the modules declared in `requires`.
3. Determine whether each dependency is a modular JAR, automatic module, or exploded module.
4. Place modules in a clear directory or path element.
5. Configure `--module-path` when compiling and running.
6. When compiling multiple source modules, also use `--module-source-path`.
7. Launch the named module with `--module` or `-m`.
8. Inspect the module descriptor, module graph, and package exports if errors occur.
9. Remove duplicate-named modules from the module path.
10. If creating a runtime image, provide the appropriate module path to `jlink`.
11. Document the JDK version, module locations, and build/run commands so team members can reproduce the environment.

Standardize module names and dependency directory layouts across the team. This reduces errors caused by different machines using different paths or library versions.

## 17. Summary

The module path is the mechanism for locating and resolving named modules in the Java module system. It enables the compiler, JVM, and `jlink` to find the right modules, verify dependencies, and build the module graph.

Key takeaways:

- `--module-path` or `-p` specifies where to search for modules.
- The module path can contain modular JARs, automatic module JARs, exploded modules, or directories containing modules.
- `module-info.java` declares the module name, `requires`, `exports`, and related directives.
- `--module-source-path` locates module source code; `--module-path` locates module dependencies.
- `--module` or `-m` is used to launch a named module.
- Windows uses `;` to separate path elements; Linux and macOS use `:`.
- The classpath and module path serve two different organizational models; a named module cannot declare a direct dependency on an unnamed module.
- `jlink` uses the module path to build runtime images; JMODs are primarily for link time.
- When troubleshooting errors, check module names, descriptors, dependencies, exports, and duplicate versions on the path.

**Official references:**

- [The java Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [The javac Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [ModuleFinder API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/module/ModuleFinder.html)
