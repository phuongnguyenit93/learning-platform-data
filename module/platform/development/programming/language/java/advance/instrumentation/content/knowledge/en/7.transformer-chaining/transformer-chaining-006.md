# Input-Deterministic Transformation and Repeat-Safe Processing in Java Instrumentation

## 1. Why Must a Transformer Be Stable?

In Java Instrumentation, a `ClassFileTransformer` can be invoked when the JVM defines a class, when a class is redefined, or (if the transformer supports it) when a class is retransformed. A class can also pass through **multiple transformers**, coming from the same agent or different agents. The output of the previous transformer is the input of the next transformer.

If every time the transformer encounters the same class file it unintentionally produces different bytecode, or each processing pass inserts additional hooks, wrappers, metrics, or fields, the system can easily run into:

- Different execution results between two startups despite having the same code and configuration.
- Logs/metrics being recorded two or three times because the same hook is inserted multiple times.
- Unpredictable stack traces and method call order; instrumentation overhead increasing with the number of passes.
- `ClassFormatError`, `VerifyError`, or errors during retransformation because the class file structure is no longer valid.
- Another agent failing to process the new output, or the pipeline changing behavior depending on registration order.

Two properties to design for are:

1. **Input-deterministic transformation** (*deterministic transformation*): the same input bytecode and the same fixed context/configuration produce the same result.
2. **Repeat-safe processing** (*idempotence* or *repeat-safe transformation*): when the same transformation is applied repeatedly to its own output, the result does not continue to change unintentionally.

These two properties are **different**. A transformation can be completely deterministic yet still insert an additional hook on every run; conversely, a transformation can avoid duplicate insertion yet still generate random helper names and therefore not be deterministic.

## 2. Explicit Modeling

Let `B` be the class file bytes, and `C` be the defined context (class name, class loader/module, agent configuration, schema version, and inputs that actually have an effect). For the effective transformation `T(B, C)`:

### 2.1. Determinism

```text
B1 = B2 and C1 = C2
             =>
T(B1, C1) = T(B2, C2)
```

Here, equality can be checked via **byte-for-byte equality** when that is the intended contract of the transformer; at minimum, **equivalent output semantics** must be ensured if the library produces different constant-pool ordering among valid class generation approaches. In a fixed test on the same tool/configuration, exact byte array comparison will detect nondeterminism most clearly.

Do not treat "input" as only the byte array if the transformer also reads configuration files, system properties, environment variables, module names, or loaders. When those values change, different output **does not violate** determinism for an input contract that includes them.

An example that is **nondeterministic** when wanting the same input to produce the same output:

```java
String helperName = "agent$" + System.nanoTime();
```

The same class file can receive two different helper names. A more stable approach is to generate the name from the class/method descriptor and configuration version, for example a fixed hash of `className + methodName + descriptor + ruleVersion`, and then handle collisions deterministically.

### 2.2. Idempotence

```text
T(T(B, C), C) = T(B, C)
```

This means re-processing **already-processed output** does not continue to increase the level of intervention. With bytecode instrumentation, "idempotent" is usually implemented by **detecting an existing hook** and not inserting another copy.

Example of a non-idempotent transformer:

```text
Initial:   public void work() { businessLogic(); }
Pass 1:    public void work() { trace(); businessLogic(); }
Pass 2:    public void work() { trace(); trace(); businessLogic(); }
```

A better transformer checks for the probe before inserting:

```text
Initial:   work() { businessLogic(); }
Pass 1:    work() { trace(); businessLogic(); }
Pass 2:    work() { trace(); businessLogic(); }   // No duplicate insertion.
```

**Note on the Java contract:** `ClassFileTransformer.transform(...)` is allowed to return `null` if no byte modifications are needed. When reasoning about `T` above, treat `return null` as the **identity operation**: the effective output equals the input bytes, rather than treating `null` as a class file.

### 2.3. Deterministic Does Not Automatically Mean Idempotent

The operation below always produces the same output given the same input:

```java
String addHook(String text) {
    return "trace();" + text;
}
```

It is deterministic but **not idempotent**: `addHook(addHook("work();"))` contains two occurrences of `trace();`. You need to add a condition to recognize already-instrumented code or rewrite the algorithm into a *canonical form*.

### 2.4. Idempotent Does Not Mean Side-Effect-Free

A bytecode-generating function may be idempotent, yet the callback still logs, increments a counter, registers a shutdown hook, or opens a resource **every time it is called**. Therefore, distinguish between:

- **Idempotence of the output class file**: no increase in hooks or wrappers in the bytes.
- **Repeat safety of side effects**: logging, thread/handler registration, caching, and state updates do not cause unwanted duplicated behavior.
- **Idempotence of the entire pipeline**: different transformers combined still do not produce new effects on each re-run.

Not all side effects must be eliminated. A "callback invocation count" counter that intentionally increments each time is valid; just do not use it as a value that alters bytecode generation when deterministic results are desired.

## 3. Practical Contract of `ClassFileTransformer`

An agent registers a transformer:

```java
instrumentation.addTransformer(transformer);
```

or:

```java
instrumentation.addTransformer(transformer, canRetransform);
```

When a class is defined, the JVM invokes transformers according to the specified grouping and registration order. In a transformer chain `A` then `B`:

```text
Initial class file bytes
           |
           v
A.transform(..., input)
           |
           +-- return null  -> keep input unchanged
           |
           +-- return bytes -> output A
           |
           v
B.transform(..., effective output of A)
           |
           v
JVM verifies and defines class
```

Principles:

- **Do not mutate the input `classfileBuffer` directly**. When modification is needed, create a **new `byte[]`**; do not modify the object passed to the callback.
- If no changes are needed, **return `null`**, not an empty array.
- The output must be a **valid class file** for the target JVM. An invalid byte array does not become correct just because the processing is deterministic.
- Class filtering uses JVM internal names such as `com/example/Service`; write it null-safely: `"com/example/Service".equals(className)`.
- `loader` can be `null` for the bootstrap loader. Different loaders can define two classes with the same name; do not merge caches solely by `className` when the output depends on the class loader/module.
- Transformers are called during class loading; avoid loading unnecessary extra classes, arbitrary I/O, recursion, or hard-to-control global locks.

On Java 17, both overloads of `ClassFileTransformer.transform` (the versions with and without `Module`) have **default implementations**. Therefore, `ClassFileTransformer` is not a functional interface: Java 17 examples should use a class/anonymous class overriding the method, and **not write a lambda** for this interface.

### When Multiple Transformers Exist

For two operations `A` and `B`:

```text
F(B) = B_transform(A_transform(B))
```

The composition `F` can differ if the order of A/B is swapped, meaning **it is not commutative by default**. Moreover, even if A and B are each individually idempotent, **F is not necessarily idempotent**.

A simple example on strings:

- `A` changes `a → b`; running it repeatedly on itself changes nothing further.
- `B` changes `c → a`; running it repeatedly on itself changes nothing further.
- The chain `F = B ∘ A` gives `F(c) = a`, but `F(F(c)) = F(a) = b`.

This explains why you must test **the entire pipeline in the exact registration order**, not just each transformer individually. Transformations need clear preconditions and ownership definitions: which transformer is allowed to insert which method, attribute, or hook; and how to recognize traces of another transformer.

## 4. Is Retransformation "Running T on T(B) Again"?

**Not necessarily.** This is a very important difference between the mathematical model for testing idempotence and the JVM mechanism.

According to `Instrumentation.retransformClasses` in Java SE 17:

1. The JVM starts from the **initial class file bytes** of the most recent definition or redefinition (which may not match the on-disk copy byte-for-byte because the JVM normalizes the constant pool and attributes).
2. For transformers registered with `canRetransform=false`, the JVM **reuses the previous result** and **does not call `transform(...)` again** for that transformer.
3. For transformers registered with `canRetransform=true`, the JVM **calls `transform(...)` again** on the bytecode along the chain being formed.
4. When valid, the JVM installs the new definition.

```text
First load:
  input B -> A(canRetransform=false) -> B(canRetransform=true) -> JVM

Retransform:
  initial bytes
     -> reapply previous output of A, DO NOT call A
     -> call B with input at the corresponding stage
     -> JVM
```

Therefore, multiple retransformations do not prove that the transformer received the exact output bytes of **the previous pass itself**. To test true idempotence, you need unit/property tests that **explicitly pass the output of T into T a second time**. At the same time, you must have integration tests on a real JVM because the `classfileBuffer` during retransform can differ from the byte array on the first load.

However, repeat safety is still important when:

- The same patch is accidentally registered **twice**;
- Multiple transformers share the same rewriting library;
- Build-time and runtime tools both instrument the same class;
- Redefinition brings an already-instrumented class back into the JVM;
- An agent toggles certain rules on/off and re-runs the pipeline across multiple classes.

The JVM allows registering the same transformer multiple times, but the API **discourages** this practice. Lifecycle and registration must be managed separately, rather than relying solely on bytecode idempotence to cure duplicate registration bugs.

## 5. Strategies for Creating Stable Transformations in Production

### 5.1. Based on Class Identity and Immutable Configuration

A policy can be represented as:

```text
TransformInput {
  className,
  definingClassLoader,
  module,
  classfileBuffer,
  immutableRuleSet,
  instrumentationSchemaVersion
}
```

Do not rely on `System.nanoTime()`, random UUIDs, unstable `HashMap` iteration order, or callback counts to generate helper names, probe IDs, or method/attribute ordering when determinism is required.

If configuration can change at runtime, take an **immutable snapshot** for each transform pass. Record the rule version clearly. Same input but a new config version yielding new output is intentional, not a nondeterminism bug.

### 5.2. Detecting Already-Applied Transformations

Common approaches when using ASM/Byte Buddy or equivalent tools:

- **Inspect bytecode structure**: look for the exact call to a known helper (owner/name/descriptor), or the instrumented wrapper pattern, before inserting.
- **Namespaced and versioned markers**: add a marker with clear ownership, only when the class format and JVM allow; the marker must reflect **the actual state**, not just a collision-prone string.
- **Canonical rewriting**: parse the method into a logical structure, strip probes belonging to older versions of the agent itself, and regenerate them exactly once according to current rules. This approach requires extreme care regarding probes from other agents.

A simple marker can become stale if another agent has modified the bytecode; marker checks and key structural checks should go together. Do not remove markers or hooks belonging to other tools without an explicit contract.

### 5.3. Generating Stable and Valid Output

- Use tools that understand the **constant pool**, opcodes, stack map frames, exception tables, method descriptors, and classfile versions; avoid arbitrary raw-byte find/replace on class/method name strings.
- With ASM, keep traversal/generation structure and the frames/max-stack computation strategy fixed. With Byte Buddy, keep configuration/matchers/naming strategies stable.
- Do not change the class schema during retransformation if the JVM does not support it; many kinds of field/method/supertype changes are restricted.
- If there are no changes, return `null`. If modified, return a valid new copy.
- If the transformer produces side effects, consider attaching a correlation ID/trace and a separate deduplication mechanism, without letting those side effects randomly dictate the bytecode.

## 6. Runnable Java 17 Example: A Deterministic and Idempotent Transformer

This example is **intentionally small** to observe input/output properties directly. It modifies exactly one ASCII string constant in the **constant pool** of a sample class:

```text
"ORIGIN"  ->  "PATCH!"
```

Both strings are 6 ASCII bytes, so there is no need to change the `CONSTANT_Utf8` length or subsequent offsets. The transformer only processes the `Target` class and does not mutate `classfileBuffer` in place.

The example illustrates the mechanism and is **not a general-purpose class file editor**. Production code should use ASM/Byte Buddy instead of writing a custom parser. The parser below recognizes Java 17 constant pool tags and assumes the input is a valid class file generated by `javac`; it is not intended to handle arbitrary data or corrupted class files.

### 6.1. Files to Create

```text
stable-demo/
├── StableAgent.java
├── PatchTransformer.java
├── Target.java
├── DemoApp.java
└── agent.mf
```

All classes are in the default package to focus on the algorithm. Run commands in the directory containing the files.

### 6.2. `Target.java`

```java
public final class Target {
    private Target() {
    }

    public static String value() {
        return "ORIGIN";
    }
}
```

This method contains the single literal `ORIGIN` that the transformer looks for in `CONSTANT_Utf8`. When the class is defined by the JVM through the agent, the literal will be replaced with `PATCH!`.

### 6.3. `StableAgent.java`

```java
import java.lang.instrument.Instrumentation;

public final class StableAgent {
    private StableAgent() {
    }

    public static void premain(String agentArgs, Instrumentation inst) {
        inst.addTransformer(new PatchTransformer(), false);
    }
}
```

The agent registers exactly one transformer, does not call retransform, and does not need `Can-Retransform-Classes`. The callback occurs when the JVM defines `Target` after the agent has been installed.

### 6.4. `PatchTransformer.java`

```java
import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;
import java.nio.charset.StandardCharsets;

public final class PatchTransformer implements ClassFileTransformer {
    private static final byte[] OLD =
            "ORIGIN".getBytes(StandardCharsets.US_ASCII);
    private static final byte[] NEW =
            "PATCH!".getBytes(StandardCharsets.US_ASCII);

    @Override
    public byte[] transform(
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {

        if (!"Target".equals(className)) {
            return null; // Do not interfere with other classes.
        }

        return patch(classfileBuffer);
    }

    // Pure function: same input bytes -> same output bytes.
    // Returns null if already patched or no literal needs replacement.
    public static byte[] patch(byte[] original) {
        if (original.length < 10
                || (original[0] & 0xff) != 0xca
                || (original[1] & 0xff) != 0xfe
                || (original[2] & 0xff) != 0xba
                || (original[3] & 0xff) != 0xbe) {
            throw new IllegalArgumentException("Not a class file");
        }

        int cpCount = u2(original, 8);
        int p = 10;            // Start of constant_pool.
        byte[] changed = null; // Allocate only when actually needed.

        for (int i = 1; i < cpCount; i++) {
            int tag = original[p++] & 0xff;

            switch (tag) {
                case 1 -> { // CONSTANT_Utf8
                    int length = u2(original, p);
                    p += 2;

                    if (length == OLD.length
                            && equalsAt(original, p, OLD)) {
                        if (changed == null) {
                            changed = original.clone();
                        }
                        System.arraycopy(
                                NEW, 0, changed, p, NEW.length);
                    }

                    p += length;
                }
                case 3, 4, 9, 10, 11, 12, 17, 18 -> p += 4;
                case 5, 6 -> { // Long/Double occupy 2 indices.
                    p += 8;
                    i++;
                }
                case 7, 8, 16, 19, 20 -> p += 2;
                case 15 -> p += 3;
                default -> throw new IllegalArgumentException(
                        "Unsupported constant pool tag: " + tag);
            }
        }

        return changed; // null = input does not need modification.
    }

    private static int u2(byte[] bytes, int p) {
        return ((bytes[p] & 0xff) << 8)
                | (bytes[p + 1] & 0xff);
    }

    private static boolean equalsAt(
            byte[] bytes, int offset, byte[] expected) {
        for (int i = 0; i < expected.length; i++) {
            if (bytes[offset + i] != expected[i]) {
                return false;
            }
        }
        return true;
    }
}
```

Detailed explanation:

- `transform` checks the exact internal name `"Target"`, because the sample class has no package; all other classes are untouched.
- `patch` only traverses the **constant pool** structure and does not search for the string by scanning the entire `classfileBuffer`; thus it never accidentally alters bytes in method bodies, length fields, or attributes.
- Only when a `CONSTANT_Utf8` with the exact 6 bytes `ORIGIN` is found does it create `original.clone()` and replace in the clone. The JVM still receives the original input array intact.
- On the next pass, the string is already `PATCH!`, and `ORIGIN` is no longer present; `patch` returns `null`, which is equivalent to "keep the already-patched input unchanged".
- The algorithm does not depend on clocks, randomness, invocation counts, or mutable global state.
- Cases `5` and `6` handle the rule that a Long/Double constant pool entry uses two indices. This simple example does not handle corrupted class files or tags in future formats.
- Replacing a literal of the same length does not change the class schema, method signatures, stack map frames, or offsets, so it is a valid modification for the sample class in Java 17.

In a real application, replacing a literal generally from the constant pool can affect **every place referencing** that constant, not just one method. Therefore, the example is limited to one class and one specific string; if you need to insert per-method hooks, analyze method structure and instructions using a bytecode library.

### 6.5. `DemoApp.java` — verify properties, then run the instrumented class

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

public final class DemoApp {
    private DemoApp() {
    }

    public static void main(String[] args) throws Exception {
        byte[] original = Files.readAllBytes(Path.of("Target.class"));
        byte[] snapshot = original.clone();

        byte[] one = PatchTransformer.patch(original);
        if (one == null) {
            throw new AssertionError("No ORIGIN literal found");
        }

        byte[] sameInputAgain = PatchTransformer.patch(original);
        byte[] secondPass = PatchTransformer.patch(one);

        System.out.println("[test] deterministic="
                + Arrays.equals(one, sameInputAgain));
        System.out.println("[test] idempotent="
                + (secondPass == null));
        System.out.println("[test] inputUnchanged="
                + Arrays.equals(original, snapshot));

        // First time the JVM uses Target after the agent is registered.
        System.out.println("[app] value=" + Target.value());
    }
}
```

The three `[test]` lines are verified by calling the **pure patch function** with the bytes of the `Target.class` file on disk. This is a self-contained test to verify `T(B)` and `T(T(B))`, and is **not** claiming that the JVM invoked the callback three times.

The `[app]` line confirms the JVM integration path: after `premain`, `Target` is defined and the transformer actually modifies the literal in the class bytes used for execution.

### 6.6. `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: StableAgent
Main-Class: DemoApp

```

Both attributes are in the **main section** and the file ends with a blank line. `Premain-Class` is used for `-javaagent`, while `Main-Class` allows running the application with `-jar`.

### 6.7. Commands to Compile, Package, and Run

Open a terminal in the `stable-demo/` directory. Use JDK 17+ with target 17 support:

```bash
javac --release 17 StableAgent.java PatchTransformer.java Target.java DemoApp.java
jar --create --file stable-demo.jar --manifest agent.mf StableAgent.class PatchTransformer.class Target.class DemoApp.class
java -javaagent:stable-demo.jar -jar stable-demo.jar
```

**Expected stdout on a compatible Java 17+ JVM**:

```text
[test] deterministic=true
[test] idempotent=true
[test] inputUnchanged=true
[app] value=PATCH!
```

Reasons:

- Two calls to `patch(original)` produce **byte arrays with identical contents**, even though they are two different objects.
- `patch(one)` returns `null`: no further modification needed, so the effective result after the second pass remains `one`.
- `original` is not modified because `patch` clones before writing.
- When the JVM loads `Target` from the JAR, the registered transformer changes `ORIGIN` to `PATCH!`, so the executed code returns `PATCH!`.

`javac` and `jar` normally print no stdout on success. If you run `java -jar stable-demo.jar` **without `-javaagent`**, no transformer is registered and `Target.value()` will return `ORIGIN`; however, the direct checks with `PatchTransformer.patch` still return `true` as before.

### 6.8. Scope of the Example

- The parser is only for valid class files from `javac` in the demo; it does not bounds-check every offset or handle malformed input, custom attributes, or all future classfile variants.
- You cannot replace arbitrary literals of different UTF-8 lengths by copying bytes at the same offset; when length changes are needed, the classfile representation must be updated properly according to spec.
- The article does not demonstrate method advice or constructor instrumentation; in production, use ASM/Byte Buddy with proper marker/structure checks.
- The code illustrates **bytecode idempotence**; it does not prove that a multi-agent pipeline is automatically idempotent. The next section describes how to test composition.

## 7. Properly Testing Stability

### 7.1. Unit/property tests for a single transformer

For each fixture `B` and configuration `C`:

1. Compute `x = effective(T(B, C), B)`, where a `null` output means keeping the input unchanged.
2. Compute `y = effective(T(B, C), B)` again from **the original input**. Verify `Arrays.equals(x, y)`.
3. Compute `z = effective(T(x, C), x)`. If the transformer is designed to be idempotent, verify `Arrays.equals(x, z)`.
4. Verify that input `B` was not mutated.
5. Use ASM `CheckClassAdapter` or have the JVM define the class to verify the output is valid; comparing hashes alone does not detect invalid classes.
6. Repeat with classes containing overloaded methods, constructors, annotations, generic signatures, exception handlers, records, lambdas, and target-appropriate modules/class loaders.

For transformers that return `null`, a test helper can interpret the result as follows (**illustrative snippet, not standalone**):

```java
static byte[] effective(byte[] input, byte[] result) {
    return result == null ? input : result;
}
```

Do not run `Arrays.equals(null, transformedBytes)` and conclude the transformer is not idempotent; `null` carries the valid no-op meaning under the instrumentation contract.

### 7.2. Integration tests on a real JVM

Register the transformer under production-like conditions:

- Test initial load via `-javaagent` with the real artifact.
- If supported, test `retransformClasses` with `Can-Retransform-Classes: true` and `addTransformer(t, true)`.
- If redefinition is used, also test `redefineClasses` on already-instrumented classes.
- Test multiple transformers in their **actual registration order**, because order and `canRetransform` capability determine the input bytes of each callback.
- Test two classes with the same name from different loaders, avoiding cache/key mixing across classloaders/modules.
- Test toggling configuration on/off: which classes are allowed to be updated and which must remain unchanged.

Accurately measure the number of probes in **application bytecode/traces**, how many times hooks actually execute, and output equivalence. The `transform` callback count can vary across JVMs/configurations; do not use callback count as the sole proof of idempotence.

### 7.3. Build reproducibility and artifact comparison

If byte-for-byte stable class output is required for caching, fix:

- JDK target and ASM/Byte Buddy version, rule/agent version;
- actual classfile input, module/class-loader context, and policy;
- transformer/visitor order, metadata serialization, and class/method naming scheme;
- byte/canonical hash comparison method.

Retransform results from the JVM may not match the initial class file bytes because the JVM is permitted to reorganize the constant pool/attributes within specification limits. **Do not compare hashes of two callback passes and conclude nondeterminism** if the actual inputs already differed. Log or snapshot the corresponding inputs and check the contract fairly.

## 8. Common Pitfalls

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Every build of the same source produces different instrumented bytecode | Randomly generated helper names, unstable map/set iteration order, timestamp metadata, or changing config | Fix input/config, sort structures, use deterministic naming, exclude volatile data from output |
| Hook runs twice after re-instrumenting | Failure to detect existing probe or running two instrumentation pipelines | Check structure/markers, insert only once, test `T(T(B))` |
| Transformer returns `byte[0]` to signal no modification | API misunderstanding | Return `null` for no-op; an empty array is not a valid classfile |
| Deterministic tests pass but output adds hooks on each pass | Determinism does not imply idempotence | Separately test the property `T(T(B)) = T(B)` |
| Both transformers are idempotent, yet the pipeline keeps changing | Composition is not necessarily idempotent, or two agents rewrite the same location | Test the exact order, establish ownership/preconditions, consider canonicalization |
| Retransform does not invoke a transformer | Transformer registered with `canRetransform=false` | JVM reuses old output; only `true` transformers receive callbacks on retransform |
| Two callbacks see different byte arrays even though source is unchanged | JVM may provide different bytes on retransform; an earlier transformer may also alter bytes | Measure input at each callback and evaluate the whole pipeline; do not compare raw hashes of different inputs |
| `VerifyError`/`ClassFormatError` | Invalid generated method/stack map/constant pool | Check classfile version, verify bytecode, use appropriate libraries and tests |
| Classloader leak after instrumentation | Cache holds strong references to `ClassLoader` or `Class<?>` of unloaded plugins | Use appropriate keys/lifecycles, release caches, consider weak references where safe |
| Data changes solely due to callback logging | Transformer depends on a counter, current time, or I/O results | Separate telemetry from inputs that determine output; snapshot immutable policies |
| First pass makes no change, later pass adds hook | Unsynchronized marker, rule depends on mutable state, or transformers A/B changed order | Clarify state, rule validity, pipeline order, and preconditions |

## 9. Checklist for a Stable Transformer Chain

1. **Define inputs completely**: `classfileBuffer`, class name/loader/module, and configuration version that can affect output.
2. **Deterministic**: same input and immutable context produce the same bytecode or same semantics per contract; do not use random/time/counters as sources for helper names.
3. **Idempotent as required**: after attaching a hook once, subsequent runs do not attach more; have reliable signals to recognize instrumented code.
4. **Standard no-op**: when unchanged, `return null` and do not mutate the input array.
5. **Composition**: test thoroughly with multiple transformers in exact order and control each agent's markers/hooks.
6. **Understand retransform properly**: distinguish `canRetransform=false` transformers (reused) from `true` transformers (re-invoked); do not assume you always receive the previous call's output.
7. **Valid classfile**: respect JVM limits, schemas, stack frames, class version, and bytecode verifier.
8. **Controlled side effects**: logging and resource registration do not duplicate unintentionally; clear rollback/de-registration.
9. **Observe real failures**: measure verify/linkage errors, actual hook executions, overhead, and impact when multiple agents are present.
10. **Integration tests on target runtime**: classloader/module, build tools, retransformation, and JVM-provided class files.

## 10. Self-Check Questions

**Question 1:** `T(x)` always inserts `trace()` before existing code, without using randomness. Is T deterministic?

**Answer:** Yes, if all inputs and rules are fixed. However, it is not idempotent because `T(T(x))` will insert two hooks.

**Question 2:** `transform` returns `null` when a class already has a marker. Does that violate idempotence because the Java return value has a different type?

**Answer:** No. Per the API, `null` indicates keeping the received bytes unchanged. Considering the **effective output**, it can be completely idempotent.

**Question 3:** The same transformer is registered with `canRetransform=false` and the JVM calls `retransformClasses`. Does the JVM invoke the callback again?

**Answer:** No. By contract, the previous result of a non-retransformable transformer is reapplied without invoking the callback.

**Question 4:** Two transformers A and B are each individually idempotent. Can we conclude `B ∘ A` is idempotent?

**Answer:** No. You must test the entire pipeline and execution order; two idempotent operations can still compose into a non-idempotent one.

**Question 5:** Same class and rule, yet `classfileBuffer` on the retransform pass has a different constant pool ordering than on the initial load. Does a different hash prove the transformer is nondeterministic?

**Answer:** No. The input **already differed**; you must compare results against **the same input bytes**, the same context, and the same algorithm version, or verify semantic/canonical output per contract.

## 11. Official References

- [Oracle Java SE 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): transformation chain, ordering, `return null`, not mutating `classfileBuffer`, semantics on retransform/redefine.
- [Oracle Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `retransformClasses`, capabilities, and reusing results of `false` transformers.
- [Java Virtual Machine Specification SE 17 — Chapter 4, The class File Format](https://docs.oracle.com/en/java/javase/specs/jvms/se17/html/jvms-4.html): constant pool, `CONSTANT_Utf8`, Long/Double occupying two indices, and class file limits.
- [ASM — User Guide / API](https://asm.ow2.io/): practical approach for rewriting bytecode, checking structure, and frames.
- [Byte Buddy — project documentation](https://bytebuddy.net/): instrumentation API capable of creating specialized advice and matchers.

**Takeaway:** **Deterministic** means same input/context produces same output; **idempotent** means re-processing output produces no further transformation; **repeat-safe** also covers side effects and interactions across multiple transformers. When the JVM retransforms, a callback is **not guaranteed** to receive the previous pass's output, so test both the pure transformation function and the actual instrumentation pipeline.