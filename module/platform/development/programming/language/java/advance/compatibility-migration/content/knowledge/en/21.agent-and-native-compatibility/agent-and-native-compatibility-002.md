# Startup Java Agents vs. Agents Attached to Running Processes

## 1. Why Are Java Agents Important in Migration?

When upgrading the JDK, a Java application may compile cleanly yet fail to boot, lose tracing data, or encounter bytecode-related errors in production. Sometimes the root cause lies not in business code, but in a **Java agent**: a component loaded into the JVM to observe or transform classes during startup or runtime.

Java agents frequently appear in:

- Application Performance Monitoring (APM), distributed tracing, metrics, and profiling.
- Unit/integration tests, code coverage, or mocking tools requiring instrumentation.
- Bug-detection tools, method-call tracers, and runtime diagnostics.
- Certain bytecode enhancement frameworks or operational tooling.
- Long-running systems needing additional observability in authorized scenarios.

An easy point to miss is that agents need not appear in the application's dependency list. Infrastructure may inject them via `-javaagent`, `JAVA_TOOL_OPTIONS`, container entrypoints, Java test runners, or a separate attach utility. Consequently, within **Java Advance Compatibility Migration — Agents and Native Code**, treat every agent as a **runtime dependency capable of altering process behavior**, never as an optional accessory.

Two modes exist for using a Java instrumentation agent:

1. **Loaded at startup:** the JVM launches with `-javaagent:<agent.jar>[=<options>]` and invokes `premain` before `main`.
2. **Dynamically attached to a running JVM:** a controller uses the **Attach API** to ask the target JVM to load the agent JAR and invoke `agentmain`.

Both modes share the Java Instrumentation API yet differ in timing, operational privileges, impact on already-loaded classes, and security policies in newer JDK releases.

## 2. Distinguishing Java Agents, Native JVMTI Agents, and Management Tools

The term *agent* covers multiple categories of software. During migration, identify them accurately:

| Technology | Form | Primary Component | Purpose |
| --- | --- | --- | --- |
| Java instrumentation agent | `-javaagent` or Attach API `loadAgent` | JAR, `java.lang.instrument` | Class transformers, APM, testing |
| Native JVMTI agent | `-agentlib`, `-agentpath`, or matching native load mechanism | Shared library, JVM Tool Interface | Low-level debugging/profiling and JVM events |
| Java Flight Recorder (JFR) | Recording APIs and tools | Built-in JVM event recorder | Performance diagnostics and observability |
| JMX / management | Management APIs | MBeans, management interfaces | Monitoring and runtime state management |
| App-level logging/metrics/tracing | Libraries compiled into code | Application APIs/SDKs | Observability at business boundaries |

**`-javaagent` is not `-agentlib`.** The former uses a JAR with a Java entry point; the latter loads a native shared library carrying distinct requirements for OS, CPU, ABI, and JVMTI.

Not every observability need calls for attaching an agent. If you only need GC, CPU, thread states, or built-in events, JFR/JMX and JVM-vendor-supported tools can be simpler and lower-risk. Agents fit cases requiring class-loading interception or fine-grained instrumentation those tools cannot supply.

## 3. How Do the Two Java Agent Loading Modes Differ?

| Criterion | Startup Agent | Dynamic Agent |
| --- | --- | --- |
| How invoked | JVM option `-javaagent` | Attach API from an authorized tool |
| Entry point | `premain` | `agentmain` |
| Timing | Before application `main` runs | While target JVM is already running |
| Classes loaded before agent | Typically fewer | Potentially very many |
| Instrumenting new classes | Transformer registers in time before class load | Instruments classes loaded after registration |
| Instrumenting loaded classes | May need retransform/redefine | Usually needs retransform/redefine to modify loaded code |
| Operations | Declared at startup/deployment | Privileged operational action requiring audit |
| Load failure | Can prevent the JVM from booting | Attach/load call fails; assess impact on target |
| JDK policy | Startup option declared up front | Subject to additional dynamic-loading policies |
| Rollback | Adjust deployment config and restart | No general equivalent to `detach` that unloads the agent |

An agent loads **inside the exact same JVM as the application**. It can execute code, spawn threads, allocate memory, install transformers, reshape class definitions, and add overhead. Never treat an agent as a completely isolated observer process.

### 3.1. Timing Differences Can Alter Outcomes

A startup tracing agent can register its transformer before the HTTP server and JDBC driver load. If attached late after those classes are already defined, the agent does not automatically instrument them retroactively. The agent must explicitly process already-loaded classes using supported capabilities; otherwise both modes may report differing coverage despite logging “agent loaded.”

## 4. What APIs Does `java.lang.instrument` Provide?

Core abstractions:

- `Instrumentation`: handle supplied by the JVM to register transformers, inspect loaded classes, and request retransformation/redefinition where supported.
- `ClassFileTransformer`: callback invoked whenever a class is defined or reprocessed under instrumentation.
- `ClassDefinition`: pairs a class with replacement bytecode for redefinition.
- Manifest attributes: declare entry points and capabilities of the agent JAR.
- `premain` / `agentmain`: entry points for startup vs dynamic loading.

Startup flow:

~~~text
Java launcher
    |
    | -javaagent:/path/agent.jar
    v
JVM reads agent manifest
    |
    v
Agent.premain(...)
    |
    v
Register ClassFileTransformer
    |
    v
Application.main(...)
    |
    v
Application classes loaded / methods executed
~~~

Attach flow:

~~~text
Target JVM is already running
          |
Authorized controller
          |
          v
VirtualMachine.attach(pid)
          |
VirtualMachine.loadAgent(jar, options)
          |
          v
Target JVM invokes agentmain(...)
          |
          v
Transformer registered
          |
New loads / optional retransformation
~~~

The JVM creates no bytecode transformer unless an agent registers one. Returning `null` from a transformer merely inspects or skips the class bytes without modifying bytecode.

## 5. Manifest of a Java Agent JAR

Example `agent-manifest.mf`:

~~~text
Manifest-Version: 1.0
Premain-Class: example.agent.DemoAgent
Agent-Class: example.agent.DemoAgent
Can-Redefine-Classes: true
Can-Retransform-Classes: true
~~~

| Attribute | Meaning |
| --- | --- |
| `Premain-Class` | Class declaring the startup `premain` method |
| `Agent-Class` | Class declaring the dynamic attach `agentmain` method |
| `Can-Redefine-Classes` | Requests capability to redefine classes |
| `Can-Retransform-Classes` | Requests capability to retransform classes |
| `Can-Set-Native-Method-Prefix` | Advanced capability for native method prefixes |

Do not request capabilities an agent does not use. Nor do `Can-*` attributes guarantee support across every JVM. Agent code must check `Instrumentation.isRetransformClassesSupported()`, `isRedefineClassesSupported()`, and `isModifiableClass(...)` before invoking advanced operations.

An executable JAR's `Main-Class` **does not substitute** for `Premain-Class` or `Agent-Class`. An application JAR with `Main-Class` does not automatically become a Java agent.

### 5.1. Entry Points Must Have Valid Signatures

With `Instrumentation`:

~~~java
public static void premain(
        String arguments,
        Instrumentation instrumentation) {
    // Startup path
}

public static void agentmain(
        String arguments,
        Instrumentation instrumentation) {
    // Dynamic attach path
}
~~~

The Java Instrumentation API also defines single-argument `String` overloads under specified conditions. For agents that register transformers, use the two-argument signature to receive `Instrumentation` explicitly.

## 6. Complete Example: Java Agent Supporting Both Modes

This snippet logs lifecycle details only and **does not alter bytecode**:

~~~java
package example.agent;

import java.lang.instrument.Instrumentation;

public final class DemoAgent {
    private DemoAgent() {}

    public static void premain(
            String args, Instrumentation inst) {
        start("startup", args, inst);
    }

    public static void agentmain(
            String args, Instrumentation inst) {
        start("dynamic", args, inst);
    }

    private static void start(
            String mode, String args, Instrumentation inst) {
        System.err.println(
                "[demo-agent] mode=" + mode
                + ", args=" + args
                + ", canRetransform="
                + inst.isRetransformClassesSupported());
    }
}
~~~

Printing `args` illustrates passing options. In real products, **never log options verbatim** if they contain secrets, tokens, sensitive hosts, or PII; parse and redact them.

Suppose source files live at:

~~~text
src/agent/java/example/agent/DemoAgent.java
src/agent/agent-manifest.mf
src/app/java/example/app/Main.java
~~~

Example JAR build commands using JDK tools:

~~~bash
javac -d build/agent-classes \
  src/agent/java/example/agent/DemoAgent.java

jar --create \
  --file build/demo-agent.jar \
  --manifest src/agent/agent-manifest.mf \
  -C build/agent-classes .
~~~

In real Maven/Gradle builds, use agent-packaging tasks/plugins and pin build tool versions. Verify that the output JAR includes `META-INF/MANIFEST.MF` properly, contains the entry-point class, and bundles required agent libraries.

### 6.1. Verify the Manifest

The manifest must name the exact fully qualified class. If the package is `example.agent` while the manifest writes `DemoAgent`, the JVM fails to load the class. If building a fat/shaded agent JAR, verify shading preserves manifest attributes and dependencies cleanly.

## 7. Using Startup `-javaagent`

Example:

~~~bash
java -javaagent:build/demo-agent.jar=trace \
     -cp build/app-classes example.app.Main
~~~

Or with an executable JAR:

~~~bash
java -javaagent:/opt/agents/demo-agent.jar=trace \
     -jar orders-service.jar
~~~

`-javaagent` is a **JVM option** and must appear among launcher options before the main class or `-jar`. Placed afterward, it becomes an application argument and the JVM ignores it for agent loading.

### 7.1. What Happens Before `main`?

The JVM loads the agent JAR, resolves `Premain-Class`, and runs `premain`. The agent can register transformers early so subsequent class loads pass through its callbacks. If `premain` throws a fatal error or the manifest/JAR is broken, the application fails to start.

Startup agents therefore affect **availability**. Never roll a new agent JAR into production based merely on source compilation passing; smoke-test the exact launcher and runtime image being shipped.

### 7.2. Multiple Startup Agents

~~~bash
java -javaagent:/opt/agents/apm.jar \
     -javaagent:/opt/agents/coverage.jar \
     -jar orders-service.jar
~~~

Startup `premain` methods execute in command-line order. Yet how multiple transformers act on a class also depends on registration/retransformation rules. Two agents working cleanly in isolation can still clash when paired together.

In production, an APM agent and a tracing agent may emit duplicate spans; a coverage agent may rewrite bytecode on classes also enhanced by a framework. Test **the real production agent combination**, not each agent separately.

### 7.3. Startup Args from Environment Variables

Some environments inject JVM flags through:

~~~text
JAVA_TOOL_OPTIONS=-javaagent:/opt/agents/apm-agent.jar
~~~

Startup scripts, Dockerfiles, Helm charts, or platform admission controllers can inject `-javaagent`. Inspect **the actual launched JVM command line**, not only repository build scripts. An agent can end up loaded twice if both a Dockerfile and the platform inject it.

## 8. What Is Dynamic Attach?

Dynamic attach lets an **authorized** tool ask a running JVM to load an agent. It relies on the Attach API in module `jdk.attach` on supporting JDKs.

Characteristics:

- Does not necessarily require restarting the JVM to load an agent where permitted.
- `agentmain` runs after startup; never assume identical state to `premain`.
- Many classes are already loaded, so instrumentation misses them unless the agent triggers retransformation.
- Attach permissions are enforced by OS/JVM/platform policy; it is not an unauthenticated channel.
- Loading an agent is not read-only: it runs arbitrary code inside the target JVM.

Dynamic attach suits authorized diagnostic tasks, not mandatory always-on agents expected from service startup.

## 9. Attach API and `VirtualMachine.loadAgent`

Minimal Java controller:

~~~java
package example.tools;

import com.sun.tools.attach.VirtualMachine;

public final class AttachController {
    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            throw new IllegalArgumentException(
                    "Usage: <pid> <absolute-agent-jar> [options]");
        }

        String pid = args[0];
        String agentJar = args[1];
        String options = args.length >= 3 ? args[2] : "";

        VirtualMachine vm = VirtualMachine.attach(pid);
        try {
            vm.loadAgent(agentJar, options);
        } finally {
            vm.detach();
        }
    }
}
~~~

Run such tools strictly against **authorized JVMs under change-control governance**. Sample PIDs must never target third-party or unverified processes.

Example compile/run commands:

~~~bash
javac --add-modules jdk.attach \
  -d build/attach-classes \
  src/attach/java/example/tools/AttachController.java

java --add-modules jdk.attach \
  -cp build/attach-classes \
  example.tools.AttachController \
  12345 /absolute/path/demo-agent.jar diagnostic
~~~

`12345` is a hypothetical PID. The JAR path must resolve inside the target JVM's filesystem view, and the JAR must declare `Agent-Class` with a valid `agentmain` method.

### 9.1. `detach()` Does Not Unload the Agent

`VirtualMachine.detach()` only closes the controller's connection to the target JVM. It does not remove the loaded agent, unregister transformers, or revert bytecode transformations. If an agent needs deactivation, design dedicated lifecycle/cleanup switches and respect API limits—there is no universal “unload Java agent JAR from JVM” operation.

### 9.2. Common Attach API Errors

| Error | What to Check |
| --- | --- |
| `AttachNotSupportedException` | Whether the target JVM supports attach and has it enabled |
| `IOException` | Attach IPC socket, target process state, paths, and environment |
| `AgentLoadException` | JAR visibility, manifest, and agent loading eligibility |
| `AgentInitializationException` | Failure inside `agentmain` or agent initialization |
| OS / security permission errors | Whether the controller holds valid privileges for the target |

Never change permissions blindly to “fix” errors. Confirm operational policies, process ownership, container namespaces, and approved privileges.

## 10. Conditions and Limits of the Attach Mechanism

Not every JVM or deployment permits dynamic attach. Governing factors include:

1. JVM implementation/vendor and JDK release.
2. OS user, process privileges, and platform attach mechanics.
3. PID namespaces, mount namespaces, and container isolation.
4. Runtime image contents and installed modules/tools.
5. JVM flags such as `-XX:+DisableAttachMechanism` on supporting HotSpot runtimes.
6. Explicit policies regarding **dynamic agent loading**.
7. Whether managed/cloud infrastructure allows attach.

On supporting HotSpot JVMs, this flag:

~~~text
-XX:+DisableAttachMechanism
~~~

disables the attach mechanism. It is set at target JVM launch; controllers cannot reverse it once the process is running.

### 10.1. Self-Attach Has Separate Rules

A process attaching to its own JVM is **self-attach**, distinct from an authorized external controller attaching from another process. Certain JDK releases/implementations restrict self-attach by default and control it via properties like `jdk.attach.allowAttachSelf`.

Do not treat:

~~~text
-Djdk.attach.allowAttachSelf=true
~~~

as a default fix for test instrumentation errors. Check whether the tool documents a startup `-javaagent` mode and whether your target JDK permits dynamic loading under approved configuration.

## 11. JDK 21: Dynamic Agent Loading Warnings from JEP 451

**JEP 451** shipped in JDK 21 to prepare for tighter restrictions on dynamic agent loading. On applicable HotSpot JVMs, loading a Java agent dynamically prints a warning similar to:

~~~text
WARNING: A Java agent has been loaded dynamically
WARNING: Dynamic loading of agents will be disallowed
         by default in a future release
~~~

Core message: runtimes expect **explicit consent from the application owner** before loading agent code after JVM startup. Passing startup `-javaagent` differs because the agent is declared upfront at launch.

Flags commonly mentioned in docs for applicable releases:

~~~text
-XX:+EnableDynamicAgentLoading
-XX:-EnableDynamicAgentLoading
~~~

Per JEP 451, enabling dynamic loading explicitly on supporting runtimes suppresses warnings, while disabling it lets teams test strict restriction impact. However, **exact defaults and operational behavior must be verified against your specific JDK vendor/release** rather than assuming identical defaults across every post-21 JDK.

### 11.1. Distinguish Attach Access from Agent Loading Permission

The Attach API supports multiple administrative commands. Permission to attach **does not guarantee** permission to load an agent dynamically. A JVM may permit certain diagnostic commands while blocking `loadAgent` per policy.

Never assume `jcmd` listing a PID proves `VirtualMachine.loadAgent` will succeed.

### 11.2. Do Not Suppress Warnings Before Identifying the Source

If tests on JDK 21+ print this warning, trace which library is self-attaching: mocking, coverage, bytecode agent, or profiler. If the vendor supports a startup agent, switching to `-javaagent` per documentation reduces reliance on dynamic loading.

Never add `-XX:+EnableDynamicAgentLoading` globally in production just to silence console warnings from a test library.

## 12. Before vs. After Class Loading: Timing Consequences

Under normal conditions, the JVM defines a Java class once per classloader/identity. When a transformer registers before class loading, it intercepts the class definition step directly.

Conversely, when an agent attaches to an already-running JVM:

- Many application, framework, and driver classes are already loaded.
- Newly registered transformers affect classes loaded/processed afterward.
- Updating already-loaded classes requires JVM-supported **retransformation** or **redefinition**.
- Some classes are non-modifiable, or structural edits exceed JVM limits.

For example, an APM agent attached after an HTTP server begins serving traffic may fail to instrument core servlet/driver classes unless it retransforms them. The service runs and logs “agent loaded,” yet traces remain incomplete.

**Operational takeaway:** Agent loading cleanly and agent instrumenting every business path are **two separate assertions to verify**.

## 13. `ClassFileTransformer`: Example Observing Class Names

A transformer receives the classloader, internal class name, redefinition handle, and raw bytecode. Example printing names of one application package:

~~~java
package example.agent;

import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

public final class NameObserver implements ClassFileTransformer {
    @Override
    public byte[] transform(
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {
        if (className != null
                && className.startsWith("example/app/")) {
            System.err.println("[agent] class=" + className);
        }
        return null; // Do not modify bytecode.
    }
}
~~~

Registration:

~~~java
instrumentation.addTransformer(new NameObserver());
~~~

This snippet uses the classic `transform` overload; modern JDKs also define an overload receiving `Module`. Production agents must handle modern APIs, module boundaries, and classloader strategies cleanly.

### 13.1. Why Return `null`?

In `ClassFileTransformer`, returning `null` signals no bytecode changes are requested. To actually instrument code, the transformer must generate valid bytecode and return the updated byte array. Never patch raw byte arrays manually without thorough mastery of JVM class-file formats, stack map frames, and bytecode verification.

For non-trivial instrumentation, projects rely on ASM, Byte Buddy, or supported bytecode tools. Crucially, that bytecode library itself must support the target JDK's class-file version.

### 13.2. Avoid Causing Issues on the Class-Loading Path

Transformers execute inside a sensitive path:

- Avoid blocking I/O or logging every loaded class.
- Avoid inadvertent recursive class loading via helper classes.
- Minimize allocations and memory overhead.
- Never retain strong references pinning every classloader indefinitely.
- Design carefully for exceptions, concurrency, and reentrancy.
- Test emitted bytecode under multi-classloader and modular setups.

Even a “logging-only” agent can severely hurt performance if synchronous I/O runs on every class load.

## 14. Retransformation and Redefinition

Two advanced `Instrumentation` features:

**Retransformation:** asks the JVM to reprocess an already-loaded class through supporting transformers. **Redefinition:** supplies replacement class bytes directly for an already-loaded class.

Neither mechanism acts as **unrestricted hot reload for arbitrary Java edits**. Adding/removing fields, altering inheritance hierarchies, changing method signatures, or altering other class structures typically violates JVM constraints.

Capability check example:

~~~java
if (instrumentation.isRetransformClassesSupported()
        && instrumentation.isModifiableClass(targetClass)) {
    instrumentation.retransformClasses(targetClass);
}
~~~

`targetClass` represents a deliberately chosen class. Never trigger retransformation across all loaded classes indiscriminately, as doing so adds heavy overhead, hits unmodifiable classes, or triggers concurrency surprises.

### 14.1. Registering a Retransform-Capable Transformer

When declared in the manifest and supported by the runtime:

~~~java
if (instrumentation.isRetransformClassesSupported()) {
    instrumentation.addTransformer(
            new NameObserver(),
            true);
}
~~~

This registers an observer-only transformer without emitting updated bytecode. Actually modifying behavior requires returning valid transformed class-file bytes while respecting JVM constraints.

### 14.2. Do Not Assume Active Stack Frames Switch Behavior Immediately

Retransformation does not rewind calls currently executing on thread stacks. The JVM enforces strict rules around active stack frames and redefined methods. Never use dynamic agent patching to fix live business logic in production without proper concurrency/state analysis and full testing.

## 15. Multiple Agents, Transformers, and Ordering Effects

One JVM may load multiple agents from:

- Startup JVM options.
- Dynamic attach at different points in time.
- Libraries/frameworks registering their own instrumentation.

If both Agent A and Agent B transform a class, bytecode handed to B can include edits applied by A according to transformer chaining rules. During retransformation, special ordering rules apply too. Never infer combined behavior from testing agents one by one.

Risks include:

- Duplicate traces or inflated metrics.
- Conflicting transformations causing `VerifyError`.
- Helper classes loaded by wrong classloaders.
- Agent A bundling a conflicting bytecode library version vs Agent B.
- Resource overhead exceeding expected combined sum.
- Startup order shifts changing class-loading timing.

During migration, test **real agent combinations** and verify observability outputs, not merely that the JVM stays alive.

## 16. Java Module System and Agents

Since Java 9, JPMS governs read edges, `exports`, and `opens`. Instrumentation agents may need to:

- Access non-exported packages for reflection or helpers.
- Let injected code resolve types residing in other modules.
- Instrument classes living inside named modules.
- Respect strong encapsulation and JDK internal API policies.

Typical symptoms:

~~~text
java.lang.reflect.InaccessibleObjectException
java.lang.IllegalAccessError
java.lang.NoClassDefFoundError
~~~

An older agent reflecting into JDK internal packages might have run fine earlier yet break on the target JDK.

### 16.1. `Instrumentation.redefineModule`

The Instrumentation API provides `redefineModule(...)` to adjust selected module edges under JVM rules when genuinely required. This is a low-level API; opening packages or adding read edges must remain tightly controlled and documented.

Never blast open every JDK module just because an agent library has not yet added target JDK support. First upgrade to a vendor-certified release.

### 16.2. `--add-opens` Is Only a Scoped Workaround

Syntax example:

~~~text
--add-opens=java.base/java.lang=ALL-UNNAMED
~~~

This is **not** a flag recommended blindly for every service. It grants reflective access under specific conditions yet does not guarantee internal APIs remain present. If temporarily required, document the component, package, owner, rationale, and removal deadline.

## 17. Classloaders and Agent Helper Classes

Bytecode injected into application classes by an agent often calls helper methods:

~~~text
example.agent.TraceHelper.onEnter()
~~~

If the classloader loading the application class cannot see `TraceHelper`, linkage fails. Application servers, OSGi runtimes, or plugin architectures with isolated classloaders complicate visibility further.

`Instrumentation` exposes advanced helpers such as:

~~~java
instrumentation.appendToBootstrapClassLoaderSearch(helperJar);
instrumentation.appendToSystemClassLoaderSearch(helperJar);
~~~

This merely illustrates the API; `helperJar` must be a valid `JarFile` and follows strict class-loading rules. Never invoke these lightly: injecting classes onto bootstrap/system search paths can alter class resolution, package access, and dependency conflicts.

### 17.1. Agent JARs Often Embed Shaded Dependencies

APM agents typically bundle bytecode libraries, config parsers, logging, or exporters. Many shade/relocate dependencies to isolate them from app libraries. Yet shading is not failproof.

When upgrading an agent, inspect:

- Embedded libraries, particularly ASM and Byte Buddy.
- Shading/relocation accuracy and `ServiceLoader` descriptors.
- Module and classloader interactions.
- Bytecode parser capabilities against new class-file major versions.
- Class initialization timing and helper class lifetimes.

## 18. Native JVMTI Agents: Loading Paths and Compatibility

Native agents differ from Java JARs:

~~~bash
java -javaagent:/opt/agents/apm.jar -jar app.jar
java -agentlib:profiler=options -jar app.jar
java -agentpath:/absolute/path/profiler.so=options -jar app.jar
~~~

`profiler.so` and `profiler` are placeholders. On Windows or macOS, shared library extensions and search rules differ.

Native JVMTI agents implement entry points defined by the JVM TI Specification, such as `Agent_OnLoad` at startup plus JVM-dependent late-load hooks. Attach API offers native methods like `loadAgentLibrary`/`loadAgentPath`; Java JAR `loadAgent` is not an equivalent substitute.

### 18.1. Native Migration Imposes Additional Constraints

- Operating system and CPU architecture.
- ABI compatibility, libc, and shared-library dependencies.
- Native binaries bundled in target runtime images.
- JVMTI capabilities and vendor/JDK compatibility.
- Container permissions and filesystem mounts.
- Native memory overhead and crashes outside Java exception handling.

A Java agent JAR running on the target JDK never proves your native profiler works there too.

## 19. Agents in Unit Tests, Mocking, and Code Coverage

Tools such as Mockito, Byte Buddy, JaCoCo, and test frameworks often rely on instrumentation; loading mechanics depend on tool version and configuration. Some tools historically used **dynamic self-attach** during test runs.

When upgrading the JDK, typical signals include:

~~~text
WARNING: A Java agent has been loaded dynamically
~~~

Or bytecode parser failures:

~~~text
Unsupported class file major version 65
~~~

These two symptoms require distinct fixes:

1. **JEP 451 warning:** inspect dynamic-loading mechanics, JDK policy, and vendor docs for startup `-javaagent` support.
2. **Class-file/parser failure:** inspect JDK class-file versions alongside bytecode/agent library versions.

Do not assume a warning immediately equals a failing test, nor assume warnings can simply be ignored forever.

### 19.1. Configuring a Startup Agent for the Test JVM

Gradle Groovy DSL syntax illustration:

~~~groovy
tasks.withType(Test).configureEach {
    jvmArgs '-javaagent:/absolute/path/approved-test-agent.jar'
}
~~~

The actual JAR must declare `Premain-Class` and resolve from an approved tool/dependency version. Never commit placeholder paths to production CI pipelines.

In Maven Surefire/Failsafe, `argLine` passes JVM flags to forked test processes. If JaCoCo or another plugin also populates `argLine`, combine settings properly so plugins do not overwrite each other; exact syntax varies by plugin version.

**Not every mocking/test library JAR is a valid `-javaagent` JAR.** Follow tool-specific documentation rather than guessing modes.

## 20. Dynamic Self-Attach: Path to Migrating to a Startup Agent

Scenario: a test library self-attaches to the JVM on demand. After upgrading to JDK 21, logs print dynamic loading warnings. The team wants to remove reliance on dynamic agent loading going forward.

Migration path:

1. Identify which library self-attaches and which JAR gets loaded.
2. Check whether a supporting startup agent mode exists for that version.
3. Pin the agent dependency and resolve its local path for the test JVM.
4. Configure `-javaagent` on the test process startup command.
5. Verify no duplicate attach occurs if the library still probes dynamically.
6. Re-run unit/integration suites, coverage, mocking behavior, and CI.
7. Remove unnecessary dynamic-loading flags/workarounds.

Conceptual shift:

~~~text
Before:
  Test JVM starts
  Library requests dynamic self-attach
  Agent starts during test execution

After:
  Test JVM starts with a supported -javaagent
  Library reuses instrumentation as documented
~~~

Follow this only when the vendor documents a matching startup agent mode. Never assume every self-attaching library supports a 1:1 replacement.

## 21. APM/Tracing Agents in Production: Where to Inventory?

Agent settings may live inside:

- Application launch scripts.
- Dockerfiles or container entrypoints.
- Kubernetes Deployments / Helm charts.
- `JAVA_TOOL_OPTIONS` or `JDK_JAVA_OPTIONS`.
- Application server configurations.
- Platform injection webhooks or auto-instrumentation operators.

Sample inventory record:

~~~text
Service: orders-service
JDK distribution/version: target-runtime
Agent: vendor-agent
Agent artifact/version/checksum: ...
Mode: startup -javaagent
Injected by: container entrypoint
Configuration: approved config reference, secrets redacted
Capabilities: tracing + JDBC instrumentation
Owner: platform/observability
Known JVM flags: ...
Rollback strategy: ...
~~~

Identify **every agent actually loaded** in each environment. Maven/Gradle dependency trees will not show agents injected at deployment time by platform infrastructure.

### 21.1. Verify More Than Just “Agent Started” Logs

After upgrading JDKs, frameworks, or agents, check:

- Do HTTP, JDBC, and messaging traces still capture full spans?
- Does context propagation work across threads and async tasks?
- Are duplicate spans, altered service names, or changed resource attributes occurring?
- Do error reporting and exception mapping remain accurate?
- Are agent exporter queues, backpressure, or dropped telemetry showing up?
- How did CPU, memory, startup time, and p95/p99 latencies change?

An agent can start cleanly yet quietly drop auto-instrumentation for newer framework releases. That is an operational regression, not “zero errors.”

## 22. Security and Governance When Loading Agents

Java agents execute arbitrary code inside the target JVM. Dynamic attach is therefore a high-privilege operation, not read-only inspection.

Principles:

- Attach strictly to authorized JVMs under your administrative domain.
- Use agent artifacts from trusted sources with verified versions, hashes, and provenance.
- Restrict who can alter startup arguments or invoke the Attach API.
- Never expose endpoints letting arbitrary users upload JARs and attach them to JVMs.
- Protect agent options, credentials, telemetry, and sensitive data.
- Maintain audit trails: who attached, target process, timestamp, artifact, and outcome.
- Maintain resource monitoring, incident playbooks, and rollback procedures.
- Define per-environment allow/deny policies for attach operations.

### 22.1. Agent Bugs Can Crash Applications

Transformers emitting invalid bytecode trigger verification/linkage failures. Agents retaining classloader references leak memory. Agents performing synchronous I/O in load callbacks inflate startup latency. Faulty native agents crash the JVM outright outside Java exception handling.

Never consider an agent “safe” simply because the JVM loaded the JAR. Validate correctness, overhead, and security across trust boundaries.

### 22.2. Production Attach Requires Explicit Authorization

Never use attach to bypass security controls, patch application behavior silently, or extract secrets. If a cloud/managed runtime forbids attach, use startup instrumentation or platform-provided observability mechanisms.

## 23. Containers and Kubernetes: Practical Constraints

Attaching inside containers introduces complications beyond bare-metal hosts:

- Container PIDs differ from host PIDs.
- Controller and target may occupy isolated process namespaces.
- User IDs, file permissions, and filesystem mounts differ.
- The agent JAR path must exist and be readable inside the target JVM's mount namespace.
- Minimal base images may omit `jcmd`, attach tools, or required JDK modules.
- Target JVMs may disable attach explicitly.
- Sidecars do not automatically hold privileges to attach across containers.

**Never assume PID 1 inside a container equals PID 1 on the host**, or that host tools can cross container namespaces without authorization.

For always-on observability in immutable deployments, startup `-javaagent` is far easier to audit and reproduce. Reserve dynamic attach for controlled, authorized diagnostics.

## 24. Checking Agent Compatibility During JDK Upgrades

Record for every agent:

| Verification Dimension | Question |
| --- | --- |
| JDK vendor/release | Does the vendor officially support the target JDK? |
| Class-file support | Does the agent's bytecode engine handle new major versions? |
| Module boundaries | Does the agent touch JDK internals or deep reflection? |
| Framework compatibility | Does the agent support upgraded HTTP/ORM/messaging frameworks? |
| Agent mode | Startup, dynamic, or both; does it require retransformation? |
| Native dependencies | Do JNI/JVMTI/shared libs match the target OS/architecture? |
| Runtime image | Are agent JARs, flags, and classloaders packaged properly? |
| Security policy | Are attach permissions, secrets, auditing, and actions approved? |
| Functional observability | Are traces, spans, metrics, and error records accurate? |
| Performance | Do CPU, memory, startup time, latency, and GC stay within budget? |

An agent JAR compiled with a lower class-file major version than the target JVM **does not prove** compatibility with runtime classes. It may embed an outdated ASM/Byte Buddy, break on altered internal APIs, or lack rules for newer frameworks.

### 24.1. Artifact Inspection Tools

Reference commands:

~~~bash
jar --list --file /opt/agents/monitor.jar

javap -verbose \
  -classpath /opt/agents/monitor.jar \
  example.agent.DemoAgent
~~~

Representative class-file major versions: Java 8 → 52, Java 17 → 61, Java 21 → 65. Checking bytecode levels covers only one dimension and never replaces integration tests.

## 25. Common Diagnostic Matrix

| Symptom | Possible Cause | Investigation Approach |
| --- | --- | --- |
| `Failed to find Premain-Class manifest attribute` | JAR omits startup entry-point header | Inspect manifest |
| `Failed to find Agent-Class manifest attribute` | JAR omits dynamic entry-point header | Check `Agent-Class` |
| `ClassNotFoundException` loading agent | Wrong manifest class name or broken JAR | Verify packages, packaging, classpath |
| `NoClassDefFoundError` during instrumentation | Helper/dependency invisible to app classloader | Check classloaders/modules |
| `UnsupportedClassVersionError` | JVM cannot read agent's class-file version | Match JDK runtime vs compile target |
| `Unsupported class file major version 65` in parser | Tool's ASM/Byte Buddy lacks Java 21 support | Upgrade agent/bytecode engine |
| `InaccessibleObjectException` | Reflection into unopened JDK package | Check agent support, module access |
| `AttachNotSupportedException` | JVM/OS/container blocks attach | Check flags, permissions, namespaces |
| JDK 21 dynamic loading warning | Dynamic agent load; JEP 451 | Identify source, follow vendor guidance |
| `AgentLoadException` | Invalid agent JAR/load request | Check JAR path, manifest, target logs |
| `AgentInitializationException` | `agentmain`/startup init threw exception | Read target JVM logs/root cause |
| Agent logs loaded, spans missing | Classes preloaded, no retransform, or matcher stale | Check timing, capabilities, framework version |
| Duplicate spans | Multiple agents instrumenting same paths | Inventory agents and tracing ownership |
| Slow boot or crash with agent added | Bug in `premain`, transformer, or dependencies | A/B smoke tests and agent logs |
| Native agent fails to load | Missing ABI/architecture/shared lib | Inspect container image and native deps |

Never apply random JVM flags to mask failures. Identify **which component failed first** and in which mode the JVM loads the agent.

## 26. Troubleshooting Startup Agent Failures

1. **Inspect the JVM command line:** verify `-javaagent` appears in JVM options at the proper position.
2. **Verify the JAR:** file exists, checksum matches, manifest declares `Premain-Class`.
3. **Check Java runtime details:** class-file versions, JDK vendor, and included modules.
4. **Read the first exception:** separate entry-point failures from class loading, helper visibility, or transformers.
5. **Test without the agent in an isolated sandbox:** confirm whether the app boots cleanly; use strictly for triage, never to justify disabling production telemetry.
6. **Test a vendor-supported agent release:** avoid overriding embedded ASM/Byte Buddy arbitrarily.
7. **Re-verify observability outputs:** clean startup alone is insufficient if spans/metrics vanish.
8. **Document root cause and config changes:** never leave ownerless module workarounds behind.

## 27. Troubleshooting Dynamic Attach Failures

1. **Verify target PID and authorization** in an approved environment.
2. **Check the target JVM** for attach mechanism support and dynamic-loading policy.
3. **Check the controller JDK** includes `jdk.attach` and matching Attach APIs.
4. **Inspect the manifest:** JAR contains valid `Agent-Class`/`agentmain`.
5. **Read logs from both controller and target JVM.**
6. **Confirm whether loading succeeded yet instrumentation remained incomplete.**
7. **Check preloaded classes and retransform capabilities** where required.
8. **Reproduce in staging** with matching JDK, permissions, and attach timing.
9. **Log audit details and results**; never hammer production with repeated attach retries.

Where policy prohibits attach, **never** disable guardrails as a standard diagnostic reflex. Separate observability requests from runtime-modification requests and adopt approved channels.

## 28. Test Matrix for Startup and Dynamic Modes

| Scenario | JDK | Mode | Verification Goals |
| --- | --- | --- | --- |
| Baseline | Old JDK | Startup | App startup and accurate traces/metrics |
| Baseline dynamic | Old JDK | Attach if permitted | `agentmain` and instrumentation |
| Target startup | Target JDK | Startup | Bytecode, modules, and agent version |
| Target dynamic | Target JDK | Attach if permitted | Dynamic policy, warnings, class coverage |
| Target no agent | Target JDK | None | Isolate app bugs vs agent bugs |
| Target multi-agent | Target JDK | Production mix | Duplicate spans, linkage, overhead |
| Target image | Target JDK | Real deployment | Container, permissions, flags, JARs |

For dynamic attach, test both **classes loaded before attach** and **classes loaded after attach**. If the agent lacks retransformation support, record that limitation explicitly—never report “dynamic compatible” merely because `agentmain` ran.

### 28.1. Metrics to Measure

- Startup latency.
- CPU and heap/native memory overhead.
- GC pauses, thread counts, and class-loading volume.
- p95/p99 latencies on critical endpoints.
- HTTP/JDBC/messaging instrumentation coverage.
- Traces/spans/error attributes and context propagation.
- Behavior when telemetry collectors are unavailable.
- Rollback cleanups on production images.

Even an exception-free agent can introduce resource regressions or degrade observability quality.

## 29. End-to-End Case Study: Java 17 to Java 21

Suppose a service runs:

~~~text
orders-service
  Runtime JDK: 17 -> 21
  Startup: vendor APM -javaagent
  Tests: coverage + mocking instrumentation
  Operations: dynamic diagnostic agent if authorized
  Deployment: Linux container
~~~

### 29.1. Inventory

The team records the APM agent version and support matrix, test tooling versions, embedded ASM/Byte Buddy capabilities, class-file major 65 impact, container injection paths, and any self-attaching libraries.

### 29.2. Issue 1: JEP 451 Warnings in Unit Tests

When tests run on JDK 21, logs emit dynamic-loading warnings. Inspect logs/stacks to locate the mocking or test library self-attaching. Where the vendor supports a startup mode, configure `-javaagent` on the test JVM per official docs and re-run all tests. Never enable broad dynamic loading in production merely to silence this test warning.

### 29.3. Issue 2: APM Loses JDBC Traces

The service boots yet dashboards miss one family of database spans. Possible causes include an APM agent lacking support for the newer JDBC/framework version, incompatible class-file transformation, or container injection misloading the agent. Verify image JAR hashes, `premain` logs, network exporter traffic, and traces under the same workload.

### 29.4. Issue 3: Late Diagnostic Attach

An agent attaches to a running JVM, yet a framework class loaded at startup remains uninstrumented. Verify class-loading timing and retransform capabilities. If the agent cannot retransform that class, restart a canary replica with startup instrumentation or pick another approved diagnostic tool—do not retry production attaches blindly.

### 29.5. Acceptance Criteria

- Reproducible JVM/agent configuration on JDK 21.
- Agents and bytecode tools vendor-certified or carrying explicitly approved exceptions.
- Coverage/mocking test agents remain active (not disabled just for green CI).
- Traces, metrics, errors, and context propagation verified end to end.
- Resource overhead stays within performance budgets.
- Attach operations restricted strictly to permitted environments, permissions, and policies.
- Canary rollout and rollback/roll-forward plans carry assigned owners.

## 30. Common Mistakes

**“Having `premain` means dynamic attach works.”** False: dynamic mode needs `Agent-Class`/`agentmain` and attach preconditions.

**“If `agentmain` succeeded, every class is instrumented.”** False: preloaded classes need retransformation within JVM limits.

**“`detach()` removes the agent from the JVM.”** False: it only closes the Attach API control connection.

**“`-javaagent` and `-agentlib` differ only in file extension.”** False: Java instrumentation and native JVMTI use different entry points, APIs, and constraints.

**“Every `Unsupported class file major version` comes from `javac`.”** False: often an agent's outdated bytecode parser hit newer class files.

**“Just add `--add-opens` across all modules.”** False: grants broad access without replacing an outdated agent.

**“JEP 451 warning means a business-logic bug on Java 21.”** False: identify the dynamically loading agent and policy first.

**“An agent can attach to any visible PID.”** False: requires proper privileges and policy compliance; never bypass security boundaries.

**“Agents don't belong in the dependency inventory.”** False: they are runtime dependencies, even when platform-injected.

**“If two agents work separately, running both together is safe.”** False: transformers can collide or duplicate telemetry.

**“Seeing `agent loaded` finishes testing.”** False: verify traces/metrics, coverage of loaded classes, and overhead.

**“Disabling APM/coverage is a quick way to finish migration.”** False whenever those tools are production or quality-gate requirements.

**“Any running class can be edited without restarting.”** False: redefinition/retransformation imposes capability and structural limits.

**“Testing only on a dev laptop is enough.”** False: container namespaces, OS permissions, native libs, and JVM flags vary.

## 31. Pre-Cutover Checklist

- [ ] Distinguished Java instrumentation agents from native JVMTI agents.
- [ ] Inventoried all agents from launch scripts, test tools, and platform injection.
- [ ] Assigned owner, version, checksum, and exact config path for each agent.
- [ ] Confirmed `Premain-Class`, `Agent-Class`, and needed manifest capabilities.
- [ ] Confirmed vendor support matrices cover the target JDK and frameworks.
- [ ] Confirmed embedded ASM/Byte Buddy or bytecode parsers support target class-file versions.
- [ ] Verified module access, internal API dependencies, and classloader strategies.
- [ ] Reviewed JEP 451 and dynamic-loading policy on the exact JDK release/vendor.
- [ ] For attach workflows, verified OS permissions, target PID/namespace, and JVM policy.
- [ ] Avoided sweeping `--add-opens` without owners or removal dates.
- [ ] Tested startup agents and, where needed, dynamic agents.
- [ ] Tested both pre-attach loaded classes and post-attach loaded classes.
- [ ] Checked retransformation/redefinition capabilities and class modifiability.
- [ ] Tested real multi-agent combinations matching production.
- [ ] Verified test runners, coverage agents, and mocking tools still operate cleanly.
- [ ] Verified traces, metrics, error tracking, and absence of duplicate instrumentation.
- [ ] Measured startup latency, CPU/memory, GC behavior, and p95/p99 latencies.
- [ ] Verified agent setup inside the actual production runtime image.
- [ ] Established audit logging and approvals for dynamic attach usage.
- [ ] Prepared rollout, rollback/roll-forward, and incident response plans.
- [ ] Documented changes to modes, flags, agent versions, and limitations in release notes.

## 32. References to Cross-Check by JDK

In a real migration, check official documentation for your **exact JDK and agent versions**:

- **Java SE API — `java.lang.instrument`:** `Instrumentation`, `ClassFileTransformer`, manifest attributes, retransform/redefine.
- **Java SE API — `com.sun.tools.attach` and `jdk.attach` module:** `VirtualMachine`, `loadAgent`, `detach`, exceptions.
- **OpenJDK JEP 451:** warnings and roadmap for controlling dynamic agent loading starting in JDK 21.
- **JVMTI Specification:** native agents and capabilities.
- **JDK launcher documentation:** `-javaagent`, `-agentlib`, `-agentpath`, and JVM flags.
- **JPMS / Java module documentation:** module boundaries, opens/exports, and class access.
- **Gradle/Maven test plugin documentation:** JVM arguments, test toolchains, and coverage integration.
- **Vendor documentation:** compatibility matrices, agent modes, and instrumentation prerequisites.

Never assume behavior observed on JDK 21 stays immutable across newer JDK releases; flags and default security policies evolve.

## 33. Conclusion

Both **startup agents** and **dynamic attach agents** build upon the Java Instrumentation API yet work very differently. Startup `-javaagent` invokes `premain` prior to `main` and cleanly intercepts classes as they load. Dynamic attach via `VirtualMachine.loadAgent` invokes `agentmain` inside a live JVM, contingent on OS privileges, attach support, JDK policies, and retransformation support for already-loaded classes.

In Java Advance Compatibility Migration, treat agents as high-privilege runtime components affecting correctness and performance: inventory them from build/test tooling through containers/platforms, check versions and manifests, validate bytecode engines, module/classloader behavior, JEP 451 policies, attach permissions, and native dependencies. Validate on the real target JDK and deployment image across telemetry accuracy, resource budgets, quality gates, and app behavior.

Whenever instrumentation is required continuously from launch, **supported and declaratively configured startup agents** are easier to reproduce, audit, and roll back. Reserve dynamic attach for authorized, tightly governed diagnostics of running processes. Migration is truly ready only when **both the application and its full agent stack** run reliably on the target runtime.
