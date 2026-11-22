# Module Not Found, Duplicate Packages, and JPMS Resolution Errors

When a Java application migrates from the traditional classpath to the Java Platform Module System (JPMS), errors can occur even before the `main` method is invoked. Messages such as `Module com.acme.core not found`, `module X reads package p from both A and B`, or `ResolutionException` are usually related to **module discovery, resolution, readability, exports, and package ownership**, rather than necessarily being caused by a bug in business logic.

During a **Java Advance Compatibility Migration**, this is especially important. A set of libraries running for years on a Java 8 classpath may contain duplicate packages, duplicate classes, or plugin JARs without descriptors. When moving them onto the Java 17/21 module path, the Java launcher applies more explicit JPMS rules, and conflicts previously hidden by the classpath can be exposed.

This lesson explains in detail the root causes, how to read error messages, the `java`, `javac`, `jar`, and `jdeps` tools, reproducible examples, safe remediation approaches, and a migration testing matrix. The goal is not merely to make exceptions disappear, but to build a **module graph that can be explained, packaged, and reproduced on the target environment**.

## 1. Starting from the JPMS Model

JPMS distinguishes several steps:

1. **Discovery:** locating observable module definitions from the JDK runtime image and the application module path.
2. **Resolution:** selecting the root modules and the dependencies required by descriptors.
3. **Readability:** determining which module can read which module.
4. **Accessibility:** determining which packages are exported or opened to which modules/callers.
5. **Class loading and reflection:** loading classes and accessing members when the application runs.

Diagram:

~~~text
Application JARs + JDK runtime modules
                   |
                   v
           Module discovery
                   |
                   v
   Roots + requires -> Module resolution
                   |
                   v
       Readability / exports checks
                   |
                   v
          Valid module graph
                   |
                   v
     Class loading, services, reflection
                   |
                   v
               main()
~~~

Not every error in the chain above has the same fix.

### 1.1. Observable, resolved, readable, and accessible

| State | Question | Indicator |
|---|---|---|
| Observable | Does the module finder see the module's definition? | Is the right JAR on the module path or is it a system module? |
| Resolved | Has the module been selected into the graph? | Is it a root or a pulled-in dependency? |
| Readable | Does module A read module B? | Is there an appropriate readability edge? |
| Accessible | Is A allowed to use B's package? | Does B export the package to A? |

For example, the `com.acme.metrics` module has a JAR placed in `lib/` but is not a root or a dependency of the app module. It can be **observable but not yet resolved**. A resolved module may also not be read by another module, or its package may not be exported.

These concepts should not be used as synonyms.

## 2. Three Module Types When Upgrading Java

### 2.1. Explicit named module

A module has `module-info.java`:

~~~java
module com.acme.orders {
    requires java.sql;
    requires com.acme.catalog;
    exports com.acme.orders.api;
}
~~~

The compiler generates `module-info.class`. When the artifact is found via the module path and resolved, it is a named module with explicit dependencies and access rules.

### 2.2. Automatic module

A library JAR without a module descriptor can become an **automatic module** when placed on the module path.

Its name is determined from:

- The manifest attribute `Automatic-Module-Name`, if declared validly.
- The JAR filename derived according to JPMS rules, if the attribute is missing.

Automatic modules assist the transition of legacy libraries, having broader readability/exports than explicit modules in appropriate cases. However, an automatic module **does not automatically resolve split packages**, duplicate module names, or class binary incompatibility.

### 2.3. Unnamed module

Classes loaded via the traditional classpath belong to the unnamed module associated with the class loader. For code in the unnamed module, access rules differ from named modules and classpath mechanisms still operate.

Important point: an explicit named module **cannot declare `requires unnamed`** to pull dependencies from the classpath. If a JAR is placed on the classpath instead of the module path, design appropriate boundaries instead of writing a nonexistent dependency in the descriptor.

### 2.4. System module

The JDK provides modules such as `java.base`, `java.logging`, and `java.sql`. A custom runtime image created via `jlink` may contain only a smaller subset. Therefore, an application may run on a full JDK yet report a missing system module in the runtime image.

## 3. Classpath and Module Path Are Two Different Operating Modes

Classpath:

~~~bash
java -cp "lib/*:app.jar" com.acme.app.Main
~~~

Module path:

~~~bash
java --module-path "mods:lib" \
  --module com.acme.app/com.acme.app.Main
~~~

On Windows, use `;` to separate entries in the path list, instead of `:` on Unix-like systems.

When switching from `-cp` to `--module-path`, the application does not merely change the path for finding JARs. The JVM builds a module graph and enforces module access rules.

### 3.1. Related options

| Option | Purpose |
|---|---|
| `--module-path`, `-p` | Specifies the location to search for application modules |
| `--module`, `-m` | Specifies the module/main class to launch |
| `--add-modules` | Adds root modules during resolution |
| `--limit-modules` | Limits the set of modules allowed to be observable |
| `--add-reads` | Adds an intentional readability edge |
| `--add-exports` | Exports an additional package when justified |
| `--add-opens` | Allows additional deep reflection |
| `--show-module-resolution` | Displays the resolution process at launch |
| `--list-modules` | Lists system modules in the runtime |
| `--describe-module` | Describes a module found by the launcher |

Use `java --help` and `javac --help` from the **exact target JDK** to verify supported syntax. These options only address individual layers; `--add-opens` cannot be used to create a missing module.

## 4. Module Not Found Errors at Compile Time

A descriptor:

~~~java
module com.acme.app {
    requires com.acme.catalog;
}
~~~

If the compiler cannot find `com.acme.catalog`, a message similar to the following usually appears:

~~~text
module-info.java:2: error: module not found: com.acme.catalog
    requires com.acme.catalog;
                     ^
~~~

The causes:

1. The dependency JAR has not been downloaded or built.
2. The compiler `--module-path` is missing the directory/JAR.
3. The actual module name differs from the name written in `requires`.
4. The JAR is on the classpath instead of the module path.
5. The dependency belongs to a multi-module build, but the output module has not been generated yet.
6. The set of observable modules is restricted by compiler configuration.
7. The artifact or module descriptor is invalid.

Do not start by modifying Java source code that consumes the API. Verify the **module name** and the **compile module path**.

## 5. Module Not Found Errors at Launch Time

A common message:

~~~text
Error occurred during initialization of boot layer
java.lang.module.FindException:
  Module com.acme.catalog not found, required by com.acme.app
~~~

The JVM needs to resolve `com.acme.app`, whose descriptor contains `requires com.acme.catalog`, but the module finder cannot see the requested module in the observable module set of the runtime launch.

What needs to be checked:

- The actual `java` command executed by systemd/Windows service/Docker.
- The current working directory and relative paths.
- Whether the JAR was copied into the image/distribution.
- Whether `--module-path` uses the correct path and is properly quoted.
- Whether the module JAR has the expected name/module descriptor.
- Whether `--limit-modules` is making the module non-observable.
- Whether another transitive dependency is missing.
- Whether the runtime is a custom `jlink` image missing system modules.

A JAR existing on disk is not necessarily on the process's module path.

## 6. Diagnostic Procedure for Module Not Found

### Step 1 — Record the actual compile and launch commands

For example:

~~~bash
java --module-path "dist/mods:dist/lib" \
  --module com.acme.app/com.acme.app.Main
~~~

Record absolute paths if needed. A common mistake is a script running from a different directory so `dist/lib` points to a nonexistent location.

### Step 2 — Inspect the JAR manifest/descriptor

~~~bash
jar --describe-module --file dist/lib/catalog-client.jar
~~~

The tool reports the corresponding explicit module or automatic module information. Do not guess the module name from Maven groupId, artifactId, or class package root.

### Step 3 — List module path entries

Check JAR file names, versions, contents, and module names. A distribution may accidentally copy `catalog-1.0.jar` while compiling against `catalog-2.0.jar`.

### Step 4 — Observe resolution

~~~bash
java --show-module-resolution \
  --module-path "dist/mods:dist/lib" \
  --module com.acme.app/com.acme.app.Main
~~~

When resolution fails very early, the output may not be detailed enough; combine it with checking `module-info.java` and specific JARs.

### Step 5 — Minimize the module graph

Try using only the root module and the minimal set of dependencies. If a directory contains extra JARs, remove them from the test run to identify module name or split-package conflicts.

### Step 6 — Preserve evidence

~~~text
JDK vendor/build:
Launch command:
Working directory:
Module path:
Root module:
module-info descriptors:
JAR names and hashes:
Exception and stack trace:
~~~

This information helps reproduce the error in CI and production environments.

## 7. Minimal Example with Two Explicit Modules

Project structure:

~~~text
src/
├── com.acme.catalog/
│   ├── module-info.java
│   └── com/acme/catalog/Catalog.java
└── com.acme.app/
    ├── module-info.java
    └── com/acme/app/Main.java
~~~

Library module:

~~~java
module com.acme.catalog {
    exports com.acme.catalog;
}
~~~

Library class:

~~~java
package com.acme.catalog;

public final class Catalog {
    public static String name() {
        return "catalog";
    }
}
~~~

Application module:

~~~java
module com.acme.app {
    requires com.acme.catalog;
}
~~~

Main class:

~~~java
package com.acme.app;

import com.acme.catalog.Catalog;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Catalog.name());
    }
}
~~~

Using module source path:

~~~bash
javac --module-source-path src \
  -d out \
  -m com.acme.catalog,com.acme.app
~~~

Launching:

~~~bash
java --module-path out \
  --module com.acme.app/com.acme.app.Main
~~~

The command above applies to a properly structured modular source tree. If you only copy the `com.acme.app` source into another project without providing the compiled `com.acme.catalog` artifact via module path or source module path, the compiler may report module not found.

### 7.1. Inspecting output

~~~text
out/
├── com.acme.catalog/
│   ├── module-info.class
│   └── com/acme/catalog/Catalog.class
└── com.acme.app/
    ├── module-info.class
    └── com/acme/app/Main.class
~~~

There are two exploded modules in the output root. When packaging into JARs, confirm that each archive contains the right module-info and classes for its corresponding module.

## 8. Module Name Differs from artifactId and JAR Name

Maven dependency example:

~~~xml
<dependency>
  <groupId>com.acme.platform</groupId>
  <artifactId>catalog-client</artifactId>
  <version>2.4.0</version>
</dependency>
~~~

The actual module name may be `com.acme.catalog.client`. If `module-info.java` writes:

~~~java
requires catalog.client;
~~~

then an error may be reported even though the file `catalog-client-2.4.0.jar` exists.

Sources of the module name in order of relevance:

1. The name in the explicit `module-info.class` if the JAR is already modularized.
2. `Automatic-Module-Name` for a non-modular JAR, when present.
3. The name derived from the JAR filename for remaining automatic modules.

In particular, a derived automatic module name can change when renaming a JAR or changing the version filename convention. For dependencies used long-term on the module path, stable module naming should be chosen.

## 9. Duplicate Module Name Differs from Module Not Found

Runtime distribution example:

~~~text
lib/
├── client-api-1.9.jar
└── client-api-2.4.jar
~~~

If both define the same module name `com.acme.client.api`, the module finder may report an error about duplicate modules in a module lookup source.

JPMS does not automatically pick the "latest version" based on the version suffix in the filename. It does not replace Maven/Gradle dependency mediation mechanisms.

Remediation approach:

- Choose one supported version.
- Remove the duplicate from the runtime bundle.
- Check that plugins/service wrappers do not also copy the old version.
- Check that shading or packaging does not create a module name collision.
- Verify the effective runtime module path, not just dependency declarations.

Do not keep both versions "just in case": doing so can turn a missing dependency error into a duplicate module error.

## 10. Module Present but Not Yet Resolved

Suppose:

~~~text
mods/
├── com.acme.app.jar
└── com.acme.metrics.jar
~~~

If `com.acme.app` does not `requires com.acme.metrics` and metrics is not added as a root or as a dependency via another path in the graph, the metrics JAR may sit on the module path yet **not appear in the resolved graph**.

There are situations where adding a root module is needed:

~~~bash
java --module-path mods \
  --add-modules com.acme.metrics \
  --module com.acme.app/com.acme.app.Main
~~~

However, `--add-modules` only works if that module is **observable** and causes no conflict. It does not fix a wrong name or automatically resolve split packages.

### 10.1. ALL-MODULE-PATH is not a default fix

In supported circumstances, `--add-modules ALL-MODULE-PATH` requests adding observable modules on the module path as roots. This can cause the graph to pull in unrelated libraries and create new package/name conflicts.

Do not pull every module into the graph if the application only needs a few explicit modules.

## 11. requires, transitive, and static

Example:

~~~java
module com.acme.report {
    requires com.acme.core;
    requires transitive com.acme.api;
    requires static com.acme.annotations;

    exports com.acme.report.api;
}
~~~

- `requires com.acme.core`: direct dependency/readability of this module.
- `requires transitive com.acme.api`: when another module reads `com.acme.report`, readability of `com.acme.api` can be propagated according to JPMS rules.
- `requires static com.acme.annotations`: module required at compile time, may be absent at runtime; code using optional classes still must handle when the module is absent.

`requires static` is not a way to hide a mandatory runtime dependency. If a feature actually calls a class that is absent at runtime, class loading/linkage errors can still occur.

### 11.1. Readability is not enough to access every class

Even when module A reads B, a package not exported by B to A is still not an accessible Java API. Both **`requires` and `exports`** must be checked.

## 12. --limit-modules Can Make a Dependency Non-Observable

A launch configuration may use:

~~~bash
java --limit-modules java.base,com.acme.app \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

`--limit-modules` has a mechanism that restricts the universe of observable modules based on the specified modules and their related closure according to Java launcher rules; as a consequence, another module may no longer be allowed to participate in resolution, even though its JAR exists on disk.

When module not found occurs only in a launcher but not with a manual `java` command, also look for `--limit-modules` in startup scripts, IDE, or CI options.

Do not remove `--limit-modules` without understanding the security/packaging reason it was added; first determine which dependency needs to belong to the allowed module set.

## 13. What Is a Split Package?

A **split package** is a situation where the same Java package name is defined by multiple JAR/module components.

Example:

~~~text
util-a.jar
└── com/acme/common/UtilA.class

util-b.jar
└── com/acme/common/UtilB.class
~~~

Both contain the `com.acme.common` package even though the class names differ.

On the classpath, this layout sometimes works because a class loader can locate classes from multiple JARs. On the module path, JPMS distinguishes package ownership per module and has rules preventing a module from reading the same package from conflicting module sources.

### 13.1. Not every duplicate package produces the same error

It is necessary to distinguish:

- Two named modules export the same package and a third module reads both.
- Two JARs share the same package but reside in isolated loaders/layers.
- One named module and one unnamed module share the same package name.
- Two versions both contain the same class name and package name.
- A shaded JAR merges classes into a single module.

The outcome depends on the graph, exports, readability, and class loader identity. Therefore, the statement "every split package always throws the same exception" should not be used for diagnosis.

## 14. Example Reproducing a Duplicate Package Error

Module A:

~~~java
module com.acme.util.a {
    exports com.acme.common;
}
~~~

Class A:

~~~java
package com.acme.common;

public final class UtilA {
    public static String value() {
        return "A";
    }
}
~~~

Module B:

~~~java
module com.acme.util.b {
    exports com.acme.common;
}
~~~

Class B:

~~~java
package com.acme.common;

public final class UtilB {
    public static String value() {
        return "B";
    }
}
~~~

Application:

~~~java
module com.acme.app {
    requires com.acme.util.a;
    requires com.acme.util.b;
}
~~~

The compiler/resolver may report:

~~~text
module com.acme.app reads package com.acme.common
  from both com.acme.util.a and com.acme.util.b
~~~

Even with no duplicate class names, the `com.acme.common` package is exported by two modules to the same reader. The issue lies in **package boundary and readability**, not the class names `UtilA`/`UtilB`.

### 14.1. Why is it not solved by renaming one class?

Renaming `UtilB` to `HelperB` still leaves module B exporting the `com.acme.common` package. Package ownership, module composition, or dependency topology must be changed.

## 15. Ways to Fix Split Packages

### 15.1. Consolidate the package under a single module owner

If the package is genuinely a shared API, merge the classes into one valid module:

~~~text
com.acme.common.module
└── com/acme/common/
    ├── UtilA.class
    └── UtilB.class
~~~

Other modules simply `requires com.acme.common.module`. This is the easiest model to reason about when the team has permission to modify source/packaging.

### 15.2. Separate packages by responsibility

If A and B have different ownership:

~~~text
com.acme.util.a
com.acme.util.b
~~~

Renaming packages requires considering public API compatibility, reflection, serialization, resource paths, generated code, and external consumers.

### 15.3. Remove duplicate dependencies

If the split package comes from two versions of a library, choose one version in the runtime distribution. Find out why both appear: manual copying, fat JAR, transitive dependency, or container-provided library.

### 15.4. Design a bridge for legacy libraries

If a library cannot yet be modularized and has many duplicate packages, it can be kept on the classpath during a transition phase, but boundaries with named modules must be designed. You cannot simply write `requires unnamed`.

### 15.5. ClassLoader or ModuleLayer isolation

For plugin systems needing to run incompatible dependencies, separate loaders/layers or separate processes can be used. However:

- Shared API/SPI types must have proper class identity.
- A module layer has its own resolution and package constraints.
- Service discovery, TCCL, resources, and memory leaks must be tested.
- Isolation does not fix a graph that requires the same module to read two conflicting exports.

This is a plugin platform design solution, not a trick to patch a distribution that copied extra JARs.

## 16. Duplicate Class and Split Package Are Different

Two JARs may contain:

~~~text
com/acme/common/Util.class
~~~

That is a **duplicate class name**. If only the package is duplicated without a duplicate binary class name, it can still be a split package.

| Scenario | Duplicate class? | Duplicate package? |
|---|---:|---:|
| JAR A contains `p.A`, JAR B contains `p.B` | No | Yes |
| JAR A/B both contain `p.A` | Yes | Yes |
| JAR A contains `a.X`, JAR B contains `b.Y` | No | No |

Duplicate classes on the classpath can cause shadowing and `NoSuchMethodError` if a different version is loaded than at compile time. In JPMS, conflicts can appear earlier at resolution/readability.

Do not merely run a duplicate-class checker and conclude that the package structure is already suitable for JPMS.

## 17. Automatic Modules Easily Expose Legacy Split Packages

Two legacy libraries:

~~~text
legacy-api.jar
  com/vendor/common/Client.class

legacy-impl.jar
  com/vendor/common/ClientImpl.class
~~~

On the classpath there may be no problem. When both are placed on the module path, each JAR becomes an automatic module with broad package exports/readability, and conflicts can appear if the app needs to read them according to the module graph.

Do not generate `module-info.java` for each JAR while keeping the duplicate packages intact. That does not fix ownership.

Options:

- Wait for the vendor to release a properly structured modularized version.
- Remove a redundant artifact if present.
- Merge packages in a controlled manner into one module within license limits.
- Move owned code to its own package.
- Keep the legacy classpath and separate JPMS modernization into another phase.

## 18. Finding Duplicate Packages in JARs

For each JAR:

~~~bash
jar --list --file lib/util-a.jar
jar --list --file lib/util-b.jar
~~~

Entries:

~~~text
com/acme/common/UtilA.class
com/acme/common/UtilB.class
~~~

show the same package path. With many artifacts, an archive analysis tool can be written to group class entries by package and module name.

Proper handling is needed for:

- `META-INF` is not a Java application package.
- `module-info.class` is a module descriptor.
- `META-INF/versions/N` has special meaning in a multi-release JAR.
- Shaded JARs may contain metadata/service descriptors in addition to classes.
- Duplicate packages in the archive list are not enough to conclude the graph fails; exports/readability/layers still must be examined.

Only analyze artifact copies in an authorized environment; do not extract them into production directories and accidentally overwrite files.

## 19. Indirect Package Conflict via requires transitive

For example, the app module only directly requires a facade:

~~~java
module com.acme.app {
    requires com.acme.facade;
    requires com.vendor.beta;
}
~~~

Facade:

~~~java
module com.acme.facade {
    requires transitive com.vendor.alpha;
}
~~~

If `com.vendor.alpha` and `com.vendor.beta` both export `com.vendor.common` to the app, a conflict can appear **even though the app does not directly write `requires com.vendor.alpha`**.

When diagnosing, examine:

- Direct `requires` of the app.
- Transitive readability from intermediate modules.
- Automatic modules.
- Root modules from `--add-modules`.
- Service binding/module layer configuration when present.

Do not just delete a `requires` line in the app and assume the conflict is gone if the module is still read through another path.

## 20. Package Exists but Is Not Visible

A module has:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
~~~

Internal class:

~~~java
package com.acme.catalog.internal;

public final class InternalParser {
}
~~~

Consumer `com.acme.app` can read the catalog module but cannot access the internal package. Compile error:

~~~text
package com.acme.catalog.internal is not visible
  (package is declared in module com.acme.catalog,
   which does not export it)
~~~

This is neither a missing module nor a split package.

The preferred fix is to use the exported API package. If the module author intentionally provides an SPI to a host, a qualified export can be used:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
    exports com.acme.catalog.spi
        to com.acme.plugin.host;
}
~~~

Do not export all internal packages just to "make the errors go away" without confirming the API contract.

## 21. opens Differs from exports

Frameworks such as ORMs, dependency injection, serializers, or test runners may require deep reflective access.

Example:

~~~java
module com.acme.app {
    requires com.acme.orm;

    exports com.acme.app.api;
    opens com.acme.app.entities to com.acme.orm;
}
~~~

- `exports` allows access to public types/members of the package under module access rules.
- `opens` allows deep reflection within the declared scope.
- `--add-opens` is an escape hatch used for runtime/configuration with a clear justification.

If the error is `InaccessibleObjectException`, the module graph may already be completely resolved. Adding new JARs does not fix reflection issues and can even create duplicate module/package errors.

Do not broadly use `--add-opens java.base/...=ALL-UNNAMED` when you only need to upgrade an incompatible library.

## 22. jlink Runtime Image May Miss System Modules

An application declares:

~~~java
module com.acme.app {
    requires java.sql;
}
~~~

A full JDK usually includes `java.sql`. However, a custom image built with `jlink` may lack that module if the module set in the image does not match the actual application.

Check:

~~~bash
/opt/app/runtime/bin/java --list-modules
~~~

Compare with the build JDK:

~~~bash
java --list-modules
~~~

If the custom image does not contain the needed system module, simply adding the application JAR to `--module-path` does not make that module appear. The runtime image creation must be adjusted and the final image tested.

### 22.1. jdeps assists but does not see all dynamic dependencies

~~~bash
jdeps --print-module-deps app.jar
~~~

`jdeps` analyzes static dependencies and can help select modules for the runtime image. It does not necessarily see reflection, ServiceLoader, plugin code, and features loaded only via dynamic configuration.

Integration tests should be added on the actual image covering less-used flows, not just a startup smoke test.

## 23. ServiceLoader and Provider Modules

With named modules, `ServiceLoader` can use `uses`/`provides` in module descriptors.

Host:

~~~java
module com.acme.payment.host {
    requires com.acme.payment.api;
    uses com.acme.payment.api.PaymentProvider;
}
~~~

Provider:

~~~java
module com.acme.payment.card {
    requires com.acme.payment.api;
    provides com.acme.payment.api.PaymentProvider
        with com.acme.payment.card.CardProvider;
}
~~~

The provider module must be located and placed into the appropriate layer/module configuration according to how the system launches or performs API resolution. Related errors include:

- The provider module is not observable.
- The provider has not been resolved into the required layer.
- `uses`/`provides` or metadata is incorrect.
- The provider class does not implement the same runtime SPI type.
- Incorrect ClassLoader/module-layer identity.
- The `META-INF/services` descriptor of a legacy plugin was lost after shading.

### 23.1. Provider not found differs from Module not found

The application can launch completely normally, yet `ServiceLoader` finds 0 providers. That may be a service binding/registration/visibility issue rather than a boot-layer `FindException`.

Actual provider discovery and callbacks must be tested; merely checking that the JAR is in the `plugins` directory is not enough.

## 24. ClassLoader Identity and Plugin Systems

The JVM distinguishes class identity by binary name **and defining class loader**. A plugin JAR may inadvertently bundle a copy of the SPI API:

~~~text
HostClassLoader:
    com.acme.spi.PaymentProvider

PluginClassLoader:
    com.acme.spi.PaymentProvider
~~~

Two types with the same name but defined by different loaders. When the host casts the plugin to the host's SPI type, a `ClassCastException` can occur.

Ways to reduce risk:

- Share the SPI API from a commonly designed loader.
- Isolate implementation dependencies when needed.
- Do not bundle an inappropriate copy of the SPI API into the plugin.
- Test ServiceLoader/TCCL/module layer just like in production.
- Check plugin load/reload and resource cleanup.

Not all `ClassCastException` errors of this kind should be attributed to split packages. This is an identity and class loader topology problem, although duplicate packages can also be a symptom.

## 25. Dynamic ModuleLayer and ResolutionException Errors

Some systems load plugins into child layers:

~~~text
Boot Layer
    |
    +-- Host API modules
    |
    v
Plugin Layer A
    +-- plugin-a modules

Plugin Layer B
    +-- plugin-b modules
~~~

When calling APIs such as `ModuleFinder`, `Configuration.resolve`, or `ModuleLayer.defineModulesWithOneLoader`, resolution errors can arise when the plugin is loaded, not when the JVM starts.

What to examine:

1. Does the finder locate the module artifact?
2. Is the requested module name correct?
3. Does the parent layer/configuration have the required modules?
4. Does the module graph have split packages?
5. Does the loader mapping violate package constraints?
6. In which layer is the shared API module defined?
7. Which layer/loader is `ServiceLoader` probing?

An error when creating a child layer is not fixed merely by changing `--module-path` for the boot layer if the code creates the child finder from a different path.

## 26. --patch-module and Testing Cases

`--patch-module` allows supplementing classes/resources into a module in special cases, commonly seen in testing.

Example:

~~~bash
java --patch-module com.acme.app=build/test-classes \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

It can help some test frameworks run test classes inside the module under test. However:

- It is not a Maven/Gradle dependency resolution mechanism.
- It does not automatically fix a graph with wrong module names.
- It can hide differences between test and production.
- It should not be used to arbitrarily merge all packages from multiple conflicting modules.

A smoke test must be run on the **distribution without test-only patches** before release.

## 27. Maven: Dependency Graph Is Not the JPMS Graph

A POM may have:

~~~xml
<dependency>
  <groupId>com.acme</groupId>
  <artifactId>catalog-api</artifactId>
  <version>2.4.0</version>
</dependency>
~~~

That allows Maven to resolve the artifact, yet the compiler/runtime still needs the right module name and module path configuration.

Check:

- Is `module-info.java` in the appropriate source root?
- Does the Maven Compiler Plugin support the target JDK and module-aware compilation?
- Do test plugins run tests on the module path or classpath?
- Do actual dependency versions have duplicate package/module names?
- Does the build reactor produce all modular artifacts?
- Do annotation processors/generated code add duplicate packages?
- Does the distribution copy all runtime modules?

Command:

~~~bash
./mvnw dependency:tree
~~~

helps show Maven dependency resolution, but does not replace `jar --describe-module` or runtime `--show-module-resolution`.

### 27.1. A testing trap

JUnit tests may pass when the Maven test plugin uses the classpath or test-specific module flags, while production runs named modules under a different configuration. Tests must exist that launch the exact production topology.

## 28. Gradle: inferModulePath Does Not Automatically Fix Split Packages

A Java Gradle project may use:

~~~groovy
plugins {
    id 'java'
}

java {
    modularity.inferModulePath = true
}
~~~

This configuration is supported in compatible Gradle versions and helps Gradle infer how to use the module path for related tasks. It **does not create valid descriptors**, does not change automatic module names, and does not resolve duplicate packages.

Need to examine separately:

- `compileJava` module path.
- `test` and test-specific reflective access.
- `runtimeClasspath` and distribution copy.
- Gradle Wrapper and JDK toolchain compatibility.
- Module-aware test execution and packaging.
- Third-party Gradle plugins/annotation processors.

Dependency analysis commands:

~~~bash
./gradlew dependencies

./gradlew dependencyInsight \
  --dependency catalog-api \
  --configuration runtimeClasspath
~~~

Do not infer from a dependency report that the module graph is valid.

## 29. Shading, Fat JARs, and Nested Archives

Shading can merge classes from multiple JARs into a single archive, but must consider:

- Duplicate `module-info.class`.
- Multiple packages with the same name.
- `META-INF/services` needing to be merged.
- JAR signatures altered when the archive is modified.
- Automatic module metadata and Multi-Release entries.
- License/NOTICE and resource conflicts.

A Spring Boot executable JAR typically has nested JARs in `BOOT-INF/lib` and its own loader. It is not equivalent to a directory of explicit named modules on the Java launcher's module path.

Do not conclude "modularized" simply because the source has `module-info.java` if production actually runs via a different framework loader/classpath layout. The **final artifact and launch mode** must be checked.

## 30. Java Agents and Reflective Frameworks Can Cause Different Errors

After a JDK upgrade, an APM agent or legacy ORM library may report:

~~~text
java.lang.reflect.InaccessibleObjectException
java.lang.IllegalAccessError
java.lang.UnsupportedClassVersionError
~~~

These errors do not necessarily stem from module resolution. For example:

- `InaccessibleObjectException`: package not opened for deep reflection.
- `UnsupportedClassVersionError`: classfile exceeds what the runtime supports.
- `NoSuchMethodError`: dependency version mismatch.
- `FindException: Module ... not found`: module is not observable/resolvable.

A layer-accurate classification table helps avoid modifying descriptors or adding unnecessary JARs.

## 31. Useful JDK Commands When Investigating

### 31.1. Identify the JDK runtime

~~~bash
java -version
java --list-modules
~~~

`--list-modules` lists the modules of the current runtime image, and does not replace an application module inventory.

### 31.2. Read the module descriptor in a JAR

~~~bash
jar --describe-module --file lib/catalog.jar
~~~

Very useful for automatic module names and explicit descriptors.

### 31.3. Describe module according to the launcher

~~~bash
java --module-path mods \
  --describe-module com.acme.catalog
~~~

Shows information about the module found on the configured module path.

### 31.4. Observe resolution

~~~bash
java --show-module-resolution \
  --module-path "mods:lib" \
  --module com.acme.app/com.acme.app.Main
~~~

Save the output to compare environments.

### 31.5. Analyze static dependencies

~~~bash
jdeps --module-path "mods:lib" --summary app.jar

jdeps --module-path "mods:lib" --check com.acme.app

jdeps --jdk-internals app.jar
~~~

Appropriate syntax and options should be checked against `jdeps --help` of the target JDK. `jdeps` does not necessarily recognize reflective/dynamic dependencies.

### 31.6. Inspect contents and bytecode

~~~bash
jar --list --file app.jar
javap -verbose -classpath app.jar com.acme.app.Main
~~~

Used to confirm class existence, package path, and classfile version. They do not by themselves prove module readability.

## 32. JPMS Migration Test Matrix

A regression plan may include:

| Axis | Combinations to test |
|---|---|
| JDK | Old supported JDK, target JDK |
| Launch mode | Classpath, module path if both are supported |
| Dependency | Baseline versions, target versions |
| Module type | Explicit, automatic, and legacy classpath bridge |
| Runtime image | Appropriate full JDK/JRE, custom jlink if present |
| Packaging | Modular JAR, distribution, framework executable JAR |
| Plugins | No plugin, one plugin, multiple plugins |
| Platform | Linux/Windows/container as committed |
| Tests | Compile, resolution, service discovery, reflection, integration |
| Rollback | Old artifact/runtime with still-compatible configuration/data |

It is not mandatory for every cell to pass. The goal is to have evidence for **the combinations the organization commits to supporting** and block misconfigurations before production.

### 32.1. Smoke tests must run the exact production command

Example:

~~~bash
java --module-path "dist/mods:dist/lib" \
  --show-module-resolution \
  --module com.acme.app/com.acme.app.Main
~~~

A unit test run using the IDE classpath is not sufficient evidence that the production application will resolve modules properly.

## 33. A Specific Migration Case from Java 8 to Java 21

Legacy application:

~~~text
lib/
├── app.jar
├── legacy-api.jar
├── legacy-impl.jar
└── logging.jar
~~~

It runs:

~~~bash
java -cp "lib/*" com.acme.app.Main
~~~

The project team creates a descriptor:

~~~java
module com.acme.app {
    requires legacy.api;
    requires legacy.impl;
    requires java.logging;
}
~~~

and switches the launcher:

~~~bash
java --module-path lib \
  --module com.acme.app/com.acme.app.Main
~~~

Errors may appear in sequence:

1. `module legacy.api not found` because the actual automatic module name is different.
2. After fixing the name, `reads package com.vendor.common from both ...` because legacy-api and legacy-impl share the package.
3. After fixing the split package, providers are not found because ServiceLoader/module registration is not yet correct.
4. After providers can be loaded, framework reflection into the entity package is blocked.
5. After opening the package to the proper scope, the app is missing the runtime JDBC driver because the distribution copy omitted the dependency.

A controlled strategy:

**Step 1:** save the baseline classpath command, dependency versions, and artifact checksums.

**Step 2:** inventory module names using `jar --describe-module`, distinguishing automatic and explicit.

**Step 3:** lock down runtime dependency versions; remove duplicate JARs.

**Step 4:** fix ownership of split packages or choose a valid bridge.

**Step 5:** write `requires`/`exports`/`opens`/`uses`/`provides` descriptors matching the architecture.

**Step 6:** confirm build/test tooling runs on the new JDK with the module path.

**Step 7:** build a distribution containing all modules and dependencies, without relying on developer machine caches.

**Step 8:** verify resolution on the final artifact.

**Step 9:** run integration tests with resources, JDBC, plugins, reflection, and external services.

**Step 10:** have a clear artifact/runtime/launcher rollback plan.

Do not add batches of flags uncontrollably every time an error appears at a different layer.

## 34. When to Keep Classpath First, Modularize Later?

Not every JDK upgrade forces an application to switch to JPMS named modules. If frameworks/dependencies still support the classpath, it can be split:

~~~text
Java 8 + classpath
       |
       | Only change runtime, toolchain, and compatibility fixes
       v
Java 21 + classpath
       |
       | After stabilizing, design module boundaries
       v
Java 21 + explicit JPMS modules
~~~

Benefits:

- Separates JDK/runtime errors from module graph errors.
- Makes it easier to compare behavior and test compatibility.
- Does not force fixing all split packages simultaneously.
- Allows time to coordinate with vendors of legacy libraries.
- Easier to roll back one phase instead of both.

If the product genuinely requires `jlink`/named modules or plugin layers, a JPMS roadmap must be established; do not postpone indefinitely without ownership.

## 35. Quick Diagnosis Table

| Symptom | Suspected layer | First step |
|---|---|---|
| `module not found: X` at compile time | Compiler module path/module name | `module-info.java` and JAR descriptor |
| `FindException: Module X not found` | Runtime discovery | Runtime module path/artifact |
| JAR is present but module is not active | Root/resolution graph | `--show-module-resolution` |
| Two modules with same name | Duplicate artifact/module definitions | Choose one runtime version |
| `reads package p from both A and B` | Split package/readability | Find package owners |
| `package p exists in another module` | Package ownership | Source/JAR entries |
| `package p is not visible` | Readability/exports | `requires` and `exports` |
| `InaccessibleObjectException` | Reflection openness | `opens`/library compatibility |
| `ServiceConfigurationError` | Provider registration/loader | `uses/provides`, service metadata |
| `ClassNotFoundException` | Dynamic loading/classpath | Loader and runtime dependency |
| `NoSuchMethodError` | Binary mismatch | Actual JAR version loaded |
| `ClassCastException` same class name | Different defining loaders | Duplicate API JARs, plugin loader |
| Full JDK runs, jlink image fails | Missing system modules | `--list-modules` on image |
| CI passes, production fails | Different JDK/path/packaging | Compare command, artifact digest |

Do not draw conclusions solely from the outermost exception name. Inspect the stack trace, runtime version, module graph, and actual artifacts.

## 36. Common Misconceptions

**"A JAR on the module path means it is already resolved."** False: observable differs from resolved.

**"Module name matches artifactId."** Not necessarily: the descriptor/manifest must be checked.

**"Adding `--add-modules` fixes every module not found."** Not if the module is non-observable or the name is wrong.

**"`--add-opens` fixes module not found."** No: opens only affects reflective access.

**"Only duplicate class names are split packages."** False: the same package name alone can cause conflicts when the graph requires it.

**"Automatic modules solve all legacy classpath issues."** No: they can expose split packages and naming problems.

**"requires is synonymous with access to every class."** No: exports is needed.

**"The Maven/Gradle dependency tree is the module graph."** No: build dependency selection and JPMS resolution have different rules.

**"Using jlink definitely keeps all system modules."** No: the runtime image is built according to a module set.

**"Fixing startup to succeed means plugins also run."** Not sufficient: ServiceLoader, ModuleLayer, reflection, and dynamic loading can fail late.

**"Upgrading the JDK always requires adding module-info.java."** No: the classpath remains a valid model for many applications.

## 37. Deployment and Investigation Checklist

- [ ] Identified the actual JDK vendor/version and runtime image.
- [ ] Recorded the exact launcher command/working directory.
- [ ] Distinguished classpath, module path, and module-source-path.
- [ ] Checked module names with `jar --describe-module`.
- [ ] Identified which dependencies are explicit/automatic/unnamed.
- [ ] Checked compile and runtime module paths separately.
- [ ] Determined root modules, `requires`, and transitive readability.
- [ ] Checked whether `requires static` is genuinely optional at runtime.
- [ ] Checked `--add-modules`/`--limit-modules` in scripts.
- [ ] Removed duplicate module versions/names.
- [ ] Determined package ownership and split packages.
- [ ] Distinguished duplicate classes from duplicate packages.
- [ ] Checked `exports`/`opens` and appropriate access permissions.
- [ ] Checked ServiceLoader `uses`/`provides`.
- [ ] Checked class loaders/module layers when plugins are present.
- [ ] Checked annotation processors, agents, and ORM/test reflection.
- [ ] Confirmed the full JDK or jlink image contains the required system modules.
- [ ] Checked Maven/Gradle compiler/test/package configuration.
- [ ] Ran a production-like module resolution smoke test.
- [ ] Ran integration tests on the final artifact/runtime.
- [ ] Recorded module graph/JAR hashes and exceptions.
- [ ] Established a rollback plan for the build artifact and launcher.
- [ ] Avoided letting temporary `--add-opens`/`--patch-module` become a permanent solution without an owner.

## 38. Conclusion

**Module not found**, **duplicate package**, and **JPMS module resolution** errors point to problems at different layers. A module may be non-observable; present yet not resolved; resolved yet not readable; or readable yet not exporting/opening the package the consumer needs. Two modules can create a conflict when a reader sees the same package from multiple sources. At the same time, classloaders, plugin discovery, and custom runtime images produce errors with similar symptoms yet different root causes.

The right approach is to start from **module names, artifact inventory, and the actual launch command**, use `jar --describe-module` and `--show-module-resolution` to inspect the graph, remove duplicate versions, resolve package ownership, and then check exports/opens, ServiceLoader, and dynamic layers. Do not blindly patch by adding every JAR or opening every JDK package.

In Java Advance Compatibility Migration, when conditions allow, **upgrade the JDK and stabilize the runtime first, then modularize later in a separately tested phase**. A JPMS system is considered ready only when the module graph, deployment artifact, and critical business flows are verified on the exact target JDK and operating environment.