# Distinguishing `Main-Class`, `Premain-Class`, `Agent-Class`, and `Launcher-Agent-Class`

All four attributes can appear in a JAR's `META-INF/MANIFEST.MF`, but they **do not specify the same kind of entrypoint**. `Main-Class` selects the starting point of the **application**; the other three attributes select the starting point of a **Java instrumentation agent** through three different mechanisms. The easiest point to confuse: `Launcher-Agent-Class` contains the word *Launcher* but invokes **`agentmain`**, not `premain`, and runs **before** the application's `main`.

This lesson focuses on agents at JVM/executable JAR startup time; the attach mechanism for an already-running JVM is presented to clarify the difference between `Agent-Class` and `Launcher-Agent-Class`.

## 1. Map of the Four Attributes

| Attribute in main manifest | Triggered by | Method invoked | Timing | Role |
|---|---|---|---|---|
| `Main-Class` | `java -jar app.jar` | `public static void main(String[] args)` | Application entry point | Specifies the application class to run |
| `Premain-Class` | `java -javaagent:agent.jar[=options] ...` | `public static void premain(String, Instrumentation)` or `premain(String)` | Before application `main` | Installs an agent from the start of the JVM session |
| `Agent-Class` | Tool attaching/loading an agent into a **running JVM** | `public static void agentmain(String, Instrumentation)` or `agentmain(String)` | After the JVM has started, usually after the application has entered `main` | Initializes a dynamic agent |
| `Launcher-Agent-Class` | Launching an **executable JAR** containing an agent alongside the application, typically `java -jar app.jar` | `public static void agentmain(String, Instrumentation)` or `agentmain(String)` | Before application `main` | Agent bundled directly inside the application JAR |

Values such as `demo.DemoApp` and `demo.DemoAgent` are **binary names of Java classes** by package (dot-separated, without `.class`, not file paths). The attributes must be placed in the **main section** of the manifest. The JVM does not run every entrypoint just because it sees all four names in the same JAR: the JVM chooses based on **how the program/agent is launched**.

You can remember this with four questions:

- **Which application to run?** → `Main-Class`.
- **Load an agent via a JVM argument right at startup?** → `Premain-Class`.
- **Load an agent into an already-running process?** → `Agent-Class`.
- **Automatically run an agent packaged inside an executable JAR?** → `Launcher-Agent-Class`.

### Overall Flow

~~~text
java -jar app.jar
    reads Main-Class + Launcher-Agent-Class (if present)
    -> invokes launcher agent: agentmain("", Instrumentation)
    -> invokes application: main(String[])

java -javaagent:agent.jar=cfg -cp ... demo.DemoApp
    reads Premain-Class in agent.jar
    -> invokes startup agent: premain("cfg", Instrumentation)
    -> invokes application: main(String[])

Running application JVM
    attach tool calls loadAgent("agent.jar", "cfg")
    -> reads Agent-Class in agent.jar
    -> invokes dynamic agent: agentmain("cfg", Instrumentation)
    -> application continues running
~~~

The diagram illustrates **three independent activation paths**. The `java -javaagent:...` line above intentionally runs the application using `-cp`, so as not to simultaneously trigger `Launcher-Agent-Class` from an executable JAR. If a user intentionally combines `-javaagent` with `-jar`, both startup mechanisms can launch an agent together; each mechanism must be considered individually, without assuming that one attribute "takes precedence" and disables the other.

## 2. `Main-Class`: The Application Entrypoint

Example manifest:

~~~text
Manifest-Version: 1.0
Main-Class: demo.DemoApp

~~~

When running `java -jar app.jar`, the Java launcher looks up `Main-Class`, loads the specified class, and invokes the `main` entrypoint. In the Java 17 example in this lesson, the signature is:

~~~java
public static void main(String[] args) throws Exception
~~~

`args` receives the arguments **after the JAR name** in the command `java -jar app.jar one two`. `Main-Class` **does not provide `Instrumentation`**, does not define `premain`/`agentmain`, and does not turn an application into an agent on its own. If an application JAR lacks a valid `Main-Class`, `java -jar` does not know which class to use as the starting point and will fail to launch with an error.

Important difference:

~~~bash
java -jar app.jar
java -cp app.jar demo.DemoApp
~~~

The first command obtains the entrypoint from `Main-Class`. The second command uses an **explicitly specified class name** and does not rely on `Main-Class` in the manifest. The `Launcher-Agent-Class` attribute is also a mechanism for executable JARs; merely placing a JAR on `-cp` does not cause that JAR's launcher agent to run automatically.

`Main-Class` applies to application JARs, not as a required `main()` for an agent. An agent JAR used solely with `-javaagent` can completely **omit `Main-Class`**.

## 3. `Premain-Class`: Java Agent from the Command Line

Agent manifest:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.DemoAgent

~~~

Activation command:

~~~bash
java -javaagent:agent.jar=trace -cp app.jar demo.DemoApp
~~~

The JVM reads `Premain-Class` from **`agent.jar`** and invokes the `premain` method **before** invoking the application's `main`. Accepted signatures:

~~~java
public static void premain(
        String agentArgs,
        java.lang.instrument.Instrumentation inst)

// Fallback signature, if the class does not declare the two-parameter form:
public static void premain(String agentArgs)
~~~

These are **illustrative method signatures**, not two methods that must both be declared at the same time. The JVM prioritizes the `(String, Instrumentation)` form, and only looks for the `(String)` form if the preferred form does not exist. In practice, the two-parameter form is usually useful because `Instrumentation` allows registering a `ClassFileTransformer`, inspecting loaded classes, and performing instrumentation operations supported by the JVM.

- `agentArgs` is **a single string** containing the part after the `=` sign in `-javaagent:...=...`. If a format like `key=value,flag` is desired, the agent parses it itself.
- The application's `String[] args` is separate from `agentArgs`; agent options are not automatically converted into application arguments.
- Multiple `-javaagent` flags can be used; the JVM invokes the `premain` methods **in the order they appear on the command line**.
- When an agent lacks `Premain-Class`, lacks a matching `premain`, or `premain` throws an unhandled error, the JVM **aborts startup before `main`**.
- Even if an agent class has both `premain` and `agentmain`, the `-javaagent` mechanism only selects **`premain`** and does not invoke `agentmain` instead.

`premain` is not an entry point before *every* JVM activity: the JVM has already performed its own initialization beforehand. It is invoked before the application's `main` and may cause many classes to be loaded while the agent initializes. If you want to monitor classes loaded afterward, the agent typically registers its transformer directly inside `premain`.

## 4. `Agent-Class`: Agent Loaded After the JVM Is Running

Agent manifest:

~~~text
Manifest-Version: 1.0
Agent-Class: demo.DemoAgent

~~~

On this path, a tool attaches to a running JVM and requests loading a JAR as an agent, for example via the `com.sun.tools.attach.VirtualMachine.loadAgent` API. The JVM reads `Agent-Class` and invokes:

~~~java
public static void agentmain(
        String agentArgs,
        java.lang.instrument.Instrumentation inst)

// Fallback signature if the two-parameter form is absent:
public static void agentmain(String agentArgs)
~~~

The method name **must be `agentmain`**. Having `premain` in that class does not make it an entrypoint for dynamic attach. `agentArgs` receives the options string passed by the attach tool; there is no mandatory convention requiring it to match `-javaagent` arguments.

At runtime, application classes may **already be loaded and executing** when `agentmain` runs. Registering a transformer at this point does not mean all already-loaded classes are automatically transformed retroactively. Depending on the capabilities granted by the JVM and declared in the manifest, the agent can use `Instrumentation.retransformClasses`/`redefineClasses` for eligible classes. This is separate from invoking the entrypoint.

Unlike startup agent errors, dynamic agent loading errors typically **do not force the application JVM to stop** according to the `java.lang.instrument` specification (the attach tool may receive an error, and the JVM may log a message). The attach mechanism depends on the JVM, policy, and environment: process permissions, the `jdk.attach` module, attach supportability, and security configurations can restrict the operation. **Merely having `Agent-Class` in the manifest does not automatically attach to any JVM**.

With HotSpot JDK 21, dynamic agent loading may emit a warning per JEP 451; depending on policy, launching the target JVM with `-XX:+EnableDynamicAgentLoading` explicitly opts in to allowing dynamic agent loading and avoids the warning. This is a setting related to **dynamic attach**, not a normal requirement for using `-javaagent` at startup.

## 5. `Launcher-Agent-Class`: Agent Bundled with an Executable JAR

Application manifest combined with an agent:

~~~text
Manifest-Version: 1.0
Main-Class: demo.DemoApp
Launcher-Agent-Class: demo.DemoAgent

~~~

Typical command:

~~~bash
java -jar app.jar
~~~

If the Java launcher/runtime supports this executable JAR mechanism, it looks up the agent class declared via `Launcher-Agent-Class` **inside the application JAR itself**, invokes **`agentmain` before `main`**, and only then lets the application run. This is still a **startup agent in terms of execution timing**, even though the callback name is `agentmain`.

Points to distinguish accurately:

1. `Launcher-Agent-Class` invokes **`agentmain`**, not `premain`; the valid signatures are the same as for `Agent-Class`.
2. `agentArgs` passed into `agentmain` via the **launcher agent path is always the empty string `""`**, even when `java -jar app.jar first second` has application arguments. The two arguments `first` and `second` go into `main(String[])`, **not into the agent**.
3. The agent class must **be packaged in the same executable JAR**; unlike `-javaagent`, which explicitly points to a standalone agent JAR.
4. If `Launcher-Agent-Class` is declared but the agent cannot be loaded, lacks a valid `agentmain`, or the callback throws an uncaught exception/error, **the JVM aborts before `main`**.
5. `Launcher-Agent-Class` by itself **does not mean** `Agent-Class`: both share the same callback name, but one is triggered by the executable JAR launcher while the other is triggered by an attach tool after startup. The two attributes can declare two different classes.

`Launcher-Agent-Class` is often useful for applications that self-bundle instrumentation/diagnostic mechanisms and want to initialize an agent before application code without requiring users to manually add `-javaagent`. Because the agent is loaded very early and has instrumentation privileges, developers must control the JAR source and initialization impact.

## 6. Java 17+ Hands-On Lab: One JAR, Four Attributes, Three Activation Modes

This example **compiles and runs on JDK 17+** using three classes in the `demo` package. The first two classes are packaged into one executable JAR; the third class is a standalone attach utility.

Directory structure:

~~~text
agent-lab/
├── MANIFEST.MF
├── src/
│   └── demo/
│       ├── DemoApp.java
│       ├── DemoAgent.java
│       └── AttachAgent.java
└── out/                      directory containing compiled .class files
~~~

### 6.1. Application: `src/demo/DemoApp.java`

~~~java
package demo;

import java.util.Arrays;

public final class DemoApp {
    public static void main(String[] args) throws Exception {
        System.out.println("[main] args=" + Arrays.toString(args));
        if (args.length > 0 && args[0].equals("wait")) {
            System.out.println("[main] pid=" + ProcessHandle.current().pid());
            System.out.println("[main] Press Enter to exit");
            System.in.read();
        }
    }
}
~~~

`DemoApp` only has `main`. When passed `wait`, it prints its PID and reads one character from the console to keep the process alive for the dynamic attach exercise. Without `wait`, it exits immediately.

### 6.2. Agent: `src/demo/DemoAgent.java`

~~~java
package demo;

import java.lang.instrument.Instrumentation;

public final class DemoAgent {
    public static void premain(String agentArgs, Instrumentation inst) {
        System.out.println("[premain] options=" + render(agentArgs));
    }

    public static void agentmain(String agentArgs, Instrumentation inst) {
        System.out.println("[agentmain] options=" + render(agentArgs));
    }

    private static String render(String value) {
        return value == null ? "<null>" : (value.isEmpty() ? "<empty>" : value);
    }
}
~~~

Here the agent only prints the callback name and options to observe the execution path, without performing bytecode transformation. This lets us distinguish **the entrypoint selection mechanism** without needing extra libraries like ASM or Byte Buddy. In a real agent, the `inst` parameter is the `Instrumentation` object used to register transformers or query JVM capabilities.

### 6.3. Attach Utility: `src/demo/AttachAgent.java`

~~~java
package demo;

import com.sun.tools.attach.VirtualMachine;
import java.nio.file.Path;

public final class AttachAgent {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("Usage: AttachAgent <pid> <jar>");
        }

        VirtualMachine target = VirtualMachine.attach(args[0]);
        try {
            target.loadAgent(
                    Path.of(args[1]).toAbsolutePath().toString(),
                    "from-attach");
        } finally {
            target.detach();
        }
    }
}
~~~

The `AttachAgent` class belongs to a **separate control tool**, not required to be packaged inside the application/agent JAR. It uses the JDK's `jdk.attach` module (typically absent from minimal runtime images). This pattern requires the target JVM to allow attaching from the current process, usually under the same OS user. The `finally` block ensures detaching after sending the request.

### 6.4. Manifest: `MANIFEST.MF`

~~~text
Manifest-Version: 1.0
Main-Class: demo.DemoApp
Premain-Class: demo.DemoAgent
Agent-Class: demo.DemoAgent
Launcher-Agent-Class: demo.DemoAgent

~~~

This is **a valid manifest** for a single JAR to serve multiple execution paths. Make sure there is a **trailing blank line ending the main manifest section**. The manifest file uses `Attribute-Name: value` pairs, not `demo/DemoAgent.class`. `jar` will include this manifest when packaging.

### 6.5. Compile and Package

From the `agent-lab` directory (with `src/demo` and `out` created), run:

~~~bash
javac --release 17 -d out src/demo/DemoApp.java src/demo/DemoAgent.java src/demo/AttachAgent.java
jar --create --file demo.jar --manifest MANIFEST.MF -C out demo/DemoApp.class -C out demo/DemoAgent.class
~~~

`javac --release 17` generates bytecode compatible with Java 17. `DemoApp.class` and `DemoAgent.class` are packaged into `demo.jar`, while `AttachAgent.class` remains in the `out` directory to run the attach tool. Maven/Gradle is not needed for this experiment.

### 6.6. Run A — Executable JAR: `Main-Class` + `Launcher-Agent-Class`

~~~bash
java -jar demo.jar alpha
~~~

Stdout:

~~~text
[agentmain] options=<empty>
[main] args=[alpha]
~~~

The JVM invokes **`DemoAgent.agentmain`**, even though the manifest also contains `Premain-Class` and `Agent-Class`. Reason: this path is triggered by **`Launcher-Agent-Class`** of the executable JAR. The line `options=<empty>` proves that the launcher agent **does not receive** the application's `alpha` argument.

### 6.7. Run B — Startup Agent via `-javaagent`: `Premain-Class`

~~~bash
java -javaagent:demo.jar=boot -cp demo.jar demo.DemoApp alpha
~~~

Stdout:

~~~text
[premain] options=boot
[main] args=[alpha]
~~~

Here the JVM reads **`Premain-Class`** from the JAR used with `-javaagent` and invokes `DemoAgent.premain("boot", inst)`. `Main-Class` is not used to locate the app because `demo.DemoApp` is specified directly on the command line. `Launcher-Agent-Class` is also not triggered: the application runs via the **classpath**, not via `java -jar`.

The position of `-javaagent` is among the **JVM options, before the main class name or before `-jar`**. If mistakenly placed after the class name or after the executable JAR name, it typically becomes an **application argument** rather than a JVM option.

### 6.8. Run C — Normal Classpath: No Automatic Agent Activation

~~~bash
java -cp demo.jar demo.DemoApp alpha
~~~

Stdout:

~~~text
[main] args=[alpha]
~~~

The output contains only `main`. Even though the manifest carries all four attributes, without `-javaagent`, `-jar`, or a dynamic attach call, the JVM does not activate any agent automatically.

### 6.9. Run D — Attach to a Running JVM: `Agent-Class`

Open the **first terminal** in the `agent-lab` directory:

~~~bash
java -XX:+EnableDynamicAgentLoading -cp demo.jar demo.DemoApp wait
~~~

The application prints `[main] args=[wait]`, then prints `[main] pid=` with the actual PID and waits for Enter. In this experiment, `-XX:+EnableDynamicAgentLoading` applies to the **target HotSpot JVM**, explicitly allowing dynamic attach. The PID number varies between runs.

Open a **second terminal** in the same directory. Suppose the first terminal printed `pid=12345`, run:

~~~bash
java --add-modules jdk.attach -cp out demo.AttachAgent 12345 demo.jar
~~~

`AttachAgent` converts `demo.jar` to an absolute path and calls `VirtualMachine.loadAgent(..., "from-attach")`. The first terminal will additionally print:

~~~text
[agentmain] options=from-attach
~~~

This is **`Agent-Class`**: the `agentmain` callback runs inside the **active target JVM**. `-XX:+EnableDynamicAgentLoading` is a target JVM option, not `-javaagent`. After the experiment, press Enter in the first terminal to terminate the application.

If the attach tool fails, verify that the PID is still alive, user permissions match, the JDK includes `jdk.attach`, OS/container attach settings allow it, and JVM policies permit it. On JDK 21, omitting the opt-in flag may result in a warning about dynamic agent loading; on other versions or distributions, dynamic loading policies may be stricter. Do not interpret environment error output as a sign that `Agent-Class` invokes `premain`.

## 7. If the Same JAR Declares Multiple Attributes, What Decides?

**The trigger determines the entrypoint**, not the line order in the manifest.

| Launch method | Attribute(s) used in the example | Callback |
|---|---|---|
| `java -jar demo.jar` | `Launcher-Agent-Class` and `Main-Class` | `agentmain("")`, then `main(args)` |
| `java -javaagent:demo.jar=boot -cp demo.jar demo.DemoApp` | `Premain-Class` | `premain("boot")`, then `main(args)` |
| `java -cp demo.jar demo.DemoApp` | None of the four attributes needed | Only `main(args)` |
| `VirtualMachine.loadAgent("demo.jar", "from-attach")` | `Agent-Class` | `agentmain("from-attach")` in the target JVM |

When `-javaagent` points to a JAR that has both `Premain-Class` and `Agent-Class`, the JVM selects **`Premain-Class`**; the `Agent-Class` line does not cause `agentmain` to run on that startup path. When attaching to the same JAR, the JVM selects **`Agent-Class`**. The two attributes can point to **the same class** with both methods like `DemoAgent`, or to two different classes.

You can run `java -javaagent:demo.jar=boot -jar demo.jar alpha` to use both a **startup agent** and a **launcher agent** from the same JAR. In this scenario, do not treat having the same class name in both attributes as a deduplication mechanism: each launch path has its own meaning. If an agent has side effects (logging, spawning threads, registering transformers), its initialization must be designed appropriately when users intentionally trigger multiple mechanisms. The `premain` methods of **multiple `-javaagent` flags** are invoked in option order; do not infer ordering across different hook types from the line positions in the manifest.

**There is no rule** that "the JVM invokes all of `main`, `premain`, and `agentmain` present in a class." The manifest holds class names; the launcher/VM looks up the method based on the **activation path**.

## 8. Packaging, Permissions, and Companion Attributes

The manifest can include additional optional attributes for agent capabilities:

~~~text
Can-Redefine-Classes: true
Can-Retransform-Classes: true
Can-Set-Native-Method-Prefix: true
~~~

Declare only the capabilities actually needed. Declaring `true` indicates a **capability request** but does not guarantee that every class can be redefined/retransformed; the agent must check the corresponding `Instrumentation` support methods and JVM limitations. Any value other than `true` is treated as `false`; the default is `false`. These attributes **do not replace** `Premain-Class`, `Agent-Class`, or `Launcher-Agent-Class`.

When packaging for production:

- Clearly decide whether the application needs a **separate agent JAR** (`-javaagent`) or wants to **embed the agent in an executable JAR** (`Launcher-Agent-Class`). Do not cram all four attributes in if only one execution mode is used.
- Ensure `META-INF/MANIFEST.MF` is the **actual main manifest** of the launched JAR. Class names in the manifest must match the built package/class, and the class must be loadable through the relevant class loader hierarchy.
- For **fat JARs**, **shaded JARs**, or custom launchers (e.g., application frameworks with bootstrap mechanisms), inspect the actual manifest and how the launcher loads classes: nested JARs and custom class loaders can affect entrypoint discovery. Do not assume every executable archive behaves like a simple JAR built by the `jar` tool.
- Consider the **`java.instrument` module**, class access permissions, and the fact that an agent can trigger early class loading, logging, or startup dependency cycles. Side effects in callbacks can occur before the first line of application code.
- Only run agents from trusted sources: an agent can manipulate bytecode and observe the state of the entire process. Do not treat being packaged inside the same JAR as a security boundary.
- For **dynamic attach**, prepare for dynamic loading policy changes across JDK versions. JEP 451 introduced warnings starting in JDK 21; future JDKs may require explicit opt-in. For applications that need an agent from the start, `-javaagent` generally offers a more controllable lifecycle.

## 9. Common Errors and How to Diagnose Them

| Symptom | Common cause | How to verify |
|---|---|---|
| `java -jar` reports missing main manifest attribute | No valid `Main-Class` in the executable JAR | Check the **manifest of the JAR passed after `-jar`** |
| `-javaagent` reports `Premain-Class` not found | Agent JAR only has `Agent-Class` or manifest is malformed | Set `Premain-Class` to the correct class containing `premain` |
| `premain` prints nothing while the application still runs | Running `java -cp`/`java -jar` without `-javaagent` | Check the actual **trigger**, not just the JAR contents |
| `Launcher-Agent-Class` is set but `premain` runs unexpectedly | Confusing `-javaagent` with the executable-JAR launcher; class has both callbacks | Inspect the actual command executed and log the callback name |
| `Launcher-Agent-Class` is declared but startup fails | Missing `agentmain`, wrong class name, or initialization error | Check for a `public static` `agentmain` method and class packaging |
| Attach fails despite having `Agent-Class` | Target JVM/process disallows attach, missing `jdk.attach`, wrong PID/permissions, or agent class cannot be loaded | Distinguish **attach connection errors** from **callback errors** |
| `agentmain` sees an empty string despite app CLI args | Using the `Launcher-Agent-Class` path | This is expected behavior: launcher agent receives `""`; app args go to `main` |
| Transformer does not affect already-loaded classes | Agent attached after classes were already defined | Distinguish load-time transformation from retransform/redefine, and check JVM capabilities |
| Agent is triggered twice | Combining `-javaagent` with launcher-agent or an extra attach | Design idempotent initialization as needed; document the deployment mechanism clearly |

When investigating, read in this order: **actual `java` command** → **which exact JAR** → **manifest inside that JAR** → **callback signature** → **logs/exceptions when the JVM invokes the callback**. Do not rename `premain` to `agentmain` merely because you see `Launcher-Agent-Class` in the name; the behavior depends on the manifest field used by the launcher.

## 10. Self-Check

1. `agent.jar` only has `Premain-Class` and no `Main-Class`. Can it be run with `-javaagent`? **Yes**, if the class has a valid `premain`; an agent JAR does not need to be an executable application JAR.
2. `app.jar` has `Main-Class` and `Launcher-Agent-Class`. Where does `java -jar app.jar hello` pass `hello`? **Into `main(String[])`**; the `agentmain` callback via the launcher receives the empty string `""`.
3. `agent.jar` has both `Premain-Class` and `Agent-Class`. Which method does `java -javaagent:agent.jar=cfg ...` invoke? **`premain`**; it does not automatically invoke `agentmain`.
4. A tool calling `VirtualMachine.loadAgent(...)` on a running JVM will look up which attribute? **`Agent-Class`**, and then invoke `agentmain`.
5. Does merely adding `Agent-Class` to `app.jar`'s manifest make the agent run during `java -jar app.jar`? **No**; you need `Launcher-Agent-Class` for the executable JAR path or an actual attach operation.
6. Why is `Launcher-Agent-Class` not synonymous with dynamic attach? Because it **starts before the application's `main` in the executable JAR path**, whereas `Agent-Class` is the target of a request to **load an agent into a running JVM**, even though both invoke `agentmain`.
7. If a startup agent throws an uncaught exception, does the application's `main` continue running according to the specification? **No** for `Premain-Class` and `Launcher-Agent-Class`; dynamic attach errors do not share the same target-JVM abort rule.

### References

- [Oracle Java SE 21 — `java.lang.instrument` package specification](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): agent lifecycle, callbacks, and manifest attributes.
- [Oracle Java SE 21 — JAR File Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html): `Main-Class`, `Launcher-Agent-Class`, and manifest format.
- [Oracle Java SE 21 — `java` launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `-jar`, `-cp`, and JVM option usage.
- [Oracle Java SE 21 — `Instrumentation` interface](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): instrumentation capabilities inside callbacks.
- [OpenJDK JEP 451 — Prepare to Disallow the Dynamic Loading of Agents](https://openjdk.org/jeps/451): dynamic attach policy and warnings.

**Takeaway:** `Main-Class` is for the **application**; `Premain-Class` is for an **agent via `-javaagent`**; `Agent-Class` is for an **agent via attach to a running JVM**; `Launcher-Agent-Class` is for an **agent packaged inside an executable JAR and invokes `agentmain` before `main`**.