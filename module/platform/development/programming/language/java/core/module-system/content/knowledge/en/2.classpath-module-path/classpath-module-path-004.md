# Named Module, Automatic Module, and Unnamed Module

## 1. Three Ways a Java Library Participates in an Application

When a Java application uses multiple JAR libraries, where the JARs are placed determines how Java classifies them. Under JPMS (Java Platform Module System, since Java 9), a library can be handled in three common forms:

- **Explicit named module**: a module with a `module-info.java` descriptor (compiled into `module-info.class`). Its module name, dependencies, and exported packages are declared explicitly.
- **Automatic module**: a JAR without a module descriptor that is placed on the module path. The module system synthesizes a descriptor for that JAR.
- **Unnamed module**: classes loaded from the classpath belong to the unnamed module of the corresponding class loader. This module has no name and no descriptor.

An automatic module is also a named module because it has a name in the module graph. The difference is that its descriptor is derived automatically, whereas an explicit named module has a descriptor authored by the library maintainer. An unnamed module has no name for another module to declare in `requires`.

## 2. Explicit Named Module: An Explicitly Declared Module Contract

An explicit named module is typically packaged in a modular JAR with `module-info.class` at the JAR root, or exists as an exploded module in an output directory.

For example:

~~~java
module com.acme.customer {
    requires java.sql;
    requires com.acme.logging;

    exports com.acme.customer.api;
    opens com.acme.customer.model to com.acme.persistence;
}
~~~

The descriptor above shows the main parts:

- The module name is `com.acme.customer`.
- The module reads `java.sql` and `com.acme.logging` via `requires`.
- Package `com.acme.customer.api` is exposed to modules that read this module.
- Package `com.acme.customer.model` is opened for deep reflection from module `com.acme.persistence`.

By default, a package in an explicit named module is not exported merely because it contains `public` classes. Other modules must read the providing module, and the package being used must be appropriately exported. Java access rules such as `public`, `protected`, package-private, and `private` still apply after module-level checks.

Explicit named modules let library authors control the public API and keep implementation packages internal to the module. This is the target form when a library is ready to fully participate in JPMS.

## 3. Automatic Module: A Bridge for JARs Without module-info

A JAR that does not contain `module-info.class`, when placed on the **module path**, can be treated by the module system as an automatic module. Java generates a synthetic module descriptor for that JAR, allowing another named module to declare `requires` on it.

### How Is an Automatic Module Name Determined?

There are two cases:

1. If the JAR's manifest has the `Automatic-Module-Name` attribute, that value is used as the module name.
2. If this attribute is absent, the module name is derived from the JAR filename according to the module system's naming rules, including handling version parts and separators.

For example, a library's manifest might contain:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.acme.legacy
~~~

An application module can then declare:

~~~java
module com.example.app {
    requires com.acme.legacy;
}
~~~

When the module name is derived from the filename, renaming the JAR file can change the module name the application must require. For libraries controlled by your team, set a stable `Automatic-Module-Name` before releasing so consumers do not depend on specific filenames.

You can check the module name provided by a JAR with the command:

~~~bash
jar --describe-module --file libs/legacy.jar
~~~

### What Permissions Does an Automatic Module Have?

Automatic modules are designed so legacy libraries can participate on the module path with minimal changes:

- All packages of an automatic module are exported.
- An automatic module reads all other modules in the configuration, including unnamed modules.
- Named modules can declare `requires` on the automatic module name.
- The JAR still lacks an author-declared dependency contract and package boundaries like an explicit named module.

Broad reading and exporting makes migration easier, but also reduces the encapsulation benefits of JPMS. A module might accidentally depend on packages of another library that it has not directly declared in its descriptor. Therefore, automatic modules serve well as a transitional step; they should not be viewed as the final module design.

## 4. Unnamed Module: The Traditional Classpath World

Classes loaded from the classpath belong to the unnamed module associated with the corresponding class loader. Each class loader has its own unnamed module. The unnamed module has no name and no `module-info.java`.

Example of running an application on the classpath:

~~~bash
java -cp "app.jar:lib/*" com.acme.app.Main
~~~

Classes in `app.jar` and the libraries on the classpath are loaded into the unnamed module of the corresponding class loader. This model preserves traditional library usage: individual JARs do not need to declare `requires` or `exports`.

The unnamed module has important characteristics:

- It reads all named modules in the same module layer.
- All of its packages are exported and opened.
- It has no name to write in a `requires` directive of an explicit named module.
- Package boundaries and dependencies are not strictly enforced at the module level as with explicit named modules.

This explains why code running on the classpath can still access many libraries in the traditional way. However, an explicit named module does not automatically read the unnamed module. If you need to temporarily integrate classpath code with modular code, you can add a read relationship from the command line:

~~~bash
java --add-reads com.acme.app=ALL-UNNAMED --module-path mods -m com.acme.app/com.acme.app.Main
~~~

`ALL-UNNAMED` is a special target name for the command-line option representing unnamed modules. It is a migration compatibility mechanism; it is not a module name that can be used inside `module-info.java`.

## 5. JAR Placement Determines How the Module System Handles It

The same JAR can be handled differently depending on where it is placed:

| JAR type | Placed on classpath | Placed on module path |
|---|---|---|
| JAR with `module-info.class` | Module descriptor is ignored; classes load as classpath code in the unnamed module | Handled as an explicit named module |
| JAR without `module-info.class` | Classes belong to the unnamed module | Can be handled as an automatic module |

For example:

~~~text
app.jar
mods/
  com.acme.domain.jar
  legacy-library.jar
~~~

Suppose `com.acme.domain.jar` has `module-info.class`, while `legacy-library.jar` has no descriptor:

- Place both on the module path: `domain` is an explicit named module; `legacy-library` is an automatic module.
- Place `legacy-library.jar` on the classpath: its classes belong to the unnamed module.
- Place a modular JAR on the classpath: its module descriptor does not enforce JPMS boundaries during that run; the JAR is used in classpath mode.

Therefore, when encountering errors regarding module names, readability, or package visibility, check both the JAR contents and where the JAR is placed at compile time and runtime.

## 6. Comparing the Three Module Forms

| Criterion | Explicit named module | Automatic module | Unnamed module |
|---|---|---|---|
| Source of descriptor | Author declares `module-info.java` | Module system derives descriptor from JAR | No descriptor |
| Has module name | Yes, explicitly declared | Yes, taken from manifest or JAR filename | No |
| Typical usage location | Module path | Module path | Classpath |
| Read relationships | Per `requires` directives and JPMS rules | Reads all modules in configuration | Reads all named modules in layer |
| Exported packages | Per `exports` | All packages | All packages |
| Packages opened for reflection | Per `opens` or `open module` | Do not infer reflection rights solely from packages being exported; check descriptor/runtime when integrating frameworks | All packages opened |
| Can be required by a named module via `requires` | Yes | Yes | No |
| Encapsulation level | Clear, controlled | Broad, convenient for migration | Follows classpath model |

Distinguish two concepts: **export** allows code in other modules to access public types in a package under Java rules; **open** allows deep reflection. An exported package does not imply that the package is opened for reflection.

## 7. Mixing Classpath and Module Path During Migration

JPMS allows an application to keep some libraries on the classpath while newer modules have already moved to the module path. This enables incremental migration, though you need to understand the direction of read relationships:

- The unnamed module can read named modules in its layer.
- An automatic module reads named modules and unnamed modules in the configuration.
- An explicit named module only reads dependencies per established module relationships; it does not automatically read the unnamed module.
- To allow an explicit named module to read classpath code during transition, `--add-reads module=ALL-UNNAMED` can be used on the launch command. Afterward, convert that dependency into a named module and declare `requires` explicitly.

Example of an application that already has a module descriptor but still needs an older library on the classpath:

~~~bash
java --add-reads com.acme.app=ALL-UNNAMED --class-path "legacy/*" --module-path mods -m com.acme.app/com.acme.app.Main
~~~

The command above adds read access from `com.acme.app` to unnamed modules. It only solves readability; other issues such as missing classes, split packages, or incompatible APIs still need to be handled separately.

## 8. Roadmap to Migrate Legacy JARs to Modules

You can migrate incrementally with the following steps:

1. **Inventory dependencies**: identify which JARs already have `module-info.class`, which have `Automatic-Module-Name`, and which only use the classpath.
2. **Check module names**: use `jar --describe-module --file <jar>` to see the name and descriptor Java recognizes.
3. **Stabilize names for legacy libraries**: if you have permission to re-release the JAR, add `Automatic-Module-Name` to the manifest so consumers have a stable module name.
4. **Move compatible JARs onto the module path**: declare `requires` on the automatic modules and test the application at both compile time and runtime.
5. **Create explicit descriptors**: when the library can be modified, add `module-info.java`, select required dependencies, and export only API packages.
6. **Remove temporary bridges**: once a dependency is an explicit named module, drop `--add-reads ...=ALL-UNNAMED` options and compatibility workarounds that are no longer needed.

Do not put every JAR onto the module path without checking module names. Two JARs with conflicting module names or duplicate packages can cause module resolution to fail or make the configuration hard to maintain.

## 9. Diagnosing Which Module a JAR Provides

The following commands help identify how Java recognizes a JAR:

~~~bash
jar --describe-module --file libs/legacy.jar
jar --describe-module --file libs/domain.jar
~~~

To observe resolved modules at runtime:

~~~bash
java --show-module-resolution --module-path mods -m com.acme.app/com.acme.app.Main
~~~

To inspect module dependencies detected by `jdeps`:

~~~bash
jdeps --print-module-deps --module-path mods app.jar
~~~

When results are unexpected, check in order:

- Is the JAR actually on the classpath or module path?
- Does the JAR contain `module-info.class` or only a manifest?
- Does the declared module name match what `jar --describe-module` displays?
- Has the explicit named module declared `requires` on the dependency?
- Is the needed package exported?
- Does the dependency appear in the runtime configuration just as in the compile-time configuration?

## 10. Common Errors When Confusing the Three Module Forms

- **`module not found`**: the JAR is not on the module path, the requested module name does not match, or the module was not resolved.
- **`module A does not read module B`**: module A lacks a readability relationship; check `requires`, `requires transitive`, or appropriate transition configuration.
- **Cannot write `requires` to a classpath library**: that library belongs to the unnamed module and has no module name. You can temporarily use `--add-reads A=ALL-UNNAMED`, or move the old JAR onto the module path so it becomes an automatic module.
- **Package is not exported**: the module is read, but the explicit named module's package has not been exported to the calling module.
- **Reflection error in a framework**: check `opens` or `open module`; `exports` does not replace `opens`.
- **Module name changes after renaming a JAR**: the JAR does not declare `Automatic-Module-Name`, so the name derived from the filename can change.

## Conclusion

Explicit named modules, automatic modules, and unnamed modules are the three ways Java code participates in a runtime configuration:

- Explicit named modules have explicit descriptors controlling dependencies and package APIs.
- Automatic modules allow legacy JARs to join the module path with a module name and broad readability, suitable for migration phases.
- Unnamed modules preserve traditional classpath organization, have no name, and cannot be required directly with `requires`.

When inspecting a dependency, identify where the JAR is located, which module form Java recognizes it as, and only then verify readability relationships and package exports. Understanding these three forms helps migrate applications to JPMS step by step while keeping access boundaries clear at both compile time and runtime.