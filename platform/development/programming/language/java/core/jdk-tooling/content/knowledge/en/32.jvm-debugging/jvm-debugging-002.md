# JDWP: Java Debug Wire Protocol

**Java Debug Wire Protocol (JDWP)** is the communication protocol between a debugger and a Java Virtual Machine (JVM) running the application to be debugged (the debuggee). JDWP allows the debugger to query information about classes, threads, stack frames, objects, and variables; set breakpoints; receive events when breakpoints or exceptions occur; step through code; modify certain runtime values; and control suspending/resuming the JVM.

JDWP is one layer in the **Java Platform Debugger Architecture (JPDA)**. It is the foundation that enables JDB, IntelliJ IDEA, Eclipse, and compatible debuggers to connect to a local or remote JVM. To use JDWP on HotSpot, the JVM must be started with the debug agent, typically using the `-agentlib:jdwp` option.

## 1. Where Does JDWP Fit in the JPDA Architecture?

JPDA has three main layers:

| Layer | Full Name | Role |
| --- | --- | --- |
| JVM TI | Java Virtual Machine Tool Interface | Native interface exposed by the JVM to inspect state and control debugging operations |
| JDWP | Java Debug Wire Protocol | Defines packets, commands, replies, and events between the debugger and the debuggee |
| JDI | Java Debug Interface | High-level Java API for writing debuggers and working with breakpoints, threads, stack frames, and objects |

In Oracle's reference implementation:

- JVM TI is implemented inside the VM.
- The JDWP back-end runs on the debuggee side, receiving requests from the debugger and invoking JVM TI functions.
- The JDWP front-end translates debugger operations into JDWP packets.
- JDI is the API used by JDB and many IDEs to interact with the front-end.

For example, when you inspect a local variable in an IDE:

1. The IDE calls JDI to request the variable's value in a stack frame.
2. The front-end translates the request into a JDWP command.
3. The JDWP back-end receives the packet and queries the JVM through JVM TI.
4. The result is packaged into a JDWP reply and returned to the debugger.
5. The IDE displays the variable's value.

When a breakpoint is hit, the VM sends an event through the back-end; the debugger receives the event and displays the suspended location.

**Distinguishing the terms:**

- JPDA is the overall architecture.
- JDWP is the protocol for transmitting debug data.
- JVM TI is the native interface on the VM side.
- JDI is the API on the debugger side.
- JDB is the sample command-line debugger built on JDI.
- The JDWP agent is the component loaded into the target JVM to support debug communication.

JDWP is optional; some JVM implementations may not provide this protocol or agent.

## 2. Connection Mechanism and JDWP Handshake

JDWP transmits commands, replies, and events over a transport. The transport defines how the two processes exchange bytes; JDWP defines the format and meaning of the data.

When a connection is established, the debugger and the VM perform a handshake:

- The debugger sends the 14-byte ASCII string `JDWP-Handshake`.
- The VM replies with the exact same string.
- Only after the handshake do the two sides exchange JDWP packets.

There are two basic packet types:

- **Command packet:** The debugger requests information or controls the VM; the VM can also send command/event packets to notify the debugger of events.
- **Reply packet:** Returns the success/error status and corresponding data for a command.

Examples of command sets in JDWP:

- VirtualMachine: list classes/threads, suspend, resume, exit, and query capabilities.
- ReferenceType/Method: query fields, methods, source line tables, and variable tables.
- StackFrame: read or modify values in a frame.
- EventRequest: register or clear breakpoints, exception events, and other events.
- ThreadReference: inspect state, stack frames, monitors, and suspend/resume threads.
- ObjectReference/ClassType: read fields, write fields, invoke methods, or create objects when supported by the VM.

The protocol includes events for breakpoints, single-stepping, exceptions, thread start/end, and other runtime changes. Not every capability is available on every JVM; the debugger should check the target VM's capabilities.

## 3. Loading the JDWP Agent into the JVM

On modern HotSpot JDKs, use:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 -jar app.jar
```

General syntax:

```text
-agentlib:jdwp=<name1>=<value1>,<name2>=<value2>,...
```

Options:

| Option | Meaning |
| --- | --- |
| `-agentlib:jdwp` | Loads the JDWP agent into the JVM |
| `transport` | Selects the transport between the debugger and the JVM |
| `server` | Selects which side listens for the connection |
| `address` | Transport address |
| `suspend` | Determines whether the JVM pauses before running the application |
| `timeout` | Connection wait timeout in milliseconds |
| `allow` | Filters client addresses allowed to connect to the socket server |
| `onthrow` | Initializes JDWP only when a specified exception class is thrown |
| `onuncaught` | Initializes JDWP only when an uncaught exception occurs |
| `launch` | Launches a debugger stub program after JDWP initializes; often combined with onthrow/onuncaught |

Check the actual options supported by your JDK:

```bash
java -agentlib:jdwp=help
jdb -help
jdb -listconnectors
```

JDK 24 still supports the legacy `-Xrunjdwp` interface, but warns that it will be removed in a future release. Use `-agentlib:jdwp` for new configurations.

## 4. Understanding server, transport, address, and suspend

### server=y and server=n

`server=y` means the target JVM opens an endpoint and waits for the debugger to connect. This is the common setup when an IDE attaches to an application already started with the debug agent.

`server=n` means the target JVM actively initiates a connection to a listening debugger. This configuration is useful when the network or firewall only allows outbound connections from the application host to the development machine.

Note: `server=y` refers to the client/server role of the JDWP connection; it does not mean the application must be a web server.

### Transport

| Transport | How It Works | Scope |
| --- | --- | --- |
| `dt_socket` | TCP/IP socket | Same machine or remote machine |
| `dt_shmem` | Windows shared memory | Two processes on the same Windows machine |

`dt_socket` supports both IPv4 and IPv6. A socket address has the form `<host>:<port>`. If the host is omitted, the transport uses loopback; host `*` in server mode listens on all network interfaces.

`dt_shmem` is only available in the reference implementation on Windows and cannot be used for remote debugging over a network.

### address

Example listening on loopback:

```bash
-agentlib:jdwp=transport=dt_socket,server=y,address=127.0.0.1:5005
```

Example listening on all interfaces:

```bash
-agentlib:jdwp=transport=dt_socket,server=y,address=*:5005
```

In JDK 24, if the server uses a port-only address such as `address=5005`, the socket transport defaults to listening on loopback. Using an explicit loopback address makes the configuration clearer and reduces confusion across environments.

If `server=y` and `address` is omitted, the agent can select an available transport address and print it to standard output. This is useful when a dynamic port is needed.

### suspend

| Value | Behavior |
| --- | --- |
| `suspend=y` | Pauses the VM at the VMStart event before the main class is loaded/run; resumes after the debugger connects and sends resume |
| `suspend=n` | VM runs immediately; the debugger can attach while the application is running |

The default for the JDWP agent is `suspend=y`.

Use `suspend=y` when you need startup breakpoints or need to debug initialization failures. If no debugger connects, the application remains suspended; you can configure `timeout` to limit the wait time.

Use `suspend=n` when you do not want the application to wait for a debugger. However, breakpoints set after a method has already executed cannot retroactively catch earlier invocations.

## 5. Common Configuration Examples

### Local debugging, pausing before main

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 -cp out DebugTarget
```

The JVM opens a loopback socket and waits for the debugger. The application does not run `main` until the debugger connects and resumes the VM.

### Local debugging without pausing startup

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -cp out DebugTarget
```

The application starts running immediately. Attach the debugger afterward and set breakpoints for subsequent executions.

### Limiting debugger wait time

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005,timeout=30000 -cp out DebugTarget
```

`timeout=30000` sets a 30-second timeout for transports that support the timeout option. If the timeout expires before a debugger attaches, the agent may terminate the connection or the VM depending on the transport's behavior.

### Restricting allowed client addresses

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005,allow=127.0.0.1+192.168.1.0/24 -cp out DebugTarget
```

`allow` applies to `dt_socket` when `server=y`. The IP/subnet list is separated by `+`. This is a source-address filter, not debugger authentication.

### Debugger listening, JVM actively connecting

Debugger terminal:

```bash
jdb -connect com.sun.jdi.SocketListen:port=5005
```

Application terminal:

```bash
java -agentlib:jdwp=transport=dt_socket,server=n,address=127.0.0.1:5005,suspend=y -cp out DebugTarget
```

In this setup, the debugger listens and the JVM initiates the connection. When deploying remotely, make sure the connection direction aligns with your firewall and network policies.

## 6. Connecting with JDB

JDB is the command-line debugger included with the JDK. You can use JDB to launch a program or attach to a JVM already running with the JDWP agent.

View supported connectors:

```bash
jdb -listconnectors
```

Common connectors:

- `com.sun.jdi.SocketAttach`: attach to a JVM over a TCP socket.
- `com.sun.jdi.SocketListen`: wait for a JVM to connect over a TCP socket.
- `com.sun.jdi.SharedMemoryAttach`: attach over Windows shared memory.
- `com.sun.jdi.SharedMemoryListen`: listen on Windows shared memory.
- `com.sun.jdi.ProcessAttach`: attach to a JVM by PID if supported by the target.
- `com.sun.jdi.CommandLineLaunch`: JDI connector that launches a new JVM.

Example of attaching over a socket:

```bash
jdb -connect com.sun.jdi.SocketAttach:hostname=127.0.0.1,port=5005
```

JDB also has a shorthand syntax:

```bash
jdb -attach 5005
```

However, the default connector for `jdb -attach` is platform-dependent: the reference implementation uses shared memory on Windows and sockets on Linux/macOS. If the target is using `dt_socket` on Windows, specify `com.sun.jdi.SocketAttach` explicitly as shown above.

To have JDB launch a new program:

```bash
jdb -sourcepath src -classpath out DebugTarget
```

With this approach, JDB manages launching the target and can pause the program before the first instruction of the main class so you can set breakpoints.

## 7. Common JDB Commands

| Command | Purpose |
| --- | --- |
| `stop at Class:line` | Set a breakpoint at a source line |
| `stop in Class.method` | Set a breakpoint at method entry |
| `clear Class:line` | Remove a breakpoint at a line |
| `where` | Print the stack trace of the current thread |
| `where all` | Print stack traces of all threads |
| `threads` | List threads |
| `thread <id>` | Select a thread as the current thread |
| `locals` | Print method arguments and local variables |
| `print expression` | Evaluate and print an expression |
| `dump expression` | Print object details |
| `set variable = expression` | Modify the value of an allowed variable/field |
| `step` | Step into the next method call |
| `next` | Step over the current method call, stopping at the next line in the frame |
| `step up` | Run until the current method returns to its caller |
| `stepi` | Step by bytecode instruction |
| `cont` | Continue after a breakpoint |
| `resume` | Resume a thread or the entire VM; defaults to all threads |
| `catch ExceptionClass` | Stop when the specified exception is thrown |
| `ignore ExceptionClass` | Stop tracking a previously registered exception |
| `watch all Class.field` | Watch field reads and writes if supported by the VM |
| `redefine Class file.class` | Reload a class definition if supported by the VM |

When the VM has just attached at VMStart and has no stack frame yet, use `resume` to let all threads run. After stopping at a breakpoint, use `cont` to resume execution.

To view command help:

```text
help
```

Some operations depend on VM capabilities, breakpoint types, and debug information present in the class files.

## 8. Java 17 Hands-On Example: Setting Breakpoints and Inspecting Variables with JDWP

The following example sums two numbers, doubles the result, and prints it to the console.

Project structure:

```text
project/
  src/
    DebugTarget.java
  out/
```

File `src/DebugTarget.java`:

```java
public final class DebugTarget {
    private DebugTarget() {
    }

    public static void main(String[] args) {
        int left = 7;
        int right = 5;
        int result = calculate(left, right);
        System.out.println("result=" + result);
    }

    static int calculate(int left, int right) {
        int sum = left + right;
        int doubled = sum * 2;
        return doubled;
    }
}
```

Compile with debug information:

```bash
mkdir out
javac --release 17 -g -d out src/DebugTarget.java
```

The `-g` option instructs the compiler to generate debug information such as source file, line number, and local variable tables. This helps the debugger map bytecode back to source lines and read local variables. Without a local variable table, the `locals` command may not display local variables.

### Terminal A: start the JVM with JDWP

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 -cp out DebugTarget
```

Initial output:

```text
Listening for transport dt_socket at address: 5005
```

The JVM is waiting for the debugger; `main` has not executed yet.

### Terminal B: attach with JDB

```bash
jdb -sourcepath src -connect com.sun.jdi.SocketAttach:hostname=127.0.0.1,port=5005
```

At the JDB prompt, set a breakpoint at line 11, then resume the VM:

```text
stop at DebugTarget:11
resume
```

The JVM runs up to the line:

```java
int doubled = sum * 2;
```

When the breakpoint hits, inspect the stack and variables:

```text
where
locals
print sum
```

Key output:

```text
Breakpoint hit: "thread=main", DebugTarget.calculate(), line=11
11            int doubled = sum * 2;

[1] DebugTarget.calculate (DebugTarget.java:11)
[2] DebugTarget.main (DebugTarget.java:6)

Method arguments:
left = 7
right = 5

Local variables:
sum = 12

sum = 12
```

Step over the `doubled` assignment:

```text
next
print doubled
```

Output:

```text
Step completed: "thread=main", DebugTarget.calculate(), line=12
12            return doubled;

doubled = 24
```

Continue to let the program finish:

```text
cont
```

Application output:

```text
result=24
```

This debugging flow was tested on HotSpot JDK 24.0.2 with source compiled using `javac --release 17 -g`. Ports and BCI/thread details may vary across runs; the variable values and computed result in the example are deterministic.

## 9. Breakpoints, Stepping, and Exceptions

### Line breakpoints

```text
stop at DebugTarget:11
```

JDB sets the breakpoint at the first instruction corresponding to an executable source line. A line with no corresponding bytecode may not produce a breakpoint as expected.

### Method breakpoints

```text
stop in DebugTarget.calculate
```

If a method is overloaded, specify the parameter types:

```text
stop in DebugTarget.calculate(int,int)
```

### Step into and step over

- `step` enters the method called on the next line.
- `next` executes the method call without entering it.
- `step up` runs until the current method returns to its caller.
- `stepi` steps by bytecode instruction.

Choose the command based on what you want to inspect: use `step` to examine logic inside the called method; use `next` to follow the flow of the current method.

### Breaking on exceptions

Register an exception breakpoint:

```text
catch java.lang.IllegalArgumentException
```

When the exception is thrown, JDB pauses at the throw site so you can inspect the stack and variables. Use `ignore` to unregister the exception.

Exception breakpoints can catch handled exceptions or only uncaught ones depending on the `catch` syntax and configuration. Check `help catch` in your JDB version.

## 10. Compiling Debug Information and Source Mapping

JDWP transmits runtime information from the VM; displaying source lines and local variables depends on metadata stored in the class files.

Compile code that needs debugging with:

```bash
javac -g -d out src/DebugTarget.java
```

Types of debug information:

- Source file attribute: the source file name.
- Line number table: maps bytecode indices to source lines.
- Local variable table: names and scopes of local variables.
- Local variable type table: generic type information when generated.

If you use Maven or Gradle, check the compiler configuration to ensure debug information is retained. Some optimized builds or obfuscation steps may strip metadata or rename classes and methods.

When attaching to a remote JVM, use source code from the exact same revision/build as the running class files. If the source differs, breakpoint lines may be misaligned or JDB may fail to locate the corresponding position.

## 11. JDWP with IDEs

Java IDEs typically integrate JDI and JDWP in their Debug / Remote Debug features.

General workflow:

1. Start the application with the JDWP agent.
2. Choose the transport and host/port.
3. Create a Remote JVM Debug configuration in the IDE.
4. Select the source/module matching the running binary.
5. Attach the debugger.
6. Set breakpoints and trigger the request or execution path to investigate.
7. Inspect Variables, Watches, Frames, Threads, and Console.
8. Resume or detach when finished.

IDEs provide a richer visual interface than JDB, but they use the same underlying connection architecture. If the IDE reports a connection failure, check the JDWP agent, transport, port, firewall, and connector before investigating breakpoints.

## 12. Debugging Virtual Threads

Modern JDKs support virtual threads. When an application creates a very large number of virtual threads, a debugger must track many threads/events and can become overwhelmed.

In JDK 24:

- By default, JDB does not track every virtual thread from the moment it is created.
- `jdb -trackallthreads` tells JDB to track virtual threads as they are created.
- The JDWP agent provides `includevirtualthreads=y` to include virtual threads in the thread list requested by the debugger.
- Virtual threads created before the debugger attaches may not appear in the list known to the agent.
- Tracking all virtual threads can introduce overhead or overload the debugger when thread counts are very high.

Example:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,includevirtualthreads=y,address=127.0.0.1:5005 -cp out DebugTarget
```

And:

```bash
jdb -trackallthreads -connect com.sun.jdi.SocketAttach:hostname=127.0.0.1,port=5005
```

Only enable full tracking when investigating issues involving virtual threads. For applications with hundreds of thousands or millions of virtual threads, consider narrowing the scope of observation.

## 13. JDWP Limitations and Runtime Behavior

JDWP is a debug control protocol, not a profiler or monitoring system.

Key limitations:

- Not every JVM supports the JDWP agent or all JDWP capabilities.
- The debugger can read local variables only if the class file contains a local variable table.
- Line breakpoints depend on the line number table and actual bytecode.
- JIT optimizations, inlining, and code generation can make stepping/source mapping differ from reading source sequentially.
- Class redefinition is constrained by VM capabilities; standard HotSwap does not allow arbitrarily adding/removing fields or methods or changing the class hierarchy.
- JDWP focuses on Java-level debugging. Native code requires an appropriate native debugger.
- Suspending threads/VMs alters application timing; race conditions or timeouts may disappear or behave differently while debugging.
- A breakpoint that suspends the entire VM can cause requests, lock owners, heartbeats, or health checks to stall.
- Attaching to a production JVM can impact latency and stability; have a clear plan and debugging scope.

For continuous performance analysis, allocations, lock contention, or GC, use JFR/JMC and profilers. JDWP is primarily meant for inspecting logic, state, and execution flow at specific points.

## 14. Security When Enabling JDWP

JDWP allows a debugger to read JVM state and control the process. The protocol has commands to read/write fields, read/write stack frames, invoke methods, suspend/resume, and terminate the VM. Treat the JDWP port as a high-privilege administrative interface.

Safe practices:

- Enable JDWP only when debugging is genuinely needed.
- Prefer binding to loopback, e.g., `address=127.0.0.1:5005`.
- Never use `address=*:5005` on a public network.
- If you must expose a network interface, restrict sources using `allow`, firewalls, and network policies.
- `allow` only filters source addresses; it is not authentication.
- For remote debugging, prefer an SSH tunnel or VPN instead of exposing the port directly.
- Disable the debug agent and close tunnels once investigation is complete.
- Do not put sensitive information in command-line arguments or debug logs.
- Do not leave a debugger paused at a breakpoint in an environment serving user traffic.
- Grant debug access only to users authorized to access the process and runtime data.

Example SSH tunnel from a development machine:

```bash
ssh -L 5005:127.0.0.1:5005 user@debug-host
```

If the remote JVM is listening on loopback on the host, the tunnel forwards local port 5005 to port 5005 on the host's loopback. The IDE/JDB on the development machine connects to `127.0.0.1:5005`.

Do not treat JDWP as an authenticated or end-to-end encrypted protocol. Use an external network boundary to protect the connection.

## 15. Common Errors and Troubleshooting

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `Connection refused` | JVM agent not enabled, wrong port, or agent not listening yet | Check startup command, PID, host, and port |
| JDB attaches but breakpoint is not hit | Breakpoint set after the method already ran, or class not loaded yet | Use `suspend=y` to catch startup; set breakpoint before the next invocation |
| `No source found` | Missing source path or source does not match revision | Use `-sourcepath` and matching source revision |
| Cannot inspect local variables | Class file lacks a local variable table | Recompile with `javac -g` or enable debug info in the build |
| Breakpoint line is misaligned | Source does not match binary, or line has no executable bytecode | Verify commit/build and line number table |
| `Unable to attach` | Wrong transport, process permissions, or incompatible connector | Use the connector matching `dt_socket`/`dt_shmem` |
| `jdb -attach` shared memory error on Windows | `-attach` defaults to shared memory while target uses socket | Use `-connect com.sun.jdi.SocketAttach:hostname=...,port=...` |
| JVM fails to start with JDWP | Invalid agent options or invalid port/address | Check `java -agentlib:jdwp=help` and startup logs |
| Application does not run after enabling debug | `suspend=y` is waiting for a debugger to attach | Attach the debugger and run `resume`; consider setting `timeout` |
| Debugger does not see virtual threads | Not all virtual threads are tracked by default | Consider `-trackallthreads` and `includevirtualthreads=y` |
| Breakpoints cause request timeouts | Thread/VM is suspended while requests are in flight | Use conditional/thread-scoped breakpoints, minimize pause time, and debug in an appropriate environment |
| Cannot hot-swap class structure changes | VM does not support schema changes during redefine | Restart the application or use a tool with appropriate reload support |

## 16. Workflow for Debugging a JVM with JDWP

1. Identify the issue and the target JVM to investigate.
2. Verify that the JDK/JVM supports JDWP.
3. Compile with source/line/local debug information.
4. Choose the transport, server/client direction, and address.
5. Choose `suspend=y` to catch startup or `suspend=n` if the application must run immediately.
6. Enable the agent with `-agentlib:jdwp`.
7. Attach JDB/IDE using the connector matching the transport.
8. Set breakpoints or exception breakpoints.
9. Use stack, locals, print, watch, and stepping to inspect state.
10. Resume the application as soon as observation is complete.
11. Detach/close the debugger and disable the JDWP agent when no longer needed.
12. Record the JDK version, build, breakpoints, observed data, and conclusions.

## 17. Key Takeaways

- JDWP is a command/reply/event protocol between a debugger and a target JVM.
- JPDA consists of JVM TI, JDWP, and JDI; JDB/IDEs typically use JDI.
- `-agentlib:jdwp` loads the debug agent into the JVM.
- `transport=dt_socket` uses TCP; `dt_shmem` uses Windows shared memory.
- `server=y` makes the JVM wait for a debugger; `server=n` makes the JVM connect to a debugger listener.
- `suspend=y` pauses the VM before the main class runs; `suspend=n` lets the application run immediately.
- `address` specifies the endpoint; `allow` filters connection sources for a socket server.
- JDK 24 on Windows uses shared memory as the default connector for `jdb -attach`; use `SocketAttach` explicitly when the target uses sockets.
- `stop`, `where`, `locals`, `print`, `step`, `next`, and `cont` are common JDB commands.
- `javac -g` provides the debugger with line number tables and local variable tables.
- Virtual threads require dedicated tracking options when full visibility is needed.
- JDWP provides powerful control and alters timing; enable it only within trusted networks and for as long as needed.

Understanding JDWP helps you connect a debugger to the right JVM, pause at the right location, inspect thread/variable state, and trace execution flow. Combining breakpoints, stack frames, local variables, and stepping lets you systematically pinpoint logic errors.

## References

- [Java Platform Debugger Architecture — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/jpda/jpda.html)
- [Connection and Invocation Details — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/jpda/conninv.html)
- [The jdb Command — JDK 24 Tool Specifications](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdb.html)
- [Java Debug Wire Protocol Details — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/jdwp/jdwp-protocol.html)
