# When to Use jinfo?

`jinfo` is a command-line tool included with the JDK for reading configuration information from a running JVM. It can display system properties, VM flags, and the value of a specific flag. For certain dynamically manageable flags (*manageable flags*), the tool also allows enabling, disabling, or changing their values while the process is still running.

However, Oracle marks `jinfo` as *experimental and unsupported* and recommends using `jcmd` instead of legacy diagnostic tools like `jinfo`, `jstack`, and `jmap`. Therefore, this lesson focuses on recognizing when `jinfo` is still useful, understanding its limitations, and choosing the appropriate alternative.

## 1. What is jinfo used for?

A running JVM has various configuration details that need to be inspected when troubleshooting an issue:

- Which VM flags was the JVM started with?
- What is the current value of a specific flag?
- Which Java version, installation directory, and classpath is the application using?
- Which system properties are being provided to the JVM?
- Is a dynamically manageable flag currently enabled?

`jinfo` can answer these questions for a Java process specified by its PID.

Example:

~~~bash
jinfo 12345
~~~

If no option is passed, `jinfo` prints both VM flags and system property name/value pairs. The output can be long and may contain sensitive information, so in practice you should choose the narrowest option that meets your goal.

### 1.1. When should you use it?

`jinfo` can be appropriate in the following situations:

1. An existing operations runbook or script already uses `jinfo`, and the current environment still provides the tool.
2. You need to quickly inspect flags or system properties of a running JVM, such as when investigating differences between two instances.
3. You need to read the value of a specific flag without printing the entire configuration.
4. You need to temporarily enable/disable a dynamically manageable flag during an approved incident response session, and you already understand the impact of that flag.
5. You are learning or supporting a legacy system where you need to understand `jinfo` commands before migrating the runbook to `jcmd`.

If you are writing new automation, standardizing CI/CD, or designing long-term diagnostics workflows, prefer `jcmd`. It is recommended by Oracle for modern JVM diagnostics and offers more diagnostic commands.

## 2. Main jinfo options

Syntax on Java SE 21:

~~~text
jinfo [option] pid
~~~

`pid` is the process ID of the JVM to inspect. `jinfo` takes a PID; do not use the main class name as an argument in place of the PID.

| Command | Purpose |
|---|---|
| `jinfo <pid>` | Print VM flags and system properties |
| `jinfo -flags <pid>` | Print VM flags |
| `jinfo -sysprops <pid>` | Print system properties as name-value pairs |
| `jinfo -flag <name> <pid>` | Read the value of a VM flag |
| `jinfo -flag +<name> <pid>` | Enable a Boolean VM flag |
| `jinfo -flag -<name> <pid>` | Disable a Boolean VM flag |
| `jinfo -flag <name>=<value> <pid>` | Set the value of a VM flag if the flag allows modification |
| `jinfo -h` / `jinfo -help` | Print help |

### 2.1. Viewing all configuration

~~~bash
jinfo 12345
~~~

The output includes sections such as:

~~~text
Java System Properties:
java.version=21.0.x
java.home=/opt/jdk-21
user.dir=/srv/orders
...

VM Flags:
-XX:InitialHeapSize=...
-XX:MaxHeapSize=...
-XX:+UseG1GC
...
~~~

This is an illustrative example; actual names, ordering, and values depend on the JDK, JVM vendor, and how the application was launched.

Only use the optionless command when you genuinely need both groups of information. Some system properties may contain URLs, internal paths, usernames, or sensitive configuration details.

### 2.2. Viewing only VM flags

~~~bash
jinfo -flags 12345
~~~

Use this when you need to verify heap, GC, or certain HotSpot options passed to the JVM.

Note: the output shows the flags reported by the JVM; it is not an exhaustive list of every flag the JVM may support. In HotSpot, `-XX` is a group of implementation-dependent options that can change between releases.

### 2.3. Viewing only system properties

~~~bash
jinfo -sysprops 12345
~~~

Example of filtering specific properties after saving the output:

~~~bash
jinfo -sysprops 12345 > jvm-properties.txt
grep -E '^(java.version|java.home|user.dir|app.mode)=' jvm-properties.txt
~~~

On Windows PowerShell:

~~~powershell
jinfo -sysprops 12345 |
    Select-String '^(java.version|java.home|user.dir|app.mode)='
~~~

Do not paste the full output into public logs. System properties may contain internal endpoints, file paths, database configurations, or data considered confidential by your organization.

### 2.4. Reading a specific flag

~~~bash
jinfo -flag MaxHeapSize 12345
jinfo -flag UseG1GC 12345
jinfo -flag HeapDumpOnOutOfMemoryError 12345
~~~

This is useful when you only need to confirm an active setting. For example, `MaxHeapSize` shows the maximum heap limit in bytes; `UseG1GC` indicates whether the G1 GC selection flag is enabled.

Flag names and queryability depend on the HotSpot/JDK version. If you are unsure whether a flag exists in the target JVM, check the documentation for that exact JDK or use `jcmd <pid> VM.flags -all`.

## 3. When can you modify a VM flag with jinfo?

`jinfo` supports three forms of modification:

~~~bash
# Enable Boolean flag
jinfo -flag +HeapDumpOnOutOfMemoryError 12345

# Disable Boolean flag
jinfo -flag -HeapDumpOnOutOfMemoryError 12345

# Set flag value
jinfo -flag HeapDumpOnOutOfMemoryError=true 12345
~~~

Only flags that can be changed while the JVM is running accept this operation. In HotSpot, these are commonly called *manageable flags*. Flags that can only be set at startup will reject modifications.

### 3.1. Example: enabling heap dump on OutOfMemoryError

`HeapDumpOnOutOfMemoryError` is a dynamically manageable Boolean flag. You can check its current state:

~~~bash
jinfo -flag HeapDumpOnOutOfMemoryError 12345
~~~

If the output indicates the flag is disabled, you can enable it during an incident response session:

~~~bash
jinfo -flag +HeapDumpOnOutOfMemoryError 12345
~~~

Read it back to confirm:

~~~bash
jinfo -flag HeapDumpOnOutOfMemoryError 12345
~~~

Once enabled, the JVM can generate a heap dump if an OutOfMemoryError occurs afterwards. By default, the dump file is written in the process's working directory with a name like `java_pid<pid>.hprof`; the path can be configured with `-XX:HeapDumpPath` at startup. A heap dump can be very large and contain objects, strings, tokens, or user data from memory. Before enabling it, determine where the file will be written, access permissions, disk space, and the procedure for securing/deleting the file.

Changes made via `jinfo` only affect the current JVM instance. They do not modify source code, startup configuration files, or settings for the next run. If you want the flag to remain enabled after a restart, update the startup arguments or deployment configuration according to your project's workflow.

### 3.2. Which flags cannot be changed?

Not every VM flag can be changed at runtime. For example, the maximum heap size usually must be determined at startup:

~~~bash
jinfo -flag MaxHeapSize=268435456 12345
~~~

For a JVM where `MaxHeapSize` is not a manageable flag, the command will fail with a message similar to:

~~~text
AttachOperationFailedException:
flag 'MaxHeapSize' cannot be changed
~~~

This is expected behavior: a flag that does not allow runtime modification cannot be forced to change with `jinfo`. To change heap sizing, configure the appropriate `-Xmx` value and restart the JVM during an approved deployment window.

Do not experiment with changing production flags by trial and error. Before running a write command, verify that the flag is dynamically manageable, understand its impact, and have a rollback plan.

## 4. jinfo or jcmd?

Oracle JDK 21 recommends using `jcmd` instead of `jinfo` for modern diagnostics. Reading configuration and modifying certain flags can be performed with the corresponding diagnostic commands.

| Purpose | jinfo | Recommended jcmd |
|---|---|---|
| Read VM flags | `jinfo -flags <pid>` | `jcmd <pid> VM.flags` |
| Read all VM-supported flags | No full equivalent option | `jcmd <pid> VM.flags -all` |
| Read system properties | `jinfo -sysprops <pid>` | `jcmd <pid> VM.system_properties` |
| Read a single flag | `jinfo -flag <name> <pid>` | `jcmd <pid> VM.flags -all` and filter |
| Change a manageable flag | `jinfo -flag <name>=<value> <pid>` | `jcmd <pid> VM.set_flag <name> <value>` |
| View JVM version | Not its primary purpose | `jcmd <pid> VM.version` |
| View uptime | Not its primary purpose | `jcmd <pid> VM.uptime` |
| Thread dump, heap info, JFR | Not the right tool | Commands such as `Thread.print`, `GC.heap_info`, `JFR.start` |

Equivalent examples:

~~~bash
# Read flags
jcmd 12345 VM.flags

# Read all system properties
jcmd 12345 VM.system_properties

# List all VM-supported flags
jcmd 12345 VM.flags -all

# Change a manageable flag
jcmd 12345 VM.set_flag HeapDumpOnOutOfMemoryError true
~~~

Use `jcmd <pid> help` to see the diagnostic commands available on the target JVM. The set of available commands may vary across JVMs and versions.

### 4.1. Why prefer jcmd?

- Recommended by Oracle as the replacement for legacy diagnostic tools such as `jinfo`.
- Provides dedicated commands for flags, system properties, heap, threads, class loading, logging, and Flight Recorder.
- Lets you inspect command syntax and impact level via `help <command>`.
- Better suited for new runbooks and automation.
- A unified interface reduces the number of legacy tools you need to maintain.

`jinfo` can still be useful when supporting legacy systems or when a proven workflow depends on it. Do not choose it merely because the command name is shorter.

## 5. Java 17+ hands-on example: reading configuration from a running JVM

Create `JinfoTarget.java`:

~~~java
import java.util.concurrent.CountDownLatch;

public final class JinfoTarget {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("PID=" + ProcessHandle.current().pid());
        System.out.println("jinfo target ready");

        new CountDownLatch(1).await();
    }
}
~~~

Compile and run in the first terminal:

~~~bash
javac --release 17 JinfoTarget.java

java -Xmx128m \
  -Dapp.mode=staging \
  -Dapp.region=ap-southeast-1 \
  JinfoTarget
~~~

Stdout looks like:

~~~text
PID=12345
jinfo target ready
~~~

The PID is assigned by the operating system; use the actual PID printed by the program.

In the second terminal, inspect the configuration:

~~~bash
jinfo -flags 12345
jinfo -sysprops 12345
jinfo -flag MaxHeapSize 12345
jinfo -flag HeapDumpOnOutOfMemoryError 12345
~~~

In the system properties output, look for lines such as:

~~~text
app.mode=staging
app.region=ap-southeast-1
~~~

For the flag-reading commands, the output may look like:

~~~text
-XX:MaxHeapSize=134217728
-XX:-HeapDumpOnOutOfMemoryError
~~~

The values shown here correspond to the 128 MiB heap example; actual values may differ depending on the JDK and environment.

### 5.1. Enable the flag and verify

~~~bash
jinfo -flag +HeapDumpOnOutOfMemoryError 12345
jinfo -flag HeapDumpOnOutOfMemoryError 12345
~~~

Reading it back should show:

~~~text
-XX:+HeapDumpOnOutOfMemoryError
~~~

Disable it again after testing:

~~~bash
jinfo -flag -HeapDumpOnOutOfMemoryError 12345
jinfo -flag HeapDumpOnOutOfMemoryError 12345
~~~

The final output should show:

~~~text
-XX:-HeapDumpOnOutOfMemoryError
~~~

### 5.2. Compare with jcmd

~~~bash
jcmd 12345 VM.flags
jcmd 12345 VM.system_properties
jcmd 12345 VM.flags -all
jcmd 12345 VM.set_flag HeapDumpOnOutOfMemoryError true
jcmd 12345 VM.set_flag HeapDumpOnOutOfMemoryError false
~~~

Stop the example with `Ctrl+C` in the first terminal. You do not need to trigger a real OutOfMemoryError to test reading/enabling/disabling the flag.

## 6. When the JVM has already crashed: use jhsdb jinfo

Distinguish between the two cases:

- `jinfo <pid>` reads configuration from a running JVM.
- `jhsdb jinfo` uses the Serviceability Agent to read information from a core dump after a crash.

Example on Linux:

~~~bash
jhsdb jinfo \
  --exe /opt/jdk-21/bin/java \
  --core /var/crash/core.19256
~~~

The executable path must match the binary that produced the core dump. If the process was created via the JNI Invocation API, the binary name might not be `java`; you must provide the exact original executable.

Reading a core dump is a postmortem operation. It does not change flags on a running JVM and does not replace dedicated core analysis tools. Core dumps can contain sensitive memory data, so read permissions and retention periods must be restricted.

## 7. Limitations and prerequisites to know

### 7.1. jinfo is experimental and unsupported

Oracle JDK 21 documentation explicitly notes that `jinfo` is experimental and unsupported. It may change or be removed in future JDK releases.

Therefore:

- Do not build new production systems that depend on `jinfo`'s output format.
- Do not assume commands and flags are identical across all vendors/JDKs.
- Prefer `jcmd` in new runbooks.
- If you must keep legacy scripts, pin the JDK/toolchain, test when upgrading versions, and have a migration plan.

### 7.2. Choosing the right process and attach permissions

`jinfo` requires the PID of the Java process. You can find processes with:

~~~bash
jcmd -l
jps -l
ps -ef | grep '[j]ava'
~~~

On Windows PowerShell:

~~~powershell
Get-Process java
where.exe jinfo
~~~

For a running process, attach locally on the same machine and under an identity with appropriate permissions. OS, user, container, and Attach API requirements can affect the outcome.

If the PID has terminated or been reused, the command may fail or target the wrong process. Verify the PID, main class, and start time before reading or changing flags.

### 7.3. Windows requirements

Oracle JDK 21 notes that if `dbgeng.dll` is not present in the Windows environment, you may need to install Debugging Tools for Windows for these tools to work. The `PATH` environment variable must contain the location of `jvm.dll` used by the target process or the location where the core dump was generated.

When `jinfo` works on Linux but fails on Windows, check the JDK, architecture, debug libraries, and `PATH` before concluding that the JVM is at fault.

### 7.4. Output may expose sensitive information

System properties and VM flags can reveal:

- Installation paths, working directories, and classpaths.
- Endpoints, profiles, regions, and environment names.
- `-D...` arguments passed by the application.
- Configuration details that could help someone infer your infrastructure layout.

Do not post full output into public tickets or unrestricted build logs. Extract only what is necessary and redact sensitive values.

## 8. Common errors and how to handle them

| Symptom | Possible cause | Resolution |
|---|---|---|
| `jinfo` is not recognized | JDK `bin` is not in `PATH`, or only JRE/runtime is installed | Use the `JAVA_HOME/bin/jinfo` path or an appropriate JDK |
| `Unable to open socket file` / attach failed | Wrong PID, process already terminated, or insufficient attach permissions | Verify the PID and the identity running the tool |
| `flag 'MaxHeapSize' cannot be changed` | Flag cannot be changed at runtime | Reconfigure startup arguments and restart according to plan |
| Expected property not found | Wrong property name, property not provided to the JVM, or wrong process | Verify the PID and use `-sysprops` |
| Output has too many lines | Using `jinfo <pid>` without options | Switch to `-flags`, `-sysprops`, or `-flag <name>` |
| Tool incompatible with target JVM | Using a JDK tool from a different release/vendor | Use the tool matching the target process's JDK |
| Windows reports missing `dbgeng.dll` | Missing Debugging Tools for Windows | Install the appropriate debug components and check `PATH` |
| Flag changed but lost after restart | Change only applies to the current JVM | Update startup arguments/deployment config to persist it |

## 9. Tool selection workflow

You can decide based on your needs:

~~~text
Need to read JVM flags or system properties?
                 |
                 v
           Use jcmd first
                 |
                 v
Is there a legacy runbook requiring jinfo
or need for legacy tool compatibility?
          /              \
        Yes               No
        |                  |
        v                  v
Use jinfo with controls   Continue with jcmd
        |
        v
Need to change a flag at runtime?
        |
        v
Verify flag is manageable,
assess impact and rollback
~~~

If the issue involves threads, heap, class loading, GC, or profiling, choose a specialized `jcmd` diagnostic command or JDK Mission Control/Flight Recorder. `jinfo` only provides configuration information and modifies certain flags; it is not a profiler or a heap analysis tool.

## 10. Checklist before running jinfo

- [ ] Identify the exact PID and main class of the JVM.
- [ ] Check which JDK `jinfo` belongs to and which JDK the target JVM uses.
- [ ] Prefer `jcmd` if writing a new runbook or automation.
- [ ] Only use `-sysprops` or the optionless command when you genuinely need the full output.
- [ ] Redact or protect system properties and VM flags containing sensitive information.
- [ ] Before changing a flag, confirm that it is dynamically manageable.
- [ ] Assess the flag's impact and prepare a rollback.
- [ ] Do not expect runtime changes to persist after a JVM restart.
- [ ] If analyzing a core dump, use `jhsdb jinfo` with the exact executable and core file.
- [ ] Re-verify after JDK upgrades since `jinfo` is an unsupported tool.

## 11. Key takeaways

Use `jinfo` when you need to quickly read VM flags/system properties of an older JVM, support a legacy runbook, or temporarily change a manageable VM flag during a controlled troubleshooting session. Do not use it to change arbitrary JVM options; startup-only flags like `MaxHeapSize` cannot be modified while the process is running.

For new projects, prefer `jcmd`: `VM.flags`, `VM.system_properties`, and `VM.set_flag` cover common configuration tasks, while `jcmd` also supports many other diagnostics. When analyzing a core dump, use `jhsdb jinfo` instead of the `jinfo` command meant for running processes.

References:

- [The jinfo Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jinfo.html)
- [Diagnostic Tools — Java SE 21: jinfo and jcmd](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html)
- [The jcmd Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Java HotSpot VM Command-Line Options — Serviceability and heap dump options](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)