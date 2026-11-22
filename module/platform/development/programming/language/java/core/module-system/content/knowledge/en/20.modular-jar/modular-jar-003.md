# Compiling module-info Together with Sources

## 1. Why Does module-info.java Need to Be Compiled with Module Sources?

In the Java Platform Module System (JPMS), the `module-info.java` file describes the module: its module name, dependencies, exported packages, services used or provided, and related access rules.

This file is a special source file of the module. During compilation, `javac` produces `module-info.class` alongside the classes belonging to that module. Therefore, when building a module from source, you need to include the module descriptor and the module's source files in the same compilation pass or the same consistent build process.

The most common approach is to use `--module-source-path` to point to the directory containing the module sources, and then select the modules to compile with `-m` or `--module`.

You do not need to compile `module-info.java` into a standalone artifact first and then compile the classes afterward. The compiler needs the descriptor to enforce module readability, package exports, and dependencies while compiling the sources.

## 2. Standard Source Structure

Suppose we have a module `com.acme.hello`:

```text
project/
└── src/
    └── com.acme.hello/
        ├── module-info.java
        └── com/
            └── acme/
                └── hello/
                    └── Main.java
```

`src/com.acme.hello/module-info.java` file:

```java
module com.acme.hello {
}
```

`src/com.acme.hello/com/acme/hello/Main.java` file:

```java
package com.acme.hello;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from a named module");
    }
}
```

Key points to keep right:

- A direct subdirectory under `src` represents a module source root, here `com.acme.hello`.
- `module-info.java` resides directly at the module source root, not inside a package directory.
- Class sources reside under paths matching their packages.
- The name in `module-info.java` is the module name, not a package name.
- `module-info.java` has no `package` declaration.

## 3. Compiling module-info.java Together with All Sources

From the `project` directory, run:

```bash
javac --module-source-path src -d out -m com.acme.hello
```

Or use the full option name:

```bash
javac --module-source-path src -d out --module com.acme.hello
```

Meaning:

- `--module-source-path src`: specifies where module sources reside. With the default layout, the compiler looks for module directories under `src`.
- `-d out`: writes compiled classes to the output directory.
- `-m com.acme.hello`: requests compiling the module with this name. The compiler reads `module-info.java` and the module's source files.

The output has the structure:

```text
out/
└── com.acme.hello/
    ├── module-info.class
    └── com/
        └── acme/
            └── hello/
                └── Main.class
```

You can inspect the compiled descriptor:

```bash
javap -p out/com.acme.hello/module-info.class
```

Or run it:

```bash
java --module-path out -m com.acme.hello/com.acme.hello.Main
```

Output:

```text
Hello from a named module
```

The key point to remember is that a single `javac` invocation compiled both the descriptor and the source classes into the same module's output.

## 4. Compiling Multiple Modules Together

When module sources depend on each other, you can place them under the same module source path:

```text
src/
├── com.acme.api/
│   ├── module-info.java
│   └── com/acme/api/Customer.java
└── com.acme.app/
    ├── module-info.java
    └── com/acme/app/Main.java
```

API module:

```java
module com.acme.api {
    exports com.acme.api;
}
```

API class:

```java
package com.acme.api;

public record Customer(String name) {
}
```

Application module:

```java
module com.acme.app {
    requires com.acme.api;
}
```

Main class:

```java
package com.acme.app;

import com.acme.api.Customer;

public class Main {
    public static void main(String[] args) {
        Customer customer = new Customer("Ada");
        System.out.println(customer.name());
    }
}
```

Compile both modules:

```bash
javac --module-source-path src -d out -m com.acme.api,com.acme.app
```

The compiler compiles the descriptor and sources of both the API and the application. Because both modules are selected in the same invocation, source dependencies between them are resolved during compilation.

Output:

```text
out/
├── com.acme.api/
│   ├── module-info.class
│   └── com/acme/api/Customer.class
└── com.acme.app/
    ├── module-info.class
    └── com/acme/app/Main.class
```

Run:

```bash
java --module-path out -m com.acme.app/com.acme.app.Main
```

Output:

```text
Ada
```

If a source module has a dependency on another module that is also in the source tree, include that module in the list of modules to compile or provide its compiled version on the module path.

## 5. Compiling an Application with a Compiled Dependency

In larger projects, API libraries are often built beforehand and packaged as modular JARs. In that case, use `--module-path` for compiled dependencies and `--module-source-path` for the current module sources.

For example:

```text
project/
├── mods/
│   └── com.acme.api.jar
└── src/
    └── com.acme.app/
        ├── module-info.java
        └── com/acme/app/Main.java
```

Compile:

```bash
javac --module-path mods --module-source-path src -d out -m com.acme.app
```

The two options serve different roles:

| Option | Purpose |
|---|---|
| `--module-source-path` | Locates source code of the modules being compiled |
| `--module-path` | Locates compiled modules, typically modular JARs or module directories |
| `-d` | Directory to write class output |
| `-m` / `--module` | Module(s) to compile |

If the API JAR is not in `mods`, the compiler can report `module not found` even though the application's source already has `requires com.acme.api`.

## 6. Compiling Source Files Directly and the Role of module-source-path

You can pass a list of source files directly to `javac` in simple builds, but when a project has multiple modules, `--module-source-path` helps the compiler identify module boundaries and locate sources by module name.

Standard example:

```bash
javac -d out --module-source-path src -m com.acme.api,com.acme.app
```

Do not place all sources of multiple named modules into a single package tree directory and compile them like a classpath application. Each named module needs its own source root and descriptor.

If the source layout differs from the default, you can use a module-source-path pattern to indicate the location of module sources. Example structure:

```text
src/
└── modules/
    ├── com.acme.api/
    └── com.acme.app/
```

You can specify:

```bash
javac --module-source-path "src/modules/*" -d out -m com.acme.api,com.acme.app
```

The `*` pattern represents the module name segment in the path. Ensure the pattern matches the exact location of the module directories; otherwise, the compiler will not find the sources or the module descriptor.

## 7. Adding Compiler Options During the Build

You can combine common options:

```bash
javac --release 21 -encoding UTF-8 -Xlint:all --module-source-path src -d out -m com.acme.api,com.acme.app
```

- `--release 21` compiles against Java 21 APIs and language features, if the JDK in use supports that release.
- `-encoding UTF-8` specifies the source encoding.
- `-Xlint:all` enables common compiler warnings.
- `--module-source-path` and `-m` select the source modules to compile.

Choose `--release` based on the project's actual JDK baseline. Do not use a release newer than the production runtime version if the application needs to run on an older runtime.

You can use `-g` to generate debug information or `-parameters` if a framework needs to preserve method parameter names. These options do not change the module graph structure.

## 8. Packaging Output into Modular JARs

After compiling, each module directory in `out` can be packaged separately:

```bash
jar --create --file mods/com.acme.api.jar -C out/com.acme.api .
jar --create --file mods/com.acme.app.jar -C out/com.acme.app .
```

Make sure `module-info.class` is at the root of each JAR. Verify:

```bash
jar --describe-module --file mods/com.acme.api.jar
jar --describe-module --file mods/com.acme.app.jar
```

If packaged by mistake from a parent directory or if `module-info.class` is omitted, the JAR may no longer be an explicit named module as expected.

After packaging, run the created JARs directly:

```bash
java --module-path mods -m com.acme.app/com.acme.app.Main
```

Testing from the JAR helps catch packaging errors that running directly from the `out` directory might hide.

## 9. Integrating into Build Tools

### Maven

With Maven, module sources typically reside in `src/main/java`, and `module-info.java` sits directly at the source directory root:

```text
src/main/java/
├── module-info.java
└── com/acme/app/Main.java
```

The Maven Compiler Plugin compiles sources and the module descriptor according to the JDK/compiler plugin configuration. Minimal configuration example:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

Ensure the Maven Compiler Plugin version and JDK support the target release. In a multi-module Maven project, each Maven module typically has its own artifact and descriptor; dependencies declared in the POM must be compatible with the module names in `module-info.java`.

### Gradle

With the Gradle Java plugin, `module-info.java` is placed in the source set alongside Java sources:

```text
src/main/java/
├── module-info.java
└── com/acme/app/Main.java
```

Configure the toolchain/release according to the target JDK and ensure the Gradle version supports modular compilation appropriately. When module path inference is needed, check the compile/test task configuration and ensure dependencies are placed on the module path rather than the classpath.

Build tools may organize compiler invocations themselves, but the principle remains the same: the descriptor must be processed by the compiler together with the module sources, and dependencies must be provided on the proper path type.

## 10. Common Errors

| Error | Cause | How to Fix |
|---|---|---|
| `module not found: X` | Dependency is missing from the module path or source path cannot find the module | Check module name, `--module-path`, and `--module-source-path` |
| `module X does not read module Y` | Missing `requires Y` | Add the dependency in the consumer module's descriptor |
| Package is not visible | Owning module has not exported the package or consumer does not read the module | Check both `requires` and `exports` |
| `module-info.java` not found | Wrong module source root location or pattern | Place the descriptor at the module root and fix `--module-source-path` |
| Package declaration does not match directory | Source file is in the wrong package path | Align the package declaration with the source directory |
| Main class not found when running | Wrong module name, class name, or output layout | Check output and use the correct `-m module/class` |
| JAR is not recognized as an explicit module | Missing `module-info.class` in the artifact | Check packaging and `jar --describe-module` |
| Build tool succeeds but manual `javac` fails | Build tool added compiler/module path options | Print or inspect compiler arguments and reproduce the exact configuration |

When encountering an error, read the module/package names in the message before editing the descriptor. Do not broadly add `exports` or `requires transitive` just to make compilation pass.

## 11. Reproducible Build Workflow

A clear modular build workflow can include:

1. Check the source layout: each module has its own root and `module-info.java` in the right place.
2. Verify module names and dependencies in the descriptors.
3. Build source modules in the same invocation if they depend on each other, or build dependencies first and place them on the module path.
4. Use a fixed compiler release and encoding.
5. Package each module, making sure to preserve `module-info.class`.
6. Inspect artifacts with `jar --describe-module`.
7. Run from the module path using the exact JARs to be released.
8. Record the compiler/JDK version and build configuration for reproducibility.

## Key Takeaways

- `module-info.java` is a special source file of the module and is compiled into `module-info.class`.
- Place the descriptor at the root of the module source, alongside the package tree.
- Use `--module-source-path` so the compiler locates module sources and `-m` to select modules to compile.
- Compile multiple source modules by listing module names in `-m`.
- Use `--module-path` for compiled dependencies; do not confuse it with the module source path.
- Package the output so that `module-info.class` sits at the root of the modular JAR.
- Always test the packaged artifact with `java --module-path`, not only by running from the compiled classes output directory.