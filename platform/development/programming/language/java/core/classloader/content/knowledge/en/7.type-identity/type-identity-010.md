# Designing Shared API Types Across Multi-Loader Boundaries

When a Java application has multiple **class loaders** — such as a host application and separate loaders for plugins — a class named `api.Greeter` may appear in multiple places. Crucially: **two classes with the same binary name defined by two different defining loaders are not the same type at runtime**. This property directly dictates how you design shared APIs, invoke callbacks, pass DTOs, handle exceptions, and load plugin versions.

**Goal of this lesson:** create a host–plugin boundary where both sides use the **same `Class<?>` object** for the shared contract, while implementations and private dependencies can still be defined in the plugin's loader. From this principle, we will design dependencies, choose parent/delegation strategies, verify with `==`/`isAssignableFrom`, examine common errors, and run Java 17+ examples.

## 1. The Root Problem: "Same Name" Is Not Enough for "Same Type"

According to the JVM model, a reference class/interface at runtime is identified by the pair:

```text
(binary name, defining class loader)
```

For example, with the same binary name `api.Greeter`:

```text
AppLoader     defines api.Greeter   → type A
PluginLoader  defines api.Greeter   → type B

A.getName().equals(B.getName())    → true
A == B                              → false
```

Therefore, an object implementing `api.Greeter` version B is **not automatically** an instance of `api.Greeter` version A. The JVM checks runtime type identity; it does not compare package names or source signatures and guess that two types can be cast to each other.

Common consequences:

- `ClassCastException`: the plugin object cannot be cast to the host interface even though the message looks like `api.Greeter cannot be cast to api.Greeter`.
- `Class.isAssignableFrom(...)` returns `false` even though both classes have the same name and methods.
- `ServiceLoader` or reflection finds the implementation, but the host does not accept it as a subtype of the known service interface.
- Method/field signatures crossing two loaders receive classes with the same name but different identities; the JVM may detect **loading constraints** conflicts and throw `LinkageError`.
- DTOs, exceptions, callback types, or enums are incompatible at runtime because one side uses a different definition.

**Design rule:** *Types appearing in the exchange contract between host and plugin must have a clearly defined owning loader and be resolved by both sides to the same runtime type.* Not every class on both sides needs to be shared; only the **boundary types** need a shared identity.

## 2. Identifying What Is Contract vs. What Is Implementation

Let's divide a plugin's responsibilities into three areas:

```text
                  HOST APPLICATION
           ┌──────────────────────────────┐
           │ host orchestration / UI       │
           │ registry, lifecycle, config   │
           └──────────────┬───────────────┘
                          │
                   SHARED API
           ┌──────────────▼───────────────┐
           │ api.Greeter                  │
           │ api.Request / api.Response   │
           │ api.PluginException          │
           │ api.PluginContext (callback)  │
           └──────────────▲───────────────┘
                          │
                   PLUGIN INSTANCE
           ┌──────────────┴───────────────┐
           │ impl.PluginGreeter           │
           │ plugin-private dependencies  │
           │ optional resource/config     │
           └──────────────────────────────┘
```

Here:

- **Host** orchestrates, provides the shared API, and consumes the results.
- **Shared API** contains types that both host and plugin need to know. This is a **stable contract**, so it usually lives in a small artifact and is defined by a **shared/ancestor loader**.
- **Plugin implementation** lives in a separate artifact. A separate loader is allowed to define implementation classes, provided that references to the shared API resolve to the classes the host is using.
- **Plugin-private dependencies** are internal implementation libraries. Depending on the design, versions can be isolated; if a type from a private library appears in a public method signature across the boundary, it becomes part of the contract and needs its own policy.

An important milestone: "shared" here refers to **class identity at runtime**, not necessarily "both sides have two copies of the same JAR file." Two JARs with identical bytes that are separately passed to `defineClass` by two loaders will still produce two different runtime types.

## 3. Architectural Principle: A Shared API Owned by One Loader Used by Both Sides

The most common design is **parent-first for the shared API**:

```text
                     host/application loader
                       defines api.Greeter
                                ▲
                     parent/delegation
                                │
                     plugin URLClassLoader
                      defines impl.PluginGreeter
                                │
               uses api.Greeter defined above
```

When `PluginGreeter` declares `implements api.Greeter`, the plugin loader must **delegate** finding `api.Greeter` to the loader that defined the interface for the host. Desired result:

```java
Class<?> contract = api.Greeter.class;
Class<?> pluginClass = pluginLoader.loadClass("impl.PluginGreeter");

boolean canUse = contract.isAssignableFrom(pluginClass);
```

The above is an **illustrative snippet**, requiring `pluginLoader` and the corresponding classes to be declared. If the boundary is configured properly, `canUse == true`.

Choosing the shared loader does not always mean `ClassLoader.getSystemClassLoader()`. In application servers, OSGi environments, or custom module layers, the host API may reside in a dedicated loader. The invariant to preserve is: **the plugin and the host use the exact same `Class<?>` for every type in the contract**.

### Why Not Just Check `getName()`?

`getName()` returns the binary name. Two classes from two loaders can both return `"api.Greeter"`. Effective checks:

```java
hostApiClass == pluginApiClass
hostApiClass.isAssignableFrom(pluginImplementationClass)
hostApiClass.getClassLoader()
pluginApiClass.getClassLoader()
```

Check both **class identity** and the **defining loader**. `getClassLoader() == null` may represent the bootstrap loader, not an error.

## 4. Lab A — One Shared Interface Used by Both Host and Plugin

The complete example below is designed to run on **JDK 17+** with no frameworks required. We intentionally compile the API, plugin, and host into **separate directories**, then place only **API + host** on the application classpath at runtime. The plugin implementation will be loaded from its own directory using `URLClassLoader`.

Structure:

```text
shared-api-lab/
├── src/
│   ├── api/
│   │   └── api/
│   │       └── Greeter.java
│   ├── plugin/
│   │   └── impl/
│   │       └── PluginGreeter.java
│   └── host/
│       └── host/
│           └── HostMain.java
├── shared-out/      (created by javac)
├── plugin-out/      (created by javac)
└── host-out/        (created by javac)
```

**File `src/api/api/Greeter.java`:**

```java
package api;

public interface Greeter {
    String greet(String name);
}
```

**File `src/plugin/impl/PluginGreeter.java`:**

```java
package impl;

import api.Greeter;

public final class PluginGreeter implements Greeter {
    public PluginGreeter() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

**File `src/host/host/HostMain.java`:**

```java
package host;

import api.Greeter;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class HostMain {
    public static void main(String[] args) throws Exception {
        URL pluginLocation =
                Path.of("plugin-out").toAbsolutePath().toUri().toURL();
        ClassLoader hostLoader = HostMain.class.getClassLoader();

        try (URLClassLoader pluginLoader =
                 new URLClassLoader(new URL[] { pluginLocation }, hostLoader)) {
            Class<?> implementation =
                    pluginLoader.loadClass("impl.PluginGreeter");
            Class<?> pluginApi = implementation.getInterfaces()[0];

            System.out.println("plugin defined locally: " +
                    (implementation.getClassLoader() == pluginLoader));
            System.out.println("same API Class: " +
                    (pluginApi == Greeter.class));
            System.out.println("assignable: " +
                    Greeter.class.isAssignableFrom(implementation));

            Object instance =
                    implementation.getDeclaredConstructor().newInstance();
            Greeter service = (Greeter) instance;
            System.out.println("result: " + service.greet("Java"));
        }
    }
}
```

From the `shared-api-lab` directory, compile with JDK 17+:

```sh
javac --release 17 -d shared-out src/api/api/Greeter.java
javac --release 17 -cp shared-out -d plugin-out src/plugin/impl/PluginGreeter.java
javac --release 17 -cp shared-out -d host-out src/host/host/HostMain.java
```

Run on **Windows PowerShell/CMD**, where the classpath uses `;`:

```powershell
java -cp "host-out;shared-out" host.HostMain
```

On **Linux/macOS**, replace `;` with `:`:

```sh
java -cp "host-out:shared-out" host.HostMain
```

**Expected stdout for the configuration above:**

```text
plugin defined locally: true
same API Class: true
assignable: true
result: Hello, Java
```

### Why Does Lab A Succeed?

1. When compiling `PluginGreeter`, the compiler sees `api.Greeter` from `shared-out`; the class file records a reference to `api.Greeter`.
2. At runtime, the application classpath only has `host-out` and `shared-out`. The application/host loader loads `host.HostMain` and `api.Greeter`.
3. `pluginLoader` receives **`hostLoader` as its parent** and only has a URL to `plugin-out`. It finds `impl.PluginGreeter` via `URLClassLoader`'s `findClass`/`defineClass`, so the implementation belongs to the plugin loader.
4. When `api.Greeter` is needed for `implements`, the plugin loader follows parent-first delegation and receives **the same `Class<?>` interface** already present on the host. This makes `pluginApi == Greeter.class` true.
5. The `PluginGreeter` object is a true runtime subtype of the `api.Greeter` known to the host, so `Greeter.class.isAssignableFrom(implementation)` is true and the `(Greeter)` cast succeeds.
6. The host needs no compile-time dependency on `impl.PluginGreeter`; it only has a compile-time dependency on the API. This is key to swapping plugin implementations independently.

**Lab scope:** The URL from `Path.of("plugin-out")` depends on the **working directory**. Commands must be run from `shared-api-lab`. The example is kept simple and omits discovery mechanisms, version management, security boundaries, exception translation, or complex lifecycle management.

## 5. Lab B — Same Interface Name, Two Defining Loaders

Now keep **`Greeter.java`** and **`PluginGreeter.java`** from Lab A unchanged, but intentionally let the plugin loader see a **copy of the API** in `shared-out` while its **parent** is only the platform loader.

Create **`src/host/host/BrokenBoundary.java`**:

```java
package host;

import api.Greeter;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class BrokenBoundary {
    public static void main(String[] args) throws Exception {
        URL pluginLocation =
                Path.of("plugin-out").toAbsolutePath().toUri().toURL();
        URL apiLocation =
                Path.of("shared-out").toAbsolutePath().toUri().toURL();

        try (URLClassLoader isolated = new URLClassLoader(
                new URL[] { pluginLocation, apiLocation },
                ClassLoader.getPlatformClassLoader())) {

            Class<?> implementation =
                    isolated.loadClass("impl.PluginGreeter");
            Class<?> apiSeenByPlugin =
                    implementation.getInterfaces()[0];

            System.out.println("same API name: " +
                    apiSeenByPlugin.getName().equals(Greeter.class.getName()));
            System.out.println("same API Class: " +
                    (apiSeenByPlugin == Greeter.class));
            System.out.println("assignable: " +
                    Greeter.class.isAssignableFrom(implementation));

            Object instance =
                    implementation.getDeclaredConstructor().newInstance();
            try {
                Greeter service = (Greeter) instance;
                System.out.println(service.greet("Java"));
            } catch (ClassCastException e) {
                System.out.println("cast failed: " +
                        e.getClass().getSimpleName());
            }
        }
    }
}
```

Compile again against the same shared API; do not add the plugin to the host classpath:

```sh
javac --release 17 -cp shared-out -d host-out src/host/host/BrokenBoundary.java
```

Run on Windows:

```powershell
java -cp "host-out;shared-out" host.BrokenBoundary
```

Or Linux/macOS:

```sh
java -cp "host-out:shared-out" host.BrokenBoundary
```

**Expected stdout:**

```text
same API name: true
same API Class: false
assignable: false
cast failed: ClassCastException
```

**Why does it fail?**

- The host loader defines `api.Greeter` from the application classpath.
- `isolated` uses the **platform loader as its parent**. In this setup, the platform loader does not look for custom `api.Greeter` classes on the application classpath. Because `isolated`'s URLs include `shared-out`, `isolated` itself defines **a second copy of `api.Greeter`**.
- The plugin implementation `impl.PluginGreeter` implements the API copy defined by `isolated`, not the API copy from the host loader.
- Both have the name `api.Greeter`, yet the two `Class<?>` objects have different identities. Therefore, the implementation type is not assignable to the host interface and the cast fails.

This is an **intentionally broken** example to clarify class identity; it is **not a valid plugin design pattern**. You do not fix `PluginGreeter`'s `extends` clause to rescue the cast. You must ensure both host and plugin resolve `api.Greeter` through **the same loader that owns the shared API** — as configured via the parent in Lab A.

### "What If Both JARs Are Byte-for-Byte Identical?"

It can still fail. Class identity comes from the pair **binary name + defining loader**, not by hashing file contents to merge runtime types. Even with byte-for-byte identical bytecode, two `defineClass` calls by two loaders still create two distinct runtime classes.

## 6. Lab C — Two Plugin Loaders, One Contract, Two Separate Implementation Types

The same **`PluginGreeter.class`** can be defined independently by two loader instances, yet **both implementations remain subtypes of the same API** if both loaders delegate the contract to the host.

Create `src/host/host/TwoPlugins.java`:

```java
package host;

import api.Greeter;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class TwoPlugins {
    public static void main(String[] args) throws Exception {
        URL location =
                Path.of("plugin-out").toAbsolutePath().toUri().toURL();
        ClassLoader sharedParent = Greeter.class.getClassLoader();

        try (URLClassLoader first = new URLClassLoader(
                     new URL[] { location }, sharedParent);
             URLClassLoader second = new URLClassLoader(
                     new URL[] { location }, sharedParent)) {

            Class<?> one = first.loadClass("impl.PluginGreeter");
            Class<?> two = second.loadClass("impl.PluginGreeter");

            System.out.println("same implementation name: " +
                    one.getName().equals(two.getName()));
            System.out.println("same implementation Class: " + (one == two));
            System.out.println("first matches API: " +
                    Greeter.class.isAssignableFrom(one));
            System.out.println("second matches API: " +
                    Greeter.class.isAssignableFrom(two));

            Greeter a = (Greeter) one.getDeclaredConstructor().newInstance();
            Greeter b = (Greeter) two.getDeclaredConstructor().newInstance();
            System.out.println(a.greet("A"));
            System.out.println(b.greet("B"));
        }
    }
}
```

Compile (keeping `shared-out` and `plugin-out` from Lab A):

```sh
javac --release 17 -cp shared-out -d host-out src/host/host/TwoPlugins.java
```

Run on Windows:

```powershell
java -cp "host-out;shared-out" host.TwoPlugins
```

On Linux/macOS:

```sh
java -cp "host-out:shared-out" host.TwoPlugins
```

**Expected stdout:**

```text
same implementation name: true
same implementation Class: false
first matches API: true
second matches API: true
Hello, A
Hello, B
```

This demonstrates that **shared API identity** and **implementation isolation** can coexist:

```text
                   Host API Loader
                 defines api.Greeter
                      ▲      ▲
                      │      │
              PluginLoader 1  PluginLoader 2
                  │                │
      defines impl.PluginGreeter   defines impl.PluginGreeter
      (implementation type #1)    (implementation type #2)

PluginLoader1.impl.PluginGreeter != PluginLoader2.impl.PluginGreeter

but both implement the same HostLoader.api.Greeter
```

With multiple plugin instances, you can easily instantiate separate implementation objects and communicate via the shared contract. Note that this does not make plugin code safe from untrusted execution risks, does not eliminate the need for loader lifecycle management, and does not guarantee isolation of all static state or native libraries the way separate OS processes do.

## 7. Artifact Packaging Rules: Contract One Way, Implementation Another

In a real deployment, you might have:

```text
plugins/
  shared-api.jar           # shared copy controlled by the host
  host-app.jar             # host orchestration code
  plugin-a.jar             # implementation A
  plugin-b.jar             # implementation B
```

The deciding factor is not the file name. Determine **dependency ownership**:

| Artifact/type | Class identity owner | Why |
| --- | --- | --- |
| `api.Plugin`, `api.PluginContext` | Shared loader delegated to by host and plugin | Plugin objects must be assignable to host interfaces; callback parameters must have the same type. |
| `api.Request`, `api.Response` | Usually the shared loader, or a class-identity-independent exchange format | DTOs must cross the boundary safely. |
| `api.PluginException` | Shared loader if the host must `catch` this type | Exception types are part of the boundary contract. |
| `impl.PluginA` | Plugin A's loader | Implementation can be swapped independently of the host. |
| `impl.PluginB` | Plugin B's loader | Can isolate classes/static state/dependencies from A. |
| Internal implementation libraries | Plugin loader, if not leaked through the contract | Allows plugins to use different dependency versions. |
| Java SE classes | Bootstrap/platform loaders per JDK | Types like `String` or `List` are shared platform types, though generic type arguments may hold app/plugin-specific classes. |

**Build recommendation:** Plugins **compile against** the shared API, while runtime wiring ensures the API is resolved from the shared loader. If a plugin artifact bundles the API for build convenience, you still need a mechanism to exclude the duplicate from dynamic loading or ensure the delegation policy prioritizes the shared API; do not let a child-first plugin redefine it.

With Gradle/Maven, use appropriate compile-time dependency configurations to avoid packaging duplicate shared APIs into the plugin distribution. However, configuration names like `compileOnly` or `provided` only solve **artifact packaging**; proper class identity still depends on the runtime loader graph and how loaders resolve classes.

### How to Tell Whether a Library Should Be Shared or Private?

Ask: **Does a type from that library appear at a public boundary where both host and plugin interact through the JVM type system?**

- If `api.Plugin.execute(Request)` takes `api.Request`, the `Request` type is a boundary type.
- If `PluginGreeter` uses `org.example.json.InternalParser` only inside private methods, the parser can be a plugin-private dependency.
- If `api.Plugin.execute(com.vendor.JsonNode)` uses a `JsonNode` outside the shared API, **the version and identity of `JsonNode` must be designed as shared**, or the boundary should be changed to a DTO with clear ownership.
- If the host passes `java.util.Map<String, Object>`, the `Map` class is a shared platform type, but the `Object` values could hold plugin-private instances. This makes the contract look neutral while hiding potential cast or lifecycle errors.

**The smaller and clearer the boundary surface, the lower the risk of leaking implementation types.**

## 8. Designing a Stable API Contract

A shared interface can be organized like this:

```java
package api;

public interface Plugin {
    String id();

    Result execute(Request request, PluginContext context);
}
```

The example above is an **illustrative API design snippet** and will not compile on its own until `Request`, `Result`, and `PluginContext` are declared. It demonstrates three groups of data commonly found in a plugin API:

1. **Identity/capability metadata**: `id()`, version, or capability metadata.
2. **Input/output data**: request/response defined in the shared API.
3. **Host-provided callback/facade**: `PluginContext` giving the plugin access to capabilities the host intentionally exposes.

### DTOs: Java Classes or Loader-Neutral Data?

There are two approaches:

**A. Shared Java DTO types.** Host and plugin share `api.Request` and `api.Result` from the same defining loader. Pros: direct compile-time and runtime type checking. Cons: binary API changes require versioning and compatibility planning; DTOs only work when both sides have the same class identity.

**B. Class-loader-neutral protocol.** Use JSON, byte arrays, protobuf, message schemas, or data records across a well-defined conversion interface. Pros: reduces reliance on runtime class identity for internal payloads and can extend to out-of-process plugins. Cons: requires validation, schema evolution, and deserialization error handling. Even if the payload is bytes/JSON, the Java types at the **direct API call** boundary (e.g., an interface taking `byte[]`) must still have compatible identities.

### Exceptions Across the Boundary

If the contract declares `throws api.PluginException`, the host can only catch the exact runtime exception subtype it knows when the plugin uses the same class identity for `api.PluginException`. If the plugin defines a same-named copy through another loader, the host's catch clause **will not catch that copy**.

In practice, agree clearly on:

- Are checked exceptions part of the contract?
- Are runtime exceptions from private libraries allowed to cross the boundary, or should a plugin adapter map them to standard errors?
- Are error codes, messages, causal chains, and redaction needed so the host does not depend on plugin implementations?
- How does the host operate if a plugin throws `LinkageError`, `OutOfMemoryError`, or another serious error?

For public APIs, avoid putting volatile implementation types directly into method signatures.

### Callbacks Must Go Through the Same Shared API

If the host passes an object implementing `api.PluginContext`, the plugin will cast and invoke it. For callbacks to be safe, both sides must see the exact same `api.PluginContext` runtime type. If the plugin loads its own copy of the context interface, identity errors appear immediately in the **host → plugin** direction, even if the return direction for plugin objects was already handled.

## 9. Method Signatures, Binary Compatibility, and Loading Constraints

An API contract is a **binary contract**. The JVM links method/field references by name and **descriptor**; the descriptor contains parameter types and the return type in JVM format.

Example Java method:

```java
api.Result execute(api.Request request)
```

Conceptual descriptor:

```text
(Lapi/Request;)Lapi/Result;
```

If the host compiles against an API version with `execute(Request):Result` but the plugin or runtime has a different signature, errors can include `NoSuchMethodError`, `AbstractMethodError`, or an appropriate `LinkageError` depending on the change and when it is used.

**Loading constraints** protect type safety when method signatures cross different loaders. For instance, if the host and plugin have a method with the same descriptor requiring `api.Request` to have the same identity, yet the loader mapping defines two different types, the JVM may reject linking with a `LinkageError` due to a loader constraint violation. Do not try to "fix" this by forcing method calls by name via reflection: the identity violation still exists.

### API Upgrades Require a Policy

A few practical rules:

- Do not change return types, parameter types, static/instance modifiers, or remove methods used by older plugins and expect binary compatibility to hold automatically.
- Adding an abstract method to an interface can leave implementations compiled against the old API missing an implementation when the new method is called; seemingly source-compatible changes can cause runtime errors.
- Adding a `default` method can help in some interface evolution scenarios, though it risks default method conflicts between interfaces; test across supported plugin versions.
- For major contract changes, use separate API versions, adapters, or lifecycle migrations rather than trying to share multiple copies of `api.Plugin` with the same binary name across the same boundary.
- Use integration tests that load **published plugin JARs** through real class loaders, rather than only recompiling both host and plugin from the latest source.

**Important:** Two libraries with the same source-level Java API do not guarantee binary compatibility at runtime when class files are built from different versions.

## 10. Designing the Loader Graph and Delegation Policy

A plugin architecture must be able to describe:

```text
                Shared/Host API Loader
                  │  api.*, JDK types
                  ▲
                  │ parent-first for api.*
          ┌───────┴────────┐
          │                │
      Plugin A           Plugin B
      impl.a.*           impl.b.*
      libs A             libs B
```

The diagram illustrates the goal: **shared API from parent**, **private implementations at child**. On some platforms, the shared API is defined by a dedicated loader that the host also uses; in other architectures, the application loader may be used.

### Parent-First

The default `ClassLoader.loadClass` pattern tries the parent first and then `findClass`. It works well when the shared API is in the parent and plugins have no unintended class name collisions. However, parent-first for **all classes** can prevent a plugin from loading the private library version it needs when the host already has a class with the same name.

### Child-First with Exceptions for the Shared API

Some systems implement a custom `loadClass` to prioritize plugin implementations/dependencies while **reserving contract packages and JDK classes for the parent**. This is a viable design, but you must account for:

- `java.*` must never be defined in an application loader.
- API packages must be delegated consistently, including types referenced indirectly in signatures.
- `findLoadedClass`, class-loading locks, concurrency, and circular loading risks must be handled.
- Package sealing, signed JARs, and module accessibility can restrict how classes are defined.
- Resource lookup may have its own policy; a loader that finds the right class does not necessarily find the right resource.
- Native libraries and static state have different isolation boundaries than Java class namespaces.

**Do not write a child-first loader just to "fix" a `ClassCastException`** without investigating why the API was duplicated. In many cases, fixing the parent graph and dependency placement is simpler and easier to test.

### Why Might the Platform Loader Not Be Enough?

`ClassLoader.getPlatformClassLoader()` sees platform classes, but by default it does not see the application's shared API on the unnamed application classpath. Lab B intentionally chose the platform parent to separate from the host API. If a plugin must receive an interface defined by the host, its parent should be a loader that sees that interface, or an explicit bridging mechanism must be in place.

**A loader's parent is an object relationship**, not Java class inheritance: `new URLClassLoader(urls, hostLoader)` passes an instance that determines delegation. The plugin loader's Java class does not need to `extends` the host loader's Java class.

## 11. JPMS, Module Layers, and Accessibility

Since Java 9, modules add another dimension to the Java runtime. Class loaders, module resolution, and module access cannot be treated as the same thing.

Questions to separate:

1. **Which module contains the shared API?** For example, a named module `com.example.plugin.api` or a package in an unnamed module.
2. **Which layer is that module resolved into?** Having a module on the path does not mean it has been resolved.
3. **Which module reads which module?** A named module caller must have appropriate readability (typically via `requires`).
4. **Which packages are exported?** A public class is not automatically accessible if its package is not exported.
5. **Which loader defines each class?** Two modules or layers can use different loaders; avoid assuming the same module name guarantees the same type.
6. **Is deep reflection used?** Check `opens` and corresponding access rights, not just `exports`.

Example module descriptor for a shared API artifact:

```java
module com.example.plugin.api {
    exports api;
}
```

This is an **illustrative `module-info.java`**, not standalone source meant to run directly with the classpath directories from Labs A–C. A named plugin module consuming the API will declare `requires com.example.plugin.api;` where appropriate. In real JPMS environments, the module layer design and loader mapping must preserve the same contract class identity; simply writing `requires` does not prevent multiple copies of the same class from being defined in different loaders.

**Core distinction:** a loader seeing class bytes **does not mean** module code is permitted to call that class due to `exports`/readability. Conversely, a valid module graph **does not necessarily** eliminate conflicts among plugin dependencies outside the graph.

## 12. `ServiceLoader` and Finding Implementations

`ServiceLoader` is a Java mechanism for loading **service providers**, commonly used to discover plugins. It does not replace the shared class identity principle.

Example:

```java
ServiceLoader<Greeter> providers = ServiceLoader.load(Greeter.class);
```

This is an **illustrative snippet**; it requires importing `java.util.ServiceLoader` and `api.Greeter`. The provider must be validly declared in `META-INF/services/api.Greeter` when using the classpath, or `provides ... with ...` in a named module, and must belong to loaders/layers accessible to `ServiceLoader`. The `ServiceLoader.load(Class<S>)` overload uses the **thread context class loader** in normal contexts.

Three common pitfalls:

- **Discovering a provider does not mean its type is valid**: the instance must still be a subtype of the **exact `Greeter.class`** that the host passed to `ServiceLoader`.
- **TCCL is not the parent loader**: `Thread.currentThread().getContextClassLoader()` may point to a plugin loader, system loader, or framework-configured value. Setting the TCCL only changes the discovery context, not the definition of an already loaded class.
- **Provider metadata can be right while the class is missing a dependency**: the runtime may throw `ServiceConfigurationError` with an underlying cause such as `ClassNotFoundException`, `LinkageError`, or a provider constructor failure.

When using `ServiceLoader.load(Greeter.class, pluginLoader)`, the plugin loader must see the **exact shared API `Greeter.class`** and load a valid provider. If using named modules, also understand `ServiceLoader.load(layer, service)` and provider scoping within module layers.

## 13. Reflection, Method Handles, and Types "Leaking" Across the Boundary

Reflection can invoke methods by name, but the JVM still enforces access, assignability, and class identity rules. For example:

```java
Class<?> type = pluginLoader.loadClass("impl.PluginGreeter");
Object plugin = type.getDeclaredConstructor().newInstance();
```

This is an illustrative snippet that can be placed inside a method declaring `throws Exception` once `pluginLoader` is declared. If `plugin` implements a duplicate copy of the interface defined by another loader, casting on the host still fails.

Risks to watch for:

- **Method parameter types:** `getMethod("execute", Request.class)` must match the **exact `Class<?>` of `Request`** declared by the method. The same name is not enough.
- **Return types:** an `api.Result` from the plugin loader is not automatically an `api.Result` of the host loader.
- **Array types:** `api.Result[]` also depends on the component type's defining loader; two array types with different runtime component types are not interchangeable.
- **Enums and records:** these are still runtime Java classes with a defining loader; values are not automatically identical across loader copies.
- **Exceptions:** Java catch clauses are checked by runtime type; an exception class with the same name but a different defining loader will not be caught by the host's type.
- **Annotations:** if a plugin class carries an `api.Extension` annotation separately defined by the plugin loader, host reflection using `api.Extension.class` may not recognize it as the same annotation type.
- **Proxies and method handles:** generated proxy classes and handle signatures must respect the visibility/access of the involved loaders; you cannot assume matching interface names solve everything.
- **Java generics:** type erasure does not remove all type checks. `List<PluginDto>` shares the raw runtime `List`, but objects inside still carry their own defining loader identity.

An API that "just uses `Object`" sometimes hides the issue until the host casts the payload contents. Prefer an explicit DTO contract or a loader-neutral exchange format with validation at the boundary.

## 14. Managing Loader Lifecycles and Avoiding Keeping Plugins in Memory Forever

A plugin loader typically stays alive alongside the objects and classes it defines. Unloading a class loader may require releasing all references keeping the loader, classes, and instances alive; the GC/runtime decides when and whether unloading occurs.

Commonly overlooked reference sources:

- A host registry still holding a plugin instance, `Class<?>`, `Method`, or `MethodHandle` from the plugin.
- A static field on the host holding a plugin object or a listener registered by the plugin.
- A thread pool or thread context class loader still pointing to the plugin loader.
- Timers/tasks, callbacks, `ThreadLocal`, metrics registries, or loggers holding plugin classes/instances.
- A `ServiceLoader` instance/cache or framework cache still retaining provider/plugin implementations.
- A plugin's private library spawning a non-daemon thread that has not been stopped.

`URLClassLoader.close()` closes resources managed by the loader (such as open JARs); it **does not guarantee the JVM unloads all classes immediately** and does not automatically stop threads or close objects created by the plugin. You need a plugin lifecycle (`start/stop/close`) with a clear contract: unregister callbacks, stop background work, clear registries, and clean up TCCLs in a controlled manner.

When the host holds a contract interface in a shared loader, that interface itself may live for the lifetime of the application — which is normal. What to avoid is the shared API or registry accidentally holding strong references to plugin instances after unloading.

## 15. Debugging `ClassCastException` or `LinkageError` at the Boundary

**Step 1: identify the two types being compared.** Do not just read the binary name from the exception; inspect the actual `Class<?>` objects on both sides.

A helper you can place in your application when you have both the host API class and the plugin implementation class:

```java
static void inspect(Class<?> hostApi, Class<?> implementation) {
    System.out.println("host API: " + hostApi.getName());
    System.out.println("host loader: " + hostApi.getClassLoader());
    System.out.println("impl: " + implementation.getName());
    System.out.println("impl loader: " + implementation.getClassLoader());
    System.out.println("assignable: " +
            hostApi.isAssignableFrom(implementation));
    for (Class<?> api : implementation.getInterfaces()) {
        System.out.println("implemented: " + api.getName());
        System.out.println("interface loader: " + api.getClassLoader());
        System.out.println("same interface: " + (api == hostApi));
    }
}
```

This is an **illustrative method** that must be placed inside a class and called with appropriate types; it is not a standalone `.java` file. `getInterfaces()` only lists interfaces directly declared by the class, so for deeper hierarchies also inspect superclasses and superinterfaces.

**Step 2: inspect the runtime dependency/loader graph.** Check whether the shared API directory/JAR appears on both the host and plugin paths, the specific parent of the loader, and the parent-first/child-first strategy. **Do not just delete duplicate files** if the loader still has no path to find the shared API.

**Step 3: inspect bytecode/binary descriptors.** Use `javap -verbose` and `javap -s` on the classes in the artifacts **actually being executed**, not just the latest source:

```sh
javap -classpath shared-out -s api.Greeter
javap -classpath plugin-out -v impl.PluginGreeter
javap -classpath host-out -v host.HostMain
```

These commands apply to the Lab A outputs; output can be verbose and varies by `javac`/JDK. `javap` shows class-file references and signatures; it does not by itself tell you **which defining loader the JVM will choose** at runtime.

**Step 4: class loading logs.** On HotSpot, Unified Logging is supported:

```sh
java -Xlog:class+load=info -cp "host-out;shared-out" host.HostMain
```

The command uses **Windows** classpath syntax for consistency with the example; on Linux/macOS replace `;` with `:`. Logs show the source of class bytes and loading info to help identify which artifact is used. Combine with `Class.getClassLoader()` to verify actual identity; the moment a class is loaded does not mean initialization or resolution is complete.

**Step 5: classify the error instead of guessing fixes.**

| Symptom | Likely cause to check | Primary fix direction |
| --- | --- | --- |
| `ClassCastException` with the same binary name | Two defining loaders created duplicate API copies | Share one contract loader; fix delegation/packaging. |
| `isAssignableFrom` returns `false` | Implementation does not implement the exact runtime interface | Inspect the plugin's interface `Class<?>`, loader chain, and contract version. |
| `ServiceConfigurationError` | Provider is not a service subtype, misconfigured service, or constructor/dependency error | Compare service `Class<?>`, TCCL/ServiceLoader loader, and provider metadata. |
| `NoSuchMethodError` / `NoSuchFieldError` | Binary API mismatch at runtime | Compare descriptors across host/plugin/runtime JARs; check version compatibility. |
| `AbstractMethodError` | Runtime implementation lacks a method required by the call site | Check interface evolution/ABI and which version the plugin was compiled against. |
| `LinkageError` involving loader constraints | Signature type identity conflict between loaders | Check shared types nested in parameters/returns and loader delegation. |
| `IllegalAccessError` / `InaccessibleObjectException` | Insufficient package/module access or `opens` | Fix module descriptor/`exports`/`opens` and valid reflection paths. |
| `ClassNotFoundException` | The queried loader cannot see the class | Check parent chain, URL/module/layer, and runtime packaging. |
| `NoClassDefFoundError` | Required class could not be defined/used or initialization previously failed | Find `Caused by`, runtime dependencies, and initializers. |

`ClassNotFoundException` from `loadClass` is a checked exception of the lookup API; `NoClassDefFoundError` is a `LinkageError` that can occur at a different time when bytecode needs the class. Do not conflate them.

## 16. Pre-Release Plugin Design Checklist

Before choosing a loading mechanism, check in order:

1. **List all boundary types.** Interfaces, DTOs, exceptions, annotations, enums, callbacks, collections holding third-party values, and types in descriptors.
2. **Designate one valid defining loader for each shared type.** The host and every involved plugin must resolve to that same `Class<?>`.
3. **Draw the loader graph.** Which loader is the parent/ancestor of which, and are there any child-first rules or package exceptions?
4. **Ensure matching packaging.** The shared API is distributed/versioned clearly, plugins do not accidentally define copies, and implementations sit on the plugin path.
5. **Isolate private dependencies.** Do not let private dependency types leak across the public contract without a plan for shared identity.
6. **Verify binary compatibility.** The host API version and released plugin artifacts have an explicit version contract.
7. **Check JPMS if using modules.** Readability, `exports`, `opens`, layers, and actual defining loaders.
8. **Check discovery.** `ServiceLoader`/TCCL can locate providers, and providers are assignable to the host's service type.
9. **Check lifecycle.** Have start/stop hooks, callback/thread/resource cleanup, and proper loader closing.
10. **Run integration tests through real loaders.** Do not test only with plugin classes directly on the system classpath, as that can accidentally bypass the boundary you need to test.

### Minimum Recommended Test

A worthwhile integration test should actually create a plugin loader with a separate classpath as in Lab A, load the plugin by binary name, and assert:

```java
assert api.Plugin.class.isAssignableFrom(implementationClass);
assert implementationClass.getClassLoader() == pluginLoader;
```

These are **illustrative assertions**, not complete JUnit code. If the source belongs to a module or another framework, the second assertion may need adjustment for the specific loader design; the contract identity assertion is the critical one. Also test cases such as plugins bundling duplicate API JARs, version mismatches, missing dependencies, and unload lifecycles where applicable.

## 17. Misconceptions to Avoid

- **"Same package and class name means the JVM will automatically share the type."** False: the defining loader is part of runtime type identity.
- **"Adding `api.jar` to both host and plugin classpaths is enough."** Not enough: if each loader defines its own copy, their identities diverge.
- **"The plugin loader must inherit from the same Java superclass loader as the host for casts to succeed."** False: inheritance between loader implementation classes does not determine contract identity.
- **"The plugin is child-first, so every class must be loaded in the child."** Avoid this: the shared API usually needs a delegation exception to the shared loader.
- **"Once the shared interface is right, all DTOs are safe."** Not necessarily: every type exposed at the boundary must also be aligned or passed via a neutral protocol.
- **"Reflection solves class loader conflicts."** False: obtaining classes/methods via reflection does not remove access or type constraints.
- **"`ServiceLoader` always sees all plugins."** False: discovery depends on TCCL, loaders/layers, service metadata, and assignability.
- **"`URLClassLoader.close()` makes all plugin classes disappear immediately."** False: unloading also depends on reachability and GC.
- **"One shared API lasts forever without versioning."** False: changing binary signatures can break linking for older plugins.
- **"If two plugins use the same dependency version, they must share all classes."** False: each plugin can define its own implementation/dependencies as long as the **shared boundary types** preserve identity.

## 18. Self-Check Questions

**1. What elements does the JVM use to distinguish two reference types with the same name?** Binary name and defining class loader.

**2. Why can't the host copy and plugin copy of `api.Greeter` be cast to each other?** Two loaders define two different `Class<?>` interfaces, causing runtime assignability to fail despite identical names/source.

**3. What condition is required for a plugin implementation to be assignable to a host interface?** The plugin must use the exact runtime interface the host uses in its `implements` relationship, typically via a shared parent/delegation.

**4. Why does `PluginGreeter` belong to the plugin loader in Lab A while `Greeter` is shared?** `URLClassLoader` defines the implementation class from `plugin-out`, whereas the contract from `shared-out` is provided by the host loader via parent-first delegation.

**5. Why does Lab B intentionally fail even though `Greeter.java` is unchanged?** The plugin loader uses the platform parent and then defines the API itself from `shared-out`, creating an interface copy with a different identity from the host.

**6. Can two different plugin loaders share the same API while having separate implementations?** Yes. Both delegate to one shared API loader while defining their own implementations.

**7. Does `List<Object>` in a contract guarantee no private types leak?** No. Values inside the collection can be plugin-private classes; casts on the host can still fail.

**8. Why can changing a return type break plugin binary compatibility?** The JVM method descriptor includes the return type. Callers compiled earlier contain symbolic references using the old descriptor.

**9. How does TCCL relate to shared APIs?** Some discovery mechanisms like `ServiceLoader` use TCCL to locate providers, but TCCL does not merge two class identities.

**10. What should be tested before releasing a plugin API revision?** Test plugin JARs compiled against older versions through the real loader graph, including subtype checks and method invocations across all boundary types.

## 19. References for Verification

- [Java Virtual Machine Specification, Java SE 17 — Chapter 5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): loading, defining/initiating loader, class identity, loading constraints, and linking.
- [Java SE 17 `ClassLoader` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, parent delegation, `getParent`, and class loader contracts.
- [Java SE 17 `URLClassLoader` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): creating a loader from URLs and closing a loader.
- [Java SE 17 `Class` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getClassLoader`, `getInterfaces`, `isAssignableFrom`, and runtime types.
- [Java SE 17 `ServiceLoader` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): provider discovery on classpath/module path and context loader.
- [Java SE 17 `Module` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): module readability and access model.

**Closing principle:** multi-class-loader design succeeds when **the shared contract has a single runtime identity visible to all sides**, while implementations can keep separate namespaces. Inspect actual `Class<?>` objects, defining loaders, method descriptors, module access, and loader graphs — rather than just comparing package names or JAR contents.
