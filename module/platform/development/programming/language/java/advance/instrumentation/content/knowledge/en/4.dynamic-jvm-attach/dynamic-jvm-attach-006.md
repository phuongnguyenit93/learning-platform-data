# Initializing an Agent When the Application Is Already Running and Classes May Already Be Loaded

## 1. The Problem to Solve

A Java service may have been running for hours before the development team needs to enable diagnostics, record metrics, or observe a method. At that point, many classes have already been loaded by the JVM, objects are live, and threads are executing. **Attaching an agent to a running JVM** solves two distinct problems: **(1) initializing an agent inside an existing process**; **(2) handling classes that were already loaded before the agent registered its transformer**.

This lesson explains `agentmain`, `VirtualMachine.attach/loadAgent`, `Instrumentation`, loaded and unloaded classes, `ClassFileTransformer`, `retransformClasses`, `redefineClasses`, and limitations regarding state, threads, and safety. At the end, there is a **Java 17+** JDK-only example showing an agent attached after the target class has already been loaded and actively routing that class through the transformer callback.

**Key takeaway upfront:** a successful attach does not cause every previously loaded class to automatically pass through the new transformer. And even if the bytecode of a loaded class is reprocessed, the agent **cannot retroactively reconstruct calls that occurred before it was installed**, unless the system already has another telemetry source recording them.

## 2. Timeline: Before and After Dynamic Attach

~~~text
t0: JVM starts, runs the application's main()
    |
t1: JVM loads ServiceA.class; calls to A have already occurred
    |
t2: JVM loads ServiceB.class; calls to B have already occurred
    |
t3: External tool attaches to the target JVM
    |
t4: JVM invokes agentmain(agentArgs, instrumentation)
    |
t5: Agent registers ClassFileTransformer
    |   +--> ClassC newly loaded after t5: transformer can be invoked
    |
t6: Agent requests retransformClasses(ServiceA.class)
    |   +--> Transformer supporting retransform processes the already-loaded class A
    |
t7: Threads, objects, and the application continue running
~~~

At **t5**, `addTransformer` sets up a callback for classes defined or transformed by the JVM *after the registration time*. `ServiceA` and `ServiceB` have already passed their initial loading phase, so they **do not automatically trigger new callbacks just because the agent appeared**.

At **t6**, if the JVM supports it and `ServiceA` is a modifiable class, **`retransformClasses`** actively routes the existing class definition through the transformation pipeline. This is the core point of this lesson.

Comparison table:

| Question | Startup agent | Late-attached agent |
|---|---|---|
| When does the JVM load the agent? | When the launcher starts with `-javaagent` | When an attach request is made to a running JVM |
| Entry point | `premain(...)` | `agentmain(...)` |
| Manifest | `Premain-Class` | `Agent-Class` |
| Execution timing relative to the app | `premain` runs before `main` | The application may already be serving requests |
| Already-loaded classes | Can usually install transformers early for the app | Must account for already-loaded classes and reprocessing capability |
| Historical data | Does not automatically generate data before probes run | Does not reconstruct events that occurred before attach |

A single JAR can support both startup mechanisms, but `loadAgent` invokes `agentmain` from **`Agent-Class`**, whereas `-javaagent` invokes `premain` from **`Premain-Class`**. `Main-Class` is only used for executable JARs run via `java -jar`.

## 3. How Does the Attach API Work?

The **`jdk.attach`** module provides `com.sun.tools.attach.VirtualMachine` in JDKs that implement the Attach API. Typical mechanism:

~~~text
  Attach tool JVM                          Target application JVM
  ---------------                          ----------------------
  VirtualMachine.attach(pid) ---------> connects to the running JVM
  vm.loadAgent(agentJar, args) --------> reads agent JAR and Agent-Class
                                       loads the agent class
                                       invokes agentmain(args, Instrumentation)
                                           |
                                           +--> registers transformer
                                           +--> inspects loaded classes
                                           +--> may retransform
  loadAgent returns         <----------- agentmain completes
  vm.detach()                          Target JVM continues running
~~~

**Three roles to distinguish:**

1. **Target application:** the JVM currently performing work, holding existing objects and threads.
2. **Attach tool:** another JVM process that calls `VirtualMachine.attach(pid)`, `loadAgent(path, options)`, and `detach()`.
3. **Agent code:** a class with `public static void agentmain(...)`; this method **runs inside the target JVM** and receives the `Instrumentation` object provided by the target JVM.

`loadAgent` uses **a file path interpreted by the target JVM**. Inside containers, the same path string on the host does not necessarily point to the file inside the container. `detach()` only closes the Attach API connection; it **does not automatically remove transformers, stop agent threads, revert bytecode, or clear metrics**.

Attaching also depends on the JVM vendor, security configuration, OS permissions, PID namespaces, and startup options. Do not assume every JVM allows attach, and do not rely on self-attach because many HotSpot builds disallow a process from attaching to itself by default.

## 4. APIs to Identify and Process Already-Loaded Classes

### 4.1. Inspecting a Snapshot of Loaded Classes

`Instrumentation.getAllLoadedClasses()` returns an array of `Class<?>` objects currently held by the JVM at the time of the query. This includes many non-application classes such as frameworks, JDK classes, arrays, or hidden classes. You should not take the entire array and call retransform in bulk.

~~~java
Class<?> target = Arrays.stream(inst.getAllLoadedClasses())
        .filter(c -> c.getName().equals("lab.TargetService"))
        .findFirst()
        .orElse(null);
~~~

**This code is a snippet, not a standalone program.** It is suitable for a simple example with only one class loader. In Spring Boot, application servers, plugin systems, or OSGi, two loaders can create **two separate classes even with the same binary name**; you must filter by the right class loader, module, and class source before acting.

This is a **snapshot** and does not freeze class loading. A class may appear immediately after the snapshot is taken.

### 4.2. JVM Capabilities and Per-Class Modifiability

Before calling `retransformClasses(target)`, check:

~~~java
if (inst.isRetransformClassesSupported()
        && target != null
        && inst.isModifiableClass(target)) {
    inst.retransformClasses(target);
}
~~~

This is also a **snippet**, used in a context where `inst` and `target` are available.

- `isRetransformClassesSupported()` is a capability of the current JVM configuration and the agent. The agent needs to declare **`Can-Retransform-Classes: true`** in its manifest, and the VM must support it.
- `isModifiableClass(target)` indicates whether a specific class can be modified via the instrumentation mechanism. Array and primitive classes are not modifiable; other kinds of classes may also be restricted.
- `retransformClasses(target)` requests the JVM to perform the retransformation process on that class. It **does not mean every bytecode change will be accepted**.

For a **new transformer**'s callback to be invoked during retransformation, register it with:

~~~java
inst.addTransformer(transformer, true);
~~~

If you use `addTransformer(transformer, false)`, that transformer's callback **will not be newly invoked** during retransformation; the JVM may reuse results previously computed by non-retransformation-capable transformers from earlier phases.

### 4.3. Retransform and Redefine Are Not the Same

- **Retransform:** `retransformClasses(Class<?>... classes)` reruns the transformer pipeline on existing class definitions (according to JVM semantics). It is typically suited for applying an instrumenter to already-loaded classes.
- **Redefine:** `redefineClasses(ClassDefinition... definitions)` takes **replacement classfile bytes** supplied by the agent, such as in hot-replace/debugger workflows. It requires `Can-Redefine-Classes: true` and VM support.
- The two capabilities are **independent**; enabling one attribute does not implicitly enable the other.
- Both are subject to constraints on structural class changes, bytecode verification, and unmodifiable classes.

**Important limitation:** retransform/redefine must not be understood as reinitializing a class or restarting the application. **Static initializers do not rerun just because of this operation; static fields and existing objects retain their state**. Stack frames currently executing an old method may continue running the old bytecode; **new method calls** use the updated definition after the update succeeds.

## 5. Java 17+ Hands-On: Agent Appearing After the Class Is Loaded

This demo creates two JVMs: the target JVM preloads `lab.TargetService`, while the attach JVM instructs it to load the agent late. The transformer in the example **only prints in the callback and returns `null`**, meaning it **does not alter bytecode**. This lets the example accurately verify the `agentmain` and retransform mechanics without needing ASM/Byte Buddy.

### 5.1. Directory Structure

~~~text
late-attach-lab/
├── agent.mf
├── src/
│   ├── TargetService.java
│   ├── TargetApp.java
│   ├── LiveAgent.java
│   └── AttachTool.java
├── out/                      # generated during compilation
└── agent.jar                 # generated by the jar command
~~~

### 5.2. Class Loaded Before Attach

File **`src/TargetService.java`**:

~~~java
package lab;

public final class TargetService {
    public String work() {
        return "OK";
    }
}
~~~

File **`src/TargetApp.java`**:

~~~java
package lab;

public final class TargetApp {
    public static void main(String[] args) throws Exception {
        TargetService service = new TargetService();
        System.out.println("target-ready:" + service.work());
        System.out.flush();
        Thread.sleep(20000);
    }
}
~~~

By the time the program prints **`target-ready:OK`**, `TargetService` has already been loaded and its instance has already been used. `Thread.sleep(20000)` keeps the target JVM alive for about 20 seconds so you can open another terminal and attach. During manual practice, if the JVM has already exited, run it again to get a new PID.

### 5.3. Dynamic Agent and ClassFileTransformer

File **`src/LiveAgent.java`**:

~~~java
package lab;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.Arrays;

public final class LiveAgent {
    public static void agentmain(String agentArgs, Instrumentation inst)
            throws Exception {
        System.out.println("agentmain:" + agentArgs);

        Class<?> target = Arrays.stream(inst.getAllLoadedClasses())
                .filter(c -> c.getName().equals("lab.TargetService"))
                .findFirst()
                .orElse(null);

        System.out.println("already-loaded:" + (target != null));
        System.out.println(
                "retransform-supported:" + inst.isRetransformClassesSupported()
        );

        if (target == null || !inst.isRetransformClassesSupported()
                || !inst.isModifiableClass(target)) {
            return;
        }

        ClassFileTransformer transformer = new ClassFileTransformer() {
            @Override
            public byte[] transform(ClassLoader loader, String className,
                    Class<?> classBeingRedefined, ProtectionDomain domain,
                    byte[] bytes) {
                if ("lab/TargetService".equals(className)) {
                    System.out.println(
                        "transform-existing:" + (classBeingRedefined != null)
                    );
                }
                return null; // Do not modify bytecode in this experiment.
            }
        };

        inst.addTransformer(transformer, true);
        try {
            inst.retransformClasses(target);
        } finally {
            inst.removeTransformer(transformer);
        }
    }
}
~~~

Full explanation:

1. The JVM calls **`agentmain`** after the Attach API requests loading the agent. The `agentArgs` parameter is passed verbatim as a string from the helper.
2. **`getAllLoadedClasses`** allows finding `TargetService` that was loaded earlier; if not found, the demo reports `already-loaded:false` and stops.
3. The capability flag and **`isModifiableClass`** ensure we do not attempt retransformation when it is known upfront to be unsupported.
4. **`addTransformer(transformer, true)`** registers a transformer capable of participating in retransformation, unlike the default `false` flag.
5. **`retransformClasses(target)`** asks the JVM to revisit the existing class. Inside the callback, `classBeingRedefined != null` indicates that the JVM passed a reference to the class being retransformed, rather than a class being loaded for the first time.
6. **`return null`** means this transformer provides no replacement bytes. This is a callback-mechanism demo; **it creates no actual measurement probes**.
7. **`removeTransformer`** unregisters the callback after one attempt. It does not exit the JVM, does not unload the agent, and does not automatically revert bytecode modified in a different example.

A continuously monitoring production agent typically **keeps the transformer registered** to handle newly loaded classes, manages its lifecycle, and avoids attaching duplicates. This demo removes it immediately to verify **a single operation**.

### 5.4. Main Manifest of the Agent JAR

File **`agent.mf`**, ending with a newline:

~~~text
Manifest-Version: 1.0
Agent-Class: lab.LiveAgent
Can-Retransform-Classes: true

~~~

**`Agent-Class`** is the required attribute for the JVM to invoke `agentmain` via dynamic attach; `Premain-Class` is used for `-javaagent` at startup. **`Can-Retransform-Classes: true`** requests the retransform capability; the VM still reserves the right to report it as unsupported. `Main-Class` is not needed in this agent JAR.

**Manifest note:** Attributes belong in the main section of **`META-INF/MANIFEST.MF`** inside the JAR. Use `jar --manifest agent.mf` so the tool generates the entry properly; the source manifest file must have a trailing newline, with attribute lines formatted as `Name: value`.

### 5.5. Attach Tool in a Separate JVM

File **`src/AttachTool.java`**:

~~~java
package lab;

import com.sun.tools.attach.VirtualMachine;

public final class AttachTool {
    public static void main(String[] args) throws Exception {
        VirtualMachine vm = VirtualMachine.attach(args[0]);
        try {
            vm.loadAgent(args[1], "late-load");
        } finally {
            vm.detach();
        }
        System.out.println("attached");
    }
}
~~~

`args[0]` is the **PID of the target JVM**; `args[1]` is the **JAR path readable by the target JVM**. The option `"late-load"` is passed into `agentmain` as a single string and is not automatically parsed into name–value parameters.

`VirtualMachine` belongs to the JDK `jdk.attach` module, so the demo uses the `--add-modules jdk.attach` option when compiling/running the helper. The tool can connect to the target JVM if the JVM, permissions, and platform allow it; there is no guarantee across every JRE or locked-down environment.

### 5.6. Compiling with the JDK

In the root directory **`late-attach-lab`**, create `out`. In Bash:

~~~bash
mkdir -p out
~~~

In PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out
~~~

Compile all sources targeting Java 17:

~~~bash
javac --release 17 --add-modules jdk.attach -d out src/TargetService.java src/TargetApp.java src/LiveAgent.java src/AttachTool.java
~~~

Create the agent JAR containing only the agent class:

~~~bash
jar --create --file agent.jar --manifest agent.mf -C out lab/LiveAgent.class
jar --list --file agent.jar
~~~

Important entry list:

~~~text
META-INF/
META-INF/MANIFEST.MF
lab/LiveAgent.class
~~~

Because the files are in `package lab;`, the class entry must be **`lab/LiveAgent.class`**. Using `-C out lab/LiveAgent.class` avoids accidentally including the `out/` prefix inside the JAR. `TargetApp`, `TargetService`, and `AttachTool` only need to be in `out` for the demo, not inside the agent JAR.

### 5.7. Running Two Terminals and Observing Output

**Terminal A**: start the target application. On HotSpot builds supporting the following flag, enable dynamic-agent loading explicitly:

~~~bash
java -XX:+EnableDynamicAgentLoading -cp out lab.TargetApp
~~~

The target JVM prints:

~~~text
target-ready:OK
~~~

This is the moment the target class is loaded. Within 20 seconds, in **terminal B** run:

~~~bash
jps -l
~~~

Find the line named `lab.TargetApp`; the number at the start of the line is the **target PID**. Replace the illustrative PID **`12345`** and the path `/absolute/path/to/agent.jar` with values appropriate for your OS/target JVM:

~~~bash
java --add-modules jdk.attach -cp out lab.AttachTool 12345 /absolute/path/to/agent.jar
~~~

In terminal B, if `loadAgent` succeeds, stdout is:

~~~text
attached
~~~

In **terminal A** (target JVM), on a JVM supporting the required features, the additional lines are:

~~~text
agentmain:late-load
already-loaded:true
retransform-supported:true
transform-existing:true
~~~

These lines prove:

- `agentmain` ran after the application had already started.
- `TargetService` was in the set of already-loaded classes.
- The JVM supports retransformation for the configured agent.
- The transformer received a callback on an **already-existing** class, triggered by the `retransformClasses` call.

**No message proves that method behavior was altered**, because the demo's transformer returns `null`. If the target exited before attach, run it again and grab the new PID. If the JVM implementation does not support the startup flag, use that VM's policy instead of blindly adding an incompatible JVM flag.

### 5.8. Control Experiments

Temporarily remove the **`inst.retransformClasses(target)`** line from the demo, rebuild the JAR, and attach to **a new target JVM**. Because `TargetService` was loaded before the transformer was registered and the demo removes the transformer immediately, **`transform-existing:true`** will not appear. This demonstrates the boundary between **registering to handle new classes** and **actively processing existing classes**.

Similarly, if you change `Can-Retransform-Classes: false` in the manifest, on a JVM honoring this capability, `isRetransformClassesSupported()` will be **false** and the demo skips retransformation. Editing the manifest alone is not enough: you must **repackage a new JAR** and then attach to a new test JVM.

## 6. When Changing the Bytecode of a Loaded Class, What Is Preserved?

Retransformation is not a restart or a redeploy:

- **Objects and static state are not automatically cleared.** Existing fields, singleton state, and in-use instances continue to exist.
- **Static initializers do not rerun** solely because of `retransformClasses`.
- **Active frames:** If a thread is currently executing old bytecode of a retransformed method, that frame may continue running the old version. **New calls** to the method use the updated version after the change succeeds.
- **Past events are not automatically recorded.** A counter inserted today cannot accurately count invocations from yesterday.
- **Structural limitations:** On common JVMs like HotSpot, you cannot assume retransform allows arbitrarily changing the number of fields/methods, superclass, or signatures. Invalid bytecode will be rejected by the verifier or the API.
- **Per-class modifiability:** `isModifiableClass` can be false even when the JVM supports retransformation in general.

A real bytecode-transforming agent must generate valid class bytes and ensure verification (stack map frames, method descriptors, class file version, compatibility). ASM or Byte Buddy can be used in real projects. **The current example does not depend on them**, focusing instead on attach logic, class selection, and calling the APIs at the right time.

## 7. Concurrency and the Unobserved Window

The application is **not automatically frozen** while the agent attaches. Class loading, GC, network I/O, and requests can still occur. If the agent does:

~~~text
t1: snapshot = getAllLoadedClasses()
t2: application loads ClassX
t3: agent addTransformer(...)
t4: agent retransformClasses(selected snapshot)
~~~

then `ClassX` **may be missed** because it was loaded after the snapshot was taken but before the transformer took effect. Therefore, even when combining a transformer with a scan of existing classes, **do not claim 100% absolute class instrumentation** unless you have designed a solution for the race, defined coverage boundaries, and verified the results.

In production:

1. Only take a snapshot to find **the classes actually needed**; narrow the scope by class loader, module, package, and class name.
2. Check that classes are modifiable; batch/limit counts to avoid cost spikes.
3. Configure the transformer to exclude agent classes, core JVM classes, and internal dependencies to avoid recursion.
4. If continuous monitoring is needed, keep the transformer for future class loads and manage its lifecycle; if doing a one-off check, remove it in `finally`.
5. Record which classes were processed and how failures occurred; consider a bounded re-scan when races matter.
6. Account for multiple class loaders, JPMS access, and JVM implementation differences. Two classes with the same name do not necessarily have the same definition.
7. Avoid inserting heavy logging/locking into hot methods or running heavy network I/O inside `transform`.

## 8. Managing Agent Lifecycle After Attach

`agentmain` launches inside a live JVM, not an empty environment. An agent may create threads, metric exporters, timers, MBeans, or transformers. **`vm.detach()` does not tear down those resources.**

For real-world agents, design **idempotent initialization** (preventing repeated attaches from creating duplicate transformers/threads), maintain explicit initialized state, enforce telemetry bounds, and provide appropriate shutdown/reconfiguration mechanisms. If the agent transforms classes, **merely removing the transformer does not revert already-applied bytecode changes**; a separate restoration mechanism is needed if rollback is truly required. Do not assume a second attach command will automatically clean up the first attach's state.

Note on errors: per the `java.lang.instrument` specification, an initialization failure in `agentmain` during dynamic attach **does not require the target JVM to exit**, unlike a `premain` failure at startup. However, attach failures may surface in the helper as `AgentLoadException`, `AgentInitializationException`, or `IOException`, and side effects in the target JVM may still remain. Observe **both helper logs and target JVM logs**.

## 9. Permissions, JVM Flags, and Real-World Environments

The Attach API depends on JVM support and environment policies:

| Situation | What to verify |
|---|---|
| PID not found | JVM not running, already exited, different PID namespace, or `jps` cannot list it |
| `VirtualMachine.attach` rejected | Different user/permissions, incompatible attach provider, target disallows attach |
| `loadAgent` cannot find JAR | Path must be accessible by the **target JVM**, especially inside containers |
| JVM missing `jdk.attach` | Stripped runtime or does not provide the required Attach API |
| JVM does not recognize `Agent-Class` | Wrong manifest, class not inside JAR, or `agentmain` has wrong signature |
| `retransform-supported:false` | Missing capability in JAR or VM does not support it; do not force the API call |
| `isModifiableClass` false | Specific class cannot be modified; skip it and choose another approach |
| Bytecode transformer causes errors | Invalid bytecode, disallowed schema changes, class loading recursion |
| Agent runs but has no historical data | Probes appeared **after** the events being investigated |
| Target latency increases after attach | Transformer, retransform, or probes have overhead that must be measured and bounded |

### Changes Since JDK 21

**JDK 21's JEP 451** introduced warnings when agents are **dynamically loaded** into a running JVM without explicit opt-in, preparing to disallow it by default in future releases. On HotSpot builds implementing this flag, starting the target with **`-XX:+EnableDynamicAgentLoading`** explicitly permits dynamic loading; **`-XX:-EnableDynamicAgentLoading`** disallows dynamic agent loading. Default behavior may vary by **version/vendor/runtime configuration**, so verify in your actual environment and do not treat this guide as a guarantee that every JVM allows attach.

**Two non-interchangeable permissions:**

- Whether the JVM allows **dynamically loading an agent** into the target: attach mechanism/flags/policy.
- Whether the loaded agent is allowed to **retransform classes**: VM capability together with the **`Can-Retransform-Classes: true`** manifest attribute.

It is possible to attach successfully yet be unable to retransform; conversely, the manifest may properly request retransform while the target blocks agent loading.

If the application runs in a container, the PID namespace and filesystem may differ from the outside; an absolute path on the host **does not automatically mean** the path seen by the target JVM. When the platform forbids attach by policy, consider a startup agent in the next deployment, JFR, or platform-supported observability mechanisms.

## 10. Common Misconceptions

**Misconception 1: “`agentmain` ran, so every class now has probes inserted.”**  
False. The agent must select classes, register a transformer with the right capability, process existing classes when needed, and verify effectiveness on new calls.

**Misconception 2: “Calling `getAllLoadedClasses` itself instruments classes.”**  
False. That operation inspects the list of loaded classes; by itself it does not change any bytecode.

**Misconception 3: “Calling `addTransformer(transformer, true)` alone is enough for all existing classes.”**  
False. Normally an explicit retransform request is needed for already-loaded classes.

**Misconception 4: “`Can-Retransform-Classes: true` guarantees retransformation will work.”**  
False. The VM might not support it, and individual classes might not be modifiable.

**Misconception 5: “`return null` in the transformer modified the method.”**  
False. That signals **no replacement bytes** from that transformer. A callback having run and a class's behavior having changed are two different things.

**Misconception 6: “Running classes immediately switch to the new bytecode mid-method.”**  
False. Active frames may continue running the old bytecode; you must check new invocations.

**Misconception 7: “Once attached, I can query all past requests.”**  
False. Instrumentation code cannot reconstruct events that the system never collected.

**Misconception 8: “`vm.detach()` reverts the entire agent.”**  
False. It disconnects the Attach API control session; it does not automatically revert transformers/class bytes/hooks/threads.

**Misconception 9: “Same `Class.getName()` guarantees the same class.”**  
False. Class identity in the JVM also depends on the defining class loader; picking the wrong loader can cause you to miss the right target.

## 11. Exercises and Self-Check Questions

**Exercise A:** Run two terminals as in section 5, proving `TargetService` was loaded before attach via the `target-ready:OK` line and after attach via `already-loaded:true`. Why did the callback still run? Because the agent called **`retransformClasses`**.

**Exercise B:** Remove `retransformClasses(target)`, keep the rest, build the JAR, and test on a new JVM. Why does `transform-existing:true` no longer appear? Because a late-registered transformer does not retroactively process already-loaded classes.

**Exercise C:** Change the manifest to `Can-Retransform-Classes: false`, build a new JAR, and rerun on a new JVM. Explain what `retransform-supported:false` means and why the agent does not call `retransformClasses`.

**Exercise D:** Suppose there are two versions of `com.example.Service` loaded by two different class loaders. Propose a way to select the right `Class<?>` based on defining loader/module instead of only the name.

**Exercise E:** During a long-running request, attach and retransform a method while that method is executing. Why should you trigger a new request to verify the probe? Because the current frame may continue running the old bytecode.

**Quick questions:**

- Which entry point does dynamic attach use? **`agentmain`**, declared by **`Agent-Class`**.
- Which API tells you which classes are already loaded? **`getAllLoadedClasses()`**.
- What are the two key checks before retransforming? **`isRetransformClassesSupported()`** and **`isModifiableClass(target)`**.
- When does a new transformer get a callback for an existing class? When the JVM **performs retransformation** on an eligible class and the registered transformer supports it.
- Does `detach()` remove installed hooks? **No**.
- If you want invocation counts from before attach, what must you rely on? **Pre-existing telemetry**, not the new transformer.

## 12. Key Takeaways and Official Documentation

**Late attach initializes additional observability code inside a live JVM.** `agentmain` gives the agent access to `Instrumentation`, but already-loaded classes must be deliberately processed using `retransformClasses` or `redefineClasses` when appropriate and supported by the VM. Modifying classes does not replay history or reinitialize the entire application state. When investigating incidents, measure on **new events**, verify that the bytecode/probe actually took effect, and evaluate overhead under real traffic.

Official specification references:

- [Java SE 17 — java.lang.instrument](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): `Agent-Class`, `agentmain`, lifecycle, and manifest.
- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): loaded classes, transformers, retransformation, redefinition, and state.
- [Java SE 17 — Attach API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/package-summary.html): `VirtualMachine` and the `jdk.attach` module.
- [OpenJDK — JEP 451](https://openjdk.org/jeps/451): warning and permission changes for dynamically loading agents starting in JDK 21.