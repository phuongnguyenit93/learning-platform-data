# Troubleshooting Incorrect Module Path Errors in Java

The module path is where Java looks for compiled modules, such as modules in an output directory or modular JARs. When the module path is incorrect, the compiler or JVM may fail to find a module declared in `module-info.java`, pick up the wrong version of a module, or find the module but not be allowed to access the required package.

To fix this properly, you need to distinguish three things: finding the module, allowing the module to read its dependency, and having the required package exported by that module. A correct path only solves the step of locating the module; the `requires` and `exports` declarations still need to be right.

This article uses Java 17 or later and an example with two independent modules. The commands were run on Amazon Corretto 17.0.15+6-LTS on Windows.

## 1. What is the module path?

Since Java 9, the Java Platform Module System (JPMS) organizes applications into modules. Each module has a name and can have a `module-info.java` descriptor file. This file declares which modules it depends on and which packages it exposes to other modules.

Example:

~~~java
module com.example.app {
    requires com.example.greeter;
}
~~~

The `com.example.app` application declares that it requires the `com.example.greeter` module. At compile time or runtime, Java must find that module on the module path or among the built-in JDK modules.

The module path can contain:

- Modular JAR: a JAR file with `module-info.class` at the root directory.
- Exploded module: a compiled directory with `module-info.class` at the root and packages underneath.
- Automatic module: a library JAR without `module-info.class` that is placed on the module path. The module name is taken from `Automatic-Module-Name` in the manifest if present, or derived from the JAR filename.

A directory containing multiple modules is typically organized as follows:

~~~text
mods/
├── com.example.greeter/
│   ├── module-info.class
│   └── com/
│       └── example/
│           └── greeter/
│               └── Greeter.class
└── com.example.app/
    ├── module-info.class
    └── com/
        └── example/
            └── app/
                └── Main.class
~~~

Here, `mods` is the module path directory. Each subdirectory is an exploded module. If the modules are packaged into JARs, a `lib` directory can contain multiple modular JARs:

~~~text
lib/
├── com.example.greeter.jar
└── com.example.app.jar
~~~

The filesystem path and the module name are two different values. The module name is declared in `module-info.java` or derived for an automatic module; the path only tells Java where to look for the files/modules.

## 2. Distinguishing the different path types

This is the most common source of confusion:

| Option | What is it used to find? | When to use? |
|---|---|---|
| `--module-path` or `-p` | Compiled modules, modular JARs, automatic modules | Compiling and running modular applications |
| `--module-source-path` | Source code of one or more modules | Compiling multiple modules from a source tree |
| `--class-path`, `-classpath` or `-cp` | Classes and JARs on the classpath, belonging to the unnamed module | Classic applications/libraries that are not named modules |
| `--source-path` | Source code following the package hierarchy | Compiling regular source or a single module |
| `--upgrade-module-path` | Replacement versions for certain JDK modules | Special cases for upgrading system modules |
| `--patch-module` | Additional content patched into an existing module | Testing or patching modules in specialized scenarios |

Do not use `--module-path` to point to a source directory containing `module-info.java` and expect the compiler to automatically find all sources. When compiling multiple modules, use `--module-source-path`. `--module-path` is where to look for modules that can already be used as dependencies.

Example of two different directories:

~~~text
project/
├── src/       # module source path
│   ├── com.example.greeter/
│   └── com.example.app/
├── mods/      # compiled module path
│   ├── com.example.greeter/
│   └── com.example.app/
└── lib/       # modular JAR path
~~~

The compile command uses `src` and writes output into `mods`. The run command uses `mods` or `lib`. Passing `src` to `--module-path` is a path-type mistake, even if the directory exists.

## 3. Proper module source structure

With `--module-source-path src`, each module lives in its own directory named after the module. `module-info.java` is at the root of the module directory; package sources sit underneath following the package hierarchy.

~~~text
project/
└── src/
    ├── com.example.greeter/
    │   ├── module-info.java
    │   └── com/
    │       └── example/
    │           └── greeter/
    │               └── Greeter.java
    └── com.example.app/
        ├── module-info.java
        └── com/
            └── example/
                └── app/
                    └── Main.java
~~~

Contents of `src/com.example.greeter/module-info.java`:

~~~java
module com.example.greeter {
    exports com.example.greeter;
}
~~~

Contents of `src/com.example.greeter/com/example/greeter/Greeter.java`:

~~~java
package com.example.greeter;

public final class Greeter {
    private Greeter() { }

    public static String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Contents of `src/com.example.app/module-info.java`:

~~~java
module com.example.app {
    requires com.example.greeter;
}
~~~

Contents of `src/com.example.app/com/example/app/Main.java`:

~~~java
package com.example.app;

import com.example.greeter.Greeter;

public final class Main {
    public static void main(String[] args) {
        System.out.println(
            Greeter.greet(args.length == 0 ? "module path" : args[0])
        );
    }
}
~~~

The name `com.example.greeter` in `module-info.java` must match the module name that other modules declare in `requires`. The package name `com.example.greeter` is a separate concept, even though this example intentionally gives them the same name. A module can contain multiple packages, and a module name does not have to match any package name.

## 4. Compiling multiple modules with javac

Open a terminal in the `project` directory and run:

~~~bash
javac --module-source-path src -d mods -m com.example.greeter,com.example.app
~~~

Meaning of the arguments:

- `--module-source-path src`: where the module sources are located.
- `-d mods`: output directory for class files.
- `-m` or `--module`: list of modules to compile.

`javac` reads the `module-info.java` files, resolves module dependencies, and creates the module hierarchy in `mods`. With the example structure, the result contains `mods/com.example.greeter` and `mods/com.example.app`.

Run the application module:

~~~bash
java --module-path mods --module com.example.app/com.example.app.Main
~~~

You can use the short form:

~~~bash
java -p mods -m com.example.app/com.example.app.Main
~~~

Output:

~~~text
Hello, module path!
~~~

If the module is packaged into a modular JAR and has a main class declared in its descriptor, you can run it using only the module name. The example in section 8 uses `jar --main-class` to declare the entry point.

### 4.1. Errors when omitting the module path

If a compiled application requires a module outside the JDK, but the compiler or JVM is not given the location of that module, dependency resolution will fail. For example:

~~~text
error: module not found: com.example.greeter
~~~

or at runtime:

~~~text
Error occurred during initialization of boot layer
java.lang.module.FindException: Module com.example.greeter not found
~~~

How to fix:

1. Identify where the compiled dependency module is located.
2. Verify that the directory has `module-info.class` in the right place or contains a valid modular JAR.
3. Pass the parent directory containing the modules or the JAR directory to `--module-path`.
4. Ensure the module name in `requires` matches the actual module name.
5. Place `--module-path` before `--module` in the run command for readability and to avoid confusion with program arguments.

For example, if the dependency is in `mods`, the run command needs `--module-path mods`. If the modular JAR is in `lib`, use `--module-path lib`.

## 5. Compiling multiple modules with different source paths

`--module-source-path` can accept a pattern for a uniform module structure or separate paths per module. For a small number of modules, a simple pattern form is usually easier to maintain:

~~~bash
javac --module-source-path src -d mods -m com.example.greeter,com.example.app
~~~

If the source tree has an extra `src/main/java` level inside each module:

~~~text
src/
├── com.example.greeter/
│   └── src/main/java/
│       ├── module-info.java
│       └── com/example/greeter/Greeter.java
└── com.example.app/
    └── src/main/java/
        ├── module-info.java
        └── com/example/app/Main.java
~~~

You can use a pattern matching that structure:

~~~bash
javac --module-source-path "*/src/main/java" -d mods -m com.example.greeter,com.example.app
~~~

The pattern must accurately match the position of the module directory and package hierarchy. If sources sit directly under `src/<module>/`, do not add `/src/main/java` to the pattern. When compiling multiple modules, the specified source files must belong to one of the declared module source paths.

For a single module or non-modular code, `--source-path` may be more appropriate. Do not try to use a single `--source-path` package hierarchy for multiple named modules; that case requires `--module-source-path`.

## 6. Module name, JAR filename, and path

These three values are often confused:

- Module name: the value in `module-info.java`, e.g. `com.example.greeter`.
- JAR filename: the filename on disk, e.g. `greeter-library-1.2.jar`.
- Module path: the location containing the JAR, e.g. `lib/`.

For a modular JAR, the module name is read from the module descriptor inside the JAR. Therefore, you do not need to rename the JAR to match `requires`, but you must ensure the descriptor is correct.

For an automatic module, the name can be taken from the manifest:

~~~text
Automatic-Module-Name: com.example.legacy
~~~

If the manifest does not have `Automatic-Module-Name`, Java derives the name from the JAR filename. This derivation can change when the filename or version suffix changes. For libraries used long-term on the module path, prefer a stable automatic module name provided by the publisher or choose a version that already includes a module descriptor.

Check the module name inside a JAR:

~~~bash
jar --describe-module --file lib/greeter-library-1.2.jar
~~~

Example output of a modular JAR:

~~~text
com.example.app jar:file:///.../com.example.app.jar!/module-info.class
requires com.example.greeter
requires java.base mandated
contains com.example.app
main-class com.example.app.Main
~~~

If the displayed name differs from `requires` in your application, fix the module descriptor or choose the right JAR version.

## 7. Module found but package is not accessible

The module path may already be correct, yet compilation still reports:

~~~text
error: package com.example.greeter is not visible
(package com.example.greeter is declared in module com.example.greeter,
which does not export it)
~~~

This is an export error, not a module location error. In the module providing the API, the package must be exported:

~~~java
module com.example.greeter {
    exports com.example.greeter;
}
~~~

`exports` allows modules that read this module to access public types in that package. If a module has the right `requires` but the package is not exported, the compiler still rejects the import.

Distinguish these three directives:

| Directive | Effect |
|---|---|
| `requires module.name` | The current module reads the dependency module |
| `exports package.name` | Exposes the package's public API to modules that read it |
| `opens package.name` | Allows deep reflection into the package at runtime |

`opens` does not replace `exports` for normal imports and compilation. If a framework uses reflection to access private fields/constructors, `opens` may be needed for the corresponding package. If the error is `InaccessibleObjectException`, review reflective access permissions rather than changing the module path.

You can restrict a package to a specific module only:

~~~java
module com.example.greeter {
    exports com.example.greeter.api to com.example.app;
}
~~~

In this case, only the `com.example.app` module can access the `com.example.greeter.api` package through a valid module graph.

## 8. Packaging and running modular JARs

After compiling, you can package each module. From the `project` directory:

~~~bash
mkdir lib
jar --create --file lib/com.example.greeter.jar -C mods/com.example.greeter .
jar --create --file lib/com.example.app.jar --main-class com.example.app.Main -C mods/com.example.app .
~~~

The first command packages the library module. The second packages the application and records the main class in the modular JAR's module descriptor.

Check the descriptor:

~~~bash
jar --describe-module --file lib/com.example.app.jar
~~~

Run the application using the directory containing both JARs:

~~~bash
java --module-path lib --module com.example.app
~~~

Output:

~~~text
Hello, module path!
~~~

If the application JAR has a main class but the dependency JAR is missing from `lib`, the JVM still cannot resolve the required module. `--module-path` must include all required module dependencies, or the dependencies must be available in the JDK's system modules.

You can pass a single JAR directly as a module path element, but when there are multiple dependencies, using a `lib` directory makes management and review easier.

## 9. Classpath and module path are not interchangeable

The classpath places classes and JARs into the unnamed module. The module path places named modules or automatic modules into the module graph.

For example, consider a library without `module-info.class`:

- If placed on the classpath, it belongs to the unnamed module.
- If placed on the module path, it is treated as an automatic module and gets a module name derived from the filename or taken from `Automatic-Module-Name`.

If `module-info.java` has:

~~~java
module com.example.app {
    requires com.example.legacy;
}
~~~

then the `com.example.legacy` dependency must be found as a module on the module path. Placing that JAR only on the classpath will not satisfy `requires`.

If you need to integrate legacy code located on the classpath, you can temporarily add readability using `--add-reads`:

~~~bash
javac --add-reads com.example.app=ALL-UNNAMED ...
~~~

~~~bash
java --add-reads com.example.app=ALL-UNNAMED ...
~~~

This is a compatibility measure for special situations. For dependencies used regularly, you should move the JAR onto the module path so it has a stable module name, or keep the application on the classpath if the project does not yet need JPMS.

Note when using `java -jar`: the specified JAR becomes the sole source of user classes, and other classpath settings are ignored. If running a modular application, use `--module-path` and `--module`; if running a non-modular application, configure the manifest/classpath according to your packaging approach.

## 10. Understanding module resolution: requires, readability, and exports

The module system resolves dependencies into a readability graph. When module A declares `requires B`, A reads B. If B declares `requires transitive C`, any module that reads B can also read C under transitive rules.

Three checks to perform when a dependency error occurs:

1. Is module B found on the module path or in system modules?
2. Does module A declare `requires B` and can the dependency graph be resolved?
3. Is the package containing the API exported by B to A?

Some related directives:

~~~java
module com.example.api {
    requires java.logging;
    requires transitive com.example.model;
    requires static com.example.optional;
    exports com.example.api;
    opens com.example.api.internal;
    uses com.example.spi.Plugin;
}
~~~

- `requires transitive`: the module uses types from that dependency in its public API and wants client modules to read that dependency through the graph.
- `requires static`: the dependency is needed at compile time but may be optional at runtime.
- `uses`: the module consumes a service via `ServiceLoader`.
- `provides ... with ...`: the module provides an implementation for a service.
- `opens`: allows deep reflection into a package according to the module's policy.

Do not add `requires` randomly just to make errors go away. Read the compiler message to identify which module needs to read which module, then fix the descriptor of the module that owns the dependency.

### 10.1. When to use add-modules, add-reads, and add-exports?

| Option | Meaning | When to use |
|---|---|---|
| `--add-modules` | Adds modules as roots for resolution | Services or extra modules need to be resolved even though they are not direct dependencies |
| `--add-reads` | Adds a readability edge | Integrating legacy code or special test configurations |
| `--add-exports` | Temporarily exports a package to another module | Tools/tests need access to an unexported API |
| `--add-opens` | Opens a package for deep reflection | Frameworks need to access private members at runtime |
| `--patch-module` | Adds or replaces classes inside a module | Testing or patching a module in a controlled way |

Example of adding a root module:

~~~bash
java --add-modules java.sql --module-path mods --module com.example.app/com.example.app.Main
~~~

`--add-modules` does not make the module path magically find a JAR located in the wrong directory. Nor does it replace `requires` when the source code of a named module needs to read a dependency. If a module is not on the module path, fix the path first.

With `--add-exports`, the syntax is `module/package=target-module`. For example:

~~~bash
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED -cp app.jar com.example.Main
~~~

This configures access to internal APIs in special situations; internal APIs can change across JDK versions. Prefer public APIs or update the module descriptor of modules managed by your project.

## 11. Path separators, spaces, and OS differences

The module path can contain multiple path elements. The element separator depends on the operating system:

| Operating System | Separator | Example |
|---|---|---|
| Windows | `;` | `lib/a.jar;lib/b.jar` |
| Linux/macOS | `:` | `lib/a.jar:lib/b.jar` |

Do not confuse the path separator with `/` or `\` used inside a filesystem path.

PowerShell:

~~~powershell
$modulePath = "lib\greeter.jar;lib\logging.jar"
java --module-path $modulePath --module com.example.app/com.example.app.Main
~~~

Linux/macOS:

~~~bash
MODULE_PATH="lib/greeter.jar:lib/logging.jar"
java --module-path "$MODULE_PATH" --module com.example.app/com.example.app.Main
~~~

If a path contains spaces, quote the entire value:

~~~powershell
java --module-path "C:\Java Libraries\mods" --module com.example.app/com.example.app.Main
~~~

~~~bash
java --module-path "/opt/java libraries/mods" --module com.example.app/com.example.app.Main
~~~

A common mistake is copying `:` directly from a Linux command to Windows, or using `;` on Linux. The wrong separator can cause the JVM to treat multiple path elements as a single path.

Windows is usually case-insensitive for filenames, whereas Linux is usually case-sensitive. Keep consistent spelling and casing for module names, package names, directories, and source filenames to avoid commands that work on one machine but fail in CI.

## 12. Inspecting the module path with JDK tools

You can diagnose issues without editing code first.

### 12.1. List observable modules

~~~bash
java --module-path mods --list-modules
~~~

Check whether your application's modules appear in the list. If not, review the module path, module descriptors, and directory structure.

### 12.2. View a module's descriptor

~~~bash
java --module-path mods --describe-module com.example.greeter
~~~

Output for the example module:

~~~text
com.example.greeter
exports com.example.greeter
requires java.base mandated
~~~

If using a modular JAR:

~~~bash
jar --describe-module --file lib/com.example.greeter.jar
~~~

This command helps verify the module name and exported packages in the actual artifact.

### 12.3. Validate the module graph

~~~bash
java --module-path mods --validate-modules
~~~

This command checks for conflicts among observable modules on the module path. On success, it prints nothing. If it fails, read the output to find duplicate module names, split packages, or invalid descriptors.

### 12.4. View dependency resolution order

~~~bash
java --show-module-resolution --module-path mods --module com.example.app/com.example.app.Main
~~~

The output may include many JDK modules due to service binding. Look for lines containing your application and dependency module names:

~~~text
root com.example.app ...
com.example.app requires com.example.greeter ...
~~~

### 12.5. Check dependencies with jdeps

~~~bash
jdeps --module-path lib --check com.example.app
~~~

`jdeps` displays the module descriptor and suggested dependency graph. Use it to detect missing module dependencies or mismatched declarations in modular JARs.

When you need to see in detail where the compiler is looking for files:

~~~bash
javac -verbose --module-path lib ...
~~~

Verbose output helps identify which modules/JARs the compiler is reading. Do not just verify that the compile command succeeds; check that runtime also uses the same module path and dependency versions.

## 13. Common errors and how to handle them

| Message or symptom | Common cause | How to fix |
|---|---|---|
| `module not found: com.example.greeter` | Module is missing from the module path or wrong module name | Check directory/JAR, descriptor, and `--module-path` |
| `FindException: Module ... not found` | Runtime cannot find the dependency | Add the right module/JAR to the module path when running |
| `package ... is not visible` | Module is found, but package is not exported | Add `exports` in the module owning the package |
| `module ... does not read ...` | Missing dependency readability | Declare `requires` for the right module |
| `package ... does not exist` | Wrong package/import or mixing up classpath and module path | Check package declaration, JAR contents, and path type |
| `module not found` even though JAR exists | JAR is not a valid modular/automatic module or derived name differs | Use `jar --describe-module`, check manifest and filename |
| `InvalidModuleDescriptorException` | Invalid `module-info.class` or descriptor | Rebuild JAR, check `module-info.java` and archive structure |
| `ResolutionException` | Conflicting dependency graph, duplicate module names, or split package | Check JAR versions on the module path and package ownership |
| `InaccessibleObjectException` | Framework reflecting into an unopened package | Add scoped `opens` or configure `--add-opens` as required |
| Works in IDE but fails in terminal | IDE and terminal use different JDK, module path, or dependencies | Compare SDK, compiler options, and runtime arguments |
| Works on Windows but fails on Linux | Case sensitivity or path separator differences | Check module/file names and `:` separator |
| Build has `module-info.java` but dependencies do not resolve | Build tool does not place dependencies on the module path or lacks inference | Inspect compiler command and build tool modularity configuration |

## 14. Workflow for troubleshooting module path issues

Follow these steps in order to pinpoint the right error layer:

1. Run `java --version` and `javac --version`; ensure compiler/runtime use the expected JDK.
2. Read the module names in `requires` inside `module-info.java`.
3. Run `jar --describe-module --file path/to/dependency.jar` or `java --module-path path --describe-module module.name`.
4. Confirm whether the dependency is a modular JAR, automatic module, or exploded module.
5. Verify that the module path directory contains the right modules or modular JARs.
6. Use `--module-source-path` for multi-module sources and `--module-path` for compiled modules.
7. Check `requires` and `exports` of each involved module.
8. Run `java --validate-modules` and `jdeps --module-path ... --check ...`.
9. Run the application with `--show-module-resolution` to inspect the runtime module graph.
10. Compare compile/run commands across IDE, Gradle/Maven, and terminal; look for differing dependencies or options.

When a build tool generates the command line for you, enable verbose logging. With Gradle:

~~~bash
./gradlew compileJava --info
~~~

With Maven:

~~~bash
mvn -X -DskipTests compile
~~~

Look for `--module-path`, `--module-source-path`, `--class-path`, and dependency JARs in the logs. Check whether the build tool is using a different JAR version than the IDE. If the module path is passed through an environment variable such as `JDK_JAVA_OPTIONS`, check that environment variable as well because the launcher prepends its options to the command line.

## 15. Checklist before concluding the issue is fixed

- [ ] Confirmed the JDK used for compilation and runtime.
- [ ] Confirmed the module name in `module-info.java`.
- [ ] `module-info.java` is at the root of each module source directory.
- [ ] Source tree matches `--module-source-path`.
- [ ] Module output has `module-info.class` at the root of each module.
- [ ] Module path points to the directory containing modules or modular JARs.
- [ ] `requires` declares the right dependencies.
- [ ] Required packages are exported with `exports`.
- [ ] Distinguished `--module-path`, `--module-source-path`, and `--class-path`.
- [ ] Checked path separators and quoting for paths containing spaces.
- [ ] No duplicate module names or unintended split packages.
- [ ] `java --validate-modules` runs cleanly.
- [ ] `jdeps --check` reports no unresolved dependency issues.
- [ ] Application runs from terminal/CI using the intended module path.

## 16. Summary

`--module-path` specifies where Java looks for compiled modules; `--module-source-path` specifies where `javac` looks for multi-module sources; `--class-path` serves code on the classpath and the unnamed module. When compiling multiple modules, organize sources in a module hierarchy, use `--module-source-path`, and write output to a module hierarchy directory.

A module dependency only works when the module is found, the graph has the appropriate `requires`, and the API package is exported. Use `jar --describe-module`, `java --describe-module`, `java --validate-modules`, `--show-module-resolution`, and `jdeps --check` to determine whether the error lies in the path, descriptor, or package accessibility. After fixing, verify both compile time and runtime on the same dependency set.

References:

- [The javac Command — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [The java Command — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [JEP 261 — Module System](https://openjdk.org/jeps/261)
- [java.lang.module — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/package-summary.html)
- [ModuleDescriptor — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleDescriptor.html)
- [The jar Command — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html)
- [The jdeps Command — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html)
