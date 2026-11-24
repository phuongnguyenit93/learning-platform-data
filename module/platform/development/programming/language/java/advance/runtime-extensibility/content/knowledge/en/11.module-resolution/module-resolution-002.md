# Inspecting ModuleReference, ModuleDescriptor, and Declared Dependencies

## 1. Goal: Reading “What a Module Says” Before the JVM Connects Modules

In the Java Platform Module System (JPMS, Java 9+), a module has a **name**, contains packages/classes/resources, and declares relationships with other modules. When building a plugin system with a module path or custom `ModuleLayer`, we often need to answer:

- What **module name** does the discovered JAR/module file have? Is it an explicit module or an automatic module?
- Which modules does the module **declare** in `requires`, and with `transitive` or `static`?
- Which packages does the module `exports`/`opens`, which services does it `uses`, and which implementations does it `provides`?
- Which modules has the JVM **resolved**, and what actual **readability** relationships has it established?
- If a dependency is missing, should we look at metadata, module location, resolution errors, or class loaders?

Three core APIs in this guide:

| API | Represents | Used When |
| --- | --- | --- |
| `ModuleFinder` | Mechanism for finding observable modules from a system image or paths | Determining which modules can be found where |
| `ModuleReference` | Reference to a module's **contents** and its descriptor | Retrieving the descriptor, location (if known), and reading module contents |
| `ModuleDescriptor` | Declared metadata of a module | Reading name, `requires`, `exports`, `opens`, `uses`, `provides`, and module attributes |

To compare **declarations** with **resolution results**, also learn `Configuration` and `ResolvedModule`:

- `Configuration`: the graph of resolved modules (resolution), including readability edges.
- `ResolvedModule`: a node in that graph; `reads()` reports the modules it can read within the configuration.
- `java.lang.Module`: a **runtime** module already defined by the JVM in a layer; use `getDescriptor()`, `canRead(...)`, `isExported(...)`, etc. to inspect runtime state.

**Important distinction:** `ModuleDescriptor.requires()` consists of the dependencies **declared in the descriptor** (including certain implicit dependencies); it is **not** equivalent to the list of all modules a module can read after resolution. `ResolvedModule.reads()` describes the resolved graph. And `Module.canRead(...)` can reflect dynamic changes such as `addReads` after a layer is defined.

## 2. Observation and Resolution Flow Diagram

~~~text
module-info.java
   │ javac
   ▼
module-info.class + classes + resources
   │  (exploded module / modular JAR / runtime image)
   ▼
ModuleFinder.of(path...) or ModuleFinder.ofSystem()
   │ find("demo.app") / findAll()
   ▼
ModuleReference
   ├── descriptor() ──> ModuleDescriptor
   │                      ├── name()
   │                      ├── requires()  [declared dependencies]
   │                      ├── exports() / opens()
   │                      └── uses() / provides()
   ├── location() ────> Optional<URI>
   └── open() ────────> ModuleReader
   │
   │  When actually performing resolution from roots + finder + parents
   ▼
Configuration
   └── ResolvedModule
         ├── reference() ──> ModuleReference
         └── reads() ─────> Set<ResolvedModule> [readability edges]
   │
   │  When defining the module layer
   ▼
ModuleLayer / java.lang.Module (runtime)
~~~

**Do not skip steps:** `finder.find(name)` returning a `ModuleReference` proves the module is **visible to the finder**; it does not prove the module is part of the resolved configuration or current runtime layer. A module can be found on the module path without being selected as a root or transitive dependency to be included in the configuration.

## 3. ModuleReference: A “Handle” to a Module's Contents

`java.lang.module.ModuleReference` is an abstract class for which the system provides concrete implementations. Primary operations:

~~~java
// Illustrative snippet: finder is already a valid ModuleFinder.
ModuleReference reference = finder.find("demo.app").orElseThrow();

ModuleDescriptor descriptor = reference.descriptor();
Optional<java.net.URI> uri = reference.location();
try (java.lang.module.ModuleReader reader = reference.open()) {
    // Read module resources when actually needed.
}
~~~

This is an **illustrative code snippet, not a standalone program**, using types from `java.lang.module` and `java.util.Optional`. Meaning:

1. `descriptor()`: always returns the metadata of the module described by the reference.
2. `location()`: `Optional<URI>`; may be `file:` for an exploded module/modular JAR, `jrt:` for a system module, or empty if the finder does not provide a location. **Do not force** it into a `Path` via `Path.of(uri)` without first checking the URI scheme and file system provider.
3. `open()`: creates a `ModuleReader` to read contents, which may throw `IOException`. Close the reader with try-with-resources; it is not a required operation just to inspect dependencies.

`ModuleReference` does **not** mean the module's classes have been initialized, does not manage instance/plugin lifecycles, and does not automatically establish `requires` relationships for the application. It is an object used for lookup/inspection and resolution.

### 3.1. Finding a System Module

Standalone example, saved as `InspectSystemModule.java`:

~~~java
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;

public class InspectSystemModule {
    public static void main(String[] args) {
        ModuleReference ref = ModuleFinder.ofSystem()
                .find("java.base")
                .orElseThrow();

        System.out.println("name=" + ref.descriptor().name());
        System.out.println("automatic=" + ref.descriptor().isAutomatic());
        System.out.println("requires=" + ref.descriptor().requires().size());
        System.out.println("locationKnown=" + ref.location().isPresent());
    }
}
~~~

Compile/run from the directory containing the file with JDK 17+:

~~~powershell
javac --release 17 InspectSystemModule.java
java InspectSystemModule
~~~

Lines that are **stable for module `java.base`**:

~~~text
name=java.base
automatic=false
requires=0
~~~

The `locationKnown=...` line is printed next and **depends on the runtime image/finder**; on many JDKs it is `true` with `jrt:/java.base`. Do not treat the specific URI as a public path to a JAR on disk. `java.base` is chosen because it is the foundational module that is always present and does not need `requires java.base` on itself.

### 3.2. ModuleFinder: Set of Findable Modules, Not Loaded Modules

Common sources:

~~~java
// Illustrative snippets, not a standalone program.
ModuleFinder system = ModuleFinder.ofSystem();
ModuleFinder plugins = ModuleFinder.of(Path.of("plugins"));
ModuleFinder merged = ModuleFinder.compose(plugins, system);

Optional<ModuleReference> found = merged.find("com.example.plugin");
Set<ModuleReference> candidates = merged.findAll();
~~~

- `ofSystem()` finds modules in the JDK's **runtime image**.
- `of(Path...)` finds modules from the passed paths: directories containing modular JARs/automatic JARs, or exploded modules; it does not arbitrarily traverse every subdirectory.
- `compose(...)` combines multiple finders in **priority order**. A finder created from a sequence of directories also has rules for selecting same-named modules; when two modules with the same name appear **in a single directory**, the operation may throw `FindException`.
- `findAll()` returns a `Set` with no guaranteed iteration order for display. **Sort by `descriptor().name()`** if reproducible output/report files are needed.
- A finder is not required to be thread-safe; do not access and modify module path contents concurrently while expecting a safely updated snapshot.

`ModuleFinder` looks up modules by **module name**, not by Maven coordinates. Module name, JAR version, and artifact name are three different things; in particular, an automatic module can derive its name from manifest `Automatic-Module-Name` or from the JAR filename according to automatic naming rules.

## 4. ModuleDescriptor: Accurately Reading Declared Module Information

`java.lang.module.ModuleDescriptor` describes a module, compiled into `module-info.class` for an **explicit named module**, or synthesized correspondingly for an **automatic module**. It is metadata, not a `Class<?>` representing an implementation class.

APIs to remember:

| API on ModuleDescriptor | Meaning |
| --- | --- |
| `name()` | Module name, e.g. `demo.app` |
| `isAutomatic()` | Whether it is an automatic module |
| `isOpen()` | Whether it is an `open module` |
| `version()` / `rawVersion()` | Module version if recorded; does not mean a runtime version is being enforced |
| `mainClass()` | Main class in the descriptor, if present |
| `requires()` | Set of `ModuleDescriptor.Requires`: declared and implicit dependencies |
| `exports()` | Exported API packages, including unqualified/qualified exports |
| `opens()` | Packages opened for deep reflection |
| `uses()` | Names of service types the module declares it uses |
| `provides()` | Service types and provider implementation names |
| `packages()` | Packages belonging to the module according to the descriptor |
| `modifiers()` | Set of module modifiers (e.g. `OPEN` or `AUTOMATIC`) |

Note: `exports`, `opens`, and `uses/provides` are **not** “dependencies” in `requires()`. They govern access rules, reflection, and service binding, which can affect resolution or subsequent usage, so they must be read from **separate sets** rather than lumped together like Maven dependencies.

### 4.1. ModuleDescriptor.Requires Is Where Primary Dependencies Are Read

Each `ModuleDescriptor.Requires` element contains:

- `name()`: target module name.
- `modifiers()`: set of `ModuleDescriptor.Requires.Modifier`.
- `compiledVersion()`: `Optional<ModuleDescriptor.Version>` if a version was recorded at compile time and can be parsed.
- `rawCompiledVersion()`: `Optional<String>` for the raw version string, if present.

Four important modifiers:

| Modifier | Form/Scenario | Meaning |
| --- | --- | --- |
| `TRANSITIVE` | `requires transitive demo.api;` | Other modules reading the current module gain an implicit read edge to `demo.api` per JPMS rules |
| `STATIC` | `requires static java.logging;` | Dependency required at compile time, **optional at runtime**; if not resolved, there is no runtime readability edge to it |
| `MANDATED` | `requires java.base` automatically added by compiler/descriptor | Dependency declared **implicitly** in the module declaration |
| `SYNTHETIC` | Metadata generated outside explicit/implicit declarations | Dependency added synthetically; not a keyword written in `module-info.java` |

A normal `requires foo;` has an empty modifier set `[]`. A directive can also have multiple modifiers (such as static + transitive where permitted); **do not assume the set contains only one**. When printing for machine comparison, sort modifier names.

**`java.base` is a special case:** for named modules other than `java.base`, the descriptor usually has an implicit dependency on `java.base`, carrying `MANDATED` when not explicitly declared. Therefore, the “number of requires” obtained from the API may be greater than the number of `requires` directives you see in source.

### 4.2. Version Is Not a Maven/Gradle Dependency Resolver

`ModuleDescriptor.version()` is the version attached to **the module being described**, if present. `Requires.compiledVersion()` can represent the version of a required module recorded at compile time. Both can be empty. Java's `module-info.java` has **no** direct syntax like `requires lib@1.2`, and JPMS does not automatically resolve Maven group/artifact/version ranges like Maven/Gradle.

Therefore, when checking for compile-time vs. runtime mismatches, you cannot conclude “versions are enforced” solely from these `Optional` values. You must inspect the actual JARs, module path, build dependency graph, and binary compatibility.

## 5. Java 17+ Hands-On Lab: Creating Three Modules and Inspecting ModuleReference/ModuleDescriptor

The lab creates a concrete relationship:

~~~text
demo.app
    │ requires demo.util
    ▼
demo.util
    │ requires transitive demo.api
    ▼
demo.api

demo.app also declares requires static java.logging
All modules above implicitly read java.base.
~~~

What to observe: `demo.app`'s descriptor **does not have** `requires demo.api`, yet after resolution `demo.app` **can read `demo.api`** because `demo.util` declares `requires transitive demo.api`.

### 5.1. Project Structure

Create the structure:

~~~text
jpms-inspector/
├── src/
│   ├── demo.api/
│   │   ├── module-info.java
│   │   └── demo/api/Message.java
│   ├── demo.util/
│   │   ├── module-info.java
│   │   └── demo/util/Greeter.java
│   └── demo.app/
│       ├── module-info.java
│       └── demo/app/ModuleReport.java
└── mods/                # generated by javac
~~~

Directory names under `src` **match the module name**; this is the convention of `javac --module-source-path`. Each named module has its own `module-info.java`.

File `src/demo.api/module-info.java`:

~~~java
module demo.api {
    exports demo.api;
}
~~~

File `src/demo.api/demo/api/Message.java`:

~~~java
package demo.api;

public record Message(String text) {}
~~~

File `src/demo.util/module-info.java`:

~~~java
module demo.util {
    requires transitive demo.api;
    exports demo.util;
}
~~~

File `src/demo.util/demo/util/Greeter.java`:

~~~java
package demo.util;

import demo.api.Message;

public final class Greeter {
    private Greeter() {}

    public static Message greeting() {
        return new Message("hello-jpms");
    }
}
~~~

File `src/demo.app/module-info.java`:

~~~java
module demo.app {
    requires demo.util;
    requires static java.logging;
}
~~~

`demo.app` has **two explicit directives**: `demo.util` and `java.logging`. The `static` modifier indicates `java.logging` is needed at compile time, but that dependency **is not required to be present during runtime resolution**. The lab does not use any classes from `java.logging`, so it only demonstrates it in the descriptor.

### 5.2. Writing the Inspector Program Running Inside demo.app

File `src/demo.app/demo/app/ModuleReport.java`:

~~~java
package demo.app;

import demo.util.Greeter;
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.lang.module.ResolvedModule;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

public final class ModuleReport {
    public static void main(String[] args) {
        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));

        for (String name : List.of("demo.api", "demo.util", "demo.app")) {
            ModuleReference reference = finder.find(name).orElseThrow();
            ModuleDescriptor descriptor = reference.descriptor();

            System.out.println("MODULE " + descriptor.name());
            System.out.println("  automatic=" + descriptor.isAutomatic());

            descriptor.requires().stream()
                    .sorted(Comparator.comparing(
                            ModuleDescriptor.Requires::name))
                    .forEach(required -> {
                        String flags = required.modifiers().stream()
                                .map(Enum::name)
                                .sorted()
                                .collect(Collectors.joining(","));
                        System.out.println("  requires " + required.name()
                                + " [" + flags + "]");
                    });
        }

        ResolvedModule app = ModuleLayer.boot()
                .configuration()
                .findModule("demo.app")
                .orElseThrow();

        System.out.println("READS demo.api="
                + app.reads().stream()
                     .anyMatch(module -> module.name().equals("demo.api")));
        System.out.println("READS demo.util="
                + app.reads().stream()
                     .anyMatch(module -> module.name().equals("demo.util")));
        System.out.println("MESSAGE " + Greeter.greeting().text());
    }
}
~~~

Line-by-line explanation:

1. `ModuleFinder.of(Path.of("mods"))` observes the compiled exploded modules.
2. `find(name).orElseThrow()` retrieves each module's `ModuleReference`. If not found, the lab stops explicitly rather than ignoring it.
3. `reference.descriptor().requires()` returns **direct declared requirements** along with the implicit `java.base`; sorting by name ensures stdout does not depend on `Set` iteration order.
4. `required.modifiers()` is sorted and joined; `[]` means a normal dependency with no modifiers.
5. `ModuleLayer.boot().configuration().findModule("demo.app")` retrieves the **resolved module of the actually running application**. `reads()` reflects readability after resolution.
6. `Greeter.greeting()` returns a `Message` belonging to `demo.api`. `demo.app`'s code compiles and runs even without directly declaring `requires demo.api` because `demo.util` declared `requires transitive demo.api`. This is a concise illustration of the transitive effect.

### 5.3. Compile and Run Commands

Open PowerShell in the `jpms-inspector` directory on a machine with **JDK 17+**:

~~~powershell
New-Item -ItemType Directory -Force mods | Out-Null
javac --release 17 -encoding UTF-8 --module-source-path src -d mods -m demo.api,demo.util,demo.app
java --module-path mods --module demo.app/demo.app.ModuleReport
~~~

Program stdout (with the exact source files above):

~~~text
MODULE demo.api
  automatic=false
  requires java.base [MANDATED]
MODULE demo.util
  automatic=false
  requires demo.api [TRANSITIVE]
  requires java.base [MANDATED]
MODULE demo.app
  automatic=false
  requires demo.util []
  requires java.base [MANDATED]
  requires java.logging [STATIC]
READS demo.api=true
READS demo.util=true
MESSAGE hello-jpms
~~~

The two `READS` lines show that the app can read both `demo.util` (direct dependency) **and** `demo.api` (via transitive). Yet when inspecting `requires()` on **the app itself**, `demo.api` does not appear. Do not write code that infers all runtime-readable modules solely from `app.descriptor().requires()`.

If you get `module demo.app not found` or `module demo.util not found`, verify the command is running from the **correct working directory** and `mods` has the structure `mods/demo.app/module-info.class`, `mods/demo.util/module-info.class`, `mods/demo.api/module-info.class` after compilation.

## 6. Using ModuleDescriptor to Inspect exports, opens, uses, and provides

Beyond `requires`, inspect the other components to understand **why a module is readable yet a class remains inaccessible**, or **why a provider was brought into the graph**.

In a module descriptor:

~~~java
// Illustrative module-info.java of another application module.
module example.host {
    requires example.api;
    uses example.api.Task;
    opens example.host.config to example.reflect;
}
~~~

And a provider module:

~~~java
// Illustrative module-info.java of a provider module.
module example.provider {
    requires example.api;
    provides example.api.Task with example.provider.TaskImpl;
}
~~~

**These are two illustrative descriptors belonging to two different modules, not a standalone program.** The corresponding packages/modules/types must be created for them to compile.

Given `ModuleDescriptor d`:

~~~java
// Illustrative Java snippet, requires variable d of type ModuleDescriptor.
d.exports().forEach(e -> {
    System.out.println(e.source() + " -> " + e.targets());
});
d.opens().forEach(o -> {
    System.out.println(o.source() + " -> " + o.targets());
});
d.uses().forEach(service -> System.out.println("uses " + service));
d.provides().forEach(p -> {
    System.out.println("provides " + p.service() + " with " + p.providers());
});
~~~

- `exports()`: returns `ModuleDescriptor.Exports`. `source()` is the package; `isQualified()` and `targets()` indicate whether target modules are restricted. An **unqualified export** does not mean the package is open for deep reflection.
- `opens()`: returns `ModuleDescriptor.Opens`, supporting framework reflection at module scope. For an `open module`, also check `descriptor.isOpen()` because packages are opened by the module's nature even though the `opens()` set does not list each package individually.
- `uses()`: set of service interface names required by the module.
- `provides()`: set of mappings from service type to implementation names. This is **service binding metadata**, not direct `requires` dependencies.

**Checkpoint:** a module may declare `uses` and have resolution with service binding add provider modules into the graph, even without writing `requires providerModule`. Therefore, if you want to build the **actual dependency closure**, you must know whether `resolve(...)` or `resolveAndBind(...)` was used and which providers were observed.

## 7. How Direct Dependencies, Transitive Readability, and Resolved Graph Differ

Consider the exact three modules in the lab:

~~~text
Declared requires of demo.app:
  demo.util          []
  java.logging       [STATIC]
  java.base          [MANDATED]

Declared requires of demo.util:
  demo.api           [TRANSITIVE]
  java.base          [MANDATED]

After resolution of the running application:
  demo.app READS demo.util
  demo.app READS demo.api  (via requires transitive)
  demo.app READS java.base
  java.logging may not be in the graph if only requested via requires static.
~~~

### 7.1. Regular requires: Direct Dependency

`requires demo.util;` allows the app to read `demo.util` when resolved. This **does not automatically propagate** readability of all `demo.util`'s dependencies to the app. For the app to read `demo.api` through util, util must declare `requires transitive demo.api;` (or the app must declare an appropriate dependency another way).

**Readability differs from accessibility:** being able to read a module does not guarantee access to all classes. The target's package must be `exports`ed to the caller, and the public class/method must meet Java access rules; deep reflective access is further governed by `opens`.

### 7.2. requires transitive: Propagated Readability

Example:

~~~java
// module-info.java of demo.util in the lab:
module demo.util {
    requires transitive demo.api;
    exports demo.util;
}
~~~

When the app `requires demo.util`, it can read `demo.api` thanks to the transitive directive in util. Saying “the app directly declares `requires demo.api`” is **wrong**: the app's direct descriptor still only contains the app's own directives and implicit ones like `java.base`.

`requires transitive` does not mean “automatically export every package”: `demo.api` must still export the packages the app wants to use. If a library module has public code that returns a type from `demo.api`, using `requires transitive` generally helps API consumers read that type.

### 7.3. requires static: Present in Descriptor but Not Required to Resolve at Runtime

`requires static java.logging;` is stored in `ModuleDescriptor.Requires` with modifier `STATIC`, even though module `java.logging` is **not necessarily pulled in by runtime resolution** solely from that directive. If `java.logging` is resolved for another reason, the app can read it per JPMS rules; otherwise, the presence of a static directive does not create a runtime module to use.

This is why `requires()` is not the answer to “which modules are loaded right now?”. When code actually uses a class in an optional module, you must handle the case where the module is absent from the runtime graph. Specific error types/runtime behaviors depend on where the class is referenced and linked; do not assume `requires static` automatically provides a fallback.

### 7.4. requires java.base: Implicitly Added Dependency

Named modules (except `java.base`) have a dependency on `java.base` even when `module-info.java` source does not write it. The descriptor API displays `MANDATED` for this implicit dependency. Thus, when counting “how many requires a module has”, you must decide whether the report includes `MANDATED`:

- **Classfile/descriptor structure report:** keep `MANDATED` for transparency.
- **Author-written directives report:** filter out implicit dependencies and document the filter clearly, avoiding the misinterpretation that the source added `requires java.base;`.
- **Resolved graph report:** do not use the raw count of `requires()`; read `ResolvedModule.reads()`.

## 8. Creating a New Configuration to Preview Resolution Results Before Running a Plugin

`ModuleLayer.boot().configuration()` shows the boot layer's graph. If you are building a plugin platform, you can also **test resolution against a finder** before defining an actual module layer.

**Non-standalone illustrative** example (assuming `pluginModulePath` is a `Path` pointing to prepared plugin modules and `rootName` is the root module name):

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

ModuleFinder finder = ModuleFinder.of(pluginModulePath);
Configuration parent = ModuleLayer.boot().configuration();

Configuration candidate = parent.resolve(
        finder,
        ModuleFinder.of(),       // empty after finder
        Set.of(rootName));

candidate.modules().stream()
        .sorted(java.util.Comparator.comparing(m -> m.name()))
        .forEach(m -> {
            System.out.println(m.name() + " reads "
                    + m.reads().stream()
                       .map(r -> r.name())
                       .sorted()
                       .toList());
        });
~~~

This is a **resolution step, without defining a new module layer yet**. In a configuration with a parent:

- Roots and dependencies are searched in the order `before finder`, parent configurations, and then `after finder` (per API rules).
- Modules already in the parent configuration can be reused and **do not reappear in `candidate.modules()`**. If you want the entire graph including parents, you must traverse `parents()`/`findModule(name)` appropriately.
- `candidate.modules()` contains only the modules added in the new configuration, not necessarily all modules the plugin can read.
- If a dependency is missing, `FindException` may be thrown; if the graph violates consistency (cycles or package conflicts, etc.), `ResolutionException` may be thrown.
- `resolveAndBind(...)` extends resolution with service binding: it can add provider modules for discovered `uses`. That makes the actual graph differ from the direct `requires` set.

**Do not guess loaders:** creating a `Configuration` does not load/define classes yet. When defining a `ModuleLayer`, you must choose the proper module-to-class-loader mapping, such as `defineModulesWithOneLoader` or `defineModulesWithManyLoaders` with package/class loading constraints. Do not infer “one module = one loader” solely from `ModuleReference`.

### 8.1. Comparing Observation Levels in a Modular Application

| Level | API | Question Answered |
| --- | --- | --- |
| Findable | `ModuleFinder.find(name)` | Is there a module with this name in the source observed by the finder? |
| Declared | `ModuleReference.descriptor().requires()` | What dependencies and modifiers does the descriptor state? |
| Resolved | `Configuration.findModule(name)`, `ResolvedModule.reads()` | What edges exist in the readability graph after resolution? |
| Defined at runtime | `ModuleLayer.findModule(name)`, `Module.canRead(...)` | Which layer does the running module belong to, and can it read that other module at runtime? |

A real-world system sometimes has **multiple layers** and duplicate module names across different layers. When inspecting, record the **layer/configuration/loader context** as well—do not look up module names as a JVM-wide key.

## 9. Inspecting Module Descriptors with Command-Line Tools

You do not always need to write a Java inspector. Useful commands on JDK 17+:

~~~powershell
# List modules in the runtime image:
java --list-modules

# Inspect a module observable from runtime:
java --describe-module java.sql

# With the compiled demo project:
java --module-path mods --describe-module demo.app

# Observe resolution during a launch:
java --show-module-resolution --module-path mods --module demo.app/demo.app.ModuleReport

# Inspect the Module attribute in the class file (depending on path):
javap -v mods/demo.app/module-info.class
~~~

- `java --describe-module` displays the module declaration in the JDK's presentation format, not guaranteed to match `ModuleDescriptor.toString()`.
- `java --show-module-resolution` helps cross-check roots, resolved modules, and graph relationships at launch; output can span many lines and varies by runtime image and flags.
- `javap -v` inspects classfile structure, including the `Module` attribute. This is the source closest to bytecode when suspecting packaging issues.
- `jdeps` helps detect class/package dependencies from bytecode, but the **bytecode dependency graph** does not always match declared `requires` (especially with reflection, optional modules, and service binding).

A quick check inside a Java program if you **only have a runtime module object**:

~~~java
// Syntax-illustrative snippet; choose an appropriate runtime module.
Module module = String.class.getModule();
System.out.println(module.getName());
System.out.println(module.getDescriptor().name());
~~~

Stdout:

~~~text
java.base
java.base
~~~

`Class.getModule()` is tied to the module that **defined** that class. For a class on the classpath, you get an unnamed module; `getDescriptor()` on an unnamed module returns `null`, so **do not call `.requires()` directly without checking**.

## 10. Common Pitfalls When Reading Descriptors and Dependencies

### 10.1. “Having a ModuleReference means the module is resolved”

Wrong. `ModuleFinder.find` can return a candidate module that is not in the current `Configuration`. When runtime reports a module is inaccessible, check roots, visibility, and the actual graph. **A finder seeing a module** does not guarantee the running host JVM has defined that module.

### 10.2. “requires() is every module I can read”

Wrong because `requires transitive` creates additional readability; `requires static` may not lead to a runtime module; runtime may involve service binding or dynamic reads. Read `ResolvedModule.reads()` / `Module.canRead` at the exact layer you want to observe.

### 10.3. “requires transitive means exporting every package”

Wrong. `requires transitive` is about **readability**; `exports` is about access rights to public types; `opens` is about deep reflection. All three must be checked when a module is present yet the caller still cannot use a class/package.

### 10.4. “Module descriptors are required to specify a version”

Wrong. `version()` and `compiledVersion()` are `Optional`s; do not call `get()` or `orElseThrow()` without an explicit policy. JPMS module names are not Maven coordinates and do not automatically download dependencies from artifact repositories.

### 10.5. “The order of requires()/findAll() is the graph order”

Wrong. These are `Set`s with no reliable display order. If generating reports for diffing or testing, **sort by module name then modifier**. Do not infer class-loading order from metadata print order.

### 10.6. “An automatic module with empty requires() reads no other modules”

Wrong. Automatic modules have special readability/exports rules. An automatic module's descriptor typically lists only the `java.base` dependency; this does **not** fully describe runtime readability. Check `isAutomatic()` before interpreting results and use the resolved graph when you want to know the edges.

### 10.7. “A module-info.class error is caused by a missing JAR”

It could be `InvalidModuleDescriptorException`/`FindException` due to a malformed module descriptor, duplicate module names, invalid package metadata, or runtime incompatibility; it could also be `ResolutionException` when the graph violates constraints. Read the exception cause and finder/resolver logs. Swapping JARs randomly can mask another version/package error.

### 10.8. “Reading metadata with ModuleReader is always safe to keep open long-term”

`ModuleReader` is a resource that must be closed; keeping readers/streams open long-term can hold file handles or resources from the runtime/module image. When the goal is only to inspect `requires`, use `reference.descriptor()` and do not open a reader unless you truly need to read files inside the module.

## 11. Diagnostic Workflow for Plugin/Module Resolution

Suppose plugin `com.example.report` fails to run. An ordered investigation flow:

1. **Observation:** Does `ModuleFinder` on the right module path/candidate layer find the module name? If not, check the artifact, module name, path, and automatic module naming.
2. **Declaration:** Retrieve `ModuleReference.descriptor()`. Record `name`, `isAutomatic`, `requires` with modifiers, and `exports/opens/uses/provides`.
3. **Cross-check existing dependencies:** For each mandatory required module, check which finder/parent configuration contains it. Specifically for `STATIC`, understand its runtime-optional semantics.
4. **Resolution:** Use `Configuration.resolve(...)` or the existing runtime configuration; record the set of resolved modules and `ResolvedModule.reads()` edges. Catch `FindException`/`ResolutionException` with the specific cause.
5. **Layer/runtime:** If a layer is already defined, check `ModuleLayer.findModule`, `Module.canRead`, `isExported`/`isOpen`. Pay attention to parent layers and dynamic additions.
6. **Class loading:** If a class still cannot be used, cross-check class loaders, class/package visibility, and binary signatures. Successful JPMS resolution does **not** guarantee an implementation class will not hit `NoClassDefFoundError` when used.
7. **Result:** Report clearly whether it is a “missing observable module”, “unresolved module”, “wrong readability/accessibility”, or “classloading/bytecode error” so the right root cause is fixed.

### Suggested Report Format

~~~text
Root module: demo.app
Finder: module path ./mods
Module candidate: demo.app (explicit; location known)
Declared requirements:
  demo.util []                  present in finder
  java.logging [STATIC]         runtime optional
  java.base [MANDATED]          system module
Resolved readability:
  demo.util, demo.api, java.base ...
Conclusion:
  demo.api is readable via requires transitive in demo.util.
~~~

This is an **illustrative report format**, not official API stdout. The `...` indicates there may be additional readable modules depending on the resolved configuration. Do not copy the exact list from this example as the output on any given JDK.

## 12. Exercises and Completion Criteria

### Exercise A — Change requires transitive to regular requires

In `demo.util/module-info.java`, change:

~~~java
requires transitive demo.api;
~~~

to:

~~~java
requires demo.api;
~~~

This is a **descriptor snippet**, not a standalone program. Keep `demo.app` only requiring `demo.util`. Because `ModuleReport` only directly imports `demo.util.Greeter` and uses `var` inference/method chains in the current version, the application might still compile depending on how the API type is used; to clearly verify the readability relationship, add a **direct import line** `demo.api.Message` along with a variable declaration of type `Message` in the app. At that point the app will not be permitted to use public types from `demo.api` through the removed transitive relationship; you will need to add `requires demo.api;` to `demo.app/module-info.java` or restore `requires transitive demo.api;` in util.

### Exercise B — Visibility and Usage Differ

Create a module `demo.hidden` on the module path that is not required by root `demo.app` and is not a bound provider. Verify that `ModuleFinder.of(Path.of("mods")).find("demo.hidden")` can return a `ModuleReference`, whereas `ModuleLayer.boot().configuration().findModule("demo.hidden")` can be empty when launching with only `demo.app`. This is the difference between **observable** and **resolved**.

### Exercise C — Try requires static

Keep `requires static java.logging` in the app. Observe that the descriptor still contains the `STATIC` element. Cross-check `--show-module-resolution` and whether `java.logging` is resolved by the runtime or another root. Takeaway: **declared static dependency != guaranteed runtime presence**.

### Exercise D — Try Service Binding

Create a service interface in the API module, declare `uses` in the host, and `provides ... with ...` in a provider. Compare the results of `resolve` and `resolveAndBind` on the same finders/roots (remembering to account for parent configurations). Report which providers were added due to service binding, rather than assuming there was a `requires provider`.

### Outcome Checklist

You have mastered this topic when you can explain and verify:

- What `ModuleFinder.find` returns and why a module is not guaranteed to be resolved.
- How `ModuleReference.descriptor()` differs in role from `ModuleReference.open()`.
- That `ModuleDescriptor.requires()` contains declared dependencies as well as `java.base [MANDATED]`.
- How `Requires.Modifier.STATIC` and `TRANSITIVE` behave differently.
- Why the app module can read `demo.api` despite not directly declaring `requires demo.api`.
- What information `ResolvedModule.reads()` provides that `requires()` does not.
- Why `exports`, `opens`, `uses`, and `provides` must be inspected separately.
- Why the version on a module descriptor does not replace Maven/Gradle version resolution.
- How to avoid pitfalls from unnamed/automatic modules, multiple layers, and Set iteration order.
- How to reproduce issues using `java --describe-module`, `--show-module-resolution`, and a Java 17+ program.

## 13. Authoritative References

- Java SE 17 — ModuleFinder: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html
- Java SE 17 — ModuleReference: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleReference.html
- Java SE 17 — ModuleDescriptor: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleDescriptor.html
- Java SE 17 — ModuleDescriptor.Requires: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleDescriptor.Requires.html
- Java SE 17 — Configuration: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/Configuration.html
- Java SE 17 — ResolvedModule: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ResolvedModule.html
- Java SE 17 — Module runtime: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- JPMS resolution specification: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/package-summary.html
