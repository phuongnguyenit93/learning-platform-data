# When to Use --add-modules, --add-reads, and --add-exports in Java

When working with the Java Platform Module System (JPMS, since Java 9), having a class present on the machine is **not enough** for another class to use it. The module containing that class must be placed into the **resolved module graph**; the calling module must **read** the module containing the class; and the package containing the needed type must be **exported** to the calling module. The three flags `--add-modules`, `--add-reads`, and `--add-exports` solve **three different problems**.

This lesson explains exactly when to use each flag on `javac` and `java` commands, how to inspect common errors, and why a compile-time-only fix can still fail at runtime. The minimal examples use Java 17+ syntax and are designed so you can create the files, compile, and run standalone. The shell commands in the examples use **Bash on Linux/macOS** from the project directory; Windows PowerShell needs equivalent commands to create directories and the proper path separator when lists contain multiple entries.

## 1. Three Conditions to Use a Type from Another Named Module

Imagine the program in `demo.app` wants to use the public class `Library` in package `demo.lib.internal` of module `demo.lib`:

~~~text
Observable modules (JDK image, module path)
                    │
                    ▼
        Module resolution (root + requires)
                    │
          Is demo.lib resolved?
                    │
          ┌─────────┴──────────┐
          │                    │
         No                   Yes
          │                    │
     --add-modules            ▼
                     Does demo.app read demo.lib?
                                │
                      ┌─────────┴────────┐
                      │                  │
                      No                Yes
                      │                  │
                  --add-reads            ▼
                                 Package exported
                                 to demo.app?
                                        │
                              ┌─────────┴─────────┐
                              │                   │
                              No                 Yes
                              │                   │
                         --add-exports       Continue checking
                                             public/access
~~~

This is a diagram for diagnostic thinking, **not a recipe requiring you to add all three flags**. Normally `module-info.java` already declares `requires` and `exports` properly so **no flags are needed**. Not every error calls for exactly one flag: a missing dependency on the module path, a package/private member, or a split package each have their own causes.

Foundational concepts:

- **Observable module:** a module that the compiler or launcher can discover from the JDK image/module path; *observable* does not automatically mean *resolved*.
- **Root module:** the starting point of the resolution algorithm; the `requires` set of the roots and subsequent dependencies determine which modules enter the graph.
- **Readability edge:** a directed relation `A → B` allowing module `A` to read types that `B` exports to `A`.
- **Exports:** module `B` exposes a package to all modules (unqualified export) or to a selected set of modules (qualified export). `public` on a class is still insufficient if the package is not exported.
- **Unnamed module:** code on the classpath belongs to the unnamed module, which has no name to use in a named target position; the special token `ALL-UNNAMED` is used in certain options.

In standard named modules, `requires demo.lib;` in `demo.app/module-info.java` normally both resolves `demo.lib` as a dependency and creates a readability edge. If `demo.lib` already `exports demo.lib.api;`, `demo.app` code can use public types in `demo.lib.api` without modifying the command line.

## 2. Quick Decision Table

| Flag | What does it change? | When is it useful? | What can the flag not do? |
| --- | --- | --- | --- |
| `--add-modules M` | Adds `M` to the root modules to resolve | Classpath code needs a module on the module path; optional module not yet resolved; tools/test harnesses | Does not grant `exports` to internal packages; does not create `A reads B` edges for every named module |
| `--add-reads A=B` | Adds readability edge `A → B` | Named module `A` temporarily needs an API whose descriptor lacks `requires B`; tests and migration | Does not export `B`'s packages; does not substitute for a missing dependency/JAR |
| `--add-exports B/p=A` | Makes `B` export package `p` to `A` at compile/runtime per the command | White-box tests, legacy tools needing public types in unexported packages | Does not grant access to `private` members; does not enable deep reflection; does not add `requires` |
| `--add-opens B/p=A` | Opens package for deep reflection at runtime | Reflection frameworks needing access to non-public members | Not a general solution for importing unexported types in Java source code |

Read **the name on the left side of `=`** very carefully:

- `--add-reads A=B`: **A reads B**; the direction is from consumer to provider.
- `--add-exports B/p=A`: **B exports p to A**; the direction is from provider to consumer.
- `--add-modules B`: **B is added as a root to resolve**, with no package name or target consumer.

A module can be present and read, yet an internal package remains inaccessible. Conversely, a package may be exported to `A` while `A` does not yet read the owning module, leaving accessibility incomplete. That is why the flags should not be treated as interchangeable "unlock levels."

## 3. Exact Syntax of the Three Flags

### 3.1. --add-modules

~~~text
--add-modules module1,module2
--add-modules=module1,module2
--add-modules ALL-MODULE-PATH
~~~

The module name list uses **commas**, not the classpath separator. `ALL-MODULE-PATH` means adding all modules on the module path as roots. In the `java` launcher there are also special values `ALL-DEFAULT` and `ALL-SYSTEM` for specialized launch/test situations. Avoid using `ALL-SYSTEM` routinely because it expands the graph far beyond what is needed; and do not assume every launcher special value has the same semantics/availability when using `javac`.

### 3.2. --add-reads

~~~text
--add-reads consumer.module=provider.module
--add-reads=consumer.module=provider.module
--add-reads consumer.module=first.module,second.module
--add-reads consumer.module=ALL-UNNAMED
~~~

`consumer.module` is the module needing an added read edge. The list on the right holds target modules. `ALL-UNNAMED` lets a named module read code in unnamed modules, often used in testing/migration while libraries remain on the classpath.

### 3.3. --add-exports

~~~text
--add-exports provider.module/provider.pkg=consumer.module
--add-exports=provider.module/provider.pkg=consumer.module
--add-exports provider.module/provider.pkg=first.module,second.module
--add-exports provider.module/provider.pkg=ALL-UNNAMED
~~~

`provider.pkg` is a **package** inside `provider.module`, not a class. Use `/` between the module name and package name; do not put a class name after `/`. `ALL-UNNAMED` allows **all unnamed modules** to see public types in the exported package, provided other accessibility conditions are met.

All three flags must be placed **before the main class name or `-m` along with appropriate launch arguments** when using `java`. They are **tool options**, not `String[] args` parameters passed to `main`. `javac` commands likewise place flags alongside source/module paths and the output directory per tool syntax.

## 4. --add-modules: Module Is Present Yet Not in the Graph

Common scenario: a **classpath** application uses a **named module** on the module path. Placing a JAR or module directory on `--module-path` only makes it *observable*; for an application run via the classpath, modules on the module path are normally **not yet roots**, so `--add-modules` is needed.

### Complete example: a library module and a classpath application

Create the structure:

~~~text
project/
├── src/
│   ├── library/
│   │   ├── module-info.java
│   │   └── demo/greet/api/Greeter.java
│   └── classic/
│       └── Main.java
├── mods/               (generated at build time)
└── out/                (generated at build time)
~~~

**`src/library/module-info.java`**

~~~java
module demo.greeter {
    exports demo.greet.api;
}
~~~

**`src/library/demo/greet/api/Greeter.java`**

~~~java
package demo.greet.api;

public final class Greeter {
    private Greeter() {
    }

    public static String message() {
        return "Hello from module";
    }
}
~~~

**`src/classic/Main.java`**

~~~java
import demo.greet.api.Greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.message());
    }
}
~~~

From the `project` directory, Bash commands:

~~~bash
mkdir -p mods/demo.greeter out
javac -d mods/demo.greeter src/library/module-info.java src/library/demo/greet/api/Greeter.java
javac --module-path mods --add-modules demo.greeter -d out src/classic/Main.java
java --module-path mods --add-modules demo.greeter -cp out Main
~~~

Stdout from the final run command:

~~~text
Hello from module
~~~

Why do the commands work?

1. `javac -d mods/demo.greeter ...` generates class files for named module `demo.greeter`; the module descriptor is placed at the module's output root.
2. `--module-path mods` makes module `demo.greeter` *observable* to the compiler and runtime invocations.
3. `--add-modules demo.greeter` adds this module to the graph. Because `Main` is **unnamed module** code, it reads resolved named modules and can use public classes in the unrestrictedly exported package `demo.greet.api`.
4. The flag is present on **both the `javac` and `java` invocations** so the compiler can resolve the type and the runtime has the matching graph.

If you provide `--module-path mods` yet omit `--add-modules demo.greeter`, `Main` normally does not see that custom module in the graph during compilation; at runtime a class-loading error may also occur. Diagnostic messages differ by context, yet the cause is **the module is not yet resolved**, not a missing `public`.

### When --add-modules may not be needed

If `Main` resides in named module `demo.app` having `requires demo.greeter;`, resolution from root `demo.app` will normally bring `demo.greeter` into the graph automatically. In that case adding `--add-modules demo.greeter` usually solves nothing new.

The best choice is declaring permanent dependencies with `requires` in `module-info.java` rather than using temporary flags. Only use `--add-modules` intentionally when you want to add extra roots to the graph that descriptors or default launch mode do not already include.

## 5. --add-reads: A Module Needs to Read Another Module Without requires in Its Descriptor

With named modules, the compiler checks readability. A module `A` does not automatically read every other module just because they are all on the module path. `--add-reads A=B` adds edge `A → B` in the module graph during compilation or execution depending on where the flag is used.

### Complete example with the java.sql module

This example avoids external library dependencies, using the standard `java.sql` module and an application named module that does not declare `requires java.sql`.

Structure:

~~~text
project/
└── src/
    └── read/
        ├── module-info.java
        └── demo/read/Main.java
~~~

**`src/read/module-info.java`**

~~~java
module demo.read {
}
~~~

**`src/read/demo/read/Main.java`**

~~~java
package demo.read;

import java.sql.DriverManager;

public class Main {
    public static void main(String[] args) {
        System.out.println(DriverManager.class.getModule().getName());
    }
}
~~~

Bash commands:

~~~bash
mkdir -p mods/demo.read
javac --add-modules java.sql --add-reads demo.read=java.sql -d mods/demo.read src/read/module-info.java src/read/demo/read/Main.java
java --module-path mods --add-modules java.sql --add-reads demo.read=java.sql -m demo.read/demo.read.Main
~~~

Stdout from the final command:

~~~text
java.sql
~~~

`--add-modules java.sql` ensures `java.sql` is added as a root to resolve in this example since `demo.read` does not `requires` it; `--add-reads demo.read=java.sql` allows `demo.read` to read the exported public packages of `java.sql`.

If you **omit only `--add-reads`** at compile time, the compiler may report that package `java.sql` is not visible because `demo.read` does not read `java.sql`, even though `java.sql` is already resolved. If you provide the flags at compile time yet omit them at runtime, the dependency is still not properly established in the runtime graph; accessing related types will risk linkage/access errors.

The sustainable solution is updating the descriptor to:

~~~java
module demo.read {
    requires java.sql;
}
~~~

With the proper descriptor and module `java.sql` present, you can compile and run with:

~~~bash
javac -d mods/demo.read src/read/module-info.java src/read/demo/read/Main.java
java --module-path mods -m demo.read/demo.read.Main
~~~

Neither `--add-modules` nor `--add-reads` is needed in this example because `requires` handles both dependency resolution and readability. **This is the recommended approach when genuinely having a permanent dependency on `java.sql`.** The `--add-reads` flag is better suited for white-box testing, migration, or experimental setups where `module-info.java` cannot or should not be edited immediately.

### When to use =ALL-UNNAMED?

A module has already been placed on the module path yet still needs to use a legacy library **on the classpath** during migration. The flag:

~~~text
--add-reads demo.read=ALL-UNNAMED
~~~

adds a read edge to unnamed modules (the classpath side). It **does not turn a classpath JAR into a named module** and does not solve class lookup if `-cp` is wrong. This is a temporary bridge while modularization is incomplete; if the library can become an appropriate named/automatic module, improve the dependency structure.

## 6. --add-exports: Allowing Public Types in an Unexported Package

A named module can declare a public class yet **not export** the package containing it. Code in other modules cannot access that type through normal access. The flag `--add-exports B/p=A` tells `B` to treat package `p` as additionally exported to `A` for the specified tool invocation.

### Complete example: internal package conditionally exposed to a test module

Structure:

~~~text
project/
├── src/
│   ├── lib/
│   │   ├── module-info.java
│   │   └── demo/lib/internal/Secret.java
│   └── use/
│       ├── module-info.java
│       └── demo/use/Main.java
└── mods/                 (generated at build time)
~~~

**`src/lib/module-info.java`**

~~~java
module demo.lib {
    // Do not export demo.lib.internal
}
~~~

**`src/lib/demo/lib/internal/Secret.java`**

~~~java
package demo.lib.internal;

public final class Secret {
    private Secret() {
    }

    public static String message() {
        return "internal: allowed";
    }
}
~~~

**`src/use/module-info.java`**

~~~java
module demo.use {
    requires demo.lib;
}
~~~

**`src/use/demo/use/Main.java`**

~~~java
package demo.use;

import demo.lib.internal.Secret;

public class Main {
    public static void main(String[] args) {
        System.out.println(Secret.message());
    }
}
~~~

Bash commands:

~~~bash
mkdir -p mods/demo.lib mods/demo.use
javac -d mods/demo.lib src/lib/module-info.java src/lib/demo/lib/internal/Secret.java
javac --module-path mods --add-exports demo.lib/demo.lib.internal=demo.use -d mods/demo.use src/use/module-info.java src/use/demo/use/Main.java
java --module-path mods --add-exports demo.lib/demo.lib.internal=demo.use -m demo.use/demo.use.Main
~~~

Final stdout:

~~~text
internal: allowed
~~~

Here:

- `demo.use` **already reads** `demo.lib` because its descriptor has `requires demo.lib`.
- `demo.lib` **is already resolved** through that dependency.
- What is missing is that `demo.lib.internal` is **not exported**. The `--add-exports` flag supplies exactly this accessibility to `demo.use`.
- If the flag is omitted from the `javac` command, `import demo.lib.internal.Secret` is rejected because the package is not exported.
- If compiled with the flag yet the corresponding flag is omitted when `java` runs, the JVM may throw `IllegalAccessError` when accessing a class in a package not exported at runtime.

This flag does not make `private` fields/methods accessible from outside the class: `Secret.message()` is `public`, so only after module access is valid can it be called. `--add-exports` only affects **module-level package exports**; it does not eliminate language access modifiers.

### Why not always edit module-info.java to add exports?

If `demo.lib.internal` is an internal API, unconditional exporting increases the public API surface and can cause application code to depend on implementation details. For white-box tests, sometimes a package only needs temporary exposure to the test module. For actual production dependencies, the better solution is usually moving the needed feature into an intentionally exported public API.

Do not use flags that open packages merely to mask poorly defined module boundaries in a project.

## 7. When Multiple Flags Are Needed Together

A JPMS error may involve **multiple independent unsatisfied conditions**. For example, in a situation where `demo.app` has not declared `requires demo.lib`, and the needed class resides in unexported `demo.lib.internal`:

~~~text
--add-modules demo.lib
--add-reads demo.app=demo.lib
--add-exports demo.lib/demo.lib.internal=demo.app
~~~

When temporary CLI configuration is necessary, the three options above respectively:

1. Ensure `demo.lib` is present in the graph.
2. Create the edge `demo.app → demo.lib`.
3. Have `demo.lib` export package `demo.lib.internal` specifically to `demo.app`.

The snippet above is a **scenario-based combination pattern**, not a standalone runnable program. Only two or one flag is needed if the rest is already satisfied by descriptors/the module graph. Avoid "firing all three options" with vague module names: that makes configuration hard to audit and easy to forget in deployment.

A useful principle for debugging:

~~~text
Module not found?
  └── Check --module-path and module resolution/--add-modules.

Module is in the graph yet 'does not read'?
  └── Check requires or --add-reads in the right direction.

Module already read yet 'package ... is not visible/does not export'?
  └── Check exports or --add-exports.

Accessing private member / reflective access?
  └── Check access modifier or --add-opens for deep reflection.
~~~

If the error stems from a JAR missing on the module path, graph flags cannot conjure the JAR out of thin air. If two modules share a duplicate package in invalid configurations, adding exports/reads is not a fix for the split-package problem either.

## 8. Distinguishing Compile-Time and Runtime Effects

There are **two processes and two configurations** that matter:

| Phase | Tool | What to check |
| --- | --- | --- |
| Source compilation | `javac` | Resolved module names, readability, exports for types in source code |
| Running compiled classes | `java` launcher / JVM | Runtime graph, module path, readability, exports of loaded classes |

Exposing a package via `--add-exports` at compile time only ensures the compiler **is permitted to emit a class file referencing** that class. Runtime still requires the corresponding permission if the descriptor does not export it. Similarly, a `--add-reads` edge at compile time is not automatically written into `module-info.class` as a new `requires` for every subsequent `java` command.

This explains a common situation: the build succeeds because the IDE/Gradle automatically adds compiler flags, yet running `java` from the terminal hits `IllegalAccessError` or module errors. Inspect the **actual `java` command** launched by the build, test runner, IDE, or container.

There are certain cases where the compiler/launcher propagates special settings automatically (such as source-file mode), yet you should not generalize from that to assume compile-time flags always carry over to runtime.

**Note on `--release`:** when using `javac --release`, especially when attempting to export an internal package of a *system module* like `java.base`, release compatibility restrictions may cause the option combination to be rejected. Do not assume a command leveraging JDK internals will work across all `--release` values. Check `javac --help` and `javac --help-extra` of the JDK in use and choose alternative public APIs when available.

## 9. The Three Flags Differ from Easily Confused Concepts

### 9.1. --module-path vs. --class-path

`--module-path` (`-p`) tells the tool where to find **named modules/automatic modules**. `--class-path` (`-cp`) is where to look for code belonging to the unnamed module. Placing a plain JAR without `module-info.class` on the module path can turn it into an **automatic module** with special naming and rules. The same JAR on the classpath belongs to the unnamed module, with no module name to pass to `--add-modules my.jar`.

Do not infer a module name from a JAR filename without verifying. You can use `jar --describe-module --file library.jar` or an appropriate module-listing tool. An automatic module can derive its name from the manifest `Automatic-Module-Name` or from the JAR filename.

### 9.2. --add-exports vs. --add-opens

- `--add-exports B/p=A` opens **compile/link-time** access to public types/members in package `p` of `B` for `A` (when read edges and other public/access conditions hold).
- `--add-opens B/p=A` opens `B`'s package so code in `A` can perform **deep reflection** at runtime, such as accessing non-public members via `setAccessible` when appropriately permitted.
- `opens` does not replace `exports` as a normal compiler flag for importing and calling public internal APIs. Conversely, `exports` does not automatically allow reflection into `private` fields.

When a program throws `InaccessibleObjectException` from reflection, check `opens`/`--add-opens`, JDK version, and reflection permissions. When the compiler reports an unexported package, check `exports`/`--add-exports`. Two errors at different layers should not be fixed with the same flag.

### 9.3. --add-reads vs. --patch-module

`--patch-module module=path` is used to add/replace classes/resources belonging to a module at build/runtime via a patching mechanism, commonly seen in white-box tests. It is not synonymous with making a module read another module. For tests needing access to internal packages, you may need to combine `--patch-module`, `--add-reads`, and `--add-exports` depending on how the tests are placed in the module.

### 9.4. --add-modules vs. --limit-modules

`--add-modules` adds root modules; `--limit-modules` narrows the set of observable modules in a configuration. If a module is excluded from the universe by `--limit-modules` or missing from the runtime image, merely adding its name via `--add-modules` cannot guarantee successful resolution.

## 10. Special Values and When to Avoid Over-Opening

| Value | Used with | Meaning |
| --- | --- | --- |
| `ALL-MODULE-PATH` | `--add-modules` | Makes all observable modules from the module path roots, useful in build tools/automatic modules |
| `ALL-DEFAULT` | `--add-modules` of the `java` launcher | Default root set for classpath applications in that runtime configuration |
| `ALL-SYSTEM` | `--add-modules` of the `java` launcher | Roots all system modules; usually for test harnesses/special cases |
| `ALL-UNNAMED` | Right-hand side of `--add-reads` or `--add-exports` | Targets unnamed modules, usually associated with the classpath |

Example of a tool needing to load multiple plugins placed under the module path:

~~~bash
java --module-path plugins --add-modules ALL-MODULE-PATH -cp out Host
~~~

This is a **command template**, working only when the modules in `plugins` are valid and `Host`/dependencies are present. Avoid using `ALL-MODULE-PATH` unconditionally because it can pull unwanted modules into the graph and expose version/package conflicts. When the needed modules are known, naming them explicitly is usually clearer.

`ALL-UNNAMED` in `--add-exports java.base/sun.nio.ch=ALL-UNNAMED` is a syntax example for legacy classpath code needing an internal JDK package. Relying on internal packages may break compatibility with newer Java releases; this is **not a recommended configuration for production code**. Do not include this flag in every application just "to be safe."

## 11. Common Errors and Fixing the Right Issue

| Symptom | Possible cause | How to check/fix |
| --- | --- | --- |
| `module not found: demo.lib` | Wrong `--module-path`, module name, or module artifact does not exist | Check output `module-info.class`, `jar --describe-module`, paths |
| `package ... is not visible (not in the module graph)` | Named module is on the module path yet not resolved | Check `requires` or `--add-modules` |
| `module demo.app does not read demo.lib` | Missing readability edge | `requires demo.lib` or temporarily `--add-reads demo.app=demo.lib` |
| `package ... is not visible (does not export ...)` | Provider module does not export the package | Use public API/`exports` or temporary flag `--add-exports` |
| `IllegalAccessError` when running after successful compile | Runtime graph/exports differ from compiler graph/exports | Pass matching flags to the JVM launcher or fix descriptors |
| `InaccessibleObjectException` during reflection | Package not opened for deep reflection | Check `opens` / `--add-opens` at runtime |
| `NoClassDefFoundError`/`ClassNotFoundException` | Missing class/runtime dependency or unresolved module | Check `-cp`, `--module-path`, root modules, runtime image |
| Flag `--add-exports` "does not open private" | Module export does not change Java access modifiers | Fix API/control reflection via the proper mechanism |
| Flags have no effect when running IDE/tests | Flags were set only for the compiler, not the test JVM/launcher | Check both compile and test runtime configurations |

Do not read error messages by a single keyword: the same "package not visible" phrasing can result from missing resolution, readability, or export. Examine the full diagnostic, the mentioned module names, and how the build tool supplies the module path.

## 12. Step-by-Step Diagnostic Workflow

1. **Identify where the needed class lives**: classpath (unnamed module), JDK system module, named module JAR, or automatic module on the module path?
2. **Confirm the module name** using `java --list-modules` for the runtime image when appropriate, or `jar --describe-module --file path/to/library.jar` for a JAR. `java --list-modules` by default lists runtime image modules; do not treat it as an exhaustive list of every plugin JAR placed outside the image.
3. **Check observability**: does `--module-path` point to the right module artifact? Does the artifact have `module-info.class` or the expected automatic module name?
4. **Check resolution**: did the provider module enter the graph via root/`requires`, or does it need `--add-modules`?
5. **Check readability**: does the consumer module have a `requires`/readability edge to the provider, or is it merely sitting on the module path?
6. **Check exports**: does the provider package have `exports p` or `exports p to A`? If not, is exposing an internal class truly necessary for testing/migration?
7. **Check the corresponding runtime**: rerun with the exact module path, module flags, and JVM of the target environment, rather than merely proving `javac` passes.
8. **Remove flags when possible**: after fixing module descriptors or switching to public APIs, remove temporary flags and run regression tests.

You can use `java --describe-module demo.lib` for a module found by the runtime, or `jar --describe-module --file ...` for modular/automatic JARs. These commands help verify name, `requires`, exports, and main class metadata when present; not every question about the runtime graph can be solved by a single listing command.

## 13. Things You Should Not Conclude

**"Once --add-modules is present, every class in the module can be imported."** False. The module may be resolved yet unread by a named consumer or its package unexported.

**"Once --add-reads is added, package-private elements of the dependency can be called."** False. Readability only establishes the read edge; the package must still be exported, and types/members must still have Java accessibility.

**"--add-exports allows reflection into any field."** False. For deep reflection into non-public members, `--add-opens` and appropriate reflection conditions are typically needed.

**"If javac succeeds, java will automatically inherit similar flags."** False. Compiler and launcher configurations must be verified independently, even when orchestrated by the same build tool.

**"All three flags should be added to every JPMS project."** False. The right path is describing module dependencies with `requires` and public APIs with `exports` in descriptors; use CLI adjustments in specific cases.

**"If the artifact is named library-1.0.jar, the module name is definitely library."** False. The module descriptor, manifest, and automatic module naming rules can yield a different result.

## 14. Self-Check Exercises

**Question 1.** A classpath application wants to use a public API in named module `org.tools` on the module path, yet the compiler reports the module is not in the graph. Which flag is directly involved?  
**Answer:** `--add-modules org.tools`, while also checking the module path. `--add-exports` is unnecessary if the package is already publicly exported.

**Question 2.** `demo.app` and `demo.lib` are both resolved; `demo.lib` already exports `demo.lib.api`, yet `demo.app` lacks `requires demo.lib`. What is missing?  
**Answer:** A readability edge; ideally declare `requires demo.lib`; when the descriptor cannot be edited, `--add-reads demo.app=demo.lib` can be used temporarily.

**Question 3.** `demo.app` already `requires demo.lib` yet wants to call public `Secret` in unexported `demo.lib.internal`. What is needed?  
**Answer:** A new public API / intentional exports, or temporarily `--add-exports demo.lib/demo.lib.internal=demo.app` at compile and runtime when needed.

**Question 4.** `Main` code on the classpath wants to use a package conditionally exported to unnamed modules. Which special value is involved?  
**Answer:** `ALL-UNNAMED` as the target of `--add-exports`, for example `--add-exports demo.lib/demo.lib.internal=ALL-UNNAMED`.

**Question 5.** Why is `--add-exports demo.lib/internal=demo.app` invalid syntax when the actual package is named `demo.lib.internal`?  
**Answer:** After `/` must be the **full package name**, here `demo.lib.internal`, not a directory name or an arbitrary shortened suffix.

**Question 6.** Does `--add-reads demo.app=ALL-UNNAMED` move `legacy.jar` from the classpath to the module path?  
**Answer:** No. It only creates a readability edge to unnamed modules; library lookup still follows the classpath.

**Question 7.** `--add-exports` was added to `javac` and compilation passed, yet `java` throws `IllegalAccessError` when accessing the internal class. What needs checking?  
**Answer:** Whether the corresponding export is present at runtime, whether the module path and module names are correct, and whether other module/readability conditions are met.

**Question 8.** For a project where `module-info.java` can be changed, should you use `--add-reads` for a permanent dependency or add `requires`?  
**Answer:** Add `requires` so the module metadata self-describes the dependency and the compiler/runtime share the same graph by design.

## 15. Checklist for Applying in Java 17+ Projects

- Read `module-info.java` and determine **root → resolution → reads → exports** in that exact question order.
- When a *module is missing from the graph*, check paths and `--add-modules`.
- When a *readability edge* is missing, prefer `requires` or use `--add-reads` when there is a temporary reason.
- When lacking *permission to use public types of a package*, prefer an exported public API or `--add-exports` for the selected target.
- Distinguish `--add-exports` from `--add-opens` for deep reflection.
- If using flags to cross module boundaries, apply them completely to both **javac** and **java/test launcher** as actually needed.
- Do not use `ALL-MODULE-PATH`, `ALL-SYSTEM`, or `ALL-UNNAMED` unconditionally; the wider the graph and access permissions, the harder they are to control.
- Check the exact JDK version, option support, and restrictions when using `--release` or a custom runtime image.
- When migration finishes, switch to sustainable `requires`/`exports` and remove CLI overrides that are no longer needed.

**Remember:** `--add-modules` solves **which modules are resolved**; `--add-reads` solves **whether module A reads module B**; `--add-exports` solves **whether package P of B is exported to A**. The three flags address different pieces of JPMS and do not replace `public`, a proper classpath, real dependencies, or clean module design.

### Official documentation and practical guides

- [Oracle Java SE 17: javac Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html).
- [Oracle Java SE 17: java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html).
- [Dev.java: Extending the Module Graph with --add-modules and --add-reads](https://dev.java/learn/modules/add-modules-reads/).
- [Dev.java: Circumventing Strong Encapsulation](https://dev.java/learn/modules/strong-encapsulation/).
- [JEP 261: Module System](https://openjdk.org/jeps/261).