# Dynamic Agent Loading Warnings, `EnableDynamicAgentLoading`, and Policy by JDK Version

> **Context:** Java Advance → Instrumentation → Attaching to the JVM. This content focuses on agents loaded **after the JVM has started** on HotSpot/OpenJDK, how to read JEP 451 warnings, how to verify JVM flags, and strategies to prepare for upcoming JDK releases. Version information is cross-checked up to **2026-10-31**; JVM vendors may have their own policies or attach implementations.

## 1. Distinguishing Three Timings and Three Operations

An agent is code that runs inside the JVM and can use the `java.lang.instrument` API or the JVM Tool Interface (JVM TI) to observe or transform execution. **Not every connection to a running JVM is agent loading.**

| Trigger method | Typical entry point | When does it happen? | Is it within the scope of JEP 451 warnings? |
|---|---|---|---|
| Startup Java agent: `java -javaagent:agent.jar ...` | `premain(String, Instrumentation)`; manifest `Premain-Class` | At JVM startup, before the application's `main` | **No**: dynamic loading warnings do not apply to agents declared at startup |
| Dynamic Java agent: `VirtualMachine.loadAgent(...)`, typically via the Attach API | `agentmain(String, Instrumentation)`; manifest `Agent-Class` | After the target JVM is already running | **Yes**, when the JVM implements the warning policy and dynamic loading has not been opted in |
| Attach for diagnostics: reading properties/heap/threads or invoking diagnostic commands | Does not necessarily involve `agentmain` or an agent JAR | JVM is already running | **Not automatically**: attach, diagnostic commands, and *agent loading* are different operations |

For example, a tool can use the Attach API to read system information without calling `loadAgent`. The `-XX:-EnableDynamicAgentLoading` flag blocks **dynamic agent loading capability**; it does not mean the entire attach feature or all `jcmd` commands are disabled. Conversely, `-XX:+DisableAttachMechanism` (HotSpot) targets disabling the **attach mechanism** and has a broader scope.

JEP 451 is motivated by the **integrity by default** principle: code with the ability to modify the behavior of a running JVM should receive explicit approval from the operator. Profilers, debuggers, and testing tools have legitimate use cases; however, libraries that automatically attach an agent to an application process can execute privileged code without the operator's awareness.

## 2. Version History: What Has Changed and What Is Expected

**JEP 451 — Prepare to Disallow the Dynamic Loading of Agents** was introduced in **JDK 21 (2023)**. The JEP title speaks of *preparing* for a policy shift: JDK 21 does not mean all attaches are locked down. Dynamic loading remains allowed in the default HotSpot configuration, but the JVM warns when an agent is loaded into a running process if the process owner has not explicitly opted in.

| Version / stage | HotSpot and JEP 451 warnings | `EnableDynamicAgentLoading` | What not to infer |
|---|---|---|---|
| JDK 8 | Has implementation-dependent agent/attach mechanisms; **no JEP 451 warning yet** | Do not take newer HotSpot JDK syntax/configuration as a guarantee for Java 8 | Do not assume no warning means no agent is running |
| JDK 9–20, including JDK 17 | Dynamic agent loading is **enabled by default**, no JEP 451 warning yet | The `-XX:[+|-]EnableDynamicAgentLoading` flag has been supported in HotSpot since JDK 9 | Do not assume the runtime is "safer" just because it is silent |
| JDK 21 | Dynamic loading is **still enabled by default**, but emits a warning on dynamic agent loading if not opted in | `+`: allow and suppress the warning; `-`: deny dynamic loading | **A warning is not an error, nor does it prove bytecode was modified** |
| JDK 22–27 (cross-checked up to 2026-10-31) | The JEP 451 warning/opt-in policy remains a checkpoint when upgrading versions; it is not established that all agents are blocked by default | Use the `+`/`-` flag on the **target JVM** and check the actual status of your vendor/build | Do not arbitrarily assign a specific version as the milestone that "changed the default" based solely on the warning message |
| Future JDK release if the policy shifts | Expected to **disallow dynamic agent loading by default**, unless the operator allows it | `-XX:+EnableDynamicAgentLoading` is the opt-in prepared in advance | The "future release" message **does not announce a committed version number** |

This table is for **HotSpot/OpenJDK** and the versions listed. Another runtime (for example OpenJ9), a custom build, or a vendor update may have different warning details and defaults. When you need certainty, check the **actual JVM running the application**, rather than looking only at the JDK used to build.

As of this article's update milestone, JDK 27 was released in September 2026; you must not read the warning from JDK 21 and claim "JDK 27 definitely blocks dynamic agents by default" without checking the release notes and flags of that specific build. Similarly, do not promise that "it will only change in JDK 28" without an official announcement. Treat this as a **possibility to prepare for and test**, not a fixed rollout date.

## 3. Reading the Warning Correctly

On HotSpot JDK 21 and later, when a running process is asked to dynamically load a Java agent without an opt-in, stderr typically contains a group of lines starting with content like:

~~~text
WARNING: A Java agent has been loaded dynamically (...)
...
WARNING: Dynamic loading of agents will be disallowed by default in a future release
~~~

The middle lines may instruct you to use `-XX:+EnableDynamicAgentLoading` to confirm permission for dynamic loading or `-Djdk.instrument.traceUsage` to assist diagnostics. The JAR path, print count, and formatting can vary by JDK, vendor, and whether an agent was already loaded earlier. **Do not match the entire warning as an invariant string in tests.**

Meaning:

1. **Event:** The JVM observed a request to load an agent into a running process. With the typical warning, loading the agent is currently permitted; this is **not by itself** an error.
2. **Future risk:** Relying on default dynamic loading may stop working in a later JVM release.
3. **Decision authority:** The person running the JVM must actively allow it if this capability is genuinely needed. Simply changing the application's log level will not resolve the root cause, because the warning comes from the JVM and is usually written to **stderr**.

For example: a test suite using a mocking tool or bytecode instrumentation may still **PASS** while the JVM prints the warning. Do not resolve this by suppressing logs without identifying who requested the agent load. In environments with multiple JVMs (IDE, Gradle daemon, Gradle Test worker, Maven Surefire fork, app server), you need to find the **exact PID and exact target JVM**.

## 4. Three Key Flags and Their Scope

### `-XX:+EnableDynamicAgentLoading` — explicitly allow

~~~bash
java -XX:+EnableDynamicAgentLoading -cp out/app demo.app.TargetApp
~~~

On HotSpot with JEP 451, this is the **opt-in** signal at startup: it allows dynamic agent loading and suppresses the JEP 451 warning group when an agent is loaded. The flag must be on the **command line of the target JVM when it starts**, not merely added to the Attach tool in another process. You cannot expect to change an `-XX` flag of an already running JVM by passing it to the `java` command that runs the client.

The flag does not grant OS permissions, does not unlock all restricted attach mechanisms, and does not fix a broken agent JAR. It also does **not** make an agent appear on its own: there must still be an actual request to load an agent.

### `-XX:-EnableDynamicAgentLoading` — test the blocking policy

~~~bash
java -XX:-EnableDynamicAgentLoading -cp out/app demo.app.TargetApp
~~~

This simulates the **disallow dynamic agent loading** condition of the future policy. With a `VirtualMachine.loadAgent(...)` call, you will typically receive an agent loading error in the requesting tool instead of invoking `agentmain` in the target JVM. The exception name and detailed message are implementation-specific; for instance, the client may receive `AgentLoadException`. **Do not assume the target JVM will die**: the application process usually continues running.

An important distinction: even when `-XX:-EnableDynamicAgentLoading` is enabled, a Java agent specified at **startup** with `-javaagent` is not prohibited by this flag itself. This is a useful way to verify whether a library can be switched to starting alongside the application.

### `-Djdk.instrument.traceUsage=true` — trace Instrumentation usage

~~~bash
java -Djdk.instrument.traceUsage=true -cp out/app demo.app.TargetApp
~~~

This system property requests printing traces/stack traces of operations using `java.lang.instrument` to help track down the actor instrumenting code. It is **not** a flag that permits agent loading, nor is it a mechanism guaranteed to list every Attach event. In the hands-on example below, the agent only prints a line without calling methods on the `Instrumentation` object, so **there is no guarantee it will emit additional stack traces**. When a library actually calls Instrumentation APIs, this information is more useful.

### Commonly confused flags

| Flag / property | Primary meaning | Does it replace the dynamic agent loading opt-in? |
|---|---|---|
| `-javaagent:...` | Loads a Java agent **at startup** (`premain`) | Does not need a dynamic loading opt-in; this is a different startup path |
| `-XX:+EnableDynamicAgentLoading` | Allows the process owner to approve dynamic agent loading | **Yes**, for this feature on HotSpot |
| `-XX:-EnableDynamicAgentLoading` | Denies dynamic agent loading after startup | No; it intentionally blocks it |
| `-XX:+DisableAttachMechanism` | Disables the HotSpot attach mechanism, which can affect many diagnostic tools | No; it may even block attach requests upfront |
| `-Djdk.attach.allowAttachSelf=true` | On JDKs that support it, changes the **self-attach** restriction within the same process | **No**: self-attach and dynamic agent loading permission are two separate controls |
| `-Djdk.instrument.traceUsage=true` | Traces Instrumentation usage | **No**, it is only a root-cause diagnostic tool |

There is no equivalence between "attach succeeded" and "loadAgent succeeded". In dynamic-loading-denied mode, some attach operations used for diagnostics can still continue to work.

## 5. Java 17+ Hands-On: Observing Both `premain` and `agentmain`

The experiment creates an agent that **does not transform bytecode**, an application acting as the target JVM, and a separate Attach program. Use **two terminal windows** for the two processes so you can see where the warning appears. The sample compiles with JDK 17+; **to actually observe the JEP 451 warning, you must run the target JVM with JDK 21 or later**.

### Directory structure

~~~text
dynamic-agent-policy/
├── manifest.mf
├── src/
│   └── demo/
│       ├── agent/
│       │   └── PolicyAgent.java
│       ├── app/
│       │   └── TargetApp.java
│       └── attach/
│           └── LoadAgent.java
└── out/
    ├── agent/
    ├── app/
    ├── attach/
    └── policy-agent.jar
~~~

Create the files inside the `dynamic-agent-policy/` root directory; `out/` is generated during the build. No Spring, Maven, Gradle, or external libraries are required.

### File `src/demo/agent/PolicyAgent.java`

~~~java
package demo.agent;

import java.lang.instrument.Instrumentation;

public final class PolicyAgent {
    private PolicyAgent() {}

    public static void premain(String args, Instrumentation inst) {
        System.out.println("[AGENT] premain args=" + args);
    }

    public static void agentmain(String args, Instrumentation inst) {
        System.out.println("[AGENT] agentmain args=" + args);
    }
}
~~~

An agent JAR **can support both launch modes**, but which entry point is used depends on how it is triggered. `-javaagent` invokes `premain`; the Attach API `loadAgent` invokes `agentmain`. In this sample, both methods only print a message for observation, without calling `addTransformer` or modifying classes.

### File `src/demo/app/TargetApp.java`

~~~java
package demo.app;

public final class TargetApp {
    public static void main(String[] args) throws Exception {
        System.out.println("[TARGET] pid=" + ProcessHandle.current().pid());
        System.out.println("[TARGET] ready; press Enter to exit");
        System.in.read();
        System.out.println("[TARGET] bye");
    }
}
~~~

The application prints the current process PID and waits for Enter so you can attach from another terminal. It must be run in an **interactive terminal** that keeps stdin open; if stdin is closed/EOF (for example, some CI runners), it may exit immediately after printing. The PID will differ across runs.

### File `src/demo/attach/LoadAgent.java`

~~~java
package demo.attach;

import com.sun.tools.attach.VirtualMachine;
import java.nio.file.Path;

public final class LoadAgent {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("Usage: LoadAgent <pid> <agent-jar>");
            System.exit(2);
        }

        String pid = args[0];
        String jar = Path.of(args[1]).toAbsolutePath().normalize().toString();

        VirtualMachine vm = VirtualMachine.attach(pid);
        try {
            vm.loadAgent(jar, "probe");
            System.out.println("[ATTACH] loadAgent completed");
        } finally {
            vm.detach();
        }
    }
}
~~~

The code uses the **`jdk.attach`** module, provided by the JDK since Java 9; this is a JDK-specific API, which does not mean every JVM/runtime image supports it. `VirtualMachine.attach(pid)` connects to the target JVM; `vm.loadAgent(jar, "probe")` asks the target JVM to load the JAR and invoke `agentmain`. `detach()` releases the connection in all cases. The sample does **not** attach to the client process itself, so self-attach permission does not need to be enabled.

### File `manifest.mf`

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.PolicyAgent
Agent-Class: demo.agent.PolicyAgent

~~~

The **agent JAR** manifest has both `Premain-Class` and `Agent-Class`. Those are two distinct attributes. If only `Premain-Class` is present, you cannot use the same JAR for `VirtualMachine.loadAgent` under the Java Instrumentation contract. Make sure the manifest has a trailing newline at the end of the file; the `jar` tool will place it into `META-INF/MANIFEST.MF`.

### Compile and package

macOS/Linux (Bash):

~~~bash
mkdir -p out/agent out/app out/attach

javac --release 17 -d out/agent src/demo/agent/PolicyAgent.java
javac --release 17 -d out/app src/demo/app/TargetApp.java
javac --add-modules jdk.attach -d out/attach src/demo/attach/LoadAgent.java

jar --create --file out/policy-agent.jar --manifest manifest.mf -C out/agent .
jar --list --file out/policy-agent.jar
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path out/agent, out/app, out/attach | Out-Null

javac --release 17 -d out/agent src/demo/agent/PolicyAgent.java
javac --release 17 -d out/app src/demo/app/TargetApp.java
javac --add-modules jdk.attach -d out/attach src/demo/attach/LoadAgent.java

jar --create --file out/policy-agent.jar --manifest manifest.mf -C out/agent .
jar --list --file out/policy-agent.jar
~~~

Use `--release 17` for the agent and application to produce class files that run on JDK 17 and later; the compiler for the client uses the installed JDK and the `jdk.attach` module. When multiple JDKs are installed on the machine, you should choose the **same vendor/major JDK and compatible architecture** for both the client and the target JVM to avoid Attach API errors unrelated to JEP 451.

The JAR listing must include `META-INF/MANIFEST.MF` and `demo/agent/PolicyAgent.class`. If the package or agent class name is wrong, an error will occur **before** you reach the expected checkpoints.

## 6. Four Experimental Scenarios

### Case A — dynamic loading on HotSpot JDK 21+ with default warning

**Terminal A:** from the project root directory, run the target JVM:

~~~bash
java -cp out/app demo.app.TargetApp
~~~

Expected initial lines in terminal A:

~~~text
[TARGET] pid=12345
[TARGET] ready; press Enter to exit
~~~

`12345` is only an **example PID**; use the **actual PID** printed in your run. Keep terminal A waiting for Enter.

**Terminal B:** in the same project directory, replace `12345` with that PID:

~~~bash
java --add-modules jdk.attach -cp out/attach demo.attach.LoadAgent 12345 out/policy-agent.jar
~~~

With valid attach permissions and dynamic loading allowed, the client is expected to print:

~~~text
[ATTACH] loadAgent completed
~~~

In **terminal A of the target JVM**, you will see the line:

~~~text
[AGENT] agentmain args=probe
~~~

And on **stderr of the target JVM**, there may be the JEP 451 warning group (containing the word `WARNING`). The *interleaved* ordering between stdout and stderr is not strictly guaranteed because they are two separate output streams. What to verify is: `agentmain` runs **after the app has entered `main`**, and the warning does not mean the command failed.

### Case B — opt-in from the start: `-XX:+EnableDynamicAgentLoading`

Stop the target JVM in terminal A by pressing Enter, then run it again:

~~~bash
java -XX:+EnableDynamicAgentLoading -cp out/app demo.app.TargetApp
~~~

Terminal B invokes `LoadAgent` again with the **new PID**. Expected outcome: `[AGENT] agentmain args=probe` still appears on the target JVM and `[ATTACH] loadAgent completed` on the client side, but **there is no JEP 451 warning group** for missing opt-in. Other application logs may still appear.

**Reason:** the `+` flag does not block attach; it confirms that the process owner allows dynamic agent loading. Putting the flag in **terminal B** without putting it in **terminal A** does not resolve the warning on the target JVM.

### Case C — blocking dynamic loading: `-XX:-EnableDynamicAgentLoading`

Stop the target JVM, and restart terminal A:

~~~bash
java -XX:-EnableDynamicAgentLoading -cp out/app demo.app.TargetApp
~~~

Terminal B runs the Attach command with the new PID. Expected outcome:

- The attach connection part may still succeed.
- The `loadAgent` request **is rejected**; the client gets an exception (usually of the `AgentLoadException` family) and does **not** print `[ATTACH] loadAgent completed`.
- The target JVM does not execute `PolicyAgent.agentmain`, so there is no `[AGENT] agentmain args=probe` line from the blocked request.
- The `TargetApp` program can still wait for Enter and exit normally; you should not conclude "the JVM crashed".

Detailed error messages may vary by version, vendor, and attach method. Do not hard-code exact error text in tests; check **presence/absence of the callback, command success or failure, and the target JVM's flags**.

### Case D — startup agent still runs even when dynamic loading is disallowed

This is a very important comparison test. Run in terminal A:

~~~bash
java -XX:-EnableDynamicAgentLoading -javaagent:out/policy-agent.jar=boot -cp out/app demo.app.TargetApp
~~~

Expected initial lines in order:

~~~text
[AGENT] premain args=boot
[TARGET] pid=12345
[TARGET] ready; press Enter to exit
~~~

Once again, the PID is only an **example**. No JEP 451 **dynamic** loading warning appears because the agent was requested on the startup command line. The `-XX:-EnableDynamicAgentLoading` flag controls loading **after the JVM is running**, so by itself it does not forbid `-javaagent`. If you continue sending a `loadAgent` request from terminal B to this JVM, the **additional load** request may be rejected as in Case C.

### Summary of expected results

| How the **target JVM** is run | `premain` | `agentmain` when client requests | JEP 451 warning from dynamic load | Dynamic load result |
|---|---:|---:|---|---|
| No agent, no flag (HotSpot JDK 21+) | No | Yes | Yes, typically | Allowed under current default |
| `-XX:+EnableDynamicAgentLoading` | No | Yes | No, because opted in | Allowed |
| `-XX:-EnableDynamicAgentLoading` | No | No | No "loaded successfully" warning for a blocked agent | Rejected |
| `-XX:-EnableDynamicAgentLoading -javaagent:...` | Yes | No if dynamic loading is attempted afterward | None for the startup agent | Startup succeeds, dynamic loading remains blocked |

Keep the **agent JAR**, target JVM, attach permissions, and client constant across all four runs, changing only the flags. Use a **new PID** each time, because each `java` invocation spawns a new JVM.

## 7. Diagnosing Warnings in Real Projects

### Step 1: confirm the version and the JVM actually emitting the warning

~~~bash
java -version
java -XX:+PrintFlagsFinal -version 2>&1 | grep EnableDynamicAgentLoading
~~~

On PowerShell, replace the filter with:

~~~powershell
java -version
java -XX:+PrintFlagsFinal -version 2>&1 | Select-String EnableDynamicAgentLoading
~~~

`PrintFlagsFinal` shows the flag state of the **JVM running that command**, which does not automatically reflect another application JVM started from an IDE/service. To know the actual runtime, check the command line and version of the **target PID**, the process manager/IDE/container configuration, and the flags passed to the exact Java process.

In build ecosystems, distinguish the JVM driving the **Gradle daemon** from the JVM running the **Gradle Test worker**, or the **Maven launcher** JVM from the **Surefire fork**. An agent may be inside the test JVM even if the daemon does not display a warning.

### Step 2: find who is loading the agent

Common sources are testing tools that need to instrument classes, inline mocking, profiling, monitoring, bytecode weaving, or libraries that call self-attach at runtime. Check tool dependencies/configurations, startup scripts, and logs printed by the target JVM; use `-Djdk.instrument.traceUsage=true` **on the target JVM** to trace Instrumentation API calls when relevant activity occurs.

Not every message containing the word `agent` belongs to JEP 451. If the primary error is `AttachNotSupportedException`, PID not found, or permission denied, you must resolve the **attach connection** first. If attach succeeds but `Agent-Class` is missing, you must fix the **manifest**. If the error says dynamic loading is denied, check `-XX:-EnableDynamicAgentLoading` and the runtime policy.

### Step 3: prefer startup agents when possible

If the library/tool supports specifying the agent at JVM startup, switch to `-javaagent:<path-to-JAR>` with the appropriate `Premain-Class`. This makes the agent's intervention transparent, easy to audit, and unaffected by changes to the **dynamic** loading default. **Not every JAR originally loaded via `agentmain` already provides `premain`**: you must check the manifest and documentation of the tool itself.

Example configuration for the JVM running the **Gradle test task** (Groovy DSL):

~~~groovy
tasks.withType(Test).configureEach {
    // Diagnostic: test the policy that denies dynamic loading.
    jvmArgs '-XX:-EnableDynamicAgentLoading'
}
~~~

If tests fail because a dependency genuinely requires attach, you can temporarily opt in on that exact test JVM:

~~~groovy
tasks.withType(Test).configureEach {
    jvmArgs '-XX:+EnableDynamicAgentLoading'
}
~~~

These are **two mutually exclusive configurations**; do not declare both at the same time. The `-XX:+...` configuration lets tests keep running via dynamic loading, but does not eliminate the dependency on attach. To remove that dependency, consult the library's official guide on supplying `-javaagent` to the test JVM; different library versions may require different JARs and arguments.

Example with Maven Surefire: configure `<argLine>` for the **forked test JVM** if you need to test with `-XX:-EnableDynamicAgentLoading`:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-surefire-plugin</artifactId>
  <configuration>
    <argLine>-XX:-EnableDynamicAgentLoading</argLine>
  </configuration>
</plugin>
~~~

When the project already has an `argLine` generated by JaCoCo or another test configuration, **you must merge** the arguments according to the plugin's instructions, rather than overwriting blindly. The snippet above only illustrates the meaning of the flag, not a complete configuration for every project.

### Step 4: confirm deployment usage requirements

If dynamic attach is needed for a profiler/debugger in production, document enabling `-XX:+EnableDynamicAgentLoading` as a JVM operator decision, and control account permissions and the origin of the agent JAR. If not needed, test with `-XX:-EnableDynamicAgentLoading` in staging/CI to uncover hidden self-attaches before upgrading the JDK. Do not treat a silent warning as proof that all agents are safe.

## 8. Common Misconceptions

**"JDK 21 and later have banned attach."** False. JEP 451 adds a warning on dynamic agent loading; attach and loadAgent are two separate capabilities. You need to check the specific build/JVM.

**"The warning makes tests fail."** Not by itself; there can be a warning on stderr while tests still PASS. Test failures are usually caused by another exception, a policy that already sets `-XX:-EnableDynamicAgentLoading`, or a tool that classifies warnings as errors.

**"Just add `-XX:+EnableDynamicAgentLoading` to the attach client command."** False. The flag must be set on the **JVM process receiving the agent** when that process starts.

**"`-Djdk.instrument.traceUsage` is how you turn off the warning."** False. That is a way to help trace instrumentation API usage; the HotSpot opt-in uses `-XX:+EnableDynamicAgentLoading`.

**"`-javaagent` and `VirtualMachine.loadAgent` both invoke `premain`."** False. Startup goes through `premain`, while dynamic goes through `agentmain`. If you want one JAR to support both, it must have both the corresponding entry points and manifest attributes.

**"Enabling `-XX:+EnableDynamicAgentLoading` enables self-attach for every process."** False. OS permissions, attach providers, security policies, runtime image types, and self-attach restrictions can still block it. The dynamic loading opt-in is not a way to bypass those permissions.

**"Seeing the words 'future release' in the WARNING tells you the exact JDK that will ban it."** False. That is a preparatory notice. Read the release notes of the runtime you are using, verify the default by testing the `-XX:-EnableDynamicAgentLoading` flag, and re-check when updating versions.

## 9. Self-Check Questions

1. **JDK 21, no flags passed, an agent is loaded via the Attach API: can there be a warning while the agent still runs?** Yes. In HotSpot's JEP 451 default, dynamic loading is still allowed; the warning only reminds about a future change.
2. **To simulate the default blocking dynamic loading, which flag do you use?** `-XX:-EnableDynamicAgentLoading` on the target JVM.
3. **To confirm the process owner allows dynamic loading and avoid the current JEP 451 warning, what do you use?** `-XX:+EnableDynamicAgentLoading` on the target JVM, from startup.
4. **Does the flag that denies dynamic loading forbid `-javaagent` at startup?** No, that is a separately governed startup path.
5. **If the client can attach but `loadAgent` fails, does that prove attach is completely disabled?** No. The connection may still work while the agent load request is rejected.
6. **Looking at the stdout of an agent that only prints a marker, can you claim it modified bytecode?** No. Loading an agent and calling class-instrumenting APIs are two different events.
7. **Can you use the Java compiler version to know which JVM printed the warning?** No; you must check the runtime of the process emitting the warning.

## 10. Checklist Before Upgrading the JDK

- [ ] Record the JVM vendor, actual running JDK build, PID, and flags in the environment where the warning appears.
- [ ] Determine whether `-javaagent` is used at startup or loaded via `VirtualMachine.loadAgent`/an equivalent tool while the JVM is running.
- [ ] Test in the same environment with `-XX:-EnableDynamicAgentLoading` to uncover where dynamic loading is genuinely relied upon.
- [ ] Switch to a startup agent when the tool supports it; verify the library's manifest and parameters.
- [ ] If dynamic loading is unavoidable, set `-XX:+EnableDynamicAgentLoading` **on the target JVM** and ensure permissions/agent sources are controlled.
- [ ] Check **stderr** logs and actual behavior; do not treat the disappearance of a warning as a complete verification.
- [ ] Read the release notes of the exact JDK before concluding that the policy has changed.

## Authoritative References

- [OpenJDK JEP 451 — Prepare to Disallow the Dynamic Loading of Agents](https://openjdk.org/jeps/451): goals, motivation, warnings starting in JDK 21, opt-in mechanism, and policy transition direction.
- [Oracle JDK 21 Release Notes — Warning Printed When an Agent Is Loaded](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html): description of HotSpot behavior, `EnableDynamicAgentLoading`, and `jdk.instrument.traceUsage`.
- [Java SE 26 — `java.lang.instrument` Package Specification](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/package-summary.html): distinction between `premain`/`agentmain`, `Premain-Class`/`Agent-Class`, and warnings on stderr.
- [Java SE 21 — `jdk.attach` Module](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.attach/module-summary.html): module providing `com.sun.tools.attach`.
- [Oracle JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): checkpoint for policy and JDK 27 release information at the time of this article's update.
