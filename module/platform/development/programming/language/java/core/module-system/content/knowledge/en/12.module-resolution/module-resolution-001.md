# ModuleFinder.of and Finding Modules on the Module Path

## 1. Objectives

After this lesson, you will be able to:

- Understand `ModuleFinder` in the Java Platform Module System (JPMS) and its role in **module resolution**.
- Create a `ModuleFinder` from physical paths using `ModuleFinder.of(Path... entries)`.
- Find a module with `find(name)`, list observable modules with `findAll()`, and read the `ModuleDescriptor` and location of a `ModuleReference`.
- Distinguish between **finding a module**, **resolving the module dependency graph**, and **loading modules for execution**.
- Identify common cases: modular JAR, exploded module, automatic module, duplicate names, and incorrect paths.

Examples apply to Java 9 and later. The example commands assume the current working directory is the project directory.

## 2. Where Does ModuleFinder Fit in the Resolution Process?

JPMS describes an application through named modules declared in `module-info.java`. A module can require another module with `requires`, export packages with `exports`, or declare services via `uses`/`provides`.

`java.lang.module.ModuleFinder` is the interface for **finding module definitions**. A finder provides a `ModuleReference` for each module it sees; the reference contains a `ModuleDescriptor` (name, `requires`, `exports`, `opens`, etc.) and can provide the URI where the module is stored.

Mental sequence:

1. **Locate/discovery:** `ModuleFinder.of(...)` identifies which modules exist on the specified paths.
2. **Resolve:** `Configuration.resolve(...)` selects the root modules and resolves required dependencies to build a `Configuration`.
3. **Load/runtime:** a `ModuleLayer` with appropriate class loaders is what brings the configuration into the runtime environment.

Therefore, `finder.find("com.example.greeting")` returning a non-empty value **does not mean** the module has been included in the resolution graph or loaded by the JVM into a layer.

## 3. Key APIs

~~~java
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;
import java.util.Optional;
import java.util.Set;

ModuleFinder finder = ModuleFinder.of(Path.of("mods"));
Optional<ModuleReference> one = finder.find("com.example.greeting");
Set<ModuleReference> all = finder.findAll();
~~~

| API | Meaning |
| --- | --- |
| `ModuleFinder.of(Path... entries)` | Creates a finder that scans the specified module path entries. |
| `finder.find(String name)` | Finds a module by **module name**; returns `Optional<ModuleReference>`. |
| `finder.findAll()` | Retrieves the set of modules found by the finder; do not rely on the iteration order of the `Set`. |
| `reference.descriptor()` | Reads the `ModuleDescriptor`: name, version if present, dependencies, and module directives. |
| `reference.location()` | Returns an `Optional<URI>` for the module's location if known to the finder. |
| `ModuleFinder.ofSystem()` | Finds the system modules provided by the runtime image. |
| `ModuleFinder.of()` | An empty finder when no entries are passed. |

The arguments to `of` are `Path` objects pointing to **module-path entries**, such as a modular JAR or a directory containing multiple modules. A directory containing module JARs is usually the most convenient entry, for example `mods/`. An exploded module is a directory containing `module-info.class` and the classes/packages of that module itself. For an automatic module, a JAR without `module-info.class` can still be recognized on the module path; its name will be derived from metadata or the JAR filename.

`Path.of("mods")` is a relative path with respect to the Java process's working directory. The API does not automatically use the classpath or read environment variables to locate modules for you; pass the actual path.

## 4. Preparing a Modular JAR for Testing

Create the following two source files:

**`src/com.example.greeting/module-info.java`**

~~~java
module com.example.greeting {
    exports com.example.greeting;
}
~~~

**`src/com.example.greeting/com/example/greeting/Greeting.java`**

~~~java
package com.example.greeting;

public final class Greeting {
    private Greeting() {}

    public static String text() {
        return "Hello from module!";
    }
}
~~~

Create the two directories `out/com.example.greeting` and `mods` beforehand using the appropriate command for your operating system, then run:

~~~sh
javac -d out/com.example.greeting src/com.example.greeting/module-info.java src/com.example.greeting/com/example/greeting/Greeting.java
jar --create --file mods/com.example.greeting.jar -C out/com.example.greeting .
~~~

Inspect the JAR:

~~~sh
jar --describe-module --file mods/com.example.greeting.jar
~~~

You will see the name `com.example.greeting` and the exported package. At this point, the `mods` directory contains a modular JAR ready for `ModuleFinder` to discover. If the commands contain spaces in paths, use the appropriate shell quoting syntax.

## 5. Example: find, findAll, and ModuleReference

Save the following program as **`InspectModulePath.java`**. This is a Java program running on the regular classpath that uses ModuleFinder to *inspect the metadata* of modules at a user-supplied path.

~~~java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Comparator;

public class InspectModulePath {
    public static void main(String[] args) {
        if (args.length == 0) {
            System.err.println("Usage: java InspectModulePath <module-path-entry>...");
            return;
        }

        Path[] entries = Arrays.stream(args)
                .map(Path::of)
                .toArray(Path[]::new);

        ModuleFinder finder = ModuleFinder.of(entries);

        finder.find("com.example.greeting").ifPresentOrElse(ref -> {
            ModuleDescriptor descriptor = ref.descriptor();
            System.out.println("Found: " + descriptor.name());
            System.out.println("Automatic: " + descriptor.isAutomatic());
            System.out.println("Requires: " + descriptor.requires());
            System.out.println("Location: " +
                    ref.location().map(Object::toString).orElse("(no URI)"));
        }, () -> System.out.println("com.example.greeting not found"));

        System.out.println("All modules in finder:");
        finder.findAll().stream()
                .sorted(Comparator.comparing(ref -> ref.descriptor().name()))
                .forEach(ref -> System.out.println("- " +
                        ref.descriptor().name()));
    }
}
~~~

Compile and run:

~~~sh
javac InspectModulePath.java
java InspectModulePath mods
~~~

The output may look like (the URI and display format depend on the operating system):

~~~text
Found: com.example.greeting
Automatic: false
Requires: [mandated java.base]
Location: file:///.../mods/com.example.greeting.jar
All modules in finder:
- com.example.greeting
~~~

The descriptor's `requires()` may represent `java.base` with different modifiers depending on the module; do not write programs that depend on the printed string of a `Set` or the order of `findAll()`. If `find(name)` returns `Optional.empty()`, check the actual module name and the passed path.

If you want to search directly from a JAR file instead of a directory, you can use:

~~~java
ModuleFinder oneJar = ModuleFinder.of(
        Path.of("mods/com.example.greeting.jar"));
~~~

Do not add both `mods` and a JAR inside `mods` to the finder at the same time if doing so causes a module to appear more than once.

## 6. From ModuleFinder to Module Resolution

Once the finder sees the modules, it can be used as a source of module definitions for `Configuration.resolve`. The standalone example below assumes the JAR was created in section 4.

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public class ResolveGreeting {
    public static void main(String[] args) {
        ModuleFinder applicationModules = ModuleFinder.of(Path.of("mods"));

        Configuration configuration = ModuleLayer.boot()
                .configuration()
                .resolve(
                        applicationModules,
                        ModuleFinder.ofSystem(),
                        Set.of("com.example.greeting")
                );

        configuration.findModule("com.example.greeting")
                .ifPresent(module -> {
                    System.out.println("Resolved: " + module.name());
                    module.reads().forEach(dependency ->
                            System.out.println("Reads: " + dependency.name()));
                });
    }
}
~~~

Run with `javac ResolveGreeting.java` and `java ResolveGreeting`.

Here:

- `ModuleLayer.boot().configuration()` provides the parent configuration from the boot layer.
- `applicationModules` is the finder checked first to locate application modules in this resolution.
- `ModuleFinder.ofSystem()` can provide system modules that are not yet available in the parent configuration.
- `Set.of("com.example.greeting")` selects the **root module**. The resolver follows the required `requires` directives, validates consistency, and creates a `Configuration`; it may throw `FindException` or `ResolutionException` when resolution cannot succeed.
- `configuration.findModule(...)` checks whether a module has been resolved; unlike `finder.find(...)`, which only checks whether the module can be found.

The code above **has not created a new `ModuleLayer`**. If you need to call classes in the resolved module at runtime, you must define a layer and appropriate class loaders, for example via `ModuleLayer.defineModulesWithOneLoader` or `ModuleLayer.defineModulesWithManyLoaders`; `resolve` alone does not do that.

## 7. Automatic Modules, System Modules, and Composed Finders

**Modular JAR:** contains the `module-info.class` descriptor; `descriptor.isAutomatic()` is `false`. The name, `requires`, and `exports` come from the descriptor.

**Automatic module:** a JAR without a descriptor when treated as a module-path entry; `descriptor.isAutomatic()` is `true`. Its name can come from the `Automatic-Module-Name` manifest attribute or be derived from the JAR filename. The derived name may change when the JAR filename or version changes, so you should not assume an arbitrary name. Inspect it with `jar --describe-module --file path/to/library.jar` or list the descriptor via a finder. Automatic modules have special readability/exports rules; they cannot be treated as equivalent to explicit modules.

**System modules:** `ModuleFinder.ofSystem()` finds modules belonging to the current Java runtime, such as `java.base`; it does not replace a finder pointing to application JARs in `mods`.

When you need to combine multiple search sources, there is the `ModuleFinder.compose(first, second, ...)` API. An earlier finder takes precedence if multiple finders provide the same module name; you should intentionally design this order. Unlike having duplicate names within *the same module path*, this is a mechanism for composing finders.

## 8. Common Errors and Troubleshooting

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| `find(name)` is empty | Wrong path, different working directory, or wrong module name | Print `Path.of("mods").toAbsolutePath()`, verify the file exists, and run `jar --describe-module`. |
| `findAll()` is empty | Module path directory does not contain valid modules yet | Confirm the JAR or exploded module has been built and the entry points to the right directory level. |
| `FindException` during discovery | Invalid JAR/descriptor or conflicting module definitions, such as duplicate names | Read the exception message, list the module path, remove duplicate entries, and fix the JAR. |
| Finder sees the module but resolution fails | Missing `requires` target or an issue in the dependency graph | Read `descriptor.requires()`, add a finder containing the dependency modules, and check roots and parent configuration. |
| Found but cannot invoke classes at runtime | Only discovery/resolve performed; no layer created or readability/exports not configured | Check `Configuration`, `ModuleLayer`, exports, and class loaders. |
| Third-party JAR has an unexpected module name | The JAR is an automatic module whose name is derived from manifest/filename | Check `descriptor.name()` instead of guessing from the library name. |

Note: `ModuleFinder.of(Path...)` works with the **module path** you pass to it. The launcher's `--module-path` is a configuration option when running a program; the two mechanisms are related, but placing a JAR on the classpath does not automatically allow the finder to detect it. When debugging, always clarify which entries were passed to the finder.

## 9. Practice Exercises

1. Change the inspector run command to `java InspectModulePath mods/com.example.greeting.jar`. Compare `find` and `findAll` with the directory-based case.
2. Change the name passed to `finder.find` to `com.example.unknown`. Explain why an empty `Optional` is not the same as a resolution exception.
3. Create an additional module `com.example.consumer` declaring `requires com.example.greeting;` and package it into `mods`. Set the resolver root to `com.example.consumer` and observe both modules in `Configuration`.
4. Place a JAR without `module-info.class` into a separate directory. Inspect `descriptor.name()` and `isAutomatic()`. Try specifying the name explicitly using the `Automatic-Module-Name` manifest attribute when repackaging the JAR.
5. Temporarily change the `mods` path to a directory containing no modules, then distinguish between an empty finder result and an error when the resolver attempts to resolve a non-existent root.

**Self-check questions:** What does `find` return when a module is missing? Does `findAll` guarantee any order? When is `Configuration.resolve` needed? Why does `ModuleFinder.ofSystem()` not replace the path to application JARs? To *run code* in a newly resolved module, what other object is still needed?

## 10. Key Takeaways

`ModuleFinder.of` provides the starting point for **discovering modules on the module path**. `find` and `findAll` provide metadata via `ModuleReference`, whereas `Configuration.resolve` is what resolves the dependency graph from the specified roots. When dynamic module execution is needed, proceed to create a `ModuleLayer` and choose appropriate class loaders. Distinguishing these three steps helps avoid confusing “the module is on disk”, “the module is resolved”, and “the module is ready to load classes”.
