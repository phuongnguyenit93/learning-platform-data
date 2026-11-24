# 19.3 Launching an Application with -agentlib:jdwp and Understanding server, suspend, and address

## 1. The Problem: Why Is the JVM "Listening on Port 5005" While the App Has Not Run Yet?

When you need to debug a Java service, you can launch it with JDWP:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar app.jar
~~~

Yet three seemingly simple options control three **different** behaviors:

- `server=y/n`: **which side opens a listening socket (`listen`), and which side actively initiates the connection (`connect`)**? `server` refers to **the network role of the target JVM**, not "whether this is an HTTP application server."
- `suspend=y/n`: should the JVM **pause before loading the main class** so the debugger has a chance to set breakpoints right from the start? It does not mean "the debugger is only allowed to pause when `y` is enabled."
- `address=...`: **the JDWP connection endpoint**, which can be the target's bind address/port when `server=y`, or the host/port where the debugger is listening when `server=n`. The wrong address can cause connection failures, expose an unintended port, or leave the app waiting for a debugger forever without becoming ready.

The opening example uses JDK 17+ and HotSpot: the JVM opens a TCP port on loopback only, runs `main` immediately without waiting for a debugger connection, yet still allows a debugger to attach later. The fact that the app runs comes from **`suspend=n`**, independent of the agent's `server` name.

**Goal:** read `-agentlib:jdwp` syntax accurately; choose the right `server/suspend/address` combination; connect using an IDE or `jdb`; observe firsthand the difference between immediate startup and waiting for a debugger; handle port/bind/container issues; and protect JDWP from unauthorized access.

## 2. JPDA, JDWP, and the Position of the Debug Agent

**JPDA** (Java Platform Debugger Architecture) provides the debugging communication layers:

- **JDI (Java Debug Interface)**: the interface used by IDEs/`jdb` to control and inspect the debugged JVM.
- **JDWP (Java Debug Wire Protocol)**: the protocol exchanging commands/events between the debugger and target JVM.
- **JVM TI**: the tooling interface on the JVM side; HotSpot's JDWP agent uses VM capabilities to serve debugger requests.
- **Transport**: the mechanism carrying JDWP packets. Most common is the TCP socket `dt_socket`. On Windows HotSpot there can be `dt_shmem` (shared memory, same machine), not applicable for TCP/Linux debugging.

Familiar scenario diagram:

~~~text
IDE / jdb (debugger)  -- TCP JDWP -->  Java target VM
         attach                           listens at
                                          127.0.0.1:5005
                              agentlib:jdwp,server=y
~~~

In the **`server=n`** case, the connection setup arrow reverses: the debugger **listens**, and the target JVM **connects** to `address`. Once the connection is established, the debugger still controls the target over JDWP; `server=n` does not turn the Java app into a debugger.

Enabling JDWP at startup means **loading the debug agent into the JVM before running application code**. Merely opening an IDE or running `jdb` does not turn an arbitrary JVM into a listening debug port; to attach via TCP port, the target must have the corresponding agent, or use a separate attach/instrumentation mechanism supported by the JVM/IDE. Do not treat `jcmd` and JDWP as the same protocol.

## 3. Syntax and Defaults: Do Not Guess

Common syntax of the Java launcher:

~~~text
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -cp out MyMain
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar app.jar
~~~

The `-agentlib:jdwp=...` argument must be passed to the **JVM launcher**, placed **before the main class name or `-jar`**. Sub-options are separated by commas, **with no spaces inserted in between**. `jdwp` is the agent library name, not an application name or environment variable.

| Option | Value | Meaning | Default per JPDA/JDK 17 docs |
| --- | --- | --- | --- |
| `transport` | `dt_socket` (common), `dt_shmem` (HotSpot Windows) | Selects the transport for the connection | **Required**, no default |
| `server` | `y` / `n` | `y`: target listens. `n`: target connects to debugger | **`n`** |
| `suspend` | `y` / `n` | `y`: VMStart has policy `SUSPEND_ALL`; `n`: `SUSPEND_NONE` | **`y`** |
| `address` | `port` / `host:port` / `*:port` in socket transport | With `server=y`, where target binds/listens; with `server=n`, where target connects | Required when `server=n`, optional when `server=y` |
| `timeout` | Milliseconds, transport-dependent | Limits wait time for attach/connect on transports that support it | No timeout, though support level should be checked |
| `allow` | IP or subnet for socket when `server=y` | Restricts addresses allowed to connect (transport feature) | `*` when unspecified |

Often-forgotten but important defaults: if you only write `-agentlib:jdwp=transport=dt_socket,server=y,address=5005`, then **`suspend=y` is the default**. The JVM will print a listening message, yet **`main` has still not run** until a debugger connects and resumes it.

You should **explicitly specify `server`, `suspend`, and `address`** in operational configs, even when you could rely on defaults. Check the syntax supported by your current JDK:

~~~bash
java -agentlib:jdwp=help -version
~~~

This command **prints help and exits**, without starting an application. Advanced options like `onthrow`/`onuncaught` can defer agent initialization until an exception occurs; those are specialized configurations for just-in-time debugging and are **not needed** to understand basic startup behavior.

## 4. `server=y` and `server=n`: Who Listens to Whom?

### 4.1 `server=y`: Target JVM Listens, IDE/jdb Attaches

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -cp out MyMain
~~~

Meaning:

1. The target JVM asks the OS to bind/listen on `127.0.0.1:5005`.
2. When the debugger opens in **Attach to remote JVM** mode, the debugger actively connects to host `127.0.0.1` port `5005`.
3. If `suspend=n`, the target **enters `main` immediately** regardless of whether a debugger has attached. A late-attaching debugger may miss code that ran right at startup.
4. Once attached successfully, the debugger can still set breakpoints, suspend threads/VM, inspect stacks/variables, and resume per debug mechanics.

This is the most common direction when running an app locally or in an environment that only allows controlled tunneling.

Example `jdb` in a second terminal:

~~~bash
jdb -attach 127.0.0.1:5005
~~~

If `server=y` and the debugger also chooses **Listen** instead of **Attach**, both sides wait and no connection will happen. The debugger must use the matching connector type.

### 4.2 `server=n`: Debugger Listens, Target JVM Actively Connects

~~~bash
# Start the debugger in listen mode first (on the same machine).
jdb -listen 5005
# In another terminal, have the target connect to the debugger:
java -agentlib:jdwp=transport=dt_socket,server=n,suspend=y,address=127.0.0.1:5005 -cp out MyMain
~~~

Here the target JVM does not open a port waiting for an IDE to attach. It **actively connects to the debugger's listener** at `127.0.0.1:5005`. The debugger side chooses **Listen for debug connection** or the `SocketListen` connector, not Attach.

If the debugger has not opened a listener yet, the JVM may fail immediately during JDWP initialization with a connect/refused error or timeout. **`suspend=n` does not guarantee ignoring connection initialization errors when `server=n`**; it only governs the initial suspend policy once debugging is established. Systems requiring "the app must start even when no debugger is present" should generally use `server=y,suspend=n` in local/dev environments rather than `server=n`.

`server=n` can be useful in certain workflows that actively connect outbound from the target to the debugger, but **it does not make the connection safe by itself**: the listening debugger still requires controlled network access.

### Table of Four Combinations

| `server` | `suspend` | Initialization and execution behavior |
| --- | --- | --- |
| `y` | `y` | Target **listens**, VM pauses **before loading the main class**; app runs only after debugger attaches and resumes |
| `y` | `n` | Target **listens**, app **runs immediately**; debugger can attach later |
| `n` | `y` | Target **connects** to listening debugger, then pauses initially for debugger control/resume |
| `n` | `n` | Target **connects** to debugger; no initial suspend, though JDWP init can still fail if it cannot connect |

**Rule to remember:** `server` is *connection direction*. `suspend` is *initial pause point*. Two independent axes.

## 5. `suspend=y`: Why Are There No Log Lines from main?

With the command:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 -cp out MyMain
~~~

The JVM may print a message like:

~~~text
Listening for transport dt_socket at address: 5005
~~~

At that point **there is no proof that the application has entered `main`, bound its HTTP port, loaded the Spring context, or become ready for traffic**. This is only the debug agent waiting for a connection. Per JDWP semantics, `suspend=y` gives the `VMStart` event the `SUSPEND_ALL` policy before loading the main class; the debugger must connect and send a resume command. Some IDEs may auto-resume after attaching; with `jdb`, after setting breakpoints you can use `cont` to proceed.

This is helpful when you want to stop in `main`, static initializers, bootstrap code, or errors occurring right at startup. However, if `suspend=y` is left enabled accidentally in a container:

- Health/readiness probes can fail because the HTTP server has not initialized yet.
- Deployment can hang in Starting state even though the JVM process exists and the JDWP port is listening.
- The orchestrator's startup timeout can terminate the container before a debugger attaches.
- Application metrics/JFR will not appear yet because application code has not run.

For debugging that does not need to catch startup bugs, choose `suspend=n` to avoid the issues above. For debugging that requires breaking early, use `suspend=y` **deliberately**, in a controlled environment and time window, never leaving it silently enabled in production.

**Important:** `suspend=n` does not prevent the debugger from suspending code later. A `SUSPEND_ALL` or `SUSPEND_EVENT_THREAD` breakpoint after attaching can still pause the application according to the breakpoint's policy; consider active threads and live requests.

## 6. `address`: Loopback, Wildcard, Port, and Network Model

With `transport=dt_socket` and `server=y` in JDK 17+:

| `address` | Where does the target listen? | When to use |
| --- | --- | --- |
| `127.0.0.1:5005` | IPv4 loopback in **the target's host/network namespace** | Good default for local debugging or SSH tunnel on a remote host |
| `5005` | **Loopback** under modern JDWP syntax (JDK 9+) | Concise local debug; specifying the host explicitly is still clearer |
| `localhost:5005` | Hostname `localhost` resolved on target; depends on IPv4/IPv6 | Only when address family and resolver are verified |
| `*:5005` | **Wildcard / all network interfaces** for the transport | Only when cross-namespace/network reachability is needed and access is blocked by an appropriate security layer |
| `127.0.0.1:0` | Loopback with **OS-assigned port**; agent prints actual port | Multi-JVM labs, avoiding port conflicts; read printed port before attaching |
| `[::1]:5005` | IPv6 loopback when JVM/OS supports it | When both debugger and target use IPv6 |

In JDK 17, writing only `address=5005` typically listens on **loopback**, not all interfaces. On some **older JDKs prior to JDK 9** or other VMs, semantics differ; never copy old configs without checking `java -version` and the actual bind. With `server=n`, `address=host:port` specifies **where the target must connect**, not where the target listens.

### Checking the Port per OS

**Linux:**

~~~bash
ss -ltnp | grep ':5005'
~~~

**PowerShell/Windows:**

~~~powershell
Get-NetTCPConnection -State Listen -LocalPort 5005
~~~

If the output shows loopback, connections from another machine **cannot reach it directly** over an external network IP; a tunnel or appropriate bind configuration is required. `localhost` inside a **container** is the container's loopback, not automatically identical to `localhost` on the host or the IDE machine.

Port **5005 is only a common convention**, nothing special in the protocol. An occupied port reports errors such as `Address already in use`/`transport error 202` or related bind messages, and the JVM may fail to start. Pick an unused port or `:0` for labs; do not try to attach a debugger to an HTTP service that happens to use port 5005.

## 7. Java 17+ Lab: Observe Running Immediately vs. Pausing Before main

This lab uses a complete Java program with no Spring/IDE dependencies. Use JDK 17+; it can run on Windows/Linux/macOS with `dt_socket`. Pick an unused port 5005 and bind loopback only. **Never expose the port to the Internet.**

### File `JdwpLaunchDemo.java`

~~~java
public final class JdwpLaunchDemo {
    private static int calculate(int number) {
        return number * number + 1;
    }

    public static void main(String[] args) throws Exception {
        System.out.println("MAIN_STARTED");

        if (args.length == 1 && "--hold".equals(args[0])) {
            System.out.println("WAITING_FOR_ENTER");
            System.in.read();
        }

        for (int i = 1; i <= 3; i++) {
            System.out.println("step=" + i
                    + " value=" + calculate(i));
            Thread.sleep(200);
        }

        System.out.println("MAIN_FINISHED");
    }
}
~~~

**Explanation:** `calculate()` provides an easy-to-observe breakpoint site; `Thread.sleep(200)` simply spaces out output order. The `--hold` argument makes `main` pause at `System.in.read()` **after starting** so learners have time to attach; this is an **application-code wait mechanism**, not JDWP's `suspend=y`. `System.in.read()` requires an interactive terminal stdin; if stdin is already EOF, it may return immediately.

Compile with debug symbols, then run normally:

~~~bash
javac -g JdwpLaunchDemo.java
java JdwpLaunchDemo
~~~

**Exact stdout of the run without JDWP enabled**:

~~~text
MAIN_STARTED
step=1 value=2
step=2 value=5
step=3 value=10
MAIN_FINISHED
~~~

### Experiment 1 — `server=y,suspend=n` (run immediately, attach later)

**Terminal 1:**

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 JdwpLaunchDemo --hold
~~~

When there is no port conflict, the target typically prints in order:

~~~text
Listening for transport dt_socket at address: 5005
MAIN_STARTED
WAITING_FOR_ENTER
~~~

Notice `MAIN_STARTED` appeared **before the debugger attached**. The `WAITING_FOR_ENTER` line comes from Java code, not JDWP.

**Terminal 2:**

~~~bash
jdb -attach 127.0.0.1:5005
~~~

In `jdb`, run:

~~~text
stop in JdwpLaunchDemo.calculate
cont
~~~

Then return to **terminal 1** and press Enter so the program enters `calculate()`. If the debugger is running and the breakpoint is registered, it pauses at `calculate`; use `where` to view the stack, `locals` to view local variables (when the class has debug symbols), and `cont` to continue. Because the loop calls `calculate` three times, you may need to run `cont` three times until `MAIN_FINISHED` appears. Pausing a Java thread with a breakpoint does not depend on the initial `suspend=n`.

If `jdb` does not pause at `calculate`, check the sequence of steps, the breakpoint, `cont`, and pressing Enter in the application terminal. When using an IDE, choose **Remote JVM Debug → Attach**, host `127.0.0.1`, port `5005`, and set the breakpoint matching the source/build.

### Experiment 2 — `server=y,suspend=y` (wait from startup)

Stop the process from Experiment 1 to release the port. **Terminal 1**:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 JdwpLaunchDemo
~~~

The target prints the JDWP listener line, yet **has not printed `MAIN_STARTED`**. **Terminal 2**:

~~~bash
jdb -attach 127.0.0.1:5005
~~~

Set a breakpoint in `main` before resuming if desired:

~~~text
stop in JdwpLaunchDemo.main
cont
~~~

Once the target is resumed by the debugger and hits the breakpoint, `jdb` reports the pause. You can issue `cont` again to continue the program. If you omit `cont` after attaching or the debugger keeps the VM suspended, **`MAIN_STARTED` will not appear yet**; the application is not deadlocked. Clear or resume breakpoints properly and continue.

### Experiment 3 — OS-assigned port to avoid collisions

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:0 JdwpLaunchDemo
~~~

JDWP prints the actual port assigned by the OS, for instance:

~~~text
Listening for transport dt_socket at address: <ASSIGNED_PORT>
MAIN_STARTED
...
~~~

This is a **format pattern**, not fixed stdout: the port changes between runs. Because the demo finishes quickly, to attach in time add `--hold` and use **the printed port**, do not type 5005 blindly. This approach is especially handy in environments running multiple parallel test instances.

### Terminal Differences to Note

In PowerShell, if the shell parses arguments starting with `-` unexpectedly, you can wrap **the entire JVM option** in quotes:

~~~powershell
java "-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005" JdwpLaunchDemo --hold
~~~

With Maven/Gradle/IDEs, add `-agentlib:jdwp=...` to the **JVM options of the actual application process**, not to program arguments or the build tool's JVM when the target is a forked service. Verify the process is listening and the classpath matches the source.

## 8. Remote, Docker, and Kubernetes: The Endpoint Must Be Viewed from the Right Side

### 8.1 Debugging a JVM on a Remote Host via SSH Tunnel

To avoid exposing a debug port to external networks, the target on the remote host listens on **loopback**:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar app.jar
~~~

On the machine running the IDE, create an SSH-authenticated local port forward:

~~~bash
ssh -N -L 5005:127.0.0.1:5005 user@remote-host
~~~

Then the IDE attaches to `127.0.0.1:5005` **on the local machine**. SSH forwards the connection to `127.0.0.1:5005` **on the remote host**. This path does not require JDWP to bind `*:5005`. Control SSH permissions, key/host verification, and local port protection; never open tunnels for unauthorized users.

### 8.2 Docker Containers: localhost Is the Container's Namespace

If Java runs **inside a container** with `address=127.0.0.1:5005`, the port binds to loopback **inside the container**; it is not reachable from the host via `-p` by default. A common pattern when debugging a container locally is:

- Inside the container, if connecting from outside its namespace is strictly necessary, the target listens on `address=*:5005`.
- On the Docker host, **publish only to the host's loopback**: `-p 127.0.0.1:5005:5005`.
- Use an SSH tunnel or equivalent network isolation when the IDE is on another machine. Check Docker/OS firewalls and actual container networking; never assume loopback publishing alone is complete protection in every topology.

Example **illustrating port mapping** (the app image must already exist and the JVM inside must have JDWP enabled):

~~~bash
docker run --rm -p 127.0.0.1:5005:5005 my-debug-app
~~~

This is **only a Docker networking example**, not something that automatically enables JDWP in the image. Never expose `5005` to `0.0.0.0` or the Internet for convenience. In Kubernetes, prefer **`kubectl port-forward` to a debug pod with RBAC** and control bind/network namespaces; how the pod binds internally must be compatible with the port-forward endpoint. Never enable JDWP publicly on a production deployment just to debug a single request.

### 8.3 `server=n` from a Container Out to a Debugger

If the target runs with `server=n`, `address` is **the IP/host and port where the debugger is listening as seen from the container**. `127.0.0.1` in this case is *the container itself*, not your laptop. Verify routing, DNS, the listener, firewalls, and network policies; do not flip `server=n` to `y` just because a connection failed without understanding the intended direction.

## 9. Security: JDWP Is a JVM Control Channel, Not an HTTP API

**Never expose a JDWP port to the Internet or untrusted networks.** Typical JDWP protocols/debug agents lack application-level authentication/authorization to guard debugging operations such as inspecting stacks/objects, altering execution state, and potentially **executing code under the process's privileges**. An unauthorized JDWP connection carries very high risk.

Safer choices in priority order:

1. Enable JDWP only in dev/test environments or approved debug sessions, keeping its enabled duration as short as necessary.
2. Default to `server=y,address=127.0.0.1:5005`; use an SSH tunnel or protected remote-access mechanism when remote connectivity is required.
3. If wildcard binding `*:5005` is unavoidable inside a container/namespace, block access with network policies, firewalls, RBAC-protected port-forward, and expose only to host loopback; consider adding `allow` as defense-in-depth, not a replacement for security controls.
4. Never copy `address=*:5005,allow=*` examples into production; `allow=*` means no source restriction under that option.
5. Keep secrets out of breakpoints/logs; a debugger can inspect variables, environment, and sensitive process data. Control who is authorized to attach.
6. After debugging, **stop the debug process or restart without the agent**; tear down forwarding, update deployment configs, and verify the port is no longer listening. Do not leave debug flags baked into build images or uncontrolled service launch scripts.

Enabling JDWP can also affect runtime behavior via breakpoints, single-stepping, and suspend-all capabilities. Using it on live traffic requires managing latency/timeout risks.

## 10. Diagnose Errors Before Changing Configs

| Symptom | Possible explanation | How to verify/resolve |
| --- | --- | --- |
| `Listening for transport dt_socket...` appears, but no main logs | `suspend=y` is waiting for a debugger; or code is paused at a breakpoint | Check launch options; attach to the right port and resume via IDE/`cont` |
| JVM fails to start, `Address already in use` or bind failure | Another process already uses the port, or bind address does not exist in namespace | Check `ss`/`Get-NetTCPConnection`, pick another port/`:0`, bind an existing interface |
| `Connection refused` when IDE attaches | No JDWP listener at endpoint, wrong port, JVM exited, misused `server=n`, or container loopback | Check target stdout, PID, port/socket state, JDK, and connector |
| Remote attach times out while local attach works | Loopback bind, firewall/NAT, or namespace blocks remote reachability | Keep loopback and use an authorized tunnel; bind wildcard only when protected |
| IDE Listens, target has `server=y` | **Both are waiting** | Switch IDE to Attach or target to `server=n` depending on the chosen model |
| IDE Attaches, target has `server=n` | **Both try to connect** | Switch IDE to Listen or target to `server=y` |
| Target `server=n` fails before main | Debugger not listening yet or wrong host/port; JDWP initialization failed | Start debugger listener first, verify route and timeout |
| Attach succeeds, but breakpoint never hits | Code already ran due to `suspend=n`, wrong source/class/build, missing line info, breakpoint off execution path | Use `suspend=y` for startup, build with `javac -g`, verify source/jar and call path |
| Debugger reports VM suspended, service times out | Suspend-all threads or breakpoints stopped application progress | Resume VM/threads properly; do not leave long-lived production pauses under load |
| Port is open, yet HTTP/curl fails | `dt_socket` speaks **JDWP packets**, not an HTTP server | Use `jdb` or an IDE with a JDWP connector |
| Disconnect message appears, yet app keeps running | `suspend=n` and debugger detached; VM continues running per its state/activity | Check process, logs, and breakpoint/suspend state; do not assume detach always stops the app |
| JDWP options behave differently across JDKs | Defaults/bind semantics/available transports vary by JDK or vendor | Record `java -version`, run `-agentlib:jdwp=help`, and test binding on the exact JDK |

For Spring Boot, insert the VM option **before** `-jar`. If the debug flag appears in Gradle/Maven logs yet the app is not listening, the agent is likely attached to the **build tool process** rather than the forked Java process running the service. With IDEs, use the built-in **Remote JVM Debug** configuration rather than launching an extra `jdb`.

## 11. Practice Checklist

- [ ] Identified Java/JDK vendor + version (prefer JDK 17+ per lab), the right process, and the right JVM arguments.
- [ ] Understood `server=y` means target listens / debugger attaches; `server=n` means target connects / debugger listens.
- [ ] Explicitly wrote `suspend=y` to catch startup or `suspend=n` to run immediately; did not rely accidentally on the default `y`.
- [ ] Chose `address` per **network namespace**: local loopback, wildcard only when controlled; did not confuse the HTTP app port with the JDWP port.
- [ ] When using containers/remote hosts, verified bind, routing, firewalls, SSH tunnels or port-forward, and access scope.
- [ ] Checked ports before/after running; no unauthorized listener on public interfaces.
- [ ] Confirmed via stdout that `MAIN_STARTED` appears before attaching with `suspend=n`, and does not appear before resuming with `suspend=y`.
- [ ] Used the right connector type in IDE/`jdb` and verified breakpoints in real code, without confusing attaching with hitting a breakpoint.
- [ ] Tested behavior when the debugger is absent, especially for `server=n`.
- [ ] Removed the JDWP agent and port-forwarding when finishing the debug session; did not expose secrets or impact live traffic.

### Official References

- Oracle JDK 17 — JPDA, transports, connectors, sub-options `server`/`suspend`/`address`, and examples: https://docs.oracle.com/en/java/javase/17/docs/specs/jpda/conninv.html
- Oracle JDK 17 — `jdb`, attach, listen, and breakpoints: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdb.html
- Oracle JDK 17 — Java launcher and `-agentlib`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle JDK 21 — JPDA specification for newer Java versions: https://docs.oracle.com/en/java/javase/21/docs/specs/jpda/conninv.html

**Key takeaway:** `server` chooses **who initiates the connection**, `suspend` chooses **whether to pause the VM at startup**, and `address` specifies **the right endpoint for that role**. Understanding these three factors independently prevents most "debugger cannot attach," "JVM hangs on startup," and "accidentally exposed JDWP to strangers" mistakes.
