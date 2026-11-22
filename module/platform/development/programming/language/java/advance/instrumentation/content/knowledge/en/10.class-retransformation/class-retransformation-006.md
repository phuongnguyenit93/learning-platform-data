# Re-invoking Retransformation-Capable Transformers in the Correct Order

In Java Instrumentation, a class already loaded by the JVM can be **retransformed** to reapply the bytecode transformation chain without restarting the process. However, **not every registered `ClassFileTransformer` is called again**. The JVM distinguishes between **retransformation-capable** transformers (`canRetransform=true`) and **retransformation-incapable** transformers (`canRetransform=false`). When `Instrumentation.retransformClasses(...)` is called, the JVM **reapplies the previous results of the incapable group** and then **re-invokes the capable group in the specified order**, passing the output of each step as the input to the next.

This lesson belongs to the **Retransformation** topic in Java Advance — Instrumentation. The focus is on understanding accurately **which transformers are called again, what order is applied, which bytes enter each transformer**, and how to verify this with a JDK 17+ Java agent that has real execution results. In particular, do not equate **global registration order** with **execution order**, because the JVM organizes transformers into multiple priority groups.

## 1. Distinguishing load, redefine, and retransform

These three events involve `ClassFileTransformer` but have different starting points:

| Event | API or trigger source | Initial input | Transformer with `canRetransform=false` | Transformer with `canRetransform=true` |
| --- | --- | --- | --- | --- |
| **Initial class load** | `ClassLoader.defineClass` or equivalent | Bytes used to define the class | **Called** | **Called** |
| **Redefine class** | `Instrumentation.redefineClasses(...)` | New class bytes provided in `ClassDefinition` | **Called** | **Called** |
| **Retransform class** | `Instrumentation.retransformClasses(...)` | Appropriate original bytes from the most recent load or redefine | **Not called again; previous result is reapplied** | **Called again** |

Two common misconceptions:

1. `canRetransform=false` **does not mean** the transformer only runs once in the lifetime of the JVM. It can still be called when a class is newly defined or **redefined**. It simply **does not receive a callback during a retransformation pass**.
2. `canRetransform=true` **does not mean** the JVM automatically invokes the transformer continuously. The transformer is called again when a retransform operation is requested for an eligible class, or when a class is loaded/redefined according to API rules.

The term “retransform” is an **operation on an already-loaded class**, not Java reloading a class loader or creating a new class object. The JVM replaces eligible method definitions within allowed limits. Currently executing method frames may continue executing the old bytecode; new invocations follow the newly applied definition.

## 2. The four standard ClassFileTransformer order groups

The Java SE `ClassFileTransformer` contract specifies **four groups**, ordered from first to last:

| Order | Group | Registration / source |
| --- | --- | --- |
| **1** | **Retransformation-incapable Java** transformers | `inst.addTransformer(t, false)` or `inst.addTransformer(t)` |
| **2** | **Retransformation-incapable native** transformers | JVMTI `ClassFileLoadHook` without the corresponding capability |
| **3** | **Retransformation-capable Java** transformers | `inst.addTransformer(t, true)` |
| **4** | **Retransformation-capable native** transformers | JVMTI `ClassFileLoadHook` with the corresponding capability |

**Within the same group, transformers run in registration order.** Across groups, the JVM prioritizes by the group numbers above, **not** by global registration time.

Example:

~~~java
inst.addTransformer(transformerB, true);  // group 3, registered first
inst.addTransformer(transformerA, false); // group 1, registered later
inst.addTransformer(transformerC, true);  // group 3, registered last
~~~

On the **initial load** of an observed class, the order of these three **Java transformers** is:

~~~text
A (group 1) -> B (group 3) -> C (group 3)
~~~

**Not** `B -> A -> C` even though `B` was registered first. If native transformers are present, they are interleaved at **group 2 or 4 positions**, not arbitrarily placed before/after Java transformers.

When **retransforming**, the order of **new Java callbacks** is:

~~~text
B (group 3) -> C (group 3)
~~~

However, this **does not mean** `A`'s result is erased. The JVM reapplies **`A`'s existing result**, at its proper group 1 position, **before** calling `B` again. The next section clarifies this.

## 3. What exactly happens in a retransform pass?

According to the `Instrumentation.retransformClasses(...)` contract, the JVM executes a logical sequence:

1. Start from the **initial class bytes** of the most recent definition or redefinition, prior to the corresponding transformations.
2. Following the standard group order, for each **retransformation-incapable** transformer, the JVM **reuses the output recorded during the previous load/redefine**, effectively reapplying that transformation itself; **it does not call `transform(...)` on this transformer**.
3. For each **retransformation-capable** transformer, the JVM actually **calls `transform(...)` again** and supplies `classfileBuffer` as the bytes at the current point in the chain.
4. After the steps in the chain complete, the JVM **verifies and applies the final class bytes** if valid. If an error causes the operation to fail, `retransformClasses(...)` throws/reports an error; no class in that invocation is successfully retransformed.

Diagram for three Java transformers `A(false)`, `B(true)`, `C(true)`:

~~~text
INITIAL LOAD:
  B0 --[call A]--> B1 --[call B]--> B2 --[call C]--> B3
                         class is defined from B3

RETRANSFORM:
  B0' --[reapply A's result, DO NOT call A]--> B1'
      --[call B again]-----------------------> B2'
      --[call C again]-----------------------> B3'
                            verify and apply B3'
~~~

`B0'` may **not be byte-for-byte identical** to `B0`: the JVM is allowed to change the order/number of constant pool entries or certain class-file representation details without changing semantics. Do not write transformers assuming that the same constant-pool index, method order, or byte offset always persists across retransformations.

**Important:** The JVM does not by default take **B3 from the previous retransform** as the intact input for the next one. Each pass is built from the appropriate original bytes, reapplies incapable steps, and re-runs capable steps. Therefore, a transformer `B(true)` should work correctly when called multiple times and should not rely on receiving back the exact byte array it returned in the previous pass.

### “Previous result” does not mean “re-invoking old code”

Suppose `A(false)` replaced `BASE` with `ONE1` when the class was loaded. During retransform, the JVM reuses `A`'s effect so `B(true)` still sees `ONE1`; **it does not re-run `A.transform(...)` logic**. If `A` has side effects such as incrementing a counter or printing logs in its callback, those side effects do not occur again just because the class is retransformed.

Do not infer that the absence of `A`'s logs proves the class bytes “lost transformation layer A”. In a proper design, both can happen simultaneously: **A is not called again** and **A's output remains in effect**.

## 4. Capability and manifest: prerequisites before re-invoking

To use retransformation from a Java agent, **both environmental conditions** must be met:

- The agent JAR declares `Can-Retransform-Classes: true` in its manifest.
- The current JVM implementation and configuration actually support that capability.

Checking via API:

~~~java
if (!inst.isRetransformClassesSupported()) {
    // Choose load-time instrumentation or explicitly report unsupported.
    return;
}
~~~

This is an **illustrative snippet placed in code that has an `Instrumentation inst` variable**; it is not a standalone runnable program.

Once the capability is present:

~~~java
inst.addTransformer(myTransformer, true);
~~~

registers a transformer belonging to the retransformation-capable group. Conversely:

~~~java
inst.addTransformer(myTransformer);         // canRetransform defaults to false
inst.addTransformer(otherTransformer, false);
~~~

both belong to the incapable Java group. Calling `addTransformer(t, true)` when the JVM/agent does not allow retransformation may throw `UnsupportedOperationException`.

Before actually calling:

~~~java
inst.retransformClasses(Target.class);
~~~

you also need to check `inst.isModifiableClass(Target.class)`. Primitive classes and array classes are **never modifiable** per the API; additionally, there are JVM-dependent classes that cannot be modified. `isModifiableClass == true` still **does not guarantee** that all bytecode produced by a transformer is valid for retransformation: class structure rules and the JVM verifier still enforce their own restrictions.

**Note:** `Can-Retransform-Classes` resides in the **agent JAR's manifest**, not in a Java file or the application classpath. `-javaagent:...` loads the agent and invokes `premain`; it is not equivalent to running a class containing a `premain` method directly via `java ClassName`.

## 5. Complete JDK 17+ demo: proving group precedence and ordered re-invocation

This example is designed to observe **both the callback order and the actual bytes passed between steps**. It uses **three Java transformers**, but **registers them in a counter-intuitive order** to show the JVM automatically applying group ordering.

Each transformer replaces **an exact 4-byte ASCII string constant** in the target class's constant pool:

| Transformer | `canRetransform` | Input marker | Output marker |
| --- | --- | --- | --- |
| `T1-incapable` | `false` | `BASE` | `ONE1` |
| `T2-capable` | `true` | `ONE1` | `TWO2` |
| `T3-capable` | `true` | `TWO2` | `DONE` |

**Intentional registration order:** T2 first, T1 second, T3 last. Yet the processing order at load time is still **T1 → T2 → T3**, because T1 belongs to group 1 and T2/T3 belong to group 3.

When retransform is called, T1 **receives no callback**, while T2 still receives the `ONE1` marker from T1's transformation reapplied by the JVM. T3 receives the `TWO2` marker just produced by T2. The final result remains `DONE`.

### 5.1. Create RetransformOrderDemo.java

Save all of the following code in **a single file** `RetransformOrderDemo.java`. The file contains a public class serving as both the agent and application, plus a package-private class `OrderTarget`:

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.IllegalClassFormatException;
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.ProtectionDomain;

public final class RetransformOrderDemo {
    private static Instrumentation instrumentation;

    public static void premain(String args, Instrumentation inst) {
        instrumentation = inst;
        if (!inst.isRetransformClassesSupported()) {
            throw new IllegalStateException("JVM/agent cannot retransform");
        }

        // Deliberately register a capable transformer before an incapable one.
        inst.addTransformer(new MarkerTransformer("T2-capable", "ONE1", "TWO2"), true);
        inst.addTransformer(new MarkerTransformer("T1-incapable", "BASE", "ONE1"), false);
        inst.addTransformer(new MarkerTransformer("T3-capable", "TWO2", "DONE"), true);
    }

    public static void main(String[] args) throws UnmodifiableClassException {
        System.out.println("supported="
                + instrumentation.isRetransformClassesSupported());
        System.out.println("before=" + new OrderTarget().message());
        System.out.println("modifiable="
                + instrumentation.isModifiableClass(OrderTarget.class));
        instrumentation.retransformClasses(OrderTarget.class);
        System.out.println("after=" + new OrderTarget().message());
    }

    private static final class MarkerTransformer implements ClassFileTransformer {
        private final String label;
        private final String expected;
        private final String replacement;

        MarkerTransformer(String label, String expected, String replacement) {
            this.label = label;
            this.expected = expected;
            this.replacement = replacement;
        }

        @Override
        public byte[] transform(Module module, ClassLoader loader,
                String className, Class<?> classBeingRedefined,
                ProtectionDomain domain, byte[] classfileBuffer)
                throws IllegalClassFormatException {
            if (!"OrderTarget".equals(className)) {
                return null;
            }
            byte[] changed = replaceConstant(classfileBuffer, expected, replacement);
            if (changed == null) {
                throw new IllegalClassFormatException(
                        label + ": marker " + expected + " not found exactly once");
            }
            System.out.printf("%s phase=%s %s->%s%n", label,
                    classBeingRedefined == null ? "load" : "retransform",
                    expected, replacement);
            return changed;
        }
    }

    private static byte[] replaceConstant(byte[] original, String from, String to) {
        if (from.length() != to.length()) {
            throw new IllegalArgumentException("Same-length ASCII only");
        }
        byte[] copy = original.clone();
        ByteBuffer pool = ByteBuffer.wrap(copy);
        if (pool.getInt() != 0xCAFEBABE) {
            throw new IllegalArgumentException("Not a class file");
        }
        pool.position(8);
        int constantPoolCount = Short.toUnsignedInt(pool.getShort());
        byte[] expected = from.getBytes(StandardCharsets.US_ASCII);
        byte[] replacement = to.getBytes(StandardCharsets.US_ASCII);
        int found = 0;
        for (int slot = 1; slot < constantPoolCount; slot++) {
            int tag = Byte.toUnsignedInt(pool.get());
            switch (tag) {
                case 1 -> {
                    int size = Short.toUnsignedInt(pool.getShort());
                    int offset = pool.position();
                    if (size == expected.length
                            && bytesEqual(copy, offset, expected)) {
                        System.arraycopy(replacement, 0, copy, offset, size);
                        found++;
                    }
                    pool.position(offset + size);
                }
                case 3, 4, 9, 10, 11, 12, 17, 18 ->
                        pool.position(pool.position() + 4);
                case 5, 6 -> {
                    pool.position(pool.position() + 8);
                    slot++;
                }
                case 7, 8, 16, 19, 20 ->
                        pool.position(pool.position() + 2);
                case 15 -> pool.position(pool.position() + 3);
                default -> throw new IllegalArgumentException("Invalid CP tag " + tag);
            }
        }
        return found == 1 ? copy : null;
    }

    private static boolean bytesEqual(byte[] bytes, int offset, byte[] match) {
        for (int n = 0; n < match.length; n++) {
            if (bytes[offset + n] != match[n]) return false;
        }
        return true;
    }
}

final class OrderTarget {
    String message() {
        return "BASE";
    }
}
~~~

**Why does the example include a constant pool parser?** We want to prove that the later transformer receives **the bytes produced by the previous step**, not just prove ordering via println. `replaceConstant` walks the constant pool entries, finds **exactly one** 4-byte ASCII UTF-8 constant, and replaces it with the new bytes on a **copy** of the class file. If it does not find exactly one marker, the demo throws `IllegalClassFormatException` to expose test cases with broken assumptions.

The parser handles `CONSTANT_Long` and `CONSTANT_Double` occupying **two indices** in the constant pool (hence `slot++`). This is only a **demo on a simple target class**, not a general-purpose classfile manipulation library. Class files use **modified UTF-8**; the code replaces same-length ASCII because its byte encoding matches ASCII in this case. Do not use this byte-patching technique for Unicode characters, length-changing strings, multiple markers, or complex classes. In production, use a standard class-file processing library like ASM/Byte Buddy or the JDK Class-File API (JDK 24+).

### 5.2. Create agent.mf

Create a manifest file named `agent.mf` in the same directory:

~~~text
Manifest-Version: 1.0
Premain-Class: RetransformOrderDemo
Can-Retransform-Classes: true
~~~

**The manifest file needs a trailing blank line**. Declaring `Can-Retransform-Classes: true` is essential because the demo registers T2/T3 with `canRetransform=true` and actually calls `retransformClasses`. Declaring the manifest alone cannot force a JVM that lacks capability support to support it; `premain` checks and fails clearly when the condition is not met.

### 5.3. Compile, package JAR, and run

Use **JDK 17+**. In Bash or PowerShell, execute:

~~~bash
javac RetransformOrderDemo.java
jar --create --file order-agent.jar --manifest agent.mf 'RetransformOrderDemo.class' 'RetransformOrderDemo$MarkerTransformer.class'
java -javaagent:order-agent.jar -cp . RetransformOrderDemo
~~~

Class files generated by `javac`:

- `RetransformOrderDemo.class`: contains `premain` and `main`.
- `RetransformOrderDemo$MarkerTransformer.class`: transformer helper that must be included in the agent JAR.
- `OrderTarget.class`: business class **located on the application classpath**, does not need to be packaged inside the agent JAR.

Single quotes around filenames containing `$` prevent the shell from interpolating the nested class name. When running in PowerShell or Bash, the commands above work properly. If using another shell, ensure the `$` in the filename is preserved when passed to `jar`.

### 5.4. Verified stdout

**Actual result when compiled/run on Zulu OpenJDK 24.0.2:**

~~~text
supported=true
T1-incapable phase=load BASE->ONE1
T2-capable phase=load ONE1->TWO2
T3-capable phase=load TWO2->DONE
before=DONE
modifiable=true
T2-capable phase=retransform ONE1->TWO2
T3-capable phase=retransform TWO2->DONE
after=DONE
~~~

Key lines:

1. `supported=true`: the test environment has the retransformation capability.
2. `T1-incapable phase=load` appears **before** T2 even though T2 was registered first: **priority groups determine execution order**.
3. `T2-capable phase=load ONE1->TWO2`: T2 receives data already transformed by T1.
4. `T3-capable phase=load TWO2->DONE`: T3 receives the new data from T2.
5. `before=DONE`: class `OrderTarget` is defined with the final value.
6. `modifiable=true`: the target class on the test JVM can be retransformed.
7. **There is no T1 line at phase=retransform.** This is expected because T1 was registered with `false`.
8. T2 still sees `ONE1` at phase=retransform: **T1's effect was reapplied by the JVM, even though T1 was never called again**.
9. T3 still receives `TWO2` from T2, so `after=DONE`. This proves the T2 → T3 order within the capable group.

The example also shows a useful detail: `classBeingRedefined == null` on initial load, and non-`null` when the class is retransformed. The logging code uses the `retransform` label when the parameter is non-`null` **because the demo does not perform redefine**. In a general agent, a non-`null` parameter can also appear during **redefine**, so do not rely solely on this condition to strictly distinguish the two events.

If using a JVM that does not support retransformation, the example intentionally fails in `premain`; the output above is **not guaranteed** to appear on every JVM. The class file must still compile with Java 17+, but retransform execution depends on the manifest/JVM.

## 6. Deep dive into reapplying incapable transformers

The most important point to remember is that **replay is not a callback**. Registering T1 with `false` in the Java agent causes T1's callback to be skipped during retransform; however, the JVM still reuses the result produced during the most recent load or redefine.

Simplified example following the demo:

~~~text
Initial class source:         OrderTarget.message() -> "BASE"

Load:
    T1(false): BASE -> ONE1
    T2(true):  ONE1 -> TWO2
    T3(true):  TWO2 -> DONE

Retransform:
    JVM automatically reapplies T1's old result: BASE -> ONE1
    T2(true) is called again:                   ONE1 -> TWO2
    T3(true) is called again:                   TWO2 -> DONE
~~~

This has an important consequence when designing interdependent transformations: if T2 relies on a marker created by T1 at load time, T1 not running again **does not necessarily break** T2. The replay mechanism itself keeps the chain supplied with the appropriate input. Conversely, if T2 **expects to receive the DONE output from the previous retransform** and only appends a change to DONE, T2 may fail because its actual input bytes in this example are **ONE1**, not DONE.

Notable practical behaviors:

- If T1 randomly computes a marker at load time, its **applied** result is reused; no new random value is computed merely because a retransform occurs.
- If T1 increments a counter in its callback, that counter does not increment when only retransforming the class, because T1 is not called again.
- If T1 performs no transformation (returns `null` at load time), its “result” is also the **unchanged input**, not a newly allocated byte array.
- If a class was previously **redefined**, the replay baseline follows the **most recent redefine** rather than permanently following the original `.class` file on disk.

The API does not promise that all class-file byte details are identical across passes, so check the **semantics and structure** of the result rather than comparing fixed constant pool indices.

## 7. What if a transformer returns null, returns bytes, or throws an error?

Within the same chain:

| Behavior of a retransformation-capable transformer | Input to the next transformer | Meaning |
| --- | --- | --- |
| Returns a new `byte[] B` array | Contents of array B | Transformation is passed to the next step |
| Returns `null` | Current bytes immediately before that transformer | No change at this step |
| Throws an exception while executing `transform` | The JVM still continues the remaining transformers per contract; the effect of this step is like returning `null` | Do not use exceptions as a mechanism to halt the pipeline |
| Returns malformed class bytes | Subsequent steps may still be called, but the final class bytes may be rejected by the verifier | The `retransformClasses` call may fail |

For an incapable transformer, it **does not run again** in this pass, so there is no **new** `return` value or exception from its callback. The JVM reapplies the effect from the previous pass.

The `ClassFileTransformer` contract requires **not modifying the `classfileBuffer` array provided by the JVM directly**. If transforming, create a new array and return it. The demo did this properly with `original.clone()`. If there is no class to modify, `return null` is correct:

~~~java
@Override
public byte[] transform(Module module, ClassLoader loader, String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain domain, byte[] classfileBuffer) {
    if (!"com/example/OrderService".equals(className)) {
        return null;
    }
    return transformKnownClass(classfileBuffer);
}
~~~

This is **illustrative code** inside a class implementing `ClassFileTransformer`; `transformKnownClass(byte[])` must be provided by the application. Returning `null` to leave the current class unchanged differs from returning a byte copy and unnecessarily altering logic.

When retransform/redefine fails due to invalid final bytes, the classes participating in the same `retransformClasses(...)` call are **not partially updated** per the API contract. This does not roll back any side effects that transformer code performed before failing (such as logging or incrementing counters), because those side effects live outside the class bytes update.

## 8. Registration order and callback order: practical scenarios

### Scenario A: two capable Java transformers

~~~java
inst.addTransformer(first, true);
inst.addTransformer(second, true);
~~~

Both belong to **group 3**. For the same retransformed class, `first.transform(...)` is called before `second.transform(...)`; the bytes returned by `first` become the input to `second`. If `first` returns `null`, `second` receives the input that `first` saw.

### Scenario B: one incapable transformer present

~~~java
inst.addTransformer(firstCapable, true);
inst.addTransformer(secondIncapable, false);
~~~

On load/redefine, `secondIncapable` belongs to group 1, so it is called **before** `firstCapable` despite being registered later. On retransform, `second`'s previous effect is reapplied **before** calling `first` again.

### Scenario C: two incapable transformers

~~~java
inst.addTransformer(incapableA);
inst.addTransformer(incapableB, false);
~~~

Both belong to group 1, so on load/redefine they run in order A → B. During a retransform pass, **there are no new callbacks for either A or B**, but the previous outputs of both are reapplied **in the exact chain order** before capable transformers.

### Scenario D: Java agent plus native JVMTI agent

The order is not simply “all Java agents before all native agents”. The true order is **Java incapable → native incapable → Java capable → native capable**. If a capable Java transformer T2 receives input already processed by an incapable native transformer, that is a consequence of group 2 being applied before group 3. When multiple agents intervene, inspect **all groups**, not just the logs of your own Java agent.

### Scenario E: changing order via remove/add

`Instrumentation.removeTransformer(transformer)` can unregister a transformer for future class definitions. However, the API warns that due to multithreaded class loading, a transformer **may still receive callbacks after removal** due to races. Do not rely on runtime remove/add to guarantee strict synchronous ordering. It is better to define an ordered pipeline at agent startup, using a single internal coordinating transformer if multiple tightly coupled steps are needed.

## 9. Do not infer cross-class/thread order from global logs

The order **within a transformation chain for a single class** is specified by the API. However, the JVM can load/retransform multiple classes, including from different threads; callback logs from different classes **can interleave**.

Log example:

~~~text
T1(OrderA)
T1(OrderB)
T2(OrderA)
T2(OrderB)
~~~

does not say that for OrderA, T2 ran before T1. It only shows events for **two different classes** interleaving. To analyze order, attach at least the following to logs:

- `className` as an **internal name** (using `/`, e.g., `com/example/OrderA`).
- Class loader and module to distinguish classes with the same name.
- Transform session ID or load/retransform phase tracked by the agent.
- Transformer name and callback order **within the same class invocation**.
- Optional checksum/length of before-and-after bytes (no need to log full bytecode).

Because `ClassFileTransformer.transform(...)` can be invoked concurrently by the JVM, do not arbitrarily share mutable counters/state across threads. If metrics are needed, use proper synchronization; if only testing order in a demo, intentionally retransform **one** class on the main thread so stdout is easy to verify.

## 10. Two capability error modes that are easily conflated

### 10.1. Having capability but the class is not modifiable

If `inst.isRetransformClassesSupported() == true` but `inst.isModifiableClass(type) == false`, a registered capable transformer still cannot retransform that class. For example, primitive and array classes are never modifiable; many JVM-defined classes have their own restrictions.

Check:

~~~java
if (inst.isRetransformClassesSupported()
        && inst.isModifiableClass(target)) {
    inst.retransformClasses(target);
}
~~~

This is an **illustrative code snippet** with `Instrumentation inst`, `Class<?> target`, and appropriate `UnmodifiableClassException` handling in the outer scope. **Both checks are necessary**, yet errors caused by the transformer or class bytes must still be handled.

### 10.2. Modifiable class but missing capability

If `isModifiableClass(type) == true` while `isRetransformClassesSupported() == false`, `retransformClasses(type)` cannot be called successfully. Whether a class is modifiable in general and whether the environment supports retransformation are **two different questions**.

A manifest missing `Can-Retransform-Classes: true` is a common cause, alongside an unsupported JVM. Using `Can-Redefine-Classes` is a **different** capability and cannot substitute for `Can-Retransform-Classes`.

## 11. Class redefinition limits do not disappear just because the order is right

Correct callback ordering **does not guarantee** the JVM will accept the final bytes. Retransformation has class structure constraints; on HotSpot/JVM TI, replacing method bodies is generally valid, but you cannot arbitrarily add/remove fields/methods, change method signatures, or change the superclass in an already-loaded class.

Keep in mind:

- Transformers must produce a **valid class file**, matching the class file version and JVM verifier.
- Restricted structural attributes must be preserved during retransform/redefine.
- Stack maps, exception tables, labels, and branch offsets must be resolved if inserting complex bytecode.
- If a class currently has running methods, **old frames may continue using old bytes**, while new invocations use the new definition. Immediate observations must account for this.
- Retransformation **does not automatically re-run static initializers** and does not reset static fields or the state of existing objects.
- Transformers are called during request processing, **before** the JVM verifies and applies the final bytes. A “transform succeeded” log is not equivalent to “class installed successfully”.

In the demo, replacing a same-length ASCII constant does not alter class structure. For production bytecode, use a supporting framework and test on the exact target JVM.

## 12. Diagnosing issues from callback traces

| Symptom | Likely valid explanation | Check |
| --- | --- | --- |
| `false` transformer prints no log on retransform | **Per contract**: previous result is reused | Inspect the bytes received by the next capable transformer |
| `true` transformer prints no log on retransform | May be unregistered, wrong class filter, no retransform occurred, or failed before entering callback | Check manifest, capability, target, log wrapper |
| Transformer registered earlier runs later | Belongs to a **different group** | Print group/canRetransform, compare against 4-group order |
| T2 does not see marker created by T1 | T1 returned `null`/errored, or wrong group/registration order, or unexpected class input | Compare markers/checksums between steps |
| T2 sees marker from initial load but T1 did not run | **Replay mechanism for incapable transformer results** | Do not treat this as a bug |
| Results accumulate after multiple retransforms | Non-idempotent transformer or wrong assumption about input bytes | Check replay mechanism; run retransform multiple times |
| Callback runs fine but method still returns old value | Old frame may be running, class bytes did not actually change, or redefine/retransform failed | Check call result, new method invocations, post-transform bytecode |
| `UnsupportedOperationException` | Missing capability or unsupported class modification | Manifest, `isRetransformClassesSupported`, JVM TI restrictions |
| `UnmodifiableClassException` | Target class cannot be modified | `isModifiableClass(target)` |
| `ClassFormatError` / `VerifyError` | Corrupted final bytecode | Verify final output and each step, stack maps |
| Order right on machine A, wrong on machine B | Another native agent present, changed registration order, different JVM | List Java/native agents, groups, and timing |
| Strange interleaved logs | Multiple classes/threads are being transformed | Attach class loader, module, thread, invocation ID |

**Recommended debugging workflow:** before modifying bytes, run a pass with a **log-only** transformer returning `null` to verify grouping and callbacks. Then add a simple transformation, verify the class; finally chain interdependent transformer steps together. Avoid logging every class in production: it is both slow and risks reentrancy issues.

## 13. Testing to avoid accidentally breaking the pipeline

Beyond the single-run test in the demo, a good regression test suite for retransformation should include:

1. **Initial load:** expected callback order of both incapable and capable groups.
2. **One retransform:** only capable callbacks are invoked; incapable ones are not called again.
3. **Replay:** bytes passed into the first capable transformer still contain the previous effect of incapable ones.
4. **Multiple retransforms:** run at least twice, confirming output does not accumulate erroneously.
5. **Return null:** a capable transformer returns `null`; the subsequent transformer receives the exact current bytes.
6. **Chained transformation:** previous output is next input, in exact capable order within the same group.
7. **Agent mismatch:** manifest missing capability; detected before calling retransform.
8. **Unmodifiable class:** do not attempt to modify `int[].class` or classes marked `false` by the JVM.
9. **Invalid output:** generate invalid bytes in an isolated test environment to confirm errors are reported properly without pretending the class updated.
10. **Loaded/active frames:** understand that code already running before transform may not see new method bytes immediately in the current frame.

When testing multiple transformers, **do not rely solely on global log line counts** to prove order. Match **target class, phase, and markers/bytecode between steps**, as in the `BASE → ONE1 → TWO2 → DONE` demo.

## 14. Self-check exercises

**Q1.** Register `T2(true)` before `T1(false)`, both Java. When a new class is loaded, which callback runs first?

**Q2.** There are two Java transformers `A(true)` then `B(true)`. When retransforming a class, what callback order is guaranteed within the same group? If A returns `null`, what does B receive?

**Q3.** `X(false)` previously changed marker `BASE → ONE1`. On retransform, `X.transform(...)` does not appear in the log, yet transformer `Y(true)` still sees `ONE1`. Is there a contradiction?

**Q4.** A Java transformer `A(false)` and a native transformer `N(false)` both process a class. Which group goes first?

**Q5.** You call retransform twice. Should a capable transformer assume it receives the final output of the previous pass as its input?

**Q6.** `isModifiableClass(MyClass.class)` returns `true`, but `isRetransformClassesSupported()` returns `false`. Can `retransformClasses(MyClass.class)` be called?

**Q7.** If capable T1 throws `IllegalClassFormatException` in its callback, is capable T2 guaranteed **not** to be called?

**Q8.** A class has an active frame in one thread. You retransform successfully in another thread. Does the current frame necessarily switch bytecode mid-execution?

**Q9.** An incapable transformer was called at load time. Later, a tool performs `redefineClasses(...)` and subsequently calls `retransformClasses(...)`. Which event is the input/replay baseline tied to?

**Q10.** The agent receives three log events in order `A(T1)`, `B(T1)`, `A(T2)`. Can we conclude that T2 ran “out of order” for class A?

### Answers

1. **T1(false)**, because the Java incapable group is group 1, before the Java capable group, which is group 3.
2. **A then B** in registration order. If A returns `null`, B receives the **current bytes** that A just saw, not necessarily reverting to the initial original bytes if earlier transformations occurred before A.
3. **No.** The JVM reapplies X's previous output without calling X again, and then calls Y.
4. The **Java incapable (1)** group goes before the **native incapable (2)** group.
5. **No.** Replay starts from the appropriate original bytes and applies the results of incapable transformers; capable ones are re-invoked on that pass's input, not necessarily the final output of the previous pass.
6. **No.** Both JVM/agent capability and a modifiable class are required.
7. **No.** Per the contract, an exception in `transform` does not halt the chain; the JVM still invokes subsequent transformers.
8. **No.** Active frames may continue executing old bytecode; new calls use the newly applied definition.
9. To the **most recent redefine** (and the transformer results recorded relative to that definition), not necessarily the initial load.
10. **No.** Logs can interleave between classes A and B; within class A, the T1-before-T2 order is still correct.

## 15. Key takeaways

**The most accurate rules:**

- **On load/redefine:** run groups in order **Java incapable → native incapable → Java capable → native capable**, and by registration order within each group.
- **On retransform:** **no callbacks** for the incapable group; **replay their previous results** at their proper positions; **invoke callbacks for the capable group** by group order and registration order.
- **Bytes form a sequential chain**: the output of the previous step is the input to the next; `null` keeps the current bytes.
- **Do not blindly accumulate capable output from the previous pass**; each retransform pass rebuilds from the appropriate byte source and applies the chain per the API.
- **Correct order is not enough**: you also need manifest/capability, a modifiable class, valid bytes, JVM TI compliance, and testing on a real runtime.

## 16. Official technical documentation

- [Java SE 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): four order groups, passing `classfileBuffer`, capable/incapable, `null`/exceptions, obligation not to modify the input array.
- [Java SE 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `isRetransformClassesSupported`, `isModifiableClass`, `retransformClasses`, and how previous transformations are replayed.
- [Java SE 21 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): agent JAR manifest, `premain`, and capability conditions.
- [Java SE 21 — Java Virtual Machine Tool Interface (JVMTI)](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html): native `ClassFileLoadHook`, RetransformClasses capability, and class structure constraints.
