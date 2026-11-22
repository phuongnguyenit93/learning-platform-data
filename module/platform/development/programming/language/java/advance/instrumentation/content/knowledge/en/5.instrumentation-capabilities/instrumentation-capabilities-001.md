# Manifest capability declarations differ from what the JVM actually supports

## 1. The problem: declaring `true` is not proof that a feature is usable

When packaging a Java agent, you can put attributes like the following in `META-INF/MANIFEST.MF`:

~~~text
Premain-Class: demo.agent.CapabilityAgent
Can-Retransform-Classes: true
Can-Redefine-Classes: true
Can-Set-Native-Method-Prefix: true
~~~

Many people mistakenly believe that these three `Can-*` lines **guarantee that the corresponding features are enabled**. In reality, these lines **declare what the agent requests**; the JVM still retains the right not to provide an optional capability. Furthermore, even when the JVM reports a capability as available, each specific class and each classfile change must still satisfy its own conditions.

A typical scenario:

- The agent JAR has `Can-Retransform-Classes: true`.
- `premain` calls `Instrumentation.isRetransformClassesSupported()` and receives `false` on a JVM/configuration that does not provide this capability.
- If it still calls `addTransformer(transformer, true)` or `retransformClasses(...)`, the operation requiring retransformation may throw `UnsupportedOperationException`.
- The agent can still use `addTransformer(transformer)` to observe or transform **newly loaded classes**, as long as the standard instrumentation mechanism is active.

**Lesson goal:** learn to distinguish between manifest declarations, runtime capability query results, per-class modifiability, and transformation validity; implement checks and fallback strategies before calling conditional APIs.

## 2. Four layers that determine whether an operation succeeds

Do not collapse every condition into a single flag. Ask four questions in order:

| Layer | Question | Check / source of truth | Conclusion that can be drawn |
|---|---|---|---|
| 1. **Agent declaration** | Does the JAR request this capability? | `Can-Retransform-Classes`, `Can-Redefine-Classes`, `Can-Set-Native-Method-Prefix` in the main manifest | The agent **requests** the permission; there is no guarantee the JVM grants it |
| 2. **Running JVM capability** | Does the current JVM actually provide the requested capability? | `Instrumentation.isRetransformClassesSupported()`, `isRedefineClassesSupported()`, `isNativeMethodPrefixSupported()` | Can decide whether to call or skip the corresponding API group |
| 3. **Target class** | Can this `Class<?>` object be modified? | `Instrumentation.isModifiableClass(targetClass)` | If `false`, do not retransform/redefine that class |
| 4. **Specific transformation** | Is the new classfile valid and within the limits permitted by the JVM? | Validator, verifier, exceptions from the API, and runtime testing | Can fail even if all prior capability checks returned `true` |

Decision diagram:

~~~text
Does the manifest request the feature?
    |
    +-- No --> do not use APIs that depend on that feature
    |
    +-- Yes
         |
         v
Does the running JVM report is...Supported() = true?
    |
    +-- No --> skip / degrade / report error per agent policy
    |
    +-- Yes
         |
         v
If modifying an already-loaded class: isModifiableClass(target) = true?
    |
    +-- No --> skip target / report unsupported
    |
    +-- Yes
         |
         v
Attempt valid operation: retransformClasses / redefineClasses
         |
         +-- Classfile error, structural limits, linkage error ...
         |       --> log and handle per policy
         |
         +-- Success --> verify new behavior
~~~

The last two layers apply to **retransforming/redefining already-loaded classes**. If you only use a transformer at **initial class definition time**, you do not need to enable those manifest flags.

## 3. What do the three `Can-*` attributes mean?

These attributes appear in the **main section** of the agent JAR's manifest. Values are interpreted as Boolean; `true` (case-insensitive) requests the capability, while any other value or absence of the attribute is interpreted as `false`. The default value is `false`.

| Manifest attribute | Capability the agent requests | Query API | Affected APIs |
|---|---|---|---|
| `Can-Retransform-Classes: true` | Requests retransforming already-loaded classes | `isRetransformClassesSupported()` | `addTransformer(t, true)`, `retransformClasses(...)` |
| `Can-Redefine-Classes: true` | Requests redefining already-loaded classes with a supplied classfile | `isRedefineClassesSupported()` | `redefineClasses(ClassDefinition...)` |
| `Can-Set-Native-Method-Prefix: true` | Requests prefix support for native method name resolution after transformation | `isNativeMethodPrefixSupported()` | `setNativeMethodPrefix(t, prefix)` |

**Distinctions:**

- `Premain-Class` specifies the entry point of an agent started with `-javaagent`; it **cannot** replace the `Can-*` flags.
- `Agent-Class` is used for agents dynamically loaded on a supporting JVM; it does not automatically grant retransform/redefine capabilities.
- `Can-Retransform-Classes` is **not synonymous** with `Can-Redefine-Classes`. You may need one without needing the other.
- `Can-Set-Native-Method-Prefix` does not mean the JVM allows arbitrary modification of native code. A native method has no Java bytecode body to insert instructions into; the prefix supports using a wrapper and the native implementation lookup mechanism.
- These flags do not confirm that the application has been successfully instrumented, do not check which classes have been loaded, and do not assert that generated class bytes are valid.

### 3.1. Why must both conditions be true?

Per the `java.lang.instrument` contract, retransformation or redefinition is an **optional JVM capability**. For each feature:

~~~text
Agent JAR request = true
            AND
Current JVM/configuration capability = supported
            ↓
is...Supported() returns true
~~~

Scenarios:

| Agent manifest | JVM/configuration has capability | Agent capability query result | What should you do? |
|---|---|---|---|
| Not declared / `false` | Yes | `false` | Do not use that capability; if sufficient, transform only at load time |
| Not declared / `false` | No | `false` | Do not use that capability |
| `true` | No | `false` | Graceful fallback or fail-fast depending on requirements |
| `true` | Yes | `true` | Can proceed to **class check and operation**, not yet guaranteed to succeed |

The table applies similarly to all three features, with their corresponding `is...Supported()` methods. **Read the manifest to know "what the agent wants"; query `Instrumentation` to know "what this runtime actually permits".**

### 3.2. Does capability change across calls?

The three methods `isRetransformClassesSupported()`, `isRedefineClassesSupported()`, and `isNativeMethodPrefixSupported()` are specified to return **the same result across calls within a single JVM instance**. Therefore, an agent can query once during `premain`/`agentmain` startup, store the result in an immutable capability configuration object, and make consistent decisions across the components that need it.

This differs from whether **a class is among the loaded classes and can be modified**, which must be evaluated on the specific `Class<?>` object. Do not draw conclusions solely from general capabilities.

## 4. `isModifiableClass` is a separate check

Suppose:

~~~java
boolean retransformEnabled = inst.isRetransformClassesSupported();
boolean modifiable = inst.isModifiableClass(Target.class);
~~~

These two Booleans do not imply each other. According to the API:

- `isModifiableClass(c)` checks whether **that class belongs to a modifiable kind**.
- It **does not depend on the value** of `isRetransformClassesSupported()` or `isRedefineClassesSupported()`.
- To actually retransform, you need **both** `isRetransformClassesSupported() == true` and `isModifiableClass(c) == true`.
- To redefine, you need **both** `isRedefineClassesSupported() == true` and `isModifiableClass(c) == true`.
- **Primitive classes** and **array classes** are never modifiable. For example, `int.class`, `int[].class`, and `String[].class` all return `false` for `isModifiableClass`.

Note: `isModifiableClass(c) == true` **does not prove that every change to the class is valid**. A JVM may allow modifying method bodies while disallowing changes to class structure, fields, methods, superclass, or certain attributes. `UnsupportedOperationException`, `UnmodifiableClassException`, `ClassFormatError`, `UnsupportedClassVersionError`, or `LinkageError` can still occur depending on the operation type and class bytes.

### Class identity and class loaders

When checking a real class, keep the `Class<?>` object you obtained; do not select a class solely by string name. Two different loaders can define two classes with the **same binary name but different identity**. The `isModifiableClass` result and the `retransformClasses` target must be tied to the **exact class object** in the JVM, not a class name guessed by an external tool.

In particular, do not arbitrarily call `Class.forName` in `premain` just to "check whether it can be instrumented" if the goal is to intercept the **first class load**. That lookup can cause the class to be loaded before the transformer is registered.

## 5. APIs that look similar but have different preconditions

### 5.1. `addTransformer(transformer)`: does not require retransformation

~~~java
inst.addTransformer(transformer);
~~~

Equivalent to `inst.addTransformer(transformer, false)`. It registers a transformer **without the ability to receive new retransform callbacks**, though it can still be called when the JVM defines a new class or when a class is redefined. This is a valid choice for Java agents that only need to instrument at class load time.

Do not declare `Can-Retransform-Classes: true` merely because the agent has a `ClassFileTransformer`. Declare it only when you genuinely need to **re-run transformations on already-loaded classes**.

### 5.2. `addTransformer(transformer, true)`: requires an additional capability

~~~java
if (inst.isRetransformClassesSupported()) {
    inst.addTransformer(transformer, true);
} else {
    inst.addTransformer(transformer); // Load-time/redefinition callbacks only.
}
~~~

If you call the `true` overload when the JVM configuration does not permit retransformation, `addTransformer` may throw `UnsupportedOperationException`. Checking beforehand gives the program a clear fallback branch.

**Important:** registering with `canRetransform=true` only states that the transformer may participate in **future requested retransform passes**. It does not make the JVM automatically iterate over all `getAllLoadedClasses()` to invoke the transformer again.

### 5.3. `retransformClasses(c)`: requests re-running the transformation chain

~~~java
if (inst.isRetransformClassesSupported()
        && inst.isModifiableClass(targetClass)) {
    inst.retransformClasses(targetClass);
}
~~~

This is an **illustrative API usage pattern**. `targetClass` must be a valid `Class<?>` object obtained from the JVM, and real code must declare/catch `UnmodifiableClassException` and handle verifier/linkage errors along with application protection policies.

- For transformers registered with `canRetransform=true`, the JVM invokes the callback again for the retransform pass.
- For transformers registered with `canRetransform=false`, the callback is **not** invoked again in that pass; the JVM reuses the previous transformation result per the specification.
- Classes that currently have active stack frames may continue executing the old version's bytecode for those frames; new invocations use the new definition.
- `retransformClasses` does not re-run the class's static initializer.

### 5.4. `redefineClasses(definitions)`: replaces definitions with input classfiles

`redefineClasses` accepts a `ClassDefinition` containing the target class and the byte array of the replacement definition. You need `isRedefineClassesSupported()` together with `isModifiableClass`, and then **validate the bytes and change restrictions**. Unlike retransform, you actively supply the new definition; it is the tool's responsibility to ensure the classfile is suitable. `isRedefineClassesSupported()` succeeding **does not** guarantee that every `ClassDefinition` will be accepted.

If a redefine/retransform pass over a group of classes throws an exception, per the API contract, the entire pass is not applied. However, the agent must still report the error and avoid continuing under the assumption that the classes were modified.

### 5.5. `setNativeMethodPrefix`: separate capability, separate problem

The method:

~~~java
inst.setNativeMethodPrefix(transformer, "$myAgent$");
~~~

should only be called when **`isNativeMethodPrefixSupported()` is `true`** and `transformer` has already been registered. This method assists with native method resolution when a transformer creates a Java wrapper and renames the native method in the classfile; it **does not create a wrapper automatically**. If the capability is unavailable, `UnsupportedOperationException` may be thrown; if the transformer is not yet registered, `IllegalArgumentException` may be thrown.

Conceptual diagram:

~~~text
Native method before instrumentation:
    native long calculate(long input);

After a valid classfile transformation:
    long calculate(long input) {
        // Measure time, then call the renamed native method.
        return $myAgent$calculate(input);
    }
    native long $myAgent$calculate(long input);

The native prefix helps the JVM locate the JNI implementation per resolution rules.
~~~

This is a **conceptual illustration**, not a standalone Java program: running it requires a native library/JNI and a transformer that actually generates valid bytecode. Do not declare this capability for an agent that only instruments regular Java methods.

## 6. Java 17+ hands-on: same agent, two manifests

The experiment below demonstrates three points: **not declaring a capability** yields different check results than **requesting the capability when the JVM supports it**; `isModifiableClass` is an independent check; and a **load-time transformer** remains useful when retransform/redefine is not granted.

The example only observes the `demo.app.Work` class and returns `null`, so it does not modify bytecode. The only requirement is JDK 17 or newer with `javac`, `jar`, `java`, and Java agent startup support.

### 6.1. Directory tree

~~~text
capability-demo/
├── Manifest-basic.mf
├── Manifest-requested.mf
└── src/
    ├── demo/
    │   ├── agent/
    │   │   └── CapabilityAgent.java
    │   └── app/
    │       ├── App.java
    │       └── Work.java
    └── ...
~~~

The `...` in the diagram simply represents that an output directory may exist after building; the three Java files and two manifests listed above are **complete** for the example.

### 6.2. File `src/demo/agent/CapabilityAgent.java`

~~~java
package demo.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class CapabilityAgent {
    private CapabilityAgent() {}

    public static void premain(String args, Instrumentation inst) {
        boolean canRetransform = inst.isRetransformClassesSupported();
        boolean canRedefine = inst.isRedefineClassesSupported();
        boolean canNativePrefix = inst.isNativeMethodPrefixSupported();

        System.out.println("[agent] retransform=" + canRetransform);
        System.out.println("[agent] redefine=" + canRedefine);
        System.out.println("[agent] nativePrefix=" + canNativePrefix);

        // Primitive and array classes are never modifiable.
        System.out.println("[agent] int[] modifiable="
                + inst.isModifiableClass(int[].class));

        // Java 17: ClassFileTransformer is not a functional interface;
        // explicitly override one of the two transform methods.
        ClassFileTransformer observer = new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    Module module,
                    ClassLoader loader,
                    String className,
                    Class<?> classBeingRedefined,
                    ProtectionDomain domain,
                    byte[] classBytes) {

                if ("demo/app/Work".equals(className)) {
                    System.out.println("[agent] observed demo.app.Work");
                }
                return null; // Do not modify class bytes.
            }
        };

        // JVM supports retransform: register a capable transformer.
        // JVM does not support it: still observes newly loaded classes.
        inst.addTransformer(observer, canRetransform);
        System.out.println("[agent] transformer canRetransform="
                + canRetransform);
    }
}
~~~

**Why the example uses an anonymous class instead of a lambda:** `ClassFileTransformer` in JDK 17 has two `transform(...)` overloads with default implementations; it is **not a functional interface** that can be instantiated with a lambda expression. Writing an anonymous class and explicitly overriding the 6-parameter overload avoids compilation errors.

Using the runtime query result in `inst.addTransformer(observer, canRetransform)` **does not perform retransformation by itself**. On a JVM reporting `false`, the callback is still registered as non-retransform-capable to receive new class loads.

### 6.3. File `src/demo/app/App.java`

~~~java
package demo.app;

public final class App {
    private App() {}

    public static void main(String[] args)
            throws ReflectiveOperationException {

        System.out.println("[app] main");
        Class<?> workClass = Class.forName("demo.app.Work");
        workClass.getMethod("run").invoke(null);
    }
}
~~~

The application explicitly requests loading `Work` via reflection after printing `[app] main`. It does not need to call any agent API.

### 6.4. File `src/demo/app/Work.java`

~~~java
package demo.app;

public final class Work {
    private Work() {}

    public static void run() {
        System.out.println("[app] Work.run");
    }
}
~~~

### 6.5. Two manifest files

**`Manifest-basic.mf`** (provides only the entry point):

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.CapabilityAgent

~~~

**`Manifest-requested.mf`** (requests all three optional capabilities):

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.CapabilityAgent
Can-Retransform-Classes: true
Can-Redefine-Classes: true
Can-Set-Native-Method-Prefix: true

~~~

The blank line at the end of the manifest in both code blocks represents the trailing newline terminating the manifest file. All attributes are placed in the **main section**, not under a separate JAR entry.

### 6.6. Compiling and packaging

Run from the `capability-demo` directory. On Bash:

~~~bash
mkdir -p out/agent out/app
~~~

On Windows PowerShell, replace the directory-creation command with:

~~~powershell
New-Item -ItemType Directory -Force out/agent, out/app | Out-Null
~~~

Then run:

~~~bash
javac --release 17 -d out/agent src/demo/agent/CapabilityAgent.java
javac --release 17 -d out/app src/demo/app/App.java src/demo/app/Work.java

jar cfm out/agent-basic.jar Manifest-basic.mf -C out/agent .
jar cfm out/agent-requested.jar Manifest-requested.mf -C out/agent .
~~~

Both JARs contain the **same agent bytecode**, differing only in their manifest. To confirm the manifest is actually inside the JAR, you can use `jar tf out/agent-basic.jar` and `jar tf out/agent-requested.jar` to check `META-INF/MANIFEST.MF`; extract into a separate inspection directory if you need to view the contents.

### 6.7. Running the JAR without requesting capabilities

~~~bash
java -javaagent:out/agent-basic.jar -cp out/app demo.app.App
~~~

Per the manifest contract (the optional capabilities are **not requested**), the expected output is:

~~~text
[agent] retransform=false
[agent] redefine=false
[agent] nativePrefix=false
[agent] int[] modifiable=false
[agent] transformer canRetransform=false
[app] main
[agent] observed demo.app.Work
[app] Work.run
~~~

There are three points to observe:

1. All capability queries are `false` because the JAR **did not request** the three corresponding permissions.
2. `int[].class` is not modifiable, regardless of manifest flags.
3. The transformer **still receives the class definition** and observes `demo.app.Work` even without requesting retransform. The reason is that transforming a class when it is **loaded for the first time** differs from requesting retransformation of an **already-loaded** class.

In a JVM where additional agents or a custom loader load `demo.app.Work` early, the callback timing may differ; the output order above is for this self-contained example with no other actor loading the target class beforehand.

### 6.8. Running the JAR requesting all three capabilities

~~~bash
java -javaagent:out/agent-requested.jar -cp out/app demo.app.App
~~~

On a **standard HotSpot JDK 17 that supports all three capabilities**, the expected result is:

~~~text
[agent] retransform=true
[agent] redefine=true
[agent] nativePrefix=true
[agent] int[] modifiable=false
[agent] transformer canRetransform=true
[app] main
[agent] observed demo.app.Work
[app] Work.run
~~~

This is a **JVM-conditional result**: if a JVM/VM configuration does not support a requested capability, the corresponding line will print `false`, and the `canRetransform` value used when registering the transformer will reflect the actual value. The program still runs via the basic load-time instrumentation path.

We have no basis to treat `true/true/true` output as a contract across every vendor, every configuration, and every Java version. That is precisely why you must **print and use the query results**, rather than inferring from manifest lines.

## 7. What should the agent do if the JVM reports `false`?

No single policy fits every tool. Choose based on actual requirements:

| Agent requirement | Missing capability | Appropriate behavior |
|---|---|---|
| Only wants to monitor newly loaded classes | Retransform | Still call `addTransformer(transformer)`; clearly document that scope only includes subsequent loads |
| Needs to observe already-loaded classes, but can tolerate incompleteness | Retransform | Degrade: do not modify old classes, emit an accurate warning about observation scope |
| Must hot-patch running classes to guarantee functionality | Redefine or retransform depending on design | Fail-fast; do not leave the system in a state where it appears patched |
| Only instruments regular Java methods | Native method prefix | Do not request native prefix; no missing functionality arises |
| Needs native method wrappers to record metrics | Native method prefix | Disable the native instrumentation branch separately, or refuse to start if it is a required feature |
| JVM reports capability true, but a class is not modifiable | Per-class | Skip that class and report the reason; do not proceed to invoke an operation that will fail |

A good rule: distinguish **required capabilities** from **optional capabilities** in the agent design. Do not log `Instrumentation ready` and assume all features are available. Instead, log the status clearly:

~~~text
Capabilities: retransform=..., redefine=..., nativePrefix=...
Effective mode: load-time only / load-time + retransformation
Target: skipped, class not modifiable / eligible for operation
~~~

This is a **descriptive log pattern**, not fixed output from a Java API. Specific labels are decided by the agent implementation.

## 8. Pattern for checking actual capabilities before retransforming

The following snippet shows a **design pattern** after obtaining `Instrumentation inst` from the agent and having the exact `Class<?> target`. It is **not a standalone Java file** because `inst` and `target` are supplied by the real agent:

~~~java
if (!inst.isRetransformClassesSupported()) {
    System.err.println("Retransformation is not available");
} else if (!inst.isModifiableClass(target)) {
    System.err.println("Target class is not modifiable");
} else {
    try {
        inst.retransformClasses(target);
        System.out.println("Retransformation completed");
    } catch (java.lang.instrument.UnmodifiableClassException ex) {
        System.err.println("Target became unavailable: " + ex);
    } catch (UnsupportedOperationException ex) {
        System.err.println("Unsupported retransform operation: " + ex);
    } catch (LinkageError ex) {
        System.err.println("Invalid transformed class/linkage: " + ex);
    }
}
~~~

**Warning on error handling:** `retransformClasses` can throw other errors per its contract (for example `ClassFormatError`, `UnsupportedClassVersionError`). This snippet groups certain errors under `LinkageError` to illustrate branching; production policy must decide which errors can be handled locally and which must be reported as fatal. **Do not catch `Throwable` to silently swallow** a failure and then report that instrumentation succeeded.

Even when the transformer callback receives `classBeingRedefined` and class bytes, a retransform pass must still respect class structure, the verifier, and compatibility. If the transformer returns `null`, it does not mean it changed the class's bytecode.

## 9. Common misconceptions that cause real-world bugs

### Misconception 1 — "The manifest is a command forcing the JVM to enable capabilities"

False. The manifest **declares requests**, whereas whether the current JVM/configuration provides the capability is an external condition. The agent must check via `Instrumentation` and have a way to handle cases where the result does not match expectations.

### Misconception 2 — "`isModifiableClass == true` means `retransformClasses` will definitely work"

False. Modifiability is a per-class condition, **independent** of whether the retransform/redefine capability has been granted. And a modifiable class can still be rejected if the operation attempts an impermissible structural change or supplies an invalid classfile.

### Misconception 3 — "Without `Can-Retransform-Classes`, `ClassFileTransformer` does not run"

False. A load-time transformer is still invoked via `addTransformer(transformer)` for new class definitions. The retransform capability relates to **requests to reprocess already-loaded classes** and whether the callback participates in those passes.

### Misconception 4 — "`addTransformer(t, true)` automatically modifies all existing classes"

False. It only registers a transformer capable of participating in **subsequent retransform passes**. A separate `retransformClasses(...)` operation is required for eligible classes; already-loaded classes are not retroactively transformed automatically just because the agent was registered.

### Misconception 5 — "Having `Can-Redefine-Classes` means you can freely add fields/methods"

False. Redefinition/retransformation is constrained by the JVM TI contract and classfile format; you can change valid method bytecode, but many schema changes or inheritance relationship changes are unsupported. Test a specific implementation before deploying.

### Misconception 6 — "Native method prefix is for renaming any Java function"

False. `setNativeMethodPrefix` assists **native method resolution** after a transformer creates a wrapper; it is not a general-purpose class/method renaming API or a way to directly instrument the machine code of native libraries.

### Misconception 7 — "Having JDK 17 means every JVM supports all three capabilities"

False. These are optional features depending on the specific JVM implementation and configuration. Common JDKs may support them, but a portable agent must make decisions from `Instrumentation.is...Supported()` of the **running process**.

### Misconception 8 — "Checking capabilities successfully in `premain` is enough"

Not enough. A production agent needs to verify the right class loader, target class, byte validity, operational exceptions, and behavioral evidence. Capability check methods help **select a valid strategy**, not test the instrumentation product itself.

## 10. Checklist for testing across multiple JVMs/configurations

Before releasing an agent, verify:

1. **Right JAR**: inspect `META-INF/MANIFEST.MF` to confirm it actually contains the main section attributes, rather than only looking at the manifest file in the workspace before packaging.
2. **Right runtime**: record the Java vendor, Java version, and JVM options from the target environment when diagnosing issues, avoiding using developer-machine results to draw conclusions about servers.
3. **Support boundaries**: check all three `is...Supported()` methods for the features the agent needs; do not indiscriminately enable features the agent does not use.
4. **Right overload**: `addTransformer(t)` for load-time; `addTransformer(t,true)` only when retransform is supported and actually needed.
5. **Target modifiability**: for already-loaded classes, use the exact `Class<?>` and `isModifiableClass`; also test array/primitive types as cases that are always rejected.
6. **Transformation errors**: test invalid bytes, unsupported structural changes, and fallback paths when a class cannot be modified.
7. **Do not confuse success logs**: "transformer registered" differs from "class retransformed" and differs even more from "behavior changed correctly".
8. **Bytecode library compatibility**: JDK classfile version, method frames, loaders/modules, and ordering of multiple transformers must all be verified.
9. **Operational impact**: measure startup overhead, control I/O inside callbacks, and do not leave the application in a partially patched state when a required capability is missing.

A minimal test matrix:

| Scenario | What to observe | Expected outcome |
|---|---|---|
| Agent does not declare `Can-*` | Three `is...Supported` calls + transformer at class load | Optional features return `false`; load-time callback still works |
| Agent declares all three `Can-*`, JVM supports them | Three `is...Supported` calls | May return `true`, but this is only the initial condition |
| Agent declares `true`, JVM does not support a capability | Query and fallback branch | Query for that feature is `false`; APIs requiring the feature are not called |
| Array/primitive class | `isModifiableClass` | Always `false`, even if manifest/JVM support retransform |
| Modifiable regular class and supported feature | `retransformClasses` or `redefineClasses` | Still must verify classfile and transformation limits |
| Transformer without `canRetransform` | Retransform pass of an already-loaded class | That callback does not re-run; the JVM reuses the prior transformation per spec |

## 11. Self-assessment

**Question 1.** Is `Can-Retransform-Classes: true` enough to call `retransformClasses`?

> No. `isRetransformClassesSupported()` must report `true` and the target class must be modifiable, and then the modified classfile must still be valid.

**Question 2.** The JVM supports retransform, but the agent manifest is missing `Can-Retransform-Classes`. What does `isRetransformClassesSupported()` return per the contract?

> `false` for the capability configuration that the agent receives. JVM-side availability is only one of the two conditions.

**Question 3.** If `isModifiableClass(int[].class)` returns `false` when all other capability queries are `true`, is there a contradiction?

> No. Primitive/array classes are inherently not modifiable. Global capability support does not mean every class can be modified.

**Question 4.** Does an agent that only wants to log when business classes are loaded need `Can-Retransform-Classes`?

> No. `addTransformer(transformer)` is sufficient to receive new class definitions. Retransform capability is only needed when you must re-run the transformer on already-loaded classes.

**Question 5.** What is the difference between `retransformClasses` and `redefineClasses`?

> `retransformClasses` requests re-running the processing chain from the appropriate source class bytes and re-invoking transformers registered with `canRetransform=true`; `redefineClasses` accepts new classfile bytes as a `ClassDefinition`. Both are subject to class modification restrictions.

**Question 6.** Why might `isNativeMethodPrefixSupported` be `false` even when the agent has no errors?

> It is an optional capability. In particular, an agent that does not request `Can-Set-Native-Method-Prefix: true` will not have that capability. If the agent does not instrument native methods, lacking this feature can be completely normal.

**Question 7.** On a JVM reporting `true` for `isRetransformClassesSupported()`, does running `addTransformer(t,true)` guarantee that a class's methods have been modified?

> No. That only registers the transformer; you still need the target class, a retransform request or a new class definition, and the transformer must return valid new class bytes rather than `null` if it wants to change code.

## 12. Official specification sources

- Java SE 17, `java.lang.instrument` — agent startup, manifest, and the three optional capabilities: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
- Java SE 17, `Instrumentation` — `is...Supported`, `isModifiableClass`, `addTransformer`, `retransformClasses`, `redefineClasses`, `setNativeMethodPrefix`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- Java SE 17, `ClassFileTransformer` — callback and retransformation-capable transformer mechanism: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
- Java SE 17, `ClassDefinition` — class and classfile bytes pair for redefinition: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html
- JVM Tool Interface — class redefine/retransform restrictions: https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html
