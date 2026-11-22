# Attaching an Agent to a Test JVM and Transforming a Loaded Class via Retransformation

## 1. Objective: a running JVM changes behavior without restarting

When a Java agent is started via the `-javaagent` flag, the JVM invokes `premain` before running the application's `main` method. However, many real-world diagnostic scenarios occur **after the JVM and business classes are already running**. Where environment and policy allow, the **Attach API** can be used from another Java process to dynamically load an agent into a running JVM. The agent receives `Instrumentation` in `agentmain` and can request the JVM to **retransform** an already-loaded class.

This lab demonstrates one exact flow:

1. Start the **target JVM** with the `demo.lab.TargetLogic` class, whose `state()` method initially returns `"COLD"`. The application calls the method before the agent is present.
2. Start a separate **controller JVM**, using `com.sun.tools.attach.VirtualMachine.attach(pid)` to attach to the target JVM's PID.
3. The controller calls `loadAgent(...)`; the target JVM loads the agent JAR with the `Agent-Class` manifest attribute and runs `agentmain`.
4. The agent checks `isRetransformClassesSupported()`, finds `TargetLogic` in `getAllLoadedClasses()`, and checks `isModifiableClass(...)`.
5. The agent registers a `ClassFileTransformer` with `canRetransform=true` and calls `retransformClasses(TargetLogic.class)`.
6. The transformer modifies an **equal-length ASCII** string constant from `COLD` to `WARM` in the classfile bytes **of the already-loaded class itself**.
7. The running application continues calling the method; new invocations print `state=WARM`. The target JVM does not restart, and the `TargetLogic.class` file on disk is not rewritten either.

**This is a safe experiment on a self-created JVM**, not advice for arbitrary production hot-patching. Attaching grants the ability to execute code inside the target JVM, and retransformation can break the program if the bytecode is invalid. Practice only in test processes that you own.

### What will you be able to do after this lab?

- Distinguish between `premain`, `agentmain`, the Attach API, and a class undergoing retransformation.
- Write the `Agent-Class` manifest attribute correctly along with `Can-Retransform-Classes: true`.
- Compile/run the controller with the `jdk.attach` module on Java 17+.
- Perform `VirtualMachine.attach` / `loadAgent` / `detach` from another process.
- Locate an already-loaded class **inside the target JVM** and verify retransformation capability before modifying bytes.
- Distinguish between a registered transformer and a transformer **that was actually invoked on a loaded class**.
- Understand how retransformation interacts with the classfile baseline, transformer pipeline, active stack frames, static state, schema restrictions, and classloaders.
- Verify results using the **same PID** and the same application before/after, instead of relying solely on agent log lines.
- Diagnose disabled attach, incorrect agent JAR manifests, missing permissions, and invalid bytecode.

## 2. Architecture: controller, agent, and target are three roles

~~~text
TARGET JVM                             CONTROLLER JVM
  demo.lab.TargetApp                     demo.attach.Attacher
        |                                      |
  loads TargetLogic                        VirtualMachine.attach(pid)
        |                                      |
  state() => COLD                              |
        | <---------- Attach protocol ---------+
        |                                      |
  target JVM loads attach-agent.jar <----- vm.loadAgent(path, "")
        |
  AttachAgent.agentmain(args, inst)
        |
        +-- getAllLoadedClasses()
        +-- select exact target Class<?>/loader
        +-- check isRetransformClassesSupported
        +-- check isModifiableClass
        +-- addTransformer(transformer, true)
        +-- retransformClasses(target)
                 |
                 +-- ClassFileTransformer.transform(...)
                 +-- return byte[] changing COLD to WARM
        +-- removeTransformer(transformer)
        |
  state() => WARM                    controller calls vm.detach()
~~~

| Component | Where it runs | Responsibility |
|---|---|---|
| `TargetApp` | Target JVM | Calls the business class and prints observed state |
| `TargetLogic` | Target JVM | Class loaded and used **before attaching** |
| `Attacher` | Controller JVM | Connects to the PID, requests the target JVM to load the agent, then detaches |
| `AttachAgent` | Target JVM | Receives `Instrumentation` and orchestrates retransformation |
| `PatchTransformer` | Callback inside target JVM | Receives classfile bytes, filters the class, and returns transformed bytes |

The controller **does not hold the target's `Instrumentation` object** in its own process. `Instrumentation` is passed by the target JVM into `agentmain` after loading the JAR.

Nor should the Attach API be confused with Java agent instrumentation: Attach is **the channel that delivers the agent into the process**, while `Instrumentation.retransformClasses` is **the mechanism that applies transformations to already-loaded classes**.

## 3. Environment and security requirements

### 3.1. Java and attach permissions

The experiment uses public APIs on **JDK 17+**, including:

- `java`, `javac`, and `jar` for compiling/running/packaging.
- The `jdk.attach` module for the controller (`com.sun.tools.attach.VirtualMachine`).
- The `java.instrument` module for the agent (`Instrumentation`, `ClassFileTransformer`).
- A compatible Attach Provider for the target JVM, OS permissions/same process owner, and a path to the agent JAR that **the target JVM can read**.
- Retransformation capability permitted by both the VM and the manifest.

A custom runtime image may not include `jdk.attach`; a JVM may disable attach or dynamic agent loading. Attach is not guaranteed to succeed across every JVM vendor, container, OS user, or policy.

**Safety rule:** only attach to JVMs you own or have explicit authorization to inspect. Do not test on someone else's production process or a JVM handling critical data. Loading an agent is equivalent to injecting high-privilege code into the target process.

### 3.2. Dynamic loading warnings in JDK 21+

JEP 451 prepares to restrict dynamic agent loading by default in future releases. Starting in JDK 21, some JDK configurations emit a warning when a Java agent is loaded dynamically. In actual testing on **JDK 24**, the target JVM printed a warning to stderr while attach and retransformation still **succeeded**:

~~~text
WARNING: A Java agent has been loaded dynamically (...)
WARNING: If a serviceability tool is in use, please run with -XX:+EnableDynamicAgentLoading to hide this warning
WARNING: Dynamic loading of agents will be disallowed by default in a future release
~~~

Do not treat this warning as a `retransformClasses` error. If the lab environment allows, you can proactively launch the **target JVM** with:

~~~bash
java -XX:+EnableDynamicAgentLoading -cp out/target demo.lab.TargetApp stop.flag
~~~

This flag expresses explicit intent to allow dynamic agent loading in JDKs that support it; it is not a privilege-bypass mechanism, does not alter security policies, and does **not** guarantee attach will succeed when permissions are missing or the attach mechanism is disabled. Check the documentation and specific policy of the JVM you are using, and do not assume every future release behaves identically to JDK 24.

### 3.3. Why use two JVMs instead of self-attach?

Some JVMs restrict self-attach or require specific options. This lab runs `Attacher` in a **second process**, avoiding differences in self-attach policies and making it clear which PID is being modified. Do not confuse the controller's PID with the target's PID.

### 3.4. PASS verification criteria

The experiment passes only when all of the following are demonstrated:

~~~text
Target prints pid=... and state=COLD before the controller attaches.
Attacher connects to the right PID and loads the agent JAR successfully.
Agentmain finds the loaded TargetLogic, and the class is modifiable.
The capable transformer receives the retransform callback on that class.
The JVM accepts the new bytes: retransformClasses returns without error.
A new call to TargetLogic.state() prints state=WARM.
The target JVM remains the same process; the original classfile is not overwritten.
~~~

Seeing only `attach=done` is not sufficient to conclude the transformation succeeded. You must verify **runtime behavior**.

## 4. Directory tree and purpose of each file

~~~text
attach-retransform-lab/
├── AGENT.MF
├── src/
│   ├── target/
│   │   └── demo/lab/
│   │       ├── TargetLogic.java
│   │       └── TargetApp.java
│   ├── agent/
│   │   └── demo/attach/
│   │       └── AttachAgent.java
│   └── control/
│       └── demo/attach/
│           └── Attacher.java
└── out/                       # generated after build
    ├── target/
    ├── agent/
    ├── control/
    └── attach-agent.jar
~~~

There are **four Java source files** and one manifest. No ASM, Byte Buddy, Maven, JNI, or internal classfile APIs are used. The bytecode patcher in this lab only replaces a **same-length** UTF8 constant, keeping the method schema unchanged.

Additionally, `stop.flag` is a file that **the target app itself checks in order to exit early**; it is not part of the Attach API. Do not create this file **before** starting the target, or the target may exit before you attach.

## 5. Target JVM source code

### 5.1. `src/target/demo/lab/TargetLogic.java`

~~~java
package demo.lab;

public final class TargetLogic {
    private TargetLogic() {}

    public static String state() {
        return "COLD";
    }
}
~~~

A very short method using `ldc` with a string constant. Once the JVM defines the class, the method can be called at any time. In this experiment, `state()` has already been called prior to attach, so this is no longer a load-time instrumentation example.

### 5.2. `src/target/demo/lab/TargetApp.java`

~~~java
package demo.lab;

import java.nio.file.Files;
import java.nio.file.Path;

public final class TargetApp {
    private TargetApp() {}

    public static void main(String[] args) throws Exception {
        Path done = Path.of(args[0]);
        System.out.println("pid=" + ProcessHandle.current().pid());
        String previous = null;
        for (int n = 0; n < 200; n++) {
            String current = TargetLogic.state();
            if (!current.equals(previous)) {
                System.out.println("state=" + current);
                System.out.flush();
                previous = current;
            }
            if (Files.exists(done)) break;
            Thread.sleep(100);
        }
        System.out.println("target=done");
    }
}
~~~

Explanation:

- `ProcessHandle.current().pid()` prints the **actual PID** of the target JVM. When attaching, use this PID—do not use a hardcoded example PID.
- The loop calls `TargetLogic.state()` before the agent appears, guaranteeing the class is already loaded and the method has executed.
- `previous` prevents repetitive printing every 100 ms. Normal observed output has a single `state=COLD` line, and upon successful transformation, a single `state=WARM` line.
- `System.out.flush()` ensures logs appear immediately when stdout is redirected.
- `Files.exists(done)` is a lab-specific early-exit condition. The target also has a 200-iteration limit so it does not run forever.
- When a new invocation of `state()` returns WARM, the process continues running in the exact same JVM/PID without invoking a new constructor/`<clinit>`.

**Do not create `stop.flag` before starting the target**. If the target exits too early, restart it following the proper steps instead of trying to attach to a terminated PID.

## 6. Dynamically loaded agent and retransformation-capable transformer

### 6.1. `src/agent/demo/attach/AttachAgent.java`

~~~java
package demo.attach;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class AttachAgent {
    private AttachAgent() {}

    public static void agentmain(String args, Instrumentation inst) throws Exception {
        if (!inst.isRetransformClassesSupported()) {
            throw new IllegalStateException("Retransformation unsupported");
        }
        Class<?> target = null;
        for (Class<?> type : inst.getAllLoadedClasses()) {
            if ("demo.lab.TargetLogic".equals(type.getName())
                    && type.getClassLoader() == ClassLoader.getSystemClassLoader()) {
                target = type;
                break;
            }
        }
        if (target == null || !inst.isModifiableClass(target)) {
            throw new IllegalStateException("Target not found/modifiable");
        }
        PatchTransformer transformer = new PatchTransformer();
        inst.addTransformer(transformer, true);
        try {
            inst.retransformClasses(target);
            if (!transformer.patched) {
                throw new IllegalStateException("Target bytes not patched");
            }
            System.out.println("agent=retransformed");
        } finally {
            inst.removeTransformer(transformer);
        }
    }

    private static final class PatchTransformer implements ClassFileTransformer {
        volatile boolean patched;

        @Override
        public byte[] transform(Module module, ClassLoader loader, String name,
                Class<?> redefining, ProtectionDomain domain, byte[] input) {
            if (!"demo/lab/TargetLogic".equals(name)
                    || redefining == null
                    || loader != ClassLoader.getSystemClassLoader()) {
                return null;
            }
            byte[] output = replaceConstant(input);
            patched = output != null;
            return output;
        }

        private static byte[] replaceConstant(byte[] input) {
            if (input == null || input.length < 10
                    || (input[0] & 255) != 0xca
                    || (input[1] & 255) != 0xfe
                    || (input[2] & 255) != 0xba
                    || (input[3] & 255) != 0xbe) return null;

            int entries = u2(input, 8), p = 10, matches = 0;
            byte[] output = input.clone();

            for (int i = 1; i < entries; i++) {
                if (p >= input.length) return null;
                int tag = input[p++] & 255;
                switch (tag) {
                    case 1: {
                        if (p + 2 > input.length) return null;
                        int len = u2(input, p);
                        p += 2;
                        if (p + len > input.length) return null;
                        if (len == 4 && input[p] == 'C'
                                && input[p+1] == 'O'
                                && input[p+2] == 'L'
                                && input[p+3] == 'D') {
                            output[p] = 'W'; output[p+1] = 'A';
                            output[p+2] = 'R'; output[p+3] = 'M';
                            matches++;
                        }
                        p += len;
                        break;
                    }
                    case 3: case 4: case 9: case 10:
                    case 11: case 12: case 17: case 18:
                        p += 4; break;
                    case 5: case 6:
                        p += 8; i++; break;
                    case 7: case 8: case 16: case 19: case 20:
                        p += 2; break;
                    case 15:
                        p += 3; break;
                    default:
                        return null;
                }
                if (p > input.length) return null;
            }
            return matches == 1 ? output : null;
        }

        private static int u2(byte[] bytes, int pos) {
            return ((bytes[pos] & 255) << 8) | (bytes[pos + 1] & 255);
        }
    }
}
~~~

### 6.2. Which JVM does `agentmain` run in?

This is a **dynamically loaded Java agent**. `VirtualMachine.loadAgent` causes the **target JVM** to run `agentmain` and supply `Instrumentation`. Therefore `getAllLoadedClasses` returns the **target's** classes, and `System.out.println("agent=retransformed")` appears on **target stdout**.

If the controller fails to load the agent or the manifest has an incorrect `Agent-Class`, `agentmain` does not run. If the target VM blocks dynamic loading, the controller may receive an error before the JVM provides `Instrumentation`.

### 6.3. Why use `getAllLoadedClasses()`?

The goal is to **transform an already-loaded class**. Calling `Class.forName("demo.lab.TargetLogic")` from the agent might accidentally load the class for the first time or pick the wrong context loader, causing the test to no longer prove "already loaded".

Instead, we iterate over existing `Class<?>` objects and filter:

- The binary name must be `demo.lab.TargetLogic`.
- The defining loader must be `ClassLoader.getSystemClassLoader()` in this lab.
- `isModifiableClass(target)` must be true before requesting retransformation.

In a JVM with plugin/custom loaders, the same binary name can produce distinct runtime classes across multiple defining loaders. Do not blindly pick the first class by name alone. The lab intentionally uses only the system loader to keep the condition unambiguous.

### 6.4. Two separate capability checks

~~~java
inst.isRetransformClassesSupported()
inst.isModifiableClass(target)
~~~

`isRetransformClassesSupported` indicates whether the JVM/configuration/manifest supports retransformation. `isModifiableClass` indicates whether the specific class can be modified. Do not infer the second from the first. Primitive/array classes cannot be modifiable targets like ordinary business classes.

The **manifest** requires `Can-Retransform-Classes: true` and the JVM must actually support it. `addTransformer(transformer, true)` can throw `UnsupportedOperationException` when the capability is missing.

### 6.5. Why add the transformer with `true` and then retransform?

Merely calling `addTransformer(...)` after `TargetLogic` has been loaded does not automatically re-run the callback on the old class. Calling `retransformClasses(target)` is a **mandatory trigger** for this experiment.

`canRetransform=true` marks the transformer as eligible to be called again during retransformation. A transformer added via the single-argument overload or with `false` does not receive retransform callbacks as a capable transformer; the previous transform result of non-capable transformers may be reused by the JVM, per the Java Instrumentation contract.

In the lab, the sequence is:

~~~text
get already-loaded target Class<?>
    |
check capability and modifiability
    |
addTransformer(transformer, true)
    |
retransformClasses(target)
    |
JVM invokes transformer on old target
    |
return modified byte[]
    |
VM verifies/installs definition
    |
removeTransformer(transformer)
~~~

### 6.6. Inputs to `ClassFileTransformer.transform`

The six-parameter overload in Java 17:

~~~java
byte[] transform(Module module, ClassLoader loader, String className,
                 Class<?> classBeingRedefined, ProtectionDomain domain,
                 byte[] classfileBuffer);
~~~

Meaning in this experiment:

- `className` is the **internal name** `demo/lab/TargetLogic`, unlike the dot-separated binary name.
- `classBeingRedefined` is **non-null** in the retransformation callback for a loaded class.
- `loader` is the class's loader, here the system loader.
- `input` is the bytes the JVM passes to the transformer **at its position in the pipeline**, not always byte-for-byte identical to the file on disk.
- Returning `null` means no class bytes are modified in this callback.
- Returning a new `byte[]` indicates the transformer provides a replacement definition; the JVM must still verify its validity.
- You must not assume the input buffer can be mutated arbitrarily in-place. The code uses `input.clone()`.

Do not call methods on the target inside the transformer to "verify directly": class loading/transform callbacks can be reentrant. The lab performs a small constant pool patch without network I/O or complex logging inside the callback.

### 6.7. How is the narrow constant pool patcher constrained?

The code:

1. Checks the classfile magic header `CAFEBABE`.
2. Reads `constant_pool_count` as a big-endian `u2`.
3. Walks a subset of Java 17 classfile tags by their defined lengths; `CONSTANT_Long`/`Double` occupy two slots.
4. Only modifies a four-byte `CONSTANT_Utf8` entry containing ASCII `COLD`, replacing it with the four bytes `WARM`.
5. Requires exactly **one entry** to be modified; if missing or duplicated, returns `null`.
6. Does not alter method descriptors, branch offsets, `StackMapTable`, method/field counts, superclass, or bytes of any other class.

This is an **illustrative** technique, not a full classfile parser. To insert invocation hooks/branches, alter control flow, compute `StackMapTable`, or handle arbitrary valid classfiles, use ASM, Byte Buddy, or the JDK Class-File API appropriate for your version. You must test classfile validity and the verifier. Do not blindly patch `CONSTANT_Utf8` on classes you do not control: a single entry may be referenced by multiple parts of the classfile.

### 6.8. Role of `patched` and `removeTransformer`

`volatile boolean patched` indicates whether the callback actually produced a non-null output. It lets the agent refuse to report `agent=retransformed` if it never modified the target. However, this flag alone is **not sufficient** proof of correctness: only when `retransformClasses` finishes and the target observes WARM do we have full lab evidence.

`removeTransformer(transformer)` runs in `finally` to prevent a debug callback from affecting future loads. **Removing a transformer does not undo the installed class definition**. The existing class and instances remain; rolling back requires another transformation or a controlled restart.

Per the Javadoc, due to multithreaded class loading, a recently removed transformer may still receive a callback that was already triggered around the time of removal. This is not a global barrier guaranteeing zero concurrent callbacks.

## 7. Controller using `jdk.attach`

### 7.1. `src/control/demo/attach/Attacher.java`

~~~java
package demo.attach;

import com.sun.tools.attach.VirtualMachine;
import java.nio.file.Path;

public final class Attacher {
    private Attacher() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("Usage: Attacher <pid> <agent.jar>");
        }
        VirtualMachine vm = VirtualMachine.attach(args[0]);
        try {
            vm.loadAgent(Path.of(args[1]).toAbsolutePath().toString(), "");
        } finally {
            vm.detach();
        }
        System.out.println("attach=done");
    }
}
~~~

The controller is a **separate** Java process and cannot call `Instrumentation.retransformClasses` directly from this code. It only holds a `VirtualMachine` handle to the target.

- `VirtualMachine.attach(args[0])` establishes a connection to the target PID.
- `vm.loadAgent(path, "")` loads the agent JAR into the **target** and waits for `agentmain` to complete per the Attach API contract.
- `Path.toAbsolutePath()` reduces errors when the controller's working directory differs from the target's. **The path must exist and be readable from the target JVM's filesystem**; across different container mounts, an absolute path from the controller may not be valid in the target.
- `vm.detach()` in `finally` ensures the session is closed even if `loadAgent` fails.
- `attach=done` is a **controller** log, not a target log; do not infer from it that the user method changed without observing the target.

### 7.2. Self-attach and API scope

`VirtualMachine.attach` can throw `AttachNotSupportedException` or `IOException` when permissions/namespaces/JVMs are incompatible. Do not assume you can attach to every Java PID. The controller uses `jdk.attach` and runs with a JDK that includes the module; the agent runs via `java.instrument` inside the target. These are two distinct API sets and two distinct security mechanisms.

## 8. Manifest for a dynamic Java agent

Create `AGENT.MF` (main section, ending with a newline):

~~~text
Manifest-Version: 1.0
Agent-Class: demo.attach.AttachAgent
Can-Retransform-Classes: true

~~~

**Three key attributes:**

- `Manifest-Version`: manifest format version.
- `Agent-Class`: the class containing `agentmain(String, Instrumentation)` for dynamic loading.
- `Can-Retransform-Classes: true`: requests retransformation capability for the agent JAR.

Do not write only `Premain-Class`: that is the startup agent entry point. This lab attaches after the target is running, so the JVM needs `Agent-Class`. `Can-Redefine-Classes` is also unnecessary because `redefineClasses` is not called.

If the manifest is wrong, do not guess the cause from the method's state; inspect the controller exception, target logs, and JAR contents first.

## 9. Building all four source files with JDK 17+

### 9.1. Create output directories

In the `attach-retransform-lab` root directory:

Bash/Linux/macOS:

~~~bash
mkdir -p out/target out/agent out/control
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out/target,out/agent,out/control | Out-Null
~~~

### 9.2. Compile the target JVM classes

~~~bash
javac --release 17 -d out/target src/target/demo/lab/TargetLogic.java src/target/demo/lab/TargetApp.java
~~~

These are the target classes; neither the agent nor the controller is needed on the target's compile-time classpath.

### 9.3. Compile the agent

~~~bash
javac --release 17 -d out/agent src/agent/demo/attach/AttachAgent.java
~~~

`java.lang.instrument` is a long-standing Java API; the source is compiled targeting `--release 17` so it does not depend on newer APIs.

### 9.4. Compile the controller with the `jdk.attach` module

~~~bash
javac --release 17 --add-modules jdk.attach -d out/control src/control/demo/attach/Attacher.java
~~~

When running the controller, also specify `--add-modules jdk.attach`. If a JDK runtime image lacks the module, use a suitable JDK; do not use reflection to bypass module access.

### 9.5. Package the agent JAR

~~~bash
jar cfm out/attach-agent.jar AGENT.MF -C out/agent .
~~~

You can inspect the contents:

~~~bash
jar tf out/attach-agent.jar
~~~

The JAR should contain `META-INF/MANIFEST.MF`, `demo/attach/AttachAgent.class`, and the nested `AttachAgent$PatchTransformer.class`. Note that the agent JAR does **not** contain `TargetLogic`; the target JVM already has that class from `out/target`.

These commands were actually compiled on a test JDK using `javac --release 17` and `javac --release 17 --add-modules jdk.attach`, and then run successfully on JDK 24.

## 10. Running the experiment across two terminals

### 10.1. Terminal 1 — start the target JVM

From the lab root, ensure `stop.flag` **does not exist yet**. On Bash or PowerShell:

~~~bash
java -cp out/target demo.lab.TargetApp stop.flag
~~~

You will see output like:

~~~text
pid=12345
state=COLD
~~~

`12345` is an example PID. Copy the **actual PID printed by the JVM**; do not copy the number literally from the README.

Keep Terminal 1 open; the target is actively calling `TargetLogic.state()`. If the target already printed `target=done` before you attach, you must restart the target (and ensure `stop.flag` is gone) because the old PID has exited.

### 10.2. Terminal 2 — attach using the controller JVM

Replace `12345` with the real PID:

~~~bash
java --add-modules jdk.attach -cp out/control demo.attach.Attacher 12345 out/attach-agent.jar
~~~

The same command in Windows PowerShell:

~~~powershell
java --add-modules jdk.attach -cp out/control demo.attach.Attacher 12345 out/attach-agent.jar
~~~

If all conditions are met, the controller prints:

~~~text
attach=done
~~~

In **Terminal 1**, the target JVM will display the key lines:

~~~text
state=WARM
agent=retransformed
~~~

**The order may be reversed.** `retransformClasses` installs the new definition before `agentmain` prints its completion message; the target thread may receive WARM and print its log before the agent thread does. Do not rely on a strict ordering between the two threads.

### 10.3. Stopping the target cleanly

After seeing `state=WARM`, you can let the target finish its loop or create the stop flag to exit early:

Bash:

~~~bash
touch stop.flag
~~~

PowerShell:

~~~powershell
New-Item -ItemType File -Path stop.flag -Force | Out-Null
~~~

The target prints `target=done`. This is a mechanism of the lab's **TargetApp**, not an Attach API method. Before starting a new target JVM, clean up the old stop flag.

### 10.4. Verified test results

A Java 17-targeted test run executed **two separate JVM processes**, using a real PID; `Attacher` loaded the agent into the target, and the target itself printed:

~~~text
pid=<actual PID>
state=COLD
state=WARM
agent=retransformed
target=done
~~~

The separate controller printed:

~~~text
attach=done
~~~

`<actual PID>` is a descriptive placeholder for the PID that varies per run. In an actual run, `ProcessHandle.current().pid()` prints a concrete integer.

Target stderr on JDK 24 showed the JEP 451 dynamic agent loading warning; **that was not an error** in this test run. The program transitioned from COLD to WARM **without restarting** and without modifying the class file on disk.

## 11. Deep dive into `retransformClasses`

### 11.1. Byte source and pipeline

Per `Instrumentation`, retransformation re-runs the transformation process from the class's **initial classfile bytes**, or the corresponding baseline after a redefine. The bytes used by the JVM may differ in constant pool/attribute layout from the file originally passed to `defineClass`, yet remain equivalent under the contract.

For a class with multiple transformers:

~~~text
JVM baseline bytes
    |
    v
Transformers with canRetransform=false:
    previous transform results are reused; callbacks are not re-invoked
    |
    v
Transformers with canRetransform=true:
    transform callbacks are re-invoked with the appropriate input
    |
    v
JVM verifies and installs the new class definition
~~~

**`classfileBuffer` in your transformer is the input at that point in the pipeline**, not necessarily identical to the `.class` file in the original JAR, and your output may not be the final output if another transformer runs afterward.

### 11.2. Why `addTransformer` alone is not enough

If a class was already loaded before the agent attached, adding a transformer does not automatically revisit the old definition. There will not necessarily be another load of that same class. `retransformClasses(target)` is an explicit request for the JVM to re-invoke capable transformers and install the new definition.

### 11.3. Comparison with `redefineClasses`

| Characteristic | `retransformClasses` | `redefineClasses` |
|---|---|---|
| Input | Loaded `Class<?>`; JVM manages baseline/pipeline | `ClassDefinition` with caller-supplied classfile bytes |
| Primary purpose | Instrument/reinstrument an already-loaded class | Replace definition with an external byte source |
| Uses transformers | Yes, via capable/incapable pipeline | Yes, via the corresponding pipeline |
| Does the API itself add arbitrary fields/methods? | No | No |
| Re-runs static initializer? | No | No |
| Replaces existing object state? | No | No |
| Do active method frames switch mid-execution? | No | No |

If you need to supply complete classfile bytes produced by another compiler, `redefineClasses` may be more appropriate; if you want to run transformers on the bytes of a running class, `retransformClasses` is usually the right fit. Both are subject to JVM TI/class schema limits; do not call one API "strictly more powerful in every respect" than the other.

### 11.4. Class schema restrictions

Do not assume retransformation is permitted to:

- Add or remove fields or methods.
- Change method signatures, modifiers, hierarchy, interface relationships, or schema prohibited by the VM.
- Change class identity, defining loader, or module of an already-defined class.
- Re-run `<clinit>` or reset static fields.
- Convert existing instances into new objects.
- Make an active method jump to new bytecode mid-stack-frame.

That is why the example only replaces an equal-length UTF8 literal in the constant pool, preserving method signatures, fields, and control-flow structure. Complex method body changes require a bytecode writer and thorough tests.

### 11.5. Active frames and observation points

If a thread is in the middle of a retransformed method, that active frame may continue executing the old definition's bytecode. **New invocations** will use the new version once the JVM installs the definition. The lab target repeatedly calls the short method from a separate loop, so it quickly observes WARM.

Log ordering between the target thread and the agent thread can vary; simply keep before/after evidence on the same target process.

### 11.6. Static fields do not reset

If `TargetLogic` has a static counter or cached object, `retransformClasses` does not automatically reset them. The class initializer does not re-run and existing instances are not replaced. Do not think of retransformation as restarting a class at runtime.

### 11.7. Removing a transformer does not roll back

`inst.removeTransformer(transformer)` only unregisters the callback. The class definition installed by the VM remains in its post-retransform state. If you need to restore the previous state, you must design another transformation or restart the process with the original definition according to policy.

If you attach a second time, the input classfile and transformer/redefine history may differ from expectations. The lab **does not guarantee** that attaching twice yields the same behavior. To retry cleanly, use a **new target JVM with a new PID**.

## 12. Reading bytecode and runtime verification

### 12.1. `javap` only reads files on disk

You can inspect the classfile produced by the compiler:

~~~bash
javap -c -v -classpath out/target demo.lab.TargetLogic
~~~

Illustrative partial output:

~~~text
#7 = String             #8  // COLD
#8 = Utf8                   COLD

public static java.lang.String state();
  Code:
     0: ldc           #7      // String COLD
     2: areturn
~~~

Numbers `#7/#8` are compiler-dependent examples. After a successful attach, running `javap` **on `out/target` can still print COLD**, because it reads the initially built classfile. `retransformClasses` replaces the runtime definition and **does not write the classfile back to disk**.

To inspect bytes at a specific point in the transformer, you can build a bounded capture mechanism that saves input and returned bytes along with classloader/phase metadata, then inspect each file with `javap -c -v`. However, a mid-pipeline snapshot is not guaranteed to be the final JVM-installed bytes if another transformer runs afterward.

### 12.2. Do not confuse behavior tests with transformer debugging

A **PASS** run requires all of the following:

1. Appropriate agent/controller logs.
2. `retransformClasses` returns without error.
3. The target method prints WARM from a new invocation.
4. The PID remains the original process.
5. Other functional tests still pass if this is beyond a simple demo.

`javap` on the original file is a tool for explaining classfiles; it **cannot replace observing the JVM runtime**.

## 13. Common causes of attach/retransform failure

| Symptom | Primary hypothesis | Diagnostic action |
|---|---|---|
| `AttachNotSupportedException` | Target JVM incompatible with Attach Provider, wrong namespace, or mechanism blocked | Check JDK, PID, process permissions, OS/container policy |
| `IOException` during attach | Target already exited, missing permissions, attach socket unreachable | Verify the process is alive and in the same security context |
| `Can not attach to current VM` | Self-attach or PID points to the controller | Run two JVMs; get the PID from TargetApp |
| `AgentLoadException` | Wrong JAR path or loading blocked by policy | Path from **target**, manifest, and JVM dynamic agent policy |
| `AgentInitializationException` | `agentmain` threw an exception | Read target stderr and the root cause |
| `isRetransformClassesSupported() == false` | Manifest missing capability or VM does not support it | Check `Can-Retransform-Classes: true` and configuration |
| `Target not found/modifiable` | Class not yet loaded, wrong loader filter, unmodifiable class | Check `getAllLoadedClasses` and defining loader |
| `UnmodifiableClassException` | Class cannot be modified | `isModifiableClass` and class category |
| `UnsupportedOperationException` | Retransform capability disallowed or prohibited schema change | Check VM/JVMTI constraints |
| `ClassFormatError`, `VerifyError` | Transformer produced an invalid classfile | Use a full parser/writer; inspect output bytes/frames |
| `Target bytes not patched` | UTF8 COLD entry not found or transformer filter mismatch | Inspect original classfile, internal name, phase, loader |
| Target still prints COLD | Attached to a different JVM, class unchanged, or target exited | Verify PID and controller/target logs |
| Target prints WARM before agent log | Normal thread scheduling | Do not assume stdout ordering across threads |
| `javap` on disk still shows COLD | Build artifact is not rewritten during retransformation | Understand it is the compile-time artifact |
| Dynamic agent warning | JDK 21+ policy warning | Distinguish warning from failure; read JVM flags/release notes |

### 13.1. Targeting the right process is paramount

Do not pick a PID by a generic "java" name when multiple JVMs run on the machine. Use `pid=...` from the target's `ProcessHandle.current().pid()` or appropriate tools such as `jps -l` / `jcmd -l` and verify the main class/process.

Controller `loadAgent` does not necessarily print every exception in its own terminal. `agentmain` runs inside the target, so inspect **target stdout/stderr** to see retransformation status and failure causes.

### 13.2. Loaders and modules

The same name `demo.lab.TargetLogic` loaded by two different loaders produces two distinct `Class<?>` objects. In an app server, plugin system, or OSGi, do not filter by name alone and pick arbitrarily. The lab uses the system loader; production tools must identify the exact defining loader, module, and class version.

If a transformer inserts a helper call, that helper must also be visible to the target loader/module. A `NoClassDefFoundError` can appear after a retransformation if the helper cannot be found by the JVM; simply returning bytes from a transformer does not resolve visibility automatically.

### 13.3. Concurrency and operational responsibility

A multithreaded JVM may have active frames still executing old code while new invocations run new code; behavior during a transition window may be non-uniform. Do not treat retransformation as a system-wide transactional business rollback. You must test exception paths, side effects, lock/monitor semantics, module graphs, and observability models.

## 14. Additional test matrix

| Case | Action | Expected result |
|---|---|---|
| Baseline | Run target without attaching | Only `state=COLD` appears |
| Standard | Target prints COLD, controller attaches to right PID | Target switches to WARM; attach done |
| Stale PID | Attach to an exited process | Controller fails without affecting other JVMs |
| Missing JAR | Invalid `loadAgent` path | Agent load error |
| Bad manifest | Missing `Agent-Class` | `agentmain` does not run |
| Capability false | Omit `Can-Retransform-Classes` | Agent rejects as unsupported |
| Target not loaded | Attach before first `state()` call | `getAllLoadedClasses` does not find the class |
| Different loader | Use a custom class loader | Lab filter does not select it |
| Unmodifiable target | Select an unmodifiable class | Gate rejects it |
| Changed literal | Rebuild class returning a string other than COLD | Transformer returns null; agent reports not patched |
| Invalid classfile | Test a buggy writer in a sandbox | VM rejects with format/verify error |
| Active invocation | Retransform during a long method | Old frame may continue with old code |
| Second attach | Use an already-WARM target | Does not pass by default; requires idempotency design |
| Dynamic loading disabled | Blocked by JVM policy | Attach/loadAgent fails cleanly |

Do not fault-inject by killing or disrupting shared JVMs. Negative test cases must run in an authorized lab environment.

## 15. Checklist for a reproducible experiment

**Before attaching**

- [ ] Ran `java -version` and `javac -version`, confirming the JDK includes `jdk.attach`.
- [ ] PID obtained from the new target JVM, not copied from instructions.
- [ ] Target has printed COLD and has not exited yet.
- [ ] Manifest includes `Agent-Class` and `Can-Retransform-Classes: true`.
- [ ] JAR contains the agent class and nested transformer.
- [ ] Agent JAR path is accessible to the target JVM, not just the controller.
- [ ] Experimenter has attach permissions under OS/JVM/security policy.
- [ ] No leftover stop flag from a previous run.

**During attach/retransform**

- [ ] Controller attaches and detaches in `finally`.
- [ ] Agent checks both JVM retransformation support and target modifiability.
- [ ] Target is selected by class name **and** defining loader.
- [ ] Transformer registered with `canRetransform=true`.
- [ ] `retransformClasses(target)` is actually called.
- [ ] Transformer does not mutate `classfileBuffer` in-place and does not touch other classes.
- [ ] Class schema/method signatures are unchanged.
- [ ] Agent removes the transformer whether it succeeds or fails.
- [ ] Exceptions are not swallowed and reported as success.

**After attaching**

- [ ] Target transitions from COLD to WARM on the **same PID**.
- [ ] Controller prints `attach=done` without loadAgent errors.
- [ ] Understand dynamic agent warnings are warnings, not automatic failures.
- [ ] Distinguish build artifacts on disk from runtime definitions.
- [ ] Do not treat `removeTransformer` as a rollback.
- [ ] Test business behavior beyond the demo method if used in a real system.
- [ ] Record reproduction details: JDK/version, manifest, commands, PID, and redacted logs.

## 16. Review questions (with answers)

**1.** Why must `TargetLogic` print COLD before attaching?

> Because we need to prove the class was already loaded and used **before** the agent was injected. This is a retransformation experiment, not a class-load transform.

**2.** How does `Agent-Class` differ from `Premain-Class`?

> `Agent-Class` selects the `agentmain` entry point for dynamic attach; `Premain-Class` selects `premain` at startup.

**3.** Which module is used in the controller JVM?

> `jdk.attach`, which provides `com.sun.tools.attach.VirtualMachine`. `Instrumentation` belongs to the `java.instrument` module and is supplied inside the target agent.

**4.** Why use two JVMs?

> It allows targeting an independent PID and avoids relying on the JVM's self-attach policy.

**5.** Why is calling `addTransformer` alone not enough?

> Because the target class was already loaded earlier. `retransformClasses` is needed to trigger capable transformers to run again.

**6.** Is `Can-Retransform-Classes: true` sufficient?

> No. The JVM must also support retransformation and the specific class must be modifiable.

**7.** What advantage does `getAllLoadedClasses()` have over loading via `Class.forName`?

> It verifies the class already exists in the VM, allows selecting the exact `Class<?>` with its loader, and does not proactively trigger an initial load.

**8.** Why does `transform` return a new byte array instead of mutating the input?

> The transformer contract requires leaving the input array unmodified in-place; the output is a new `byte[]` definition or `null` when unchanged.

**9.** In the demo, where do the bytes change from COLD to WARM?

> In a four-byte `CONSTANT_Utf8` entry in the constant pool of the loaded target class; the method bytecode uses the same constant reference.

**10.** Does removing the transformer revert to COLD?

> No. The WARM definition installed in the JVM remains in effect; removing only unregisters the callback.

**11.** What happens when the class has active frames?

> Active frames may continue using the old code; new invocations use the new definition once installed by the JVM.

**12.** Why can `javap` on `out/target` after attaching still print COLD?

> Because `javap` reads the build artifact classfile on disk, whereas retransformation updates the definition inside the running JVM.

**13.** If the controller prints attach done, is it certain the target changed?

> Not yet. You need logs/evidence of `retransformClasses` and to observe the method newly returning WARM.

**14.** Can `state=WARM` appear before `agent=retransformed`?

> Yes. Threads can interleave after the new definition is installed; there is no guarantee on that print order.

**15.** Why not use the lab's very short constant pool patcher to instrument any application?

> It does not handle arbitrary classfiles, control flow, frames, schema changes, or bytecode edge cases. Use a full library/classfile API and verifier tests.

## 17. References

- Java SE 17, `Instrumentation` — `isRetransformClassesSupported`, `isModifiableClass`, `getAllLoadedClasses`, `addTransformer`, `retransformClasses`, active stack frames, and class schema: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- Java SE 17, `ClassFileTransformer` — callback during load/redefine/retransform, `canRetransform`, return bytes: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
- Java SE 17, `java.lang.instrument` package — `Agent-Class`, `Can-Retransform-Classes`, `agentmain`, and manifest: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
- Java SE 17, `com.sun.tools.attach.VirtualMachine` — `attach`, `loadAgent`, `detach`, and error classes: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html
- Java SE 17, `jdk.attach` module — Attach API: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/module-summary.html
- OpenJDK JEP 451, `Prepare to Disallow the Dynamic Loading of Agents by Default` — policy, warnings, and VM flags: https://openjdk.org/jeps/451
- Java SE 17, JVM Specification, Chapter 4 — classfile constant pool and tags: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
- Java SE 17, `javap` — reading bytecode from classpath or classfiles: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html
