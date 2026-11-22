# Separating the Host Application, Shared API, and Plugin Implementation with ClassLoader

## 1. Architectural Problem: Host Calling Plugins Without Depending on the Implementation

Suppose a Java application needs to load additional features after the application has been released: data exporters, content analyzers, connectors, drivers, or optional processors. If the host application (**host**) directly imports each implementation class, every added plugin requires modifying the host code, changes the dependency graph, and can cause library version conflicts.

A sustainable plugin architecture separates three roles:

1. **Host application (host):** orchestrates the lifecycle, discovers and selects plugins, invokes business logic through the contract, and manages errors, resources, and versions.
2. **Shared API (shared API/SPI):** stable communication types — interfaces, DTOs, exceptions, or metadata that **both the host and the plugin see under the same runtime class identity**.
3. **Plugin implementation (implementation):** feature code, its own dependencies, service providers, and classes/resources that only need to appear in the plugin's ClassLoader.

A common model:

~~~text
             Application/Parent ClassLoader
            +---------------------------------+
            | Host: plugin.host.PluginHost     |
            | API:  plugin.api.Plugin          |
            | API:  other DTOs / contracts     |
            +---------------------------------+
                         |
                         | parent delegation, shared API
                         v
             Child ClassLoader plugin A
            +---------------------------------+
            | plugin.impl.EchoPlugin          |
            | plugin-specific classes/JARs   |
            | META-INF/services/...          |
            +---------------------------------+

             Child ClassLoader plugin B
            +---------------------------------+
            | plugin.other.ReportPlugin       |
            | own dependency version          |
            +---------------------------------+
~~~

**The most important principle:** the host and the plugin must use **the same `Class<?>` object** for the `plugin.api.Plugin` type. Simply having the same name `plugin.api.Plugin` or identical bytecode is not enough; an interface with the same name created by two different defining ClassLoaders constitutes **two different runtime types**.

Article goals: design the three parts and the dependency boundary; run a Java 17+ example that loads a plugin from a JAR not on the system classpath; understand `ServiceLoader`, parent delegation, API packaging, type identity errors, version compatibility, lifecycle management, and how to extend with JPMS when needed.

## 2. Specific Responsibilities of the Three Parts

### 2.1. Host: The Orchestrator, Not Owning the Implementation

The host knows the plugin's **contract**, for example:

~~~java
Plugin plugin = /* instance created by discovery */;
String result = plugin.execute("hello");
~~~

This is a snippet **illustrating code inside a method**, not a standalone program; `Plugin` belongs to the shared API.

The host is typically responsible for:

- Selecting the plugin directory/artifact allowed to be loaded and determining compatible versions.
- Creating or selecting a ClassLoader/module layer for each plugin or group of plugins.
- Discovering implementations based on metadata, `ServiceLoader`, or a registry.
- Checking the API version, access permissions, and initialization conditions.
- Instantiating/starting, managing requests, stopping, and reclaiming plugin resources.
- Handling errors and preventing a failing plugin from disabling the entire host if the architecture allows it.

**The host should not need to import `plugin.impl.EchoPlugin`** in order to compile. If it imports a concrete implementation, the host may still run, but it defeats the goal of replacing plugins independently.

### 2.2. Shared API: The Meeting Point for Data Types

A small, stable contract:

~~~java
package plugin.api;

public interface Plugin {
    String id();
    String execute(String input);
}
~~~

The API needs to reside in an artifact/version managed by the host and **be defined once by a shared ClassLoader, usually the parent**.

Characteristics of a good API:

- Contains interfaces, enums, DTOs, or sufficient abstractions; **does not contain plugin engine/vendor details**.
- Types appearing in method signatures must also share identity, for example `PluginRequest`, `PluginResponse`, `PluginException`.
- Does not require the host to know private implementation classes.
- Has a versioning and compatibility policy: binary/source/API contract, default methods when appropriate, feature negotiation, or manifest version.
- If the API needs to be called by both sides, it must be visible according to the appropriate classpath/module rules.

**Pay attention to signature closure:** not only `Plugin.class`, but also all types in parameters, return types, callbacks, and exceptions crossing the boundary need an appropriate class identity architecture. If the interface is defined by the parent, but a DTO is packaged separately into both the host and the plugin, `ClassCastException` or `LinkageError` can still occur.

### 2.3. Plugin Implementation: Replaceable Code

Example:

~~~java
package plugin.impl;

import java.util.Locale;
import plugin.api.Plugin;

public final class EchoPlugin implements Plugin {
    @Override
    public String id() {
        return "echo";
    }

    @Override
    public String execute(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
~~~

The plugin only needs compile-time access to `plugin.api.Plugin`. The host application does not need a compile-time dependency on `EchoPlugin`.

Internal libraries needed by the plugin can be placed in the implementation JAR or arranged as separate JARs that **the plugin loader actually sees**. Do not confuse a build tool's dependency declaration with the JVM's classpath/loader paths at runtime.

## 3. ClassLoader Rules That Make This Architecture Work

### 3.1. Runtime Type Identity

A runtime class is typically identified by the pair:

~~~text
(binaryName, definingClassLoader)
~~~

For example, if the host loader `L_host` defines `plugin.api.Plugin`:

~~~text
Plugin_host = ("plugin.api.Plugin", L_host)
~~~

If the plugin loader `L_plugin` **defines an additional copy of the API with the same name**:

~~~text
Plugin_plugin = ("plugin.api.Plugin", L_plugin)
~~~

then:

~~~text
Plugin_host != Plugin_plugin
~~~

Even if the interface source is identical, an object implementing the `Plugin_plugin` version **does not automatically become an instance of** `Plugin_host`. Casting on the host side may throw `ClassCastException`; `ServiceLoader` may report the provider as **not a subtype** via `ServiceConfigurationError`.

**Proper design:** `L_plugin` **delegates loading** of contract packages (`plugin.api.*`) to the loader used by the host. In a standard parent-first `URLClassLoader`, if the API resides in the parent and the plugin JAR **does not contain a duplicate copy of the API**, the implementation naturally uses the exact same type as the host.

### 3.2. Parent Delegation and How the API Is Shared

~~~text
pluginLoader.loadClass("plugin.api.Plugin")
    -> parentLoader.loadClass("plugin.api.Plugin")
    -> returns the Class<Plugin> that the host also uses

pluginLoader.loadClass("plugin.impl.EchoPlugin")
    -> parent does not have the implementation class
    -> child searches in the plugin JAR
    -> EchoPlugin class is defined by child
~~~

The mechanism of `URLClassLoader` normally follows parent-first delegation. However, frameworks/containers may use child-first or namespace-dependent delegation. Therefore, **it is not enough to simply say "the plugin loader is a child"**: if a child-first policy picks the API copy inside the plugin JAR, identity can still be split.

One preventive measure is to explicitly manage namespaces:

- `java.*` and platform APIs: must not be shadowed arbitrarily.
- `plugin.api.*` and shared SDK packages: always delegate to the shared loader.
- `plugin.impl.*` and private dependencies: loaded from the plugin's loader when appropriate.
- Other shared libraries: explicitly decide whether to share them or allow separate versions; do not accidentally create an API whose signature depends on a type that only exists in one plugin.

### 3.3. ClassLoader Is Not a Security Boundary

ClassLoader supports class lookup, type identity, and a degree of namespace isolation. It is **not** a sufficient sandbox for running untrusted plugins: Java code in the same process can access system resources with the process's permissions, consume CPU/RAM, create threads, and interact with shared libraries.

For untrusted third-party plugins, consider **process isolation**, OS/container permissions, resource quotas, artifact signing/verification, and IPC protocols. Do not rely on `ClassLoader` or the legacy `SecurityManager` as the sole barrier.

## 4. Code and Artifact Organization: One API, Two Dependent Sides

A simple layout:

~~~text
project/
├── src/
│   ├── api/
│   │   └── plugin/api/Plugin.java
│   ├── host/
│   │   └── PluginHost.java
│   └── plugin/
│       └── plugin/impl/EchoPlugin.java
├── build/
│   ├── api/
│   ├── host/
│   └── plugin/
│       ├── plugin/impl/EchoPlugin.class
│       └── META-INF/services/plugin.api.Plugin
└── dist/
    └── plugin-echo.jar
~~~

**Compile-time dependency graph:**

~~~text
Shared API module/artifact
       ^             ^
       |             |
      Host         Plugin implementation

No compile dependency:
Host ----------> plugin.impl.EchoPlugin
~~~

**Runtime/class loader graph:**

~~~text
JVM launcher classpath:
    build/host + build/api
    => application loader defines host and Plugin API

URLClassLoader child:
    dist/plugin-echo.jar
    => implementation + provider descriptor
    => parent = application loader
~~~

The host compiles against the API; the plugin compiles against the API; however, **the deployed plugin JAR does not need to additionally package `plugin/api/Plugin.class`**. The Plugin API is already provided by the host at runtime.

With build tools:

| Role | Reasonable dependency | Warning |
|---|---|---|
| Host → shared API | `implementation` / Maven compile | The API must be on the host runtime classpath/module graph |
| Plugin → shared API | `compileOnly` (Gradle) or `provided` (Maven), if the host guarantees providing it | Ensure the API is actually present in the parent loader; do not let another version of the API get accidentally bundled |
| Plugin → private library | Runtime dependency/packaging appropriate for the plugin loader | Build resolution does not automatically make the JVM see the JAR if it is missing at deployment |
| Tests → host/API/implementation | Test dependencies for each part | Passing tests do not prove that the production classloader layout is similar |

This is a **common configuration approach**, not mandatory for every framework. With Gradle composite/multi-project builds, Maven modules, or JPMS, how artifacts and scopes are published differs; you need to inspect the **final plugin JAR/distribution** using `jar --list` and test running it with the exact JVM command.

## 5. Java SPI and ServiceLoader: Host Finding Implementations Without Importing Classes

Java supports the Service Provider Interface (**SPI**) based on `java.util.ServiceLoader`. Two components:

1. **Service type:** the `plugin.api.Plugin` interface that both the host and provider recognize.
2. **Provider configuration:** a text file at `META-INF/services/plugin.api.Plugin` containing the **binary name** of the provider class.

File contents:

~~~text
plugin.impl.EchoPlugin
~~~

The file name must be the **full binary name** of the service type, without `.class` or any other extension. Each provider is declared on its own line. The provider class in the example is public, has a default public no-arg constructor, and implements the exact runtime service interface.

The host uses the overload:

~~~java
ServiceLoader<Plugin> providers =
        ServiceLoader.load(Plugin.class, pluginLoader);
~~~

**Important:** the two-argument overload uses the **explicitly passed ClassLoader**, without having to hope that the ambient Thread Context ClassLoader points to the right plugin. The one-argument overload `ServiceLoader.load(Plugin.class)` uses the current thread's context ClassLoader instead and can produce different results.

`ServiceLoader` performs lazy discovery/instantiation; provider read errors or an invalid provider can throw `ServiceConfigurationError`. Therefore, a production host should establish a policy for handling provider errors and closing resources, rather than assuming discovery cannot fail.

## 6. Standalone Java 17+ Hands-On Practice: Host/API/Plugin Separated into Three Parts

This is a complete hands-on practice **requiring no Maven/Gradle and no library downloads from the internet**. It verifies:

- The host classpath contains only the **host** and the **API**, without the plugin implementation.
- The host cannot find the implementation on its own via the application loader.
- A child `URLClassLoader` finds the plugin from the implementation JAR.
- `ServiceLoader.load(service, pluginLoader)` discovers the provider.
- The provider implements **the exact same API interface object** as the host, so the host calls it directly via `Plugin` without reflective casting.
- The plugin library is used without the host **importing** `EchoPlugin`.

### 6.1. File `src/api/plugin/api/Plugin.java`

~~~java
package plugin.api;

public interface Plugin {
    String id();
    String execute(String input);
}
~~~

This is the shared contract for the entire system. It uses `String` to keep the example concise; in real applications, implementation-agnostic DTOs can be used.

### 6.2. File `src/plugin/plugin/impl/EchoPlugin.java`

~~~java
package plugin.impl;

import java.util.Locale;
import plugin.api.Plugin;

public final class EchoPlugin implements Plugin {
    public String id() {
        return "echo";
    }

    public String execute(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
~~~

### 6.3. Provider Descriptor File

Create the file:

~~~text
build/plugin/META-INF/services/plugin.api.Plugin
~~~

Exact single-line content (trailing newline allowed):

~~~text
plugin.impl.EchoPlugin
~~~

This content must go into the **plugin JAR**, not just exist in the source tree. In this example, creating the file directly under `build/plugin` after compilation is sufficient.

### 6.4. File `src/host/PluginHost.java`

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ServiceLoader;
import plugin.api.Plugin;

public final class PluginHost {
    public static void main(String[] args) throws Exception {
        ClassLoader hostLoader = PluginHost.class.getClassLoader();
        System.out.println("hostApiLoaderSame="
                + (hostLoader == Plugin.class.getClassLoader()));

        try {
            Class.forName("plugin.impl.EchoPlugin", false, hostLoader);
            System.out.println("hostCannotLoadPlugin=false");
        } catch (ClassNotFoundException expected) {
            System.out.println("hostCannotLoadPlugin=true");
        }

        URL pluginUrl = Path.of("dist/plugin-echo.jar").toUri().toURL();
        try (URLClassLoader pluginLoader =
                     new URLClassLoader(new URL[] { pluginUrl }, hostLoader)) {
            int count = 0;
            for (Plugin plugin : ServiceLoader.load(Plugin.class, pluginLoader)) {
                count++;
                System.out.println("pluginImplLoaderIsChild="
                        + (plugin.getClass().getClassLoader() == pluginLoader));
                System.out.println("sharedApiIdentity="
                        + (plugin.getClass().getInterfaces()[0] == Plugin.class));
                System.out.println("pluginId=" + plugin.id());
                System.out.println("result=" + plugin.execute("hello"));
            }
            System.out.println("pluginsFound=" + count);
        }
    }
}
~~~

**Several important details:**

- `PluginHost` only imports `plugin.api.Plugin`. It does not import or directly instantiate `EchoPlugin`.
- Calling `Class.forName(..., false, hostLoader)` intentionally demonstrates that the application loader cannot find the plugin. It does **not** require initialization.
- `URLClassLoader` is passed the plugin JAR URL and the parent `hostLoader`. In this classpath setup, `plugin.api.Plugin` comes from the parent.
- `ServiceLoader.load(Plugin.class, pluginLoader)` finds provider metadata using the specified loader and instantiates providers during iteration.
- `getInterfaces()[0]` is a sufficient check **specifically for the `EchoPlugin` class in this example**, where the class directly implements only one interface. In production code, you must not assume the first interface in the array is always the API; `Plugin.class.isAssignableFrom(providerClass)` can be used when appropriate.
- `try-with-resources` closes the `URLClassLoader` after use. It closes loader resources, and **does not guarantee that classes/plugin objects are unloaded immediately**.

### 6.5. Compiling and Packaging on Linux/macOS

From inside the `project` directory (with the exact source tree described):

~~~sh
mkdir -p build/api build/host build/plugin/META-INF/services dist

javac --release 17 -d build/api \
    src/api/plugin/api/Plugin.java

javac --release 17 -cp build/api -d build/plugin \
    src/plugin/plugin/impl/EchoPlugin.java

printf 'plugin.impl.EchoPlugin\n' \
    > build/plugin/META-INF/services/plugin.api.Plugin

jar --create --file dist/plugin-echo.jar -C build/plugin .

javac --release 17 -cp build/api -d build/host \
    src/host/PluginHost.java

java -cp "build/host:build/api" PluginHost
~~~

The `:` character is the Linux/macOS classpath separator; the trailing `\` at the end of a line is POSIX shell line continuation, and is not used the same way in PowerShell.

### 6.6. Compiling and Running on Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force build/api, build/host, build/plugin/META-INF/services, dist | Out-Null

javac --release 17 -d build/api src/api/plugin/api/Plugin.java

javac --release 17 -cp build/api -d build/plugin src/plugin/plugin/impl/EchoPlugin.java

[System.IO.File]::WriteAllText(
    "build/plugin/META-INF/services/plugin.api.Plugin",
    "plugin.impl.EchoPlugin" + [Environment]::NewLine,
    [System.Text.UTF8Encoding]::new($false)
)

jar --create --file dist/plugin-echo.jar -C build/plugin .

javac --release 17 -cp build/api -d build/host src/host/PluginHost.java

java -cp "build/host;build/api" PluginHost
~~~

The PowerShell snippet above requires a JDK 17+ runtime environment and a PowerShell version that supports the `::new` constructor syntax (Windows PowerShell 5+ or PowerShell 7). If using CMD, create the provider file with an appropriate text tool and use `;` in `-cp`.

### 6.7. Verified Exact Stdout

~~~text
hostApiLoaderSame=true
hostCannotLoadPlugin=true
pluginImplLoaderIsChild=true
sharedApiIdentity=true
pluginId=echo
result=HELLO
pluginsFound=1
~~~

The code in this practice was compiled with `javac --release 17` and executed successfully with the JDK. The plugin JAR does not need a `Main-Class` because the host is the executable entry point; `plugin-echo.jar` is a **provider artifact**, not a standalone program.

### 6.8. Why Is Each Line Important?

| Output | Evidence |
|---|---|
| `hostApiLoaderSame=true` | The host and shared API are loaded by the same defining loader |
| `hostCannotLoadPlugin=true` | The plugin implementation is not on the application classpath |
| `pluginImplLoaderIsChild=true` | The child `URLClassLoader` defines the implementation |
| `sharedApiIdentity=true` | The interface that the implementation directly implements is **the exact same `Plugin.class`** used by the host |
| `pluginId=echo` | The plugin was instantiated and invoked via the interface successfully |
| `result=HELLO` | The host executed business logic through the contract without needing to import the implementation |
| `pluginsFound=1` | The provider descriptor/JAR/ServiceLoader lookup works properly, detecting exactly one provider |

`ClassLoader.toString()` and absolute file paths are not printed because they can differ across machines/JDKs; the example verifies via **object identity** and business logic.

### 6.9. Inspecting the Packaged Artifact

~~~sh
jar --list --file dist/plugin-echo.jar
~~~

Important entries:

~~~text
plugin/impl/EchoPlugin.class
META-INF/services/plugin.api.Plugin
~~~

**There should not be** `plugin/api/Plugin.class` inside the plugin JAR in this architecture. If it is present, in the parent-first URLClassLoader of the demo the parent API may still win, but a child-first loader or another framework could load the duplicate copy into the child and create two interface types. Therefore, packaging constraints should be clearly established from the start.

In production, additionally check implementation dependencies, resource collisions, duplicate providers, and `META-INF/services` paths when using shaded/uber JARs. Shading tools need to **merge service descriptors** if multiple libraries publish providers.

## 7. Scaling to Multiple Plugins and Loader Strategies

There are three layout approaches depending on your needs. **A single shared loader** is simple when all plugins are released together and use compatible dependencies, though a given binary name can only have one definition in that loader. **A separate loader per plugin** is suitable when different library versions, independent upgrades, or individual shutdowns are needed; it must still ensure the shared API is defined by the parent. **JPMS `ModuleLayer`** offers strategies with one or multiple loaders for modules and uses `uses`/`provides` declarations, unlike classpath SPI which uses `META-INF/services`. Choosing a model, testing name collisions, and evaluating trade-offs between isolation, state, and memory are practiced in depth in the following articles.

## 8. Plugin Lifecycle: Load, Use, Stop, and Unload

The host manages the states `DISCOVERED → VALIDATED → LOADED → STARTED → STOPPING → STOPPED → RELEASED`, with rollback when startup fails. Before closing the loader, the host must block new work, drain/cancel running tasks, invoke stop hooks, unregister callbacks/listeners, close streams/connections/executors, clean up `ThreadLocal`/TCCL/caches, and then drop references. `URLClassLoader.close()` closes the resources managed by the loader but does not force the JVM to unload classes or stop threads. The articles on initialization, shutdown, and hot reload dive deeper into this mechanism; here, the key responsibility is that **the host owns the lifecycle**, while the plugin provides hooks/cleanup according to the contract.

## 9. API Version Compatibility and Plugin-Private Dependencies

The shared API requires **binary compatibility** between the host and all deployed plugins. Removing methods, changing JVM descriptors, or changing constructor/record components can cause `NoSuchMethodError`, `AbstractMethodError`, or linkage errors, even with the same shared loader. Individual plugins can use `codec v1/v2` in separate loaders as long as `codec.*` is not exposed through SPI method signatures; map them to shared DTOs/schemas at the boundary. A faulty plugin can cause exceptions, deadlocks, or resource exhaustion, so the host must have error/timeout/quota policies; separate loaders only provide namespace and dependency isolation. If multiple incompatible API versions exist, migration/adapters or a new version contract are needed, not just swapping JARs.

## 10. Troubleshooting Process When a Plugin Does Not Work

### 10.1. Verify the Correct Artifacts and Loader

1. Was the host built **depending only on the shared API**, or does it still import implementation classes?
2. Are the API JAR/classes on the host's **parent/runtime**?
3. Does the plugin JAR contain `plugin/impl/EchoPlugin.class` and the provider descriptor `META-INF/services/plugin.api.Plugin`?
4. Was the API class **duplicately packaged** into the plugin implementation artifact?
5. Did the `URLClassLoader` or custom loader receive the plugin's correct URLs/resources? Nested JARs are not automatically loaded by a standard `URLClassLoader` without a launcher that understands their structure.
6. Do `Plugin.class.getClassLoader()` and `provider.getClass().getInterfaces()[0].getClassLoader()` have the proper parent-shared relationship? (Only use `getInterfaces()[0]` directly when you know the provider's structure.)
7. Is `Plugin.class.isInstance(provider)` true?
8. Is ServiceLoader using the explicit overload or the TCCL? Is the plugin still on the right loader when enumerating providers?
9. Do the API version and runtime private dependencies match the actually deployed artifacts?
10. Does the plugin have stop hooks/resources/threads still retaining the old loader?

### 10.2. Error Table and Inspection Guide

| Symptom | Likely Causes to Check | Resolution |
|---|---|---|
| `ServiceLoader` returns 0 providers | Missing/incorrect descriptor, provider not on the runtime loader path | Check `META-INF/services`, binary name, JAR layout, and loader |
| `ServiceConfigurationError: not a subtype` | Provider implements **an API copy from another loader** or provider config is wrong | Compare the identity of `Plugin.class` from the host and the interface from the provider |
| `ClassCastException: plugin.impl.EchoPlugin cannot be cast to plugin.api.Plugin` | Split API identity or provider does not implement the real interface | Enforce that the plugin API is defined by the parent; remove duplicate APIs |
| `ClassNotFoundException` on implementation | Child loader cannot see the JAR/wrong classpath, wrong binary name | Check loader URLs, artifacts, and package names |
| `NoClassDefFoundError` when invoking plugin | Missing private transitive dependency, prior initialization error | Read `Caused by` and identify missing classes/libraries |
| `NoSuchMethodError`/`AbstractMethodError` | Incompatible API/plugin binary versions | Compare compiled ABI and runtime artifacts |
| `IllegalAccessError`/`InaccessibleObjectException` | Java access/JPMS exports/opens | Check package, defining loader, and module rules |
| Changing one plugin breaks another | Shared loader cannot isolate dependency versions | Consider a separate loader per plugin and a stable shared API |
| Old plugin stays alive after reload | Registry, TCCL, threads, or ServiceLoader/cache retain references | Stop, clean up, close the loader, and drop references |
| Works in local IDE, plugin not found when deployed | IDE classpath differs from launcher/JAR distribution | Run the released artifact and verify the actual command |
| Plugin class has the same name as parent | Parent-first prioritizes host class or child-first creates duplicate type | Define a clear namespace/delegation policy |

### 10.3. A Quick Diagnostic Check in Code

~~~java
static void inspectPlugin(Class<?> api, Object plugin) {
    Class<?> impl = plugin.getClass();
    System.out.println("api=" + api.getName());
    System.out.println("apiLoader=" + api.getClassLoader());
    System.out.println("impl=" + impl.getName());
    System.out.println("implLoader=" + impl.getClassLoader());
    System.out.println("apiAssignable=" + api.isInstance(plugin));
}
~~~

This is an **illustrative method**, placed inside an appropriate class. A ClassLoader's `toString()` is useful for debugging but is not a canonical ID; when an exact check is needed, compare reference identity directly. If the application has multiple module layers, also print `api.getModule()` and `impl.getModule()`.

## 11. Common Architectural Mistakes

Mistakes worth checking before release: the host directly imports an implementation; a plugin JAR bundles a copy of the shared API that gets defined by a child-first loader; a private library type appears in a public method signature; `META-INF/services` or runtime plugin URLs are missing; the wrong TCCL is used during discovery; API binary compatibility is not verified; the loader is closed while the plugin is still running; listeners/threads/caches are retained after stop; or `ClassLoader` is treated as a security sandbox. Each case requires verifying **the defining loader, actual artifact, service descriptor, runtime exception, and lifecycle ownership**. The following in-depth articles provide experiments for each mistake.

## 12. Self-Check Questions and Exercises

1. By what principles should the three roles—host, shared API, and implementation—be separated?
2. Why does the host only need a compile dependency on the `Plugin` interface rather than `EchoPlugin`?
3. What elements make up `Class<?>` identity? Why can two interfaces with the same binary name still be different?
4. Why must the shared API be loaded from a loader accessible to both the host and the plugin?
5. With a parent-first `URLClassLoader`, what happens when the child looks up `plugin.api.Plugin`?
6. If the plugin JAR also contains `plugin/api/Plugin.class`, what risk arises with a child-first loader?
7. What content must `META-INF/services/plugin.api.Plugin` contain?
8. How do `ServiceLoader.load(Plugin.class, pluginLoader)` and `ServiceLoader.load(Plugin.class)` differ in terms of loader selection?
9. In the example, why can `hostCannotLoadPlugin=true` still result in `pluginsFound=1`?
10. What does `sharedApiIdentity=true` prove beyond comparing binary names?
11. Why does the plugin JAR not need a manifest `Main-Class`?
12. When are Gradle `compileOnly` or Maven `provided` appropriate for an API provided by the host?
13. If plugins A and B use different versions of a codec, when is creating two separate plugin loaders useful?
14. Why should private codec classes not appear in the public method signatures of the Plugin API?
15. When ServiceLoader reports `not a subtype`, which interface's classloader needs to be checked?
16. Why does merely closing `URLClassLoader` not guarantee that the old plugin is garbage-collected?
17. Does TCCL automatically change the ClassLoader of an already defined class? When does ServiceLoader use TCCL?
18. If you want to migrate to JPMS, which descriptor directives correspond to the API, host, and implementation?
19. If a plugin is untrusted code, does a separate ClassLoader replace process isolation?
20. In a production plugin application, what additional rules do you need for versioning, resource limits, shutdown, and observability?

**Completion criteria:** you independently compile the three Java 17+ source sets, package the provider JAR properly, run the host, and explain all seven lines of stdout; draw the dependency graph and classloader hierarchy; and identify how to preserve shared API identity, configure `ServiceLoader`, separate private dependencies, and manage the plugin lifecycle.

## 13. Official References

- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, runtime loader semantics, `loadClass`.
- [Java SE 21 — URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): loading classes/resources from JAR/directory URLs, closing resources.
- [Java SE 21 — ServiceLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html): service/provider contract, configuration file, loader/layer overloads, ServiceConfigurationError.
- [Java SE 21 — ModuleLayer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html): module layers and loader mapping for JPMS.
- [JVMS Java SE 21 — Loading/Linking](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html): defining/initiating loaders, runtime identity, and loading constraints.
- [Gradle Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): API/implementation dependency separation when designing multi-project builds.
- [Maven Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): scopes such as `compile`, `provided`, `runtime`, and `test`.

**Conclusion:** plugin architecture is not just "creating a ClassLoader". The architecture operates sustainably when **the host owns the shared contract**, **the ClassLoader hierarchy unifies the API's runtime identity**, and **the implementation and private dependencies** are packaged, loaded, and lifecycle-managed under separate policies. The example was verified with Java 17-compatible bytecode; framework/JPMS variants need to choose appropriate API discovery and module/loader mapping.
