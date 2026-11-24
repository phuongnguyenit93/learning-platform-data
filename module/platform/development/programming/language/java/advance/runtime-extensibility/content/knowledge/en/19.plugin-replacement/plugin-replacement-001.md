# Distinguishing SPI Cache Reload, Object Replacement, and Class Definition Replacement

In a Java application extensible via plugins, the word **“reload”** is often used for three different actions:

1. Clearing the service discovery cache of `ServiceLoader` to iterate over providers again.
2. Replacing **the provider object currently used by the application**, such as swapping a reference in a registry.
3. Loading **a new class definition** when replacing a bytecode/JAR version, usually with a new `ClassLoader` or a dedicated class redefinition mechanism.

They are **not equivalent**. Calling `ServiceLoader.reload()` does not replace bytecode by itself; creating a new provider object does not prove the class has changed; and having a new class definition does not automatically route in-flight requests to the new object.

This lesson builds all three levels of replacement, explains their boundaries and lifecycles, and then runs a **Java 17** program using two plugin JARs that both contain `demo.plugin.GreetingProvider` but have different implementations. Every observable result can be verified through object identity, class identity, and `ClassLoader`.

## 1. Three layers of state to track

When a Java host uses SPI, there are at least three independent components:

```text
Shared SPI: demo.spi.Greeter
           |
           v
  ServiceLoader<Greeter>      (discovery/instance cache)
           |
           v
  Greeter provider instance  (object held by the application)
           |
           v
  Class<?> + ClassLoader     (bytecode definition loaded by the JVM)
```

If the application has a registry holding the currently used provider:

```text
ServiceLoader instance  ---->  cached provider A
                                    |
Host registry ----------->  active provider A
                                    |
                                Class A
                                    |
                           defining ClassLoader
```

Then three **separate** changes can occur:

| Action | What is changed directly | What does **not change automatically** |
|---|---|---|
| `ServiceLoader.reload()` | Provider cache belonging to **that exact `ServiceLoader` instance** | Old object held by the host, already-defined `Class<?>`, classpath, JAR on disk |
| `active.set(newProvider)` | Active reference that the host uses to select the provider | `ServiceLoader` cache, existing bytecode/class, old references already held by requests |
| Loading a new JAR with a new loader | Can create a new `Class<?>` and instance from new bytecode | Active reference, in-progress sessions, objects/classes of the old loader |

A complete **new plugin deployment** operation may need to perform all three according to a strategy; however, it must explicitly specify who is responsible for each step. `reload()` should not be treated as a comprehensive hot-deployment API.

## 2. ServiceLoader is a provider discovery mechanism, not a code updater

On the **classpath**, providers are registered using the resource:

```text
META-INF/services/<fully qualified binary name of the service type>
```

For example, the SPI `demo.spi.Greeter` will have the resource:

```text
META-INF/services/demo.spi.Greeter
```

Inside the registration file is the fully qualified name of the implementation, for example:

```text
demo.plugin.GreetingProvider
```

`ServiceLoader.load(Greeter.class, loader)` uses the passed class loader to locate service configurations, check the provider type, and instantiate providers according to the corresponding rules. Providers are usually discovered/instantiated **lazily** when the application iterates over the iterator or stream; merely creating the `ServiceLoader` object does not guarantee that all providers have been instantiated.

A `ServiceLoader` instance maintains a **cache of loaded providers**. When iterating again with `iterator()` without calling `reload()`, the cached provider is normally the **same object returned earlier**. This allows the same service loader to return the object it already loaded, rather than constructing a new one on every iteration.

### What exactly does `reload()` do?

```java
ServiceLoader<Greeter> services =
        ServiceLoader.load(Greeter.class, pluginLoader);

Greeter before = services.iterator().next();
services.reload();
Greeter after = services.iterator().next();
```

This is an **illustrative snippet**, assuming `Greeter` and `pluginLoader` already exist and the service loader finds at least one provider. In the complete program below, we also check the provider count.

Behaviors to remember:

- `services.reload()` **clears the provider cache** of `services`; the next iteration can discover and instantiate providers again. For a classpath provider with a public no-argument constructor as in this example, it creates a **new instance**.
- `reload()` **does not delete the `before` object held by the application**. The `before` reference still points to the old object; if the object has not been closed under application policy, it can still be used.
- `reload()` **does not remove the class from the JVM and does not invoke a new `ClassLoader`**. If the provider class was already defined by the same loader, the new instance continues to have the same `Class<?>`.
- **Static fields, static caches, and static initializers of an already-loaded class are not reset merely by reloading the service.** The new instance still sees the static state belonging to the same class.
- `reload()` **does not automatically add a new JAR to the classpath or module path**, does not replace an already-open JAR, does not update the class loader's URLs, and does not select a provider for the host.
- Iterators/streams in use before calling `reload()` must be discarded and a new iteration started; do not iterate and reload at the same time, because errors may occur due to cache changes.

`ServiceLoader` is also not guaranteed to be thread-safe for concurrent operations on the same instance. If one thread is iterating while another thread calls `reload()`, do not expect that to be a safe update procedure. Proper synchronization and ownership are needed, or a separate immutable snapshot should be built after discovery.

### When is cache reload actually useful?

You can use `reload()` when **the discovery configuration visible to the current class loader** has changed in a supported way and you want to re-iterate services. However, do not assume that every approach of “dropping a JAR file into a directory” will be picked up automatically by the loader. With a `URLClassLoader` created statically from JAR URLs, calling `reload()` **does not automatically add new URLs**.

In particular, if a class's bytecode has already been defined by the loader, reload does not replace that class definition. To refresh the implementation version, you must address class loading or instrumentation, not just the cache.

## 3. Object replacement: controlled switching of the active reference

Suppose the host holds the active provider in:

```java
AtomicReference<Greeter> active =
        new AtomicReference<>(oldProvider);
```

When a new provider object is eligible to run:

```java
active.set(newProvider);
```

This is a **snippet**, not a standalone program. `AtomicReference` ensures that reading/writing the reference through that API is atomic and has proper visibility across threads, but it does **not** automatically orchestrate full replacement of all resources.

Key points:

1. **Object identity changes:** `active.get()` returns `newProvider` for reads after the reference is updated.
2. **Class identity may not change:** if `oldProvider` and `newProvider` were created from the same class loader, `oldProvider.getClass() == newProvider.getClass()` is `true`.
3. **Old references do not vanish:** a request that executed `Greeter p = active.get()` before the swap can still continue calling `p` after the registry is switched.
4. **Old plugin is not closed automatically:** if the old object holds files, sockets, threads, executors, or callbacks, the application must define how to stop/reclaim them.
5. **Static state is not reset:** two different objects belonging to the same `Class<?>` can still share static fields.

For example, with a provider that has an instance sequence number:

```text
v1#1:Java  <-- first object
v1#2:Java  <-- different object, same class and same static counter
```

Seeing `#2` instead of `#1` proves the objects are different, but it does **not** prove the bytecode was replaced.

In a multithreaded system, `active.set(...)` is only **switching the entry point**. If the old plugin must not be stopped while requests are running, the host needs **quiescence / draining / lease / reference counting** or an appropriate handoff protocol. Never close the old class loader or resources immediately while requests are still using them.

## 4. Class definition replacement: the issue lies in the class loader

The JVM distinguishes classes not only by their fully qualified name. In terms of class-loading identity, a class is identified by **its binary name and its defining class loader**:

```text
("demo.plugin.GreetingProvider", loaderV1)
    !=
("demo.plugin.GreetingProvider", loaderV2)
```

The notation above describes the model, not Java syntax.

If two plugin JARs both contain a class with the same name `demo.plugin.GreetingProvider`:

- `loaderV1` can define this class from `plugin-v1.jar`.
- `loaderV2` can define a class **with the same name** from `plugin-v2.jar`.
- The two `Class<?>` objects are different: `v1.getClass() != v2.getClass()`.
- Static fields of the class belonging to the two class loaders are kept **separate**.
- If the host uses SPI properly, both classes can be cast to **the same interface** `demo.spi.Greeter`.

To achieve the last point, the host must **share the SPI definition from a parent class loader**. If each child loader defines its own copy of `demo.spi.Greeter`, they are two different interfaces despite having the same name; the host may encounter `ClassCastException` or `ServiceConfigurationError` because the provider is not a subtype of the type required by the host.

Diagram:

```text
                 Application ClassLoader (parent)
                      spi.jar + host.jar
                              |
                       demo.spi.Greeter
                              |
              +---------------+---------------+
              |                               |
        loaderV1                         loaderV2
     plugin-v1.jar                    plugin-v2.jar
              |                               |
  demo.plugin.GreetingProvider   demo.plugin.GreetingProvider
           Class #1                         Class #2
      static count = 2                  static count = 1
              |                               |
              +---------------+---------------+
                              |
                       host uses Greeter
```

In the demo, the application classpath **does not contain the provider JARs**. Therefore, the default parent-first delegation rule of `URLClassLoader` does not cause the parent to mistakenly load the provider. Each child only has a URL pointing to its own JAR.

**Warning:** If the host classpath also contains a provider class with the same name, parent-first delegation can cause the child to see the parent's class instead of the class in its own JAR. For complex plugin architectures, namespaces, packages, and delegation rules must be designed clearly. Do not arbitrarily use child-first for the entire SPI package, as doing so can duplicate the contract.

## 5. Runnable example: same provider name, two JAR versions

Problem: the host knows only the SPI `Greeter`, while provider versions 1 and 2 are packaged as **two independent artifacts**, sharing the same class name but having different bytecode.

We will observe three phases:

1. `ServiceLoader` iterates twice on the same cache → returns the same instance.
2. Call `reload()`, iterate again → different instance, still the same class.
3. Create a new loader pointing to the v2 JAR and switch `active` to the new provider → different class, still the same shared SPI.

### 5.1. File tree

Create the following files inside the `spi-replacement-demo` directory:

```text
spi-replacement-demo/
├── contract/
│   └── src/demo/spi/Greeter.java
├── plugin-v1/
│   ├── src/demo/plugin/GreetingProvider.java
│   └── resources/META-INF/services/demo.spi.Greeter
├── plugin-v2/
│   ├── src/demo/plugin/GreetingProvider.java
│   └── resources/META-INF/services/demo.spi.Greeter
└── host/
    └── src/demo/host/Main.java
```

When compiling, we produce four JARs:

```text
dist/
├── spi.jar
├── host.jar
├── plugin-v1.jar
└── plugin-v2.jar
```

Do not place both provider versions on the same application classpath. `host.jar` depends only on `spi.jar` at compile time, without importing a concrete implementation.

### 5.2. SPI contract — only one copy

File `contract/src/demo/spi/Greeter.java`:

```java
package demo.spi;

public interface Greeter {
    String id();

    String greet(String name);
}
```

The SPI keeps a stable signature. Plugin versions can change internal code, yet all `implements Greeter`. `id()` illustrates a business identifier; both versions return `"greeting"`, because **they are two replacement versions of the same capability**, not two different kinds of services.

Business identity must be distinguished from **class identity**: two providers having the same `id()` does not mean they are the same object, the same bytecode, or from the same class loader. If the host simultaneously registers multiple providers with the same ID into **an active registry**, there must be an explicit version selection policy.

### 5.3. Version 1 implementation

File `plugin-v1/src/demo/plugin/GreetingProvider.java`:

```java
package demo.plugin;

import demo.spi.Greeter;

public final class GreetingProvider implements Greeter {
    private static int constructed;
    private final int number = ++constructed;

    @Override
    public String id() {
        return "greeting";
    }

    @Override
    public String greet(String name) {
        return "v1#" + number + ":" + name;
    }
}
```

`constructed` is a static field incremented upon object instantiation; `number` stores the sequence number of each instance. The example executes sequentially without sharing the constructor across threads. In a real application with concurrency, a counter used for inspection may need `AtomicInteger` or appropriate synchronization.

### 5.4. Version 2 implementation

File `plugin-v2/src/demo/plugin/GreetingProvider.java`:

```java
package demo.plugin;

import demo.spi.Greeter;

public final class GreetingProvider implements Greeter {
    private static int constructed;
    private final int number = ++constructed;

    @Override
    public String id() {
        return "greeting";
    }

    @Override
    public String greet(String name) {
        return "v2#" + number + ":" + name;
    }
}
```

Both source files declare `public final class GreetingProvider` in `package demo.plugin`, but with **different return values**. Each source is compiled into a separate output directory and packaged into a separate JAR.

Passing both sources to a single `javac` invocation with the same package/class would collide on duplicate definitions. The isolation mechanism here occurs **at class loading time**, not by compiling two files of the same name into a single directory.

### 5.5. Registration via `META-INF/services`

In **both** resource directories:

```text
plugin-v1/resources/META-INF/services/demo.spi.Greeter
plugin-v2/resources/META-INF/services/demo.spi.Greeter
```

the file contents are **identical**:

```text
demo.plugin.GreetingProvider
```

This is valid because each `URLClassLoader` only has the URL for one provider JAR; each loader finds the class with the same name but a different definition. The registration file must reside inside the corresponding JAR, not inside `spi.jar`/`host.jar`.

Both providers are public classes with a default public no-argument constructor; they conform to classpath provider instantiation in this example.

## 6. Host: observing cache, swapping object, replacing class

Complete file `host/src/demo/host/Main.java`:

```java
package demo.host;

import demo.spi.Greeter;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.Iterator;
import java.util.ServiceLoader;
import java.util.concurrent.atomic.AtomicReference;

public final class Main {
    private static Greeter exactlyOne(ServiceLoader<Greeter> services) {
        Iterator<Greeter> iterator = services.iterator();

        if (!iterator.hasNext()) {
            throw new IllegalStateException("No provider");
        }
        Greeter result = iterator.next();
        if (iterator.hasNext()) {
            throw new IllegalStateException("More than one provider");
        }
        return result;
    }

    public static void main(String[] args) throws Exception {
        Path dist = Path.of("dist").toAbsolutePath();
        ClassLoader parent = Greeter.class.getClassLoader();

        URL[] v1 = {
                dist.resolve("plugin-v1.jar").toUri().toURL()
        };
        URL[] v2 = {
                dist.resolve("plugin-v2.jar").toUri().toURL()
        };

        try (URLClassLoader loaderV1 = new URLClassLoader(v1, parent);
             URLClassLoader loaderV2 = new URLClassLoader(v2, parent)) {

            ServiceLoader<Greeter> servicesV1 =
                    ServiceLoader.load(Greeter.class, loaderV1);

            Greeter first = exactlyOne(servicesV1);
            Greeter cached = exactlyOne(servicesV1);
            System.out.println("cached same object: " + (first == cached));
            System.out.println("before reload: " + first.greet("Java"));

            servicesV1.reload();
            Greeter fresh = exactlyOne(servicesV1);
            System.out.println("after reload: " + fresh.greet("Java"));
            System.out.println("same object after reload: " + (first == fresh));
            System.out.println("same Class after reload: "
                    + (first.getClass() == fresh.getClass()));
            System.out.println("old object still works: "
                    + first.greet("Java"));

            AtomicReference<Greeter> active = new AtomicReference<>(first);
            active.set(fresh);
            System.out.println("active after object swap: "
                    + active.get().greet("Java"));

            Greeter v2Provider = exactlyOne(
                    ServiceLoader.load(Greeter.class, loaderV2));
            active.set(v2Provider);
            System.out.println("active after loader switch: "
                    + active.get().greet("Java"));
            System.out.println("old object still works after switch: "
                    + first.greet("Java"));

            System.out.println("same binary name: "
                    + first.getClass().getName().equals(
                            v2Provider.getClass().getName()));
            System.out.println("same runtime Class: "
                    + (first.getClass() == v2Provider.getClass()));

            boolean sharedContract =
                    loaderV1.loadClass("demo.spi.Greeter") == Greeter.class
                    && loaderV2.loadClass("demo.spi.Greeter") == Greeter.class;
            System.out.println("shared SPI Class: " + sharedContract);
        }
    }
}
```

The program imports only `demo.spi.Greeter`. It **does not import** `demo.plugin.GreetingProvider`, does not call provider constructors manually, and does not merge the plugin JARs onto the application classpath.

`exactlyOne(...)` requires each loader to supply **exactly one provider**; this is the demo's policy. In a real system, if a class loader scope has multiple providers, a selector by ID/capability/configuration is needed instead of taking the first element. Returning `Greeter` also keeps the host independent of implementation names.

`AtomicReference<Greeter>` simulates the active registry. In the example it is updated sequentially in `main`; merely having `AtomicReference` **does not automatically create a safe lifecycle mechanism** for a multithreaded server system.

## 7. Compiling and running with Java 17+

JDK 17 or newer (`java`, `javac`, `jar`) is required. Run from the root directory `spi-replacement-demo` containing `contract`, `plugin-v1`, `plugin-v2`, and `host`.

### 7.1. Linux/macOS (Bash)

```bash
mkdir -p out/spi out/plugin-v1 out/plugin-v2 out/host dist

javac --release 17 -encoding UTF-8 -d out/spi contract/src/demo/spi/Greeter.java
jar --create --file dist/spi.jar -C out/spi .

javac --release 17 -encoding UTF-8 -cp dist/spi.jar -d out/plugin-v1 plugin-v1/src/demo/plugin/GreetingProvider.java
jar --create --file dist/plugin-v1.jar -C out/plugin-v1 . -C plugin-v1/resources .

javac --release 17 -encoding UTF-8 -cp dist/spi.jar -d out/plugin-v2 plugin-v2/src/demo/plugin/GreetingProvider.java
jar --create --file dist/plugin-v2.jar -C out/plugin-v2 . -C plugin-v2/resources .

javac --release 17 -encoding UTF-8 -cp dist/spi.jar -d out/host host/src/demo/host/Main.java
jar --create --file dist/host.jar -C out/host .

java -cp "dist/spi.jar:dist/host.jar" demo.host.Main
```

### 7.2. Windows PowerShell

On Windows, classpath entries are separated by `;`. When using PowerShell, wrap the classpath string in single quotes:

```powershell
New-Item -ItemType Directory -Force out/spi,out/plugin-v1,out/plugin-v2,out/host,dist | Out-Null

javac --release 17 -encoding UTF-8 -d out/spi contract/src/demo/spi/Greeter.java
jar --create --file dist/spi.jar -C out/spi .

javac --release 17 -encoding UTF-8 -cp dist/spi.jar -d out/plugin-v1 plugin-v1/src/demo/plugin/GreetingProvider.java
jar --create --file dist/plugin-v1.jar -C out/plugin-v1 . -C plugin-v1/resources .

javac --release 17 -encoding UTF-8 -cp dist/spi.jar -d out/plugin-v2 plugin-v2/src/demo/plugin/GreetingProvider.java
jar --create --file dist/plugin-v2.jar -C out/plugin-v2 . -C plugin-v2/resources .

javac --release 17 -encoding UTF-8 -cp dist/spi.jar -d out/host host/src/demo/host/Main.java
jar --create --file dist/host.jar -C out/host .

java -cp 'dist/spi.jar;dist/host.jar' demo.host.Main
```

**Important note:** The final `java -cp` contains only `spi.jar` and `host.jar`, not the two plugin JARs. The host itself opens `plugin-v1.jar` and `plugin-v2.jar` through two separate `URLClassLoader` instances. If run from another directory, `Path.of("dist")` will no longer point to the right location and the path or working directory must be adjusted.

### 7.3. Exact stdout

```text
cached same object: true
before reload: v1#1:Java
after reload: v1#2:Java
same object after reload: false
same Class after reload: true
old object still works: v1#1:Java
active after object swap: v1#2:Java
active after loader switch: v2#1:Java
old object still works after switch: v1#1:Java
same binary name: true
same runtime Class: false
shared SPI Class: true
```

Explanation:

- `cached same object: true`: iterating the same `ServiceLoader` again before `reload()` returns the cached instance.
- `before reload: v1#1:Java`: the first v1 provider was instantiated, `constructed == 1`.
- `after reload: v1#2:Java`: when iterating after `reload()`, the v1 constructor runs again, creating a second instance.
- `same object after reload: false`: two instantiations produce two distinct Java objects.
- `same Class after reload: true`: both objects still share the same runtime class and the same defining class loader.
- `old object still works`: clearing the cache does not mean the JVM automatically destroys the old object.
- `active after object swap: v1#2:Java`: only the active registry changed to the new instance.
- `active after loader switch: v2#1:Java`: the host created a provider via the v2 loader and pointed active to it; the static counter of v2 starts separately at 1.
- `same binary name: true` yet `same runtime Class: false`: both versions have the same Java name, yet the JVM treats them as two different classes because their defining loaders differ.
- `shared SPI Class: true`: both children delegate the same `demo.spi.Greeter` to the parent, so both can be invoked by the host via the SPI.

The example distinguishes **cache replacement**, **object replacement**, and **class replacement** through independent observations, rather than guessing from a single “reloaded” log line.

## 8. Detailed comparison table: which state stays alive?

Assume `loaderV1` has defined `GreetingProvider` v1, and the host holds `first`.

| Check | After `ServiceLoader.reload()` | After `active.set(fresh)` on same loader | After creating v2 loader and `active.set(v2)` |
|---|---|---|---|
| Cache of v1 ServiceLoader instance | Cleared; will rediscover upon iteration | Unchanged by `active.set` | Unchanged automatically |
| Object `first` | Alive if host holds reference | Still alive if host/requests hold it | May still remain alive |
| Active provider object | Does not change automatically | Changes to `fresh` | Changes to v2 |
| `Class<?>` of new provider | Usually same class if still same loader | Same as `first` in the demo | Different because defined by loader v2 |
| Static state v1 | Still exists | Still shared by `fresh` | Does not vanish while loader v1 is alive |
| Static state v2 | Not involved | Not involved | Starts in class v2 when initialized |
| Loaded bytecode of class v1 | Not replaced | Not replaced | Not replaced |
| Requests already holding v1 provider | Do not switch automatically | Do not switch automatically | Do not switch automatically |
| Resources/JAR of old loader | Not closed automatically | Not closed automatically | Not closed automatically |

If a provider stores state in static fields, a new object of **the same class** may feel “brand new” yet still affect or be affected by shared state. To isolate a class version, the class loader is an essential part of the design; to clean up old state, references and lifecycle must also be handled.

## 9. Replacing the JAR file on disk is not replacing the loaded class

Once a class is defined in the JVM, its bytecode does not automatically change just because the source JAR file was replaced:

```text
plugin.jar v1 on disk
      |
      v
ClassLoader has defined GreetingProvider v1
      |
      v
Replace plugin.jar with v2 file at the same path
      |
      x
Does not automatically modify the already-defined GreetingProvider
```

`ClassLoader.loadClass()` typically checks whether a class is already loaded before searching for and defining a new class. Therefore, even if the loader re-reads service resources, if `demo.plugin.GreetingProvider` has already been defined by that loader, `ServiceLoader.reload()` will not turn it into the v2 class.

Replacing JAR contents directly underneath an active `URLClassLoader` also carries risks from JAR URL/resource caching, file locks, and deployment state; it should not be treated as a reliable upgrade method.

**Controllable strategy:** use versioned artifacts, such as `plugin-v1.jar`, `plugin-v2.jar`; create a new loader pointing to the exact new artifact; verify the provider before shifting traffic. That avoids requiring “overwriting” class definitions inside an old loader.

## 10. “Defining a new class” differs from “redefining a class in place”

There are **two** kinds of bytecode changes commonly referred to together as “replacing a class”:

### 10.1. Creating a new `Class<?>` with a new loader

This is the demo's strategy:

```text
old loader -> old Class<?> -> old provider
new loader -> new Class<?> -> new provider
```

Advantages: both versions can be kept side by side for testing, gradual traffic shifting, and rollback by switching the registry back to the old provider while it remains valid.

Limitations: old objects still belong to the old class; an old-version object cannot be automatically cast to the new class simply because both classes have the same name. Static state of the two loaders is separated; any information to be transferred must pass through shared data/SPI/DTOs or an intentional migration procedure.

### 10.2. Redefinition/retransformation via Java Instrumentation

Java provides the `java.lang.instrument.Instrumentation` API, such as `redefineClasses(...)` and `retransformClasses(...)` when supported by the agent/JVM. This is a specialized mechanism for **replacing the bytecode definition of an already-loaded class** within JVM/agent constraints.

Fundamental differences:

- No need to create a new `Class<?>` using a new class loader for that class name.
- Existing instances still belong to the redefined runtime class; subsequent method calls can use the replaced code.
- Class initialization does not automatically rerun just because of redefinition; static fields are not treated as brand-new storage.
- Method frames already executing can continue running old bytecode until they finish, rather than being patched mid-instruction.
- Common JVMs restrict **class structure changes** such as adding/removing fields or methods, or changing signatures/inheritance hierarchy; check `isRedefineClassesSupported()`/`isRetransformClassesSupported()` capabilities and practical constraints.

**`ServiceLoader.reload()` does not invoke `Instrumentation` and does not trigger HotSwap.** Replacing the loader with a versioned artifact and redefining in place are **two different strategies** with different scopes and risks. This lesson only **explains** Instrumentation and does not provide a runnable HotSwap agent because that is a separate deployment mechanism from refreshing the SPI cache.

## 11. Safe plugin replacement workflow in a server application

A plugin upgrade can be designed in phases:

```text
[1] Prepare new artifact, verify checksum/version/dependencies
                       |
                       v
[2] Create new class loader, keep shared SPI/API in parent
                       |
                       v
[3] Discover new provider, verify contract/configuration
                       |
                       v
[4] Initialize, warm up, health-check, verify compatibility
                       |
                       v
[5] Switch active registry to new provider (atomic pointer)
                       |
                       v
[6] Wait for old requests using the old provider to finish
                       |
                       v
[7] Unregister callbacks, stop threads/workers, close resources
                       |
                       v
[8] Close old loader when safe; drop references so the JVM can GC/unload
```

`AtomicReference.set(newProvider)` handles only part of step [5]. It **does not replace** steps [6]–[8]. During step [4], the new provider must not mutate unauthorized production data; warm-up checks must be designed safely.

A `PluginHandle` in a real application typically holds at least the provider, loader, version, lifecycle state, and an in-flight request counter. The registry should point to the **handle**, not solely the provider object, so the system knows which loader must be kept alive and when it can be closed.

Conceptual illustration, **not a standalone program**:

```java
record PluginHandle(
        String version,
        Greeter provider,
        AutoCloseable loader) {}

AtomicReference<PluginHandle> current = ...;

PluginHandle candidate = prepareAndValidateNewPlugin();
PluginHandle old = current.getAndSet(candidate);

// Do not close old.loader() immediately if requests are still holding old.
// Must wait to drain/in-flight requests, release resources, and only then close.
```

The variables and `prepareAndValidateNewPlugin()` function are design notation, not present in the runnable program in Section 6. Using `getAndSet` ensures the handle is swapped atomically at the registry read point, but requests that already read the old handle still hold it. For stronger guarantees, a lease/acquire/release protocol is needed to prevent races between new requests and draining.

### Rollback

If switching to the v2 provider reveals a bug:

- The registry can be switched **back to the v1 provider** as long as the v1 artifact, loader, instance, and resources remain in a usable state.
- Do not assume rollback works merely via `ServiceLoader.reload()`; the cache is not a version history.
- If v1 was already closed or released, a new v1 loader/instance may have to be created; old plugin state may require restoration or reverse migration.
- Rolling back bytecode does not automatically roll back external data changes such as database/schema updates or already-sent messages.

## 12. Constraints when unloading a plugin

Closing a `URLClassLoader` with `close()` **closes resources managed by the loader**, such as the JARs/files it holds, but **does not force the JVM to unload classes immediately** and does not destroy live provider objects.

Class unloading depends on the reachability of the class loader and related references. Common sources keeping a plugin alive include:

- Registries/caches still holding old instances or `Class<?>`.
- In-flight requests or threads created by the plugin still holding objects from the old loader.
- `ThreadLocal`, timers, schedulers, or executors holding callbacks/classes from the plugin.
- Thread context class loader (`Thread.currentThread().getContextClassLoader()`) of a live thread still pointing to the old loader.
- Listeners, MBeans, shutdown hooks, logging/application framework registries, or resource providers registered and not yet removed.
- A `ServiceLoader` retained by the host may still hold provider instances in its cache until reloaded/dereferenced.
- Plugin objects leaked outward through a shared API and kept alive in the host.

Therefore, an explicit `start`/`stop` policy, resource closing, callback/registration removal, cache clearing, and classloader leak checks are required. Weak references can be used in tests to observe reclaimability, but do **not** rely on GC timing as a deterministic deadline.

A class loader only isolates **class namespaces**; it does not sandbox untrusted code by itself, nor does it isolate the process, network access, or filesystem permissions. When plugins are untrusted, stronger isolation measures are necessary.

## 13. Notes when SPI runs on the module path/JPMS

The demo above uses **classpath + `META-INF/services` resources + `URLClassLoader`**. With named modules in the Java Platform Module System, providers are typically declared with `provides ... with ...` in `module-info.java`, while consumers use `uses`. When building a new `ModuleLayer` for a plugin, the module-aware `ServiceLoader.load(layer, ServiceType.class)` API can be used.

The common principles still hold:

- `ServiceLoader` discovers and caches providers; **it does not automatically update bytecode**.
- The host must have a shared API/SPI boundary that plugins can actually use; do not duplicate the service type across class-loading scopes.
- Switching the active provider is a separate routing/lifecycle decision.
- Creating a new `ModuleLayer`/class loader for a new artifact is different from redefining classes in place.
- The old provider does not stop automatically when a new module layer is created.

Do not copy the demo's classpath syntax verbatim onto the module path assuming only `META-INF/services` resources are needed; registration and discovery for named modules must follow JPMS rules.

## 14. Common mistakes and how to diagnose them

| Symptom / misconception | Reality | Remediation |
|---|---|---|
| “`reload()` replaces the plugin JAR” | It only clears the cache of one `ServiceLoader` | Use a new loader/layer if new class definitions are needed |
| “New object after reload means new code too” | The new instance may still belong to the old `Class<?>` | Compare `getClass()` and defining class loader |
| “Calling `reload()` destroys the old provider” | Old references can still remain active | Manage stop/close and object ownership |
| “Updating `AtomicReference` updates every request” | Requests that already read the old reference can continue using the old one | Draining/lease and a handoff plan |
| “Overwriting the JAR file makes the JVM use v2 immediately” | Already-defined classes are not replaced automatically | Versioned artifacts and a new loader, or Instrumentation where supported |
| “Same class name means the same class” | Class identity depends on the defining loader | Print `getClassLoader()` and compare `Class<?>` |
| “Each plugin can bundle its own SPI” | Produces two distinct service types, which may fail to cast | Use the SPI owned by a shared parent/layer |
| “`URLClassLoader.close()` means unload classes” | It closes resources, not forcing immediate GC unload | Clear references, threads, callbacks, and lifecycle |
| “Static counter resets after `reload()`” | Same class preserves static state | Check the loader and static fields |
| “Having `ServiceLoader` automatically supports concurrent reload” | `ServiceLoader` is not guaranteed thread-safe | Do not reload while another thread is iterating |
| “The app has only one provider because it calls `.next()`” | There may be multiple providers or duplicate configs | Check 0/1/n candidates and select by policy |
| “A new loader guarantees no memory leak” | Host/threads can still retain the old loader | Monitor instance lifecycles and references |

### Useful diagnostic checks

When an upgrade does not change behavior as expected, log in a controlled way:

```java
Class<?> type = provider.getClass();
System.out.println("provider id = " + provider.id());
System.out.println("binary name = " + type.getName());
System.out.println("defining loader = " + type.getClassLoader());
```

This is a snippet to place inside a method that has a `provider` variable of type `Greeter`. Logging only the class/loader name is not enough to prove the source artifact; larger systems need additional information about artifact version, checksum, and routing mechanism.

When true comparison is needed, use:

```java
boolean sameObject = oldProvider == newProvider;
boolean sameClass = oldProvider.getClass() == newProvider.getClass();
boolean sameLoader =
        oldProvider.getClass().getClassLoader()
                == newProvider.getClass().getClassLoader();
```

These three values answer three different questions. Remember that two different objects can share the same class; two classes with the same name can have different loaders; and changing a reference alone does not mean bytecode was replaced.

## 15. Practice exercises

1. **Skip `reload()`:** use v1 `ServiceLoader` to iterate twice and compare objects. Predict why both iterations yield `v1#1`.
2. **Cache `reload()` only:** call `servicesV1.reload()` again, print the static instance ordinal, and compare `Class<?>`. Explain why the instance number increments while the class stays identical.
3. **Skip switching active:** create `v2Provider` via `loaderV2` without calling `active.set(v2Provider)`. Why does the host still use the v1 provider?
4. **Early active switch:** simulate request A calling `Greeter old = active.get()` before the registry switch, and request B calling it after the switch. Have both call `greet("Java")` and explain why A still uses the old version.
5. **Break the SPI boundary:** intentionally package `Greeter.class` into each JAR as well and use a child-first strategy for the entire `demo.spi` package. Analyze why the host can hit a “provider not a subtype” or casting error; then restore the shared SPI from the parent.
6. **Wrong JAR replacement:** try loading v1 and then replacing the JAR file at the same URL (in a test environment you can clean up afterwards). Explain why you cannot rely on `reload()` to replace class definitions and why overwriting an open JAR is risky.
7. **Design a rollout:** describe `prepare -> validate -> swap -> drain -> close` and how to roll back if v2 fails after already handling some requests. Why does an atomic pointer solve only part of the problem?
8. **HotSwap vs new loader:** state a scenario suited for Instrumentation and a scenario suited for versioned artifacts with a new class loader; point out the impact on static state and object identity in both strategies.

## 16. Checklist before enabling plugin replacement in production

- **Versioning:** Do artifacts/JARs have clear identifiers, checksums, dependencies, and compatibility protocols?
- **Shared contract:** Do all plugins use the exact single SPI/API type from the parent, with signatures containing no child-loader private classes?
- **Discovery:** Are providers registered properly, is it clear which class loader/layer performs discovery, and are provider count and selection checked?
- **Cache:** Is it clear which `ServiceLoader` is reloaded, are old iterators discarded, and are invalid concurrent operations prevented?
- **Object:** Do you know which object is active, and has the new provider been warmed up and tested before switching?
- **Class:** Is there a new class definition from a new loader/layer when bytecode changes are required, or is it merely creating a new object from the old class?
- **Traffic:** Is there a strategy to handle in-flight requests, synchronize state, and migrate data when needed?
- **Resources:** Are callbacks stopped, listeners removed, files/sockets/executors closed, and the old loader released?
- **Security:** Are plugins trusted, and are resource limits and appropriate permissions in place?
- **Observability:** Can you log provider ID, version, class name, loader identity, swap timestamp, and rollback errors without exposing sensitive information?

**Conclusion:** `ServiceLoader.reload()` only **refreshes the SPI discovery cache**; updating a registry reference only **selects a different object**; loading a different bytecode version usually requires a **new class loader/module layer** or dedicated **Instrumentation**. Regardless of the approach, the host must still manage the lifecycle of the old provider and in-flight requests. That is the boundary separating “refreshing a cache,” “swapping an instance,” and true “new plugin deployment.”