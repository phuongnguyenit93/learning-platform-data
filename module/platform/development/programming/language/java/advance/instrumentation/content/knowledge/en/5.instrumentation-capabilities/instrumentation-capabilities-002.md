# `Can-Retransform-Classes` and `isRetransformClassesSupported()` in Java Instrumentation

## 1. Problem: Can a class already loaded by the JVM still be instrumented?

In Java Instrumentation, `ClassFileTransformer` typically receives bytecode when a class **is about to be defined**. However, a Java agent might be attached late, or a profiler/tracer might want to change how an already-loaded class is observed. **Retransformation** is the mechanism for asking the JVM to re-run the bytecode transformation process for classes **currently loaded in the JVM** without restarting the process.

The two components in the title address two different layers:

- **`Can-Retransform-Classes: true`** is an attribute in the **agent JAR's main manifest**: the agent requests the retransform capability.
- **`Instrumentation.isRetransformClassesSupported()`** is a Java method that returns the capability **actually available in the current JVM configuration**. Merely enabling the manifest attribute does not guarantee the JVM will grant that capability.

Once the capability is available, the agent still needs to register a transformer in the right mode, select modifiable classes, and call `Instrumentation.retransformClasses(...)`. Do not conflate four separate questions: “Does the JVM support it?”, “Did the agent request it?”, “Will the transformer be invoked again?”, and “Can this specific class be modified?”.

This lesson applies to `java.lang.instrument` in Java 17+ and compatible runtimes; retransformation is an **optional** JVM capability, so results must be verified on the actual runtime environment.

## 2. Where is `Can-Retransform-Classes` declared?

When passing an agent JAR to the JVM at startup using `-javaagent`, the manifest can contain:

```text
Manifest-Version: 1.0
Premain-Class: demo.agent.RetransformAgent
Can-Retransform-Classes: true

```

- `Premain-Class` is the Java class containing `public static void premain(String, Instrumentation)` invoked by the launcher when using `-javaagent`.
- `Can-Retransform-Classes` is a **manifest** attribute, not an annotation or a `javac` option.
- The attribute must be in the **main section** of `META-INF/MANIFEST.MF` inside the **actual agent JAR loaded by the JVM**.
- A value of `true`, case-insensitive, indicates the request. If it is **absent**, set to `false`, or given any value other than `true`, it is treated as `false`.
- An agent launched via the attach mechanism uses `Agent-Class` instead of `Premain-Class` and likewise must declare the appropriate capability in the agent JAR.
- For an agent packaged inside an executable JAR using `Launcher-Agent-Class` and `agentmain`, check the capability of the agent launched by the JVM under that mechanism; the entry point name does not replace the `Can-Retransform-Classes` attribute.

The manifest only describes the agent's **request**. There is no official Java API to call `instrumentation.enableRetransform()` at runtime to fix a manifest that lacked the capability.

### Conditions for `isRetransformClassesSupported()` to return `true`

According to the `Instrumentation` contract:

```text
isRetransformClassesSupported() == true
             only when
   agent requests Can-Retransform-Classes: true
                    AND
     current JVM supports retransformation
```

On a given JVM, repeated calls to this method within the same JVM lifecycle **return the same result**. It is not a signal that varies depending on the class being inspected or the number of registered transformers.

| Agent manifest | Runtime/JVM | Expected result |
| --- | --- | --- |
| No `Can-Retransform-Classes` | Capable JVM | `false` per agent configuration |
| `Can-Retransform-Classes: false` | Capable JVM | `false` |
| `Can-Retransform-Classes: true` | JVM supports it, capability granted | `true` |
| `Can-Retransform-Classes: true` | JVM does not support this optional capability | `false` |

**Do not infer from the Java version number**: the API has existed since Java 6, yet the specification still treats retransformation as an optional capability. Log the method's return value during agent initialization.

## 3. Three levels to check before retransforming

### Level 1 — Does the JVM/agent have the capability?

```java
boolean supported = instrumentation.isRetransformClassesSupported();
```

If `false`, do not call `addTransformer(transformer, true)` or `retransformClasses(...)` as if they were guaranteed to succeed. `addTransformer(..., true)` throws `UnsupportedOperationException` when the JVM configuration does not allow retransformation.

### Level 2 — Is the transformer registered to be re-invoked?

```java
instrumentation.addTransformer(transformer, true);
```

The `true` argument here means **this specific transformer** is called again during retransformation. It does not mean “ask the JVM to retransform immediately” and does not replace the manifest.

Meanwhile:

```java
instrumentation.addTransformer(transformer);
instrumentation.addTransformer(transformer, false);
```

These two calls are equivalent regarding the transformer's retransform capability: **`canRetransform = false`**. Such a transformer can be called at initial class definition and during redefinition; during retransformation, the JVM **does not call** its `transform(...)` again. Even so, its previous transformation results are reapplied when constructing the new definition.

A transformer registered with `true` **does not automatically retransform already-loaded classes**. To process already-loaded classes, you still need to call `retransformClasses(...)` at the appropriate time.

### Level 3 — Is the target class modifiable?

```java
if (instrumentation.isRetransformClassesSupported()
        && instrumentation.isModifiableClass(MyService.class)) {
    instrumentation.retransformClasses(MyService.class);
}
```

`isModifiableClass(Class<?>)` is a **separate** question about the target class; this method does not depend on the value of `isRetransformClassesSupported()`. For example, primitive types (`int.class`) and array types (`String[].class`) are **not** modifiable.

Even when both checks return `true`, `retransformClasses` can still fail if a transformer produces an invalid class file or a change forbidden by the JVM. Therefore, an error-handling path is required.

## 4. What does `retransformClasses(...)` actually do?

API:

```java
void retransformClasses(Class<?>... classes)
        throws UnmodifiableClassException;
```

It asks the JVM to **rebuild the definition** of one or more loaded classes using the registered transformers. Multiple classes can be passed so the JVM processes a related set together; if the call throws an exception, the specification guarantees that **no class in the set is partially retransformed**.

Simplified diagram:

```text
Class already defined by the JVM
           |
           | instrumentation.retransformClasses(Foo.class)
           v
Original bytes from the most recent define/redefine
           |
           +-- Transformer canRetransform=false:
           |       reuse saved result, do NOT call transform again
           |
           +-- Transformer canRetransform=true:
           |       CALL transform again on the current bytes in the chain
           |
           v
JVM checks/verifies the new class file
           |
           +-- valid   -> install new definition
           |
           +-- invalid -> throw exception; do not install changes
```

Here, “original bytes” refers to the baseline from the last definition or redefinition; the JVM does not guarantee that this byte array **matches byte-for-byte** with the `.class` file on disk. Constant pool layout, entry ordering, or certain attributes may differ, while equivalent semantics must still hold.

### `true` and `false` transformers are not treated the same

Suppose when the class is loaded:

1. Transformer A registered with `canRetransform=false` transforms bytecode P into Q.
2. Transformer B registered with `canRetransform=true` transforms Q into R.

When `retransformClasses` is called:

1. The JVM starts with the appropriate baseline bytes.
2. A's previous transformation is reapplied **without calling A.transform()**.
3. The JVM **calls B.transform()** so B can produce a new result.
4. The JVM installs the definition only after the result satisfies constraints.

The general ordering rule also includes native/JVMTI transformers: the non-retransform-capable group (Java then native) is processed before the retransform-capable group (Java then native); within each group, registration order is respected. Be careful when multiple agents affect the same class.

### Does retransformation lose object state?

Normally, **instances are not recreated** and static fields are not reset merely because `retransformClasses` ran. The class initializer is not run again. For a method with an **active stack frame**, that frame continues executing the old bytecode; subsequent method invocations will use the new definition. This explains why instrumentation applied to a live application must consider timing and cross-thread behavior.

## 5. Runnable Java 17 example: enabling the capability, observing retransformation

The example below demonstrates three things:

1. The JVM reports support only when the agent JAR requests `Can-Retransform-Classes: true` and the runtime satisfies it.
2. A `canRetransform=true` transformer is invoked again with `classBeingRedefined != null` when retransforming a loaded class.
3. Returning `null` only observes, **without modifying bytecode**. The application method's return value before and after will be identical.

Files in the same directory:

```text
retransform-demo/
├── RetransformAgent.java
├── DemoTarget.java
├── DemoApp.java
└── manifest-enabled.mf
```

The classes are in the default package to keep compilation and packaging commands concise. In production, use a dedicated package for the agent.

### 5.1. File `RetransformAgent.java`

```java
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;

public final class RetransformAgent {
    private static volatile Instrumentation instrumentation;

    private RetransformAgent() {
    }

    public static void premain(String agentArgs, Instrumentation inst) {
        instrumentation = inst;

        boolean supported = inst.isRetransformClassesSupported();
        System.out.println("[agent] supported=" + supported);

        if (!supported) {
            return;
        }

        inst.addTransformer(
                (loader, className, classBeingRedefined,
                 protectionDomain, classfileBuffer) -> {
                    // Only print when DemoTarget is retransformed,
                    // not on the initial class load.
                    if ("DemoTarget".equals(className)
                            && classBeingRedefined != null) {
                        System.out.println(
                                "[transformer] retransform DemoTarget");
                    }
                    return null; // Do not modify bytecode.
                },
                true
        );
    }

    public static void retransform(Class<?> target) {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("Agent not initialized");
        }

        if (!inst.isRetransformClassesSupported()) {
            System.out.println("[agent] skipped: unsupported");
            return;
        }

        if (!inst.isModifiableClass(target)) {
            System.out.println("[agent] skipped: class not modifiable");
            return;
        }

        try {
            inst.retransformClasses(target);
            System.out.println("[agent] retransform request completed");
        } catch (UnmodifiableClassException
                 | UnsupportedOperationException ex) {
            System.out.println(
                    "[agent] failed: " + ex.getClass().getSimpleName());
        }
    }
}
```

**Why does this work on Java 17?** `ClassFileTransformer` is a functional interface; the five-argument lambda in `addTransformer` implements the `transform(ClassLoader, String, Class<?>, ProtectionDomain, byte[])` overload. No external bytecode library is needed because the transformer only observes and returns `null`.

`volatile` ensures visibility of the `Instrumentation` field if accessed across multiple threads later; in this demo the agent's `premain` runs before `main`, so no more complex synchronization is needed.

### 5.2. File `DemoTarget.java`

```java
final class DemoTarget {
    static String message() {
        return "hello";
    }
}
```

This class is the target. No transformer modifies its bytecode, so `message()` always returns `"hello"`.

### 5.3. File `DemoApp.java`

```java
public final class DemoApp {
    private DemoApp() {
    }

    public static void main(String[] args) {
        System.out.println("[main] before=" + DemoTarget.message());

        // DemoTarget was already loaded by the call above.
        RetransformAgent.retransform(DemoTarget.class);

        System.out.println("[main] after=" + DemoTarget.message());
    }
}
```

The application explicitly requests retransformation after using `DemoTarget`. In practice, an agent can find loaded classes via `getAllLoadedClasses()` and select target classes by name/class loader, while avoiding scanning and interfering with every class indiscriminately.

### 5.4. File `manifest-enabled.mf`

```text
Manifest-Version: 1.0
Premain-Class: RetransformAgent
Can-Retransform-Classes: true

```

Keep the **trailing blank line** ending the manifest's main section. `Premain-Class` is used when launching the agent with `-javaagent`; `Can-Retransform-Classes` requests the capability. Because the classes are in the default package, the class name `RetransformAgent` has no package prefix.

### 5.5. Compile, package, and run

Open a terminal in the directory containing the four files, using JDK 17 or newer that supports `--release 17`:

```bash
javac --release 17 RetransformAgent.java DemoTarget.java DemoApp.java
jar --create --file demo-enabled.jar --manifest manifest-enabled.mf RetransformAgent.class DemoTarget.class DemoApp.class
java -javaagent:demo-enabled.jar -cp demo-enabled.jar DemoApp
```

On a **standard HotSpot/JDK 17+ with retransformation support**, stdout from the `java` command is:

```text
[agent] supported=true
[main] before=hello
[transformer] retransform DemoTarget
[agent] retransform request completed
[main] after=hello
```

Meaning:

- `premain` runs before `DemoApp.main` and confirms the capability.
- The first call to `DemoTarget.message()` simply loads the class. The registered transformer may receive a callback on first load, but the `println` statement inside the transformer intentionally runs only when `classBeingRedefined != null`.
- `retransformClasses(DemoTarget.class)` re-invokes the transformer registered with `true`; it prints the `[transformer] ...` line.
- Because the transformer returns `null`, `message()`'s behavior is unchanged. **Retransformation does not mean bytecode must be altered every time.**

If the JVM does not grant the capability, the program takes the `supported=false` branch and prints `skipped: unsupported`. Do not treat the `supported=true` output on a typical HotSpot environment as a guarantee for every JVM.

### 5.6. Control case: missing capability in the manifest

Create **`manifest-disabled.mf`**:

```text
Manifest-Version: 1.0
Premain-Class: RetransformAgent
Can-Retransform-Classes: false

```

Package into a **different JAR** to avoid confusing artifacts:

```bash
jar --create --file demo-disabled.jar --manifest manifest-disabled.mf RetransformAgent.class DemoTarget.class DemoApp.class
java -javaagent:demo-disabled.jar -cp demo-disabled.jar DemoApp
```

On the same HotSpot that supports retransformation, stdout is now:

```text
[agent] supported=false
[main] before=hello
[agent] skipped: unsupported
[main] after=hello
```

The Java code is **unchanged**; the difference comes from the **agent JAR's manifest**. If you omit the `Can-Retransform-Classes` line entirely, the default is also `false`.

### 5.7. What happens if you skip the check?

If you omit `if (!supported) return;` and go ahead and call:

```java
inst.addTransformer(transformer, true);
```

in an unsupported configuration, the API can throw **`UnsupportedOperationException`** right at registration time. Similarly, calling `inst.retransformClasses(...)` when the configuration does not allow it also throws `UnsupportedOperationException`. Do not use this exception as the normal way to “probe whether the JVM supports it”; the API provides `isRetransformClassesSupported()` for explicit branching.

## 6. Limitations of retransformation

### 6.1. Not an arbitrary structural hot reload

On many JVMs, retransformation is used to modify **bodies of existing methods** or allowed metadata. You cannot assume it is permitted to:

- Add, remove, or rename methods or fields;
- Change method signatures, structurally significant modifiers, superclass, or interfaces;
- Change structural relationships such as nestmates, records, or permitted subclasses in ways JVMTI does not support;
- Replace a class file with a version newer than the current JVM can understand.

The exact set of allowed changes is defined by **JVMTI `RetransformClasses`** and JVM capabilities. Invalid transformations can lead to `UnsupportedOperationException`, `ClassFormatError`, `VerifyError`, or appropriate forms of `LinkageError`.

### 6.2. Not every class can be modified

`isModifiableClass()` reports the capability for a specific class. Primitive types and arrays are never modifiable; certain special JVM classes may also be restricted. Do not pass all of `getAllLoadedClasses()` into `retransformClasses(...)` without filtering.

Understand **class identity**, which consists of name and class loader. Two `com.example.Service` classes defined by two different class loaders are two distinct classes. If an agent filters only by name without accounting for the loader, it may accidentally touch classes belonging to the application, plugins, tests, or frameworks.

### 6.3. No guarantee that running frames switch immediately to new code

When a method is executing, existing frames may continue with the old bytecode version; new invocations use the new definition. Existing instances and static values are not automatically recreated or reset. Thus, “retransformation succeeded” does not mean every thread observes the change at the exact same instant.

### 6.4. Granted capability does not mean every transformer re-runs

A transformer registered via `addTransformer(transformer)` **is not called again** during retransformation; its already-applied result is reused. You must register with `addTransformer(transformer, true)` **from the start** when you genuinely want callbacks on already-loaded classes.

There is no operation on the same registration to flip `false` to `true`; you can manage registrations (remove/re-register) when the capability is supported, but you must account for already-transformed classes, transformer ordering, and races with class loading.

## 7. Comparison with load-time transform and redefine

| Criterion | Load-time transform | Retransform | Redefine |
| --- | --- | --- | --- |
| Trigger | JVM prepares to define a class | `retransformClasses(Class<?>...)` | `redefineClasses(ClassDefinition...)` |
| Class already loaded? | Not yet defined when the transformer is called | **Yes** | **Yes** |
| Bytecode source | Bytes submitted to define the class | Baseline bytes from most recent define/redefine and transformer chain | Replacement bytes supplied by caller |
| Capability requirement | No `Can-Retransform-Classes` needed to register a `false` transformer | Requires `Can-Retransform-Classes` + VM support | Requires `Can-Redefine-Classes` + VM support |
| Control API | `addTransformer(transformer)` | `addTransformer(transformer, true)` and `retransformClasses` | `redefineClasses` with `ClassDefinition` |
| Restrictions | Bytecode must be valid and match the class being defined | Restrictions on modifying loaded classes | Restrictions on modifying loaded classes |

`Can-Retransform-Classes` and `Can-Redefine-Classes` are two **independent** manifest capabilities. Do not assume enabling one enables both. `isRetransformClassesSupported()` is not a substitute for `isRedefineClassesSupported()`.

## 8. Designing agents safely with optional capabilities

In performance monitoring, coverage, or tracing agents, a practical workflow is typically:

1. When `premain` or `agentmain` receives `Instrumentation`, read and log `isRetransformClassesSupported()`.
2. If `true`, register the transformer with `canRetransform=true` and prepare a mechanism to select the right loaded classes; if `false`, use a mode that only observes future class loads with `addTransformer(transformer, false)` when that meets your needs.
3. When you need to modify loaded classes, filter `getAllLoadedClasses()` by class kind, class loader, module, or name; check `isModifiableClass` for each class.
4. Execute `retransformClasses` in controlled batches; transformers should be deterministic, idempotent, and have clear error handling.
5. Verify impact on the target JVM environment: startup/runtime performance, interaction among multiple agents, callback counts, active threads, and verify/linkage errors.
6. When retiring a transformer, you can call `removeTransformer(transformer)`; note that in-flight callbacks may still arrive due to concurrent class loading, and unregistering **does not automatically revert already-installed bytecode**.

### “Fallback” when retransformation is unsupported

Some agents only need to measure classes loaded **after the agent is attached**. When the capability is false, registering a `false` transformer still allows load-time instrumentation of new classes; you cannot expect already-loaded classes to go through the transformer. Agents that need to observe already-loaded classes may choose alternatives such as existing metrics, application logging, or narrowing feature scope. Do not claim full instrumentation if critical classes are in fact missing.

### Do not put retransformation in a tight loop

Retransformation goes through class file processing/verification and can affect latency, JIT compilation, or running code behavior. Do not default to calling it in an endless loop for all classes to “keep the agent up to date”. Trigger it only on configuration changes or explicit measurement requests, while monitoring timing and errors.

## 9. Common errors and how to fix them

| Symptom | What to check |
| --- | --- |
| `isRetransformClassesSupported()` is `false` on a seemingly recent JDK | Does the manifest in the **actual agent JAR** have `Can-Retransform-Classes: true`? Was it launched with the right `-javaagent`/entry point? Does the JVM support the capability? |
| `addTransformer(t, true)` throws `UnsupportedOperationException` | Requesting a retransform-capable transformer when the configuration does not grant it; check `isRetransformClassesSupported()` first |
| `transform()` is not called again | Was the transformer registered with `true`? Was `retransformClasses` actually called for the loaded class? Are the class name/loader filters correct? |
| `isModifiableClass(c)` is `false` | The class may be an array/primitive or a JVM class that cannot be modified; skip it instead of trying to retransform |
| `retransformClasses` throws `UnmodifiableClassException` | A class in the set is not modifiable; check and split into smaller batches to identify the class |
| `retransformClasses` throws `UnsupportedOperationException` | Capability is missing or the transformer produced a change not supported for an active class |
| `ClassFormatError`/`VerifyError`/`LinkageError` | Generated bytecode is invalid; check class-file version, stack map frames, constant pool, schema, and ASM/Byte Buddy usage |
| Retransform succeeds but behavior does not change | Transformer returns `null`, does not instrument the target method, has a wrong filter, or active frames are still running old code |
| Old effect persists after `removeTransformer` | Unregistering does not automatically undo the definition currently used by the JVM; design an explicit revert if needed |
| Running with `-cp` without the agent | Not launched with `-javaagent` or an appropriate agent mechanism; merely having a manifest in a JAR on the classpath does not activate it |

When diagnosing, inspect the **actual launch path** (`java -javaagent:...`, dynamic attach, or executable JAR), the **post-build manifest**, the running JVM, the **class loader**, and the exact stack trace. An “unsupported” message can come from the JVM, a bytecode library, or the agent; distinguish the source before fixing.

## 10. Self-check quiz

**Question 1.** An agent JAR has `Premain-Class` but no `Can-Retransform-Classes`. The agent calls `addTransformer(t)` and runs fine. Does that prove retransformation is supported?

**Answer:** No. `addTransformer(t)` defaults to `canRetransform=false`, which allows observing/transforming classes at load time. Retransformation capability requires the proper manifest attribute and JVM support; read `isRetransformClassesSupported()` to know.

**Question 2.** `Can-Retransform-Classes: true` is set, yet `isRetransformClassesSupported() == false`. Can you call `retransformClasses` to “force” the JVM to enable the feature?

**Answer:** No. The capability is optional for the JVM; the call may throw `UnsupportedOperationException`. Choose an appropriate fallback path or use a runtime that supports it.

**Question 3.** The JVM supports retransformation, but a transformer was added with `addTransformer(t, false)`. When `retransformClasses` runs, is `t.transform(...)` called again?

**Answer:** No. This transformer's previous transformation result is reapplied per the contract; only transformers registered with `true` are called again during retransformation.

**Question 4.** Does `isRetransformClassesSupported() == true` mean every class can be modified?

**Answer:** No. `isModifiableClass(c)`, class-file/JVMTI restrictions, and bytecode validity still apply. Primitive and array classes cannot be modified via this mechanism.

**Question 5.** Does retransforming a class with a method currently mid-execution automatically re-run the static initializer or replace the contents of existing stack frames?

**Answer:** No. The static initializer does not re-run merely due to retransformation; active frames continue with the old bytecode, while new invocations use the new definition.

## 11. Official references

- [Oracle Java SE 17 — `Instrumentation` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `isRetransformClassesSupported`, `isModifiableClass`, `addTransformer`, `retransformClasses`.
- [Oracle Java SE 21 — `java.lang.instrument` package specification](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): manifest attributes and agent startup mechanisms.
- [Oracle Java SE 21 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): transformer ordering, callback characteristics, and retransformation conditions.
- [Oracle Java SE 21 — `Instrumentation` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): retransformation process, errors, and constraints when modifying loaded classes.
- [JVM Tool Interface — `RetransformClasses`](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html): VM-level restrictions on class file changes.

**Key takeaway:** The `Can-Retransform-Classes: true` manifest attribute only **requests** the capability; `isRetransformClassesSupported()` confirms the **granted capability**. To transform already-loaded classes, register a transformer with `canRetransform=true`, check `isModifiableClass`, and call `retransformClasses`. Having the capability granted does not remove class-file constraints, runtime constraints, or the need for testing.
