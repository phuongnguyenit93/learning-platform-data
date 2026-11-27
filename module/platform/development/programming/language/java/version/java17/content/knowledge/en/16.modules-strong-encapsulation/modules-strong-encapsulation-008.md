# Scoping `--add-exports` and `--add-opens` for Mandatory Integrations

The Java Platform Module System (JPMS) divides an application into named modules, each declaring dependencies and the packages it permits other modules to consume. This mechanism constrains access across module boundaries. Starting in Java 17, strong encapsulation of JDK internal APIs is strictly enforced; a legacy library relying on unexported packages or using reflection to touch non-public members may fail at runtime.

In cases of mandatory integrations that cannot be replaced immediately, Java provides two options to open only the necessary boundary:

- **`--add-exports`**: exports a package from a source module to a target module, allowing target code to access public types and members in that package under Java access rules.
- **`--add-opens`**: opens a package from a source module to a target module so reflection can perform deep access into non-public members at runtime.

These two options solve two different kinds of access. Using the wrong option usually fails to fix the error; widening scope excessively undermines the encapsulation benefits of modules. This lesson focuses on syntax, minimal scoping, compile/runtime configuration, and bounding exceptions when an integration genuinely requires them.

## 1. Why Do Modules Need exports and opens?

A module can contain many packages, yet not every package is a public API. For example:

```text
com.example.payment
├── com.example.payment.api
├── com.example.payment.spi
└── com.example.payment.internal
```

A module might export only `api` and `spi`; package `internal` stays internal:

```java
module com.example.payment {
    exports com.example.payment.api;
    exports com.example.payment.spi;
}
```

Another module can use public types belonging to exported packages. However, it cannot arbitrarily import types in `com.example.payment.internal`.

Module encapsulation has two layers to distinguish:

1. **Readability:** whether the current module reads the other module. Typically declared via `requires` in `module-info.java`.
2. **Accessibility/export:** whether the other module's package is exported to the current module.

`--add-exports` and `--add-opens` handle package accessibility in different ways. They **do not replace `requires` and do not automatically add readability** for ordinary Java code.

### 1.1. Example of a module exporting only its API

```java
module com.example.payment {
    exports com.example.payment.api;
}
```

External code can use public types in `com.example.payment.api` if the external module also reads this module. Other packages remain closed to normal access from outside modules.

### 1.2. Strong encapsulation in the JDK

Since Java 9, platform modules have organized APIs by module and package. Public packages are documented in API specifications; JDK internal packages are not compatibility commitments for applications.

Java 17 continues strongly encapsulating JDK internal components under JEP 403. Thus, a library that previously accessed `sun.*`, `com.sun.*`, or `jdk.internal.*` may stop working if it depended on unsupported access.

Do not treat `--add-exports` as a way to make an internal API a long-term supported API. The option only relaxes a module boundary for a specified package and target; it creates no commitment that the package will exist or stay unchanged in future JDK releases.

## 2. --add-exports: Allowing Access to Public Types and Members

`--add-exports` exports a package from a source module to one or more target modules.

Syntax:

```text
--add-exports <source-module>/<package>=<target-module>(,<target-module>)*
```

You can join `=` directly to the option:

```text
--add-exports=java.base/jdk.internal.misc=com.example.app
```

Meaning of each component:

| Component | Meaning |
| --- | --- |
| `source-module` | Module containing the package to export. |
| `package` | Package name to open for public type access. |
| `target-module` | Module receiving access to that package. |
| `ALL-UNNAMED` | All unnamed modules, typically code loaded from the classpath. |

Hypothetical example:

```text
--add-exports=com.vendor.legacy/com.vendor.internal=com.example.app
```

This option lets module `com.example.app` access public types in package `com.vendor.internal` of module `com.vendor.legacy`, provided the application module also reads the source module.

### 2.1. --add-exports does not open private members for deep reflection

`--add-exports` enables normal access to **public types and public/protected members** in the exported package, per Java access rules.

It does not mean:

- Every other package in the source module is also exported.
- Package-private or private classes/members become public.
- Reflection can call `setAccessible(true)` on private fields or private methods in that package.
- The target module automatically gains readability to the source module.

If a library needs to read or write private fields via reflection, consider `--add-opens`, not just adding `--add-exports`.

### 2.2. Compile-time configuration

When module code needs to import public types from an unexported package, `javac` supports `--add-exports`:

```bash
javac --module-path mods --add-exports=com.vendor.legacy/com.vendor.internal=com.example.app -d out ...
```

In the example, the application module must still declare the dependency if it needs to read the source module:

```java
module com.example.app {
    requires com.vendor.legacy;
}
```

`--add-exports` handles exporting the package to the target module; `requires` handles readability. One permission does not imply the other.

### 2.3. Runtime configuration

If code was compiled relying on an extra export, runtime also requires the matching configuration:

```bash
java --module-path mods --add-exports=com.vendor.legacy/com.vendor.internal=com.example.app -m com.example.app/com.example.app.Main
```

If you add the option only at compile time and omit it at runtime, the module system can still block access when the application executes.

## 3. --add-opens: Allowing Deep Reflective Access

`--add-opens` opens a package so code in the target module can perform **deep reflection** on members of the package at runtime.

Syntax:

```text
--add-opens <source-module>/<package>=<target-module>(,<target-module>)*
```

Example:

```text
--add-opens=com.example.app/com.example.domain=com.example.orm
```

Suppose module `com.example.app` has package `com.example.domain` containing models with private fields. ORM `com.example.orm` needs reflection to read/write those fields. The option above opens only the domain package to only the ORM module.

### 3.1. Why does reflection need opens?

A class may have private fields:

```java
package com.example.domain;

public class Customer {
    private String email;

    public Customer(String email) {
        this.email = email;
    }
}
```

An ORM library can discover the field via reflection and want to access its value even though the field is non-public. On the module path, the package must be opened to the module performing deep reflection.

If the package is not opened, operations such as `Field.setAccessible(true)` may throw `InaccessibleObjectException` (a runtime exception) when the module system denies access.

Once the package is properly opened to the ORM module, the framework can perform deep reflection according to Java reflection rules.

### 3.2. --add-opens takes effect only at runtime

`--add-opens` is a runtime option of the Java launcher; it is not a compiler option for letting code import an unexported package.

Example:

```bash
java --module-path mods --add-opens=com.example.app/com.example.domain=com.example.orm -m com.example.app/com.example.app.Main
```

If opening the package is part of a long-term module configuration, you can declare `opens` in `module-info.java`:

```java
module com.example.app {
    opens com.example.domain to com.example.orm;
}
```

`opens` in the module descriptor and `--add-opens` both govern runtime reflective access. The descriptor form is preferable when the package-owning module controls configuration; the command-line form is useful when an external integration cannot yet modify the module descriptor.

### 3.3. opens is not exports

A package opened for reflection does not automatically become an API that other modules can import in Java code:

```java
module com.example.app {
    opens com.example.domain to com.example.orm;
}
```

Module `com.example.orm` can use deep reflection into the domain package when the module graph and related conditions match. However, `opens` does not replace `exports` for ordinary Java access to public types.

Conversely, exporting a package does not allow other modules to break encapsulation and access private members via reflection.

## 4. Direct Comparison of --add-exports and --add-opens

| Criterion | `--add-exports` | `--add-opens` |
| --- | --- | --- |
| Goal | Access public types/members in a package | Deep reflection into package members, including non-public ones |
| Phase | Compile time and runtime | Runtime |
| Used with `javac` | Yes | No |
| Used with Java launcher | Yes | Yes |
| Allows importing public types in an unexported package | Yes, if module readability is also satisfied | No |
| Allows reflection to access private members | Does not automatically grant this | Yes, within the opened package and target |
| Equivalent declaration in `module-info.java` | `exports p to m;` | `opens p to m;` |
| Scope | One specific package and target | One specific package and target |

Choose based on the error type:

- `package ... is not visible` or compile error due to unexported package: check `requires` and `--add-exports`.
- `InaccessibleObjectException` when a framework reflects on private fields/methods: check `opens` or `--add-opens`.
- `module X does not read module Y`: check `requires` or an appropriate readability mechanism; not solved solely by `--add-exports`/`--add-opens`.

## 5. Identifying the Correct Source Module, Package, and Target Module

An option works only when all three parts are identified accurately.

### 5.1. Source module

This is the module **owning the package to be exported/opened**. It is not necessarily the calling library's module.

Example:

```text
com.example.app/com.example.domain
^^^^^^^^^^^^^^^
source module
```

If the package belongs to the application module, the source module is `com.example.app`. If the package belongs to the JDK, the source module may be `java.base`, `java.sql`, `java.desktop`, or another JDK module.

### 5.2. Package

The package must be the exact package name, not a class name or JAR file name.

Example:

```text
com.example.app/com.example.domain=com.example.orm
                ^^^^^^^^^^^^^^^^^^
                package
```

The option exports/opens only the specified package. It does not apply automatically to subpackages like `com.example.domain.internal`; if another package is needed, evaluate and configure it separately.

### 5.3. Target module

Target is the module receiving permission:

- If the caller is a named module, specify that module's name, e.g., `com.example.orm`.
- If the caller is on the classpath, its code belongs to the unnamed module; use `ALL-UNNAMED` when granting access to unnamed modules is genuinely needed.

Do not use a JAR filename like `orm-1.2.jar` as the target module. Determine the module name from `module-info.java`, `Automatic-Module-Name` metadata, or the derived automatic module name.

### 5.4. Limits of ALL-UNNAMED

Example:

```text
--add-opens=java.base/java.lang=ALL-UNNAMED
```

This option opens package `java.lang` in module `java.base` to **every unnamed module** in the JVM. Its scope is broader than opening a package to one specific module.

Use `ALL-UNNAMED` only when the caller genuinely runs in the unnamed module and no narrower target module can be specified. If the library is already a named module, specify the library's module name.

## 6. Example: Integrating an ORM That Needs Reflection on Models

Suppose an application has two modules:

```text
com.example.app
  └── com.example.domain.Customer

com.example.orm
  └── framework needing to read private fields of Customer
```

Application module:

```java
module com.example.app {
    requires com.example.orm;
    exports com.example.api;
}
```

The ORM module can use the application's public API via exported packages. If the framework must access private fields in the domain package, open only that package:

```java
module com.example.app {
    requires com.example.orm;
    exports com.example.api;
    opens com.example.domain to com.example.orm;
}
```

Or, when the application's module descriptor cannot be modified, pass the option at runtime:

```bash
java --module-path mods --add-opens=com.example.app/com.example.domain=com.example.orm -m com.example.app/com.example.app.Main
```

Here only `com.example.domain` is opened and only module `com.example.orm` receives deep reflection access. Other API packages maintain their own export/open policies.

### 6.1. If the ORM is on the classpath

If the ORM is not packaged as a named module and is loaded from the classpath, the option's target is `ALL-UNNAMED`:

```bash
java --module-path mods --class-path "libs/orm.jar" --add-opens=com.example.app/com.example.domain=ALL-UNNAMED -m com.example.app/com.example.app.Main
```

This illustrates scoping for a caller on the classpath. In real applications, also ensure readability and classpath/module-path integration align with the application's module graph. Do not add `ALL-UNNAMED` blindly before knowing where the framework is loaded from.

## 7. Example: Library Needing a Public Type in an Unexported Package

Another case: an application needs to compile against and call a public class in a library module's unexported package.

Suppose:

```java
module com.vendor.legacy {
    // Does not export com.vendor.legacy.internal
}
```

Application:

```java
module com.example.app {
    requires com.vendor.legacy;
}
```

If a mandatory integration uses a public type from `com.vendor.legacy.internal`, an export can temporarily be added at compile time:

```bash
javac --module-path mods --add-exports=com.vendor.legacy/com.vendor.legacy.internal=com.example.app -d out ...
```

And at runtime:

```bash
java --module-path mods --add-exports=com.vendor.legacy/com.vendor.legacy.internal=com.example.app -m com.example.app/com.example.app.Main
```

If the package-owning module can be edited and exporting aligns with the API design, an explicit qualified export in the module descriptor is easier to manage:

```java
module com.vendor.legacy {
    exports com.vendor.legacy.internal to com.example.app;
}
```

Yet if a package is named `internal`, depending on it remains coupling to implementation details. Treat this as a time-bounded integration exception with a plan to replace it with a supported API.

## 8. Using Options on JDK Internals: Only When No Suitable Alternative Exists

A legacy library might depend on a JDK internal package. Syntactic example of exporting an internal package of `java.base` to an application:

```bash
java --add-exports=java.base/jdk.internal.misc=com.example.app --module-path mods -m com.example.app/com.example.app.Main
```

This is an example of **how to scope the target**, not advice to depend on `jdk.internal.misc`. Internal packages can change or be removed; the option only relaxes module access for the current run.

Before adding an option, you should:

1. Identify the exact stack trace and blocked package.
2. Check whether a newer library version already supports Java 17.
3. Look for a JDK-supported public replacement API.
4. If the dependency must stay temporarily, export/open only the needed package to the exact module calling it.
5. Record the reason and removal criteria for the option.

You can use `jdeps` to locate dependencies on JDK internal APIs:

```bash
jdeps --jdk-internals app.jar
```

The output identifies internal packages the artifact depends on. Finding a dependency does not mean adding `--add-exports` is a permanent solution; review warnings and replace APIs wherever possible.

## 9. Do Not Use --illegal-access as a Broad Workaround

`--illegal-access` was used during earlier module-system transition stages to relax certain reflective accesses to JDK internals. On **Java 17**, this option is no longer a way to re-enable the legacy access behavior; it does not disable strong encapsulation and may merely emit a warning that the option is no longer effective.

Do not add:

```bash
# Do not use as a solution on Java 17:
java --illegal-access=permit -jar app.jar
```

If a library needs access to a specific package, determine the exact requirement and use `--add-exports` or `--add-opens` with a narrow target, after considering upgrading or replacing the library.

## 10. Choose the Narrowest Possible Opening

For mandatory integrations, the goal is minimizing the number of packages and modules granted permissions.

### 10.1. Prefer named targets

If the ORM is module `com.example.orm`, use:

```text
--add-opens=com.example.app/com.example.domain=com.example.orm
```

Use `ALL-UNNAMED` only if the caller genuinely is code on the classpath.

### 10.2. Open only the exact package

If the framework only needs reflection on `com.example.domain`, do not open the entire module:

```java
module com.example.app {
    opens com.example.domain to com.example.orm;
}
```

Avoid `open module com.example.app { ... }` if only one package needs reflection. `open module` opens every package in the module for runtime deep reflection, a far broader scope.

### 10.3. Do not export or open an entire module via CLI

The options do not provide an "export entire module" syntax as a shortcut around picking packages. Each option should name the specific package requiring permission. If an integration needs multiple packages, list each one and verify each need instead of using an unexplained broad configuration.

### 10.4. Avoid opening JDK internals to all code

The following example has a very broad scope:

```text
--add-opens=java.base/java.lang=ALL-UNNAMED
```

It grants all unnamed modules deep reflection into package `java.lang`. Use it only with evidence that a library on the classpath genuinely requires this permission and cannot be upgraded/replaced right away. If the caller is a named module, specify that module rather than opening to all.

## 11. Managing Options in Application Runtime Environments

Options must be passed to **the JVM that actually executes the code needing access**. Adding them to a build command does not automatically ensure the application or test JVM receives the configuration.

Places to inspect:

- Direct `java` launch commands.
- Service startup scripts or container entrypoints.
- Application server JVM options configurations.
- Forked JVMs when running tests.
- Build tool runtimes when spawning child processes.
- Staging/production deployment configurations.

Example running a modular application:

```bash
java --add-opens=com.example.app/com.example.domain=com.example.orm --module-path mods -m com.example.app/com.example.app.Main
```

Do not confuse Maven/Gradle's JVM with the forked test or application JVM. If an error occurs only during tests, put the option on the test JVM; if it occurs in production, configure the production process.

### 11.1. Using the JDK_JAVA_OPTIONS environment variable

The Java launcher supports the `JDK_JAVA_OPTIONS` environment variable to prepend options to the launcher command:

```bash
JDK_JAVA_OPTIONS="--add-opens=com.example.app/com.example.domain=com.example.orm" java --module-path mods -m com.example.app/com.example.app.Main
```

How environment variables are set varies by shell and OS. Use this mechanism only when operations teams strictly manage process environments. For reproducible deployments, placing options directly in startup scripts or deployment manifests is usually easier to control and audit.

### 11.2. Avoid configuration drift across environments

If an option exists only on a developer machine, the application may work locally yet fail in staging or production. Store configuration alongside the application's runtime definitions, documenting:

- Exported/opened package.
- Module receiving access.
- Library or feature requiring that permission.
- Library/JDK version tested.
- Criteria for removing the option.

Do not scatter options across every environment or JVM automatically before identifying which process needs permission.

## 12. Diagnosing Module Access Errors

When encountering an error, categorize by message:

| Message or situation | Common cause | Resolution |
| --- | --- | --- |
| `package ... is not visible` | Package not exported to the compiling module. | Check `requires`, `exports`, or `--add-exports`. |
| `module X does not read module Y` | Missing readability relationship. | Declare `requires` or appropriate readability configuration; export does not replace this. |
| `InaccessibleObjectException` | Reflection blocked by module system because package is unopened. | Open exact package to caller module with `opens` or `--add-opens`. |
| `IllegalAccessError` at runtime | Runtime module access differs from compile time or package is unexported. | Compare runtime options against actual module graph. |
| Error occurs only on classpath | Caller belongs to unnamed module or target configuration is wrong. | Identify caller's module; use `ALL-UNNAMED` only if appropriate. |
| Option fails to fix error | Wrong package, wrong source/target module, or wrong permission type. | Check exact stack trace, module names, and required access type. |

A practical workflow:

1. Read the full message and identify source module, blocked package, and caller module.
2. Determine whether the code needs to import a public type or reflect on non-public members.
3. Inspect module descriptors and how the library is loaded (module path vs classpath).
4. Pick `--add-exports` or `--add-opens` according to the exact need.
5. Limit target to a specific module; use `ALL-UNNAMED` only when the caller resides in the unnamed module.
6. Verify both compile time and runtime when using `--add-exports`.
7. Re-run in the exact test or application JVM.
8. Document a plan to remove the option once dependencies are upgraded.

## 13. Combined Example: Separating Compile Access and Deep Reflection

Suppose an application integrates a legacy library:

- The library has a public type in an unexported package; the application needs to import that type.
- Another ORM needs reflection into private fields of the application's models.

These two needs require two separate configurations:

```bash
# Grant app access to public types of the legacy package:
javac --module-path mods --add-exports=com.vendor.legacy/com.vendor.legacy.internal=com.example.app -d out ...

# At runtime: keep export and open model package to ORM:
java --module-path mods --add-exports=com.vendor.legacy/com.vendor.legacy.internal=com.example.app --add-opens=com.example.app/com.example.domain=com.example.orm -m com.example.app/com.example.app.Main
```

In this example:

- `--add-exports` grants app access to the legacy package's public API.
- `--add-opens` grants ORM deep reflection into the model package.
- `requires` in module descriptors must still describe needed dependencies.
- Do not open the legacy package to the ORM if the ORM does not need it.
- Do not open the model package to all unnamed modules if the ORM is already a named module.

These are two targeted exceptions with different goals; do not merge them into a blanket "open module" setting.

## 14. Common Mistakes and Fixes

| Mistake | Why it happens | Fix |
| --- | --- | --- |
| Using `--add-opens` to fix a package import error. | `opens` serves runtime deep reflection only, not compile-time package exports. | Use `--add-exports` or declare `exports` appropriately. |
| Using `--add-exports` yet `setAccessible(true)` is still blocked. | Exports do not open private members for deep reflection. | Use `--add-opens` or `opens` for the exact caller. |
| Adding option for the wrong source module. | The specified module does not own the package in the stack trace. | Identify the package-owning module via module descriptor or module docs. |
| Writing a JAR filename as target module. | Target must be a module name, not a filename. | Use the name in `module-info.java`, `Automatic-Module-Name`, or the derived module name. |
| Using `ALL-UNNAMED` even though the library is a named module. | Grants permission to all unnamed modules rather than the exact recipient. | Use the library's exact module name. |
| Adding `--add-exports` only at compile time. | Runtime module graph can still block access. | Pass the matching export to the JVM running the application. |
| Assuming exporting a package means the module is already read. | Readability and export are two separate conditions. | Add `requires` or appropriate readability configuration. |
| Opening the entire module to fix one field error. | Deep reflection scope exceeds actual need. | Use qualified `opens` for the exact package and target. |
| Using `--illegal-access=permit` on Java 17. | Legacy transition flag no longer reopens encapsulation. | Use public APIs or exact options after identifying the need. |
| Forgetting options in test/production JVMs. | Build JVM and runtime JVM may be separate processes. | Configure the exact process executing the code requiring access. |

## 15. Principles for Bounding Permissions in Mandatory Integrations

When a dependency requiring special permissions cannot be removed immediately, apply these principles:

1. **Grant only the right permission type:** public APIs need exports; deep reflection needs opens.
2. **Select only the exact package:** do not open sibling packages or the whole module without evidence of need.
3. **Select only the exact caller:** prefer named module names; `ALL-UNNAMED` only when calling code truly belongs to the unnamed module.
4. **Keep readability separate:** handle `requires`/module graph independently of exports/opens.
5. **Place options on the exact runtime:** verify tests, services, or forked apps receive the configuration.
6. **Prefer supported APIs:** upgrade libraries, use SPIs, or use public APIs before accessing internals.
7. **Document and retire:** every exception needs a reason, owner, and removal criteria.

Opening a package is a module-boundary decision. A small, target-specific, time-bounded configuration is far easier to govern than a broad option added just to make errors disappear.

## 16. Practice Exercises

### Exercise 1 — Choosing the right option

An application fails to compile because it needs to import a public class from an unexported package of module `com.vendor.lib`. Identify the needed option and explain why `--add-opens` does not fix the import error.

### Exercise 2 — Deep reflection

An ORM running in module `com.example.orm` needs to read private fields in package `com.example.model` of module `com.example.app`. Write the minimally scoped runtime option. Then write the equivalent `opens` directive in `module-info.java`.

### Exercise 3 — Caller on the classpath

A legacy framework running on the classpath needs reflection into package `com.example.model` of a modular application. Write the appropriate option and explain which group of callers `ALL-UNNAMED` grants access to.

### Exercise 4 — Separating readability and exports

An application already has `--add-exports`, yet the compiler reports that `com.example.app` does not read `com.vendor.lib`. Analyze why export does not automatically add readability and write the required dependency.

### Exercise 5 — Narrowing scope

An application currently uses `--add-opens=com.example.app/com.example=ALL-UNNAMED`, yet the stack trace shows only ORM module `com.example.orm` needs reflection into package `com.example.model`. Propose a narrower configuration and explain the risks of the current one.

### Exercise 6 — Workaround retirement plan

A library uses a JDK internal package and requires `--add-exports`. Outline a plan to inspect dependencies using `jdeps --jdk-internals`, find replacement APIs, upgrade the library, and test after removing the option.

## 17. Official Java 17 Documentation

- [Java SE 17 Launcher — add-exports and add-opens](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): syntax and passing options to the JVM.
- [Java SE 17 javac — add-exports](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): additional export options during compilation.
- [JLS Java SE 17, §7.7 — Module Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7): module declarations, `requires`, `exports`, `opens`, and related directives.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): module system design and options for adjusting module boundaries.
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): strong encapsulation of JDK internal components in modern Java releases.
- [Java SE 17 jdeps tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html): dependency analysis, including dependencies on JDK internal APIs.

For mandatory integrations, remember: **`--add-exports` is for public access across package boundaries; `--add-opens` is for deep reflection at runtime**. Identify the exact source module, package, and target module; grant the minimal necessary permissions while keeping readability separate. This is a clearly bounded workaround, not a reason to depend long term on JDK internal APIs.
