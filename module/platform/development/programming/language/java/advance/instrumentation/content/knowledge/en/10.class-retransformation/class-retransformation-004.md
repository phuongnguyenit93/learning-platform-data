# Initial Data Is Taken from the Most Recent Definition or Redefine

In Java instrumentation, `Instrumentation.retransformClasses(...)` allows re-running the bytecode transformation pipeline for a class **already loaded by the JVM**. A very easy point to misunderstand is the data source for a retransformation pass: does the JVM simply take the hook-instrumented bytecode from the previous retransform pass and layer further modifications directly on top of it?

**Not by default in that way.** According to the `java.lang.instrument` Javadoc, each retransform pass starts from **the class file data from the original definition via `ClassLoader.defineClass` or the most recent `Instrumentation.redefineClasses`** — prior to the transformations applied during that corresponding load/redefine. The JVM automatically reuses the results of transformers that do not support retransformation and calls back the transformers that do support retransformation. In other words, the starting baseline depends on the **most recent define/redefine**, and does not automatically update after each retransform.

An important caveat must be added: the data the JVM uses to start **represents** the bytes that were passed during the define/redefine, but **is not required to be byte-for-byte identical**. The constant pool may be reordered or have entries added/removed; some attributes or the order of methods may differ. Therefore, saying "taking the initial bytecode" describes the **semantic and procedural baseline**, not a guarantee of an array identical to the `.class` file on disk.

This lesson belongs to the **Retransformation** group of Java Advance – instrumentation. After studying it, you will be able to accurately trace the define → retransform → redefine → retransform sequence, distinguish replay from new callbacks, handle idempotence, design diagnostics, check capabilities, and run a Java 17+ experiment with two transformers A/B yourself.

## 1. Distinguishing class definition, redefinition, and retransformation

| Operation | Typical triggering API | Are new class-file bytes supplied by caller? | Baseline for subsequent retransform |
| --- | --- | --- | --- |
| **Define** | `ClassLoader.defineClass` or native equivalent | Yes, these are the bytes used to define the class | The initial define, if not yet redefined |
| **Redefine** | `Instrumentation.redefineClasses(ClassDefinition...)` | **Yes**, each `ClassDefinition` contains the class and replacement bytes | **Switches to the most recent successful redefine** |
| **Retransform** | `Instrumentation.retransformClasses(Class<?>...)` | **No**, caller passes class objects; JVM retrieves the baseline itself | **Does not change the define/redefine baseline** |

**Define:** The JVM defines the class for the first time from the corresponding classfile bytes. Previously registered transformers may process the classfile bytes while the JVM prepares the definition. Those input bytes to define form the logical starting baseline prior to any transformation.

**Redefine:** The caller passes a new classfile, for example a recompiled version of the class with a different method body but the same supported schema. During redefine, transformers may be called; if the operation succeeds, the effective definition is updated. The baseline for subsequent retransform passes is **the input to the latest redefine**, prior to the transforms at that time.

**Retransform:** The caller does not pass new bytes to the JVM. Instead of patching directly on top of the previous retransform result, the JVM re-runs the pipeline from the saved define/redefine baseline using replay rules. A transformer may vary its output depending on configuration, but this is not a redefine in the sense of supplying a new classfile.

For example, consider a class named `Target`, with method version `V1` at D0 and `V2` at D1:

~~~text
LOAD Target V1  -> baseline D0
RETRANSFORM     -> starts from D0, does not become a new baseline
REDEFINE V2     -> baseline switches to D1 if successful
RETRANSFORM     -> starts from D1, does not revert to D0
~~~

If no redefine has ever occurred, even the tenth retransform pass still starts from the initial define baseline per the contract; it does not always use the bytecode from the ninth retransform pass.

## 2. Two groups of transformers that form the replay rules

When registering:

~~~java
instrumentation.addTransformer(transformerA, false);
instrumentation.addTransformer(transformerB, true);
~~~

the `canRetransform` parameter divides them into groups:

- **Retransformation-incapable** (`false`): the `transform` callback is invoked for matching load/redefine events, **and is not called again during retransform**. However, the **previous result** of the transformer from the most recent load/redefine **is automatically reused by the JVM** in the retransform pipeline. Not invoking a new callback **does not mean the transformation is lost**.
- **Retransformation-capable** (`true`): the callback is invoked on matching load, redefine, and **retransform** events. It can build new bytecode when agent configuration changes, while maintaining legal redefinition semantics and avoiding duplicating hooks.

| Event | A (`false`) | B (`true`) |
| --- | --- | --- |
| First class load | A.transform is called | B.transform is called |
| Redefine class | A.transform is called | B.transform is called |
| Retransform class | **Does not call A.transform**; JVM reuses A's result from load/redefine | **Calls B.transform again** |
| Change config then retransform | A does not recompute its result | B can compute according to the new config |
| Redefine then retransform | Replays A's result from the **new redefine** | B receives the pipeline from the new redefine baseline |

The table covers the case where the transformers actually observe the class in question. If a transformer is only registered after the class has already loaded, or if a dependency class is excluded, the actual behavior must be checked against the contract. Do not assume callbacks are guaranteed for every class in the JVM.

### 2.1. Illustration using baselines D0 and D1

Let:

- `D0` = initial data from define.
- `A0` = logical output of A applied to D0.
- `B0` = logical output of B applied to A0.
- `D1` = data supplied by a successful redefine.
- `A1` = logical output of A during redefine from D1.
- `B1` = logical output of B during redefine from A1.

~~~text
LOAD:
   D0 -> call A -> A0 -> call B -> B0 -> effective class

RETRANSFORM without redefine:
   D0 -> replay A0 [do not call A] -> call B again -> new effective class

REDEFINE:
   D1 -> call A -> A1 -> call B -> B1 -> new effective class

RETRANSFORM after redefine:
   D1 -> replay A1 [do not call A] -> call B again -> new effective class
~~~

Note: **B does not necessarily receive raw D0 or D1 bytes**. Because A precedes it in the pipeline, B may receive bytes that already contain A's modifications. Therefore, both absolute statements are false: "B always sees the pristine original file" and "B always sees all transformations from the previous retransform".

### 2.2. Transformer ordering

`ClassFileTransformer` specifies four groups, in order:

1. Retransformation-incapable Java transformers.
2. Retransformation-incapable native transformers.
3. Retransformation-capable Java transformers.
4. Retransformation-capable native transformers.

Within each group, ordering is based on registration order. During a retransform pass, non-capable groups are not called again; the results from the corresponding load/redefine are replayed. At the capable tier, new callbacks process the bytes present after the preceding tiers.

If a transformer returns `null`, it makes no changes to the bytes at **its own tier**. Returning `null` from B does not automatically undo modifications already replayed from A. If a transformer returns a new byte array, the JVM feeds that result into the pipeline for the next transformer; **do not mutate the input buffer directly** passed by the JVM to the callback.

## 3. "Initial" does not mean "a copy of the file on disk"

In the `Instrumentation.retransformClasses` documentation, initial class-file bytes represent the data previously passed to `ClassLoader.defineClass` or `Instrumentation.redefineClasses` prior to transformations. However, the JVM does not guarantee the same byte array or a byte-for-byte identical layout:

- The constant pool may have more or fewer entries.
- Entries may be arranged in a different order.
- Constant pool indices in method bytecode must still correspond to a valid interpretation.
- Some attributes may not be present.
- Ordering that has no semantic significance, such as the order of methods, may change.

Therefore:

~~~text
Original on disk:    SHA256(D0) = abc...
Bytes observed:      SHA256(observed) = def...
Semantic baseline:   can still correspond to D0
~~~

This is a **hypothetical illustration**, not a real checksum. Comparing hashes alone and concluding that the JVM picked the wrong baseline is inaccurate. Nor should you read `Target.class` via `getResourceAsStream` and assume that array is the exact bytecode currently executing after redefine/retransform: the resource on the classpath may still be the V1 file.

**Recommendation:** use a classfile/bytecode reader that understands the constant pool, method descriptors, attributes, and branch offsets; when idempotence is needed, check instruction patterns or reliable markers rather than relying solely on an absolute checksum. If diagnostics store classfile bytes, enforce memory bounds and security constraints because class bytes may contain strings or sensitive information.

## 4. When redefine occurs, how is the baseline updated?

For example, an application has already loaded `Target.version() = "V1"`, and then a tool performs:

~~~java
instrumentation.redefineClasses(
        new ClassDefinition(Target.class, version2ClassBytes));
~~~

**This snippet is illustrative only**: it requires appropriate `instrumentation`, `Target`, and `version2ClassBytes` variables, and is not a standalone program. If the call succeeds, the V2 class file is used by the JVM as the **input to the redefine**, and then the pipeline transformers process it. The baseline for the next retransform is **the V2 redefine data**, not V1.

If redefine fails, do not update the agent's state tracking to V2. `redefineClasses` can fail due to an unmodifiable class, invalid bytecode, a class name mismatch, or schema changes unsupported by the JVM. The documentation specifies that an error causes none of the classes in the set to be successfully redefined. You must inspect the actual error type rather than assuming that successfully reading the V2 file means V2 has been installed.

A class can be redefined multiple times:

~~~text
Define D0 -> Retransform -> Redefine D1 -> Retransform
          -> Redefine D2 -> Retransform -> Retransform
~~~

The last two retransforms are based on D2; they do not revert to D0 or D1 and do not automatically accumulate outputs from previous retransforms. Replaying non-capable transformers uses the results corresponding to redefine D2.

## 5. Complete Java 17+ experiment: A non-capable, B capable

We will run an experiment in **a single JVM**, using an agent launched via `-javaagent`. There are two versions of the `Target` class:

- `Target V1`: `version()` returns the string `"V1"`.
- `Target V2`: `version()` returns `"V2"`, keeping the same class name and method signature.

The agent registers two transformers, **A** and **B**, both of which only observe and return `null`. This way, the output clearly shows the **callback order** and **effective definition version**, without being obscured by bytecode transformations from a third-party library.

The example was compiled and actually run on OpenJDK HotSpot 21 with `javac --release 17`. The JVM must support `redefineClasses` and `retransformClasses`; runtimes lacking these capabilities will not produce the same output as the demo. Commands use JDK 17+ with the `javac` and `jar` tools.

### 5.1. Source file structure

~~~text
demo/
  Agent.java
  Main.java
  Target.java
  MANIFEST.MF
  v2/
    Target.java
~~~

The two files with the same name `Target.java` are in **two different directories**; they are compiled into two class files in two separate output directories. Do not place `v2out` on the runtime classpath because V2 is only passed via `ClassDefinition` during redefine.

### 5.2. File `Target.java` — V1 version

~~~java
public final class Target {
    public static String version() { return "V1"; }
}
~~~

### 5.3. File `v2/Target.java` — V2 version

~~~java
public final class Target {
    public static String version() { return "V2"; }
}
~~~

Both versions have the same binary name `Target` and the same method descriptor `()Ljava/lang/String;`. They differ only in the method body, so they fit within the redefinition scope supported by the demo.

### 5.4. File `Agent.java`

~~~java
import java.io.IOException;
import java.lang.instrument.ClassDefinition;
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.ProtectionDomain;

public final class Agent implements ClassFileTransformer {
    private static Instrumentation instrumentation;
    private final String id;

    private Agent(String id) { this.id = id; }

    public static void premain(String options, Instrumentation inst) {
        instrumentation = inst;
        if (!inst.isRedefineClassesSupported()
                || !inst.isRetransformClassesSupported()) {
            throw new IllegalStateException("JVM does not support demo capabilities");
        }
        inst.addTransformer(new Agent("A"), false);
        inst.addTransformer(new Agent("B"), true);
    }

    @Override
    public byte[] transform(ClassLoader loader, String name,
            Class<?> redefining, ProtectionDomain domain, byte[] bytes) {
        if ("Target".equals(name)) {
            System.out.println(
                    "TRANSFORM=" + id + ",existing=" + (redefining != null));
        }
        return null;
    }

    public static void redefine(Class<?> target, Path newClass)
            throws IOException, ClassNotFoundException,
                   UnmodifiableClassException {
        byte[] bytes = Files.readAllBytes(newClass);
        instrumentation.redefineClasses(new ClassDefinition(target, bytes));
    }

    public static void retransform(Class<?> target)
            throws UnmodifiableClassException {
        instrumentation.retransformClasses(target);
    }
}
~~~

Explanation:

1. `premain` receives `Instrumentation` from the JVM, checks both capabilities, and then registers A and B. The agent does not reference `Target.class` in `premain`, thereby avoiding proactively loading Target before registration.
2. A is registered with `false`, B with `true`. Both only print when `name` equals `Target`; in the default package, the internal name is `Target`.
3. `redefining` is `classBeingRedefined` from the five-parameter overload. It is `null` on a new definition and non-null on redefine **or** retransform. **You cannot reliably distinguish redefine from retransform solely by checking for null.**
4. `return null` indicates the transformer does not alter the bytecode. The printed messages are for learning purposes only; when writing a production transformer, avoid `println`/logging and synchronous network calls inside class-loading callbacks.
5. `redefine(...)` reads the V2 file and passes the byte array via `new ClassDefinition(target, bytes)`. `retransform(...)` takes no new bytes and simply asks the JVM to re-run the transformer pipeline.
6. The `Instrumentation` instance is provided to the agent at startup, not instantiated via `new` by the application.

### 5.5. File `Main.java`

~~~java
import java.nio.file.Path;

public final class Main {
    public static void main(String[] args) throws Exception {
        System.out.println("BEFORE=" + Target.version());

        System.out.println("STEP=REDEFINE");
        Agent.redefine(Target.class, Path.of("v2out/Target.class"));
        System.out.println("AFTER_REDEFINE=" + Target.version());

        System.out.println("STEP=RETRANSFORM");
        Agent.retransform(Target.class);
        System.out.println("AFTER_RETRANSFORM=" + Target.version());
    }
}
~~~

For simplicity, `Main` directly references `Agent` on the same application classpath; in a real product, the agent is typically independent of the application. From the `Main` source, you can see the exact points where redefine/retransform are requested and where the results are read.

### 5.6. File `MANIFEST.MF`

~~~text
Manifest-Version: 1.0
Premain-Class: Agent
Can-Retransform-Classes: true
Can-Redefine-Classes: true

~~~

This is a startup agent manifest, using `Premain-Class`. The two `Can-...` lines are capability requests and **do not guarantee** that every JVM supports them. Keep the trailing newline and blank line at the end of the manifest; `jar --manifest` puts these fields into `META-INF/MANIFEST.MF`.

### 5.7. Compile, package, and run

From the `demo/` directory containing the files:

~~~bash
javac --release 17 -d out Agent.java Main.java Target.java
javac --release 17 -d v2out v2/Target.java
jar --create --file demo-agent.jar --manifest MANIFEST.MF -C out Agent.class
java -javaagent:demo-agent.jar -cp out Main
~~~

- `out` contains `Agent.class`, `Main.class`, and the V1 version of `Target.class`.
- `v2out` contains the V2 version of `Target.class` and is **not** on `-cp`.
- The agent JAR contains `Agent.class` and the manifest declaring the capabilities.
- The `java` command enables the startup agent before invoking `Main.main`.

**Standard output compiled and verified exactly on OpenJDK HotSpot 21:**

~~~text
TRANSFORM=A,existing=false
TRANSFORM=B,existing=false
BEFORE=V1
STEP=REDEFINE
TRANSFORM=A,existing=true
TRANSFORM=B,existing=true
AFTER_REDEFINE=V2
STEP=RETRANSFORM
TRANSFORM=B,existing=true
AFTER_RETRANSFORM=V2
~~~

The output illustrates three phases:

- On **load**, both A and B are called with `existing=false`, and the method returns `V1`.
- On **redefine**, both A and B are called again with `existing=true`, and the method switches to `V2`.
- On **retransform**, **only B is called**, while A does not appear in the callback log; the method still returns `V2`.

This is empirical evidence of the callback counts and the method version invoked. It **does not** assert that the bytes seen by B during retransform are 100% identical to the `v2out/Target.class` file; the program does not measure byte arrays, and the contract does not guarantee byte equality either.

## 6. Exact meaning of the A/B output

### 6.1. Load: both callbacks run

~~~text
TRANSFORM=A,existing=false
TRANSFORM=B,existing=false
BEFORE=V1
~~~

Both transformers are registered before Target loads. Both receive callbacks; since both return `null`, the JVM uses the V1 code.

### 6.2. Redefine: both A and B are called

~~~text
STEP=REDEFINE
TRANSFORM=A,existing=true
TRANSFORM=B,existing=true
AFTER_REDEFINE=V2
~~~

Redefine does not run only B. Non-capable A is still called because this is **redefine**, not **retransform**. It processes the bytes supplied via `ClassDefinition`. After the redefine succeeds, the method now uses the V2 body.

### 6.3. Retransform: A is replayed without a callback

~~~text
STEP=RETRANSFORM
TRANSFORM=B,existing=true
AFTER_RETRANSFORM=V2
~~~

The absence of a `TRANSFORM=A` line means A **did not receive a new callback**; the JVM reuses A's result from the most recent redefine. B is called anew; it returns `null`. The baseline remains V2, not reverting to V1. Do not misinterpret this as "A was removed from the pipeline" or "A had `removeTransformer` called on it".

In the demo, both A and B are no-ops, so it does not prove that a specific bytecode patch is replayed. However, the callback pattern and post-redefine behavior match what the Java Instrumentation API describes. If you add a transformer A that inserts a real hook, you must use a bytecode editor with a verifier and separate tests to confirm replay, rather than inferring from a print-only demo that bytes were modified.

## 7. Transformations do not simply accumulate across each retransform

Suppose a capable transformer B adds a helper call to a method:

~~~text
B(input) -> output with an added helper call
~~~

A flawed design is to save B's output, and on the next retransform pass feed that output back into the modifier and **add another** helper call. The JVM contract does not force you to do that yourself. Typically, B is called again on a pipeline built from the **most recent define/redefine baseline**, plus replays from non-capable tiers before B.

However, **you must not conclude that every input arriving at B is free of hooks**: the D1 bytecode from redefine might already contain a hook, a non-capable A might have inserted a hook and been replayed, or earlier transformers in the pipeline before B might have modified the code. Therefore, idempotence must consider **the entire pipeline**, not just the explanation of the initial baseline.

A better approach for a transformer that actually modifies bytecode:

1. Filter accurately by internal class name, loader/module, method name, and descriptor.
2. Detect an already-present helper call using an instruction pattern or a reliable marker.
3. Exclude the helper/exporter/agent code itself to avoid call loops.
4. Given the same logical input and configuration, the output should be deterministic and not add unintended duplicate hooks.
5. Do not cache raw bytes from a previous retransform pass and use them as the default baseline for the next pass.
6. When redefine D1 succeeds, update expectations about the definition version and re-run the test suite.
7. Do not rely solely on `Arrays.equals` or a CRC of `classfileBuffer` to determine whether a class has been instrumented.

If you need to remove a capable transformer's hook, the desired result must be constructed based on the existing pipeline contract. Returning `null` from B **does not remove** modifications replayed from A. Similarly, removing B from the transformer list may affect subsequent retransforms, but does not mean all currently running active stack frames will immediately switch bytecode.

## 8. Difference between binary bytes and behavior

An agent may need to check a classfile checksum to identify a built artifact. However, during retransformation:

~~~text
Semantic baseline D1: definition passed to the most recent redefine
Byte array re-supplied by JVM: may differ in constant pool/attributes ordering
New behavior: also depends on replaying A and whether B transforms or is a no-op
~~~

All three are **three distinct concepts**.

Merely having `sha256(bytesFromTransform) != sha256(fileFromBuild)` does not prove the JVM used the wrong definition. Conversely, an original file having the same hash **does not prove** that transformer B returned the right output or that business behavior was unchanged.

For debugging, you must retain simultaneously: the D0/D1 build versions, the source of the define/redefine/retransform event, transformer capabilities, group ordering, transform error logs, and method execution results on selected inputs. If you need to dump bytecode as an artifact, the tool must describe it as bytes **at the point of observation in the pipeline**, not carelessly label it the "exact original .class file".

## 9. Limitations of redefine/retransform and common errors

### 9.1. Capabilities and manifest

Retransformation is an **optional** JVM capability. The agent must declare `Can-Retransform-Classes: true` in its manifest, the JVM must support it, and the specific class must be modifiable. Similarly, redefine requires `Can-Redefine-Classes: true` and corresponding support. You should check:

~~~java
if (!inst.isRetransformClassesSupported()) {
    // Cannot call retransformClasses in this configuration.
}
if (!inst.isRedefineClassesSupported()) {
    // Cannot call redefineClasses in this configuration.
}
if (!inst.isModifiableClass(targetClass)) {
    // Cannot replace the target class definition.
}
~~~

The snippet above is an **illustrative snippet inside a method that already has `inst` and `targetClass`**, not standalone source. `isModifiableClass` does not replace checking JVM-wide capabilities. Array classes and primitive types are not modifiable under this API.

If `addTransformer(transformer, true)` is called on an unsupported JVM, an `UnsupportedOperationException` may be thrown. If a class is not modifiable, `retransformClasses` may throw `UnmodifiableClassException`. Invalid replacement bytecode may cause `ClassFormatError`, `UnsupportedClassVersionError`, `LinkageError`, or other errors depending on the cause.

### 9.2. Do not arbitrarily change the schema

For redefinition/retransformation under the commonly applied JVM restrictions, you cannot arbitrarily change the class name, add/remove fields or methods, or change signatures or inheritance. Transforming method bodies while preserving the schema is a practical starting point. The V1/V2 demo uses that exact kind of change.

If redefine fails, the API installs no new definitions for any of the classes in that request. Do not record D1 as the "last successful redefine" merely because bytes were sent to the JVM; record success only after the method returns normally.

### 9.3. Static state, object instances, active stack frames

The Javadoc states that retransform/redefine does not re-run the class initializer and does not reset static variables. Existing object instances do not automatically become new objects either. If a method has **active stack frames** at the time of replacement, those frames continue executing the old bytecode; new invocations use the new method version.

Therefore, even when the new `Target.version()` method already returns V2, a long-running request in the middle of an older method version may continue following the old code. Do not immediately conclude that retransform failed based solely on a stack trace or the state of an in-flight request.

### 9.4. A failing callback does not always block the entire pipeline

An unhandled exception thrown by a `ClassFileTransformer` typically has the same effect as `return null` for the transformation at that tier: subsequent transformers may still be called and the JVM continues attempting the load/redefine/retransform operation. Therefore, do not rely on throwing an exception in a callback as a fail-closed mechanism for a security requirement. Design a safe strategy and record errors separately, avoiding complex logging inside class-loading callbacks.

## 10. Symptom-based diagnostic table

| Symptom | Likely explanation | Next step |
| --- | --- | --- |
| After retransform, A no longer prints | A is non-capable and is being replayed | Check the registration flag; do not jump to concluding A's hook was lost |
| After retransform, B still prints | B is capable | Check which tiers precede the input B receives |
| Redefine to V2 then retransform still returns V2 | Baseline switched to the latest redefine | Check whether any transformer actively alters the method |
| Redefine to V2 but retransform reverts to V1 | Agent/transformer may be patching from a cache, stale config, or altering the method | Trace the pipeline and test output; do not assume this is the JVM's baseline rule |
| Retransform bytes differ from JAR bytes | JVM is allowed to change constant pool/attributes | Parse the structure; do not perform blind bit-for-bit checks |
| Callback has `classBeingRedefined != null` | Could be redefine **or** retransform | Correlate with caller/phase; do not classify by null check alone |
| Class cannot be retransformed | Missing capability or unmodifiable class | Check manifest + `is...Supported` + `isModifiableClass` |
| Same hook appears twice | Duplicate patching in pipeline, redefine already contained the hook, or missing idempotence | Inspect instruction pattern, group ordering, and D1 source |
| V2 class returns wrong result | Helper/transformer altered behavior incorrectly, or V2 itself has different logic | Compare behavioral tests and method bytecode |
| A thread continues running V1 code | Old active frame is still executing | Check new invocations after the update point |
| Removed B but output does not change immediately | No new retransform has run yet, or active frames are still old | Check lifecycle and timing of definition replacement |

If you must collect data from inside a callback, use bounded counters/buffers, avoid synchronous console/network writes, and do not hold large `classfileBuffer` arrays in an unbounded cache. The demo prints logs directly only to observe event order; do not carry that exact pattern into production.

## 11. Further practice to distinguish baselines

### Exercise A: retransform twice without redefine

Modify `Main` in the experiment directory to call `Agent.retransform(Target.class)` twice before redefining. Observe that each time only B's callback fires; the version remains V1. This proves that A's callback count does not increase with the number of retransform requests.

### Exercise B: second redefine

Create a `v3/` directory containing `Target.java` with the same schema and `version()` returning V3; compile it to `v3out` and call `Agent.redefine(Target.class, Path.of("v3out/Target.class"))`. Then retransform. If the redefine is valid and both transformers are no-ops, the version must be V3, as that is the latest redefine baseline. There is no need to rename the class or add fields to test this.

### Exercise C: B changes configuration

Create a capable B with a config flag that changes between two retransforms and modifies bytecode according to the flag. Only do this once you have an appropriate bytecode toolkit/API and verifier tests. Compare bytes/output across both configurations; B must regenerate the transformation from the appropriate pipeline, not arbitrarily stack onto old output.

### Exercise D: A actually modifies bytes

Replace the no-op A with a non-capable transformer that inserts a valid hook. On retransform, verify that A does not receive a callback again while A's hook remains in effect. This is an advanced exercise; the current demo **does not prove this** with bytecode itself, and only observes the replay branch per the Javadoc contract.

### Exercise E: hash mismatch

Use a parser to compare the method body and constant-pool references between the source file and the bytes received by callback B. If the hashes differ, inspect the structural differences before concluding the JVM picked an old/wrong definition.

## 12. Common misconceptions to avoid

1. **"Retransform always continues from the previous retransform output."** Not the API contract. It starts from the most recent define/redefine, replays non-capable, and runs capable.
2. **"The baseline is always the class file loaded initially."** False once a successful redefine occurs.
3. **"Non-capable does not run, so its hook is removed."** False: its previous result is replayed.
4. **"Capable always receives the clean original class file."** False when a non-capable precedes it or the redefine input already has a hook.
5. **"Bytes must match the JAR file exactly."** No: the constant pool and some attributes may differ.
6. **"Non-null `classBeingRedefined` definitely means redefine."** No: retransform also has this value.
7. **"Redefine only invokes capable transformers."** False: both A and B are called per the contract during redefine.
8. **"Returning `null` from B undoes all prior transformations."** False: it is a no-op at B's tier.
9. **"A successful retransform creates a new baseline."** False: the baseline is the most recent define or redefine.
10. **"Loading an agent JAR guarantees the capability is available."** False: both the manifest and JVM must support it, and the class must be modifiable.
11. **"Redefine will re-run static initialization."** False: static state is preserved per the contract.
12. **"Active method frames switch to the new bytecode immediately."** False: old frames continue with the old bytecode.
13. **"Checking the classfile CRC alone tells you the logical version."** Insufficient because bytes may not be bit-identical.
14. **"Throwing from a callback prevents the JVM from completing retransformation."** You must not rely on that assumption.
15. **"A print-only demo proves that a bytecode hook was replayed."** No: the demo proves the callback pattern and behavior, whereas bytecode-hook replay must be tested separately.

## 13. Checklist for designing a safe retransform agent

1. Identify target classes/methods/loaders/modules; avoid instrumenting every JVM class unconditionally.
2. Declare capabilities properly in the agent manifest and check `isRetransformClassesSupported` and `isModifiableClass`.
3. Distinguish define baseline D0, redefine baselines D1, D2, and the replay/non-capable/capable pipeline.
4. Let capable transformers receive input at their proper tier; do not use cached bytes from the previous pass as the default source.
5. Design idempotent patches using patterns/markers to avoid duplicate hooks.
6. Keep transformers fast; avoid class loader circularity, loggers, reflection, and I/O on the class-loading path.
7. Do not mutate the `classfileBuffer` array directly; return a valid new buffer when actually transforming.
8. Verify schema constraints, verifier rules, method signatures, exception handlers, and stack frames.
9. Run tests for define → retransform ×2 → redefine → retransform ×2, comparing behavior, callback counts, and metrics.
10. Compare classfile artifacts by structure/semantics as well, not only by hash.
11. Monitor CPU/GC/latency overhead and the number of dropped diagnostic events.
12. Provide a way to roll back configuration, unregister transformers, and report verification errors.

## 14. Self-check questions

1. Does calling `retransformClasses(Target.class)` take a classfile byte array passed by the caller?
2. When no redefine has occurred, where does the baseline for the fifth retransform come from?
3. After a successful redefine from V1 to V2, does retransform revert back to V1?
4. Why can a `canRetransform=false` transformer still affect retransform output?
5. During retransform, does B receive data already modified by A?
6. Why is `classBeingRedefined != null` insufficient to distinguish redefine from retransform?
7. Is a hash mismatch enough to conclude the JVM used the wrong baseline?
8. Does returning `null` from B remove A's replayed output?
9. When redefine D2 fails, is the baseline used in the subsequent retransform D2 or the previous successful redefine?
10. Does a method with an active frame running across a redefine immediately use the new bytecode?
11. Why does the demo have `Can-Redefine-Classes` and `Can-Retransform-Classes` in the manifest?
12. If a new helper is used, what restrictions must be checked so the output forms a valid class definition?
13. Why does `Target.version()` returning V2 after retransform not prove the bytes are bit-for-bit identical to V2?
14. When the JVM does not support retransformation, how should the agent's request be handled?
15. How would you test the idempotence of a hook-inserting transformer across multiple redefines/retransforms?

## 15. Conclusion and official documentation

**Rule to remember:** during retransformation, the JVM starts from the class file data of the most recent define or redefine, automatically reuses the results of non-capable transformers, and calls capable transformers again. The previous retransform result **does not automatically become a new input baseline**. A successful redefine updates the baseline, and the initial bytes represented by the JVM may differ from the source file in the constant pool/attributes while still adhering to the contract.

By clearly understanding this boundary, you will not miscount callbacks, mistake replays for new calls, stack hooks infinitely, misidentify class versions from checksums, or accidentally reset V2 logic back to V1 when deploying complex agents.

**Further reading:**

- [Oracle Java 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `retransformClasses`, `redefineClasses`, support, and limitations; sufficient to cross-reference the demo code.
- [Oracle Java 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): starting from initial class file bytes, replaying non-capable, active frames, and constant pool.
- [Oracle Java 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): ordering of transformer groups and byte sources during define/redefine/retransform.
- [Oracle Java 21 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): `Premain-Class` and manifest capabilities.
- [JVM TI specification — RetransformClasses](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html#RetransformClasses): corresponding model when native agents are present.
