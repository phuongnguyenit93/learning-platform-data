# Process Access Permissions with jinfo

**jinfo** is a JDK command-line tool used to retrieve configuration information from a running Java process. It can display JVM flags and Java system properties, and it also supports modifying certain VM flags while the JVM is running.

The topic **Process Access Permissions** focuses on identifying the right process, operating system conditions that allow attaching, operator account permissions, and the risks involved in reading or changing JVM configuration. Having a valid PID is not enough: the process must be a Java process, the attach mechanism must be enabled, and the user running the tool must have appropriate access permissions.

Note the status of the tool: in JDK 26, Oracle marks jinfo as **experimental and unsupported**, meaning it may be removed in future JDK releases. Oracle recommends using **jcmd** for new diagnostics. This guide covers jinfo to help understand existing systems, process access permissions, and how to transition to jcmd.

## 1. What is jinfo used for?

jinfo retrieves configuration information from a Java process specified by its process ID (PID). The main information includes:

- JVM command-line flags: options used to start the HotSpot JVM.
- Java system properties: name/value pairs passed via -D or set by the runtime and application.
- The value of a specific JVM flag.
- Certain JVM flags that can be enabled, disabled, or have their values changed while the process is running.

Common use cases:

| Scenario | Information to check |
|---|---|
| Application is using the wrong Java release | JVM version and command line |
| Unclear how much heap is configured | Flags such as InitialHeapSize and MaxHeapSize |
| Investigating the classpath | java.class.path and related properties |
| Checking application configuration | System properties |
| Confirming whether a flag is enabled or disabled | Specific flag value |
| Checking configuration after startup | Current flags and properties |

jinfo is not a debugger, does not monitor continuously, and does not read all internal process state. Nor does the tool determine which configurations are safe; operators must understand the meaning of each flag and property.

## 2. Syntax and specifying a process

JDK 26 syntax:

~~~bash
jinfo [option] pid
~~~

Where:

- option is the option to execute.
- pid is the process ID of the Java process to inspect.

Example:

~~~bash
jinfo 2125
~~~

If no option is passed, jinfo prints both JVM command-line flags and system property name-value pairs.

jinfo operates on the PID of a process on the local machine. The jinfo syntax in JDK 26 is not a remote JVM administration protocol over hostname or IP. For remote administration, use a dedicated management mechanism with proper authentication and network protection, such as securely configured JMX.

## 3. Identifying the right PID before attaching

Do not guess a PID or pick a PID simply because the process name resembles the application under investigation.

### Using jps

~~~bash
jps -l
~~~

Example output:

~~~text
2125 com.acme.DemoServer
5485 jdk.jcmd/sun.tools.jps.Jps
~~~

jps lists the HotSpot JVMs that the current account has permission to see. The -l option displays the full class name or path to the application's JAR.

Note: the value displayed by jps is the local VM identifier (lvmid). It is usually the operating system PID, but the documentation does not guarantee it always matches the OS PID in every case.

jps is also an experimental/unsupported tool. Do not write scripts that strictly depend on its output format, as the format may change between JDK releases.

### Using OS tools

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

These commands help cross-check the PID, the account running the process, and the command line. Command-line output may contain sensitive information; only store or share it when properly authorized.

### Verifying the PID before use

Suppose the PID is 2125:

~~~bash
jinfo -flags 2125
~~~

If the PID has terminated and been reassigned by the operating system to another process, the command may fail or target the wrong process. Therefore, always verify the PID right before attaching, especially when running automated scripts.

## 4. Process access permissions and the attach mechanism

jinfo needs to connect to the running JVM through the HotSpot attach mechanism. This is an operating-system and process-level operation, not a standard Java permission of a class inside the application.

Key operational requirements:

| Requirement | Meaning |
|---|---|
| Same machine | jinfo runs on the host where the target JVM is located |
| Valid PID | The PID must belong to a Java process |
| OS permissions | The account running the tool must be allowed to access the process |
| Appropriate account | Use the same account running the JVM or an account granted equivalent attach permissions |
| Attach enabled | The JVM must not have been started with DisableAttachMechanism |
| Compatible JDK | Use a tool from the same JDK release as the target JVM whenever possible |

Oracle's jcmd documentation explicitly states that attach tools must run on the same machine and with the same effective user ID and group ID that started the JVM. jinfo also uses the local HotSpot attach mechanism; in operations, use the service account that started the JVM or an account granted corresponding access permissions by an administrator.

Do not default to running as Administrator or root to bypass permission errors. Identify which account owns the process and follow the access procedure approved by your organization.

### Example of a process running under a service account

~~~text
PID    USER          COMMAND
2125   acme-service  java -jar app.jar
~~~

If the JVM is running under the acme-service account, the operator should execute the jinfo command as that same account or as an account granted attach permissions according to OS policy.

On Linux, you can inspect the process identity:

~~~bash
ps -o pid,user,group,args -p 2125
~~~

This command only displays process information; it does not grant attach permissions.

If you need to run as the service account and your organization permits sudo, for example:

~~~bash
sudo -u acme-service -- jinfo -flags 2125
~~~

The path to jinfo may need to be specified explicitly if the service account's PATH does not include the JDK bin directory.

## 5. The attach mechanism can be disabled

HotSpot provides the option:

~~~bash
-XX:+DisableAttachMechanism
~~~

When the JVM is started with this option, tools relying on the attach mechanism such as jcmd, jinfo, jstack, and jmap cannot attach in the normal way.

Key points to remember:

- By default, the attach mechanism is enabled.
- DisableAttachMechanism must be decided when starting the JVM.
- jinfo cannot re-enable the attach mechanism for an already running process.
- If attach tools are needed, evaluate the startup configuration and schedule a process restart when appropriate.
- Do not arbitrarily remove this protection option in production without understanding why it was enabled.

Check the process command line or service configuration for this flag. If the process was started with attach disabled, running jinfo repeatedly will not resolve the root cause.

## 6. Access permissions in Docker and containers

The PID inside a container can differ from the PID visible from the host due to PID namespaces. A process may have PID 1 inside the container while having a different PID on the host.

Things to keep in mind:

- jps -l may not list JVMs running in separate Docker processes.
- Use ps in the appropriate namespace to identify the PID.
- You can run jinfo inside the container if the JDK and attach permissions are available.
- If using the host PID namespace, verify that the host PID points to the right JVM.
- The account running jinfo still needs corresponding process access permissions.
- Container policies, user namespaces, and host security mechanisms may restrict attach operations.

Example executed inside a container:

~~~bash
ps -ef
jinfo -flags 1
~~~

PID 1 here is only valid if the Java process actually has PID 1 inside the container. Verify with ps before running.

Do not take a PID from one container and use it in another. PID namespaces can cause the same number to represent different processes.

If running jinfo from the host, determine the host PID of the JVM inside the container and check the host account's permissions. Do not assume that being able to see a process means you can attach to it.

## 7. Read-only options of jinfo

### Print all default information

~~~bash
jinfo 2125
~~~

When no option is passed, jinfo prints both command-line flags and Java system property pairs.

The output can be long. In production environments, consider retrieving only the subset of information you need.

### Print flags passed at startup

~~~bash
jinfo -flags 2125
~~~

The -flags option displays the JVM flags passed when the process started. It is useful for checking options such as heap size, garbage collector, or JVM configurations explicitly declared in the startup script.

Do not confuse the list of startup flags with all default flags supported by the JVM.

### Print system properties

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

System properties can expose internal endpoints, configuration paths, account names, or secrets if the application stores secrets improperly. Treat the output as internal data and redact it before sharing.

### View the value of a single flag

~~~bash
jinfo -flag MaxHeapSize 2125
~~~

The -flag name option prints the name and value of the specified JVM flag.

Use this approach when you only need to confirm a specific setting instead of printing all flags.

### View help

~~~bash
jinfo -help
~~~

You can also use:

~~~bash
jinfo -h
~~~

Documentation and available options may change between JDK releases because jinfo is an experimental tool.

## 8. The -flag option can modify process configuration

This is the area that requires the most caution when discussing process access permissions.

jinfo supports three forms of -flag:

| Syntax | Action |
|---|---|
| -flag name | Read the value of the flag |
| -flag +name or -flag -name | Enable or disable a Boolean flag |
| -flag name=value | Set a new value for the flag |

Read example:

~~~bash
jinfo -flag MaxHeapSize 2125
~~~

Boolean toggle form:

~~~bash
jinfo -flag +BooleanFlag 2125
jinfo -flag -BooleanFlag 2125
~~~

Value assignment form:

~~~bash
jinfo -flag FlagName=NewValue 2125
~~~

BooleanFlag and FlagName above are placeholder names illustrating the syntax. In real operations, only use flag names supported by the target JVM.

Not every JVM flag can be changed at runtime. Some flags only take effect when the JVM starts; others are marked as dynamically manageable. If you attempt to change a flag that does not support runtime updates, the operation will fail or the JVM will reject the value.

Before making a change:

1. Verify that the flag is allowed to be changed dynamically.
2. Read the current value.
3. Check that the new value is within the valid range.
4. Assess the impact on heap, GC, logging, or runtime behavior.
5. Record who performed the change and when.
6. Have a rollback plan if the result is unexpected.

Do not modify flags on a production process just to test syntax. A runtime change also does not persist to the startup configuration; when the process restarts, the value may revert to what is declared in the startup script.

## 9. Reading flags and system properties with jcmd

Oracle recommends using jcmd instead of jinfo for new diagnostics. Common equivalent commands:

| Need | jinfo | jcmd |
|---|---|---|
| View flags | jinfo -flags PID | jcmd PID VM.flags |
| View all flags supported by the JVM | No clear direct equivalent | jcmd PID VM.flags -all |
| View a single flag | jinfo -flag name PID | jcmd PID VM.flags -all and search for the flag |
| View system properties | jinfo -sysprops PID | jcmd PID VM.system_properties |
| Change a manageable flag's value | jinfo -flag name=value PID | jcmd PID VM.set_flag name value |

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

Before using VM.set_flag, check the syntax on the target JVM:

~~~bash
jcmd 2125 help VM.set_flag
~~~

jcmd also requires appropriate attach permissions and must run on the same machine as the JVM. The JDK 26 documentation explicitly states that the same effective user ID and group ID are required for this operation. Switching to jcmd does not eliminate process permission requirements.

## 10. jinfo is an experimental and unsupported tool

The JDK 26 manual explicitly states that jinfo is experimental and unsupported. This has practical implications:

- The tool may change or be removed in a future JDK release.
- Do not build production pipelines that depend on jinfo's output format.
- Scripts that parse its output may break across JDK updates.
- Support across operating systems is not uniform.
- Prefer jcmd for new diagnostic workflows.

Oracle also recommends not using serviceability tools from one JDK release to troubleshoot a JVM from a different release. Use a JDK compatible with the target process to avoid errors caused by differences in implementation or internal protocols.

If a legacy system currently uses jinfo, document the JDK version, operating system, commands, and output format before migrating.

## 11. Windows-specific requirements

The JDK 26 jinfo manual notes a specific requirement on Windows:

- If dbgeng.dll is not present, you need to install Debugging Tools for Windows for these tools to work.
- PATH must contain the location of jvm.dll used by the target process or the location corresponding to the executable/core file.

When encountering native debugging or attach errors on Windows, check:

1. The JDK and target JVM architecture.
2. Whether PATH includes the required directories.
3. Whether dbgeng.dll is available.
4. Whether the process belongs to the right account with proper access permissions.
5. Whether jinfo is compatible with the target process's JDK.

Do not download standalone DLLs from untrusted sources to fix errors. Use official Windows tools and the JDK distribution managed by your organization.

## 12. Protecting data retrieved from a process

Attach permissions can allow an operator to read a wide range of information used by the application.

For example:

- java.class.path can expose directories and deployment structure.
- java.home reveals the JDK location.
- user.dir reveals the working directory.
- Custom system properties may contain endpoints, tokens, or internal configuration.
- JVM flags can expose heap sizes, GC settings, and operational options.

Measures to apply:

- Grant attach permissions only to the operations team members who need them.
- Do not share full output in public channels.
- Redact secrets and identifying information before sending logs.
- Do not store output in directories with public read permissions.
- Log the PID, account, timestamp, and purpose of collection.
- Limit the retention period of diagnostic files.
- Avoid passing passwords or tokens in JVM arguments in the first place.

In particular, do not run jinfo on processes outside your administrative scope. Process access permissions can expose application data and may allow modifying certain JVM flags.

## 13. Using jhsdb jinfo for core dumps

jinfo in JDK 26 takes the PID of a running Java process. When you need to read information from a core dump after an incident, use the postmortem mode of jhsdb:

~~~bash
jhsdb jinfo --exe /path/to/java --core /path/to/core
~~~

Where:

- --exe is the Java executable corresponding to the core dump.
- --core is the core dump file to analyze.

Clearly distinguish between the two cases:

- jinfo PID: retrieves configuration from a running Java process.
- jhsdb jinfo --exe ... --core ...: reads information from a core dump.

Do not arbitrarily use jhsdb to attach to a live production process. The JDK 26 manual warns that attaching jhsdb to a running process can cause the process to hang and potentially crash when the debugger detaches. For active processes, prefer jcmd.

## 14. Java 17+ example: creating a process to practice access permissions

This example creates a waiting Java process so you have time to identify the PID and run jinfo from a second terminal.

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

Flag and property output varies by JDK, operating system, and startup configuration. There is no fixed list of values across all machines.

If jinfo is unavailable or does not work on the JDK you are using, perform the corresponding steps with jcmd:

~~~bash
jcmd 2125 VM.flags
jcmd 2125 VM.system_properties
~~~

When finished, return to the terminal running DemoServer and press Ctrl+C to stop the test process.

## 15. Troubleshooting process access errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| Process ID does not exist | Wrong PID or process has exited | Re-run jps/ps and confirm the new PID |
| Process is not a Java process | PID points to another application | Check the command line and process executable |
| Attach failed or permission denied | Account running the tool lacks access permissions | Check owner, effective UID/GID, and OS permissions |
| JVM not visible in jps | Different user or JVM is in a separate Docker namespace | Use ps in the right namespace or run the tool inside the container |
| Attach mechanism disabled | JVM started with -XX:+DisableAttachMechanism | Check startup flags and plan a restart if attach is needed |
| jinfo not recognized | JDK bin is not in PATH or JDK build lacks the tool | Check JAVA_HOME and the bin directory |
| Unknown flag | Flag does not exist in this JVM release or name is misspelled | Check flags with jcmd and use the exact name |
| Flag cannot be changed | Flag does not support runtime updates | Check dynamic manageability and change at restart if needed |
| Output missing system properties | Used -flags instead of -sysprops | Choose the right option |
| jinfo error on Windows | Missing dbgeng.dll or PATH cannot find jvm.dll | Install Debugging Tools for Windows and check PATH |
| jinfo behaves differently across two JDKs | Experimental tool or different releases | Use the tool from the same release as the target JVM; prefer jcmd |
| Output contains secrets | Application passes secrets via -D or command line | Restrict access, redact output, and fix secret management |
| Core dump cannot be read | Wrong executable or mismatched core file | Use the exact binary that generated the core and verify the dump file |

## 16. Process for granting and using process access permissions

An operational workflow you can adopt:

1. Identify the service and diagnostic objective.
2. Confirm the host, container, and PID of the JVM.
3. Check the account owning the process using ps or OS tools.
4. Use an operator account granted attach permissions.
5. Confirm that the attach mechanism is not disabled.
6. Check the JVM's JDK release and use a compatible tool.
7. Start with low-impact read commands such as jinfo -flag or jcmd VM.flags.
8. Only read system properties when needed and protect the output.
9. Do not change a VM flag without verifying that it is dynamically manageable and assessing its impact.
10. Record the command, PID, operator, and timestamp.
11. Delete or protect output according to your retention policy.
12. Prefer migrating new scripts to jcmd and re-testing on the target JDK.

Attach permissions should be granted according to the principle of least privilege. If multiple services need support, use dedicated operational accounts and clear authorization procedures rather than granting machine-wide administrative privileges to everyone.

## 17. Key takeaways

- jinfo retrieves JVM flags and Java system properties of a Java process specified by its PID.
- JDK 26 jinfo is experimental and unsupported; Oracle recommends using jcmd for new diagnostics.
- jinfo uses the local attach mechanism; access permissions depend on the account and OS policies.
- For HotSpot attach tools, use the same effective user ID and group ID that started the JVM, per the documented attach requirements for jcmd.
- -XX:+DisableAttachMechanism disables attach tools such as jinfo and jcmd.
- jps -l helps locate JVMs but may not see JVMs in separate Docker processes; lvmid is usually the OS PID but is not guaranteed to always match.
- -flags prints flags passed at startup; -sysprops prints system properties; -flag name reads the value of a single flag.
- -flag +name, -flag -name, and -flag name=value can modify certain flags while the JVM is running.
- Not all JVM flags can be changed at runtime; check dynamic manageability before making changes.
- Output may contain classpaths, endpoints, paths, and secrets; protect it as internal data.
- jcmd VM.flags and VM.system_properties are the modern alternatives for common read operations.
- Use jhsdb jinfo for core dumps; avoid arbitrarily attaching jhsdb to live processes as it can hang or crash them.
- Use a JDK compatible with the target JVM and check Windows-specific requirements when needed.

## Official references

- [The jinfo Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jinfo.html)
- [The jcmd Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
- [The jps Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jps.html)
- [The java Command — DisableAttachMechanism, JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [The jhsdb Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jhsdb.html)