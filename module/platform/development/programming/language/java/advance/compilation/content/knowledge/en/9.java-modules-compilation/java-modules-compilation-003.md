# module-info.java with requires and exports in Java

Since Java 9, the Java Platform Module System (JPMS) allows programs to explicitly declare **modules**, their dependent modules, and the packages exposed as APIs. The `module-info.java` file is the *module declaration*: it describes boundaries between components larger than packages and is processed by the compiler to verify access permissions.

The two central keywords are:

- **`requires`:** which modules the current module needs to read in order to use eligible exposed types from those modules.
- **`exports`:** which of the current module's packages are allowed to be used across module boundaries under ordinary Java access rules.

A module `A` writing `requires B;` **cannot** use every class in `B`: `B` must also export the package containing the desired class, and the class/member must have appropriate access permissions. Conversely, `B` writing `exports p;` does not automatically make every other module read `B`. Understanding **readability**, **exports**, and **Java access modifiers** together is key to fixing JPMS errors.

This lesson uses Java 17+ with a complete two-module example, distinguishes `requires`, `requires transitive`, `requires static`, and `exports ... to`, and explains their relationship with module path, classpath, reflection, and common errors.

## 1. How Do Modules Differ from Packages and JARs?

- A **package** organizes the namespace for classes, interfaces, records, enums, and annotations; for example, `com.example.greetings.api`.
- A **named module** is a unit with its own name that owns packages and declares module dependencies and API surface via a module descriptor.
- **`module-info.java`** is the source describing an *explicit named module*; when compiled, the compiler produces `module-info.class`.
- A **modular JAR** is a JAR with a module descriptor. A plain JAR can run on the classpath without a descriptor. A JAR without a descriptor, when placed on the module path, can become an *automatic module* under appropriate conditions.
- **Module path** tells tools the location of modules; **classpath** is the traditional class-lookup mechanism. They have different ways of resolving dependencies.

Example of a module with two packages:

```text
Module com.example.greetings
    com.example.greetings.api
        Greeting.java
    com.example.greetings.internal
        Formatter.java
```

Usually only the `api` package needs to be exposed. Even though `Formatter` is a `public class`, if the `internal` package is not exported, another named module cannot simply import and use this class across the module boundary.

In many build projects, a module has its source at `src/main/java/module-info.java`. When experimenting with multiple modules using `javac` directly, you can arrange `src/<module-name>/module-info.java`; this is an illustrative layout compatible with `--module-source-path src`.

## 2. Structure of a Module Descriptor

A valid `module-info.java` file:

```java
module com.example.greetings {
    exports com.example.greetings.api;
}
```

A consuming module has its own descriptor:

```java
module com.example.app {
    requires com.example.greetings;
}
```

Things to remember:

1. A descriptor uses the `module` keyword, followed by the module name and a directive block; there is **no** `package ...;` or `ModuleInfo` class.
2. `module-info.java` is placed at the root of the module's source directory, not a separate copy inside each package.
3. Module names usually follow reverse-domain notation, but **are not required to match package names**.
4. `exports` takes a **specific package name**, not a class name. Exporting `com.example.greetings` **does not automatically export** `com.example.greetings.api`.
5. `requires` takes a **module name**, not a package name or a JAR filename.
6. Most modules do not need to declare `requires java.base;`: Java automatically provides a readability relationship to `java.base` according to language rules.

Regular Java source files reside in the module's packages and declare `package` as usual. When compiled, `module-info.class` sits at the output root of the module.

## 3. Conditions for Accessing a Type from Another Module

If module `com.example.app` wants to use `com.example.greetings.api.Greeting`:

| Condition | Responsibility |
| --- | --- |
| Module `com.example.greetings` is resolved and observable | Module path and tool configuration |
| `com.example.app` reads `com.example.greetings` | `requires`, `requires transitive`, or a valid readability relationship |
| `com.example.greetings` exports package `com.example.greetings.api` to app | `exports`, including qualified exports if any |
| Type/member permits access | `public`, `protected`, package-private, `private` per the JLS |

The first three steps involve JPMS; the final step is still Java's language access control check. Having the module and knowing the package name does not mean any type can be accessed.

Conceptual diagram:

```text
com.example.app                 com.example.greetings
┌──────────────────┐  requires  ┌──────────────────────────┐
│ Main             │ ─────────▶ │ exports ...api           │
│ import Greeting  │            │ api.Greeting (public)    │
└──────────────────┘            │ internal.Formatter       │
                                │   (not exported)         │
                                └──────────────────────────┘
```

The `requires` arrow represents a dependency/readability relationship. `exports` is the provider module's policy; it **does not** automatically create a reverse arrow or put every package into the API.

## 4. Complete Java 17+ Example with Two Named Modules

Create the file structure in the project directory `module-lab`:

```text
module-lab/
└── src/
    ├── com.example.greetings/
    │   ├── module-info.java
    │   └── com/example/greetings/
    │       ├── api/Greeting.java
    │       └── internal/Formatter.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java
```

### File 1: src/com.example.greetings/module-info.java

```java
module com.example.greetings {
    exports com.example.greetings.api;
}
```

The `api` package is exported; `internal` is kept hidden at the module boundary.

### File 2: src/com.example.greetings/com/example/greetings/api/Greeting.java

```java
package com.example.greetings.api;

import com.example.greetings.internal.Formatter;

public final class Greeting {
    private Greeting() {}

    public static String hello(String name) {
        return Formatter.format(name);
    }
}
```

`Greeting` is the public API. It calls into `internal.Formatter` because both packages are in the **same module**. No `exports internal` is needed for internal communication.

### File 3: src/com.example.greetings/com/example/greetings/internal/Formatter.java

```java
package com.example.greetings.internal;

public final class Formatter {
    private Formatter() {}

    public static String format(String name) {
        return "Hello, " + name + "!";
    }
}
```

This class is intentionally declared `public` while its package is not exported, in order to observe JPMS **strong encapsulation**. `public` is only one of the conditions for cross-module access.

### File 4: src/com.example.app/module-info.java

```java
module com.example.app {
    requires com.example.greetings;
}
```

### File 5: src/com.example.app/com/example/app/Main.java

```java
package com.example.app;

import com.example.greetings.api.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.hello("Lan"));
    }
}
```

### Compile

Run from the `module-lab` directory. Create the `mods` directory first (for example, using `mkdir mods`). Use the following single-line command on Java 17+:

```bash
javac -encoding UTF-8 --module-source-path src -d mods --module com.example.greetings,com.example.app
```

Explanation:

- `--module-source-path src` uses the `src/<module-name>/...` layout to locate multiple module sources.
- `--module` (short form `-m`) selects the two modules to compile.
- `-d mods` writes classes into the output directory per module.
- `-encoding UTF-8` specifies the charset of the Java files.

After compilation, the output contains:

```text
mods/
    com.example.greetings/
        module-info.class
        com/example/greetings/api/Greeting.class
        com/example/greetings/internal/Formatter.class
    com.example.app/
        module-info.class
        com/example/app/Main.class
```

### Run

```bash
java --module-path mods --module com.example.app/com.example.app.Main
```

Exact stdout:

```text
Hello, Lan!
```

In the syntax `--module <module>/<main-class>`, the part before the slash is the **module name**, and the part after it is the **binary class name** containing `main`. It is not a physical path to a `.class` file.

This command works identically on Windows, macOS, and Linux because the module path contains only **one entry**, `mods`; there is no multi-entry separator. When there are multiple paths, Windows uses `;` while macOS/Linux uses `:`.

For clear results, you should run the lab from a clean output directory. If leftover class files from a previous run remain, it becomes hard to tell whether an error comes from the current descriptor or a stale artifact.

## 5. Missing requires: Module Does Not Read Dependency

Using a copy of the lab to test, modify `src/com.example.app/module-info.java` to:

```java
module com.example.app {
}
```

Keep `Main.java` with `import com.example.greetings.api.Greeting;`. This is a **case intentionally causing a compilation error**. Even though `Greeting` is `public` and the package is exported by the library module, the app module does not declare a readability relationship to greetings.

The diagnostic typically means:

```text
package com.example.greetings.api is not visible
(module com.example.app does not read module com.example.greetings)
```

This message **illustrates the meaning**, not a fixed stdout/stderr across all JDKs. Depending on how you compile, the exact message may vary.

Fix properly by restoring:

```java
module com.example.app {
    requires com.example.greetings;
}
```

`import` only enables using short names in source code and does not replace a module readability relationship. The type name may be known to the compiler yet still invalid if the current module does not read the module that owns it.

## 6. Missing exports: Package Is Not Exposed as API

Continuing with an independent copy, keep `requires com.example.greetings;` in app but change the library descriptor to:

```java
module com.example.greetings {
}
```

Now app reads the greetings module, yet **does not have permission to use the `api` package** under ordinary access rules. The diagnostic usually mentions `package ... is not visible` because the provider module does not export the package to app.

Another experiment: restore `exports com.example.greetings.api;` but in app try importing:

```java
import com.example.greetings.internal.Formatter;
```

This is also invalid: `internal` is not exported, even though `Formatter` is a `public class`. You should not solve this by exporting every package; the design goal is for app to call the stable `Greeting` API and not depend on the `Formatter` implementation.

Another detail: inside an exported package, a class declared without `public` still does not become public to other modules. `exports` does not elevate the visibility of package-private symbols.

## 7. Exporting an Entire Package vs. Qualified Exports

Unqualified syntax:

```java
module com.example.greetings {
    exports com.example.greetings.api;
}
```

It allows modules that read greetings to access eligible types and members of the `api` package.

If you need to grant access only to specific modules:

```java
module com.example.greetings {
    exports com.example.greetings.api;
    exports com.example.greetings.internal to com.example.testing;
}
```

This is a **qualified export**. Module `com.example.testing` can use public types in `internal` **if it also reads** greetings. Other modules do not have the corresponding export.

Comparison:

| Provider descriptor | Result |
| --- | --- |
| Package `p` not exported | Package `p` has no ordinary cross-module public API access |
| `exports p;` | Exports to any module with appropriate readability |
| `exports p to m1, m2;` | Exports specifically to modules named `m1`, `m2` when they read the provider |

`exports com.example.greetings;` **does not** export `com.example.greetings.api`: Java has no rule that "exporting a package exports all subpackages."

Target module names in qualified exports must be exact. Exporting to a module does not automatically add `requires` in that module, nor does it grant access to package-private classes/members of the exported package.

## 8. requires transitive and Dependencies Present in the Public API

Suppose the system has three modules:

```text
com.example.app
      |
      v
com.example.facade
      |
      v
com.example.model
```

The model module:

```java
module com.example.model {
    exports com.example.model.api;
}
```

The facade module exposes an API using `User` types from model:

```java
module com.example.facade {
    requires transitive com.example.model;
    exports com.example.facade.api;
}
```

The app module:

```java
module com.example.app {
    requires com.example.facade;
}
```

**`requires transitive`** allows modules reading facade to also gain a readability relationship to model under JPMS rules. This is useful if facade's API has methods that accept or return types from model.

Do not interpret transitive as "facade automatically re-exports every class of model." Model still must export the package containing `User`; types and members still obey access control.

Comparison:

- `requires com.example.model;`: facade reads model; app reading facade **does not automatically** read model.
- `requires transitive com.example.model;`: facade reads model and propagates readability to modules that read facade.

Use transitive when the dependency is part of the API contract, not to avoid thinking about which module actually has which dependency.

## 9. requires static: Compile-Time Dependency, Optional at Runtime

Example:

```java
module com.example.report {
    requires static com.example.annotations;
}
```

Here `static` is a modifier on a **module dependence**, unrelated to static methods/fields of a class. It means:

- The annotations module must be present at **compile time** for the compiler to resolve the needed types.
- That module **is not mandatory for runtime resolution** solely because of the `requires static` declaration.
- If the code actually uses a class from annotations during execution while that module is absent, class-loading errors can still occur.

Certain dependencies used only for compile-time annotations fit this option, but `requires static` must not be treated as a magic trick that "automatically drops any dependency while still running."

You may encounter the combination `requires static transitive` in appropriate API designs; you must understand both runtime optionality and JLS readability propagation together.

| Directive | Compile-time dependency | Mandatory for runtime resolution | Propagates readability downstream |
| --- | --- | --- | --- |
| `requires m;` | Yes | Yes per requires relationship | Not automatically |
| `requires transitive m;` | Yes | Yes | Yes |
| `requires static m;` | Yes | Not mandatory | Not automatically |

## 10. Implicit java.base and Other Platform Modules

Most modules have an implicit relationship to `java.base`, which contains common APIs such as `java.lang.String`, `java.util.List`, and `java.nio.file.Path`. There is no need to add `requires java.base;` for the examples in this lesson.

However, not every `java.*` package resides in java.base. For example, to use JDBC:

```java
module com.example.database {
    requires java.sql;
}
```

To use the Java 11+ HTTP Client API, a module may need:

```java
module com.example.httpclient {
    requires java.net.http;
}
```

When a platform API is reported as missing by the compiler, check **which module contains the API** and add the corresponding `requires`. `import java.sql.Connection;` cannot replace `requires java.sql;` in an explicit named module.

## 11. exports vs. opens in Reflection

JPMS distinguishes ordinary Java access from **deep reflection**. `exports` makes a package's public API available under language rules; it does not automatically let every framework access private fields via `setAccessible(true)`.

For example, a module can allow a JSON framework to reflect into a package:

```java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.internal to com.example.json;
}
```

- `exports ...api` grants ordinary access to the public API, provided the consumer reads the module.
- `opens ...internal to com.example.json` permits deep reflection in the internal package under JPMS conditions; it **does not turn the internal package into a compile-time API** that other modules can freely import.
- In an exported package, ordinary reflection on public members can be valid without deep opens; do not equate all reflection with `opens`.
- `open module m { ... }` is another declaration that opens the module's packages for deep reflection, without automatically exporting all packages.

An `InaccessibleObjectException` from an ORM/serialization library usually leads to checking `opens`; a compiler `package ... is not visible` error usually leads to checking `requires` and `exports`. Those are two different permission layers.

Flags such as `--add-exports` and `--add-opens` are used to widen permissions in specific compile/run contexts, useful for migration or diagnostics; they should not be used routinely to legitimize an application's dependency on internal packages.

## 12. Module Path, Classpath, and Automatic Modules

Classpath and module path differ in more than just flag names:

| | Classpath | Module path |
| --- | --- | --- |
| Flag | `-cp` / `--class-path` | `-p` / `--module-path` |
| Lookup target | Class by package/binary name | Module by module name |
| Source descriptor | Not required | Explicit module has `module-info.class` |
| Boundaries | Traditional access modifiers | Adds readability, exports/opens |
| Launcher | `java -cp ... Main` | `java -p mods -m module/package.Main` |

Classes on the classpath usually belong to the **unnamed module** of the corresponding class loader. A named module does not read unnamed modules by default; therefore, adding `module-info.java` to an application that previously used only `-cp` may make some dependencies on the classpath inaccessible from the named module.

An **automatic module** is typically a JAR without a descriptor placed on the module path. It gets a synthesized module name from the manifest's `Automatic-Module-Name` or the filename, and JPMS provides special compatibility rules for it. It is a migration tool, not synonymous with an explicit module designed with careful package boundaries.

When building a new library, establish a stable module name; when depending on legacy JARs, check the actual module name instead of guessing from the Maven artifactId.

## 13. Packaging and Inspecting Module Descriptors

After compiling the two-module example, you can create a modular JAR from the greetings output (create the `lib` directory first):

```bash
jar --create --file lib/com.example.greetings.jar -C mods/com.example.greetings .
```

This JAR has `module-info.class` at its root and contains classes under the proper package path. You can inspect it:

```bash
jar --describe-module --file lib/com.example.greetings.jar
```

The command describes the module name, requires, exports, and packages based on actual information in the JAR. You should not hardcode the verbatim command output across all JDKs.

If you want to run the application using that modular JAR, configure the module path so that only **one clearly selected version of greetings** is present. In the lab, `mods` still contains greetings. Do not accidentally leave multiple versions with the same name across different entries and assume the tooling will always pick the expected version.

With the initial configuration, the clearest command remains:

```bash
java --module-path mods --module com.example.app/com.example.app.Main
```

Diagnostic tools:

- `java --show-module-resolution --module-path mods --module com.example.app/com.example.app.Main`: observes module resolution before execution; log output may vary across JDKs.
- `jar --describe-module --file <path-to-jar>`: reads the descriptor or describes the automatic module if the JAR has no descriptor.
- `jdeps --print-module-deps ...`: analyzes bytecode dependencies according to the tool's mechanism; cannot infer all dynamic reflection dependencies.
- `javap -p mods/com.example.greetings/module-info.class`: inspects the descriptor's class file metadata.

## 14. Common Errors and How to Diagnose Them

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| `module not found: com.example.greetings` | Dependency module is missing from the module path or module name is wrong | Check `--module-path`, module name, and modular JAR/source |
| `package ... is not visible` / `does not read` | Consumer lacks a readability relationship | Check `requires` in the consumer's descriptor |
| `package ... is not visible` / `does not export` | Provider does not export the right package to the consumer | Check `exports` or qualified exports |
| `cannot find symbol` | Wrong type name, class does not exist, or invalid context | Check imports, packages, module path, signatures, and access |
| `InaccessibleObjectException` | Deep reflection is blocked | Identify caller/target module and required `opens` |
| Runtime module resolution error | Mandatory module requirement not satisfied or invalid graph | Check the full runtime module path and descriptors |
| `NoClassDefFoundError` | Runtime dependency failed to load; may relate to `requires static` or class version | Check dependencies and root cause |
| `UnsupportedClassVersionError` error | JVM is older than the built class-file version | Check toolchain and `--release` |
| Two modules sharing a package cause a conflict | Split packages can violate module graph/package definition rules | Separate package ownership and audit the module path |
| Works in IDE but fails in terminal | IDE adds a different module path or compiler flags | Compare `javac`, `java` commands and actual JDKs |

A "package not visible" error can result from **not reading the module** or from **not exporting the package**. Read `javac`'s specific explanation line before fixing; do not reflexively add `exports` to the provider.

Quick diagnostic principles:

1. Does the running code belong to a named module or classpath/unnamed module?
2. What is the dependency's module name, and is it resolved?
3. Does the consumer have `requires` or the needed readability relationship?
4. Does the provider export the exact package (not a parent package) to the consumer?
5. Is the class/member `public` or does it have appropriate access permissions?
6. Does the error involve ordinary access or deep reflection?
7. Do the compile-time and runtime module paths contain **the same version** of the dependency?

## 15. When Should You Use requires transitive or Qualified Exports?

**Facade library whose public API depends on types from a model module:** consider `requires transitive model` so consumers receive the readability needed for API signatures, provided model exports the appropriate package.

**Library needing to call an internal implementation module without exposing the dependency's types in the API:** use regular `requires dependency`.

**A technical package intended only for modules you control:** `exports p to named.consumer;` may fit, though if that package is genuinely a private implementation, keep it unexported.

**Framework needing to instantiate entities via deep reflection:** consider `opens p to framework.module;` instead of blanket `exports`; the framework's module name must match the actual module path.

**Dependency needed only at compile time such as annotations:** consider `requires static`, while evaluating whether runtime code actually depends on any of its types.

These modifiers express architectural relationships. They are not "error-silencing tricks" to be substituted arbitrarily.

## 16. Self-Check Exercises

**1.** `com.example.app` writes `requires com.example.greetings;`. If the greetings module does not export the `api` package, can app import `Greeting`?

**Answer:** No. Readability exists, but the package is not exported.

**2.** The greetings module has `exports com.example.greetings.api;`. If app has no reads relation to greetings, is export alone enough to use `Greeting`?

**Answer:** No. The consumer must read the provider.

**3.** Does `exports com.example.greetings;` automatically export `com.example.greetings.api`?

**Answer:** No. An export applies only to the exact specified package.

**4.** Why is `Formatter` `public` yet app cannot import from `internal`?

**Answer:** The internal package is not exported; a class modifier does not bypass module boundaries by itself.

**5.** Facade provides an API returning the `User` type from model. Which declaration expresses that facade consumers also need readability to model?

**Answer:** `requires transitive com.example.model;` in facade, while model must also export the needed package.

**6.** Does `requires static com.example.annotations;` guarantee the annotations library is always present at runtime?

**Answer:** No. Runtime resolution is not mandatory merely because of requires static; code that truly depends on it can still fail if the type is absent.

**7.** A framework needs to read private fields via reflection. Is only `exports` on the model package sufficient?

**Answer:** Not necessarily; deep reflection usually requires `opens` or an appropriate equivalent permission mechanism.

**8.** After compiling the lab, which command is run and what is the output?

**Answer:** `java --module-path mods --module com.example.app/com.example.app.Main`; prints exactly `Hello, Lan!`.

## 17. Conclusion and Official Learning Resources

`module-info.java` creates a clear contract between modules. **`requires`** describes dependencies and readability; **`exports`** determines which packages form the cross-module API; `public` and Java rules still restrict access to individual types and members. `requires transitive` is used when a dependency must propagate to consumers, `requires static` represents a dependency mandatory at compile time yet optional at runtime, and qualified exports share a package only with named modules.

When encountering an error, separate three questions: **has the module been found and read, has the package been exported, and does the type/member have valid access permissions?** Once you grasp this order, `javac` diagnostics become easier to understand and module descriptors can maintain proper architectural boundaries.

References:

- [JLS Chapter 7 — Packages and Modules (`7.7)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html), module definitions and `requires`/`exports`.
- [JDK 21 javac manual](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html), especially `--module-source-path`, `--module-path`, `--module`.
- [JDK 21 java launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html), how to launch named modules.
- [java.lang.module JDK 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/package-summary.html), resolution/readability rules.