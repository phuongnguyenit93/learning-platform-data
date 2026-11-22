# Missing Module and Missing Package

When working with the Java Platform Module System (JPMS), two common errors have similar names yet originate from two different stages: **missing module** means a required module cannot be found or cannot be added to the module graph; **missing package** means source code cannot find the needed package, or the package exists but the current module is not permitted to access it.

Distinguishing the two error types properly helps you pick the exact fix. Adding a JAR to the right module path can resolve a missing module error; declaring `requires` or `exports` can resolve readability and package visibility errors. These actions are not interchangeable.

## 1. Module and Package Are Not the Same Concept

A **module** is a unit of packaging with a name, dependencies, and access boundaries. A named module typically declares this information in `module-info.java`.

    module com.example.billing {
        requires com.example.money;
        exports com.example.billing.api;
    }

A module can contain multiple packages, for example:

    com.example.billing.api
    com.example.billing.internal
    com.example.billing.persistence

A package is a unit for organizing Java types. A module is a larger unit that owns packages and decides which packages can be accessed by other modules.

Therefore:

- A module name like `com.example.money` does not necessarily match a package name.
- A single module can contain multiple packages.
- A package does not automatically become a module just because its package name has multiple dots.
- `exports` exposes a package; it does not cause a module to be found or resolved.

## 2. Missing Module: Required Module Not Found

Suppose the application module declares:

    module com.example.app {
        requires com.example.money;
    }

At compile time or runtime, JPMS needs to locate a module named `com.example.money`. If that module is not present in the module sources the tool is searching, module lookup or resolution can fail with an error like:

    java.lang.module.FindException:
        Module com.example.money not found, required by com.example.app

Common causes:

- The module's JAR has not been added to the module path.
- The module path points to the wrong directory or wrong file.
- The module name in `requires` does not match the name in `module-info.class`.
- The JAR is a legacy library on the classpath, yet the application declares `requires` on it.
- A provider module or transitive dependency is missing at runtime.
- Build and runtime use different module paths.

Key point to remember: `requires` references a **module name**, not a JAR filename or Maven/Gradle coordinate. A file `money-library-1.0.jar` can declare the module name `com.example.money`; the JAR name and module name do not have to be identical.

## 3. Checking Whether a Module Is Found

You can use `jar --describe-module` to inspect a JAR's module descriptor:

    jar --describe-module --file libs/money-library.jar

If the JAR is an explicit module, the output shows the declared module name. For an automatic module, the name may be derived from the JAR filename or the `Automatic-Module-Name` attribute in the manifest.

You can list the modules in the current JDK:

    java --list-modules

You can ask the launcher to validate the module path:

    java --module-path mods --validate-modules

In a Java program, `ModuleFinder` can check for a module name in a path:

    ModuleFinder finder = ModuleFinder.of(Path.of("mods"));

    Optional<ModuleReference> reference =
            finder.find("com.example.money");

    if (reference.isEmpty()) {
        throw new IllegalStateException("Module not found");
    }

If the finder does not locate the module, check the JAR/exploded module location, the actual module name, and the module path configuration before modifying packages or source code.

## 4. Module Path and Classpath Are Different Sources

For an application using named modules, dependencies must be placed on the module path so JPMS can locate the corresponding modules.

Compile example:

    javac --module-path libs
          --module-source-path src
          -d out
          -m com.example.app

Run:

    java --module-path "out;libs"
         -m com.example.app/com.example.app.Main

On Windows, the separator between module path entries is a semicolon; on Linux and macOS, a colon is used.

If libraries are only placed on the classpath:

    java -cp "app.jar;libs/*" com.example.app.Main

then JARs on the classpath belong to the unnamed module of the corresponding class loader. A named module cannot declare `requires` on an unnamed module because unnamed modules have no name.

A legacy JAR without `module-info.class` can be placed on the module path to become an automatic module. It then has a module name and can be required by a named module using `requires`. Determine the exact automatic module name rather than guessing from the artifact name.

## 5. Missing Package: Package Absent or Inaccessible

A package error can occur even when the module containing the library has already been found.

Source code example:

    import com.example.money.Currency;

If the compiler reports:

    package com.example.money does not exist

then the package the source is importing cannot be found among the modules or libraries visible to the compilation. The package name may be misspelled, the module containing the package may not be in the compile configuration, or the actual package may have a different name.

Another case is when the package exists but is not exported. For example, the library module has:

    module com.example.money {
        // Does not export com.example.money.internal
    }

While the application writes:

    import com.example.money.internal.CurrencyParser;

The compiler may report that the package is not visible, along with information about which module owns the package and that the module does not export the package to the application.

This is not a missing JAR error: the module may have been found, yet the package is not exposed according to the module descriptor.

## 6. Readability and Exports Must Both Match

For module A to access public types in a package of module B, two conditions are normally required:

1. Module A has readability to module B, directly via `requires` or propagated via `requires transitive`.
2. Module B exports the package containing that type to module A, via ordinary `exports` or matching qualified exports.

Library module example:

    module com.example.money {
        exports com.example.money.api;
    }

Application module:

    module com.example.app {
        requires com.example.money;
    }

The application can import:

    import com.example.money.api.Currency;

But it cannot import types in an unexported package:

    import com.example.money.internal.CurrencyParser;

Adding `requires com.example.money;` does not automatically export all packages. Conversely, adding `exports com.example.money.api;` does not allow the application to access the package if the application module does not read the module containing that package.

## 7. Distinguishing Common Error Messages

| Message or Situation | Meaning | What to Check |
|---|---|---|
| `FindException: Module X not found` | Module X was not found in the module sources | Module path, module name, artifacts, and transitive dependencies |
| `module not found: X` at compile time | The compiler cannot find the required module X | `--module-path`, module name, and JAR location |
| `package p does not exist` | The package is absent from the sources the compiler considers, or the package name is wrong | Package declaration, module/JAR containing the package, compilation configuration |
| `package p is not visible` | The package may belong to a known module, but is inaccessible per the module graph or exports | `requires`, `requires transitive`, `exports` |
| `module A does not read module B` | A lacks readability to B | Dependencies in `module-info.java` or readability configuration |
| `does not export package p to module A` | B does not expose package p to A | `exports p` or `exports p to A` |
| `ClassNotFoundException` | The program requested a class by name, but the class loader could not find it | Runtime module path/classpath, class name, and loader |
| `NoClassDefFoundError` | The JVM cannot find or define a required class at runtime | Runtime dependencies, module resolution, and prior class initialization failures |

Exact messages may vary across `javac`, the Java launcher, IDEs, and build tools. Read the entire message, especially the part naming the module that owns the package or the module requiring the dependency.

## 8. An Ordered Diagnostic Workflow

When encountering a module or package error, check in the following order:

**Step 1 — Identify the error stage.**

- Does the error occur when compiling `module-info.java` or source code?
- Does the error occur when the launcher resolves modules?
- Does the error occur when a class loader loads a class?
- Does the error occur when reflection accesses a member?

Do not treat a compile error with runtime options or treat a reflection error by adding a JAR.

**Step 2 — Determine the actual module name.**

Run:

    jar --describe-module --file libs/dependency.jar

Compare the displayed name with the name in `requires`. Do not assume the Maven artifact, JAR filename, and module name are identical.

**Step 3 — Determine the actual package.**

List the contents of the JAR:

    jar --list --file libs/dependency.jar

Check the class path inside the JAR, package declaration, and fully qualified name of the type to import. For example, the path `com/example/money/api/Currency.class` corresponds to the package `com.example.money.api`.

**Step 4 — Inspect the module descriptor.**

Verify whether the application module has `requires` on the library module, and whether the library module has `exports` on the needed package. If the package is only needed for reflection, check `opens` instead of reflexively adding `exports`.

**Step 5 — Compare compile and runtime configurations.**

Ensure the dependency appears on both the compiler's module path and the launcher's module path. A dependency may exist in a Gradle compile configuration yet be missing from the runtime configuration.

**Step 6 — Resolve and run again.**

Use the same set of artifacts and module path across verification steps. If the error persists, read the specific module or package name in the new message to trace further.

## 9. Additional Options Do Not Replace Missing Dependencies

Certain JVM options can adjust the module graph or access permissions:

- `--add-modules`: adds modules to the root set to resolve.
- `--add-reads`: adds readability relationships between modules.
- `--add-exports`: exports a package to a target module at runtime.
- `--add-opens`: opens a package for deep reflection at runtime.
- `--patch-module`: adds or overrides classes/resources in a specified module.

These options are useful for testing, migration, or special runtime configurations. They do not load a module or class that does not exist at all. If module X is not on the module path, `--add-reads A=X` cannot make X appear. If a package does not exist in any module, `--add-exports` does not create that package either.

For missing artifact errors, fix dependency resolution and the module path first. Use extension options only once you have pinpointed the issue as readability, exports, or reflection.

## 10. Distinguishing exports and opens When Errors Involve Packages

Two commonly confused directives:

    module com.example.money {
        exports com.example.money.api;
        opens com.example.money.internal;
    }

- `exports` allows other modules to access public types in the package under ordinary Java rules.
- `opens` allows deep reflection into the package at runtime.
- `open module` opens all packages of the module for deep reflection.

If the compiler reports that it cannot import a public type in a package, examine `requires` and `exports`. If a framework reports `InaccessibleObjectException` when accessing private fields, examine `opens`. Adding `opens` does not make a package importable from source code.

## 11. Combined Example: From Missing Module to Missing Package

Suppose the application needs the `Currency` type from the `com.example.money` library.

Library module:

    module com.example.money {
        exports com.example.money.api;
    }

Application:

    module com.example.app {
        requires com.example.money;
    }

Source:

    import com.example.money.api.Currency;

If the library JAR is not yet on the module path, the error is a missing module. Place the JAR on the module path and verify the module name with `jar --describe-module`.

If the JAR is present and the module is found, yet the source changes to:

    import com.example.money.internal.CurrencyParser;

then the error is package visibility because the internal package is not exported. Change the import to use the public API, or update the library's module descriptor if that package is genuinely meant to be part of the API.

These are two separate diagnostic steps: locate the module first, then verify whether the package is accessible.

## Key Takeaways

- **Missing module:** a required module cannot be found or cannot be resolved. Check the module name, module path, and dependencies.
- **Missing package:** the package does not exist in the sources under consideration, or the package is not visible due to readability/exports. Check package declarations, `requires`, and `exports`.
- **Readability** and **exports** are two distinct conditions for accessing public types from another module.
- **Opens** serves deep reflection; it does not replace exports.
- Classpath, module path, compile configuration, and runtime configuration may differ; inspect the exact stage where the error occurs.

When troubleshooting JPMS errors, first determine whether the module is found, and only then check the package, readability, and export permissions.
