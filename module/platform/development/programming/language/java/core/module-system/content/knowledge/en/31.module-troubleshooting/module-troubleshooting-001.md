# ModuleNotFoundException and Wrong Module Path

In the Java Platform Module System (JPMS), a common error when compiling or running a modular application is **"module not found"**: the program requires a named module, but the tool cannot find that module in the module sources under consideration. The error can occur because `--module-path` is wrong, the JAR was placed on the classpath instead of the module path, the name in `requires` differs from the actual module name, or the runtime configuration does not match the compile-time configuration.

**Note on the error name:** `ModuleNotFoundException` is often a descriptive term or a custom exception name defined by a library; it is **not the name of a standard JPMS exception in `java.base`**. In standard Java, when running a modular application you typically see `java.lang.module.FindException` with the message `Module ... not found`. When using `javac`, the message is usually `error: module not found: ...`, not necessarily an exception thrown by the program.

This lesson focuses on how to identify **which module is actually missing, at which stage it is missing, and which path must be fixed**, rather than adding JVM options by guesswork.

## 1. Distinguishing module name, package name, and JAR name

The following three names are not necessarily the same:

    JAR filename: money-utils-2.3.0.jar
    Module name:  com.example.money
    Package:      com.example.money.api

The library's descriptor may declare:

    module com.example.money {
        exports com.example.money.api;
    }

An application that needs this library declares:

    module com.example.app {
        requires com.example.money;
    }

`requires` takes a **module name**, not a JAR filename, Maven artifactId, or package name. The following example is wrong if no module with the exact name `money.utils` exists:

    module com.example.app {
        requires money.utils;
    }

Hyphens in a filename are generally not used directly in a module name; for an automatic module, the JDK has its own name-derivation rules. Always determine the actual name from the descriptor rather than guessing from the artifact filename.

## 2. Does the error occur at compile time or runtime?

| Scenario | Common message | First thing to check |
|---|---|---|
| `javac` cannot find a module in `requires` | `error: module not found: com.example.money` | Compiler module path, module name |
| Java launcher cannot find the root module or a dependency | `java.lang.module.FindException: Module ... not found` | Launcher module path, root module, and dependencies |
| Program calls `ModuleFinder.find(name)` but the module is absent | `Optional.empty()` | Does the finder point to the right directory/JAR? |
| Module exists, but the package is not exported | `package ... is not visible`, or an access error at runtime | `requires`, `exports`, module readability |
| Class not found after the module has been resolved | `ClassNotFoundException` or `NoClassDefFoundError` | Class loader, actual class/package, classpath/module path |

Do not lump all of these together as `ModuleNotFoundException`. For example, `ClassNotFoundException` is about a **class**, whereas `FindException` during resolution is usually about a **module**.

## 3. What is the module path?

The **module path** is the source of modules observable by the compiler, launcher, or `ModuleFinder` API. It can contain:

- A directory containing **modular JARs**.
- A directory containing multiple **exploded modules** (compiled module directories, each having `module-info.class`).
- A direct path to a modular JAR or automatic-module JAR, depending on how the tool is used.
- Multiple locations separated according to the operating system's path separator rules.

Example structure:

    project/
      libs/
        money-utils-2.3.0.jar
      out/
        com.example.app/
          module-info.class
          com/example/app/Main.class

The launch command can be:

    java --module-path "out;libs" -m com.example.app/com.example.app.Main

On **Windows**, the path separator is `;`; on **Linux/macOS**, use `:`:

    java --module-path "out:libs" -m com.example.app/com.example.app.Main

Depending on the operating system and shell, wrap the entire module path in quotes if it contains spaces or separators that the shell might interpret.

`--module-path` (short form `-p`) is **different** from `--class-path` (or `-cp`). JARs placed on the classpath are normally loaded into the unnamed module and do not become named modules that can be referenced with `requires`.

## 4. A working two-module project example

Suppose there are two source modules:

    src/
      com.example.money/
        module-info.java
        com/example/money/api/Money.java
      com.example.app/
        module-info.java
        com/example/app/Main.java

`src/com.example.money/module-info.java`:

    module com.example.money {
        exports com.example.money.api;
    }

`src/com.example.money/com/example/money/api/Money.java`:

    package com.example.money.api;

    public final class Money {
        private Money() {}

        public static String currency() {
            return "VND";
        }
    }

`src/com.example.app/module-info.java`:

    module com.example.app {
        requires com.example.money;
    }

`src/com.example.app/com/example/app/Main.java`:

    package com.example.app;

    import com.example.money.api.Money;

    public class Main {
        public static void main(String[] args) {
            System.out.println(Money.currency());
        }
    }

Compile the modules from the project directory:

    javac --module-source-path src -d out -m com.example.money,com.example.app

Run the application:

    java --module-path out -m com.example.app/com.example.app.Main

Output:

    VND

Because `out` contains both exploded modules, the Java launcher can find `com.example.app` and its dependency `com.example.money`.

If the launch command uses a wrong path:

    java --module-path wrong-directory -m com.example.app/com.example.app.Main

the launcher cannot find the root module and may report:

    java.lang.module.FindException:
        Module com.example.app not found

If only the app module is provided while the money module is missing, the launcher may report the missing dependent module:

    java.lang.module.FindException:
        Module com.example.money not found, required by com.example.app

Both messages belong to the same group, yet they point to two different places to check: the **root module** or a **dependency**.

## 5. Why does compilation succeed while running fails?

The compiler and the Java launcher are two tools with separate configurations. For example, compilation uses:

    javac --module-path libs -d out ...

but runtime executes:

    java --module-path out -m com.example.app/com.example.app.Main

If `com.example.money` only resides in `libs` and not in `out`, runtime does not have sufficient module sources to resolve the dependency. Having compiled the class files earlier does not make the library appear on the launcher's module path.

Other common mistakes:

- The IDE automatically configures the module path when running inside the IDE.
- A shell script puts only the application JAR onto the runtime path.
- A CI pipeline or Docker image omits a `libs` directory.
- The test runner executes with a different classpath/module path than production.
- Relative paths are used, but the working directory at runtime differs from the working directory at build time.

The fix is to determine the **actual module path of the exact failing process**, rather than only looking at the dependencies declared in the build file.

## 6. Using jar --describe-module to determine the real name

The most important command when suspecting a module name mismatch:

    jar --describe-module --file libs/money-utils-2.3.0.jar

For an explicit modular JAR, the tool describes the descriptor, including the module name, `requires`, `exports`, and other metadata.

If the JAR does not have `module-info.class`, when placed on the module path it can become an **automatic module**. The name of an automatic module is taken from the `Automatic-Module-Name` manifest attribute if present, or derived from the JAR filename according to JDK rules.

Therefore, do not assume:

    requires money.utils;

just because the file is named `money-utils-2.3.0.jar`. Check the name reported by the tool and use that exact name in `requires`.

If an artifact has multiple versions on the module path, check whether they create **duplicate module names** or make module resolution ambiguous. Do not try to fix it by randomly changing `requires` to a package name.

## 7. Module path pointing to the wrong parent/child directory

An exploded modules structure usually looks like:

    out/
      com.example.money/
        module-info.class
        com/example/money/api/Money.class
      com.example.app/
        module-info.class
        com/example/app/Main.class

In this structure, the module path normally points to **`out`**, which contains the module directories:

    java --module-path out -m com.example.app/com.example.app.Main

If you mistakenly point the module path to a subdirectory that is inappropriate for the command being run, the root module or dependencies may not be found as expected.

For JARs placed in:

    libs/
      money-utils-2.3.0.jar
      logging-api.jar

the module path normally points to **`libs`**:

    java --module-path libs ...

Do not assume that the module path option searches recursively through all subdirectories. If the layout has nested levels such as `libs/vendor/...`, pass the exact locations containing the modules to the module path.

## 8. Do not confuse classpath with module path

A configuration error:

    java --module-path out --class-path libs/money-utils-2.3.0.jar -m com.example.app/com.example.app.Main

If `com.example.app` declares `requires com.example.money`, the JAR `money-utils-2.3.0.jar` on the classpath does not satisfy that named module dependency.

The configuration to consider instead:

    java --module-path "out;libs" -m com.example.app/com.example.app.Main

Use `out:libs` on Linux/macOS.

For a legacy non-modularized application, running entirely with the classpath can be valid:

    java -cp "app.jar;libs/*" com.example.app.Main

However, when launching with `-m`, Java uses the module system to resolve named modules. The two models are not always interchangeable simply by swapping `-cp` for `-p`.

## 9. When a JAR does not yet have module-info.java

A legacy JAR placed on the classpath normally belongs to the unnamed module. When moving that same JAR onto the module path, it can be treated as an **automatic module**.

Example:

    libs/
      legacy-money-1.0.jar

Placed on the module path:

    java --module-path "out;libs" -m com.example.app/com.example.app.Main

If the app source declares:

    module com.example.app {
        requires legacy.money;
    }

the name `legacy.money` is only right if the JDK actually assigns that name to the JAR. Use:

    jar --describe-module --file libs/legacy-money-1.0.jar

to check.

Automatic modules help with incremental migration, but they do not solve every issue: duplicate packages across named modules, missing dependencies, artifact versions, or class loaders can still cause separate errors. Whenever possible, provide a stable module name via an explicit descriptor or `Automatic-Module-Name`.

## 10. A module is present but not yet resolved

A module appearing on the module path does not always participate in the runtime module graph.

For example, a plugin module sits in `plugins`, but the application has no static dependency on it and does not include the plugin in the root set. The module can be found on the module path, yet it has not been resolved into the layer the program is using.

Additional root modules can be added in appropriate cases:

    java --module-path "out;plugins" --add-modules com.example.plugin -m com.example.app/com.example.app.Main

`--add-modules` requests that the module be added to the root set of resolution. It does not create a missing module; the `com.example.plugin` module must still exist on the module path or an appropriate module source.

If the plugin is loaded into a **custom module layer**, check `ModuleFinder`, the configuration, and how the layer is defined; fixing only the launcher's module path is not necessarily sufficient for a custom loader.

## 11. JDK diagnostic tools

Several useful commands:

**Inspect a JAR's module descriptor:**

    jar --describe-module --file libs/money-utils-2.3.0.jar

**List modules observable with the path configuration:**

    java --module-path libs --list-modules

**Validate the module path using the launcher's verification capabilities:**

    java --module-path libs --validate-modules

**Display the module resolution process:**

    java --module-path "out;libs" --show-module-resolution -m com.example.app/com.example.app.Main

**Inspect a JAR's dependencies:**

    jdeps --module-path libs --print-module-deps app.jar

In practice, `jdeps` needs the right dependencies for a complete analysis. Do not use an option that ignores missing dependencies and then conclude that all dependencies are satisfied.

In addition, run commands from the **actual working directory of CI or the container**. A relative path like `libs` may be valid on a development machine yet not exist in the runtime image.

## 12. ModuleFinder: finding modules via Java code

If you need to inspect the module path programmatically in Java, use `java.lang.module.ModuleFinder`:

    import java.lang.module.ModuleFinder;
    import java.lang.module.ModuleReference;
    import java.nio.file.Path;
    import java.util.Optional;

    public final class CheckModule {
        public static void main(String[] args) {
            ModuleFinder finder =
                    ModuleFinder.of(Path.of("libs"));

            Optional<ModuleReference> result =
                    finder.find("com.example.money");

            if (result.isEmpty()) {
                System.out.println("Module not found in libs");
                return;
            }

            ModuleReference reference = result.get();
            System.out.println(reference.descriptor().name());
            System.out.println(reference.location());
        }
    }

`find(...)` returns `Optional.empty()` if no module with the requested name is found. It does not throw an exception named `ModuleNotFoundException` merely because the `Optional` is empty.

A finder may throw `FindException` in error situations while finding or reading module content, such as an invalid artifact on the module path. Therefore, distinguish between "no module with this name exists" and "cannot process a module artifact".

`ModuleFinder.of(Path.of("libs"))` searches only in the source you specify; it does not automatically scan all Maven dependencies, every classpath, or all plugin directories of an application.

## 13. FindException, ResolutionException, and package errors

Three distinct error groups:

- `FindException`: failure to find or resolve a module because a required module is not found, or an issue with module content.
- `ResolutionException`: a module configuration cannot be validly resolved, such as incompatible package/readability relationships.
- `LayerInstantiationException`: failure when defining a module layer according to a class loader mapping, potentially involving multiple modules sharing a package on the same class loader.

If the message states `Module com.example.money not found`, focus on the module path and module name.

If the message states that a package appears in both one module and another, the issue may be a **split package** or a module graph conflict; adding to the module path is not a sufficient solution.

If the module exists but a package is not exported to the caller, check `requires`, `exports`, and `opens` depending on the situation. `--add-opens` does not turn a missing module into an existing one.

## 14. Why --add-exports and --add-opens do not fix a missing module

The following options address **access permission** issues:

    --add-reads
    --add-exports
    --add-opens

They do not download JARs from a repository, fix an incorrect relative path, or resolve a nonexistent module name.

Example error:

    java.lang.module.FindException:
        Module com.example.money not found,
        required by com.example.app

Do not attempt to fix it with:

    --add-opens=com.example.money/com.example.money.internal=ALL-UNNAMED

This option assumes `com.example.money` already exists; it only adjusts reflection capability for a package belonging to the source module.

The right order is:

1. Ensure the `com.example.money` artifact exists.
2. Place the right artifact/module onto the module path.
3. Confirm the module name is recognized by the JVM.
4. Resolve the module graph successfully.
5. Only afterward address exports/opens errors if any remain.

## 15. With Maven: checking compile and runtime dependencies

In a Maven project, a dependency may be present in the compile configuration yet absent at runtime because of scope, profiles, or how the distribution is packaged.

Example library dependency:

    <dependency>
      <groupId>com.example</groupId>
      <artifactId>money-utils</artifactId>
      <version>2.3.0</version>
    </dependency>

This dependency does not guarantee that every script launched with `java -m` puts the JAR onto `--module-path`. When running a JAR with a custom command, you must manage the paths to the actual JARs.

Items to check:

- The JDK version used by Maven compiler/test/runtime.
- The actual module name inside the JAR and `requires`.
- The `provided`, `runtime`, and `test` scopes and their impact on the packaged artifact set.
- Whether the distribution-packaging plugin copies all necessary JARs into the runtime directory.
- Whether Maven Surefire/Failsafe runs tests on the classpath or module path and whether that differs from production.

You can inspect Maven's dependency tree in an environment with the appropriate plugin:

    mvn dependency:tree

However, the dependency tree only shows which artifacts Maven resolves; to prove the runtime module path is right, you still need to inspect the actual launcher command or logs of the running Java process.

## 16. With Gradle: separating module dependencies and launcher args

The Gradle Java plugin can infer the module path for sources that have a module descriptor when configured:

    plugins {
        id 'java'
    }

    java {
        modularity.inferModulePath = true
    }

Example dependency:

    dependencies {
        implementation 'com.example:money-utils:2.3.0'
    }

The configuration above is useful during the build, but if deploying with a separate Java script, the script must specify the corresponding module path.

With the Gradle Application plugin, check the main module, main class, and the set of runtime dependencies that the launch task is configured to use. A test task may run with a different configuration than the application task.

Do not assume that enabling `modularity.inferModulePath` will automatically fix a Docker entrypoint or CI shell script that has hardcoded `-p out`.

## 17. Checking relative paths and deployment environments

Many errors lie not in Java source code but in the filesystem:

- The runner is in the wrong working directory.
- Using `;` on Linux/macOS or `:` on Windows.
- The directory name in the script differs from the directory name after building.
- A JAR was omitted when building the container image.
- The JAR file has a different version than the file used at compile time.
- A directory is mounted at a different path.
- Modules are inside an unextracted archive in a form that the launcher does not support as expected.
- A wildcard or environment variable is not expanded by the shell as the author expected.

To troubleshoot, first print the exact path that the deployment process actually uses. Then verify that the directory or JAR exists and contains the right `module-info.class` or an automatic module recognized by the JVM.

When a script uses `--module-path "out:libs"`, confirm that the `out` and `libs` directories are relative to the current working directory, not implicitly relative to the `.jar` file location.

## 18. The case of --limit-modules and system modules

A module may exist in the JDK or on the module path yet be excluded from the observable module set due to limiting configurations.

For example, `--limit-modules` restricts the modules that resolution can observe, depending on the specified module set and dependency closure. If a limiting configuration accidentally excludes a required module, the program can fail with an error that looks just like a missing module.

This can also happen when running a custom runtime image created with `jlink` that omits a needed platform module.

Therefore, if the error involves a JDK module such as `java.sql`, `java.xml`, or another standard module, do not immediately search for a third-party JAR. Check the JDK/runtime image version, the list of actually present modules, and any launcher options that limit modules.

## 19. Short step-by-step diagnostic workflow

When encountering a module not found error, proceed in order:

**Step 1 — Record the exact error.**

Example:

    java.lang.module.FindException:
        Module com.example.money not found,
        required by com.example.app

Record the missing module (`com.example.money`) and the requiring module (`com.example.app`). If the compiler reports `error: module not found`, also record the `javac` command that was run.

**Step 2 — Verify the artifact is actually present.**

Check the JAR/path in the build output, distribution, container, or CI environment.

**Step 3 — Verify the module name.**

Run:

    jar --describe-module --file libs/money-utils-2.3.0.jar

Compare the module name against `requires` and the `-m` option.

**Step 4 — Verify the module path of the exact tool.**

Do not mix up the `javac` command, test JVM, and production JVM. Fix only the module path of the failing process.

**Step 5 — Observe resolution.**

Use:

    java --module-path "out;libs" --show-module-resolution -m com.example.app/com.example.app.Main

Adjust the path separator for your operating system.

**Step 6 — Classify any subsequent error.**

If the error turns into package not visible, split package, missing service provider, or classloader mismatch, handle it according to the new category. Do not keep adding JARs endlessly.

**Step 7 — Re-run with the exact deployment configuration.**

On CI/Docker or in production systems, the final launch command is the proof that the module path configuration has been fixed.

## 20. Common misconceptions

- **Assuming `ModuleNotFoundException` is a standard JPMS exception.** Standard messages are typically `FindException` or the compile error `module not found`; the name `ModuleNotFoundException` may come from another library.
- **Assuming the module name and JAR filename are identical.** You need to read the descriptor or the actual automatic module name.
- **Assuming a JAR on the classpath satisfies `requires`.** Named modules are looked up on the module path, not from the unnamed module of the classpath.
- **Assuming a module on the module path is guaranteed to be resolved.** Resolution depends on root modules, dependencies, and configuration.
- **Assuming compile success guarantees runtime will find the module.** The compiler and launcher can use different paths.
- **Assuming every missing-class error is a missing-module error.** `ClassNotFoundException` is an error at the class/class loader level.
- **Assuming `--add-opens` can fix `FindException: Module not found`.** It is a reflection option and does not supply module content.
- **Assuming the module path scans all subdirectories recursively.** You must pass the exact locations recognized by the tool.
- **Assuming the path separator is identical across all operating systems.** Windows uses a semicolon; Linux/macOS use a colon.
- **Assuming `--list-modules` proves a module is an app dependency.** It helps observe modules, whereas whether the app resolves that module requires checking the module graph.
- **Assuming `--limit-modules` or a custom runtime image can be ignored.** They can affect the set of observable modules.

## Key takeaways

- In standard JPMS, a "module not found" error usually appears via `java.lang.module.FindException` at runtime or the compiler message `error: module not found`.
- `requires` uses the **module name**; confirm it with `jar --describe-module`.
- `--module-path` differs from `--class-path`; a JAR on the classpath does not automatically become a named module.
- Use the right paths for **both compilation and runtime**; check the path separator and working directory.
- Use `java --show-module-resolution`, `java --validate-modules`, and `ModuleFinder` to classify the issue.
- Once the module is found, the next error may be readability, exports/opens, split package, or class loading; re-diagnose based on the new message.

A reliable approach is to verify **the module name**, **the artifact**, **its location**, **the module graph**, and **the exact failing process**, in that order. When the module path is configured consistently, "module not found" errors can usually be resolved without widening package access permissions or modifying unrelated code.