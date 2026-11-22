# Receiving Instrumentation from the JVM and Retaining the Reference Throughout the Java Agent Lifecycle

When starting an application with **-javaagent**, the Java Virtual Machine (JVM) loads an agent class and invokes **premain** before calling the application's **main**. At this point, the JVM **passes a java.lang.instrument.Instrumentation object directly** to the agent. This is the entry point for the agent to register a **ClassFileTransformer**, inspect loaded classes, check class transformation capabilities, and perform instrumentation operations supported by the JVM.

The practical problem: the **Instrumentation** parameter only appears in the startup callback signature, whereas the agent may need to use it **after premain has returned**. Therefore, it is necessary to receive the parameter properly, safely publish the reference, place it in a location with an appropriate lifecycle, ensure all components see the exact same holder, and control operations throughout the agent's active lifetime.

## 1. Learning Objectives

Upon completing this lesson, you should be able to:

1. Write **public static void premain(String agentArgs, Instrumentation inst)** and explain when the JVM invokes it.
2. Package an **agent JAR** properly with the **Premain-Class** manifest attribute and run an application using **-javaagent**.
3. Store **Instrumentation** in a shared runtime component without having to implement this interface yourself.
4. Explain why **static volatile**, safe publication of state, initialization order, and **class loader identity** matter when multiple components access the holder.
5. Reuse the handle after **premain** finishes; know how to check capabilities before performing optional operations.
6. Handle cases where the agent is not installed, installed repeatedly, multiple agents run together, startup errors occur, and clean up resources on shutdown.

The scope of this lesson is a **startup agent** via **-javaagent**. The mechanism for loading an agent into a running JVM uses **agentmain**, which is a different entry point; do not use it to replace the **premain** callback in this example.

## 2. When Does the JVM Provide Instrumentation?

### 2.1. Startup Sequence

~~~text
User runs:
  java -javaagent:my-agent.jar=options -cp ... com.example.Main
                │
                ▼
JVM initializes required runtime components
                │
                ▼
JVM reads META-INF/MANIFEST.MF inside my-agent.jar
                │ looks up the Premain-Class attribute
                ▼
JVM loads the agent class and invokes:
  public static void premain(String agentArgs, Instrumentation inst)
                │
                ├── receives inst from the JVM
                ├── stores the reference in the holder
                ├── optionally: registers transformers / starts services
                ▼
premain returns
                │
                ▼
JVM invokes the application's main(String[] args)
                │
                ▼
Agent continues serving registered callbacks and tasks
~~~

Classes used for JVM/agent startup may still have been loaded **before** the agent is registered. **premain before main** does not mean the transformer sees every JDK class or every class loaded prior to registration.

In implementations that support command-line options, the JVM can accept **multiple** **-javaagent** arguments. Their **premain** methods are invoked in the order declared on the command line. Each agent should manage its own state; do not assume all agents are a single class or share a single static field.

### 2.2. Two Valid premain Signatures

~~~java
// Preferred form when the agent needs Instrumentation:
public static void premain(String agentArgs, Instrumentation inst)

// Compatibility form if the Instrumentation parameter is not needed:
public static void premain(String agentArgs)
~~~

The JVM tries to find the **two-parameter** signature first; if absent, it tries the **one-parameter** signature. This snippet illustrates the signatures, not a standalone Java file.

- **agentArgs** is an optional **single string**, received from the part after **=** in **-javaagent:agent.jar=...**. The agent decides its own format/parsing; it is not a **String[]** like **main**'s parameter.
- **inst** is the **Instrumentation object provided by the JVM**. This interface belongs to the **java.instrument** module. Do not instantiate it yourself with **new Instrumentation()**, do not create a mock replacement for the JVM, and do not retrieve it by calling some hypothetical static method.
- Both **premain** and the agent class must be validly configured. If the JVM cannot find a valid class or signature, or if **premain** throws an uncaught exception, the JVM may **abort startup before main runs**.

The passed object is the source of instrumentation capabilities for the current JVM. According to the API documentation, once the reference is obtained, the agent can invoke supported methods on it at later times; **premain does not need to keep executing** for the handle to remain usable.

## 3. Why Keep the Reference, and Where Should It Be Placed?

The following code has a long-term usability problem:

~~~java
// Illustrates lack of a sharing mechanism; not a standalone runnable class.
public static void premain(String args, Instrumentation instrumentation) {
    System.out.println(instrumentation.getAllLoadedClasses().length);
}
// Another service has no direct way to access the local parameter above.
~~~

Method parameters are only directly accessible within the callback scope. Once **premain** returns, a command-handling service or a transformer management component still needs a way to obtain the same handle. A simple organization path for **one agent in one JVM** is:

~~~text
BootAgent.premain(..., Instrumentation from JVM)
                     │
                     ▼
AgentRuntime.install(instrumentation)
                     │ publishes the reference once
                     ▼
AgentRuntime.required()
          │
          ├── TransformerCoordinator
          ├── DiagnosticsService
          └── AgentLifecycle
~~~

This is **an agent-owned holder**, rather than passing the reference through local variables or injecting it into every object that has no need to know about JVM instrumentation.

Benefits:

- There is **a single entry point** and **a clear readiness condition**.
- Each consumer retrieves the handle through a checked method, so “not started with agent” errors surface early and clearly.
- No need to re-implement the **Instrumentation** interface or depend on internal JVM APIs.
- Concise startup code can be separated from other agent services; later, permissions can be wrapped through a narrower service.

**A static field is a simple choice, not JVM-wide magic**: static belongs to a specific **Class** defined by a **class loader**. If two loaders create two copies of **AgentRuntime**, each has its own static state. The packaging and loader identity sections below are very important.

## 4. Complete Example: Receiving, Storing, and Reusing Instrumentation

The example uses **Java 17+** with no external libraries required. For ease of execution, the three classes are placed in the **default package**; real projects should place them in the agent's package and package them consistently.

### 4.1. File AgentRuntime.java — Guarded Holder

~~~java
// File: AgentRuntime.java
import java.lang.instrument.Instrumentation;
import java.util.Objects;

public final class AgentRuntime {
    private static volatile Instrumentation instrumentation;

    private AgentRuntime() {
        // Do not instantiate the holder.
    }

    static synchronized void install(Instrumentation supplied) {
        Objects.requireNonNull(supplied, "instrumentation");

        if (instrumentation != null) {
            if (instrumentation == supplied) {
                return; // same handle: safe if intentionally called again
            }
            throw new IllegalStateException(
                    "A different Instrumentation was already installed"
            );
        }

        instrumentation = supplied;
    }

    public static boolean isInstalled() {
        return instrumentation != null;
    }

    public static Instrumentation required() {
        Instrumentation current = instrumentation;
        if (current == null) {
            throw new IllegalStateException(
                    "Agent was not initialized through premain"
            );
        }
        return current;
    }
}
~~~

How this design works:

- **private static volatile Instrumentation**: holds a shared reference for that exact **AgentRuntime** class; **volatile** provides visibility/happens-before guarantees when **premain** writes and other threads read afterward.
- **synchronized install(...)**: prevents races when there are multiple installation calls. This intentionally disallows replacing an already-stored handle with a different one. In a normal startup flow, the JVM invokes **premain** once per agent launch; the duplicate-install check acts as a safeguard against design bugs or unintended calls.
- **Objects.requireNonNull(...)**: immediately catches cases where a caller passes an invalid value.
- **required()**: reads the volatile field **once** into a local variable; if not yet ready, throws an exception with clear semantics. It returns the exact installed object without creating a new instance.
- **install** is package-private: in a single-package sample, application code is discouraged from assigning the handle itself. In production, this API can be placed in an internal package and expose only permitted operations instead of returning the raw handle to all components.

Do not use **final** directly when initialization happens after class loading, because the JVM only passes the value when the **premain** callback executes. Do not use **ThreadLocal** to hold the handle because other threads will not see the value; do not use **WeakReference** because there is no reason to tie access to the agent's API to the garbage collector.

### 4.2. File BootAgent.java — JVM Entry Point

~~~java
// File: BootAgent.java
import java.lang.instrument.Instrumentation;

public final class BootAgent {
    private BootAgent() {
    }

    public static void premain(String agentArgs,
                               Instrumentation instrumentation) {
        AgentRuntime.install(instrumentation);

        System.out.println("premain: args=" + agentArgs);
        System.out.println(
                "premain: installed=" + AgentRuntime.isInstalled()
        );

        // After storing the handle, you can register transformers or
        // initialize agent services if truly needed.
    }
}
~~~

The key point is calling **AgentRuntime.install(instrumentation)** before spawning worker threads, registering callbacks, or exposing services that may access the holder. When using complex transformers or services, registration may cause the JVM to load additional classes; therefore, ordering state publication and minimizing work inside **premain** helps avoid nested initialization errors.

### 4.3. File ExampleApplication.java — Verification After premain

~~~java
// File: ExampleApplication.java
public final class ExampleApplication {
    public static void main(String[] args) {
        System.out.println(
                "main: installed=" + AgentRuntime.isInstalled()
        );

        int loaded = AgentRuntime.required()
                                 .getAllLoadedClasses()
                                 .length;
        System.out.println("main: hasLoadedClasses=" + (loaded > 0));
    }
}
~~~

In this example, **main** checks the holder and calls **getAllLoadedClasses()** to prove the handle remains usable after **premain** finishes. The result only checks whether the JVM has at least one loaded class; the total class count depends on the JDK and process, so it is not fixed.

### 4.4. File agent.mf — Agent JAR Manifest

Create a text file **agent.mf** containing:

~~~text
Manifest-Version: 1.0
Premain-Class: BootAgent
~~~

There must be a **trailing newline at the end of the manifest file** so the last attribute is parsed properly according to the format. **Premain-Class** is the **binary name of the class**, not the path **BootAgent.class** or a Java file name. If using a package, such as **org.example.agent.BootAgent**, the manifest value must contain the full dot-separated name.

### 4.5. Compiling, Packaging the JAR, and Running

Place the four files **AgentRuntime.java**, **BootAgent.java**, **ExampleApplication.java**, and **agent.mf** in the same directory and run:

~~~bash
javac --release 17 AgentRuntime.java BootAgent.java ExampleApplication.java
jar cfm boot-agent.jar agent.mf BootAgent.class AgentRuntime.class
java -javaagent:boot-agent.jar=inspect -cp . ExampleApplication
~~~

Output on a Java 17 JVM that supports Java agents:

~~~text
premain: args=inspect
premain: installed=true
main: installed=true
main: hasLoadedClasses=true
~~~

Step-by-step explanation:

1. **javac** produces Java 17–compatible class files. **BootAgent.class** and **AgentRuntime.class** are packaged into the agent JAR; **ExampleApplication.class** is on the application classpath.
2. **jar cfm** creates the JAR with the manifest from **agent.mf**. The JVM reads **Premain-Class: BootAgent** and looks up **BootAgent.premain(String, Instrumentation)**.
3. The **=inspect** portion is passed verbatim as the string **inspect** into **agentArgs**. It does not automatically become an argument to **ExampleApplication.main**.
4. **premain** stores **Instrumentation**, prints the first two lines, and returns. **main** retrieves the handle from **AgentRuntime.required()** and prints the last two lines.
5. The agent JAR is added to the system class loader's search path in the standard startup agent mechanism. In this example, **BootAgent**, **AgentRuntime**, and **ExampleApplication** are located by the same system/application class loader, so **main** sees the exact static field assigned by **premain**.

Try running **without** adding **-javaagent**:

~~~bash
java -cp . ExampleApplication
~~~

**main** will print **main: installed=false**, and then **AgentRuntime.required()** throws **IllegalStateException** with the message **Agent was not initialized through premain**. This is an intentional failure to prevent the misconception that Instrumentation appears automatically in a normal Java application; the stack trace depends on the JVM, so no fixed output is listed.

> **Important packaging condition:** if the real application and the agent use different class loaders or modules, define a clear shared API boundary and ensure the holder resolves to the exact same **Class**. A class with the same name redefined in another loader does not share static fields. Do not copy **AgentRuntime.class** into multiple loaders and expect the copies to share state automatically.

## 5. Reference Lifecycle vs. Agent Work Lifecycle

**Holding Instrumentation** only means holding **the ability to invoke the API**. It does not mean the JVM will automatically register transformers, start schedulers, or observe all events for you.

| Point in time | Handle state | Typical agent actions |
| --- | --- | --- |
| Before JVM invokes premain | Holder has no value | Consumers must not assume **required()** will succeed |
| During premain | JVM passes **inst**; holder is assigned | Validate configuration, set up required transformers and resources |
| After premain returns | Holder still retains the static reference | Callbacks or services reuse the handle for permitted operations |
| While application is running | Multiple threads may read the same handle | Synchronize agent state; avoid duplicate registration or racy operations |
| When agent stops operating | Handle may still remain in the holder | Unregister appropriate transformers, close agent-owned resources |
| When JVM terminates | This JVM's Instrumentation object is no longer meaningful | The next JVM run receives a new object/callback |

**Instrumentation has no close() method.** Therefore, an agent that wants to stop observing must stop **the activities it registered or created**: remove transformers, stop background services, and close files/sockets or executors owned by the agent. There is no single “close Instrumentation” command to automatically undo all side effects.

**Do not serialize or persist the reference across JVMs**: this is a runtime API tied to the current process and JVM environment, not a token or configuration that can be saved to disk. Once the JVM exits, all holder state is lost with the process.

### 5.1. Should a Strong Reference Be Kept?

A normal static field holds a **strong reference** to **Instrumentation** for the lifetime of its enclosing class. This is reasonable if the agent needs long-term reuse. However, do not turn the holder into a dumping ground holding every **Class**, **ClassLoader**, transformer, or application object: strong-reference caches without an eviction strategy can prevent old class loaders and plugins from being garbage collected.

Keeping the handle stable does not mean keeping every related object forever. Manage the lifecycle of additional resources separately.

### 5.2. Can Instrumentation Be Replaced at Runtime?

Within the scope of a normal startup agent, there is no need for a public **setInstrumentation(...)** mechanism for arbitrary callers, nor is there a need to “refresh” the handle over time. Arbitrary reassignment breaks the guarantees of services that previously obtained the reference. The example's policy of installing once and allowing repeat calls with **the same reference** is simple and easy to control.

If an application supports multiple agent loading mechanisms, clearly define who owns initialization and state before combining entry points; do not assume a later callback is allowed to overwrite the installed value.

## 6. Safe Publication and Concurrency Handling

### 6.1. Why Does volatile Matter?

Consider this flow:

~~~text
Startup thread (premain)           Event-handling thread (agent)
         │                                  │
         ├── install(inst)                  │
         │    volatile write                │
         │                                  ├── required()
         │                                  │    volatile read
         │                                  └── receives exact reference
         ▼
       returns
~~~

In the Java Memory Model, a **volatile write** happens-before subsequent volatile reads of the same variable in the corresponding synchronization order. Thus, consumers read the properly published reference. Initializing other configuration may require separate happens-before relationships; **volatile does not make all mutable agent data structures thread-safe**.

For the simple example, **premain** completes before the JVM invokes the application's **main**, but real agents may spawn worker threads or callbacks right during startup. **volatile** makes the state publication contract explicit for these multithreaded consumers.

### 6.2. Synchronizing Installation vs. Synchronizing Usage

**synchronized install(...)** only protects the step that decides whether the initial assignment is allowed. It **does not** synchronize operations on transformers, caches, counters, or other resources with one another. When multiple threads:

- Register/remove transformers, manage identity and execution order.
- Record metrics, use atomic/LongAdder or an appropriate mechanism instead of an unprotected **int++**.
- Share maps/caches, use thread-safe structures and guard multi-step operations when needed.
- Start/stop services, clearly define **STARTING**, **RUNNING**, **STOPPING**, and **STOPPED** states if the workflow is complex.

The holder example using **volatile + synchronized** is sufficient for **publishing a single handle**. Do not automatically extend the same mechanism to all state without considering the atomicity and lifecycle rules of each resource.

## 7. Using the Handle After premain: Which Operations Are Supported?

Once **AgentRuntime.required()** returns the handle, services can use the **Instrumentation** API. However, each method has its own contract:

| Operation group | Representative APIs | What must be understood |
| --- | --- | --- |
| Class inspection | **getAllLoadedClasses()**, **getInitiatedClasses(loader)** | Results only reflect the state at query time; not fixed |
| Register bytecode transform | **addTransformer(transformer)** | Applies to matching future definitions; does not automatically modify already-loaded classes |
| Remove transformer | **removeTransformer(transformer)** | Requires the exact registered instance; in-flight callbacks may continue after removal |
| Retransform existing classes | **isRetransformClassesSupported()**, **retransformClasses(...)** | Optional capability; check manifest, JVM, and target class |
| Redefine existing classes | **isRedefineClassesSupported()**, **redefineClasses(...)** | Optional capability; restricts changes to existing definitions |
| Check class modifiability | **isModifiableClass(clazz)** | Returning **true** is not enough: the operation also requires the corresponding capability |
| Object size estimation | **getObjectSize(object)** | Implementation-dependent approximation, not the deep size of an object graph |
| Module adjustment | **redefineModule(...)** | Extends reads/exports/opens per API rules; does not allow arbitrarily bypassing all JVM restrictions |

### 7.1. A Small Consumer Snippet

This is **an illustrative snippet for a service already in the same class loader as the holder**, not a standalone runnable program:

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;

final class AgentTransformerService {
    private final ClassFileTransformer transformer;

    AgentTransformerService(ClassFileTransformer transformer) {
        this.transformer = transformer;
    }

    void start() {
        Instrumentation inst = AgentRuntime.required();
        inst.addTransformer(transformer, false);
    }

    void stop() {
        Instrumentation inst = AgentRuntime.required();
        inst.removeTransformer(transformer);
    }
}
~~~

In production, manage **idempotent start/stop** and registration state, avoiding calling **addTransformer** multiple times with the same instance. The API allows multiple registrations, but you should not rely on that. **removeTransformer** removes one matching registration and does not guarantee that all currently running callbacks have finished immediately. A transformer must be written so that callbacks executing concurrently with shutdown do not corrupt state.

If the agent only needs to observe newly loaded classes, calling **addTransformer(transformer)** defaults to **addTransformer(transformer, false)**; there is no need to declare the retransform capability.

### 7.2. Optional Capabilities Depend on Manifest and JVM

In addition to **Premain-Class**, the manifest can declare:

~~~text
Can-Retransform-Classes: true
Can-Redefine-Classes: true
~~~

These are **two illustrative attributes, not included in the example's minimal manifest**. They default to **false** if omitted. Declaring **true** only means the agent requests the capability; the JVM must still support it. Therefore, you must still check **isRetransformClassesSupported()** or **isRedefineClassesSupported()**, and check **isModifiableClass(clazz)** before attempting an operation on a specific class.

A safe check in code:

~~~java
// Illustrative snippet inside a service, where target is a valid Class<?>.
Instrumentation inst = AgentRuntime.required();
if (inst.isRetransformClassesSupported()
        && inst.isModifiableClass(target)) {
    // At this point you can consider inst.retransformClasses(target),
    // after ensuring the transformer and bytecode satisfy JVM constraints.
}
~~~

Without the permission/capability, **do not** call **retransformClasses(...)** directly and hope every JVM accepts it. When retransforming a class, the JVM does not re-run static initializers just because you updated method bytecode.

## 8. Class Loaders and Modules: Why Can a Static Holder “Disappear”?

A confusing failure is when the agent prints **installed=true**, yet another component reading **AgentRuntime.isInstalled()** gets **false**. In this case, check:

1. Do the consumer and the agent reference the exact same **Class** named **AgentRuntime**?
2. Does **AgentRuntime.class.getClassLoader()** return the same defining loader in both places?
3. Are there two copies of a JAR containing the same FQCN in independent class loaders?
4. Does the consumer belong to a **named module** or an **unnamed module**? Is the holder's package visible under the appropriate access rules and module readability?
5. Is the consumer running **before premain installs the handle** or running in a different JVM/process?

For a startup agent via **-javaagent**, classes in the agent JAR are normally loaded by the **system class loader**, belonging to that loader's **unnamed module**. That does not mean an application running through a custom loader/plugin or an arbitrary named module automatically has access to every agent package.

A diagnostic snippet you can place in the appropriate part of both the agent and the consumer:

~~~java
System.out.println(AgentRuntime.class.getClassLoader());
System.out.println(AgentRuntime.class.getModule());
~~~

The output contains runtime-dependent object/loader names, so there is no fixed stdout string here. If the loaders differ, redesign the **shared API boundary** (for example, a bridge class placed in a loader referenced by both sides, a valid public interface, or injecting dependencies from the agent into the service within the same loader). Do not fix it by arbitrarily duplicating the holder class or forcing access via reflection.

When the application does not truly need direct access to **Instrumentation**, keep the holder internal to the agent and expose a narrow domain API; normal applications do not need to depend on the agent runtime.

## 9. Initialization Order and Handling Startup Errors

### 9.1. Recommended Order in premain

~~~text
1. Receive/validate agentArgs and Instrumentation.
2. Install the handle into the holder.
3. Check capabilities matching the configuration.
4. Create required state, transformers, and services.
5. Register callbacks/transformers after state is ready.
6. Return so the JVM proceeds to invoke main.
~~~

This order can be adjusted by design, but the rule is that **consumers must not run before their dependencies are safely published**. If the agent starts threads in **premain**, initialize the dependencies those threads need before calling **start()**. If a transformer can be invoked while classes used by the agent itself are being defined, filter classes and minimize reentrant class loading.

Do not perform excessive blocking work in **premain** unnecessarily: the JVM waits for the callback to return before executing **main**. Log carefully for diagnostics, but if an error genuinely makes the agent unsafe, throw intentionally rather than ignoring it and letting the application start in a half-baked state. Conversely, failures in optional agent features can be handled according to a well-defined degradation policy.

### 9.2. Common Errors

| Symptom | Common cause | How to check |
| --- | --- | --- |
| JVM does not reach main when **-javaagent** is added | Unreadable agent JAR, missing **Premain-Class**, wrong class name or **premain** signature, uncaught exception | Inspect manifest, package name, **public static** method, first stack trace |
| **premain** receives unexpected args | Confusing **agentArgs** with main's **String[] args**; wrong **=options** syntax | Print agentArgs string and parse the designed format yourself |
| **AgentRuntime.required()** throws **IllegalStateException** | Running application without **-javaagent** or accessing too early | Verify launch command and initialization order |
| Agent prints installed, but consumer sees empty | Multiple **AgentRuntime** copies due to different defining loaders or different JVMs | Compare **Class** objects, loaders, modules, and processes |
| **NoClassDefFoundError** when loading agent | Forgot to package helper/dependency classes into the agent JAR or wrong loader visibility | Check file listing inside the JAR and dependencies |
| **UnsupportedOperationException** when retransforming | Agent/JVM does not support the required capability | Check **Can-Retransform-Classes** and **isRetransformClassesSupported()** |
| Callbacks occur after **removeTransformer** | Callback was already triggered by the JVM before removal and runs concurrently | Design thread-safe shutdown; do not treat remove as a barrier waiting for all callbacks |
| Application hangs during startup | Long wait in premain, loader/transformer deadlock, or thread holding a lock | Thread dump, timestamped logs, locks, and startup threads |

You can inspect the packaged agent files with:

~~~bash
jar tf boot-agent.jar
~~~

You should see at minimum **META-INF/MANIFEST.MF**, **BootAgent.class**, and **AgentRuntime.class**. File presence alone does not prove the manifest is correct: verify the exact **Premain-Class** value in the main manifest against the actual class's binary name.

### 9.3. Do Not Swallow Errors and Break Consistency

Distinguish between:

- **Required configuration/initialization errors**: without Instrumentation or with the wrong instance installed, an agent that depends on the handle cannot perform its core function. Report the error with a clear cause.
- **Optional features**: if a monitoring system is designed to run even when retransform is unsupported, you can disable that feature and record its status. Do not claim retransform is enabled when the capability check fails.
- **Runtime errors after startup**: the handle still exists, but a transformer, service, or resource may not be operating. Manage operational state separately; **isInstalled() only confirms that the reference was published**.

## 10. Responsibility Boundaries and Production Design Notes

### 10.1. The Holder Should Not Own Everything

**AgentRuntime** has a narrow responsibility: install once and provide the handle. Other responsibilities belong elsewhere:

- **AgentBootstrap/BootAgent**: receives the **premain** callback, reads configuration, and orchestrates startup.
- **TransformerCoordinator**: creates, registers, manages, and removes transformers according to lifecycle.
- **DiagnosticsService**: performs inspection queries when needed, bounding query cost.
- **AgentLifecycle**: manages executors, files/sockets, hooks, and shutdown commands if the agent creates them.

This model makes Instrumentation-controlling code easy to audit. A static method returning raw **Instrumentation** may suit small internal codebases, but if exposed to plugins or arbitrary consumers, consider an API that only permits intended operations rather than handing over full JVM class-transformation power.

### 10.2. Do Not Equate “Stored” with “Active”

A more granular readiness model for a large agent can be:

~~~text
UNINITIALIZED
    │ premain receives Instrumentation
    ▼
INITIALIZING
    │ install holder, load config, register callbacks
    ▼
RUNNING
    │ stop requested or JVM shutdown
    ▼
STOPPING
    │ remove transformers, stop executors, and close resources
    ▼
STOPPED
~~~

This is an **illustrative architectural model**, not a built-in state of the **Instrumentation** API. The holder only knows whether the handle exists; the **RUNNING** state requires the agent's own lifecycle manager if startup tasks can partially fail.

An agent that creates non-daemon threads can prevent the process from exiting as expected; decisions about daemon mode, shutdown hooks, and cleanup must follow product requirements. Do not clear **Instrumentation** from the holder to simulate shutdown if callbacks still need it; shut down owned activities in a safe order.

## 11. Self-Check Questions

1. **Why can't a Java application simply do new Instrumentation?** Because it is an interface provided by the JVM instrumentation mechanism; a valid object is passed through the agent entry point, not instantiated by the application.
2. **When running -javaagent, which method does the JVM look for first?** **premain(String, Instrumentation)**; only if absent does it try **premain(String)**. Use the two-parameter form to receive the handle.
3. **Once premain returns, does Instrumentation become invalid?** No. The agent retains the reference and can continue calling supported APIs in the current JVM.
4. **For a service on another thread to see the handle, does the static field need to be volatile?** Safe publication can be achieved through other synchronization mechanisms; in the example, **volatile** is a clear and sufficient way to publish the reference. It does not automatically synchronize other data structures.
5. **Do two AgentRuntime classes with the same name in two loaders share static instrumentation?** No. Each runtime definition of the class has its own static storage.
6. **Does isInstalled() returning true mean every class can be retransformed?** No. You must check JVM/manifest capabilities, per-class modifiability, and bytecode/schema constraints.
7. **Does removeTransformer wait for all currently running callbacks to finish?** There is no such guarantee; callbacks may continue after removal.
8. **When the JVM exits, can Instrumentation be kept and used for the next run?** No. The reference is bound to the old JVM runtime; a new run must be started and the agent initialized again.

## 12. Checklist Before Deploying a Startup Agent to Production

- The agent JAR manifest has **Premain-Class** matching the exact binary name of the class containing the two-parameter **public static premain**.
- The JVM is launched with **-javaagent:...**, and agentArgs is parsed intentionally.
- **Instrumentation** is obtained solely from the JVM parameter and installed into the holder before consumers/callbacks use it.
- The holder enforces **single initialization**, safe publication, and clear error reporting when not ready.
- The agent and consumers see the exact same **Class** of the holder, or have a valid forwarding API across loader/module boundaries.
- Optional capabilities are checked with **is...Supported()**; do not assume setting a manifest flag is enough.
- Transformers and resources are lifecycle-managed; **removeTransformer** is not assumed to block waiting for callbacks.
- The events “handle obtained” and “agent RUNNING” are distinguished; failure handling for initialization and cleanup is consistent.
- Tested both with and without **-javaagent** to verify the startup path and error messages.

## 13. Official Documentation

- [JDK 17 — Package java.lang.instrument, Starting an Agent from the Command-Line Interface](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [JDK 17 — Instrumentation interface](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [JDK 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [Java Language Specification 17 — Threads and Locks / Java Memory Model](https://docs.oracle.com/en/java/javase/specs/jls/se17/html/jls-17.html)

The examples use public Java 17 APIs and require no preview features. Support for retransform/redefine and specific error log messages depend on the JVM and runtime configuration.
