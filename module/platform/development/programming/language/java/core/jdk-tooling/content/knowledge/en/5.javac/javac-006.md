# Compiling Java Modules with the Module Path

## 1. What is the module path in the compilation process?

The Java Platform Module System (JPMS), introduced in Java 9, allows applications to organize code into named modules. Each named module declares its name, its module dependencies, and the packages accessible from outside. The `module-info.java` file is the module descriptor that describes that contract.

When compiling a module, `javac` needs to locate:

- The source code of the module being compiled.
- The modules that the module declares via `requires`.
- The packages that dependent modules export via `exports`.
- The JDK platform modules required by the source code.

The **module path** is the path the compiler uses to locate compiled or packaged modules. The primary option is `--module-path` (short form `-p`). It can contain modular JARs and directories of compiled modules (exploded modules).

The compile-time module path does not automatically configure the runtime module path. The `java` command must also receive the corresponding module path when launching the application.

General command:

~~~bash
javac --module-path <module-path> -d <output-dir> <source-files>
~~~

When compiling multiple modules from a source directory tree, add `--module-source-path` and `--module`:

~~~bash
javac --module-source-path <source-root> --module <module-name> -d <output-dir>
~~~

Do not confuse these three concepts:

| Path | Purpose |
|---|---|
| `--class-path` or `-cp` | Locates classes and JARs on the classpath, typically in the unnamed module. |
| `--module-path` or `-p` | Locates compiled named modules or modular JARs. |
| `--module-source-path` | Locates the source code of multiple modules following the module directory structure. |

## 2. Module descriptor: `requires` and `exports`

A minimal module can be declared as follows:

~~~java
module com.example.greetings {
    exports com.example.greetings;
}
~~~

The module name is `com.example.greetings`. Only the `com.example.greetings` package is exported so that other modules can use the public types in that package. Non-exported packages remain encapsulated from other modules under JPMS accessibility rules.

An application module can declare a dependency:

~~~java
module com.example.app {
    requires com.example.greetings;
}
~~~

Key directives:

- `requires module.name;` declares that the current module needs to read another module.
- `requires transitive module.name;` allows dependent modules to also read the required module through this dependency relationship.
- `requires static module.name;` declares a dependency required at compile time but optional at runtime.
- `exports package.name;` allows other modules to access public types in the package.
- `exports package.name to other.module;` exports the package only to one or more named modules.
- `opens package.name;` opens the package for deep reflection access at runtime; it does not replace `exports` for compiling source code that accesses public types.
- `uses` and `provides ... with ...` declare service consumer/provider relationships.

Every module can read `java.base` without explicitly declaring `requires java.base;`. This is the foundational module containing core types such as `String`, `Object`, and `System`.

## 3. Example of two modules with a dependency

Create a source directory tree organized by module name:

~~~text
project/
└── src/
    ├── com.example.greetings/
    │   ├── module-info.java
    │   └── com/
    │       └── example/
    │           └── greetings/
    │               └── Greeting.java
    └── com.example.app/
        ├── module-info.java
        └── com/
            └── example/
                └── app/
                    └── Main.java
~~~

The library module `com.example.greetings`:

File `src/com.example.greetings/module-info.java`:

~~~java
module com.example.greetings {
    exports com.example.greetings;
}
~~~

File `src/com.example.greetings/com/example/greetings/Greeting.java`:

~~~java
package com.example.greetings;

public class Greeting {
    public static String message(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

The application module `com.example.app`:

File `src/com.example.app/module-info.java`:

~~~java
module com.example.app {
    requires com.example.greetings;
}
~~~

File `src/com.example.app/com/example/app/Main.java`:

~~~java
package com.example.app;

import com.example.greetings.Greeting;

public class Main {
    public static void main(String[] args) {
        String name = args.length == 0 ? "Java modules" : args[0];
        System.out.println(Greeting.message(name));
    }
}
~~~

The two modules have an explicit relationship: the application requires the library module, and the library exports the package containing the API being used. If `requires com.example.greetings;` or `exports com.example.greetings;` is omitted, the compiler will report an error because the application module cannot read the module or cannot access the corresponding package.

## 4. Compiling multiple modules with `--module-source-path`

With the directory tree above, run from the `project` directory:

~~~bash
javac --release 17 --module-source-path src -d out --module com.example.greetings,com.example.app
~~~

Explanation:

- `--release 17` instructs the compiler to check against Java 17 language, bytecode, and APIs.
- `--module-source-path src` specifies the root directory containing the module source directories.
- `-d out` places the compilation output into the `out` directory.
- `--module com.example.greetings,com.example.app` requests compiling the two listed modules.

The output structure looks like:

~~~text
out/
├── com.example.greetings/
│   ├── module-info.class
│   └── com/
│       └── example/
│           └── greetings/
│               └── Greeting.class
└── com.example.app/
    ├── module-info.class
    └── com/
        └── example/
            └── app/
                └── Main.class
~~~

Run the application module using the Java launcher:

~~~bash
java --module-path out -m com.example.app/com.example.app.Main
~~~

Stdout:

~~~text
Hello, Java modules!
~~~

Passing an argument:

~~~bash
java --module-path out -m com.example.app/com.example.app.Main "Ada Lovelace"
~~~

Stdout:

~~~text
Hello, Ada Lovelace!
~~~

Here `out` is the runtime module path because it contains the two compiled module directories. The `-m` option specifies the main module and the class containing the `main` method. The class name must be fully qualified, including its package.

## 5. Compiling modules one by one in dependency order

Another approach is to compile the library module first, then put the library's output directory on the module path when compiling the application module.

From the `project` root directory:

~~~bash
# Compile the library module
javac --release 17 -d mods/com.example.greetings src/com.example.greetings/module-info.java src/com.example.greetings/com/example/greetings/Greeting.java

# Compile the application module using the compiled library module
javac --release 17 --module-path mods -d mods/com.example.app src/com.example.app/module-info.java src/com.example.app/com/example/app/Main.java

# Run the application module
java --module-path mods -m com.example.app/com.example.app.Main
~~~

Stdout:

~~~text
Hello, Java modules!
~~~

This approach is useful when a build pipeline splits modules into separate steps, or when the library module has already been built and packaged. The `mods` path contains the compiled `com.example.greetings` module; the compiler can read its module descriptor and exported public classes from there.

When compiling the application module, `--module-path mods` is a compile-time configuration. At runtime, you must pass the module path to the launcher again as shown in the last command. Specifying the module path only in `javac` does not make the JVM automatically know where modules are located at runtime.

## 6. Compiling a module that depends on an external modular JAR

In real-world projects, a dependent module may be distributed as a JAR. Suppose the `lib` directory contains `com.example.greetings.jar`, a modular JAR with `module-info.class`.

You can compile the application module as follows:

~~~bash
javac --release 17 --module-path lib -d out src/com.example.app/module-info.java src/com.example.app/com/example/app/Main.java
~~~

And run it:

~~~bash
java --module-path "out:lib" -m com.example.app/com.example.app.Main
~~~

On Windows, the separator between path elements is a semicolon:

~~~powershell
java --module-path "out;lib" -m com.example.app/com.example.app.Main
~~~

The module name declared in the library's `module-info.java` must match the name in the `requires` directive. The JAR filename does not determine the name of an explicit named module when the JAR already contains a module descriptor.

You can inspect a JAR's module descriptor with:

~~~bash
jar --describe-module --file lib/com.example.greetings.jar
~~~

If the compiler reports that the module cannot be found, verify that the JAR resides directly inside a valid module path entry, the module descriptor declares the correct name, and the name in `requires` matches the actual module name.

## 7. How do module path and classpath differ?

The classpath and module path address two different packaging models:

| Characteristic | Classpath | Module path |
|---|---|---|
| Unit of organization | Classes and packages | Named modules |
| Dependency description | Usually supplied by the build tool or runner | Declared in `module-info.java` via `requires` |
| Package visibility | No module encapsulation rules | Only exported packages form the API for other modules |
| Module name | Classes on the classpath belong to the unnamed module | Modules have explicit names |
| How to launch | `java -cp ... package.Main` | `java -p ... -m module/package.Main` |
| Compatibility | Fits many legacy Java libraries | Fits modularized applications/libraries |

A named module cannot automatically read the unnamed module on the classpath. When you must use a legacy library placed on the classpath, you can add a temporary read edge with `--add-reads module.name=ALL-UNNAMED`. A more sustainable approach is to use a modular JAR or an automatic module when supported by the library, and explicitly manage dependency versions.

Do not mix paths by guesswork. If a library is placed on the classpath, it does not become a named module just because the application has a `module-info.java`. If you place a JAR without a module descriptor on the module path, the compiler can treat it as an automatic module with its own compatibility rules.

## 8. Automatic modules and unmodularized libraries

A JAR without `module-info.class` can be placed on the module path as an automatic module. The automatic module name can be taken from the `Automatic-Module-Name` attribute in the manifest; if absent, the name is usually derived from the JAR filename. Derived names can change when filenames or versions change, so avoid relying on them when a better option is available.

An automatic module typically exports all its packages and reads other named modules to support gradual migration from the classpath to JPMS. However, this is a compatibility mechanism and does not replace a well-designed module descriptor.

Inspect the JAR:

~~~bash
jar --describe-module --file lib/legacy-library.jar
~~~

When using an automatic module, the `requires` directive in the application module must use the exact module name reported by the tool. For libraries controlled by your development team, declare a stable `Automatic-Module-Name` or convert the library into a modular JAR when appropriate.

A few notes:

- A JAR on the classpath belongs to the unnamed module; a JAR on the module path can become an automatic module.
- Automatic modules do not provide the strict package encapsulation of explicit named modules.
- Do not guess the module name from Maven/Gradle artifact coordinates; check with `jar --describe-module` or the library's documentation.
- Test both compile-time and runtime behavior after moving a library from the classpath to the module path.

## 9. Module-related `javac` options

| Option | Meaning and use case |
|---|---|
| `--module-path path` or `-p path` | Sets the path to locate application modules and library modules. |
| `--module-source-path path` | Sets the root path containing source code for multiple modules following the module directory layout. |
| `--module name` or `-m name` | Specifies the module(s) to compile; multiple modules can be comma-separated. |
| `--add-modules name` | Adds root modules to module resolution; supports `ALL-MODULE-PATH` to add all modules on the module path. |
| `--limit-modules name` | Limits the set of observable modules for the compiler. |
| `--add-reads module=other` | Adds a readability edge between two modules, typically used for compatibility or diagnostics. |
| `--add-exports module/package=target` | Temporarily exports a package to a target module; `ALL-UNNAMED` can be used for unnamed modules. |
| `--patch-module module=path` | Augments or overrides classes/resources in a module during compilation, mainly for testing or special cases. |
| `--upgrade-module-path path` | Provides replacement modules for upgradeable system modules; rarely used in normal application builds. |
| `--module-version version` | Records the module version for the modules being compiled. |
| `--processor-module-path path` | Sets a separate module path for annotation processors. |

A few examples:

~~~bash
# Add a root module to resolve from the module path
javac --module-path lib --add-modules com.example.optional -d out src/com.example.app/module-info.java src/com.example.app/com/example/app/Main.java

# Temporarily allow the application module to read the unnamed module on the classpath
javac --module-path lib --class-path legacy.jar --add-reads com.example.app=ALL-UNNAMED -d out src/com.example.app/module-info.java src/com.example.app/com/example/app/Main.java

# Temporarily export an internal package to a specific module
javac --add-exports java.base/sun.nio.ch=com.example.app -d out src/com.example.app/module-info.java src/com.example.app/com/example/app/Main.java
~~~

`--add-reads` and `--add-exports` adjust the module graph at compile time. If the application also needs that behavior at runtime, the corresponding flags must be passed to the Java launcher. In particular, exporting internal JDK packages may depend on implementation details and is not a stable public API; prefer standard APIs over depending on internal packages.

`--patch-module` must also be considered at both compile time and runtime if the same code is compiled and run under a patched configuration. Do not use these options to mask module design issues in normal applications.

## 10. Combining `--release`, warnings, and the module path

`--release 17` allows building with a newer JDK while restricting source, bytecode, and APIs to Java 17. This is usually clearer than setting `-source 17` and `-target 17` separately.

Example:

~~~bash
javac --release 17 -Xlint:all -Werror --module-path lib -d out src/com.example.app/module-info.java src/com.example.app/com/example/app/Main.java
~~~

- `-Xlint:all` enables common compiler warnings.
- `-Werror` treats warnings as errors, which is useful in CI once the project has resolved existing warnings.
- `--module-path lib` lets the compiler resolve dependent modules.
- `-d out` places the compiled class files and module descriptor into the build output directory.

If enabling `-Werror` on an older project, address existing warnings first to avoid build failures caused by warnings unrelated to new changes.

You can ask the compiler to print detailed activity with `-verbose` or enable module-related warnings with `-Xlint:module` when diagnosing issues. Use `javac --help` and `javac --help-extra` from the exact JDK in your build environment to verify the options supported by that version.

## 11. Reading and troubleshooting module path errors

| Message / Symptom | Common Cause | Resolution |
|---|---|---|
| `module not found: com.example.lib` | Module is not on the module path or the name in `requires` is incorrect. | Check the path, JAR/module descriptor contents, and the actual module name. |
| `package ... is not visible` | The package is not exported by its owning module to the calling module. | Add `exports` for the package in the API-providing module, or use another public API. |
| `module ... does not read ...` | The application module has not declared the required dependency. | Add `requires` to the module descriptor. |
| `package ... does not exist` | The package is not on the appropriate module path/classpath or the source path is wrong. | Distinguish module sources from library dependencies; check `--module-source-path` and `--module-path`. |
| `not in a module on the module source path` | Source directory layout does not match module names or the compiler did not receive the module source path. | Place source code under directories named after the module and pass the proper root to `--module-source-path`. |
| Module found at compile time but not at runtime | Module path configured only for `javac`, not for `java`. | Pass the module path to the launcher command at runtime. |
| Module path has multiple JARs for the same module | Duplicate dependencies or inconsistent versions. | Remove duplicates and pin dependency versions in the build tool. |
| Works on dev machine but CI reports missing module | CI uses a different JDK, build directory, or dependency set. | Pin the JDK/toolchain, cache dependencies properly, and print the module path configuration when diagnosing. |

An ordered diagnostic checklist:

1. Check the compiler version with `javac --version`.
2. Verify that the module descriptor has the right name and `requires`/`exports` directives.
3. Verify that the module path contains the expected modular JARs or exploded modules.
4. If compiling multiple modules from source, check the directory layout and `--module-source-path`.
5. Run `jar --describe-module` on dependent JARs to confirm their actual module names.
6. Verify that the `java` runtime command uses the same set of required modules.
7. Check for duplicate JAR versions or legacy libraries placed on the wrong path.

## 12. Integrating the module path with Maven, Gradle, and CI

In projects using Maven or Gradle, the build tool typically manages dependencies, compilation order, and compiler arguments. When a project has `module-info.java`, ensure that required dependencies are resolved under the appropriate module model and that the compiler is configured with the right JDK.

Practical guidelines:

- Pin the JDK/toolchain and target Java version in the build configuration.
- Use `--release 17` when the artifact must be compatible with Java 17.
- Do not manually concatenate classpath and module path strings in hard-to-maintain ways; let the build tool manage dependencies if the project already uses Maven/Gradle.
- Verify the module names of external libraries, especially automatic modules.
- Run clean builds in CI to prevent stale class files from hiding dependency errors.
- Keep compile and run commands consistent: modules resolved at compile time must also be provided at runtime or in the packaged distribution.
- If using annotation processors, check `--processor-module-path` or the processor path configured by the build tool separately.

When a build fails, extract the actual compiler command from Maven/Gradle logs. Looking only at high-level dependency configuration without inspecting the final command can miss differences between the classpath and module path.

## 13. Module compilation checklist

- Each named module has a `module-info.java` with a unique, accurate name.
- Packages used by other modules are declared with `exports`.
- The application's module descriptor has `requires` for every module it needs to read.
- Multi-module source code is arranged in a directory layout compatible with `--module-source-path`.
- Required modular JARs and exploded modules are on `--module-path`.
- `--module` is used to select the right modules to compile when multiple source modules exist.
- `--release` is used to pin the target API and bytecode version.
- The runtime module path is configured in the `java` command or packaging configuration.
- Legacy libraries are not placed on the wrong path; automatic module names are verified when using legacy JARs on the module path.
- Program stdout and exit code are verified after a successful compilation.

When compiling a JPMS application, declare relationships using `requires`/`exports`, place dependent modules on `--module-path`, and use `--module-source-path` when compiling multiple modules from a single source tree. After the compiler generates the module output, pass that output to the Java launcher's module path to run the application module.
