# Compiling Multiple Modules with javac --module-source-path

## 1. Objectives

When a Java project is divided into multiple named modules, compilation is no longer as simple as passing all `.java` files into a single `javac` command like in a traditional classpath project. The compiler needs to know which module each source file belongs to, where the module descriptors are located, and how dependencies between modules are resolved.

The `--module-source-path` option tells `javac` where the source trees of multiple modules are located. Combined with `--module` or `-m`, the compiler can compile the specified modules from a shared directory structure.

This lesson focuses on how to organize the source tree, compilation command syntax, output directories, and how to combine source modules with precompiled dependencies.

After this lesson, you will be able to:

- Organize multi-module source code by module name.
- Use `--module-source-path` so the compiler can locate `module-info.java` and the source files of each module.
- Use `-m` to select modules to compile.
- Use `-d` to specify the output directory and `--module-path` for precompiled dependencies.
- Recognize common errors when compiling a modular project.

## 2. Example Source Tree Structure

Suppose an application has two modules:

- `com.example.api`: provides the API.
- `com.example.app`: uses the API.

A simple directory structure:

```text
project/
├── src/
│   ├── com.example.api/
│   │   ├── module-info.java
│   │   └── com/
│   │       └── example/
│   │           └── api/
│   │               └── Greeting.java
│   └── com.example.app/
│       ├── module-info.java
│       └── com/
│           └── example/
│               └── app/
│                   └── Main.java
└── out/
```

Points to remember:

- `src` is the module source path root.
- Each immediate subdirectory represents one module, and the directory name matches the module name in `module-info.java`.
- Inside the module directory, the package structure still follows the standard package path.
- Each named module has a `module-info.java` at the root of the module's source tree.

Example API module:

```java
// src/com.example.api/module-info.java
module com.example.api {
    exports com.example.api;
}
```

```java
// src/com.example.api/com/example/api/Greeting.java
package com.example.api;

public final class Greeting {
    public static String message() {
        return "Hello from API";
    }
}
```

Application module:

```java
// src/com.example.app/module-info.java
module com.example.app {
    requires com.example.api;
}
```

```java
// src/com.example.app/com/example/app/Main.java
package com.example.app;

import com.example.api.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
```

The module directory name and the name declared in `module-info.java` must be consistent so the compiler can find the module's source files properly.

## 3. Basic Syntax of --module-source-path

General syntax:

```bash
javac --module-source-path <module-source-path> -d <output-directory> --module <module-name>[,<module-name>...]
```

Components:

| Component | Meaning |
| --- | --- |
| `javac` | Java compiler. |
| `--module-source-path` | Specifies the location or path pattern containing the source files of the modules. |
| `-d` | Specifies the directory where compiled files are written. |
| `--module` or `-m` | Specifies one or more modules to compile. |

With the structure in the previous section, running from the `project` directory:

```bash
javac --module-source-path src -d out --module com.example.api,com.example.app
```

Short form:

```bash
javac --module-source-path src -d out -m com.example.api,com.example.app
```

The two commands are equivalent because `-m` is the short form of the `--module` option in `javac`.

The command above tells the compiler that the modules' source trees are located under `src`, the output is placed in `out`, and the two modules requested for compilation are `com.example.api` and `com.example.app`.

When compiling a set of modules with dependency relationships, ensure that the source files of all related modules can be found and that the selected modules are included in the compilation command according to the project's scope.

## 4. Result After Compilation

With the `-d out` option, the compiler generates output per module. The resulting structure looks like:

```text
out/
├── com.example.api/
│   ├── module-info.class
│   └── com/
│       └── example/
│           └── api/
│               └── Greeting.class
└── com.example.app/
    ├── module-info.class
    └── com/
        └── example/
            └── app/
                └── Main.class
```

Each module has its own output directory. The `module-info.class` file contains the compiled module descriptor; the remaining classes are organized by package.

You can run the application with the module path pointing to the output directory:

```bash
java --module-path out --module com.example.app/com.example.app.Main
```

Short form:

```bash
java -p out -m com.example.app/com.example.app.Main
```

In the run command, the part before `/` is the module name; the part after is the fully qualified name of the main class. This is the syntax of the `java` command, not `javac`'s syntax for selecting modules to compile.

## 5. Specifying Module Source Path with Patterns

When the source tree is not placed directly under a simple module source root directory, `--module-source-path` supports patterns with `*` to represent the module name.

Example structure:

```text
project/
└── src/
    ├── com.example.api/
    │   └── main/
    │       └── java/
    │           ├── module-info.java
    │           └── com/example/api/Greeting.java
    └── com.example.app/
        └── main/
            └── java/
                ├── module-info.java
                └── com/example/app/Main.java
```

The pattern `src/*/main/java` represents the source root of each module:

```bash
javac --module-source-path "src/*/main/java" -d out -m com.example.api,com.example.app
```

The `*` is used by `javac` as the module name placeholder in the module source path pattern. Enclosing the pattern in quotes helps the shell pass the pattern intact to the compiler instead of interpreting the wildcard character itself.

If the project has multiple source roots, the module source path can also contain a list of paths following the operating system's path separator rules. On Windows, path lists typically use a semicolon; on Linux/macOS, they typically use a colon. When writing commands to run across multiple operating systems, pay attention to this difference.

## 6. Which Modules to Compile?

Use `--module` or `-m` to explicitly state the modules to compile:

```bash
javac --module-source-path src -d out -m com.example.api
```

This command requests compiling the `com.example.api` module.

You can specify multiple modules separated by commas:

```bash
javac --module-source-path src -d out -m com.example.api,com.example.app
```

When selecting an application module, the compiler needs to resolve the modules required by the application. If dependencies are also compiled from source within the same module source path, ensure the compiler can find the dependency sources and select the set of modules matching the build goal.

If dependencies have already been compiled into module outputs or JARs, you can place them on `--module-path` instead of recompiling them from source in the same pass.

## 7. Combining with --module-path

The two options have different roles:

- `--module-source-path`: where to find the source code of the modules being compiled.
- `--module-path`: where to find precompiled modules, such as module output directories or JARs.

Suppose `com.example.api` has already been compiled as a module in `libs/api-module`, while the app's source is in `src/com.example.app`:

```text
project/
├── libs/
│   └── api-module/
│       └── com.example.api/
│           ├── module-info.class
│           └── com/example/api/Greeting.class
├── src/
│   └── com.example.app/
│       ├── module-info.java
│       └── com/example/app/Main.java
└── out/
```

You can compile the app with the module path pointing to the existing dependency:

```bash
javac --module-path libs/api-module --module-source-path src -d out -m com.example.app
```

The compiler reads the app's source from the module source path and reads the compiled API module from the module path. The app's module descriptor still needs:

```java
module com.example.app {
    requires com.example.api;
}
```

Do not use `--module-source-path` in place of `--module-path`: one is for source modules, and the other is for compiled modules.

## 8. When to Use the Regular Source Path?

`-source-path` and `--module-source-path` serve two different ways of organizing source code:

| Option | Purpose |
| --- | --- |
| `-source-path` | Find source files by package in the traditional compilation model. |
| `--module-source-path` | Find source trees of multiple named modules, with module boundaries defined. |

For a modular project, where each module has its own `module-info.java` and source tree, `--module-source-path` helps the compiler understand module boundaries. You should not lump sources from multiple modules into a single package root and expect the compiler to infer module ownership on its own.

## 9. Common Errors and How to Handle Them

**Specified module not found**

For example, errors related to a module not existing or not being found in the module source path.

Check:

- Does the module name in `-m` match the name in `module-info.java`?
- Is the module directory located properly under the module source path?
- Does the pattern point to the exact directory containing `module-info.java`?
- Is there a typo or case mismatch between the directory name and the module name?

**Package not exported or module cannot read dependency**

Check the dependency's descriptor:

- Does the consuming module `requires` the module providing the package?
- Has the module providing the package `exports` the needed package yet?
- Is the dependency on `--module-path` or in a source tree discoverable by the compiler?

**Class or package not found**

Compare the package declaration with the source directory structure. For example, `package com.example.app;` corresponds to the directory `com/example/app` inside the module's source root.

**Output does not have expected module directories**

Check whether `-d` points to the right output directory and whether the modules are compiled as named modules. With modular compilation, each module has its own output area under the target directory.

**Confusing --module-path and --module-source-path**

Determine what form the dependency is in: source files belong in the module source path; compiled modules or modular JARs belong in the module path.

## 10. Practical Compilation Workflow

For a small multi-module project, you can follow this sequence:

1. Create a source root, for example `src/`.
2. Create a separate directory for each module, with the directory name matching the module name.
3. Place `module-info.java` at the root of each module's source tree.
4. Write package source files inside the module directory.
5. Declare `requires` and `exports` according to actual module relationships.
6. Choose the output directory with `-d`.
7. Use `--module-source-path` to point to the source tree location and `-m` to select the modules to compile.
8. If there are precompiled dependencies, add their locations with `--module-path`.
9. Run the application with `java --module-path` and `--module`.

Sample commands for the structure in Section 2:

```bash
javac --module-source-path src -d out -m com.example.api,com.example.app
java --module-path out -m com.example.app/com.example.app.Main
```

## 11. Key Takeaways

- `--module-source-path` specifies where the source trees of named modules are located.
- The module directory name must match the name in `module-info.java`.
- `-m` is the short form of `--module` in `javac`, used to specify the modules to compile.
- `-d` determines where output is written; output for modules is separated by module name.
- `--module-path` finds compiled modules, whereas `--module-source-path` finds module sources.
- When running the program, use module path pointing to the output and specify the module along with the main class.

Start with the directory structure and module descriptors. When these two parts are right, `javac --module-source-path` helps compile multiple modules from an organized source tree while preserving the boundaries of the Java Module System.
