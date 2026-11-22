# Why a Package Cannot Be Split Between Named Modules

## 1. Objectives

In the Java Platform Module System (JPMS), a package is the unit of organization for classes and interfaces; a module is the unit that groups multiple packages into a component with dependency and encapsulation boundaries. A package can contain multiple compilation units, but when placing modules into the same modular application, a package needs to have a clear visible source for each module that uses it.

A common error-causing situation is a **split package**: the same package name, for example com.acme.shared, appears in multiple named modules. A consuming module reads both modules and both export that package. In that case, the compiler and module resolver cannot treat the package as a single set of types with a clear owning source.

This article explains:

- Why a package needs a single visible source for each consumer.
- The exact JPMS rules and the cases that create conflicts.
- Why exports, requires, and class loaders are involved.
- How to detect and fix split packages when splitting a large library into multiple modules.
- Runtime exceptions to distinguish so as not to interpret the rule too rigidly.

**Scope note:** JPMS does not simply forbid every case where two modules anywhere have the same package name. The key rule is that a package must be uniquely visible to the module being compiled. However, in typical application architecture, you should design so that one package belongs to a single named module; this avoids conflicts when the module graph changes and is compatible with creating layers that share a single class loader.

## 2. Distinguishing Packages and Modules

Packages group types by their fully qualified names:

~~~java
package com.acme.shared;

public final class Ids {
    private Ids() {}

    public static String newId() {
        return java.util.UUID.randomUUID().toString();
    }
}
~~~

A module can contain multiple packages:

~~~text
com.acme.orders
  ├── com.acme.orders.api
  ├── com.acme.orders.domain
  └── com.acme.orders.internal
~~~

A module descriptor defines dependencies and which packages are exposed:

~~~java
module com.acme.orders {
    requires com.acme.customer.api;

    exports com.acme.orders.api;
}
~~~

Package names and module names are two separate namespaces:

- **com.acme.orders** can be a module name.
- **com.acme.orders.api** is a package name.
- Module com.acme.orders can contain multiple packages, of which some are exported and others are kept internal.

Dotted package names express naming structure. A subpackage is not automatically part of its parent package. For example, com.acme.shared and com.acme.shared.internal are two different packages. Therefore, having one module contain com.acme.shared while another contains com.acme.shared.internal does not by itself create a split package.

## 3. What Is a Split Package?

Suppose a legacy library contains two groups of classes in the same package:

~~~text
legacy-library/
  com/acme/shared/
    Ids.java
    StringUtils.java
    DateUtils.java
    JsonSupport.java
    XmlSupport.java
~~~

When splitting it into two modules by functionality, a developer might divide the files as follows:

~~~text
module com.acme.shared.core
  com.acme.shared.Ids
  com.acme.shared.StringUtils
  com.acme.shared.DateUtils

module com.acme.shared.formats
  com.acme.shared.JsonSupport
  com.acme.shared.XmlSupport
~~~

Both modules contain the package com.acme.shared. This is a split package.

If both modules export this package:

~~~java
module com.acme.shared.core {
    exports com.acme.shared;
}
~~~

~~~java
module com.acme.shared.formats {
    exports com.acme.shared;
}
~~~

and the application reads both:

~~~java
module com.acme.application {
    requires com.acme.shared.core;
    requires com.acme.shared.formats;
}
~~~

then application sees the package com.acme.shared exported from two modules. The package is no longer uniquely visible to application. Module resolution fails rather than picking one source arbitrarily.

The key point to understand is that the error is not simply because two directories on disk have the same name. It stems from the module graph and exports/readability relationships: the consumer module sees the same package from multiple modules.

## 4. The Uniquely Visible Rule in the JLS

JLS Java SE 21, section **7.4.3 — Package Observability and Visibility**, defines when a package is uniquely visible to a module M.

There are two cases:

1. A compilation unit belonging to module M declares that package, and M does not read any other module that exports that package to M.
2. No compilation unit belonging to M declares that package, and M reads exactly one other module that exports that package to M.

If neither of these two cases holds, the package is not uniquely visible to M.

This can be illustrated in a table:

| Situation for consumer module M | Result |
|---|---|
| M itself contains package p, and no other readable module exports p to M | p is uniquely visible from M |
| M does not itself contain p, and only one module read by M exports p to M | p is uniquely visible from that module |
| M does not itself contain p, and two modules read by M both export p to M | Conflict, not uniquely visible |
| M itself contains p, and another module read by M also exports p to M | Conflict, not uniquely visible |

Module resolution has a corresponding consistency check. Resolution fails if two or more modules in a configuration export the same package to a module that reads both. The case where module M itself contains package p yet reads another module exporting p to M also falls into the conflict category.

This explains why a module can compile in isolation yet fail when integrated into a larger application: the new module is placed in a graph with additional dependencies, causing a previously uniquely visible package to have multiple sources.

## 5. Why Does JPMS Need This Rule?

### Avoiding package names with multiple sources in the same compilation context

When source code in module M writes:

~~~java
import com.acme.shared.Ids;
~~~

the compiler needs to determine where the package com.acme.shared and the type Ids come from. If M reads two modules that both export this package, name resolution does not have a single package source under the JLS rules.

You should not rely on module path order, JAR order, or dependency order to decide which type wins. JPMS requires an explicit module graph rather than allowing an implicit classpath search order to determine the API.

### Keeping module boundaries meaningful

Modules are designed to group related packages into a component. If the same package is split across multiple modules, users have difficulty knowing which module owns the API, which module is responsible for compatibility, and which module needs to be upgraded together with the other.

Having a single package in a single module helps the descriptor clearly define:

- Which module owns the types of the package.
- Which modules can read the package through requires.
- Which modules can access public types through exports.
- Which internal implementations remain hidden within the module.

### Avoiding dependence on class loading behavior

A class loader needs to find the module responsible for a package when loading a type. If multiple modules are defined for one class loader while containing the same package, mapping a package to a module becomes ambiguous.

The **ModuleLayer.defineModulesWithOneLoader** API refuses to create a layer when two or more modules in the configuration have overlapping packages. This is a concrete runtime constraint of the single-shared-class-loader model.

With multiple class loaders, the runtime can isolate modules with identically named packages in advanced scenarios. That does not turn them into a shared package and does not remove exports/readability consistency checks in the module configuration.

## 6. How requires and exports Combine to Create Conflicts

The two directives have different roles:

- **requires** creates a dependency and readability from the declaring module to the required module.
- **exports** allows eligible modules to access public types in the package.

For example:

~~~java
module com.acme.lib.one {
    exports com.acme.shared;
}
~~~

~~~java
module com.acme.lib.two {
    exports com.acme.shared;
}
~~~

~~~java
module com.acme.application {
    requires com.acme.lib.one;
    requires com.acme.lib.two;
}
~~~

Application reads both lib.one and lib.two; both export com.acme.shared to application. This is a conflict.

If only one module exports the package to application, that module can be the single source that application sees. However, keeping one physical package across multiple modules is still a fragile design: adding a requires, changing qualified exports to unqualified exports, or changing how layers are created can push the graph into a conflicting state.

### requires transitive can cause conflicts to appear indirectly

Suppose application only requires facade:

~~~java
module com.acme.application {
    requires com.acme.facade;
}
~~~

But facade declares:

~~~java
module com.acme.facade {
    requires transitive com.acme.lib.one;
    requires transitive com.acme.lib.two;
}
~~~

Application reads both lib.one and lib.two because of the transitive edges. If both modules export the same package to application, the conflict still occurs even though application does not directly declare requires for each module.

When investigating split packages, you must examine the entire readability graph, including requires transitive, rather than looking only at the application's module-info.java.

## 7. Can Qualified Exports Solve It?

A qualified export only exports a package to a specific set of modules:

~~~java
module com.acme.lib.one {
    exports com.acme.shared to com.acme.application;
}
~~~

~~~java
module com.acme.lib.two {
    exports com.acme.shared to com.acme.plugin;
}
~~~

If application only reads lib.one and does not receive the export of com.acme.shared from lib.two, the package can be uniquely visible to application from lib.one.

However, qualified exports only restrict who sees the package. They do not merge the two parts of the package, do not make package-private members shared between the two modules, and do not automatically resolve every other consumer configuration.

You should not use qualified exports to mask a split package that lacks clear design boundaries. They can be appropriate in an intentional architecture with multiple isolated consumer modules, but each consumer's graph must be controlled.

### opens does not replace exports

**opens** serves deep reflection at runtime. It does not make a package exported for ordinary Java access at compile time. Therefore, adding opens is not a fix for a package-not-uniquely-visible error during source compilation.

## 8. Why Cannot You Rely on Package-Private to Split a Package?

In a normal Java package, types and members without an access modifier typically have package access. This often makes developers want to split classes of the same package into multiple modules to preserve internal access.

For example:

~~~java
package com.acme.shared;

final class InternalCache {
    static Object load() {
        return new Object();
    }
}
~~~

~~~java
package com.acme.shared;

public final class PublicFacade {
    public Object get() {
        return InternalCache.load();
    }
}
~~~

In a single-module model, PublicFacade can use InternalCache because both belong to the same package of the module.

When moving the two classes into two named modules, writing the same package com.acme.shared line does not turn the two modules into one shared internal package. Module boundaries and class loader/module identity still apply; package-private access is not a mechanism for sharing APIs between two modules.

If a class in another module needs to be called, design a clear public API in an exported package. If an implementation must use package-private internals of the facade, keep those classes in the same module.

## 9. Can Subpackages Reside in Different Modules?

Yes. A parent package and a subpackage are two different packages.

For example:

~~~text
module com.acme.shared.api
  com.acme.shared.api

module com.acme.shared.internal
  com.acme.shared.internal
~~~

API module:

~~~java
module com.acme.shared.api {
    exports com.acme.shared.api;
}
~~~

Internal module:

~~~java
module com.acme.shared.internal {
    requires com.acme.shared.api;
}
~~~

This is not a split package because the two package names are different. The packages com.acme.shared.api and com.acme.shared.internal have a hierarchical naming relationship but no special package-private access relationship.

Splitting subpackages across modules is a valid organization approach, provided dependencies and exports are declared clearly. Do not assume that code in com.acme.shared.internal automatically accesses package-private members of com.acme.shared.api.

## 10. Runtime Layer and Class Loader Cases

Two questions must be distinguished:

1. **Module resolution:** is the package uniquely visible to consumer modules according to readability and exports?
2. **Layer/class loader:** can the resolved modules be mapped to the chosen class loader(s) to load types?

When using:

~~~java
ModuleLayer.defineModulesWithOneLoader(
        configuration,
        List.of(ModuleLayer.boot()),
        ClassLoader.getSystemClassLoader());
~~~

every module in the configuration is defined to the same class loader. The API specifies that the operation can fail with **LayerInstantiationException** if two or more modules have overlapping packages.

With:

~~~java
ModuleLayer.defineModulesWithManyLoaders(
        configuration,
        ClassLoader.getSystemClassLoader());
~~~

each module is defined in its own class loader. This can isolate identically named packages across modules in advanced runtime scenarios. However:

- Each module remains a separate module.
- Types with the same fully qualified name loaded from different modules/class loaders do not become the same type.
- Consumers still must satisfy readability and exports rules.
- A consumer cannot read two modules that both export that package to it and still have the package uniquely visible.

Therefore, multiple class loaders are a runtime isolation mechanism, not a way to design a package shared across modules.

## 11. Automatic Modules and Legacy Libraries

When a JAR without module-info.class is placed on the module path, it can become an automatic module. Automatic modules have several broad rules:

- The module name is derived from the JAR name or corresponding metadata.
- An automatic module reads the modules enumerated in the configuration.
- Packages in an automatic module are exported according to automatic module rules.

This can easily expose legacy split packages when migrating libraries from the classpath to the module path. Two legacy libraries may both contain the package com.vendor.common; on the classpath, class loader search order may allow the application to keep running. When they become automatic modules and the modules are read together, broad exports can create conflicts.

When modularizing legacy libraries:

1. Check the actual packages in each JAR.
2. Identify which packages overlap between dependencies.
3. Determine whether a consumer module reads both of those modules.
4. Prefer upgrading or replacing libraries with overlapping packages.
5. If needed, relocate the packages of one library via shading/bytecode relocation before putting it on the module path.
6. Only use the classpath or automatic modules as an intentional transitional step, not as a long-term architectural solution.

## 12. How to Detect Split Packages

### Inventory packages in JARs

List the JAR contents:

~~~text
jar --list --file library-one.jar
jar --list --file library-two.jar
~~~

Look for duplicate package paths, for example:

~~~text
com/acme/shared/Ids.class
com/acme/shared/StringUtils.class
~~~

You can use a script or build tool to generate a package list from .class entries, skipping META-INF and module-info.class when cataloging type packages.

### Inspect module descriptors

~~~text
jar --describe-module --file library-one.jar
jar --describe-module --file library-two.jar
~~~

This command shows the module name, requires, exports, opens, uses, and provides. For an automatic module, the output can show the packages that the module contains.

### Inspect the module graph

Read all module-info.java files and determine which modules consumers read. Include requires transitive and the root modules selected by the launcher/build tool.

Look for cases where:

- Two modules export the same package to a consumer.
- A consumer itself contains a package and simultaneously reads another module that exports that package to the consumer.
- An automatic module causes more modules to be read and packages to be exported more broadly than expected.

You can use:

~~~text
java --validate-modules --module-path mods
~~~

to ask the launcher to check the module path and whether the modules can resolve under the corresponding configuration. For a real project, run with the exact module path, root modules, and JDK that the application will use; a check command on a different set of modules does not prove the deployment graph is valid.

## 13. How to Fix Split Packages

### Approach 1 — Merge classes of the same package into one module

If the classes need to share package-private APIs or form a single logical unit, keep the entire package in one module:

~~~text
module com.acme.shared
  com.acme.shared.Ids
  com.acme.shared.StringUtils
  com.acme.shared.JsonSupport
  com.acme.shared.XmlSupport
~~~

Other modules simply read the shared module and use the exported public API. This is usually the lowest-risk choice when the package was originally designed as a single unit.

### Approach 2 — Rename packages by responsibility

If the two groups of classes are genuinely two independent APIs, rename the packages to reflect the boundaries:

~~~text
module com.acme.shared.core
  com.acme.shared.core.Ids
  com.acme.shared.core.StringUtils

module com.acme.shared.formats
  com.acme.shared.formats.json.JsonSupport
  com.acme.shared.formats.xml.XmlSupport
~~~

Module descriptors:

~~~java
module com.acme.shared.core {
    exports com.acme.shared.core;
}
~~~

~~~java
module com.acme.shared.formats {
    requires com.acme.shared.core;

    exports com.acme.shared.formats.json;
    exports com.acme.shared.formats.xml;
}
~~~

Consumers can read both without a package collision:

~~~java
module com.acme.application {
    requires com.acme.shared.core;
    requires com.acme.shared.formats;
}
~~~

Renaming a package is an API change. You must update imports, reflection strings, service metadata, serialization configs, framework scanning, tests, and documentation.

### Approach 3 — Create a separate API module

If multiple implementations need to share a contract, place the interfaces and public types into an API module:

~~~text
com.acme.codec.api
  com.acme.codec.Codec
  com.acme.codec.CodecException

com.acme.codec.json
  com.acme.codec.json.JsonCodec

com.acme.codec.xml
  com.acme.codec.xml.XmlCodec
~~~

API module:

~~~java
module com.acme.codec.api {
    exports com.acme.codec;
}
~~~

Provider module:

~~~java
module com.acme.codec.json {
    requires com.acme.codec.api;

    provides com.acme.codec.Codec
        with com.acme.codec.json.JsonCodec;
}
~~~

Implementations use separate packages. Consumers depend on the API module and discover implementations via ServiceLoader or injection configuration. This separates the contract from implementations without splitting a package.

### Approach 4 — Relocate packages of a third-party dependency

If two third-party libraries contain the same package and their sources cannot be modified, you can use shading/relocation to change the package of one dependency during packaging.

For example, relocate:

~~~text
com.vendor.common
~~~

to:

~~~text
com.acme.internal.shaded.vendor.common
~~~

Relocation must update both bytecode references and related metadata. Check reflection, service provider files, resource paths, serialization, native integration, and license obligations. Do not merely rename folders inside the JAR because bytecode still references the old names.

### Approach 5 — Patch a module in intentional situations

The **--patch-module** option allows adding classes/resources into an existing named module. Patched classes become contents of the target module under the patch mechanism.

For example:

~~~text
javac
  --patch-module com.acme.shared=patches/shared
  -d build/test-patch
  ...
~~~

This mechanism is useful for testing, instrumentation, or controlled migration. It does not create two owner modules for the same package; the purpose is to supplement content into a selected module. Do not use patch module as a way to arbitrarily stitch together multiple production libraries with package collisions.

## 14. Why Is Renaming the Module Not Enough?

Suppose you change:

~~~text
com.acme.shared.core
com.acme.shared.extra
~~~

into two different module names, yet both still contain the package:

~~~text
com.acme.shared
~~~

then the package collision remains. The module name only changes the module identifier; it does not change the package name or the uniquely visible rule.

Similarly, renaming a Maven/Gradle artifact, renaming a JAR, or placing files in different directories does not solve a split package if the module graph still exports the same package to a consumer.

To solve it, you must change at least one meaningful factor:

- Package name.
- Module ownership of the classes.
- Readability/exports relationships according to an intentional design.
- Runtime layer/class loader isolation in specialized plugin architectures.

## 15. Package Design Process When Splitting Modules

1. List the packages and types of the current library.
2. Group types by responsibility and cohesion; identify types that require package-private access.
3. Assign each package to one owning module.
4. Create module-info.java with minimal requires and exports.
5. Rename packages if two groups of classes need to belong to independent modules.
6. Extract public APIs into an API module if multiple implementations share a contract.
7. Check requires transitive and automatic modules to detect indirect readability.
8. Inspect input JARs to find duplicate packages.
9. Resolve the module graph with the exact root modules of the application.
10. Create runtime layers according to the actual class loader strategy.
11. Run compile-time and runtime tests on the module path, not just on the classpath.
12. Check reflection, ServiceLoader, resource, and serialization paths after changing packages.

## 16. Common Misconceptions

### Thinking you only need to rename the module

Not enough. The conflict concerns exported packages and visibility to the consumer. Two different module names can still export the same package.

### Thinking a parent package and a subpackage are the same package

Incorrect. com.acme and com.acme.internal are two separate packages. They have a hierarchical naming relationship, but do not share package-private access.

### Thinking all identically named packages across any modules are strictly forbidden

This needs to be stated more precisely. The JLS establishes the uniquely visible rule per consumer module; module resolution checks exports/readability conflicts. Additionally, how layers are created can impose its own constraints. For example, defineModulesWithOneLoader rejects overlapping packages in the configuration, whereas a multiple-class-loader model can isolate modules differently. For typical modular applications, you should still avoid split packages so the graph stays clear and stable.

### Thinking opens can replace exports

No. opens serves deep reflection at runtime; exports is the mechanism that exposes a package for normal Java access between modules.

### Thinking requires transitive only affects the compile-time API

It also affects the readability graph of the consuming module. Therefore, it can cause the consumer to see an additional module exporting a duplicate package.

### Thinking putting one JAR on the classpath has fixed the package collision

The classpath can change how modules are observed, but moving a library into the unnamed module also changes encapsulation and the dependency model. Use it as a controlled transitional solution, not as a way to share a package between named modules.

## 17. Self-Check Exercises and Answers

### Exercise 1 — Two modules exporting the same package

Modules A and B both export com.acme.shared. Module C requires both A and B. What happens?

**Answer:** The package com.acme.shared is exported to C from two modules that C reads. The package is not uniquely visible and module resolution fails.

### Exercise 2 — Consumer reading only one module

A and B both contain com.acme.shared, but only A exports the package to C; C only reads A. Does an exports conflict necessarily occur for C?

**Answer:** No. According to the uniquely visible rule, if C does not itself contain the package and only one module that C reads exports that package to C, the package can be uniquely visible from A. However, you need to check the entire graph and how runtime layers are created.

### Exercise 3 — Subpackages

Module A contains com.acme.shared.api; module B contains com.acme.shared.internal. Is this a split package?

**Answer:** No. The two full names are two different packages. Package hierarchy does not create a package-private access relationship.

### Exercise 4 — requires transitive

C only requires A. A declares requires transitive B. If A and B both export the same package p to C, why can C still fail?

**Answer:** C reads B indirectly through the transitive edge. Module resolution evaluates the final readability graph, not just the direct requires in C's module-info.java.

### Exercise 5 — opens

If B opens com.acme.shared to C without exporting this package, does that create package visibility for C's source code?

**Answer:** No. opens allows deep reflection at runtime; it does not replace exports in source/module access rules.

### Exercise 6 — One class loader

Two modules in the same configuration contain the package com.acme.shared. Can a layer be created using defineModulesWithOneLoader?

**Answer:** No. The ModuleLayer API specifies that a layer sharing a single class loader cannot be created if the modules have overlapping packages; the operation throws LayerInstantiationException.

### Exercise 7 — Multiple class loaders

Does using defineModulesWithManyLoaders turn two identically named packages into one shared package?

**Answer:** No. Each module has its own class loader; this is an isolation mechanism. The readability/exports rules of the module configuration still apply.

### Exercise 8 — Appropriate fix

Two groups of classes need to be released and upgraded independently, and do not need package-private access between them. What should be done?

**Answer:** Separate them into packages with distinct names by responsibility, then export the required APIs and declare requires. If multiple implementations share a contract, create a separate API module.

## 18. Checklist When Reviewing Split Packages

- Have you fully inventoried the packages in each named module/JAR?
- Do two modules both contain the exact same full package?
- Which consumers read those modules, including via requires transitive?
- Do two modules both export a package to a consumer?
- Does a consumer itself contain a package while also reading another module that exports that package?
- Does any automatic module make readability or exports broader than expected?
- Is a parent package being confused with a subpackage?
- Are types needing package-private access kept within the same module?
- Can you rename packages, merge modules, or create a separate API module?
- If using multiple ModuleLayers/class loaders, are boundaries and type identity clearly designed?
- Have you checked with the exact module path and root modules of the deployment?
- Are there compile-time and runtime tests after migrating from the classpath to the module path?

**Key takeaway:** A package needs a single visible source for each consumer module. Conflicts occur when a consumer sees the same package exported from multiple modules, or its own internal package overlaps with a package exported to it by another module. Assign packages along module boundaries, use separate package names for independent components, and only use multiple class loaders when module isolation is truly needed.

## References

- Java Language Specification, Java SE 21 — 7.4.3 Package Observability and Visibility: https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.4.3
- Oracle Java SE 21 API — java.lang.module package summary, Module Resolution: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/package-summary.html
- Oracle Java SE 21 API — ModuleLayer, defineModulesWithOneLoader and defineModulesWithManyLoaders: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html
- Oracle Java SE 21 API — Configuration: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/Configuration.html
- OpenJDK JEP 261 — Module System: https://openjdk.org/jeps/261
