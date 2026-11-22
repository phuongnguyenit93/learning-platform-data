# Distinguishing premain Startup Errors, agentmain Errors, and Installed Bytecode Errors

## 1. Nature of the Problem: Identifying the Failing Phase

A Java agent can fail **before the application enters main**, fail when **attaching to a running JVM**, or be loaded successfully and later cause a class **to fail to define** or an instrumented method **to fail at execution time**. An exception name such as `IllegalStateException`, `ClassFormatError`, or `NoClassDefFoundError` by itself does not pinpoint the root cause.

Three categories must be distinguished:

1. **`premain` startup errors:** The Java agent is specified via `-javaagent:<jar>`. The JVM reads `Premain-Class` and invokes `premain` before application `main`. If the entry point cannot be loaded or the method throws an uncaught exception, **the JVM aborts before application main**.
2. **`agentmain` errors in dynamic attach:** A tool requests loading an agent into a **running JVM**. The JVM invokes `agentmain` via `Agent-Class`. If initialization fails or the method throws an uncaught exception, **the target JVM does not abort solely due to the attach error**, though the tool calling `VirtualMachine.loadAgent` may receive an error and the JVM may log a stack trace.
3. **Bytecode / class lifecycle errors:** The agent is already active and the transformer is invoked. The transformer may throw an exception itself, return malformed bytes rejected by the JVM at the definition step, or return valid bytes that are installed by the JVM successfully while the new method later triggers a linkage/runtime error on a subsequent call.

**An exception that must not be overlooked:** `Launcher-Agent-Class` also invokes a method named `agentmain`, but it is a **launcher agent in an executable JAR** that runs **before application main**. If this method throws an uncaught exception, **the JVM aborts**. Therefore, you must verify **the launch mechanism**, rather than classifying solely by the method name `agentmain`.

In this lesson, we test five distinct outcomes using a Java 17 target:

- `premain` throws → the process never enters `Main.main`.
- `ClassFileTransformer.transform` throws → not guaranteed to prevent class loading; in the demo, V1 still runs.
- Transformer returns `byte[]{1,2,3}` → `ClassFormatError` when the JVM defines the class.
- Transformer returns a **valid** V2 classfile, but V2 calls a helper **absent at runtime** → the class is defined, and `NoClassDefFoundError` only occurs when invoking the method.
- `agentmain` dynamic attach throws → the attach tool receives `AgentInitializationException`, while the target JVM remains alive.

You must know **whether class definition has completed or not**. That a transformer callback was invoked and returned data **does not mean** the data has been verified, linked, defined, and executed successfully by the JVM.

## 2. Timeline of the Three Mechanisms

### 2.1. Startup with premain

~~~text
java -javaagent:diag-agent.jar=options -cp app demo.Main
          |
       JVM bootstrap
          |
       agent JAR + Premain-Class
          |
       load agent class and dependencies
          |
       invoke premain(...)
          |
          +-- uncaught throw / init error --> JVM ABORT
          |
          +-- normal return
                  |
                  v
            application main()
                  |
            class load / transform / verify / invoke
~~~

Typical causes: manifest missing `Premain-Class`, wrong binary class name, wrong `premain` signature, missing agent dependency, or config parsing error inside `premain`. If the JVM aborts during this phase, you cannot conclude that Target bytecode was installed incorrectly, because the application has not necessarily loaded Target yet.

### 2.2. Dynamic Attach with agentmain

~~~text
Target JVM already running main and threads
             |
Attach tool / VirtualMachine.loadAgent(...)
             |
Permission / provider / PID / policy
             |
Agent-Class in agent JAR
             |
load agent class, invoke agentmain(...)
             |
             +-- uncaught throw
             |     target JVM does not abort due to attach error
             |     attach caller may receive AgentInitializationException
             |     VM may log error at Attach Listener
             |
             +-- normal return
                   tool continues
                   must verify agent had expected effect
~~~

An error in `agentmain` **does not automatically roll back side effects** that occurred before the method threw. The agent may have already added a transformer, threads, or module relationships before failing. Therefore, "the target process is still alive" does not prove the agent **had no impact** either.

### 2.3. Transformer, Verify, Define, Execute

~~~text
Agent has registered transformer
          |
JVM needs to define demo.Target
          |
transform(loader, "demo/Target", inputBytes)
          |
          +-- return null or throw -->
          |     this transformer does not modify bytes
          |     other transformers can still run
          |     JVM continues attempting to define
          |
          +-- return malformed bytes -->
          |     ClassFormatError / VerifyError at load/verify step
          |     class may NOT have been defined yet
          |
          +-- return valid bytes -->
                JVM verifies and defines class
                        |
                        v
                 new Target() succeeds
                        |
                        v
                 target.work() calls MissingProbe.mark()
                        |
                        v
                 NoClassDefFoundError if helper is absent
~~~

**Distinguish the boundary:** **invalid** bytes are rejected at class definition, whereas bytes that have already been defined **may** only trigger an error upon invocation due to lazy resolution, helper visibility, or new logic. Resolution timing can differ across JVMs, so you must rely on actual runtime milestones.

## 3. Java SE 17 Contract of premain

Manifest for an agent run with `-javaagent`:

~~~text
Premain-Class: demo.DiagAgent
~~~

The JVM looks up this entry point first:

~~~java
public static void premain(
        String agentArgs,
        Instrumentation instrumentation) {
    // Initialize the agent.
}
~~~

If this overload is not present, the JVM looks for:

~~~java
public static void premain(String agentArgs) {
    // Does not receive Instrumentation as a parameter.
}
~~~

The two snippets above **illustrate signatures**, not two methods that must both exist. `premain` requires `public static void` with the exact parameters. The JVM invokes `premain` after JVM bootstrap, **before application main**, and the method must return for startup to proceed.

Per the Java SE 17 `java.lang.instrument` specification:

- If the JVM fails to start the agent (missing class, non-conformant method, invalid manifest, etc.), the JVM **aborts**.
- If `premain` throws an uncaught exception, the JVM **aborts**.
- Multiple `-javaagent` options on the command line have their `premain` invoked in the order specified.
- Declaring only `Agent-Class` does not cause `-javaagent` to fall back to invoking `agentmain`.

**Diagnosis:** if no application startup logs appear, inspect **the actual deployed JAR**, the main manifest, the agent class loader, the root exception, and the process exit code. Do not use a generic "Java application startup failed" message alone to infer a malformed classfile.

### 3.1. Fail-Fast and Fail-Open in premain

A **mandatory policy agent** can deliberately fail-fast if it lacks the capability to instrument. An **optional telemetry agent** can choose to log the error, disable probes, and return safely so as not to block application startup. This is an **operational decision**, not automatic JVM semantics.

Avoid "catch Throwable and ignore all errors" in production; `OutOfMemoryError`, VM errors, or classloader recursion can leave the system in an unreliable state. If choosing a fallback, explicitly log the `agent:disabled` outcome and control any side effects already created.

## 4. agentmain, Attach API, and the Launcher Agent Exception

Manifest for an agent using dynamic attach:

~~~text
Agent-Class: demo.DiagAgent
~~~

The JVM looks up first:

~~~java
public static void agentmain(
        String agentArgs,
        Instrumentation instrumentation) {
    // Initialize the agent in the running JVM.
}
~~~

If there is no overload with `Instrumentation`, the JVM looks for `agentmain(String)`.

### 4.1. Target Errors and Attach Caller Errors Are Not on the Same Thread

During dynamic attach, the target JVM already has `Main.main` and business threads running. If `agentmain` throws an uncaught exception, per Java SE 17 **the target JVM does not abort because of that error**. However, the JVM may log a stack trace, and the tool calling `VirtualMachine.loadAgent` may have thrown to it:

- `AgentLoadException` — the JAR/agent could not be loaded as requested.
- `AgentInitializationException` — the agent was requested to load, but failed to initialize.
- `IOException` — communication, attach operation, or I/O error.

**Do not confuse with an application exception:** `AgentInitializationException` is raised to **the caller of `loadAgent`**, and does not automatically become an exception in a business thread of the target JVM. If self-attach is used in a lab, `main` is also the caller so that we can observe this directly.

### 4.2. Launcher-Agent-Class Changes the Conclusion

Java SE 17 can run an executable JAR with a main manifest:

~~~text
Launcher-Agent-Class: demo.DiagAgent
~~~

The launcher selects `agentmain` but invokes it **before application main**. If the class/method cannot be loaded or `agentmain` throws an uncaught exception/error, **the JVM aborts**. Therefore:

| How it starts | Manifest | JVM invokes | Uncaught entry point error |
|---|---|---|---|
| `-javaagent` on command line | `Premain-Class` | `premain` | **JVM aborts before main** |
| Dynamic attach after JVM is running | `Agent-Class` | `agentmain` | **Target JVM does not abort solely due to attach error** |
| Executable JAR launcher agent | `Launcher-Agent-Class` | `agentmain` | **JVM aborts before main** |

**Rule:** do not use the string "agentmain" in a stack trace to conclude it is an attach error without checking the manifest, command line, and JVM lifecycle.

### 4.3. Runtime Support for Attach Is a Separate Question

Dynamic attach also depends on the JDK vendor, the `jdk.attach` module, OS/PID permissions, container policy, and VM flags. On HotSpot, `-XX:+EnableDynamicAgentLoading` controls dynamic agent loading; starting with JDK 21, the JVM emits a warning if an agent is loaded dynamically without opt-in per JEP 451. Self-attach on some HotSpot JDKs requires the property `-Djdk.attach.allowAttachSelf=true`.

These flags only determine **whether attach can be requested**; they do not fix `agentmain` bugs, do not verify bytecode, and do not automatically allow a transformer to make arbitrary schema changes.

## 5. Transformer Throwing vs. Returning Malformed Bytes

`ClassFileTransformer` has the `transform` callback to process a classfile before the JVM defines, retransforms, or redefines it. A transformer can:

- Return `null` if no transformation is made.
- Return a `byte[]` array containing a **well-formed** transformed classfile.
- Throw an exception, including `IllegalClassFormatException` when the input classfile is malformed.

**Per the Javadoc**, if a transformer throws an uncaught exception, the JVM still invokes the remaining transformers in order and still attempts to load/redefine/retransform the class; for that transformer, the effect is equivalent to **returning null**. Therefore, **throwing inside a transformer is not guaranteed to reject class loading**.

### 5.1. Same Exception, Different Lifecycles

~~~java
throw new IllegalStateException("demo-failure");
~~~

If this line escapes **`premain`** uncaught → the JVM aborts startup. If it escapes **`transform`** → the JVM continues the pipeline, and the class can still load normally. If it escapes **`agentmain` during dynamic attach** → the attach caller may receive an error, but the target does not abort from the attach error itself.

**Always identify the originating method/callback from the stack trace and timestamp.**

### 5.2. Malformed Bytes Are Not Installed Bytes

~~~java
return new byte[] {1, 2, 3};
~~~

This array lacks the `CAFEBABE` magic number and valid classfile structure. If these are the final bytes, the JVM may report `ClassFormatError` at class definition. When bytecode is structurally well-formed but the verifier detects invalid stack frames or operand stacks, `VerifyError` may occur.

**Merely logging that the transformer returned bytes is not enough.** You need evidence that the VM defined the class, or for `redefineClasses/retransformClasses`, that the API call completed normally.

### 5.3. Valid Bytes Can Still Have Linkage Errors

If V2 was compiled against `MissingProbe.mark()` but the target JVM cannot see the helper, class definition may succeed, and only upon invoking `Target.work()` will `NoClassDefFoundError` occur. If the helper class exists but has the wrong method descriptor, `NoSuchMethodError` may occur. If the target lacks permission to access the helper, `IllegalAccessError` may occur.

**These are post-installation errors**, distinct from `ClassFormatError` at the verify/define step. Not all VMs resolve dependencies at the exact same point, so keep the `class-defined` and `method-invoked` milestones separate.

## 6. Symptom-Based Triage Table

| Symptom | Suspect first | Evidence to collect |
|---|---|---|
| Process aborts, application `main` did not print a single line | `Premain-Class`, `premain`, or startup loader | Manifest, stderr, exception, exit code |
| Application already running, `loadAgent` reports `AgentInitializationException` | `Agent-Class` / dynamic `agentmain` | Caller stack, Attach Listener logs, target PID still alive |
| `agentmain` throws and JVM aborts before main | May be using `Launcher-Agent-Class` | Executable JAR manifest, launch method |
| Transformer callback throws, yet target V1 runs | Callback exception treated as returning `null` | Callback log + actual class bytes/behavior |
| Transformer returns bytes, `ClassFormatError` | Final bytes malformed, class not defined | Classfile, verifier, class definition marker |
| `VerifyError` | Invalid stack maps/instructions/frames | Bytecode dump, full verifier output |
| Object created, method reports `NoClassDefFoundError` | Helper missing or cannot be loaded | Defining class loader/module, runtime classpath |
| Method reports `NoSuchMethodError` | Runtime helper has different version/descriptor | `javap -p -s`, dependency versions |
| Method reports `IllegalAccessError` | Runtime access/module/package visibility | Target/module identity and exports/opens |
| Instrumentation prints expected logs, yet result is wrong | Installed bytecode altered semantics | Return value, exception flow, side effects |
| No transformer callback observed | Target loaded earlier or wrong filter/registration | Agent entry timestamps, class name/loader |
| JVM still running, yet probe does not appear | Agent may have failed-open or transform was skipped | Entry log, callback outcome, runtime trace |

Each row is a **diagnostic direction**, not a one-to-one mapping. For example, the same `NoClassDefFoundError` can happen immediately when the JVM loads an agent class because the agent JAR is missing a dependency, or only when an instrumented method references a missing helper. **Timing** matters more than the exception name.

## 7. Complete Demo: Five Modes in One Java 17 Source Set

This lab uses a single agent JAR containing both `premain` and `agentmain`. We compile with `javac --release 17` and test on JDK 24.0.2 with `-Xverify:all`.

Directory structure:

~~~text
agent-diagnostics-lab/
├── agent.mf
├── src/
│   ├── agent/
│   │   └── demo/DiagAgent.java
│   ├── app/
│   │   └── demo/Main.java
│   │   └── demo/Target.java        # V1
│   ├── v2/
│   │   └── demo/Target.java        # V2 missing helper at runtime
│   └── helper/
│       └── demo/MissingProbe.java  # provided only when compiling V2
└── out/
    ├── agent/
    ├── app/
    ├── v2/
    └── diag-agent.jar
~~~

The two `demo.Target` sources intentionally share the same binary name and must be compiled into **two separate output directories**. When running, the JVM only puts `out/app` on the classpath; V2 is read by the agent as bytes from `out/v2/demo/Target.class`. Do not add `out/v2` to the runtime classpath, because doing so would allow the helper to be loaded and defeat the runtime linkage experiment.

### 7.1. Agent: src/agent/demo/DiagAgent.java

~~~java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.ProtectionDomain;

public final class DiagAgent {
    public static void premain(String options, Instrumentation inst)
            throws Exception {

        String mode = options == null ? ""
                : options.split(":", 2)[0];
        System.out.println("agent:premain mode=" + mode);

        if ("fail".equals(mode)) {
            throw new IllegalStateException(
                    "premain-demo-failure");
        }

        if ("throws".equals(mode)
                || "badclass".equals(mode)
                || "installed".equals(mode)) {

            final byte[] replacement = "installed".equals(mode)
                    ? Files.readAllBytes(Path.of(
                            options.substring("installed:".length())))
                    : null;

            inst.addTransformer(new ClassFileTransformer() {
                @Override
                public byte[] transform(
                        ClassLoader loader,
                        String name,
                        Class<?> redefined,
                        ProtectionDomain domain,
                        byte[] original) {

                    if (!"demo/Target".equals(name)) {
                        return null;
                    }

                    System.out.println(
                            "agent:transform mode=" + mode);

                    if ("throws".equals(mode)) {
                        throw new IllegalStateException(
                                "transform-demo-failure");
                    }

                    if ("badclass".equals(mode)) {
                        return new byte[] {1, 2, 3};
                    }

                    return replacement;
                }
            }, false);
        }

        System.out.println("agent:premain-ready");
    }

    public static void agentmain(
            String options, Instrumentation inst) {
        System.out.println(
                "agent:agentmain mode=" + options);

        if ("fail".equals(options)) {
            throw new IllegalStateException(
                    "agentmain-demo-failure");
        }

        System.out.println("agent:agentmain-ready");
    }
}
~~~

**Full explanation:**

- `premain` takes `Instrumentation` and parses the option `fail`, `throws`, `badclass`, or `installed:<path>`.
- `fail` throws **inside the entry point**. The JVM has not transitioned to application main.
- The other three modes register a transformer that filters for the exact class name `demo/Target`. `name` in the callback uses slashes, not `demo.Target`.
- `throws` throws an unchecked exception inside the **transform callback**, not the entry point.
- `badclass` returns intentionally malformed classfile bytes.
- `installed` returns precompiled V2 class bytes that reference a helper unavailable at runtime.
- `agentmain` is invoked via dynamic attach and intentionally throws to show the difference from `premain`.
- The callback returns `null` for all other classes to avoid self-instrumentation and bootstrap recursion.
- Retransformation is not registered; the example only instruments **when target is loaded for the first time**. `Can-Retransform-Classes` and `Can-Redefine-Classes` are not needed.

**Do not run `badclass` or `throws` modes in production.** These failures are placed in a sandbox to demonstrate the transformer contract.

### 7.2. Target V1: src/app/demo/Target.java

~~~java
package demo;

public final class Target {
    public void work() {
        System.out.println("target:v1");
    }
}
~~~

This is the class the app loads on `new Target()`. If the transformer does not replace the bytes, `work()` prints `target:v1`.

### 7.3. Main: src/app/demo/Main.java

~~~java
package demo;

import com.sun.tools.attach.AgentInitializationException;
import com.sun.tools.attach.VirtualMachine;

public final class Main {
    public static void main(String[] args) throws Exception {
        String mode = args[0];
        System.out.println("main:begin mode=" + mode);

        if ("attach".equals(mode)) {
            VirtualMachine vm = VirtualMachine.attach(
                    Long.toString(ProcessHandle.current().pid()));

            try {
                vm.loadAgent(args[1], "fail");
                System.out.println("main:attach-returned");
            } catch (AgentInitializationException expected) {
                System.out.println("main:attach-error="
                        + expected.getClass().getSimpleName());
            } finally {
                vm.detach();
            }

            System.out.println("main:still-running");
            return;
        }

        try {
            System.out.println("main:before-target");
            Target target = new Target();
            System.out.println("main:target-defined");
            target.work();
            System.out.println("main:target-success");
        } catch (LinkageError expected) {
            System.out.println("main:linkage-error="
                    + expected.getClass().getSimpleName());
        }

        System.out.println("main:still-running");
    }
}
~~~

**Milestones to read:**

- `main:begin` = the application has actually entered main. With a `premain` error, this line does not appear.
- `main:before-target` = about to load/instantiate Target.
- `main:target-defined` = `new Target()` succeeded. If an error occurs afterward, we know the target object was created in the JVM.
- `main:linkage-error=...` = the test harness intentionally catches `LinkageError` to print the error type without killing the process.
- `main:still-running` = the JVM/application continues running in the test; it does **not** by itself prove instrumentation succeeded.
- `mode=attach` uses the JDK Attach API `com.sun.tools.attach.VirtualMachine`. This is a JDK-specific API documented in the `jdk.attach` module, not part of portable Java SE core. Self-attach depends on permissions/runtime settings.

**Do not catch `LinkageError` globally in a production application** as a way to avoid system failure; this is an isolated test harness for comparing phases.

### 7.4. Compile-Time Helper: src/helper/demo/MissingProbe.java

~~~java
package demo;

public final class MissingProbe {
    public static void mark() {
        System.out.println("probe:mark");
    }
}
~~~

### 7.5. V2: src/v2/demo/Target.java

~~~java
package demo;

public final class Target {
    public void work() {
        MissingProbe.mark();
        System.out.println("target:v2");
    }
}
~~~

V2 compiles successfully because `MissingProbe` is present in **output `out/v2` at build time**. However, the runtime classpath only contains `out/app`, so `MissingProbe` **is not loaded from `out/v2`**. The V2 classfile is still valid; the error occurs when the instruction calling the helper needs resolution.

Depending on the JVM and classloader, resolution may be eager or lazy at different points; the **specific result in the JDK 24.0.2 test** is that the instance is created first and then `NoClassDefFoundError` occurs when invoking `work()`.

### 7.6. Agent JAR Manifest

File **`agent.mf`** with a trailing newline:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.DiagAgent
Agent-Class: demo.DiagAgent

~~~

`Launcher-Agent-Class` is omitted in this example to focus on the two paths: `-javaagent` startup and dynamic attach.

## 8. Building with JDK 17 or Later

Create output directories. Bash:

~~~bash
mkdir -p out/agent out/app out/v2
~~~

PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out/agent, out/app, out/v2
~~~

At the `agent-diagnostics-lab` root directory, compile:

~~~bash
javac --release 17 -d out/agent src/agent/demo/DiagAgent.java
javac --release 17 --add-modules jdk.attach -d out/app src/app/demo/Main.java src/app/demo/Target.java
javac --release 17 -d out/v2 src/v2/demo/Target.java src/helper/demo/MissingProbe.java
jar --create --file out/diag-agent.jar --manifest agent.mf -C out/agent .
~~~

**Build explanation:**

- `--release 17` produces Java 17-compatible classfiles and restricts APIs to that release.
- `--add-modules jdk.attach` is required for `Main` source code referencing the Attach API in a suitable JDK environment.
- `out/app` contains Main and Target V1.
- `out/v2` contains Target V2 along with the helper for building, but is not on the runtime classpath.
- `out/agent` is packaged into a JAR containing `DiagAgent.class` and the manifest.
- The agent and app are compiled separately; `DiagAgent` does not depend on ASM/Byte Buddy so no other dependencies are needed.

Inspect artifacts:

~~~bash
jar --list --file out/diag-agent.jar
javap -p -s -classpath out/app demo.Target
javap -p -s -classpath out/v2 demo.Target
javap -c -p -classpath out/v2 demo.Target
~~~

`javap -c` on V2 shows that method `work` has bytecode calling `MissingProbe.mark`. This is evidence that the compile-time dependency exists in the V2 classfile; it **does not guarantee** the helper will exist in the runtime classloader.

## 9. Testing Four Startup and Bytecode Modes

### 9.1. Test A — premain Throw Causes JVM Abort

~~~bash
java -Xverify:all -javaagent:out/diag-agent.jar=fail -cp out/app demo.Main normal
~~~

**Observed stdout markers:**

~~~text
agent:premain mode=fail
~~~

Afterward, the VM reports an agent startup failure on stderr; the process had **exit code 1** in the JDK 24.0.2 test. **There is no** `agent:premain-ready`, `main:begin`, or `main:target-defined`.

Meaning: the failure is in **premain/agent startup**. Each JVM's stderr message/fatal details may vary; you do not need to exact-match the entire fatal trace to classify it.

### 9.2. Test B — Transformer Throws, Yet App Still Runs V1

~~~bash
java -Xverify:all -javaagent:out/diag-agent.jar=throws -cp out/app demo.Main normal
~~~

**Observed stdout:**

~~~text
agent:premain mode=throws
agent:premain-ready
main:begin mode=normal
main:before-target
agent:transform mode=throws
main:target-defined
target:v1
main:target-success
main:still-running
~~~

The agent entry point returned. The transformer threw when Target loaded, but the JVM treated this transformer as returning `null`; with the lab's simple pipeline, class V1 still loads and `work()` prints `target:v1`.

**Do not generalize** that every throwable from every JVM phase is ignored. This is solely the transformer callback contract. Other transformers could still return malformed bytes or the agent could have caused its own side effects.

### 9.3. Test C — Malformed Bytes, Class Not Defined

~~~bash
java -Xverify:all -javaagent:out/diag-agent.jar=badclass -cp out/app demo.Main normal
~~~

**Observed stdout:**

~~~text
agent:premain mode=badclass
agent:premain-ready
main:begin mode=normal
main:before-target
agent:transform mode=badclass
main:linkage-error=ClassFormatError
main:still-running
~~~

`main:target-defined` is not printed. The JVM cannot define Target from malformed bytes; the error is caught by the test harness and application main continues. In production without a catch, the thread/process may be impacted along the call path.

**This is not evidence that an installed method threw an error.** It failed **before the class definition milestone**.

### 9.4. Test D — Valid Classfile Defined, Invocation Fails with Linkage Error

~~~bash
java -Xverify:all -javaagent:out/diag-agent.jar=installed:out/v2/demo/Target.class -cp out/app demo.Main normal
~~~

**Observed stdout:**

~~~text
agent:premain mode=installed
agent:premain-ready
main:begin mode=normal
main:before-target
agent:transform mode=installed
main:target-defined
main:linkage-error=NoClassDefFoundError
main:still-running
~~~

The line `main:target-defined` appears before the error, proving `new Target()` completed in the test JVM. Afterward, V2 `Target.work()` calls `MissingProbe.mark` and throws `NoClassDefFoundError` because the runtime cannot find the helper.

**The proper fix:** ensure the helper class is present in a loader/module that the target can legally link against, or avoid inserting that reference. Changing `Premain-Class`, indiscriminately adding `--add-opens`, or just catching exceptions inside the transformer is not a solution for a missing helper class.

## 10. Testing agentmain Dynamic Attach

Self-attach is only a **convenience for creating a single-process demo**. On JVMs that do not support self-attach, switch to a separate tool process and target PID using the Attach API. On the tested HotSpot JDK 24, the command needs to allow self-attach and dynamic loading.

**Bash:**

~~~bash
agentJar="$(pwd)/out/diag-agent.jar"
java -Xverify:all --add-modules jdk.attach -Djdk.attach.allowAttachSelf=true -XX:+EnableDynamicAgentLoading -cp out/app demo.Main attach "$agentJar"
~~~

**Windows PowerShell:**

~~~powershell
$agentJar = (Resolve-Path 'out/diag-agent.jar').Path
java -Xverify:all --add-modules jdk.attach '-Djdk.attach.allowAttachSelf=true' '-XX:+EnableDynamicAgentLoading' -cp out/app demo.Main attach $agentJar
~~~

Putting `-D...`/`-XX...` flags in single quotes as above helps PowerShell pass the arguments verbatim to `java`. In Bash, quote the agent JAR path to handle directories with spaces. The agent JAR path passed to `VirtualMachine.loadAgent` must be accessible by the target JVM.

**Stdout lines to compare against:**

~~~text
main:begin mode=attach
agent:agentmain mode=fail
main:attach-error=AgentInitializationException
main:still-running
~~~

On the specific JDK 24.0.2 test, the exit code is **0** because `Main` catches `AgentInitializationException` and returns normally, while the JVM logs an **Attach Listener** stack trace and an agent-failed-to-start message on stderr. Internal log details should not be exact-matched because they vary by JDK build/vendor.

**The right conclusion:** dynamic `agentmain` **did not initialize successfully**, yet the target JVM **remained alive** after the failed call. Exit code 0 of the **test application** does not prove the agent attached successfully.

If self-attach is blocked **before invoking `agentmain`**, you may encounter `AttachNotSupportedException` or `IOException`; that is an **attach transport/policy** error. Do not treat that scenario as a test of the uncaught `agentmain` contract.

## 11. "Installed Bytes" Errors and Different Root Causes

### 11.1. Do Not Equate Format/Verification with Runtime Linkage

| Error type | Typical timing | Cause |
|---|---|---|
| `ClassFormatError` | Reading classfile during define | Malformed magic/constant pool/structure |
| `VerifyError` | Bytecode verification before execution | Invalid stack maps, operand stack, control flow/types |
| `NoClassDefFoundError` | Class resolution/linkage, possibly at invocation | Helper class missing or cannot be loaded |
| `NoSuchMethodError` | Method resolution | Runtime class lacks the called descriptor |
| `IllegalAccessError` | Access check/linkage | Type/member/package/module not accessible |
| `ExceptionInInitializerError` | Class initialization | Static initializer throws an exception |
| `NullPointerException` in probe | Execution | Bytecode/helper logic fails to handle null |
| `StackOverflowError` in probe | Execution | Instrumented method calls helper, helper calls method back causing recursion |
| `UnsupportedClassVersionError` | Class load/define | Classfile major version newer than VM supports |
| `UnmodifiableClassException` | Retransform/redefine API | Class is not modifiable |
| `UnsupportedOperationException` | Retransform/redefine API | VM does not support capability/schema change |

The same class can pass verification and definition while resolution of its symbolic references is deferred. Therefore, **a successful `ClassFileTransformer.transform` log line is not confirmation that the business method is safe**.

### 11.2. When Multiple Transformers Exist

If one transformer throws, other transformers can still be invoked. The final bytes of the chain are what the VM checks. When investigating, record:

- transformer registration order and `canRetransform`;
- target binary name and class loader;
- hash/size of input bytes and output bytes (do not arbitrarily log raw bytes);
- which transformer returned `null`, threw an exception, or returned new bytes;
- whether the final verify/redefine step returned successfully or failed;
- whether new invocations are using the new definition.

Never print `class-defined=true` directly inside the callback before the VM verifies/defines the class.

### 11.3. Class Loader, Module, and Helper Visibility

If the target class is from the bootstrap loader, a helper on the system classloader is not automatically visible. If the target belongs to a named module, it may need to read the helper's module and have the package exported; `Instrumentation.redefineModule` only changes module relationships, and does not make a missing helper class appear. If shading relocates the helper package, injected bytecode must use the packaged internal names/descriptors.

Before fixing with launcher flags, verify whether **the class actually exists** and is visible to the target's loader.

## 12. Five-Milestone Investigation Workflow

### Milestone 1 — Which entry point was invoked?

Check how it was launched:

~~~text
-javaagent:...             -> Premain-Class -> premain
VirtualMachine.loadAgent   -> Agent-Class   -> agentmain
Launcher-Agent-Class       -> agentmain in executable JAR startup
~~~

Read **the manifest inside the actual JAR**, not an unpackaged source manifest file. With multiple agents, record the `-javaagent` order and versions.

### Milestone 2 — Has application main started yet?

Is there a `main:start` milestone? If not, inspect `premain` and the JVM launcher. If yes, move on to attach/class loading/probe. Do not blame startup just because you see an agent stack frame.

### Milestone 3 — Did agentmain run in the target JVM?

Collect the caller exception `AgentLoadException`/`AgentInitializationException`/`IOException` and stderr of the **target JVM**, and check permissions, PID, provider, and vendor/runtime policy. If `agentmain` ran and then threw, inspect **side effects that occurred before the throw**.

### Milestone 4 — Was the class verified/defined?

- Which transformers were invoked?
- Did any return malformed bytes, return null, or throw?
- Did the JVM report `ClassFormatError`/`VerifyError` before object creation?
- For `redefineClasses/retransformClasses`, did the API return normally?
- Did object creation succeed?
- Have new invocations run yet?

If bytes were installed, examine **linkage and business semantics**, not just the verifier.

### Milestone 5 — Where did the method/probe fail?

If the target instance was created but the method fails, inspect symbolic references to helpers, method descriptors, module reads/exports, classloader visibility, recursion, exception flow, and return value. Use `javap` to inspect build artifact bytecode; if absolute precision on runtime bytes is needed, capture them using permitted diagnostics.

Tools:

~~~bash
jar --list --file out/diag-agent.jar
javap -v -p out/v2/demo/Target.class
jdeps --jdk-internals out/diag-agent.jar
~~~

With HotSpot, unified logging such as `-Xlog:class+load=info` can help when debugging class loading. Output can be very large; enable it only in controlled environments or time windows.

## 13. Post-Failure Handling and Rollback

### 13.1. Uncaught premain Error: There May Be No Running Application to Roll Back

Because a `premain` throw aborts startup, you must fix the agent JAR/config and restart the process. However, if `premain` already modified files, opened sockets, or caused external side effects before throwing, startup abort does not automatically undo those actions.

### 13.2. agentmain Error: A Live Process Is Not Guaranteed Clean

A dynamic agent may have already registered a transformer, altered module relationships, or replaced definitions before throwing an exception. The JVM does not abort per the attach contract, but it does not automatically roll back side effects. A production agent should structure initialization in phases, report `ready/failed/degraded` status, and have explicit cleanup for cleanable resources.

### 13.3. Transformer Throw: No Transformation from That Callback

If a transformer throws, it is equivalent to `null` for that transform step; however, logging or side effects may have already occurred before the throw. Other transformers may still produce new bytes; do not conclude the entire class was left unmodified.

### 13.4. Malformed Classfile Bytes Rejected

When class definition fails with `ClassFormatError`, an instance may not have been created; you do not "undo installed bytecode" with `removeTransformer`. You must fix the transformer/replacement bytes and reproduce in a valid class loading attempt, typically with a fresh JVM or a new class loader in a test environment.

### 13.5. Installed Bytes Where the Method Fails

Removing a transformer does not revert a class back to V1. To roll back a definition on an already-loaded class, you need the appropriate capabilities and baseline bytes for `redefineClasses`/`retransformClasses`. For currently executing methods, active frames may retain old bytecode while new invocations use the new definition. You must test both field state and in-flight requests.

**Do not report `instrumentation=SUCCESS` just because the agent entry point returned**; verify class definition/update and that invocations actually behave correctly.

## 14. Fail-Fast, Fail-Open Policies and Recommended Logging

### 14.1. Fail-Fast or Fail-Open Depending on Goal

| Agent type | Priority principle |
|---|---|
| Mandatory security / policy enforcement | Fail-fast if safety conditions cannot be guaranteed; never silently skip checks |
| Optional telemetry/metrics | Can fail-open in a controlled way, log agent disabled, and avoid breaking business logic |
| Business logic hotfix | Only declare successful cutover after API update succeeds and new invocations pass smoke tests |
| Dynamic troubleshooting agent | Limit scope, control attach permissions, record partial side effects |
| Agent handling multiple classes | Distinguish single-class errors from whole-agent session errors; check atomicity of each API |

An **illustrative** pattern, not standalone since helpers are undeclared:

~~~java
public static void premain(String args, Instrumentation inst) {
    try {
        installOptionalProbes(inst);
        reportStatus("READY");
    } catch (Exception e) {
        reportError(e);
        if (requiredByPolicy()) {
            throw new IllegalStateException(
                    "Required instrumentation failed", e);
        }
        reportStatus("DISABLED");
    }
}
~~~

Do not "catch Throwable and ignore everything" when `OutOfMemoryError`/VM failures occur. When failing open, ensure partially installed hooks do not leave the application running in a dangerous state.

### 14.2. Lifecycle-Correlated Logging

A suggested event structure:

~~~text
agent.jar.sha256=...
agent.mode=PREMAIN | AGENTMAIN | LAUNCHER_AGENTMAIN
agent.phase=ENTER | READY | ERROR
agent.pid=...
agent.jvm.version=...
target.class=demo.Target
target.loader=...
transform.phase=CALLBACK | RETURN_NULL | RETURN_BYTES | CALLBACK_ERROR
define.phase=REJECTED | DEFINED
invoke.method=demo.Target.work()V
invoke.outcome=SUCCESS | LINKAGE_ERROR | BUSINESS_ERROR
~~~

This is a **log template**, not lab output. Do not emit `define.phase=DEFINED` inside the callback without evidence that the JVM actually defined the class. Limit log volume, avoid recursion on the class loading path, and do not push raw bytecode/secrets into logs.

### 14.3. What to Test in CI

- Agent JAR has the right manifest entry points.
- Agent dependencies are actually packaged/visible in the target loader.
- `premain` validation failure produces a clear outcome before application main.
- `agentmain` error produces a warning/caller exception while the target process survives.
- Transformer throw is not mistaken for policy enforcement.
- Malformed bytes are rejected by the verifier in a **sandbox**.
- Valid transformed bytes have no unresolved helpers or wrong method descriptors.
- Test across the JVM runtime matrix and accurate module/classloader topology.
- Run with `-Xverify:all`, checking stdout/stderr, exit code, and service behavior.

## 15. Common Misconceptions

**1. "Just seeing `premain` print a log means agent startup succeeded."** False: `premain` can print and then throw, causing the JVM to abort.

**2. "An `agentmain` error always kills the target application."** False for dynamic attach; note that launcher agent mode must be considered separately if it runs before main.

**3. "Exit code 0 means the agent attached successfully."** False: the application can catch `AgentInitializationException` and return normally.

**4. "A transformer throwing prevents class loading."** False: a callback exception is equivalent to returning null for that transformer.

**5. "Once a transformer returns bytes, the JVM has installed them."** False: the parser/verifier can reject them.

**6. "Once a class is defined, every method can always run."** False: symbolic resolution and helper loading can fail at invocation time.

**7. "`ClassFormatError` is always a post-method-execution error."** False: it typically relates to classfile structure during definition.

**8. "`NoClassDefFoundError` only means a missing agent JAR."** False: the error can be an app dependency, an injected helper, or a classloader/module issue.

**9. "Removing a transformer rolls back existing bytecode."** False: it only changes future registration/pipeline; definitions currently in use are not automatically undone.

**10. "Just adding `--add-opens` fixes every linkage error."** False: module access flags do not create a missing helper class.

**11. "Having `Agent-Class` makes `-javaagent` invoke `agentmain`."** False: `-javaagent` uses `Premain-Class`.

**12. "Attach succeeding on this JDK means every JDK/container allows attach."** False: attach is implementation- and policy-dependent, and must be tested on the target runtime.

## 16. Exercises and Review Questions

### Exercise A — Identifying premain Failure

Run `fail` mode. Why is `main:begin` not printed? If the agent is optional telemetry, how should config/exception handling be changed so the JVM can run in a **designed** degraded state?

### Exercise B — Distinguishing Callback Throw from Fail-Fast

Run `throws` mode and locate `target:v1`. Why is an exception inside a transformer not a supported class-blocking mechanism? If the agent is a mandatory policy component, what conditions must be verified before declaring the app ready?

### Exercise C — Class Definition or Method Execution?

Compare stdout of `badclass` and `installed`. Which line proves the JVM created an instance of Target? Why must `ClassFormatError` and `NoClassDefFoundError` in these two modes be investigated in two different directions?

### Exercise D — Fixing Helper Visibility

In the `installed` lab, try adding `MissingProbe.class` to the runtime classpath visible from Target. If all other conditions are right, the V2 method can print `probe:mark` and then `target:v2`. This shows the original V2 classfile was **not malformed**, only missing a dependency at runtime.

### Exercise E — Attach Error and Target Health

Run `attach` mode on a JDK supporting self-attach. Why does `AgentInitializationException` appear while `main:still-running` is still printed? Does that prove the agent left completely zero side effects?

### Exercise F — Launcher-Agent-Class

If an executable JAR has `Launcher-Agent-Class` and `agentmain` throws an uncaught exception before application main, how does the outcome differ from dynamic attach? **Answer:** the launcher JVM aborts startup.

### Exercise G — Error After Redefinition

An agent calls `redefineClasses` successfully and then a new invocation hits `NoSuchMethodError`. Should you report `premain startup failed`? **No**: the error is in the linkage of the installed code. Inspect the helper method descriptor, loader/module, and rollback strategy.

### Quick Questions

1. **Entry point for `-javaagent`?** — `premain`.
2. **Entry point for dynamic attach?** — `agentmain` from `Agent-Class`.
3. **Uncaught `premain` exception?** — JVM aborts before main.
4. **Uncaught dynamic `agentmain` exception?** — Target JVM does not abort due to the attach error; caller may receive an exception.
5. **Which method does `Launcher-Agent-Class` use?** — `agentmain`, but at startup.
6. **What is a transformer throw equivalent to?** — Returning `null` for that transformer.
7. **Returning malformed classfile bytes?** — Can cause `ClassFormatError`/`VerifyError` before definition.
8. **Definition succeeds, but helper missing at invoke time?** — Can cause `NoClassDefFoundError`.
9. **Does the target's class loader matter?** — Yes; it determines helper visibility.
10. **Does `-Xverify:all` prove there are no runtime linkage errors?** — No.
11. **Where does `AgentInitializationException` appear?** — On the caller side of `VirtualMachine.loadAgent`.
12. **Does `removeTransformer` undo already-installed bytecode?** — No.
13. **What must be checked before declaring rollback successful?** — Update result, new invocations, active frames, and app state.

## 17. Final Checklist and References

### Technical Preflight

- [ ] Determine whether `-javaagent`, dynamic attach, or executable launcher agent is used.
- [ ] Read the manifest inside the final JAR; verify `Premain-Class`, `Agent-Class`, or `Launcher-Agent-Class`.
- [ ] Check entry point signatures and dependencies.
- [ ] Log `premain/agentmain enter/ready/fail` status with PID/JVM version.
- [ ] Collect stdout, stderr, exit code, and process liveness.
- [ ] Verify runtime/permission support for dynamic attach.
- [ ] Explicitly specify transformer order, class loader, module, and target name.
- [ ] Distinguish callback exceptions, malformed class bytes, verify/define, and invocation linkage.
- [ ] Verify helper classes and method descriptors in the target JVM.
- [ ] Run integration tests with `-Xverify:all`.
- [ ] Do not treat a callback returning bytes as confirmation of class installation.
- [ ] Do not let malformed bytecode tests run on production services.
- [ ] If the agent has already altered code, prepare a proper API-based rollback rather than relying on removeTransformer.
- [ ] Report success based on **exact evidence of the succeeded phase**, not a single generic boolean.

**Conclusion:** properly investigating Java Instrumentation means classifying **entry point errors**, **class transform/definition errors**, and **method linkage/execution errors**. A `premain` failure can prevent the JVM from entering application main; a dynamic attach `agentmain` failure does not abort the target per contract; a transformer throw can be ignored; malformed bytes can be rejected before definition; and valid installed bytes can still fail at invocation. Only by pinpointing the exact phase and evidence can you choose the right fix or rollback.

### Official Documentation

- [Java SE 17 — java.lang.instrument](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): `premain`, `agentmain`, `Launcher-Agent-Class`, manifest, and startup error semantics.
- [Java SE 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback, returning `null`, unchecked exceptions, transformer chain.
- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): registration, class retransform/redefine, capability checks.
- [JDK 17 — Attach API VirtualMachine](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html): `loadAgent`, agent initialization, attach/detach.
- [JDK 17 — AgentInitializationException](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/AgentInitializationException.html): load/initialization errors in the target JVM.
- [JEP 451 — Prepare to Disallow Dynamic Loading of Agents](https://openjdk.org/jeps/451): warnings and HotSpot opt-in for dynamic loading.
- [JVMS Java SE 17 — Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): classfile format, verifier constraints.
- [JVMS Java SE 17 — Loading, Linking, Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): verification, resolution, and linkage timing.
