# Distinguishing First Definition from Redefine or Retransform via Callback Context

> **Key takeaway:** In `ClassFileTransformer.transform(...)`, the `Class<?> classBeingRedefined` parameter is a reliable indicator for distinguishing **first-time class definition** from **reprocessing an already-defined class**: `null` when the class is being defined for the first time; **non-`null`** when the JVM is performing a **redefine or retransform**. However, **this value alone cannot distinguish between the two operations `redefine` and `retransform`**: both pass the `Class<?>` object. To interpret the callback accurately, additional context is needed regarding the API that triggered the operation, the transformer's `canRetransform` capability, and the source of the class-file bytes the JVM is processing.

This lesson belongs to the **Transformer Contract** group in Java Instrumentation. The goal is to read the callback according to its exact lifecycle and avoid misinterpreting a `transform` invocation as "the class is loading for the first time" or "it is definitely retransforming."

## 1. Three Moments the JVM Can Call `transform`

A Java agent registers a `ClassFileTransformer` object using `Instrumentation.addTransformer(...)`. The JVM uses the transformer in the following situations:

1. **First definition (class load).** A class loader or an equivalent mechanism requests the JVM to create a `Class` definition from class-file bytes. The callback is invoked **before the JVM verifies and defines the class**. At this point **`classBeingRedefined == null`** because there is no defined `Class<?>` yet to replace.
2. **Redefine.** A tool calls `Instrumentation.redefineClasses(new ClassDefinition(existingClass, replacementBytes))` or an equivalent JVM TI mechanism. The class **already exists**; the system supplies replacement class-file bytes. The callback receives **`classBeingRedefined != null`**.
3. **Retransform.** A tool calls `Instrumentation.retransformClasses(existingClass)` or equivalent. The class **already exists**; the JVM reruns the transformation pipeline from the base bytes of the initial definition or the most recent redefine, with a mechanism that reuses the results of retransformation-incapable transformers. The callback of a **retransformation-capable transformer** receives **`classBeingRedefined != null`**.

~~~mermaid
flowchart TD
    A["JVM processes class definition"] --> B{"Is there an already-defined Class<?>?"}
    B -->|No| C["First definition: classBeingRedefined = null"]
    B -->|Yes| D["Redefine or retransform: classBeingRedefined != null"]
    D --> E["Cannot infer redefine/retransform separately from this parameter"]
    C --> F["Transformer returns null or new bytes"]
    E --> F
    F --> G["JVM continues checking and applying the definition"]
~~~

For **first definition**, the transformer can process the class even if the application has never executed a single line in that class. For **redefine/retransform**, the `Class<?>` already exists, and instances along with stack frames executing the old code may already exist.

## 2. Reading Callback Parameters Correctly

In Java 17+, the full form with the `Module` parameter is:

~~~java
byte[] transform(Module module,
                 ClassLoader loader,
                 String className,
                 Class<?> classBeingRedefined,
                 ProtectionDomain protectionDomain,
                 byte[] classfileBuffer);
~~~

This is an **illustrative API signature**, not a standalone Java program. The API also has a five-parameter form (without `Module`):

~~~java
byte[] transform(ClassLoader loader,
                 String className,
                 Class<?> classBeingRedefined,
                 ProtectionDomain protectionDomain,
                 byte[] classfileBuffer);
~~~

Both methods in the interface have default implementations in modern JDKs: the six-parameter form delegates to the five-parameter form by default, and the five-parameter form returns `null` by default. Therefore, you can override **either one**; the hands-on section below overrides the six-parameter form, compatible with Java 17+.

| Parameter | Practical Meaning | Common Pitfall |
| --- | --- | --- |
| `module` | The module containing the class being transformed (API since Java 9) | Assuming it is the agent's module |
| `loader` | The class loader defining the class; `null` may mean the bootstrap loader | Equating `loader == null` with redefine/retransform |
| `className` | Class name in JVM internal name format, e.g., `com/acme/Target` | Filtering with `com.acme.Target` or confusing it with `Class.getName()` |
| **`classBeingRedefined`** | `null` on **first definition**; the `Class<?>` object on **redefine/retransform** | Treating non-null as "definitely retransform" |
| `protectionDomain` | Protection domain used when defining the class | Treating it as an event code or operation cause |
| `classfileBuffer` | Input class-file bytes for the **current transform pass** | Assuming it is always the original bytes on disk or safe to mutate directly |

**Reading rule in code:**

~~~java
if (classBeingRedefined == null) {
    // Class load/first definition.
} else {
    // Class already exists: redefine OR retransform.
    // This parameter alone does NOT tell which exact operation it is.
}
~~~

This is an **illustrative conditional snippet inside a callback**, not standalone runnable code. If you need to print the name, use `className` for both cases; when `classBeingRedefined != null`, you can use `classBeingRedefined.getName()`. For packaged names, the two formats differ: `com/acme/Target` and `com.acme.Target`.

In addition:

- `classfileBuffer` **must not be modified in place**. Return `null` when not transforming; if transformation is needed, create a new `byte[]` containing a valid class file.
- Callbacks can run in class-loading paths across multiple threads. Do not use a global `currentMode` variable to reliably infer the operation if multiple agents or JVM TI tools are active concurrently.
- The callback occurs **while the JVM is processing the request**, before the new bytes are completely applied. A "transform called" log **does not prove** that redefine/retransform succeeded.
- The fact that a class was defined in the past **does not automatically re-invoke the transformer**; an actual request (redefine/retransform) and appropriate transformer configuration are required.

## 3. Situation and Callback Eligibility Matrix

A transformer has two registration modes:

~~~java
inst.addTransformer(transformer);        // Equivalent to canRetransform=false
inst.addTransformer(transformer, false); // Retransformation-incapable
inst.addTransformer(transformer, true);  // Retransformation-capable
~~~

These are **illustrative calls** inside a method receiving `Instrumentation inst`. Passing `true` requires the JVM/agent to permit retransformation. Do not confuse a transformer's `canRetransform` with the ability to call `redefineClasses`.

| Event | `classBeingRedefined` in callback | Transformer `canRetransform=false` | Transformer `canRetransform=true` |
| --- | --- | --- | --- |
| Class **defined for the first time** after registration | `null` | **Called** | **Called** |
| `redefineClasses` on an existing class | **non-null** | **Called** | **Called** |
| `retransformClasses` on an existing class | **non-null** | **Not called again**; JVM reapplies the previous transform result | **Called** |

What needs emphasis is the "Not called again" cell in the retransform row: **not receiving a callback does not mean that incapable transformer has lost its effect**. The JVM retains and reapplies the previous result of that transformer instead of invoking its `transform` method again.

In many JVMs, the order of transform groups is:

1. Java transformers that are **not** retransformation-capable.
2. Native transformers that are **not** retransformation-capable (via JVM TI).
3. Java transformers that **are** retransformation-capable.
4. Native transformers that **are** retransformation-capable.

Within each group, transformers are invoked in registration order. During retransformation, the incapable groups have their **results reapplied** without invoking callbacks; the capable groups are actually invoked. If multiple transformers modify bytes, each subsequent pass receives the output of the previous pass. Returning `null` means no byte changes in that pass.

**Important:** Even if you only install one `canRetransform=true` transformer, non-null **still does not indicate** whether this is redefine or retransform; that transformer receives both. Distinguish them via **the request source and controlled context**, not via a single comparison on a callback parameter.

## 4. Java 17+ Hands-On Example: Observing All Three Contexts

This experiment intentionally registers **two transformers**:

- `fixed`: `canRetransform=false`.
- `capable`: `canRetransform=true`.

Both only log and **return `null`, without modifying bytecode**. After the `Target` class is loaded, the application requests a **retransform**, and then **redefines** the same class using bytes from a structurally identical replacement. This makes the logs clearly show which callback is invoked and what value `classBeingRedefined` receives.

You need JDK 17+ with `javac`, `jar`, `java`; the JVM must actually support both capabilities. No external libraries are needed.

### 4.1. Create `TraceTransformer.java`

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

public final class TraceTransformer implements ClassFileTransformer {
    private final String label;

    public TraceTransformer(String label) {
        this.label = label;
    }

    @Override
    public byte[] transform(Module module, ClassLoader loader, String className,
            Class<?> classBeingRedefined, ProtectionDomain domain, byte[] originalBytes) {
        if (!"Target".equals(className)) {
            return null;
        }
        String context = classBeingRedefined == null ? "FIRST_DEFINITION" : "REVISIT";
        String target = classBeingRedefined == null ? "null" : classBeingRedefined.getName();
        System.out.println(label + ": " + context + ", classBeingRedefined=" + target);
        return null;
    }
}
~~~

Because the `Target` class in the example is in the **default package**, `className` equals `"Target"`. In a real project with `package demo;`, you must filter with `"demo/Target"`. The `context` variable intentionally has only **FIRST_DEFINITION** and **REVISIT**: do not name it **RETRANSFORM** just because `classBeingRedefined` is non-`null`.

### 4.2. Create `EventAgent.java`

~~~java
import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;

public final class EventAgent {
    private static Instrumentation instrumentation;

    public static void premain(String args, Instrumentation inst) {
        instrumentation = inst;
        if (!inst.isRetransformClassesSupported() || !inst.isRedefineClassesSupported()) {
            throw new IllegalStateException("This demo requires both capabilities");
        }
        inst.addTransformer(new TraceTransformer("fixed"), false);
        inst.addTransformer(new TraceTransformer("capable"), true);
    }

    public static void retransform(Class<?> type) throws Exception {
        instrumentation.retransformClasses(type);
    }

    public static void redefine(Class<?> type, Path replacement) throws Exception {
        byte[] newClassFile = Files.readAllBytes(replacement);
        instrumentation.redefineClasses(new ClassDefinition(type, newClassFile));
    }
}
~~~

`Instrumentation` is passed by the JVM into `premain`. The agent stores the reference so the demo application can proactively trigger both operations, helping distinguish the cause of each log segment. In production, only authorized components should invoke redefine/retransform mechanisms; do not expose control APIs to business code by default.

`retransformClasses(Class<?>...)` asks the JVM to use the base bytes of the already-loaded class itself. `redefineClasses(ClassDefinition...)` takes **new bytes** supplied by the caller. In the example, the bytes for redefine are read from `replacement/Target.class`.

### 4.3. Create Two Versions of `Target`

**`Target.java`** in the root directory of the exercise:

~~~java
public final class Target {
    public String value() {
        return "v1";
    }
}
~~~

**`replacement/Target.java`** in the `replacement` subdirectory:

~~~java
public final class Target {
    public String value() {
        return "v2";
    }
}
~~~

Both files use **the same class name and the same field/method structure**; only the string constant returned by the method changes. Do not put both `Target.class` files on the application classpath at the same time. Version `v2` is **the input class-file bytes for redefine**, not a separate Java class with a different name. If you change the class name, add/remove methods, or alter signatures arbitrarily, the JVM may reject `redefineClasses` for violating structural constraints.

### 4.4. Create `EventApp.java`

~~~java
import java.nio.file.Path;

public final class EventApp {
    public static void main(String[] args) throws Exception {
        Target target = new Target();
        System.out.println("initial=" + target.value());

        EventAgent.retransform(Target.class);
        System.out.println("after-retransform=" + target.value());

        EventAgent.redefine(Target.class, Path.of("replacement/Target.class"));
        System.out.println("after-redefine=" + target.value());
    }
}
~~~

Notice that the application **does not recreate** the `target` object after redefine; the same instance will invoke the new `value()` implementation on subsequent calls if redefine succeeds.

### 4.5. Create the Manifest `agent.mf`

~~~text
Manifest-Version: 1.0
Premain-Class: EventAgent
Can-Retransform-Classes: true
Can-Redefine-Classes: true
~~~

This is the **main manifest section** of a startup agent, and the text file must end with a trailing newline. Both capabilities are optional depending on JVM configuration; having the flag set to `true` is only a request condition, and you must still check the result via `isRetransformClassesSupported()` and `isRedefineClassesSupported()`. If the JVM does not support them, the example intentionally stops with a message from `premain`.

### 4.6. Compile, Package, and Run

From a clean directory containing the four files `TraceTransformer.java`, `EventAgent.java`, `Target.java`, `EventApp.java`, `agent.mf`, and the subdirectory `replacement/Target.java`, run:

~~~bash
javac --release 17 TraceTransformer.java EventAgent.java Target.java EventApp.java

javac --release 17 -d replacement replacement/Target.java

jar --create --file event-agent.jar --manifest agent.mf EventAgent.class TraceTransformer.class

java -javaagent:event-agent.jar -cp . EventApp
~~~

The commands use JDK syntax and can be run in Bash, CMD, or PowerShell from the **exercise directory**. `javac --release 17` requires a JDK supporting release 17. `EventAgent.class` and `TraceTransformer.class` must be inside the agent JAR; the `v1` version of `Target.class` is in the application directory; `replacement/Target.class` is the bytes file supplied for redefine.

On OpenJDK/HotSpot supporting both capabilities, **the stdout of the code above is**:

~~~text
fixed: FIRST_DEFINITION, classBeingRedefined=null
capable: FIRST_DEFINITION, classBeingRedefined=null
initial=v1
capable: REVISIT, classBeingRedefined=Target
after-retransform=v1
fixed: REVISIT, classBeingRedefined=Target
capable: REVISIT, classBeingRedefined=Target
after-redefine=v2
~~~

### 4.7. Reading Each Log Group

**Group 1 — first definition:**

~~~text
fixed: FIRST_DEFINITION, classBeingRedefined=null
capable: FIRST_DEFINITION, classBeingRedefined=null
initial=v1
~~~

Both transformers were registered in `premain`, before `Target` was loaded. Therefore both `fixed` and `capable` are invoked when the JVM **defines `Target` for the first time**, with `classBeingRedefined == null`.

**Group 2 — retransform:**

~~~text
capable: REVISIT, classBeingRedefined=Target
after-retransform=v1
~~~

The application just called `EventAgent.retransform(Target.class)`. The `capable` transformer is invoked because `canRetransform=true`; the `fixed` transformer **is not called again**. The JVM still reapplies the previous result of `fixed` if that transformer had modified bytes. In the demo, both return `null`, so `Target.value()` remains `"v1"`.

**Group 3 — redefine:**

~~~text
fixed: REVISIT, classBeingRedefined=Target
capable: REVISIT, classBeingRedefined=Target
after-redefine=v2
~~~

The application just called `EventAgent.redefine(...)` with the class bytes of `Target` version `v2`. **Both transformers** receive the callback during redefine. Both again return `null`, so the `v2` bytes are applied and the `target` instance invokes the new `value()`.

**Observation conclusion:** The two `capable: REVISIT` lines in group 2 and group 3 **have the exact same callback data pattern** (`classBeingRedefined=Target`). They can only be distinguished by **the operation requested by the application** and the callback pattern of `fixed`, not by the `classBeingRedefined` value alone.

## 5. Redefine and Retransform Differ in Byte Source

Both process an existing class, but the *input* to the transformer is not the same:

| Property | `retransformClasses(Target.class)` | `redefineClasses(new ClassDefinition(Target.class, bytes))` |
| --- | --- | --- |
| Who supplies the bytes? | The JVM takes the base bytes from the initial definition or **the most recent redefine** | The caller supplies **replacement bytes** via `ClassDefinition` |
| Re-invokes `canRetransform=false` transformers? | **No**; reuses the previous transform result | **Yes** |
| Invokes `canRetransform=true` transformers? | **Yes** | **Yes** |
| `classBeingRedefined` received in callback | Non-null | Non-null |
| Capability checks | `isRetransformClassesSupported()` and class modifiability | `isRedefineClassesSupported()` and class modifiability |
| Common scenario | Updating instrumentation for already-loaded classes | Hotfix or replacing a definition from chosen class-file bytes |

### 5.1. Are the Bytes in `classfileBuffer` Always Identical to the File on Disk?

**No.** For class load, the initial input comes from the class-file bytes passed to `ClassLoader.defineClass` (or equivalent mechanism). For redefine, the initial input is `ClassDefinition.getDefinitionClassFile()`; those may be custom-built bytes supplied by the user. For retransform, the JVM reconstructs the input from the base bytes after the most recent load or redefine, plus the results of retransformation-incapable transformers automatically reapplied.

Java documentation notes that the base bytes during retransform **are not necessarily byte-for-byte identical** to the original bytes: constant-pool entries and certain attributes may be reorganized. Therefore, comparing the hash of `classfileBuffer` against the `.class` file on disk to identify DEFINE/REDEFINE/RETRANSFORM is error-prone.

### 5.2. Effects After a Class Is Redefined

- **The class initializer `<clinit>` is not re-run** simply because of redefine/retransform. Existing static field values are preserved according to standard semantics.
- Previously created instances **are not replaced with new objects**; new invocations can execute the new bytecode.
- For methods with stack frames currently executing at the time of redefinition, those frames may continue running the old code; new calls use the new definition.
- Definition changes have **structural constraints**. You cannot arbitrarily add/remove fields/methods, change signatures, or alter inheritance hierarchies in a single redefine/retransform under current Java instrumentation rules.
- An executing method is not "restarted from the beginning" when instrumentation changes the class definition.

In the example, the same `target` instance returns `"v1"` after retransform but returns `"v2"` after redefine, because only the second operation supplies **new class-file bytes**.

## 6. Conditions for Callbacks to Appear as Expected

To verify real code, distinguish **JVM capabilities**, **transformer capabilities**, and **class modifiability**:

1. The agent manifest requires `Can-Retransform-Classes: true` if retransform is needed; it requires `Can-Redefine-Classes: true` if redefine is needed. These are **two independent attributes**.
2. The JVM may not support one or both, so you must call `inst.isRetransformClassesSupported()` and `inst.isRedefineClassesSupported()` before using them.
3. For a specific class, call `inst.isModifiableClass(Target.class)`. Array classes and primitives cannot be modified via the API; you should not assume every bootstrap, VM-generated, or special class is modifiable.
4. Only transformers registered with `addTransformer(t, true)` are called again during a retransform. `addTransformer(t)` implicitly uses `false`.
5. Some classes may already have been defined **before registering** the transformer. In that case, there is never a retroactive DEFINE callback; the agent only sees later processing if the JVM and the class allow it.
6. Transformers should be registered early enough to observe initial class definitions. In a startup agent, registering in `premain` typically satisfies this for application classes loaded afterward; if loading an agent dynamically, many classes may already be defined.
7. Do not equate a **successful `retransformClasses` call** with *every transformer having run*: incapable transformers are not called again, even when their previous results still take effect.

If `addTransformer(t, true)` is used when the capability is unsupported, `UnsupportedOperationException` may be thrown. If `retransformClasses` or `redefineClasses` is requested for an unmodifiable class, `UnmodifiableClassException` may occur, or class format/version/linkage errors when bytes are invalid. The API rejecting a request does not mean no callbacks ran beforehand: some callbacks may have already executed before the final check/application step.

## 7. Writing Safe Transformers When a Class Can Be Processed Multiple Times

Transformers used in production must handle both initial load and multiple redefine/retransform cycles cleanly:

- **Correct name and class loader:** `className` is in `com/example/Target` form; do not convert to a dotted name unnecessarily when comparing. Two class loaders can define **two different classes** with the same name; track both `loader` and class name if needed.
- **Semantically idempotent:** do not blindly re-insert the same logging call into bytecode every time you see `classBeingRedefined != null`. Retransformation typically uses reconstructed base bytes, but when multiple transformers or external-byte redefines are involved, markers/instrumentation may already be present. Verify the actual structure of the input bytes.
- **Do not mutate input in place:** allocate a new byte array if transforming; if not modifying, return `null`.
- **Do not over-classify operations using the callback:** `classBeingRedefined != null` means *existing class*, do not infer `retransform`; track the source action if your task must distinguish them.
- **Thread-safe and avoid class-loading cycles:** callbacks may be invoked concurrently; logging with heavy frameworks, deep reflection, or loading additional instrumented classes can cause recursion, deadlocks, or linkage errors.
- **Keep class structure valid across redefinitions:** if a transformer adds methods/fields at initial load, subsequent redefine/retransform passes must produce a valid class definition under the allowed rules. Arbitrary structural changes may be rejected.
- **Separate classification decisions from transformation decisions:** a callback can log "FIRST_DEFINITION"/"REVISIT" from parameters, then decide whether to transform based on policy and actual bytes. Do not keep global state assuming "this class is only transformed once in the JVM's lifetime."
- **Lifecycle management:** `removeTransformer` unregisters for future passes, but due to concurrent processing, callbacks may still occur after the remove call; it does not automatically revert already-modified class bytes.

### Safer Logging Example for Operational Monitoring

~~~java
String identity = String.valueOf(className);
String context = classBeingRedefined == null ? "DEFINE" : "EXISTING_CLASS";
String loaderName = loader == null ? "bootstrap" : loader.getClass().getName();
System.out.println(context + " " + identity + " loader=" + loaderName);
~~~

This is an **illustrative code snippet placed inside `transform`**, not a standalone `.java` file. Do not let logging cause the transformer to reload the very classes it intercepts: set narrow filters and use low-dependency logging for sensitive callbacks.

## 8. When Logs Only Contain Callbacks, How Far Can You Conclude?

| Observed Signal | Warranted Conclusion | What **Cannot** Yet Be Concluded |
| --- | --- | --- |
| `classBeingRedefined == null` | The JVM is processing the initial class definition | That the class definitely does not exist on the filesystem, or that `main` is about to run |
| `classBeingRedefined != null` | The JVM is processing an already-defined class | Whether it is redefine or retransform **without other context** |
| A `canRetransform=false` transformer appears | That callback **cannot be a normal retransformation** | Whether it is DEFINE or REDEFINE without checking `classBeingRedefined` |
| A `canRetransform=true` transformer appears with non-null | It is a revisit | Whether it is redefine or retransform based on the flag alone |
| No `fixed` callback seen during a retransform operation | Normal rule of not re-invoking incapable transformers | That `fixed`'s previous result definitely no longer has effect |
| `transform` returns `null` | This transformer requested no byte changes in the current pass | That the entire transformer chain or JVM operation definitely did not modify the class |
| A "REVISIT" log appears | The transformer was called while processing a class-modification request | That the request applied successfully or that currently running methods switched code immediately |

**How to determine the exact cause in an application you control:**

- Log at the call site of `Instrumentation.retransformClasses` or `Instrumentation.redefineClasses`: operation type name, target class, timestamp, and success/failure status.
- Log narrowly inside the callback: `className`, `classBeingRedefined`, `canRetransform` registration group, and necessary class loader/module info.
- Correlate both log types and test results. Do not rely on "callback ran on thread X" to prove operation Y: another JVM TI tool or multiple concurrent tasks can trigger callbacks.
- If you do not control the triggering tool and logs only show `classBeingRedefined != null`, report **"redefine/retransform indistinguishable"** rather than guessing.

## 9. Self-Check

**Scenario A:** The callback receives `classBeingRedefined == null`, `className="sample/Widget"`. What can be said: `Widget` is undergoing its first definition from class-file bytes for that class loader. Do not call `classBeingRedefined.getName()` as it will throw `NullPointerException`.

**Scenario B:** A `canRetransform=false` transformer just logged with `classBeingRedefined != null`. By the callback contract, this is **redefine** rather than retransform (incapable transformers are not called again during retransform).

**Scenario C:** A `canRetransform=true` transformer logs with `classBeingRedefined != null`. It could be **redefine or retransform**. You must rely on the triggering operation or additional evidence.

**Scenario D:** When calling retransform, the logs do not show the `fixed` transformer, yet the class behavior still contains instrumentation created by `fixed` from the previous definition. This is normal behavior because the JVM **reuses the result** without calling the incapable transformer again.

**Scenario E:** After redefine, an existing instance returns a new result on the next call, while no static initializer runs again. This matches redefinition semantics; it does not mean the JVM created a new class with the same name.

### Official References

- [Java SE 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): both `transform` signatures, meaning of `classBeingRedefined`, transformer ordering, byte sources, and callback rules.
- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `retransformClasses`, `redefineClasses`, capabilities, and modifiable class constraints.
- [Java SE 17 — ClassDefinition](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html): pair of `Class<?>` and class-file bytes supplied by the caller for redefine.
