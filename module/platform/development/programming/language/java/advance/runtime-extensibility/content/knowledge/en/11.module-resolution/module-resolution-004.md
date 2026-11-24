# Search Scope of ModuleFinder Before and After Parent Configurations in Java JPMS

## 1. The Problem and Terms to Distinguish

When a Java runtime creates a new module layer to load extensions, it must determine **which module will be selected for each module name** and whether that module resides in the new configuration or was already resolved in a parent configuration. In the Java Platform Module System (JPMS), that job belongs to `java.lang.module.Configuration.resolve(...)`. Two `ModuleFinder` parameters named `before` and `after` determine the lookup order relative to **the parent configurations**.

Three key concepts:

- **`ModuleFinder`:** a lookup source for `ModuleReference` by *module name*, such as modules in JARs, exploded modules, or the runtime image. It describes which modules can be found; it does not yet create a module layer or load classes.
- **`Configuration`:** the resolution result for root modules and their required dependencies, containing the readability graph and relationships to parent configurations. Each `ResolvedModule` points to the selected `ModuleReference`.
- **`ModuleLayer`:** the step that materializes a configuration in the JVM with runtime `Module` objects and class loaders. Successful resolution does not mean plugin classes have been loaded or the plugin has executed.

Example: the host has `demo.lib@1.0` in a parent configuration, the plugin wants `demo.lib@2.0`, and a fallback repository provides `demo.lib@3.0`. Which finder exposes the module with the same name and where it sits will determine the result; JPMS **does not automatically pick the highest version**.

The goal here is to understand the exact **scope and lookup order of `before` / `after` relative to parent configurations**, for both roots and dependencies, and then know how to inspect the result and avoid confusing it with class-loading order.

## 2. API Contract: Overloads to Read Carefully

Java 17 provides two ways to solve the same problem (instance and static):

```java
// Instance: the configuration receiving the call is the sole parent.
Configuration child = parent.resolve(before, after, roots);

// Static: the list of parent configurations is specified with explicit order.
Configuration child = Configuration.resolve(
        before, List.of(parentA, parentB), after, roots);
```

These are **illustrative signature/call snippets**, assuming variables are already initialized; a standalone runnable Java 17 program is in section 6.

- `before`: finder authorized to be queried **before** parent configurations.
- `parents`: one or more parent `Configuration`s searched **in list order**. For the instance method, the list is equivalent to `List.of(parent)`.
- `after`: fallback finder, used only when a module name is absent from `before` **and** not found in the parent configurations.
- `roots`: set/collection of module names starting the resolution process. Root modules also follow the exact same order above; names in `roots` do not have to belong to `before`.

Two corresponding methods with service binding:

```java
Configuration child = parent.resolveAndBind(before, after, roots);

Configuration child = Configuration.resolveAndBind(
        before, List.of(parentA, parentB), after, roots);
```

`resolveAndBind` still applies the lookup and consistency checks of resolution, but also includes provider discovery for service dependencies; do not assume the selected module set will match plain `resolve`.

## 3. Exact Lookup Order for Each Module Name

Per the Java 17 `Configuration.resolve(before, parents, after, roots)` contract, when locating module name `M`:

```text
Find M
  |
  v
before.find("M") ?
  | yes --> select ModuleReference from before
  |
  no
  v
parents[0].findModule("M") ?    // including ancestors of this parent
  | yes --> reuse ResolvedModule already in parent
  |
  no
  v
parents[1].findModule("M") ?    // if multiple parents exist
  | yes --> reuse ResolvedModule already in parent
  |
  no
  v
... remaining parents ...
  |
  v
after.find("M") ?
  | yes --> select ModuleReference from after
  |
  no --> module not observable, resolution fails
```

**Priority order: `before → parents in search order → after`.** For a given parent, calling `parent.findModule("M")` searches that configuration first, then searches ancestors in the order exposed by `parents()`. With multiple parents, the Javadoc describes calling `findModule` on each parent in the list in turn; traversal within each configuration tree corresponds to depth-first search.

This rule applies to:

1. **Root modules**, e.g. `demo.app` in `roots`.
2. **Direct dependencies**, e.g. `demo.app requires demo.lib;`.
3. **Transitive dependencies needing resolution**, including additional read edges computed in the graph later.

If a name is found in a **parent configuration**, that module **is not re-resolved** and **does not appear in `child.modules()`**. This is the crucial distinction between “found in the configuration tree” and “newly added to the child configuration”.

The “before/after” markers in the parameter names refer to **per-name lookup precedence**, not execution phases of the whole pipeline: there is no rule like “load everything from before, run all parents, then load after”. Dependency traversal during resolution may happen in a different order, but source selection for each name follows the contract above.

## 4. Practical Scope of Each Source

| Source | Data Looked Up | When Selected | Consequence |
|---|---|---|---|
| `before` | Module names observable by this finder | Has module with requested name | Takes precedence over a same-named module in parents and modules in after |
| First parent configuration | `ResolvedModule`s in that parent and its ancestors | Absent from before | Reuses already-resolved module; not re-added to child |
| Subsequent parent configurations | Same, in `parents` list order | Absent from before and earlier parents | Earlier parent in list wins; not merged arbitrarily |
| `after` | Modules known to fallback finder | Absent from before and all parents | Newly resolved into child if needed |
| Found in no source | Name cannot be found | Resolution requires that name | `FindException`; no fallback module inferred from classpath |

### When the Same Name Appears in Multiple Places

Suppose all three places contain `demo.lib`:

```text
before : demo.lib@2.0
parent : demo.lib@1.0
after  : demo.lib@3.0

When demo.lib is needed --> select before: demo.lib@2.0
```

When `demo.lib` is removed from before, parent beats after. Only when `demo.lib` is absent from both before and parent is after selected. The `@1.0` notation is just for observation in this example; ***there is no automatic highest-version selection algorithm*** in `Configuration.resolve`.

A child configuration can pick a new module named `demo.lib` from before even when a parent configuration already contains a module with the same name; the version in the parent is not “replaced” or modified. Do not interpret the result as a runtime-wide upgrade. Modules in the parent still belong to the parent, and the module graphs of other components remain intact. Consistency checks can cause some dependency combinations to fail with `ResolutionException`; name shadowing is not a guarantee that every graph will be valid.

### “After” Does Not Mean Searching Arbitrary Modules on Disk

`after` is an **independent finder**, not a command to scan every remaining directory automatically. If the runtime passes `ModuleFinder.of()`, then after is empty; if it passes `ModuleFinder.of(path)`, it searches only those paths; if it passes `ModuleFinder.ofSystem()`, it searches system modules from the runtime image. A module sitting in another JAR outside the finders does not magically become “observable”.

## 5. Ways to Create ModuleFinder and Internal Finder Rules

Common patterns:

```java
ModuleFinder none = ModuleFinder.of();                 // no entries
ModuleFinder plugins = ModuleFinder.of(pluginDir);    // directory containing JARs/modules
ModuleFinder oneJar = ModuleFinder.of(pluginJar);     // a single modular/automatic JAR
ModuleFinder system = ModuleFinder.ofSystem();        // modules from runtime image
ModuleFinder combined = ModuleFinder.compose(plugins, system);
```

This is an illustrative snippet: `pluginDir` and `pluginJar` are existing `Path` variables.

- `ModuleFinder.of(Path...)` searches in **the order the paths are passed**. When multiple distinct paths contain the same module name, the finder picks the first occurrence rather than comparing versions to find the newest. If **within a single directory of modules** there are multiple modules with the same name, that is a `FindException`.
- `ModuleFinder.compose(first, second, ...)` preserves precedence in component finder order: a name seen in an earlier finder shadows that name in a later finder. This is an ordering **inside a composed finder**, distinct from the three-tier `before/parents/after` precedence of `Configuration.resolve`.
- `find(String name)` returns `Optional<ModuleReference>`; `findAll()` returns the set of all module references the finder sees. A finder must present a consistent view of the modules it exposes.
- A `ModuleFinder` is not required to be thread-safe. An instance backed by file paths may scan/fail when `find` or `findAll` is called; do not assume `of(...)` has already validated every JAR.
- A JAR with `module-info.class` describes an explicit named module. A JAR without a descriptor may be recognized as an automatic module based on manifest/filename; automatic modules have broader resolution and readability rules, so placing them on a finder can enlarge the resulting graph.

**Do not confuse the two-level ordering:**

```text
ModuleFinder.compose(A, B) in BEFORE:
    A is queried before B for duplicate names
Then Configuration.resolve:
    Composed BEFORE -> PARENTS -> AFTER
```

Modules currently in `ModuleLayer.boot().configuration()` are **modules already resolved in the parent**, not automatically the set of all modules `ModuleFinder.ofSystem()` can find. The system finder can find modules in the runtime image that were not part of the boot graph on a given invocation. Distinguish “available in system image” from “already resolved in parent configuration”.

## 6. Runnable Java 17 Program: Observing before, parent, and after

This example creates two named modules containing only `module-info.class`: `demo.app` requires `demo.lib`. We package the same `demo.lib` descriptor into three modular JARs with versions `1.0`, `2.0`, and `3.0` so it is easy to see which source was chosen. There are no plugin classes or service bindings in this example because the goal is **resolution/ModuleFinder**, not class loading.

### 6.1. Source Structure

Create a working directory `module-order-demo/`:

```text
module-order-demo/
  src/
    lib/module-info.java
    app/module-info.java
    host/ModuleOrderDemo.java
  build/                         (created by the commands below)
    classes/lib/
    classes/app/
    parent/
    before/
    after/
    app/
    host/
```

**File `src/lib/module-info.java`:**

```java
module demo.lib {
}
```

**File `src/app/module-info.java`:**

```java
module demo.app {
    requires demo.lib;
}
```

**File `src/host/ModuleOrderDemo.java`:**

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public final class ModuleOrderDemo {
    private static String describe(Configuration child) {
        var found = child.findModule("demo.lib").orElseThrow();
        String version = found.reference().descriptor().version()
                .orElseThrow().toString();
        boolean local = child.modules().contains(found);
        return "version=" + version + ",local=" + local;
    }

    public static void main(String[] args) {
        Configuration boot = ModuleLayer.boot().configuration();
        ModuleFinder empty = ModuleFinder.of();

        Path parentJar = Path.of("build/parent/demo.lib.jar");
        Path beforeJar = Path.of("build/before/demo.lib.jar");
        Path afterJar = Path.of("build/after/demo.lib.jar");
        Path appJar = Path.of("build/app/demo.app.jar");

        // Create a separate parent configuration: demo.lib@1.0 is already resolved.
        Configuration parent = boot.resolve(
                ModuleFinder.of(parentJar), empty, Set.of("demo.lib"));

        // Before provides demo.lib@2.0 even though parent has 1.0.
        Configuration beforeWins = parent.resolve(
                ModuleFinder.of(appJar, beforeJar),
                ModuleFinder.of(afterJar), Set.of("demo.app"));

        // Before only has demo.app; parent provides demo.lib@1.0.
        Configuration parentWins = parent.resolve(
                ModuleFinder.of(appJar),
                ModuleFinder.of(afterJar), Set.of("demo.app"));

        // Boot does not have demo.lib; before does not have demo.lib:
        // after is used to find demo.lib@3.0.
        Configuration afterFallback = boot.resolve(
                ModuleFinder.of(appJar),
                ModuleFinder.of(afterJar), Set.of("demo.app"));

        System.out.println("beforeWins: " + describe(beforeWins));
        System.out.println("parentWins: " + describe(parentWins));
        System.out.println("afterFallback: " + describe(afterFallback));
    }
}
```

**Explanation of the example design:**

- `ModuleLayer.boot().configuration()` is the boot layer's configuration, which already has `java.base`. As a result, the default `requires java.base` of new modules can be satisfied from the parent.
- Calling `boot.resolve(ModuleFinder.of(parentJar), empty, Set.of("demo.lib"))` creates a `parent` configuration containing `demo.lib@1.0`. This is a **configuration**; no new runtime `ModuleLayer` has been created yet.
- In `beforeWins`, the before finder knows both root `demo.app` and `demo.lib@2.0`; that version beats parent 1.0 and after 3.0.
- In `parentWins`, before knows only `demo.app`; when `demo.lib` is needed, it is reused from `parent`, so `demo.lib` is not a local module of the child.
- In `afterFallback`, the parent is `boot`, which does not contain `demo.lib`, so after supplies version 3.0.
- `child.findModule("demo.lib")` can find it in the child or parent; `child.modules().contains(found)` checks whether it actually belongs to the child itself.

### 6.2. Windows PowerShell Commands

From the `module-order-demo/` directory with JDK 17 or newer on `PATH`:

```powershell
New-Item -ItemType Directory -Force -Path build/classes/lib,build/classes/app,build/parent,build/before,build/after,build/app,build/host | Out-Null

javac --release 17 -d build/classes/lib src/lib/module-info.java
jar --create --file build/parent/demo.lib.jar --module-version 1.0 -C build/classes/lib .
jar --create --file build/before/demo.lib.jar --module-version 2.0 -C build/classes/lib .
jar --create --file build/after/demo.lib.jar --module-version 3.0 -C build/classes/lib .

javac --release 17 --module-path build/parent/demo.lib.jar -d build/classes/app src/app/module-info.java
jar --create --file build/app/demo.app.jar -C build/classes/app .

javac --release 17 -d build/host src/host/ModuleOrderDemo.java
java -cp build/host ModuleOrderDemo
```

`jar --module-version` records a version in each JAR's module descriptor; **it does not make JPMS perform semantic-version resolution**. We use this version solely to print which source won. `demo.app` was compiled with a path to `demo.lib@1.0`, yet `requires demo.lib` in the descriptor binds **by module name**; it does not lock version 1.0 during runtime resolution.

### 6.3. Equivalent Commands for Linux/macOS

```bash
mkdir -p build/classes/lib build/classes/app build/parent build/before build/after build/app build/host

javac --release 17 -d build/classes/lib src/lib/module-info.java
jar --create --file build/parent/demo.lib.jar --module-version 1.0 -C build/classes/lib .
jar --create --file build/before/demo.lib.jar --module-version 2.0 -C build/classes/lib .
jar --create --file build/after/demo.lib.jar --module-version 3.0 -C build/classes/lib .

javac --release 17 --module-path build/parent/demo.lib.jar -d build/classes/app src/app/module-info.java
jar --create --file build/app/demo.app.jar -C build/classes/app .

javac --release 17 -d build/host src/host/ModuleOrderDemo.java
java -cp build/host ModuleOrderDemo
```

The host program runs on the classpath and uses the `java.lang.module` API to **inspect configurations**, so `demo.app` does not need to be placed on the runtime module path. `Path.of("build/...")` uses relative paths; you must run from `module-order-demo/`.

### 6.4. Exact Stdout

```text
beforeWins: version=2.0,local=true
parentWins: version=1.0,local=false
afterFallback: version=3.0,local=true
```

This output was verified by compiling the code with `javac --release 17` and running the modular JARs created by `jar`.

- Line 1: `before` selects 2.0 despite 1.0 in parent and 3.0 in after; `local=true` because the module was resolved in the child.
- Line 2: Parent already contains 1.0, so after 3.0 **does not replace it**; `local=false` because `demo.lib` belongs to the parent config.
- Line 3: `demo.lib` is not found in before/boot, so fallback 3.0 enters the child.
- The three configurations are **three separate resolution results** in the program; they do not overwrite one another, and the example creates no runtime layers.

## 7. Roots and Dependencies Go Through the Same Lookup Chain

Many people assume roots must always sit in before while after is only for dependencies. The JDK rules clearly state **roots and transitive dependencies use the same lookup order**.

| Scenario Looking Up Name `M` | `before` | Parent | `after` | Result |
|---|---|---|---|---|
| Root M in before | M | M | M | M from before |
| Root M absent in before, in parent | no | M | M | M from parent; not added to child |
| Root M only in after | no | no | M | M from after |
| Dependency M of a root in both before and parent | M | M | any | Dependency from before |
| Dependency M only in parent/after | no | M | M | Dependency from parent |
| Dependency M nowhere | no | no | no | `FindException` |

When computing dependencies, the resolver reads descriptors (such as `requires demo.lib;`), then selects `demo.lib` according to the table. If the earlier and later versions have different descriptors (different dependencies or exported packages), **the resulting graph also differs**. Thus, when designing a plugin host, finder ordering affects both compatibility and whether resolution succeeds.

**Key point:** If a root is found in a parent, it was already resolved there and its dependencies are not re-traversed as a new root in the child. To get a module with the same name freshly resolved, you must provide it in the before finder and ensure a valid graph. Using after cannot force a module already present in a parent to be re-selected.

## 8. Distinguishing Configuration.modules, findModule, parents, and ModuleFinder.find

The following calls answer four different questions:

```java
child.modules();                  // only modules resolved in child
child.findModule("demo.lib");      // child, then parent configurations
child.parents();                  // list of direct parent configs
before.find("demo.lib");          // module *observable* via before finder
```

This is an illustrative snippet using the example variables; `before` here denotes a `ModuleFinder`, not a variable declared across the whole section 6 program.

- `ModuleFinder.find(name)` returns a `ModuleReference`, allowing you to read its descriptor and location, but the module is not necessarily selected into a `Configuration`.
- `Configuration.modules()` returns the set of `ResolvedModule`s **of that configuration itself**; it excludes modules residing in parents.
- `Configuration.findModule(name)` searches the current configuration, then parents in lookup order. Hence this method can find modules that the child's `modules()` does not contain.
- `ResolvedModule.reference().descriptor().version()` is metadata for observation; it does not prove which module is executing.
- `Configuration.parents()` records the parent ordering. With the static method taking multiple parents, this order affects lookup; a parent tree can itself have parents. Java describes the search order as akin to **depth-first search** over parent configurations.

Example if you want accurate logging during debugging:

```java
var resolved = child.findModule("demo.lib").orElseThrow();
System.out.println(resolved.name());
System.out.println(resolved.reference().location().orElse(null));
System.out.println(resolved.reference().descriptor().version().orElse(null));
System.out.println(child.modules().contains(resolved));
```

This is an illustrative snippet in a context where `child` already exists. `location()` can be empty and is not necessarily a physical file path; do not write production code that relies on `location`'s `toString()` as a guaranteed module identity.

## 9. How Does Lookup Work With Multiple Parent Configurations?

The static overload allows:

```java
Configuration combined = Configuration.resolve(
        before,
        List.of(parentA, parentB),
        after,
        Set.of("demo.app"));
```

Lookup sequence for a name `M`:

1. Query `before`.
2. If not found, query `parentA.findModule(M)`: this itself checks `parentA` and then A's ancestors.
3. If still not found, query `parentB.findModule(M)`: including `parentB` and B's ancestors.
4. Finally, query `after`.

**Parents are searched in list order**, rather than merging module sets and picking the “best version”. If two parents contain a module with the same name, ordering is a lookup rule; graph validity still undergoes further checks. Do not rely on overlapping multi-parent designs to bypass consistency rules.

The static overload requires a non-empty `parents` list; the Javadoc also states constraints when multiple parents have inconsistent target operating systems, architectures, or versions. A graph resolved by `Configuration.resolve` does not guarantee that the runtime can arbitrarily create a layer if parent layers do not match parent configurations or if package/loader conflicts exist.

When there is only one parent, using `parent.resolve(before, after, roots)` is usually easier to read and less error-prone because the API explicitly indicates the inherited parent.

## 10. How resolve and resolveAndBind Differ in Observation Scope

`resolve` follows roots and `requires` dependencies to build the readability graph. `resolveAndBind` also considers **service-use dependencies**:

- After resolving roots/dependencies like `resolve`, modules with `uses` in the new configuration **and parent configurations** are examined.
- The resolver scans provider modules found via the supplied `ModuleFinder`s (involving `findAll()`). Providers with a matching `provides ... with ...` can be added to the new configuration, pulling in that provider module's dependencies.
- Adding service-provider modules can introduce further `uses`, so this process can iterate until no new modules need to be added.
- `resolveAndBind` remains subject to name-lookup rules and graph consistency checks. It can add modules to `child.modules()` that inspecting only `roots` and `requires` would not predict.

Illustrative descriptor example, **not a standalone program**:

```java
// module-info.java of the consumer module
module demo.consumer {
    uses demo.api.Codec;
}

// module-info.java of the provider
module demo.provider {
    requires demo.api;
    provides demo.api.Codec with demo.provider.JsonCodec;
}
```

A provider can only be resolved/bound if its descriptor, exports/readability, dependencies, and finders are validly configured. Finder precedence order should not be interpreted as provider execution order or provider quality.

**Avoid confusion:** `ServiceLoader.load(...)` operates at the runtime service discovery step; `Configuration.resolveAndBind(...)` expands the module graph during resolution. The two APIs relate to service providers but address different stages.

## 11. When Resolution Fails: Wrong Source or Invalid Graph?

### FindException: Observability Issues

`java.lang.module.FindException` commonly occurs when:

- A required root or dependency is not found across `before`, parents, and `after`.
- A finder cannot read a JAR, encounters a malformed `module-info.class` descriptor, finds two modules with the same name in a single directory of modules, or hits an error during lookup.
- A module is found, but its descriptor cannot be parsed or module metadata is invalid.

If before has a broken module, do not expect the resolver to silently “skip before and try after” like a fallback reload system. Exact behavior depends on the finder failure; fix or filter the input rather than treating after as a rescue mechanism for broken configurations.

### ResolutionException: Graph Consistency Issues

`java.lang.module.ResolutionException` can occur when:

- Module A `requires` B and forms an invalid `requires` cycle.
- A module reads two different modules with the **same name**; including the case where a module reads another copy with the same name as itself.
- A module simultaneously reads two modules exporting the same package to it (split-package conflicts), or the module's own package conflicts with a package it reads.
- A module declares `uses` / `provides` for a service type in a package that is not present or not properly exported per readability.

The before/parents/after order only selects **candidates for module names**; it does not skip consistency checks. Finding all modules is a necessary condition, not sufficient to produce a valid graph.

### Other Errors

- `IllegalArgumentException` when calling the static overload with an empty parent list or a multi-parent configuration with conflicting target OS/architecture/version per Javadoc.
- `SecurityException` in environments where a security policy/manager blocks module lookup.
- Versions in module images/descriptors are metadata: they do not automatically solve binary/source compatibility or verify JAR provenance. The runtime must enforce its own version checks and plugin rules before building the module graph if required by the product.

## 12. From Configuration to ModuleLayer: Boundaries to Keep Clear

The section 6 program **only** creates `Configuration`s. To actually run code inside modules, the JVM needs an appropriate `ModuleLayer`:

```java
// Illustrative when parent is the boot layer:
ModuleLayer bootLayer = ModuleLayer.boot();
Configuration child = bootLayer.configuration().resolve(
        before, ModuleFinder.of(), Set.of("demo.app"));
ModuleLayer layer = bootLayer.defineModulesWithOneLoader(
        child, ClassLoader.getSystemClassLoader());
```

This is an **illustrative** snippet: valid finders and JARs with code must be prepared, and the child's parent configuration must match the parent layer used. Do not blindly apply this snippet to `beforeWins` from section 6 because its parent configuration is **not directly the boot configuration**; materializing it requires creating the corresponding layer for `parent` first, then creating the child layer with the matching parent relationship.

- `Configuration` determines which modules and readability edges exist logically.
- `ModuleLayer` creates runtime `Module` objects and maps modules to class loaders. It also enforces package- and loader-related constraints.
- `before` and `after` **are not class loaders**, nor do they define “parent-first/child-first class loading” as in `ClassLoader.loadClass`. Those two orderings belong to separate mechanisms.
- Defining a new layer does not modify the parent layer; modules in the parent continue to exist in that layer.
- If plugins must be removed from the JVM or hot-reloaded, you must manage the lifecycle of classes, objects, service registrations, threads, caches, and class loaders; a `Configuration` does not provide an automatic “replace running module” operation.

## 13. Automatic Modules and Overly Broad Finder Sources

A system using the module path may encounter **automatic modules** created from JARs without `module-info.class`. According to module resolution rules, if an automatic module is enumerated, other observable automatic modules may also need to be enumerated, so the result can be broader than the dependencies visible in `requires` descriptors.

Impact on `before` and `after` design:

- Placing a large plugin directory into `before` can make many automatic modules observable. Do not assume only a single JAR is considered just because the initial root is one module.
- When using `resolveAndBind`, service providers within finder scope can pull additional modules into the graph. Adding a single provider JAR can change the scope of resolved modules.
- `ModuleFinder.ofSystem()` has broad system scope. If the parent configuration already contains the required system modules, using `ModuleFinder.of()` as `after` is usually easier to control than an unintended extra finder.
- If strict module name/version policies are needed, verify `find(name)` and `findAll()`, restrict finder inputs, and check source metadata and consistency before allowing plugins to materialize.

JPMS is not a dependency manager capable of resolving Maven/Gradle-style version conflicts automatically, nor does it replace process-level isolation for untrusted plugins.

## 14. Diagnostic Checklist and Common Misconceptions

| Symptom | How to Check |
|---|---|
| Module in after is not selected | Is there a same-named module in before or a parent config? |
| Parent has 1.0 but child uses 2.0 | Before has a same-named copy; inspect `child.modules()`, `ResolvedModule.reference().location()` |
| `findModule()` finds the name but `modules()` does not contain it | The module is in a parent configuration; this result is valid |
| Root “not in before” still resolves | The root may have been found in a parent or after |
| Finder sees JAR but resolve reports missing dependency | The root's finder does not necessarily see every dependency; verify each name across all three levels |
| Right module name but wrong JAR selected | Check the order of `ModuleFinder.of(paths...)` and `ModuleFinder.compose(...)` before checking before/parent/after |
| Pick highest version? | No such mechanism exists: `before/parents/after` is a precedence policy, not a version solver |
| Split package/duplicate readability | Inspect `requires`, `requires transitive`, `exports`, parent graph, and `ResolutionException` |
| `resolveAndBind` pulls in extra modules | Modules with `uses` and providers in finders expand the graph |
| Configuration resolves but classes fail to load | A `ModuleLayer` might not be defined yet; also loader, package, access, and code limits apply |
| Plugin hot reload sees old version | Cannot mutate parent `Module`/classes by changing the after finder; need a new lifecycle/layer/loader |
| Error appears only when finding multiple modules | `findAll()` may hit a broken JAR/descriptor while single-name `find()` did not touch that source |

When designing a module resolution contract for runtime extensibility:

1. **Identify which modules the parent configuration already has**, not just by inspecting a module-path folder. When using multiple parents, document the exact ordering and ancestor tree.
2. **Choose `before` contents deliberately.** This is where you put modules when you genuinely want a new module to take precedence over a same-named module in a parent. Verify compatibility rather than assuming runtime override works automatically.
3. **Choose `after` as a bounded fallback source.** It cannot override a parent when before does not find a match.
4. **Distinguish observable and resolved modules.** Print `finder.find(name)`, `Configuration.modules()`, and `Configuration.findModule(name)` to explain which source was chosen.
5. **Test duplicate-name, missing-name, and service-binding cases.** Use explicit module descriptors/versions, assert `ResolvedModule.configuration()` or `modules().contains(...)`, and test both `FindException` and `ResolutionException`.
6. **Materialize layers deliberately.** Parent configuration, parent layers, class loaders, and lifecycle must align; resolution is only the first step.

**Remember:** In `Configuration.resolve`, each module name is looked up in **before → parent(s) → after** order. A module already in a parent is reused and not added to the child configuration; before can supply a new same-named module; after is only the last resort. This is a rule about **module resolution**, not class-loading order or a version-selection algorithm.

**Authoritative sources:** [Java SE 17 — Configuration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/Configuration.html), [ModuleFinder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html), [ModuleLayer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html), and [Module resolution](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/package-summary.html).