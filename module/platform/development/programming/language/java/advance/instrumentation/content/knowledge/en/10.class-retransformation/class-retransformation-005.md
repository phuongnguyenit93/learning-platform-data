# Reusing Results of Retransformation-Incapable Transformers Without Re-invoking Them

In Java Instrumentation, `Instrumentation.retransformClasses(...)` can reprocess a class **already loaded by the JVM**. However, not every transformer that previously affected the class is called again. For a transformer registered with `Instrumentation.addTransformer(transformer, false)`, the JVM **automatically reapplies the effect of the previous transformation** during retransformation **without invoking that transformer's `transform(...)` method again**.

This is a crucial rule when multiple Java agents or multiple `ClassFileTransformer` instances participate in a transformation chain.

**Two misconceptions to avoid:**

- "A transformer that does not support retransform does not run again, so its previous instrumentation result is lost." **False**: the old result is still semantically reapplied.
- "Every retransform reruns all transformers on the bytecode installed in the previous round." **False**: the JVM starts again from the **initial class-file bytes** corresponding to the most recent load or redefine, reapplies the results of incapable transformers, and then invokes the capable group.

This lesson fully explains the byte source, callback timing, transformation order, capability boundaries, and a Java 17+ example that actually modifies the constant pool to verify both **class behavior** and **callback counts**.

## 1. What does `canRetransform=false` actually mean?

The two overloads of `Instrumentation`:

~~~java
void addTransformer(ClassFileTransformer transformer);
void addTransformer(
        ClassFileTransformer transformer,
        boolean canRetransform);
~~~

The single-parameter registration is **equivalent to**:

~~~java
inst.addTransformer(transformer, false);
~~~

These are API signatures and a fragment with `inst` and `transformer` variables already declared; it is not a standalone runnable program.

| Registration | Group name | At class load | At `redefineClasses` | At `retransformClasses` |
|---|---|---|---|---|
| `addTransformer(t)` | *Retransformation incapable* | Calls `t.transform` | Calls `t.transform` | **Not called**; reuses previous result |
| `addTransformer(t, false)` | *Retransformation incapable* | Calls `t.transform` | Calls `t.transform` | **Not called**; reuses previous result |
| `addTransformer(t, true)` | *Retransformation capable* | Calls `t.transform` | Calls `t.transform` | **Re-invokes** `t.transform` |

An **incapable** transformer is still fully able to modify bytecode at **load** or **redefine** time. The word "incapable" only emphasizes that it **does not receive callbacks during retransform**, rather than forbidding it from producing new bytecode.

The `canRetransform` attribute is tied to the **transformer's registration**, not a fixed flag on the `Class<?>` object itself. The same class can be transformed sequentially by both `false` and `true` transformers.

## 2. Official procedure when calling `retransformClasses`

Example fragment:

~~~java
inst.retransformClasses(Target.class);
~~~

Assume `inst` is the `Instrumentation` provided by the JVM, and `Target.class` has already been loaded. According to the `Instrumentation.retransformClasses` contract:

1. The JVM starts from the **initial class-file bytes**: the bytes from the initial class definition or the bytes supplied in the **most recent `redefineClasses`**, prior to transformations.
2. For each transformer registered with **`canRetransform=false`**, the JVM reuses the result of its `transform` call from the **corresponding class load or redefine**. The effect is identical to reapplying the old transformation **unchanged**, but **without invoking the callback**.
3. For each transformer registered with **`canRetransform=true`**, the JVM **actually re-invokes** `transform(...)` in chain order.
4. The final result is verified and installed as the new class definition if valid; if the operation fails, the JVM throws the corresponding error.

Diagram with two Java transformers A and B:

~~~text
When Target is loaded:
Original bytes B0
  └── A(false).transform(B0) → B1       [A is called]
      └── B(true).transform(B1) → B2   [B is called]
          └── JVM defines Target using B2

On 1st retransform:
Initial bytes B0 (does not start from B2)
  └── reuse effect of A → B1           [A is NOT called]
      └── B(true).transform(B1) → B3   [B is called again]
          └── JVM installs Target from B3

On 2nd retransform:
Initial bytes B0
  └── reuse effect of A → B1           [A is NOT called]
      └── B(true).transform(B1) → B4   [B is called again]
          └── JVM installs Target from B4
~~~

`B0…B4` are only logical labels for class-file byte arrays, not existing Java variable names. Results `B3` and `B4` may be the same or different depending on B's logic. **The second retransform does not automatically take output B3 as its base and stack every transformation on top of it.**

### What does "reusing the old result" mean?

The specification states that **the result from the previous class load or redefine** is reused in the chain. That does not require an agent author to know any physical **cache** structure the JVM maintains. Treat this as a **bytecode semantics guarantee**, not a memory guarantee or `byte[]` array object-identity guarantee.

More importantly: if A(false) computes based on a configuration that changes at runtime, **changing the configuration after the class is loaded and calling retransform will not make the JVM call A again**. For an already processed class, the JVM preserves A's effect from the previous load/redefine, regardless of what A's current logic would return if called.

## 3. Why distinguish "bytecode result" from "callback count"?

Suppose the original class has:

~~~java
public static String message() {
    return "INIT";
}
~~~

The agent registers:

- **A(false)**: when `Target` is loaded, changes the literal `"INIT"` to `"BASE"` in `CONSTANT_Utf8_info`.
- **B(true)**: on load it only observes and returns `null`; on retransformation it changes `"BASE"` to `"LIVE"`.

All literals are **4 ASCII bytes** long, so in this controlled experiment an entry in the constant pool can be replaced without changing the length of the class file.

At load time:

~~~text
Original Target.message() → "INIT"
      │
      ▼ A(false) runs, changes "INIT" → "BASE"
      ▼ B(true) runs, returns null
Target.message() after load → "BASE"
~~~

At retransform time:

~~~text
Base bytes corresponding to "INIT"
      │
      ▼ JVM automatically reapplies A's effect → "BASE"
        [does not call A.transform again]
      ▼ B(true) runs, changes "BASE" → "LIVE"
Target.message() after retransform → "LIVE"
~~~

A's callback count **does not increase**, yet the `"BASE"` effect from A **remains B's input**. To prove this, one must inspect **the behavior of `Target.message()`** alongside the callback counters. Only printing A's logs could mislead learners into thinking A no longer has any effect.

## 4. Java 17+ hands-on: a `false` transformer actually modifies the class file

The example uses **JDK 17 or later**, with no external libraries. The Java files are in the **default package** to reduce noise, with no requirement for production package layout. Every file is self-contained and has the exact class name.

Directory tree:

~~~text
retransform-reuse/
├── Target.java
├── CpPatch.java
├── DemoAgent.java
├── DemoApp.java
├── MANIFEST.MF
└── out/              created by javac
~~~

### 4.1. `Target.java`

~~~java
public final class Target {
    public static String message() {
        return "INIT";
    }
}
~~~

This is the target class; it is loaded by `Class.forName("Target")` **after** the agent registers the two transformers. We do not modify method signatures, fields, or hierarchy.

### 4.2. `CpPatch.java` — finding the exact UTF-8 constant pool entry

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public final class CpPatch {
    public static byte[] replaceUtf8(
            byte[] source, String oldValue, String newValue) {
        byte[] oldBytes = oldValue.getBytes(StandardCharsets.UTF_8);
        byte[] newBytes = newValue.getBytes(StandardCharsets.UTF_8);
        if (oldBytes.length != newBytes.length) {
            throw new IllegalArgumentException(
                    "replacement must have same UTF-8 length");
        }

        byte[] output = source.clone();
        ByteBuffer bb = ByteBuffer.wrap(output);
        if (bb.getInt() != 0xCAFEBABE) {
            throw new IllegalArgumentException("not a class file");
        }
        bb.getShort(); // minor version
        bb.getShort(); // major version
        int entries = Short.toUnsignedInt(bb.getShort());
        int replacements = 0;

        for (int i = 1; i < entries; i++) {
            int tag = Byte.toUnsignedInt(bb.get());
            switch (tag) {
                case 1 -> {
                    int length = Short.toUnsignedInt(bb.getShort());
                    int offset = bb.position();
                    if (length == oldBytes.length
                            && Arrays.equals(
                                Arrays.copyOfRange(
                                    output, offset, offset + length),
                                oldBytes)) {
                        System.arraycopy(
                                newBytes, 0, output, offset, length);
                        replacements++;
                    }
                    bb.position(offset + length);
                }
                case 3, 4, 9, 10, 11, 12, 17, 18 ->
                    bb.position(bb.position() + 4);
                case 5, 6 -> {
                    bb.position(bb.position() + 8);
                    i++; // long/double occupies two slots
                }
                case 7, 8, 16, 19, 20 ->
                    bb.position(bb.position() + 2);
                case 15 ->
                    bb.position(bb.position() + 3);
                default -> throw new IllegalArgumentException(
                        "unknown constant tag " + tag);
            }
        }

        if (replacements != 1) {
            throw new IllegalArgumentException(
                    "expected one literal; found " + replacements);
        }
        return output;
    }
}
~~~

Brief explanation and notes:

1. Always create `byte[] output = source.clone()`; **do not modify in place** the `classfileBuffer` array passed by the JVM to the transformer.
2. `ByteBuffer` reads the class-file magic `0xCAFEBABE`, version, and constant pool. The `tag` values indicate the entry length to read/skip.
3. Specifically for **`CONSTANT_Utf8` (tag 1)**, the demo only replaces a full-matching ASCII string **of the same length**; `replacements != 1` is treated as an error.
4. CONSTANT_Long/Double occupies two slots in the constant pool, so `i` must be incremented one extra time.
5. This is a **minimal parser**, suited for experimenting with `"INIT"`, `"BASE"`, `"LIVE"`; it is not a production bytecode tool. It does not support changing entry lengths, general modified UTF-8, labels, attributes, stack map frames, or arbitrary method bodies. For complex transformations, use ASM, Byte Buddy, or the Java Class-File API for the appropriate JDK version.

By only replacing the value of a UTF-8 literal of the same length, the output class file preserves the exact identity and structure of `Target`.

### 4.3. `DemoAgent.java` — two transformers and counters

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.concurrent.atomic.AtomicInteger;

public final class DemoAgent {
    private static Instrumentation instrumentation;
    private static final AtomicInteger frozen = new AtomicInteger();
    private static final AtomicInteger dynamic = new AtomicInteger();

    public static void premain(String options, Instrumentation inst) {
        instrumentation = inst;
        if (!inst.isRetransformClassesSupported()) {
            System.out.println("retransform=false");
            return;
        }
        inst.addTransformer(new FrozenTransformer(), false);
        inst.addTransformer(new DynamicTransformer(), true);
        System.out.println("retransform=true");
    }

    public static Instrumentation inst() { return instrumentation; }

    public static void counts() {
        System.out.println(
                "calls frozen=" + frozen.get()
                + " dynamic=" + dynamic.get());
    }

    static final class FrozenTransformer
            implements ClassFileTransformer {
        @Override
        public byte[] transform(
                Module module, ClassLoader loader, String name,
                Class<?> existingClass, ProtectionDomain domain,
                byte[] bytes) {
            if (!"Target".equals(name)) return null;
            System.out.println(
                    "frozen call=" + frozen.incrementAndGet());
            return CpPatch.replaceUtf8(bytes, "INIT", "BASE");
        }
    }

    static final class DynamicTransformer
            implements ClassFileTransformer {
        @Override
        public byte[] transform(
                Module module, ClassLoader loader, String name,
                Class<?> existingClass, ProtectionDomain domain,
                byte[] bytes) {
            if (!"Target".equals(name)) return null;

            if (existingClass == null) {
                System.out.println(
                        "dynamic load call=" + dynamic.incrementAndGet());
                return null;
            }

            System.out.println(
                    "dynamic revisit call=" + dynamic.incrementAndGet());
            return CpPatch.replaceUtf8(bytes, "BASE", "LIVE");
        }
    }
}
~~~

During load, **A(false)** changes `"INIT"` to `"BASE"` and **B(true)** only logs. During retransform, A does **not** receive a callback, while B receives a callback and changes `"BASE"` to `"LIVE"`.

`existingClass == null` means the callback is processing a **newly defined class**; when it is non-null, the callback occurs during **redefine or retransform**. You cannot rely solely on that parameter to distinguish the two operations. Since this program only calls `retransformClasses`, the `revisit` log can be accurately explained as retransform.

`name` is the **JVM internal name**, here `"Target"` because the class is in the default package. For package `demo`, the name would look like `"demo/Target"`. Filtering by name prevents the program from modifying/logging JDK classes being loaded. `AtomicInteger` provides a thread-safe callback counter under concurrent access.

### 4.4. `DemoApp.java` — observing the class across three points in time

~~~java
import java.lang.instrument.Instrumentation;
import java.lang.reflect.Method;

public final class DemoApp {
    public static void main(String[] args) throws Exception {
        Instrumentation inst = DemoAgent.inst();
        if (!inst.isRetransformClassesSupported()) {
            System.out.println("skipped");
            return;
        }

        Class<?> clazz = Class.forName("Target");
        Method message = clazz.getMethod("message");
        System.out.println("initial=" + message.invoke(null));
        DemoAgent.counts();

        if (!inst.isModifiableClass(clazz)) {
            System.out.println("unmodifiable");
            return;
        }

        inst.retransformClasses(clazz);
        System.out.println("afterFirst=" + message.invoke(null));
        DemoAgent.counts();

        inst.retransformClasses(clazz);
        System.out.println("afterSecond=" + message.invoke(null));
        DemoAgent.counts();
    }
}
~~~

`Class.forName("Target")` is the intentional moment the demo loads the target class. `getMethod("message")` and `invoke(null)` retrieve the result **of the method executing in the JVM**, not merely reading a file copy on disk.

`isModifiableClass` checks the modifiability of a **specific class**. It differs from `isRetransformClassesSupported()`, which asks whether the **JVM/agent has the capability**. If the JVM or the target class does not support it, the demo exits safely instead of requesting retransform.

### 4.5. `MANIFEST.MF`

~~~text
Manifest-Version: 1.0
Premain-Class: DemoAgent
Can-Retransform-Classes: true

~~~

This is the manifest inside the agent JAR. There must be a trailing blank line. `Can-Retransform-Classes: true` **requests** the capability but does not guarantee that every JVM provides it. It is **different from** `Can-Redefine-Classes`, which is used when you want to replace a definition with bytes passed to `redefineClasses`.

### 4.6. Compiling and running

From the `retransform-reuse` directory, create `out`.

With Bash/Git Bash:

~~~bash
mkdir -p out
~~~

With PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
~~~

Run the JDK 17+ commands:

~~~bash
javac --release 17 -d out Target.java CpPatch.java DemoAgent.java DemoApp.java
jar --create --file demo.jar --manifest MANIFEST.MF -C out .
java -javaagent:demo.jar -cp demo.jar DemoApp
~~~

`javac` also generates `DemoAgent$FrozenTransformer.class` and `DemoAgent$DynamicTransformer.class`. `jar ... -C out .` automatically packages inner classes, so there is no need to list `$...` names explicitly. Java runs with **`-javaagent` before the main class name**; no `Main-Class` is needed in the manifest because we use `-cp demo.jar DemoApp`.

**Verified stdout when run on JDK 24 with `javac --release 17`:**

~~~text
retransform=true
frozen call=1
dynamic load call=1
initial=BASE
calls frozen=1 dynamic=1
dynamic revisit call=2
afterFirst=LIVE
calls frozen=1 dynamic=2
dynamic revisit call=3
afterSecond=LIVE
calls frozen=1 dynamic=3
~~~

**Exact output analysis:**

- When loading `Target`, A produces `BASE` and B is called for the first time, without modifying the bytes.
- `initial=BASE` confirms **A actually took effect**.
- The first `retransformClasses(clazz)` has no `frozen call=2` log. Even so, B receives a base with A's effect reapplied, finds `BASE`, and produces `LIVE`, leading to `afterFirst=LIVE`.
- The second `retransformClasses(clazz)` also **does not call A again**. B still receives a base containing `BASE`, hence `afterSecond=LIVE`.
- Total callbacks for A **remain 1**, while B increases from 1 to 3, as shown by `calls frozen=1 dynamic=3`.

If the JVM lacks the retransformation capability, the demo may print `retransform=false` and then `skipped`; the lines on the success path depend on the JVM's capabilities. If the byte replacement is invalid, a class format error or different result may occur. Do not treat the fixed stdout above as a promise across all JVM versions/distributions.

## 5. Evidence table: callback does not rerun yet the effect remains

| Operation | Call A(false)? | Call B(true)? | Effect used | Method behavior |
|---|---|---|---|---|
| Load `Target` | Yes, 1st time | Yes, 1st time | A: `INIT→BASE`; B: unchanged | `BASE` |
| 1st Retransform | **No** | Yes, 2nd time | Replay A: `BASE`; B: `BASE→LIVE` | `LIVE` |
| 2nd Retransform | **No** | Yes, 3rd time | Replay A: `BASE`; B: `BASE→LIVE` | `LIVE` |

The key takeaway: **no log from A does not prove A lost its effect**. In the example, B successfully modifies the `"BASE"` literal in both rounds because the JVM reapplied A's old effect in the pipeline.

A test using two transformers that always `return null` would illustrate callbacks but **would not prove that the bytecode effect is preserved**. That is why the example uses an actual byte modification and then verifies method behavior.

## 6. What if a `false` transformer returns `null`?

`ClassFileTransformer` allows:

~~~java
return null; // do not modify classfileBuffer at this step
~~~

When A(false) returns `null` during load/redefine, the JVM treats step A as **not modifying the bytes**. In subsequent retransforms, it **does not call A again** and reapplies that exact "no-change" effect from the previous step.

~~~text
Load:
B0 -- A(false) returns null --> B0 -- B(true) --> B1

Retransform:
B0 -- reuse A's previous no-op, no callback --> B0
   -- B(true) --> B2
~~~

Suppose A depends on a `featureFlag` and at load time the flag is off, so A returns `null`. After changing `featureFlag=true` and calling `retransformClasses`, **A is not called again to compute a new effect**. The current flag state does not turn A(false) into a capable transformer.

To recompute logic on an already loaded class, choose the appropriate mechanism **from the design stage**: a `true` transformer can be called during retransform; or `redefineClasses` can be used if the agent has the separate capability and you supply valid bytes. Do not rely on changing a variable in A and expecting the JVM to automatically run A's callback on retransform.

## 7. Ordering of the four transformer groups

The `ClassFileTransformer` specification orders transformers into **four groups**:

1. **Java retransformation-incapable** (`canRetransform=false`).
2. **Native retransformation-incapable** (via JVM TI).
3. **Java retransformation-capable** (`canRetransform=true`).
4. **Native retransformation-capable**.

**Within each group**, transformers run in the order they were registered. However, **group** order takes precedence over global registration order.

Example fragment:

~~~java
inst.addTransformer(transformerB, true);  // registered first
inst.addTransformer(transformerA, false); // registered later
~~~

At class load/redefine, between these two **Java** transformers, A(false) **still comes before** B(true) even though A was registered later. At retransform, the JVM reapplies A's effect in the incapable group's position, **without calling A**, and only then calls B.

With A1(false), A2(false), B(true):

~~~text
Load:
B0 → A1(false) → B1 → A2(false) → B2 → B(true) → B3

Retransform:
B0 → [reuse A1 → B1] → [reuse A2 → B2] → B(true) → B4
      no A1 callback    no A2 callback    B callback
~~~

If native transformers exist, they participate in groups 2 and 4 respectively. The output of one step becomes the **input of the next step**, so B cannot assume the `classfileBuffer` it receives is still the untouched original bytes.

## 8. Why multiple retransforms do not automatically stack B's code from the previous round

**Common mistake:** understanding retransformation as "taking the currently installed class and calling A, B again on those exact bytes".

~~~text
Wrong:
B0 -- A --> B1 -- B --> B2
B2 -- A --> ... -- B --> B3
B3 -- A --> ... -- B --> B4
~~~

Whereas the correct principle is:

~~~text
Correct:
B0 -- [reapply A] --> B1 -- B(true) --> B2
B0 -- [reapply A] --> B1 -- B(true) --> B3
B0 -- [reapply A] --> B1 -- B(true) --> B4
~~~

That is why in the `CpPatch` demo, B(true) **always** finds `"BASE"` in every retransform round even though the class from the previous round was returning `"LIVE"`.

This reduces the risk of stacking a transformation solely from using the previous round's output as a base, **but it is not a guarantee that capable transformers are always idempotent**. Multiple agents may instrument the same method, other capable transformers may alter the input, and bytes from the most recent **redefine** change the baseline. Proper class analysis logic and output verification are still required for complex transformations.

### Initial bytes are not necessarily bit-for-bit identical

The API explicitly notes that the initial class-file bytes used during retransform **may not be byte-for-byte identical** to the original array passed to `ClassLoader.defineClass` or `redefineClasses`. For example, the constant pool may have a different order/layout, some attributes may not be present, or the order of methods where order is insignificant may differ.

Therefore, do not assume the **absolute offset** of a UTF-8 entry in the constant pool remains fixed across callbacks. In production, parse class files with a structure-aware tool rather than patching by manual byte offsets.

## 9. How does redefine differ from retransform here?

| Operation | Key input data | A(false) | B(true) |
|---|---|---|---|
| Class load | Bytes used to define the class | Called | Called |
| `retransformClasses` | Initial bytes + incapable effects from load/redefine | **Not called; reused** | **Called** |
| `redefineClasses` | New bytes supplied by caller in `ClassDefinition` | **Called** | **Called** |

The specification states that **the previous class load or redefine** is the basis for the result reapplied by the incapable group. Thus, if an agent performs a **redefine** after load, A(false) can be called during redefine and produce a new result. Subsequent retransforms are based on the baseline associated with the latest redefine, not necessarily the bytes of the originally loaded class.

To use `redefineClasses`, the agent must request the **`Can-Redefine-Classes`** capability and check `isRedefineClassesSupported()`; this is **distinct** from the retransformation capability.

## 10. Capabilities and target class selection

An agent manifest typically contains:

~~~text
Manifest-Version: 1.0
Premain-Class: DemoAgent
Can-Retransform-Classes: true

~~~

`Can-Retransform-Classes: true` is a **request**. Before registering B(true) or requesting retransform, check the JVM:

~~~java
if (!inst.isRetransformClassesSupported()) {
    return;
}
if (!inst.isModifiableClass(clazz)) {
    return;
}
inst.retransformClasses(clazz);
~~~

The snippet above is a fragment inside a method with `Instrumentation inst` and `Class<?> clazz`.

- `isRetransformClassesSupported()` checks the general capability, depending on the JVM and manifest.
- `isModifiableClass(clazz)` checks the specific class; primitive and array classes are not modifiable.
- `addTransformer(t, true)` throws `UnsupportedOperationException` if the JVM configuration does not support retransform.
- `retransformClasses` can fail due to missing capability, an unmodifiable class, invalid byte format/version, or invalid structural changes (such as adding fields/methods).
- Passing multiple classes forms a batch to support interrelated changes; when the operation throws an error, the API specifies that **no classes in the batch are retransformed**.

For executing classes, **active method frames** continue running the old bytecode; **new invocations** use the new definition. Retransformation does not rerun static initializers and does not recreate existing objects.

None of these conditions cause A(false) to be called again. That is a **dedicated mechanism** of the incapable group under the callback contract.

## 11. Notes when using `removeTransformer`

~~~java
boolean removed = inst.removeTransformer(transformer);
~~~

This call **removes the registration**; it does not directly revert bytecode in already loaded classes. An instrumented class continues running its currently installed definition until a valid class change occurs.

If you want to restore a class after removal, you must actively design the retransform/redefine process and consider **the remaining registered transformers**, already applied transformations, JVM constraints, and final bytecode; do not treat `removeTransformer` as an automatic undo button.

Due to concurrency, the specification also notes that a transformer may receive a callback **after being removed** because a class loading operation had already started earlier. Transformers must be safe against late callbacks.

## 12. `return null`, exceptions, and byte validation

Inside a callback:

~~~java
if (!"demo/Target".equals(className)) {
    return null;
}
return transformedClassBytes;
~~~

This is a fragment inside a `transform(...)` with parameters `className` and `byte[] transformedClassBytes`; it does not run standalone.

- **`return null`**: no transformation at this step. For an incapable transformer, the previous "no-change" effect will be applied on subsequent retransformations without a callback.
- **`return byte[]`**: must be a new array containing a valid class file; do not modify `classfileBuffer` in place.
- **Throwing an uncaught exception in `transform`**: the JVM still attempts to call the remaining transformers and continues trying to load/redefine/retransform; in effect, that transformer step is equivalent to no change. Do not use `throw` as a guaranteed mechanism to abort class loading.
- **Invalid transformation**: if the final class file is malformed, the JVM may throw a format, version, verifier, or linkage error. Just because transformers A and B ran does not mean the definition will be accepted.

For production code, filter by class loader/name/method, avoid JDK or bootstrap-dependent classes, generate bytes with a reliable library, and properly update stack-map frames, exception ranges, and labels when modifying control flow.

## 13. Explaining common errors and symptoms

| Observation | Explanation | Check |
|---|---|---|
| A(false) only logs at load time | **Expected** behavior: no callback on retransform | Inspect byte effects, not just log counts |
| After retransform the class still has A's effect | JVM automatically reapplies A's old result | Compare class behavior and B's input |
| B(true) sees bytes already processed by A | Transformation chain is ordered by group | Check `canRetransform` and application order |
| B cannot find the literal from A | A has not affected that class, transformation failed, or wrong class loader | Verify internal name, input bytes, lifecycle |
| Changing A(false) config does not update old classes | A is not called again on retransform | Use a capable transformer or appropriate redefine mechanism |
| Registering A(false) after class load, calling only retransform | No new callback for A on the retransformation path | Design registration before the relevant load/redefine |
| `UnsupportedOperationException` at `addTransformer(..., true)` | Missing retransformation capability | Check manifest and `isRetransformClassesSupported()` |
| `UnmodifiableClassException` at retransform | Specific class cannot be modified | Query `isModifiableClass` |
| `ClassFormatError`/`LinkageError` | Transformed bytes have invalid format/limits | Inspect each step and final bytes |
| `classBeingRedefined != null`, assumed to be redefine | This parameter is also non-null during retransform | Identify which API actually triggered the callback |
| Removing A still leaves instrumentation active | `removeTransformer` does not directly restore classes | Design an explicit rollback |
| Repeated transforms duplicate probes | Capable transformer is incompatible with chain input | Test idempotence, multiple agents, and redefinition |

**Debugging workflow:** verify the exact agent JAR and manifest → class load timing → registration of each transformer → class loader and internal name → A(false) output at load/redefine → B(true) input at retransform → inspect bytes/behavior of the final definition.

Do not use "whether A has a new log" as the sole measure of "whether A's effect still exists".

## 14. Design and performance implications

Not re-invoking A(false) can avoid rerunning a CPU-intensive callback A, but **a full retransform is not free**. The JVM still has to process the request, reapply the incapable group's effects per contract, invoke the capable group, verify bytecode, and potentially adjust JIT-optimized code.

Choose `false` when a transformation should be decided **at load/redefine time** and remain unchanged when other agents request retransformation. Choose `true` if a transformation needs to be **recomputed under new configuration** after the class is loaded. Do not default every agent to capable registration, as it requires the capability and increases the callback surface to manage.

With multiple agents:

1. Design later transformers' output to be compatible with **bytes already modified by earlier transformers**, rather than assuming the input is always a pristine class file.
2. Filter early by internal class name, module, and class loader to reduce overhead and avoid accidentally instrumenting dependent classes.
3. Test both **callback counts** and **actual class results** before/after retransform.
4. Distinguish `retransformClasses` from `redefineClasses`; only the latter causes the incapable group to **receive callbacks again** on the new definition.
5. Have a clear strategy to disable/remove instrumentation; `removeTransformer` alone is not a bytecode rollback operation.
6. If transformer code is complex, use a bytecode API that supports the target JDK version instead of patching class files via raw byte replacement like the demo.

## 15. Self-check

1. **Is `addTransformer(A)` equivalent to `addTransformer(A, false)`?** Yes.
2. **Is A(false) allowed to modify bytecode at class load?** Yes.
3. **When `retransformClasses` runs, is A(false) called again?** No.
4. **A(false) is not called again, so is A's effect erased?** No; the JVM reapplies the previous transformation result.
5. **Which point in time is the old transformation result taken from?** The relevant class load or **most recent redefine**, not simply the output of the last retransform.
6. **Why can B(true) see the `BASE` literal even though A did not run during retransform?** Because A's effect was already reapplied by the JVM before B.
7. **Does a second retransform take B's `LIVE` output from the previous round and apply B one more time?** No under the basic model; the JVM rebuilds from initial bytes and incapable results, then calls B.
8. **A(false) returned `null` at load, then configuration changes. Does retransform call A to re-decide?** No.
9. **Why can the same A(false) be called again in `redefineClasses`?** Because redefinition is not retransformation; the API requires calling A back during redefine.
10. **What is the order between Java A(false) and B(true) if B is registered first?** A still runs before B by group.
11. **Does calling `removeTransformer(A)` automatically revert all old classes back to pre-instrumentation state?** No.
12. **If the JVM does not support retransform, can you force registering B(true)?** No; you must check the capability.
13. **What does the output `calls frozen=1 dynamic=3` prove?** A only received a callback at load, while B received callbacks at load and both retransforms.
14. **Why is it necessary to observe `initial=BASE`, `afterFirst=LIVE`?** Because they confirm **the byte transformation effect** alongside counting callbacks.
15. **Should the example's `CpPatch` be used to modify any class in production?** No; it is intentionally limited to a single ASCII literal of the same length.

### Authoritative references

- [Java SE 21 — `Instrumentation.retransformClasses`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): specifies **reusing** incapable transformer results without callbacks, capabilities, limits, and errors.
- [Java SE 21 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): ordering of the four groups, inputs/outputs, and handling of `return null`/exceptions.
- [Java SE 21 — `java.lang.instrument` package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): `premain`, agent manifest, and `Can-Retransform-Classes`.
- [Java Virtual Machine Specification 21 — Class File Format](https://docs.oracle.com/en/java/javase/specs/jvms/se21/html/jvms-4.html): constant pool, tags, and `CONSTANT_Utf8_info`.
- [Java SE 21 — `UnmodifiableClassException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/UnmodifiableClassException.html): unmodifiable classes.

**Key takeaway:** `canRetransform=false` means **do not invoke `transform(...)` again during retransformation**, **not that existing bytecode effects disappear**. The JVM reuses the result from the previous load/redefine, then invokes `true` transformers to produce the final class definition.