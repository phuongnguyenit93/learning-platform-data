# ResolutionException Due to Invalid Graph

When compiling or running an application that uses the Java Platform Module System (JPMS), Java does not merely locate JAR files. It also **resolves the module graph**: selecting the necessary modules, linking dependencies via `requires`, determining readability, checking exported packages, and ensuring the set of modules can coexist under JPMS rules.

If the modules can be found yet **cannot form a valid graph**, resolution may fail with `java.lang.module.ResolutionException`. A common symptom is two modules both exporting the same package to a consuming module; a module cannot read the same package from two conflicting sources.

This lesson explains the nature of the error, distinguishes it from other module errors, illustrates package conflicts, points out sources of error such as `requires transitive`, automatic modules, and service binding, and then presents a diagnostic and design-fix workflow.

## 1. What is ResolutionException?

`ResolutionException` resides in the `java.lang.module` package and represents an error detected while resolving a module configuration.

An overview:

~~~text
Module path / system modules / parent configuration
                       │
                       ▼
                 Find modules
                       │
                       ▼
              Select root modules
                       │
                       ▼
             Resolve dependencies
                       │
                       ▼
          Validate module graph rules
                       │
            ┌──────────┴──────────┐
            ▼                     ▼
       Valid graph          Invalid graph
            │                     │
            ▼                     ▼
     Configuration       ResolutionException
            │
            ▼
       ModuleLayer
~~~

In the API, resolution can take place when using:

~~~java
Configuration child = parentConfiguration.resolve(
    beforeFinder,
    afterFinder,
    rootModules
);
~~~

or:

~~~java
Configuration child = Configuration.resolve(
    beforeFinder,
    parentConfigurations,
    afterFinder,
    rootModules
);
~~~

The Java launcher must also perform module resolution before launching a modular application with `java --module ...`.

**Having modules on the module path does not mean the graph is valid.** The resolver must also ensure the relationships among them do not violate module rules.

## 2. Distinguishing ResolutionException from other errors

JPMS-related errors often have similar names yet occur at different stages:

| Error | Typical meaning | Investigation direction |
| --- | --- | --- |
| `FindException` | Required module not found or issue discovering modules | Module path, module name, artifacts, and missing dependencies |
| `ResolutionException` | Modules are present but cannot form a valid module graph | Readability, conflicting exports, dependency graph |
| `LayerInstantiationException` | Graph resolved, but defining modules into a layer failed | Class loader mapping, package conflict in layer, parent layers |
| `IllegalAccessError` | Runtime access to a type/member not permitted | `exports`, access modifiers, and runtime options |
| `InaccessibleObjectException` | Reflection not permitted across module encapsulation | `opens`, target module, and `--add-opens` |
| `ClassNotFoundException` | Class loader cannot find the requested class | Classpath/module path, class name, and class loader |

Key takeaway: **not every error containing the word "module" is a `ResolutionException`**. For example, JARs with duplicate module names, missing modules, or corrupted JAR files can lead to errors at the module discovery step. Read the exact exception type and the verbatim actual message.

## 3. Basic example: two modules export the same package

Suppose two independent libraries both place public classes in the package `com.acme.common`.

First module:

~~~java
// com.acme.left/module-info.java
module com.acme.left {
    exports com.acme.common;
}
~~~

~~~java
// com.acme.left/com/acme/common/Left.java
package com.acme.common;

public final class Left {
    public static String value() {
        return "left";
    }
}
~~~

Second module:

~~~java
// com.acme.right/module-info.java
module com.acme.right {
    exports com.acme.common;
}
~~~

~~~java
// com.acme.right/com/acme/common/Right.java
package com.acme.common;

public final class Right {
    public static String value() {
        return "right";
    }
}
~~~

The application requires both:

~~~java
// com.acme.app/module-info.java
module com.acme.app {
    requires com.acme.left;
    requires com.acme.right;
}
~~~

Diagram:

~~~text
                  com.acme.app
                   /        \
                  /          \
     requires left            requires right
            │                       │
            ▼                       ▼
     com.acme.left            com.acme.right
            │                       │
            └── exports com.acme.common ──┘
                         ▲
                     Conflict
~~~

`com.acme.app` reads both modules, and both export the `com.acme.common` package to it. JPMS cannot treat `com.acme.common` as a single API package with a clear source for the app.

The runtime message might resemble:

~~~text
Error occurred during initialization of boot layer
java.lang.module.ResolutionException:
Modules com.acme.left and com.acme.right
export package com.acme.common to module com.acme.app
~~~

This is an illustrative message; module order and exact wording can vary by JDK or the graph being resolved.

In a project built from source, `javac` can detect the conflict while compiling the consumer module. In that case, the error appears at compile time rather than waiting for the Java launcher. **Regardless of which stage detects it, the design cause remains a graph with two conflicting export sources for the same consumer.**

## 4. Why do split packages make a graph hard to validate?

A **split package** means the same package name appears in multiple different modules.

Example:

~~~text
library-one.jar
└── com/acme/common/Alpha.class

library-two.jar
└── com/acme/common/Beta.class
~~~

If both JARs become named modules and both expose the package `com.acme.common`, whether a conflict occurs depends on module relationships, how packages are exported, and how layers/class loaders are created.

For a consumer module, two exported packages with the same name from two modules that the consumer reads are a classic source of `ResolutionException`. Do not overgeneralize that **any two JARs with overlapping packages anywhere on disk** immediately produce this exact exception: Java must still observe, select, and resolve the modules involved. Some package conflicts may be detected at the layer definition stage and manifest as a different exception.

The design principle for explicit modules is that **each package should have one clear owner in the module graph**. Do not share package names just to group classes by an organizational convention.

The usual fix is to rename packages and separate responsibilities:

~~~text
com.acme.left.api
com.acme.right.api
~~~

or extract the shared API into an independent module:

~~~text
com.acme.shared.api
        ▲      ▲
        │      │
com.acme.left  com.acme.right
        ▲      ▲
        └──┬───┘
       com.acme.app
~~~

The second approach fits if both libraries genuinely need the same set of API types, rather than each library owning its own copy of classes with the same package name.

## 5. requires transitive can propagate conflicts to consumers

A module may declare direct dependencies on only two API modules, yet still read other dependencies **indirectly** via `requires transitive`.

Example:

~~~java
module com.acme.first.api {
    requires transitive com.vendor.first.model;
    exports com.acme.first.api;
}
~~~

~~~java
module com.acme.second.api {
    requires transitive com.vendor.second.model;
    exports com.acme.second.api;
}
~~~

If `com.vendor.first.model` and `com.vendor.second.model` both export the package `com.vendor.common`, the consumer:

~~~java
module com.acme.app {
    requires com.acme.first.api;
    requires com.acme.second.api;
}
~~~

can hit a conflict when the graph causes it to read both model modules.

Diagram:

~~~text
com.acme.app
├── requires com.acme.first.api
│   └── requires transitive com.vendor.first.model
│       └── exports com.vendor.common
└── requires com.acme.second.api
    └── requires transitive com.vendor.second.model
        └── exports com.vendor.common
~~~

Looking only at the two `requires` lines in the app may not reveal the root issue. When diagnosing, trace the entire path of dependencies with propagated readability, not just directly declared dependencies.

Do not blindly change every `requires transitive` to `requires` to hide the error. If the intermediate module's public API returns types from the dependency, `transitive` may be part of the right design. Fix package ownership or the API architecture before altering readability.

## 6. A module reading a package from a dependency and its own package

Conflicts do not happen only between two external dependencies.

If module `com.acme.app` itself contains the package `com.acme.shared` while reading another module that exports the same package, JPMS also enforces constraints to prevent a module from both owning a package and seeing a duplicate definition from another source.

Conceptual example:

~~~text
com.acme.app
├── classes: com.acme.shared.LocalType
└── requires com.acme.lib
                  └── exports com.acme.shared
~~~

This is a sign to review package boundaries and class packaging. For properly built modules, shared public API packages should live in a single owning module, rather than "copying" a dependency's classes into the consumer module.

If the same sources are packaged into multiple JARs via shading or build plugins, inspect the final artifacts rather than just the source layout.

## 7. Automatic modules can surface conflicts

A JAR without `module-info.class`, when placed on the module path, can be recognized by Java as an **automatic module**.

Example:

~~~text
mods/
├── legacy-utils-1.0.jar
├── other-utils-2.0.jar
└── com.acme.app.jar
~~~

Automatic modules have broad readability and export rules convenient for migration. When moving multiple legacy JARs onto the module path, packages that previously coexisted on the classpath can expose split package issues.

For example, two legacy JARs both contain:

~~~text
com/legacy/util/Helper.class
~~~

If both become modules and both end up in the graph where a consuming module reads them, the package conflict can prevent resolution or cause an error at the layer definition step, depending on the configuration.

Therefore, when migrating from the classpath to the module path:

1. Check the derived automatic module names.
2. Inspect the packages each JAR contains.
3. Remove duplicate classes and unnecessary dependencies.
4. Prefer library releases with explicit module descriptors and clear package ownership.
5. Do not assume a set of JARs that worked on the classpath will automatically form a valid module graph.

To check an artifact's module name:

~~~bash
jar --describe-module --file mods/legacy-utils-1.0.jar
~~~

If the output indicates it is an automatic module, note that the module name may depend on the `Automatic-Module-Name` manifest entry or the JAR filename.

## 8. Module path containing multiple versions of the same module

Another common dependency error is placing multiple versions of the same library on the module path:

~~~text
mods/
├── com.acme.data-1.0.jar
└── com.acme.data-2.0.jar
~~~

If both declare the module name `com.acme.data`, the module finder may report a module discovery/duplicate module name issue. Depending on the tool and how the module path is organized, that can be a `FindException` or another module path error, **not necessarily a `ResolutionException`**.

What to do:

- Determine which version is actually selected by dependency management.
- Avoid copying all versions of the same artifact into the `mods` directory.
- Inspect the manifest or descriptor to know the actual module name.
- Synchronize dependencies between Maven/Gradle and the distribution directory.
- Do not merely rename the JAR file: an explicit module name lives in `module-info.class` and does not change with the filename.

Maintaining multiple versions of a module in separate `ModuleLayer`s is a different problem. It requires intentional layer/class loader configuration and cannot be solved simply by placing two JARs with the same module name into a normal module path directory.

## 9. Service binding adds extra modules to the graph

When using `Configuration.resolveAndBind(...)`, JPMS can add matching provider modules to the resolution result.

Example:

~~~java
Configuration config = parentConfiguration.resolveAndBind(
    pluginFinder,
    ModuleFinder.of(),
    Set.of("com.acme.app")
);
~~~

If `com.acme.app` declares:

~~~java
module com.acme.app {
    uses com.acme.spi.Plugin;
}
~~~

and the module path has multiple providers, service binding can pull provider modules and their dependencies into the graph. That can expose package conflicts that did not appear when resolving only the initial root modules.

Diagram:

~~~text
com.acme.app
    │ uses Plugin
    ▼
Service binding
    ├── com.acme.provider.a
    │    └── requires com.vendor.common.a
    └── com.acme.provider.b
         └── requires com.vendor.common.b
~~~

If the expanded graph causes a module to read two sources exporting overlapping packages, the resolver can report an error.

Do not jump to the conclusion that the service loader is "broken". Check which providers were added, which dependencies were pulled in, and which package conflicts.

As a plugin architecture grows, clearly defining provider discovery, root modules, and module layer boundaries helps reduce unexpected conflicts.

## 10. Reading ResolutionException messages systematically

Example error:

~~~text
java.lang.module.ResolutionException:
Modules vendor.alpha and vendor.beta export package
com.vendor.common to module com.acme.app
~~~

Break the message into its components:

- **Consumer:** `com.acme.app`, the module affected by the conflict.
- **Source A:** `vendor.alpha`, one module exporting the package.
- **Source B:** `vendor.beta`, the other module exporting the same package.
- **Package:** `com.vendor.common`, the conflicting package name.

Information to collect:

~~~text
Consumer module:       com.acme.app
Conflicting package:   com.vendor.common
Exporter 1:            vendor.alpha
Exporter 2:            vendor.beta
Root modules:          ...
Module path:           ...
Java version:          ...
~~~

The error message is a clue, not always the entire root cause. For example, the consumer might depend directly only on `com.acme.api`, while `requires transitive` pulls both conflicting exports into the graph. Therefore, trace from the consumer to the exporters.

If the exception originates from the `Configuration.resolve` API, record `beforeFinder`, parent configurations, `afterFinder`, and the root set. The module names and source finders are key to reproducing the state.

## 11. Diagnostic workflow with JDK tools

### Step 1: verify the exact Java being used

~~~bash
java --version
javac --version
~~~

If the application runs in a custom runtime image, use that image's own executable. Module availability depends on the running runtime image.

### Step 2: check the actual module path

Example launch command:

~~~bash
java \
  --module-path "mods:libs" \
  --module com.acme.app/com.acme.app.Main
~~~

On Windows, the module path separator is usually a semicolon instead of a colon:

~~~powershell
java --module-path "mods;libs" --module com.acme.app/com.acme.app.Main
~~~

Ensure the paths actually passed to the launcher match what is intended in the script/container.

### Step 3: check observable modules

~~~bash
java --module-path mods --list-modules
~~~

This command helps identify which modules are found. It does not prove the graph resolves validly, because `--list-modules` is not the same as launching all root modules together in one graph.

### Step 4: inspect the descriptor of each relevant JAR

~~~bash
jar --describe-module --file mods/vendor.alpha.jar
jar --describe-module --file mods/vendor.beta.jar
jar --describe-module --file mods/com.acme.app.jar
~~~

Inspect the module name, `requires`, `requires transitive`, `exports`, and service directives. When a JAR is an automatic module, the output of `jar --describe-module` also helps determine the module name Java will use.

### Step 5: observe the resolution process

~~~bash
java \
  --show-module-resolution \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

This asks the launcher to print resolution details. If the graph fails, the output may show roots/dependencies processed before the error. There is no guarantee every module is printed when the resolver stops early; combine it with descriptors and the exception.

### Step 6: analyze dependencies

~~~bash
jdeps --module-path mods --check com.acme.app
~~~

`jdeps` can analyze descriptors, dependencies, and readability according to the JDK version's capabilities. You can continue checking intermediate modules that use `requires transitive`.

For a specific artifact:

~~~bash
jdeps --module-path mods --list-deps mods/com.acme.app.jar
~~~

Static analysis is a supplementary diagnostic tool. It is not guaranteed to see dynamically selected providers, bytecode generated at runtime, or all reflective interactions.

## 12. Fixing conflicts by redesigning packages

The most durable approach is clarifying **which module owns which package**.

Suppose initially:

~~~text
vendor.alpha → exports com.acme.common
vendor.beta  → exports com.acme.common
~~~

If the two modules contain unrelated APIs, rename the packages:

~~~text
vendor.alpha → exports com.acme.alpha.api
vendor.beta  → exports com.acme.beta.api
~~~

If they share the same API types, extract a single shared owning module:

~~~java
module com.acme.common.api {
    exports com.acme.common.api;
}
~~~

Then have both implementation modules depend on it:

~~~java
module com.acme.alpha {
    requires com.acme.common.api;
    exports com.acme.alpha.api;
}
~~~

~~~java
module com.acme.beta {
    requires com.acme.common.api;
    exports com.acme.beta.api;
}
~~~

This not only resolves the resolution error; it also prevents other modules from accidentally compiling against two versions of types that share binary names across two different artifacts.

If the conflict comes from third-party dependencies, prefer finding library versions that have fixed the split package or published valid JPMS metadata before modifying vendor classes yourself.

## 13. When to change requires transitive?

Sometimes the issue arises because an API module propagates readability unnecessarily to consumers:

~~~java
module com.acme.facade {
    requires transitive com.vendor.legacy;
    exports com.acme.facade.api;
}
~~~

If the public API of `com.acme.facade` does not expose types from `com.vendor.legacy` and consumers do not need to read the vendor module, you can consider:

~~~java
module com.acme.facade {
    requires com.vendor.legacy;
    exports com.acme.facade.api;
}
~~~

However, this change must be based on the actual API contract. If public method signatures use types from `com.vendor.legacy`, removing `transitive` can deprive consumers of necessary readability.

When two modules genuinely need the same API package, downgrading `transitive` is not a long-term solution. Fix package ownership rather than masking the conflict by narrowing module visibility.

## 14. Qualified exports are not an arbitrary workaround

A module can export a package selectively:

~~~java
exports com.vendor.internal to com.acme.adapter;
~~~

Qualified exports are useful when a package is an integration API intended specifically for one module. They can affect which consumer modules see the exported package.

However, do not change `exports p` to `exports p to some.module` merely to dodge `ResolutionException` if `p` is actually a public API meant for other consumers. Doing so changes the library's contract and may break compilation for other applications.

Questions to ask before fixing:

- Is the package genuinely a public API?
- Which modules are using public types in that package?
- Are two modules providing the same API or two unintentionally overlapping APIs?
- Can we rename packages or extract a shared API module instead of narrowing exports?

Fix the design at the root cause rather than optimizing to make the error message temporarily disappear.

## 15. JVM flags that usually do not solve the problem

Several options commonly come up during JPMS diagnostics:

| Option | Function | Note regarding ResolutionException |
| --- | --- | --- |
| `--add-modules` | Adds root modules | May resolve more modules, thereby exposing conflicts |
| `--limit-modules` | Limits observable modules | May temporarily hide an issue, yet also drop needed dependencies |
| `--add-reads` | Adds module read relationships | Does not fix package ownership; can introduce conflicting read edges |
| `--add-exports` | Grants access to public API from unexported package | Not a merge operation for two identically named packages |
| `--add-opens` | Allows deep reflection | Does not resolve module graph conflicts during resolution |
| `--patch-module` | Supplements/replaces content of an existing module | Requires strict package control; not a design fix for split packages |

For example, `--add-opens` is meant for `InaccessibleObjectException`, not as a fix for two modules exporting the same package.

Do not try random flags hoping the launcher will ignore the error. If the graph violates JPMS constraints, changing dependencies or package boundaries is the sustainable direction.

## 16. Dynamic ModuleLayer: catching and reporting at the right layer

Plugin applications often resolve configurations via the API:

~~~java
import java.lang.module.Configuration;
import java.lang.module.FindException;
import java.lang.module.ModuleFinder;
import java.lang.module.ResolutionException;
import java.nio.file.Path;
import java.util.Set;

ModuleLayer parentLayer = ModuleLayer.boot();
ModuleFinder finder = ModuleFinder.of(Path.of("plugins"));

try {
    Configuration child = parentLayer.configuration().resolve(
        finder,
        ModuleFinder.of(),
        Set.of("com.acme.plugin")
    );

    ModuleLayer pluginLayer = parentLayer.defineModulesWithOneLoader(
        child,
        ClassLoader.getSystemClassLoader()
    );

    System.out.println(pluginLayer.modules());

} catch (FindException exception) {
    System.err.println("Module discovery failed: "
        + exception.getMessage());

} catch (ResolutionException exception) {
    System.err.println("Invalid module graph: "
        + exception.getMessage());
}
~~~

`ResolutionException` is detected when creating the `Configuration`. If the graph is created successfully yet defining the modules into class loaders fails, that is a separate stage and may produce `LayerInstantiationException`.

In production, avoid swallowing the error and proceeding as if the plugin loaded successfully. Log context such as the plugin directory, module roots, list of configured artifacts, JDK version, and the reported module names.

If the resolver uses parent configurations, remember that dependencies can be satisfied from a parent layer. That makes the graph depend on both new modules and modules already present in the parent, not solely on JARs in the plugin directory.

## 17. Checklist for fixing ResolutionException

When encountering an invalid graph message, follow this sequence:

1. **Record the verbatim exception**, especially the modules and package named.
2. **Identify the Java executable** and runtime image being used.
3. **Record the exact module path** and root modules at launch.
4. **Inspect artifacts** using `jar --describe-module`.
5. **Distinguish explicit/automatic modules** in the dependency set.
6. **Trace direct and transitive dependencies** from the affected module.
7. **Locate duplicate packages** in two modules exporting to the same consumer.
8. **Check service binding and plugin modules** if the graph is resolved dynamically.
9. **Fix package/module ownership** or switch to compatible dependency versions.
10. **Recompile descriptors and artifacts** instead of only editing JVM flags.
11. **Launch on the module path** and observe `--show-module-resolution`.
12. **Test the actual plugin/runtime flow** to ensure the error does not reappear when other modules are loaded after startup.

For systems using Maven/Gradle, inspecting the dependency tree is also critical. A transitive dependency or an older library version pulled in by another plugin can introduce duplicate packages that the main project never declared directly.

## 18. Incident report template for team coordination

A module resolution bug report should include:

~~~text
Symptom:
  java.lang.module.ResolutionException: ...

Java:
  java --version output

Launch:
  java --module-path ... --module ...

Root module:
  com.acme.app

Conflicting package:
  com.vendor.common

Modules exporting package:
  vendor.alpha
  vendor.beta

Observed dependency paths:
  app -> facade-a -> vendor.alpha
  app -> facade-b -> vendor.beta

Proposed fix:
  remove duplicate dependency /
  upgrade modular library /
  move shared API to one owning module
~~~

Structured details help separate design causes from environmental symptoms. When dealing with hundreds of artifacts, knowing **which package is exported twice and which consumer reads both** is far more useful than merely writing "Java 17 fails to run".

## Conclusion

`ResolutionException` reflects a failure at the step of **building a valid module graph**. The classic case is a consumer reading two modules that both export the same package, though conflicts can also arise from indirect dependency paths, automatic modules, or provider modules added through service binding.

Start from the **exception message**, identify the consumer module and conflicting package, and then use `jar --describe-module`, `java --list-modules`, `java --show-module-resolution`, and `jdeps` to trace the graph. The lasting solution is establishing a single owner for each package, removing duplicate dependencies, and managing `requires`/`exports` contracts properly. Flags meant for reflective access cannot substitute for fixing a genuinely invalid graph.