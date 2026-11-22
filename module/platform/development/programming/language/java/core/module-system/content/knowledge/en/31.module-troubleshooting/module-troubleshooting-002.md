# FindException During Module Resolution

In the Java Platform Module System (JPMS), a modular application can only start when Java locates the required modules and builds a valid module graph. If **module lookup** fails, the application may encounter `java.lang.module.FindException`. This error commonly appears when launching with `java -m`, calling `Configuration.resolve(...)` or `Configuration.resolveAndBind(...)`, or when `ModuleFinder` reads an invalid module source.

Example of a common message:

~~~text
Error occurred during initialization of boot layer
java.lang.module.FindException:
Module com.example.catalog not found, required by com.example.app
~~~

This message does not mean the JVM failed to find a single class. It indicates that **module resolution** could not locate a named module required by the module graph, or that the module finder encountered a failure while reading and identifying a module.

This lesson explains how to identify the missing module, the actual search sources, the causes of `FindException`, and a troubleshooting workflow that does not weaken JPMS structure.

## 1. Which stage does FindException belong to?

A modular program goes through several steps:

~~~text
module-info.java
       |
       v
  javac compiles
       |
       v
module-info.class and modular JAR
       |
       v
ModuleFinder locates modules
       |
       v
Configuration.resolve / resolveAndBind
       |
       v
Valid module graph
       |
       v
ModuleLayer or boot layer
       |
       v
Class loading and running main
~~~

`FindException` is mainly associated with the **ModuleFinder** and **resolution** steps: a module cannot be found by name, or required module metadata cannot be read from the supplied source.

Distinguish among these:

- **Cannot find a module:** typically `FindException`.
- **Modules found, but the module graph conflicts:** typically `ResolutionException`.
- **Module graph resolved, but layer creation is invalid:** may throw `LayerInstantiationException`.
- **Module created, but class not found at execution time:** may throw `ClassNotFoundException` or `NoClassDefFoundError`.
- **Service provider fails during instantiation:** may throw `ServiceConfigurationError`.

The exception type helps narrow down the first stage to inspect; avoid changing the classpath, module descriptors, and business code all at once.

## 2. Minimal example: a missing dependency module

Suppose there are two named modules:

~~~text
src/
├── com.example.catalog/
│   ├── module-info.java
│   └── com/example/catalog/api/CatalogService.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

Descriptor of the library module:

~~~java
module com.example.catalog {
    exports com.example.catalog.api;
}
~~~

Descriptor of the application:

~~~java
module com.example.app {
    requires com.example.catalog;
}
~~~

Main class:

~~~java
package com.example.app;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Application started");
    }
}
~~~

Compile the modules:

~~~bash
javac --module-source-path src \
      -d mods \
      -m com.example.catalog,com.example.app
~~~

When compilation succeeds, the output is typically:

~~~text
mods/
├── com.example.catalog/
│   ├── module-info.class
│   └── com/example/catalog/api/CatalogService.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
~~~

Run with a module path containing both modules:

~~~bash
java --module-path mods \
     -m com.example.app/com.example.app.Main
~~~

In this case, the resolver can find both the app module and the catalog module.

If you later package or deploy **only the app module** while omitting the catalog module, running the app with a module path lacking catalog may report:

~~~text
java.lang.module.FindException:
Module com.example.catalog not found, required by com.example.app
~~~

The name after `Module` is the unfound dependency. The name after `required by` is the module that directly declares that required dependency.

**Fix:** place the right `com.example.catalog` artifact onto the module path, or update the dependency/module name if the descriptor changed. Do not add `--add-exports` or `--add-opens` to deal with a module that has not even been found.

## 3. How do a missing root module and a missing dependency differ?

There are two important message patterns.

**Root module not found:**

~~~text
java.lang.module.FindException:
Module com.example.app not found
~~~

This occurs when the module name is specified directly as a root, such as `-m com.example.app`, but the module finder cannot see that module from the current sources.

Check:

- Has the app module been compiled or packaged yet?
- Does `--module-path` point to the right directory or modular JAR?
- Does the name in `-m` match the actual module name?
- Is the path wrong due to the working directory or quoting?

**Dependency of a module not found:**

~~~text
java.lang.module.FindException:
Module com.example.catalog not found, required by com.example.app
~~~

Here the resolver found `com.example.app` and read its descriptor, but `requires com.example.catalog;` cannot be satisfied.

Check the catalog module on the module path before editing the app module. The required module may live in another JAR, an exploded module directory, or the JDK's module runtime image.

Note: the error message only names the missing link at the moment the resolver detects it. A graph may be missing multiple modules; after fixing the first error, the resolver may report the next one.

## 4. The module path is the first source to verify

Syntax for running a named module:

~~~bash
java --module-path <module-path> \
     -m <module-name>/<main-class>
~~~

Short form:

~~~bash
java -p <module-path> \
     -m <module-name>/<main-class>
~~~

On Linux/macOS, multiple path entries are normally separated by colons:

~~~bash
java --module-path "mods:lib:plugins" \
     -m com.example.app/com.example.app.Main
~~~

On Windows, paths are separated by semicolons:

~~~powershell
java --module-path "mods;lib;plugins" -m com.example.app/com.example.app.Main
~~~

Common configuration mistakes:

1. Pointing to a nonexistent directory.
2. Pointing by mistake to the source directory instead of the compiled module output.
3. Adding only the app's directory while forgetting dependencies.
4. Placing a JAR on `--class-path` while another module declares `requires` on it.
5. Using the wrong path separator for the operating system.
6. Running the command from a different working directory so relative paths are no longer valid.
7. CI and the IDE using two different module paths.

**The module path is not the classpath.** A JAR on the classpath belongs to the unnamed module; it does not automatically become a named module that can be referenced with `requires com.example.catalog;`.

## 5. Checking the actual module name

A JAR filename is not necessarily the module name.

Example:

~~~text
lib/
├── catalog-utils-2.4.jar
└── catalog-api-1.0.jar
~~~

An explicit module JAR has its name declared in `module-info.class`. A JAR without a descriptor, when placed on the module path, can become an **automatic module**; an automatic module's name may come from `Automatic-Module-Name` in the manifest or be derived from the filename.

Use the JDK tool to inspect it:

~~~bash
jar --describe-module --file lib/catalog-utils-2.4.jar
~~~

The output might show:

~~~text
com.example.catalog
requires java.base mandated
exports com.example.catalog.api
~~~

If the actual name is `catalog.utils` while the app descriptor requires `com.example.catalog`, the resolver will not treat the two names as the same module.

To view the JAR contents:

~~~bash
jar --list --file lib/catalog-utils-2.4.jar
~~~

For an explicit modular JAR, check that `module-info.class` exists in the appropriate location. For an automatic module, check whether the derived module name matches the name in `requires`.

Do not rename JARs arbitrarily expecting that to always fix dependencies. For an explicit module, the name lives in the descriptor and does not depend on the filename.

## 6. ModuleFinder: checking module lookup before resolution

When an application creates a dynamic module layer, we typically start from:

~~~java
ModuleFinder finder =
    ModuleFinder.of(Path.of("plugins"));
~~~

You can ask whether the finder recognizes a specific module:

~~~java
Optional<ModuleReference> reference =
    finder.find("com.example.catalog");

System.out.println("Found: " + reference.isPresent());
~~~

If `reference.isEmpty()`, that module is not recognized by the current finder under the requested name.

You can list the recognized modules:

~~~java
finder.findAll().stream()
    .map(ref -> ref.descriptor().name())
    .sorted()
    .forEach(System.out::println);
~~~

Required imports:

~~~java
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;
import java.util.Optional;
~~~

**Important:** `find` and `findAll` can also throw `FindException` if reading the module source fails. Therefore, you do not always merely get `Optional.empty()`; sometimes the finder itself cannot interpret an artifact in the directory.

Diagnostic example that catches the exception:

~~~java
import java.lang.module.FindException;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;

public final class InspectModules {
    public static void main(String[] args) {
        ModuleFinder finder =
            ModuleFinder.of(Path.of("plugins"));

        try {
            finder.findAll().stream()
                .map(ref -> ref.descriptor().name())
                .sorted()
                .forEach(System.out::println);
        } catch (FindException ex) {
            System.err.println(
                "Cannot inspect module source: " + ex.getMessage());
            ex.printStackTrace();
        }
    }
}
~~~

This class helps separate two issues: **the finder cannot read the source** versus **the resolver found the source but is missing a dependency**.

## 7. Configuration.resolve and FindException

When building a custom `ModuleLayer`, for example:

~~~java
import java.lang.module.Configuration;
import java.lang.module.FindException;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

ModuleFinder finder =
    ModuleFinder.of(Path.of("plugins"));

Configuration parent =
    ModuleLayer.boot().configuration();

Configuration configuration;
try {
    configuration = parent.resolve(
        finder,
        ModuleFinder.of(),
        Set.of("com.example.plugin")
    );
} catch (FindException ex) {
    System.err.println(
        "Module lookup failed: " + ex.getMessage());
    throw ex;
}
~~~

Parameters to understand:

- The first `finder` is the module lookup source searched before the parent.
- `parent` is the configuration already present in the parent layer.
- `ModuleFinder.of()` is an empty finder used for the lookup source searched after the parent.
- `Set.of("com.example.plugin")` is the set of **root modules** to resolve.

If a root module or a required dependency is not among the modules observable from these sources, `FindException` can be thrown.

Do not merely check `finder.find("com.example.plugin")` and conclude all dependencies are sufficient. The root may exist, yet its `requires`, or the `requires` of a transitive dependency, may still fail to resolve.

## 8. Successful resolution does not mean ModuleLayer creation succeeded

Dynamic module loading typically has two phases:

~~~java
Configuration configuration =
    ModuleLayer.boot().configuration().resolve(
        ModuleFinder.of(Path.of("plugins")),
        ModuleFinder.of(),
        Set.of("com.example.plugin")
    );

ModuleLayer pluginLayer =
    ModuleLayer.boot().defineModulesWithOneLoader(
        configuration,
        ClassLoader.getSystemClassLoader()
    );
~~~

The first phase produces the resolved **configuration**. The second phase defines the runtime modules and attaches a class loader.

If the error occurs inside `resolve`, inspecting class loader creation logic or `ModuleLayer` APIs generally will not pinpoint the primary cause. First, ensure the module graph is accepted by the resolver.

Conversely, if `resolve` succeeds but `defineModulesWithOneLoader` fails, investigate the layer definition stage instead of automatically assuming it is a `FindException`.

## 9. Reading dependencies from the module descriptor

A useful diagnostic technique is printing the `requires` directives of a found module:

~~~java
ModuleFinder finder =
    ModuleFinder.of(Path.of("mods"));

finder.find("com.example.app").ifPresent(ref -> {
    var descriptor = ref.descriptor();

    System.out.println("Module: " + descriptor.name());
    descriptor.requires().forEach(req -> {
        System.out.println(
            "requires " + req.name() + " " + req.modifiers());
    });
});
~~~

Dependencies can be:

- `requires com.example.catalog;`: a regular dependency.
- `requires transitive com.example.api;`: a dependency whose readability is propagated according to JPMS rules.
- `requires static com.example.optional;`: a compile-time dependency, not necessarily required to be present at runtime.

For `requires static`, understand it properly: the dependency may be absent during a runtime resolution. Do not force adding an optional module just to silence another error when the descriptor does not actually require its presence. However, if the application invokes a class from the optional dependency when it is not provided, a class loading error can still occur at a later stage.

If a library module's `requires transitive` pulls in a missing dependency, the `required by` message may point to the library module rather than necessarily the root app. Trace the actual dependency chain rather than looking only at the root module.

## 10. Inspecting artifacts on the module path

A common deployment layout:

~~~text
deployment/
├── modules/
│   ├── com.example.app.jar
│   ├── com.example.catalog.jar
│   └── com.example.logging.jar
└── start.sh
~~~

If the start script points to `deployment/modules` when the working directory is not `deployment`, the relative path can be misinterpreted.

On Linux/macOS, you can check:

~~~bash
pwd
ls -la modules
java --module-path modules \
     -m com.example.app/com.example.app.Main
~~~

In PowerShell:

~~~powershell
Get-Location
Get-ChildItem .\modules
java --module-path modules -m com.example.app/com.example.app.Main
~~~

For a suspect JAR:

~~~bash
jar --describe-module --file modules/com.example.catalog.jar
jar --list --file modules/com.example.catalog.jar
~~~

Confirm:

1. The JAR file actually exists at the location seen by the process.
2. The file is not empty, truncated, or corrupted.
3. The descriptor contains the right module name.
4. The JAR provides the expected module version/artifact.
5. Its transitive dependencies are also present or in the parent configuration.

If using exploded modules, check that the directory has `module-info.class` and class files underneath in the proper module layout.

## 11. Errors reading module descriptors and modular JARs

`FindException` does not only occur when a module name is missing. It can also occur when the module finder encounters an artifact that it cannot read or interpret as a valid module.

Some scenarios:

- `module-info.class` is corrupted or the descriptor is invalid.
- The modular JAR is truncated, unreadable, or not valid ZIP content.
- Module metadata is incompatible with the runtime/tool being used.
- The module path points to a file or directory lacking valid module content under the rules expected by the finder.
- There is an I/O or read-permission issue with the module source.

The message may contain something like:

~~~text
java.lang.module.FindException:
Error reading module: ... 
~~~

For some descriptor issues, the underlying exception may be nested in the cause chain. Therefore, keep the stack trace and `Caused by` entries rather than extracting only the first line.

Example:

~~~java
try {
    ModuleFinder finder =
        ModuleFinder.of(Path.of("plugins"));

    finder.findAll();
} catch (FindException ex) {
    System.err.println(ex.getMessage());

    Throwable cause = ex.getCause();
    while (cause != null) {
        System.err.println("Caused by: " + cause);
        cause = cause.getCause();
    }
}
~~~

Do not just drop an arbitrary JAR with the same name onto the module path when the actual copy is corrupted. Fix the artifact source, verify checksums, or rebuild the modular JAR from reliable inputs.

## 12. JDK version and module descriptor compatibility

If a JAR was built with a newer JDK than the runtime being used, class/descriptor reading errors or class format errors may appear at different stages. Not every version error is a `FindException`, yet this is a factor to check when module lookup behaves abnormally.

Check:

~~~bash
java -version
javac -version
jar --describe-module --file modules/com.example.catalog.jar
~~~

In CI/CD systems, pin an appropriate Java toolchain/baseline for build and runtime. Do not mix artifacts built from different JDK configurations without knowing their bytecode level and minimum API level.

If an artifact uses a multi-release JAR, the module name and descriptor may depend on content matching the runtime version. Use the appropriate JDK tools and inspect the output actually seen by the deployment environment.

## 13. Automatic modules and derived names

A JAR on the module path without `module-info.class` can become an automatic module.

Example JAR:

~~~text
shared-utils-3.2.jar
~~~

The automatic module name can be derived from the filename (according to Java's rules) or taken from `Automatic-Module-Name` in the manifest.

If the app declares:

~~~java
module com.example.app {
    requires com.example.shared;
}
~~~

but the JAR on the module path has a different automatic module name, the resolver will not recognize the `com.example.shared` dependency from that JAR.

Verification command:

~~~bash
jar --describe-module --file lib/shared-utils-3.2.jar
~~~

If the output reports a different name, choose an appropriate fix:

- Use the exact module name published by the artifact if the design accepts an automatic module.
- Convert the library to an explicit module with a stable descriptor.
- Use an appropriate artifact/version that has `Automatic-Module-Name` defined consistently.
- Avoid temporarily renaming the JAR to fix the error if doing so creates an unstable dependency contract.

When migrating from the classpath to the module path, managing module names is an important part of dependency design.

## 14. --add-modules does not create a missing module

The `--add-modules` option adds modules to the **root set** of resolution:

~~~bash
java --module-path mods \
     --add-modules com.example.catalog \
     -m com.example.app/com.example.app.Main
~~~

It does not download JARs from the Internet, automatically copy module dependencies, or turn a nonexistent name into a real module.

If `com.example.catalog` is not visible to the finder, merely adding `--add-modules com.example.catalog` may trigger the error earlier or produce a missing root module message.

Similarly:

- `--add-reads` changes readability in appropriate contexts; it does not create a new module source.
- `--add-exports` opens package access; it does not find or restore a missing JAR.
- `--add-opens` relates to deep reflection, not module lookup.
- `--module-path` is what needs checking when the resolver cannot find a module artifact.

Only use `--add-modules` when the module can be found and you genuinely need to add a root for that resolution.

## 15. Service binding can expose missing dependencies

When an application uses services in JPMS, `Configuration.resolveAndBind(...)` can pull in provider modules beyond regular dependencies.

Example:

~~~java
Configuration configuration =
    ModuleLayer.boot().configuration().resolveAndBind(
        ModuleFinder.of(Path.of("plugins")),
        ModuleFinder.of(),
        Set.of("com.example.app")
    );
~~~

An app module declares:

~~~java
module com.example.app {
    requires com.example.spi;

    uses com.example.spi.Converter;
}
~~~

A provider module may declare:

~~~java
module com.example.provider.json {
    requires com.example.spi;
    requires com.example.json.core;

    provides com.example.spi.Converter
        with com.example.provider.json.JsonConverter;
}
~~~

If service binding brings the `com.example.provider.json` provider into the configuration, but `com.example.json.core` cannot be found, resolution may report a `FindException` related to the provider's dependency.

Therefore, when the error occurs only with `resolveAndBind` and not with `resolve`, inspect the **discovered provider modules** and all of their dependencies.

Do not blindly disable service binding if the application needs services. Instead, clarify which provider modules are brought into the graph and ensure the provider artifacts are complete and compatible.

## 16. Custom ModuleFinders and non-filesystem module sources

JPMS allows applications to provide a custom `ModuleFinder`, for example reading modules from a repository or memory. A custom finder must return a `ModuleReference` with a valid descriptor and the ability to read module contents.

When an application uses a custom finder:

- `find(name)` must return the right module by descriptor name.
- `findAll()` must publish a consistent set of available modules.
- `ModuleReference.descriptor()` must accurately reflect the actual dependencies and packages.
- `ModuleReference.open()` must provide a `ModuleReader` able to read classes and resources.
- There must be a version/tenant policy to avoid changing the module set between resolution steps.

If the repository has the artifact yet the finder returns `Optional.empty()` because of a wrong name mapping, the resolver still considers the module not found. If descriptor metadata is broken, the finder may throw `FindException` before creating a configuration.

Do not only debug the filesystem if the application uses a custom source. Observe the finder's own logic and the list of modules it publishes.

## 17. How does FindException differ from ResolutionException?

These two exceptions are often confused:

| Error type | Primary stage | Examples |
|---|---|---|
| `FindException` | Finding/reading modules | Root does not exist, dependency not found, cannot read descriptor |
| `ResolutionException` | Validating found module graph | Module graph conflicts because multiple modules supply incompatible packages |
| `LayerInstantiationException` | Defining runtime layer | Cannot apply module configuration to layer/loaders |
| `ClassNotFoundException` | Loading a class by name | Loader cannot find a class |
| `NoClassDefFoundError` | Linking/loading class on use | Required class cannot be defined or found |
| `IllegalAccessError` | Runtime access check | Access to class/member blocked by Java/JPMS rules |

For example, if two modules are both present yet cause the same consumer to read overlapping packages, that error leans toward a **module graph conflict**, not a missing module artifact. In that case, expanding `--module-path` by adding more JARs will not necessarily help; it can even make the conflict worse.

Conversely, if the message says `Module X not found`, first locate the exact artifact with module name X.

## 18. Module path, classpath, and root set limits

Several runtime options change the set of modules observable to the resolver:

- `--module-path`: where to find application modules.
- `--upgrade-module-path`: where to provide upgradeable modules if the environment permits.
- `--limit-modules`: restricts the observable module set, which can make a needed module unavailable.
- `--add-modules`: adds roots that the resolver must consider.
- `-m`: specifies the named root module to launch.

If a module exists on the filesystem yet is excluded from the observable module set due to limiting settings or search sources, the error can still be "not found" from the resolver's perspective.

For example, when debugging `--limit-modules`, try a test configuration without that limit in a test environment to determine whether the limit is hiding a dependency. Do not permanently remove a production limiting policy without understanding its operational or security goals.

Distinguish between **a module artifact existing on disk** and **a module name being selected by the finder and present in a specific resolution**. The two are not always equivalent.

## 19. JDK tools for diagnostics

Useful commands:

~~~bash
# Check Java version
java -version
javac -version

# Check descriptor and module name
jar --describe-module --file lib/com.example.catalog.jar

# Check classes and module-info.class
jar --list --file lib/com.example.catalog.jar

# List runtime image modules
java --list-modules

# Print resolution process on launch
java --show-module-resolution \
     --module-path "mods:lib" \
     -m com.example.app/com.example.app.Main
~~~

If you want to inspect dependencies among built modules, you can use `jdeps` with the appropriate module path:

~~~bash
jdeps --module-path "mods:lib" \
      --check com.example.app
~~~

These commands help determine different pieces of information:

- `jar --describe-module`: what module name the artifact claims and what it declares.
- `jar --list`: whether the artifact actually contains class files/descriptor.
- `java --list-modules`: which JDK modules the runtime image currently has.
- `--show-module-resolution`: helps observe the graph resolved by the launcher if execution reaches the relevant reporting phase.
- `jdeps`: assists in checking dependencies/module graph at the artifact level.

If the command line is long or generated by a build tool, log the **actual command/argument list** rather than trusting only IDE or Gradle/Maven configuration files.

## 20. Ordered workflow for handling FindException

When encountering `FindException`, follow these steps:

1. **Read the entire message.** Identify the module name after `Module ... not found` and the module in `required by` if present.
2. **Record the running command.** Include Java version, working directory, module path, main module, `--add-modules`, and limiting options.
3. **Check the actual artifact.** Is the file/directory in the right place where the JVM runs?
4. **Read the module name with a JDK tool.** Use `jar --describe-module`; do not guess from the filename.
5. **Check the requiring module's descriptor.** Do `requires`, `requires transitive`, or `requires static` directives have the right name and semantics?
6. **Check transitive dependencies.** Does the module being looked up depend on another module that has not been supplied?
7. **Check any custom finder.** Do `find` and `findAll` see the right module name?
8. **If it reports error reading module**, check the JAR, descriptor, I/O, checksum, and cause chain.
9. **If it fails only when binding services**, check newly resolved provider modules and their dependencies.
10. **Re-run with a minimal, explicit module path.** Do not add unrelated flags that open access.
11. **Check both build and runtime.** A module may be present at compile time yet missing in the deployment environment.
12. **Confirm the module graph.** Only after resolution succeeds should you debug class loading or package access.

An ordered workflow prevents fixing the wrong layer, such as changing `exports` when the artifact is completely missing.

## 21. Real-world scenarios

### 21.1. Running from the IDE works, but running the JAR fails

The IDE may automatically add dependencies to the module path when running. The deployment script copies only one modular JAR, missing direct or transitive dependencies.

The fix is to inspect the JVM args generated by the IDE, compare them against the production command line, and package all required modules.

### 21.2. Refactoring a module name while forgetting to update requires

Previously:

~~~java
module com.example.catalog {
    exports com.example.catalog.api;
}
~~~

Refactored to:

~~~java
module com.example.catalog.core {
    exports com.example.catalog.api;
}
~~~

Yet the app still has:

~~~java
module com.example.app {
    requires com.example.catalog;
}
~~~

Even though the new artifact exists, the resolver has no module named `com.example.catalog`. Update the app descriptor and corresponding dependencies, or retain a valid compatibility module if a migration strategy requires it.

### 21.3. A library is placed on the classpath

The app requires the named module `com.example.catalog`, but the deployer runs:

~~~bash
java -cp "lib/*" \
     --module-path mods \
     -m com.example.app/com.example.app.Main
~~~

If the catalog JAR sits only on the classpath, the resolver cannot satisfy `requires com.example.catalog;` with that JAR. Move the right artifact to the module path or adjust the dependency architecture accordingly; do not expect the classpath to supply named modules.

### 21.4. A plugin exists but is not inside ModuleFinder

The application uses:

~~~java
ModuleFinder finder =
    ModuleFinder.of(Path.of("plugins/active"));
~~~

While the artifact is deployed at `plugins/available`. Even though the JAR is on disk, the finder does not find it from the `active` directory.

Point the finder path to the intended source, or establish a clear plugin activation policy. Do not change module names just because the deployment directory configuration is wrong.

### 21.5. A service provider pulls in a new dependency

A provider added to the plugins directory has `requires com.example.codec;`. If the repository has not deployed the codec module, `resolveAndBind` can fail even though the root app did not change. Check the provider's dependencies and the module search scope.

## 22. Common wrong fixes

**Adding `--add-exports` to fix module not found.** Exports only affect package access permissions; they do not make a module appear.

**Adding `--add-modules` for a nonexistent module.** Selecting a root does not create an artifact. First bring the right module into the finder's scope.

**Only renaming the JAR.** For an explicit module, the module name comes from the descriptor; changing the filename does not change the module name.

**Moving all JARs to the classpath.** This can eliminate the intended module graph and alter the encapsulation model; it is not a minimal fix when the project is designed around JPMS.

**Removing the `requires` line to stop the runtime error.** If the app genuinely depends on the missing module's API, removing the dependency can cause another compile or runtime error. Only edit the descriptor when the dependency relationship is no longer valid in the architecture.

**Swallowing FindException and continuing to run the plugin as if resolved.** If a configuration was not created successfully, proceeding to define a layer or invoke services is unreliable. Catch the exception to report a context-rich error and then stop or select a designed fallback.

**Confusing FindException with ResolutionException.** If the modules were found but the graph conflicts, analyze packages/readability and version selection rather than merely checking whether the JAR exists.

**Changing all configurations at once.** Adjust one variable step by step: working directory, module path, module names, dependencies, provider finder. This approach helps pinpoint the exact cause.

## 23. Self-check checklist

1. Is the root module specified in `-m` present on the module path?
2. Does the module name in the descriptor match the name used by the `java` command and `requires`?
3. Is the missing module a root or a dependency of another module?
4. Is there a `requires transitive` pulling in a transitive dependency?
5. Are you confusing `requires static` with a mandatory runtime dependency?
6. Is the JAR an explicit module or an automatic module?
7. Is any module placed only on the classpath so the resolver cannot see it?
8. Are the Java versions on the build machine and runtime compatible with the artifacts?
9. Can `ModuleFinder` read the source without throwing `FindException`?
10. In a custom finder, does the module name match `descriptor.name()`?
11. Is any `--limit-modules` or finder configuration hiding a required module?
12. Does `resolveAndBind` bring new providers and new dependencies into the graph?
13. Are the full stack trace and `Caused by` preserved when reporting the error?
14. Have you distinguished finding errors from graph conflicts and class loading?
15. Does the production launch command include the full module path that the IDE/CI used during the build?

## 24. Conclusion

`java.lang.module.FindException` is a signal that Java cannot **find or read a required module** while constructing the module graph. The right fix is not widening exports, adjusting reflection, or trying random JVM flags. Start from **the module name in the message**, locate the module with `ModuleFinder` or `jar --describe-module`, check the module path, direct/transitive dependencies, and artifact state. If using a dynamic `ModuleLayer` or service binding, check both the finder and the resolved providers.

Once the module is found and its descriptor is valid, resolution can proceed to validate the consistency of the module graph. Clearly distinguishing these stages helps fix errors at their true cause, preserve module structure, and operate JPMS applications reliably.