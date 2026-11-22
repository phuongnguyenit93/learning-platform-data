# Compiling Multiple Modules in Java

The Java Platform Module System (JPMS) allows splitting an application into named modules, declaring dependencies, and controlling which packages are exported. When a project has multiple modules, the compiler must see the source code or artifacts of each module, resolve dependency relationships, and generate class files for the appropriate module. The Java launcher then uses the module path to locate and launch the main module.

This article focuses on how to compile multiple modules using JDK tools, specifically `javac`, `jar`, and `java`. The examples use Java 17 or later and two small modules to illustrate the entire flow from the source tree to running the application.

## 1. Modules and Module Descriptors

A **module** is a unit of code organization in JPMS. A module has a name, contains one or more packages, and declares the modules it depends on. A module is typically described by a `module-info.java` file at the root directory of the source tree or module artifact.

Example module descriptor:

~~~java
module com.acme.model {
    exports com.acme.model;
}
~~~

Common directives:

- **requires module.name** declares that the current module depends on another module.
- **exports package.name** makes a package public so that other modules can access public types in that package.
- **opens package.name** allows deep reflective access to a package in scenarios controlled by JPMS; `opens` does not replace `exports` for normal source-code access.
- **requires transitive module.name** propagates the readability requirement of the depended-on module to modules that depend on the current module.
- **requires static module.name** declares a dependency required at compile time but potentially optional at runtime.
- **uses service.Interface** declares that the module uses a service via `ServiceLoader`.
- **provides service.Interface with implementation.Type** declares an implementation provided for a service.

Module names typically follow the reverse-domain naming convention such as `com.acme.model` or `org.example.app`. A module name is an identifier in the module graph; it does not necessarily have to match a package name, although using the same convention makes the project easier to read.

### Module graph

`requires` directives create dependency relationships between modules. When compiling or running, the compiler/launcher needs to resolve the module graph: which modules are required, which modules can read which modules, and which packages are accessible.

Example:

~~~text
com.acme.app
    |
    | requires
    v
com.acme.model
~~~

In this diagram, `com.acme.app` reads `com.acme.model` because the application's module descriptor declares `requires com.acme.model`. Packages that the application needs to use must be exported (`exports`) by the model module.

## 2. Source Tree Structure for Multiple Modules

When compiling multiple modules from a single source tree, `javac` typically uses a directory structure where each module has a subdirectory with the same name as the module. Each module directory contains `module-info.java` and the package sources.

Example of a two-module project:

~~~text
multi-module-demo/
└── src/
    ├── com.acme.model/
    │   ├── module-info.java
    │   └── com/
    │       └── acme/
    │           └── model/
    │               └── Message.java
    └── com.acme.app/
        ├── module-info.java
        └── com/
            └── acme/
                └── app/
                    └── Main.java
~~~

Three kinds of names should be distinguished:

- Module name: `com.acme.model` or `com.acme.app`.
- Package name: `com.acme.model` or `com.acme.app`.
- Fully qualified class name: `com.acme.model.Message` or `com.acme.app.Main`.

The module name and package name in this example have the same text, but they belong to two different concepts. The `module-info.java` file is always placed at the root of the module's source tree, not inside a package.

## 3. Preparing a Two-Module Example

The first module provides the `Message` type.

File `src/com.acme.model/module-info.java`:

~~~java
module com.acme.model {
    exports com.acme.model;
}
~~~

File `src/com.acme.model/com/acme/model/Message.java`:

~~~java
package com.acme.model;

public record Message(String text) {
}
~~~

The second module is the application that uses `Message`.

File `src/com.acme.app/module-info.java`:

~~~java
module com.acme.app {
    requires com.acme.model;
}
~~~

File `src/com.acme.app/com/acme/app/Main.java`:

~~~java
package com.acme.app;

import com.acme.model.Message;

public class Main {
    public static void main(String[] args) {
        Message message = new Message("Hello, modules!");
        System.out.println(message.text());
    }
}
~~~

Here:

- `com.acme.model` exports the package `com.acme.model`, so other modules can use the public type `Message`.
- `com.acme.app` requires `com.acme.model`, so the compiler can resolve the import and the launcher can resolve the module graph.
- `Message` is a `record`, a standard feature since Java 16, so the example is compatible with Java 17.
- The `text()` method is the accessor generated by the compiler for the record component named `text`.

## 4. Compiling Multiple Modules at Once

With the source tree structure above, both modules can be compiled with a single `javac` command:

~~~bash
javac --release 17 --module-source-path src -d out -m com.acme.model,com.acme.app
~~~

Meaning of the options:

- **--release 17** selects the Java SE API, language level, and target class file format for Java 17.
- **--module-source-path src** specifies the root containing the module source trees.
- **-d out** specifies the destination directory for compiled class files.
- **-m** is the short form of `--module`; the following list specifies the modules to compile.
- **com.acme.model,com.acme.app** instructs the compiler to compile the two listed modules.

`javac` reads the module descriptors, resolves `requires` relationships, and checks package access. If the `app` module needs `model`, the compiler must be able to find the `model` module in the specified module sources or on the module path.

After compilation, the output structure looks like:

~~~text
out/
├── com.acme.model/
│   ├── module-info.class
│   └── com/
│       └── acme/
│           └── model/
│               └── Message.class
└── com.acme.app/
    ├── module-info.class
    └── com/
        └── acme/
            └── app/
                └── Main.class
~~~

These are **exploded modules**: each module resides in a directory with `module-info.class` at its root. The `out` directory can be used directly as a module path.

### Running the compiled modules

Launch the main class of the application module:

~~~bash
java --module-path out -m com.acme.app/com.acme.app.Main
~~~

You can use the short option:

~~~bash
java -p out -m com.acme.app/com.acme.app.Main
~~~

Where:

- **--module-path out** or **-p out** specifies where the launcher searches for modules.
- **-m** or **--module** selects the module and main class in the form `module.name/class.name`.
- `com.acme.app` is the module to run.
- `com.acme.app.Main` is the class containing the `main` method.

Exact output:

~~~text
Hello, modules!
~~~

If the application module has `Main-Class` declared in the manifest of a modular JAR, you can use the module launch syntax suited to that JAR configuration. For exploded modules, the `module/class` syntax above explicitly specifies the entry point.

## 5. Compiling Modules One by One in Dependency Order

In some workflows, each module is compiled in a separate step. In that case, you need to compile dependencies first, and then pass the compiled module directory on the module path when compiling dependent modules.

Create output directories:

~~~bash
mkdir -p mods/com.acme.model mods/com.acme.app
~~~

Compile the `model` module:

~~~bash
javac --release 17 -d mods/com.acme.model \
  src/com.acme.model/module-info.java \
  src/com.acme.model/com/acme/model/Message.java
~~~

Compile the `app` module, using `mods` as the module path so the compiler can find `com.acme.model`:

~~~bash
javac --release 17 --module-path mods -d mods/com.acme.app \
  src/com.acme.app/module-info.java \
  src/com.acme.app/com/acme/app/Main.java
~~~

The output structure is now:

~~~text
mods/
├── com.acme.model/
│   ├── module-info.class
│   └── com/acme/model/Message.class
└── com.acme.app/
    ├── module-info.class
    └── com/acme/app/Main.class
~~~

Run using `mods` as the module path:

~~~bash
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Output:

~~~text
Hello, modules!
~~~

The module-by-module compilation approach is useful when modules have separate build lifecycles or dependencies are produced as artifacts in an earlier step. The key requirement is that the compiler's module path must contain the compiled dependency modules and the module name must match the `requires` directive.

## 6. Packaging Modules into JARs

A module can be packaged into a modular JAR. A modular JAR contains `module-info.class` at the root of the archive. When that JAR is placed on the module path, Java can recognize the module name and the directives in the descriptor.

After compiling the two modules into `mods`, create a directory to hold the JARs:

~~~bash
mkdir -p mlib
~~~

Package the `model` module:

~~~bash
jar --create --file mlib/com.acme.model.jar -C mods/com.acme.model .
~~~

Package the `app` module and specify the main class:

~~~bash
jar --create --file mlib/com.acme.app.jar \
  --main-class com.acme.app.Main \
  -C mods/com.acme.app .
~~~

Run the application from the module path containing both JARs:

~~~bash
java --module-path mlib -m com.acme.app
~~~

The launcher finds `com.acme.app`, reads `requires com.acme.model`, and resolves the `model` module from the same module path. Because the `app` JAR has a main class in its manifest, the main class can be selected via that configuration. To explicitly specify the main class without relying on the `Main-Class` attribute, use:

~~~bash
java --module-path mlib -m com.acme.app/com.acme.app.Main
~~~

The `jar` command does not compile source code; it packages compiled files. Make sure `module-info.class` is included in the JAR. If the descriptor is missing, the JAR may be treated as an automatic module when placed on the module path, with different naming and encapsulation rules.

## 7. Module Path and Classpath

The **module path** is where named modules or automatic modules are located. The **classpath** is where classes and resources are located according to the traditional classpath mechanism.

| Characteristic | Module path | Classpath |
|---|---|---|
| Unit of organization | Module | Classes and resources |
| Descriptor | Can have `module-info.class` | Does not use a module descriptor to define an unnamed module |
| Dependencies | Declared with `requires` | Typically resolved via the classpath and class-loading mechanism |
| Package access | Subject to `exports`/`opens` rules and module readability | No named module boundaries in that manner |
| Module name | Named or automatic module | Classes belong to the unnamed module corresponding to the class loader |

### Named modules, automatic modules, and unnamed modules

- **Named module** has an explicitly declared name and module descriptor.
- **Automatic module** is a module inferred when a JAR without a module descriptor is placed on the module path. Its name can come from the `Automatic-Module-Name` attribute in the manifest or be derived from the JAR filename according to platform rules.
- **Unnamed module** contains classes loaded from the classpath. It has no module name declared in `module-info.java`.

A named module cannot declare `requires` on an unnamed module. Therefore, if an application has migrated to JPMS while a library can only be placed on the traditional classpath, you need to consider how to package or adapt the library appropriately. Automatic modules are often a compatibility step during migration, but they do not replace designing an explicit module descriptor for a library in the long term.

### Placing external libraries on the module path

If a library is a modular JAR, add the directory containing the JAR to the module path:

~~~bash
javac --module-path "mods:lib" -d mods/com.acme.app \
  src/com.acme.app/module-info.java \
  src/com.acme.app/com/acme/app/Main.java
~~~

This example uses a colon as the path separator on Linux/macOS. On Windows, a multi-entry module path typically uses a semicolon. Quotes can be used so the shell preserves the path string according to the environment's syntax.

## 8. Important `javac` Options When Compiling Modules

| Option | Purpose |
|---|---|
| `--module-source-path` | Specifies the source tree containing the modules |
| `-m` or `--module` | Selects the modules to compile |
| `-d` | Specifies the output directory |
| `--module-path` or `-p` | Specifies where to find dependency modules |
| `--release` | Selects the target Java platform version |
| `--module-version` | Writes the module version into the output module descriptor |
| `--patch-module` | Supplements or overrides the contents of a module in appropriate testing/patching scenarios |
| `--add-reads` | Adds a module readability relationship in special scenarios |
| `--add-exports` | Opens a package for access by another module in special scenarios |

The `--patch-module`, `--add-reads`, and `--add-exports` options are typically intended for testing, tooling, or special compatibility scenarios. They should not be used as a default workaround for a poorly designed module descriptor. For normal applications, fix `requires` and `exports` properly in `module-info.java`.

You can enable module warnings during compilation:

~~~bash
javac -Xlint:module --release 17 --module-source-path src -d out \
  -m com.acme.model,com.acme.app
~~~

Warnings help detect certain issues with module declarations and dependencies. Not every warning is a compilation error; read the warning message and evaluate it in the context of the project.

## 9. Inspecting Modules and Module Resolution

When the compiler or launcher cannot find a module, check the module name, the location of `module-info.class`, and the module path.

Some useful commands:

~~~bash
jar --describe-module --file mlib/com.acme.model.jar
~~~

This command displays the module name and related declarations of a modular JAR.

~~~bash
java --show-module-resolution --module-path mlib -m com.acme.app
~~~

The `--show-module-resolution` option prints details about the launcher's module resolution process, which is useful when investigating which dependencies were found and which modules were included in the graph.

You can use `jdeps` to analyze JAR dependencies:

~~~bash
jdeps --module-path mlib --print-module-deps mlib/com.acme.app.jar
~~~

The output depends on the classes and libraries referenced by the JAR. `jdeps` assists with dependency analysis; it does not replace checking the module descriptor and testing the application.

## 10. Common Errors When Compiling Multiple Modules

### Module not found

Common causes:

- The dependency module has not been compiled or packaged yet.
- The module path points to the wrong directory.
- The name in `requires` differs from the actual module name.
- Passing the source root directory or a package directory to the module path instead of the root directory containing the modules.

How to fix: check `module-info.java`, the location of `module-info.class` or the modular JAR, and then point the module path to the right directory containing the modules.

### Package is not visible or package is not exported

The module was found, but the required package has not been exported (`exports`). Add the appropriate `exports` package directive to the module descriptor of the module providing the API. If only deep reflective access is needed, evaluate `opens` as required; `opens` does not replace `exports` for normal Java imports.

### Package does not belong to the declared module

The package directory structure and the package name in the Java file may not match. Check the `package` declaration, source file location, and module source tree.

### Split package

A package with the same name appearing in multiple named modules can cause errors or conflicts when the module graph is resolved. Avoid splitting the same package across multiple modules; move the classes into a single module that owns the package or redesign package boundaries.

### Cyclic dependence

If module A `requires` B and module B `requires` A, the module graph has an invalid cycle. Break the dependency cycle by extracting the shared API into a third module or inverting the dependency direction.

### Invalid module name or invalid module descriptor

A module name that violates identifier rules, a misplaced `module-info.java`, or duplicate declarations can cause the compiler to reject the descriptor. Place the module descriptor at the root of the source tree and use stable module names, rather than using a package name in place of the module directory structure.

### Main class not found or module fails to launch

Check whether the module path contains the application module, whether the main class is in the properly declared package, and whether the `-m` syntax specifies the correct `module/class`. For modular JARs, check the manifest and the module descriptor.

### Compiler and runtime version mismatch

A module compiled with newer APIs or a newer class file format may not run on an older runtime. Use `--release` to control the target version and verify `java --version` and `javac --version` in the build environment.

## 11. Build Tools and Multi-Module Projects

In large projects, invoking `javac` manually is useful for understanding the mechanics, but build tools usually orchestrate the dependency graph, build order, testing, and packaging.

- **Maven multi-module:** a parent project typically lists submodules. Each submodule can produce a separate JAR; `module-info.java` declares JPMS relationships if the project uses named modules.
- **Gradle multi-project:** subprojects are declared in settings; compile tasks can depend on artifacts from other projects. Toolchains select the JDK and target version.
- **IDE:** must recognize each source root/module, module descriptor, and dependency. The project SDK configuration must be compatible with the target release.

It is important to distinguish between **build-tool multi-module** and the **Java Platform Module System**. A Maven/Gradle module is a project/build boundary; a JPMS module is a module-graph unit at compile time and runtime. A multi-module Maven/Gradle project does not automatically have `module-info.java` or produce modular JARs.

When building multiple modules, keep the JDK version, compiler release, module path, and dependency versions consistent between developer machines and CI. Avoid having the build tool and IDE use different JDKs unintentionally.

## 12. Multi-Module Compilation Checklist

- Clearly define module boundaries and stable module names.
- Place `module-info.java` at the root of each module's source tree.
- Declare `requires` for dependencies and `exports` for API packages that need to be public.
- Keep each package owned by a single appropriate named module; avoid split packages.
- Organize the source tree by module name to use `--module-source-path`.
- When compiling together, list the modules to build with `-m`.
- When compiling module by module, build dependencies first and put their artifacts on `--module-path`.
- Use `--release` to standardize the API and class file target.
- Verify that the output has `module-info.class` and package class files in the right locations.
- Package modular JARs with `jar` and keep the module descriptor at the root of the archive.
- Run with `java --module-path` and `-m`.
- Use `jar --describe-module`, `--show-module-resolution`, and `jdeps` when diagnostics are needed.
- Test the application on the exact target JDK runtime.

## 13. Key Terminology

| Term | Meaning |
|---|---|
| JPMS | Java Platform Module System, Java's module system |
| Module descriptor | The `module-info.java` file describing a module's name and relationships |
| requires | Declares a module dependency |
| exports | Makes a package public to other modules |
| opens | Allows deep reflective access to a package |
| Module graph | The resolved graph of modules and dependency relationships |
| Module source path | The location of module source trees |
| Module path | The location containing exploded modules or modular JARs |
| Exploded module | A compiled module residing in a directory |
| Modular JAR | A JAR containing a module descriptor at the root of the archive |
| Automatic module | A module inferred from a JAR without a descriptor when placed on the module path |
| Unnamed module | The module containing classes loaded from the classpath |
| Split package | A package split across multiple modules |
| Module resolution | The process of determining required modules and readability relationships |

Compiling multiple modules comes down to getting three things right: **organizing the source tree by module, declaring dependencies and package visibility in module descriptors, and providing the right module source path or module path to `javac`**. When these steps are consistent, the Java launcher can resolve the module graph and launch the application from exploded modules or modular JARs.
