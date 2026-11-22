# Split Packages Across Multiple Libraries

In Java, a package can appear in multiple JAR files while an application still runs on the classpath. When migrating those libraries to the Java Platform Module System (JPMS), that same package can create conflicts between named modules. This is a common issue when modularizing a legacy system, upgrading dependencies, or combining independently developed libraries.

A **split package** is a situation where different modules or artifacts both contain classes belonging to a package with the same fully qualified name. For example, both `library-a.jar` and `library-b.jar` contain classes in the package `com.acme.shared`. On the classpath, the classloader can find classes from both JARs; on the module path, the two JARs can become two separate modules and cause module resolution to fail if a module reads both modules that export that package.

A sustainable approach is to determine who owns the package, then merge the parts belonging to the same module, separate the packages into distinct namespaces, or extract the shared API into an independent module.

## 1. What Is a Split Package?

A package is identified by its package name, such as `com.acme.shared`. The following classes belong to the same package:

~~~java
package com.acme.shared;

public class JsonCodec {
}
~~~

~~~java
package com.acme.shared;

public class XmlCodec {
}
~~~

If the two classes reside in the same module, there is no split package between modules. However, if `JsonCodec` is in module `com.acme.json` and `XmlCodec` is in module `com.acme.xml`, both modules contain the package `com.acme.shared`.

Example structure:

~~~text
lib/
├── library-json.jar
│   └── com/acme/shared/JsonCodec.class
└── library-xml.jar
    └── com/acme/shared/XmlCodec.class
~~~

The JAR filename does not determine package ownership. You need to inspect the class entries inside each JAR and the corresponding module descriptor.

Split packages can arise when:

- Two independent libraries accidentally choose the same package name.
- A large library is split into multiple JARs while keeping the same internal package.
- A legacy library places classes of multiple components in a shared package.
- An application adds a class to a package that belongs to a third-party library.
- A dependency is replaced or upgraded, causing a package that previously had one owner to appear in multiple modules.

Reverse-domain package naming like `com.vendor.product` helps reduce the chance of collisions, but does not by itself guarantee there are no split packages if artifacts use the same namespace.

## 2. Why Does the Classpath Often Hide Split Packages?

Before JPMS, many applications placed JARs on the classpath:

~~~bash
java -cp "lib/library-json.jar:lib/library-xml.jar:app.jar" com.acme.app.Main
~~~

On Windows, the classpath separator is a semicolon:

~~~powershell
java -cp "lib/library-json.jar;lib/library-xml.jar;app.jar" com.acme.app.Main
~~~

Classes on the classpath belong to the unnamed module of the corresponding classloader. Multiple JARs can contribute classes to the same package of the unnamed module. Therefore, two JARs both containing the package `com.acme.shared` can often still run without encountering a named-module split package error.

However, the classpath does not make duplicate classes safe:

- If two JARs contain the same fully qualified class name, such as `com.acme.shared.Codec`, the classloader typically loads the version found first in search order.
- Changing JAR order can alter behavior.
- Duplicate resource names can be found according to classloader order.
- One part of the package may rely on package-private access or assumptions about being in the same codebase; when splitting modules, those assumptions may no longer hold.

Thus, the fact that an application runs on the classpath does not prove the libraries have sound module boundaries. Moving to the module path exposes existing ownership issues.

## 3. How Does JPMS Detect Conflicts?

Suppose two modular JARs have descriptors:

`library-json.jar`:

~~~java
module com.acme.json {
    exports com.acme.shared;
}
~~~

`library-xml.jar`:

~~~java
module com.acme.xml {
    exports com.acme.shared;
}
~~~

Application:

~~~java
module com.acme.app {
    requires com.acme.json;
    requires com.acme.xml;
}
~~~

Both dependency modules export the package `com.acme.shared` to the app module. When resolving the graph, app reads both modules yet sees the same package name from two different modules. The module system cannot provide a single package with clear ownership to the module reading both; resolution can fail with a split package error.

The error message may look like:

~~~text
java.lang.module.ResolutionException:
Modules com.acme.json and com.acme.xml
export package com.acme.shared to module com.acme.app
~~~

Depending on the JDK and how it is launched, the error may appear wrapped in a `FindException` or as a message from the launcher. What to look for in the message are the two modules, the overlapping package name, and the module reading both.

The important rule is not merely "having two JAR files with an overlapping package." Look at which modules those JARs are recognized as, which modules are in the configuration, and which module reads the overlapping exported packages. Some split package cases do not immediately produce an error if the modules are not resolved together or no module reads both overlapping exported packages. However, relying on that to design a system is still very fragile; avoid having packages with multiple owners in the same module graph.

## 4. Automatic Modules Can Also Create Split Packages

A JAR without `module-info.class` when placed on the module path typically becomes an automatic module, with its name derived from the JAR filename or metadata such as `Automatic-Module-Name`.

Automatic modules have characteristics convenient for migration:

- Treated as a named module with a module name.
- Export their packages.
- Have broader readability than ordinary modules.
- Can participate in the module graph alongside explicit modules.

However, automatic modules do not resolve split packages. If two automatic modules both contain and export the package `com.acme.shared`, a module reading both can still encounter a similar resolution error.

Example of two JARs without descriptors:

~~~text
lib/
├── library-json-1.0.jar
└── library-xml-1.0.jar
~~~

If both JARs contain `com/acme/shared/` and are placed on the module path, inspect the automatic module names and the packages they contain. Do not assume that merely because a JAR lacks `module-info.java` it will continue to behave like the classpath.

## 5. How to Detect Split Packages in Dependencies

You should inspect before migrating the entire application from the classpath to the module path.

### List the contents of each JAR

~~~bash
jar --list --file lib/library-json.jar
jar --list --file lib/library-xml.jar
~~~

Look for entries sharing the same package prefix, for example:

~~~text
com/acme/shared/JsonCodec.class
com/acme/shared/XmlCodec.class
~~~

If you need a quick comparison, focus on package paths ending with a slash, such as `com/acme/shared/`. Do not compare only class names: a split package can exist even when two JARs contain different classes in the same package.

### Inspect module names and descriptors

~~~bash
jar --describe-module --file lib/library-json.jar
jar --describe-module --file lib/library-xml.jar
~~~

For explicit modules, check the `exports` directives. For automatic modules, the output shows the inferred module name and exported packages.

You can use `java --describe-module` once the module is on the module path:

~~~bash
java --module-path lib --describe-module com.acme.json
~~~

### Inspect the graph at runtime

~~~bash
java --show-module-resolution --module-path "lib:mods" --module com.acme.app/com.acme.app.Main
~~~

This command helps determine which modules are actually resolved and their module location sources. If resolution stops due to a split package, combine the error message with descriptors and JAR contents to find the two conflicting modules.

### Validate the module path

You can ask the launcher to validate observable modules:

~~~bash
java --module-path lib --validate-modules
~~~

This command is useful for detecting certain module configuration issues before running the main class. Results depend on the set of modules provided by the module path and the applicable resolution rules.

### Static dependency analysis

~~~bash
jdeps --module-path lib --check com.acme.app
~~~

`jdeps` helps check dependencies and module consistency. It does not replace checking the package contents of each JAR; when suspecting a split package, you still need to inspect the artifact's entries and descriptor.

## 6. Strategy 1: Merge JARs Belonging to the Same Module

If two JARs are parts of the same logical library and the same team owns the package, the solution may be to package them into a single module.

For example:

~~~text
Before:
library-json.jar  -> com.acme.shared.JsonCodec
library-xml.jar   -> com.acme.shared.XmlCodec

After:
com.acme.codec.jar
  module com.acme.codec
  -> com.acme.shared.JsonCodec
  -> com.acme.shared.XmlCodec
~~~

Module descriptor after merging:

~~~java
module com.acme.codec {
    exports com.acme.shared;
}
~~~

The application only needs:

~~~java
module com.acme.app {
    requires com.acme.codec;
}
~~~

Merging can be done with a build tool, an assembly process, or by creating a new modular JAR. When packaging, check carefully:

- Duplicate class entries: do not let two versions unintentionally overwrite a class.
- Resources and service provider configurations: preserve required contents properly.
- Native libraries and configuration files: place them in the right locations and preserve loading behavior.
- Module metadata: there should only be one `module-info.class` appropriate for the final module.
- Licenses and notices: preserve full information from distributed dependencies.

Do not merely concatenate the bytes of the JARs together. A final module needs a valid archive structure and descriptor.

## 7. Strategy 2: Rename Packages So Each Library Has Its Own Namespace

If two libraries are genuinely independent and do not belong to the same module, the clear approach is to rename packages so they do not share ownership of a package name.

Before:

~~~text
com.acme.shared.JsonCodec
com.acme.shared.XmlCodec
~~~

After:

~~~text
com.acme.json.shared.JsonCodec
com.acme.xml.shared.XmlCodec
~~~

The descriptors:

~~~java
module com.acme.json {
    exports com.acme.json.shared;
}
~~~

~~~java
module com.acme.xml {
    exports com.acme.xml.shared;
}
~~~

Advantages:

- Clear package ownership.
- No duplicate exported packages in the module graph.
- Easy to develop and release independently.
- Less reliance on JAR order or classloaders.

Renaming a package is a binary API change and can affect client source code. If the library is already widely used, you need a migration plan: releasing a new version, providing adapters, or an appropriate deprecation period.

## 8. Strategy 3: Extract the Shared API into a Separate Module

Sometimes two libraries contain the same package because they share some API types. Instead of letting each library package a copy, you can extract the shared types into a single API module.

For example:

~~~text
com.acme.codec.api
    com.acme.codec.spi.Codec

com.acme.codec.json
    com.acme.codec.json.JsonCodec

com.acme.codec.xml
    com.acme.codec.xml.XmlCodec
~~~

API module:

~~~java
module com.acme.codec.api {
    exports com.acme.codec.spi;
}
~~~

JSON module:

~~~java
module com.acme.codec.json {
    requires com.acme.codec.api;
    provides com.acme.codec.spi.Codec
        with com.acme.codec.json.JsonCodec;
}
~~~

XML module:

~~~java
module com.acme.codec.xml {
    requires com.acme.codec.api;
    provides com.acme.codec.spi.Codec
        with com.acme.codec.xml.XmlCodec;
}
~~~

Service-consuming application:

~~~java
module com.acme.app {
    requires com.acme.codec.api;
    uses com.acme.codec.spi.Codec;
}
~~~

Each package has one owning module. Providers depend on the API module and implement the shared interface without repackaging API classes. This creates clear module boundaries and lets you swap providers without making consumers depend directly on implementations.

## 9. Strategy 4: Use the Classpath During the Transition Phase

If dependencies cannot be modularized immediately, you can continue keeping some JARs on the classpath during migration. They will then belong to the unnamed module rather than becoming multiple separate named modules.

For example:

~~~bash
java --module-path mods --class-path "legacy-a.jar:legacy-b.jar" --module com.acme.app/com.acme.app.Main
~~~

On Windows:

~~~powershell
java --module-path mods --class-path "legacy-a.jar;legacy-b.jar" --module com.acme.app/com.acme.app.Main
~~~

A named module does not automatically read the unnamed module in the usual way. If a module needs classes from the classpath, you must design an appropriate bridge/migration; do not assume that simply adding JARs to `--class-path` makes them accessible to the app module.

The classpath can serve as a transitional step for applications that cannot be split into modules right away, but risks of duplicate classes and search-order dependence remain. Document legacy dependencies and aim to gradually eliminate duplicate packages.

## 10. --patch-module Is Not a Normal Way to Merge Libraries

The `--patch-module` option allows adding or replacing classes/resources in an existing module. It is useful for testing, instrumentation, or certain controlled migration scenarios.

For example:

~~~bash
java --patch-module com.acme.library=patches/com.acme.library   --module-path mods   --module com.acme.app/com.acme.app.Main
~~~

Contents in the patch directory are treated as part of the specified module. This differs from creating a second module that contains the same package.

Do not use `--patch-module` as the default way to merge two independent libraries. Patching can alter runtime module contents and create discrepancies between test and production environments. If two JARs genuinely belong to the same module, produce a merged module artifact in the build process so the result is reproducible.

Similarly, `--add-exports` and `--add-reads` only adjust access permissions/readability. They do not remove duplicate packages and do not merge two modules into one module.

## 11. Workflow for Handling a Real Split Package

When module resolution reports that a package is exported from two modules, follow this order:

1. Record the exact package name and the two modules cited in the error.
2. Use `jar --list --file` to confirm both JARs actually contain that package.
3. Use `jar --describe-module` to determine whether they are explicit or automatic modules and inspect exports.
4. Use `--show-module-resolution` to identify which modules are being resolved and from which paths.
5. Determine whether the two artifacts belong to the same logical library or are two independent owners.
6. If they belong to the same logical module, merge the artifacts into a single module.
7. If independent, rename packages or extract the shared API part into a separate module.
8. Compile and rerun from clean outputs; verify the module graph and resolved dependencies.
9. Test consumers of the libraries because renaming packages or merging artifacts can affect APIs and resources.

Do not fix the error by arbitrarily deleting a JAR from the module path if the application still needs classes in that JAR. Identify which classes are being used and move them to the right owning module.

## 12. Common Pitfalls

**The application runs on the classpath but not on the module path.** Two JARs may both contain the same package, and upon becoming named/automatic modules, resolution detects the conflict. Inspect each JAR's module descriptor and package entries.

**Different classes only, yet still a split package.** Split packages are based on package names, not requiring the two JARs to have the same class names. `JsonCodec` in one JAR and `XmlCodec` in another JAR is still a split package if they share the same package and belong to two modules.

**Two JARs have the same module name.** This is a different issue: duplicate module names on the module path. Check `Automatic-Module-Name` or `module-info.class`; renaming the file does not necessarily change the module name.

**Used --add-exports yet the error persists.** Exports control package access permissions. If two modules both export a package to a module reading both, adding exports does not resolve the ownership conflict.

**Merged JARs yet multiple module-info.class files exist.** The final artifact should have only one appropriate descriptor. Configure the build tool to generate the final descriptor rather than keeping multiple input descriptors.

**Moving classes to a new package breaks consumer compilation.** This is an API change. Update imports, module descriptors, and dependencies; if compatibility is needed, release an adapter or transitional version.

**A package appears in multiple JARs without immediately throwing an error.** The modules might not be resolved together or no module reads both exported packages. Do not treat that as a safety guarantee; when the root set or dependencies change, conflicts can emerge.

## 13. Practice

1. Create two modular JARs `com.acme.json` and `com.acme.xml`, both containing the package `com.acme.shared` and exporting that package.
2. Create an app module requiring both modules. Compile and run to observe the resolution error.
3. Use `jar --list --file` and `jar --describe-module` to identify the exact overlapping package and module owners.
4. Try merging the two libraries into one module `com.acme.codec`, update app, and rerun.
5. Create a second variant by renaming the packages to `com.acme.json.shared` and `com.acme.xml.shared`; verify the graph no longer has duplicate exported packages.
6. Create a shared API module and two independent providers; use `ServiceLoader` to observe how to share an API without sharing package ownership.
7. Run `java --show-module-resolution` and `java --validate-modules` to compare results before and after refactoring.

When modularizing multiple libraries, treat the package as an ownership unit that must be explicitly managed. Each package should have one owner in the module graph used by the application. Merge when JARs belong to the same logical module; change namespaces or extract shared APIs when they need to exist independently. That way module resolution becomes predictable and dependencies no longer rely on JAR ordering on the classpath.
