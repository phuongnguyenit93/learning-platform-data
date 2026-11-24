# 3.4. VM.command_line, VM.flags, VM.system_properties, and VM.info

When a Java application behaves differently between a developer machine and production, the key question is often not “what is the configuration in the repository?” but **how the running JVM was actually started and configured**. Shell commands, JVM arguments, Java system properties, and environment state can differ due to startup scripts, containers, orchestration, environment variables, runtime configuration, or mutations after the process has started.

For HotSpot/OpenJDK JVMs supporting diagnostic commands, the **`jcmd`** utility lets you read information directly from a **living JVM process**. The following four commands answer four distinct questions:

- **`VM.command_line`:** What arguments was the JVM started with?
- **`VM.flags`:** What effective values do the VM flags currently have?
- **`VM.system_properties`:** What Java system properties does the process currently see?
- **`VM.info`:** What is the running JVM's status and environmental context?

This lesson belongs to **3. Process and Environment**, focusing on the purpose, usage, reading, comparison, and limits of these four diagnostic commands in Java 17+. Do not treat them as the sole evidence of application behavior, and do not confuse information captured at inspection time with configuration version-controlled at build time.

## 1. Prerequisites for Reading a Live JVM Directly

`jcmd` belongs to the appropriate **JDK** toolset. Most commands send diagnostic requests to the JVM via the attach mechanism, so you need:

1. An **existing** JVM process. Record the exact PID, container/pod/host, timestamp, and JDK version.
2. Run `jcmd` on the same machine or in an environment able to reach that process, with matching **effective user/group**. In containers with a separate PID namespace, the PID on the host and inside the container may not match.
3. The target JVM supports the invoked commands and permits attach. Running with `-XX:+DisableAttachMechanism` or in an environment with blocked permissions/access can cause the command to fail.
4. `jcmd` is present in the tool execution environment. A minimal runtime image containing only a JRE/application binary may lack `jcmd`; you may need a JDK and an approved way to access the process.
5. Do not assume every JVM vendor/version produces identical content or output format. **Ask the target JVM directly with `help`** to see which commands are actually supported.

Basic commands (example PID **12345**, replace with the actual PID):

~~~bash
jcmd -l
jcmd 12345 help
jcmd 12345 help VM.command_line
jcmd 12345 help VM.flags
jcmd 12345 help VM.system_properties
jcmd 12345 help VM.info
~~~

`jcmd -l` lists JVMs visible from the current environment. It **can miss JVMs inside separate Docker/PID namespaces**; in that case look up the PID with process/container tools in the proper namespace. Do not use `jcmd 0 ...` or target by main class in a multi-JVM environment just for convenience: you risk sending commands to **multiple processes**. Always target a specific PID.

**Operation scope:** the four commands covered here are for *viewing* information, unlike `VM.set_flag` which mutates flags. However, output can be long and contain secrets; restrict who can read it, store it in a protected location, and sanitize before sharing.

## 2. Quick Comparison Table

| Command | Question answered | Core data | Pitfalls to avoid |
| --- | --- | --- | --- |
| `VM.command_line` | “What was it launched with?” | JVM arguments and Java command/main class/JAR, depending on JVM version | Do not treat as **current application configuration** state after runtime mutations |
| `VM.flags` | “What values do VM flags have?” | JVM flags with current effective values; can view all via `-all` | Do not confuse flags with system properties, `main` args, or env vars |
| `VM.system_properties` | “What are the current Java system properties?” | List of `key=value` entries seen by the JVM | Do not equate with **OS environment variables** or all Spring/application config |
| `VM.info` | “What are the JVM's environment and status?” | Summary report of JVM/runtime and environment, version-dependent | Do not treat as a complete snapshot of every memory/CPU/thread issue; do not expect a fixed schema |

**Visualizing the three configuration layers:**

~~~text
Command/launcher starting the JVM
       |
       +-- JVM options: -Xmx, -Xms, -XX:... ----> VM.flags (effective values)
       |
       +-- Java properties: -Dkey=value -------> VM.system_properties (current snapshot)
       |
       +-- Main class/JAR and app args ---------> VM.command_line (startup trace)
       |
       +-- OS/container/JDK/runtime -----------> VM.info (environment and status report)
~~~

This is a conceptual diagram, **not a one-to-one mapping** between character strings. For example, `-Xmx256m` in `VM.flags` is usually represented by the `MaxHeapSize` flag in bytes; a flag may be computed by the VM using ergonomic defaults; a system property may be modified by the program via `System.setProperty(...)` after startup.

## 3. VM.command_line — Arguments at JVM Startup

Syntax:

~~~bash
jcmd 12345 VM.command_line
~~~

This command prints the command details recorded by the JVM at startup. On a HotSpot build, you may see entries like:

~~~text
VM Arguments:
jvm_args: -Xms128m -Xmx256m -Ddemo.mode=startup
java_command: VmIntrospectDemo alpha beta
java_class_path (initial): .
Launcher Type: SUN_STANDARD
~~~

**This is illustrative output**, not guaranteed stdout for every JDK/launcher. Placement, fields, and contents vary by launch method, vendor, Java version, and classpath/JAR/module path.

Typically:
- **`jvm_args`:** arguments passed to the JVM at startup, such as `-Xmx`, `-XX:+UseG1GC`, `-Ddemo.mode=startup`.
- **`java_command`:** the launched application and application arguments as represented by the launcher; for example `-jar app.jar` or the main class name plus `args`.
- **Classpath/launcher:** may show the initial classpath or launcher type, but does not mean that path remains identically effective across all subsequent classloaders.

Use when:
- Deployment reports the JVM is running with a different `-Xmx` than expected.
- You need to verify which class/JAR the process actually runs and what arguments follow main.
- Two pods use the same image, yet their entrypoint scripts or JVM arguments differ.
- You need to check whether `-D...`, `-XX...`, agents, or options meant for another environment were accidentally passed.

**Important limitations:** output reflects startup info retained by the VM; it is not an exact, unaltered copy of the original shell command, quoting/expansion, environment variables, configuration files, or everything the application framework uses. If the application changes a property after start, `VM.command_line` still shows startup input, whereas `VM.system_properties` shows the new value. Some launchers/runtimes may add or transform options (for instance via startup-related Java environment variables); to trace the root source, cross-check entrypoint, deployment manifest, and environment config.

Pay special attention to **secrets in the command line**: an application passing tokens/passwords via `-Dsecret=...` or application arguments can expose them in this output as well as in other process inspection tools. Avoid placing secrets on the command line; when collecting evidence, redact before saving/sharing.

## 4. VM.flags — JVM Flags and Effective Values

Syntax:

~~~bash
jcmd 12345 VM.flags
jcmd 12345 VM.flags -all
~~~

- **`VM.flags`:** displays VM flags formatted by the JVM, usually focusing on notable/non-default flags rather than a full catalog.
- **`VM.flags -all`:** requests all flags supported by the VM along with current values; output is very long and useful when investigating a specific flag or where it was set.

Commonly encountered names during investigations:

| Flag | Related to |
| --- | --- |
| `InitialHeapSize` | Initial heap size, usually related to `-Xms` |
| `MaxHeapSize` | Maximum Java heap limit, usually related to `-Xmx` |
| `UseG1GC` / other GC flags | Selected garbage collector |
| `ActiveProcessorCount` | Manually configured processor count used by the VM for certain decisions |
| `MaxRAMPercentage` | RAM percentage considered when computing max heap if no direct limit is set |
| `UseContainerSupport` | Mechanism allowing the VM to inspect container limits on supported HotSpot builds |

Flags can be **boolean, numeric, string, or size**; output typically expresses sizes in **bytes** or internal format. For instance, `-Xmx256m` typically corresponds to a `MaxHeapSize` around **268435456 bytes** (256 × 1024 × 1024), though do not assume all constraints/alignments/JVMs are identical. Always read the **actual value** on the target process.

In HotSpot `-all` output, value markers and type/origin metadata may appear, such as `{product}`, `{default}`, `{command line}`, `{ergonomic}`; **interpret them according to the target JVM version**. This helps distinguish:
- **Default value:** chosen by the JVM when no override applies.
- **Startup-declared value:** passed by the operator, launcher, or configuration.
- **Ergonomically computed value:** chosen by the JVM based on environment and policy.
- **Runtime-modifiable value:** only for flags eligible for dynamic change with proper tool privileges; do not assume all flags are mutable.

This is the **JVM options** layer. It is **not** the set of `-D` system properties and **not** the arguments passed to `main(String[] args)`. Similar-looking names across those layers can still have independent meanings.

### Why Check VM.flags Even When “-Xmx Was Already Passed”?

Because the JVM can apply calculations, alignment, RAM/container policies, collector selection, and version-specific defaults. Comparing startup input with **effective values** lets you test the hypothesis “`-Xmx` was set, yet actual heap differs.” If an option does not appear in the short `VM.flags` output, do not hastily conclude “it isn't set”: check `VM.flags -all`, `VM.command_line`, and `help`.

Do not use `VM.flags` to conclude memory limits **for the entire process**: heap is only one part; metaspace, code cache, native buffers, stacks, and GC/JIT also consume separate memory. Even when `MaxHeapSize` is known, you still need process RSS/cgroup data and other memory tools when investigating OOMKilled.

## 5. VM.system_properties — Current Java System Properties

Syntax:

~~~bash
jcmd 12345 VM.system_properties
~~~

The output consists of **`key=value`** pairs provided by Java system properties inside the JVM at read time; typical properties include:

~~~text
java.version=17...
java.home=...
java.class.path=...
user.dir=...
file.encoding=...
demo.mode=runtime
~~~

This is an **abbreviated example**, where `...` denotes environment-dependent values rather than literal data. A program can also add/modify properties, for example:

~~~java
System.setProperty("demo.mode", "runtime");
String mode = System.getProperty("demo.mode");
~~~

The snippet above is **API illustration only**; to run standalone, use the full program in Section 7. If a JVM was originally started with `-Ddemo.mode=startup` and the program later calls `System.setProperty("demo.mode", "runtime")`, capturing `VM.system_properties` may show `demo.mode=runtime`. That is evidence that **current config differs from startup input**, not a “contradiction” between two commands.

Distinguish three frequently conflated sources:

| What is read | Setting example | How to inspect | Limitations |
| --- | --- | --- | --- |
| **Java system property** | `-Ddemo.mode=startup` or `System.setProperty` | `VM.system_properties` / `System.getProperty` | Can be mutated at runtime |
| **Environment variable** | `APP_MODE=prod` in shell/pod | `System.getenv("APP_MODE")` or OS/container tools | Does not automatically become a Java system property |
| **Application/framework config** | YAML, JSON, config server, secret manager, command-line application args | Application framework diagnostics/config mechanisms | May merge multiple sources by precedence; not necessarily a JVM property |

For example, `SPRING_PROFILES_ACTIVE` is an environment variable a framework may read and map into application config, but do not assume it appears verbatim in `VM.system_properties`. Likewise, `java.version`/`user.dir` appearing in system properties does not turn them into environment variables.

**Snapshot note:** properties may be changed concurrently by other code; treat output strictly as a snapshot at command execution time. When two reads differ, save timestamps and identify which code/config mutated them. Do not use it to directly infer **all** environment variables, secrets, and runtime configuration.

**Data protection:** system properties can contain internal endpoints, user info, truststore/keystore paths, proxy details, tokens, or sensitive data stuffed into `-D` by the app. Do not publish raw dumps; restrict access and perform controlled redaction when building reports.

## 6. VM.info — Comprehensive JVM and Environment Context

Syntax:

~~~bash
jcmd 12345 VM.info
~~~

`VM.info` prints a report on **JVM environment and status** for the running installation. On many HotSpot builds, output can be lengthy and include sections on JVM/runtime, compiler/GC, configuration, OS, CPU, memory, or VM status details. **Do not rely on a fixed section order or catalog**: a different JDK, vendor, or upgrade may alter which sections appear. Run `jcmd 12345 help VM.info` to see supported command options for your exact target.

When it helps:
- Investigating differences across machines/containers running the same application.
- Adding runtime context to a bug report for reproduction: JDK build/vendor, OS, CPU, memory, JVM state at capture time.
- Combining with `VM.command_line` and `VM.flags` to verify environment effects, especially container limits or ergonomic decisions.
- Gathering extra context when CPU/GC/memory anomalies occur while application logs show only symptoms.

**Do not over-interpret:** `VM.info` is not a heap dump, thread timeline, CPU profiler, JFR recording, or full accounting of every native memory allocation. Depending on the issue, you may need `GC.heap_info`, `Thread.print`, GC logs/JFR, NMT, or OS/container metrics; those lie **outside the four core commands** of this lesson.

**Operational aspect:** JDK documentation classifies these four commands as low-impact diagnostics, yet `VM.flags -all` and `VM.info` can still produce substantial text, take time to read/store, and contain sensitive data. Avoid tight polling loops or indiscriminate collection during incidents. Choose timing, PID, scope, and storage safely.

## 7. Java 17+ Practice: Observing Startup vs. Runtime Differences

The program below **runs standalone** on Java 17+. It reads a system property from startup, **intentionally mutates it at runtime**, prints the count of application arguments, and keeps the process alive long enough for you to invoke `jcmd` from another terminal.

Save the code verbatim as **VmIntrospectDemo.java**:

~~~java
public final class VmIntrospectDemo {
    public static void main(String[] args) throws InterruptedException {
        System.out.println(
                "initial.demo.mode=" + System.getProperty("demo.mode", "unset")
        );

        System.setProperty("demo.mode", "runtime");

        System.out.println(
                "current.demo.mode=" + System.getProperty("demo.mode")
        );
        System.out.println("appArgCount=" + args.length);
        System.out.println("ready");

        Thread.sleep(120_000L);
    }
}
~~~

Compile and run in **Terminal 1**:

~~~bash
javac VmIntrospectDemo.java
java -Xms128m -Xmx256m -Ddemo.mode=startup VmIntrospectDemo alpha beta
~~~

**Exact stdout of the application before sleeping:**

~~~text
initial.demo.mode=startup
current.demo.mode=runtime
appArgCount=2
ready
~~~

The main thread then sleeps for up to about 120 seconds (in practice it may wake slightly later). In an interactive terminal, you can stop it with Ctrl+C once done testing. Note that this is an experimental program, **not an HTTP server**.

In **Terminal 2**, run while the process is still alive:

~~~bash
jcmd -l
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
jcmd 12345 VM.flags -all
jcmd 12345 VM.system_properties
jcmd 12345 VM.info
~~~

**Replace `12345` with the actual `VmIntrospectDemo` process PID.** If containers hide it from `jcmd -l`, obtain the PID from the proper process environment.

Targeted comparison:

| Question | Expected indicator |
| --- | --- |
| Was `-Ddemo.mode=startup` passed? | `VM.command_line` typically shows the corresponding startup JVM argument |
| What is the current property value? | `VM.system_properties` shows `demo.mode=runtime` because the code modified it |
| Are `alpha beta` JVM flags or app arguments? | They are **two application arguments**, appearing as represented by the launcher in `java_command`, not VM flags |
| Were `-Xms128m` and `-Xmx256m` set? | Startup contains the options; `VM.flags` can show effective `InitialHeapSize` and `MaxHeapSize` |
| Where do VM/OS details come from? | `VM.info` provides runtime and environment context, depending on the JVM |

**Do not fabricate fake stdout for `jcmd`:** each environment has a different PID, Java build, OS, classpath, flag list, and memory size. The example output above only illustrates structure; the guaranteed lines printed by the program are the four application lines shown above.

### Self-Check Exercises

1. Remove `-Ddemo.mode=startup` and run again: `initial.demo.mode=unset`, then the property is changed to `runtime`. This time `VM.command_line` has no `-Ddemo.mode=startup`, yet `VM.system_properties` still contains `demo.mode=runtime`.
2. Change `-Xmx256m` to `-Xmx384m`: observe the change in `VM.command_line` and `MaxHeapSize` via `VM.flags`. Do not assume RSS/cgroup memory equals heap max.
3. Omit the two arguments `alpha beta`: `appArgCount=0`; this does not mean the JVM lost its flags or system properties.
4. Observe `VM.info` across two different environments; record **which fields are actually present** before comparing, rather than assuming an identical output schema.

## 8. Configuration Comparison Workflow During Incident Diagnostics

A capture record is far more valuable when it answers “which process, at what time, is seeing what, and where does it differ from expectations?”:

**Step 1 — Specify the target process.** Record service, pod/container, host, timestamp with timezone, PID in the active namespace, Java version/vendor, and deployment revision. PIDs can be reused by the OS after a restart, so tie them to start time.

**Step 2 — Save the startup trace.** Capture `VM.command_line` to check JVM options, agents, class/JAR, and application arguments. Compare against the actually deployed manifest/entrypoint, not just source config files.

**Step 3 — Save flag values.** Capture `VM.flags`; use `VM.flags -all` when you need to find a flag omitted from the short view. For heap/GC suspicions, verify `InitialHeapSize`, `MaxHeapSize`, GC choice, and origin markers if available.

**Step 4 — Check system properties.** Capture `VM.system_properties` and compare only relevant keys after filtering secrets. If a live property differs from `-D`, investigate code calling `System.setProperty`, initialization libraries, or framework config.

**Step 5 — Attach execution context.** Capture `VM.info` and OS/container metrics if needed. For instance, two pods with the same `-Xmx` but different memory limits/CPU quotas can still behave differently. `VM.info` aids interpretation; it does not replace cgroup data or metrics near the incident time.

**Step 6 — Build an expected/actual table.** Avoid vague notes like “JVM misconfigured”. For example:

| Item to verify | Expected from deployment | Actual from process | Verifiable conclusion |
| --- | --- | --- | --- |
| Max heap | `-Xmx512m` | `VM.command_line` shows `-Xmx256m`; `VM.flags` reports corresponding max heap | Actual launch differs from expected config; trace entrypoint/override |
| App property | `-Dapp.mode=prod` | Startup was `prod` but live property is `test` | Likely mutated after startup; find the mutation source |
| Java runtime | Approved JDK 17 build | `VM.info` shows a different vendor/build | Check image digest/bundled JDK before blaming application code |

These values **illustrate only how to record**, not data taken from a real JVM. Save outputs with timestamps and exclude secret strings from reports.

### Tricky Case: VM.flags Does Not Match Command Line

Not every difference is a bug:
- `-Xmx` maps to an internal flag name and may undergo alignment adjustments.
- Some flags are chosen **ergonomically** rather than appearing on the startup command.
- `-XX:MaxRAMPercentage` together with CPU/memory limits influences automatic heap calculation when no explicit override is given.
- Some flags support runtime modification, so current values can differ from startup input; confirm how it was changed rather than guessing from a single output.
- Different vendors/JDK versions can change supported flags and default mechanisms.

To prove “deployment config was overridden,” combine startup arguments, effective values, flag origin (if displayed by the JVM), and container/launcher configuration; do not infer from a single line.

## 9. When jcmd Fails or Output Is Incomplete

| Symptom | Possibilities to check | Next action |
| --- | --- | --- |
| `jcmd -l` does not see the process | Different PID namespace/container; JVM not discovered | Find PID via process tools in the proper namespace; avoid scanning all-process |
| `Could not attach` / permission denied | Different user/group, attach disabled, temp dir, or restricted environment | Check permissions and attach mechanism; run tool in appropriate environment |
| PID exists sometimes and disappears others | Process restarting/crashing/exiting, PID reused | Check timestamps, start time, logs, and container events |
| `Unknown diagnostic command` | Unsupported by vendor/JDK or different command name | Run `jcmd <pid> help` on the target JVM; do not guess options |
| `VM.flags` lacks the flag of interest | Default view lists a limited subset | Try `VM.flags -all` if supported by target; check `help` |
| `VM.system_properties` lacks env variables | OS env vars are not Java properties | Use appropriate env/container tools and config loading logic |
| Output too large or contains secrets | Command/info/properties contain sensitive operational data | Limit scope, store internally, redact before sharing |
| Numbers differ between two captures | Process restarted, runtime changed, or measured at wrong time | Verify PID + start time, version, timestamp, and trace changes |

**Do not change configuration just because one unexpected line appears.** First verify the value's purpose and origin, JVM version, launch method, container limits, and baseline. The four commands studied here are state-verification tools; analyzing CPU hotspots, memory leaks, or deadlocks requires dedicated evidence.

## 10. Common Mistakes and How to Avoid Them

- **Calling `VM.command_line` “the current application configuration”.** It reflects the startup command retained by the VM; frameworks and runtime code may alter config afterward.
- **Confusing `-D` with `-XX`.** `-Dkey=value` creates a Java system property, whereas `-XX:...` sets a VM flag; they are separate systems.
- **Confusing args after the main class with JVM flags.** In `java -Xmx256m App one two`, `one two` are `main` arguments, not JVM options.
- **Seeing a short `VM.flags` output and concluding flags are missing.** Query `VM.flags -all` and check value origins if needed.
- **Confusing heap numbers with process/container memory.** `MaxHeapSize` does not cover the entire memory footprint.
- **Confusing Java properties with environment variables.** `System.getProperty` and `System.getenv` have different sources and management.
- **Reading every output as a fixed schema.** Sections, flags, and field names in `VM.info` or `VM.flags -all` vary across JDKs/vendors.
- **Reading a PID in the wrong namespace.** When a JVM runs in a container, host PID and container PID differ; tie evidence to the exact process.
- **Running commands against a restarted process.** PIDs can change or be reused; verify timestamps and start time.
- **Treating a snapshot as root cause.** It shows state; causality must be proven with timelines, metrics, logs, and deployment events.
- **Putting secrets on command line/properties and sharing raw dumps.** Sanitize sensitive data and restrict access.
- **Using other commands for a “quick check” that mutate state.** `VM.set_flag` or active VM commands are different from the four observation commands here.

## 11. Summary Checklist for Incident Handoff

A report on a Java process should contain:

1. **Identity:** service, PID, host/container, observation timestamp, and JDK version.
2. **Startup:** relevant JVM/application arguments from `VM.command_line`.
3. **Effective VM settings:** key flags and actual values from `VM.flags` or `VM.flags -all`.
4. **Current Java properties:** relevant keys in `VM.system_properties`, noting any startup discrepancy and with secrets redacted.
5. **Environment/status:** actual fields observed from `VM.info`, combined with OS/container metrics if the hypothesis requires them.
6. **Expected vs. actual:** expected configuration source and actual evidence, plus possible change timestamps.
7. **Unknowns:** do not speculate on override mechanisms or incident root cause from a single snapshot.

**Key takeaway:** `VM.command_line` looks at **startup input**; `VM.flags` reveals **effective JVM flag values**; `VM.system_properties` is a **snapshot of current Java properties**; `VM.info` supplies **overall JVM environment and status context**. Read all four layers for **the same PID, same time window, and same JDK** to avoid mismatching evidence.

**Reference:** Oracle JDK 17, *The jcmd Command*, https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html. Use `jcmd <pid> help <command>` to verify actual syntax and flags on the JVM under investigation.