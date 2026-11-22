# How a Java agent runs in the same JVM as the application and what its lifecycle looks like

> **Key takeaway:** A Java agent is Java code loaded and initialized by the target application's JVM to observe or transform program behavior. When using `-javaagent`, the JVM calls `premain` before `main`; when loaded into a running JVM via the attach mechanism, the JVM calls `agentmain`. After these two initialization methods return, any transformers, threads, and resources registered by the agent can remain active until they are unregistered or the JVM terminates.

## 1. What does "same JVM" actually mean?

A Java agent is typically a **JAR with agent-specific manifest attributes**. It is not automatically a separate process, does not have its own JVM, and does not necessarily have its own processing loop.

When an agent is loaded into an application:

- **Same process and address space:** the agent shares the heap, garbage collector, CPU, OS resources, and memory limits of the application's JVM. Fatal errors, deadlocks, or excessive resource consumption in the agent can affect the entire application.
- **Same runtime, but not necessarily the same class loader:** classes in the agent JAR are loaded via the *system class loader* into that loader's unnamed module. Application classes may use the system loader or a dedicated loader from a framework, container, or plugin. Therefore, you must not assume the agent can see all application dependencies.
- **A JVM-invoked entry point:** `premain`/`agentmain` receives an options string and, with the two-parameter signature, a `java.lang.instrument.Instrumentation` object. This object is the bridge to the instrumentation capabilities supported by the JVM.
- **Independent of whether bytecode is modified:** an agent may only observe or set up hooks, or it may register a `ClassFileTransformer` to transform class bytes. The example in this article only logs when a class is defined; it **does not modify bytecode**.

Distinguish between these three components:

| Component | Where is it? | Role |
| --- | --- | --- |
| Application | Target JVM | Runs business logic with the application's `main`, threads, class loaders, and resources |
| Java agent | **Inside the target JVM itself** | Registers instrumentation, observes class loading, collects metrics, or transforms bytecode |
| Attach tool (if used) | Usually a **separate process/JVM** | Connects to the target JVM and requests it to load the agent; once loaded, `agentmain` code runs in the **target JVM** |

## 2. Lifecycle when starting with `-javaagent`

Syntax on a JDK that supports Java instrumentation:

~~~bash
java -javaagent:agent.jar=someOptions -cp app.jar com.example.Main
~~~

`someOptions` is passed verbatim as the `String agentArgs` parameter; the JVM does not automatically split or parse key/value pairs on the agent's behalf.

Key sequence:

1. The Java launcher creates the JVM and processes startup options, including the path to the agent JAR.
2. The JVM reads the `Premain-Class` manifest attribute, loads the agent class, and looks for `public static void premain(String, Instrumentation)`; if not found, the JVM tries the `premain(String)` signature.
3. **After the JVM initializes but before calling the application's `main`**, the JVM invokes `premain`. The agent typically reads configuration, checks permissions/capabilities, registers transformers, and initializes meters and required resources. `premain` must return for the application to continue starting up.
4. The JVM continues loading/defining classes and calls `main`. With a registered transformer, the JVM can call `transform` **right during class definition, before `main`**, and continue calling it for subsequent class loads.
5. While the application is running, the agent's callbacks and threads can continue executing. When the JVM process stops, the agent terminates along with the process; Java instrumentation does not provide a mandatory `stop` method.

~~~mermaid
sequenceDiagram
    participant Launch as Java launcher
    participant JVM as Target JVM
    participant Agent as In-JVM agent
    participant App as Application
    Launch->>JVM: -javaagent:agent.jar=boot
    JVM->>Agent: premain("boot", Instrumentation)
    Agent->>JVM: addTransformer(...)
    Agent-->>JVM: premain returns
    JVM->>Agent: transform(HelloApp) on class definition
    Agent-->>JVM: null (bytecode unchanged)
    JVM->>App: main(args)
    Note over JVM,Agent: Transformer remains registered and can be invoked again
~~~

**Two operational consequences:**

- If multiple `-javaagent` arguments are specified, `premain` is called in the **order they are listed on the command line**. When multiple agents modify the same class, transformer order becomes important.
- If the startup agent cannot be loaded, `Premain-Class`/a matching signature is missing, or `premain` throws an uncaught exception, the JVM **may abort startup before running `main`**. This is an application startup failure, not a failure of an isolated monitoring tool.

## 3. Hands-on: observing an agent run before `main` (Java 17+)

Create the following four files in the **same directory**. No external libraries outside the JDK are needed.

**`LifecycleAgent.java`** — contains both entry points; the first run uses only `premain`.

~~~java
import java.lang.instrument.Instrumentation;

public final class LifecycleAgent {
    public static void premain(String args, Instrumentation inst) {
        start("premain", args, inst);
    }

    public static void agentmain(String args, Instrumentation inst) {
        start("agentmain", args, inst);
    }

    private static void start(String entry, String args, Instrumentation inst) {
        System.out.println("[agent] " + entry + ", args=" + args);
        inst.addTransformer(new LoggingTransformer());
    }
}
~~~

**`LoggingTransformer.java`** — callback invoked by the JVM when defining a matching class. It returns `null`, leaving the class bytes unchanged.

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

public final class LoggingTransformer implements ClassFileTransformer {
    @Override
    public byte[] transform(ClassLoader loader, String className,
                            Class<?> type, ProtectionDomain domain,
                            byte[] originalBytes) {
        if ("HelloApp".equals(className)) {
            System.out.println("[agent] about to define HelloApp");
        }
        return null;
    }
}
~~~

**`HelloApp.java`** — a minimal target application.

~~~java
public final class HelloApp {
    public static void main(String[] args) {
        System.out.println("[app] main");
    }
}
~~~

**`agent.mf`** — the agent's manifest, starting with the two corresponding entry point attributes; save it with a trailing newline at the end of the file.

~~~text
Manifest-Version: 1.0
Premain-Class: LifecycleAgent
Agent-Class: LifecycleAgent
~~~

Compile, package **both agent classes**, and start the application:

~~~bash
javac --release 17 LifecycleAgent.java LoggingTransformer.java HelloApp.java
jar --create --file lifecycle-agent.jar --manifest agent.mf LifecycleAgent.class LoggingTransformer.class
java -javaagent:lifecycle-agent.jar=boot HelloApp
~~~

**Expected stdout:**

~~~text
[agent] premain, args=boot
[agent] about to define HelloApp
[app] main
~~~

Line-by-line explanation:

- The first line proves the JVM called `premain` and passed the string `boot` to the agent before `main`.
- The second line occurs while the JVM is defining the `HelloApp` class. The transformer returns `null`, so it does not alter the bytecode; the application continues running normally.
- The last line is the application's `main`. Sharing the same stdout stream proves the agent is inside the target process; the order of the three lines shows that callback registration happened before this class definition.

The example uses the default-package class name `HelloApp`. For packaged classes, the `className` parameter is in JVM internal name format, for example `com/example/HelloApp` (slashes instead of dots). `ClassFileTransformer` is an interface with default `transform` methods, so the sample uses an explicit implementation class rather than a lambda.

## 4. Lifecycle when attaching to a running JVM: `agentmain`

The second path starts **after the application has already launched**. An external tool uses the Attach API (if permitted by the JVM, OS, and policy) to load the agent JAR into the target JVM. The target JVM reads `Agent-Class` from the manifest and calls `public static void agentmain(String, Instrumentation)`, or the single-parameter signature if appropriate.

~~~text
Attach tool JVM                    Running application JVM
-------------------                ------------------------
VirtualMachine.attach(pid)  --->   Target JVM attach channel
VirtualMachine.loadAgent(jar) --->  Load JAR, call agentmain(...)
VirtualMachine.detach()      --->  Close tool connection
                                   Registered transformers/threads keep running
~~~

**`agentmain` must also initialize quickly and return**, but it does not re-run `premain` or `main`. Unlike a startup agent, it arrives **after some classes have already been defined**, so merely calling `addTransformer` does not automatically go back in time to observe or transform those classes. If you need to process already-loaded classes, see the retransformation section below.

When `agentmain` fails or throws an exception, the specification does not require the target JVM to abort the process as with a `premain` failure; the attach tool may still receive an error and the agent's effects may be incomplete. Do not infer that a dynamic agent failure is harmless: code that already ran in the same JVM may still have mutated state.

### Trying attach with the same JAR above

Keep `lifecycle-agent.jar` from the previous example. Create two more files in the same directory.

**`LongApp.java`** — keeps the application JVM alive long enough to attach.

~~~java
public final class LongApp {
    public static void main(String[] args) throws Exception {
        System.out.println("[app] pid=" + ProcessHandle.current().pid());
        Thread.sleep(120_000); // Two minutes to practice attaching
        System.out.println("[app] done");
    }
}
~~~

**`AttachAgent.java`** — tool program running in a separate JVM, receiving the target JVM's PID from the command line.

~~~java
import java.nio.file.Path;
import com.sun.tools.attach.VirtualMachine;

public final class AttachAgent {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Pass the target JVM PID");
        }

        String agentJar = Path.of("lifecycle-agent.jar")
                              .toAbsolutePath().toString();
        VirtualMachine vm = VirtualMachine.attach(args[0]);
        try {
            vm.loadAgent(agentJar, "live");
        } finally {
            vm.detach();
        }
        System.out.println("[tool] agent loaded");
    }
}
~~~

Compile with a JDK that includes the `jdk.attach` module:

~~~bash
javac --release 17 --add-modules jdk.attach LongApp.java AttachAgent.java
~~~

In **terminal A**, run the active application JVM (without `-javaagent`). On supported JDKs, the `-XX:+EnableDynamicAgentLoading` flag explicitly allows dynamic agent loading:

~~~bash
java -XX:+EnableDynamicAgentLoading LongApp
~~~

Terminal A prints `[app] pid=...`. Copy the **actual PID number** printed, then in **terminal B**, replace the sample number `12345` below with that PID:

~~~bash
java --add-modules jdk.attach AttachAgent 12345
~~~

When attach is permitted, terminal B prints:

~~~text
[tool] agent loaded
~~~

And **terminal A of the target JVM** will additionally print:

~~~text
[agent] agentmain, args=live
~~~

Additional JVM/policy-dependent messages, such as a dynamic-loading warning on some versions, may appear on stderr. Most importantly: the `agentmain` log appears in the **target JVM**, not the attach tool. Even though `LoggingTransformer` was registered, there will be **no** "about to define HelloApp" log in this example because `LongApp` was already defined before attaching, and the transformer only filters for the name `HelloApp`.

Attach may be rejected due to different user accounts, container environments, JVM configuration, missing attach module/mechanism, or security policies. JDK 21 emits a warning when dynamically loading agents (JEP 451) and prepares for stricter policies in subsequent JDK releases. Therefore, you must test on the **exact JDK version being deployed**; do not rely on the assumption that attach is always enabled. When you want the agent to be loaded consistently from the start, configuring `-javaagent` is usually easier to control.

## 5. Once `premain`/`agentmain` has returned, what keeps the agent "alive"?

Those two methods are **initialization points**, not the agent's life loop.

| Phase | What keeps the agent's activity going? | When does it stop? |
| --- | --- | --- |
| Registered transformer | The JVM maintains the registration of the `ClassFileTransformer` object | Upon `removeTransformer` or JVM shutdown |
| Agent-created threads/tasks | Threads, schedulers, buffers, and exporters run in the same JVM | When the task finishes, is stopped, or the JVM shuts down |
| Other hooks/listeners/resources | Registrations/objects remain referenced by the relevant subsystems | When explicitly unregistered, released, or on JVM shutdown |
| Code running only in the entry point | No background work is created automatically | Direct effects end when the method returns |

Therefore, **`premain` returning does not mean the agent has been unloaded**. Conversely, if the entry point only prints a line and registers nothing, there is no background work to continue either. If using a background thread to send telemetry, you must manage queues, backpressure, connection closing, timeouts, and avoid unintentionally preventing the JVM from exiting; daemon threads do not guarantee data is flushed on abrupt termination.

Java instrumentation **does not define a standard `stop()` callback**. An agent can provide its own shutdown mechanism, call `removeTransformer`, close resources, and register a shutdown hook when appropriate. However, `removeTransformer` does not guarantee that no callbacks are still in flight due to concurrent class loading, nor does it **automatically restore bytecode** for previously modified classes. A shutdown hook does not replace a clearly designed flush and error-handling mechanism.

## 6. Which classes does a transformer see and how much can it change?

`Instrumentation.addTransformer(transformer)` registers a transformer that does not actively support retransformation. When the JVM is about to define a class, a callback may occur:

~~~java
byte[] transform(
    ClassLoader loader,
    String className,
    Class<?> classBeingRedefined,
    ProtectionDomain protectionDomain,
    byte[] classfileBuffer
);
~~~

This is an **API signature for explanation**, not a standalone Java file. `classfileBuffer` contains the input bytes; the agent can return another valid class file byte array to change the definition, or **`null`** if no change is made. Do not mutate the input array directly. The callback may be invoked on different class-loading threads; keep it fast, thread-safe, and avoid recursion/class-loading cycles.

Clearly distinguish these cases:

| Case | Basic `addTransformer` | What else is needed? |
| --- | --- | --- |
| Class defined **after** registration | Has a chance to receive `transform` | No retransform needed |
| Class already defined **before** attach | No retroactive callback | Can use `retransformClasses`/`redefineClasses` if the JVM and class allow it |
| Class running during retransform | Does not arbitrarily pause or rewind entire methods | Active frames may continue with old bytecode; new calls use the new definition |
| Wanting arbitrary class structure changes | Not guaranteed | Redefinition/retransformation has limits on structure and which classes can be modified |

When already-loaded classes need to be retransformed, the agent must declare this in its manifest:

~~~text
Can-Retransform-Classes: true
~~~

Then **check actual capability** with `inst.isRetransformClassesSupported()`, check each class with `inst.isModifiableClass(clazz)`, register the transformer using `inst.addTransformer(transformer, true)`, and only then call `inst.retransformClasses(clazz)` when safe. Setting the manifest attribute **does not perform retransformation by itself**. Additionally, certain structural class changes (such as changing the set of fields/methods or inheritance hierarchy) are not supported through this mechanism.

Agent classes typically reside in the system loader, while the application may have custom loaders or strongly encapsulated modules. `ClassNotFoundException`, `NoClassDefFoundError`, `IllegalAccessError`, or a transformer inadvertently triggering loading of its own dependencies are signs that you need to analyze class loaders and module readability/openness. The `Instrumentation` API has additional capabilities such as `redefineModule`, but use them only once access requirements are precisely determined.

## 7. Common misconceptions and practical pitfalls

1. **Confusing a Java agent with an independent service.** The agent runs **inside the target JVM**; only the attach tool can be in another process. There is no default fault or memory isolation.
2. **Only setting `Main-Class` in the JAR and expecting `premain` to run.** An application's `Main-Class` and an agent's `Premain-Class`/`Agent-Class` have different meanings. Calling `premain` like a regular Java method also does not produce a valid `Instrumentation` object from the JVM.
3. **Assuming `agentmain` sees all past class loads.** A regular transformer receives future class definitions; intervening in already-loaded classes requires dedicated APIs and capabilities.
4. **Forgetting to package the agent's dependencies.** A correct manifest still fails if the JAR is missing `LoggingTransformer.class` or libraries the agent needs. Application dependencies are not guaranteed to be visible to the agent's loader.
5. **Registering duplicate transformers or doing too much work in callbacks.** This causes duplicate logs, overhead, CPU load, class-loading loops, or deadlock risks. In practice, lifecycle management and thread-safe configuration are required.
6. **Treating an agent as "read-only/observe-only" and therefore always safe.** An agent has the power to directly affect JVM behavior and can read in-process data. Only run trusted agents; measure overhead, verify JDK compatibility, logging rules, and rollback capability.
7. **Assuming attach works on every JDK/infrastructure.** User permissions, containers, JVM flags, modules, and policies can vary; test on the exact runtime and prefer enabling the agent at startup if the deployment model allows.

## 8. Lifecycle summary

- **Startup:** `-javaagent` → JVM loads JAR via `Premain-Class` → `premain` registers hooks → application enters `main`.
- **Running:** Agent and application share one JVM; transformers are invoked when matching classes are defined, and agent-created threads/resources continue running independently of the entry point having returned.
- **Dynamic attach:** Attach tool connects to a running JVM → JVM loads via `Agent-Class` → `agentmain` → hooks apply only from registration onward, unless explicitly retransforming/redefining old classes.
- **Termination:** No standard `stop`; cleanup must be designed explicitly. When the JVM exits, both the agent and the application terminate together.

**Official documentation for further reading:**

- [Java SE 17 — Package java.lang.instrument](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): entry points, manifest, startup sequence, and agent class loader.
- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): registering/removing transformers, retransform, redefine, and limitations.
- [Java SE 17 — Attach API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/package-summary.html): tool for attaching to a target JVM.
- [OpenJDK JEP 451](https://openjdk.org/jeps/451): warnings and policy direction regarding dynamic agent loading.
