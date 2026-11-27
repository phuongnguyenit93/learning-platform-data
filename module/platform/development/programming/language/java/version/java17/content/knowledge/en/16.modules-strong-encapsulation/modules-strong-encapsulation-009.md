# Module Path, Classpath, and Package Conflicts in Java 17

When a Java program uses external libraries, the compiler and JVM need to know where to find classes. Two common mechanisms are the **classpath** and the **module path**. The classpath is the traditional class lookup mechanism. The module path is used with JPMS (the Java Platform Module System), officially introduced in Java 9 and continuing in Java 17.

The difference is not merely in command-line option names. A JAR placed on the classpath typically belongs to the **unnamed module**; a JAR with a module descriptor placed on the module path is a **named module**. Consequently, how modules see packages, declare dependencies, and handle overlapping packages also differs.

This lesson explains how to choose between the classpath and module path, how to compile and run modular applications in Java 17, how legacy libraries participate in the module system, and how to identify and resolve package conflicts.

## 1. What Is the Classpath?

The **classpath** is a list of directories and JARs searched by the compiler or JVM when loading classes and resources. It can be specified via:

- **-cp** or **-classpath** on **javac** and **java**;
- **--class-path** on tools supporting long options;
- the **CLASSPATH** environment variable if configured in the deployment environment.

Example:

~~~bash
javac -cp "lib/greetings.jar" -d out src/com/acme/app/Main.java
java -cp "out:lib/greetings.jar" com.acme.app.Main
~~~

On Linux/macOS, the separator between classpath entries is a colon (**:**). On Windows, use a semicolon (**;**):

~~~powershell
java -cp "out;lib/greetings.jar" com.acme.app.Main
~~~

The classpath can contain:

- directories holding **.class** files;
- JARs containing classes and resources;
- multiple directories or JARs, separated according to OS rules.

### 1.1. Classpath and the unnamed module

When running on the classpath, classes loaded by a class loader belong to the **unnamed module** associated with that class loader. Traditional applications do not need **module-info.java**.

The unnamed module has notable characteristics:

- No module name declared in **module-info.java**.
- Its packages are exported so modules that read the unnamed module can access them under Java access rules.
- The unnamed module reads all modules in the corresponding module layer.
- Named modules do not automatically read the unnamed module.

This last point is important when combining a modular application with libraries placed on the classpath: a named module cannot implicitly use classes from a library in the unnamed module merely because that JAR appears on the command line.

### 1.2. Classpath does not declare module relationships

The classpath has no **requires** and **exports** declarations under JPMS. Whether a class can be found primarily depends on:

1. whether the class resides in an entry on the classpath;
2. whether the class loader locates and loads that class;
3. whether bytecode compatibility, dependencies, and Java access permissions are satisfied.

The classpath remains widely used for non-modular applications, CLI tools, tests, and libraries not yet modularized. Java 17 does not require every application to migrate to the module path.

## 2. What Is the Module Path?

The **module path** is a list of locations containing modules that the compiler or JVM can locate. Use **--module-path** or the short form **-p**:

~~~bash
javac --module-path mods -d out ...
java --module-path mods --module com.acme.app/com.acme.app.Main
~~~

The module path can contain:

- **Modular JAR**: a JAR containing the **module-info.class** module descriptor.
- **Exploded module**: a directory containing the structure of a compiled module, including the module descriptor.
- **Automatic module**: a JAR without a module descriptor that is placed on the module path and treated by the module system as an automatic module.

When using the module path, Java resolves modules by name and dependency relationships. The module descriptor states which module requires which module, which packages are exported, and related policies.

### 2.1. Named modules and module-info.java

A named module is declared in **module-info.java** at the module root:

~~~java
module com.acme.greetings {
    exports com.acme.greetings.api;
}
~~~

In this example:

- **com.acme.greetings** is the **module name**.
- **com.acme.greetings.api** is the exported **package name**.
- Other modules can read this module and access public types in the exported package if they declare the appropriate dependency.

Module names and package names are distinct concepts. Module names typically follow reverse-DNS convention like **com.acme.greetings**; packages are typically **com.acme.greetings.api**. A module name does not automatically determine package names.

### 2.2. requires and exports

A module using another module's API needs to declare **requires**:

~~~java
module com.acme.app {
    requires com.acme.greetings;
}
~~~

The API-providing module needs to export the package containing the API:

~~~java
module com.acme.greetings {
    exports com.acme.greetings.api;
}
~~~

The two declarations have different meanings:

| Directive | Meaning |
| --- | --- |
| **requires module.name;** | The current module reads the required module. |
| **exports package.name;** | The package is exposed to modules that read this module. |
| **exports package.name to other.module;** | Exports the package only to listed modules. |
| **requires transitive module.name;** | The dependency module is propagated to modules reading the current module. |
| **opens package.name;** | Opens the package for deep reflection under module rules. |
| **opens package.name to other.module;** | Opens the package only to listed modules. |

**exports** serves API access under Java access rules. **opens** serves deep reflection operations, such as frameworks needing access to non-public members. Do not use **opens** instead of **exports** when the goal is solely to expose an API.

## 3. Example: Two Modules Communicating Through an Exported Package

Suppose an application has two modules:

~~~text
project/
└── src/
    ├── com.acme.greetings/
    │   ├── module-info.java
    │   └── com/acme/greetings/api/Greeter.java
    └── com.acme.app/
        ├── module-info.java
        └── com/acme/app/Main.java
~~~

Library module:

**src/com.acme.greetings/module-info.java**

~~~java
module com.acme.greetings {
    exports com.acme.greetings.api;
}
~~~

**src/com.acme.greetings/com/acme/greetings/api/Greeter.java**

~~~java
package com.acme.greetings.api;

public class Greeter {
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Application module:

**src/com.acme.app/module-info.java**

~~~java
module com.acme.app {
    requires com.acme.greetings;
}
~~~

**src/com.acme.app/com/acme/app/Main.java**

~~~java
package com.acme.app;

import com.acme.greetings.api.Greeter;

public class Main {
    public static void main(String[] args) {
        Greeter greeter = new Greeter();
        System.out.println(greeter.greet("Java 17"));
    }
}
~~~

Compile both modules from the module source path:

~~~bash
javac --module-source-path src -d out \
    -m com.acme.greetings,com.acme.app
~~~

Run the application module:

~~~bash
java --module-path out \
    --module com.acme.app/com.acme.app.Main
~~~

Output:

~~~text
Hello, Java 17!
~~~

**--module-source-path** tells **javac** where to find module sources. **-m** or **--module** selects the modules to compile. At runtime, **--module-path out** provides the compiled modules and **--module module/mainClass** specifies the module and main class.

If you only want to run a module that already declares a main class in its module descriptor, you can use **--module com.acme.app**; the example above specifies the class name to make the boundary between module and package clear.

## 4. Comparing Classpath and Module Path

| Criterion | Classpath | Module path |
| --- | --- | --- |
| Mechanism | Finds classes/resources across a list of directories and JARs. | Finds modules by name and resolves the dependency graph. |
| Module identity | Classes reside in the class loader's unnamed module. | Named modules, or automatic modules. |
| Dependency declaration | No **requires** on the classpath. | Uses **requires** in **module-info.java**. |
| Package exposure | No JPMS **exports**. | Named modules must export packages for other modules to read. |
| Packaging | Standard JARs or class directories. | Modular JARs, exploded modules, or automatic modules. |
| Conflict detection | Duplicate classes may be shadowed by lookup/class-loader order. | Module system checks the module graph and overlapping exported packages in a consumer's context. |
| Best suited for | Traditional apps, tests, non-modular libraries. | Modular apps needing explicit dependencies and module encapsulation. |

Both mechanisms can appear simultaneously in the same launch command. However, a JAR being on the classpath does not mean named modules will automatically read that JAR.

## 5. Automatic Module: A Bridge for Libraries Without a Module Descriptor

A JAR lacking **module-info.class** yet placed on the module path can be treated as an **automatic module**.

The automatic module name is generally determined in order:

1. The **Automatic-Module-Name** value in the JAR's manifest, if present.
2. Otherwise, the name is derived from the JAR filename according to automatic module naming rules.

For example, a library **legacy-utils-2.1.jar** without a module descriptor can be placed on the module path. The automatic module name is derived from the JAR name after normalization under Java's rules. For applications needing stable names, library publishers should include **Automatic-Module-Name** in the manifest.

An automatic module has these characteristics:

- Has a module name for other modules to reference in **requires**.
- Exports all of its packages.
- Reads other modules in the module graph according to automatic module rules.
- Can help bring legacy libraries onto the module path during a transition.

For example, the application module declares:

~~~java
module com.acme.app {
    requires legacy.utils;
}
~~~

The name **legacy.utils** must be the module name recognized by the runtime, not necessarily identical to the JAR filename or package name. Verify the actual name using the **jar** tool.

Automatic modules are a compatibility and migration mechanism. They do not offer strict package encapsulation like a named module with a well-designed descriptor. Whenever possible, use a library version with a stable module descriptor.

## 6. Putting a Library on the Classpath or the Module Path?

Suppose an application needs to use **vendor-utils.jar**.

### 6.1. Placing the library on the classpath

~~~bash
javac -cp "lib/vendor-utils.jar" -d out \
    src/com/acme/app/Main.java

java -cp "out:lib/vendor-utils.jar" com.acme.app.Main
~~~

This is the classpath model. Application and library classes reside in the corresponding class loader's unnamed module. No **requires** declaration is needed.

### 6.2. Placing a non-modular JAR on the module path

If **vendor-utils.jar** lacks **module-info.class**, the runtime can treat it as an automatic module:

~~~bash
javac --module-path lib -d out \
    --module-source-path src -m com.acme.app

java --module-path "out:lib" \
    --module com.acme.app/com.acme.app.Main
~~~

The application module needs **requires** on the automatic module name:

~~~java
module com.acme.app {
    requires vendor.utils;
}
~~~

The name above is illustrative. Before writing **requires**, verify the module name actually provided by the JAR.

### 6.3. Placing a library on the classpath when the application is a named module

You can pass both **--module-path** and **--class-path** in the same command:

~~~bash
java --module-path mods \
    --class-path "legacy/old-helper.jar" \
    --module com.acme.app/com.acme.app.Main
~~~

However, a JAR on the classpath belongs to the unnamed module. Named modules do not automatically read the unnamed module. If the application module needs to access that library, consider:

- moving the library to the module path if it can work as an automatic module;
- using a modular version of the library;
- or, during an intentional transition, adding readability via **--add-reads** after understanding the implications.

Syntactic example of adding readability at runtime:

~~~bash
java --module-path mods \
    --class-path "legacy/old-helper.jar" \
    --add-reads com.acme.app=ALL-UNNAMED \
    --module com.acme.app/com.acme.app.Main
~~~

This is a compatibility tool, not a long-term dependency design. If a named module's source directly imports classes in the unnamed module, readability must be added for compilation using the corresponding **javac** option and for execution using **java**. **--add-reads** only adds a readability edge; it does not convert a JAR into a named module and does not resolve package conflicts.

## 7. What Is a Package in the Context of Modules?

In Java, a package is a namespace used to group types and support access control. Example:

~~~java
package com.acme.payment;

public class PaymentService {
}
~~~

The package name is **com.acme.payment**. A package can contain multiple classes, interfaces, enums, or records.

In the module system:

- Modules contain packages.
- Module descriptors determine which packages are exported or opened.
- Other modules must read the module providing that package.
- Module names do not replace package names.

Example:

~~~text
module com.acme.billing
└── package com.acme.billing.api
    ├── Invoice.java
    └── BillingClient.java
~~~

**com.acme.billing** is the module name; **com.acme.billing.api** is the package name. A module can contain many packages, yet only exported packages become public APIs to other modules under JPMS.

## 8. What Is a Package Conflict?

A **split package** occurs when the same package name is divided across multiple packaging units/modules. This issue is particularly critical when migrating applications from the classpath to the module path.

Example of two libraries both containing a package:

~~~text
vendor-a.jar
└── com/example/util/
    └── TextHelper.class

vendor-b.jar
└── com/example/util/
    └── DateHelper.class
~~~

On the classpath, two JARs can both contain classes in **com.example.util**. This does not automatically trigger an error solely due to matching package names; however, it splits the package across JARs and can complicate maintenance or JPMS migration.

When moving to named modules, a typical conflict happens when two resolved modules both export package **com.example.util** to the same consuming module. The module system cannot treat that package as a single unambiguous API, and module graph resolution/compilation fails.

Example:

~~~java
module com.vendor.a {
    exports com.example.util;
}
~~~

~~~java
module com.vendor.b {
    exports com.example.util;
}
~~~

~~~java
module com.acme.app {
    requires com.vendor.a;
    requires com.vendor.b;
}
~~~

If both modules export the same package to **com.acme.app**, the application hits a split-package conflict. The exact error message varies by tool and detection phase, but the cause is that the consumer sees the same package from multiple modules.

Point to understand accurately: not every occurrence of the same package string anywhere leads to the exact same error. Conflicts depend on the module graph, exported packages, and which modules read them. Nonetheless, module design should avoid splitting one package across multiple named modules.

## 9. Class Collisions on Classpath Differ from Split Packages on Module Path

These two situations should not be equated:

### 9.1. Package overlap on the classpath

Multiple JARs on the classpath can contain classes in the same package. Example:

~~~text
lib-a.jar: com/acme/util/StringTools.class
lib-b.jar: com/acme/util/DateTools.class
~~~

If two JARs contain distinct classes in the same package, a traditional classpath program may run normally.

### 9.2. Duplicate class names on the classpath

If two JARs both contain the same binary name:

~~~text
lib-a.jar: com/acme/util/Version.class
lib-b.jar: com/acme/util/Version.class
~~~

the class loader typically searches in classpath order and the first class loaded is used in that class loader. Behavior can depend on entry order, leading to running the wrong version or linkage errors like **NoSuchMethodError** when code was compiled against one version yet runtime loads another.

Do not rely on classpath order to manage multiple versions of the same library. Remove duplicates and pick a single unified dependency version.

### 9.3. Split packages between named modules

With named modules, module descriptors and the module graph determine which packages are supplied to consumers. If two modules both export the same package to a module reading them, the conflict is detected during resolution/compilation.

Therefore:

- Classpath can hide split packages that the module path will catch.
- A JAR that runs on the classpath is not guaranteed to move to the module path unchanged.
- Moving a JAR from the classpath to the module path can surface module name, readability, export, or split-package errors.

## 10. How to Detect Duplicate Packages and Modules

### 10.1. Inspecting a JAR's module descriptor

Use **jar --describe-module**:

~~~bash
jar --describe-module --file lib/vendor-utils.jar
~~~

The output shows the module name, packages, and descriptor details. If the JAR has no module descriptor, the tool can display the automatic module name or derived name hint.

For a modular JAR, you can inspect the descriptor directly:

~~~bash
jar --describe-module --file mods/com.acme.greetings.jar
~~~

### 10.2. Observing module resolution

When running a modular application, use:

~~~bash
java --show-module-resolution \
    --module-path mods \
    --module com.acme.app/com.acme.app.Main
~~~

This option displays resolved modules and the dependency relationships used to launch the application.

### 10.3. Analyzing dependencies with jdeps

**jdeps** analyzes dependencies at the class/package/module level. Example checking a module:

~~~bash
jdeps --module-path mods --check com.acme.app
~~~

You can use **jdeps** options to inspect package- or module-level dependencies when investigating whether a library has unexpected dependencies.

### 10.4. Inspecting JAR contents

Use **jar --list** to list classes and packages in a JAR:

~~~bash
jar --list --file lib/vendor-a.jar
jar --list --file lib/vendor-b.jar
~~~

Look for package paths appearing across multiple JARs. When suspecting duplicate classes, compare binary names and artifact versions, not just package names.

## 11. How to Resolve Package Conflicts

### 11.1. Consolidate classes of the same package into one module

If **com.example.util** is a single API package split across two modules, a sound solution is usually placing that package's classes into **one owning module**. The remaining modules can depend on that module.

Example:

~~~text
com.example.util
        |
        v
com.acme.common
        |
        +------> com.vendor.a
        |
        +------> com.vendor.b
~~~

This design clarifies which module owns the package and avoids conflicts when consumers read the modules.

### 11.2. Rename packages when two APIs are truly independent

If two libraries model different concepts yet share the same package name, consider renaming packages so names reflect the vendor or domain namespace:

~~~text
com.vendorA.util
com.vendorB.util
~~~

This is an API change affecting source and binary compatibility; coordinate with library users and plan upgrades.

### 11.3. Choose a single dependency version

If a conflict comes from two versions of the same library, pick one compatible version and exclude the other from the dependency graph. Build tools should manage versions centrally to prevent duplicate JARs at runtime.

### 11.4. Relocate packages when shading dependencies

Some libraries bundle dependencies using shading/relocation. The dependency's packages are renamed to a private namespace to avoid colliding with versions supplied by other applications.

This packaging decision requires careful control:

- do not accidentally relocate public API packages;
- check resources, service descriptors, and reflection strings;
- ensure license and provenance notices for dependencies are preserved as required.

### 11.5. Use automatic modules as a controlled transition step

If a library lacks **module-info.java**, an automatic module can serve as a transitional step to place it on the module path. However, check:

- whether the automatic module name is stable;
- which packages are exported;
- whether there are split packages with other modules;
- whether dependencies share duplicate module names.

Automatic modules do not fix overlapping packages automatically. They simply provide a way to place a non-modular JAR into the module graph.

### 11.6. Do not use add-exports to fix split packages

**--add-exports** adds export permission for a package from one module to another in certain compatibility scenarios. It does not merge two split packages and does not resolve conflicts when two modules export the same package to one consumer.

Similarly, **--add-opens** serves deep reflection; it is not a tool for fixing package collisions. Fix the root cause in dependency/module layout.

## 12. Compile and Run Workflow in Java 17

When working with modular applications, follow this workflow:

1. Identify the modules and the packages belonging to each module.
2. Place **module-info.java** at the corresponding source/module root.
3. Declare **requires** for module dependencies.
4. Export the appropriate API packages with **exports**.
5. Place modular JARs or exploded modules on the module path.
6. Compile with **javac** using the appropriate module source path or module path.
7. Run with **java --module-path** and select the module entry point.
8. If errors occur, inspect module names, readability, exports, and split packages before adding compatibility options.

Example compile and run commands:

~~~bash
javac --module-source-path src -d out \
    -m com.acme.greetings,com.acme.app

java --module-path out \
    -m com.acme.app/com.acme.app.Main
~~~

For classpath applications, the workflow is simpler:

~~~bash
javac -cp "lib/*" -d out src/com/acme/app/Main.java
java -cp "out:lib/*" com.acme.app.Main
~~~

On Windows, replace the colon in the classpath with a semicolon. The wildcard lib/* adds JARs in the directory to the classpath; it does not turn them into named modules.

## 13. Common Errors and How to Fix Them

| Symptom | Cause | Resolution |
| --- | --- | --- |
| **ClassNotFoundException** | Class is missing from the appropriate classpath/module path or class name is misspelled. | Check the launch command, JAR location, and binary name. |
| **NoClassDefFoundError** | Required class could not be loaded at runtime or class initialization failed. | Check runtime dependencies, classpath/module path, and root initialization failure. |
| **module not found** | Module name in **requires** was not found on the module path. | Use **jar --describe-module**; verify module name and paths. |
| Package not exported | Module reads the dependency, yet the needed package is unexported. | Add appropriate **exports** in the API-providing module or use the right public API. |
| Named module cannot read class on classpath | Classpath JAR belongs to unnamed module; named modules do not read it by default. | Move JAR to module path if appropriate or use **--add-reads** as a transitional bridge. |
| Split-package conflict | Multiple modules export the same package to one consumer. | Consolidate package into one module, rename namespace, or remove duplicate dependency. |
| **NoSuchMethodError** at runtime | Runtime loaded a different class version than used at compile time. | Remove duplicate JARs, align dependency versions, and check classpath ordering. |
| Two modules with the same name | Multiple artifacts declare the same module name on the module path. | Pick one artifact/version and remove duplicates from the module path. |
| Legacy JAR works on classpath yet fails on module path | Automatic module or JPMS surfaced dependency, export, or package conflicts. | Inspect descriptors, module graph, and split packages; migrate dependency by dependency. |
| Using **--add-opens** to fix package compile error | Confusing reflection permission with readability/exports. | Use **requires**/**exports** properly; **opens** is only for deep reflection. |

## 14. Practice Exercises

### Exercise 1 — Choosing classpath or module path

A small program has only **Main.java** and two JARs without module descriptors. Write the **javac** and **java** commands using the classpath to compile and run the program. Then explain which module the classes are placed into.

### Exercise 2 — Reading a module descriptor

Given module:

~~~java
module com.acme.orders {
    requires com.acme.common;
    exports com.acme.orders.api;
}
~~~

Answer:

1. Which module does this module read?
2. Which package is exported?
3. Can another module use classes in an unexported internal package?
4. How does **exports** differ from **opens**?

### Exercise 3 — Finding the cause of a split package

Two modules **com.vendor.one** and **com.vendor.two** both export package **com.shared.util**. Module **com.acme.app** declares **requires** on both. Explain why the consumer hits a conflict and propose how to reorganize the dependencies.

### Exercise 4 — Duplicate classes on the classpath

Two JARs both contain **com.acme.Version**. The application runs but prints an unexpected version. Explain the role of classpath ordering and why duplicate JARs should be removed rather than relying on lookup order.

### Exercise 5 — Automatic module

A JAR without **module-info.class** is placed on the module path. Explain why it can still be used in **requires**, how its module name is determined, and the limitations of automatic modules compared to named modules with descriptors.

### Exercise 6 — Investigating an application that fails to start

An application reports **module not found** after migrating from the classpath to the module path. List diagnostic steps using **jar --describe-module**, checking **module-info.java**, inspecting the module path, and enabling **--show-module-resolution**.

## 15. Summary for Using Classpath and Module Path

- The classpath is the traditional class lookup mechanism; classpath classes belong to the class loader's unnamed module.
- The module path resolves modules by name; named modules declare dependencies and API packages in **module-info.java**.
- **requires** creates readability; **exports** exposes packages; **opens** serves deep reflection.
- A JAR without a module descriptor on the module path can become an automatic module; verify its name with **jar --describe-module**.
- Named modules do not automatically read the unnamed module; **--add-reads** can serve as a transitional bridge, though explicit dependencies should be designed.
- Split packages across named modules cause conflicts when exported together to a consumer; let one module own a package.
- Duplicate classes on the classpath can cause the class loader to load a version by lookup order, creating subtle linkage errors.
- Avoid multiple versions of the same dependency and multiple modules with the same name on the module path.
- Use **jar --describe-module**, **java --show-module-resolution**, and **jdeps --check** to investigate module structure.
- Do not use **--add-exports** or **--add-opens** to fix split packages; fix dependencies and module boundaries.

### References

- [Java SE 17 API — Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html) — runtime module model.
- [Java SE 17 API — ModuleLayer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html) — module layers and module graphs.
- [Java SE 17 javac documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html) — **--module-path**, **--module-source-path**, **--module**, and compilation options.
- [Java SE 17 java documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html) — classpath, module path, **--module**, **--add-reads**, and **--show-module-resolution**.
- [Java SE 17 jar documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html) — JAR packaging and **--describe-module**.
- [Java SE 17 jdeps documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html) — dependency analysis and module checks.
- [JEP 261: Module System](https://openjdk.org/jeps/261) — design of the Java module system.
