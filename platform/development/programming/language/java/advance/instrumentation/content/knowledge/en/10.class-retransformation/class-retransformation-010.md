# Active Frames Continue Using Old Code; New Invocations Use the New Definition

## 1. Lesson Objectives

When using Java Instrumentation to **retransform a class currently in use by the JVM**, what happens if a thread is currently executing a method of that class? Does the JVM immediately switch the running stack frame to the new bytecode? Does a new invocation on **the exact same old object** still run the old code?

According to the `Instrumentation.retransformClasses` contract in Java SE 17:

> If a retransformed method has active stack frames, those active frames continue to run the bytecodes of the original method; the retransformed method will be used on new invokes.

This distinguishes **replacing a class definition for upcoming calls** from **swapping code mid-execution in an already created frame**. Retransformation **does not automatically restart a method**, does not move the instruction pointer of an old frame to the new method, does not re-run the static initializer, and does not create a new set of objects.

This lesson clarifies:

1. What an active stack frame is and why it is bound to a selected method version.
2. The timeline boundary between old frames, the new class definition, and new invocations.
3. Why living objects, fields, and static state persist across retransformation.
4. How to use `ClassFileTransformer`, `addTransformer(..., true)`, `retransformClasses`, and manifest capabilities.
5. A **complete Java 17+ demo**: holding a running method with `CountDownLatch`, retransforming that method, and proving the old frame prints `OLD` while the subsequent invocation on **the same object** prints `NEW`.
6. Implications for tracing, latency, instrumentation rollout, rollback, and in-flight requests.

**Important condition:** the conclusion that "new invocations run the new definition" assumes that retransformation **succeeded**, the class was accepted by the JVM, and no other redefinition/retransformation changed the definition between measurements.

## 2. Understanding "Active Frames" and "New Invokes"

A method call causes the JVM to create an **execution frame** containing the state of that call: local variables, operand stack, and the corresponding execution position. The method may be running on the CPU, waiting on a lock, sleeping, waiting for I/O, or waiting on another synchronization primitive without the frame having exited.

Consider the timeline:

~~~text
Thread A                                  Thread B / Instrumentation
--------                                  --------------------------
invoke Service.work() [version V1]
    |
frame A starts V1
    |
V1: does some work
    |
V1: waits on CountDownLatch  ------------------+
    |                                          |
    |                                   addTransformer(..., true)
    |                                   retransformClasses(Service)
    |                                          |
    |                                   JVM installs definition V2
    |                                          |
frame A is woken up     <----------------------+
    |
V1: continues executing the remaining part
    |
V1: RETURN
                                         invoke Service.work() again
                                               |
                                         frame B is created using V2
                                               |
                                         V2: runs new logic
~~~

**There is no mid-execution replacement of frame A into frame V2.** It continues the bytecode version that the JVM selected for invocation A. When invocation B starts after retransformation, the JVM uses the new method definition. This is **API-specified semantics**, not a trick of `Thread.sleep` or the JVM forgetting to update memory.

### 2.1. "Old Frame" Does Not Mean "Old Object"

The `Service` object remains the exact same reference before and after the change. A first `service.work()` call can use V1 and a subsequent `service.work()` call can use V2 **on that same instance**.

Three entities to keep distinct:

| Tracked Entity | Before Retransformation | After Successful Retransformation |
|---|---|---|
| Already created object (`service`) | Exists | **Still the same object**, not automatically reallocated |
| Frame of an active `work()` invocation | Runs V1 | Continues V1 until the frame exits |
| `work()` invocation started **after definition V2 is installed** | Has not occurred yet | Runs V2 |
| Static fields of the class | Have current values | **Preserved**, not reset by retransform |
| Static initializer (`<clinit>`) | Already ran if class was initialized | **Does not automatically re-run** |
| Constructor (`<init>`) of the old object | Already ran when object was created | **Not automatically called again** |

**Illustrative example:** a long-running request entered `CheckoutService.process()` before the agent instrumented it. Even if you successfully retransform mid-request, the frame handling the old request may execute the old logic. A new request entering the method **after** the change runs the new method.

### 2.2. "New Invokes" Means New Calls, Not New Objects

A common misconception: "V2 code only takes effect for objects created after retransformation." That is incorrect. **Existing instances are not affected** means objects do not turn into different objects, while **dispatch for a new method invocation** still uses the new definition after retransformation.

A retransformed class should not be called "a different class" in the sense of having a new identity or class loader. It is still the same class identity in the JVM; the method definition has been updated within the limits permitted by the JVM.

## 3. Contract of Instrumentation.retransformClasses

Relevant API:

~~~java
Instrumentation inst; // Provided by the JVM to premain/agentmain.
Class<?> target;       // Loaded class selected for retransformation.

if (inst.isRetransformClassesSupported()
        && inst.isModifiableClass(target)) {
    inst.retransformClasses(target);
}
~~~

This is an **illustrative snippet**, not a standalone runnable program. To obtain `Instrumentation`, the agent must be loaded by the JVM through the proper mechanism.

To register a callback for retransformation:

~~~java
inst.addTransformer(transformer, true);
~~~

The `true` parameter states that this transformer is capable of participating in **retransformation**. It is only accepted when the corresponding capability is supported. In the agent's main manifest, this typically requires:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.LiveAgent
Can-Retransform-Classes: true

~~~

If the agent uses dynamic attach, declare `Agent-Class` and use `agentmain` accordingly, but **the old-frame/new-method contract belongs to retransformation**, regardless of whether the agent is loaded before or after `main`.

### 3.1. What Happens During Retransform?

At a conceptual level:

1. The JVM receives the list of classes to retransform, checking capabilities and modifiability.
2. The JVM determines the base classfile bytes according to `Instrumentation` rules. These bytes **may not be byte-for-byte identical** to the original file; for example, constant-pool layout or attributes may differ.
3. The results of transformers **not supporting retransformation** are reapplied according to the API contract, without necessarily invoking their callbacks again.
4. Transformers **supporting retransformation** are called; the output from a preceding transformer is passed into the next transformer in the specified order.
5. The JVM verifies and installs valid method definitions. If the call succeeds, new invocations use the updated definitions.
6. Existing **active frames** of the replaced methods are not switched to the new bytecode mid-execution.

An **actual `retransformClasses` call** is required to apply changes to already loaded classes. Merely registering a new transformer does not automatically update classes previously defined by the JVM.

### 3.2. What If the Operation Fails?

Retransformation can fail if the VM does not support it, a class is not modifiable, the new schema violates constraints, the bytes are malformed, or class verification/linking fails. Relevant errors include `UnmodifiableClassException`, `ClassFormatError`, `VerifyError`, `UnsupportedClassVersionError`, or other errors per specification.

According to the `retransformClasses` Javadoc, if this method **throws an exception/error**, **no classes in the requested set have been retransformed**. Therefore, you must not claim "new invokes run V2" without evidence that the operation succeeded.

### 3.3. What Changes Are Allowed?

Retransformation is meant to change parts **permitted by the JVM**, notably method bodies, certain constant-pool entries, and attributes. You must not assume you can arbitrarily:

- add or remove fields;
- add, remove, or rename methods;
- change method descriptors/signatures;
- change the superclass or set of interfaces;
- modify structures prohibited by the VM.

The hands-on example creates **two versions of the same class, with the same field/method schema**, differing only in the body of the `work()` method. That avoids confusing replacing an implementation with creating a new object type.

## 4. Why Can an Old Frame Continue?

A frame that has started executing is bound to **the method version used for that invocation**. During a class definition replacement, the JVM can retain the old method version long enough for active frames. JVM TI uses the concept of method versions that can become **obsolete** after redefinition/retransformation.

This allows:

- A thread currently performing work not to have to "jump back to the start of the method" just because a new agent was enabled.
- The JVM not to have to rewrite the frame's local variables and operand stack to match V2 bytecode.
- Definition updates for future calls to proceed while old calls are still finishing.

**This does not mean the JVM does nothing to JIT code.** A JVM implementation may invalidate or deoptimize JIT-compiled code to preserve correct semantics. API users should rely only on **the contract of V1 bytecode for old frames and V2 for new invocations**, without assuming the implementation always keeps the same machine code, avoids safepoints, or incurs no latency spikes.

### 4.1. An Old Frame Can Still Call a New Method

An important nuance: "frame A continues V1 bytecode" **does not mean every method it subsequently calls uses V1**. If the remaining V1 bytecode contains an instruction that **invokes another method** after the class has been updated, **that new call** is resolved according to the appropriate definition at invocation time.

For example, the old logic of `process()` calls `calculate()` right after waking up. If `calculate()` has been retransformed, that `calculate()` call can use the new code even though the caller `process()` is still an old frame. Thus, a long-running request **can experience a mix of method versions**, rather than a uniform snapshot of the entire application at the moment the request began.

### 4.2. No Replay of Past Events

If `work()` performed 100 data writes before retransformation, a probe attached in V2 **cannot retroactively observe** those 100 events. For an old frame, a new probe inserted at the end of the method does not magically appear inside the V1 frame's execution. For future events, the new agent can observe within the scope it actually instruments.

For tracing/metrics, you must distinguish the timestamps when **the agent was loaded**, **the class was retransformed**, **old frames exited**, and **new data began taking effect**.

## 5. Complete Java 17+ Demo: Active Frame Uses OLD, New Invocation Uses NEW

This example uses a real agent with `ClassFileTransformer` and `Instrumentation.retransformClasses`. It does not use ASM/Byte Buddy or the JDK 24 Class-File API; all code compiles with `javac --release 17`.

We prepare **two classfile builds of `demo.HotMethod`**:

- **V1**: `work()` prints `OLD:entered`, waits on a `CountDownLatch`, then prints `OLD:resumed`.
- **V2**: same class name, modifiers, and method signature, but `work()` prints `NEW:invoked`.
- **Main**: creates **a single instance**, starts a thread calling V1, waits for the thread to enter the method, requests retransformation from V1 to V2, releases the old thread, and then calls `work()` again on **the original instance**.
- **LiveAgent**: captures `Instrumentation` during `premain` and registers a retransformation-capable transformer only for the duration of the update.

**Key design point in the experiment:** using `CountDownLatch` instead of `Thread.sleep` establishes a deterministic happens-before ordering. The old thread is woken up **only after `retransformClasses` has returned successfully**. Thus stdout does not rely on machine speed or accidental race conditions.

### 5.1. Directory Structure

~~~text
retransform-frame-lab/
├── agent.mf
├── src/
│   ├── agent/
│   │   └── demo/
│   │       └── LiveAgent.java
│   ├── app/
│   │   └── demo/
│   │       └── Main.java
│   ├── v1/
│   │   └── demo/
│   │       └── HotMethod.java
│   └── v2/
│       └── demo/
│           └── HotMethod.java
└── out/                    # created during build
    ├── agent/
    ├── v1/
    ├── v2/
    └── live-agent.jar
~~~

The two `HotMethod.java` sources have **the same class name and package** but live in **two separate directories**. **Do not compile both V1 and V2 in the same command/classpath**: keep them as two separate artifacts so the JVM starts with V1 and the transformer supplies V2 bytes.

### 5.2. Agent Receiving Instrumentation and Requesting Retransform

File **`src/agent/demo/LiveAgent.java`**:

~~~java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.ProtectionDomain;

public final class LiveAgent {
    private static Instrumentation inst;

    public static void premain(
            String opts, Instrumentation instrumentation) {
        inst = instrumentation;
    }

    public static void update(
            Class<?> target, Path replacement) throws Exception {
        if (!inst.isRetransformClassesSupported()
                || !inst.isModifiableClass(target)) {
            throw new IllegalStateException(
                    "Retransformation unavailable");
        }

        byte[] bytes = Files.readAllBytes(replacement);

        ClassFileTransformer tx = new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    ClassLoader loader,
                    String name,
                    Class<?> redefining,
                    ProtectionDomain protection,
                    byte[] input) {

                if ("demo/HotMethod".equals(name)
                        && target == redefining) {
                    System.out.println("agent:transform");
                    return bytes;
                }
                return null;
            }
        };

        inst.addTransformer(tx, true);
        try {
            inst.retransformClasses(target);
        } finally {
            inst.removeTransformer(tx);
        }
    }
}
~~~

**Detailed explanation:**

- The JVM passes `Instrumentation` to `premain` during agent startup. We store it in a static field so `Main` can request retransformation **while the application is running**.
- `isRetransformClassesSupported()` checks the capability (requires a matching manifest and VM support); `isModifiableClass(target)` checks the specific class.
- `Files.readAllBytes(replacement)` reads the compiled **V2 class file**. This demo uses a trusted local file; production code must control the source, format, and signature of bytecode.
- In `transform`, `name` uses the JVM internal name `demo/HotMethod`. `redefining` is the class being retransformed, allowing exact filtering of the existing target; when defining a new class, this parameter is normally `null`.
- `return bytes` returns the **byte[] of the replacement definition**. It does not patch `input` in place; the bytes are submitted to the JVM for verification and installation.
- `addTransformer(tx, true)` is required for the new callback to be invoked when `retransformClasses` runs.
- `try/finally` always removes the transformer after the operation. **Removing the transformer does not automatically revert the installed definition.** A later retransformation might reapply a different transformer chain and produce a different definition; do not treat the state as permanently immutable.

**Note:** This demo uses an agent loaded **at startup** and then requests retransformation **after the method is already active**. This lesson tests **retransformation** behavior, not the dynamic attach mechanism. A late-attached agent using `agentmain` can also request retransformation if the JVM permits it and the agent has the corresponding capability.

### 5.3. Main Coordinating Synchronization Between Two Threads

File **`src/app/demo/Main.java`**:

~~~java
package demo;

import java.nio.file.Path;
import java.util.concurrent.CountDownLatch;

public final class Main {
    static final CountDownLatch ENTERED = new CountDownLatch(1);
    static final CountDownLatch RELEASE = new CountDownLatch(1);

    public static void main(String[] args) throws Exception {
        HotMethod service = new HotMethod();

        Thread worker = new Thread(service::work, "old-frame");
        worker.start();

        ENTERED.await();
        System.out.println("main:before-retransform");

        try {
            LiveAgent.update(
                    HotMethod.class, Path.of(args[0]));
            System.out.println("main:after-retransform");
        } finally {
            RELEASE.countDown();
            worker.join();
        }

        service.work();
    }
}
~~~

**Why are there two latches?**

- `ENTERED` lets the main thread know that the worker thread **has entered V1.work()** and is on its way to the waiting point before retransformation begins. No guessing with sleep durations is needed.
- `RELEASE` prevents the old frame from finishing before the update occurs. The main thread only opens the latch after `LiveAgent.update` has returned (even if the update fails, `finally` still releases the worker to avoid hanging the demo).
- `worker.join()` ensures the old frame has exited before `main` makes the next invocation. This keeps **stdout deterministically ordered**.
- `service` is **a single object allocated exactly once**; there is no second `new HotMethod()` statement. This proves that **an old instance uses the new method definition on a subsequent invocation**.
- `Path.of(args[0])` receives the path to the V2 classfile from the command line. Exactly one argument must be supplied, as shown in Section 5.7.

### 5.4. Version V1: Active Method

File **`src/v1/demo/HotMethod.java`**:

~~~java
package demo;

public final class HotMethod {
    public void work() {
        System.out.println("OLD:entered");
        Main.ENTERED.countDown();

        try {
            Main.RELEASE.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return;
        }

        System.out.println("OLD:resumed");
    }
}
~~~

When the worker thread calls `work()`:

1. It prints `OLD:entered`.
2. It signals `main` that it has entered the method.
3. It waits on `Main.RELEASE.await()`, while **the `work()` frame remains active** and has not returned.
4. When `main` opens the latch, it continues to the statement printing `OLD:resumed` in **V1 bytecode**.

If method V1 is retransformed between steps 3 and 4, this frame **does not automatically switch to V2**.

### 5.5. Version V2: Method Used for New Invocations

File **`src/v2/demo/HotMethod.java`**:

~~~java
package demo;

public final class HotMethod {
    public void work() {
        System.out.println("NEW:invoked");
    }
}
~~~

Both sources use the same `package demo`, the same binary name `demo.HotMethod`, the same modifiers, compatible default constructors, the same instance method `public void work()`, and **add no new fields or methods**. Only the method body changes, making this a typical case that fits retransformation constraints on supporting JVMs.

`NEW:invoked` is printed during the invocation **after** the V2 definition has been installed. It is not a log printed by the transformer itself; the transformer prints a separate line `agent:transform`.

### 5.6. Manifest and Build Commands

File **`agent.mf`**:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.LiveAgent
Can-Retransform-Classes: true

~~~

Keep a trailing newline at the end of the file. `Can-Retransform-Classes: true` **requests** retransformation permission; if the JVM does not support it, `isRetransformClassesSupported()` may return false. `Can-Redefine-Classes` is not needed because the demo does not call `redefineClasses`.

Create build directories with Bash:

~~~bash
mkdir -p out/agent out/v1 out/v2
~~~

Or PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out/agent, out/v1, out/v2
~~~

At the `retransform-frame-lab` root, compile with **JDK 17 or later**:

~~~bash
javac --release 17 -d out/agent src/agent/demo/LiveAgent.java
javac --release 17 -cp out/agent -d out/v1 src/v1/demo/HotMethod.java src/app/demo/Main.java
javac --release 17 -d out/v2 src/v2/demo/HotMethod.java
jar --create --file out/live-agent.jar --manifest agent.mf -C out/agent .
~~~

**Build order explanation:**

1. The agent must be compiled first so `Main` can import/reference `demo.LiveAgent`.
2. `Main` and **HotMethod V1** are compiled together into `out/v1`; V1 code references `Main.ENTERED`/`Main.RELEASE`.
3. **HotMethod V2** is compiled **separately** into `out/v2`. Do not put `out/v2` on the application's startup classpath.
4. The agent JAR contains `LiveAgent.class` and `META-INF/MANIFEST.MF`, but does not contain V1 or V2 of `HotMethod`.
5. `-javaagent` at runtime automatically loads the agent; `Main` can call into `LiveAgent`, which is loaded in the system class loader per the startup agent JAR mechanism.

**Inspecting artifacts:**

~~~bash
jar --list --file out/live-agent.jar
javap -verbose -classpath out/v1 demo.HotMethod
javap -verbose -classpath out/v2 demo.HotMethod
~~~

In both `javap` outputs, with `--release 17`, look for `major version: 61`. You can use `javap -p -s` to verify both have the method descriptor `()V` for `work`. Class V2 is **a replacement definition of the same class**, not a class with a new name or package.

### 5.7. Running the Lab

~~~bash
java -Xverify:all -javaagent:out/live-agent.jar -cp out/v1 demo.Main out/v2/demo/HotMethod.class
~~~

Command components:

- `-Xverify:all` instructs the JVM to perform stricter bytecode verification in the test environment.
- `-javaagent:out/live-agent.jar` loads the agent at JVM startup to obtain `Instrumentation`.
- `-cp out/v1` supplies `Main` and **the V1 class** of the application.
- `out/v2/demo/HotMethod.class` is **the path to the V2 class bytes**, read by `LiveAgent.update` when invoking retransformation.

**Demo stdout on a JVM supporting retransformation:**

~~~text
OLD:entered
main:before-retransform
agent:transform
main:after-retransform
OLD:resumed
NEW:invoked
~~~

This example has been tested on a JDK supporting Java 17 target, using `javac --release 17` and `java -Xverify:all`.

### 5.8. Why Do These Six Lines Prove the Lesson?

| Line | Who Prints It? | Meaning |
|---|---|---|
| `OLD:entered` | Worker, method V1 | Old invocation has started |
| `main:before-retransform` | Main | Worker has entered the method; now starting definition replacement |
| `agent:transform` | Agent callback | JVM invoked the transformer on the right class during retransform |
| `main:after-retransform` | Main | `retransformClasses` returned normally; V2 was accepted |
| `OLD:resumed` | **Old worker frame** | Pre-existing active frame continued in V1 bytecode |
| `NEW:invoked` | **New invocation on the same service** | V2 method body was used for the next call |

These are **not** two different objects. No code creates a second object after retransformation. They are **two invocations of the same method name on the same instance**, started at two different times.

**Key distinction:** The `agent:transform` output only proves the callback ran. It is the fact that `retransformClasses` returned successfully **and** the new invocation printed `NEW:invoked` that proves definition V2 was installed and used.

## 6. Interaction Among Multiple Frames, Threads, and Method Versions

### 6.1. Two Frames of the Same Method Can Simultaneously Use Two Versions

In the demo, we let the old frame exit before calling the new method so stdout is easy to read. Semantically, however, if after `retransformClasses` succeeds, **`main` calls `service.work()` while the old worker is still waiting**, the JVM can simultaneously have:

~~~text
Thread worker: earlier work() frame      -> V1 bytecode (waiting)
Thread main:   new work() invocation     -> V2 bytecode (running)
~~~

This does not require two `ClassLoader`s, two `Class` objects, or two instances. **Method-version coexistence** is normal during a transition period.

If you want to try it, move the `service.work()` call in `Main` to **right after** `main:after-retransform` but **before** `RELEASE.countDown()`. In the V2 demo, the new method only prints a line and does not block. Re-run in a test environment to observe `NEW:invoked` while the old worker has not yet exited.

### 6.2. A Long Call Can Outlive Multiple Retransformations

A frame that started with V1 can retain V1 semantics even if the class is retransformed to V2 and then V3, as long as that frame remains active and the VM applies valid updates. New calls after each definition change will use the version active at invocation time.

**Do not assume system-wide semantic switching is instantaneous.** At a single point in time, you may have:

- old requests in V1 frames;
- requests launched after the first update using V2;
- newer requests using V3;
- shared resources (databases, queues, static state) still accessed concurrently by multiple logic versions.

The system must account for **compatibility across overlapping execution flows**, especially if instrumentation alters side effects rather than merely adding telemetry.

### 6.3. Do Not Rely on Arbitrary Sleep Durations

An unsynchronized demo often uses:

~~~java
Thread.sleep(500);
retransform();
Thread.sleep(500);
~~~

**This is not standalone and does not prove the thread entered the method.** On a busy machine, during JIT warmup, or during a GC pause, the thread may not have reached the point of interest. To prove an active frame, use a barrier/latch/phaser or a deterministically verifiable synchronization condition.

In the main demo, `ENTERED.await()` and `RELEASE.await()` eliminate the critical timing skew: `main` cannot retransform before the worker signals it has entered the method; the worker cannot print `OLD:resumed` before `main` releases it after retransformation.

## 7. Static State, Instance State, and Class Initialization

During a successful retransformation:

- **The class does not automatically re-run its static initializer (`<clinit>`).** For example, if a class has `static int counter=10` and `counter` increments to 80, retransformation does not reset `counter` to 10.
- **Already allocated instances are not recreated**, do not re-run constructors, and do not have fields reassigned according to new bytecode.
- **Existing static and instance field values persist**; new bytecode can read/write those compatible fields in new method calls.
- **Changing a method body does not require changing class identity.** Pre-existing object references remain usable.
- **You cannot arbitrarily add new fields** and expect the JVM to populate default values in old objects; schema changes are not a general capability of retransformation.

Conceptual example:

~~~text
Before:
  service.counter == 7
  frame #1: work() V1 waiting

Retransform work() -> V2:
  service.counter still == 7
  frame #1 continues V1

After:
  frame #2: work() V2 can observe counter == 7
~~~

If a framework uses caches, object state and code version can temporarily diverge in **business-logic conventions**. Instrumentation should tolerate old state rather than assuming every object was "migrated" by retransformation.

## 8. Impact on Tracing, Metrics, and Profiling

### 8.1. Enabling a Probe Mid-Request

Suppose at `t0` request A enters `Service.process()`, at `t1` the agent retransforms the class to insert a timer, and at `t2` request A exits:

~~~text
t0 request A enters process V1 -------- active ------------ t2 return
                                 ^
                                 t1 retransform to V2
                                                             
t3 request B enters process V2 ---- records new metric/trace ----> return
~~~

If the timer only exists in **V2**, request A's V1 frame **does not automatically receive the inserted timer call**. Therefore, A may not appear in the new metric/trace even though it completes after `t1`. Request B, starting after the update, is typically the appropriate verification case.

### 8.2. Do Not Treat Attach Time as an Absolute Data Boundary

Distinguish these milestones:

1. The agent was loaded by the JVM.
2. The transformer was registered.
3. A specific class was successfully retransformed.
4. New invocations of the method began running the new definition.
5. All old active frames have exited.
6. New telemetry was successfully exported/ingested.

If a dashboard marks "enabled" at milestone 1, that does not mean all subsequent requests are fully instrumented. In particular, for long requests that started **before** milestone 3, data may be missing the beginning or the entirety of that method.

### 8.3. Avoid Mistaking Old Events for Broken Probes

After deploying an agent, you may observe:

- Some old requests do not record metrics → **likely active V1 frames**.
- New requests have metrics → **V2 is being used for new invokes**.
- A few deep methods inside an old request have metrics → these are **new invokes** made from the old frame after the update.
- A request completes without a matching span → not necessarily a broken exporter; check when the invocation started.

When debugging, log **the timestamp of successful retransformation**, classloader/class identity, count of updated classes, and an appropriate probe identity/version label. You can use counters to distinguish V1/V2 invocation counts in a test environment. Do not treat completion event counts as an exact proxy for the number of calls that went through the new version.

## 9. JIT Mechanics and Real-World Latency

The JVM may execute a method via the interpreter, the JIT compiler, or optimized/inlined code. Retransformation can force the VM to **invalidate some compiled code, deoptimize, or perform an implementation-dependent safepoint/handshake** to preserve semantics. This can cause pauses or overhead that a small demo does not reflect.

**The API-level guarantee is method-version semantics**, not a guarantee of zero stop-the-world pauses, zero deoptimization, or `retransformClasses` completing below a specific latency threshold.

When enabling instrumentation on a production service, measure:

- `retransformClasses` return duration;
- CPU spikes and JIT/deoptimization fluctuations;
- p95/p99 request latency;
- allocations/GC introduced by new probes;
- number of instrumented classes and class loaders;
- transform failure counts, skipped classes, and telemetry drops.

Do not retransform all of `getAllLoadedClasses()` if you only need a few methods. Filter by target, check `isModifiableClass`, and limit class count/batch size to reduce impact.

## 10. How Retransformation Differs from Redefinition and Class Reloading

| Mechanism | How It Works | Active Frames | New Invocations | Object and Class Identity |
|---|---|---|---|---|
| `Instrumentation.retransformClasses` | Re-runs the transformer pipeline on a loaded class | Continue old bytecode version | Use retransformed method if successful | Preserves identity/state |
| `Instrumentation.redefineClasses` | Accepts replacement classfile bytes directly | Continue old bytecode version | Use redefined method if successful | Preserves identity/state |
| Loading another class with a **new class loader** | Creates a different class identity despite the same name | Old frame belongs to old class identity | Depends on which loader/reference is called | **Not** the same class; old objects do not change type |
| Restarting the JVM | New process and fresh class loading | Old frames end with process lifecycle | All invocations in the new process | In-memory state typically must be reinitialized |

Under Java SE 17, both `retransformClasses` and `redefineClasses` specify that active frames continue original bytecodes and new invokes use the new definition. The difference is primarily **the bytecode source and update workflow**, not a "stack frame swapping" mechanism.

### 10.1. Why Not Use a New ClassLoader Instead of Retransform?

If you create a new `URLClassLoader` and load a class with the same name `demo.HotMethod`, the JVM can have **two distinct class identities**. An object of the old class **does not become an instance** of the class from the new loader. Call sites holding references to the old object/class may keep using the old version, and `ClassCastException` or linkage conflicts can occur if types from the two loaders are mixed.

Retransformation in the demo is completely different: there is only **one class identity and one object**, yet the method body is updated for new invocations.

### 10.2. Removing a Transformer Does Not Automatically Revert

In the demo:

~~~java
inst.addTransformer(tx, true);
try {
    inst.retransformClasses(target);
} finally {
    inst.removeTransformer(tx);
}
~~~

Removing `tx` prevents that transformer's callback from participating in **future** transformations. It **does not automatically trigger a retransformation to bring V1 back**. To roll back, you must have another designed and tested definition-update step; and remember that **V2 frames that already started before rollback can also continue running V2**.

Rollback therefore also has an overlap window between method versions. Never claim that merely removing a transformer immediately returns all threads to the old behavior.

## 11. Common Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Old frame still prints `OLD` after retransform | **Expected behavior per API**: frame started with V1 | Check a new invocation; do not expect an active frame to switch versions |
| New invocation still runs V1 | Retransform did not succeed, transformer lacks capability, wrong class, or replacement bytes were not used | Check manifest, `isRetransformClassesSupported`, `isModifiableClass`, callback filter, and output |
| `agent:transform` not printed | Transformer not registered with `true` or target class did not match | Register before calling `retransformClasses`; check `classBeingRedefined` |
| `UnmodifiableClassException` | VM or target class disallows modification | Skip unmodifiable classes; choose another approach |
| `UnsupportedOperationException` or schema-change error | V2 added/removed fields/methods or made disallowed hierarchy/signature changes | Transform only valid method bodies; verify structure of both versions |
| `ClassFormatError` / `VerifyError` | Invalid V2 class bytes or transformer chain output | Check bytecode, stack map, constant pool, class version, and verifier |
| Out-of-order output when demo uses `sleep` | Thread timing race | Use `CountDownLatch` as in the example; do not infer from sleep duration |
| Metrics miss old requests | Request entered the method before instrumentation | Record invocation start time; rely on old telemetry if history is needed |
| Metrics double-counted after multiple applies | Transformer inserts duplicate probes or multiple agents instrument the same target | Ensure idempotence, detect existing probes, manage lifecycle |
| App slows down when enabling instrumentation | Retransforming many classes, JIT deopt, expensive probes | Narrow target classes, measure p95/p99/CPU/GC, roll out in batches |
| V2 still appears after rollback | V2 frame already started or definition update to revert to V1 was not executed | Verify rollback workflow and wait for/measure active requests |

### 11.1. Check Both Class Loader and Class Name

The name `demo/HotMethod` in the callback is only the first filter step. In multi-classloader applications, there can be **multiple classes with the same binary name**. The example uses `target == redefining` to avoid accidentally modifying a `Class<?>` instance from another loader.

You should also check `Instrumentation.getAllLoadedClasses()`, `isModifiableClass`, modules, and class loaders when attaching to a large JVM. Do not retransform a different class merely because its name matches.

### 11.2. A Transformer Exception Is Not a Rollback

If a transformer's `transform` throws `IllegalClassFormatException` or another callback exception, the JVM follows `ClassFileTransformer` error-handling rules; a callback exception **does not automatically prevent loading/retransformation**. However, if the final bytes are invalid, `retransformClasses` can fail when installing the definition.

Therefore, when evaluating "success", do not check only whether the callback was invoked. Verify that `retransformClasses` returns normally, and if specific behavior is required, **verify with a new invocation** as in the demo.

## 12. Operational Checklist When Enabling Instrumentation at Runtime

### Before the Change

- [ ] Define the **milestone** from which new data is counted: after each class has been successfully retransformed.
- [ ] Recognize that long-running requests or old frames may continue executing pre-change bytecode.
- [ ] Identify exact class identity/loader; do not filter by name alone.
- [ ] Check `Can-Retransform-Classes`, `isRetransformClassesSupported`, and `isModifiableClass`.
- [ ] Ensure no disallowed class schema changes are made.
- [ ] Verify helper classes and dependencies added by probes are visible to the target loader.
- [ ] Prepare tests on the target JVM/classfile version; test with `-Xverify:all` in an isolated environment.
- [ ] Have a recovery plan if transformation fails; avoid updating all classes at once unnecessarily.

### During the Change

- [ ] Log/record metrics for the start and end timestamps of `retransformClasses`.
- [ ] Count succeeded/failed classes; do not equate callback invocation with an installed definition.
- [ ] Monitor latency/CPU/GC/JIT on live traffic.
- [ ] Do not perform heavy operations or blocking I/O inside the transformer.
- [ ] Do not retain class/object references too long and cause a classloader leak.
- [ ] Avoid duplicate retransformations or multiple agents overwriting each other without ordering control.

### After the Change

- [ ] Verify that a **new invocation** runs the new version.
- [ ] Accept that pre-existing active frames may finish using old bytecodes.
- [ ] Correlate telemetry by invocation start time, not only completion time.
- [ ] Do not attribute missing spans/metrics of old requests as proof of a broken agent.
- [ ] Verify static/instance state was not reset and class identity did not change.
- [ ] Have a dedicated rollback plan; `removeTransformer` does not revert already-running frames.
- [ ] Define when data coverage is sufficient for SLA/measurement evaluation.

## 13. Self-Practice Exercises and Review Questions

### Exercise A — Predict the Output

For the Section 5 demo, write down the order of the six stdout lines **before running it**. Why does `OLD:resumed` appear **after** `main:after-retransform` yet still print OLD?

**Answer:** The worker thread already started method V1 before retransformation. The latch only pauses frame execution; waking it up does not create a new invocation.

### Exercise B — Simultaneous V1 and V2

Move `service.work()` between `main:after-retransform` and `RELEASE.countDown()` (adjusting `try/finally` appropriately). If the JVM accepts the retransformation, you can see `NEW:invoked` while the old worker is still blocked. Explain why two method versions coexist while there is only a single `HotMethod.class` identity.

### Exercise C — Inspect Object State

Add an identical `int count` field to both V1 and V2, initialized/assigned in V1's constructor before the update. Have V2 print `count`. If retransformation succeeds, predict whether it sees the old value or the default value. Explain why **retransformation does not create a new object**.

**Note:** Because the field is added to *the test source of both versions before building*, the class schema remains identical. Do not attempt to add a field **only in V2** and expect the JVM to support schema changes.

### Exercise D — Evaluate Tracing

A span starts from request A before retransformation, and request B starts after. If V2 adds a probe at the entry of `work()`, why might A lack the new entry span while B has it? If A calls another method **after** the update, why might that called method still have the new probe?

### Exercise E — During Rollback

V2 was installed, and then V1 was reinstalled. List the three groups that can coexist briefly: **old V1 frames from before the update**, **V2 frames started between the two updates**, and **new invocations after rollback running V1**. Why can't rollback force all active frames to "switch code immediately"?

### Exercise F — Schema-Change Error

Modify V2 to add a new method or change the descriptor of `work()`. The JVM is allowed to reject the retransformation for violating schema constraints. Restore the signature to match V1 and re-run; this exercise helps separate **method version** concerns from **type structure** concerns.

### Quick Quiz

1. **Does an active frame running V1 automatically switch to V2 bytecode after retransform?** — No; it continues executing the bytecodes of the original version.
2. **Does a new `work()` call on the same old object use V2?** — Yes, once V2 has been installed successfully and has not been replaced again.
3. **Does `retransformClasses` automatically re-run constructors or static initializers?** — No, beyond what occurs under normal JVM initialization semantics.
4. **Does `addTransformer(tx, true)` automatically update already-loaded classes?** — No; you must explicitly call `retransformClasses`.
5. **Does `Can-Retransform-Classes: true` guarantee the VM supports every class?** — No; check the capability and `isModifiableClass`.
6. **Can both V1 code and V2 code appear within the same request?** — Yes, if an old frame calls a new method after the update.
7. **Does `removeTransformer` roll back V2?** — It does not do so automatically.
8. **To prove the new version is in effect, what should you observe?** — An invocation started after `retransformClasses` succeeds, not just the callback.
9. **If retransform throws an exception, can V2 be considered installed for part of the class set?** — According to the Javadoc, no classes in the requested set have been retransformed.
10. **What should you do when enabling metrics amid live traffic?** — Record the update timestamp, evaluate old and new requests separately, and test coverage and overhead.

## 14. Summary and References

**Core takeaway:** `retransformClasses` replaces a class definition so **new invocations** execute the transformed method, but **does not rewrite bytecode currently being executed by an active frame**. An object can be called first with V1 and next with V2; its fields, static state, and class identity remain intact. This creates a transition window with multiple method versions, which must be accounted for in instrumentation, tracing, hot fixes, and rollbacks.

**When verifying, synchronize the experiment with a latch/barrier, observe a method already running before the update, and trigger a new invocation after the update completes.** The mere appearance of a transformer callback is not enough to prove a definition was installed.

Official documentation:

- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `retransformClasses` contract, active frames, new invokes, preserving instance/static state, and class change restrictions.
- [Java SE 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): transformer pipeline, `canRetransform`, and byte handling.
- [Java SE 17 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): `-javaagent`, `premain`, manifest, and JVM initialization.
- [JVMTI — RetransformClasses](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html#RetransformClasses): corresponding native JVMTI model, method versions, and active frames.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): deterministic ordering synchronization for testing.