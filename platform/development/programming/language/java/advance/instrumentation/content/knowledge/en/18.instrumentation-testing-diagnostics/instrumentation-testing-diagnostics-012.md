# Recording the Matrix of JDK, JVM, Launch Mode, and Supported Capabilities

Java Instrumentation should not be described with the sentence "this agent runs on every Java". A Java agent may **start up successfully** yet **not be granted retransform permission**, **be unable to modify a specific class**, or **be unable to attach to a running JVM**. Conversely, a JVM that theoretically supports all three capabilities is not guaranteed to grant all three to **the agent JAR being loaded**, if the manifest does not request them.

Therefore, when testing and diagnosing a Java agent, it is necessary to build an **empirical matrix (compatibility/capability matrix)** with at least four axes:

1. **JDK/JRE and distribution**: runtime version, vendor, architecture, operating system, and Java runtime configuration.
2. **JVM implementation**: VM name/version such as HotSpot/OpenJDK Server VM or another VM; do not infer the implementation solely from the word "JDK".
3. **Agent and application launch mode**: `-javaagent` with `-cp`, `-jar`, `--module`; `Launcher-Agent-Class`; dynamic agent loading via the Attach API.
4. **Actual granted capabilities**: `Instrumentation.isRedefineClassesSupported()`, `isRetransformClassesSupported()`, `isNativeMethodPrefixSupported()`, `isModifiableClass(...)`, `isModifiableModule(...)`, and success/failure status when invoking specific APIs.

**Lesson objective:** produce a table with **PASS / FAIL / BLOCKED / NOT_TESTED** evidence rather than filling in "Supported" by guesswork; know how to re-run the same testcase across different JDKs/JVMs and clearly separate **launch support**, **manifest capability**, **class/module eligibility**, and **operation success**.

The Java 17+ hands-on lab below uses **the same agent code** across multiple launch methods, recording the three capabilities and class/module modification eligibility. It was actually tested on **Zulu OpenJDK 24.0.2 (OpenJDK 64-Bit Server VM, VM vendor Azul Systems, Inc.)** with **seven scenarios**, including dynamic attach allowed or blocked.

## 1. Why a matrix is needed instead of a list like "Java 17: yes, Java 21: yes"

A single row saying "JDK 21 / supported" hides many critical variables:

- `java -javaagent:agent.jar -cp ...` invokes `premain` **before application `main`**.
- `java -javaagent:agent.jar -jar app.jar` still uses **`Premain-Class`** of the agent JAR; `-jar` does not automatically switch to `agentmain`.
- `java -javaagent:agent.jar --module app.module/...` is still a **startup agent**, but application code is in a **named module**, affecting package/module accessibility during instrumentation.
- `java -jar executable-with-launcher-agent.jar` with **`Launcher-Agent-Class`** invokes **`agentmain` before `main`**, even though this is an agent started with the JVM, **not dynamic attach**.
- Loading into a running JVM via the Attach API requires **`Agent-Class`** and an attach/dynamic loading mechanism permitted by the **implementation, environment, and policy**.
- Two agent JARs with identical bytecode but different **`Can-Retransform-Classes`** values can return two different `isRetransformClassesSupported()` values **on the same JVM**.
- `isModifiableClass(target) == true` **does not mean** `isRedefineClassesSupported() == true`, nor does it guarantee that redefining with any given byte array will succeed.

Therefore, the matrix must record all input conditions, **runtime** checks, and observed errors/outputs.

## 2. Distinguishing JDK, runtime, JVM, vendor, and loading mode

| Term | Meaning to record |
|---|---|
| **JDK release** | For example Java 17, 21, 24; record the full version/build from `java -version` |
| **JDK vendor/distribution** | For example Oracle JDK, Eclipse Temurin, Azul Zulu; must be taken from the actual running build |
| **JVM implementation** | Values of `java.vm.name`, `java.vm.vendor`, `java.vm.version` |
| **Runtime configuration** | Architecture, OS, cgroup/CPU limits, JVM flags, security/attach policy |
| **Agent entrypoint** | Whether `premain` or `agentmain` was actually invoked, not inferred from the JAR name |
| **Application launcher** | `-cp`, `-jar`, `--module`, and `Launcher-Agent-Class` |
| **Agent loader/target loader** | Class loader defining the agent/target; very important when transforming across multiple modules or plugin loaders |
| **Agent capability configuration** | The three `Can-*` flags in the manifest plus the results of the three `is*Supported()` APIs |
| **Target eligibility** | `isModifiableClass(clazz)` / `isModifiableModule(module)` for **a specific target** |
| **Observed result** | Agent load, callback invoked, operation success/failure, errors, and logs |

**Do not equate the JDK vendor with the VM implementation.** A single vendor may provide distributions using VMs from multiple families; flags such as `-XX:+EnableDynamicAgentLoading` are **implementation-specific**, not portable Java language options across all VMs.

**Do not equate "having a JDK" with "having a permitted Attach API".** In Java 9+, the Attach API resides in the **`jdk.attach`** module; a stripped-down runtime image might not contain that module. Attach also depends on OS/process permissions, PID namespace/container, JVM policy, and whether the target allows dynamic agent loading.

## 3. Matrix template to use in testing

A row template that records data clearly:

| Column | Example or rule |
|---|---|
| `run_id` | Unique ID for tracing logs |
| `timestamp_utc` | Execution timestamp, in UTC |
| `host_os_arch` | OS, architecture, CPU/container info |
| `java_home` | Actual Java runtime path |
| `java_version` | Full version from the running JVM |
| `java_vendor` | `java.vendor` |
| `java_vm_name` | `java.vm.name` |
| `java_vm_vendor` | `java.vm.vendor` |
| `java_vm_version` | `java.vm.version` |
| `application_artifact` | Name/hash of the same app JAR |
| `agent_artifact` | Name/hash of the agent JAR, entrypoints, `Can-*` |
| `launch_mode` | `classpath`, `jar`, `module`, `launcher`, `attach` |
| `command` | Full command line used |
| `attach_policy` | Not applicable / allowed / denied / unknown |
| `agent_entry` | `premain`, `agentmain`, or **not invoked** |
| `redefine` | true / false / not observable |
| `retransform` | true / false / not observable |
| `native_prefix` | true / false / not observable |
| `class_modifiable` | true / false / not checked |
| `module_modifiable` | true / false / not checked |
| `operation_result` | PASS / FAIL / BLOCKED / NOT_TESTED |
| `evidence` | Exit code, stdout/stderr, error class, JFR/log location |

**A matrix row represents one combination of conditions that was actually executed**, not every possible JDK version. If OpenJ9 or another JDK has not been run yet, mark it **NOT_TESTED**; do not fill it in based on HotSpot results.

Use distinct statuses:

- **PASS:** the operation/result was verified to be correct in the recorded environment.
- **FAIL:** the testcase ran but did not meet expectations; must include the error and expected/actual.
- **BLOCKED:** policy/environment did not allow executing the testcase, for example dynamic agent loading was blocked; do not conclude that the instrumentation API inside the JVM is missing.
- **NOT_TESTED:** not yet empirically tested; do not fill in "not supported".
- **N/A:** the field has no meaning for the scenario, for example `isRetransformClassesSupported` cannot be queried when the agent has not loaded successfully.

For forensic-grade testing, record `java -version`, the actual JAR manifest, SHA-256 of the app/agent, the JVM command line, flags, PID, and corresponding logs.

## 4. The three main capabilities: requested by manifest, decided by runtime

The three `Instrumentation` APIs:

~~~java
boolean redefine = inst.isRedefineClassesSupported();
boolean retransform = inst.isRetransformClassesSupported();
boolean nativePrefix = inst.isNativeMethodPrefixSupported();
~~~

Where `inst` is provided to the agent by the JVM. **None of the three are created via `new Instrumentation()`**.

| Manifest attribute | Check API | Related work |
|---|---|---|
| `Can-Redefine-Classes: true` | `isRedefineClassesSupported()` | Replace definitions of already-loaded classes via `redefineClasses` |
| `Can-Retransform-Classes: true` | `isRetransformClassesSupported()` | Re-invoke capable transformers via `retransformClasses` |
| `Can-Set-Native-Method-Prefix: true` | `isNativeMethodPrefixSupported()` | Transformer's native JNI name resolution fallback |

All three attributes are **optional** and **default to false** if omitted from the agent manifest. A manifest value of `true` only means "**the agent requests it**"; the JVM must also support it. There is no single catch-all flag `Can-Instrument-Everything`.

Example manifest requesting all three:

~~~text
Manifest-Version: 1.0
Premain-Class: agent.MatrixAgent
Agent-Class: agent.MatrixAgent
Can-Redefine-Classes: true
Can-Retransform-Classes: true
Can-Set-Native-Method-Prefix: true

~~~

The specification also states that capability boolean values are case-insensitive; any value other than `true` is treated as `false`.

**Conversely**, an agent JAR missing the three `Can-*` lines can still:

- Be loaded by the JVM via `-javaagent`.
- Register a **non-capable** `ClassFileTransformer` to transform classes upon initial loading.
- Call certain observation APIs or modify modules when appropriate conditions are met.

However, the corresponding `is*Supported()` APIs may still return false even if the JVM implementation in principle supports those capabilities.

## 5. `isModifiableClass` is completely different from requested capabilities

Check:

~~~java
Class<?> target = Class.forName(
        "lab.Target", false, ClassLoader.getSystemClassLoader());

boolean modifiable = inst.isModifiableClass(target);
System.out.println(modifiable);
~~~

This is a fragment running inside an agent, assuming the app has `lab.Target` in the system loader.

`isModifiableClass(target)` asks whether **a specific class can be modified** by an appropriate redefine/retransform mechanism; it does not mean the agent has requested/possesses the corresponding capability. On a HotSpot JVM, one might observe:

~~~text
REDEFINE=false
RETRANSFORM=false
NATIVE_PREFIX=false
TARGET_MODIFIABLE=true
~~~

That result is **not contradictory**. The JVM is structurally capable of supporting modifications to the target class, but the current agent is not granted redefine/retransform permission because the manifest did not request it.

In addition:

- Primitive or array classes are not modifiable according to `Instrumentation`.
- Certain special classes are rejected by the JVM for modification.
- `isModifiableClass==true` **does not guarantee that new bytes are valid**; the operation can fail due to class format, schema, verifier, or JVM TI restrictions.
- Passing a `Class<?>` from the right loader matters. Two classes with the same binary name but different defining loaders are **two different classes**.
- Do not use `isModifiableClass` as proof that a retransform operation actually ran; to prove it, you must actually invoke it and verify the result when the testcase requires it.

Similarly, for Java 9+:

~~~java
boolean modifiableModule =
        inst.isModifiableModule(Object.class.getModule());
~~~

This is a check on **the specific `java.base` module**. `true` only says that this module allows runtime relationships to be modified via `redefineModule`; it does **not** automatically open/export every package, nor does it say that every class in that module can be modified arbitrarily.

## 6. Agent launch modes: choosing the exact entrypoint

### 6.1. Startup agent via `-javaagent`

Syntax:

~~~text
-javaagent:<agent-jar>[=<agent-options>]
~~~

In the agent JAR, **`Premain-Class`** and the method are required:

~~~java
public static void premain(String agentArgs, Instrumentation inst) {
    // Invoked before application main.
}
~~~

The JVM may accept an overload with only `String`; this lesson uses the two-parameter overload to receive `Instrumentation`.

**Example launching an app via classpath:**

~~~bash
java -javaagent:agent-all.jar=from-cp -cp app.jar lab.MatrixApp
~~~

**Example executable JAR application:**

~~~bash
java -javaagent:agent-all.jar=from-jar -jar app.jar
~~~

**Example named module:**

~~~bash
java -javaagent:agent-all.jar=from-module \
     --module-path out/mods --module lab.app/lab.MatrixApp
~~~

All three invoke **`premain`**, not `agentmain`, because the condition selecting the callback is **how the agent is loaded** (`-javaagent`), not how `main` is invoked.

If multiple `-javaagent` options are specified, the JVM invokes `premain` in **the order of the options** on the command line. This order can alter the `ClassFileTransformer` chain, so when building a matrix you must record **the order of agent JARs**, not just the set of names.

An uncaught exception thrown by an agent's `premain` can cause the JVM to **abort startup** before `main`; record the exit code and stderr clearly, and do not misrecord it as "capability false".

### 6.2. Executable JAR with `Launcher-Agent-Class`

Manifest in **the executable app JAR itself**:

~~~text
Manifest-Version: 1.0
Main-Class: lab.MatrixApp
Launcher-Agent-Class: agent.MatrixAgent

~~~

Run:

~~~bash
java -jar launcher.jar
~~~

The `java.lang.instrument` specification mandates that the class in `Launcher-Agent-Class` is invoked via **`agentmain` before application `main`**, with `agentArgs` as an **empty string**. It is a **startup mechanism**, **not dynamic attach** just because the callback name is `agentmain`.

**Differences from external `-javaagent`:**

| Case | Manifest to read | Callback |
|---|---|---|
| `java -javaagent:agent.jar -jar app.jar` | `Premain-Class` in `agent.jar` | `premain` |
| `java -jar launcher.jar` with `Launcher-Agent-Class` | `Launcher-Agent-Class` in `launcher.jar` | **`agentmain` before `main`** |
| Attach agent JAR after the app is already running | `Agent-Class` in agent JAR | **`agentmain` after startup** |

Do not confuse `Launcher-Agent-Class` with `Agent-Class` when filling out the matrix. Both mechanisms invoke a method with the same name `agentmain`, but their timing, launch method, and environment requirements differ.

### 6.3. Dynamic loading of an agent into a running JVM

If the JVM supports it, you can use `com.sun.tools.attach.VirtualMachine` or an appropriate tool:

~~~java
VirtualMachine vm = VirtualMachine.attach(pid);
try {
    vm.loadAgent(pathToAgentJar, "some-options");
} finally {
    vm.detach();
}
~~~

This is a fragment; you must import `com.sun.tools.attach.VirtualMachine` and provide the valid PID and JAR.

The agent JAR needs `Agent-Class`, and the class needs the method:

~~~java
public static void agentmain(String agentArgs, Instrumentation inst) {
    // Late-loaded into a running JVM.
}
~~~

Dynamic attach **does not guarantee** that every already-loaded class can be modified: `Can-Retransform-Classes` or `Can-Redefine-Classes` may be required, and the specific class must be modifiable. A successful attach only confirms that **the agent was loaded** and `agentmain` ran; to prove a running class was transformed, a testcase must actually perform and verify that further.

**Environmental limitations:** Some runtime images lack `jdk.attach`; OS permissions or container PID namespaces prevent attach; HotSpot has the `-XX:+/-EnableDynamicAgentLoading` flag; security policies may block attach. Do not write "JDK 21 always attachable".

## 7. JEP 451 and dynamic agent loading policy

**JEP 451**, introduced in JDK 21, aims to **warn** about dynamic agent loading and prepare for a default policy change in a future release. Key points to remember:

- **Startup `-javaagent` is not the same as dynamic attach.** Dynamic loading warnings are no reason to assume `-javaagent` startup is unsupported.
- In HotSpot, `-XX:+EnableDynamicAgentLoading` is used to **allow dynamic agent loading** and express explicit opt-in; in releases with warnings, it can also suppress the warning.
- `-XX:-EnableDynamicAgentLoading` is used to **block dynamic loading** and test the failure path.
- **Do not equate the ability to attach to a PID with the ability to load an agent.** A client may be able to obtain `VirtualMachine` and attach, yet the `loadAgent` call is still rejected.
- Default values/policies and warning text depend on **version + VM implementation + deployment configuration**, and must be measured at runtime. **Do not assume that every JDK after 21 blocks by default**, or will block on a fixed release date, without verifying that exact JDK.

In the test table, there should be **two separate columns**:

~~~text
attach_api_connection = SUCCESS / FAIL / NOT_TESTED
dynamic_agent_load    = SUCCESS / BLOCKED / FAIL / NOT_TESTED
~~~

If `loadAgent` is rejected due to `-XX:-EnableDynamicAgentLoading`, you must not conclude that the three capabilities `redefine/retransform/nativePrefix` are false; **there was no `Instrumentation` object to query**.

## 8. Selecting high-value matrix combinations for testing

Instead of testing all combinations of thousands of variables, start with representative cases:

| Case | JVM | Launcher | Agent manifest | What to prove |
|---|---|---|---|---|
| C1 | Target JDK | `-javaagent` + `-cp` | all `Can-* = true` | `premain`, the three capability APIs |
| C2 | Same JVM | `-javaagent` + `-jar` | all true | `premain`, executable app runs |
| C3 | Same JVM | `-javaagent` + `--module` | all true | `premain`, named module target |
| C4 | Same JVM | `-javaagent` + `-cp` | three flags **absent** | the three capability APIs usually false |
| C5 | Same JVM | `-jar` + `Launcher-Agent-Class` | all true | `agentmain` before `main`, empty args |
| C6 | Same JVM | dynamic Attach API, opt-in | all true | `agentmain` in a running JVM |
| C7 | Same JVM | dynamic Attach API, opt-out | all true | agent load blocked, distinguish from attach |
| C8 | Different JDK/vendor/JVM | Repeat C1–C7 | Keep JAR, compatible source | Record only new empirical runs |
| C9 | Custom loader/module | Target in a separate loader/layer | Matching agent | Class/modifiable and actual access |

In particular, **C4 is an important negative control**: the same VM can return `isModifiableClass(target)=true` while all three capabilities are `false` because the manifest did not request them. This separates **implementation support** from **agent-granted support**.

**Status before running:** C8/C9 must be **NOT_TESTED**; do not use results from C1–C7 to fill in "PASS" for a different JVM.

## 9. Complete Java 17+ example: `MatrixAgent` recording runtime capabilities

The experiment consists of a **Java agent usable for both `premain` and `agentmain`**, a standalone app JAR, an executable JAR with `Launcher-Agent-Class`, a named module, and an Attach API test harness.

Directory structure:

~~~text
instrumentation-matrix/
├── src/
│   ├── agent/agent/MatrixAgent.java
│   ├── app/lab/Target.java
│   ├── app/lab/MatrixApp.java
│   ├── app/lab/TargetWait.java
│   ├── attach/AttachHarness.java
│   └── module/module-info.java
├── APP.MF
├── AGENT-ALL.MF
├── AGENT-OFF.MF
├── LAUNCHER.MF
└── out/
    ├── app/
    ├── agent/
    ├── attach/
    └── mods/lab.app/
~~~

The example **does not call `redefineClasses` or `retransformClasses` on a target class**. It checks support + eligibility and verifies the entrypoint; to score `operation_success`, a separate testcase is needed. This makes it easy to distinguish capability granting from the class transformation action itself.

### 9.1. `src/agent/agent/MatrixAgent.java`

~~~java
package agent;

import java.lang.instrument.Instrumentation;

public final class MatrixAgent {
    public static void premain(String args, Instrumentation inst) {
        report("premain", args, inst);
    }

    public static void agentmain(String args, Instrumentation inst) {
        report("agentmain", args, inst);
    }

    private static void report(
            String entry, String args, Instrumentation inst) {
        System.out.println("ENTRY=" + entry);
        System.out.println("ARGS=" + args);
        System.out.println("JDK="
                + System.getProperty("java.version"));
        System.out.println("VM="
                + System.getProperty("java.vm.name"));
        System.out.println("VM_VENDOR="
                + System.getProperty("java.vm.vendor"));

        System.out.println("REDEFINE="
                + inst.isRedefineClassesSupported());
        System.out.println("RETRANSFORM="
                + inst.isRetransformClassesSupported());
        System.out.println("NATIVE_PREFIX="
                + inst.isNativeMethodPrefixSupported());

        try {
            Class<?> target = Class.forName(
                    "lab.Target",
                    false,
                    ClassLoader.getSystemClassLoader());
            System.out.println("TARGET_MODIFIABLE="
                    + inst.isModifiableClass(target));
            System.out.println("TARGET_LOADER="
                    + target.getClassLoader()
                            .getClass().getSimpleName());
        } catch (Exception exception) {
            System.out.println("TARGET_LOOKUP="
                    + exception.getClass().getSimpleName());
        }

        System.out.println("JAVA_BASE_MODULE_MODIFIABLE="
                + inst.isModifiableModule(
                        Object.class.getModule()));
    }
}
~~~

**Explanation:**

1. **The same class has both entrypoints**, so the test clearly identifies whether the JVM invoked `premain` or `agentmain`.
2. The system properties `java.version`, `java.vm.name`, and `java.vm.vendor` record the **actual runtime** instead of relying on JAR filenames.
3. The three `is*Supported()` APIs are queried immediately inside the agent callback.
4. `Class.forName(..., false, systemLoader)` selects the **target class `lab.Target`** without running its static initializer just from looking up the class object. In the classpath/named-module demo with the system loader, the class is available. Production uses the appropriate loader.
5. `isModifiableClass(target)` checks the **target**, not inferred from capabilities.
6. `Object.class.getModule()` retrieves `java.base` (a named module on JDK 17+) to check `isModifiableModule`.
7. `TARGET_LOADER=AppClassLoader` is **the loader class name observed on the tested runtime**; a specific loader name is not a portable API to assert across all JVMs.
8. This is a **capability collection probe**, not proof that `redefineClasses` succeeded.

When recording into a production matrix, you can add `System.getProperty("java.runtime.version")`, `java.vm.version`, `java.vendor`, `os.name`, `os.arch`, `java.home`, and VM input arguments. However, do not print **secrets** in `-D...` flags or the environment to uncontrolled logs.

### 9.2. `src/app/lab/Target.java`

~~~java
package lab;

public final class Target {
    public static String work() {
        return "ok";
    }
}
~~~

A simple target class with no special restrictions. The `isModifiableClass` API in the example receives the exact `Class<?>` object of `lab.Target`.

### 9.3. `src/app/lab/MatrixApp.java`

~~~java
package lab;

public final class MatrixApp {
    public static void main(String[] args) {
        System.out.println("MAIN=" + Target.work());
    }
}
~~~

`MAIN=ok` verifies that application `main` ran after the startup `premain` or `agentmain` callback. If `agentmain` is dynamically attached to an already-running process, the callback order depends on attach timing and **the agent cannot be assumed to run before application main**.

### 9.4. `src/app/lab/TargetWait.java`

~~~java
package lab;

import java.io.BufferedReader;
import java.io.InputStreamReader;

public final class TargetWait {
    public static void main(String[] args) throws Exception {
        System.out.println("TARGET_READY");
        new BufferedReader(
                new InputStreamReader(System.in)).readLine();
        System.out.println("TARGET_DONE");
    }
}
~~~

This process simply **prints `TARGET_READY` and waits for a line on stdin**. It lets `AttachHarness` control precisely when to attempt attach, rather than waiting with `Thread.sleep` and hoping the process is still alive.

### 9.5. `src/module/module-info.java`

~~~java
module lab.app {
    exports lab;
}
~~~

The named module `lab.app` enables the command `--module lab.app/lab.MatrixApp`. In the demo, the target class is loaded by the system/application loader. For real-world modules, additional read edges/exports/opens may be needed to instrument code in packages. **`Capability=true` does not automatically grant all module access permissions**.

## 10. Attach API harness: spawning the target process and loading the agent

File `src/attach/AttachHarness.java`:

~~~java
import com.sun.tools.attach.VirtualMachine;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.file.Path;
import java.io.OutputStreamWriter;

public final class AttachHarness {
    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "args: mode appJar agentJar");
        }

        String javaBin = Path.of(
                System.getProperty("java.home"),
                "bin",
                System.getProperty("os.name")
                        .toLowerCase().contains("win")
                        ? "java.exe" : "java").toString();

        String mode = args[0];
        String appJar = args[1];
        String agentJar = args[2];
        String flag = mode.equals("allow")
                ? "-XX:+EnableDynamicAgentLoading"
                : "-XX:-EnableDynamicAgentLoading";

        Process target = new ProcessBuilder(
                javaBin, flag, "-cp", appJar, "lab.TargetWait")
                .redirectErrorStream(true)
                .start();

        BufferedReader output = new BufferedReader(
                new InputStreamReader(target.getInputStream()));
        System.out.println("CASE=" + mode);

        try {
            String ready = output.readLine();
            System.out.println(ready);

            VirtualMachine vm = VirtualMachine.attach(
                    Long.toString(target.pid()));
            try {
                vm.loadAgent(agentJar, "from-attach");
                System.out.println("ATTACH=success");
            } catch (Exception error) {
                System.out.println("ATTACH_ERROR="
                        + error.getClass().getSimpleName());
            } finally {
                vm.detach();
            }
        } finally {
            OutputStreamWriter writer =
                    new OutputStreamWriter(target.getOutputStream());
            writer.write("\n");
            writer.flush();

            for (String line;
                    (line = output.readLine()) != null; ) {
                System.out.println("TARGET_OUT=" + line);
            }
            target.waitFor();
            System.out.println("TARGET_EXIT="
                    + target.exitValue());
        }
    }
}
~~~

**This is test code using a HotSpot option**, not a portable API for all JVMs. When running on another JVM lacking the `-XX:+/-EnableDynamicAgentLoading` flags, you must change how policy is configured or record `BLOCKED`/`NOT_TESTED`, **not call it a general Java Instrumentation failure**.

Explanation:

1. `ProcessBuilder` spawns a **new JVM** with the same `java.home` as the harness.
2. The target `TargetWait` prints `TARGET_READY` so the harness knows the process has started.
3. The harness uses `VirtualMachine.attach(pid)` from the `jdk.attach` module to connect to the target.
4. `vm.loadAgent(agentJar, "from-attach")` requests loading the agent JAR. **`Agent-Class`** is read and `agentmain` is invoked if successful.
5. `-XX:+EnableDynamicAgentLoading` enables the success path on the tested HotSpot; the negative flag prevents agent loading in the blocked case.
6. `vm.detach()` closes the connection. Then the harness sends a newline so the target exits and reads the output.
7. When `loadAgent` throws an exception, it prints the error class name **without assuming the target JVM crashed**.
8. The demo script has no **timeout/forced destroy** for a hung process. When turning it into a CI test, add a timeout, kill/cleanup, and record PID/exit code.

**Two very different failure situations**:

- Cannot attach to the PID (`VirtualMachine.attach` fails): check permissions, the `jdk.attach` module, process ownership, and container policy.
- Attach succeeds but `loadAgent` is blocked (`AgentLoadException` in the test case): the JVM does not allow **dynamic agent load**. Do not speculate about the three capabilities inside the agent because `agentmain` was never invoked.

## 11. Four manifests to verify the exact lifecycle

`APP.MF` — standard executable app JAR:

~~~text
Manifest-Version: 1.0
Main-Class: lab.MatrixApp

~~~

`AGENT-ALL.MF` — external agent requesting all three:

~~~text
Manifest-Version: 1.0
Premain-Class: agent.MatrixAgent
Agent-Class: agent.MatrixAgent
Can-Redefine-Classes: true
Can-Retransform-Classes: true
Can-Set-Native-Method-Prefix: true

~~~

`AGENT-OFF.MF` — same agent bytecode, **not requesting** the three capabilities:

~~~text
Manifest-Version: 1.0
Premain-Class: agent.MatrixAgent
Agent-Class: agent.MatrixAgent

~~~

`LAUNCHER.MF` — agent packaged inside the executable JAR:

~~~text
Manifest-Version: 1.0
Main-Class: lab.MatrixApp
Launcher-Agent-Class: agent.MatrixAgent
Can-Redefine-Classes: true
Can-Retransform-Classes: true
Can-Set-Native-Method-Prefix: true

~~~

Each manifest must have a **trailing blank line**. Do not confuse:

- `Premain-Class`: agent loaded via **`-javaagent`** at JVM startup.
- `Agent-Class`: agent loaded **into an already-running JVM**.
- `Launcher-Agent-Class`: agent located **inside the executable JAR**, started before app `main` via `agentmain`.
- `Main-Class`: main application class invoked by the launcher.

There is no need to change the bytecode of `MatrixAgent` to vary `Can-*`. Using two JARs with **the same class files but different manifests** allows tests C1/C4 to isolate the effect of the manifest.

## 12. Building with JDK 17+: app JAR, agent JAR, and named module

Run from the `instrumentation-matrix` directory. On Bash/Git Bash:

~~~bash
mkdir -p out/app out/agent out/attach out/mods/lab.app
~~~

On PowerShell:

~~~powershell
New-Item -ItemType Directory -Force `
  out/app, out/agent, out/attach, out/mods/lab.app | Out-Null
~~~

Compile app and agent:

~~~bash
javac --release 17 -d out/app \
  src/app/lab/Target.java \
  src/app/lab/MatrixApp.java \
  src/app/lab/TargetWait.java

javac --release 17 -d out/agent \
  src/agent/agent/MatrixAgent.java
~~~

Compile the Attach API harness (requires the `jdk.attach` module):

~~~bash
javac --release 17 --add-modules jdk.attach \
  -d out/attach src/attach/AttachHarness.java
~~~

Separately compile the application as a named module:

~~~bash
javac --release 17 -d out/mods/lab.app \
  src/module/module-info.java \
  src/app/lab/Target.java \
  src/app/lab/MatrixApp.java
~~~

**Create the JARs:**

~~~bash
jar --create --file app.jar \
  --manifest APP.MF -C out/app .

jar --create --file agent-all.jar \
  --manifest AGENT-ALL.MF -C out/agent .

jar --create --file agent-off.jar \
  --manifest AGENT-OFF.MF -C out/agent .

jar --create --file launcher.jar \
  --manifest LAUNCHER.MF -C out/app . -C out/agent .
~~~

Separate `app.jar` and `agent-all.jar` is the common startup pattern. `launcher.jar` is **a single executable JAR containing both the application and `agent.MatrixAgent`**. Do not assume that merely setting `Launcher-Agent-Class` in `app.jar` is enough if the agent class is not present in the JAR/loader path being used.

**Inspect the manifest inside the actual JAR** rather than only the source `.MF` file. For example:

~~~bash
jar --describe-module --file app.jar
jar --list --file agent-all.jar
jar --list --file launcher.jar
~~~

`app.jar` is a **JAR without a `module-info` declaration**, so `jar --describe-module` may describe it as an automatic module; this command does not replace inspecting the manifest. You can use an appropriate ZIP/JAR tool to open `META-INF/MANIFEST.MF` or inspect it with Java's `java.util.jar.JarFile`.

**Portability note:** `--release 17` produces class files compatible with Java 17 and above, but older JVMs or native-image runtimes will not necessarily run this sample. You must recompile for a compatible target release if the matrix includes a Java 8 row, and in that case the `Module` API (`Object.class.getModule`) does not exist.

## 13. Running the startup test suite

### C1 — Startup `-javaagent` + classpath

~~~bash
java -javaagent:agent-all.jar=from-cp \
  -cp app.jar lab.MatrixApp
~~~

Observed on Zulu OpenJDK 24.0.2:

~~~text
ENTRY=premain
ARGS=from-cp
JDK=24.0.2
VM=OpenJDK 64-Bit Server VM
VM_VENDOR=Azul Systems, Inc.
REDEFINE=true
RETRANSFORM=true
NATIVE_PREFIX=true
TARGET_MODIFIABLE=true
TARGET_LOADER=AppClassLoader
JAVA_BASE_MODULE_MODIFIABLE=true
MAIN=ok
~~~

### C2 — Startup `-javaagent` + `-jar`

~~~bash
java -javaagent:agent-all.jar=from-jar -jar app.jar
~~~

Result on the same JVM: `ENTRY=premain`, `ARGS=from-jar`, all three capabilities `true`, target and `java.base` reported modifiable, then `MAIN=ok`. **Does not invoke `agentmain`** just because the app is run with `-jar`.

### C3 — Startup `-javaagent` + named module

~~~bash
java -javaagent:agent-all.jar=from-module \
  --module-path out/mods --module lab.app/lab.MatrixApp
~~~

Verified `ENTRY=premain`, `ARGS=from-module`, all three capabilities `true`, `TARGET_MODIFIABLE=true`, `JAVA_BASE_MODULE_MODIFIABLE=true`, `MAIN=ok`.

**Interpretation limit:** This does not prove the agent can reflect into every private package of named modules or that a transformer can arbitrarily add methods. To do so, you must also consider module exports/opens/reads and class-file constraints.

### C4 — Same JVM, but agent manifest **lacks the three `Can-*` attributes**

~~~bash
java -javaagent:agent-off.jar=from-off \
  -cp app.jar lab.MatrixApp
~~~

Key stdout:

~~~text
ENTRY=premain
ARGS=from-off
REDEFINE=false
RETRANSFORM=false
NATIVE_PREFIX=false
TARGET_MODIFIABLE=true
JAVA_BASE_MODULE_MODIFIABLE=true
MAIN=ok
~~~

**This case verifies the difference between granted capabilities and class eligibility.** Do not read `TARGET_MODIFIABLE=true` and then fill in `REDEFINE=true` and `RETRANSFORM=true` by assumption.

### C5 — `Launcher-Agent-Class` in an executable JAR

~~~bash
java -jar launcher.jar
~~~

Key observed lines:

~~~text
ENTRY=agentmain
ARGS=
REDEFINE=true
RETRANSFORM=true
NATIVE_PREFIX=true
MAIN=ok
~~~

`ARGS=` is an **empty string**, not the literal `null`. `ENTRY=agentmain` appears **before** `MAIN=ok`. This is **not** dynamic attach after startup.

### C6 — Dynamic attach with opt-in on HotSpot

~~~bash
java --add-modules jdk.attach \
  -cp out/attach AttachHarness allow app.jar agent-all.jar
~~~

Key observed lines:

~~~text
CASE=allow
TARGET_READY
ATTACH=success
TARGET_OUT=ENTRY=agentmain
TARGET_OUT=ARGS=from-attach
TARGET_OUT=REDEFINE=true
TARGET_OUT=RETRANSFORM=true
TARGET_OUT=NATIVE_PREFIX=true
TARGET_OUT=TARGET_MODIFIABLE=true
TARGET_OUT=JAVA_BASE_MODULE_MODIFIABLE=true
TARGET_OUT=TARGET_DONE
TARGET_EXIT=0
~~~

The agent loads **after the target prints `TARGET_READY`**, so it is genuinely dynamic attach. `VirtualMachine.attach`/`loadAgent` succeeded; the target continued running and exited cleanly.

### C7 — Dynamic attach denied

~~~bash
java --add-modules jdk.attach \
  -cp out/attach AttachHarness deny app.jar agent-all.jar
~~~

Key observed lines:

~~~text
CASE=deny
TARGET_READY
ATTACH_ERROR=AgentLoadException
TARGET_OUT=TARGET_DONE
TARGET_EXIT=0
~~~

`-XX:-EnableDynamicAgentLoading` is on the harness's **target JVM**; the Attach API connection can be made, but **agent loading is blocked**. In this row, `ENTRY`, `REDEFINE`, `RETRANSFORM`, and `NATIVE_PREFIX` are all **N/A** because the `agentmain` callback was never invoked.

## 14. Empirical observation matrix of the example

**Actually tested environment:** Azul Zulu OpenJDK **24.0.2**, `java.vm.name=OpenJDK 64-Bit Server VM`, Windows, JDK 17 bytecode target (`javac --release 17`). These details are **the conditions of one test machine**, not a support claim for every JVM.

| Case | Launch mode | Callback / status | Redefine | Retransform | Native prefix | Target modifiable | Result |
|---|---|---|---|---|---|---|---|
| C1 | `-javaagent` + `-cp` | `premain` | true | true | true | true | **PASS** |
| C2 | `-javaagent` + `-jar` | `premain` | true | true | true | true | **PASS** |
| C3 | `-javaagent` + `--module` | `premain` | true | true | true | true | **PASS** |
| C4 | `-javaagent`, no `Can-*` | `premain` | **false** | **false** | **false** | true | **PASS** (negative control) |
| C5 | `Launcher-Agent-Class` + `-jar` | `agentmain` before `main` | true | true | true | true | **PASS** |
| C6 | Attach + `EnableDynamicAgentLoading=+` | `agentmain` after startup | true | true | true | true | **PASS** |
| C7 | Attach + `EnableDynamicAgentLoading=-` | `agentmain` **did not run** | N/A | N/A | N/A | N/A | **BLOCKED** (`AgentLoadException`) |

Cases with successful callbacks also observed `JAVA_BASE_MODULE_MODIFIABLE=true` in this environment. Case C7 could not check module eligibility because the agent was not loaded. `MAIN=ok` was verified for startup apps (C1–C5); C6/C7 used a target waiting on stdin with `TARGET_READY`/`TARGET_DONE` markers.

**Do not extrapolate** from this table to JDK 17, 21, 25, 26 or OpenJ9/GraalVM without running on the corresponding JVM. When testing another JDK, create a **new data row** containing vendor/build, command, manifest, capability results, and full stderr.

**Key takeaway shown by the matrix:** within the same HotSpot/OpenJDK VM, the manifest can change capability results; a different startup mode can change the callback; and dynamic loading policy can block everything before any capability can even be queried.

## 15. Multi-JDK/JVM expansion table: recording "not tested" properly

When testing across other runtimes, use a table like the following **before having results**:

| JDK/VM to check | `-javaagent` | `Launcher-Agent-Class` | Dynamic attach | Three capabilities | Conclusion |
|---|---|---|---|---|---|
| Specific JDK 17 HotSpot | NOT_TESTED | NOT_TESTED | NOT_TESTED | NOT_TESTED | Awaiting empirical test |
| Specific JDK 21 HotSpot | NOT_TESTED | NOT_TESTED | NOT_TESTED | NOT_TESTED | Awaiting empirical test |
| JDK 24 Zulu OpenJDK 24.0.2 | PASS per C1–C5 | PASS per C5 | PASS/BLOCKED per C6/C7 | Observed true/false per manifest | Evidence recorded for the environment above |
| Specific JDK 25/26 runtime | NOT_TESTED | NOT_TESTED | NOT_TESTED | NOT_TESTED | Awaiting empirical test |
| Specific OpenJ9 distribution | NOT_TESTED | NOT_TESTED | NOT_TESTED | NOT_TESTED | Awaiting empirical test |
| jlink/custom runtime image | NOT_TESTED | NOT_TESTED | NOT_TESTED | NOT_TESTED | Check `java.instrument`, `jdk.attach`, and options |
| Native-image runtime | NOT_TESTED | NOT_TESTED | NOT_TESTED | NOT_TESTED | Do not assume equivalence to HotSpot JVM |

In newer JDKs, dynamic agent policies and launcher options may evolve. Oracle/JEP documentation is only a basis for **expectations and test plans**, not a substitute for executed results on **the actual version/build**.

For Java 8: startup instrumentation existed before JPMS, but this example uses **Java 17 APIs** such as `Module` and `ProcessHandle`; **do not compile/run directly on Java 8**. If Java 8 needs to be tested, write a separate probe version, query only APIs present in that release, and mark module-related fields as **N/A**.

## 16. Adding real operation tests after the capability probe

The matrix above shows **that the agent started and what the capabilities report**. To prove Instrumentation operations actually work, independent testcases are needed for each feature.

### 16.1. Class load transformation

Register a `ClassFileTransformer` **before the target class is defined**. Have the transformer return a valid class-file `byte[]`; verify the class behavior changes. This is a test path that may not require `Can-Redefine-Classes` or `Can-Retransform-Classes`.

### 16.2. Retransform

~~~java
if (inst.isRetransformClassesSupported()
        && inst.isModifiableClass(targetClass)) {
    inst.retransformClasses(targetClass);
}
~~~

This fragment resides inside an agent with `Instrumentation inst`, `Class<?> targetClass`. For the testcase to be meaningful, a capable transformer must be registered via `addTransformer(t, true)` **and** before-and-after output/behavior must be verified. `isRetransformClassesSupported=true` **does not prove** that an invalid byte array will be accepted by the JVM.

### 16.3. Redefine

~~~java
if (inst.isRedefineClassesSupported()
        && inst.isModifiableClass(targetClass)) {
    ClassDefinition definition =
            new ClassDefinition(targetClass, newClassBytes);
    inst.redefineClasses(definition);
}
~~~

This is a **fragment**: `java.lang.instrument.ClassDefinition` must be imported; `newClassBytes` must be **valid class-file bytes** and obey schema restrictions. For already-loaded classes, you cannot assume you can arbitrarily add/remove methods/fields or change the hierarchy.

### 16.4. Native method prefix

~~~java
if (inst.isNativeMethodPrefixSupported()) {
    inst.addTransformer(transformer, false);
    inst.setNativeMethodPrefix(transformer, "$MyAgent$");
}
~~~

This is a fragment with an agent-defined `transformer` not previously registered. The prefix only alters **JNI native resolution fallback** when normal lookup fails; it does not automatically generate Java wrappers or native libraries. To mark `native_prefix_operation=PASS`, a **real JNI integration test** is required, not just the boolean capability.

### 16.5. Module instrumentation

~~~java
if (inst.isModifiableModule(targetModule)) {
    // Call redefineModule with appropriate extraReads/extraExports/
    // extraOpens/extraUses/extraProvides.
}
~~~

This fragment does not modify the module because the API is not called yet. To actually test it, you must make verifiable additions to reads/exports/opens/uses/provides, and avoid testing on arbitrary production modules without permission.

**Record separate columns** for `capability_result` and `operation_result`. Do not use a single shared `PASS` for both.

## 17. Recording enough environment information for reproducibility

Useful commands on JDK 17+:

~~~bash
java -version
java --version
javac -version
jar --version
java --list-modules
~~~

`java -version` is generally supported even on older JDKs; `--version`, module-related options, and the `jar` tool depend on the release/image. `java --list-modules` verifies whether `java.instrument` and `jdk.attach` modules are present in the tested runtime image.

Save the manifest of **the actual agent JAR**:

~~~bash
jar --list --file agent-all.jar
~~~

`jar --list` only checks **archive entries**, not the manifest contents. Use ZIP/JAR inspection or `java.util.jar.JarFile` to confirm `Premain-Class`, `Agent-Class`, `Can-*`, and `Launcher-Agent-Class` in **`META-INF/MANIFEST.MF`**.

VM/process diagnostics (when the JDK includes tools):

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
~~~

This is **example syntax** and cannot be run verbatim with `<pid>`; replace it with an actual numeric PID and verify process permissions. `jcmd` may be absent in stripped-down runtime images and cannot always access processes across different containers.

A **machine-readable record** format:

~~~json
{
  "runId": "C1-2026-10-31T01:00:00Z",
  "javaVersion": "24.0.2",
  "vmName": "OpenJDK 64-Bit Server VM",
  "vmVendor": "Azul Systems, Inc.",
  "launch": "-javaagent + -cp",
  "agentManifest": "all-true",
  "entry": "premain",
  "redefine": true,
  "retransform": true,
  "nativePrefix": true,
  "targetModifiable": true,
  "javaBaseModuleModifiable": true,
  "operationTested": false,
  "status": "PASS",
  "evidence": "stdout and exit=0"
}
~~~

**The `runId` and timestamp in the JSON above are structural illustrations, not the actual timestamp of the test run**; the capability/VM name fields are values observed on the example environment. In CI, supply **the actual runtime timestamp**, and keep raw output and JAR SHAs.

### Is CSV sufficient?

CSV is very useful for filtering/comparing many rows. However, fields like **JVM flags, list of agents, stderr stack trace, and manifest contents** can be long or multi-line. You can store **a summary CSV row and a JSON/artifact log per run**, linked via `run_id`. Avoid stuffing an entire stack trace into a single result cell, which makes it hard to read and prone to quoting issues.

## 18. Common mistakes when filling out the matrix

| Symptom | Misinterpretation | Correct way to record |
|---|---|---|
| `-javaagent` runs successfully | "Redefine is definitely supported" | Record `premain` succeeded, query capabilities separately |
| `isModifiableClass=true`, `isRetransformClassesSupported=false` | "JVM contradicts itself" | Class eligibility is different from agent capability |
| `Launcher-Agent-Class` invokes `agentmain` | "This is dynamic attach" | This is **startup**, invoking `agentmain` before `main` |
| JAR contains both `Premain-Class` and `Agent-Class` | "The JVM will run both callbacks" | Only the entrypoint matching the load mode is invoked |
| Attach API connects but `loadAgent` fails | "JVM has no instrumentation" | Dynamic loading is blocked or agent error; capabilities not observed |
| `AgentLoadException` with deny flag | "All three capabilities are false" | Record **BLOCKED**, capabilities **N/A** |
| `-XX:+EnableDynamicAgentLoading` works on HotSpot | "Flag works on every JVM" | Mark as implementation-specific |
| JDK 21 has JEP 451 warning | "JDK 21 forbids dynamic agents by default" | Distinguish warning from denial; check runtime/flags |
| Agent lacks `Can-*` | "JVM implementation does not support it" | The JVM may support it, but **the agent did not request it** |
| `isNativeMethodPrefixSupported=true` | "JNI method wrapper works" | Requires a real JNI integration test |
| `-javaagent` on an app running with `--module` | "The agent is in that named module" | Agent classes are usually in a different module/loader; verify in practice |
| App uses custom class loader | "System loader always finds target" | Use the right `Class<?>`/loader, record runtime identity |
| Test A built on a different JDK than B | "Different results due to launch mode" | Keep binary/JVM identical, vary only launch mode |
| Read source `.MF` manifest but packaged JAR incorrectly | "Capability was requested" | Inspect the manifest **inside the actual running agent JAR** |
| JVM crashes when `premain` fails | "Class is not modifiable" | Agent startup error; must read stderr/stack trace |
| Used `-jar` and added `-cp` thinking it takes effect | "Additional classpath was applied" | `-jar` has its own classpath rules; check launcher config |
| Used `--release 17` then tested on Java 8 | "Java 8 does not support Instrumentation" | Class-file version/API incompatible; test separately |
| Case not run on OpenJ9 | "OpenJ9 does not support it" | Record NOT_TESTED |

**A useful runtime matrix is an evidence table, not a wish list.**

## 19. Practical matrix testing checklist

1. **Select specific JVM/JDK builds** to support, not just "Java 17+".
2. **Record vendor, VM name/version**, OS/arch/container limits, and `java.home`.
3. **Package app+agent properly** and record the SHA-256 of each JAR.
4. **Inspect the manifest inside the JAR**, do not trust the `.MF` file sitting next to the source.
5. **Iterate through startup modes**: `-javaagent` with classpath, executable jar, named module if the product uses them.
6. **Iterate `Launcher-Agent-Class`** if the product distributes an executable JAR with an integrated agent.
7. **Iterate dynamic attach** with allowed/denied policies if the product needs late loading; run in a permitted environment.
8. **Record the exact callback** `premain`/`agentmain`, options string, and timing relative to app `main`.
9. **Query the three `is*Supported` APIs separately**, storing true/false alongside the manifest/configuration.
10. **Query target-specific `isModifiableClass`**, recording loader/module identity, not taking one class as representative of all.
11. **Query `isModifiableModule`** for the module that actually needs modification; do not infer from `java.base` to all modules.
12. **Run operation tests** for redefine/retransform/prefix/module edits on safe test classes, recording errors/byte outputs.
13. **Mark BLOCKED/N/A** when agent loading is not permitted, rather than filling in false.
14. **Record exit code and stderr**, avoiding treating JEP 451 warnings as failures if the operation still succeeded.
15. **Save raw evidence** and executed commands; when the environment changes, re-run the entire relevant subset.
16. **Establish a support policy**: PASS per tested build/configuration, FAIL/BLOCKED with reason, NOT_TESTED needing a follow-up test plan.
17. **Compare with official documentation**, but treat runtime observations as the basis of result rows.
18. **Do not alter system/runtime policy on production machines** just to make tests pass; opt-in attach or module opens must be approved per deployment policy.

## 20. Self-check questions

1. **Are JDK vendor and JVM implementation the same field?** No; record `java.vendor`/`java.vm.vendor` and `java.vm.name` separately.
2. **Which method does `java -javaagent:agent.jar -jar app.jar` invoke?** `premain`, according to `Premain-Class` in the agent JAR.
3. **Which method does `Launcher-Agent-Class` invoke and when?** `agentmain`, before app `main` during executable JAR startup.
4. **Which manifest attribute does dynamic attach use?** `Agent-Class` together with `agentmain`.
5. **If an agent has both `Premain-Class` and `Agent-Class`, does the JVM invoke both once?** No; it selects based on the loading method.
6. **If a manifest lacks `Can-Retransform-Classes` but the JVM has the capability, what does the boolean return?** `false` for that agent configuration.
7. **Does `isModifiableClass(target)=true` prove `redefineClasses` is permitted?** No, the separate capability is required.
8. **Does an all-true manifest on a JVM that lacks the capability force the API to return true?** No.
9. **Does a successful `VirtualMachine.attach(pid)` call prove `loadAgent` is allowed?** No.
10. **If attach is blocked before `agentmain`, what should be recorded for the three capabilities?** `N/A`, not false.
11. **How is JEP 451 relevant?** Warnings and policy changes for dynamic agent loading; startup must be distinguished from attach.
12. **Is `-XX:+EnableDynamicAgentLoading` portable across all JVMs?** No; it is a HotSpot implementation option.
13. **What else might a named module target need besides `isModifiableClass`?** Module readability/exports/opens and class-loader linkage when injected code calls helpers.
14. **Does `isModifiableModule(java.base)=true` prove every other module is modifiable?** No.
15. **Why not mark all of OpenJ9 as PASS from Zulu 24 results?** Different VM build/implementation; it must be specifically tested.
16. **Why can the same agent class with different manifests return different capabilities?** Because the booleans represent capabilities requested by the agent and granted by the JVM under that configuration.
17. **What status should be recorded in the matrix when not yet run?** NOT_TESTED; do not assume FAIL.
18. **Does recording `status=PASS` after a capability probe mean real redefine worked?** No; the operation test is a separate column.
19. **Why is the SHA-256 of the JAR needed?** To ensure the exact artifact tested and detect different rebuilds/manifests.
20. **Why must the full command line be recorded?** An option such as `--module` or `-XX:-EnableDynamicAgentLoading` can change the entrypoint/policy and the result.
21. **If running Java 8 with code that uses `Module`, does the error prove Java 8 has no agent support?** No; the probe code is incompatible with Java 8 APIs.
22. **What is the difference between `BLOCKED` and `FAIL`?** BLOCKED means the test could not be executed due to environment/policy; FAIL means the testcase ran but did not meet expectations.
23. **What `agentArgs` parameter does `Launcher-Agent-Class` receive in the demo?** An empty string.
24. **What should be concluded from C4?** Class modifiable can be true while all three capabilities are false because the manifest did not request them.
25. **What should be added to measure true product compatibility?** Operation tests with verifiable effects, across the defined JDKs/JVMs, launch modes, and policies.

### Authoritative references

- [Oracle Java SE 21 — `java.lang.instrument` package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): `Premain-Class`, `Agent-Class`, `Launcher-Agent-Class`, `Can-*` flags, dynamic loading warnings, and differences between callbacks.
- [Oracle Java SE 21 — `Instrumentation` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): the three `is*Supported()`, `isModifiableClass`, `isModifiableModule`, `retransformClasses`, `redefineClasses`.
- [Oracle Java SE 17 — `java.lang.instrument` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): same entrypoint model on Java 17.
- [Oracle Java SE 21 — JDK Attach API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html): `attach`, `loadAgent`, `detach`, exceptions, and constraints.
- [OpenJDK JEP 451 — Prepare to Disallow the Dynamic Loading of Agents](https://openjdk.org/jeps/451): warning, `-XX:+EnableDynamicAgentLoading`/`-XX:-EnableDynamicAgentLoading`, policy direction.
- [Oracle JDK 21 Release Notes — Dynamic Agent Loading](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html): JEP 451 and flags in HotSpot.
- [Oracle Java SE 21 — `java` launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `-javaagent`, `-cp`, `-jar`, module mode, and JVM flags.
- [Oracle Java SE 21 — `Module` and `ClassLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): module runtime relationships, defining loaders, and class identity.

**Remember:** To test Java instrumentation reliably, record **each combination of JDK build + VM implementation + launch mode + manifest + attach policy** as **one matrix row with verifiable logs**. Separate the three questions: **did the agent load**, **was the capability granted**, and **did the operation on the target succeed**. Do not turn a single PASS run on one HotSpot build into a support promise for every JDK/JVM.