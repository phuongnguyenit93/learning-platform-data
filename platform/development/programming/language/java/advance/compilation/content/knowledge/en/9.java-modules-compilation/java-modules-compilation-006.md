# Module Readability, Package Accessibility, and Split Packages in Java

The **Java Platform Module System (JPMS)** was introduced in Java 9 to describe dependencies between **named modules**, control which packages are public API, and prevent applications from accidentally depending on unexposed implementation parts. When compiling Java 17 code with `javac`, to access a class from another module, having that class be `public` is **not enough**: **readability** relationships, package **exports** permissions, and normal Java access control must all be evaluated simultaneously.

Another situation that very frequently appears when migrating a project from the classpath to the module path is a **split package**: two module sources containing classes belonging to the same package name. JPMS designs resolution and class loading to avoid these dangerous ambiguous situations. This lesson explains the three issues from one unified perspective: **which module sees which module, which packages are accessible, and why duplicate package names can break compilation/startup**.

## 1. Model to Remember: Module, Package, Type, and Call

Each named module is described by `module-info.java`:

```java
module com.example.app {
    requires com.example.lib;
}
```

Each package contains compilation units declaring `package ...;`. A module usually contains multiple packages, yet a package does not automatically become public API simply because it has a `public class` inside.

Access checking can be pictured in three layers:

1. **Readability:** Does module A *read* module B? Usually declared via `requires B;`, or received through `requires transitive`.
2. **Package export:** Does module B **export** the package containing the needed type to A? It can export to all modules or to specific modules.
3. **Java access control:** Does the type/method/field have a `public`, `protected`, package-private, or `private` modifier appropriate for the access context?

All three conditions matter for **static access in Java source**. Rules for deep reflection also involve **opens** and will be covered separately.

### Quick combination table

| A reads B | B exports package p to A | Type `p.T` public | Can A use `p.T` in source? |
| --- | --- | --- | --- |
| No | Yes | Yes | **No**: lacks readability |
| Yes | No | Yes | **No**: package is encapsulated |
| Yes | Yes | No (top-level package-private) | **No**: Java access control still applies |
| Yes | Yes | Yes | **Yes**, if the accessed member also has sufficient visibility |
| Yes | Qualified export only to module C, while A differs from C | Yes | **No**: export is not granted to A |

`exports` **does not mean "every class in the package becomes public"**. It only grants access to types and members with sufficient visibility under normal Java rules. A `private` method does not automatically become callable just because its package is exported.

## 2. Readability: `requires` as an Edge in the Module Graph

The declaration:

```java
module com.example.app {
    requires com.example.lib;
}
```

means: `com.example.app` **reads** `com.example.lib`. At compile time, `javac` must locate the dependent module in the appropriate module graph, typically via `--module-path` or `--module-source-path`; at runtime, the launcher/module resolver must also resolve the matching dependency.

**Readability is directional:** A reads B does not mean B reads A. Readability is also **not automatically transitive through ordinary `requires`**.

Suppose:

```text
A --requires--> B --requires--> C
```

A reads B; B reads C; **A does not automatically read C** simply because a path exists through B. If A needs to use APIs from C directly, A must have a valid read edge to C, or B must publish its dependency on C via `requires transitive C;`.

Every named module **implicitly reads `java.base`** (except for the special definition of `java.base` itself), so code can use `String` and `Object` without writing `requires java.base;`. A module also reads itself.

### `requires transitive`: exposing a dependency as part of the API

```java
module com.example.facade {
    requires transitive com.example.lib;
}
```

If A reads `com.example.facade`, then A also reads `com.example.lib` due to the facade's transitive requirement. Note:

- This **extends the readability relation**, and does not automatically export the library's packages.
- The library must still `exports` the corresponding package for A to use public types.
- When a public API returns or accepts a parameter whose type comes from a dependent module, `requires transitive` usually expresses the API relationship more accurately than plain `requires`.

Example graph:

```text
com.example.app --requires--> com.example.facade
com.example.facade --requires transitive--> com.example.lib

=> app reads facade and reads lib
```

Without `requires transitive` on the facade, app is only guaranteed to read facade. When app directly imports the library API, the fix is to **add `requires com.example.lib` in app** or, if the dependency truly appears in the facade's API, change it to `requires transitive` on the facade.

### `requires static`: mandatory at compile time, optional at runtime

```java
module com.example.client {
    requires static com.example.annotations;
}
```

`requires static` expresses a dependency needed at compile time yet **potentially absent at runtime**. It fits certain annotation APIs or libraries used only during the build, though one cannot conclude that "every call to it will work if the JAR is absent." If runtime code needs to load a class/execute a method from the optional module, actually missing that module can still fail during class linking/loading or execution.

`requires transitive static` is also a modifier combination with its own meaning in the module system; when encountering it, check the exact compile-time/runtime contract and how the dependency is resolved, rather than treating it as completely equivalent to `requires transitive`.

## 3. `exports`: Which Packages Are a Module's Public API?

Library module:

```java
module com.example.lib {
    exports com.example.api;
}
```

This declaration exports package `com.example.api` to all other modules **that have readability on `com.example.lib`**. If the library also has package `com.example.internal` without exporting it, outside code will **not** have permission to statically reference `com.example.internal.Hidden`, even if `Hidden` is `public`.

Example:

```text
com.example.lib
├── module-info.java       // exports com.example.api;
├── com/example/api/Greeting.java
└── com/example/internal/Secret.java
```

| Type name | Package/module condition | Accessible from app reading lib? |
| --- | --- | --- |
| `com.example.api.Greeting` public | Package exported, module read | Yes |
| `com.example.api.Helper` package-private | Package exported, module read | No, still package-private |
| `com.example.internal.Secret` public | Package not exported | No under normal static access |

**Concealed package** is the term for a package not exported to the calling module. Encapsulation enables changing internal implementations without committing a source API to outsiders. `requires` is only a dependency edge; it cannot "unlock" all concealed packages.

### Qualified exports: allowing only specific modules

```java
module com.example.lib {
    exports com.example.api;
    exports com.example.spi to com.example.adapter;
}
```

Here `com.example.api` is broadly exported, while `com.example.spi` is exported **conditionally** only to the named module `com.example.adapter`. Module `com.example.app` having `requires com.example.lib;` still **cannot** statically access `com.example.spi` if not on the allowed list.

Qualified exports are useful when a package is needed by a specific integration module without wanting to make it a broad API. However, they create coupling via **module names** in the descriptor; renaming a module will require reviewing related `to ...` clauses.

**Do not confuse module names and package names.** `module com.example.lib` is an identifier; package `com.example.api` is a separate namespace. They may share prefixes by convention, yet are not required to match.

## 4. Complete Runnable Java 17 Example: `requires transitive` Plus `exports`

The example comprises three named modules in one source tree. This is a complete program requiring no dependencies outside the JDK.

```text
project/
└── src/
    ├── com.example.lib/
    │   ├── module-info.java
    │   └── com/example/api/Greeting.java
    ├── com.example.facade/
    │   ├── module-info.java
    │   └── com/example/facade/Facade.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java
```

**`src/com.example.lib/module-info.java`:**

```java
module com.example.lib {
    exports com.example.api;
}
```

**`src/com.example.lib/com/example/api/Greeting.java`:**

```java
package com.example.api;

public final class Greeting {
    private Greeting() {
    }

    public static String message() {
        return "from library";
    }
}
```

**`src/com.example.facade/module-info.java`:**

```java
module com.example.facade {
    requires transitive com.example.lib;
    exports com.example.facade;
}
```

**`src/com.example.facade/com/example/facade/Facade.java`:**

```java
package com.example.facade;

import com.example.api.Greeting;

public final class Facade {
    private Facade() {
    }

    public static String message() {
        return "facade -> " + Greeting.message();
    }
}
```

**`src/com.example.app/module-info.java`:**

```java
module com.example.app {
    requires com.example.facade;
}
```

**`src/com.example.app/com/example/app/Main.java`:**

```java
package com.example.app;

import com.example.api.Greeting;
import com.example.facade.Facade;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
        System.out.println(Facade.message());
    }
}
```

From the `project` directory, using a JDK capable of compiling Java 17:

```sh
javac --release 17 -encoding UTF-8 -d mods --module-source-path src -m com.example.lib,com.example.facade,com.example.app
java --module-path mods -m com.example.app/com.example.app.Main
```

**Exact stdout:**

```text
from library
facade -> from library
```

The output is the compiled modules:

```text
mods/
├── com.example.lib/
│   ├── module-info.class
│   └── com/example/api/Greeting.class
├── com.example.facade/
│   ├── module-info.class
│   └── com/example/facade/Facade.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
```

Why can `Main` directly import `Greeting` even though `com.example.app/module-info.java` **only has `requires com.example.facade`**? Because facade wrote `requires transitive com.example.lib;`, causing app to also read lib. At the same time, lib exports `com.example.api`, making the public type `Greeting` accessible.

You can inspect the compiled descriptor:

```sh
java --module-path mods --describe-module com.example.facade
javap -v mods/com.example.facade/module-info.class
```

`java --describe-module` displays the module declaration in human-readable form; `javap -v` dives into the `Module` attribute of the `module-info.class` class file. Detailed output formatting varies by JDK version; do not use full stdout help or constant-pool offsets as test assertions.

### Negative test 1: changing `requires transitive` to `requires`

Modify only `src/com.example.facade/module-info.java`:

```java
module com.example.facade {
    requires com.example.lib;
    exports com.example.facade;
}
```

Keep app unchanged and recompile the modules. `Main` directly imports `com.example.api.Greeting`, yet app no longer receives **read** access to lib through facade. The compiler reports an error related to module `com.example.lib` not being read by app or the package not being visible. Exact error lines vary by JDK; **this example is intended to fail compilation**. There are two ways to fix it:

- If facade genuinely exposes the lib API as part of its public contract, restore `requires transitive com.example.lib;`.
- If app intentionally depends on the library itself, add `requires com.example.lib;` to app's descriptor.

### Negative test 2: keeping readability while removing `exports`

Restore `requires transitive` on facade, then change the library's `module-info.java` to:

```java
module com.example.lib {
}
```

App now **reads** lib, yet package `com.example.api` is no longer exported, so `Main` and `Facade` cannot use `Greeting` as a normal API. This is also a **negative test**, not code meant to run successfully. Add `exports com.example.api;` back to restore access.

The experiment shows that both errors can lead to messages like "package is not visible," yet the **root causes differ**: missing readability versus an unexported package.

## 5. `opens` and Reflection Access: Different from `exports`

A package may need to be read by a framework via reflection at runtime, including non-public constructors, fields, or methods. JPMS separates this need from exposing APIs to source code:

- **`exports p;`**: provides ordinary Java access to public types and eligible public or protected members for modules that read the owning module. It also permits some reflection on accessible members without breaking encapsulation.
- **`opens p;`**: opens the package for **deep reflection at runtime**, allowing reflection to attempt suppressing Java language access checks for members in the package under relevant API conditions. It **does not grant permission to import and statically reference from other source code** the way `exports` does.
- **`opens p to x.y;`**: opens the package only to the named module `x.y`.
- **`open module x.y { ... }`**: opens all packages of the module for reflection; this is not synonymous with exporting all packages as a compile-time API.

Example of an appropriate module descriptor:

```java
module com.example.lib {
    exports com.example.api;
    opens com.example.internal to com.example.framework;
}
```

Module `com.example.framework` can be permitted deep reflection into `com.example.internal`; other modules do not automatically inherit this. Another client module still cannot directly `import com.example.internal.Secret;` solely because of `opens`.

**On the same package**, you can both `exports` and `opens` with appropriate scopes. The two directives address different kinds of access.

### Deep reflection and `setAccessible`

Reflection does not bypass all rules simply by calling `setAccessible(true)`. With strong encapsulation, `setAccessible` can be rejected if the named module's package has not been opened properly. One commonly encounters `java.lang.reflect.InaccessibleObjectException` when attempting to access a private member whose module has not `opens`-ed the package to the calling module. Check the specific situation via `AccessibleObject.trySetAccessible()` or the thrown exception.

**Note:** Distinguish shallow reflective access to public members in exported packages from **deep reflection** that needs to bypass Java visibility checks. `exports` does not by default allow a framework from another module to arbitrarily read every private field.

### When frameworks use the classpath

Non-modularized applications typically run in the **unnamed module**. To open a package to a framework on the classpath, runtime configuration may be needed:

```sh
java --add-opens com.example.lib/com.example.internal=ALL-UNNAMED ...
```

This is an **illustrative form of the option**; replace `...` with the actual application launch arguments. `ALL-UNNAMED` is a special target for all unnamed modules, not the name of an ordinary named module. When the library can be edited, prefer declaring properly scoped `opens`/`opens ... to ...` rather than opening too broadly just to avoid a reflection error.

## 6. Split Package: One Package Name Divided Across Multiple Modules

A **split package** occurs when classes belonging to the same **package name** are distributed across multiple modules or class-resolution components. Example:

```text
module.alpha
└── com/example/shared/Alpha.class

module.beta
└── com/example/shared/Beta.class
```

Both modules contain package `com.example.shared`. In pre-JPMS Java or when simply relying on multiple JARs on the classpath, this layout appeared quite often. With named modules on the module path, it complicates resolution and class loading because the package name no longer maps uniquely to a single source.

### Do not overgeneralize

There are **multiple check levels** for split packages:

1. **Readability graph/resolution:** Per the `java.lang.module` API, resolution fails if a module reads two modules that both export **the same package name to it**, or if a module itself contains a package matching a package exported to it by a module it reads.
2. **Layer/class loader:** Defining modules in a module layer/class loader has additional restrictions; for example, creating a layer using **the same class loader** must not have overlapping packages among the modules placed in that loader.
3. **Classpath + module path:** Encountering the same package name in two places can lead to classes not found, unexpected class-source selection, or differences between compile time and runtime, depending on loader/module graph configuration.

Therefore, **"whenever two JARs contain the same package, `javac` is guaranteed to immediately report one single error"** is an oversimplified conclusion: you need to know whether each JAR is on the classpath or module path, how they are resolved, whether the package is exported, and whether they share a class loader. Nevertheless, it remains a **design to avoid** when organizing named modules, because it easily causes builds or launches to fail.

### Resolution error example with two identically exported packages

Suppose two named modules:

**`src/com.example.alpha/module-info.java`:**

```java
module com.example.alpha {
    exports com.example.shared;
}
```

**`src/com.example.beta/module-info.java`:**

```java
module com.example.beta {
    exports com.example.shared;
}
```

They have two different classes yet share package `com.example.shared`. A client module:

```java
module com.example.app {
    requires com.example.alpha;
    requires com.example.beta;
}
```

When the client reads both modules exporting the same package to it, the graph is inconsistent. The message may mention "reads package ... from both ..." or "package ... is declared in module ...", depending on the command and JDK. This is a **negative test model** and does not yet supply the source classes needed to run standalone.

**Do not solve this by renaming classes** if the package name still collides: the issue lies in the **package namespace**. The sustainable solution is to unify package ownership, rename the package in one module, extract a single module owning the whole package, or adjust the dependency structure to avoid reading colliding exports.

### Split package between classpath and module path

For example, an old JAR has `com.example.shared.Legacy` on the classpath, while a new module has `com.example.shared.NewType` on the module path. Depending on how modules are resolved and how the class loader resolves packages, the class on the classpath may not be visible as expected, leading to errors like `NoClassDefFoundError` or `ClassNotFoundException` even though the file actually resides in the JAR.

Do not treat "the JAR is on the classpath so it is guaranteed to be seen" as a general rule when that package also appears in a named module. **Move the package to a single location**, or if genuinely performing a special migration, study `--patch-module` as a controlled workaround.

## 7. Named, Automatic, and Unnamed Modules: Differences During Migration

| Module kind | Formation | Key characteristics to remember |
| --- | --- | --- |
| **Explicit named module** | JAR/directory with a valid `module-info.class` | Readability/exports/opens per descriptor; proactive encapsulation |
| **Automatic module** | Regular JAR placed on the module path and treated by the module system as automatic | Has an automatic or manifest-derived module name; all packages exported, broad readability mechanism to support migration |
| **Unnamed module** | Code loaded from the classpath | No `module-info`; legacy code generally has broader access during migration, yet named modules do not automatically read the unnamed module |

Some consequences:

- **Automatic modules** read other resolved named modules and have compatibility mechanisms with unnamed modules at runtime; they export all packages. This is a migration bridge, not a reason to keep duplicate packages indefinitely.
- **Unnamed modules** read resolved modules under their own rules and can access appropriately exported packages, yet cannot arbitrarily "break open" concealed packages of a named module.
- **Named modules** normally cannot simply `requires` an unnamed module by name because an unnamed module has no module name to list in the descriptor.

When moving an older library onto the module path, check its **automatic module name**, package conflicts, and the library's own dependencies. Moving a JAR from the classpath to the module path **is not just changing one command-line argument**; resolution semantics have changed.

## 8. Commands for Investigating the Module Graph

Common compile/run commands:

```sh
javac --release 17 --module-source-path src -d mods -m com.example.app,com.example.lib
java --module-path mods -m com.example.app/com.example.app.Main
```

This is a **general command template**; use the module tree and module list fitting the project. For the three-module example in section 4, use the exact three-module command provided there, because facade is a required component.

Useful tools:

| Command | Purpose |
| --- | --- |
| `java --list-modules` | View runtime system modules and version info when available |
| `java --module-path mods --describe-module com.example.lib` | View the module descriptor of a module on the path |
| `jar --describe-module --file lib.jar` | View the module description of a JAR, including automatic module info when applicable |
| `jdeps --module-path mods --list-deps mods/com.example.app` | Analyze module dependencies observed from artifacts per configuration |
| `javap -v mods/com.example.app/module-info.class` | Inspect the `Module` attribute in the compiled descriptor |
| `javac --help` and `java --help` | Look up options for the exact JDK, especially module path and related flags |

**`jdeps` is a static dependency analysis tool**, not absolute proof for all reflection/dynamic class loading paths. When results differ from runtime behavior, also check resolved modules, service loading, reflective access, and actual JARs.

### Options `--add-reads`, `--add-exports`, `--add-opens`

During migration or testing, the launcher and compiler may support module graph adjustments:

```text
--add-reads   com.example.app=com.example.lib
--add-exports com.example.lib/com.example.internal=com.example.app
--add-opens   com.example.lib/com.example.internal=com.example.app
```

The three lines above are **syntax templates for reference**, not complete Java commands, and must be applied in the required phase (compiler, runtime, or both, depending on the option):

- **`--add-reads`** adds a readability edge.
- **`--add-exports`** opens access to the package's public API for the specified target.
- **`--add-opens`** opens the package for deep reflection at runtime.

These flags are not synonymous. `--add-exports` does not grant permission to call private methods via reflection; `--add-opens` does not grant permission to import a source package as `exports` does. Certain combinations, especially with `--release` and platform modules, are restricted or rejected.

**Long-term direction:** fixing `module-info.java`, designing packages/APIs, and managing dependencies properly are maintainable solutions. Graph-overriding options suit time-bounded migration or diagnostics; they should not turn into an unbounded set of bypasses.

## 9. Common Errors and Messages

| Symptom | What to check | Proper root-cause fix |
| --- | --- | --- |
| `module not found: ...` | Module path/source path, module name, is JAR valid? | Fix module descriptor and paths; ensure module is visible |
| `package ... is not visible` | Does client module read the owner? Does owner export that package to client? | Fix `requires` and/or `exports` appropriately |
| `package ... is declared in module ..., which does not export it` | Package is concealed | Export the proper package or remove dependency on internal API |
| `module ... does not read ...` | Readability edge is missing | Appropriate `requires` or `requires transitive` |
| `module ... reads package ... from both ...` | Two modules both export a package to the consumer | Eliminate the split package or restructure the graph |
| `InaccessibleObjectException` | Framework attempts deep reflection into an unopened package | `opens`/qualified opens or `--add-opens` at runtime as needed |
| `NoClassDefFoundError` during migration | Compile/runtime paths differ, split package, or missing dependency | Check module path, classpath, resolution, and actual files |
| `IllegalAccessError` at runtime | Binary links to class/member no longer accessible after changing module descriptor/version | Compare descriptors, ABI, and runtime environment |

The error strings above are **common symptoms**; verbatim messages may vary by JDK and check location. A compile error due to invalid export differs from a runtime error due to encapsulation/loader; distinguish the phase where it occurs.

### Step-by-step debugging workflow

1. **Record version and mode:** `javac -version`, `java -version`; actual module path and classpath, which JARs are automatic modules?
2. **Identify the owning module of the type:** which package is the class to be imported in, and which JAR/module is it built into?
3. **Draw readability:** which modules does the client `requires`, are `requires transitive` declarations appropriate, and are dependent modules resolved?
4. **Check `exports`:** is the package broadly exported, conditionally exported, or concealed? Do public classes/members have sufficient Java visibility?
5. **If using reflection:** has the package been `opens`-ed to the right framework module? Does the call use shallow reflection or deep reflection?
6. **If there are two copies of a package with the same name:** inspect all JARs on the classpath/module path and resolved modules; avoid randomly changing path order as a permanent "fix."
7. **Verify compile and runtime separately:** a compile-time module graph can differ from runtime due to missing modules, toolchains, automatic modules, or flags.
8. **Fix the source owning the package, rerun from clean output:** avoid stale classes/JARs skewing results.

## 10. Before-and-After Design Scenarios

### Case 1: library with internal APIs

**Before:** the library module puts all packages in `exports` so clients can compile, turning `com.example.internal` into an unintended part of the public interface.

**After:** export only `com.example.api`; keep package `com.example.internal` internal. If a framework needs specific introspection, add `opens com.example.internal to <framework-module>;` for that exact purpose.

### Case 2: facade exposing types from a dependent library

**Before:**

```java
module com.example.facade {
    requires com.example.lib;
    exports com.example.facade;
}
```

The client only `requires com.example.facade` yet also imports the library API, so a readability edge is missing.

**After:** if the library types are a public part of the facade:

```java
module com.example.facade {
    requires transitive com.example.lib;
    exports com.example.facade;
}
```

Then app validly reads lib through facade, provided lib actually exports the necessary package.

### Case 3: a package split across two JARs

**Before:**

```text
legacy-api.jar -> com/example/shared/Api.class
legacy-impl.jar -> com/example/shared/Impl.class
```

When turning each JAR into named/automatic modules and a consumer needs both, the likelihood of conflict increases.

**After:** move `Impl` into a separate package belonging to the implementation module, such as `com.example.impl`; keep the API in `com.example.shared` owned by one module. If the classes need to stay in the same package to use package-private access, review module boundaries and consider merging that code into **one module** instead of splitting JARs the old way.

**Do not use package-private as a communication channel across two named modules** merely because classes share a package name; JPMS distinguishes runtime packages by name and module/class loader, so that arrangement does not preserve package-private privileges across modules.

## 11. Common Misconceptions

**"Once module B is `requires`-ed, every public class of B is accessible."** False. The package containing the class must be exported to the client, and Java visibility still applies.

**"`exports` is enough, `requires` is unnecessary."** False for a client module using normal static access; there must be a valid readability edge.

**"`requires` is always transitive."** False. Only `requires transitive` (or other special mechanisms in the graph) propagates readability to the client under JPMS rules.

**"`opens` is the same as `exports`."** False. `opens` handles reflective access at runtime; it does not expose a package as a compile-time API.

**"`open module` exposes the entire Java API to every module."** False. It opens packages for reflection and does not replace exports needed for source access.

**"All split packages are automatically merged into one by the JVM."** False. Module resolution/class loading imposes limits to avoid ambiguous package namespaces. Do not expect Java to combine packages from multiple named modules into one shared package.

**"Same package name means same package-private access even across two modules."** False. Runtime package identity is tied to the module/class loader and namespace; having the same string name is not enough to merge access privileges.

**"Split packages can be cured with `--add-exports`."** Not necessarily; adding exports can actually create conflicts when a consumer reads multiple modules exporting the same package. Fixing package ownership and the graph is usually right.

**"An automatic module is an explicit named module with `module-info.java`."** False. An automatic module is derived from a JAR on the module path and has migration compatibility behavior; configuration will differ when switching to an explicit descriptor.

**"`jdeps` will detect every reflection dependency."** No. Static analysis does not see all reflection and dynamic class loading, so runtime testing is required.

## 12. Checklist Before Running `javac` with the Module Path

- [ ] Each module has a clear name and an appropriate `module-info.java` if it is an explicit named module.
- [ ] Consumer modules have read edges to the modules directly used by their source.
- [ ] Dependencies that are part of the public API are marked `requires transitive` where appropriate; do not use transitive indiscriminately for everything.
- [ ] Packages intended as public API have `exports` with the proper target (unqualified/qualified).
- [ ] Public types and members have appropriate Java access modifiers; package-private remains protected.
- [ ] Frameworks needing deep reflection have properly scoped `opens`, without opening the entire module unnecessarily.
- [ ] Each package has a clear owner; check for split packages across named modules, automatic modules, and the classpath.
- [ ] Module path is declared separately from classpath; know which dependencies are automatic/unnamed.
- [ ] Tested compiling with `--release 17` and running via the module path on the target JDK.
- [ ] When encountering an error, did you classify **readability**, **exports**, **opens**, **Java modifiers**, or **split package** before fixing?

**Remember:** *Readability* determines which module sees which module; *exports* determines which packages become API for normal Java access; *opens* grants deep reflective access at runtime. Split packages obscure namespace resolution and frequently break module graphs/class loading. Designing each package with a clear owner and declaring `requires`/`exports` accurately is the stable way to use JPMS.

## References

- Java Language Specification 17, Chapter 7, *Packages and Modules*, section `7.7`: https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html
- Java SE 17, package `java.lang.module`, *Resolution and readability graph*, including export conflict conditions: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/package-summary.html
- Java SE 17, `ModuleLayer` — duplicate package/class loader conditions when defining a layer: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- Dev.java, *Strong Encapsulation with --add-exports and --add-opens*: https://dev.java/learn/organizing/modules/add-exports-opens/
- Oracle JDK 17, *The javac Command* — `--module-path`, `--module-source-path`, and `--add-reads`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html