# `premain` Before `main` Order and Multiple `-javaagent` Options

A **startup Java agent** is loaded using the `-javaagent` JVM option. Its entry point is the `premain` method; the JVM invokes `premain` **after the JVM initializes but before invoking the application's `main`**. When multiple `-javaagent` options are present, the `premain` methods are invoked **in the exact order the agents appear on the command line**, and each `premain` must return for the next startup step to proceed.

This article focuses on the startup sequence, how to package and run multiple startup agents, the impact of ordering, how to distinguish `premain` invocation order from `ClassFileTransformer` processing order, and common pitfalls when coordinating agents.

## 1. Sequence Guaranteed by `java.lang.instrument`

The command has the form:

```text
java [JVM options] \
     -javaagent:agent-a.jar[=optionsA] \
     -javaagent:agent-b.jar[=optionsB] \
     -cp <classpath> <fully-qualified-main-class> [application-args]
```

Lifecycle diagram for two agents starting up successfully:

```text
User invokes java
    |
    v
JVM is initialized
    |
    v
Load Agent A, invoke A.premain(optionsA, instrumentation)
    |
    | A.premain returns normally
    v
Load Agent B, invoke B.premain(optionsB, instrumentation)
    |
    | B.premain returns normally
    v
Invoke Application.main(String[] args)
    |
    v
Application continues running
```

Three guarantees to keep distinct:

1. **`premain` runs before the application's `main`**, but not before *every JVM activity*. The JVM has already initialized, and some classes may already be loaded when `premain` begins.
2. **Multiple `premain` methods run in the order of `-javaagent` options on the command line**; if A precedes B, the `A.premain` call must return before the JVM invokes `B.premain` in this startup chain. The JVM only begins invoking `main` after the startup agents have started up successfully.
3. **Completion order of asynchronous work is not guaranteed by this rule**: `premain` can spawn background threads, register callbacks, or submit tasks to an executor and then return. Those threads/callbacks may still run during or after `main`.

For example, if A initializes configuration synchronously and returns, and B reads that configuration in `premain`, then B sees A's result. However, if A only spawns a thread to update the configuration and returns immediately, B **has no guarantee** that A's thread has finished updating.

> Note: the specified order is the **`premain` invocation order on the startup path**. Do not infer that all tasks created by agents remain sequential thereafter.

## 2. Conditions for the JVM to Recognize a Startup Agent

Each agent must be packaged in a JAR whose manifest contains the `Premain-Class` attribute pointing to the fully qualified name of the entry-point class:

```text
Manifest-Version: 1.0
Premain-Class: demo.agents.AgentA

```

In this class, the JVM prefers the two-parameter signature:

```java
public static void premain(String agentArgs,
                           java.lang.instrument.Instrumentation inst)
```

If that signature does not exist, the JVM tries the one-parameter signature:

```java
public static void premain(String agentArgs)
```

Both must be `public static void`. When using the two-parameter form, `Instrumentation` provides the API to register `ClassFileTransformer`s, query loaded classes, retransform/redefine if the capability is supported, and so on. The `agentArgs` parameter is **a single option string for the agent itself** after the `=` sign, not the application's `String[] args` array.

Differences between entry points:

| Startup mechanism | Related manifest attribute | Entry point |
| --- | --- | --- |
| `java -javaagent:agent.jar` at JVM startup | `Premain-Class` | `premain(...)` |
| Attach agent to a running JVM (when supported by the JVM) | `Agent-Class` | `agentmain(...)` |
| Agent packaged inside an executable application JAR via launcher mechanism | `Launcher-Agent-Class` | `agentmain(...)` per that mechanism's specification |
| Normal application | `Main-Class` (if run with `-jar`) or main class on the command line | `main(String[] args)` |

**`Premain-Class` is different from `Main-Class`**. Putting a class with `main` into an agent JAR without `Premain-Class` does not automatically make it an agent. With `-javaagent`, the JVM does not invoke `agentmain` even if the JAR declares both `Premain-Class` and `Agent-Class`.

## 3. Practice: Two Agents Confirming Order Using Shared State

The example runs on **JDK 17+**. We use three Java classes and two manifests. The agents only print one line and update a system property to demonstrate invocation timing; no bytecode is modified so the output is easy to verify.

Directory structure:

```text
example/
├── src/
│   └── demo/
│       └── agents/
│           ├── AgentA.java
│           ├── AgentB.java
│           └── MainApp.java
├── agent-a.mf
└── agent-b.mf
```

### 3.1. `src/demo/agents/AgentA.java`

```java
package demo.agents;

import java.lang.instrument.Instrumentation;

public final class AgentA {
    private static final String KEY = "demo.agent.order";

    private AgentA() {
    }

    public static void premain(String agentArgs, Instrumentation inst) {
        String previous = System.getProperty(KEY, "");
        System.out.println("[AgentA] premain args=" + agentArgs
                + ", before=" + (previous.isEmpty() ? "<empty>" : previous));

        String next = previous.isEmpty() ? "A" : previous + " -> A";
        System.setProperty(KEY, next);
    }
}
```

This is a valid startup agent because the class has a `public static void premain(String, Instrumentation)` method. The `inst` parameter is unused because this lesson checks **timing and order**, without implementing a transformer. A system property is simply an easy observation mechanism because the agents and the application reside in **the same JVM process**.

### 3.2. `src/demo/agents/AgentB.java`

```java
package demo.agents;

import java.lang.instrument.Instrumentation;

public final class AgentB {
    private static final String KEY = "demo.agent.order";

    private AgentB() {
    }

    public static void premain(String agentArgs, Instrumentation inst) {
        String previous = System.getProperty(KEY, "");
        System.out.println("[AgentB] premain args=" + agentArgs
                + ", before=" + (previous.isEmpty() ? "<empty>" : previous));

        String next = previous.isEmpty() ? "B" : previous + " -> B";
        System.setProperty(KEY, next);
    }
}
```

Agent B reads the existing value before updating it. Therefore, the order A then B produces the string `A -> B`; if the order is swapped, we will see `B -> A`.

### 3.3. `src/demo/agents/MainApp.java`

```java
package demo.agents;

public final class MainApp {
    private MainApp() {
    }

    public static void main(String[] args) {
        String order = System.getProperty("demo.agent.order", "<empty>");
        System.out.println("[MainApp] main sees=" + order);
    }
}
```

The application does not import `AgentA` or `AgentB`. Thus, the `premain` methods are not called by `main` itself. The JVM selects and invokes the agents from the `-javaagent` options.

### 3.4. Two Separate Manifests with the Correct `Premain-Class`

Contents of `agent-a.mf`:

```text
Manifest-Version: 1.0
Premain-Class: demo.agents.AgentA

```

Contents of `agent-b.mf`:

```text
Manifest-Version: 1.0
Premain-Class: demo.agents.AgentB

```

Keep a **trailing newline at the end of each manifest**; leaving a blank line after `Premain-Class` as shown above is an easy way to verify. Do not use `demo/agents/AgentA` because the manifest requires a binary class name with dots.

### 3.5. Compiling and Packaging with JDK Tools

Open a terminal in the `example/` directory. Create the `out` directory once (for example `mkdir out`), then run:

```bash
javac --release 17 -d out src/demo/agents/AgentA.java src/demo/agents/AgentB.java src/demo/agents/MainApp.java

jar --create --file agent-a.jar --manifest agent-a.mf -C out demo/agents/AgentA.class
jar --create --file agent-b.jar --manifest agent-b.mf -C out demo/agents/AgentB.class
```

The `-d out` flag places compiled classes into package paths, for example `out/demo/agents/AgentA.class`. Each agent JAR contains the class specified in its manifest; the application runs with `-cp out`. These commands work with JDK 17+ in a shell that has `javac` and `jar` on `PATH`. On PowerShell, you can also use `New-Item -ItemType Directory -Force out` to create `out`.

Inspect the file list inside the JARs:

```bash
jar --list --file agent-a.jar
jar --list --file agent-b.jar
```

To check the manifest, open the `META-INF/MANIFEST.MF` entry using a ZIP/JAR tool and confirm that `Premain-Class` points to the right class. Simply seeing a JAR named "agent" is not enough.

## 4. Running A Before B: Exact Output

```bash
java -javaagent:agent-a.jar=left -javaagent:agent-b.jar=right -cp out demo.agents.MainApp
```

In a test environment without `demo.agent.order` pre-set, stdout is:

```text
[AgentA] premain args=left, before=<empty>
[AgentB] premain args=right, before=A
[MainApp] main sees=A -> B
```

Step-by-step analysis:

1. The JVM reads the first agent JAR, loads `demo.agents.AgentA`, and invokes `AgentA.premain("left", inst)`.
2. A sees the property is unset, prints `<empty>`, sets the property to `A`, and **returns**.
3. The JVM invokes `AgentB.premain("right", inst)`. B sees `A`, updates it to `A -> B`, and returns.
4. The JVM invokes `MainApp.main(...)`. The application reads `A -> B` and prints the last line.

Each invocation of the `java` command is a new JVM process. System properties updated by agents in a previous run do not persist into a subsequent Java process.

## 5. Swapping Command-Line Positions: B Before A

Simply swap the order of the two `-javaagent` JVM arguments:

```bash
java -javaagent:agent-b.jar=right -javaagent:agent-a.jar=left -cp out demo.agents.MainApp
```

Stdout:

```text
[AgentB] premain args=right, before=<empty>
[AgentA] premain args=left, before=B
[MainApp] main sees=B -> A
```

There is no automatic sorting of agents by **class name, JAR name, JAR creation order, or classpath**. `premain` order is determined by the order of `-javaagent` options on the command line. If a system launches Java indirectly via a script, Gradle task, container entrypoint, or IDE configuration, inspect the **final JVM command line** that the system actually executes.

### 5.1. Loading the Same JAR Twice

The specification allows multiple `-javaagent` options with the **same JAR path**. Try:

```bash
java -javaagent:agent-a.jar=once -javaagent:agent-a.jar=twice -cp out demo.agents.MainApp
```

Stdout:

```text
[AgentA] premain args=once, before=<empty>
[AgentA] premain args=twice, before=A
[MainApp] main sees=A -> A
```

This means **you must not assume each agent JAR receives only one `premain` call per startup command**. With real agents, repeated invocations can register transformers/callbacks multiple times and duplicate side effects; an agent should clearly define how to handle this, such as rejecting duplicate configurations or designing idempotent initialization.

### 5.2. Without Any Agent

```bash
java -cp out demo.agents.MainApp
```

Stdout:

```text
[MainApp] main sees=<empty>
```

This line confirms the application class runs independently; the `[AgentA]`/`[AgentB]` lines only appear when the JVM is passed the corresponding startup agents.

## 6. Roles of `agentArgs`, JVM Options, and `main` Arguments

Compare:

```bash
java -javaagent:agent-a.jar=mode=debug -cp out demo.agents.MainApp hello
```

- The string `"mode=debug"` is the entire `agentArgs` received by `AgentA.premain`.
- The word `"hello"` is element `args[0]` of `MainApp.main` (the example application does not print it).
- The agent itself is responsible for parsing the `agentArgs` string if multiple key/value pairs are used; Java does not automatically convert `mode=debug` into a `Map`.
- Another `-javaagent:...` has its own option string. A's options are not passed to B by default.
- JVM flags such as `-javaagent` must be placed **before the main class name** or before `-jar app.jar`. Placing `-javaagent:agent.jar` after the main class name only turns it into an application argument instead of activating the agent.

If running the application as an executable JAR:

```bash
java -javaagent:agent-a.jar=left -javaagent:agent-b.jar=right -jar application.jar
```

`application.jar` needs its own `Main-Class`; `agent-a.jar` and `agent-b.jar` need `Premain-Class`. Using `-jar` does not reverse startup agent ordering.

## 7. When Multiple Real Agents Register `ClassFileTransformer`

The example above only demonstrates `premain` timing. A monitoring or coverage agent typically uses `Instrumentation.addTransformer(...)` inside `premain` to register a bytecode transformer. You must distinguish **transformer registration order** from **`premain` invocation order**.

Suppose A and B both register normal transformers directly inside `premain`:

```java
// Illustrative snippet inside premain, not a standalone class.
inst.addTransformer(transformerA);  // A registers in A.premain
inst.addTransformer(transformerB);  // B registers in B.premain
```

In reality, these two lines reside **in two different agents**, not in a single place as in the shorthand above. Once both transformers are registered and a new class is about to be defined, the JVM can pass the bytes through the transformers in sequence. Within the same **retransformation-capability group**, transformers are invoked in **registration order**; the bytes from the previous step become the input to the next step if the previous step returns a new byte array.

However, Java defines **ordering groups** when applying transformers:

1. Java transformers that **do not support retransformation** (`retransform-incapable`);
2. Native transformers that do not support retransformation;
3. Java transformers that **support retransformation** (`retransform-capable`);
4. Native transformers that support retransformation.

Within each group, registration order is preserved. Therefore, **you must not make an absolute claim that "because Agent A comes before Agent B, every transform of A always runs before every transform of B"**. If A registers a retransform-capable transformer while B registers a retransform-incapable transformer, the group order differs from the order of the two `premain` calls.

The following example is only for illustrating the logic, **not actual compiler output or standalone transformer code**:

```text
premain A: register transformer A (retransform-capable)
premain B: register transformer B (retransform-incapable)

A new class is loaded afterward:
    B.transform(originalBytes) -> bytesB
    A.transform(bytesB)        -> bytesA
```

When `retransformClasses(...)` is called on an already loaded class, retransform-incapable transformers are not called again; the JVM reuses their previous effect according to API rules, whereas retransform-capable transformers are called again. Retransformation capability must be supported by the JVM, and the agent may require the `Can-Retransform-Classes: true` manifest attribute. **`premain` order still matches the command line** in all of these cases.

### 7.1. Startup Order Does Not Guarantee Intercepting Every Class

If Agent A proactively loads `com.example.Service` inside `A.premain`, and Agent B only registers a transformer for `com.example.Service` in `B.premain`, B's transformer does not automatically go back in time to see that class's initial definition. Processing already-loaded classes requires the appropriate capability and calls (such as retransformation if supported, the class is modifiable, and the changes are valid).

Even the first agent can run after some JDK classes or startup-supporting classes have already been loaded. Therefore, "`premain` before `main`" **is not equivalent to** "the transformer sees 100% of classes ever loaded in the JVM".

### 7.2. Two Agents Transforming the Same Class

Two tracing, coverage, profiling, or APM tools may instrument the same method. The outcome depends on the transformations, ordering within groups, and bytecode compatibility. Common issues:

- The second transformer does not understand bytecode already modified by the first transformer.
- Both agents create helper fields/methods with colliding names.
- An agent initializes too early or registers too late relative to the target class.
- A non-idempotent transformer inserts nested code when run again.
- Another agent loads many classes or spawns threads in `premain`, causing class-loading events to interleave with registrations.
- Changing agent order changes behavior, even though both still have valid `premain` methods.

When evaluating two agents, test **each agent individually, then run both together in both orders**, on the same JDK version and agent versions. There is no guarantee that any arbitrary pair of agents is compatible.

## 8. What Happens If a `premain` Fails?

A startup agent differs from application code that can catch its own errors and continue. According to the Java 17 specification, if an agent cannot be started (invalid JAR, invalid `Premain-Class`, class cannot be loaded, missing suitable `premain`) or `premain` throws an **uncaught exception**, the JVM **aborts startup**. The application's `main` is not invoked.

Example with three agents A, B, C:

```text
java -javaagent:a.jar -javaagent:b.jar -javaagent:c.jar -cp out demo.Main

A.premain --> returns
B.premain --> throws uncaught exception
JVM abort
C.premain --> not invoked
Application.main --> not invoked
```

This diagram illustrates the result of a failure in B under startup rules, not a literal JVM log. Error messages and stack traces depend on the runtime.

Other issues that do not change the ordering rules but should be distinguished:

| Issue | Outcome or diagnostic direction |
| --- | --- |
| Agent has `main` but lacks `Premain-Class` | The JVM does not recognize it as a valid startup agent. |
| Manifest points to a class name missing from the JAR / unloadable | Agent fails to start; the JVM stops before the application. |
| Agent class has `premain` that is non-`public` or has the wrong signature | No suitable startup agent entry point is found. |
| `premain` throws an uncaught error | JVM aborts before `main`. |
| `premain` never returns | The startup chain stalls at the agent; `main` is not called until the agent returns. |
| Agent spawns an asynchronous thread and returns | The thread may run concurrently with later agents or with `main`. |
| Agent registers a transformer after the target class is loaded | Registration alone cannot catch the earlier load; appropriate reprocessing capability is needed. |
| Agent requests retransformation but the JVM/configuration does not support it | `addTransformer(..., true)` may throw `UnsupportedOperationException`; check `isRetransformClassesSupported()` and the manifest. |
| Two agents modify the same result/class metadata | Check transformer ordering and bytecode compatibility; do not infer directly from `premain` log order. |

It is possible to **catch and handle expected errors inside `premain`**, but the agent must decide whether continuing the application without instrumentation is valid. You should not simply "swallow" all exceptions and report that the agent is working normally.

## 9. Checklist for Debugging an Application with Multiple Agents

A concise workflow for investigating ordering issues:

1. **Record the exact actual JVM command line**, including every `-javaagent`, JAR path, option string, and main class/`-jar`. If a launcher/script/IDE/container adds arguments automatically, verify the final configuration.
2. **Inspect each JAR's manifest** and the class referenced by `Premain-Class`. Confirm the `public static premain` method has a valid signature.
3. **Add minimal logging at the start and end of `premain`** (agent name, secret-redacted arguments, order, thread if helpful). Seeing the start message without the end message suggests the agent hung or failed before returning.
4. **Run each agent alone**, then run both together and swap their order. For bytecode-related errors, check whether the target class was already loaded before registration.
5. **Separate startup failures from transform/runtime failures**. The JVM stopping before `main` may indicate an agent startup failure; exceptions when a class is first loaded after `main` usually require checking transformers and class loading.
6. **Check optional capabilities** via `Instrumentation.isRetransformClassesSupported()` and `isRedefineClassesSupported()` if the agent relies on them; only request manifest capabilities when needed.
7. **Verify the normal return path**: for synchronous agents, each `premain` should complete critical initialization before returning; for background tasks, provide explicit synchronization if later agents or the application depend on their results.

For production configurations, there should be a way to observe which agents initialized successfully, each agent's version, and the actual options used, without logging tokens or secrets from `agentArgs`.

## 10. Misconceptions to Avoid

| Misconception | Accurate understanding |
| --- | --- |
| "`premain` runs before the JVM itself." | The JVM initializes first, then invokes `premain` before application `main`. |
| "An agent only runs when `main` calls into the agent class." | `-javaagent` and `Premain-Class` cause the JVM to proactively invoke `premain`. |
| "Agent B, whose name comes first alphabetically, will run before A." | Only the order of `-javaagent` options determines `premain` order. |
| "Only one `-javaagent` is allowed." | Multiple can be passed, including the same JAR multiple times. |
| "Two agents on the same command line run `premain` in parallel." | `premain` calls belong to the sequential startup chain; tasks spawned by an agent may run in parallel. |
| "All of A's transformers must run before B's because A's `premain` ran first." | Transformers have their own retransformation/nativity groups and registration rules. |
| "`premain` runs before `main`, so it is guaranteed to see every class." | Some classes are already loaded before or during agent startup. |
| "If `premain` is missing, the JVM ignores the agent and runs the app." | Startup agent failure can cause the JVM to abort. |
| "`agentArgs` is the same as `main(String[] args)`." | One is an option string dedicated to the agent; the other is the application's argument array. |
| "`agentmain` and `premain` only differ in name." | The two entry points serve different startup mechanisms, with different error handling. |

## 11. Self-Check

**Question 1.** With the command `java -javaagent:b.jar -javaagent:a.jar -cp out demo.Main`, which method runs first?

**Answer:** `B.premain`, then `A.premain`, and then `Main.main`, provided both startup agents start up successfully and return.

**Question 2.** Agent A spawns a thread and returns. Agent B needs data produced by that thread. Is relying solely on the order `-javaagent:a.jar -javaagent:b.jar` sufficient?

**Answer:** No. `premain` invocation order does not wait for A's background thread to finish. Appropriate synchronization must be added, or the required initialization must be performed directly inside A's `premain`.

**Question 3.** A registers a retransform-capable Java transformer, and B registers a retransform-incapable Java transformer. A's `premain` runs first. When a new class is loaded, which transformer's group is invoked first?

**Answer:** The retransform-incapable group (transformer B) takes precedence before the retransform-capable group (transformer A). This is a `ClassFileTransformer` rule, distinct from `premain` invocation order.

**Question 4.** If both A and B have `premain` run successfully, yet `MainApp.main` does not appear in the logs, can we conclude the JVM skipped `main` because multiple `-javaagent` options were used?

**Answer:** No. Multiple agents are valid. You need to check whether a later agent is hanging or aborting, how the launcher invokes Java, exceptions during main class loading, stdout/stderr, and whether the program exited on its own.

**Question 5.** Does the command `java -cp out demo.agents.MainApp -javaagent:agent-a.jar` invoke `AgentA.premain`?

**Answer:** No. `-javaagent:agent-a.jar` is placed **after** the main class name, so it is passed as an application argument. Move this option before the main class name.

## 12. Summary and Authoritative References

- A startup agent is identified by `-javaagent:jar[=options]` and the `Premain-Class` manifest attribute.
- The JVM invokes `premain` **after JVM initialization, before `main`**; multiple `premain` methods are invoked in **`-javaagent` order**.
- Each `premain` must return normally for the startup chain to continue; startup failures or uncaught exceptions cause the JVM to abort.
- `premain` invocation order does not guarantee asynchronous thread completion order, nor does it automatically determine the entire `ClassFileTransformer` order.
- With multiple agents, you must consider **launcher configuration, class-loading timing, transformer ordering/capabilities, and interactions between bytecode transformations**.

Authoritative sources for reference:

1. **Java SE 17 API — `java.lang.instrument` package specification**: `-javaagent` syntax, `Premain-Class`, multiple `premain` ordering, signatures, and startup errors: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
2. **Java SE 17 API — `Instrumentation`**: `addTransformer`, `retransformClasses`, capability checks: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
3. **Java SE 17 API — `ClassFileTransformer`**: transformer invocation groups/ordering: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
4. **JDK 17 — `java` command**: placement of JVM options, `-javaagent`, `-cp`, and `-jar`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html