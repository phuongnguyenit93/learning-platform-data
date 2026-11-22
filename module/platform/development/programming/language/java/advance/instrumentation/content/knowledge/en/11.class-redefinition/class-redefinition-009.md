# Restoring Code via Redefinition: Definitions Must Be Compatible and Remain Subject to the Transformer Chain

## 1. The Problem: Why “Reloading the Original Class” Is Not Necessarily a Rollback

Suppose a Java agent has replaced the method body of a running class using `Instrumentation.redefineClasses(...)`. When wanting to revert to the previous version, one often thinks it suffices to retrieve the old `.class` file and call `redefineClasses` again. This idea **can work**, but it is **not sufficient to guarantee restoration of the executing bytecode**.

There are **two independent constraints**:

1. **The replacement definition must be compatible with the class already loaded by the JVM.** Standard redefinition allows modifying method bodies, the constant pool, and certain attributes, but does not allow arbitrarily changing the class name, field/method schema, signatures, modifiers, hierarchy, or other structures prohibited by the JVM/JVMTI.
2. **The bytes supplied to `ClassDefinition` still pass through any registered `ClassFileTransformer`s.** A transformer may re-insert tracing, replace literals, or alter the result. Therefore, **the rollback input bytes** may differ from **the final bytes installed by the JVM**.

This lesson focuses on the ability to **restore instrumented/redefined code** in a verifiable way: identifying the exact definition to restore, checking class identity and schema, controlling transformers, observing runtime results, and planning for error handling.

**Version scope:** The example code uses Java 17+, `java.lang.instrument`, and the `Can-Redefine-Classes` manifest attribute. Redefinition is an **optional JVM capability**; illustrative output assumes a common runtime such as HotSpot that supports this capability.

## 2. Relevant APIs

### 2.1. `ClassDefinition` Holds a Class and Full Class File Bytes Pair

```java
byte[] bytes = Files.readAllBytes(pathToOldClass);
ClassDefinition definition =
        new ClassDefinition(Target.class, bytes);
```

The snippet above is **illustrative**, not standalone: it requires importing `java.nio.file.Files`, `java.lang.instrument.ClassDefinition`, and having `Target.class` refer to the exact target class.

- `Target.class` is an **already loaded** `Class<?>` object, not a file name.
- `bytes` is the **entire valid class file content** (not Java source, a single method's bytecode, or JAR/ZIP bytes).
- The `ClassDefinition` constructor **retains the array reference**; it does not copy the bytes. Do not modify the array after creating the definition or while `redefineClasses` is using it.
- Two classes with the same binary name but defined by two different loaders have **two distinct class identities**. Use the exact target `Class<?>` to avoid restoring the wrong class.

### 2.2. `Instrumentation.redefineClasses` Requests the JVM to Replace the Definition

```java
instrumentation.redefineClasses(definition);
```

`redefineClasses(ClassDefinition...)` accepts one or more class/bytes pairs and replaces the definitions of the loaded classes; it **does not automatically locate the original file**. The call requires the appropriate capabilities:

```text
Agent JAR manifest:
Can-Redefine-Classes: true

JVM:
instrumentation.isRedefineClassesSupported() == true

Specific class:
instrumentation.isModifiableClass(Target.class) == true
```

The last condition only indicates that **the class can be modified**; it does not guarantee that all replacement bytes are valid.

When an error occurs in a call containing multiple `ClassDefinition`s, the Javadoc specifies that **no class in the set is redefined**. This is atomicity of the class redefinition operation on failure, **not** a transaction for application data, caches, DBs, or any running frames.

### 2.3. `removeTransformer` Only Unregisters, It Does Not Remove Installed Bytecode

```java
boolean removed = instrumentation.removeTransformer(transformer);
```

This call prevents future class definition/redefinition requests from passing through the corresponding registration. It **does not** automatically revert already transformed classes back to their original code. Some callbacks may still occur after removal due to concurrent class loading.

With multiple agents or multiple registrations, removing one transformer does not mean all other transformers are removed. In production, an agent should **only manage transformers that it owns**, and never attempt to disable other agents.

## 3. Three Different Byte Versions to Distinguish

To restore properly, one must first understand what “original code” the operator means:

| Layer | Symbol | Meaning |
| --- | --- | --- |
| **Original artifact** | `B0` | Exact class file from build/JAR before instrumentation, not passed through any transformer |
| **Redefine input** | `Br` | Full class-file bytes passed by the agent into `ClassDefinition` |
| **JVM-installed version** | `Beffective` | Result after passing through the transformer chain, verification, and application |

Diagram:

```text
Original file B0
    |
    +--- agent wants to rollback, sets Br = B0
                  |
                  v
       new ClassDefinition(Target.class, Br)
                  |
                  v
        JVM executes redefineClasses
                  |
                  v
       Transformer T1 -> T2 -> ... -> Tn
                  |
                  v
       Verification / JVM restrictions
                  |
                  v
          Beffective in JVM
```

If all transformers return `null` (no-op) for the rollback pass, `Beffective` may correspond to `B0`. If a transformer is still active and intentionally modifies bytes, then `Beffective = Tn(...T2(T1(B0)))` **does not necessarily equal** `B0`.

**Key takeaway:** A “successful rollback” in the sense that `redefineClasses` **throws no exception** only proves that the JVM accepted **the final result after transformations**. It does not prove that the exact original artifact was installed byte-for-byte or behaviorally.

Even when semantics are restored, JVMTI/JVM may normalize the constant pool, attributes, or internal representation. To confirm behavior, test **observable behavior** with the same class loader/JVM configuration and, when needed, inspect bytes at the appropriate transformer stage or via a suitable dump mechanism. Do not treat the hash of the original file on disk as sufficient proof of the bytes being executed by the JVM.

## 4. The Transformer Chain Still Runs During Redefinition

According to Java SE 17 `ClassFileTransformer`:

- During **class load** or **class redefine**, registered transformers are invoked in a chain, except in cases excluded by the specification such as transformer dependencies.
- For `redefineClasses`, **the input to the first transformer** is `ClassDefinition.getDefinitionClassFile()`, i.e., the bytes supplied by the caller.
- Any transformer that returns `null` does not change the bytes at that step; if a transformer returns a `byte[]`, the new bytes become the input to the next transformer.
- Group ordering: **Java transformers without retransform capability**, **native without capability**, **Java with capability**, **native with capability**; within each group, registration order is preserved.
- The `canRetransform=false` parameter **does not** mean “does not participate in redefinition”. It only affects the **retransformation** mechanism: there, the previous result of the non-capable group is reapplied by the JVM without invoking the callback.
- On the **redefinition** path, both transformers registered with `false` and `true` can be invoked again.

Two-agent example:

```text
ClassDefinition containing original bytes B0
                  |
                  v
T_trace (canRetransform=false)
    + adds probe / helper call
                  |
                  v
T_security (canRetransform=true)
    + checks/modifies method body
                  |
                  v
JVM installs output after both transformers
```

If the goal is “remove all probes”, passing `B0` is **not enough** while `T_trace` still adds probes. If you want to keep the security transform while removing tracing, you must know the exact policy/ownership of both tools and the effect of transformer ordering.

### “No Transformer Returned Bytes” Differs From “No Transformer”

A transformer may be invoked and return `null`. In that case, the result is unchanged at its step. Therefore, testing whether “a callback occurred during rollback” is not enough; you must test **output and behavior**. Conversely, if a callback still occurs from another agent, that is not automatically an error: system policy may require that instrumentation to always be present.

### When Transformers Have Side Effects

A transformer may record metrics, increment counters, or log when redefinition runs. The bytecode output may be a no-op while side effects still occur. A good rollback design must distinguish between:

- **The currently installed bytecode state**;
- **The registration state** of transformers;
- **Telemetry/agent state** (caches, counters, threads, helper objects, native hooks).

`redefineClasses` only handles the class definition; it does not automatically undo these side effects.

## 5. What Makes a Definition Compatible?

### 5.1. Preserving Exact Class Identity

`ClassDefinition(Target.class, oldBytes)` must supply a class file bearing **the exact name of `Target`**. Do not pass bytes of `OtherTarget.class` merely because it has the same method signatures. The JVM may throw `NoClassDefFoundError` when the class file name does not match.

If the application uses two loaders that both define `com.example.Service`, you must specify the **defining loader** of the target `Class<?>`. A `.class` file taken from the system classpath is not automatically the original of a class defined by a plugin/custom loader.

### 5.2. Schema Must Not Change Arbitrarily

In common JVMs, redefinition of an already loaded class accepts only a narrow set of changes. Things that must remain compatible include:

- Binary name and class defining scope;
- Superclass and interfaces;
- Set of fields, names, and descriptors;
- Set of methods, names, and descriptors;
- Modifiers/schema that JVM TI does not allow changing;
- Structural constraints such as nestmates, records, permitted subclasses, if applicable;
- Class-file version and format supported by the target JVM;
- Valid bytecode, proper constant pool/stack map frames, and linkable references.

Changing a method body from `return "patched";` back to `return "original";` with **the same name/descriptor/schema** is usually compatible. However, an old “original” that differs from the current schema can still be rejected.

**Tricky scenario:** A transformer **added a field** during initial class load. When calling rollback with bytes from the JAR **that do not contain that field**, if the transformer does not re-add the field on the redefine path, the final result differs from the schema of the class already installed by the JVM and may be rejected. This is why you should not look only at the original file and ignore transformer output.

### 5.3. Do Not Add/Remove Methods to “Remove Advice”

Instrumenting a method with Code does not allow deleting methods, changing signatures, converting native/abstract to concrete, or changing hierarchy during redefinition. When wanting to remove a call to a helper, you must generate a new valid body **within the same schema**; do not rely on editing the method/field list.

### 5.4. Definition Compatibility Also Depends on Runtime

A class file that is valid at build time may be invalid in the running JVM if:

- Its major version is higher than the JVM;
- Frames/control flow fail verification;
- Names resolve through a different loader/module than expected;
- Bootstrap/platform/module visibility differs from the build environment;
- Another agent modifies bytes in a way that makes the resulting schema incompatible.

The JVM checks **after the transformer chain has run**. Succeeding with `javac` is necessary but not sufficient; you must check **the final class file result** and test on the target runtime.

## 6. Restoration Does Not Undo Runtime State

### 6.1. Static Fields and Object State Remain

`redefineClasses` **does not reset static fields**, does not rerun the class initializer, and does not recreate instances. If previously instrumented code incremented a counter or wrote data, the rollback action does not reverse those side effects.

```text
Original version:  counter = 5
New version:       counter increments to 9
Rollback body to original: counter is still = 9
```

In the demo later in this lesson, the counter continues incrementing across multiple redefinitions to demonstrate this.

### 6.2. Active Stack Frames May Continue Running the Old Body

If a previous version of a method already has an active frame before the JVM installs the new definition, that frame **continues executing the old bytecode**. New invocations use the post-redefine method body.

Therefore, rollback is not “pause the world and switch all active frames to the old version”. Long-running operations, deadlocks, worker threads, or running callbacks may continue executing the previous version's logic for some time.

### 6.3. Does Not Create a Business Transaction

Batch redefinition is all-or-nothing **if the call fails**, but it does not roll back network operations, files, DBs, events, caches, or side effects of methods executed before rollback. If the new logic already mutated data, a separate data rollback or forward fix mechanism is required.

## 7. Java 17 Example: Rolling Back Original Bytes Still Gets Modified by a Transformer

The following experiment demonstrates **three different outcomes**:

1. Running the original version: the method returns `"original"`.
2. Redefining to the updated version: the method returns `"updated!"`.
3. Redefining back using **the exact original file**, while the transformer is still registered, so the literal `"original"` is replaced with `"filtered"`. After **removing the transformer**, the method still returns `"filtered"` until **redefining the original one more time**.

To make testing easy without external dependencies beyond the JDK, the sample transformer only patches **one `CONSTANT_Utf8` entry** in the constant pool of **class `Target`**. Both literals `"original"` and `"filtered"` consist of **8 ASCII bytes**, so replacing them does not change constant pool length or offsets. This is a **scoped demo**, not a general-purpose bytecode editor algorithm; in production, use ASM/Byte Buddy or an appropriate Class-File API.

### 7.1. Directory Structure

```text
rollback-demo/
├── src/
│   ├── v1/
│   │   └── Target.java
│   ├── v2/
│   │   └── Target.java
│   ├── LiteralTransformer.java
│   ├── RollbackAgent.java
│   └── DemoApp.java
└── agent.mf
```

Both `Target.java` files share the same binary name in the **default package**, but are built into **separate directories**. This is intentional so that one version is loaded by the JVM while the other only supplies replacement bytes.

### 7.2. `src/v1/Target.java`

```java
public final class Target {
    private static int calls;

    private Target() {
    }

    public static String value() {
        calls++;
        return "original";
    }

    public static int calls() {
        return calls;
    }
}
```

The `value()` method increments a static field and returns the literal `original`.

### 7.3. `src/v2/Target.java`

```java
public final class Target {
    private static int calls;

    private Target() {
    }

    public static String value() {
        calls++;
        return "updated!";
    }

    public static int calls() {
        return calls;
    }
}
```

v2 keeps **the exact same class name, field, constructor, methods, descriptors, and modifiers**. Only the body of `value()` changes the returned literal. Both versions are compiled targeting Java 17.

### 7.4. `src/LiteralTransformer.java`

```java
import java.lang.instrument.ClassFileTransformer;
import java.nio.charset.StandardCharsets;
import java.security.ProtectionDomain;

public final class LiteralTransformer implements ClassFileTransformer {
    private static final byte[] FROM =
            "original".getBytes(StandardCharsets.US_ASCII);
    private static final byte[] TO =
            "filtered".getBytes(StandardCharsets.US_ASCII);

    @Override
    public byte[] transform(
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {

        // Do not modify other classes and do not modify the initial load.
        if (!"Target".equals(className)
                || classBeingRedefined == null) {
            return null;
        }

        byte[] changed = patchConstantPool(classfileBuffer);
        if (changed != null) {
            System.out.println("[transformer] original -> filtered");
        }
        return changed;
    }

    private static byte[] patchConstantPool(byte[] source) {
        // Only accept class files generated by javac for the demo.
        if (source.length < 10
                || (source[0] & 255) != 0xCA
                || (source[1] & 255) != 0xFE
                || (source[2] & 255) != 0xBA
                || (source[3] & 255) != 0xBE) {
            throw new IllegalArgumentException("Not a class file");
        }

        int constantPoolCount = u2(source, 8);
        int offset = 10;
        byte[] output = null;

        for (int i = 1; i < constantPoolCount; i++) {
            int tag = source[offset++] & 255;

            switch (tag) {
                case 1 -> { // CONSTANT_Utf8
                    int length = u2(source, offset);
                    offset += 2;
                    if (length == FROM.length
                            && matches(source, offset, FROM)) {
                        if (output == null) {
                            output = source.clone();
                        }
                        System.arraycopy(
                                TO, 0, output, offset, TO.length);
                    }
                    offset += length;
                }
                case 3, 4, 9, 10, 11, 12, 17, 18 -> offset += 4;
                case 5, 6 -> { // Long/Double: two indices.
                    offset += 8;
                    i++;
                }
                case 7, 8, 16, 19, 20 -> offset += 2;
                case 15 -> offset += 3;
                default -> throw new IllegalArgumentException(
                        "Unsupported constant pool tag=" + tag);
            }
        }
        return output; // null means no changes.
    }

    private static int u2(byte[] bytes, int at) {
        return ((bytes[at] & 255) << 8)
                | (bytes[at + 1] & 255);
    }

    private static boolean matches(
            byte[] bytes, int at, byte[] pattern) {
        for (int i = 0; i < pattern.length; i++) {
            if (bytes[at + i] != pattern[i]) {
                return false;
            }
        }
        return true;
    }
}
```

**Why is this logic right for this demo?**

- The transformer filters strictly for `className = "Target"` and **`classBeingRedefined != null`**: it only processes redefinitions and does not modify the original version on initial class load.
- The transformer is registered in `premain`, before the application runs, and is invoked on `redefineClasses` calls.
- `patchConstantPool` traverses the **constant pool** structurally, replacing only an exact `CONSTANT_Utf8` match with ASCII bytes of the same length. If `original` is not found, it returns `null`.
- It does not mutate `classfileBuffer` in place; `output` is `clone`d before patching.
- The parser only serves valid classfiles from `javac --release 17`, without general bounds-checking; do not use it directly on untrusted class files or future classfile versions.
- For the v2 file which only has the literal `updated!`, the transformer does not find `original` and returns `null`: the v2 body remains unchanged.
- For the v1 file passed in for rollback, the transformer sees `original` in the input bytes and returns new bytes containing `filtered`.

**Do not use a lambda for `ClassFileTransformer`** on Java 17: the interface has two default overloads and is not a functional interface.

### 7.5. `src/RollbackAgent.java`

```java
import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;

public final class RollbackAgent {
    private static final LiteralTransformer TRANSFORMER =
            new LiteralTransformer();
    private static volatile Instrumentation inst;

    private RollbackAgent() {
    }

    public static void premain(
            String agentArgs, Instrumentation instrumentation) {
        inst = instrumentation;
        instrumentation.addTransformer(TRANSFORMER, false);

        System.out.println("[agent] supported="
                + instrumentation.isRedefineClassesSupported());
    }

    public static boolean ready() {
        Instrumentation instrumentation = inst;
        return instrumentation != null
                && instrumentation.isRedefineClassesSupported()
                && instrumentation.isModifiableClass(Target.class);
    }

    public static void redefine(Path file, String label)
            throws Exception {
        Instrumentation instrumentation = inst;
        if (instrumentation == null) {
            throw new IllegalStateException("Agent not initialized");
        }

        byte[] bytes = Files.readAllBytes(file);
        ClassDefinition definition =
                new ClassDefinition(Target.class, bytes);
        instrumentation.redefineClasses(definition);

        System.out.println("[agent] applied=" + label);
    }

    public static void removeOwnTransformer() {
        boolean removed = inst.removeTransformer(TRANSFORMER);
        System.out.println("[agent] removed=" + removed);
    }
}
```

`Can-Redefine-Classes` is the required capability, while the transformer is registered with `canRetransform=false`. **It still receives callbacks on redefine**: this is the central point of the example.

### 7.6. `src/DemoApp.java`

```java
import java.nio.file.Path;

public final class DemoApp {
    private DemoApp() {
    }

    private static void show(String label) {
        System.out.println("[main] " + label + "="
                + Target.value()
                + " calls=" + Target.calls());
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: DemoApp <baseline.class> <updated.class>");
        }

        // Target is loaded from app.jar and has not been modified by the transformer.
        show("initial");

        if (!RollbackAgent.ready()) {
            System.out.println("[main] skipped: unsupported");
            return;
        }

        // Install the version with the updated! literal.
        RollbackAgent.redefine(Path.of(args[1]), "update");
        show("updated");

        // Supply the original file, but the transformer is still active.
        RollbackAgent.redefine(Path.of(args[0]), "rollback");
        show("afterRollback");

        // Removing the registration does not change the already-installed code.
        RollbackAgent.removeOwnTransformer();
        show("afterRemove");

        // Supply the original file again, this time without passing through the transformer.
        RollbackAgent.redefine(Path.of(args[0]), "clean");
        show("restored");
    }
}
```

`show` both invokes `Target.value()` and reads the static counter. The counter makes it clear that redefinition **does not reset state**.

### 7.7. `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: RollbackAgent
Can-Redefine-Classes: true

```

The manifest must be inside the **agent JAR** loaded by `-javaagent`, the `Can-Redefine-Classes` attribute must be in the **main section**, ending with a blank line. `Can-Retransform-Classes` is not needed in this example because we only use **redefine**, not `retransformClasses`.

### 7.8. Compile, Package, and Run (Linux/macOS/WSL)

Open a terminal in the `rollback-demo/` directory:

```bash
mkdir -p build/v1 build/v2

# Compile two classes with the same name into two separate artifacts.
javac --release 17 -d build/v1 src/v1/Target.java
javac --release 17 -d build/v2 src/v2/Target.java

# App and agent are compiled with only the v1 class on the classpath.
javac --release 17 -cp build/v1 -d build/v1 \
  src/LiteralTransformer.java src/RollbackAgent.java src/DemoApp.java

# Agent JAR contains only agent code + manifest.
jar --create --file agent.jar --manifest agent.mf \
  -C build/v1 RollbackAgent.class -C build/v1 LiteralTransformer.class

# App JAR contains only Target v1 and DemoApp, NOT Target v2.
jar --create --file app.jar \
  -C build/v1 Target.class -C build/v1 DemoApp.class

java -javaagent:agent.jar -cp "agent.jar:app.jar" \
  DemoApp build/v1/Target.class build/v2/Target.class
```

**Expected stdout when the JVM grants redefinition capability:**

```text
[agent] supported=true
[main] initial=original calls=1
[agent] applied=update
[main] updated=updated! calls=2
[transformer] original -> filtered
[agent] applied=rollback
[main] afterRollback=filtered calls=3
[agent] removed=true
[main] afterRemove=filtered calls=4
[agent] applied=clean
[main] restored=original calls=5
```

Explanation:

1. On initial load, the transformer receives a callback with `classBeingRedefined == null` and does not modify bytes, so we get `original`.
2. Passing v2 into `ClassDefinition` makes the method return `updated!`. The transformer is invoked but makes no changes because it does not encounter the literal `original`.
3. Passing **the exact v1 bytes** to roll back. The transformer **still runs on the redefine path** despite `canRetransform=false` and replaces the literal with `filtered`. The JVM installs this result, not the verbatim value of v1.
4. `removeTransformer` returns `true` but the method still returns `filtered`; the registration changed, not the current definition.
5. Redefining one more time with v1 bytes **after removal** makes the method return `original` again. The counter still increments to 5, without being reset.

On a JVM without support, `ready()` returns `false`, and the program prints `[main] skipped: unsupported` and exits after the `initial` line. **Do not claim rollback ran** in that situation.

### 7.9. Windows PowerShell

Use `;` instead of `:` in the classpath:

```powershell
New-Item -ItemType Directory -Force build/v1, build/v2 | Out-Null

javac --release 17 -d build/v1 src/v1/Target.java
javac --release 17 -d build/v2 src/v2/Target.java
javac --release 17 -cp build/v1 -d build/v1 src/LiteralTransformer.java src/RollbackAgent.java src/DemoApp.java

jar --create --file agent.jar --manifest agent.mf -C build/v1 RollbackAgent.class -C build/v1 LiteralTransformer.class
jar --create --file app.jar -C build/v1 Target.class -C build/v1 DemoApp.class

java -javaagent:agent.jar -cp "agent.jar;app.jar" DemoApp build/v1/Target.class build/v2/Target.class
```

Run in the exact directory containing the manifest and JARs so that relative paths match.

### 7.10. Technical Scope of the Example

- There are no custom class loaders or other agents, so after `removeTransformer`, the final redefinition does not pass through **another** transformer. In production, this cannot be assumed.
- The literal patcher is only for same-length ASCII constant-pool UTF8 entries; it is not suitable for complex method instrumentation, different-length constant-pool UTF8 entries, or malformed class files.
- The v1/v2 classes preserve the **same schema**; if you add a field/method in v2 and try it, the JVM may reject it right at `redefineClasses`.
- `ClassDefinition` holds the v1/v2 bytes from disk. Bytes in the transformer callback before JVM installation may be transformed, so the meaning of a checksum must be tied to **the stage**.
- It does not call `getAllLoadedClasses()` or redefine all classes; the example intentionally targets a single application class.

## 8. Distinguishing Restore via Redefine vs. Retransform

| Criterion | `redefineClasses` to restore | `retransformClasses` after changing transformer config |
| --- | --- | --- |
| Input | Caller **supplies full class-file bytes** via `ClassDefinition` | JVM takes baseline bytes from the most recent define/redefine |
| Capability | `Can-Redefine-Classes` and `isRedefineClassesSupported` | `Can-Retransform-Classes` and `isRetransformClassesSupported` |
| Transformer `canRetransform=false` | **Invoked on redefine** if still registered | **Not invoked again**, JVM reapplies the recorded result from the previous load/redefine |
| Transformer `canRetransform=true` | Invoked on redefine | Invoked again |
| Easy to pick the exact old artifact? | Yes, if caller saved valid bytes and knows target identity | Does not choose which original file to use; relies on JVM-stored baseline bytes |
| Automatically resets object/static state? | No | No |
| Automatically removes instrumentation on remove transformer? | No | No; requires calling the appropriate API and understanding the pipeline |
| Biggest issue | Schema compatibility and transformer chain still runs | Baseline bytes may already be redefined, results of non-retransform-capable transformers are still reapplied |

**Pitfall when switching from redefine to retransform for a “quick rollback”:** If a class was previously redefined with v2, **the baseline bytes for the subsequent retransform are tied to the most recent redefine**, and do not automatically revert to the initial artifact. Furthermore, transformations from `canRetransform=false` transformers from the previous pass may be reused. Do not use `retransformClasses(Target.class)` as a general “undo”.

## 9. Controlled Restoration Process in Real Systems

### Step 1 — Define the Rollback Objective

Before making changes, clearly define what needs to be restored:

- **Behavior:** methods return results/emit events like the previous version.
- **Bytecode policy:** remove agent A's probes while keeping agent B's security policy.
- **Full effective definition:** return to the old executing code state, including intentional transformations.
- **Runtime/data state:** requires migration or compensation outside class redefinition.

These objectives are **not completely equivalent**. Restoring the old body does not automatically clean up thread-locals, metrics, static caches, or DB data.

### Step 2 — Save the “Recovery Snapshot” Before Intervention

Save at least:

- **Exact artifact/version** with checksum and reliable path.
- Binary name and **defining class loader identity**, module/layer if relevant.
- Class-file major version, schema fingerprint of field/method descriptors, and hierarchy.
- Transformer ownership and the list of **configurations** affecting output.
- Build timestamp and relevant JVM/JDK conditions.

If you want to restore an instrumented **effective definition**, saving only the `.class` file from the source JAR **may not be enough**. You need to design a way to reconstruct the pipeline output or ensure transformers produce the exact target output.

### Step 3 — Check Capability and Target

```java
if (!inst.isRedefineClassesSupported()
        || !inst.isModifiableClass(targetClass)) {
    throw new IllegalStateException(
            "Redefinition is not available for target");
}
```

This is an **illustrative helper**; `inst` and `targetClass` are provided by the actual agent. If capability is missing, do **not** attempt to work around it by loading a class with the same name in a new loader and claiming the old class was restored.

### Step 4 — Verify Replacement Before Installing

Check:

1. Do the bytes have the proper `CAFEBABE` format, class name, and major version?
2. Do fields/methods/hierarchy and modifiers preserve a runtime-compatible schema?
3. Can class references be resolved from the **correct loader/module**?
4. When passed through the transformer chain, is the final output still compatible?
5. Are bytecode/frames/exception handlers valid?
6. If replacing multiple classes in one pass, how do the classes interact with each other?

In complex environments, test on a staging JVM with the same agent chain and class-loader topology; **verifying bytes at build time alone is not enough**.

### Step 5 — Manage Transformers According to Policy

Appropriate options may include:

- **Keep transformers** and accept that the restored version still has tracing/security instrumentation.
- **Reconfigure self-owned transformers** to no-op for the target class, then run redefine.
- **Remove self-owned transformers** if possible, while understanding it **does not remove already-installed transformations**.
- **Coordinate with other agents** via official APIs/lifecycles instead of modifying registrations outside your control.

Do not assume you can “detach all transformers”: the JVM does not provide a simple public API to arbitrarily list/disable transformers belonging to all agents. Any lifecycle change must check thread-safety and callbacks that may still be running.

### Step 6 — Perform Redefinition in a Narrow Scope

Use `ClassDefinition` for each exact class. For tightly coupled classes, you can use **a single batch** to avoid a situation where one call fails after earlier calls have partially installed.

Understand that a batch guarantees **no partial redefinition succeeds if that call throws an exception**, but it does not create a barrier for all application threads or a transaction for business effects.

### Step 7 — Verify Execution Results

After success, check observable behaviors:

- **New** invocations use the target behavior;
- Existing objects remain valid;
- Static fields/state are not unintentionally reset;
- Tracing/profiling/security hooks are kept or removed according to policy;
- No `VerifyError`, `LinkageError`, class loader leak, or deadlock;
- Threads with old active frames are handled safely.

Depending on the system, readiness probes, synthetic transactions, or a canary environment may be needed before re-enabling traffic.

### Step 8 — Have a Recovery Path if It Fails

If rollback fails, do not keep overwriting speculatively multiple times. Save the stack trace, class identity, artifact checksums, and transformer configuration. You can:

- Halt the rollout and keep the currently running version;
- Try bytes that have been tested in the exact environment;
- Switch to a **forward fix** if restoring the old schema is not accepted by the JVM;
- Restart the JVM/re-rollout the old artifact if state needs to be reset and the agent chain isolated.

Restarting also does not automatically roll back data outside the JVM, so a separate state/data plan is needed.

## 10. Common Pitfalls

| Symptom | Cause | Remedy |
| --- | --- | --- |
| Called `removeTransformer` and the method still runs instrumented code | Remove only stops future callbacks, does not change the current definition | Controlled redefine/retransform or restart depending on the goal |
| Called `redefineClasses` with original file but still see hooks | Transformer is still registered and transforms the rollback bytes again | Check transformer chain, ownership, and policy of each step |
| Transformer `canRetransform=false` is still invoked during rollback | This parameter governs **retransformation**, does not exclude **redefinition** | Clearly distinguish the two APIs |
| `isRedefineClassesSupported() == false` | Agent lacks `Can-Redefine-Classes: true` manifest or JVM does not support it | Check actual agent JAR and runtime |
| `UnmodifiableClassException` | Target is not modifiable | Check `isModifiableClass` per class |
| `UnsupportedOperationException` | Missing capability or replacement changes unsupported schema/modifiers | Preserve schema, cross-check JVMTI and runtime |
| `NoClassDefFoundError` right at redefine | Class name in bytes differs from target class identity | Read the right classfile, exact binary name and loader |
| `ClassFormatError`/`VerifyError` | Corrupted bytes, invalid frames/stack/constant pool after transformer | Verify final output, use a proper bytecode library |
| `UnsupportedClassVersionError` | Replacement built for too new a JDK | Build with appropriate target, e.g., `--release 17` |
| Method still uses old logic despite successful restore | Active frames exist from before the redefine | Check new invocations; do not infer from running frames |
| Static state does not revert to old version | Redefinition does not rerun `<clinit>` or reset fields | Data/state migration or planned restart |
| Wrong plugin affected | Same class name exists across multiple loaders | Use exact `Class<?>`/defining loader/module |
| Rollback fails after a load-time transformer added a field | Original bytes are incompatible with current effective schema | Ensure transformer recreates compatible schema or use another recovery method |
| Removed an agent but effects still persist | Multiple transformers/native hooks or helper state remain active | Accurately identify ownership and pipeline order |
| Called retransform thinking it reverted to the initial artifact | JVM uses baseline bytes from the most recent load/redefine, reuses `false` transformer output | Use the right mechanism/bytes intended for restore; test the result |

## 11. Recommended Test Suite for Rollback

### 11.1. Schema Tests

- Same class name and target class loader;
- Same field/method descriptors, modifiers, superclass, and interfaces within JVM limits;
- No inserting/deleting fields or methods when the JVM disallows it;
- Compatible replacement class-file version;
- Final classfile after transformers passes verification.

### 11.2. Pipeline Tests

- No other transformers;
- One self-owned transformer still registered;
- Two transformers modifying the same method in different orders;
- One transformer returns `null`, one transformer produces new bytecode;
- A `canRetransform=false` transformer on the **redefine** path;
- After `removeTransformer`, old code remains until the next definition update;
- If using `retransformClasses`, test reuse of `false` transformers and the most recent baseline bytes.

### 11.3. Runtime Tests

- New method invocations receive the exact old behavior;
- Static counters/object state do not unintentionally reset;
- Methods with active frames complete with corresponding semantics;
- Exception paths, locks/synchronization, and interface dispatch are not broken;
- Agent callbacks are repeat-safe, not unintentionally duplicating hooks;
- When batch redefine fails, verify no class in the batch changed;
- Confirm rollback in a production-like JVM, with the exact agent JAR and configuration.

### 11.4. Limits of What Can Be Concluded

A test where `redefineClasses` returns normally proves **the call succeeded**, not that runtime data was reverted. A test where a method returns an expected string proves behavior on the tested path, not that all other methods or active frames are using the desired version. Write success criteria according to **the specific rollback objective**, not just a single boolean.

## 12. Self-Check Questions

**Question 1.** Does retrieving the byte array of the original file and calling `redefineClasses` always restore the bytecode verbatim?

**Answer:** No. The input bytes continue through the transformer chain; the final result may differ. The replacement must also be schema/class-identity compatible and accepted by the VM.

**Question 2.** Is a transformer registered with `addTransformer(transformer, false)` invoked when `redefineClasses` runs?

**Answer:** Yes. `false` only relates to **retransformation** capability; the transformer can still be invoked on load/redefine.

**Question 3.** Does `removeTransformer` returning `true` remove previously inserted probes?

**Answer:** No. It cancels registration; it does not automatically install a different class definition.

**Question 4.** If the original bytes are missing a field that was added by a transformer in the current class definition, is rollback guaranteed to succeed?

**Answer:** No. If the output after all transformers makes the schema differ from the definition the JVM currently accepts, redefinition may be rejected.

**Question 5.** Does a call to redefine back to the old body automatically reset instance and static fields?

**Answer:** No. Existing objects/state continue to persist; active frames may still execute bytecode of the previous definition.

**Question 6.** Why is `retransformClasses(Target.class)` not a general “undo” command?

**Answer:** It runs from the baseline bytes of the most recent load or redefine, reapplies results of `false` transformers, and re-invokes `true` transformers; it does not automatically fetch the old artifact prior to all redefinitions.

**Question 7.** When rolling back a batch of A and B throws an exception, is A half-replaced?

**Answer:** By the `redefineClasses` contract, no class in the batch is redefined if the call throws an exception. However, side effects that already occurred and application data are not transactionalized by the API.

## 13. Official Documentation

- [Oracle Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `redefineClasses`, `retransformClasses`, `removeTransformer`, capabilities, class state, and active frames.
- [Oracle Java SE 17 — `ClassDefinition`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html): `Class<?>` and full class-file bytes pair; constructor does not copy the buffer.
- [Oracle Java SE 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): transformers always participate in redefinition if registered, chain ordering, `return null`, schema limits.
- [Oracle Java SE 17 — `java.lang.instrument` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): `Premain-Class`, `Can-Redefine-Classes` manifest attributes, and how agents start.
- [Oracle Java SE 17 — JVM TI `RedefineClasses`/`RetransformClasses`](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html): class file restrictions and JVM semantics.
- [Java Virtual Machine Specification SE 17 — Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): constant pool structure and binary classfile format needed to enable transformations.

**Remember:** Restoring code via `redefineClasses` requires **(1) old bytes that are strictly compatible with the loaded class** and **(2) full control or understanding of the transformer chain**. `ClassDefinition` supplies the input, **not a guarantee that the final output remains verbatim**. Removing a transformer does not automatically undo, static state and active frames do not reset, and a reliable rollback must be tested across bytecode, behavior, and runtime lifecycle.
