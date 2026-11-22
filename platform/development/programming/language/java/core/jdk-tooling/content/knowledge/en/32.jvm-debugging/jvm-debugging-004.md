# Remote Java Debugging: Connecting a Debugger to a JVM on Another Machine

**Remote debugging** allows a debugger running on a development machine to connect to a JVM running on another machine, in a container, or in a test environment. Developers can set breakpoints, pause execution, inspect stack traces, read variables, step through code, and resume execution without running the application directly inside an IDE on the target machine.

In Java, remote debugging typically uses the **Java Platform Debugger Architecture (JPDA)**, the **Java Debug Wire Protocol (JDWP)**, and a TCP socket transport. You can use the debugger in IntelliJ IDEA, Eclipse, Visual Studio Code, or the JDK command-line tool `jdb`.

## 1. What is remote debugging used for?

Remote debugging is useful when an application only reproduces a bug in a production-like environment, integration server, container, or virtual machine where a developer cannot open an IDE directly.

A remote debugging session helps you:

- Pause the program at a specific line of code or at the start of a method.
- Inspect the call stack to see the invocation flow leading to the current location.
- Read the values of local variables, arguments, fields, and expressions.
- Use step into, step over, and step out to trace the execution flow.
- Pause when an exception is thrown.
- Inspect threads, JVM state, and the conditions causing a failure.
- Resume or terminate the debug session once the root cause is found.

Remote debugging is an interactive control session. When the debugger suspends a thread or the entire JVM at a breakpoint, the application may temporarily stop processing requests. Therefore, you should choose an appropriate time, scope, and environment.

## 2. JPDA, JDWP, and JDI architecture

JPDA is Java's standard architecture for debuggers. It consists of the following main layers:

| Component | Role |
|---|---|
| JVM TI (JVM Tool Interface) | Low-level interface for tools to observe and control JVM behavior. |
| JDWP (Java Debug Wire Protocol) | Protocol for exchanging commands and events between the target JVM being debugged and the debugger. |
| JDI (Java Debug Interface) | High-level Java API for debuggers to set breakpoints, read variables, control threads, and query the target VM. |
| Debugger frontend | The tool used by the developer, such as JDB or the built-in debugger in an IDE. |
| JDWP agent | Component running inside the target JVM that connects the JVM to the debugger over the selected transport. |

Overall communication flow:

~~~text
IDE / jdb
   |
   | JDI
   v
Debugger connector
   |
   | JDWP over transport
   v
JDWP agent in the target JVM
   |
   | JVM TI
   v
Running Java application
~~~

JDWP is not a UI tool; it is the protocol sitting between the debugger and the JVM. JDI provides the API for the debugger; IDEs typically use JDI to perform debugging operations.

## 3. Two ends of a remote debug session

There are two processes:

- **Debuggee:** The JVM running the application to be inspected.
- **Debugger:** The IDE or `jdb` connecting to the debuggee.

With TCP sockets, one end must open a port and wait for a connection while the other end actively initiates the connection. There are two setups:

1. The target JVM listens, and the debugger connects to it.
2. The debugger listens, and the target JVM actively connects to the debugger.

The first approach is common for IDE remote attach. The second approach is useful when the target can make outbound connections, but the debugger cannot receive direct inbound connections from the target's network.

Both ends must agree on the transport, address, and port. If one end uses socket transport and the other uses shared memory, the connection will fail.

## 4. Enabling JDWP when launching the target JVM

To allow the JVM to accept debugger connections over TCP, add the agent option to the launch command:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 -jar app.jar
~~~

Meaning of each option:

| Option | Meaning |
|---|---|
| `-agentlib:jdwp` | Loads the JDWP agent into the target JVM. |
| `transport=dt_socket` | Uses the TCP socket transport. |
| `server=y` | The target JVM opens a socket and waits for the debugger to connect. |
| `suspend=y` | Pauses the JVM before running the main class until the debugger attaches. |
| `address=127.0.0.1:5005` | Listens on the target machine's loopback interface, port 5005. |
| `timeout` | Connection wait timeout in milliseconds; applicability depends on the transport. |

Port 5005 is just a common example, not a mandatory fixed port. Choose a port not used by another process and open the appropriate port along the required network path.

You can view the JDWP agent help for your current JDK:

~~~bash
java -agentlib:jdwp=help -version
~~~

Use `-agentlib:jdwp` on modern JDKs. The older `-Xrunjdwp` syntax may still appear in legacy documentation, but it is deprecated.

## 5. Choosing suspend=y or suspend=n

`suspend` determines whether the target JVM waits for the debugger before starting execution.

| Value | Behavior | When to use |
|---|---|---|
| `suspend=y` | The JVM pauses before running the main class, waiting for the debugger to connect. | When you need to set breakpoints before the application executes its first line of code. |
| `suspend=n` | The JVM starts running immediately; the debugger can attach later. | For long-running applications where you need to connect when an issue occurs. |

Example waiting for the debugger before running:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 -cp out com.acme.RemoteDebugDemo
~~~

Example where the application continues running while waiting for a debugger:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar app.jar
~~~

`suspend=y` is the default for the JDWP agent. If enabled without a debugger connecting, the application will hang during startup. For services that need to keep handling requests, consider `suspend=n` and set breakpoints after attaching.

## 6. Choosing the bind address and restricting allowed IPs

The socket address determines which network interface accepts connections:

~~~bash
# Accept connections only from the target machine itself
-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005

# Listen on all network interfaces
-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005
~~~

The `127.0.0.1` address is only reachable from the target machine itself. Using `*` makes the socket listen on all network interfaces, so the network path must be tightly controlled.

With `server=y` and `dt_socket`, JDWP provides the `allow` option to restrict which source IP addresses or subnets are permitted to connect:

~~~bash
-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005,allow=192.0.2.10
~~~

You can specify multiple addresses/subnets separated by `+`, for example:

~~~text
allow=192.0.2.10+198.51.100.0/24
~~~

Replace the example addresses with the debugger's actual IP or an approved network range. `allow` is an additional source-connection filter; it does not replace a firewall, VPN, or authenticated tunnel.

## 7. Connecting the debugger to a listening JVM

Once the target JVM starts with `server=y`, the debugger connects to the target's host and port.

With JDB on Linux or macOS, the default socket connector is typically selected with:

~~~bash
jdb -attach app-server.example.com:5005
~~~

Where:

- `app-server.example.com` is the hostname or IP of the machine running the JVM.
- `5005` is the JDWP port the target is listening on.

You can pass the source path so JDB can locate Java source files:

~~~bash
jdb -sourcepath src -attach app-server.example.com:5005
~~~

### Note on Windows

On Windows, JDB's default connector may use the shared memory transport. When the target is listening via a TCP socket, explicitly select the socket connector:

~~~bash
jdb -connect com.sun.jdi.SocketAttach:hostname=app-server.example.com,port=5005
~~~

If debugging on the same machine:

~~~bash
jdb -connect com.sun.jdi.SocketAttach:hostname=127.0.0.1,port=5005
~~~

`SocketAttach` selects the JDI connector for TCP. This is the explicit way to use sockets on Windows and avoid confusion with the shared memory connector.

## 8. Reverse connection: debugger listens

In some networks, the target can make outbound connections to the developer's machine, but cannot accept inbound connections. In that case, have the debugger listen first:

~~~bash
jdb -connect com.sun.jdi.SocketListen:port=5006
~~~

Launch the target JVM with `server=n` so the target actively connects to the debugger:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=n,suspend=y,address=127.0.0.1:5006 -cp out com.acme.RemoteDebugDemo
~~~

In this mode:

- JDB opens a listener on port 5006.
- The target JVM connects to the debugger's address.
- Once connected, JDB starts the debug session.
- `suspend=y` still keeps the application paused until the debugger resumes it.

When the debugger is on a different machine, replace `127.0.0.1` with an address on the debugger machine that the target can reach. Open the firewall in the appropriate connection direction. Reverse connection changes the connection direction, but it does not provide encryption or authentication on its own.

## 9. Using an SSH tunnel for secure debugging over a network

A common approach is to keep JDWP listening only on the target machine's loopback interface and use SSH port forwarding.

On the server, launch the JVM:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar app.jar
~~~

On the developer machine, create the tunnel:

~~~bash
ssh -N -L 5005:127.0.0.1:5005 user@remote-host
~~~

Keep the SSH terminal open throughout the debug session. The tunnel forwards connections from port 5005 on the developer machine to port 5005 on the server's loopback interface over SSH.

Then configure your IDE or JDB to connect to:

~~~text
Host: 127.0.0.1
Port: 5005
Transport: Socket
~~~

Example with JDB on Windows:

~~~bash
jdb -connect com.sun.jdi.SocketAttach:hostname=127.0.0.1,port=5005
~~~

SSH provides authentication and encryption for the transport. The target JVM does not need to expose JDWP on a public network interface.

## 10. Remote debugging with an IDE

Popular Java IDEs all provide a **Remote JVM Debug** or **Attach to Remote JVM** mode. Menu names may vary by version, but the connection details typically include:

- Hostname or IP of the target JVM.
- JDWP port.
- Transport, usually Socket.
- Source/project matching the running bytecode.

General workflow:

1. Build the application with debug information.
2. Launch the target JVM with the JDWP agent.
3. Set up an SSH tunnel, VPN, or network route if needed.
4. Create a remote attach configuration in the IDE.
5. Enter the host/port reachable by the IDE.
6. Select the source code matching the exact version running on the target.
7. Set breakpoints, then attach.
8. Resume the application and inspect state when a breakpoint is hit.

If the IDE reports that it is connected but breakpoints do not pause execution, verify that the source code and bytecode come from the same build/commit, and check that line number information is present in the class files.

## 11. Preparing source code and debug information

The debugger needs to map the running bytecode to the corresponding source code. When compiling with `javac` in this example, use:

~~~bash
javac -g --release 17 -d out src/com/acme/RemoteDebugDemo.java
~~~

`-g` instructs the compiler to include debug information such as line numbers and local variable information. If the build uses `-g:none` or the packaging step strips debug metadata:

- Line-based breakpoints may fail to set or fail to match.
- `locals` may not display local variables.
- The IDE may report a source mismatch or only display bytecode.

Keep the source code from the exact commit/build that was deployed. If the target runs a JAR built from a different commit, line numbers may shift and the debugger may display code that does not match actual behavior.

## 12. Common JDB commands

Once connected, JDB displays a prompt and accepts debug commands:

| Command | Function |
|---|---|
| `stop at ClassName:Line` | Sets a breakpoint at a source line. |
| `stop in ClassName.method` | Sets a breakpoint in a method. |
| `clear ClassName:Line` | Removes the breakpoint at a line. |
| `cont` | Resumes execution. |
| `step` | Steps into the method called on the next line. |
| `next` | Steps over the next line without entering method calls. |
| `step up` | Runs until exiting the current stack frame. |
| `locals` | Displays arguments and local variables in the current frame if debug information is available. |
| `print expression` | Evaluates and prints a Java expression. |
| `dump expression` | Prints detailed object or value information. |
| `where` | Displays the call stack of the current thread. |
| `where all` | Displays stack traces of all threads. |
| `threads` | Lists threads known to the debugger. |
| `catch ExceptionClass` | Pauses when an exception of the specified type is thrown. |
| `ignore ExceptionClass` | Stops tracking an exception previously registered with `catch`. |
| `quit` | Ends the JDB session. |

Example:

~~~text
stop at com.acme.RemoteDebugDemo:8
cont
locals
print attempt
next
where
cont
~~~

`locals` and `print` depend on the paused frame, debug metadata, and variable scope. Not every variable can be read at every line or in every frame.

## 13. Complete example: remote debugging a Java 17+ application

Create the project:

~~~text
remote-debug-demo/
├── src/
│   └── com/
│       └── acme/
│           └── RemoteDebugDemo.java
└── out/
~~~

File `src/com/acme/RemoteDebugDemo.java`:

~~~java
package com.acme;

public class RemoteDebugDemo {
    public static void main(String[] args) throws InterruptedException {
        int attempt = 0;
        System.out.println("REMOTE_DEBUG_READY");

        for (int i = 1; i <= 3; i++) {
            attempt += i;
            System.out.println("attempt=" + attempt);
            Thread.sleep(500);
        }

        System.out.println("REMOTE_DEBUG_DONE=" + attempt);
    }
}
~~~

### Step 1: Compile

From the root directory:

~~~bash
javac -g --release 17 -d out src/com/acme/RemoteDebugDemo.java
~~~

### Step 2: Launch the target JVM waiting for the debugger

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 -cp out com.acme.RemoteDebugDemo
~~~

Output from the JDWP agent when opening the listener:

~~~text
Listening for transport dt_socket at address: 5005
~~~

The JVM pauses before running the `main` method.

### Step 3: Connect the debugger

Open a second terminal on a machine with the JDK installed.

On Linux/macOS, use the default socket attach:

~~~bash
jdb -sourcepath src -attach 127.0.0.1:5005
~~~

On Windows, explicitly select the socket connector:

~~~bash
jdb -sourcepath src -connect com.sun.jdi.SocketAttach:hostname=127.0.0.1,port=5005
~~~

If the target is on another machine, replace the loopback address with the target's host or connect to loopback through an SSH tunnel.

### Step 4: Set a breakpoint and resume

At the JDB prompt:

~~~text
stop at com.acme.RemoteDebugDemo:8
cont
~~~

JDB pauses at the line:

~~~java
attempt += i;
~~~

Inspect variables:

~~~text
locals
print attempt
print i
~~~

On the first pause, the expected values are:

~~~text
attempt = 0
i = 1
~~~

Step over the current line:

~~~text
next
print attempt
~~~

Value after the first addition:

~~~text
attempt = 1
~~~

Remove the breakpoint and resume:

~~~text
clear com.acme.RemoteDebugDemo:8
cont
~~~

### Step 5: Verify application output

Stdout produced by the Java program:

~~~text
REMOTE_DEBUG_READY
attempt=1
attempt=3
attempt=6
REMOTE_DEBUG_DONE=6
~~~

This example was compiled with `javac -g --release 17` and tested on Azul OpenJDK 24.0.2. JDB connected over a TCP socket, paused accurately at line 8, read `attempt` and `i`, stepped through execution, cleared the breakpoint, and let the program run to completion.

## 14. Remote debugging in containers or cloud environments

When the JVM runs in Docker, Kubernetes, or a cloud VM, the debugger must be able to reach the exact JDWP endpoint inside the target's network namespace.

Check the following:

- Is the JDWP agent enabled in the container/process command line?
- Does the bind address match how the port is published or forwarded?
- Is the JDWP port forwarded to the right container/pod?
- Do firewalls, security groups, and network policies allow the required connection?
- Are the target and debugger using the same transport and port?
- Does the source code on the developer machine match the running image/build?

You can use an SSH tunnel, VPN, or controlled port forwarding to create a temporary connection path. Avoid exposing the JDWP port publicly just for IDE convenience.

Exposing a port in a Dockerfile or declaring a container port does not guarantee that the port is protected. You must control network binding, port mapping, and access policies in the runtime environment.

## 15. How do breakpoints and thread suspension affect the application?

When a breakpoint is hit, the debugger can suspend the current thread or multiple threads depending on the suspend policy. In some IDEs, Java breakpoints may suspend all JVM threads by default.

This can cause:

- In-flight requests to stall mid-execution.
- Timeouts at load balancers or clients.
- Locks to be held longer than usual.
- Other threads to become `BLOCKED` because the thread paused at the breakpoint holds a monitor.
- Scheduled tasks, heartbeats, or health checks to miss their deadlines.
- Timing bugs or race conditions to disappear when the debugger slows down execution.

When inspecting a production-like environment, prefer conditional breakpoints or logpoints if supported by your IDE, avoid suspending the entire JVM, and use a staging environment to reproduce issues first. Because a debugger alters program timing, observed behavior may differ from normal execution.

## 16. Remote debugging security

JDWP is a powerful control interface for the target JVM. A JDWP connection begins with a fixed handshake to confirm both sides use the same protocol; this handshake is not a user authentication mechanism and does not provide transport encryption.

A debugger with JDWP access can read in-process data, suspend threads, modify values, and control execution flow. Therefore, a JDWP port reachable from an untrusted network is a severe security risk.

Safe practices:

- Enable JDWP only when debugging is genuinely needed.
- Prefer binding to loopback and connecting over an SSH tunnel.
- Use a VPN or dedicated management network when remote debugging is required.
- If you must bind to a network interface, restrict IPs using `allow` and firewall rules.
- Never expose JDWP directly to the Internet.
- Restrict who has SSH, VPN, or target-host access.
- Use `suspend=n` if the service must keep running while waiting for an attach.
- Record when debugging was enabled and disable it once finished.
- Restart the application without the JDWP agent configuration after the debug session ends.

JDWP should not be treated as an administrative service with built-in password protection or TLS. Transport security must be provided by an external network layer, such as SSH or a VPN.

## 17. Troubleshooting remote debugging

| Symptom | Common cause | Resolution |
|---|---|---|
| `Connection refused` | JDWP agent not running, wrong host/port, or target has not bound the socket. | Check JVM arguments, listener status, and actual port. |
| `Connection timed out` | Firewall, routing, security group, or tunnel is blocking the connection. | Check network path and connection direction. |
| JVM hangs before application starts | `suspend=y` is waiting for a debugger. | Attach the debugger or switch to `suspend=n` if appropriate. |
| Debugger connects but breakpoint is not hit | Breakpoint on wrong line, class not yet loaded, or source mismatches bytecode. | Verify package, class name, line number, and build. |
| Local variables are not visible | Class lacks local variable debug metadata or current frame has no variables in scope. | Compile with `javac -g` and pause on the appropriate line. |
| JDB on Windows reports shared memory error | `jdb -attach` picked a default connector that does not match the TCP socket target. | Use `-connect com.sun.jdi.SocketAttach:hostname=...,port=...`. |
| `Address already in use` | The JDWP port is already used by another process. | Choose a different port and update the debugger configuration. |
| Target reverse connection fails | JDB listener is not running or target cannot reach the listener address. | Start the listener first; verify IP/port and firewall rules. |
| IDE reports source mismatch | IDE has source checked out from a different commit than the running classes. | Check out the matching commit or build artifact. |
| Debugger does not track virtual threads | Default debugger configuration does not track all virtual threads. | Check JDK/IDE virtual thread tracking options; JDB provides `-trackallthreads`. |

## 18. How does remote debugging differ from JMX, JFR, and thread dumps?

These tools all help observe the JVM, but serve different purposes:

| Tool | How it works | Best used when |
|---|---|---|
| Remote debugger (JDWP/JDI) | Connects interactively, sets breakpoints, and controls execution. | You need to inspect logic, variable values, or call flows at a specific location. |
| JMX/JConsole | Reads MBean attributes and invokes management operations. | You need to monitor metrics and administrative JVM/application state. |
| JFR | Records time-stamped events into a recording file. | You need post-collection analysis of CPU, allocations, GC, locks, and I/O. |
| Thread dump | Captures thread stacks and states at a point in time. | You need to investigate hung threads, `BLOCKED` threads, or deadlocks. |
| Heap dump | Captures the object graph in the heap. | You need to find object retention and memory leaks. |

Do not use a remote debugger as a continuous monitoring system. For long-term observation or minimizing timing impact, JFR and metrics are generally more suitable.

## 19. Verifying and closing the debug session

When finished:

1. Resume or terminate the target according to the desired state.
2. Stop the debugger session with `quit` or the IDE's Disconnect button.
3. Confirm the application is no longer suspended.
4. Close any SSH tunnels or port forwarding.
5. Remove the JDWP configuration from the startup command, service unit, container environment, or deployment manifest if no longer needed.
6. Restart the application with its normal operational configuration if JDWP was enabled temporarily.
7. Verify that the JDWP listener is no longer active on the host.

Disconnecting the debugger does not guarantee that the JDWP configuration has been removed from future restarts. Check deployment configurations to avoid accidentally leaving a debug port open.

## 20. Recommended remote debugging workflow

When you need to debug a remote JVM:

1. Identify the host, PID, JDK version, and running artifact.
2. Build or obtain the exact matching source code and debug symbols for the artifact.
3. Choose the connection direction: target listens (`server=y`) or target connects to debugger (`server=n`).
4. Choose `suspend=y` if you must set breakpoints before `main`; use `suspend=n` to keep the service running.
5. Open only the necessary address/port and restrict connection sources.
6. Prefer an SSH tunnel or VPN to protect the transport.
7. Connect the IDE/JDB using the appropriate socket connector.
8. Set breakpoints, inspect locals and the call stack, then resume the application.
9. Monitor the impact of breakpoints on requests, threads, and locks.
10. Close the tunnel, remove the debug option, and verify the port is no longer open.

Remote debugging helps developers investigate bugs in JVMs running in other environments using their familiar source code and debugger. Understanding JPDA/JDWP, both connection directions, `suspend`, transports, and security helps keep debug sessions reproducible while minimizing application impact.

## References

- Oracle JDK 24 — [Java Platform Debugger Architecture](https://docs.oracle.com/en/java/javase/24/docs/specs/jpda/jpda.html).
- Oracle JDK 24 — [Connection and Invocation Details](https://docs.oracle.com/en/java/javase/24/docs/specs/jpda/conninv.html).
- Oracle JDK 24 — [The jdb Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdb.html).
- Oracle JDK 24 — [Java Debug Wire Protocol Specification](https://docs.oracle.com/en/java/javase/24/docs/specs/jdwp/jdwp-spec.html).
- Oracle JDK 24 — [Troubleshooting Guide: Java Debug Wire Protocol](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-guide.pdf).
