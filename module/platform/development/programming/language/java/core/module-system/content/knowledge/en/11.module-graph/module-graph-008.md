# Inspecting the module graph with jdeps and runtime options

## 1. Objectives

When an application uses the Java Platform Module System (JPMS), the `module-info.java` file states which module depends on which module, which packages are exported outward, and which packages are opened for reflection. However, a syntactically valid descriptor is not enough to guarantee the program resolves modules successfully at runtime.

After this lesson, you will be able to:

- Read and describe the **module graph** from `requires`, `requires transitive`, and `requires static` relationships.
- Use **`jdeps`** to inspect static dependencies from bytecode, find JDK dependencies, review descriptors, and export graphs.
- Use **`java` launcher** options to see which modules are observable, which modules are resolved, and the cause of runtime errors.
- Distinguish errors for **unresolved modules**, **missing readability relationships**, **unexported packages**, and **unopened packages**.
- Identify the limitations of static analysis when an application uses reflection, `ServiceLoader`, or dynamic class loading.

Examples use Java 17 or later; the foundational JPMS commands have been available since Java 9.

## 2. What does the module graph actually contain?

The module graph has **vertices** representing resolved modules and **readability edges** representing relationships where one module can read another module. The `module-info.java` descriptor declares the required dependencies for the system to build the graph. Every named module implicitly depends on `java.base`, even when `requires java.base;` is not written.

Example:

```java
// module com.demo.api
module com.demo.api {
    exports com.demo.api;
}

// module com.demo.app
module com.demo.app {
    requires com.demo.api;
}
```

When `com.demo.app` is the root module, the minimal graph has the relationships:

```text
com.demo.app ----requires----> com.demo.api
     |                              |
     +----------> java.base <-------+
                  (implicit)
```

Three mechanisms must be distinguished:

| Concept | Meaning | How to inspect |
|---|---|---|
| **Resolution** | A module is found and placed into the resolved module set | `java --show-module-resolution`, `--validate-modules` |
| **Readability** | Module A has permission to read module B | `requires`, `requires transitive`, `--add-reads` |
| **Accessibility** | A type in a package is validly accessed per `exports` or `opens` | `module-info.java`, compile/runtime error messages, `--add-exports`/`--add-opens` |

**Being able to read does not mean being able to access every package.** For example, `com.demo.app` reads `com.demo.api` yet still cannot use public classes in packages that `com.demo.api` does not `exports`. Similarly, `exports` serves normal access; deep reflection into private members typically requires `opens`.

Important declaration forms:

```java
requires com.demo.api;                 // direct dependency
requires transitive com.demo.api;      // modules reading the current module also read api
requires static com.demo.annotations;  // required at compile time; may be absent at runtime
exports com.demo.api;
exports com.demo.internal to com.demo.friend; // qualified export
opens com.demo.model to com.demo.framework;   // allow qualified deep reflection
```

`requires transitive` is significant for API design: if `com.demo.facade` declares `requires transitive com.demo.api`, a module requiring `com.demo.facade` can read `com.demo.api` via the transitive relationship. `requires static` allows a dependency to be absent at runtime, yet **does not guarantee code that actually uses that dependency will still run** if the required classes are missing.

## 3. Building a sample two-module project

Source structure:

```text
src/
  com.demo.api/
    module-info.java
    com/demo/api/Message.java
  com.demo.app/
    module-info.java
    com/demo/app/Main.java
```

Contents of each file:

**`src/com.demo.api/module-info.java`**

```java
module com.demo.api {
    exports com.demo.api;
}
```

**`src/com.demo.api/com/demo/api/Message.java`**

```java
package com.demo.api;

public final class Message {
    private Message() {}

    public static String text() {
        return "Hello from JPMS";
    }
}
```

**`src/com.demo.app/module-info.java`**

```java
module com.demo.app {
    requires com.demo.api;
}
```

**`src/com.demo.app/com/demo/app/Main.java`**

```java
package com.demo.app;

import com.demo.api.Message;

public class Main {
    public static void main(String[] args) {
        System.out.println(Message.text());
    }
}
```

Compile the modules from the project root directory:

```sh
mkdir mods
javac --module-source-path src -d mods -m com.demo.api,com.demo.app
java --module-path mods -m com.demo.app/com.demo.app.Main
```

Program output:

```text
Hello from JPMS
```

`mods` contains **exploded modules** (directories containing `module-info.class` and classes); `--module-path` can also point to a directory containing modular JARs. In real-world environments, verify the exact module path in both the build step and the run step.

## 4. Analyzing static dependencies with jdeps

`jdeps` is included in the JDK and reads classes/JARs to report dependencies. This command is very useful before packaging, when upgrading Java, or when migrating an application from the classpath to the module path.

### 4.1. Viewing concise dependencies with `--summary`

```sh
jdeps --module-path mods --module com.demo.app --summary
```

Look for the edge `com.demo.app -> com.demo.api` and related platform dependencies. The format and number of lines displayed depend on the JDK, analysis mode, and whether `--recursive` is used; do not treat graph interpretation examples as fixed stdout across all versions.

To expand to indirect dependencies:

```sh
jdeps --module-path mods --module com.demo.app --recursive --summary
```

`--recursive` requests following dependency relationships recursively, which is useful when an application has multiple intermediate modules.

### 4.2. Listing modules required to run

```sh
jdeps --module-path mods --module com.demo.app --list-deps
```

If the module list needs to be passed to another build step or tool:

```sh
jdeps --module-path mods --module com.demo.app --print-module-deps
```

`--list-deps` prints dependent modules as a list; `--print-module-deps` produces a comma-separated list. Both options are useful for evaluating the required module set, such as before considering `jlink`. However, dependencies appearing only via reflection, service configuration, or dynamic loading may not be fully detected.

### 4.3. Checking descriptors and reduced graphs

```sh
jdeps --module-path mods --check com.demo.app
```

`--check` inspects module relationships for a named module, showing the declared descriptor, the graph after analysis, and edges that can be reduced. This is especially useful when multiple layers of `requires transitive` make dependency declarations redundant or confusing.

Read the output along these lines:

1. Which modules are declared in the descriptor?
2. Which dependencies are actually required for the module to read the types in use?
3. Are any edges inherited through `requires transitive`?
4. Does the reduced graph match the design intent, or does `module-info.java` need review?

Do not delete `requires` solely because a single tool run did not observe the relationship in bytecode: there are also compile-time APIs, services, reflection, and other deployment conditions.

### 4.4. Exporting a DOT graph

```sh
jdeps --module-path mods --module com.demo.app --dot-output build/module-graph
```

`jdeps` writes `.dot` files into the output directory. If Graphviz is installed, appropriate DOT files can be converted to SVG or PNG to read large graphs. This is the result of **static analysis** based on the provided module set and options, not an exact record of every class loaded at runtime.

### 4.5. Reviewing JDK internal APIs

```sh
jdeps --jdk-internals --module-path mods --module com.demo.app
```

The `--jdk-internals` option detects bytecode references to JDK internal APIs, such as types under `sun.*`. These APIs may be hidden by module encapsulation or changed in newer JDKs. Prefer public APIs instead of trying to open internal packages with runtime flags.

For a **multi-release JAR**, specify the target version when analyzing the corresponding classes:

```sh
jdeps --multi-release 17 --print-module-deps path/to/app.jar
```

Replace `17` with the actual Java version you want to inspect. Reports may differ across versions because different classes are selected.

## 5. Observing the module graph at runtime

`jdeps` answers: "what does the bytecode reference?". Runtime options answer: "which modules did the launcher observe and resolve during this startup?".

### 5.1. Viewing observable modules

```sh
java --module-path mods --list-modules
```

The output includes system modules and named modules observable on the module path. This is **not** proof that all listed modules were resolved into a specific application's graph.

### 5.2. Viewing descriptors recognized by the launcher

```sh
java --module-path mods --describe-module com.demo.app
java --module-path mods --describe-module com.demo.api
```

Check the module name, `requires`, `exports`, and other descriptor details. This command is very useful for spotting wrong module names, stale JARs, or descriptors that differ from the open source code.

### 5.3. Printing the module resolution process

```sh
java --show-module-resolution --module-path mods \
  -m com.demo.app/com.demo.app.Main
```

In PowerShell or CMD, use **a single line** instead of the Unix shell line-continuation `\`:

```text
java --show-module-resolution --module-path mods -m com.demo.app/com.demo.app.Main
```

The launcher prints information about root module selection, modules resolved through dependencies, module locations, and related relationships, and then executes `main`. Read the messages with these questions:

- Was `com.demo.app` selected as a root module?
- On which module path was `com.demo.api` found?
- From which `requires` did the system modules originate?
- Did expected modules appear in the resolution output?

**Important:** observable modules (`--list-modules`) and resolved modules (`--show-module-resolution`) are two different sets. A module existing on the path is not guaranteed to be added to the runtime graph.

### 5.4. Validating consistency of observable modules

```sh
java --module-path mods --validate-modules
```

`--validate-modules` is useful for catching module path issues early, such as duplicate modules or conflicting packages before running the program. A successful validation does not mean all business paths or reflection usages are valid.

## 6. Runtime options that affect the graph or access permissions

The options below serve diagnostics, temporary compatibility, and library integration. In source code you own, prefer fixing descriptors or module structure to match the design.

| Option | Effect | Keep in mind |
|---|---|---|
| `--module-path <path>` | Specifies where to locate application modules | Must point to the exact built artifacts |
| `--add-modules <names>` | Adds root modules for the resolver to consider | Can bring in indirect dependencies |
| `--limit-modules <names>` | Restricts the set of observable modules | Can make a needed module unavailable |
| `--add-reads A=B` | Adds a readability edge from A to B | Does not automatically export packages in B |
| `--add-exports A/pkg=B` | Grants B access to package `pkg` of A | Serves normal type access |
| `--add-opens A/pkg=B` | Opens package `pkg` of A for deep reflection from B | Does not replace `requires` in standard design |
| `--patch-module A=<path>` | Supplements/overrides contents of module A at launch | Mainly used by tools or test environments |

Example adding a system module as a root and adding a temporary readability relationship:

```sh
java --module-path mods \
  --add-modules java.sql \
  --add-reads com.demo.app=java.sql \
  -m com.demo.app/com.demo.app.Main
```

In case an existing internal package in module `com.demo.api` needs to be accessed:

```sh
java --module-path mods \
  --add-exports com.demo.api/com.demo.internal=com.demo.app \
  -m com.demo.app/com.demo.app.Main
```

If a framework accesses private constructors or fields via reflection, the corresponding situation may require:

```sh
java --module-path mods \
  --add-opens com.demo.api/com.demo.internal=com.demo.app \
  -m com.demo.app/com.demo.app.Main
```

The last two examples are meaningful only when `com.demo.internal` actually exists in the artifact. If the target runs from the **classpath (unnamed module)**, you may see the target syntax `ALL-UNNAMED` instead of a named module.

Several usage principles:

- `--add-reads` only grants readability; access to packages still follows `exports`/`opens`.
- `--add-exports` opens package access for regular code; `--add-opens` is for deep reflection permission.
- `--add-modules` solves selecting root modules, not access permissions.
- `--limit-modules` is useful for testing the effect of a narrowed module set, yet easily excludes needed dependencies if used carelessly.
- Runtime flags are **overrides for that specific run**. They do not modify `module-info.class`, do not alter default compilation results, and may require separate configuration at compile time.

## 7. Static and dynamic cross-checking workflow

When migrating an application to JPMS or investigating startup errors, run through in order:

**Step 1 — Identify the actual artifacts running.** Check `mods`/`libs` directories, module path, and main module. A successful build does not prove the launcher is using the latest JAR.

**Step 2 — Inspect descriptors.**

```sh
java --module-path mods --describe-module com.demo.app
```

**Step 3 — Analyze dependencies from bytecode.**

```sh
jdeps --module-path mods --module com.demo.app --summary
jdeps --module-path mods --check com.demo.app
```

**Step 4 — Validate the module path.**

```sh
java --module-path mods --validate-modules
```

**Step 5 — Run and trace the resolver.**

```sh
java --show-module-resolution --module-path mods -m com.demo.app/com.demo.app.Main
```

**Step 6 — Classify the error from the actual message.** If the graph is valid yet the program fails when using reflection, services, or dynamic class loading, investigate that runtime mechanism; do not conclude `jdeps` covered all dependencies.

When comparing, distinguish three questions:

1. Which **bytecode references** did `jdeps` detect?
2. Which **modules to read** and **public packages** does `module-info.java` declare?
3. Which modules did the launcher actually **resolve** when run with the exact set of options and artifacts?

Discrepancies among these answers usually point straight to the root cause.

## 8. Common errors and how to handle them

### 8.1. `Module ... not found, required by ...`

**Symptom:** the launcher or compiler cannot find a module required by a descriptor.

**Check:** module name in `requires`, directories/JARs on `--module-path`, actual module name via `--describe-module`, differences between compile path and runtime path.

**Resolution:** supply the right modular JAR/exploded module, fix the name, or update the build. Avoid using `--add-reads` to treat a module-not-found error; resolution must be fixed first.

### 8.2. `package ... is not visible` or `does not export ...`

**Symptom:** the module reads the dependency, yet the referenced package is not exported to the caller.

**Check:** `exports` in the providing module; if using `exports ... to ...`, check the exact permitted module name.

**Resolution:** export a valid public API or adjust package organization. For legacy code, `--add-exports` is only a temporary measure appropriate once access relationships are understood.

### 8.3. `InaccessibleObjectException` during reflection

**Symptom:** code uses reflection on non-public members of an unopened package.

**Check:** the `does not "opens"` message, which package the framework accesses, and whether the calling module is named or `ALL-UNNAMED`.

**Resolution:** if the architecture requires reflection, add `opens pkg` or `opens pkg to module` in the descriptor of the module owning the package; use `--add-opens` as a runtime option when appropriate.

### 8.4. `ResolutionException` / duplicate modules / split packages

**Symptom:** conflicts when the resolver processes multiple modules defining duplicate names or containing packages that cannot coexist in resolution relationships.

**Check:** run `--validate-modules`; inspect the module path, transitive dependencies, and JARs packaging overlapping classes/packages.

**Resolution:** remove duplicate artifacts, unify library versions, or reorganize packages. Java modules are not a mechanism for allowing named modules to arbitrarily share a package.

### 8.5. `ClassNotFoundException` or `NoClassDefFoundError` even though `jdeps` looks reasonable

**Symptom:** the application starts yet fails on branches using reflection, plugins, SPI, or classes loaded only based on configuration.

**Check:** dynamic class names, actual class loader, whether the module was resolved, whether packages are exported/opened, and `uses`/`provides` declarations for ServiceLoader.

**Resolution:** add required modules to the graph through appropriate descriptor design or root modules, configure services properly, and test actual execution paths. Do not treat an empty `jdeps` report as proof of no runtime dependencies.

## 9. Limitations of jdeps to keep in mind

`jdeps` reads **class files and module descriptors**, so it is very strong for static references yet does not execute the application. Therefore:

- Dependencies created by `Class.forName(...)`, reflection, or class names read from configuration may not appear.
- Service relationships `uses`/`provides` and service binding must be checked in descriptors and how the application launches; do not infer everything from imports/bytecode.
- Automatic modules, the unnamed module on the classpath, and named modules follow different rules; check whether the application places JARs on the **classpath** or **module path**.
- One module reading another module may still be unable to access packages due to strong encapsulation rules.
- A static dependency graph does not replace testing the application with the exact JDK, module path, runtime arguments, and required business paths.

In particular, when `jdeps` and `--show-module-resolution` results differ, check the **root module set**, direct/transitive `requires`, modules brought in by `--add-modules`, as well as dependencies used only through dynamic mechanisms.

## 10. Practice exercises

**Exercise 1 — Identify dependency edges.** With the sample project, run `jdeps --summary` and `java --show-module-resolution`. Record: the root module, the edge from `com.demo.app` to `com.demo.api`, and `java.base`. Explain why `java.base` can appear even when the descriptor does not declare it explicitly.

**Exercise 2 — Distinguish resolution from accessibility.** Remove `exports com.demo.api;` from the API module and recompile. Observe the error in the application. Restore `exports` and explain why `requires com.demo.api;` alone is not enough to access `Message`.

**Exercise 3 — Check the module path.** Try running the application when `--module-path` omits `com.demo.api`. Read the error, then restore the path and run `--validate-modules` along with `--show-module-resolution` to confirm the graph.

**Exercise 4 — Expand the graph.** Add module `com.demo.facade` with `requires transitive com.demo.api;`. Have `com.demo.app` depend on `com.demo.facade` and evaluate readability to `com.demo.api`. Compare descriptors with `jdeps --check` output to recognize direct and transitive dependencies.

## 11. Practical takeaways

- **`jdeps`**: start with `--summary`; use `--list-deps` or `--print-module-deps` for module lists; use `--check` when suspecting complex descriptors/graphs; use `--jdk-internals` when upgrading the JDK.
- **`java` launcher**: `--list-modules` answers "what can be seen"; `--describe-module` answers "what does the descriptor say"; `--show-module-resolution` answers "what did the resolver pick"; `--validate-modules` helps catch module path conflicts.
- **Diagnose at the right layer**: find the module first, verify readability next, then check `exports`/`opens` and class loading mechanisms.
- **Keep the graph transparent**: fix `module-info.java` and dependency structure when you own the source code; use `--add-reads`, `--add-exports`, and `--add-opens` with clear targets when handling compatibility.

You can check syntax for your active JDK using `jdeps --help` and `java --help`; direct output from your actual JDK version and artifacts is the basis for diagnosis.