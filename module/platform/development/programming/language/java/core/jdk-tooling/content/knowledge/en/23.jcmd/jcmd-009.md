# PID and Access Permissions with jcmd

`jcmd` sends diagnostic commands to a running JVM. Before running a command, you need to select the right process ID (PID), verify whether that JVM allows the Attach API, and ensure the account running `jcmd` has permission to attach to the target process.

Attach capability depends on both the target process's environment and operating system permissions. `jcmd` is not a tool for controlling a JVM remotely over the network: it must run on the same machine as the JVM and, according to Oracle JDK 21, must use the same effective user and group identifiers that were used to launch the JVM.

## 1. What is a PID and why does choosing the right one matter?

A PID (Process ID) is an identifier assigned to a process by the operating system. A JVM running inside a Java process has its own PID. `jcmd` uses this PID to send diagnostic requests to the right JVM.

A PID is not:

- A Java thread ID shown in a thread dump.
- The application's main class name.
- The application's HTTP or JMX port.
- The container's PID on the host when viewed from a different PID namespace.

A process can terminate and its PID can be reassigned by the operating system to another process. Therefore, you should not take a PID from old logs and reuse it after a long period of time. Confirm the process right before attaching, check the main class, and execute the command within the same troubleshooting session.

### 1.1. Listing running JVMs

Basic command:

~~~bash
jcmd -l
~~~

This command lists the PID, main class, and command-line arguments of the JVMs detected by the tool. You can invoke `jcmd` without arguments; the behavior is equivalent to `jcmd -l`.

Illustrative example output:

~~~text
5485 jdk.jcmd/sun.tools.jcmd.JCmd
2125 com.example.orders.OrderApplication
7810 org.example.worker.BatchWorker
~~~

The list may also include the `JCmd` process created by the command you just ran. Do not confuse that PID with the application you want to inspect.

`jcmd -l` may not list JVMs running in a separate Docker process. For containers, check the PID inside the container using an OS tool such as `ps`, then run `jcmd` inside the matching container/PID namespace.

### 1.2. Getting the PID from a Java program itself

From Java 9 onward, `ProcessHandle.current().pid()` returns the PID of the current process. Java 17+ example:

~~~java
public final class ProcessIdDemo {
    public static void main(String[] args) {
        System.out.println("PID=" + ProcessHandle.current().pid());
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 ProcessIdDemo.java
java ProcessIdDemo
~~~

Stdout looks like:

~~~text
PID=12345
~~~

`12345` is only an illustrative PID; the actual value is assigned by the operating system on each run.

### 1.3. Selecting a process by PID or main class

General syntax:

~~~text
jcmd <pid> <command> [options]
jcmd <main-class> <command> [options]
~~~

Example:

~~~bash
jcmd 2125 VM.version
~~~

You can use the main class name:

~~~bash
jcmd com.example.orders.OrderApplication VM.version
~~~

The main class name can match partially or completely. If multiple JVMs share the same main class, targeting by name sends the request to all matching processes. In multi-instance environments, prefer a verified PID.

PID `0` means sending the diagnostic command to all available Java processes:

~~~bash
jcmd 0 VM.version
~~~

This has a very broad scope. Do not use PID `0` for commands that may generate dumps, change configuration, or impact performance unless you intentionally want to apply them to every JVM.

## 2. Access permissions when attaching to a JVM

According to the Oracle JDK 21 `jcmd` documentation, the tool must run:

1. On the same machine as the target JVM.
2. With the same effective user and group identifiers that were used to launch the JVM.

This is a requirement of the local attach mechanism. It does not mean any account can read or control every JVM on the machine.

### 2.1. Checking user identity

On Linux/macOS:

~~~bash
id
ps -o pid=,user=,group=,args= -p 2125
~~~

The `id` command shows the identity of the current terminal; `ps` shows the owner and command line of the target process. If the two processes run under different users, perform the diagnostic operation using the authorized operational account or coordinate with an administrator.

On Windows, check the terminal account and confirm the PID:

~~~powershell
whoami
Get-Process -Id 2125
~~~

`whoami` shows the current account; `Get-Process` confirms that a process with that PID exists. Determining the owner and access permissions of a process may require appropriate administrative tools. Windows also enforces process and pipe access controls. Running the terminal under a different account can cause attach to fail. Do not assume that simply opening a terminal with Administrator privileges allows attaching to every JVM; you must follow the machine's account and access policies.

### 2.2. Attach permissions differ from diagnostic command permissions

After attaching successfully, each diagnostic command may still have its own requirements and impact. For example, `Thread.print` prints stack traces of all threads; `GC.heap_dump` creates a file containing heap data. An account with attach capability can view internal application information.

Treat `jcmd` access as a sensitive operational privilege:

- Grant it only to necessary operational accounts.
- Avoid running under a broadly shared account when a dedicated account can be used.
- Restrict read permissions on directories containing dumps and reports.
- Do not publish command lines, system properties, thread dumps, or heap dumps to public locations.
- Delete or archive diagnostic data according to your organization's retention policy.

## 3. Attach API and the DisableAttachMechanism flag

`jcmd` uses the Attach API mechanism to connect to a running JVM. Attach is enabled by default in the HotSpot JVM, but a process can be launched with the option:

~~~bash
java -XX:+DisableAttachMechanism -jar app.jar
~~~

The `-XX:+DisableAttachMechanism` option disables the mechanism that allows tools to attach. When set, tools such as `jcmd`, `jstack`, `jmap`, and `jinfo` cannot attach to that JVM.

Example error:

~~~text
com.sun.tools.attach.AttachNotSupportedException:
The VM does not support the attach mechanism
~~~

If the process was launched with this flag, running `jcmd` from another terminal cannot re-enable the Attach API because the attach operation itself is disabled. To allow attaching, you need to adjust the startup configuration and restart the JVM following an approved deployment process.

Do not enable attach indiscriminately on every production process. Balance diagnostic needs with your security model and server governance procedures.

### 3.1. Other cases where attach fails

Besides `DisableAttachMechanism`, common causes include:

- The JVM has terminated or the PID no longer exists.
- The PID was taken from a previous run and has been reused.
- `jcmd` is running under a different user/group than the target process.
- The tool is running on the host while the JVM is inside a different container/PID namespace.
- The container does not have a JDK or lacks the `jcmd` executable.
- Operating system policies, sandboxes, or runtimes restrict attach operations.
- The JVM does not support the Attach API or does not provide the diagnostic commands requested by the tool.

A process running in a container does not mean `jcmd -l` from the host will always see it. Verify the correct namespace and account before investigating permission errors.

## 4. Discovering commands supported by the target JVM

The list of diagnostic commands can vary across JVMs, JDK versions, and runtimes. Do not copy a command from another machine and assume the target process supports it as well.

View the list of commands for a process:

~~~bash
jcmd 2125 help
~~~

View the syntax, parameters, and impact of a specific command:

~~~bash
jcmd 2125 help Thread.print
jcmd 2125 help GC.heap_dump
~~~

Example help output for `Thread.print` may look like:

~~~text
Thread.print
Print all threads with stacktraces.

Impact: Medium: Depends on the number of threads.
~~~

The `Impact` section helps estimate the effect of the operation. Check the help output on the exact target process before running a command in production.

### 4.1. Commonly used commands

| Diagnostic command | Purpose | Typical impact in HotSpot JDK 21 |
|---|---|---|
| `VM.version` | Print JVM/JDK version | Low |
| `VM.uptime` | Print how long the JVM has been running | Low |
| `VM.flags` | Print VM flags and current values | Low |
| `VM.command_line` | Print the JVM launch command line | Low |
| `VM.system_properties` | Print system properties | Low |
| `GC.heap_info` | Heap overview information | Medium |
| `Thread.print` | Thread dump with stack traces | Medium, depends on thread count |
| `GC.class_histogram` | Instance statistics by class | High, depends on heap |
| `GC.heap_dump` | Create a heap dump | High; may trigger a full GC by default |

Impact may vary by version and implementation. Obtain the value from `jcmd <pid> help <command>` on the target JVM rather than treating this table as a fixed contract.

Basic inspection examples:

~~~bash
jcmd 2125 VM.version
jcmd 2125 VM.uptime
jcmd 2125 VM.flags
jcmd 2125 GC.heap_info
~~~

Thread dump:

~~~bash
jcmd 2125 Thread.print
~~~

If you need to also print `java.util.concurrent` locks:

~~~bash
jcmd 2125 Thread.print -l
~~~

A heap dump is a heavy operation and can produce a large file:

~~~bash
jcmd 2125 GC.heap_dump filename=/var/tmp/orders-heap.hprof
~~~

Use an absolute path, ensure the JVM user has write permission, and verify that the disk has enough free space. A heap dump may contain passwords, tokens, personal data, and business payloads currently in memory. Protect the file as sensitive production data.

### 4.2. Beware of output containing confidential information

Some read-only commands have low impact, yet their output is still sensitive:

- `VM.command_line` may expose `-D...` parameters or launch arguments containing secrets.
- `VM.system_properties` may print URLs, paths, configuration values, and environment details.
- `Thread.print` may contain usernames, URLs, or data present on the stack.
- `GC.heap_dump` may contain application data currently being processed.

`Impact: Low` does not mean the output can be shared publicly. Impact describes the operational overhead of running the command, not the sensitivity of the data returned.

## 5. Java 17+ hands-on: creating a process to attach to

The following example keeps the JVM running until stopped. The program prints its PID so a second terminal can use that exact PID.

File `JcmdTarget.java`:

~~~java
import java.util.concurrent.CountDownLatch;

public final class JcmdTarget {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("PID=" + ProcessHandle.current().pid());
        System.out.println("Target ready. Run jcmd from another terminal.");

        new CountDownLatch(1).await();
    }
}
~~~

Compile and run in the first terminal:

~~~bash
javac --release 17 JcmdTarget.java
java JcmdTarget
~~~

Stdout looks like:

~~~text
PID=12345
Target ready. Run jcmd from another terminal.
~~~

The PID is the actual process value and is not fixed across runs.

In the second terminal, list JVMs and replace `12345` with the PID printed above:

~~~bash
jcmd -l
jcmd 12345 help
jcmd 12345 VM.version
jcmd 12345 Thread.print -l
~~~

The `VM.version` output starts with something like:

~~~text
12345:
OpenJDK 64-Bit Server VM version 24.0.2+12
JDK 24.0.2
~~~

The exact version depends on the running JDK. Stop the demo program with `Ctrl+C` in the first terminal.

### 5.1. Selecting a process by main class

If only one process is running `JcmdTarget`, you can use:

~~~bash
jcmd JcmdTarget VM.version
~~~

If multiple instances are running the same class, the tool may send the command to all matching processes. Use a specific PID to avoid collecting from or affecting the wrong instance.

## 6. PID and access permissions in Docker/containers

Containers have their own PID namespace. The PID shown inside a container may differ from the PID on the host. Additionally, `jcmd -l` does not list JVMs running in a separate Docker process, as noted by Oracle JDK 21.

The standard approach is to enter the right container and run the tool inside it:

~~~bash
docker exec -it orders-app sh
~~~

Inside the container:

~~~bash
ps -ef
jcmd -l
~~~

Identify the JVM's PID in the container namespace, then run:

~~~bash
jcmd 1 VM.version
~~~

`1` is only accurate if the JVM is actually PID 1 inside the container. If the PID is different, use the PID identified from `ps` or `jcmd -l`.

Prerequisites:

- The image must include the `jcmd` executable (usually requiring a JDK or an appropriate diagnostic image).
- `jcmd` must run in the same container/PID namespace or process environment where the JVM can be attached to.
- The user running `jcmd` must have an identity and permissions compatible with the user running the JVM.
- Container policies must not block attach operations.

If the application uses a minimal runtime image without `jcmd`, follow your organization's approved diagnostic image/sidecar workflow. Do not relax container permissions or run the entire application as root just to work around attach errors.

## 7. jcmd is a local tool, not a remote command

`jcmd` must run on the same machine as the target JVM. It does not accept a hostname, IP address, or JMX port to attach over the network.

If you need to diagnose a server from another machine:

1. Use SSH or your infrastructure management mechanism to access the right host.
2. Run `jcmd` locally on that host under an identity with appropriate permissions.
3. If you cannot run tools on the host, use a remote management solution such as JMX configured with authentication/TLS or a secured monitoring/diagnostic platform.

Do not expose an attach port arbitrarily over the network. The Attach API and `jcmd` are local diagnostic mechanisms; remote management requires its own authentication and protection mechanisms.

## 8. Choosing the right JDK tool

`jcmd` is provided in the JDK's `bin` directory. If a machine has multiple JDKs installed, the `jcmd` found via `PATH` may not belong to the same JDK as the application.

Check the tool path:

On Linux/macOS:

~~~bash
which java
which jcmd
"$JAVA_HOME/bin/jcmd" -h
~~~

On Windows PowerShell:

~~~powershell
where.exe java
where.exe jcmd
& "$env:JAVA_HOME\bin\jcmd.exe" -h
~~~

Oracle notes that the `jcmd`, `jinfo`, `jmap`, and `jstack` tools provided in one JDK are not supported for troubleshooting a JVM from a different JDK version. Choose the tool from the same JDK release/vendor as the target JVM, or follow your organization's support procedures.

Do not confuse `jcmd -h` with `jcmd -version`: the documented CLI syntax for help is `-h`; there is no `-version` flag.

## 9. Common errors and troubleshooting

| Message / situation | Possible cause | How to check |
|---|---|---|
| `java.io.IOException: no such process` | Wrong PID, process exited, or namespace mismatch | Re-run `jcmd -l`/`ps`, confirm current PID |
| `AttachNotSupportedException: The VM does not support the attach mechanism` | Attach disabled or JVM does not support the mechanism | Check startup flags, runtime, and `-XX:+DisableAttachMechanism` |
| `Operation not permitted` / access denied | User/group or OS policy blocks attach | Compare accounts running tool and process; check ACL/container policy |
| `jcmd -l` does not show the app in Docker | JVM is in a separate Docker process/PID namespace | Use `docker exec`, `ps`, and `jcmd` inside the container |
| `jcmd` is not recognized | JDK `bin` is not in `PATH` or only a runtime image is installed | Invoke via `JAVA_HOME/bin/jcmd` or install a diagnostic JDK |
| `Unknown diagnostic command` | Target JVM does not provide that command | Run `jcmd <pid> help` on the exact process |
| Command output differs from documentation | Different JDK/provider/HotSpot version | Use `help <command>` and the tool matching the target JDK |
| Attach times out | JVM is busy, shutting down, or attach socket/OS policy issue | Check process state, retry after confirming the cause |
| Cannot write heap dump | JVM user lacks write permission or disk is full | Use a writable destination directory with sufficient free space |

Compact diagnostic workflow:

1. Confirm the JVM is still running and obtain a fresh PID.
2. Confirm the main class and the user owning the process.
3. Confirm the terminal is in the same host/container/PID namespace.
4. Check `jcmd -h` and `jcmd <pid> help`.
5. Check whether the Attach API was disabled at startup.
6. Check file permissions, temporary directory, container policies, and runtime.
7. Run low-impact commands such as `VM.version` first; only run dumps or histograms after understanding their impact.

## 10. Safe operations checklist

- [ ] Identify a fresh PID from `jcmd -l`, `ps`, or the application's own logs.
- [ ] Cross-check the PID against the target main class/instance.
- [ ] Use a specific PID; avoid PID `0` or a main class selector that could match multiple processes.
- [ ] Run `jcmd` on the same host and with the matching user/group required for attach.
- [ ] For Docker, identify the PID in the right namespace and run the tool inside the container.
- [ ] Check for `-XX:+DisableAttachMechanism` if attach is not supported.
- [ ] Use the JDK tool matching the target JVM version.
- [ ] Run `help <command>` to review syntax, permissions, and impact before executing.
- [ ] Assess impact before running `GC.class_histogram`, `GC.heap_dump`, or other heavy commands.
- [ ] Protect command lines, system properties, thread dumps, and heap dumps as sensitive data.
- [ ] Store reports/dumps in a location with restricted access and a clear retention policy.

## 11. Key takeaways

The PID helps `jcmd` identify the target JVM, but a PID alone is not enough to guarantee a successful attach. The tool must run on the same machine and with the same effective user/group as the JVM; the process must allow the Attach API, and the OS/container environment must permit access.

Start with `jcmd -l`, verify the PID and main class, and then use `jcmd <pid> help` to see the commands supported by that specific JVM. Use low-impact commands first, evaluate sensitive output, and only generate histograms or heap dumps once disk space, write permissions, and data protection procedures are in place.

References:

- [The jcmd Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [The java Command — Advanced Serviceability Options, Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [Java SE 21 Troubleshooting Guide — The jcmd Utility](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-guide.pdf)
- [ProcessHandle API — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessHandle.html)