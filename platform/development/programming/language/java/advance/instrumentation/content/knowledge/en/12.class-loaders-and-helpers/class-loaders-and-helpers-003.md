# Class Identity Includes Name and Class Loader, and Duplicate-Name Errors Across Loaders

## 1. Why Are Two Classes With the Same Name Not Necessarily the Same Type?

In Java, a fully qualified name like `com.example.service.Order` is **not enough** to confirm that two objects belong to the same type at runtime. According to the Java Virtual Machine Specification (JVMS), the **runtime identity of a non-array class or interface** is determined by the pair:

**(binary name, defining class loader)**.

Two different loaders can **define** two classes with the same binary name — even from **the exact same byte array of a `.class` file** — yet the JVM treats them as **two different types**. Conversely, two loaders calling `loadClass("java.lang.String")` usually both receive **the same** class defined by the bootstrap loader; the loader that *initiates the request* is not necessarily the loader that *defines the class*.

A practical consequence is an error that seems absurd at first glance:

~~~text
ClassCastException: com.acme.Plugin cannot be cast to com.acme.Plugin
~~~

It can occur when the two printed names are identical, but the **defining loaders are not the same**. This error is especially common in plugin systems, application servers, hot reload, OSGi, custom class loaders, repeatedly packaged libraries, and Java instrumentation with helper classes.

This article distinguishes three situations often grouped together as "duplicate names": **two different loaders defining the same name (which can be valid)**, **one loader attempting to redefine the same name (invalid)**, and **conflicts when the JVM forces loaders to agree on a type across an API boundary (loader constraint violation)**.

## 2. Binary Name, Defining Loader, and Initiating Loader

### 2.1. Binary Name Differs From File Name and Internal Name

Given the Java source:

~~~java
package example.plugin;
public final class Widget {}
~~~

This is an **isolated source snippet**, solely to illustrate naming conventions; an actual corresponding file is `example/plugin/Widget.java`.

| Form | Value | Where It Appears |
| --- | --- | --- |
| **Binary name** | `example.plugin.Widget` | `Class.getName()`, `ClassLoader.loadClass(String)`, and the `defineClass(String, ...)` parameter |
| **Internal name** | `example/plugin/Widget` | Class-file constant pool, `ClassFileTransformer.transform` callback |
| **Conventional file name** | `example/plugin/Widget.class` | Resource path or entry inside a JAR |
| **Array type descriptor name** | `[Lexample.plugin.Widget;` | `Class.getName()` for `Widget[]`; follows separate array naming rules |

Dots `.` and slashes `/` are not freely interchangeable. A wrong name in `defineClass` can lead to `NoClassDefFoundError` because the expected name does not match the class bytes. Two files placed at two different paths do **not automatically** create two runtime classes: you must check which loader actually defines them.

### 2.2. Defining Loader: The Second Part of Identity

When the JVM accepts `defineClass("example.plugin.Widget", bytes, ...)` executed by a loader `L`, the new class is logically identified by:

~~~text
C = ("example.plugin.Widget", L)

("example.plugin.Widget", loaderA) !=
("example.plugin.Widget", loaderB)    if loaderA != loaderB
~~~

`Class.getClassLoader()` returns the **defining loader** of an ordinary class. For classes defined by the **bootstrap loader**, Java reflects the loader as `null`; here `null` does not mean the class is broken or lacks a loader mechanism.

Loader identity is compared by **object identity**, not merely by loader name, package name, or `toString()`. Two instances of the same `PluginLoader` subclass are still two different defining loaders.

### 2.3. Initiating Loader: The Requester Is Not Necessarily the Definer

Suppose `pluginLoader` calls `loadClass("java.lang.String")` and delegates successfully to the bootstrap loader. `pluginLoader` may be recorded by the JVM as an **initiating loader** of `String`, while the **defining loader** remains the bootstrap loader. This does not create another definition of `java.lang.String`.

~~~text
pluginLoader.loadClass("java.lang.String")
     |
     +-- asks parent/delegation chain
                |
                v
           bootstrap defines java.lang.String
                |
                v
       pluginLoader receives THAT SAME Class<?>
~~~

Therefore, you must not conclude that "two loaders both calling `loadClass` definitely results in two classes." Only when there are **two genuinely different defining loaders** for the same binary name does the JVM have two distinct types.

The specification has the concept of an **initiating loader** to manage resolution/loading constraints; being recorded as an initiating loader does not turn a loader into a defining loader. The `Instrumentation.getInitiatedClasses(loader)` API also has a different scope from `Class.getClassLoader()`: it does not mean every class in the result was defined by that loader itself.

## 3. Three Forms of "Duplicate Names" to Distinguish

| Situation | Principle Outcome | Why |
| --- | --- | --- |
| Loader A defines `p.Widget`; independent loader B also defines `p.Widget` | **Can be valid**, creating two different `Class<?>` objects | Two different `(name, defining loader)` pairs |
| Loader A calls `loadClass("p.Widget")` again after the first time | Normally returns **the same `Class<?>`** | Proper loader contract and `findLoadedClass` avoid redefinition |
| Loader A calls `defineClass("p.Widget", bytes)` twice | **`LinkageError`** | The same loader cannot define the same binary name a second time |
| Loader B delegates successfully to A to load `p.Widget` | Both see **one class defined by A** | B is only an initiating loader |
| `defineClass("p.Other", bytesOfPWidget)` | Usually **`NoClassDefFoundError`** | Expected binary name differs from the name inside the class bytes |
| Two loaders define different versions of `p.Widget`, and code casts directly between them | Can throw **`ClassCastException`** | The two runtime classes are not the same type |
| Two loaders define different `p.Widget` classes but participate in an API with a loading constraint forcing that name to agree | Can throw **`LinkageError: loader constraint violation`** | The JVM protects type safety during linking |
| Two copies of a library with duplicate names are both delegated to a common loader | Does not automatically create two runtime classes | Duplicate resources/JARs do not mean duplicate definitions |

**Not every duplicate name is an error**, and **not every duplicate-name error is a `ClassCastException`**. You need to know precisely **who is defining**, **who is delegating**, and **whether the failure occurs at loading, linking, or casting**.

### 3.1. Why Is the Second `loadClass` Different From the Second `defineClass`?

Following the default implementation of `ClassLoader.loadClass(String, boolean)`, the JVM follows this logic:

~~~text
loadClass(name):
    if findLoadedClass(name) already exists -> return the existing class
    if not -> ask parent (or bootstrap when parent is null)
    if parent cannot find it -> call findClass(name)
    once obtained -> may call resolveClass when requested
~~~

`findClass` can be overridden by a custom loader to fetch bytes and call `defineClass` **for the first time**. Directly calling `defineClass` again with a name that has already been defined by that same loader is a different operation, not normal lookup/caching.

An implementation that tries to define a class through `findClass` every time while bypassing the `findLoadedClass` contract is error-prone, especially when multiple threads request the same name concurrently. Usually you should override `findClass` instead of arbitrarily overriding all of `loadClass`; if you genuinely use child-first, you must manage locking, namespace boundaries, and shared API classes.

## 4. Runnable Java 17+ Example: Same Bytes, Two Loaders, Two Classes

The complete example uses **two source files**. First, compile a real class into bytes, then create two independent loaders. Each loader is asked to **directly define** the class from that exact same byte array. They have **the same binary name and the same contents**, but different defining loaders.

### 4.1. `src/lab/plugin/Widget.java`

~~~java
package lab.plugin;

public final class Widget {
    public String message() {
        return "hello";
    }
}
~~~

### 4.2. `src/LoaderIdentityDemo.java`

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

public final class LoaderIdentityDemo {
    private static final String BINARY_NAME = "lab.plugin.Widget";

    private static final class MemoryLoader extends ClassLoader {
        MemoryLoader() {
            super(ClassLoader.getPlatformClassLoader());
        }

        Class<?> define(String name, byte[] bytes) {
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = Files.readAllBytes(
                Path.of("out/lab/plugin/Widget.class"));
        MemoryLoader first = new MemoryLoader();
        MemoryLoader second = new MemoryLoader();

        Class<?> a = first.define(BINARY_NAME, bytes);
        Class<?> b = second.define(BINARY_NAME, bytes);
        Object one = a.getDeclaredConstructor().newInstance();
        Object two = b.getDeclaredConstructor().newInstance();

        System.out.println("sameName=" + a.getName().equals(b.getName()));
        System.out.println("sameClass=" + (a == b));
        System.out.println("differentDefiningLoader="
                + (a.getClassLoader() != b.getClassLoader()));
        System.out.println("firstRecognizesOwn=" + a.isInstance(one));
        System.out.println("firstRecognizesOther=" + a.isInstance(two));
        System.out.println("method=" + a.getMethod("message").invoke(one));
        System.out.println("cachedLoad=" + (first.loadClass(BINARY_NAME) == a));
        System.out.println("delegatedString="
                + (first.loadClass("java.lang.String")
                == second.loadClass("java.lang.String")));

        try {
            a.cast(two);
            System.out.println("crossCast=unexpected");
        } catch (ClassCastException expected) {
            System.out.println("crossCast=ClassCastException");
        }

        try {
            first.define(BINARY_NAME, bytes);
            System.out.println("doubleDefine=unexpected");
        } catch (LinkageError expected) {
            System.out.println("doubleDefine=LinkageError");
        }
    }
}
~~~

### 4.3. Compile and Run

From the directory containing `src/`, using JDK 17 or later:

~~~bash
mkdir -p out
javac --release 17 -d out src/lab/plugin/Widget.java src/LoaderIdentityDemo.java
java -cp out LoaderIdentityDemo
~~~

The line `mkdir -p out` is Unix shell syntax. On **Windows PowerShell**, replace it with `New-Item -ItemType Directory -Force out`; the two `javac` and `java` commands remain unchanged. Run from the **working directory containing `out`** because the example reads `out/lab/plugin/Widget.class` via a relative path.

**Exact stdout** of the example (compiled with `javac --release 17` and run on a compatible JDK):

~~~text
sameName=true
sameClass=false
differentDefiningLoader=true
firstRecognizesOwn=true
firstRecognizesOther=false
method=hello
cachedLoad=true
delegatedString=true
crossCast=ClassCastException
doubleDefine=LinkageError
~~~

Meaning:

1. `sameName=true`: both classes return `"lab.plugin.Widget"` from `getName()`.
2. `sameClass=false`: `Class<?> a` and `Class<?> b` are **two different runtime class objects**, not two references to the same class.
3. `differentDefiningLoader=true`: `a.getClassLoader()` and `b.getClassLoader()` differ. This is the condition that explains the difference in identity.
4. `firstRecognizesOwn=true` but `firstRecognizesOther=false`: an object defined by loader B **is not an instance of the class defined by loader A**, even though the bytes are identical.
5. `method=hello`: loader A's class works normally; the failure is not due to invalid class bytes.
6. `cachedLoad=true`: after loader A has defined `Widget`, `first.loadClass(...)` returns that same class instead of defining it again.
7. `delegatedString=true`: both loaders delegate loading `java.lang.String` to the class managed by the bootstrap loader.
8. `crossCast=ClassCastException`: `Class.cast` checks *runtime type identity*, not just the printed name.
9. `doubleDefine=LinkageError`: **loader A itself** attempts to redefine `Widget` and is rejected by the JVM.

**Why does the `MemoryLoader()` constructor choose the platform loader as its parent?** The goal of the demo is to control the definition of `Widget` by two independent loaders, preventing a parent app loader on the classpath from picking up `Widget` instead. `first.define(...)` calls `defineClass` with direct control; meanwhile, foundational classes like `String` are still provided by the parent/bootstrap. This is a choice for an **isolated demo**, not a recommendation that all production plugin loaders must use the platform loader as their parent.

**Note:** the `Widget.class` file on disk is just a convenient way to obtain a byte array for testing. The two different runtime classes are **not** caused by having two different `Widget.class` files — both use **the exact same byte array**. Runtime identity emerges from the **definition operation by each loader**.

### 4.4. Why Not Cast to `Widget` in the Example Code?

The main program does not import `lab.plugin.Widget` for a compile-time cast. If it imported it and used `(Widget) two`, the name `Widget` in `LoaderIdentityDemo` would be linked to the class seen by the **app loader**, potentially creating **a third type** or changing the test scenario. The demo intentionally uses `Class.cast(Object)` on loader A's exact `Class<?>`, ensuring the check reflects the difference between A and B.

In real systems, a `ClassCastException` reporting "`X cannot be cast to X`" is usually a sign that an interface/model/JAR has been defined multiple times across different loaders. Do not try to fix it by renaming Java variables or adding repeated casts.

## 5. Two Copies of a Library: When Is It Just a Duplicate Resource, and When Does It Create Duplicate Classes?

An application may contain `lib-a.jar` and `lib-b.jar`, both containing `com.vendor.Model.class`. Several different outcomes are possible:

- **One classpath, one application loader:** resource lookup along the classpath/module path order may pick one copy to define the class. Two `Class<?>` objects are not automatically created just because two JARs have a duplicate entry. There is a risk of **picking the wrong version**.
- **Two separate plugin loaders, each defining the same binary name:** can create two different runtime classes, **with only one definition per loader**. Version isolation may be intentional.
- **One loader attempting to define the same binary name twice:** `LinkageError`.
- **Two supposedly independent plugins that must exchange objects of the same-named class with each other:** may hit `ClassCastException` or a loader constraint violation, because the class at the API boundary is not unified.

**Class file path is lookup metadata, not a JVM identity criterion.** Printing `getProtectionDomain().getCodeSource()` can be useful to see the JAR location (when available), but two classes from the same location can still have different identities if defined by different loaders; conversely, a class can be defined from in-memory bytes without a useful code source URL.

## 6. Loader Constraints: Why Are Two Classes With the Same Name Allowed to Exist Yet Sometimes Cause `LinkageError`?

The JVM allows two independent loaders to define the same binary name if they truly reside in separate namespaces. However, when a class invokes a method or accesses a field of a class defined by another loader, the **descriptor** may reference types that both sides must agree on as **the same** to preserve type safety.

Conceptual example:

~~~text
api.Contract            defined by loader P (shared parent)
  method: process(api.Message) : api.Message

plugin.Impl             defined by loader C (child)
  implements api.Contract
  process(api.Message) : api.Message

If loaders P and C resolve api.Message to two DIFFERENT Class<?> objects,
the JVM can impose a loading constraint and reject linking.
~~~

This is a **conceptual model**, not a standalone runnable programming example. When an implementation overrides a method in a parent API, the types in the parameter and return descriptors must satisfy the applicable **loading constraints**. If the same name `api.Message` is bound to two different classes when the JVM requires them to be equivalent, linking can throw **`LinkageError`**; on HotSpot, the message may contain the phrase `loader constraint violation`.

That **does not mean** that merely having two definitions with the same name from two loaders causes the JVM to immediately throw an error. Constraint-related errors typically arise only when **preparation/resolution or recording an initiating loader** creates an actual conflict. The JVM is also permitted to defer resolution; the error may appear on the first use of a method/field, not necessarily as soon as the loader is created.

### 6.1. Why Does the JVM Need This Mechanism?

If the caller believes the parameter is the `api.Message` class defined by loader P, while the callee believes it is a different class with the same name defined by loader C, the bytecode signature matches by name while the actual object types do not match. The JVM enforces loader constraints to prevent breaking **type safety** across method/field boundaries.

A strong design rule: **types appearing in an API shared between plugins and the host must be defined by a common loader** (usually the parent/host loader), and plugin loaders must **delegate** those packages properly. Isolate implementation parts into separate loaders, and do not duplicate contract types.

## 7. Runtime Package Also Depends on the Defining Loader

Two classes with the same `package example.bridge;` in source but defined by two different loaders **do not automatically belong to the same runtime package**.

According to the JVMS, a *runtime package* is determined by the **package name and defining loader**. Therefore:

- Having the same `package` line in source **does not guarantee** package-private access across two loaders.
- Access rules, nest/module rules, protection domains, and sealed packages must still be checked appropriately by the JVM; "matching package string" is not a permission-granting mechanism.
- Reflection or `setAccessible` is not a default fix for identity bugs; in the Java module system there are also separate `exports` and `opens` restrictions.
- Matching `Class.getPackageName()` **does not prove** two classes are in the same runtime package.

This is especially important for an **agent helper** injected into a different loader from the business class. Both helper and target may declare `package com.app;`, yet if they are defined by two different loaders, they still do not have valid package-private access based solely on that name string.

**Array and primitive types:** primitives such as `int.class` have `getClassLoader() == null`. Array classes are created by the JVM, and an array's `getClassLoader()` reflects the loader of its reference element type (or `null` for primitive arrays). They have their own creation rules in the JVMS; you should not take a regular class-definition demo and assume `defineClass` can also be called directly for `int[]`.

## 8. Practical Connection to Java Instrumentation and Helper Classes

An agent typically consists of two groups of bytecode:

- **Agent logic:** `premain`/`agentmain`, transformers, registries, loggers, exporters.
- **Helpers/advice called from application code after instrumentation:** for example, `ProbeBridge.onEnter()` and `ProbeBridge.onExit()` invoked directly by injected bytecode.

The issue is not just whether the agent **can load** `ProbeBridge`, but also **whether the transformed class can resolve the right helper class appropriately**.

~~~text
               JVM
AgentLoader -> Agent/Transformer -> emits bytecode calling probe.Helper.enter()
                                          |
                                          v
                                App class defined by PluginLoader
                                          |
                                          v
                               resolves "probe.Helper" under
                               the appropriate loader/module rules
~~~

If the helper is only defined by the agent/system loader, but a plugin loader with an isolated parent cannot find the helper, the transformed code may hit **`NoClassDefFoundError`** when the JVM needs to resolve the reference. If two loaders define **two copies of `probe.Helper` with the same name**, their static state/counters are also **separate**: the transformer thinks it is reading a shared counter, while application code updates the counter in the other helper copy.

### 8.1. Beware of Two Helper Copies With the Same Name

Suppose:

~~~text
agent's system loader:
    probe.Helper  -> static counter A

isolated plugin loader:
    probe.Helper  -> static counter B
~~~

Even if the source/bytes of `probe.Helper` are identical, `counter A` and `counter B` belong to two **separate runtime classes**, each with its own static fields. This can cause metrics to "lose counts" or write to the wrong exporter without any immediate exception.

If instrumented bytecode calls `Helper.enter(Model)` and `Model` is inconsistent across loaders, the JVM can encounter a **loader constraint** or other linkage error, not just `ClassNotFoundException`. Putting the helper on the right classpath is not always enough: you must understand the helper's **defining loader**, **module visibility**, **package access**, **dependency loaders**, and **version**.

### 8.2. Ways to Place Helpers

| Approach | When Useful | What to Check |
| --- | --- | --- |
| Helper in a **shared parent/API loader** | Multiple child plugins need to use one contract/bridge | Plugin loaders actually delegate that name; packages and versions are consistent |
| Helper defined in **each plugin loader** | Want to isolate state/version per plugin | Accept that each loader has its own `Helper.class` and static state; do not cast/exchange helper types across loaders |
| Helper on **bootstrap search** via `Instrumentation.appendToBootstrapClassLoaderSearch(JarFile)` | Probe is called from many loaders, needing a minimal widely visible helper | Only append vetted JARs; avoid name/package collisions; do not assume it automatically solves all module access |
| Helper in **system class-loader search** | Target can resolve via the system parent | Target's loader might not delegate to system; plugins may be isolated |
| Transform bytecode to call a bridge already defined in an appropriate loader | Want control over access permissions and compatibility | Choose an API signature using only shared types, with proper JPMS reads/exports/opens |

`appendToBootstrapClassLoaderSearch` **adds a JAR to the bootstrap search path**; it does not automatically "move" classes already defined in other loaders into bootstrap, nor does it open packages across all modules. In practice, a helper in bootstrap should be very small and avoid referencing back to APIs that only exist in the application loader, because bootstrap does not automatically see down into child loaders.

If the agent uses ASM/Byte Buddy/metrics libraries, separate the **agent engine** from the **runtime helper** classes that actually need to be called from application code; avoid injecting an entire large library into bootstrap without good reason. Helper namespaces should be given distinctive names to avoid colliding with application libraries or other agents.

### 8.3. The Loader in the Transformer Callback Is Key Information

A code snippet inside a `ClassFileTransformer` (not a standalone program):

~~~java
@Override
public byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain domain,
        byte[] bytes) {

    // className is usually an internal name, e.g., lab/plugin/Widget.
    // loader is the defining loader of the class the JVM is processing.
    if (className == null || !className.startsWith("lab/plugin/")) {
        return null;
    }
    // Must check loader/module/helper visibility before weaving.
    // Do not touch the input bytes when only observing.
    return null;
}
~~~

Do not use **the class name alone** as the unique key for instrumentation state if multiple loaders have the same `lab/plugin/Widget`. A pair of internal name + defining-loader identity (and version context if needed) is better. For already-loaded classes, use `Class<?>` itself for exact identification: `Instrumentation.isModifiableClass(theClass)` and `retransformClasses(theClass)` also operate on **a specific class object**, rather than taking a string name for the JVM to pick arbitrarily.

For the bootstrap loader, the `loader` parameter can be `null`; never call `loader.toString()` unconditionally in a transformer. You should also avoid complex classpath logging or scanning inside the callback: it can trigger additional class loading by the agent itself and cause reentrancy.

## 9. Diagnosing Errors: Identify Which Class, Which Loader, and at Which Step

### 9.1. Minimum Information Set

When an exception says "same name but cannot cast," collect (through a safe diagnostic channel):

- **Binary name:** `type.getName()`.
- **Defining loader:** `type.getClassLoader()`; print the **loader class** and an object-identifying ID when needed, without using the loader name as a unique key.
- **Module:** `type.getModule()` to spot JPMS boundaries.
- **Code source if available:** `type.getProtectionDomain().getCodeSource()`; may be null or inaccessible, and do not treat the URL as identity.
- **Relationship:** are the two `Class<?>` objects actually `==`? Is `typeA.isInstance(objectB)` true or false?
- **Failure context:** did it happen during class lookup, define, link, invoke, cast, or plugin reload?

Illustrative snippet when you already have `Class<?> type`:

~~~java
System.out.println("binaryName=" + type.getName());
System.out.println("definingLoader=" + type.getClassLoader());
System.out.println("module=" + type.getModule());
~~~

Not a standalone program. Loader output like `SomeLoader@5a3a1b` is only an implementation representation; it is not stable across runs. Compare **object identity** or store an internal identifier generated by the diagnostic layer; do not compare `toString()` strings as a basis for type equality.

### 9.2. Matrix of Errors and Causes

| Symptom | Possible Explanation | How to Handle |
| --- | --- | --- |
| `ClassCastException: X cannot be cast to X` | Two copies of `X` defined by different loaders | Print both `Class<?>`/defining loaders; unify the shared API or avoid casting |
| `LinkageError: attempted duplicate class definition` | One loader defined the same binary name **again** | Fix `findClass`/`loadClass`, caching, and concurrency |
| `LinkageError: loader constraint violation` | Two loaders returned different classes for a type the JVM requires to agree at a boundary | Move the contract model/type up to a shared parent; check descriptors and delegation |
| `NoClassDefFoundError` after the agent injects helper calls | Target loader cannot resolve the helper or its dependencies | Provide the helper in a loader visible to the target; check modules and dependencies |
| `ClassNotFoundException` from `loadClass`/`Class.forName` | The queried loader cannot find the name | Check classpath/parent/delegation and binary name |
| `NoClassDefFoundError` due to name mismatch | `defineClass` used an expected name different from the name in the bytes | Compare binary name with the class-file `this_class` |
| `IllegalAccessError` | Access permissions/runtime package/module do not allow access | Check the defining loaders of both classes, module exports/opens, and access flags |
| `NoSuchMethodError` or `AbstractMethodError` | Binary API compatibility/version mismatch across loaders or inconsistent JARs | Check method signatures/descriptors and the resolved dependency version |
| `ClassCircularityError` | Circular loading/supertype relationship, or a loader creating an invalid circular definition chain | Inspect the loading stack and the order/recursion of the custom loader |
| `SecurityException` in `defineClass` | E.g., class in `java.*` package, invalid certificate/package policy | Do not bypass JVM policy; choose an appropriate namespace |

**Do not lump everything together as a "classloader conflict."** `NoSuchMethodError` can be purely an API version mismatch without two different loaders. `ClassNotFoundException` can be a normal lookup failure. Always use the exception class, stack trace, loader identity, and reproduction scenario as evidence.

### 9.3. Why Can Errors Appear Late?

The JVM may defer certain **symbolic reference resolution** operations. A class can be loaded/defined first, and only when another method is invoked or a field is resolved is the mismatch discovered. Thus "the agent successfully loaded the helper" **does not prove** that every injected call site will link properly.

Good diagnostics should reproduce **the exact call site** and loader boundary, not just test `Class.forName("probe.Helper")` from an arbitrary thread/tool loader: `Class.forName` with a different loader may end up checking **a different helper copy** than the one the target bytecode will resolve.

## 10. Safe Plugin Architecture: Separating Contract and Implementation

A common design:

~~~text
Host/Application loader
    -> api.Plugin (interface)
    -> api.Request, api.Result (DTO/contract)

PluginLoader A (parent = Host)
    -> pluginA.Implementation
    -> dependency-private A

PluginLoader B (parent = Host)
    -> pluginB.Implementation
    -> dependency-private B

Both A/B DELEGATE api.* to Host.
~~~

What can be shared:

- `api.Plugin`, `api.Request`, and `api.Result` are defined **once** in the shared host loader.
- Each plugin keeps its implementation classes and private libraries in its own loader; two plugins can use different dependency versions **as long as those types are not exposed across the shared API**.
- The host casts the implementation to `api.Plugin` successfully **when the implementation actually implements the exact `Class<?> api.Plugin` defined by the host**, not a same-named interface defined by the plugin itself.

If a plugin packages a copy of `api.Plugin` in the child and uses child-first loading for `api.*`, the host and plugin may see **two interfaces with the same name and different identities**; casting fails even if the source signatures and JARs are identical. The fix is to **plan namespace delegation** and dependency packaging, not just write `(Plugin)(Object) obj`.

For data exchanged across boundaries, use host-defined interfaces/DTOs, or serialization/structured data with an explicit schema/version if true isolation is needed. Do not pass raw `Class<?>`, implementation objects, or generated helper classes between plugin loaders and cast by binary name.

### 10.1. Parent-First Is Not an Absolute Rule

Default `ClassLoader.loadClass` usually favors the parent, but custom loaders can implement **child-first** for their own namespaces to isolate dependencies. What matters is not "parent-first is always right," but **having a consistent rule for the shared API**.

In practice, a policy like this can be used:

~~~text
java.*, javax.* must follow platform/runtime rules
api.host.*      -> always delegate to host
probe.bridge.*   -> delegate to shared helper loader
plugin.private.* -> controlled child-first
other names      -> clear strategy with fallback
~~~

This is a **conceptual policy** table, not a class-loading rulebook to apply mechanically to every JDK/JVM. With JPMS layers, module readers, OSGi, or enterprise applications, there are separate resolution/visibility mechanisms; a custom `ClassLoader` should not bypass JVM guarantees around package sealing and concurrent loading.

## 11. Memory, Class Loader Lifecycle, and Caches

Two different loaders do not just create two class identities: they can also hold **two copies of static state**, metadata, and the required code. For plugin reload, creating a new loader for the same name can be a valid way to load a new code version without attempting to redefine the same name in the old loader.

However, **unloading** loaders/classes does not happen automatically just because you call `plugin.close()` or delete the JAR file:

- If threads, `ThreadLocal`, callbacks, MBeans, scheduled tasks, registries, static fields, or agent transformers still hold references to a class/loader/instance, they can keep the loader alive.
- A global `Map<String, Class<?>>` cache does not distinguish loaders and easily returns **the wrong class** when a plugin version changes.
- A `Map<ClassLoader, Map<String, ...>>` cache distinguishes identity but can keep the loader alive if the map has no lifecycle strategy.
- `ClassValue<T>` is a JVM tool for values associated with a `Class<?>`, which can be useful for caching metadata by exact class identity. You need to understand the value's lifecycle/concurrency and avoid reference cycles that increase memory retention.
- Do not "fix" reload issues by trying to call `defineClass` again on the same loader; it does not replace an already defined type.

In Java instrumentation, a weak-key cache or `ClassValue` may be more appropriate than storing `Class<?>` indefinitely in a static agent map; however, you still need to check whether the **value** holds a back-reference to the class/loader, accidentally defeating GC.

## 12. Implementation and Testing Checklist

### Before Putting a Helper Into an Application

1. List the **binary names** of helpers, advice, bridges, and types appearing in public method descriptors.
2. Identify **the actual loader that defines the target class** and **the loader that defines each helper**.
3. Verify that the target can resolve the helper after bytecode injection: parent delegation, isolation, module reads/exports/opens, and helper dependencies.
4. Decide whether the helper is shared as **one copy** or **one copy per plugin**, including the policy for static counters/registries.
5. Keep the shared API in **one common loader** if objects must be cast/exchanged across boundaries.
6. Exclude agent/helper/logger packages from the transformer when needed, avoiding agent self-instrumentation.
7. Design caches keyed by **class identity**, not just `getName()`.
8. Verify that namespaces do not collide with other agents or application JARs; use dedicated packages and package dependencies carefully.
9. Test initial loading, repeated loading, hot reload, two plugins with the same name, and concurrency within the same loader.
10. Test **the actual instrumented call site**, not just loader checks from the outside.

### Minimum Empirical Test Suite

- **A/B with same bytes:** two loaders defining `p.Type` separately must produce two distinct `Class<?>` objects.
- **A loads again:** `loadClass` returns the existing class without defining another.
- **A attempts to redefine:** receives `LinkageError`.
- **A/B both delegate a JDK class:** both receive the same `Class<?>` defined by bootstrap.
- **Object from A cast to class B:** fails even though the names match.
- **Shared interface:** an implementation defined by a plugin loader that implements a contract from the host loader must cast cleanly to that shared interface.
- **Missing helper:** test handling of `NoClassDefFoundError`/resolution in an isolated environment.
- **Helper defined twice:** verify that static metrics/registries are not unexpectedly split.
- **Loading constraints:** test boundary methods whose descriptors use types loaded from multiple loaders and verify linking.
- **Cleanup:** after unloading a plugin, check for references keeping the loader alive and bound caches/`ThreadLocal`s.

## 13. Misconceptions to Avoid

1. **"`Class.getName()` being equal means two `Class<?>` objects are equal."** False: you must consider the defining loader.
2. **"Having two `p/Foo.class` files means the JVM creates two classes."** False: it depends on which class loader defines them.
3. **"Two different loaders both calling `loadClass` definitely produces two classes."** False: delegation can return a shared class.
4. **"Duplicate binary names in two loaders always throw `LinkageError`."** False: they can be two valid namespaces as long as there is no cross-boundary cast or linking conflict.
5. **"Calling `defineClass` a second time just reloads the class."** False: the same loader redefining the same name causes `LinkageError`.
6. **"Fix a cast by casting to `Object` first and casting back."** No: runtime type identity does not change.
7. **"Just put the helper in the same package as the target."** False: the runtime package also depends on the defining loader.
8. **"`appendToBootstrapClassLoaderSearch` solves everything."** False: it does not automatically resolve module/loader constraints or reverse-direction dependencies.
9. **"`ClassNotFoundException` and `NoClassDefFoundError` are the same."** False: API lookup failures and linkage/definition failures have different contexts.
10. **"`getClassLoader() == null` is an error."** False: the bootstrap class loader is commonly represented as null.
11. **"A cache keyed by name is enough for an agent working with multiple plugin loaders."** False: the same name can have multiple runtime classes/versions.
12. **"Same package name grants package-private access."** False: they must also be in the same runtime package under the JVMS.
13. **"Successfully loading the helper means woven code can definitely call it."** False: the target loader must resolve the right helper and its methods/types.
14. **"Dropping all references to `byte[]` unloads the class."** False: class loader and object reachability are what matter.

## 14. Self-Check Questions

1. What components does the JVMS use to determine the runtime identity of an ordinary class?
2. How does a `defining loader` differ from an `initiating loader`? Give an example with `java.lang.String`.
3. Why can two `Class<?>` objects created from **the same** `Widget.class` be unequal?
4. Why does `first.loadClass(BINARY_NAME)` succeed the second time, whereas `first.define(BINARY_NAME, bytes)` throws `LinkageError`?
5. When is it valid for two loaders to define the same `api.Message`, and when can the JVM enforce a loader constraint that causes an error?
6. In a plugin architecture, which loader would you place `api.Plugin` in so that the host can cast implementations?
7. Why can two same-named copies of `probe.Helper` count metrics into two different static counters?
8. Does placing an agent helper in the same `package` as an application class but in a different loader automatically grant package-private access?
9. If a class is defined in a plugin loader while the helper resides in the system loader, what conditions make the target succeed or fail to resolve the helper?
10. Why are `Class.getProtectionDomain().getCodeSource()` and JAR file names not substitute keys for runtime type identity?
11. Why can linkage errors appear only when a method is called for the first time?
12. When reloading a plugin, why does creating a new loader have a different meaning from redefining a class in the old loader?

**Key takeaway:** For non-array classes and interfaces, **runtime identity = binary name + defining class loader**. Two independent loaders can define two classes with the same name; casting between them is not automatically valid. The same loader cannot redefine the same name, and the JVM also enforces **loading constraints** at linking boundaries to protect type safety. When designing Java agents/helpers or plugins, unify **shared contract types** in the appropriate loader, check the target's actual loader/module, and never use the class name alone for identification or caching.

### Official Documentation

- [JVMS Java 17 — `5.3 Creation and Loading, `5.3.4 Loading Constraints](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html)
- [Java 17 — ClassLoader, loadClass and defineClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java 17 — Class, getName/getClassLoader/isInstance/cast](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [Java 17 — Instrumentation: bootstrap/system search and getInitiatedClasses](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [JLS Java 17 — Class Loader Consistency](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html)
