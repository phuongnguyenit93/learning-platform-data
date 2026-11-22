# Distinguishing Runtime Code Modification from Loading a Class Version with a New Class Loader

**Context:** Java Advance → instrumentation → **Redefinition**.

"Updating Java code without restarting the JVM" has at least two mechanisms that are easily confused:

1. **Modifying the existing class definition:** `Instrumentation.redefineClasses(...)` replaces the bytecode of **an already-defined runtime class**, within the limits allowed by the JVM. The runtime class identity does not change; existing instances continue to exist and new method invocations use the replaced method body.
2. **Loading a new class version with a different `ClassLoader`:** The VM creates **a different runtime class identity** even though both class files have the same binary name. V1 objects continue to belong to class V1; to use V2, you must create V2 objects and switch calls/references to them.

The two approaches differ in **class identity, static state, schema-change capability, active calls, class unloading, type compatibility, and rollback strategy**. This article includes two standalone labs with Java 17+, requiring no external libraries: a Java agent redefining the same running class, and two `URLClassLoader`s simultaneously loading two versions with the same name.

## 1. Both Mechanisms on One Diagram

**Redefinition:**

```text
One JVM, one defining loader A
  Class<?> C = demo.Service @ A
          │
          ├─ V1: message() returns "v1"
          │      object old = new Service()
          │
          ▼
  redefineClasses(C, bytesV2)
          │
          ▼
  Still Class<?> C = demo.Service @ A
  object old still has getClass() == C
  old.message() on a new call returns "v2"
```

**New loader:**

```text
One JVM
  Loader A                          Loader B
     │                                │
  demo.Service V1                  demo.Service V2
  Class<?> C1                     Class<?> C2
     │                                │
  Object old                      Object fresh
  old.message() -> "v1"           fresh.message() -> "v2"

C1.getName().equals(C2.getName()) == true
C1 == C2                             == false
```

**There is no operation to "change the class" of a V1 object** simply by creating loader B. References pointing to V1 remain as they are. Conversely, when `redefineClasses` succeeds, a V1 instance created earlier can execute the new method body on invocations **after** redefinition.

## 2. Quick Decision Table

| Aspect | `Instrumentation.redefineClasses` | Loading the same name via a new loader |
| --- | --- | --- |
| Runtime class identity | Keeps the **same** `Class<?>` and defining loader | Creates a **different** class identity if the defining loader is actually different |
| Existing objects | Keep their identity/fields; new calls can see new code | Continue to belong to V1 and run V1 code |
| Need to create V2 objects? | Not required to run V2 methods | Usually **yes** |
| Static state | Static values are **preserved**; `<clinit>` is not re-run | Each class identity has its own static fields and class initialization |
| Method body | Replaceable within the scope supported by the JVM | Version V2 has independent new code |
| Field/method schema | Restricted: cannot arbitrarily add/remove/rename fields/methods | The new class can differ in schema, but must be compatible with clients |
| Superclass/interfaces | Cannot arbitrarily change inheritance | The new class can change within linkage/ABI constraints |
| Code currently running in stack frames | Active frames can continue with the old bytecode | Calls already started on V1 continue on V1 |
| Running two versions side by side long-term | Not a per-request versioning mechanism for the same class identity | Can keep V1/V2 side by side and route by tenant/request |
| Requires Java agent/JVMTI capability | Yes, via `Instrumentation` or corresponding tooling | Not required |
| Casting V1 ↔ V2 | Does not produce a new type merely from redefining | Two classes with the same name but different loaders **cannot be cast** by default |
| Reclaiming the old version | Does not create a new class identity just to replace a body | V1 can be unloaded when the loader and references become eligible for GC |
| Operational complexity | Schema restrictions, runtime verification, active frames | Delegation, SPI, routing, cleanup, metaspace, and state migration |

Do not infer from "hot reload" that one mechanism can do everything. **Patching a method** and **replacing a module/plugin with a new version** are two different operational problems.

## 3. Why Do Classes with the Same Name Still Form Two Different Java Types?

According to **JVMS 5.3**, the runtime identity of a class/interface is determined by:

```text
(binary name, defining class loader)
```

The name `demo.VersionedService` is only one component. If `LoaderA` defines `demo.VersionedService` and `LoaderB` also defines a class file with the same name, the JVM has two class identities.

### 3.1. Defining loader vs. initiating loader

- **Defining loader** actually defines the class from bytes; it is the loader that participates in runtime type identity.
- **Initiating loader** receives the class-loading request and may delegate to another loader.
- Under the usual **parent-first** strategy, a child loader may receive the V1 class **defined by the parent**, instead of defining V2 itself.

Therefore, **two separate ClassLoader objects** do not automatically guarantee two class identities. To know whether a new version has been loaded, check the **actual `Class<?>` object and defining loader**, not just the name or configured URLs.

Example fragment:

```java
// Assume twoObjects were created in determined class loaders.
Class<?> a = firstObject.getClass();
Class<?> b = secondObject.getClass();

System.out.println(a.getName().equals(b.getName()));
System.out.println(a == b);
System.out.println(a.getClassLoader() == b.getClassLoader());
System.out.println(b.isInstance(firstObject));
```

This is **not a standalone program** because `firstObject` and `secondObject` are undeclared. If the two class identities are different despite having the same binary name, the lines typically output `true`, `false`, `false`, `false` respectively.

### 3.2. Package and module boundaries

A **run-time package** is identified by package name **and defining loader**. Two classes in the same `package demo` but with different loaders do not automatically share package-private access. When using JPMS, you also need to check module reads, exports/opens, and module layers.

Class-loader separation is meant to manage **namespaces/dependencies and versions**; it is not inherently a sandbox with separate security permissions toward the operating system or JVM resources.

## 4. What Does Redefinition Actually Replace?

Standard API in `java.lang.instrument.Instrumentation`:

```java
// Fragment: instrumentation has type java.lang.instrument.Instrumentation.
Class<?> target = Service.class;
byte[] candidateBytes = Files.readAllBytes(candidatePath);
instrumentation.redefineClasses(
        new ClassDefinition(target, candidateBytes));
```

This is **only a fragment**; it requires importing `ClassDefinition`, `Files` and declaring `Service`, `candidatePath`. `ClassDefinition` binds **the exact target runtime Class** to the replacement **class-file bytes**. You do not use `ClassLoader.defineClass` to overwrite an existing definition in the same namespace.

### 4.1. Behaviors explicitly stated in the Javadoc

1. **New method invocations** after success use the new bytecode of the redefined method.
2. **Active stack frames** (already entered into the method before redefinition) continue running the **old** bytecode for that invocation. The program counter is not automatically jumped mid-method to the new version.
3. **Existing instances** are not destroyed, do not change class identity, and do not have their fields reset.
4. **Static fields** retain their current values. Replacing `<clinit>` bytecode does not cause the JVM to **re-run the class initializer** merely because of redefinition.
5. **Constructors** are not re-invoked on existing objects. If a constructor body changes within valid bounds, subsequent new object creations may be affected.
6. Redefinition **does not automatically roll back** side effects that have already occurred: replacing code does not restore databases, external messages, static caches, or object data.
7. `redefineClasses` can process **a set of ClassDefinitions** for interdependent changes; read the JVM's error/transaction contract rather than assuming all schemas are supported.

### 4.2. Schema restrictions

On common JVM/JVMTI implementations, you can change method bodies and some matching constant-pool/attributes, but **you cannot freely**:

- Add, remove, or rename fields/methods.
- Change descriptors/signatures and the superclass/interfaces structure.
- Change constrained metadata/hierarchy structures, such as nest relationships.
- Supply a class-file version or bytecode verification not supported by the VM.

Restrictions must be verified against the **VM/vendor/version**. Complex schema changes should usually load a new class via a new loader or restart the process. Do not treat success in a debug environment as a guarantee of compatibility across all JVMs.

Checking capability:

```java
// Fragment: inst, clazz must be declared in the program.
boolean supported = inst.isRedefineClassesSupported();
boolean modifiable = inst.isModifiableClass(clazz);
```

A Java agent requests `Can-Redefine-Classes: true` in its manifest; **this flag is not sufficient** if the VM does not provide the capability. Possible errors include `UnmodifiableClassException`, `UnsupportedOperationException`, `ClassFormatError`, `NoClassDefFoundError`, or `UnsupportedClassVersionError`, depending on the cause.

### 4.3. Redefinition vs. retransformation

`redefineClasses` is supplied with **complete new bytes** for a loaded class. `retransformClasses` asks the VM to re-run the **transformer pipeline** starting from the initial class bytes according to `ClassFileTransformer` rules. The two paths have distinct mechanisms, but both target the **existing class identity**. If the goal is to maintain two versions with the same name running side by side for different new calls, a single redefine on the same runtime class does not provide that.

## 5. What Does a New Class Loader Actually Create?

`URLClassLoader` can load `demo.VersionedService` V2 from a new directory, even while V1 is running in another loader. It defines a **new class**; it does not "patch" V1.

Consequences:

- **V1 objects remain V1**; calls through those objects do not change merely because V2 was created.
- **New V2 objects** run V2 code and have V2 class identity.
- Each class has its **own static state and class initialization**.
- An object from V1 cannot be cast to V2 merely because their `Class.getName()` values are identical.
- V2 can introduce a different schema, but external callers must use a compatible shared interface/protocol.
- You must **switch references or route** to V2. Without switching, clients still use V1.
- Class V1 and loader V1 can be kept alive by callbacks, threads, `ThreadLocal`, static registries, reflection caches, and the object graph.

### 5.1. Why can creating a new loader still return V1?

Illustrative example:

```java
// Fragment, URL object and classpath need to be set up beforehand.
URLClassLoader child = new URLClassLoader(
        new URL[] {newVersionUrl});
Class<?> type = child.loadClass("demo.VersionedService");
```

This constructor uses the system loader as its parent by default. If the parent already knows `demo.VersionedService` V1, `child.loadClass` can **delegate** and return V1 itself. Thus, the label "new loader" is not enough; check:

```java
// Fragment.
System.out.println(type.getClassLoader() == child);
```

If `false`, the runtime class was created by another defining loader (usually the parent). Do not enable child-first arbitrarily for all of the JDK/framework: improper class-loading configuration can cause `LinkageError` and type compatibility errors.

## 6. Java 17+ Lab: Same V1/V2 Class, Two Independent Techniques

Directory structure:

```text
hot-reload-lab/
├── agent.mf
├── src/
│   └── demo/
│       ├── VersionedService.java       (V1)
│       ├── RedefineAgent.java
│       ├── MainRedefine.java
│       └── MainLoaders.java
├── next-src/
│   └── demo/
│       └── VersionedService.java       (V2)
├── out/                                (created on build)
└── replacement/                        (created on build)
```

The key point is that **the two source files with the same package/name must be compiled separately**, not passed together in a single `javac` command. JDK 17+ containing `javac`, `java`, and `jar` is required. ASM/Maven are not needed.

### 6.1. V1 — `src/demo/VersionedService.java`

```java
package demo;

public final class VersionedService {
    public static int counter = 1;

    public String message() {
        return "v1";
    }
}
```

### 6.2. V2 — `next-src/demo/VersionedService.java`

```java
package demo;

public final class VersionedService {
    public static int counter = 100;

    public String message() {
        return "v2";
    }
}
```

Both class files keep the **same name, fields, default constructor, and method descriptor**, changing only the method body and the value written by the static initializer. This allows us to prove:

- With **redefine**, the existing static value is preserved instead of being re-initialized to 100.
- With a **new loader**, V1 and V2 are initialized separately; V2 can start with `counter=100`.

## 7. Experiment A: Replacing the Body on a Running Class

### 7.1. Agent — `src/demo/RedefineAgent.java`

```java
package demo;

import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;

public final class RedefineAgent {
    private static volatile Instrumentation instrumentation;

    private RedefineAgent() {}

    public static void premain(String args, Instrumentation inst) {
        instrumentation = inst;
    }

    public static void replace(Class<?> clazz, Path classFile)
            throws Exception {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("Start with -javaagent");
        }
        if (!inst.isRedefineClassesSupported()) {
            throw new IllegalStateException("Redefinition not supported");
        }
        if (!inst.isModifiableClass(clazz)) {
            throw new IllegalStateException("Class not modifiable");
        }

        byte[] replacement = Files.readAllBytes(classFile);
        inst.redefineClasses(new ClassDefinition(clazz, replacement));
    }
}
```

The agent receives `Instrumentation` via `premain` when the JVM starts. We use **startup `-javaagent`**, not dynamic attach, so the example does not depend on attach/self-attach permissions or post-startup agent-loading policies. The `classFile` path must point to valid bytes of **`demo.VersionedService` itself**, not mistakenly a different class name.

### 7.2. Main — `src/demo/MainRedefine.java`

```java
package demo;

import java.nio.file.Path;

public final class MainRedefine {
    private MainRedefine() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: MainRedefine <replacement-class-file>");
        }

        VersionedService original = new VersionedService();
        Class<?> before = original.getClass();

        System.out.println("BEFORE=" + original.message());

        VersionedService.counter = 7;
        System.out.println("STATE_BEFORE="
                + VersionedService.counter);

        RedefineAgent.replace(before, Path.of(args[0]));

        System.out.println("SAME_CLASS="
                + (before == original.getClass()));
        System.out.println("AFTER=" + original.message());
        System.out.println("STATE_AFTER="
                + VersionedService.counter);
    }
}
```

`original` is created **once before** redefinition takes place. The `message` method is called a second time **on that exact same object**. `Class<?> before` is a reference to the identity of the loaded class, not a snapshot of the method body.

### 7.3. Agent manifest — `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: demo.RedefineAgent
Can-Redefine-Classes: true
```

The manifest file must have a trailing newline. `Can-Redefine-Classes: true` requests the capability; if the VM does not support it, the code reports an error via `isRedefineClassesSupported()` instead of silently claiming success.

### 7.4. Build commands

In the `hot-reload-lab` directory, create the two output directories if they do not exist yet (on PowerShell you can use `New-Item -ItemType Directory -Force out,replacement`; on Linux/macOS you can use `mkdir -p out replacement`).

```bash
javac --release 17 -d out src/demo/VersionedService.java src/demo/RedefineAgent.java src/demo/MainRedefine.java
javac --release 17 -d replacement next-src/demo/VersionedService.java
jar --create --file redefine-agent.jar --manifest agent.mf -C out demo/RedefineAgent.class
```

The two compiler invocations produce:

```text
out/demo/VersionedService.class          (V1)
replacement/demo/VersionedService.class  (V2)
redefine-agent.jar                       (startup agent)
```

Using `--release 17` for both reduces the chance of failure due to the candidate class file exceeding the JVM's class-file version. The build **does not** overwrite V1 with V2.

### 7.5. Running redefinition

```bash
java -javaagent:redefine-agent.jar -cp out demo.MainRedefine replacement/demo/VersionedService.class
```

On HotSpot/JDK supporting redefinition, with the exact project and source above, stdout is **expected to be**:

```text
BEFORE=v1
STATE_BEFORE=7
SAME_CLASS=true
AFTER=v2
STATE_AFTER=7
```

- `BEFORE=v1`: the object runs the V1 method.
- `STATE_BEFORE=7`: the code modifies the static counter.
- `SAME_CLASS=true`: the `Class<?>` identity **is not replaced**.
- `AFTER=v2`: **the same old object** receives the new method body on the next invocation.
- `STATE_AFTER=7`: the JVM **does not re-run `<clinit>`** even though the V2 source declares `counter=100`.

If the VM does not support redefinition, this success output will not appear; check the actual error instead of changing the expectation to "works on every VM". The lab intentionally does not change the field/method schema and does not add a new classloader.

### 7.6. Why are active frames an important exception?

If thread A enters `service.longTask()` version V1 and has not exited yet, and thread B redefines successfully, thread A's frame continues the **V1** body for the in-flight call, while new calls after redefine use the **V2** body. Therefore, redefinition does not automatically guarantee "all threads use V2 at the exact same instant".

Timeline:

```text
T0: Thread-A enter method V1
T1: Thread-B redefine target to V2
T2: redefineClasses returns successfully
T3: Thread-C invokes method -> V2
T4: Thread-A leaves its existing frame -> V1
```

This is a **scenario diagram**, not lab output. Do not run incompatible field/lock protocol migrations while V1 active frames may still be running.

## 8. Experiment B: Loading V1 and V2 with Two Loaders

This time **do not run `-javaagent` and do not call `redefineClasses`**. We keep the same two compiled class files, but have two different loaders independently define `demo.VersionedService`. Use the **platform loader** as the parent to prevent the system/app loader on the `out` classpath from pre-loading V1 and returning it to both child loaders.

### 8.1. `src/demo/MainLoaders.java`

```java
package demo;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class MainLoaders {
    private MainLoaders() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: MainLoaders <v1-dir> <v2-dir>");
        }

        URL[] firstPath = {
                Path.of(args[0]).toAbsolutePath().toUri().toURL()
        };
        URL[] secondPath = {
                Path.of(args[1]).toAbsolutePath().toUri().toURL()
        };
        ClassLoader parent = ClassLoader.getPlatformClassLoader();

        try (URLClassLoader first = new URLClassLoader(firstPath, parent);
             URLClassLoader second = new URLClassLoader(secondPath, parent)) {

            Class<?> typeV1 = Class.forName(
                    "demo.VersionedService", true, first);
            Class<?> typeV2 = Class.forName(
                    "demo.VersionedService", true, second);

            Object objectV1 =
                    typeV1.getDeclaredConstructor().newInstance();
            Object objectV2 =
                    typeV2.getDeclaredConstructor().newInstance();

            System.out.println("SAME_NAME="
                    + typeV1.getName().equals(typeV2.getName()));
            System.out.println("SAME_CLASS=" + (typeV1 == typeV2));
            System.out.println("DIFFERENT_LOADERS="
                    + (typeV1.getClassLoader()
                            != typeV2.getClassLoader()));

            System.out.println("OLD="
                    + typeV1.getMethod("message").invoke(objectV1));
            System.out.println("NEW="
                    + typeV2.getMethod("message").invoke(objectV2));
            System.out.println("OLD_AFTER_NEW="
                    + typeV1.getMethod("message").invoke(objectV1));

            typeV1.getField("counter").setInt(null, 7);
            System.out.println("V1_COUNTER="
                    + typeV1.getField("counter").getInt(null));
            System.out.println("V2_COUNTER="
                    + typeV2.getField("counter").getInt(null));

            System.out.println("NEW_IS_OLD="
                    + typeV2.isInstance(objectV1));
            try {
                typeV2.cast(objectV1);
            } catch (ClassCastException failure) {
                System.out.println("CAST=ClassCastException");
            }
        }
    }
}
```

The lab uses reflection so as not to force the compiler to link directly against a single `VersionedService` from the app's classpath. `Class.forName(name,true,loader)` requests loading **and initializing the class** provided by the chosen loader. `getPlatformClassLoader()` is an appropriate parent for the lab because it does not see the application classes in the `out` directory.

In a real plugin system, the parent usually needs to see **shared API/SPI** rather than only platform classes; the loader arrangement here is for clearly observing class identity.

### 8.2. Compile and run

Compile `MainLoaders` after `out` and both versions exist:

```bash
javac --release 17 -d out src/demo/MainLoaders.java
java -cp out demo.MainLoaders out replacement
```

Exact stdout **with the two class versions in section 6**:

```text
SAME_NAME=true
SAME_CLASS=false
DIFFERENT_LOADERS=true
OLD=v1
NEW=v2
OLD_AFTER_NEW=v1
V1_COUNTER=7
V2_COUNTER=100
NEW_IS_OLD=false
CAST=ClassCastException
```

These lines prove several things:

- `SAME_NAME=true` yet `SAME_CLASS=false`: the same name **does not mean** the same runtime type.
- `DIFFERENT_LOADERS=true`: different defining loaders.
- `OLD_AFTER_NEW=v1`: creating the V2 class/object does not make the V1 object change behavior.
- `V1_COUNTER=7` and `V2_COUNTER=100`: static fields are independent per runtime class.
- `NEW_IS_OLD=false`: the V1 object is not an instance of the V2 type.
- `CAST=ClassCastException`: V2 does not automatically accept a V1 object even though they have the same name and method structure.

Upon exiting `try`, the two `URLClassLoader`s are `close()`d to release appropriate class-loading resources. **Closing a loader does not mean the JVM unloads the class immediately**; live class/object references can keep the loader alive.

### 8.3. Reviewing the difference between the two stdouts

| Experiment A | Experiment B |
| --- | --- |
| `SAME_CLASS=true` | `SAME_CLASS=false` |
| `AFTER=v2` on **old object** | `OLD_AFTER_NEW=v1` on **old object** |
| `STATE_AFTER=7` even though V2 declares 100 | `V2_COUNTER=100` because V2 class initializes separately |
| No cast error because it is still one identity | `CAST=ClassCastException` due to two different identities |
| Requires redefine capability | Does not require instrumentation capability |

This very comparison is a better check than merely hashing the two `.class` files or only inspecting `Class.getName()`.

## 9. Keeping a Shared API When Loading a New Version

A plugin system that wants V1 and V2 to both communicate with the application should clearly define **class-loader boundaries**. Common pattern:

```text
Parent/shared loader:
    interface Handler {
        Response handle(Request request);
    }
    Handler active;

Child loader V1:
    class HandlerV1 implements Handler

Child loader V2:
    class HandlerV2 implements Handler
```

This is **architectural pseudocode**, not runnable Java source: `Handler`, `Response`, and `Request` need full definitions. The critical condition is that both implementations actually implement **the same runtime `Handler` interface defined by the parent**, not each plugin defining its own copy with the same name in the child loader.

If method signatures reference DTOs defined separately by each child, **loading constraints** and runtime types can become incompatible. The system may throw `ClassCastException` or `LinkageError: loader constraint violation`. Do not work around this by casting blindly or copying bytes into the same package name; design shared API ownership instead.

### 9.1. Switching routes via a shared reference

A suitable design for a request boundary:

```text
AtomicReference<Handler> active
       │
  Request 1 gets HandlerV1 ──► processed completely on V1
       │
  Deploy V2 / health-check / active.set(V2)
       │
  Request 2 gets HandlerV2 ──► processed completely on V2
```

Java fragment:

```java
// Fragment: active, Handler, Request/Response already declared.
Handler selected = active.get();
Response response = selected.handle(request);

// After V2 has initialized and passed checks:
active.set(newHandlerV2);
```

`AtomicReference.set` publishes the new binding but does not automatically migrate state, close V1 resources, wait for old requests, or guarantee that a transaction is processed on a single version. A real-world procedure requires graceful draining and tracking which version is processing each request.

### 9.2. When to choose a new loader?

- You want to run **V1 and V2 side by side** in the same JVM (canary, multi-tenant, blue/green plugin).
- You need to **add fields/methods or change class structure** that normal redefinition forbids.
- You need to isolate dependency versions between modules/plugin instances.
- You have a stable shared SPI along with a process for creating new objects, switching routes, and cleaning up.

Trade-off: you must manage multiple object graphs, classloaders, static caches, resources, compatibility, and memory.

## 10. Lifecycle and Memory Leaks When Reloading a Class Loader

There is no Java SE command that guarantees "unload class V1 immediately". A class can only be reclaimed when its loader and related references become eligible for GC, depending on the VM.

Common sources retaining loader V1:

- A static registry in the parent loader still holds a V1 instance or `Class<?>`.
- A thread, `ThreadLocal`, or executor task still holds a V1 object/TCCL.
- Unregistered timers, listeners, callbacks, schedulers, and shutdown hooks.
- Framework/DI caches storing `Class`, `Method`, `MethodHandle`, constructors, annotations.
- JDBC driver/logging/metrics/tracing libraries holding references or threads created by the plugin.
- ClassLoader-to-class references, JNI/native global refs, resource URLs, or unmanaged file handles.

`URLClassLoader.close()` helps close file handles/JAR access; it **does not clear all Java references** and does not guarantee GC. Repeated plugin reloads can grow metaspace/heap if old loaders remain reachable.

A safe handover typically:

1. Creates and verifies V2.
2. Initializes dependencies/health checks.
3. Switches routes in a controlled manner.
4. Blocks new requests to V1 and lets old requests finish.
5. Unregisters callbacks/listeners, stops threads, closes resources.
6. Clears strong references/caches in the parent and TCCL.
7. Closes the old loader when appropriate, observing class unloading/metaspace.
8. Maintains a rollback policy for state and external side effects.

**A new loader is not restricted execution privileges**: the same JVM still shares process memory, OS credentials, filesystem, and many underlying resources. Do not use it as a replacement for a security sandbox.

## 11. Modifying Code While Multiple Threads Are Running

Both redefinition and loader switching have **time overlap**:

### 11.1. With redefinition

```text
T0: Thread A enters Service.longTask V1
T1: Thread B redefines Service to V2
T2: redefineClasses succeeds
T3: Thread C calls Service.longTask => V2
T4: Thread A finishes its running frame => V1
```

The `Instrumentation` Javadoc specifies that active stack frames continue using the old bytecode. Therefore, V1/V2 code can coexist in execution during the transition window, even though there is a single runtime Class identity.

### 11.2. With a new loader

```text
T0: Request A gets handler V1
T1: Load V2, create V2 object
T2: Router switches active reference to V2
T3: Request B gets V2
T4: Request A completes using V1
```

Here you can **actively** control per-request routing/draining. However, you still need to handle shared state and side effects while V1/V2 are active simultaneously.

### 11.3. Static state vs. external data

Redefinition preserves static field values **within the same class**. A new loader has separate static fields. Yet both can still write to **the same database table**, message topic, or static registry residing in **a parent-loader class**. Separating class identity does not automatically separate side effects or external state.

## 12. Rollback and Operational Choices

**Redefinition rollback:** if you keep the V1 bytes and the JVM still supports it, you can redefine the same class back to the V1 method body. However, **state fields and out-of-process changes** do not automatically revert. V2 frames already active before the rollback may continue running V2 code.

**New-loader rollback:** if the V1 instance/loader is still alive, you can switch the route back to V1; or create a new loader from V1 artifacts. However, it does not undo data/side effects already executed by V2, and does not automatically stop V2 from processing in-flight requests.

**Rolling restart/process replacement** is usually preferable if large changes touch schemas, native libraries, global singletons, JPMS module boundaries, or when old code lifecycles cannot be managed. "No restart" does not mean "low risk".

### Practical choice matrix

| Need | Preferred approach |
| --- | --- |
| Small fix to a method for debugging/instrumentation | Redefinition (if supported by the VM) |
| Adding new fields/methods or changing public API | New loader or rolling restart |
| Running V1/V2 simultaneously for tenant A/B | New loader with version routing |
| Keeping the same objects and old state | Redefinition; but must ensure V2 understands the current state |
| Isolating two versions of a dependency/plugin | Controlled class-loader isolation |
| Updating an application with complex shared state and native resources | Process restart/rolling deployment |
| Safe rollback with database migrations | Requires independent migration/rollback; no Java technique solves this automatically |

## 13. Typical Errors and Diagnostic Guide

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| `isRedefineClassesSupported() == false` | VM/manifest does not grant capability | Check agent manifest, runtime vendor, VM flags |
| `UnmodifiableClassException` | Target class is not modifiable | `isModifiableClass(clazz)` and target kind |
| `UnsupportedOperationException` | Unsupported schema/capability | Compare fields/method names/descriptors, hierarchy |
| `ClassFormatError` | Invalid replacement file | `javap -v`, compiler output, inspect class bytes |
| `NoClassDefFoundError` on redefine | Candidate binary name differs from target | Compare `this_class` of the class file |
| `UnsupportedClassVersionError` | Candidate built with too new a JDK | `javac --release` matching target |
| V2 method is not called | Redefinition did not succeed, wrong target class/loader, or still in a V1 active frame | Log exact Class identity and timestamp |
| Static value does not become 100 after redefine | Expected semantics: `<clinit>` does not re-run | Design separate state migration |
| New loader but class is still V1 | Parent delegation already returned V1 | Compare `getClassLoader()` with expected loader |
| `ClassCastException` with same class name | Different defining loaders | Design shared SPI/DTO |
| `LinkageError` / loader constraint | Dependency type names point to different identities | Check owner loader of interface/DTO/dependencies |
| Old loader does not unload | Strong refs, threads, TCCL, listeners, caches | Cleanup, heap dump, class loading diagnostics |
| App still calls V1 object after loading V2 | Router/reference has not been switched | Check binding and request-scoped selection |
| V2 needs a new field but redefine is rejected | Schema change beyond `RedefineClasses` capability | New loader or process deployment |
| Hot swap causes inconsistent results | Overlapping V1 frames and V2 calls, incompatible state | Test concurrent transition, draining/quiescence |

Do not confuse `ClassNotFoundException` (loader cannot find the class), `NoClassDefFoundError` (link/definition error), `ClassCastException` (type identity incompatibility), and `UnsupportedOperationException` (change not supported by the JVM). Each requires a different remedy.

## 14. Testing Checklist

- [ ] Identified the **exact goal**: same runtime class or new runtime class identity?
- [ ] For redefine: have `Can-Redefine-Classes: true`, `isRedefineClassesSupported()`, and `isModifiableClass()`.
- [ ] Candidate V2 bytes have the same binary name, classfile version, and schema allowed by the VM.
- [ ] Compared behavior on the **same existing instance before and after** redefinition.
- [ ] Confirmed static state is not reset and `<clinit>` does not re-run automatically.
- [ ] Tested active frames, locking, and state compatibility when V1/V2 code can overlap.
- [ ] For a new loader: checked the **defining loader**, not just the loader name or binary class name.
- [ ] Tested `classV1 == classV2` and `classV2.isInstance(objectV1)`.
- [ ] Tested shared interface/DTO types from the parent, class-loader constraints, and JPMS access.
- [ ] If switching plugins, created a V2 object and switched the route explicitly, without assuming V1 objects change type automatically.
- [ ] Cleaned up V1 threads/TCCL, callbacks, caches, listeners, and resources.
- [ ] Observed metaspace/classloading after multiple reloads to detect leaks.
- [ ] Have a rollback policy for **code and data**; rolling back code does not roll back the database.
- [ ] Compared outputs and exceptions across multiple inputs; do not only compare SHA-256 of `.class` files.
- [ ] For major structural changes, consider a rolling restart instead of forcing redefinition.

## 15. Self-Check

1. **Two `Class<?>` objects have the same `getName()` but different `getClassLoader()`. Are they definitely the same runtime type?**  
   No. The name is not enough; the defining loader is part of class identity.

2. **After successfully modifying `message()` via redefinition, does an old V1 object need to be recreated to return V2?**  
   No. New calls reach the V2 method body on the old object.

3. **V1's static counter was 7, and V2's source assigns 100. After redefine it is still 7—is that a bug?**  
   No. Replacing a class definition does not re-run `<clinit>`.

4. **Loaded V2 with loader B and then called the method on a V1 object. Why is it still V1?**  
   Because the V1 object still belongs to loader A's V1 class; its identity was not changed.

5. **Do two different URLClassLoaders always return two different Class objects?**  
   No. Both can delegate to the same parent loader; you must check the defining loader.

6. **V2 adds a method or field. Is redefinition guaranteed to allow it?**  
   No. Structural changes are usually outside the supported scope. A new loader creates a new runtime type if the ABI is designed appropriately.

7. **Is an active V1 stack frame automatically switched to the V2 body after redefine?**  
   No. The Javadoc states that already-running frames continue with the old bytes; new invocations use the new version.

8. **Why can `typeV2.cast(objectV1)` throw `ClassCastException` even when `getName` is identical?**  
   Because the two runtime class identities are different.

9. **Does closing a `URLClassLoader` unload the class immediately?**  
   No. It depends on remaining references and GC behavior; `close()` does not force unloading.

10. **To have both V1 and V2 implement the same `Handler`, where must the interface be placed?**  
    In the shared parent loader so that the same runtime interface is used, without creating duplicate types in children.

11. **Need canarying by tenant A/B—does redefining a single class create per-tenant versions?**  
    No. New loader identities and routing are more appropriate.

12. **Does rolling back the V2 body to V1 automatically reverse all DB writes made by V2?**  
    No. A separate data migration/compensation plan is needed.

13. **Are redefinition and retransformation the same as loading a class with a new loader?**  
    No. Both redefine and retransform target the definition of an already-loaded class; a new loader creates a new identity when defining a class independently.

14. **Why must concurrent state be checked when active V1 frames and V2 calls overlap?**  
    Because lock expectations, field invariants, and external protocols within the same process may differ.

## 16. Official Documentation

- Oracle JDK 17 — **`Instrumentation`, `redefineClasses`, capability, state, and active frames**: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- Oracle JDK 17 — **`ClassDefinition`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html
- Oracle JDK 17 — **`java.lang.instrument` package**, `Premain-Class` and `Can-Redefine-Classes`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
- JVMS 17 — **Chapter 5: Loading, Linking, and Initializing**, identity by binary name + defining loader: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
- Oracle JDK 17 — **`ClassLoader`**, parent delegation and platform loader: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Oracle JDK 17 — **`URLClassLoader`**, URL classpaths and `close()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- Oracle JDK 17 — **`Class`**, `getName()`, `getClassLoader()`, `isInstance`, and `cast`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- JVM TI — **`RedefineClasses`** schema restrictions and method activation behavior: https://docs.oracle.com/javase/8/docs/platform/jvmti/jvmti.html#RedefineClasses

**Key takeaway:** When you need to preserve objects/class identity and only replace method implementations within VM-allowed bounds, consider **`redefineClasses`**. When you need to run multiple versions side by side, change schemas, or replace an entire plugin lifecycle, you need **a new defining class loader + V2 instances + an explicit routing mechanism**. In both approaches, verify active calls, state, and rollback capability rather than only confirming that the V2 class file was read.
