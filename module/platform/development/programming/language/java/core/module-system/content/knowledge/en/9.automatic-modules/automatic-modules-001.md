# Automatic Modules Formed from JARs Missing a Module Descriptor

In the Java Platform Module System (JPMS), a JAR library without a `module-info.class` can still be placed on the module path and used as a module. Java refers to this type of module as an **automatic module**.

An automatic module is a mechanism that supports migrating libraries from the classpath to the module path. It allows a new module to depend on a legacy JAR without immediately modifying the source code of that library. However, an automatic module has broader access boundaries than an explicit named module, so it should be treated as a transitional step and carefully evaluated before long-term use.

There is a terminological distinction to keep in mind: a true **modular JAR** already has a module descriptor. An automatic module is formed from a JAR that does not have a descriptor—that is, a JAR library that has not yet been explicitly modularized—when that JAR is placed on the module path.

## Objectives

After this lesson, you will be able to:

- Explain the condition for a JAR to become an automatic module.
- Distinguish between a JAR on the classpath, an automatic module, and an explicit named module.
- Determine an automatic module's name from the manifest or the JAR file name.
- Understand the broad readability and export scope of an automatic module.
- Declare `requires` on an automatic module from a named module.
- Inspect automatic modules using JDK tools and plan a migration path to an explicit module.

## 1. What Is an Automatic Module?

A JAR that does not contain a module descriptor can be treated by Java as an automatic module when placed on the module path.

An explicit module descriptor is typically the `module-info.class` file at the root of the JAR. This file is compiled from `module-info.java` source code and declares the module name, dependencies, exported packages, opens, uses, and provides.

If a JAR lacks an explicit descriptor and is placed on the module path, Java derives a module name and applies the default rules of an automatic module.

Example:

~~~text
libs/
└── legacy-utils-2.4.1.jar
~~~

Suppose the JAR `legacy-utils-2.4.1.jar` does not have `module-info.class`. When the `libs` directory is placed on the module path, Java can treat this JAR as an automatic module.

What matters is the location of the JAR:

- JAR on the classpath: its classes belong to the unnamed module corresponding to the class loader.
- JAR without a module descriptor on the module path: the JAR is treated as an automatic module.
- JAR with a module descriptor on the module path: the JAR is an explicit named module.

Simply moving a JAR from the classpath to the module path can change how Java organizes and resolves its dependencies.

## 2. Determining the Automatic Module Name

An automatic module needs a name so that other modules can declare `requires module-name;`. Java determines the name according to an order of precedence.

### 2.1. Using Automatic-Module-Name in the Manifest

A library publisher can declare the `Automatic-Module-Name` attribute in the JAR's manifest file.

Example contents of `META-INF/MANIFEST.MF`:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.acme.legacyutils
~~~

When a JAR has no module descriptor but has this attribute, Java uses `com.acme.legacyutils` as the automatic module name.

Advantages:

- The module name remains stable across JAR version changes.
- The file name can change while clients continue using the same name in `requires`.
- The publisher can choose a name matching the organization's namespace.
- Consumers do not have to rely on the algorithm that derives a name from the filename.

Note: `Automatic-Module-Name` only provides the module name. It is not a module descriptor and does not declare dependencies, exports, or opens. The JAR remains an automatic module until it has an explicit module descriptor.

### 2.2. Deriving the Name from the Filename

If the manifest does not have `Automatic-Module-Name`, Java derives the name from the JAR file name.

Example:

~~~text
legacy-utils-2.4.1.jar
~~~

The derived module name may be:

~~~text
legacy.utils
~~~

The name derivation process essentially consists of:

1. Removing the `.jar` extension.
2. Detecting and stripping the trailing version suffix if it matches a supported version format.
3. Replacing non-alphanumeric characters with dots.
4. Collapsing consecutive dots and stripping leading or trailing dots.

Other examples:

| JAR Name | Illustrative Automatic Module Name |
|---|---|
| `legacy-utils-2.4.1.jar` | `legacy.utils` |
| `http-client.jar` | `http.client` |
| `acme_json-1.2.jar` | `acme.json` |

The exact result depends on the JDK's name derivation rules and the actual filename. Therefore, check with JDK tools instead of guessing the name in a module descriptor.

### 2.3. Why Should You Set Automatic-Module-Name?

If the module name depends on the filename, renaming the artifact or changing how it is packaged can alter the derived module name. Modules that already declared `requires` with the old name would have to be updated.

Library publishers should set a stable `Automatic-Module-Name` even before migrating to an explicit module. When `module-info.class` is added later with the same name, clients can continue using the same module name.

## 3. Access Characteristics of an Automatic Module

Automatic modules are designed to help legacy libraries work in the module system with minimal changes. As a result, they have broader default rules than explicit named modules.

### 3.1. All Packages Are Exported

An automatic module is treated as exporting all of its packages. Other modules that read the automatic module can use eligible types in those packages according to Java access rules.

Example JAR structure:

~~~text
legacy-utils.jar
└── com/acme/legacy/
    ├── api/LegacyClient.class
    └── internal/ConnectionPool.class
~~~

If the JAR becomes an automatic module, both the `com.acme.legacy.api` and `com.acme.legacy.internal` packages are exported under automatic module rules.

This means a package named `internal` is not protected like an internal package of an explicit named module. If a class in that package has sufficient Java accessibility, other modules reading the automatic module can reference it.

Therefore, an automatic module does not yet provide encapsulation as strict as a module with an explicit descriptor.

### 3.2. An Automatic Module Reads Other Modules in the Configuration

An automatic module is considered to read all other modules in the module configuration, including named modules and the unnamed module if present.

This allows legacy JARs to continue referencing dependencies that would otherwise be placed on the classpath during migration. However, broad readability makes actual dependencies harder to express clearly in the module graph.

Example:

~~~text
com.acme.app ──requires──> legacy.utils

legacy.utils can read other modules
in the application's module configuration.
~~~

The app module still must declare `requires legacy.utils;` to read the automatic module. The rule that an automatic module broadly reads others does not mean every other named module automatically reads the automatic module.

### 3.3. No Module Descriptor to Control Boundaries

An automatic module has no explicit `module-info.class` to declare:

- Specific dependencies via `requires`.
- Public packages via `exports`.
- Packages opened for reflection via `opens`.
- Consumed services via `uses`.
- Service providers via `provides ... with ...`.

The default behaviors of an automatic module partially substitute for these declarations during the compatibility phase. That is why automatic modules are convenient during migration but are not the best choice for long-term architectural control.

## 4. Using an Automatic Module from a Named Module

Suppose there is a legacy library:

~~~text
libs/
└── legacy-utils-2.4.1.jar
~~~

The JAR has no `module-info.class` and the manifest does not declare `Automatic-Module-Name`. From the file name, Java derives the module name `legacy.utils`.

The app module can declare:

~~~java
module com.acme.app {
    requires legacy.utils;
}
~~~

Then the source code can import classes in packages exported by the automatic module:

~~~java
package com.acme.app;

import com.acme.legacy.api.LegacyClient;

public class Main {
    public static void main(String[] args) {
        LegacyClient client = new LegacyClient();
        client.execute();
    }
}
~~~

To compile, place the JAR on the module path alongside the module sources:

~~~bash
javac --module-path "libs" --module-source-path src -d out -m com.acme.app
~~~

On Windows, the separator between multiple module path locations is a semicolon. On Linux and macOS, use a colon.

Run the application on Windows:

~~~bash
java --module-path "out;libs" -m com.acme.app/com.acme.app.Main
~~~

Run the application on Linux or macOS:

~~~bash
java --module-path "out:libs" -m com.acme.app/com.acme.app.Main
~~~

If the actual automatic module name is not `legacy.utils`, the `requires` declaration must use the exact name determined by Java. Use `jar --describe-module` to check.

## 5. Distinguishing Classpath, Automatic Module, and Explicit Module

The same JAR can be handled differently depending on its location and contents:

| Case | How Java Treats It |
|---|---|
| JAR without descriptor on the classpath | Classes belong to the unnamed module |
| JAR without descriptor on the module path | Automatic module |
| JAR with module descriptor on the module path | Explicit named module |
| JAR with only `Automatic-Module-Name` and no descriptor on the module path | Still an automatic module, using the name from the manifest |

Some points to remember:

- Placing a JAR on the classpath does not activate an automatic module.
- The `Automatic-Module-Name` attribute does not turn a JAR into an explicit named module.
- A JAR that has `module-info.class` and is on the module path is treated as an explicit module.
- An automatic module does not have clearly designed export boundaries like an explicit module.

This distinction matters when migrating an application from the classpath to the module path. An application may compile in the old configuration yet fail if dependencies are not placed in the right locations or if the derived module name differs from the declared name.

## 6. Inspecting Automatic Modules with JDK Tools

### 6.1. Using jar --describe-module

Inspect the JAR:

~~~bash
jar --describe-module --file libs/legacy-utils-2.4.1.jar
~~~

For a JAR without a descriptor, the output indicates that no module descriptor was found and that the module is derived as an automatic module. The tool also displays the determined module name.

If the JAR has a manifest containing `Automatic-Module-Name`, verify the displayed name so you use the exact name in `requires`.

### 6.2. Listing Observable Modules

You can use:

~~~bash
java --module-path libs --list-modules
~~~

This command lists system modules and observable modules from the supplied module path. Look for the automatic module name in the list to confirm that Java recognizes the artifact.

### 6.3. Checking JAR Dependencies

Use `jdeps` to inspect the dependencies referenced by the library's bytecode:

~~~bash
jdeps --module-path libs --list-deps libs/legacy-utils-2.4.1.jar
~~~

To view analysis at the module or package level, adjust the `jdeps` options according to your goal. The results help uncover dependencies used by the legacy library, though you still need to check runtime configuration and dynamic class-loading mechanisms.

## 7. Limitations of Automatic Modules

### 7.1. Overly Broad API Exposure

Because all packages are exported, other modules can start depending on classes that the library author considered implementation details.

For example, a client might import a class from an `internal` package. When the library transitions to an explicit module and exports only API packages, that client will no longer compile.

### 7.2. Dependencies Are Not Explicitly Declared

An automatic module reads other modules in the configuration. This can mask some dependencies that have not yet been modeled in a module descriptor.

When migrating to an explicit module, the actually needed dependencies must be explicitly declared. Omissions may only surface after module boundaries are tightened.

### 7.3. Difficult to Evaluate the API Contract

Without an explicit exports list, it is hard for maintainers to determine which packages are supported as long-term API. Clients can depend on any package exposed by the automatic module.

### 7.4. Derived Names Can Be Unstable

If the module name is derived from the filename, renaming the JAR can change the module name. Declaring `Automatic-Module-Name` helps stabilize the name during the transitional period.

## 8. Migration Path from Automatic Module to Explicit Module

When the library is ready to be modularized, you can transition gradually using this process:

1. Determine a stable module name, preferring the name already published via `Automatic-Module-Name`.
2. Inventory the packages and APIs that clients are using.
3. Use `jdeps` to help discover module-level dependencies.
4. Write `module-info.java` with the appropriate `requires` directives.
5. Export only packages that are truly API; keep implementation in non-exported packages.
6. Add `opens` if a framework needs deep reflection.
7. Declare `uses` and `provides` if the module participates in ServiceLoader.
8. Compile and run clients to catch missing dependencies or package access issues.
9. Release the explicit modular JAR and re-verify the module name used by clients.

The JDK includes a tool to help generate an initial module descriptor:

~~~bash
jdeps --generate-module-info generated-modules libs/legacy-utils-2.4.1.jar
~~~

The generated code is only a starting point. You must review dependencies, package exports, reflection, and service configuration before using the descriptor in a release.

Once the JAR has an explicit descriptor and is placed on the module path, it becomes an explicit named module. At that point, dependencies and package boundaries are governed by the module descriptor rather than the broad rules of an automatic module.

## 9. Self-Check

**Scenario 1:** A JAR without `module-info.class` is placed on the classpath. Does it automatically become an automatic module?

**Answer:** No. A JAR on the classpath belongs to the unnamed module. An automatic module is formed when a JAR without a descriptor is placed on the module path.

**Scenario 2:** A JAR has no descriptor, but its manifest has `Automatic-Module-Name: com.acme.legacy`. What module name is used?

**Answer:** `com.acme.legacy`. The JAR is still an automatic module because the manifest only supplies the name and does not replace a module descriptor.

**Scenario 3:** Does an automatic module export internal packages?

**Answer:** Under automatic module rules, all of its packages are exported. This is one reason an automatic module has broader encapsulation boundaries than an explicit module.

**Scenario 4:** Does the app module need to declare `requires legacy.utils;` when it wants to use that automatic module?

**Answer:** Yes. The broad readability rule of an automatic module applies in the direction of the automatic module reading other modules; it does not automatically create a reverse readability relationship from the app to the automatic module.

**Scenario 5:** Is a library that already has `Automatic-Module-Name` an explicit named module?

**Answer:** No. If `module-info.class` is missing, the library is still an automatic module when located on the module path.

**Scenario 6:** Why should you migrate an automatic module to an explicit module when possible?

**Answer:** Explicit modules allow clear declaration of dependencies and package exports, reduce the exposed API surface, and help detect invalid dependencies early.

When encountering a legacy JAR, check where the JAR is placed, the presence of `module-info.class`, the manifest, and the module name derived by the JDK. From there, determine whether it is an unnamed module, an automatic module, or an explicit named module before designing the application's `requires` clauses.