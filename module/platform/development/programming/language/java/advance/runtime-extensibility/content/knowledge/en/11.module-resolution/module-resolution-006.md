# Inspecting the Resulting Graph via `Configuration` and `ResolvedModule`

When using the Java Platform Module System (JPMS), writing `requires` in `module-info.java` only **declares a dependency**. Java still has to perform resolution across available modules into a **resolved module graph** before constructing a module layer to run the program. To understand why a module was selected, which module can read which other module, or why a dependency could not be found, you can inspect the graph through two standard JDK APIs:

- `java.lang.module.Configuration`: represents a **resolved module configuration** and its parent configurations.
- `java.lang.module.ResolvedModule`: represents **a specific module in the configuration**, including its module reference and *readability* relationships (ability to read other modules).

The most important point: **the `requires` graph declared in descriptors and the `reads()` graph after resolution are related but not necessarily identical**. This lesson builds a Java 17 example with a `requires transitive` relationship, prints the graph in a deterministic order, properly reads `Configuration.modules()`, `findModule()`, `ResolvedModule.reference()`, and `reads()`, and explains the difference between resolving a configuration and loading modules for execution.

## 1. Before Inspecting, Distinguish Three Objects

| Component | Role | Question It Answers |
|---|---|---|
| `ModuleDescriptor` | Static description of a named module: `requires`, `exports`, `opens`, `uses`, `provides`... | “What does the module *declare*?” |
| `Configuration` | Resolution result for a set of root modules, along with parent configuration relationships | “In this resolution pass, which modules were selected?” |
| `ResolvedModule` | A selected module, having a `ModuleReference`, `configuration()`, and `reads()` set | “Which modules can this module *actually read* in the graph?” |

Two more APIs are easy to confuse:

- `java.lang.Module` represents a module **at runtime** after the module is defined into a `ModuleLayer`; it provides `canRead(...)`, `getLayer()`, and other runtime operations.
- `java.lang.ModuleLayer` binds a `Configuration` to class definitions/class loaders and `Module` objects. **Simply calling `Configuration.resolve(...)` does not create a `ModuleLayer`, does not load classes to execute, and does not instantiate providers.**

Therefore `ResolvedModule` is not a runtime `Module` object; `ModuleDescriptor` is likewise not the full list of edges after resolution.

## 2. The Resolution Graph Creation Process

A resolution pass typically needs three things:

1. **Root modules:** the set of module names required, e.g. `demo.app`.
2. **Module lookup source (`ModuleFinder`):** module path/JARs/directories containing observable modules.
3. **Parent configuration:** e.g. `ModuleLayer.boot().configuration()` to reference existing JDK platform modules.

```text
Root: demo.app
       |
       v
ModuleFinder finds demo.app and related dependencies
       |
       v
Resolution checks requirements, readability, and JPMS constraints
       |
       v
Configuration (result graph)
       |
       +-- modules() -> ResolvedModules belonging to the new configuration itself
       |
       +-- parents() -> parent configurations, which may contain java.base
       |
       +-- findModule(name) -> search by name in this configuration or parents
```

Typical API code:

```java
ModuleFinder finder = ModuleFinder.of(Path.of("mods"));
Configuration parent = ModuleLayer.boot().configuration();

Configuration graph = parent.resolve(
        finder,
        ModuleFinder.of(),
        Set.of("demo.app"));
```

This snippet illustrates the API; the complete program below includes imports, source files, and run commands.

Meaning of parameters in `parent.resolve(before, after, roots)`:

- `before`: source checked for modules before modules in parent configurations.
- `after`: fallback lookup source after parent configurations have been checked.
- `roots`: set of modules starting the resolution process.
- `parent`: inherited parent configuration; modules in the parent can be used to satisfy dependencies.

The resolution API does not take a list of classes on the classpath and automatically turn them into named modules. Only `module-info.class` files or modular JARs visible to `ModuleFinder` serve as inputs to that resolution. Ordering and module observability can affect the outcome, so verify inputs before blaming `Configuration`.

## 3. Illustrative Problem: Three Modules and an Indirect Read Edge

We create three named modules:

```text
demo.app --requires--> demo.feature --requires transitive--> demo.contract
```

`demo.app` only declares `requires demo.feature`. `demo.feature` declares `requires transitive demo.contract`, so `demo.app` also gains readability to `demo.contract` per JPMS readability rules.

Source structure:

```text
module-graph-demo/
├── src/
│   ├── demo.contract/
│   │   ├── module-info.java
│   │   └── demo/contract/Greeter.java
│   ├── demo.feature/
│   │   ├── module-info.java
│   │   └── demo/feature/GreeterImpl.java
│   └── demo.app/
│       ├── module-info.java
│       └── demo/app/App.java
└── inspector/
    └── GraphInspector.java
```

After compilation, `mods/` contains the three compiled module directories, while `out/` contains the inspector class. The inspector runs on the classpath so it can build a new configuration from `mods/` without putting the three demo modules into the inspector process's own boot layer.

### 3.1. Contract Module: `demo.contract`

File `src/demo.contract/module-info.java`:

```java
module demo.contract {
    exports demo.contract;
}
```

File `src/demo.contract/demo/contract/Greeter.java`:

```java
package demo.contract;

public interface Greeter {
    String greet(String name);
}
```

This module exports package `demo.contract` so modules that read it can access `Greeter`.

### 3.2. Feature Module: `demo.feature`

File `src/demo.feature/module-info.java`:

```java
module demo.feature {
    requires transitive demo.contract;
    exports demo.feature;
}
```

File `src/demo.feature/demo/feature/GreeterImpl.java`:

```java
package demo.feature;

import demo.contract.Greeter;

public final class GreeterImpl implements Greeter {
    @Override
    public String greet(String name) {
        return "Hello " + name;
    }
}
```

`requires transitive demo.contract` has two related effects: `demo.feature` reads `demo.contract`; and modules that read `demo.feature` under the corresponding relationship implicitly read `demo.contract` as well. Do not confuse `requires transitive` with opening/exporting packages: for code outside the module to access type `Greeter`, `demo.contract` still needs `exports demo.contract`.

### 3.3. Root Module: `demo.app`

File `src/demo.app/module-info.java`:

```java
module demo.app {
    requires demo.feature;
}
```

File `src/demo.app/demo/app/App.java`:

```java
package demo.app;

import demo.contract.Greeter;
import demo.feature.GreeterImpl;

public final class App {
    public static void main(String[] args) {
        Greeter greeter = new GreeterImpl();
        System.out.println(greeter.greet("Java"));
    }
}
```

Worth noting: `App` imports `demo.contract.Greeter` even though `demo.app` **does not declare** `requires demo.contract`. This is valid because `demo.feature` has `requires transitive demo.contract`. The program prints `Hello Java`.

## 4. Creating a `Configuration` and Iterating Over `ResolvedModule`

The following `inspector/GraphInspector.java` file is a standalone Java 17 program with complete imports and `main`:

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.lang.module.ResolvedModule;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.Set;

public final class GraphInspector {
    public static void main(String[] args) {
        ModuleFinder finder = ModuleFinder.of(
                Path.of(args.length > 0 ? args[0] : "mods"));

        Configuration parent = ModuleLayer.boot().configuration();
        Configuration graph = parent.resolve(
                finder,
                ModuleFinder.of(),
                Set.of("demo.app"));

        System.out.println("Modules in new configuration:");
        graph.modules().stream()
                .map(ResolvedModule::name)
                .sorted()
                .forEach(name -> System.out.println("  " + name));

        graph.modules().stream()
                .sorted(Comparator.comparing(ResolvedModule::name))
                .forEach(module -> {
                    List<String> direct = module.reference()
                            .descriptor()
                            .requires()
                            .stream()
                            .map(require -> require.name())
                            .filter(name -> name.startsWith("demo."))
                            .sorted()
                            .toList();

                    List<String> reads = module.reads()
                            .stream()
                            .map(ResolvedModule::name)
                            .filter(name -> name.startsWith("demo."))
                            .sorted()
                            .toList();

                    System.out.println(module.name()
                            + " requires=" + direct
                            + " reads=" + reads);
                });

        System.out.println("find demo.feature: "
                + graph.findModule("demo.feature").isPresent());
        System.out.println("find demo.missing: "
                + graph.findModule("demo.missing").isPresent());
        System.out.println("same configuration: "
                + (graph.findModule("demo.app")
                        .orElseThrow().configuration() == graph));
        System.out.println("java.base in parent: "
                + parent.findModule("java.base").isPresent());
        System.out.println("java.base through graph.findModule: "
                + graph.findModule("java.base").isPresent());
        System.out.println("java.base in graph.modules: "
                + graph.modules().stream()
                        .anyMatch(m -> m.name().equals("java.base")));
    }
}
```

The program intentionally sorts lists using `.sorted()` and `Comparator.comparing(...)`; the `Set<ResolvedModule>` returned by `modules()` or `reads()` **is not a display-order contract**. Printing sets directly can produce different ordering across environments.

To keep example output stable, we filter names starting with `demo.` when comparing `requires`/`reads`. Real modules may also read `java.base` or other modules per JPMS rules; filtering is purely for observing the demo portion of the graph.

## 5. Compiling and Running on Java 17 or Later

The example uses `javac --release 17` so classes are compiled targeting Java 17. Stand in the `module-graph-demo` directory containing `src` and `inspector` as shown above.

### Linux/macOS (Bash)

Create output directories:

```bash
mkdir -p mods out
```

Compile the three named modules. Each module must have a directory name matching its module name under `--module-source-path src`:

```bash
javac --release 17 -d mods --module-source-path src src/demo.contract/module-info.java src/demo.contract/demo/contract/Greeter.java src/demo.feature/module-info.java src/demo.feature/demo/feature/GreeterImpl.java src/demo.app/module-info.java src/demo.app/demo/app/App.java
```

Compile the inspector into a separate classpath output directory:

```bash
javac --release 17 -d out inspector/GraphInspector.java
```

Run the named-module application, then run the inspector:

```bash
java --module-path mods -m demo.app/demo.app.App
java -cp out GraphInspector mods
```

### Windows PowerShell

The relative paths using `/` below are accepted by the Java CLI and PowerShell in filename positions in this example. Run:

```powershell
New-Item -ItemType Directory -Force mods,out | Out-Null

javac --release 17 -d mods --module-source-path src src/demo.contract/module-info.java src/demo.contract/demo/contract/Greeter.java src/demo.feature/module-info.java src/demo.feature/demo/feature/GreeterImpl.java src/demo.app/module-info.java src/demo.app/demo/app/App.java

javac --release 17 -d out inspector/GraphInspector.java

java --module-path mods -m demo.app/demo.app.App
java -cp out GraphInspector mods
```

There is no need to join multiple JARs with `:` or `;` because `mods` is **one** module output path and `out` is **one** classpath entry. If multiple entries are later used in `--module-path`, Linux/macOS uses `:` while Windows uses `;`.

### Exact Output

Running `demo.app` prints to stdout:

```text
Hello Java
```

Running `GraphInspector` prints to stdout:

```text
Modules in new configuration:
  demo.app
  demo.contract
  demo.feature
demo.app requires=[demo.feature] reads=[demo.contract, demo.feature]
demo.contract requires=[] reads=[]
demo.feature requires=[demo.contract] reads=[demo.contract]
find demo.feature: true
find demo.missing: false
same configuration: true
java.base in parent: true
java.base through graph.findModule: true
java.base in graph.modules: false
```

The outputs above are the output for **the exact source files and commands presented**, not a universal output for every JPMS graph. The inspector runs on the classpath, and when it creates a child configuration with `demo.app` as root, all three demo modules are resolved together into that configuration.

## 6. Reading Each Result: What Actually Proves What?

### 6.1. `Configuration.modules()` Gives the Set of Modules Belonging to the New Configuration

```java
Set<ResolvedModule> selected = graph.modules();
```

In the example, `selected` contains three names: `demo.app`, `demo.feature`, `demo.contract`.

**Do not interpret** `graph.modules()` as “every module `graph` can look up”, because modules residing in parent configurations **do not belong to this set**. `java.base` belongs to the boot configuration in the parent; therefore:

```text
java.base through graph.findModule: true
java.base in graph.modules: false
```

This is not a contradiction. `Configuration.findModule(name)` searches both the current configuration and parent configurations. When you need to list **only the newly resolved modules**, use `modules()`; when you need to look up a module name that may come from a parent, use `findModule()`.

### 6.2. `ResolvedModule.name()` Is the Selected Module Name

```java
String name = module.name();
```

`name()` is suitable for logging, membership checks, and comparing against descriptor names. Do not treat the display name by itself as a globally unique identifier across all configurations/layers: a module name can appear in different loading contexts; when you need to understand a `ResolvedModule`, retain its owning configuration as well.

### 6.3. `ResolvedModule.reference()` Leads to the Module's Descriptor

```java
var descriptor = module.reference().descriptor();
var declaredRequires = descriptor.requires();
```

`module.reference()` returns a `ModuleReference`, containing the `ModuleDescriptor` and optionally providing `location()` as `Optional<URI>`. Do not assume `location()` always has a file/JAR URI: a module may come from a system module finder or another mechanism.

`descriptor.requires()` holds the declarations **directly in the descriptor**, along with modifiers. In the program, we extracted only `.name()` for comparison. To distinguish `requires transitive`, you can inspect:

```java
boolean transitive = module.reference()
        .descriptor()
        .requires()
        .stream()
        .anyMatch(r -> r.name().equals("demo.contract")
                && r.modifiers().contains(
                        java.lang.module.ModuleDescriptor.Requires.Modifier.TRANSITIVE));
```

This check is an **illustrative expression in a context where variable `module` exists**, not a standalone program. The value `true` applies when `module` is `demo.feature`; for `demo.app` it is `false` because `demo.app` does not directly declare `demo.contract`.

Default requirements on `java.base` are normally added to the descriptor per JPMS rules. The `demo.` filter in the inspector excludes them from the output so they do not clutter the example.

### 6.4. `ResolvedModule.reads()` Represents Readability Edges

```java
Set<ResolvedModule> readable = module.reads();
```

`reads()` returns the set of modules this module can read according to the resolution graph. The readability graph can include relationships **derived from `requires transitive`**, not solely the `requires` entries written directly in the descriptor.

In stdout:

```text
demo.app requires=[demo.feature] reads=[demo.contract, demo.feature]
```

This is the key learning point: `demo.app` **did not directly declare** `demo.contract`, yet it can read it because `demo.feature` requires `demo.contract` with `transitive`.

In the example, `demo.feature` directly reads `demo.contract`. `demo.contract` declares no demo dependencies, so its readability set after filtering for `demo.` names is empty. That does not mean it does not read `java.base`; we intentionally filtered out modules not starting with `demo.`.

### 6.5. `ResolvedModule.configuration()` Points to the Owning Configuration

```java
Configuration owner = module.configuration();
```

If you fetch `demo.app` via `graph.findModule("demo.app")`, the expression `module.configuration() == graph` is `true` in this program because `demo.app` resides in the new configuration itself.

However, for a module returned from a parent configuration via `findModule`, `module.configuration()` will be the parent configuration that owns it, **not** `graph`. Thus, when inspecting hierarchical graphs, distinguish **looked up via the current configuration** from **owned by the current configuration**.

## 7. Comparing the `requires` Graph and the `reads` Graph

Side by side for clarity:

```text
DECLARED (ModuleDescriptor.requires)
  demo.app      -> demo.feature
  demo.feature  -> demo.contract  [TRANSITIVE]
  demo.contract -> (no demo.* requires)

READABLE (ResolvedModule.reads, filtered to demo.*)
  demo.app      -> demo.feature
  demo.app      -> demo.contract  [inferred via transitive]
  demo.feature  -> demo.contract
  demo.contract -> (no demo.* reads)
```

The table below explains which API to pick for each question:

| Want to Know | Right API | Note |
|---|---|---|
| Which modules were added to the new configuration? | `configuration.modules()` | Excludes modules belonging only to parents |
| Can module `X` be found through the configuration and parents? | `configuration.findModule("X")` | May return a module from a parent |
| Which `requires` does module A declare? | `resolved.reference().descriptor().requires()` | Includes modifiers `TRANSITIVE`, `STATIC`, `MANDATED`... |
| Which modules can module A actually read after resolution? | `resolved.reads()` | May include indirect edges |
| Which configuration does module B belong to? | `resolved.configuration()` | Useful with multiple parents/layers |
| Where are the selected module's descriptor/resources? | `resolved.reference()` | `location()` is `Optional` |
| Does runtime module A currently read B? | `java.lang.Module.canRead(...)` | Only for runtime modules after they are defined |

Do not use `descriptor.requires()` to deduce full **readability**, and do not use `reads()` to assume a relationship is a direct `requires`. If drawing a full diagram, annotate **declared edges** and **effective read edges** as two distinct kinds.

## 8. When Is `Configuration.resolve(...)` Not Enough?

`Configuration` is a resolved metadata graph, not a launched application. The inspector example **does not** define class loaders/module layers for the three demo modules.

To execute classes in new modules, you need a step that defines them into a `ModuleLayer` with an appropriate class-loader strategy, or simply launch a modular program with `java --module-path ... -m ...` as shown. The two commands:

```text
java --module-path mods -m demo.app/demo.app.App
java -cp out GraphInspector mods
```

are **two executions with different purposes**. The first creates a module environment to run `demo.app`; the second builds a configuration for inspection from an inspector process on the classpath. Both graphs may reflect equivalent dependencies, but they are not the same `Configuration` object in the same JVM.

Also distinguish:

- `resolve(...)`: resolves the root set and required module dependencies per JPMS rules.
- `resolveAndBind(...)`: in addition to resolving, can bring in provider modules when performing **service binding** based on `uses` and `provides` declarations.

If a module has `uses SomeService` and a provider is only discovered through service binding, `modules()` can differ between the two methods. Do not infer “having `provides` on the module path puts the provider into the graph automatically” for plain `resolve`. Once you have the graph, the application still needs a `ModuleLayer` and an appropriate service consumption mechanism to actually invoke the provider.

## 9. Inspecting the Graph in a System with Parent Configurations

A configuration is not necessarily a flat set of modules. `Configuration.parents()` returns parent configurations; the static API also has resolution variants accepting a list of parents to support complex module layers. In a plugin application, a plugin can be resolved into a child configuration of the boot configuration or of a configuration already containing the shared API.

Model:

```text
          Boot configuration
          (java.base, ...)
                  |
                  v
          Child configuration
       (demo.app, demo.feature,
         demo.contract)
```

Inspection rules:

1. Use `graph.modules()` to see exactly the modules **belonging to the new graph**.
2. Use `graph.parents()` to inspect prior configurations the graph may rely on.
3. Use `graph.findModule(name)` to look up a module by name across configuration relationships.
4. Once you have a `ResolvedModule`, use `configuration()` to tell whether it belongs to a parent or the child.
5. Use each module's `reads()` if you need to verify readability paths. Do not use `findModule` alone to deduce that any given module can read the found module.

`findModule("java.base").isPresent()` answers “is that module somewhere in this configuration or its parents?”. It does **not** mean every module in the graph has access to every package of `java.base` or any parent module; readability, `exports`, and `opens` remain separate relationships/constraints.

## 10. Limits When Reading the Resolution Graph

**Readability differs from package accessibility.** Module A may read B, yet A can only publicly access packages that B **exports** to A. `opens` governs reflective access under corresponding rules; `reads()` is not the list of importable packages.

**A configuration can be created without running any code.** `ResolvedModule` does not tell you whether classes have been loaded, static initializers have run, or service providers have been instantiated. Those questions belong to the runtime stage.

**Descriptors are metadata at resolution time.** Readability changes via runtime APIs such as `Module.addReads(...)` (within appropriate permissions and conditions) can make runtime `Module.canRead(...)` differ from the data inspected on the initial configuration.

**`reads()` is a set of edges, not a pathfinding explanation.** If you want to trace why A reads C through intermediate modules, you must combine descriptors (`requires`/modifiers) and graph analysis. An edge appearing in `reads()` does not record “the origin of the edge”.

**Module versions do not replace dependency management.** `ModuleDescriptor` can carry version metadata, but JPMS resolution is not a semantic dependency version solver like Maven/Gradle. The module path must be assembled with compatible artifacts; having matching module names alone is not enough to conclude API compatibility.

**Not everything on the classpath enters the JPMS graph.** Code in the unnamed module and pure classpath dependencies do not automatically appear in `Configuration.modules()` as resolved named modules. Automatic modules on the module path have their own rules; distinguish them from plain classpath JARs.

## 11. Diagnosing Anomalous Results

| Symptom | Common Possibility | How to Check |
|---|---|---|
| `findModule("demo.app")` is empty | `demo.app` was not passed as a root or is absent from relevant configurations | Print roots, check `ModuleFinder` and module names |
| Resolution fails with missing module | A required dependency is not observable from finders/parents | Check `requires`, module-path paths, and actually present modules |
| Module is in finder but missing from `modules()` | It may not be in the roots' dependency closure, or was satisfied from a parent | Check roots, parents, and `findModule` |
| `findModule("java.base")` is present but `modules()` omits it | `java.base` belongs to the parent configuration | Read `parents()` and `ResolvedModule.configuration()` |
| `reads()` has more names than `requires()` | Inferred read edges, e.g. `requires transitive` | Inspect modifiers in `ModuleDescriptor.Requires` |
| Can read module B but cannot import a package in B | Package is not properly `exports`ed or API is not public | Check `ModuleDescriptor.exports()` and type visibility |
| Results differ between `resolve` and `resolveAndBind` | Service binding may have added provider modules | Check `uses`/`provides` and relevant finders |
| Printing `Set` gives changing order | Sets do not define presentation order | Sort by `ResolvedModule.name()` before printing |
| Configuration resolves but app fails linkage at runtime | A valid module graph does not guarantee binary API compatibility or correct class loading | Check artifact versions, method signatures, and runtime logs |
| `ResolvedModule` found but no runtime `Module` exists | Only resolution ran, no layer created yet | Define a layer or run a modular application to get a runtime `Module` |

If you want to observe resolution when the JVM itself launches the application, you can use:

```bash
java --show-module-resolution --module-path mods -m demo.app/demo.app.App
```

Depending on the JDK, module path, and environment configuration, this command may print additional system modules and resolution info; do not treat that debug text as a stable format for downstream tools to depend on. For automated tests requiring consistent output, traversing `Configuration` and sorting lists like `GraphInspector` is usually far more reliable.

When `resolve` throws an exception, read **the first cause and the module name in the message**. Issues like missing modules, finders seeing duplicate modules, or invalid module descriptors must be fixed at the module lookup source/descriptor; you cannot solve them by `catch`ing and pretending the graph has all modules.

## 12. A Practical Investigation Workflow

When a module in a large application cannot find or read another module, follow this sequence:

1. **Identify the real roots:** which `-m` did the app launch with, or which `roots` did the framework pass to resolution? Do not treat every present JAR as a root without reason.
2. **Record module finders and parents:** separate application modules discovered from the module path from modules already in the boot/parent configuration.
3. **Resolve and fail fast:** if an error occurs, fix the root cause in `requires`, module path, or descriptors.
4. **Check membership:** use `modules()` and `findModule(name)`. Clearly note whether each module belongs to the current configuration or a parent.
5. **Cross-check declarations and readability:** from `ResolvedModule.reference().descriptor().requires()`, check direct edges and modifiers; from `ResolvedModule.reads()`, check the effective result.
6. **Check package accessibility:** readability does not replace `exports`/`opens`; read the target module's descriptor on compile or reflection errors.
7. **If running plugins:** once the graph is valid, inspect `ModuleLayer` creation, class loaders, and service loading. Do not stop at “graph resolved” and conclude all providers are running.
8. **Automate:** sort module names, assert required node/edge sets, and fail tests if an important dependency or an unexpected `reads` edge appears or disappears.

## 13. Reinforcement Exercises

1. **Remove `transitive`:** change `demo.feature` to `requires demo.contract;`. Predict what happens when compiling `demo.app` while it still imports `demo.contract.Greeter`. Then remove the `Greeter` import from `App` or add `requires demo.contract` directly and explain the graph change.
2. **Change roots:** pass `demo.feature` as root instead of `demo.app`. Compare the new `modules()` set, `reads()` edges, and whether `demo.app` is still resolved.
3. **Look up in parent:** call `graph.findModule("java.base")`, print `configuration()` of the returned module, and compare against `graph.modules()`. Why is `java.base` not a newly selected module?
4. **Inspect modifiers:** add a loop printing `ModuleDescriptor.Requires.Modifier` for each dependency. Make sure you distinguish `TRANSITIVE` on `demo.feature` from regular `requires` on `demo.app`.
5. **Test a broken module path:** remove the `demo.contract` module directory from the finder (in a test copy), then observe whether resolution fails or is satisfied from a parent. Diagnose the error instead of ignoring it.
6. **Distinguish resolution and runtime:** explain why `Configuration.resolve(...)` gives you a `ResolvedModule` but does not yet provide that module's runtime `java.lang.Module` object. Add a `ModuleLayer` check if your deployment scenario needs it.

**Remember:** `ModuleDescriptor` is the declaration, `Configuration` is the set of modules resolved for a scope and parents, and `ResolvedModule.reads()` reports the effective read edges in that graph. Using all three views gives you a complete basis for analyzing JPMS dependencies, especially when `requires transitive` or parent configurations make the resulting graph differ from the `requires` list seen in individual `module-info.java` files.