# Why Does a Platform API Need to See Application Implementations?

A framework or platform API typically **defines the contract (interface/SPI)**, while the application, plugin, or library vendor **provides the implementation (provider)**. If the library resides in a parent loader while the provider is in a child loader, standard **parent-first class loading** does not automatically allow the parent loader to see down into the child loader's classes.

For example: the library defines `Greeting`, and the application implements `HelloGreeting`. The library needs to discover and invoke an implementation that it does not know about at compile time. With a mechanism that only asks the parent, a class in the parent can find its own classes, but **cannot automatically find** providers that exist only in the application/plugin loader.

That is one reason the **thread context class loader (TCCL)** exists: library/framework code running on a thread can proactively ask, "Which loader does the application want to use to discover implementations in this task?" APIs such as `ServiceLoader.load(Service.class)` have a contract to use TCCL to solve that need.

This article belongs to the **Context Loader** group of Java core – classloader. The focus is on why platform APIs need to see application implementations, the call path, the differences between **defining loader**, **parent loader**, and **TCCL**, a runnable Java 17+ example, limitations in module/plugin environments, and common errors.

## 1. The Design Problem: API "Above", Implementation "Below"

An extensible system typically separates two roles:

- **API/service contract:** an interface, abstract class, or shared set of rules published by the framework, such as `java.sql.Driver`, `java.util.spi.*`, or an interface defined by the application host.
- **Provider/implementation:** a concrete class implementing that contract, such as a database vendor's driver, cryptography provider, serializer, logging implementation, or plugin.
- **Discovery/factory:** the component that needs to locate or instantiate a provider based on configuration/module metadata without hard-coding a dependency on a specific class name when compiling the API.

Typical delegation tree:

```text
                     [Bootstrap loader]
                              ^
                              |
                       [Platform loader]
                              ^
                              |
                  [Application/System loader]
                              ^
                              |
                       [Plugin loader]
                       plugin.HelloGreeting
```

The arrows above indicate that **a child can ask its parent to find a class**, not that the parent can automatically access every class defined by a child.

If `host.LibraryDiscovery` is defined by the system loader, while `plugin.HelloGreeting` resides only in the child plugin loader, the call:

```java
Class.forName("plugin.HelloGreeting")
```

if written *directly inside `host.LibraryDiscovery`* will by default start from **the defining loader of `LibraryDiscovery`**. It does not automatically infer that a plugin is calling into that method and needs to switch loaders along the call stack. This can cause the provider class not to be found even though the plugin loader actually has its bytecode.

**Conflict to resolve:** platform/host code needs to discover implementations provided by the application, but a parent-first loader has no general mechanism to "query back across every child loader".

## 2. How Does TCCL Solve the Problem?

Each `Thread` in Java has a **context class loader** that can be read or changed:

```java
ClassLoader current = Thread.currentThread().getContextClassLoader();
Thread.currentThread().setContextClassLoader(someLoader);
```

This is an **illustrative snippet**, assuming `someLoader` already exists. TCCL is **state of the thread**, not a global JVM property and not a new edge in `ClassLoader.getParent()`.

Framework call path:

```text
Host/framework defines interface Service
               |
               | application starts request / plugin
               v
Thread context loader = PluginLoader
               |
               | Host API calls ServiceLoader.load(Service.class)
               v
ServiceLoader asks TCCL to find provider metadata
               |
               v
PluginLoader finds META-INF/services/... and provider class
               |
               v
Provider class defined by PluginLoader
               |
               +-- provider implements Service defined by parent
               |
               v
Framework receives Service and calls method of shared interface
```

**Core point:** TCCL allows *code located in a parent loader to proactively ask a child loader to find an implementation*. It does not make all code in the parent loader naturally see classes of the child loader, does not modify the parent chain, and does not change the defining loader of already loaded classes.

One notable detail to know from the Java 17 API:

```java
ServiceLoader<Greeting> services =
        ServiceLoader.load(Greeting.class);
```

This overload is equivalent in loader selection to:

```java
ServiceLoader<Greeting> services =
        ServiceLoader.load(
                Greeting.class,
                Thread.currentThread().getContextClassLoader());
```

This is an **illustrative snippet**, assuming the `Greeting` interface has already been declared. The TCCL selection mechanism is a specific contract of `ServiceLoader.load(Class)`, **not an automatic rule of every Java method**.

## 3. Why Does a Parent Loader Not Proactively Search Down into Children?

In the default `ClassLoader.loadClass` mechanism, a loader sequentially checks whether the class is already loaded, asks its parent, and only then tries its own `findClass`. A parent does not have a stable list of all child loaders because:

1. Applications can create multiple plugin loaders dynamically.
2. Two plugins may define **the same class name** while wanting to keep independent namespaces/versions.
3. A framework may run multiple tenants or applications on the same JVM with different contexts.
4. The parent may be loaded much earlier than plugins and does not know which implementations will appear later.
5. If the parent queried every child on its own without a contract, it could pick the wrong provider or expose unintended class boundaries.

For example:

```text
                   [App/system loader]
                     /           \
                    v             v
              [PluginLoader A] [PluginLoader B]
               demo.Provider   demo.Provider
```

The two `demo.Provider` classes can be **different** classes, because a class's runtime identity is **binary name + defining loader**. Selecting provider B for a request from A would be wrong, even though the classes have the same name.

TCCL allows the **execution context** itself to choose a specific loader when a discovery API intentionally uses it. This mechanism is useful for request-scoped, plugin-scoped, or container-scoped discovery.

However, **TCCL is not a security sandbox**: it is a reference to a chosen loader. An API using that loader must still comply with Java/module access and trust boundaries.

## 4. Runnable Java 17+ Example: Parent Framework Discovering a Child Plugin Provider

Let us build an example that can be compiled/run using JDK 17 or later. It includes:

- `api.Greeting`: shared interface defined by the **system loader**.
- `lib.Discovery`: library code **only in the system loader**, discovering providers via `ServiceLoader`.
- `plugin.HelloGreeting`: implementation **defined only by the plugin loader**.
- `main.Launcher`: application that explicitly sets TCCL = plugin loader for the duration of discovery.
- `META-INF/services/api.Greeting`: file declaring the provider according to the **Service Provider Interface (SPI)** on the classpath.

### 4.1 Directory Structure

Create the following tree in `tccl-demo`:

```text
tccl-demo/
├── src/
│   ├── api/Greeting.java
│   ├── lib/Discovery.java
│   └── main/Launcher.java
├── plugin-src/
│   └── plugin/HelloGreeting.java
├── host-out/                           (host output)
└── plugin-out/
    └── META-INF/
        └── services/
            └── api.Greeting           (text file containing provider name)
```

**Create all directories before** compiling. The file `plugin-out/META-INF/services/api.Greeting` must have the exact binary name of the service interface; its content is the binary name of the provider, not the `.class` filename.

### 4.2 Shared Interface

File `src/api/Greeting.java`:

```java
package api;

public interface Greeting {
    String greet();
}
```

This interface will be loaded by the **system loader**; both the library and the plugin reference the exact same `Class<api.Greeting>`.

### 4.3 Library/Framework Code

File `src/lib/Discovery.java`:

```java
package lib;

import api.Greeting;
import java.util.ServiceLoader;

public final class Discovery {
    private Discovery() { }

    public static void inspect() {
        long fromParent = ServiceLoader.load(
                Greeting.class, Greeting.class.getClassLoader())
                .stream().count();

        long fromContext = ServiceLoader.load(Greeting.class)
                .stream().count();

        System.out.println("parent provider count=" + fromParent);
        System.out.println("context provider count=" + fromContext);

        for (Greeting greeting : ServiceLoader.load(Greeting.class)) {
            System.out.println(greeting.greet());
        }
    }
}
```

Explanation:

- `Greeting.class.getClassLoader()` is the system loader in this program. When that loader is passed explicitly, discovery **does not see** the provider that exists only in the plugin child loader.
- `ServiceLoader.load(Greeting.class)` selects **the TCCL of the current thread**.
- `stream().count()` counts the discovered provider types, **without requiring `greet()` to be called or instances to be created to count**. The `for` loop afterward actually instantiates the provider when needed.

### 4.4 Provider in the Plugin

File `plugin-src/plugin/HelloGreeting.java`:

```java
package plugin;

import api.Greeting;

public final class HelloGreeting implements Greeting {
    public String greet() {
        return "Hello from plugin";
    }
}
```

Text file `plugin-out/META-INF/services/api.Greeting`:

```text
plugin.HelloGreeting
```

The path and contents must match **exactly**. If the metadata file is missing, `ServiceLoader` will not detect the provider from the classpath via this SPI mechanism. If the provider is declared with the wrong name or does not implement the shared interface, you may encounter a `ServiceConfigurationError` when iterating over providers.

### 4.5 Startup Program and Setting TCCL

File `src/main/Launcher.java`:

```java
package main;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import lib.Discovery;

public final class Launcher {
    public static void main(String[] args) throws Exception {
        URL pluginUrl = Path.of("plugin-out").toUri().toURL();

        try (URLClassLoader pluginLoader = new URLClassLoader(
                new URL[]{pluginUrl}, ClassLoader.getSystemClassLoader())) {

            ClassLoader original =
                    Thread.currentThread().getContextClassLoader();

            System.out.println("provider visible to system=" +
                    isVisible("plugin.HelloGreeting",
                            ClassLoader.getSystemClassLoader()));

            Thread.currentThread().setContextClassLoader(pluginLoader);
            try {
                Discovery.inspect();
            } finally {
                Thread.currentThread().setContextClassLoader(original);
            }
        }
    }

    private static boolean isVisible(String name, ClassLoader loader) {
        try {
            loader.loadClass(name);
            return true;
        } catch (ClassNotFoundException e) {
            return false;
        }
    }
}
```

Notes:

- `pluginLoader` has the system loader as its parent so that it **shares the `api.Greeting` interface**, while `plugin.HelloGreeting` exists only in `plugin-out`.
- `isVisible(...)` checks whether the system loader can load the provider on its own, before TCCL is changed.
- `setContextClassLoader` only changes the thread's context, **without recreating `Discovery` or changing the defining loader** of that class.
- `finally` restores the old loader; `try-with-resources` closes the `URLClassLoader` after the task finishes. Closing the loader does not automatically release classes immediately if references to the loader/class/provider are still held elsewhere.

### 4.6 Compiling and Running

From the **`tccl-demo` directory**:

```bash
javac --release 17 -d host-out src/api/Greeting.java src/lib/Discovery.java src/main/Launcher.java
javac --release 17 -cp host-out -d plugin-out plugin-src/plugin/HelloGreeting.java
java -cp host-out main.Launcher
```

The `javac` and `java` commands above work the same way on Windows/Linux/macOS because only one root is needed each time. You need to create `host-out`, `plugin-out`, and the `META-INF/services/api.Greeting` file as instructed earlier.

Stdout was verified by compiling with `javac --release 17` and running the program:

```text
provider visible to system=false
parent provider count=0
context provider count=1
Hello from plugin
```

Analysis:

1. `provider visible to system=false`: the host/system loader does not find the child's provider; that is the **asymmetric visibility direction** in parent delegation.
2. `parent provider count=0`: a library using only the service interface's loader does not find the metadata/provider in `plugin-out`.
3. `context provider count=1`: TCCL now points to `pluginLoader`, so `ServiceLoader` finds `META-INF/services/api.Greeting` and then identifies the provider.
4. `Hello from plugin`: the provider is instantiated and invoked through the `api.Greeting` interface, a shared type defined by the parent.

This is a scaled-down version of a real need in plugin engines, service-provider mechanisms, and applications with multiple class loaders.

**If the `setContextClassLoader(pluginLoader)` line is omitted**, in this run `ServiceLoader.load(Greeting.class)` will typically use the main thread's default system loader; the result is `context provider count=0` and no plugin greeting line. You do not need to assume every thread/runtime has the same default TCCL to understand the rule: what matters is **which loader is the TCCL at the time of the call**.

## 5. Important Specification: Not Every API Reads TCCL

Comparison:

| API / operation | Selected loader | Automatically requires initializing target class? |
| --- | --- | --- |
| `ServiceLoader.load(Service.class)` | **Current TCCL** | Discovery can be lazy; instantiates provider during iteration/`get()` |
| `ServiceLoader.load(Service.class, loader)` | Explicitly passed loader | Provider is instantiated as needed during iteration |
| `ServiceLoader.loadInstalled(Service.class)` | **Platform loader** | Only searches matching "installed" providers; does not automatically search application classpath providers |
| `ServiceLoader.load(layer, Service.class)` | Passed **ModuleLayer** | Discovery within the layer and parent layers according to module rules |
| `Class.forName("pkg.Impl")` | **Defining loader of the class calling `forName`** | **Yes**, if the target class is not yet initialized |
| `Class.forName("pkg.Impl", false, loader)` | Passed loader | Does not require initializing the target class immediately |
| `someLoader.loadClass("pkg.Impl")` | Invoked loader and its delegation | Does not automatically require initialization |
| `Class.getResourceAsStream(...)` | According to class and module/resource rules | Does not automatically select TCCL just because the method is called |

Two important patterns:

```java
Class<?> type = Class.forName("plugin.HelloGreeting");
// Does not automatically use TCCL just because a plugin context exists.

ClassLoader context = Thread.currentThread().getContextClassLoader();
Class<?> selected = Class.forName(
        "plugin.HelloGreeting", true, context);
// Uses the explicitly selected loader.
```

This is an illustrative snippet, not a standalone runnable file. `Class.forName(String)` is a **caller-sensitive** API: its default loader is the defining loader of **the class containing the call**, not a framework caller class farther away in the stack and not TCCL.

**TCCL only takes effect for APIs that proactively read it**. Do not conclude that "changing TCCL will fix every `ClassNotFoundException`" or that "every platform API queries TCCL".

## 6. SPI Separates Contract from Implementation

The design goal is **dependency inversion** at the implementation layer:

```text
Framework/API -----------------> Service interface
                                      ^
                                      |
                              Provider implements
                                      |
                              Application/plugin
```

Platform code depends on a **stable contract**. The application supplies the provider without the framework needing to know the implementation name at compile time. **Discovery metadata** lets the runtime know which provider has implemented that interface.

A typical Java SE classpath SPI uses:

```text
META-INF/services/<fully.qualified.ServiceInterface>
```

and the content contains each provider name on one line. In the example, the exact file:

```text
META-INF/services/api.Greeting
```

contains:

```text
plugin.HelloGreeting
```

On Java 17, `ServiceLoader` supports both **unnamed modules / classpath provider-configuration files** and **named modules with `provides`**. TCCL helps select the loader scope in many cases, while the module system also adds provider lookup rules based on layer/readability.

### What Does ServiceLoader Actually Do?

- Selects the loader when creating `ServiceLoader`, then iterates over providers from module/SPI information.
- Usually **lazy**: calling `ServiceLoader.load` does not mean every implementation has already been instantiated.
- Finds provider classes and checks matching service contracts.
- Creates provider instances when iteration or `Provider.get()` requests them.
- Maintains a cache for loaded/instantiated providers within each `ServiceLoader` object; `reload()` clears the object's cache.
- **Not thread-safe** if the same `ServiceLoader` object is shared across multiple threads without synchronization.

The distinction between "finding provider metadata", "loading the provider class", and "instantiating the provider" is important for understanding when side effects occur.

## 7. In Practice: Which Platform APIs Need to See Application Implementations?

Some common patterns:

**Service Provider Interface (SPI):** `java.util.ServiceLoader` is the clearest example, with its `load(Class)` contract using TCCL. The service interface may be defined by Java SE, a library, or the application host; the provider is in the application JAR/plugin.

**JDBC driver:** The JDBC API and `DriverManager` are the platform part; the JDBC driver is a vendor library. Modern drivers can be discovered through the `java.sql.Driver` service-provider mechanism. However, `DriverManager` also applies its own class loader/access rules and initialization mechanism; do not infer from the SPI example that **all JDBC calling code simply uses TCCL directly**. When debugging, check the Java/JDBC documentation and runtime configuration.

**JAXP XML parser/transformer:** Platform factory APIs may need to select an application-provided provider; factory lookup has multiple sources (system properties, service configuration, default provider, etc.). Check the specific contract of each factory; do not assume all lookups always use one loader.

**Application servers, dependency injection, plugin frameworks:** A container may run framework code from a shared parent loader while needing to load implementation components in the application loader. Containers typically manage TCCL at request/deployment/lifecycle boundaries so discovery APIs can see the right application scope.

**Logging bindings and serializers:** Libraries select providers based on service metadata or their own mechanisms. For each library, you must check **whether it uses TCCL or not**, because there is no JVM rule requiring every factory to follow the same discovery approach.

The common thread is not that "high-level APIs must directly depend on lower-level classes", but that **the API needs a mechanism to find plugins/providers in the right scope** even though the place defining the API and the place providing the implementation may use different loaders.

## 8. Thread Context Does Not Automatically Follow Asynchronous Work
A new thread normally inherits TCCL at **creation time**, whereas an executor may reuse a previously created worker. Therefore, a discovery call in a worker can see a different provider than a call on the submitter, even when using the same `ServiceLoader.load(service)`. If a specific plugin context is needed, pass the `ClassLoader` explicitly or set/restore it directly inside the task with `try/finally`. Do not keep plugin A's `ServiceLoader` in a static cache shared across multiple applications; both caches and workers can prolong a loader's lifetime. Articles on thread inheritance and pools provide separate code traces.
## 9. Why Do the Parent Loader and Plugin Need to Share the Interface?

Consider two versions:

**Correct design:**

```text
[Host/system loader]:  api.Greeting
        ^
        |
[Plugin child loader]: plugin.HelloGreeting implements api.Greeting
```

The plugin loader asks its parent to load `api.Greeting`. Both the host and the plugin see **the same `Class<api.Greeting>` object**. `ServiceLoader<Greeting>` can cast the provider to `Greeting`.

**Incorrect design:**

```text
[Host/system loader]: api.Greeting (copy A)
[Plugin child loader]: api.Greeting (copy B), plugin.HelloGreeting
```

If the plugin defines **another copy of `api.Greeting`** via a child-first loader or improper package shading, `plugin.HelloGreeting` is not necessarily assignable to the host's interface even though both interfaces share the same name. During discovery, you may receive `ServiceConfigurationError: provider ... not a subtype`, `ClassCastException`, or a corresponding linkage/access error.

A type's Java identity is **binary name + defining loader**, not merely its name and file contents. When designing an SPI:

1. Place the **service interface and shared DTO/API contract** in a shared loader, usually the parent of the plugin loaders.
2. Keep only **private implementations/dependencies** in the plugin loaders.
3. Do not package a copy of the shared API into each plugin in a way that causes the plugin to redefine that class itself.
4. Check module exports/opens and API versions when the runtime uses named modules.

**TCCL cannot fix an identity error between two copies of a service interface.** It only determines the starting loader for discovery of APIs that use TCCL.

## 10. With JPMS, TCCL Is Not the Answer for Every Module

Since Java 9, service providers can be declared in `module-info.java`:

```java
// Module m.spi
module m.spi {
    exports api;
}
```

```java
// Module m.plugin
module m.plugin {
    requires m.spi;
    provides api.Greeting with plugin.HelloGreeting;
}
```

```java
// Module m.app
module m.app {
    requires m.spi;
    uses api.Greeting;
}
```

These are **three independent illustrative files**, each block belonging to `module-info.java` in the corresponding module; do not merge the three blocks into one file. A module wanting to use `ServiceLoader` in named-module code generally needs a corresponding `uses` declaration; the provider has `provides ... with ...` and matches the constructor/provider method according to the API contract.

When a custom `ModuleLayer` contains provider modules, the convenient choice is usually:

```java
ServiceLoader<Greeting> providers =
        ServiceLoader.load(pluginLayer, Greeting.class);
```

This is an illustrative snippet where `pluginLayer` is an already-created `ModuleLayer` object. This overload searches for providers in the layer and ancestor layers, and does not use classpath providers in unnamed modules as a fully equivalent mechanism.

At the same time, `ServiceLoader.load(service, loader)` can find providers in named modules associated with the loader and certain related module layers according to specification rules. Therefore, "TCCL = one loader" **does not always mean finding only a single named module**. In JPMS, you must consider **module layer, uses/provides, package/module mapping**, not just the parent loader diagram.

Loaded classes are also not necessarily able to access every member: module readability, exports, opens, and access modifiers still take effect. Service provider discovery does not bypass module access.

## 11. Important Design Limitations

| Issue | Accurate Explanation | How to Handle |
| --- | --- | --- |
| `Class.forName(name)` does not see the plugin | It uses the **caller class's** loader and does not automatically read TCCL | Use the overload passing a loader or a contract-based SPI |
| Parent loader does not see child classes | Parent-first delegation goes child → parent and does not automatically search downward | Have the discovery API proactively use TCCL/loader/module layer |
| `ServiceLoader` does not find the provider | Missing `META-INF/services`, wrong loader, wrong module declarations, or no provider | Check SPI/module configuration and the loader at iteration time |
| Provider throws `ServiceConfigurationError` | Wrong class name, not assignable, invalid constructor/provider method, or instantiation error | Inspect the cause, compare Class identity and SPI metadata |
| "Provider visible" but casting fails | The plugin defines its own copy of the same-named API interface | Place the API in a shared loader and use proper parent delegation |
| Forgetting to restore TCCL after a request | The thread pool retains the old loader, causing wrong provider routing/leaks | `try/finally`, lifecycle management |
| Wanting to retry provider after installing a new plugin | `ServiceLoader` caches per instance, and module/classloader lifecycle affects discovery | Create an appropriate loader/ServiceLoader or call `reload()` when meaningful |
| Provider exists in named module but app does not see it | `ModuleLayer`, `uses`, `provides`, or module accessibility is incorrect | Use the appropriate layer/loader overload and check the module graph |
| Changing TCCL to fix every loader error | Only effective for APIs using TCCL; does not change bytecode/linking already performed | Identify the exact lookup API and caller |
| Using a plugin loader to run untrusted code | TCCL/loader is not a comprehensive sandbox | Apply appropriate isolation and trust measures |

### Why Should `ServiceLoader` Not Be Cached JVM-Wide?

According to the Java 17 ServiceLoader API, `ServiceLoader.load(service)` uses the TCCL when creating the loader. If a server has multiple applications in the same JVM with different TCCLs, a globally cached `ServiceLoader` may retain application A's providers while serving B, or hold references that prevent A's class loader from being released. Depending on the use case, scope caches by deployment/request/module layer, manage lifecycle, and avoid static references that outlive the plugin.

When reloading code dynamically, `ServiceLoader.reload()` alone does not replace classes already defined by the JVM in a loader. To get a genuinely new versioned namespace, the framework may need a new loader/plugin layer and to release old references.

## 12. Debugging When a Parent API Does Not See a Child Implementation
Analyze along three independent axes: **visibility** (is the class/resource actually in the namespace of the loader used for lookup?), **identity** (do the provider and host share the same runtime interface?), and **discovery** (are the descriptor/module declaration/`ServiceLoader` overload correct?). Log the values of `Greeting.class.getClassLoader()`, `Thread.currentThread().getContextClassLoader()`, and `provider.getClass().getClassLoader()` directly in the calling code, and verify that the host classpath **does not accidentally contain the provider**. For JPMS, check `uses`/`provides` and `ModuleLayer`. If the call runs through an executor, collect information from the actual worker. `ServiceConfigurationError` indicates a configuration/provider error, unlike an empty discovery result.
## 13. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "A parent loader always sees every class of its child." | Parent-first lets a child ask its parent; the reverse direction does not exist by default. |
| "A platform API knows all plugins because they are in the same JVM." | It needs a discovery mechanism and appropriate loader/module selection. |
| "Changing TCCL makes every `Class.forName(String)` use the plugin loader." | No; `Class.forName(String)` uses the caller's defining loader. |
| "TCCL is the new parent of the application loader." | No; it is only a loader reference on the thread. |
| "TCCL is stored inside the provider's `Class<?>`." | No; a class has its own **defining loader**, which is not changed by TCCL. |
| "Calling `ServiceLoader.load` means all providers have already been instantiated." | Discovery can be lazy; iteration/`Provider.get()` performs many steps. |
| "Having the provider match the host-side interface class name is enough." | No; class identity requires the right defining loader, especially for the shared API interface. |
| "A single static `ServiceLoader` cache works well for all plugins." | It can cause wrong provider scoping or leak loaders on undeploy. |
| "TCCL provides security isolation." | No; permissions/isolation must be enforced at an appropriate architectural level. |
| "Since Java 17 has JPMS, TCCL is no longer needed." | TCCL is still used in SPI APIs; `ModuleLayer` also provides layer-based discovery where appropriate. |

## 14. Self-Check Questions

**1.** Why can the system loader usually not load a class defined by a child plugin loader?

**Answer:** Default parent delegation goes from child → parent. The parent does not automatically have a list of the child's classes and does not automatically search all child loaders.

**2.** Which loader does `ServiceLoader.load(Greeting.class)` select in Java 17?

**Answer:** According to the API, it selects the **TCCL of the calling thread**. It is equivalent to `ServiceLoader.load(Greeting.class, Thread.currentThread().getContextClassLoader())` in terms of loader selection.

**3.** Why does `Discovery.inspect()` in the example still find the plugin, even though `Discovery` is defined by the system loader?

**Answer:** `Discovery` calls `ServiceLoader.load(Greeting.class)`, and this API selects TCCL. `Launcher` set TCCL to the plugin loader, so the plugin's metadata and provider are found even though the defining loader of `Discovery` does not change.

**4.** Can you use `Class.forName("plugin.HelloGreeting")` instead of `ServiceLoader.load` and expect the same result when changing TCCL?

**Answer:** Not by default. `Class.forName(String)` selects the defining loader of the class containing the call site. If you want to specify the plugin loader, you must use the `Class.forName(name, initialize, pluginLoader)` overload.

**5.** Why does `api.Greeting` need to be placed in the parent/shared loader?

**Answer:** The host and plugin must use **the same interface definition**. If each loader defines its own copy, the same binary name can still be two different JVM types; the provider is not assignable to the host-side service type.

**6.** Should plugin A's TCCL be kept on a thread pool worker when request A finishes?

**Answer:** No. Request B could mistakenly use A's provider and hold references to plugin A. Restore the old context using `finally`.

**7.** When a Java module `m.app` uses `ServiceLoader`, when does it need to declare `uses api.Greeting;`?

**Answer:** In named-module code, if the module uses that service type to discover providers via `ServiceLoader`, the module declaration needs a corresponding `uses` declaration. The provider module declares an appropriate `provides ... with ...`.

**8.** If TCCL is `null`, do the APIs `ServiceLoader.load(service)` and `Class.forName(name, true, null)` have the same loader meaning?

**Answer:** No. According to `ServiceLoader`, a `null` loader represents the system loader (if available, falling back to bootstrap). For the `Class.forName` overload taking a `ClassLoader` parameter, `null` is the bootstrap loader.

**9.** In the example, if you omit the SPI descriptor while keeping the provider class, will `ServiceLoader` see the provider?

**Answer:** Not through the example's `META-INF/services` classpath mechanism. The class may exist, but ServiceLoader does not know which provider to consider. If named modules are used, the `provides` declaration is a different mechanism.

**10.** Should a platform API proactively scan every plugin loader in the JVM?

**Answer:** It should not. Namespaces/versions, isolation, and lifecycles differ. A discovery mechanism based on a specific **context/loader/module layer** is needed; TCCL is one way to express that context when the API supports it.

## 15. Summary of the Reasoning Process

When a platform API does not see an application implementation, ask:

1. Which loader/module does the **interface/service** reside in, and where does the implementation reside?
2. Does the **discovery code** use `Class.forName`, `ServiceLoader`, or which factory mechanism? Does that API read the **caller loader**, **TCCL**, **passed-in loader**, or **ModuleLayer**?
3. What is the **TCCL on the actually executing thread**? Is an executor/thread pool changing the context?
4. Has **provider metadata** been packaged properly (`META-INF/services` or `provides`)?
5. Do the host and provider use **the same class identity** for the service interface?
6. Is a **module access**, lifecycle/cache, or initialization error masking the root cause?

In summary: **A platform API needs to see application implementations because an open contract is only useful when the runtime can find and invoke providers supplied by the application.** Parent-first protects delegation order but does not automatically create downward visibility. **TCCL provides a thread-context-based loader choice** for APIs such as `ServiceLoader`, while other module/loader systems may use other explicit mechanisms.

Authoritative sources:

- [`java.util.ServiceLoader` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): overload using TCCL, how providers are declared, discovery in modules/classpath, lazy loading, cache/lifecycle.
- [`java.lang.Thread` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `getContextClassLoader`, `setContextClassLoader`, and context inheritance.
- [`java.lang.ClassLoader` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): parent delegation and defining loader.
- [`java.lang.Class` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `Class.forName` and the selected loader.
