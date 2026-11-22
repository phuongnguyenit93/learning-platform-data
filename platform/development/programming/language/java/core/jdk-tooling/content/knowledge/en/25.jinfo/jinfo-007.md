# Process Access Permissions with jinfo

**jinfo** is a JDK command-line tool used to retrieve configuration information from a running Java process. It can display JVM flags and Java system properties, and also supports modifying certain VM flags that can be updated while the JVM is running.

The topic **Process Access Permissions** focuses on how to identify the right process, operating system conditions that permit attaching, operator account permissions, and the risks of reading or modifying JVM configuration. Having the right PID is not enough: the process must be a Java process, the attach mechanism must be enabled, and the user running the tool must have appropriate access permissions.

It is important to know the status of the tool: in JDK 26, Oracle marks jinfo as **experimental and unsupported**, and it may be removed in future JDK releases. Oracle recommends using **jcmd** for modern diagnostics because it offers more features and lower overhead. This article still covers jinfo to help you understand legacy systems, how process permissions work, and how to migrate to jcmd.

## 1. What is jinfo used for?

jinfo retrieves configuration information from a Java process specified by its process ID (PID). The main information includes:

- JVM command-line flags: options used to launch the HotSpot JVM.
- Java system properties: name/value pairs supplied via -D or set by the runtime and application.
- The value of a specific JVM flag.
- Certain JVM flags that can be enabled, disabled, or updated while the process is running.

Common use cases:

| Scenario | Information to Inspect |
|---|---|
| Application is using the wrong Java release | JVM version and command line |
| Unclear how much heap is configured | Flags such as InitialHeapSize and MaxHeapSize |
| Investigating classpath | java.class.path and related properties |
| Checking application configuration | System properties |
| Verifying whether a flag is enabled or disabled | Specific flag value |
| Inspecting configuration after startup | Current flags and properties |

jinfo is not a tool for reading all internal process state, not a debugger, and not a continuous monitoring tool. Nor does it determine which configuration is safe; the operator must understand the meaning of each flag and property.

## 2. Syntax and Specifying a Process

JDK 26 syntax:

~~~bash
jinfo [option] pid
~~~

Where:

- option is the operation you want to perform.
- pid is the process ID of the Java process to inspect.

Example:

~~~bash
jinfo 2125
~~~

If no option is passed, jinfo prints both JVM command-line flags and system properties.

jinfo operates on the PID of a process on the local machine. The JDK 26 jinfo syntax is not a remote JVM administration protocol over hostname or IP. For remote administration, use a dedicated management mechanism with proper authentication and network protection, such as securely configured JMX.

## 3. Identifying the Right PID Before Attaching

Do not guess a PID or pick one just because a process has a name similar to the application under investigation.

### Using jps

~~~bash
jps -l
~~~

Example output:

~~~text
2125 com.acme.DemoServer
5485 jdk.jcmd/sun.tools.jps.Jps
~~~

jps lists the HotSpot JVMs visible to the current account. The -l option displays the full class name or the module/JAR name of the application.

### Using Operating System Tools

On Linux:

~~~bash
ps -ef | grep java
~~~

Or:

~~~bash
ps -eo pid,user,group,args
~~~

On Windows PowerShell:

~~~powershell
Get-CimInstance Win32_Process |
    Where-Object { $_.Name -match '^java(w)?\.exe$' } |
    Select-Object ProcessId, Name, CommandLine
~~~

These commands help cross-check the PID, the account running the process, and the command line. Command-line output may contain sensitive information; store or share it only when authorized.

### Verifying the PID Before Use

Suppose the PID is 2125:

~~~bash
jinfo -flags 2125
~~~

If the PID has terminated and the operating system has reassigned it to another process, the command may fail or target the wrong process. Therefore, verify the PID right before attaching, especially in automated scripts.

## 4. Process Access Permissions and the Attach Mechanism

jinfo needs to connect to a running JVM through the HotSpot attach mechanism. This is an operating-system and process-level operation, not a regular Java permission of a class inside the application.

Key operational requirements:

| Requirement | Meaning |
|---|---|
| Same machine | jinfo runs on the host where the target JVM resides |
| Valid PID | The PID must belong to a Java process |
| OS permissions | The account running the tool must be permitted to access the process |
| Matching account | For HotSpot attach tools, run with the same effective user ID and group ID that launched the JVM |
| Attach enabled | The JVM must not have been launched with DisableAttachMechanism |
| Compatible JDK | Use a tool from the same JDK release as the target JVM whenever possible |

Oracle explicitly states the requirement for the same effective user and group identifiers in the jcmd attach guide. jinfo belongs to the same group of local HotSpot attach tools, so the safe operational practice is to use the service account that started the JVM or an account granted equivalent permissions by an administrator.

Do not default to running as Administrator or root to bypass permission errors. Identify which account owns the process and follow the access procedure approved by your organization.

### Process Account Example

~~~text
PID    USER          COMMAND
2125   acme-service  java -jar app.jar
~~~

If the JVM is running under the acme-service account, the operator should run jinfo using that same account or an account granted attach permissions according to OS policy.

On Linux, you can check process identity with ps:

~~~bash
ps -o pid,user,group,args -p 2125
~~~

This command only displays process information; it does not grant attach permissions.

## 5. The Attach Mechanism Can Be Disabled

HotSpot provides the option:

~~~bash
-XX:+DisableAttachMechanism
~~~

When a JVM is launched with this option, tools that rely on the attach mechanism—such as jcmd, jinfo, jstack, and jmap—cannot attach in the normal way.

Key points to remember:

- By default, the attach mechanism is enabled.
- DisableAttachMechanism must be decided at JVM startup.
- jinfo cannot re-enable the attach mechanism for a running process.
- If attach tools are needed, evaluate the startup configuration and schedule a process restart when appropriate.
- Do not arbitrarily remove protective options in production without understanding why they were enabled.

Check the process command line or service configuration for this flag. If the process was started with attach disabled, running jinfo repeatedly will not resolve the issue.

## 6. Access Permissions in Docker and Containers

A PID inside a container may differ from the PID seen from the host due to PID namespaces. A process may have PID 1 inside a container while having a different PID on the host.

Important considerations:

- jps -l may not list JVMs running in separate Docker processes.
- Use ps in the right namespace to identify the PID.
- You can run jinfo inside the container if the JDK and attach permissions are available.
- If using the host PID namespace, verify that the host PID points to the right JVM.
- The account running jinfo still needs appropriate process access permissions.
- Container policies, user namespaces, and host security mechanisms may restrict attach operations.

Example executed inside a container:

~~~bash
ps -ef
jinfo -flags 1
~~~

PID 1 here is valid only if the Java process actually has PID 1 inside the container. Verify with ps before running.

Do not take a PID from one container and use it in another. PID namespaces can cause the same number to represent different processes.

## 7. jinfo Options for Reading Information

### Printing All Default Information

~~~bash
jinfo 2125
~~~

When no option is passed, jinfo prints both command-line flags and Java system property pairs.

The output can be long. In production environments, consider retrieving only the subset of information you need.

### Printing Flags Passed at Startup

~~~bash
jinfo -flags 2125
~~~

The -flags option displays the JVM flags passed when launching the process. It is useful for checking options such as heap size, garbage collector, or JVM settings explicitly declared in the startup script.

Do not confuse the list of startup flags with all default flags supported by the JVM.

### Printing System Properties

~~~bash
jinfo -sysprops 2125
~~~

The -sysprops option prints Java system property name-value pairs.

Properties may include:

- java.version
- java.vendor
- java.home
- java.class.path
- user.dir
- file.encoding
- Application properties passed via -D.

System properties can expose internal endpoints, configuration paths, account names, or secrets if an application stores secrets improperly. Treat the output as internal data and redact it before sharing.

### Viewing a Single Flag Value

~~~bash
jinfo -flag MaxHeapSize 2125
~~~

The -flag name option prints the name and value of the specified JVM flag.

Use this when you only need to verify a specific setting instead of printing all flags.

### Viewing Help

~~~bash
jinfo -help
~~~

You can also use:

~~~bash
jinfo -h
~~~

Documentation and available options may vary across JDK releases because jinfo is an experimental tool.

## 8. The -flag Option Can Modify Process Configuration

This is the part that requires the greatest caution regarding process access permissions.

jinfo supports three forms of -flag:

| Syntax | Action |
|---|---|
| -flag name | Read the value of a flag |
| -flag +name or -flag -name | Enable or disable a Boolean flag |
| -flag name=value | Set a new value for a flag |

Read example:

~~~bash
jinfo -flag MaxHeapSize 2125
~~~

Boolean enable/disable form:

~~~bash
jinfo -flag +BooleanFlag 2125
jinfo -flag -BooleanFlag 2125
~~~

Value assignment form:

~~~bash
jinfo -flag FlagName=NewValue 2125
~~~

BooleanFlag and FlagName above are placeholders illustrating the syntax. In real operations, use only flag names supported by the target JVM.

Not every JVM flag can be changed at runtime. Some flags only take effect at JVM startup; others are marked as dynamically manageable. Attempting to change a flag that does not support runtime updates will fail or be rejected by the JVM.

Before making a change:

1. Confirm whether the flag is allowed to be modified dynamically.
2. Read the current value.
3. Check whether the new value is within a valid range.
4. Assess the impact on heap, GC, logging, or runtime behavior.
5. Record who made the change and when.
6. Have a rollback plan if the outcome is unexpected.

Do not change flags on a production process just to test syntax.

## 9. Reading Flags and System Properties with jcmd

Oracle recommends using jcmd instead of jinfo for new diagnostics. Common equivalent commands:

| Need | jinfo | jcmd |
|---|---|---|
| View flags | jinfo -flags PID | jcmd PID VM.flags |
| View all flags supported by the JVM | No clear direct equivalent | jcmd PID VM.flags -all |
| View a single flag | jinfo -flag name PID | jcmd PID VM.flags -all and look up the flag |
| View system properties | jinfo -sysprops PID | jcmd PID VM.system_properties |
| Change a manageable flag | jinfo -flag name=value PID | jcmd PID VM.set_flag name value |

Example reading flags:

~~~bash
jcmd 2125 VM.flags
~~~

View all flags:

~~~bash
jcmd 2125 VM.flags -all
~~~

View system properties:

~~~bash
jcmd 2125 VM.system_properties
~~~

Change a flag that supports runtime updates:

~~~bash
jcmd 2125 VM.set_flag FlagName NewValue
~~~

Before using VM.set_flag, check:

~~~bash
jcmd 2125 help VM.set_flag
~~~

jcmd also requires appropriate attach permissions and must run on the same machine as the JVM. Oracle describes matching effective user and group identifiers as a requirement for this operation. Switching to jcmd does not eliminate process permission requirements.

## 10. jinfo Is Experimental and Unsupported

The JDK 26 manual explicitly states that jinfo is experimental and unsupported. In practice, this means:

- The tool may change or be removed in future JDK releases.
- Production pipelines should not depend on jinfo's output format.
- Output-parsing scripts may break across JDK updates.
- Support across operating systems is not uniform.
- jcmd should be preferred for new diagnostic workflows.

Oracle also recommends against using serviceability tools from one JDK release to troubleshoot a JVM from a different release. Use a JDK compatible with the target process to avoid errors caused by implementation or internal protocol differences.

If a legacy system currently uses jinfo, document the JDK version, operating system, commands, and output format before migrating.

## 11. Windows-Specific Requirements

The JDK 26 jinfo manual notes a specific requirement on Windows:

- If dbgeng.dll is missing, install Debugging Tools for Windows for these tools to work.
- PATH must contain the location of the jvm.dll used by the target process or the location corresponding to the executable/core file.

When encountering native debugging or attach errors on Windows, check:

1. The JDK and target JVM architecture.
2. Whether PATH includes the required directories.
3. Whether dbgeng.dll is present.
4. Whether the process belongs to the right account with proper access permissions.
5. Whether jinfo is compatible with the target process's JDK.

Do not download standalone DLLs from untrusted sources to fix errors. Use official Windows tools and an organization-managed JDK distribution.

## 12. Protecting Data Retrieved from a Process

Attach permissions can allow an operator to read a wide range of information used by an application.

For example:

- java.class.path can reveal directories and deployment structure.
- java.home indicates the JDK location.
- user.dir reveals the working directory.
- Custom system properties may contain internal endpoints, tokens, or configuration.
- JVM flags can expose heap size, GC, and operational options.

Measures to apply:

- Grant attach permissions only to the operational team that needs them.
- Do not share full output in public channels.
- Redact secrets and identifying information before sending logs.
- Do not store output in directories with public read permissions.
- Log the PID, account, timestamp, and purpose of collection.
- Limit the retention of diagnostic files.
- Do not pass passwords or tokens in JVM arguments in the first place.

In particular, never run jinfo against a process outside your administrative scope. Process access permissions can expose application data and may allow modifying certain JVM flags.

## 13. Using jhsdb jinfo for Core Dumps

jinfo in JDK 26 accepts the PID of a running Java process. When you need to read information from a core dump after an incident, use jhsdb in postmortem mode:

~~~bash
jhsdb jinfo --exe /path/to/java --core /path/to/core
~~~

Where:

- --exe is the Java executable corresponding to the core dump.
- --core is the core dump file to analyze.

For example, on Linux you can use gcore to generate a core dump when authorized and permitted by operational policy, then analyze it with jhsdb.

Distinguish clearly between the two cases:

- jinfo PID: retrieves configuration from a running Java process.
- jhsdb jinfo --exe ... --core ...: reads information from a core dump.

Do not use jhsdb to attach arbitrarily to a live production process. The JDK 26 manual warns that attaching jhsdb to a running process may cause the process to hang and potentially crash when the debugger detaches. For live processes, prefer jcmd.

## 14. Java 17+ Example: Creating a Process to Practice Access Permissions

This example creates a waiting Java process so you have time to identify its PID and run jinfo from a second terminal.

Structure:

~~~text
project/
  src/
    com/acme/DemoServer.java
  out/
~~~

File src/com/acme/DemoServer.java:

~~~java
package com.acme;

import java.util.concurrent.CountDownLatch;

public final class DemoServer {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("READY");
        new CountDownLatch(1).await();
    }
}
~~~

Compile:

~~~bash
javac --release 17 -d out src/com/acme/DemoServer.java
~~~

Run the process:

~~~bash
java -cp out com.acme.DemoServer
~~~

Stdout:

~~~text
READY
~~~

Open a second terminal and find the PID:

~~~bash
jps -l
~~~

Suppose the displayed PID is 2125. View flags:

~~~bash
jinfo -flags 2125
~~~

View system properties:

~~~bash
jinfo -sysprops 2125
~~~

View a single flag:

~~~bash
jinfo -flag MaxHeapSize 2125
~~~

Flag and property output varies by JDK, operating system, and startup configuration. There is no single fixed list of values across all machines.

If jinfo is unavailable or does not work on your JDK, perform the equivalent steps with jcmd:

~~~bash
jcmd 2125 VM.flags
jcmd 2125 VM.system_properties
~~~

When finished, return to the terminal running DemoServer and press Ctrl+C to stop the test process.

## 15. Troubleshooting Process Access Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Process ID does not exist | Wrong PID or process has exited | Re-run jps/ps and verify the new PID |
| Process is not a Java process | PID points to another application | Check the command line and process executable |
| Attach failed or permission denied | Account running the tool lacks access | Check owner, effective UID/GID, and OS permissions |
| JVM not visible in jps | Different user or JVM in a separate Docker namespace | Use ps in the right namespace or run the tool inside the container |
| Attach mechanism disabled | JVM started with -XX:+DisableAttachMechanism | Check startup flags and plan a restart if attach is required |
| jinfo not recognized | JDK bin not in PATH or JDK distribution lacks the tool | Check JAVA_HOME and the bin directory |
| Unknown flag | Flag does not exist in JVM release or misspelled | Check flags with jcmd and use the exact name |
| Flag cannot be changed | Flag does not support runtime updates | Check dynamic manageability and change on restart if needed |
| Output missing system properties | Used -flags instead of -sysprops | Choose the right option |
| jinfo fails on Windows | Missing dbgeng.dll or PATH cannot find jvm.dll | Install Debugging Tools for Windows and check PATH |
| jinfo behaves differently across two JDKs | Experimental tool or mismatched releases | Use a tool from the same release as the target JVM; prefer jcmd |
| Output contains secrets | Application passes secrets via -D or command line | Restrict access, redact output, and fix secret management |
| Core dump cannot be read | Wrong executable or mismatched core file | Use the exact binary that produced the core and verify the dump file |

## 16. Procedure for Granting and Using Process Access Permissions

An operational procedure you can apply:

1. Identify the service and diagnostic objective.
2. Confirm the host, container, and JVM PID.
3. Check the process-owning account using ps or OS tools.
4. Use an operational account granted attach permissions.
5. Confirm that the attach mechanism is not disabled.
6. Check the JVM's JDK release and use a compatible tool.
7. Start with low-impact read commands such as jinfo -flag or jcmd VM.flags.
8. Read system properties only when necessary and protect the output.
9. Do not change a VM flag without verifying that it is dynamically manageable and assessing its impact.
10. Record the command, PID, operator, and timestamp.
11. Delete or protect output according to retention policy.
12. Prefer migrating new scripts to jcmd and re-test on the target JDK.

Attach permissions should be granted according to the principle of least privilege. If multiple services must be supported, use dedicated operational accounts and a clear authorization workflow rather than granting machine-wide administrative privileges to everyone.

## 17. Key Takeaways

- jinfo retrieves JVM flags and Java system properties for a Java process specified by PID.
- JDK 26 jinfo is experimental and unsupported; Oracle recommends using jcmd for new diagnostics.
- jinfo uses the local attach mechanism; access depends on account and OS policies.
- For HotSpot attach tools, use the same effective user ID and group ID that started the JVM.
- -XX:+DisableAttachMechanism disables attach tools such as jinfo and jcmd.
- jps -l helps locate PIDs but may not see JVMs in separate Docker processes.
- -flags prints startup flags; -sysprops prints system properties; -flag name reads a single flag's value.
- -flag +name, -flag -name, and -flag name=value can modify certain flags while the JVM is running.
- Not all JVM flags can be modified at runtime; verify dynamic manageability before making changes.
- Output may contain classpaths, endpoints, paths, and secrets; protect it as internal data.
- jcmd VM.flags and VM.system_properties are modern alternatives for common read operations.
- Use jhsdb jinfo for core dumps; avoid attaching jhsdb arbitrarily to live processes as it may hang or crash them.
- Use a JDK compatible with the target JVM and check Windows-specific requirements when needed.

## Official References

- [The jinfo Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jinfo.html)
- [Diagnostic Tools — JDK 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html)
- [The java Command — DisableAttachMechanism, JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [The jcmd Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
- [The jhsdb Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jhsdb.html)