# Handling FindException, ResolutionException, Missing Dependencies, and Package Conflicts in JPMS

## 1. What Step Is Module Resolution?

In the Java Platform Module System (JPMS), placing JARs on the **module path** is not enough for a program to run. Java must locate modules by name, build the set of selected modules, resolve \`requires\`/service-binding relationships, and verify module graph consistency. Only after the configuration is valid does the runtime define modules/layers and start the application.

This process can fail before \`main()\` is even invoked:

- **\`java.lang.module.FindException\`**: the module finder cannot locate a required module or cannot read/recognize a module artifact in certain cases.
- **\`java.lang.module.ResolutionException\`**: an issue occurs while the resolver builds the module graph or detects an inconsistent module configuration, such as conflicting package visibility.
- **Missing dependency**: a module named in \`requires\` is absent from observable modules; this commonly surfaces as \`FindException\`, not always a separate exception type.
- **Package conflict (split package)**: the same package belongs to multiple resolved modules under invalid conditions; this may be detected at compilation/resolution or when defining a layer, depending on the situation.

These errors differ from **\`ClassNotFoundException\`**, **\`NoClassDefFoundError\`**, or **\`IllegalAccessError\`**, which arise later when loading/linking/using classes. Do not use a single catch-all workaround for every error.

## 2. Conceptual Module Resolution Workflow

\`\`\`text
Module path / system modules
          |
          v
ModuleFinder identifies module artifacts and descriptors
          |
          v
Root modules (--module / --add-modules / layer roots)
          |
          v
Resolve requires and service binding when applicable
          |
          v
Validate graph: module existence, readability, exports, conflicts
          |
          v
Configuration -> ModuleLayer -> run main()
\`\`\`

In the command \`java --module-path mods --module app.host/app.Main\`, \`app.host\` is the root module. \`requires\` relationships are traversed to resolve dependencies. A module merely present on the module path but not resolved into the graph does not necessarily participate at runtime.

**First step on error:** read the full message, identify the root module, the requested module, the physical path of the artifact, and the error type; do not guess that simply adding \`--add-modules ALL-MODULE-PATH\` will fix it.

## 3. Java 17+ Example: Missing Module Causing FindException

Create two named modules where \`demo.app\` depends on \`demo.api\`.

Structure:

\`\`\`text
demo/
  src/
    demo.api/
      module-info.java
      api/Message.java
    demo.app/
      module-info.java
      app/Main.java
\`\`\`

\`src/demo.api/module-info.java\`:

\`\`\`java
module demo.api {
    exports api;
}
\`\`\`

\`src/demo.api/api/Message.java\`:

\`\`\`java
package api;

public final class Message {
    private Message() {}

    public static String value() {
        return "JPMS OK";
    }
}
\`\`\`

\`src/demo.app/module-info.java\`:

\`\`\`java
module demo.app {
    requires demo.api;
}
\`\`\`

\`src/demo.app/app/Main.java\`:

\`\`\`java
package app;

import api.Message;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Message.value());
    }
}
\`\`\`

In the \`demo\` directory, on a bash shell with JDK 17+:

\`\`\`bash
javac --module-source-path src -d mods --module demo.api,demo.app
java --module-path mods --module demo.app/app.Main
\`\`\`

Result:

\`\`\`text
JPMS OK
\`\`\`

Now package only the application module and intentionally omit its dependency:

\`\`\`bash
mkdir -p broken
jar --create --file broken/demo.app.jar -C mods/demo.app .
java --module-path broken --module demo.app/app.Main
\`\`\`

The run fails before \`main()\`. Typical message:

\`\`\`text
Error occurred during initialization of boot layer
java.lang.module.FindException: Module demo.api not found, required by demo.app
\`\`\`

The exact message/formatting may depend on the JDK/launcher version, but the core issue is the missing \`demo.api\`. To fix it, put **the proper modular JAR** for \`demo.api\` onto the module path:

\`\`\`bash
jar --create --file broken/demo.api.jar -C mods/demo.api .
java --module-path broken --module demo.app/app.Main
\`\`\`

Output returns to:

\`\`\`text
JPMS OK
\`\`\`

When a module is missing, **do not try to fix it with \`--add-exports\` or \`--add-opens\`**: those two flags control package access permissions and do not create the missing \`demo.api\` artifact.

## 4. Understanding FindException by Root Cause

Causes to separate:

| Category | Symptom | Check | Fix Direction |
| --- | --- | --- | --- |
| Module does not exist on observable module path | \`Module X not found, required by Y\` | \`--module-path\`, actual directories/JARs | Add the artifact with the matching name |
| Module name differs from expected name | \`requires example.api\` but JAR declares \`example.contract\` | \`jar --describe-module\` | Align \`module-info.java\` and module name |
| Artifact is not a valid module | Error reading/parsing \`module-info.class\` or JAR | \`jar --list\`, \`jar --describe-module\` | Rebuild JAR, check bytecode/module descriptor |
| Multiple same-named modules on search path | Module finder/configuration selects wrong artifact | Check module path and how launcher/layer selects finders | Remove duplicates, define a single clear module source |
| Required module is only on the classpath | A named module does not resolve dependencies from the unnamed module as a named module | Compare \`-cp\` and \`--module-path\` | Move dependency onto the proper module path or change design |

\`FindException\` is not synonymous with “JAR file does not exist”: the JAR may exist on disk yet have the wrong module name, not be on the effective module path, or not be visible to \`ModuleFinder\` under the running configuration.

### Verifying the Actual Module Name

\`\`\`bash
jar --describe-module --file path/to/library.jar
\`\`\`

For an explicit modular JAR, the output shows the name from \`module-info.class\`. For a non-modular JAR placed on the module path, Java may treat it as an **automatic module**: its name is derived from \`Automatic-Module-Name\` in the manifest if present, or from the filename per automatic module naming rules. Do not guess names from Maven coordinates; inspect the tool output.

\`jar --list --file path/to/library.jar\` verifies archive structure. If using a multi-release JAR, check compatibility with the target Java version and the corresponding versioned module descriptor.

## 5. ResolutionException: Inconsistent Module Graph

\`ResolutionException\` occurs when module resolution constraints cannot be satisfied. A major scenario is when **two different modules provide the same package that a module reads in a conflicting way**.

Flawed design example:

\`\`\`text
module demo.alpha
  exports shared;
  shared/A.class

module demo.beta
  exports shared;
  shared/B.class

module demo.app
  requires demo.alpha;
  requires demo.beta;
\`\`\`

The application cannot simultaneously read two modules exporting the same package \`shared\` under this configuration. The compiler or resolver will report a package conflict. Do not “fix” this by reordering the module path or hoping the first module wins. **Named modules do not behave like classpath first-match for conflicting package exports.**

Standard solution: use distinct packages, such as \`alpha.shared\` and \`beta.shared\`, or design a common API module and have both providers implement that API from it. If both JARs contain classes of *the same library* in one package, consolidate/organize ownership properly instead of leaving both on the module path haphazardly.

## 6. Package Conflict Example When Two Modules Export the Same Package

This is an *intentionally invalid* example to understand the error; the files are illustrative and cannot compile as a single valid application graph.

\`demo.alpha/module-info.java\`:

\`\`\`java
module demo.alpha {
    exports shared;
}
\`\`\`

\`demo.alpha/shared/Alpha.java\`:

\`\`\`java
package shared;
public final class Alpha {}
\`\`\`

\`demo.beta/module-info.java\`:

\`\`\`java
module demo.beta {
    exports shared;
}
\`\`\`

\`demo.beta/shared/Beta.java\`:

\`\`\`java
package shared;
public final class Beta {}
\`\`\`

\`demo.app/module-info.java\`:

\`\`\`java
module demo.app {
    requires demo.alpha;
    requires demo.beta;
}
\`\`\`

Because module \`demo.app\` reads both \`demo.alpha\` and \`demo.beta\`, package \`shared\` is exported from two different sources. The \`javac\` compiler may report an error like \`module demo.app reads package shared from both demo.alpha and demo.beta\`. When building configurations programmatically or encountering an invalid graph at runtime, the error belongs to resolution/consistency.

**How to fix:** organize package names and module boundaries so a consumer module sees only a single owner for that package. For instance, \`demo.alpha\` exports \`alpha.shared\`, while \`demo.beta\` exports \`beta.shared\`. Renaming packages requires updating sources, imports, metadata, and build artifacts consistently.

### Be Careful with Automatic Modules

Automatic modules typically export all packages and have broad readability. When moving a legacy library to the module path, split packages that survived on the classpath can become resolution conflicts. Inspect package names inside every JAR, not just module names. Avoid using automatic modules as a long-term solution for systems with many package-overlapping dependencies.

## 7. Another Package Error: Same Package Inside a Module Layer

In addition to two modules exporting the same package read by a consumer, there is a constraint when defining modules in class loaders: a single class loader cannot define the same package belonging to two named modules in a layer in ways that violate loader/package mapping rules. \`ModuleLayer.defineModulesWithOneLoader\` and \`defineModulesWithManyLoaders\` impose different constraints on classloader mapping and can detect invalid configurations after resolution. Therefore, when investigating package conflicts, distinguish:

1. **Resolution/readability conflict:** the graph is deemed inconsistent.
2. **Definition/classloader conflict:** the layer configuration cannot be defined with the chosen classloader strategy.
3. **Build/source conflict:** the compiler rejects a \`split package\` or a package exported from multiple sources.
4. **Classpath collision:** multiple JARs in the unnamed module have classes with the same fully qualified name; the classpath typically picks one by loader lookup order, hiding the bug unsafely.

Do not assume that every case where two JARs contain the same package throws exactly \`ResolutionException\`. The outcome depends on the module graph, exports, loader strategy, and checking stage.

## 8. Diagnostic Tools When Resolution Fails

### Step 1: Print the Run Command and Environment

Record the exact \`java\`, \`javac\`/Maven/Gradle command and values:

- JDK version: \`java -version\`.
- Root module: \`--module module.name/main.Class\`.
- Module path: \`--module-path path1:path2\` on Unix; the path separator is \`;\` on Windows.
- \`--add-modules\`, \`--limit-modules\`, \`--patch-module\`, \`--upgrade-module-path\` if present.
- Command-line differences between IDE/tests and distribution.

### Step 2: Inspect the Artifact

\`\`\`bash
jar --describe-module --file dist/your-module.jar
jar --list --file dist/your-module.jar
\`\`\`

Do not put an assumed name in \`requires\` if the descriptor shows a different name. Verify \`module-info.class\` actually exists and targets the right JDK version.

### Step 3: View the Graph Accepted by the Resolver

When **resolution succeeds**, the launcher can print resolution details:

\`\`\`bash
java --show-module-resolution --module-path dist --module app.host/app.Main
\`\`\`

Replace \`app.host/app.Main\` with the actual root. With a failing graph, output may stop at the failure and is not guaranteed to print everything; this is a diagnostic tool, not a fix.

\`jdeps\` helps analyze static dependencies:

\`\`\`bash
jdeps --module-path dist --check app.host
\`\`\`

Note that \`jdeps\` does not detect every dependency loaded dynamically via reflection, \`ServiceLoader\`, or class names read from configuration. When using SPI, test loading real plugins on the module path after building.

### Step 4: Verify the Module Finder and Root Set

If the application creates module layers itself:

\`\`\`java
ModuleFinder finder = ModuleFinder.of(pluginDirectory);
Configuration config = ModuleLayer.boot().configuration()
        .resolve(finder, ModuleFinder.of(), java.util.Set.of("demo.plugin"));
\`\`\`

This is an illustrative snippet inside a method that has a \`Path pluginDirectory\` variable and imports \`java.lang.module.Configuration\`, \`java.lang.module.ModuleFinder\`. \`resolve\` may throw \`FindException\`/\`ResolutionException\` before any module layer is defined. Ensure \`finder\` sees the module with the right name, the parent configuration has required contract modules, and the root set uses module names rather than JAR filenames.

### Step 5: Make the Minimal Change and Re-Test

After identifying the root cause, change only the exact module path, descriptor, or package ownership involved; do not add a pile of flags opening access to every module. Perform a clean build and re-run the production-like command.

## 9. Handling Errors in Code When Creating Module Layers Yourself

When an application supports loading dynamic plugin modules, you can handle resolution errors at the boundary to return clear diagnostics. Example (placed in a class with a valid \`Path pluginDir\`):

\`\`\`java
import java.lang.module.Configuration;
import java.lang.module.FindException;
import java.lang.module.ModuleFinder;
import java.lang.module.ResolutionException;
import java.util.Set;

public final class Resolver {
    public static Configuration resolve(Path pluginDir, String rootName) {
        ModuleFinder finder = ModuleFinder.of(pluginDir);
        Configuration parent = ModuleLayer.boot().configuration();
        try {
            return parent.resolve(finder, ModuleFinder.of(), Set.of(rootName));
        } catch (FindException ex) {
            throw new IllegalArgumentException(
                    "Cannot find module/dependency for " + rootName, ex);
        } catch (ResolutionException ex) {
            throw new IllegalStateException(
                    "Inconsistent module graph for " + rootName, ex);
        }
    }
}
\`\`\`

To compile the snippet above as a standalone class, add \`import java.nio.file.Path;\`. This is an illustrative skeleton, not an end-to-end runnable app; in practice you must define a layer and loader strategy after obtaining \`Configuration\`.

**Note:** Both \`FindException\` and \`ResolutionException\` are unchecked exceptions. Do not catch a generic \`RuntimeException\` and turn it into “plugin missing” by default, as that erases the distinction between module lookup failures, graph conflicts, and other runtime errors. Preserve the cause and log module paths/root names (without logging sensitive data) so operations can act on it.

## 10. Distinguishing from Access and Loading Errors After Resolution

| Error | Typical Stage | Question to Ask |
| --- | --- | --- |
| \`FindException\` | Module lookup / dependency resolution | Is the module visible to the finder? Is the name right? |
| \`ResolutionException\` | Resolver graph validation | Are there split packages, export/readability conflicts, or graph constraints? |
| \`LayerInstantiationException\` | Creating module layer / defining class loaders | Can the loader mapping define this package/module? |
| \`IllegalAccessError\` | Linking/using classes after resolution | Is the package exported to the calling module? |
| \`InaccessibleObjectException\` | Deep reflection at runtime | Is the package appropriately opened? |
| \`ClassNotFoundException\` | Looking up a class by name/classloader | Is the class in the module/artifact and in the right loader/layer? |
| \`NoClassDefFoundError\` | Linking/loading a referenced class | Is the class or its dependency missing or failing initialization? |
| \`ServiceConfigurationError\` | Discovering/instantiating service providers | Are \`uses\`/\`provides\`, provider contract, and resolution/layer right? |

This table is a diagnostic guide, not an absolute rule for every scenario.

\`--add-exports\` alters access to public types in a package, \`--add-opens\` enables deep reflection, and \`--add-reads\` alters module readability. **None of these flags creates a missing module artifact or fixes a split package in the module graph.** These flags should be tightly scoped compatibility measures, not a “turn everything on” tool to hide resolution errors.

## 11. A Practical Scenario: Migrating Libraries from Classpath to Module Path

An application may work on the classpath because JARs are loaded in classpath order. When migrating to JPMS:

1. Identify explicit modules and automatic modules across all JARs.
2. Verify real module names instead of relying on guessed filenames.
3. Detect duplicated packages across JARs, especially \`javax.*\`/\`jakarta.*\` packages, shaded dependencies, and libraries whose artifact names changed.
4. Extract shared APIs into an explicit module; do not let multiple modules own the same API package.
5. If automatic modules exist, gradually replace them with modularized dependencies or adjust packaging to avoid split packages.
6. Run \`jdeps\`, smoke-test \`java --module-path\`, and verify \`ServiceLoader\`/reflection in a real runtime.
7. Ensure the build does not accidentally place an outdated \`module-info.class\` or wrong JAR variant on the module path.

Avoid “fixing” a split package by putting one copy of a library on the classpath and the other on the module path without reviewing class identity and API contracts. That may sidestep an immediate error while creating harder-to-diagnose failures.

## 12. JPMS Troubleshooting Checklist

- [ ] Read the full stack trace and identify the exact exception type.
- [ ] Verify the root module, module path, JDK version, and module names from descriptors.
- [ ] Verify dependencies in \`requires\` are actually observable/resolved.
- [ ] Compare automatic and explicit module names; do not guess from Maven artifactId.
- [ ] Check package ownership and split packages across modules in the same graph.
- [ ] Separate compilation, resolution, layer definition, and runtime class loading.
- [ ] For dynamic layers, confirm \`ModuleFinder\`, parent configuration, and root module set are correct.
- [ ] Do not use \`--add-reads\`, \`--add-exports\`, or \`--add-opens\` as substitutes for missing module artifacts.
- [ ] Perform a clean build and run the real release artifacts on the module path.
- [ ] Write negative tests for missing modules and package conflicts to prevent regressions.

**Conclusion:** \`FindException\` typically points to **finding a module or dependency**, whereas \`ResolutionException\` points to an **inconsistent module graph**. The right fix is to identify roots, module finders, module names, dependency edges, and package ownership, and repair the root cause in the module model or artifacts rather than patching blindly with classpath or access flags.
