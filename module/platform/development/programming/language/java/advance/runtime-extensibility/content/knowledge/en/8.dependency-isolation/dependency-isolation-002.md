# Comparing a Shared Loader, Per-Plugin Loaders, and Dependency-Sharing Plugin Groups

## 1. The Problem to Solve: Multiple Plugins, Multiple Dependency Versions

Suppose a Java application (the host) has three plugins: **A** exports reports, **B** processes documents, and **C** analyzes data. A is built with `lib-json:1.x`, B requires `lib-json:2.x`, and C also uses `lib-json:2.x`. The host needs to load all of them in the same JVM without modifying vendor plugins.

There are three main choices for the **class sharing scope (class loading boundary)**:

1. **A single shared loader:** place plugin JARs and dependencies in the same class-defining scope.
2. **A dedicated loader per plugin:** each plugin sees its own dependencies while sharing the host API through a parent loader.
3. **Dependency-sharing plugin groups:** each group has a loader containing shared dependencies at a chosen version; member plugins have child loaders or share a loader scope, depending on the desired level of isolation.

All three still run within the **same JVM and process**. The main differences are class identity, which library version is defined, the scope of static state, the ability to unload plugins, memory footprint, and operational complexity. Class loaders do **not** create a security sandbox for running untrusted code.

This article uses Java 17+ and JARs on the **class path** to build the model first, then compares how it applies with JPMS (Java Platform Module System). "A shared loader" is a deployment strategy, not necessarily a single class loader instance in the entire JVM: the JDK still has bootstrap/platform/application loaders and other loaders.

## 2. Foundation for the Right Decision: Class Name Alone Does Not Identify a Type

### 2.1. Class Identity = Binary Name + Defining Loader

The JVM considers a class/interface to be identified by its **binary name and defining `ClassLoader`**. Two classes both named `com.acme.lib.Model` but defined by two independent loaders are **two distinct runtime types**.

~~~text
HostClassLoader
├── PluginALoader  → com.acme.lib.Model (v1)
└── PluginBLoader  → com.acme.lib.Model (v2)

Same class name, but:
(Model, PluginALoader) != (Model, PluginBLoader)
~~~

Consequence: a `Model` v1 object from A cannot be cast to B's `Model` v2 merely because `getClass().getName()` is identical. Casting may throw `ClassCastException`; under certain other signature/compilation relationships, the JVM may raise `LinkageError`. Similarly, `static` fields, caches, singletons, and class initialization are scoped to the **defined class**: two versions in two loaders have separate static state (though they can still share other process resources).

The **initiating loader** is the loader asked to find a class; it may delegate to a different **defining loader**. Therefore, two different plugin loaders can still see the **exact same `Class<?>`** when both delegate to a parent that defined the API or a shared library.

### 2.2. Parent-First Is the Reliable Default Behavior

With the default `ClassLoader.loadClass(name, resolve)` implementation, the JVM/loader:

1. Checks if the class is already loaded via `findLoadedClass`.
2. Tries `loadClass` of the **parent** (or bootstrap when there is no parent).
3. If the parent does not find it, uses `findClass` of the current loader.
4. Resolves the class according to the parameter if needed.

`URLClassLoader` inherits this delegation model for regular classes. **Parent placement matters:** if the parent has already defined `com.acme.lib.Model` v1, a child loader will by default receive v1 even if its own JAR contains a v2 copy of the same name. The presence of two JARs **does not automatically create two runtime classes**.

You can build a `child-first` loader for **controlled private packages** when a framework has special requirements, but you should not use child-first globally: if a plugin redefines a service API or host DTO, casting and interface communication can break. In addition, there are package sealing, resources, loader constraints, JNI, and deadlocks when delegation ceases to be a simple tree. Use parent-first as the default and explicitly document exceptions when needed.

### 2.3. Distinguishing Four Things Often Lumped Together as "Isolation"

- **Version isolation:** allows the same binary class name to have different bytecode versions, defined by separate loaders.
- **Type/static state isolation:** avoids sharing `Class` objects and static singletons across plugins.
- **Dependency/resource isolation:** restricts the JARs, classes/resources, and provider metadata visible from a loader. Resource lookup also depends on `getResource(s)`, parent, and TCCL, so it must be verified separately.
- **Fault, security, and CPU/memory isolation:** is **not** guaranteed by loaders alone. Exceptions, threads, native libraries, JVM crashes, process-level state, and OS resources remain shared. To run untrusted code or enforce hard resource limits, use separate processes/containers.

## 3. Diagrams of the Three Models

### 3.1. Model A — A Single Shared Plugin/Dependency Loader

~~~text
ApplicationClassLoader
  └── PluginUniverseLoader
        ├── plugin-a.jar
        ├── plugin-b.jar
        ├── plugin-c.jar
        ├── lib-json-1.jar
        └── lib-utils.jar

A, B, and C all see classes defined by PluginUniverseLoader.
~~~

One loader scope can define **only one class for a given binary name**. If `lib-json-1.jar` and `lib-json-2.jar` both containing `com.acme.json.Json` are placed on the same search path, the loader does not pick different versions per plugin. In the standard `URLClassLoader` model where the parent does not contain this class, the URL/JAR where the class is found first wins for that name; the remaining version gets no "second chance" to be defined with the same name in that loader.

**Suitable for:** a small number of plugins built and tested together; they use a single resolved dependency graph; coordinated upgrades/restarts are acceptable. Loader overhead, memory duplication, and management effort are low.

**Trade-offs:** plugins share a single set of versions and the static state of shared libraries. If B changes to require an API present only in v2, it may encounter `NoSuchMethodError` if the loader selected v1; adding another JAR does not guarantee a fix. If all plugins are placed in the same loader, replacing one plugin's classes with a **new loader** usually entails replacing the entire loader scope, unless a more complex reload mechanism is used.

### 3.2. Model B — Dedicated Loader per Plugin

~~~text
ApplicationClassLoader
  ├── Host API / contracts / shared DTO
  │
  ├── PluginALoader
  │     ├── plugin-a.jar
  │     └── lib-json-1.jar
  │
  ├── PluginBLoader
  │     ├── plugin-b.jar
  │     └── lib-json-2.jar
  │
  └── PluginCLoader
        ├── plugin-c.jar
        └── lib-json-2.jar
~~~

Each plugin loader has its own search path. Because `lib-json` is not in the parent and plugin loaders do not delegate to one another, A gets `Json` v1, while B and C get **two independently defined copies of `Json` v2**. Even though B and C use identical bytecode/versions, they do **not** share class identity if each loader defines the library itself.

**Suitable for:** plugins updated/tested independently, having version conflicts, or needing to unload one plugin while others keep running. This is the common choice for multi-vendor plugin platforms.

**Trade-offs:** libraries are loaded repeatedly, increasing class metadata/Metaspace, JIT compilation, static caches, and resources; passing dependency-private objects directly to another plugin is unsafe. Every plugin must keep host contracts and DTOs in the shared parent. A plugin can release its loader only when no objects, threads, listeners, caches, or references hold onto its classes/loader.

### 3.3. Model C — Dependency-Sharing Plugin Groups

~~~text
ApplicationClassLoader
  ├── Host API / shared DTO
  │
  ├── GroupOneDepsLoader  (lib-json-1.jar)
  │     └── PluginALoader (plugin-a.jar)
  │
  └── GroupTwoDepsLoader  (lib-json-2.jar)
        ├── PluginBLoader (plugin-b.jar)
        └── PluginCLoader (plugin-c.jar)
~~~

Group One and Group Two have separate dependency loaders: they can use **two different versions of `Json`**. Within Group Two, B and C both delegate to `GroupTwoDepsLoader`, so they **share the same `Class<?>` for `Json` v2 and its static state**. The private implementations of B/C can still reside in two separate child loaders.

**Suitable for:** many plugins requiring the same heavy library stack and governed for compatibility by "cohort"/group; reducing memory duplication while still isolating groups using different versions.

**Trade-offs:** group members have **coupled** dependency versions and lifecycles. If B needs v3 while C needs v2, you must test compatibility or move B to another group. To unload a group dependency loader, you must ensure **all** child plugins and all related objects/classes/threads have been released. As long as a group loader remains alive, the group's library classes can still be retained.

**Technical note:** a group loader as diagrammed usually holds the **group's dependencies**, while plugin code lives in child loaders. A variant that puts both plugin code and dependencies into **one loader per group** is simpler, but loses code/lifecycle separation among plugins in the same group. The label "dependency-sharing plugin groups" should clarify these two variants before adoption.

## 4. Summary Comparison Table

| Criterion | Single shared loader | One loader/plugin | Group dependency loader + child/plugin |
| --- | --- | --- | --- |
| Plugin class scope | All share one scope | Separate per plugin | Separate per plugin; dependencies shared within group |
| Two versions of the same binary class name | No within the same defining loader | Yes, across two loaders | Yes, across groups; **cannot** coexist with same name/different versions in one group deps loader |
| Static fields of dependencies | Shared across all plugins using that class | Separate per plugin | Shared within a group, isolated across groups |
| Class identity of dependencies | Shared if the same class is defined | Distinct across plugins | Shared within group, distinct across groups |
| Class/JIT/cache duplication cost | Usually low | Potentially high | Intermediate |
| Plugin release decoupling | Weakest if plugin code shares loader | Better for class loading, still depends on actual lifecycle | Plugin code can be decoupled; changing group deps affects all members |
| Independent dependency upgrades | Centralized for all | Per plugin | Per group |
| Dependency graph control | One single graph | One graph per plugin | One shared graph per group + private deps |
| Plugin ↔ host communication | Relatively simple if API is unified | Requires shared parent API/DTO | Requires shared parent API/DTO; avoid leaking group-private classes across group boundaries |
| Deploy/debug complexity | Low | Medium–high | Highest for group/version/lifecycle rules |
| Preferred use case | Plugins by the same team, built/tested together | Independent plugins / conflicting versions | Clustered plugins with many heavy shared dependencies |

No model is inherently "the fastest." More loaders do not automatically mean slower runtime: actual impact depends on the number of classes loaded, JIT, dependency size, retained resources, concurrency, and whether the application creates instances. Measure **Metaspace, heap retained size, startup time, class count, CPU/JIT, and thread/file handle counts** on real workloads before optimizing.

## 5. Runnable Java 17+ Example: Observing All Three Models Using Two Versions of a Class

The lab below needs no third-party libraries. It builds two JARs both containing `demo.lib.Version` returning `v1`/`v2`; PluginA is compiled against v1, PluginB against v2. The host does **not** include `demo.lib.Version` on its class path; the host uses reflection solely to invoke the two demo plugins, thereby illustrating lookup/identity without yet needing to design a full SPI.

### 5.1. Source Structure

~~~text
loader-compare/
├── src/
│   ├── v1/demo/lib/Version.java
│   ├── v2/demo/lib/Version.java
│   ├── a/demo/plugin/PluginA.java
│   ├── b/demo/plugin/PluginB.java
│   └── host/LoaderComparison.java
├── build/                 # Generated after compilation
└── jars/                  # Generated after creating JARs
~~~

File `src/v1/demo/lib/Version.java`:

~~~java
package demo.lib;

public final class Version {
    public static String value() {
        return "v1";
    }
}
~~~

File `src/v2/demo/lib/Version.java` has the same binary name and signature, but its method body returns `v2`:

~~~java
package demo.lib;

public final class Version {
    public static String value() {
        return "v2";
    }
}
~~~

File `src/a/demo/plugin/PluginA.java`:

~~~java
package demo.plugin;

import demo.lib.Version;

public final class PluginA {
    public String run() {
        return "A:" + Version.value();
    }
}
~~~

File `src/b/demo/plugin/PluginB.java`:

~~~java
package demo.plugin;

import demo.lib.Version;

public final class PluginB {
    public String run() {
        return "B:" + Version.value();
    }
}
~~~

File `src/host/LoaderComparison.java`:

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class LoaderComparison {
    private static String run(ClassLoader loader, String className)
            throws ReflectiveOperationException {
        Class<?> type = Class.forName(className, true, loader);
        Object instance = type.getConstructor().newInstance();
        return (String) type.getMethod("run").invoke(instance);
    }

    private static Class<?> versionClass(ClassLoader loader)
            throws ClassNotFoundException {
        return Class.forName("demo.lib.Version", false, loader);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 4) {
            throw new IllegalArgumentException(
                    "Pass lib-v1.jar lib-v2.jar plugin-a.jar plugin-b.jar");
        }

        URL v1 = Path.of(args[0]).toUri().toURL();
        URL v2 = Path.of(args[1]).toUri().toURL();
        URL pluginA = Path.of(args[2]).toUri().toURL();
        URL pluginB = Path.of(args[3]).toUri().toURL();
        ClassLoader host = LoaderComparison.class.getClassLoader();

        // A: one shared loader; v1 precedes v2 in the URL search path.
        try (URLClassLoader one = new URLClassLoader(
                new URL[] { v1, v2, pluginA, pluginB }, host)) {
            System.out.println("ONE " +
                    run(one, "demo.plugin.PluginA") + " " +
                    run(one, "demo.plugin.PluginB"));
        }

        // B: one loader per plugin, each loader has its own version.
        try (URLClassLoader a = new URLClassLoader(
                     new URL[] { pluginA, v1 }, host);
             URLClassLoader b = new URLClassLoader(
                     new URL[] { pluginB, v2 }, host)) {
            System.out.println("PER " +
                    run(a, "demo.plugin.PluginA") + " " +
                    run(b, "demo.plugin.PluginB") +
                    " sameLib=" + (versionClass(a) == versionClass(b)));
        }

        // C: v1 dependency in the group loader; plugin code in two child loaders.
        try (URLClassLoader group = new URLClassLoader(
                     new URL[] { v1 }, host);
             URLClassLoader a = new URLClassLoader(
                     new URL[] { pluginA }, group);
             URLClassLoader b = new URLClassLoader(
                     new URL[] { pluginB }, group)) {
            System.out.println("GROUP " +
                    run(a, "demo.plugin.PluginA") + " " +
                    run(b, "demo.plugin.PluginB") +
                    " sameLib=" + (versionClass(a) == versionClass(b)));
        }
    }
}
~~~

**Reading the code in order:**

- `run(loader, className)` asks the exact loader to load the plugin code. It uses reflection only for demo invocation; in a real product, use a shared API interface in the parent.
- `versionClass` returns the `Class<?>` for `demo.lib.Version` visible to each loader; `==` compares **runtime class identity**, not names.
- Case ONE puts v1 before v2 in the URL search path. `Version` is defined from v1; both A and B see v1.
- Case PER uses two independent loaders, each containing exactly one version and its corresponding plugin.
- Case GROUP has both plugins delegate up to the same group loader with v1: both see v1 and the same `Class<?>`. B was compiled against v2, but `value()` remains signature-compatible so it runs, even though it **no longer uses the version it was compiled against**.

### 5.2. Compiling and Packaging

Run from the `loader-compare` directory using **PowerShell** (Windows, JDK 17+ with `javac` and `jar`). The commands below create four exact JARs; no build tool is used so learners clearly see which dependency belongs to which JAR:

~~~powershell
New-Item -ItemType Directory -Force build\v1,build\v2,build\a,build\b,build\host,jars | Out-Null

javac -encoding UTF-8 -d build\v1 src\v1\demo\lib\Version.java
javac -encoding UTF-8 -d build\v2 src\v2\demo\lib\Version.java

javac -encoding UTF-8 -cp build\v1 -d build\a src\a\demo\plugin\PluginA.java
javac -encoding UTF-8 -cp build\v2 -d build\b src\b\demo\plugin\PluginB.java

javac -encoding UTF-8 -d build\host src\host\LoaderComparison.java

jar --create --file jars\lib-v1.jar -C build\v1 .
jar --create --file jars\lib-v2.jar -C build\v2 .
jar --create --file jars\plugin-a.jar -C build\a .
jar --create --file jars\plugin-b.jar -C build\b .

java -cp build\host LoaderComparison jars\lib-v1.jar jars\lib-v2.jar jars\plugin-a.jar jars\plugin-b.jar
~~~

**Exact expected stdout** (on JDK 17+ with the exact four JARs just created and the host having only `build\host` on the class path):

~~~text
ONE A:v1 B:v1
PER A:v1 B:v2 sameLib=false
GROUP A:v1 B:v1 sameLib=true
~~~

This is the most important result:

- **ONE:** shared classloader so both are governed by **a single version choice**; the "first found wins" behavior here is tied to URL order and the parent not containing `Version`.
- **PER:** same name `demo.lib.Version` yet two distinct classes; A and B are independent in version.
- **GROUP:** each plugin has its own loader **but** both see the dependency from the group parent, so they share the type and version.

For a real multi-group GROUP model, create `Group1Loader` from v1 for plugin A and `Group2Loader` from v2 for B/C. When comparing `versionClass(group1Child) == versionClass(group2Child)`, the result is `false` because the two group loaders define independently. A single-group lab model was chosen to highlight the **intra-group sharing** mechanism.

### 5.3. Breaking Compatibility to Understand NoSuchMethodError

Add a `public static String newFeature()` method **only** in `Version` v2, edit `PluginB.run()` to call that method, and recompile B against v2.

- With **PER**, B sees `Version` v2 and can call `newFeature()`.
- With **ONE** if v1 is found first, B will look up the method on `Version` v1 and may throw `NoSuchMethodError` when the call is linked/executed.
- With **GROUP** pinned to v1, B also runs into trouble; you must upgrade the whole group's version if backward compatible with A, or move B to another group.

Do not arbitrarily rearrange JAR order as a compatibility strategy. Build/test should determine the dependency graph and versions up front; runtime loaders merely enforce that decision.

## 6. Shared API Boundary: Conditions for Safe Plugin Interaction

The layout with a shared parent loader for **host APIs, DTOs, event contracts, and service interfaces**. In a real plugin platform, this is the foundational rule:

~~~text
Host / ApiLoader  →  com.example.api.Plugin, Request, Result
       │
       ├── PluginALoader → plugin A + private library v1
       │
       └── PluginBLoader → plugin B + private library v2

Host calls through com.example.api.Plugin,
without directly casting A/B's private classes.
~~~

Example **illustrative signature, not a standalone program**:

~~~java
package com.example.api;

public interface Plugin {
    String id();
    Result execute(Request request);
}
~~~

`Request` and `Result` must also be types seen by the host and plugins **from the same defining loader**, or use an explicit exchange format (such as byte arrays or versioned/schema-backed JSON), avoiding passing library-private objects with differing class identities across the boundary.

If `plugin-a.jar` packages a duplicate copy of `com.example.api.Plugin` and loader A defines that duplicate (for instance due to misconfigured child-first loading), A's object may fail to cast to the host's `Plugin`. With parent-first and the API already in the parent, the child's copy is normally "shadowed" by the parent, yet packaging duplicate APIs still makes the system hard to control, especially when API versions differ.

**Packaging rules:**

- Separate `plugin-api.jar` from implementations and place the API in the parent/shared layer.
- Plugins compile against the API as `provided`/`compileOnly` if the build tool supports it, avoiding re-bundling it into the plugin runtime JAR.
- Publish only sufficiently stable DTOs; do not let the API expose concrete types from `lib-json-v1` if plugins need two different versions.
- If plugin A must call B, prefer going through a **host-owned interface/event bus** or a serializable payload with a schema. Do not pass raw `com.thirdparty.JsonNode` objects if that type is defined separately in each loader.
- Test compatibility between the host API and plugins built against older versions. **Identical class identity does not guarantee binary/source compatibility** if signatures have changed.

## 7. How to Determine Which Dependencies Must Be Shared and Which Must Be Private

You cannot decide based solely on JAR filenames. Classify **each dependency** by its role:

| Dependency category | Where to place it | Rationale and caveats |
| --- | --- | --- |
| JDK/Java SE APIs | JVM built-in/platform loaders | Do not copy into plugins |
| Service API, host DTO/event contracts | Shared parent | Guarantees class identity and casting across the boundary |
| Data libraries appearing in public APIs | Either promote to shared API with unified version, or change boundary to custom DTOs | If each plugin keeps its own version while public API uses that type, integration breaks easily |
| Purely private libraries where each plugin needs a different version | Plugin loader | Prevents version collisions |
| Large libraries used by many plugins at the **same compatible version** | Group dependency loader | Reduces duplicate classes/static caches; trade-off is coupling |
| Runtime frameworks using TCCL/`ServiceLoader` | Decide discovery scope and resource visibility separately | Where the library sits is not enough; must verify TCCL/resources/config |
| Native libraries/JNI, global agents, process singletons | Requires separate policy at JVM/process level | Classloaders do not guarantee isolation of native code or OS resources |

**An important case:** two plugins both using `lib-x:2.0` does not automatically mean they should share a group loader. If the library has mutable static singletons, global registrations, thread pools, logging contexts, or per-tenant caches, sharing the class can cause **unintended state sharing**. You must evaluate behavior and ownership, not just version.

Conversely, if `lib-x` is a stateless algorithmic library with a pinned version and large class metadata footprint, a group loader is typically more economical than loading it separately per plugin.

## 8. Class Loader Tree vs. Dependency Graph

A build dependency graph is typically a DAG:

~~~text
Plugin A → API, Lib X, Lib Y
Plugin B → API, Lib X, Lib Z
Plugin C → API, Lib X, Lib Z
~~~

However, a standard `ClassLoader` has **a single parent**. You cannot directly assign loader B two independent parents ("API loader" and "X loader") like arbitrary dependency edges. You must structure an appropriate loader tree (API → group deps → plugin), or use carefully designed custom routing/delegation.

In the group model:

~~~text
ApiLoader
   └── GroupDepsLoader
         ├── PluginBLoader
         └── PluginCLoader
~~~

Plugin B sees both the API (via ancestors) and the group dependencies. B's private dependencies sit in child B, so C **cannot automatically see** B's private classes. If B must directly access C's implementation, a host-controlled bridge is needed; never quietly add cyclic B ↔ C delegation. Cyclic delegation or custom loaders that are not parallel-capable can cause deadlocks/classloading races, especially when multiple threads load classes concurrently.

For **overlapping package names**, loader boundaries can avoid collisions between two **groups**. Within the **same group loader**, the same binary name can still be defined only once; do not treat groups as "multi-version magic."

## 9. TCCL, ServiceLoader, and Resources: Class Isolation Alone Is Not Enough

### 9.1. Thread Context ClassLoader (TCCL)

Some frameworks/libraries discover implementations via `Thread.currentThread().getContextClassLoader()`. The `ServiceLoader.load(MyService.class)` overload uses the calling thread's TCCL; thus a host calling from a thread pool whose TCCL is the host loader may **fail to find** providers present only in a plugin loader.

You can set the TCCL around a plugin call when a framework requires it. The snippet below is **illustrative, not standalone** (variables `pluginLoader` and `action` must be declared):

~~~java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    action.run();
} finally {
    thread.setContextClassLoader(previous);
}
~~~

Use `finally` to avoid leaking the TCCL on pool threads after returning. If a plugin spawns threads itself, those threads may inherit the TCCL and **retain the old loader**, so lifecycle management must cover plugin-created executors/threads too.

When you want to specify the provider lookup scope explicitly, you can use `ServiceLoader.load(Service.class, pluginLoader)`. However, with parent-first/resource delegation, that scope can also include provider metadata in the parent; **do not treat this as an absolute "current plugin only" list** without controlling resource discovery. If you need whitelisting or a registry by plugin ID, permissions, and version, maintain explicit catalogs/metadata.

### 9.2. Service Provider Metadata Is Also a Resource

Class path SPI uses `META-INF/services/<FQCN>`. `ServiceLoader` locates the resource via the loader, then loads the implementation. When a dependency or provider JAR is misplaced in the parent/group, the host might see a provider outside the intended scope, or see the metadata but fail to load the implementation and throw `ServiceConfigurationError`.

When packaging a fat JAR/shaded JAR, you must handle **merging service files** properly. Merely combining class files while overwriting one metadata file can make a provider vanish even though its bytecode remains in the JAR.

### 9.3. JPMS and ModuleLayer

With **named modules**, JPMS uses `module-info.java` to declare `requires`, `exports`, `opens`, `uses`, `provides`, and places modules into a `ModuleLayer`. Java 17 provides:

- `ModuleLayer.defineModulesWithOneLoader(...)`: one loader for the modules in that layer.
- `ModuleLayer.defineModulesWithManyLoaders(...)`: one loader **for each module** in that configuration.
- `ModuleLayer.defineModules(...)`: maps module names to loaders via a custom function (must obey module readability, package/class-loading constraints, and the specific design).

**Do not equate "one loader per module" with "one loader per plugin"**. One plugin may consist of multiple modules; one module may contain multiple packages/features. The module graph has its own resolution/readability/export rules, whereas the class loader graph determines where types are defined. A module layer using a single shared loader can even fail to be created when there are overlapping packages or split delegation, per API rules.

Therefore: class-path `URLClassLoader` and JPMS layers are **two different management models**. Merely moving JARs to the module path does not automatically isolate version conflicts; you must design module names, configurations, layers, and loader mappings consistently.

## 10. Memory Cost and Lifecycle: The Price of Isolation

### 10.1. What Gets Duplicated?

With N plugins using copies of the same library while each plugin loader defines the library's classes separately:

- **Metaspace / class metadata** for classes loaded in each loader can grow.
- **JIT compilation / code cache** and class initialization may be performed separately for independent runtime classes.
- **Static state/caches**, registries, threads, pools, and resources created by the library can be duplicated.
- **Heap** still depends on the objects actually created and retained. Merely having a JAR in the URL list does not cause all classes and objects to be loaded immediately.

A group loader reduces part of the duplication if plugins actually delegate to the same group library. However, it also creates **shared fate**: library classes/static caches remain alive as long as the group loader is still used by any plugin. Therefore, do not promise fixed MB savings without measuring.

### 10.2. Closing URLClassLoader Does Not Mean Immediate Unloading

`URLClassLoader` implements `Closeable`. `close()` closes resources/JAR file handles opened by the loader (within the limits of the API), helping release file handles and avoid situations where files cannot be replaced on some operating systems. It does **not** "erase running bytecode," interrupt threads, call `Plugin.stop()`, or force immediate class unloading.

For a generation of a plugin loader to become eligible for GC/unloading when the JVM permits:

1. Stop accepting new requests into the old generation.
2. Wait for current requests to finish or enforce a clear timeout/cancel policy.
3. Call `stop/close` hooks on the plugins and the resources they own.
4. Stop threads, executors, timers, listeners, callbacks, and watchers; clear registries/static caches referencing the plugin.
5. Restore the TCCL on thread pools and drop all references to instances, `Class<?>`, `Method`, `ClassLoader`, or objects from the dependency group.
6. Close loaders **in child → parent order** and drop references to the old loaders.
7. Conclude leaks/unloading only based on actual heap/classloading evidence; GC and class unloading have no guarantee of happening instantaneously.

**For groups:** do not close/discard `GroupDepsLoader` while another child plugin is still using its classes. To upgrade `lib-json-2` to `lib-json-3` for the entire group, typically create a **new group loader**, create new plugin loaders, start/validate them, shift traffic, and then release the **entire** old group generation.

### 10.3. No Hot-Swapping Libraries Just by Editing JARs on Disk

Once a class is defined, modifying the JAR file does not change that class's bytecode. `ServiceLoader.reload()` only resets the provider cache of the **ServiceLoader object**; it does not replace JAR URLs/class loaders or lifecycle. To load a genuinely different version with the same binary names, a **new defining loader** is generally required (or instrumentation mechanisms with their own constraints, outside normal plugin architecture).

Do not close an old loader while another thread is actively loading classes from it; the `URLClassLoader.close()` API does not guarantee results when run concurrently with class loading.

## 11. Build Configuration and Pre-Deployment Testing

### 11.1. Pinning Versions and Checking the Dependency Graph

Before building loaders, you need to know **exactly which JARs** go into each loader:

- List transitive dependencies of plugins, checking for duplicate classes and conflicts by **binary names**, not only Maven artifact names.
- Pin versions of shared dependencies per group and build a compatibility matrix between plugins A/B/C and group versions.
- Do not let private dependencies "leak" onto the parent/application class path, because parent-first will prevent plugins from selecting their own versions.
- Place the common API in the parent, and compile/test multiple plugin versions against the minimum supported API.
- Check resource/service files, native libraries, log bindings, XML parsers, bytecode tooling, and plugin shading/relocation.

**Shading/relocation** is an alternative strategy: renaming packages/binary names of a bundled library so two copies can coexist even in the same defining loader. However, it affects reflection, serialization, resource paths, SPI metadata, native bindings, and public signatures; it must be tested thoroughly and not treated as a default solution.

### 11.2. What Should the Test Matrix Cover?

| Test | Single shared loader | Per-plugin loader | Group loader |
| --- | --- | --- | --- |
| Two plugins using conflicting versions | Must detect and report incompatibility before deploy | Run concurrently if types are not exposed through the API | Must split into two groups if no compatible version exists |
| Type identity | Shared classes have the same defining loader | Library-private classes have distinct identities | Shared within group, distinct across groups |
| Constructors/static singletons | Shared runtime class | Initialized separately per loader | Shared within group |
| `NoSuchMethodError` on binary mismatch | Especially requires testing version conflicts | Test each dependency set separately | Test group-wide compatibility |
| Resource/SPI lookup | Check duplicate/merged provider files | Check correct loader/TCCL | Check no provider leaks to other member plugins |
| Upgrading one plugin version | Usually replaces the shared scope | Create a new-generation loader for that plugin | May need to rebuild the group if shared dependencies change |
| Stop/unload | Performed at shared loader scope | Test closing each plugin individually | Test draining the entire group before closing shared deps |
| Memory/CPU | Measure baseline | Measure class count/metaspace per loader | Measure savings and shared static resources |

Every critical test should also check **old and new code temporarily coexisting** during traffic transition: plugin systems fail not only at startup but also during lifecycle overlap. In particular, an old plugin whose threads retain its loader as TCCL can steadily increase Metaspace over repeated redeploys.

### 11.3. Diagnostic Tools

- `jar tf plugin.jar`: inspect classes and `META-INF/services` inside a JAR.
- `javap -classpath ... -p com.acme.Type`: compare method/field signatures at build time.
- `jdeps ...`: assists in inspecting JAR/module dependencies.
- `java -Xlog:class+load=info ...`: observe class loading sources on JVMs supporting unified logging.
- `jcmd <pid> VM.classloaders` or JDK-appropriate diagnostic commands: observe the loader tree and class counts in a running environment; some options/tools vary by JVM.
- Heap dump/profiler: locate references holding old loaders, `Thread.contextClassLoader`, listeners, static maps, singletons, and plugin instances.

Inspect class identity directly in diagnostic code (**illustrative** snippet, requires an existing `obj` variable):

~~~java
Class<?> type = obj.getClass();
System.out.println("name=" + type.getName());
System.out.println("definingLoader=" + type.getClassLoader());
System.out.println("module=" + type.getModule());
~~~

A loader's `toString()` and `CodeSource` info can vary by implementation; do not use a loader's display string as a permanent identifier key. If possible, include **plugin ID + plugin version + generation ID + loader identity** in logs/metrics to trace release errors.

## 12. Choosing an Architecture from Real Requirements

### Case 1: An Internal Application with a Few Plugins Built by One Team

Plugins are built in the same pipeline, dependencies are managed via a single BOM or dependency constraints, and releases go out with the host. **A single shared loader** is the easiest approach to govern. When a requirement for two versions of the same class name arises, consider unifying versions or isolating plugins before going further.

### Case 2: A Marketplace Loading JARs from Multiple Vendors

Vendors release independently and may use logging/JSON/HTTP libraries at different versions. **A dedicated loader per plugin** is usually appropriate; marketplace contracts stay in the parent, and private libraries are not exposed through the API. You need a plugin catalog, signature/trust policy, host API compatibility checks, health checks, execution quotas if using process isolation, and a clear lifecycle.

### Case 3: Dozens of Plugins Belonging to Several "Product Suites"

Four reporting plugins use the same large v2 library suite, seven analytics plugins use library v3, and one special plugin needs v1. **Group deps loaders** can reduce class duplication within each cohort; manage versions as a **group release unit**. If one plugin in a group wants an upgrade that introduces an incompatible public ABI change, split the group or upgrade the entire cohort.

### Case 4: Plugins Containing Untrusted Code or Requiring Hard Fault Boundaries

**Do not rely solely on class loaders**. Run plugins in separate processes/containers with OS controls, resource limits, communication protocols, timeouts, and data policies; loader models only solve class organization within each JVM.

### Pragmatic Decision Tree

~~~text
Do plugins need the same binary name at different versions?
├─ No
│  └─ Do plugins have significantly independent releases/lifecycles?
│     ├─ No → A single shared loader is usually sufficient
│     └─ Yes → Per-plugin loader, or group if shared dependencies help
└─ Yes
   └─ Do they partition into stable, version-compatible groups?
      ├─ No → Per-plugin loader
      └─ Yes → Group dependency loader + child loaders
                 (explicitly document versions, ownership, upgrade strategy)
~~~

The final decision must be validated by **dependency compatibility, class identity, lifecycle, and resource measurements**, not just a clean diagram.

## 13. Common Design Mistakes

### 13.1. Placing the Same API in Multiple Loaders and Casting Across the Boundary

The typical symptom is `ClassCastException` while logs print the exact same class name. **Check the defining loader** of the host interface and the plugin implementation; move the shared API up to the parent and maintain compatible contract versions. Do not work around this with raw casts or reflection if the type boundary remains wrong.

### 13.2. Loading Private Dependencies on the Application Class Path

With parent-first delegation, a private dependency inside a plugin cannot beat a same-named class already residing in the parent. The right fix is usually correcting the **deployment class path/loader placement**, not changing URL ordering in the child when the parent has already defined the class.

### 13.3. "Using Groups to Share Everything"

If a group contains a stateful library, plugins can unintentionally share caches, singletons, and thread pools. Groups should share only dependencies proven compatible in both **API and runtime behavior**, with a clear owner for configuration and resources.

### 13.4. Assuming Per-Plugin Loaders Mean Any Object Can Be Passed Around

An object of `com.vendor.dto.Record` defined by A does not become the type B uses. When exchanging data, use host-owned DTOs, Java primitives/collections whose element types belong to the shared API, or schema-backed serialized payloads. With `List<SomePrivateType>`, generics undergo type erasure, yet the elements still carry separate class identities; that cannot be treated as a safe bridge.

### 13.5. Confusing ServiceLoader Discovery with Dependency Isolation

`ServiceLoader.load(service, loader)` only discovers providers within the loader's class/module/resource scope. It does not automatically build a per-plugin loader, group versions, or stop old providers on `reload()`. You need an independent plugin registry and lifecycle manager.

### 13.6. Forgetting to Clean Up Threads and Callbacks, Leading to "Cannot Unload"

Having called `URLClassLoader.close()` while the heap keeps growing does not prove a JVM bug. Look for references still retaining the loader: thread TCCLs, registered callbacks, scheduled tasks, host static registries, outstanding `Method`/`Class<?>`, and cached objects. Especially with group deps, even a single surviving child plugin can keep the group alive.

### 13.7. Equating JPMS with a Sandbox

JPMS establishes module readability/encapsulation and service binding; class loaders organize class scopes. They do **not** isolate CPU, heap, network/file access, or JVM crashes against malicious code. Choose a process/OS-level security boundary when the problem requires it.

## 14. Completion Checklist When Building a Plugin Platform

Before taking an architecture into production, you should be able to answer:

1. **Boundaries:** which classes belong to the host API, which to plugins, and which to groups?
2. **Versions:** does each group/plugin allow one or multiple versions of the same binary name? Is the Maven/Gradle dependency tree consistently locked?
3. **Identity:** are APIs, DTOs, annotations, and exception classes shared from the same defining loader?
4. **Discovery:** do SPI metadata, resource paths, and TCCL expose providers outside the intended scope?
5. **Lifecycle:** who performs plugin start/stop, refresh, request draining, executor shutdown, loader closing, and reference release?
6. **Concurrency:** are there races among load/discovery/release, in-flight requests, and generation updates?
7. **Memory:** have Metaspace, class unloading, heap, JIT, and static caches been measured for each option?
8. **Compatibility:** have missing dependencies, API version mismatches, `NoSuchMethodError`, `ClassCastException`, and split-version groups been tested?
9. **Observability:** do logs include plugin ID, generation, dependency group, and loader identity to trace failures?
10. **Trust:** is plugin code trusted, and if untrusted, are process/container boundaries in place?

If there is only one takeaway to remember, it is this: **which loader you place a class into determines which classes are shared, which versions can coexist, and which units must be upgraded and released together**. A single shared loader is easy to operate but shares one version space; per-plugin loaders isolate versions well but duplicate classes; group loaders provide controlled sharing yet bind members to a shared dependency lifecycle.

## 15. Standard References (Java SE 17)

- `ClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- `URLClassLoader` (constructors, parent delegation, `close()`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- `Class` (`getClassLoader()`, identity): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- `ServiceLoader` and choosing loader/layer: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- `ModuleLayer` (`defineModulesWithOneLoader`/`ManyLoaders`/`defineModules`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- The Java Virtual Machine Specification SE 17, Chapter 5 "Loading, Linking, and Initializing": https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
