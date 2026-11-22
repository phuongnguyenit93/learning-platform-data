# AttachNotSupportedException, AgentLoadException, and AgentInitializationException When Attaching to the JVM

The Attach API allows a Java program (diagnostic tool, profiler, agent manager) to connect to a **running JVM** and instruct that JVM to load an agent. When it fails, three checked exceptions are easily confused: `AttachNotSupportedException`, `AgentLoadException`, and `AgentInitializationException`. They describe **three different stages** of an operation: establishing the attach connection, loading the agent, and then initializing the agent. Distinguishing the stage accurately helps diagnose the process, JAR file, manifest, `agentmain` method, and operational conditions properly.

This is a lesson in the **Attach to JVM** topic of Java Advance – instrumentation. The focus is on the meaning, where each occurs, and how to catch and handle each exception; along with `IOException` and JVM constraints at the necessary level to avoid false conclusions. The examples use Java 17+ and a dynamically loaded Java agent JAR, requiring no framework.

**After this lesson, you will be able to:**

- Read the `VirtualMachine.attach(pid) → loadAgent(jar, options) → agentmain(...) → detach()` flow and isolate errors by the **failing call**.
- Write code to `catch` the three exceptions separately, while properly handling `IOException` and cleanup.
- Explain why **a successful attach does not prove the agent loaded or initialized successfully**.
- Distinguish `AgentInitializationException.returnValue()` from the error code of a **native JVMTI agent**, avoiding the misconception that it is the exit code of Java `agentmain`.
- Package a demo agent yourself and practice the success case, failed attach, unloadable JAR, and `agentmain` throwing an error.

## 1. The Three Failure Boundaries Model

A tool using the Attach API typically works as follows:

~~~text
PROCESS A: Java tool                     PROCESS B: Running application JVM
-------------------------                ----------------------------------
read target PID
   |
   v
VirtualMachine.attach(pid) -------> AttachProvider/transport to target JVM
   |                                         |
   | success                                 |
   v                                         v
VirtualMachine handle                     attach channel ready
   |
   v
vm.loadAgent(agentJar, options) ---> target JVM locates/reads agent JAR
                                             |
                                             v
                                      find Agent-Class in manifest
                                             |
                                             v
                                      load class and invoke agentmain(...)
                                             |
                                             v
                                return result to attach tool
   |
   v
vm.detach()  --------------------> close tool's link to the JVM
~~~

The three exceptions to learn correspond to three positions:

| Exception | Related Java Call | Primary Signal | Hypotheses to Check First |
| --- | --- | --- | --- |
| `AttachNotSupportedException` | `VirtualMachine.attach(pid)` | Failed to establish an attach connection through a suitable provider | Incorrect PID/identifier, target JVM does not exist, or attach provider is not supported |
| `AgentLoadException` | `vm.loadAgent(agentJar, options)` | `VirtualMachine` object obtained, but the agent could not be loaded/started per the agent contract | JAR inaccessible, manifest missing `Agent-Class`, invalid agent class or JAR structure, dynamic loading disallowed |
| `AgentInitializationException` | `vm.loadAgent(agentJar, options)` | Agent failed to initialize after the JVM processed the load request | `agentmain` threw an exception, invalid agent configuration, initialization error inside the agent |

**Not every error at the same stage always belongs to one of the three classes above.** `IOException` can occur when `attach`, `loadAgent`, or `detach` encounters I/O trouble; `SecurityException` can be permission-related. These are all points to note separately.

The exception classes reside in the **`jdk.attach` module**, package `com.sun.tools.attach`; all three are **checked exceptions** (extending `Exception`). They are not `java.lang.instrument.IllegalClassFormatException`, not `NoClassDefFoundError`, and they do not by themselves describe business logic errors of the target application.

## 2. API Signatures and Boundary Conditions

The snippet below shows the relevant public signatures on JDK 17:

~~~java
// Module jdk.attach, package com.sun.tools.attach
public static VirtualMachine attach(String id)
        throws AttachNotSupportedException, java.io.IOException;

// instance method
public abstract void loadAgent(String agent, String options)
        throws AgentLoadException, AgentInitializationException,
               java.io.IOException;

// overload equivalent to loadAgent(agent, null)
public void loadAgent(String agent)
        throws AgentLoadException, AgentInitializationException,
               java.io.IOException;

// close connection to the target JVM
public abstract void detach() throws java.io.IOException;
~~~

This is a **signature excerpt to explain the API**, not a standalone Java file to be compiled.

For `attach(String)`, the `id` argument is an implementation-dependent identifier, usually the OS PID string. The target JVM may have exited between listing and attaching; the fact that a PID still exists does not prove it is a JVM of the same kind, that access permissions are granted, or that the attach channel is working.

For `loadAgent(String, String)`:

- `agent` is the **path to the JAR on the target JVM's filesystem**. It is sent to the target JVM for interpretation. In the example of two processes on the same machine, the absolute path built in the tool also points to the same file. When containers/namespaces/filesystems differ, do not assume the tool's path exists on the target JVM.
- `options` is **a single string** passed to `agentmain`; the convention for parsing the string is defined by the agent. `null` may be passed.
- Once the agent JAR is loaded into the target JVM, the class specified by the **`Agent-Class`** manifest attribute must define `public static void agentmain(String agentArgs, Instrumentation inst)` or the single-parameter variant.
- `loadAgent` completes when the `agentmain` call completes; this does **not** prove that all background threads/exporters started by the agent have become healthy.

**Distinguishing startup and dynamic:** `-javaagent:...` at startup uses `Premain-Class` and `premain`. `VirtualMachine.loadAgent(...)` on a running JVM uses `Agent-Class` and `agentmain`. Using the wrong manifest type can cause the load step to fail, even if the Java code in the JAR compiles normally.

## 3. `AttachNotSupportedException` — Failing to Establish an Attach Channel

Per the API, `VirtualMachine.attach(String id)` tries installed `AttachProvider` instances; if all providers report no support or no provider exists, the method throws `AttachNotSupportedException`. Typical scenarios:

- Invalid PID/identifier string, PID has already exited, or the identifier is actually not a compatible JVM.
- The target JVM uses an implementation, platform, or attach mechanism that existing providers cannot communicate with.
- No suitable attach provider is available in the tool's runtime/configuration.
- The attach mechanism is disabled or unavailable on the target JVM; the **specific** exception can still vary by provider, OS, and how the error is propagated.

Example call:

~~~java
VirtualMachine vm = VirtualMachine.attach(pid);
~~~

If this method fails, **there is no valid `vm` handle to call `loadAgent`**. Therefore, this error is not evidence that the agent JAR file is corrupted. Focus on `pid`, the JDK/JVM in use, permissions, namespace, process state, and attach configuration.

**Caution:** permission errors, sockets, temporary files, stuck attach endpoints, timeouts, or terminated processes are sometimes represented by `IOException` or `SecurityException`. Do not write rigid rules like "a wrong PID always produces only `AttachNotSupportedException`". The Javadoc explicitly notes both `IOException` and security-related runtime errors.

### How to Verify Before Modifying the Agent

1. The PID comes from the **target Java process**; on the same host, you can cross-check with OS tools or `jcmd -l` when available.
2. Are the attach tool and target in the same environment where they can communicate? In containers, a PID seen from the host differs from the PID inside the namespace.
3. Is any permission/OS policy preventing the tool process from connecting to the target process?
4. Does the target JVM actually support the Attach API without the attach mechanism disabled? On HotSpot, `-XX:+DisableAttachMechanism` disables the attach mechanism.
5. Try attaching in a controlled test environment before concluding the application/agent is incompatible.

## 4. `AgentLoadException` — Connected, but the Agent Failed to Load Properly

The call leading to the exception:

~~~java
vm.loadAgent(agentJarPath, "mode=demo");
~~~

`AgentLoadException` means the agent does not exist, cannot be loaded, or cannot be started according to the `java.lang.instrument` contract. Common causes:

- Wrong `agentJarPath`, file has not been copied to a location visible to the target JVM, missing read permissions, or corrupted JAR.
- Missing `Agent-Class` attribute in the **main manifest** `META-INF/MANIFEST.MF` of the JAR used for attach; confused with `Premain-Class`.
- Incorrect class name in `Agent-Class`, agent class or required dependencies cannot be loaded, or `agentmain` method has the wrong signature. Error classification details may depend on the JVM/implementation.
- Dynamic agent loading is rejected by the target JVM policy; check the message and JVM flags, and do not assume every `AgentLoadException` means "file not found".

**Only investigate the classpath and JAR structure after confirming `attach` succeeded.** From the tool's perspective, the JAR path existing on the tool machine is not enough: the target JVM is the one that must read the JAR. Inspect the file with `jar --list --file demo-agent.jar`, then read the manifest with a suitable tool to confirm `Agent-Class` points to the exact binary name.

`AgentLoadException` **does not by itself confirm** whether `agentmain` ran partially or not. The error message, target JVM logs, and tool state help determine the internal phase. Especially when an agent has already created side effects before another error, do not automatically retry duplicates without checking the agent's idempotence.

### Distinguishing the Two Commonly Confused Manifests

~~~text
# Startup agent - runs with the java -javaagent:... command
Premain-Class: ExampleAgent

# Dynamic agent - loaded into a running JVM via vm.loadAgent(...)
Agent-Class: ExampleAgent
~~~

These two blocks are **separate illustrations** of the attributes, not complete executable manifests. A JAR can declare both if the author supports both lifecycles, but each activation method requires the right entry point.

## 5. `AgentInitializationException` — The JVM Entered Agent Initialization and Encountered an Error

According to `VirtualMachine.loadAgent` in JDK 17, the method can throw `AgentInitializationException` if `agentmain` throws an exception. For example, `agentmain` needs to parse options, initialize a transformer, create an exporter, or read configuration; any improperly handled initialization error at this step can cause the load call to fail.

Causes to check inside the **target JVM**:

- `agentmain` rejects the `options` value, calls `Integer.parseInt` incorrectly, or lacks required configuration.
- Agent initialization encounters `IllegalStateException`, a null reference, resource permission/path errors, missing dependencies, or instrumentation API errors.
- Transformer/hook is misinitialized, or JVM conditions do not satisfy capabilities the agent wants to use.
- The agent creates resources and then throws an exception; even though the call reports failure, partially initialized resources/hooks may remain.

### What Does `returnValue()` Mean?

`AgentInitializationException` has the method **`int returnValue()`** — the exact name is `returnValue()`, **not `getReturnValue()`**. According to the Javadoc, if the exception was created with a return code from the native `Agent_OnAttach` function, the method provides that code; otherwise, it returns **0**.

- For a **native JVMTI agent** loaded via `loadAgentLibrary` or `loadAgentPath`, this code can help diagnose the error value returned by `Agent_OnAttach`.
- For a **Java agent JAR** loaded via `loadAgent`, you cannot by default interpret `returnValue()` as the "exit code of `agentmain`". `agentmain` is a `void` method and does not return an int status by contract.
- A value of `0` **does not prove initialization succeeded**: the method may return `0` because the exception carries no native return code, even when an `AgentInitializationException` occurred.

Another important point: **a dynamic agent initialization failure does not mean the target JVM automatically exits**. The `java.lang.instrument` specification for agents loaded into an already-running JVM specifies that the JVM does not abort the application just because an agent fails to start; an unhandled exception in `agentmain` may be ignored on the application thread while still being logged, and the `loadAgent` call on the tool side can report the error. Therefore, read **both the attach tool logs and the target JVM logs**; do not guess from one side alone.

An error here also does not guarantee "the agent was rolled back": if the agent started some threads, registered hooks, or mutated state before throwing an exception, those side effects may persist. When retrying, check whether the agent supports repeated loading/idempotence.

## 6. Why `IOException` and `SecurityException` Must Also Be Handled

The three exceptions in the title **are not the entire error contract** of the Attach API. The Javadoc declares:

| Call | Checked Exceptions to Handle | Runtime Errors / Other Notes |
| --- | --- | --- |
| `VirtualMachine.attach(pid)` | `AttachNotSupportedException`, `IOException` | `SecurityException`, `NullPointerException` when id is null |
| `vm.loadAgent(path, opts)` | `AgentLoadException`, `AgentInitializationException`, `IOException` | `NullPointerException` if agent path is null; provider/JVM errors may have other details |
| `vm.detach()` | `IOException` | Not an agent-unloading call |

Some example scenarios:

- The target JVM exits after attach but before load: can surface as `IOException` on the `loadAgent` operation.
- Attach channel read/write operations fail due to the environment: `IOException` can be thrown at one of the steps.
- Runtime policy/security blocks attach: `SecurityException` or an error surfaced by the provider in its own mechanism.
- `detach` fails: that is an **attach channel cleanup error**, not sufficient grounds to claim `agentmain` did not run.

**Distinguish between "agent initialized" and "tool detached successfully".** After `loadAgent` succeeds, `detach` closes the link between the tool and the JVM; it does **not** unload the agent from the JVM, stop agent threads, or revert bytecode transformations.

In production code, if `detach` throws `IOException` while a primary error occurred in `loadAgent`, do not let cleanup completely obscure the original cause; preserve the primary error and record the cleanup failure via a suppressed exception or by reporting the two statuses separately. The example below records the two statuses separately in an easy-to-follow way.

## 7. Java 17+ Demo: Creating a Target JVM, Attaching, and Testing the Three Error Branches

The following example set **can be compiled standalone with JDK 17+**. To actually test it, you need an environment with a JDK containing the `jdk.attach` module, two compatible local Java processes, appropriate attach permissions, a shared filesystem view of the agent JAR, and a target JVM that allows dynamic agent loading. Test on a sample JVM you control; do not attach arbitrarily to production.

The three Java files and one manifest file reside in **the same directory**. No Maven, Gradle, or external libraries beyond the JDK are needed.

### 7.1. `TargetApp.java` — Application to Attach the Agent To

~~~java
import java.util.concurrent.CountDownLatch;

public final class TargetApp {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("TARGET_PID=" + ProcessHandle.current().pid());
        System.out.println("TARGET_READY");
        new CountDownLatch(1).await();
    }
}
~~~

`ProcessHandle.current().pid()` returns the **target's** PID, not the attach tool's PID. `CountDownLatch(1).await()` keeps the target alive so you have time to run the tool in a second terminal; stop it with `Ctrl+C` when finished testing. This is a demo program intentionally waiting indefinitely, not a production application lifecycle pattern.

### 7.2. `DemoAgent.java` — Agent That Can Succeed or Intentionally Fail in `agentmain`

~~~java
import java.lang.instrument.Instrumentation;

public final class DemoAgent {
    public static void agentmain(String options, Instrumentation inst) {
        System.out.println("AGENT_ARGS=" + options);

        if ("fail".equals(options)) {
            throw new IllegalStateException("demo agentmain failure");
        }

        System.out.println("AGENT_READY=" + (inst != null));
    }
}
~~~

The target JVM will invoke `agentmain(String, Instrumentation)`; the `options` parameter comes from `vm.loadAgent(jar, options)`. The `options="fail"` case makes `agentmain` throw an error **intentionally** to study `AgentInitializationException`. It does not modify bytecode or run an exporter. `premain` is omitted because the example is about **dynamic attach**.

### 7.3. `AttachTool.java` — Catching Each Exception by Stage

~~~java
import com.sun.tools.attach.AgentInitializationException;
import com.sun.tools.attach.AgentLoadException;
import com.sun.tools.attach.AttachNotSupportedException;
import com.sun.tools.attach.VirtualMachine;
import java.io.IOException;
import java.nio.file.Path;

public final class AttachTool {
    public static void main(String[] args) {
        if (args.length != 3) {
            System.err.println(
                    "Usage: java AttachTool <pid> <agent.jar> <agent-options>");
            System.exit(2);
        }

        String pid = args[0];
        String agentJar = Path.of(args[1])
                .toAbsolutePath()
                .normalize()
                .toString();
        String options = args[2];

        VirtualMachine vm = null;
        String phase = "attach";
        boolean loaded = false;
        boolean detached = true;

        try {
            vm = VirtualMachine.attach(pid);
            System.out.println("ATTACH_OK");

            phase = "loadAgent";
            vm.loadAgent(agentJar, options);
            loaded = true;
            System.out.println("LOAD_AGENT_OK");
        } catch (AttachNotSupportedException ex) {
            System.err.println("ATTACH_UNSUPPORTED: " + ex.getMessage());
        } catch (AgentLoadException ex) {
            System.err.println("AGENT_LOAD_FAILED: " + ex.getMessage());
        } catch (AgentInitializationException ex) {
            System.err.println("AGENT_INIT_FAILED: " + ex.getMessage());
        } catch (IOException ex) {
            System.err.println(
                    "IO_FAILURE at " + phase + ": " + ex.getMessage());
        } catch (SecurityException ex) {
            System.err.println(
                    "SECURITY_FAILURE at " + phase + ": " + ex.getMessage());
        } finally {
            if (vm != null) {
                try {
                    vm.detach();
                    System.out.println("DETACH_OK");
                } catch (IOException ex) {
                    detached = false;
                    System.err.println("DETACH_IO_FAILED: " + ex.getMessage());
                }
            }
        }

        if (!loaded || !detached) {
            System.exit(1);
        }
    }
}
~~~

Intentional points in this code:

1. `loadAgent` is called **only after** `VirtualMachine.attach` succeeds. Thus, seeing `AGENT_LOAD_FAILED` or `AGENT_INIT_FAILED` means the code got past handle creation.
2. Catch **`AttachNotSupportedException`, `AgentLoadException`, and `AgentInitializationException` separately**. Different user messages help isolate the exact place to inspect.
3. The `phase` variable distinguishes an `IOException` when establishing attach from I/O when sending the load request. `IOException` is not misattributed to the other three groups.
4. `vm.detach()` is in `finally` and runs only if a `VirtualMachine` was obtained; it runs even if `loadAgent` failed. The tool records `DETACH_IO_FAILED` separately and returns a non-zero exit code.
5. `loaded=true` is set only after `loadAgent` returns normally. This state does not by itself verify all internal agent functions or long-term side effects.
6. The example reports errors via console and exit code for demonstration, **without** automatic retry. Real-world applications should have structured logging, timeouts/limits, and diagnostic info that does not leak secrets.

`VirtualMachine` in JDK 17 does not implement `AutoCloseable` in a way that lets you write `try (VirtualMachine vm = ...)` like a typical resource; you explicitly call `detach()`. Catching `SecurityException` handles only one common permission branch and does not replace OS-level permission checks.

### 7.4. `MANIFEST.MF` — Correct Entrypoint of an Attached Agent

~~~text
Manifest-Version: 1.0
Agent-Class: DemoAgent

~~~

Ensure the manifest file has a **trailing newline and an empty line after `Agent-Class`**, as required by the JAR manifest format. `Agent-Class` must match the exact binary name of the agent class. Here, `DemoAgent` is in no package, so this exact name is used. If placed in a package, both the manifest and the class path inside the JAR must be updated.

### 7.5. Compiling and Packaging (First Terminal)

In the directory containing the four newly created files:

~~~bash
javac --add-modules jdk.attach TargetApp.java DemoAgent.java AttachTool.java
jar --create --file demo-agent.jar --manifest MANIFEST.MF DemoAgent.class
jar --list --file demo-agent.jar
~~~

`javac --add-modules jdk.attach` ensures the module containing `com.sun.tools.attach` is resolved during compilation, while `DemoAgent` uses `java.lang.instrument` from the JDK. The `jar` command creates the agent JAR with the manifest and `DemoAgent.class`. The listing includes `META-INF/MANIFEST.MF` and `DemoAgent.class`; there may be additional entries depending on the tool, so an exact verbatim match of the full `jar --list` output is not required.

### 7.6. Running the Target, Then Running the Tool (Two Terminals)

In **terminal A**, use HotSpot JDK 17 or JDK 21 to run the target:

~~~bash
java -XX:+EnableDynamicAgentLoading -cp . TargetApp
~~~

The `-XX:+EnableDynamicAgentLoading` option is for the **target JVM**. On HotSpot JDK 21, it explicitly allows dynamic agent loading and avoids the JEP 451 warning about dynamic agent loading. On other JVM implementations, check the corresponding flag; attach functionality and dynamic loading depend on the JVM/OS.

Terminal A's console initially prints:

~~~text
TARGET_PID=12345
TARGET_READY
~~~

**12345 is only an example PID.** An actual run will have a different value. Copy the actual PID from `TARGET_PID` and keep the target running.

In **terminal B**, use that PID in the following command (replace `12345` with the printed PID):

~~~bash
java --add-modules jdk.attach -cp . AttachTool 12345 demo-agent.jar ok
~~~

When attach conditions are valid, the tool prints **the exact lines explicitly printed by `AttachTool`** to standard output:

~~~text
ATTACH_OK
LOAD_AGENT_OK
DETACH_OK
~~~

In **target console A**, the agent prints two more lines:

~~~text
AGENT_ARGS=ok
AGENT_READY=true
~~~

Those are the stable lines printed by `DemoAgent` when `Instrumentation` is provided by the JVM and the argument is `ok`. The target console remains alive after `detach`. Do not expect the agent's output to appear in terminal B: `agentmain` runs inside the **target JVM**. The JVM or environment may also emit additional warnings/diagnostics beyond the lines defined by the demo, especially when using a different JDK version or flags.

### 7.7. Triggering an Intentional Initialization Error

Keeping the target running (if the environment allows the agent to be invoked again), run:

~~~bash
java --add-modules jdk.attach -cp . AttachTool 12345 demo-agent.jar fail
~~~

`DemoAgent.agentmain` prints `AGENT_ARGS=fail` and then throws `IllegalStateException`. Per the `VirtualMachine.loadAgent` contract, the tool can receive `AgentInitializationException` and print a line prefixed with:

~~~text
AGENT_INIT_FAILED:
~~~

The part after the colon depends on the JVM and error message; do **not** hard-predict the stack trace or exact message text. The target console may show the initialization error's stack trace. If the system disallows reloading the same agent or the target is in a different state, start a new target before testing; repeated loading should not be assumed to always be idempotent.

### 7.8. Triggering a Load Error and an Attach Error

Try a JAR that does not exist on the filesystem seen by the target JVM:

~~~bash
java --add-modules jdk.attach -cp . AttachTool 12345 missing-agent.jar ok
~~~

In a typical HotSpot environment, if attach succeeds but the JAR cannot be opened/loaded, the tool reports an error at the `loadAgent` step, usually via `AgentLoadException`. Depending on the runtime and how errors are propagated, an `IOException` may occur; cross-check the target JVM logs and the actual exception name received.

To observe an attach error, replace the PID with a PID that does not exist in your environment. When no provider can attach, `VirtualMachine.attach` throws `AttachNotSupportedException`. An I/O or permission error may produce a different exception type; there is no way to force every OS/JVM to produce the exact same message by choosing a fixed PID number.

## 8. Diagnostic Checklist by Exception Location

### 8.1. If You Receive `AttachNotSupportedException`

- Confirm the **PID is correct, currently exists, and belongs to a JVM**; identify the PID's namespace/container.
- Check that the tool program runs on a JDK with `jdk.attach`, a compatible JVM/OS build, and a compatible provider.
- Check attach permissions and flags disabling the attach mechanism, such as `-XX:+DisableAttachMechanism` on HotSpot.
- Record the PID, vendor/JDK, OS, exception message, and target state; test against a sample target.
- Do **not** edit `Agent-Class` or `agentmain` yet just because an error occurred here: those two parts have not been involved in the operation yet.

### 8.2. If You Receive `AgentLoadException`

- Verify attach succeeded; look for `ATTACH_OK` in the tool output.
- Check the **JAR path from the target JVM's perspective**; read permissions, agent class/dependencies, and ZIP/JAR integrity.
- Read `META-INF/MANIFEST.MF` to confirm the exact `Agent-Class` and class name.
- Check the `public static void agentmain(...)` signature, class loading capability, and JVM support.
- Check configuration forbidding dynamic agent loading and the specific message; distinguish it from disabling attach completely.
- Do not retry infinitely when the cause is a misconfiguration/JAR issue or a disallowed policy.

### 8.3. If You Receive `AgentInitializationException`

- Read logs and stack traces inside the **target JVM**, not just the exception from the tool.
- Verify `options`, default values, parsers, dependencies, and resources touched by `agentmain`.
- If needed, test a minimal `agentmain` version that only prints info and returns, then restore initialization steps one by one.
- Check side effects that occurred before throwing the exception: transformers, threads, exporters, hooks, resource handles.
- Do **not** interpret `returnValue()==0` as "the agent initialized successfully" for a Java agent JAR.

### 8.4. If You Receive `IOException` or a Cleanup Error

- Record the **stage**: `attach`, `loadAgent`, or `detach`; confirm the target is still running and the communication channel is active.
- Check transport, temporary files, host/namespace permissions, killed/restarted processes, JVM logs, and OS limits.
- If `detach` fails after `loadAgent` succeeded, record the two events separately; do not assume the agent was not loaded.
- Limit automatic retries for operations that may have been partially executed by the target JVM.

## 9. JVM Flags and Version Differences Affecting Error Interpretation

On HotSpot, distinguish between two mechanisms:

| Target JVM Configuration | Direct Impact | Stage to Observe |
| --- | --- | --- |
| `-XX:+DisableAttachMechanism` | Disables the mechanism allowing tools to attach to the JVM | Typically affects `VirtualMachine.attach` |
| `-XX:-EnableDynamicAgentLoading` | Disallows dynamic agent loading into a running JVM | Attach may succeed, but `loadAgent` is rejected |
| `-XX:+EnableDynamicAgentLoading` | Explicitly allows dynamic agent loading per HotSpot policy | Supports `loadAgent` when other conditions are met |
| `-javaagent:path/to/agent.jar` before app starts | Loads a **startup agent** via `premain`; does not call Attach API in a tool | Different flow from `VirtualMachine.loadAgent` |

JEP 451 in **JDK 21** adds a warning when an agent is dynamically loaded; the warning **does not by itself mean the operation failed**. Using `-XX:+EnableDynamicAgentLoading` on HotSpot expresses explicit approval and avoids that warning. The default policy of **later JDKs** may differ, so you must check the actual version/runtime; do not unconditionally apply the claim "dynamic attach is always enabled" to all future JDK releases.

More importantly, **attach** and **dynamic agent load** are two separable permissions/capabilities. A tool may be able to attach to gather diagnostic info without being permitted to inject an agent. If you only log "attach error" for every `loadAgent` exception, operators can easily fix the wrong permissions or PID instead of checking the agent loading policy.

## 10. Catching, Retry, and Error Reporting Strategies

### 10.1. Catch by *Stage*, Not a Single Generic Exception

A useful pattern is to preserve the call name and exception type. For example:

~~~java
try {
    vm.loadAgent(agentJarPath, options);
} catch (AgentLoadException ex) {
    // Check jar path, manifest, class, dynamic load policy.
} catch (AgentInitializationException ex) {
    // Check agentmain, options, resources, and target JVM logs.
} catch (IOException ex) {
    // Check communication to target; distinguish retryable from deterministic errors.
}
~~~

**This is an illustrative code snippet inside a method that already has variables `vm`, `agentJarPath`, `options`; it is not a standalone class.** The full example in section 7 shows both `attach` and `detach`.

Catching only `Exception` and logging "agent failed" loses stage information. Conversely, a single exception class is also not enough to determine a unique root cause: you need the message, target logs, environment, and correlation.

### 10.2. Retry Based on Error Nature

| Scenario | Reasonable Handling |
| --- | --- |
| PID does not exist, attach provider incompatible | Fix identifier/environment; identical retry is usually useless |
| Wrong JAR path, missing manifest, missing class | Fix artifact/packaging before retrying |
| Deterministic configuration error in `agentmain` | Fix `options`/configuration before retrying |
| Intermittent I/O, target just restarted | May retry **with limits** after verifying the new PID and state |
| Ambiguous result due to timeout while JVM is processing request | Verify whether the agent already ran/left hooks before retrying to avoid double-loading |
| `detach` cleanup failed after load succeeded | Handle transport/cleanup separately; avoid assuming the agent definitely did not run |

An agent can modify bytecode, start threads, or install hooks before reporting an error; uncontrolled retries can cause duplicate instrumentation, memory leaks, or inconsistent state. Agent design should include appropriate idempotence locks/flags and safe shutdown conditions.

### 10.3. Information to Log for Diagnostics

- Target JVM PID/identifier, process start time if available, JDK vendor/version, host/container name, and timestamp.
- Failing stage (`attach`, `loadAgent`, `detach`), **full exception type**, message, and stack trace on the tool side.
- Agent JAR basename, version, checksum (if available), `Agent-Class` value, and readable/unreadable status from the target JVM.
- Logs/stack traces inside the target around the same timeframe; use trace/correlation IDs if available, without exposing secrets.
- Record "loaded", "detached", and "agent confirmed healthy" statuses **separately**; avoid collapsing them into a single boolean.

Do not log raw `options` if they contain tokens, credentials, or secrets. If an agent is loaded via an operational tool, the attach action also requires proper authorization and auditing because it can alter application behavior.

## 11. Misconceptions That Cause Misdiagnosis

1. **"`AgentLoadException` means `attach` failed."** Incorrect: this class belongs to the `loadAgent` call; the `VirtualMachine` object was already created earlier in the demo flow.
2. **"`AttachNotSupportedException` proves the JAR is missing."** Incorrect: it fails before the step that requests reading the JAR.
3. **"`AgentInitializationException` is the exit code of Java `agentmain`."** Incorrect: `agentmain` returns `void`. `returnValue()` mainly supports native `Agent_OnAttach` error codes and can be 0 when no code is present.
4. **"`loadAgent` returned normally, so the application is fully observed."** Incorrect: the agent may not have instrumented the needed classes yet, connected its exporter, or passed post-initialization health checks.
5. **"`detach` unloads the agent from the JVM."** Incorrect: it only terminates the tool's connection.
6. **"An unattachable PID always throws the same exception."** Incorrect: provider, OS, permissions, and I/O affect the exception type and message.
7. **"JDK 21 warning about dynamic loading means the agent was rejected."** Incorrect: the JEP 451 warning describes a policy direction change; check the actual result and JVM flags.
8. **"If agent load fails, the target was completely untouched."** Not guaranteed: initialization failure can occur after side effects.
9. **"Just change `Agent-Class` to `Premain-Class` and it will work."** Wrong for the flow: dynamic attach requires `Agent-Class`/`agentmain`, whereas startup agents require `Premain-Class`/`premain`.
10. **"`IOException` is irrelevant because the three exceptions are caught."** Incorrect: it is in the signature of `attach`, `loadAgent`, and `detach`.

## 12. Self-Check Questions and Exercises

**Scenario A:** `VirtualMachine.attach("99999999")` fails. Should you edit the `Agent-Class` manifest immediately?  
**Hint:** Not yet. Identify the target JVM and attachability first. The specific error type also depends on the provider/environment.

**Scenario B:** The tool prints `ATTACH_OK` followed by `AGENT_LOAD_FAILED`. Which three factors do you check first?  
**Hint:** The JAR path from the target's perspective, the `Agent-Class` manifest / binary class name, and whether the JVM allows dynamic loading.

**Scenario C:** `DemoAgent.agentmain("fail", inst)` throws `IllegalStateException`. How should the tool classify it?  
**Hint:** `AgentInitializationException` under the `loadAgent` contract; also check the stack trace on the target, and do not infer that the target JVM automatically exits.

**Scenario D:** Caught `AgentInitializationException` and `returnValue()==0`. Did the agent definitely succeed?  
**Hint:** No. Zero may simply be the default value when the exception carries no native error code.

**Scenario E:** `loadAgent` returns normally, but `detach` throws `IOException`. How do you report the status?  
**Hint:** Load success and cleanup failure are **two separate outcomes**; do not automatically label it "agent failed".

**Scenario F:** Target runs with `-XX:-EnableDynamicAgentLoading`; the tool can attach but cannot load the agent. Where is the logical place to check?  
**Hint:** The `loadAgent` step and dynamic loading policy, rather than starting by changing the PID.

**Scenario G:** The tool has path `C:\tools\agent.jar`, but the target is inside a Linux container. Why might the agent still fail to load?  
**Hint:** The target JVM must see the path in **its own** filesystem/namespace.

**Scenario H:** When the tool encounters an I/O timeout with an ambiguous outcome, should you immediately retry multiple times?  
**Hint:** Verify the agent/hook state and target first; do not retry unboundedly for operations with side effects.

## 13. Conclusion

The three exception names form a diagnostic map along the **boundaries of the Attach API**:

~~~text
attach(pid) fails
    -> AttachNotSupportedException (or IOException/SecurityException)
attach(pid) succeeds, loadAgent(...) fails because it cannot load/start
    -> AgentLoadException (or IOException/policy/runtime error)
loadAgent(...) reaches agent initialization but agentmain fails
    -> AgentInitializationException
detach() fails
    -> cleanup IOException, must be recorded separately from the load result
~~~

Accurate diagnosis always combines the **API call**, **exception type**, **message**, **JDK/JVM flags**, **target's path**, and **logs from both processes**. That distinguishes connection errors, agent packaging errors, agent initialization errors, and communication errors, while avoiding retries that create duplicate side effects.

### Official Documentation

- [Oracle JDK 17 — VirtualMachine](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html): signatures of `attach`, `loadAgent`, `detach`, and checked exceptions.
- [Oracle JDK 17 — AttachNotSupportedException](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/AttachNotSupportedException.html): meaning of attach provider errors.
- [Oracle JDK 17 — AgentLoadException](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/AgentLoadException.html): error when an agent cannot be loaded.
- [Oracle JDK 17 — AgentInitializationException](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/AgentInitializationException.html): initialization error and meaning of `returnValue()`.
- [Oracle JDK 21 — java.lang.instrument](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): `Agent-Class`, `agentmain`, and dynamic agent loading semantics.
- [Oracle JDK 21 release notes — JEP 451](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html): warnings and `EnableDynamicAgentLoading` on HotSpot.