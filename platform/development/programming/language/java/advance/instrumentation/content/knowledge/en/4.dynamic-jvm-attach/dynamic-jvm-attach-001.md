# What Role Do the Attach API and the `jdk.attach` Module Play in Java?

## 1. The Problem: The Application Is Already Running, and We Want to Observe or Add Tooling

A production JVM may have been running for hours. When diagnostics are needed, we often want to gather information or activate measurement tools **without stopping the application and restarting it just to add options**. The **Attach API** is an interface provided by the JDK that allows a Java program acting as a **tool (attacher/client)** to connect to a **running target JVM (target VM)**, and then send requests supported by that JVM's attach mechanism.

Typical use cases:

- Discovering JVMs that the tool can detect and retrieving their identifiers.
- Reading administrative information such as system properties or agent properties of the target VM.
- Starting the target JVM's management agent/JMX when the API and configuration permit.
- Loading a **Java agent** after the JVM has started for observability, profiling, tracing, or inserting probes using `java.lang.instrument`.
- Loading a native agent through the JVM Tool Interface (JVM TI) when lower-level capabilities are needed.

**Core point:** *attach* means **establishing a control connection to a running JVM**; *load agent* is **an operation that can be performed over that connection**. Calling `VirtualMachine.attach(...)` alone does not automatically inject bytecode, does not automatically load an agent, and does not imply permission to modify code in every JVM.

## 2. What Is `jdk.attach`, Where Does It Live, and How Does It Differ from `java.instrument`?

Since **JDK 9**, the Attach API has been packaged as a JDK module named **`jdk.attach`**. This module exports two packages:

| Package | Role |
| --- | --- |
| `com.sun.tools.attach` | API for tools: `VirtualMachine`, `VirtualMachineDescriptor`, exceptions, and methods for attaching, reading information, and loading agents |
| `com.sun.tools.attach.spi` | Service Provider Interface: `AttachProvider` for JVM/system providers to implement how VMs are discovered and connected to |

Although the package names start with `com.sun`, they are **packages exported by the `jdk.attach` module with public Java API documentation**. However, `jdk.attach` is a specialized JDK module, not a Java SE library that every stripped-down runtime or alternative JVM is required to include. On **JDK 8**, the Attach API classes used to ship with tools in `tools.jar`; starting with the JDK 9+ module system, `tools.jar` is no longer added the old way.

The difference between the two commonly confused modules:

| Component | Where It Runs | Primary Responsibility |
| --- | --- | --- |
| **`jdk.attach`** | In the **tool JVM** calling the API | Discover target VMs, create connections, request agent loading or retrieve information |
| **`java.instrument`** | In the **target JVM**, where the Java agent runs | Provide the `Instrumentation` object to `premain`/`agentmain` so transformers can be registered and classes can be retransformed/redefined if supported |
| **Attach provider/transport** | Mechanism dependent on the JVM and OS | Perform communication between the tool VM and target VM |

For a **tool that is a named module**, declare the dependency in `module-info.java`:

~~~java
module com.example.attachtool {
    requires jdk.attach;
}
~~~

This is the **contents of a `module-info.java` file**, not a standalone runnable program. In an application running on the **class path** with a full JDK, the example below explicitly specifies `--add-modules jdk.attach` to instruct the runtime to resolve the module; it is not an operation to open internal packages with `--add-opens`. When using `jlink` to create a minimal runtime image, you must ensure that the `jdk.attach` module and the required attach provider are actually present **in the tool's runtime**. The target JVM must have a compatible attach mechanism; it does not need to run code that imports `com.sun.tools.attach`.

## 3. How Do the Two Processes Communicate?

The diagram below illustrates the **common case**: the tool and the application are two separate Java processes.

~~~text
  Tool JVM (JDK with jdk.attach)                 Running Target JVM
  +-----------------------------------+          +---------------------------+
  | AttachInspector / AgentLoader     |          | TargetApp                 |
  |  VirtualMachine.list()            |          |  Attach listener/provider |
  |  VirtualMachine.attach(id) -------+--------->|  check attach conditions  |
  |  getSystemProperties() -----------+--------->|  return data              |
  |  loadAgent(agent.jar) ------------+--------->|  load JAR, call agentmain |
  |  detach()                         |          |  agent uses Instrumentation|
  +-----------------------------------+          +---------------------------+
                  tool JVM                                    target JVM
~~~

Typically:

1. **Identify the target**: from `VirtualMachine.list()` (the list of JVMs detected by attach providers) or a known ID. In many implementations, the ID is the OS PID, but the API **does not guarantee that every provider uses PIDs**.
2. **Attach**: `VirtualMachine.attach(id)` selects a compatible provider and establishes a connection if the target allows it.
3. **Send requests**: such as `getSystemProperties()` or `loadAgent(...)`. Whether a command succeeds also depends on the target's state, provider capabilities, and JVM policy.
4. **Detach**: call `detach()` to close the control connection, even if an intermediate operation fails. **Detach is not a command to stop the target VM or unload an already-loaded agent**.

`VirtualMachine.list()` is an aggregated result from available providers, **not a list of all JVMs on every machine/container**. A JVM may exist without appearing in the list, or appear in the list and terminate before attach happens. Even a valid ID is not guaranteed to establish a connection due to access permissions, JVM version, configuration, or I/O errors.

## 4. Key Classes and Methods to Know

| API | Purpose | Points to Remember |
| --- | --- | --- |
| `VirtualMachine.list()` | List discoverable `VirtualMachineDescriptor`s | Dynamic list, not necessarily complete |
| `VirtualMachine.attach(String id)` | Connect to a VM by ID | May throw `AttachNotSupportedException` or `IOException` |
| `VirtualMachine.attach(VirtualMachineDescriptor)` | Connect using a descriptor | Uses the provider associated with that descriptor |
| `VirtualMachine.id()`, `provider()` | Inspect the connection's ID/provider | ID is not required to be a PID |
| `getSystemProperties()` | Retrieve a copy of the target's system properties as strings | May contain sensitive information; only fetch/display what is needed |
| `getAgentProperties()` | Retrieve properties managed by the target's agent mechanism | Not identical to system properties |
| `loadAgent(jarPath, options)` | Request loading a **Java agent JAR** and invoking `agentmain` | Path is interpreted according to the **target VM's** filesystem; agent runs code inside the target |
| `loadAgentLibrary(name, options)` | Load a native JVMTI agent by **library name** | Library lookup mechanism depends on the platform |
| `loadAgentPath(path, options)` | Load a native JVMTI agent by **full path** | Different from a Java agent JAR |
| `startLocalManagementAgent()` / `startManagementAgent(props)` | Start the JMX management agent via API | Has operational impact; check security conditions and configuration |
| `detach()` | End the connection from the tool | Place in `finally` after a successful attach |

`VirtualMachineDescriptor` provides the ID, display name, and provider. `AttachProvider` is an **SPI for implementers of the attach mechanism**; most tool authors only call `VirtualMachine` and do not implement a provider themselves.

Exceptions help distinguish the cause: `AttachNotSupportedException` usually indicates no compatible provider or resource; `IOException` can be a connection/communication error; `AgentLoadException` indicates a problem loading the agent; `AgentInitializationException` indicates a problem initializing the agent on the target side. `SecurityException` may also occur depending on the platform/policy. You should not automatically retry indefinitely when the PID is wrong, the JVM has terminated, or attach is blocked by policy.

## 5. Java 17+ Example: A Tool to Read Running JVM Information

The first example **does not load an agent**. It is a standalone Java program demonstrating `list`, `attach`, `getSystemProperties`, and `detach`. It prints the module name when no arguments are passed; `--list` lists the VMs the tool finds; passing an ID/PID attempts to connect and read only the Java version property.

**File: AttachInspector.java**

~~~java
import com.sun.tools.attach.VirtualMachine;
import com.sun.tools.attach.VirtualMachineDescriptor;
import java.util.Properties;

public final class AttachInspector {
    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            System.out.println(
                    "module=" + VirtualMachine.class.getModule().getName());
            System.out.println(
                    "usage: AttachInspector --list | <vm-id>");
            return;
        }
        if (args.length != 1) {
            throw new IllegalArgumentException("Expected one argument");
        }

        if ("--list".equals(args[0])) {
            for (VirtualMachineDescriptor descriptor : VirtualMachine.list()) {
                System.out.println(
                        "vm=" + descriptor.id() + " "
                        + descriptor.displayName());
            }
            return;
        }

        VirtualMachine target = VirtualMachine.attach(args[0]);
        try {
            Properties properties = target.getSystemProperties();
            System.out.println("attached=" + target.id());
            System.out.println(
                    "java.version=" + properties.getProperty(
                            "java.version", "unknown"));
        } finally {
            target.detach();
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 --add-modules jdk.attach AttachInspector.java
java --add-modules jdk.attach AttachInspector
~~~

**Exact stdout** in no-argument mode, when `jdk.attach` is present:

~~~text
module=jdk.attach
usage: AttachInspector --list | <vm-id>
~~~

Discover JVMs:

~~~bash
java --add-modules jdk.attach AttachInspector --list
~~~

The output depends on the JVM and environment, and may include lines like `vm=12345 com.example.Main` or **no lines at all**; this is **not fixed stdout**. In an environment where the ID is the PID and access to the target is permitted:

~~~bash
java --add-modules jdk.attach AttachInspector 12345
~~~

When the connection succeeds, the output lines look like `attached=12345` and `java.version=17.0.x`, where the actual values depend on the target. On failure, the example lets the exception propagate so the error type is clearly visible; a production tool should catch specific exceptions, provide concise messages, log safely, and decide whether to retry based on the cause.

**Why is `finally` needed?** If reading properties throws an `IOException`, the `finally` block still calls `detach()`. Only call detach **after** attach succeeds; if `attach()` throws an exception, there is no object to release. Do not print the entire `Properties` object to production logs because it may contain secrets or sensitive configuration.

## 6. Loading a Java Agent with the Attach API: The Full Flow

An observability tool may need to inject an agent into a JVM **after the target is already running**. In that case, the main flow is:

1. **Build an agent JAR** with a manifest `Agent-Class` pointing to a class containing `public static void agentmain(String, Instrumentation)`.
2. **Start the target JVM** and ensure the policy allows dynamic agent loading.
3. **The tool calls `VirtualMachine.attach(id)`**, then `loadAgent(jarPath, options)`.
4. **The target JVM loads the JAR and runs `agentmain`**; the `Instrumentation` object is passed to the agent by the JVM.
5. **The tool calls `detach()`**; the agent can continue operating inside the target if written to do so.

You must distinguish the `Agent-Class`/`agentmain` manifest for **dynamic loading** from `Premain-Class`/`premain` when using **`-javaagent` at startup**. Those are two different lifecycles. Receiving `Instrumentation` does not automatically modify classes; the agent must actively register a `ClassFileTransformer` or use APIs such as `retransformClasses` when supported by the JVM/configuration.

### 6.1. Example Agent and Two Programs

To demonstrate the effect in an easily verifiable way, the agent only writes one line to the **target VM's stdout**; it does not transform bytecode.

**File: SampleAgent.java**

~~~java
import java.lang.instrument.Instrumentation;

public final class SampleAgent {
    public static void agentmain(
            String options, Instrumentation instrumentation) {
        System.out.println("[agent] attached; options=" + options);
    }
}
~~~

**File: TargetApp.java**

~~~java
public final class TargetApp {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("target pid=" + ProcessHandle.current().pid());
        System.out.println("target ready");
        Thread.sleep(120_000);
    }
}
~~~

Target keeps the process running for two minutes so the tool has time to attach. In a real application, the target is an already-running service; this example simply creates a test environment.

**File: AgentLoader.java**

~~~java
import com.sun.tools.attach.VirtualMachine;
import java.nio.file.Path;

public final class AgentLoader {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: AgentLoader <vm-id> <agent-jar>");
        }

        String jarPath = Path.of(args[1]).toAbsolutePath().toString();
        VirtualMachine target = VirtualMachine.attach(args[0]);
        try {
            target.loadAgent(jarPath, "demo");
        } finally {
            target.detach();
        }
        System.out.println("Agent load finished");
    }
}
~~~

**File: MANIFEST.MF** (ending with a blank line):

~~~text
Manifest-Version: 1.0
Agent-Class: SampleAgent

~~~

Assume all four Java files and the manifest are in the same working directory. Compile and package the JAR:

~~~bash
javac --release 17 --add-modules jdk.attach \
    AttachInspector.java SampleAgent.java TargetApp.java AgentLoader.java
jar --create --file sample-agent.jar --manifest MANIFEST.MF SampleAgent.class
~~~

The trailing `\` is Unix shell line-continuation syntax. On Windows PowerShell, write `javac --release 17 --add-modules jdk.attach AttachInspector.java SampleAgent.java TargetApp.java AgentLoader.java` on **one line**; the `jar` command remains similar.

In **terminal A**, on HotSpot use the option that allows dynamic agent loading:

~~~bash
java -XX:+EnableDynamicAgentLoading TargetApp
~~~

For example, target prints:

~~~text
target pid=12345
target ready
~~~

The PID will differ on your machine. In **terminal B**, use the actual PID you just observed:

~~~bash
java --add-modules jdk.attach AgentLoader 12345 sample-agent.jar
~~~

When successful, **terminal B stdout** is exactly:

~~~text
Agent load finished
~~~

**Terminal A** receives an additional line from the agent running **inside the target JVM**:

~~~text
[agent] attached; options=demo
~~~

This is an important distinction: the loader reports its result in the **tool VM**, while `agentmain` runs and writes output in the **target VM**. The example has no framework or external library dependencies, though an actual connection requires JVM/OS attach support and appropriate permissions. PIDs, permission states, and OS behavior are not fixed. Run on a separate JVM you manage in a test environment, then terminate the target or wait for the sleep interval to finish.

### 6.2. Conditions for `loadAgent`

- The JAR path is interpreted by the **target VM**. If the tool runs on the host while the target runs in a container with its own filesystem, the path visible to the tool may **not exist** inside the target.
- The JAR needs a manifest containing a valid `Agent-Class`, and the class must have `public static agentmain(...)`. A missing class, manifest, or signature will cause a load/initialization error.
- Dynamic attach may be rejected due to JVM policy. **Being able to attach and read properties does not mean being allowed to load an agent**.
- The agent runs code **inside the target process**, so it can observe/mutate state and affect performance, class loading, and security. Only load agents whose origin has been vetted and that are authorized by the application.
- `loadAgentLibrary`/`loadAgentPath` are for **native JVMTI agents**, not aliases of `loadAgent` for Java JARs.

This example intentionally does not demonstrate `ClassFileTransformer` in order to clarify the boundary of responsibilities: **the Attach API delivers the agent into the right JVM; `java.instrument` is what provides bytecode intervention capabilities when the agent requests them**.

## 7. Access Permissions, Configuration, and Important Changes

Attach involves cross-process access permissions. In many typical HotSpot deployments, attach is restricted by process owner, operating system, protection policies, and runtime environment. Attach capability is also affected by containers/PID namespaces, file permissions, JVM configuration, providers, exited processes, or stripped-down runtime images.

These HotSpot options are **not equivalent**:

| Option When Starting the **Target VM** | Meaning |
| --- | --- |
| `-XX:+DisableAttachMechanism` | Disables HotSpot's attach mechanism; tools relying on that mechanism may be unable to connect |
| `-XX:-EnableDynamicAgentLoading` | Disallows dynamic agent loading into a running JVM, even though some other attach/diagnostic functions may remain available |
| `-XX:+EnableDynamicAgentLoading` | Allows dynamic agent loading under HotSpot's mechanism, expressing explicit consent and suppressing dynamic agent loading warnings on JDK versions that emit them |

**JEP 451 in JDK 21** began issuing warnings when agents are dynamically loaded without opt-in on corresponding HotSpot JVMs, preparing for a change that **denies dynamic loading by default in a future JDK release**. Because defaults can change across releases, check the documentation for the JVM version you deploy; do not assume "every JDK allows loading agents." **These warnings/options target dynamic agent loading, and do not mean the entire Attach API is being removed.** Agents supplied at startup via `-javaagent` have a different lifecycle from dynamic loading.

**Self-attach** (a tool attaching to its own PID) can also be blocked by default on HotSpot. Settings such as `jdk.attach.allowAttachSelf` are implementation-dependent and should only be considered in controlled testing; the example above intentionally creates **two separate JVMs**. Do not attempt to bypass production environment protections or arbitrarily enable attach just for debugging convenience.

### Common Errors

| Symptom | How to Interpret and Handle |
| --- | --- |
| `Module jdk.attach not found` | The tool's JDK/runtime is missing the module or the image stripped it out; check `java --list-modules` / how `jlink` was built |
| `package com.sun.tools.attach does not exist` | The tool is using a Java runtime/compiler without the Attach API or the build has not resolved the module |
| `AttachNotSupportedException` | Invalid/exited VM ID, incompatible provider, target does not support attach, or mechanism is disabled |
| `IOException`/`AttachOperationFailedException` | Connection refused or operation failed on the target side; read the message and check OS/JVM/container |
| `AgentLoadException` | Unable to load the JAR/library; check the path as seen by the target, manifest, agent type, and dynamic loading policy |
| `AgentInitializationException` | Agent failed to initialize; check target logs and `agentmain` code |
| Attach succeeds but `loadAgent` fails | Dynamic agent loading permission is separate from attach/property-reading capability; check flags and policies |
| `list()` returns no target | Provider results have limitations; check whether the JVM is running, same user/namespace, version, and attach capability |

You can check modules on the tool side using `java --list-modules` or `java --describe-module jdk.attach`. Do not conclude attach will succeed just because the module exists: that is only a requirement for the **API on the tool side**, not proof that the target allows connections.

## 8. When to Use It, and When to Choose Another Approach?

| Need | Sensible Option | Reason |
| --- | --- | --- |
| Application is already running; need a new observability agent | Attach + `loadAgent` (if permitted) | No restart required, accepting the cost/risk of dynamic loading |
| Can configure before startup | `-javaagent:...` with `premain` | Application owner decides agents at startup; does not depend on dynamic attach |
| Need built-in JVM diagnostics | `jcmd`, JFR, JMX, logs/metrics depending on target capabilities | May provide enough information without writing a custom Java attacher |
| Need to read a few target runtime details | `VirtualMachine.attach` + `getSystemProperties` or JMX | No need to build a Java agent just to read properties |
| Need to insert probes/transform bytecode | Java agent + `Instrumentation` and transformer | Attach only provides the path to deliver the agent; it does not perform transformations itself |

`jcmd` and JDK diagnostic tools may use the attach mechanism, but **not every `jcmd` command loads an agent**. JFR/JMX/metrics may be a better fit if the requirement is primarily observability. Choosing a tool should be based on the actual question, access level, production impact, and JVM configuration.

## 9. Misconceptions to Avoid

1. **“`jdk.attach` is the module for writing `agentmain`.”** False: the attach tool imports `com.sun.tools.attach`; agent code gets `Instrumentation` from `java.instrument`.
2. **“Calling `attach(pid)` modifies bytecode.”** False: attach only creates a connection; transformation depends on the agent, APIs, and supported conditions.
3. **“`VirtualMachine.list()` sees all Java processes.”** There is no such guarantee; the list depends on providers and the environment.
4. **“`loadAgent` reads the tool's path.”** The target interprets the path; inside a container, it can be completely different.
5. **“`detach` removes the agent from the JVM.”** No; it closes the connection from the tool.
6. **“Having the `jdk.attach` module guarantees attach will work.”** No; target support, OS permissions, provider, and configuration are still required.
7. **“Disabling dynamic agent loading blocks all diagnostic commands.”** Not necessarily; that is a policy for dynamic agent loading, distinct from `DisableAttachMechanism`.
8. **“Every agent is safe.”** No; an agent runs inside the target JVM and can affect the entire process. You must verify its origin, compatibility, scope of intervention, and overhead.

## 10. Knowledge Check

1. Why do we need **two JVMs** in the example, and which component actually runs `agentmain`?
2. Why might a tool be able to list a VM yet fail to attach? List at least two reasons.
3. If `sample-agent.jar` is only on the host while the target is in a separate container, will `loadAgent` succeed?
4. How do the roles of `jdk.attach` and `java.instrument` differ?
5. Why should `detach()` be placed in `finally`? After detaching, does an already-loaded agent still remain?
6. Can `-XX:-EnableDynamicAgentLoading` be used to test a stricter agent-loading policy while still testing other attach operations?
7. When the goal is only to collect JVM data, why might `jcmd`/JFR/JMX be more suitable than loading a custom agent?

**Key takeaway:** `jdk.attach` provides the **tool interface for connecting to and requesting operations on a running JVM**. `VirtualMachine` is the main entry point; `AttachProvider` supplies the implementation-specific connection mechanism. Only when the tool calls `loadAgent` does `agentmain` code run inside the target and gain access to `Instrumentation`; therefore, attach capability, agent-loading capability, and bytecode-transformation capability are **three distinct layers of responsibility**.

### Official References

- [Java 17 — Module jdk.attach](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/module-summary.html)
- [Java 17 — VirtualMachine API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html)
- [Java 17 — java.lang.instrument and agent lifecycle](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [JDK 21 Release Notes — Dynamic agent loading / JEP 451](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html)
