# What Happens When a Transformer Makes No Changes or Throws an Exception?

In Java Instrumentation, multiple `ClassFileTransformer` instances can participate together in processing a class definition. Two very important branches of the `transform(...)` method are:

- **No transformation needed:** return `null`. The class receives no changes from **this transformer**, and the input bytecode of that step is passed on to the next transformer.
- **Throwing an exception that the transformer does not catch:** according to the `ClassFileTransformer` contract, the JVM **still invokes the remaining transformers** and **still attempts** to perform the class load, redefine, or retransform. For the step in question, the exception has the same effect as **returning `null`**.

Common misconception: **an exception from one transformer does not automatically abort the entire transformation chain**, nor does it **guarantee that the class will ultimately load successfully**. Other transformers may produce valid or invalid bytecode, and the JVM still has to verify/apply the final class definition.

This article belongs to the **Transformer Chaining** topic, explaining the effect on bytecode input, invocation order, interaction with retransformation, how to measure/log failures, and a standalone runnable Java 17+ example.

## 1. Basic model: each transformer is a step in the pipeline

When a class is loaded, redefined, or retransformed, the JVM may invoke the appropriate registered transformers. Think of each callback as a step:

```text
B0 = initial class bytes for this pass
  |
  v
[T1.transform(B0)]
  | return byte[] B1  -> pass B1 to the next step
  | return null       -> pass B0 unchanged to the next step
  | throw exception   -> treated as null, pass B0 to the next step
  v
[T2.transform(...)]
  |
  v
[T3.transform(...)]
  |
  v
Bfinal = final bytes from the pipeline
  |
  v
JVM checks constraints, verifies, and attempts to define/update the class
```

In the diagram, `B0`, `B1`, and `Bfinal` are labels for the byte sequences at each step, not memory addresses or predefined Java variable names in the API. What matters is that **the output of the previous step becomes the input of the next step**. If the previous step produced no replacement output because of `null` or an exception, the next step receives the bytecode that existed **immediately before the failed step**.

### 1.1. Callback structure

Java 9+ has an overload with `Module`; Java 17+ still supports the five-parameter overload:

```java
byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer) throws IllegalClassFormatException;
```

- `classfileBuffer` is the **input bytecode to the current transformer**, not necessarily the original bytes read from the `.class` file on disk. A transformer that ran earlier may have already modified it.
- `className` is in internal name form, such as `com/example/Service`; it may be `null` in certain cases described by the API. Do not compare against the file name `Service.java`.
- `classBeingRedefined == null` generally indicates that the class is being defined for the first time. When non-null, the callback is being invoked during a redefine/retransform pass; **you cannot distinguish between those two operations based on this parameter alone**.
- `loader` is the defining class loader (may be `null` for the bootstrap loader); two classes with the same name but different defining loaders are two separate targets.
- `protectionDomain` provides the protection domain context when defining the class. Do not assume it is always non-null.
- Return value: a **new, valid byte array** if transformed; or `null` when not transformed. **Do not modify `classfileBuffer` in place**.

In Java 9+, the six-parameter overload `transform(Module, ClassLoader, String, Class<?>, ProtectionDomain, byte[])` delegates by default to the five-parameter overload if you do not override the six-parameter version. Therefore, the example below that overrides the five-parameter version will still be invoked on Java 17+.

### 1.2. Three common outcomes

| What the transformer does | Bytecode passed to the next step | Do subsequent transformers still run? | Does this mean the overall request succeeds? |
|---|---|---|---|
| `return null;` | The current bytes before this callback | **Yes**, according to the application chain | No; simply no change at this step |
| `return transformedBytes;` | The new byte array returned by the callback | **Yes** | Unknown yet; the JVM still has to check format/constraints |
| `throw new IllegalStateException(...);` uncaught | The current bytes before this callback, same as `null` | **Yes** | No; this is a transformer logic error, which may be ignored by the JVM at the transform step |
| `throw new IllegalClassFormatException(...);` | Effect on the pipeline is the same as `null` | **Yes** | No; a checked exception useful for diagnosing invalid input, does not by itself force class loading to fail |
| `return new byte[0];` or invalid bytes | The bytes returned by the callback, though very likely rejected by the JVM later | Subsequent callbacks may still be invoked before the JVM detects the error | **No**; may cause `ClassFormatError` or another error |

The table only covers the normal transform contract and cases where the callback returns/throws an error. Fatal JVM errors, instrumentation infrastructure errors, class file limits, or rejected redefine/retransform operations can still cause the overall request to fail.

## 2. `return null`: what does "no change at this step" mean?

A transformer typically only processes a specific set of classes. If the class name is out of scope or no longer needs modification, the standard code is:

```java
@Override
public byte[] transform(
        ClassLoader loader,
        String name,
        Class<?> redefining,
        ProtectionDomain domain,
        byte[] input) {
    if (!"com/example/OrderService".equals(name)) {
        return null;
    }

    if (!shouldInstrument(loader, name)) {
        return null;
    }

    // Illustrative only: createTransformedCopy must ensure
    // valid output bytes without modifying input.
    return createTransformedCopy(input);
}
```

This is **not a standalone program**: `shouldInstrument` and `createTransformedCopy` are illustrative method names that are not defined here. The complete executable program is in section 6.

### What `null` guarantees and does not guarantee

**You can conclude:**

- This transformer did not supply replacement class bytes on that invocation.
- Subsequent transformers still have the opportunity to process the input bytes at this step.
- If all transformers return `null` (or throw uncaught exceptions), the pipeline produces no replacement class bytes from those callbacks.

**You cannot conclude:**

- "The class has never been instrumented": an earlier transformer may have already replaced the bytes.
- "The class is definitely unchanged compared to the artifact on disk": the source class bytes may have already been modified by a build tool, class loader, another transformer, or an earlier redefine.
- "The class loaded successfully": the JVM still verifies the class bytes and performs the remaining class loading steps.
- "The agent ran as intended": the target filter, class loader filter, or configuration may be wrong so no transformer actually injected probes.
- "Zero overhead": the callback was still invoked and may have performed I/O, metadata checks, or object allocations before returning `null`.

### What about a new byte array with identical contents?

The API recommends **returning `null` if no transformation is needed**. If a transformer returns a new copy whose bytes are byte-for-byte identical, the JVM treats it as a replacement result at the callback layer, even though the behavior may be identical. This approach creates extra copying/overhead, easily skews "transformers modified" metrics, and does nothing to prove new probes exist.

To express intent clearly, follow this convention:

```text
no change intended  -> return null
change intended     -> return NEW well-formed byte[]; never modify input
```

`null` is not a zero-length byte array; `new byte[0]` **is different from `null`** and is not a valid class file.

## 3. Throwing an exception: why do subsequent transformers still run?

Java SE 21 specifies: if the `transform` callback throws an exception that it does not catch itself, subsequent transformers **are still called**; the class load, redefine, or retransform **is still attempted**. For the transform step in question, throwing an exception has the same effect as `return null`.

Visualize it as:

```text
T1.transform(B0) -> B1 (a valid class file)
T2.transform(B1) -> throws IllegalStateException
T3.transform(B1) -> B2 (a valid class file)
JVM attempts to verify/apply B2
```

**T2 failing does not discard B1.** Do not misinterpret this as the pipeline automatically rolling back to the original bytes `B0`. It keeps the bytes that existed right before T2 was called and continues to T3.

If `T1` also returns `null`, then `T2` throws an exception, and `T3` returns `null`, the bytes from the three callbacks remain unchanged from the start of the chain. However, that does not mean every part of class loading is guaranteed to succeed.

### 3.1. `IllegalClassFormatException` is not a command to "veto" class loading

`IllegalClassFormatException` is a checked exception declared on the five-parameter overload. If it sees that the input is not a properly formatted class file, the transformer **should throw this exception** to aid logging and debugging. However, per the API, it still has the same effect as `return null` on the transformation chain; it **does not by itself force the JVM to reject the class definition**.

If you want to **guarantee that a secure system must have probes**, you should not rely on "throwing an exception so the JVM blocks class loading". Design a fail-closed policy at the deployment/orchestration layer where you have control, verify that the agent and probes are active, or stop providing functionality if conditions are not met. Intentionally returning malformed bytes to break class loading is neither a fail-safe nor a portable strategy.

### 3.2. Runtime exceptions and Errors in the callback

A callback may encounter a `RuntimeException` from bytecode analysis code, an `IllegalClassFormatException` due to format issues, or fatal errors such as `OutOfMemoryError`. The API contract describes the exception behavior of a transformer, but **you should not design an agent that swallows fatal JVM errors** or treat catching every `Throwable` as always safe.

The Javadoc notes that a transformer can `catch (Throwable)` itself to avoid unexpected behavior when internal code throws unchecked exceptions. In production, consider selectively catching **recoverable** errors, logging them and returning `null`, while letting the system handle fatal errors according to a clear policy.

Example of diagnostic error wrapping (code is **illustrative, not standalone**):

```java
try {
    byte[] output = transformerLogic(input);
    return output; // null if unchanged, new byte[] if changed
} catch (IllegalClassFormatException e) {
    report("INVALID_INPUT", e);
    return null;
} catch (RuntimeException e) {
    report("TRANSFORMER_BUG", e);
    return null;
}
```

Here `transformerLogic` and `report` are methods you must implement yourself, and the logic for obtaining `input` and target metadata has been simplified. What matters is **reporting the error before falling back to `null`**. Do not catch and silently ignore all exceptions, which would lead users to believe instrumentation succeeded.

## 4. Transformer ordering: not always the global `addTransformer` order

There are two groups of Java transformers:

- **Retransformation incapable**: registered with `addTransformer(t)` or `addTransformer(t, false)`.
- **Retransformation capable**: registered with `addTransformer(t, true)` when the JVM supports it and the agent manifest requests the appropriate capability.

Application order in the specification:

1. Java transformers that **do not** support retransformation.
2. Native/JVMTI transformers that **do not** support retransformation.
3. Java transformers that **do** support retransformation.
4. Native/JVMTI transformers that **do** support retransformation.

**Within each group**, order follows registration order. Therefore:

```java
inst.addTransformer(transformerA, true);
inst.addTransformer(transformerB, false);
```

If registration succeeds, **B typically runs before A** when a new class definition or redefine is processed, because they belong to **different groups**, even though A was added first. If two transformers are both in the `false` group, they run in `addTransformer` order. This is an important point when depending on an earlier stage's output.

### 4.1. When are transformers invoked?

| JVM Event | Transformer registered with `false` | Transformer registered with `true` |
|---|---|---|
| Defining a new class | Invoked | Invoked |
| `redefineClasses` | Invoked | Invoked |
| `retransformClasses` | **Not invoked again**; the previously produced result is reapplied according to JVM rules | Invoked again |

During a retransform, the JVM starts from the appropriate base class bytes and automatically **reapplies the prior result as-is** from the incapable group from the previous load/redefine, rather than invoking `transform` on that group again. This is a mechanism specific to retransformation, **not** caused by whether a transformer returned `null` or previously threw an exception.

For example, transformer A is in the incapable group:

```text
Initial load:
  A (false) is invoked -> returns null
  B (true) is invoked  -> produces B1

Subsequent retransform:
  A (false) is NOT invoked again; A's previous transformation is reapplied
  B (true) is invoked again -> may produce a new result
```

If during load A produced bytes `A1`, during retransform A's transformation is reapplied according to the rules. If A produced no transformation, there is no "new A callback" to report an error or make a new decision. Therefore, do not expect that changing A's configuration variables and calling `retransformClasses` will cause A to run again.

**Note:** `ClassFileTransformer` does not guarantee that the "initial" bytes of a retransformation pass are byte-for-byte identical to the original class file. The JVM may change constant pool layout or attributes that do not affect semantics. Rely on the data provided by the API on the **current pass** rather than assuming byte-for-byte equality with an old artifact.

## 5. Transformer exceptions vs. errors when the JVM verifies the result

Distinguish between two kinds of failure:

### Type A — callback fails but the pipeline continues

```text
Transformer A -> valid byte[] A1
Transformer B -> throws exception
Transformer C -> return null
JVM           -> attempts to apply A1
```

Here, B's exception **does not automatically** prevent A1 from being tried. If A1 is valid in context, the class can still load/redefine/retransform successfully. B's failure must be recorded by B's own code or the agent's monitoring system; do not assume the application calling `Class.forName` will receive B's exception.

### Type B — final bytecode is invalid

```text
Transformer A -> return malformed byte[]
Transformer B -> return null
JVM           -> checks final class bytes, may reject
```

If the final bytes are invalid, the JVM may throw `ClassFormatError`, `VerifyError`, or related errors. For `Instrumentation.retransformClasses`/`redefineClasses`, the specification lists exceptions such as `ClassFormatError`, `UnsupportedClassVersionError`, `NoClassDefFoundError`, `ClassCircularityError`, `LinkageError`, or `UnsupportedOperationException` depending on the situation.

**Do not equate** "`throw` inside `transform`" with "`ClassFormatError` during JVM verification". They are two different layers:

- **Callback layer:** an uncaught exception is treated as `null` for that step.
- **Class file verification/application layer:** invalid final bytes or an invalid operation can cause **the entire overall request to fail**.

For a request to retransform multiple classes at once, the API specifies that if `retransformClasses(...)` throws an exception, **no classes in that group are retransformed**. This differs from an individual `transform` throwing an exception where the JVM still continues the callback chain.

## 6. Runnable Java 17+ program: one transformer returns null, one throws an exception, and the last transformer still runs

This example intentionally **does not modify bytecode** so the outcome is transparent. Three transformers of a startup Java agent are registered in the **same group** `canRetransform=false`, so callbacks occur in the order T1 → T2 → T3. T2 intentionally throws `IllegalStateException`; T3 is still called and the class can still run normally.

Create **3 files** in an empty directory: `ChainAgent.java`, `Demo.java`, `agent.mf`. No external libraries are needed.

### 6.1. `ChainAgent.java`: declaring the agent and three transformers

```java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class ChainAgent {
    public static void premain(String options, Instrumentation inst) {
        inst.addTransformer(new DemoTransformer("T1_NULL", false));
        inst.addTransformer(new DemoTransformer("T2_THROW", true));
        inst.addTransformer(new DemoTransformer("T3_NULL", false));

        System.out.println("AGENT_READY");
    }
}

final class DemoTransformer implements ClassFileTransformer {
    private final String id;
    private final boolean fail;

    DemoTransformer(String id, boolean fail) {
        this.id = id;
        this.fail = fail;
    }

    @Override
    public byte[] transform(
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {

        // Other classes are still processed normally by the JVM, just not logged.
        if (!"DemoTarget".equals(className)) {
            return null;
        }

        System.out.println("CALL " + id);

        if (fail) {
            // Intentional failure to show T3 is still invoked.
            throw new IllegalStateException("demo transformer failure");
        }

        // T1 and T3 do not change the bytecode.
        return null;
    }
}
```

Both classes are in the `ChainAgent.java` file: `ChainAgent` is `public`, and `DemoTransformer` has package-private access. Both compile into `ChainAgent.class` and `DemoTransformer.class`, making it convenient to package into a JAR with a command that does not rely on wildcards.

This code only logs when `className` equals `DemoTarget`, so it does not print a flood of callbacks from the JDK or other classes. T1 and T3 return `null`; T2 throws an unchecked exception. **No callback modifies `classfileBuffer` or returns replacement bytes**.

### 6.2. `Demo.java`: the application must continue running

```java
public final class Demo {
    public static void main(String[] args) throws Exception {
        System.out.println("APP_BEFORE");

        // Use the string class name to explicitly trigger class loading.
        Class<?> type = Class.forName("DemoTarget");
        Object result = type.getMethod("value").invoke(null);

        System.out.println("APP_RESULT=" + result);
    }
}

final class DemoTarget {
    public static int value() {
        return 7;
    }
}
```

`DemoTarget` has a static method returning `7`, independent of the agent. `Class.forName` places the loading point of `DemoTarget` after the `APP_BEFORE` line in this experiment. The application code still works because T2's exception **is not propagated as-is by the JVM into an exception from `Class.forName`**.

### 6.3. `agent.mf`: manifest for the startup Java agent

```text
Manifest-Version: 1.0
Premain-Class: ChainAgent

```

Make sure the manifest file ends with a blank line. The example uses a **startup agent** via `-javaagent`, so it only needs `Premain-Class` and `premain`; `Agent-Class` or `agentmain` for dynamic attach are not needed.

`Can-Retransform-Classes` is not required because the three transformers only use `addTransformer(t)`, which is equivalent to registering with `canRetransform=false`.

### 6.4. Compile and run commands

In the directory containing the three files, using JDK 17 or later:

```shell
javac ChainAgent.java Demo.java
jar cfm chain-agent.jar agent.mf ChainAgent.class DemoTransformer.class
java -javaagent:chain-agent.jar -cp . Demo
```

`javac` also produces `Demo.class` and `DemoTarget.class`; `-cp .` allows the JVM to find the sample program and target class. The agent JAR only needs the two classes `ChainAgent` and `DemoTransformer`; `DemoTarget` is an **application** class, not a class to put into the agent JAR.

**Expected stdout on HotSpot JDK 17/21 in the experiment:**

```text
AGENT_READY
APP_BEFORE
CALL T1_NULL
CALL T2_THROW
CALL T3_NULL
APP_RESULT=7
```

The output illustrates three points:

1. T1 returns `null`, yet T2 is still called.
2. T2 throws `IllegalStateException`, yet T3 **is still called**.
3. `DemoTarget.value()` still returns `7` because there were no replacement bytes, and the JVM could still load the class normally.

**Observation note:** the example describes stdout explicitly printed by the program. Other JVMs/IDEs/agents may add diagnostics or log to stderr; do not take the absence of a stack trace on the console as proof that a transformer did not fail. If there are external agents or an environment that alters how classes are loaded, actual logs may show additional differences.

### 6.5. Control experiment A — removing the throwing transformer

Edit only `premain` to remove the line:

```java
inst.addTransformer(new DemoTransformer("T2_THROW", true));
```

Then recompile, repackage the JAR, and run a **new JVM**:

```shell
javac ChainAgent.java Demo.java
jar cfm chain-agent.jar agent.mf ChainAgent.class DemoTransformer.class
java -javaagent:chain-agent.jar -cp . Demo
```

Expected stdout:

```text
AGENT_READY
APP_BEFORE
CALL T1_NULL
CALL T3_NULL
APP_RESULT=7
```

Comparing the two shows: with or without T2's internal error, the application still receives the result `7`. This **does not prove that all transformer errors are harmless**: if transformer code accidentally mutates the buffer, produces an invalid class file, performs I/O that blocks class loading, or causes unintended side effects, the outcome will be different.

### 6.6. Control experiment B — replacing the exception with `null`

To keep T2's name but not throw, use:

```java
inst.addTransformer(new DemoTransformer("T2_THROW", false));
```

After recompiling/repackaging/running a new JVM, stdout still has three `CALL` lines; since `fail=false`, T2 returns `null`. The result of `DemoTarget.value()` is still `7`.

This experiment illustrates the equivalence **on the bytecode pipeline** between `throw` and `return null`, but it does not mean the two branches are identical in terms of **logging, metrics, performance**, or diagnosability.

## 7. Real-world scenario: what if an earlier transformer already modified the bytes?

In the runnable example, none of the three transformers return new bytecode. In a real agent, the chain might look like:

```text
Input class bytes: B0

Transformer A (tracing):
  B0 -> B1
  // B1 is valid class bytes, with probes added.

Transformer B (metrics):
  receives B1
  throws IllegalStateException
  // B produces no replacement output.

Transformer C (security checks):
  receives B1, not B0
  B1 -> B2
  // B2 is valid class bytes after step C.

JVM:
  attempts to verify and apply B2.
```

Points worth noting:

- **No rollback of earlier steps:** B failing does not automatically undo A's tracing.
- **No skipping of later steps:** C can still run and can continue transforming.
- **No "metrics" present:** B produced no output, so B's own effect is not included in the final bytes.
- **B2 is not guaranteed to be valid:** A and C may inject incompatible code. The JVM only accepts the result if it satisfies class file and application constraints.
- **Do not call this a stage-by-stage transaction:** the final class definition/redefinition/retransformation is handled according to the JVM contract, not by each transformer committing part of a class. "Keeping earlier changes" here means **keeping the bytes flowing through the pipeline**, not that a partial class definition has been installed in the JVM.

An agent architecture that needs features A, B, and C to **depend on one another** should not simply stack three transformers and assume every part is always applied. It should prepare valid bytecode, detect failures at each step, and only report the feature as active upon final verification.

## 8. Registering multiple transformers: how to read logs and avoid misunderstandings

### 8.1. Ordered within the same group, not across all groups

All three transformers in the experiment used `false`, so callback order matched registration order. However, if you interleave `true` registrations and the JVM supports it, callback order must follow the **four groups** of `ClassFileTransformer`. Do not design an "A then B" test if A and B belong to different capability groups.

When you need to observe ordering, log at least:

```text
event=transform
target=com/example/OrderService
loader=<identity of defining loader>
phase=LOAD | REDEFINE_OR_RETRANSFORM
transformer=metrics-v2
retransformCapable=false
decision=SKIP | OUTPUT | EXCEPTION
reason=CLASS_NOT_TARGETED | TRANSFORM_FAILED | ...
```

This is an **illustrative** schema. Not every transformer is required to have these exact keys. Avoid printing data from method arguments or class bytes without a valid reason and security policy.

### 8.2. `removeTransformer` does not cancel an in-flight callback

`Instrumentation.removeTransformer(t)` unregisters the transformer for future class definitions, but the API warns that callbacks may still arrive **after removal** due to multithreaded class loading. A disabled transformer must handle races/synchronization and protect its internal state, rather than assuming no thread is still executing `transform`.

If you register **the same instance** multiple times, the API allows it but strongly discourages it; `removeTransformer` only removes the most recent matching registration. Create separate transformer instances and manage their lifecycles clearly so errors are attributed to the right callback.

### 8.3. Thread safety and recursive class loading

The JVM can define multiple classes concurrently. A transformer must not assume callbacks are single-threaded. A transformer that uses mutable counters, a map keyed by className, or an output cache must be thread-safe by design.

Complex operations inside a callback (logging that triggers class loading, reflective scans, opening network files, uncontrolled locking) can increase latency, cause reentrancy, or deadlock while the system is in the middle of class loading. Filter targets as early as possible, minimize I/O, and be careful with the agent's dependencies. The JVM excludes certain classes needed to execute a transformer per the `addTransformer` contract, but you must not assume callbacks are unconditionally safe from all class loading issues.

## 9. Diagnosing when a transformer "has no effect"

| Symptom | Possible cause | How to check |
|---|---|---|
| No logs at all from T1 | Class was not defined after registration; wrong name/loader filter; transformer was not added | Log registration, class internal name, defining loader, startup order |
| T1 logs and returns `null`, T2 still logs | Normal behavior | This is a callback chain; `null` does not stop the pipeline |
| T2 throws an exception, T3 still logs | Behavior defined by the API | Place controlled logging **before** throwing; do not rely on stack traces in the application |
| Class loads successfully even though T2 threw | The JVM treated T2's error as no transformation at that step | Check which bytes the JVM received from earlier/later steps |
| Instrumentation is absent even with no exception in the app | Transformer filtered out the target, returned `null`, error was ignored by the JVM, output was unchanged | Count target/matched/transformed/errors; verify the actual probe |
| Class fails to load even though only T2 threw an exception | There may also be class file errors, verifier errors, or other transformers | Isolate each transformer, verify final bytes, inspect JVM-level exceptions |
| `retransformClasses` is called but T1 does not run again | T1 was registered with `canRetransform=false` | Check capability/manifest, check transformer group, distinguish "reused output" |
| T3 receives bytes that look different from the build output | An earlier transformer already replaced bytes; redefine/retransform has different base bytes | Capture checksum/hash at each stage when safe to do so; compare order |
| Transformer was removed but occasionally still gets callbacks | Race from multithreaded class loading | Design state, shutdown, and metrics to tolerate late callbacks |
| Log says "success" after `return null` | Only indicates the callback completed, not that new bytes were produced | Distinguish `VISITED`, `UNCHANGED`, `MODIFIED`, `FAILED` and verify the feature |

### A minimal useful set of counters

```text
transform_calls_total{transformer,phase}
transform_decisions_total{transformer,decision="UNCHANGED"}
transform_decisions_total{transformer,decision="MODIFIED"}
transform_decisions_total{transformer,decision="FAILED"}
transform_class_install_total{status="SUCCESS|ERROR"}      [if measurable]
feature_probe_verified_total{feature,class_group}          [if measurable]
```

These are suggested metric names, not built-in APIs. In particular, do not use the callback count as the number of instrumented classes: the same class can be retransformed multiple times, a transformer can make no changes or throw errors, and the same binary name can appear across multiple defining loaders.

### Why should exceptions be recorded inside the transformer?

Because the JVM can ignore exceptions from `transform` by contract, a test that only writes:

```java
Class.forName("com.example.Service");
// No exception from Class.forName -> assume probe is OK? WRONG.
```

will miss internal failures. Record the status of each transformation in the agent or an agent-controlled error-tracking system, and then verify the postcondition that "the probe is actually active". Do not spam `System.out.println` in every production callback; console printing in the example is only for learning the behavior.

## 10. Two practical handling patterns

### 10.1. Transformer proactively skips out-of-scope classes

```java
if (className == null || !className.startsWith("com/example/")) {
    return null;
}
```

This is an **illustrative snippet inside `transform`**, not a standalone program. The `null` branch is the normal "do not modify" decision and should not be logged at `ERROR` level for thousands of out-of-scope classes.

### 10.2. Transformer catches bytecode modification failures

```java
try {
    // mutate(input) is a function that produces a validated NEW ARRAY.
    return mutate(classfileBuffer);
} catch (IllegalClassFormatException e) {
    recordFailure(className, "INVALID_CLASS_INPUT", e);
    return null;
} catch (RuntimeException e) {
    recordFailure(className, "INTERNAL_TRANSFORM_FAILURE", e);
    return null;
}
```

This is an **illustrative pattern, not independently compilable** without implementing `mutate` and `recordFailure`. The goal is to show that after an error you can **preserve the bytes of this stage**, allow the pipeline to continue, yet record the failure. If the feature is mandatory, the orchestration layer must inspect the `FAILED` status and act according to the defined policy, rather than treating the JVM's survival as business success.

**Additional safety rules:**

- Do not modify `classfileBuffer` directly even if you later return `null`. Violating this makes the behavior of other transformers and the JVM unpredictable.
- A transformation may be valid on initial load but invalid on redefine/retransform due to structural change restrictions. Design output appropriate for each phase.
- When catching errors, do not trigger unbounded recursive logging/reflection during class loading; keep error recording compact and bounded.
- Do not use a broad `catch (Throwable)` to "swallow everything" without considering `OutOfMemoryError`, `ThreadDeath`, or other fatal errors.

## 11. Self-check exercises

1. **T1 returns `null`, T2 returns a valid new byte array. Can the final class change?** Yes. T1 simply made no change at its step; T2 can still transform it.
2. **T1 returns new bytes `B1`, T2 throws an exception, T3 returns `null`. What does T3 receive?** T3 receives `B1` (the current bytes before T2), not an automatic rollback to `B0`.
3. **If `transform` throws `IllegalClassFormatException`, does the JVM always throw `ClassFormatError` to the application?** No. At the transform layer, the exception has the same effect as `null` and the pipeline continues; any final error depends on the bytes and JVM contract.
4. **If every transformer returns `null`, is the class guaranteed to load successfully?** No. The original bytes may be invalid, or class loading may fail for other reasons.
5. **Why should you not return `new byte[0]` to indicate "no change"?** It is an invalid replacement byte array, different from `null`; it can cause the JVM to reject the class file.
6. **Does a retransformation-incapable transformer run again when `retransformClasses` is called?** No. Per the API, the JVM reapplies the previous transformation result of the incapable group without invoking the callback again.
7. **A is registered with `true`, then B is registered with `false`. When a new class loads, which one may be called first?** By group order, B (`false`) runs before A (`true`), even though it was added later.
8. **T2 throws an error, yet the class runs normally. Should the agent report that all transformers "succeeded"?** No. T2 failed internally; only report final class load success when there is evidence, and record T2's failure separately.
9. **Can the callback count be treated as the number of instrumented classes?** No. Callbacks can return `null`/throw, a single class can pass through multiple times, and multiple class loaders can have different classes.
10. **A security goal is mandatory, yet the transformer throws an exception. Is it safe to rely on that exception to block class loading?** No. You need verification and a fail-closed strategy at a layer with orchestration control; do not rely on throwing from `transform`.
11. **Is `classBeingRedefined != null` enough to tell whether a redefine or a retransform is happening?** No. You need additional context about the operation controlled by the agent.
12. **A transformer returns new bytes, but the JVM rejects them due to disallowed structural changes. Can you conclude `transform` failed with an exception?** Not necessarily. The callback may have returned successfully, while the verification/application step **after the callback** failed.

## 12. Official references

- [Java SE 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): `return null` rules, throwing exceptions, input/output chaining, four-group ordering, callbacks in Java 9+.
- [Java SE 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `removeTransformer`, `retransformClasses`, `redefineClasses`, capabilities, and errors when the JVM applies class bytes.
- [Java SE 21 — IllegalClassFormatException](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/IllegalClassFormatException.html): checked exception declared in `transform`.
- [Java SE 21 — java.lang.instrument package specification](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): Java agent entry points and manifest.

**Summary:** `return null` means **no modification at this step**. An uncaught `throw` has **the same effect on the bytecode pipeline**: skip this step's output, continue invoking subsequent transformers, and attempt to apply the final bytes. It does **not** automatically roll back earlier transformations, does **not** automatically abort class loading, and does **not** guarantee that the application is safe or meets instrumentation goals. To detect real failures, instrument each stage and verify the final effect.
