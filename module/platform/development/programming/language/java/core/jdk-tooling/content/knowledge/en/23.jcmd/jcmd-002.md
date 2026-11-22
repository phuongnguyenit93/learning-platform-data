# Listing JVM Processes with jcmd

## 1. What is jcmd Used For?

**jcmd** is a JDK command-line tool for sending diagnostic commands to a running Java Virtual Machine (JVM) on the same machine. It helps find Java processes, inspect JVM information, and perform diagnostic operations supported by the JVM.

For listing JVM processes, the most important command is:

~~~bash
jcmd -l
~~~

This command displays the Java processes detected by the tool on the local machine. Each line typically includes the process ID (PID), the main class or module name, and optionally the startup arguments.

jcmd is useful when a machine runs multiple Java applications, services, or multiple versions of an application. You find the PID first, verify the target JVM, and then send diagnostic commands to the right process.

jcmd is a JVM diagnostic tool. It is not a full operating system process manager and does not replace Task Manager, tasklist, ps, or Process Explorer.

## 2. Checking That jcmd Is Included in the JDK

jcmd is bundled with the JDK. Check its usage instructions:

~~~bash
jcmd -h
java --version
~~~

On Windows PowerShell, check the executable location:

~~~powershell
where jcmd
& "$env:JAVA_HOME\bin\jcmd.exe" -l
~~~

On Linux/macOS:

~~~bash
which jcmd
"$JAVA_HOME/bin/jcmd" -l
~~~

If the shell cannot find the command, check the JDK `bin` directory and the `PATH` environment variable. A minimal runtime image created with jlink may not include the jcmd tool. When the tool is missing, use a JDK that includes jcmd in the same machine/container environment as the target JVM.

## 3. Syntax and Main Modes

General syntax:

~~~text
jcmd <pid | main class> <command ...>
jcmd -l
jcmd -h
~~~

Common usage forms:

| Command | Purpose |
|---|---|
| jcmd -l | List JVM processes on the local machine. |
| jcmd | Running with no options also lists Java processes, equivalent to -l. |
| jcmd -h | Display usage help. |
| jcmd <pid> help | List the diagnostic commands supported by the JVM. |
| jcmd <pid> <command> | Send a command to the JVM with the corresponding PID. |
| jcmd <main class> <command> | Select a JVM by main class name, matching partially or in full. |
| jcmd <pid> -f <file> | Read and execute commands from a file. |

The PID is the OS-level process ID of the JVM. When multiple Java processes are running, selecting by PID is usually clearer and less ambiguous than selecting by main class.

On JDK 24.0.2, `jcmd -h` confirms that `-l` lists local JVM processes; when run without options, `jcmd` lists processes in the same way.

## 4. Listing JVM Processes with jcmd -l

Run:

~~~bash
jcmd -l
~~~

Example output:

~~~text
12132 JcmdProbe
94336 jdk.jshell/jdk.internal.jshell.tool.JShellToolProvider --feedback silent
21864 jdk.jshell/jdk.internal.jshell.tool.JShellToolProvider --feedback concise
43528 jdk.jcmd/sun.tools.jcmd.JCmd -l
~~~

The PIDs and class names in the example depend on the running machine. Some lines show a traditional main class; modular applications may display the module name together with the main class.

Meaning of each part:

- **12132:** PID of the JVM process.
- **JcmdProbe:** main class used to launch the application.
- **jdk.jshell/...:** modular application, where the module name and main class appear together.
- **--feedback silent:** startup arguments displayed after the class name, if present.

The jcmd process itself running the list command may also appear, such as the line `jdk.jcmd/sun.tools.jcmd.JCmd -l`. This is the diagnostic tool process, not necessarily an application you want to inspect.

The list can change right after running because JVMs can start or terminate concurrently. Re-verify the PID before sending diagnostic commands.

## 5. Distinguishing JVM Processes from OS Processes

A machine may run many types of processes:

- Java applications running on the HotSpot JVM.
- `jcmd` or `jps` processes.
- Java services running under a system account.
- Native executables not running on a JVM.
- Browser, database, IDE, or operating system tool processes.

`jcmd -l` is meant to list Java VM processes recognized by the tool's discovery/attach mechanism. It does not list all Windows, Linux, or macOS processes.

You can use OS tools to cross-check:

Windows:

~~~powershell
tasklist | findstr /i java
~~~

Linux:

~~~bash
ps -ef | grep '[j]ava'
~~~

macOS:

~~~bash
ps aux | grep '[j]ava'
~~~

These commands search for processes whose name or command line contains `java`, but they do not replace jcmd's JVM list. A process named `java` does not necessarily expose HotSpot diagnostic commands.

Some Java applications compiled into native executables also do not appear as standard JVM processes. Identify the runtime type before choosing a tool.

## 6. Creating a Sample JVM to Practice Listing

Create the file **JcmdProbe.java**:

~~~java
public class JcmdProbe {
    public static void main(String[] args) throws InterruptedException {
        System.out.println(
                "JcmdProbe ready; pid=" + ProcessHandle.current().pid());

        Thread.sleep(120_000);
    }
}
~~~

`ProcessHandle.current().pid()` returns the PID of the current process. `Thread.sleep` keeps the JVM running for two minutes so you have time to observe it.

Compile with Java 17 or later:

~~~bash
javac --release 17 -encoding UTF-8 JcmdProbe.java
~~~

In the first terminal, launch it:

~~~bash
java JcmdProbe
~~~

Example stdout:

~~~text
JcmdProbe ready; pid=12132
~~~

The PID is dynamic and not fixed across runs.

Open a second terminal on the same machine and run:

~~~bash
jcmd -l
~~~

The line containing the printed PID should have the main class `JcmdProbe`. After checking, return to the first terminal and press Ctrl+C to terminate the sample program.

This example was compiled with `javac --release 17` and verified with `jcmd` on JDK 24.0.2.

## 7. Selecting the Right JVM After Finding the PID

Do not send diagnostic commands based solely on an old PID recorded in documentation or logs. A PID can be reused after a process terminates.

Verification workflow:

1. Run `jcmd -l` to get the latest list.
2. Find the line with the desired main class or module.
3. Note the PID.
4. Use `VM.command_line` to verify the application and startup arguments.
5. Use `VM.version` to confirm the JVM version.
6. Only then run the appropriate diagnostic command.

Example:

~~~bash
jcmd 12132 VM.command_line
jcmd 12132 VM.version
~~~

Sample output:

~~~text
12132:
VM Arguments:
java_command: JcmdProbe
java_class_path (initial): ...\out
Launcher Type: SUN_STANDARD
~~~

~~~text
12132:
OpenJDK 64-Bit Server VM version 24.0.2+12
JDK 24.0.2
~~~

If two processes share the same main class, use the PID and cross-check the command line, classpath, version, or deployment details to avoid targeting the wrong application.

## 8. Viewing Diagnostic Commands Supported by the JVM

After identifying the PID, view the list of commands:

~~~bash
jcmd 12132 help
~~~

The JVM returns the commands supported by its current version and configuration. The list can vary across JDK releases, vendors, JVM types, and runtime images.

To view the syntax and description of a specific command:

~~~bash
jcmd 12132 help VM.version
~~~

Example output:

~~~text
12132:
VM.version
Print JVM version information.

Impact: Low

Syntax: VM.version
~~~

The **Impact** section describes the command's impact level as reported by the JVM. Read this section before running operations that may consume significant resources or affect the process.

Do not assume every JVM has the exact same set of commands. The `help` output of the target JVM itself is the direct source of truth.

## 9. Commonly Used Commands After Listing

After finding the PID, you can use several informational commands:

| Command | Information |
|---|---|
| VM.version | JVM and JDK version. |
| VM.command_line | Command line and startup details. |
| VM.flags | Active JVM flags. |
| VM.uptime | How long the JVM has been running. |
| VM.system_properties | JVM system properties. |
| Thread.print | Thread dump and stack traces of threads. |
| GC.heap_info | Heap overview information. |
| GC.class_histogram | Histogram of class instance counts and sizes. |

Example:

~~~bash
jcmd 12132 VM.version
jcmd 12132 VM.command_line
jcmd 12132 VM.flags
jcmd 12132 VM.uptime
jcmd 12132 GC.heap_info
~~~

To inspect threads:

~~~bash
jcmd 12132 Thread.print
~~~

`Thread.print` can produce large output. `GC.class_histogram` can take time and affect performance depending on heap size. Run them only when needed, especially in production.

`VM.system_properties` may contain sensitive paths, endpoints, or configuration values. Do not share the output publicly without reviewing and redacting secrets.

## 10. Sending Commands by PID or Main Class

The most common and explicit approach is specifying the PID:

~~~bash
jcmd 12132 VM.version
~~~

You can also select by main class:

~~~bash
jcmd JcmdProbe VM.version
~~~

According to jcmd syntax, the main class name can match part or all of the class name used to launch Java. This is convenient when only one matching instance is running.

If multiple JVMs are running the same class, selecting by main class can be ambiguous. In service or production environments, prefer a freshly verified PID.

jcmd also supports PID `0`:

~~~bash
jcmd 0 VM.version
~~~

PID `0` means the command is sent to all Java processes accessible to jcmd. This is not simply a listing mechanism. Use it only when you genuinely intend to execute the same diagnostic command on every accessible JVM, as the impact multiplies with the number of processes.

## 11. Running Multiple Diagnostic Commands from a File

jcmd supports reading commands from a file using the `-f` option.

Example file **jcmd-commands.txt**:

~~~text
VM.version
VM.uptime
VM.flags
~~~

Run:

~~~bash
jcmd 12132 -f jcmd-commands.txt
~~~

The commands in the file are sent to the selected JVM. Inspect the file contents before running, as it may contain commands that impact the process.

This approach is useful when you need to repeat a consistent set of checks in testing or operations support workflows. For production, keep the command list short and include only commands whose impact has been evaluated.

## 12. Permissions and the Attach Mechanism

jcmd uses the Attach mechanism to communicate with the target JVM. Key requirements:

- jcmd and the target JVM must be on the same machine.
- On Unix systems, the user running jcmd needs the appropriate effective user and group matching the target process.
- On Windows, the account and permissions must allow attaching to the process.
- The target JVM must support the Attach mechanism and must not have it disabled.
- A JDK/JVM environment compatible with the target is required.

If the JVM was started with **-XX:+DisableAttachMechanism**, Attach-based tools like jcmd cannot send diagnostic commands through the standard mechanism.

Seeing a process in the list and successfully attaching to it are two different things. A process may appear in the list yet refuse attach requests due to configuration, permissions, or environment constraints.

Do not default to running every command as Administrator/root. First identify the account owning the JVM and run as the appropriately authorized identity.

## 13. JVMs in Docker and Container Environments

Containers create boundaries for process namespaces, filesystems, and users. As a result, jcmd running on the host may not see a JVM inside a container that has its own PID namespace.

When diagnosing a JVM inside a container:

1. Identify the exact container or pod running the application.
2. Enter the same container or an environment sharing the JVM's PID namespace.
3. Ensure the `jcmd` tool is present in the image, or mount/install the appropriate JDK tools.
4. Use a user with permission to attach to the JVM.
5. Run `jcmd -l` inside that environment.
6. Choose the PID visible inside the container, then run the required command.

Example with Docker:

~~~bash
docker exec -it <container-name> jcmd -l
~~~

Example with Kubernetes when you have cluster access:

~~~bash
kubectl exec -it <pod-name> -c <container-name> -- jcmd -l
~~~

These commands are examples only; container names, pod names, and whether jcmd is present in the image depend on your actual deployment.

The PID seen from the host may differ from the PID seen inside the container. Always use the PID listed in the same namespace where you run jcmd.

## 14. Limitations and Notes When Reading the List

`jcmd -l` is a useful discovery tool, but its list is not an absolute inventory of every Java runtime.

Several situations can produce an incomplete list:

- The JVM is on another machine.
- The JVM is running in a different PID namespace or container.
- The process belongs to another user and cannot be attached to.
- The Attach mechanism is disabled or unavailable.
- The runtime image lacks the corresponding tools.
- The application is not running on a standard HotSpot JVM.
- The process just started or terminated during the query.

A JVM not appearing in the list does not guarantee the application is not running. Cross-check with OS process tools, service manager logs, container runtime, and deployment details.

jcmd also does not provide a remote JVM list by passing a hostname. For JVMs on other machines, use a separately configured remote management/monitoring mechanism, such as JMX or an observability platform.

## 15. Comparing jcmd -l and jps

Both `jcmd` and `jps` can list local JVM processes, but they serve different purposes.

| Tool | Role |
|---|---|
| jcmd -l | Lists JVMs and serves as the starting point for sending diagnostic commands directly to a PID. |
| jps | Utility for listing JVM processes; has options to display the main class, arguments, and JVM arguments. |
| tasklist / ps | Lists OS-level processes; not a specialized diagnostic interface for the JVM. |

Example:

~~~bash
jps -lv
~~~

`jps` can be handy when you want a quick view of processes and JVM arguments. Once you have the PID, `jcmd` lets you query deeper using diagnostic commands.

Both `jps` and `jcmd` have limitations regarding local process visibility, permissions, and attach environments. Do not treat a single tool's output as sole proof that all JVMs on the system have been discovered.

## 16. Common Errors When Listing or Attaching to a JVM

| Symptom | Possible Cause | Resolution |
|---|---|---|
| jcmd is not recognized | JDK `bin` is not in `PATH`, or only a minimal runtime is installed. | Check `JAVA_HOME`, `PATH`, and the JDK `bin` directory. |
| jcmd -l does not show the application | JVM is in a different container/PID namespace, owned by another user, or not discoverable. | Run in the right environment and cross-check with OS tools. |
| PID no longer exists | Process terminated or the old PID was reused. | Re-run `jcmd -l` and confirm the new PID. |
| AttachNotSupportedException | JVM does not support attach, attach is disabled, or the environment is incompatible. | Check JVM flags, user, container, and runtime. |
| Operation not permitted / access denied | Insufficient permissions or a different user owns the JVM. | Use the account authorized to attach. |
| Could not attach to process | JVM exited, attach socket/namespace is inaccessible, or attach mechanism failed. | Verify the process is alive, and check namespace and permissions. |
| Unknown diagnostic command | Target JVM does not support that command. | Run `jcmd PID help` and use an available command. |
| Multiple processes with the same main class | Selecting target by class name is ambiguous. | Select by PID and verify with `VM.command_line`. |
| Thread.print output is too large | Many threads or deep stack traces. | Redirect output to a file and run only when needed for diagnosis. |
| Process appears in list but cannot attach | Discovery succeeded, but permissions or Attach mechanism block command execution. | Check user, `-XX:+DisableAttachMechanism`, and namespace. |

If an error occurs, record the command run, PID, JDK version, execution account, and full error message. Do not re-run high-impact diagnostic commands just to test access permissions.

## 17. Operational Workflow for Using jcmd

A short, repeatable workflow:

1. Open a terminal on the exact machine or container running the JVM.
2. Verify that `jcmd` belongs to an available JDK using `jcmd -h`.
3. Run `jcmd -l` to list processes.
4. Find the PID by main class/module and startup arguments.
5. Verify the target with `VM.command_line` and `VM.version`.
6. Run `help` to see the commands supported by the target.
7. Read `Impact` and select the required diagnostic commands.
8. Save output to a controlled location if further investigation is needed.
9. Check for sensitive data before sharing output.
10. Record the PID, timestamp, JDK version, and commands executed for reference.

Example basic command sequence:

~~~bash
jcmd -l
jcmd 12132 VM.command_line
jcmd 12132 VM.version
jcmd 12132 help
jcmd 12132 GC.heap_info
~~~

Replace `12132` with the actual verified PID. Do not copy sample PIDs from documentation into a live environment.

In automated scripts, check exit codes and handle cases where the target is not found. Avoid assuming a fixed PID across deployments or reboots.

## 18. Checklist for Listing JVM Processes

- [ ] Confirmed `jcmd` belongs to the JDK and can run in the current environment.
- [ ] Used `jcmd -l` to obtain the latest list of JVM processes.
- [ ] Understood the PID, main class/module, and arguments in the output.
- [ ] Distinguished the `JCmd` tool process line from the application under inspection.
- [ ] Verified the PID using `VM.command_line` and `VM.version`.
- [ ] Used `jcmd PID help` to check commands supported by the target.
- [ ] Read `Impact` before running any diagnostic command.
- [ ] Used the correct user and the same machine/PID namespace as the JVM.
- [ ] Checked the Attach mechanism if unable to connect.
- [ ] Avoided using stale PIDs or main-class selectors when multiple instances exist.
- [ ] Protected output that may contain sensitive command-line arguments or system properties.
- [ ] Cross-checked with OS tools when the JVM list appears incomplete.

`jcmd -l` is the first step to locate local JVM processes and obtain a PID for further diagnostics. By verifying the right target, checking attach permissions, and reviewing each command's impact, you can investigate JVMs safely and repeatably across both development and operations environments.
