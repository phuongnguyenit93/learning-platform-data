# LayerInstantiationException When Creating a Layer

## 1. What does LayerInstantiationException indicate?

In the Java Platform Module System (JPMS), a `ModuleLayer` is a collection of modules defined at runtime. An application can create custom layers to load plugins, extensions, or modules that do not reside in the boot layer.

`java.lang.LayerInstantiationException` is a runtime exception indicating that **the JVM cannot define the modules of a `Configuration` into a `ModuleLayer` under the requested class loader mapping**. The error typically arises when calling methods such as:

- `ModuleLayer.defineModulesWithOneLoader(...)`.
- `ModuleLayer.defineModulesWithManyLoaders(...)`.
- `ModuleLayer.defineModules(...)`.
- The corresponding instance overloads invoked on a parent `ModuleLayer`.

Key point: **module resolution** and **layer instantiation** are two distinct stages.

~~~text
ModuleFinder
    |
    v
Configuration.resolve / resolveAndBind
    |
    | Success: module graph obtained
    v
ModuleLayer.defineModules...
    |
    | Success: each module is bound to a defining class loader
    v
ModuleLayer ready to load classes
~~~

A module configuration can resolve successfully yet still fail to instantiate when multiple modules are forced to share a single loader, when delegation is inconsistent, or when the module-to-loader mapping violates JVM constraints.

Therefore, if you encounter `LayerInstantiationException`, identify that **the failure is at the layer definition step**, rather than looking only at the dependency list or arbitrarily modifying `requires`.

## 2. Example of creating a custom ModuleLayer

Suppose the host wants to load a plugin module from the `plugins` directory:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public final class PluginLayers {

    public static ModuleLayer create(Path pluginDirectory) {
        ModuleLayer parent = ModuleLayer.boot();

        ModuleFinder finder = ModuleFinder.of(pluginDirectory);

        Configuration configuration =
                parent.configuration().resolve(
                        finder,
                        ModuleFinder.of(),
                        Set.of("com.acme.plugin"));

        return parent.defineModulesWithOneLoader(
                configuration,
                ClassLoader.getSystemClassLoader());
    }
}
~~~

The code consists of two parts that can fail independently:

1. `resolve(...)` locates the root module and resolves dependencies.
2. `defineModulesWithOneLoader(...)` defines the resolved modules into a single new shared class loader.

If the module path is missing a dependency, step 1 may throw `FindException` or `ResolutionException` depending on the cause. If the configuration is valid yet the class loader model does not satisfy constraints, step 2 may throw `LayerInstantiationException`.

Do not write a single `catch (RuntimeException)` block that generically reports "module not found". It erases stage information and misleads investigators into editing the wrong configuration.

## 3. Three components to record before fixing the error

When analyzing a layer creation failure, record at minimum:

| Component | Example | Why you need to know it |
|---|---|---|
| Parent layer | `ModuleLayer.boot()` | Identifies modules/packages already present in parent layers |
| Configuration | `Configuration` returned from `resolve` | Identifies which modules are intended for the new layer |
| Loader strategy | One loader, many loaders, or custom mapping | Identifies why packages/modules are mapped to an unsuitable loader |

The exact same `Configuration` can succeed with one loader strategy yet fail with another.

Example:

~~~java
ModuleLayer parent = ModuleLayer.boot();

Configuration cf = parent.configuration().resolve(
        ModuleFinder.of(pluginPath),
        ModuleFinder.of(),
        Set.of("com.acme.plugin"));

ModuleLayer layer = parent.defineModulesWithOneLoader(
        cf, ClassLoader.getSystemClassLoader());
~~~

When reading the stack trace, distinguish whether the error came from `resolve` or `defineModulesWithOneLoader`. That is the single most important directional step.

## 4. Common cause: two modules contain the same package

With `defineModulesWithOneLoader`, all modules belonging to the new configuration are defined into **the same class loader**. A single loader cannot define the same package as belonging to two different modules under this model.

Example of a structure at risk of conflict:

~~~text
plugins/
├── com.acme.plugin.alpha.jar
│   └── com/acme/shared/AlphaHelper.class
└── com.acme.plugin.beta.jar
    └── com/acme/shared/BetaHelper.class
~~~

Both named modules contain the package:

~~~text
com.acme.shared
~~~

If both modules are included in the configuration and `defineModulesWithOneLoader` is called, the layer definition step may be rejected due to **overlapping packages**.

Notable points:

- There does not need to be two identically named classes; having **the same package name** in two modules is already enough to create a conflict under the one-loader strategy.
- The `public` modifier and `exports` do not make the package conflict disappear.
- Two JARs sharing a package while working on the traditional classpath do not prove they can operate together as explicit named modules with one loader.
- Package names are compared by full name; sharing a prefix, such as `com.acme`, does not by itself create a conflict if the actual packages differ.

The preferred fix is to **assign each package to one clear module**. Move shared code into an API module or a separate common module, then have plugins use `requires` instead of duplicating the package.

## 5. Distinguishing split package and split delegation

Two concepts that are easily confused:

### 5.1. Overlapping packages / split package

Two modules in the configuration contain the same package, for example:

~~~text
Module A: com.acme.shared
Module B: com.acme.shared
~~~

This directly causes trouble when trying to map both modules to a single loader.

### 5.2. Split delegation

A new class loader may need to delegate loading requests for classes in the same package to **multiple different parent class loaders** because modules in parent layers are mapped differently.

Conceptual scenario:

~~~text
                   Custom Layer
                One shared loader
                  /          \
                 /            \
 Parent loader A                Parent loader B
 Module A exports p             Module B exports p
~~~

If the new layer's loader would have to choose among more than one target loader for the same package `p`, direct delegation is no longer unique. `defineModulesWithOneLoader` can fail due to **split delegation**, even though each individual module is valid.

This is why you must inspect parent layers and class loaders as well, not only look for duplicate packages inside the new configuration itself.

Switching to `defineModulesWithManyLoaders` may suit certain architectures, yet it is not a default panacea. If the module graph or package ownership remains inconsistent, fix the design and dependency resolution first.

## 6. Defining a module into a class loader that already contains a module with the same name

With the custom mapping method:

~~~java
ModuleLayer.defineModules(
        configuration,
        parentLayers,
        moduleName -> someLoader);
~~~

the JVM checks constraints related to class loaders. One cause of `LayerInstantiationException` is attempting to define a module into a loader that **already has a module with the same name**.

For example, a plugin host retains a loader from a previous deployment and reuses that same loader for the same module name in a new layer.

Things to keep in mind:

- A module name can appear in different layers when organized with appropriate class loaders.
- However, you cannot assume the same class loader can be reused repeatedly to redefine a module with the same name.
- Hot reload normally requires a **new loader** for a new plugin version, along with a strategy for releasing references to the old loader.

If the host caches a `ClassLoader` globally and maps every new plugin version to the old loader, check whether that is the source of the error.

## 7. A loader has already defined classes in the new module's package

An important custom-mapping case is mapping a module to a loader that has already independently defined types belonging to a package the module is about to own.

For example, a `URLClassLoader` has already loaded:

~~~text
com.acme.plugin.internal.Helper
~~~

Later the application tries to assign the `com.acme.plugin` module containing that same `com.acme.plugin.internal` package to this very loader.

The JVM may reject it because the loader already defined a class in the package before the module was defined into the loader.

Therefore, when building a custom plugin loader:

1. Create or prepare the loader first.
2. Define the module/layer in the proper order.
3. Only afterward begin loading classes from the layer's modules.
4. Do not call `Class.forName(...)` or `loader.loadClass(...)` prematurely to "probe" classes in packages about to be defined.

A common bug is discovery/inspection code loading classes before the layer is created, inadvertently mutating the class loader's state and causing a conflict upon instantiation.

## 8. Restrictions on the java.base module and java.* packages

Custom layer creation APIs do not permit freely redefining core components belonging to the reserved platform namespace.

Configurations like the following are invalid:

- A configuration attempting to put a module named `java.base` into a new layer.
- A new module containing a package named `java` or starting with `java.`, such as `java.acme.plugin`.
- With custom module-to-loader mapping, certain special class loaders are forbidden as target loaders under the API contract.

For example, a plugin accidentally declares the package:

~~~java
package java.acme.plugin;
~~~

this is not a valid package naming choice for a custom module layer. Rename it to a namespace owned by the application, for example:

~~~java
package com.acme.plugin;
~~~

Do not use `--add-exports` or `--add-opens` to work around this case: those options govern package access permissions and do not grant permission to redefine platform packages.

## 9. Choosing among defineModulesWithOneLoader, ManyLoaders, and custom mapping

The three strategies have distinct characteristics:

| Layer creation method | Loader mapping | Appropriate when |
|---|---|---|
| `defineModulesWithOneLoader` | Modules in the new configuration share one loader | Tightly cooperating group of modules with no package/delegation conflicts |
| `defineModulesWithManyLoaders` | Each module in the layer gets its own loader created by the API | Wanting to isolate modules by loader and let the API manage delegation |
| `defineModules` | Custom function decides the loader for each module | Host has its own class loader system and full control over the mapping |

Choose an option based on architecture. Many loaders can help avoid certain conflicts caused by packing too many modules into one loader, yet:

- The module graph must still be valid.
- You cannot rely on multiple loaders to legitimize all split packages between modules that have readability relationships.
- Service APIs crossing plugin boundaries must share the same class identity.
- With custom mapping, loaders must obey constraints on module definition and class loading/delegation.

Do not switch to many-loaders just to make an exception disappear while ignoring the root cause. Document why the new loader model fits system requirements.

## 10. Example of switching from one loader to many loaders

Given a resolved configuration:

~~~java
ModuleLayer parent = ModuleLayer.boot();

Configuration cf = parent.configuration().resolve(
        ModuleFinder.of(pluginDirectory),
        ModuleFinder.of(),
        Set.of("com.acme.plugin.alpha", "com.acme.plugin.beta"));
~~~

One-loader version:

~~~java
ModuleLayer layer = parent.defineModulesWithOneLoader(
        cf,
        ClassLoader.getSystemClassLoader());
~~~

If the module structure satisfies the appropriate constraints, multiple loaders can be used:

~~~java
ModuleLayer layer = parent.defineModulesWithManyLoaders(
        cf,
        ClassLoader.getSystemClassLoader());
~~~

After creating the layer, you can inspect the loader attached to each module:

~~~java
ClassLoader alphaLoader =
        layer.findLoader("com.acme.plugin.alpha");

ClassLoader betaLoader =
        layer.findLoader("com.acme.plugin.beta");

System.out.println(alphaLoader == betaLoader);
~~~

With the many-loaders method, modules in the layer are defined into separate loaders. Even so, this does not mean two plugins are allowed to define their own copies of a service interface exchanged between host and plugin via an API.

If the host uses `com.acme.plugin.api.Plugin` from a parent layer, providers in the child layer must implement that exact service interface. If a plugin bundles its own copy of the API under a different loader, class identity errors can appear after the layer is created.

## 11. Module resolution failure is not layer instantiation failure

A troubleshooting flow should distinguish three exception groups:

| Stage | Common exception | Nature |
|---|---|---|
| Find module | `FindException` | Module not found, unreadable artifact, or module discovery error |
| Resolve configuration | `ResolutionException` | Module graph does not satisfy resolution constraints |
| Define layer | `LayerInstantiationException` | Cannot define modules into loaders under the requested mapping |

In addition, if mismatched parent configurations and parent layers are passed, the API may throw `IllegalArgumentException`. Errors from the mapping function can also propagate outward rather than automatically turning into `LayerInstantiationException` in all cases.

Example of stage-by-stage logging:

~~~java
ModuleLayer parent = ModuleLayer.boot();

Configuration cf;
try {
    cf = parent.configuration().resolve(
            ModuleFinder.of(pluginDirectory),
            ModuleFinder.of(),
            Set.of("com.acme.plugin"));
} catch (java.lang.module.FindException ex) {
    System.err.println("Failed to find modules");
    ex.printStackTrace();
    throw ex;
} catch (java.lang.module.ResolutionException ex) {
    System.err.println("Failed to resolve configuration");
    ex.printStackTrace();
    throw ex;
}

try {
    return parent.defineModulesWithOneLoader(
            cf, ClassLoader.getSystemClassLoader());
} catch (LayerInstantiationException ex) {
    System.err.println("Failed to instantiate module layer");
    ex.printStackTrace();
    throw ex;
}
~~~

In a complete example, the method containing the snippet above must return `ModuleLayer` and declare appropriate input parameters.

Separating catches like this ensures logs pinpoint the exact stage; do not write infinite retry fallbacks or retry layer creation with the same input without understanding the cause.

## 12. Trap of parent configuration mismatching parent layer

Example:

~~~java
ModuleLayer boot = ModuleLayer.boot();

Configuration cf = boot.configuration().resolve(
        ModuleFinder.of(pluginPath),
        ModuleFinder.of(),
        Set.of("com.acme.plugin"));
~~~

The configuration above has the boot layer's configuration as its parent. If you then call a layer definition method with a non-matching set of parent layers, the API may throw `IllegalArgumentException`.

This differs from `LayerInstantiationException`:

- `IllegalArgumentException`: the caller passed an invalid combination of configuration/parent layers according to the method contract.
- `LayerInstantiationException`: the module/layer definition operation cannot complete due to instantiation constraints.

When using the static API with multiple parent layers:

~~~java
ModuleLayer.defineModulesWithOneLoader(
        cf,
        List.of(parentLayer),
        ClassLoader.getSystemClassLoader());
~~~

ensure the list of parent layers is in the exact order and matches the parent configurations of `cf`.

Do not take a `Configuration` from one layer tree and mistakenly attach it to another layer tree merely because the module names look alike.

## 13. Checking module descriptors and package ownership

A systematic way to investigate is reading the descriptors of all modules in the `Configuration` and grouping packages by owner.

Helper example:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ResolvedModule;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

public final class PackageInspector {

    public static Map<String, List<String>> packageOwners(
            Configuration configuration) {

        Map<String, List<String>> owners = new TreeMap<>();

        for (ResolvedModule resolved : configuration.modules()) {
            String moduleName = resolved.name();

            for (String packageName :
                    resolved.reference().descriptor().packages()) {

                owners.computeIfAbsent(
                        packageName, unused -> new ArrayList<>())
                        .add(moduleName);
            }
        }

        return owners;
    }

    public static void printOverlaps(Configuration configuration) {
        packageOwners(configuration).forEach((pkg, modules) -> {
            if (modules.size() > 1) {
                System.err.println(
                        "Overlapping package " + pkg + " in " + modules);
            }
        });
    }
}
~~~

Usage:

~~~java
Configuration cf = /* resolved configuration */;
PackageInspector.printOverlaps(cf);
~~~

If this prints:

~~~text
Overlapping package com.acme.shared in
[com.acme.plugin.alpha, com.acme.plugin.beta]
~~~

it is a very strong indicator that `defineModulesWithOneLoader` will not be suitable for that configuration.

Note: the helper above only detects duplicate packages **within the configuration under examination**. It does not automatically check split delegation across parent loaders or classes previously defined by a loader. If the helper prints no errors, do not conclude that layer instantiation is guaranteed to succeed.

## 14. How to inspect actual JARs

When package overlap appears, inspect the artifacts placed on the module path, not just the source tree in the repository.

For explicit modular JARs:

~~~bash
jar --describe-module --file plugins/com.acme.plugin.alpha.jar
jar --describe-module --file plugins/com.acme.plugin.beta.jar
~~~

To view class entries:

~~~bash
jar --list --file plugins/com.acme.plugin.alpha.jar
jar --list --file plugins/com.acme.plugin.beta.jar
~~~

For example, a package packaged in both JARs:

~~~text
com/acme/shared/Utils.class
~~~

Even when class names differ, merely having two entries under the same package in two modules is a sign to review package ownership.

If build-tool shading or dependency repackaging copied a package into plugin JARs, inspect the shading configuration. A seemingly "shared" dependency can accidentally be bundled inside multiple modular JARs and create a split package.

Typical solutions are:

- Place shared code into a module with a single package owner.
- Use `requires` to the shared module.
- Or relocate the dependency's package when truly necessary and ensure descriptors/artifacts are updated consistently.

Do not simply delete one class to avoid a name collision; resolve ownership of the entire package.

## 15. Distinguishing module path from classpath

When an application previously ran on the classpath, classes could be loaded from multiple JARs without explicit module descriptors. After moving plugins to named modules on the module path, JPMS enforces new constraints on package ownership, readability, and loader mapping.

For example, an older framework has:

~~~text
legacy-a.jar -> com.acme.util
legacy-b.jar -> com.acme.util
~~~

When both JARs become automatic modules or explicit modules, splitting a package can cause module resolution errors or layer instantiation errors, depending on the module graph and how the layer is created.

Do not equate "runs on the classpath" with "can be moved as-is onto the module path".

A migration plan typically needs to:

1. Identify JARs containing duplicate packages.
2. Extract shared packages into separate modules.
3. Update module descriptors.
4. Verify the graph with JDK tools.
5. Re-run the exact custom layer creation mechanism that the host uses.

## 16. How can automatic modules affect this?

A JAR without `module-info.class` placed on the module path can be treated as an automatic module. Its module name can come from the manifest or be derived from the filename.

Automatic modules export packages broadly to assist migration, yet this does not remove class loader mapping restrictions.

If an automatic module and an explicit module contain the same package, or two automatic modules overlap on a package, a conflict can occur when both must be read or defined into a loader under a specific configuration.

Check the module name and packages of each JAR:

~~~bash
jar --describe-module --file libs/legacy-a.jar
jar --describe-module --file libs/legacy-b.jar
~~~

Pay special attention to automatic module names derived from filenames, which can be unstable if artifacts are renamed.

Adding `Automatic-Module-Name` can stabilize a transitional module name, yet it **does not fix split packages**. Package ownership still has to be resolved through design or packaging.

## 17. Checking the configuration with JDK tools

Several commands support investigation:

~~~bash
java --module-path plugins --list-modules
~~~

This command lists the observable modules for the module path in use.

~~~bash
java --module-path plugins --describe-module com.acme.plugin
~~~

This command describes the module descriptor observable by the launcher.

~~~bash
java --module-path plugins --validate-modules
~~~

Depending on the JDK version, `--validate-modules` checks the module path and reports metadata/module conflicts detected by the launcher.

When running a modular application:

~~~bash
java --show-module-resolution \
  --module-path mods:plugins \
  -m com.acme.host/com.acme.host.Main
~~~

`--show-module-resolution` is helpful for the graph resolved when **the launcher starts the application**. However, if the host creates custom layers later in code, launcher output does not necessarily show all modules dynamically resolved in custom layers. For runtime layer errors, log the configuration and module-to-loader mapping separately inside the host.

On Windows, the module path separator is usually a semicolon instead of a colon. Adjust commands for your operating system and shell.

## 18. Adding logging right where the layer is created

For production debugging, log valuable details before calling define:

~~~java
static void logConfiguration(Configuration cf) {
    System.out.println("Modules to define:");
    cf.modules().stream()
            .map(ResolvedModule::name)
            .sorted()
            .forEach(name -> System.out.println(" - " + name));
}
~~~

Example invocation:

~~~java
Configuration cf = /* resolved configuration */;
logConfiguration(cf);
PackageInspector.printOverlaps(cf);

try {
    ModuleLayer layer = ModuleLayer.boot()
            .defineModulesWithOneLoader(
                    cf, ClassLoader.getSystemClassLoader());

    System.out.println("Layer created: " + layer);
} catch (LayerInstantiationException ex) {
    System.err.println("Layer instantiation failed");
    ex.printStackTrace();
    throw ex;
}
~~~

To use this helper, import `java.lang.module.ResolvedModule`. For larger systems, also log:

- The list of parent layers and modules in parent configurations.
- The chosen loader strategy.
- The loader instance returned by the mapping function if using custom mapping.
- The file/JAR location of each module reference.
- Package overlaps and packages exported from parent layers.
- Root module names passed into `resolve` or `resolveAndBind`.

Avoid printing sensitive information or full internal paths to public logs if security environments require restricting diagnostic data.

## 19. A fix strategy by cause category

### Case A: modules have overlapping packages in a one-loader layer

How to handle:

1. Confirm the duplicate package in the configuration.
2. Identify the proper package owner.
3. Move shared classes to a separate named module or change package ownership.
4. Update `requires` and import paths.
5. Rebuild the modular JARs.
6. Retry creating the layer with the fixed configuration.

Do not merely use `--add-exports`, because exporting access rights does not resolve a package owner conflict.

### Case B: split delegation to parent loaders

How to handle:

1. Identify which package is requested for delegation.
2. Check which parent modules export that package.
3. Identify the defining loader of each module.
4. Redesign API/module sharing across parent layers if necessary.
5. Consider many-loaders or custom loader mapping only when they genuinely yield a consistent delegation mapping.

### Case C: custom loader already holds an old module/class

How to handle:

1. Check whether the loader mapping returns a loader already used for a previous version of the module.
2. Check whether the loader has already defined classes in a package of the new module.
3. Create a fresh loader for the new plugin generation, following an appropriate lifecycle design.
4. Do not load classes before defining modules.
5. Avoid retaining old class loaders via caches, thread context loaders, or unnecessary static registries.

### Case D: package or module uses a forbidden namespace

How to handle:

1. Search plugin artifacts for packages named `java` or `java.*`.
2. Rename packages to an application-owned namespace.
3. Remove configurations trying to define module `java.base` in a custom layer.
4. Rebuild and inspect the descriptor/package list.

## 20. Do not confuse with ClassNotFoundException, ClassCastException, and InaccessibleObjectException

Some errors appear **after** the layer has already been created:

| Exception | When it typically occurs | Main question |
|---|---|---|
| `LayerInstantiationException` | When defining a custom layer | Is the module-to-loader mapping valid? |
| `ClassNotFoundException` | When looking up/loading a class | Is the class in the loader/module being searched? |
| `NoClassDefFoundError` | When linking or initializing a class usage path | Did a dependency/class earlier fail or become unfindable? |
| `ClassCastException` | When casting an object | Do the two types share the same class identity? |
| `IllegalAccessError` | When access is denied by the JVM | Do readability, exports, and Java access permit it? |
| `InaccessibleObjectException` | When deep reflection is denied | Is the package open to the caller module? |
| `ServiceConfigurationError` | When finding/instantiating a service provider | Are `uses`, `provides`, resolution, and the provider valid? |

If `ModuleLayer.defineModules...` has returned a layer successfully, subsequent errors usually need to be debugged via class loading or service loading mechanisms rather than continuing to call them layer instantiation failures.

## 21. Do not blindly retry when layer creation fails

Layer creation is not an operation to retry unconditionally. With custom loader mapping, the API does not guarantee that every layer definition operation is atomic; some modules may have been defined before part of the operation failed.

This is especially important if the application maps new modules into a **reused loader**. Calling again with the same loader without inspecting the altered state can make the error harder to diagnose.

A safer policy:

1. Preserve the stack trace and configuration details.
2. Do not automatically retry into the same loader after an exception.
3. Analyze the mapping/package conflict.
4. Fix the artifacts or create a new loader set when the design allows.
5. Run standalone layer-definition tests before allowing the host to load plugins in production.

Do not clear caches or swap global class loaders as an uncontrolled rescue measure.

## 22. Example unit test checking whether the layer can be created

In a plugin project, include an integration test using the **actual final modular JARs** and the host's loader strategy.

JUnit 5 example:

~~~java
import org.junit.jupiter.api.Test;

import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertNotNull;

final class ModuleLayerIntegrationTest {

    @Test
    void createsPluginLayer() {
        Path plugins = Path.of("build/plugin-modules");

        ModuleLayer parent = ModuleLayer.boot();

        Configuration cf = parent.configuration().resolve(
                ModuleFinder.of(plugins),
                ModuleFinder.of(),
                Set.of("com.acme.plugin"));

        ModuleLayer layer = parent.defineModulesWithOneLoader(
                cf,
                ClassLoader.getSystemClassLoader());

        assertNotNull(layer.findModule("com.acme.plugin")
                .orElse(null));
    }
}
~~~

This test requires the `build/plugin-modules` directory to actually contain valid module artifacts when run. It does not prove every class/plugin behavior works; subsequent tests must verify service discovery and API calls if the host requires them.

If the application uses many-loaders, the test must use `defineModulesWithManyLoaders` itself; if it uses custom mapping, the test must mirror the actual loader mapping. Testing a different strategy and treating that as production verification is insufficient.

## 23. Checklist before deploying a custom layer

- [ ] Identified the exact root modules to resolve.
- [ ] `ModuleFinder` points to the right modular JARs or exploded modules.
- [ ] `Configuration` is resolved from the right parent configuration.
- [ ] Parent layers are passed in the exact order matching parent configurations.
- [ ] Know whether one-loader, many-loaders, or custom mapping will be used.
- [ ] For one-loader, no overlapping packages exist in the configuration.
- [ ] No unresolvable split delegation exists across parent loaders.
- [ ] For custom mapping, the loader has not already defined a duplicate module name.
- [ ] For custom mapping, the loader has not already defined a class in the new module's packages.
- [ ] Not attempting to define module `java.base` or `java.*` packages in a custom layer.
- [ ] Plugin JARs do not accidentally contain copies of a shared API module's packages.
- [ ] Inspected the actual descriptors/JARs rather than only sources.
- [ ] Logged distinctions among find, resolve, and define failures.
- [ ] No blind retries after `LayerInstantiationException`.
- [ ] Have an integration test creating the layer with production artifacts and loader strategy.

## 24. Key takeaways

`LayerInstantiationException` occurs when **resolved modules cannot be defined into a layer under the requested class loader mapping**. It is an error of the layer definition stage; it does not mean all JPMS errors stem from missing dependencies.

Cause groups worth checking first:

1. Two or more modules contain the **same package** when forced to use one loader.
2. One loader must **delegate the same package to multiple different loaders**.
3. A custom loader already has a module with the same name or has defined classes in a package the new module wants to own.
4. The configuration contains a module/package in a forbidden platform namespace.
5. Parent layers, configuration, and loader strategy are not coordinated properly (some cases produce another exception, such as `IllegalArgumentException`).

An effective investigation path is **record the stack trace → determine resolve vs. define → list modules/package owners → check loader mapping and parent layers → fix package ownership or loader strategy → retry from a clean configuration**. Do not use `--add-exports` or `--add-opens` to "cure" module definition conflicts, because those flags adjust package access rather than altering layer instantiation constraints.

### API References

- Java SE 21, `java.lang.ModuleLayer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html
- Java SE 21, `java.lang.LayerInstantiationException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/LayerInstantiationException.html
- Java SE 21, `java.lang.module.Configuration`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/Configuration.html