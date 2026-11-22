# Class path, module path, and the impact of modules on class access in the JVM

## Lesson Objectives

Since Java 9, the Java Platform Module System (*JPMS — Java Platform Module System*) adds a layer describing **which module depends on which module and which packages are allowed to be accessed**. Therefore, having a `.class` file or JAR exist on disk is not enough to conclude that source code can import its types, that the JVM can find it, or that reflection can read private members inside it.

After this lesson, you will be able to:
- Distinguish between **class path**, **module path**, and the ways classes/interfaces are located when running Java.
- Understand **unnamed module**, **named module** (explicit and automatic), and the role of `module-info.java`/`module-info.class`.
- Explain the concepts of **observability**, **module resolution**, **readability**, and **accessibility** without conflating them.
- Apply `requires`, `exports`, `opens`, `requires transitive`, and related command-line options.
- Compile/run Java 17+ examples using the class path and module path; understand why the two examples use different configuration approaches.
- Diagnose "module not found", "package is not visible", `ClassNotFoundException`, `NoClassDefFoundError`, and `InaccessibleObjectException` errors.
- Remember that runtime class identity still depends on **binary name and defining class loader**, not simply a path or module name.

## 1. What problems do class path and module path solve?

**Class path** is the list of locations where the JVM/Java tools search for application classes using the traditional mechanism: directories containing package structures and JARs. Application code placed on the Java launcher's class path typically belongs to the **unnamed module** of the corresponding class loader.

**Module path** is the list of locations for the module system to discover **modules**. A module is typically a JAR with `module-info.class` (*modular JAR*) or a compiled module directory (*exploded module*). Regular JARs without a module descriptor can still become **automatic modules** when placed on the module path, depending on naming rules.

These two concepts do not completely replace each other. A program can use both, but **placing a JAR in a different location can change how the JVM groups code into modules and how access checks are performed**.

| Criterion | Class path | Module path |
| --- | --- | --- |
| Common inputs | Directories of `.class` files, JARs | Exploded modules, modular JARs, some regular JARs as automatic modules |
| Module of code placed there | Usually the **unnamed module** | **Named module** after being discovered and resolved |
| Configuration in `java` | `-cp`, `-classpath`, `--class-path` | `-p`, `--module-path` |
| Configuration in `javac` | `-cp` / `--class-path` | `--module-path` |
| Dependency relationships | Does not declare a dependency graph via `module-info` | `requires` and the module resolution/readability process |
| Public package control | Mainly based on Java access modifiers | Adds **`exports`** and **`opens`**, depending on readable modules |
| Running main | `java -cp out pkg.Main` | `java --module-path mods -m name/pkg.Main` |
| Common issues | Wrong classpath, missing JAR, duplicate dependencies | Module not resolved, module not readable, package not exported/opened, split package |

**Do not confuse:**
- Class path **is not** a package name. The package `com.example.api` corresponds to the path `com/example/api` **under the classpath root**, not that the root itself must point to the final `api` directory.
- Module path **is not** a direct path to every class in a module. It contains locations where modules can be found, while classes are identified through modules and class loaders.
- Putting a JAR file on the module path **does not guarantee that the module has been resolved**. Resolution also depends on root modules, `requires`, and launcher options.
- Module path **is not an automatic solution to fix ClassNotFoundException**. Finding/loading/accessing a class involves several distinct steps.

## 2. Runtime class identity is not just the display name

In Java source code, we write `com.example.api.Service`; the JVM uses the *binary name* and class loader to identify a runtime class/interface. According to the JVMS model, class identity is based on the **pair (binary name, defining class loader)**.

Example:

~~~text
Source / binary name: com.example.api.Service
JVM internal name:    com/example/api/Service
Class file:           com/example/api/Service.class

Class loader L1 defines Service -> class identity A
Class loader L2 defines Service -> class identity B
~~~

Two classes with the same name but defined by **two different defining class loaders** can be **two different types**: casting from A to B can fail. Conversely, two paths containing copies with the same name do not prove that the JVM will load both: delegation strategy, classpath search order, module graph, and custom loaders determine which class is found/defined.

Modules are **an additional organization and access control layer**. You cannot simplify it to "class identity = module name + class name"; the class loader remains the core factor. To observe this in practice, Java provides:
- `SomeType.class.getClassLoader()`: the defining loader, which may return `null` for classes defined by the bootstrap loader.
- `SomeType.class.getModule()`: the module that owns the runtime class.
- `SomeType.class.getModule().isNamed()`: distinguishes between named and unnamed modules.
- `SomeType.class.getModule().getName()`: the module name if it is named; may return `null` for an unnamed module.

A resolved named module is typically associated with an appropriate class loader and module layer; a loader, depending on its implementation, may define multiple modules. **Module layers** allow an application to create its own additional module configurations, but they do not by themselves change the class identity rules stated above.

## 3. Class path example: application without a module descriptor

Create the file **`ClassPathDemo.java`** in the working directory:

~~~java
public class ClassPathDemo {
    public static void main(String[] args) {
        Module module = ClassPathDemo.class.getModule();

        System.out.println("named=" + module.isNamed());
        System.out.println("moduleName=" + module.getName());
        System.out.println("message=classpath works");
    }
}
~~~

Run with JDK 17+:

~~~bash
javac --release 17 -d out ClassPathDemo.java
java -cp out ClassPathDemo
~~~

**Exact stdout in this classpath configuration:**

~~~text
named=false
moduleName=null
message=classpath works
~~~

Explanation:
1. `javac -d out` places `ClassPathDemo.class` into the `out` directory.
2. `java -cp out ClassPathDemo` uses `out` as the **classpath root**.
3. The application class is in the unnamed module, so `isNamed() == false` and `getName() == null`.
4. No `module-info.java` is needed when running the example above.

For code in a package, for example `package demo; public class Main { ... }`, the compiled file resides in the structure `out/demo/Main.class` and the launcher must use the **package-qualified name**:

~~~bash
java -cp out demo.Main
~~~

**Do not run** `java -cp out/demo Main` as the standard configuration for using a class with package `demo`; the Java launcher searches by binary name with the appropriate classpath root. The package example above is a **descriptive snippet**, not adding an existing file from a previous standalone program.

### How to write multiple classpath entries

Form:

~~~text
java -cp <classpath> pkg.Main
~~~

Where each classpath entry can be a directory or a JAR, separated by:
- On **Windows**: semicolon `;`.
- On **Linux/macOS**: colon `:`.

Illustrative example (assuming the paths actually exist):

~~~text
Windows:
java -cp "out;libs/api.jar;libs/impl.jar" demo.Main

Linux/macOS:
java -cp "out:libs/api.jar:libs/impl.jar" demo.Main
~~~

The `libs/*` syntax in the classpath allows the Java launcher to expand it into the JARs directly inside that directory according to wildcard rules; it **does not mean recursively scanning all subdirectories**. You should quote paths when they contain spaces or special characters. Build setups in Maven/Gradle can configure the classpath for you, but the JVM ultimately still needs a correct set of paths at startup.

### Classpath order and duplicate dependencies

If the same binary name appears multiple times in the classpath, search order and loader behavior can cause **one version to be loaded instead of another**. The mere presence of a file does not guarantee that version is used. When investigating:
- Record the full JVM launch command and `java.class.path` when needed.
- Check the actual classpath/module path rather than just the dependency declarations.
- Use JVM class loading logging with an appropriate configuration (for example, HotSpot's `-Xlog:class+load=info`) to help analyze where classes are loaded from.
- Do not rely on wildcard JAR ordering to pick the desired dependency version; resolve conflicts in the build/deployment.

## 4. JPMS: named module, module descriptor, and module graph

An **explicit named module** has a declaration in **`module-info.java`** and is compiled into `module-info.class`. The module declaration expresses **direct dependencies**, **exported packages**, and **packages opened for deep reflection**, along with service configurations when needed.

Illustrative example (module descriptor snippet):

~~~java
module com.acme.app {
    requires com.acme.lib;
}
~~~

A library module:

~~~java
module com.acme.lib {
    exports com.acme.lib.api;
}
~~~

Meaning:
- Module `com.acme.app` declares **`requires com.acme.lib`** to establish a readability relationship between the modules.
- Module `com.acme.lib` only exports **package `com.acme.lib.api`** according to this declaration. Other packages, even if they contain a `public class`, are not automatically accessible as API directly by code in other modules.
- Every named module has **readability to `java.base`** by implicit rule; there is no need to write `requires java.base;` for most applications.

Just because a library "is on the module path" does not mean every other named module can automatically read that library. There is a **module resolution** step that builds a configuration from **root modules** and `requires` dependency constraints, after which the system applies readability and exports to evaluate access.

### From path to a usable type: four conditions

For code in named module `A` to normally use a `public` type in package `p` of named module `B`:

1. **Observable**: module `B` must be recognized by the tools/system on the module path, system modules, or an appropriate source.
2. **Resolved**: module `B` must be present in the resolved module graph for the application.
3. **Readable**: module `A` must be able to read `B` (typically via `requires B;` or another valid relationship).
4. **Accessible**: `B` must **export** package `p` to `A`, and the class/member must also satisfy Java access modifiers such as `public`/`protected`.

These conditions are **not synonymous**. A JAR present on the module path may be observable but not resolved; a resolved module may not be readable from `A`; a readable module may still not export the package containing the type.

## 5. Java 17+ example run with module path: two real modules

Desired directory structure:

~~~text
src/
  com.acme.lib/
    module-info.java
    com/acme/lib/api/Greeter.java
  com.acme.app/
    module-info.java
    com/acme/app/Main.java
~~~

File **`src/com.acme.lib/module-info.java`**:

~~~java
module com.acme.lib {
    exports com.acme.lib.api;
}
~~~

File **`src/com.acme.lib/com/acme/lib/api/Greeter.java`**:

~~~java
package com.acme.lib.api;

public final class Greeter {
    private Greeter() {
    }

    public static String hello() {
        return "Hello from library";
    }
}
~~~

File **`src/com.acme.app/module-info.java`**:

~~~java
module com.acme.app {
    requires com.acme.lib;
}
~~~

File **`src/com.acme.app/com/acme/app/Main.java`**:

~~~java
package com.acme.app;

import com.acme.lib.api.Greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.hello());
        System.out.println("module=" + Main.class.getModule().getName());
    }
}
~~~

From the directory containing `src`, compile with **JDK 17+**:

~~~bash
javac --release 17 --module-source-path src -d mods -m com.acme.lib,com.acme.app
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

**Exact stdout:**

~~~text
Hello from library
module=com.acme.app
~~~

Why do these commands work?
1. `--module-source-path src` declares the root of a **multi-module source structure**, where each module directory has the module name and contains `module-info.java`.
2. `-m com.acme.lib,com.acme.app` in the **`javac`** command specifies the source modules to compile (different from the `-m` context of `java`).
3. `-d mods` creates exploded module directories such as `mods/com.acme.lib`, `mods/com.acme.app`.
4. `java --module-path mods -m com.acme.app/com.acme.app.Main` takes `com.acme.app` as the root module; the module graph resolves `com.acme.lib` because of the `requires` declaration; the launcher runs the main class.
5. `Greeter` is exported by the library, so importing and calling it from module `com.acme.app` is valid.

**There is only one expected result for this complete example**; if you create the paths correctly and use a JDK that supports `--release 17`, the program requires no external JARs.

### What happens if `exports` is removed?

Change the library descriptor to:

~~~java
module com.acme.lib {
    // Does not export com.acme.lib.api
}
~~~

This is an **illustrative variant**, not to be applied if you want the example above to run successfully. `Greeter` is still a **public class**, and `com.acme.app` still declares `requires com.acme.lib`. However, the package containing `Greeter` **is not exported** to the application module, so the compiler can report that the package is **not visible** / not exported. Put `exports com.acme.lib.api;` back in order to compile.

This illustrates the exact difference between the **`public` access modifier** and **JPMS package exports**. Only having both conditions satisfied is sufficient for ordinary access from another module.

## 6. Readability: `requires` and `requires transitive`

**Readability** is a module-level relationship: one module can read another module according to the module graph. An explicit named module normally declares dependencies using `requires`.

Example:

~~~text
module A requires B
module B requires C
~~~

You must not infer from those two lines that **A is guaranteed to have direct read access to C**. If module B wants modules that depend on B to also read C transitively, B can declare:

~~~java
module com.acme.facade {
    requires transitive com.acme.api;
}
~~~

If `com.acme.app` has `requires com.acme.facade;`, that transitive relationship causes the application to read `com.acme.api` according to module readability rules. **Even so, the package to be used must still be appropriately exported**, for example `com.acme.api` must export the package containing the API types.

### Some important declarations

| Syntax | Role |
| --- | --- |
| `requires other.module;` | Declares that the current module depends on the other module; the module graph allows reading it. |
| `requires transitive other.module;` | Any module that reads the current module under the corresponding relationship also gains readability to the other module by transitivity rules. |
| `requires static other.module;` | Expresses a dependency required at compile time, which may be absent at runtime if the code does not actually need to use it; optional dependencies must be designed carefully. |
| `exports com.acme.api;` | Exports the package to modules that read this module. |
| `exports com.acme.internal to com.acme.friend;` | **Qualified exports:** exports the package only to the specified modules. |
| `opens com.acme.model;` | Opens the package for deep reflective access at runtime; does not automatically grant ordinary import access at compile time. |
| `opens com.acme.model to com.acme.json;` | **Qualified opens:** opens the package only to the specified module. |
| `open module com.acme.framework { ... }` | Opens all packages of the module for deep reflection, but does not export all packages for ordinary compile-time access. |

Some specialized dependency rules such as `requires static transitive` are also supported by JPMS, but clarify the API intent and optional dependency design before using them.

**Do not overuse `requires transitive`**: it represents a dependency that forms part of the module's API, not just a "trick" so code elsewhere sees more classes. For purely internal implementation dependencies, regular `requires` is usually clearer.

## 7. Exports vs. Opens: ordinary access and reflection

This is the core point about **how modules affect class access**.

### Exports

`exports com.acme.api;` allows code in another module that **reads the current module** to have ordinary public access to `public` types in that package, subject to Java's modifier rules. **Exports does not automatically open private fields** for deep reflection.

Example of an exported package:

~~~java
module com.acme.model {
    exports com.acme.model.api;
}
~~~

Code in a module that reads `com.acme.model` can use `import com.acme.model.api.Customer;` if the class/members are public and the class exists. However, reflection with `setAccessible(true)` on a private field of `Customer` from another module **is not guaranteed** by exports alone.

### Opens

`opens com.acme.model.internal;` opens the package for **deep reflection** at runtime, allowing frameworks to have appropriate reflective access to private/package-private/protected members according to API rules and other restrictions. However, **opens is not equivalent to exports at compile time**: source code in another module is not automatically allowed to import ordinary code from a package that is only opened.

Descriptor example:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model to com.acme.json;
}
~~~

Meaning:
- Package `com.acme.domain.api` is the public API, allowing readable modules to use it directly.
- Package `com.acme.domain.model` is opened **specifically for module `com.acme.json`** so that frameworks in that module can use deep reflection.
- Other modules must not assume that the model package is exported or opened to them.

An **open module** opens all packages for reflection while still having its own set of exports. You should not use `open module` unconditionally if only one or a few packages actually need deep reflection.

### Quick reference table

| Package configuration | Import public class from another module | Deep reflection into private members |
| --- | --- | --- |
| Neither `exports` nor `opens` | No, for ordinary compile-time access | Usually blocked across module boundaries |
| `exports p;` | Yes, if readable and class/member is public | Not by `exports` alone |
| `opens p;` | Not by opens alone at compile time | May be allowed for other modules per reflection rules |
| `exports p; opens p;` | Yes | May be allowed |
| `exports p to A;` | Exported to module A, not other modules | Not by exports alone |
| `opens p to A;` | Not by opens alone | Opened only to module A |
| Package in unnamed module | Under compatibility rules, exported and opened | Easier reflection interaction, still subject to API and other security policies |

**Important caveat:** "Opening a package" does not allow arbitrary native code execution or bypassing all JVM limits; there are still access rules of the reflection API, class loaders, security, and code logic. Distinguish permissions from JPMS from system, data, and application permissions.

## 8. Unnamed module: classpath in the JPMS world

Since Java 9, code without a module declaration is assigned to the **unnamed module** of the appropriate class loader. This design supports legacy Java applications.

Characteristics:
- An unnamed module **reads every observable module** in the module system model; however, named modules on the module path still need to be **appropriately resolved** to be present in the configuration used by the application.
- An unnamed module **exports and opens all** of its packages under JPMS rules.
- A named module **cannot use a `requires` declaration to depend directly on an unnamed module**, because an unnamed module has no name to declare in a descriptor.
- There can be **multiple unnamed modules** associated with different class loaders; you should not assume there is only one physical unnamed module across the entire JVM.
- Do not confuse the unnamed **module** with the **unnamed package** (default package); a class with `package com.example;` can still belong to the unnamed module when placed on the classpath.

### Classpath needing to use a named module on the module path

Suppose library `com.acme.lib` is on the module path while a traditional program is on the classpath. Illustrative command:

~~~bash
java --module-path mods --add-modules com.acme.lib -cp classes com.acme.app.Main
~~~

This command makes sense **only if `classes` contains class `com.acme.app.Main` compiled with a classpath configuration and module `com.acme.lib` is on the module path**. `--add-modules com.acme.lib` adds the library module as a root when needed, causing it to be resolved. However, it **does not replace exports**: the classpath program only gets ordinary access to packages that the library appropriately exports.

If a named module needs to read the classpath/unnamed module, `requires` alone in `module-info.java` is **insufficient/invalid**. There are special options such as `--add-reads my.module=ALL-UNNAMED` for transitional situations; however, you should prefer modularizing the library or bringing dependencies into explicit module form rather than prolonging unnecessary special configurations.

## 9. Automatic module: regular JAR placed on the module path

A JAR **without `module-info.class`** can be treated by the module system as an **automatic module** when placed on the module path.

Key characteristics:
- Has a **module name** taken from the manifest attribute `Automatic-Module-Name` if present, or derived from the JAR filename according to rules.
- An automatic module **exports all packages** and **opens all packages** of its own, aiding compatibility with traditional libraries.
- Automatic modules have broad readability mechanisms, including the ability to read modules needed for transition, including contents belonging to unnamed modules according to module system rules.
- They **do not need `module-info.class`** in the JAR; nevertheless, they are still **named modules** when resolved on the module path.
- A name derived from the filename can change when renaming the JAR/version; you should use a stable `Automatic-Module-Name` manifest entry if compatibility is needed during transition.

**Be careful when using automatic modules:** this module can help a named-module program temporarily depend on a legacy JAR, but **it does not provide strong encapsulation by default** because all packages are exported/opened. When the library adds an explicit module descriptor in a later release, accessibility can change; you should review the packages being used.

### Three ways to place the same JAR

~~~text
lib/legacy.jar on CLASS PATH
  -> code belongs to unnamed module
  -> no module name usable in "requires"

lib/legacy.jar on MODULE PATH (no module-info)
  -> can become an automatic named module
  -> needs to be resolved; name derived/manifest

lib/modern.jar on MODULE PATH (has module-info)
  -> explicit named module
  -> requires/exports/opens per descriptor
~~~

You should not conclude from the `.jar` extension alone whether it is on the classpath or module path; **how the launcher/compiler is configured** determines the JAR's role.

## 10. Module resolution, root modules, and module graph

A module existing on the module path is **observable**, but whether it is included in the running configuration still depends on **root modules** and resolution.

When running:

~~~bash
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

`com.acme.app` is the **root module**. The resolver traverses `requires` dependencies and module constraints to build the appropriate graph; thanks to `requires com.acme.lib;`, the library module appears in the configuration.

For a program launched from the classpath, sometimes you need to add:

~~~bash
java --module-path mods --add-modules com.acme.lib -cp classes demo.Main
~~~

This is illustrative syntax requiring a real classpath main class. `--add-modules` adds the needed module as a root; it **does not automatically export closed packages** and **does not automatically grant a named module access to the unnamed module**.

Some useful options:

| Option | Role |
| --- | --- |
| `--module-path PATH`, `-p PATH` | Location to find application modules. |
| `--module NAME[/MAINCLASS]`, `-m NAME[/MAINCLASS]` | Runs the main class in a resolved named module. |
| `--add-modules M1,M2` | Adds root modules; has special values depending on the launcher, such as `ALL-MODULE-PATH`. |
| `--limit-modules M1,M2` | Limits the set of observable modules for the resolution process per JVM rules. |
| `--show-module-resolution` | Prints resolution information to diagnose the graph. |
| `--list-modules` | Lists observable modules in the launcher context and their versions. |
| `--describe-module NAME` | Displays information about a named module. |
| `jar --describe-module --file FILE.jar` | Views module information of a JAR, including automatic module when applicable. |

Inspection examples:

~~~bash
java --list-modules
java --module-path mods --describe-module com.acme.lib
java --show-module-resolution --module-path mods -m com.acme.app/com.acme.app.Main
~~~

No "exact stdout" is provided for these diagnostic commands because the output depends on the JDK, module set, actual classpath/module path, and platform. For the complete two-module example in section 5, the application stdout is specified separately.

### Split package and module conflict

**Split package** is the situation where the same package name appears in multiple modules. JPMS restricts cases where a module reads modules with overlapping packages causing ambiguity/constraint violations; this can cause compilation or resolution to fail even when combining JARs on the classpath previously worked.

Instead of relying on classpath order to work around the error:
- Identify which JARs contain the overlapping package.
- Update/replace dependencies or intentionally move/change package ownership.
- Inspect the module graph and class loaders, avoiding copying internal packages into multiple named modules.

Not all package conflicts produce the same error message; the exact error depends on the modules and compile/runtime context.

## 11. Options that break encapsulation: use intentionally

JPMS provides transitional/migration options, but they should not be the default design.

### `--add-reads`

General syntax:

~~~text
--add-reads SOURCE_MODULE=TARGET_MODULE
--add-reads SOURCE_MODULE=ALL-UNNAMED
~~~

This option adds a **readability edge** from the source module to the target module in the appropriate configuration. It **does not automatically make all private/public packages accessible**; exports and access modifiers are still required. Use it to handle cases where a named module needs to see classes in the unnamed module during migration, when `requires` cannot simply be used.

### `--add-exports`

Syntax:

~~~text
--add-exports SOURCE_MODULE/PACKAGE=TARGET_MODULE
--add-exports SOURCE_MODULE/PACKAGE=ALL-UNNAMED
~~~

Allows a package of the source module to be **additionally exported to the target**, so that code in the target module with appropriate readability can access the **public API**. It can be set at the compiler or runtime as needed; configuring it only at compile time does not automatically guarantee the runtime has the same permission.

Syntax illustration example:

~~~bash
java --add-exports java.base/jdk.internal.misc=ALL-UNNAMED -cp classes demo.Main
~~~

The command above **is not a recommendation to rely on JDK internal APIs** and only makes sense if there is a `demo.Main` class that needs that permission; internal APIs can change or disappear. Do not use `--add-exports` just because a framework needs to open a private field for reflection; in that situation, use `opens`/`--add-opens` appropriately.

### `--add-opens`

Syntax:

~~~text
--add-opens SOURCE_MODULE/PACKAGE=TARGET_MODULE
--add-opens SOURCE_MODULE/PACKAGE=ALL-UNNAMED
~~~

Opens the package for **deep reflection at runtime** for the specified target. It is not a command to "export a package for source code to import at compile time". Example:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp classes demo.Main
~~~

This is an example of **migration option syntax**, not a standalone program, and has no fixed stdout. **Java 17 strongly encapsulates JDK internals**; reflection calling `setAccessible(true)` on a private member of an unopened package can throw `InaccessibleObjectException`.

### Prefer sustainable solutions

A usually sensible order of handling:
1. **Use public APIs and configure the module descriptor properly**.
2. If a framework needs reflection, **open the specific package to the specific module** using `opens ... to ...;`.
3. If transition is unavoidable, use `--add-reads/--add-exports/--add-opens` with a narrow scope, document the reason, and plan to remove the flag.
4. Do not open an entire module or the entire JDK just to fix an unanalyzed permission error.

## 12. Accessing classes via reflection, Class.forName, and ClassLoader

Do not conflate:
- **Finding/loading a class** from a class loader.
- **Resolving the module graph**.
- **Accessing a type/member** according to JLS/JPMS.
- **Bypassing Java access checks** via reflective APIs when the package has been appropriately opened.

Call example:

~~~java
Class<?> type = Class.forName("com.acme.lib.api.Greeter");
System.out.println(type.getModule().getName());
~~~

This is an **illustrative snippet** inside a Java method; it can throw `ClassNotFoundException` and the result also depends on the loader/runtime configuration. `Class.forName` is not a "magic spell" that makes every module readable or every private field accessible.

**Merely having a `Class<?>` reference does not prove that public/private members inside it are accessible.** With reflection, `getDeclaredField` may discover the member, but `setAccessible(true)` and actual reading/writing are still restricted by module opens/accessibility per the API. Conversely, a package opened only for reflection does not mean the Java compiler can import ordinary types from that package.

### Resource lookup also has its own rules

`ClassLoader.getResource`/`Module.getResourceAsStream` are designed to find **resources**, not as a replacement mechanism for module exports/opens for class access. Named modules can have encapsulation rules for non-class resources related to opened packages; when a resource is not found, you should not automatically conclude that the JAR file does not contain it. Check the contract of the resource API being used, the resource package, and which packages the module opens.

## 13. Inspecting runtime modules with the Java API

A standalone example **`ModuleInfoDemo.java`** that can be run on the classpath:

~~~java
public class ModuleInfoDemo {
    public static void main(String[] args) {
        Module app = ModuleInfoDemo.class.getModule();
        Module base = String.class.getModule();

        System.out.println("appNamed=" + app.isNamed());
        System.out.println("baseName=" + base.getName());
        System.out.println("appReadsBase=" + app.canRead(base));
    }
}
~~~

Commands:

~~~bash
javac --release 17 ModuleInfoDemo.java
java -cp . ModuleInfoDemo
~~~

**Exact stdout on standard JDK 17+ with classpath launch:**

~~~text
appNamed=false
baseName=java.base
appReadsBase=true
~~~

Explanation:
- The class on the classpath belongs to the unnamed module.
- `String` belongs to the named platform module `java.base`.
- The unnamed module reads module `java.base`; this **does not automatically open private members** of `java.lang.String` for reflection.

### Checking readable and exported via the API

The Module API also has methods such as `Module.canRead(Module)`, `Module.isExported(String, Module)`, and `Module.isOpen(String, Module)`. They help inspect the runtime module graph state, but should not be used to guess all Java access checks:

~~~java
Module base = String.class.getModule();
Module caller = ModuleInfoDemo.class.getModule();

System.out.println(base.isExported("java.lang", caller));
System.out.println(base.isOpen("java.lang", caller));
~~~

The snippet above is an **illustration inside a method of class ModuleInfoDemo**; do not merge it into the previous example before compiling without editing the source appropriately. Values may differ if the runtime is launched with `--add-opens`/`--add-exports` flags or a custom module configuration.

## 14. Common errors and how to handle them

| Symptom | Possible cause | Investigation direction |
| --- | --- | --- |
| `Error: Could not find or load main class ...` | Wrong classpath root, wrong binary name, missing main class, or loader cannot find it | Check that `-cp` points to the package root, full name, and actual class file. |
| `ClassNotFoundException` | Class loader/reflective lookup cannot find the requested binary class | Check classpath, module graph, loader being used, binary name. |
| `NoClassDefFoundError` | VM cannot load/define a needed class or class initialization previously failed | Check the cause and actual version/dependency; do not just look for filenames. |
| `module not found: com.acme.lib` | Module is not observable with the path/name being used, or does not satisfy resolution | Check `--module-path`, module name, `module-info`/manifest. |
| `package ... is not visible` | Caller module does not read target or package is not exported to caller | Check both `requires` and `exports` and qualified exports. |
| Public class in unexported package is rejected | `public` is not enough across named module boundaries | Export the right package; do not try to fix access with reflection. |
| `InaccessibleObjectException` when calling `setAccessible(true)` | Module owning the package does not open it to the module calling reflection | Add `opens p to framework.module;` or temporary `--add-opens`; do not use `--add-exports` instead. |
| `IllegalAccessError` at runtime | Executing binary violates access checks when class/module configuration differs from build time | Compare module graph, exports, build/runtime artifacts, JAR versions. |
| Named module cannot import class on classpath | Named module has no `requires` dependency on unnamed module | Modularize the dependency or use an appropriate `--add-reads` migration flag. |
| JAR is on module path but program cannot find class | Module not resolved, different package/module name, wrong loader/context | Check root modules, `--add-modules`, descriptor, and exports. |
| "Modules have split package" or resolution conflict | Same package resides in multiple modules causing conflict | Review dependencies, remove duplicates/change ownership; do not rely on classpath order. |
| Renaming JAR breaks `requires X` | Automatic module name was derived from filename | Use a stable module name via manifest or explicit module-info. |
| Pre-Java 9 reflection into JDK privates worked, Java 17 fails | Strong encapsulation of JDK internals | Upgrade framework/API; open limited packages if transition is unavoidable. |
| Has `requires transitive` but still cannot import type | Dependency's package is not exported to using module or class/member is not public | Check readability **and** exports, not just the requires chain. |

### Practical investigation checklist

1. **Is it compiling or running?** Compile-time errors can differ from linking/access errors of already generated bytecode.
2. **Where is the class located?** Check `.class` path, JAR, binary name, and package structure.
3. **Is the JAR placed on the classpath or module path?** Do not conclude from build.gradle/pom.xml if the actual runtime differs.
4. **What kind of module is it?** Explicit named, automatic named, or unnamed?
5. **Has it been resolved?** Check root modules, `requires`, `--add-modules`, and `--show-module-resolution` output.
6. **Can the caller read the target module?** Check requires, transitive edges, `Module.canRead` if needed.
7. **Is the package exported to the caller?** Check `exports`/qualified exports, class/member modifiers.
8. **Is deep reflection involved?** Check `opens`/qualified opens instead of only `exports`.
9. **Which class loader defined the class?** Do not overlook custom loaders, module layers, or duplicate JARs.
10. **Compare build and runtime artifacts**: module descriptor, `Automatic-Module-Name` manifest, JVM version, launcher options, and actual libraries.

## 15. Self-check exercises

**Question 1.** If a JAR is in `--module-path`, are its classes guaranteed to be accessible from every other named module?

**Answer:** No. The module needs to be observable/resolved, the caller needs readability, the package needs appropriate exports, and the type/member must also satisfy access modifiers.

**Question 2.** Why can `public class Internal` in an unexported package still not be imported from another named module?

**Answer:** `public` is only an access condition in Java; JPMS requires the package to be exported to the caller module in addition to readability.

**Question 3.** Does `requires B;` automatically allow module A to read module C if B requires C?

**Answer:** Not necessarily. Transitivity must be declared/established according to rules, for example B having `requires transitive C;`.

**Question 4.** What is the difference between `exports p;` and `opens p;`?

**Answer:** `exports` allows ordinary compile-time/runtime access to public/protected APIs from readable modules; `opens` allows runtime deep reflection and is not equivalent to exporting the package for ordinary source imports at compile time.

**Question 5.** Can a program on the classpath query its own module name?

**Answer:** Yes. `SomeClass.class.getModule()` returns an unnamed module; `isNamed()` is false and `getName()` is null.

**Question 6.** Named module `A` wants to use a legacy JAR on the classpath; can it write `requires unnamed;` in module-info?

**Answer:** No. An unnamed module has no module name to declare in requires; you should modularize/replace the dependency or use appropriate migration mechanisms.

**Question 7.** Why does `Class.forName(...)` not guarantee that `setAccessible(true)` on a private field will succeed?

**Answer:** Loading/looking up a class is different from module access. Deep reflection across named module boundaries may require the package to be appropriately opened.

**Question 8.** What is a JAR without module-info called when placed on the module path?

**Answer:** It can be inferred as an **automatic module**, with a name taken from the `Automatic-Module-Name` manifest or the filename, with its own compatibility rules.

**Question 9.** Can runtime class identity be determined solely by module name + class name?

**Answer:** Not accurate. According to the JVMS, runtime class/interface identity is based on **binary name and defining class loader**; module membership is additional organization/access information.

**Question 10.** Why can module path cause a split package error where classpath previously ran?

**Answer:** Named modules have constraints on the module graph, package ownership, and visibility, not allowing configurations that read modules with overlapping packages causing ambiguity. Traditional classpath has a different class lookup model, so the same set of JARs can encounter different errors when moving to JPMS.

**Question 11.** Does enabling `--add-opens` allow Java source code to import an unexported internal package?

**Answer:** No. `--add-opens` is for reflective access at runtime; ordinary source access usually requires appropriate exports and readability.

**Question 12.** Why can merely renaming a JAR cause a module that needs `requires` to fail to be found?

**Answer:** If using an **automatic module** with a name derived from the filename, the module name can change. Use an explicit module descriptor or a stable manifest name.

## 16. Mind Map

~~~text
                 SAME CLASS / JAR
                         |
                 where is it placed?
                /                \
         CLASS PATH           MODULE PATH
             |                     |
         unnamed module       named module
             |                 /          \
       exports/opens all  explicit     automatic
             |           module-info   inferred name
             |              |          exports/opens all
             |         requires / exports / opens
             |              |
             +--------------+-----------------+
                            |
                   Find and use class
                            |
                   1. Observable?
                   2. Resolved?
                   3. Readable?
                   4. Package exported?
                   5. Java modifiers OK?
                            |
                          ACCESS

Deep reflection: besides specific API conditions, check "opens"
Runtime class identity: (binary name, defining class loader)
~~~

**Key takeaway:** **the class path determines where to find classes via the traditional mechanism**, while **the module path supports discovering named modules and resolving JPMS dependencies**. For named modules, **readability does not replace exports**, and **exports does not replace opens for deep reflection**. When investigating a class that is "not found" or "inaccessible", always separate class finding/loading, resolution/readability, package accessibility, reflection, and class loader.

## Official References

- [JLS Java SE 17 — §7.7 Module Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7).
- [JLS Java SE 17 — §7.7.2 Exported and Opened Packages](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.2).
- [JLS Java SE 17 — §7.7.5 Unnamed Modules](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.5).
- [JVMS Java SE 17 — §5.3 Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3).
- [Java SE 17 — The java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html).
- [Java SE 17 — The javac Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html).
- [Java SE 17 — Migrating From JDK 8 to Later JDK Releases](https://docs.oracle.com/en/java/javase/17/migrate/migrating-jdk-8-later-jdk-releases.html).
- [Java SE 17 API — java.lang.Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html).
