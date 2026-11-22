# Coexistence with Multiple Agents, Coverage Tools, and CDS or AOT Modes

In modern Java applications, a single JVM may simultaneously run multiple components that manipulate bytecode: **APM/tracing** agents, **profilers**, **coverage** tools like JaCoCo, mocking frameworks, security agents, and an internal custom agent. At the same time, deployments may enable **Class Data Sharing (CDS/AppCDS)** to speed up startup, or use the **Ahead-of-Time (AOT) cache** on newer JDKs to prepare certain work before running in production.

These features are **not mutually exclusive by default**, but **coexistence** does not mean they are guaranteed to be compatible across every JVM, every agent order, and every cache. One transformer may alter classfile bytes before another transformer; a coverage tool may compute a class ID from a different version of the class than the one used to generate the report; two agents may inject the same type of hook or helper; retransformation has different callback rules than initial loading; and a CDS/AOT archive may be ignored by the JVM due to incompatible configuration.

The goal of this lesson is to build a **packaging and compatibility testing workflow** rather than offering a "magic flag." We will go from the `-javaagent`/`ClassFileTransformer` contract, how to coordinate with **JaCoCo**, the differences between **CDS vs. AOT cache**, to a Java 17+ demo with **two agents participating in the same JVM**, testing command-line order swaps, retransformation, `-Xshare:off`/`-Xshare:auto`, and a JDK 24+ testing plan with AOT.

## 1. "Coexistence" Must Be Tested Across Multiple Layers

At least five layers must be distinguished:

| Layer | Question | Example Failure |
| --- | --- | --- |
| **Startup** | Are all agents loaded and `premain`/`agentmain` invoked properly? | Wrong `Premain-Class`, missing helper JAR, agent throws an exception causing startup abort. |
| **Bytecode pipeline** | Do transformers receive the right bytes and produce valid results? | One agent strips attributes, a later agent overwrites an earlier transformation, class verifier error. |
| **Class modification capability** | Are redefine/retransform capabilities and per-class modifiability aligned? | Agent requests retransform but lacks `Can-Retransform-Classes`, class is not modifiable. |
| **Tool semantics** | Do coverage/tracing/profiling still collect accurate data? | JaCoCo sees a different class than the report input, resulting in lost coverage even though tests ran. |
| **JVM/cache optimization** | Is the CDS/AOT archive accepted by the JVM and does it still improve startup? | JVM falls back to normal loading, or fails fast when the cache is strictly required. |

Never rely solely on "the application returns HTTP 200" to conclude everything is fine: the application may run while **coverage is wrong**, **spans are missing**, **startup is slower**, or **the cache is not being used**. A good checklist must verify **both the app's output and the output/health of the tools**.

High-level flow:

```text
java launcher / service wrapper
    |
    +-- -javaagent:coverage.jar
    +-- -javaagent:tracing.jar
    +-- -javaagent:custom.jar
    |
    v
premain for each agent
    |
    v
register multiple ClassFileTransformers / helper modules
    |
    v
class load / redefine / retransform
    |
    v
transformers run by group + registration order
    |
    v
JVM verifies/links final class definition
    |
    +--> application runs business logic
    +--> coverage/tracing/profiling emits events
    +--> CDS/AOT may be used, ignored, or rejected
```

**The order of steps is not a promise that all transformers will work together seamlessly.** You must understand the API contract and then verify the actual agent combination.

## 2. Multiple `-javaagent` Options: `premain` Order and Capability Scope

According to the `java.lang.instrument` specification, the JVM allows specifying **multiple** `-javaagent` options; `premain` methods are invoked **in the order the agents appear on the command line**.

Illustrative deployment example (paths must point to real JARs):

```bash
java \
  -javaagent:/opt/agents/coverage.jar \
  -javaagent:/opt/agents/tracing.jar \
  -javaagent:/opt/agents/custom.jar \
  -jar service.jar
```

If the system uses a startup agent, the JAR must have a valid `Premain-Class`. If the agent supports dynamic attach, the manifest needs `Agent-Class` and the class must implement the corresponding `agentmain`. **Attach policy** and **retransform capability** are two separate concerns; a successful attach does not guarantee that classes can be retransformed.

A typical Java agent manifest contains:

```text
Manifest-Version: 1.0
Premain-Class: com.example.agent.AgentEntry
Can-Retransform-Classes: true
Can-Redefine-Classes: true

```

This is only an **illustrative manifest**, not the demo's agent file. The two capabilities here are **independent and optional**:

- `Can-Retransform-Classes: true`: requests permission to call `retransformClasses(...)` and register `canRetransform=true` transformers, still subject to JVM support.
- `Can-Redefine-Classes: true`: requests `redefineClasses(...)`, still subject to JVM support.
- If omitted, the default value is `false`; it is **not automatically enabled** just because another agent declared it.
- The `Instrumentation` instance passed by the JVM to the entry point must be checked via `isRetransformClassesSupported()` and/or `isRedefineClassesSupported()`.

**Do not conflate three types of order:** **`premain` order**, **transformer registration order**, and **transformer callback order**. They are related, but they do not completely coincide.

### 2.1. Reusing the Same JAR Multiple Times Is Valid

The API documentation allows multiple `-javaagent` options to point to the same JAR. For example, the hands-on demo will use:

```text
-javaagent:trace-agent.jar=A
-javaagent:trace-agent.jar=B
```

The JVM calls `premain` twice, each time passing its respective option. The agent code registers **two different transformer instances** corresponding to modes A and B. This is a way to isolate ordering rules without pulling in external libraries. In production, coverage/APM/custom agents usually use **separate JARs**, but the same transformer registration rules still apply.

### 2.2. Watch Out for Options Assembled from the Environment

In real-world applications, the command line may be assembled from:

- `JAVA_TOOL_OPTIONS` / `JDK_JAVA_OPTIONS` and similar environment variables (processed by the JVM/launcher according to their own rules).
- Shell scripts, Docker entrypoints, Kubernetes init/container configs.
- Gradle/Maven test runners, Surefire/Failsafe `argLine`, or IDE run configurations.
- An APM launcher that automatically injects `-javaagent`.

Therefore, **the configuration file you are looking at may not be the actual effective command line**. You should inspect the JVM flags/command line actually passed into the process, while taking care not to log tokens, passwords, or sensitive data that might be present in the options.

## 3. `ClassFileTransformer` Order Is by GROUP, Not Just `-javaagent`

A transformer is registered via:

```java
instrumentation.addTransformer(transformer, canRetransform);
```

When multiple transformers participate, each transformer receives **the output bytes of the preceding transformer**. A transformer returns `null` if it does not modify the class; if it does modify it, it must create a new `byte[]` array containing a valid class file and **must not mutate the input buffer directly**.

According to Java SE 17, the overall order of all transformers consists of four **priority groups**:

| Group Order | Transformer | Retransform Capability |
| --- | --- | --- |
| **1** | Java transformers | `canRetransform=false` |
| **2** | Native/JVMTI transformers | Retransform incapable |
| **3** | Java transformers | `canRetransform=true` |
| **4** | Native/JVMTI transformers | Retransform capable |

**Within each group**, transformers run in **registration order**. However, a Java transformer in **group 1** can still run **before** a Java transformer in **group 3**, **even if the group 3 agent was registered first**. This is why you must never claim that "swapping `-javaagent` order always reverses the bytecode transformation order."

Diagram:

```text
classfile input
    |
    v
[Java incapable transforms]   group 1, registration order
    |
    v
[Native incapable transforms] group 2
    |
    v
[Java capable transforms]     group 3, registration order
    |
    v
[Native capable transforms]   group 4
    |
    v
final transformed classfile
    |
    v
JVM verification / definition
```

For a class being **loaded for the first time**, all matching registered transformers can receive callbacks. For **redefine**, the appropriate groups can also participate in the new definition. For **retransform**, the rules differ: transformers registered with `canRetransform=false` **are not called again**, but the JVM **reapplies the effects of the previous load/redefine**; `canRetransform=true` transformers are called again.

**Do not interpret "A does not receive a callback during retransform" as "all previous transformations by A are erased."** If A actually altered the bytes during load, those effects can be reapplied according to the contract.

### 3.1. Do Not Assume the Classfile Buffer Is Immutable by Guessing

The API specifies not to modify `classfileBuffer` in place; if changes are needed, parse/rewrite into a new array and return it. When no changes are needed, return `null`. Never do this:

```java
// WRONG per contract: illustrates an anti-pattern, not standalone runnable.
classfileBuffer[0] = 0;
return classfileBuffer;
```

This can corrupt the magic bytes and also violates the contract against mutating the input. Use a bytecode API/library that handles the constant pool, stack map frames, method bodies, and attributes in a controlled manner.

### 3.2. When a Transformer Throws an Exception

According to `ClassFileTransformer`, if `transform(...)` throws an uncaught exception, the JVM still proceeds to invoke the remaining transformers; the effect of the failing transformer is equivalent to returning `null`. Therefore, **throwing an exception is not a safe mechanism to abort the entire chain**. Returning invalid bytes can cause class verification/loading to fail; detailed logging must have recursion guards because the logger itself can trigger class loading.

### 3.3. Avoid Transforming the Same Class Twice with the Same Logic

Multiple agents, or a single agent registering duplicate transformers, can:

- Insert two timing snippets into the same method.
- Emit duplicate metrics/spans for a single business call.
- Inject helper calls into a method that was already instrumented, leading to recursion or excessive overhead.
- Corrupt stack map frames during the second rewrite.
- Violate retransform/redefine schema restrictions if the first pass added fields/methods and the subsequent bytes differ.

You should filter by **class loader, module, package, class name, and classfile version**; design transforms to recognize instrumentation markers, or designate a single component as responsible for a given type of hook. Avoid relying solely on a global `Set<String>` to decide whether a class has been instrumented: the same class name in **two defining loaders** can represent two distinct classes.

## 4. A Java 17+ Demo Verifying Actual JVM Ordering

The demo uses **standard Java only**, without requiring ASM, Byte Buddy, or JaCoCo. Loading the same JAR twice is labeled **A** and **B** via agent options:

- A registers a transformer using `addTransformer(..., false)`.
- B registers a transformer using `addTransformer(..., true)`.
- The JAR manifest declares `Can-Retransform-Classes: true` so the JVM attempts to grant the capability; in code, A **intentionally** chooses `false` even though the overall capability may be supported.
- Both transformers only log when encountering `demo/app/Target` and return `null`. Target's bytecode is **not modified**, so application behavior is always `OK`.

By avoiding bytecode rewriting, the demo isolates two questions: **callback invocation order** and **callback behavior differences during retransformation**.

### 4.1. Directory Structure

```text
multi-agent-demo/
├── src/demo/
│   ├── agent/
│   │   └── TraceAgent.java
│   └── app/
│       ├── Target.java
│       └── App.java
└── agent.mf

After build:
├── out/
└── trace-agent.jar
```

### 4.2. `src/demo/agent/TraceAgent.java`

```java
package demo.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;
import java.security.ProtectionDomain;

public final class TraceAgent {
    private static volatile Instrumentation instrumentation;

    private TraceAgent() {}

    public static void premain(String argument, Instrumentation inst) {
        if (!"A".equals(argument) && !"B".equals(argument)) {
            throw new IllegalArgumentException("Expected agent argument A or B");
        }
        String id = argument;
        boolean canRetransform = "B".equals(id);
        instrumentation = inst;
        System.out.println("[" + id + "] premain capable=" + canRetransform);
        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(Module module, ClassLoader loader,
                    String className, Class<?> classBeingRedefined,
                    ProtectionDomain domain, byte[] bytes) {
                if ("demo/app/Target".equals(className)) {
                    String phase = classBeingRedefined == null
                            ? "load" : "retransform";
                    System.out.println("[" + id + "] transform phase=" + phase);
                }
                return null;
            }
        }, canRetransform);
    }

    public static void retransform(Class<?> target)
            throws UnmodifiableClassException {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("Run using -javaagent");
        }
        boolean supported = inst.isRetransformClassesSupported();
        boolean modifiable = inst.isModifiableClass(target);
        System.out.println("[app] supported=" + supported
                + " modifiable=" + modifiable);
        if (supported && modifiable) {
            inst.retransformClasses(target);
            System.out.println("[app] retransform complete");
        }
    }
}
```

Explanation:

1. The JVM invokes `premain` with the argument `A` or `B` depending on the part after `=` in `-javaagent`.
2. Only `B` chooses `canRetransform=true`, while `A` chooses `false`.
3. The callback only logs when the class name is in **internal format** `demo/app/Target`; this name uses `/` slashes, not `.` dots.
4. `classBeingRedefined == null` indicates a callback triggered by loading a new class in the demo; when non-null, in this demo we know it is a retransform because only `retransformClasses(...)` is called, not redefine.
5. `return null` means no byte transformation is performed. This is a pipeline observation tool, not an actual coverage/tracing agent.
6. `retransform(...)` checks capability and modifiability, then calls the API to observe transformer B.

For this experiment, `instrumentation` is updated when `premain` is called twice on the same agent class. This is **only appropriate for a demo**; independent production agents must manage their own lifecycle, helper class loader, parameters, and data separately, rather than using an indeterminate static field to coordinate multiple vendor agents.

### 4.3. `src/demo/app/Target.java`

```java
package demo.app;

public final class Target {
    private Target() {}

    public static String message() {
        return "OK";
    }
}
```

Target knows nothing about Instrumentation. It is the class observed during initial definition and during retransformation.

### 4.4. `src/demo/app/App.java`

```java
package demo.app;

import demo.agent.TraceAgent;

public final class App {
    private App() {}

    public static void main(String[] args) throws Exception {
        System.out.println("[app] first=" + Target.message());
        TraceAgent.retransform(Target.class);
        System.out.println("[app] second=" + Target.message());
    }
}
```

Because the app calls `TraceAgent.retransform(...)`, **this experiment requires running the JVM with `-javaagent`** and the agent class being loadable from the startup agent JAR. In production applications, you should not force business code to depend on a tool's class name; the agent can manage retransform requests on its own.

### 4.5. `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: demo.agent.TraceAgent
Can-Retransform-Classes: true

```

Only this manifest is needed for the demo; `Can-Redefine-Classes` does not need to be declared. **The `canRetransform=false/true` argument of each `addTransformer` call is distinct from the agent's manifest capability**: the manifest allows the JVM to provide the capability, while the transformer explicitly chooses its registration type.

Keep the trailing newline at the end of the manifest file. The JAR must contain `TraceAgent.class` **and** the anonymous class `TraceAgent$1.class` generated by the callback.

### 4.6. Compiling and Packaging

From the `multi-agent-demo/` directory:

```bash
mkdir -p out

javac --release 17 -d out \
  src/demo/agent/TraceAgent.java \
  src/demo/app/Target.java \
  src/demo/app/App.java

jar --create --file trace-agent.jar --manifest agent.mf \
  -C out demo/agent
```

In Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -d out src/demo/agent/TraceAgent.java src/demo/app/Target.java src/demo/app/App.java
jar --create --file trace-agent.jar --manifest agent.mf -C out demo/agent
```

`-C out demo/agent` packages the **entire agent package** into the JAR, including the anonymous class. The application's `Target.class`/`App.class` remain in `out` and are loaded via `-cp out`. Do not accidentally place another copy of `TraceAgent.class` on the classpath/runtime.

The `javac --release 17` and `jar` commands were verified successfully on Zulu OpenJDK 24.0.2; the code only uses Java 17 APIs. On a compliant Java 17 runtime JVM, retransform remains an optional capability; if unavailable, the program already checks and skips the operation.

## 5. Run Results: Swapping Agent Order Does Not Change Transformer Groups

### 5.1. Command A Then B

```bash
java -javaagent:trace-agent.jar=A \
     -javaagent:trace-agent.jar=B \
     -cp out demo.app.App
```

Equivalent single-line PowerShell command:

```powershell
java -javaagent:trace-agent.jar=A -javaagent:trace-agent.jar=B -cp out demo.app.App
```

**Verified stdout on OpenJDK 24.0.2:**

```text
[A] premain capable=false
[B] premain capable=true
[A] transform phase=load
[B] transform phase=load
[app] first=OK
[app] supported=true modifiable=true
[B] transform phase=retransform
[app] retransform complete
[app] second=OK
```

Interpretation:

- `premain(A)` runs before `premain(B)`.
- When the JVM defines Target, transformer **A (incapable)** receives the callback before **B (capable)**.
- When App calls `retransformClasses(Target.class)`, only B receives the callback again.
- B returns `null`, making no byte changes; the method still returns `OK`.

### 5.2. Swapping to B Then A

```bash
java -javaagent:trace-agent.jar=B \
     -javaagent:trace-agent.jar=A \
     -cp out demo.app.App
```

Verified stdout:

```text
[B] premain capable=true
[A] premain capable=false
[A] transform phase=load
[B] transform phase=load
[app] first=OK
[app] supported=true modifiable=true
[B] transform phase=retransform
[app] retransform complete
[app] second=OK
```

**Conclusions from both runs:**

1. **`premain` order changes** according to the command line: A→B or B→A.
2. **The callback order of the two Java transformers remains A→B**, because the JVM places the `canRetransform=false` group before the `true` group, regardless of `premain` order across **two different groups**.
3. **Only B receives the retransform callback**. A belongs to the incapable group, and in this example A returned `null` during initial load so there are no byte effects to reapply.
4. `Target.message()` remains `OK`: the demo only tests orchestration, **not whether two actual bytecode transformations compose cleanly**.

Therefore, the statement "JaCoCo should be placed first in the `-javaagent` list" can only be understood within **specific rules and contexts**, not as a guarantee that JaCoCo will always receive the original bytecode before every native/capable transformer. When complex agents are involved, you must know which group their transformers belong to and inspect the actual bytes.

### 5.3. What If Both Transformers Are in the Same Group?

If A and B both use `addTransformer(transformer, false)` or both register `true` (with the capability granted), Java transformers in the **same group** are called in **registration order**. If each agent registers immediately inside `premain`, that order typically matches the agent order on the command line.

However, an agent may register a transformer later on another thread, or register additional transformers after startup. Therefore, you must log **registration timing and group**, not just the agent name.

### 5.4. Do Not Assume "A Second Retransform Restarts All Agents"

`retransformClasses(...)` does not re-run `premain`, does not re-invoke `false` transformers, and does not reset static state. It asks the JVM to reapply the bytecode chain according to retransform rules. If multiple agents have already injected code, you may need to handle schema/frames/interactions from existing transforms; you cannot simply "trigger retransform" to make every tool run from scratch.

## 6. Coexisting with JaCoCo and Coverage Tools

**JaCoCo** uses a Java agent to insert **coverage probes** into classfiles at load time; as tests execute, the probes record execution data, typically written to a `jacoco.exec` file or via another configured output method. Because JaCoCo does not just look at class names—it also binds execution data to a **class ID**—bytecode modifications elsewhere can cause inaccurate reports.

### 6.1. The Class ID Mismatch Problem

According to JaCoCo's documentation, the class ID is currently computed from **raw class-file bytes** using CRC64. If JaCoCo sees one version of bytes at runtime while the report generator analyzes a different version of bytes, the data may **fail to match** and the class will appear uncovered even though tests ran.

Example:

```text
app.jar on disk:              OrderService.class V1
custom agent transformer:     produces OrderService.class V2
JaCoCo transformer:           computes coverage class ID from V2
report generator:             analyzes file V1
                               |
                               v
                     class ID mismatch, missing/0% coverage
```

Real-world causes:

- Another Java agent modifies the class **before JaCoCo** in the transformer chain.
- A class loader or framework dynamically generates/patches bytes: mocking, persistence weaving, app servers.
- The files used to generate the report were built with a different compiler or compiler settings than the runtime files.
- Obfuscation, shading, AspectJ, or post-processing alters bytes between runtime and report generation.
- Multiple versions with the same binary name are run, or the wrong version is included in the same report group.

Do not conclude "0% coverage report = tests didn't run" before checking the **JaCoCo Sessions page and class IDs**.

### 6.2. Measures Documented by JaCoCo

JaCoCo documentation recommends:

1. **Place JaCoCo before other class-modifying agents on the command line** so JaCoCo has the chance to see the **original bytes** (in compatible pipeline configurations).
2. Use JaCoCo's `classdumpdir` to save the class bytes that the agent actually sees, and then use those exact bytes when generating the report if runtime classes were modified; note that only classes actually loaded will be dumped.
3. Consider **offline instrumentation** if runtime transformations conflict; the report must analyze the **original class files**, while runtime requires the corresponding JaCoCo runtime/agent on the classpath.

**Illustrative** example requiring real JARs:

```bash
java \
  -javaagent:jacocoagent.jar=destfile=build/jacoco.exec,classdumpdir=build/jacoco-dump \
  -javaagent:custom-agent.jar \
  -jar application.jar
```

This command cannot be run directly in the demo because the lesson does not include `jacocoagent.jar` or `custom-agent.jar`. In actual use, you need a JaCoCo version that **supports the class-file version** of the target JDK and writable output paths.

**Warning about group ordering:** placing JaCoCo first on the command line is a JaCoCo-specific recommendation, **not a substitute** for understanding the four transformer groups. With agents registering native hooks or different `canRetransform` flags, you must still verify which bytes JaCoCo actually sees.

### 6.3. Do Not Instrument the Same Class Twice Without Control

When using a coverage tool alongside custom instrumentation:

- Do not let the custom agent accidentally re-insert JaCoCo probes or strip fields/methods/attributes created by JaCoCo.
- Do not enable JaCoCo **online and offline** simultaneously for **the same class** unless a specific version/documentation requires a different setup; double instrumentation normally causes errors.
- If the custom transformer uses a classfile rewriting library, it must preserve elements added by earlier tools that the JVM requires.
- Do not modify a class from an old copy of bytes on disk and return it to a subsequent transformer: doing so **overwrites** the modifications in the input created by earlier agents.
- When using `retransformClasses`, obey schema restrictions and the rules for reapplying effects from incapable transformers.
- Be careful with generated classes/lambdas/proxies and different classloaders; do not filter solely by simple class name.

### 6.4. Metadata and Report Verification

Coverage relies on debug info such as `LineNumberTable` to compute accurate line coverage. Bytecode rewrites that strip line numbers or source metadata can make reports incomplete or hard to correlate. JaCoCo also requires valid classfiles (especially stack map frames on newer class versions).

Coverage checklist:

```text
[ ] JaCoCo version compatible with JVM/classfile version
[ ] Report build uses the correct original/runtime input classfiles per mode
[ ] No online + offline double instrumentation
[ ] LineNumberTable and required class metadata are preserved
[ ] Does the JaCoCo Sessions page show matching class IDs?
[ ] Does jacoco.exec have fresh data, right session, and right path?
[ ] Are includes/excludes and class loader selection appropriate?
[ ] Tested both JaCoCo-before and JaCoCo-after other tools?
[ ] No custom agent/bytecode rewrite stripping probes?
```

**Distinguish the two filters:** the JaCoCo agent's `includes/excludes` control **execution data collection**, whereas which classes appear in the coverage report also depends on input classfiles/report configuration. Do not conflate the two stages.

## 7. Tracing/APM, Mockito/Byte Buddy, and Profilers

JaCoCo is an easy-to-spot example because of its class IDs, but many other tools also alter bytecode or operate at the JVMTI layer.

| Tool | Typical Areas to Check |
| --- | --- |
| **Tracing/APM agent** | Hooks the same methods as the custom agent; risk of duplicate spans, latency, or broken context propagation. |
| **Byte Buddy instrumentation** | Can perform load-time weaving and retransformation; check transformer group and how it detects prior transformation. |
| **Mockito inline/mock frameworks** | Can redefine/retransform classes for mocking; interacts with coverage/class IDs and unmodifiable classes. |
| **Native/JVMTI profiler** | Has native class-file hooks, belonging to different callback groups than Java transformers; do not rely solely on `-javaagent` order. |
| **Security/audit agent** | May require complete event delivery rather than best-effort telemetry; must control overhead and hook conflicts. |
| **Custom internal agent** | Should have package/classloader filters, idempotence, module helper access, and toggles to disable individual transforms. |

With **Byte Buddy AgentBuilder**, do not assume specific APIs/flags are always enabled across every version; verify retransformation config, method matchers, classloader matchers, listener errors, and the actual SDK/library version. With Mockito inline, do not treat mocking capability as a fixed property across all JVMs/containers; attach policies and agent configurations can vary.

A compatibility test should include **at least one method targeted by both tools simultaneously**. If you only test a class monitored by agent A that tool B never touches, you will miss most bytecode conflicts.

## 8. Packaging Agents for Multi-Tool Deployments

Coexistence starts with **the JAR and classloader**, not just the transformer.

### 8.1. Manifest and Helper Dependencies

Verify that the actual agent JAR has the proper fields for its mechanism:

```text
Manifest-Version: 1.0
Premain-Class: com.example.agent.StartupAgent
Agent-Class: com.example.agent.DynamicAgent
Can-Redefine-Classes: true
Can-Retransform-Classes: true

```

This is an illustrative configuration **if the agent actually provides both entry points/capabilities**; do not copy it verbatim and reference nonexistent classes.

- `Premain-Class` is used with startup `-javaagent`; `Agent-Class` is used with attach if supported.
- All agent dependencies must be loadable when needed; circular class loading inside a transformer can lead to `LinkageError`.
- When shading/relocating ASM/Byte Buddy dependencies, avoid library collisions and avoid arbitrarily renaming shared application API packages.
- Inspect `META-INF/MANIFEST.MF` **inside the deployed JAR**, not just the source manifest file or artifact name.
- Do not confuse the **agent JAR** with the **application JAR**: the app may be launched with `-jar`, while the agent is specified separately via `-javaagent:...`.

### 8.2. Package Naming and Avoiding Cross-Dependencies

Two agents sharing the same package/helper names with different versions can load the wrong class, leading to `NoSuchMethodError`, `ClassCastException`, or mixed state. Relocation can help for internal dependencies, but it must be tested against real classloaders and the module system.

If an agent injects calls to a helper, the instrumented class must be able to resolve that helper from its own loader/module. On Java 9+, you must consider **named/unnamed module readability** and appropriate exports/opens. `Instrumentation.redefineModule(...)` can add module reads/exports/opens, but it **does not automatically add a JAR to a class loader's search path**.

### 8.3. Limiting Instrumentation Scope

An agent should provide **include/exclude** mechanisms by class name, classloader, module, and code source. Exclude the agent's own code, exporters/loggers, bytecode libraries, and core classes not intended for instrumentation.

Recursive instrumentation into the logger/exporter itself can cause:

- New events triggering more events, a logging storm, or `StackOverflowError`.
- Calling helpers before classes are ready, causing class loading circularity.
- Slow locks/IO right inside the transform callback.
- Conflicts with another Java agent that also instruments logger or networking classes.

Do not turn exclusions into a rigid, untested list. Whenever you exclude a class, verify whether business telemetry or coverage needs it.

## 9. CDS and AppCDS: Startup Optimization Is Not an Agent Feature

**Class Data Sharing (CDS)** uses archives containing pre-processed class data, allowing certain classes to load faster and enabling metadata sharing across JVM processes. **AppCDS** extends this to eligible application classes. This is a **load/startup/footprint optimization mechanism**, not a Java agent and not equivalent to retransform/redefine.

Common launcher flags on HotSpot/JDK:

| Flag | Purpose |
| --- | --- |
| `-Xshare:off` | Disables CDS to establish a diagnostic baseline. |
| `-Xshare:auto` | Allows the JVM to use an archive if compatible; can fall back if unusable. |
| `-Xshare:on` | Testing mode requiring sharing; may exit if the archive cannot be used, **not recommended by default in production**. |
| `-Xlog:cds=info` | Logs archive activity/decisions on HotSpot, used to verify actual sharing. |
| `-XX:SharedArchiveFile=...` | Specifies an archive matching the JDK/OS/format. |

### 9.1. Do Not Assume the App Running Means CDS Was Used

On many JVMs, `auto` mode can run the application normally **even when the cache/archive is not used**. To verify, you must check **JVM logs and startup/memory impact**. Testing both `-Xshare:off` and `-Xshare:auto` helps separate **bytecode/tool** errors from **CDS archive** issues.

In multi-agent environments—especially when classes are instrumented at load time—modified classes or archive conditions may prevent achieving the same CDS benefits as the baseline. The extent depends on JDK version, archive content, classloader, module path, and transformation type; **never claim "enabling an agent always disables CDS"** or "CDS always works with every agent."

### 9.2. Testing the Demo with `-Xshare:off` and `-Xshare:auto`

```bash
java -Xshare:off \
  -javaagent:trace-agent.jar=A -javaagent:trace-agent.jar=B \
  -cp out demo.app.App

java -Xshare:auto \
  -javaagent:trace-agent.jar=A -javaagent:trace-agent.jar=B \
  -cp out demo.app.App
```

Both runs on Zulu/OpenJDK 24.0.2 **printed the exact same app/agent stdout** as the A-then-B case:

```text
[A] premain capable=false
[B] premain capable=true
[A] transform phase=load
[B] transform phase=load
[app] first=OK
[app] supported=true modifiable=true
[B] transform phase=retransform
[app] retransform complete
[app] second=OK
```

**Correct interpretation:** identical behavior in both modes indicates that agent and app functionality did not break when switching CDS modes **on the tested JVM**. It **does not prove** that the archive was actually used during the `-Xshare:auto` run. To confirm a CDS hit vs. fallback, add VM logging:

```bash
java -Xshare:auto -Xlog:cds=info \
  -javaagent:trace-agent.jar=A -javaagent:trace-agent.jar=B \
  -cp out demo.app.App
```

Specific logging messages vary by JDK/configuration, so no fixed "standard" stdout is shown for verbose mode.

### 9.3. CDS Archives Have Validity Conditions

An archive is typically tied to the JDK version, paths/classpath/module path, and configuration used to create it. Changing the app JAR, helper/agent JARs, flags, using incompatible module options, or switching JDKs can render the archive invalid or eliminate the expected benefits.

Deployment tests should record **how the archive was created** and **how the JVM decides to use the archive at runtime**. Never take an archive built on a different JVM/version into production and assume compatibility.

## 10. JDK 24+ AOT Cache Differs from CDS and Native Image

Starting in **JDK 24**, OpenJDK introduces **Ahead-of-Time Class Loading & Linking** via JEP 483: an AOT cache prepares certain optimizations based on a **training/recording** run, followed by **assembly/create**, and **production/on/auto**. CDS is a related component/concept for pre-run optimization, but the AOT cache can store more optimization data depending on the JDK release.

**Do not equate these three things:**

1. **CDS/AppCDS**: archives of class metadata/related data for fast loading/sharing.
2. **JDK 24+ AOT cache (Project Leyden)**: a workflow of training → cache creation → cache usage to improve startup/warm-up, dependent on version and flags.
3. **GraalVM Native Image** or an **AOT-compiled native executable**: a different closed-world/binary model that does not inherently support `-javaagent` and runtime class modification APIs like a HotSpot JVM. You must consult the documentation of that specific runtime/build tool.

### 10.1. AOT Cache Mechanism in the Java Launcher

In JDK 24+, options take the form:

| Option | Phase |
| --- | --- |
| `-XX:AOTMode=record` + `-XX:AOTConfiguration=app.aotconfig` | Training: runs the app, records AOT configuration. |
| `-XX:AOTMode=create` + `-XX:AOTConfiguration=app.aotconfig` + `-XX:AOTCache=app.aot` | Assembly: builds the cache, **does not run normal application logic**. |
| `-XX:AOTCache=app.aot` or `-XX:AOTMode=auto` | Production: attempts to use the cache, can fall back if the cache is incompatible. |
| `-XX:AOTMode=on` + `-XX:AOTCache=app.aot` | Diagnostic fail-fast: if the cache cannot be used, the VM **may exit before `main`**. |

Depending on the JDK release, the flag list, defaults, and what is stored in the cache may evolve. When using it, rely on **the documentation for the exact deployment JDK version**. For a fair comparison, training/create/run must use the same JDK release, OS/CPU architecture, application/classpath configuration, and representative environment; when the build changes, **regenerate the cache**.

**Especially with multiple agents:** agents and transformers can alter class loading, byte order, module opens/reads, classpath searches, or enable JVMTI capabilities. Some combinations may be incompatible with the AOT cache, particularly diagnostic options that support arbitrary class modification. Thus, **the mere presence of an AOT cache on disk does not prove the JVM mapped/used it**.

### 10.2. Verification from an Experiment on OpenJDK 24.0.2

A secondary experiment using the same demo agent was run on **Zulu/OpenJDK 24.0.2**:

- `AOTMode=record` with both startup agents **ran the app successfully** and produced the configuration file.
- `AOTMode=create` generated the cache file; when the classpath only used the `out` directory, the VM warned that some classes could not be archived due to **Unsupported location**. When using an application JAR without providing helper/agent classes on the assembly phase classpath, the VM also warned of **ClassNotFoundException** for agent classes seen during training.
- When using that cache with **both startup agents**, `AOTMode=auto` **continued running the application** after the VM reported it could not use archived AOT-linked classes because the full module graph was incompatible.
- With the **same cache/same startup agents** and `AOTMode=on`, the VM printed an archive error and **aborted startup** in the experiment.

Typical diagnostic message when the cache and runtime are inconsistent:

```text
CDS archive has aot-linked classes. It cannot be used when archived full module graph is not used.
```

**Conclusion:** this is **one specific result**, not a universal rule that every Java agent causes every AOT cache to fail. Furthermore, **`auto` running the app successfully is a fallback**, not proof that AOT optimization is active. You must use `-Xlog:cds` or the corresponding JDK AOT logging to confirm.

### 10.3. Operational Guidelines for AOT + Agents

For production deployments with an AOT cache:

1. First verify that the app and all agents run properly **without a cache**.
2. Keep **the same agent versions/binaries/order/config** between training and production where consistency is required; control all dynamic class modifications.
3. Prefer **stable JAR classpaths** over temporary build directories and non-reproducible paths, per the corresponding JDK recommendations.
4. Build the cache in an environment matching the required JDK release, OS/CPU, application bytecode, and classpath/module path.
5. Test `AOTMode=auto` with logging to confirm **the cache is actually loaded**, rather than just observing that the app still runs.
6. Test `AOTMode=on` **only in staging/diagnostics** to catch incompatible configurations; consider fail-fast if deployment policy requires the cache.
7. Whenever changing the JDK, agent binary, classpath, module options, or patching the application, regenerate the cache and re-run the compatibility matrix.
8. If the cache cannot be used, measure the fallback's startup/footprint instead of claiming "AOT optimized performance."

Example **illustrating flags only** (requires a valid `app.aot` cache **built for this application/VM**; will not run out-of-the-box with the demo without a cache):

```bash
# JDK 24+, prefers running even when the cache is incompatible:
java -XX:AOTMode=auto -XX:AOTCache=app.aot \
  -javaagent:coverage.jar -javaagent:custom.jar -jar service.jar

# Staging / diagnostics: requires the cache to be usable:
java -XX:AOTMode=on -XX:AOTCache=app.aot \
  -javaagent:coverage.jar -javaagent:custom.jar -jar service.jar
```

To apply this to a specific project, substitute the actual JAR paths, manifest, dependencies, and record/create workflow. **Do not use the fail-fast `AOTMode=on` command in production before compatibility has been thoroughly proven.**

## 11. Compatibility Test Matrix for Deployment

Start from **two independent dimensions**: the number/group of agents and the CDS/AOT mode. A minimal matrix:

| Test | Agent configuration | JVM/archive mode | What to verify |
| --- | --- | --- | --- |
| **T0** | No agents | `-Xshare:off` | Functional/startup/latency baseline. |
| **T1** | Custom agent | `-Xshare:off` | Class transformation, helpers, app behavior. |
| **T2** | Coverage agent | `-Xshare:off` | Execution data, report class IDs, line/branch coverage. |
| **T3** | Coverage + custom | `-Xshare:off` | Both transformers touch the same method; no errors/coverage loss. |
| **T4** | Custom + coverage | `-Xshare:off` | Swapped order; explain differences by callback group. |
| **T5** | Coverage + custom + APM/profiler | `-Xshare:auto` | Analyze p99, dropped/duplicate spans, classload errors. |
| **T6** | Full production agent set | `-Xshare:off` and `auto` | CDS behavior and JVM logs, startup delta. |
| **T7** | Full production agent set | AOT cache auto (matching JDK) | App runs, whether cache is loaded, whether fallback is masked. |
| **T8** | Full production agent set | AOT cache on (staging) | Fail-fast if cache is incompatible, logs sufficient for debugging. |
| **T9** | Same agent set | Cache/agent JAR modified | Regenerate archive, verify reproducibility. |

Depending on the project, add:

- Baseline LTS JDK and actual deployment JDK; multiple vendors/OSes/architectures if required by the environment.
- Classes loaded via system/platform/bootstrap and custom class loaders.
- Named modules, sealed packages, dynamic proxies, lambdas, hidden classes.
- Frameworks using bytecode weaving, hot reload, or inline mocking.
- Retransform/redefine tests while classes are already loaded and the app has active stack frames.
- Startup under stress, GC/heap pressure, concurrent class loading, and shutdown.
- Compatibility with security posture, attach policy, and container restrictions.

**The goal is not to run an infinite set of combinations**, but to select combinations that meaningfully alter behavior/capability/archives, especially classes that **two tools both want to instrument**.

### 11.1. Swapping Agent Order in Maven/Gradle

If the test runner appends a JaCoCo `argLine`, do not accidentally overwrite it when adding a custom agent. A **conceptual configuration** example:

```text
jvmArgs = [JaCoCo argument generated by build tool]
        + [custom -javaagent argument]
        + [other necessary JVM options]
```

Exact syntax depends on the build plugin/version; do not copy the pseudocode above verbatim into Maven or Gradle configs. What matters is verifying **the final command line of the forked test JVM** has JaCoCo and the custom agent in the intended order, not just looking at declarations in the build script.

### 11.2. Test Fixtures Must Reflect Real Interactions

A test that only prints `premain` will not catch classfile conflicts. You should have a **fixture class** transformed by both JaCoCo and the custom agent, invoke methods covering enough branches to generate coverage data, and then:

1. Verify there are no `VerifyError`/`ClassFormatError`/`LinkageError`.
2. Verify method behavior remains intact, including exception paths.
3. Verify JaCoCo data and reports have matching class IDs.
4. Verify tracing/metrics are not duplicated and context is accurate.
5. Verify behavior after retransform if any agent requires this capability.
6. Verify startup and archive logs in both CDS/AOT modes.

## 12. Typical Issues and Diagnostics

| Symptom | Likely Cause | Troubleshooting Step |
| --- | --- | --- |
| JVM aborts immediately at startup | Wrong `Premain-Class` or agent `premain` throws exception | Check main manifest, entry point, classpath, stacktrace. |
| A `-javaagent` does not run | Launcher/wrapper/argLine overwrote the option | Verify the effective command line, not just the build config. |
| Swapped `-javaagent` order, yet transformer still runs A before B | A/B belong to **two different `canRetransform` groups** | Review the four-group docs, log registration/capability. |
| `retransformClasses` does not re-invoke coverage/custom transformer | It was registered with `canRetransform=false` | This is expected semantics: old effects are reapplied, callback is not re-run. |
| `UnsupportedOperationException` when registering capable transformer | Missing `Can-Retransform-Classes` or JVM does not support it | Check manifest and `isRetransformClassesSupported()`. |
| `VerifyError`/`ClassFormatError` after adding second agent | Bytecode rewrite breaks stack map/constant pool or contract between two transforms | Inspect input/output bytes per transformer, classfile validator, library version. |
| `NoClassDefFoundError`/`NoSuchMethodError` related to helper | Helper JAR missing/version clash or invisible to classloader/module | Verify JAR, loader, module reads/exports/opens, package relocation. |
| JaCoCo writes exec but reports 0% | Class ID mismatch: runtime bytes differ from report bytes | Check Sessions, JaCoCo order, `classdumpdir`, offline rules. |
| JaCoCo errors when re-instrumenting | Double instrumentation or classfile already transformed incompatibly | Do not enable offline and online together; pick a single pipeline. |
| Tracing creates two identical spans | Both custom and APM instrument the same method | Filters, instrumentation markers, single hook owner, integration tests. |
| Agent causes `StackOverflowError`/circular loading | Instrumenting its own logger/helper classes | Exclude packages, guard reentrancy, avoid loading classes inside transformer. |
| CDS enabled but startup is not faster | Archive unusable or few eligible classes; agent/classpath changed | Enable `-Xlog:cds`, compare `-Xshare:off/auto`. |
| `AOTMode=auto` still runs despite archive incompatibility | JVM falls back without using the cache | Check diagnostics and startup timing; rebuild cache with matching config. |
| `AOTMode=on` exits before `main` | Cache cannot be mapped, incompatible class linking/VM options | Try auto/off to isolate scope; check JVM logs, rebuild cache. |
| Testing on another JDK reports unsupported class version | Agent ASM/coverage tool does not yet support the new classfile version | Upgrade tool/library to a version supporting target JDK, run compatibility tests. |
| Cannot attach agent in production | Attach policy, OS/JVM permissions, container/runtime restrictions | Prefer startup `-javaagent` where appropriate; do not assume attach is always available. |

### 12.1. Debugging via "Combination Reduction"

If a three-agent pipeline breaks:

```text
No agent
  -> Agent A only
  -> Agent B only
  -> Agent C only
  -> A+B
  -> A+C
  -> B+C
  -> A+B+C
  -> swap startup order for suspected pair
  -> repeat under -Xshare:off / auto
  -> repeat under AOT auto / on (staging)
```

At each step keep the app JAR, JDK, flags, and workload identical, changing only the variable under test. When the failure only appears with A+B, inspect **the class actually instrumented by both** and its bytecode characteristics; when it only appears with AOT on, check cache compatibility before changing source code.

## 13. Agent Release and Rollback Checklist

Before releasing a custom agent alongside coverage/APM tools:

**Packaging:**

- Manifest has accurate `Premain-Class`/`Agent-Class` and only the capabilities actually needed.
- All agent/transformer dependencies are available in the right loader; no collisions with app libraries.
- JAR version, checksums, minimum JVM version, classfile target, and module policy are documented.
- Include/exclude configuration is present, duplicate instrumentation is prevented, and exporters/loggers are not self-instrumented.
- Do not request broader `opens`/exports than necessary just to "make it work."

**Testing:**

- Run the agent standalone, in every agent pair, and then with the full toolset.
- Swap agent order and record callback groups.
- Include fixture tests for both newly loaded classes and retransform/redefine where applicable.
- Run JaCoCo with real reports, checking class IDs and line/branch coverage.
- Compare startup/throughput/p99 as each tool is added.
- Test `-Xshare:off/auto` and monitor logs to confirm actual CDS usage.
- For AOT cache, record exact training/create/runtime options; test `auto` fallback and staging `on` fail-fast.

**Operations:**

- Never allow probe exceptions to override business exceptions.
- Bound memory/CPU/I/O of telemetry workers; define a policy when queues are full.
- Monitor exporter error rates, dropped spans, coverage gaps, and retransform failures.
- Provide a feature flag to disable a group of instrumentations without shutting down the entire service during an incident.
- Maintain a rollback procedure for agent binaries/configs and **regenerate/invalidate caches** if app/JDK/archive compatibility changes.
- If a transformer must be disabled, `Instrumentation.removeTransformer(...)` only stops future callbacks—it **does not automatically revert bytecode already applied** to classes; you may need appropriate retransform/redefine or a restart.

### 13.1. Reproducibility Rules

When encountering intermittent failures, record:

```text
JDK vendor/version/OS/architecture
effective command line, -javaagent order and options (redacted)
agent JAR checksums/versions
target class name + defining loader + module
transformer group/canRetransform registration order
classfile major version + pre/post transform hashes
JaCoCo class ID, exec/report artifact versions
CDS/AOT flags, archive/cache origin, JVM archive logs
app behavior, errors, p99 latency and shutdown conditions
```

Hashing classfile bytes can help detect an agent silently altering a class, but **hashes must not replace understanding classfile semantics**; retransformation can reorder certain constant pool entries/attributes depending on the implementation.

## 14. Self-Check Exercises

**Question 1.** A command has `-javaagent:B.jar -javaagent:A.jar`. Does B's transformer always run before A's?

**Answer:** No. `premain(B)` is called before `premain(A)`, but transformers run by retransformation incapable/capable and native/Java groups, and then by registration order **within each group**.

**Question 2.** Why did the demo with B then A still log A before B when loading Target?

**Answer:** A used `addTransformer(..., false)` so it is in the Java incapable group; B used `true` so it is in the Java capable group. The incapable group is processed before the capable group.

**Question 3.** During `retransformClasses(Target.class)`, must the JVM call transformer A (`false`) again?

**Answer:** No. If A modified bytes during a prior load/redefine, the JVM reapplies its previous effect without invoking A's callback; only the capable transformer B is called again.

**Question 4.** Tests executed the class, yet the JaCoCo report shows 0% while execution data exists. What should you check?

**Answer:** JaCoCo Sessions/class IDs, runtime class bytes vs. report input, other agent ordering, `classdumpdir`, and offline/online instrumentation conflicts.

**Question 5.** Does "placing JaCoCo before all agents" guarantee it always runs before all native/capable transformers?

**Answer:** Not absolutely. It is a JaCoCo recommendation to give it a chance to see original class files; the transformer contract **prioritizes groups**, not just command-line order.

**Question 6.** Does enabling `-Xshare:auto` and having the app run normally prove the CDS archive was used?

**Answer:** No. Auto can fall back. Use JVM logging such as `-Xlog:cds=info` and measure startup/footprint.

**Question 7.** A JDK 24 AOT cache has been created. Why might it not be used when running with a new agent?

**Answer:** The cache depends on the application/JDK/OS/CPU and options; the agent may alter the class/module graph or trigger incompatible conditions. Check logs, use `auto` fallback, and regenerate the cache with the proper configuration.

**Question 8.** How do `AOTMode=auto` and `AOTMode=on` differ when the cache cannot be mapped?

**Answer:** On the JDK 24 launcher, `auto` allows running without the cache; `on` is a diagnostic fail-fast mode and the JVM may exit immediately.

**Question 9.** Does `return null` in a transformer mean canceling all transformations from earlier agents?

**Answer:** No. It only indicates the current transformer did not modify the bytes. The pipeline still carries forward the bytes produced by earlier transformers.

**Question 10.** To verify two agents truly compose safely, is checking `premain` logs enough?

**Answer:** No. You need a fixture transformed by both, verifying the classfile, behavior, coverage IDs, tracing output, retransformation, and results under CDS/AOT modes.

**Question 11.** If a transformer is removed and the agent control connection is closed, do all modified classes automatically revert to their original classfiles?

**Answer:** No. Removing a transformer does not automatically undo installed transformations. An appropriate restoration mechanism or a restart is required.

**Question 12.** Is JDK 24's AOT cache the same as GraalVM native-image and does it inherently share the same `Instrumentation` contract?

**Answer:** No. HotSpot AOT cache is an optimization for a normal running JVM; native-image has a different compilation/runtime model, so you must check the documentation and limitations of the respective tool.

## 15. Summary and Authoritative Sources

**Key principles to remember:**

1. **Multiple agents are supported**, but you must distinguish `premain` order, registration order, and **transform group order**.
2. Java transformers have two groups (`canRetransform=false/true`), interleaved with native/JVMTI hooks; registration order only applies within each group.
3. Retransformation **only re-invokes capable transformers**, while prior incapable effects can be reapplied by the JVM; it does not reinitialize all agents.
4. JaCoCo uses **class IDs from raw class bytes**; tools modifying bytes before JaCoCo or reports using different classes can cause lost coverage even when the app works correctly.
5. Avoid double instrumentation, stripped frames/attributes, helper collisions, recursive instrumentation, and mismatches in named modules.
6. CDS/AppCDS is a **fallback-capable optimization**, not a mode that alters `ClassFileTransformer` semantics; verify via JVM logs.
7. JDK 24+ AOT cache adds requirements for **training/create/runtime consistency**, JDK/OS/CPU, and options; `auto` may run without the cache, while `on` helps catch compatibility errors.
8. **No single fixed agent order guarantees every tool is compatible.** A test matrix covering app behavior + coverage/tracing + startup/cache is the true deployment criterion.

**Official references:**

- [Java SE 17 — `java.lang.instrument`, multiple `-javaagent` and `premain` order](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [Java SE 17 — `ClassFileTransformer`, four callback groups and `transform` contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [Java SE 17 — `Instrumentation.addTransformer` and `retransformClasses`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [JaCoCo — Class Ids, causes of mismatch and remedies](https://www.jacoco.org/jacoco/trunk/doc/classids.html)
- [JaCoCo — Java Agent options, `classdumpdir`, includes/excludes](https://www.jacoco.org/jacoco/trunk/doc/agent.html)
- [JaCoCo — Offline Instrumentation](https://www.jacoco.org/jacoco/trunk/doc/offline.html)
- [JaCoCo — FAQ and compatibility with other tools](https://www.jacoco.org/jacoco/trunk/doc/faq.html)
- [Java SE 17 — Java launcher, AppCDS and `-Xshare`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [JDK 24 — Java launcher, AOT cache record/create/auto/on and cache fallback](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)
- [OpenJDK JEP 483 — Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483)
- [Inside Java — AOT caching, training/assembly/deployment consistency](https://inside.java/2026/01/09/run-aot-cache/)