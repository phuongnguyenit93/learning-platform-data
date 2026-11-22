# Comparing the results of transformers with and without retransformation capability

## 1. Both are `ClassFileTransformer`, why do callbacks run differently?

When doing Java instrumentation, an agent can register a `ClassFileTransformer` in two ways:

~~~java
inst.addTransformer(transformer, false);
inst.addTransformer(transformer, true);
~~~

The two ways **do not differ merely by a performance flag**. They determine whether the transformer is **called back** by the JVM when a loaded class is requested via `retransformClasses(...)`.

- **`canRetransform=false`:** the callback is used for future class definitions, and can also participate in redefinition according to the contract; however, when `retransformClasses` runs, the JVM **does not call this callback again**. For a class already transformed by it during a previous load/redefine, the JVM **reapplies the saved transformation result**.
- **`canRetransform=true`:** the callback can be invoked both at initial load/redefine and **called back** when `retransformClasses` actually runs on the relevant class. It receives input at its position in the pipeline and can provide new bytes.
- **Transformer registered after the class is already loaded:** if `canRetransform=false`, `retransformClasses` does not cause that callback to automatically run on the old class. If the new transformer has `canRetransform=true` and the VM allows it, `retransformClasses` can be used to instrument the loaded class.

**Key takeaway:** do not conclude "`canRetransform=false` ⇒ previous transformation disappears after retransform". According to Java SE 17 `Instrumentation.retransformClasses`, **the previous result of an incapable transformer is reused, but the callback itself is not called again**.

This lesson belongs to the **Agent Experiment** group: instead of only reading Javadoc, we will compile a Java 17+ agent, run a target class with the original value `ORIG`, register both types of transformers, perform **two retransforms**, and observe **the results along with the callback counts**. Then register an incapable transformer **too late** to verify why it does not intervene in an already-existing class.

### Observation goals

~~~text
Source classfile:
    Message.value() -> "ORIG"

Initial load (with agent from startup):
    early incapable transformer: ORIG -> BASE
    capable transformer:         called; returns null
    Method invocation:           "BASE"

retransformClasses #1:
    early incapable transformer: NOT called again; JVM replays BASE bytes
    capable transformer:         called again; BASE -> LIVE
    Method invocation:           "LIVE"

Register late incapable after initial load, then retransform #2:
    early incapable:              still NOT called again
    late incapable:               NOT called on already-loaded class
    capable:                      called again, sees BASE -> LIVE
    Method invocation:            "LIVE"
~~~

The experiment does not use dynamic attach: the agent is loaded **from startup** via `-javaagent` to focus on comparing the semantics of `canRetransform`. This difference is also important when the agent is loaded via `agentmain`, provided retransformation capability is available and the class is eligible. Do not confuse the method of loading the agent into the JVM with the transformer callback policy.

## 2. Exact definitions of the three phases

### 2.1. Initial class load

When the JVM defines a new class, eligible registered transformers are invoked in pipeline order. Each transformer can:

1. Return `null`: **do not change bytes** at its step.
2. Return a new `byte[]`: provide replacement classfile bytes to pass to the next step.
3. Throw an exception: the JVM has a mechanism to continue processing other transformers according to the `ClassFileTransformer` contract; an exception in the transformer should not be confused with an exception in the injected business hook.

Both capable and incapable transformers can participate in **initial class definition**. The `canRetransform` flag does not mean "only capable transformers run at load time".

### 2.2. Retransformation of an already-loaded class

After the target class has been defined, the agent calls:

~~~java
inst.retransformClasses(targetClass);
~~~

The JVM performs a retransformation process on the existing class. According to the Java SE 17 Javadoc, the basic flow is:

~~~text
initial classfile bytes / base bytes managed by the JVM
          |
          v
canRetransform=false transformers:
    replay the result of the previous load/redefine
    DO NOT call transform(...) again
          |
          v
canRetransform=true transformers:
    call transform(...) again
          |
          v
Verify and install the new class definition
~~~

`initial classfile bytes` in the step above are not necessarily byte-for-byte identical to the `.class` file on disk; the JVM may rearrange the constant pool or equivalent attributes. The replay mechanism for incapable transformers is **reapplying the previous transformation** without requiring the transformer logic to run again.

### 2.3. Redefinition is not retransformation

`Instrumentation.redefineClasses(ClassDefinition...)` accepts classfile bytes supplied by the caller. `Instrumentation.retransformClasses(Class<?>...)` asks the JVM to re-run the pipeline based on the bytes managed by the JVM. The two operations are related but have **different APIs and different inputs**.

The `canRetransform=false` flag does **not** mean the transformer is forbidden from all **redefine** operations: the `addTransformer` Javadoc states the callback is called when a class is loaded or redefined, whereas only when `canRetransform=true` is it called again during retransformation. Do not use a redefine test to infer retransform callback counts.

## 3. Behavior matrix by scenario

| Scenario | Initial load callback? | Callback on `retransformClasses`? | What happens to the old result? |
|---|---|---|---|
| Registered before load, `false` | Yes, if filter matches | **No** | JVM replays old transform result |
| Registered before load, `true` | Yes, if filter matches | **Yes** | Callback is invoked again to decide new output |
| Registered **after load**, `false` | No past load event | **No** | Does not produce new transformation for old class via retransform alone |
| Registered **after load**, `true` | No past load event | **Yes**, if class/VM allows | Transformer gets a chance to return bytes for already-loaded class |
| `removeTransformer(t)` then retransform later | Depends on history | Removed transformer receives no future callbacks under that registration | Do not treat remove as rolling back the class definition |
| Class not modifiable or VM unsupported | Depends on load | Retransformation is rejected or cannot be requested | Do not measure callbacks by assuming the operation succeeded |

**Be careful with scope:** callbacks may receive other class definitions (if unfiltered) or other event types. The table only describes **a single target class** and a valid retransformation request. The number of times a transformer is called across all other classes is not necessarily 1/2/3 as in the lab.

### 3.1. How to read `addTransformer`

~~~java
inst.addTransformer(transformer);
~~~

is equivalent to:

~~~java
inst.addTransformer(transformer, false);
~~~

Therefore, the overload without the boolean does **not** automatically enable retransformation capability. For instrumentation code that wants to instrument already-loaded classes, this is a common configuration mistake.

### 3.2. Mandatory preconditions when passing `true`

~~~java
if (!inst.isRetransformClassesSupported()) {
    throw new IllegalStateException("Retransformation is unavailable");
}
inst.addTransformer(transformer, true);
~~~

`isRetransformClassesSupported()` must return `true`. Capability is optional depending on JVM configuration and agent JAR: `Can-Retransform-Classes: true` in the manifest along with VM support. If unsupported, `addTransformer(..., true)` may throw `UnsupportedOperationException`.

For the target class:

~~~java
if (!inst.isModifiableClass(targetClass)) {
    throw new IllegalStateException("Class is not modifiable");
}
~~~

Not every `Class<?>` can be retransformed. Both the general capability and the specific class must be checked.

## 4. Designing an experiment to distinguish callbacks from results

The experiment uses three transformer instances with two behavior types:

1. **EARLY (incapable, registered before class load):** records callbacks; if it sees the literal `ORIG`, it returns a classfile copy with the literal `BASE`. It is not capable, yet its initial change must still be replayed by the JVM during retransform.
2. **CAPABLE (registered before class load):** counts every callback; at initial load it observes `BASE` and returns `null`. On retransformation, it sees `BASE` and returns bytes with the literal `LIVE`.
3. **LATE (incapable, registered after class load):** records callbacks without attempting to modify the class. After two retransformations, LATE's callback count **remains 0**.

This is neither a throughput benchmark nor an attach example. It is a **test of callback counts + input data + method behavior**.

### 4.1. Why use `ORIG`, `BASE`, `LIVE`?

All three strings are exact **4-byte** ASCII. The demo transformer only replaces the content of a `CONSTANT_Utf8` entry in the constant pool, keeping classfile length, method signature, branch offsets, and schema unchanged.

This edit approach is chosen to make **replay vs rerun** clear, and is not recommended as a production classfile patcher. Arbitrary byte edits can affect many constant-pool references, frames, and classfile format. For real-world instrumentation, use ASM/Byte Buddy or the appropriate JDK Class-File API.

### 4.2. Exact expectations

| Milestone | `Message.value()` | EARLY callbacks | CAPABLE callbacks | LATE callbacks | CAPABLE sees BASE in retransforms |
|---|---|---:|---:|---:|---:|
| Initial load | `BASE` | 1 | 1 | 0 | 0 |
| After retransform #1 | `LIVE` | 1 | 2 | 0 | 1 |
| Add LATE; after retransform #2 | `LIVE` | 1 | 3 | 0 | 2 |

Conclusions from these numbers:

- EARLY callbacks **do not increase** from 1 to 2/3, yet its `BASE` effect remains in the input that CAPABLE receives.
- CAPABLE callbacks **increase** 1 → 2 → 3, proving a rerun on each retransform.
- LATE is not called on the target via `retransformClasses` alone when it is not capable.
- Retransform #2 does **not** turn `LIVE` into some other new literal: the pipeline goes back to the base/replay source, CAPABLE sees `BASE` again, and then produces `LIVE`.
- Do not guess callback counts from the number of times `Message.value()` is called: method invocation **does not run transformers**.

## 5. Runnable Java 17+: project structure

~~~text
compare-transformer-lab/
├── AGENT.MF
├── src/
│   ├── agent/demo/agent/CompareAgent.java
│   └── app/demo/
│       ├── target/Message.java
│       └── app/ExperimentApp.java
└── out/
    ├── agent/
    ├── app/
    └── compare-agent.jar
~~~

There are **three Java source files** and one manifest. `CompareAgent` contains two private nested transformer classes; no additional source files are needed. The application accesses some public methods on the agent JAR to actively request retransform and retrieve counts.

**Lab-specific characteristic:** the agent JAR is both loaded via `-javaagent` and placed on the application classpath so `ExperimentApp` can call methods on `CompareAgent`. This is a design for quick testing in the **same JVM**, not a pattern to apply by default to a standalone production agent.

### 5.1. File `src/app/demo/target/Message.java`

~~~java
package demo.target;

public final class Message {
    private Message() {}

    public static String value() {
        return "ORIG";
    }
}
~~~

This code is the entire target class source. It contains only a single string literal `ORIG`. After the agent transforms the classfile at load time, the application will never see `ORIG` at the initial milestone: it sees `BASE` because EARLY modified the input before the class was defined.

### 5.2. File `src/app/demo/app/ExperimentApp.java`

~~~java
package demo.app;

import demo.agent.CompareAgent;
import demo.target.Message;

public final class ExperimentApp {
    private ExperimentApp() {}

    public static void main(String[] args) throws Exception {
        System.out.println("initial=" + Message.value());
        System.out.println("afterLoad=" + CompareAgent.counts());
        System.out.println("capableSawBaseAtLoad=" + CompareAgent.sawBaseAtLoad());

        CompareAgent.retransform(Message.class);
        System.out.println("afterRetransform1=" + Message.value());
        System.out.println("afterRetransform1Counts=" + CompareAgent.counts());
        System.out.println("capableSawBaseOnRetransforms="
                + CompareAgent.sawBaseOnRetransforms());

        CompareAgent.registerLateIncapable();
        CompareAgent.retransform(Message.class);
        System.out.println("afterRetransform2=" + Message.value());
        System.out.println("afterRetransform2Counts=" + CompareAgent.counts());
        System.out.println("capableSawBaseOnRetransforms="
                + CompareAgent.sawBaseOnRetransforms());
    }
}
~~~

Calls to `Message.value()` do not request retransform. The two transformations only happen at **the two `CompareAgent.retransform(Message.class)` lines**. The `registerLateIncapable()` call occurs after the class is already loaded, helping simulate an agent adding capability at the wrong time.

### 5.3. File `src/agent/demo/agent/CompareAgent.java`

~~~java
package demo.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;
import java.security.ProtectionDomain;
import java.util.concurrent.atomic.AtomicInteger;

public final class CompareAgent {
    private static volatile Instrumentation instrumentation;
    private static final Incapable EARLY = new Incapable(true);
    private static final Incapable LATE = new Incapable(false);
    private static final Capable CAPABLE = new Capable();

    private CompareAgent() {}

    public static void premain(String options, Instrumentation inst) {
        instrumentation = inst;
        if (!inst.isRetransformClassesSupported()) {
            throw new IllegalStateException("Retransformation is unavailable");
        }
        inst.addTransformer(EARLY, false);
        inst.addTransformer(CAPABLE, true);
    }

    public static void retransform(Class<?> type)
            throws UnmodifiableClassException {
        Instrumentation inst = instrumentation;
        if (inst == null || !inst.isModifiableClass(type)) {
            throw new IllegalStateException(
                    "Agent is absent or class is unmodifiable");
        }
        inst.retransformClasses(type);
    }

    public static void registerLateIncapable() {
        instrumentation.addTransformer(LATE, false);
    }

    public static String counts() {
        return "early=" + EARLY.calls.get()
                + ",capable=" + CAPABLE.calls.get()
                + ",late=" + LATE.calls.get();
    }

    public static boolean sawBaseAtLoad() {
        return CAPABLE.sawBaseAtLoad;
    }

    public static int sawBaseOnRetransforms() {
        return CAPABLE.sawBaseOnRetransforms.get();
    }

    private static boolean matches(ClassLoader loader, String name) {
        return "demo/target/Message".equals(name)
                && loader == ClassLoader.getSystemClassLoader();
    }

    private static final class Incapable implements ClassFileTransformer {
        final AtomicInteger calls = new AtomicInteger();
        final boolean initialPatch;

        Incapable(boolean initialPatch) {
            this.initialPatch = initialPatch;
        }

        @Override
        public byte[] transform(Module module, ClassLoader loader, String name,
                Class<?> classBeingRedefined, ProtectionDomain pd,
                byte[] bytes) {
            if (!matches(loader, name)) return null;
            calls.incrementAndGet();
            return initialPatch ? patchUtf8(bytes, "ORIG", "BASE") : null;
        }
    }

    private static final class Capable implements ClassFileTransformer {
        final AtomicInteger calls = new AtomicInteger();
        final AtomicInteger sawBaseOnRetransforms = new AtomicInteger();
        volatile boolean sawBaseAtLoad;

        @Override
        public byte[] transform(Module module, ClassLoader loader, String name,
                Class<?> classBeingRedefined, ProtectionDomain pd,
                byte[] bytes) {
            if (!matches(loader, name)) return null;
            calls.incrementAndGet();
            boolean isRedefinition = classBeingRedefined != null;
            if (!isRedefinition) {
                sawBaseAtLoad = containsUtf8(bytes, "BASE");
                return null; // Do not change anything on the first class definition.
            }
            byte[] result = patchUtf8(bytes, "BASE", "LIVE");
            if (result != null) sawBaseOnRetransforms.incrementAndGet();
            return result;
        }
    }

    private static int u2(byte[] b, int pos) {
        return ((b[pos] & 255) << 8) | (b[pos + 1] & 255);
    }

    private static boolean containsUtf8(byte[] classFile, String literal) {
        return patchUtf8(classFile, literal, literal) != null;
    }

    private static byte[] patchUtf8(byte[] source, String before,
            String after) {
        if (source == null || source.length < 10
                || before.length() != after.length()
                || (source[0] & 255) != 0xca
                || (source[1] & 255) != 0xfe
                || (source[2] & 255) != 0xba
                || (source[3] & 255) != 0xbe) {
            return null;
        }

        byte[] out = source.clone();
        int count = u2(source, 8);
        int pos = 10, matches = 0;

        for (int entry = 1; entry < count; entry++) {
            if (pos >= source.length) return null;
            int tag = source[pos++] & 255;
            switch (tag) {
                case 1: {
                    if (pos + 2 > source.length) return null;
                    int len = u2(source, pos);
                    pos += 2;
                    if (pos + len > source.length) return null;
                    if (len == before.length()) {
                        boolean same = true;
                        for (int i = 0; i < len; i++) {
                            if ((source[pos+i] & 255) != before.charAt(i)) {
                                same = false;
                                break;
                            }
                        }
                        if (same) {
                            for (int i = 0; i < len; i++) {
                                out[pos+i] = (byte) after.charAt(i);
                            }
                            matches++;
                        }
                    }
                    pos += len;
                    break;
                }
                case 3: case 4:
                case 9: case 10: case 11: case 12:
                case 17: case 18:
                    pos += 4;
                    break;
                case 5: case 6:
                    pos += 8;
                    entry++; // long/double occupies two constant pool slots.
                    break;
                case 7: case 8: case 16:
                case 19: case 20:
                    pos += 2;
                    break;
                case 15:
                    pos += 3;
                    break;
                default:
                    return null;
            }
            if (pos > source.length) return null;
        }
        return matches == 1 ? out : null;
    }
}
~~~

**Runnability note:** This is Java 17, overriding the `ClassFileTransformer.transform(Module, ClassLoader, String, Class<?>, ProtectionDomain, byte[])` overload. The `containsUtf8` method intentionally calls `patchUtf8` with identical before/after to check for **one** matching UTF8 entry without using the output. The transformers only match `demo/target/Message` belonging to the system class loader.

### 5.4. File `AGENT.MF`

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.CompareAgent
Can-Retransform-Classes: true

~~~

`Premain-Class` is for agents loaded at startup via `-javaagent`. `Can-Retransform-Classes: true` requests the capability. The manifest needs a properly formatted trailing newline (an empty line ending the main section).

If using dynamic attach instead of startup, you would also need `Agent-Class` and `agentmain`. This test **does not use the Attach API** to avoid mixing two questions: "when is the agent loaded?" and "is the callback called again on retransform?".

## 6. Build and run without external libraries

### 6.1. Create output directories

From the root directory `compare-transformer-lab`.

Linux/macOS (Bash):

~~~bash
mkdir -p out/agent out/app
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out/agent, out/app | Out-Null
~~~

### 6.2. Compile the agent

~~~bash
javac --release 17 -d out/agent src/agent/demo/agent/CompareAgent.java
~~~

### 6.3. Package the JAR with manifest

~~~bash
jar cfm out/compare-agent.jar AGENT.MF -C out/agent .
~~~

It is good practice to inspect the JAR:

~~~bash
jar tf out/compare-agent.jar
~~~

It must contain `META-INF/MANIFEST.MF`, `demo/agent/CompareAgent.class`, and nested classes such as `CompareAgent$Capable.class`, `CompareAgent$Incapable.class`. There is no need to package `Message.class` into the agent JAR.

### 6.4. Compile the application

~~~bash
javac --release 17 -cp out/compare-agent.jar -d out/app src/app/demo/target/Message.java src/app/demo/app/ExperimentApp.java
~~~

`ExperimentApp` imports `demo.agent.CompareAgent` to actively trigger retransform and read counters, so the agent JAR must be on both the **compile classpath** and **runtime classpath** of the application.

### 6.5. Run on Linux/macOS

~~~bash
java -javaagent:out/compare-agent.jar -cp "out/app:out/compare-agent.jar" demo.app.ExperimentApp
~~~

### 6.6. Run on Windows PowerShell

~~~powershell
java "-javaagent:out/compare-agent.jar" -cp "out/app;out/compare-agent.jar" demo.app.ExperimentApp
~~~

The difference between `:` on Unix and `;` on Windows is the **classpath separator**. If you forget `-javaagent` or forget the JAR on `-cp`, the experiment may fail to obtain `Instrumentation` or fail to resolve `CompareAgent`.

**Do not run this program in a JVM serving real production workloads.** `retransformClasses` changes the runtime definition of the class, even though the class chosen in the lab is very small.

## 7. Stdout verified on a real JVM

Java source equivalent to this lesson was compiled with `javac --release 17`, packaged into an agent JAR, and run on JDK 24. The exact output of the experiment:

~~~text
initial=BASE
afterLoad=early=1,capable=1,late=0
capableSawBaseAtLoad=true
afterRetransform1=LIVE
afterRetransform1Counts=early=1,capable=2,late=0
capableSawBaseOnRetransforms=1
afterRetransform2=LIVE
afterRetransform2Counts=early=1,capable=3,late=0
capableSawBaseOnRetransforms=2
~~~

**This is deterministic stdout from an executed test**, not a variable timing/throughput number. The test uses one target class, one startup agent, one JVM, two retransforms, and the stated filter conditions.

### 7.1. What does `initial=BASE` prove?

The source method returns `ORIG`, but when the JVM defines the class:

1. EARLY `capable=false` receives input containing `ORIG` and returns bytes changed to `BASE`.
2. CAPABLE `capable=true` receives bytes at the next step, sees `BASE`, and returns `null` because it is the initial load.
3. The class is defined with the method returning `BASE`.

Therefore `Message.value()` initially returns `BASE` even though the Java source is `ORIG`.

### 7.2. What does `afterLoad=early=1,capable=1,late=0` prove?

EARLY and CAPABLE are **both called at initial class load**; the capable flag does not determine whether a transformer is called on the first load. LATE has not been registered yet at this point, so its count=0.

### 7.3. What does `capableSawBaseAtLoad=true` prove?

EARLY modified the bytes **before** CAPABLE in the demo pipeline. CAPABLE confirms there is exactly one `BASE` UTF8 entry in the constant pool, even though the original source was `ORIG`.

### 7.4. What does `afterRetransform1=LIVE` prove?

When `retransformClasses(Message.class)` is called the first time:

1. EARLY `canRetransform=false` is not called again. Its counter stays = 1.
2. The JVM **replays EARLY's previous result**, giving CAPABLE an input containing `BASE`.
3. CAPABLE `canRetransform=true` is called again, changing `BASE` → `LIVE`.
4. The JVM installs the new definition successfully; a new `Message.value()` call returns `LIVE`.

CAPABLE's callback count increases 1 → 2. `sawBaseOnRetransforms` increases 0 → 1. Both observations explain **why the method changes to LIVE without EARLY running again**.

### 7.5. What do `afterRetransform2=LIVE` and counters 1/3/0 prove?

After the first retransform, the program registers LATE with `canRetransform=false`. On the second retransform:

- EARLY is still not called again: **1**.
- CAPABLE is called one more time: **3**.
- LATE is not called: **0**, because it is an incapable transformer registered after class load.
- CAPABLE continues to see `BASE` in its input: `sawBaseOnRetransforms=2`.
- The final definition again contains `LIVE`. Behavior is stable, with no automatic stacking of the `LIVE` string patch on top of itself.

**A common misreading:** "The capable transformer is called again, so it must receive `LIVE` bytes from the previous pass." According to the `retransformClasses` process, input is built from the baseline and replay steps; in the demo CAPABLE receives `BASE` on every retransform, **not** the previous LIVE definition as its sole input.

## 8. The replay mechanism of incapable transformers: the most important difference

### 8.1. No callback invocation while still preserving the old transformation effect

The `Instrumentation.retransformClasses` Javadoc explicitly states: for a transformer registered with `canRetransform=false`, the bytes returned by the transformer during its most recent load or redefine are **reused as the output of that step**, but `transform(...)` is **not called again**.

For example, if EARLY inserted a measurement call into bytecode at initial load, a future retransform does not automatically remove that call just because EARLY is incapable. The previous transformation result can remain in the definition after retransform, depending on the pipeline and other transformers.

Logical model:

~~~text
INPUT BASELINE (ORIG)
    |
EARLY (false):
    before load: callback ORIG -> BASE
    on retransform: replay the same saved transformation
    |
CAPABLE (true):
    before load: callback sees BASE -> null
    on retransform: callback sees BASE -> LIVE
    |
VM OUTPUT: BASE at initial load, LIVE after retransform
~~~

### 8.2. Replay does not mean calling a fake `transform` function a second time

If EARLY's callback has a side effect:

~~~java
calls.incrementAndGet();
~~~

when retransformation occurs, the counter **does not increment**. The number of times **a bytecode effect persists** differs from the number of times **the Java callback is executed**.

For metrics, use two separate concepts:

- **Invocation count:** times the callback was invoked.
- **Effective bytecode transformation:** transformation effect reused or returned by a new transformer.

Do not infer "incapable count=1" to mean "the transformation only took effect the first time and then disappeared".

### 8.3. Why is LATE not called on an already-loaded class?

LATE was registered after the `Message` class was already defined. When the second `retransformClasses` runs, LATE is incapable so it **receives no callback**. It also has no old transformation result for that class from initial load for the JVM to replay.

If LATE wants to intervene on an already-loaded class, it must be registered with `canRetransform=true` and request retransformation, provided the JVM and target class satisfy the capability. If it only needs to instrument classes **loaded after registration**, `canRetransform=false` may still be appropriate.

### 8.4. An incapable transformer can still process new classes

`canRetransform=false` does not mean the transformer is "useless". If the JVM later defines a **new class** matching the filter, it can still receive the initial load callback. In the demo, the filter is fixed to `demo/target/Message`, which is already loaded; no new initial load of the same class/loader occurs, so LATE stays 0.

## 9. Transformer ordering and interaction

### 9.1. Not simply "global registration order"

According to `ClassFileTransformer`, transformers are organized into **retransformation-incapable/capable** groups, which may include Java/native instrumentation agents. Group ordering is determined by the JVM; within a group, callbacks follow the appropriate registration order.

The lab only uses:

~~~text
EARLY: incapable Java transformer
CAPABLE: capable Java transformer
LATE: incapable Java transformer, registered after load
~~~

When the target is initially loaded, EARLY runs and then CAPABLE. LATE does not exist yet. On retransform, EARLY's result is replayed; CAPABLE runs again; LATE is not called.

If there are multiple agents/transformers in production, read the `ClassFileTransformer` Javadoc and store enough metadata to distinguish callback/group/loader/phase. Do not assume the transformer you called `addTransformer` on most recently will run last **across all groups**.

### 9.2. What does a transformer returning `null` mean?

`return null` means the transformer **provides no replacement bytes at this step**. CAPABLE returns null at initial load, so EARLY's output `BASE` continues passing through the pipeline.

Do not interpret `return null` as "rolling back previous transformations". It only means "this step changes nothing".

### 9.3. When a transformer throws an error?

The Javadoc states that the JVM still calls the remaining transformers if one `transform(...)` throws an exception. In terms of pipeline logic, a callback error acts like that step returning no new bytes, though the agent should handle/log the error per policy; never report "success" just because no exception appeared in business code.

Invalid classfile errors after the pipeline completes can cause `ClassFormatError`, `VerifyError`, `UnsupportedOperationException`, or other errors depending on the cause. `retransformClasses` can fail without installing a new definition. These errors must be distinguished from internal transformer exceptions.

### 9.4. Must the output on retransform necessarily be different?

No. A capable transformer can return `null` or return equivalent bytes. The JVM can still perform a valid retransformation process. An increasing callback count does not prove that method behavior changed. The test simultaneously uses:

- Callback counters.
- Verification that CAPABLE sees the literal `BASE`.
- Confirmation that return bytes were successfully produced.
- Runtime invocation of `Message.value()` returning `LIVE`.

Combining multiple pieces of evidence is the right way to draw a conclusion.

## 10. Retransformation and JVM limitations

### 10.1. Class schema change limitations

`retransformClasses` is not a way to change everything in an already-loaded class. JVM TI and Javadoc restrictions apply, typically disallowing arbitrary addition/removal of fields or methods, hierarchy changes, method descriptor changes, or disallowed class modifier changes.

The lab only replaces a same-length UTF8 literal in the constant pool. It does not add methods, fields, branches, stack frames, or exception handlers.

If you need to insert real method calls/hooks, use a bytecode library/tool capable of updating `StackMapTable` and checking verifier rules; do not use an ASCII patcher for production classfiles.

### 10.2. Active stack frames

If a method of a retransformed class **currently has an active stack frame**, that frame may continue executing the **old version** of the bytecode. New invocations use the new definition after the JVM installs it.

The lab method `Message.value()` is very short and called fresh at each milestone, so it does not attempt to demonstrate an active frame jumping to new code mid-execution.

### 10.3. Static fields and object state are not reset

Retransformation does not re-run `<clinit>` or constructors of already-created instances. Static fields, object instances, and application state are not automatically reinitialized when method code changes.

If there were:

~~~java
static int attempts = 42;
~~~

the static field value would not reset back to 42 on every retransform. This code snippet is an **illustrative fragment**, not present in the lab's `Message`.

### 10.4. Same binary name, different loader

Two classes with the same name `demo.target.Message` defined by two different class loaders are **two different runtime classes**. The filter in `matches(loader, name)` intentionally checks:

~~~java
"demo/target/Message".equals(name)
        && loader == ClassLoader.getSystemClassLoader()
~~~

to avoid colliding with a same-named class in a custom loader. In application servers/OSGi/plugin systems, you must explicitly target the right loader/module/layer, rather than matching by name alone.

### 10.5. Measured values on classfile bytes

The `classfileBuffer` input to a capable transformer after retransform is not guaranteed to be byte-for-byte identical to the load-time input or the build artifact file. The JVM may supply an equivalent classfile representation with a different constant pool/attributes; earlier transformers may also have modified/replayed it.

**Therefore, do not hardcode byte offsets** to apply patches in production. The lab patcher walks the constant pool by tags rather than relying on absolute positions. Still, it remains a narrow parser, not a replacement for a bytecode framework.

## 11. Why is `Can-Retransform-Classes: true` important?

The lab's manifest:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.CompareAgent
Can-Retransform-Classes: true

~~~

On a JVM that does not support retransformation, `isRetransformClassesSupported()` may return false even if the manifest contains this attribute. If the manifest does **not** grant the capability, the agent cannot assume it can use `addTransformer(..., true)` and `retransformClasses`.

Correct sequence:

~~~text
Agent JAR manifest requests capability
        |
JVM initializes Instrumentation
        |
isRetransformClassesSupported() == true ?
        |-- no  -> do not register capable transformer
        |-- yes -> addTransformer(t, true)
                         |
                     class already loaded?
                         |
                 isModifiableClass(target)?
                         |-- no  -> stop / report unsupported
                         |-- yes -> retransformClasses(target)
~~~

Do not flip the boolean in source code and expect the JVM to comply if the manifest or policy does not support it.

### 11.1. Should you use `false` or `true`?

**`false`** is usually appropriate when:

- You only want to process **future** classes at load time or during eligible redefines.
- You do not need to update already-running classes.
- You want to reduce the complexity of writing repeatable transforms.
- The JVM lacks or does not grant retransformation capability.

**`true`** is usually needed when:

- You want to instrument **already-loaded** classes at attach/late-startup time.
- You want to update rules/probes for loaded classes at runtime.
- You want to change the output when retransforming a class.
- You have a controlled model for idempotency/re-entrancy, bytecode validity, and rollback.

`true` does not automatically make a transformer "more correct" or always "faster"; it opens an additional callback path and design responsibilities on rerun.

### 11.2. Registering after the class is already loaded

A typical scenario:

~~~text
App loads Service at 08:00
Agent attaches at 08:30
Agent calls addTransformer(t, false)
App continues calling Service
No new load event for the same Class<?>
=> t does not automatically instrument the old Service
~~~

If changed to `addTransformer(t, true)` **and** the VM allows it, followed by calling `retransformClasses(Service.class)`, the callback gets a chance to run on the old class. Attaching the agent and registering the transformer alone is **not enough** without triggering retransformation.

## 12. Distinguishing retransformation from class redefinition

| Characteristic | `retransformClasses` | `redefineClasses` |
|---|---|---|
| What does the caller pass? | Set of loaded `Class<?>` | `ClassDefinition` objects containing classfile bytes |
| Byte source | JVM baseline + transform pipeline/replay | Caller-supplied bytes passed through corresponding pipeline |
| What is it used for? | Reinstrumenting running classes | Replacing definition with custom classfile |
| Arbitrary schema changes allowed? | No | No, still subject to VM restrictions |
| Re-runs static initializer? | No | No |
| Active frames automatically switch to new code mid-execution? | No | No |
| Capable callbacks can participate? | Yes, on retransform | Callbacks per separate redefine contract |

**Do not treat redefinition as "retransform without capability" and ignore constraints.** It requires its own byte set and corresponding capability (`Can-Redefine-Classes`, `isRedefineClassesSupported()`). The callback count test in this lesson **only applies to retransformation**, not by default to all `redefineClasses` calls.

## 13. Small variations for self-study

The following experiments have educational value when performed **one variant at a time on a fresh lab JVM**. Do not change multiple factors at once and guess the cause.

### 13.1. Remove the EARLY transformer

If EARLY is not registered, the `Message` source keeps the `ORIG` literal. CAPABLE only searches for `BASE`, so it will not change it to `LIVE`. In that case, the lab needs to **adjust the oracle**: do not expect initial BASE or after LIVE.

The goal of this variant is to prove CAPABLE in the demo **depends** on EARLY's output. This also simulates scenarios where multiple transformers have input-byte ordering/dependencies.

### 13.2. Change CAPABLE to `false`

If `inst.addTransformer(CAPABLE, false)`, CAPABLE only receives the initial load callback, returns `null`, and does not run on retransform. `Message.value()` remains `BASE` in the lab, even if retransform capability is available, because no capable transformer modifies the bytes.

**However, the `ExperimentApp` source prints counters and fixed expectations from the original version**, so you must update the expected output when running variants. Do not present that as the stdout of the original code.

### 13.3. Register the capable transformer after class load

If CAPABLE does not exist at initial load and is registered with `true` after `Message` is already loaded, then `retransformClasses(Message.class)` is called, it can still be invoked during retransformation while incapable EARLY replays its old effect. This is the foundation of instrumenting already-loaded classes at runtime.

If registered with `false` after load, `retransformClasses` does **not** call it. This is the exact LATE case already tested.

### 13.4. Call retransform a third time

In the standard lab, each valid retransform adds **one** capable callback. EARLY and LATE keep counts 1 and 0. CAPABLE continues to see BASE input and produce LIVE, provided the JVM/pipeline still satisfies the assumptions.

When adding another transformer or replacing the definition via redefine, source bytes and ordering may differ; do not treat the demo's count pattern as a global invariant.

### 13.5. Use two capable transformers both editing the literal

If CAPABLE A changes BASE → LIVE, and CAPABLE B also looks for BASE → DONE, B may **not see BASE** because B's input was already changed to LIVE by A. For two transformers to cooperate, contracts/bytecode expectations must be clearly defined and tested together in the pipeline.

Note that a transformer returning `null` still lets the previous transformer's bytes flow through. This bug often appears when combining multiple Java agents or plugin instrumentation frameworks.

## 14. Common mistakes when reading callback counts

### Mistake 1 — "`false` means it doesn't run at load time either"

Wrong. EARLY `false` still runs at initial load and returns BASE bytes. The flag only governs the **retransformation callback path**.

### Mistake 2 — "`false` will be stripped from the class on retransform"

Wrong. The previous result of an incapable transformer can be replayed by the JVM, as seen in the BASE input that CAPABLE observes in both retransforms.

### Mistake 3 — "Calling addTransformer alone instruments old classes"

Wrong. For already-loaded classes, an appropriate retransform/redefine mechanism is required; a new registration does not automatically replay loaded classes.

### Mistake 4 — "`true` forces the transformer to modify bytes"

Wrong. A capable transformer can be called and return `null` or equivalent bytes. Callback count does not prove behavior changed.

### Mistake 5 — "CAPABLE on the second call always receives LIVE because that was the previous output"

Not in this demo. The JVM rebuilds the transformation from base bytes and replays the incapable result, so CAPABLE sees BASE and then outputs LIVE. Input depends on the pipeline and baseline, not solely on the previously installed definition.

### Mistake 6 — "Counting callbacks by how many times the method was called"

Wrong. `Message.value()` is called multiple times without triggering class transformation; only valid class load/redefine/retransform events produce corresponding callbacks.

### Mistake 7 — "Changing boolean to `true` without declaring it in the manifest"

Insufficient. The VM must support retransformation, and the JAR must request the appropriate capability.

### Mistake 8 — "Same class name means the same class"

No. The defining class loader is part of runtime identity. Without loader filtering, metrics/callbacks may conflate different classes.

### Mistake 9 — "`removeTransformer` automatically rolls back installed effects"

No. It unregisters the callback; definitions already installed in the VM do not automatically revert to the original source.

### Mistake 10 — "A callback throwing an exception means the JVM immediately stops class loading"

Distinguish the `ClassFileTransformer` contract: throwing an exception in a transformer does not necessarily halt the entire pipeline; other transformers may still be called. If the final output classfile is invalid, it can still cause load/retransform to fail.

### Mistake 11 — "One successful retransform means every class is modifiable"

Wrong. `isModifiableClass` applies per class, and capability is VM-optional.

### Mistake 12 — "The lab UTF8 patcher is good enough for all Java classfiles"

Wrong. It only targets ORIG/BASE/LIVE in a lab-controlled class and does not understand all semantics, attributes, bytecode frames, or future classfile versions. A proper writer/verifier is required.

## 15. When should you capture before/after classfiles?

If on a real application you see mismatched callback counts or confusing behavior, capture **selectively**:

- Input `classfileBuffer` when the capable transformer is called.
- Byte array returned by the transformer, if non-null.
- Internal class name, class loader/module, transform phase, sequence, agent version.
- SHA-256/size of binary classfile before and after.
- Skip/filter reason and transformer invocation count.

Use `javap -c -v -p` to inspect the captured files for constant pool, method Code, StackMapTable, exception table, and helper references. However, a snapshot at **one point in the pipeline** does not by itself prove the final bytes installed by the JVM; other transformers may run afterward or the JVM may normalize the classfile.

Example commands (only valid if you have captured `.class` files):

~~~bash
javap -c -v -p captures/Message-before.class
javap -c -v -p captures/Message-after.class
~~~

**The current lesson's example does not save these snapshots.** It verifies via counters/input markers/method return values. Do not expect a `captures` directory after running the original code.

## 16. How to design a safe repeatable transformer

A capable transformer can be called multiple times on a loaded class; keep in mind:

1. **Idempotency:** if the same semantic input is processed multiple times, the output does not add duplicate hooks or corrupt branch offsets.
2. **Do not mutate input:** create new output bytes when actually modifying, return null when skipping.
3. **Keep class schema valid:** on retransform, do not arbitrarily change fields/methods/hierarchy.
4. **Do not rely on input being the previous runtime output:** the JVM has baseline/replay rules.
5. **Do not attach arbitrary global state to `Class<?>` objects:** avoid classloader leaks and leaking references to plugin loaders.
6. **Filter early:** by internal class name, loader, module, retransform phase, and method signature if needed.
7. **Reentrancy:** do not instrument the helper/logger/transformer itself; avoid class loading recursion.
8. **Concurrency:** callbacks can happen from multiple threads; metrics and config need proper visibility/synchronization.
9. **Liveness:** no unbounded blocking I/O inside transform; bound time/budget if needed.
10. **Verification:** use bytecode verifier, javap, unit tests, and runtime behavior tests; do not report success based solely on callback invocation.

The `Capable` demo receives the same BASE input on each retransform and returns the same LIVE output; that is a form of stability **within the scope of this simple classfile**. For real bytecode injection, attach appropriate marker/probe IDs to avoid duplicating instrumentation when multiple agents are present.

## 17. Run and verification checklist

### Before compiling

- [ ] JDK 17+, `java`, `javac`, `jar` available?
- [ ] `AGENT.MF` has `Premain-Class` and `Can-Retransform-Classes: true`?
- [ ] Agent/target/app sources separated into the proper package paths?
- [ ] Target `Message` only has the `ORIG` literal in the method under test?
- [ ] Not running the experiment on a JVM outside permitted scope?

### After initial class load

- [ ] `initial=BASE`, not ORIG?
- [ ] EARLY and CAPABLE each called once?
- [ ] LATE not yet registered, count=0?
- [ ] CAPABLE confirmed seeing BASE in the initial load callback input?
- [ ] Not equating CAPABLE's `return null` with rolling back EARLY's output?

### After retransform #1

- [ ] `isRetransformClassesSupported()` and `isModifiableClass(Message.class)` pass?
- [ ] `afterRetransform1=LIVE`?
- [ ] EARLY counter still 1?
- [ ] CAPABLE counter increased to 2?
- [ ] CAPABLE saw BASE in retransform input at least once?
- [ ] Not calling `Message.value()` a "transform callback"?

### After retransform #2 with LATE

- [ ] LATE registered after initial load with `false`?
- [ ] `afterRetransform2=LIVE`?
- [ ] EARLY still 1, CAPABLE increased to 3, LATE still 0?
- [ ] CAPABLE saw BASE on retransforms = 2?
- [ ] Not assuming the second result is patching the first pass's LIVE output directly?

### When deploying a real agent

- [ ] Understand multi-transformer ordering and capable grouping?
- [ ] Measure/capture errors when retransform fails?
- [ ] Verified the right loader/module/target `Class<?>`?
- [ ] Have a proper rollback/redefine strategy instead of just removing the transformer?
- [ ] Tested active frames/static state and concurrency?
- [ ] Protected classfile snapshots/metrics from data exposure and overhead?
- [ ] Distinguished callback count, bytes returned, and installed runtime behavior?

## 18. Review questions with answers

**1.** Is `addTransformer(t)` equivalent to `addTransformer(t, true)` or `false`?

> Equivalent to `addTransformer(t, false)`.

**2.** Why does EARLY `false` still change ORIG to BASE?

> Because an incapable transformer is still called during **initial class load** when registered before class definition.

**3.** After retransform, why does EARLY's count remain 1 yet BASE still appears?

> Because the JVM replays **EARLY's previous result** without calling the `transform` callback again.

**4.** Why does CAPABLE's count increase from 1 to 3?

> Because it is called at initial load and on **both** retransforms due to being registered with `canRetransform=true`.

**5.** Which string does CAPABLE receive as input on each retransform in the demo?

> BASE, because the pipeline starts from the baseline and replays EARLY's result.

**6.** LATE incapable is registered after the target class loads. Why is count=0 after retransforms?

> Because `canRetransform=false` receives no callbacks on retransformation, and that class had already passed initial load before LATE existed.

**7.** If CAPABLE returns `null` during initial load, why is the initial value still BASE?

> Because null means CAPABLE did not change the output from the previous step; EARLY had already transformed ORIG→BASE.

**8.** Is enabling `canRetransform=true` in source code enough?

> No. It requires `Can-Retransform-Classes: true` in the manifest, JVM capability, and a modifiable class.

**9.** Can `retransformClasses` arbitrarily add methods or fields?

> No. It is subject to JVM TI/Instrumentation class schema restrictions.

**10.** Does `removeTransformer` revert a method back to its original value?

> No. It unregisters the callback; it does not automatically roll back the runtime definition.

**11.** What do `getObjectSize` or `ClassFileTransformer` have to do with callback counts in the demo?

> `ClassFileTransformer` is the primary API; `getObjectSize` measures object shallow size and is unrelated to retransform. Do not use the two APIs interchangeably.

**12.** If CAPABLE is changed to `false`, what else differs in the test?

> CAPABLE is not called again on retransform; it only returns null at initial load, so in the lab the result stays BASE and does not switch to LIVE.

**13.** Will a class with the same binary name under a custom class loader be matched by the filter?

> No, if the filter requires `loader == ClassLoader.getSystemClassLoader()`; class identity also depends on the defining loader.

**14.** What if callback count increases but the method still returns BASE?

> The transformer may have returned null or the input did not match the patch condition. Check bytes returned, logs/filters, VM install capability, and behavior tests—not just the counter.

**15.** When two transformers both edit a constant pool entry, what must be watched?

> Pipeline order and the input seen by the later transformer. An earlier transformation may cause the entry sought by the later transformer to no longer exist.

**16.** Why does the experiment have two retransforms instead of one?

> The second one after registering LATE proves a new non-capable transformer does not automatically run on an old class; it also proves CAPABLE is called again and always receives the baseline replay.

## 19. References

- Java SE 17, `Instrumentation.addTransformer` and `retransformClasses`: differences in canRetransform, replay of incapable results, capable callbacks, and class schema limitations: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- Java SE 17, `ClassFileTransformer`: transformer group ordering, input/output contract, returning `null`, redefinition/retransformation: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
- Java SE 17, `java.lang.instrument` package: `Premain-Class`, `Can-Retransform-Classes`, agent manifest: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
- Java SE 17, JVM Specification Chapter 4: classfile constant pool, `CONSTANT_Utf8`, versions and attributes: https://docs.oracle.com/en/java/javase/specs/jvms/se17/html/jvms-4.html
- OpenJDK JEP 451: notes on dynamic agent loading policy; the current experiment uses a startup agent so the Attach API is not needed: https://openjdk.org/jeps/451
