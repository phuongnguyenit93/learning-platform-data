# URLClassLoader: Choosing a Parent and Inherited Dependency Scope

When creating a `java.net.URLClassLoader` to load plugins or dynamic JARs, the two most important parameters are **the loader's own URL list** and **the parent class loader**. The URL list specifies which sources the child loader can search on its own for classes/resources; the parent specifies which classes/resources it can reach through **delegation**. With the **default parent-first** strategy, the parent also determines **which dependency version is chosen first** when a plugin JAR contains a class with the same name.

This lesson focuses on choosing the parent of `URLClassLoader` on **Java 17+**, the dependency scope visible through the parent, the host–plugin boundary, how to avoid version conflicts, and runnable hands-on exercises. “Dependency inheritance” here is **not** Java `extends`, does not automatically copy JARs from parent to child, and does not mean the child owns every class it finds.

## 1. Two Class Sources of a URLClassLoader

Commonly used constructor:

```java
URLClassLoader pluginLoader =
        new URLClassLoader(pluginUrls, parentLoader);
```

This is a **snippet**, requiring the `pluginUrls` and `parentLoader` variables to already be declared. It establishes:

1. **Child URL roots** (`pluginUrls`): URLs of class directories or JARs for the child to search when the parent cannot find a class. `URLClassLoader.findClass` uses these sources.
2. **Parent object** (`parentLoader`): a `ClassLoader` instance that `URLClassLoader` typically asks first through `ClassLoader.loadClass`.
3. **Class identity:** if the parent returns a `Class<?>`, the child uses that exact class. The child **does not define a duplicate copy** simply because the child's URLs also contain the same binary name.
4. **Lookup scope:** `pluginLoader.getURLs()` lists only the child's own URLs; it does not merge the parent's URLs or dependencies.
5. **Parent identity:** `pluginLoader.getParent()` returns the parent object, not the Java superclass of `URLClassLoader`.

This is the default class-loading model:

```text
pluginLoader.loadClass("feature.Service")
                │
                ▼
findLoadedClass(name)
     ├── already known ──► return existing Class<?>
     └── not yet
          │
          ▼
parent.loadClass(name)
     ├── found ──► return Class<?> defined by parent/ancestor
     └── not found
          │
          ▼
pluginLoader.findClass(name)
     ├── search child URLs ──► define and return Class<?>
     └── failed ──► ClassNotFoundException
```

The JVM also has its own verification, linking, initialization, and runtime module semantics; the diagram does not claim that every custom class loader is parent-first. However, this is the right mental model for a `URLClassLoader` using the standard `loadClass` implementation.

## 2. The Parent Is Not the Java Superclass

`URLClassLoader` extends the Java class `SecureClassLoader`, and then `ClassLoader`. That is the **type hierarchy**:

```text
Object
  └── ClassLoader
        └── SecureClassLoader
              └── URLClassLoader
```

However, `new URLClassLoader(urls, hostLoader)` creates a `URLClassLoader` object whose parent **points to the `hostLoader` object**. `hostLoader` may be an instance of the built-in application loader or a subclass unrelated to `URLClassLoader` in the type hierarchy.

```text
hostLoader : ClassLoader instance
          ▲
          │ pluginLoader.getParent() == hostLoader
          │
pluginLoader : URLClassLoader instance
```

Therefore:

- `pluginLoader.getClass().getSuperclass()` returns the Java superclass **`SecureClassLoader.class`**.
- `pluginLoader.getParent()` returns **the loader object selected** in the constructor.
- `pluginLoader.loadClass("api.Plugin")` returns the `Class<?>` that was found, while `returnedClass.getClassLoader()` is what helps identify the **defining loader** of the returned class.
- The parent is chosen based on the **API/dependency visibility contract**, not Java `extends`.

Especially in plugin architectures, the parent and the Java superclass solve two completely different problems: **lookup delegation** and **inheritance of implementation methods**.

## 3. Parent Options on Modern JDKs

| Parent | What the child can see via delegation | When to use |
| --- | --- | --- |
| `ClassLoader.getSystemClassLoader()` | Java platform classes along with the classes/dependencies that the **system loader actually sees** | The plugin needs the host SDK/SPI or code on the application classpath |
| `HostApi.class.getClassLoader()` | The namespace of the loader that **defines the shared API** (and whatever it sees) | The plugin must be compatible with interfaces, DTOs, and exceptions used by the host |
| `ClassLoader.getPlatformClassLoader()` | Platform classes from the JDK and ancestors | The plugin has its own dependencies and does not use the application classpath by default |
| `null` | The **bootstrap** lookup mechanism in the default `ClassLoader` | Only when you truly want the bootstrap as parent and accept a narrow scope |
| Custom shared loader | The classes/resources managed by the shared loader | Application servers, specialized plugin SDKs, multi-tier class loaders |

Points to distinguish:

- A **system parent** is convenient, but it can cause a **host** dependency to win over a **plugin** dependency of the same name.
- A **platform parent** is suitable when a plugin only needs Java platform APIs and its own JARs. However, it does not automatically know about an interface such as `com.myapp.spi.Plugin` defined by the application loader.
- A **`null` parent** does not mean the child cannot find `java.lang.String`: this class is normally defined by the bootstrap loader. However, since Java 9, **not every platform class is necessarily defined by the bootstrap loader**, so the platform parent is usually more appropriate when full platform APIs are needed.
- The **Host API loader** may differ from the system loader in a container/framework. Use `HostApi.class.getClassLoader()` as the anchor when the goal is to share the **exact same runtime interface**.

The parent is an **object reference**. When you change the parent between two URLClassLoader instances, you are not changing their Java superclass; you are changing the **lookup path** and compatibility.

## 4. Which Constructor Selects the Default Parent?

Java 17 Javadoc includes these forms:

```java
new URLClassLoader(urls);
new URLClassLoader(urls, parent);
new URLClassLoader("plugin-A", urls, parent);
```

This is illustrative syntax. Key points to remember:

- `URLClassLoader(URL[] urls)` uses the **system class loader as the parent**.
- `URLClassLoader(URL[] urls, ClassLoader parent)` uses the **exact loader object** passed in, including `null`.
- `URLClassLoader(String name, URL[] urls, ClassLoader parent)` supports naming the loader for observability/diagnostics. The name `"plugin-A"` is not a binary name, does not automatically create a separate package, and does not affect delegation order.
- Some overloads support `URLStreamHandlerFactory`. They are not needed to load classes from ordinary file/JAR URLs.
- Use `try-with-resources` when the application owns the loader and wants to close those JAR handles at the right time; `close()` does not cause already-loaded classes to unload automatically right away.

**Do not omit the parent argument out of habit** if the module's primary requirement is **dependency isolation**. The single-argument constructor already selects the system parent and can make the lookup scope broader than intended.

## 5. Hands-On A — Three Parents with the Same Empty URL Array

This example demonstrates that even when a child **has no URLs at all**, it can still see classes through its parent.

File tree:

```text
parent-scope-lab/
└── src/demo/ParentScopeDemo.java
```

Contents of `src/demo/ParentScopeDemo.java`:

```java
package demo;

import java.net.URL;
import java.net.URLClassLoader;

public final class ParentScopeDemo {
    private static void inspect(String label, URLClassLoader child)
            throws ClassNotFoundException {
        System.out.println(label + " urls=" + child.getURLs().length);
        System.out.println(label + " JDK=" +
                (child.loadClass("java.lang.String") == String.class));

        try {
            boolean visible =
                    child.loadClass("demo.ParentScopeDemo")
                            == ParentScopeDemo.class;
            System.out.println(label + " app=" + visible);
        } catch (ClassNotFoundException e) {
            System.out.println(label + " app=false");
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader app = ParentScopeDemo.class.getClassLoader();
        ClassLoader platform = ClassLoader.getPlatformClassLoader();

        try (URLClassLoader viaApp =
                    new URLClassLoader(new URL[0], app);
             URLClassLoader viaPlatform =
                    new URLClassLoader(new URL[0], platform);
             URLClassLoader viaBootstrap =
                    new URLClassLoader(new URL[0], null)) {
            inspect("app-parent", viaApp);
            inspect("platform-parent", viaPlatform);
            inspect("bootstrap-parent", viaBootstrap);
        }
    }
}
```

Compile/run from the `parent-scope-lab` directory:

```sh
javac --release 17 -d out src/demo/ParentScopeDemo.java
java -cp out demo.ParentScopeDemo
```

**Typical stdout on OpenJDK/HotSpot 17+ with `-cp out`:**

```text
app-parent urls=0
app-parent JDK=true
app-parent app=true
platform-parent urls=0
platform-parent JDK=true
platform-parent app=false
bootstrap-parent urls=0
bootstrap-parent JDK=true
bootstrap-parent app=false
```

**Reading the output:**

1. `viaApp` has as its parent the loader that loaded the demo class from `-cp out`. The child finds `demo.ParentScopeDemo` **through the parent**, even though `getURLs().length == 0`.
2. `viaPlatform` sees `java.lang.String` but cannot see the demo class managed by the application loader. The child also has no URLs of its own, so looking up the demo class fails.
3. `viaBootstrap` still sees `java.lang.String` because the bootstrap loader loads this core class. It cannot find the demo class.
4. None of the children define the demo class themselves when it is found through the parent. Checking `Class<?>.getClassLoader()` will reveal the loader that actually defined the class.

**Principle:** `getURLs()` is not an “effective dependency list”. It only describes the child's own sources.

## 6. Parent-First Can Cause an Older Host JAR to Beat a Newer Plugin Version

Suppose:

```text
Application loader:
    deps/Version.class   → returns "host"

Child URLs:
    plugin-out/extension/Feature.class
    pluginlib-out/deps/Version.class → returns "plugin"
```

If the plugin loads `extension.Feature` through the child and `Feature` calls `deps.Version.value()`, the child loader normally asks the parent first. When the parent has the `deps.Version` class, the JVM links the method reference to **the parent's version**. This does not change even when the pluginlib URL contains a class with the same name and different source.

Consequences:

- The plugin may execute **valid bytecode**, yet produce a result different from the version the plugin author expected.
- If a method/field signature changed between the host and plugin compile-time versions, the runtime may throw `NoSuchMethodError` or `NoSuchFieldError`.
- Parent-first is useful for **shared API identity**, but may be unsuitable for **plugin-private** libraries that have versions with the same name.
- You should not fix every issue with unconditional child-first delegation: if the plugin loader defines its own copy of a host interface, the host may be unable to cast the plugin instance.

## 7. Hands-On B — Same Plugin Bytes, Different Result When Only the Parent Changes

File structure:

```text
dependency-choice-lab/
└── src/
    ├── hostlib/deps/Version.java
    ├── pluginlib/deps/Version.java
    ├── plugin/extension/Feature.java
    └── host/demo/DependencyChoiceDemo.java
```

**`src/hostlib/deps/Version.java`:**

```java
package deps;

public final class Version {
    public static String value() {
        return "host";
    }
}
```

**`src/pluginlib/deps/Version.java`:**

```java
package deps;

public final class Version {
    public static String value() {
        return "plugin";
    }
}
```

These are **two alternative versions** with the same binary name `deps.Version`; they must be compiled into two separate directories.

**`src/plugin/extension/Feature.java`:**

```java
package extension;

import deps.Version;

public final class Feature {
    public String readVersion() {
        return Version.value();
    }
}
```

**`src/host/demo/DependencyChoiceDemo.java`:**

```java
package demo;

import deps.Version;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class DependencyChoiceDemo {
    private static URL directory(String name) throws Exception {
        return Path.of(name).toAbsolutePath().toUri().toURL();
    }

    private static String call(URLClassLoader loader) throws Exception {
        Class<?> feature = loader.loadClass("extension.Feature");
        Object instance = feature.getDeclaredConstructor().newInstance();
        return (String) feature.getMethod("readVersion").invoke(instance);
    }

    public static void main(String[] args) throws Exception {
        URL[] pluginUrls = {
                directory("plugin-out"),
                directory("pluginlib-out")
        };

        System.out.println("host direct=" + Version.value());
        ClassLoader app = DependencyChoiceDemo.class.getClassLoader();

        try (URLClassLoader appParent =
                    new URLClassLoader(pluginUrls, app);
             URLClassLoader platformParent =
                    new URLClassLoader(
                            pluginUrls,
                            ClassLoader.getPlatformClassLoader())) {

            System.out.println("app-parent feature=" + call(appParent));
            System.out.println("platform-parent feature=" +
                    call(platformParent));

            System.out.println("app uses host Class=" +
                    (appParent.loadClass("deps.Version") == Version.class));
            System.out.println("plugin copy differs=" +
                    (platformParent.loadClass("deps.Version")
                            != Version.class));
        }
    }
}
```

**Compile** from `dependency-choice-lab`:

```sh
javac --release 17 -d hostlib-out src/hostlib/deps/Version.java
javac --release 17 -d pluginlib-out src/pluginlib/deps/Version.java
javac --release 17 -cp pluginlib-out -d plugin-out src/plugin/extension/Feature.java
javac --release 17 -cp hostlib-out -d host-out src/host/demo/DependencyChoiceDemo.java
```

**Run on Windows PowerShell/CMD**:

```powershell
java -cp "host-out;hostlib-out" demo.DependencyChoiceDemo
```

**Run on Linux/macOS**:

```sh
java -cp "host-out:hostlib-out" demo.DependencyChoiceDemo
```

**Expected stdout on JDK 17+ when run from the correct directory:**

```text
host direct=host
app-parent feature=host
platform-parent feature=plugin
app uses host Class=true
plugin copy differs=true
```

**Careful explanation:**

1. The host application classpath consists of `host-out` and `hostlib-out`, **without `plugin-out`**.
2. Both child `URLClassLoader`s receive the same URL array with `plugin-out` and `pluginlib-out`. Each child defines `extension.Feature` itself because neither of their parents has this class.
3. With the **app parent**, the request for `deps.Version` is resolved by the parent first: the result is the `"host"` version on the host classpath.
4. With the **platform parent**, the platform loader does not see the custom `deps.Version` class on the application classpath. The child reads `pluginlib-out` and uses the `"plugin"` version.
5. `fromParent == Version.class` represents the same runtime type in the app branch; the platform branch has a `deps.Version` class with a different identity.
6. In this example, both versions have `public static String value()` so the output can be observed without causing binary compatibility errors. If the signatures differ, linkage errors may occur when invoking the method.

**Core takeaway:** Changing only the parent without changing the plugin bytes altered the dependency binding. This is why configuring the parent must be an **intentional design decision**, not an arbitrary parameter.

## 8. Inherited Scope Is Not a Copy of the Classpath or Maven Dependencies

“The parent contains the dependency” can mean several different things:

| Concept | What does it decide? | Automatically copied into the child? |
| --- | --- | --- |
| `javac -cp ...` | Which types the compiler sees at compile time | No |
| `java -cp ...` | Which sources the application/system loader can look up at runtime | No |
| Parent chain | Which classes the child can delegate lookup for | No |
| `URLClassLoader.getURLs()` | The child's own URL roots | Does not contain the parent's URLs |
| Maven/Gradle transitive graph | Which artifacts are built/resolved according to build tool configuration | Not automatically loaded into `URLClassLoader` |
| Module `requires`/JPMS readability | Which module is allowed to read which module | Not equivalent to the parent chain |

If a plugin compiles against `api.Shared` and `lib.Helper` while the runtime parent only provides `api.Shared` and the child URLs only contain the plugin JAR, then **`lib.Helper` may still be missing**. A successful compile does not guarantee that the URL loader sees all required dependencies at runtime.

A URL pointing to a **directory containing JAR files** also does not automatically scan all JARs inside it: to make each JAR visible to the loader, you normally have to put **each JAR's URL** into the array, or use another mechanism to manage the classpath.

## 9. Choosing a Parent Based on Shared API Identity

The host typically defines a contract such as:

```java
package api;

public interface Plugin {
    String execute();
}
```

If the host loads `api.Plugin` with the application loader, while the plugin chooses the platform parent and **loads its own copy** of `api.Plugin` from its own URLs, the JVM may end up with two distinct interfaces:

```text
HostLoader    defines api.Plugin   → Class A
PluginLoader  defines api.Plugin   → Class B

A.getName().equals(B.getName())    → true
A == B                              → false
A.isAssignableFrom(PluginImpl.class) → false
    (if PluginImpl implements B instead of A)
```

This can cause a `ClassCastException` even though both copies of the API have the exact same source. Type identity in the JVM is **(binary name, defining loader)**.

**Proper design:** the host's and plugin's shared API must be loaded as the **exact same `Class<?>`**, usually via a parent/delegation to a common loader. Implementations and private libraries can live under separate loaders as long as they do not break types crossing the boundary.

An interface is not the only boundary type: DTOs, callbacks, exceptions, annotations, method parameter/return types, enums, and classes in reflective signatures may also need shared identity.

## 10. Hands-On C — Separate Implementation, Contract from Parent

Create the structure:

```text
shared-api-lab/
└── src/
    ├── api/api/Plugin.java
    ├── plugin/impl/EchoPlugin.java
    └── host/demo/SharedApiDemo.java
```

**`src/api/api/Plugin.java`:**

```java
package api;

public interface Plugin {
    String execute();
}
```

**`src/plugin/impl/EchoPlugin.java`:**

```java
package impl;

import api.Plugin;

public final class EchoPlugin implements Plugin {
    @Override
    public String execute() {
        return "plugin ready";
    }
}
```

**`src/host/demo/SharedApiDemo.java`:**

```java
package demo;

import api.Plugin;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class SharedApiDemo {
    public static void main(String[] args) throws Exception {
        URL source =
                Path.of("plugin-out").toAbsolutePath().toUri().toURL();
        ClassLoader apiOwner = Plugin.class.getClassLoader();

        try (URLClassLoader pluginLoader = new URLClassLoader(
                new URL[] { source }, apiOwner)) {

            Class<?> implementation =
                    pluginLoader.loadClass("impl.EchoPlugin");
            Class<?> contract = implementation.getInterfaces()[0];

            System.out.println("implementation from child=" +
                    (implementation.getClassLoader() == pluginLoader));
            System.out.println("API shared=" + (contract == Plugin.class));
            System.out.println("assignable=" +
                    Plugin.class.isAssignableFrom(implementation));

            Plugin service = (Plugin) implementation
                    .getDeclaredConstructor()
                    .newInstance();
            System.out.println("result=" + service.execute());
        }
    }
}
```

Compile inside `shared-api-lab`:

```sh
javac --release 17 -d api-out src/api/api/Plugin.java
javac --release 17 -cp api-out -d plugin-out src/plugin/impl/EchoPlugin.java
javac --release 17 -cp api-out -d host-out src/host/demo/SharedApiDemo.java
```

Run on **Windows**:

```powershell
java -cp "host-out;api-out" demo.SharedApiDemo
```

Or on **Linux/macOS**:

```sh
java -cp "host-out:api-out" demo.SharedApiDemo
```

**Expected stdout with the configuration above:**

```text
implementation from child=true
API shared=true
assignable=true
result=plugin ready
```

`impl.EchoPlugin` only exists in `plugin-out`, so it is defined by the child. `api.Plugin` is found by the host API loader via the parent, so `EchoPlugin` genuinely implements the same interface that the host uses; the cast is valid.

If you put `plugin-out` onto the host application classpath, parent-first delegation may cause the implementation to be loaded by the host as well. **Do not do that in this experiment** because the goal is to verify separate child and parent identities.

## 11. What If You Want to Isolate Private Libraries While Sharing the API?

A good plugin model typically aims for:

- **Parent-first for `api.*` and Java platform types:** protects shared runtime identity.
- **Plugin-private for `impl.*` and certain `vendor.*` packages:** allows different dependency versions.
- **A clear collision-handling mechanism:** prevents the same binary name from being used accidentally in two places.
- **Attention to boundary signatures:** if `api.Plugin.execute(vendor.JsonNode)` uses a library type, `JsonNode` has become part of the boundary; each side cannot arbitrarily have a copy with a different identity.

`URLClassLoader` with the default `loadClass` is **parent-first**, with no constructor switch for “child-first for vendor package”. If you want a complex policy, you can write a custom loader that overrides `loadClass`, but that is difficult work: you must preserve `findLoadedClass`, class-loading locks, race avoidance, loading constraints, `java.*` names, and module/resource policies. A simpler approach when possible is to **redesign shared/API dependency placement** so that the parent holds only the contract that genuinely needs to be shared.

Do not try to put every dependency inside the plugin JAR and immediately switch the parent to `null`; doing so can make `api.Plugin` no longer share the same runtime type with the host.

## 12. Parent and Resources: Close, Yet Not Completely Identical

`URLClassLoader` provides the methods:

```java
URL found = loader.getResource("config/settings.properties");
URL local = loader.findResource("config/settings.properties");
URL[] ownSources = loader.getURLs();
```

This is a **snippet**: it requires `loader` of type `URLClassLoader` and importing `java.net.URL`.

- `getResource` follows the loader's lookup mechanism and may return a resource from the parent first.
- `URLClassLoader`'s `findResource` searches for the resource in the loader's own sources without using the parent the way `getResource` does by default.
- `getURLs` only describes the URL roots configured for the child; it does not list parent URLs.
- `getResourceAsStream` reads a resource as a stream (or `null` if not found), so you need to check for `null` and close the stream.
- Resources in a named module may be subject to separate encapsulation rules; seeing a class from the same loader does not guarantee being able to read every resource whose package is not opened.

If both the host and plugin have `config/settings.properties`, parent-first resource lookup can cause the host version to be chosen. Use `getResource`/`getResources` to inspect what actually happens and use clear resource namespaces, rather than treating it as a `ClassLoader.loadClass` bug.

The **TCCL** (`Thread.currentThread().getContextClassLoader()`) is also not automatically equal to `loader.getParent()`. A framework may use the TCCL for `ServiceLoader` discovery, but choosing a `URLClassLoader`'s parent does not automatically change the TCCL on the thread.

## 13. Accurate URL Paths and Dependency Packaging

For an output directory:

```java
URL classes =
        Path.of("plugin-out").toAbsolutePath().toUri().toURL();
```

This is a snippet requiring imports `java.net.URL` and `java.nio.file.Path`. `Path.toUri()` helps produce a valid file URL, avoiding faulty `file:///...` string concatenation when directory names contain spaces.

For a JAR:

```java
URL jar = Path.of("plugins", "feature.jar")
        .toAbsolutePath().toUri().toURL();

URLClassLoader loader = new URLClassLoader(
        new URL[] { jar }, ClassLoader.getPlatformClassLoader());
```

The snippet does not include a `close` lifecycle yet, so in a real application you need to manage the created loader.

Checks:

1. A URL to a directory must point to the **root of the package layout**. For example, `out/extension/Feature.class` corresponds to the binary name `extension.Feature`, so the URL must point to `out/`.
2. A URL to a JAR must point directly to the **JAR file**, not just a directory containing multiple JARs expecting the loader to scan it recursively.
3. A JAR containing only the implementation does not automatically supply all transitive dependencies. The runtime parent or other URLs must be able to see the required dependencies.
4. If multiple URLs belonging to the child contain the same class name, the search order can cause conflicts. Explicit packaging and avoiding duplicates are healthier than relying on order.
5. `getURLs()` shows the child's own URLs, but is **not enough** to determine which class the parent selected.
6. `URLClassLoader` suits classpath-style sources; merely placing a modular JAR in its URLs does not automatically build a **JPMS module layer**.

## 14. Common Errors When Choosing the Wrong Parent

| Error/symptom | What to check | How to fix |
| --- | --- | --- |
| `ClassNotFoundException` | Neither the parent nor the child's own URLs found the class name | Check binary name, roots/JARs, parent, and runtime paths |
| `NoClassDefFoundError` | A dependency needed at linking/initialization is not defined, or prior initialization failed | Read `Caused by`, runtime JAR versions, and the initializer |
| `NoSuchMethodError` | The parent returned an older library lacking the method descriptor the plugin compiled against | Compare `javap -s` and parent classpath; avoid version skew |
| `NoSuchFieldError` | Field name/descriptor at runtime differs from compile-time | Compare the actual class files |
| `ClassCastException` despite the same interface name | Host and plugin use two definitions of the shared API | Print defining loaders; share the exact `Class<?>` |
| `LinkageError` loader constraint violation | A cross-loader signature contains types with incompatible identities | Check all boundary DTO, return, and parameter types |
| `IllegalAccessError` | Runtime access/package/module restrictions | Check visibility and JPMS readability/exports |
| Resource returns wrong content | Parent resource shadows child resource | Check `getResource`, `getResources`, and resource namespaces |
| `ServiceConfigurationError` | Service API and provider do not share runtime identity, or provider error | Check ServiceLoader/TCCL, runtime API, and provider metadata |
| Plugin does not unload | Host/threads/caches/TCCL retain references or loader has not been closed | Manage lifecycle and release references |

**Not all of the errors above stem from missing JARs.** Some are caused by lookup, some by bytecode linkage, and some by type identity or module access. Use the exception/error type and stack trace to narrow down the cause.

## 15. Tools for Debugging Dependency Scope

A helper snippet for a loaded class:

```java
static void describe(Class<?> type) {
    System.out.println("name=" + type.getName());
    System.out.println("defining loader=" + type.getClassLoader());
    System.out.println("module=" + type.getModule().getName());
}
```

This is an **illustrative method**, not a standalone program. `getModule().getName()` may return `null` for an unnamed module; this is normal.

You can inspect the parent and own URLs:

```java
System.out.println("parent=" + pluginLoader.getParent());
System.out.println("urls=" +
        java.util.Arrays.toString(pluginLoader.getURLs()));
```

When you suspect the wrong class version was picked, use `javap` to read the **binary signatures** in each artifact:

```sh
javap -classpath hostlib-out -s deps.Version
javap -classpath pluginlib-out -s deps.Version
javap -classpath plugin-out -c -v extension.Feature
```

The commands above apply from the directory of Example B after compiling. `javap` verifies which symbols the bytecode references; it **does not** show which class the runtime selected from the parent. Combine it with `Class.getClassLoader()`.

HotSpot supports Unified Logging:

```sh
java -Xlog:class+load=info -cp "host-out:hostlib-out" demo.DependencyChoiceDemo
```

The `-cp` example uses Linux/macOS syntax; on Windows replace `:` with `;`. Class-loading logs can be long and runtime-dependent; they help show the source of class bytes, but do not prove that class initialization or method resolution has completed.

## 16. URLClassLoader Lifecycle and Swapping Plugins

`URLClassLoader` implements `Closeable` and can be used with `try-with-resources` as in the hands-on exercises:

```java
try (URLClassLoader plugin = new URLClassLoader(urls, parent)) {
    Class<?> feature = plugin.loadClass("extension.Feature");
    // Use feature while the loader still serves lookups.
}
```

This is a snippet with `urls` and `parent` already available. `close()` closes the resource handles managed by the loader. **It does not mean all of the plugin's classes/objects have unloaded immediately**.

Notes:

- A running plugin may need to lazy-load dependencies; **do not close the loader before the end of the plugin's usage lifecycle**.
- A host registry may still hold plugin objects, `Class<?>`, reflective `Method`s, callbacks, or the thread context class loader; these references can keep the loader alive.
- Replacing the JAR file on disk does not automatically replace a previously defined `Class<?>`.
- Reloading should create a new loader instance and a new plugin object, stop the old instance, release references, and check the contract API version.
- The shared API used through the parent should remain stable across the plugin lifecycle; do not redefine a copy of the contract on each reload.

## 17. Checklist for Choosing a Parent Before Implementation

1. List all **boundary types**: SPI, DTOs, callbacks, exceptions, annotations, and types in method descriptors.
2. Identify the **actual defining loader** of the shared API; do not guess the system loader just because the host is running.
3. List **private dependencies** and host versions that may share the same binary name.
4. Choose the parent (system, platform, bootstrap/null, or a custom API loader) based on the two sets above.
5. Verify child URL roots: accurate directory/JAR URLs containing all necessary private dependencies.
6. Determine whether parent-first causes shadowing; only use a custom child-first loader when you clearly understand the risks.
7. Integration-test the **plugin JAR through a real loader**; do not place the plugin JAR onto the application classpath when the goal is to test isolation.
8. Assert shared API identity using `isAssignableFrom` or `Class<?> == Class<?>`, not just `getName()`.
9. Observe resource URLs and TCCL if the plugin uses config/service discovery.
10. Check JPMS module rules if the application uses named modules.
11. Manage `close`, plugin lifecycle, callbacks, threads, and references.
12. Do not treat a class loader as a security sandbox for untrusted code.

### Illustrative Test

```java
if (pluginLoader.getParent() != expectedParent) {
    throw new AssertionError("Wrong parent");
}
if (!SharedPluginApi.class.isAssignableFrom(implementationClass)) {
    throw new AssertionError("Wrong API identity");
}
```

This is a snippet requiring the variables `pluginLoader`, `expectedParent`, `implementationClass` as well as an actual `SharedPluginApi` type. If the implementation **must** be defined by the child, you can add `implementationClass.getClassLoader() == pluginLoader`; do not apply that assertion to classes provided by the parent by design.

## 18. Common Misconceptions to Avoid

- **“`new URLClassLoader(urls)` defaults its parent to bootstrap.”** False: the default is the system class loader.
- **“An empty `getURLs()` means the loader cannot find classes.”** False: delegation still works.
- **“If the parent has dependency v1 and a plugin URL contains v2, v2 always wins.”** False under default parent-first delegation.
- **“All JARs from the parent are copied into the child.”** False: the parent returns classes from its own namespace/logic.
- **“The parent class loader is the Java superclass of URLClassLoader.”** False: the parent is a referenced object.
- **“Switching the parent to platform preserves all host-defined SPIs.”** Not by default; the platform loader is not the application classpath loader.
- **“A null parent is a safe sandboxing solution.”** False: class loader visibility is not a complete security boundary.
- **“Having the same interface name is enough for the host to cast a plugin object.”** False: runtime identity also depends on the defining loader.
- **“If Maven compiles, URLClassLoader is guaranteed to see all transitive dependencies.”** False: the runtime classpath must actually be configured.
- **“A URL pointing to a plugin directory automatically scans all JARs inside it.”** Not by default.
- **“`close()` immediately removes classes currently in use.”** False: garbage collection/unloading depends on references.
- **“Resource lookup and class lookup always follow the same order/namespace.”** You must inspect the actual API and loader.

## 19. Self-Check Questions

**1. What parent does the single-argument constructor `URLClassLoader(urls)` choose?** The system class loader.

**2. Why can a child with empty URLs still find `java.lang.String`?** The child can delegate to its parent/ancestor or bootstrap.

**3. Why do the app parent and platform parent give different results with the same URL array in Example A?** Because they have different class visibility scopes via delegation.

**4. The parent contains `deps.Version` v1 and the child URL contains v2: which version is usually selected?** Parent v1 under the default parent-first `loadClass`.

**5. What error can occur if v1 lacks a method required by the plugin?** `NoSuchMethodError`, depending on the binary mismatch and when the symbol is used.

**6. Does `getURLs()` reflect every JAR visible to the parent?** No; it only returns the child's own URLs.

**7. When should you choose the platform loader?** When the plugin needs Java platform APIs without inheriting the entire application classpath by default, and the shared API is designed separately.

**8. If the plugin must implement `api.Plugin` defined by the host, how should you choose the parent?** Ensure the plugin loader resolves the interface through **the exact defining loader of the shared API**.

**9. Do two classes with the same binary name defined by two loaders have the same runtime type?** No, type identity also includes the defining loader.

**10. Is a null parent guaranteed to see all Java SE classes?** No, on Java 9+; some platform classes do not belong to the bootstrap loader.

**11. Is the parent object the Java superclass of URLClassLoader?** No; `getParent()` and `getSuperclass()` describe two different relationships.

**12. Does `close()` unload a plugin immediately?** No; references must be released and the JVM decides when class unloading occurs.

## 20. Official References and Conclusion

- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): constructor parent, `getURLs`, `findClass`, `findResource`, `close`.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, parent delegation, `getParent`, `getSystemClassLoader`, `getPlatformClassLoader`.
- [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getClassLoader` and `isAssignableFrom` when checking type identity.
- [Java Virtual Machine Specification Java SE 17, Chapter 5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): defining/initiating loaders, runtime type identity, linking, and loading constraints.
- [JDK 17 javap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): inspect method descriptors and bytecode to debug binary mismatches.

**Rule to remember:** `URLClassLoader` has **its own class sources in the URL array**, yet **sees dependencies that its parent can provide through delegation**. Parent-first helps share API contracts while also potentially causing a host version to shadow a plugin version. Choose the parent according to **shared API identity and private dependency boundaries**, then test exactly which loader defines each class — do not just look at JAR names or class names.
