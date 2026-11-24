# Parent-First vs. Plugin-First Delegation and Mandatory Delegation Exceptions

## 1. The Dependency Isolation Problem for Java Plugins

Suppose a host application and a plugin both need a class named `com.acme.lib.Parser`, but the host packages version 1 of the library while the plugin needs version 2. The two versions may differ in method signatures, behavior, or dependencies. Placing a `ClassLoader` between the host and the plugin can let each side use its own copy, yet the decision to **load from the parent first (parent-first)** or **load from the plugin first (plugin-first/child-first)** determines which version gets chosen.

There is also an opposite constraint: the SPI interface and the data types used to communicate between host and plugin **must have a unified Java identity**. If the host loads `com.acme.api.Plugin` with class loader A while the plugin loads a *same-named copy* with class loader B, the two `Class<?>` objects do not become the same type merely because their names match. In Java, a class's identity is tied to its **binary name and defining class loader**; two identically named classes defined by two different loaders are two distinct runtime types.

Therefore, class-loading design for an extensible system typically combines:

- **Parent-first** for classes belonging to the host, the JDK, and shared communication contracts.
- **Plugin-first** for implementation code and private dependencies owned by the plugin, when version conflicts must be avoided.
- **Mandatory parent-delegation exceptions** even under a plugin-first policy, especially for APIs/SPIs exchanged between host and plugin.

The goal is not merely "the plugin can load classes"; the host must also cast, call APIs, receive callbacks, pass DTOs, register `ServiceLoader` providers, and handle exceptions across the boundary consistently.

## 2. Class Loader Delegation Mechanics

### 2.1. Parent-First Is the Default Behavior of ClassLoader

In its standard implementation, `ClassLoader.loadClass(String)` prioritizes in the following order:

1. Check `findLoadedClass(name)`: has the class already been loaded/defined by the **current loader**?
2. Delegate to the **parent loader** (or bootstrap when there is no parent).
3. If the parent cannot find it, try `findClass(name)` in the current loader.
4. If found nowhere, throw `ClassNotFoundException`.

In `loadClass(name, resolve)`, the `resolve` parameter decides whether to call `resolveClass` after locating the class. Do not skip the cache check and synchronization mechanism when writing a custom precedence algorithm.

`URLClassLoader` also follows this default delegation. Creating a `URLClassLoader` pointing to a plugin JAR is **not enough** to separate versions when the parent already sees a class with the same name: if the parent finds it first, the plugin's class may not be selected.

```text
Parent-first when requesting com.acme.lib.Parser

pluginLoader.loadClass("com.acme.lib.Parser")
    |
    +-- already loaded by pluginLoader? -- yes --> reuse
    |
    +-- ask host/parent ------------------ yes --> take class found by parent
    |
    +-- parent did not find it --------------> pluginLoader.findClass(...)
```

### 2.2. Plugin-First Reverses the Order for a Group of Classes

For a set of names owned by a plugin, a custom loader can try `findClass(name)` from the plugin's JARs/directories **before** delegating to the parent. When the plugin has its own copy of the library, the plugin's class wins; when the plugin does not have it, it can still fall back to the parent.

```text
Plugin-first for com.acme.plugin.lib.Parser

pluginLoader.loadClass("com.acme.plugin.lib.Parser")
    |
    +-- already loaded? ------------------ yes --> reuse
    |
    +-- class exists in plugin? ---------- yes --> define plugin's class
    |
    +-- not found in plugin -----------------> try host/parent
```

**Policies should be applied by owned name groups**, not by a blanket "child-first for everything" slogan. Within a single loader, classification rules are normally decided before `loadClass` runs; do not let results depend on when a plugin happens to be initialized.

### 2.3. "Loading" Does Not Mean "Defining"

A loader receiving a request may **return a class defined by its parent**; the class is not necessarily defined by the loader that received the call. This explains why we can have a separate `PluginLoader` while `api.Plugin.class.getClassLoader()` is still the host loader.

Useful diagnostic information:

- `type.getName()`: class name.
- `type.getClassLoader()`: defining class loader (may be `null` for bootstrap-defined classes).
- `type.getModule()`: module containing the class on Java 9+.
- `loader.getParent()`: parent structure of the loader; does not imply all classes coming through the parent belong to a single JAR.

Class-loading order affects identity, linking, package access, and library visibility; it does not by itself change Java signatures or make an object from two different class definitions compatible.

## 3. Choosing Parent-First vs. Plugin-First by Scenario

| Scenario | Appropriate priority | Reason |
| --- | --- | --- |
| Host–plugin API/SPI (shared interfaces, DTOs, exceptions) | **Mandatory parent-first by contract** | Preserves a single runtime type for casting/callbacks |
| Java platform classes (`java.*`) | **Delegate to Java platform/parent** | Do not redefine platform classes; the JVM prevents ordinary class loaders from defining names under `java.*` |
| Runtime bridges, framework interfaces managed by the host and crossing boundaries | Usually **parent-first** | Avoids two differently identified copies for the same contract |
| Plugin's private implementation | Plugin loader defines it (plugin-first or parent fallback when absent in parent) | Plugin code has its own lifecycle |
| Private dependency with a different version from the host | **Plugin-first** when policy allows | Avoids forcing plugins onto the host's version |
| Dependency that must genuinely share one instance/type with the host | **Parent-first** | Keeps contract, class identity, object model, and lifecycle unified |
| Library with only one version, not crossing boundaries and having no conflicts | Can be parent-first | Simpler if deployment strategy allows |
| Config/resources, `META-INF/services` | **Separate resource lookup policy** | `getResource(s)` and `ServiceLoader` do not necessarily follow the same order as `loadClass` |

Parent-first is not automatically wrong: it reduces duplicate class loading, suits host-controlled APIs, and is simpler in single-classpath applications. Nor is plugin-first inherently safer: it can produce two API definitions and cause `ClassCastException` or `ServiceConfigurationError`.

The decision principle is: **which classes need the same identity on both sides, which classes must be version-isolated, and which classes have their lifecycle owned by the host**.

## 4. Mandatory Delegation Exceptions in a Plugin-First Design

### 4.1. Java Platform Classes and Protected Namespaces

Do not attempt to load/define copies of JDK classes to override platform behavior. For `java.*`, custom loaders must delegate; the JVM even restricts ordinary class loaders from defining classes whose names begin with `java.`. Other platform packages may live in modules such as `java.base`, `java.sql`, `java.logging`, `java.xml`, or carry `javax.*`/`jdk.*` names; classify according to actual runtime modules and host policy.

Do not mechanically assume "all `javax.*` and `jakarta.*` belong to the JDK":

- `jakarta.*` is typically external libraries/frameworks outside the JDK; when `jakarta.servlet.*` or `jakarta.validation.*` contracts cross the boundary, the host should designate the shared version.
- A private dependency with a `javax.*` namespace may be an off-platform library; policy must be based on **ownership and contract**, not just a guessed prefix.
- For standard Java APIs, classes should still be loaded from the platform/parent rather than shadowed by a copy inside a plugin.

### 4.2. Host API/SPI and Communication Types

Suppose the host defines:

```java
package com.acme.api;

public interface Plugin {
    Result execute(Request request);
}
```

This is an **illustrative interface snippet**; `Request` and `Result` also belong to the shared API, not built-in JDK classes. If a plugin bundles its own copy of `Plugin` or `Request`, the host may see an object that "implements Plugin" in source yet still fail at runtime. You must **delegate all Java types that can appear across the boundary**, including:

- SPI interfaces/abstract classes and base classes.
- DTOs, enums, records, generic bounds, exceptions, and annotations shared between host and plugin.
- Callbacks/listeners, service contracts, event types, and types appearing in method signatures.
- Supporting APIs directly referenced by the types above that genuinely belong to the shared contract.

Do not list only one primary interface and forget supporting types. A `Plugin.execute(Request)` signature works only if both `Plugin` and `Request` have the same runtime identity on the host and plugin sides.

The proper packaging approach is for the host to provide a **shared API JAR**; plugins compile against this API without defining a second copy at runtime. You can declare the dependency as `compileOnly`/`provided` (depending on the build tool), inspect JAR contents at packaging time, and enforce delegation exceptions for the API namespace.

**Important:** parent-first only tries the parent first; if the parent lacks the API, the default implementation can still fall back to a copy inside the plugin. The system should **validate up front that required contracts exist in the parent** and reject plugins that fail this condition, rather than silently accepting a private API definition.

### 4.3. Shared Bridges Managed by the Host

Depending on the architecture, APIs such as a logging facade, tracing/metrics APIs, dependency injection extension contracts, or transaction callbacks may also need to be shared. For instance, if host and plugin pass `org.slf4j.Logger` or register a framework callback consumed by the host, interfaces appearing on both sides should have one consistent definition. The internal implementation/backend inside the plugin may still need separation.

Do not put every framework library onto the parent-first list merely because its name is familiar. Ask:

1. Do **objects of this type** cross the host–plugin boundary?
2. Who manages that type's lifecycle/registry?
3. Which ABI and version does the host commit to providing?
4. Which transitive dependencies require matching identity to avoid linkage errors?

If the answer is merely "the plugin uses the library internally," plugin-first may be more suitable.

## 5. Writing a Correct loadClass Policy and Avoiding Bad Fallbacks

A practical decision can be expressed as a policy table:

| Class group | Rule | When missing |
| --- | --- | --- |
| `java.*` and platform classes | Parent/platform first | Fail if absent from platform |
| `com.acme.api.*` (shared contract) | **Load only from validated parent** | Report missing shared API; do not use plugin copy |
| `com.acme.plugin.*` | Look in plugin first | Can fail fast if this must be an internal implementation |
| `com.acme.vendor.private.*` | Plugin-first; fallback per explicit policy | Avoid accidentally picking an incompatible host version |
| Other packages | Parent-first by default, unless policy allows isolation | Avoid shadowing undeclared classes |

This is an **illustrative** policy. Package names are conventions of each system, not a built-in list inside `ClassLoader`.

Pseudocode of a loader with exceptions:

```text
loadClass(name, resolve):
    lock by class name if loader is parallel-capable
    if findLoadedClass(name) != null: return already loaded class

    if isPlatform(name):
        result = delegateToParent(name)
    else if isSharedHostApi(name):
        result = delegateToParentStrictly(name)
        # do not fall back to plugin if required API is missing
    else if isPluginOwned(name):
        result = findClassInPlugin(name)
        # fall back to parent only if policy permits and class is absent in plugin
    else:
        result = delegateToParentThenFindLocal(name)

    if resolve: resolveClass(result)
    return result
```

When implementing `loadClass(String, boolean)` yourself:

- Always check `findLoadedClass` first to avoid redefining a class in the same loader.
- Use `synchronized (getClassLoadingLock(name))` or an equivalent mechanism to handle concurrent loads; the subclass's parallel-capable characteristics must be well understood.
- Fall back to the parent only when `findClass` throws **`ClassNotFoundException`** for an absent class. Do not swallow `LinkageError`, `SecurityException`, or genuine verification/initialization errors to silently try another version.
- Honor `resolveClass` according to the `resolve` parameter.
- Calling `super.loadClass(name, false)` in a subclass loader can perform **parent-first followed by local search in the current loader**. If you need **parent-only** mode for a shared API, call `getParent().loadClass(name)` with proper bootstrap handling and explicit validation to avoid unintended local fallbacks.
- Choose prefixes accurately; `name.startsWith("com.acme.api.")` differs from `name.startsWith("com.acme.api")`, as the version without a trailing dot can accidentally match `com.acme.application.*`. If there is a class named `com.acme.api` itself, handle exact names if policy requires.
- Already-loaded classes do not automatically move to another loader when policies change or JARs are swapped. Upgrading a plugin independently typically requires creating a **new loader** and releasing all references to the old one.

If strong isolation is needed, one dedicated loader **per plugin** is better than one shared loader for all plugins: two plugins can then use two versions of `com.vendor.Json` without stepping on each other. The host must verify that plugin A's private types do not leak directly into plugin B's API.

## 6. Runnable Java 17+ Example: Parent-First, Plugin-First, and API Exceptions

The following example runs from a **single file**, creating two independent sets of classes in a temporary directory and compiling them using the JDK's `JavaCompiler`:

- **Host classes** contain `demo.api.Greeting` and `demo.lib.Message` returning `host-library`.
- **Plugin classes** also contain a copy of `demo.api.Greeting` and a different `demo.lib.Message` returning `plugin-library`, along with `demo.plugin.Hello` using them.
- A `PluginLoader` tries the parent or plugin first according to policy. With `delegateSharedApi=true`, the `demo.api.*` namespace is always delegated to the host. The last case intentionally omits this exception to demonstrate the risk.

File **`DelegationPolicyDemo.java`**:

```java
import java.io.IOException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class DelegationPolicyDemo {
    static final class PluginLoader extends URLClassLoader {
        private final boolean pluginFirst;
        private final boolean delegateSharedApi;

        PluginLoader(Path pluginClasses, ClassLoader parent,
                     boolean pluginFirst, boolean delegateSharedApi)
                throws IOException {
            super(new URL[]{pluginClasses.toUri().toURL()}, parent);
            this.pluginFirst = pluginFirst;
            this.delegateSharedApi = delegateSharedApi;
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            synchronized (getClassLoadingLock(name)) {
                Class<?> type = findLoadedClass(name);
                if (type == null) {
                    boolean alwaysParent =
                            name.startsWith("java.")
                            || (delegateSharedApi
                                && name.startsWith("demo.api."));
                    if (alwaysParent || !pluginFirst) {
                        type = super.loadClass(name, false);
                    } else {
                        try {
                            type = findClass(name);
                        } catch (ClassNotFoundException notInPlugin) {
                            type = super.loadClass(name, false);
                        }
                    }
                }
                if (resolve) {
                    resolveClass(type);
                }
                return type;
            }
        }
    }

    static Path source(Path root, String relative, String code)
            throws IOException {
        Path file = root.resolve(relative);
        Files.createDirectories(file.getParent());
        Files.writeString(file, code, StandardCharsets.UTF_8);
        return file;
    }

    static void compile(JavaCompiler compiler, Path output,
                        Path... files) throws IOException {
        Files.createDirectories(output);
        List<String> args = new ArrayList<>(
                List.of("--release", "17", "-encoding", "UTF-8",
                        "-d", output.toString()));
        for (Path file : files) {
            args.add(file.toString());
        }
        if (compiler.run(null, null, null,
                args.toArray(String[]::new)) != 0) {
            throw new IllegalStateException("Compilation failed");
        }
    }

    static Object instance(ClassLoader loader) throws Exception {
        return Class.forName("demo.plugin.Hello", true, loader)
                .getDeclaredConstructor().newInstance();
    }

    static String message(Object provider) throws Exception {
        return (String) provider.getClass()
                .getMethod("message").invoke(provider);
    }

    static void deleteTree(Path root) throws IOException {
        try (Stream<Path> paths = Files.walk(root)) {
            for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                Files.deleteIfExists(path);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Run with a JDK, not a JRE");
        }
        Path root = Files.createTempDirectory("delegation-demo-");
        try {
            Path hostSrc = root.resolve("host-src");
            Path pluginSrc = root.resolve("plugin-src");
            Path hostClasses = root.resolve("host-classes");
            Path pluginClasses = root.resolve("plugin-classes");
            Path hostApi = source(hostSrc, "demo/api/Greeting.java",
                    "package demo.api; public interface Greeting { String message(); }");
            Path hostLib = source(hostSrc, "demo/lib/Message.java",
                    "package demo.lib; public class Message { "
                    + "public static String value() { return \"host-library\"; } }");
            Path pluginApi = source(pluginSrc, "demo/api/Greeting.java",
                    "package demo.api; public interface Greeting { String message(); }");
            Path pluginLib = source(pluginSrc, "demo/lib/Message.java",
                    "package demo.lib; public class Message { "
                    + "public static String value() { return \"plugin-library\"; } }");
            Path pluginImpl = source(pluginSrc, "demo/plugin/Hello.java",
                    "package demo.plugin; public class Hello "
                    + "implements demo.api.Greeting { "
                    + "public String message() { return demo.lib.Message.value(); } }");

            compile(compiler, hostClasses, hostApi, hostLib);
            compile(compiler, pluginClasses, pluginApi, pluginLib, pluginImpl);

            try (URLClassLoader host = new URLClassLoader(
                        new URL[]{hostClasses.toUri().toURL()},
                        ClassLoader.getPlatformClassLoader());
                 PluginLoader parentFirst =
                        new PluginLoader(pluginClasses, host, false, true);
                 PluginLoader pluginFirst =
                        new PluginLoader(pluginClasses, host, true, true);
                 PluginLoader noException =
                        new PluginLoader(pluginClasses, host, true, false)) {

                Class<?> sharedApi = host.loadClass("demo.api.Greeting");
                Object first = instance(parentFirst);
                Object second = instance(pluginFirst);
                Object broken = instance(noException);

                System.out.println("parent-first: " + message(first));
                System.out.println("plugin-first: " + message(second));
                System.out.println("shared API: " + sharedApi.isInstance(second));
                System.out.println("no API exception: " + sharedApi.isInstance(broken));
            }
        } finally {
            deleteTree(root);
        }
    }
}
```

Compile and run on **JDK 17 or newer** (requires `javac` and `java` on the machine):

```bash
javac --release 17 DelegationPolicyDemo.java
java DelegationPolicyDemo
```

Exact output (verified by actual compilation and execution):

```text
parent-first: host-library
plugin-first: plugin-library
shared API: true
no API exception: false
```

Line-by-line explanation:

1. `parent-first`: the host already has `demo.lib.Message`, so the plugin's loader receives the class defined by the host; `Hello` prints the result from the host library.
2. `plugin-first`: the plugin's loader looks up `demo.lib.Message` in the plugin's bytecode repository first; hence the plugin copy is used.
3. `shared API: true`: even though `Hello` and the private library can be loaded from the plugin, `demo.api.Greeting` is delegated to the host, so the host recognizes the instance as an implementation of **the host's own type**.
4. `no API exception: false`: the plugin has a copy of `demo.api.Greeting` and the loader loads that copy first; when the host checks `isInstance` against the host's interface, it fails. An equivalent cast would throw `ClassCastException`.

The example **intentionally** places the same API into both class sets to illustrate the bug; production systems should remove the duplicate API copy from the plugin runtime if the host supplies the API. In the demo, the `demo.api.*` exception is a simple parent-first policy, **not a strict parent-only mode** if the host lacks the API: `super.loadClass` can still fall back to the plugin's class. For a mandatory shared API, a real system must verify the API exists on the host and reject improper fallbacks.

Also note that this demo uses the classpath and `URLClassLoader` to focus on **class lookup order**; it does not simulate full JPMS module management, artifact signing, sandboxing, or production hot-reload. `JavaCompiler` compiles temporary sources at runtime purely to generate two class sets with identical names but differing contents; in real deployments, the class sets are usually already built into separate JARs.

## 7. Do Not Confuse Class Loading with Resource Lookup

`ClassLoader.loadClass(...)` and `getResource(...)` / `getResources(...)` are **two separate groups of behaviors**. Switching to plugin-first in `loadClass` does not automatically cause:

- `getResource("config.yml")` to pick the plugin's copy first.
- `getResources("META-INF/services/...")` to return the exact descriptors needed from host and plugin.
- `ServiceLoader` to discover the right providers across every class loader or module layer.
- A framework using the **thread context class loader (TCCL)** to automatically switch to the plugin loader.

By default, `URLClassLoader` follows inherited resource lookup behavior; if the architecture wants plugin resources to override the host, you must design a **separate resource lookup policy**, controlling both single and multiple results as well as ordering/duplicates.

In particular, many plugins use `META-INF/services`. Careless "plugin-first resources" that skip parent provider lists or naively merge duplicates can prevent plugins from being discovered, cause provider API identity errors, or trigger `ServiceConfigurationError` at initialization. Do not apply a blanket resource-override policy to every path; plugin-private configuration files and service declarations may need two different rules.

### 7.1. ServiceLoader and Shared SPI

When the host loads providers:

```java
ServiceLoader<MySpi> providers =
        ServiceLoader.load(MySpi.class, pluginLoader);
```

This is an **integration snippet**, where `MySpi` is a host-defined type and `pluginLoader` is the loader managing the plugin artifact. `ServiceLoader` requires providers to genuinely match `MySpi`. If plugin-first defines a duplicate copy of `MySpi`, the provider may not be assignable and discovery/instantiation can fail with `ServiceConfigurationError`.

Choosing the loader explicitly avoids finding a provider using one loader while the SPI was loaded with another. With the `ServiceLoader.load(MySpi.class)` overload, Java uses the current **thread context class loader**; hence changing TCCL can affect the discovery path, even though `MySpi.class` itself belongs to the host.

### 7.2. TCCL Must Be Restored

Some frameworks/JDK APIs look up classes or resources via `Thread.currentThread().getContextClassLoader()`, rather than going directly through the loader that created the plugin object. If you must temporarily set the TCCL to call a plugin, restore it in `finally`:

```java
Thread thread = Thread.currentThread();
ClassLoader original = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    // Invoke code/plugin framework requiring TCCL here.
    invokePlugin();
} finally {
    thread.setContextClassLoader(original);
}
```

This is an **integration snippet**, requiring `pluginLoader` and `invokePlugin()` supplied by the application. Do not leave the plugin's TCCL on a thread pool after returning from a request: doing so can cause other tasks to see the wrong plugin dependencies, leak the class loader, and block unloading. Propagate/restore context intentionally in asynchronous tasks according to the contract; setting TCCL on one thread does not automatically change other execution threads.

## 8. Common Errors from Wrong Ordering or Exceptions

| Symptom | Possible cause | Investigation and fix |
| --- | --- | --- |
| Plugin calls a new method and hits `NoSuchMethodError` | Parent-first picked up the host's old library copy by mistake | Check defining loader and version; allow plugin-first for private dependencies |
| `ClassCastException` despite identical class names | Host and plugin both defined the same API/SPI | Share the API in the parent and enforce mandatory delegation; check `getClassLoader()` |
| `ServiceConfigurationError` when discovering providers | Provider may implement its own SPI copy; metadata/resources may be wrong | Check service class identity, loader, descriptor, and root cause |
| `NoClassDefFoundError` at runtime | Missing transitive dependency or earlier initialization failure | Inspect cause chain, dependency closure, and actual layer/classpath |
| `LinkageError`, `loader constraint violation` | Classes participating in a runtime signature lack compatible identities | Check delegation of all types crossing the boundary |
| Plugin loads, yet callbacks fail to register | Host registry expects host-defined interfaces/classes | Both SPI and event/annotation contracts must use shared classes |
| Plugin library accidentally replaces shared framework classes | Plugin-first scope is too broad | Restrict private namespaces and shared exceptions |
| Plugin cannot find resources/providers | Overrode only `loadClass`, while resource lookup/TCCL differs | Inspect `getResources`, `ServiceLoader`, and TCCL |
| Old plugin fails to unload | Static caches, threads, listeners, or TCCL retain references | Unregister, close loader, terminate tasks, and clear caches per ownership |

**Do not fix `NoSuchMethodError` by switching everything to plugin-first**. If the method belongs to a DTO or SPI crossing the boundary, creating a separate copy can turn the error into `ClassCastException` or `LinkageError`. Determine precisely which libraries are allowed to be private and which must be shared.

When diagnosing, print the loaders of both the host interface and the implementation class:

```java
System.out.println(MySpi.class.getClassLoader());
System.out.println(instance.getClass().getClassLoader());
System.out.println(MySpi.class.isInstance(instance));
```

This is also an **integration snippet**. `instance` may belong to the plugin loader while still implementing an API defined by the parent; what matters is that classes/interfaces in the inheritance chain and method signatures have consistent identities.

## 9. Operations, Versioning, and Isolation Limits

### 9.1. Versioning and Dependency Rules

- **Host API/SPI:** publish compatible versions and check them when accepting a plugin. Parent-first only unifies types; it does not prove ABI/behavior compatibility.
- **Private dependencies:** package with the plugin and allow plugin-first in the chosen namespace; avoid letting private classes appear directly in public SPI methods.
- **Shared dependencies:** the host decides the version; plugins declare the version range they support and are tested against the exact version the host provides.
- **Two different plugins:** use separate loaders when two parallel private versions are needed; avoid shared static singletons unless intentionally shared.
- **Shading/relocation:** can reduce package-name collisions for private dependencies, but resources such as `META-INF/services`, reflection strings, and serialization metadata must be updated if build tools do not handle them automatically. Shading does not replace a shared SPI policy.

A duplicate API packaged inside a plugin should be caught by build/deploy checks, rather than relying solely on parent-first "shadowing" the extra copy.

### 9.2. JPMS and Module Layers

In Java 9+, you can use `ModuleLayer` to deploy dedicated modules for plugins; services can be declared via `provides ... with ...` and `uses` instead of `META-INF/services`. Class visibility is then also governed by module resolution, readability, `exports`, and `opens`. You cannot fix a `module does not read` or reflective access error merely by flipping parent-first/child-first order.

A layer can be associated with one or multiple class loaders depending on the definition strategy; **class loader isolation** and **module encapsulation** are related but distinct mechanisms. Choose `ServiceLoader.load(layer, service)` or another overload according to the deployment model and re-verify service identity as well.

### 9.3. Dependency Isolation Is Not a Security Sandbox

A dedicated ClassLoader primarily supports namespaces, lifecycle, and dependency management. It **does not by itself prevent** plugins from reading files, opening network connections, using reflection, or calling public host APIs. The Java Security Manager has been removed from recommended protection models, and plugin-first cannot be viewed as a sandbox mechanism for untrusted code. If strong trust boundaries are required, consider separate processes, OS permissions, IPC, container environments, or appropriate isolation controls.

### 9.4. Lifecycle and Unloading

A class already defined by the JVM via a specific loader cannot "switch owners" when policies change. To load a new version of a plugin, you typically create a new loader/module layer, register the new provider, cancel the old plugin's listeners/tasks/timers/threads, and ensure no strong references remain to old classes/instances/loaders. Closing `URLClassLoader` releases resources it manages, yet **does not guarantee immediate unloading of all classes** if other references remain.

## 10. Pre-Release Plugin Testing Checklist

1. **Parent-first baseline:** when host and plugin both contain a dependency, confirm the actual version and defining loader are the host's copy.
2. **Plugin-first private dependencies:** with two different versions, confirm the plugin uses its own copy and the host still uses the host copy.
3. **API/SPI always shared:** even if a plugin JAR accidentally contains a copy, `HostSpi.class.isInstance(provider)` must be true; in production, remove the duplicate copy from the artifact.
4. **Mandatory shared API in parent:** test a host missing the API and confirm it is rejected rather than silently falling back to the plugin's copy.
5. **Cross-boundary types:** test shared DTOs, callbacks, exceptions, enums, and annotations—not just the main interface.
6. **Missing dependencies or linkage errors:** do not catch and arbitrarily fall back; preserve the root cause and identify the artifact/class loader.
7. **Resources and ServiceLoader:** test single resources, multiple resources, service descriptors, TCCL, and `ServiceConfigurationError` in a realistic deployment environment.
8. **Multiple concurrent plugins:** same-named libraries at different versions do not conflict across loaders.
9. **JPMS if applicable:** test `uses`, `provides`, layers, `exports`, and `opens`.
10. **Reload/unload:** ensure no threads, TCCL, registries, or host static caches continue referencing the old plugin.

**Design principle:** use parent-first for classes needing a **shared Java identity**, plugin-first for code and dependencies **genuinely privately owned by the plugin**, and declare delegation exceptions tightly enough that the host's API/SPI cannot be shadowed. The rest of the system—resource lookup, `ServiceLoader`, TCCL, version policies, and lifecycle—must be designed to align with that decision rather than assuming every kind of lookup follows the same rule.