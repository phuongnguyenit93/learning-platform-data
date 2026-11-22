# Choosing ClassLoaders for Shared APIs and Private Dependencies in Java Plugin Architecture

A plugin system aims to achieve two seemingly conflicting goals: **the host and plugins must understand the same communication contract**, yet **each plugin may need its own implementation libraries, even at different versions from the host or other plugins**. If you put all classes on a single application classpath, version conflicts can occur. If you create a child-first loader for everything, the host and plugins may no longer share the same runtime interface to communicate.

The common architectural solution is to divide **ownership by class category**:

- **Shared API** — SPI interfaces, DTOs, exceptions, callbacks, and true contracts across the host/plugin boundary: defined by the **shared parent loader**; plugins delegate when API classes are needed.
- **Plugin implementation** — business execution classes used only by the plugin: defined by the **dedicated plugin loader**.
- **Private dependencies** — libraries owned by a plugin whose versions need to be isolated: typically defined by the **plugin loader** with a selective lookup policy; avoid accidentally using a same-named version from the parent.
- **JDK/platform classes** — continue delegating via the appropriate mechanism without "reloading" `java.*` manually.

**Key principle:** *Share the contract; isolate implementation details.* Choosing the right loader must be based on **class identity**, **binary contracts**, **the actual loaded version**, **resource visibility**, **plugin lifecycle**, and **interoperability needs**, rather than just the loader tree diagram.

## 1. Why Does a Plugin Architecture Need Multiple Loaders?

In Java, the runtime identity of a class/interface is the **pair (binary name, defining class loader)**:

~~~text
Runtime type = (binary name, defining loader)

(api.Greeting, AppLoader)        -> shared interface
(api.Greeting, PluginLoaderA)    -> DIFFERENT interface if child defines it itself
(plugin.impl.Greeter, LoaderA)   -> implementation A
(plugin.impl.Greeter, LoaderB)   -> different implementation B
~~~

Two byte-for-byte identical `api/Greeting.class` files defined by two different defining loaders are still **two distinct runtime types**. This directly affects `instanceof`, casts, method signatures, reflection, and the ability to pass objects between the host and plugins.

### Recommended Diagram

~~~text
                   Bootstrap / Platform
                           |
                   Application loader
                  /        |          \
       api.Greeting  api.PluginContext  shared DTO
                           |
                  +--------+--------+
                  |                 |
            Plugin loader A   Plugin loader B
                  |                 |
       plugin.impl.Greeter   plugin.impl.Greeter
       deps.private.Json v1 deps.private.Json v2
       resources A          resources B
                  |                 |
                  +--------+--------+
                           |
                 host communicates via
                  the same api.Greeting
~~~

Here, two plugins can each define an implementation class with the **same binary name**, as long as the host does not try to treat them as a single runtime implementation type. Both objects can be cast to the **same `api.Greeting` interface** defined by the parent.

### Defining Loader Differs from Initiating Loader

~~~java
Class<?> apiType = pluginLoader.loadClass("api.Greeting");
ClassLoader defining = apiType.getClassLoader();
~~~

This is an illustrative snippet using an existing `pluginLoader` variable. If the plugin loader delegates to the parent, `defining` is the **parent**, not `pluginLoader`. The loader that receives the `loadClass` call is not necessarily the loader that defines the class.

When debugging, ask:

~~~java
System.out.println(apiType == api.Greeting.class);
System.out.println(apiType.getClassLoader()
        == api.Greeting.class.getClassLoader());
~~~

Both values are `true` in a properly configured shared API setup. However, checking `getName()` alone is **not sufficient**, because two `Class<?>` objects from different loaders can still have the same name.

## 2. Classifying Classes Before Choosing Parent or Child

| Class group | Examples | Where it should typically be defined | Reason |
|---|---|---|---|
| Cross-boundary API interfaces | `api.Greeting`, `spi.PaymentProvider` | Shared parent | Preserves a single runtime type for casting and invocation |
| Shared DTOs, callbacks, exceptions | `api.Request`, `api.PluginException` | Shared parent | Cross-boundary method signatures require the same identity |
| Java/platform | `java.lang.String`, `java.sql.*` | Appropriate bootstrap/platform/parent | Avoids redefining Java platform types |
| Plugin implementation | `plugin.impl.Greeter` | Plugin loader | Separates lifecycle and versions |
| Private implementation dependency | `deps.format.Formatter` | Plugin loader if a separate version is needed | Prevents the host version from shadowing the plugin version |
| Shared dependency used in the API | `api.json.JsonNode` if the type appears in a public method | Parent or unified contract | Avoids two incompatible versions in signatures |
| Shared logging/service facades | Logging/metrics API or SPI | Usually parent | Prevents API splitting and establishes a clear policy for adapters |
| Private resources | `plugin/config.txt`, templates | Plugin's own source, intentional lookup | Prevents configuration from being shadowed by parent resources |

**Do not decide solely based on JAR names.** A library may consist of a genuinely shared API part and a private implementation part. If classes in a package require package-private access to one another, consider keeping them in the **same defining loader**, because the JVM identifies a runtime package by **package name + defining loader**.

### Questions to Ask Before "Putting a Dependency in the Child"

1. Does any type from that library appear in a public method or field of the SPI?
2. Does the host cast, use reflection on, deserialize, or invoke callbacks with objects from that library?
3. Does it rely on `ServiceLoader`, `Class.forName`, or the thread context class loader?
4. Does it use native libraries, static singletons, global registries, thread pools, or a log manager?
5. Do two versions coexist, and are both genuinely needed?
6. Does the library use package-private/nestmate access between classes that you plan to split across loaders?
7. If the plugin is redeployed, what references could keep the old loader alive?
8. Is there a JPMS module system or a custom framework launcher involved?

If a type must cross the boundary, you usually have to place that type into a **shared contract** or replace it with a neutral format (such as a message/schema) rather than letting each side define its own copy.

## 3. Parent-First: Safe Default for Shared APIs, but Can Pick the Wrong Dependency

By default, `ClassLoader.loadClass(String, boolean)` performs:

~~~text
Child.loadClass(name)
  -> findLoadedClass(name)
  -> parent.loadClass(name)  [if parent finds it, use parent's class]
  -> child.findClass(name)   [if parent does not find it]
  -> resolve if requested
~~~

Advantages of **parent-first**:

- Keeps the host and plugins sharing the same APIs, DTOs, and classes on the parent.
- Avoids accidentally redefining `java.*` and shared APIs in every child.
- Matches the default behavior of `URLClassLoader` naturally.
- Reduces duplicate class metadata and simplifies many dependency paths.

However, there is a risk:

~~~text
Host classpath:
  deps.format.Formatter v1
Plugin JAR:
  deps.format.Formatter v2
PluginLoader: parent-first
~~~

If the parent sees `deps.format.Formatter` v1, the plugin loader returns **v1** when asked to load the class with that name, even though the plugin's JAR contains **v2**.

If the plugin was compiled against a method that only exists in v2, the JVM may throw `NoSuchMethodError` or another linkage error at runtime. "Finding a class" does not prove **binary compatibility**. Therefore, parent-first is a good choice for **shared APIs**, but not automatically right for every **private dependency**.

## 4. Selective Child-First: Apply Only to Implementations/Private Dependencies

When a plugin needs its own version of a library with the same binary name, we can change the class lookup policy **for a limited set of namespaces**:

~~~text
Class name                     Policy
------------------------------------------------
java.*                         default / delegation
api.*                          parent-first
shared.contract.*              parent-first
plugin.impl.*                  child-first (if needed)
deps.format.*                  child-first
all remaining names            parent-first
~~~

The implementation should **not** simply be "child-first for everything":

- If `api.Greeting` is inside the plugin JAR and the child defines it on its own, the host cannot cast the provider to the host's `api.Greeting`.
- If the plugin uses framework APIs that must be shared, loading a separate copy can break method signatures, service registries, or reflection.
- The JVM enforces restrictions on the `java.*` package; a custom loader is not allowed to define core Java classes itself.
- A private library might call a host interface; in that case, the API portion of the library must be shared across the proper boundary.

**The goal is not "as much child-first as possible," but "child-first strictly where a different version is needed."**

### Avoid Splitting Package-Private Dependent Classes

Suppose two classes `p.Accessor` and `p.Secret` access package-private members. If they are defined by two different loaders even though the source declares the same `package p;`, they belong to **two different runtime packages**. A bytecode call between them can throw `IllegalAccessError`.

Therefore, the namespace policy should be designed around **coherent package clusters or library groups**, not individual classes split arbitrarily across loaders.

## 5. Complete Java 17+ Example: Parent-First Uses v1, Private Dependency Uses v2

The following experiment demonstrates:

- The host has `api.Greeting` and `deps.format.Formatter` version **v1** on the application classpath.
- The plugin contains `plugin.impl.PluginGreeting` and a copy of `deps.format.Formatter` version **v2** in its own JAR.
- The default **parent-first** loader causes the plugin to run with the **host-v1** dependency.
- A **child-first loader only for `deps.format.*`** allows the plugin to use **plugin-v2**.
- Both providers **cast successfully to a single `api.Greeting`** because the shared API is defined by the parent.
- Two separate plugin loaders produce two distinct runtime implementation and dependency classes.
- Resources with the same name may still be retrieved from the parent because resource lookup is independent of class loading policy.

No Maven, Gradle, or external libraries are used. The code compiles and runs on **JDK 17+**.

### 5.1. Project Structure

~~~text
project/
  src/
    api/api/Greeting.java
    v1/deps/format/Formatter.java
    v2/deps/format/Formatter.java
    plugin/plugin/impl/PluginGreeting.java
    host/LoaderBoundaryDemo.java
  out/
    api/
    lib-v1/
    lib-v2/
    plugin/
    host/
  dist/
    private-plugin.jar
~~~

The `out` and `dist` directories are created during the build step.

### 5.2. Shared API: `src/api/api/Greeting.java`

~~~java
package api;

public interface Greeting {
    String message();
}
~~~

This is the contract the host knows at compile time. **Do not copy `api/Greeting.class` into the private plugin JAR.** The plugin compiles against the API in `out/api`, while at runtime the plugin loader delegates lookups for `api.Greeting` to the parent.

### 5.3. Host Version of Formatter: `src/v1/deps/format/Formatter.java`

~~~java
package deps.format;

public final class Formatter {
    private Formatter() {
    }

    public static String identity() {
        return "host-v1";
    }
}
~~~

### 5.4. Plugin-Private Version of Formatter: `src/v2/deps/format/Formatter.java`

~~~java
package deps.format;

public final class Formatter {
    private Formatter() {
    }

    public static String identity() {
        return "plugin-v2";
    }
}
~~~

The two sources share the same binary name `deps.format.Formatter` but return different results. This is a minimal example of a **version conflict**, not a recommendation to place two libraries with the same name on a single classpath.

### 5.5. Implementation: `src/plugin/plugin/impl/PluginGreeting.java`

~~~java
package plugin.impl;

import api.Greeting;
import deps.format.Formatter;

public final class PluginGreeting implements Greeting {
    public PluginGreeting() {
    }

    @Override
    public String message() {
        return Formatter.identity();
    }
}
~~~

This file will be compiled against Formatter **v2**, yet when run with parent-first it can still receive Formatter **v1**. In this example both versions share the same method signature, so it runs and produces two different outputs. If real-world versions do not preserve binary compatibility, you may encounter linkage errors rather than merely different outputs.

### 5.6. Host and Custom Loader: `src/host/LoaderBoundaryDemo.java`

~~~java
import api.Greeting;
import deps.format.Formatter;

import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

public final class LoaderBoundaryDemo {

    static final class PolicyLoader extends URLClassLoader {
        private final boolean isolatePrivateDeps;

        PolicyLoader(String name, URL[] sources, ClassLoader parent,
                     boolean isolatePrivateDeps) {
            super(name, sources, parent);
            this.isolatePrivateDeps = isolatePrivateDeps;
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {

            // Shared API, Java classes, and all other namespaces:
            // use default parent-first delegation.
            if (!isolatePrivateDeps || !name.startsWith("deps.format.")) {
                return super.loadClass(name, resolve);
            }

            // Only the private dependency namespace uses child-first.
            synchronized (getClassLoadingLock(name)) {
                Class<?> found = findLoadedClass(name);

                if (found == null) {
                    try {
                        found = findClass(name);
                    } catch (ClassNotFoundException absentInPlugin) {
                        found = super.loadClass(name, false);
                    }
                }

                if (resolve) {
                    resolveClass(found);
                }
                return found;
            }
        }
    }

    private static Greeting instantiate(PolicyLoader loader)
            throws Exception {
        Class<?> type = loader.loadClass(
                "plugin.impl.PluginGreeting");

        return (Greeting) type.getConstructor().newInstance();
    }

    private static String text(URL url) throws Exception {
        if (url == null) {
            return "missing";
        }
        try (InputStream in = url.openStream()) {
            return new String(in.readAllBytes(),
                    StandardCharsets.UTF_8).strip();
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: LoaderBoundaryDemo <plugin-jar>");
        }

        URL jar = Path.of(args[0]).toAbsolutePath()
                .toUri().toURL();
        URL[] sources = {jar};
        ClassLoader parent =
                LoaderBoundaryDemo.class.getClassLoader();

        try (PolicyLoader parentFirst =
                    new PolicyLoader("parent-first", sources,
                            parent, false);
             PolicyLoader privateFirst =
                    new PolicyLoader("private-first", sources,
                            parent, true);
             PolicyLoader otherPrivate =
                    new PolicyLoader("private-2", sources,
                            parent, true)) {

            Greeting normal = instantiate(parentFirst);
            Greeting isolated = instantiate(privateFirst);

            Class<?> apiFromPlugin = privateFirst.loadClass(
                    "api.Greeting");
            Class<?> ownLib = privateFirst.loadClass(
                    "deps.format.Formatter");
            Class<?> parentLib = parentFirst.loadClass(
                    "deps.format.Formatter");

            System.out.println("host library: "
                    + Formatter.identity());
            System.out.println("parent-first plugin: "
                    + normal.message());
            System.out.println("private-first plugin: "
                    + isolated.message());

            System.out.println("same shared API: "
                    + (apiFromPlugin == Greeting.class));
            System.out.println("plugin cast works: "
                    + (isolated instanceof Greeting));
            System.out.println("parent-first library from parent: "
                    + (parentLib.getClassLoader() == parent));
            System.out.println("private library from child: "
                    + (ownLib.getClassLoader() == privateFirst));

            Class<?> otherLib = otherPrivate.loadClass(
                    "deps.format.Formatter");
            System.out.println("private library types equal: "
                    + (ownLib == otherLib));

            Class<?> otherImplementation = otherPrivate.loadClass(
                    "plugin.impl.PluginGreeting");
            System.out.println("implementation types equal: "
                    + (isolated.getClass() == otherImplementation));

            String resourceName = "plugin/config.txt";
            System.out.println("resource via loader: "
                    + text(privateFirst.getResource(resourceName)));
            System.out.println("resource from child URL: "
                    + text(privateFirst.findResource(resourceName)));
        }
    }
}
~~~

**Technical explanation:**

1. `PolicyLoader` extends `URLClassLoader`. This loader holds the URL list containing the plugin JAR, and its parent is the application loader.
2. By default, all class names still follow `super.loadClass`. Only classes starting with `deps.format.` prioritize the child's `findClass`.
3. Inside the child-first branch, `getClassLoadingLock(name)` together with `findLoadedClass(name)` prevent redefining the same class name within a single loader. `resolveClass` handles resolution when `resolve=true`.
4. `api.Greeting` does not fall under the child-first branch, so it is defined and shared by the parent. Two plugin objects from different implementation loaders remain compatible with the shared API.
5. `plugin.impl.PluginGreeting` is not on the host's application classpath; both the parent-first and private-first loaders define their own copy of the plugin class.
6. `deps.format.Formatter` exists in both the host and the plugin. The default loader returns the parent's class; the private-first loader defines the class from the plugin JAR.
7. By default, `getResource` continues to use ClassLoader resource delegation. **Changing `loadClass` does not automatically change `getResource`**.
8. `findResource` only searches the URLs belonging to the URLClassLoader itself; it is used here to illustrate where the resource resides, not as a recommendation to access resources through every loader's protected API.

### 5.7. Compilation and Packaging Commands

The following commands use **Bash/Linux/macOS**, run from the `project` directory:

~~~bash
mkdir -p out/api out/lib-v1 out/lib-v2 out/plugin out/host dist
mkdir -p out/lib-v1/plugin out/plugin/plugin

javac -d out/api src/api/api/Greeting.java
javac -d out/lib-v1 src/v1/deps/format/Formatter.java
javac -d out/lib-v2 src/v2/deps/format/Formatter.java

javac -cp "out/api:out/lib-v2" -d out/plugin \
    src/plugin/plugin/impl/PluginGreeting.java

javac -cp "out/api:out/lib-v1" -d out/host \
    src/host/LoaderBoundaryDemo.java

printf 'host-resource\n' > out/lib-v1/plugin/config.txt
printf 'plugin-resource\n' > out/plugin/plugin/config.txt

jar --create --file dist/private-plugin.jar \
    -C out/plugin . -C out/lib-v2 .

java -cp "out/api:out/host:out/lib-v1" \
    LoaderBoundaryDemo dist/private-plugin.jar
~~~

Notes:

- `out/api` is the **shared API**, present on the host classpath.
- `out/lib-v1` is a host dependency, so the application loader sees Formatter v1 and the host's `plugin/config.txt` resource.
- `out/lib-v2` is the plugin's private dependency, used only when compiling the plugin and packaging `private-plugin.jar`; do **not** put it on the application classpath of the run command.
- `out/plugin` is also **not** on the application classpath. The plugin implementation comes exclusively from the URLClassLoader.
- The private JAR contains the implementation class, the v2 library, and the plugin resource, but **does not contain `api/Greeting.class`**.
- `javac -cp ...` is the **compile-time classpath**. It does not determine the runtime policy of the custom loader.

After building, the key entries inside `dist/private-plugin.jar` are:

~~~text
plugin/impl/PluginGreeting.class
deps/format/Formatter.class
plugin/config.txt
~~~

You can verify this with:

~~~bash
jar --list --file dist/private-plugin.jar
~~~

If `api/Greeting.class` appears in the plugin JAR due to a packaging mistake, even though parent-first usually still prioritizes the parent's version, **duplicate API bytecode** is a sign that the packaging should be fixed so another policy cannot inadvertently redefine the shared API.

### 5.8. Stdout and Explanation

**Expected stdout on Java 17+ when the files match the above:**

~~~text
host library: host-v1
parent-first plugin: host-v1
private-first plugin: plugin-v2
same shared API: true
plugin cast works: true
parent-first library from parent: true
private library from child: true
private library types equal: false
implementation types equal: false
resource via loader: host-resource
resource from child URL: plugin-resource
~~~

Interpreting by group:

- `host library: host-v1`: the app loader loads `deps.format.Formatter` from the host's v1 output.
- `parent-first plugin: host-v1`: the plugin class is defined by its own loader, but the `Formatter` reference is returned as v1 by the parent.
- `private-first plugin: plugin-v2`: the child-first branch for `deps.format.*` forces the private dependency to come from the plugin JAR.
- `same shared API: true`: the plugin loader also sees the exact same `api.Greeting.class` used by the host.
- `plugin cast works: true`: the plugin object is instantiated from its own class yet implements the shared API defined by the parent, so the host cast succeeds.
- `parent-first library from parent: true` and `private library from child: true` demonstrate that you should not rely on the class name to guess the defining loader.
- `private library types equal: false`: two separate child loaders define two distinct runtime `deps.format.Formatter` types even when reading from the same plugin JAR.
- `implementation types equal: false`: implementation classes from two plugin loaders also have different identities.
- `resource via loader: host-resource`: `ClassLoader.getResource` queries the parent first by default, and the host already has a resource with the same name.
- `resource from child URL: plugin-resource`: `URLClassLoader.findResource` looks up resources only in the child's URL sources.

**A very important point:** a selective child-first class policy **does not automatically make the resource policy child-first**. If the plugin inadvertently calls `getResource("plugin/config.txt")` and the parent has a duplicate, the host's configuration can shadow the plugin's configuration even though the `Formatter` class has been isolated to v2.

### 5.9. Windows PowerShell

On Windows, replace directory and file creation with `New-Item` and `Set-Content`; the `javac`, `jar`, and `java` commands work similarly. The `-cp` separator is **`;`**, for example:

~~~powershell
java -cp "out/api;out/host;out/lib-v1" LoaderBoundaryDemo dist/private-plugin.jar
~~~

If using PowerShell to create resources, save them in UTF-8 with exact contents and no unwanted characters; in the example, `String.strip()` strips newline characters from the resource when printing.

## 6. Binary Contracts and Dependency Leaks Across the Public API

Choosing a loader for a dependency is not just about deciding where to store the JAR. Consider this interface:

~~~java
package api;

public interface ReportPlugin {
    deps.format.Document create();
}
~~~

This is an **illustrative snippet**; the `deps.format.Document` type must actually be loadable from the corresponding API or module.

Here, `deps.format.Document` appears in a **public method signature**. If each plugin defines its own `Document` type, the host receives runtime types with different identities and may fail to invoke, cast, or link the contract properly.

**A better design approach:**

~~~java
package api;

public interface ReportPlugin {
    api.DocumentDto create();
}
~~~

In this model, `api.DocumentDto` is defined by the shared loader. The plugin can convert from its private `deps.format.Document` object to the shared DTO before returning it.

When a plugin needs to use a dependency type as part of a public contract, **that dependency is no longer truly private**. You need one of the following approaches:

1. Promote the dependency API type to a **shared dependency** defined by the parent, standardizing on a single version/ABI.
2. Create an **anti-corruption layer/adapter** that converts data from the private type into a DTO belonging to the shared API.
3. Use data exchange formats independent of class identity (schemas/messages, JSON, or protobuf as appropriate) if you need a flexible or out-of-process boundary.
4. Version the contract explicitly when introducing incompatible changes.

You should not place both v1 and v2 of a dependency on the parent and hope the JVM picks the right one based on the caller. For a single binary name and a single defining loader, the JVM cannot simultaneously define two versions with the same name in that same loader.

## 7. Shading, Relocation, and Cases Where a Custom Loader Is Unnecessary

Not every version conflict forces you to write a child-first `ClassLoader`. One option is **shading/relocation**, where a build tool rewrites the binary package name of a private dependency, for example:

~~~text
deps.format.Formatter
        |
        v
pluginA.shadow.deps.format.Formatter
~~~

When the binary class name is genuinely renamed and the corresponding bytecode and resource metadata are updated, parent-first can work without colliding with the old class name. However, relocation requires checking:

- Reflection using class names as Strings.
- `META-INF/services` descriptors and provider names.
- Resources referenced by package paths.
- Serialization metadata or hardcoded names.
- Native libraries, JNI, service registries, or configuration resources the library depends on.
- Licensing/packaging and integration with frameworks that rely on specific package names.

**Relocation is not just renaming a JAR file.** If a library relies heavily on reflection or service metadata, relocation can introduce other failures. Weigh the simplicity of the runtime loader against build and compatibility costs when multi-version support is genuinely needed.

## 8. ServiceLoader, SPI, and TCCL at the Plugin Boundary

`ServiceLoader` consumes a **shared service type** from the parent and providers from the plugin loader. For classpath SPI, the plugin needs `META-INF/services/api.PluginService` containing the exact binary provider name; the host should use the explicit overload `ServiceLoader.load(api.PluginService.class, pluginLoader)` when the owning plugin is known. The single-argument overload uses the thread's TCCL, so a framework running on a different worker thread may fail to find the plugin's provider. If you must change the TCCL, save the worker's own context and restore it in a `finally` block. JPMS named modules use `uses`/`provides` and can call `ServiceLoader.load(layer, Service.class)`; do not conflate that mechanism with classpath URL loaders.

## 9. Resource Policy Does Not Automatically Follow Class Policy

Resource lookup and class lookup are two separate paths:

| API | Typical Lookup Behavior |
|---|---|
| `loader.loadClass("deps.format.Formatter")` | Follows the loader's override policy; can be child-first |
| `loader.getResource("plugin/config.txt")` | Parent-first by default |
| `loader.getResources("plugin/config.txt")` | Can return multiple URLs from both parent and child |
| `URLClassLoader.findResource("plugin/config.txt")` | Searches only the loader's own URL sources |
| `SomeClass.class.getResource("config.txt")` | Name relative to the class's package |
| `Class.getResource("/plugin/config.txt")` | Absolute name from the root, yet still subject to the relevant module/loader rules |

If both the parent and child contain `plugin/config.txt`, the resource from the parent may be selected even when the class logic is using the dependency from the child. Therefore:

- Place private configuration under its own namespace to avoid path collisions.
- Pass an explicit resource URL or stream if you need a guaranteed source.
- With URLClassLoader, you can use `findResource` when you specifically want to search within child URLs and the loader has not been closed.
- When overriding resource lookup, remember to keep `getResource` **and `getResources`** consistent so they do not exhibit conflicting behavior.
- For JPMS named modules, resources inside a named module's package are also governed by `opens` rules; the `Class`/`Module`/`ClassLoader` APIs have different access conditions.

**Do not use** a successful `getResource` call to conclude that a class of the same name was also defined by that same loader.

## 10. Binary Compatibility and Real-World Version Errors

There are several important scenarios:

### 10.1. Parent-First Selects an Older Version

The plugin compiles against:

~~~java
Formatter.formatAdvanced(value);
~~~

but the parent only has an older version of Formatter that lacks a method with a matching descriptor. Class loading may succeed, yet when the JVM resolves the method at execution time, `NoSuchMethodError` can occur.

**How to investigate:** inspect `Formatter.class.getClassLoader()` on the actual class, its `CodeSource` if available, the JAR name/path, and the method signatures of the version used at compile time.

### 10.2. Child-First Loads the Shared API Too

The plugin object implements an interface with the **same name** as the host's, but with a different defining loader. `ClassCastException` or `ServiceConfigurationError` can occur. Do not try to fix this with a "stronger" cast; fix **loader ownership**.

### 10.3. Package-Private Access Across Loaders

Two classes in the same source package but with different defining loaders belong to different runtime packages. The JVM can reject package-private access with `IllegalAccessError`. Do not blindly apply `--add-opens` as a workaround: module openness and runtime package identity are two distinct issues.

### 10.4. Host and Plugin Have Two Versions of the Same Native Library

Some native libraries have their own restrictions on loading native code from multiple class loaders within the same JVM. Classloader separation does not automatically create **two independent native linker/process namespaces**. If a plugin dependency relies on JNI or global native state, carefully check the library's lifecycle and support guarantees; process-level isolation may be required.

### 10.5. Duplicate Classes in the Same Plugin JAR

If a plugin JAR was improperly merged or shaded and contains multiple copies with the same binary name, entry or search order may cause an unintended class to be picked. Before changing the policy, inspect the artifact with `jar --list --file ...` as well as your dependency tree and build pipeline.

## 11. Distinguishing Version "Privacy" from Security "Privacy"

In this article, `private` only means **a dependency whose version/namespace is not shared with the host**. A ClassLoader does not create a security sandbox: a plugin in the same process can still invoke JDK APIs and affect files, networking, and memory within the process's permissions. Untrusted plugins require OS/process/container isolation and an appropriate IPC boundary.

## 12. Lifecycle: How Far Can a Plugin Be Unloaded?

Each plugin generation must keep its loader open as long as lazy loading of classes or resources is still needed. On shutdown, the host blocks new work, drains tasks, unregisters callbacks, closes resources, restores the TCCL, and finally closes the `URLClassLoader`. Class unloading depends on GC and reachability; `close()` does not force immediate class unloading. Check parent/shared libraries in particular, as static caches in them can keep plugin objects alive.

## 13. Diagnostics: Which Loader Defined Which Class?

### Using `Class.getClassLoader()`

~~~java
Class<?> type = object.getClass(); // object is non-null
ClassLoader defining = type.getClassLoader();

System.out.println("type=" + type.getName());
System.out.println("loader=" + defining);
System.out.println("module=" + type.getModule());
~~~

This is an illustrative snippet, not a complete program. For core Java classes, `getClassLoader()` may return `null` to represent the bootstrap loader.

### Using CodeSource When Available

~~~java
Class<?> type = object.getClass();
var domain = type.getProtectionDomain();
var source = domain == null ? null : domain.getCodeSource();

System.out.println(source == null
        ? "CodeSource unavailable"
        : source.getLocation());
~~~

Not every runtime class has a useful CodeSource; it may be `null`. Do not rely on a loader's string representation or `identityHashCode` as an absolute ID; they do not replace object identity `==`.

### Information Worth Logging

| Information | Why |
|---|---|
| Binary name | Identify the exact class causing the error |
| Defining loader object/type | Distinguish between parent APIs and child dependencies |
| Loader logical name/generation | Correlate with the active plugin instance |
| Parent chain | Understand delegation |
| CodeSource URL/JAR hash | Identify the actual bytecode |
| Package-based policy branch | Know whether parent-first or child-first was applied |
| Thread context loader | Investigate ServiceLoader and frameworks |
| Resource URL | Investigate config files shadowed by the parent |
| Java module/layer | Investigate JPMS readability/exports/opens |
| Full exception chain | Distinguish load/link/initialize/cast/runtime failures |

Do not log credentials or the full contents of sensitive resources solely for observability.

### JVM Tracing Command

On HotSpot/JDK 17+:

~~~bash
java -Xlog:class+load=info \
    -cp "out/api:out/host:out/lib-v1" \
    LoaderBoundaryDemo dist/private-plugin.jar
~~~

This is a diagnostic command; its output is JDK-dependent and more verbose than the demo's standard output. Do not treat the class-loading log as a guaranteed official class-loading order across all JVM implementations.

## 14. Designing Plugins by Need: Three Approaches

| Approach | When It Fits | Trade-offs |
|---|---|---|
| **Single shared loader, parent-first** | All plugins use compatible dependencies, with little need for parallel versions | Simple, but risks version conflicts between plugins |
| **One loader per plugin, selective child-first** | Each plugin needs private dependencies, while the shared API is stable | Increases loader count/metaspace usage; requires policy/resource/lifecycle management |
| **Separate processes** | Untrusted plugins or conflicting native/global state | Stronger isolation, but requires IPC/serialization/operational tooling |

**Shading/relocation** is an additional option if runtime child-first introduces too much complexity; choosing an approach should be based on the actual dependency graph, method signatures, and deployment model.

**Not every plugin needs its own loader.** If plugins are trusted and share compatible APIs and dependencies, simple parent-first may be the better option. Conversely, "one loader per plugin" is only worthwhile when the benefits of version isolation and lifecycle control outweigh the overhead.

## 15. Pre-Release Design Checklist

- [ ] Identify the set of shared API interfaces/DTOs/exceptions/callbacks.
- [ ] Shared types are defined by **a single parent loader** shared by both host and plugins.
- [ ] The plugin JAR does not accidentally bundle a copy of the shared API, or at minimum the policy ensures that API is never redefined.
- [ ] Plugin implementations are defined by the child plugin loader.
- [ ] Private dependencies are child-first only for explicitly intended namespaces.
- [ ] All classes in the same package that use package-private access are kept in the same defining loader.
- [ ] Cross-boundary method signatures do not leak private dependency types.
- [ ] Parent and plugin versions are checked for binary compatibility.
- [ ] Resource lookup is verified independently from class lookup.
- [ ] SPI/ServiceLoader, TCCL, and provider descriptors are properly configured.
- [ ] A fail-fast policy is in place if a dependency is missing or a library version is incompatible.
- [ ] A stop/drain/close/unload plan exists for each plugin generation.
- [ ] Defining loader, CodeSource, resource URL, and root errors are logged.
- [ ] There is a test with at least two plugins sharing the same binary implementation name but using different defining loaders.
- [ ] There is a test for duplicate resource names verifying that parent-first/child-first selects the expected data.
- [ ] There are tests covering missing methods, class not found, duplicate shared API, class cast, and hot reload.
- [ ] If using JPMS, module layers, readability, exports, and opens are evaluated independently.

## 16. Common Pitfalls

**"Just put every library on the parent to share it."** Incorrect if plugins require multiple incompatible versions with the same binary name.

**"Just make everything child-first for isolation."** Incorrect if it splits the shared API and prevents the host from casting the implementation.

**"The same `api/Greeting.class` file means the same interface."** No: the JVM considers the **defining loader**, not just the bytecode contents.

**"The loader whose `loadClass` was called is definitely the loader that defined the class."** No: parent delegation can return a parent type.

**"As long as the plugin interface is on the parent, all implementation libraries are isolated."** No: you must check the actual class loading policy and transitive dependencies.

**"Child-first for classes means child-first for resources."** No: resource delegation follows a separate path.

**"Calling `Thread.currentThread().setContextClassLoader` once is enough."** No: you must restore it when the request finishes, especially with thread pools.

**"`URLClassLoader.close()` replaces old bytecode with new bytecode."** No: existing class definitions are not replaced by closing; a new generation usually requires a new loader.

**"`--add-opens` automatically fixes every ClassCastException."** No: module openness does not turn two runtime types from different loaders into one type.

**"Putting a framework inside the plugin JAR guarantees it will use the provider/plugin class."** No: the framework may use TCCL, ServiceLoader, the system loader, or its own cache.

**"Shading just means renaming the JAR."** No: you must systematically relocate class and resource names.

**"A separate ClassLoader is a sandbox."** No: an independent security boundary is required if the plugin code is untrusted.

## 17. Self-Check Questions

**Question 1.** The host and plugin exchange `api.Greeting`. Which loader should define this interface?

**Answer:** A shared parent loader to which both the host and plugin delegate, so that both use the **same runtime interface**.

**Question 2.** The host has `deps.format.Formatter` v1, and the plugin wants v2. Which version will parent-first return if the parent sees v1?

**Answer:** v1. To use a separate v2, you need selective child-first for the appropriate namespace or an approach like shading/relocation.

**Question 3.** A child-first plugin loader defines `api.Greeting` itself using identical bytecode to the host's copy. Can the host cast the provider to the host's `api.Greeting`?

**Answer:** There is no guarantee; they are two different runtime interfaces and the cast can fail. A genuinely shared API must be used.

**Question 4.** Both the host and plugin have `plugin/config.txt`. Why can a loader that is child-first for `deps.format.*` still return the host's config?

**Answer:** Because `getResource` delegates to the parent first by default; overriding the class loading policy does not change resource lookup.

**Question 5.** Why should you avoid exposing a private `deps.format.Document` through a public SPI method?

**Answer:** Because the host and plugin need the same runtime type for that signature. If each plugin defines its own version, the boundary can become incompatible. Use a shared DTO/API or convert the data to a neutral format.

**Question 6.** Do two plugin loaders that each define `plugin.impl.PluginGreeting` from the same JAR produce the same runtime `Class<?>`?

**Answer:** No. Although the name and bytecode are identical, the defining loaders differ, so the class identity is different.

**Question 7.** Does `URLClassLoader.close()` immediately unload the plugin's classes?

**Answer:** No. References and lifecycle ties must be released; the JVM/GC determines when class unloading occurs.

**Question 8.** When `ServiceLoader.load(SPI.class)` fails to find a provider, what should you check?

**Answer:** The thread's TCCL, `META-INF/services` or `uses`/`provides`, loader visibility, and whether the provider implements the **exact runtime SPI type**.

## 18. Final Decision Diagram

~~~text
           Design a plugin class loader architecture
                             |
                    Cross-boundary API?
                     /            \
                   Yes             No
                    |                 |
         place API on parent    Consider simplicity:
                    |            parent-first if sufficient
        private version per plugin?
                     /          \
                    No          Yes
                     |            |
              parent-first    selective child-first
                     |        ONLY private namespaces
                     |            |
                     +------+-----+
                            |
                  Verify type identity
                  + public method signatures
                            |
                  Verify resources/SPI/TCCL
                            |
                  Verify lifecycle/generation
                            |
                 Log defining loader/CodeSource
                            |
                   Integration + redeploy tests
~~~

**Conclusion:** When choosing loaders, **place the shared API where all participants see the exact same runtime Class**, and keep **private implementations/dependencies in separate loaders only when version isolation is genuinely required**. Parent-first provides a stable default for contracts; selective child-first resolves implementation conflicts; and observing the actual defining loader and source helps prove that the policy is working as intended.

### Official References

- [Java SE 17 — ClassLoader: loadClass, getClassLoader, and delegation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 17 — URLClassLoader: findClass, getResource, findResource, close](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html)
- [JVMS 17 5.3 — Class/interface identity, defining and initiating loaders](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3)
- [Java SE 17 — ServiceLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
- [Java Language Specification 13 — Binary compatibility](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html)
