# Warnings or Restrictions on Dynamic Agent Loading Across JDK Versions

During a JDK upgrade, an application may continue to compile, pass tests, and start normally yet unexpectedly print a warning related to **dynamically loaded agents**:

```text
WARNING: A Java agent has been loaded dynamically (...)
WARNING: If a serviceability tool is in use, please run with
         -XX:+EnableDynamicAgentLoading to hide this warning
WARNING: If a serviceability tool is not in use, please run with
         -Djdk.instrument.traceUsage for more information
WARNING: Dynamic loading of agents will be disallowed by default
         in a future release
```

This set of warnings comes from **JEP 451 — Prepare to Disallow the Dynamic Loading of Agents**, introduced in JDK 21. The goal of this change is strengthening JVM integrity: the ability to modify or observe bytecode in an already-running process should be a controlled decision, rather than a hard-to-detect side effect of a library or test framework.

The warning does not automatically mean the application is under attack or that an agent is incompatible. Nor does it mean all Java agents or all diagnostic tools have been forbidden. What needs to be done is separating **agents declared at JVM startup** from **agents attached after the JVM is running**, identifying which JDK executes the target process, understanding that JVM's dynamic-loading policy, and choosing an appropriate deployment mechanism.

This lesson explains Java agents and native JVMTI agents, the Attach API, changes across JDK versions, dynamic-loading control flags, `premain` and `agentmain` examples, Mockito/Byte Buddy/APM scenarios, security risks, troubleshooting, and migration procedures.

> **Version note:** JDK 21 is the milestone for JEP 451 when the warning was introduced. For JDKs newer than 21, including whichever JDK release is used at deployment time, you must inspect the release notes and behavior of the **exact vendor, update level, and runtime image**. Do not turn the JEP's "in a future release" statement into an unverified claim that specific JDKs have already changed the default.

## 1. What is an agent in Java?

### 1.1. Java instrumentation agent

A Java agent is a component running inside the JVM to observe or influence class loading and execution. Its core API is:

```java
java.lang.instrument.Instrumentation
```

An agent can register a `ClassFileTransformer`, inspect loaded classes, transform bytecode at permitted points, or retransform/redefine eligible classes.

Common legitimate uses:

- Application Performance Monitoring (APM), tracing, and profiling.
- Code coverage during tests.
- Mocking frameworks needing class instrumentation, such as certain Mockito/Byte Buddy configurations.
- Debugging, serviceability, and diagnostic tooling.
- Organization-managed runtime policy enforcement or observability.
- Framework integrations requiring bytecode transformation.

An agent wields deep power inside the process. It can affect behavior, access sensitive data, and impact performance; therefore, permission to load an agent must be treated like permission to alter runtime integrity.

### 1.2. Native JVMTI agent

The Java Virtual Machine Tool Interface (JVMTI) enables native agents to interact with the JVM via virtual-machine-level APIs. Native agents are typically shared libraries:

```text
Linux   : libobserver.so
macOS   : libobserver.dylib
Windows : observer.dll
```

Native agents can be configured at startup through options such as `-agentlib` or `-agentpath` and, when supported by the runtime, loaded dynamically through attach mechanisms.

Java instrumentation agents and JVMTI native agents differ in APIs and packaging, yet both can fall under **dynamic agent loading** controls.

### 1.3. Agents differ from ordinary Java libraries

Adding a JAR to the classpath does not automatically make it a Java agent. An agent JAR has a manifest declaring entry points and is loaded by the JVM through agent mechanisms.

Example:

```text
application.jar       -> contains the application
logging-api.jar       -> ordinary dependency
observability-agent.jar -> agent JAR with Premain-Class / Agent-Class
```

One observability product may ship both an API library and a standalone agent. Identify which component is actually loaded via JVM flags or the Attach API.

## 2. Two ways to load an agent: at startup vs. dynamically at runtime

### 2.1. Startup agent

A Java instrumentation agent can be declared before the application starts:

```shell
java -javaagent:/opt/agents/observe-agent.jar \
     -jar application.jar
```

In this mode, the JVM knows about the agent from the start. The entry point is typically `premain`.

Advantages:

- Reflects an explicit decision by whoever manages JVM startup.
- Does not require attach permissions against a running process afterward.
- Can instrument critical classes from the moment they are loaded.
- Depends less on dynamic-attach policies of newer JDKs.
- Fits declarative configuration in service launchers, containers, test JVMs, or CI.

Limitations:

- Usually requires restarting the JVM to add, remove, or swap agents.
- Requires managing agent versions, arguments, and JAR paths before launch.
- Agent failures during initialization can prevent the application from starting.
- Not every agent supports the same usage pattern.

### 2.2. Dynamic agent

Dynamic attach happens after the target JVM has already started:

```text
Running application JVM
        |
        v
Tool / attaching process
        |
        v
Attach API / serviceability mechanism
        |
        v
Target JVM loads Java agent or native agent
        |
        v
agentmain(...) or corresponding agent entry point
```

A Java instrumentation agent loaded dynamically typically uses `agentmain`, while a native JVMTI agent uses the entry point specified by JVMTI.

Advantages:

- Can enable diagnostics or instrumentation without necessarily restarting the application.
- Useful when investigating an already-running process.
- Some developer tools self-attach to perform mocking/instrumentation.

Limitations:

- Depends on attach mechanisms, OS permissions, the target JVM's agent-loading capability, and packaging.
- May trigger warnings or rejections depending on JDK policy.
- Already-loaded classes may need retransformation/redefinition, and not all bytecode modifications are supported.
- Self-attachment carries additional restrictions of its own.
- A library may attach an agent without operators realizing it.

### 2.3. Quick comparison

| Criterion | Startup agent | Dynamic agent |
|---|---|---|
| Load timing | Before/at the start of JVM launch | After the JVM process is already running |
| Common options | `-javaagent`, `-agentlib`, `-agentpath` | Attach API and corresponding tools |
| Java agent entry point | `premain` | `agentmain` |
| Needs attach to running JVM | No | Yes |
| JEP 451 warning on dynamic load | Not a standard dynamic-loading warning case | Requires attention starting in JDK 21 |
| Future policy impact | Startup mechanism is explicitly authorized | May be restricted by default depending on release |
| Needs restart to add an agent | Usually yes | Not necessarily, if the JVM permits |
| Early class instrumentation | Better | May have missed initial class loading |

The most important distinction is not whether agent code is "strong" or "weak", but **who allows the agent to intervene in the JVM, and when**.

## 3. Java agent entry points: premain and agentmain

### 3.1. Agent supporting startup loading

A minimal Java agent:

```java
package com.example.agent;

import java.lang.instrument.Instrumentation;

public final class ObserveAgent {
    private ObserveAgent() {
    }

    public static void premain(
            String agentArgs,
            Instrumentation instrumentation) {

        System.out.println(
            "[agent] premain called; args=" + agentArgs
        );

        System.out.println(
            "[agent] loaded class count="
                + instrumentation.getAllLoadedClasses().length
        );
    }
}
```

This example only prints information supplied by the JVM without modifying classes. For the runtime to locate the entry point via `-javaagent`, the JAR manifest must declare `Premain-Class` accurately.

### 3.2. Agent supporting dynamic loading

Adding the dynamic entry point:

```java
package com.example.agent;

import java.lang.instrument.Instrumentation;

public final class ObserveAgent {
    private ObserveAgent() {
    }

    public static void premain(
            String options,
            Instrumentation instrumentation) {

        report("premain", options, instrumentation);
    }

    public static void agentmain(
            String options,
            Instrumentation instrumentation) {

        report("agentmain", options, instrumentation);
    }

    private static void report(
            String mode,
            String options,
            Instrumentation instrumentation) {

        System.out.println(
            "[agent] " + mode + " options=" + options
        );
        System.out.println(
            "[agent] loaded="
                + instrumentation.getAllLoadedClasses().length
        );
    }
}
```

When loaded as a startup agent, the JVM calls `premain`; when loaded dynamically via the Java instrumentation agent protocol, the JVM calls `agentmain`. An agent can support one or both modes.

Real instrumentation passes often call `addTransformer`, `retransformClasses`, or `redefineClasses`. These operations depend on declared capabilities, class modifiability, JDK version, and bytecode format; never assume arbitrary classes can always be altered freely.

### 3.3. Agent JAR manifest

Example:

```text
Manifest-Version: 1.0
Premain-Class: com.example.agent.ObserveAgent
Agent-Class: com.example.agent.ObserveAgent
Can-Redefine-Classes: true
Can-Retransform-Classes: true
```

Attribute meanings:

- `Premain-Class`: entry point class when loaded via `-javaagent`.
- `Agent-Class`: entry point class when loaded dynamically.
- `Can-Redefine-Classes`: capability required to use class-redefinition APIs.
- `Can-Retransform-Classes`: capability required for retransformation.
- `Can-Set-Native-Method-Prefix`: capability related to native method prefixes for agents using that feature.

Declaring a capability does not guarantee the JVM allows every transformation the agent attempts. At runtime, use `Instrumentation.isRedefineClassesSupported()` and `isRetransformClassesSupported()` to verify.

### 3.4. Building an agent JAR differs from a normal application JAR

The agent entry class and its required dependencies must be packaged/visible appropriately when loaded by the JVM. When relying on bytecode libraries, resolve classloading, package conflicts, and module access properly.

Building a JAR with a valid manifest is only the initial prerequisite. Test both execution paths separately if the agent commits to supporting both startup and dynamic loading.

## 4. The Attach API and target JVMs

### 4.1. Java API for dynamic agent loading

The JDK provides an API for tools to interact with another JVM:

```java
com.sun.tools.attach.VirtualMachine
```

An administrative tool can attach to a target JVM process and request loading an agent JAR. Illustrative example using an operator-provided PID and path:

```java
import com.sun.tools.attach.VirtualMachine;
import java.nio.file.Path;

public final class AttachAgentTool {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                "Usage: AttachAgentTool <pid> <agent-jar>"
            );
        }

        String pid = args[0];

        Path agentPath = Path.of(args[1])
            .toAbsolutePath()
            .normalize();

        VirtualMachine vm = VirtualMachine.attach(pid);

        try {
            vm.loadAgent(agentPath.toString(), "mode=observe");
        } finally {
            vm.detach();
        }
    }
}
```

This illustrates the API inside an authorized JVM administration context, not advice to load agents arbitrarily into another process. The tool succeeds only if the JDK and target process expose the attach mechanism, OS permissions allow it, and dynamic-loading policy does not reject the request.

### 4.2. The attaching program and target JVM are two separate processes

Separate the two:

```text
Process A: AttachAgentTool runs with JDK A
Process B: Target application JVM runs with JDK B
```

The attaching tool's JDK is **not necessarily** the target application's JDK. Warnings and dynamic-agent-loading permissions are governed primarily by the **target JVM**, not only by the JDK running the attach client.

If the attach tool reports success while the agent fails to act, inspect both the target JVM's logs and the tool's logs. The agent may have loaded and failed inside `agentmain`, or instrumentation code may be incompatible with active class-file versions.

### 4.3. From tools.jar to the jdk.attach module

On many traditional JDK 8 distributions, the Attach API lived inside the JDK's `tools.jar`, rather than inside every minimal JRE.

Starting in JDK 9, the modular JDK introduced the `jdk.attach` module. A modular application using the Attach API may need a descriptor:

```java
module com.example.attachtool {
    requires jdk.attach;
}
```

For classpath applications or custom runtime images, verify that `jdk.attach` is present and resolved in the active configuration.

Never copy `tools.jar` from JDK 8 into a newer JDK runtime to "restore" the Attach API; that is not a supported migration path.

### 4.4. Custom runtime images may omit attach support

When building a runtime via `jlink`, which modules enter the image is a packaging decision. A minimal image may omit necessary tooling modules.

Check separately:

- Does the **attach tool's** runtime include `jdk.attach` and needed modules?
- Does the **target JVM's** runtime support serviceability/attach and instrumentation?
- Does the agent JAR require `java.instrument` or other modules?
- Did the JDK vendor or custom image strip those features?

Do not assume a container holding only a minimal application runtime image includes `jcmd`, `jps`, or full JDK tools like a developer workstation.

## 5. Changes across JDK versions

### 5.1. JDK 8: attach mechanisms already existed

In common HotSpot/OpenJDK 8 releases, Java instrumentation and the Attach API were widely used by tools. Documentation/builds may reference `tools.jar` and JDK 8-specific commands or APIs.

Points to check when upgrading:

- Do not assume tooling classpaths still contain `lib/tools.jar`.
- Old agents may touch unstable JVM/JDK internals.
- Bytecode transformers may not understand new class-file versions.
- Startup/attach flags can differ across vendors and JDK releases.

### 5.2. JDK 9 onward: JPMS and the reorganized JDK

The Attach API moved into the JDK module system. Java instrumentation and JVMTI remain core mechanisms, yet strong module encapsulation breaks some reflective tricks used by older agents and frameworks.

Example errors that can occur:

```text
java.lang.reflect.InaccessibleObjectException
java.lang.IllegalAccessError
java.lang.ClassNotFoundException
```

Do not lump these errors together with JEP 451 warnings. They often relate to module exports/opens, classloading, or dependency incompatibility rather than dynamic-agent-loading permissions.

### 5.3. JDK 17 and pre-JDK 21 releases

On common HotSpot/OpenJDK runtimes prior to JDK 21, dynamic agent loading frequently worked without standard JEP 451 warnings. Even so, attach capability could still be restricted by flags, OS permissions, containers, or security policies.

Hence, "no JEP 451 warning" does **not** mean agent loading works on every host. Nor should you assume Java 17 carries zero instrumentation risks merely because logs show no warning.

### 5.4. JDK 21: JEP 451 introduces warnings

JEP 451 prepares the ecosystem for disallowing dynamic agent loading by default in the future. At JDK 21, when a Java agent or JVMTI agent is loaded dynamically in scenarios covered by the JEP, the JVM may print warnings to standard error.

Core message:

- **Dynamic loading** of an agent occurred.
- If intentional for administration/serviceability, permit it explicitly with `-XX:+EnableDynamicAgentLoading`.
- If unintentional, use `-Djdk.instrument.traceUsage` to trace instrumentation usage where appropriate.
- A future JDK release may change the default authorization state.

In JDK 21, this JEP focuses on warnings and migration readiness rather than declaring that all dynamic loading is disabled across every runtime right away.

### 5.5. JDK releases after JDK 21

Do not extrapolate JDK 21 defaults onto every subsequent JDK release. When moving to a newer release:

1. Read the JDK release notes and flag documentation for that **exact JDK version**.
2. Identify the JDK vendor/distribution and update level.
3. Run a controlled agent-loading smoke test if the product relies on dynamic loading.
4. Inspect warnings, exit codes, agent entry points, and application logs.
5. Verify the semantics and support status of `-XX:+EnableDynamicAgentLoading`/`-XX:-EnableDynamicAgentLoading` on that runtime.
6. Never use guesses about when a JEP changes its default as a release criterion.

Mental model table:

| Phase | Key takeaway | Recommended action |
|---|---|---|
| JDK 8 | Attach API and instrumentation exist; legacy JDK layout | Audit `tools.jar` dependencies and internal APIs |
| JDK 9–20 | JPMS reorganizes JDK layout and module access | Verify `jdk.attach`, `java.instrument`, opens/exports, bytecode tools |
| JDK 21 | JEP 451 warns on dynamic agent loading | Identify agent origins and move to startup agents where sensible |
| Post-21 JDKs | Policy may evolve by release and vendor | Verify release notes and real behavior before signing off |

This table summarizes technology milestones, not a guaranteed support matrix across all JVM vendors.

## 6. What does a JEP 451 warning actually indicate?

### 6.1. Not a compilation error

An application can build cleanly, open its HTTP port, and serve requests normally even when the JVM prints the warning. The warning points to an instrumentation mechanism, not necessarily a bug in application source code.

Even so, do not ignore it, because future releases may prevent dynamic-loading workflows from working by default.

### 6.2. Not automatically an active exploit

Many legitimate sources load agents: APMs, profilers, test tools, debuggers, or troubleshooting utilities. A warning appearing in CI while a test framework instruments mocks differs greatly from an unknown agent appearing in production without a change request.

Classify accordingly:

- **Expected and authorized:** agent/version/path is documented in deployment or test plans.
- **Expected but implicit:** a library or test framework self-attaches without explicit governance.
- **Unexpected:** nobody knows who loaded the agent, from which JAR, or why it touches the JVM.

The second category calls for better configuration; the third calls for security/operations investigation.

### 6.3. The warning depends on loading timing, not vendor name

The exact same agent JAR can be loaded via `-javaagent` at startup or via the Attach API while running. JEP 451 distinguishes loading mechanism, not simply "vendor A's agent" vs. "vendor B's agent".

You cannot tell from a library's name alone whether it triggers warnings. Inspect how the library or test tool initializes instrumentation.

### 6.4. Printing the warning does not prove instrumentation succeeded

The warning indicates the JVM entered the warned dynamic-loading path. The agent can still fail if:

- `Agent-Class` or `agentmain` with the right signature is missing.
- Dependencies inside the agent JAR are missing.
- The bytecode transformer fails to recognize class major versions.
- Required `retransform`/`redefine` capabilities are absent.
- Module access is denied.
- The agent throws an exception during initialization.
- Target classes are not modifiable as requested.

Therefore, when troubleshooting, inspect **attach outcomes, agent logs, and actual instrumentation behavior**, not just "WARNING" lines.

## 7. Key JVM flags

### 7.1. `-XX:+EnableDynamicAgentLoading`

On HotSpot/JDK runtimes supporting this flag, specifying:

```shell
java -XX:+EnableDynamicAgentLoading -jar application.jar
```

records an intentional decision allowing dynamic agent loading on the target JVM. Under JDK 21 behavior described by JEP 451, this explicit opt-in also suppresses the dynamic-agent-loading warning.

**Important:** pass the flag to the **target JVM when it starts**. Passing this flag only to the attaching client process does not alter an already-running JVM's policy.

The flag does not load any agent itself. It only controls dynamic-loading permission on supporting runtimes. Agents and tools still need attach permissions and must satisfy all other prerequisites.

### 7.2. `-XX:-EnableDynamicAgentLoading`

The opposing flag:

```shell
java -XX:-EnableDynamicAgentLoading -jar application.jar
```

instructs supporting HotSpot JVMs to reject dynamic agent loading. This is a very useful test setting to **surface early** which libraries or tools still rely on self-attaching agents.

Loading an agent at startup with `-javaagent` follows a separate path from dynamic loading; do not assume this flag disables all instrumentation across all JVMs.

### 7.3. `-XX:+DisableAttachMechanism`

Example:

```shell
java -XX:+DisableAttachMechanism -jar application.jar
```

On supporting HotSpot runtimes, this is a stronger policy affecting the JVM attach mechanism overall and can prevent many serviceability/diagnostic tools from connecting.

Do not use `DisableAttachMechanism` merely to "hide warnings". It can break essential tooling for collecting thread dumps, JVM diagnostics, or investigating production issues. Evaluate operational impact and distinguish it from denying only **dynamic agent loading**.

### 7.4. `-Djdk.instrument.traceUsage`

Diagnostic example:

```shell
java -Djdk.instrument.traceUsage -jar application.jar
```

This system property is cited in JEP 451 warnings to help trace where the Instrumentation API is used on runtimes supporting that diagnostic.

It helps when a library triggers instrumentation indirectly and the team does not yet know which code path participates. However:

- Not every attach attempt is guaranteed to be explained exhaustively by this trace.
- Tracing can increase log volume and affect performance.
- It does **not** grant attach rights or fix incompatibilities.
- Enable it temporarily in controlled environments.

### 7.5. `-Djdk.attach.allowAttachSelf=true`

On certain HotSpot runtimes, a **JVM attaching to its own PID** is restricted unless enabled explicitly:

```shell
java -Djdk.attach.allowAttachSelf=true -jar application.jar
```

This controls **self-attach**, which is separate from dynamic-agent-loading permission and separate from attaching from an external process.

If a library attempts self-attach after enabling this property, it must still pass dynamic-agent policy checks. Never use the self-attach property as a substitute for `-XX:+EnableDynamicAgentLoading`.

### 7.6. Flag comparison table

| Option | Primary purpose | What it does not replace |
|---|---|---|
| `-javaagent:path` | Load Java instrumentation agent at startup | Does not request dynamic attach |
| `-agentlib:name` / `-agentpath:path` | Load native JVMTI agent at startup | Does not replace Java instrumentation JARs |
| `-XX:+EnableDynamicAgentLoading` | Permit dynamic agent loading per supporting runtime policy | Does not load agents automatically or bypass OS permissions |
| `-XX:-EnableDynamicAgentLoading` | Reject dynamic agent loading per runtime policy | Does not necessarily disable every attach utility |
| `-XX:+DisableAttachMechanism` | Disable/restrict attach mechanism on supporting runtimes | Not merely a warning-suppression switch |
| `-Djdk.instrument.traceUsage` | Trace instrumentation usage on supporting runtimes | Does not authorize agent loading |
| `-Djdk.attach.allowAttachSelf=true` | Allow self-attach on runtimes enforcing that restriction | Does not guarantee dynamic loading is allowed |

`-XX` flags are JVM-implementation-specific options. If running a non-HotSpot JVM vendor/implementation or a custom image, verify supported flags and their exact semantics.

## 8. A test scenario distinguishing warnings from blocking

Suppose a target JVM runs an application:

```shell
java -jar application.jar
```

And an authorized administrative tool invokes `VirtualMachine.loadAgent(...)` against the target PID.

### 8.1. On JDK 21 with defaults aligned to JEP 451

When dynamic loading is still permitted by default, the agent can load while the target JVM prints warnings. Check both tool and application to verify `agentmain` actually executed.

### 8.2. Explicitly permitting dynamic loading

Start the target with:

```shell
java -XX:+EnableDynamicAgentLoading -jar application.jar
```

When supported by the runtime and permitted by attach checks, dynamic loading proceeds. On JDK 21, this explicit opt-in also suppresses the corresponding warning.

### 8.3. Testing the denied path

Start the target with:

```shell
java -XX:-EnableDynamicAgentLoading -jar application.jar
```

The attach call requesting Java/JVMTI agent loading can fail. Record the exact exception/message and confirm the application or test suite handles fallback properly.

Do not immediately label an attach tool failure as a JDK bug: the policy was explicitly configured to reject that operation.

### 8.4. Separating "agent loading" from "attach diagnostics"

Some serviceability commands communicate with the JVM via attach without loading a Java/JVMTI agent under JEP 451. Blocking dynamic agent loading does not mean **every** `jcmd` command fails.

Conversely, disabling the Attach Mechanism altogether can prevent attach-based diagnostics from connecting. Verify key operational workflows independently.

## 9. Test framework scenarios: Mockito, Byte Buddy, and inline mocking

### 9.1. Why can unit tests emit warnings even when the app uses no agents?

Some mocking frameworks and bytecode tools use Java instrumentation to mock classes or methods that ordinary proxies struggle to intercept. Without an `Instrumentation` instance supplied at startup, they may fall back to self-attachment or dynamic attach to instrument the test JVM.

Thus, test logs can print agent warnings even though application code never calls `VirtualMachine.attach`.

Common examples involve Mockito/Byte Buddy configurations performing inline instrumentation. Exact behavior varies by library version, plugins, and test settings; never assert that every Mockito version must self-attach.

### 9.2. Identifying what actually loads the agent

Inspect:

- Stack traces or JAR paths inside warnings.
- Resolved test-runtime dependency graphs.
- Versions of Mockito, Byte Buddy, and Byte Buddy agent libraries.
- JUnit/TestNG plugins and build tool settings.
- `jvmArgs` passed to the test JVM.
- Migration documentation for the exact mocking framework version.
- Whether a `-javaagent` is already configured at startup.

If warnings appear **only during tests**, do not rush to add `-XX:+EnableDynamicAgentLoading` to production JVMs. Fix it at the test scope.

### 9.3. Prefer startup agents when supported by the framework

A sustainable fix is supplying the required agent to the test JVM via `-javaagent` instead of letting libraries self-attach at runtime.

Illustrative command form:

```shell
java -javaagent:/opt/test-agents/mock-agent.jar \
     -cp "test-classes:dependencies/*" \
     com.example.RunTests
```

This is an illustrative layout; `mock-agent.jar` is not a mandatory real artifact name for Mockito. Verify with your exact framework **which artifact is published as a Java agent**, its manifest declaration, and its JDK support.

Never pass an arbitrary JAR to `-javaagent` merely because it appears in Mockito/Byte Buddy dependencies.

### 9.4. Gradle: passing the agent to the test JVM

In Gradle builds, test JVMs can configure `jvmArgs` or `jvmArgumentProviders`. Simple example referencing a managed agent JAR location:

```groovy
tasks.withType(Test).configureEach {
    jvmArgs "-javaagent:/opt/test-agents/test-agent.jar"
}
```

This is syntax illustration, not portable config to copy verbatim. In real projects, resolve the agent via dependency configurations or providers, handle Windows/Linux path differences, and avoid hard-coding personal developer paths.

If Gradle defines multiple test tasks, identify which tasks actually need instrumentation—such as unit tests vs. integration tests—so unneeded agents are not attached to every JVM.

### 9.5. Maven Surefire/Failsafe: preserving other JVM arguments

Maven Surefire or Failsafe can configure `argLine` to pass `-javaagent` to the test JVM. However, JaCoCo or other plugins may already modify `argLine`.

If new configuration overwrites `argLine` wholesale, you can accidentally drop code coverage or required JVM flags.

Migration principles:

1. Identify which plugin currently manages `argLine`.
2. Use the value-composition / late-interpolation mechanism supported by the plugin version.
3. Ensure agent paths resolve before the test JVM launches.
4. Avoid placing the test agent onto Maven's main JVM when only the test JVM needs it.
5. Run coverage and mocking together to verify both work.

`-XX:+EnableDynamicAgentLoading` can serve as a controlled temporary step, yet should not remain long-term if the test framework supports startup agent configuration.

### 9.6. Do not silence warnings by filtering logs

A pipeline might filter out `WARNING` lines so CI stays "clean green", yet doing so merely hides a hidden dependency on dynamic instrumentation that can stop working in future releases.

Fix test configuration or pin/upgrade to supported framework versions, and verify with a test confirming mocking still behaves properly when dynamic loading is disallowed.

## 10. APM, profiling, and production observability

### 10.1. APM agents are typically loaded at startup

Service JVM example:

```shell
java -javaagent:/opt/agents/apm-agent.jar \
     -Dservice.name=orders \
     -jar orders-service.jar
```

This makes startup ownership and agent versions straightforward to govern. Some products can attach to running processes, though JDK policies and vendor guidance must be checked.

### 10.2. Dynamic profiling can be a valid operational need

When a production service misbehaves, authorized tooling may need to attach to start a profiler or instrument a subset of code without restarting. Organizations must weigh operational agility against process integrity risks here.

No single choice fits every service:

- High-integrity services can keep dynamic agent loading disabled by default.
- Services needing ad-hoc diagnostics can enable it under tight controls.
- Prefer JFR, thread dumps, heap dumps, or existing metrics when sufficient for diagnosis.
- Some environments require a controlled change/restart workflow to activate an agent.
- Audit who invoked tooling and against which PID.

### 10.3. JFR and diagnostics are not necessarily Java agents

Java Flight Recorder (JFR) is JVM observability configurable through JVM flags or serviceability tools on supporting runtimes. Using it does not automatically imply calling `VirtualMachine.loadAgent` to load a Java instrumentation agent.

Example starting a recording where HotSpot supports it:

```shell
java -XX:StartFlightRecording=filename=service.jfr \
     -jar application.jar
```

On supporting runtimes, `jcmd` provides JFR commands. However, invoking `jcmd` still relies on the Attach Mechanism and process permissions; do not assume JFR has zero environmental prerequisites.

During migration, check whether a tool actually **dynamically loads an agent** or simply sends a diagnostic command to the JVM.

## 11. Java agents vs. JVMTI native agents: OS migration differences

### 11.1. Startup native agents

Example:

```shell
java -agentlib:observe=mode=sample -jar application.jar
```

Or:

```shell
java -agentpath:/opt/agents/libobserve.so \
     -jar application.jar
```

This illustrates syntax, without implying a real `observe` library exists. Native libraries must be built for the matching OS, CPU architecture, and ABI.

### 11.2. Dynamic native agents

The Attach API also provides methods for native agents, such as `loadAgentLibrary` or `loadAgentPath` depending on the case. Dynamic-agent-loading policy can restrict these paths too; Java `-javaagent` is not the sole area to check.

Questions when investigating:

- Is the agent a Java JAR or a native shared library?
- Is it loaded at startup or after startup?
- Which JVMTI capabilities does it require?
- Does the library match the OS, CPU architecture, and libc?
- Is the native symbol entry point valid?
- Are the vendor JVM and supported JVMTI version matched?

### 11.3. Bytecode compatibility differs from native compatibility

A Java agent JAR may contain Java 17 bytecode and run on JDK 21 while its native companion library only supports Linux x86_64. Conversely, a native agent may load cleanly yet encounter differences in JVMTI events or capabilities across JVM versions.

Never try fixing `UnsatisfiedLinkError` with `EnableDynamicAgentLoading`. Those are two separate problem domains.

## 12. Module access, instrumentation, and class transformation limits

### 12.1. Java agents cannot modify every class arbitrarily

`Instrumentation` provides:

```java
boolean isRedefineClassesSupported();
boolean isRetransformClassesSupported();
boolean isModifiableClass(Class<?> type);
```

When using transformers or redefinition, agents must respect class-file and runtime limits. Structural edits such as adding/removing methods or fields or altering class hierarchies are restricted under normal redefinition rules.

Check example:

```java
public static void agentmain(
        String options,
        java.lang.instrument.Instrumentation instrumentation) {

    System.out.println(
        "Retransform supported: "
        + instrumentation.isRetransformClassesSupported()
    );
}
```

Successful agent loading does not guarantee class instrumentation succeeds.

### 12.2. Newer JDKs emit newer class-file versions

When applications move to JDK 21 or 25, compilers can produce class files with newer major versions. Agents relying on older ASM, Byte Buddy, or Javassist releases may fail to parse new formats, breaking bytecode scanning or instrumentation.

Verification steps:

1. Identify class-file major versions of application and libraries.
2. Identify bytecode library versions embedded in the agent.
3. Check release notes for the agent and bytecode library.
4. Run both startup and dynamic-agent tests if both are supported.
5. Verify actual tracing/mocking behavior, not merely successful agent attachment.
6. Record the agent version in release metadata.

### 12.3. JPMS encapsulation is an independent axis

Since JDK 9, the module system governs readability, exports, and opens. An agent or libraries it touches can hit:

```text
java.lang.reflect.InaccessibleObjectException
```

Appropriate remedies include updating agents/frameworks to use supported APIs or granting tightly scoped module access. `Instrumentation.redefineModule` permits adjusting module edges where applicable; startup `--add-opens` can also serve as a controlled measure.

However, **`--add-opens` never turns a JVM rejecting dynamic agent loading into one that allows it**. Separate two questions:

- Was the agent **allowed to load** into the JVM?
- Once loaded, was the agent **permitted to access/instrument** the target classes?

Answering the wrong layer leads teams to keep stacking JVM flags without resolving the error.

### 12.4. Virtual threads and instrumentation

When adopting a JDK with virtual threads, APM or profiling agents may need updates to capture thread context, stack frames, and traces accurately. Dynamic-loading policy is not the only reason older agents behave differently.

When applications use virtual threads, inspect the agent's support matrix and test propagation/tracing directly rather than checking JVM flags alone.

## 13. Security and integrity considerations

### 13.1. Why does the JDK care about dynamic loading?

An agent authorized to transform bytecode and inspect the runtime affects application integrity. If libraries self-attach without explicit operator consent, a running application's behavior can change after startup.

JEP 451 helps operators govern that boundary. It is not a claim that all agents are malicious, rather a requirement that authorization to load agents be explicit.

### 13.2. Agent loading is not a benign operation

An agent can:

- Read heap contents or class metadata per granted APIs.
- Emit instrumentation telemetry potentially containing sensitive data.
- Modify class behavior where permitted.
- Increase CPU, memory, or latency overhead.
- Interfere with startup/classloading and cause deadlocks or crashes if buggy.
- Load native code carrying memory/ABI risks.

Therefore, govern artifact origin, versions, JVM configuration permissions, and audit trails. Agents are part of the software supply chain.

### 13.3. Least privilege and diagnostic readiness

An operational policy might stipulate:

- Allow only approved startup agents in standard production environments.
- Keep dynamic agent loading disabled by default unless needed.
- Restrict PID access and JVM diagnostic interfaces to authorized operators.
- Require change records and time bounds when dynamic loading must be enabled.
- Preserve supported channels for thread dumps/JFR/metrics so incident response stays intact.
- Pass secrets to agents safely rather than hard-coding them on JVM command lines whenever avoidable.

Do not apply `-XX:+DisableAttachMechanism` across every service just to shrink attack surface without evaluating incident response impacts.

### 13.4. JVM flags are not the sole security boundary

OS permissions, container namespaces, service accounts, filesystem permissions, and runtime configuration jointly govern process interaction. Even when a JVM forbids dynamic agent loading, it is not a complete sandbox against an attacker already holding process-owner or higher OS privileges.

Conversely, permitting dynamic loading does not let every local user attach: OS-level access checks still enforce boundaries.

## 14. Docker, Kubernetes, and custom runtime image scenarios

### 14.1. Containers reshape the attach environment

Inside containers, external tools may not see PIDs or process namespaces like on a bare host. `jcmd -l` and attach mechanisms can depend on OS permissions, shared temporary directories, and matching environments.

Common issues:

- Container PID differs from host PID.
- Sidecars do not share a PID namespace.
- Tool user/group does not match the user running Java.
- Security profiles or container policies block system calls.
- Minimal runtime images lack JDK tools or required modules.
- Temporary filesystem mounts or write permissions break attach sockets.
- Target JDK disables dynamic loading by policy.

Do not grant overly broad container privileges just to fix a failing attach tool. Identify exact required capabilities and consider startup instrumentation.

### 14.2. Startup agents inside containers

A clear approach:

```dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY application.jar /app/application.jar
COPY agents/observe-agent.jar /opt/agents/observe-agent.jar
ENTRYPOINT ["java", "-javaagent:/opt/agents/observe-agent.jar", "-jar", "/app/application.jar"]
```

This Dockerfile is illustrative only and omits image digest pinning, non-root users, and supply chain policies. Ensure the agent JAR exists in the build context and matches the runtime.

When application images are not meant to use dynamic attach, startup agents make instrumentation state deterministic from container boot.

### 14.3. Do not assume base images include JDK tools

A JRE-only or `jlink` custom runtime image may lack:

```text
jcmd
jps
javac
jdk.attach
```

Verify each component individually. Diagnostic utilities can run from separate admin images when architecture, permissions, and organizational policy permit.

### 14.4. Kubernetes sidecars and ephemeral containers

A profiler launched from a sidecar or ephemeral container faces two layers of constraints:

1. **Kubernetes/OS:** PID namespace sharing and process access permissions.
2. **JVM:** Attach Mechanism and dynamic-agent-loading policy.

If the sidecar sees the PID yet the JVM forbids agent loading, tweaking namespaces will not fix it. If the JVM permits dynamic loading yet the sidecar lacks OS rights, adding `EnableDynamicAgentLoading` is not enough.

## 15. Diagnosing with system tools

### 15.1. Identifying the target JVM's JDK

Do not infer from `java -version` in an operator's shell if the service runs via a different JVM binary path. Check the service's actual command line, container image, and JDK runtime metadata.

On runtimes permitting attach, a useful command is:

```shell
jcmd <pid> VM.version
```

Replace `<pid>` with the actual PID; this example applies only when `jcmd` is available and interaction is authorized.

### 15.2. Inspecting active JVM flags

```shell
jcmd <pid> VM.flags
```

Or:

```shell
jcmd <pid> VM.command_line
```

These inspect runtimes exposing the serviceability interface. If the JVM disabled the Attach Mechanism, these commands fail. Fall back to startup logs, deployment manifests, or archived configuration records.

### 15.3. Distinguishing "agent present" from "dynamically loaded"

A log showing `premain` ran does not indicate the Attach API was used. A JEP 451 warning typically correlates with dynamic loading. When investigating, look for:

- `-javaagent` in startup arguments.
- `-agentlib`/`-agentpath` in startup arguments.
- Agent logs showing `agentmain`.
- Warning lines naming the agent JAR or native library path.
- Stack traces originating from self-attaching libraries.
- Operator-invoked APM/profiler CLI activity.
- `EnableDynamicAgentLoading` and `DisableAttachMechanism` flags.

Trace source evidence rather than guessing solely from JAR names.

### 15.4. Never print secrets in diagnostics

JVM command lines, system properties, and agent options sometimes carry sensitive values. When sharing logs with vendors or saving CI artifacts, redact tokens, passwords, credentials, and sensitive paths.

## 16. Troubleshooting: common warnings and errors

### 16.1. Warning only; tests still pass

**Symptom:**

```text
WARNING: A Java agent has been loaded dynamically (...)
BUILD SUCCESSFUL
```

**Likely cause:** a mocking/instrumentation library self-attached an agent inside the test JVM on JDK 21 or a runtime enforcing similar policy.

**Resolution:** identify which dependency performs the attach, check release documentation, and prefer startup agent setup in tests when supported. Never copy test flags blindly to production.

### 16.2. Dynamic loading rejected

**Symptom:** attach client reports an agent-loading failure or runtime states dynamic agent loading is disallowed.

**Likely cause:** target JVM passes `-XX:-EnableDynamicAgentLoading` or the release/vendor default changed; permissions/capabilities at another layer may also be missing.

**Resolution:** confirm target runtime version and active flags; decide whether dynamic loading should be permitted. If intentional, configure startup permission explicitly or switch to a startup agent. Never bypass security policies.

### 16.3. `AttachNotSupportedException`

**Symptom:** unable to attach to the target PID.

**Likely cause:** wrong PID, non-JVM or attach-disabled process, mismatched OS user/permissions, isolated container namespace, Attach Mechanism disabled, or missing runtime modules.

**Resolution:** verify PID, runtime, OS permissions, container configuration, and attach support. Separate attach failing **before** agent loading from dynamic-loading policy rejecting an agent load.

### 16.4. `AgentLoadException`

**Symptom:** attach connected, yet `loadAgent` or related loader failed.

**Likely cause:** dynamic loading disallowed by policy, missing agent JAR/native library path, wrong manifest/entry point, or loader error.

**Resolution:** inspect the cause and target JVM logs; check `Agent-Class`, paths, flags, and environment rather than catching and retrying endlessly.

### 16.5. `AgentInitializationException`

**Symptom:** the JVM attempted initializing the agent, yet its entry point or setup logic threw an error.

**Cause:** exception inside `agentmain`, missing dependencies, invalid options, or instrumentation failure.

**Resolution:** inspect agent logs/stack traces and test the agent directly on the target JDK; do not assume a permissions failure.

### 16.6. `ClassNotFoundException` or `NoClassDefFoundError` from the agent

**Cause:** missing dependencies in agent packaging or incorrect classloading/module visibility.

**Resolution:** inspect JAR manifest, runtime classpath/module path, shaded/embedded dependencies, and JDK version. Adding `-XX:+EnableDynamicAgentLoading` does not supply missing classes.

### 16.7. `InaccessibleObjectException` after agent loads

**Cause:** strong encapsulation/JPMS blocked reflective access.

**Resolution:** upgrade the agent/framework or grant tightly scoped module opens per documentation. This is a **post-load access** issue, not a **dynamic-loading permission** issue.

### 16.8. Errors parsing newer class-file versions

**Symptom:** bytecode transformer reports unsupported class-file major version, skips classes, or fails tests after JDK upgrade.

**Cause:** ASM/Byte Buddy/Javassist/agent is too old for the target bytecode version.

**Resolution:** upgrade agents and bytecode libraries per the support matrix, run regression tests, and inspect outputs on the target JDK.

### 16.9. Agent loads yet produces no tracing data

**Likely cause:** wrong classloader instrumented, loaded classes not retransformed, misconfigured filters, sampling disabled, network exporter failures, or agent/runtime incompatibility.

**Resolution:** verify capabilities, target class selectors, exporter connectivity, configuration, and runtime metrics. Do not treat "agentmain called" as proof the feature works.

### 16.10. `jcmd` stops working after hardening

**Likely cause:** `-XX:+DisableAttachMechanism` or restricted OS permissions/namespaces.

**Resolution:** review hardening policy and incident response workflows; allowing every dynamic agent load is not required for all diagnostics, yet authorized diagnostic paths must remain functional.

## 17. Choosing a migration strategy

### 17.1. Strategy A: switch to startup agents

Fits cases where agents run consistently for APM, tracing, or test-suite mocking/instrumentation.

Steps:

1. Identify the agent artifact supported by the vendor/framework.
2. Pin the agent version against the target JDK support matrix.
3. Configure `-javaagent` on the JVMs needing it.
4. Remove obsolete self-attach or dynamic-attach paths.
5. Test startup, instrumentation, performance, and shutdown.
6. Verify agent paths exist inside containers and CI runners.
7. Record agent versions, options, and ownership in release metadata.

Advantage: instrumentation authorization is explicit in startup configuration.

### 17.2. Strategy B: retain controlled dynamic loading

Fits cases genuinely requiring attachment to running JVMs during incident troubleshooting.

Steps:

1. Verify the target JDK release/vendor supports dynamic loading.
2. Decide whether to enable explicit `EnableDynamicAgentLoading`.
3. Restrict OS permissions and tool access.
4. Govern approved agent binaries and versions.
5. Audit attach events/commands where infrastructure supports it.
6. Test in staging under production-equivalent policies.
7. Maintain an alternative plan if future JDKs alter defaults or remove prior behavior.

Do not enable the permission fleet-wide when only one subset of services needs dynamic loading.

### 17.3. Strategy C: replace with built-in observability

If the agent only collects metrics or diagnostics, evaluate:

- JFR and JDK-supported diagnostic commands.
- Metrics already exposed via application endpoints.
- Structured logging and source-instrumented distributed tracing.
- Async profiling/monitoring tools verified on the JDK without needing the same dynamic agent loading.
- Heap/thread dumps through supported administrative mechanisms.

Not every agent capability has an equivalent built-in substitute. Evaluate data fidelity, overhead, and actual access needs.

### 17.4. Strategy D: keep libraries/frameworks on supported releases

When an old library self-attaches due to age, check before adding long-term JVM workarounds:

- Does a newer library release support JEP 451 or the target JDK?
- Is there an official startup-agent configuration guide?
- Did the newer version alter its mocking/profiling mechanism?
- Does the build plugin provide options to supply `-javaagent` automatically?
- Can unnecessary instrumentation features be turned off temporarily?

Workarounds help during urgent releases, provided each carries an owner and technical-debt payoff plan.

## 18. Step-by-step practical migration workflow

### Phase 1: Inventory agents and attach paths

Search repositories and configuration for:

```text
-javaagent
-agentlib
-agentpath
EnableDynamicAgentLoading
DisableAttachMechanism
jdk.attach.allowAttachSelf
jdk.instrument.traceUsage
VirtualMachine.attach
loadAgent
loadAgentLibrary
loadAgentPath
ByteBuddyAgent
Mockito
java.instrument
jdk.attach
```

Initial ripgrep queries:

```shell
rg -n "javaagent|agentlib|agentpath|EnableDynamicAgentLoading" .
rg -n "VirtualMachine[.]attach|loadAgent|ByteBuddyAgent" .
rg -n "Mockito|mockito|byte-buddy|jacoco|apm" .
```

Note that agent loading configuration may live outside the source repo in CI pipelines, service units, Helm charts, container entrypoints, or vendor launchers. Source searches alone are incomplete inventories.

### Phase 2: Classify every agent

| Agent | Environment | Loading mode | Owner | Required? | Recommendation |
|---|---|---|---|---|---|
| Unit-test mocking | CI | Self-attach may occur | Dev team | Per test features | Prefer startup test agent where supported |
| APM | Production | Startup `-javaagent` | SRE | Yes | Keep startup, upgrade per JDK |
| Incident profiler | Staging/production | Attach on demand | SRE/Platform | Per incidents | Controlled dynamic loading rights |
| Native monitoring | Production | `-agentlib`/dynamic JVMTI | Platform | As needed | Verify native ABI and JVMTI |
| Legacy helper | Build/CI | Unclear | Build team | Needs verification | Trace and remove if obsolete |

This table is a template example. Fill in your system's actual agent versions, paths, and runtimes.

### Phase 3: Capture the baseline

Record:

- JDK vendor, release, and update level.
- Framework, test tool, and agent versions.
- Startup JVM flags.
- OS/architecture and container image digests.
- Loading modes: startup, external attach, self-attach.
- Active warnings or exceptions.
- Real instrumentation feature test results.
- Performance and startup-time impact.

This baseline isolates whether behavioral shifts stem from JDK policy, agent versions, or deployment settings.

### Phase 4: Test restrictive mode early

On a supporting HotSpot runtime, run tests with:

```shell
java -XX:-EnableDynamicAgentLoading ...
```

This simulates an environment disallowing dynamic agent loading while still letting explicitly declared startup agents operate under policy.

If tests fail:

1. Identify which code/tool attempts attaching.
2. Check whether it is a genuine requirement or hidden library behavior.
3. Configure a supported startup agent option.
4. Confirm coverage, mocking, and tracing remain intact.
5. Update CI and deployment documentation.

Note that this **tests dynamic-loading permissions**, not overall functional QA or every JVM feature.

### Phase 5: Test on the target JDK

Run a matrix:

```text
Old JDK + old agent              -> baseline
New JDK + old agent              -> defect detection
New JDK + new agent              -> candidate
New JDK + startup agent          -> primary option
New JDK + dynamic loading off    -> check implicit dependencies
New JDK + dynamic loading on     -> check administrative use case
```

Not every application needs to run every row if no agents are used. Whenever agents or JVMTI tools participate in the stack, verify the actual loading path.

### Phase 6: Release and operations

- Put agent configs into deployment-as-code.
- Pin agent versions and verify provenance.
- Separate test-only flags from production flags.
- Never hard-code personal workstation JAR paths.
- Scope dynamic-attach allowances/restrictions by environment.
- Preserve diagnostic channels for SRE incident response.
- Monitor logs for agent warnings and initialization errors.
- Keep rollback ready if an agent degrades performance or crashes processes.

## 19. Verification in CI and test suites

### 19.1. Minimum matrix

| Scenario | Objective |
|---|---|
| Test JVM on current JDK | Baseline framework instrumentation |
| Test JVM on target JDK | Surface new warnings/exceptions |
| Target JDK + startup agent | Confirm path independent of dynamic attach |
| Target JDK + dynamic loading disabled | Catch overlooked self-attach paths |
| Production-like startup | Verify agent arguments, images, and permissions |
| Agent functionality tests | Test actual agent features, not merely "process ran" |

### 19.2. Actually test instrumentation behavior

If an agent exists for inline mocking, a test running `assertTrue(true)` does not verify mocking works.

If an agent is an APM, smoke tests should verify traces/spans emit cleanly across an HTTP request; for profilers, verify authorized tooling retrieves valid samples.

Not every agent needs a huge integration suite, yet at least one test must exercise the **capability that justifies the agent's presence**.

### 19.3. Failures must report clear causes

A clean test harness should distinguish:

```text
ATTACH_UNAVAILABLE
DYNAMIC_AGENT_LOADING_DISABLED
AGENT_JAR_NOT_FOUND
AGENT_ENTRYPOINT_INVALID
AGENT_INITIALIZATION_FAILED
BYTECODE_TRANSFORM_FAILED
MODULE_ACCESS_DENIED
INSTRUMENTATION_FEATURE_FAILED
```

These are suggested diagnostic labels, not standard JVM error codes. Separating them prevents misapplied workarounds such as adding `--add-opens` when dynamic loading itself was rejected.

### 19.4. Never blindly inject startup flags globally across all processes

If test frameworks need an agent, configure the **test JVM**. If production APM needs a startup agent, configure the **service JVM**. Never set system-wide `JAVA_TOOL_OPTIONS` arbitrarily, as it injects agents into compilers, build tools, CLI utilities, and unrelated JVMs in the same environment.

## 20. Safe triage when warnings appear in production

A concise response workflow:

1. Record timestamp, service/PID/container, and JDK runtime.
2. Save warning output with paths redacted where sensitive.
3. Check whether the agent appears on the approved artifacts list.
4. Identify whether attach was triggered by an operator, profiler, or library.
5. Inspect startup flags and dynamic-loading policies.
6. Confirm whether the agent instrumented properly and caused abnormal overhead.
7. If unauthorized, follow incident response procedures and tighten permissions.
8. If authorized yet undocumented, update deployment configs and runbooks.
9. Plan replacing self-attach with startup agents or equivalents where supported.
10. Re-test on the target JDK release before rolling out.

Never assume "an attacker is present" solely because a warning printed. Equally, never dismiss an unknown agent thinking "all libraries just self-attach".

## 21. Common migration mistakes to avoid

### 21.1. Thinking JDK 21 banned all agents

Conceptually false. JEP 451 warns about and prepares to restrict **dynamic loading**. Explicitly declared startup agents remain a separate supported mechanism.

### 21.2. Assuming every warning is a runtime failure

Not necessarily. An agent may work normally while relying on a path the JVM now flags so operators know about it.

### 21.3. Enabling `EnableDynamicAgentLoading` merely to quiet logs

If an application has no operational need for dynamic loading, permitting it just to silence warnings widens privileges without removing hidden library behavior. Trace the source and consider startup agents.

### 21.4. Applying `DisableAttachMechanism` without consulting SRE

Disabling attach altogether can break vital diagnostic utilities. That is an operations/security decision, not a casual build-flag tweak.

### 21.5. Confusing self-attach with external attach

`jdk.attach.allowAttachSelf` governs self-attachment on supporting runtimes; it neither overrides dynamic-loading policy nor changes permissions for external tools.

### 21.6. Adding `--add-opens` when attach fails

Module opens unlock reflective access after code loads. They cannot authorize an operation blocked at the agent-loading layer.

### 21.7. Upgrading the JDK while keeping old agent binaries unchanged

Bytecode libraries, native JVMTI, instrumentation rules, and JVM internals change across versions. Always check agent support matrices for the target JDK.

### 21.8. Letting test frameworks self-attach unnoticed

When moving tests onto a newer JDK, hidden self-attachment can turn into a blocker. Pin tool versions and configure startup agents when supported.

### 21.9. Treating developer-laptop runs as proof for production

Container/JRE images, OS permissions, PID namespaces, JDK vendors, and startup flags differ. Test close to actual production conditions.

### 21.10. Guessing future JDK policies from warning text alone

JEPs describe staged evolution. Base release decisions on **target JDK** release notes and observed behavior, not guesses about "in a future release".

## 22. Migration checklist

### Agent inventory

- [ ] Inventoried all Java agents, JVMTI native agents, and all loading mechanisms.
- [ ] Distinguished startup `premain` from dynamic `agentmain`.
- [ ] Identified whether each agent comes from the app, test framework, APM, or operators.
- [ ] Recorded agent versions, artifact origins, and owners.
- [ ] Removed or accounted for any self-attaching agents without clear ownership.

### JDK version and permissions

- [ ] Verified the target JVM's exact JDK/vendor/update level.
- [ ] Reviewed release notes for the target JDK's dynamic-agent-loading policy.
- [ ] Tested `EnableDynamicAgentLoading` flags on applicable runtimes.
- [ ] Distinguished `DisableAttachMechanism` from dynamic-agent-loading permissions.
- [ ] Checked self-attach requirements if used by the product.
- [ ] Verified OS/container/PID namespace/permission constraints.
- [ ] Verified custom runtime images include required modules and utilities.

### Agent compatibility

- [ ] Verified agent JAR manifests specify `Premain-Class`/`Agent-Class` for intended modes.
- [ ] Confirmed agent support matrices cover target JDKs and class-file versions.
- [ ] Upgraded bytecode libraries and native companions accordingly.
- [ ] Scoped JPMS access/opens strictly as required.
- [ ] Verified real instrumentation functionality with dedicated tests.
- [ ] Measured performance, memory, and startup impact.

### Build, CI, and deployment

- [ ] Kept test JVM and production JVM agent configurations separate.
- [ ] Tested with dynamic loading disabled when long-term compatibility matters.
- [ ] Switched to startup agents where supported by frameworks.
- [ ] Verified JaCoCo/test-runner JVM arguments are not inadvertently overwritten.
- [ ] Validated CI runs on the exact target JDK runtime.
- [ ] Pinned agent artifacts and flags in deployment-as-code.
- [ ] Updated logging and runbooks for warnings, attach failures, and agent errors.
- [ ] Prepared rollback plans and SRE diagnostic procedures.

## 23. Practice exercises

### Exercise 1: Warnings from a test library

A Mockito/Byte Buddy test suite runs fine on JDK 17 yet prints dynamic-agent-loading warnings after moving to JDK 21.

Determine:

1. Which library loads the agent and through which path?
2. Why does the warning appear even though tests do not fail?
3. Does the library support supplying the agent at test JVM startup?
4. How can you test with `EnableDynamicAgentLoading` disabled?
5. How do you keep test-only flags out of production?

### Exercise 2: APM and production policy

A Java 21 service loads an APM agent via `-javaagent`, while SRE teams occasionally attach a profiler during incidents.

Design:

- Policy for the startup APM agent.
- Policy for the dynamic profiler agent.
- Required OS permissions and JVM flags.
- `jcmd`/JFR capabilities that must stay working.
- Audit trail and runbook for handling warnings.
- Fallback options if a target JDK disallows dynamic attach by default.

### Exercise 3: Triaging attach failures

Staging shows three failures:

```text
Case A: AttachNotSupportedException
Case B: AgentLoadException after connecting
Case C: InaccessibleObjectException during instrumentation
```

Identify which layer each failure belongs to, what diagnostics to capture, and why adding `--add-opens` will not resolve all three.

### Exercise 4: Containers with minimal runtimes

A Java application runs inside a custom `jlink` image. Operations wants to use the Attach API from an external utility.

Verify:

- Does the utility's runtime image include `jdk.attach`?
- Does the target JVM expose attach mechanisms and permit dynamic loading?
- Do container PID namespaces and OS permissions allow connecting?
- Are JFR or metrics alternatives viable?
- Do agent JARs/native libraries match OS, architecture, and JDK?

### Exercise 5: Building a JDK upgrade matrix

Create a table covering JDK 17, JDK 21, and your organization's target JDK with columns:

```text
JDK vendor/update
Startup agent support
Dynamic agent loading policy
Self-attach policy
Container/OS constraints
Instrumentation feature test
Release notes evidence
Owner/decision
```

Never mark a new JDK as "supported" before gathering official evidence and running tests on the real runtime.

## Conclusion

Java agents are essential mechanisms for observability, profiling, testing, and instrumentation, yet **loading agents after JVM startup** demands process-integrity controls. JEP 451 introduced warnings for dynamic agent loading in JDK 21 to prepare for stricter future defaults. Warnings do not automatically break applications, do not mean all Java agents are banned, and do not substitute for testing behavior on your exact JDK and vendor.

For durable migrations, identify who loads each agent and when, distinguish `-javaagent`/`premain` from Attach API/`agentmain`, manage `EnableDynamicAgentLoading` on the target JVM, separate self-attach errors from module-access errors, upgrade agents alongside bytecode/native dependencies, and verify on real artifacts and runtimes. When an agent is required routinely, prefer explicitly declared startup configuration; when dynamic attach is needed operationally, retain intentional authorization, auditing, scoped permissions, and diagnostic alternatives.
