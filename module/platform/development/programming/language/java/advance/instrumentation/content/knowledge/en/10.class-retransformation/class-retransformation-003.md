# Manifest Conditions and JVM Capabilities Before Retransformation

**Retransformation** is the ability to ask the JVM to re-run the bytecode transformation chain for an **already loaded** class, via `Instrumentation.retransformClasses(Class<?>...)`. This is an **optional** capability, not a default right of every Java agent. Before using it, the agent must satisfy **two capability-granting conditions**: **the agent's JAR declares the need for retransformation in its manifest** and **the current JVM supports that capability**. Even when both conditions are met, the specific class must still be **modifiable**, and the resulting bytecode must be valid within retransform constraints.

This lesson focuses on the `Can-Retransform-Classes` manifest attribute, checking `isRetransformClassesSupported()` and `isModifiableClass(...)`, registering a `ClassFileTransformer` with `canRetransform=true`, errors to prevent before calling the API, and a runnable Java 17+ example with **two agent JARs having different manifests**.

## 1. Three Tiers of Conditions to Distinguish

Do not conflate the following three questions into one:

| Tier | Question | How to Check |
| --- | --- | --- |
| **Agent declaration** | Does the agent request retransformation permission in the JAR manifest? | `Can-Retransform-Classes: true` in the **agent JAR's manifest**. If missing or not `true`, it defaults to `false`. |
| **JVM/configuration capability** | Does the JVM allow retransformation for the declared agent? | `Instrumentation.isRetransformClassesSupported()`; this is a **runtime** check, not guessing by JVM name. |
| **Class modifiability** | Can this specific loaded class have its definition replaced? | `Instrumentation.isModifiableClass(targetClass)`; must still be checked even if the overall capability is `true`. |

Summary:

```text
agent.jar/META-INF/MANIFEST.MF
    └─ Can-Retransform-Classes: true ?
             │
             ├─ no  → isRetransformClassesSupported() = false
             │
             └─ yes
                  │
                  v
             Does the JVM support this capability?
                  │
                  ├─ no  → isRetransformClassesSupported() = false
                  │
                  └─ yes → isRetransformClassesSupported() = true
                              │
                              v
                  Is targetClass loaded and modifiable?
                              │
                              ├─ no  → do not retransform that class
                              │
                              └─ yes → can call retransformClasses(...)
                                        │
                                        v
                               Transformer runs/bytes are verified;
                               result must still be valid and within constraints.
```

**A very common point of confusion:** `isModifiableClass(clazz) == true` **does not prove** `isRetransformClassesSupported() == true`. According to the API, the two values are **independent**: `isModifiableClass` indicates whether a class can be modified by the redefine/retransform mechanism, while each capability must still be checked separately.

## 2. Manifest: Declaring Retransformation Permission in the Right Place

### 2.1. Required Fields for a Startup Agent

For an agent launched with `-javaagent`:

```text
Manifest-Version: 1.0
Premain-Class: demo.retransform.ProbeAgent
Can-Retransform-Classes: true

```

- `Premain-Class`: fully qualified class name containing `public static void premain(String, Instrumentation)` or `premain(String)`.
- `Can-Retransform-Classes: true`: **requests the capability** for the agent; by itself it does not guarantee that every JVM supports it.
- The trailing blank line in the example ensures the manifest is parsed cleanly. The attributes must be in the `META-INF/MANIFEST.MF` file **inside the actual agent JAR**, not just in a text file sitting next to the JAR.

How to run:

```bash
java -javaagent:agent-on.jar -cp out demo.retransform.App
```

The JVM reads the manifest, starts the agent, and passes `Instrumentation` to `premain`. Upon receiving `Instrumentation`, the agent must **check the capability** before registering a retransformation-capable transformer or calling retransform.

### 2.2. Missing, Incorrect, or Non-`true` Values

Example of a manifest that **does not declare** the capability:

```text
Manifest-Version: 1.0
Premain-Class: demo.retransform.ProbeAgent

```

According to the specification, `Can-Retransform-Classes` is an **optional** attribute; **it defaults to `false`**. Values other than `true` are also treated as `false`. For example:

| Manifest | Meaning |
| --- | --- |
| `Can-Retransform-Classes: true` | Agent requests retransformation; still requires JVM support. |
| `Can-Retransform-Classes: TRUE` | Boolean value is case-insensitive; equivalent to `true`. |
| `Can-Retransform-Classes: false` | Does not request retransformation. |
| No `Can-Retransform-Classes` line | Defaults to `false`. |
| `Can-Retransform-Classes: yes` | Not `true`; treated as `false`. |

You **cannot** enable the capability merely by calling `addTransformer(transformer, true)`. The `true` argument here requests **registering a transformer in the retransformation-capable group**; it does not replace the manifest and cannot force the JVM to grant an unsupported capability.

### 2.3. Agent Attached After the JVM Starts

If loading an agent via the Attach API (when the JVM and environment allow it), the JAR must have the `Agent-Class` entry point:

```text
Manifest-Version: 1.0
Agent-Class: demo.retransform.ProbeAgent
Can-Retransform-Classes: true

```

The agent class needs `public static void agentmain(String, Instrumentation)` (or the single-parameter form) when dynamically loaded. `Can-Retransform-Classes` remains a **capability request** of the agent JAR. If a JAR supports **both startup modes**, the manifest can declare both `Premain-Class` and `Agent-Class`, and the JVM selects the entry point based on **how the agent is loaded**.

You can distinguish them as follows:

- **`-javaagent:...`** → `Premain-Class` and `premain`.
- **Attach API `loadAgent(...)`** → `Agent-Class` and `agentmain`, if the attach mechanism is supported/permitted.
- **`Can-Retransform-Classes`** → requests the capability for both paths above; does not determine which entry point is called.

Whether **dynamic agent loading** is permitted (attach policy, OS permissions, JVM flags) is a separate question from **retransformation capability**. A successful attach does not imply retransform is available; having retransform capability available does not guarantee external attach is permitted either.

### 2.4. Do Not Confuse with `Can-Redefine-Classes`

The two manifest entries are **independent**:

| Manifest | Corresponding API | Meaning |
| --- | --- | --- |
| `Can-Retransform-Classes: true` | `isRetransformClassesSupported()`, `retransformClasses(...)`, `addTransformer(..., true)` | Requests re-running the transformer chain on currently loaded classes. |
| `Can-Redefine-Classes: true` | `isRedefineClassesSupported()`, `redefineClasses(...)` | Requests replacing class definitions from a caller-supplied `ClassDefinition`. |

**Both** may be needed if the agent performs both types of operations. However, declaring `Can-Redefine-Classes: true` **does not replace** `Can-Retransform-Classes: true`. Similarly, a manifest with a valid `Premain-Class` **does not automatically enable** retransform.

## 3. Formal Checks Using `Instrumentation`

Safe pattern inside `premain`/`agentmain`:

```java
// Snippet inside an agent class, not a standalone program.
public static void configure(Instrumentation inst,
                             ClassFileTransformer transformer,
                             Class<?> targetClass)
        throws UnmodifiableClassException {

    if (!inst.isRetransformClassesSupported()) {
        System.out.println("Retransformation unavailable");
        return;
    }

    if (!inst.isModifiableClass(targetClass)) {
        System.out.println("Target class not modifiable");
        return;
    }

    inst.addTransformer(transformer, true);
    inst.retransformClasses(targetClass);
}
```

You need to import `java.lang.instrument.Instrumentation`, `ClassFileTransformer`, and `UnmodifiableClassException`. This snippet **illustrates the order of checks**; a production agent also needs to coordinate re-registration, exception handling, protecting transformer callbacks, and cleanup.

There are two key API points:

1. `isRetransformClassesSupported()` indicates whether **the current JVM configuration for the agent that received Instrumentation** supports retransform. According to the Java 17 API, within a single invocation of a JVM, repeated calls on this same configuration return **the same result**. There is no need to re-query on every bytecode event just to see if the flag spontaneously changes from `false` to `true`.
2. `isModifiableClass(target)` checks **the specific class**. Primitive classes such as `int.class` and array classes such as `String[].class` are **not modifiable**. Certain other classes may also be marked unmodifiable by the JVM. The result of `isModifiableClass` is not a substitute check for the capability.

### 3.1. When `isRetransformClassesSupported() == false`

If you call:

```java
// Illustrative snippet in an agent that already has inst and transformer:
inst.addTransformer(transformer, true);
```

without the capability, the API throws `UnsupportedOperationException`. If the agent skips the check and calls `inst.retransformClasses(Target.class)`, that call can also throw `UnsupportedOperationException` because the configuration does not allow retransform.

If the agent still needs to observe **future loaded classes**, it can register:

```java
// Can register a transformer that does not support retransformation.
inst.addTransformer(transformer, false);
```

Registering with `false` allows callbacks in applicable load/redefine cases, but does not cause that transformer to be **called again** during retransform. Choosing `false` is a meaningful operating mode, not a “failed registration”.

### 3.2. When the Capability Is `true` but a Class Is Not Modifiable

Every retransform call must consider the **target class**. `retransformClasses(...)` throws `UnmodifiableClassException` if a specified class cannot be modified. Therefore, **do not scan all loaded classes and pass the unfiltered list** to retransform.

A workflow for multiple classes:

```java
// Illustrative code in an agent; not a standalone program.
if (inst.isRetransformClassesSupported()) {
    Class<?>[] candidates = inst.getAllLoadedClasses();
    java.util.List<Class<?>> allowed = new java.util.ArrayList<>();

    for (Class<?> candidate : candidates) {
        if (inst.isModifiableClass(candidate)) {
            allowed.add(candidate);
        }
    }

    if (!allowed.isEmpty()) {
        inst.retransformClasses(allowed.toArray(Class<?>[]::new));
    }
}
```

This pattern **only illustrates capability filtering**. A real-world agent must filter further by **package/module/class loader and instrumentation purpose**, limit batch sizes, avoid the agent's own classes, and handle transformers that are unsafe for bootstrap/system classes. Retransforming every modifiable class merely because the API allows it **is not a recommended strategy**.

## 4. Runnable Example: Two Manifests, the Same Agent, and a Matching JVM

This is a **Java 17+** experiment with no external libraries. We package **the exact same agent classes** into **two JARs** but use different manifests:

- **`agent-on.jar`** has `Can-Retransform-Classes: true`.
- **`agent-off.jar`** **does not have** the `Can-Retransform-Classes` line, meaning it defaults to `false`.

The program loads `Target`, checks the capability, and then attempts `retransformClasses(Target.class)` when eligible. The transformer only **prints a log and returns `null`**, so Target's behavior does not change. Thus, the output separates **the ability to re-invoke the callback** from **modifying logic**.

### 4.1. File Structure

```text
retransform-demo/
├── src/
│   └── demo/
│       └── retransform/
│           ├── ProbeAgent.java
│           ├── ProbeTransformer.java
│           ├── Target.java
│           └── App.java
├── agent-on.mf
└── agent-off.mf
```

The four Java files below form a complete sample program with consistent class and package names.

### 4.2. `src/demo/retransform/ProbeAgent.java`

```java
package demo.retransform;

import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;

public final class ProbeAgent {
    private static Instrumentation instrumentation;

    private ProbeAgent() {}

    public static void premain(String options, Instrumentation inst) {
        instrumentation = inst;
        boolean supported = inst.isRetransformClassesSupported();
        System.out.println("[agent] retransformationSupported=" + supported);
        if (supported) {
            inst.addTransformer(new ProbeTransformer(), true);
            System.out.println("[agent] registered canRetransform=true");
        } else {
            System.out.println("[agent] skip capable transformer");
        }
    }

    public static void tryRetransform(Class<?> type)
            throws UnmodifiableClassException {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("No startup agent");
        }

        boolean modifiable = inst.isModifiableClass(type);
        System.out.println("[app] modifiable=" + modifiable);
        if (!inst.isRetransformClassesSupported() || !modifiable) {
            System.out.println("[app] skip retransform");
            return;
        }

        inst.retransformClasses(type);
        System.out.println("[app] retransform complete");
    }
}
```

Explanation:

1. The JVM calls `premain` **before the application `main`**.
2. If the capability is missing, the agent **does not** attempt `addTransformer(..., true)`. It prints a message and allows the application to continue.
3. When `true`, the transformer is registered **before** the application requests loading `Target`.
4. `tryRetransform(...)` independently checks **JVM capability** and **class modifiability** before calling the API.
5. The experiment uses the `ProbeAgent` class as a direct call channel from the application for brevity. In a real tool, an agent typically has a control API, MBean, or its own orchestration thread rather than forcing the application to import the agent class.

`instrumentation` is set in `premain` and then read in the same process during the demo run. If you copy this example into a multi-threaded control design, you must consider synchronization/volatile and lifecycle rather than using an uncontrolled static field across multiple threads.

### 4.3. `src/demo/retransform/ProbeTransformer.java`

```java
package demo.retransform;

import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

public final class ProbeTransformer implements ClassFileTransformer {
    @Override
    public byte[] transform(Module module, ClassLoader loader,
            String className, Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain, byte[] classfileBuffer) {
        if ("demo/retransform/Target".equals(className)) {
            System.out.println("[transform] Target phase="
                    + (classBeingRedefined == null ? "load" : "retransform"));
        }
        return null;
    }
}
```

This is a **no-op byte transformer**. For a new definition, `classBeingRedefined == null`; when retransform is called on an already loaded class, the parameter is non-`null`.

The `ClassFileTransformer` contract on Java 17 also has a five-parameter overload; both overloads have default methods. Therefore, the interface **is not a functional interface** in Java 17 and the class above cannot be replaced with a plain lambda without creating a separate interface.

Do not rely on the `phase=retransform` label as a universal detector for all cases: `classBeingRedefined != null` also occurs during **redefineClasses**. In this specific program we know it is retransform because the code calls `retransformClasses(...)`, not redefine.

### 4.4. `src/demo/retransform/Target.java`

```java
package demo.retransform;

public final class Target {
    private Target() {}

    public static String message() {
        return "original";
    }
}
```

Target is a normal application class. We use it to verify that **the callback occurs for an already loaded class**, without replacing literals or bytecode.

### 4.5. `src/demo/retransform/App.java`

```java
package demo.retransform;

public final class App {
    private App() {}

    public static void main(String[] args) throws Exception {
        System.out.println("[app] first=" + Target.message());
        ProbeAgent.tryRetransform(Target.class);
        System.out.println("[app] second=" + Target.message());
    }
}
```

The first `Target.message()` call ensures `Target` is already loaded before `tryRetransform` is called. If the capability is `true`, the JVM will invoke the transformer **a second time** for Target due to retransform, even though the class does not need to be loaded anew.

### 4.6. The Two Manifest Files

`agent-on.mf`:

```text
Manifest-Version: 1.0
Premain-Class: demo.retransform.ProbeAgent
Can-Retransform-Classes: true

```

`agent-off.mf`:

```text
Manifest-Version: 1.0
Premain-Class: demo.retransform.ProbeAgent

```

Both JARs contain **the exact same agent bytecode**, differing only in the manifest. Keep the trailing newline at the end of each manifest; do not use `Main-Class` in place of `Premain-Class`. In the experiment, the agent JAR contains `ProbeAgent.class` and `ProbeTransformer.class`, while `App`/`Target` are on the application classpath `out`.

### 4.7. Compiling on JDK 17+ and Packaging

From the `retransform-demo/` directory, in **Bash**:

```bash
mkdir -p out

javac --release 17 -d out \
  src/demo/retransform/ProbeAgent.java \
  src/demo/retransform/ProbeTransformer.java \
  src/demo/retransform/Target.java \
  src/demo/retransform/App.java

jar --create --file agent-on.jar --manifest agent-on.mf \
  -C out demo/retransform/ProbeAgent.class \
  -C out demo/retransform/ProbeTransformer.class

jar --create --file agent-off.jar --manifest agent-off.mf \
  -C out demo/retransform/ProbeAgent.class \
  -C out demo/retransform/ProbeTransformer.class
```

Equivalently in **PowerShell**, create the `out` directory and run each command on a single line:

```powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -d out src/demo/retransform/ProbeAgent.java src/demo/retransform/ProbeTransformer.java src/demo/retransform/Target.java src/demo/retransform/App.java
jar --create --file agent-on.jar --manifest agent-on.mf -C out demo/retransform/ProbeAgent.class -C out demo/retransform/ProbeTransformer.class
jar --create --file agent-off.jar --manifest agent-off.mf -C out demo/retransform/ProbeAgent.class -C out demo/retransform/ProbeTransformer.class
```

The `\` in the Bash commands means **line continuation**, not equivalent syntax in PowerShell. The commands use `javac` and `jar` included in the JDK. The `--release 17` option ensures the example's API/source/classfile is Java 17 compatible.

### 4.8. Running with the Manifest ENABLING Retransformation

```bash
java -javaagent:agent-on.jar -cp out demo.retransform.App
```

**Stdout when running on OpenJDK 24.0.2 supporting retransformation:**

```text
[agent] retransformationSupported=true
[agent] registered canRetransform=true
[transform] Target phase=load
[app] first=original
[app] modifiable=true
[transform] Target phase=retransform
[app] retransform complete
[app] second=original
```

Analysis:

- The JVM reads the manifest containing `Can-Retransform-Classes: true`; in the lab environment, `isRetransformClassesSupported() == true`.
- The agent registers `ProbeTransformer` with `true` before the application runs.
- The JVM defines Target: callback with `classBeingRedefined == null` → `phase=load`.
- The application calls `isModifiableClass(Target.class)`: for a simple class in the test JVM, the result is `true`.
- Calling `retransformClasses(Target.class)` causes the transformer to **be called again** with `classBeingRedefined != null` → `phase=retransform`.
- Target still returns `original` because the transformer only returns `null`. **Retransformation can succeed without modifying logic**.

### 4.9. Running with the Manifest NOT Requesting Retransformation

```bash
java -javaagent:agent-off.jar -cp out demo.retransform.App
```

**Stdout on the same OpenJDK 24.0.2:**

```text
[agent] retransformationSupported=false
[agent] skip capable transformer
[app] first=original
[app] modifiable=true
[app] skip retransform
[app] second=original
```

Same JVM implementation and same agent code, but missing the capability line → `isRetransformClassesSupported() == false`. The agent handles this safely by **not registering a `true` transformer and not calling retransform**.

The `[app] modifiable=true` line still appears even though `retransformationSupported=false`. This is direct proof that **`isModifiableClass` must not be used as a substitute for `isRetransformClassesSupported`**.

> The specific output above was verified when compiled with `javac --release 17` and run on **Zulu/OpenJDK 24.0.2**. On a different JVM, capability or modifiability may differ. Treat the stdout as the result **of the lab environment**, not a guarantee that every JVM in the world returns the same booleans.

### 4.10. Inspecting the Manifest Inside the Actual JAR

You can list the JAR contents:

```bash
jar --list --file agent-on.jar
jar --list --file agent-off.jar
```

Inside each JAR, inspect the `META-INF/MANIFEST.MF` entry using a ZIP/JAR viewer, confirming:

- `agent-on.jar` has `Premain-Class` and `Can-Retransform-Classes: true`.
- `agent-off.jar` has `Premain-Class` but **does not** have `Can-Retransform-Classes`.
- Both JARs contain the required entry-point and transformer classes.

**Do not** just look at the `agent-on.mf` file outside in the directory and assume the JAR was built from it: in CI/CD systems, a shading/packaging step can accidentally overwrite the manifest.

## 5. Order of Checks in a Production Agent

A safe decision flow:

```text
Was the agent entry point called by the JVM?
    |
    ├─ no: check manifest entry point, -javaagent, or Attach
    |
    └─ yes: receive Instrumentation
             |
             v
       isRetransformClassesSupported() ?
             |
             ├─ false:
             |   ├─ log capability unavailable
             |   ├─ may observe only future class loads with a false transformer
             |   └─ do not call retransformClasses
             |
             └─ true:
                  |
                  v
              addTransformer(transformer, true)
                  |
                  v
              identify loaded classes to process
                  |
                  v
              isModifiableClass(clazz) ?
                  |
                  ├─ false → skip/log reason
                  |
                  └─ true → retransformClasses(clazz)
                                |
                                v
                         check success or exception
                                |
                                v
                          verify runtime behavior
```

Do not treat a “registered transformer” log as proof that retransform succeeded; registration only sets up the ability to receive callbacks in requested cases. Similarly, a `true` capability does not mean the JVM has automatically called `transform(...)` on all previously loaded classes.

**When you need to process currently loaded classes**, you can use `Instrumentation.getAllLoadedClasses()` to find candidates, but you should restrict by scope, `isModifiableClass`, relevant loaders, and work limits. The list of loaded classes is not a list of classes that all need or are allowed to be instrumented.

## 6. Why `addTransformer(..., true)` and `retransformClasses(...)` Are Two Separate Steps

- `addTransformer(t, true)`: registers **t** so it can receive callbacks when classes are loaded, redefined, and retransformed (if supported by the JVM/configuration).
- `retransformClasses(clazz)`: **instructs** the JVM to re-run the transformation chain for **already loaded classes** at that moment. Without calling this API, registering a `true` transformer **does not retroactively go back in time** to instrument all existing classes.

When the JVM performs a retransform:

1. It starts from the class's base bytes according to JVM rules (related to the most recent load/redefine), not by re-reading the original JAR file on disk by default.
2. For transformers registered with `canRetransform=false`: the JVM **re-applies the bytecode effects previously obtained** during the prior load/redefine; `transform` of this group is **not called again**.
3. For transformers registered with `canRetransform=true`: the JVM calls `transform` again in group order and registration order.
4. The JVM then verifies and applies the new definition if valid.

This is why an earlier agent with `canRetransform=false` can still leave its effects in the bytes being retransformed: **not calling the callback again** does not mean **reverting previous effects**.

Note that the input bytes for a retransform are not necessarily byte-for-byte identical to the bytes originally passed to `ClassLoader.defineClass`: constant pool layout, entry ordering, or certain attributes may differ per the specification. A transformer should parse **the current array** rather than assuming offsets from the old class file.

## 7. Remaining Constraints Even When All Flags Are True

**`isRetransformClassesSupported() == true` and `isModifiableClass(clazz) == true` are necessary conditions, not proof that every bytecode change is valid.**

### 7.1. Cannot Arbitrarily Alter the Class Schema

Per the corresponding JVM TI constraints, retransform generally allows changing **method bodies**, but does not arbitrarily allow:

- Adding, removing, or renaming methods/fields.
- Changing method descriptors/signatures in a way that causes prohibited structural changes.
- Changing inheritance hierarchies, interfaces, or disallowed class structures.

Unsupported actions can cause `UnsupportedOperationException`. Even when only modifying method code, you must keep the class file valid, handling stack map frames, control flow, and a compatible constant pool.

### 7.2. Does Not Automatically Re-Run Static Initializers

Retransformation **does not automatically re-invoke `<clinit>`** or reset static fields. If the class is already initialized, static state remains intact unless the code itself acts otherwise. If a frame is currently executing an old method, the running frame may continue using the old bytecode; new calls use the newly applied definition.

Therefore, do not expect that “calling retransform makes the JVM reset the class to its initial state” or “all threads immediately switch to the new code mid-method”.

### 7.3. Errors Occurring After Passing the Capability Check

Several specified exceptions/errors:

| API / Phase | Possible Error | Meaning |
| --- | --- | --- |
| `addTransformer(t, true)` | `UnsupportedOperationException` | JVM/configuration does not allow retransformation. |
| `retransformClasses(clazz)` | `UnsupportedOperationException` | Lacks capability or the transformation is not supported. |
| `retransformClasses(clazz)` | `UnmodifiableClassException` | Selected class is not modifiable. |
| `retransformClasses(clazz)` | `ClassFormatError`, `UnsupportedClassVersionError`, `LinkageError`, and related errors | Output class is invalid, version is incompatible, or linkage failed. |
| `retransformClasses(null)` or null element | `NullPointerException` | Invalid input. |

By contract, if a `retransformClasses(...)` call for a set of classes fails, **none of the classes in that set are retransformed**. This is helpful for consistency, but does not eliminate the need for logging, error classification, and careful selection of the class batch.

A transformer may throw an exception; per `ClassFileTransformer`, the JVM continues the chain as if that transformer had returned `null`. Hence, **a Java exception inside a transformer is not a reliable mechanism to block all class loading/retransformation**. On the other hand, returning malformed bytes can cause the retransform to fail when the JVM verifies the output.

### 7.4. JVM Environment, Version, and Permissions

- Retransformation is an **optional capability**. Do not hard-code the assumption that every JVM/VM configuration supports it.
- When using the Attach API, whether **an agent can be dynamically loaded** depends on the attach mechanism, permissions, JVM policies, and JDK version; it is distinct from retransform permission. Do not conflate the two problems.
- Module boundaries and class loaders also affect the agent's ability to **link helper classes** or access components to be instrumented. Having retransform capability does not automatically open every encapsulated package.
- For certain special core classes, primitives/arrays, and some VM-defined classes, modification may be rejected. Query `isModifiableClass` instead of guessing from the class name.
- VM capability does not guarantee that other transformers running in the JVM are compatible with your bytecode.

## 8. Multiple Java Agents in the Same JVM

Each **agent JAR** must declare the capability request appropriate for that agent's operations. Do not rely on “agent A already has `Can-Retransform-Classes: true`, so agent B does not need to declare it and is still guaranteed permission”—check the actual `Instrumentation` that the JVM passes to agent B and the actual manifest of each JAR.

Suppose:

```text
java -javaagent:monitor.jar -javaagent:coverage.jar -cp app.jar example.Main
```

The command above is illustrative only; with `-cp app.jar`, the `example.Main` class must actually exist in that JAR/classpath. When both agents instrument the same class:

- The `premain` invocation order follows the `-javaagent` order on the command line, if both start normally.
- **Bytecode transformation order** is also governed by group rules: Java/native and `canRetransform=false/true`; within each group, registration order is preserved.
- During retransform, incapable transformers are not called again, though their existing effects may be reused; capable transformers are called again.
- When one agent has already loaded a class early, a later-registered agent's transformer may miss **the initial definition**. If it has the capability and the class is modifiable, the agent can request a retransform to process it.
- Changing agent order is a way to investigate interactions, **not a substitute for capability checks and idempotent transformer design**.

If the same agent is reloaded or passed multiple times, take care to avoid duplicate transformer registration and self-looping retransforms. A `supported=true` value says nothing about **how many transformers** are participating or whether they can coordinate safely.

## 9. Implementation and QA Checklist

Before deploying retransform into a monitoring tool or profiler:

1. **Verify the actual JAR:** the manifest has `Premain-Class` or `Agent-Class` matching the mechanism and `Can-Retransform-Classes: true`; the JAR file on the server/CI is the right artifact, not a different build.
2. **Verify startup/load:** `premain` or `agentmain` is called successfully; the agent receives `Instrumentation` without missing dependencies or classloader errors.
3. **Log runtime capability:** log `isRetransformClassesSupported()` clearly. If `false`, operate in degraded mode (e.g., only instrument future loads) or fail-fast according to product policy.
4. **Register the right transformer type:** if you want callbacks during retransform, use `addTransformer(t, true)` after the capability has been confirmed. Do not use `false` and expect retransform callbacks.
5. **Select the right classes:** the class is already loaded, `isModifiableClass(clazz)` returns true; filter by package, module, defining loader, and exclude the agent's own classes unless intentionally intervening.
6. **Verify bytecode:** every returned `byte[]` must be valid and obey retransform constraints (unchanged schema); do not mutate the `classfileBuffer` array in place.
7. **Test on target environments:** Java version, JVM vendor, flags, classloaders, number of agents, module system, and security/policy settings may differ from the dev environment.
8. **Observe actual behavior:** after calling `retransformClasses`, verify the expected callback and new behavior if any; do not conclude success solely from a transformer registration log.
9. **Unregister and cleanup:** when stopping the agent, you can call `removeTransformer(t)`. Unregistering **does not automatically revert** code already applied to classes, and in-flight callbacks may still arrive after removal.
10. **Error strategy:** only submit eligible class batches, classify `UnsupportedOperationException`/`UnmodifiableClassException`/class format errors, and clearly define operational behavior when the capability is absent.

Especially in production, do not use `retransformClasses` as a harmless operation to be repeated continuously across the entire JVM. It has overhead, impacts class loading, and can interact with other agents.

## 10. Quick Diagnostic Table

| Symptom | Cause / Remediation |
| --- | --- |
| `isRetransformClassesSupported() == false` on a JVM that seems to support it | Check the **manifest of the running agent JAR**: missing `Can-Retransform-Classes: true` is a common cause. If the manifest is correct, the JVM/configuration may not support it. |
| `isModifiableClass(Target.class) == true` but cannot retransform | `isModifiableClass` is independent of capability; check `isRetransformClassesSupported()` first. |
| `addTransformer(t, true)` throws `UnsupportedOperationException` | Capability was not granted/supported, or manifest flag is invalid. Do not retry infinitely with the same configuration. |
| Only `phase=load` is seen, no callback when already loaded | Check whether `retransformClasses(...)` was called; whether the transformer was registered with `canRetransform=true`. |
| `retransformClasses(...)` throws `UnmodifiableClassException` | Check `isModifiableClass(clazz)` and exclude primitives/arrays/unsupported VM classes. |
| Agent loaded via attach but retransform reports unsupported | Two different mechanisms; check manifest `Agent-Class`, `Can-Retransform-Classes`, and JVM capability. |
| `Can-Redefine-Classes: true` but retransform is false | These are two independent capabilities; add the retransform flag if needed, and the JVM must still support it. |
| Retransform succeeds but application output does not change | Transformer may just return `null` as in the example; or the change did not affect the tested path, or an old frame is still running. |
| Error/VerifyError after retransform callback | Check classfile bytes, stack maps, constant pool, method descriptors, schema constraints, and preceding transformers. |
| First `-javaagent` is supported, second is not | Check the manifest and `Instrumentation` of **each agent**; do not assume the same capability for every agent. |
| Manifest text is correct but runtime is false | Verify the `META-INF/MANIFEST.MF` contents **inside the exact running JAR**; a package/shade step may have overwritten the manifest. |

## 11. Self-Check Questions

**Question 1.** An agent has a valid `Premain-Class` but does not declare `Can-Retransform-Classes`. Is the JVM required to support retransform for the agent?

**Answer:** No. The default manifest value is `false`, so `isRetransformClassesSupported()` returns `false` by contract, even if the JVM implementation has the general capability.

**Question 2.** `isModifiableClass(MyClass.class) == true`. Can `retransformClasses(MyClass.class)` be called immediately?

**Answer:** Not enough. You also need `isRetransformClassesSupported() == true`, a valid loaded class, and resulting bytes that satisfy JVM rules.

**Question 3.** To have a transformer receive callbacks during retransform, is registering with `addTransformer(transformer, false)` sufficient?

**Answer:** No. You must register with `true` when the JVM supports it; the `false` group is not called again during retransformation.

**Question 4.** Can `Can-Redefine-Classes: true` substitute for `Can-Retransform-Classes: true`?

**Answer:** No. `redefineClasses` and `retransformClasses` are two independent capabilities with different purposes.

**Question 5.** If a class is not modifiable and an agent attempts to call retransform, which error is specified?

**Answer:** `UnmodifiableClassException`. The agent should check `isModifiableClass(clazz)` while still handling the exception when calling the API.

**Question 6.** If retransform succeeds and the transformer returns `null`, does the JVM necessarily change the output of `Target.message()`?

**Answer:** No. `null` means no byte modification. The callback may still have been invoked successfully and the class reprocessed, yet behavior remains unchanged.

**Question 7.** Why does the `agent-off.jar` example print `modifiable=true` yet still print `skip retransform`?

**Answer:** Because `isModifiableClass` does not depend on the result of `isRetransformClassesSupported`. The experiment's JVM allows this class to be modifiable, but the agent's manifest did not request retransformation, so the runtime capability is `false`.

**Question 8.** Can `Can-Retransform-Classes` be enabled after the agent has already started simply by editing the manifest file on disk?

**Answer:** No. The manifest is read by the JVM when the agent is loaded and the capability is determined by that configuration; changing the file afterward **does not elevate permissions on the existing `Instrumentation`**. You must redesign the startup/loading process as required, rather than assuming hot-editing the manifest has any effect.

**Question 9.** A `false` transformer is not called again during retransform. Is it guaranteed that its previous effects are gone?

**Answer:** No. According to the Java Instrumentation API, the effects of a retransformation-incapable transformer are re-applied by the JVM from the previous load/redefine.

## 12. Summary and Official Documentation

Before using `retransformClasses`, keep the chain of conditions in mind:

**Manifest `Can-Retransform-Classes: true` → JVM supports `isRetransformClassesSupported()` → specific class `isModifiableClass(clazz)` → register `addTransformer(..., true)` → call `retransformClasses(...)` → verify valid output and actual behavior.**

All three questions—**“did the agent request permission?”**, **“does the JVM support it?”**, and **“is this class modifiable?”**—must be answered. Do not use `Premain-Class`, `Can-Redefine-Classes`, or `isModifiableClass` as substitutes for retransform conditions.

Official references:

1. **Java SE 17 API — `Instrumentation`**: `isRetransformClassesSupported`, `addTransformer`, `isModifiableClass`, `retransformClasses`, and exceptions: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
2. **Java SE 17 API — `java.lang.instrument`**: manifest `Can-Retransform-Classes`, `Premain-Class`, `Agent-Class`, and default `false`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
3. **Java SE 17 API — `ClassFileTransformer`**: callbacks, transformer ordering, `classBeingRedefined` parameter, and `null`/`byte[]` rules: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
4. **JVMTI Specification — `RetransformClasses`**: capability and class modification constraints: https://docs.oracle.com/javase/8/docs/platform/jvmti/jvmti.html#RetransformClasses
5. **Java SE 17 Tool Guide — `java` launcher**: how to use `-javaagent`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html