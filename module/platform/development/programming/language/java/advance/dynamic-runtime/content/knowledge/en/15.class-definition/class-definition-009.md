# 15.9 Distinguishing Defining a New Class from Replacing the Bytecode of an Already Loaded Class

When a Java application is already running, having a new `.class` file **does not mean** the currently executing code will change automatically. The JVM clearly distinguishes two actions:

1. **Defining a new class** (*define a new class*): loading bytecode into a **class identity namespace** and creating a new `Class<?>`. APIs such as `ClassLoader.defineClass`, `MethodHandles.Lookup.defineClass`, or `Lookup.defineHiddenClass` belong to this group.
2. **Replacing the definition/bytecode of an already loaded class** (*redefine/retransform an already loaded class*): changing the supported code and metadata of **the existing runtime class itself**, usually via `java.lang.instrument.Instrumentation` or the JVM Tool Interface (JVMTI). This does not create a second class identity for the replaced class.

The core point: **having a new class** is completely different from **updating the method behavior of an existing class**. The two operations are not interchangeable, because type identity mechanisms, instance lifecycles, structural limits, and execution permissions are all different.

This article uses Java 17+, distinguishing three easily confused operations: **defining a class**, **redefining a class**, and **retransforming a class**. The two standalone runnable examples in sections 6–8 use bytecode compiled with `javac --release 17`. The Java agent demo requires a JVM that supports redefinition capability and is launched with the appropriate agent configuration.

## 1. Class file, runtime class, and class loader are three different things

A `DemoService.class` file is a **byte sequence containing the class file structure**, not the Java type object itself. When a loader uses that data to **define**, the JVM creates a runtime class; Java represents this class with a `Class<?>` object.

~~~text
.java source ── javac ──> .class bytes
                               │
                               │ ClassLoader.defineClass(...)
                               ▼
                    runtime class / Class<?>
                               │
                  link + initialize when needed
                               │
                               ▼
                object instances and method calls
~~~

**Normal class type identity** is determined by its *binary name* together with its **defining class loader**. Two bytecode files with the same binary name but defined by two independent loaders can create **two different runtime types**. Therefore:

~~~text
Loader A defines pkg.Service -> Class A
Loader B defines pkg.Service -> Class B

Class A.getName() == Class B.getName() as strings: true
Class A == Class B:                               false
Casting a Class B instance to Class A:            invalid
~~~

This is a **diagram**, not stdout. In Java, check type identity using `==` on `Class<?>` or `instanceof`/`isInstance`, not just `Class.getName()`.

**Initialization is not definition.** `defineClass` creates/links the class but does not itself guarantee that the static initializer `<clinit>` has run. Initialization according to JLS rules (for example, before the first instance creation or accessing a static field that is not a constant variable) is a separate phase. And **defining another class** does not mean the old class's code has been replaced.

## 2. Comparison table: define / redefine / retransform

| Property | Defining a new class | `Instrumentation.redefineClasses` | `Instrumentation.retransformClasses` |
| --- | --- | --- | --- |
| Target | **New class** from bytecode | **Existing class** specified by `Class<?>` | **Existing class** re-running the transformer pipeline |
| Java 17 entry point | `ClassLoader.defineClass`, `Lookup.defineClass` | `Instrumentation.redefineClasses(new ClassDefinition(...))` | `Instrumentation.retransformClasses(clazz)` |
| Requires Java agent/JVMTI? | Usually no, but requires appropriate define/load permissions | **Yes**, JVM redefinition capability and `Instrumentation` | **Yes**, retransformation capability and compatible transformers |
| Resulting `Class<?>` | **New Class object** if define succeeds | **Still the same runtime Class** | **Still the same runtime Class** |
| Objects already created from old class | Do not automatically switch to the new class | Remain instances of that class; can execute the replaced method | Similar to redefinition |
| Static fields | New class has its **own** static state | Preserves existing static values; does not re-run class initializer | Preserves existing static values |
| Which bytecode does it start from? | Bytecode passed at definition time | The **replacement** class file bytecode you provide | Input bytecode from the previous load/redefine, passed through transformers per the rules |
| Can schema be changed arbitrarily? | New class is defined with any valid bytecode structure | **No**; subject to JVMTI restrictions | **No**; subject to similar JVMTI restrictions |
| Selection criteria | Plugins / new version classes / isolated namespaces | Hot-fixing method bodies or modifying a class in use | Instrumentation / coverage / profiling / repeatable transformations |
| Common risks | `LinkageError` from duplicate class in same loader; incompatible casts across loaders | Unsupported change, agent capability, verify/link errors | Mistyped transformer, capability issues, or invalid bytecode after transform |

**Core difference between redefine and retransform:** both update an existing class. `redefineClasses` accepts a **direct replacement byte array** from the caller; `retransformClasses` uses the **`ClassFileTransformer` chain** and does not accept a new byte array in the `retransformClasses` call. Do not use the word "retransform" to imply creating a new class.

## 3. Defining a new class: `ClassLoader#defineClass` and `Lookup#defineClass`

### 3.1. `ClassLoader.defineClass` creates an additional type identity

Example in a `ClassLoader` subclass:

~~~java
final class ByteArrayLoader extends ClassLoader {
    ByteArrayLoader(ClassLoader parent) {
        super(parent);
    }

    Class<?> define(String name, byte[] bytes) {
        return defineClass(name, bytes, 0, bytes.length);
    }
}
~~~

This is an **illustrative snippet**, not a standalone runnable application. `defineClass` is a protected method, so it is typically called through a subclass. It creates a class from bytecode, using the **defining** loader as part of the type identity. `name` must match the binary name inside the bytes (if an explicit name is passed).

A normal loader uses **parent delegation** when calling `loadClass`: it asks the parent loader first, so if the parent already has a class with that name, `loadClass` may return the parent's old class. However, when a subclass directly calls `defineClass` (as in the example above), it is requesting to **define the class in the child loader**, not an operation to "replace the parent's bytes".

Key points:

- **One defining loader cannot define two normal classes with the same binary name.** Calling `defineClass` a second time with the same name in the same loader results in `LinkageError`. You need **another loader** for a different version/class identity, or instrumentation for an existing class.
- **Two loaders can define the same name** (under appropriate loading/constraint conditions). In that case, there are two different `Class<?>` objects, which may not be castable to each other.
- The new class has its **own static fields** and runs `<clinit>` according to its own lifecycle; the old class does not change because a new class was defined.
- Merely replacing a `.class` file on disk does not cause a loader to automatically define a new version or cause the JVM to update an already loaded class. A running JVM process may never read that file again.
- The bytes argument must be a valid class file and comply with package, access, sealing/certificates, verification, and class file version limits.

### 3.2. `MethodHandles.Lookup.defineClass`

Java 9+ supports:

~~~java
Class<?> newClass = MethodHandles.lookup().defineClass(bytes);
~~~

This is an illustrative snippet, assuming `bytes` describes a valid new class. `Lookup.defineClass` defines the class **in the same class loader and runtime package** as the lookup class, with the same protection domain; it requires the `PACKAGE` access mode in `Lookup`. It also creates a **new normal class**, not replacing an existing class.

In particular, using `Lookup.defineClass` cannot add a "new version" with the **same binary name** into the same loader if the class has already been defined there. A duplicate `defineClass` call is not an automatic hot reload.

`Lookup.defineHiddenClass`, on the other hand, creates a **hidden class** with different identity and lifecycle rules from a normal class: it cannot be found by ordinary name via `Class.forName`; it is useful for runtimes generating private implementations. This is still **defining a new class**, not `Instrumentation.redefineClasses`. A hidden class is also not a target that a Java agent/JVMTI can arbitrarily redefine/retransform like a normal class.

### 3.3. Why do "two classes with the same name" still not replace the old class?

If the parent class has `api.Service` and a child loader defines **another `api.Service`**, references already linked to the parent class do not automatically switch to the child's version. A caller compiled to use `api.Service` from loader A will continue to have A's **parameter types and method linkages**, and will not treat class B as the same type just because the name is identical.

This is a common cause of errors like:

~~~text
java.lang.ClassCastException:
  api.Service cannot be cast to api.Service
~~~

The message may include loader/module names. The identical class name strings are not a paradox: the two `Class<?>` objects have different identities. The solution is to design a **shared API loader**, versioned namespaces, or communication boundaries that do not rely on direct casting—not simply casting again.

## 4. Replacing bytecode of an already loaded class: `Instrumentation.redefineClasses`

Java 17 API:

~~~java
instrumentation.redefineClasses(
    new ClassDefinition(AlreadyLoaded.class, replacementClassBytes)
);
~~~

This is an illustrative snippet with `instrumentation` and prepared bytes. It does not create an `AlreadyLoadedV2.class` or assign a new `Class<?>` object to the old name. The JVM takes the `AlreadyLoaded.class` object itself to know **which runtime class** to update.

The standard way to obtain `Instrumentation` is a **Java agent** launched with `-javaagent:/path/agent.jar` (method `premain`), or an agent dynamically attached via a JVM-permitted mechanism (`agentmain`). `Instrumentation` is not a public singleton arbitrarily obtainable from any application code. The agent needs the capability:

~~~text
Premain-Class: HotSwapAgent
Can-Redefine-Classes: true
~~~

And the JVM must actually support it. Do not assume "having the manifest is enough"; before proceeding, check:

~~~java
instrumentation.isRedefineClassesSupported();
instrumentation.isModifiableClass(AlreadyLoaded.class);
~~~

The two snippets above are in the context of code that already has an `instrumentation` object. If the capability is not supported or the class is not modifiable, do not run the rewrite flow.

### 4.1. Observable results

After `redefineClasses` succeeds:

- `oldInstance.getClass() == AlreadyLoaded.class` remains **`true`**; the `Class<?>` object and defining loader **are not replaced**.
- Previously created objects remain instances of **that same class**; previous instance fields retain their values.
- **New method calls** use the redefined method bytecode. Thus, an old object can call `message()` and receive the new behavior.
- **Static fields keep their current runtime values**. `<clinit>` is not re-run; putting `static int counter=999` in the replacement bytecode **does not reset** an already used field to 999.
- **Stack frames currently executing the old method** continue running the **old version's** bytecode until that frame finishes; new invocations use the new version. Therefore, in a multithreaded system, there may be a period where old and new methods coexist on different stack frames.
- If the JVM has JIT-compiled or inlined the relevant methods, the JVM is responsible for maintaining compatible behavior after redefinition; do not build business logic on assumptions about machine-level deoptimization details.

Diagram:

~~~text
Before redefine:
  Class<?> DemoService [app loader] ── method message() -> "old"
       ├─ instance #1
       └─ instance #2

Instrumentation.redefineClasses(DemoService.class, bytes-v2)
       │
       ▼
After redefine:
  SAME Class<?> DemoService [app loader] ── NEW invokes -> "new"
       ├─ SAME instance #1
       └─ SAME instance #2

  Static fields keep their existing values.
  Stack frames currently running old code finish using the old bytecode.
~~~

Do not confuse "instances are not affected" in the documentation with "old instances forever use old methods". **Instance data/identity is not changed**, but new method calls on those instances can use the new bytecode.

### 4.2. The JVM does not allow changing everything in a loaded class

According to Java 17 JVMTI, redefinition can replace **method bodies**, the constant pool, and certain permitted attributes. However, it **cannot**:

- Add, remove, or rename fields/methods.
- Change method signatures, modifiers, or inheritance relationships.
- Arbitrarily change the class hierarchy or superclass/interface list.
- Change constrained attributes such as `NestHost`, `NestMembers`, `Record`, or `PermittedSubclasses`.

For example, having v2 add `public int newMethod()` or `private long newField` is a **schema change** outside standard redefinition capabilities on a Java 17 JVM. A specialized JVM might have extensions, but you should not assume IDE "HotSwap" means arbitrary structural changes on every JDK.

Even with the same names/methods/fields, the replacement bytes must be a class file of a valid version, matching binary name, and valid for the JVM. You cannot use bytes of a differently named class to try to "rename" a running class.

## 5. How does `retransformClasses` differ from `redefineClasses`?

`Instrumentation.retransformClasses(Class<?>... classes)` also operates on an **already loaded class**, but does not require the caller to pass a v2 byte array into this method itself.

Conceptual pipeline:

~~~text
Already loaded Class<?> C
       │
       ▼
Instrumentation.retransformClasses(C)
       │
       ▼
Obtain base class-file bytes per API rules:
  - input bytes from the most recent load / redefine
  - reapply previous transform results from non-retransform-capable transformers
  - re-run transformers with canRetransform = true
       │
       ▼
Verify and install new definition for C
       │
       ▼
SAME Class<?> and existing instances
~~~

With a transformer, you register:

~~~java
instrumentation.addTransformer(transformer, true);
instrumentation.retransformClasses(SomeLoadedClass.class);
~~~

The snippet above assumes the agent has created a `transformer` implementing `ClassFileTransformer`. To use `true` in `addTransformer`, the agent must be granted retransformation capability (`Can-Retransform-Classes: true` in the manifest, and supported by the JVM). A transformer may be called during load, redefine, or retransform depending on configuration; only transformers eligible for retransform are called again when retransformation is requested.

**Do not be mistaken:** both `redefineClasses` and `retransformClasses` can pass through registered transformers in the order specified by the API. The difference is **where the initial byte array originates**: `redefineClasses` takes replacement bytes; `retransformClasses` takes base bytes according to pipeline rules and then re-runs the appropriate transformations. It is not that "redefine has no transformers at all".

Both must obey JVM schema limits, modifiable class capability, and error rules. `retransformClasses` is useful for coverage, tracing, profiling, or instrumentation where transformers decide what code to add. `redefineClasses` is often convenient for replacement bytecode pre-compiled by a debugger or development tool.

## 6. Complete Example A — defining the same name under another loader

This lab uses only **core Java** (no javaagent needed) to prove that a **new class** is different from an **existing class**, even when the name and bytecode are identical.

Create the directory:

~~~text
example/
  v1/
    DemoService.java
    DefineClassDemo.java
    HotSwapAgent.java
    RedefineDemo.java
  v2/
    DemoService.java
  manifest.mf
~~~

The two files `HotSwapAgent.java` and `RedefineDemo.java` will be used in Example B; in Example A you only need to compile `DemoService.java` and `DefineClassDemo.java`.

**`v1/DemoService.java`:**

~~~java
public class DemoService {
    public static int counter = 1;
    public String message() {
        return "old";
    }
}
~~~

**`v1/DefineClassDemo.java`:**

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

public class DefineClassDemo {
    static class MyLoader extends ClassLoader {
        MyLoader(ClassLoader parent) { super(parent); }

        Class<?> define(byte[] bytes) {
            return defineClass("DemoService", bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        // Run from the v1 directory, where DemoService.class is located.
        byte[] bytes = Files.readAllBytes(Path.of("DemoService.class"));
        Class<?> existing = DemoService.class;
        MyLoader loader = new MyLoader(existing.getClassLoader());
        Class<?> copy = loader.define(bytes);

        Object childObject = copy.getDeclaredConstructor().newInstance();
        DemoService original = new DemoService();

        System.out.println("same name: " +
                existing.getName().equals(copy.getName()));
        System.out.println("same Class object: " + (existing == copy));
        System.out.println("different defining loader: " +
                (existing.getClassLoader() != copy.getClassLoader()));
        System.out.println("original message: " + original.message());
        System.out.println("child message: " +
                copy.getMethod("message").invoke(childObject));
        System.out.println("cast compatible: " +
                (childObject instanceof DemoService));

        try {
            loader.define(bytes);
            throw new AssertionError("duplicate must fail");
        } catch (LinkageError expected) {
            System.out.println("second definition: " +
                    expected.getClass().getSimpleName());
        }
    }
}
~~~

Run on the class path, not the module path. From the `example` directory:

~~~bash
javac --release 17 -d v1 v1/DemoService.java v1/DefineClassDemo.java
cd v1
java DefineClassDemo
~~~

**Verified stdout**:

~~~text
same name: true
same Class object: false
different defining loader: true
original message: old
child message: old
cast compatible: false
second definition: LinkageError
~~~

Explanation:

1. `existing` and `copy` both have the binary name `DemoService` and the same v1 bytes, so both return `"old"`. However, they have **different `Class<?>` objects** and **different defining loaders**.
2. `childObject instanceof DemoService` is `false` because the `DemoService` source reference in the caller is linked to the class defined by the application loader, not the class created by `MyLoader`.
3. The second `loader.define(bytes)` fails with `LinkageError` because **one loader has already defined a normal class with that name**.
4. The new class **does not** replace `existing`; the line `original message: old` still retains the original behavior.

**Be careful with delegation:** the example uses a **direct `defineClass` call in a subclass**, not `loader.loadClass("DemoService")`. Using the default `loadClass` with the application loader as parent typically returns the already loaded parent class, **without creating a new version**.

Also, do not catch `LinkageError` to arbitrarily ignore it in production: here it is caught intentionally to demonstrate the duplicate-name rule within a single loader.

## 7. Complete Example B — Java agent replacing a method of the already loaded class

Continue with the **same `example` directory tree**, but use **two bytecode versions of the same binary name**:

- `v1/DemoService.java` has `message() -> "old"`, static field `counter = 1`.
- `v2/DemoService.java` has `message() -> "new"`, static field **with the same name/same type** `counter = 999`.

**`v2/DemoService.java`:**

~~~java
public class DemoService {
    public static int counter = 999;
    public String message() {
        return "new";
    }
}
~~~

Version v2 intentionally **adds no fields and does not change method signatures**, so it fits within Java 17 redefinition scope. The initializer value `999` helps verify that static state **is not re-initialized** during redefine.

**`v1/HotSwapAgent.java`:**

~~~java
import java.lang.instrument.Instrumentation;

public final class HotSwapAgent {
    static Instrumentation inst;

    public static void premain(String args, Instrumentation instrumentation) {
        inst = instrumentation;
    }
}
~~~

This is a minimal Java agent: the JVM calls `premain` before `RedefineDemo.main` when run with `-javaagent`. It stores `Instrumentation` in a static variable for the demo to use. Real-world code must design capability management, access control, and security for the agent more carefully.

**`v1/RedefineDemo.java`:**

~~~java
import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;

public final class RedefineDemo {
    public static void main(String[] args) throws Exception {
        Instrumentation inst = HotSwapAgent.inst;
        DemoService instance = new DemoService();
        Class<?> originalClass = instance.getClass();
        DemoService.counter = 42;

        System.out.println("redefine supported: " +
                inst.isRedefineClassesSupported());
        System.out.println("before: " + instance.message());
        System.out.println("before static: " + DemoService.counter);

        byte[] replacement = Files.readAllBytes(Path.of(args[0]));
        inst.redefineClasses(
                new ClassDefinition(DemoService.class, replacement));

        System.out.println("same Class object: " +
                (instance.getClass() == originalClass));
        System.out.println("same instance still valid: " +
                (instance instanceof DemoService));
        System.out.println("after old instance: " + instance.message());
        System.out.println("after new instance: " +
                new DemoService().message());
        System.out.println("after static: " + DemoService.counter);
    }
}
~~~

**`manifest.mf`** (saved as UTF-8 without BOM or ASCII text, ending with a blank line):

~~~text
Manifest-Version: 1.0
Premain-Class: HotSwapAgent
Can-Redefine-Classes: true

~~~

Now from the **`example` directory**, compile the two versions separately and package the JAR:

~~~bash
javac --release 17 -d v1 v1/DemoService.java v1/DefineClassDemo.java v1/HotSwapAgent.java v1/RedefineDemo.java
javac --release 17 -d v2 v2/DemoService.java
jar cfm hotswap-agent.jar manifest.mf -C v1 HotSwapAgent.class

cd v1
java -javaagent:../hotswap-agent.jar RedefineDemo ../v2/DemoService.class
~~~

On PowerShell/CMD, you can use `\` instead of `/` in paths; `javac` and `jar` commands still accept relative paths as above. When launched from `v1`, the application picks up v1 `DemoService.class` from the current class path; the agent loads v2 bytes from the path provided by the caller.

**Verified stdout on a JVM with redefinition support** (Zulu OpenJDK 24, bytecode compiled at Java 17 level):

~~~text
redefine supported: true
before: old
before static: 42
same Class object: true
same instance still valid: true
after old instance: new
after new instance: new
after static: 42
~~~

**How to read it:**

1. `redefine supported: true` is obtained because both **the test JVM and the agent manifest** allow it. This is a **capability to check**, not a guaranteed result on every JVM.
2. `before: old`: the existing instance is using the v1 method.
3. `before static: 42`: the program assigned a runtime value to the field before redefinition.
4. `redefineClasses(...)` passes **compiled bytes of the same binary name `DemoService`** whose method body returns `"new"`. It affects **the same loaded class**.
5. `same Class object: true`, `same instance still valid: true`: no new Class identity is created, and the old instance is not lost.
6. `after old instance: new` and `after new instance: new`: new invocations use the v2 method body on **both old and new instances**.
7. `after static: 42`: the v2 initializer with `counter = 999` **does not re-run**. The existing static value remains 42.

Note on behavior in other JVMs: if `isRedefineClassesSupported()` returns `false` or `isModifiableClass(DemoService.class)` returns `false`, the call may be rejected. In real tools, check both, report a clear error, and do not attempt to hot-patch when unsupported.

### 7.1. Avoid ineffective ways of "replacing a class"

The following actions are **not** equivalent to redefinition on a running JVM:

- Overwriting `v1/DemoService.class` with `v2/DemoService.class` when `DemoService` is already loaded: does not force the running JVM to update the method.
- Calling `Class.forName("DemoService")` again under the same initiating loader: usually returns the existing class.
- Creating another child loader and loading the v2 version: may create a **class with a different identity**, without updating instances created by the old loader.
- Calling `Lookup.defineClass(v2Bytes)` in a loader that already defined the same binary name: encounters a duplicate definition error, does not replace the code.
- Calling `ClassLoader.resolveClass(existing)`: links/verifies an unlinked class when needed, **does not** accept replacement bytecode.

## 8. Running methods and other threads: two versions can overlap temporarily

Suppose thread T1 has entered `service.longOperation()` before the time of redefinition. While T1 has not yet returned, thread T2 executes `redefineClasses`. When redefinition completes:

~~~text
T1: ── enter longOperation() v1 ───── [running v1] ─── return
                         │
T2: ─────────────────── redefineClasses(v2) ──────── done
                                                   │
T3: ────────────────────────────────────────── enter longOperation() v2 ─ return
~~~

Per the Java instrumentation API, **active stack frames continue running the old bytecode**; **new invokes** use the new version. Therefore, a "hot fix" does not mean every in-flight operation **switches code mid-method**. If the v1 method already acquired resources, started a transaction, or updated state, it can finish with the old assumptions after T2 has already updated the class.

Operational implications:

- Identify data/state regions shared by v1/v2 methods; avoid modifying bodies in a way where concurrent execution of both versions causes inconsistency.
- Do not expect redefinition to re-run constructors, `static {}`, or migrate object state; the schema remains restricted.
- For severe protocol/data model changes, starting a new version process or separating class loaders/versions with a compatibility bridge may be safer.
- Do not assume every method handle object, reflection cache, or third-party library can be replaced/schema-extended the way debugger tools "seem" to allow. Test specifically on the target JVM/container.

## 9. When to use a new class, when to use hot swap?

**Use a new class or new loader** if you need:

- A new plugin version running alongside the old version.
- To add fields/methods, change the superclass, or change public APIs outside standard redefinition support.
- To create different runtime implementations per tenant/workload.
- Independent plugin lifecycle management, routing new requests to the new version while old requests finish.

When reloading plugins, you usually need to **switch to a new class loader** and create new instances. For the old loader to be garbage-collected and classes unloaded, all live references to its classes/objects/loader (threads, static registries, thread context class loader, caches, listeners, `ThreadLocal`, etc.) must be released. Closing a `URLClassLoader` releases open resources but **does not itself guarantee** that all of its classes are unloaded immediately. There is no reliable standalone "force unload class" button in Java SE.

**Use `redefineClasses`** if you need:

- To hot-fix a method body in a running JVM, with the schema unchanged.
- To fix code while debugging without restarting existing state.
- To update tracing/diagnostic logic in an already loaded class when the JVM and agent support it.

**Use `retransformClasses`** if you need:

- To run/reapply bytecode transformers on already loaded classes.
- To install specialized instrumentation (coverage, profiler, monitoring) from retransform-capable transformers.
- To maintain a class transformation pipeline that can be re-triggered in a controlled manner rather than generating a separate v2 class file yourself.

In production, an agent's ability to replace code is a very sensitive privilege: replacement bytecode must come from a trusted source, with signature/origin verification, scoped impact, and testing on the actual JVM version.

## 10. Error table and how to identify the wrong operation

| Symptom | Related mechanism | Cause & resolution |
| --- | --- | --- |
| `LinkageError` on second define | `ClassLoader.defineClass` | Same binary name already defined by that loader. Use another loader for a new class; to update an old class, use a valid redefine tool |
| `NoClassDefFoundError` when defining with mismatched name/bytecode | `defineClass(name,bytes,...)` | Binary name in bytes differs from requested `name`; check build output |
| `ClassCastException` despite identical class names | Same name defined in two loaders | Different `Class<?>` identity; check defining loader and design a shared contract |
| `ClassFormatError`, `UnsupportedClassVersionError` | Define or redefine | Invalid bytes or class-file version not supported by target JVM |
| `IllegalAccessException` from `Lookup.defineClass` | Defining a new class | Lookup lacks `PACKAGE` access or bytes violate same-package conditions |
| `isRedefineClassesSupported() == false` | Instrumentation | Missing agent manifest capability or unsupported by JVM |
| `UnmodifiableClassException` | Redefine/retransform | Target class is not modifiable; check `isModifiableClass(clazz)` |
| `UnsupportedOperationException` at redefinition | Instrumentation/JVMTI | JVM does not grant capability or bytes attempt unsupported schema/attribute changes |
| Class was redefined but static counter did not change | Redefine | **By design**: static fields retain values, initializer does not re-run |
| Old instance calling method receives new body | Redefine | **By design**: Class identity is preserved, new invokes use new code |
| A thread still runs v1 after redefinition | Redefine | Old active stack frames continue running old bytecode |
| Replaced `.class` file on disk but process still runs old version | Not hot swap | File change does not automatically trigger redefinition or a new class definition |
| `retransformClasses` does not run transformer as expected | Retransform | Agent lacks `Can-Retransform-Classes: true` or transformer was not registered with `canRetransform` |

**Classify errors accurately:** `LinkageError` from duplicate define in one loader is **different** from `UnsupportedOperationException` due to redefinition exceeding schema limits. Do not fix the former by randomly enabling a Java agent, and do not fix the latter by calling `defineClass` again.

## 11. Diagnostic checklist before modifying runtime

1. **Do you want a new identity or to keep the old identity?** If you need a new class with a new API, choose a different loader/namespace. If you need an existing instance's old method to change its body, consider instrumentation.
2. **Which `Class<?>` is present?** Print `clazz.getName()`, `clazz.getClassLoader()`, and `clazz.getModule()`; compare `Class<?>` objects with `==`, not just by name.
3. **What kind of bytes are being defined?** Check binary name, class-file version, bytecode verification, package, superclass, and interface constraints.
4. **Are you calling `loadClass` or `defineClass`?** `loadClass` has parent delegation and may return the old class; `defineClass` creates a new type if the loader does not already have that binary name.
5. **If redefining:** do you already have `Instrumentation` from an agent? Manifest `Can-Redefine-Classes: true`? Are `isRedefineClassesSupported()` and `isModifiableClass` both checked?
6. **Does the replacement have the same schema?** Compare fields, method names/descriptors/modifiers, superclass, interfaces, nest/record/sealed attributes. Do not confuse a body change with adding a method.
7. **Is there state to migrate?** Static/instance fields and active frames are not reset. Consider data risks from v1 and v2 code accessing state concurrently.
8. **If retransforming:** which transformers are registered and what is their `canRetransform` capability? Where do the "base" bytes in the pipeline come from?
9. **Rollback goal?** Keep a reliable v1 classfile if redefining in reverse, though rollback does not undo side effects that already occurred in the v2 method.
10. **Verify on target JVM:** instrumentation features are optional; capabilities and error messages depend on JVM configuration, agent, and target class.

## 12. Self-check questions

**1.** `Service.class` is already loaded; you overwrite it with a new file at the same path. Do running instances automatically change their method bodies?  
**Answer:** No. Replacing the file on disk does not automatically perform `Instrumentation.redefineClasses` and does not replace the already defined runtime class.

**2.** You call `defineClass("api.Service", bytesV2)` in **another loader** while loader A already has `api.Service`. Will instances created by A automatically turn into class B?  
**Answer:** No. Loader B can define class B with the same name but a **different `Class<?>`**; instances from A remain instances of class A.

**3.** You call `defineClass` twice with the same binary name in the same defining loader. What is the usual result?  
**Answer:** `LinkageError` due to duplicate class definition. It is not a hot reload.

**4.** You successfully redefine a class that has `static int counter=42`, where the initializer in the new bytes says `counter=999`. Does the runtime value automatically change to 999?  
**Answer:** No. Redefinition does not re-run `<clinit>`; the field remains 42 unless code explicitly modifies it.

**5.** An instance was created before redefinition; calling a method after it succeeds runs which body?  
**Answer:** **New calls** run the new body. The instance remains an instance of the same `Class<?>`.

**6.** A thread is in the middle of `longOperation()` during redefine. Does it switch to the new body mid-stack-frame?  
**Answer:** No. Active stack frames continue the old bytecode; new invokes use the new code.

**7.** You want to add a field `newField` without restarting and only have standard Java SE 17 instrumentation. Does `redefineClasses` support it?  
**Answer:** No, per Java 17 JVMTI structural restrictions; you need another approach such as a new class/loader or an extended implementation outside the standard guarantees.

**8.** Does `retransformClasses(clazz)` accept v2 bytes in the call itself?  
**Answer:** No. It re-triggers the transformer pipeline per API rules. `redefineClasses(new ClassDefinition(clazz,bytesV2))` is the call that supplies replacement bytes directly.

**9.** Is `Lookup.defineHiddenClass` a tool for modifying the body of an already loaded normal class?  
**Answer:** No. It creates a new hidden class; it does not redefine the old class.

**10.** You need to deploy plugin v2 alongside plugin v1, and v2 changes the structure of many classes. Which mechanism should you prefer?  
**Answer:** Two appropriate class namespaces/loaders or two independent processes/services with compatible contracts, rather than trying to force all changes through standard redefinition.

## Java 17 standard references

- [`ClassLoader.defineClass` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [`MethodHandles.Lookup.defineClass` / `defineHiddenClass`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [`Instrumentation.redefineClasses`, `retransformClasses` and capability checks](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [`ClassDefinition`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html)
- [`ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [`java.lang.instrument` agent manifest: `Premain-Class`, `Can-Redefine-Classes`, `Can-Retransform-Classes`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [JVM TI Specification 17: `RedefineClasses` / `RetransformClasses`](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html)
- [JVMS 17 `5.3: Creation and Loading; `5.4: Linking](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html)
- [JLS 17 `12: Execution, class initialization and unloading](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html)
