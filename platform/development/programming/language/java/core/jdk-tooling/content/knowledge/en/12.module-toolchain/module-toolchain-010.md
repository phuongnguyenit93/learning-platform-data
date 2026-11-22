# Inspecting the Module Graph in Java

## 1. What is a module graph?

In the Java Platform Module System (JPMS), a module graph is a graph that describes modules and the readability relationships between them. Each module is a node; a `requires` directive in `module-info.java` creates a relationship from the module declaring the dependency to the required module.

Example:

~~~text
com.example.app
       |
       | requires
       v
com.example.base
       |
       | requires (mandated)
       v
java.base
~~~

In this diagram, `com.example.app` reads `com.example.base` because it declares `requires com.example.base;`. Both the base and app modules read `java.base` by default under JPMS rules.

The module graph helps answer the following questions:

- Which modules does the application need to compile and run?
- Which `requires` relationships are direct, and which are propagated through `requires transitive`?
- Which modules are being resolved from the module path?
- Are there any missing modules, duplicate names, or package conflicts?
- What set of modules can be used to build a compact runtime image?
- Which JDK modules or internal APIs does a legacy library depend on?

It is important to distinguish the **module graph** from the classpath. The classpath locates classes and JARs in the unnamed module; the module graph represents named modules, descriptors, readability, and JPMS encapsulation rules.

## 2. Module resolution and readability

When launching a modular application, the Java launcher determines the set of root modules, then resolves the required dependencies according to the directives in the module descriptors.

Key rules:

- The main module specified with `-m` or `--module` is a root module.
- `--add-modules` adds modules to the root set to be resolved.
- `requires` requires the current module to read the named module.
- `requires transitive` propagates readability to modules that depend on the required module.
- `requires static` is required at compile time but may be optional at runtime.
- `java.base` is implicitly read by every module; declaring `requires java.base` is unnecessary.
- Service binding may add service provider modules when startup or linking enables the appropriate service resolution mechanism.

A module may be found on the module path and still not be resolved if it is neither in the root set nor pulled in as a dependency from the root set. Therefore, the list of observable modules and the set of modules actually resolved are two different concepts.

The resolution process also checks the consistency of the module graph, including module names, required dependencies, exported packages, and conflicts under JPMS rules.

## 3. A two-module example for observing the graph

Create the project structure:

~~~text
module-graph-demo/
├── src/
│   ├── com.example.base/
│   │   ├── module-info.java
│   │   └── com/example/base/Base.java
│   └── com.example.app/
│       ├── module-info.java
│       └── com/example/app/Main.java
└── mods/
~~~

Base module, file `src/com.example.base/module-info.java`:

~~~java
module com.example.base {
    exports com.example.base;
}
~~~

File `src/com.example.base/com/example/base/Base.java`:

~~~java
package com.example.base;

public class Base {
    public static String value() {
        return "base";
    }
}
~~~

App module, file `src/com.example.app/module-info.java`:

~~~java
module com.example.app {
    requires com.example.base;
}
~~~

File `src/com.example.app/com/example/app/Main.java`:

~~~java
package com.example.app;

import com.example.base.Base;

public class Main {
    public static void main(String[] args) {
        System.out.println(Base.value());
    }
}
~~~

Compile both modules with JDK 17 or later:

~~~bash
mkdir -p mods
javac --release 17 --module-source-path src -d mods --module com.example.base,com.example.app
~~~

Output tree:

~~~text
mods/
├── com.example.base/
│   ├── module-info.class
│   └── com/example/base/Base.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
~~~

Run the application module:

~~~bash
java --module-path mods -m com.example.app/com.example.app.Main
~~~

Stdout:

~~~text
base
~~~

The minimal module graph for this example has the edge `com.example.app → com.example.base` and the default edges to `java.base`. The following examples use this same structure.

## 4. Inspecting the module graph at startup with `--show-module-resolution`

The `--show-module-resolution` option instructs the Java launcher to print information about the modules resolved during startup:

~~~bash
java --show-module-resolution --module-path mods -m com.example.app/com.example.app.Main
~~~

For the example above, the key lines look like:

~~~text
root com.example.app file:/.../mods/com.example.app/
com.example.app requires com.example.base file:/.../mods/com.example.base/
base
~~~

Actual output may also list many system modules and `binds` relationships caused by service binding. The number of lines depends on the JDK version, the root set, and any service providers that can be resolved.

Meaning of common line types:

- `root`: a module added directly to the root set.
- `requires`: a module resolved because another module declared a dependency on it.
- `binds`: a module added through service provider binding.

Use this option when you need to know which modules the JVM actually resolves and where they are located. It is especially useful when an application runs on a development machine but fails in a packaged environment or runtime image.

On PowerShell, you can filter for lines related to the application modules:

~~~powershell
java --show-module-resolution --module-path mods -m com.example.app/com.example.app.Main 2>&1 | Select-String "root com.example.app|com.example.app requires|com.example.base"
~~~

On Linux/macOS:

~~~bash
java --show-module-resolution --module-path mods -m com.example.app/com.example.app.Main 2>&1 | grep -E "root com.example.app|com.example.app requires|com.example.base"
~~~

This is diagnostic output; do not treat it as a stable dependency list without verifying the module graph with a static analysis tool.

## 5. Checking the module graph with `jdeps --check`

`jdeps` is the dependency analysis tool in the JDK. For named modules, `--check` compares the declared module descriptor against the dependencies inferred from bytecode.

Run:

~~~bash
jdeps --module-path mods --check com.example.app
~~~

The output contains sections similar to:

~~~text
com.example.app
  [Module descriptor]
    requires com.example.base;
    requires mandated java.base;
  [Suggested module descriptor for com.example.app]
    requires com.example.base;
    requires mandated java.base;
  [Transitive reduced graph for com.example.app]
    requires com.example.base;
    requires mandated java.base;
~~~

Meaning of the three sections:

- **Module descriptor:** the dependencies declared in `module-info.java`.
- **Suggested module descriptor:** the dependencies that bytecode analysis indicates the module may need to declare.
- **Transitive reduced graph:** the graph after removing readability edges already implied through `requires transitive` relationships.

`jdeps --check` can also point out unused qualified exports. If a descriptor declares multiple `exports package to ...` directives, check the warnings to see which packages are not used by the target modules.

Static analysis results depend on the bytecode and the provided module path. It cannot infer every dependency loaded dynamically via reflection, class names constructed from strings, or external configuration.

## 6. Listing module dependencies

`jdeps` provides multiple levels of dependency views. Specify the module path and the root module:

~~~bash
# List module dependencies
jdeps --module-path mods --module com.example.app --list-deps

# List the reduced graph
jdeps --module-path mods --module com.example.app --list-reduced-deps

# Print the module list in CSV format
jdeps --module-path mods --module com.example.app --print-module-deps
~~~

With the two-module example, the output looks like:

~~~text
com.example.base
java.base
~~~

The `--print-module-deps` command prints a comma-separated list, for example:

~~~text
com.example.base,java.base
~~~

Distinguishing the options:

| Option | Result |
|---|---|
| `--list-deps` | Lists the analyzed module dependencies, including dependencies inferred during analysis. |
| `--list-reduced-deps` | Lists dependencies after removing readability edges implied by `requires transitive`. |
| `--print-module-deps` | Prints the reduced list in comma-separated format, suitable as input for `jlink --add-modules`. |

In large graphs, the reduced list can be significantly shorter because a module can read another module through transitive edges. When you need to see the full relationships, use `--list-deps`; when determining root modules for a runtime image, `--print-module-deps` is usually more convenient.

## 7. Exporting the graph to DOT for visualization

To generate graph files that can be viewed with Graphviz, use `--dot-output`:

~~~bash
jdeps --module-path mods --module com.example.app --dot-output graph-out
~~~

The tool creates DOT files in the specified directory, typically including a file for each module and an overview file `summary.dot`. For the example, the module file has edges like:

~~~dot
digraph "com.example.app" {
    "com.example.app" -> "com.example.base (com.example.base)";
    "com.example.app" -> "java.io (java.base)";
    "com.example.app" -> "java.lang (java.base)";
}
~~~

DOT files represent dependencies found in bytecode; an edge can point to a package inside the module containing that package. Therefore, detailed graph files may show packages such as `java.io` and `java.lang`, while `summary.dot` summarizes at the module level.

If Graphviz is installed, you can convert DOT to SVG:

~~~bash
dot -Tsvg graph-out/summary.dot -o module-graph.svg
~~~

Or generate PNG:

~~~bash
dot -Tpng graph-out/summary.dot -o module-graph.png
~~~

Graphviz is a separate tool and is not bundled with the JDK. If Graphviz is not installed, DOT files are still readable text and can be fed into other visualization tools.

Use the summary graph to view module-to-module relationships. Use the detailed graphs when you need to trace which package or class introduces a dependency.

## 8. Inspecting observable modules and descriptors

The Java launcher provides several options to inspect modules on the module path and their descriptor information.

List observable modules:

~~~bash
java --module-path mods --list-modules
~~~

Describe a specific module:

~~~bash
java --module-path mods --describe-module com.example.app
~~~

For the app module, the main information will look similar to:

~~~text
com.example.app
requires java.base mandated
requires com.example.base
contains com.example.app
~~~

`--list-modules` is useful for confirming that the module path is configured and the launcher sees the modules. `--describe-module` shows the module's declared `requires`, `exports`, `opens`, `uses`, `provides`, and contained packages, depending on the module.

You can inspect the descriptor of a modular JAR using `jar`:

~~~bash
jar --describe-module --file app.jar
~~~

For compiled modules in a directory, use `java --describe-module` with the corresponding module path. Do not infer a module name solely from the JAR filename; read the module descriptor or use the describe tool.

## 9. Checking for errors and conflicts with `--validate-modules`

The `--validate-modules` option instructs the launcher to validate all observable modules and then exit:

~~~bash
java --module-path mods --validate-modules
~~~

When all modules are valid, the command typically exits with code 0 and prints no error messages. If there is a conflict or an invalid descriptor, the launcher prints diagnostics and returns a non-zero exit code.

Issues that can be detected:

- Two modules with the same name across module path entries.
- A required module that does not exist.
- Package conflicts or split packages between named modules.
- Invalid descriptors or dependency relationships.
- Modules that cannot be resolved under JPMS rules.

`--validate-modules` checks the set of observable modules along the current module path. It does not replace running the application or testing runtime behavior. An application can still fail at runtime due to dynamically loaded dependencies, missing configuration files, or incorrect program logic.

Use it as a module path verification step before running or building a runtime image.

## 10. Testing launch options with `--dry-run`

`--dry-run` instructs the Java launcher to create the VM and load the main class without invoking the `main` method:

~~~bash
java --module-path mods --dry-run -m com.example.app/com.example.app.Main
~~~

This command is useful for confirming:

- Whether the module name and main class are valid.
- Whether the module path has all required modules.
- Whether the module graph can be resolved.
- Whether the launcher/JVM options are accepted.

Because the `main` method is not executed, the command does not print `base` in the example. If VM initialization or loading the main class fails, the launcher still reports an error.

`--dry-run` differs from `--validate-modules`:

| Option | Purpose |
|---|---|
| `--validate-modules` | Validates all observable modules and exits. |
| `--dry-run` | Attempts to create the VM and load the main class with the actual launch configuration, without executing `main`. |
| `--show-module-resolution` | Prints details of the modules resolved during startup. |

You can combine dry run with module resolution:

~~~bash
java --show-module-resolution --dry-run --module-path mods -m com.example.app/com.example.app.Main
~~~

This is a quick way to verify a launch configuration before running an application that has side effects.

## 11. From module graph to runtime image with `jlink`

`jlink` builds a runtime image containing the application modules and the required platform modules. The module graph determines the set of modules resolved and included in the image.

First, obtain the module dependency list from `jdeps`:

~~~bash
jdeps --module-path mods --module com.example.app --print-module-deps
~~~

Then use the application module as the root so `jlink` resolves transitive dependencies automatically:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --launcher app=com.example.app/com.example.app.Main --output runtime-image
~~~

On Windows PowerShell, the module path separator is a semicolon:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --launcher app=com.example.app/com.example.app.Main --output runtime-image
~~~

Run the runtime image launcher:

~~~bash
./runtime-image/bin/app
~~~

On Windows:

~~~powershell
.\runtime-image\bin\app.bat
~~~

Stdout:

~~~text
base
~~~

You can use the list from `jdeps --print-module-deps` as the root list when you want to control the module set:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.base,java.base --output runtime-image
~~~

However, in real applications, using the application module as the root usually allows `jlink` to resolve the dependency graph according to the descriptors. Do not copy package or class lists into `--add-modules`; this option takes module names.

## 12. Analyzing dependencies of non-modular JARs

A legacy JAR without `module-info.class` can still be analyzed with `jdeps`. This is a useful step before migrating a library to JPMS.

List the module dependencies of a JAR:

~~~bash
jdeps --multi-release 17 --print-module-deps lib/legacy-library.jar
~~~

If you need to generate a sample module descriptor:

~~~bash
jdeps --multi-release 17 --generate-module-info generated-modules lib/legacy-library.jar
~~~

The tool creates a directory containing a suggested `module-info.java` based on static dependencies. Review and edit the descriptor before using it in production, because bytecode analysis cannot fully capture API design intent, reflection dependencies, or service configuration.

If the library is an open module, you can use `--generate-open-module`. For multi-release JARs, select the appropriate version with `--multi-release` to analyze the corresponding bytecode.

For dependencies loaded via reflection or class names read from configuration, inspect them manually and add the required modules. Do not use `--ignore-missing-deps` just to make a report look clean; understand and resolve missing dependencies instead.

## 13. Finding missing dependencies and JDK internal APIs

A module graph may resolve, yet a library may still reference classes not present on the module path. `jdeps` helps find these cases:

~~~bash
jdeps --module-path mods --missing-deps app.jar
~~~

For JARs or classpath directories, provide the appropriate dependency classpath so the results reflect the actual build/runtime environment.

To find dependencies on JDK internal APIs:

~~~bash
jdeps --jdk-internals app.jar
~~~

Internal APIs are not stable public APIs and may be encapsulated or changed across Java versions. When you see findings, prefer replacing them with standard APIs. If you cannot replace them immediately, review the warnings and constrain the supported runtime versions.

Related options:

- `--api-only` analyzes only dependencies appearing in public/protected signatures of public classes.
- `--recursive` recursively analyzes runtime dependencies.
- `--require module.name` filters dependencies by module name.
- `--package package.name` filters dependencies by package.
- `--ignore-missing-deps` ignores missing dependency warnings; use only when there is a clear reason.

## 14. Adjusting the root set and module universe

The module graph can change depending on the root modules and the set of modules the runtime is allowed to observe.

| Option | Effect |
|---|---|
| `--add-modules` | Adds one or more modules to the root set. `ALL-DEFAULT`, `ALL-SYSTEM`, or `ALL-MODULE-PATH` can be used depending on the goal. |
| `--limit-modules` | Limits the set of observable modules during resolution. |
| `--upgrade-module-path` | Provides replacement modules for upgradeable modules in the runtime image. |
| `--module-path` | Specifies where to locate modular JARs or exploded modules. |
| `jlink`'s `--bind-services` | Includes service provider modules and their dependencies during linking. |

Example of adding an optional module to the root set:

~~~bash
java --module-path mods --add-modules com.example.base -m com.example.app/com.example.app.Main
~~~

Example of limiting the module universe:

~~~bash
java --limit-modules java.base,com.example.base,com.example.app --module-path mods -m com.example.app/com.example.app.Main
~~~

Use `--limit-modules` only when you already know all modules required by the application. Limiting too strictly can make a dependency or provider unobservable and cause resolution to fail.

If the application uses `ServiceLoader`, check both `uses` and `provides` in the module descriptors. When building a runtime image, consider `jlink --bind-services` to include the required provider modules in the image.

## 15. Module graph verification workflow in CI

A pipeline can run the following steps after compiling the modules:

~~~bash
# 1. Check module descriptors and dependency graph
jdeps --module-path mods --check com.example.app

# 2. List module dependencies
jdeps --module-path mods --module com.example.app --list-deps

# 3. Generate the root module list for a runtime image
jdeps --module-path mods --module com.example.app --print-module-deps

# 4. Validate all observable modules
java --module-path mods --validate-modules

# 5. Verify that the launch configuration can load the main class
java --module-path mods --dry-run -m com.example.app/com.example.app.Main

# 6. Run the application and observe module resolution when needed
java --show-module-resolution --module-path mods -m com.example.app/com.example.app.Main
~~~

In CI, you should:

- Pin the JDK/toolchain and module path.
- Build from a clean output directory to avoid stale class files.
- Save `jdeps` reports or DOT graphs as artifacts when dependency review is needed.
- Treat changes in `module-info.java` as API/dependency contract changes.
- Run tests on the runtime image if the product is distributed using `jlink`.
- Avoid automatically ignoring missing dependencies or internal API warnings.
- Verify service binding if the application uses `ServiceLoader`.

Not every project needs to save DOT graphs on every build. For small pipelines, `jdeps --check`, `--validate-modules`, and `--dry-run` are usually sufficient; export DOT only when reviewing or investigating complex relationships.

## 16. Common errors when inspecting the module graph

| Symptom | Common cause | Resolution |
|---|---|---|
| `FindException: Module ... not found` | The module is not on the module path or the module name is wrong. | Check `--module-path`, `module-info.java`, and the module name with `--describe-module`. |
| `ResolutionException` | A dependency cannot be resolved or the module graph has a conflict. | Run `--validate-modules`, `jdeps --check`, and inspect `--show-module-resolution`. |
| `package ... is not visible` | The providing module has not exported the package or the calling module does not read that module. | Check `exports` and `requires`. |
| `Package ... is declared in module ...` or split package | The same package appears in multiple incompatible named modules. | Consolidate the package into one module or fix the module structure. |
| `jdeps --check` suggests a different descriptor | The descriptor declares fewer or more dependencies than the analyzed bytecode. | Read the suggested descriptor, verify static dependencies, and intentionally update `requires`. |
| `jdeps --missing-deps` reports missing classes | Missing JAR/module on the analysis path or a dynamically loaded dependency. | Add the right module/JAR and check dynamic loading points. |
| `java --dry-run` succeeds but actual execution fails | The error occurs inside `main`, class initialization, or runtime work. | Run the program and read the stack trace; dry run does not execute `main`. |
| `--show-module-resolution` prints too many lines | Large root set or many service providers bound. | Filter output for the modules under investigation; check `--add-modules` and service binding. |
| `jlink` reports missing modules | Incomplete root modules or module path. | Use `jdeps --print-module-deps`, check `--module-path`, and run `jlink --verbose`. |
| Application runs on full JDK but fails in runtime image | The image is missing modules/providers or runtime configuration differs from development. | Inspect the graph, consider `--bind-services`, and run tests on the generated image. |

## 17. Module graph inspection checklist

- Every named module has a valid module descriptor and a unique name.
- `requires`, `requires transitive`, and `requires static` directives accurately reflect dependencies.
- Packages needed across modules are exported with the proper scope.
- The module path contains the correct modular JARs or exploded modules.
- `jdeps --check` shows no misdeclared dependencies or unexpected unused qualified exports.
- `jdeps --list-deps` and `--list-reduced-deps` have been reviewed for the intended purpose.
- `jdeps --missing-deps` shows no missing required dependencies.
- `java --validate-modules` completes successfully.
- `java --dry-run` loads the module and main class.
- `--show-module-resolution` confirms modules are resolved from the expected sources.
- Service providers are verified if the application uses `ServiceLoader`.
- `jlink` builds the runtime image successfully and the image runs on the target platform.

When inspecting the module graph, start with `jdeps --check` to evaluate descriptors and static dependencies, use `--show-module-resolution` to see the launcher's actual resolution choices, and then verify the module path with `--validate-modules` and `--dry-run`. If you need a visual view of relationships or want to build a runtime image, export DOT with `jdeps --dot-output` and use the verified dependency list as input for `jlink`.