# 19.4 Attaching or Launching with jdb and Managing Session Lifecycle

## 1. Goal: Connect to the Right JVM, Control the Right Lifecycle

**`jdb` (Java Debugger)** is the command-line debugger bundled with the JDK, using the **Java Debug Interface (JDI)** to communicate with a target JVM through the **Java Platform Debugger Architecture (JPDA)**. It lets you set breakpoints, view stacks/local variables, inspect threads, single-step, and resume execution without an IDE.

However, proper debugging is not just "getting a `jdb` prompt open." You must determine:

- **Who creates the target JVM?** Does `jdb` *launch* a new process or merely *attach* to an already running application?
- **Who listens for the connection?** The target JVM with `server=y`, or the debugger with `server=n`?
- **Is the application running or waiting?** `suspend=y/n` controls waiting before passing startup; breakpoints can also pause threads/VM afterward.
- **What happens when done?** `cont`/`resume`, `clear`, and `quit` have different implications for stopping the application or ending the session.
- **What if the connection drops?** The debugger and the JVM are separate processes/entities; never infer process status merely from a `jdb` window closing.

This lesson focuses on **JDK 17+ and HotSpot/JDWP sockets on a development machine**; syntax references Oracle JDK 21. Certain connectors or specific behaviors depend on platform, JDK, and how the service is run.

**Expected outcome:** independently run both *launch* and *attach* workflows, explain the relationship among debugger/JVM/port/PID, observe and control a breakpoint, and close the session cleanly without accidentally hanging or killing a critical application.

## 2. Three-Layer Model: JDI, JDWP, Transport

```text
Debugger terminal                     Application JVM (debuggee)
+------------------+                 +---------------------------+
| jdb              |                 | Java code + threads       |
| breakpoint cmds, |                 | JDWP agent                |
| step, cont, quit |                 |                           |
|     JDI          |                 | JVM TI / runtime          |
+---------+--------+                 +-------------+-------------+
          |                                        |
          +----------- JDWP messages --------------+
                   over dt_socket TCP
                     (or other transport)
```

- **JDI**: the API on the debugger side to control/observe the target VM. `jdb` is a client application using JDI; the `jdb` interface is not inherent to every JVM.
- **JDWP**: the protocol exchanging requests and events, such as setting a breakpoint or reporting a suspended thread.
- **`dt_socket`**: the TCP-based transport. Usually `jdb` and the JVM meet via `host:port`.
- **JDWP agent**: loaded into the target JVM via `-agentlib:jdwp=...` when attaching to a program prepared for debugging.

Clearly distinguish three types of identifiers:

| Identifier | Example | Role |
| --- | --- | --- |
| JVM **PID** | `12345` | OS process identifier; used to verify the right application, logs, `jcmd`, etc. |
| **JDWP address** | `127.0.0.1:5005` | Debugger connection address; `jdb -attach` uses an **address**, not a PID |
| **Main class name** | `JdbSessionDemo` | Needed in **launch** commands so the new JVM knows which program to run; attach does not re-run `main` |

**Common mistake:** `jdb -attach 12345` does not mean "attach to PID 12345" on Linux/macOS. With the default socket connector, `12345` in that syntax is interpreted as a **JDWP address/port**; if a JVM with PID 12345 does not have JDWP enabled, this command cannot create a debug session on its own.

For certain advanced connectors, JDI has `com.sun.jdi.ProcessAttach` accepting `pid`, but its requirements/mechanisms differ from standard socket attach. When learning `jdb`, start from explicit `-attach host:port`.

## 3. Four Connection Modes to Distinguish

| Mode | How does the target JVM start? | Listening side | Common command | When to use |
| --- | --- | --- | --- | --- |
| **Launch (default)** | `jdb` spawns a new JVM for the specified class | Launch connector manages connection | `jdb -classpath . JdbSessionDemo` | Control before `main` runs |
| **Immediate launch (`-launch`)** | `jdb` spawns a new JVM immediately, pauses before loading first app class | Launch connector | `jdb -launch -classpath . JdbSessionDemo` | Want target ready in paused state, use `cont` instead of `run` |
| **Attach** | JVM **already started with JDWP agent** | Usually target JVM: `server=y` | `jdb -attach 127.0.0.1:5005` | Investigate a running application without launching a copy |
| **Listen / reverse connect** | Target JVM opens connection to debugger | `jdb`: listener, target `server=n` | `jdb -listen 5006` and JVM `server=n` | Debugger must be the listening side, e.g., due to network constraints |

**`server=y/n` belongs to the target JVM's agent config**, and does **not** mean `jdb` automatically runs on the server or application client. Both sides can be on the same machine, in containers, or on two machines over a secured network.

**Remote connections must be treated as privileged operations.** JDWP provides access to view data and execute commands through the debugger, not an HTTP endpoint with default user authentication. Bind only to loopback in exercises; never set `address=*:5005` on the Internet or shared networks.

## 4. Java 17+ Program for Practice

The program below stays alive long enough for you to attach, has a small method for breakpoints, uses no frameworks, and prints only a few lines so the terminal stays readable.

Save the **entire** code as **`JdbSessionDemo.java`**:

```java
public final class JdbSessionDemo {
    public static void main(String[] args)
            throws InterruptedException {
        int rounds = args.length == 0
                ? 60
                : Integer.parseInt(args[0]);
        if (rounds < 1 || rounds > 600) {
            throw new IllegalArgumentException(
                    "rounds must be from 1 to 600");
        }

        System.out.println("PID=" + ProcessHandle.current().pid());
        System.out.println("rounds=" + rounds);

        for (int i = 1; i <= rounds; i++) {
            int score = calculate(i);
            if (i <= 3 || i % 10 == 0) {
                System.out.println("tick=" + i
                        + " score=" + score);
            }
            Thread.sleep(1_000);
        }

        System.out.println("completed");
    }

    private static int calculate(int value) {
        int squared = value * value;
        return squared + 10;
    }
}
```

Compile with **full debug info**:

```bash
javac -g JdbSessionDemo.java
```

`javac -g` writes line/source/local-variable metadata into the bytecode. Without proper local variable info, `locals` in `jdb` may fail to display expected variables even though the program runs normally. Compile **the exact source file and exact class build** used when debugging.

Run standalone to verify:

```bash
java JdbSessionDemo 10
```

With `rounds=10`, the **deterministic logical output lines** include:

```text
PID=<actual process PID>
rounds=10
tick=1 score=11
tick=2 score=14
tick=3 score=19
tick=10 score=110
completed
```

The PID line changes on each run; `<actual process PID>` is an **annotation**, not verbatim stdout. The `score` lines follow `value * value + 10`. With `Thread.sleep(1_000)` between iterations, `rounds=10` takes around 10 seconds, or longer if the machine is busy or the debugger pauses it.

If you need a longer attach window, use `120` or `180` rounds. Avoid infinite loops in demos because verifying session completion and cleaning up processes is harder.

## 5. Workflow A — jdb Launches a New JVM

This is the clearest approach when you want to debug from the beginning. Open a terminal in the directory containing `JdbSessionDemo.class` and run:

```bash
jdb -classpath . JdbSessionDemo 20
```

Command breakdown:

- `jdb` runs the **debugger process**.
- `-classpath .` tells the **target JVM** to find classes in the current directory; it is not a separate path for `.java` files.
- `JdbSessionDemo` is the class name containing `main` (do not append `.java`).
- `20` is passed to `main(String[] args)` as `rounds`; it is not a breakpoint timeout.
- In default launch mode, you can configure breakpoints at the prompt and then use **`run`** to launch/execute the target per `jdb`'s launch model.

At the `jdb` prompt, enter in order:

```text
help
stop in JdbSessionDemo.calculate
run
```

`stop in ...` sets a method-entry breakpoint for `calculate`. When the target hits the breakpoint, `jdb` pauses per the event's policy; the prompt may display the thread name and frame count and need not match any exact example verbatim. Next, inspect:

```text
where
locals
next
locals
```

- `where` prints the current thread's stack, confirming execution is inside `calculate`.
- `locals` lists local variables in the frame when bytecode has debug info and the thread is suspended. At method entry, `value` already has a value, whereas `squared` may not be assigned yet; after `next` steps past the assignment, it receives its value.
- `next` executes the next line **in the current frame**; `step` enters called methods when applicable. Exact line stepping may vary by compiler/JVM/line mapping; watch the current line in the prompt.

To avoid hitting this breakpoint on **every** subsequent loop iteration, clear it and continue:

```text
clear JdbSessionDemo.calculate
cont
```

`clear` removes the installed breakpoint; `cont` resumes suspended execution. If you forget to clear it, the next call to `calculate` will pause again and require repeated `cont` commands. To list active breakpoints, enter `stop` or `clear` without arguments depending on `jdb` version support.

Once the target completes all 20 rounds, the app prints `completed` and exits normally. The debugger may report that the target VM exited; **this is the target terminating**, not evidence that `jdb` or the shell was forcibly killed. Exit the debugger UI with `quit` when needed.

### The `-launch` Variant: No Extra `run`

```bash
jdb -launch -classpath . JdbSessionDemo 20
```

Oracle JDK 21 documents that `-launch` starts the debugged application **immediately upon starting `jdb`**, with the target suspended before the application begins executing. Thus, in this session:

```text
stop in JdbSessionDemo.calculate
cont
```

`-launch` **eliminates the need for `run`**. Mixing `run` from the default launch workflow into a `-launch` session can confuse learners about target state or trigger unintended restarts.

**Launch indicator:** No manual JDWP port or prior PID is needed. The debugger spawns the new JVM; when configuring session teardown, check the launched process's status separately (see section 10).

## 6. Workflow B — jdb Attaches to a Running JVM

**Attach** does not spawn a duplicate application; it connects to an existing JVM. You **must prepare the JDWP agent** when starting the target process in this lesson's simple workflow.

### Step 1 — Start the target JVM with JDWP enabled, without suspending

Open terminal A and run:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 JdbSessionDemo 120
```

Key parameters:

| Parameter | Role | If misunderstood |
| --- | --- | --- |
| `-agentlib:jdwp=...` | Loads the JDWP agent inside the target JVM | `jdb` cannot automatically debug an arbitrary unprepared JVM |
| `transport=dt_socket` | Uses a TCP socket | Not a Unix domain socket file or HTTP |
| `server=y` | **Target JVM listens** for debugger connections | Does not turn the Java app into an HTTP server |
| `suspend=n` | Allows the app to start running without a debugger | Can miss code paths executed before attaching |
| `address=127.0.0.1:5005` | Binds only loopback port 5005 | Target's PID is **not** 5005 |
| `JdbSessionDemo 120` | Runs 120 rounds, giving enough time to attach | Argument 120 is unrelated to debugger timeout |

Terminal A may print the agent listening message alongside `PID=...` and `tick=...` lines. Keep terminal A open to observe **proof that the JVM continues running** after the debugger detaches.

**If using a different port:** update both the Java and `jdb` commands. If a port is in use, JDWP may fail to bind; resolve the conflict in the lab environment rather than connecting to an unknown process.

### Step 2 — Connect with jdb

Open terminal B:

```bash
jdb -attach 127.0.0.1:5005
```

Or with the default loopback address in supported environments:

```bash
jdb -attach 5005
```

**This attaches by socket address.** Do not pass `JdbSessionDemo` on the command line, because the target is already running its `main`. If attach succeeds, `jdb` presents a prompt and you can set breakpoints while the application is alive.

### Step 3 — Control the attach session

At the prompt:

```text
threads
stop in JdbSessionDemo.calculate
```

Wait for the next iteration to call `calculate`. When the breakpoint pauses:

```text
where
locals
next
locals
clear JdbSessionDemo.calculate
cont
```

Because of `suspend=n`, the target ran prior to attaching; if the program finishes before `jdb` connects, a connection error is normal. Re-run with higher `rounds` **in the lab environment**; `jdb` cannot replay lines that already executed.

### Step 4 — Leave the session without shutting down the service

If the goal is to stop observing and **let the target keep running**, you must:

1. Verify no pausing breakpoints or unwanted watchpoints remain; `clear`/`unwatch` any you created.
2. If the target is paused at a breakpoint, run `cont`; if you manually ran `suspend` on threads/VM, issue the matching `resume`. Do not treat "closing the terminal window" as safe state management.
3. Run `quit` (or `exit` per `jdb` internal command) to **exit the debugger**. In typical attach mode, disconnecting releases debugger-owned suspensions/event requests and the target continues running if work remains. However, exiting JDB **does not guarantee** the target was unaffected by timeouts, app errors, or another debugger/process.
4. Watch terminal A: does the JVM continue printing `tick` and eventually `completed` per its lifecycle? Check PID/health checks for a real service.

Never confuse `quit` inside **jdb** with an application's `System.exit()` or the JDI API's `VirtualMachine.exit(int)`. The former closes the debugger UI; the latter tells the target VM to terminate and is not a "graceful detach."

## 7. `suspend=y` — Waiting for the Debugger from Startup

Sometimes you need a breakpoint **before** `main` passes the code under investigation. When launching a separate target and attaching afterward, use:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 JdbSessionDemo 20
```

The default for `suspend` in JDWP config can be `y` if omitted; **write it explicitly** to avoid confusion. With `suspend=y`:

- The JVM initialized the agent and is waiting for a debugger; the program **has not executed `main` normally yet**.
- In terminal B, run `jdb -attach 127.0.0.1:5005`, verify connection, and set `stop in JdbSessionDemo.calculate`.
- Use `cont` to let the target continue. Do **not** use `run` in an attach session because `main` was launched by `java` in terminal A, not by `jdb`.

If terminal A only says "Listening for transport..." and never prints `PID=...`, that can be the **intended waiting state**, not an application deadlock. However, on a real service, `suspend=y` can cause health/readiness probes to fail while waiting for a debugger, triggering a restart loop; use only during controlled maintenance windows.

**Note:** Some environments/debuggers may handle resuming the `VMStart` event differently; read the prompt and actual state, and run `cont` when the target is waiting.

## 8. Listen Mode: Reversing Who Initiates the Connection

In standard attach mode, the target is the **JDWP server** (`server=y`) and `jdb` actively connects. **Listen** reverses the direction: `jdb` waits, and the target opens a connection to the debugger via `server=n`. Lab setup on the same machine:

**Terminal B — start the debugger in listen mode first:**

```bash
jdb -listen 5006
```

**Terminal A — start the target second:**

```bash
java -agentlib:jdwp=transport=dt_socket,server=n,suspend=y,address=127.0.0.1:5006 JdbSessionDemo 20
```

- `server=n` indicates the target JVM is the **outbound-connecting side**, so `jdb` must listen first.
- `address` points to the endpoint where `jdb` is listening. If no listener is up or the network is unreachable, the target may fail to connect/start per timeout config.
- With `suspend=y`, the target pauses at startup via JDWP; set breakpoints once `jdb` connects and run `cont`.
- `-listenany` can pick an automatic listener address in JDI config, yet while learning use an explicit port; do not mistake "any" for allowing connections across all network interfaces.

This is a **different connection workflow**, not attaching over port `5005` from section 6. Do not start a JVM with `server=y` while waiting with `jdb -listen` expecting them to find each other: when both listen, neither side initiates the connection.

In environments with firewalls/NAT, either direction still requires an authorized network path, network-layer authentication, and endpoint restrictions. Never turn JDWP into a public port.

## 9. Advanced Connectors and CLI Flags to Use Properly

`jdb` provides connector shortcuts as well as explicit connector specifications. To list connectors available in **your JDK**:

```bash
jdb -listconnectors
```

Equivalent attach via explicit socket connector:

```bash
jdb -connect com.sun.jdi.SocketAttach:hostname=127.0.0.1,port=5005
```

To debug an application where **`jdb` spawns a new JVM**, use the shortcut `jdb JdbSessionDemo` or the `com.sun.jdi.CommandLineLaunch` connector with appropriate `main` (argument names and quoting vary by shell). You do not need explicit connectors just to run a basic demo.

**Flags worth distinguishing:**

- `-classpath .`: classpath for the **debuggee** to load bytecode in launch mode; when attaching, the classpath belongs to the already running target and is not altered by `jdb` flags.
- `-sourcepath <path>`: search path for **`.java` sources** for `list`/viewing source lines. It does not replace the classpath used to locate compiled classes.
- `-J-Xmx256m`: passes `-Xmx256m` to the JVM **running `jdb`** (the debugger).
- `-R-Xmx256m`: passes an option to the **target JVM launched by `jdb`**, per the JDK 21 man page.
- `-listconnectors`: lists available connectors; do not use this in place of `JFR.check` or `jcmd`.
- `-attach host:port`: attaches via address without creating a new JVM.
- `-launch`: launches target immediately, skipping `run` required by the default launch workflow.

**With packages:** if a class resides in `com.example.debug`, run `jdb -classpath ... com.example.debug.JdbSessionDemo` using its fully qualified name. Set breakpoints with the fully qualified class name if simple names collide. The demo uses the default package to minimize setup steps, not as a package recommendation for production.

## 10. Session Lifecycle: Seven States to Track

```text
[No target yet]
        |
        +-- jdb launch ---------+
        |                       |
        +-- java -agentlib JDWP +---> [Target exists]
                                       |
                            [Not connected / listening]
                                       |
                             JDWP connection succeeds
                                       |
                               [JDB connected]
                                 /        \
                       breakpoint         cont/resume
                          |                   |
                     [Target paused] -----> [Target running]
                          |
                     step/next/where
                                       |
                         +-------------+--------------+
                         |                            |
                    quit/disconnect              Target exits
                         |                            |
                    [Debugger closed]        [VMDeath/disconnect]
                         |                            |
                [Target may stay alive]      [Target terminated]
```

**Monitor two separate entities:** (1) **the `jdb` process**, and (2) **the target JVM process**. With attach, the normal goal is **closing the debug connection without stopping the service**; with launch, the process was created by the debugger and its lifecycle may be tied to that session, so **verify the target PID** instead of guessing.

| Action | Immediate effect | Follow-up check |
| --- | --- | --- |
| `stop in ...` | Registers method breakpoint; does not necessarily pause target immediately | Wait for code path execution; watch for breakpoint notice |
| `stop at Class:line` | Registers breakpoint by source line | Verify class has proper line info and line exists |
| `step` / `next` | Executes one step from paused state | Inspect stack/locals after each step |
| `cont` | Resumes program after breakpoint/step | Watch whether another breakpoint intercepts it |
| `suspend` | Puts VM/thread in suspended state per command | Use matching `resume`; never leave service hung |
| `clear ...` | Removes specified breakpoint | Run `clear`/`stop` to confirm |
| `quit` / `exit` in jdb | Closes debugger session/UI | Inspect target PID, output, and health independently |
| Program `return`s from `main` or `System.exit` | JVM enters termination per application logic | Subsequent debug commands may report `VMDisconnected` |
| `kill -9` or forcibly terminating target | Target killed by OS; not a detach | Check business impact; never use as normal session exit |

**A breakpoint with suspend-all policy can pause many threads**, not just the method/thread you care about. On a live service, lingering at the prompt too long can time out requests/health checks and mislead observers into thinking "the incident got worse." Minimize pause duration and use less intrusive tools when needed.

### Do Not Equate quit with JDI `VirtualMachine.exit(int)`

Per the JDI API, `VirtualMachine.dispose()` closes the debugger channel, cancels event requests, restores threads suspended by the debugger, and allows the application to continue within that mechanism. `VirtualMachine.exit(int)`, by contrast, requests **abrupt termination of the target VM**. These are two distinct concepts even though `jdb`'s internal command can also be named `exit`.

**Safe management practice:** use `quit` to close the debug UI, and still verify whether the target JVM remains running. Never rely on closing a terminal or dropping the network to guarantee recovery.

### Scenario A — Attaching to a Traffic-Serving Service

- Record the exact timestamp and PID/instance/service before attaching.
- Limit suspend-all breakpoints and avoid changing variable values in production without strict controls.
- Once done inspecting, clear breakpoints, `cont`/resume, `quit`, and check health/latency and continued request processing.
- If the JDWP agent remains enabled, **the debug port is still a privileged attack surface**; quitting `jdb` does not disable the agent. Manage via restart/configuration per deployment procedures to close the port.

### Scenario B — jdb Launching a Test Process

- `run` starts execution; `cont` resumes when paused.
- Let the program finish normally whenever possible; record exit code/status from the target.
- If exiting the debugger while the target is still alive, verify whether the process is still running or stopped per connector/implementation; do not assume the target is definitely killed or definitely still running.
- Do not leave stray test processes bound to debug ports or holding unintended resources.

## 11. Session Teardown Checklist Without Leaving "Hung Processes"

Before ending debugging, ask yourself:

1. **What was the original goal?** Production attach to observe, or launching a demo allowed to exit?
2. **Are any threads still paused by breakpoints/`suspend`?** Use `where`, `threads`, and prompt status to check.
3. **Are unnecessary breakpoints/watchpoints cleared?** Use `clear`/`unwatch` if configured.
4. **Did you `cont` or `resume` in the right context?** Do not leave a service suspended and walk away.
5. **What will the command close?** `quit` closes `jdb`; it is not equivalent to `System.exit`. Verify against the real process.
6. **Is JDWP still open after `jdb` exits?** A `server=y` JVM may keep listening. Check your environment's security policy.
7. **Were any runtime changes made that need reverting?** Variables edited with `set`, method calls via `print/eval`, triggered side effects, and thread states can all alter app behavior.
8. **Are incident notes complete?** Timestamp, PID, build, port, breakpoints, stack, control actions, and post-exit service status.
9. **If disconnected unexpectedly:** inspect JVM/agent/port and thread state independently; do not blindly send commands to a different process that may have reused the port.
10. **If the process should remain running:** verify logs/health/metrics continue progressing and the target PID matches; in a cluster, verify the right instance too.

## 12. Safety When Debugging Over Networks, Containers, or Production

**JDWP must never be treated as a public API port.** Anyone connecting gains privileges to inspect internal JVM data and potentially control behavior/evaluate expressions. Therefore:

- In labs, prefer `address=127.0.0.1:5005`; do not arbitrarily change to `address=*:5005` or bind `0.0.0.0` on untrusted networks.
- If remote debugging is unavoidable, use a **protected administrative channel** (such as an SSH tunnel or trusted network zone) with proper authorization; never publish JDWP ports directly.
- Check network namespaces: a JVM in a container may listen on the **container's** loopback, not the host's loopback. `jdb` on the host will not see the port without configured forwarding.
- Port-forwards/tunnels must use approved access mechanisms, restrict users/time, and be revoked after investigation.
- `suspend=y` can cause containers to fail readiness probes; the orchestrator may restart the process before a debugger even attaches.
- Breakpoints with `suspend-all` can impact every request being served on that instance; assess blast radius beforehand.
- `-agentlib:jdwp=...` is configured **on the JVM**, not something `jdb` can inject into any arbitrary PID on its own. Restarting an app to enable the agent must follow deployment procedures.
- `.class` and `.java` files used in debugging must match the build; never send source code or sensitive data to unauthorized machines.
- On newer JDKs with virtual threads, thread lists may be incomplete in `jdb`'s default mode. JDK 21 provides `-trackallthreads` when broader visibility is needed, though it can add overhead/load; never enable unconditionally on systems with huge numbers of virtual threads.

In production, consider **JFR, metrics, tracing, and thread dumps** before using breakpoints that pause the entire VM. `jdb` is capable of mutating process state; a debug session is not a purely passive observation.

## 13. Troubleshooting Connection and State Errors

| Symptom | Common cause | Check and resolution |
| --- | --- | --- |
| `jdb -attach 5005` fails to connect | Target lacks JDWP, wrong port, process exited, or firewall/namespace | Verify target command line, PID, listening address, port, and process state |
| Target does not print `PID=...` after `java` | `suspend=y` makes JVM wait for debugger at startup | Attach to the right port and `cont`; or use `suspend=n` for immediate execution |
| JDWP reports inability to bind address | Port already in use by another process or address unavailable | Pick a valid port on the lab host and change **both** target and `jdb` |
| `jdb` prompt appears, yet breakpoint never hits | Code path already ran, class not loaded yet, different overload, wrong breakpoint name | Check `stop`, `methods`, full class name, retry with `suspend=y` if needed |
| `locals` empty or "no local variables" | Missing debug info or not in the right stack frame | `javac -g`, right class build, `where`/`up`/`down` |
| Breakpoint triggers repeatedly making service seem hung | Method inside a loop, forgot `clear` or `cont` | Clear, cont, use shorter scenarios or conditional stops |
| `run` does nothing in attach mode | Attach mode does not spawn a target JVM | Use `cont` when paused; to start fresh, launch a separate JVM |
| `jdb` closes, yet service is not running | Target crashed/exited, other suspension remains, network/process issue | Check PID/health and thread state independently |
| `jdb` connects and immediately disconnects | Target exited, port changed, network lost, attach policy error | Check target logs, exit status, JDK compatibility, and actual port |
| Debugger source displays wrong line numbers | `.java` mismatches running `.class` | Sync artifact/source, debug symbols, `-sourcepath` |

**Avoid "fixing" the wrong thing:** If the target is waiting on `suspend=y`, do not reach for `kill -9` first. That may be the expected state. If the target has actually died, a JDWP connection cannot resurrect the JVM or recover lost stacks.

### Minimizing Investigation Impact

- Prefer breakpoints in low-traffic code paths or on test instances.
- When paused, inspect only what is needed and `cont` promptly.
- For tight loops, clear the breakpoint before `cont` to avoid repeated pauses.
- Do not run `eval`/`set` on business objects when passive observation suffices.
- If multiple debuggers/IDEs exist, ensure the agent permits only valid connections per implementation; avoid tools competing to control the target.

## 14. Comparing Three Sample Dialogues

### A. Launch for a unit-like demo

Terminal:

```bash
javac -g JdbSessionDemo.java
jdb -classpath . JdbSessionDemo 20
```

Inside `jdb`:

```text
stop in JdbSessionDemo.calculate
run
where
locals
next
clear JdbSessionDemo.calculate
cont
```

**Explanation:** The target JVM is spawned by `jdb`; `run` is part of the launch workflow; the breakpoint catches the first call. Wait for the program to finish per its logic and verify status.

### B. Attach to a running JVM

Terminal A:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 JdbSessionDemo 120
```

Terminal B:

```bash
jdb -attach 127.0.0.1:5005
```

Inside `jdb`:

```text
stop in JdbSessionDemo.calculate
where
locals
clear JdbSessionDemo.calculate
cont
quit
```

**Explanation:** The JVM is started outside the debugger. `quit` exits `jdb` after resuming execution; keep watching terminal A to confirm the target keeps running. Do not use `run` to restart `main` when attaching.

### C. Reverse connect with listener

Terminal B:

```bash
jdb -listen 5006
```

Terminal A:

```bash
java -agentlib:jdwp=transport=dt_socket,server=n,suspend=y,address=127.0.0.1:5006 JdbSessionDemo 20
```

Inside `jdb`:

```text
stop in JdbSessionDemo.calculate
cont
```

**Explanation:** The debugger listens first; the target connects outbound to that address. `server=n` does not mean JDWP is disabled. When done, know which JVM remains running and whether it is still listening for unintended connections.

## 15. Common Mental Mistakes

1. **Confusing port with PID:** `jdb -attach 5005` targets a JDWP address, not OS PID 5005 automatically.
2. **Trying to attach without JDWP enabled:** plain `java` does not open a remote-debugger port by itself.
3. **Mistaking `server=y` for "HTTP application server":** it is the JDWP agent's connection-listening mode.
4. **Setting both sides to listen mode:** nobody initiates the connection; understand the `server=y/n` direction.
5. **Forgetting `suspend=y`:** the app has not logged yet because it awaits a debugger, not automatically a deadlock.
6. **Trying `run` in an attach session:** the target is already running; `run` belongs to `jdb`'s launch workflow.
7. **Forgetting `cont` after a breakpoint:** the target stays paused and service health can degrade.
8. **Not clearing breakpoints inside loops:** continuing immediately pauses again, making the app appear stuck.
9. **Using `quit` as a target-kill command:** debugger and debuggee have separate lifecycles.
10. **Assuming closing the terminal is enough:** you must verify threads and target PID/health have recovered.
11. **Exposing JDWP ports publicly:** exposes JVM control privileges, a severe risk.
12. **Expecting local variables without `javac -g`:** bytecode may lack debugging metadata.
13. **Using `-sourcepath` instead of `-classpath`:** one locates sources, the other locates compiled classes when launching.
14. **Not distinguishing `-J` from `-R`:** they affect two different JVMs.
15. **Not verifying build/class names:** a breakpoint might be placed on a method that does not exist in the target.
16. **Concluding a dropped debug session means the app died:** a connection error does not prove the target terminated.
17. **Silently mutating variables/state just to "test an idea":** evaluating methods or setting fields can cause real side effects.
18. **Ignoring container namespaces:** loopback inside a container is not necessarily the host's loopback.
19. **Treating a debug session as zero-cost observation:** suspend-all and breakpoints/stepping slow real-time execution.
20. **Not keeping session notes:** later nobody knows who set which breakpoint, when, and whether it was cleared.

## 16. Self-Check Exercises

**Question 1 — distinguishing identifiers.** A JVM has PID `4112`, and JDWP listens on `127.0.0.1:5005`. What is the right attach command?

**Answer:** `jdb -attach 127.0.0.1:5005`, or `jdb -attach 5005` if the tool defaults to loopback. `4112` is not a socket address.

**Question 2 — startup state.** A JVM starts with `server=y,suspend=y`, prints "Listening for transport...", yet has not printed `PID=...` from `main`. Could this be a bug?

**Answer:** It could be the completely valid debugger-waiting state. Connect, set breakpoints, and run `cont` to proceed before calling it an error.

**Question 3 — launch lifecycle.** Running `jdb JdbSessionDemo 20`, wanting to set a breakpoint before `main` runs, do you use `run` or `cont`?

**Answer:** With default launch, set `stop in ...` and then `run` per the workflow. If using `-launch`, the target has already launched and paused before the application class starts, so set the breakpoint and then `cont`.

**Question 4 — attach lifecycle.** You paused a request-serving JVM at a breakpoint. Should you run `quit` immediately "to avoid affecting it"?

**Answer:** Clear breakpoints, let threads/VM resume to a valid state, then quit and **check health**. Disconnecting usually releases debugger-held suspensions, yet does not replace verifying the service.

**Question 5 — connection direction.** Must `jdb -listen 5006` pair with target `server=y` or `server=n`?

**Answer:** `server=n`: the target actively connects to `jdb`'s listener. With `server=y`, the target also waits for a debugger to connect, so both sides would be listening.

**Question 6 — safety.** Why should `address=*:5005` not be used in production without protection?

**Answer:** A JDWP port grants deep control over the JVM; it is not an endpoint with default user authorization. Only open it within authorized network zones for the needed duration.

**Hands-on:** complete two sessions with the demo, one `launch` and one `attach`. For each session, record **who started the target**, PID, JDWP address (if any), state before/after the breakpoint, the resume command, how you exited the debugger, and evidence that the target remained alive or exited as intended. For attach, watch terminal A keep printing `tick` after `quit`. Explain in your own words why the same `quit` command is not proof that the app was killed.

## 17. Official References

- [Oracle JDK 21 — The `jdb` Command: launch, attach, `-launch`, `-listen`, and breakpoints](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdb.html).
- [Oracle JDK 21 — JPDA Connection and Invocation Details: `-agentlib:jdwp`, `server`, `suspend`, `address`, `dt_socket`, and connectors](https://docs.oracle.com/en/java/javase/21/docs/specs/jpda/conninv.html).
- [Oracle JDK 21 — JDI `VirtualMachine`: `dispose()` vs `exit(int)`, `resume()`/`suspend()`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jdi/com/sun/jdi/VirtualMachine.html).
- [Oracle JDK 21 — JDI `ThreadReference`: suspend/resume state and limitations](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jdi/com/sun/jdi/ThreadReference.html).
- [Oracle Java Debug Interface API (JDI), module `jdk.jdi`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jdi/module-summary.html).

**Closing principle:** *Launch* = debugger creates the JVM; *attach* = an existing JVM prepared for JDWP; *listen* = debugger waits for the JVM to connect outbound. `run`, `cont`, `clear`, `resume`, and `quit` have **different target effects**. A debug session is only safely closed once you have verified **the debugger connection, thread states, target process, and JDWP port** against your original goal.
