# Configuring a Debug Port for the Java JVM

## 1. What is a debug port?

A debug port is the TCP port that the Java Virtual Machine (JVM) uses to exchange debugging data with a debugger via the Java Debug Wire Protocol (JDWP). When the JDWP agent is enabled, a debugger such as IntelliJ IDEA, Eclipse, or JDB can connect to the JVM to set breakpoints, view stack traces, inspect variables, step through code, and resume or suspend threads.

The debug port is typically a dedicated port, such as `5005`. It is not the application's HTTP port, not the JMX port, and not the `jcmd` port.

A remote debugging session has two endpoints:

- **Target JVM:** The Java process running the application to be debugged.
- **Debugger:** The IDE or JDB that connects to the target to send debug commands.

The JDWP agent resides inside the target JVM. The `dt_socket` transport transmits JDWP packets over TCP/IP. When the debugger and the JVM are on different machines, the address and port must be reachable over the network.

## 2. How do JPDA, JDI, and JDWP relate?

The Java Platform Debugger Architecture (JPDA) consists of coordinating components:

| Component | Role |
|---|---|
| JPDA | Overall architecture for Java debugging. |
| JDI (Java Debug Interface) | Debugger-side API for controlling the target VM. |
| JDWP (Java Debug Wire Protocol) | Protocol for exchanging commands and replies between the debugger and the JVM. |
| JDWP agent | Component loaded into the target JVM to implement the protocol. |
| Transport | Data transmission channel, typically the `dt_socket` TCP socket. |

The IDE uses JDI to establish a connection and send requests. The JDWP agent inside the JVM processes those requests and returns runtime information. With the socket transport, data travels over a TCP connection.

The debug port is the transport address where the two sides meet. Both the debugger and the JVM must agree on the host, port, and connection direction.

## 3. Two connection directions: server=y and server=n

The `server` option describes the network role of the target JVM:

| Configuration | What does the target JVM do? | What does the debugger do? | When to use |
|---|---|---|---|
| `server=y` | Opens a port and waits for the debugger to connect. | Actively attaches to the JVM. | Common approach when an IDE connects to an application. |
| `server=n` | Actively connects to a listening debugger. | Opens a listener and waits for the JVM to connect. | When the network only allows outbound connections from the machine running the application. |

With `server=y`, the JVM is the TCP server. With `server=n`, the debugger is the TCP server. The name `server` does not mean the debugger is always the server.

The most common approach is `server=y`: the application opens the debug port, and then the IDE selects Attach to remote JVM and connects to that host/port.

## 4. JDWP agent syntax

Load the JDWP agent when launching the JVM with:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar app.jar
~~~

General syntax:

~~~text
-agentlib:jdwp=<option>=<value>,<option>=<value>,...
~~~

Key options:

| Option | Meaning |
|---|---|
| `transport` | Transport used to exchange data. For TCP/IP, this is `dt_socket`. |
| `server` | `y` for the JVM to listen for a debugger; `n` for the JVM to connect to a debugger. |
| `address` | Address and port of the listening endpoint or the endpoint to connect to. |
| `suspend` | `y` to pause the JVM until a debugger connects; `n` to let the application run immediately. |
| `timeout` | Connection wait timeout, in milliseconds. |
| `allow` | With `server=y` and `dt_socket`, restricts the IPs/subnets allowed to connect. |

Use commas to separate options. Do not add spaces inside the JDWP string, as the JVM may treat them as part of a value.

View the list of supported options on your current JDK:

~~~bash
java -agentlib:jdwp=help
~~~

JDK 24.0.2 in this lab confirms the `transport`, `server`, `address`, `suspend`, and `allow` options. The default value of `suspend` is `y`; `server` defaults to `n`.

## 5. Choosing a bind address for the debug port

The bind address determines which network interface accepts connections:

| Address | Behavior |
|---|---|
| `address=5005` | Listens on loopback by default in the JDK 24 socket transport. |
| `address=127.0.0.1:5005` | Listens only on IPv4 loopback. |
| `address=localhost:5005` | Listens on the loopback address resolved from the hostname. |
| `address=*:5005` | Listens on all network interfaces. |

For debugging on the same machine, bind to loopback:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar app.jar
~~~

When the debugger runs on a different machine, the target needs to listen on a reachable interface. You can use:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005 -jar app.jar
~~~

`address=*:5005` exposes the listening port on every network interface. Only use it when connections are already restricted by a firewall, allow list, or private network. Do not expose a debug port to the public Internet.

Port `5005` is a common convention, not a mandatory port. You can choose any other available TCP port permitted through the firewall.

## 6. Understanding suspend=y and suspend=n

`suspend` determines whether the application runs before a debugger connects:

**suspend=y**

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 -jar app.jar
~~~

The JVM opens the debug port and pauses before running the main class. The application waits for a debugger to connect. This is the right choice when you need to debug:

- Errors occurring in a static initializer or constructor at startup.
- Class loading or Spring/application initialization.
- Configuration that only exists during the startup phase.
- An error that appears before an operator can attach.

If no debugger connects, the application remains paused at startup. In deployment environments with health checks, this may cause the instance to be marked unhealthy.

**suspend=n**

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar app.jar
~~~

The JVM starts the application even when no debugger is attached. Use this option when you want to attach to a running process, observe a request, or investigate an issue that occurs after startup.

With `server=y`, `suspend=y` is the default. Always specify `suspend` explicitly in your configuration so operators know whether the application will wait or run immediately.

## 7. Enabling the debug port for a JAR application

You can pass the JDWP agent directly to the `java` command:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar service.jar
~~~

If the application takes additional JVM options, place the debug option before `-jar`:

~~~bash
java -Xms512m -Xmx1g -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar service.jar
~~~

For applications run with a classpath:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -cp out com.example.Main
~~~

JDWP is a JVM option, so it must be placed before the main class name or `-jar`. Placing it after the class name causes the JVM to pass that string as an application argument.

## 8. Enabling the debug port via environment variables or launch scripts

In Docker, Kubernetes, or service scripts, you can add JDWP to the JVM options environment variable used by the entrypoint.

Example:

~~~bash
JAVA_TOOL_OPTIONS="-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005"
export JAVA_TOOL_OPTIONS
java -jar app.jar
~~~

The JVM automatically reads `JAVA_TOOL_OPTIONS` at startup. Startup logs usually display a message indicating that the option has been picked up.

If you use `JAVA_OPTS`, make sure the launch script actually passes this variable to the `java` command. `JAVA_OPTS` is not automatically read by the JVM in all environments.

Do not add the same JDWP agent twice—for example, in both `JAVA_TOOL_OPTIONS` and on the command line. Loading the agent twice can cause the JVM to fail on startup or bind the port unexpectedly.

## 9. Connecting a debugger with JDB

JDB is the command-line debugger bundled with the JDK. When the target JVM is listening on localhost port 5005, you can connect via the socket connector:

~~~bash
jdb -connect com.sun.jdi.SocketAttach:hostname=127.0.0.1,port=5005
~~~

On Linux/macOS, the following shortcut typically uses the socket connector by default:

~~~bash
jdb -attach 127.0.0.1:5005
~~~

On Windows, `jdb -attach` may default to the shared-memory connector. If the target JVM is using a TCP socket, that command can fail with an error like `shmemBase_attach failed`. Use the explicit connector for TCP connections:

~~~powershell
jdb -connect com.sun.jdi.SocketAttach:hostname=127.0.0.1,port=5005
~~~

Once connected, JDB opens a prompt. Useful commands:

| Command | Effect |
|---|---|
| `help` | View the list of commands. |
| `threads` | List threads in the target JVM. |
| `thread <id>` | Select a thread to inspect. |
| `where` | Display the stack trace of the current thread. |
| `where all` | Display stack traces of all threads. |
| `stop at ClassName:line` | Set a breakpoint by line number. |
| `stop in ClassName.method` | Set a breakpoint by method. |
| `locals` | Display local variables when the thread is suspended. |
| `print expression` | Evaluate and print the value of an expression. |
| `next` | Step to the next line without entering method calls. |
| `step` | Step into the next method call. |
| `cont` | Resume target execution. |
| `clear` | Remove a breakpoint. |
| `exit` | Exit JDB. |

Example:

~~~text
stop at com.example.Main:42
cont
locals
where
next
cont
~~~

Line breakpoints require classes to be compiled with appropriate debug information. When using `javac`, add `-g` to preserve local variable and line number information:

~~~bash
javac --release 17 -g -d out src/com/example/Main.java
~~~

## 10. Connecting with an IDE

In IntelliJ IDEA, Eclipse, or any IDE supporting remote debugging, create a Remote JVM Debug or Attach to Remote JVM configuration.

Fields to fill in:

| Field | Example value |
|---|---|
| Debugger mode | Attach to remote JVM |
| Host | `127.0.0.1` if debugging locally or through a tunnel |
| Port | `5005` |
| Transport | Socket / TCP |
| Module / classpath | Module containing the application's source code |

After the target JVM has opened the port, click Debug/Attach in the IDE. Once connected, the IDE can display threads, stack frames, local variables, and breakpoints.

The source code in the IDE must match the version of the classes currently running. If the source and bytecode do not match, breakpoints may be misaligned or fail to bind.

## 11. Using server=n when the debugger must listen first

In some networks, the target is not allowed to open inbound ports but can initiate outbound connections to the development machine. In that case, have the debugger act as the TCP server by opening a socket listener with the JDI connector:

~~~bash
jdb -connect com.sun.jdi.SocketListen:port=5005,localAddress=127.0.0.1
~~~

Launch the target JVM with `server=n` so the JVM connects to the debugger listener:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=n,address=127.0.0.1:5005,suspend=y -jar app.jar
~~~

If the debugger is on another machine, replace `127.0.0.1` with the hostname/IP of the debugger machine and configure the listener to bind to a reachable interface.

In JDI, the corresponding connector is `com.sun.jdi.SocketListen`. This approach is useful when a firewall allows the target to connect outbound but prevents the debugger from initiating connections to the target. `server=n` is an advanced configuration; verify that the listener is ready before launching the target.

## 12. Using allow to restrict allowed client IPs

With `server=y` and `transport=dt_socket`, the `allow` option restricts which IPs or subnets are permitted to connect:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005,allow=127.0.0.1+10.20.30.40 -jar app.jar
~~~

The example above listens on all interfaces but only allows loopback and the specified debugger IP.

CIDR subnets can also be used:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005,allow=10.20.0.0/16 -jar app.jar
~~~

Entries in the `allow` list are separated by a plus sign (`+`). Each entry can be a single IP or a subnet. This option is supported in JDK 24; check `java -agentlib:jdwp=help` before using it on other JDKs.

`allow` is an additional restriction layer. You still need to configure firewalls or network policies so that only the debugger machine can reach the port.

## 13. Connecting over an SSH tunnel

When the JVM runs on a remote server, you can keep the debug port bound only to loopback on the server and use an SSH tunnel.

On the development machine:

~~~bash
ssh -L 5005:127.0.0.1:5005 user@remote-host
~~~

On the remote host, launch the JVM:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar app.jar
~~~

In the IDE or JDB on the development machine, connect to:

~~~text
127.0.0.1:5005
~~~

SSH forwards traffic from localhost on the development machine to loopback on the remote host. This avoids exposing the debug port directly on a public network.

## 14. Using a debug port in Docker and Kubernetes

### Docker

Inside a container, the JVM needs to bind to the container's interface so the host can forward connections:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005 -jar app.jar
~~~

You can pass JDWP via `JAVA_TOOL_OPTIONS` and publish the port only on the host's loopback:

~~~bash
docker run -e "JAVA_TOOL_OPTIONS=-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005" -p 127.0.0.1:5005:5005 my-java-image
~~~

Then the IDE on the host connects to `127.0.0.1:5005`. Do not publish the debug port on all interfaces without proper network restrictions.

### Kubernetes

You can use `kubectl port-forward` to forward the port from a pod to the development machine:

~~~bash
kubectl port-forward pod/my-java-pod 5005:5005
~~~

The JVM in the pod must listen on port 5005 and bind to the pod's interface. While port-forward is active, the debugger connects to `127.0.0.1:5005` on the development machine.

Port-forward only remains active while the command session is running. When you stop port-forward, the debugger loses its connection.

## 15. Verifying that the debug port is open

### Checking the JVM command line

Find the PID:

~~~bash
jcmd -l
~~~

Inspect JVM options:

~~~bash
jcmd 18420 VM.command_line
~~~

The output should include the `-agentlib:jdwp` configuration with the expected transport, server mode, and address.

### Checking the TCP listener

Linux:

~~~bash
ss -lntp | grep 5005
~~~

Windows PowerShell:

~~~powershell
Get-NetTCPConnection -LocalPort 5005 -State Listen
~~~

If using loopback, the local address should be `127.0.0.1` or the corresponding loopback address. If using a wildcard, the listener may show `0.0.0.0` or `::` depending on the operating system.

### Testing from the debugger

Try connecting with JDB:

~~~bash
jdb -connect com.sun.jdi.SocketAttach:hostname=127.0.0.1,port=5005
~~~

If JDB connects and the `threads` command lists threads, both the TCP path and the JDWP handshake are working.

## 16. Complete Java 17 hands-on example

Create the file `src/DebugPortDemo.java`:

~~~java
public class DebugPortDemo {
    public static void main(String[] args) throws InterruptedException {
        int total = 0;
        System.out.println("DebugPortDemo started");

        for (int i = 1; i <= 5; i++) {
            total += i;
            System.out.println("step=" + i + ", total=" + total);
            Thread.sleep(1000);
        }

        System.out.println("DebugPortDemo complete: " + total);
    }
}
~~~

Compile:

~~~bash
mkdir -p out
javac --release 17 -g -d out src/DebugPortDemo.java
~~~

Stdout when running without the debugger enabled:

~~~text
DebugPortDemo started
step=1, total=1
step=2, total=3
step=3, total=6
step=4, total=10
step=5, total=15
DebugPortDemo complete: 15
~~~

Run the JVM with a local debug port:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -cp out DebugPortDemo
~~~

The JDWP log on JDK 24.0.2 looks like:

~~~text
Listening for transport dt_socket at address: 5005
~~~

In another terminal, connect JDB:

~~~bash
jdb -connect com.sun.jdi.SocketAttach:hostname=127.0.0.1,port=5005
~~~

At the JDB prompt, you can list threads and set a breakpoint:

~~~text
threads
stop at DebugPortDemo:7
cont
locals
where
cont
exit
~~~

This lab was compiled with `javac 24.0.2 --release 17 -g` and run with the JDWP socket transport. JDB connected to port 5017 in the test environment and listed the `main` thread along with JVM background threads. Port 5017 was only a test port; the lab commands in this guide use port 5005.

## 17. Timeout and automatically assigned addresses

You can set a timeout for the debugger connection:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,address=127.0.0.1:5005,suspend=y,timeout=5000 -jar app.jar
~~~

`timeout` is specified in milliseconds. With `server=y`, it is the wait time for a debugger to attach; with `server=n`, it is the timeout when the JVM connects to the debugger. A timeout of 0 means unlimited according to JDK 24 help.

If `server=y` is set without specifying `address`, JDWP can pick an available transport address and print it to the output:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n -jar app.jar
~~~

Read the printed port and use that exact address to configure the debugger. Do not assume an ephemeral port will always be 5005.

## 18. Security when enabling a debug port

JDWP is a powerful control channel for the JVM. Anyone who connects a debugger can inspect in-process data, read stacks and variables, suspend threads, set breakpoints, and influence execution flow. The socket transport does not provide built-in user authentication or TLS in standard JDWP options.

Therefore:

- Do not expose a debug port directly to the Internet.
- Prefer binding to loopback for local debugging.
- For remote debugging, use a VPN, SSH tunnel, or private network.
- Use `allow` and a firewall to restrict connection sources.
- Only enable the debug agent for as long as needed.
- Remove the debug option after finishing investigation and restart the JVM according to your deployment process.
- Do not use a debug port as a public monitoring endpoint.
- Protect logs and configuration files, as they may contain host, port, and deployment details.

Do not treat a hard-to-guess or unadvertised port as a security mechanism. Only trusted debuggers should be allowed access.

## 19. Common errors when configuring a debug port

| Symptom | Common cause | Resolution |
|---|---|---|
| `Address already in use` | The port is already in use by another process. | Choose another port or identify the process listening on it. |
| `Connection refused` | The JVM has not opened the port, wrong host/port, or the target process has exited. | Check JDWP logs, PID, and TCP listeners. |
| Connection timed out | Firewall, routing, container mapping, or incorrect bind address. | Check the interface, network policy, port-forward, and allow list. |
| JVM hangs before `main` runs | `suspend=y` is waiting for a debugger to attach. | Connect a debugger or use `suspend=n` if startup suspension is not needed. |
| JVM runs but debugger cannot attach | JDWP agent not loaded or wrong port. | Check `jcmd PID VM.command_line` and startup logs. |
| `shmemBase_attach failed` on Windows | JDB selected the shared-memory connector while the target uses a TCP socket. | Use `jdb -connect com.sun.jdi.SocketAttach:hostname=...,port=...`. |
| Breakpoint not bound/verified | Source differs from bytecode or line debug info is missing. | Use the matching source revision and compile with `javac -g`. |
| Breakpoint does not hit | Wrong class/line, method not loaded yet, or thread does not reach that line. | Check the breakpoint, stack trace, and execution flow. |
| Remote debug cannot reach container | JVM bound to loopback inside the container or port not published. | Bind to the container interface and publish/forward the right port. |
| Port unintentionally exposed on network | Used `address=*` without a firewall or allow restriction. | Bind to loopback or restrict IPs and network access. |
| Target waiting on the wrong side | Confused `server=y` and `server=n`. | Determine which side must listen and which side must connect. |
| JDK does not recognize `allow` option | The JDK version or agent does not support that option. | Run `java -agentlib:jdwp=help` to check runtime-supported options. |

## 20. Workflow for enabling and disabling a debug port in practice

1. Identify the JVM, host/container, and JDK version.
2. Pick an available TCP port, such as 5005.
3. Choose the connection direction; typically `server=y` so the debugger attaches to the JVM.
4. Choose the bind address. Use loopback for local debugging; use a private interface, allow list, and firewall for remote debugging.
5. Choose `suspend=y` if you need to debug startup or `suspend=n` if you need to attach to a running application.
6. Add `-agentlib:jdwp` to the command line or the service's JVM options configuration.
7. Restart the JVM if the agent was not loaded at startup.
8. Verify the JDWP log, command line, and TCP listener.
9. Configure the IDE/JDB with the correct host, port, and socket transport.
10. Set breakpoints, inspect threads/stacks/variables, and resume the application.
11. Stop the debug session when finished.
12. Remove the JDWP option, close the port, or restart the service according to your deployment process.

A debug port lets a debugger control a JVM remotely over JDWP. Proper configuration depends on the connection direction, bind address, port, suspend state, and network access permissions. Always verify the listener and debugger handshake before investigating code, and limit both the duration and the allowed sources for debug port access.

## 21. References

- [Connection and Invocation Details — JPDA, JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/jpda/conninv.html)
- [The jdb Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdb.html)
- [The java Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)
- [The jcmd Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
