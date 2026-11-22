# Roles of java.lang.instrument, Attach API, Class-File API, and JVM TI

## 1. Why Distinguish These Four Components?

When observing or changing the behavior of a running Java program, you often encounter four names: `java.lang.instrument`, the Attach API, the Class-File API, and the JVM Tool Interface (JVM TI). They sit at **different layers of the JVM tooling ecosystem**, so they do not replace one another on a one-to-one basis.

For example, suppose you need to measure the execution time of a method without modifying the application source code. One solution can use a Java agent to observe class loading, use a class-file processor to add timing code to bytecode, and—depending on the deployment approach—either load the agent into the JVM at startup or attach it to an already running process. If you need VM-level data such as thread, heap, and breakpoint events, a tool can use JVM TI.

**Lesson objectives:** After this lesson, you will be able to identify what each API is responsible for, when it is activated, what data passes through it, the limitations of modifying already-loaded classes, and how to choose the right layer for an agent, profiler, debugger, or bytecode processing tool.

## 2. Architecture Map: Each Component Does One Job

| Component | Layer / Module | Primary Role | When Used | What It Does Not Do on Its Own |
|---|---|---|---|---|
| `java.lang.instrument` | Java API in the `java.instrument` module | Provides `Instrumentation` to a Java agent; registers `ClassFileTransformer`, observes/transforms class bytes during loading, redefining, or retransforming | Agent started with `-javaagent` or loaded dynamically | Does not parse bytecode structure at the class/method level on its own; does not discover and connect to a PID on its own |
| Attach API | JDK-specific API in `jdk.attach`, package `com.sun.tools.attach` | Connects from a tool process to a target JVM and loads a Java or native agent into that JVM | When the JVM is already running and supports attach | Does not modify bytecode or provide `Instrumentation` to the calling process on its own |
| Class-File API | `java.lang.classfile` in `java.base`, standardized since JDK 24 (JEP 484) | Reads, generates, verifies, and transforms the `.class` file format / class byte arrays | Offline or inside a transformer/agent | Does not attach, load agents, redefine running classes, or emit profiler events on its own |
| JVM TI | Native interface per the JVM specification, using `jvmti.h` from C/C++ | Queries and controls JVM state, registers VM/thread/method events, supports debuggers/profilers | Native agent at startup or via attach if the VM supports it | Does not provide a high-level Java model like the Class-File API out of the box; is not synonymous with JNI |

Two common flows can be visualized as follows:

~~~text
A. Starting with a Java agent
java -javaagent:agent.jar App
      │
      └─> premain(..., Instrumentation)
              └─> register ClassFileTransformer
                      └─> JVM prepares to define a class
                              └─> transform(class bytes)
                                      ├─> null: keep current bytecode
                                      └─> new byte[]: JVM checks/loads new bytes

B. Attaching to a running JVM
Tool JVM ──VirtualMachine.attach(pid)──> Target JVM
         ──loadAgent(agent.jar)───────> agentmain(..., Instrumentation)
                                        └─> register transformer / handle loaded classes

C. Native agent
java -agentpath:/path/libtool.so App
      └─> Agent_OnLoad(JavaVM*, ...)
              └─> obtain jvmtiEnv, request capabilities, register event callbacks
                      └─> JVM dispatches corresponding events
~~~

In the diagram above, **the Class-File API can serve as the `byte[]` processing engine inside `transform(...)`**, or be called by a build tool without any agent. **The Attach API is the path for delivering an agent into a process**, not a bytecode transformation engine. **JVM TI is a native interface close to the virtual machine**, capable of providing capabilities that pure Java APIs do not have.

## 3. `java.lang.instrument`: Entry Point of a Java Agent

### 3.1. Two Activation Modes and Two Entry Points

- **Startup agent:** Run `java -javaagent:observer-agent.jar App`. The JAR manifest declares `Premain-Class`. The JVM calls `public static void premain(String agentArgs, Instrumentation inst)` **before `App.main`**. This approach is suitable when you need to observe even classes loaded very early and can configure the JVM from the start.
- **Dynamic agent:** When the JVM supports loading an agent into a running process, the JAR declares `Agent-Class` and defines `public static void agentmain(String agentArgs, Instrumentation inst)`. Loading is typically done via the Attach API or an appropriate tool. Classes that were already loaded beforehand **do not automatically re-run transformers** just because a new agent was attached.
- A manifest can declare both `Premain-Class` and `Agent-Class` for a single JAR. The `agentArgs` parameter is a raw option string; the agent parses it itself.
- `Instrumentation` is provided to the agent by the JVM; normal applications do not instantiate `new Instrumentation()`. The agent runs **in the same JVM** as the application, so errors or overly heavy work in the agent can affect the application.

Methods worth remembering:

| Method | Meaning / Conditions |
|---|---|
| `addTransformer(transformer)` | Registers for subsequent class loads/redefines; by default, the transformer is not retransform-capable |
| `addTransformer(transformer, true)` | The transformer is invoked again during retransformation; use only if the capability is supported |
| `getAllLoadedClasses()` | Lists loaded `Class<?>` instances without modifying them by default |
| `isRetransformClassesSupported()` and `isModifiableClass(c)` | Checks actual capabilities before acting on a loaded class |
| `retransformClasses(c)` | Requests the VM to re-run the valid transformation chain for an already-loaded class |
| `redefineClasses(ClassDefinition...)` | Directly supplies new class definitions; also subject to VM constraints |
| `removeTransformer(transformer)` | Unregisters the transformer so it will not apply to future transformations; an in-flight callback may still complete |

**Distinguishing three points in time:** initial class loading (class load), requesting the VM to redefine from new class bytes (redefine), and requesting retransformation of an already-loaded class (retransform). On initial load, `ClassFileTransformer` receives the internal class name such as `com/example/OrderService`, `classBeingRedefined` is normally `null`, along with the initial class byte array. Returning `null` means **no modification**, while returning a valid `byte[]` proposes replacement class bytes. The JVM still checks the format and verifies the code.

### 3.2. Java 17+ Example: One JAR for Startup and Attach

Create three files in the same directory. The example intentionally **observes without modifying bytecode** to make the API's role clear.

File `ObserverAgent.java`:

~~~java
import java.lang.instrument.Instrumentation;

public final class ObserverAgent {
    public static void premain(String options, Instrumentation inst) {
        System.out.println("[agent] premain");
        inst.addTransformer((loader, internalName, redefining, domain, bytes) -> {
            if ("Demo".equals(internalName)) {
                System.out.println("[agent] observed class Demo");
            }
            return null; // Keep bytecode unchanged; do not interfere with application behavior.
        });
    }

    public static void agentmain(String options, Instrumentation inst) {
        System.out.println("[agent] agentmain");
        boolean demoAlreadyLoaded = java.util.Arrays
                .stream(inst.getAllLoadedClasses())
                .anyMatch(type -> "Demo".equals(type.getName()));
        System.out.println("[agent] Demo already loaded: " + demoAlreadyLoaded);
    }
}
~~~

File `Demo.java`:

~~~java
public final class Demo {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("[app] pid=" + ProcessHandle.current().pid());
        Thread.sleep(120_000); // Keep the JVM alive to test the Attach API.
    }
}
~~~

File `MANIFEST.MF` (with a trailing blank line ending the manifest):

~~~text
Manifest-Version: 1.0
Premain-Class: ObserverAgent
Agent-Class: ObserverAgent
Can-Retransform-Classes: true

~~~

Compile and package with JDK 17 or later:

~~~bash
javac ObserverAgent.java Demo.java
jar cfm observer-agent.jar MANIFEST.MF ObserverAgent.class
java -javaagent:observer-agent.jar Demo
~~~

A **structural** output of startup mode:

~~~text
[agent] premain
[agent] observed class Demo
[app] pid=<PID of the current process>
~~~

The PID is an OS-assigned number that changes on each run. The callback observes `Demo` when the JVM loads that class; no line indicates that bytecode was modified because the transformer returns `null`.

**Key point to understand:** If you only register a transformer after `Demo` has already loaded, there is no reason for the initial-load callback to appear again. To inspect an already-loaded class again, the agent must register an appropriate transformer, check capabilities, and call `retransformClasses` on that exact class. This is a separate operation, can fail, and is restricted in the types of changes allowed.

### 3.3. How Does Actual Transformation Differ from Observation?

Inside the transformer, instead of `return null`, you can:

1. Check the class name, class loader, module, and permitted scope; skip agent classes, JDK classes, and libraries that do not need intervention.
2. Read class bytes using the Class-File API (JDK 24+) or a bytecode library appropriate for the target JDK; locate the target method and build new bytes.
3. Return the new byte array; let the JVM verifier check it; deploy only with compatibility and performance tests.
4. If the target is already loaded, consider `retransformClasses` or `redefineClasses` depending on capabilities; **you cannot by default add/remove fields or methods, change the superclass, or change method signatures** of a running class.

You must properly handle the constant pool, frames/`StackMapTable`, exception flow, stack depth, and instruction validity. Incorrect bytecode manipulation can lead to `VerifyError`, `ClassFormatError`, or errors during class loading/linking. Successful agent attachment **does not guarantee** that the new class bytes are valid.

## 4. Attach API: Connecting to a Process and Requesting Agent Loading

The Attach API resides in the `jdk.attach` JDK module, package `com.sun.tools.attach`. The **tool outside the target process** typically performs:

1. Identify the target JVM (usually via PID, `VirtualMachine.list()`, or OS/JDK tools).
2. `VirtualMachine.attach(pid)` to establish a connection session, subject to JVM/OS support and permissions.
3. `vm.loadAgent("/absolute/path/agent.jar", options)` to ask the target JVM to load the **Java agent**, invoking `agentmain` in the **target JVM**.
4. `vm.detach()` to close the control connection. `detach()` **does not unload the agent or revert bytecode changes**.

The `loadAgentLibrary` and `loadAgentPath` methods are for **native agents**; they are not the same as `loadAgent` for an agent JAR. The JAR path in `loadAgent` is interpreted in the filesystem environment seen by the **target JVM**, which matters when the two sides are in different containers/namespaces.

Add the file `AttachTool.java` to the example above:

~~~java
import com.sun.tools.attach.VirtualMachine;
import java.nio.file.Path;

public final class AttachTool {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: java AttachTool <pid> <agent-jar>");
        }

        String jarPath = Path.of(args[1]).toAbsolutePath().toString();
        VirtualMachine vm = VirtualMachine.attach(args[0]);
        try {
            vm.loadAgent(jarPath, "from=attach");
        } finally {
            vm.detach();
        }
        System.out.println("[tool] loadAgent request finished");
    }
}
~~~

Run from **two terminals** on a JDK with the `jdk.attach` module:

~~~bash
javac --add-modules jdk.attach AttachTool.java
# Terminal 1: run the application without -javaagent.
java -XX:+EnableDynamicAgentLoading Demo

# Terminal 2: replace <PID> with the number Demo just printed.
java --add-modules jdk.attach AttachTool <PID> observer-agent.jar
~~~

On a JDK/HotSpot that allows attach, the application's terminal will display:

~~~text
[agent] agentmain
[agent] Demo already loaded: true
~~~

The connecting tool will print `[tool] loadAgent request finished` after the agent load call completes. **There is no `[agent] observed class Demo` line** in this attach test: `agentmain` only lists currently loaded classes, without registering a transformer or retransforming. That demonstrates that the Attach API handles **when the agent is deployed**, and does not instrument the application on its own.

**Practical limitations:** Attach depends on the JVM vendor/implementation, OS permissions, container isolation, security policies, and JDK version. A process can disable the attach mechanism (for example, HotSpot has `-XX:+DisableAttachMechanism`). Self-attach (the same process attaching to itself) also has its own default restrictions; the example above uses **two processes**. Do not assume `com.sun.tools.attach` is a universal Java SE API available in every minimal runtime.

## 5. Class-File API: Understanding and Generating Class Bytes, Not Managing the Target JVM

`java.lang.classfile` was standardized in **JDK 24** (JEP 484; previously a preview feature in JDK 22 and 23). The API belongs to `java.base` and uses an immutable/lazy model to read classfiles, represent classes/methods/fields/attributes, generate new classes, and transform class bytes. It is the standard solution for classfile operations on supported JDKs, instead of relying directly on `jdk.internal.org.objectweb.asm` (an internal API with no stability guarantees).

Key concepts:

- `ClassFile.of()` provides the parse/build/transform context. `ClassFile.parse(byte[])` or `parse(Path)` returns a `ClassModel`.
- `ClassModel` represents a class (name, fields, methods, attributes, constant pool). `MethodModel` and `CodeModel` let you inspect method bodies and bytecode.
- `ClassFile.build(...)` creates class bytes; `transformClass(model, transform)` produces a modified byte array; `verify(...)` checks certain classfile validity rules at the API layer.
- Models are read/resolved lazily, so initial parsing success **does not guarantee** that every malformed element will be flagged immediately; deeper access may throw exceptions on a corrupted classfile. Do not share lazy models arbitrarily across multiple threads.
- The Class-File API **knows nothing about PIDs, does not call `agentmain`, and does not load new code into a running JVM on its own**. Generated bytes still need a mechanism to consume them: writing to `.class`, a class loader, a build tool, or a transformer.

Standalone example on **JDK 24+**; file `InspectClassFile.java`:

~~~java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.nio.file.Path;

public final class InspectClassFile {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java InspectClassFile <path-to-class>");
        }

        ClassModel model = ClassFile.of().parse(Path.of(args[0]));
        System.out.println("class: " + model.thisClass().asInternalName());
        for (var method : model.methods()) {
            System.out.println("method: " + method.methodName().stringValue());
        }
    }
}
~~~

~~~bash
# Reuse Demo.class from the previous example; requires JDK 24+.
javac InspectClassFile.java
java InspectClassFile Demo.class
~~~

With the `Demo.class` file compiled by `javac` from the example above, the output is:

~~~text
class: Demo
method: <init>
method: main
~~~

`<init>` is the compiler-generated default constructor, not a Java method you explicitly declared in `Demo.java`. The example only **reads metadata offline**; no agent is loaded, and the `Demo` class does not need to be run by a JVM to be inspected.

To combine the Class-File API with `java.lang.instrument`, the mental model is:

~~~text
ClassFileTransformer.transform(..., byte[] original)
       ├─> ClassFile.of().parse(original)
       ├─> select the MethodModel / CodeModel instances to modify
       ├─> ClassFile.of().transformClass(model, transform)
       └─> return transformedBytes
             └─> JVM verifier -> redefine / load class
~~~

The diagram is a design flow, **not a standalone Java snippet you can copy and run**. A real transform must build an appropriate `ClassTransform`, preserve valid bytecode, avoid touching already-instrumented classes, and include tests for the target JDK. **Do not use the JDK 24 Class-File API in an agent that must run on JDK 17**: in that case, you must compile for a compatible target and use a compatible bytecode processing library (such as ASM/Byte Buddy) or upgrade the runtime to a supported version.

## 6. JVM TI: Native Interface for Deep Tooling

**JVM Tool Interface (JVM TI)** is a C/C++ interface for native agents to access JVM observation and control capabilities. An agent is typically a `.so` on Linux or `.dll` on Windows and runs **inside the JVM process**. JVM TI can provide events/functions related to lifecycle, threads, methods, breakpoints, exceptions, heap, class loading, and GC, depending on the JVM and available capabilities.

Common flow:

1. The JVM starts with `-agentlib:name` or `-agentpath:/absolute/path/to/library` and calls the `Agent_OnLoad` entry point; if dynamic loading is supported, the JVM calls `Agent_OnAttach`.
2. The native agent uses `JavaVM::GetEnv` with `JVMTI_VERSION_*` to obtain `jvmtiEnv*`.
3. Register event callbacks (`SetEventCallbacks`), enable each event with `SetEventNotificationMode`; for features requiring special privileges, call `AddCapabilities` beforehand and check the result.
4. The JVM proactively invokes callbacks when events occur, or the agent calls JVM TI functions to query/control state. Select only the events you truly need, because MethodEntry, SingleStep, or tracking every allocation can incur high overhead.

**Minimal example to recognize the API**: a C native agent that only listens for the JVM initialization event. File `sample_jvmti.c`:

~~~c
#include <jni.h>
#include <jvmti.h>
#include <stdio.h>

static void JNICALL on_vm_init(jvmtiEnv *ti, JNIEnv *jni, jthread thread) {
    puts("[jvmti] VM initialized");
    fflush(stdout);
}

JNIEXPORT jint JNICALL Agent_OnLoad(JavaVM *vm, char *options, void *reserved) {
    jvmtiEnv *ti = NULL;
    if ((*vm)->GetEnv(vm, (void **)&ti, JVMTI_VERSION_1_2) != JNI_OK
            || ti == NULL) {
        return JNI_ERR;
    }

    jvmtiEventCallbacks callbacks = {0};
    callbacks.VMInit = &on_vm_init;
    if ((*ti)->SetEventCallbacks(ti, &callbacks, sizeof(callbacks))
            != JVMTI_ERROR_NONE) {
        return JNI_ERR;
    }
    if ((*ti)->SetEventNotificationMode(
            ti, JVMTI_ENABLE, JVMTI_EVENT_VM_INIT, NULL)
            != JVMTI_ERROR_NONE) {
        return JNI_ERR;
    }
    return JNI_OK;
}
~~~

**Linux + GCC + JDK with JNI/JVM TI headers** example, from the directory containing `sample_jvmti.c` and `Demo.class`:

~~~bash
gcc -shared -fPIC \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  -o libsamplejvmti.so sample_jvmti.c
java -agentpath:"$PWD/libsamplejvmti.so" Demo
~~~

Before `Demo.main` runs, the callback prints:

~~~text
[jvmti] VM initialized
~~~

This example only handles `Agent_OnLoad` and `VMInit`, **without `Agent_OnAttach` or an actual profiler**. An agent using sensitive events such as method entry must request the appropriate capability, check which functions are available in the current phase, and avoid performing blocking/heavy work inside callbacks.

**JVM TI vs. JNI:** JNI lets native code interact with Java (calling Java methods, accessing objects, creating references); JVM TI is for **VM monitoring/control tools**. JVM TI can use JNI types in callbacks, but the two interfaces have different responsibilities. Debuggers typically go through the **JDWP** protocol layer and components of the **Java Platform Debugger Architecture (JPDA)**; applications consuming debugger tools do not necessarily call JVM TI directly.

## 7. Combining All Four Components in a Real Requirement

**Scenario:** The `OrderService` application is running, and you need to measure the latency of certain methods without modifying source code.

| Specific Need | Choice | Why |
|---|---|---|
| You can modify startup configuration and want to instrument from the beginning | `-javaagent` + `premain` + `Instrumentation` | Allows registering a transformer before application classes are loaded |
| You need ad-hoc diagnostics on a running JVM, and policy permits | Attach API → `agentmain` | Injects an agent after application startup; already-loaded classes must be handled separately |
| You need to analyze/insert instructions into method bytecode on JDK 24+ | Class-File API inside a transformer | The API helps parse/transform/generate classfiles in valid format |
| You need breakpoints, method/thread events, or detailed native VM data | JVM TI native agent / appropriate debugger/profiler | Provides a direct event/capability interface with the JVM |
| You only need thread dumps, heap summaries, or built-in observations | `jcmd` / JFR / JMX tools when appropriate | In some cases you do not need to write and deploy a custom agent |

Two valid designs:

~~~text
Startup:
-app startup config---> -javaagent:metrics.jar
                         └─> Instrumentation
                               └─> transformer + classfile tool
                                     └─> modified class bytes

Live:
diagnostic tool ---> Attach API ---> agentmain
                                      └─> Instrumentation
                                            ├─> observe loaded classes
                                            └─> retransform if permitted and supported

Low-level:
-profiler startup config---> -agentpath:profiler.so
                               └─> JVMTI callbacks / queries
~~~

A system is not required to use **all four**. For example, a build tool processing `.class` files offline only needs the Class-File API; a Java agent that only observes class names may not need the Class-File API; a native profiler can use JVM TI without using `java.lang.instrument`.

## 8. Technical, Security, and Operational Boundaries

### 8.1. Already-Loaded Classes Are Not the Same as Classes About to Be Loaded

- A transformer registered today applies by default to future class definitions. Appearing in `getAllLoadedClasses()` does not mean a class will automatically be transformed again.
- `retransformClasses` requires JVM and agent support, and the target class must be modifiable; the `Can-Retransform-Classes: true` manifest attribute is only one prerequisite. When reloading a definition, the JVM typically restricts structural changes to an already-loaded class (for instance, you cannot freely add/remove methods or fields, or change inheritance). Valid body changes must still pass the verifier.
- An already-running method may continue executing frames using the old definition depending on redefine/retransform semantics, while subsequent calls use the new definition. Therefore, do not treat hotswap as an instant replacement of every active stack frame.
- Class identity depends on **class name + defining class loader**. Two classes with the same name but different loaders are two distinct types; filtering by name alone can easily instrument the wrong class.

### 8.2. Dynamic Agent Loading and JEP 451

Starting in **JDK 21**, HotSpot emits a warning when **dynamically loading** a Java/JVM TI agent into a running JVM, per JEP 451. Startup agents via `-javaagent`, `-agentlib`, and `-agentpath` do not trigger this warning simply from how they are loaded. On HotSpot with the appropriate mechanism, `-XX:+EnableDynamicAgentLoading` explicitly permits it at startup and suppresses the warning; `-XX:-EnableDynamicAgentLoading` disallows dynamic loading. Default policies can vary by JDK release and vendor: **check the exact target runtime**, and do not assume attach is always permitted.

Do not rely on self-attach or attach as a default privilege; sandboxes, containers, OS users, seccomp, permissions, or JVM flags can block attach. In production environments, prefer placing approved agents in startup configuration if the tool needs to run regularly, and record the agent version along with the permissions of the agent-loading process.

### 8.3. Stability and Performance

- Agent code runs inside the target JVM; an initialization error in `premain` can halt JVM startup. Handle errors and disable features cleanly before production deployment.
- Instrument only the packages/methods you need to measure; avoid transformers that modify the entire JDK, logging classes, or the agent's own libraries, as this can cause recursive class loading (`ClassCircularityError`), deadlocks, or heavy overhead.
- Class load and method event callbacks may run on sensitive application threads; keep them short, do not wait on external I/O, and avoid hard-to-control locks. Design data collection with bounded buffers and load-shedding mechanisms.
- Do not assume transformed bytecode remains valid across all JDKs: classfile versions, stack map frames, method handles, `invokedynamic`, module boundaries, and hidden classes can expose bugs.
- The `Class-File API` in `java.base` is usable on JDK 24+; the `Attach API` is the implementation-specific `jdk.attach` module; `JVM TI` requires a supporting runtime and a native library matching the OS/CPU/ABI. The "Java 17+ code" in the agent section does not make the Class-File API example runnable on JDK 17.

## 9. Common Misconceptions

1. **"The Attach API is a bytecode instrumentation API."** False: Attach connects and requests agent loading; instrumentation lives in `Instrumentation`/transformers or a native agent.
2. **"Registering a transformer modifies every running class."** False: already-loaded classes are only reconsidered through an explicit operation and with the appropriate capabilities.
3. **"The Class-File API makes the JVM immediately use the new class."** False: the API only creates/reads/transforms classfiles; a class loader, agent, or build tool must consume the bytes.
4. **"Both Java agents and JVM TI agents are JARs."** False: a Java agent is typically a JAR with `Premain-Class`/`Agent-Class`; a JVM TI agent is typically a native shared library with C entry points.
5. **"JNI and JVM TI are the same."** False: JNI is for Java/native interop; JVM TI is a dedicated interface for debuggers, profilers, and VM tools.
6. **"Having `Can-Retransform-Classes: true` means any class can be changed."** False: it also depends on JVM capabilities, whether the class is modifiable, and structural restrictions during redefine/retransform.
7. **"JDK 21 warning means attach is already banned."** False: JEP 451 starts with a warning to prepare for stricter policies; whether it is allowed depends on the specific JVM version and runtime flags.

## 10. Self-Check Knowledge

- **Exercise A:** You need to add logging to a class before its first load on JDK 17. Do you choose `-javaagent`/`premain` or Attach? Do you need the JDK 24 Class-File API?
- **Exercise B:** A JVM has been running for 2 hours, and an agent was just attached. Why does a callback registered only with `addTransformer` not capture already-loaded classes? What conditions must be checked before `retransformClasses`?
- **Exercise C:** A CLI tool needs to read the list of methods from `UserService.class` offline on JDK 24. Which of the four technologies do you need? Why is no PID needed?
- **Exercise D:** You want to receive the VMInit event and analyze threads at the VM level in C code. Why choose JVM TI instead of the Attach API alone? Which flags start a native agent?

Answer hints: **A** uses `-javaagent` and a JDK 17-compatible bytecode library; **B** must handle already-loaded classes via retransform/redefine when the JVM supports it and the class is modifiable; **C** only needs the Class-File API; **D** uses a JVM TI native agent via `-agentlib` or `-agentpath` (Attach may only play the role of delivering the agent if the JVM supports it).

## Official Documentation for Reference

- Java Instrumentation API, startup/dynamic agents: https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html
- `Instrumentation` and retransform/redefine conditions: https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- Attach API (`jdk.attach`): https://docs.oracle.com/en/java/javase/21/docs/api/jdk.attach/com/sun/tools/attach/package-summary.html
- Class-File API JDK 24: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/package-summary.html
- JVM Tool Interface specification: https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html
- JEP 451, dynamic agent loading: https://openjdk.org/jeps/451
- JEP 484, Class-File API: https://openjdk.org/jeps/484
