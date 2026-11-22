# `addTransformer` with `canRetransform = false` or `true`: Understanding the Bytecode Transformation Chain

In Java Instrumentation, an agent registers a `ClassFileTransformer` so that the JVM allows observing or modifying a class's bytes when the **class is defined, redefined, or retransformed**. The second parameter of `Instrumentation.addTransformer(transformer, canRetransform)` determines whether that transformer is **invoked again during retransformations**.

Key takeaways of this lesson:

- `canRetransform = false`: the transformer still runs when a class is **loaded** or **redefined**. On `retransformClasses(...)`, the JVM **does not invoke this transformer again**, and instead **reuses the transformation result from the previous load/redefine**.
- `canRetransform = true`: the transformer runs when a class is **loaded**, **redefined**, and is **invoked again** when a class is **retransformed**.
- A `true` value is only valid if the agent/JVM configuration supports retransformation; **`addTransformer(..., true)` does not grant the capability by itself**.
- Both types belong to **a single transformation chain**, with a clear group ordering. A `false` value **does not mean "cannot instrument"**.

After this lesson, you will be able to choose the right `addTransformer` overload for your purpose, predict which transformer gets invoked again, read the input/output of the transformation chain, and verify the behavior with a Java 17+ program.

## 1. Two Overloads of `Instrumentation.addTransformer`

The API belongs to the `java.instrument` module:

~~~java
void addTransformer(ClassFileTransformer transformer);

void addTransformer(
        ClassFileTransformer transformer,
        boolean canRetransform);
~~~

The single-parameter overload **is equivalent to**:

~~~java
inst.addTransformer(transformer, false);
~~~

Parameters:

| Parameter | Meaning |
|---|---|
| `transformer` | An object implementing `java.lang.instrument.ClassFileTransformer`; the JVM calls its `transform(...)` method |
| `canRetransform` | Whether the transformer belongs to the **retransformation capable** group |

`addTransformer` **registers a callback** into the JVM's instrumentation mechanism. It is not an immediate call to transform a specific class at registration time. Classes processed by the JVM afterward will pass through the chain according to the conditions of each operation; classes already loaded before registration **are not automatically reprocessed**.

Two transformer groups:

- **Retransformation incapable**: registered with `false` or the single-parameter overload.
- **Retransformation capable**: registered with `true`.

The group name *incapable* can be misleading: it means **not invoked again on retransform**, not that it cannot perform a bytecode transformation at load/redefine time.

## 2. When Is `transform(...)` Called?

| JVM Operation | `addTransformer(t, false)` | `addTransformer(t, true)` |
|---|---|---|
| Defining a new class (`ClassLoader.defineClass` or equivalent) | **Calls `transform`** | **Calls `transform`** |
| `Instrumentation.redefineClasses(...)` | **Calls `transform`** | **Calls `transform`** |
| `Instrumentation.retransformClasses(...)` | **Not called again; reuses the effect of the most recent load/redefine** | **Calls `transform` again** |
| Normal method execution, with no class definition/redefinition/retransformation | No | No |

Transformers do not necessarily receive **every** auxiliary class: the `Instrumentation.addTransformer` specification has an exception for definitions of classes that a registered transformer depends on, to avoid initialization circularity issues. In practice, you should filter by `className` and avoid using loggers or complex dependencies inside `transform`.

### Distinguishing Redefinition and Retransformation

- **Redefinition**: the agent supplies **a new byte array** for an already-loaded class using `redefineClasses(new ClassDefinition(clazz, bytes))`. Both `false` and `true` transformers are called in this process.
- **Retransformation**: the agent calls `retransformClasses(clazz)` so the JVM starts again from the corresponding **initial class file bytes**, replays the effects of `false` transformers, and then calls `true` transformers to compute the new result. *Initial bytes* may be the latest definition from `redefineClasses`, and are not required to be byte-for-byte identical to the previously passed version (for example, the constant pool layout may change).

`canRetransform` is a property of the **transformer registration**, not a permanent label attached to a class. The same class may have passed through multiple transformers from both groups.

## 3. `false`: Callback Does Not Run Again, but Previous Effects Are Reapplied

Suppose a class initially has bytecode `B0` and the agent registers:

~~~java
inst.addTransformer(transformerA, false);
~~~

On the first load, `transformerA` receives `B0` and returns bytes `B1`. Later, when the class is retransformed, the JVM **does not call `transformerA.transform(...)` again**. Instead, the JVM reuses the previous transformation effect, equivalent to passing `B1` to the next step in the chain.

~~~text
Initial load:
B0 ── A(false).transform(...) ──> B1

Subsequent retransform:
B0 ── [reapply saved A result, DO NOT call A] ──> B1
~~~

This preserves the effect of a `false` transformer across retransformations, even when that transformer is not triggered again. You must **not** interpret `false` as "losing all of A's transformations after retransform".

If the transformer returns `null` at load time, its step **does not modify the bytes**. On retransform, that "unchanged" result is treated as the transformer's previous effect.

A false transformer can be a tool for applying **fixed changes at initial load**. Not calling it again avoids repeated computation or side effects during retransformations initiated by other agents.

## 4. `true`: Callback Runs Again During Retransformation

Suppose the agent also registers:

~~~java
inst.addTransformer(transformerB, true);
~~~

At load time:

~~~text
B0 ── A(false) ──> B1 ── B(true) ──> B2
~~~

When `retransformClasses(Target.class)` is called:

~~~text
B0 ── [reapply saved A result] ──> B1
                                    │
                                    └── B(true).transform(...) ──> B3
~~~

`B(true)` **receives input that already includes A's effect** and can return `B3` different from `B2`, for example because B's instrumentation configuration has changed. This difference is what makes `true` suitable for transformers that need to reapply rules according to a new configuration.

However, `true` **does not cause the JVM to invoke the transformer again at arbitrary times**. There must be an **actual retransformation request** (`retransformClasses`) or a class load/redefine operation. Registering `true` and then continuing to call methods normally will **not** trigger a new round of callbacks.

`true` also **does not** mean the transformer is allowed to alter any class structure arbitrarily. The returned bytes must still be a valid class file and comply with redefinition/retransformation restrictions (such as not arbitrarily adding or removing methods or fields).

## 5. JVM Capability: Condition for Registering `true`

To use retransformation, an agent typically declares it in the **main section** of the manifest of the JAR loaded as the agent:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.TraceAgent
Can-Retransform-Classes: true

~~~

`Can-Retransform-Classes` is a capability request:

1. The attribute is optional, **defaulting to `false`** when omitted.
2. `true` requests retransformation, but only succeeds when the JVM **supports and grants that capability**.
3. `Instrumentation.isRetransformClassesSupported()` returns whether it is supported in the current JVM configuration; multiple calls on the same JVM return the same result.
4. If the method above returns `false`, `addTransformer(t, true)` **throws `UnsupportedOperationException`**. Registering `addTransformer(t, false)` is still allowed and can be useful for load/redefine.
5. Do not confuse `Can-Retransform-Classes` with `Can-Redefine-Classes`. The two attributes grant **two separate capabilities**.

To avoid errors:

~~~java
if (inst.isRetransformClassesSupported()) {
    inst.addTransformer(transformer, true);
} else {
    inst.addTransformer(transformer, false);
}
~~~

This is an **illustrative snippet** placed inside an agent callback where `Instrumentation inst` and `ClassFileTransformer transformer` are already available. The `else` branch does not turn a false transformer into one that can participate in retransform callbacks; it only allows observing eligible load/redefine events.

`isRetransformClassesSupported()` checks the **JVM capability**, not the modifiability of a specific class. Before requesting `retransformClasses(Target.class)`, you should also check `inst.isModifiableClass(Target.class)`. Even when both necessary conditions are true, that still does not guarantee the new bytes are valid.

## 6. Execution Order with Multiple Transformers

The JVM does **not** simply invoke every transformer in global registration order. `ClassFileTransformer` specifies a **four-group** ordering:

1. **Retransformation-incapable Java transformers (`false`)**.
2. **Retransformation-incapable native transformers** (via JVMTI `ClassFileLoadHook`).
3. **Retransformation-capable Java transformers (`true`)**.
4. **Retransformation-capable native transformers**.

**Within each group**, transformers are called in the order they were registered. A `true` transformer registered **before** a `false` transformer still runs **after** the false group in the chain.

For example:

~~~java
inst.addTransformer(transformerB, true);   // registered first
inst.addTransformer(transformerA, false);  // registered later
~~~

During a class load/redefine operation, considering these two Java transformers alone, the order is still **A(false) → B(true)**, not B then A. If A2(false) is added as well, the order between A(false) and A2(false) is then determined by their registration order.

For a Java-only chain:

~~~text
Original bytes
   │
   ▼
A1(false) → A2(false) → B1(true) → B2(true)
   │                                 │
   └──── each step receives previous step's bytes ────┘
                                      │
                                      ▼
                             Bytes for JVM verification
~~~

If native transformers are present, they are inserted in their exact group 2 and group 4 positions as shown above. During retransformation, the `false` group **reuses its saved effects without invoking callbacks**, whereas the `true` group actually runs its callbacks.

**Every transformer must be compatible with the output of the transformer before it.** Order matters greatly if A modifies method code and B adds logging to the modified code. If B assumes the input bytes are always the original ones, it can produce invalid bytecode or accidentally overwrite A's effects.

## 7. `ClassFileTransformer.transform`: Input, Output, and Callback Info

With Java 17+, you can override the version with the `Module` parameter:

~~~java
@Override
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain protectionDomain,
        byte[] classfileBuffer) {
    // Read classfileBuffer; return null if no modification is needed.
    return null;
}
~~~

This is an **illustrative method body** inside a class implementing `ClassFileTransformer`, not a standalone Java program. An older overloaded version without the `Module` parameter also exists for compatibility with pre-Java 9 implementations.

Parameter meanings:

| Parameter | Key Meaning to Remember |
|---|---|
| `module` | The module of the class being transformed |
| `loader` | The defining class loader of the class, may be `null` for the bootstrap loader |
| `className` | Internal JVM name such as `demo/Work`, **not** `demo.Work`; in some cases may be `null` |
| `classBeingRedefined` | `null` on a new definition; **non-null** when the callback is triggered by **redefine or retransform**. This field alone cannot distinguish the latter two operations |
| `protectionDomain` | Protection domain associated with the class |
| `classfileBuffer` | Input bytes for the **current step in the chain**, which may already include the effects of preceding transformers |

Return convention:

- `return null`: **no byte modifications**; the next step sees the current input.
- `return newBytes`: replaces the input bytes with a **new byte array** containing a valid class file for the next step.
- **Do not modify `classfileBuffer` directly**. If transformation is needed, create a new array (typically using ASM, Byte Buddy, or verified class file manipulation).

A transformer may `throw IllegalClassFormatException` when it detects an invalid class file structure. Per the API contract, if `transform` throws an unhandled exception, the JVM still proceeds to call subsequent transformers and the load/redefine/retransform is still attempted; the effect of the throwing step is equivalent to `return null`. Therefore, **throwing an exception in a transformer is not a reliable mechanism to abort the entire class load**. An agent should log errors appropriately and avoid breaking the bootstrap process.

Typically, you should write a clear filter:

~~~java
if (!"demo/Work".equals(className)) {
    return null;
}
~~~

This comparison is also safe when `className == null`. You should not log or transform every JVM class when first learning; the transformer may be invoked while the runtime is loading classes that the agent itself depends on.

## 8. Java 17+ Example: Observing `false` and `true` on One Class

To observe actual callbacks and ordering without needing the ASM library, we create two transformers that **only print logs and return `null`**. They do not modify the class file. This example clarifies **when each callback runs**, while the `B0/B1/B2` diagrams above illustrate the byte chain when transformers actually modify bytecode.

Directory structure:

~~~text
transformer-lab/
├── MANIFEST.MF
├── src/
│   └── demo/
│       ├── TraceAgent.java
│       ├── Work.java
│       └── Demo.java
└── out/               created during compilation
~~~

### 8.1. Agent: `src/demo/TraceAgent.java`

~~~java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class TraceAgent {
    private static volatile Instrumentation current;

    public static void premain(String options, Instrumentation inst) {
        current = inst;
        boolean supported = inst.isRetransformClassesSupported();
        System.out.println("[premain] supported=" + supported);

        inst.addTransformer(new LogTransformer("A(false)"), false);
        if (supported) {
            inst.addTransformer(new LogTransformer("B(true)"), true);
        }
    }

    public static Instrumentation instrumentation() {
        if (current == null) {
            throw new IllegalStateException("Start JVM with -javaagent");
        }
        return current;
    }

    private static final class LogTransformer
            implements ClassFileTransformer {
        private final String name;

        private LogTransformer(String name) {
            this.name = name;
        }

        @Override
        public byte[] transform(
                Module module,
                ClassLoader loader,
                String className,
                Class<?> classBeingRedefined,
                ProtectionDomain domain,
                byte[] classfileBuffer) {
            if (!"demo/Work".equals(className)) {
                return null;
            }

            String phase = classBeingRedefined == null
                    ? "load" : "revisit";
            System.out.println("[transform] " + name + " " + phase);
            return null;
        }
    }
}
~~~

This class **always** registers A in the `false` group and registers B in the `true` group **only if the JVM supports retransformation**. `phase = revisit` means the callback is reprocessing an existing class, **without distinguishing redefine from retransform by itself**; in this experiment, only `retransformClasses` is called, so we know this is a retransformation from the call in `Demo`.

`return null` ensures the example only measures callbacks without altering the class's runtime behavior.

### 8.2. Target Class: `src/demo/Work.java`

~~~java
package demo;

public final class Work {
    public static int answer() {
        return 7;
    }
}
~~~

### 8.3. Application: `src/demo/Demo.java`

~~~java
package demo;

import java.lang.instrument.Instrumentation;

public final class Demo {
    public static void main(String[] args) throws Exception {
        System.out.println("[main] loading demo.Work");
        Class<?> target = Class.forName("demo.Work");

        Object answer = target.getMethod("answer").invoke(null);
        System.out.println("[main] answer=" + answer);

        Instrumentation inst = TraceAgent.instrumentation();
        if (!inst.isRetransformClassesSupported()
                || !inst.isModifiableClass(target)) {
            System.out.println("[main] skip retransform");
            return;
        }

        System.out.println("[main] request retransform");
        inst.retransformClasses(target);

        Object after = target.getMethod("answer").invoke(null);
        System.out.println("[main] answer=" + after);
    }
}
~~~

`Class.forName("demo.Work")` explicitly loads the class after the agent has registered the transformers. Reflection (`getMethod` and `invoke`) is only used to avoid referencing `Work.class` before the moment we want to load it; both calls return the same result because the transformers only log.

### 8.4. Manifest and Run Commands

Create `MANIFEST.MF`:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.TraceAgent
Can-Retransform-Classes: true

~~~

Keep the **trailing blank line** in the manifest. Run in the `transformer-lab` directory.

On Bash/Git Bash:

~~~bash
mkdir -p out
~~~

On PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
~~~

Compile and package using **JDK 17 or newer**:

~~~bash
javac --release 17 -d out src/demo/TraceAgent.java src/demo/Work.java src/demo/Demo.java
jar --create --file trace.jar --manifest MANIFEST.MF -C out .
java -javaagent:trace.jar -cp trace.jar demo.Demo
~~~

`--release 17` produces Java 17-compatible class files; the program uses `java.instrument` and needs no extra dependencies. Forward slashes `/` in paths are accepted by the JDK on Windows.

On a typical JVM (e.g., HotSpot supporting retransformation and modifiable classes), **expected output**:

~~~text
[premain] supported=true
[main] loading demo.Work
[transform] A(false) load
[transform] B(true) load
[main] answer=7
[main] request retransform
[transform] B(true) revisit
[main] answer=7
~~~

**Reading the evidence line by line:**

1. `[premain] supported=true`: the JVM grants the capability when the agent declares `Can-Retransform-Classes: true`.
2. A(false) and B(true) are **both** called when loading `demo.Work`.
3. `Demo` requests `inst.retransformClasses(target)` after the class has been loaded.
4. During retransformation, only `[transform] B(true) revisit` appears; **there is no second A(false) line**. The JVM still reuses A's effect at the byte level.
5. `answer=7` before and after because both transformers **return `null`** without modifying the method.

If the JVM reports `supported=false`, the agent only registers A(false); after loading and printing `[main] answer=7`, the program will print `[main] skip retransform` and exit. The result depends on the JVM/configuration; you should not try to force `false` to `true` in the log.

If `isModifiableClass(target)` returns `false`, `Demo` also skips the retransform operation even when the overall capability is `true`. This is why **you check JVM-wide capability and target-class modifiability separately**.

## 9. Control Case: What Happens Without the Capability?

If you replace the manifest with:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.TraceAgent
Can-Retransform-Classes: false

~~~

On a JVM that does not grant retransformation, the output prints `supported=false`; the example still registers A(false) and processes the load of `demo.Work`. However, it does not register B(true) and does not call `retransformClasses` because the guard branch in the code checks the capability.

If you remove the guard and call directly:

~~~java
inst.addTransformer(new LogTransformer("B(true)"), true);
~~~

this snippet is an **illustration inside `TraceAgent`**. When `isRetransformClassesSupported() == false`, `addTransformer(..., true)` **throws `UnsupportedOperationException`** per the API. The example includes the guard so it can run on unsupported JVMs while still observing A(false). `LogTransformer` here is a private inner class of `TraceAgent`; do not use it as a standalone class from another file.

**Summary of the two levels of `true`:**

- `Can-Retransform-Classes: true` in the manifest: **the agent requests the capability**.
- `isRetransformClassesSupported() == true`: **the JVM confirms the capability is available**.
- `addTransformer(t, true)`: **registers the transformer in the capable group**.
- `retransformClasses(clazz)`: **explicitly requests reprocessing of an already-loaded class**.

Without any of the appropriate steps, the claim "having `true` makes classes automatically re-transform themselves" is false.

## 10. Real-World Scenario: Two Agents, Two Transformers

Suppose agent **A** adds method invocation counting code at class load time using a `false` transformer; agent **B** wants to change logging points when monitoring configuration changes, so it registers a `true` transformer.

~~~text
When defining the class:
Bytes B0 → A(false) produces B1 → B(true) produces B2 → JVM defines the class

When agent B requests retransform:
Initial bytes B0
    → reuse A's effect on bytes, without calling A
    → B(true) runs with bytes already transformed by A, producing B3
    → JVM verifies and applies the new definition
~~~

Suppose B initially enables logging at `INFO` level, then switches to `DEBUG` and calls `retransformClasses`. B can recompute bytes with the new configuration, while A's effect is preserved. This is a conceptual example, **not executable bytecode**; inserting probes into methods requires ASM/Byte Buddy and proper handling of stack map frames and retransform restrictions.

If a **new `false` transformer** is registered *after a class is already loaded*, calling retransform on that class **will not cause this new false callback to run**. To apply a transformation from that transformer, it must be applied when an eligible class is defined/redefined; do not assume `retransformClasses` will invoke the false group again.

If both A and B modify code, do not assume B always sees the original bytes. Following the chain, B receives the bytes already processed by A. Use an up-to-date bytecode library, handle errors, and test on specific classes to avoid overwriting other agents' instrumentation.

## 11. Managing Registrations and Common Pitfalls

### Does `removeTransformer` Revert the Class?

~~~java
boolean removed = inst.removeTransformer(transformer);
~~~

This call **removes the registration** of the transformer object (if the same instance was added multiple times, it removes the most recently added matching registration). It **does not automatically restore the bytes of already-loaded classes**. If you want to change the state of existing classes, you need an appropriate redefine/retransform mechanism and must ensure the final result is valid. Because class loading happens concurrently, a transformer may still receive some callbacks **after** its registration is removed; therefore, write callbacks to handle late invocations safely.

Do not register the same instance repeatedly multiple times: the API permits it, but the specification advises against it, as it easily causes unintended multiple transformations and confusing removal order.

### Common Mistakes

| Symptom | Possible Cause | How to Check |
|---|---|---|
| `addTransformer(t, true)` throws `UnsupportedOperationException` | Agent did not request or JVM did not grant retransformation | Check the **agent JAR** manifest, check `isRetransformClassesSupported()` |
| A(false) disappears from logs during `retransformClasses` | This is expected behavior: A's result is reapplied **without calling the callback** | Compare load-time and retransform logs; do not treat missing logs as lost instrumentation |
| `true` is registered but existing classes do not change | `retransformClasses` has not been called or the class is not modifiable | Call the API explicitly, check guards and results |
| Newly registered false transformer does not affect already-loaded classes | False transformers are not called during retransformation | Register before the relevant load/redefine |
| Retransform call throws `UnmodifiableClassException` | Target cannot be modified in this JVM | Check `isModifiableClass` and the class type |
| `ClassFormatError`, verification/linkage error | Transformer returned invalid or incompatible bytes | Inspect final bytes, stack frames, and schema changes |
| Class transformers run in an order contrary to registration expectation | **false/true group** ordering takes precedence over registration time | Group them first, then compare order **within each group** |
| Callback sees `className` as `demo/Work`, filter `demo.Work` does not match | Callback class names use **internal form** | Compare against `"demo/Work"` |
| B still sees bytes modified by A | Transformer bytecode is **chained** | Never assume each callback receives original bytes |
| `revisit` line appears but unclear whether redefine or retransform | `classBeingRedefined` does not distinguish the two cases | Check whether the caller invoked `redefineClasses` or `retransformClasses` |
| Callback throws an exception yet the class still loads | JVM continues the chain, treating the failed step's effect as `null` | Log inside the transformer; do not use throw as a "cancel" |
| After `removeTransformer`, the application still runs instrumented code | Removing a callback does not directly revert running classes | Determine an appropriate retransform/redefine recovery strategy |

In a real agent, avoid heavy side effects and I/O inside `transform`: callbacks may run while the JVM is loading core classes or when multiple threads request class loading. Filter classes early, keep transformers safe to run multiple times (*idempotent* when needed), and avoid creating dependencies on the very classes being instrumented.

## 12. Decision Checklist Before Writing an Agent

1. **Only need to transform when classes are loaded/redefined?** Registering `false` is enough. It has no retransform callback, yet its previous result is preserved across retransformation per the specification.
2. **Need to recompute a transformation for already-loaded classes when agent configuration changes?** Request `Can-Retransform-Classes: true`, check support, register a `true` transformer, and then call `retransformClasses` on modifiable classes.
3. **Have multiple transformers?** Design the order by false → true groups and by registration time within each group; remember native transformers also participate in the standard order.
4. **Does the transformer need to return bytes?** Do not modify `classfileBuffer` in place; use a new array containing a complete valid class file, and verify stack map frames and structural constraints when reprocessing already-loaded classes.
5. **Want to measure results?** Log the exact class name, registration type, and load/redefine/retransform timing, then compare against actual bytes/effects. Callback counts **do not directly reflect** how many times bytecode effects are reapplied.

## 13. Self-Check

1. **Which group does `inst.addTransformer(t)` belong to?** Equivalent to `inst.addTransformer(t, false)`.
2. **Is a `false` registration called when a class is first loaded?** Yes. It can modify bytecode at load time.
3. **A class was transformed by A(false), and the JVM calls `retransformClasses`: is A called again?** No. The JVM reuses A's transformation result from the previous load/redefine.
4. **B(true) is registered; when `retransformClasses` runs, is B called again?** Yes, if the request is accepted by the JVM.
5. **`addTransformer(B, true)` before `addTransformer(A, false)`—what is the load-time order of these two Java transformers?** A(false) then B(true) because group ordering takes precedence.
6. **`Can-Retransform-Classes: true` but `isRetransformClassesSupported() == false`—can a true transformer be registered?** No; `addTransformer(..., true)` throws `UnsupportedOperationException`.
7. **What should `transform` return if it does not want to change bytes?** `null`. Do not modify `classfileBuffer`.
8. **Does `classBeingRedefined != null` prove that `redefineClasses` is being called?** No; retransform also passes the existing `Class<?>`.
9. **Two transformers modify the same class: does the second callback receive the original bytes?** Not necessarily; it receives the output bytes from previous steps in the chain.
10. **If A is removed from registration, does the JVM immediately revert all instrumented classes?** No; removing a callback is not a class rollback operation.
11. **Why does the Java example keep `answer=7` both times?** Because A/B only log and `return null`, without changing the definition of `demo.Work`.

### Official References

- [Java SE 21 — `Instrumentation`: `addTransformer`, `isRetransformClassesSupported`, `retransformClasses`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html).
- [Java SE 21 — `ClassFileTransformer`: group ordering, input/output, callbacks, and error handling](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html).
- [Java SE 21 — `java.lang.instrument` package specification: agent JAR and `Can-Retransform-Classes`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html).
- [Java SE 21 — `UnmodifiableClassException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/UnmodifiableClassException.html).

**Key takeaway to remember:** `false` **has no retransform callback, yet its previous effects are reapplied**; `true` **has retransform callbacks** if the JVM/agent has the capability. When multiple transformers participate, **group ordering determines the byte chain**, while `retransformClasses` determines when an already-loaded class is actually reprocessed.