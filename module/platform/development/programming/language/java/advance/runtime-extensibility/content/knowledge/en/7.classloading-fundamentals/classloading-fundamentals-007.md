# Roles of findClass, defineClass, and Constraints When Writing a Custom ClassLoader in Java

## 1. The Problem: Why Understand These Two Methods?

In Java, a class is not just a `.class` file on disk. The JVM must locate the bytecode, convert that bytecode into a `Class<?>` object, link the types the bytecode references, and manage class identity throughout execution. `java.lang.ClassLoader` provides the interface allowing a runtime to decide where to fetch bytecode from: a custom directory, a plugin JAR, memory, an internal store, or another source.

When writing a custom class loader, two methods frequently appear side by side yet **do not do the same job**:

- **`findClass(String name)`:** the extension point to *locate and create* a class when the default loading path has not found it. It typically reads bytecode from a source managed by the loader and calls `defineClass`. It does not provide parent delegation on its own if called directly.
- **`defineClass(String name, byte[] bytes, int offset, int length)`:** a `protected final` method on `ClassLoader` that asks the JVM to define a class from bytecode; it does not search files, decide parent vs. child precedence, and cannot be overridden.
- **`loadClass(String name)` / `loadClass(String name, boolean resolve)`:** the class-loading entry point using the default mechanism: check already-loaded classes, try the parent, and only then call `findClass`. This is where *delegation*, loading synchronization, and optional resolution happen.

In an extensibility architecture, a common mistake is thinking "just override `findClass` to load all classes from the plugin." In reality, the parent may have already loaded the class first, and the JVM enforces rules on identity, duplicate definitions, packages, signatures, linking, and concurrency.

**Learning objective:** understand the loading flow accurately, write a small safe parent-first loader, predict class identity, distinguish class-lookup errors from definition errors, and recognize what else must be handled when moving from a learning example to a plugin runtime.

## 2. Default Flow: loadClass → findClass → defineClass

For a class with binary name `demo.plugin.HelloGreeter`, the default `ClassLoader.loadClass(name, resolve)` contract follows this sequence:

```text
caller: loader.loadClass("demo.plugin.HelloGreeter")
                  |
                  v
    lock = getClassLoadingLock(name)
                  |
                  v
       findLoadedClass(name)
          | already loaded? -> return existing Class
          v not yet
       try parent.loadClass(name)
          | found? -> return Class defined by parent/ancestor
          v not found
       this.findClass(name)           <--- common override point
          |
          v
       fetch byte[] from own source
          |
          v
       this.defineClass(name, bytes, 0, bytes.length)
          |
          v
       Class<?> defined by this loader
          |
          v
       if resolve == true: resolveClass(result)
          |
          v
       return Class<?>
```

The actual branches of default `loadClass`:

1. `findLoadedClass(name)` checks whether this loader has already been recorded by the JVM as an *initiating loader* of the class with that name. This check avoids recreating the same class during normal loading; a class returned from the parent can also be recorded for the initiating loader.
2. The parent loader is tried first. If the parent cannot find it, the method proceeds to `findClass(name)` on the child. When parent is `null`, the JVM uses the corresponding bootstrap loading mechanism, though you should not assume `null` exposes all platform classes.
3. `findClass` is where custom bytecode is located and **usually** calls `defineClass`; that is our implementation choice, not something `findClass` performs automatically.
4. If `resolve=true` is requested, `resolveClass` performs linking. **Resolution differs from initialization**: static class initializers do not necessarily run just from calling `loadClass`.
5. If the class cannot be found, `ClassNotFoundException` is thrown. If bytecode is present yet invalid or unlinkable, other errors under `LinkageError` can arise and must not all be turned into "not found."

The steps above describe the **default implementation** in Java 17. Other runtimes or loaders can override `loadClass` and alter the policy, in which case the author must personally ensure synchronization, recursion safety, parent/child contracts, and type compatibility.

## 3. Which API Is Responsible for What?

| Component | Role | Key points to remember |
|---|---|---|
| `loadClass(String)` | Public call site, loads per the loader's logic | Equivalent to calling overload `loadClass(name, false)` |
| `loadClass(String, boolean)` | Default loading cycle, delegation, locking, optional resolution | Can be overridden, though mistakes easily cause deadlocks/duplicate classes |
| `findLoadedClass(String)` | Queries the JVM for a class already recorded for this loader | `protected final`; not a "scan files on disk" operation |
| `findClass(String)` | Hook to locate bytecode/class outside parent | Default throws `ClassNotFoundException` |
| `defineClass(String, byte[], int, int)` | Turns bytecode into a class definition bound to this loader | `protected final`, validates name/bytecode and enforces JVM constraints |
| `resolveClass(Class<?>)` | Links the specified class | Not the same as running constructors or static initializers |
| `getClassLoadingLock(String)` | Supplies the lock for loading a class name | Default uses the loader itself or a per-name lock if parallel-capable |
| `findResource`/`findResources` | Hooks to locate resources for this loader | Completely separate from `findClass`; needed for SPI configs/plugin resources |

Names passed to loading methods are **binary names**, e.g. `demo.plugin.HelloGreeter` or `demo.plugin.Outer$Inner`. The corresponding file path may be `demo/plugin/HelloGreeter.class`, yet that path string must **not** be passed as the class name to `defineClass`.

When writing a loader, **usually override only `findClass(String)`** and inherit `loadClass`. This is the approach recommended by Javadoc for loaders following parent delegation.

## 4. Class Identity Rule: Same Name Does Not Guarantee Same Class

The JVM distinguishes classes by **binary name + defining loader**. Therefore:

- Child loader A defines `demo.plugin.HelloGreeter` and child loader B also defines `demo.plugin.HelloGreeter` from the same bytecode: the two `Class<?>` objects are **different**.
- A class defined by the parent, when loaded by a child via parent delegation, still has `getClassLoader()` pointing to **the parent's defining loader**, not the child that received the request.
- A shared interface, such as `demo.api.Greeter`, must be referenced by both host and plugin using **the same definition**. If a plugin defines its own copy of the interface in another loader, casting to the host's interface can fail despite identical package/class names.
- Two classes with the same package name defined by two different loaders do not automatically belong to the same *runtime package*. Package-private access is not granted solely by matching package name strings.

The **initiating loader** is the loader recorded by the JVM when loading/referencing a class; the **defining loader** is the loader that actually invoked `defineClass` to define that class. Under parent-first, the two roles can differ. `clazz.getClassLoader()` reports the defining loader (`null` for bootstrap-defined classes), not necessarily the loader on which the application called `loadClass`.

When classes across different loaders interact through method/field signatures, the JVM also enforces **loading constraints** so shared type references do not disagree. Violations can surface as `LinkageError` rather than an ordinary cast error. A useful design rule is to keep shared APIs/SPIs in a parent loader, plugins in child loaders, and avoid bundling incompatible API copies inside individual plugins.

## 5. Standalone Runnable Java 17+ Example: DirectoryPluginLoader

The following example creates an SPI in the host, a provider in a separate plugin directory, and a `ClassLoader` that loads bytecode from a directory. The result shows `findClass` defines the implementation only when the parent cannot see it; the interface is shared through the parent.

**Intentional limits of the example:** loads only `.class` files from a trusted directory under package `demo.plugin`, without supporting JARs, manifests, signatures, resources, hot reload, module layers, or sandboxing. For plugins packaged as standard JARs, `URLClassLoader` is usually more convenient and complete than a hand-written loader.

### 5.1. File Structure

Create working directory `loader-demo/` with:

```text
loader-demo/
  src/
    api/demo/api/Greeter.java
    plugin/demo/plugin/HelloGreeter.java
    host/demo/app/LoaderWalkthrough.java
  build/                            (created during compilation)
    api/
    plugin/
    host/
```

**File `src/api/demo/api/Greeter.java`:**

```java
package demo.api;

public interface Greeter {
    String greet(String name);
}
```

**File `src/plugin/demo/plugin/HelloGreeter.java`:**

```java
package demo.plugin;

import demo.api.Greeter;

public final class HelloGreeter implements Greeter {
    public HelloGreeter() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

**File `src/host/demo/app/LoaderWalkthrough.java`:**

```java
package demo.app;

import demo.api.Greeter;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class LoaderWalkthrough {
    private static final class DirectoryPluginLoader extends ClassLoader {
        private final Path root;

        DirectoryPluginLoader(Path directory, ClassLoader parent) {
            super(parent);
            this.root = directory.toAbsolutePath().normalize();
        }

        @Override
        protected Class<?> findClass(String name) throws ClassNotFoundException {
            // Host/API and JDK continue through parent-first loadClass.
            if (!name.startsWith("demo.plugin.")) {
                throw new ClassNotFoundException(name);
            }

            Path classFile = root.resolve(
                    name.replace('.', '/') + ".class").normalize();

            // Keep reads confined within the demo root.
            if (!classFile.startsWith(root)) {
                throw new ClassNotFoundException(name);
            }

            try {
                byte[] bytecode = Files.readAllBytes(classFile);
                return defineClass(name, bytecode, 0, bytecode.length);
            } catch (IOException cause) {
                throw new ClassNotFoundException(
                        "Unable to read class: " + name, cause);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path pluginDirectory = Path.of("build/plugin");
        ClassLoader sharedApiLoader = Greeter.class.getClassLoader();

        DirectoryPluginLoader first =
                new DirectoryPluginLoader(pluginDirectory, sharedApiLoader);
        DirectoryPluginLoader second =
                new DirectoryPluginLoader(pluginDirectory, sharedApiLoader);

        Class<?> one = first.loadClass("demo.plugin.HelloGreeter");
        Class<?> oneAgain = first.loadClass("demo.plugin.HelloGreeter");
        Class<?> two = second.loadClass("demo.plugin.HelloGreeter");

        Greeter provider = one.asSubclass(Greeter.class)
                .getDeclaredConstructor()
                .newInstance();

        System.out.println("providerByFirst=" +
                (one.getClassLoader() == first));
        System.out.println("sameWithinFirst=" + (one == oneAgain));
        System.out.println("sameNameAcrossLoaders=" +
                one.getName().equals(two.getName()));
        System.out.println("sameClassAcrossLoaders=" + (one == two));
        System.out.println("sharedApi=" +
                (Greeter.class.isAssignableFrom(one)
                && Greeter.class.isAssignableFrom(two)));
        System.out.println("bootstrapString=" +
                (first.loadClass("java.lang.String").getClassLoader() == null));
        System.out.println("greeting=" + provider.greet("Java"));

        try {
            first.loadClass("demo.plugin.NotThere");
        } catch (ClassNotFoundException expected) {
            System.out.println("missing=ClassNotFoundException");
        }
    }
}
```

**Implementation explanation:**

1. `DirectoryPluginLoader` overrides only `findClass`. Inherited `loadClass` handles locking, checking cached classes, and querying the parent first.
2. `super(parent)` receives the loader that loaded `Greeter.class`, so both host and implementation share the SPI. Avoid `super(null)` in this example.
3. `name.startsWith("demo.plugin.")` scopes the classes for the plugin. If the parent already defines the same name, parent-first still favors the parent: a prefix check in `findClass` **does not by itself make the loader child-first**.
4. `root.resolve(name.replace('.', '/') + ".class")` maps a binary name to a path. `normalize` and `startsWith(root)` are simple boundary checks; they do **not** yet handle symlinks, file-swap races, or all risks from untrusted content.
5. `Files.readAllBytes` reads the class file contents. If unreadable, the method throws `ClassNotFoundException` preserving the `IOException` cause. When `defineClass` detects malformed bytecode, the linkage error is not hidden as "not found."
6. `defineClass(name, bytecode, 0, bytecode.length)` is where the JVM defines the class belonging to `first` or `second`. It can define the same binary name **in two different loaders**, yet cannot define it twice in the same loader.
7. `asSubclass(Greeter.class)` checks type compatibility when obtaining the implementation. The plugin's public no-arg constructor is called via reflection.

### 5.2. Compiling and Running on Windows PowerShell

From `loader-demo/` using JDK 17 or later:

```powershell
New-Item -ItemType Directory -Force -Path build/api,build/plugin,build/host | Out-Null
javac -d build/api src/api/demo/api/Greeter.java
javac -cp build/api -d build/plugin src/plugin/demo/plugin/HelloGreeter.java
javac -cp build/api -d build/host src/host/demo/app/LoaderWalkthrough.java
java -cp "build/api;build/host" demo.app.LoaderWalkthrough
```

### 5.3. Compiling and Running on Linux/macOS

```bash
mkdir -p build/api build/plugin build/host
javac -d build/api src/api/demo/api/Greeter.java
javac -cp build/api -d build/plugin src/plugin/demo/plugin/HelloGreeter.java
javac -cp build/api -d build/host src/host/demo/app/LoaderWalkthrough.java
java -cp "build/api:build/host" demo.app.LoaderWalkthrough
```

**Important:** at runtime, the classpath contains **only** `build/api` and `build/host`. If you add `build/plugin` to the `java -cp` command, the parent application loader may find `HelloGreeter` first, preventing the example from demonstrating the defining-loader boundary properly.

### 5.4. Exact Stdout

```text
providerByFirst=true
sameWithinFirst=true
sameNameAcrossLoaders=true
sameClassAcrossLoaders=false
sharedApi=true
bootstrapString=true
greeting=Hello, Java
missing=ClassNotFoundException
```

**How to read the output:**

- `providerByFirst=true`: the implementation class was genuinely defined by `first` because the parent lacks `demo.plugin.HelloGreeter`.
- `sameWithinFirst=true`: calling `loadClass` a second time on `first` returns the same `Class<?>`; inherited `loadClass` reuses the already-loaded class instead of defining it twice.
- `sameNameAcrossLoaders=true` yet `sameClassAcrossLoaders=false`: identical names and bytecode are not enough to produce the same runtime class when defining loaders differ.
- `sharedApi=true`: both implementation classes implement the `Greeter` copy supplied by the parent. Hence the host can use the shared interface.
- `bootstrapString=true`: `java.lang.String` was defined by the bootstrap loader (`getClassLoader() == null`); the child delegated rather than trying to define core classes itself.
- `greeting=Hello, Java`: instantiating and calling the method on the provider succeeded.
- `missing=ClassNotFoundException`: the implementation file is missing so `findClass` reports not found; this is distinct from a bytecode file existing yet being invalid.

The example runs sequentially and does not modify plugin files mid-load. It does not prove compatibility with hosts using a `SecurityManager`, the module system, `ModuleLayer` configurations, or externally mutated classpaths.

## 6. Constraints of defineClass: Having Bytecode Does Not Mean It Can Always Be Loaded

`defineClass` is a JVM-controlled API. Its method name sounds like "create any class at will," yet Java bytecode and the runtime must still obey language and VM rules.

### 6.1. Class Names, Bytecode Data, and JDK Versions

- Use an overload that takes a name: `defineClass(name, bytes, offset, length)` or the overload taking `ProtectionDomain`; the overload taking only `byte[]` without a name has been deprecated.
- `name` is the expected binary name, e.g. `demo.plugin.HelloGreeter`, and must match the name inside the class file. On mismatch, the error is normally `NoClassDefFoundError` mentioning *wrong name*.
- `offset` and `length` must stay within array bounds; out-of-range values cause `IndexOutOfBoundsException`.
- Bytecode must have a valid `.class` structure. Corrupted bytecode can throw `ClassFormatError`, bytecode compiled for a newer JVM can throw `UnsupportedClassVersionError`, and bytecode failing verification can throw `VerifyError`.
- Bytecode holds references to dependencies; a successful `defineClass` **does not guarantee** all dependencies will link or all code can execute. Linking/initialization errors can appear later when the JVM needs a referenced type or member.
- Distinguish **load**, **link** (verify, prepare, and resolve which may occur on demand), and **initialize** (running static initializers). `ClassLoader.loadClass` is not equivalent to `Class.forName(name, true, loader)` or creating an instance.

Do not take `bytes` from an untrusted source and treat `defineClass` as a sandbox: JVM bytecode verification checks structural/type safety, not business-behavior boundaries of the executed code.

### 6.2. Never Define the Same Class Twice in One Loader

A defining loader cannot define the same binary name twice. Along the default loading path, `findLoadedClass` and locking prevent duplicate definitions. If you call `defineClass` repeatedly yourself or override `loadClass` incorrectly, the JVM may throw `LinkageError: attempted duplicate class definition`.

To run a new bytecode version of the same class name, the runtime normally must create a **new class loader** and shift references and plugin lifecycle over to the new version. Calling `reload()` on service discovery or re-reading files does not "overwrite" a class definition already existing in the same loader.

### 6.3. Restricted Packages, Signers, and Sealing

- Ordinary application loaders cannot define classes in the `java.*` namespace; doing so can raise `SecurityException`. Never use a custom loader to mock or replace core JDK classes.
- Classes in the same package defined by **the same loader** must satisfy certificate/signer consistency rules of `CodeSource` during `defineClass`. You cannot arbitrarily mix classes with different signers in the same runtime package.
- For JAR-based loaders carrying package metadata, `definePackage(...)` can be called **before** `defineClass` to attach specification/implementation metadata and `sealBase`. When `defineClass` creates a package implicitly, those attributes are not automatically inferred from JAR manifests by a hand-rolled loader.
- If supporting sealed packages, the loader must **enforce consistent sealing/JAR-source policies itself** when admitting new classes. Merely reading files and calling `defineClass` does not replicate all packaging rules of `URLClassLoader`.
- Use `getDefinedPackage(name)` to check packages defined by this loader; do not confuse it with the older `getPackage(name)` which may return an ancestor's package.

These constraints directly affect setups where plugins span multiple JARs or where a custom loader loads classes from an aggregated store without preserving package and code source metadata.

### 6.4. ProtectionDomain Does Not Automatically Create Security Isolation

The `defineClass(String, byte[], int, int, ProtectionDomain)` overload associates a protection domain with the class; overloads without a domain use a JDK default `ProtectionDomain`. `SecureClassLoader` also provides overloads based on `CodeSource`.

However, do not treat `ProtectionDomain`/class loader choices as a safe solution for running malicious plugins. In Java 17, `SecurityManager` has been deprecated for removal, and operational safety depends on the actual environment/JDK/policies. A plugin in the same JVM can still consume CPU, memory, spawn threads, or cause logic errors; reliable sandboxing typically requires process/container/OS boundaries and separate privileges, not just a custom class loader.

## 7. Delegation: When Should You Override loadClass?

**Parent-first** is the default and usually the best starting point for SPI/plugin hosts:

1. Shared APIs, JDK classes, logging contracts, and common data types are loaded from the parent.
2. Plugin implementations and specialized dependencies are resolved by the child when absent from the parent.
3. The host can cast providers to interfaces loaded from the parent.

**Child-first** can be useful when different plugins need different dependency versions, yet overriding `loadClass` must be designed carefully. If you default to child-first for every package, plugins may reload shared APIs and break compatibility. A pragmatic policy when child-first is needed is **parent-first for JDK, host SPIs, and explicitly shared packages**, allowing child-first only for truly plugin-private packages.

When overriding `loadClass(String, boolean)`, your code must be responsible for:

- checking `findLoadedClass` and executing the lookup order correctly;
- synchronizing on `getClassLoadingLock(name)` or an equivalent mechanism;
- avoiding parent ↔ child delegation cycles;
- preventing duplicate definitions if two threads request the same class;
- calling `resolveClass(clazz)` properly when `resolve` is requested;
- keeping API/SPI boundaries, packages, and loader constraints consistent.

Do not override `loadClass` merely to log or change where files are read from when `findClass` already suffices. If you need child-first, explicitly map which packages are shared and which are isolated, and write tests covering class identity and method signature scenarios before using it in runtime.

## 8. Concurrency: getClassLoadingLock and Parallel-Capable Loaders

A loader can be called from multiple threads during application startup or plugin loading. If two threads simultaneously request `demo.plugin.HelloGreeter`, an unsynchronized implementation can let both attempt `defineClass`, causing duplicate definitions and hard-to-reproduce failures.

`ClassLoader`'s inherited `loadClass` by default **synchronizes on the return value of `getClassLoadingLock(name)`** across the loading step:

- For a loader **not registered as parallel-capable**, the default lock is the loader instance itself (`this`). Requests to load different names are serialized on the same lock.
- For a loader **registered as parallel-capable**, a separate lock object can be maintained **per class name**, allowing different class names to load concurrently while requests for the same name stay coordinated.
- `registerAsParallelCapable()` must be called in the loader class's static initializer, before instances are created, and succeeds only if all relevant superclasses (except `Object`) are also registered. That capability cannot be toggled arbitrarily per instance afterward.
- Marking a loader parallel-capable **does not automatically make internal data thread-safe**: caches, maps, JAR handles, package definitions, resource lookups, and auxiliary structures must all be concurrency-safe.

The directory loader in section 5 uses inherited `loadClass` and does not declare itself parallel-capable; that is a simple, easy-to-follow choice. If upgrading it for concurrent multi-class loading, test both same-name and different-name loads, verify lock granularity, and verify parent delegation behavior before optimizing throughput.

Avoid holding arbitrary locks while calling external code or other loaders: dependency loading can nest, especially if plugins A and B cross-depend on each other. Class-loading deadlocks are far harder to diagnose than file-read errors.

## 9. Class Loading Does Not Include Resource Loading

A plugin archive often also includes `application.properties`, configuration files, service descriptors, and other resources. Overriding `findClass` only loads bytecode and **does not automatically make**:

```java
loader.getResource("META-INF/services/demo.api.Greeter");
```

return resources from the plugin directory. Per Java 17 Javadoc, default `findResource(String)` returns `null`, and default `findResources(String)` returns an empty enumeration. Inherited `getResource` tries the parent and then those hooks; therefore a custom loader that can read `.class` files may still fail to read resources.

Important consequences for runtime extensibility:

- `ServiceLoader` on the classpath looks up descriptors `META-INF/services/<SPI binary name>` via resource loading. If the loader does not expose resources, service discovery can come up empty even though `loader.loadClass("demo.plugin.HelloGreeter")` succeeds.
- Plugin code calling `Class.getResource*` or `ClassLoader.getResourceAsStream` may fail to find bundled configurations.
- If plugins are JARs/URLs, consider `URLClassLoader` and check resource policies; if the custom source is memory or another repository, implement `findResource`/`findResources` with proper URL/stream semantics rather than adding only `findClass`.
- With **named modules**, JPMS class/resource visibility and encapsulation impose additional rules. Never assume resources inside a named module's package can always be read publicly.

The section 5 demo **does not use `ServiceLoader`** and provides no `META-INF/services`, so it does not require overriding resource hooks.

## 10. How Do Classpath Loaders and Named Module Loaders Differ?

The example above compiles onto the classpath, so classes defined by `DirectoryPluginLoader` belong to that loader's **unnamed module**. It does not automatically create a named module merely because classes sit in package directories.

Java 9+ adds the overload:

```java
protected Class<?> findClass(String moduleName, String name);
```

Unlike ordinary `findClass(String name)`:

- The two-argument hook is intended to locate a class within a specific module defined by the loader; the default implementation delegates to the one-argument hook only when `moduleName == null`, and returns `null` for non-null module names.
- `ModuleLayer`, layer creation, module packaging, exports/opens, package mappings, and how the JVM associates modules with loaders must be handled separately.
- Overriding `findClass(String)` to read `.class` files from a directory is **not enough** to claim the runtime fully supports named modules.
- A loader can define classes from unnamed modules and participate in a JPMS environment, yet you must verify actual package/module boundaries before building plugin isolation.

Choose a simple loader or `URLClassLoader` for classpath plugins; use proper module-layer mechanisms when the system requires named module isolation. Do not treat `ClassLoader` and `ModuleLayer` as two names for the same object.

## 11. Operational Constraints When Writing Your Own Loader

### Paths, Resources, and Bytecode Sources

The section 5 loader takes a trusted directory. Bringing user or remote input into a real deployment requires addressing more:

1. **Namespace and root boundaries:** reject out-of-scope names, canonicalize paths, and check symlinks/traversal and file permissions. `normalize()` only resolves syntactic path segments and does not guarantee the final file stays under the root directory when symlinks exist.
2. **Avoid reading oversized files:** `Files.readAllBytes` allocates based on file size. For potentially influenced sources, enforce bytecode size limits and handle TOCTOU/file-swap races if trust levels require it.
3. **Close resources and log sources:** manage opened `InputStream`s, JARs, sockets, or handles with clear lifecycles; log class name, byte source, and loader name for investigation. `defineClass` itself does not close those resources.
4. **Preserve meaningful errors:** throw `ClassNotFoundException` when a class cannot be found/read per contract; let `LinkageError`/`SecurityException` surface with context when a class was found yet rejected by the JVM.
5. **Bytecode immutability:** do not swap bytes between inspection/selection and definition without a snapshot policy; plugin hot-swapping should use a fresh loader with fresh state and ownership.
6. **Separate classes from resources:** do not assume loading an implementation means resources, native libraries, or SPI descriptors are supported.

### Lifecycle and Class Unloading

A `ClassLoader` has no method to "unload just class X." Once defined, a class is not removed from **the same loader** so that name can be reloaded with different bytecode. The JVM may reclaim classes when their defining loader and all related classes/instances are no longer kept alive, subject to GC and runtime conditions.

References that commonly block reclamation include host `static` caches, uncancelled listeners/subscriptions, threads/TCCLs, `ThreadLocal`s, executor tasks, reflection metadata, and `Class<?>` entries retained in registries. For loaders holding JARs/sockets, close handles explicitly—unlike the example's loader which reads files and releases streams immediately.

For hot reload: build a new loader, load the new plugin version, perform a controlled lifecycle handoff, stop old callbacks, clear references, and close the previous version's resources. Do not expect calling `loadClass` or `findClass` again on the old loader to replace an already-defined class.

## 12. Diagnosing Errors at the Right Layer

| Symptom | Layer to inspect | What to check |
|---|---|---|
| `ClassNotFoundException` from `loadClass` | Discovery/delegation | Is the binary name right? Which parent and plugin directory are used? Does the file exist? |
| `NoClassDefFoundError: wrong name` | Define/link | Does the name passed to `defineClass` match the name inside the class file? |
| `ClassFormatError` | Bytecode format | Is the file a valid `.class`, were bytes truncated or corrupted? |
| `UnsupportedClassVersionError` | Bytecode/JDK version | Do `javac --release` and the runtime JDK match the class-file version? |
| `VerifyError` | Bytecode verification | Did bytecode generation/manipulation produce valid stack maps/instructions? |
| `LinkageError: duplicate class definition` | Identity/concurrency | Was the same binary name defined twice in one loader, bypassing cache/locking? |
| `LinkageError: loader constraint violation` | Type identity | Is there a same-named SPI/API with different defining loaders? Do method signatures conflict? |
| `ClassCastException` despite matching printed names | Type identity | Compare `clazz.getClassLoader()`, `interfaceClass.getClassLoader()`, and the actual `Class<?>` objects |
| `SecurityException` during define | Package name / signer / policy | Trying to define `java.*`, mixing signers, or violating policy? |
| `IllegalAccessError` or `InaccessibleObjectException` | Access/module | Package-private across loaders, JPMS exports/opens, or reflection access |
| Empty `ServiceLoader` even though `loadClass` succeeds | Resource/discovery | Can the loader find `META-INF/services/...` or is `uses/provides` configured properly? |
| OOM or failure to unload after redeploy | Lifecycle | Are registries/caches/threads/TCCLs still holding old classes, instances, or loaders? |

In logs, record the binary name, bytecode source, initiating/defining loaders, parent, exception cause, and plugin version. Never catch every `LinkageError` into `catch (ClassNotFoundException)`; they have different meanings. In particular, "file missing" differs from "file exists yet definition is invalid."

## 13. Minimum Test Suite and Design Decisions

Before using a custom loader in runtime, write dedicated integration tests covering:

- **Delegation:** host/JDK classes are loaded by the parent, plugin-private implementations are defined by the child; no duplicate SPI loading.
- **Caching:** repeated `loadClass` calls on the same instance return the exact cached `Class<?>`, never calling `defineClass` twice.
- **Identity:** two independent loaders loading the same name create two distinct definitions; both still implement the shared host interface if the parent is configured properly.
- **Missing vs. malformed:** missing files throw `ClassNotFoundException`; corrupted or mismatched-name bytecode raises the appropriate bytecode/linking error.
- **Concurrency:** multiple threads loading both the same name and different names concurrently; verify no duplicate definitions, deadlocks, or partial reads.
- **Packages and JAR sources:** metadata/certificates/sealing follow policy; plugins with different signers are not improperly merged.
- **Resources:** provider descriptors/configurations are located properly if the application relies on `ServiceLoader`.
- **Lifecycle:** unload/redeploy cleans up listeners, caches, references, and handles; TCCL is restored if modified by the runtime.
- **Source boundaries:** path traversal, symbolic links, oversized class files, I/O failures, and untrusted JARs are handled according to the actual threat model.

When you only need to load classes from standard JARs/URLs, evaluate `URLClassLoader` or built-in module mechanisms first before writing a custom loader. Write custom `findClass` only when you genuinely have a bytecode source, resolution strategy, or lifecycle requirement that standard tools cannot satisfy.

**Rule of thumb:** `loadClass` chooses **the loading path and delegation**, `findClass` decides **where to find the class when the parent cannot**, and `defineClass` asks the JVM to **define bytes into a class belonging to this loader**. Every choice is bound by class identity, bytecode/linking, packaging, concurrency, and lifecycle constraints.

**Official documentation:** [Java SE 17 ClassLoader Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html), [Java SE 17 SecureClassLoader Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureClassLoader.html), and [JVM Specification — Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html).
