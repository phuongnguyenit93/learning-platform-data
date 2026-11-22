# Isolating Multiple Library Versions Between Plugins with ClassLoader

## 1. The Problem: Two Plugins Need Two Versions of a Library with the Same Class Name

Suppose a host application runs two plugins:

- **Plugin A** is compiled with version 1 of the `lib.Versioned` library, whose `value()` method returns `"v1:legacy"`.
- **Plugin B** is compiled with version 2 of the `lib.Versioned` library, whose `value()` method returns `"v2:modern"`.
- Both implement the `api.Plugin` interface provided by the host.

If all classes are loaded by a single application class loader, the same binary name `lib.Versioned` cannot simultaneously represent **two different class definitions within that same loader**. One version may end up being used instead of the other; plugins may produce wrong results or encounter `NoSuchMethodError`/`LinkageError` when APIs are incompatible.

Java allows isolating runtime classes using separate class loaders:

```text
                       Host / Application loader
                       └── api.Plugin (shared API)
                          /                    \
                         /                      \
                Plugin loader A            Plugin loader B
                ├── plugin.Implementation   ├── plugin.Implementation
                └── lib.Versioned (v1)      └── lib.Versioned (v2)
```

In this example, the two `lib.Versioned` classes have **the same binary name but different defining class loaders**, so they are two distinct runtime types. Conversely, both implementations use the **same** `api.Plugin` defined in the common loader. This is the core model of **version isolation** in a plugin system.

**The goal is not to force everything to be separate.** You need to isolate *implementations and dependent libraries with different versions*, while **stably sharing the interfaces/DTOs/contracts that cross the host–plugin boundary**.

## 2. JVM Foundation: The Same Class Name Alone Does Not Make the Same Type

According to the JVMS, a runtime class/interface is identified by:

**Binary name + defining class loader**

For example:

```text
("lib.Versioned", loaderA) != ("lib.Versioned", loaderB)
("api.Plugin",    appLoader) == ("api.Plugin",    appLoader)
```

This means:

- `Class<?> versionA = loaderA.loadClass("lib.Versioned")` and `versionB = loaderB.loadClass("lib.Versioned")` can have the same `getName()`.
- If they are actually defined separately by loaderA and loaderB, `versionA == versionB` is `false`.
- An object belonging to loaderA's `lib.Versioned` cannot simply be cast to loaderB's `lib.Versioned`.
- The static fields of these two runtime classes are independent; a singleton using a static field in the library can be **one singleton per defining loader**, not a JVM-wide singleton.
- A third loader can delegate to one of the two loaders and receive the parent's exact `Class<?>`, rather than automatically creating a copy.

The **defining loader** is the one that actually defines the class; the **initiating loader** is the loader recorded by the JVM as having initiated the request to load/resolve that class. `clazz.getClassLoader()` reflects the defining loader for ordinary classes, rather than simply returning the object on which `loadClass` was most recently called.

### Why Can Identical Bytes Still Result in Two Types?

Even if two plugins contain byte-for-byte identical class files, when two different loaders actually define the same binary name, the JVM still creates **two class identities**. Class loading is part of the Java type system, not merely a file lookup mechanism.

Conversely, two loaders with the same name (equal `getName()`) can still be two different objects/defining loaders. A loader name is a diagnostic label, not an identifying key for runtime classes.

## 3. What Is a Shared API, and What Is a Private Dependency?

Decide on the architecture before choosing parent delegation:

| Class Group | Where It Should Normally Be Defined | Reason |
|---|---|---|
| `java.lang.*`, core JVM libraries | Appropriate built-in loaders | Plugins share the runtime platform |
| `api.Plugin` and DTOs/interfaces used across the host boundary | The host's shared API loader | Host and plugins need **the same runtime type identity** |
| `plugin.Implementation` | The corresponding plugin loader | Can have the same binary name across multiple plugins while remaining isolated |
| `lib.Versioned` version 1 | Plugin A loader | Independent of version 2 |
| `lib.Versioned` version 2 | Plugin B loader | Independent of version 1 |
| Libraries that are truly shared and compatible | Common parent loader if the version is agreed upon | Reduces duplicates and avoids classloader leaks |
| Private libraries or those at risk of version conflicts | Each plugin's own loader | Allows different versions to coexist |

Example of a safe API across the boundary:

```java
package api;

public interface Plugin {
    String run();
}
```

The `String run()` signature uses the platform type `java.lang.String` unified by the runtime, without forcing the host to understand whether `lib.Versioned` belongs to plugin A or B.

**The host's shared API should not have return types or parameters from a plugin's private library**, for example:

```java
// Avoid this kind of design in the shared API:
lib.Versioned run();
```

This is an illustrative declaration, not a standalone program. If the host and plugin resolve `lib.Versioned` through two loaders with different definitions, the JVM may encounter a **loading constraint violation** on the field/method descriptor during linking, or the host will lack the right class needed to compile/run.

Instead, pass **shared interfaces/DTOs**, primitives/Strings, or data converted at the boundary such as JSON/byte arrays with clear schema/versioning across the boundary. Converting data does not automatically make all API versions compatible: schema and behavior still need to be managed.

## 4. Parent-First Is Sometimes Already Enough to Isolate Two Libraries

`URLClassLoader` inherits the default `loadClass` strategy: typically **parent-first**. When a child loader needs a class name, it checks whether the class is already loaded, asks its parent, and only searches its own URLs if the parent cannot find it.

Different versions of libraries can be isolated using **two separate URLClassLoader objects** **without overriding `loadClass`**, provided that:

1. The **parent's class path does not contain** private classes such as `lib.Versioned`.
2. Each plugin loader has its own path containing the corresponding library version.
3. The shared API `api.Plugin` is defined by the parent and delegated to the same definition by the plugin loaders.

```text
Parent (classpath: out/api + out/host)
     without lib.Versioned
          |                         |
          v                         v
Plugin A URLClassLoader      Plugin B URLClassLoader
  out/plugin-a/                out/plugin-b/
  lib.Versioned v1             lib.Versioned v2

Request for lib.Versioned:
  A -> parent does not have it -> A defines v1 itself
  B -> parent does not have it -> B defines v2 itself

Request for api.Plugin:
  A -> parent returns shared API
  B -> parent returns shared API
```

**This is usually the most maintainable starting point**: isolate a separate class path for each plugin without complicating the class-loading algorithm unless necessary.

### When Is Parent-First Not Enough?

If the host application class path already contains version 1 of `lib.Versioned`, the parent of both plugins may return version 1 **before** plugin B has a chance to look up version 2 in its own directory.

Consequences:

- Plugin B may run with v1's behavior instead of v2's.
- If B was compiled to call a method that only exists in v2, yet receives v1 at runtime, it may encounter a `NoSuchMethodError` when the symbolic reference is resolved.
- The failure does not depend on whether plugin B has the v2 file in its JAR: **the parent already returned the class with the same name first**.

Preferred solution: **do not place private, versioned libraries on the parent's class path**. If the architecture forces the parent to contain a conflicting library, **selective child-first** may be needed for private namespaces; you should not arbitrarily invert the order for all packages.

## 5. Runnable Java 17 Demo: Two Versions, Two URLClassLoaders, One Shared API

The demo uses two versions of a class **with the same binary name `lib.Versioned`** but different source/bytecode. They are compiled into **two separate output directories**, then loaded by two loader objects. The host only sees the shared API.

### 5.1. Source File Structure

Create the directory tree:

```text
src/
  api/
    Plugin.java
  plugin-a/
    lib/
      Versioned.java
    plugin/
      Implementation.java
  plugin-b/
    lib/
      Versioned.java
    plugin/
      Implementation.java
  host/
    PluginHost.java
```

**File `src/api/Plugin.java`:**

```java
package api;

public interface Plugin {
    String run();
}
```

**File `src/plugin-a/lib/Versioned.java`:**

```java
package lib;

public final class Versioned {
    public String value() {
        return "v1:legacy";
    }
}
```

**File `src/plugin-a/plugin/Implementation.java`:**

```java
package plugin;

import api.Plugin;
import lib.Versioned;

public final class Implementation implements Plugin {
    @Override
    public String run() {
        return new Versioned().value();
    }
}
```

**File `src/plugin-b/lib/Versioned.java`:**

```java
package lib;

public final class Versioned {
    public String value() {
        return "v2:modern";
    }
}
```

**File `src/plugin-b/plugin/Implementation.java`:**

```java
package plugin;

import api.Plugin;
import lib.Versioned;

public final class Implementation implements Plugin {
    @Override
    public String run() {
        return new Versioned().value();
    }
}
```

Note that both pairs of `lib.Versioned` and `plugin.Implementation` have **the same package + class name**, yet are compiled separately for the two plugins. The shared interface `api.Plugin` has only **one** common source/output.

### 5.2. The Host Explicitly Selects Loaders

**File `src/host/PluginHost.java`:**

```java
package host;

import api.Plugin;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class PluginHost {
    private static URL pluginUrl(String directory)
            throws Exception {
        return Path.of(directory).toUri().toURL();
    }

    private static Plugin create(URLClassLoader loader)
            throws Exception {
        Class<?> implementation =
                Class.forName("plugin.Implementation", true, loader);
        Object instance =
                implementation.getDeclaredConstructor().newInstance();
        return (Plugin) instance;
    }

    public static void main(String[] args) throws Exception {
        ClassLoader shared = Plugin.class.getClassLoader();

        try (URLClassLoader loaderA = new URLClassLoader(
                        new URL[]{pluginUrl("out/plugin-a")}, shared);
             URLClassLoader loaderB = new URLClassLoader(
                        new URL[]{pluginUrl("out/plugin-b")}, shared)) {

            Plugin a = create(loaderA);
            Plugin b = create(loaderB);

            Class<?> libA = loaderA.loadClass("lib.Versioned");
            Class<?> libB = loaderB.loadClass("lib.Versioned");

            System.out.println("Plugin A: " + a.run());
            System.out.println("Plugin B: " + b.run());

            System.out.println("Libraries have same name: "
                    + libA.getName().equals(libB.getName()));
            System.out.println("Libraries have different identity: "
                    + (libA != libB));
            System.out.println("Plugin types have different identity: "
                    + (a.getClass() != b.getClass()));

            System.out.println("A library defined by A: "
                    + (libA.getClassLoader() == loaderA));
            System.out.println("B library defined by B: "
                    + (libB.getClassLoader() == loaderB));

            System.out.println("Both share API: "
                    + (a.getClass().getInterfaces()[0] == Plugin.class
                       && b.getClass().getInterfaces()[0] == Plugin.class));
        }
    }
}
```

Design explanation:

- `shared` is the defining loader of `api.Plugin` on the normal class path. Both plugin loaders receive it as their **parent**.
- `URLClassLoader` is configured with the separate directory that already contains the plugin's class files. The URL points to the **directory**, not to each individual `.class` file.
- The host **does not put `out/plugin-a` or `out/plugin-b` onto the application class path itself**, so the parent does not automatically see the private `lib.Versioned` and `plugin.Implementation`.
- `Class.forName(..., true, loader)` selects the right plugin loader and requests initialization of the implementation, and then reflection instantiates the object via the implicit public zero-arg constructor.
- Both objects implement the parent's `api.Plugin` interface; the cast in `create` is valid. If a copy of the API is accidentally packaged and child-first loading is used for the `api.*` namespace, this cast may be invalid.
- The `try-with-resources` block closes the `URLClassLoader` at the end of the scope; closing it **does not automatically make the JVM unload all classes immediately**.

### 5.3. Compiling the Two Versions Separately

From the root directory containing `src`, run in sequence:

```bash
mkdir -p out/api out/plugin-a out/plugin-b out/host

javac -d out/api src/api/Plugin.java

javac -cp out/api -d out/plugin-a \
  src/plugin-a/lib/Versioned.java \
  src/plugin-a/plugin/Implementation.java

javac -cp out/api -d out/plugin-b \
  src/plugin-b/lib/Versioned.java \
  src/plugin-b/plugin/Implementation.java

javac -cp out/api -d out/host src/host/PluginHost.java

java -cp "out/api:out/host" host.PluginHost
```

For **Windows PowerShell**, use the `;` class path separator, and write the commands on a single line:

```powershell
New-Item -ItemType Directory -Force out/api,out/plugin-a,out/plugin-b,out/host

javac -d out/api src/api/Plugin.java

javac -cp out/api -d out/plugin-a src/plugin-a/lib/Versioned.java src/plugin-a/plugin/Implementation.java

javac -cp out/api -d out/plugin-b src/plugin-b/lib/Versioned.java src/plugin-b/plugin/Implementation.java

javac -cp out/api -d out/host src/host/PluginHost.java

java -cp "out/api;out/host" host.PluginHost
```

**Important:** The `java` command puts **only** `out/api` and `out/host` on the application class path. If you add `out/plugin-a` to the host's class path, the parent may find v1 early and defeat the purpose of the test.

### 5.4. Expected Stdout

With JDK 17+ and a clean structure like the one above:

```text
Plugin A: v1:legacy
Plugin B: v2:modern
Libraries have same name: true
Libraries have different identity: true
Plugin types have different identity: true
A library defined by A: true
B library defined by B: true
Both share API: true
```

**Analysis:**

1. Both `Versioned.value()` methods exist under the same class name, yet return two different behavioral versions. This is evidence that each plugin uses its own class.
2. `libA.getName().equals(libB.getName())` is `true` because the two classes have equal binary names.
3. `libA != libB` is `true` because runtime identity differs by defining loader. That is precisely the isolation the application needs.
4. `a.getClass() != b.getClass()` is `true`: implementations with the same binary name are also loaded separately.
5. `libA.getClassLoader() == loaderA` and `libB.getClassLoader() == loaderB` prove which loader **defines** each of the two libraries.
6. Both implementation classes implement the exact `api.Plugin` from the common loader; the result `Both share API: true` shows that the boundary is valid.

The example intentionally does **not** use a static final compile-time constant to represent the version, because the Java compiler could inline such constant values and cause the output to no longer prove where the `lib.Versioned` class was loaded from.

## 6. When Selective Child-First Is Needed for Private Libraries

On many platforms, the host or a dependency of the host has already placed `lib.Versioned` on the parent class path. Parent-first then causes plugin B to receive the version from the parent, even though it has its own JAR.

One approach is to use **child-first only for private packages**. For packages such as `java.*`, the shared API `api.*`, logging contracts, and host communication types, the parent still takes priority.

Illustrative code skeleton:

```java
import java.net.URL;
import java.net.URLClassLoader;

public class SelectivePluginLoader extends URLClassLoader {
    public SelectivePluginLoader(String name, URL[] urls,
                                 ClassLoader parent) {
        super(name, urls, parent);
    }

    @Override
    protected Class<?> loadClass(String name, boolean resolve)
            throws ClassNotFoundException {
        if (!name.startsWith("lib.privatecopy.")) {
            return super.loadClass(name, resolve);
        }

        synchronized (getClassLoadingLock(name)) {
            Class<?> c = findLoadedClass(name);
            if (c == null) {
                try {
                    c = findClass(name); // prioritize plugin URL
                } catch (ClassNotFoundException missingLocally) {
                    c = super.loadClass(name, false); // can fall back
                }
            }

            if (resolve) {
                resolveClass(c);
            }
            return c;
        }
    }
}
```

This is **a compilable class in `SelectivePluginLoader.java`**, but it is only a policy template and does not replace the example in section 5. The prefix `lib.privatecopy.` must be changed to match the namespace owned by the plugin; the demo example uses `lib.Versioned`, so if you want to apply it to the demo, you must adjust the package condition accordingly and manage related dependent classes as well.

Very important notes:

- Always use `findLoadedClass` under `getClassLoadingLock(name)` before searching/defining on your own; avoid repeated `defineClass` attempts in the same loader.
- Do not apply child-first indiscriminately to `java.*`, `javax.*`, or the shared API `api.*`.
- **Parent fallback** can break strict isolation if a private dependency is missing from the plugin while the parent has a different version. In architectures requiring absolute version isolation, you may choose **no fallback** for private namespaces.
- An overly broad package prefix can accidentally isolate SPI interfaces/DTOs that the host needs to share.
- Many classes in the same library reference one another; isolating only a single class in a multi-class library is usually **not enough**. Consider the entire dependency graph/transitive dependencies.
- Class-loader constraints, package sealing, JPMS boundaries, and access rules still apply.
- If a library uses resource lookups, native code, or the context class loader, changing the class lookup order does not guarantee that all dependencies/resources will also resolve to the right version.

**Recommendation:** before overriding `loadClass`, try the simpler approach: keep private versioned libs **off the parent class path** and provide them separately to each `URLClassLoader`. Override only when there is a clear reason and a class identity test suite.

## 7. When Is Version Isolation No Longer a Safe Boundary?

Version isolation works well when the private library **stays inside the plugin**, without exposing objects of the plugin's own runtime classes across the shared host boundary.

### Mistake: Returning a Private Library Object Directly

Consider the host API:

```java
// Illustrates an API that introduces a dependency on a private lib:
package api;

public interface Converter {
    lib.Versioned convert(lib.Versioned input);
}
```

This snippet is not a safe plugin design. When the host defines `Converter`, it needs to know `lib.Versioned` in the signature. If a plugin uses a different version of `lib.Versioned`, resolving field/method descriptors or method overrides can cause a **loading constraint violation** and `LinkageError`.

### A Better Model

```java
package api;

public interface Converter {
    String convert(String input);
}
```

Keep the private library inside the implementation:

```java
package plugin;

public class ConverterImpl implements api.Converter {
    @Override
    public String convert(String input) {
        // Perform the conversion using the versioned library visible only to this plugin.
        return input.trim();
    }
}
```

These two blocks are **separate files that must be placed according to their packages**, not a single-file program. `ConverterImpl` only illustrates the boundary and does not by itself demonstrate using a specific library. The idea is that the contract uses shared types understood consistently by all sides.

For complex payloads, you can use a DTO defined by the common loader, a serialization API with an explicit schema, or an adapter interface provided by the host. However, JSON/serialization also has its own versioning/compatibility issues; it is not a test-free solution.

## 8. Parent-First, Child-First, and Class Identity Comparison Table

| Design | Can Private Libraries Use Separate Versions? | Risks |
|---|---|---|
| One application class loader for all plugins | Usually **no**, if different versions share the same binary name | Version conflict, `NoSuchMethodError` |
| One `URLClassLoader` per plugin, parent has no private lib | **Yes**, parent-first is usually sufficient | Class/resource lookup paths must be right |
| One loader per plugin, parent already has private lib, parent-first | Usually shadowed by the parent's version | Silent wrong version or linkage error |
| Selective child-first for private namespaces | **Possible**, if prefixes and transitive deps are controlled | Duplicate shared types, package/resource bugs |
| Child-first for all packages, including shared API | Not a safe design | `ClassCastException`/`LinkageError`, package rule violations |
| Shading/relocation renaming packages/binary names for dependencies | Can run multiple versions in the same loader | Complex build process; resource/reflection/service metadata must be updated |
| Running each plugin in a separate process/JVM | Stronger isolation than class loaders | IPC/deployment overhead and protocol compatibility |

**Shading/relocation** is another option: changing the binary name (for example from `lib.Versioned` to `pluginA.shaded.lib.Versioned`) in the build artifact to eliminate name collisions. It is not synonymous with classloader isolation and requires build tooling to handle reflection, serialized names, and service files/resource references accordingly.

**Multiple processes/JVMs** are often more suitable when safety isolation or fault containment is required. Classloader isolation **is not a security sandbox** and does not completely isolate native state, process-wide system properties, static state of shared classes, or shared threads.

## 9. ServiceLoader, TCCL, and Per-Plugin Providers

In a multi-version plugin system, host code can use `ServiceLoader` to discover implementations of the shared interface `api.Plugin`.

API:

```java
java.util.ServiceLoader<api.Plugin> providers =
        java.util.ServiceLoader.load(api.Plugin.class, pluginLoader);
```

In this snippet, `pluginLoader` should be the loader of the plugin the host wants to search. This is an **explicit loader**, avoiding reliance on `Thread.currentThread().getContextClassLoader()` when the host runs on a worker pool.

You can add a resource file inside **each plugin directory**:

```text
out/plugin-a/META-INF/services/api.Plugin
out/plugin-b/META-INF/services/api.Plugin
```

Each file contains a single line:

```text
plugin.Implementation
```

Then `ServiceLoader.load(api.Plugin.class, loaderA)` can find A's provider; similarly loaderB for B. The shared `api.Plugin` must be provided by the parent so that the provider is assignable to the host.

**Warning:** The single-argument `ServiceLoader.load(api.Plugin.class)` overload uses **the current thread's TCCL**. In a thread pool, the TCCL may point to another plugin or a loader set by the container. If you already know the loader of the plugin to query, pass it explicitly.

Do not automatically assume that `ServiceLoader` only scans the child's resources: the resource lookup mechanism can follow parent and layer behavior. If the parent also advertises a provider, providers known to the parent may also appear. To strictly control provider scope, design a dedicated discovery mechanism or an appropriate classloader/resource policy, and test it in practice.

### TCCL Can Easily Cause Classloader Leaks

If a host thread pool retains `pluginLoader` via `Thread.setContextClassLoader(pluginLoader)` and fails to restore it, that loader may not be garbage-collected even after logical plugin unloading.

Safe pattern when a framework requires using the TCCL:

```java
Thread worker = Thread.currentThread();
ClassLoader before = worker.getContextClassLoader();
try {
    worker.setContextClassLoader(pluginLoader);
    // Perform the SPI/framework call that uses the TCCL.
} finally {
    worker.setContextClassLoader(before);
}
```

This is illustrative code that requires `pluginLoader` in scope. Setting and restoring it must happen on **the thread actually executing the lookup**, not merely on the thread submitting the task.

## 10. Resources, JNI, the Module System, and Isolation Limits

### 10.1. Non-Class Resources

Many libraries use resources such as `config.properties`, `META-INF/services/...`, XML, or native libraries. Isolated class identity does not guarantee that resource lookups automatically use the same loader:

- `SomeClass.class.getResourceAsStream(...)` depends on the owning class and resource path.
- `pluginLoader.getResourceAsStream(...)` uses the loader chosen by the caller and resource lookup rules.
- `Thread.currentThread().getContextClassLoader().getResource(...)` depends on the thread context and may point to the wrong plugin.

When debugging "right class version, wrong configuration," check the **resource lookup path** as well. With URLClassLoader, resource URLs can include directories or JARs; the order of URLs and parent delegation affect the outcome.

### 10.2. Native Libraries Are Not Isolated Like Bytecode

If two Java libraries share a dependency on a JNI native library, loading and sharing native code is governed by `System.loadLibrary`/JVM and operating system rules. You cannot assume that two `URLClassLoader` instances automatically provide two independent native namespaces as they do for Java class files.

On the JVM, attempting to load the same native library from two class loaders can trigger an `UnsatisfiedLinkError` in corresponding scenarios. If a library has JNI or process-level singleton state, consider how the native dependency is designed and whether process separation is needed.

### 10.3. JPMS and ModuleLayer

The `URLClassLoader` example in section 5 uses the **class path**, where libraries belong to the unnamed module of their respective loader. With **named modules**, a parent loader does not automatically bypass module readability/exports/opens; you must configure the module graph and may consider separate `ModuleLayer` instances.

You can create different module layers for plugins when the system is designed modularly, while still distinguishing class identity, shared APIs, split packages, service binding, and module access.

### 10.4. Do Not Treat a Class Loader as a Security Sandbox

A custom class loader cannot completely prevent a plugin from modifying system properties, spawning threads, consuming CPU/memory, or calling platform APIs that the code has permission to use. To run untrusted code, consider process/container isolation with appropriate system policies rather than relying solely on child-first delegation.

## 11. Lifecycle: Loading, Running, Stopping, and Reloading Plugins

To support multiple versions in parallel or reloading:

1. **Create a separate loader** for the plugin version with specific class/resource sources.
2. **Load the implementation** and pass the object through the shared API.
3. **Use the plugin** within the defined scope; do not leak private `Class<?>` references into long-lived registries.
4. **Stop the plugin**: unregister listeners/callbacks, shut down executors, clear thread locals, and close resources.
5. **Close the URLClassLoader** when no tasks are using the class/resource sources anymore, and drop references to the loader as well as the plugin's objects/classes.
6. **If a new version is needed**, typically create a new loader with the new version's class bytes/URLs.

A `ClassLoader` object that has already defined `lib.Versioned` cannot turn the old runtime definition into a new version by modifying the underlying JAR file and calling `loadClass` again. A class already recorded for that loader is normally reused; attempting to call `defineClass` again with the same binary name can cause a `LinkageError`.

`URLClassLoader.close()` closes closeable resources managed by the loader and prevents certain subsequent lookup operations, but **does not itself unload already-loaded classes** or make already-created objects disappear. Class unloading depends on reachability/classloader lifetime and VM policy.

### References That Commonly Prevent Unloading

- A thread still running with the plugin's TCCL.
- A ThreadLocal holding an object/plugin class.
- A host static cache holding a `Class<?>`, `Method`, provider instance, or class loader.
- Event listeners/callbacks that have not been unregistered.
- Executors, timers, or scheduled tasks that have not been shut down.
- A ServiceLoader/provider cache or registry still holding plugin instances.

JVM observation:

```bash
java -Xlog:class+load=info,class+unload=info -cp "out/api:out/host" host.PluginHost
```

This command is illustrative for HotSpot/JDK 17 on Linux/macOS. It prints many class loading/unloading events, and **does not guarantee** seeing an unload line immediately when `try-with-resources` closes the loader.

## 12. Diagnosing Failures When Two Versions Do Not Behave as Expected

### Error A: Both Plugins Print Version 1's Value

Common possibilities:

- The parent class path already contains v1 and loads it before the two children.
- Both plugin loaders point to the same directory/JAR.
- Plugin B uses the TCCL or A's class loader during reflection/resource lookup.
- The library was **shaded** or copied mistakenly during packaging.

How to check:

```java
System.out.println(libA.getName());
System.out.println(libA.getClassLoader());
System.out.println(libB.getClassLoader());
System.out.println(libA == libB);
```

This illustrative snippet assumes the variables `libA` and `libB` have already been obtained. If `libA == libB` is true, the same runtime class is being used; the problem lies in **lookup/delegation**, not in whether two separate files exist.

### Error B: NoSuchMethodError or NoSuchFieldError

The plugin was compiled against v2's API, but at runtime it resolves to v1, where the corresponding method/field is missing. Compare the **runtime class source and defining loader** against the compile-time class path.

If you need to inspect the actual code in the class file:

```bash
javap -classpath out/plugin-a -p lib.Versioned
javap -classpath out/plugin-b -p lib.Versioned
```

In the demo example, both versions have the same method signature but different behavior; in real-world APIs, method descriptors may differ. `javap` shows the bytecode from the specified path and **does not by itself prove** that the runtime selected that version.

### Error C: ClassCastException Between Two Classes with the Same Name

Can occur when the host/plugin attempts to cast an object defined by loader A to a class with the same name defined by loader B. Check:

```java
System.out.println(typeA.getName().equals(typeB.getName()));
System.out.println(typeA == typeB);
```

If the names are identical but the `Class<?>` instances differ, the issue lies in runtime class identity. Do not fix this by changing the loader name or casting through `Object`; instead, unify the shared contract and use an appropriate adapter.

### Error D: LinkageError Due to a Loader Constraint Violation

The JVM enforces loading constraints when types in field/method descriptors at loader boundaries must be resolved consistently. If both the host API and a plugin define their own versions of `api.Message` with the same name, the JVM may reject linking with a `LinkageError` when the constraint is violated.

Solution: have `api.Message` and shared DTOs defined in the **common API loader**, and avoid letting private library types slip into the API signature.

### Error E: ClassNotFoundException or NoClassDefFoundError

Not everything is a version issue. A plugin loader may be missing a transitive dependency, have an invalid resource URL, or have a parent that cannot see the shared contract.

- `ClassNotFoundException` typically occurs when an explicit lookup cannot find the binary name.
- `NoClassDefFoundError` can arise when resolution/runtime requires a class that cannot be found, or when prior class initialization failed.
- Do not lump these two error types together as "the loader isn't working" while ignoring the stack trace.

### Error F: ServiceLoader Finds the Wrong Provider

Check whether the overload uses an **explicit loader** or the **TCCL**, which plugin contains the `META-INF/services/...` resource, whether the provider implements **the same runtime shared API type**, and whether additional providers are exposed by the parent.

### Systematic Diagnostic Process

1. Record the binary name of the failing class, the compile-time dependency version, and the owning plugin.
2. Record `Class.getClassLoader()` of the runtime class; do not just print `getName()`.
3. Check the URLs/class path of the parent and each child.
4. For the shared API, compare `Class<?>` directly between the host and the plugin.
5. Inspect the class bytes using `javap -classpath` and check the artifact inventory.
6. If needed, enable `-Xlog:class+load=info` on HotSpot to observe lookups; the log format depends on the VM and does not prove the full root cause without further analysis.
7. Check the TCCL, SPI, resources, and transitive dependencies.
8. Fix the issue at **dependency ownership and delegation policy**, rather than just clearing caches or renaming JAR files.

## 13. Common Mistakes

| Misconception | Reality |
|---|---|
| "If two JAR files contain the same class name, the JVM always loads both." | A single loader normally defines only one runtime class per binary name; different defining loaders or relocation are required. |
| "Creating two URLClassLoader instances guarantees two versions." | If the parent already has the private class, both parent-first children may share the parent's version. |
| "Child-first for all packages is the safest approach." | It can duplicate shared API types and cause ClassCastException/LinkageError. |
| "Identical bytes mean the same runtime type." | The defining loader also determines class identity. |
| "Different loader getName() values alone provide isolation." | A loader name is just a label; it does not determine lookup or identity. |
| "Host signatures can freely contain plugin-private types." | That is where loading constraints and incompatibilities can arise. |
| "Closing a URLClassLoader immediately unloads its classes." | Closing does not automatically make all Class<?>/objects unreachable. |
| "The TCCL is always equal to the currently running plugin's loader." | The TCCL belongs to the thread and can be changed by frameworks/thread pools. |
| "Classloader isolation isolates JNI/process-wide state as well." | Native/process-wide resources have different lifecycles and constraints. |
| "NoSuchMethodError means the class has not been loaded." | The class may have been loaded with **the wrong version**, resulting in a missing method for the expected descriptor. |
| "ServiceLoader.load(service) always searches only the current plugin's providers." | It uses the TCCL; to target a specific plugin, pass its loader explicitly and consider parent visibility. |

## 14. Self-Check Exercises

**Question 1.** Two loaders define the same `lib.Versioned` from two different JARs. What are the results of `classA.getName().equals(classB.getName())` and `classA == classB`?

**Answer:** The names can be equal, but the `Class<?>` instances differ if the defining loaders are different.

**Question 2.** Plugins A and B are both parent-first. The parent cannot see `lib.Versioned`. Each plugin URLClassLoader has its own version. Is a custom child-first loader required to use both versions?

**Answer:** No. When the parent does not have the private class, having each child find/define its own version is sufficient.

**Question 3.** The parent contains `lib.Versioned` v1, and plugin B contains v2. What can happen?

**Answer:** Parent-first may select v1 for B, causing wrong behavior or `NoSuchMethodError` if v2 has a new method. You should move the private lib out of the parent or design an appropriate selective child-first policy.

**Question 4.** Why can both plugins in the example be cast to the host's `api.Plugin`?

**Answer:** Both loaders delegate the `api.Plugin` interface to the same defining loader of the shared API; the implementation classes differ, but the contract's runtime identity is shared.

**Question 5.** What is the risk when a host API declares `lib.Versioned convert(lib.Versioned)`?

**Answer:** A private lib type leaks across the boundary. The host and plugin may resolve it to different runtime classes, causing a loading constraint violation or cast/lookup errors. You should use a shared DTO/interface or an adapter.

**Question 6.** Does `URLClassLoader.close()` guarantee that the JVM reclaims class metadata immediately?

**Answer:** No. You must consider object/classloader reachability and GC/unloading; `close()` mainly manages the loader's resources.

**Question 7.** Why shouldn't you use `static final String VERSION = "v2";` as definitive proof that version v2 was loaded?

**Answer:** Compile-time constants can be inlined at reference sites. Calling the instance method `value()` and inspecting the defining loader is clearer.

**Question 8.** ServiceLoader finds the wrong plugin's provider in a thread pool. What should you check?

**Answer:** Whether the overload uses the TCCL or an explicit loader, the worker's actual loader, the provider resource file, API type identity, and parent visibility.

## 15. Key Takeaways and Official Documentation

**Summary of three principles:**

1. **Isolate what needs to differ:** give each plugin its own defining loader for private dependencies with different versions.
2. **Share what needs to be compatible:** have interfaces and DTOs at the host/plugin boundary defined in a common loader; avoid letting private types pass through method/field descriptors of the shared API.
3. **Control loading paths and lifecycle:** prefer parent-first with a parent that does not contain private libs; use selective child-first only when necessary, pass loaders explicitly when looking up providers, close resources, and clean up references when a plugin stops.

**References:**

- [JVMS 17 — Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): defining/initiating loaders, runtime class identity, loading constraints, and resolution.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, `loadClass`, `findClass`, `defineClass`.
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): class/resource lookup via URLs and `close()`.
- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): provider discovery, explicit loader/TCCL, and service configuration.
- [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getName()`, `getClassLoader()`, and runtime type metadata.
