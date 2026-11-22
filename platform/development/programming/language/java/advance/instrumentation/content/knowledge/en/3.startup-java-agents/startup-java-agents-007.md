# Agent loading errors, wrong signatures, and uncaught exceptions can prevent the JVM from starting

> **Scenario:** A Java application runs normally with `java App`, but when `-javaagent:agent.jar` is added, the JVM stops before entering `App.main`. For an agent loaded **at startup**, this is specified behavior: if the JVM fails to initialize the agent or `premain` throws an uncaught exception, **the JVM must abort startup**. An observability agent still runs inside the target JVM and therefore can become a gate for whether the entire application is allowed to start.

This lesson focuses on the **agent startup point**, how to distinguish packaging errors and wrong signatures from runtime errors, Java 17+ experiments, how to find root causes from logs, and how to deliberately choose between *fail fast* and *degrade gracefully* behavior.

## 1. What happens before `main`?

With the command:

~~~bash
java -javaagent:agent.jar=mode=demo App
~~~

The JVM processes a sequence of steps before calling `App`'s `public static void main(String[] args)`:

~~~text
Launcher receives -javaagent:agent.jar=mode=demo
  |
  v
Can it open the JAR and read META-INF/MANIFEST.MF?
  |
  v
Can it find the Premain-Class attribute?
  |
  v
Can it load/initialize the agent class and the classes it needs?
  |
  v
Can it find a valid premain signature?
  |
  v
Invoke premain("mode=demo", Instrumentation)
  |
  +--> premain completes normally --> continue application startup --> App.main
  |
  +--> initialization error / uncaught exception --> JVM aborts startup
~~~

This is the **startup agent lifecycle**. `-javaagent` instructs the JVM to load the agent and call `premain` **before `main`**; `premain` must return normally for startup to continue. If a required step fails, `main` may never have been called, so any logs, health checks, or error-handling mechanisms placed in `main` never get a chance to run.

**Distinguishing three points in time:**

| Point in time | Error examples | Key indicators |
| --- | --- | --- |
| Before calling `premain` | Wrong JAR path, missing `Premain-Class`, agent class not found, wrong signature | The first message from `premain` is not seen |
| Inside `premain` | Config parsing causes `IllegalArgumentException`, missing dependency, transformer initialization error, uncaught runtime error | Some agent logs may appear, but no `main` logs appear |
| After `premain` returns | Application throws an exception in `main`; class loading/callback error occurs later | `premain` has run; need to trace the stack trace to see if the error belongs to the application or the agent |

You should not rely solely on the word "FATAL" or a fixed exit code to identify an error; **the first meaningful log, the exception type, the JAR path, and whether `main` has started** are what help narrow it down.

## 2. Manifest and `premain` signature must match the JVM contract

A startup agent is a JAR containing the **main manifest attribute** `Premain-Class` pointing to the fully qualified binary name of the agent class. For example, if the class is `com.acme.agent.StartupAgent`, the manifest must state:

~~~text
Manifest-Version: 1.0
Premain-Class: com.acme.agent.StartupAgent
~~~

The value after `Premain-Class:` is the **Java class name**, not `StartupAgent.java`, the path `com/acme/agent/StartupAgent.class`, or the JAR name. For an agent started with `-javaagent`, having only `Main-Class` (for an executable app) or only `Agent-Class` (for a dynamic agent) **does not replace** `Premain-Class`.

The JVM tries to find the method in the following order:

~~~java
public static void premain(String agentArgs, Instrumentation inst)
~~~

If that two-parameter signature is not present, the JVM tries:

~~~java
public static void premain(String agentArgs)
~~~

The two lines above are **illustrative signatures**, not a standalone Java file. `Instrumentation` here is `java.lang.instrument.Instrumentation`.

Constraints to remember:

- The method must be **`public static void`** and named exactly **`premain`** (case-sensitive).
- The parameter order for the two-argument signature is **`String` then `Instrumentation`**; reversing the order is invalid.
- **`premain(String)` is valid**; omitting the `Instrumentation` parameter is not an error by itself. However, an agent that wants to register a transformer usually needs the two-parameter variant.
- If both variants are declared, the JVM prefers the **two-parameter** one.
- A no-arg `premain()`, `premain(Object)`, `premain(Instrumentation, String)`, an instance method, a private method, or a method with a return type other than `void` all fail to satisfy the contract.
- `agentArgs` is the **entire string** after the `=` sign on `-javaagent`; the JVM does not automatically split `mode=demo` into key/value pairs.
- The agent class and its dependencies must be loadable under the application's actual class loader/module configuration. Compiling successfully on a build machine does not guarantee the target JVM can load them.

**Why does a wrong signature stop the entire application?** The JVM cannot determine a valid agent entry point, while the startup agent is a requested part of the startup configuration. The `java.lang.instrument` specification mandates that the JVM **abort** if an agent cannot be started. This is not an exception for `App.main` to `catch`.

## 3. Classifying errors by root cause

| Category | Common symptoms | First thing to check |
| --- | --- | --- |
| **JAR does not exist, is unreadable, or is not a valid JAR** | `Error opening zip file or JAR manifest missing`, `agent library failed Agent_OnLoad`, or equivalent message | Relative/absolute path, read permissions, file type, actual file present in the deploy environment |
| **Missing/wrong `Premain-Class`** | `Failed to find Premain-Class manifest attribute` | `META-INF/MANIFEST.MF` inside the *actual deployed JAR*, main section location, and attribute name |
| **Agent class not found** | `ClassNotFoundException`; sometimes `NoClassDefFoundError` due to missing dependent classes | Fully qualified name in manifest, `.class` location, dependency packaging, and class loader |
| **Wrong `premain` signature** | `NoSuchMethodException` or reflection/instrumentation error | `public static void`, parameter types and order; inspect with `javap` |
| **Class loading incompatible with JVM** | `UnsupportedClassVersionError`, `LinkageError`, `IllegalAccessError` | Java version at compile/run time, modules, dependencies, and packaging method |
| **Exception inside `premain`** | Stack trace with `IllegalStateException`, `ExceptionInInitializerError`, or `InvocationTargetException` wrapper | First throw site in agent code; deepest `Caused by`; input configuration |
| **Agent requests an unsupported capability** | `UnsupportedOperationException` in an `Instrumentation` call or bytecode tool initialization | Manifest capabilities, `isRetransformClassesSupported()`, running JDK/JVM, and how the agent handles failure |

**Note on `NoClassDefFoundError`:** the agent class may exist in the JAR, but a dependency appearing in the signature, static initializer, or `premain` body is unavailable. Therefore, do not immediately change the `Premain-Class` name when you see the class name in the log; read the entire `Caused by` chain.

**Note on `InvocationTargetException`:** the JVM may use reflection to invoke the entry point, so the root error from `premain` may lie in the cause chain underneath. Do not treat the wrapper as the final cause.

**Note on class version errors:** for example, an agent compiled for Java 24 running on a Java 17 JVM can fail before `premain`. When Java 17+ support is needed, you can compile with `javac --release 17` and check the agent's dependencies as well, not just the entry point class.

## 4. Lab: observing success and six failure modes

The following examples are **standalone programs compilable with JDK 17+**. Place all files in the same empty directory. Save `.java` files as UTF-8 without BOM; save manifests as plain text ending with a newline (a trailing blank line can be added). The `javac`, `jar`, and `java` commands run on PowerShell, CMD, or Unix shells once a JDK is in PATH.

### 4.1. Small application to detect whether `main` runs

**`App.java`**

~~~java
public final class App {
    public static void main(String[] args) {
        System.out.println("APP_MAIN_REACHED");
        if (args.length > 0 && "fail".equals(args[0])) {
            throw new IllegalStateException("application failure");
        }
    }
}
~~~

Printing `APP_MAIN_REACHED` is the simplest evidence: if this line is **absent**, the JVM stopped before or never reached `main`; if it is **present**, at least `main` has started.

### 4.2. Valid agent with two-argument signature

**`HealthyAgent.java`**

~~~java
import java.lang.instrument.Instrumentation;

public final class HealthyAgent {
    public static void premain(String args, Instrumentation inst) {
        System.out.println("AGENT_READY: " + args);
    }
}
~~~

**`healthy.mf`**

~~~text
Manifest-Version: 1.0
Premain-Class: HealthyAgent
~~~

The trailing blank line in the manifest marks the end of the main section in the JAR manifest format; save the file so the `jar` tool reads all headers completely.

### 4.3. Agent using the one-argument signature is also valid

**`OneArgumentAgent.java`**

~~~java
public final class OneArgumentAgent {
    public static void premain(String args) {
        System.out.println("ONE_ARG_OK: " + args);
    }
}
~~~

**`one-arg.mf`**

~~~text
Manifest-Version: 1.0
Premain-Class: OneArgumentAgent
~~~

This example is important because many people misdiagnose it: not having the `Instrumentation` parameter is still a **valid entry point**.

### 4.4. Agent with wrong parameter order

**`WrongSignatureAgent.java`**

~~~java
import java.lang.instrument.Instrumentation;

public final class WrongSignatureAgent {
    // Compiles, but is NOT the premain signature required by the JVM.
    public static void premain(Instrumentation inst, String args) {
        System.out.println("WRONG_SIGNATURE");
    }
}
~~~

**`wrong-signature.mf`**

~~~text
Manifest-Version: 1.0
Premain-Class: WrongSignatureAgent
~~~

This is a *runtime contract* error: `javac` accepts a valid Java method, but JVM instrumentation cannot find `premain(String, Instrumentation)` or `premain(String)`, so **the application fails to start**.

### 4.5. Agent with a valid `premain` signature that throws an exception

**`ThrowingAgent.java`**

~~~java
import java.lang.instrument.Instrumentation;

public final class ThrowingAgent {
    public static void premain(String args, Instrumentation inst) {
        System.out.println("AGENT_START");
        throw new IllegalStateException("invalid agent config");
    }
}
~~~

**`throwing.mf`**

~~~text
Manifest-Version: 1.0
Premain-Class: ThrowingAgent
~~~

`AGENT_START` may be printed, but the unhandled `throw` statement causes the JVM to abort startup **before `App.main`**. Some JVMs display `InvocationTargetException` or internal stack traces wrapping the original exception; the message `invalid agent config` is the domain clue.

### 4.6. Agent that deliberately disables itself on recoverable configuration errors

**`GracefulAgent.java`**

~~~java
import java.lang.instrument.Instrumentation;

public final class GracefulAgent {
    public static void premain(String args, Instrumentation inst) {
        try {
            if ("bad".equals(args)) {
                throw new IllegalArgumentException("invalid agent config");
            }
            System.out.println("AGENT_READY");
        } catch (IllegalArgumentException e) {
            System.err.println("AGENT_DISABLED: " + e.getMessage());
        }
    }
}
~~~

**`graceful.mf`**

~~~text
Manifest-Version: 1.0
Premain-Class: GracefulAgent
~~~

Because `premain` **caught the expected exception and returned normally**, `App.main` still runs. However, the agent no longer guarantees instrumentation functionality: the `AGENT_DISABLED` state must be observed and handled according to policy. This approach should only be used if the absence of the agent **does not violate a mandatory requirement** of the service.

### 4.7. Two intentionally broken manifests to test pre-`premain` errors

**`missing-class.mf`** points to a class that is not packaged at all:

~~~text
Manifest-Version: 1.0
Premain-Class: MissingAgent
~~~

**`missing-entry.mf`** is completely missing the `Premain-Class` attribute:

~~~text
Manifest-Version: 1.0
~~~

Below we package `HealthyAgent.class` into these two JARs. Having a Java class present **cannot fix** a missing manifest attribute or one pointing to the wrong class.

### 4.8. Compile and build the JARs

Run sequentially from the directory containing all files:

~~~bash
javac --release 17 App.java HealthyAgent.java OneArgumentAgent.java WrongSignatureAgent.java ThrowingAgent.java GracefulAgent.java

jar --create --file healthy-agent.jar --manifest healthy.mf HealthyAgent.class
jar --create --file one-arg-agent.jar --manifest one-arg.mf OneArgumentAgent.class
jar --create --file wrong-signature-agent.jar --manifest wrong-signature.mf WrongSignatureAgent.class
jar --create --file throwing-agent.jar --manifest throwing.mf ThrowingAgent.class
jar --create --file graceful-agent.jar --manifest graceful.mf GracefulAgent.class
jar --create --file missing-class-agent.jar --manifest missing-class.mf HealthyAgent.class
jar --create --file missing-entry-agent.jar --manifest missing-entry.mf HealthyAgent.class
~~~

If `javac` or `jar` fails, fix the build/manifest error **before running** the JVM experiments. A JAR with both the class and a valid manifest **does not need** to declare `Main-Class` to be used as an agent with `-javaagent`; `App` is the class with `main`.

### 4.9. Run the test cases and explain the results

**Case A — healthy agent**

~~~bash
java -javaagent:healthy-agent.jar=ok App
~~~

**Exact stdout for this example:**

~~~text
AGENT_READY: ok
APP_MAIN_REACHED
~~~

**Case B — valid one-parameter signature**

~~~bash
java -javaagent:one-arg-agent.jar=ok App
~~~

**Stdout:**

~~~text
ONE_ARG_OK: ok
APP_MAIN_REACHED
~~~

**Case C — reversed parameter signature, Case D — throwing an exception, Case E — missing class, Case F — missing manifest entry, Case G — wrong JAR path**

~~~bash
java -javaagent:wrong-signature-agent.jar App
java -javaagent:throwing-agent.jar App
java -javaagent:missing-class-agent.jar App
java -javaagent:missing-entry-agent.jar App
java -javaagent:no-such-agent.jar App
~~~

**Run each line separately** and inspect the exit code, stdout, and stderr of each process. Expected results:

| Case | What may be observed | `APP_MAIN_REACHED`? |
| --- | --- | --- |
| C — wrong signature | `NoSuchMethodException`, `-javaagent failed` message | **No** |
| D — uncaught exception | `AGENT_START` then `IllegalStateException`/wrapper and JVM startup error | **No** |
| E — missing class | `ClassNotFoundException: MissingAgent` or agent initialization error | **No** |
| F — missing manifest entry | `Failed to find Premain-Class manifest attribute` | **No** |
| G — missing JAR file | Unable to open ZIP/JAR or agent load failure | **No** |

Specific stderr snippets, internal frame names, message placement between stdout/stderr, and exit codes **are not a stable contract across JDKs/JVMs/operating systems**. On one JVM, severe cases may show `FATAL ERROR in native method`; on another JVM the message will differ. The stable conclusion is that the startup agent failed, so `main` was not called.

**Case H — agent handles error and disables itself**

~~~bash
java -javaagent:graceful-agent.jar=bad App
~~~

Stdout:

~~~text
APP_MAIN_REACHED
~~~

Stderr:

~~~text
AGENT_DISABLED: invalid agent config
~~~

**Case I — error in the application after the agent has succeeded**

~~~bash
java -javaagent:healthy-agent.jar=ok App fail
~~~

Stdout:

~~~text
AGENT_READY: ok
APP_MAIN_REACHED
~~~

Then stderr has `IllegalStateException: application failure` from `App.main`. The process may exit with an error, **but this is not an agent loading failure**: the `APP_MAIN_REACHED` line already proved the application started running.

## 5. Workflow for debugging startup agents in real environments

When an application dies immediately after adding `-javaagent`, check from the outside in:

1. **Verify the actual JVM command used** and runtime version. In scripts, containers, services, or IDEs, the position of `-javaagent`, the current working directory, and the JDK may differ from your development terminal. For example:
   
   ~~~bash
   java -version
   java -javaagent:healthy-agent.jar=ok App
   ~~~

   For a real application, use the exact command line and agent file that the deployment launches. Relative paths are resolved against the process working directory, not necessarily the directory containing the application.

2. **Inspect the deployed JAR file**, not just the file in the build directory. Use:
   
   ~~~bash
   jar --list --file healthy-agent.jar
   ~~~

   Expect `META-INF/MANIFEST.MF` and `HealthyAgent.class`. For a class packaged in a package, the path must look like `com/acme/agent/StartupAgent.class`. To view the actual manifest, you can extract `META-INF/MANIFEST.MF` into a **separate inspection directory**, then read the file:
   
   ~~~bash
   jar --extract --file healthy-agent.jar META-INF/MANIFEST.MF
   ~~~

   Check that `Premain-Class` is in the *main section* of the manifest and has the exact class name. The extract command creates files under the current directory, so run it in an inspection directory to avoid overwriting other files.

3. **Inspect the compiled method and bytecode**; do not just trust the Java source or file name:
   
   ~~~bash
   javap -public -classpath healthy-agent.jar HealthyAgent
   ~~~

   For this example, `javap` must list `public static void premain(java.lang.String, java.lang.instrument.Instrumentation)`. If the class belongs to a package, use its dot-separated fully qualified name. If you see wrong parameter order or missing `static`, fix the code and **repackage a new JAR**.

4. **Read the root cause of the stack trace**, especially the deepest `Caused by`. `ClassNotFoundException` may mean the `Premain-Class` name is wrong; `NoClassDefFoundError` can also come from an unpackaged transitive library. `UnsupportedClassVersionError` requires comparing Java versions. `IllegalAccessError` or `InaccessibleObjectException` may indicate module/readability/openness issues. `IllegalArgumentException` in the agent configuration parser should usually be logged with the offending option name, without printing secrets.
5. **Reproduce in isolation** with a minimal app like `App.java` first, then test with the actual application, JDK, and configuration. When testing `-javaagent`, compare runs with and without the agent, and observe **the `main` started milestone**. Be careful: changing the agent may make an application error disappear without proving the agent's configuration/bytecode is safe.
6. **Ensure diagnostic logs exist before `main`**. Print logs at the start of `premain` or use a safely initialized logger; do not depend on a logging framework that is only bootstrapped in `main`/Spring context. Clearly log the agent version, mode, option names (with sensitive data scrubbed), root cause, and handling behavior.

**Testing on the exact target JDK is mandatory.** Compiling the entry point class with `--release 17` is not enough if the JAR pulls in dependencies built for a newer Java version or libraries requiring modules/access permissions unavailable at runtime.

## 6. Choosing an error policy: fail fast or disable the agent?

There is no single answer for every application. You must base it on **the agent's role**:

| Context | Reasonable handling | Consequence to accept |
| --- | --- | --- |
| Agent is required to guarantee instrumentation needed by the application/operational policy | **Fail fast**: throw an error with context, let startup stop | Service does not run; deployment must report the error clearly |
| Optional monitoring agent; application remains correct without telemetry | **Controlled graceful degradation**: catch only recoverable errors, log `AGENT_DISABLED`, clean up, and return | Application runs but loses telemetry; alerting and status distinction are needed |
| Agent already modified bytecode/registered hooks before failing | Prefer fail fast or a verified rollback; do not return as if everything were normal | Partial side effects may remain; a bare `catch` does not guarantee state recovery |
| Unchecked errors such as `OutOfMemoryError`, severe JVM/class linkage errors | Do not attempt to swallow every `Throwable` to "keep running" | Continuing may leave the JVM in an unreliable state |

The `GracefulAgent` example above only catches **`IllegalArgumentException` from invalid configuration** and has not registered any transformer or modified any class yet. This is a simple boundary, suitable for illustrating the choice to disable the agent. In a real implementation, you should separate initialization steps: **validate first → acquire/register resources → publish ready state**; when failing mid-way, clean up what was already registered. Do not recklessly catch `Throwable` to mask severe errors. In a startup agent, a useful rule is:

~~~text
Startup agent REQUIRED:
    fail -> log cause -> throw -> JVM does not enter main

Startup agent OPTIONAL:
    anticipated failure, no irreversible side-effects yet
         -> cleanup + report disabled state -> premain return
         -> application still enters main
~~~

The two policies must not be mixed. If a system uses an agent for audit/compliance and merely logs a warning and ignores the error, the system may serve requests while a mandatory control is missing. If an agent only records optional metrics, halting the entire service because an exporter endpoint is temporarily unreachable may be overly strict. The decision must be clearly documented and tested with failure injection.

## 7. Misconceptions to avoid

- **"`premain` must always have `Instrumentation`":** false. `premain(String)` also exists; the JVM tries the two-parameter signature first.
- **"Passing `javac` compilation proves the JVM will call the method":** false. `javac` only checks syntax/signatures according to the Java language; the instrumentation entry point is looked up by a separate contract at runtime.
- **"Having `Main-Class` or `Agent-Class` means `-javaagent` automatically understands it":** false. This kind of startup agent requires `Premain-Class`.
- **"If an agent fails at startup, the app can `catch` it in `main`":** false. `main` has not been called.
- **"`premain` is just library code; throwing does not affect the application":** false. It runs inside the target JVM and an uncaught exception causes startup to abort.
- **"`catch(Exception)` is enough to always be safe":** false. Errors can occur before `premain` is called; `Error` types are not `Exception`, and swallowing an error after registering hooks can leave the system in a partial state.
- **"Agent loading errors and application errors in `main` are the same":** false. Look for `APP_MAIN_REACHED` evidence and the true root cause.
- **"Dynamic `agentmain` attach also always aborts the JVM":** inaccurate per the specification: when an agent is requested to load **after the JVM is already running**, an `agentmain` failure does not necessarily abort the target JVM; uncaught exceptions may be ignored after being logged. This is a different mechanism from `-javaagent`. Additionally, `Launcher-Agent-Class` in an *executable JAR* also initializes before application main but uses the `agentmain` signature; **failures in this launcher mode still abort**, so you must distinguish by **how the agent is loaded**, not just the method name.

## 8. Pre-production checklist for startup agents

- Verify the JAR is the right version artifact, is readable, and contains `META-INF/MANIFEST.MF` along with the required agent/dependencies.
- Verify `Premain-Class` and `public static void premain(String, Instrumentation)` or `premain(String)` using `javap` and a smoke test.
- Test with the **exact runtime JDK, class loader/modules, container, OS permissions, and startup command** used in production; avoid assuming the local environment matches deployment.
- Create negative tests for corrupt/missing JAR, wrong class, wrong signature, invalid config, and exceptions in `premain`; verify logs and whether `main` runs or does not run as designed.
- Clearly decide whether the agent is **required** or **optional**. For an optional agent, record the disabled state and clean up resources before letting the application proceed.
- Avoid slow/blocking work in `premain` (network calls without timeouts, waiting for an exporter, unbounded dependency scanning), as it slows down or hangs startup before `main`.
- If using multiple `-javaagent` flags, remember the JVM invokes `premain` in **command-line argument order**; one failing agent can block the entire startup sequence.
- Do not print tokens, API keys, credentials, or full options containing sensitive data during diagnostics.

**Self-check:** If `java App` succeeds but `java -javaagent:wrong-signature-agent.jar App` does not print `APP_MAIN_REACHED`, the first thing to do is check **the `premain` contract and manifest**, not debug business logic in `App.main`. If `APP_MAIN_REACHED` has already appeared before an application stack trace, that is a different diagnostic branch.

### Official documentation

- [Java SE 17 — `java.lang.instrument` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): launch modes, `premain`/`agentmain` signatures, abort rules, and manifest.
- [Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): capabilities and transformer operations.
- [Java SE 17 — JAR File Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html): manifest format, main section, headers.
