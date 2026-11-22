# Inspecting JVM Configuration with `jinfo`

`jinfo` is a JDK tool used to read the configuration of a running Java Virtual Machine (JVM). It displays two main groups of information: JVM flags and Java system properties. With it, operators can inspect heap size, garbage collector, `-XX` options, `-D` properties, and other runtime details without restarting the application.

Basic commands:

~~~text
jinfo -flags <PID>
jinfo -flag MaxHeapSize <PID>
jinfo -sysprops <PID>
~~~

`jinfo` also provides syntax to modify certain JVM flags while a process is running. Only flags that support runtime changes can be updated; startup-only or non-manageable flags will be rejected. Runtime changes can directly affect the application, so check flag metadata and operational policies before using them.

One important note: the Oracle JDK 24 documentation marks `jinfo` as experimental and unsupported, and recommends using `jcmd` for modern diagnostics. This article explains how to read `jinfo` output to understand existing systems and how to transition to the equivalent `jcmd` commands where appropriate.

The toolchain used to verify this article is Zulu/OpenJDK 24.0.2. Syntax and flags depend on the JVM, vendor, and JDK version. Check `jinfo -h` and `jcmd <PID> help` in your actual environment.

## 1. What types of configuration does `jinfo` display?

Configuration information can be divided into three groups:

| Group | Examples | Source |
|---|---|---|
| JVM flags | `-Xms`, `-Xmx`, `-XX:+UseG1GC` | Startup options and VM-selected flags |
| Java system properties | `java.version`, `user.timezone`, `app.profile` | `-Dname=value` or `System.setProperty()` |
| Environment variables | `JAVA_HOME`, `PATH`, `APP_ENV` | Process environment provided by the OS |

`jinfo` focuses on JVM flags and Java system properties. It is not a tool for listing all OS environment variables.

A system property can be set at startup:

~~~text
java -Dapp.profile=staging -Dapp.region=ap-southeast com.example.ConfigProbe
~~~

The application can read it with:

~~~java
String profile = System.getProperty("app.profile");
~~~

Meanwhile, environment variables are read with `System.getenv("APP_ENV")`. These two mechanisms are different and should not be confused when investigating configuration.

## 2. Syntax and selecting the right process

Syntax according to JDK 24.0.2 help:

~~~text
jinfo <option> <pid>
~~~

The `<pid>` argument is the process ID of the JVM to inspect. Start by listing Java processes:

~~~text
jps -l
~~~

Illustrative example output:

~~~text
18240 com.example.OrderService
29116 com.example.ReportWorker
~~~

PIDs vary by machine and across restarts. Always obtain a fresh PID from the actual environment; do not reuse PIDs from documentation or old logs because the OS can recycle PIDs.

You can use OS tools if `jps` does not see the process:

Windows PowerShell:

~~~powershell
Get-CimInstance Win32_Process |
    Where-Object { $_.Name -match '^java(w)?\.exe$' } |
    Select-Object ProcessId, Name, CommandLine
~~~

macOS/Linux:

~~~sh
ps -ef | grep '[j]ava'
~~~

After identifying the right PID, inspect the configuration:

~~~text
jinfo -flags 18240
~~~

Do not select a process based solely on the PID. Cross-check the application name, command line, process owner, and deployment environment before reading or changing configuration.

## 3. Configuration reading options

According to `jinfo -h` on JDK 24.0.2, the main forms are:

| Command | Result |
|---|---|
| `jinfo <PID>` | Prints both JVM flags and Java system properties |
| `jinfo -flags <PID>` | Prints JVM flags |
| `jinfo -flag <name> <PID>` | Prints the value of a single flag |
| `jinfo -sysprops <PID>` | Prints Java system properties |
| `jinfo -h` | Displays help |

### 3.1. Viewing all JVM flags

~~~text
jinfo -flags 18240
~~~

The output usually starts with `VM Flags:` followed by flags in the form:

~~~text
VM Flags:
-XX:InitialHeapSize=67108864
-XX:MaxHeapSize=268435456
-XX:+UseG1GC
-XX:+UseCompressedOops
~~~

This is an illustrative example. Actual flags, ordering, and values depend on the JVM, hardware, collector, and startup options.

Key points to understand:

- `-XX:+FlagName`: Boolean flag that is enabled.
- `-XX:-FlagName`: Boolean flag that is disabled.
- `-XX:FlagName=value`: flag with a specific value.
- Heap values are typically displayed in bytes in the output of some commands.
- Some values are chosen automatically by the JVM through ergonomics and may not appear verbatim on the original command line.

`jinfo -flags` is useful for viewing flag states. If you need the exact original startup arguments, use `jcmd <PID> VM.command_line`.

### 3.2. Viewing a specific flag

~~~text
jinfo -flag MaxHeapSize 18240
jinfo -flag InitialHeapSize 18240
jinfo -flag UseG1GC 18240
~~~

Example output:

~~~text
-XX:MaxHeapSize=268435456
-XX:InitialHeapSize=67108864
-XX:+UseG1GC
~~~

Checking a single flag is easier to read when investigating a specific setting, for example:

- `MaxHeapSize`: maximum heap limit.
- `InitialHeapSize`: initial heap size.
- `UseG1GC`: whether the G1 collector is enabled.
- `MaxMetaspaceSize`: Metaspace limit if configured.
- `ActiveProcessorCount`: number of CPUs the JVM uses for certain runtime decisions.

Flag names must be verified against the exact JDK in use. Not every flag exists in every version.

### 3.3. Viewing Java system properties

~~~text
jinfo -sysprops 18240
~~~

Illustrative output:

~~~text
java.version=24.0.2
java.specification.version=24
file.encoding=UTF-8
user.timezone=Asia/Ho_Chi_Minh
app.profile=staging
app.region=ap-southeast
~~~

You can filter for the properties you need to avoid reading hundreds of lines:

PowerShell:

~~~powershell
jinfo -sysprops 18240 |
    Select-String 'java.version=|app.profile=|app.region='
~~~

macOS/Linux:

~~~sh
jinfo -sysprops 18240 |
    grep -E '^(java.version|app.profile|app.region)='
~~~

If a property contains special characters, `=`, newlines, or sensitive data, save and filter the output in a way that suits the actual format. Do not assume every property is a public configuration string.

## 4. Distinguishing JVM flags from the original command line

`jinfo -flags` shows the VM's flag state. It is not an exact copy of the `java` command that was executed.

For example, if a process was started with:

~~~text
java -Xms64m -Xmx256m -XX:+UseG1GC -Dapp.profile=staging -Dapp.region=ap-southeast -cp . com.example.ConfigProbe
~~~

You can inspect each part separately:

~~~text
jinfo -flags <PID>
jinfo -sysprops <PID>
jcmd <PID> VM.command_line
~~~

- `jinfo -flags`: the VM flags currently in effect.
- `jinfo -sysprops`: the current system properties.
- `VM.command_line`: the command line the JVM received at startup, including JVM arguments, main class, and classpath.

Some flags are selected automatically by the JVM based on the environment. Therefore, `MaxHeapSize` may appear in `jinfo -flags` even if the operator did not pass `-Xmx` with that exact value.

When comparing configuration between two machines, record the JDK version, command line, JVM flags, system properties, container memory limit, and CPU limit. Comparing only a single flag can lead to wrong conclusions if the two environments have different resource limits.

## 5. Reading heap values and common flags

Flags commonly checked during memory investigations:

| Flag | Meaning |
|---|---|
| `InitialHeapSize` | Initial heap used by the JVM |
| `MaxHeapSize` | Maximum heap limit |
| `MinHeapSize` | Minimum heap size according to the VM |
| `MaxMetaspaceSize` | Metaspace limit if configured |
| `UseG1GC` | Whether the G1 garbage collector is enabled |
| `UseParallelGC` | Whether the Parallel collector is enabled |
| `UseSerialGC` | Whether the Serial collector is enabled |
| `HeapDumpOnOutOfMemoryError` | Whether to generate a heap dump on OutOfMemoryError |
| `ActiveProcessorCount` | Number of processors the JVM uses for certain runtime decisions |

Examples:

~~~text
jinfo -flag InitialHeapSize <PID>
jinfo -flag MaxHeapSize <PID>
jinfo -flag MaxMetaspaceSize <PID>
jinfo -flag UseG1GC <PID>
jinfo -flag HeapDumpOnOutOfMemoryError <PID>
~~~

If `MaxMetaspaceSize` or another flag is not explicitly set, the JVM may use a default or ergonomic value. Do not conclude that a missing flag means a value of `0`.

`-XX` options are specific to the HotSpot VM, not part of the Java SE API. Flag names, defaults, and mutability may differ across JDK releases or JVM vendors.

## 6. Distinguishing system properties, environment variables, and application config

These configuration sources should be inspected with the appropriate tools:

| Source | How it is set | How it is read |
|---|---|---|
| JVM flags | `-Xmx256m`, `-XX:+UseG1GC` | `jinfo -flags`, `jcmd VM.flags` |
| Java system properties | `-Dapp.profile=staging` | `jinfo -sysprops`, `jcmd VM.system_properties` |
| Environment variables | `APP_ENV=staging` | `System.getenv`, OS process tools |
| Application config | YAML, properties, JSON, database | Application's configuration mechanism |

Example:

~~~java
String profile = System.getProperty("app.profile");
String environment = System.getenv("APP_ENV");

System.out.println("profile=" + profile);
System.out.println("environment=" + environment);
~~~

`jinfo -sysprops` will show `app.profile` if the property exists. It does not list the `APP_ENV` variable.

An application can also modify system properties after startup using `System.setProperty()`. Therefore, the value in `jinfo -sysprops` reflects the current state of the process, not necessarily the literal `-D` argument at startup. Use `VM.command_line` to view the original arguments.

## 7. Changing JVM flags at runtime

In addition to read mode, `jinfo` provides syntax for modifying flags:

~~~text
jinfo -flag +<BooleanFlag> <PID>
jinfo -flag -<BooleanFlag> <PID>
jinfo -flag <FlagName>=<value> <PID>
~~~

Syntax examples:

~~~text
jinfo -flag +HeapDumpOnOutOfMemoryError <PID>
jinfo -flag -HeapDumpOnOutOfMemoryError <PID>
jinfo -flag MaxHeapSize=268435456 <PID>
~~~

The commands above illustrate the syntax, not a recommendation to change those flags in production. `MaxHeapSize` typically cannot be changed after the JVM has initialized; the command will be rejected if the flag does not support runtime updates.

### 7.1. Checking whether a flag can be changed

Use `jcmd` to inspect flag metadata:

~~~text
jcmd <PID> VM.flags -all
~~~

The output may mark some flags with `{manageable}`. These are the flags that can be managed while the JVM is running according to the VM's mechanism.

Illustrative example:

~~~text
bool HeapDumpOnOutOfMemoryError = false {manageable} {default}
bool ShowCodeDetailsInExceptionMessages = true {manageable} {default}
size_t MaxHeapSize = 268435456 {default}
~~~

Only perform runtime updates when the flag is changeable and you understand the impact. Some flags are read-only; some only apply during startup; and some cannot be changed because the VM has already initialized the associated structures.

### 7.2. Runtime updates are not the same as a restart

Changing a flag with `jinfo` or `jcmd VM.set_flag` only affects the current process. It does not automatically modify service files, Docker images, Kubernetes manifests, startup scripts, or deployment configurations.

When the JVM restarts, the new startup configuration determines the initial values. For a permanent change, update the managed configuration source in your build/deploy pipeline and verify again after restart.

Do not use runtime updates to mask misconfigurations in deployment. Record who made the change, when, the old flag, the new flag, the reason, and the rollback steps.

## 8. Using `jcmd` instead of `jinfo`

Oracle recommends using `jcmd` instead of legacy tools like `jinfo` in modern diagnostic workflows.

Common equivalent commands:

| Goal | `jinfo` | `jcmd` |
|---|---|---|
| View VM flags | `jinfo -flags <PID>` | `jcmd <PID> VM.flags` |
| View all flags and metadata | No direct equivalent | `jcmd <PID> VM.flags -all` |
| View a single flag | `jinfo -flag <name> <PID>` | `jcmd <PID> VM.flags -all` then filter |
| View system properties | `jinfo -sysprops <PID>` | `jcmd <PID> VM.system_properties` |
| View command line | Not dedicated | `jcmd <PID> VM.command_line` |
| View JVM version | `jinfo` is not suitable | `jcmd <PID> VM.version` |
| Change a manageable flag | `jinfo -flag <name>=<value> <PID>` | `jcmd <PID> VM.set_flag <name> <value>` |

Examples:

~~~text
jcmd 18240 VM.flags
jcmd 18240 VM.flags -all
jcmd 18240 VM.system_properties
jcmd 18240 VM.command_line
jcmd 18240 VM.version
~~~

To search for a flag in the list:

PowerShell:

~~~powershell
jcmd 18240 VM.flags -all |
    Select-String 'MaxHeapSize|UseG1GC|HeapDumpOnOutOfMemoryError'
~~~

macOS/Linux:

~~~sh
jcmd 18240 VM.flags -all |
    grep -E 'MaxHeapSize|UseG1GC|HeapDumpOnOutOfMemoryError'
~~~

`jcmd` provides additional diagnostic commands such as `VM.info`, `VM.uptime`, `VM.classloader_stats`, `GC.heap_info`, `Thread.print`, and `JFR.*`. Run `jcmd <PID> help` to see what commands a specific JVM supports.

## 9. Permissions and attaching to the JVM

`jinfo` needs to connect to a running JVM. If it fails to attach, check:

- Is the PID correct and does the process still exist?
- Is the tool running on the same machine as the target JVM?
- Does the user running the tool have permission to access the process?
- Is the JVM running under a different user or group?
- Has the attach mechanism been disabled with `-XX:+DisableAttachMechanism`?
- Is the process inside a container or a different PID namespace?
- Is the tool's JDK compatible with the target runtime?

With `jcmd`, Oracle requires running on the same machine with the same effective user/group identifiers as the launched JVM. With `jinfo`, appropriate OS permissions are also required to attach to the process.

In containers, the PID on the host may differ from the PID inside the container. `jps` on the host may also fail to list JVMs in separate containers. In that case, run the tool from the target container or use the container runtime to identify the process in its corresponding namespace.

Do not disable security protections or escalate privileges arbitrarily just to make attach succeed. If the environment does not allow attach, use platform-provided diagnostics such as GC logs, JFR, authenticated JMX, or application logs.

## 10. Protecting configuration information

The output of `jinfo -sysprops` can contain sensitive data. For example:

- Tokens, passwords, or API keys mistakenly passed via `-D`.
- JDBC URLs containing a username/password.
- Internal paths, account names, or home directories.
- Endpoint details, profiles, or tenant configurations.
- `java.class.path` containing module names or internal deployment paths.

`jinfo -flags` can also reveal heap sizing, GC configuration, dump paths, or security options.

When saving output:

1. Collect only the properties and flags needed for the investigation.
2. Redact credentials before sharing.
3. Restrict read permissions on report files.
4. Do not paste full output into tickets or public chats.
5. Delete temporary reports according to retention policies.
6. If an exposed secret is discovered, follow rotation/incident response procedures.

Do not pass real passwords via `-D` when a secret manager or dedicated credential mechanism can be used. System properties are not a secure secret store.

## 11. Java 17+ example: inspecting a running JVM's configuration

Create `ConfigProbe.java`:

~~~java
public final class ConfigProbe {
    private ConfigProbe() {
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("app.profile=" + System.getProperty("app.profile"));
        System.out.println("app.region=" + System.getProperty("app.region"));

        Thread.sleep(300_000);
    }
}
~~~

The program prints two properties and then waits five minutes to give the operator time to inspect the process.

Compile:

~~~text
javac --release 17 ConfigProbe.java
~~~

Run:

~~~text
java -Xms64m -Xmx256m -XX:+UseG1GC -Dapp.profile=staging -Dapp.region=ap-southeast ConfigProbe
~~~

Stdout:

~~~text
app.profile=staging
app.region=ap-southeast
~~~

Open a second terminal and find the process:

~~~text
jps -l
~~~

Get the PID of `ConfigProbe`, then run:

~~~text
jinfo -flags <PID>
jinfo -flag MaxHeapSize <PID>
jinfo -flag UseG1GC <PID>
jinfo -sysprops <PID>
~~~

Expected results:

- `MaxHeapSize` corresponds to the `-Xmx256m` setting.
- `UseG1GC` is enabled.
- `app.profile=staging`.
- `app.region=ap-southeast`.

Check the original command line:

~~~text
jcmd <PID> VM.command_line
~~~

The output will include the `-Xms64m`, `-Xmx256m`, and `-XX:+UseG1GC` arguments, the two `-D` properties, and the main class name `ConfigProbe`.

When finished, stop the program with `Ctrl+C`. The PID and other flags may vary at runtime; the two stdout lines for the application properties are fixed for the sample launch command.

## 12. Inspecting core dumps with `jhsdb jinfo`

If a JVM has crashed and produced a core dump, standard `jinfo` is not the command for processing core files under current syntax. Use the Serviceability Agent instead:

~~~text
jhsdb jinfo --exe <path-to-java> --core <core-file>
~~~

Example on Linux:

~~~text
jhsdb jinfo --exe /usr/lib/jvm/jdk-24/bin/java --core core.19256
~~~

The Java executable path must match the binary that generated the core dump. For JVMs created via the JNI Invocation API, the original binary may not be named `java`.

Postmortem attach requires proper permissions and matching symbol/debug information. The Serviceability Agent can pause the process or have significant impact if used in live-attach mode on a running process; check `jhsdb jinfo --help` and your environment's crash dump analysis procedures.

## 13. Troubleshooting

### `AttachNotSupportedException`

**Cause:** The JVM does not allow attach, wrong user, wrong namespace, or the process no longer exists.

**Resolution:** Verify the PID, host, user/group, and `-XX:+DisableAttachMechanism`. If running in a container, execute from the correct namespace.

### `Not enough permissions`

**Cause:** The current account lacks permission to access the process or the temporary directory used for attach.

**Resolution:** Run with the appropriate operational account, and check OS permissions and temporary directory configuration. Do not escalate privileges globally when only limited attach permissions are needed.

### `Could not find ... JVM`

**Cause:** Wrong PID, the process has terminated, or the target is not a compatible JVM.

**Resolution:** Re-run `jps -l` or use a process manager to confirm the PID and executable.

### `Unknown VM flag`

**Cause:** The flag does not exist in the target JDK/runtime or has been renamed/removed.

**Resolution:** Check `jcmd <PID> VM.flags -all`, the JDK version, and the documentation for that exact version.

### Unable to change a flag

**Cause:** The flag is not manageable or is only read after startup.

**Resolution:** Check metadata with `jcmd <PID> VM.flags -all`; if `{manageable}` is absent, do not assume it can be changed at runtime. Update the startup config and restart following your operational process if needed.

### Property missing from `jinfo -sysprops`

**Cause:** The application reads an environment variable or config file instead of a Java system property, the property is set after the check, or the key name is wrong.

**Resolution:** Check `System.getenv`, application config, the command line, and code calling `System.setProperty()`.

### `jinfo -flags` values differ from the startup script

**Cause:** The JVM chose ergonomic values, a wrapper added options, the environment injected `JAVA_TOOL_OPTIONS`/`JDK_JAVA_OPTIONS`, or the flag was changed at runtime.

**Resolution:** Compare `VM.command_line`, `VM.flags -all`, the process environment, and the deployment configuration. Record both the JDK version and container resource limits.

### JVM not visible in `jps`

**Cause:** The JVM is in another container, under another user, using a custom launcher, or in a different PID namespace.

**Resolution:** Obtain the PID using an OS process manager or container runtime and run diagnostics in the appropriate environment.

### Output contains credentials

**Cause:** Secrets were placed in system properties or command-line arguments.

**Resolution:** Stop sharing unredacted reports, rotate exposed secrets, and switch to proper secret management.

## 14. Operational workflow for inspecting JVM configuration

A short workflow can be carried out as follows:

1. Identify the exact host, container, service, and PID.
2. Record the JDK vendor/version using `jcmd <PID> VM.version`.
3. Read JVM flags with `jcmd <PID> VM.flags` or `jinfo -flags`.
4. Check key flags with `jinfo -flag <name> <PID>` or by filtering `VM.flags -all`.
5. Read the necessary system properties; redact sensitive data.
6. Cross-check `VM.command_line` against startup scripts/deployment manifests.
7. Check container CPU/memory limits and environment variables if ergonomic values differ from expectations.
8. Only change runtime flags after confirming they are manageable and assessing the impact.
9. Update the deployment configuration source if the change needs to persist across restarts.
10. Store the redacted report with timestamp, PID, JDK version, and owner.

## 15. Checklist before drawing conclusions about JVM configuration

- [ ] Confirmed the exact process and current PID.
- [ ] Recorded the JDK vendor/version.
- [ ] Inspected `jinfo -flags` or `jcmd VM.flags`.
- [ ] Checked heap size, collector, and related flags individually.
- [ ] Inspected the necessary system properties.
- [ ] Distinguished system properties from environment variables.
- [ ] Checked the original command line with `VM.command_line`.
- [ ] Checked `{manageable}` metadata before proposing flag changes.
- [ ] Understood that runtime updates do not automatically update startup/deploy configs.
- [ ] Verified user, attach permissions, and container/PID namespace.
- [ ] Redacted tokens, passwords, URL credentials, and internal details.
- [ ] Saved the report with timestamp and JDK version if needed for auditing.
- [ ] Used `jcmd` instead of `jinfo` for new diagnostic workflows where appropriate.

## 16. References

- Oracle JDK 24 — The `jinfo` Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jinfo.html
- Oracle JDK 24 — Diagnostic Tools, `jinfo` and `jcmd` sections: https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html
- Oracle JDK 24 — Java HotSpot VM Command-Line Options: https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html

`jinfo` provides a quick way to inspect JVM flags and system properties of a running process, and supports changing certain manageable flags at runtime. To draw accurate configuration conclusions, cross-check the current state against the command line, flag metadata, environment, and deployment configuration. Because `jinfo` is an experimental/unsupported tool, prefer `jcmd` for new diagnostic workflows.