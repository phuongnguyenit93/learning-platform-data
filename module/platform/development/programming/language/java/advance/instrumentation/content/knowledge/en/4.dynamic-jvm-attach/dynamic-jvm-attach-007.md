# Distinguishing Successful Attach, Successful Agent Load, and Successful Class Transformation

When attaching a Java agent to a running JVM, the three events—**successful attach**, **successful agent load**, and **successful class transformation**—occur at three different layers. They have a before–after relationship, but they are **not equivalent**. A tool can connect to the JVM without being able to load an agent; an agent can be invoked by the JVM and return normally without transforming a single class; and a transformer can be called and return bytecode, yet the JVM may not accept it or the application may not exhibit the expected behavior.

This lesson focuses on Java's **dynamic attach** mechanism (module **jdk.attach**) and Java agents (module **java.instrument**), how to observe each milestone, and how to design a test that can accurately pinpoint the cause of a failure.

## 1. Three Success Levels That Must Be Defined Separately

In this lesson:

- **Level A — ATTACH_OK:** the tool's JVM successfully calls **VirtualMachine.attach(id)** and receives a **VirtualMachine** handle to the *target JVM*. This proves that an attach connection has been established via the current provider. It does not prove that any agent JAR has been loaded.
- **Level B — AGENT_LOAD_OK:** after attaching, the tool calls **vm.loadAgent(path, options)** and the call completes normally. For a Java agent, the target JVM receives the JAR path, looks up **Agent-Class** in the manifest, and invokes **agentmain**. This does not by itself prove that the agent has enabled all features properly: **agentmain** might silently ignore a business-logic error and return, or only register a transformer without any class passing through it yet.
- **Level C — TRANSFORMATION_OK:** the target class has been accurately identified (name, defining class loader, module), valid replacement bytecode has been applied via the appropriate load/redefine/retransform operation, and there is **independent evidence that the expected definition/behavior is in effect**. For an already-loaded class, a **retransformClasses** call completing without error together with a post-retransform behavioral test provides stronger evidence than merely checking callback logs.

~~~text
Tool JVM (controller)                    Target JVM (target)
        │                                       │
        ├── VirtualMachine.attach(pid) ────────>│ Attach provider checks/connects
        │<────── VirtualMachine handle ─────────┤
        │         [A: ATTACH_OK]                │
        │                                       │
        ├── vm.loadAgent(agent.jar, "mode") ───>│ Read JAR + Agent-Class manifest
        │                                       ├── agentmain(options, inst)
        │                                       │      │
        │                                       │      ├── may only log/return
        │                                       │      └── or addTransformer(...)
        │<────── loadAgent completes ───────────┤
        │         [B: AGENT_LOAD_OK]            │
        │                                       │
        │                                       ├── identify the exact target class
        │                                       ├── transformer produces replacement bytes
        │                                       ├── JVM verifies/installs definition
        │                                       └── behavior is verified
        │                                              [C: TRANSFORMATION_OK]
        │
        └── vm.detach() (closes management channel;
            not a command to unload agent from target)
~~~

**Valid inference:** C usually requires B, and B usually requires A when using the **VirtualMachine.loadAgent** path. **The converse is not true**. A startup agent via **-javaagent** or another loading mechanism can reach state B/C **without** going through step A of the controller under consideration.

### 1.1. Quick Comparison Table

| Scenario | Attach | Agent Load | Target Class Transformation |
| --- | --- | --- | --- |
| **VirtualMachine.attach** returns, **loadAgent** not called yet | Yes | Not yet | Not yet |
| Attach succeeds, **loadAgent** throws **AgentLoadException** | Yes | No | No evidence |
| Attach succeeds, **agentmain** runs in observe mode and returns | Yes | Yes | No |
| Agent registers transformer, target class is already loaded without retransform | Yes | Yes | Not yet for the old class |
| Transformer is called but returns **null** | Yes | Yes | Not by that callback |
| Transformer returns different bytes but JVM rejects them | Yes | May have entered agentmain | No |
| **retransformClasses** completes and a test shows the new behavior | Yes | Yes | Yes for the verified class |

Do not store a single variable named **success=true** for the entire workflow. Record status and evidence at each milestone.

## 2. What Does a Successful Attach Actually Prove?

### 2.1. Controller and Target Are Two Separate JVMs

**com.sun.tools.attach.VirtualMachine** resides in the JDK module **jdk.attach**. The controller typically runs in **a separate JVM**, receives the target's id (usually the PID on common operating systems), and asks the JDK provider to connect:

~~~java
// Illustrative snippet, inside a method that handles exceptions.
import com.sun.tools.attach.VirtualMachine;

VirtualMachine vm = VirtualMachine.attach(targetPid);
try {
    System.out.println("ATTACH_OK");
    // vm.loadAgent(...) has not been called yet.
} finally {
    vm.detach();
}
~~~

The snippet above is not a standalone runnable Java file. At this layer, the controller has permission to invoke management operations supported by the provider; for example, it can read the target's system properties. **Nothing in the attach call automatically loads Agent-Class or invokes ClassFileTransformer.**

- **AttachNotSupportedException**: the provider does not support connecting to the target JVM under current conditions (or no compatible provider exists).
- **IOException**: a connection/I/O error may occur during attach.
- **Permissions and JVM policy issues**: having the right PID is not enough. OS user identity, JVM configuration, container isolation boundaries, attach policies, and whether the target is still alive can all have an impact.
- **Self-attach**: "attaching to the controller JVM's own PID" should not be assumed to always be permitted; many environments impose specific restrictions.

**detach** only closes the controller's connection to the target according to the Attach API. It does not unload any loaded agent, revert transformed classes, or terminate the target JVM.

### 2.2. Successful Attach Does Not Mean an Agent Exists

The same target PID can receive multiple attach connections to query information or load different agents. Therefore, the log:

~~~text
ATTACH_OK pid=12345
~~~

is only evidence for milestone A. It does not mean "agent is ready", "transformer is registered", or "application code has changed". If a test stops here, reporting **ATTACH_ONLY** is more accurate than reporting **INSTRUMENTED**.

## 3. What Additional Conditions Are Required for a Successful Agent Load?

### 3.1. Attach-Based Java Agents Use Agent-Class and agentmain

The path for attaching to a running JVM differs from a startup agent:

| Scenario | Manifest Attribute | Java Agent Callback |
| --- | --- | --- |
| JVM started with **-javaagent:...** | **Premain-Class** | **premain(String, Instrumentation)** |
| Controller calls **VirtualMachine.loadAgent(...)** | **Agent-Class** | **agentmain(String, Instrumentation)** |

During dynamic attach, the JVM attempts to invoke **agentmain(String, Instrumentation)** first, and falls back to **agentmain(String)** if the first form is absent. Use the two-parameter form when you need the **Instrumentation** instance provided by the JVM.

Abbreviated entry-point example:

~~~java
// Illustrative snippet inside an agent class, not a complete file.
public static void agentmain(
        String options,
        java.lang.instrument.Instrumentation instrumentation) {
    System.out.println("AGENTMAIN_ENTERED");
    System.out.println("AGENT_OPTIONS=" + options);
}
~~~

The controller calls **vm.loadAgent(path, options)**. According to the Attach API contract, **loadAgent** waits for the **agentmain** call to complete; if no API-level error occurs, the method returns normally. However, that is still only **API-level loading/initialization success**, not proof that the intended business functionality is running properly.

**The JAR path** is interpreted by the target JVM on the **target's filesystem**. In this exercise, the controller and target are on the same machine so absolute paths match; if the target is in a different mount/container environment, you must confirm that the path actually exists on the target side.

### 3.2. Why loadAgent Returning Is Still Not Enough

There are at least four possibilities:

1. **agentmain only logs and returns**: the agent was invoked, but no transformer was registered.
2. **agentmain catches an exception and does not rethrow it**: the controller side may see **loadAgent** complete; the internal feature has failed and must be reflected via an agent-specific status.
3. **a transformer is registered, but the target class has not been encountered**: the transformer waits for future class loads; a class loaded earlier does not automatically pass through the transformer just because it was registered late.
4. **the transformer is registered successfully, but the callback returns null**: for the invoked class, no replacement bytes were supplied by that transformer.

If the JVM cannot load the agent JAR, lacks **Agent-Class**, or encounters an initialization error, the controller may receive **AgentLoadException**, **AgentInitializationException**, or **IOException** depending on the phase and how the provider reports errors. An uncaught exception in **agentmain** does not abort the target JVM like the **premain** startup rule; the error may be logged by the JVM and surfaced to the attach tool per the API contract.

To measure real initialization quality, the agent should maintain application-level states, such as **AGENT_STARTED**, **TRANSFORMER_REGISTERED**, **TARGET_FOUND**, and **TRANSFORMED**, rather than relying solely on the controller not receiving an exception.

## 4. Successful Class Transformation Is a Separate Verification Layer

### 4.1. ClassFileTransformer Being Invoked Is Not Enough

A transformer receives **classfileBuffer** and returns:

- **null**: do not transform this class from that callback.
- **a new byte[]**: propose a replacement class file for the next transformation step/JVM processing. The input buffer must not be modified in place.
- **an exception**: per the ClassFileTransformer contract, the JVM can still continue invoking other transformers and proceed with load/redefine/retransform; an exception from a transformer is treated as supplying no change in that callback.

Thus, a **TRANSFORM_CALLED** log proves the callback ran, and **TRANSFORM_RETURNED_BYTES** proves the callback supplied replacement bytes. They **do not by themselves guarantee** that the bytes were accepted by the JVM, were not altered by another transformer, or that the target behavior changed.

### 4.2. Newly Loaded Classes and Already-Loaded Classes Have Different Verification Paths

- **Unloaded class**: register the transformer **before** the class is defined. Upon loading, the callback can supply replacement bytes. Then verify that the class definition is accepted and that the behavior/bytecode matches expectations.
- **Already-loaded class**: a newly registered transformer is not automatically re-invoked for the prior definition. If supported by the JVM/agent, register the transformer with **canRetransform=true**, identify the exact **Class<?>**, check **isRetransformClassesSupported()** and **isModifiableClass(clazz)**, and call **retransformClasses(clazz)**.
- **Redefinition**: another path uses **redefineClasses(...)** and **ClassDefinition**, which is also subject to capability/schema restrictions. Do not equate redefine with retransform.

When **retransformClasses** returns normally, the JVM has completed the retransform operation for the requested classes. However, if no transformer made a change, or if the new bytes are equivalent to the old ones, the method can still complete without **producing any behavioral difference**. If the bytes are invalid or structural changes are prohibited, the call may throw an exception such as **ClassFormatError**, **UnsupportedOperationException**, **UnmodifiableClassException**, or **LinkageError**. When retransforming a set of classes and the call fails, the API guarantees that **none of the classes in that set are successfully retransformed**.

### 4.3. Identifying the Exact Target Class

A class name alone is not enough in complex systems:

~~~text
com.example.Service + defining loader A  -> Class A
com.example.Service + defining loader B  -> Class B
~~~

Two **Class** objects with the same fully qualified name but defined by different loaders are two distinct runtime types. When verifying a transformation, record all of the following:

- Binary name and internal name (for example, **com.example.Service** and **com/example/Service**).
- Defining **ClassLoader** and **Module** of the target class.
- Event type: **new class load**, **redefine**, or **retransform**; **classBeingRedefined** is typically non-null in the latter two cases.
- Version/build and patch identifier (for example, **before/after** byte hashes in a controlled pipeline).
- Evidence that the JVM accepted the patch and that the expected behavior holds for the exact selected class.

If you only check a **transform(name)** log without tracking the defining loader, you could mistakenly patch a different class with the same name in a plugin/server application.

## 5. Java 17 Hands-On Lab: Observing All Three Success Levels

The example consists of **three Java files** and **one manifest**. The controller attaches to a running target JVM; the agent has two modes:

- **observe**: loads the agent successfully but **intentionally does not transform any class**.
- **patch**: uses **retransformClasses** to change the literal returned by a method in an already-loaded class from **OLD_VALUE** to **NEW_VALUE**, then observes the result from the target.

To keep the example free of external library dependencies, the transformer only replaces a **CONSTANT_Utf8** entry of the same length in a class file designed for this demo. This is **not a general-purpose transformer for production**. In a real system, use a bytecode library such as ASM or Byte Buddy for structural handling and strict verification.

### 5.1. TargetApp.java — the application to observe

~~~java
// File: TargetApp.java
public final class TargetApp {
    static final class Probe {
        static String value() {
            return "OLD_VALUE";
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("TARGET_PID=" + ProcessHandle.current().pid());

        while (true) {
            System.out.println("PROBE=" + Probe.value());
            Thread.sleep(1500);
        }
    }
}
~~~

**Probe.value()** is a real method invoked repeatedly inside the target JVM. Do not place **OLD_VALUE** in a **static final String** that the caller could inline at compile time; this exercise aims to verify that the method definition itself has changed.

**ProcessHandle.current().pid()** prints the actual PID of the target; the value varies between runs. Once the loop prints **PROBE=OLD_VALUE**, we know the nested class **TargetApp$Probe** has already been loaded before attaching.

### 5.2. AttachAgent.java — agentmain and transformer

~~~java
// File: AttachAgent.java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.charset.StandardCharsets;
import java.security.ProtectionDomain;

public final class AttachAgent {
    private AttachAgent() {
    }

    public static void agentmain(String mode, Instrumentation inst)
            throws Exception {
        System.out.println("AGENTMAIN_ENTERED mode=" + mode);

        if ("observe".equals(mode)) {
            System.out.println("AGENT_READY_NO_TRANSFORM");
            return;
        }

        if (!"patch".equals(mode)) {
            throw new IllegalArgumentException("Unknown mode: " + mode);
        }

        if (!inst.isRetransformClassesSupported()) {
            throw new IllegalStateException("Retransform not supported");
        }

        Class<?> target = null;
        for (Class<?> loaded : inst.getAllLoadedClasses()) {
            if ("TargetApp$Probe".equals(loaded.getName())) {
                target = loaded;
                break;
            }
        }

        if (target == null) {
            throw new IllegalStateException("TargetApp$Probe is not loaded");
        }
        if (!inst.isModifiableClass(target)) {
            throw new IllegalStateException("Target class is not modifiable");
        }

        Utf8Transformer transformer = new Utf8Transformer();
        inst.addTransformer(transformer, true);
        try {
            inst.retransformClasses(target);
            if (!transformer.changed()) {
                throw new IllegalStateException(
                        "No replacement bytes supplied for target"
                );
            }
            System.out.println("RETRANSFORM_COMPLETED");
        } finally {
            inst.removeTransformer(transformer);
        }
    }
}

final class Utf8Transformer implements ClassFileTransformer {
    private volatile boolean replacementSupplied;

    boolean changed() {
        return replacementSupplied;
    }

    @Override
    public byte[] transform(
            ClassLoader loader,
            String name,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] bytes) {
        if (!"TargetApp$Probe".equals(name)
                || classBeingRedefined == null) {
            return null;
        }

        byte[] patched = replaceKnownLiteral(bytes);
        if (patched != null) {
            replacementSupplied = true;
            System.out.println("TRANSFORM_RETURNED_BYTES");
        }
        return patched;
    }

    private static byte[] replaceKnownLiteral(byte[] bytes) {
        // This utility is only for the demo class, not a general-purpose
        // class-file parser or an arbitrary bytecode string-replacement API.
        if (bytes.length < 10
                || (bytes[0] & 0xff) != 0xca
                || (bytes[1] & 0xff) != 0xfe
                || (bytes[2] & 0xff) != 0xba
                || (bytes[3] & 0xff) != 0xbe) {
            return null;
        }

        int poolCount = u2(bytes, 8);
        int p = 10;

        for (int i = 1; i < poolCount; i++) {
            int tag = bytes[p++] & 0xff;
            switch (tag) {
                case 1: { // CONSTANT_Utf8_info
                    int length = u2(bytes, p);
                    p += 2;
                    if (length == 9 && matchesAscii(bytes, p, "OLD_VALUE")) {
                        byte[] result = bytes.clone();
                        byte[] newer = "NEW_VALUE"
                                .getBytes(StandardCharsets.US_ASCII);
                        System.arraycopy(newer, 0, result, p, newer.length);
                        return result;
                    }
                    p += length;
                    break;
                }
                case 3: case 4:       // Integer, Float
                    p += 4;
                    break;
                case 5: case 6:       // Long, Double: two slots
                    p += 8;
                    i++;
                    break;
                case 7: case 8: case 16: case 19: case 20:
                    p += 2;
                    break;
                case 9: case 10: case 11: case 12: case 17: case 18:
                    p += 4;
                    break;
                case 15:             // MethodHandle
                    p += 3;
                    break;
                default:
                    throw new IllegalArgumentException(
                            "Unsupported constant-pool tag: " + tag
                    );
            }
        }
        return null;
    }

    private static int u2(byte[] bytes, int offset) {
        return ((bytes[offset] & 0xff) << 8)
                | (bytes[offset + 1] & 0xff);
    }

    private static boolean matchesAscii(byte[] bytes, int offset,
                                        String value) {
        if (offset + value.length() > bytes.length) {
            return false;
        }
        for (int i = 0; i < value.length(); i++) {
            if (bytes[offset + i] != (byte) value.charAt(i)) {
                return false;
            }
        }
        return true;
    }
}
~~~

**Step-by-step explanation:**

1. **agentmain** prints evidence to the **target JVM's stdout**, not the controller's stdout.
2. **observe** mode returns immediately after logging. It intentionally creates the case **A=PASS, B=PASS, C=NOT_PERFORMED**.
3. **patch** mode checks capabilities before acting. Both **Can-Retransform-Classes** in the manifest and JVM support are required.
4. The agent finds the loaded class using **getAllLoadedClasses()**. In this example there is only one **TargetApp$Probe**; production code must add defining loader/module checks before selecting.
5. The agent registers a transformer that supports retransformation (**true**), calls **retransformClasses(target)**, checks that replacement bytes were supplied, and then removes the transformer. **removeTransformer** does not automatically revert the patch just installed.
6. The transformer clones `classfileBuffer`, replacing the exact **9 ASCII bytes** of the literal **OLD_VALUE** with **NEW_VALUE** in the constant pool; it adds no methods or fields, and changes neither inheritance nor bytecode length. For this demo class, the JVM can verify and use the new definition.
7. After **retransformClasses** returns without error, the agent prints **RETRANSFORM_COMPLETED**. The decisive final evidence remains the **PROBE=NEW_VALUE** line printed by the target itself when invoking the method again.

**Warning about the demo parser's scope:** The literal-replacement logic is written specifically for the valid class generated by **javac** here. General class files have complex structures, modified UTF-8, verifier constraints, many constant-pool entries, and other metadata. Do not use this function to patch arbitrary classes or as a substitute for a bytecode library. Replacing a constant pool entry can also affect every other place referencing that entry if applied to another class.

### 5.3. AttachCommand.java — controller reporting attach and load separately

~~~java
// File: AttachCommand.java
import com.sun.tools.attach.VirtualMachine;
import java.nio.file.Path;

public final class AttachCommand {
    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "Usage: AttachCommand <pid> <agent-jar> <observe|patch>"
            );
        }

        String pid = args[0];
        String agentPath = Path.of(args[1])
                               .toAbsolutePath()
                               .normalize()
                               .toString();
        String mode = args[2];

        VirtualMachine vm = VirtualMachine.attach(pid);
        System.out.println("ATTACH_OK");

        try {
            vm.loadAgent(agentPath, mode);
            System.out.println("LOAD_AGENT_OK");
        } finally {
            vm.detach();
        }
    }
}
~~~

This code intentionally places **ATTACH_OK** right after **attach(...)**, while **LOAD_AGENT_OK** is printed only when **loadAgent(...)** completes normally. If **loadAgent** fails, the controller still runs **detach** in **finally**, and does not mistakenly print **LOAD_AGENT_OK**.

**Note:** This is a controller in a separate JVM. It does not directly receive the **Instrumentation** parameter from the target: that handle is passed by the target JVM to **AttachAgent.agentmain(...)**.

### 5.4. agent.mf — manifest for dynamic attach

Create a text file **agent.mf**:

~~~text
Manifest-Version: 1.0
Agent-Class: AttachAgent
Can-Retransform-Classes: true
~~~

Include a **trailing newline at the end of the manifest file**. For this example, **Agent-Class** is required, and **Can-Retransform-Classes: true** requests the JVM to allow the agent to use retransform. This is not a manifest dedicated to startup **-javaagent**; the **Premain-Class** attribute cannot substitute for **Agent-Class** in an attach exercise.

### 5.5. Compiling and Packaging

In a directory containing **TargetApp.java**, **AttachAgent.java**, **AttachCommand.java**, and **agent.mf**, using a **full JDK 17**:

~~~bash
javac --release 17 TargetApp.java AttachAgent.java
javac --release 17 --add-modules jdk.attach AttachCommand.java
jar cfm attach-agent.jar agent.mf AttachAgent.class Utf8Transformer.class
~~~

The **TargetApp$Probe.class** file is generated automatically by **javac** from the nested class in **TargetApp.java**. It belongs on the **target**'s classpath and does not need to be packaged into **attach-agent.jar**. The agent JAR must contain **AttachAgent.class**, **Utf8Transformer.class**, and **META-INF/MANIFEST.MF**.

If your JDK/distribution requires module configuration when running the controller, add **--add-modules jdk.attach** as shown in the command below. Do not run the controller with a runtime that lacks the **jdk.attach** module.

### 5.6. Starting the Target (First Terminal)

~~~bash
java -XX:+EnableDynamicAgentLoading -cp . TargetApp
~~~

Example initial output (**PID is for illustration only**):

~~~text
TARGET_PID=12345
PROBE=OLD_VALUE
PROBE=OLD_VALUE
PROBE=OLD_VALUE
~~~

Keep this terminal running. **-XX:+EnableDynamicAgentLoading** is a HotSpot option that enables dynamic agent loading; Java 21 added a warning when an agent is loaded dynamically without an explicit opt-in. Default behavior and messages may vary across versions/JVMs: check the policy of the actual target runtime. The attach mechanism is also subject to OS permissions and deployment environment constraints.

### 5.7. Observe Only — Attach and Load Succeed, No Transform Yet (Second Terminal)

Use the **actual PID** printed by the target:

~~~bash
java --add-modules jdk.attach -cp . AttachCommand 12345 attach-agent.jar observe
~~~

Controller output:

~~~text
ATTACH_OK
LOAD_AGENT_OK
~~~

At the same time, the target prints the corresponding lines from **agentmain**:

~~~text
AGENTMAIN_ENTERED mode=observe
AGENT_READY_NO_TRANSFORM
~~~

Subsequent iterations of the loop still print:

~~~text
PROBE=OLD_VALUE
~~~

**Exact conclusion:** the controller attached and loaded the agent; agentmain executed and exited normally, but **no transformer was registered/applied** in observe mode. This is hands-on proof of why **LOAD_AGENT_OK cannot mean TRANSFORMATION_OK**.

### 5.8. Performing the Patch — Confirming Level C Success

While the target is still running, run the controller again:

~~~bash
java --add-modules jdk.attach -cp . AttachCommand 12345 attach-agent.jar patch
~~~

The controller again prints:

~~~text
ATTACH_OK
LOAD_AGENT_OK
~~~

The target additionally prints:

~~~text
AGENTMAIN_ENTERED mode=patch
TRANSFORM_RETURNED_BYTES
RETRANSFORM_COMPLETED
~~~

Afterward, new calls to **Probe.value()** in the target will print:

~~~text
PROBE=NEW_VALUE
~~~

**PROBE=OLD_VALUE** lines may have appeared prior to the retransform point; the two terminals operate concurrently, so the interleaved line order does not follow a fixed chronological transcript. The three lines **TRANSFORM_RETURNED_BYTES**, **RETRANSFORM_COMPLETED**, and **PROBE=NEW_VALUE** represent three escalating types of evidence: the callback supplied bytes, the retransform API completed, and the behavior observed from the target class itself changed.

Stop the target with **Ctrl+C** after finishing the test. There is no need to call **detach** on the target: the controller already performed this in **finally**, and the target and agent have independent lifecycles.

### 5.9. Case Where Attach Is OK but Agent Load Fails

To simulate a non-agent JAR, create a JAR without **Agent-Class** in the same directory:

~~~bash
jar cf not-agent.jar TargetApp.class
java --add-modules jdk.attach -cp . AttachCommand 12345 not-agent.jar observe
~~~

If attach is still permitted, the controller will print **ATTACH_OK** and then **loadAgent** will fail because the JAR is not a valid Java agent for this mechanism; **LOAD_AGENT_OK** will **not appear**. The exact exception type/stack trace depends on the JVM/provider. This lesson does not require the target to change or stop when an agent load fails.

This is a direct control case between Level A and Level B, unlike **observe** mode which distinguishes between B and C.

## 6. Practical Observability: Placing Logs in the Right Spots

An easily diagnosable system should have a **request ID** for each attach request and separate logs by process.

| Milestone | Emitter | Evidence | How far can you conclude? |
| --- | --- | --- | --- |
| **ATTACH_ATTEMPT** | Controller | PID/id, timestamp, JVM/provider | Connection attempt only |
| **ATTACH_OK** | Controller | **attach(...)** returns handle | A |
| **LOAD_AGENT_REQUESTED** | Controller | Target-visible JAR path, mode, request ID | Request sent only |
| **AGENTMAIN_ENTERED** | Target agent | Agent-Class, mode/request ID, agent version | Callback has started |
| **LOAD_AGENT_OK** | Controller | **loadAgent(...)** returns normally | B per API contract |
| **TRANSFORMER_REGISTERED** | Target agent | Transformer identity, canRetransform | Handler registered for class events |
| **TARGET_CLASS_SELECTED** | Target agent | FQCN + loader + module + modifiable flag | Exact target to patch selected |
| **TRANSFORM_RETURNED_BYTES** | Target agent | Class identity, event, input/output hash if applicable | Replacement bytes proposed |
| **RETRANSFORM_COMPLETED** | Target agent | **retransformClasses(...)** returns normally | JVM completed retransform operation |
| **PROBE_NEW_BEHAVIOR** | Target/independent observer | Method value, business signal, or installed bytes check | C for the verified target |

You must monitor the **correct JVM/process** for each line. The **AGENTMAIN_ENTERED** log is emitted by the target; you cannot infer whether the target executed code from the controller's stdout alone.

### 6.1. Illustrative Workflow States

~~~text
REQUESTED
   │
   ├── ATTACH_FAILED             -> no handle yet
   │
   ▼
ATTACHED
   │
   ├── AGENT_LOAD_FAILED         -> handle exists, agent not initialized properly
   │
   ▼
AGENT_LOADED
   │
   ├── TRANSFORM_NOT_REQUESTED   -> observe only
   ├── TARGET_NOT_FOUND          -> target Class to patch not selected
   ├── TRANSFORM_NO_CHANGE       -> no new bytes
   ├── TRANSFORM_REJECTED        -> JVM rejected the patch
   │
   ▼
TRANSFORM_COMPLETED
   │
   ├── EFFECT_NOT_CONFIRMED      -> no target test/behavior check yet
   ▼
BEHAVIOR_VERIFIED
~~~

These are **states defined by your own application**, not standard enums of **VirtualMachine** or **Instrumentation**. In a real system, include error cause, timestamp, request ID, class loader identity, and target version for debugging.

### 6.2. Why Is a Final Check on the Target Necessary?

A request might be "change how method X logs" or "attach a metric to method Y". If only the callback is invoked, you cannot be sure whether:

- The new bytecode was accepted or rejected by the verifier/retransform.
- The exact class used by real requests was patched, or only a same-FQCN class defined by another loader.
- Invocations after retransform execute the new code or are bypassed by another logic branch.
- The feature works properly, but no traffic has hit the target method yet.

The test should trigger an **identifiable new invocation** after the transformation point. For a retransformed class, **active stack frames** currently running may continue using the old definition, while new calls use the new definition. Therefore, do not judge success/failure solely by a call that started before the patch.

## 7. Pitfalls Related to JVM Capabilities and Policies

### 7.1. Being Able to Attach Does Not Mean Being Able to Retransform

An agent JAR can be accepted by the JVM without requesting retransform permission. Before registering a transformer with **canRetransform=true**, check **inst.isRetransformClassesSupported()**. For the target class, check **inst.isModifiableClass(clazz)**. Both are necessary, yet they still do not guarantee the modified bytecode will be accepted if it violates schema limits.

Common restrictions when retransforming/redefining existing classes: you cannot arbitrarily add/remove fields or methods, change inheritance hierarchies, or apply structural changes unsupported by the JVM. The agent must design instrumentation within allowed method-body/bytecode and metadata boundaries, or use a different approach.

A **retransformClasses** call can complete even if every transformer returns **null**. Therefore, **RETRANSFORM_COMPLETED** does not by itself prove a behavioral change; you must check both the supplied bytes and the actual output.

### 7.2. Dynamic Attach Policy and Dynamic Agent Loading Policy Are Two Layers of Conditions

A JVM may allow attach while rejecting **dynamic agent loading**, for example when the target enables **-XX:-EnableDynamicAgentLoading** on a JVM that supports this option. In practice, you may also encounter OS permission issues, container namespaces, attach provider issues, runtime images missing required components, or policy changes across JDK versions.

Starting in JDK 21, HotSpot issues warnings for dynamic agent loading in certain configurations, aligned with the *integrity by default* direction. **-XX:+EnableDynamicAgentLoading** can be enabled on supported targets in accordance with the system's operational policy; check the specific JVM/version rather than assuming all Java releases share the same default. This differs from **-javaagent** at JVM startup: a startup agent does not rely on the controller's **VirtualMachine.attach**.

## 8. Handle Errors by the Exact Layer, Do Not Lump Everything into "attach fail"

| Symptom | Relevant Layer | Check First |
| --- | --- | --- |
| **AttachNotSupportedException** when calling attach | A | Does the provider support the target JVM? Correct PID/namespace/OS permissions? |
| **IOException** during attach | A | Is the target still alive? Are the attach channel and access permissions intact? |
| **ATTACH_OK** appears but **AgentLoadException** follows | B | Target-side JAR path, **Agent-Class** manifest, valid agent JAR? |
| **AgentInitializationException** or agentmain error | B | **agentmain** stack trace, agent dependencies, mode argument, target log? |
| **LOAD_AGENT_OK** but no sign of the feature | B -> C | Did agentmain return early/catch an exception? Was a transformer registered? |
| **TRANSFORMER_REGISTERED** present but no callback | C | Is the class loaded? Is retransform needed? Does the className/loader filter match? |
| **TRANSFORM_RETURNED_BYTES** present but **retransformClasses** fails | C | Class format, verifier, schema restriction, capability, linkage? |
| **retransformClasses** has no error but old behavior persists | C | Did the transformer actually return different bytes? Correct class/loader selected? New call or old stack frame? |
| New behavior observed in tests but production requests unchanged | C | Different classloader, different method, traffic not hitting the code, or different logic condition? |

**Debugging rule:** record the error at the earliest layer where it occurs. If A fails, do not conclude there is a transformer bug; if B returns normally but C lacks evidence, do not report "agent cannot attach". Separating the steps prevents misdiagnosis and avoids endless attach retries when the real fault lies in bytecode or verification logic.

## 9. Distinguishing Five Misleading Log Statements

### "PID found"

Only proves the tool can list/find the PID; a process can disappear before attach. Not enough for A.

### "Attach succeeded"

**VirtualMachine.attach(...)** returned a handle. Accurate for A, not enough for B.

### "Agentmain ran"

Proves the target started the agent callback. If the callback has not finished or failed midway, it cannot be equated with **loadAgent** completing successfully or the agent being ready.

### "Transformer ran"

Proves the callback was invoked. If it returns null or throws, it supplies no change. If it returns a valid byte[], the JVM still needs to verify and install it before concluding C.

### "Retransform returned"

Proves the JVM completed the retransform request (if no exception occurred), yet the patch may have **changed no bytes**. Actual behavioral/definition verification is what confirms the business goal.

## 10. Self-Check Questions

1. **If VirtualMachine.attach(pid) succeeds, is the agent JAR already inside the target JVM?** No. You must call **loadAgent(...)** or use an independent loading mechanism.
2. **Does loadAgent(...) returning normally prove a class was modified?** No. **agentmain** might only perform an observation task or no class may have been transformed.
3. **In dynamic attach, does the JVM look for Premain-Class or Agent-Class?** It looks for **Agent-Class** and invokes **agentmain**; it does not invoke **premain** for this path.
4. **Does registering a transformer after the target class is loaded automatically patch the old class?** No. Transforming an already-loaded class requires retransform/redefine compatible with JVM capabilities.
5. **Does a transformer returning null mean the class bytecode changed?** Not by that transformer.
6. **Is a transformer returning a new byte[] enough to conclude success?** Not yet; the result could be rejected or altered by another transformer.
7. **Why is it necessary to check the defining class loader as well?** Because two classes with the same FQCN in two different loaders are two distinct runtime types.
8. **Does removeTransformer revert a method that was just retransformed?** No. It unregisters the transformer; the installed definition does not automatically revert to the old one.
9. **Does detach unload the agent from the target?** No. It closes the controller's Attach API channel.
10. **Why can the target continue running after agentmain fails?** The post-startup agent loading path does not have the same process-abort policy as **premain** startup; an agent load failure is handled as an error of the attach/agent operation and the target can keep running.

## 11. Verification Checklist Before Reporting "Instrumentation Succeeded"

- I have the **ATTACH_OK** log only after **VirtualMachine.attach(...)** returns.
- I have the **LOAD_AGENT_OK** log only after **vm.loadAgent(...)** returns normally; **detach** is always called in **finally**.
- The target proves **agentmain** ran, read the right agent options, and completed initialization of the requested feature.
- I verified the right **Agent-Class**, the right target JVM, and the JAR path as seen by the target.
- I know whether the class was already loaded; if already loaded, retransform/redefine capabilities were checked.
- I have the target identity **Class + defining loader + module**, avoiding patching the wrong class with the same name.
- The transformer actually supplied a different byte[], not just logging when the callback started; verifier/schema/transformer errors are logged clearly.
- I confirmed the definition-installation operation completed, while also verifying **the effective behavior/bytecode on the target itself** with a new invocation.
- Status is reported per layer (**A**, **B**, **C**), along with timestamp, request ID, and error cause; not everything is lumped into "attach success".

## 12. Official Documentation

- [Java 17 — VirtualMachine, Attach API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html)
- [Java 17 — java.lang.instrument: Starting an Agent After VM Startup](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [Java 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [Java 17 — Instrumentation, retransformClasses and capabilities](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [OpenJDK JEP 451 — Prepare to Disallow the Dynamic Loading of Agents](https://openjdk.org/jeps/451)

When debugging, ask in order: **(A) has the attach connection been established? (B) has the target JVM actually loaded/called back into the agent? (C) has the right class had its patch accepted by the JVM and has the new behavior been verified?** Only with sufficient evidence through C can you report that class transformation succeeded.
