# Using --patch-module in Controlled Scenarios

`--patch-module` is an advanced option of the Java module system (JPMS) that allows **adding to or overriding the class/resource contents of an existing named module** for a specific compilation or execution run. It is especially useful when writing **white-box tests** (testing inside a module), trying a temporary replacement of a class to diagnose bugs, or verifying a change before rebuilding the official module.

The key point: this option changes **how tools locate a module's contents in the configured process**. It does not permanently modify the original JAR/module, does not create a new module, and does not turn an arbitrary classpath into a properly structured module system. Because patches take precedence during class lookup, overuse can hide version mismatches, break reproducibility, and cause a program to behave differently across development machines, CI, and production.

This article belongs to the **Java Modules** group of Java Advance – compilation, using Java 17 or later. The hands-on section is tested on a JDK supporting `javac --release 17`, focusing on a named module we create ourselves and a patch residing in a separate output directory.

## 1. Context: Java Modules Differ from Packages and the Classpath

A **named module** declares `module-info.java`, with a module name and directives such as `requires`, `exports`, `opens`, `uses`, `provides`. Example:

~~~java
module demo.library {
    exports demo.library.api;
}
~~~

In this example:

- `demo.library` is the **module name**.
- `demo.library.api` is the **package** whose public API the module allows other modules to access.
- Unexported internal packages can still contain classes and methods, yet code outside the module cannot arbitrarily use them under JPMS rules.
- `requires demo.library;` in an application module declares a *readability* relationship between the two modules.
- `--module-path` specifies the locations of module artifacts (modular JARs or exploded module directories) for tools to locate and resolve modules.

An ordinary **classpath** is used for the unnamed module, whereas the **module path** allows JPMS to recognize named modules and enforce boundaries. `--patch-module` acts upon **a specific module that already has an identity**, so you must understand the patched module and the module resolution environment.

Comparison:

| Configuration | Meaning | Does it change the visible contents of a module? |
|---|---|---|
| `--class-path` or `-cp` | Classpath-style search path for classes/resources | Not a mechanism for patching named modules |
| `--module-path` | Search path for module artifacts | Specifies where to find modules; does not override individual classes patch-style |
| `--patch-module m=path` | Merges contents from `path` into module `m`, prioritizing patch contents | Yes, within the configured compilation/execution run |
| `--add-reads` | Relaxes module readability relationship | Does not replace bytecode |
| `--add-exports` | Relaxes package accessibility to other modules | Does not replace bytecode |
| `--add-opens` | Relaxes deep reflection access at runtime | Does not replace bytecode |

These are distinct mechanisms. Use `--patch-module` to **inject contents into a module**, and use the additional `reads/exports/opens` options only when those specific constraints need adjustment for a controlled testing environment.

## 2. Syntax and Patch Paths

General syntax for `javac` and `java`:

~~~text
--patch-module <module-name>=<patch-path>
~~~

`<module-name>` is the **module name**, not a package or JAR name. `<patch-path>` is one or more directories/JARs searched as roots of the package tree, using the OS-specific path separator:

~~~text
Windows:      --patch-module demo.library="patch-classes;extra-patch.jar"
Linux/macOS:  --patch-module demo.library="patch-classes:extra-patch.jar"
~~~

The two-line example above only illustrates multi-entry syntax; the main hands-on walkthrough uses a single directory so it works identically across operating systems.

Important rules:

1. Each entry of the patch path must point to the **root of the package tree**. If the file is `patch-classes/demo/library/api/Greeting.class`, pass `patch-classes`, not `patch-classes/demo/library/api`.
2. A patch can contain **new** classes, classes with the **same binary name** as original classes to replace them, and resources. Declarations must conform to package/module identity and other Java rules.
3. Content found on the patch path takes precedence over content with the same name in the original module; when multiple patch path entries exist, an earlier entry can shadow matching content in later entries.
4. For `javac`, specify `--patch-module` at most **once per module** in a single compilation pass; combine multiple entries into that single path value.
5. Because relative paths depend on the process's working directory, run from a known project root or pass normalized paths.
6. `--patch-module` does not automatically pick up contents from every JAR file inside a directory; specify the exact directory containing the package tree or the exact JAR.

When patching a module from multiple sources, control the order of path entries to avoid unexpectedly picking a duplicate-named class. Do not use the order of an unmanaged JAR list as a version selection mechanism.

## 3. Difference Between Compile-Time Patching and Runtime Patching

There are **two independent processes**:

- `javac --patch-module demo.library=...`: the compiler analyzes patch sources/classes as part of the specified module, allowing compilation of test classes in the same package as internal module classes, or compilation of an alternate version of an original class.
- `java --patch-module demo.library=...`: the JVM loads patch classes/resources into the corresponding module for that specific run. This operation affects execution.

Using a patch in one phase **does not automatically activate the patch in the other**:

~~~text
               Compile phase                            Run phase
  original module + patch-src --javac--> patch-classes
                                                       |
  original module + patch-classes ---------java--------> patched process
  original module -------------------------java--------> original process
~~~

For example, after generating patch bytecode, if you run `java` **without** passing `--patch-module`, the JVM still uses the original contents from the module artifact (unless another configuration changed the content source).

This enables cleanly scoped experiments: with the exact same original modules, run **baseline**, **patched run**, then **baseline again** to prove the patch does not alter the original artifacts.

## 4. Sample Project with Two Named Modules and a Separate Patch

We will have:

- `demo.library`: library module, containing an exported API and a package-private internal class.
- `demo.app`: application module, `requires demo.library` and calls the public API.
- `patch-src`: replacement `Greeting` class and new `WhiteBoxProbe` for internal inspection.
- `patch-classes`: separate bytecode for the patch, **not** bytecode of the original module.

Final directory structure:

~~~text
project/
├── src/
│   ├── demo.library/
│   │   ├── module-info.java
│   │   └── demo/library/
│   │       ├── api/Greeting.java
│   │       └── internal/Secret.java
│   └── demo.app/
│       ├── module-info.java
│       └── demo/app/Main.java
├── patch-src/
│   └── demo/library/
│       ├── api/Greeting.java
│       └── internal/WhiteBoxProbe.java
├── mods/                  # original module compilation output
└── patch-classes/         # patch compilation output
~~~

The paths use `/` compatible with the `javac`/`java` commands shown below. Create the proper source directories before saving the files. Each `public` class name must match its Java filename.

### 4.1. Library module: module-info.java

File `src/demo.library/module-info.java`:

~~~java
module demo.library {
    exports demo.library.api;
}
~~~

Package `demo.library.api` is exported; package `demo.library.internal` is not exported. That is a key point for understanding **white-box testing**.

### 4.2. Library module: original API

File `src/demo.library/demo/library/api/Greeting.java`:

~~~java
package demo.library.api;

public final class Greeting {
    public static String message() {
        return "original";
    }
}
~~~

Method `message()` is public and returns the string `original`.

### 4.3. Library module: internal class

File `src/demo.library/demo/library/internal/Secret.java`:

~~~java
package demo.library.internal;

final class Secret {
    static String token() {
        return "inside-module";
    }
}
~~~

`Secret` is a **package-private top-level class**, and method `token()` is also package-private. A class in another package, even within the same module, cannot directly call `Secret.token()` under normal Java access rules.

### 4.4. Application module: module-info.java

File `src/demo.app/module-info.java`:

~~~java
module demo.app {
    requires demo.library;
}
~~~

The `requires` line gives the application module readability to `demo.library`; the application still only has access to appropriately exported packages.

### 4.5. Application module: Main.java

File `src/demo.app/demo/app/Main.java`:

~~~java
package demo.app;

import demo.library.api.Greeting;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
~~~

This is a complete program with main. The application only uses the library's public API.

## 5. Compiling the Original Modules and Running the Baseline

Open a terminal in the `project` directory. Compilation command:

~~~sh
javac --release 17 -encoding UTF-8 --module-source-path src -d mods -m demo.library,demo.app
~~~

Explanation:

- `--module-source-path src` indicates the source layout `src/<module-name>/...`.
- `-m demo.library,demo.app` selects the modules to compile, without needing to manually list each source file.
- `-d mods` stores the compiled modules under `mods/demo.library` and `mods/demo.app`; `javac` organizes output according to module structure.
- `--release 17` uses Java 17 language rules and public APIs.
- `-encoding UTF-8` keeps source encoding consistent.

Run the baseline:

~~~sh
java --module-path mods -m demo.app/demo.app.Main
~~~

Stdout:

~~~text
original
~~~

In the run command, `--module-path mods` supplies the two exploded modules; `-m demo.app/demo.app.Main` runs the main class of module `demo.app`. JPMS resolves `demo.library` via `demo.app`'s `requires` directive.

**This is a mandatory control point:** before patching, we need to verify that the original modules run properly and print `original`. If the baseline already fails, fix the structure or module graph before attempting a patch.

## 6. Creating a Patch to Override the Original API Class

Create file **`patch-src/demo/library/api/Greeting.java`**:

~~~java
package demo.library.api;

public final class Greeting {
    public static String message() {
        return "patched";
    }
}
~~~

It shares the same package name and same binary name `demo.library.api.Greeting` as the original class; the `message()` method signature stays the same, changing only the return value. This is an **intentional behavioral replacement**, not an official way to update a module.

Compile the patch file in the context of the original module:

~~~sh
javac --release 17 -encoding UTF-8 --module-path mods --patch-module demo.library=patch-src -d patch-classes patch-src/demo/library/api/Greeting.java
~~~

Create directory `patch-classes` before running if your tool/setup requires the target directory to exist. Option `--module-path mods` tells `javac` about the compiled `demo.library` module; `--patch-module demo.library=patch-src` places the patch sources in **that module's context**; `-d patch-classes` outputs patch bytecode to a separate directory.

After compilation, `patch-classes/demo/library/api/Greeting.class` exists. Do not put the patch class inside `mods/demo.library`: the goal of the example is keeping the original module intact for comparison.

Run with patch:

~~~sh
java --module-path mods --patch-module demo.library=patch-classes -m demo.app/demo.app.Main
~~~

Exact stdout:

~~~text
patched
~~~

This proves the runtime prioritizes the `Greeting` definition from the patch path. If `--patch-module` is omitted from the run command:

~~~sh
java --module-path mods -m demo.app/demo.app.Main
~~~

the output returns to:

~~~text
original
~~~

Running in the order baseline → patched → baseline has been verified in practice, compiling with `javac --release 17`. The changed behavior exists only in the process configured with the patch.

## 7. Adding Classes to Test Inside a Module

Another controlled scenario is **white-box testing**: needing to verify internal component behavior without opening the public API or modifying `exports` of the original module solely to run tests.

Create file **`patch-src/demo/library/internal/WhiteBoxProbe.java`**:

~~~java
package demo.library.internal;

public final class WhiteBoxProbe {
    public static void main(String[] args) {
        System.out.println(Secret.token());
    }
}
~~~

`WhiteBoxProbe` is placed in the **same package** as `Secret`, so it can call `Secret.token()` if compiled and run within the same module. There is no `import` line because both classes share the package; making the new class `public` does not automatically export package `demo.library.internal`.

Compile the full patch including both the replacement class and the probe class:

~~~sh
javac --release 17 -encoding UTF-8 --module-path mods --patch-module demo.library=patch-src -d patch-classes patch-src/demo/library/api/Greeting.java patch-src/demo/library/internal/WhiteBoxProbe.java
~~~

Run the probe inside the patched module:

~~~sh
java --module-path mods --patch-module demo.library=patch-classes -m demo.library/demo.library.internal.WhiteBoxProbe
~~~

Exact stdout:

~~~text
inside-module
~~~

Why is this valid?

1. `Secret` and `WhiteBoxProbe` are in the same package `demo.library.internal`.
2. `WhiteBoxProbe` is **injected into module `demo.library`** via `--patch-module` at compile time and runtime.
3. Package-private access is checked according to the rules of the corresponding package and runtime module.
4. We do not need to add `exports demo.library.internal;` to the original `module-info.java` just to run an internal probe.

In practice, a unit-test framework may require additional `--add-reads`/`--add-opens` options depending on how the runner, framework, and reflection are structured. This article uses `main` inside the patched module to isolate the basic mechanism without involving frameworks.

### 7.1. Why not just put the test class on the classpath?

If `WhiteBoxProbe` is compiled as a class of the **unnamed module** and references a package-private class in a named module, two barriers arise: the package is not exported, and the type is not declared public. Having the same `package demo.library.internal;` string in source from a different module **does not mean** being in the same runtime package with automatic access rights.

For white-box tests, patching is an intentional way for test code to be treated as part of the target module. The goal is **preserving module encapsulation in the main product**, while the test environment receives the required access through separate configuration.

## 8. Packaging a Patch into a Separate JAR

Instead of passing the `patch-classes` directory, you can create a patch JAR **without its own module-info.class**. Create the `patches` directory and package it:

~~~sh
jar --create --file patches/library-patch.jar -C patch-classes .
~~~

With PowerShell you can create the directory first via:

~~~powershell
New-Item -ItemType Directory -Path patches -Force | Out-Null
~~~

With Linux/macOS: `mkdir -p patches`.

Run:

~~~sh
java --module-path mods --patch-module demo.library=patches/library-patch.jar -m demo.app/demo.app.Main
~~~

The mechanism matches using a patch directory: the JVM reads classes in the patch JAR as contents of **demo.library**. The patch JAR does not need (and should not attempt) to declare a new `module demo.library { ... }`; the original module's descriptor continues to determine module identity and constraints.

A JAR on `--module-path` **differs** from a JAR passed to `--patch-module`. In this example, `library-patch.jar` is a **container of patch contents**, not an independent module to `requires`.

If running with the JAR produces different results from the patch directory, check for the exact entry `demo/library/api/Greeting.class` using `jar --list --file patches/library-patch.jar`, as well as paths/working directory. Do not assume creating the JAR automatically applies the patch to every run.

## 9. Precedence Order and Duplicate Class Names

The patching mechanism prioritizes content from the patch path over corresponding content in the original module. If multiple entries are specified for the same module, the first found content can shadow identically named items in later entries. Example (syntax illustration only):

~~~text
Windows:
--patch-module demo.library="patch-a;patch-b"

Linux/macOS:
--patch-module demo.library="patch-a:patch-b"
~~~

If both `patch-a` and `patch-b` contain `demo/library/api/Greeting.class`, do not treat them as two copies merged into one class. One duplicate-named class definition will be found first, while the later one is shadowed.

Maintain a clear list of **each class/resource added or replaced**, avoiding cases where a patch contains an unintended stale `.class` file. You can inspect with:

~~~sh
jar --list --file patches/library-patch.jar
javap -classpath patch-classes demo.library.api.Greeting
~~~

`javap` shows the structure/signatures of the class in the patch, helping verify you built the right class. To see what a method does at the bytecode level, you can use `javap -c -classpath patch-classes demo.library.api.Greeting`.

Avoid placing inconsistent sources and bytecode across multiple patch paths and relying on implicit ordering. Specify a single target patch, keep patch output separate from product output, and retain test evidence.

## 10. --patch-module Does Not Replace module-info or Alter the Module Graph

One of the most important boundaries is that **patching content does not mean modifying the module descriptor**. Patching is not an API to redefine a module by replacing `module-info.class` in a patch JAR, and it does not automatically add `requires`, `exports`, `opens`, `uses`, or `provides` directives to the original module's descriptor.

For example, `demo.library` only exports `demo.library.api`. If another module wants to directly import a type in `demo.library.internal`, having `WhiteBoxProbe.class` in the patch **does not automatically export** package `demo.library.internal` outward.

### 10.1. When readability adjustments are needed

If a patch class genuinely needs to call an API from another module that `demo.library` **does not read** in the current module graph, the compiler/runtime may reject it even though the bytecode/file is on the module path. In specialized tests, an appropriate `--add-reads` can be used to extend the module's readability.

Conceptual example (not a runnable command for the project in section 4 since that project needs no other module):

~~~text
--add-reads demo.library=some.module
~~~

Condition: `some.module` must actually exist and be properly resolved, and needed packages remain subject to export rules. **`--add-reads` does not create modules or grant access to every package.**

### 10.2. When exports or opens are needed

If a test module **other than the patched module** must directly use a public type from an unexported package, an appropriate `--add-exports` may be needed in the test compile/run configuration. If a framework uses deep reflection into non-public members, runtime may require `--add-opens`.

Conceptual example:

~~~text
--add-exports demo.library/demo.library.internal=demo.tests
--add-opens demo.library/demo.library.internal=demo.tests
~~~

In the case above, `demo.tests` is a hypothetical existing test module not present in the sample project. `--add-exports` does not allow direct access to a **package-private class** from another package using normal Java syntax; it only alters the package's export boundary, while member access rules still apply.

`--add-opens` pertains to deep reflective access at runtime and is not equivalent to granting compile-time permission to import an arbitrary type.

### 10.3. Patching does not turn a nonexistent module into a valid module

To use:

~~~text
--patch-module demo.library=patch-classes
~~~

the tool must recognize **module `demo.library`** in the configured environment. Placing a directory of classes onto the patch path without a target module is not a way to declare a new named module. Check that the module resides in `mods`, on the appropriate module path, or is an actual system module; at runtime, verify whether the module is resolved in the module graph.

For the example application, `demo.app` already `requires demo.library`, so the module resolves naturally when running `-m demo.app/...`.

## 11. Risks of Replacing Classes with Incompatible Signatures

In the sample project, the patch preserves:

~~~java
public static String message()
~~~

and only changes the return value. This is a change compatible with the already compiled `demo.app` bytecode.

If a patch removes a method, changes parameters, changes the return type in the bytecode signature, switches from `static` to instance, or alters access conditions, compiled application code can fail when the JVM links/invokes it, for example:

- `NoSuchMethodError`: bytecode requires a method that the actually loaded class no longer appropriately declares/inherits.
- `NoSuchFieldError`: the referenced field no longer matches.
- `IncompatibleClassChangeError`: a binary structural relationship changed incompatibly.
- `IllegalAccessError`: access denied during linking.
- `ExceptionInInitializerError` or initialization errors: the patch alters class initialization behavior.

Therefore, a patch replacing an implementation must be verified for **both API compatibility and runtime behavior**. Do not prove a patched class loaded by glancing at one line of stdout and conclude every consumer is safe.

Even when signatures do not change, semantic changes (such as a method always returning `null` instead of a string) can still cause business logic bugs. White-box patching is only appropriate for targeted tests with clear outputs and rollback conditions.

## 12. Patching System Modules and Boundaries to Respect

The `--patch-module` mechanism can also appear in specialized tests of system modules, such as a core library in a test JDK environment. However, **patching system modules like `java.base` has a very broad impact**: JDK classes are used by many other components; substituting incorrect bytecode or violating runtime assumptions can cause startup failures, linkage errors, or unpredictable behavior.

For practice and most applications:

1. Patch **modules you own**, inside a reproducible test project.
2. Do not use patches to silently swap internal JDK APIs in production.
3. Do not treat `--patch-module` as an official way to fix bugs in released third-party libraries.
4. Do not take a working patch as proof that a package is exported or an internal API has become a supported public contract.
5. For libraries/modules genuinely needing long-term fixes, modify source code, then build and publish a proper module/JAR; let dependency management handle versioning.

Certain special mechanisms impose limits on class format, access permissions, module resolution, and class loading. Consult documentation for the running JDK version; do not extrapolate from one simple test that every module, class loader, and JDK accepts the same patch.

## 13. Applying This to Testing in Gradle/Maven/IDEs

In real projects, build tools may automatically manage compiling and running module/test sources. There are multiple testing structures:

- **Black-box tests:** use only the module's exported public API. Usually `--patch-module` is not needed.
- **White-box tests:** tests live in packages of the target module and need to see package-private classes/members. `--patch-module` can be used so the compiler and JVM treat test code as contents of the target module.
- **Reflection-heavy tests:** frameworks need access to internal members; appropriate `--add-opens` may be required in addition to patching.
- **Integration tests:** verify that the actual packaged artifact **contains no test patches** and that test configuration is not accidentally applied to production.

With Gradle, `JavaCompile` and `Test` tasks usually need **separate** configuration for compiler arguments and JVM arguments. Adding `--patch-module` only to `options.compilerArgs` is not enough for a `Test` or `JavaExec` process to automatically use the patch when running. Conversely, runtime JVM arguments do not make `javac` compile test sources in the patch context.

With Maven/IDEs, inspect how plugins or the IDE construct the module path, classpath, test output, JVM args, and module launcher selection; plugin versions can differ. Do not copy one configuration snippet across every project while ignoring actual output. A reliable workflow is **printing/logging the exact javac and java commands generated by the build tool**, comparing them with manual examples, and running tests in CI.

If a framework or plugin already provides a JPMS-aware white-box testing solution, follow that tool's exact documentation. Do not add `--patch-module` broadly to every task, as it can mask module boundary errors that ought to be caught.

## 14. Diagnosing Common Errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| `module not found: demo.library` | Target module is missing from the module path of the corresponding phase | Check `mods/demo.library/module-info.class`, `--module-path`, and module name |
| Patch present yet still prints `original` | Patched only at compile time, forgot patch at runtime; wrong root directory or module not resolved | Check the `java --patch-module ...` command and whether the class actually exists on the patch path |
| `package ... is not visible` | Module does not read the other module or package is not properly exported | Check `requires`, `exports`; only add `--add-reads`/`--add-exports` if genuinely justified |
| `cannot find symbol` when compiling probe | `javac` cannot see original internal class or patch source path is wrong | Check `--module-path mods`, `--patch-module demo.library=patch-src`, and package path |
| `IllegalAccessError` at runtime | Bytecode generated under different access context than runtime; wrong class/module or changed API | Use matching patch and module access config at compile/run when needed, read stack trace |
| `ClassNotFoundException`/`NoClassDefFoundError` | Patch class or dependency cannot be found/loaded in runtime graph/class loader | Check patch output, module path, and runtime dependencies |
| `NoSuchMethodError` | Patch class changed signature compared to compiled consumer | Compare binary signatures with `javap`, recompile, or fix patch compatibility |
| Running from IDE differs from terminal | IDE uses different JDK, module graph, or working directory | Check JVM args, compiler args, toolchain, and module output in the IDE |
| Patched run succeeds yet release JAR is wrong | Test patch included in real artifact or build mixes outputs | Keep test/patch directories separate; inspect artifact contents before release |

### 14.1. Command-based verification checklist

After compiling the sample project:

~~~sh
java --module-path mods -m demo.app/demo.app.Main
java --module-path mods --patch-module demo.library=patch-classes -m demo.app/demo.app.Main
java --module-path mods -m demo.app/demo.app.Main
~~~

Expected three lines from the three separate runs:

~~~text
original
patched
original
~~~

If it does not match:

1. `javac -version` and `java -version`: do they match the appropriate target JDK version?
2. Do `mods/demo.library/module-info.class` and `mods/demo.library/demo/library/api/Greeting.class` exist?
3. Does `patch-classes/demo/library/api/Greeting.class` have the updated patch version?
4. Was `--patch-module` passed to **the java command on the second run**?
5. Is the working directory the exact location containing `mods` and `patch-classes`?
6. Is another patch JAR/directory shadowing the class being tested?
7. Was the test run with `-m demo.app/demo.app.Main` to select the intended named module?

Isolating each change with **a single test condition** helps distinguish errors caused by patch code from errors caused by the module graph, paths, or caches.

## 15. Misconceptions to Avoid

**"Patching means directly modifying the original JAR file."** No. The patching mechanism changes what content is seen during class lookup in the configured environment; if the run command omits the patch, the original is still used.

**"If patch classes are on disk, java automatically uses them."** No. You must explicitly pass `--patch-module module=path` to the runtime (or an equivalent configuration mechanism of the runtime environment).

**"Patching only at runtime is enough to compile tests accessing package-private members."** No. Test compilation must also be configured properly so `javac` knows which module the tests belong to.

**"Patching automatically changes requires and exports."** No. The main module's descriptor still dictates the module graph/public surface; separate permission-relaxing options may be needed per test scenario.

**"--patch-module can create a module with any arbitrary name."** No. The target module must have an identity and be found/resolved in the appropriate environment.

**"Patching can completely replace dependency management."** No. Patching is only a controlled override/augmentation mechanism; dependency versions, API compatibility, and artifact publishing still must be managed.

**"A class in the same spelled package name is guaranteed package-private access."** No. In JPMS applications, runtime package/module identity and how classes are loaded matter greatly. Injecting test code into the module itself via patching differs from creating an identically named package in the unnamed module.

## 16. Practice Exercises

### Exercise 1 — Distinguishing compile-time patch and runtime patch

Compile the `Greeting` patch using `javac --patch-module`. Run `demo.app` twice: first without a runtime patch, second with the runtime patch. Explain why only the second run prints `patched`.

### Exercise 2 — White-box tests and module boundaries

Compile/run `WhiteBoxProbe` as in section 7 to access `Secret.token()`. Then try writing another module with `import demo.library.internal.Secret;` without editing the module descriptor. Predict why `Secret` still does not become public API: the package is unexported, and the class remains package-private.

### Exercise 3 — Patch JAR

Package `patch-classes` into `patches/library-patch.jar`; inspect contents with `jar --list --file`. Use that JAR as the patch path instead of the directory. Verify the application still prints `patched`, while the unpatched command again prints `original`.

### Exercise 4 — Binary compatibility

Change the signature of `Greeting.message()` in the patch to `Greeting.message(String value)` without keeping the old overload. Compile the patch without recompiling the application module. Predict the likelihood of `NoSuchMethodError` when the application runs with the patch, then restore the compatible signature. Perform this exercise in the test project since the consumer bytecode was generated against the original API.

### Exercise 5 — Safe testing workflow

Suppose a unit test needs to see a package-private method of a library module. Describe the steps: creating separate patch sources, compiling the right module, running tests with the patch, verifying output, and excluding the patch from production artifacts. Explain when adding `--add-reads` or `--add-opens` has a practical reason and when it is unnecessary.

## 17. Decision Checklist for Whether to Use --patch-module

Before using it, verify:

- **Purpose**: white-box test, diagnosing a class, or compatibility testing in a controlled environment.
- **Target module**: which named module, where is it located, and is it resolved at runtime?
- **Patch scope**: which classes/resources are added or replaced? Are there duplicate names or stale artifacts?
- **Paths**: does the patch path point to the package tree root, matching the OS and working directory?
- **Two phases**: do both `javac` and `java` need configuration? Does the build tool/IDE pass them properly to each process?
- **Access permissions**: are current `requires`, `exports`, and `opens` sufficient for the test? Are you accidentally broadening permissions in the production environment?
- **Compatibility**: do bytecode signatures and behavior match the compiled consumer?
- **Verification**: does baseline → patched → baseline demonstrate an effect strictly within scope?
- **Isolation**: are patch classes/JARs kept outside main outputs and release artifacts?
- **Removal**: does removing the JVM/compiler patch option restore the original behavior?

For JPMS applications, **`--patch-module` is a tool for selective intervention into the contents of an existing module**. Treat it as a capability for testing and diagnostics with concrete evidence, not a substitute for proper public API design, dependency configuration, or standard module publishing.

## 18. Official Documentation for Reference

- Oracle Java SE 17, *The javac Command*, **Patching Modules** section: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- Oracle Java SE 17, *The java Command*, describing `--patch-module`, `--add-reads`, `--add-exports`, `--add-opens`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Java Platform Module System, JEP 261: https://openjdk.org/jeps/261

When discrepancies arise across IDEs, JDK versions, or module launcher invocations, inspect the **actual compiler/runtime commands** and the documentation corresponding to the JDK in use.