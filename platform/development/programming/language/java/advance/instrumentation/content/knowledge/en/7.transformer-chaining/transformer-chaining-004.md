# Registration Order Within Each `ClassFileTransformer` Group

A Java agent can register multiple `ClassFileTransformer` instances. When the JVM processes a class, eligible transformers are run in a **chain**: each step receives the `classfileBuffer` left by the previous step. Therefore, the order not only determines the log order, but can also determine the final bytecode.

However, the actual rule is **not** "whichever transformer has `addTransformer` called on it first always runs before all other transformers." Java instrumentation divides transformers into **groups with a fixed priority order**. **Within each group, the order is the registration order**. This lesson belongs to the **Transformer Chaining** section, focusing on the meaning of the phrase "within each group," how to verify it on Java 17+, and the pitfalls when groups are interleaved during registration.

## 1. Two Tiers of Ordering: Group First, Registration Time Second

According to the `java.lang.instrument.ClassFileTransformer` contract, when a class is newly loaded or redefined, the transformation steps are applied in the following order:

| Group order | Group | Registration source |
|---|---|---|
| 1 | **Retransformation-incapable** transformers written in Java | `Instrumentation.addTransformer(t)` or `addTransformer(t, false)` |
| 2 | **Retransformation-incapable** transformers at the native layer | JVMTI `ClassFileLoadHook` |
| 3 | **Retransformation-capable** transformers written in Java | `Instrumentation.addTransformer(t, true)` |
| 4 | **Retransformation-capable** transformers at the native layer | JVMTI `ClassFileLoadHook` with the appropriate capability |

These groups form a **fixed** order in the pipeline. Even if you register a Java transformer in group 3 before a Java transformer in group 1, **group 1 still runs before group 3** when the JVM defines a new class.

After the JVM selects the group, it processes the transformers **in the order they were registered within that group**:

```text
Group 1 (Java, retransformation-incapable): N1 -> N2 -> N3
                                            |
Group 2 (native, retransformation-incapable): ... (if any)
                                            |
Group 3 (Java, retransformation-capable): R1 -> R2 -> R3
                                            |
Group 4 (native, retransformation-capable): ... (if any)
                                            |
                                            v
                  Class file is verified and applied by the JVM
```

In the two Java groups, `N` and `R` are illustrative notations:

- `N`: *retransformation incapable*, registered with `false`.
- `R`: *retransformation capable*, registered with `true`.
- The trailing number (`N1`, `N2`, `R1`, `R2`) represents the **relative order within the group**, not the global `addTransformer` call order across the entire system.

Do not confuse **retransformation capable** with "has performed a retransform." This is a property of the **transformer registration**, indicating whether the callback is invoked again when `retransformClasses` occurs. Both Java groups can still be called when a class is newly loaded or redefined.

## 2. An Example of Interleaved Registration but Group-Based Execution

Suppose an agent registers four transformers in chronological order:

```java
inst.addTransformer(r1, true);   // Registration 1: group R
inst.addTransformer(n1, false);  // Registration 2: group N
inst.addTransformer(r2, true);   // Registration 3: group R
inst.addTransformer(n2, false);  // Registration 4: group N
```

This is an **illustrative snippet in `premain`**, where `inst` is `Instrumentation`, and `r1`, `n1`, `r2`, `n2` are instances implementing `ClassFileTransformer`. It is not yet a standalone Java program.

Global registration history:

```text
R1 -> N1 -> R2 -> N2
```

Callback order when the JVM newly loads a class:

```text
N1 -> N2 -> R1 -> R2
```

**Why?** The JVM groups the steps by group first. Within the retransformation-incapable group, `N1` was registered before `N2`, so `N1` runs before `N2`. Within the retransformation-capable group, `R1` was registered before `R2`, so `R1` runs before `R2`. Group N completes before group R, regardless of how the registration calls of the two groups are interleaved.

| Registration | Transformer | Group | Position on new load (with no native transformers) |
|---|---|---|---|
| 1 | `R1` | R (retransformation-capable) | 3 |
| 2 | `N1` | N (retransformation-incapable) | 1 |
| 3 | `R2` | R (retransformation-capable) | 4 |
| 4 | `N2` | N (retransformation-incapable) | 2 |

This is a **two-Java-group** table used to demonstrate the order within each group; it does not imply that native transformers do not exist in real-world applications. When JVMTI native transformers are present, the two native groups are inserted at positions 2 and 4 as shown in section 1.

### What Is the Effect of Changing Registration Order Within the Same Group?

Keep the group order fixed, but swap the registration positions of `N1` and `N2`:

```java
inst.addTransformer(r1, true);
inst.addTransformer(n2, false);
inst.addTransformer(r2, true);
inst.addTransformer(n1, false);
```

On a new load, the order becomes:

```text
N2 -> N1 -> R1 -> R2
```

Similarly, if `R2` is registered before `R1`, then within group R it becomes `R2 -> R1`. That is the core meaning of **"registration order within each group"**: group sorting does not erase the sequential ordering of registrations **within the same group**.

### Changing Cross-Group Interleaving Does Not Necessarily Change the Pipeline

Two histories:

```text
A: add(R1,true), add(N1,false), add(R2,true), add(N2,false)
B: add(N1,false), add(N2,false), add(R1,true), add(R2,true)
```

both lead to the same order in the Java pipeline:

```text
N1 -> N2 -> R1 -> R2
```

because the **relative order within N** and the **relative order within R** are both the same.

## 3. Why Within-Group Order Matters for Bytecode

`ClassFileTransformer.transform(...)` receives a class file `byte[]`. A transformer can:

- Return `null`: make no changes to the bytes at this step.
- Return a valid new `byte[]`: the JVM uses the new bytes as the input for the next step.

Conceptual model (not executable Java code):

```text
B0 = original class file
B1 = N1(B0)                  // Or keep B0 if N1 returns null
B2 = N2(B1)                  // Or keep B1 if N2 returns null
B3 = native_incapable(B2)    // If present
B4 = R1(B3)
B5 = R2(B4)
B6 = native_capable(B5)      // If present
JVM verifies and defines from the final bytes
```

Transformations are **generally non-commutative**: `N2(N1(B0))` does not necessarily yield the same result as `N1(N2(B0))`.

An example of a real-world scenario:

- Transformer `A` inserts a logging call at the beginning of a method.
- Transformer `B` finds the first instruction and inserts a check right before that instruction.
- If `B` runs first, it sees the first instruction **in the original version**.
- If `A` runs first, `B` may see the new logging instruction as the first instruction.

Therefore, registration order within the same group can change the **instrumentation site**, runtime behavior, and conflicts between libraries. To illustrate this logic safely, we can use a simulated string example:

```text
A: prepend prefix "log:"
B: convert the existing prefix to uppercase

B(A("work")) = "LOG:work"
A(B("work")) = "log:work"
```

This is only a **model for sequential operations**, not a valid operation on class file bytes. For real bytecode, you must use a tool that understands the class file format, such as ASM or Byte Buddy, and return a valid new byte array. Do not arbitrarily modify characters in a `.class` file.

### Does `return null` Break the Chain?

No. If `N1` returns `null`, the JVM still continues by calling `N2` with the bytes unmodified by `N1`. `null` means **no transformation at this step**, not "stop the entire pipeline."

If a callback throws an uncaught exception, the Javadoc also specifies that subsequent transformers may still be called and the JVM continues attempting to define/update the class. Therefore, do not use `return null` or `throw` as a mechanism to block other transformers.

## 4. Runnable Java 17+ Example: Demonstrating the Actual Order

This example creates a **startup Java agent** and a small application. The agent registers `R1`, `N1`, `R2`, `N2` in the exact interleaved order from section 2, then triggers loading a class named `demo.Probe`.

Afterward, the agent explicitly requests `retransformClasses` to further demonstrate:

- On **new load**, both N and R receive callbacks, in the order `N1, N2, R1, R2`.
- On **retransform**, N is **not called again**; the JVM automatically reapplies the previous result of group N, then calls `R1, R2` in group R's registration order.

We only log and `return null`; thus, the example tests **callback order** without needing an ASM dependency or modifying bytecode.

### 4.1. Directory Structure

```text
order-demo/
├── src/demo/
│   ├── OrderAgent.java
│   ├── Probe.java
│   └── App.java
└── agent.mf
```

### 4.2. Target Class `src/demo/Probe.java`

```java
package demo;

public final class Probe {
    public String value() {
        return "base";
    }
}
```

`Probe` is simple because its main role is to make the traversal order through the transformers visible. It has no `static` initializer that would produce unrelated extra logs.

### 4.3. Application `src/demo/App.java`

```java
package demo;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("[app] value=" + new Probe().value());
    }
}
```

Without the agent, the application prints:

```text
[app] value=base
```

### 4.4. Agent and Transformer `src/demo/OrderAgent.java`

```java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class OrderAgent {
    private OrderAgent() {
    }

    public static void premain(String agentArgs, Instrumentation inst)
            throws Exception {

        if (!inst.isRetransformClassesSupported()) {
            throw new IllegalStateException(
                    "This demo requires retransformation support");
        }

        // Intentionally interleave registrations of the two groups.
        inst.addTransformer(new TraceTransformer("R1"), true);
        inst.addTransformer(new TraceTransformer("N1"), false);
        inst.addTransformer(new TraceTransformer("R2"), true);
        inst.addTransformer(new TraceTransformer("N2"), false);

        System.out.println("[agent] registered R1,N1,R2,N2");

        // Class.forName uses a string name, avoiding a direct reference
        // to Probe.class before the transformers are registered.
        Class<?> probe = Class.forName(
                "demo.Probe",
                false,
                ClassLoader.getSystemClassLoader());

        System.out.println("[agent] load completed");

        if (!inst.isModifiableClass(probe)) {
            throw new IllegalStateException(
                    "demo.Probe cannot be retransformed");
        }

        System.out.println("[agent] retransform requested");
        inst.retransformClasses(probe);
        System.out.println("[agent] retransform completed");
    }
}

// A non-public helper class can still be placed in the same source file.
final class TraceTransformer implements ClassFileTransformer {
    private final String label;

    TraceTransformer(String label) {
        this.label = label;
    }

    @Override
    public byte[] transform(
            Module module,
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {

        if ("demo/Probe".equals(className)) {
            String phase = classBeingRedefined == null
                    ? "load"
                    : "retransform";
            System.out.println("[" + label + "] " + phase);
        }

        // Do not modify bytes: we are observing callback invocation order.
        return null;
    }
}
```

**Code explanation according to the contract:**

1. `premain` runs before `App.main`, so it can register transformers before `demo.Probe` is loaded.
2. `isRetransformClassesSupported()` is a runtime capability check. This condition requires both the JVM and an appropriate manifest, not just whether the code passes `true`.
3. Four distinct `TraceTransformer` instances, each carrying a `label`, are registered in the history `R1, N1, R2, N2`.
4. `Class.forName("demo.Probe", false, ...)` requests loading the class after registration; `false` avoids triggering class initialization if not needed. In this example, the application class loader can find `demo.Probe` from the `out` classpath.
5. The callback filters for the exact internal name `"demo/Probe"`, avoiding printing logs for the many other JDK classes loaded during startup.
6. `classBeingRedefined == null` indicates a new load; in this example, a non-null value appears during the **retransform** explicitly requested by the agent. In a general system, non-null could also be a redefine, so that condition must not be used to distinguish the two mechanisms without knowing the context.
7. All transformers `return null`, so `Probe.value()` still returns `"base"`.
8. `premain` only finishes after loading and retransformation complete; only then does the JVM run `App.main`.

This section intentionally **does not write a native transformer**. With Java `Instrumentation.addTransformer`, we directly observe the **two Java groups**; the two JVMTI native groups follow the same ordering rules according to the specification, but use different APIs/native tooling.

### 4.5. Manifest `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: demo.OrderAgent
Can-Retransform-Classes: true

```

- `Premain-Class` selects `demo.OrderAgent`.
- `Can-Retransform-Classes: true` declares the need to use retransformation; if omitted or set to `false`, `isRetransformClassesSupported()` may return `false` and `addTransformer(t, true)` will be rejected.
- The example uses a startup agent so that dynamic attach setup is not needed; the goal is to demonstrate transformer ordering.

Place a blank line at the end of the manifest as shown in the example to terminate the main section.

### 4.6. Compiling and Packaging the JAR

Open a terminal in the `order-demo` directory, with **JDK 17+**:

```bash
mkdir out

javac --release 17 -encoding UTF-8 -d out src/demo/OrderAgent.java src/demo/Probe.java src/demo/App.java

jar --create --file order-agent.jar --manifest agent.mf -C out demo/OrderAgent.class -C out demo/TraceTransformer.class
```

The commands can be run in Bash, PowerShell, or cmd; `mkdir out` is only needed once in a new directory.

The `javac` command produces two class files from the `OrderAgent.java` source: `demo/OrderAgent.class` and `demo/TraceTransformer.class`. Both must be in the agent JAR; otherwise, a missing class error may occur when `premain` instantiates the transformer. `Probe.class` and `App.class` reside on the application's `out` classpath and do not need to be packaged into the agent JAR.

Inspect the archive:

```bash
jar --list --file order-agent.jar
```

You should see `META-INF/MANIFEST.MF`, `demo/OrderAgent.class`, and `demo/TraceTransformer.class`.

### 4.7. Running and Reading Stdout

Without the agent:

```bash
java -cp out demo.App
```

Stdout:

```text
[app] value=base
```

With the agent:

```bash
java -javaagent:order-agent.jar -cp out demo.App
```

**Expected stdout when the JVM supports retransformation, no other native transformers interfere, and loading/updating succeeds:**

```text
[agent] registered R1,N1,R2,N2
[N1] load
[N2] load
[R1] load
[R2] load
[agent] load completed
[agent] retransform requested
[R1] retransform
[R2] retransform
[agent] retransform completed
[app] value=base
```

Reading the lines by phase:

- **Registration line:** `R1,N1,R2,N2` accurately reflects the order in which `addTransformer` was called.
- **Four `load` lines:** `N1,N2,R1,R2` is the actual order applied by the JVM, showing that group N precedes group R even though they were registered interleaved.
- **Two `retransform` lines:** only `R1,R2` are called again. The order between them remains the same as at registration time.
- **Application line:** `base` shows that the transformers did not modify the bytecode because all of them returned `null`.

If the JVM does not support retransformation or `Probe` is not modifiable, the example explicitly throws an error instead of printing a misleading "completed" result. This is a runtime condition checked in code, not a guessed alternative stdout result.

### 4.8. Experimenting with Changing Registration Order Within the Same Group

In `OrderAgent.premain`, swap the two N calls:

```java
inst.addTransformer(new TraceTransformer("R1"), true);
inst.addTransformer(new TraceTransformer("N2"), false);
inst.addTransformer(new TraceTransformer("R2"), true);
inst.addTransformer(new TraceTransformer("N1"), false);
```

This is a **replacement snippet for the four registration calls** in the full file, not a separate program. After recompiling and repackaging the JAR, the expected callback lines on load will be:

```text
[N2] load
[N1] load
[R1] load
[R2] load
```

If you swap the two R calls instead of the two N calls, the group R portion will swap positions accordingly. This is a direct test of the rule **"within the same group, invoke in registration order"**.

Note: there is no need to change `className`, the manifest, or the JDK to perform this test; the only change affecting the callback chain is the order of registrations.

## 5. During `retransformClasses`: Order Remains, but the Incapable Group Does Not Re-run

A point to distinguish clearly: **pipeline order** and **how many times a callback is invoked** are not the same concept.

For the retransformation process, the JVM operates according to this contract:

1. Start from the appropriate defining bytes of the class (not necessarily byte-for-byte identical to the original file on disk, as the JVM may reconstruct the constant pool).
2. **Reapply the previous results** of retransformation-incapable transformers, in the same group order, **without calling their callbacks again**.
3. Invoke the callbacks of transformers registered with `canRetransform=true` in their within-group order.
4. Verify and install the new class definition if valid.

Illustration for the Java-transformers-only case:

```text
On new load:
  B0 -> N1() -> N2() -> R1() -> R2() -> defined bytes

On retransform:
  B0' -> [saved N1 result] -> [saved N2 result]
      -> R1() -> R2() -> new bytes verified and applied
         ^         ^
       callback  callback

  N1 and N2 do NOT receive callbacks again in this phase.
```

The `B0'` notation emphasizes that the starting bytes during retransformation may not match the exact layout of the initial classfile; what matters is that the results of the incapable group are reused according to the contract.

**Why does this matter?** If `N1` inserted bytecode during the initial load, retransformation does not automatically erase its effect just because `N1` is not called again. The JVM has a mechanism to reapply the old transformations. You must not infer from a log showing only `R1,R2` that N's bytes have "disappeared."

For redefine, callbacks of the eligible groups can still run. For retransform, only the capable group runs its callbacks again. The order within each group still follows registration order in both scenarios.

In real code, only use `inst.addTransformer(t, true)` when `inst.isRetransformClassesSupported()` is `true`; this requires the `Can-Retransform-Classes: true` manifest attribute and JVM capability support. Also check `inst.isModifiableClass(clazz)` before requesting an update to a specific class.

## 6. Where Do Native Groups and JVMTI Fit?

Java instrumentation can coexist with JVM Tool Interface (JVMTI) tools written in native code. At the native layer, `ClassFileLoadHook` allows receiving events related to class bytes.

The full order of all four groups is:

```text
Java N group   ->  Native N group  ->  Java R group  ->  Native R group
  N1,N2,...          JNI/JVMTI          R1,R2,...          JNI/JVMTI
```

Within **each native group**, callbacks still follow the order in which the native transformers were registered via their mechanism. This is the order specified by the `ClassFileTransformer` Javadoc; pure Java agent authors do **not** use `Instrumentation.addTransformer` to register a native JVMTI `ClassFileLoadHook`.

Two claims to avoid making:

- "All Java transformers always finish running before native ones." **False:** the incapable native group sits between the two Java groups.
- "Registering a native transformer after all Java transformers guarantees it runs last." **False:** position is determined by **group**, and only then by registration order within the group.

For example, if a JVM has Java `N1,N2,R1,R2` plus JVMTI native `JN` (incapable) and `JR` (capable), the group-based order is:

```text
N1 -> N2 -> JN -> R1 -> R2 -> JR
```

This is a **theoretical example**, not the output of the Java program in section 4 (that program does not install a JVMTI native agent). Experimentally verifying native order requires a JVMTI agent and an appropriate native environment, which is beyond the scope of a pure Java example.

## 7. Rules That Still Hold When Changing Transformers

### 7.1. `addTransformer` Does Not Reorder Existing Steps

`Instrumentation.addTransformer(t, canRetransform)` registers a transformer for eligible future events. It does not automatically re-invoke callbacks for already-loaded classes, does not trigger retransformation, and does not reorder transformers in other groups according to global registration order.

Registering **later** does not allow a group N transformer to run after a group R transformer that was registered earlier. Group priority is still enforced as specified.

### 7.2. `removeTransformer` Affects Future Registrations

```java
boolean removed = inst.removeTransformer(transformer);
```

This is an **illustrative method snippet**, where `inst` and `transformer` are existing variables. The API returns `true` if a matching registration is found and removes it. If the **same instance** was registered multiple times, the API removes the **most recent** matching registration; therefore, developers are advised **not to register duplicate instances**.

Due to multithreaded class loading, callbacks that have already started or are scheduled may still occur after you call `removeTransformer`; do not use this call as an absolute synchronization barrier. If redefining a pipeline after removing and re-registering, you must recalculate the order for **subsequent** events, and not assume that already-loaded classes will be transformed immediately.

### 7.3. One Instance Registered Twice Is Not Two "Independent" Transformers

Although the API may allow registering the same object multiple times, doing so easily leads to:

- Duplicate logs and unintended multiple callbacks.
- Difficulty determining which registration belongs to which group.
- Removal with `removeTransformer` not necessarily removing all registrations.
- Non-idempotent bytecode modifications being applied repeatedly.

Create distinct instances, retain references when removal is needed, and manage the registration lifecycle accurately.

### 7.4. "Right Order" Does Not Mean "Right Result Every Time"

Things that can still cause a transformation to fail even when the order is completely correct:

- A transformer returns invalid class bytes, causing the JVM to report a verify/format error.
- A downstream transformer relies on structure that an earlier transformer altered.
- Incorrect class name filtering (`"demo.Probe"` instead of internal name `"demo/Probe"`).
- Invalid class transformation during retransform/redefine.
- Instrumentation code depends on the very classes it is trying to instrument, causing recursion or class loading errors.
- A callback uses unsynchronized shared state across class-loading threads.

Filter accurately by class/module/loader, validate input data, avoid mutating `classfileBuffer`, and test multiple agents together to detect conflicts.

## 8. How Callback Order Relates to Concurrency

A JVM can load **multiple classes across multiple threads**. The rule "within each group in registration order" applies **to the transformation chain of a single class definition/update event**, and does not mean every log line for all classes across the entire JVM must form a single sequential stream.

For example, if two classes `A` and `B` load concurrently, you may see output interleaved between A's events and B's events, while **for each individual class**, the transformer steps still obey the order.

Therefore, when diagnosing a real pipeline, log enough context:

- Class internal name (`className`).
- `ClassLoader` reference or identity.
- `Module` identity (if needed).
- Transformer name/ID.
- Thread/phase (`load`, `redefine`, `retransform`) when there is evidence identifying the phase.
- Hash/fingerprint of the input/output byte arrays if transformation tracing is needed.

Do not rely on a multithreaded log file without correlation IDs to conclude that the JVM's group ordering rules are violated.

## 9. Common Misconceptions

| Misconception | Reality |
|---|---|
| "Registering R1 before N1 makes R1 run first" | **False:** N always belongs to a higher-priority group than R in the Java chain |
| "Within the same group, the JVM invokes them in arbitrary order" | **False:** invoked in **registration order** |
| "There are two Java groups, so native transformers are all at the end" | **False:** native N sits between Java N and Java R |
| "During retransform, N transformers run again" | **False:** previous N results are **reapplied** without callbacks |
| "Not seeing N logs on retransform means N's effects were dropped" | **False:** the old results are still used |
| "`return null` stops all subsequent transformers" | **False:** keeps the bytes unchanged at the current step and continues |
| "Interleaved log order across multiple classes proves a pipeline bug" | **False:** must be correlated **per class event** |
| "Just changing registration order fixes an already-loaded class" | **False:** updating an existing class is a separate operation, subject to JVM constraints |
| "Every transformer has the ability to retransform" | **False:** capability depends on how it was registered and the JVM/manifest |
| "N1/N2 in group N can ignore registration order" | **False:** their order affects the bytes passed to one another |

## 10. Order-Reasoning Exercises

### Question 1. Interleaved Two-Group Registration

An agent calls:

```java
inst.addTransformer(r2, true);
inst.addTransformer(n2, false);
inst.addTransformer(r1, true);
inst.addTransformer(n1, false);
```

**What is the new-load order across the two Java groups?**

Answer: `N2 -> N1 -> R2 -> R1`. Group N precedes group R; within each group, the registration order is preserved.

### Question 2. Swapping Two Calls in the Same Group

Swap `addTransformer(n2, false)` and `addTransformer(n1, false)` in the history above without changing the two R calls. What happens?

Answer: `N1 -> N2 -> R2 -> R1`. Only the order **within group N** changes.

### Question 3. Native JVMTI in Between

The Java transformers run in group order `N1,N2,R1,R2`. In addition, there are incapable native `JN` and capable native `JR`. What is the overall order?

Answer: `N1 -> N2 -> JN -> R1 -> R2 -> JR`.

### Question 4. Retransform

In the section 4 example, why are only `R1`, `R2` printed during retransform?

Answer: `N1,N2` were registered with `false`, so they do not receive callbacks again; their old transformation results are reapplied by the JVM before calling group R.

### Question 5. Two Transformers Producing New Bytes

One group N transformer prepends an instruction to a method, and a second transformer in the same group inserts another instruction based on the current first instruction. Can swapping the order of N produce a different result?

Answer: Yes. The later step receives the post-transformation bytes from the earlier step, so operations can be **non-commutative**. You must test the entire chain and verify valid bytecode.

### Question 6. All Return `null`

If N1, N2, R1, and R2 all return `null`, can we conclude that the JVM skipped any group?

Answer: No. They still receive callbacks on a new load and preserve the input bytes at each step; `null` only states that there is no replacement byte array at that step.

### Question 7. Adding R3 After N2

Add `inst.addTransformer(r3, true)` after the initial four registrations `R1,N1,R2,N2`. What does the new-load order become?

Answer: `N1 -> N2 -> R1 -> R2 -> R3`. `R3` is at the end of **group R**.

### Question 8. Concurrent Loading of Different Classes

Two different classes are loaded concurrently on two threads; the logs show their callbacks interleaved. Can we conclude that the order within a group was broken?

Answer: No. You must group the logs by each class loading event and then check the order **within that event**.

## 11. Key Takeaways to Apply

**The two-tier rule is the core:**

1. The JVM places transformers into four **fixed groups** based on retransformation capability and Java/native.
2. **Within each group**, transformers are invoked **in registration order**.
3. Each transformer receives the byte result of the previous step; `return null` keeps the bytes unchanged and does not stop the chain.
4. During retransformation, **incapable** transformers are not called again; their previous results are reapplied, and then **capable** transformers run again in their within-group order.
5. With concurrent class loads, evaluate order **per single-class event**, not from a thread-interleaved global log.

In the pure Java example, the registration calls `R1,N1,R2,N2` must be understood as the load callback chain **`N1,N2,R1,R2`**. This is the exact way to verify "registration order within each group."

## References

- Oracle Java 17 — [`ClassFileTransformer`: transformation order and chaining](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html).
- Oracle Java 17 — [`Instrumentation`: addTransformer, removeTransformer, retransformClasses](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html).
- OpenJDK — [Java Instrumentation Package Specification](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html).
- OpenJDK — [JVM TI Specification: `ClassFileLoadHook`](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html).
