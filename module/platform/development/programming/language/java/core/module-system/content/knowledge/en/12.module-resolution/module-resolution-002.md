# System Module Finder and JDK Modules

## 1. Objectives

After this lesson, you will be able to:

- Explain what “system modules” are in the Java Platform Module System (JPMS).
- Use the `java.lang.module.ModuleFinder.ofSystem()` API to discover the modules provided by the current runtime.
- Read `ModuleReference` and `ModuleDescriptor` to inspect a module's name, dependencies, exports, and information.
- Distinguish between **observable modules**, **modules selected during resolution**, and **modules present in the boot layer**.
- Use JDK commands to list modules, analyze dependencies, and inspect the resolved module graph.
- Recognize the difference between `java.*` and `jdk.*` modules, as well as the impact of JDK distributions or custom runtime images.

The examples in this lesson use Java 17 or later; the core module APIs were introduced in Java 9. The exact list of modules and results may vary by JDK version or distribution.

## 2. Where Do “System Modules” Fit in JPMS?

JPMS organizes programs into **named modules**. A named module (such as `java.sql`) is described by a descriptor, typically declared in `module-info.java` when built from source.

There are three concepts to keep distinct:

| Concept | Meaning |
| --- | --- |
| **System module** | A module provided in the currently running runtime image, typically belonging to Java SE/JDK. |
| **Observable module** | A module that the resolution process can consider, depending on system modules, the module path, and launch options. |
| **Resolved module** | A module selected into a `Configuration` because it is in the root set or lies on a required dependency path. |
| **Module in a layer** | A module attached to a specific `ModuleLayer`, which can be looked up with `findModule`. |

System modules typically reside in the modern runtime image instead of treating the entire standard library as a single `rt.jar` file as prior to Java 9. The runtime image has a special `jrt:/` filesystem to represent module contents.

The ecosystem has two common naming groups:

- `java.*`: Java SE API modules, for example `java.base`, `java.logging`, `java.xml`, `java.sql`, `java.net.http`.
- `jdk.*`: feature, tool, or implementation modules provided by the JDK, for example `jdk.compiler`, `jdk.javadoc`, `jdk.jfr`, `jdk.httpserver`, `jdk.jdeps`. The presence and stability of public APIs must be checked per module; the `jdk.` prefix does not imply that all packages inside are exported.

`java.base` is the foundational module: every module reads it by JPMS rules, and you do not need to declare `requires java.base;`.

Some JDK distributions include an aggregator module `java.se` to represent the standard module set, but you should not assume every trimmed runtime includes this module. A runtime created by `jlink` may contain only selected modules.

## 3. System Module Finder: `ModuleFinder.ofSystem()`

`ModuleFinder` is an interface in the `java.lang.module` package. It is a mechanism for **finding module descriptions**, not a class loader, and by itself it does not resolve or instantiate modules.

Methods to remember:

| API | Effect |
| --- | --- |
| `ModuleFinder.ofSystem()` | Obtains a finder for the system modules of the current runtime. |
| `finder.find("java.sql")` | Returns `Optional<ModuleReference>` if a module named `java.sql` is found. |
| `finder.findAll()` | Returns a `Set<ModuleReference>` of the modules seen by the finder. |
| `ModuleFinder.of(paths...)` | Creates a finder over paths containing modular JARs or exploded modules. |
| `ModuleFinder.compose(f1, f2, ...)` | Combines finders; when module names collide, the finder appearing earlier takes precedence. |

`findAll()` shows which modules are accessible via the finder. It **does not mean** all of those modules are participating in the application's module graph.

A finder returns `ModuleReference`, which provides access to:

- `descriptor()`: the `ModuleDescriptor` object containing the module name, `requires`, `exports`, `opens`, `uses`, `provides`, and version if present.
- `location()`: an `Optional<URI>` for where the module is referenced; system modules typically have the form `jrt:/java.base`.
- `open()`: opens a `ModuleReader` to browse or read resources inside the module; the reader must be closed properly when used.

A finder is used to observe metadata and build configurations. Type access permissions in code still depend on the graph and `exports`/`opens` declarations, not on whether a finder found the module.

## 4. Java Program to List System Modules

Create the file `SystemModuleExplorer.java`:

~~~java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.util.Comparator;

public class SystemModuleExplorer {
    public static void main(String[] args) {
        ModuleFinder systemFinder = ModuleFinder.ofSystem();

        System.out.println("=== System modules ===");
        systemFinder.findAll().stream()
                .sorted(Comparator.comparing(ref -> ref.descriptor().name()))
                .forEach(ref -> {
                    ModuleDescriptor descriptor = ref.descriptor();
                    String location = ref.location()
                            .map(Object::toString)
                            .orElse("(no URI)");
                    String version = descriptor.rawVersion()
                            .orElse("(no version)");

                    System.out.printf("%-26s version=%-12s location=%s%n",
                            descriptor.name(), version, location);
                });

        String name = "java.sql";
        boolean available = systemFinder.find(name).isPresent();
        boolean inBootLayer = ModuleLayer.boot().findModule(name).isPresent();

        System.out.println();
        System.out.printf("%s found by system finder: %s%n", name, available);
        System.out.printf("%s present in boot layer: %s%n", name, inBootLayer);
    }
}
~~~

Compile and run in a terminal with `javac`/`java` from a JDK:

~~~bash
javac SystemModuleExplorer.java
java SystemModuleExplorer
~~~

The output lines may look like:

~~~text
java.base                  version=17.0.x       location=jrt:/java.base
java.logging               version=17.0.x       location=jrt:/java.logging
java.sql                   version=17.0.x       location=jrt:/java.sql
jdk.compiler               version=17.0.x       location=jrt:/jdk.compiler
...
java.sql found by system finder: true
java.sql present in boot layer: true
~~~

This is only an illustration: the number of modules, sorted order, versions, and boot layer status depend on the runtime and launch options. `rawVersion()` may be empty; do not write code assuming every module has a version.

The key takeaway from the last two boolean values: **the finder tells you about presence in the module source; the boot layer tells you whether the module is in the startup layer of this run**. These two questions are not identical.

## 5. Reading Metadata of a JDK Module

To inspect the `java.sql` module without guessing its packages or dependencies:

~~~java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;

public class InspectModule {
    public static void main(String[] args) {
        String target = args.length == 0 ? "java.sql" : args[0];

        var optionalRef = ModuleFinder.ofSystem().find(target);
        if (optionalRef.isEmpty()) {
            System.out.println("System module does not exist: " + target);
            return;
        }

        ModuleDescriptor descriptor = optionalRef.get().descriptor();

        System.out.println("Name: " + descriptor.name());
        System.out.println("Is automatic module: " + descriptor.isAutomatic());
        System.out.println("Is open module: " + descriptor.isOpen());

        System.out.println("Requires:");
        descriptor.requires().stream()
                .sorted(java.util.Comparator.comparing(ModuleDescriptor.Requires::name))
                .forEach(r -> System.out.println("  " + r));

        System.out.println("Exports:");
        descriptor.exports().stream()
                .sorted(java.util.Comparator.comparing(ModuleDescriptor.Exports::source))
                .forEach(e -> System.out.println("  " + e));

        System.out.println("Uses:");
        descriptor.uses().stream().sorted()
                .forEach(s -> System.out.println("  " + s));

        System.out.println("Provides:");
        descriptor.provides()
                .forEach(p -> System.out.println("  " + p));
    }
}
~~~

Run:

~~~bash
javac InspectModule.java
java InspectModule java.sql
java InspectModule java.base
java InspectModule jdk.compiler
~~~

Meaning of the entries in the descriptor:

- `requires x`: the module depends directly on `x`.
- `requires transitive x`: in addition to depending on it, readability of `x` is propagated to modules that read the current module.
- `requires static x`: a dependency required at compile time but allowed to be absent at runtime.
- `exports p`: exposes package `p` so code in other modules can use the package's public API, restricted if it is a qualified export.
- `opens p`: allows deep reflective access to the corresponding package according to JPMS rules.
- `uses S`, `provides S with P`: declares consumption or provision of a service.

`ModuleDescriptor` describes the module contract; it does not by itself confirm that every implementation class can be accessed by your module. An unexported package remains strongly encapsulated against ordinary access from other modules.

## 6. How Do the Finder and Module Resolution Work Together?

Resolution is the process of determining a valid module graph from **root modules** and dependency relationships. The runtime or configuration API locates modules via finders, then traverses the required `requires`. The result is stored in `java.lang.module.Configuration` as `ResolvedModule` instances.

Conceptual diagram:

~~~text
System runtime image (java.*, jdk.*)
            |
            v
   ModuleFinder.ofSystem()
            |
            v
  ModuleReference/Descriptor
            |
            v
      Select root modules
            |
            v
 Resolution: requires, transitive,
 service binding (if requested)
            |
            v
     Configuration (graph)
            |
            v
 ModuleLayer (defined modules)
~~~

When running a modular application, Java can also observe modules from `--module-path`. In an actual configuration, the finders used during resolution can include both system modules and application modules. `ModuleFinder.ofSystem()` alone only handles the system module source and does not replace the application's module path.

Application module example:

`src/com.example.app/module-info.java`:

~~~java
module com.example.app {
    requires java.sql;
}
~~~

`src/com.example.app/com/example/app/Main.java`:

~~~java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        Module me = Main.class.getModule();
        Module sql = ModuleLayer.boot()
                .findModule("java.sql")
                .orElseThrow();

        System.out.println("My module: " + me.getName());
        System.out.println("java.sql is named: " + sql.isNamed());
        System.out.println("App reads java.sql: " + me.canRead(sql));
    }
}
~~~

Compile the module and run:

~~~bash
javac -d mods/com.example.app src/com.example.app/module-info.java src/com.example.app/com/example/app/Main.java
java --show-module-resolution --module-path mods --module com.example.app/com.example.app.Main
~~~

In this example, `com.example.app` is the root from `--module`; `java.sql` is brought into the graph because of `requires java.sql`, and the required dependencies of `java.sql` are also resolved. With `--show-module-resolution`, the JVM prints resolution information before running the program.

The `--module-path mods` option supplies the application module; the system finder supplies `java.sql` and the JDK modules. If a required module is missing from the observable sources, resolution fails, typically with an error such as `Module ... not found, required by ...`.

### 6.1. What Is the Boot Layer?

`ModuleLayer.boot()` returns the JVM's startup layer. `ModuleLayer.boot().modules()` lists the modules actually defined in that layer, not the list of all runtime modules.

You can inspect it:

~~~java
ModuleLayer.boot().modules().stream()
        .map(Module::getName)
        .sorted()
        .forEach(System.out::println);
~~~

`ModuleLayer.boot().configuration()` is the configuration associated with the boot layer. The `Configuration` API can be used to resolve other configurations in plugin systems or custom layers. Do not confuse a finder (locating candidates) with a configuration (the resolved graph) or a layer (modules defined at runtime).

### 6.2. Presence Does Not Guarantee Readability

For example, `ModuleFinder.ofSystem().find("jdk.compiler")` returning a result does not make every application module automatically read `jdk.compiler`, nor does it make that module's internal packages public API.

For code in a **named module** to use public APIs from another module, there must be a corresponding read relationship (typically via `requires`) and the package must be exported to the calling module. Deep reflection additionally requires checking `opens` or an allowed package-opening mechanism.

## 7. Useful JDK Commands for Investigating System Modules

| Command | Purpose |
| --- | --- |
| `java --list-modules` | Lists the modules belonging to the current runtime. |
| `java --describe-module java.base` | Displays the descriptor of the specified module. |
| `java --describe-module jdk.compiler` | Displays metadata of a JDK module if it exists. |
| `java --show-module-resolution -m ...` | Traces the module graph when running a modular application. |
| `jdeps --list-deps app.jar` | Analyzes the modules/packages an application depends on at the bytecode level. |
| `jdeps --print-module-deps app.jar` | Suggests a list of modules for building a runtime image; runtime and reflection dependencies must be checked separately. |
| `jlink --list-plugins` | Lists the plugins available when building a runtime image, depending on the tool version. |

Note that the `-m ...` syntax requires an existing modular main module; only run `java --show-module-resolution` together with an actual launch command. `jdeps` performs static analysis, so it does not always detect dependencies that only appear through reflection, service loading, or configuration.

Some standalone practice commands:

~~~bash
java --list-modules
java --describe-module java.sql
java --describe-module jdk.compiler
jdeps --print-module-deps my-app.jar
~~~

Example output may contain names like `java.base@17.0.x` or `jdk.compiler@17.0.x`. Do not hard-code the JDK module list based on one machine: a full JDK, a trimmed runtime image, and different distributions can produce different results.

### 7.1. Trimmed Runtime Images and `jlink`

`jlink` can build a runtime image containing a selected set of modules. Illustrative example (adjust the path for your environment):

~~~bash
jlink --module-path /path/to/jdk/jmods --add-modules java.base,java.logging --output custom-runtime
~~~

To see the modules packaged in the resulting image:

~~~bash
custom-runtime/bin/java --list-modules
~~~

On Windows, the executable is typically `custom-runtime\bin\java.exe`. Depending on the OS, the `--module-path` path should point to the appropriate `jmods` directory of the JDK.

A program running on this image receives the system finder of **that image itself**. Therefore, a module present in the JDK during development may be absent in a minimal runtime. If the application needs `java.sql`, the image must contain it and its dependencies.

Some JDKs include the `jmod` command for working with `.jmod` archives. `.jmod` files are primarily for linking/packaging a runtime, not the format normally placed on an application module path at runtime like a modular JAR. Distinguish JDK `.jmod` files from the `jrt:/...` URIs observed once a runtime has been created.

## 8. Common Error Scenarios

**1. The module is found by the finder, but `ModuleLayer.boot().findModule(...)` is empty.** The module is present in the runtime, but was not selected for this run's boot graph. Check root modules, `requires`, and launch options; there is no need to assume the runtime is broken.

**2. The application reports “Module ... not found”.** Verify the module name, the executing runtime/version, `java --list-modules`, `--module-path`, and the module descriptor. You may be running on a trimmed image, or the application module may not be on the right path.

**3. The module exists, but the compiler reports that a package is not visible.** Check whether the calling module reads the target module, whether the package is exported by `exports`, and whether the export is restricted to specific targets. `--add-exports` is a special compatibility option and does not replace proper module descriptor design.

**4. Reflection fails with `InaccessibleObjectException`.** `requires`/`exports` are usually not enough for deep reflective access. Check `opens`, `open module`, or the `--add-opens` runtime option where appropriate.

**5. Code runs on one JDK but fails on another machine.** Compare `java -version`, `java --list-modules`, and the executable path. Do not assume `jdk.*` modules, JDK tools, or internal packages are always present in every distribution.

**6. Seeing `java.se` and assuming it includes all JDK modules.** `java.se` is an aggregate module in runtimes that provide it, related to Java SE modules; `jdk.*` modules are not necessarily part of `java.se`.

## 9. Practice Exercises

1. Write a program that prints the total number of modules returned by `ModuleFinder.ofSystem().findAll()`, grouped by `java.`, `jdk.`, and other prefixes. Explain why this total may differ from a friend's machine.
2. Look up `java.base`, `java.sql`, and `jdk.compiler` using `find(name)`. For each module found, print `descriptor().name()`, `rawVersion()`, and `location()`. Handle `Optional.empty()` safely.
3. Print the list of modules in `ModuleLayer.boot()` and compare it against the system finder. Find at least one case where they differ if your environment allows, and explain the difference in meaning.
4. Create a small modular app with `requires java.logging;`, use `java.util.logging.Logger`, and launch it with `--show-module-resolution`. Identify the root and the modules pulled into the graph.
5. Use `java --describe-module java.sql` and compare it with the `descriptor.requires()` data from code. Give an example of `requires transitive` if your JDK's descriptor displays one.
6. If you are already familiar with `jlink`, create a trimmed image and run `--list-modules` using the executable inside that image. Compare it with the original JDK.

Hint for the exercises: record the **Java version and launch command** so results can be reproduced; do not treat the module list printed on one machine as an absolute standard for every environment.

## 10. Key Takeaways

- `ModuleFinder.ofSystem()` locates **modules provided by the current runtime**, based on module descriptions rather than loading classes.
- `ModuleReference` describes a module's location and info; `ModuleDescriptor` reveals the dependency contract and package exposure.
- **Resolution** selects modules from roots and dependencies to produce a `Configuration`; `ModuleLayer` is where modules are defined for execution.
- Being present in a finder, participating in a configuration, and being present in the boot layer are three states to keep distinct when debugging.
- Tools like `java --list-modules`, `--describe-module`, and `--show-module-resolution` help inspect directly; `jdeps`/`jlink` assist with dependency analysis and runtime packaging.
- The list of `java.*`/`jdk.*` modules depends on the runtime image, so always check against the exact JDK/runtime the application uses.

## 11. References

- Java SE API: `java.lang.module.ModuleFinder`, `ModuleReference`, `ModuleDescriptor`, `Configuration`.
- Java SE API: `java.lang.ModuleLayer`.
- Java Platform Module System (JPMS), JEP 261.
- Documentation for the `java`, `jdeps`, `jlink`, and `jmod` commands of the JDK version in use.
