# Distinguishing Feature Disabling, Transformer Removal, and Process Termination

## 1. Three Operations Commonly Called “Turning Off the Agent” That Are Not Equivalent

In Java instrumentation deployments, a request to “turn off the agent” is very easy to misinterpret. There are at least three completely different levels of impact:

1. **Feature disable:** keeps the agent/helper and the instrumented bytecode in the JVM, but switches the hooks to a branch that **does not perform measurement work** or reduces the collection level.
2. **Unregister transformer:** calls `Instrumentation.removeTransformer(transformer)` to stop applying **that registered transformer** to classes/definitions processed later; **does not automatically revert the bytecode of already-loaded classes**.
3. **JVM process termination:** the application stops running. The threads, runtime classes, agent, and memory of the process disappear when the JVM actually terminates; this is a **process-level action**, not a safe way to “turn off only the agent” in a serving application.

A fourth operation often confused with the three above is **reverting transformations of loaded classes** using `retransformClasses` or `redefineClasses` when supported and when the proper bytes have been prepared. Reverting bytecode is **a separate proactive task**, not the default effect of `removeTransformer`.

For example, an agent inserts a call to `Probe.hit()` at the entry of `PaymentService.pay()`:

~~~text
PaymentService.pay()                  [transformed class]
    |
    +-- Probe.hit() ----------------> check enabled flag
    |
    +-- business logic

disable feature:
    Probe.hit() remains in bytecode
    but the method returns early without recording an event

remove transformer:
    already-loaded PaymentService class still has Probe.hit()
    new classes do not go through the removed transformer
    (except for callbacks already running concurrently)

shutdown JVM:
    both the application and the agent in that JVM cease to exist
~~~

This is a **conceptual diagram**, not an immediately runnable program. Choose the right level based on your goal: reducing overhead, stopping instrumentation of new classes, restoring classes, or stopping the application.

## 2. Quick Comparison Table

| Criterion | Disable via flag/condition | `removeTransformer` | JVM actually terminates |
| --- | --- | --- | --- |
| Does the JVM keep running? | **Yes** | **Yes** | **No** |
| Do transformed classes automatically revert to original bytecode? | **No** | **No** | No runtime classes remain in that process |
| Do hooks inserted in already-loaded bytecode still exist? | **Yes** | **Yes** | No process remains to execute hooks |
| Do new classes still go through registered transformers? | Possibly, depending on whether the flag is in the helper or transformer | Do not go through the **removed** transformer once removal settles | No new class loading in a stopped JVM |
| Are agent/helper classes still loaded? | Usually **yes** | Usually **yes** | Lost along with the process |
| Do existing threads/exporters/static counters keep running? | Depends on disable/cleanup logic | **May continue** | Terminated with the JVM lifecycle |
| Can it be re-enabled quickly? | **Yes**, if the flag is designed safely | Requires re-registering the transformer and handling target classes | Must start a new JVM process |
| Is retransformation capability required? | **No** to change a runtime flag | **No** to unregister | **No** to exit |
| Main risks | Hooks still incur overhead; in-flight events; config visibility | Misconception of rollback; race with class loading; helper remains alive | Loss of availability, pending events, unclean shutdown |

**Correctness matters:** “Turning off” can mean **stopping event emission**, **stopping modification of new classes**, **stopping execution of agent code**, or **terminating the JVM**. These are four different goals. Before taking action, you must state precisely which one needs to be guaranteed.

## 3. Runtime Feature Disabling: Fast Flag Check at the Hook

A common approach in long-running agents is to maintain a `volatile` or `AtomicBoolean` flag. The hook checks the flag **before** building payloads, capturing stack traces, serializing, or enqueuing data.

~~~java
import java.util.concurrent.atomic.AtomicLong;

public final class Probe {
    private static volatile boolean enabled = true;
    private static final AtomicLong hits = new AtomicLong();

    private Probe() { }

    public static void setEnabled(boolean value) {
        enabled = value;
    }

    public static void onEnter() {
        if (!enabled) {
            return;  // Do not create a record or call the exporter.
        }
        hits.incrementAndGet();
    }

    public static long hits() {
        return hits.get();
    }
}
~~~

This is a **standalone Java class** that can be compiled on Java 17+, but to observe a real hook you still need **another method calling `Probe.onEnter()`** (or an agent inserting the call). A complete example with a real Java agent and helper is in section 7.

**Meaning:**

- `volatile enabled` guarantees **visibility** for flag reads/writes across threads under the Java Memory Model, preventing a thread from indefinitely seeing a stale cached value without a synchronization relationship.
- `AtomicLong` is just an example counter; under high load, `LongAdder` may be suitable for aggregate counts, though it does not provide an atomic snapshot across multiple counters.
- Disabling **does not remove the `Probe.onEnter()` call** from already-instrumented bytecode.
- The flag can be switched back to `true` to record subsequent invocations; no retransformation is needed just to toggle the logic branch.

### 3.1. A Flag in the Helper and a Flag in the Transformer Are Different

**Runtime flag in the helper:**

~~~text
Previously instrumented class:
  method -> Probe.onEnter() -> if (!enabled) return
Disable enabled:
  method still calls Probe.onEnter(), but helper skips recording.
~~~

**Transform control flag:**

~~~java
@Override
public byte[] transform(
        ClassLoader loader, String className, Class<?> redefinedClass,
        java.security.ProtectionDomain domain, byte[] classfileBuffer) {
    if (!transformEnabled) {
        return null;
    }
    // Check className/loader, then generate instrumented bytecode.
    return transformSelectedClass(classfileBuffer);
}
~~~

This is a **code snippet inside `ClassFileTransformer`**, not standalone: `transformEnabled` and `transformSelectedClass` are agent-defined components. When `transformEnabled=false`, the transformer can skip **subsequent callbacks**, but classes instrumented previously **do not automatically revert to their original form**.

**Specifically:** if a method already had a helper call inserted earlier, turning off a flag **only in the transformer** does not stop those already-inserted calls from emitting events. Usually **both a runtime gate in the helper** (to stop recording immediately for old classes) and an appropriate transformer policy (to avoid inserting hooks into new classes) are needed.

### 3.2. Does Not Mean Immediate Stop of Everything In Progress

Suppose thread A has already read `enabled=true` and started building an event; thread B immediately afterward changes the flag to `false`. The **in-progress** event may still complete. `volatile` guarantees visibility for reads according to memory ordering, but **does not cancel work that has already passed the check point**.

If a stronger operational boundary is required, you must design a `RUNNING → QUIESCING → DISABLED` state machine, track the number of actively executing scopes, stop accepting new events, wait up to a deadline, and then flush/drop remaining data. **Waiting indefinitely for all scopes** in business threads is also dangerous if a method hangs.

When setting flags in a multi-classloader system, you must also pay attention to **class identity**: each classloader may define **its own copy of the `Probe` helper** with its own static flag. Turning off `Probe.enabled` in loader A does not automatically change the copy in loader B. The control design needs to know where the helper is defined.

### 3.3. A “No-Op” Hook Still Has Overhead

A call instruction into the helper, a branch checking the flag, a volatile read, potential class initialization, and stack/bookkeeping still incur cost. The JIT may optimize part of this depending on the case, but **zero overhead must never be promised**. For extremely high-frequency methods, benchmark latency/throughput when enabled and when disabled, after JIT warmup.

When the flag is off, do not continue building stack traces/JSON/arguments before checking the flag:

~~~java
// Bad if capturing a very expensive stack trace before knowing whether enabled is true.
String expensive = captureStackTrace();
if (enabled) exporter.send(expensive);

// Prefer checking early:
if (!enabled) return;
String payload = captureStackTrace();
exporter.send(payload);
~~~

This is a **code snippet inside a helper** that has `captureStackTrace`, `exporter`, and the flag already declared; it is only meant to illustrate **the ordering that reduces overhead**.

## 4. Removing the Transformer: Stops Future Transformations, Does Not Roll Back Old Classes

Standard Java 17 API:

~~~java
boolean removed = instrumentation.removeTransformer(transformer);
~~~

This is a **code snippet inside a Java agent** that already has `Instrumentation instrumentation` and the **exact `ClassFileTransformer` object** that was registered. `removed=true` means a registration was found and removed. `removed=false` means that transformer was not found in the currently registered list.

According to the Java 17 Javadoc:

- `addTransformer(transformer)` or `addTransformer(transformer, canRetransform)` registers a transformer to process class definitions per the contract.
- `removeTransformer(transformer)` **cancels one registration**; if the same instance was registered multiple times, the API removes **the most recently added matching registration**. Therefore, avoid registering the same instance repeatedly unless necessary.
- Class definitions **after removal settles** will not be sent to that transformer.
- **Callbacks may still arrive after `removeTransformer` returns** due to concurrent multi-threaded class loading already in progress. The transformer must be written defensively for this possibility.
- The API **does not remove bytes already applied to loaded classes** and does not stop agent workers/threads/loggers/helpers.

Source: [Java 17 — Instrumentation.removeTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#removeTransformer(java.lang.instrument.ClassFileTransformer)).

### 4.1. Removing a Transformer Differs From “Disabling a Transformer”

There are two ways to prevent future transforms:

~~~text
A. Transformer remains registered, callback enters -> sees flag false -> return null.
B. removeTransformer -> future class definitions do not invoke it
   (except in-flight callbacks may still occur).
~~~

A can be easily re-enabled via a flag, but still incurs callback/matcher overhead. B stops that registration, though re-enabling requires `addTransformer`. Neither **reverts already-transformed classes**.

### 4.2. `removeTransformer` Does Not Unload the Agent JAR, Helper, or Static State

When a transformer is removed:

- `premain` does not “run in reverse”; there is no default lifecycle callback named `unloadAgent`.
- Already-loaded agent classes do not suddenly disappear.
- Any `AtomicLong`/`LongAdder`, worker pools, daemon threads, shutdown hooks, and agent registries must have their **lifecycles managed separately**.
- Already-woven methods can still call `AgentHelper.onEnter`.
- If the exporter is still running, it may consume resources even when no new events arrive.
- With multiple registered transformers/other agents, only **the removed registration** is affected; not all of them are removed.

Do not build a UI button labeled “Uninstall agent” that internally only calls `removeTransformer` and then reports that it “reverted all changes.” That misrepresents its actual effect.

## 5. Why Do Transformed Classes Keep Old Bytecode After `removeTransformer`?

The class file transformed when the JVM defines a class is installed as **the runtime definition of the class**. When unregistering a transformer, the JVM receives no request to modify already-defined classes. Thus, if `ServiceA` was instrumented earlier, subsequent method calls still execute the applied definition (unless another transformation operation occurs).

~~~text
When loading ServiceA:
    original bytes
        |
        +-- transformer T: produces instrumented bytes
        v
    JVM defines ServiceA with hook

removeTransformer(T):
    registry no longer has T
    already-loaded ServiceA still has hook

When loading ServiceB after remove:
    original bytes
        |
        +-- without T
        v
    JVM defines ServiceB without receiving transformation from T
~~~

This is a **characteristic diagram**; it does not claim that `ServiceB` will be completely untransformed by **other transformers** that remain registered. Likewise, if `ServiceA` had a helper call before instrumentation, removing T does not delete a call written in source.

### 5.1. Retransforming to Revert: A Conditional Operation, Not the Default

In some environments you can try:

~~~java
if (inst.isRetransformClassesSupported()
        && inst.isModifiableClass(targetClass)) {
    inst.retransformClasses(targetClass);
}
~~~

This is a **code snippet inside an agent**, requiring the variables `inst` and `targetClass`. The result **is not guaranteed to be the original bytecode** if other transformers remain, if the class has been redefined, or if outputs of non-retransform-capable transformers need to be replayed.

According to the Javadoc, during retransformation:

1. The JVM starts from the **initial class-file bytes** (not necessarily byte-for-byte identical to the source class file; constant pool/layout may differ).
2. Remaining participating transformers registered with `canRetransform=false` may have their **previous output reapplied** without calling `transform` again.
3. Remaining participating `canRetransform=true` transformers are invoked per contract.
4. The resulting bytes are verified and installed as the new definition if valid.

Therefore, **simply removing one transformer and then retransforming** can restore a class in simple test conditions, but **does not guarantee** removing all instrumentation from other agents. For production rollback, you must understand the **entire transformer chain**, capabilities, class modifiability, accumulated changes, and how to reliably store/restore bytes.

For `redefineClasses`, the agent must supply compatible `ClassDefinition` bytes under JVM constraints; “just grabbing the source and recompiling” does not always work.

### 5.2. Limitations When Retransforming/Redefining

- `isRetransformClassesSupported()` is an **optional capability** of the JVM/agent; at Java agent startup it may require `Can-Retransform-Classes: true` in the manifest. Query the flag in the running JVM itself.
- `isModifiableClass(clazz)` checks **each specific class**; global support is not enough.
- The JVM restricts many schema changes (adding/removing methods/fields, changing class hierarchy, certain modifiers); do not arbitrarily change hooks and then request retransformation of loaded classes.
- **Currently executing stack frames may continue running bytecode of the old version**; new calls use the updated definition. Do not use the completion of a single `retransform` call to assert that no old frames remain in the JVM immediately.
- The class initializer `<clinit>` does not automatically re-run just because of retransformation; static field values remain, so prior agent/helper state or side effects are not cleared.
- If other transformers and native agents are present, class loader and module constraints can impose additional limits.
- A `retransformClasses` call may throw `UnmodifiableClassException`, `UnsupportedOperationException`, `ClassFormatError`, or linking/verification errors depending on conditions; handle them rather than assuming restoration succeeds.

**Consequence:** “Bytecode has been removed” is a claim that requires **readback/runtime testing**, and cannot be inferred solely from `removeTransformer()==true`.

## 6. Terminating the JVM Process: Strongest Level, but Affects the Entire Application

Java provides:

~~~java
System.exit(0);                         // Initiate the JVM shutdown sequence.
Runtime.getRuntime().halt(1);          // Forcibly terminate the JVM without running shutdown hooks.
~~~

These are two **API calls** for comparison; **do not run both consecutively** in the same program because the first call will not return normally. The `halt(1)` example is illustrative only and **should not be run in a serving application** to turn off telemetry.

According to the `Runtime.exit` / `System.exit` Javadoc:

- `System.exit(code)` initiates the JVM shutdown sequence; by convention `0` indicates successful termination, and non-zero indicates abnormal termination.
- The JVM starts registered shutdown hooks in an **unspecified order**, and hooks may run **concurrently**. After the hooks finish, the JVM halts.
- Shutdown hooks are not a place for unbounded work: they need timeouts/flush deadlines, must avoid deadlocks, and must avoid blindly depending on other services that are shutting down.
- `Runtime.halt(code)` terminates forcibly, **does not start shutdown hooks**, and does not wait for them to finish if shutdown has already begun.
- **Forced OS kills**, native crashes, severe OOMEs, and infrastructure failures can cause the JVM to stop with **no guarantee that hooks will run**.

Documentation: [Java 17 — Runtime.exit, halt, addShutdownHook](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html).

**Do not use `System.exit` as an “agent off switch” in a running service**, unless the actual requirement is to **stop the service/JVM** under an approved operational procedure. It will stop the business application as well, not just telemetry.

### 6.1. Cleanly Stopping an Agent Differs From Stopping the JVM

An agent can provide a `close()` method or an administrative endpoint following this model:

~~~text
RUNNING
    |
    v
QUIESCING:
   - turn off flag to stop accepting new records
   - remove transformer to avoid weaving new classes
   - wait within a time limit for in-progress callbacks/scopes
   - flush exporter until deadline
   - stop worker pool, timer, listener, unregister metrics/MBean
   - clean up ThreadLocal/context if under control
    |
    v
DISABLED (JVM still running, instrumented classes may remain)
    |
    +-- if there is a bytecode restoration policy, retransform separately
    +-- if a guaranteed clean class state is needed, rolling restart the JVM
~~~

This is a **sample workflow**, not a built-in automatic Java agent API. Removing a transformer does not undo a registered shutdown hook; if you need to remove your hook before the JVM begins shutdown, you can call `Runtime.removeShutdownHook(thread)` while it is still valid. Nor can you force other threads already running hooks to stop immediately.

If a telemetry exporter has a bounded queue, stopping the producer and flushing with a deadline reduces data loss; however, **do not promise exactly-once/durable delivery** merely because `flush()` returns successfully if the exporter/backend lacks a corresponding durability contract.

## 7. Runnable Java 17 Example: Toggle → Remove → Load New Class → Retransform → Exit

This hands-on exercise uses a **real Java agent** via `-javaagent`. A transformer patches **a fixed-length string literal** in the constant pool of two sample classes to illustrate changed class-file bytes. A helper with `volatile enabled` decides whether to increment a counter.

**Explicitly stated limitation:** replacing `CONSTANT_Utf8` `"ORIGINAL"` with `"CHANGED!"` (both 8 ASCII bytes long) is a **test trick only for controlled inputs**, **not general-purpose bytecode weaving**, and does not demonstrate the ability to insert hooks into arbitrary methods. The `FeatureSwitch.mark()` calls in the two targets are written **directly in the source** to simulate a previously inserted hook. The example verifies **the lifecycle and independence of the three actions**, and does not present the demo as a transformer that automatically weaves `mark()` bytecode.

### 7.1. Directory Structure

~~~text
lifecycle-demo/
  agent-src/demo/agent/
    FeatureSwitch.java
    LifecycleAgent.java
  app-src/demo/app/
    TargetEarly.java
    TargetLate.java
    DemoApp.java
  manifest.mf
  agent-classes/        (generated on compile)
  app-classes/          (generated on compile)
  agent.jar             (generated on JAR packaging)
~~~

### 7.2. `FeatureSwitch.java` — Runtime Gate That Persists After Removal

~~~java
package demo.agent;

import java.util.concurrent.atomic.AtomicInteger;

public final class FeatureSwitch {
    public static volatile boolean enabled = true;
    private static final AtomicInteger HITS = new AtomicInteger();

    private FeatureSwitch() { }

    public static void mark() {
        if (enabled) {
            HITS.incrementAndGet();
        }
    }

    public static int hits() {
        return HITS.get();
    }
}
~~~

Here `enabled=false` causes `mark` to skip updating; the `FeatureSwitch` class and `mark` method **are not removed** from the JVM. For production, you can optimize the fast path, eliminate loggers/reentrancy, and add clearer lifecycle states.

### 7.3. `LifecycleAgent.java` — Transformer and Control API

~~~java
package demo.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicInteger;

public final class LifecycleAgent {
    private static Instrumentation instrumentation;
    private static ClassFileTransformer transformer;
    private static final AtomicInteger TRANSFORMS = new AtomicInteger();

    public static void premain(String args, Instrumentation inst) {
        instrumentation = inst;
        transformer = new ClassFileTransformer() {
            @Override
            public byte[] transform(ClassLoader loader, String className,
                    Class<?> redefined, ProtectionDomain protection,
                    byte[] data) {
                if (!"demo/app/TargetEarly".equals(className)
                        && !"demo/app/TargetLate".equals(className)) {
                    return null;
                }
                TRANSFORMS.incrementAndGet();
                return patchConstantForTest(data);
            }
        };
        inst.addTransformer(transformer, true);
        Runtime.getRuntime().addShutdownHook(new Thread(
                () -> System.out.println("shutdownHook=ran")));
        System.out.println("agent=installed");
    }

    public static int seen() {
        return TRANSFORMS.get();
    }

    public static boolean remove() {
        return instrumentation.removeTransformer(transformer);
    }

    public static boolean canRestore(Class<?> type) {
        return instrumentation.isRetransformClassesSupported()
                && instrumentation.isModifiableClass(type);
    }

    public static void restore(Class<?> type) throws Exception {
        instrumentation.retransformClasses(type);
    }

    // Demo only: patch a CONSTANT_Utf8 with the same byte count.
    // Do not use this approach as a general-purpose production transformer.
    private static byte[] patchConstantForTest(byte[] original) {
        byte[] out = original.clone();
        byte[] oldValue = "ORIGINAL".getBytes(StandardCharsets.US_ASCII);
        byte[] newValue = "CHANGED!".getBytes(StandardCharsets.US_ASCII);
        int count = u2(out, 8);
        int offset = 10;
        boolean changed = false;

        for (int i = 1; i < count; i++) {
            int tag = out[offset++] & 0xff;
            switch (tag) {
                case 1: {
                    int length = u2(out, offset);
                    offset += 2;
                    if (length == oldValue.length
                            && Arrays.equals(Arrays.copyOfRange(
                                    out, offset, offset + length), oldValue)) {
                        System.arraycopy(newValue, 0, out, offset, length);
                        changed = true;
                    }
                    offset += length;
                    break;
                }
                case 3: case 4:
                    offset += 4;
                    break;
                case 5: case 6:
                    offset += 8;
                    i++;
                    break;
                case 7: case 8: case 16: case 19: case 20:
                    offset += 2;
                    break;
                case 9: case 10: case 11: case 12: case 17: case 18:
                    offset += 4;
                    break;
                case 15:
                    offset += 3;
                    break;
                default:
                    throw new IllegalArgumentException("cp tag=" + tag);
            }
        }
        return changed ? out : null;
    }

    private static int u2(byte[] data, int offset) {
        return ((data[offset] & 0xff) << 8)
                | (data[offset + 1] & 0xff);
    }
}
~~~

**Technical commentary:**

- The transformer applies only to the exact two internal names; agent, JDK, helper, and logger classes are not processed.
- `addTransformer(transformer, true)` registers a transformer **that supports callbacks during retransformation**, if the manifest and JVM allow it. This is a **transformer capability**; it does not mean every class is modifiable.
- `patchConstantForTest` walks the constant pool by `tag` and only patches UTF-8 entries that **exactly match** the test literal. It understands the basic lengths of tags needed for JDK 17 class files; it is not a production parser and does not verify all class-file invariants or multi-release/newer JDKs.
- Replacing a string of the same byte length helps illustrate a transformation that does not alter method/field schemas. Use ASM/Byte Buddy/the Class-File API as appropriate for real bytecode transformations.
- `TRANSFORMS` counts **matching callbacks**, not all classes in the JVM or the number of method calls.
- `Runtime.addShutdownHook` has a hook that prints a closing line to illustrate graceful exit; it does **not** represent a real exporter flushing system.
- When multiple threads load classes concurrently, `removeTransformer` returning creates no guarantee that “all callbacks in all threads have finished”; the Javadoc explicitly notes that late callbacks may arrive.

### 7.4. Both Target Classes Have the Same Initial Marker

**File `app-src/demo/app/TargetEarly.java`:**

~~~java
package demo.app;

import demo.agent.FeatureSwitch;

public final class TargetEarly {
    public static String work() {
        FeatureSwitch.mark(); // Simulates a hook already present in the method.
        return "ORIGINAL";
    }
}
~~~

**File `app-src/demo/app/TargetLate.java`:**

~~~java
package demo.app;

import demo.agent.FeatureSwitch;

public final class TargetLate {
    public static String work() {
        FeatureSwitch.mark();
        return "ORIGINAL";
    }
}
~~~

Both classes return the literal `"ORIGINAL"` if unaffected by the transformer. The `FeatureSwitch.mark()` call is already present, so **when the helper is disabled**, the code may still execute the instruction calling `mark`, but inside the helper it does not increment the counter.

### 7.5. `DemoApp.java` — Using Those Classes Before and After Removal

~~~java
package demo.app;

import demo.agent.FeatureSwitch;
import demo.agent.LifecycleAgent;

public final class DemoApp {
    public static void main(String[] args) throws Exception {
        System.out.println("early.first=" + TargetEarly.work());
        System.out.println("hits.afterFirst=" + FeatureSwitch.hits());
        System.out.println("transforms.beforeRemove=" + LifecycleAgent.seen());

        FeatureSwitch.enabled = false;
        System.out.println("early.disabled=" + TargetEarly.work());
        System.out.println("hits.whenDisabled=" + FeatureSwitch.hits());

        System.out.println("removed=" + LifecycleAgent.remove());
        System.out.println("early.afterRemove=" + TargetEarly.work());
        System.out.println("transforms.afterRemove=" + LifecycleAgent.seen());

        // Late is looked up by name after removal, avoiding early direct reference.
        Class<?> late = Class.forName("demo.app.TargetLate");
        System.out.println("late.afterRemove="
                + late.getMethod("work").invoke(null));
        System.out.println("transforms.afterLate=" + LifecycleAgent.seen());

        FeatureSwitch.enabled = true;
        System.out.println("early.reenabled=" + TargetEarly.work());
        System.out.println("hits.reenabled=" + FeatureSwitch.hits());

        System.out.println("canRestore="
                + LifecycleAgent.canRestore(TargetEarly.class));
        if (LifecycleAgent.canRestore(TargetEarly.class)) {
            LifecycleAgent.restore(TargetEarly.class);
            System.out.println("early.afterRetransform="
                    + TargetEarly.work());
        }
        System.out.println("transforms.final=" + LifecycleAgent.seen());
        System.out.println("process=exiting");
        System.exit(0);
        System.out.println("unreachable");
    }
}
~~~

**Key point:** `TargetEarly` is loaded while the transformer is still registered, whereas `TargetLate` is looked up with `Class.forName` **after removal**. Because the test program has a single thread and no relevant concurrent callbacks, this makes the difference clearly visible. In production, class loading is concurrent and there is no guarantee that “all threads stop immediately after the remove call.”

### 7.6. Agent Manifest and Run Commands

**File `manifest.mf`:**

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.LifecycleAgent
Can-Retransform-Classes: true

~~~

The trailing blank line terminates the main section of the manifest. `Can-Retransform-Classes: true` is required for the example attempting `addTransformer(..., true)` and retransformation; it **does not mean every JVM supports** this capability.

On Linux/macOS, from the `lifecycle-demo` directory:

~~~bash
mkdir -p agent-classes app-classes
javac --release 17 -d agent-classes \
  agent-src/demo/agent/FeatureSwitch.java \
  agent-src/demo/agent/LifecycleAgent.java

jar --create --file agent.jar --manifest manifest.mf \
  -C agent-classes .

javac --release 17 -cp agent.jar -d app-classes \
  app-src/demo/app/TargetEarly.java \
  app-src/demo/app/TargetLate.java \
  app-src/demo/app/DemoApp.java

java -javaagent:agent.jar -cp "app-classes:agent.jar" demo.app.DemoApp
~~~

On **Windows PowerShell**, classpath entries are separated by a semicolon instead of a colon. The compile commands can be run on single lines without Bash's `\` line continuation character:

~~~powershell
New-Item -ItemType Directory -Force agent-classes, app-classes | Out-Null
javac --release 17 -d agent-classes agent-src/demo/agent/FeatureSwitch.java agent-src/demo/agent/LifecycleAgent.java
jar --create --file agent.jar --manifest manifest.mf -C agent-classes .
javac --release 17 -cp agent.jar -d app-classes app-src/demo/app/TargetEarly.java app-src/demo/app/TargetLate.java app-src/demo/app/DemoApp.java
java -javaagent:agent.jar -cp "app-classes;agent.jar" demo.app.DemoApp
~~~

Requires a **full JDK 17+** with `javac`/`jar` and a JVM that supports retransformation. No dynamic attach or external libraries beyond the JDK are needed.

### 7.7. Verified Output on OpenJDK 21 With `--release 17`

~~~text
agent=installed
early.first=CHANGED!
hits.afterFirst=1
transforms.beforeRemove=1
early.disabled=CHANGED!
hits.whenDisabled=1
removed=true
early.afterRemove=CHANGED!
transforms.afterRemove=1
late.afterRemove=ORIGINAL
transforms.afterLate=1
early.reenabled=CHANGED!
hits.reenabled=2
canRestore=true
early.afterRetransform=ORIGINAL
transforms.final=1
process=exiting
shutdownHook=ran
~~~

This is the **exact stdout** verified by compiling all classes with `javac --release 17`, packaging the agent JAR, and running `java -javaagent:...` on OpenJDK 21/HotSpot. For JVMs that do not support retransformation or for non-modifiable classes, the program must choose a different policy; this configuration intentionally includes a manifest requesting the capability and may not start identically on every VM.

### 7.8. Reading the Output Step by Step

- `early.first=CHANGED!`: `TargetEarly` is transformed on first load; the runtime class no longer returns the `ORIGINAL` marker.
- `hits.afterFirst=1`: the helper is enabled, so the hook called from `TargetEarly.work()` increments the counter.
- `early.disabled=CHANGED!` but `hits.whenDisabled=1`: **disabling the helper only changes hook behavior**, not the class contents.
- `removed=true`: `Instrumentation.removeTransformer` removes the registration in the demo.
- `early.afterRemove=CHANGED!`: **already-loaded classes keep the transformation** even though the transformer was removed.
- `late.afterRemove=ORIGINAL` and `transforms.afterLate=1`: in this single-threaded demo, `TargetLate` is loaded after removal so it does not receive this transformer's patch.
- `early.reenabled=CHANGED!`, `hits.reenabled=2`: re-enabling the flag makes **the hook still in the code** active again; no need to re-register the transformer.
- `canRestore=true` and `early.afterRetransform=ORIGINAL`: in this demo's condition with only this transformer, after removal and requesting retransformation, the JVM uses a new class definition without the patch.
- `transforms.final=1`: the unregistered transformer no longer receives a callback during the example's retransformation.
- `process=exiting` then `shutdownHook=ran`: `System.exit(0)` initiates shutdown; the `unreachable` line does not appear.

**What cannot be concluded from the demo:** that retransformation on every production application restores exact original bytecode; that flag-off eliminates all overhead; that removal guarantees no callbacks are still running; or that shutdown hooks are guaranteed to run if the process is killed with `SIGKILL`/crashes.

## 8. Stopping New Class Transformations While Keeping Old Class Functionality: Sometimes Intentional

Rollback is not always required. Some scenarios:

| Goal | Reasonable action | Trade-off to accept |
| --- | --- | --- |
| Reduce telemetry volume immediately because backend is overloaded | Turn off gate in helper/exporter, increment drop counter if needed | Bytecode hooks still exist; in-flight events |
| Avoid inserting probes into subsequently loaded classes | Disable matcher or remove transformer | Already-loaded classes remain instrumented |
| Re-enable telemetry quickly later | Keep helper/runtime gate and toggle flag | Hook overhead remains while disabled |
| Stop agent from receiving class-load callbacks | `removeTransformer` | Helper/worker/static state is not automatically removed |
| Reduce overhead of already-instrumented classes | Consider retransform/redefine to revert, if valid | JVM capability, verification risks, schema, other agents |
| Guarantee clean code/classloader state across deployment | Rolling restart JVM with new config/agent | Availability impact and operational coordination |
| Stop the service from the system | Graceful shutdown then process exit | Shuts down the entire application in the JVM |
| Stop only one attached agent in the JVM | Design a dedicated control plane/`close()` | No general standard Java API to “unload this javaagent” |

When “complete disable” is demanded, ask for the **SLO/verification criteria** to be defined: no new events, no new callbacks, no bytecode hooks, no agent threads, or no agent classes still loaded? Some goals can be achieved via flags/removal, some require retransformation, and the goal “no agent classes left in the JVM” is usually most practically achieved by **starting a new JVM** without loading that agent.

## 9. Concurrency and Memory Scenarios: Consistency Is Not Instantaneous

### 9.1. State Transition Protocols Should Have Clear Milestones

Example state machine controlled from an administrative endpoint:

~~~text
RUNNING
  |
  | request-disable
  v
QUIESCING (prevent new events; in-progress callbacks/scopes remain)
  |
  | drain until deadline, unregister, stop worker
  v
DISABLED
  |
  | request-enable, restart worker if needed
  v
RUNNING
~~~

If every thread calling `FeatureSwitch.mark` reads the volatile flag before doing work, **new calls passing the check after the update** observe the state consistent with volatile synchronization. However, callbacks that have already passed the check can still finish; the deadline/quiescence phase must also observe an active-scopes counter or queue depth.

Do not wrap an entire business method in `synchronized` just to turn off telemetry “immediately” if doing so destroys throughput and causes deadlocks. If strong linearizability properties are needed, design the state-transition point and its cost intentionally.

### 9.2. Transformer Callbacks Can Enter After Removal

The Javadoc warns about multi-threaded class loading. Therefore, a well-written transformer should use a terminal/volatile flag to reject invalid work even in late callbacks:

~~~java
private volatile boolean registeredAndActive = true;

@Override
public byte[] transform(
        ClassLoader loader, String name, Class<?> type,
        java.security.ProtectionDomain domain, byte[] bytes) {
    if (!registeredAndActive) {
        return null;
    }
    // Only perform the allowed transformation and control reentrancy.
    return transformAllowedClass(name, bytes);
}
~~~

This is a **code snippet in a class implementing `ClassFileTransformer`**; `transformAllowedClass` is application-defined. When disabling/unregistering, set the flag to false and remove the transformer; callback code already executing before seeing the flag may still complete.

**Do not use a non-`volatile`/unsynchronized Boolean** as a control plane in a multi-threaded environment and assume every thread sees the change immediately.

### 9.3. Bytecode Versions Can Coexist During Retransformation

When `retransformClasses` succeeds, **active stack frames** of the modified method may continue using the old bytecode version, while new invocations receive the new bytecode. This behavior is mentioned in the Javadoc; it is not a sign that “`removeTransformer` failed.”

If you need a guarantee that no hooks are still executing, wait for scopes to finish or choose a JVM restart at a rollout boundary. Avoid operating on running frames with assumptions not guaranteed by the JVM.

## 10. Resource Cleanup: Removing the Transformer Does Not Clean Up Workers and Queues

An agent may have created:

- A bounded queue holding unexported events.
- Executors/daemon workers, schedulers, HTTP clients, native handles.
- `ThreadLocal` contexts and per-classloader caches.
- Metrics registries, JMX MBeans, shutdown hooks.
- File/JAR resources, buffered outputs, and network connections.

`removeTransformer` does not call `close()` on these components. A stop mechanism might look like:

~~~java
public void stop() {
    enabled = false;
    instrumentation.removeTransformer(transformer);
    exporter.stopAccepting();
    exporter.flushUntilDeadline();
    exporter.close();
}
~~~

This is **Java pseudocode for a service owning the fields** `enabled`, `instrumentation`, `transformer`, and `exporter`; the exporter methods are library/application-designed, not standard `Instrumentation` APIs.

**Ordering to verify:** once telemetry intake stops, in-flight events may still exist. If the exporter is closed before the helper stops producing events, the system may throw exceptions from hooks or lose data unexpectedly. A clear policy is needed: drop with a counter, flush until deadline, or durable spooling. Avoid catching broad exceptions in a way that causes business methods to fail because of telemetry.

If there are multiple transformers, each transformer needs its own registration handle and owner; do not call `removeTransformer` on an object used by another module without a lifecycle agreement.

### 10.1. A Shutdown Hook Is Not a Guaranteed Delivery Channel

A hook can help with **best-effort** flushing, but:

- JVM hooks have no guaranteed execution order and run concurrently.
- Hooks can deadlock if they depend on services that have already shut down.
- A forcibly terminated JVM may skip hooks.
- Backends/exporters may not receive records in time within the OS-allowed grace period.
- Calling `System.exit` directly inside a hook can cause unexpected behavior in the shutdown sequence.

For mandatory audit data, use transactional/durable logging per business requirements; do not replace it with a shutdown hook and an in-memory buffer.

## 11. Operations in Containers, Servers, and Rolling Deployments

### 11.1. Does “Process Died” Mean Telemetry Disappears Forever?

Not necessarily. A container orchestrator, service manager, or process supervisor may **automatically restart** the JVM with the same `-javaagent` or `JAVA_TOOL_OPTIONS`. When that happens, the agent runs `premain` again in the new JVM. Therefore, to disable the agent **across restarts**, you must update the **deployment configuration** (startup flags, agent JAR, sidecar settings, environment, or attachment policy), and then roll out properly.

**Different examples:**

~~~text
Runtime disable:
  /admin/telemetry = off
  -> current JVM stays alive, toggle enabled

Remove transformer:
  agentController.unregister()
  -> JVM stays alive, old classes remain transformed

Rolling restart removing agent:
  modify JVM startup args, restart instances one by one
  -> new JVMs do not load the agent per the updated configuration
~~~

This is a **descriptive operational procedure**, not a standard JDK endpoint. A deployment may have many instances; disabling on one instance does not automatically apply to others.

### 11.2. Dynamic Attach and Detaching an Agent

`agentmain` can be invoked when a Java agent is dynamically loaded depending on JVM capabilities/configuration. However, Java `Instrumentation` **does not provide a generic “unload agent JAR and undo all changes” method**. An agent that wants a deactivate switch must **provide its own** control endpoint/command, cancel registrations, and clean up helpers/resources. For native JVMTI agents, lifecycle and unloading are a different mechanism; do not apply one-sided rules to all agent types.

Some JVM states cannot be guaranteed to be fully reversible within the same process (class identity, loaded classes, static initialization, side effects that have already occurred). A **controlled restart** is usually the most reliable boundary if the requirement is “return to a JVM that has never loaded the agent.”

## 12. Diagnosing Whether a “Turn Off” Actually Achieved Its Goal

Avoid checking just a single `removed=true` line and closing the incident. Separate the questions:

| Question | Appropriate verification |
| --- | --- |
| Did the runtime flag switch to false? | Read `AtomicBoolean`/`volatile` via admin API and observe hook counters |
| Do loaded hooks still emit events? | Invoke an instrumented method in a test, compare events/counters before and after |
| Was the transformer unregistered? | `removeTransformer` return true/false and registry ownership |
| Do callbacks still occur after removal? | Count callbacks on a **newly** loaded class, noting in-flight races |
| Do old classes still have modified bytecode? | Check behavior or class bytes via a reliable mechanism; test on the exact loaded `Class` |
| Can retransformation roll back? | `isRetransformClassesSupported` + `isModifiableClass` + actual result/exceptions |
| Do helpers/exporters still have live threads? | Thread/worker/queue/JMX/metrics diagnostics |
| Does the queue have pending records at shutdown? | Queue depth, exporter in-flight, retry buffer, flush result/deadline |
| Did the JVM actually terminate? | Process exit status, supervisor/container health, and lifecycle logs |
| Does the agent reappear after restart? | Check startup flags/JVM args and rollout config, not just the old PID |

Things that **should not be used as sole proof**:

- “No more logs”: could be due to sampling, exporter down, log level, or event-loss errors.
- “Counter is 0”: there might simply be no requests yet, not removed bytecode.
- “`removeTransformer` returned true”: only speaks to the registration, not runtime class rollback.
- “`retransformClasses` threw no exception”: still need to verify the class reached the desired state and was not affected by another transformer.
- “Ran `System.exit`”: the process may not have stopped yet due to a hung hook, or the supervisor may have restarted a new JVM.

## 13. Common Implementation Pitfalls

| Misconception | Consequence | Resolution |
| --- | --- | --- |
| Turning off a flag automatically removes hook calls from bytecode | Overhead remains, classes stay instrumented | Separate **no-op** from **class rollback** |
| Removing the transformer reverts all old classes | Loaded classes continue carrying transformations | Conditional retransform/redefine or restart required |
| Removing the transformer means helper/exporter is unloaded | Workers/threads/caches remain alive | Stop/flush/close explicitly |
| Using only a flag in the transformer to disable hooks in old classes | Old classes still call the helper | Runtime gate in helper or rollback |
| Using a non-volatile Boolean for shared config | Threads may see inconsistent data | `volatile`/`AtomicBoolean`/synchronization |
| Assuming zero callbacks immediately after remove | Concurrent loads already started may call late | Transformer checks flag and manages in-flight work |
| Registering one transformer instance twice, removing once | Duplicate registration remains | Avoid duplicate registrations; track ownership |
| Calling retransform without querying global/per-class capability | Exceptions, non-modifiable classes | `isRetransformClassesSupported` and `isModifiableClass` |
| Thinking retransform always returns exact original file bytes | Other transformers, replay, different layout | Understand transform chain and verify output |
| Thinking retransform resets static counters/`<clinit>` | Old state remains in the JVM | Clean up state separately if needed |
| Thinking retransform immediately updates active frames | Old frames may still be running | Quiescence or controlled restart |
| Using `System.exit` to turn off only the agent | Entire application is stopped | Use agent's lifecycle API; exit only when stopping the service |
| Using `Runtime.halt` to flush/close | Shutdown hooks are not run | Graceful stop with deadline if needed |
| Allowing unbounded flush in a shutdown hook | JVM may hang on exit | Deadline and fallback policy |
| Removing agent in one container without changing rollout config | Supervisor restarts with the agent | Manage deployment config |
| Assuming the agent's classloader is automatically GC'd on unregister | References/statics/threads still retain the loader | Clean caches/threads/registries, mind classloaders |
| Writing config variables to multiple helper copies across loaders | Only one group of targets is actually disabled | Organize helper loader/bridge and unified config |
| Deleting the agent JAR from disk while the JVM runs to “unload” | Does not change loaded runtime classes | Proper lifecycle management, rolling restart |
| Not measuring in-flight events when disabling | Seeing a few events “after the off command” and suspecting a bug | Document semantics and observe quiescence |
| Using the constant-pool patch demo as production bytecode weaving | Can corrupt class files or update unintended entries | Use standard bytecode libraries/APIs and a verifier |

## 14. Pre-Production Testing Checklist

**A. Feature toggle**

- [ ] With an instrumented class, enabled → hook records events/counters as expected.
- [ ] Disabled → new invocations do not build payloads/send events, counters do not increment.
- [ ] Re-enabled → the same loaded class behaves per the new flag without needing another transformation.
- [ ] Multiple threads read the flag with proper visibility; handle in-flight scopes and nested calls.
- [ ] Verify helpers in different class loaders do not hold unintended desynchronized flags.
- [ ] Measure overhead when disabled; do not promise zero overhead.

**B. Removing the transformer**

- [ ] `removeTransformer` returns the correct boolean for the exact instance.
- [ ] Count callbacks before/after intentionally loading a new class.
- [ ] Test races with concurrent class loading; transformer reacts safely to late callbacks.
- [ ] Old classes do not automatically roll back; if rollback is desired, test separately.
- [ ] Do not register the same transformer multiple times in the same lifecycle; or have a mechanism to fully remove each registration.
- [ ] Does not affect other transformers/agents.

**C. Rollback and shutdown**

- [ ] Query JVM capabilities and class modifiability before retransformation.
- [ ] Test already-loaded classes, unloaded classes, active method frames, and side effects.
- [ ] Verify new bytes are valid for the VM/module/loader; do not make forbidden schema changes.
- [ ] Review remaining registered non-retransformable transformers and output replay.
- [ ] Stop exporter with a timeout, verify dropped/pending/in-flight records.
- [ ] Test `System.exit(0)` in a **separate test process**, not on a production host.
- [ ] Verify shutdown hooks run in normal shutdown paths and are **not guaranteed** on forced kills.
- [ ] Verify agent state when a new JVM starts per deployment config.
- [ ] Have a rollout/rollback plan if agent startup changes across a multi-instance cluster.

## 15. Self-Check Questions

1. If bytecode already inserted `Probe.onEnter()` yesterday, and today `enabled=false` is set, does the instruction calling `Probe.onEnter()` disappear?
2. What is the difference between a flag in the **helper** and a flag in the **transformer**?
3. What does `removeTransformer(t)` returning `true` confirm, and what does it **not** confirm?
4. Why can `removeTransformer` still be followed by callbacks appearing after the call returns?
5. If the **same transformer instance is registered twice**, is one `removeTransformer` call enough?
6. Why does `TargetEarly` in the demo still return `CHANGED!` after removing the transformer?
7. Why does `TargetLate` return `ORIGINAL` in the same test run?
8. When re-enabling `enabled=true` after removal, why do hooks in old classes still increment the counter?
9. What conditions must be checked before calling `retransformClasses(TargetEarly.class)`?
10. Why can the example restore via retransformation, yet you cannot infer that every production system can restore the same way?
11. If a method is executing during retransformation, where can the old bytecode continue to be used?
12. Why does retransformation not reset static counters or re-run `<clinit>`?
13. How does `System.exit(0)` differ from `Runtime.halt(1)` regarding shutdown hooks?
14. Why might an agent reappear after a JVM stops when a container/service restarts?
15. If the requirement is “no agent classes remaining in the process,” why does removing the transformer usually fail to meet the goal?
16. When an agent has a bounded telemetry queue, what ordering of disable/drain/close should be considered?
17. Are the `FeatureSwitch.mark()` calls in the demo source automatically inserted by the transformer? If not, what is the demo proving?
18. If logs still appear after removal, what causes are unrelated to a `removeTransformer` bug?

**Key takeaway:** **Feature disabling** changes helper/hook behavior, **removing a transformer** stops one registration so new class definitions do not pass through it, and **terminating the JVM** ends the entire application process. Neither of the first two operations **automatically reverts** already-instrumented classes. Reverting bytecode requires a conditional retransform/redefine plan and QA; cleaning up workers/exporters requires a separate lifecycle. When the goal is “a JVM that has never loaded the agent,” a controlled restart with updated startup config is more reliable than calling `removeTransformer`.

### Official References

- [Java 17 — Instrumentation: addTransformer, removeTransformer, retransformClasses](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [Java 17 — ClassFileTransformer and callback lifecycle](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [Java 17 — java.lang.instrument: manifest, premain, agentmain](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [Java 17 — Runtime: exit, halt, and shutdown hooks](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html)
- [Java 17 — AtomicBoolean, volatile, and Java concurrency memory effects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicBoolean.html)
