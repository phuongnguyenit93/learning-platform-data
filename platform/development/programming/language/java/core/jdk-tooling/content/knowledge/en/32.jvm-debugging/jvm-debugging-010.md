# Closing the JVM Debug Endpoint with JDWP

A **JVM debug endpoint** is typically the TCP port opened by the Java Debug Wire Protocol (JDWP) agent so an IDE or debugger can connect to a running Java process. On HotSpot JDK, the agent is usually enabled with the **-agentlib:jdwp** option.

When ending a debug session, you need to distinguish three separate actions:

1. **Detach debugger:** disconnect the current IDE/debugger.
2. **Close the debug endpoint:** close the listener/port that the JVM has open so no other debugger can connect.
3. **Stop the JVM:** terminate the Java process, which closes the JDWP socket along with the process.

Detaching only performs the first action. With a running JDWP server, the listener can continue waiting for another debugger. To completely close the JVM's endpoint, perform a controlled shutdown of the application and restart it without loading the JDWP agent. If you cannot restart immediately, block access to the port using a firewall or network policy while preparing a restart window.

## 1. Identifying Where the Endpoint Is Opened

The JDWP socket transport uses a TCP connection between the debugger and the target JVM. The two sides can swap server/client roles:

| JDWP option | Target JVM role | Where the listener is opened |
|---|---|---|
| `server=y` | Target JVM waits for a debugger to connect | The JVM being debugged |
| `server=n` | Target JVM actively connects to the debugger | The machine running the debugger |

Example of a target JVM opening port 5005:

~~~sh
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar app.jar
~~~

- `transport=dt_socket`: uses a TCP socket.
- `server=y`: the JVM acts as the server and listens for debugger connections.
- `suspend=n`: the application starts immediately without waiting for a debugger to attach.
- `address=127.0.0.1:5005`: listens only on the JVM machine's loopback interface.

If `server=n` is used, the JVM is the client and requires the debugger's address:

~~~sh
java -agentlib:jdwp=transport=dt_socket,server=n,suspend=y,address=127.0.0.1:5005 -jar app.jar
~~~

In this case, the listener port is on the debugger machine. Close the debugger's listening connector when no more targets need to connect.

Windows also supports the `dt_shmem` transport via shared memory. With this transport, there is no TCP port to inspect; you must manage the connection session and process lifecycle accordingly.

## 2. Why Must the Debug Endpoint Be Closed After Investigation?

JDWP is a high-privilege control channel into the JVM. According to the JDWP specification, a debugger can read and modify private fields, invoke private methods, suspend/resume threads, inspect stacks, and instruct the JVM to exit. The protocol does not enforce Java access control on these operations.

If an unnecessary JDWP listener remains open, anyone who can connect to the endpoint can control the Java process within the capabilities provided by the debugger protocol. In particular, avoid exposing a debug port on all network interfaces in production environments.

Signs to check for:

- Startup logs contain `Listening for transport dt_socket at address: 5005`.
- `jcmd <pid> VM.command_line` shows that the JVM was started with `-agentlib:jdwp`.
- The OS reports a Java process in the `LISTEN` state on the debug port.
- A container or service has a port mapping dedicated to remote debugging.
- Environment variables or service run configurations automatically inject JDWP options.

Do not treat a debug port like an ordinary application port. Anyone who can connect via JDWP has control over the JVM's execution.

## 3. Detaching the Debugger Does Not Close the Listener

When an IDE selects **Disconnect** or **Detach**, the debugger sends a dispose request via JDI/JDWP. According to the JDK 24 JDI API, `VirtualMachine.dispose()` closes the debugger's communication channel, cancels event requests, and resumes threads that were suspended by the debugger. The target JVM then **prepares to accept a subsequent debugger connection**.

Therefore, after clicking Disconnect:

- Breakpoints and event requests from the current debugger are cancelled.
- Threads suspended by the debugger are resumed.
- The application continues running.
- The target JVM's JDWP listener may still be in the LISTEN state.
- Another debugger can re-attach to the same JVM.

This behavior is intentional so you can detach and re-attach without restarting the application.

~~~text
IDE debugger A
      |
      | JDWP attach
      v
Target JVM + JDWP listener
      |
      | JDI VirtualMachine.dispose()
      v
Debugger A disconnected
      |
      +----> JVM continues running
      |
      +----> Listener accepts debugger B
~~~

Do not confuse `VirtualMachine.dispose()` with `VirtualMachine.exit()`. `exit()` instructs the target JVM to terminate; threads are terminated abruptly and `finally` blocks are not guaranteed to run. Do not use this operation as a substitute for the normal application shutdown procedure.

## 4. Safe Procedure for Completely Closing the Endpoint

### Step 1: Identify the exact JVM and debug port

List running Java processes:

~~~sh
jcmd -l
~~~

Example:

~~~text
25884 DebugEndpointProbe
57488 com.example.OrderService
~~~

Inspect the command line of the JVM you want to check:

~~~sh
jcmd 57488 VM.command_line
~~~

Look for parameters such as:

~~~text
-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005
~~~

This command helps identify the agent, transport, server/client mode, and startup address. Do not rely on a PID from a previous run; verify against the current processes before acting.

Check the listener on Windows:

~~~powershell
Get-NetTCPConnection -State Listen -LocalPort 5005 | Format-Table LocalAddress, LocalPort, State, OwningProcess
~~~

Inspect the process owning the port:

~~~powershell
Get-Process -Id 57488
~~~

On Linux:

~~~sh
ss -ltnp 'sport = :5005'
~~~

Or:

~~~sh
lsof -nP -iTCP:5005 -sTCP:LISTEN
~~~

Confirm the port belongs to the exact JVM you intend to close. A port may have been reused by another process after the old application stopped.

### Step 2: End the debug session properly

Before detaching:

1. Save any needed information from the debugger, such as stack traces, breakpoints, and inspected variables.
2. Resume any threads suspended by breakpoints or debug actions.
3. Remove breakpoints if the IDE will reuse the configuration for future debug sessions.
4. Select **Disconnect/Detach** in the IDE.
5. Wait for the IDE to confirm that the debug session has ended.

This step keeps the application running normally. It does not close the JDWP listener.

### Step 3: Perform a controlled application shutdown

When you need to close the endpoint, stop the target JVM according to the application's lifecycle:

- For a Linux service, use the service manager or the deployment/restart workflow managing the service.
- For a Windows Service, use Services or the corresponding service management tool.
- For containers/Kubernetes, drain traffic, stop the pod, or perform a rollout according to your deployment process.
- For an application running in the foreground in a terminal, use the application's shutdown mechanism or press `Ctrl+C` if the program handles shutdown signals appropriately.

Do not use `Stop-Process -Force` or `kill -9` as a default step. Forceful termination can skip shutdown hooks, fail to flush data, and lose in-flight work.

When the JVM exits, the JDWP socket belonging to that process is closed along with the process.

### Step 4: Restart without loading the JDWP agent

Remove the debug parameter from the launch configuration:

~~~text
-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005
~~~

Check all sources that might automatically inject JVM options:

- Service configuration or startup scripts.
- `JAVA_TOOL_OPTIONS`.
- `JDK_JAVA_OPTIONS`.
- `JAVA_OPTS` or framework/container-specific variables.
- Docker Compose, Kubernetes Deployment, Helm values, or deployment manifests.
- IDE Run/Debug configurations or local startup scripts.

If you only remove the option from a temporary command line while the service configuration still retains it, the endpoint will reopen on the next restart.

Start the service with the JDWP-free configuration. Then check `jcmd <pid> VM.command_line` to confirm the new JVM no longer has the `-agentlib:jdwp` parameter.

## 5. If You Cannot Restart Immediately

In some situations, the application must continue serving requests and you cannot restart the JVM right away. In that case, restrict access to the debug port using a host firewall, network firewall, security group, or network policy.

Windows Firewall example—block inbound TCP to port 5005:

~~~powershell
New-NetFirewallRule -DisplayName "Block JDWP 5005" -Direction Inbound -Protocol TCP -LocalPort 5005 -Action Block
~~~

When this rule is no longer needed, remove it by its exact name:

~~~powershell
Remove-NetFirewallRule -DisplayName "Block JDWP 5005"
~~~

On Linux, you can use the OS firewall or infrastructure network policy. For example, with UFW:

~~~sh
sudo ufw deny 5005/tcp
sudo ufw status numbered
~~~

**A firewall only blocks network access; the socket may still remain in the LISTEN state inside the JVM.** This is an emergency mitigation while waiting for a restart, not proof that the endpoint is closed. Once you have a maintenance window, remove JDWP from the startup options, restart the application, and verify that the listener is gone.

If the JDWP port is published via Docker or Kubernetes, remove the port mapping/service exposure and check network policies as well. Closing the firewall on the host alone may not be enough if another proxy layer or port forwarding still exposes the port.

## 6. Safe Debug Configuration for Next Time

Ideally, do not enable JDWP in standard production configurations. Enable it only for a single run or a controlled investigation period.

### 6.1. Debugging only from the same machine

Bind the listener to loopback:

~~~sh
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar app.jar
~~~

Connections can only be made via the JVM machine's loopback interface. Do not use `address=*:5005` unless there is an explicit remote access requirement.

In JDK 24, `address=5005` also defaults to listening on loopback. Explicitly writing `127.0.0.1` makes the configuration intent easier to read and audit.

### 6.2. Remote debugging over an SSH tunnel

You can keep the JDWP listener on the server's loopback interface and create an SSH tunnel from the debugger machine:

~~~sh
ssh -L 5005:127.0.0.1:5005 user@debug-host
~~~

Then configure the IDE to connect to:

~~~text
localhost:5005
~~~

The tunnel forwards traffic from the debugger machine's local port to the JVM machine's loopback interface. This avoids exposing the JDWP listener on all interfaces.

### 6.3. Remote debugging over a private network with an allowlist

If the architecture strictly requires a direct connection, bind to the appropriate interface, restrict source IPs, and configure infrastructure firewalls.

Example:

~~~sh
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005,allow=192.0.2.25+198.51.100.0/24 -jar app.jar
~~~

- `address=*:5005`: the listener accepts connections on all network interfaces.
- `allow=...`: permits only the listed IPs or subnets.
- Addresses in the `allow` list are separated by `+`.
- For `dt_socket`, the default value of `allow` is `*`, meaning all addresses are permitted.

An allowlist is one layer of source-connection restriction. You still need firewall/network ACLs and a time-bounded procedure for opening/closing the endpoint. Do not use the `*` wildcard as a security measure.

The `timeout=5000` option in `server=y` mode limits the transport wait time for the initial debugger attach. It is not a timer that automatically closes the listener after a debugger has attached and detached.

## 7. Verifying That the Endpoint Is Truly Closed

After restarting the JVM without JDWP, check both the command line and the socket.

### Windows

Find the new JVM:

~~~powershell
jcmd -l
~~~

Check the JVM options:

~~~powershell
jcmd <pid> VM.command_line
~~~

Neither `-agentlib:jdwp` nor `-Xrunjdwp` should appear in the command line.

Check the listener:

~~~powershell
Get-NetTCPConnection -State Listen -LocalPort 5005 -ErrorAction SilentlyContinue
~~~

If there is no output, there is currently no TCP listener on port 5005. If there is output, inspect `OwningProcess` to identify which process is holding the port.

You can also test from another machine:

~~~powershell
Test-NetConnection debug-host -Port 5005
~~~

After closing the endpoint, connections from an allowed machine must fail. If a firewall is blocking it, this result only confirms that the network path is blocked; also check the listener on the host to distinguish that from a closed socket.

### Linux

~~~sh
jcmd -l
jcmd <pid> VM.command_line
ss -ltnp 'sport = :5005'
~~~

If there is no longer a `LISTEN` line for port 5005, the socket listener is gone. If one still appears, check the PID/process owning the port before drawing conclusions.

Do not rely solely on seeing the IDE disconnected or `Test-NetConnection` timing out. Confirm both the process and the socket state on the machine running the JVM.

## 8. Java 17+ Hands-On Example: Opening and Closing a Debug Endpoint

This example creates a JVM that waits while running. A shutdown hook prints a message when the application receives a normal termination signal.

Create `DebugEndpointProbe.java`:

~~~java
import java.util.concurrent.CountDownLatch;

public class DebugEndpointProbe {
    public static void main(String[] args) throws InterruptedException {
        Runtime.getRuntime().addShutdownHook(new Thread(
            () -> System.out.println("debug-endpoint-stopped")
        ));

        System.out.println("debug-endpoint-ready");
        new CountDownLatch(1).await();
    }
}
~~~

Compile with Java 17 or later:

~~~sh
mkdir -p out
javac --release 17 -d out DebugEndpointProbe.java
~~~

Launch with the JDWP listener on loopback only:

~~~sh
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -cp out DebugEndpointProbe
~~~

Output:

- The JDWP agent writes to stderr:

~~~text
Listening for transport dt_socket at address: 5005
~~~

- The application writes to stdout:

~~~text
debug-endpoint-ready
~~~

Open a second terminal and find the PID:

~~~sh
jcmd -l
~~~

Check the listener on Windows:

~~~powershell
Get-NetTCPConnection -State Listen -LocalPort 5005
~~~

When you want to close the endpoint in this exercise, return to the terminal running the application and press `Ctrl+C`. The shutdown hook writes to stdout:

~~~text
debug-endpoint-stopped
~~~

Check again:

~~~powershell
Get-NetTCPConnection -State Listen -LocalPort 5005 -ErrorAction SilentlyContinue
~~~

No output means the listener has closed. On Linux, use `ss -ltnp 'sport = :5005'` to verify.

## 9. JDI Example: Detaching While the Listener Remains Open

The following code uses JDI `SocketAttach` to connect to the JVM and then calls `VirtualMachine.dispose()`. It demonstrates closing the debugger session without terminating the target JVM.

Create `DetachProbe.java`:

~~~java
import com.sun.jdi.Bootstrap;
import com.sun.jdi.VirtualMachine;
import com.sun.jdi.connect.AttachingConnector;
import com.sun.jdi.connect.Connector;
import java.util.Map;

public class DetachProbe {
    public static void main(String[] args) throws Exception {
        AttachingConnector connector =
            Bootstrap.virtualMachineManager().attachingConnectors().stream()
                .filter(c -> c.name().equals("com.sun.jdi.SocketAttach"))
                .findFirst()
                .orElseThrow();

        Map<String, Connector.Argument> values = connector.defaultArguments();
        values.get("hostname").setValue("127.0.0.1");
        values.get("port").setValue(args[0]);

        VirtualMachine vm = connector.attach(values);
        System.out.println("debugger-attached");

        vm.dispose();

        System.out.println("debugger-detached");
    }
}
~~~

Compile:

~~~sh
javac --release 17 --add-modules jdk.jdi -d out DetachProbe.java
~~~

Assuming the target JVM has port 5005 open:

~~~sh
java --add-modules jdk.jdi -cp out DetachProbe 5005
~~~

Exact stdout:

~~~text
debugger-attached
debugger-detached
~~~

After the helper finishes, check:

~~~powershell
Get-NetTCPConnection -State Listen -LocalPort 5005
~~~

The listener may still exist, and another debugger can re-attach. When the target JVM is stopped with Ctrl+C as in the previous example, the shutdown hook runs and the socket listener disappears.

This is an important test to confirm that detaching and closing the endpoint are two distinct actions.

## 10. Common Issues

| Symptom | Cause | Resolution |
|---|---|---|
| IDE shows Disconnected, but port is still LISTEN | Debugger only detached; target JVM still holds the JDWP listener | Stop/restart the JVM without the JDWP agent |
| Port reopens after restart | Startup script, environment variable, or manifest still adds `-agentlib:jdwp` | Inspect `VM.command_line` and deployment configuration |
| Port 5005 is still open after the old process stopped | Another process is reusing the port | Check `OwningProcess`/PID to identify the exact process |
| Cannot connect even though the listener is open | Firewall, allowlist, bind address, or routing is blocking the connection | Check `LocalAddress`, `allow`, security groups, and network policies |
| Debugger cannot attach | Wrong server/client mode, wrong address, or wrong port | Verify `server`, `address`, and startup logs |
| Application hangs at startup | `suspend=y` causes the JVM to wait for a debugger | Attach a debugger or stop the JVM using the appropriate procedure |
| Firewall rule added, but `ss` still shows LISTEN | Firewall only blocks connections; the socket still belongs to the JVM | Restart the JVM without the agent to close the listener |
| Used `-XX:+DisableAttachMechanism`, but debug port is still open | That option controls the Attach API; it does not stop an already-loaded JDWP listener | Remove the JDWP agent and restart the JVM |
| Called `VirtualMachine.dispose()`, but JVM can still be debugged again | Dispose prepares the target VM to accept the next debugger | Stop/restart the target JVM to close the endpoint |
| Port is not open when `server=n` | Target JVM is connecting out to the debugger, not acting as a server | Check the listener on the debugger machine |

## 11. Post-Debug Operational Procedure

1. Identify the JVM, PID, transport, and debug address in use.
2. Save the necessary diagnostic data.
3. Resume any suspended threads and detach the debugger.
4. Verify that the application continues serving traffic normally.
5. Schedule a graceful stop/restart if the JDWP listener needs to be closed.
6. Remove the JDWP option from service startup, environment variables, and deployment manifests.
7. Start a new JVM without the JDWP agent.
8. Use `jcmd <pid> VM.command_line` to verify the command line.
9. Use `Get-NetTCPConnection` or `ss` to confirm no listener remains.
10. If you cannot restart yet, block the inbound port with a firewall/network policy and document it as a temporary measure.
11. Re-check after the next deployment/restart to ensure the endpoint does not reopen automatically.

### Checklist

- [ ] Identified the exact JVM/PID and debug port.
- [ ] Distinguished between `server=y` and `server=n`.
- [ ] Understood that detaching the debugger does not close the JDWP listener.
- [ ] Resumed threads suspended by the debugger before detaching.
- [ ] Stopped the JVM gracefully or restarted the service.
- [ ] Removed JDWP options from startup config and environment variables.
- [ ] Verified `VM.command_line` of the new JVM.
- [ ] Confirmed no TCP listener remains on the debug port.
- [ ] Applied firewall/network policy if temporary blocking was needed.
- [ ] Checked Docker/Kubernetes port mappings if the application runs in a container.
- [ ] Confirmed the endpoint did not reopen after the next restart/deployment.

Closing a debug endpoint means the JDWP listener no longer accepts new connections. Detaching the debugger only closes the current control session; the target JVM can continue listening. Shut down the application according to its lifecycle, remove `-agentlib:jdwp` from the launch configuration, restart, and verify both the command line and the socket listener. When an immediate restart is not possible, a firewall helps block access in the meantime, but it does not replace closing the listener.

## References

- [Oracle JDK 24 — The java Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)
- [Oracle JDK 24 — JPDA Connection and Invocation Details](https://docs.oracle.com/en/java/javase/24/docs/specs/jpda/conninv.html)
- [Oracle JDK 24 — JDI VirtualMachine API](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jdi/com/sun/jdi/VirtualMachine.html)
- [Oracle JDK 24 — JDWP Protocol Details](https://docs.oracle.com/en/java/javase/24/docs/specs/jdwp/jdwp-protocol.html)
- [Oracle JDK 24 — Java Platform Debugger Architecture](https://docs.oracle.com/en/java/javase/24/docs/specs/jpda/jpda.html)