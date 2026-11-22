# Guide to Running with the Module Path

## 1. Purpose of this guide

When a Java application uses the Java Platform Module System (JPMS), running the program differs from the familiar approach based solely on the classpath. Instead of placing every JAR on `-cp` and passing a main class name, the application can declare named modules, specify dependencies in `module-info.java`, place artifacts on the module path, and select a main module when starting the JVM.

This guide presents a repeatable workflow from source code to distribution:

1. Identify module names and main class.
2. Compile named modules.
3. Run directly from exploded modules.
4. Package modular JARs.
5. Run from the distribution directory with `--module-path` and `-m`.
6. Inspect the module graph and handle common errors.
7. Document run commands for development, CI, and production environments.

The goal is to help readers understand precisely **what the module path contains, which modules the JVM resolves, and how launch commands should be written**.

## 2. Prerequisites before running

First, confirm the environment meets these requirements:

- A JDK or Java runtime supporting JPMS (Java 9 or later).
- Exact knowledge of the application's target Java version.
- Corresponding modular JARs or directories containing exploded modules.
- A valid main module name and main class.
- Necessary dependencies on the module path or in the runtime image.
- `module-info.class` inside explicit named modules.
- Knowledge of whether the application also uses classpath libraries, plugins, ServiceLoader, or reflection.

Check Java tools:

~~~bash
java -version
javac -version
~~~

View the system modules present in the current runtime:

~~~bash
java --list-modules
~~~

If using a custom runtime image from `jlink`, run verification commands using the `java` executable inside that image, not only the JDK installed on the development machine.

## 3. Distinguishing the module path and classpath

The traditional classpath is a set of directories or JARs containing classes/resources, typically specified with `-cp` or `--class-path`:

~~~bash
java -cp "app.jar:lib/*" com.example.app.Main
~~~

Code on the classpath belongs to the unnamed module of the relevant class loader. The program launches by main class name and does not declare a main module.

The module path contains artifacts that Java can recognize as named modules:

~~~bash
java --module-path dist/mods \
     --module com.example.app/com.example.app.Main
~~~

Equivalent short form:

~~~bash
java -p dist/mods -m com.example.app/com.example.app.Main
~~~

In the command above:

- `-p` or `--module-path`: path where named modules are located.
- `-m` or `--module`: specifies the main module, optionally followed by the main class after `/`.
- `com.example.app`: module name, not necessarily matching the JAR filename.
- `com.example.app.Main`: fully qualified name of the main class in the `app` module.

The JVM starts resolution from root modules and then resolves dependencies following `requires` in descriptors. Just because a JAR sits in the module path directory does not guarantee that JAR is included in the runtime module graph.

## 4. Example structure with two modules

Let's create a very small application consisting of:

- `com.example.greeting`: library module exposing a greeting API.
- `com.example.app`: module containing the main class and reading the greeting module.

Source layout:

~~~text
demo/
  src/
    com.example.greeting/
      module-info.java
      com/example/greeting/api/Greeter.java
    com.example.app/
      module-info.java
      com/example/app/Main.java
  out/
  dist/
~~~

Library descriptor, file `src/com.example.greeting/module-info.java`:

~~~java
module com.example.greeting {
    exports com.example.greeting.api;
}
~~~

Library API, file `Greeter.java`:

~~~java
package com.example.greeting.api;

public final class Greeter {
    private Greeter() {
    }

    public static String sayHello(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Application descriptor, file `src/com.example.app/module-info.java`:

~~~java
module com.example.app {
    requires com.example.greeting;
}
~~~

Main class, file `src/com.example.app/com/example/app/Main.java`:

~~~java
package com.example.app;

import com.example.greeting.api.Greeter;

public final class Main {
    public static void main(String[] args) {
        String name = args.length > 0 ? args[0] : "JPMS";
        System.out.println(Greeter.sayHello(name));
    }
}
~~~

What matters is the relationship between three elements:

- `app` must have `requires com.example.greeting` to read the library module.
- `greeting` must have `exports com.example.greeting.api` so `app` can use the public type.
- The main class must have a valid `public static void main(String[] args)` method for the launcher to start.

## 5. Compiling the two modules from source

From the `demo` directory, use `javac`:

~~~bash
javac --module-source-path src \
      --module com.example.greeting,com.example.app \
      -d out/mods
~~~

Single-line form, convenient for PowerShell or Command Prompt:

~~~text
javac --module-source-path src --module com.example.greeting,com.example.app -d out/mods
~~~

Meaning:

- `--module-source-path src` tells the compiler where multi-module sources reside.
- `--module` / `-m` selects the modules to compile.
- `-d out/mods` writes compiled output into separate per-module directories.

After successful compilation:

~~~text
out/
  mods/
    com.example.greeting/
      module-info.class
      com/example/greeting/api/Greeter.class
    com.example.app/
      module-info.class
      com/example/app/Main.class
~~~

If a module depends on a precompiled modular JAR outside the source tree, add `--module-path` to `javac`. The module source path parameter does not substitute for the module path of precompiled dependencies.

## 6. Running directly from exploded modules

An **exploded module** is a directory containing `module-info.class` and the classes/resources belonging to that module, not yet packaged into a JAR.

With the output above, run:

~~~bash
java --module-path out/mods \
     -m com.example.app/com.example.app.Main
~~~

Expected output:

~~~text
Hello, JPMS!
~~~

Passing an argument to `main`:

~~~bash
java --module-path out/mods \
     -m com.example.app/com.example.app.Main Lan
~~~

Output:

~~~text
Hello, Lan!
~~~

All arguments after `main-module/main-class` in this command are passed into `String[] args` of the main class.

On the module path, `out/mods` is the parent directory containing **individual module subdirectories**. There is no need to list individual `.class` files or packages.

This is a convenient approach when debugging or running locally before creating JARs.

## 7. Packaging into modular JARs

When distributing an application, it is usually best to package each module into its own modular JAR. A JAR counts as an explicit named module when it contains a valid `module-info.class` descriptor.

Create the target directory:

~~~bash
mkdir -p dist/mods
~~~

The command above is for POSIX shells. On PowerShell you can use:

~~~powershell
New-Item -ItemType Directory -Force dist/mods
~~~

Package the library module:

~~~bash
jar --create \
    --file dist/mods/com.example.greeting.jar \
    -C out/mods/com.example.greeting .
~~~

Package the application:

~~~bash
jar --create \
    --file dist/mods/com.example.app.jar \
    --main-class com.example.app.Main \
    -C out/mods/com.example.app .
~~~

The `--main-class` option of `jar` allows recording main class metadata in the modular JAR where supported by the tool and descriptor. However, launch commands that explicitly specify `main-module/main-class` remain easy to understand and independent of how main class metadata was packaged.

Verify the descriptor in the final artifacts:

~~~bash
jar --describe-module --file dist/mods/com.example.app.jar
jar --describe-module --file dist/mods/com.example.greeting.jar
~~~

When checking, ensure the JAR contains the exact module name and `requires`/`exports` directives as in source. Do not guess the module name solely from the JAR filename.

## 8. Running from released modular JARs

Distribution layout:

~~~text
dist/
  mods/
    com.example.app.jar
    com.example.greeting.jar
~~~

Main run command:

~~~bash
java --module-path dist/mods \
     -m com.example.app/com.example.app.Main
~~~

Output:

~~~text
Hello, JPMS!
~~~

The JVM finds `app` and `greeting` from the same module path. `app` is chosen as the root because of `-m`; `greeting` is resolved due to `requires` in `app`'s descriptor.

If the modular JAR has the main class recorded in its descriptor, a shorter form can be used:

~~~bash
java --module-path dist/mods -m com.example.app
~~~

The module-name-only form will fail if the runtime cannot locate valid main class metadata inside the module. Therefore, deployment docs should use the `module/mainclass` form when avoiding reliance on main class metadata.

If your JAR is only a traditional executable JAR with `Main-Class` in its manifest, do not assume running `-m` with an arbitrary module name is valid. Check whether it has `module-info.class`, `Automatic-Module-Name`, or only a classpath manifest.

## 9. Module paths on Linux, macOS, and Windows

A module path can contain multiple elements: directories of modular JARs, exploded modules, or specific JAR files. When multiple elements exist, the separator character depends on the operating system.

| Operating system | Path separator |
|---|---|
| Linux / macOS | Colon `:` |
| Windows | Semicolon `;` |

Example on Linux/macOS:

~~~bash
java --module-path "dist/mods:third-party" \
     -m com.example.app/com.example.app.Main
~~~

Example on Windows PowerShell:

~~~powershell
java --module-path "dist/mods;third-party" -m com.example.app/com.example.app.Main
~~~

If a directory contains spaces, always quote the entire path value:

~~~bash
java --module-path "/opt/My Application/modules" \
     -m com.example.app/com.example.app.Main
~~~

On Windows:

~~~powershell
java --module-path "C:\Program Files\Example\modules" -m com.example.app/com.example.app.Main
~~~

Do not use the POSIX `:` as a path separator on Windows because `:` appears in drive letters such as `C:`.

Relative paths are resolved from the **current working directory**, not automatically from the location of the JAR or `java` executable. This is a common cause of commands working in an IDE yet failing in CI or production.

## 10. Main module, main class, and root modules

With:

~~~bash
java --module-path dist/mods \
     -m com.example.app/com.example.app.Main
~~~

`com.example.app` is the **main module**, and `com.example.app.Main` is the **main class**. A module name can contain dots, yet does not have to match the package containing the main class.

The main module is added to the set of root modules. From there, module resolution follows `requires` dependencies.

Example:

~~~java
module com.example.app {
    requires com.example.greeting;
    requires java.logging;
}
~~~

When running the app, needed modules such as `greeting` and `java.logging` are resolved if observable.

If a provider or additional module is not pulled into the graph via `requires` or service binding, you may need to add roots at launch:

~~~bash
java --module-path dist/mods \
     --add-modules com.example.plugin \
     -m com.example.app/com.example.app.Main
~~~

`--add-modules` specifies additional modules as roots. It does not edit `module-info.class` and does not grant access to internal packages of the added module for every consumer.

Multiple module names can be passed to `--add-modules`, separated by commas. Add only modules truly needed for the application to function; do not blindly add the entire module path for every application.

## 11. When the module path contains third-party libraries

A real-world application often depends on external libraries, such as HTTP clients, JSON, logging, or database drivers.

Before adding them to the module path, inspect the actual JAR:

~~~bash
jar --describe-module --file lib/library.jar
~~~

Three common situations arise:

1. **Explicit named module:** the JAR contains `module-info.class`. This is the clearest case; the descriptor defines `requires`/`exports`/`opens`/`uses`/`provides`.
2. **Automatic module:** the JAR lacks `module-info.class` but is treated as an automatic module by the JVM when placed on the module path. Its name can come from `Automatic-Module-Name` or be derived from the artifact filename.
3. **Classpath library:** the JAR stays on the classpath, belonging to the unnamed module; a named module cannot write `requires` to an unnamed module as a normal named dependency.

An automatic module is helpful as a migration bridge, though it may have an unstable module name if derived from the filename. Prefer artifacts with stable module names and check for split packages.

If the app's `module-info.java` states:

~~~java
module com.example.app {
    requires com.example.json;
}
~~~

then the module path must contain a module identified by the **exact name com.example.json**. Placing `json-lib.jar` on the classpath is not enough for `javac` or the JVM to resolve that `requires`.

## 12. Differences among -jar, -cp, and -m

Three ways of running Java serve different purposes:

~~~bash
# Run a main class on the classpath.
java -cp "app.jar:lib/*" com.example.app.Main
~~~

~~~bash
# Run an executable JAR using manifest metadata.
java -jar app.jar
~~~

~~~bash
# Run a named module from the module path.
java --module-path dist/mods \
     -m com.example.app/com.example.app.Main
~~~

Key points:

- `-jar` selects an executable JAR and uses manifest-based launch mechanics; it does not automatically launch a named module from the module path.
- `-cp` selects the traditional classpath and requires a main class.
- `-m` selects the main module and main class under JPMS.
- When running `-jar`, do not assume any `-cp` passed alongside will be used as in a regular classpath command.
- Replacing `-jar` with `-m` can change how classloaders/resources/services are discovered, so test with actual artifacts.

A module may be packaged as a JAR, yet that does not mean every way of running a JAR is equivalent.

## 13. Properly reading requires and exports relationships

The module path only locates modules. It does not replace module access rules.

Library:

~~~java
module com.example.greeting {
    exports com.example.greeting.api;
}
~~~

Application:

~~~java
module com.example.app {
    requires com.example.greeting;
}
~~~

The consumer must read the providing module. If a class resides in an unexported package, the consumer cannot import/call it normally even if the class is declared `public`.

A typical compile error:

~~~text
package com.example.greeting.internal is not visible
~~~

The proper fix is to check whether the app is mistakenly depending on an implementation package. If you own the library module, consider exposing a stable API via `exports`. If it is a third-party internal package, prefer public APIs over widening access with temporary flags.

Do not apply `--add-exports` to every package just to get past the first error. Define module boundaries and valid dependencies clearly.

## 14. Inspecting the module graph at startup

When an application fails to find a module or behaves unexpectedly, use:

~~~bash
java --show-module-resolution \
     --module-path dist/mods \
     -m com.example.app/com.example.app.Main
~~~

This option displays information about module resolution during that run, helping verify:

- The main module and dependencies that were resolved.
- Dependencies on which modules caused the root graph to expand.
- Whether provider or additional modules were included in the runtime graph.
- Whether unexpected module versions or module sources appeared.

Inspect a JAR's module descriptor:

~~~bash
jar --describe-module \
    --file dist/mods/com.example.app.jar
~~~

Inspect observable modules to the Java runtime given the passed module path:

~~~bash
java --module-path dist/mods \
     --list-modules
~~~

For a specific module:

~~~bash
java --module-path dist/mods \
     --describe-module com.example.app
~~~

`--list-modules` shows observable modules under the launcher configuration, whereas `--show-module-resolution` shows the resolved graph for a specific run. Both serve different purposes.

## 15. Validating modules on the module path

Before running a production application, you can ask the launcher to validate modules:

~~~bash
java --module-path dist/mods \
     --validate-modules
~~~

This command helps detect certain module path problems such as invalid module descriptors or module/package conflicts identifiable by the tool.

For compiled artifacts, use `jdeps` to view module dependencies:

~~~bash
jdeps --check com.example.app \
      --module-path dist/mods
~~~

If a library uses JDK internal APIs, try analyzing:

~~~bash
jdeps --jdk-internals \
      --module-path dist/mods \
      dist/mods/com.example.app.jar
~~~

Keep in mind `jdeps` is a static analysis tool. It does not fully detect modules loaded via reflection, class names in configuration, runtime plugins, or ServiceLoader. Real execution paths must still be tested.

## 16. ServiceLoader and provider modules

If an application uses an SPI, having the provider JAR on the module path is not always enough to ensure the provider is selected and used.

Consumer module declares `uses`:

~~~java
module com.example.app {
    requires com.example.greeting;
    uses com.example.greeting.api.GreetingProvider;
}
~~~

Provider module declares `provides`:

~~~java
module com.example.provider {
    requires com.example.greeting;

    provides com.example.greeting.api.GreetingProvider
        with com.example.provider.DefaultGreetingProvider;
}
~~~

For ServiceLoader to find the implementation, the provider module must exist within the module graph/layer being used and register a valid provider.

When explicitly bringing a provider module into the graph for diagnostics or configuration:

~~~bash
java --module-path dist/mods \
     --add-modules com.example.provider \
     -m com.example.app/com.example.app.Main
~~~

The app does not need to import `DefaultGreetingProvider` directly. The app should depend on the service interface, and the provider implements the service contract.

If using a custom `ModuleLayer`, `ServiceLoader.load(layer, ServiceType.class)` discovers providers in the appropriate layer. Do not assume the thread context class loader can see plugins living in a separate layer.

## 17. Reflection and opens when running on the module path

ORMs, JSON serialization, dependency injection frameworks, or test runners may need deep reflection to invoke non-public constructors or access private fields.

JPMS distinguishes:

- `exports`: allows other code to use public types/members in a package, with appropriate readability.
- `opens`: allows deep reflection for the opened scope.
- `--add-exports`: adds a temporary targeted export.
- `--add-opens`: temporarily opens a package for deep reflection.

Example when you own the module:

~~~java
module com.example.app {
    requires com.example.greeting;
    opens com.example.app.model to com.example.serializer;
}
~~~

Here `com.example.serializer` must be the framework's actual resolved module name. Do not guess the module name solely from an artifact filename.

In a migration scenario, a temporary command might be:

~~~bash
java --module-path dist/mods \
     --add-opens com.example.app/com.example.app.model=ALL-UNNAMED \
     -m com.example.app/com.example.app.Main
~~~

This command makes sense when the caller requiring deep reflection belongs to an unnamed module. `ALL-UNNAMED` is inappropriate if you need to restrict access to a specific named module.

If the error is `InaccessibleObjectException`, check reflection/`opens`. If the error is “package not exported” or `IllegalAccessError` from regular bytecode access, check `requires`/`exports`. Do not use one single flag to solve every module-related error.

## 18. Running applications with legacy libraries on the classpath

During migration, some code may still depend on older libraries placed on the classpath. In that case, the command can combine module path and classpath for **appropriate independent components**:

~~~bash
java --module-path dist/mods \
     --class-path "legacy/*" \
     -m com.example.app/com.example.app.Main
~~~

However, a named module cannot automatically import classes from the unnamed module just by adding `--class-path`. Review the named module's dependency design, or move appropriate libraries onto the module path with valid module names.

Some bridges from classpath code to a named module may need `--add-modules` to pull the named module into the graph. Identify the exact caller and provider before choosing options.

If a project still has many libraries that cannot be modularized, consider keeping the launcher or main application on the classpath during transition while modularizing independent libraries incrementally instead of forcing the whole system onto `-m` immediately.

## 19. Split packages, duplicate module names, and dependency cycles

Structural errors that can surface when moving from classpath to module path:

**Split package:** two different modules contain classes in the same package and cause a conflict in the graph. Fix by merging artifacts belonging to the same logical module or reorganizing packages, not with `--add-exports`.

**Duplicate module name:** multiple distinct JARs declare or derive the same module name. Depending on the module path and how finders locate modules, one artifact may shadow another or fail. Inspect each JAR's module name and distribute only one suitable version.

**Dependency cycle:** two explicit modules `requires` each other. JPMS is not designed to resolve such `requires` cycles in a normal module graph. Break the cycle by extracting an API or inverting a dependency direction.

**Module not found:** the name in `requires` or `-m` does not match the actual module name; the module path directory lacks the right artifact; or the JAR was packaged improperly.

When errors occur, do not edit module descriptors in bulk right away. Determine module names, artifact origins, package ownership, and the `requires` graph first.

## 20. Runtime images from jlink are another distribution form

If you want to bundle a Java runtime with the application rather than relying on a preinstalled JDK, use `jlink` to create a custom runtime image from valid explicit named modules.

Example on Linux/macOS with an appropriate JDK:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:dist/mods" \
  --add-modules com.example.app \
  --launcher demo=com.example.app/com.example.app.Main \
  --output dist/runtime
~~~

Once the image is built:

~~~bash
dist/runtime/bin/demo
~~~

If the application uses service providers, consider `--bind-services` when creating the image, and verify providers are present in the graph/image.

Notes:

- `jlink` is a runtime packaging step, not a replacement for `javac`.
- Automatic modules are not valid explicit-module inputs for direct linking.
- Runtime images are typically tied to the OS/CPU and JDK used to build them.
- A linked image does not automatically contain dynamically loaded plugins or JARs unless incorporated into packaging design.
- Always test on the production image itself using `image/bin/java`, not only the development JDK.

## 21. Writing stable run commands in deployment scripts

Commands containing relative paths depend on the current working directory. If users may invoke scripts from any directory, resolve paths relative to the script's location.

Distribution folder example:

~~~text
distribution/
  bin/
    run.sh
  mods/
    com.example.app.jar
    com.example.greeting.jar
~~~

Contents of `bin/run.sh` on a POSIX shell:

~~~sh
#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
APP_HOME="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"

exec java \
  --module-path "$APP_HOME/mods" \
  -m com.example.app/com.example.app.Main "$@"
~~~

The script derives `APP_HOME` from the script location rather than depending on the caller's working directory. `"$@"` forwards all CLI arguments to the main class.

On Windows PowerShell, the equivalent idea:

~~~powershell
$ErrorActionPreference = "Stop"
$AppHome = Split-Path -Parent $PSScriptRoot
$Modules = Join-Path $AppHome "mods"

& java --module-path $Modules -m com.example.app/com.example.app.Main @args
exit $LASTEXITCODE
~~~

The Windows script should be saved at `distribution/bin/run.ps1` so `$PSScriptRoot` points to the `bin` folder. If a Java runtime is bundled with the product, replace the system `java` invocation with the path to the `java` executable inside that runtime.

In CI and production, document environment variables affecting the JVM, such as `JAVA_HOME`, instead of relying on whatever JDK happens to be on `PATH`.

## 22. Mandatory information to include in a release README

A user-facing module path run guide should cover at minimum:

1. Supported Java/JDK versions.
2. How to extract or install artifacts.
3. The directory containing modular JARs and how to preserve distribution layout.
4. Main module and main class.
5. Run commands on Linux/macOS and Windows.
6. How to pass application arguments.
7. Required environment variables, configuration files, and filesystem permissions.
8. Modules/providers that must be distributed alongside.
9. How to enable module resolution diagnostics.
10. Common errors and fixes.
11. How to run via custom runtime image, if provided.
12. A quick smoke-test command to verify the program works.

Example of a short command block for users:

~~~text
Requirements: Java 17+ and complete dist/mods directory.

Linux/macOS:
  java --module-path dist/mods -m com.example.app/com.example.app.Main

Windows PowerShell:
  java --module-path dist/mods -m com.example.app/com.example.app.Main

Debug:
  java --show-module-resolution --module-path dist/mods -m com.example.app/com.example.app.Main
~~~

This is a documentation structure example. Real projects must substitute actual module names, JDK versions, paths, and configuration details rather than copying `com.example.*` names into production.

## 23. Common startup errors table

| Message / symptom | Cause to inspect | Resolution |
|---|---|---|
| Module com.example.app not found | Main module missing from module path or wrong name | Check folder, `jar --describe-module`, `-m` |
| Module X not found, required by Y | Dependency in `requires` missing or recognized under different name | Supply modular JAR with exact name/version |
| Main class not found | Portion after `/` wrong or class absent from JAR/module | Check package/class and artifact contents |
| Module ... does not export package | Public type in package not exported to caller | Check API, `requires`/`exports` |
| IllegalAccessError | Runtime denies bytecode reference per module/member access rules | Cross-check module graph and descriptors |
| InaccessibleObjectException | Deep reflection into package not `opens`ed | Fix framework or add selective `opens` |
| ClassNotFoundException | Class absent or loaded in different loader/path | Check artifacts, plugins, module layers |
| NoClassDefFoundError | Class needed at runtime unfound or dependency init failed | Inspect root cause and runtime dependencies |
| ServiceConfigurationError | Provider registration, metadata, or service init error | Check `uses`/`provides` and provider module |
| Runs in IDE but fails via script | Different module path, JDK, cwd, or JVM args | Record actual command and standardize launcher |
| Split package / resolution conflict | Two modules/packages cannot coexist in graph | Fix package ownership or artifacts |
| jlink build missing module | Runtime image lacks required dependency/provider | Check `--add-modules`, `--bind-services`, and image |

When diagnosing, prioritize identifying whether the failure lies in **module discovery**, **graph resolution**, **package access permissions**, or **class/resource/service loading**. These problem classes require different fixes.

## 24. Pre-release verification workflow

A practical verification workflow:

1. Build using the JDK/toolchain specified in documentation.
2. Produce the exact modular JARs without accidentally reusing stale files.
3. Inspect module descriptors with `jar --describe-module`.
4. Confirm the module path folder holds all required artifacts.
5. Run `java --module-path ... --validate-modules` for basic checks.
6. Run `java --show-module-resolution ... -m ...` to confirm the graph.
7. Invoke the main class using the exact production command.
8. Test CLI arguments and configuration files.
9. Exercise features using reflection, ServiceLoader, resources, and plugins.
10. Test on Windows/Linux/macOS matching supported platforms.
11. If scripts exist, run from a different directory than the script location to verify path handling.
12. If a custom runtime image exists, run the full test suite using the image's executable.
13. Record the approved startup command and corresponding Java environment.

Do not rely solely on compile success. A modular JAR can compile cleanly yet fail on startup due to runtime dependencies, un-opened packages, or improperly wired service providers.

## 25. Quick operator checklist

- [ ] Appropriate Java runtime version available.
- [ ] Exact main module and main class known.
- [ ] Module path points to the right JAR/exploded modules directory.
- [ ] All dependencies declared with `requires` are discoverable.
- [ ] No module name or package conflicts exist.
- [ ] Application JAR contains `module-info.class` if an explicit module is required.
- [ ] `-m` chosen properly, not confused with `-jar` or `-cp`.
- [ ] Paths are quoted and use the OS's path separator.
- [ ] If providers are used, provider modules are resolved and validly registered.
- [ ] If reflection is used, required packages are selectively `opens`ed.
- [ ] Module graph verified with `--show-module-resolution`.
- [ ] Production script has no unintended dependence on current working directory.
- [ ] Smoke test passed using the exact release artifacts and runtime.

## Conclusion

Running an application with the module path enables the JVM to recognize named modules, start from the main module, and resolve dependencies via `module-info.java`. The core command is:

~~~bash
java --module-path <modules-dir> \
     -m <module-name>/<main-class-name>
~~~

Good deployment documentation must clearly state module names, main class, distribution layout, Java version, per-OS path syntax, and how to inspect module resolution. When troubleshooting errors, distinguish missing modules, wrong readability/exports, un-opened reflection, and dynamically loaded dependencies. This practice keeps launch commands consistent and diagnosable from IDE to CI to production.
