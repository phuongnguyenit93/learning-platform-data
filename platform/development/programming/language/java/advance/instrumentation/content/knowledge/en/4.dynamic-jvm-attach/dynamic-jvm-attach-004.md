# VirtualMachine.loadAgent and the Agent JAR Path in the Target JVM's Environment

When using the Attach API to attach a Java agent to a **running** JVM process, the most common mistake is usually not the `VirtualMachine.attach(pid)` call itself, but the path passed to `VirtualMachine.loadAgent(...)`.

**Principle:** The first parameter of `loadAgent` is **the path to the JAR file that the target JVM can open on the filesystem it sees**. The attach tool passes that path string to the target JVM for processing; the API does not automatically transfer the JAR from the machine running the attach tool to the target process. Two processes running on the same machine may share the same path space, but with containers, mount namespaces, sandboxes, or different machines/OSes, this cannot be assumed.

This lesson belongs to the **JVM Attach** topic, focusing on the meaning of `VirtualMachine.loadAgent`, the differences between the **attacher** and **target** environments, how to package the JAR, test runs, and path diagnostics.

## 1. The Two Sides of an Attach Operation

In a simple model, there are two Java processes:

- **Attach tool**: the control program, using the `jdk.attach` module and the `com.sun.tools.attach.VirtualMachine` class. The tool takes a PID, establishes an attach connection, instructs the target to load the agent, and then calls `detach`.
- **Target JVM**: the running Java application. It receives the request, opens the JAR according to **its own view of the filesystem**, locates the agent entry point, runs `agentmain` inside the target process, and returns the result to the attach tool.

```text
ATTACH TOOL (JVM A)                          TARGET APP (JVM B)
--------------------                         --------------------
VirtualMachine.attach(pid) ----------------> attach listener/provider
                                               |
vm.loadAgent("/opt/agents/probe.jar",         |
             "mode=demo") ------------------> receives path string + options
                                               |
                                     opens /opt/agents/probe.jar
                                      in TARGET filesystem
                                               |
                                     reads META-INF/MANIFEST.MF
                                     Agent-Class: AgentProbe
                                               |
                                     calls AgentProbe.agentmain(...)
                                               |
vm.loadAgent(...) <-------------------------- returns result after agentmain
                                               |
vm.detach() -------------------------------> closes attach session
                                               |
                                     loaded agent remains in target
```

In the diagram, `/opt/agents/probe.jar` is just an example path. It **must be valid for the target process**. Running the attach command on a different host from where the JAR is mounted in the target leads to two different path contexts.

### Three Things That Are Not Synonymous

1. A successful `VirtualMachine.attach(pid)` proves that the tool connected to an eligible target; it **does not prove** that the target can open the agent JAR.
2. A successful `vm.loadAgent(path, options)` means the agent load request completed per the API contract, typically after `agentmain` returns; it **does not prove** that the agent has instrumented every class or produced the desired business-logic change.
3. `vm.detach()` only disconnects the attach tool; it **does not unload** a newly loaded Java agent and does not revert the bytecode that the agent transformed.

This is why you need to verify **PID/attach**, **JAR path**, and **manifest and `agentmain`** separately before checking instrumentation effectiveness.

## 2. The Contract of `VirtualMachine.loadAgent`

The API in the `jdk.attach` module declares:

```java
public abstract void loadAgent(String agent, String options)
        throws AgentLoadException, AgentInitializationException, IOException;

public void loadAgent(String agent)
        throws AgentLoadException, AgentInitializationException, IOException;
```

The two overloads differ in that the single-parameter overload is equivalent to `loadAgent(agent, null)`.

- `agent`: the pathname of the JAR file **in the target VM's filesystem**; the target interprets the path string.
- `options`: an arbitrary **single string** passed verbatim to the `agentArgs` parameter of `agentmain`; it can be `null`. The Java Attach API does not split that string into a command-line array by default and does not turn it into a path.
- `loadAgent`: used for a **Java agent JAR**. Do not confuse it with `loadAgentPath` or `loadAgentLibrary`, which are APIs for loading a **native JVMTI agent library**, such as a `.so`/`.dll` file.
- `AgentLoadException`: the agent could not be found or could not be started via the prescribed mechanism (for example, issues with the JAR file, manifest, or agent class).
- `AgentInitializationException`: an error during initialization/execution of `agentmain` reported over the attach protocol.
- `IOException`: an I/O/communication error; in addition, `attach(pid)` can throw `AttachNotSupportedException` before reaching the JAR loading step.

The Javadoc states the key point precisely: the JAR path string is **passed to the target VM for the target to interpret**. This is the fundamental difference between "the tool can call `Files.exists(...)` on a path" and "the target can actually open that path."

### `Agent-Class` and `agentmain`

A JAR to be loaded **after the JVM has started** must have a main manifest declaring:

```text
Manifest-Version: 1.0
Agent-Class: AgentProbe

```

And the corresponding class must have one of the following `public static` methods:

```java
public static void agentmain(String agentArgs, Instrumentation inst);
public static void agentmain(String agentArgs);
```

The JVM prioritizes the version with `Instrumentation` if the class provides it. This is a **dynamic Java agent**, not a startup agent using `Premain-Class` and `premain` with the `-javaagent` option. A JAR can declare both `Agent-Class` and `Premain-Class` if it supports both modes; specifically, `loadAgent` requires the entry point for dynamic attach.

## 3. Paths as Seen from the Target Side: Environment Examples

| Environment | Actual JAR File Location | Value Passed to `loadAgent` | What to Check |
|---|---|---|---|
| Tool and target on the same Linux host, same filesystem view | `/home/dev/agents/probe.jar` | `/home/dev/agents/probe.jar` | File exists and target has read permission |
| Tool and target on the same Windows host | `C:\lab\agents\probe.jar` | `C:\lab\agents\probe.jar` | Drive/directory is accessible by the target |
| Tool on host, target in container; host volume `/srv/agents` mounted to container `/opt/agents` | Host: `/srv/agents/probe.jar`; container: `/opt/agents/probe.jar` | `/opt/agents/probe.jar` | Target sees the file at the path **inside the container**; attach connection must also be feasible |
| Tool and target in two different containers | Tool: `/work/probe.jar`; target: `/app/agents/probe.jar` after separate mount/copy | `/app/agents/probe.jar` | Mount/PID namespace/permissions are not necessarily the same |
| Tool has the JAR file, target has no corresponding file | `/home/operator/probe.jar` only on tool | No valid path for target | Copy/mount the JAR to a location the target can read before calling |

**Container example:** if the host builds `/srv/agents/probe.jar` and the volume mounted into the target is `/opt/agents`, then the call

```java
vm.loadAgent("/srv/agents/probe.jar", "mode=demo");
```

may fail because `/srv/agents` only exists on the host. The appropriate path for the **target** would be:

```java
vm.loadAgent("/opt/agents/probe.jar", "mode=demo");
```

However, this **only solves finding the JAR**. Attaching to a JVM inside a container is also governed by PID namespaces, OS permissions, the attach provider mechanism, and JVM configuration; having the JAR inside the container does not guarantee that attaching will succeed.

### Why Are Absolute Paths Safer Than Relative Paths?

The Javadoc specifies that the target interprets the path; therefore, `"probe.jar"` must not be assumed to mean "the JAR located in the same directory where the tool is running." A relative path may be resolved based on the working context of the target/JVM deployment. If the tool is run in `/home/dev` while the target was started in `/opt/service`, the two `"probe.jar"` strings very likely refer to two different files or a nonexistent one.

For production applications, **place the JAR at an absolute path that exists in the target's filesystem view** and use that exact path. Be careful with symlinks, read permissions, Windows drives, container mounts, and modifying the file while it is being loaded.

**Avoid doing this:**

```java
// Only verifies the path on the ATTACH TOOL machine:
String path = java.nio.file.Path.of("probe.jar")
        .toAbsolutePath().toString();
vm.loadAgent(path);
```

The snippet above only works when the computed absolute path is **also** the path the target sees. If the tool runs on the host while the target runs in a container, the tool's `toAbsolutePath()` does not resolve mount-path mapping. You must construct/obtain the **target-visible** path from the deployment configuration.

### What Environment Information Can You Query from the Target?

After attaching, the `vm.getSystemProperties()` API reads a number of system properties **from the target**. For example:

```java
var properties = vm.getSystemProperties();
System.out.println(properties.getProperty("user.dir"));
System.out.println(properties.getProperty("java.home"));
System.out.println(properties.getProperty("os.name"));
```

`user.dir` usually indicates the working directory used by the JVM for resolving relative paths, but it **does not** prove that the JAR exists or is readable at the intended path. `java.home` and `os.name` help avoid constructing Linux paths for a Windows target or mistaking the runtime location; they are only **clues**, not a complete answer about mount namespaces.

## 4. Runnable Java 17+ Hands-On: Two JVMs and One Agent JAR

This hands-on exercise uses **one machine** and **two terminal windows** to clearly see which code runs in the tool and which code runs in the target. No third-party libraries are required. Use JDK 17 or JDK 21 with the `jdk.attach` module; the example commands below target HotSpot JDK 21.

Create **four files in the same directory**: `TargetApp.java`, `AgentProbe.java`, `AttachTool.java`, and `agent.mf`.

### 4.1. `TargetApp.java` — the running target process

```java
public final class TargetApp {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("TARGET_PID=" + ProcessHandle.current().pid());
        System.out.println("TARGET_READY");
        while (true) {
            Thread.sleep(60_000);
        }
    }
}
```

The application simply prints its PID, reports readiness, and keeps the JVM alive for another tool to attach. The PID changes on each run. This is the target into which the agent will be loaded.

### 4.2. `AgentProbe.java` — code called by the target JVM

```java
import java.lang.instrument.Instrumentation;

public final class AgentProbe {
    public static void agentmain(
            String options, Instrumentation instrumentation) {
        System.out.println("AGENTMAIN_RUNNING");
        System.out.println("AGENT_OPTIONS=" + options);
        System.out.println(
                "AGENT_TARGET_USER_DIR=" + System.getProperty("user.dir"));
    }
}
```

This is a **Java agent** with an `agentmain` entry point. It does not register a `ClassFileTransformer` or modify any classes yet; its purpose is to confirm that the agent **is executed inside the target**. The `AGENT_TARGET_USER_DIR` line must be understood as the system property of the **target**, not the working directory of the attach tool.

### 4.3. `AttachTool.java` — tool calling `VirtualMachine.loadAgent`

```java
import com.sun.tools.attach.VirtualMachine;

public final class AttachTool {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println(
                    "Usage: AttachTool <target-pid> <target-visible-agent-jar>");
            System.exit(2);
        }

        String targetPid = args[0];
        String jarPathInsideTarget = args[1];

        VirtualMachine vm = VirtualMachine.attach(targetPid);
        try {
            String targetDir =
                    vm.getSystemProperties().getProperty("user.dir");
            System.out.println("TARGET_USER_DIR=" + targetDir);

            vm.loadAgent(jarPathInsideTarget, "mode=demo");
            System.out.println("LOAD_AGENT_OK");
        } finally {
            vm.detach();
        }
    }
}
```

Notes:

- `targetPid` must be the identifier that the attach provider recognizes as the target process.
- `jarPathInsideTarget` is passed **verbatim** to the target; the code does not replace it with `Path.of(...).toAbsolutePath()` on the tool side.
- `"mode=demo"` is an **options string**, passed to `agentmain(String options, ...)`; it does **not** specify where the JAR is located.
- `finally` ensures `detach` is called once attach succeeds, even if `loadAgent` throws an exception. `detach` is not `unloadAgent`.

### 4.4. `agent.mf` — manifest of the agent JAR

Create a text file with the exact content below, **ending with a blank line**:

```text
Manifest-Version: 1.0
Agent-Class: AgentProbe

```

`Agent-Class` is the **fully qualified binary name of the Java class**. Since the example does not use a package, `AgentProbe` is sufficient. If the class is in the `com.example.agent` package, the value must be `com.example.agent.AgentProbe`, and the class entry inside the JAR must match that package structure. Do not use the source file path `AgentProbe.java` instead of the class name.

### 4.5. Compiling and Packaging

Run in the directory containing the four files:

```shell
javac --add-modules jdk.attach TargetApp.java AgentProbe.java AttachTool.java
jar cfm agent-probe.jar agent.mf AgentProbe.class
jar tf agent-probe.jar
```

In the listing from `jar tf`, check that `META-INF/MANIFEST.MF` and `AgentProbe.class` are present. If you want to inspect the manifest, use a JAR/ZIP reading tool; merely listing entry names does not prove the `Agent-Class` content is correct.

`--add-modules jdk.attach` allows the tool to compile and access `com.sun.tools.attach.VirtualMachine`. The `jdk.attach` module is an API belonging to the **JDK**; if you use a minimal runtime image without this module on the tool side, compiling/running the tool will fail. The target does not need `VirtualMachine`, so it does not need to import that module into `TargetApp`.

### 4.6. Terminal 1 — starting the target

In the same directory:

```shell
java -XX:+EnableDynamicAgentLoading -cp . TargetApp
```

The application prints two structured lines:

```text
TARGET_PID=<actual PID>
TARGET_READY
```

`<actual PID>` is a placeholder to be replaced with the number your machine prints, not fixed stdout. Do not type the literal `< >` angle brackets into the attach command.

On HotSpot JDK 21, `-XX:+EnableDynamicAgentLoading` expresses opt-in permission for dynamic agent loading and avoids the corresponding warning. Depending on the JVM version and policy, dynamic loading behavior may vary; pass the flag when starting the **target JVM**, rather than only adding it to the terminal running `AttachTool`.

Keep Terminal 1 open.

### 4.7. Terminal 2 — attaching and loading the JAR

On the **same host and in a context that can see the JAR file**, run using the **actual PID** from Terminal 1 and the **target's absolute path**:

Linux/macOS example, assuming the user created the JAR at `/home/dev/demo/agent-probe.jar`:

```shell
java --add-modules jdk.attach -cp . AttachTool 12345 /home/dev/demo/agent-probe.jar
```

Windows example, assuming the file is at `C:\lab\attach\agent-probe.jar`:

```powershell
java --add-modules jdk.attach -cp . AttachTool 12345 "C:\lab\attach\agent-probe.jar"
```

**Illustrative only:** replace `12345` with the PID printed in Terminal 1 and replace the path with where the JAR actually exists and can be read by the target. In the two-JVM same-host experiment, the absolute paths usually match. In a container, you must use the **path from the target's container perspective**.

Observe:

- Terminal 2 prints a line starting with `TARGET_USER_DIR=` (value depends on the environment), then **`LOAD_AGENT_OK`** if loading succeeded.
- Terminal 1, where the target's stdout is displayed, additionally prints:

```text
AGENTMAIN_RUNNING
AGENT_OPTIONS=mode=demo
AGENT_TARGET_USER_DIR=<target JVM working directory>
```

The lines `AGENTMAIN_RUNNING` and `AGENT_OPTIONS=mode=demo` are fixed values from the example code; the `AGENT_TARGET_USER_DIR=...` line carries the actual environment value. On a system that writes the target's stdout to a service log or container log, the agent's messages will appear in the target's log rather than in the attach terminal.

After the experiment, stop the target with `Ctrl+C` in Terminal 1. If you try `loadAgent` again on the same target, decide for yourself whether you accept the agent's `agentmain` being invoked another time; the API has no implicit mechanism guaranteeing each agent runs only once.

## 5. Host, Docker, and Kubernetes Cases: Three Mapping Layers Must Be Right

In containers, **three different names for the same thing** often appear:

1. **File on the build/host side:** where the build tool produces the JAR, e.g., `/workspace/build/agent-probe.jar`.
2. **File inside the target container:** the result of a copy/mount/image layer, e.g., `/opt/agents/agent-probe.jar`.
3. **Process identifier:** the PID seen from the host and the PID seen from a container namespace may differ.

```text
HOST                                  CONTAINER TARGET
/workspace/build/agent-probe.jar
              |
              | copy/mount
              v
                               /opt/agents/agent-probe.jar
                                             |
                                      TARGET JVM opens
                                      /opt/agents/agent-probe.jar

host PID (example: 30102)             container PID (example: 1)
              \                          /
               \---- attach provider ----/
                  must use matching ID/namespace
```

Do not pick `/workspace/build/agent-probe.jar` just because `Files.exists(...)` on the host returns `true`. Likewise, do not assume that `VirtualMachine.attach("1")` from the host will always find PID 1 inside the container: the ID is interpreted according to the attach provider and process context.

### Container Operations Checklist

- Ensure the JAR has been **copied or mounted** into the target before calling `loadAgent`. Verify existence from **inside the target's filesystem view**, not only on the host.
- Confirm that the user running the target has permission to **read the file and traverse parent directories**; symlinks must point to a location the target actually sees.
- If convenient, run the attach tool in the **same container/PID namespace** as the target using a system-approved method. If the tool is on the host or in a sidecar, verify the attach provider, user/UID, mount/PID namespaces, and security policies; the JAR path must still be the target's path.
- If the image only has a JRE/trimmed runtime, the tool needs a JDK/the `jdk.attach` module in the environment **running the tool**. The target might lack `jcmd`/`jar` tools, yet the target JVM must still support the attach/dynamic-agent mechanism per its implementation.
- The target's `user.dir` is a hint for debugging relative paths; it is not proof that the JAR file is located there. Use an absolute path with a verified mount path.
- When coordinating between a Windows host and a Linux container, a Windows path `C:\...` is **not** automatically translated into a Linux path. Use the Linux path that the target actually sees.

**Architecture note:** The Attach API uses a channel attached to a VM supported by the attach provider, not a "remote load JAR over the Internet" service. There is no automatic file copy step or cross-machine path translation.

## 6. Distinguishing the JAR Path from Other Paths

A `loadAgent` call can involve **two different groups of paths**, which often causes errors to be misdiagnosed:

```java
vm.loadAgent("/opt/agents/agent-probe.jar",
             "config=/etc/myapp/agent.yml");
```

- `/opt/agents/agent-probe.jar` is the **agent JAR path**, passed by the Attach API to the target JVM to open the JAR.
- `config=/etc/myapp/agent.yml` is the **agent options string**; the JVM passes the string verbatim to `agentmain`. If the agent itself parses `config=...` and opens the file, that is **behavior implemented by the agent**, and because agent code runs inside the target, the configuration file must be accessible from the target's environment.
- Java agent dependencies must also be loadable in the appropriate class-loading context. Having the main JAR does not guarantee that dependencies used by `agentmain` are packaged/declared and readable.
- A dynamically loaded JAR is added to the system class path as described by the API, but this should not be treated as a mechanism to arbitrarily modify the classpath of every class loader or grant access to internal modules.
- If the agent returns successfully without instrumenting any classes, inspect the `agentmain`/`Instrumentation` logic itself. `loadAgent` does not automatically call `retransformClasses` and does not automatically apply a transformer to already-loaded classes.

A common mistake: the tool builds `String config = Path.of("agent.yml").toAbsolutePath().toString()` and passes it in `options`, but the agent inside the container cannot see the host's absolute path. The same principle applies: you must know **which side will actually open the file**.

## 7. Why Should You Check the Path from the Target Instead of Inferring from the Attach Tool?

Suppose there are two shells:

```text
TOOL:
  user.dir = /home/operator
  /home/operator/agent.jar = EXISTS

TARGET:
  user.dir = /opt/service
  /home/operator/agent.jar = NOT FOUND
  /opt/agents/agent.jar = EXISTS
```

Given these facts:

```java
vm.loadAgent("/home/operator/agent.jar");
```

has no basis to succeed; the target side cannot see the corresponding file. Conversely:

```java
vm.loadAgent("/opt/agents/agent.jar");
```

is a well-founded choice, **provided** the target JVM supports dynamic agent loading, the file is readable, and the manifest/class are valid.

Checking `vm.getSystemProperties().getProperty("user.dir")` can confirm that the target has a different working directory from the tool, but it does not replace verifying access to the JAR. If you do not yet have a safe channel to inspect the target, use authoritative deployment information (volume mapping, image content, mount path) and diagnose the exception after `loadAgent`; do not guess based on host paths.

## 8. Common Errors and How to Distinguish Root Causes

| Symptom | Where the Error Occurs | Recommended Checks |
|---|---|---|
| `AttachNotSupportedException` at `attach(pid)` | Failed to attach | Wrong/no longer alive PID, unsupported runtime/provider, attach user/namespace/permissions, attach disabled in configuration |
| `IOException` during attach/command send | Connection with target | Target stopped, IPC channel, provider, or access permissions; check cause/message |
| `AgentLoadException`: agent path does not exist | Command sent, but target cannot open JAR | Check file in **target filesystem**, absolute path, mount, read permissions, and path separator for the target OS |
| `AgentLoadException`: invalid manifest/entry point | Target sees JAR, but cannot start agent | `META-INF/MANIFEST.MF` must have the correct `Agent-Class`; JAR contains that class and a valid `public static agentmain` method |
| `AgentInitializationException` | Agent initialization failed | Target stack trace/logs, dependencies, errors inside `agentmain`; do not equate with file not found |
| `LOAD_AGENT_OK` printed, but no agent logs seen | Observing the wrong process | Check **target** stdout/logs, not just tool stdout; verify PID and log destination |
| Agent runs, but application code does not change | Agent behavior | Did `agentmain` register a transformer, request retransform for already-loaded classes when needed, and produce valid bytecode? |
| Host finds JAR, container reports missing | Wrong filesystem view | Compare host build path with target mount path; use the target-visible value in `loadAgent` |
| `agentmain` invoked multiple times | Reloaded on demand | Do not assume the JVM automatically unloads/locks the agent; design idempotent initialization if reload is allowed |
| JDK 21 JVM warns about dynamic agent | JVM policy | Check JEP 451, the **target's** `-XX:+EnableDynamicAgentLoading` option, and deployment policy |
| Dynamic agent loading is disallowed | JVM policy/version | Check `-XX:-EnableDynamicAgentLoading`, JVM version, and configuration; consider `-javaagent` at startup if appropriate |

**Reliable diagnostic order:**

1. Verify the correct **target PID**, that the JVM is alive, and that attach succeeds.
2. Read the exact path string passed to `loadAgent`: this path is for the **target**, not for the tool.
3. Verify that the JAR file exists and is readable in the target's filesystem view, including mount namespaces, symlinks, and OS permissions.
4. Check that the JAR actually has the `Agent-Class` manifest attribute, class entry, `agentmain`, and required dependencies.
5. Verify that the target allows dynamic agent loading; especially on HotSpot JDK 21, which issues warnings per JEP 451 and provides an opt-in option.
6. Distinguish **load completed** from **instrumentation goal achieved** via logs/behavior actively produced by the agent.

### "Wrong Path" Errors Can Be Disguised by Other Errors

You should not conclude that `loadAgent` failed to find the JAR merely because you see the word "agent" in an exception. For instance, if `vm.attach` fails, no load request ever reached the target. If `agentmain` throws an exception due to a missing library, the target did read the main JAR, but agent initialization failed. If `loadAgent` returns successfully but the transformer is not applied, the JAR path may be completely correct.

Conversely, checking `Files.exists(jarPath)` **only in the attach tool** does not rule out a path error for the target.

## 9. Operational Aspects: Capability and Trust Boundary

When a Java agent runs `agentmain`, it can use `Instrumentation` to observe or transform bytecode in the target JVM. Therefore, allowing agent loading is an application/system configuration decision that must be authorized by the JVM owner. Do not use attach as a way to bypass OS permissions, container isolation, or runtime policies.

For **HotSpot JDK 21**:

- Dynamic agent loading is still supported, but JEP 451 issues a warning when loading a Java/JVMTI agent dynamically without opting in.
- `-XX:+EnableDynamicAgentLoading` on the **target** JVM is an explicit opt-in and also suppresses the related warning in JDK 21.
- `-XX:-EnableDynamicAgentLoading` can be used to disable dynamic agent loading. Default policies may change in other JDKs/VMs; rely on the documentation for the exact runtime version.
- A Java agent started with the application via `-javaagent:path/to/agent.jar` uses the `premain` lifecycle, which differs from dynamic `loadAgent`/`agentmain`.

For safe deployment, operators typically pin the agent JAR version/hash, inspect the manifest/dependencies, and control write permissions on the directory storing the JAR, because a modification to the JAR between verification and when the target opens the file can lead to loading unintended content. This is an artifact trust issue, not specific to `loadAgent` syntax.

## 10. Knowledge Check Exercises

**Question 1.** The attach tool runs on the host with `/srv/build/probe.jar`; the target in a container has the same JAR at `/opt/agents/probe.jar`. Which path should be passed?

> `/opt/agents/probe.jar`, because the **target JVM** is the side opening the file. You must also ensure that attaching to the right target is possible.

**Question 2.** Does `vm.loadAgent("./probe.jar")` necessarily look for the file in the tool's working directory?

> No. The target is where the path is interpreted; you should use a target-visible absolute path to avoid context dependence.

**Question 3.** Which JVM does `vm.getSystemProperties().getProperty("user.dir")` reflect?

> The **target** JVM after attaching, not the attacher process.

**Question 4.** A JAR only has `Premain-Class` and `premain`. Is that enough for `loadAgent`?

> No. Dynamic attach requires `Agent-Class` and a valid `public static agentmain` entry point.

**Question 5.** `loadAgent` succeeds and then `detach` is called. Is the agent unloaded?

> No. `detach` closes the attach connection; the agent can remain active in the target.

**Question 6.** `loadAgent` returns, but already-loaded classes have not changed behavior. Can you conclude the file path is wrong?

> No. The path may be completely correct; the agent may not have registered a transformer, may not have requested retransformation, or the instrumentation logic may not apply to that class.

**Question 7.** Does `loadAgent(path, "config=/etc/agent.yml")` automatically read the YAML file?

> No. That is an options string for `agentmain`; only agent code that parses it and opens the file on the target filesystem will read the YAML.

**Question 8.** Why can the same PID shown in a container and on the host refer to different entities?

> PIDs are interpreted within the context of a namespace/attach provider. You must not assume an ID printed in one namespace works unchanged everywhere.

## Official References

- [Java SE 21 — VirtualMachine (jdk.attach)](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html): `loadAgent` contract, target JAR path parameter, `getSystemProperties`, `attach`, `detach`, and exceptions.
- [Java SE 21 — java.lang.instrument](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): `Agent-Class` manifest attribute, `agentmain`, dynamic agent lifecycle, `Premain-Class`, and `premain`.
- [Java SE 21 — module jdk.attach](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.attach/module-summary.html): packages of the Attach API.
- [OpenJDK JEP 451 — Prepare to Disallow the Dynamic Loading of Agents](https://openjdk.org/jeps/451): warnings and policy direction for dynamic agent loading starting in JDK 21.
- [Oracle JDK 21 release notes](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html): notes on `EnableDynamicAgentLoading`.

**Key Takeaway:** `VirtualMachine.loadAgent` only accepts a **path string**; it does not transfer the JAR to the target JVM. Find the right PID, place the JAR in the target's filesystem, pass the **exact absolute path that the target sees**, ensure a valid manifest/`agentmain`, and verify the result directly in the target.