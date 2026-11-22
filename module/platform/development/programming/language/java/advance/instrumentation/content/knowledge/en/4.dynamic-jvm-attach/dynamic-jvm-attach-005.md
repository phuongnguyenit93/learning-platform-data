# `Agent-Class`, the Two `agentmain` Signatures, and Passing `agentArgs` When Attaching to a JVM

A Java agent does not necessarily have to be loaded at application startup with `-javaagent`. On JVMs that support the **dynamic attach** mechanism, a tool process can connect to a **running** JVM, request it to load an agent JAR, and pass an options string. The target JVM then reads `Agent-Class` in the JAR's manifest, loads the agent class, and invokes the **`agentmain`** method.

Three important questions need to be separated:

1. **Which agent class is loaded?** — `Agent-Class` in `META-INF/MANIFEST.MF`.
2. **Which method is invoked?** — The JVM prioritizes `public static void agentmain(String, Instrumentation)`, and only falls back to `public static void agentmain(String)` if the two-argument form is not present.
3. **Where do the options go?** — `VirtualMachine.loadAgent(jarPath, options)` passes `options` as **a single `String`** to `agentArgs`; the JVM does not automatically parse `key=value` pairs.

This lesson belongs to the **Attaching to a JVM** group. The focus is the contract between the attach tool, the agent JAR, and `agentmain`; it does not yet go deep into bytecode rewriting algorithms.

## 1. Flow from the Tool Process to the Running JVM

```text
Process A: running Java application (target JVM)
   demo.TargetApp.main(...)
             ^
             | attach / load agent
             |
Process B: control tool (attacher JVM)
   VirtualMachine.attach(targetPid)
             |
   vm.loadAgent("/abs/path/agent.jar", "mode=trace,tag=alpha")
             |
             v
Target JVM reads agent JAR
   META-INF/MANIFEST.MF
      Agent-Class: demo.AgentBoth
             |
             v
Load demo.AgentBoth into target JVM
             |
             +-- Has public static void agentmain(String, Instrumentation)?
             |      Yes -> invoke two-argument signature
             |
             +-- Otherwise -> look for public static void agentmain(String)
             |
             v
agentmain initializes, optionally uses Instrumentation, then returns
             |
             v
loadAgent(...) completes; target application is still running
```

It is necessary to distinguish **two JVMs**: the JVM running the attach tool calls `VirtualMachine.attach/loadAgent`, while `agentmain` runs **inside the target JVM**, not in the attacher process. Therefore, `System.out` logs from `agentmain` normally appear in the target application's output; logs from the attacher program appear in the tool's terminal.

**Attaching does not mean bytecode has already been modified.** An agent may simply print logs, take measurements, register a transformer, or perform an administrative operation. The fact that the JVM can invoke `agentmain` only proves the entry point works; transforming a class requires adding appropriate instrumentation logic.

## 2. `Agent-Class` in the Manifest: Class Name, Not File Name

A JAR can be used as a dynamic agent when the manifest at `META-INF/MANIFEST.MF` declares the **main attribute**:

```text
Manifest-Version: 1.0
Agent-Class: demo.AgentBoth

```

Meaning:

- `Agent-Class` is the **exact key name**. Do not substitute `Main-Class` or `Premain-Class` when intending to activate the agent via `VirtualMachine.loadAgent(...)`.
- `demo.AgentBoth` is the **binary name** of the Java class, using dots to separate packages, without `.java` or `.class`.
- The class `demo.AgentBoth` must be loadable by the target JVM. In the example, we place the file `demo/AgentBoth.class` directly inside the agent JAR.
- The header must be in the **main section** of the manifest, before any individual `Name:` entry sections; a similar line of text appearing elsewhere does not guarantee the agent contract.
- The trailing blank line in the example terminates the main section; `jar --create --manifest` can be used to create the archive and inspect the actual manifest.

The following strings are not valid `Agent-Class` values for the class `demo.AgentBoth`:

```text
Agent-Class: demo/AgentBoth.class
Agent-Class: src/demo/AgentBoth.java
Agent-Class: demo.AgentBoth.class
```

The `.class` file path in the JAR and the class name in the manifest serve two different purposes:

```text
JAR entry:       demo/AgentBoth.class
Manifest value:  demo.AgentBoth
```

A JAR that merely has `Agent-Class` **does not activate automatically** when placed on the application's classpath. There must be a mechanism instructing the target JVM to load the agent, such as the Attach API's `VirtualMachine.loadAgent`. Whether attaching is actually possible also depends on the runtime and protection configuration of the target JVM.

## 3. The Two Valid `agentmain` Signatures and Priority Order

### 3.1. Full Form, Prioritized by the JVM

```java
public static void agentmain(String agentArgs, Instrumentation inst)
```

Required import:

```java
import java.lang.instrument.Instrumentation;
```

Contract explanation:

| Component | Role |
|---|---|
| `public` | Entry point callable by the JVM under the contract |
| `static` | No need to instantiate an agent object |
| `void` | No return value |
| `agentmain` | Exact method name, case-sensitive |
| `String agentArgs` | Receives the options string for this agent load |
| `Instrumentation inst` | Instrumentation API provided by the target JVM |

Illustrative snippet (**not yet a standalone Java file**):

```java
public static void agentmain(String agentArgs, Instrumentation inst) {
    System.out.println("args=" + agentArgs);
    System.out.println("has instrumentation=" + (inst != null));
}
```

This form is suitable when the agent needs to use `inst.addTransformer(...)`, `inst.getAllLoadedClasses()`, `inst.isRetransformClassesSupported()`, or other APIs. Having an `Instrumentation` reference **does not guarantee** all capabilities are supported: capability methods and per-operation restrictions must be checked.

### 3.2. Short Form, Valid Fallback

```java
public static void agentmain(String agentArgs)
```

This is also a specification-recognized signature. The JVM uses it **only when the agent class does not provide a matching two-argument signature**. It receives options but does not directly receive an `Instrumentation` object via a parameter.

Illustrative method example:

```java
public static void agentmain(String agentArgs) {
    System.out.println("agent options=" + agentArgs);
}
```

The one-argument form suits agents that only need a single initialization action or simple configuration handling. If you need to register a transformer directly, declare the two-argument form.

### 3.3. When Both Overloads Exist Together

Suppose a class has:

```java
public static void agentmain(String agentArgs) {
    System.out.println("one-arg");
}

public static void agentmain(String agentArgs, Instrumentation inst) {
    System.out.println("two-arg");
}
```

When loaded via the Attach API, the JVM invokes the **two-argument form**; it does not run both methods and does not depend on declaration order in the Java file.

| Method in agent | Valid entry point? | Notes |
|---|---|---|
| `public static void agentmain(String, Instrumentation)` | Yes | Prioritized |
| `public static void agentmain(String)` | Yes | Fallback if the above form is missing |
| Both | Yes | Only the two-argument form is invoked |
| `private static void agentmain(String)` | No | Missing `public` |
| `public void agentmain(String)` | No | Missing `static` |
| `public static int agentmain(String)` | No | Wrong return type |
| `public static void agentmain(Instrumentation, String)` | No | Wrong parameter order and types |
| `public static void agentmain(String[] args)` | No | `String[]` is not `String` |
| `public static void agentMain(String)` | No | Wrong casing |

If no valid signature exists, the dynamic agent **fails to initialize**. However, a dynamic agent load failure does not have the same consequence as a `premain` failure at startup: the `java.lang.instrument` specification does not require the target JVM to abort the entire application on an `agentmain` error; the tool calling `loadAgent` may receive an exception and must handle it.

## 4. How Is `agentArgs` Passed?

There is no built-in Java command that calls `agentmain` directly. Instead, a tool uses the Attach API in the `jdk.attach` module:

```java
VirtualMachine vm = VirtualMachine.attach(targetPid);
try {
    vm.loadAgent(absoluteJarPath, "mode=trace,tag=alpha");
} finally {
    vm.detach();
}
```

This is an **illustrative code snippet**; the complete example in section 5 has imports, class names, and full argument handling.

`loadAgent(String agent, String options)` delivers `options` verbatim to the target JVM, which the agent then receives via the `agentArgs` parameter of `agentmain`. Examples:

| Attacher side | Value received by agent |
|---|---|
| `loadAgent(path, "verbose")` | `verbose` |
| `loadAgent(path, "mode=trace,tag=alpha")` | `mode=trace,tag=alpha` |
| `loadAgent(path, "a=b=c")` | `a=b=c` |
| `loadAgent(path, "")` | Empty string |
| `loadAgent(path)` | Equivalent to `loadAgent(path, null)` at the API level; the agent must tolerate the absence of options |

There is no JVM step that splits `mode`, `tag`, commas, or `=` signs into multiple parameters. **The options syntax convention is defined by the agent author.** If `split(",")`, `split("=", 2)`, or a parser library is used, that is logic added by the agent itself. Option data also needs null/empty checks and value validation.

Here, `agentArgs` is **not**:

- `String[] args` of `main` in the target application;
- the PID of the target process;
- the path to the agent JAR;
- a map pre-parsed by the JVM;
- the initial JVM command-line arguments.

**Two separate pieces of information when calling `loadAgent`:**

```text
vm.loadAgent("/abs/path/agent.jar", "mode=trace,tag=alpha")
               |                        |
               |                        +--> agentmain(String agentArgs, ...)
               +--> JAR + manifest Agent-Class --> agent class
```

`agent`/`jarPath` must be a path to a **JAR accessible from the target JVM's filesystem**, because the path is forwarded to the target JVM to open. For a target application on the same machine, passing an absolute path usually avoids working-directory mismatches. If the tool and target do not share a filesystem, the same path string on the attacher does not guarantee the JAR exists on the target side.

## 5. Java 17+ Example: Real Cross-Process Attach, Testing Both Signatures and `agentArgs`

We will create a target program that keeps the JVM alive, two agent JARs, and an attach tool. The goal of the example is to **demonstrate the `Agent-Class` contract, the selected signature, and the options string passed intact**; the agents only log output and do not modify bytecode.

Environment requirements: JDK 17+ with the `jdk.attach` module, `javac`, `jar`, `java`, `jps` tools, a target JVM that allows attach, and two processes run by the same OS user account. The illustrative commands use the Attach API mechanism available on HotSpot/OpenJDK; other JVMs or container environments may require additional setup.

Expected directory structure:

```text
attach-agent-demo/
├── src/
│   └── demo/
│       ├── TargetApp.java
│       ├── AgentBoth.java
│       ├── AgentOne.java
│       └── AttachClient.java
└── manifests/
    ├── both.mf
    └── one.mf
```

### 5.1. Target Application: `src/demo/TargetApp.java`

```java
package demo;

import java.util.concurrent.CountDownLatch;

public final class TargetApp {
    private TargetApp() {
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("[target] started; awaiting dynamic attach");
        new CountDownLatch(1).await();
    }
}
```

`CountDownLatch(1).await()` keeps the process waiting so there is enough time to attach. It **does not** itself enable attach or instrumentation capabilities. After finishing the test, stop the target process with `Ctrl+C` in the terminal where it was started.

### 5.2. Agent with **Both Signatures**: `src/demo/AgentBoth.java`

```java
package demo;

import java.lang.instrument.Instrumentation;

public final class AgentBoth {
    private AgentBoth() {
    }

    public static void agentmain(String agentArgs) {
        System.out.println("[both] one-argument agentmain");
        System.out.println("[both] options=" + agentArgs);
    }

    public static void agentmain(String agentArgs, Instrumentation inst) {
        System.out.println("[both] two-argument agentmain");
        System.out.println("[both] options=" + agentArgs);
        System.out.println("[both] instrumentation=" + (inst != null));
    }
}
```

The one-argument method is intentionally placed **before** the two-argument method. Order in the source file does not matter; when loaded successfully, only the two-argument method is selected. The `inst != null` check does not depend on whether the JVM supports retransformation, because `Instrumentation` is the entry-point object supplied.

### 5.3. Agent with Only the Fallback Form: `src/demo/AgentOne.java`

```java
package demo;

public final class AgentOne {
    private AgentOne() {
    }

    public static void agentmain(String agentArgs) {
        System.out.println("[one] one-argument agentmain");
        System.out.println("[one] options=" + agentArgs);
    }
}
```

Without a two-argument method, the JVM uses the one-argument method. This is normal and valid behavior.

### 5.4. Attach Tool: `src/demo/AttachClient.java`

```java
package demo;

import java.nio.file.Path;
import com.sun.tools.attach.VirtualMachine;

public final class AttachClient {
    private AttachClient() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            System.err.println(
                    "Usage: AttachClient <pid> <agent.jar> <options>");
            return;
        }

        String pid = args[0];
        String jarPath = Path.of(args[1])
                .toAbsolutePath()
                .normalize()
                .toString();
        String options = args[2];

        VirtualMachine vm = VirtualMachine.attach(pid);
        try {
            // Agent-Class in the manifest selects the class with agentmain.
            // options is passed as a single raw string into agentArgs.
            vm.loadAgent(jarPath, options);
        } finally {
            vm.detach();
        }

        System.out.println("[client] loadAgent returned");
    }
}
```

The responsibilities are clearly separated:

- `VirtualMachine.attach(pid)` connects to the target JVM by PID, if permitted.
- `Path.of(...).toAbsolutePath()` converts the JAR path to an absolute path, helping a target JVM on the same machine open the right file.
- `vm.loadAgent(jarPath, options)` asks the target JVM to load the JAR and invoke `agentmain`.
- `finally { vm.detach(); }` releases the attach connection session even if `loadAgent` throws an exception.
- The message `[client] loadAgent returned` appears only when `loadAgent` finishes normally. It is not the agent's stdout.

`VirtualMachine` belongs to the **`jdk.attach`** module on the JDK, not the `java.lang.instrument` package. Meanwhile, `Instrumentation` belongs to the `java.instrument` module. `AttachClient` only needs the Attach API; the agent itself receives `Instrumentation` when running **inside the target JVM**.

### 5.5. Two Manifests Actually Using `Agent-Class`

Create **`manifests/both.mf`** with the content:

```text
Manifest-Version: 1.0
Agent-Class: demo.AgentBoth

```

Create **`manifests/one.mf`**:

```text
Manifest-Version: 1.0
Agent-Class: demo.AgentOne

```

Keep the trailing newline. In both examples, the manifest **does not need** `Premain-Class`, because we are not using `-javaagent`. Nor is it necessary to set `Can-Retransform-Classes: true`: the program only receives the entry point and prints logs, and does not yet request retransformation.

### 5.6. Compile and Build Both JARs

Open a terminal in the `attach-agent-demo` directory. Run with JDK 17+:

```bash
mkdir out

javac --add-modules jdk.attach -encoding UTF-8 -d out src/demo/TargetApp.java src/demo/AgentBoth.java src/demo/AgentOne.java src/demo/AttachClient.java

jar --create --file agent-both.jar --manifest manifests/both.mf -C out demo/AgentBoth.class
jar --create --file agent-one.jar --manifest manifests/one.mf -C out demo/AgentOne.class
```

The commands use explicit file names so they work in Bash, PowerShell, and cmd. The `out` directory here is created once; if it already exists, skip the `mkdir out` step.

Explanation:

1. `--add-modules jdk.attach` allows the compiled program to reference the Attach API module.
2. `-d out` outputs classes by package, such as `out/demo/AttachClient.class`.
3. Each `jar --create --manifest` writes a manifest selecting the corresponding agent class.
4. `-C out demo/AgentBoth.class` ensures the entry in the JAR is `demo/AgentBoth.class`, not `out/demo/AgentBoth.class`.

To verify the JAR files contain the right classes, run:

```bash
jar --list --file agent-both.jar
jar --list --file agent-one.jar
```

Both archives must contain `META-INF/MANIFEST.MF` and the corresponding class. When checking the manifest contents, inspect `META-INF/MANIFEST.MF` from the JAR; **having the `.class` file is not enough**, because the `Agent-Class` header must also be correct.

### 5.7. Terminal 1: Run the Target JVM

In the `attach-agent-demo` directory, run:

```bash
java -XX:+EnableDynamicAgentLoading -cp out demo.TargetApp
```

Initial stdout:

```text
[target] started; awaiting dynamic attach
```

The process continues waiting and does not exit. On HotSpot, `-XX:+EnableDynamicAgentLoading` expresses intent to allow dynamic agent loading; on JDK 21, this option also avoids the dynamic agent loading warning described in JEP 451. It **does not** bypass all OS permission limits or attach mechanisms.

### 5.8. Terminal 2: Get the PID and Attach the Two-Argument Agent

In a second terminal, on the same machine and under the same user account, run:

```bash
jps -l
```

Find the line with the class name:

```text
<target-pid> demo.TargetApp
```

`<target-pid>` here is a **placeholder**, and must be replaced with the actual numeric PID displayed by `jps`. Other process IDs may also appear and are not fixed. Do not copy `<` or `>` literally into the Java command.

Example **command structure**, replacing `ACTUAL_PID` with the discovered PID:

```bash
java --add-modules jdk.attach -cp out demo.AttachClient ACTUAL_PID agent-both.jar "mode=trace,tag=alpha"
```

When attach succeeds, **terminal 1** gains the following stdout:

```text
[both] two-argument agentmain
[both] options=mode=trace,tag=alpha
[both] instrumentation=true
```

**Terminal 2** prints:

```text
[client] loadAgent returned
```

Key observations:

- The target had already run `main` and was waiting before the agent was loaded.
- The JVM read `Agent-Class: demo.AgentBoth` and then looked up the matching `agentmain`.
- Both overloads exist together, yet there is **no** `[both] one-argument agentmain` line.
- `mode=trace,tag=alpha` arrived as **one intact string**.
- The agent's `System.out` appears in the target terminal, because `agentmain` runs inside the target JVM.
- `loadAgent` returns after `agentmain` finishes in this example; if the method throws an error, the client's success message is not printed.

### 5.9. Terminal 2: Attach the One-Argument-Only Agent Next

Keeping the target running in terminal 1, run:

```bash
java --add-modules jdk.attach -cp out demo.AttachClient ACTUAL_PID agent-one.jar "level=basic"
```

**Terminal 1** receives additionally:

```text
[one] one-argument agentmain
[one] options=level=basic
```

**Terminal 2** prints:

```text
[client] loadAgent returned
```

This time `Agent-Class: demo.AgentOne` points to a class without a two-argument method, so the JVM invokes the `agentmain(String)` fallback.

After both attaches, the stdout of **terminal 1** in valid order will be:

```text
[target] started; awaiting dynamic attach
[both] two-argument agentmain
[both] options=mode=trace,tag=alpha
[both] instrumentation=true
[one] one-argument agentmain
[one] options=level=basic
```

This is the expected stdout from the **demo code** on a successful attach run, excluding any JVM diagnostics on stderr. Actual warnings/paths/PIDs may depend on the operating system and JDK version. Press `Ctrl+C` in terminal 1 to end the example.

## 6. Parsing `agentArgs` Yourself: Example Parser with Validation

If the options convention is comma-separated `key=value` pairs, the agent can parse them itself. The code below is **a standalone Java class** illustrating how to parse, not part of the section 5 demo program:

**`OptionsParser.java`**

```java
import java.util.LinkedHashMap;
import java.util.Map;

public final class OptionsParser {
    private OptionsParser() {
    }

    public static Map<String, String> parse(String agentArgs) {
        Map<String, String> options = new LinkedHashMap<>();
        if (agentArgs == null || agentArgs.isBlank()) {
            return options;
        }

        for (String entry : agentArgs.split(",", -1)) {
            String[] pair = entry.split("=", 2);
            if (pair.length != 2 || pair[0].isBlank()) {
                throw new IllegalArgumentException("Invalid option: " + entry);
            }
            if (options.putIfAbsent(pair[0], pair[1]) != null) {
                throw new IllegalArgumentException("Duplicate key: " + pair[0]);
            }
        }
        return options;
    }

    public static void main(String[] args) {
        Map<String, String> result = parse("mode=trace,tag=alpha");
        System.out.println(result.get("mode"));
        System.out.println(result.get("tag"));
    }
}
```

Compile and run:

```bash
javac --release 17 OptionsParser.java
java OptionsParser
```

Exact stdout:

```text
trace
alpha
```

This parser **only illustrates a simple convention**: it supports at most the first `=` sign in each entry (`split("=", 2)`) but **does not** support escaped commas, complex quoted strings, key names with spaces, or URI standards. If configuration contains commas or special characters, choose a clearer format (URL encoding, JSON, a configuration file with appropriate access permissions, etc.). In particular, avoid putting secret tokens/passwords on the command line/process list if they could be observed by other processes.

Inside `agentmain`, you can call `OptionsParser.parse(agentArgs)` after bundling the parser into the agent JAR, but you must decide the policy when an invalid option is encountered: log, return, or throw an error so the attach tool is notified. The JVM does not validate this custom syntax for you.

## 7. Comparison with `Premain-Class` / `premain`

| Aspect | Startup agent | Dynamic attach agent |
|---|---|---|
| Scenario | Before application `main` runs | Target JVM is usually already running `main` |
| Activation mechanism | `-javaagent:agent.jar[=options]` | Attach/load mechanism, e.g., `VirtualMachine.loadAgent(path, options)` |
| Manifest | `Premain-Class` | `Agent-Class` |
| Priority method | `premain(String, Instrumentation)` | `agentmain(String, Instrumentation)` |
| Fallback method | `premain(String)` | `agentmain(String)` |
| `agentArgs` | A single string from the `-javaagent` options part | A single string passed by the tool calling `loadAgent` |
| Initialization failure | Can cause the JVM to abort startup | Target JVM is not required to abort merely because a dynamic agent failed to load; the attach tool must handle errors |
| Prerequisites | JVM supports startup Java agents | JVM has an attach mechanism, appropriate permissions, and allows dynamic loading |

One agent JAR can support **both mechanisms**:

```text
Manifest-Version: 1.0
Premain-Class: demo.BothModesAgent
Agent-Class: demo.BothModesAgent

```

That class must define both `premain(...)` and `agentmain(...)` appropriately. When started with `-javaagent`, the JVM selects `Premain-Class` and `premain`; when loaded into a running JVM, the JVM uses `Agent-Class` and `agentmain`. There is no automatic conversion from one method name to the other.

Also distinguish `Launcher-Agent-Class` in an executable JAR: that mechanism also invokes **`agentmain`** but operates on the launcher-controlled application startup path, and does not mean an external attach process has connected. For this mechanism, `agentArgs` is specified as the empty string. Do not infer from the shared name `agentmain` that all three activation paths are the same.

## 8. Attach Conditions, Warnings, and Runtime Limits

### 8.1. Attach API Is a Capability of the JDK and Target JVM

The example tool uses `com.sun.tools.attach.VirtualMachine` from the `jdk.attach` module. That does not guarantee every JVM allows attaching at all times. Conditions to check:

- Does the JDK/JVM support the Attach API and the `jdk.attach` module?
- Does the PID exist and is it still alive? Did the tool pick the right target process?
- Are the tool and target on the same machine, with the appropriate user account, access permissions, and matching PID/filesystem namespace?
- Does the target JVM configuration disable the attach mechanism (`-XX:+DisableAttachMechanism` on HotSpot) or disallow dynamic agent loading?
- Does the JAR path exist **from the target JVM's perspective**? Are the manifest and agent class correct?
- Are there agent dependencies that the target class loader cannot find?

Some VMs restrict attaching to **their own process**; our example uses two independent processes to avoid conflating self-attach with attaching to another JVM. The attach mechanism is also distinct from class retransform/redefine requirements: successfully loading an agent does not mean it has permission to modify every class.

### 8.2. JDK 21+ and Dynamic Agent Loading Policy

JEP 451 (JDK 21) began issuing a warning when a Java agent is **dynamically loaded** into a running HotSpot JVM in preparation for tightening defaults in future releases. When using a version with this behavior, you may see a message on **stderr** about dynamic agent loading; that is not a line printed by `agentmain` in the example.

On HotSpot, the flag:

```bash
-XX:+EnableDynamicAgentLoading
```

allows/declares consent to dynamic agent loading and can avoid the related warning. Conversely:

```bash
-XX:-EnableDynamicAgentLoading
```

disables dynamic agent loading. This is a policy of the **target JVM**, not something that can be fixed by adding a valid `Agent-Class`. If attaching succeeds but the `loadAgent` step is rejected, check runtime flags/protection mechanisms before suspecting the `agentmain` signature.

Do not assume defaults are identical across all JVM versions. Check the documentation for the specific JDK and JVM being run; the example only requires an environment that legitimately permits attach and has the process owner's consent.

### 8.3. `agentmain` Errors Differ from Startup `premain` Errors

The `java.lang.instrument` package documentation states: if a dynamic agent fails to start, the target JVM **does not automatically abort as in a startup `premain` failure**. An uncaught exception in `agentmain` may be logged by the JVM; on the attach tool side, `VirtualMachine.loadAgent` may throw `AgentInitializationException` or another load error.

Example of client-side error catching needed in an application:

```java
try {
    vm.loadAgent(jarPath, options);
} catch (com.sun.tools.attach.AgentLoadException e) {
    System.err.println("Cannot load agent: " + e.getMessage());
} catch (com.sun.tools.attach.AgentInitializationException e) {
    System.err.println("Agent initialization failed: " + e.getMessage());
}
```

This is an **illustrative snippet inside a program that has `vm`, `jarPath`, and `options` variables**, not a standalone Java file. Real application code also needs to handle `IOException`, ensure `detach()` is called, and distinguish failure to connect to the target from errors inside the agent. Do not interpret a `loadAgent` failure as "the target JVM died" without checking the process status.

## 9. Diagnosing by Responsibility Boundary

| Symptom | Where to check |
|---|---|
| `VirtualMachine.attach(pid)` fails | Wrong/expired PID, OS permissions, attach disabled, PID namespace, user privileges |
| `attach` succeeds but `loadAgent` fails | Dynamic loading blocked, JAR absent on target, missing `Agent-Class`, bad manifest, or missing dependency |
| Agent stdout not visible in the tool's terminal | The agent runs inside the **target JVM**; check the target's stdout/logs |
| JVM reports agent class not found | Is `Agent-Class` a binary name? Does the JAR have the `.class` entry in the right package? |
| JVM reports `agentmain` not found | Check `public static void` and the exact two supported signatures |
| Both methods exist but only one runs | Expected by contract: `agentmain(String, Instrumentation)` is prioritized |
| Options arrive as a single unsplit string | This is standard behavior; the agent must parse it itself |
| Empty/null `agentArgs` causes an error | Handle missing options before calling `.split`, `.trim`, `.equals` |
| Attach succeeds but no application behavior changes | Does the agent only log? Have you registered a transformer/retransform appropriately? |
| JDK 21+ warns about dynamically loaded agent | Check JEP 451, the target's consent flag, and runtime policy |
| Loading the agent multiple times causes state errors | Design initialization with state checks/idempotency; do not assume a single load |

A common mistake when testing is **launching the target application with `-javaagent:agent-both.jar`** when the manifest only has `Agent-Class`. In that case, JVM startup requires `Premain-Class` and `premain`, so that invocation is inappropriate. With the JARs in the example, an attacher process calling `loadAgent` is required.

## 10. Quick Check Questions

**1.** The manifest has `Agent-Class: demo.AgentBoth`. The class has both `agentmain(String)` and `agentmain(String, Instrumentation)`. Which method is selected?

**Answer:** The two-argument form; the JVM does not invoke both.

**2.** `vm.loadAgent("/agents/agent.jar", "mode=trace,tag=alpha")`. How many configuration parameters does the agent receive?

**Answer:** One `agentArgs` parameter of type `String` with the verbatim content `mode=trace,tag=alpha`; it may also receive `Instrumentation` if using the two-argument signature, but that is not a configuration option.

**3.** Why do logs inside `agentmain` appear in the target application's terminal?

**Answer:** Because `agentmain` executes inside the target JVM; `AttachClient` only sends the command to load the agent.

**4.** `Agent-Class` is written correctly, yet the JVM does not allow attaching. Is it definitely a manifest error?

**Answer:** No. Check attach support, OS permissions, PID, target filesystem, and dynamic loading policy.

**5.** Does using `-javaagent` with a JAR that only declares `Agent-Class` trigger `agentmain`?

**Answer:** No. `-javaagent` requires `Premain-Class`/`premain`; `Agent-Class` serves post-startup loading mechanisms.

**6.** Why should an absolute path be passed to `loadAgent`?

**Answer:** Because the target JVM resolves the JAR path on the filesystem it sees; a relative path may point to a different directory than the attacher's.

**7.** After an agent is loaded successfully, is an already-loaded class's bytecode automatically modified?

**Answer:** No. The agent must actively use the appropriate transformation API/mechanism, check JVM capabilities, and provide the transform logic.

## 11. Mechanism Takeaways

- **`Agent-Class` → agent class**: required attribute of a dynamically loaded JAR under supported mechanisms.
- **`agentmain` → entry point**: the two valid signatures are `(String, Instrumentation)` and `(String)`; the JVM **prioritizes the two-argument signature**.
- **`VirtualMachine.loadAgent(jar, options)` → triggers loading**: the attach tool asks the target JVM to read the JAR, invoke `agentmain`, and pass `options` as a single **string**.
- **Target JVM → where the agent executes**: agent logs appear on the target process side; attach permissions and dynamic loading capability are checked separately.
- **Instrumentation → post-attach manipulation capability**: receiving an `Instrumentation` object does not automatically modify bytecode; you must actively register a transformer or request valid operations.

## Official References

- Oracle Java 17 — [`java.lang.instrument`: Starting an Agent After VM Startup](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- Oracle Java 17 — [`VirtualMachine` (Attach API)](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html)
- Oracle Java 17 — [`Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- OpenJDK — [JEP 451: Prepare to Disallow the Dynamic Loading of Agents](https://openjdk.org/jeps/451)
- Oracle Java 21 — [`java.lang.instrument` package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html)
