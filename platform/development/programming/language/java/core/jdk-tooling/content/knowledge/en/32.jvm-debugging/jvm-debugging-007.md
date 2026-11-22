# Using the Java Debugger (`jdb`) to Debug the JVM

`jdb` is the command-line debugger included with the JDK. It lets you pause a program at breakpoints, step line by line or bytecode instruction by instruction, inspect call stacks, read local variables, evaluate expressions, monitor threads, and catch exceptions. `jdb` is well suited for terminal environments, headless servers, and remote debugging sessions.

`jdb` uses the Java Debug Interface (JDI) to control the target JVM over the Java Debug Wire Protocol (JDWP). When you launch a program directly with `jdb`, the debugger starts the JVM with the appropriate debug mechanism enabled. When you attach to a running process, the target JVM must allow the debugger to connect via a compatible connector.

This lesson uses Zulu/OpenJDK 24.0.2 to verify syntax and practice, and uses Java 17+ code so the examples compile on modern JDKs.

## 1. When to Use `jdb`?

Some suitable scenarios:

- A program fails on a server where only SSH or a terminal is available.
- You need to pinpoint the exact line of code producing an incorrect value.
- You want to inspect variables and call stacks without modifying code to add logging.
- You need to pause execution at a specific method or source line.
- You need to inspect threads that are running, waiting, or holding locks.
- You need to catch an exception at the exact moment it is thrown.
- You want to attach to a running JVM with JDWP enabled.
- You need to debug an application inside a container or staging environment without an IDE.

`jdb` does not replace logs, metrics, tracing, or JFR. A debugger often suspends threads or the entire JVM at a breakpoint, so you should not casually set interactive breakpoints on production traffic. For production incidents, prefer low-overhead telemetry and recordings; only enable a remote debugger under a controlled operational procedure.

## 2. JDI, JDWP, and JPDA

Related components:

- **JPDA (Java Platform Debugger Architecture):** the overall architecture for Java debugging.
- **JDI (Java Debug Interface):** the debugger-side API for setting breakpoints, reading frames, controlling threads, and retrieving object information.
- **JDWP (Java Debug Wire Protocol):** the communication protocol between the debugger and the target JVM.
- **JVM TI:** the native interface the VM uses to support runtime tools, including the debug agent.

Basic flow:

~~~text
jdb (debugger)
     |
     | JDI
     v
JDWP transport / connector
     |
     | JDWP protocol
     v
JVM debug agent
     |
     v
Java application
~~~

When debugging locally with `jdb <class>`, JDB launches the application and establishes the connection. When debugging remotely, the application must be started with the JDWP agent or configured to accept debugger attachments.

## 3. Preparing Source Code and Debug Symbols

To view source lines and local variable names, compile with debug information:

~~~text
javac -g -d out src/JdbDemo.java
~~~

`-g` instructs the compiler to generate full debug information, including source file, line number, and local variable tables. You can specify individual kinds:

~~~text
javac -g:source,lines,vars -d out src/JdbDemo.java
~~~

Without line number information, source-line breakpoints and source listings may not behave as expected. Without local variable information, the `locals` command may not display local variable names or values.

In Maven or Gradle projects, check the compiler configuration and the artifact actually deployed. Do not assume the `.class` files on the server match the source code open on your development machine. If code is obfuscated, instrumented, shaded, or optimized in a build pipeline, breakpoints and line mappings may drift.

## 4. `jdb` Syntax and Help

Display command-line help:

~~~text
jdb -help
jdb -listconnectors
~~~

Launch the debugger for a class:

~~~text
jdb -classpath out -sourcepath src JdbDemo
~~~

Key options:

| Option | Meaning |
|---|---|
| `-classpath` | Classpath of the target JVM when JDB launches the program |
| `-sourcepath` | Directory to search for source files to display code |
| `-attach address` | Attach to a JVM listening for JDWP over the standard socket connector |
| `-connect name:arguments` | Select a JDI connector and pass arguments |
| `-listen address` | Wait for the target JVM to connect to the debugger |
| `-listenany` | Wait for a connection on any available address |
| `-launch` | Launch the JVM immediately without waiting for the `run` command |
| `-trackallthreads` | Track both virtual threads and platform threads |
| `-R<option>` | Pass a JVM option to the debuggee launched by JDB |

Example passing a system property and heap size to the target JVM:

~~~text
jdb -Dapp.mode=debug -R-Xmx512m -classpath out JdbDemo
~~~

Available options and connectors depend on the JDK. Run `jdb -listconnectors` on the exact JDK running your application to see connector names, transports, and required arguments.

## 5. Launching a Program Under the Debugger

Example:

~~~text
jdb -classpath out -sourcepath src JdbDemo
~~~

JDB displays its prompt:

~~~text
Initializing jdb ...
>
~~~

Set a breakpoint before running the program:

~~~text
stop in JdbDemo.calculate
run
~~~

`stop in` sets a breakpoint at a method. If the class has not been loaded yet, JDB reports a deferred breakpoint and installs it once the class is loaded.

You can use `-launch` to start the JVM as soon as JDB opens:

~~~text
jdb -launch -classpath out -sourcepath src JdbDemo
~~~

If you do not use `-launch`, enter `run` to start the main class. When the program pauses at a breakpoint, the prompt typically looks like `main[1]`.

## 6. Setting, Listing, and Clearing Breakpoints

Two common breakpoint forms:

**By method:**

~~~text
stop in com.example.OrderService.reserve
~~~

**By source line:**

~~~text
stop at com.example.OrderService:84
~~~

You can disambiguate overloaded methods by specifying the parameter type list:

~~~text
stop in com.example.OrderService.reserve(java.lang.String,int)
~~~

List current breakpoints:

~~~text
stop
~~~

Clear a breakpoint by method or line:

~~~text
clear com.example.OrderService.reserve
clear com.example.OrderService:84
~~~

Line breakpoints require line number information in the class file, and that line must have corresponding bytecode. If set on a blank line, comment, or brace-only line, JDB may reject it or move it to the nearest executable location.

JDB supports deferred breakpoints when a class is not yet loaded. If a breakpoint never triggers, verify the fully qualified class name, classloader, source line, and actual execution path.

## 7. Stepping: `step`, `next`, `step up`, `stepi`

While the program is paused:

| Command | Behavior |
|---|---|
| `step` | Execute one source line and step into any called method |
| `next` | Execute one source line, stepping over method calls |
| `step up` | Run until the current method returns to its caller |
| `stepi` | Execute one bytecode instruction |
| `cont` | Resume execution until the next breakpoint or stop event |

Example:

~~~text
step
next
step up
stepi
cont
~~~

Use `step` when you need to inspect the inside of a method. Use `next` when you already know the called method behaves correctly and want to stay in the current method. `stepi` is useful for bytecode analysis or when source mapping is unclear, though it is rarely needed for routine business-logic debugging.

The compiler can inline or transform code; lambdas, bridge methods, and synthetic methods also complicate stack traces. Cross-check bytecode, source, and line numbers rather than assuming every source line maps to a single instruction.

## 8. Inspecting the Call Stack and Selecting Stack Frames

Primary commands:

~~~text
where
where all
where 2
up
up 2
down
down 2
~~~

- `where`: display the call stack of the current thread.
- `where all`: display the stacks of all threads.
- `where <thread-id>`: display the stack of a specific thread.
- `up` and `down`: move between frames in the current stack.

When you select another frame, `locals`, `print`, and `dump` are evaluated in that frame's scope. If a variable is not found, verify that you are in the right frame and that the variable has been initialized at the current execution point.

JDB also provides `pop` to discard the current frame and any frames above it from the stack, and `reenter` to re-execute the frame. These alter execution flow; use them only when you understand their impact and in a debug session that can be restarted.

## 9. Reading and Modifying Variables

Expression commands:

~~~text
locals
print quantity
dump customer
eval order.getTotal()
set quantity = 5
~~~

- `locals`: list parameters and local variables in the current frame.
- `print`: evaluate an expression and print its value.
- `dump`: display object details.
- `eval`: evaluate an expression, equivalent to `print`.
- `set`: assign a new value to an assignable variable, field, or array element.

Examples of inspecting fields:

~~~text
print order.status
print order.items.length
dump order
~~~

JDB's expression evaluator supports common Java syntax, but not the full compiler or IDE environment. Expressions that invoke methods can execute code inside the debuggee, mutate state, perform I/O, or block threads. Prefer reading simple fields and variables; avoid calling methods with side effects in an application processing real data.

Not every variable is inspectable at every point. A variable may not yet be initialized, may be out of scope, may have been optimized away, or may lack a local variable table. `locals` and `print` only apply to the currently selected frame and thread.

## 10. Viewing Source and Class Information

Useful commands:

~~~text
list
list 84
list com.example.OrderService.reserve
use src
sourcepath
classpath
classes
class com.example.OrderService
methods com.example.OrderService
fields com.example.OrderService
~~~

- `list`: display source around the current location.
- `list <line>` or `list <method>`: display source at a specific location.
- `use` or `sourcepath`: view or change the source path.
- `classpath`: print the target VM's classpath.
- `classes`: list known classes.
- `class`, `methods`, `fields`: inspect class, method, and field details.

If JDB cannot find source files, pass `-sourcepath` at startup or run `use` at the prompt. Make sure the source matches the exact running build; mismatched source versions can make line numbers misleading.

## 11. Debugging Multiple Threads

JDB provides these commands:

~~~text
threads
threadgroups
thread 2
where 2
suspend 2
resume 2
interrupt 2
threadlocks 2
lock order
~~~

- `threads`: list threads in the current thread group.
- `thread <id>`: select the default thread for debugging.
- `suspend` and `resume`: pause or resume threads; omitting the ID applies to all threads by default.
- `interrupt`: send an interrupt to a thread.
- `threadlocks`: display lock information for a thread.
- `lock <expr>`: inspect lock information for an object.

When a breakpoint triggers, JDB may suspend all threads by default to keep state consistent for inspection. This can slow down other requests or cause timeouts. JDB supports `stop thread ...` syntax to pause only a specified thread in certain cases; check `help` for your JDK version before using it.

JDK 24 includes the `-trackallthreads` option to track both virtual threads and platform threads. If your application uses virtual threads, enable this option when you need to list and inspect all threads. Detailed visibility and control still depend on the JDK, connector, and thread state.

## 12. Catching Exceptions and Watching Fields

### 12.1. Exception Catchpoints

Pause on an uncaught exception:

~~~text
catch uncaught java.lang.NullPointerException
run
~~~

Pause whenever an exception is thrown, even if it may later be caught:

~~~text
catch all java.lang.IllegalArgumentException
~~~

Remove a catchpoint:

~~~text
ignore uncaught java.lang.NullPointerException
~~~

You can use `catch caught` or `catch all` depending on the scope you want to monitor. Catchpoints on common exceptions can cause the debugger to pause very frequently; choose a specific exception type and remove the catchpoint when finished.

### 12.2. Field Watchpoints

Monitor field access or modification:

~~~text
watch access com.example.Account.balance
watch all com.example.Account.balance
unwatch all com.example.Account.balance
~~~

`watch access` monitors reads; `watch all` monitors both access and modification as supported by JDB. Watchpoints can trigger frequent pauses in hot code paths, so enable them only for the specific field under investigation.

## 13. Conditional Breakpoints and Command Automation

JDB's standard `stop` syntax sets breakpoints by class/method or class/line; the JDK 24 command set does not provide an inline condition clause like some IDEs.

How to work around this when you need a condition:

1. Set a breakpoint at a method or line near the check you care about.
2. When paused, use `print` to inspect the value.
3. If the condition is not met, use `cont` to resume.
4. When possible, add an intentional guard in a debug build or write a test that reproduces the condition.

You can automatically run commands each time the program pauses:

~~~text
monitor where
monitor locals
monitor print orderId
~~~

List active monitor commands:

~~~text
monitor
~~~

Remove a monitor by its number:

~~~text
unmonitor 1
~~~

You can save a sequence of commands to a file and replay it:

~~~text
read debug-commands.txt
~~~

Command files are useful for repeatable reproduction workflows, but make sure the command order matches the JVM state. Running `print` before a thread is paused or before a variable enters scope will produce an error.

## 14. Attaching to a Running Local JVM

There are two common ways to attach.

### 14.1. Attaching by PID

Check available connectors:

~~~text
jdb -listconnectors
~~~

If the JDK provides the `com.sun.jdi.ProcessAttach` connector, attach by PID:

~~~text
jdb -connect com.sun.jdi.ProcessAttach:pid=18240
~~~

This connector attaches to a local process and requires OS attach permissions—the same user or equivalent platform privileges. It does not make an arbitrary JVM remotely debuggable; the target must support attach and the attach mechanism must not be disabled.

### 14.2. Attaching Over a Socket

If the target has a JDWP socket listener enabled at `localhost:5005`:

~~~text
jdb -attach localhost:5005
~~~

Or use the explicit connector:

~~~text
jdb -connect com.sun.jdi.SocketAttach:hostname=localhost,port=5005
~~~

`-attach` takes a socket address; do not pass a PID here. To attach by PID, use the `ProcessAttach` connector.

## 15. Enabling JDWP on the Target JVM

Start the application with the JDWP agent:

~~~text
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar application.jar
~~~

Meaning of each parameter:

- `transport=dt_socket`: use the TCP socket transport.
- `server=y`: the target JVM opens a listening socket for the debugger to connect to.
- `suspend=n`: the application starts running without waiting for a debugger.
- `address=127.0.0.1:5005`: bind the endpoint to loopback on the target host.

If you want the debugger to connect before `main` runs:

~~~text
-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005
~~~

With `suspend=y`, the JVM pauses at startup until a debugger connects. If no debugger connects, the service will not start handling requests.

To debug an application running on another machine, create an SSH tunnel to the loopback endpoint:

~~~sh
ssh -L 5005:127.0.0.1:5005 ops@jvm-host.example.internal
~~~

Keep the tunnel open, then on the administration machine run:

~~~text
jdb -attach localhost:5005
~~~

This keeps the JDWP listener bound to loopback on the target host and forwards the connection over SSH. If you must bind to an administrative network interface instead of loopback, restrict firewall/security group rules to specific admin IPs and use a trusted network.

## 16. Security for Remote Debugging

JDWP is a debugger control protocol, not an administrative service with built-in authentication and authorization like an application API. Anyone who can connect can read state, pause threads, modify variables, and evaluate expressions inside the JVM. Exposing a JDWP port to a public network is effectively equivalent to granting control over the process.

Operational rules:

- Never expose a JDWP port to the Internet.
- Prefer binding to `127.0.0.1` and using an SSH tunnel.
- If you must bind to a network interface, allow only specific admin IPs via firewall rules.
- Do not leave JDWP permanently enabled in production without explicit approval.
- Use `suspend=n` unless you intentionally want the JVM to wait for a debugger at startup.
- Open debugging only during an incident window and close the listener/tunnel immediately afterward.
- Record the PID, host, port, timestamp, operator, and purpose.
- Never leave an abandoned debugger session attached while a service is serving traffic.

A JVM-wide breakpoint can stall all incoming requests. Treat a debugger session as an operational action that can directly affect availability.

## 17. Java 17+ Example: Setting a Breakpoint, Inspecting Variables, and Continuing

Create `JdbDemo.java`:

~~~java
public final class JdbDemo {
    private JdbDemo() {
    }

    public static void main(String[] args) {
        int quantity = 3;
        int unitPrice = 120;
        int amount = calculate(quantity, unitPrice);
        System.out.println("AMOUNT=" + amount);
    }

    static int calculate(int quantity, int unitPrice) {
        int subtotal = quantity * unitPrice;
        int discount = 60;
        int result = subtotal - discount;
        return result;
    }
}
~~~

Compile with debug symbols:

~~~text
javac --release 17 -g -d out JdbDemo.java
~~~

Start JDB:

~~~text
jdb -classpath out JdbDemo
~~~

At the prompt:

~~~text
stop in JdbDemo.calculate
run
~~~

JDB registers a deferred breakpoint and pauses when `calculate` is called. Run:

~~~text
where
locals
print quantity
print unitPrice
next
locals
print subtotal
cont
~~~

Key observations:

- `where` shows that `JdbDemo.calculate` was called from `JdbDemo.main`.
- `locals` at the start of the method shows `quantity = 3` and `unitPrice = 120`.
- `next` executes the subtotal calculation line and pauses on the next line.
- `locals` now includes `subtotal = 360`.
- `print subtotal` returns `360`.
- `cont` lets the program run to completion.

Application stdout:

~~~text
AMOUNT=300
~~~

Exit the debugger with:

~~~text
exit
~~~

Line numbers and prompt formatting depend on the JDK's output format, but the variable values and stdout of the program above are deterministic.

## 18. Common Troubleshooting

### `No source found`

**Cause:** JDB cannot locate the source files, or the source path does not match the package structure.

**Resolution:** Pass `-sourcepath`, use `use <path>`, and verify the source matches the exact running build.

### Breakpoint is deferred but never hits

**Cause:** The class has not been loaded, the method is never called, the class name is wrong, or the breakpoint was placed on a line with no bytecode.

**Resolution:** Check `classes`, `methods`, the call path, and the full package name, and use a method breakpoint to narrow it down.

### `locals` does not display variables

**Cause:** Class files lack local variable debug information, the variable is not yet in scope, or the wrong frame is selected.

**Resolution:** Compile with `javac -g`, and select the right thread/frame using `thread`, `where`, `up`, and `down`.

### `Name unknown` when running `print`

**Cause:** The variable does not exist in the current frame, is uninitialized, is out of scope, or a field name requires a qualifier.

**Resolution:** Check `where` and `locals`, select the appropriate frame, and qualify field names with the object or class name.

### Cannot attach via socket

**Cause:** The target does not have JDWP enabled, host/port or transport is wrong, a firewall is blocking traffic, or the JVM has exited.

**Resolution:** Verify the `-agentlib:jdwp` startup option, confirm the listener is running, and check the bind address, port, and network path from the debugger host.

### PID attach fails

**Cause:** The target does not support attach, runs under a different user, has the attach mechanism disabled, or runs in a different PID namespace.

**Resolution:** Run the debugger with appropriate privileges on the same host/container, check for `-XX:+DisableAttachMechanism`, and use a connector listed by `jdb -listconnectors`.

### JVM hangs after enabling JDWP

**Cause:** `suspend=y` makes the JVM wait for a debugger before continuing.

**Resolution:** Connect the debugger to the configured endpoint, or restart with `suspend=n` if you do not need to pause before `main`.

### Breakpoint causes production request timeouts

**Cause:** The debugger suspends threads or the entire VM at a breakpoint.

**Resolution:** Clear the breakpoint, `cont`/`resume` threads, and end the debug session. Use staging or recordings such as JFR for extended investigations.

### Virtual threads are not visible

**Cause:** The JDB session does not have full thread tracking enabled, or the target JDK/connector has limitations.

**Resolution:** Launch with `jdb -trackallthreads`, check `threads`, and verify support on the target JDK.

### Source line stepping behaves unexpectedly

**Cause:** Compiler optimizations, instrumented/obfuscated code, lambdas/synthetic methods, or source/bytecode mismatch.

**Resolution:** Verify the artifact and source version, recompile with debug symbols, and use `stepi` when bytecode-level inspection is needed.

## 19. Controlled JVM Debugging Workflow

1. Identify the symptom, service, host/container, and exact running build.
2. Prefer reproducing the issue locally or in staging.
3. Compile with debug symbols if you control the build.
4. Choose the appropriate launch mode or attach connector.
5. Set narrow breakpoints at the suspected method or line.
6. Use `where`, `locals`, `print`, and `next` to locate the incorrect value.
7. Inspect related threads if the bug involves concurrency.
8. Catch specific exceptions if the failure only occurs on a rare branch.
9. Record findings, stack frames, values, and reproduction steps.
10. Clear breakpoints, resume threads, and close the debugger.
11. Shut down the JDWP listener or SSH tunnel after the investigation.
12. Turn the findings into a regression test or appropriate logging/metrics.

Do not leave breakpoints, JDWP ports, or listeners open after finishing. If you modified state using `set` or `eval`, document the exact change, as the debug session may behave differently from a normal run.

## 20. Pre-Use Checklist for `jdb`

- [ ] Confirmed the exact JDK and target JVM.
- [ ] Verified that the source code matches the running artifact.
- [ ] Compiled with `-g` if local variables need to be inspected.
- [ ] Configured classpath and sourcepath properly.
- [ ] Selected the right mode: launch, `ProcessAttach`, or `SocketAttach`.
- [ ] Placed breakpoints on executable methods or lines.
- [ ] Familiar with `where`, `locals`, `print`, `next`, and `cont`.
- [ ] Selected the right thread and stack frame.
- [ ] Scoped catchpoints and watchpoints narrowly to the target.
- [ ] Assessed the impact of suspending threads or the JVM.
- [ ] Bound JDWP only to loopback or a restricted management network.
- [ ] Kept JDWP ports closed to the Internet.
- [ ] Closed the tunnel, listener, and debugger upon completion.
- [ ] Converted findings into a repeatable test or operational evidence.

## 21. References

- Oracle JDK 24 — `jdb` Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdb.html
- Oracle JDK 24 — JPDA Connection and Invocation: https://docs.oracle.com/en/java/javase/24/docs/specs/jpda/conninv.html
- Oracle JDK 24 — Java Debug Wire Protocol: https://docs.oracle.com/en/java/javase/24/docs/specs/jpda/jdwp-spec.html
- Java SE 24 — Java Debug Interface: https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jdi/module-summary.html
- Oracle JDK 24 — `javac` Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html

`jdb` lets you pause and inspect a running JVM right at the point of execution. Start with debug symbols, narrow breakpoints, `where`, and `locals`; use stepping to trace data flow, then resume execution with `cont`. When attaching remotely, protect JDWP with loopback binding and an SSH tunnel, and close the endpoint immediately after the investigation.