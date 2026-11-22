# Configuring -javaagent via Launcher or JAVA_TOOL_OPTIONS with Clear Scope

When packaging and deploying a Java agent, two common ways to enable instrumentation at JVM startup are placing `-javaagent` **directly in the Java launch command** and providing the same option via the **`JAVA_TOOL_OPTIONS`** environment variable. Both can trigger `premain` before `main`, but their **configuration scopes** are very different: an option attached to a specific launch command only serves the JVM created by that command, whereas an environment variable can be **inherited** by other processes and child JVMs.

The design concern is not just "getting the agent enabled" but also **which JVM must have the agent, which JVM must definitely not have it, and who is responsible for providing that JAR/path/option**. An overly broad environment configuration can cause Gradle, Maven, administrative commands, or auxiliary JVMs to accidentally run the agent; a path that only exists on a developer's machine can prevent a production process from starting.

This lesson covers syntax, scope, runnable Java 17+ examples, shell/Windows/container/service usage, testing, and safe operations. The topic belongs to the **Packaging and Deployment** section of Java Advance – Instrumentation.

## 1. Distinguishing Three Types of Scope

The word "scope" in agent deployment has at least three layers:

1. **JVM startup scope:** which processes receive the `-javaagent` option when the JVM is created. This is the main focus of this lesson.
2. **Class transformation scope:** once loaded into a JVM, which classes/modules/class loaders the transformer is allowed to process. `-javaagent` itself has no syntax for selecting application packages; the agent must filter them itself via configuration/allowlist.
3. **Telemetry data scope:** which requests, tenants, endpoints, or environments the probes record events for. This belongs to the agent's logic, not permissions that the launcher infers automatically.

For example: `JAVA_TOOL_OPTIONS` is declared for a single application container, but the transformer inside that container scans every class and instruments libraries as well; **a narrow process scope does not mean a narrow bytecode scope**. Conversely, an agent that filters the right packages can still initialize unintentionally in build processes if the environment variable is exported too broadly.

## 2. Basic Mechanics of `-javaagent`

Standard syntax:

```text
-javaagent:<agent-jar-path>[=<agent-options>]
```

Here:
- `<agent-jar-path>` is the path to the **agent JAR** whose main manifest contains `Premain-Class`.
- `<agent-options>` is **a single string** passed to the `String agentArgs` parameter of `premain`. Java Instrumentation **does not define a standard** key/value syntax: the agent parses the string itself if needed.
- The JVM loads the agent and calls `public static void premain(String agentArgs, Instrumentation inst)` before running the application's `main`. There is a one-parameter fallback signature according to the specification.
- If the JVM cannot open the JAR, cannot load the agent class, lacks a matching `premain` signature, or `premain` throws an uncaught exception, **agent startup fails and the JVM aborts startup before `main`**.
- Multiple `-javaagent` options can be used; `premain` methods are called in the order the JVM receives the agents. **Do not assume two agents interact safely by default**, especially when instrumenting the same method.

Example command to start an application JAR:

```bash
java -javaagent:/opt/agents/metrics-agent.jar=service=orders -jar /opt/apps/orders.jar
```

JVM options must appear **before** the main class or `-jar`. The following command **does not enable the agent**, because `-javaagent:...` after the app JAR may just become an argument to `main(String[] args)`:

```bash
# WRONG if the goal is to configure the JVM:
java -jar /opt/apps/orders.jar -javaagent:/opt/agents/metrics-agent.jar
```

An agent JAR is not an application by itself: it needs `Premain-Class` for agent startup, not to be confused with `Main-Class` of an executable application JAR. `-javaagent` and `-jar` have different roles and can be used together.

## 3. Direct Configuration from the Launcher: Clear Single-JVM Scope

When you have permission to edit the command or startup script, the easiest option to trace is placing the agent on the exact JVM launch command that needs instrumentation.

### 3.1. Direct Java Command

```bash
java -javaagent:/opt/agents/metrics-agent.jar=service=orders -Xms256m -Xmx1g -jar /opt/apps/orders.jar
```

Or running with a classpath:

```bash
java -javaagent:/opt/agents/metrics-agent.jar=service=orders -cp /opt/apps/classes com.example.Main
```

**Scope:** The JVM created by that exact `java` command. Other Java commands run independently afterward do not automatically receive the agent, unless their script or process launcher configures them as well.

Pros: easy to read in the command, controlled per service, easy to vary between staging/production, and does not accidentally apply to the entire shell. Cons: requires control over the actual launch command; if a framework/service wrapper generates a hidden command, you must configure it through wherever the wrapper supports passing JVM arguments.

### 3.2. Startup Script with `exec`

File `run-orders.sh`, illustrated on Linux:

```sh
#!/bin/sh
set -eu

exec java \
  -javaagent:/opt/agents/metrics-agent.jar=service=orders \
  -Xmx1g \
  -jar /opt/apps/orders.jar
```

`exec` replaces the shell with the `java` process; this approach is typically suitable for signal handling in container/service scripts. **Do not** add a global `JAVA_TOOL_OPTIONS` just to configure a single service that already has an explicit launch command.

If the application is launched by Maven/Gradle, an IDE, a test runner, an app server, or a service wrapper, you must identify **which JVM is running the code**. The JVM running Maven/Gradle may differ from the forked JVM running tests or the server; configuring the wrong place will attach the agent to the tool instead of the application, or to both.

### 3.3. Paths and Quoting

It is best to use an absolute, stable path **without spaces** in production. If the path contains spaces, the shell must pass the entire `-javaagent:<path>[=<options>]` as **a single argument**; for example:

```bash
java "-javaagent:/opt/my agents/metrics-agent.jar=service=orders" -jar /opt/apps/orders.jar
```

The quotes in the example only help the **shell** group the argument; the JVM ultimately receives a single argument. When the same option is placed in `JAVA_TOOL_OPTIONS`, the token/quote splitting syntax handled by the JVM **differs from the shell**, so the lowest-risk solution is to use paths without spaces and test how parsing behaves on the target runtime. Avoid assuming every environment variable undergoes a second shell expansion.

## 4. `JAVA_TOOL_OPTIONS`: Process-Environment Scope

`JAVA_TOOL_OPTIONS` is an environment variable that the JVM can read when creating the virtual machine, documented by Oracle at the time **`JNI_CreateJavaVM`** is called. Its value is prepended/added to the JVM startup options and can contain `-javaagent`. Therefore, it is especially useful when the Java command is buried inside scripts/wrappers or when a native program creates a JVM via JNI.

Example on Linux/macOS:

```bash
JAVA_TOOL_OPTIONS="-javaagent:/opt/agents/metrics-agent.jar=service=orders" \
  java -jar /opt/apps/orders.jar
```

This form sets the variable **for that specific command**; the current shell does not retain the exported change permanently. However, if that Java process itself spawns a child process and the child inherits the environment, another child JVM can still read the same variable. Therefore, the accurate statement is: **it attaches the environment to the process tree created by that command**, not a technical guarantee that only a single JVM will see it.

If exported in the shell:

```bash
export JAVA_TOOL_OPTIONS="-javaagent:/opt/agents/metrics-agent.jar=scope=shell"

java -jar /opt/apps/orders.jar
java -version

unset JAVA_TOOL_OPTIONS
```

Every JVM created from that shell environment **while the variable remains set**, including `java -version` or Java programs spawned by scripts, may attempt to load the agent. In HotSpot, a line like `Picked up JAVA_TOOL_OPTIONS: ...` is typically printed to **stderr**. This line is a diagnostic signal, not an API or a log format guaranteed to be identical across all JVMs.

### 4.1. Why Is `JAVA_TOOL_OPTIONS` Different from a Shell Script Adding `-javaagent`?

A direct shell script only adds the option to **the command it launches**. An environment variable, on the other hand, lives in the **process environment** and is typically passed down to child processes according to OS/launcher rules. A command such as:

```bash
export JAVA_TOOL_OPTIONS="-javaagent:/opt/agents/metrics-agent.jar=scope=global"
./start-all-services.sh
```

can cause multiple Java processes spawned by `start-all-services.sh` to all carry the agent, including services outside the target scope. If a child JVM does not have the corresponding `/opt/agents/metrics-agent.jar` path, startup can fail.

In privileged environments or certain security configurations, the JVM may **reject** or **ignore** `JAVA_TOOL_OPTIONS`. Therefore, you must verify on the actual runtime rather than treating setting the variable as proof that the agent was loaded.

### 4.2. When Should You Choose the Environment Variable?

Choose `JAVA_TOOL_OPTIONS` when:
- you cannot edit the exact Java command, but you have control over providing the **environment for the specific service/container**;
- the system has a wrapper/native launcher creating the JVM that you need to configure;
- you want a process/container-level deployment policy with clear boundaries in an orchestrator;
- you have verified that no auxiliary JVMs are affected and the JAR is accessible everywhere the variable is present.

Do not choose a machine-wide or entire-terminal-session global variable when you only want to instrument one application. Specifically avoid setting it broadly in shell profile files, node-wide environments, CI runners, or base images reused by multiple tasks unless you intentionally accept that scope.

## 5. Deployment Scope Decision Table

| Where configured | Which JVMs can receive the agent? | When appropriate | Risks to control |
| --- | --- | --- | --- |
| `java -javaagent:... -jar app.jar` | The JVM created by **that command** | Single application, controllable command | Actual command may differ from assumed command |
| Launcher/service wrapper JVM arguments | The JVM to which the wrapper passes arguments | Application server, test runner, run configuration | Accidentally placing on the build tool's own JVM or missing forks |
| `JAVA_TOOL_OPTIONS=... java ...` for one POSIX command | The JVM created by the command and child JVMs inheriting env | Quick testing, a specific run | Child JVMs affected if spawned |
| `export JAVA_TOOL_OPTIONS=...` in shell | Future processes/JVMs inheriting env from the shell | Only when shell-wide scope is truly desired | Build tools, `java -version`, Java utilities also receive it |
| `JAVA_TOOL_OPTIONS` in a service's environment | Service JVM and inheriting child processes/JVMs | Cannot edit `ExecStart` | Requires restarting service to take effect; child JVMs affected |
| Env of **a single container** | JVMs inside that container (and child processes) | Isolated Docker/Pod container | Agent JAR must exist in the container filesystem |
| Env declared on a Pod's container | The specified container; does not automatically spread to other containers | Kubernetes with multi-container workloads | Does not automatically provide the JAR; rollout/restart to apply |
| Node-wide/CI runner environment | Many JVM processes, including builds/tests | Only when intentionally applying globally | Scope too broad, prone to causing startup failures |

**None of the options in this table automatically restricts which classes get instrumented.** Once the agent is loaded, the transformer filter/agent configuration decides which classes are transformed.

## 6. Runnable Java 17+ Example: Observing Direct vs. Environment Configuration

This experiment uses no external libraries. The agent simply prints `agentArgs` in `premain` to verify **which JVM loaded the agent**. The application prints a line from `main`. The example intentionally does not transform bytecode, because the goal is **startup configuration**.

Project structure:

```text
agent-scope-demo/
├── agent.mf
├── src/
│   ├── agent/
│   │   └── ScopeAgent.java
│   └── demo/
│       └── Main.java
└── out/
```

### 6.1. Agent Entry Point

File `src/agent/ScopeAgent.java`:

```java
package agent;

import java.lang.instrument.Instrumentation;

public final class ScopeAgent {
    private ScopeAgent() {}

    public static void premain(String agentArgs, Instrumentation inst) {
        System.out.println("agent: " + agentArgs);
    }
}
```

`Premain-Class` points to `agent.ScopeAgent`. `agentArgs` is printed verbatim here; there is no automatic JVM parser converting `source=direct` into key/value pairs. In a production agent, configuration parsing and validation must be performed by the agent itself, in a controlled manner without logging secrets.

### 6.2. Simple Application

File `src/demo/Main.java`:

```java
package demo;

public final class Main {
    public static void main(String[] args) {
        System.out.println("app: " + String.join(",", args));
    }
}
```

File `agent.mf` with a trailing blank line:

```text
Manifest-Version: 1.0
Premain-Class: agent.ScopeAgent

```

### 6.3. Compile and Package

On Linux/macOS, create the output directory:

```bash
mkdir -p out
```

On PowerShell:

```powershell
New-Item -ItemType Directory -Force out | Out-Null
```

Run in the project directory with JDK 17+:

```bash
javac --release 17 -encoding UTF-8 -d out src/agent/ScopeAgent.java src/demo/Main.java
jar --create --file scope-agent.jar --manifest agent.mf -C out agent
```

Only classes in the `agent` package are packaged into this JAR; the application runs from `out`. If packaging standalone for production, you must coordinate agent/app versions and ensure all agent dependencies can be loaded.

### 6.4. Case A: `-javaagent` in the Command

```bash
java -javaagent:scope-agent.jar=source=direct -cp out demo.Main hello
```

**Exact stdout** in the experiment:

```text
agent: source=direct
app: hello
```

Because the JVM invokes `premain` before `main`, the agent's line appears before the application's line.

### 6.5. Case B: `JAVA_TOOL_OPTIONS` for a Single Command

With a POSIX shell, from the project directory, using an absolute path via `$PWD`:

```bash
JAVA_TOOL_OPTIONS="-javaagent:$PWD/scope-agent.jar=source=env" \
  java -cp out demo.Main hello
```

Program stdout:

```text
agent: source=env
app: hello
```

On the tested OpenJDK/HotSpot, the JVM also prints to **stderr** a line like:

```text
Picked up JAVA_TOOL_OPTIONS: -javaagent:/absolute/path/to/scope-agent.jar=source=env
```

`/absolute/path/to` is the actual path on the host machine, not a fixed literal string printed by the Java program. Do not confuse this stderr notice with the experiment's stdout.

### 6.6. Case C: Without an Agent

Ensure the shell has no remaining `JAVA_TOOL_OPTIONS` or other agent options, then run:

```bash
java -cp out demo.Main hello
```

Stdout:

```text
app: hello
```

If the `agent:` line still appears, check other configuration sources: inherited `JAVA_TOOL_OPTIONS`, launcher `JDK_JAVA_OPTIONS`, JVM arguments in a wrapper, or another agent.

### 6.7. Case D: Enabled in Both Environment and Command

**Do not use in operations unless multiple agents are intentionally desired.** This experiment illustrates accumulation:

```bash
JAVA_TOOL_OPTIONS="-javaagent:$PWD/scope-agent.jar=source=env" \
  java -javaagent:scope-agent.jar=source=direct -cp out demo.Main hello
```

On the tested OpenJDK 21.0.12.1, stdout is:

```text
agent: source=env
agent: source=direct
app: hello
```

This is **not two configurations merged into one agent**; in the example, the same agent JAR is launched twice. For a production agent that installs hooks, threads, exporters, or transformers, loading twice can cause duplicate instrumentation and metrics. In environments with multiple tools/launchers, always inspect the final options list and agent order rather than inferring from a single configuration variable.

**Verification performed:** The example code was compiled with `javac --release 17` and run on OpenJDK 21.0.12.1 in all four cases above; stdout matched as recorded. This is a test for the example, **not a guarantee that every JVM will print stderr identically to HotSpot**.

## 7. Linux/macOS: Set the Variable for One Command or the Whole Shell?

### 7.1. Single Run, Without Polluting the Shell

```bash
env JAVA_TOOL_OPTIONS="-javaagent:$PWD/scope-agent.jar=scope=one-run" \
  java -cp out demo.Main hello
```

The `env NAME=value command` syntax creates an environment for the command; after the command finishes, the shell invoking `env` does not retain the variable. However, as noted, **child processes spawned by the command** can still inherit the environment.

### 7.2. `export` for a Sequence of Commands, Then `unset`

```bash
export JAVA_TOOL_OPTIONS="-javaagent:$PWD/scope-agent.jar=scope=session"

java -cp out demo.Main one
java -cp out demo.Main two

unset JAVA_TOOL_OPTIONS
```

Both Java processes are likely to load the agent. If you only intend to enable it for one process, using the single-command form or direct configuration is less risky.

### 7.3. Avoid Setting Permanently in Shell Profiles

A line `export JAVA_TOOL_OPTIONS=...` in `.bashrc`, `.profile`, or machine-wide environment settings can spill over into build scripts, unrelated applications, and administrative tools. If the agent JAR is replaced/deleted or the path becomes invalid, many Java commands can fail together right at startup. For production, put the configuration in the management layer of the **workload that owns the agent**.

## 8. Windows PowerShell: Setting in a Session and Reverting

In PowerShell, setting the variable applies to the environment of the **current PowerShell process**; child processes spawned afterward inherit it unless configured otherwise:

```powershell
$env:JAVA_TOOL_OPTIONS = "-javaagent:C:\agents\scope-agent.jar=scope=local"
java -cp out demo.Main hello
Remove-Item Env:\JAVA_TOOL_OPTIONS
```

If the environment already had a value beforehand, using `Remove-Item` can accidentally delete the user's configuration. For a reversible test:

```powershell
$previous = $env:JAVA_TOOL_OPTIONS
try {
    $env:JAVA_TOOL_OPTIONS = "-javaagent:C:\agents\scope-agent.jar=scope=test"
    java -cp out demo.Main hello
}
finally {
    if ($null -eq $previous) {
        Remove-Item Env:\JAVA_TOOL_OPTIONS -ErrorAction SilentlyContinue
    }
    else {
        $env:JAVA_TOOL_OPTIONS = $previous
    }
}
```

Both snippets require the agent JAR to exist at `C:\agents\scope-agent.jar`. The path `C:\agents\...` is only a deployment example, **not a path automatically created by the compiled example in Section 6**. When just built with `jar` in the current directory, you can use the corresponding absolute path, while avoiding spaces in the path to reduce option-parsing errors.

Do not edit system-wide environment variables via the registry or change permanent machine-level settings just to test an agent on a single service.

## 9. Docker/Containers: Per-Container Environment

Configuration-only example, assuming the container image already has `/opt/agents/metrics-agent.jar` and the application at `/app/app.jar`.

**Approach A: Let the container command enable the agent**

```dockerfile
FROM eclipse-temurin:21-jre
COPY app.jar /app/app.jar
COPY metrics-agent.jar /opt/agents/metrics-agent.jar
ENTRYPOINT ["java", "-javaagent:/opt/agents/metrics-agent.jar=scope=api", "-jar", "/app/app.jar"]
```

In this approach, running a container creates the JVM with the agent directly in the command. The Dockerfile is an **illustrative example**; `app.jar` and `metrics-agent.jar` must be present in the build context.

**Approach B: Keep the image's ENTRYPOINT unchanged; only the target container receives the variable**

```bash
docker run --rm \
  -e JAVA_TOOL_OPTIONS="-javaagent:/opt/agents/metrics-agent.jar=scope=api" \
  my-java-api:1.0
```

Assumes `my-java-api:1.0` already contains the agent JAR at that path. Otherwise, the JAR must be packaged into the image or mounted via an appropriate volume. Using a dedicated environment for the container under observation prevents the agent from becoming an accidental host-wide policy.

**Note:** If an image runs multiple Java commands inside the same container, every JVM inheriting `JAVA_TOOL_OPTIONS` can start the agent. One container does not guarantee a single JVM. Also avoid putting `ENV JAVA_TOOL_OPTIONS=...` into a base image used to build or run multiple services unless the impact scope has been explicitly decided.

## 10. Kubernetes: Declaring for a Specific Container

Example fragment of a Kubernetes Deployment, **not a standalone manifest**:

```yaml
spec:
  template:
    spec:
      containers:
        - name: api
          image: example/api:1.0
          env:
            - name: JAVA_TOOL_OPTIONS
              value: "-javaagent:/opt/agents/metrics-agent.jar=scope=api"
```

Kubernetes injects the environment variable into the **`api` container** declared here. Other containers in the same Pod do not automatically receive this variable unless they are also configured. The `metrics-agent.jar` file must already exist in the `example/api:1.0` image, or be provided to the container filesystem via an appropriate volume/init-container mechanism.

To limit rollout blast radius:
- Declare the agent only on the workload/pod template that needs observation; do not use a cluster-wide variable unless required.
- Use immutable image/JAR versions with clear checksums/provenance.
- Test first on a single replica/canary; monitor startup, readiness, linkage errors, and overhead.
- When editing a Pod template's env, a rollout creating **new Pods/JVMs** is required; an already-running JVM does not suddenly re-read `JAVA_TOOL_OPTIONS`.
- If the agent encounters a startup error, the pod may enter a crash/restart loop; have a rollback plan to the previous configuration or image.

Distinguish between **container env scope**, **JVM start scope**, and **the scope of classes the agent instruments**. These are three separate decisions.

## 11. Service Managers, Build Tools, and Nested Launchers

### 11.1. Service Managers

Example systemd fragment on Linux, with the JAR actually present at the corresponding path:

```ini
[Service]
Environment="JAVA_TOOL_OPTIONS=-javaagent:/opt/agents/metrics-agent.jar=scope=orders"
ExecStart=/usr/bin/java -jar /opt/apps/orders.jar
```

The option is placed in the service's environment rather than exported machine-wide. If the service spawns Java child processes that inherit the environment, they may also be affected. After editing the unit configuration, reload the service manager configuration (when needed) and **restart the service** to create a new JVM; editing the unit file alone does not change an already-running JVM.

You can choose to place `-javaagent` directly in `ExecStart` if this is a Java service with a stable command; that approach has a clearer scope than an environment variable if the service spawns Java subprocesses.

### 11.2. Maven/Gradle and Test Runners

A command like `mvn test` may create a JVM to run Maven plus additional forked test JVMs. `gradle test` also has a daemon/launcher JVM and worker/test processes depending on configuration. Therefore:

- If the target is the **test JVM**, use the test runner/fork JVM arguments configuration (e.g., Maven Surefire `argLine`, Gradle `Test.jvmArgs`) appropriate for the project.
- If the target is an **application run by a plugin**, use the JVM arguments of the `JavaExec` task/application-running plugin rather than hastily setting a global env for Gradle/Maven.
- If `JAVA_TOOL_OPTIONS` is used at the build job's shell level, it can affect both the build tool's JVM and forked JVMs if the environment is inherited.
- When a tool also attaches another Java agent (coverage/profiler), coordinate ordering and argument merging; do not accidentally overwrite the tool's agent configuration.

Example Gradle Groovy DSL configuration, which only makes sense when the project already has a `JavaExec` task named `run` (such as with the `application` plugin):

```groovy
tasks.named('run', JavaExec) {
    jvmArgs '-javaagent:/opt/agents/metrics-agent.jar=scope=app-run'
}
```

This is a **task configuration snippet, not a standalone program**. It sets the option for the JVM launched by the `run` task, without needing `JAVA_TOOL_OPTIONS` on the Gradle daemon.

### 11.3. Launchers via JNI

When a native launcher creates a JVM via the JNI Invocation API, operators sometimes have no opportunity to edit a `java` command because there is no visible `java` command at all. According to Oracle documentation, `JAVA_TOOL_OPTIONS` is examined at `JNI_CreateJavaVM`, so it can address this case when the implementation permits. However, it **cannot replace options parsed only by the Java launcher**, such as launcher VM selection flags on some platforms.

**Do not confuse `JAVA_TOOL_OPTIONS` with `JDK_JAVA_OPTIONS`.** On supported JDKs, `JDK_JAVA_OPTIONS` is read by the Java **launcher** and prepended to the launcher's command-line arguments; `JAVA_TOOL_OPTIONS` is examined when creating the JVM. `JDK_JAVA_OPTIONS` does not automatically help a native application that creates its own JVM via JNI, because that application may not use the Java launcher.

## 12. When Both Command and Environment Have an Agent

Such combinations can occur because:
- an image has `ENTRYPOINT ["java", "-javaagent:..."]`;
- the deployment system also sets `JAVA_TOOL_OPTIONS=-javaagent:...`;
- a launcher or framework injects its own agent;
- `JDK_JAVA_OPTIONS` also contains an agent option.

Do not simply say "command-line overrides environment." For **`-javaagent` flags**, this is not a single-key configuration pair where one replaces the other; the JVM can **launch multiple agents**. On HotSpot in the Section 6 example, the agent from `JAVA_TOOL_OPTIONS` ran before the agent specified directly, but do not assume the exact same order across every wrapper chain and JVM configuration. What must be ensured is the **actual set of agents** and that `premain` methods are called as expected.

How to prevent this:
1. Choose **a single configuration owner** for each workload: either the command/startup script or the workload environment.
2. Inspect `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, and flags supplied by service wrappers/tools.
3. Ensure the same agent is not accidentally specified twice.
4. If intentionally using multiple agents, run interaction tests on the exact Java version: transformer order, callback order, helper classes, and performance impact.
5. Agent configuration should be idempotent where possible; however, do not rely on idempotence to mask duplicate deployment mistakes.

## 13. Changing, Disabling the Agent, and Rollback

`-javaagent` is a **JVM startup** option; `JAVA_TOOL_OPTIONS` is read when the JVM is created. Therefore:

- Remove `-javaagent` from the command and **start a new JVM** to get a new process without that agent loaded.
- Remove `JAVA_TOOL_OPTIONS` from a shell/service/container and create a new process; a **running** JVM does not automatically unload the agent or transformed bytecode.
- Do not use `unset JAVA_TOOL_OPTIONS` in a shell to conclude that all old JVMs have stopped instrumenting; that only changes the environment for subsequent launches.
- Java Instrumentation has a **dynamic attach/agentmain** mechanism on some JVMs, but that is a **different** deployment path from the startup `premain` discussed here; do not treat attach as a behavior of `JAVA_TOOL_OPTIONS`.
- If an agent itself supports soft-off/hard-off, evaluate how it removes probes via retransformation and which classes were transformed, rather than inferring it from changing a JVM option.

Minimum production rollback plan: keep a pre-agent configuration/image, know how to restart the workload, use a canary, monitor startup failures, and ensure the agent JAR can be retracted without breaking the deployment.

## 14. Security and Configuration Control

`-javaagent` carries high privilege: the agent executes Java code in the same JVM process as the application, can observe/modify bytecode, and affects stability. Therefore:

- Only load agent JARs from trusted sources, pin versions, and verify checksums/signatures when appropriate.
- Define exactly which teams/workloads are allowed to modify JVM arguments or `JAVA_TOOL_OPTIONS`; avoid node-wide environment configurations when unnecessary.
- The agent JAR must be readable by the user running the JVM, and untrusted applications must not be allowed to replace the JAR.
- Avoid placing tokens, passwords, or private keys in the agent options string whenever possible: command lines, environments, and startup logs can expose them. Use appropriate secrets mechanisms and access controls per the agent's design.
- Choose managed, predictable paths; avoid wildcards or depending on the service's current working directory.
- Test JDK compatibility, JPMS, class loaders, required Java Instrumentation capabilities, and impact on startup, memory, and CPU.
- A failing agent startup can **prevent the application from starting**; before rollout, test missing JAR, invalid manifest, and invalid configuration cases.
- When logging telemetry confirming `premain`, only log non-sensitive information: enabled status, agent version, approved service name—do not dump raw secret strings.

## 15. Diagnosing Configuration That Has No Effect

| Symptom | Check first |
| --- | --- |
| `premain` does not run when using the command | Is `-javaagent` placed **before** the main class/`-jar`? Are the agent JAR and `Premain-Class` valid? |
| Launch command reports agent JAR not found | Does the path exist **inside the process/container filesystem**? Read permissions and working directory? |
| App fails to start after enabling agent | Read stderr and startup exceptions, JDK version, errors in `premain`, agent dependencies |
| `JAVA_TOOL_OPTIONS` is set but no `premain` runs | Did the environment actually reach the process creating the JVM? Does the JVM support and not block the variable? Is JNI or another launcher used? |
| `java -version` also runs the agent | Environment variable has overly broad shell/system scope |
| Maven/Gradle is slowed down or broken by the agent | `JAVA_TOOL_OPTIONS` is inherited by the build tool's JVM instead of only the test/app JVM |
| Every event appears recorded twice | Both command and env contain the agent; two agents/transformers are inserting probes |
| Set new env but old app does not change | Running app/JVM needs to be restarted; env is only read at JVM creation |
| Container reports missing JAR | JAR was not COPYed/mounted at the right path inside the **container**, even if the host has the file |
| `premain` runs but no probes fire | Check allowlist/transformer config, module/loader visibility, types of classes instrumented, and runtime hooks |
| Agent only runs on some Pods | Pod template, canary, rollout, per-container env, image and version across replicas |

**Most concise verification:** have the agent print/emit a safe startup indicator, check logs for `premain` and build/version; then verify that only the intended process/Pod/service receives the agent. HotSpot's `Picked up JAVA_TOOL_OPTIONS` line on stderr is only a helpful signal; it does **not** prove the transformer instrumented the right classes or that probes produced data.

The `jcmd <pid> VM.command_line` command can help inspect part of the command-line/VM arguments of a running HotSpot JVM if you have sufficient permissions, but it **does not always prove the origin** of every option (CLI, env, wrapper). There is no need to dump the entire environment, which may contain secrets, just to diagnose agent scope.

## 16. Pre-Deployment Checklist

- [ ] Identify the **exact JVM**: application, server process, worker/test fork, or JNI-embedded launcher?
- [ ] Choose the right configuration location: startup command, wrapper JVM arguments, or workload `JAVA_TOOL_OPTIONS`.
- [ ] Know whether child processes/JVMs can **inherit the variable**.
- [ ] Have a trusted agent JAR, correct version, valid `Premain-Class`, and readable absolute path at runtime.
- [ ] Know the exact `agentArgs` string, ensure it contains no secrets, and ensure it is validated by the agent.
- [ ] No unintended duplicate `-javaagent` across command, env, wrapper, or `JDK_JAVA_OPTIONS`.
- [ ] Filter classes/modules/loaders in the agent so instrumentation scope matches the target.
- [ ] Test both successful startup and failure cases (missing JAR, invalid config), checking stderr and `premain` indicators.
- [ ] Assess overhead, class loading, canary, rollback, and restart plan.
- [ ] Document who owns the configuration and how to disable it for JVMs created **after** changes.

## 17. Self-Check Questions

1. Why is `java -jar app.jar -javaagent:agent.jar` not equivalent to `java -javaagent:agent.jar -jar app.jar`?
2. When exporting `JAVA_TOOL_OPTIONS` in a shell and then running Maven and a Java application, which JVMs can receive the agent?
3. Why can using an environment variable for a single command **still** affect a child JVM spawned by that process?
4. What is the difference between `JAVA_TOOL_OPTIONS` and `JDK_JAVA_OPTIONS` when a native launcher calls `JNI_CreateJavaVM`?
5. If a container has `JAVA_TOOL_OPTIONS=-javaagent:/opt/agent/agent.jar` without that JAR file present, what happens at startup?
6. Why does declaring `JAVA_TOOL_OPTIONS` in `containers[].env` for `api` not automatically apply to a sidecar in the same Pod?
7. When both env and command specify an agent JAR, how many times can you expect `premain` to be called?
8. Can you modify the shell's `JAVA_TOOL_OPTIONS` to make an agent currently running inside a JVM stop working immediately? Why?
9. What is the difference between the scope of **JVMs with the agent enabled** and the scope of **classes transformed by the transformer**?
10. When you see the `Picked up JAVA_TOOL_OPTIONS` log, what else must you check to conclude that probes are actually working?

## 18. Official Documentation

- [Java SE 21 — `java.lang.instrument`, section *Starting an Agent from the Command-Line Interface*](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): `-javaagent:<jarpath>[=<options>]`, `premain`, manifest, and startup failures.
- [Java SE 21 — The `java` Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): JVM option placement, `-jar`, `-javaagent`, and `JDK_JAVA_OPTIONS`.
- [Oracle JDK Troubleshooting Guide — `JAVA_TOOL_OPTIONS` environment variable](https://docs.oracle.com/javase/8/docs/technotes/guides/troubleshoot/envvars002.html): variable applied when `JNI_CreateJavaVM` is called, embedded applications, and security notes.
- [Java SE 21 — `Instrumentation`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): API the agent receives via `premain` or `agentmain`, instrumentation mechanisms.
