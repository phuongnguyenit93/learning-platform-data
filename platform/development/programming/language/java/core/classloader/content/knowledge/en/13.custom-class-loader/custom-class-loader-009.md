# Do Not Redefine the Same Name in the Same ClassLoader

## 1. The Rule to Remember

In Java, a **specific ClassLoader cannot create a new class definition with the same binary name** after that loader has already become an *initiating loader* for a class with that name. If you try calling `defineClass` again for the same name in the same loader, the JVM rejects it, typically with a **`LinkageError`** (the typical message contains `attempted duplicate class definition`).

This is not because the `.class` file disappeared, nor because the new bytecode has the same content as the old bytecode. It is a JVM rule about **runtime type identity**.

~~~text
ClassLoader L1
  ├── defineClass("demo.plugin.Entry", bytes-v1) -> Class Entry#1
  └── defineClass("demo.plugin.Entry", bytes-v2) -> LinkageError
      (even if bytes-v2 is identical to bytes-v1)

ClassLoader L2 (new loader object)
  └── defineClass("demo.plugin.Entry", bytes-v2) -> Class Entry#2

Entry#1 != Entry#2 because the defining loaders are different.
~~~

**Two principles that seem contradictory, yet both are true:**

1. **Same binary name + same defining loader** means the same runtime class identity; you cannot create two different definitions by repeatedly calling `defineClass`.
2. **Same binary name + two different defining loaders** can represent **two different runtime types**. Those classes might not be castable to one another and may be subject to additional **loading constraints** when they interact across APIs.

This lesson belongs to the **Custom Loader** topic. The focus is on understanding why `loadClass` should return the already-loaded class, why calling `defineClass` directly a second time is wrong, and how to organize loaders for plugin/reload mechanisms.

### Learning Outcomes

After this lesson, you will be able to:

- Distinguish between **binary name**, **defining loader**, **initiating loader**, and **`Class<?>` object**.
- Explain the role of `findLoadedClass` in the default `loadClass` algorithm.
- Predict when the same `Class<?>` is returned and when `LinkageError` is thrown.
- Run a Java 17+ example yourself that creates a custom loader, calls `loadClass` twice, attempts `defineClass` again, and compares it with a new loader.
- Understand the risks of overriding `loadClass` incorrectly, especially regarding thread concurrency.
- Distinguish **reloading with another loader** from **class redefinition/retransformation** via instrumentation.

## 2. Runtime Type Identity: The Name Does Not Stand Alone

### 2.1. Class Name Is Part of the Identity

A class file contains a binary name such as:

~~~text
demo.plugin.Entry
~~~

When the JVM creates a class from a definition provided by a loader, the class's **defining loader** is a component that makes up its runtime identity. It can be described as:

~~~text
RuntimeClassIdentity = (binaryName, definingClassLoader)
~~~

Two classes with the same name but different loaders can be two different types:

~~~java
Class<?> a = loaderA.loadClass("demo.plugin.Entry");
Class<?> b = loaderB.loadClass("demo.plugin.Entry");

System.out.println(a.getName().equals(b.getName())); // may be true
System.out.println(a == b);                           // may be false
~~~

This is an **illustrative snippet**, requiring two loaders configured to find the class from the right source. `a == b` is what directly checks class identity, whereas `getName()` only checks the binary name string.

### 2.2. Two Different Loader Roles

- **Defining loader:** the loader that actually defined a class, reflected through `Class.getClassLoader()` (for bootstrap-defined classes, the API may return `null`).
- **Initiating loader:** the loader that requested the JVM to load a class by name and was recorded by the JVM as initiating the lookup of that class; the loader may receive a class defined by a parent via delegation.

Example:

~~~text
L_child.loadClass("java.lang.String")
    -> delegates to bootstrap
    -> returns java.lang.String.class

Defining loader of String: bootstrap
L_child: may be recorded by the JVM as an initiating loader for that name.
~~~

This subtlety explains why the rule in [JVMS §5.3.5](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3.5) **is not merely** “if a loader has directly called `defineClass` once, forbid a second call”. The JVM checks loading state by **initiating loader and binary name**. If a loader has already initiated and been recorded for a class with the same name via its parent, attempting to define that name itself in the same loader is also a way to violate the rule.

### 2.3. The Key Term “Same Loader” Means the Same Object

Two different instances of the **same ClassLoader subclass** are not the same loader:

~~~java
ByteLoader loaderOne = new ByteLoader(path);
ByteLoader loaderTwo = new ByteLoader(path);
~~~

Even though both use the same `path` and the same bytes, `loaderOne != loaderTwo`. If each loader defines `demo.plugin.Entry` itself, the JVM can create two separate `Class<?>` objects. Do not use the loader's class name (`getClass().getName()`), hash string, or `toString()` as a substitute for identity comparison `==`.

## 3. `loadClass` and `defineClass` Do Not Have the Same Role

### 3.1. `loadClass(String)` Is the Gateway for Looking Up a Class by Name

According to the [Java SE 21 `ClassLoader` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html), the default implementation of `loadClass(name, resolve)` works in the following basic order:

1. Call **`findLoadedClass(name)`** to check whether the loader has already been recorded by the JVM as an initiating loader for a class with the same name. If it already exists, **return that class**.
2. If not, try **parent delegation** (or the bootstrap loader when the parent is `null`).
3. If the parent cannot find it, call this loader's **`findClass(name)`**.
4. If `resolve == true` is requested, call `resolveClass` with the result according to the contract.

Pseudocode for illustration (not verbatim JDK source code):

~~~java
protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException {
    synchronized (getClassLoadingLock(name)) {
        Class<?> result = findLoadedClass(name);

        if (result == null) {
            try {
                result = (getParent() == null)
                        ? findBootstrapClassSomehow(name)
                        : getParent().loadClass(name);
            } catch (ClassNotFoundException notFound) {
                result = findClass(name);
            }
        }

        if (resolve) {
            resolveClass(result);
        }
        return result;
    }
}
~~~

**Note:** `findBootstrapClassSomehow` is a **placeholder name to describe the delegation step**, not an existing Java method. This snippet is only meant to explain the algorithm; you **must not copy it to compile**. In practice, keep the standard `loadClass` implementation and override `findClass`.

In particular, **`findLoadedClass` can return a class defined by a parent** if the current loader is an *initiating loader* of that class. The method name can easily mislead people into thinking it only returns classes that were directly passed to `defineClass` by this loader.

### 3.2. `defineClass` Creates a New Definition from Bytes

The family of protected methods such as:

~~~java
protected final Class<?> defineClass(
        String name, byte[] bytes, int offset, int length)
~~~

takes a valid class file representation for the JVM to create a class. `defineClass` **is not designed as an idempotent API like “if it already exists, return the old class”**.

Differences:

| Operation | Intent | When a class with the same name has already been initiated by the loader |
|---|---|---|
| `loader.loadClass(name)` with default implementation | Find a class by name, reusing the result if already loaded | Usually returns the same `Class<?>` |
| `findLoadedClass(name)` in a subclass | Check the state recorded by the JVM for the initiating loader | Returns the corresponding class or `null` |
| `defineClass(name, bytes, ...)` | **Define** a new class from bytecode | Attempting a duplicate definition → **`LinkageError`** |
| `findClass(name)` overridden by you | Locate bytecode from your own source and usually call `defineClass` when needed | Should only be called along a path with appropriate checks/caching |
| `new AnotherLoader(...).loadClass(name)` | A **different** loader can define a new type with the same binary name | May produce a different `Class<?>` (depending on source, delegation, and constraints) |

**Key takeaway:** if the goal is to obtain an already-existing class, call `loadClass`; **do not call `defineClass` again to “refresh” an old class**.

## 4. What Actually Causes `LinkageError`?

### 4.1. The JVM Rule

According to JVMS §5.3.5, when deriving a class from a class-file representation for name `N` by loader `L`, the JVM checks whether `L` is already an initiating loader of a class/interface named `N`. If it is already recorded, the new derivation is **invalid** and throws **`LinkageError`**.

Example:

~~~text
L = ByteLoader@1
N = demo.plugin.Entry

L.loadClass(N)        -> Class<?> C1
L.loadClass(N)        -> C1 itself
L.defineClass(N, ...) -> LinkageError
~~~

The specific `LinkageError` message depends on the JVM; this lesson relies only on the **error type and the rule**, not on the verbatim message text, which may vary by runtime/vendor.

### 4.2. What If the New Bytes Are Identical?

It is still **not** allowed to redefine the same name in the same initiating loader. The rule is based on runtime loading identity, **not on comparing file hashes**.

- Identical bytes → do not become a “duplicate yet valid definition”.
- Changed bytes → do not automatically replace the old definition.
- Modifying a `.class` file or replacing JAR contents on disk → a `Class<?>` already loaded in the JVM is not overwritten.
- Calling `ClassLoader.loadClass(name)` again after replacing the file → by default, it usually still returns the old `Class<?>` because of caching by initiating loader.

This explains why a hot-reload mechanism cannot simply be “overwrite the JAR and then call `loadClass`”.

### 4.3. Different from `ClassNotFoundException`

If you search for bytecode by name but **there is no file**, a proper custom `findClass` will throw `ClassNotFoundException`.

If you have bytes but **attempt a duplicate definition**, the error is **`LinkageError`**; the JVM is not saying that the class does not exist, rather the opposite: **a corresponding class has already been recorded**.

Other errors that can occur when defining a class: `ClassFormatError` (invalid class file), `UnsupportedClassVersionError` (classfile version not supported by the JVM), `NoClassDefFoundError` if the passed name is incompatible with the name declared in the bytes, and `SecurityException` in cases of package/security constraints. You should not lump all of these under “duplicate class definition”.

## 5. Hands-On Java 17+: Repeating `loadClass`, Trying `defineClass` Again, and Using a New Loader

The following program requires only Java 17 or later, no Gradle/Maven, and no network downloads. It creates:

- **A class `demo.plugin.Entry`** compiled into a `.class` file in the plugin directory, separate from the app classpath.
- **A `ByteLoader`** custom subclass that only overrides `findClass` to read class bytes and call `defineClass`.
- **A `forceDefineAgain` method** used only in the lab to intentionally attempt a duplicate definition and observe `LinkageError`.
- **Two independent loader instances** to compare identity.

### 5.1. Directory Tree

~~~text
demo/
  src/
    plugin/
      demo/
        plugin/
          Entry.java
    app/
      DuplicateDemo.java
  build/
    plugin/                 # separate output for Entry
    app/                    # separate output for DuplicateDemo
~~~

**Important:** when running, put only `build/app` on `-cp`. If you add `build/plugin` to the system classpath, parent-first delegation may find `Entry` first; in that case, the custom `ByteLoader` experiment will no longer accurately measure its own class definition.

### 5.2. File `src/plugin/demo/plugin/Entry.java`

~~~java
package demo.plugin;

public class Entry {
    public String id() {
        return "entry";
    }
}
~~~

`Entry` is an ordinary class. It has no special static logic because the topic of this lesson is **class definition**, not class initialization.

### 5.3. File `src/app/DuplicateDemo.java`

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class DuplicateDemo {
    static final String NAME = "demo.plugin.Entry";

    static class ByteLoader extends ClassLoader {
        private final Path root;

        ByteLoader(Path root) {
            super(DuplicateDemo.class.getClassLoader());
            this.root = root;
        }

        private byte[] bytes(String name) throws IOException {
            return Files.readAllBytes(
                    root.resolve(name.replace('.', '/') + ".class"));
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!NAME.equals(name)) {
                throw new ClassNotFoundException(name);
            }
            try {
                byte[] data = bytes(name);
                return defineClass(name, data, 0, data.length);
            } catch (IOException ex) {
                throw new ClassNotFoundException(name, ex);
            }
        }

        Class<?> forceDefineAgain(String name) throws IOException {
            byte[] data = bytes(name);
            return defineClass(name, data, 0, data.length);
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Path.of("build/plugin");
        ByteLoader firstLoader = new ByteLoader(root);

        Class<?> first = firstLoader.loadClass(NAME);
        Class<?> again = firstLoader.loadClass(NAME);
        System.out.println("repeatSameClass=" + (first == again));
        System.out.println("firstLoaderOwnsClass="
                + (first.getClassLoader() == firstLoader));

        try {
            firstLoader.forceDefineAgain(NAME);
            System.out.println("duplicateDefinition=UNEXPECTED");
        } catch (LinkageError expected) {
            System.out.println("duplicateDefinition="
                    + expected.getClass().getSimpleName());
        }

        ByteLoader secondLoader = new ByteLoader(root);
        Class<?> other = secondLoader.loadClass(NAME);
        System.out.println("sameBinaryName="
                + first.getName().equals(other.getName()));
        System.out.println("differentClassObjects=" + (first != other));
        System.out.println("secondLoaderOwnsClass="
                + (other.getClassLoader() == secondLoader));
    }
}
~~~

**Limitation of this example:** `forceDefineAgain` **intentionally violates the JVM condition** to demonstrate the error. Do not copy that method into a production loader for the purpose of “updating a class”. In a real loader, `findClass` is typically responsible for looking up bytecode, while `loadClass` performs cached/delegation lookup.

### 5.4. Compiling/Running

From inside the `demo` directory on Linux/macOS:

~~~sh
mkdir -p build/plugin build/app
javac --release 17 -d build/plugin src/plugin/demo/plugin/Entry.java
javac --release 17 -d build/app src/app/DuplicateDemo.java
java -cp build/app DuplicateDemo
~~~

On Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/plugin, build/app | Out-Null
javac --release 17 -d build/plugin src/plugin/demo/plugin/Entry.java
javac --release 17 -d build/app src/app/DuplicateDemo.java
java -cp build/app DuplicateDemo
~~~

**Exact stdout**, compiled with `javac --release 17` and verified with Java:

~~~text
repeatSameClass=true
firstLoaderOwnsClass=true
duplicateDefinition=LinkageError
sameBinaryName=true
differentClassObjects=true
secondLoaderOwnsClass=true
~~~

### 5.5. Line-by-Line Explanation

| Output | Meaning |
|---|---|
| `repeatSameClass=true` | Two calls to `firstLoader.loadClass(NAME)` return the **same `Class<?>` object**, without creating a new definition |
| `firstLoaderOwnsClass=true` | `Entry` on the first load is actually defined by the `firstLoader` instance |
| `duplicateDefinition=LinkageError` | `forceDefineAgain` attempts to call `defineClass` a second time on **the same old loader**, and the JVM rejects it |
| `sameBinaryName=true` | Both runtime classes carry the name `demo.plugin.Entry` |
| `differentClassObjects=true` | Two different loader instances can create two runtime classes with different identities |
| `secondLoaderOwnsClass=true` | The second class is actually defined by `secondLoader`, not merely returned by the parent |

**What to take away, not just memorizing the output:** the loader cache makes `loadClass` stable; `defineClass` is not an operation for modifying a class; to get a new definition with the same name, there must be conditions allowing a **different** loader to define it, or you must use a special instrumentation mechanism under its own contract.

### 5.6. Try Variations Yourself

**Experiment A — Call `loadClass` a third time:** after catching `LinkageError`, call `firstLoader.loadClass(NAME)` again and compare it with `first`. The result is still the same `Class<?>`, because the failed duplicate definition attempt did not create a new definition.

**Experiment B — Replace bytes after loading:** if you change `Entry.id()` in `Entry.java` and recompile it in another running process, the class held by the old loader in the running JVM **is not updated automatically**. With a new JVM and a new loader, the new class can be defined from the new bytes. To test this within the same JVM, you must structure the file-update and loader steps so that the moment the bytes are read can be observed; do not attribute self-refreshing behavior to an already-loaded class.

**Experiment C — Call `findClass` directly in succession:** `findClass` typically reads bytes and then calls `defineClass`; if you allow external code to call it repeatedly, you can run into duplicate definition again. Good design is to provide the `loadClass` API with the JDK's `findLoadedClass`/delegation checks, rather than exposing `findClass` as a “reloader”.

**Experiment D — Put `build/plugin` on the application classpath:** the parent may define `Entry`, causing `firstLoader.loadClass(NAME)` to return the parent's class instead of creating the class via `ByteLoader.findClass`. `firstLoader.getClass().getName()` remains the same, but `first.getClassLoader()` changes. Once an initiated record already exists for that name, trying to define a duplicate class yourself in the child is still not a valid mechanism.

## 6. Concurrency: Why Must the Loading Process Be Locked?

A custom loader may have `loadClass("demo.plugin.Entry")` called by multiple threads at the same time. If both see “not yet loaded” and then both define it, one thread may succeed while the other hits `LinkageError`. This is a risk if you override `loadClass` carelessly without preserving proper synchronization.

### 6.1. Recommended Design

**Prefer overriding `findClass`, not `loadClass`**, unless there is a special need. The default `loadClass(String, boolean)` method synchronizes on **`getClassLoadingLock(name)`**, while also checking `findLoadedClass` before delegating or looking up bytes.

~~~text
Thread T1: loadClass(N)
  -> lock for N
  -> findLoadedClass(N) == null
  -> parent delegation fails
  -> findClass(N) -> defineClass(N) succeeds
  -> release lock

Thread T2: loadClass(N)
  -> lock for N
  -> findLoadedClass(N) returns C1
  -> return C1; DO NOT redefine
~~~

The diagram illustrates the loading path where the result is defined by this loader; when the parent has the class, the `findClass` step may not be called.

### 6.2. Parallel-Capable ClassLoader

If the subclass is registered as parallel-capable via `ClassLoader.registerAsParallelCapable()` according to the rules (the relevant superclasses must also meet the requirement), `getClassLoadingLock(name)` can use a **per-class-name lock** so that multiple class names can be processed concurrently.

This **does not allow the same loader to define two classes with the same binary name**. It only changes the synchronization strategy and throughput. If you override `loadClass`, you need to verify caching, delegation, locking, and loading constraints; if done wrong, `LinkageError` may only appear under multi-threaded conditions.

You should not omit locking and try to catch `LinkageError` as a way to fix the race. That masks the root cause and can easily cause threads to observe unstable class resolution results.

## 7. Inheritance, Delegation, and “Duplicate Definition”

### 7.1. When the Parent Has Defined the Class: The Child Normally Does Not Redefine It

In the standard parent-first model:

~~~text
Parent loader P:
  defines demo.api.Service

Child loader C:
  C.loadClass("demo.api.Service")
     -> P.loadClass(...), returns P's Service
     -> C does not call findClass/defineClass for this name
~~~

This is a common way to share the **same API type** between host and plugin. If the child later attempts to call `defineClass("demo.api.Service", bytes)` to create a class with the same name in that same child that already initiated the load, it can violate the JVMS §5.3.5 rule.

### 7.2. Child-First Can Be Valid for Uninitiated Names

Some containers use child-first loading for isolated namespaces. If `C` is **not yet** an initiating loader of `com.plugin.Widget`, and the parent has not been used by C to record this class, C can define a class with that name itself under a child-first policy. However:

- You need to understand protected packages and package sealing/certificates when defining a class.
- A class with the same name as a parent's class across **two defining loaders** represents two different runtime types.
- Different type identities can cause `ClassCastException` and loading-constraint `LinkageError` when signatures cross loader boundaries.
- Core platform classes such as `java.lang.*` cannot be arbitrarily defined by a custom loader.

Therefore, **“defining the same binary name in two different loaders can work” does not mean “every case of class shadowing is safe”**.

### 7.3. Loading Constraints Between Loaders

The JVM imposes **loading constraints** when linking references across type signatures, ensuring that a type name used in certain positions represents the same runtime class when corresponding interactions occur. If two loaders have defined two different classes for a name that must match, the JVM may throw `LinkageError`.

Do not conflate two situations:

1. **Duplicate definition within the same initiating loader:** the JVM rejects attempting to derive/define a duplicate name per `5.3.5`.
2. **Loading constraint violation between loaders:** each loader may already have its own class, but linking between them requires the same identity and detects a conflict per `5.3.4`.

Both involve `LinkageError`, but **the fix is different**. The first situation is usually fixed by proper caching/delegation; the second requires designing the classpath, shared API, and loader boundaries.

## 8. What If You Need Hot Reload / Hot Deploy?

### 8.1. Common Approach: Create a New ClassLoader

A plugin system can use:

~~~text
Version 1:
  PluginLoader_v1 -> defines plugin.Feature
  application holds Feature_v1 and instance_v1

Version 2:
  create PluginLoader_v2 (new loader instance)
  PluginLoader_v2 -> defines plugin.Feature from version 2 bytes
  application switches active reference to instance_v2
  release old references when safe
~~~

At this point, `plugin.Feature` from loader v1 and from loader v2 are **two different runtime types**. The framework usually needs a common API interface defined by the parent loader for interoperability:

~~~java
// Illustrative code: API interface seen by both host and plugin through a shared loader
package demo.api;

public interface FeatureService {
    String run();
}
~~~

Plugin implementations in different loaders can all implement `FeatureService` as long as they use the exact same runtime interface from the parent. The host should hold the object by the **shared API type** rather than casting between implementation classes of two loader versions.

This is a way to change **class definitions through loader isolation**, not by calling `defineClass` to overwrite an existing `Class<?>`.

### 8.2. Conditions for the Old ClassLoader to Be Garbage Collected

Creating loader v2 **does not automatically unload v1**. Loader v1 and its classes can remain alive because:

- Old instances are retained by a singleton/static cache.
- A worker thread's `Thread Context ClassLoader` still points to v1.
- A thread created by the plugin is still running.
- `ServiceLoader`/reflection/proxy/callback caches still reference v1 classes.
- Resource/JAR file handles have not been closed.

To retire a plugin properly, you need to stop or migrate tasks, clear references/caches, restore the TCCL, close the URLClassLoader if appropriate, and let GC do its work under JVM conditions. **There is no guarantee that classes unload immediately when `close()` is called**.

### 8.3. Instrumentation Is a Different Mechanism

Java provides `java.lang.instrument.Instrumentation.redefineClasses(...)` and `retransformClasses(...)` when supported by the JVM and when the agent has the required capability. These APIs can **modify the definition of an already-loaded class within JVM limits**, but:

- **They do not create a new `Class<?>` by calling `defineClass` a second time in the same loader**.
- They depend on tooling/JVM/agent support and usually have restrictions on structural/schema changes to classes.
- They require separate instrumentation design, compatibility testing, and lifecycle management.

Therefore, **Java agent hot swap** and **plugin reload using a new ClassLoader** are two different approaches; do not use a repeated `defineClass` call as a substitute for either.

## 9. Common Errors and Diagnostic Guide

| Symptom | Likely Cause | How to Check |
|---|---|---|
| `LinkageError: attempted duplicate class definition` | `defineClass` is being called again on the same loader for a name already initiated | Trace code overriding `loadClass`/`findClass` and the number of `defineClass` calls |
| After replacing the `.class` file, calling `loadClass` still shows old behavior | The loader already has the class and returns the old `Class<?>` | Compare `first == second`, source bytes, and loader lifecycle |
| Two classes have the same name, yet casting fails | Different defining loaders | Compare `a.getClassLoader() == b.getClassLoader()` and `a == b` |
| `LinkageError: loader constraint violation` | Two loaders disagree on type identity in a shared signature | Inspect call signatures, shared API, and loader hierarchy |
| `ClassNotFoundException` | The loader could not find bytes/class for the name | Check the binary name, JAR/directory path, and delegation |
| `NoClassDefFoundError` | The JVM lacks a required class at runtime or a class previously failed initialization | Check `Caused by`, classpath/JAR, and the initial error |
| `ClassFormatError` | Input bytes are invalid according to the classfile format | Inspect the bytes read and the compiler/JDK |
| `UnsupportedClassVersionError` | Class file version exceeds the running JVM | Compare `javac --release` and `java -version` |
| `SecurityException` when defining a class in a restricted package | Package/signer/security condition was violated | Do not define `java.*` yourself; check the protection domain |
| Fails only under concurrency | Overriding `loadClass` with broken caching/locking causes two threads to define simultaneously | Preserve `getClassLoadingLock`/`findLoadedClass` or use the default loadClass |

### Checklist Before Modifying a Custom ClassLoader

1. Do you have the exact **binary name** of the class?
2. Has a class already been initiated/loaded by this loader? In a subclass, `findLoadedClass(name)` is a useful inspection tool.
3. Is the code **calling `defineClass` directly every time** instead of going through `loadClass`?
4. Did parent delegation already define a class with the same name first?
5. Is the loader used from multiple threads? Are locking and caching correct?
6. Do the loader and class belong to the right plugin/version?
7. Were plugin classes accidentally placed on the parent/system classpath?
8. Are you confusing `ClassNotFoundException` with `LinkageError`?
9. If the goal is reloading, should you create a new loader and a shared API contract instead of a duplicate redefinition?
10. Is anything holding references to the old loader and delaying class unloading?

## 10. Common Misconceptions

1. **“Calling `defineClass` a second time will update the old implementation.”** False; the JVM does not treat that as an update.
2. **“If the bytes are identical, duplicate definition is allowed.”** False; the JVM tracks class state by name/loader.
3. **“Calling `loadClass` a second time also calls `defineClass` a second time.”** False for the default algorithm when the class is already loaded.
4. **“`findLoadedClass` only sees classes defined by this loader itself.”** Incomplete; the method relies on the *initiating loader* state recorded by the JVM.
5. **“If you create two loader objects of the same subclass, they must share the same `Class<?>`.”** False if each loader defines the class itself; delegation must be taken into account.
6. **“Same binary name means the same Java type.”** False when the defining loaders differ.
7. **“Replacing the JAR on disk makes the JVM automatically reload classes with the same name.”** False for already-defined classes.
8. **“Catching `LinkageError` and calling `defineClass` again will fix it.”** False; repeating the violating operation does not resolve class identity.
9. **“Child-first always solves every class collision.”** False; it can produce loading constraint violations or mismatched API types.
10. **“Once a new loader exists, the old plugin unloads immediately.”** False while objects/threads/caches still retain the old loader.
11. **“Java instrumentation simply calls `defineClass` a second time.”** False; it is an update mechanism under a different contract.
12. **“A class loader can refresh every method by calling `loadClass` again.”** False; class lookup must be distinguished from changing a definition.

## 11. Self-Check Questions

1. Which two elements identify a normal runtime class in the JVM?
2. What is the function of `findLoadedClass(name)` in the default `loadClass` algorithm?
3. Why does calling `firstLoader.loadClass(NAME)` twice in the demo return the same `Class<?>`?
4. Why does `forceDefineAgain(NAME)` throw `LinkageError` even though the bytes did not change?
5. Distinguish between **defining** and **initiating** ClassLoaders; when a child receives a class returned by its parent, which loader defined that class?
6. When can two different loaders create two `Class<?>` objects with the same binary name?
7. Why can `first.getName().equals(other.getName())` be `true` while `first == other` is `false`?
8. Why shouldn't you put `build/plugin` on the system classpath when trying to demonstrate that `ByteLoader` defines `Entry` itself?
9. If a custom loader has two threads loading `Entry` at the same time, what mechanism must be preserved to avoid duplicate definition?
10. Does `registerAsParallelCapable` allow defining two classes with the same binary name in the same loader?
11. How does a loader constraint violation differ from a duplicate definition within the same loader?
12. Does replacing the `Entry.class` file on disk and calling `loadClass` again guarantee that the new code is used?
13. When you want to update a plugin while keeping the same class name, why is creating a new loader instance a common choice?
14. If the host and plugin v1/v2 exchange objects, why is a shared interface defined by the parent valuable?
15. Does `URLClassLoader.close()` guarantee that old classes are unloaded immediately?
16. How does instrumentation `redefineClasses` fundamentally differ from calling `defineClass` again?
17. If a loader has already initiated a class with the same name via parent delegation, why is trying to define that class again in the same loader a mistake?
18. When encountering a `LinkageError`, what information should be logged to distinguish a duplicate definition from a loading-constraint violation?

**Completion criteria:** you run the demo properly yourself, explain all six stdout lines, distinguish `loadClass` from `defineClass`, state the conditions that make up class identity, understand the causes of `LinkageError`, and choose a safe reload approach via a new loader or a dedicated instrumentation mechanism when appropriate.

## 12. Official Specifications and API Documentation

- [JVMS Java SE 21 §5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): class identity, defining/initiating loaders, and the class creation process.
- [JVMS Java SE 21 §5.3.5 — Deriving a Class from a Class File Representation](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3.5): the conditions under which the JVM rejects deriving a class with an already-initiated duplicate name and the related errors.
- [JVMS Java SE 21 §5.3.4 — Loading Constraints](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3.4): why type identity constraints exist between loaders during linking.
- [Java SE 21 `ClassLoader` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findLoadedClass`, `findClass`, `defineClass`, `getClassLoadingLock`, and parallel capability.
- [Java SE 21 `Instrumentation` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `redefineClasses`/`retransformClasses`, and how classes are updated within their own limits.

This lesson applies to Java 17+; the demonstration program was compiled with `javac --release 17` and runs standalone without requiring a build tool or framework. Rely on **Class object identity** and the actual defining loader when diagnosing issues, rather than relying solely on the class name string.
