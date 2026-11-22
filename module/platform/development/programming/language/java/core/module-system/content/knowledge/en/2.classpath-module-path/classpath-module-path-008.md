# Troubleshooting Errors When Mixing Classpath and Module Path

When a Java application uses both traditional libraries via the **classpath** and the **Java Platform Module System (JPMS)** via the **module path**, errors often appear at compile time, at startup, or when accessing a class via reflection. This guide walks through reading error messages, identifying which class/module is actually loaded, and choosing the lowest-risk fix on Java 9 and later.

## 1. Understand Both Paths Before Troubleshooting

| Concept | Classpath (`--class-path` or `-cp`) | Module path (`--module-path` or `-p`) |
| --- | --- | --- |
| Unit seen by the JVM | Classes belonging to the **unnamed module** of the corresponding class loader | Named modules with `module-info.class`; JARs without a descriptor can become an **automatic module** |
| Dependency declaration | No `requires` needed | Named modules use `requires module.name;`; the module must also be **resolved** |
| Access rules | No internal `exports` boundaries between classpath JARs | Has **readability** rules (which module reads which) and **exports** rules (which packages are publicly usable) |
| Reflection into non-public members | Depends on Java/reflection access rights and the target's module mechanism | Adds the requirement of **opens** or `--add-opens` for deep reflection |
| Primary launch form | `java -cp ... com.example.Main` | `java -p ... -m module.name/com.example.Main` |

A JAR moved from the classpath to the module path **no longer carries the same access mechanism**. A JAR with a descriptor becomes a named module; an ordinary JAR on the module path typically becomes an automatic module with a name derived from the manifest or file name. Conversely, when a JAR with `module-info.class` is placed on the classpath, its classes operate under classpath rules and the descriptor does not govern modules as it does on the module path.

Three questions must be answered in order:

1. **Resolution:** Has the module containing the needed class been found and included in the module configuration at compile/run time?
2. **Readability:** Can the calling module read the module that provides the class?
3. **Accessibility:** Is the package `exports`-ed for normal access, or `opens`-ed for deep reflection?

A class that exists in a JAR can still be unusable if any of these three conditions is not satisfied.

## 2. Quick Diagnostic Workflow

**Step 1 — Determine at which stage the error occurs.** Record the full `javac` or `java` command, the JDK version, the first stack trace, and the execution method (IDE, Maven, Gradle, command line). Do not look only at the final message line.

```bash
java -version
javac -version
```

**Step 2 — Identify the application entry point.** A command with `-m module.name/com.example.Main` runs a named module. A command with `-cp ... com.example.Main` runs main via the classpath. Both `-p` and `-cp` can be specified together, but **specifying both does not mean all modules/JARs automatically see one another**.

**Step 3 — Confirm what kind of module the JAR is treated as.**

```bash
jar --describe-module --file libs/example-lib.jar
```

Output showing a descriptor and `requires`/`exports` indicates a modular JAR. If it reports an automatic module or derived automatic module, record the exact module name displayed by the tool; do not guess from the file name. Inspect inside the JAR when needed:

```bash
jar --list --file libs/example-lib.jar
```

**Step 4 — Observe which modules are actually resolved.**

```bash
java --show-module-resolution --module-path mods -m com.example.app/com.example.app.Main
java --validate-modules --module-path mods
java --list-modules
```

`--show-module-resolution` helps show the root module set and the dependencies selected at startup. `--validate-modules` helps detect certain conflicts on the module path. `--list-modules` lists system/observable modules seen by the launcher under the given options; it does not replace reading the resolution of the actual application launch command.

**Step 5 — Check where a class/module is loaded from.** If duplicate JARs are suspected, check the build's dependency tree and use class-loading logs on Java 9+:

```bash
java -Xlog:class+load=info --module-path mods -m com.example.app/com.example.app.Main
```

Search the suspect class name in the log to see the actual loading source. Filter the log when the application is large.

## 3. Error Recognition and Resolution Table

| Typical symptom | Cause to check | Preferred fix |
| --- | --- | --- |
| `module not found: foo.bar` during `javac` | `requires foo.bar` is declared, but no matching module is on the compile module path, or the module name does not match | Place the right module/JAR on `--module-path` and verify the name with `jar --describe-module` |
| `java.lang.module.FindException: Module foo.bar not found` | Module is missing at runtime, even though it may have been present at compile time | Align the runtime module path with actual artifacts; inspect the graph with `--show-module-resolution` |
| `package ... is not visible`; "module ... does not read ..." | Missing `requires`, missing `--add-modules`, or missing readability relationship | Identify the source module and add a valid `requires`; for classpath code use `--add-modules` when needed |
| `package ... is not visible`; "does not export ..." | The module is read, but the package is not exported | Use an API from an `exports`-ed package; update the descriptor if you own the module |
| `IllegalAccessError` mentioning `does not export` | The class exists at runtime, but access violates JPMS rules | Align the descriptor, JAR version, and runtime paths; consider `--add-exports` only for compatibility |
| `InaccessibleObjectException`: "does not opens ..." | A framework uses deep reflection into a package that is not open | Use `opens`/`open module` in a module you own, or scoped `--add-opens` |
| `ClassNotFoundException` / `NoClassDefFoundError` | The class or a transitive dependency is not in the runtime configuration; a module may not be resolved | Cross-check runtime classpath/module path, dependency tree, and class-load logs |
| `ResolutionException`; "reads package ... from both ..." | Split package: two modules provide the same package to a reading module | Remove duplicates, upgrade/align libraries, or restructure packages |
| `FindException`; "Unable to derive module descriptor" | Legacy JAR is unsuitable as an automatic module (e.g., problematic package names or dependencies) | Check `jar --describe-module`, JAR contents, and an appropriate library version |
| `NoClassDefFoundError: ...` occurs only in IDE/tests | Classpath/module path of the IDE, runner, or tests differs from the standard launch command | Compare the actual launch command and test runner configuration, not just the pom/build script |

Do not jump to conclusions from the exception name alone. The phrases **"module X does not read Y"**, **"does not export P to X"**, and **"does not opens P to X"** in the message pinpoint the blocked step.

## 4. Minimal Example: Two Named Modules Running Properly

Suppose we have the following structure:

```text
src/
  com.example.greeter/
    module-info.java
    com/example/greeter/Greeter.java
  com.example.app/
    module-info.java
    com/example/app/Main.java
```

File `src/com.example.greeter/module-info.java`:

```java
module com.example.greeter {
    exports com.example.greeter;
}
```

File `src/com.example.greeter/com/example/greeter/Greeter.java`:

```java
package com.example.greeter;

public final class Greeter {
    private Greeter() {}
    public static String greet() {
        return "Hello JPMS";
    }
}
```

File `src/com.example.app/module-info.java`:

```java
module com.example.app {
    requires com.example.greeter;
}
```

File `src/com.example.app/com/example/app/Main.java`:

```java
package com.example.app;

import com.example.greeter.Greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.greet());
    }
}
```

Compile and run from the project root directory:

```bash
javac -d mods/com.example.greeter src/com.example.greeter/module-info.java src/com.example.greeter/com/example/greeter/Greeter.java
javac --module-path mods -d mods/com.example.app src/com.example.app/module-info.java src/com.example.app/com/example/app/Main.java
java --module-path mods -m com.example.app/com.example.app.Main
```

Expected output:

```text
Hello JPMS
```

Here `mods` is a directory containing two exploded module directories. If `--module-path mods` is omitted when compiling the application, `requires com.example.greeter;` cannot be resolved and raises `module not found`. If the same option is omitted at runtime, the launcher cannot find the application module or its dependency.

## 5. Scenario A: A Classpath Program Calling a Module-Path Library

Create a traditional program at `legacy/LegacyMain.java`:

```java
import com.example.greeter.Greeter;

public class LegacyMain {
    public static void main(String[] args) {
        System.out.println(Greeter.greet());
    }
}
```

If the `com.example.greeter` library is in `mods`, adding only `--module-path mods` is usually **not enough** for root-module resolution to select the library module for a main class on the classpath. Specify the module to resolve explicitly at compile time and runtime:

```bash
javac --module-path mods --add-modules com.example.greeter -d out-legacy legacy/LegacyMain.java
java --module-path mods --add-modules com.example.greeter --class-path out-legacy LegacyMain
```

`--add-modules com.example.greeter` puts the library into the root modules set so classes in the unnamed module can use exported packages. If a `does not export` error still occurs, changing `--add-modules` cannot expose a hidden package: check the library module's `exports`.

When running classpath code with multiple JARs:

```bash
# Linux/macOS: separate multiple classpath entries with a colon
java -cp "out-legacy:libs/dependency.jar" LegacyMain

# Windows: use a semicolon
java -cp "out-legacy;libs/dependency.jar" LegacyMain
```

The classpath separator differs across operating systems. Multi-entry `--module-path` also follows the corresponding path separator. The JPMS example above has only a single path entry, so it works across both.

## 6. Scenario B: A Named Module Needs a Legacy Library

Suppose the application has `module-info.java` and needs the library `legacy-util-1.0.jar`, which does not yet declare a module.

**Usually suitable transition approach:** place the legacy JAR on the module path so it becomes an **automatic module** (if the JAR is valid), and obtain the exact module name from:

```bash
jar --describe-module --file libs/legacy-util-1.0.jar
```

If the tool confirms the name `legacy.util`, the application module can declare:

```java
module com.example.app {
    requires com.example.greeter;
    requires legacy.util;
}
```

And place both the application modules and the library JAR on the module path:

```bash
# Illustrate the path portion; separate entries according to the OS
java --module-path "mods;libs/legacy-util-1.0.jar" -m com.example.app/com.example.app.Main
```

The command above uses `;` for Windows; Linux/macOS uses `:`. The name `legacy.util` is only an **example** and must not be put into `requires` before inspecting the actual JAR. An automatic module name derived from the file name can change if the artifact is renamed; for libraries you maintain, adding `Automatic-Module-Name` in the manifest stabilizes the name during the transition. An automatic module does not have the same strict encapsulation as an explicit module and can still suffer from split-package, module-naming, or dependency errors.

**When the library cannot be moved to the module path:** A named module cannot write `requires ALL-UNNAMED;` or `requires jar.on.classpath;` to declare a dependency on the unnamed module. A special compatibility workaround can be used with `--add-reads com.example.app=ALL-UNNAMED`, combined with the classpath containing the legacy JAR, at the required compile/run stages; however, this configuration should be treated as a temporary transition step because it weakens module boundaries and is easily forgotten in IDEs, tests, and production.

## 7. Scenario C: Confusing `exports`, `opens`, and `--add-reads`

Three distinct permissions:

- `requires com.example.lib;`: the named module **reads** module `com.example.lib`; it does not automatically expose all packages of the library.
- `exports com.example.api;`: lets other modules use `public` types in that package under normal access rules. It can be restricted: `exports com.example.internal to com.example.client;`.
- `opens com.example.model;`: allows deep reflection into the package—for example, a framework reading non-public fields/constructors—subject to corresponding access checks. It can be restricted: `opens com.example.model to com.example.framework;`.

For example, a framework on the classpath reflects into package `java.lang` and hits `InaccessibleObjectException`. When compatibility is genuinely required, a temporary launch option is:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp "app.jar" com.example.Main
```

For normal access to a non-exported package, another compatibility mechanism is:

```bash
java --add-exports module.name/com.example.internal=ALL-UNNAMED -cp "app.jar" com.example.Main
```

Do not use `--add-exports` to fix a reflection error that needs `opens`, or use `--add-opens` to fix a module-not-found error. When you own the module source, updating `module-info.java` properly is usually more sustainable. For JDK internals, prefer supported APIs and newer framework versions; compatibility flags may stop being appropriate after a JDK upgrade.

## 8. Scenario D: Duplicate Dependencies or Split Packages

For example, `lib-old.jar` and `lib-new.jar` both contain package `com.vendor.util`; when both are named/automatic modules on the module path and a module reads both, JPMS can reject resolution due to a **split package**. Similarly, a JAR declared on both the classpath and module path can cause confusion over which source loads a class or which dependency version is used.

Trace the issue in order:

1. Run `jar --describe-module --file ...` on suspect JARs to learn their module names.
2. Run `jar --list --file ...` to check which packages appear in each JAR.
3. Inspect the dependency tree and actual launch paths, especially when a framework constructs paths automatically.
4. Keep one consistent dependency version; remove duplicate JARs or adjust versions in the build tool.
5. If two modules genuinely share a required package, intentionally refactor/shade or use JPMS-ready library versions; do not just add `--add-reads`.

The classpath selects classes by search order, whereas JPMS checks packages/modules at resolution time. Thus, the same set of JARs can "work on the classpath" yet fail when moved to the module path; this is a signal to fix dependencies, not merely tweak JVM flags.

## 9. Scenario E: Works on CLI, Fails in IDE, Tests, or Packaging

Do not infer runtime configuration from successful compilation. Inspect the **actual Java command** generated by the IDE, JUnit/test plugin, Maven, or Gradle:

- Is the main class launched with `-cp` or `-m`? Was a named module accidentally launched as a classpath program?
- Are `--module-path`, `--class-path`, `--add-modules`, and `--add-opens` all present in both the **run command and the test command**?
- Is there a JDK version mismatch across terminal, IDE, CI, and production?
- Do tests use `--patch-module` or a separate classpath causing test classes and application modules to sit in different configurations?
- Do the actual runtime JARs match the exact versions and module names used at compile time?

`jlink` images contain only the modules included in the image and their appropriate dependencies; when packaging, verify that required modules are included in the image. For directly launched applications, check `--show-module-resolution` to see the exact graph chosen by the launcher.

## 10. Choosing a Solution by Project Architecture

| Current architecture | Preferred configuration | Points to verify |
| --- | --- | --- |
| Both application and libraries are named modules | `--module-path`; complete `requires` and `exports` | Module names, graph, split packages |
| Main on classpath, libraries on module path | `-cp` for main, `-p` for libraries, `--add-modules` when libraries are not yet resolved | Required packages must be exported |
| Main is a named module, legacy JAR libraries | Move eligible JARs to automatic modules; then declare `requires` | Automatic module names, transitive dependencies, split packages |
| Fully legacy application with no JPMS need yet | Keep a unified classpath configuration during transition | Avoid accidentally placing part of dependencies on `-p` |
| Framework uses reflection into a named module | `opens` required packages, optionally qualified to target | Reflection rights differ from `public` type import rights |

**Recommended fix order:** correct artifact and version → correct classpath/module path → correct module name and root modules → correct `requires`/readability → correct `exports`/`opens` → only last, consider compatibility flags. Change only one cause at a time with evidence from the error message or module-resolution log.

## 11. Practical Command Set to Keep When Investigating

```bash
# Current JDK in use
java -version
javac -version

# Modular JAR or automatic module? What is the exact module name?
jar --describe-module --file libs/example-lib.jar

# Check files inside the JAR
jar --list --file libs/example-lib.jar

# Any obvious module-path conflicts?
java --validate-modules --module-path mods

# Which modules does the launcher resolve for the entry point?
java --show-module-resolution --module-path mods -m com.example.app/com.example.app.Main

# Which class is loaded and from where? (Java 9+)
java -Xlog:class+load=info --module-path mods -m com.example.app/com.example.app.Main

# Analyze dependencies of a JAR to aid modularization
jdeps --recursive libs/example-lib.jar
```

Substitute file/module names and paths according to your real project. If `jdeps` reports a missing dependency, supply the necessary library paths and rerun to get the complete dependency picture; `jdeps` performs static dependency analysis and cannot prove every interaction made via reflection.

## 12. Self-Check Questions When Encountering a New Error

1. Is the JAR containing the class on the classpath, the module path, or both?
2. When inspected with `jar --describe-module`, what is the actual module name and module kind?
3. Is the target module resolved? If not, do you need `requires`, `-p`, or `--add-modules`?
4. Does the calling module have permission to read the target module?
5. Is the package being imported exported to the calling module?
6. If the error occurs during reflection, is the target package opened to the right module/framework?
7. Are there duplicate JARs, split packages, or configuration differences across compile/runtime/tests?
8. After fixing, will the actual launch command still be valid in the IDE, CI, and deployment artifact?

Once these eight questions are answered using the error message, JAR details, and actual command line, most classpath/module-path mixing errors can be narrowed down to **missing resolution, missing readability, missing exports/opens, or a dependency conflict**.
