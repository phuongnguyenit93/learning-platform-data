# Why Registering a Transformer After Attach Does Not Modify Already Loaded Classes

## 1. Symptom: The Agent Attached Successfully, Yet the Old Class Behaves the Same

A running Java application has the class `com.example.PaymentService`. After the application has already loaded and used this class, an observability tool uses the Attach API to load a Java agent into the JVM. Inside `agentmain`, the agent calls `instrumentation.addTransformer(transformer)`, prints “transformer registered”, and returns. However, subsequent calls to `PaymentService.pay()` still execute just as before.

**This is the expected behavior under the Java Instrumentation contract**: registering a transformer **does not automatically scan and re-transform** all classes that the JVM defined prior to the time of registration.

Three distinct events must be separated:

1. **Attach/load agent:** The running JVM accepts the agent and invokes `agentmain` (if dynamic attach is supported).
2. **Register transformer:** `addTransformer(...)` adds a callback to the processing chain for **future class definitions**, redefine operations, and eligible retransform operations.
3. **Request retransformation:** `retransformClasses(Class<?>...)` is a **separate** call that asks the JVM to re-run the transformation chain for the selected already-loaded classes.

**Short takeaway:** “agent loaded” is different from “transformer registered”; both are different from “running class retransformed”; and “retransformed” is still different from “application behavior actually changed.”

## 2. Timeline for an Exact Understanding

~~~text
T0: java -cp app.jar com.example.App
    |
T1: JVM defines PaymentService (initial load)
    |   No transformer from the new agent yet => the agent has not processed this class
    |
T2: application calls PaymentService.pay() multiple times
    |
T3: Attach tool -> VirtualMachine.loadAgent(agent.jar)
    |   -> JVM invokes Agent.agentmain(args, instrumentation)
    |
T4: agent calls instrumentation.addTransformer(t, true)
    |   t is registered, but the JVM does NOT automatically replay event T1
    |
T5: PaymentService.pay() continues running
    |   The old class still has the same method bytes as before if not replaced
    |
T6: agent finds the exact Class<?> of PaymentService
    |   checks capability and modifiability
    |   -> instrumentation.retransformClasses(target)
    |
T7: JVM invokes t.transform(...) during the retransform pass
    |   t may return valid new classfile bytes or return null
    |
T8: if valid bytes are installed, new method calls use the new version
        (active frames may still continue executing the old bytecode)
~~~

Distinguishing **registering the transformer at T4** from **requesting a retransform at T6** is the core of this article.

With a `-javaagent` startup agent, `premain` is called before `main`, so the agent can register transformers *before* important business classes are loaded. Conversely, attaching an agent to a running JVM usually encounters many already-loaded classes. The `addTransformer` contract does not pass them through the callback just because the agent was newly registered.

In particular, **“class already loaded” is not synonymous with “instances currently exist.”** A class may already have been defined, initialized, had its static initializer run, and had objects instantiated; none of those operations automatically re-triggers the class definition callback after registration.

## 3. What Does Each API Actually Do?

| API / Event | Role | Does It Automatically Reprocess Already-Loaded Classes? |
|---|---|---|
| `VirtualMachine.attach(pid)` | Attaches the tool to a target JVM | No |
| `VirtualMachine.loadAgent(path, args)` | Requests the target JVM to load the agent JAR and invoke `agentmain` | No, unless the agent code explicitly does so |
| `agentmain(String, Instrumentation)` | Entry point for a dynamically loaded Java agent | No; it is only the agent's initialization callback |
| `instrumentation.addTransformer(t)` | Registers a non-retransform-capable transformer | **No** |
| `instrumentation.addTransformer(t, true)` | Registers a transformer capable of receiving callbacks in subsequent retransformations | **No** |
| `instrumentation.getAllLoadedClasses()` | Lists the classes currently loaded by the JVM | No, query only |
| `instrumentation.isModifiableClass(c)` | Checks whether class `c` is of a kind the JVM allows modifying | No, query only |
| `instrumentation.retransformClasses(c)` | **Requests** re-running the transformation process for class `c` | **Yes**, if capability, target, and result are valid |
| `instrumentation.redefineClasses(...)` | Requests replacing a classfile definition with supplied bytes | Can replace an old class, but is a **different** mechanism requiring a different capability |

`addTransformer(t)` is equivalent to `addTransformer(t, false)`. If you want `t` itself to be called **again** during a retransform pass, it must be registered with `addTransformer(t, true)` **and** the JVM must actually support retransformation.

**Easy-to-miss detail:** a transformer registered with `canRetransform=false` can still participate when the JVM **defines a new class** or **redefines a class**. During a `retransformClasses` pass, the JVM **does not call** that transformer again; the previous results of non-capable transformers are **reused according to the specification**. Having a load-time callback does not prove having a retransform callback.

## 4. “Just Registered” Only Establishes a Relationship with Future Events

`Instrumentation.addTransformer` registers a callback into the class-file transformation pipeline; it is not a command to re-scan the heap, not a request for the JVM to re-run `ClassLoader.defineClass` for every class, and it does not re-initialize objects.

The following cases can cause `transform` to be invoked after you register:

- **A new definition** of a class not yet defined in the JVM by the corresponding loader.
- **A redefine pass** requested via the `redefineClasses` API.
- **A retransform pass** requested via `retransformClasses`, **if** the transformer was registered with `canRetransform=true`.
- In multi-classloader scenarios, a class with the same name newly defined by a **different loader** after attach: this is a **new class definition**, not an automatic retransform of the old class.

Conversely, activities that **do not automatically trigger transform again for an old class** include:

- Calling a method on an already-loaded class one more time.
- Creating a new object of an already-defined class.
- Reading a static field.
- Calling `Class.forName(...)` for a class already defined by the same loader (without creating a new class definition).
- Calling `getAllLoadedClasses()` and iterating over the list.
- Calling `addTransformer(t, true)` by itself.

In an environment with multiple class loaders, do not conclude “the transformer received the old class again” merely from logging the class name. Check **loader identity** and `classBeingRedefined` to distinguish a new class definition by another loader from a retransformation of the class in question.

## 5. Sufficient Capabilities Are Required: Manifest, JVM, Class, and Bytecode Changes

To process already-loaded classes via retransformation, separate layers of checks are needed:

### 5.1. The Agent JAR Must Declare Its Requirement

For a dynamic Java agent, the manifest main section contains:

~~~text
Manifest-Version: 1.0
Agent-Class: demo.ObserveAgent
Can-Retransform-Classes: true

~~~

`Agent-Class` is the name of the class containing `public static void agentmain(...)`. `Can-Retransform-Classes: true` is the declaration that retransformation is needed; if this attribute is omitted, it defaults to `false`.

**Do not confuse:** `Premain-Class` is for `-javaagent` before `main`. A single JAR can declare both entry points, but the Attach mechanism uses `Agent-Class` and `agentmain`.

### 5.2. The JVM Must Actually Support It

~~~java
if (!inst.isRetransformClassesSupported()) {
    // Do not use addTransformer(t, true) or retransformClasses.
}
~~~

JVM capabilities can depend on the implementation/configuration. **Declaring `true` is not enough**: the result of `isRetransformClassesSupported()` reflects the current agent runtime. If it returns `false`, `addTransformer(t, true)` may throw `UnsupportedOperationException`; a `retransformClasses` request will also be unavailable.

If the agent only needs new class load events, it can still use `addTransformer(t)` as a fallback, but it must clearly report that it is **not retroactive**. If the product requires patching an existing class to ensure correctness, it should fail fast or disable that specific feature rather than logging a false success.

### 5.3. The Target Class Must Be Modifiable

~~~java
if (!inst.isModifiableClass(targetClass)) {
    // Skip the target or clearly report the reason.
}
~~~

`isModifiableClass` is a query about **the class object itself**, independent of the JVM-wide capability. Primitive classes and array classes are not modifiable; many special JVM classes may also not support modification. Even for a modifiable class, a **specific modification** may still violate bytecode/class schema limits.

### 5.4. You Must Find the Exact Loaded `Class<?>`

`getAllLoadedClasses()` returns the list of loaded class objects. You should filter not only by name, but also by defining loader and, if needed, by module/code source:

~~~java
Class<?> target = null;
for (Class<?> c : inst.getAllLoadedClasses()) {
    if ("com.example.PaymentService".equals(c.getName())
            && c.getClassLoader() == expectedLoader) {
        target = c;
        break;
    }
}
~~~

This is an **illustrative snippet**: `expectedLoader` must be determined by the agent according to the actual architecture, and is not a standalone program. Two classes with the same binary name defined by two different loaders are **two different runtime types**. Indiscriminately calling `Class.forName(...)` to find the target can **itself create a new class definition**, defeating the goal of “getting the class that was already loaded.”

### 5.5. The New Classfile Must Be Valid and Within Limits

During retransform, the JVM invokes capable transformers; a transformer can produce new bytes. Changes such as altering the hierarchy, adding/removing members, or modifying structure are not supported on many JVMs under the retransformation contract. `retransformClasses` can fail with `UnmodifiableClassException`, `UnsupportedOperationException`, `ClassFormatError`, `UnsupportedClassVersionError`, `LinkageError`, or other classfile errors.

**Do not infer** from “capability true, class modifiable true” that every change will be applied. Verifying valid bytecode, stack map frames, loader/module visibility, and the operation's outcome are separate steps.

## 6. Runnable Java 17+ Example: Attaching Twice to Distinguish Registration from Retransform

The goal of this example is to prove that **the callback does not automatically re-run on an already-loaded class**. To avoid depending on a bytecode manipulation library, the transformer will **only print a log message and return `null`**. As a result:

- First attach in `register` mode: registers the transformer; `demo.Service` is already loaded, so there is **no `transform` callback for it** solely from registration.
- Second attach with `retransform`: the agent explicitly calls `retransformClasses(demo.Service.class)` using the exact `Class<?>` retrieved from the JVM. The callback will print an indication that it ran again.
- The `Service.message()` method still returns `ORIGINAL`, because the transformer **does not modify the classfile**. This is an important point so you do not confuse “retransformed” with “behavior modified.”

The example uses **one target JVM** and **one AttachTool JVM** running separately. The Attach API may be restricted by OS permissions, containers, JDK variants, or security policies. Do not use this guide to attach to JVMs outside your administrative authority.

### 6.1. File Structure

~~~text
attach-retransform-demo/
├── AGENT.MF
├── src/
│   ├── app/demo/
│   │   ├── Service.java
│   │   └── Target.java
│   ├── agent/demo/
│   │   └── ObserveAgent.java
│   └── tool/demo/
│       └── AttachTool.java
└── out/                         # created during the build step
    ├── app/
    ├── agent/
    ├── tool/
    └── observe-agent.jar
~~~

There are **four Java files** and **one manifest**. Maven/Gradle, ASM, or Byte Buddy are not required. Only a full JDK 17+ with the `jdk.attach` module and a target JVM that allows dynamic agent loading are needed.

### 6.2. File `src/app/demo/Service.java`

~~~java
package demo;

public final class Service {
    private Service() {}

    public static String message() {
        return "ORIGINAL";
    }
}
~~~

We want the class to be loaded **before attaching**. The target code below calls `Service.message()` right at startup, so the fact that the class is already loaded is observable.

### 6.3. File `src/app/demo/Target.java`

~~~java
package demo;

import java.io.BufferedReader;
import java.io.InputStreamReader;

public final class Target {
    private Target() {}

    public static void main(String[] args) throws Exception {
        System.out.println("[target] pid=" + ProcessHandle.current().pid());
        System.out.println("[target] initial=" + Service.message());
        System.out.println("[target] enter tick or exit");

        BufferedReader reader = new BufferedReader(
                new InputStreamReader(System.in));

        String command;
        while ((command = reader.readLine()) != null) {
            if ("exit".equals(command)) {
                break;
            }
            if ("tick".equals(command)) {
                System.out.println(
                        "[target] current=" + Service.message());
            } else {
                System.out.println("[target] unknown command");
            }
        }
        System.out.println("[target] finished");
    }
}
~~~

Target waits for input so you can proactively check the state **before**, **after register**, and **after retransform**. It does not use `Thread.sleep` and does not rely on a race between two processes to infer state.

### 6.4. File `src/agent/demo/ObserveAgent.java`

~~~java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class ObserveAgent {
    private static ClassFileTransformer observer;

    private ObserveAgent() {}

    public static synchronized void agentmain(
            String mode, Instrumentation inst) throws Exception {

        if ("register".equals(mode)) {
            register(inst);
        } else if ("retransform".equals(mode)) {
            retransform(inst);
        } else {
            throw new IllegalArgumentException("Unknown mode: " + mode);
        }
    }

    private static void register(Instrumentation inst) {
        if (observer != null) {
            System.out.println("[agent] already registered");
            return;
        }

        boolean capable = inst.isRetransformClassesSupported();

        ClassFileTransformer t = new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    Module module,
                    ClassLoader loader,
                    String className,
                    Class<?> classBeingRedefined,
                    ProtectionDomain protectionDomain,
                    byte[] classfileBuffer) {

                if ("demo/Service".equals(className)) {
                    System.out.println("[agent] transform demo.Service"
                            + " redefined="
                            + (classBeingRedefined != null));
                }

                return null; // Keep bytes unchanged.
            }
        };

        // If the JVM does not support retransform, still have a load-time callback.
        inst.addTransformer(t, capable);
        observer = t;

        Class<?> target = findLoadedService(inst);
        System.out.println("[agent] registered"
                + " canRetransform=" + capable
                + " alreadyLoaded=" + (target != null));
    }

    private static void retransform(Instrumentation inst)
            throws java.lang.instrument.UnmodifiableClassException {

        if (observer == null) {
            System.out.println("[agent] register first");
            return;
        }
        if (!inst.isRetransformClassesSupported()) {
            System.out.println("[agent] retransform unsupported");
            return;
        }

        Class<?> target = findLoadedService(inst);
        if (target == null) {
            System.out.println("[agent] Service not loaded");
            return;
        }
        if (!inst.isModifiableClass(target)) {
            System.out.println("[agent] Service not modifiable");
            return;
        }

        System.out.println("[agent] requesting retransform");
        inst.retransformClasses(target);
        System.out.println("[agent] retransform completed");
    }

    private static Class<?> findLoadedService(Instrumentation inst) {
        for (Class<?> c : inst.getAllLoadedClasses()) {
            if ("demo.Service".equals(c.getName())
                    && c.getClassLoader()
                       == ClassLoader.getSystemClassLoader()) {
                return c;
            }
        }
        return null;
    }
}
~~~

**Why can two attaches share the same state?** In this example scenario, the same agent class `demo.ObserveAgent` is defined by the system loader in the target JVM, so the static field `observer` holds the transformer reference across both `agentmain` calls. We do not re-register the transformer on the second attach, avoiding duplicate callbacks.

**Accurate note on loaded classes:** `getAllLoadedClasses()` only lists the `Class<?>` objects the JVM already knows about; it does not automatically “replay” them through transformers. `findLoadedService` checks both name and loader identity. The system loader condition fits the demo application run with `-cp out/app`; applications using other loaders must adjust the condition accordingly.

**Note on the callback:** `className` is the internal name `demo/Service`, not `demo.Service`. `classBeingRedefined != null` helps observe a retransform pass of an existing class. For an ordinary new class definition, this value is `null`.

### 6.5. File `src/tool/demo/AttachTool.java`

~~~java
package demo;

import com.sun.tools.attach.VirtualMachine;
import java.nio.file.Path;

public final class AttachTool {
    private AttachTool() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "Usage: AttachTool <pid> <agent-jar> <mode>");
        }

        String pid = args[0];
        String agentJar = Path.of(args[1])
                .toAbsolutePath()
                .toString();

        VirtualMachine vm = VirtualMachine.attach(pid);
        try {
            vm.loadAgent(agentJar, args[2]);
            System.out.println(
                    "[tool] loadAgent complete: " + args[2]);
        } finally {
            vm.detach();
        }
    }
}
~~~

`VirtualMachine.attach(...)` connects to a target JVM with valid attach permissions. `loadAgent(...)` sends a request to load the agent JAR **at a path accessible to the target JVM**, and invokes `agentmain`; per the Java Attach API contract, `loadAgent` completes when `agentmain` completes. `detach()` releases the tool's Attach session; it does **not** mean removing the transformer registered inside the target.

The `com.sun.tools.attach.VirtualMachine` class belongs to **`jdk.attach`**, not the `java.instrument` module. The target JVM and AttachTool are **two different processes**: `[agent]` logs appear in the target's console; `[tool]` logs appear in AttachTool's console.

### 6.6. Manifest File `AGENT.MF`

~~~text
Manifest-Version: 1.0
Agent-Class: demo.ObserveAgent
Can-Retransform-Classes: true

~~~

The file must end with a newline, and the attributes above must be in the **main section** of the manifest. The `Can-Retransform-Classes: true` attribute requests the capability to use `retransformClasses`; the actual JVM must also support it. `Premain-Class` is not needed in this example because we are not using `-javaagent`.

### 6.7. Compiling and Packaging

Open a terminal in the `attach-retransform-demo` directory and create three output directories.

**Bash:**

~~~bash
mkdir -p out/app out/agent out/tool
~~~

**PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force out/app, out/agent, out/tool | Out-Null
~~~

Then use JDK 17+:

~~~bash
javac --release 17 -d out/app src/app/demo/Service.java src/app/demo/Target.java

javac --release 17 -d out/agent src/agent/demo/ObserveAgent.java

javac --release 17 --add-modules jdk.attach -d out/tool src/tool/demo/AttachTool.java

jar cfm out/observe-agent.jar AGENT.MF -C out/agent .
~~~

`javac --release 17` produces Java 17-compatible bytecode. When building AttachTool, `--add-modules jdk.attach` makes explicit the module the tool uses; at runtime this module is also added when running AttachTool. The commands above assume a full JDK with the Attach module, not a stripped-down JRE/runtime that removed this module.

You can verify that the agent JAR contains `META-INF/MANIFEST.MF` and `demo/ObserveAgent.class` with `jar tf out/observe-agent.jar`. Note: the `AGENT.MF` file in the workspace does not automatically become the JAR manifest if you package with the wrong command; `jar cfm` with the manifest argument is the crucial step.

### 6.8. Terminal 1: Run the Target JVM

~~~bash
java -XX:+EnableDynamicAgentLoading -cp out/app demo.Target
~~~

Example output (the PID is just an illustrative number, **use the actual PID from your terminal**):

~~~text
[target] pid=12345
[target] initial=ORIGINAL
[target] enter tick or exit
~~~

`-XX:+EnableDynamicAgentLoading` is a HotSpot option to allow dynamic agent loading and avoid related warnings on JDK versions that emit them. Depending on the implementation, policy, security settings, and JDK version, dynamic agent loading may be blocked. On HotSpot JDK 21+, JEP 451 warns when loading agents dynamically without opt-in; **do not assume all JVMs/vendors allow attach**. Practice on a JVM you control.

Important: `Service.message()` was already called to print `initial=ORIGINAL`, so the JVM has already loaded `demo.Service` **before** you run AttachTool. If the target has not printed `initial=ORIGINAL` yet, do not start the attach step.

### 6.9. Terminal 2: First Attach Only Registers

Replace `12345` with the actual PID from terminal 1:

~~~bash
java --add-modules jdk.attach -cp out/tool demo.AttachTool 12345 out/observe-agent.jar register
~~~

Terminal 2:

~~~text
[tool] loadAgent complete: register
~~~

Terminal 1 (the agent prints to the target's stdout):

~~~text
[agent] registered canRetransform=true alreadyLoaded=true
~~~

This is the **expected result on a HotSpot JDK that supports retransformation**. If the JVM returns `isRetransformClassesSupported() == false`, the line will print `canRetransform=false`; in that case the example still registers a load-time transformer, but the subsequent retransform step must be skipped.

**Key observation:** there is no `[agent] transform demo.Service ...` line during this attach. Successful registration **does not** cause already-loaded classes to automatically replay the callback.

Return to terminal 1 and type:

~~~text
tick
~~~

You will see:

~~~text
[target] current=ORIGINAL
~~~

Press Enter after `tick` so the application reads the command. Calling `Service.message()` again does not cause `transform` to be invoked again.

### 6.10. Terminal 2: Second Attach Explicitly Retransforms

Still using **the same PID and the same JAR**:

~~~bash
java --add-modules jdk.attach -cp out/tool demo.AttachTool 12345 out/observe-agent.jar retransform
~~~

Terminal 2:

~~~text
[tool] loadAgent complete: retransform
~~~

Terminal 1:

~~~text
[agent] requesting retransform
[agent] transform demo.Service redefined=true
[agent] retransform completed
~~~

This is clear evidence that **the explicit retransform pass** invoked the transformer again. `classBeingRedefined != null` confirms the callback is processing an already-existing class. Because the demo returns `null`, the JVM receives no modified bytes from this transformer.

Type `tick` again in terminal 1:

~~~text
[target] current=ORIGINAL
~~~

**Do not conclude that retransform failed:** in the demo, the transformer only observes and **never produces different bytecode**, so unchanged behavior is correct. To actually change a method, the transformer must return **a valid new classfile byte array** while also satisfying retransform constraints. That is an additional step outside the scope of this experiment.

Finally, type `exit` in terminal 1 to finish:

~~~text
[target] finished
~~~

### 6.11. Output Does Not Need Strict Cross-Process Ordering

The two terminals have separate stdout streams, so you cannot enforce a single total order across all log lines just by looking at them. Instead, correlate by **explicit synchronization milestones**:

1. `[target] initial=ORIGINAL` appeared before starting the attach.
2. `[tool] loadAgent complete: register` means the `agentmain("register", ...)` call has finished.
3. Immediately after register, there is no callback for the old target solely from registration.
4. `[tool] loadAgent complete: retransform` means `agentmain("retransform", ...)` has completed; during this step there was a specific retransform request and a callback for the target.
5. `tick` returns `ORIGINAL` after both steps, because the transform code is an observer that `return null`s.

If another profiler/agent is active or the target contains multiple `demo.Service` classes from custom loaders, the output may contain extra callbacks; the example assumes a simple target without other agents.

## 7. Why Registering `canRetransform=true` Is Still Not Enough

The `true` flag in `addTransformer(t, true)` declares **the capability to participate in future retransform passes**. It does not specify:

- Which target classes need processing.
- When you want them reprocessed.
- Whether the JVM needs to pause/synchronize the activity of running classes.
- What new bytes should be produced.
- Whether changing class structure or loading helpers is permitted.
- Whether every existing instance must be accessed.

That is why the API separately designs `retransformClasses(Class<?>... classes)` so the caller names **a specific set of classes**, rather than automatically processing all of `getAllLoadedClasses()`.

You should also not unconditionally run retransform on **every** loaded class to “compensate for late attach.” Doing so can be very resource-intensive, hit unmodifiable core/JDK/hidden/array classes, break dependency ordering, and cause the tool to unintentionally interfere with out-of-scope classes. Determine filters by name, loader, module, code source, and `isModifiableClass` **before calling** retransform.

## 8. What Happens Inside `retransformClasses`?

According to the `Instrumentation` contract, a retransform pass proceeds roughly in this sequence:

~~~text
Loaded Class<?> target
       |
       v
JVM obtains the baseline classfile bytes for retransformation
       |
       +-- transformer registered with canRetransform=false:
       |      NO callback again; reapplies previous result per JVM rules
       |
       +-- transformer registered with canRetransform=true:
       |      JVM invokes transform(...) to get new bytes or null
       |
       v
JVM verifies the classfile/result and class schema constraints
       |
       +-- failure -> exception, no classes in the batch are retransformed
       |
       +-- success -> new definition is installed
                         (no new instances created; <clinit> does not re-run)
~~~

Several important details:

- The input classfile data for a retransform pass may not be **byte-for-byte identical** to the original classfile on disk: the JVM may reorder/reformat the constant pool or drop irrelevant attributes.
- Non-capable transformers **are not called again** during a retransform pass; instead, the JVM reapplies their previous effect according to the specification rules.
- Capable transformers must process the input supplied by the JVM and should avoid repeated transformations that duplicate instrumentation code (idempotency).
- `retransformClasses` does not re-run static initializers and **does not reset static fields**.
- Existing instances remain instances of that class; objects are not re-created.
- If a method currently has an active stack frame, the current frame may **continue executing the old bytecode**; new method calls use the new definition after success.
- When a pass over a group of classes fails with an exception, **none of the classes in that pass are retransformed** according to the contract.

Thus, retransform is neither “restarting a class” nor “restarting the application.” If you need to change the object model/field layout, class redefinition cannot arbitrarily do that either.

## 9. What Additional Steps Are Needed to See Real Behavioral Changes?

Only when a transformer returns a **new, valid classfile `byte[]`** with a modified method can a retransformation pass change behavior. Pseudocode:

~~~text
transform(module, loader, className, beingRedefined, domain, bytes):
    if className != "demo/Service":
        return null

    if loader != expectedLoader:
        return null

    modified = bytecodeLibrary.transform(bytes)
        // For example, insert timing code into a specific method;
        // must keep the classfile valid and within retransform limits.

    if noChange:
        return null
    return modified  // new byte[], do NOT mutate input bytes in place
~~~

This is **pseudocode**, not a standalone compilable Java program. For Java 17, you can use an appropriate bytecode manipulation library such as ASM/Byte Buddy. `java.lang.classfile` is the standard Class-File API starting in **JDK 24**; do not use that API in the Java 17 example above.

If modifying classes in a production JVM:

1. Select only the classes that need changing, by **actual class identity**.
2. Ensure the transformer does not unintentionally instrument the agent/its own helpers or core JDK classes.
3. Generate new class bytes with a compatible structure; avoid adding/removing fields/methods, changing superclass/interfaces, and other unsupported schema changes.
4. Check the exception table, StackMapTable, frames, monitors, and behavior of methods with try/finally/early returns.
5. Check whether injected helper bytecode is visible from the target's loader/module.
6. Choose how to handle transformation failures: fail-open, skip target, disable feature, or deliberate fail-fast.
7. Run functional tests before/after in the same process, including active stack frames and concurrency.

**Point to remember:** a `"transform invoked"` log proves the callback was called, not that the transformer returned different bytes; a `"retransform completed"` log proves the API finished, not that the application's functionality/bytecode changed as intended.

## 10. Common Mistakes

### 10.1. Calling Only `addTransformer(t)` and Waiting for Old Classes to Change

`addTransformer(t)` is not retransform-capable and does not request any class to re-run. Fix this by clarifying the requirement: if you only want **later-loaded** classes, retransform is not needed; if you want **already-loaded** classes, use the capability + `addTransformer(t,true)` + `retransformClasses(target)`.

### 10.2. Registering with `true` While Ignoring Capability

If `isRetransformClassesSupported() == false`, the `addTransformer(t,true)` overload is not permitted. Always check and accurately report the effective mode instead of guessing from the manifest.

### 10.3. Calling `retransformClasses` with Non-Modifiable Classes

`getAllLoadedClasses()` can contain arrays, primitive-like objects, hidden classes, or special classes. Only include classes that are truly needed and have `isModifiableClass(c)==true` in the request set. An `UnmodifiableClassException` should be explained rather than retried in an infinite loop.

### 10.4. Selecting Classes by String Name Alone

Two loaders can both define `com.example.Service`. Same binary name does not mean same runtime type. Class loader identity and module/source policy are needed in multi-loader environments.

### 10.5. Registering the Same Transformer Multiple Times

`addTransformer` can register the same object multiple times, but the specification discourages it because it can cause duplicate callbacks and multiply-instrumented code. Across multiple Attaches, use idempotent state or a registry; consider `removeTransformer` on shutdown.

### 10.6. Thinking `return null` Means Retransform Failed

`return null` in `transform` means the callback did not change the class bytes. The retransform pass can still complete. That is the exact intended result of the observer in the demo.

### 10.7. Thinking `Class.forName` Always Returns the Class You Want to Modify

`Class.forName` depends on the chosen loader and can trigger **a new class definition**. Use `getAllLoadedClasses()`, check class identity/loader and modifiability; avoid accidentally loading classes during inspection.

### 10.8. Confusing `redefineClasses` with `retransformClasses`

`redefineClasses` takes a `ClassDefinition` and caller-supplied classfile bytes, requiring `Can-Redefine-Classes`/`isRedefineClassesSupported()`. `retransformClasses` re-runs the transformer chain per the contract, requiring `Can-Retransform-Classes`/`isRetransformClassesSupported()`. These two capabilities are **different**.

### 10.9. Watching Only AttachTool Logs

`AttachTool` runs outside the target process; `agentmain` and `transform` run **inside the target JVM**. If you do not see agent logs in the tool's terminal, it does not mean the agent is inactive; check the target's actual stdout/logging backend.

### 10.10. Assuming Dynamic Attach Is Always Allowed

The JVM may forbid the Attach API or agent loading based on OS permissions, containers, JVM options, and security policy. Starting in JDK 21, JEP 451 prepares to change dynamic agent loading policy and issues warnings unless properly opted in. If attach fails, you cannot diagnose the cause by “adding retransformClasses”: those are two separate steps.

## 11. Symptom-Based Diagnostic Table

| Symptom | Likely Explanation | Next Check |
|---|---|---|
| `loadAgent` throws `AgentLoadException` | JAR/path/manifest or target environment cannot load the agent | `Agent-Class`, target path, attach permissions |
| Agent prints `agentmain started`, no transform seen for old target | No new load event for an already-defined class | Use `getAllLoadedClasses`, check capability |
| `addTransformer(t,true)` throws `UnsupportedOperationException` | Retransformation capability is not supported/granted | `Can-Retransform-Classes`, `isRetransformClassesSupported` |
| `retransformClasses` called, but `t`'s callback is not seen | `t` may have been registered with `canRetransform=false` or filtered out | Check registration overload, target identity, className |
| Callback logs, method behaves the same | Transformer returned `null` or bytes with identical behavior | Verify scoped bytecode output; test behavior |
| Callback runs twice unexpectedly | Transformer may be registered twice or class reloaded via another loader | Check idempotent registration, loader |
| `UnmodifiableClassException` | A target class cannot be modified | Check `isModifiableClass` before requesting |
| `ClassFormatError` / `VerifyError` | Transformed classfile is invalid | Check verifier/stack maps/classfile version |
| Just retransformed, yet running thread has not changed behavior | Active frame may continue using old bytecode version | Test on a new call after the successful pass |
| JVM rejects dynamic agent loading | Configuration/permission/integrity policy | Check startup agent option or official opt-in |

## 12. When Should You Use `-javaagent` Instead of Late Attach?

If the product requirement is to **instrument every initial definition of business classes** and you can modify how the JVM is launched, use:

~~~bash
java -javaagent:agent.jar -cp out/app demo.Target
~~~

with an appropriate `Premain-Class` manifest attribute and `premain` method. Registering the transformer from `premain` **before `main`** helps observe many business classes on their first load. However, the JVM/agent may already have loaded some classes before `premain`; therefore, a startup agent does not mean no core classes have ever been defined yet either.

The Attach API is useful for profiling/debugging or instrumenting a running JVM without restarting, **when permitted**. The trade-off is that many classes are already loaded, so you must handle finding classes, requesting retransform, capability checks, idempotency, and safe rollback/redeploy.

| Requirement | `-javaagent` / `premain` | Attach / `agentmain` |
|---|---|---|
| Observe business classes from the start | Usually more favorable | May have already missed initial class loads |
| No application restart | Not suitable if the app is already running | Suitable when dynamic attach is allowed |
| Already-loaded classes need bytecode changes | Still needs retransform/redefine if loaded before registration | Needs conditional retransform/redefine |
| Security/integrity policy | Declared at startup | Must consider attach permissions and dynamic loading policy |
| Operational control | Configured at startup | Additional step to coordinate target process and agent lifecycle |

## 13. Minimum Checklist for an Attach + Retransformation Agent

- [ ] Target process is a JVM you administer, and the environment allows the Attach API and dynamic agent loading.
- [ ] Agent JAR has `Agent-Class` and `public static void agentmain(String, Instrumentation)` with the exact signature.
- [ ] Manifest declares `Can-Retransform-Classes: true` **if retransform is needed**, not just `Premain-Class`.
- [ ] JVM returns `isRetransformClassesSupported()==true` before using the `addTransformer(t,true)` overload / `retransformClasses`.
- [ ] Transformer is registered **once**, with appropriate name/loader/module filters and ready state.
- [ ] `getAllLoadedClasses()` has identified the **exact `Class<?>`** to modify, not just a string name.
- [ ] `isModifiableClass(target)==true`; exclude arrays/primitives/unsupported classes.
- [ ] **Explicitly** call `retransformClasses(target)` when you want to process already-loaded classes.
- [ ] Callback actually receives `classBeingRedefined != null` for the target during retransform.
- [ ] If behavior needs to change, the transformer must return **different and valid** bytes, not `null`.
- [ ] Test code paths and error paths, active frames, loader/module visibility, and latency.
- [ ] Log distinctions between **registered**, **retransform requested**, **callback invoked**, **applied**, and **behavior verified**.

## 14. Self-Check Questions

**Question 1.** An agent attaches successfully, and `agentmain` calls `addTransformer(t,true)`. Do previously loaded classes automatically receive the callback?

> No. `addTransformer` only registers the callback. To reprocess already-loaded classes, you must select the exact `Class<?>` and call `retransformClasses` if the runtime supports it.

**Question 2.** Why is `Can-Retransform-Classes: true` not enough?

> That is only a declaration of intent in the manifest. The current JVM must also support retransformation; use `isRetransformClassesSupported()` to decide how to proceed.

**Question 3.** When is `transform` called again on an already-loaded class?

> During a requested retransform pass (when the transformer has `canRetransform=true`), or a redefine pass per the API contract. Calling a method on an object does not automatically trigger such a pass.

**Question 4.** Why must you also check the loader when searching for the target?

> One binary name can be defined by multiple class loaders into distinct runtime classes. `retransformClasses` requires the exact `Class<?>` object.

**Question 5.** The demo prints `[agent] transform demo.Service redefined=true`, yet `Service.message()` still returns `ORIGINAL`. Why?

> The transformer only observes and returns `null`. The callback was invoked and the retransform pass completed, but no modified bytes were supplied by that transformer to change the method body.

**Question 6.** Does a transformer registered with `addTransformer(t)` get called back by the JVM during retransform?

> No. That is a `canRetransform=false` transformer. During a retransform pass, the JVM reuses its previous transformation result per the specification instead of calling `t` again.

**Question 7.** Does `retransformClasses` re-run static initializers, refresh instances, or replace all active frames?

> No. Class initializers do not automatically re-run, existing instances remain intact, and active frames may continue executing the old bytecode; new calls use the new definition after the retransform succeeds.

**Question 8.** If the JVM disallows dynamic attach, will adding a `retransformClasses` call inside the agent help attach succeed?

> No. That is an issue of **loading the agent into the JVM**. Only once the agent has been loaded and has `Instrumentation` can retransformation be considered.

## 15. Official Documentation

- Java SE 17, `java.lang.instrument`: `premain`/`agentmain` mechanism, `Agent-Class` and `Can-Retransform-Classes` manifest attributes: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
- Java SE 17, `Instrumentation`: `addTransformer`, `getAllLoadedClasses`, `isRetransformClassesSupported`, `isModifiableClass`, `retransformClasses`, `redefineClasses`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- Java SE 17, `ClassFileTransformer`: callback at load/redefine/retransform, `canRetransform`, and `return null` behavior: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
- Java SE 17, `VirtualMachine` (Attach API): `attach`, `loadAgent`, and `detach`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html
- JEP 451 — **Prepare to Disallow the Dynamic Loading of Agents**: dynamic agent loading warnings starting in JDK 21 and the opt-in mechanism: https://openjdk.org/jeps/451
- Java SE 17, `UnmodifiableClassException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/UnmodifiableClassException.html
