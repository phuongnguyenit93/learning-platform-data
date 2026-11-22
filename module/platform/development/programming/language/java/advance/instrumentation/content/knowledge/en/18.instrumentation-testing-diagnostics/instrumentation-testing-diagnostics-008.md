# Testing Multiple Retransforms, Redefines, and Agent Order Changes

A Java agent may work on initial class loading yet fail when `Instrumentation.retransformClasses(...)` is called a second time, when a class is redefined via `Instrumentation.redefineClasses(...)`, or when another agent appears before it on the command line. Symptoms can include duplicate probe insertions, changed advice order, abnormal invocation counts, bytecode verifier errors, or differing results between two `-javaagent` configurations.

In **Java Advance – instrumentation**, under **Testing and Diagnostics**, the requirement is to test **multiple retransforms, multiple redefines, and reversed agent ordering**. This is not merely a matter of "calling the API without throwing an exception"; you must verify application behavior after each change, which callbacks actually run, composition order, probe stability, and recovery when conflicting transformations occur.

This lesson presents the JVM rules, a test matrix, and a **runnable Java 17+ experiment** using two startup agents A/B, verifying results both before/after two retransforms, two redefines, and a subsequent retransform. The experiment actually mutates a constant string in the class file (without requiring external libraries), allowing you to observe differences caused by **agent ordering** rather than merely printing registration logs.

## 1. Distinguishing Load, Retransform, and Redefine

All three can pass through `ClassFileTransformer`, but their starting points and callbacks differ:

| Operation | Starting Point | Transformers Invoked | Key Checks |
| --- | --- | --- | --- |
| **Initial class loading** | Bytes provided by the class loader | Registered transformers, according to the defined groups and order | Class verifier accepts, method runs correctly, hook works |
| **`retransformClasses(C)`** | Original bytecode associated with the most recent define or redefine, re-prepared by the JVM | Transformers with **canRetransform=true** are invoked; previous results of the `false` group are automatically reused | No duplicate insertion; repeated runs remain correct; do not assume `false` callbacks re-run |
| **`redefineClasses(new ClassDefinition(C, bytes))`** | **New bytes supplied by the caller**, replacing the class definition | Both registered capable and incapable groups are invoked, in order | New bytes are valid, within JVM-supported schema, new behavior is correct, state is not reset |
| **`retransformClasses(C)` after redefine** | Based on the **most recent redefine**, not necessarily the original JAR | The `false` group reuses results from the most recent load/redefine; the `true` group re-runs | New version does not accidentally revert to the old baseline; no probe duplication |

From the `Instrumentation.retransformClasses` Javadoc: when retransforming, the JVM starts from the corresponding initial class file bytes; the output of non-retransform-capable transformers is **replayed without calling `transform()` again**; capable transformers are invoked again. "Initial class file bytes" are not necessarily byte-for-byte identical to the original `.class` file: the JVM may rearrange constant pool/attributes without changing meaning. Therefore, **do not compare hashes of the entire `classfileBuffer` to conclude the JVM misbehaved**.

### 1.1. `retransformClasses` Transforms Again, Not Appending New Bytes to Old Results

A common misconception:

```text
Wrong:
  load -> insert hook once
  retransform #1 -> take bytes that already have the hook and insert a second time
  retransform #2 -> continue inserting a third time

Correct understanding per the API:
  retransform -> JVM rebuilds the transformation chain from the corresponding baseline
  -> replays results of the incapable group
  -> invokes capable transformers again in order
  -> verifies and installs the new definition
```

However, **you must not rely solely on baseline behavior to skip idempotence checks**. If a capable transformer receives a classfile that already contains a marker introduced by another transformer or by the source of a `redefineClasses` call, unconditional advice insertion can duplicate hooks. Production bytecode instrumentation should detect existing methods/hooks/markers, verify structure before applying, or design transformations to be idempotent by contract.

### 1.2. `redefineClasses` Is Not Just an Alias for Retransform

With redefine, the caller supplies a `ClassDefinition(Class<?>, byte[])`. This byte array may come from a new build, a verified class file source, or a separate pipeline. It **does not automatically take** the running baseline and does not implicitly "reconfigure hooks" for you.

Example:

```java
// Illustrative snippet; requires inst, targetClass, and verifiedBytes to already exist.
inst.redefineClasses(new ClassDefinition(targetClass, verifiedBytes));
```

In principle, `redefineClasses` is appropriate when you want to supply a **new class definition**. If you want to re-apply the transformer pipeline to an already running class, `retransformClasses` is the more suitable choice.

## 2. Transformer Ordering Rules Matter More Than Apparent Registration Order

The `ClassFileTransformer` specification divides transformers into four groups and applies them in this order:

1. **Java transformers without retransformation capability** (`canRetransform=false`).
2. **Native transformers without retransformation capability** (JVMTI).
3. **Java transformers with retransformation capability** (`canRetransform=true`).
4. **Native transformers with retransformation capability** (JVMTI).

**Within each group**, transformers are invoked in **registration order**. The bytes returned by a preceding transformer (if non-`null`) become the input to the next transformer. `return null` means that transformer did not modify the bytes on that invocation.

Thus, if `premain(A)` registers `A.fixed` then `A.cap`, followed by `premain(B)` registering `B.fixed` then `B.cap`, the Java callback sequence for a loaded class is:

```text
premain(A): register A.fixed, A.cap
premain(B): register B.fixed, B.cap

transform(Target) — class load:
A.fixed -> B.fixed -> A.cap -> B.cap
```

It is **not** `A.fixed -> A.cap -> B.fixed -> B.cap`: the JVM groups noncapable before capable. On retransform, `fixed` **is not invoked again**, but its previously recorded result is reapplied, so looking only at callback logs shows:

```text
retransform(Target):
  [JVM reuses fixed transforms invisibly]
  A.cap -> B.cap
```

When redefining with `ClassDefinition`, all four Java transformers are invoked by group. If the two `-javaagent` options are swapped, the registration order within each group also swaps:

```text
B.fixed -> A.fixed -> B.cap -> A.cap
```

In real-world agents, native JVMTI hooks may interleave according to the **group order** in the specification. Furthermore, each agent may register transformers after `premain` or via runtime attach; do not infer the entire transformation order solely from the JAR name order on the command line.

## 3. Prerequisites and Safety Limits

Before putting a target into the matrix:

- Confirm the JVM supports `Instrumentation.isRetransformClassesSupported()` and `isRedefineClassesSupported()`. Both capabilities are **optional** and not enabled by default on every JVM.
- For a **startup agent**, set manifest `Can-Retransform-Classes: true` if you need to register capable transformers, and `Can-Redefine-Classes: true` if you need redefine. Actual availability still depends on JVM support.
- Check `Instrumentation.isModifiableClass(target)`. Some classes such as arrays, primitives, or special structures cannot be modified; avoid assuming every loaded class is modifiable.
- Specify the exact `Class<?>`: identity consists of **class name + defining class loader**. Two `demo.Target` classes defined by two different loaders are two distinct targets.
- Do not change schema beyond JVM limits: normally redefine/retransform **cannot add/remove/rename fields or methods, change method signatures, superclass, or interfaces**, and there are restrictions regarding class file attributes. Modifying method bodies/constant pool within valid limits is generally feasible.
- For a multi-class modification request, the API supports passing a set so related changes are applied within JVM capabilities. If the request fails, **no class in that request is modified** by contract; you must still handle errors and report clearly.
- A method with an active stack frame continues executing the **old** bytecode for that frame; new invocations use the modified method. Therefore, tests must use **new invocations** after each operation, not just observe an already-running call.
- Redefinition/retransformation does not re-run `<clinit>` solely because the definition changed; static field values persist. Previously created instances are not automatically reset. Tests should keep old objects and re-check them to verify.
- Do not concurrently invoke redefine/retransform on the same target group from multiple threads without coordination; interleaved event ordering makes tests non-reproducible.

## 4. Runnable Experiment in Java 17+: Two Agents A and B Mutating One Class

The example uses **one agent JAR** twice with arguments `A` and `B`. Each `premain` registers:
- one **fixed** transformer (`canRetransform=false`) that only logs;
- one **capable** transformer (`canRetransform=true`) that patches an eight-byte ASCII string constant in the constant pool of `demo.Target`.

There are two replacement values:
- Agent A wants the method to return `AAA00000`.
- Agent B wants the method to return `BBB00000`.

Whichever capable transformer runs **last** determines the observed string. When `-javaagent:A` and `-javaagent:B` are swapped, the application output swaps accordingly. Both transformers **recognize already-mutated constants** and overwrite intentionally, so subsequent retransforms do not accumulate "old + new" strings.

**Demo scope:** patching `CONSTANT_Utf8` directly below is only safe for ASCII literals of **equal** length and a controlled target. This is **not** a general-purpose bytecode manipulation library. In production, use ASM/Byte Buddy or an appropriate classfile library, check verifier/frames, and preserve class file invariants.

### 4.1. File Structure

```text
multi-agent-order/
├── agent.mf
├── src/
│   ├── agent/
│   │   └── MultiAgent.java
│   └── demo/
│       ├── Target.java
│       └── Main.java
└── out/                      # created during compilation
```

### 4.2. Target with Marker Constant

File `src/demo/Target.java`:

```java
package demo;

public final class Target {
    public String value() {
        return "BASE0000";
    }
}
```

The markers `BASE0000`, `AAA00000`, and `BBB00000` all have **8 ASCII characters**. Here, the Java compiler places the string literal in the constant pool; the transformer replaces the bytes of the UTF-8 entry referenced by `CONSTANT_String`. The demo does not alter method/field lists, descriptors, or the length of a `CONSTANT_Utf8` entry.

### 4.3. Agent and Two Transformers

File `src/agent/MultiAgent.java`:

```java
package agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.charset.StandardCharsets;
import java.security.ProtectionDomain;

public final class MultiAgent {
    private static volatile Instrumentation instrumentation;

    public static void premain(String id, Instrumentation inst) {
        if (!"A".equals(id) && !"B".equals(id)) {
            throw new IllegalArgumentException(
                    "Use -javaagent:agent.jar=A or =B");
        }
        instrumentation = inst;
        inst.addTransformer(new MarkerTransformer(id, false), false);
        inst.addTransformer(new MarkerTransformer(id, true), true);
        System.out.println("premain:" + id);
    }

    public static Instrumentation instrumentation() {
        return instrumentation;
    }

    private static final class MarkerTransformer
            implements ClassFileTransformer {
        private final String id;
        private final boolean capable;

        MarkerTransformer(String id, boolean capable) {
            this.id = id;
            this.capable = capable;
        }

        @Override
        public byte[] transform(
                Module module,
                ClassLoader loader,
                String className,
                Class<?> classBeingRedefined,
                ProtectionDomain domain,
                byte[] bytes) {

            if (!"demo/Target".equals(className)) {
                return null;
            }

            System.out.println("transform:" + id + ":"
                    + (capable ? "cap" : "fixed") + ":"
                    + (classBeingRedefined == null
                            ? "load" : "change"));

            if (!capable) {
                return null;
            }
            return patchLiteral(bytes,
                    "A".equals(id) ? "AAA00000" : "BBB00000");
        }

        private static byte[] patchLiteral(
                byte[] input, String replacement) {
            byte[] result = input.clone();
            int cpCount = u2(result, 8);
            int p = 10;
            boolean patched = false;

            for (int i = 1; i < cpCount; i++) {
                int tag = result[p++] & 0xFF;
                switch (tag) {
                    case 1 -> {
                        int len = u2(result, p);
                        p += 2;

                        if (len == 8) {
                            String value = new String(
                                    result, p, len,
                                    StandardCharsets.US_ASCII);
                            if (value.equals("BASE0000")
                                    || value.equals("AAA00000")
                                    || value.equals("BBB00000")) {
                                byte[] data = replacement.getBytes(
                                        StandardCharsets.US_ASCII);
                                System.arraycopy(data, 0, result,
                                        p, data.length);
                                patched = true;
                            }
                        }
                        p += len;
                    }
                    case 3, 4 -> p += 4;
                    case 5, 6 -> {
                        p += 8;
                        i++;
                    }
                    case 7, 8, 16, 19, 20 -> p += 2;
                    case 9, 10, 11, 12, 17, 18 -> p += 4;
                    case 15 -> p += 3;
                    default -> throw new IllegalArgumentException(
                            "cp tag=" + tag);
                }
            }
            return patched ? result : null;
        }

        private static int u2(byte[] b, int p) {
            return ((b[p] & 0xFF) << 8)
                    | (b[p + 1] & 0xFF);
        }
    }
}
```

Key characteristics to note:

1. `premain` is called twice **because the same JAR is specified twice**, with agent arguments `A` and `B`. This is an **experimental technique to observe ordering**, not recommended for loading the same agent twice in production.
2. Each invocation registers two **distinct transformer instances**; the same transformer object is not registered twice.
3. The callback only processes `className="demo/Target"`, avoiding touching JDK classes and the agent itself.
4. The `fixed` transformer returns `null`; it is used to demonstrate that **its callback does not run on retransform**, not to "freeze the entire class".
5. The `capable` transformer reads the bytes passed by the previous transformer and creates a new copy; it does not mutate the JVM's `classfileBuffer` directly.
6. `patchLiteral` walks the constant pool table, skips fixed-length tags, and replaces a UTF8 entry of exact length 8. For these ASCII characters, byte length and char length match; for real Unicode/modified UTF-8, such a simple byte-replacement rule cannot be applied.
7. Because the transformer accepts both the original value and the two mutated values, **a later transformer can overwrite an earlier transformer's result**; swapping agents produces a verifiable difference in method execution output.
8. `classBeingRedefined != null` in the callback only indicates that an **already-defined** class is being processed; in the demo we print the label `change` for both redefine and retransform. **Do not use this condition to accurately distinguish the two APIs**.

If a real application has multiple class loaders containing the same `demo.Target`, filtering by name alone is insufficient. You must combine loader identity, module, configuration, and avoid instrumenting the agent's own helper classes.

### 4.4. Driver Program

File `src/demo/Main.java`:

```java
package demo;

import agent.MultiAgent;
import java.io.InputStream;
import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.lang.reflect.Method;

public final class Main {
    public static void main(String[] args) throws Exception {
        Instrumentation inst = MultiAgent.instrumentation();
        System.out.println("support:retransform="
                + inst.isRetransformClassesSupported()
                + ",redefine="
                + inst.isRedefineClassesSupported());

        Class<?> target = Class.forName("demo.Target");
        System.out.println("modifiable="
                + inst.isModifiableClass(target));
        Object instance = target.getConstructor().newInstance();
        Method value = target.getMethod("value");
        System.out.println("initial=" + value.invoke(instance));

        for (int i = 1; i <= 2; i++) {
            System.out.println("retransform:" + i);
            inst.retransformClasses(target);
            System.out.println("after-retransform:" + i
                    + "=" + value.invoke(instance));
        }

        byte[] baseline;
        try (InputStream stream = target.getResourceAsStream(
                "/demo/Target.class")) {
            if (stream == null) {
                throw new IllegalStateException(
                        "Missing class resource");
            }
            baseline = stream.readAllBytes();
        }

        for (int i = 1; i <= 2; i++) {
            System.out.println("redefine:" + i);
            inst.redefineClasses(new ClassDefinition(
                    target, baseline));
            System.out.println("after-redefine:" + i
                    + "=" + value.invoke(instance));
        }

        System.out.println("retransform:post-redefine");
        inst.retransformClasses(target);
        System.out.println("after-post-redefine="
                + value.invoke(instance));
    }
}
```

Explanation:
- `Class.forName("demo.Target")` causes `Target` to be loaded **after** both agents have finished `premain`. `Main` does not reference `Target.class` before this point, making the logs easier to observe.
- Check both capabilities and `isModifiableClass` before modifying classes in a real system. The demo prints the values, and test runs verified environment support; if the JVM returns `false`, you must skip/mark unsupported rather than running blindly.
- `instance` and `Method value` are **retained** across all changes; calling `value.invoke(instance)` after each operation verifies that the existing object itself receives the new behavior.
- `getResourceAsStream("/demo/Target.class")` reads `.class` bytes **from the example's classpath** as data for `ClassDefinition`. It does not read the definition currently installed in JVM memory. In production, a JAR resource may not match the bytecode originally used by `defineClass`; you must obtain bytes from a trusted source and verify version and class loader.
- Both `redefineClasses` calls intentionally use the **same baseline**, allowing you to observe stability under the same input definition. Afterward, another retransform is run to test the transition path between the two APIs.

### 4.5. Manifest and Build

File `agent.mf` (**must end with a trailing blank line**):

```text
Manifest-Version: 1.0
Premain-Class: agent.MultiAgent
Can-Retransform-Classes: true
Can-Redefine-Classes: true

```

From the `multi-agent-order` directory, create the output directory on Linux/macOS:

```bash
mkdir -p out
```

Or on Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out | Out-Null
```

Compile with JDK 17 or later:

```bash
javac --release 17 -encoding UTF-8 -d out src/agent/MultiAgent.java src/demo/Main.java src/demo/Target.java
jar --create --file agent.jar --manifest agent.mf -C out agent
```

The command `jar -C out agent` packages only the `agent` package into the agent JAR; the `demo.Main` and `demo.Target` application runs from `out`. Use a JDK/JVM that supports both redefine and retransform, such as OpenJDK 21 used in this experiment. The agent file must be locatable from the working directory, or use an absolute path.

**Run configuration A then B:**

```bash
java -javaagent:agent.jar=A -javaagent:agent.jar=B -cp out demo.Main
```

**Reverse order B then A:**

```bash
java -javaagent:agent.jar=B -javaagent:agent.jar=A -cp out demo.Main
```

You must launch **two new JVM processes** to compare startup ordering. Changing order within an already-running JVM does not automatically reorder already-registered transformers.

## 5. Actual Output: A → B, Two Retransforms, Two Redefines

Here is the observed stdout using `javac --release 17` on OpenJDK **21.0.12.1** for configuration A before B:

```text
premain:A
premain:B
support:retransform=true,redefine=true
transform:A:fixed:load
transform:B:fixed:load
transform:A:cap:load
transform:B:cap:load
modifiable=true
initial=BBB00000
retransform:1
transform:A:cap:change
transform:B:cap:change
after-retransform:1=BBB00000
retransform:2
transform:A:cap:change
transform:B:cap:change
after-retransform:2=BBB00000
redefine:1
transform:A:fixed:change
transform:B:fixed:change
transform:A:cap:change
transform:B:cap:change
after-redefine:1=BBB00000
redefine:2
transform:A:fixed:change
transform:B:fixed:change
transform:A:cap:change
transform:B:cap:change
after-redefine:2=BBB00000
retransform:post-redefine
transform:A:cap:change
transform:B:cap:change
after-post-redefine=BBB00000
```

There are three core observations:

1. `premain:A` then `premain:B`, yet the **load callbacks** sequence is grouped `A.fixed → B.fixed → A.cap → B.cap`.
2. During the **two retransforms**, there are no `fixed:change` lines; the capable group `A.cap`, `B.cap` is invoked again. The result value does not accumulate into strange strings after each run.
3. During the **two redefines**, both fixed and capable are invoked again. After each redefine and after the subsequent retransform, the result remains `BBB00000` because B is the last capable transformer.

In this run, each `fixed` transformer had exactly **3 callbacks** for `Target` (1 load + 2 redefine); each `cap` transformer had exactly **6 callbacks** (1 load + 2 retransform + 2 redefine + 1 post-redefine retransform). Those are **callback counts in this scenario**, not JVM constants for all applications; if a class is loaded/redefined elsewhere, the counts differ.

## 6. Actual Output When Reversed B → A

Same classes, same source, only swapping the order of the two `-javaagent` options. Stdout on OpenJDK 21.0.12.1:

```text
premain:B
premain:A
support:retransform=true,redefine=true
transform:B:fixed:load
transform:A:fixed:load
transform:B:cap:load
transform:A:cap:load
modifiable=true
initial=AAA00000
retransform:1
transform:B:cap:change
transform:A:cap:change
after-retransform:1=AAA00000
retransform:2
transform:B:cap:change
transform:A:cap:change
after-retransform:2=AAA00000
redefine:1
transform:B:fixed:change
transform:A:fixed:change
transform:B:cap:change
transform:A:cap:change
after-redefine:1=AAA00000
redefine:2
transform:B:fixed:change
transform:A:fixed:change
transform:B:cap:change
transform:A:cap:change
after-redefine:2=AAA00000
retransform:post-redefine
transform:B:cap:change
transform:A:cap:change
after-post-redefine=AAA00000
```

Here `A.cap` is the last transformer, so the class returns `AAA00000`. **Reversing agent order is part of the test matrix** because two transformers can modify the same call site, advice stack, or constant pool, leading to different behavior even when each agent works correctly in isolation.

**Demo limitation:** the two agents mutate a constant string under a "last writer wins" policy. In real instrumentation, composition may result in both probes being inserted, two advices wrapping each other, or bytecode conflicts; it does not always mean "last agent wins". The experiment's goal is to prove that order **is observable and can alter results**, not to claim every transformer overwrites the previous one.

## 7. Multi-Pass Test Matrix: Do Not Check Only the Final Result

For each A/B agent pair or each new version/configuration, you should have at least the following table:

| Test Case | Action | What Must Be Verified |
| --- | --- | --- |
| **No-agent baseline** | Run application without `-javaagent` | Original behavior and baseline classes are clearly defined |
| **A only** | Single startup agent | Result/hooks match A; classload succeeds |
| **B only** | Single startup agent | Result/hooks match B; classload succeeds |
| **A → B** | Two agents in this order | `premain`, callback order, method behavior, and probe count |
| **B → A** | Reverse startup order in a new JVM | Compare intentional differences and conflict errors |
| **Retransform #1** | `retransformClasses(target)` | Capable callbacks invoked; incapable reused; no duplicated advice |
| **Retransform #2…N** | Repeat the same transformation | Probe logic/counters per *new call* do not increase unexpectedly; callbacks do not duplicate due to repeated registration |
| **Redefine #1** | Supply valid `ClassDefinition` | Both groups invoked; class remains valid; new method works |
| **Redefine #2…N** | Same bytes or another verified version | No accumulation of wrappers/probes; state/instances are not unexpectedly reset |
| **Retransform after redefine** | Call API immediately after redefine sequence | New baseline is used; does not unintentionally revert to old behavior/JAR |
| **Toggle probe on/off** | Change config, retransform by design | Probe is truly disabled, no extra advice remains if removed; not just decrementing a counter |
| **Different class loaders** | Same binary name in two loaders | Does not mistakenly modify wrong class loader instance or miss helpers |
| **Schema/bytes error** | Test invalid class file in an isolated environment | JVM rejects change with clear message; does not partially install a batch |
| **Concurrent load** | Threads invoke method while redefinition occurs | No deadlock/crash; distinguish old active frames and new invokes |
| **Unregister agent** | `removeTransformer` | Future callbacks stop; understand that old bytes are not immediately reverted |

If performance measurement is a goal, add latency/CPU/memory/class-load time in the same environment. A transformation that "works once" is not representative of the cost when repeated multiple times under load.

### 7.1. What to Assert in CI

You should verify using conditional tests and structured output, rather than just `grep`ping a single line:

- **Capabilities**: `retransform` and `redefine` report `true`, `isModifiableClass(target)` is correct.
- **Callback sequence**: compare **lines related to target**, do not infer from other classes the JVM is loading.
- **Callback count**: for the example, each `fixed` must run on load and both redefines, **not run** on the three retransforms; each `cap` runs on all five post-load operations.
- **Semantic output**: `value.invoke(instance)` returns the expected result after each operation, not only after the final operation.
- **No duplication**: hook count per method call matches expectations on retransform 1/2/N; detect duplicated advice wrappers.
- **No stale baseline**: after redefine, retransform does not revert to the pre-redefine version.
- **Error path**: when `isModifiableClass=false` or the JVM lacks capability support, tests report an **intentional SKIP/UNSUPPORTED**, not pass.
- **Reproducibility**: change only one factor when comparing: agent order; fix JVM version, flags, JAR hashes, class loader, and testcase.

Remember that the `transform:...:change` log in the demo **does not distinguish APIs**; that is why the test harness prints `retransform:1` and `redefine:1` **outside the callback**. In a real system, design a per-operation correlation ID if you must debug multiple threads or concurrent requests.

## 8. Common Expectation-Breaking Test Cases

### 8.1. A Transformer Registered with the Wrong Capability

If registered with:

```java
// Snippet in premain; transformer has already been initialized.
inst.addTransformer(transformer); // equivalent to canRetransform=false
```

then the transformer can still run on class load and redefine, but **will not be invoked again** during `retransformClasses`. Changing a configuration variable inside the transformer and expecting retransform to update the probe is wrong if the transformer belongs to the incapable group. For the callback to run again, you need the appropriate manifest/capability and to register with `inst.addTransformer(transformer, true)`.

If the JVM does not support retransformation, registering capable/performing the operation may throw `UnsupportedOperationException`. You must check `isRetransformClassesSupported()`, the manifest, and the actual Java VM, rather than assuming the error is only due to a missing JAR.

### 8.2. Misusing `return null` Semantics

`return null` means **this transformer did not modify the classfile bytes passed in that turn**. It does not mean `the JVM will automatically remove probes installed in previous turns` in all circumstances. On retransform, the JVM rebuilds the pipeline with incapable transformers' results replayed; a capable transformer now returning `null` may stop adding its own transformation, **but transformations from other transformers or bytes supplied by redefine still remain**.

You must check **method behavior** and actual bytecode after disabling a hook, not rely solely on a callback's return value.

### 8.3. Inserting a Probe a Second Time Because Input Already Has a Hook

If an agent receives bytes that already contain `INVOKESTATIC agent/ProbeHooks.hit()` and still inserts it again on every callback, the probe count can double. How to handle this:
- scan methods/call sites or agent-controlled marker attributes;
- have precise rules to detect already-instrumented code without mistaking business instructions;
- insert once per target identity + transform version, not per callback count;
- test `load → retransform × N → redefine → retransform × N` by checking behavior and hook count;
- keep logic compatible with transformers **before and after**.

**Do not merely keep a `Set<Class<?>>` and skip all subsequent calls:** when the target is genuinely redefined with original bytes, you must be able to re-apply the hook. A simple "seen this class before" state can cause probes to disappear after a redefine. Idempotence should be tied to **the bytecode content being processed and the current instrumentation policy**.

### 8.4. Redefining with Bytes from the Wrong Source

If the caller reads a `Target.class` that does not correspond to the class loaded by the defining loader (different version, different package, different schema), the JVM may reject it or produce unintended behavior. The demo reads the resource from a self-controlled classpath solely to ensure a clear baseline.

With custom loaders/shaded JARs/multi-release JARs, you should record class identity, the hash of **trusted source data**, build ID, and the redefine operation's config. Do not rely on `getResourceAsStream` as a universal recipe to obtain bytes currently installed on the JVM.

### 8.5. Changing Field or Method Schema Live

A class file built with new fields or different signatures may run fine at startup yet **cannot** be redefined on the current JVM. The limits of `redefineClasses` and `retransformClasses` are not equivalent to loading a brand-new class. You must test negative cases for `UnsupportedOperationException` or appropriate `LinkageError`s, and confirm the batch is not partially installed.

### 8.6. Looking at Callback Logs and Assuming the Class Changed

A callback may print "transform ok" and return `null`; afterward another transformer may alter the result, or the JVM may reject the bytes. Therefore, at least three observation levels are needed:
1. **Pipeline**: which callbacks ran, in what order.
2. **Install**: whether the retransform/redefine API completed or threw an error.
3. **Runtime**: whether new method calls and hook data are correct.

The experiments in sections 5–6 check all three: callback logs, no API exceptions, and `value()` output after each step.

## 9. Class and State After Retransform/Redefine

Several properties are easily misunderstood during repeated runs:

- **Class identity**: target remains the same logical class in the same defining loader; the API does not create a parallel `Class<?>` to replace existing references.
- **Old instances**: objects created before redefinition continue to exist. When calling the *new* method, the JVM applies the new method definition according to supported rules.
- **Static state**: redefine/retransform by itself does not re-run `<clinit>`; existing static fields retain their values unless the program mutates them.
- **Active frames**: methods currently executing on the stack continue using the old code for that frame; new calls use the new code. When testing under load, logs may interleave outputs from before and after a change.
- **Class loader**: the JVM does not move the class to another loader on retransform/redefine; injected helpers must still be loadable and validly accessible from the target.
- **Constant pool**: representation may differ byte-for-byte across JVM class file reconstructions. Compare **semantics** or a purpose-built stable fingerprint, rather than assuming "the JVM must return the exact same bytes".
- **Pipeline result**: when an incapable transformer previously modified bytes, the JVM may replay that part without invoking its callback. Not seeing a `fixed` log during retransform **does not mean its transformation vanished**.

## 10. Testing with Multiple Real Agents

Beyond the single-JAR-run-twice experiment, production often has at least one combination:
- APM/observability agent, profiling agent, and coverage agent.
- Custom Java agent alongside Byte Buddy/ASM.
- Startup agent alongside a dynamic attach agent.
- Native JVMTI agent and Java `ClassFileTransformer`.

Transformers may write to the same method, alter class signatures, or add helper calls. Define a **composition contract**: probe A before B or B before A? If one transformer returns bytes that already have a probe, will the next transformer accept that structure? If A is temporarily disabled, does B still work properly?

### 10.1. Avoid Relying on Fragile Ordering When Possible

Good design prioritizes:
- separate allowlists and method scopes for each agent;
- markers or detection of existing advice;
- bytecode verifier and semantic checksums/signatures;
- distinguishing capable/incapable transformer types;
- testing startup order A→B and B→A in fresh JVMs;
- running canaries with the exact production JAR combination and flags;
- recording source/version/class loader in diagnostics.

If two agents strictly require an ordering, deployment documentation must specify and test the exact **effective transformer order** and JVM groups, not merely list two JARs in a Dockerfile.

### 10.2. `removeTransformer` and Rollback Capability

`Instrumentation.removeTransformer(transformer)` stops the transformer from being invoked on future events (callbacks may still be running concurrently during removal). **It does not automatically revert all already-transformed bytecode in loaded classes.** If you want to remove probes, you must design appropriate retransform/redefine logic, accounting for the effects of other transformers and the baseline currently used by the JVM.

Do not try to "reverse agent order" in a live JVM hoping to undo changes: group/registration order is established by the registration actions that already occurred. When comparing A→B/B→A, run two independent processes with equivalent test suites and JDKs.

## 11. Diagnosing Mismatched Results

| Symptom | Investigation Path |
| --- | --- |
| `retransformClasses` reports unsupported | Manifest `Can-Retransform-Classes`, JVM capability, how `addTransformer(..., true)` was called |
| `redefineClasses` reports unsupported | Manifest `Can-Redefine-Classes`, JVM capability, schema change |
| `UnmodifiableClassException` | `isModifiableClass(target)`, class kind, JDK/runtime |
| `VerifyError` / `ClassFormatError` | Classfile bytes, stack-map frames, constant pool, advice validity |
| `NoSuchMethodError` / `NoClassDefFoundError` | Helpers, dependencies, descriptors, loader/module visibility |
| Multiple retransforms duplicate probes | Non-idempotent transformer, source bytes already have hook, changes from another agent |
| Retransform does not invoke expected transformer | Transformer registered incapable, wrong className/loader filter, capability not enabled |
| Redefine loses probes | `ClassDefinition` source lacks hook, current transformer does not re-add it, return null/replay rules |
| Changing agent order changes logic | Bytecode composition order, transformer groups, advice conflicts |
| Class still returns old result right after redefine | Active stack frames, cached code path, call-site, or observing wrong object |
| `transform` callback reports success but API throws | JVM checks/verifies bytes after callback, schema/linkage error present |
| `premain` runs twice | Agent JAR specified twice in CLI, env, or wrapper |

**How to debug:** always log `Class<?> target`, `target.getClassLoader()`, `target.getModule()`, agent JAR/version, capability flags, config variables, and each operation. If callbacks must log, use a lightweight path and avoid loading complex dependencies during class loading.

## 12. Recommended Pre-Release Testing Workflow

1. **Lock the baseline:** JDK/vendor/version, JVM flags, classpath/module path, original class file hash, agent JARs/versions.
2. **Run class loading without agents** to establish baseline behavior.
3. **Run each agent independently** to determine what each agent modifies on its own.
4. **Run A→B and B→A** in two fresh JVMs, saving callback order and business results.
5. **Execute `retransformClasses` at least twice**, checking both callbacks that run/do not run and behavior/hook counts after each pass.
6. **Execute `redefineClasses` at least twice**, with valid bytes and a known version; do not test only once.
7. **Retransform after redefine**, verifying incapable transformers are replayed and capable ones run on the corresponding baseline.
8. **Test controlled failures:** capability false, unmodifiable target, invalid schema, unloadable helper; ensure clear error messages and no partial batch writes.
9. **Test concurrency and rollback plans** under production-like workloads; separate active stack frames from new invocations.
10. **Compare within the right scope:** hook counts, class identity/state, listener registrations, CPU/memory, startup overhead, and repeatability.

A test passes only when the API, applied bytecode, **behavior after each operation**, and agent ordering matrix all match expectations. Do not use "`premain` ran" or "`retransformClasses` did not throw an exception" alone as sufficient criteria.

## 13. Self-Check Questions

1. During retransform, why does a transformer registered with `canRetransform=false` not print new callbacks yet its previous transformation can still affect the class?
2. Why does `ClassFileTransformer` use fixed/capable group ordering rather than simply running sequentially across all `addTransformer` calls?
3. Why does the result `BBB00000` in A→B become `AAA00000` when reversed to B→A?
4. If `redefineClasses` receives bytes without a probe, when can the probe be re-applied? When can it disappear?
5. Why is comparing two `classfileBuffer` arrays with a raw hash insufficient to prove the JVM duplicated bytecode?
6. Why is `removeTransformer` not considered a rollback of all running classes?
7. Why must you check `isModifiableClass` in addition to the two capabilities `isRetransformClassesSupported`/`isRedefineClassesSupported`?
8. If an active stack frame is running old code while a new call uses new code, how should a test record that difference?
9. When multiple class loaders define `demo.Target`, which target must be identified before retransform/redefine?
10. Design assertions for the sequence `load → retransform ×2 → redefine ×2 → retransform` to detect duplicated, missing, or out-of-order callbacks.

## 14. Official Documentation

- [Java SE 21 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): four transformer groups, composition order, callbacks on load/redefine/retransform, and `return null` rules.
- [Java SE 21 — `Instrumentation`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, capabilities, `retransformClasses`, `redefineClasses`, active stack frames, and static state.
- [Java SE 21 — `ClassDefinition`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html): how to supply `Class<?>` and bytes for redefinition.
- [Java SE 21 — `java.lang.instrument` package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): startup agent `premain`, manifest attributes, and `-javaagent` invocation.
- [JVM Specification SE 21 — Class File Format](https://docs.oracle.com/en/specs/jvms/se21/html/jvms-4.html): constant pool and class file structural limits illustrated in the experiment.
