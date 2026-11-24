# Diagnosing Module Readability, Exports, and Opens Errors in Java JPMS

When running a Java application with the **Java Platform Module System (JPMS)**, a class that exists in a JAR and has the `public` modifier can still be inaccessible to another module. A reflection call can fail even though the class loaded successfully, or code may run in the IDE yet throw `IllegalAccessError` when deployed. Three distinct root-cause groups are frequently conflated: **readability** (whether a module can read another), **exports** (access to a package's public API), and **opens** (deep reflective access).

Accurate diagnosis requires knowing **who is performing the access**, **which module owns the target class**, **which package contains the class**, **which permission is missing**, and **whether the check occurs at compile time, link time, or reflection runtime**. Do not apply `--add-opens` JVM-wide as a magic fix for every error: it does not replace module resolution, does not create compile-time dependencies, does not locate missing classes, and weakens encapsulation if opened too broadly.

This article applies to **Java 17+**, featuring a Java 17 example compiled and run in three modes: default, `--add-exports` only, and `--add-opens` only. It also reproduces compile-time `does not read`, `does not export`, and runtime `IllegalAccessError` cases separately, alongside a workflow for inspecting the module graph with JDK tools.

## 1. Three Questions to Ask in Order

Let the module performing the operation be **consumer** `C`, the module containing the target class be **library/provider** `L`, and the package containing the class be `p`.

| Check Layer | Question | Diagnostic API | Typical Declaration / Grant |
| --- | --- | --- | --- |
| **Reads** | Does `C` read `L`? | `C.canRead(L)` | `requires L;` or a validly granted runtime edge |
| **Exports** | Does `L` export package `p` to `C`? | `L.isExported(p, C)` | `exports p;`, `exports p to C;`, or a targeted override |
| **Opens** | Does `L` open package `p` to the module performing reflection? | `L.isOpen(p, caller)` | `opens p;`, `opens p to caller;`, or a targeted override |

**Direction of relationships is the easiest thing to confuse:**

~~~text
module C (consumer/caller)                  module L (library/provider)
      |                                                  |
      +------------------ reads ----------------------->  |
                                                         |
      <------------------- exports p --------------------+
      <-------------------- opens p ---------------------+

C.canRead(L)               // direction C -> L
L.isExported("p", C)        // L's package -> C
L.isOpen("p", C)            // L's package -> C
~~~

Standard access conditions from code in module `C` to a **public type** in package `p` of module `L` include `C` reading `L` and `L` exporting `p` to `C` (plus standard Java visibility rules). For **deep reflection** into private members in package `p`, the package must be appropriately opened to the module actually invoking the reflection API, except in cases where Java permits `setAccessible` without `opens` because access is already valid.

**Note:** `opens` is not the same as `exports` in source semantics, yet **an open package is also treated as exported at runtime** when queried via `Module.isExported`. This is demonstrated in our experimental example: after `--add-opens`, both `isOpen` and `isExported` return `true` for the same target. To know whether a package was exported/opened **in the static descriptor**, inspect `ModuleDescriptor.exports()`/`opens()` rather than inferring from a single runtime check.

## 2. Readability: Does the Consumer Module Actually Read the Target Module?

Example of an application depending on a library's API:

~~~java
module diag.consumer {
    requires diag.library;
}
~~~

When both modules are resolved in a valid configuration, the `requires diag.library;` edge normally establishes that `diag.consumer` **reads** `diag.library`. This is a question about the **module graph**, not whether `diag.library.jar` exists in a folder.

A module may sit on `--module-path` yet **remain unresolved** in the running graph. Conversely, a classloader might locate a class via a special mechanism without compile-time readability declared; never equate class loading with permission to use a public API.

### 2.1. Signs of Missing Readability

If source code in `diag.consumer` writes:

~~~java
import diag.library.api.Greeter;

public final class Probe {
    String text = Greeter.sayHello();
}
~~~

this is an **illustrative snippet**; to compile as a file, it must include a `package` declaration matching its location. When `diag.consumer` omits `requires diag.library;`, the compiler reports something like:

~~~text
package diag.library.api is not visible
(package diag.library.api is declared in module diag.library, but module diag.consumer does not read it)
~~~

The message explicitly states **which module does not read which module**. The proper fix in an explicit module project is adding `requires diag.library;` if the dependency is genuine, rather than opening packages with `opens`.

### 2.2. `requires`, `requires transitive`, and `requires static`

- `requires L;`: the declaring module reads module `L`.
- `requires transitive L;`: in a valid graph, extends readability to modules that depend on the declaring module; useful when a module's public API contract exposes types from another module. Do not use `transitive` indiscriminately to paper over access errors.
- `requires static L;`: requires the dependency at compile time while allowing it to be absent at runtime under an optional-dependency contract; if code actually executes a path needing that class when absent at runtime, it can still fail. Do not treat `requires static` as a way to "auto-discover" modules.
- `--add-reads C=L`: adds a scoped read edge during compilation or JVM launch, typically for diagnostics or migration support. It does not replace a permanent module declaration for static dependencies.

**The first layer to verify** is whether module `L` was resolved properly, and only then ask `C.canRead(L)`. `--add-reads` does not bring a completely absent module into the graph; you may need to adjust root modules or the module path.

## 3. Exports: Reading a Module Does Not Expose All Packages

A module exposes its public API selectively:

~~~java
module diag.library {
    exports diag.library.api;
}
~~~

The descriptor above **does not export** `diag.library.internal`. Even if a class in the internal package has the `public` modifier, another named module cannot access it by default from ordinary compiled code.

| Descriptor Form | Who Can Access Public Types in the Package? |
| --- | --- |
| `exports diag.library.api;` | Modules that read the source module, subject to other rules |
| `exports diag.library.api to diag.consumer;` | Only the listed target modules |
| No `exports` for package | The package is encapsulated against ordinary access from other modules |
| `opens diag.library.internal to diag.consumer;` | The package is open for deep reflection and treated as exported at runtime for the target, though it **cannot** be imported at compile time without extra configuration |

Exporting a package **does not automatically export subpackages**. For instance, `exports diag.library;` does not export `diag.library.internal;`.

A `public` class in an unexported package can still be found by a loader or inspected by name via reflection; the access error may occur **after class lookup**, when using the public type/member or requesting deep reflection. Thus `Class.forName(...)` succeeding does not confirm that ordinary access or `setAccessible(true)` will succeed.

### 3.1. Signs of Missing Exports

With a class `public diag.library.internal.Vault` whose package is not exported in the descriptor, when a consumer attempts to import it:

~~~java
package diag.consumer;

import diag.library.internal.Vault;

public final class CompileProbe {
    public static void main(String[] args) {
        System.out.println(Vault.class.getName());
    }
}
~~~

The Java compiler reports something like:

~~~text
package diag.library.internal is not visible
(package diag.library.internal is declared in module diag.library, which does not export it)
~~~

**This is completely different** from the missing-readability message `does not read`. If the consumer already has `requires diag.library;` and still fails, adding `requires` again will not export the package.

Sustainable fixes: export only **packages that genuinely belong to the public API contract**. If consumer code imports an internal implementation, consider refactoring to an interface/service API instead of exporting the internal package. `--add-exports diag.library/diag.library.internal=diag.consumer` can be used to isolate causes, support controlled migrations, or handle library-owner-approved scenarios; never treat it as a permanent default policy.

## 4. Opens: Deep Reflection Across Module Boundaries

`exports` primarily serves ordinary access to **public APIs**; `opens` allows frameworks to reflect deeply into non-public members within the authorized package.

For example, a framework wants to read a private field:

~~~java
Class<?> type = Class.forName("diag.library.internal.Vault");
var field = type.getDeclaredField("TOKEN");
field.setAccessible(true);
System.out.println(field.get(null));
~~~

This is an illustrative snippet; imports and exception handling are needed in a complete program. If package `diag.library.internal` is not open to the module containing this reflection code, `setAccessible(true)` typically throws `java.lang.reflect.InaccessibleObjectException`. Similarly, `trySetAccessible()` returns `false` instead of throwing when disallowed.

### 4.1. Distinguishing Four Cases

| Goal | Permission Typically Required | Notes |
| --- | --- | --- |
| Call a public member of a public class from compiled code in another module | Reads from consumer and exports from provider | Must also satisfy Java visibility |
| Ordinary reflection on a public member of an exported public class | Appropriate public API export | Does not necessarily require `opens` if access checks are not suppressed |
| `setAccessible(true)` to access a private member from another module | **Opens** package to the module performing reflection | `exports` **alone is insufficient** |
| Host on classpath needing deep reflection into a named module | Opens package to **the unnamed module actually calling reflection** | If using a launcher flag, `ALL-UNNAMED` may be targeted; broad scope requires caution |

**Do not confuse the business caller's module with the reflection framework's module.** If Hibernate/Jackson/a framework runs in its own module and the framework itself calls `setAccessible`, the `opens` target must be the framework's module, not the upper-layer controller module calling the framework.

**Additional precision:** core reflection APIs handle readability according to their own rules (reflective access checks assume readability). Therefore, do not inspect `C.canRead(L)==false` alone and claim that is the sole reason `setAccessible` failed. Read the exception message, identify the module executing reflective access, and check `isOpen`/`isExported` appropriately. For **ordinary bytecode** access, readability remains a separate foundational requirement.

### 4.2. Qualified Opens vs. Opening the Whole Module

~~~java
module diag.library {
    exports diag.library.api;
    opens diag.library.internal to diag.consumer;
}
~~~

The descriptor above opens `diag.library.internal` specifically to `diag.consumer`. There is no need for `open module diag.library { ... }` just so one framework can read one package. `open module` deeply opens every package in the module, weakening encapsulation much more broadly.

## 5. Java 17 Hands-On Lab: Three Access Modes for an Internal Package

Create two **explicit named modules** and the following five files; the example runs end-to-end with JDK 17+. It clearly demonstrates the difference between `reads`, `exports`, and `opens` by observing both the `Module` API and a `Field.setAccessible` call. No external libraries are used.

### 5.1. Directory Structure

~~~text
src/
├── diag.library/
│   ├── module-info.java
│   └── diag/library/
│       ├── api/Greeter.java
│       └── internal/Vault.java
└── diag.consumer/
    ├── module-info.java
    └── diag/consumer/Main.java
~~~

File **`src/diag.library/module-info.java`**:

~~~java
module diag.library {
    exports diag.library.api;
}
~~~

This is the library module with a public API in `diag.library.api` while keeping `diag.library.internal` unexported and unopened.

File **`src/diag.library/diag/library/api/Greeter.java`**:

~~~java
package diag.library.api;

public final class Greeter {
    private Greeter() {}
    public static String sayHello() { return "hello"; }
}
~~~

File **`src/diag.library/diag/library/internal/Vault.java`**:

~~~java
package diag.library.internal;

public final class Vault {
    private static final String TOKEN = "sealed";
}
~~~

`Vault` has the `public` modifier so learners do not confuse the cause with a package-private class; the barrier here is that **the package is neither exported nor open** and the field is private.

File **`src/diag.consumer/module-info.java`**:

~~~java
module diag.consumer {
    requires diag.library;
}
~~~

The consumer already reads the library, allowing the example to isolate **exports/opens** errors from missing **reads**.

File **`src/diag.consumer/diag/consumer/Main.java`**:

~~~java
package diag.consumer;

import diag.library.api.Greeter;
import java.lang.reflect.Field;
import java.lang.reflect.InaccessibleObjectException;

public final class Main {
    public static void main(String[] args) throws Exception {
        Module app = Main.class.getModule();
        Module lib = Greeter.class.getModule();
        System.out.println("reads=" + app.canRead(lib));
        System.out.println("apiExported=" + lib.isExported("diag.library.api", app));
        System.out.println("internalExported=" + lib.isExported("diag.library.internal", app));
        System.out.println("internalOpen=" + lib.isOpen("diag.library.internal", app));
        System.out.println("apiCall=" + Greeter.sayHello());

        Class<?> vault = Class.forName("diag.library.internal.Vault");
        Field token = vault.getDeclaredField("TOKEN");
        try {
            token.setAccessible(true);
            System.out.println("token=" + token.get(null));
        } catch (InaccessibleObjectException expected) {
            System.out.println("privateAccess=denied");
        }
    }
}
~~~

**Explanation of key points:**

- `Main.class.getModule()` retrieves the module performing reflection, avoiding mistakenly picking `Vault`'s module.
- `Greeter.class.getModule()` returns the module containing the public API class; here it is the same module containing `Vault`.
- `canRead` measures consumer → provider; `isExported`/`isOpen` measure provider package → consumer.
- `Greeter.sayHello()` is permitted by the compiler because of `requires` + `exports diag.library.api;`.
- `Class.forName` only obtains the class object; it does not prove permission to break encapsulation on a private field.
- `getDeclaredField("TOKEN")` can locate the private field, while `setAccessible(true)` is the step that tests deep reflection permission.
- Catching only `InaccessibleObjectException` makes the output deterministic for missing `opens`; other exceptions can still surface so other configuration errors are not masked.

### 5.2. Compilation

From the directory containing `src/`:

~~~bash
javac --release 17 --module-source-path src -d mods -m diag.library,diag.consumer
~~~

`--module-source-path src` maps module-named folders to the source tree, and `-d mods` holds per-module output. `--release 17` checks Java 17 compatibility even when the actual compiler is newer. This example was compiled and run using Amazon Corretto JDK 17.

### 5.3. Default Run: Reads Present, API Exported, Internals Closed

~~~bash
java --module-path mods -m diag.consumer/diag.consumer.Main
~~~

**Exact** stdout:

~~~text
reads=true
apiExported=true
internalExported=false
internalOpen=false
apiCall=hello
privateAccess=denied
~~~

From this output:

1. `reads=true` confirms `requires diag.library;` established readability.
2. `apiExported=true` confirms the public API package is accessible.
3. `internalExported=false` and `internalOpen=false`: the internal package has not granted access to the consumer.
4. The public API call succeeds (`hello`); only deep reflection into `TOKEN` is blocked.
5. `Class.forName` returning `Class<?>` is not sufficient proof of permission to access private members.

### 5.4. Granting `--add-exports` Only: Still Cannot Read the Private Field

~~~bash
java --module-path mods --add-exports diag.library/diag.library.internal=diag.consumer -m diag.consumer/diag.consumer.Main
~~~

**Exact** stdout:

~~~text
reads=true
apiExported=true
internalExported=true
internalOpen=false
apiCall=hello
privateAccess=denied
~~~

`--add-exports` changes access to the package's public API **for that specific target module**, yet **does not** allow deep reflection into private members. Hence `setAccessible(true)` continues to fail. This is a useful troubleshooting test: if a framework simply lacks `opens`, adding `exports` will not fix the core issue.

### 5.5. Granting `--add-opens` Only: Deep Reflection Succeeds

~~~bash
java --module-path mods --add-opens diag.library/diag.library.internal=diag.consumer -m diag.consumer/diag.consumer.Main
~~~

**Exact** stdout:

~~~text
reads=true
apiExported=true
internalExported=true
internalOpen=true
apiCall=hello
token=sealed
~~~

Two important findings:

- `internalOpen=true` and `token=sealed` confirm the package was opened to **the exact module calling reflection**; the private field is accessed.
- **`internalExported=true` even though only `--add-opens` was added**. The JDK treats open packages as exported in runtime access checks; do not infer from `isExported(true)` that the original descriptor had an `exports` clause.

**All three commands were compiled/run and verified against actual JDK 17 stdout.** These results are deterministic for the article's modules and code, independent of plugin count or external provider discovery order.

## 6. Reproducing Compilation Errors: Missing Reads and Missing Exports

This section describes **intentionally broken variants to observe diagnostics**—do not add them to the working demo simultaneously. Keep the section 5 code as a baseline; edit each case separately and then revert.

### 6.1. Case A — Consumer Module Does Not Read Library

Temporarily change `src/diag.consumer/module-info.java` to:

~~~java
module diag.consumer { }
~~~

Keep `Main.java` importing `diag.library.api.Greeter` and recompile:

~~~bash
javac --release 17 --module-source-path src -d mods -m diag.library,diag.consumer
~~~

The compiler rejects it because `diag.consumer` **does not read** `diag.library`. The core diagnostic reproduced in a separate fixture:

~~~text
package diag.library.api is not visible
(package diag.library.api is declared in module diag.library, but module diag.consumer does not read it)
~~~

**Proper fix:** add `requires diag.library;` back to the consumer's descriptor. `--add-opens` on the API package will not directly replace a missing compile-time readability edge. Once `requires` is in place, diagnose package exports next if needed.

### 6.2. Case B — Consumer Reads Library but Tries to Import Internal Package

Restore `module diag.consumer { requires diag.library; }`. Suppose we add **`src/diag.consumer/diag/consumer/CompileProbe.java`**:

~~~java
package diag.consumer;

import diag.library.internal.Vault;

public final class CompileProbe {
    public static void main(String[] args) {
        System.out.println(Vault.class.getName());
    }
}
~~~

Rerun the `javac` command from section 6.1. Because `diag.library.internal` is not exported, the compiler rejects it. Reproduced core diagnostic:

~~~text
package diag.library.internal is not visible
(package diag.library.internal is declared in module diag.library, which does not export it)
~~~

Here **readability is already valid**; the error is that the package is not exported. Three options to consider: stop using the internal type and move to an exported API (preferred), update the library descriptor if the package is genuinely a public contract, or grant a targeted `--add-exports` when you understand and accept internal coupling.

### 6.3. Case C — Compile-Time Permission Exists, Runtime Permission Missing

If compiled with a targeted override, for example:

~~~bash
javac --release 17 --module-path mods --module-source-path src --add-exports diag.library/diag.library.internal=diag.consumer -d out -m diag.consumer
~~~

then the compiler allows `CompileProbe` to link against `Vault`. However, if the **runtime** lacks the corresponding export in the module graph, the JVM can throw:

~~~text
java.lang.IllegalAccessError: class diag.consumer.CompileProbe (in module diag.consumer) cannot access class diag.library.internal.Vault (in module diag.library) because module diag.library does not export diag.library.internal to module diag.consumer
~~~

The line above shows the **error pattern**; exact class names depend on the variant. In a separate test fixture, the corresponding `IllegalAccessError` was observed, and adding `--add-exports diag.library/diag.library.internal=diag.consumer` to the JVM allowed the code accessing the public class to run.

Lesson: **compiler flags and JVM launcher flags belong to two separate phases**. Passing an override to one `javac` invocation does not bake that permission into `module-info.class` or guarantee the production JVM grants the same access. In particular, avoid using temporary overrides to encode long-term dependencies on internal APIs.

### 6.4. Do Not Guess from the Single Word "Inaccessible"

- **`does not read`** → investigate `reads` edges and module resolution.
- **`does not export`** → investigate package `exports` toward the target.
- **`does not open`** in `InaccessibleObjectException` → investigate deep reflection/`opens` toward the module performing reflection.
- **`ClassNotFoundException`** → investigate loader/module path; do not immediately jump to `opens`.
- **`IllegalAccessError`** → investigate runtime access checks in bytecode/linkage, which can differ from compile-time permissions.

Read the entire message—especially **source module**, **target module**, **package**, and class names—instead of spotting one keyword and adding a flag.

## 7. JDK Tools for Evidence-Based Investigation

### 7.1. First Identify the JDK and Launch Mode

~~~bash
java -version
javac -version
java --list-modules
~~~

Verify the Java actually used by the launcher/deployment, not just the Java SDK shown in the IDE. In multi-JDK environments, `javac` and `java` can belong to two different versions. With custom runtime images (`jlink`), the module list may be smaller than a full JDK.

Determine whether the process actually runs with `--class-path` or `--module-path`, which class is the main class, what the root module name is, and how launcher flags were applied.

### 7.2. Inspect the Descriptor of a Discovered Module

In the section 5 project, the command:

~~~bash
java --module-path mods --describe-module diag.library
~~~

shows module `diag.library`, its exported packages, and internal-only packages. The tested run produced meaningful lines including:

~~~text
exports diag.library.api
requires java.base mandated
contains diag.library.internal
~~~

Module paths in the output are machine-dependent and therefore not fixed here. If `diag.library` is packaged as a JAR, `jar --describe-module --file path/to/diag.library.jar` inspects the descriptor of the exact distributed JAR file.

**Watch out for artifact versions:** IDE build output, repository JARs, and production JARs can differ. Inspect the **exact file/runtime actually in use** rather than reading an unbuilt `module-info.java` and assuming the graph matches it.

### 7.3. Observe Startup Module Resolution

~~~bash
java --module-path mods --show-module-resolution -m diag.consumer/diag.consumer.Main
~~~

The JDK prints the resolved graph before running the program. In this article's fixture, the relationship appears as:

~~~text
diag.consumer requires diag.library
~~~

Full output may contain many system modules and `binds` lines depending on the JDK and environment. **Do not match the entire stdout verbatim** as a brittle test; extract only the root modules, dependency edges, and provider bindings actually needed for diagnosis.

If `diag.library` is absent from the resolved graph, inspect `--module-path` and root modules. A JAR sitting in the module-path directory yet left unresolved **is not enough** for `--add-opens` to take effect on the intended target module.

### 7.4. Use `jdeps` for Static Dependency Analysis

~~~bash
jdeps --module-path mods --check diag.consumer
~~~

On the tested fixture, `jdeps` shows `diag.consumer`'s descriptor has `requires diag.library;` and the implicit dependency on `java.base`. `jdeps` helps detect unnecessary dependencies, accesses to internal JDK APIs, and potential issues before runtime.

**Limitation:** static dependency analysis does not see every string-based `Class.forName`/reflection call, dynamically loaded provider, or dynamically created module layer. Therefore, `jdeps` reporting a valid graph **does not** mean the application cannot hit `InaccessibleObjectException` when frameworks run.

### 7.5. JVM Module Logging (When Needed)

The JDK supports Unified Logging; it can be enabled depending on configuration:

~~~bash
java -Xlog:module=debug --module-path mods -m diag.consumer/diag.consumer.Main
~~~

This is a **supplementary diagnostic command**, not a default option for every production run. Output can be verbose and varies across JDK builds; enable it only in controlled environments with size and duration limits. Never build business logic by parsing exact debug-log phrasing.

### 7.6. Recording Runtime Module Identity in Code

Place the snippet below inside a method that has references to the target and caller classes:

~~~java
Module caller = Main.class.getModule();
Module target = Greeter.class.getModule();

System.out.println(caller.getName());
System.out.println(target.getName());
System.out.println(caller.canRead(target));
System.out.println(target.isExported("diag.library.api", caller));
System.out.println(target.isOpen("diag.library.internal", caller));
~~~

This is a **snippet depending on the example classes**, not a standalone source file. When diagnosing plugins, also log `caller.getLayer()`, `target.getLayer()`, both classes' class loaders, package name, and the failing method/field name. Two modules sharing the same name in **two different layers/loaders** are not necessarily the same `Module` object; obtain `Module` from the **actual `Class<?>` being used**.

## 8. Isolating Each Exception Type

| Exception / Diagnostic | Typical Phase | Evidence to Collect | Fix Priority |
| --- | --- | --- | --- |
| `error: module not found: X` | Compile / module-graph resolution | `--module-path`, module name, artifact, `requires X` | Fix artifact/path/module name/roots |
| `FindException` or `ResolutionException` | Configuration / boot-layer resolution | Root modules, descriptors, version constraints, cyclic/conflicting packages | Fix module graph/packaging |
| `package ... is not visible: does not read` | Compile time | Consumer descriptor and discovered target module | Add `requires` or proper dependency model |
| `package ... is not visible: does not export` | Compile time | Provider `exports`/qualified targets | Export required API or stop using internal package |
| `IllegalAccessError` | Runtime bytecode linkage/access | Actual module pair and compile/runtime flags | Align permissions or fix descriptor/API |
| `IllegalAccessException` | Java reflection checks | Member modifier, class visibility, export/open, caller module | Appropriate reflective access or use public API |
| `InaccessibleObjectException` | `setAccessible` cannot open access | Package, reflection target module, `isOpen` | Targeted qualified `opens`; avoid broad opens |
| `ClassNotFoundException` | Name-based class loading | Loader, classpath/module path, actual package/module | Fix loading/distribution |
| `NoClassDefFoundError` | Using a compiled class missing at runtime/linking | Dependencies, cause chain, classloader identity | Fix artifact/module resolution/dependency |
| `ServiceConfigurationError` | Discovering/instantiating service provider | `uses`, `provides`, `META-INF/services`, constructor/factory, dependencies | Fix SPI/provider config before touching exports/opens |
| `InvocationTargetException` | Reflective invocation | `getCause()` is the exception from the invoked method | Diagnose method business error once access succeeded |

**Not every error mentioning "module" is an access-policy failure.** `FindException` can occur before any class loads; `NoClassDefFoundError` can come from a missing JAR or failed class initialization. Opening a package does not conjure up missing bytecode.

### 8.1. `IllegalAccessError` vs. `IllegalAccessException`

- `IllegalAccessError` is a **`LinkageError`** thrown at the JVM level when an instruction/linkage lacks access permission, typically after bytecode was compiled under different conditions than runtime.
- `IllegalAccessException` is a checked exception thrown by reflection APIs when Java/JPMS access checks fail.
- `InaccessibleObjectException` is a runtime exception commonly thrown by `setAccessible(true)` when a package is not open to suppress access checks.

Trying to catch `IllegalAccessException` will not catch `IllegalAccessError`. The operational fix is to **repair the graph/packaging**, not catch `Throwable` to hide JDK access denials.

### 8.2. Identifying Which Module Actually Calls Reflection

Suppose application `business.app` calls framework library `example.mapper`, which in turn calls `setAccessible(true)` on an entity in module `domain.model`:

~~~text
business.app  ---> example.mapper ---> reflection on domain.model/privateField
                       |
                       +-- module calling setAccessible()
domain.model ------------------------ opens p to example.mapper
~~~

Typically, package `p` must be opened **to `example.mapper`**, not simply to `business.app`. If the framework sits on the classpath, the target may be an unnamed module; when using launcher `--add-opens domain.model/p=ALL-UNNAMED`, understand its scope covers **all unnamed modules** in the process, not just that library.

Use `SomeFrameworkClass.class.getModule()` (when available) or the stack trace to pinpoint the true caller. Do not treat a JAR file name as automatically equal to a JPMS module name.

## 9. Runtime Overrides: Treating Symptoms vs. Resolving Contracts

Java provides several ways to relax module relationships. Understand their direction, application phase, and scope.

| Mechanism | Permission Added | When Useful |
| --- | --- | --- |
| `requires L;` | Intentional read edge in consumer's descriptor | Permanent static dependency |
| `exports p;` / `exports p to C;` | Public API package in provider | Clear compile-time contract |
| `opens p;` / `opens p to F;` | Deep reflection permission from provider to framework | Legitimate framework needing non-public fields/constructors |
| `--add-reads C=L` | Adds `reads` at the relevant tool/launcher stage | Debugging/migration, dependency outside descriptor |
| `--add-exports L/p=C` | Adds package export from provider to target | Debugging an internal API or selective compatibility config |
| `--add-opens L/p=F` | Adds package `opens` for reflection caller | Debugging reflection or intentional framework access |
| `Module.addReads/addExports/addOpens` | Module adjusts its own permissions subject to caller restrictions | Code already privileged within the source module |
| `ModuleLayer.Controller` | Host controller adjusts **source modules in the layer it manages** | Plugin/runtime systems creating new module layers |

### 9.1. Do Not Apply All Flags at Once During Diagnosis

If on your first attempt you add `--add-reads`, `--add-exports`, and `--add-opens` for every package, the application may start working while **destroying evidence of the root cause**. Test minimally in sequence: verify module resolved → reads → exports → reflection opens. Change only **one targeted permission** at a time, recording changes in `canRead`/`isExported`/`isOpen` and the resulting exception.

### 9.2. Compile-Time and Runtime Are Not the Same Configuration

For example, `javac --add-exports` can allow importing an internal type, while running `java` without that flag will still fail at runtime. Inspect **both actual command lines** and the compiled `module-info.class`; IDE test runners may also inject flags absent from production artifacts.

Conversely, adding `--add-exports` only at runtime cannot rescue source code previously rejected by `javac`. A JVM flag does not retroactively alter an earlier compilation.

### 9.3. Prefer Fixing the Contract Source When You Own It

- If `requires` is genuinely missing, add it to the consumer module descriptor.
- If a package is intended public API, export that package properly (prefer qualified exports if only one consumer needs it).
- If a framework legitimately needs deep access, open the package **to that specific framework module**.
- If a package is private implementation detail, refactor the architecture so consumers do not depend on it.
- If the error is simply an unresolved module or a classloader missing a JAR, fix packaging/resolution—do not tweak access flags.
- If a platform/library prevents editing its descriptor, document the targeted override as a **managed exception**, pin versions, and regression-test on JDK upgrades.

Never fix errors with `open module` across a whole library or `ALL-UNNAMED` across all packages simply because you have not identified which caller needs access. That creates coupling and excessive deep-reflection exposure.

## 10. JPMS in Plugin Systems, ModuleLayer, and Multiple Class Loaders

In hosts that load plugins into separate layers, the three access checks gain a **module identity** dimension:

~~~text
boot layer (host)
       |
       +--- child ModuleLayer (plugin generation V1)
       |         diag.library  (ClassLoader A)
       |         diag.consumer (ClassLoader B)
       |
       +--- child ModuleLayer (plugin generation V2)
                 diag.library  (ClassLoader C)
                 diag.consumer (ClassLoader D)
~~~

Identical module names do not mean `Module`, `Class<?>`, or class loader objects are identical between V1 and V2. If the host checks `canRead` on a module obtained from V1 while the failing class belongs to V2, diagnostic output can be misleading.

### 10.1. What Evidence Should Be Recorded?

In a real failure, collect:

1. `Class<?>` of **the actual consumer** and **the actual target class**.
2. `Class.getModule()`, `Module.getName()`, `Module.getLayer()`, and `Class.getClassLoader()` for each.
3. Exact package accessed, public/private modifiers, and bytecode vs. reflection access type.
4. `canRead` in consumer → target direction, and `isExported`/`isOpen` in provider → caller direction.
5. Module resolution roots, provider layer configuration, parent layers, and plugin JAR locations.
6. Runtime access overrides applied to **that specific generation**.
7. If a stack trace exists, which frame actually invoked `setAccessible` or reflective invocation.

### 10.2. `ModuleLayer.Controller` Cannot Modify Arbitrary Modules

`ModuleLayer.Controller.addReads(source, target)`, `addExports(source, p, target)`, and `addOpens(source, p, target)` have a critical restriction: **`source` must belong to the layer created/managed by that controller**. A child layer's controller cannot modify a source module like `java.base` in the boot layer. `target` may be a module in another layer per the API contract, which still grants no permission to mutate `target`.

Nor can a controller create missing modules/classes, recompile code, or alter static `ModuleDescriptor`s. It adds dynamic edges **with no corresponding direct revocation API**. When handling access issues in plugins, respect security boundaries and ensure only the trusted host holds the controller.

### 10.3. Do Not Confuse `ClassCastException` with Exports Errors

Two classes with the same binary name but different defining loaders can be type-incompatible. A `ClassCastException` involving the same class name from two loaders cannot be solved with `--add-exports`/`--add-opens`. SPI/DTO contracts between host and plugins must be defined in a shared API module/classloader; this is a **runtime type identity** issue, not a package access issue.

Similarly, if a consumer using `ServiceLoader` finds no providers, first check `uses`/`provides` or `META-INF/services`, module resolution, and the right loader/layer. Only investigate `exports`/`opens` if the stack trace actually shows a provider unable to access an API or framework reflection being blocked.

## 11. Common Misconceptions That Lead to Wrong Fixes

**Misconception 1: "A public class is accessible from any module."** False; the `public` modifier does not cross unexported package boundaries in a named module.

**Misconception 2: "Once a module is `requires`'d, all its packages can be imported."** False; `requires` establishes readability, not exporting every internal package of the target module.

**Misconception 3: "`--add-exports` fixes every `InaccessibleObjectException`."** False; deep reflection into private members usually requires `opens`. The three modes in section 5 demonstrate this directly.

**Misconception 4: "`--add-opens` does not affect `isExported`."** False at runtime. An open package is treated as exported to the target when queried via `Module.isExported`; inspect the descriptor to distinguish static declarations.

**Misconception 5: "`Class.forName` succeeding means private fields are accessible."** False; class loading and Java access checks are independent stages.

**Misconception 6: "Putting a JAR on the module path means the module is resolved."** Not necessarily; the resolved graph depends on roots, `requires`, and service binding/configuration.

**Misconception 7: "Adding `--add-opens` at runtime fixes `javac` errors."** False. The compile-time checker runs beforehand and requires appropriate descriptors or compile flags.

**Misconception 8: "Modules with the same name must be the same module."** False across different layers/loaders. Always inspect the actual `Module` instance.

**Misconception 9: "Once `jdeps` passes, reflection will definitely work."** False. `jdeps` analyzes static dependencies and cannot see all dynamically constructed class names.

**Misconception 10: "Adding `ALL-UNNAMED` is always harmless."** False; it can expose internals to many classpath libraries, increasing internal coupling and reflection surface area.

## 12. Step-by-Step Diagnostic Workflow

~~~text
Error using a module's class/member?
                    |
                    v
Does the module/class actually exist at runtime?
                    |
       +------------+----------------+
       | no                          | yes
       v                             v
fix path, roots, loader       Is it ordinary compiled access?
       |                             |
       |                      +------+------+
       |                      | yes         | reflection
       |                      v             v
       |                 C.canRead(L)?    Identify module calling
       |                      |           setAccessible/invoke
       |                 missing reads?      |
       |                      |             v
       |                      v        Does it need deep access?
       |                 fix requires        |
       |                      |         +---+---+
       |                      v         | no  | yes
       |                 L exports p?   v       v
       |                      |       check     L opens p to
       |                 missing export? public   caller?
       |                      |       visibility |
       |                      v                  v
       |                 export API /         qualified opens
       |                 stop using internals    |
       +------------------------------+-----------+
                                      |
                                      v
                        Rerun exact build and runtime
                                      |
                                      v
                        Check remaining exceptions/causes
~~~

During this process, every step must have **evidence**. Record it in a form like:

~~~text
consumer module = diag.consumer
library module  = diag.library
package         = diag.library.internal
operation       = Field.setAccessible(true)
canRead         = true
isExported      = false
isOpen          = false
exception       = InaccessibleObjectException
minimal trial   = --add-opens diag.library/diag.library.internal=diag.consumer
result          = reflection works
~~~

On the exact demo fixture from section 5, this table isolates the missing `opens` cause without replacing libraries or moving the entire JVM into the unnamed module.

### 12.1. When to Fix Immediately vs. When to Profile Further?

If the failure is a clear permission error from `IllegalAccessError`/`InaccessibleObjectException`, profiling CPU or heap usually **will not help**; fix the configuration/module graph. If the system is merely slow at startup due to module discovery, class loading, or reflection, measure with JFR or a suitable profiler and compare startup traces before optimizing. Never treat `--add-opens` or `--add-exports` as "performance optimizations": they are **access permissions**, not speedups.

Repeating `Class.forName`/reflection scans frequently can create framework overhead; cache metadata per **exact classloader/layer generation** where appropriate while ensuring caches do not retain old plugin classloaders forever. Never cache a `Class<?>` from generation V1 and use it to check permissions for V2.

## 13. Regression Testing and Protecting Encapsulation

Every deployed module graph/module layer should have at minimum:

| Test Group | Test Case | What to Verify |
| --- | --- | --- |
| Module resolution | Remove `diag.library` from module path | Build/boot reports missing module instead of obscure business errors |
| Reads | Remove `requires diag.library` | Compiler reports module does not read target |
| Qualified exports | Code imports internal package | Compiler rejects if package is unexported |
| Public API | `Greeter.sayHello()` | Works with proper `requires` + `exports` |
| Default deep reflection | Private field in unopened package | Denied as expected |
| Add exports only | `--add-exports` for exact package/target | Public access opened, yet private reflection still denied |
| Add opens only | `--add-opens` for exact package/target | `isOpen` is true and private reflection succeeds |
| Compile/runtime mismatch | Compile with export override, run without it | Triggers `IllegalAccessError`; test ensures final packaging does not drift |
| Caller identity | Framework module differs from host business module | `opens` must target the module calling reflection |
| Multi-layer | Two generations with same module name, different loaders | Debug against exact module identity without mixing V1/V2 |
| Security | Only exact package/target granted `opens` | No accidental broadening via `ALL-UNNAMED` |
| Deployment | JVM, module flags, app server, container differ from IDE | Record actual module graph/flags and run smoke tests |

In particular, include a **test running the real production artifact**, not only IDE unit tests. Maven Surefire, Gradle test runners, or IDEs may run on the classpath and inject `--add-opens` automatically; when running the application on the real module path, access checks differ. Use test configurations that mirror the deployment launcher.

### 13.1. Bug Report Information Checklist

An effective bug report should attach:

- **JDK/JRE versions** of the failing process and build tool.
- **Exact module names**, failing package and class, and source/target modules.
- An intact **stack trace excerpt**, especially `module ... does not export/open ... to ...`.
- **`module-info.java`** of producer and consumer, omitting unrelated files.
- Runtime **module path/classpath**, `--add-modules`/`--add-reads`/`--add-exports`/`--add-opens`.
- Compact outputs of `--describe-module`, `--show-module-resolution`, `jdeps`/runtime access queries.
- If using plugins, **ModuleLayer**, ClassLoader, plugin generation, and how the host builds layers.
- A controlled test with one targeted override, showing before/after results.
- Intended long-term fix: update descriptor, change API, or keep a justified compatibility flag.

Never log secrets, stack variables containing PII, or sensitive payloads while gathering this evidence.

## 14. Summary Decision Table

| Verified Symptom | Permission / Condition to Check First | Do Not Mis-Fix With |
| --- | --- | --- |
| `module not found` | Resolution / module path / roots | `--add-opens` |
| `consumer does not read library` | `requires` or targeted `--add-reads` | `--add-exports` alone |
| `library does not export package` when importing public class | `exports` or targeted `--add-exports` | Adding `requires` alone |
| `setAccessible` reports package not open | `opens` for exact caller or targeted `--add-opens` | `--add-exports` alone |
| Compile succeeds, runtime throws `IllegalAccessError` | Compare compile flags and runtime graph | Catching exception and continuing |
| `Class.forName` cannot find class | Loader / module resolution / artifact | `--add-opens` |
| `ClassCastException` between same class name, different loaders | Runtime class identity and shared API | `--add-exports` |
| `jdeps` passes, yet runtime reflection fails | Caller module, package `opens`, and reflection code | Assuming `jdeps` covers dynamic names |

**Conclusion:** JPMS enforces multiple distinct permission layers, and diagnosis is only reliable when measured on **the actual `Module` objects in the actual runtime**. Check *consumer reads provider*, then *provider exports package to consumer*, then *provider opens package to reflection caller*; cross-check source descriptors against runtime overrides, the module graph, and stack traces. Grant **least privilege**, fix the exact failing layer, and retest in the real deployment environment.

### Java SE 17 References

- [Java Platform Module System – JLS `7.7](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7): `requires`, `exports`, `opens`, and module declarations.
- [Java SE 17 – Class `Module`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): `canRead`, `isExported`, `isOpen`, and runtime access.
- [Java SE 17 – `AccessibleObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `setAccessible` rules, readability, and reflection across modules.
- [Java SE 17 – `InaccessibleObjectException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html): error when access checks cannot be suppressed.
- [Java SE 17 – `ModuleLayer.Controller`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.Controller.html): limits of `addReads`/`addExports`/`addOpens` in child layers.
- [Java 17 `java` launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `--module-path`, `--show-module-resolution`, `--add-reads`, `--add-exports`, `--add-opens`.
- [Java 17 `javac`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): compile options, module-source-path, and diagnostics.
- [Java 17 `jdeps`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html): module dependency analysis and `--check`.
