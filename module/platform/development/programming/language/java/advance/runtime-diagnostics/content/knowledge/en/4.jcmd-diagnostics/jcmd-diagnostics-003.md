# 4.3. Discovering Commands with help and Reading Syntax, Options, and Impact Levels

`jcmd` is a tool that sends **diagnostic commands** to a running JVM. Before requesting a thread dump, heap histogram, heap dump, or JFR recording, an operator needs to know **whether the target JVM supports the command, what its exact syntax is, which parameters are required, and how the command affects the application**. The most reliable answer comes from the **target JVM's own `help`**, then cross-checked against documentation for the exact JDK/vendor/version.

This lesson belongs to section **4. The jcmd Tool**, focusing on the workflow for discovering and **reading** help, rather than assuming every `jcmd` command is harmless or immediately running commands that can pause the JVM or mutate state in production.

**After this lesson, you will be able to:**
- Distinguish `jcmd -h`, `jcmd -l`, `jcmd <PID> help`, `jcmd <PID> help <COMMAND>`, and `jcmd <PID> help -all`.
- Accurately read **Description, Impact, Permission, Syntax, Options, Arguments, data types, and default values** in help output.
- Interpret **Impact: Low / Medium / High** according to what impact level actually means; separate impact from **access permissions** and **state-changing effects**.
- Choose commands matching your measurement goal, operational constraints, and available resources; resolve syntax errors or missing commands without trial-and-error on live systems.

## 1. Understanding the three layers of jcmd

There is no single global `help` command that replaces everything. Keep them separate:

| Layer | Example | Purpose |
| --- | --- | --- |
| **Caller-side jcmd utility** | `jcmd -h` or `jcmd --help` if supported by the tool build | View command-line launcher usage, target selection, and switches of the `jcmd` program itself |
| **List of visible JVMs** | `jcmd -l` | Find Java processes listable in the current environment |
| **Diagnostic commands published by the target JVM** | `jcmd 12345 help` | Query **the JVM at PID 12345** for the commands it supports |
| **Details of one diagnostic command** | `jcmd 12345 help Thread.print` | Read description, impact, permission, syntax, options, and arguments of `Thread.print` on that exact JVM |
| **Details of all commands** | `jcmd 12345 help -all` | Print full help for all published commands; output is usually long |

In these examples, **12345 is only an illustrative PID** and must be replaced with the real PID in the right namespace. `jcmd -h` is help for the **tool program**; `jcmd 12345 help` is the `help` diagnostic command sent to the **running JVM**. This distinction matters: the caller-side tool may come from a different JDK than the target JVM, while the command list depends on the target JVM's version and state.

A sensible discovery order:

~~~bash
jcmd -h
jcmd -l
jcmd 12345 help
jcmd 12345 help Thread.print
~~~

If you need to inspect all descriptions instead of one command:

~~~bash
jcmd 12345 help -all
~~~

**You do not need to execute `Thread.print`, `GC.heap_dump`, or a GC command just to read its help.** Discovery starts with lookup first.

## 2. Identify the right target JVM before asking for help

`jcmd` needs to connect to a live JVM, typically on the same machine and under the **effective user/group** matching the process; attach permissions, runtime image, and OS/container policies can all affect access.

Minimum identification workflow:

1. Identify **service, container/pod, host, PID, observation timestamp, Java vendor/version**.
2. Try `jcmd -l` in the appropriate environment, matching the main class/JAR name with the desired service.
3. If the process is not visible because it is in Docker or another PID namespace, find the PID using process/container tools **in the right namespace**. `jcmd -l` failing to list it **does not by itself prove** the process is dead.
4. Run `jcmd <PID> help` and make sure the PID still represents the right JVM, avoiding PID reuse after a restart.
5. If attach fails, check user/group, access permissions, whether attach is disabled, whether the JDK includes `jcmd`, filesystem/namespace setup, and JVM state.

Two targeting forms must be understood before use:
- `jcmd 0 <COMMAND>` can send the command to **every JVM** visible to the utility.
- `jcmd <MAIN_CLASS> <COMMAND>` can match **multiple processes** sharing the same main class.

Therefore, when learning or diagnosing a specific JVM, **prefer a directly verified PID** to avoid unintended broadcasts. Querying help by PID also retrieves the exact syntax for the target version.

If the program has already exited or suffered a JVM fatal crash, `jcmd` cannot attach to the old process; use logs, `hs_err`, core dumps, exit reasons, and deployment metadata for analysis instead of blindly trying a new PID.

## 3. Reading a help page from top to bottom

Example:

~~~bash
jcmd 12345 help Thread.print
~~~

On a HotSpot/OpenJDK build, the output has a structure similar to this (exact wording/formatting may vary by build):

~~~text
Thread.print
Prints all threads with stacktraces.

Impact: Medium: Depends on the number of threads.
Permission: java.lang.management.ManagementPermission(monitor)

Syntax : Thread.print [options]

Options:
    -l : [optional] Prints java.util.concurrent locks (BOOLEAN, false)
~~~

This is a **simplified example for learning how to read help**, not fixed stdout across every JDK. Break it down question by question:

| Help field | Meaning | Key point to remember |
| --- | --- | --- |
| **Command name** | Diagnostic command name, e.g., `Thread.print` | Usually case-sensitive and contains a dot in the name |
| **Description** | Purpose of the command | Tells what the command *performs*, not a promise that every run has identical performance |
| **Impact** | Classification of expected impact on the target JVM | May include conditions depending on thread count, heap size, or contents |
| **Permission** | Runtime/Java permission documented for the command | Does not replace OS/container permissions needed to attach |
| **Syntax** | Invocation form after `jcmd <PID>` | Square brackets are **meta-syntax**, do not type `[` and `]` literally |
| **Options** | Named parameters, e.g., `-l`, `-all`, `name=...` | Check type, default, optionality, and writing format |
| **Arguments** | Positional parameters, e.g., `filename` | Check whether required and order per help |

The line `Syntax : Thread.print [options]` means running:

~~~bash
jcmd 12345 Thread.print
jcmd 12345 Thread.print -l
~~~

and **not** typing:

~~~text
jcmd 12345 Thread.print [options]
~~~

In `Thread.print`, `-l` is a boolean option to print additional information about `java.util.concurrent` locks; **`-l` here differs from `jcmd -l`** (listing processes), even though it is spelled the same. Context determines meaning.

### Options, arguments, optional/default, and data types

When reading a parameter, extract all four attributes:

1. **Name**: e.g., `-l`, `-all`, `name`, `duration`, or positional `filename`.
2. **Data type**: `BOOLEAN`, `STRING`, `INT/INTEGER`, duration with unit suffix per description, etc.
3. **Optional or required**: `[optional]` or `(Optional)` indicates the parameter can be omitted; `no default value` on a required argument means a value must be passed.
4. **Default**: the value used when the option is omitted; it is **not** a value you actively configured.

Some commands expect options in **`key` or `key=value`** form, and help states the rule clearly. For instance, a boolean may be written `-all` or an equivalent form if supported; strings/durations typically require `name=myrecording`, `duration=60s`. Do not assume every command recognizes the same `-all` flag or the same `m`, `s`, `k` suffixes; each command has its own grammar.

**Arguments with spaces:** paths or values containing spaces must be properly shell-quoted before reaching `jcmd`. Quoting rules on Bash, PowerShell, and cmd.exe can differ. The syntax shown by `jcmd ... help <COMMAND>` only states **how the command accepts parameters**, while the shell processes quotes/escapes before the program receives them. When unsure, use paths without spaces in test environments and test directly in the exact shell you use.

**Position of options and arguments:** read `Syntax` together with `Options/Arguments`. For `GC.heap_dump`, `filename` is a positional argument, unlike flag options. Do not turn every parameter into `name=value` just because another command uses that form.

## 4. What do Impact: Low, Medium, and High actually say?

`Impact` in HotSpot help is a **qualitative assessment of expected impact** when executing the diagnostic command on the target JVM, not a certification that it causes no pause, consumes no disk, changes no state, or is safe to run unconditionally in production.

| Level | Operational interpretation | Examples in JDK 17 docs |
| --- | --- | --- |
| **Low** | Usually relatively small impact; still has cost and can alter state if it is a control command | `VM.version`, `VM.flags`, `VM.command_line`, `VM.info`; `JFR.start` also says Low even though it **starts a recording** |
| **Medium** | Can involve noticeable work; duration depends on workload and data size | `Thread.print` (depends on thread count), `GC.heap_info`, `VM.native_memory` |
| **High** | Potentially significant resource cost/pause; evaluate before using on live load | `GC.class_histogram`, `GC.heap_dump`; depends on heap size/content |

**Two key points to remember:**

- `Low` **does not mean "read-only"**: `VM.set_flag` is labeled Impact: Low yet **changes a VM flag**; `JFR.start` is Impact: Low yet **starts a recording**, incurring overhead/disk usage; `ManagementAgent.start` can start the management agent. Read the **Description** and consequences, not just the Impact label.
- `Medium/High` **is not a fixed number of milliseconds**. `Thread.print` depends on thread count; `GC.heap_dump` depends on heap size/content, disk capacity, I/O subsystem, and may request a full GC. A command can significantly affect a large workload while appearing minor on a small test machine.

**Four questions to ask before executing any command:**
1. **What action?** Printing info, starting collection, requesting GC, writing a file, or modifying a runtime flag?
2. **What impact?** Is there a condition like "depends on heap size/number of threads"?
3. **What resources?** CPU, pause, RAM, disk, I/O, output size, sensitive data?
4. **Does it fit the current goal?** Is there a lower-impact approach, or does operations need advance notice within an approved window?

If you cannot answer these yet, only read `help` to gather information—**do not test-run commands in production** just to see what they do.

## 5. Examples of reading help by goal

### 5.1. Checking JVM flags: typically an Impact Low command

~~~bash
jcmd 12345 help VM.flags
~~~

Reading help: the command prints VM flag values; Impact: **Low**; syntax `VM.flags [options]`; an optional boolean `-all` defaulting to false prints **all flags supported by the JVM**. Once you need to run the read command after identifying the right PID:

~~~bash
jcmd 12345 VM.flags
jcmd 12345 VM.flags -all
~~~

The `-all` form can print **many lines**, so consider where to save it and how to redact secrets. `-all` in `VM.flags` is not the same as `-all` in `GC.heap_dump` or `help`.

### 5.2. Thread dump: Impact Medium scaling with thread count

~~~bash
jcmd 12345 help Thread.print
~~~

Help states `Syntax : Thread.print [options]`, an option `-l` defaulting to false, and Impact **Medium** because cost relates to the number of threads. If you need to run it to investigate lock ownership, check the thread count and operating environment carefully:

~~~bash
jcmd 12345 Thread.print -l
~~~

Output can be very long, especially with many workers. `Thread.print` is a **snapshot**; a thread in `WAITING` does not by itself prove a deadlock. Analyzing stalls usually requires comparing multiple timestamped snapshots alongside processing progress.

### 5.3. Heap histogram: Impact High

~~~bash
jcmd 12345 help GC.class_histogram
~~~

JDK 17 docs classify Impact **High**, depending on heap size/content. The command gives heap statistics by object class; its `-all` option specifies whether to include objects that are not yet unreachable (including unreachable objects). Do not read `-all` and assume it merely "prints more columns" like `VM.flags`. If your goal is only confirming general heap sizing, inspect `help` for `GC.heap_info` before considering a histogram.

### 5.4. Heap dump: Impact High, with positional filename

~~~bash
jcmd 12345 help GC.heap_dump
~~~

Key parts in JDK 17 docs:

- **Description:** creates an HPROF heap dump file.
- **Impact:** High, depends on heap size/content.
- **Syntax:** `GC.heap_dump [options] [arguments]`.
- **Options:** `-all` is an optional boolean, default false; enable to dump unreachable objects as well per description.
- **Arguments:** `filename` of type STRING, **required**, no default.
- **Behavior:** in JDK 17, the command normally **requests a full GC before dumping**, unless `-all` is used under documented conditions.

Sample syntax to **understand argument placement**, not a recommendation to run immediately:

~~~text
jcmd 12345 GC.heap_dump /var/tmp/heap-12345.hprof
jcmd 12345 GC.heap_dump -all /var/tmp/heap-12345-all.hprof
~~~

Dumps can be huge, cause pauses, fill disks, and contain sensitive data in the object graph. Before actually running one, verify where the process can write, available space, diagnostic purpose, and operational conditions. **Filename having no default** means you cannot omit the file argument expecting the command to pick a path automatically.

### 5.5. JFR.start: Impact Low yet has side effects

~~~bash
jcmd 12345 help JFR.start
~~~

Help lists options such as `name`, `duration`, `settings`, `filename`, `delay`, `disk`. Example **illustrative syntax** once you decide to collect JFR on an appropriate process:

~~~text
jcmd 12345 JFR.start name=diagnose settings=profile duration=60s filename=/var/tmp/diagnose.jfr
~~~

`JFR.start` in JDK 17 docs has Impact Low, yet it **starts recording** and can write files/consume resources. `settings=profile` captures more detailed events than `default`; do not treat overhead as zero. When you only want to know whether any recording is running, explore `help JFR.check` and use the observation command instead of starting a new recording automatically.

### 5.6. VM.set_flag: counterexample for Impact Low

~~~bash
jcmd 12345 help VM.set_flag
~~~

JDK 17 docs state **Impact: Low**, yet Description clearly states it **sets a JVM flag value** and Permission relates to `control` permission. This is a **state-changing command**, completely different from the read-only `VM.flags`. If your goal is verifying current configuration, use `VM.flags`, not `VM.set_flag`. This is an important example showing that **Impact and "read-only/write" are two separate classification axes**.

### 5.7. GC.run: Medium yet not a read command

~~~bash
jcmd 12345 help GC.run
~~~

`GC.run` is documented as calling `System.gc()`; Impact Medium depends on heap size/content. That means it is a **request for GC action**, not a passive snapshot. Do not run it just to "see if the JVM does GC". Distinguish it from `GC.heap_info` (reading heap info) and `GC.class_histogram` (producing statistics with High Impact).

## 6. Three similar-looking name pairs that cause confusion

### 6.1. `help -all` vs. `VM.flags -all` vs. `GC.heap_dump -all`

| Command | Meaning of `-all` |
| --- | --- |
| `jcmd 12345 help -all` | Displays **help** for all diagnostic commands published by the JVM |
| `jcmd 12345 VM.flags -all` | Prints all supported VM flags and their values per JVM capability |
| `jcmd 12345 GC.heap_dump -all /path/file.hprof` | Requests the dump to include unreachable objects; impact and contents differ from default dump |

There is no rule that "`-all` always does the same thing"; you must read `help <COMMAND>`.

### 6.2. `jcmd -l` vs. `Thread.print -l`

- `jcmd -l`: **option of the jcmd tool** to list JVMs.
- `jcmd 12345 Thread.print -l`: **option of the diagnostic command** to display extra `java.util.concurrent` lock details.

The two options belong to two different parsers. Identical spelling does not guarantee identical meaning.

### 6.3. `-Dkey=value` at JVM startup vs. `name=value` of a diagnostic command

- `java -Dapp.mode=prod MyApp`: sets a Java system property **at startup**.
- `jcmd 12345 JFR.start name=diagnose ...`: passes a **named option of a diagnostic command** to an already running JVM.

Do not use `-D` for every `jcmd` option, and do not expect command options to appear automatically in `VM.system_properties`.

## 7. Hands-on with a self-written Java 17+ program

Goal: have a real, live JVM long enough to try **help commands only**. No need to artificially create a memory leak, deadlock, or trigger a heap dump.

Create file **JcmdHelpTarget.java** with complete contents:

~~~java
public final class JcmdHelpTarget {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("JcmdHelpTarget ready");
        Thread.sleep(180_000L);
    }
}
~~~

Compile and run in **Terminal 1** using JDK 17 or higher:

~~~bash
javac JcmdHelpTarget.java
java JcmdHelpTarget
~~~

**Exact stdout right after starting:**

~~~text
JcmdHelpTarget ready
~~~

The program keeps the main thread sleeping for about 180 seconds, printing no extra lines on normal exit. That duration is **the lifetime of the example app**, not the runtime of a `jcmd` task. If that window expires, the JVM exits and must be restarted to continue experimenting. You can stop it with Ctrl+C once finished.

In **Terminal 2** on the same machine and under the right user:

~~~bash
jcmd -l
~~~

Find the line with `JcmdHelpTarget` and note the **actual PID**. Assuming the PID is 12345, explore in order:

~~~bash
jcmd 12345 help
jcmd 12345 help VM.version
jcmd 12345 help Thread.print
jcmd 12345 help GC.heap_dump
jcmd 12345 help JFR.start
jcmd 12345 help VM.set_flag
jcmd 12345 help -all
~~~

The list above **only invokes `help`**, without executing dumps or changing flags. There is no fixed stdout for `jcmd` because PID, vendor, JDK build, command catalog, and help formatting depend on the target JVM. The guaranteed output of `JcmdHelpTarget` is the `JcmdHelpTarget ready` line noted above.

Record an observation table for **each** command:

| Command | Description | Impact | Permission | Syntax | Special parameters | Read operation or side effect |
| --- | --- | --- | --- | --- | --- | --- |
| `VM.version` | Reads JVM version | Low | Per help | No typical positional args | None | Read |
| `Thread.print` | Prints thread stacks | Medium | Per help | `Thread.print [options]` | `-l` | Snapshot read, sampling cost |
| `GC.heap_dump` | Writes HPROF heap | High | Per help | `GC.heap_dump [options] [arguments]` | Required `filename`, `-all` | Writes file/resource intensive; possible full GC |
| `JFR.start` | Starts Flight Recording | Low | Per help | Multiple named options | `duration`, `filename`, `settings` | Mutates recording state |
| `VM.set_flag` | Changes flag value | Low | `control` permission per help | Positional flag name/value | Applies only to eligible flags | Modifies VM config |

This table shows **expectations for JDK 17**; in practice, prioritize the actual output printed by the target JVM. If a command is not listed, do not jump to assuming a `jcmd` bug: it may depend on JVM build, vendor, environment, or the command being hidden/unsupported.

### Mini exercises

1. On the same JVM, compare `help VM.flags` and `help GC.heap_dump`; identify which command only prints information, which creates a file, and what makes their Impact differ.
2. Inspect `-all` across `help`, `VM.flags`, and `GC.heap_dump`; explain why they cannot be used interchangeably.
3. Find one command with **Low Impact yet state-changing behavior** and present two pieces of evidence from help (Description and Permission/Options).
4. Inspect `help Thread.print` and answer whether `-l` is optional or required, what its default is, and why thread count affects cost.
5. Once the example JVM's lifetime expires, retrying `jcmd 12345 help` may fail or hit a reused PID; describe how to verify the process before the next attempt.

## 8. Making decisions based on purpose and impact level

Before sending an execution command, write down the exact observation need. A suitable practical flow:

~~~text
Identify the symptom to investigate
       |
       v
Identify right JVM/PID + Java vendor/version
       |
       v
jcmd <PID> help
       |
       v
jcmd <PID> help <COMMAND>
       |
       v
Read Description + Syntax + Options/Arguments
       |
       v
Read Impact + Permission + side effects
       |
       +-- Only need small config data --> consider Low read command
       |
       +-- Need thread/heap statistics --> weigh Medium/High against load
       |
       +-- Need dump/record/change flag --> verify resources, maintenance window
       |
       v
Execute purposefully; record timestamp, PID, output, and observed impact
~~~

**Impact is a decision signal**, not a policy of "auto-run Low, forbid High". A Low command can mutate the VM; a High command may be necessary during an incident with proper preparation. Look at **actual purpose and consequences** first, then pick the tool.

### Scenario A: Need to verify heap parameters

Start with `help VM.flags` and `help VM.command_line`; then use the corresponding read commands to compare effective flags against startup args. Do not create a heap dump just to find out what `-Xmx` is set to.

### Scenario B: Suspected deadlock

Check `help Thread.print` and its Medium Impact, thread count, and how output will be stored. Collect timestamped snapshots when needed to look for lock owners/wait chains. `Thread.print` does not prove the root cause in a single sample.

### Scenario C: Suspected memory leak

`GC.heap_dump` can be useful for retention analysis, but it is High Impact and writes a large file; consider `GC.heap_info`, metrics, GC logs/JFR, and heap-dump criteria first. Do not treat `-all` as a "safer" dump mode in every situation; it changes the object set and interacts with the command's GC behavior.

### Scenario D: Only want to know if any JFR recording is running

`help JFR.check` lets you see the syntax of the observation command; do not start a new recording with `JFR.start` if the goal is merely checking status. `JFR.start`'s Low label does not make it a read command.

### Scenario E: Need to know whether a VM supports a new command

A command may exist in a newer JDK yet be absent in the running JVM; `jcmd <PID> help` is the direct measure. Do not force syntax from a blog post written for a different JDK, and do not upgrade production versions just because a documented command is missing.

## 9. When help or attach does not work

| Symptom | What to verify | Reasonable handling |
| --- | --- | --- |
| `jcmd -l` does not see the JVM | Different container/PID namespace, JVM exited, missing listing permission | Find process in the right environment, verify PID and start time |
| `Could not attach` / permission denied | Effective UID/GID, OS policy, attach disabled, hung runtime | Run from right user/environment or use prepared observation channels |
| `Unknown diagnostic command` | JVM version/vendor lacks command, wrong capitalization | Run `jcmd <PID> help` and check exact name from the list |
| Command exists in help, but invocation fails | Missing positional argument, wrong option name, wrong type/unit, or shell quoting | Re-read `Syntax`, `Options`, `Arguments`; check `=` signs and spaces |
| `-all` yields unexpected behavior | Option name collision with another command | Read help of **the exact command being invoked** |
| Impact/Permission fields missing compared to example | Different vendor/JDK or output format | Rely on actual help and JDK/vendor docs; do not fabricate values |
| Output too long or contains secrets | Command prints many flags/properties/stacks/paths | Choose narrow scope, store in restricted location, redact before sharing |
| Read-only command still hurts performance | Collection cost, thread/heap count, or high call frequency | Adjust frequency and command choice; correlate latency/CPU/GC during capture |

An error returned by `help` is **no reason to blindly try all commands one by one**. Separate attach errors, nonexistent commands, and syntax errors; each group has a distinct fix.

## 10. Common misconceptions

- **"`jcmd -h` already lists all commands of the current JVM."** False: that is utility help; you must send `help` to a specific PID to see the target's command set.
- **"A command is in Java 21 docs, so Java 17 must have it."** False: version/vendor and build determine the list.
- **"`-all` always has one meaning."** False: parameters are parsed within each command's context.
- **"The `[options]` brackets must be typed literally."** False: square brackets in help denote optional components.
- **"`(STRING, no default value)` means it can be left blank."** False for **required positional arguments** such as `GC.heap_dump`'s filename.
- **"Impact: Low guarantees no change to the application."** False: `VM.set_flag` and `JFR.start` can alter state/behavior despite the Low label.
- **"Impact: High means the command always runs slowly for a fixed few seconds."** False: it depends on heap/content, I/O, and workload.
- **"Permission: monitor is enough to attach to any process."** False: OS permissions, user/group, containers, and JVM flags also apply.
- **"Thread.print Medium means there is a deadlock."** False: Impact is command cost, not a diagnosis of thread state.
- **"Once help opens, every command should be run right away."** False: help is an informational step; execution is a separate action that can write files, trigger GC, start recordings, or change flags.
- **"One help output covers every JVM with the same app name."** False: PID/JDK/vendor or capabilities can differ; diagnostics must track the actual target.
- **"Just substitute a similar-looking JVM command name if you get Unknown."** False: only use commands published by the JVM with exact syntax.

## 11. Practical checklist

Before deciding to execute a diagnostic command, you can log in the ticket:

1. **Target**: service, PID, host/container, Java vendor/version, timestamp, and operator.
2. **Discovery**: `jcmd <PID> help` confirmed the command exists.
3. **Syntax**: from `jcmd <PID> help <COMMAND>`, copy the exact name, required positional arguments, options, types, defaults, and units.
4. **Impact**: Low/Medium/High per target output; note conditions depending on heap size, thread count, or workload.
5. **Side effects**: read-only, snapshot output, file write, GC trigger, recording start, or flag change; evaluate disk space and impact window.
6. **Permissions**: runtime permission stated in help plus actual attach/OS/container permissions.
7. **Evidence**: save secret-redacted output, timestamp, PID/start time; record failed commands and error messages as well if any.
8. **Conclusion**: distinguish data obtained from the command from root-cause hypotheses; verify with metrics, timelines, and other appropriate tools.

**Key takeaway:** three distinct actions are **finding JVMs** with `jcmd -l`, **discovering commands** with `jcmd <PID> help [<COMMAND>]`, and **executing a command** with `jcmd <PID> <COMMAND> ...`. When reading help, always review **Description + Syntax + Options/Arguments + Impact + Permission** as one cohesive unit. **Low Impact does not guarantee read-only**, and High Impact does not mean a forbidden command; the choice depends on the goal and operating conditions of that specific JVM.

### References

- Oracle JDK 17, **The jcmd Command**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- Oracle JDK 17, **Diagnostic Tools** (examples of help structure): https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html

Documentation describes commands for the corresponding JDK; **help returned by the target JVM** remains the authoritative source to confirm which commands are actually available, their syntax, and Impact in the environment under diagnosis.