# Ordering of the Four Transformer Groups: Java, Native, and Retransformation Capability

> **Goal:** Understand the standard ordering of the four groups of Java `ClassFileTransformer` and native JVMTI `ClassFileLoadHook`; know the difference between *retransformation incapable* and *retransformation capable*; predict how class bytes flow through transformers during **load**, **redefine**, and **retransform**; verify the ordering yourself using Java 17+; recognize limitations to avoid double-counting probes or misinterpreting agent logs.

This lesson belongs to the **Transformer Chaining** section. This is the order in which the JVM applies transformations to **class-file bytes**, not the execution order of application methods after a class has been loaded.

## 1. A Class Can Pass Through Multiple Transformers

Within the same JVM, we can install a coverage Java agent, a native JVMTI profiler, a tracing Java agent, and another bytecode analysis tool. All of them may be interested in the same `com/example/OrderService`. The JVM does not overwrite the class independently on a "last agent wins" basis; instead, it **chains the results layer by layer**:

```text
Original class bytes
    │
    ▼
Transformer A → bytes A
    │
    ▼
Transformer B → bytes B (receives bytes A as input)
    │
    ▼
Transformer C → bytes C
    │
    ▼
Verifier / JVM applies the class definition
```

A Java `ClassFileTransformer.transform(...)` can return `null` if no transformation is made, or a new `byte[]` array if it has produced a valid class file. When a layer returns `null`, the current bytes **pass through unchanged**, without reverting to the original bytes. A native JVMTI `ClassFileLoadHook` can also keep or replace class data through the native interface.

The key question is: **by what rules are A, B, and C ordered?** If both Java transformers and native transformers are present, looking only at global registration time will give the wrong answer. The JVM divides transformers into exactly **four groups with a fixed order**.

## 2. The Four Groups According to the JDK Specification

According to the `ClassFileTransformer` Javadoc, the transformation order is:

| Order | Group | Mechanism | Retransformation |
| --- | --- | --- | --- |
| **1** | Java **retransformation incapable** | `Instrumentation.addTransformer(t, false)` or `addTransformer(t)` | No new callback on retransform |
| **2** | Native **retransformation incapable** | JVMTI `ClassFileLoadHook` of an incapable environment | No new callback on retransform |
| **3** | Java **retransformation capable** | `Instrumentation.addTransformer(t, true)` | New callback on retransform |
| **4** | Native **retransformation capable** | JVMTI `ClassFileLoadHook` of a capable environment | New callback on retransform |

Remember this exact sequence:

```text
1. Java incapable
       ↓
2. native incapable
       ↓
3. Java capable
       ↓
4. native capable
```

This is the rule the JVM applies **across groups**, regardless of which agent started or registered first. **Within each group**, transformers are processed in registration order. For native JVMTI, within each group the order of environments is based on environment creation order per the JVMTI specification; it is not ordered by `.so`/`.dll` library name.

The word "native" here refers to a native JVMTI agent with a **`ClassFileLoadHook`** callback. It does not mean that every Java method written with the `native` keyword is a transformer, nor does it mean that any arbitrary JNI library participates in the transformation chain.

### An Easy-to-Confuse Example About Registration Order

Suppose:

```text
09:00: Java capable C registers
09:01: native capable D is enabled
09:02: Java incapable A registers
09:03: native incapable B is enabled
```

If a class is loaded **after 09:03**, its transformation order is still:

```text
A → B → C → D
```

The timeline is only a hypothetical scenario. This does not mean a newly registered transformer can retroactively receive a **class load event that already occurred**. A previously loaded class needs an appropriate update event, and during an update the groups follow their own rules.

### When Multiple Transformers Are in the Same Group

If Java incapable A1 registers before Java incapable A2, then A1 receives the bytes before A2. Both belong to **group 1**. If Java capable C registers before both A1 and A2, it still runs **after all of group 1 and group 2**.

Transformations are not necessarily commutative:

```text
A(B(originalBytes)) may differ from B(A(originalBytes))
```

One agent inserting a probe at method entry and another agent writing a wrapper can produce different results if their order is swapped. Therefore, knowing the chain is a prerequisite when analyzing an instrumented class.

## 3. Two Classification Dimensions: Java/Native and Incapable/Capable

### Java Transformers

`ClassFileTransformer` is an interface in the `java.instrument` module. A Java agent obtains `Instrumentation` via `premain` at startup or `agentmain` when the JVM allows dynamic agent loading. Registration methods:

```java
// Syntax in agent code with Instrumentation inst and transformer t:
inst.addTransformer(t);        // Group 1, defaults to false
inst.addTransformer(t, false); // Group 1
inst.addTransformer(t, true);  // Group 3
```

**Capable** here means the transformer **is called again when a class is retransformed**. It does not mean the transformer always returns new bytes, does not mean it runs before other transformers, and does not guarantee that every class in the JVM can be updated.

### Native JVMTI Transformers

A native agent can request the `ClassFileLoadHook` event callback in JVMTI. In the callback, it receives the current class data and can provide replacement class data.

A JVMTI environment is classified as:

- **Incapable** if it **did not yet have the** `can_retransform_classes` **capability** at the time `ClassFileLoadHook` was first enabled in that environment.
- **Capable** if it **already had the** `can_retransform_classes` **capability** before the hook was first enabled.

This is a constraint on **when the capability is possessed**. You must not assume that an environment that enabled the hook in incapable mode will automatically switch to capable just because it tries to acquire the capability later.

In native C/JVMTI, the configuration idea is:

```c
// Illustrative C code; omits bootstrap and error handling.
jvmtiCapabilities capabilities = {0};
capabilities.can_retransform_classes = 1;
(*jvmti)->AddCapabilities(jvmti, &capabilities);

// After verifying success, register ClassFileLoadHook,
// and only then enable JVMTI_EVENT_CLASS_FILE_LOAD_HOOK.
```

This is **not a standalone C program**. A complete native agent also needs `Agent_OnLoad`, `GetEnv`, `SetEventCallbacks`, `SetEventNotificationMode`, JVMTI-allocated memory management, error codes, and building a library for the operating system. This lesson focuses on the **grouping rules**, not a full JVMTI agent implementation.

**Important:** Java code cannot create the two native groups simply by calling `Instrumentation.addTransformer`. Those two groups belong to the JVMTI mechanism; the Java example later only directly verifies group 1 and group 3.

## 4. Three Event Types: Class Load, Redefine, and Retransform

Transformers can participate in events related to the JVM creating/updating a class definition:

| Event | Source of Input Bytes | Groups 1 and 2 | Groups 3 and 4 |
| --- | --- | --- | --- |
| **Initial class load** | Bytes supplied to define the new class | Callback if applicable | Callback if applicable |
| **`redefineClasses`** | New class bytes provided by the caller | Callback if applicable | Callback if applicable |
| **`retransformClasses`** | Initial bytes of the current definition, with incapable results reapplied | **No callback invoked**; reuse previous result | **New callback invoked** |

During initial class load or redefine, the logical chain is:

```text
initial bytes
   → [1] Java incapable (callback)
   → [2] native incapable (callback)
   → [3] Java capable (callback)
   → [4] native capable (callback)
   → verify/apply
```

During retransform:

```text
initial bytes of the current definition
   → [1] reuse Java incapable output, NO callback
   → [2] reuse native incapable output, NO callback
   → [3] Java capable, NEW callback
   → [4] native capable, NEW callback
   → verify/apply
```

The phrase "callback if applicable" means the transformer/event was registered/enabled at the relevant time and the JVM can process that class. Registering a transformer after a class has already loaded does not immediately replay the old class load event.

### Why Are Redefine and Retransform Different?

`Instrumentation.redefineClasses(ClassDefinition...)` takes **new class-file bytes** from the calling tool. The JVM feeds the new bytes into the chain and invokes the appropriate transformer groups again, including incapable ones.

`Instrumentation.retransformClasses(Class<?>...)` does not take a new `byte[]` passed in by the caller. The JVM starts from the initial bytes of the current definition, restores the previous incapable transformations, and then invokes capable ones again. If the class has previously been redefined, the initial bytes used for subsequent retransforms correspond to the most recent redefinition per JVM rules.

Therefore:

```text
redefine    = new bytes from caller + all 4 groups receive callbacks
retransform = initial bytes + reuse first 2 groups + last 2 groups receive callbacks
```

You should not refer to both operations by a single generic name like "reload class" and assume the same callback order.

## 5. What Does "Reusing Output" Actually Mean?

Suppose the `OrderService` class initially has bytes `B0`. During load:

```text
B0
 ├─ A (Java incapable)    → B1, with coverage probe
 ├─ B (native incapable)  → B2, with additional metadata
 ├─ C (Java capable)      → B3, with trace probe version 1
 └─ D (native capable)    → B4, with sample probe version 1
```

Later, agents C/D change their policy. When `retransformClasses` occurs:

```text
initial bytes of the class
 ├─ A: reuse B1, do not call A.transform again
 ├─ B: reuse B's transformation, do not send a new hook to B
 ├─ C: call transform anew, may produce trace version 2
 └─ D: send a new hook, may produce sample version 2
      → new class bytes if valid
```

A/B **are not removed from the class**. Their output is **reapplied as-is** by the JVM, without requiring recomputation. If A inserted coverage bytecode, the coverage effect continues to exist across a successful retransformation, unless another layer produces a transformation that alters that effect.

This is why you should not read logs like this:

> "I don't see logs from the coverage transformer during the retransform pass, so the coverage probe must have disappeared."

That conclusion is wrong: having no new callback from groups 1/2 is **standard behavior**.

### It Does Not Take the Final Bytes and Append Code Indefinitely

Wrong model:

```text
WRONG: B4 → A → B → C → D → B8 → A → ...
```

The correct model starts from the **initial class-file bytes**, then reapplies the incapable part and invokes the capable part again. This prevents automatically duplicating every transformation just because retransform is called multiple times.

However, if a capable transformer does not recognize bytes that another group already instrumented with a probe and creates another wrapper with the same meaning, the system can still double-measure. "Starting from initial bytes" does not replace designing transformers that can cooperate.

### Are "Initial Bytes" Always Equal to the `.class` File on Disk?

Not necessarily. The JDK states that the input bytes for retransformation **may differ in binary details** from the original bytes passed to `ClassLoader.defineClass` or a redefine call. The constant pool may be reorganized, some attributes may differ or be missing, and method ordering may change where order is not significant.

Therefore, you should not rely on `Arrays.equals(bytes, Files.readAllBytes(classPath))` as the sole criterion. When analysis is needed, look at **semantics, class structure, and valid bytecode**, rather than requiring every offset to stay identical.

## 6. Callback Rules and Bytes at Each Layer

The Javadoc describes transformer chaining: if the first callback returns a new `byte[]` array, the next callback receives that output in `classfileBuffer`. If it returns `null`, there is no change at that layer.

Hypothetical example:

```text
T1 receives B0, returns B1.
T2 receives B1, returns null.
T3 receives B1, returns B3.
```

The output after T2 **is B1**, not B0. A Java transformer must treat the input `classfileBuffer` as **read-only**. To make a change, it must create a new byte array containing a well-formed class file; it must not mutate the callback's input in place.

### What If a Transformer Throws an Exception?

If `transform(...)` throws an uncaught exception, per the Java transformer contract, the JVM still invokes subsequent transformers and continues attempting to load/redefine/retransform. For that layer, an exception has the same effect as **returning `null`**. `IllegalClassFormatException` can be used to report a malformed input class file for diagnostics; do not use an exception as a "guaranteed stop button" for the entire chain.

Conversely, if a callback returns **invalid bytes**, the JVM may reject the class definition/update at the verify/apply step, after the callbacks of all layers have run. A log line saying "transform succeeded" **does not prove** that the class was installed successfully.

### What Does a `redefine` or `retransform` Class Look Like in the Callback?

In Java `ClassFileTransformer`:

- `classBeingRedefined == null` for initial class load.
- `classBeingRedefined != null` when the callback is processing a **redefine or retransform**.

This parameter **does not distinguish** between the two update operations on its own. If a lab only calls retransform, we know a callback with an existing class came from that operation **because of the program flow**, not because the JVM passes a separate `isRetransform` flag.

## 7. Checking Capabilities Before Registering a Capable Transformer

A Java agent registering in capable mode should check:

```java
if (!instrumentation.isRetransformClassesSupported()) {
    throw new IllegalStateException(
            "Retransformation unavailable on this JVM/configuration");
}
instrumentation.addTransformer(myTransformer, true);
```

The snippet above is **illustrative inside an agent** that already has `Instrumentation instrumentation` and `ClassFileTransformer myTransformer`.

For an agent JAR launched with `-javaagent`, the manifest needs:

```text
Premain-Class: MyAgent
Can-Retransform-Classes: true

```

`MyAgent` here is an example class name, not the lab's class name. `Can-Retransform-Classes: true` is a necessary condition for the JVM to consider the agent as requesting the capability; the JVM itself must also support it. If `isRetransformClassesSupported()` is false, calling `addTransformer(t, true)` may throw `UnsupportedOperationException`.

In addition to the JVM-wide capability, before modifying a specific class you must check:

```java
if (!instrumentation.isModifiableClass(targetClass)) {
    throw new IllegalArgumentException("Target class cannot be modified");
}
instrumentation.retransformClasses(targetClass);
```

These two lines are understood in the context of an agent that has `targetClass`. `isModifiableClass` and `isRetransformClassesSupported` ask **two different things**. `int.class` and array classes are not modifiable; other special classes may also have restrictions.

You should also distinguish `isRedefineClassesSupported()` (redefine capability) from `isRetransformClassesSupported()` (retransform capability). Incapable transformers are still invoked during appropriate **redefine** passes.

## 8. Java 17+ Hands-On Lab: Registering Capable First, Yet Callback Runs Later

We will build a Java agent that registers **capable first**, then **incapable second**. When the class is loaded, the incapable callback must be invoked before the capable one according to group ordering. After retransform, only the capable callback is invoked again.

To focus on verifying the ordering, **both transformers return `null`**: no bytecode is modified. This is an experiment on **events and callback order**, not a demo of actual probe insertion.

### 8.1. File Structure

```text
transform-order-demo/
├── OrderAgent.java
├── WatchedTarget.java
├── DemoApp.java
└── agent.mf
```

**File `WatchedTarget.java`:**

```java
public final class WatchedTarget {
    public String value() {
        return "OK";
    }
}
```

**File `OrderAgent.java`:**

```java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;
import java.security.ProtectionDomain;

public final class OrderAgent {
    private static Instrumentation instrumentation;

    public static void premain(String options, Instrumentation inst) {
        instrumentation = inst;
        boolean capable = inst.isRetransformClassesSupported();
        System.out.println("agent: retransform=" + capable);

        if (!capable) {
            throw new IllegalStateException(
                    "This lab requires retransform capability");
        }

        // Register capable first to observe ordering by GROUP.
        inst.addTransformer(logger("capable"), true);
        inst.addTransformer(logger("incapable"), false);
        System.out.println("agent: registered=capable-then-incapable");
    }

    private static ClassFileTransformer logger(String label) {
        return new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    Module module,
                    ClassLoader loader,
                    String className,
                    Class<?> classBeingRedefined,
                    ProtectionDomain domain,
                    byte[] classfileBuffer) {

                if ("WatchedTarget".equals(className)) {
                    String phase = classBeingRedefined == null
                            ? "initial" : "existing";
                    System.out.println(
                            "transform: " + label + " " + phase);
                }
                return null; // Only record the callback, do not modify bytecode.
            }
        };
    }

    public static void retransform(Class<?> target)
            throws UnmodifiableClassException {
        if (instrumentation == null) {
            throw new IllegalStateException("Agent did not start");
        }
        if (!instrumentation.isModifiableClass(target)) {
            throw new IllegalStateException("Target not modifiable");
        }
        instrumentation.retransformClasses(target);
    }
}
```

**File `DemoApp.java`:**

```java
public final class DemoApp {
    public static void main(String[] args) throws Exception {
        System.out.println("app: first load");
        Class<?> type = Class.forName("WatchedTarget");

        Object instance = type.getDeclaredConstructor().newInstance();
        System.out.println(
                "app: value=" + type.getMethod("value").invoke(instance));

        System.out.println("app: retransform");
        OrderAgent.retransform(type);

        System.out.println(
                "app: value=" + type.getMethod("value").invoke(instance));
    }
}
```

`Class.forName("WatchedTarget")` triggers loading of the target class **after** `premain` has registered the transformers. The lab intentionally uses a class name string to avoid a static type reference before that point. After creating the object, the program asks the JVM to retransform **that same class**.

**File `agent.mf`:**

```text
Manifest-Version: 1.0
Premain-Class: OrderAgent
Can-Retransform-Classes: true

```

Make sure the manifest ends with a newline, ideally with a blank line terminating the section.

### 8.2. Compile and Run

Bash commands in the directory containing the four files:

```bash
mkdir -p out
javac -encoding UTF-8 -d out OrderAgent.java WatchedTarget.java DemoApp.java
jar --create --file order-agent.jar --manifest agent.mf -C out .
java -javaagent:order-agent.jar -cp out DemoApp
```

Equivalent on Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path out | Out-Null
javac -encoding UTF-8 -d out OrderAgent.java WatchedTarget.java DemoApp.java
jar --create --file order-agent.jar --manifest agent.mf -C out .
java -javaagent:order-agent.jar -cp out DemoApp
```

To keep the number of files small, the JAR here also includes the demo classes; in real applications, package the agent separately. `-cp out` ensures `DemoApp` and `WatchedTarget` can be found on the class path. The experiment uses Java 17+ and a common JVM that supports retransformation, such as HotSpot/OpenJDK with the capability enabled.

### 8.3. Expected Stdout

```text
agent: retransform=true
agent: registered=capable-then-incapable
app: first load
transform: incapable initial
transform: capable initial
app: value=OK
app: retransform
transform: capable existing
app: value=OK
```

Explanation:

1. `premain` registers **capable before incapable**.
2. When `WatchedTarget` is loaded, the JVM still invokes **incapable initial before capable initial**. Group 1 precedes group 3.
3. When `retransformClasses` is called, the JVM **does not invoke** the incapable transformer; the previous result is reused. `capable existing` appears.
4. `WatchedTarget.value()` still returns `"OK"` because both transformers return `null`. A callback being invoked **does not mean** the bytes changed.

There are no groups 2/4 in stdout because the lab does not install a native JVMTI agent. Do not infer native output from the Java example; native rules must be verified directly with JVMTI or by reading the specification.

If `isRetransformClassesSupported()` is false, the agent stops with an error message in `premain`, and you will **not** see the full expected output. If the class is not modifiable, the check in `retransform` proactively rejects it; this is a capability/target error, not a group-ordering error.

### 8.4. Observing Order **Within** a Group

If you register two additional incapable transformers in order:

```java
// Illustrative code snippet placed inside premain:
inst.addTransformer(logger("incapable-A"), false);
inst.addTransformer(logger("incapable-B"), false);
```

When a new class is loaded, `incapable-A` receives the callback before `incapable-B` **within the same group 1**. Both of these transformers still run before **every** capable transformer in group 3, even if the capable one was registered earlier.

### 8.5. Why Not Use `return classfileBuffer` in the Example?

To demonstrate a callback without changing bytes, `return null` has the clearest meaning. The Javadoc requires not modifying the input array; if creating a real transformation, create a **new array** containing a valid class file and return that array. Do not use a callback experiment to conclude that code has been instrumented.

## 9. Illustrating All Four Groups When a Native Agent Is Present

Suppose native JVMTI environments B (incapable) and D (capable) also listen to `ClassFileLoadHook` for `WatchedTarget`. On load:

```text
Input ClassFile bytes
  │
  ├─ 1. Java incapable A: callback; adds coverage
  │
  ├─ 2. Native incapable B: callback; adds metadata
  │
  ├─ 3. Java capable C: callback; adds trace v1
  │
  └─ 4. Native capable D: callback; adds sample v1
          ↓
     Class definition v1
```

After a successful `retransformClasses` call:

```text
Initial ClassFile bytes of the current definition
  │
  ├─ 1. Java incapable A: reuses coverage; NO callback
  │
  ├─ 2. Native incapable B: reuses metadata; NO callback
  │
  ├─ 3. Java capable C: callback; produces trace v2
  │
  └─ 4. Native capable D: callback; produces sample v2
          ↓
     Class definition v2
```

**This is a logical simulation, not the stdout of the Java program in section 8.** Actual bytecode output depends on the agents and class contents.

Suppose later a tool calls `redefineClasses` with new bytes. Then **all four groups** (if still registered and applicable to the class) receive new callbacks in the order A → B → C → D. That is a critical distinction when investigating why logs from native/Java incapable transformers do not appear after a specific operation.

### Returning `null` and Multi-Layer Coordination

Suppose A creates a coverage probe, B keeps it unchanged, C adds tracing, and D keeps it unchanged. The resulting chain:

```text
B0 ─ A → B1 ─ B(null) → B1 ─ C → B3 ─ D(no change) → B3
```

You cannot say "B returned null so coverage was removed"; B simply contributed no new changes. If D makes no changes, the final bytes remain C's output.

## 10. Limitations of Retransformation and Implications for Instrumentation

**Capable** is not a promise that every class edit is valid. `retransformClasses` has the following conditions:

- The JVM/agent must support the capability; a Java agent requires `Can-Retransform-Classes: true` at startup via the appropriate manifest mechanism.
- The class must be modifiable. Primitive types and array classes are not modifiable; the JVM may also disallow modifying other kinds of classes.
- The new class bytes must satisfy **legal redefinition** requirements. You may not arbitrarily add/remove/rename fields or methods; changing method signatures/modifiers, inheritance, or structural attributes is forbidden. Replacing a **method body** appropriately is usually the target of instrumentation.
- Callbacks are invoked during processing prior to verify/apply. A transformer finishing its log does not confirm that the new class has been installed.
- `retransformClasses` does not re-run the class initializer, does not reset static fields, and does not make existing objects disappear.
- Stack frames currently executing the old version of a method may continue with the old bytecode; new calls use the new definition after the JVM applies it successfully.

Installation can fail due to `UnmodifiableClassException`, malformed class bytes, or a platform limitation. For a request to retransform multiple classes, the operation must be handled according to the atomic semantics described by JDK/JVMTI; do not treat an individual callback as proof that all classes have changed.

### Do Not Confuse the Three Capabilities

| API | Question |
| --- | --- |
| `isRetransformClassesSupported()` | Does the JVM/agent configuration allow **retransform**? |
| `isRedefineClassesSupported()` | Does the JVM/agent configuration allow **redefine**? |
| `isModifiableClass(clazz)` | Is this **specific class** of a kind whose definition can be modified? |

A `true` answer in the table does not replace the other two questions. Native JVMTI also has its own capabilities on the corresponding environment. Do not assume "there is a Java capable transformer" means a native capable hook is definitely enabled.

## 11. Common Implementation and Log-Reading Mistakes

### Mistake 1: Java transformers always run before native ones

False. **Native incapable (group 2)** comes before **Java capable (group 3)**. Check all four groups.

### Mistake 2: `canRetransform=true` gives a transformer top priority

False. Capable belongs to group 3 for Java, after both groups 1 and 2. Earlier/later registration order only compares within the same group.

### Mistake 3: Incapable groups "do not participate" in retransform

False regarding the **result**. The JVM does not invoke callbacks for groups 1/2, but it **replays their previous output**. If a coverage probe is still in the bytecode, it still consumes CPU at runtime.

### Mistake 4: `redefineClasses` also skips incapable transformers

False. With redefine, both incapable and capable transformers are invoked again in group order, based on the bytes from `ClassDefinition`.

### Mistake 5: Returning `null` loses all previous changes

False. `null` only means no change at the **current layer**. Chaining still preserves the results of earlier layers.

### Mistake 6: `classBeingRedefined != null` proves the callback is from retransform

False. Both redefine and retransform pass an existing class. You need to correlate the operation requested by the tool with logs from the orchestration layer.

### Mistake 7: `removeTransformer` immediately strips probes from running classes

False. `removeTransformer` affects registration for **subsequent events**; already-installed class bytes have a different lifecycle. Due to multithreaded class loading, callbacks can even arrive after a transformer has been removed. Do not infer that removing an agent/transformer rolls back all classes.

### Mistake 8: Having the capability means any class can be modified

False. You must check the specific class, structural restrictions, and the validity of the class-file bytes.

### Mistake 9: Throwing an exception in a transformer blocks subsequent transformers

False under the Java callback contract: the JVM still calls the next ones, and the behavior of the throwing layer is equivalent to no transformation. If you want to reject installation, you must understand errors at the verify/apply phase and how the calling operation handles them.

### Mistake 10: The Java `native` keyword is a native JVMTI transformer

False. "Native" in the diagram refers to an agent using JVMTI `ClassFileLoadHook`, not a method with the `native` modifier, a JNI wrapper, or a regular `System.loadLibrary`.

## 12. Multi-Agent Chain Design Checklist

1. **Identify target classes:** use internal class name, loader, module, and JDK version, not just simple class name.
2. **List transformers by group:** Java incapable, native incapable, Java capable, native capable; know `canRetransform`/JVMTI capabilities clearly.
3. **Record intra-group order:** distinguish Java registration order and JVMTI environment order; do not create a single global timestamp order for everything.
4. **Distinguish events:** class load, redefine, or retransform. For retransform, do not expect callbacks for groups 1/2.
5. **Know the input bytes:** from a new definition, redefine bytes, or initial bytes of the current definition with incapable output reused.
6. **Preserve the transformation contract:** do not mutate the input `classfileBuffer`; return `null` or valid new bytes; handle method signatures, frames, and exception flow properly.
7. **Avoid recursion:** exclude agent/helper classes; be careful with loggers and classloaders called back from `transform`.
8. **Avoid duplicate probes:** recognize each layer's instrumentation, do not count every wrapper/bridge as multiple independent business operations.
9. **Measure cost:** callbacks have transformation cost at load/redefine/retransform; probes installed in bytes have runtime cost on every method invocation.
10. **Verify results:** check `isModifiableClass`, API success, correct bytecode/class loader, and runtime behavior; callback logs alone are not enough.
11. **Plan for recovery:** removing a transformer does not automatically restore classes; have a valid update strategy or restart with a consistent configuration.
12. **Test compatibility:** test both the JVM/JDK and the agent combination in the target environment; a chain with an added JVMTI native agent can change the bytes fed into Java capable transformers.

### A Useful Diagnostic Log Format

When you control the agent code, log at minimum:

```text
class=<internal-name>
loader=<loader-identity>
event=<load|redefine|retransform known by the orchestration layer>
group=<1|2|3|4>
inputSize=<bytes>
outputSize=<bytes or unchanged>
```

The values in this `text` block are **log field templates**, not actual output. In production, avoid printing full bytecode or sensitive data. If hashing is needed, distinguish byte hashes from semantic equivalence: the JVM may reorganize the constant pool during retransform.

## 13. Self-Check Questions

**1.** A Java capable transformer registers at 09:00, and a Java incapable transformer registers at 09:05. A new class loads at 09:10; which runs first?  
**Answer:** Java incapable, because group 1 comes before group 3.

**2.** Native incapable versus Java capable: which group comes first?  
**Answer:** Native incapable is group 2, which comes before Java capable in group 3.

**3.** A class was instrumented by a Java incapable transformer. During retransform, its callback does not run. Is the instrumentation effect lost?  
**Answer:** It is not automatically lost. The JVM reuses the incapable transformer's result from the previous load/redefine.

**4.** During `redefineClasses`, do incapable groups receive callbacks?  
**Answer:** Yes, if still registered/applicable, because redefine feeds new bytes into the chain and differs from retransform.

**5.** Which overload is `addTransformer(t)` equivalent to?  
**Answer:** `addTransformer(t, false)`.

**6.** A native `ClassFileLoadHook` is enabled before possessing `can_retransform_classes`; will the environment later belong to group 4?  
**Answer:** No, per JVMTI classification rules; the capability must be held before **the hook is first enabled** for the environment to be considered capable.

**7.** Does `transform` receive bytes that passed through earlier layers or always the original ones?  
**Answer:** It receives the current bytes in the chain; the output of the previous layer is the input to the next layer.

**8.** Does `retransformClasses` reinitialize static fields?  
**Answer:** No. The class initializer does not re-run just because of retransform.

**9.** Is `classBeingRedefined != null` enough to distinguish `redefine` from `retransform`?  
**Answer:** No. Both pass an existing class.

**10.** Why doesn't the lab prove native ordering?  
**Answer:** Because it only uses Java `ClassFileTransformer` and does not install a JVMTI `ClassFileLoadHook`; native requires a separate agent/capability.

## 14. Authoritative References

- [JDK 21 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): the four groups and application order, chaining, `null`/exception handling.
- [JDK 21 — `Instrumentation`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): transformer registration, capabilities, retransform, and redefine.
- [JDK 21 — package `java.lang.instrument`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): agent startup, manifest, and contexts for receiving `Instrumentation`.
- [JDK 21 — JVM Tool Interface (JVMTI)](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html): `ClassFileLoadHook`, `can_retransform_classes`, hook enablement timing, and native ordering.

**Key Takeaway:** **1. Java incapable → 2. native incapable → 3. Java capable → 4. native capable.** During **load/redefine**, relevant groups are invoked in this order; during **retransform**, the two incapable groups **have no new callbacks, yet their previous results are still reapplied**, and then the two capable groups run. Always consider **event type**, **group order**, and **class bytes source** before analyzing an instrumentation result.