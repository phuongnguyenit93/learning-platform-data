# The jinfo Command in the JDK

## 1. What is jinfo?

**jinfo** is a command-line tool bundled with the JDK used to read configuration information of a running Java Virtual Machine (JVM). The tool can display JVM flags and Java system properties; for certain flags that the JVM allows to be changed dynamically, jinfo can also enable, disable, or set their values while the process is still running.

jinfo is useful when you need to answer questions such as:

- What heap size and garbage collector is the JVM running with?
- Which JVM options was the application launched with?
- Which system properties are currently in effect?
- Is a Boolean VM flag currently enabled or disabled?
- Can a specific flag be changed without restarting the process?

General syntax:

~~~text
jinfo <option> <pid>
~~~

Where PID is the process ID of the JVM to inspect. jinfo operates on a specific JVM process; the tool does not list all Java processes on its own. You can find the PID using jcmd -l, jps -l, or your operating system's process tools.

## 2. Where jinfo Fits in the JDK Tooling

jinfo is a JVM diagnostic tool in the command-line toolset. It focuses on the flags and system properties of a single process.

Related tools have different purposes:

| Tool | Purpose |
|---|---|
| jps | Lists JVM processes observable by the current account. |
| jcmd | Sends diagnostic commands to the JVM, inspects flags/properties, and performs a wide range of diagnostic operations. |
| jinfo | Reads flags and system properties; modifies certain supported VM flags. |
| jhsdb | Analyzes a JVM process or crash dump at a lower level; especially useful for postmortem analysis. |

Oracle classifies jinfo as an **experimental and unsupported** tool. It may change or be removed in future JDK releases. The JDK 24 documentation recommends using jcmd instead of jinfo for new diagnostic needs because jcmd provides a richer set of diagnostic commands with lower overhead.

This does not diminish the value of learning jinfo: understanding its syntax helps you read older runbooks, inspect systems that still use it, and migrate to the corresponding jcmd commands.

## 3. Checking jinfo Availability

jinfo is installed in the JDK's bin directory. Check the usage instructions:

~~~bash
jinfo -h
~~~

You can use the following help forms:

~~~bash
jinfo -help
jinfo --help
~~~

On Windows PowerShell:

~~~powershell
where jinfo
& "$env:JAVA_HOME\bin\jinfo.exe" -h
~~~

On Linux/macOS:

~~~bash
which jinfo
"$JAVA_HOME/bin/jinfo" -h
~~~

If the shell cannot find the command, check PATH and JAVA_HOME. A minimal runtime image created with jlink might not include jinfo. In that case, use a JDK with diagnostic tools matching the target JVM's environment.

Do not use jinfo -version to check the version: the tool's help syntax does not provide this option. You can use java --version to identify the current JDK and jinfo -h to confirm the supported jinfo options.

## 4. Finding the PID Before Running jinfo

jinfo requires the PID of an active Java process. Some ways to find the PID:

List JVMs using jcmd:

~~~bash
jcmd -l
~~~

List JVMs using jps:

~~~bash
jps -l
~~~

On Linux:

~~~bash
ps -eo pid,user,args | grep '[j]ava'
~~~

On Windows PowerShell:

~~~powershell
Get-CimInstance Win32_Process |
    Where-Object { $_.Name -match 'java' } |
    Select-Object ProcessId, Name, CommandLine
~~~

After finding the PID, verify it belongs to the right application before reading or modifying configuration. PIDs can be reused after a process exits; do not reuse an old PID from logs or documentation without verifying it.

The command examples in this guide use 12345 as an illustrative PID. Replace it with the actual PID you just confirmed.

## 5. Printing All Flags and System Properties

If no option is passed, jinfo prints both JVM flags and Java system properties:

~~~bash
jinfo 12345
~~~

The output is divided into sections, typically with headers like:

~~~text
Java System Properties:
java.version=24.0.2
java.vendor=...
java.class.path=...
user.dir=...
...
VM Flags:
-XX:InitialHeapSize=...
-XX:MaxHeapSize=...
-XX:+UseG1GC
...
~~~

This is the combined mode, convenient when you need a quick snapshot of the JVM configuration. However, the output can be long and may contain sensitive data. When you only need a specific group of information, choose a specific option to reduce the amount of data printed.

## 6. Printing JVM Flags with -flags

Run:

~~~bash
jinfo -flags 12345
~~~

This option prints the VM flags of the target process. Flags can reveal the heap configuration, garbage collector, code cache, and other runtime choices.

Illustrative output example:

~~~text
VM Flags:
-XX:InitialHeapSize=33554432
-XX:MaxHeapSize=31675383808
-XX:+UseCompressedOops
-XX:+UseG1GC
~~~

Actual values depend on the JDK, architecture, RAM, container limits, and startup options. Do not assume a default heap value will be the same across all machines.

Some flag formats:

- -XX:+FlagName: Boolean flag that is enabled.
- -XX:-FlagName: Boolean flag that is disabled.
- -XX:FlagName=Value: flag with a numeric or string value.

jinfo -flags lets you observe the configuration currently in effect; it is not an exhaustive list of every flag the JVM can support. If you need flag details, data types, or mutability, consult the corresponding JVM documentation and jcmd diagnostic commands.

## 7. Printing Java System Properties with -sysprops

Run:

~~~bash
jinfo -sysprops 12345
~~~

This option prints Java system properties as name-value pairs.

Some common properties:

| Property | Meaning |
|---|---|
| java.version | Java runtime version. |
| java.vendor | JDK vendor. |
| java.home | Runtime installation directory. |
| java.class.path | Application classpath. |
| java.library.path | Search path for native libraries. |
| user.dir | Working directory of the process. |
| user.home | Home directory of the account running the JVM. |
| os.name | Operating system name. |
| file.encoding | Default charset used by the runtime as configured. |

Applications can set custom properties using the -D option at startup:

~~~bash
java -Dapp.environment=staging -Dapp.region=ap-southeast-1 com.example.Main
~~~

Once the JVM is running, you can inspect them:

~~~bash
jinfo -sysprops 12345
~~~

The output will include lines corresponding to app.environment and app.region if they remain among the process's system properties.

System properties are runtime configuration. They are not the same as operating system environment variables. You cannot infer the entire process environment from jinfo -sysprops alone.

## 8. Reading a Single VM Flag with -flag name

If you only need to check a single flag, run:

~~~bash
jinfo -flag UseG1GC 12345
~~~

Example output:

~~~text
-XX:+UseG1GC
~~~

Another example:

~~~bash
jinfo -flag HeapDumpOnOutOfMemoryError 12345
~~~

The result can be:

~~~text
-XX:-HeapDumpOnOutOfMemoryError
~~~

or:

~~~text
-XX:+HeapDumpOnOutOfMemoryError
~~~

The plus sign indicates that the Boolean flag is enabled; the minus sign indicates that the flag is disabled.

Querying a single flag is suitable when you need to quickly test a hypothesis without reading the entire list. The flag name must be spelled exactly as supported by the HotSpot VM.

## 9. Enabling or Disabling a Boolean Flag at Runtime

jinfo can enable or disable certain Boolean VM flags using the syntax:

~~~text
jinfo -flag +<flag-name> <pid>
jinfo -flag -<flag-name> <pid>
~~~

Example enabling heap dump creation on OutOfMemoryError:

~~~bash
jinfo -flag +HeapDumpOnOutOfMemoryError 12345
~~~

Verify again:

~~~bash
jinfo -flag HeapDumpOnOutOfMemoryError 12345
~~~

If the flag is enabled, the output is:

~~~text
-XX:+HeapDumpOnOutOfMemoryError
~~~

Disable the flag:

~~~bash
jinfo -flag -HeapDumpOnOutOfMemoryError 12345
~~~

Then verify again with the query command.

This change affects the running JVM process. If the application restarts, the startup configuration is applied again; runtime changes are not automatically written to deployment configuration files.

**Only certain flags can be changed dynamically.** A flag must be marked appropriately by HotSpot for runtime modification, typically described as manageable. For flags that do not support runtime updates, jinfo may report an error even when the command syntax is valid.

Do not enable a flag in production just because the command is accepted. For example, HeapDumpOnOutOfMemoryError can write a heap dump to disk when an OutOfMemoryError occurs; you must ensure the target directory, storage capacity, and access permissions are appropriate.

## 10. Setting a Flag Value with name=value

For flags that take a value, the syntax is:

~~~text
jinfo -flag <flag-name>=<value> <pid>
~~~

General syntax example:

~~~bash
jinfo -flag MaxHeapFreeRatio=75 12345
~~~

The command only succeeds when that flag supports dynamic modification and the value is valid. Not every flag can be updated at runtime; options related to initial heap size, VM structure, or already-initialized subsystems may require a restart.

Safe procedure:

1. Read the current value using jinfo -flag.
2. Check the flag's documentation and confirm whether it can be changed dynamically.
3. Assess the impact on application performance and behavior.
4. Apply the change on a test process first.
5. Read the flag again to confirm the value.
6. Record the change in the operations log.
7. Add the desired configuration to startup parameters or managed configuration so subsequent restarts preserve the same policy.

The MaxHeapFreeRatio example above illustrates the name=value syntax; do not assume every JDK or JVM allows changing this flag at runtime.

## 11. Complete Example: Inspecting JVM Configuration

Create the file **JinfoProbe.java**:

~~~java
public class JinfoProbe {
    public static void main(String[] args) throws InterruptedException {
        System.out.println(
                "JinfoProbe ready; pid=" + ProcessHandle.current().pid());

        Thread.sleep(120_000);
    }
}
~~~

Compile with JDK 17 or later:

~~~bash
javac --release 17 -encoding UTF-8 JinfoProbe.java
~~~

Run with a JVM flag and a system property:

~~~bash
java -Xms32m -Dprobe.mode=jinfo-check JinfoProbe
~~~

Example stdout:

~~~text
JinfoProbe ready; pid=12345
~~~

The PID is dynamic. Open a second terminal and use the PID that was just printed.

Print flags:

~~~bash
jinfo -flags 12345
~~~

Check the system property:

~~~bash
jinfo -sysprops 12345
~~~

In the system properties output, look for:

~~~text
probe.mode=jinfo-check
~~~

Check a single flag:

~~~bash
jinfo -flag UseG1GC 12345
~~~

Enable a dynamically changeable Boolean flag:

~~~bash
jinfo -flag +HeapDumpOnOutOfMemoryError 12345
jinfo -flag HeapDumpOnOutOfMemoryError 12345
~~~

On JDK 24.0.2, testing against a Java 17 process confirmed:

- jinfo -flags exited with code 0 and returned the VM flags.
- jinfo -sysprops exited with code 0 and included the property probe.mode=jinfo-check.
- jinfo -flag UseG1GC printed -XX:+UseG1GC.
- The command enabling HeapDumpOnOutOfMemoryError exited with code 0; the subsequent query printed -XX:+HeapDumpOnOutOfMemoryError.

Stop the sample program with Ctrl+C once inspection is complete.

## 12. Using jcmd Instead of jinfo

Oracle recommends using jcmd for new JVM diagnostics. Common equivalent commands:

| Need | jinfo | jcmd |
|---|---|---|
| Print VM flags | jinfo -flags PID | jcmd PID VM.flags |
| Print all VM-supported flags | No simple equivalent in jinfo | jcmd PID VM.flags -all |
| Print system properties | jinfo -sysprops PID | jcmd PID VM.system_properties |
| View JVM version | Not its primary purpose | jcmd PID VM.version |
| Set a VM flag | jinfo -flag name=value PID | jcmd PID VM.set_flag name value |

Examples:

~~~bash
jcmd 12345 VM.flags
jcmd 12345 VM.flags -all
jcmd 12345 VM.system_properties
jcmd 12345 VM.version
~~~

Modify a flag using jcmd:

~~~bash
jcmd 12345 VM.set_flag HeapDumpOnOutOfMemoryError true
~~~

View the command syntax supported by the target JVM:

~~~bash
jcmd 12345 help VM.set_flag
~~~

jcmd provides additional details on Impact and Syntax for each diagnostic command. Review the target JVM's help before running commands, especially when operating in production.

## 13. Access Permissions and the Attach Mechanism

jinfo connects to the target JVM using the Attach mechanism. Several conditions must be met:

- The PID must belong to an active Java process.
- jinfo and the target JVM must be in a machine environment where they can communicate via Attach.
- The user running jinfo needs permissions matching the user owning the JVM.
- The JVM's Attach mechanism must be enabled.
- The tool and target JVM must be compatible in platform and runtime.

If the JVM was launched with:

~~~text
-XX:+DisableAttachMechanism
~~~

tools that use Attach such as jinfo and jcmd cannot connect in the standard way.

If jinfo reports permission denied or attach failure, check the process owner, PID, namespace, JVM configuration, and OS permissions. Do not default to running as Administrator/root; use the properly authorized operations account.

## 14. Containers and Platform Limitations

When a JVM runs in Docker or a container, the PID namespace and filesystem namespace can affect process discovery and attaching.

If jps on the host does not list the JVM inside the container:

1. Identify the container and the PID inside the container using the appropriate management tool.
2. Check the process with ps inside the same namespace.
3. Run jinfo from an environment that can attach to the target JVM.
4. Ensure the user, filesystem, and Attach socket match.
5. Re-verify the PID before sending commands.

Example running the tool inside a container:

~~~bash
docker exec -it <container-name> jinfo -flags <pid>
~~~

With Kubernetes:

~~~bash
kubectl exec -it <pod-name> -c <container-name> -- jinfo -sysprops <pid>
~~~

These commands depend on the image containing JDK tools and on container access permissions. The PID on the host may differ from the PID seen from inside the container.

On Windows, some configurations may require the Debugging Tools for Windows component if dbgeng.dll is missing; PATH must also point to the target JVM's jvm.dll location per JDK documentation. If jinfo already runs on the current machine, you do not need to install this component just to follow the examples.

## 15. Sensitive Information in Output

jinfo -sysprops and the no-option mode can expose:

- User home and working directory.
- Classpath or internal library paths.
- Endpoints, environment names, and connection details.
- Custom properties set by the application.
- Configuration that may contain tokens or credentials if passed improperly by the application.

Do not pass passwords, API tokens, or private keys in JVM arguments or system properties. Prefer a secret manager or the platform's secret-provisioning mechanism.

Before sending output to colleagues or attaching it to a ticket:

- Collect only the necessary subset of information.
- Strip tokens, passwords, sensitive endpoints, and personal data.
- Restrict who can read the logs.
- Do not store raw output in public directories or repositories.
- Delete temporary copies according to retention policies.

Permission to run jinfo is also permission to observe application configuration. Grant it only to accounts tasked with diagnosing that process.

## 16. Using jhsdb jinfo with Core Dumps

Standard jinfo takes the PID of a running JVM. When you need to analyze a crash dump/core file, use the jinfo mode of the jhsdb tool.

Example:

~~~bash
jhsdb jinfo --exe /path/to/java --core core.12345
~~~

Print only VM flags:

~~~bash
jhsdb jinfo --exe /path/to/java --core core.12345 --flags
~~~

Print only system properties:

~~~bash
jhsdb jinfo --exe /path/to/java --core core.12345 --sysprops
~~~

The executable path must be the binary corresponding to the core dump. For JVMs created via the JNI Invocation API, the binary that produced the core may not be named java.

jhsdb is a low-level analysis tool and is also classified as experimental/unsupported. In particular, attaching jhsdb to a running JVM can hang the process and even crash it when the debugger detaches. Use the core dump examples only for postmortem analysis and consult the jhsdb documentation for the exact JDK.

## 17. Common Errors When Running jinfo

| Symptom | Possible Cause | Resolution |
|---|---|---|
| jinfo is not recognized | JDK bin is not in PATH or the runtime image lacks the tool. | Check JAVA_HOME, PATH, and the full JDK installation. |
| Could not attach to process | Wrong PID, process has exited, or Attach mechanism is unavailable. | Re-run jcmd -l/jps -l and verify the PID. |
| Operation not permitted / access denied | User lacks permission to attach to the JVM. | Use the account that owns the process or granted permissions. |
| jinfo -flags does not return expected results | Inspecting the wrong JVM or a different JDK vendor/runtime. | Check PID, VM.version, and tool path. |
| jinfo -sysprops lacks the expected property | Property was not set for the process or changed at runtime. | Check the command line, application, and current system properties. |
| jinfo -flag reports flag does not exist | Misspelled flag name or flag not present in the target JVM version. | Check documentation for the exact JDK and jcmd VM.flags -all. |
| jinfo cannot change a flag | Flag does not support runtime updates or value is invalid. | Check manageable status, syntax, and value. |
| Flag change is lost after restart | jinfo only changes the configuration of the current process. | Update startup parameters or deployment configuration. |
| jinfo does not see a JVM in a container | Different PID namespace or attach environment. | Run the tool inside the appropriate container or namespace. |
| Output contains secret information | System property or JVM argument contains a secret. | Do not share raw output; scrub secrets and fix provisioning. |
| jinfo is unavailable on newer JDKs | Experimental/unsupported tool has changed or been removed. | Use jcmd or a supported diagnostic tool. |

## 18. Procedure for Inspecting JVM Configuration

A repeatable procedure:

1. Identify the JDK and tool in use with java --version and jinfo -h.
2. Find the JVM process using jcmd -l or jps -l.
3. Verify the PID, application, and process-owning user.
4. Use jinfo -flags when you need to read VM flags.
5. Use jinfo -sysprops when you need to read system properties.
6. Use jinfo -flag name PID to check a specific flag.
7. Modify a flag only after confirming it supports runtime updates and understanding the impact.
8. Read the flag again to confirm the new value.
9. Record the change and update deployment configuration if it must persist across restarts.
10. For new diagnostics, prefer jcmd and check help/Impact for the corresponding command.
11. Review the output to remove sensitive information before sharing.
12. For crash dumps, use jhsdb jinfo with the corresponding executable instead of the PID of an exited process.

## 19. Checklist When Using jinfo

- [ ] Confirmed jinfo is available in the JDK in use.
- [ ] Identified the exact PID of the target JVM.
- [ ] Distinguished -flags from -sysprops.
- [ ] Understood that running without options prints both flags and system properties.
- [ ] Used -flag name to read a specific flag.
- [ ] Checked that a flag can be changed dynamically before using +name, -name, or name=value.
- [ ] Read the flag again after modifying it.
- [ ] Understood that runtime changes do not persist across restarts.
- [ ] Checked user permissions and the Attach mechanism.
- [ ] Considered container/PID namespaces if the process is not found.
- [ ] Protected output that may contain sensitive system properties or configuration.
- [ ] Noted that jinfo is an experimental/unsupported tool and preferred jcmd for new diagnostics.
- [ ] Used jhsdb jinfo appropriately when analyzing core dumps.

## 20. References

- Oracle JDK 24 — Diagnostic Tools: https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html
- Oracle JDK 24 — The jhsdb Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jhsdb.html
- Oracle JDK 26 — The jinfo Command: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jinfo.html

jinfo helps read the configuration of a running JVM and modify certain flags that allow dynamic updates. By verifying the right PID, distinguishing flags from system properties, checking the mutability of each flag, and protecting the output, you can use this tool to investigate runtime configuration. For new diagnostic work, prefer jcmd as recommended by the JDK 24 documentation.