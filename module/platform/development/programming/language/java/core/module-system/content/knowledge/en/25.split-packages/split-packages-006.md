# Identifying Split Packages with jdeps and Module Resolution

> Scope: Java Platform Module System (JPMS). This article walks through finding and verifying **split packages** by combining package-level dependency analysis from **jdeps**, inspecting JAR contents, and validating the module graph with the Java module resolver.

## Objectives

After this article, you will be able to:

- Recognize when a package appears in multiple modules.
- Use **jdeps** to inspect dependency relationships between modules, classes, and packages.
- Distinguish packages that are referenced from packages actually contained inside a JAR.
- Inventory packages in JARs using **jar --list** and **jar --describe-module**.
- Use **java --validate-modules** to detect conflicts among observable modules.
- Use **--show-module-resolution** to see which modules the module resolver selects when running an application.
- Choose a split package resolution aligned with module boundaries.

## 1. What Is a Split Package?

A **split package** occurs when the same package name is contained in multiple different modules. For example, two JARs both have classes in the package **com.acme.shared**:

~~~text
acme-core.jar
└── com/acme/shared/DateParser.class

acme-extra.jar
└── com/acme/shared/DateFormatter.class
~~~

If the two JARs are treated as two named modules, the package **com.acme.shared** is divided between two modules. This is a design problem in JPMS because packages are part of module boundaries: a module is responsible for containing and controlling a package, while other modules access the package through readability and exports relationships.

On the traditional class path, multiple JARs can co-contribute classes to a package in the unnamed module. This organization often worked in legacy applications. When moving JARs onto the module path, each JAR can become a named module; identically named packages can then create conflicts in the module configuration.

The severity of the conflict depends on the module graph and whether the modules are resolved together, read, or export that package. The module resolver can reject the configuration when it detects an invalid split package. Therefore, do not assume every identically named package in any JAR always produces the exact same error; inspect the actual module graph.

Another case is two modules both containing a class with the same fully qualified name:

~~~text
com.acme.shared.DateParser
~~~

This is a more severe case because the same class name appears in two modules. Even if class names do not collide, merely splitting a package across modules can make the module configuration invalid.

## 2. Why Combine jdeps and Module Resolution?

The two tools address different parts of the investigation:

| Tool/Mechanism | Question Answered |
|---|---|
| **jdeps** | Which module, class, or package references which package? Which modules do static dependencies go through? |
| **jar --list** | Which classes/resources does a JAR actually contain? Which packages appear in the JAR contents? |
| **jar --describe-module** | Which module is the JAR recognized as and what packages/directives does its descriptor declare? |
| **java --validate-modules** | Do observable modules form a valid configuration? Are there module conflicts to fix? |
| **java --show-module-resolution** | When launching an application, which root modules and dependencies does the module resolver select? |

**jdeps is static analysis.** It helps make visible the dependencies expressed in bytecode and descriptors. It does not by itself replace inventorying all packages in each JAR, nor does it reliably detect every dependency arising from reflection, dynamically generated class names, plugins, or runtime configuration.

**Module resolution checks the actual JPMS configuration.** It tells you whether modules can be resolved into a valid module graph. Its output should be read alongside the package inventory and dependency report to pinpoint the exact conflicting JARs.

## 3. Preparing an Example with a Split Package

Suppose there are three modules:

- **com.acme.core**: contains one part of the package **com.acme.shared**.
- **com.acme.extra**: contains the remaining part of the package **com.acme.shared**.
- **com.acme.app**: uses APIs from both modules above.

JAR structure:

~~~text
mods/
├── com.acme.core.jar
├── com.acme.extra.jar
└── com.acme.app.jar
~~~

Contents of the two libraries:

~~~text
com.acme.core.jar
└── com/acme/shared/DateParser.class

com.acme.extra.jar
└── com/acme/shared/DateFormatter.class
~~~

Module descriptor of core:

~~~java
module com.acme.core {
    exports com.acme.shared;
}
~~~

Module descriptor of extra:

~~~java
module com.acme.extra {
    exports com.acme.shared;
}
~~~

Module descriptor of app:

~~~java
module com.acme.app {
    requires com.acme.core;
    requires com.acme.extra;
}
~~~

In this example, app reads both modules and both modules export **com.acme.shared**. This is the configuration to investigate: the same package appears in two modules that a consuming module reads simultaneously.

## 4. Using jar to Inventory Packages Actually Present in JARs

The first step is inspecting each JAR's contents, not just looking at filenames or module names.

List contents:

~~~bash
jar --list --file mods/com.acme.core.jar
jar --list --file mods/com.acme.extra.jar
~~~

You can use the short form:

~~~bash
jar tf mods/com.acme.core.jar
jar tf mods/com.acme.extra.jar
~~~

Find entries belonging to the suspected package:

Linux/macOS:

~~~bash
jar tf mods/com.acme.core.jar | grep '^com/acme/shared/'
jar tf mods/com.acme.extra.jar | grep '^com/acme/shared/'
~~~

Windows PowerShell:

~~~powershell
jar tf mods/com.acme.core.jar | Select-String '^com/acme/shared/'
jar tf mods/com.acme.extra.jar | Select-String '^com/acme/shared/'
~~~

Entries with the path **com/acme/shared/** show that the JAR contains classes/resources in that package. When comparing, note:

- **.class** files indicate classes belonging to the package.
- Resource files can also reside in the package path.
- **module-info.class** resides at the root of a modular JAR and is not a class in an application package.
- Package names in Java use dots; entry paths inside a JAR use forward slashes.

You can describe each JAR's module:

~~~bash
jar --describe-module --file mods/com.acme.core.jar
jar --describe-module --file mods/com.acme.extra.jar
~~~

The output helps confirm the module name and the packages/directives inferred by the tool or read from the descriptor. For an explicit modular JAR, the explicit descriptor is the module declaration source. For an automatic module, the name and package list are derived according to automatic module rules.

**jar --describe-module** is useful for checking module identity, while **jar --list** is useful for checking actual entries. Use both when tracing identically named packages.

## 5. Using jdeps to Inspect Module-Level Dependencies

First, list the application's module dependencies:

~~~bash
jdeps --module-path mods --list-deps --module com.acme.app
~~~

This command analyzes the dependencies referenced by the app module and lists the related modules. The output can show **com.acme.core**, **com.acme.extra**, and JDK modules such as **java.base**.

You can output a comma-separated list of dependencies:

~~~bash
jdeps --module-path mods --print-module-deps --module com.acme.app
~~~

The output is useful when preparing a module path configuration or the set of input modules for a tool like **jlink**.

If you want to see transitive dependencies, use the recursive option:

~~~bash
jdeps --module-path mods --recursive --list-deps --module com.acme.app
~~~

When there are many libraries, make sure all modules to be analyzed are on the module path passed to **jdeps**. If a dependency is missing, the report may be incomplete or unresolved warnings may appear.

## 6. Using jdeps to Inspect Package-Level Dependencies

To see which package depends on which package, use the package verbose level:

~~~bash
jdeps --module-path mods -verbose:package --module com.acme.app
~~~

The **-verbose:package** option displays package-level dependencies. It helps trace relationships such as:

~~~text
com.acme.app -> com.acme.shared
com.acme.shared -> java.lang
~~~

The exact names and presentation in the output depend on the JAR/module being analyzed. Pay attention to the module containing the target package in the output to see which module the dependency is resolved from.

You can analyze a JAR directly:

~~~bash
jdeps --module-path mods -verbose:package mods/com.acme.app.jar
~~~

Or inspect at the class level when you need to know which class creates the dependency:

~~~bash
jdeps --module-path mods -verbose:class mods/com.acme.app.jar
~~~

Verbose levels:

- **-verbose:module**: module-level relationships.
- **-verbose:package**: package-level relationships.
- **-verbose:class**: class-level relationships.

For split packages, **-verbose:package** helps identify referenced packages and the modules through which dependencies flow. However, if a JAR contains a package that no class in the analyzed module references, the app's dependency report might not show that package. Therefore, use **jar --list** to inventory JAR contents when searching for identically named packages.

## 7. Using jdeps --check to Inspect Module Descriptors and Dependencies

The **--check** option helps analyze module dependencies and inspect the descriptors of specified modules:

~~~bash
jdeps --module-path mods --check com.acme.app
~~~

You can check multiple modules:

~~~bash
jdeps --module-path mods --check com.acme.core,com.acme.extra,com.acme.app
~~~

The output of **--check** helps reveal:

- Which dependencies the module declares.
- Which dependencies are actually used in bytecode.
- How the module descriptor might be streamlined.
- Declared dependencies that are unused or module relationships needing review.

Depending on the JDK version and analyzed modules, the output content may vary. Read both the current module descriptor section and the suggested descriptor section if the tool provides one.

**--check is not a complete inventory of every class/package in every JAR.** It assists with dependency and descriptor analysis; to confirm whether two JARs share the same package, you still must check the package inventory or use a tool/module resolver to verify the configuration.

## 8. Verifying the Module Graph with java --validate-modules

After inspecting JAR contents and dependencies, use Java's module resolver to validate the module path:

~~~bash
java --module-path mods --validate-modules
~~~

The **--validate-modules** option asks the launcher to validate observable modules in the current configuration and then exit. It is useful for catching module descriptor errors, duplicate module names, package conflicts, and other issues on the module path.

If there is an invalid split package in the checked set of modules, the launcher may report an error such as:

~~~text
Error occurred during initialization of boot layer
java.lang.module.ResolutionException: ...
~~~

The specific message may name the two conflicting modules or package. Use the exact module/package names in the error to go back and inspect the two JARs with **jar --list** and **jar --describe-module**.

This is an important step because jdeps only analyzes static dependencies; the module resolver checks the validity of the JPMS configuration used by the launcher.

When running the command, use the exact JDK/runtime matching the project and pass the module path containing the JARs to validate. If the module path has multiple directories or JARs, make sure they are genuinely the input set you intend to validate.

## 9. Observing the Module Resolver When Launching the Application

To see which modules are resolved when running a modular application, use:

~~~bash
java --show-module-resolution \
     --module-path mods \
     --module com.acme.app/com.acme.app.Main
~~~

The **--show-module-resolution** option prints module resolver information as the launcher builds the module configuration. The output typically shows the root modules and resolved dependencies.

This command helps answer:

- Which main module is being launched?
- Which modules are resolved due to **requires** directives?
- Which system modules are pulled into the module graph?
- Which provider modules are bound when service binding occurs?

If the application fails before running the main class due to a split package, the module resolution error usually points out the conflict to fix. If the application starts up yet the module path differs from expectations, the resolution output helps determine which modules were actually chosen.

**--show-module-resolution** only shows the configuration resolved for that specific run. It does not replace **--validate-modules** when validating the overall module path, nor does it automatically list every package present in each JAR.

## 10. Complete Split Package Investigation Workflow

Suppose the application reports an error related to the package **com.acme.shared**. You can investigate in sequence:

1. Record the package name and the modules mentioned in the error message.
2. Use **jar --describe-module --file** to confirm the module name of each JAR.
3. Use **jar --list --file** to find entries under the path **com/acme/shared/** in each JAR.
4. Use **jdeps --list-deps** to understand the application's module dependencies.
5. Use **jdeps -verbose:package** to inspect package dependencies of the modules/classes causing the issue.
6. Use **jdeps --check** to review descriptors and declared dependencies.
7. Run **java --module-path mods --validate-modules** to confirm errors in the module configuration.
8. Run the application with **--show-module-resolution** to see the actual set of resolved modules.
9. Fix the library/module structure, then rerun the verification commands.

For example, if both **com.acme.core.jar** and **com.acme.extra.jar** contain entries under **com/acme/shared/**, determine which module this package should belong to. Do not merely add **requires** or **exports** to mask the error; those directives do not merge a package residing in two modules.

## 11. Ways to Handle a Detected Split Package

Common resolution approaches:

### Merge the package into one module

If two JARs are parts of the same library, you can merge the package into a single module. This establishes one clear owner for the package and makes the module descriptor reflect true API boundaries.

### Move the package to a separate namespace

If both libraries can be modified, move part of the package to a distinct package name, such as **com.acme.extra.shared**. Then update imports, APIs, and related configurations.

### Relocate packages during packaging

For third-party libraries, you can use shading/relocation in the build to rename the package of one dependency before releasing the artifact. You must verify reflection, serialization, service configurations, native integrations, and public APIs because changing package names can affect compatibility.

### Keep legacy libraries on the class path when appropriate

Some applications can keep legacy libraries on the class path so they belong to the unnamed module, rather than converting everything into named modules immediately. This is a transitional choice; you need to check interactions between named modules and the unnamed module, as well as encapsulation and maintainability.

### Use --patch-module only when content belongs to the same module

**--patch-module** can add classes/resources into a target module. It is suitable when the intent is to patch a single module, such as for tests or controlled hotfixes. It is not a general way to combine two independent libraries declared as two named modules into the same module graph.

Do not use **--add-exports**, **--add-reads**, or **--add-opens** as ways to fix split packages. These options alter access permissions/readability; they do not move a package from one module to another.

## 12. Limitations to Remember When Using jdeps

- jdeps analyzes observable bytecode and module metadata; dependencies arising from reflection or dynamically generated class names may be missed.
- **-verbose:package** shows package dependencies, not a complete list of packages contained inside each JAR.
- **--list-deps** and **--print-module-deps** focus on module dependencies and do not uniquely identify which JAR contains a package.
- **--check** helps inspect descriptors/dependencies and suggest adjustments; it does not replace JAR inventorying.
- Analysis results depend on the module path and the JDK version used to run jdeps.
- Module resolution only validates the modules and roots/configuration included in the launcher's check scope; confirm the command uses the right module path and target modules.

Therefore, a reliable workflow combines **jdeps to understand dependencies**, **jar to inventory packages**, and the **java module resolver to validate the module graph**.

## 13. Key Takeaways

- A split package is the same package appearing in multiple modules.
- **jar --list** shows which classes/resources a JAR actually contains; use it to compare package inventories.
- **jar --describe-module** confirms module names and descriptors.
- **jdeps --list-deps** inspects dependencies at the module level.
- **jdeps -verbose:package** inspects dependencies at the package level; **-verbose:class** drills down to classes.
- **jdeps --check** assists in analyzing module descriptors and dependencies.
- **java --validate-modules** checks the validity of observable modules.
- **--show-module-resolution** displays resolved modules when launching the application.
- jdeps does not replace the module resolver and does not automatically list every package inside each JAR.
- A sustainable fix establishes a single clear module owning the package, moving or relocating packages when necessary.

## References

- [The jdeps Command — Java SE 21 Tool Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html)
- [The java Command — Java SE 21 Tool Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [The jar Command — Java SE 21 Tool Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html)
- [JEP 261 — Module System](https://openjdk.org/jeps/261)
- [Java Platform Module System — OpenJDK Project Jigsaw](https://openjdk.org/projects/jigsaw/spec/)
