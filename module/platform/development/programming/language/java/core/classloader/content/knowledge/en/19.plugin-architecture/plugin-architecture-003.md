# One ClassLoader per Plugin or Multiple Plugins Sharing a ClassLoader?

When designing a **Java plugin architecture**, an important decision is: should **each plugin have its own defining class loader**, or should **multiple plugins be loaded together through one loader**? Both models can be valid. The core differences lie in **namespace boundaries, the ability to use different dependency versions, type and state sharing, the degree of independence when upgrading/unloading, resource lookup behavior, and operational overhead**.

**Guiding rule:** If plugins have independent lifecycles, require different dependency versions, or risk colliding on binary class names, consider **one loader per plugin**. If components are released and tested as a unified set, use the same dependency versions, and need to directly exchange many internal classes, **a shared loader** may be simpler. In both cases, place the **shared communication API/SPI** in a parent loader or a consistent module contract mechanism.

This lesson assumes Java 17+ and discusses plugins running **within the same JVM**. A ClassLoader is a tool for organizing runtime classes and resource lookup; **it is not a sandboxing mechanism for executing untrusted code**.

## 1. First: What Does "One Loader" Change?

According to the *Java Virtual Machine Specification (JVMS)*, the identity of a runtime class/interface is determined by:

```text
(binary name, defining class loader)
```

For example, with the binary name `impl.Greeting`:

```text
Plugin A loader ──define──> impl.Greeting  (runtime type A)
Plugin B loader ──define──> impl.Greeting  (runtime type B)

Name: same
Defining loader: different
Result: two DIFFERENT runtime classes
```

However, if both plugins are placed into **the same loader**:

```text
SharedLoader:
  plugin-a.jar contains impl/Greeting.class
  plugin-b.jar contains impl/Greeting.class
       |
       +--> SharedLoader.loadClass("impl.Greeting")
                      |
                      +--> one runtime class selected by that loader
```

A defining loader **cannot define two different runtime classes with the same binary name**. If a second library/JAR also contains `impl.Greeting`, the code will not automatically get "the version for plugin B". Usually one version is found first according to the classpath/URL search policy; repeated requests return the same `Class<?>` already recorded by the loader.

It is important to distinguish between **calling `loadClass`** and **being defined by a loader**. With parent-first delegation, a child loader may call `loadClass("shared.api.Plugin")` yet receive a class defined by its parent. Merely calling the child loader does not prove that the class belongs exclusively to the child loader.

### Three Easily Confused Concepts

| Concept | Identity / Rule | Consequence |
|---|---|---|
| **Runtime class** | Binary name + defining loader | Two copies with the same name in different loaders are two different types |
| **Runtime package** | Package name + defining loader | Two classes with the same package name in different loaders do not automatically share package-private access |
| **Plugin instance** | A specific object instantiated from a class | Multiple instances can exist even when there is only one class/loader |

**One loader for multiple plugins** does not mean "only one plugin object". Plugins can still create multiple instances. However, they share the same runtime type if the loader defines only one class with that same name, and the **static fields** of that runtime class are also shared.

## 2. Model A: One Loader per Plugin

A simple parent-first diagram:

```text
Host / Application ClassLoader
  ├── spi.Plugin                    (public interface)
  ├── spi.Context                   (shared DTO)
  └── host.PluginManager
       ^                  ^
       | parent           | parent
       |                  |
Plugin A URLClassLoader   Plugin B URLClassLoader
  ├── impl.Greeting         ├── impl.Greeting
  ├── acme.lib.Helper v1    ├── acme.lib.Helper v2
  ├── a.properties          └── b.properties
  └── META-INF/services/... 
```

Each plugin loader has its own list of URLs or bytecode source. It maintains its own **defining namespace** for classes that the parent does not provide.

**Advantages:**

1. Two plugins can have classes with the **same binary name** and independent definitions (if they are actually defined by separate loaders).
2. Different versions of private libraries can coexist: `acme.lib.Helper` v1 and v2 are distinct runtime types.
3. Plugin lifecycles can be distinguished, monitored, and managed on a per-loader basis.
4. It is easier to design **swapping in a new loader** when updating an individual plugin without forcing all other plugins onto the same generation.
5. Resource lookup can be scoped to a specific loader, reducing config/template name collisions.

**Costs/Risks:**

- The same private library may be loaded **repeatedly** across multiple loaders; metadata, bytecode representation, and static state are not automatically shared.
- An object of a private type defined by loader A cannot be cast directly to the same-named type defined by loader B.
- A↔B communication is more difficult if methods accept or return private classes; stable contracts/DTOs must be shared.
- TCCL, ServiceLoader, resource lookup, and caching can cause code to inadvertently pick up the provider/resource from the wrong plugin.
- Unloading is not automatic: threads, static caches in the host, event listeners, JDBC drivers, logging, MBeans, executors, and references to a Class/instance can keep the loader alive.

**Subtlety with parent-first:** Two child `URLClassLoader` instances sharing the same parent **do not guarantee different library versions** if the parent already has a version of that library. If the parent contains `acme.lib.Helper`, both children will delegate to the parent by default and receive the **single** version from the parent. For true isolation, you must clearly define **shared classes in the parent** and **private classes belonging solely to plugin loaders**, or use a controlled child-first policy.

## 3. Model B: Multiple Plugins Sharing One Loader

```text
Host / Application ClassLoader
  └── spi.Plugin
        ^
        | parent
        |
One Shared URLClassLoader
  ├── plugin-a.jar
  ├── plugin-b.jar
  ├── common-helper.jar
  └── resource descriptors of the entire group
```

A shared `URLClassLoader` is created with the URLs of multiple plugins and dependencies. Every class **actually defined** by this loader shares the same loader identity.

**Advantages:**

1. Fewer class-loader boundaries, so classes in the same loader can easily share **package-private access** when in the same runtime package (while still subject to other Java rules).
2. A shared dependency version can be loaded and initialized **once for the entire group**, avoiding duplication.
3. Plugins released as a co-versioned suite can easily call each other's classes since all classes reside in a single namespace.
4. Resource scanning from a shared loader can be simpler when intentionally aggregating descriptors from the entire group.
5. Reduces complexity in module/class identity when plugins are essentially "features within the same application" without a need for isolation.

**Costs/Risks:**

- Two JARs containing the same binary class name create a **conflict**: two separate definitions cannot be selected simultaneously within the same defining loader.
- One plugin wanting `foo.Bar v1` while another plugin wants `foo.Bar v2` can lead to `NoSuchMethodError`, `NoClassDefFoundError`, incorrect behavior, or binary compatibility mismatches.
- **Static fields/singletons** belonging to shared classes are shared across plugins; this easily leaks state or creates unintended coupling.
- It is difficult to replace just one plugin implementation with the **same binary name** using new bytecode in the same loader: the JVM has no simple "redefine via `defineClass`" operation.
- The shared loader can only become collectible when all classes/instances/references of the group are no longer in use according to JVM conditions. A single still-active plugin can make the entire group hard to unload.
- The order of URLs/JARs and duplicate resource names affects the result; "plugin B having its own JAR" does not mean B will always use the class inside that JAR.

Sharing a loader can be suitable for an **integrated plugin suite released by the same team**, tested together, and deployed/upgraded in lockstep. Do not choose it merely for "fewer ClassLoader objects" while ignoring versioning and lifecycle requirements.

## 4. Comparison Table of Options

| Criterion | One Loader per Plugin | One Loader for Multiple Plugins |
|---|---|---|
| **Class identity** | Each child can define its own private classes | One binary name can only have one definition in the shared loader |
| **Same-named dependencies with different versions** | Can be isolated if the parent does not occupy that namespace | Usually conflicts; must align versions or relocate |
| **API between host and plugins** | Must share the contract in the parent/shared loader | Should still share a stable contract in the parent |
| **Plugin A calling B's private class** | Complex; requires an appropriate contract/loader visibility | Usually easier since the class is visible in the same loader |
| **Package-private between plugins** | Different runtime packages if defining loaders differ | Can be in the same runtime package when package names match |
| **Static state of private dependencies** | Separate per runtime class/loader | Shared if it is the same runtime class |
| **Duplicate resource names** | Has per-loader lookup namespaces, though delegation still has an effect | Prone to shadowing; requires a precedence/aggregation policy |
| **Replacing one plugin** | Can create a separate new loader; proper cleanup is required | Usually requires a new loader for the whole group if replacing an already-defined class |
| **Unloading** | Can clean up per plugin, though immediacy is not guaranteed | One remaining live reference can retain the entire group's namespace |
| **Memory/metadata** | Risk of duplicating class metadata, caches, and static state | Can be more economical when sharing classes |
| **Security for untrusted code** | Not a sandbox | Also not a sandbox |
| **Initial code simplicity** | More loaders/lifecycle handling | Fewer loaders, but requires conflict control |

Do not turn this table into absolute rules. Delegation policies, module layers, how JARs are deployed, containers/frameworks, and class loader implementations can change the details. You must measure and verify against your actual product.

## 5. Java 17+ Demo: Two Plugins with the Same Class Name, Testing Both Models

This example allows us to observe the exact **impact of the defining loader**. Two plugins have the same **`impl.Greeting`** class and implement the same `spi.Plugin` interface, yet return different results. We will test:

- A `URLClassLoader` containing only plugin A.
- A `URLClassLoader` containing only plugin B.
- A shared `URLClassLoader` containing **both A and B**, in URL order A then B.

The host only has the **SPI and application code** on its classpath. It does **not** have the plugin implementations, so parent-first delegation does not break the isolation between the two plugins.

Source/output structure:

```text
plugin-demo/
├── src/
│   ├── spi/Plugin.java
│   ├── app/PluginLoaderDemo.java
│   ├── alpha/impl/Greeting.java
│   └── beta/impl/Greeting.java
└── out/
    ├── host/
    │   ├── spi/Plugin.class
    │   └── app/PluginLoaderDemo.class
    ├── alpha/
    │   ├── impl/Greeting.class
    │   └── plugin.properties
    └── beta/
        ├── impl/Greeting.class
        └── plugin.properties
```

### 5.1. Shared SPI

**`src/spi/Plugin.java`:**

```java
package spi;

public interface Plugin {
    String id();
}
```

This class/interface must be defined by the host. Both plugins declare `implements spi.Plugin` and, due to parent delegation, use the host's exact runtime interface without bundling another copy of the API themselves.

### 5.2. Plugin A

**`src/alpha/impl/Greeting.java`:**

```java
package impl;

import spi.Plugin;

public class Greeting implements Plugin {
    @Override
    public String id() {
        return "alpha";
    }
}
```

### 5.3. Plugin B

**`src/beta/impl/Greeting.java`:**

```java
package impl;

import spi.Plugin;

public class Greeting implements Plugin {
    @Override
    public String id() {
        return "beta";
    }
}
```

Both source files have the **same package/name** but different contents. They are compiled into **two separate output directories**. If both are placed in the same compiler output directory and on an uncontrolled shared classpath, the example could overwrite the class file or fail to demonstrate the actual problem.

### 5.4. Host runner

**`src/app/PluginLoaderDemo.java`:**

```java
package app;

import spi.Plugin;
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Enumeration;
import java.util.List;

public final class PluginLoaderDemo {
    private static String id(Class<?> type) throws Exception {
        Plugin plugin = (Plugin) type
                .getDeclaredConstructor().newInstance();
        return plugin.id();
    }

    public static void main(String[] args) throws Exception {
        ClassLoader host = PluginLoaderDemo.class.getClassLoader();

        URL alpha = Path.of(args[0]).toUri().toURL();
        URL beta = Path.of(args[1]).toUri().toURL();

        try (URLClassLoader a =
                     new URLClassLoader(new URL[] {alpha}, host);
             URLClassLoader b =
                     new URLClassLoader(new URL[] {beta}, host);
             URLClassLoader shared =
                     new URLClassLoader(new URL[] {alpha, beta}, host)) {

            Class<?> typeA = a.loadClass("impl.Greeting");
            Class<?> typeB = b.loadClass("impl.Greeting");

            System.out.println("Different implementation types: "
                    + (typeA != typeB));
            System.out.println("Loader A owns A: "
                    + (typeA.getClassLoader() == a));
            System.out.println("Loader B owns B: "
                    + (typeB.getClassLoader() == b));
            System.out.println("Shared API type: "
                    + (a.loadClass("spi.Plugin")
                        == b.loadClass("spi.Plugin")));
            System.out.println("A: " + id(typeA));
            System.out.println("B: " + id(typeB));

            Class<?> sharedType =
                    shared.loadClass("impl.Greeting");
            System.out.println("Shared loader first: "
                    + id(sharedType));
            System.out.println("Shared class reused: "
                    + (sharedType
                        == shared.loadClass("impl.Greeting")));

            Enumeration<URL> urls =
                    shared.getResources("plugin.properties");
            List<String> found = new ArrayList<>();

            while (urls.hasMoreElements()) {
                try (InputStream in =
                        urls.nextElement().openStream()) {
                    found.add(new String(in.readAllBytes(),
                            StandardCharsets.UTF_8).trim());
                }
            }
            System.out.println("Shared resources: "
                    + String.join(",", found));
        }
    }
}
```

The runner class uses **Java 17 syntax/APIs**. `URLClassLoader` is a `Closeable`, so `try-with-resources` releases the resources managed by the loader when the block finishes. However, `close()` **does not force immediate class unloading**, and a loader should not be closed while the plugin still needs to load new classes/resources.

`id(Class<?>)` uses reflection to create an instance and cast it to the host's `spi.Plugin` interface. Because both A and B delegate this interface to the parent, the cast succeeds. If they were to define their own `spi.Plugin`, identity/cast or linkage errors could occur.

### 5.5. Compiling and Running

Using **Bash** from the `plugin-demo` directory:

```bash
mkdir -p out/host out/alpha out/beta

javac --release 17 -d out/host \
  src/spi/Plugin.java src/app/PluginLoaderDemo.java

javac --release 17 -cp out/host -d out/alpha \
  src/alpha/impl/Greeting.java

javac --release 17 -cp out/host -d out/beta \
  src/beta/impl/Greeting.java

printf 'alpha\n' > out/alpha/plugin.properties
printf 'beta\n' > out/beta/plugin.properties

java -cp out/host app.PluginLoaderDemo out/alpha out/beta
```

On **Windows PowerShell**, run the equivalent:

```powershell
New-Item -ItemType Directory -Force -Path out/host, out/alpha, out/beta | Out-Null
javac --release 17 -d out/host src/spi/Plugin.java src/app/PluginLoaderDemo.java
javac --release 17 -cp out/host -d out/alpha src/alpha/impl/Greeting.java
javac --release 17 -cp out/host -d out/beta src/beta/impl/Greeting.java

[System.IO.File]::WriteAllText(
    "out/alpha/plugin.properties", "alpha",
    [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText(
    "out/beta/plugin.properties", "beta",
    [System.Text.UTF8Encoding]::new($false))

java -cp out/host app.PluginLoaderDemo out/alpha out/beta
```

In PowerShell, instantiating `UTF8Encoding($false)` creates the resource **without a BOM**. On Bash, `printf` produces standard UTF-8 content for this ASCII example. The paths `out/alpha` and `out/beta` are passed as program arguments; `Path.of(...).toUri().toURL()` constructs the URLs of the two directories.

**Output verified with `javac --release 17` and JDK 24:**

```text
Different implementation types: true
Loader A owns A: true
Loader B owns B: true
Shared API type: true
A: alpha
B: beta
Shared loader first: alpha
Shared class reused: true
Shared resources: alpha,beta
```

### 5.6. Analyzing Each Result

**`Different implementation types: true`**

Loaders A and B both call `loadClass("impl.Greeting")`, but the parent does not have this class. A finds/defines the version in `out/alpha`, while B finds/defines the version in `out/beta`. `typeA != typeB` because their runtime identities have different defining loaders.

**`Loader A owns A` and `Loader B owns B`**

`getClassLoader()` confirms that the **defining loader** is indeed the corresponding plugin loader. If the parent accidentally contains `impl.Greeting`, these two lines might no longer hold true: you must check for that situation when implementing isolation.

**`Shared API type: true`**

`spi.Plugin` has only one copy in `out/host`. Parent-first delegation causes A and B to receive the same `Class<?>` object of the interface. This is the basis for the host calling `Plugin.id()` on instances from both loaders.

**`A: alpha` and `B: beta`**

Both plugins return their own expected behavior even though their implementations have the **same binary name**.

**`Shared loader first: alpha`**

The shared loader has URLs in the order `alpha` then `beta`. Both directories contain `impl/Greeting.class`. With the `URLClassLoader` configuration in the demo, the class found first is **the alpha version**. Having the beta version present does not create a second class with the same name in the shared loader.

**`Shared class reused: true`**

A subsequent call to `shared.loadClass("impl.Greeting")` returns the exact same `Class<?>` already loaded by the shared loader, rather than switching to the beta version.

**`Shared resources: alpha,beta`**

`getResources("plugin.properties")` **enumerates multiple URLs**. A loader can have **two resources with the same name** across its URL sources, even though it only defines **one class with a given binary name**. Therefore, **resource enumeration** must not be confused with **class definition selection**.

**Example limitations:** This is a parent-first case with directories on the standard JDK classpath, without a custom child-first policy, named modules, or framework-specific nested JAR URLs. `URLClassLoader` has its own rules for class/resource URLs; other containers may have different policies and lifecycles.

## 6. Sharing APIs: An Important Condition for Both Models

A plugin application should clearly separate:

```text
shared.api.*          -> host/plugins communication contracts
plugin.impl.*         -> private implementation code
plugin.private.libs.* -> plugin-specific internal dependencies
```

Example SPI:

```java
package shared.api;

public interface Plugin {
    String name();
    void start(PluginContext context);
    void stop();
}
```

This is an **illustrative interface** and cannot run standalone because it requires a matching `PluginContext`. The key point is that the **class identity** of `Plugin` and `PluginContext` must be identical wherever objects are exchanged.

When using **one loader per plugin**, having the host define the public SPI/DTOs and interfaces is the most straightforward way to guarantee the same runtime types. Plugins must **delegate** the API namespace to the parent, or the system must design an equivalent module/layer contract.

If plugin loader A defines its own `shared.api.Plugin` while the host has a different copy of `shared.api.Plugin`, a statement such as:

```java
Plugin plugin = (Plugin) instanceFromPlugin;
```

can throw a `ClassCastException`, even when both `Plugin` classes share the same package name and similar bytecode. **Having the same name does not make classes from two defining loaders the same Java type.**

With **a shared loader**, multiple implementation types can reference each other more easily, yet the shared API with the host should still be clearly demarcated to avoid having the contract version "shadowed" by a plugin JAR.

### Be Careful with Parameter and Return Types

Suppose the host API is:

```java
public interface Processor {
    shared.api.Result process(shared.api.Input input);
}
```

This is an illustrative snippet (requiring two classes in the `shared.api` package). If those method signatures were replaced with `pluginA.internal.Result` that plugin B or the host cannot load—or loads from a different loader—the code could encounter `NoClassDefFoundError`, access errors, or `LinkageError`. Keep the **cross-plugin boundary** strictly on stable public shared contracts, and avoid leaking internal implementation types into shared API signatures.

## 7. Dependency Conflicts: Different Plugin Names Are Not Enough for Isolation

Suppose plugin A uses `org.example.json.Parser v1` and plugin B uses `org.example.json.Parser v2`:

**Two separate loaders:**

```text
host (does not contain Parser)
   ├── loader A -> org.example.json.Parser v1
   └── loader B -> org.example.json.Parser v2
```

If both A and B actually define `Parser` themselves, the two versions can coexist. However, an object of v1 is not automatically compatible with the v2 type if exchanged directly across the boundary. Use shared DTOs/serialized payloads or an adapter with a clear contract.

**One shared loader:**

```text
shared loader:
    plugin-a.jar -> Parser v1
    plugin-b.jar -> Parser v2

loader.loadClass("org.example.json.Parser")
    -> one of the two definitions according to the lookup policy
```

There cannot be two runtime classes `org.example.json.Parser` v1 and v2 **both defined by the shared loader under the same binary name**. Reordering the JARs may flip which plugin fails, rather than solving the requirement for simultaneous versions.

### Can Shading/Relocation Replace Isolation?

In some projects, dependencies are **relocated** into different binary names at build time:

```text
pluginA.shadow.json.Parser
pluginB.shadow.json.Parser
```

In that case, a shared loader can define both classes because their **names are different**. However, shading must handle reflective names, `META-INF/services`, resources, native code, and related references. This is a different **build strategy**, not default plugin class-loader isolation.

### A Common Failure Point of "Two Separate Loaders"

If the host loader has dependency version v1 and both loaders A and B are **parent-first**, loader B may always receive Parser v1 from the parent even though B's URL contains v2. To actually allow B to use v2, you must design carefully:

- Do not place private dependencies that require multiple versions into the parent/shared loader.
- Place only genuinely shared **contracts** into the parent.
- Use a loader strategy/container that supports plugin-private namespaces when needed.
- Write tests that verify `Parser.class.getClassLoader()` and the actual behavior/version.

A separate loader is a **prerequisite for isolation**; it does not automatically guarantee isolation if class loading still delegates an unwanted version from the parent.

## 8. Static Fields, Singletons, and Plugin State

Static fields belong to a **runtime class**, not to a JVM-wide "class name string".

If two loaders define two copies of `plugin.State`:

```text
(loader A, plugin.State).counter = 10
(loader B, plugin.State).counter = 20
```

each copy has its **own static state**. This may be desirable for plugin caches/configs, or it may cause confusion if the author assumes `State.INSTANCE` is a JVM-wide singleton.

If A and B share **one defining loader** for `plugin.State`, the static field will be shared by both. In that case, the code must design synchronization, tenant isolation, and lifecycle management for the shared state.

An important note: **statics in classes defined by the parent are shared regardless of whether plugin loaders are separate**. If a logging library, global registry, or shared API holds a static cache in the parent, both A and B can still affect that same state.

### You Cannot Remove an "Old Static Singleton" Simply by Replacing the JAR

Once `plugin.State` has been defined in a loader and used, replacing the bytes on disk **does not alter the existing runtime class definition**. With a per-plugin loader, you can create a **new** loader for the new plugin generation, but references to the old loader must be cleaned up. With a shared loader, replacing a plugin with the same name usually requires creating a **new loader for the group**, affecting the remaining plugins.

## 9. Resources, Configuration, and ServiceLoader

Plugin JARs contain more than just bytecode:

```text
plugin-a.jar:
  impl/Greeting.class
  plugin.properties
  META-INF/services/spi.Plugin

plugin-b.jar:
  impl/Greeting.class
  plugin.properties
  META-INF/services/spi.Plugin
```

**When each plugin has its own loader:** code can use loader A to retrieve A's `plugin.properties` and loader B for B's. However, the default **parent delegation** of `getResource` usually prioritizes a resource in the parent if one has the same name. If a plugin requires child-first resources, you must properly control the lookup policy or namespace resources per plugin to avoid collisions.

**When using a shared loader:** `getResource("plugin.properties")` typically returns **the first single URL**, whereas `getResources("plugin.properties")` can return **multiple URLs**. Do not design plugin B to read "B's file" via a shared `getResource` call and assume the loader knows which plugin is calling.

### SPI and ServiceLoader

With classpath SPI, the provider descriptor:

```text
META-INF/services/spi.Plugin
```

contains the binary names of provider implementations, for example:

```text
plugins.alpha.AlphaPlugin
plugins.beta.BetaPlugin
```

This is an example of metadata, not runnable code from the Section 5 demo; in the Section 5 demo, there are **two implementations with the same binary name `impl.Greeting`** to demonstrate class collision.

`ServiceLoader.load(Plugin.class, pluginLoader)` uses **the passed-in loader**. `ServiceLoader.load(Plugin.class)` uses the **thread context class loader (TCCL)** per the Java SE 17 API. This affects how the plugin manager selects the set of providers.

- **One loader per plugin:** load service providers through the corresponding loader, and verify that the SPI type is defined by the parent and that the descriptor resides in the plugin.
- **Shared loader:** service discovery can aggregate multiple providers; providers must be distinguished by metadata/ID rather than relying strictly on order if the contract does not guarantee it.
- If two descriptors both point to the **same provider binary name** while there is only **one shared loader**, the name is resolved within that namespace and does not produce two separate provider implementations corresponding to the two JARs.
- With named modules, `ServiceLoader` also supports `provides ... with ...` in `module-info.java` and discovery via `ModuleLayer`, rather than relying solely on `META-INF/services`.

## 10. TCCL, Thread Pools, and Async Tasks

The TCCL belongs to a **thread** and is used by `ServiceLoader.load(serviceType)` and certain frameworks for discovery; it does not change a class's defining loader or automatically propagate into an already-existing worker pool. Inside a plugin callback/task, if the TCCL is needed, set the appropriate plugin loader **on the executing worker thread** and restore the previous context in a `finally` block. Prefer `ServiceLoader.load(serviceType, pluginLoader)` when there is an explicit owner. Forgetting to restore causes incorrect provider lookups and retains the old loader after a reload.

## 11. Reload/Unload: A Separate Loader Does Not Guarantee GC

A separate loader enables replacing **one plugin generation** independently, but only after stopping new incoming work, draining requests/tasks, unregistering listeners, closing resources, and dropping host references. Create a **new loader** for the same binary names; do not use `close()` or swap JARs to redefine classes in the old loader. A shared loader couples the lifecycle of the entire group: replacing a single already-defined class typically requires creating a new namespace/loader for the group or changing the partitioning boundary. The JVM/GC makes no promise about when unloading will occur.

## 12. Intermediate Models: Grouped Loaders or a Shared Library Loader

The two extremes—"one loader per plugin" and "one loader shared by all plugins"—are not the only choices.

For example:

```text
Application Host Loader
    └── shared.api.*
          ^
          |
Common Plugin API/Library Loader
    ├── stable.shared.lib.*
    ├── contracts.*
    ^
    | parent
    +-----------+-----------+
    |                       |
PluginGroupLoader-X     PluginGroupLoader-Y
    |                       |
    +--> A, B                +--> C, D
```

A group of plugins can share a single loader when **they share lifecycle management and dependencies**, while other groups have their own loaders. Alternatively, there can be a base loader containing stable shared libraries with each plugin loader acting as a child.

Important points to understand:

- If a private dependency is pushed up into the parent **too early**, parent-first children will not automatically get their own separate versions.
- A shared library loader can save resources, yet it turns **shared dependency definitions into version constraints** across plugins.
- A one-way parent-child tree does not automatically support all cross-dependencies A→B. Enabling plugins to call each other's APIs may require a **shared contract loader**, a registry/service bus, or explicit loader delegation.
- Avoid loader graphs with dependency cycles that lead to class-loading recursion or deadlock. `ClassCircularityError` and `LinkageError` can also appear in situations involving class resolution/constraints.

An intermediate model should be designed around the **dependency graph and lifecycle domains**, not merely the number of JAR files.

## 13. JPMS, ModuleLayer, and Plugin Loaders

Java 9+ provides the **Java Platform Module System (JPMS)**:

- `Module` identifies a runtime module and its access rules.
- `ModuleLayer` organizes the modules resolved within a configuration.
- `ClassLoader` performs class loading/defining and can be associated with one or more modules.

For plugins packaged as **named modules**:

- `ModuleLayer.defineModulesWithOneLoader(...)`: creates a layer in which the modules are defined for a single created loader.
- `ModuleLayer.defineModulesWithManyLoaders(...)`: creates a layer with one loader per module in the configuration.
- You can use custom module-to-loader mapping under your control when you have specific requirements and understand the `defineModules` mechanism.

These APIs differ from simply creating multiple `URLClassLoader` instances from plain JARs. **A module is not synonymous with a plugin**: a single plugin can consist of multiple modules, and a single module can contain multiple components. Choose between one or many loaders in `ModuleLayer` based on module resolution, visibility, and lifecycle needs rather than treating one method as an automatic answer.

**Important limitations:**

- `exports` and `opens` determine the accessibility of code, resources, and reflective access for named modules; they are not bypassed simply by sharing the same class loader.
- Split packages across modules in the same loader may be subject to JPMS constraints.
- Service providers can be registered using `provides ... with ...` in the module descriptor.
- `ModuleLayer` does not automatically guarantee that a plugin is completely independent or unloaded when no longer needed; similar lifecycle and reference issues still apply.

If a plugin architecture already uses named modules, design a dedicated **ModuleLayer/plugin manager** rather than merely stacking JAR URLs and expecting JPMS to infer all relationships.

## 14. When Child-First Is Needed Instead of Parent-First URLClassLoader

A standard `URLClassLoader` inherits the **parent-first** policy. In cases A and B of the demo, the parent did not contain `impl.Greeting`, so isolation worked. However, if the parent contains the same binary name or dependencies requiring separate versions, child-first may be required for the **private namespace**.

A design outline:

```text
loadClass(name):
    lock with getClassLoadingLock(name)
    if already loaded -> return result
    if name is JDK or shared.api -> delegate to parent first
    if name is plugin-private:
         try child's findClass
         if ClassNotFoundException -> fall back to parent per policy
    other names -> parent-first
    resolve when needed
```

This is **pseudocode**, not a runnable Java method. When overriding `loadClass` yourself, you must check:

1. `findLoadedClass` and locking to avoid duplicate class definitions.
2. `resolveClass` according to the `resolve` parameter when needed.
3. Do not attempt to define `java.*` from a custom loader; `defineClass` enforces namespace restrictions.
4. Do not duplicate shared SPI/DTO contracts between parent and child.
5. Do not catch/swallow `VerifyError`, `LinkageError`, or `SecurityException` as "not found" errors.
6. The `getResource` and `getResources` resource policies must align with the class policy where necessary.
7. Java package sealing, CodeSource, certificates, module access, and native resources can affect the actual loader behavior.

**If your plugins only need to read JARs/directories and the parent does not contain private classes**, start with a standard `URLClassLoader`. A hand-rolled custom child-first loader is not the default choice.

## 15. Security and Fault Isolation Issues

Both a per-plugin loader and a shared loader execute bytecode inside the same JVM, sharing process permissions as well as CPU/RAM/OS resources. If the threat model includes untrusted plugins or requires a hard stop, a process/OS sandbox and clear protocols are needed; a ClassLoader only isolates runtime types/dependencies.

## 16. Observations and Measurements When Deciding

To make an informed choice, test realistic workloads and measure:

| Observation | One Loader/Plugin May Be Better When | A Shared Loader May Be Better When |
|---|---|---|
| Class metadata size, metaspace | Plugins share little duplicate code or isolation is more important | Plugins share many dependencies, saving duplicate metadata |
| Startup/load latency | Plugins are independent and lazily loaded on demand | The whole group always runs concurrently, caching shared classes |
| Changing dependency versions | Multiple libraries have the same binary name with different versions | A unified BOM/dependency lock is in place |
| Independent deploy/reload | A and B have separate release cadences | The group deploys atomically |
| Direct object sharing | Most communication goes through public SPIs/DTOs | Plugins intentionally share many implementation internals |
| Debugging | Good tooling exists to log loader/class origins | Fewer namespaces, though class shadowing must be handled |
| Plugin failures | Separate stop/cleanup procedures exist | A failure/coupling can affect the shared group |

There is no guarantee that "one loader per plugin is always faster" or "one loader always uses less memory" for every system. Measure the **actual number of loaded classes**, metaspace, heap retained references, runtime behavior, latency, and specific dependencies instead of using the JAR count as a proxy.

### Minimal Diagnostic Logging

In code where a `Class<?> type` object is already available:

```java
System.out.println("name=" + type.getName());
System.out.println("loader=" + type.getClassLoader());
System.out.println("module=" + type.getModule());
System.out.println("package=" + type.getPackageName());
```

This is an illustrative snippet inside a method, not a standalone program. Do not compare loaders by the name printed from `toString()`; if you need definitive identity checks, use `==` on the `ClassLoader` or `Class<?>` object within the same JVM.

You can add module/code-source/version metadata if appropriate; do not infer a reliable source class file solely from a resource URL if the loader performs bytecode transformation.

## 17. Common Scenarios and Suggested Choices

### Scenario 1: An IDE/Editor Allowing Third-Party Plugin Installation

Plugins have different lifecycles/versions, potential dependency conflicts, and need to unload when the user disables a plugin. **Prefer one loader per plugin or independent lifecycle groups**, with the parent holding the public SPI. If the code is untrusted, additional process/permission isolation is required.

### Scenario 2: 20 "Plugins" That Are Effectively Feature Modules of the Same Product

All are released in lockstep, share a dependency lock, and are never hot-swapped individually. **A shared loader** or JPMS layer/module grouping can be simple, provided binary name collisions have been checked.

### Scenario 3: Two Plugins Both Using a JSON Library at Different Versions

If both versions are needed simultaneously, **separate the defining loaders for the private library** or relocate the dependencies with thorough testing. Do not place one private copy of the JSON parser into the parent and expect a parent-first child to select a different copy.

### Scenario 4: Plugin A Must Call a Service in Plugin B

Do not exchange `b.internal.Foo` directly across the boundary if it can be avoided. Provide a **shared SPI/DTO** and a registry/service locator managing endpoints/versions, with the host mediating A↔B. If calling private classes directly is necessary, a shared loader or an intentional layer/module graph is more suitable, at the cost of reduced isolation.

### Scenario 5: Upgrading a Plugin While the Host Is Still Running

A **per-plugin loader + new generation** allows replacing an individual plugin's code at the class-identity level, provided the old plugin is quiesced/cleaned up and has no remaining live references. With a shared loader, replacing the same binary name for one plugin usually forces building a new namespace for the entire group.

### Scenario 6: Multiple Providers for the Same SPI with Duplicate Class Names

The service descriptors of both A and B declare `impl.Greeting`. A shared loader cannot inherently distinguish "`impl.Greeting` in A" from "the one in B"; change the provider binary names, use separate loaders, or maintain a plugin-specific mapping. ServiceLoader is a discovery mechanism; **it does not resolve class identity collisions** for you.

## 18. Pre-Implementation Decision Checklist

- [ ] Do plugins require **multiple versions of the same binary class name**?
- [ ] Do plugins need to be **deployed/reloaded/unloaded independently**?
- [ ] Do the shared API/SPI and DTOs already have **one common defining loader**?
- [ ] Does the parent loader accidentally contain private libraries that render child isolation ineffective?
- [ ] Are there multiple `META-INF/services` or config/templates with colliding resource names?
- [ ] Is the TCCL of the plugin execution thread set and reset at the right times?
- [ ] Do cross-plugin method signatures expose any private classes?
- [ ] Are JPMS `ModuleLayer`, named modules, or qualified exports/opens needed?
- [ ] Have duplicate classes/metaspace and overhead actually been measured rather than guessed?
- [ ] Are listeners/ThreadLocal/executors/ServiceLoader caches/native registrations managed for unloading?
- [ ] Is there an actual conflict test: **the same binary name** in two plugins with different behavior?
- [ ] If plugin code is untrusted, is there isolation/security **beyond the class loader**?

**A sensible starting workflow:** Place contracts in the host loader; build a pilot with two plugins having colliding dependency names; use a simple `URLClassLoader` for the children; test loader identities, type casting, resource discovery, and lifecycle. Only develop advanced custom delegation/ModuleLayer logic when the pilot proves it necessary.

## 19. Self-Check Questions

**1. Two plugins both declare `impl.Greeting`, but each plugin has a different defining loader. Are these the same runtime type?** No. Class identity also depends on the defining loader.

**2. Can a shared loader simultaneously `defineClass` two different versions of `impl.Greeting`?** Not within the same defining loader. One binary name corresponds to one runtime class for that loader.

**3. Having two separate URLClassLoader instances, are dependencies A v1 and B v2 guaranteed to be isolated?** Not yet. If the parent contains the same class name, parent-first delegation can cause both to use the parent's copy.

**4. Can two plugins with separate loaders both implement an SPI interface defined by the parent?** Yes. This is a common design; the plugin implementation types differ, while the shared SPI type is the same.

**5. Does loading two plugins via the same loader mean there is only one instance?** No. Multiple instances can still be created from one or more runtime classes. Only the static fields of the same runtime class are shared.

**6. Why can `getResources` return two configuration files while `loadClass` only selects one definition?** Resource enumeration can return multiple URLs, whereas a defining loader can only have one runtime class per binary name.

**7. Does `URLClassLoader.close()` make the JVM immediately unload plugin classes?** No. Class unloading depends on references, GC, and the runtime lifecycle.

**8. Does using ServiceLoader automatically resolve version conflicts or duplicate provider class names?** No. ServiceLoader discovers providers but still follows class loader/module type identity rules.

**9. If two plugins must hot-reload independently, which model is more favorable?** Usually a per-plugin loader, with quiescing/cleanup and a clear API boundary. Immediate unloading is still not guaranteed.

**10. If plugin code is untrusted, is a separate loader sufficient for security?** No. Additional process/container/OS isolation and appropriate secure execution measures are required.

**11. Can using a shared loader save metaspace?** Possibly when sharing many classes/dependencies, though you need to measure the workload; it is not guaranteed to be better in all cases.

**12. Does adopting JPMS mean each module automatically gets its own loader?** No. ModuleLayer has strategies for mapping module→loader; modules and loaders are two different kinds of runtime entities.

## 20. Authoritative References for Further Reading

- Java SE 17 API, `ClassLoader` — defining/initiating loaders, parent delegation, `loadClass`, `defineClass`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 API, `URLClassLoader` — class/resource lookup from URLs and `close()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- Java SE 17 API, `ServiceLoader` — service providers, classpath descriptors, and named modules: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Java SE 17 API, `ModuleLayer` — `defineModulesWithOneLoader` and `defineModulesWithManyLoaders`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- Java Virtual Machine Specification `5.3, *Creation of Classes and Interfaces*, runtime identity and defining loader: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- Java SE 17 API, `Thread` — TCCL: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html

**Remember:** **One loader per plugin** prioritizes independence in namespaces, dependency versions, and lifecycles; **multiple plugins sharing one loader** prioritizes sharing classes/static state and synchronized deployment. Whichever model you choose, keep **shared contracts consistently defined**, verify actual delegation behavior, understand the limits of service/resource lookup, and explicitly manage plugin lifecycles.
