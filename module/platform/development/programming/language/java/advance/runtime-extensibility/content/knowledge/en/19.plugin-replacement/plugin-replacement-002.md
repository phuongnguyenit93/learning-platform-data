# Why Replacing a JAR on Disk Does Not Automatically Change Loaded Class Code

In a Java application that supports installing or upgrading plugins at runtime, a seemingly simple operation is **copying a new-version JAR over the old JAR**. Yet after copying, calls to the running plugin object still execute the old logic. This is correct behavior under the JVM's **class loading and class identity** model, not a data synchronization bug or an OS failure to refresh the file.

**Most important principle:** *A JAR is a bytecode source for a class loader to load from; a `Class` already defined by the JVM is a runtime entity with its own identity and lifecycle. Replacing JAR contents on disk does not automatically redefine the `Class`, update old instances, or cause the JVM to recreate the class loader.*

When upgrading a plugin, three actions must be distinguished:

1. **Artifact replacement**: placing a new JAR on disk.
2. **Loading the new version**: creating an appropriate class loader/layer to define classes from the new JAR.
3. **Switching execution to the new version**: updating the registry, routing new calls, completing or cancelling old calls in a controlled manner, and releasing resources.

Completing only step (1) does **not** automatically complete (2) and (3).

## 1. What happens when Java loads a class from a JAR?

Consider the file `plugins/report.jar` containing the class `com.example.report.ReportPlugin`. When the application needs that class, a class loader locates the bytecode inside the JAR, converts the bytes into a class definition, and the JVM creates a metadata object of type `java.lang.Class`. The class can then be linked, initialized, and executed according to the JVM lifecycle.

```text
On disk: plugins/report.jar (v1 bytecode)
                   |
                   v
       ClassLoader looks up class by name
                   |
                   v
          JVM defines/loads Class
                   |
                   v
  Class<ReportPlugin> is now defined
                   |
                   +--> creates ReportPlugin instance A
                   +--> creates ReportPlugin instance B
                   +--> JIT may optimize execution paths
                   
Later: report.jar is replaced with v2 bytecode
                   |
                   X (no automatic mechanism)
                   |
     Class v1, instances A and B do not turn into v2
```

The JVM has distinct phases: **loading, linking, initialization**. From bytecode inside an artifact, the JVM establishes a class with metadata and a loader relationship. Once defined, that class is **not normally reloaded under the same identity merely because an external file changed**.

Several consequences follow:

- `new ReportPlugin()` using the class already resolved by the loader can continue creating **v1** instances, even if the JAR file at the old path now contains new bytes.
- Existing instances retain their own class; editing the JAR file does not replace the method code of those instances.
- The JIT compiler optimizes code **of the runtime class**; JIT/GC activity does not mean the JVM polls JAR files to refresh bytecode.
- If a class has never been loaded yet, a lookup after the file changes can be affected by caches, the loader, and JAR state. Therefore there is a risk of **mixing versions** between older classes and later-loaded classes; overwriting JARs should not be used as an update strategy.

A deployed JAR should be treated as an **immutable artifact**. Each release should use a versioned path or filename, and let a new loader/layer read that release.

## 2. Class identity consists of the name and the defining class loader

A crucial point in Java is that **two classes with the same binary name can still be two different runtime types**, if they are defined by two different class loaders.

Think of it as:

```text
DefiningLoader#1 + "com.example.Plugin" => Class A (v1)
DefiningLoader#2 + "com.example.Plugin" => Class B (v2)

Class A.getName().equals(Class B.getName())  == true
Class A == Class B                           == false
```

The runtime type identity of a class is determined by **its binary name and its defining class loader**. You cannot rely solely on the class name or JAR filename to conclude that two classes are the same type.

Therefore:

- `Class<?> oldClass` and `Class<?> newClass` can have the same `getName()`, yet `oldClass != newClass`.
- An object created from a class in the old loader does not automatically become an instance of the class in the new loader.
- Attempting to cast an object defined by loader A to a **same-named** type defined by loader B can throw `ClassCastException`.
- Types in the plugin signature must be managed carefully: if a plugin bundles its own copy of the host API interface and its loader redefines that interface, even methods that look identical can be type-incompatible.
- Parent delegation can cause the new class loader to pick up the class from the parent instead of the new JAR, making you think the version switched when it is actually still invoking the old code.

### 2.1. The same loader cannot simply redefine the same name

Under normal class loading, a `ClassLoader` remembers the classes it has loaded/defined. When the same binary name is requested again, `loadClass` typically returns the already-loaded class following delegation rules; it **does not reopen the JAR to replace old bytecode**.

Nor can a class loader define a second class with the same binary name within the same loader namespace via `defineClass` in normal loading; attempting a duplicate definition can cause a `LinkageError`. Thus, “clearing an application cache and calling `loadClass` again” is **not** equivalent to reloading an existing class.

Not everything named “reload” redefines Java classes. You must read the specific contract of the framework/loader to know whether it reloads configuration, a service list, resources, or **actually creates new runtime classes**.

## 3. Runnable Java 17 example: same class name, two JARs, two versions

The example uses **two JARs at different paths** to avoid errors from overwriting an open file on Windows/Linux and to keep results deterministic. It shows that within **the same JVM**, v1 can still execute after v2 has been loaded by another loader.

### 3.1. Prepare two source versions

Project structure:

```text
project/
  v1/
    src/demo/plugin/Greeting.java
  v2/
    src/demo/plugin/Greeting.java
  PluginSwapDemo.java
```

Contents of `v1/src/demo/plugin/Greeting.java`:

```java
package demo.plugin;

public final class Greeting {
    public String say() {
        return "v1";
    }
}
```

Contents of `v2/src/demo/plugin/Greeting.java`:

```java
package demo.plugin;

public final class Greeting {
    public String say() {
        return "v2";
    }
}
```

Both classes have **the same package, name, and public API**. Only the method body differs.

### 3.2. Host program using two URLClassLoaders

File `PluginSwapDemo.java`:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class PluginSwapDemo {

    static String message(Class<?> type) throws Exception {
        Object instance = type.getConstructor().newInstance();
        return (String) type.getMethod("say").invoke(instance);
    }

    public static void main(String[] args) throws Exception {
        URL oldJar = Path.of(args[0])
                .toAbsolutePath().toUri().toURL();
        URL nextJar = Path.of(args[1])
                .toAbsolutePath().toUri().toURL();

        try (URLClassLoader oldLoader = new URLClassLoader(
                    new URL[] {oldJar},
                    ClassLoader.getPlatformClassLoader());
             URLClassLoader newLoader = new URLClassLoader(
                    new URL[] {nextJar},
                    ClassLoader.getPlatformClassLoader())) {

            Class<?> oldClass = Class.forName(
                    "demo.plugin.Greeting", true, oldLoader);
            Class<?> newClass = Class.forName(
                    "demo.plugin.Greeting", true, newLoader);

            System.out.println("old=" + message(oldClass));
            System.out.println("new=" + message(newClass));
            System.out.println("sameName="
                    + oldClass.getName().equals(newClass.getName()));
            System.out.println("sameClass=" + (oldClass == newClass));
            System.out.println("sameLoader="
                    + (oldClass.getClassLoader()
                       == newClass.getClassLoader()));
            System.out.println("oldStill=" + message(oldClass));
        }
    }
}
```

**Why is the parent the platform class loader?** Since `Greeting` uses only JDK APIs, we can pick `ClassLoader.getPlatformClassLoader()` to avoid accidentally picking up a same-named `demo.plugin.Greeting` from the application classpath. **This is only how the demo is organized.** In a real plugin architecture, the parent typically needs to share **the host's stable API interfaces** and shared dependencies; choosing the wrong parent will prevent plugins from loading API classes or create mismatched type identities.

### 3.3. Compile, package JARs, and run

From the `project` directory, with JDK 17+:

```bash
javac -d v1/classes v1/src/demo/plugin/Greeting.java
javac -d v2/classes v2/src/demo/plugin/Greeting.java

jar --create --file v1.jar -C v1/classes .
jar --create --file v2.jar -C v2/classes .

javac PluginSwapDemo.java
java PluginSwapDemo v1.jar v2.jar
```

The `javac` and `jar` commands have the same syntax in PowerShell/CMD and bash when run from a project directory with the structure above. The commands use paths without OS-specific classpath separators.

Verified stdout when running the program:

```text
old=v1
new=v2
sameName=true
sameClass=false
sameLoader=false
oldStill=v1
```

**Explanation of each result:**

- `old=v1`: the class defined by `oldLoader` reads bytecode from `v1.jar`.
- `new=v2`: the class defined by `newLoader` reads bytecode from `v2.jar`.
- `sameName=true`: both classes are named `demo.plugin.Greeting`.
- `sameClass=false` and `sameLoader=false`: the JVM treats them as two different types because their defining loaders differ.
- `oldStill=v1`: after the v2 class appears in the JVM, **the old class is not rewritten**; calls through `oldClass` still execute v1.

This example demonstrates **loading two versions** safely and deterministically, without deleting or overwriting an in-use JAR. Nor does it automatically route real application requests from v1 to v2: routing switches must be programmed separately.

## 4. Why overwriting the same JAR path can produce unpredictable results

Suppose the application is using:

```text
plugins/analytics.jar   -> already loaded from v1
```

Then a deployment overwrites it:

```text
plugins/analytics.jar   -> v2 file contents
```

There will be independent factors:

| Component | After overwriting the file | Conclusion |
|---|---|---|
| Already-defined v1 `Class` | Remains the v1 runtime type object | Does not automatically change to v2 |
| v1 instance held in registry | Still references old class/loader | Subsequent calls can still run v1 |
| JIT-optimized method | Based on the defined runtime class | Not a polling mechanism for JARs on disk |
| Class not yet loaded by old loader | Can be affected by caches, JAR handles, new file contents, or I/O errors | Cannot be relied upon as a hot-reload guarantee |
| `URLClassLoader` holding the JAR | May hold handles/caches to the old JAR depending on environment | Overwriting can be blocked or cause inconsistent state |
| `getResource(...)` / resource stream | How URLs/caches/resources are opened may differ from class loading | Does not prove old class bytecode changed |
| New class loader pointing to new JAR | Can define new classes from v2 when configured properly | Still requires version-switching routing |

### 4.1. A stable path does not mean updated bytecode

`ClassLoader` and `URLClassLoader` are not file watchers. They **do not automatically register** to monitor file modification times, purge `Class` objects, or re-call `defineClass` for already-loaded types. A path such as `plugins/current.jar` might switch symlink targets or change bytes, yet an already-loaded `Class` remains the class defined earlier.

Within a JVM, **an artifact's file location and class identity are not the same thing**. OS file caching or URL/JAR caching can make reading a new resource behave unexpectedly; it does not alter the rules of class identity.

### 4.2. The “half-old, half-new” hazard

Do not actively replace JAR bytes in place while the JVM is running:

- Class A was loaded before the change and continues running v1.
- Class B was never loaded; a load after the change might open the replaced file, use an old cache, or fail.
- If A and B have different ABIs/constants, `NoSuchMethodError`, `NoSuchFieldError`, `LinkageError`, `ClassNotFoundException`, or other inconsistent behaviors can occur.
- A new configuration resource might be incompatible with v1 code, causing failures that operators assume mean “the plugin just upgraded.”
- On Windows, an open file may fail to be overwritten/deleted; on other systems, rename/replace and open handles also have their own semantics.

**Solution:** create files with distinct versions/content hashes (`plugin-1.4.0.jar`, `plugin-1.5.0.jar`), verify integrity, and point a **new loader** to the new artifact path. Keep the old artifact until no request or old loader needs it.

## 5. Why merely calling reload or a partial restart is not enough

Several APIs have names resembling reload but have different scopes.

### 5.1. `ServiceLoader.reload()`

`java.util.ServiceLoader` finds providers published by JARs/modules via Java's service mechanism. `ServiceLoader.reload()` **clears the provider cache** of that specific `ServiceLoader` object so subsequent iterations can discover/re-instantiate providers under the current lookup.

It does **not** automatically:

- Add a new JAR URL to an existing `URLClassLoader`.
- Redefine classes already loaded by the old loader.
- Replace v1 provider objects that the application previously stored in registries/fields.
- Guarantee that classes in an overwritten JAR will be loaded from v2.
- Manage lifecycle, drain old requests, or release resources for you.

A new provider obtained through a `ServiceLoader` can still belong to **the same old `Class`** if the loader in use has already loaded that type.

### 5.2. Closing `URLClassLoader`

`URLClassLoader` implements `Closeable`; loaders should be closed when loading resources from their JARs is no longer needed. However:

```java
try (URLClassLoader loader =
        new URLClassLoader(jarUrls, parentLoader)) {
    // load classes, create providers, use within a controlled lifecycle
}
```

The above is **illustrative code inside a method**; `jarUrls` and `parentLoader` must be initialized, along with importing `java.net.URLClassLoader`.

`close()` closes resources opened by the loader per the `URLClassLoader` contract and restricts loading further new classes/resources from the loader. It **does not remove already-defined `Class` objects from the JVM**, does not destroy instances, does not stop threads started by the plugin, and does not guarantee GC will unload classes immediately. Loaded classes can still be called while references remain.

In the Section 3 example, both loaders are closed upon exiting `try`; prior to that, v1 and v2 classes coexisted. **Closing a loader is not a “class upgrade” operation.**

### 5.3. JPMS and `ModuleLayer`

For plugins deployed as named modules, `ModuleLayer` represents the group of defined modules. Replacing JARs visible to a finder on disk **does not mutate modules already defined in an existing layer**. Typically, you must create a **new `ModuleFinder` and `Configuration`**, resolve from appropriate roots, and define a **new layer** to load the new module version.

Like a class loader, a module layer is not a “live file list” that updates itself. When replacing plugin modules, you must account for shared API modules in parent layers, the dependency graph, module readability, and references retaining the old layer.

### 5.4. `Class.forName(...)` or “clear cache”

`Class.forName(name, true, oldLoader)` does not mean “fetch the latest version on disk.” It asks the loader to locate the class with that name, and the loader can return the already-loaded class. Nor does `Class.forName` **mean creating a new instance**. Likewise, clearing an application-built map cache does not force the JVM to forget class metadata.

To obtain a new class under normal loading mechanisms, you need a **different defining loader** or the specialized bytecode intervention described later.

## 6. How to upgrade plugins safely with a new loader

A controlled update workflow is not just “copy JAR, call reload.” It manages versions, permissions, references, and in-flight requests.

```text
             plugin v1 currently active
                     |
           [1] Stage new v2 artifact
                     |
           [2] Verify hash/signature,
              API and dependencies
                     |
           [3] Create v2 loader/layer
                     |
           [4] Initialize + self-test,
              health check + warm-up
                     |
           [5] Publish v2 snapshot
                atomically
                 /                 \
          new requests         old requests
           -> v2                -> v1 until done
                 \                 /
                  [6] Drain v1
                       |
             [7] Deregister/stop
                 threads, listeners,
                 callbacks, and resources
                       |
             [8] Close v1 loader,
                 drop references
                       |
             [9] GC may unload
                 when eligible
```

### 6.1. Detailed operational steps

1. **Stage immutable artifact.** Store `plugin-2.0.0.jar` (or a hash-addressed path) separately from `plugin-1.0.0.jar`; never write over the copy serving requests. Verify signatures/hashes from a trusted deployment source.
2. **Verify metadata.** Check plugin ID, version, min/max host API version, dependencies, requested plugin permissions, and package/module lists; reject invalid releases.
3. **Create new loader/layer.** Use the new JAR and a parent loader containing **the stable shared SPI/API**, preventing the plugin from redefining host API interfaces.
4. **Trial initialization.** Create a new instance, run readiness and dependency checks. If it fails, discard the candidate and keep v1 serving normally.
5. **Manage state.** Define which state can be transferred, whether schemas/configs need migration, which transactions are in progress, and backward compatibility. Never cast a v1 object to a v2 class.
6. **Atomic route switch.** Swap the registry/holder reference used for **new requests** from v1 to v2 using proper synchronization/atomic primitives; do not rewrite bytecode inside old classes.
7. **Drain requests using v1.** Apply safe timeout/cancellation policies, especially for side-effecting operations; in-flight requests can complete on the v1 snapshot.
8. **Teardown v1.** Stop schedulers/threads, deregister listeners, MBeans, callbacks, and services, close streams/sockets, clear caches/ThreadLocals, and close the loader according to lifecycle.
9. **Roll back if needed.** You can switch the registry back to a still-alive v1 instance if it has not been drained/stopped and data migrations are compatible; if the schema changed, rollback must be planned separately.
10. **Collect old artifacts when safe.** Delete the v1 file only after no loader/request needs it and operations no longer need to retain it for rollback.

### 6.2. Boundary between host API and plugin implementation

A common architecture:

```text
Application / parent class loader
  com.example.plugin.api.Plugin    <-- shared contract
                  |
           PluginRegistry
            /          \
       PluginV1       PluginV2
       loader v1      loader v2
       impl JAR v1    impl JAR v2
```

`Plugin` is an interface managed by the host or a stable API artifact, loaded once from the **parent loader**. Different plugin implementation versions are defined by **child loaders**; implementations can implement the same shared interface.

With standard `URLClassLoader`, delegation is normally parent-first. Therefore:

- Do not allow implementation class names to collide with classes already loaded by the parent.
- Do not bundle duplicate API/SPI copies in plugin JARs in a way that causes multiple API versions to be defined by different loaders.
- Lock down host API compatibility (method signatures, DTO data, exception contracts); versioning the JAR filename alone does not fix binary compatibility errors.
- Check plugin-provided dependencies and shared dependencies. Two plugins can use different library versions if loader isolation is sound; native libraries or global state cannot always be isolated.
- Use interfaces/DTOs as the boundary; do not pass raw plugin implementation classes back to the host for long-term retention if you want to unload older versions.

### 6.3. Atomic switch does not mean immediate unload

The registry can store a `PluginHandle` object containing the version, provider instance, loader, lifecycle status, and number of requests holding the snapshot. When swapping versions, the host atomically publishes the v2 handle, while keeping the v1 handle until in-flight calls complete.

Illustrative code sketch (not a standalone program):

```java
AtomicReference<PluginHandle> active =
        new AtomicReference<>(handleV1);

// After handleV2 has been validated and initialized successfully:
PluginHandle previous = active.getAndSet(handleV2);

// Requests still holding handleV1 may still need to complete.
// previous is closed only after safe draining.
```

For real use, the types `PluginHandle`, `handleV1`, `handleV2`, and `import java.util.concurrent.atomic.AtomicReference` are required; `AtomicReference` **only guarantees an atomic reference swap**, and does not by itself solve draining, transactions, quotas, lifecycle, or rollback.

If a request reads `active.get()` and calls the plugin while the system immediately closes the old loader, a race still exists. A lease/reference counting contract, read/write coordination, or appropriate stable snapshot mechanism is required. Interrupting an operation producing side effects is not solved by a simple reference swap.

## 7. When can old classes actually be unloaded?

The JVM performs **class unloading** when eligible classes and their defining class loader become unneeded and GC decides to collect them; timing is not guaranteed. Calling `System.gc()` is not an unloading contract.

References that commonly keep old plugins alive unintentionally:

| Reference source | Consequence |
|---|---|
| Registry/singleton still holding v1 provider | Retains v1 instance, class, and loader |
| Cached `Class<?>` / `Method` / `Constructor` | Retains metadata tied to old classes |
| Unstopped plugin thread or thread context class loader pointing to v1 | Loader can continue to be kept alive |
| `ThreadLocal` on a thread pool still holding plugin values | Retains plugin objects and old loader across requests |
| Listeners/event bus/schedulers/MBeans still registered | v1 callbacks and target instances remain alive |
| `ServiceLoader`, reflection caches, or framework containers | May retain old providers/classes/loaders |
| Running tasks, unclosed streams/sockets or resources | Retains lifecycle and associated file handles |
| Static fields inside v1 classes | May retain more objects/threads; if the class stays reachable, complicates cleanup |

A good plugin manager provides `start`/`stop`/`close`, registers all resources by lifecycle, and tracks metrics per version. On stop, actively clear host references, deregister callbacks, clean TCCL/ThreadLocals where appropriate, and shut down executors. **Closing `URLClassLoader` helps release resources, but does not guarantee class unloading.**

If repeated plugin replacements steadily increase Metaspace or thread counts, inspect leaks from registries, threads, event listeners, and class loader reachability—not just JAR sizes.

## 8. Exception: Instrumentation can redefine bytecode

Java also has a specialized mechanism, `java.lang.instrument.Instrumentation`, typically supplied via a **Java agent**, allowing `redefineClasses(...)` or `retransformClasses(...)` on JVMs supporting the corresponding features.

This introduces important differences:

- **Overwriting a JAR does not invoke instrumentation APIs.** The JVM does not automatically replace class definitions merely because bytes in a file changed.
- With supporting instrumentation APIs, an agent can supply **new bytecode for an existing class** at runtime, subject to JVM/agent limitations and capabilities.
- `redefineClasses` has restrictions on changing class structure (e.g., it cannot arbitrarily add/remove fields or methods or change hierarchy/signatures in standard HotSwap). This is not an arbitrary full-plugin JAR hot swap.
- **Already-executing** method invocations may continue running the old bytecode on the stack, while subsequent calls use the updated definition per JVM mechanics. Do not assume an automatic global pause across all logic.
- State, static fields, object instances, resources, and dependency graphs are not automatically migrated. New method bodies may be incompatible with old state.
- Not every JVM supports every form of redefine/retransform; check capabilities such as `isRedefineClassesSupported()` and `isRetransformClassesSupported()`.

**When to use it?** Agent/hot code replace can be useful for debuggers, profilers, instrumentation, or controlled method body changes. For **plugin upgrades involving API, field, dependency, or lifecycle changes**, creating **a new class loader/layer and switching** is usually clearer and more appropriate. Do not promise that “enabling HotSwap” is enough to apply arbitrary new JARs in production.

## 9. Testing plugin replacement scenarios

Tests should distinguish bytecode on disk, defined classes, loaders, instances, and the registry:

| Scenario | Expectation |
|---|---|
| Host holds `Greeting` v1; JAR file is replaced | v1 `Class`/instance does not automatically become v2 |
| Call `Class.forName(..., oldLoader)` after replacing file | Not guaranteed to create v2 class; usually gets v1 class already loaded by the loader |
| Create new loader pointing to `v2.jar` | Can create v2 `Class` if delegation does not pick the old class |
| Same v1/v2 class name, different loaders | `getName()` matches, `Class<?>` differs |
| Cast v1 implementation object to same-named v2 implementation | Can throw `ClassCastException` when using v2 type |
| Host and child both have SPI copies with different defining loaders | API cast can fail despite identical interface name |
| `ServiceLoader.reload()` on old loader | Does not guarantee already-loaded provider bytecode changes |
| `URLClassLoader.close()` | Does not remove loaded classes or terminate all threads |
| New plugin fails health check | Does not switch active registry; v1 keeps serving |
| In-flight request using v1 during route switch | Continues on v1 snapshot; does not jump mid-flight to v2 |
| v1 plugin still has registered listeners/threads | Risk of leaks or v1 callbacks continuing to execute |
| v1 loader/layer has no remaining references | GC **may** unload it, with no hard deadline |
| Overwriting an open JAR on Windows | Can be locked; therefore use versioned artifacts |
| Resource reads v2 while code stays v1 | This does not prove class reload; diagnose separately |
| Plugin JAR had not been loaded before file change | Do not assume safety/consistency; depends on loader/caches |
| Proper JVM agent redefinition | Behavior only within instrumentation support; does not migrate state automatically |

### 9.1. Minimum logs needed for diagnosis

When users report “replaced the JAR yet old code runs,” logs should include:

```text
plugin.id=report
plugin.version=2.0.0
artifact.sha256=<calculated-hash>
artifact.path=<approved-immutable-path>
class.name=com.example.report.ReportPlugin
class.loader.id=plugin-loader-v2
active.handle.version=2.0.0
inflight.v1=3
```

These are **example field names**, not program stdout. `artifact.sha256` must be computed from the actual artifact; do not trust a version label or a `current.jar` path alone. A loader identifier can be assigned by the registry for debugging; do not use a loader's `toString()` as an authorization mechanism.

If the active handle still points to v1 even though the artifact path updated to v2, the bug is **failing to switch the registry/snapshot**, not the JVM failing to read the new file. If switched to v2 yet logs still invoke the v1 class, check **parent delegation**, instance/callback caches, class identity, and resource paths.

## 10. Misconceptions to avoid

1. **“The JVM always reads the JAR file from disk on every method call.”** False: method calls execute code of already-defined classes; a JAR is a loading source, not a script re-read on every call.
2. **“Overwriting the JAR takes effect immediately.”** False: there is no default file watcher/hot reload.
3. **“If class names match, two objects can be cast between each other.”** False: class identity includes the defining loader.
4. **“Placing a new JAR in the same folder and calling `Class.forName` will reload it.”** Not if the old class was already resolved by that loader; a new class loader and new routing are the primary steps.
5. **“`ServiceLoader.reload()` solves everything.”** False: it only resets the provider cache of that `ServiceLoader`, without updating classes or application registries.
6. **“Calling `close()` on `URLClassLoader` destroys all plugin objects.”** False: old objects/classes live on according to references and GC.
7. **“Calling GC definitely frees the class loader.”** False: there is no timing guarantee, especially if references remain in threads/listeners/singletons.
8. **“Using one loader for all versions is the most economical.”** Easily causes name conflicts and prevents replacing classes; sensible loader boundaries are required.
9. **“Two loaders always isolate plugins completely.”** False: in the same JVM they still share the process, native state, OS permissions, and global services; a class loader is not a sandbox.
10. **“Once v2 is loaded, all requests immediately use v2.”** False: routing/registries, active objects, and in-flight requests have independent lifecycles.
11. **“Instrumentation can change any class structure.”** False: redefinition has restrictions, state does not migrate automatically, and support depends on the JVM.
12. **“Replacing a JAR in place only suffers from Windows file locks.”** False: there are also risks of mixing classes/resources, caching, races, and lacking rollback across platforms.
13. **“Deleting the old JAR right after switching is enough cleanup.”** False: old requests, class loader/resource handles, and rollback capability still remain.
14. **“Changing a resource path means the code upgraded.”** False: resource lookup and class definition are two different mechanisms.

## 11. Checklist for an upgradeable plugin manager

Before switching versions, confirm:

- There is an **immutable v2 artifact** whose origin, checksum/signature, and API version have been verified.
- There is a **new class loader/module layer** with correct parent API and dependency policies.
- There is a check that `v2` truly runs from the v2 loader/layer, without the parent mistakenly serving the v1 class.
- There is a way to instantiate candidates, run health checks, and reject faulty versions without affecting active v1.
- There is a holder/snapshot to **switch atomically** and manage in-flight calls safely.
- There is a plan for **state migration**, idempotency, database/schema compatibility, and rollback.
- There is lifecycle stop/close handling for executors, listeners, caches, ThreadLocals, streams, sockets, and class loaders.
- There are logs/metrics by plugin ID, version, artifact hash, defining loader, active handle, and inflight count.
- There is testing on both Windows and the actual deployment OS, covering JAR/module paths and classloader delegation.
- Security boundaries are respected: untrusted plugins are **not** considered safe merely because they run in a separate class loader.

**Conclusion:** replacing a JAR **only replaces the artifact**, and does not automatically replace JVM-defined `Class` objects or live instances. To upgrade plugins at runtime under standard Java mechanisms, **produce a new versioned artifact, load it with a new loader/layer, switch the registry to the new instance, and drain and release the old version**. That workflow cleanly separates file replacement, runtime type replacement, and request-serving switches, making the application testable, rollback-capable, and free of mixed versions.

### Reference APIs (Java SE 17)

- [ClassLoader — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [URLClassLoader — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html)
- [ServiceLoader — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
- [Instrumentation — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [ModuleLayer — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html)