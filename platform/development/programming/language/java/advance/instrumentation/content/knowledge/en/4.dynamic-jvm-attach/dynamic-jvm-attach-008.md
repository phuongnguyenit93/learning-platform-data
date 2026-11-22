# `detach` of the Control Connection Does Not Mean Unloading the Agent from the JVM

When a Java tool uses the **Attach API** to connect to a running JVM, it can load a **Java agent** into that process and then call `VirtualMachine.detach()`. Calling **detach** only ends the control tool's communication session with the target JVM. It is **not** equivalent to “unloading the agent”, does **not** automatically remove registered `ClassFileTransformer` instances, does not revert modified bytecode, and does not force threads/services created by the agent to stop running.

The core takeaway: you must manage **two independent lifecycles** — the lifecycle of the *control connection* and the lifecycle of the *agent logic running inside the target JVM*. This is foundational knowledge for writing attach tools, tracers, profilers, APMs, or runtime observation agents properly.

## 1. Separating Three Entities: Controller, Attach Connection, and Agent in the Target JVM

Suppose the application is running in JVM B, while the control program is in JVM A:

```text
JVM A — AttachController                  JVM B — TargetApp
┌──────────────────────────────┐         ┌────────────────────────────────────┐
│ VirtualMachine.attach(pid)  │────────>│ JVM B's Attach listener/service    │
│                              │         │                                    │
│ vm.loadAgent("agent.jar")   │────────>│ Loads agent.jar and calls agentmain(...)│
│                              │         │   ├─ Updates state inside the JVM  │
│                              │         │   ├─ Registers ClassFileTransformer │
│                              │         │   └─ May create threads/resources  │
│ vm.detach()                  │ --X--  │                                    │
│ Control connection ends      │         │ JVM B keeps running: agent         │
│                              │         │ callbacks can continue receiving events │
└──────────────────────────────┘         └────────────────────────────────────┘
```

In the diagram, `--X--` marks **terminating the controller's attach session**. It does not represent a command asking JVM B to remove agent classes or restore the entire initial state.

| Component | Location | After the controller calls `detach()` successfully |
| --- | --- | --- |
| `com.sun.tools.attach.VirtualMachine` object | Controller's JVM memory | Can no longer be used to operate on the detached session; calling further operation methods throws `IOException` per the API. |
| Attach connection/session | Between the two JVMs | Released according to the attach provider's mechanism. |
| Loaded Java agent | Target JVM | Components that remain referenced or active can continue to exist and run. |
| `Instrumentation` received via `agentmain` | Target JVM | Remains a runtime service object that the agent can use while holding a reference; detach does not revoke it. |
| Registered `ClassFileTransformer` | Target JVM's instrumentation registry | Continues to be invoked for eligible load/redefine/retransform operations until explicitly removed or the JVM exits. |
| Transformed bytecode and application state | Target JVM | Does not automatically revert to the initial state merely because the controller detached. |
| Target JVM and running threads | Target JVM | Are not terminated merely by the detach operation. |

**An easy-to-picture analogy:** opening a remote control panel, enabling a monitoring feature in the application, and then closing the control session. Closing the session does not mean the monitoring feature has been turned off.

## 2. Exact Semantics of Attach API Calls

A common attach sequence using the `jdk.attach` API:

```java
// Snippet illustrating the control flow, not a standalone program.
VirtualMachine vm = VirtualMachine.attach(pid);
try {
    vm.loadAgent(agentJarAbsolutePath, "mode=observe");
} finally {
    vm.detach();
}
```

- `VirtualMachine.attach(pid)`: requests attaching to a target JVM with the matching identifier (typically the PID on HotSpot and standard process environments). It returns a **communication handle** in the control tool's process, without moving the entire target JVM into the controller process.
- `vm.loadAgent(path, options)`: requests the target JVM to load a **Java agent JAR**; the JAR must have the `Agent-Class` manifest attribute and that class must define `public static void agentmain(String, Instrumentation)` or `agentmain(String)`. With this call, the agent executes **inside the target JVM**.
- According to the Java 17 documentation, `loadAgent(...)` returns when the `agentmain(...)` call completes. That does **not** mean all services/threads/callbacks initialized by `agentmain` have finished; they may intentionally be long-running.
- `vm.detach()`: releases the control session. After detach, attempting to call `vm.getSystemProperties()` or `vm.loadAgent(...)` on the **same handle** will cause an `IOException`. To perform further operations, the controller must attach again and obtain a new handle, provided the target JVM still supports attach and is still running.

A `loadAgent` call executing concurrently with `detach` on the same handle is a race condition; the Attach API documentation states that whether the in-progress operation completes or throws `IOException` is **implementation-dependent**. The `try/finally` pattern above executes sequentially: **wait for `loadAgent` to return, then detach**.

An important point about *API objects*: `VirtualMachine` is the **controller-side** handle, whereas `Instrumentation` is the interface that the agent receives **inside the target JVM**. There is no contract stating that `VirtualMachine.detach` will call `Instrumentation.removeTransformer`, close the agent's resources, or unload all agent classes.

## 3. Hands-On Java 17+: Observing the Transformer Still Active After `detach`

This experiment uses **two Java processes** and one Java agent:

- `TargetApp`: the running target application, waiting for commands on stdin to read state or load a new class.
- `MarkerAgent`: loaded into `TargetApp` via the Attach API, sets a system property, and registers a `ClassFileTransformer` that only **logs when the `LateLoaded` class is loaded**. The transformer **does not modify bytecode** because it returns `null`.
- `AttachController`: another process that calls `attach → loadAgent → detach` and then exits.

Only after the controller prints `CONTROLLER detached` and exits do we instruct the target JVM to load `LateLoaded`. If the transformer still prints a log message, we have direct proof that the `detach` operation **does not unregister the transformer**.

### 3.1. File Structure

```text
attach-demo/
├── src/
│   └── demo/
│       └── attach/
│           ├── TargetApp.java
│           ├── LateLoaded.java
│           ├── MarkerAgent.java
│           └── AttachController.java
└── agent.mf
```

The listings below are **four standalone Java files matching the exact file/class names**, plus one manifest file.

### 3.2. `src/demo/attach/TargetApp.java`

```java
package demo.attach;

import java.io.BufferedReader;
import java.io.InputStreamReader;

public final class TargetApp {
    private TargetApp() {
    }

    public static void main(String[] args) throws Exception {
        System.out.println("TARGET ready");

        BufferedReader reader =
                new BufferedReader(new InputStreamReader(System.in));

        String command;
        while ((command = reader.readLine()) != null) {
            switch (command) {
                case "check" -> System.out.println(
                        "TARGET state=" +
                        System.getProperty("demo.agent.state", "absent"));
                case "load" -> {
                    Class.forName("demo.attach.LateLoaded");
                    System.out.println("TARGET class loaded");
                }
                case "quit" -> {
                    System.out.println("TARGET stopped");
                    return;
                }
                default -> System.out.println("TARGET unknown command");
            }
        }
    }
}
```

This application does not import `MarkerAgent`; it only observes a system property of the **target process itself**. The `load` command uses `Class.forName(String)` to load `LateLoaded` on demand. Because the class name here is in a string literal, the class does not need to be loaded beforehand just to run `main`.

### 3.3. `src/demo/attach/LateLoaded.java`

```java
package demo.attach;

public final class LateLoaded {
    private LateLoaded() {
    }
}
```

This is a test class that is only requested to be loaded after attach/detach. It intentionally has no side effects so that logs produced by the transformer can be distinguished from logs executed by the class itself.

### 3.4. `src/demo/attach/MarkerAgent.java`

```java
package demo.attach;

import java.lang.instrument.Instrumentation;

public final class MarkerAgent {
    private MarkerAgent() {
    }

    public static void agentmain(
            String options, Instrumentation instrumentation) {

        System.setProperty("demo.agent.state", "ACTIVE");

        instrumentation.addTransformer(
                (loader, className, classBeingRedefined,
                 protectionDomain, bytes) -> {
                    if ("demo/attach/LateLoaded".equals(className)) {
                        System.out.println("AGENT saw LateLoaded");
                    }
                    return null; // Do not modify the class bytes.
                },
                false);

        System.out.println("AGENT installed");
    }
}
```

The agent uses the `agentmain` entry point because it is **attached after the application is already running**, rather than using `-javaagent`'s `premain`. Calling `addTransformer(..., false)` registers a callback for eligible class loads/redefinitions and does not require the retransformation capability. `return null` is the valid way to indicate “do not transform bytecode”.

Note: no `static` field holding the transformer is needed in an observation-only example. The instrumentation registry holds the callback registration, so the agent can still receive events after `agentmain` has returned and the controller has detached. If you want to **remove the transformer on demand**, a real-world agent must proactively **keep a reference** to the registered transformer to pass to `removeTransformer` later.

### 3.5. `src/demo/attach/AttachController.java`

```java
package demo.attach;

import com.sun.tools.attach.VirtualMachine;
import java.nio.file.Path;

public final class AttachController {
    private AttachController() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println(
                    "Usage: AttachController <target-pid> <agent-jar>");
            return;
        }

        String pid = args[0];
        String agentPath =
                Path.of(args[1]).toAbsolutePath().normalize().toString();

        VirtualMachine vm = VirtualMachine.attach(pid);
        try {
            vm.loadAgent(agentPath, "demo");
            System.out.println("CONTROLLER loaded");
        } finally {
            vm.detach();
            System.out.println("CONTROLLER detached");
        }
    }
}
```

The API calls in the controller connect to the **target JVM**, but the `CONTROLLER ...` logs appear in the **controller's terminal**. `MarkerAgent.agentmain` and the transformer, on the other hand, print in **TargetApp's terminal**. `finally` ensures the controller attempts to detach whether `loadAgent` succeeds or throws an error, as long as `attach` returned a handle.

### 3.6. Creating the Agent Manifest

The full contents of `agent.mf` (with a trailing newline):

```text
Manifest-Version: 1.0
Agent-Class: demo.attach.MarkerAgent

```

The `Agent-Class` attribute is required for a Java agent loaded via `VirtualMachine.loadAgent`. `Premain-Class` is used when launching with `-javaagent` and does not replace `Agent-Class` in this experiment.

### 3.7. Compiling and Packaging

Open a terminal in the `attach-demo/` directory. Create the output directory first:

```bash
mkdir out
```

If `out` already exists, skip the directory creation command. With JDK 17 or newer:

```bash
javac --add-modules jdk.attach -d out \
  src/demo/attach/TargetApp.java \
  src/demo/attach/LateLoaded.java \
  src/demo/attach/MarkerAgent.java \
  src/demo/attach/AttachController.java

jar --create --file marker-agent.jar \
  --manifest agent.mf \
  -C out demo/attach/MarkerAgent.class
```

The lines with `\` for line continuation use Bash-style shell syntax. If using Windows PowerShell, enter the entire `javac` or `jar` command on **one line**, for example:

```powershell
javac --add-modules jdk.attach -d out src/demo/attach/TargetApp.java src/demo/attach/LateLoaded.java src/demo/attach/MarkerAgent.java src/demo/attach/AttachController.java
jar --create --file marker-agent.jar --manifest agent.mf -C out demo/attach/MarkerAgent.class
```

The `VirtualMachine.attach` method belongs to the **JDK module `jdk.attach`**. The `--add-modules jdk.attach` option makes the intent to use the module explicit. The Instrumentation APIs belong to the `java.instrument` module, which is typically resolved automatically on a full JDK environment.

> This runnable example uses a simple classpath with Java 17+. No Maven, Gradle, or Byte Buddy libraries are needed.

## 4. Running in Two Terminals and Reading the Output Correctly

### Step A — Start the Target Application

**Terminal 1** in `attach-demo/`:

```bash
java -cp out demo.attach.TargetApp
```

Initial stdout:

```text
TARGET ready
```

Keep Terminal 1 open. Type `check` and press Enter to confirm the agent has not been loaded yet. The application prints exactly:

```text
TARGET state=absent
```

### Step B — Find the Target JVM's PID

**Terminal 2** in the same directory:

```bash
jps -l
```

In the list, find the line with main class `demo.attach.TargetApp`. The PID changes on each run; an illustrative example is:

```text
43120 demo.attach.TargetApp
```

**Replace the sample PID with the actual PID** of `TargetApp` on your machine; `jps` may display other JDK processes as well. You can use your OS process management tools if the environment does not support `jps`.

### Step C — Attach, Load the Agent, and Detach

**Terminal 2**, replacing `43120` in the example with the actual PID:

```bash
java --add-modules jdk.attach -cp out \
  demo.attach.AttachController 43120 marker-agent.jar
```

On PowerShell, write it on one line:

```powershell
java --add-modules jdk.attach -cp out demo.attach.AttachController 43120 marker-agent.jar
```

When attach succeeds, the **controller's stdout (Terminal 2)** is:

```text
CONTROLLER loaded
CONTROLLER detached
```

Meanwhile, **Terminal 1** receives the line printed by `agentmain` running inside the target JVM:

```text
AGENT installed
```

Thus, after seeing `CONTROLLER detached`, the controller's Attach session has ended. However, the agent has just registered a transformer inside TargetApp and no call has been made to remove it.

### Step D — Verify That the Agent's Effects Still Persist

Back in **Terminal 1**, type `check` and press Enter:

```text
TARGET state=ACTIVE
```

This shows that the system property set by the agent in the target JVM **was not cleared by `detach`**.

Next, type `load` and press Enter:

```text
AGENT saw LateLoaded
TARGET class loaded
```

The line `AGENT saw LateLoaded` was printed **after detach** by the **ClassFileTransformer registered before detach**, right when TargetApp loaded a new class. This is stronger evidence than just seeing the system property still present: **the instrumentation callback remains active even though the controller has disconnected**.

Finally, type `quit` and press Enter:

```text
TARGET stopped
```

The application exits normally. The output lines above are the **exact stdout content of the sample program at each step**, excluding the commands you typed, the PID list, any JVM/diagnostic logs that may appear, and output lines from previous steps.

## 5. Does `detach()` Make the Agent “Disappear”?

There is no general `unloadAgent()` API corresponding to `VirtualMachine.loadAgent()` in the **standard Java Instrumentation API**. Once an agent has been loaded, several independent kinds of state can exist:

| What the agent set up | After detach | What is needed to stop/reclaim it? |
| --- | --- | --- |
| `ClassFileTransformer` | Continues receiving eligible callbacks | The agent calls `Instrumentation.removeTransformer(transformer)` with the **exact reference** that was registered. |
| Bytecode of transformed classes | The control session does not revert it | May require `retransformClasses`/`redefineClasses` subject to capabilities, transformation rules, and appropriate bytes; there is no automatic “undo” guarantee. |
| Threads/schedulers created by the agent | May continue running, even keeping the JVM alive if non-daemon threads | The agent needs cooperative shutdown: setting a stop flag, calling `interrupt` appropriately, closing schedulers/executors, and awaiting termination when needed. |
| Sockets, HTTP endpoints, file handles, MBeans | Not automatically closed/unregistered | The agent itself must close resources and unbind/unregister via each respective API. |
| System properties or static state | Retains values until changed elsewhere or the JVM stops | If restoration is needed, the agent must save the prior state and revert it intentionally, avoiding overwriting valid changes from other components. |
| Loaded classes/JARs | Cannot assume automatic unloading when the controller leaves | Class unloading is determined by GC and reachability/class loaders; agents and instrumentation structures often hold long-lived references. |
| Ability to re-attach | Depends on the running JVM and attach conditions | Create a new `VirtualMachine.attach(...)` session if you need to control it again. |

**Important:** `removeTransformer` **does not automatically restore** bytecode that the transformer already modified on loaded classes. It only unregisters the transformer for future processing; even after removal, an in-flight callback on another thread may still arrive due to a race. Meanwhile, `retransformClasses` requires JVM/manifest support and has rules for reapplying transformations from transformers that do not support retransformation; it is not a “revert everything” button.

Therefore, when implementing a real agent, you must separately define **stop instrumentation**, **cleanup resources**, and (if truly necessary) **conditional bytecode rollback**. You should not promise “stop = JVM state identical to before attach”, because loaded classes, JIT state, threads, static state, opened modules, and side effects may not be completely reversible.

## 6. Designing an Agent That Can Be Stopped in a Controlled Manner

An agent can store `Instrumentation` and the transformer object in static fields to unregister itself. The following snippet is **illustrative code placed inside an agent class**, **not a standalone Java program**:

```java
// Example members of an agent with its own control mechanism.
private static Instrumentation instrumentation;
private static ClassFileTransformer transformer;

public static synchronized void start(Instrumentation inst) {
    if (transformer != null) {
        return; // Avoid duplicate registration if agentmain is called again.
    }

    instrumentation = inst;
    transformer = (loader, name, type, domain, bytes) -> {
        // Observe or modify the class provided by the JVM.
        return null;
    };
    instrumentation.addTransformer(transformer, false);
}

public static synchronized void stop() {
    if (transformer != null) {
        instrumentation.removeTransformer(transformer);
        transformer = null;
    }
    // Continue stopping schedulers, endpoints, and other resources if any.
}
```

To call `stop()` **from outside the target JVM**, you need **a control mechanism designed by the agent/application**: for example, a JMX MBean with a stop operation, a secured management endpoint, an internal IPC channel, or a new attach call to send a control request to the agent. `VirtualMachine.detach()` itself **does not call** this stop method.

At the design level, you also need to address:

1. **Idempotence:** two consecutive start or stop commands must not create duplicate registrations or errors.
2. **Races:** an in-progress callback may overlap with the timing of stop; the transformer must tolerate callbacks arriving after `removeTransformer` due to concurrency.
3. **Resources:** release executors, sockets, MBeans, hooks, and references holding class loaders when needed.
4. **State management:** preserve data that other parts of the application may also have modified after the agent attached.
5. **Bytecode compatibility:** if you want to process already-transformed classes, evaluate capabilities and other mechanisms transforming the same classes, rather than blindly restoring old bytes that may no longer be valid.

A common strategy for profilers is to **stop collecting events** without promising to remove every bytecode trace of instrumentation. For agents that require completely removing all changes, reversibility must be designed in from the start and verified on the actual target JVM/version.

## 7. Easily Confused Differences Between Detach, Dispose, Remove, and JVM Exit

| Action | Affected entity | Meaning |
| --- | --- | --- |
| `VirtualMachine.detach()` | Controller's Attach handle/connection | Terminates the management session to the target JVM; **does not unload the agent**. |
| `Instrumentation.removeTransformer(t)` | Registration of transformer `t` in the target JVM | Stops most future callbacks for this registration; does not roll back already-transformed classes. |
| `ExecutorService.shutdown()` or custom stop mechanism | Tasks/resources managed by the agent | Performs partial shutdown as defined by the agent. |
| `Instrumentation.retransformClasses(...)` | Loaded classes, if supported by JVM/config | Reapplies the transformation process under special rules; results depend on currently registered transformers. |
| `Instrumentation.redefineClasses(...)` | Loaded classes, if supported by JVM/config | Replaces definitions with new class bytes within JVM limits; does not automatically clear all runtime side effects. |
| Controller process exits | External attach program | Does not mean the target JVM stops or the agent is cleaned up. |
| Target JVM exits | Entire target runtime | Java activities in that process terminate; only traces in external systems may persist depending on the agent. |

Separating these clearly helps when debugging “I closed the profiler UI, yet I still see agent logs” or “the attach tool exited, yet the application is still instrumented”. That behavior can be **completely expected according to the API**.

## 8. Real-World Scenarios

### Scenario A — The Attach Tool Is a Short-Lived Process

A monitoring tool runs for a few seconds to attach, `loadAgent`, `detach`, and then exit. The agent starts a long-running metric collection thread inside the target JVM. **There is no need to keep the controller alive** just for the thread inside the target JVM to continue working. To view metrics, you need an endpoint or extraction mechanism designed by the agent; the agent's existence **does not automatically provide** a management channel after detach.

### Scenario B — Closing the Management Window While the JVM Keeps Logging

The management window may have called `VirtualMachine.detach` successfully. If the agent's transformer is still registered, subsequent class loading events will still invoke the transformer and logs will still appear. The proper action is to instruct the agent to stop via its management channel, or restart the target JVM if no stop path exists.

### Scenario C — The Controller Tries to Call a Method on the Old Handle

After:

```java
// Illustrative Java snippet. vm is a VirtualMachine that was attached successfully.
vm.detach();
vm.getSystemProperties(); // IOException per the API contract.
```

That handle cannot be reused for attach operations. This **only proves the controller is no longer connected**; it says nothing about whether the agent has stopped.

### Scenario D — Closing the Connection Before `agentmain` Completes

If multiple threads in the controller call `loadAgent` and `detach` on the same handle simultaneously, you must not rely on the load call always succeeding: the `VirtualMachine.detach` documentation specifies that the outcome of an in-progress operation is implementation-dependent. Therefore, the normal workflow must **wait for `loadAgent` to complete before detaching**. For asynchronous agent tasks, the agent is responsible for coordinating its own tasks.

### Scenario E — Seeing Instrumented Classes Even After Removing the Transformer

If the transformer previously injected bytecode into a method, `removeTransformer` only unregisters processing for future definitions; classes that already have the transformed definition installed still carry that bytecode. To modify a running class back, you must consider the retransform/redefine APIs, JVM capabilities, class structure change limitations, and other active transformers.

## 9. Common Pitfalls and How to Check Them

| Symptom | Explanation / Verification Step |
| --- | --- |
| `detach` succeeds but the agent continues logging | Not necessarily a bug: check transformers, threads, and endpoints still active in the target JVM. |
| Controller calls an API on a detached `VirtualMachine` and gets `IOException` | API contract: the handle has been invalidated; re-attach if needed. |
| `loadAgent` fails to run | Check that the JVM has an attach provider and proper permissions; check PID, process owner, JVM options, and JAR/manifest. |
| `ClassNotFoundException` / agent load failure | Check `Agent-Class`, JAR location, and dependencies that the target JVM can load. |
| `AGENT saw LateLoaded` does not appear in the lab | Ensure you type `load` **after the controller detaches**, the class was not loaded earlier, and the agent JAR installed the transformer successfully. |
| Removed transformer yet still see one more log | A callback may have been executing concurrently during removal; set a stop flag and handle the race. |
| Expecting bytecode to automatically revert after stop | `removeTransformer` is not a rollback; a dedicated restoration strategy must be designed. |
| Running the controller on a stripped-down JRE fails with `jdk.attach` error | The module may not be packaged; use a JDK/runtime that includes `jdk.attach` and attach support. |
| Attempting to attach to a blocked JVM | Some JVMs/configurations, container environments, or OS permissions do not allow the operation; use a test environment with proper permissions. |
| Confusing loading an agent with connecting a debugger | The Attach API can load an instrumentation agent; a JDWP debugger has its own protocol, connection lifecycle, and operations. Do not use `VirtualMachine.detach` as a universal “detach debugger”. |

If you see the agent still active after the controller exits, do not look only at the controller's PID. Observe the **target application's PID**, target-side logs, new class loads/transforms, threads/resources still held by the agent, and the state of the control endpoint if any.

## 10. Self-Check

**Question 1.** The controller calls `attach → loadAgent → detach`, and afterward the target application loads a new class and the newly registered transformer is invoked. Is that behavior correct or incorrect?

**Answer:** Correct. `detach` ends the controller's Attach connection, while the transformer registered in the target JVM continues to exist until it is removed or the JVM exits.

**Question 2.** After detach, can `vm.loadAgent(...)` be called again using the detached `vm` object?

**Answer:** No. Subsequent operations on a detached `VirtualMachine` handle will throw `IOException`; you must attach again to obtain a new handle if the target JVM allows it.

**Question 3.** When the agent calls `Instrumentation.removeTransformer(t)`, do all methods modified by `t` automatically revert to their old code?

**Answer:** No. That call unregisters the transformer; it does not guarantee reverting bytecode previously installed into classes.

**Question 4.** Does `agentmain` returning prove that all threads started by the agent have stopped?

**Answer:** No. `agentmain` can create threads or register callbacks to run long-term. `loadAgent` waits for `agentmain` to return, not for all background work to finish.

**Question 5.** An agent wants a “Stop monitoring” button after the initial controller exits. What needs to be designed?

**Answer:** A new management channel or maintaining the ability to receive commands, storing the transformer reference, coordinating the shutdown of callbacks/threads/resources, and explicitly calling cleanup APIs. Do not rely on `VirtualMachine.detach` to do this.

## 11. Summary and References

- **`detach()` only stops an Attach session**, not an unload-agent call. It renders the controller's `VirtualMachine` handle unusable.
- **`loadAgent(...)` invokes `agentmain(...)` in the target JVM**. After `agentmain` returns, the callbacks, class transformations, and resources set up by the agent can continue operating.
- **Stopping instrumentation** must be managed by the agent using `removeTransformer` and appropriate cleanup; restoring transformed bytecode is a separate, conditional problem.
- **To prove the difference**, test a new effect of the agent **after the controller detaches**, such as the transformer in the lab logging when the `LateLoaded` class is loaded.

Official Java SE 17 Documentation:

1. **`com.sun.tools.attach.VirtualMachine`** — `attach`, `loadAgent`, `detach`, and handle lifecycle: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html
2. **`java.lang.instrument` package** — Java agent mechanism, `Agent-Class`, `agentmain`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
3. **`Instrumentation`** — `addTransformer`, `removeTransformer`, `retransformClasses`, `redefineClasses`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
4. **`ClassFileTransformer`** — callback rules and `return null`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
