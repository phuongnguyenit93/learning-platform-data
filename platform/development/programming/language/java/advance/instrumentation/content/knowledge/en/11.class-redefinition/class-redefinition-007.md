# Active Invocations Differ from Invocations Started After Redefinition

## 1. The Problem: Changing a Method Definition While the JVM Is Running

Suppose a JVM is serving requests. Thread A has entered `Service.work()` and is still executing. At the same time, a Java agent calls `Instrumentation.redefineClasses(...)`, supplying a new classfile with a modified `work()` body. Does Thread A jump from the old code to the new code? Which code will a `work()` invocation created after the redefinition run?

**Core rule of Java Instrumentation:** When a redefined method has **active stack frames**, those frames **continue executing the bytecode of the old method version**. **New method invocations** after the new definition is installed use the **new method body**. This is the contract of `Instrumentation.redefineClasses` in Java SE 17, not merely an accidental side effect of `Thread.sleep` or JIT.

This Knowledge article focuses on the difference between an **active invocation** and an **invocation started after redefinition**, while answering related questions:

- Do “old” and “new” describe the **method body** version, or the **object** version?
- Is it necessary to create `new Service()` for V2 code to take effect?
- Are instance fields and static fields automatically reset when a class is redefined?
- At what point is it safe to declare that V2 instrumentation is active?
- When rolling back V2 to V1, do live V2 frames have their code swapped mid-execution?
- How does redefinition differ from retransformation, class loading, and application restart?

At the end of the article is a **complete Java 17+ example**: an agent that actually calls `redefineClasses(new ClassDefinition(...))`, two versions of `HotMethod.class` with the same schema, two `CountDownLatch` instances guaranteeing ordering, the bytecode verifier, verified stdout, and follow-up exercises.

## 2. Active Frames and New Invocations Are Two Different Milestones

### 2.1. Method invocation and stack frame

Each call to a method creates a new invocation; the JVM uses a frame to hold local variables, the operand stack, and the execution state of that call. A frame can remain active even while the thread is blocked on a lock, latch, I/O, or another method call.

~~~java
void process() {
    loadOrder();
    awaitSignal();
    commitOrder();
}
~~~

This is only an **illustrative code snippet**, without definitions for `loadOrder`, `awaitSignal`, and `commitOrder`. If a thread has entered `process()` and is waiting inside `awaitSignal()`, the `process` frame **has not finished**. The invocation started before the agent replaced the definition.

### 2.2. A V1 frame does not automatically convert into a V2 frame

A `process()` V1 frame has local variables and a bytecode offset belonging to V1. If the definition is replaced while it is waiting, the JVM **does not patch the frame to resume from a corresponding offset in V2**. Although the VM may perform deoptimization or replace compiled artifacts, it preserves **V1 semantics** for the active frame.

A `process()` invocation **started after redefinition succeeds** uses the updated V2 method body. That is a different frame; it is not the V1 frame restarted.

### 2.3. One object, multiple invocation timestamps

~~~text
service = new Service();                     // Only one object

Thread A: service.work() called when class = V1
              |
              +--> frame A (V1) runs, then waits
                                           Thread B:
                                           redefineClasses(Service, V2)
                                               |
                                           redefinition succeeds
              |
Thread A:     +--> frame A continues V1 bytecode, RETURN
                                           Thread B:
                                           service.work() called again
                                               |
                                           frame B uses V2, RETURN
~~~

In both calls, `service` is the **same previously created reference**. There is no requirement to create a new object for V2 to take effect. “New” in **new invokes** refers to a **new method call**, not a **new instance**.

### 2.4. What must not be inferred?

- A successful redefine **does not mean every thread immediately runs V2**.
- An old frame continuing V1 **does not mean it holds a snapshot of old fields**.
- Both V1 and V2 can coexist in the JVM for a period of time; that is not necessarily a sign that the update failed.
- Distinguish between **having issued a redefine request** and **the API having completed successfully**.
- When an invocation starts right while the operation is executing, do not classify it using raw timestamps; use synchronization to establish before/after ordering.

## 3. The Formal Contract of redefineClasses

Java 17 API:

~~~java
void redefineClasses(ClassDefinition... definitions)
        throws ClassNotFoundException, UnmodifiableClassException;
~~~

This line is a **condensed signature for study**, not a standalone Java file. `Instrumentation` is an interface in the `java.instrument` module. A Java agent can receive an `Instrumentation` instance via `premain(String, Instrumentation)` at JVM startup, or `agentmain(String, Instrumentation)` if the JVM supports dynamic attach.

Key points of the `redefineClasses` specification:

1. Replaces the definition of **already-loaded classes** using classfile bytes supplied by the caller, without relying on the old file bytes.
2. Designed to support debugger-style hot replace or fix-and-continue changes. It can update **multiple classes** in a single call if they have mutual dependencies.
3. **Active frames** of a redefined method continue running the **original bytecodes**.
4. **New method invocations** use the redefined definition.
5. Does not re-run class initialization; **static variable values are not automatically reset**.
6. **Existing instances are not replaced** by redefinition.
7. Replacement bytes are processed and verified by the JVM and relevant transformers before installation. If the API throws an exception, **none of the classes in the requested set are redefined**.

Points 3 and 4 are the core of this article. Points 5 and 6 explain why the same instance can run V1 and then V2 while keeping its existing data.

### 3.1. What is ClassDefinition?

~~~java
new ClassDefinition(targetClass, replacementBytes)
~~~

`ClassDefinition` pairs an exact existing `Class<?>` with a `byte[]` containing the new classfile. The Java 17 documentation notes that this constructor **retains a reference to the array** rather than copying it. Therefore, do not mutate the array while the agent is using it for redefinition. The file bytes must correspond to the **exact binary name/class identity** of the target.

Do not confuse reading a `.class` file from disk with the JVM automatically reloading the class. The change only occurs when the agent actually calls `redefineClasses` and the JVM accepts it.

### 3.2. Prerequisites

~~~java
if (!inst.isRedefineClassesSupported()
        || !inst.isModifiableClass(targetClass)) {
    throw new IllegalStateException("Cannot redefine");
}

inst.redefineClasses(
        new ClassDefinition(targetClass, replacementBytes));
~~~

This is an **excerpt** with variables that must be supplied by the agent. Before using it, check:

- **`isRedefineClassesSupported()`:** the redefinition capability is configured and supported by the JVM.
- **`isModifiableClass(targetClass)`:** the specific class can be modified. Primitive classes and array classes are not modifiable; the VM may restrict other classes as well.
- **Agent manifest:** `Can-Redefine-Classes: true` in the main section.
- **Bytes:** correct class name, valid classfile version and schema, and dependencies loadable from the appropriate runtime/class loader.

`Can-Redefine-Classes` **is not** `Can-Retransform-Classes`. They are two separate capabilities.

## 4. A Verifiable Timeline

~~~text
Time         Worker thread (old frame)              Main/agent thread
---------    -------------------------              ------------------------
t0           service.work() called when V1
t1           prints OLD:entered
t2           signals ENTERED
t3           waits on RELEASE latch
t4                                                 receives ENTERED
t5                                                 prints main:before-redefine
t6                                                 reads V2 bytes
t7                                                 redefineClasses(...V2)
t8                                                 JVM verifies/installs V2
t9                                                 prints agent:redefine-ok
t10                                                prints main:after-redefine
t11                                                opens RELEASE latch
t12          V1 frame resumes, prints OLD:resumed
t13          V1 frame returns
t14                                                main calls service.work()
t15                                                new invocation runs V2
t16                                                prints NEW:invoked
~~~

At **t12**, even though V2 installation succeeded at t8, the old frame continues V1. At **t15**, that same object receives a new V2 invocation. This proves the behavior directly, rather than relying only on a callback or an agent message saying “updated”.

**CountDownLatch** establishes a deterministic happens-before ordering: the worker cannot pass t12 before main opens RELEASE, and main cannot start redefining before the worker has signaled ENTERED. Compared to `Thread.sleep(500)`, this avoids depending on machine speed, JIT, the scheduler, and GC.

## 5. Java 17+ Demo: Redefining While a V1 Frame Is Active

This example was verified on a real JVM with redefinition support. We create **two classfile versions with the same name `demo.HotMethod`**:

- **V1:** `work()` prints `OLD:entered`, waits on a latch, then prints `OLD:resumed`.
- **V2:** `work()` prints `NEW:invoked`.
- **RedefineAgent:** reads the V2 class file and calls **`Instrumentation.redefineClasses(new ClassDefinition(...))`**.
- **Main:** creates a **single `HotMethod`**, calls V1 on a worker thread, waits until the worker has entered the method, redefines to V2, lets the worker finish, and then invokes the new method.

To check state, both V1 and V2 share the same two fields: `private int count = 7` and `static int staticCounter = 100`. Main reassigns them to `9` and `777` before calling `work()`. Redefinition does not reset these fields.

### 5.1. File layout

~~~text
redefine-active-frame-lab/
├── agent.mf
├── src/
│   ├── agent/
│   │   └── demo/
│   │       └── RedefineAgent.java
│   ├── app/
│   │   └── demo/
│   │       └── Main.java
│   ├── v1/
│   │   └── demo/
│   │       └── HotMethod.java
│   └── v2/
│       └── demo/
│           └── HotMethod.java
└── out/                         # generated on build
    ├── agent/
    ├── v1/
    ├── v2/
    └── redefine-agent.jar
~~~

The two versions of `HotMethod.java` have the **same package and class name** but are compiled **separately**. When running main, **only `out/v1` is on the classpath**; the V2 file is read by the agent as replacement bytes, not loaded as a second class identity.

### 5.2. Agent: src/agent/demo/RedefineAgent.java

~~~java
package demo;

import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;

public final class RedefineAgent {
    private static Instrumentation inst;

    public static void premain(
            String options, Instrumentation instrumentation) {
        inst = instrumentation;
    }

    public static void replace(
            Class<?> type, Path classFile) throws Exception {

        if (inst == null || !inst.isRedefineClassesSupported()
                || !inst.isModifiableClass(type)) {
            throw new IllegalStateException(
                    "Redefinition unavailable");
        }

        byte[] v2 = Files.readAllBytes(classFile);

        System.out.println("agent:redefine-start");
        inst.redefineClasses(new ClassDefinition(type, v2));
        System.out.println("agent:redefine-ok");
    }
}
~~~

Explanation:

1. The JVM passes `Instrumentation` to the agent's `premain`. The experiment uses a **startup agent** to simplify setup; the **redefinition happens after the application and V1 frame are already active**.
2. `replace` checks VM and class capabilities.
3. `Files.readAllBytes` reads the pre-compiled V2 class file; it does not parse Java source at runtime.
4. `new ClassDefinition(type, v2)` targets the exact loaded class.
5. `redefineClasses` submits the bytes to the VM for verification/installation. There is no need to register a `ClassFileTransformer` for this direct replacement style.
6. `agent:redefine-ok` only appears after the API **returns normally**. If the operation fails, this line is not printed.
7. In apps with other registered transformers, those transformers may still be invoked when a class is redefined. Thus the final result also depends on the transformer chain; the demo has no extra transformers to keep behavior easy to observe.

### 5.3. Main: src/app/demo/Main.java

~~~java
package demo;

import java.nio.file.Path;
import java.util.concurrent.CountDownLatch;

public final class Main {
    static final CountDownLatch ENTERED = new CountDownLatch(1);
    static final CountDownLatch RELEASE = new CountDownLatch(1);

    public static void main(String[] args) throws Exception {
        HotMethod service = new HotMethod();
        service.setCount(9);
        HotMethod.staticCounter = 777;

        Thread oldFrame = new Thread(service::work, "v1-frame");
        oldFrame.start();

        ENTERED.await();
        System.out.println("main:before-redefine");

        try {
            RedefineAgent.replace(
                    HotMethod.class, Path.of(args[0]));
            System.out.println("main:after-redefine");
        } finally {
            RELEASE.countDown();
            oldFrame.join();
        }

        service.work();
    }
}
~~~

Explanation:

- **`service` is created only once**. Main and the worker both call methods on that exact instance.
- `ENTERED` opens only after the worker has **entered V1.work()**, ensuring it is genuinely a V1 frame.
- `RELEASE` holds the worker inside the V1 method until main performs the redefinition.
- `finally` always opens RELEASE and joins the worker so the test does not hang indefinitely if redefine throws an error.
- The final `service.work()` call runs only **after the redefine API has returned successfully** and the old worker has finished, keeping log order deterministic.
- Setting `count=9` and `staticCounter=777` before starting the worker lets us observe that both V1 and V2 see the same state.

### 5.4. V1: src/v1/demo/HotMethod.java

~~~java
package demo;

public final class HotMethod {
    static int staticCounter = 100;
    private int count = 7;

    public void setCount(int value) {
        count = value;
    }

    public void work() {
        System.out.println("OLD:entered count=" + count +
                " static=" + staticCounter);
        Main.ENTERED.countDown();

        try {
            Main.RELEASE.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return;
        }

        System.out.println("OLD:resumed count=" + count +
                " static=" + staticCounter);
    }
}
~~~

When the worker enters `work()`, it prints `OLD:entered` and then waits on `Main.RELEASE.await()`. The `work` frame **remains active** while the thread is waiting. After main replaces the definition and releases the latch, that same frame prints `OLD:resumed`, without re-invoking `work` from the start.

### 5.5. V2: src/v2/demo/HotMethod.java

~~~java
package demo;

public final class HotMethod {
    static int staticCounter = 100;
    private int count = 7;

    public void setCount(int value) {
        count = value;
    }

    public void work() {
        System.out.println("NEW:invoked count=" + count +
                " static=" + staticCounter);
    }
}
~~~

The **only intentional difference** in this example is the body of `work()`. Both classes have the same package/name, modifiers, fields, default constructor, and method descriptors. Keeping the schema identical avoids HotSwap/redefinition restrictions on adding/removing fields or methods, or changing signatures and hierarchy.

Even though the V2 source still writes `staticCounter = 100` and `count = 7`, **redefinition does not re-run `<clinit>` or the constructor**, so the stored values remain **777** and **9**.

### 5.6. Manifest: agent.mf

~~~text
Manifest-Version: 1.0
Premain-Class: demo.RedefineAgent
Can-Redefine-Classes: true

~~~

Save the file with a trailing newline; the attributes are in the **main section**. `Premain-Class` identifies the agent entry point invoked by `-javaagent`. `Can-Redefine-Classes: true` requests redefinition permission from the JVM; a JVM implementation may still not support it, so the test must check the capability at runtime.

Do not substitute `Can-Retransform-Classes: true`: that is a **different mechanism**.

### 5.7. Compiling and packaging

From the `redefine-active-frame-lab` root directory. In Bash:

~~~bash
mkdir -p out/agent out/v1 out/v2
~~~

In PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out/agent, out/v1, out/v2
~~~

Then run the JDK tools from the project root:

~~~bash
javac --release 17 -d out/agent src/agent/demo/RedefineAgent.java
javac --release 17 -cp out/agent -d out/v1 src/v1/demo/HotMethod.java src/app/demo/Main.java
javac --release 17 -d out/v2 src/v2/demo/HotMethod.java
jar --create --file out/redefine-agent.jar --manifest agent.mf -C out/agent .
~~~

Why this exact order:

1. `RedefineAgent` must be compiled first so `Main` can reference it.
2. `Main` and V1 `HotMethod` are built into `out/v1`.
3. V2 `HotMethod` is built into `out/v2` **separately**, avoiding overwriting V1.
4. The agent JAR contains the `RedefineAgent` class and the manifest, without V1/V2 `HotMethod`.
5. `--release 17` ensures the classfile targets Java 17 and APIs used in the source stay within release 17.

You can verify with:

~~~bash
jar --list --file out/redefine-agent.jar
javap -p -s -classpath out/v1 demo.HotMethod
javap -p -s -classpath out/v2 demo.HotMethod
javap -c -p -classpath out/v1 demo.HotMethod
javap -c -p -classpath out/v2 demo.HotMethod
~~~

In the `javap` output, check that both versions have the same `work()V` and `setCount(I)V` methods, while the `work` body differs. Do not put `out/v2` on the classpath when running the target.

### 5.8. Running the application and observing the exact output

~~~bash
java -Xverify:all -javaagent:out/redefine-agent.jar -cp out/v1 demo.Main out/v2/demo/HotMethod.class
~~~

This command uses a single JVM:

- The agent is loaded at startup to obtain `Instrumentation`, but **does not call redefine in `premain`**.
- The application uses V1 from `out/v1`, creates an instance, runs the V1 worker, and then calls the agent to redefine.
- The `out/v2/demo/HotMethod.class` file is read as **new bytecode**, without causing the JVM to load a separate class identity.
- `-Xverify:all` enables strict bytecode verification in the test environment.

**Stdout verified on a real JVM when the redefinition capability is supported:**

~~~text
OLD:entered count=9 static=777
main:before-redefine
agent:redefine-start
agent:redefine-ok
main:after-redefine
OLD:resumed count=9 static=777
NEW:invoked count=9 static=777
~~~

If the API is disallowed, V2 has an invalid schema/format, or the file is not found, the program will throw an error instead of producing the successful output sequence above. Compare the **target JVM's log** and exception if the result differs.

### 5.9. What proves the lesson?

| Stdout line | Emitted from | Conclusion |
|---|---|---|
| `OLD:entered count=9 static=777` | Worker entering V1 `work()` | The V1 frame started before redefinition |
| `main:before-redefine` | Main after receiving ENTERED | Worker has entered the V1 frame and is waiting |
| `agent:redefine-start` | Agent before the API call | Starting definition replacement |
| `agent:redefine-ok` | Agent after the API call returns | The JVM accepted the redefine operation |
| `main:after-redefine` | Main | Main continues after the update |
| `OLD:resumed count=9 static=777` | **Pre-existing V1 frame** | Even though the class was updated, the old frame still runs V1 bytecode |
| `NEW:invoked count=9 static=777` | **New invocation on the same service** | V2 method is used for the new invocation; state is not reset |

In particular, V2 **does not contain** the print statement for `OLD:resumed`. That line appearing after a successful redefinition proves that the old V1 frame really was allowed by the JVM to continue running.

## 6. Old Bytecode Does Not Mean Old Data

An active V1 frame keeps the **V1 method bytecode version**, but field reads in V1 still reference **existing object and static variables**. If another thread writes a field after redefinition, the old frame can read the new value, subject to the **Java Memory Model / happens-before**.

Example:

~~~text
V1 frame waiting, object.count = 9
main redefines method -> V2
main updates object.count = 41 (with proper synchronization)
V1 frame resumes and reads object.count -> may read 41
new V2 invocation also reads the same object.count
~~~

**Method version and data version are two independent axes.** What `redefineClasses` does not do is reset state or run initializers. It does not freeze an object's state as of the moment the frame started.

In the demo, main assigns `count=9` and `staticCounter=777` **before creating the worker**, so both calls see those values. `CountDownLatch` guarantees thread ordering in the experiment.

### 6.1. New invocation on an old instance

A self-check is to add:

~~~java
System.out.println(service == originalService);
~~~

This is an **excerpt**, requiring an `originalService` variable of the same type and scope in the application. The result will be true if it is just an alias of `service`; no new instance is needed for the V2 method definition to take effect.

The class identity of `HotMethod.class` is also preserved. Redefinition **is not like** creating a new `URLClassLoader` to load a class with the same name.

### 6.2. An old caller frame can invoke a new callee version

An important nuance: if caller `process()` started in V1, but after waking up it **makes a new invocation** of `helper()` which has been redefined to V2, the new `helper` frame can run V2. Therefore, within **a single request**, the stack can contain a V1 frame and a V2 frame at the same time.

Do not interpret “old frames continue old code” as “every method an old request calls later is also locked to V1”. The guarantee boundary is **per method invocation**, not the entire request as a system-wide consistent snapshot.

## 7. Two Method Versions Can Coexist Simultaneously

In the demo, `join` lets the V1 frame finish before main creates the V2 invocation so the log is easy to read. However, if main calls `service.work()` right after `agent:redefine-ok`, **before releasing the V1 worker**, there will be a moment where:

~~~text
Worker thread: HotMethod.work() frame from V1 -> still waiting on RELEASE
Main thread:   new V2 HotMethod.work() frame -> prints NEW:invoked
~~~

Same object, same `Class<?>`, yet **two stack frames created at two different times**. No second class loader and no second JVM are needed.

### 7.1. Multiple consecutive redefinitions

If you update **V1 → V2 → V3**, there can simultaneously be:

- a very long-running frame that entered V1 before the first update;
- a frame that entered V2 after the first update;
- a new invocation after the second update running V3.

There is no default mechanism forcing all three frames to switch to V3 immediately. This is why hotfixes can create a **multi-version transition period** even when the definition update succeeds.

### 7.2. Rollback also does not force frames back to the old version

Suppose after V2 you call redefine to restore V1. **New invocations after the rollback** use V1, but **active V2 frames** created before the rollback continue running V2. This can cause “NEW” logs to appear after the rollback timestamp, without necessarily meaning the rollback failed to apply.

To restore a definition, you must **supply the V1 bytes and call `redefineClasses` again**; disabling the agent or removing a transformer does not automatically revert an already-installed method body.

## 8. Redefine vs. Retransformation, Reload, and Restart

| Mechanism | Bytecode input | Active frames | New invokes | State/identity |
|---|---|---|---|---|
| `redefineClasses` | `ClassDefinition(Class, byte[])` supplied by the tool | Continue old method bytecodes | Use redefined method if successful | Preserves class identity and object state |
| `retransformClasses` | Re-runs the transformation pipeline for loaded classes | Continue old method bytecodes | Use retransformed method if successful | Preserves identity/state |
| Loading same-named class with another loader | Loader defines a different class identity | Frames of old identity do not auto-switch | Depends on the class identity/reference invoked | Can have two class types with the same name that are not identical |
| Restart JVM | Reloads application in a new process | Old frames belong to the terminated process | Runs version from the new process | In-memory state usually must be rebuilt |

Both Instrumentation APIs share the **old active frame / new invoke** rule, but have **different byte sources and workflows**:

- **Redefine**: you supply the replacement classfile, suitable for debugger/hot replace of compiled code. Capability is `Can-Redefine-Classes: true`.
- **Retransform**: the VM re-runs the relevant transformers; suitable when you want to instrument already-loaded classes. Capability is `Can-Retransform-Classes: true`.

Do not assume that changing a `.class` file on disk and calling `retransformClasses` will make the JVM read that file automatically. If you want to use pre-compiled replacement bytes, `redefineClasses` expresses that intent directly.

**Do not confuse with `ClassLoader.defineClass`**: an already-loaded class cannot be “overwritten” simply by loading a class of the same name in the current loader.

## 9. Schema Limits and Classfile Integrity

Redefinition in a live JVM must preserve constraints compatible with existing instances, call sites, vtables, and layouts. By default, the JVM does not allow arbitrary changes to field/method counts or superclass simply by supplying a different classfile.

Safe V2 example for the lab:

~~~text
V1 HotMethod:
  static int staticCounter
  int count
  void setCount(int)
  void work() { ... OLD ... }

V2 HotMethod:
  static int staticCounter
  int count
  void setCount(int)
  void work() { ... NEW ... }

==> Same class schema, only the body of work() changes
~~~

If you add a `private String newField` field **only in V2**, common JVMs such as HotSpot may reject it because schema changes are unsupported. If you change the binary class name in the classfile, `NoClassDefFoundError` may occur. If the classfile major version exceeds the target JDK, `UnsupportedClassVersionError` may occur. If the bytes are invalid, `ClassFormatError`, `VerifyError`, or `LinkageError` may occur accordingly.

### 9.1. Data to check before redefining

- Binary class name, defining class loader, and module.
- Major/minor version of the V1/V2 classfile.
- Field/method names, descriptors, and access flags within what the VM permits.
- Superclass and interfaces.
- Stack map frames and bytecode verification.
- Dependencies/helper classes called from V2 being available in the target runtime.
- Static/instance data types that V2 code will read on objects originating from V1.
- If multiple agents exist, the transformer chain may transform replacement bytes before the VM installs them.

### 9.2. Failures when updating a multi-class set

`redefineClasses` allows passing **multiple `ClassDefinition`s** in a single call when mutually dependent classes need to be updated together:

~~~java
inst.redefineClasses(
        new ClassDefinition(First.class, firstBytes),
        new ClassDefinition(Second.class, secondBytes));
~~~

This is an **illustrative snippet**, with `inst`/`firstBytes`/`secondBytes` needing to be supplied. According to the Javadoc, if the call throws an exception, **none of the classes in the requested set are redefined**. However, even when a group of classes is applied successfully, **old active frames can still continue running the old code version**. “Installing definitions together” does not mean “every thread has the same code version for the entire request”.

## 10. Common Errors and How to Identify Them

| Symptom | Common cause | How to verify and handle |
|---|---|---|
| `isRedefineClassesSupported()==false` | VM or manifest does not allow redefinition | Check `Can-Redefine-Classes: true` in the agent JAR and runtime configuration |
| `isModifiableClass(target)==false` | Specific class cannot be modified | Do not force replacement; choose another target or mechanism |
| `UnmodifiableClassException` | An unmodifiable class is in the set | Filter classes beforehand, manage update results |
| `UnsupportedOperationException` | VM does not support it or structural change is forbidden | Compare V1/V2 schemas, only make valid method body changes |
| `ClassFormatError` / `VerifyError` | Invalid replacement class bytes | Check `javap`, the verifier, and the bytecode generator |
| `UnsupportedClassVersionError` | Target JVM does not support V2's classfile major version | Build with the appropriate `--release` and test on the target JVM |
| `NoClassDefFoundError` | Binary name mismatch or missing dependency in the specific context | Check classfile name, loader, and full exception message |
| Worker still prints OLD after `agent:redefine-ok` | **Per contract**, old active frame keeps V1 | Use a **new invocation** to prove V2 |
| New invocation still prints OLD | Redefine failed, wrong class loader, V2 did not actually change, or class was changed again | Verify API return, replacement bytes, and class identity |
| Static field resets to an unexpected default | Agent/app code modified the field, not redefine running the initializer | Analyze side effects; do not assume state auto-resets |
| Mixed OLD/NEW logs in the same request | A V1 frame can call a newly updated V2 method | Log version markers per method or invocation |
| Still seeing NEW after rollback | An active V2 frame has not exited yet | Distinguish frame start time from rollback completion time |

**Recommendation:** do not rely solely on log completion timestamps to conclude whether a V2 method is running or not. Record when the invocation **started**, when redefinition **succeeded**, the class identity, and the probe/definition version.

## 11. Impact on Tracing, Metrics, and Hotfixes

### 11.1. Old spans may miss new telemetry

Suppose `Checkout.process()` V1 starts at t0, redefinition to V2 adding a tracing entry hook occurs at t1, and the V1 request finishes at t2. The V1 frame **does not automatically gain** the instrumentation code inserted into V2. Another request starting after t1 can record the entry span via the V2 method.

~~~text
Request A:
t0: enter Checkout.process() V1 ------------ active frame --------- t2 return
                                             ^
                                             t1 redefine to V2

Request B:
t3: enter Checkout.process() V2 --> trace hook --> business code --> return
~~~

Do not treat a missing span on Request A as an exporter bug just because the request completed after t1. Verify whether the request started before or after the cutover; also check that deeper methods invoked after the cutover may use the new code.

### 11.2. Hotfix code must tolerate old state

A V2 method can run on an **instance initialized by a V1 constructor**. If V2 expects new data that does not exist or an incompatible new protocol, business errors can still occur even if the classfile is valid and redefinition succeeds.

When changing business behavior, do not only test `java -Xverify:all`. Run integration tests and scenarios where **old running code ↔ newly installed code** interact, especially with transactions, database state, queue consumers, caches, or long-running tasks.

### 11.3. No constant-latency guarantee

The VM may need safepoints, handshakes, deoptimization, or compiled-code invalidation depending on the implementation to preserve semantics. The API does not guarantee that `redefineClasses` is always fast or completely pause-free.

Measure in practice:

- `redefineClasses` duration and failure count;
- request p95/p99 during the update window;
- CPU, allocation/GC, JIT/deoptimization;
- number of target classes/loaders and lifetime of old frames;
- number of new requests properly instrumented and telemetry drops;
- helper method risks if V2 calls into a library not visible from the target class loader.

## 12. Common Misconceptions

**“Once redefined, all threads immediately run V2.”** False. Only **new** invocations use the new definition. Active frames from V1 continue V1.

**“A V1 object will always run V1 methods.”** False. An old object can receive new invocations and run V2. No new object needs to be created.

**“A V1 frame freezes data as well.”** False. V1 bytecode can still read current fields according to synchronization/JMM.

**“V2 source has a field initializer, so redefine will reset the field.”** False. Redefinition does not re-run constructors/`<clinit>` just because replacement bytes are installed.

**“Writing the V2 .class file to disk is enough.”** False. You need `ClassDefinition` and `redefineClasses`.

**“If Can-Retransform-Classes=true, redefine will definitely work.”** False. You must separately check `Can-Redefine-Classes` and `isRedefineClassesSupported()`.

**“Same binary name means same class.”** False if the classes are defined by different class loaders. Use the exact `Class<?>`, not just a name comparison.

**“A single successful redefine can change any class layout.”** False. Schema changes have limits.

**“Just counting transformer callbacks tells you V2 is installed.”** False. You need the API to complete and to test a **new invocation**.

**“Rollback immediately reverts all V2 frames to V1.”** False. Active V2 frames may still be alive; only new invocations after the rollback use the restored definition.

## 13. Practice Exercises

### Exercise A — predict the output

Before running the demo, write down the exact order of the seven stdout lines. Explain why `OLD:resumed` appears **after** `agent:redefine-ok` yet is still OLD.

**Answer:** the worker frame started V1 before redefinition; when the latch opens, it **resumes V1** rather than creating a V2 invocation. Only the new call at the end of `Main` runs V2.

### Exercise B — run V1 and V2 at the same time

Move main's `service.work()` call to **right after `main:after-redefine` but before `RELEASE.countDown()`** (adjusting `try/finally`). Because the V2 body does not wait on the latch, it can print NEW while the V1 worker is still blocked. Why does this not require a new class loader?

### Exercise C — change state without changing schema

Change `service.setCount(9)` to `service.setCount(31)`, and `HotMethod.staticCounter = 777` to `= 502`. Re-run. Why do both V1 and V2 see the new values instead of the default initializers 7 and 100?

### Exercise D — check capability

Remove `Can-Redefine-Classes: true` from the manifest, build a new JAR, and run on a JVM that enforces this capability. Why is `isRedefineClassesSupported()` no longer guaranteed to be true? If it is false, how should the program respond?

### Exercise E — intentionally change class schema

Add a new field **only in V2**, rebuild, and run the test on your VM. If the JVM rejects the redefinition, at which layer does it report the error? Why can't we assume every V1 object will automatically get the new field layout?

### Exercise F — rollback with an active V2 frame

Have V2 `work()` wait on a separate latch, create a V2 frame, then redefine back to V1. Predict which code the waiting V2 frame will run after waking up and which code a new invocation after the rollback will run.

### Self-check questions

1. **Does a frame running during redefinition switch bytecode mid-execution?** No.
2. **Does a new invocation on the same old instance use V2?** Yes, after a successful update.
3. **Does `redefineClasses` require a `ClassDefinition` containing replacement bytes?** Yes.
4. **Does the static initializer re-run on redefinition?** No.
5. **What is the manifest capability specific to redefine?** `Can-Redefine-Classes: true`.
6. **If the API throws an exception when updating a multi-class set, is part of the set redefined?** According to the Javadoc, no.
7. **Can a V1 frame call a new V2 method?** Yes, if the callee's invocation starts after the update.
8. **How should you verify that an update took effect?** With a **new invocation** after `redefineClasses` succeeds.

## 14. Summary and Official References

**Redefinition updates the method definition for future calls, without overwriting the instruction stream of stack frames that have already started.** Within a single JVM, an active V1 frame and a V2 invocation can coexist on the **same class identity and the same object**, with static and instance state preserved. This is essential to understand when analyzing traces missing entry spans, hotfix method replacements, rollbacks, and instrumentation coverage measurements.

To verify your conclusions, use tests with real synchronization such as `CountDownLatch`, compare the output of an active frame before/after redefinition against that of a new invocation, and verify that the API returned successfully. Do not use arbitrary timestamps or rely solely on callback notifications.

Official documentation:

- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `redefineClasses`, active stack frames, new invokes, static state, errors, and limitations.
- [Java SE 17 — ClassDefinition](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html): pairing class identity and replacement byte array.
- [Java SE 17 — java.lang.instrument](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): `-javaagent`, `premain`/`agentmain`, and manifest attributes.
- [Java SE 17 — UnmodifiableClassException](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/UnmodifiableClassException.html): conditions for unmodifiable classes.
- [JVMTI 17 — RedefineClasses](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html#RedefineClasses): low-level VM semantics for method versions.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): synchronization utility for deterministic output.
