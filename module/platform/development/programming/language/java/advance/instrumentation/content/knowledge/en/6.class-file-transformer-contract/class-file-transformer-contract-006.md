# ClassFileTransformer: return null when unchanged, return a new byte array when transformed

In Java Instrumentation, **ClassFileTransformer.transform(...)** receives the bytecode of a class and can supply a replacement version before the JVM finishes defining, redefining, or retransforming the class. The return rule is very short, yet it determines the correctness of an agent:

- **When not modifying the class in this callback:** return **null**.
- **When actually wanting to replace the class file:** create a **new byte[]**, keep the input data intact, modify the copy, and return the **new array containing a valid class file**.

This is the **transformation result contract of each individual transformer**, not a global test of whether the class has changed behavior. In a chain of multiple transformers, a transformer returning **null** can still sit before or after another transformer that modifies the class. Conversely, returning a byte array with a different reference does not guarantee that the bytecode has a meaningful difference, and the JVM still must verify the final definition.

This article presents the exact return semantics, how to decide whether to transform or not, safe handling of the input bytecode, common mistakes, and a runnable Java 17+ program demonstrating both the **return null** and **return new byte[]** branches.

## 1. Reading the ClassFileTransformer contract accurately

An agent registers a transformer through the **Instrumentation** object that the JVM passes into **premain** (startup agent) or **agentmain** (dynamically attached agent):

~~~java
// Illustrative snippet, located inside premain/agentmain.
instrumentation.addTransformer(transformer);
~~~

From then on, when a matching class definition event occurs, the JVM can invoke the transformer before the class file application/verification step. With Java 17, the common implementation overrides the five-parameter form:

~~~java
// Signature in a class implementing ClassFileTransformer.
// This is an illustrative snippet, not a standalone Java file.
@Override
public byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain protectionDomain,
        byte[] classfileBuffer) {

    if (!"example/Target".equals(className)) {
        return null;
    }

    byte[] replacement = createReplacement(classfileBuffer);
    return replacement; // must be a valid class file and a new array
}
~~~

Since Java 9, there is also a six-parameter overload starting with **Module module**:

~~~java
// Overload with Module, suitable when JPMS information is needed.
@Override
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain protectionDomain,
        byte[] classfileBuffer) {
    return null;
}
~~~

In Java 17, the default implementation of the six-parameter overload **delegates to the five-parameter overload**; therefore, overriding the five-parameter form remains valid. If you need to distinguish classes with the same name by module, overriding the six-parameter form is more convenient. The two snippets above illustrate separate signatures, not two methods that must be implemented together.

Parameters directly relevant to the transformation decision:

| Parameter | Meaning when deciding the return value |
| --- | --- |
| **module** (six-parameter overload) | Module containing the class being processed; helps filter by JPMS boundaries |
| **loader** | Defining class loader, may be **null** when defined by the bootstrap loader |
| **className** | Internal name, e.g. **java/util/List**, with **/** instead of **.**; handle possible null according to the API contract |
| **classBeingRedefined** | **null** for a new class definition; non-null during redefine/retransform |
| **protectionDomain** | Protection domain associated with the class being defined or redefined |
| **classfileBuffer** | Input class file byte sequence for the **current transformer invocation**; must never be mutated directly |

Important: **classfileBuffer is a read-only input by contract**, not a buffer that the agent owns and can modify in place. The JVM passing it to the transformer does not transfer ownership of the byte[] to application code.

## 2. What does returning null mean?

Returning **null** indicates that **this transformer does not perform a transformation on this invocation**. For a class outside the target scope, the most appropriate behavior is usually to return immediately:

~~~java
if (className == null || !className.startsWith("com/acme/")) {
    return null;
}
~~~

This has three consequences:

1. The input is forwarded unchanged **by the current transformer** to the remaining steps or transformers.
2. Subsequent transformers still have a chance to replace the bytes. **null** is not a signal that "forbids all other transformers from transforming".
3. During a retransform, **null** does not mean the JVM will automatically restore the class to its original bytecode. Prior transformation results and retransform rules can still have an effect.

Example:

~~~text
Original bytes B0
    │
    ▼
Transformer A: return null
    │
    ▼
Transformer B receives B0
    │  if B returns valid B1
    ▼
JVM continues processing B1
~~~

Even if A logs **SKIPPED**, whether the class ultimately changes still depends on B, the other transformers, and the JVM's verification/application result.

**When should you return null?**

- The class name, module, loader, or event is out of scope.
- The agent only wants to observe the class and not replace bytes.
- A feature flag condition is not enabled.
- Code has inspected the class and determined for sure that no instructions need to be added or modified.
- No safe target pattern was found in a narrowly scoped transformer example.
- A valid result cannot be produced under a designed "fail safely" policy; record the specific reason and return null, avoiding pretending the class was modified.

Do not use **new byte[0]**, a dummy byte array, or an empty class file as a "no change" signal: the JVM can reject that result with a class format/verification error. **null** is the API's signal for "no transformation".

## 3. What does returning a new byte array mean?

To modify bytecode, the transformer creates **a different array**, modifies the copy, and returns the resulting array:

~~~java
// Illustrative snippet inside transform(...).
byte[] changed = classfileBuffer.clone();
// Modify only changed, using a valid class file edit.
return changed;
~~~

**clone() only copies bytes; it does not by itself create a meaningful transformation.** Real code must perform a valid change on the copy (or use a bytecode library to construct a different class file), and then verify the result.

There are four concepts that are easily confused:

| Observed fact | What can be concluded |
| --- | --- |
| **result != null** | The transformer supplied a replacement byte sequence |
| **result != classfileBuffer** | A different array object exists |
| **!Arrays.equals(result, classfileBuffer)** | The byte contents of the two arrays differ |
| The class is accepted by the JVM and the expected behavior is verified | The transformation took effect for the intended goal |

The first three **do not by themselves prove** the last one. An array with a different reference but identical contents is possible. An array with different contents but invalid format, invalid frames, or redefine/retransform limit violations can still be rejected.

Mental model to use:

~~~text
shouldTransform?
    ├── No  ──> return null
    └── Yes
          │
          ├── read/inspect class file
          ├── create a new byte[]
          ├── modify according to valid bytecode rules
          ├── confirm the desired result
          └── return changedBytes
                        │
                        ▼
             JVM/next transformer
             verifies and applies afterward
~~~

### 3.1. Why not modify classfileBuffer directly?

The approach below **violates the contract**, regardless of whether it ends up returning null or returning the input itself:

~~~java
// WRONG: counterexample snippet, do not use in real programs.
classfileBuffer[0] = 0;
return null;
~~~

Reason: **classfileBuffer must be kept intact**. You do not know how the JVM or other transformers rely on the input contents; mutating it can lead to inconsistent data, corrupt the **CAFEBABE** header, cause hard-to-diagnose errors, and go against the API guidelines.

The appropriate approach:

~~~java
// CORRECT regarding buffer ownership; illustrative snippet omits the specific edit step.
byte[] candidate = classfileBuffer.clone();
// Perform modifications only on candidate.
return candidate;
~~~

If it is ultimately determined that `candidate` has no differences and the class does not need modification, **return null** expresses the intent more accurately. There is no need to copy the entire class file for out-of-scope classes.

## 4. Java 17+ lab: two classes, two return branches

The lab demonstrates:

- Class **Ignored** is seen by the transformer, which **returns null**: the method keeps the result **STABLE**.
- For class **Changed**, the transformer creates a **new byte[]**: replaces a string constant **"BEFORE"** with **"AFTER!"** in the constant pool, and the JVM defines the new class with the new result.
- To stay independent of external libraries, the example uses a small helper that only finds/replaces **CONSTANT_Utf8_info** in the demo class file. Both ASCII strings are **6 bytes** long; replacing them preserves the constant pool entry length without shifting offsets. This is a **minimal technique for the demo**; production code should use an appropriate bytecode library such as ASM or Byte Buddy.

### 4.1. SampleApp.java

~~~java
// File: SampleApp.java
public final class SampleApp {
    public static void main(String[] args) {
        System.out.println("ignored=" + Ignored.value());
        System.out.println("changed=" + Changed.value());
    }
}

class Ignored {
    static String value() {
        return "STABLE";
    }
}

class Changed {
    static String value() {
        return "BEFORE";
    }
}
~~~

**Ignored.value()** and **Changed.value()** are runtime method calls, so the caller does not simply inline a compile-time constant from another class's field. The compiler produces **SampleApp.class**, **Ignored.class**, and **Changed.class**.

### 4.2. DemoAgent.java

~~~java
// File: DemoAgent.java
import java.lang.instrument.Instrumentation;

public final class DemoAgent {
    private DemoAgent() {
    }

    public static void premain(String options,
                               Instrumentation instrumentation) {
        instrumentation.addTransformer(new DemoTransformer());
        System.out.println("AGENT_READY");
    }
}
~~~

**premain** receives `Instrumentation` from the JVM and registers the transformer **before main is invoked**. The lab only handles new classes loaded after registration, so **addTransformer(transformer)** is sufficient; the example does not require the retransform capability.

### 4.3. DemoTransformer.java

~~~java
// File: DemoTransformer.java
import java.lang.instrument.ClassFileTransformer;
import java.nio.charset.StandardCharsets;
import java.security.ProtectionDomain;

public final class DemoTransformer implements ClassFileTransformer {

    @Override
    public byte[] transform(
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain domain,
            byte[] classfileBuffer) {

        if ("Ignored".equals(className)) {
            System.out.println("TRANSFORM Ignored -> null");
            return null; // Intentionally do not modify.
        }

        if (!"Changed".equals(className)) {
            return null; // Keep all other classes unchanged as well.
        }

        byte[] replacement = replaceDemoUtf8Constant(classfileBuffer);

        if (replacement == null) {
            System.out.println("TRANSFORM Changed -> null (no match)");
            return null;
        }

        System.out.println("TRANSFORM Changed -> new byte[]");
        return replacement;
    }

    private static byte[] replaceDemoUtf8Constant(byte[] original) {
        // Intended only for valid example class files and fixed ASCII strings.
        // Not a general-purpose parser/class writer for arbitrary bytecode.
        if (original.length < 10
                || (original[0] & 0xff) != 0xca
                || (original[1] & 0xff) != 0xfe
                || (original[2] & 0xff) != 0xba
                || (original[3] & 0xff) != 0xbe) {
            return null;
        }

        int constantPoolCount = readU2(original, 8);
        int p = 10;

        for (int i = 1; i < constantPoolCount; i++) {
            int tag = original[p++] & 0xff;

            switch (tag) {
                case 1 -> { // CONSTANT_Utf8
                    int size = readU2(original, p);
                    p += 2;

                    if (size == 6 && matchesAscii(
                            original, p, "BEFORE")) {
                        byte[] copy = original.clone();
                        byte[] replacement = "AFTER!"
                                .getBytes(StandardCharsets.US_ASCII);
                        System.arraycopy(
                                replacement, 0, copy, p, replacement.length);
                        return copy;
                    }

                    p += size;
                }

                case 3, 4, 9, 10, 11, 12, 17, 18 -> p += 4;
                case 5, 6 -> { // long/double occupy two slots
                    p += 8;
                    i++;
                }
                case 7, 8, 16, 19, 20 -> p += 2;
                case 15 -> p += 3;

                default -> throw new IllegalArgumentException(
                        "Unknown constant-pool tag: " + tag);
            }
        }
        return null;
    }

    private static int readU2(byte[] bytes, int p) {
        return ((bytes[p] & 0xff) << 8) | (bytes[p + 1] & 0xff);
    }

    private static boolean matchesAscii(byte[] bytes, int p,
                                        String needle) {
        if (p + needle.length() > bytes.length) {
            return false;
        }
        for (int i = 0; i < needle.length(); i++) {
            if (bytes[p + i] != (byte) needle.charAt(i)) {
                return false;
            }
        }
        return true;
    }
}
~~~

Key points in the program:

1. **"Ignored".equals(className)** is safe when **className** is null, and accurately distinguishes the class name to ignore.
2. **return null** in the **Ignored** branch does not create/allocate a new array.
3. For **Changed**, the helper reads the constant pool structure to find only the UTF8 entry with the value **BEFORE**; it only replaces it if the length condition is met.
4. **original.clone()** creates a different byte[]. **System.arraycopy** modifies only the copy, keeping the input **classfileBuffer** intact.
5. **return replacement** notifies the JVM that a replacement result exists. Class **Changed** is defined with the new literal; calling **Changed.value()** afterward returns **AFTER!**.
6. For classes that do not match the name or do not contain the constant to modify, the transformer returns **null**, adhering to the no-transformation contract.
7. The logs show the **transformer's action**. The output of **SampleApp** is the proof that the corresponding class actually executed with the desired contents.

**Important scope and limitations:** The constant pool reader above assumes a valid class file such as one generated by **javac --release 17**, does not perform full bounds checking for untrusted input, does not decode general Modified UTF-8, and only replaces ASCII strings of the same length. Do not use it to instrument arbitrary libraries or treat it as a production bytecode processor. The **return null / return byte[]** part is the skill to take away from this example.

### 4.4. Creating the agent.mf manifest

Create a text file **agent.mf**:

~~~text
Manifest-Version: 1.0
Premain-Class: DemoAgent
~~~

Put a **newline at the end of the file**. **Premain-Class** is the binary name of the agent class; if moved into a package, the full FQCN must be updated in the manifest. The example runs as a startup **-javaagent** agent, not via dynamic **agentmain** attach.

### 4.5. Compiling, packaging, and running

Place the four files **SampleApp.java**, **DemoAgent.java**, **DemoTransformer.java**, and **agent.mf** in the same directory. Run with JDK 17 or later:

~~~bash
javac --release 17 SampleApp.java DemoAgent.java DemoTransformer.java
jar cfm demo-agent.jar agent.mf DemoAgent.class DemoTransformer.class
java -javaagent:demo-agent.jar -cp . SampleApp
~~~

Typical output on HotSpot Java 17:

~~~text
AGENT_READY
TRANSFORM Ignored -> null
ignored=STABLE
TRANSFORM Changed -> new byte[]
changed=AFTER!
~~~

The key lines to verify are **TRANSFORM Ignored -> null**, **ignored=STABLE**, **TRANSFORM Changed -> new byte[]**, and **changed=AFTER!**. The exact moment the JVM decides to load independent classes can vary across implementations, so production tests should not rely solely on class-load log order; the final values must match.

Baseline run **without** the agent:

~~~bash
java -cp . SampleApp
~~~

Output:

~~~text
ignored=STABLE
changed=BEFORE
~~~

Comparison of the two runs:

| Class | Transformer returned | Without agent | With agent |
| --- | --- | --- | --- |
| **Ignored** | **null** | **STABLE** | **STABLE** |
| **Changed** | **new byte[]**, different content | **BEFORE** | **AFTER!** |

The example shows the difference between **performing no transformation** and **proposing a valid new class definition**, without depending on external libraries.

## 5. Why does modifying a single constant pool entry in the example take effect?

In **Changed.class**, the **value()** method typically contains a JVM **ldc** instruction or equivalent to fetch the string literal from the constant pool and then **areturn**. When replacing the contents of the referenced string's UTF8 entry, the new class definition returns the corresponding string.

Use **javap** to inspect the original class file on disk:

~~~bash
javap -c -p Changed
javap -v -p Changed
~~~

With **javac --release 17**, the disassembly of method **Changed.value()** typically looks like:

~~~text
static java.lang.String value();
  Code:
     0: ldc           #7                  // String BEFORE
     2: areturn
~~~

The constant pool index number (e.g. **#7**) can vary by compiler, so the output here is an **illustrative snippet**, not a fixed byte-for-byte transcript across all JDKs. What must be checked is that there is a reference to **String BEFORE**. After running the agent, the **Changed.class file on disk** can still contain **BEFORE**: the example replaced bytes **during class definition in the JVM**, without overwriting the class file on disk.

Modifying only the contents of a single constant pool entry of the same length is viable for the demo class because:

- Both **BEFORE** and **AFTER!** consist of 6 ASCII bytes.
- The resulting array is a complete copy of the class file; the header and all other parts remain unchanged.
- The Code attribute length, instruction offsets, fields, methods, or inheritance structure are not altered.
- The JVM still runs the class verification/definition process before letting the application use it.

In real class files, modifying the constant pool can also affect every place referencing the same entry; for non-ASCII strings with Modified UTF-8 and different lengths, you cannot arbitrarily overwrite bytes as above. You need a library that rewrites the class file and recomputes/maintains the related structures.

## 6. Multiple-transformer chains: null is only a local decision

Instrumentation allows registering multiple transformers; the JVM applies them according to the groups and order specified in **ClassFileTransformer**. Within the same group, transformers are invoked in registration order. The byte[] result of a preceding transformer becomes the **classfileBuffer** of the next transformer; when the preceding one returns null, the current data is forwarded.

~~~text
Input bytes B0
        │
        ▼
Transformer A: sees class is out of scope
        │ return null
        ▼
Transformer B: transforms B0 into B1
        │ return new byte[] B1
        ▼
Transformer C: receives B1
        │ return null
        ▼
JVM verifies and can define the class with B1
~~~

Thus:

- A and C **did not modify** the class in their respective invocations.
- B **supplied a replacement**.
- A or C returning null does not cancel B's transformation.
- The JVM still needs to confirm B1 is valid. Another transformer afterward might continue modifying it, so logging at B alone is not enough to conclude the final contents.

When writing audits/metrics, distinguish between:

~~~text
callbackCount       = number of times the callback was invoked
skippedCount        = number of times null was intentionally returned
replacementCount    = number of times a new byte[] was returned
verifiedChangeCount = number of times there is evidence the class/behavior actually changed correctly
~~~

**replacementCount is not synonymous with verifiedChangeCount.** If you need to ensure "whether the array differs from the input data", you can compare **Arrays.equals(before, after)**, but byte-by-byte comparison is expensive for large class files and still does not prove the modification is accepted by the JVM. Use such comparisons only for diagnostics or tests, not indiscriminately on every class load in production.

### 6.1. Is it safe to register a transformer twice?

**Instrumentation.addTransformer(...)** can accept the same instance multiple times; the API discourages this. If registered repeatedly, the same logic can be applied multiple times across the byte pipeline, causing duplicate transformations or invalid results. The design should maintain exactly one registration point per responsibility and manage the **removeTransformer(instance)** lifecycle intentionally.

Transformers should also be written to be **idempotent** when possible: if a class already has a marker or the corresponding transformation, a subsequent invocation **returns null** instead of adding the same instruction again.

## 7. Reload, redefine, and retransform: same return contract, different context

**ClassFileTransformer** can be invoked when a class is first defined, redefined, or retransformed. Whether it is invoked during **retransformClasses(...)** depends on how it was registered:

~~~java
// In premain/agentmain, if retransform callbacks are needed:
if (instrumentation.isRetransformClassesSupported()) {
    instrumentation.addTransformer(transformer, true);
}
~~~

This snippet is illustrative, not a standalone program. With the default **addTransformer(transformer)** (**canRetransform=false**), the transformer receives new class definition and redefine events per the contract, but **is not called again** during retransform; the JVM can **reapply the cached result** from the previous transformation of the non-retransform-capable transformer group.

With **canRetransform=true**, the callback is invoked during eligible retransforms. The rule remains:

- **return null** if **this invocation** does not supply new bytes.
- **return a new byte[]** if a replacement class file **valid under retransform restrictions** is needed.

Avoid a false inference: "Returning null during retransform will make the JVM revert to the original uninstrumented class." You cannot infer this when multiple transformers exist, especially since results from non-retransform-capable transformers are automatically reapplied.

A **retransformClasses** call completing without throwing does not mean every callback returned different bytes: the request can succeed even if all returned null. Conversely, returning a new byte[] does not guarantee success if the verifier or structural change restrictions reject the final class file.

Retransforming/redefining existing classes is usually restricted from schema changes (adding/removing methods/fields, changing inheritance, etc.). Instrumentation at initial load time and retransform after the class has already run need to be tested under their respective conditions.

### 7.1. Rules when a class has already been transformed

Suppose a transformer adds logging code at the beginning of a method. When invoked again, if it keeps adding logging code without checking existing markers/structure, it can lead to duplicate logging or bytecode bloat. The appropriate approach is:

1. Identify the **right class and right event**.
2. Check whether the class already has the corresponding change.
3. If it is already in the desired state, **return null** for the current invocation.
4. If an update is needed, create a **valid new class file** while respecting redefine/retransform restrictions.

Do not assume **classfileBuffer** during retransformation is always a byte-for-byte copy of the running class file or the file on disk: the Javadoc describes a process of reconstructing bytes, which may differ in constant pool/attribute details.

## 8. Filter classes properly before spending transformation cost

A registered transformer can receive callbacks for a large number of classes. Creating a copy for every class is wasteful and can increase startup time; therefore, prioritize cheap filter conditions and return null early:

~~~java
// Illustrative snippet inside transform with Module.
if (className == null) {
    return null;
}
if (loader == null) {
    return null; // Example policy: do not touch bootstrap classes.
}
if (!className.startsWith("com/example/app/")) {
    return null;
}
if (module != null && module.isNamed()
        && !"com.example.app".equals(module.getName())) {
    return null;
}
// Only after filtering should you consider parsing/transforming classfileBuffer.
~~~

These conditions are an **example policy**, not a JVM requirement. Real-world agents may need to process bootstrap classes or other modules. Internal names with **/** must be matched properly; using **className.equals("com.example.app.Service")** will not match names passed in internal format.

In applications using multiple class loaders, **the same binary name + different defining loader** can be two distinct runtime classes. If an agent only wants to modify the copy from one plugin or one web application, it needs to check the appropriate loader/module/class source rather than relying on the name alone.

**Do not try to call loader.loadClass(...) just to inspect a class inside transform.** That call can trigger nested class loading, leading to recursion, class circularity, loader locks, or unintended initialization side effects. Keep filtering logic as dependency-free as possible.

## 9. Thread safety and error handling in a transformer

Transform callbacks can happen while the JVM loads classes on different threads. The **null vs byte[]** contract must be preserved even under concurrency.

### 9.1. Do not keep mutable buffers as shared state

Dangerous design example:

~~~java
// WRONG: counterexample snippet, non-executable.
static byte[] lastInput;

public byte[] transform(..., byte[] classfileBuffer) {
    lastInput = classfileBuffer;
    return null;
}
~~~

This is not a valid Java signature because **...** is only used as illustrative notation. The problem: storing **classfileBuffer** in static state both creates unnecessary data-sharing risks and makes lifecycle/allocation hard to control. If you need to debug class files, make a separate copy, bound storage size/retention time, and protect collections under an appropriate concurrency model.

**Each invocation should use local variables**, without reusing a mutable byte[] array across transform invocations. If caching bytes is truly necessary, it must have a sufficiently strong class-identifying key, a policy to avoid class loader memory leaks, and clear synchronization.

### 9.2. What do Throwable or IllegalClassFormatException mean?

By contract, if a transformer throws an uncaught exception, the JVM may still invoke other registered transformers and continue attempting to define/redefine/retransform the class. As for that transformer's result, the exception is treated equivalently to **supplying no transformation**.

Do not use **throwing an exception** as a normal way to skip a class. **return null** makes intent clear, has low overhead, and makes state counting straightforward. **IllegalClassFormatException** is appropriate when signaling that the input is not a properly formatted class file; even though the outcome is equivalent to null for this callback, the error details aid diagnosis.

If a transformer produces different bytes that are **invalid**, the JVM may throw **ClassFormatError**, **VerifyError**, **LinkageError**, or related errors during class definition/verification; in the case of retransform, an exception may be raised at the API caller. That is a different failure from deciding to **return null**.

### 9.3. Logging and metrics reliably

It is good practice to label clearly:

~~~text
CLASS_SEEN name=com/example/app/Service loader=...
SKIPPED reason=FILTER
SKIPPED reason=ALREADY_INSTRUMENTED
REPLACEMENT_SUPPLIED name=... inputBytes=... outputBytes=...
CLASS_APPLY_FAILED error=...
BEHAVIOR_VERIFIED probe=...
~~~

An observability system can report callback-level status (**SKIPPED**/**REPLACEMENT_SUPPLIED**) and JVM-result-level status (**APPLIED**/**REJECTED**) separately. Do not conclude "instrumentation succeeded" just because the transformer printed **REPLACEMENT_SUPPLIED**; verification and class usage happen afterward.

## 10. Common mistakes and fixes

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Returning **new byte[0]** to skip | JVM receives an invalid class file | **return null** |
| Modifying **classfileBuffer** and then **return null** | Violates input immutability; unreliable result | Do not mutate input; if not modifying **return null** |
| Modifying input directly and returning input | Violates contract, easily breaks pipeline | Create a different byte[] and modify the copy |
| **return classfileBuffer.clone()** for every class | Wastes CPU/heap even when content is unchanged | Filter and **return null** when no modification is needed |
| Treating **result != null** as "bytecode changed properly" | Could be a new array with identical bytes | Test output data and JVM application separately |
| Confusing internal **className** and FQCN | Wrong filtering; transformer always returns null | Use the **com/example/Foo** form |
| Filtering by name only, ignoring class loader/module | Modifies the wrong class with the same name | Identify loader/module when needed |
| Calling application code or heavy I/O inside transform | Risk of recursion/deadlock, slow startup | Keep callbacks short, limit side effects |
| Forgetting retransform when transformer registers late | Already-loaded classes do not get callbacks again | Choose an appropriate retransform/redefine mechanism |
| Returning a byte[] with invalid class format | **VerifyError**, **ClassFormatError**, and startup failures | Use a compliant class writer, test on the target JDK |
| Not protecting shared state | Races across multiple class loading threads | Atomic/ConcurrentHashMap and clear lifecycle |

## 11. QA checklist for a ClassFileTransformer

Before registering a transformer, verify:

- **Filter conditions** accurately decide the class, loader, module, event, and feature flag.
- For every case not needing modification, the callback **returns null** without creating placeholder bytes.
- **classfileBuffer is always immutable**; every modified output is a **new array**.
- Returned bytes are a **well-formed class file** with the right class file version, constant pool structure, instructions, stack/frames, and related metadata.
- No branch accidentally returns a new byte[] without modifying anything while logging "transformed".
- With multiple transformers, understand that results are **chained**; your null does not cancel another transformer's output.
- If retransform is supported, design safely for callback re-invocation, respect redefine/retransform restrictions, and check JVM capabilities.
- Do not pull class loader/module state into long-lived caches without an eviction strategy; callbacks tolerate concurrency and reentrancy.
- Have tests for **ignored class**, **properly modified class**, **class without matching pattern**, **already-instrumented class**, and **invalid bytes** when needed.
- The final result is verified **outside the callback** by real method/class behavior, not just by a **return new bytes** log.

### Self-check questions

1. **If you do not want to modify a class, return null or clone the input and return it?** **null** is the right and clearest result.
2. **Transformer A returns null; can transformer B still modify the class?** Yes. **null** is only A's decision.
3. **Can you modify classfileBuffer and return null to keep the effect?** No. The input must be immutable; the JVM does not promise to use such changes.
4. **Does returning a new byte[] identical to the input mean the class was modified?** No. Being new by identity does not mean different data or different behavior.
5. **If a transformer supplies invalid bytes, is the JVM forced to use them?** No. The JVM still verifies the definition; errors can block loading/retransformation.
6. **Does skipping a class during a retransform always erase previous transforms?** No. Rules for reapplying output from non-retransform-capable transformers and other transformers still matter.
7. **Why should you return null before cloning?** To avoid parsing, allocating, and modifying out-of-scope classes.
8. **How do you prove the example modified class Changed?** Compare the run without the agent (**changed=BEFORE**) with the run with the agent (**changed=AFTER!**), while observing the callback returning a new byte[].

## 12. Standard references

- [Java SE 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): describes return null semantics, new byte arrays, unmodified input, invocation order of multiple transformers, and error handling.
- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): registering/removing transformers, capabilities, and retransform/redefine.
- [Java Virtual Machine Specification 17 — Class File Format](https://docs.oracle.com/en/java/javase/specs/jvms/se17/html/jvms-4.html): constant pool, method bytecode, class format, verification metadata.
- [Java SE 17 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): manifest, Premain-Class, and agent entry point.

**Rule to remember when writing a transformer:** **No change → return null. Change → create a new byte[], modify the copy into a valid class file, and return it.** Only then use the JVM's verification result and behavioral tests to confirm the transformation actually took effect.
