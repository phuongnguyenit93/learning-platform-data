# Breakpoints in JVM Debugging

## 1. What is a Breakpoint?

A **breakpoint** is a request sent to a debugger to pause program execution when a specific location or event occurs. When the JVM suspends at a breakpoint, the developer can inspect the stack trace, current thread, variable values, object state, and step through execution to find the root cause of a bug.

Breakpoints help answer questions such as:

- On which line does a variable first take on an incorrect value?
- Which conditional branch was executed?
- What arguments did a method receive at the time it was called?
- Where is a field being modified?
- Where was an exception thrown and through which call chain did it propagate?
- Which thread is running the faulty code?

A breakpoint is a targeted investigative tool. Placing a breakpoint near the point where data first becomes invalid helps narrow the search space; placing too many breakpoints can make the debugging session hard to follow and prolong the investigation.

## 2. How Breakpoints Work in the JPDA Architecture

The Java Platform Debugger Architecture (JPDA) provides communication layers that allow a debugger to control a running JVM:

| Component | Role |
|---|---|
| JVM TI (Java Virtual Machine Tool Interface) | Native interface exposed by the VM to set breakpoints, retrieve stack frames, and receive events |
| JDWP (Java Debug Wire Protocol) | Protocol for transmitting requests and events between the target JVM and the debugger |
| JDI (Java Debug Interface) | High-level Java API used by IDEs and debuggers to set breakpoints, read variables, and control execution |
| jdb | The JDK command-line debugger, built on top of JDI |

When a user sets a breakpoint in an IDE:

1. The IDE creates a breakpoint request via JDI.
2. JDI sends the request over JDWP to the debug agent inside the JVM.
3. The debug agent forwards the request to the VM via JVM TI.
4. When execution reaches that location, the VM emits a breakpoint event.
5. The event is sent back to the debugger so the IDE can display the stack, source line, and variables.

Therefore, breakpoints in an IDE and breakpoints in jdb rely on the same JVM debugging mechanism. The main differences lie in the user interface and convenience features provided by the tool.

Documentation: [Oracle Java SE 24 — Java Platform Debugger Architecture](https://docs.oracle.com/en/java/javase/24/docs/specs/jpda/jpda.html) and [JPDA Structure Overview](https://docs.oracle.com/en/java/javase/24/docs/specs/jpda/architecture.html).

## 3. Preparing Bytecode with Debug Information

For a debugger to map bytecode back to source lines and display local variables, class files must contain the appropriate debug metadata.

Use `javac` with the `-g` option:

```bash
javac -g -d out src/BreakpointDemo.java
```

`-g` instructs the compiler to generate full debug information, including:

- Source file information.
- `LineNumberTable` to map bytecode to source lines.
- `LocalVariableTable` so the debugger can display local variable names and values.

You can also select individual groups:

```bash
javac -g:lines,vars,source -d out src/BreakpointDemo.java
```

If compiled with `-g:none`, the debugger may lack line numbers or variable names. In that case, line breakpoints, the `locals` command, or source viewing may not behave as expected.

Use `javap -c -l` to inspect bytecode and metadata:

```bash
javap -c -l -classpath out BreakpointDemo
```

In the output, look for `LineNumberTable` and `LocalVariableTable`. If the corresponding tables are missing, check your build configuration and ensure the debugger is loading the newly compiled class files.

Documentation: [Oracle Java SE 24 — The javac Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html).

## 4. Common Types of Breakpoints

### 4.1. Line breakpoint

Stops at a source line that has corresponding bytecode. This is the most common type when you know the exact location to inspect.

Example in jdb:

```text
stop at com.example.OrderService:42
```

The debugger stops at the first instruction associated with line 42. If that line does not produce executable bytecode, the breakpoint may fail to be set or may move to the nearest valid bytecode location.

### 4.2. Method breakpoint

Stops when a method begins executing. Useful when you need to inspect every call to an API or a business-logic method.

```text
stop in com.example.OrderService.calculateTotal
```

If the method is overloaded, specify the parameter types:

```text
stop in com.example.OrderService.calculateTotal(int,java.lang.String)
```

You can set a breakpoint on a constructor or static initializer when you need to trace object creation or class initialization.

### 4.3. Exception breakpoint

Stops when an exception is thrown. This is especially useful when an exception is caught deep in the stack and the final stack trace does not reveal the original throw site.

In jdb:

```text
catch all java.lang.IllegalArgumentException
```

JDB also supports `caught`, `uncaught`, or `all`. For example, `catch uncaught java.lang.IllegalArgumentException` only stops on exceptions not handled in the current call stack.

Remove an exception breakpoint configuration:

```text
ignore all java.lang.IllegalArgumentException
```

### 4.4. Field watchpoint

A watchpoint monitors accesses or modifications to a field. It is useful when a state variable is modified in multiple places and you do not yet know which method produces the incorrect value.

JDB supports:

```text
watch access com.example.Cache.threshold
watch all com.example.Cache.threshold
unwatch all com.example.Cache.threshold
```

`watch access` stops when the field is read; `watch all` monitors both access and modification as supported by the VM. Watchpoints can generate many events if a field is read or written frequently, so choose the target field and scope carefully.

### 4.5. Conditional breakpoints and hit counts

IDEs typically allow setting a Java expression condition, a hit count, or a log message when a breakpoint is triggered. For example, stop only when `orderId == 5001` or when `attempt >= 3`.

The basic `stop` syntax in jdb focuses on line/method locations and threads; it does not provide the same conditional and hit-count interface as popular IDEs. If complex conditions are needed, use conditional breakpoints in an IDE or write a debugger client based on JDI.

## 5. Launching an Application Under jdb

The simplest approach is to replace the `java` command with `jdb`.

Compile the application:

```bash
javac -g -d out src/BreakpointDemo.java
```

Launch the debugger:

```bash
jdb -classpath out BreakpointDemo
```

JDB opens a prompt and waits for commands. Set a breakpoint before running:

```text
stop at BreakpointDemo:6
run
```

JDB may report that the breakpoint is deferred until the class is loaded. This is normal behavior when the class has not yet been loaded. When execution reaches that location, the debugger will suspend.

Useful options:

- `jdb -sourcepath src -classpath out BreakpointDemo`: specify where to find source and class files.
- `jdb -launch -classpath out BreakpointDemo`: start the debuggee immediately when the debugger opens.
- `jdb -listconnectors`: list available connectors.
- `help` at the prompt: view jdb command syntax for the current version.

Documentation: [Oracle Java SE 24 — The jdb Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdb.html).

## 6. Hands-on Example: Stopping at a Breakpoint and Inspecting Variables

The example below calculates a total after applying a fixed discount. A breakpoint on the discount calculation line lets you inspect the data before the calculation completes.

Create `BreakpointDemo.java`:

```java
public class BreakpointDemo {
    private static int discountThreshold = 100;

    static int calculateTotal(int price, int quantity) {
        int subtotal = price * quantity;
        int discount = subtotal >= discountThreshold ? 10 : 0;
        int total = subtotal - discount;
        return total;
    }

    public static void main(String[] args) {
        int unitPrice = 25;
        int quantity = 5;
        int total = calculateTotal(unitPrice, quantity);
        System.out.println("Total: " + total);
    }
}
```

Compile and start jdb:

```bash
javac -g BreakpointDemo.java
jdb BreakpointDemo
```

At the jdb prompt, enter each command:

```text
stop at BreakpointDemo:6
run
locals
print subtotal
print BreakpointDemo.discountThreshold
next
print discount
cont
```

Explanation:

1. `stop at BreakpointDemo:6` sets a line breakpoint before the discount calculation.
2. `run` starts the program.
3. `locals` displays arguments and local variables in the current frame.
4. `print subtotal` reads the value of `subtotal`.
5. `print BreakpointDemo.discountThreshold` reads the static field.
6. `next` executes the current line and stops at the next line in the same method.
7. `print discount` inspects the newly computed `discount` value.
8. `cont` resumes execution until the program finishes or hits another breakpoint.

Expected values at the breakpoint:

```text
price = 25
quantity = 5
subtotal = 125
BreakpointDemo.discountThreshold = 100
discount = 10
```

Final program stdout:

```text
Total: 115
```

This example was compiled with `javac -g` and run under jdb on OpenJDK Zulu 24.0.2. JDB actually stopped at line 6, displayed the expected arguments and `subtotal`, and then continued to produce `Total: 115`.

## 7. jdb Commands for Managing Breakpoints and Controlling Execution

| Command | Effect |
|---|---|
| `stop at Class:line` | Set a line breakpoint |
| `stop in Class.method` | Set a method breakpoint |
| `stop` | List current breakpoints |
| `clear Class:line` | Remove a line breakpoint |
| `clear Class.method` | Remove a method breakpoint |
| `catch all ExceptionClass` | Stop when an exception is thrown |
| `ignore all ExceptionClass` | Remove an exception breakpoint |
| `watch access Class.field` | Monitor field reads |
| `watch all Class.field` | Monitor field accesses and modifications |
| `unwatch all Class.field` | Remove a field watchpoint |
| `cont` | Resume execution |
| `exit` or `quit` | Exit the debugger |

Example of setting and removing breakpoints:

```text
stop in BreakpointDemo.calculateTotal
stop
clear BreakpointDemo:6
clear BreakpointDemo.calculateTotal
```

When a method has overloaded versions, specify the parameter types to avoid setting the breakpoint on the wrong method.

## 8. Stepping Through Code and Inspecting Stack Frames

Once the debugger is suspended, you can control execution step by step:

| Command | Effect |
|---|---|
| `step` | Execute the current line and step into any called method |
| `next` | Execute the current line, stepping over method calls |
| `step up` | Run until the current method returns to its caller |
| `cont` | Continue until a breakpoint or program termination |
| `where` | Display the stack trace of the current thread |
| `where all` | Display stack traces for all threads |
| `up` / `down` | Move between stack frames |
| `locals` | Display local variables in the current frame |
| `print expression` | Evaluate and print an expression's value |
| `dump expression` | Print object details |
| `threads` | List threads |
| `thread <id>` | Select a thread as the current thread |
| `list` | Display source around the current location |

Example:

```text
where
up
locals
print this
down
next
cont
```

When inspecting variables, pay attention to which frame is currently selected. The same variable name can exist across multiple methods or recursive calls. `up` and `down` change the current frame, so the output of `locals` and `print` changes accordingly.

## 9. Setting Breakpoints on a Running Application

You can attach a debugger to an already running JVM if the JVM was started with the debug agent enabled.

Example of launching an application with a JDWP socket on loopback:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -cp out BreakpointDemo
```

Attach from another terminal:

```bash
jdb -attach 127.0.0.1:5005
```

Key parameters:

- `transport=dt_socket`: use TCP socket transport.
- `server=y`: the target JVM listens for incoming debugger connections.
- `address=127.0.0.1:5005`: listen only on loopback at port 5005.
- `suspend=n`: allow the application to run before a debugger attaches.

If the debugger must connect before `main()` starts, use `suspend=y`. This is also the default value for the JDWP agent if omitted. With `suspend=n`, breakpoints near program startup may be missed if the application executes past them before the debugger attaches.

On Windows, you can use the shared memory transport `dt_shmem` when both the JVM and debugger run on the same machine. Check available connectors with `jdb -listconnectors`.

To attach via the `ProcessAttach` connector to a local JVM with the debug agent enabled:

```bash
jdb -connect com.sun.jdi.ProcessAttach:pid=<PID>
```

`PID` is the process ID of the target JVM. This connector requires the JVM to support attach and be launched with `server=y`.

## 10. Secure Remote Debugging via SSH Tunnel

JDWP can transmit commands that control the JVM. According to the Oracle specification, JDWP allows reading and modifying even private fields, as well as invoking private methods; therefore, anyone with access to the debug port can exercise deep control over the process.

Do not expose the JDWP port to the Internet or untrusted networks. Configure the JVM to listen only on loopback:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar app.jar
```

From the machine running the debugger, create an SSH tunnel:

```bash
ssh -L 5005:127.0.0.1:5005 user@server
```

Then connect JDB through the tunnel:

```bash
jdb -attach 127.0.0.1:5005
```

This keeps the debug port bound to the server's loopback interface and uses SSH to forward the connection. If direct network access is unavoidable, restrict source IPs using a firewall and JDWP's `allow` option, and keep the port open only for the required duration and scope.

Documentation: [Oracle Java SE 24 — Connection and Invocation Details](https://docs.oracle.com/en/java/javase/24/docs/specs/jpda/conninv.html) and [JDWP Protocol](https://docs.oracle.com/en/java/javase/24/docs/specs/jdwp/jdwp-protocol.html).

## 11. Breakpoints in IDEs

IDEs such as IntelliJ IDEA, Eclipse, and Visual Studio Code provide a visual interface built on top of the Java debugger/JDI.

Typically, you can:

- Click the left gutter of a source line to toggle a line breakpoint.
- Set method breakpoints or exception breakpoints.
- Create field watchpoints if supported by the debugger and VM.
- Set a condition expression to suspend only when the condition evaluates to true.
- Set a hit count to suspend after a specified number of hits.
- Use logpoints to log information without suspending threads.
- Choose to suspend all threads or only the event thread.
- Inspect Variables, Watches, Call Stack, Threads, and Evaluate Expression.

Conditional breakpoints are very useful when a bug only occurs for specific data. For example, set `orderId == 5001` instead of stopping on thousands of requests.

When using an expression that calls a method, note that the debugger will execute that method inside the debuggee. Methods with side effects or lock waits can alter the application's state during investigation.

## 12. Breakpoints in Multithreaded Applications

Breakpoints can alter the timing of a multithreaded program. When one thread is suspended, other threads may continue running or be suspended together depending on the suspend policy.

In JDB, by default when a breakpoint is hit, the debugger suspends all threads. You can suspend only the event-generating thread using the `thread` option in the `stop` command, as shown in jdb's help syntax:

```text
stop thread <thread-id> at BreakpointDemo:6
```

Key considerations:

- Suspending all threads can cause other requests to wait and make timing-related symptoms disappear.
- Suspending a thread that holds a monitor can cause other threads to block waiting for the lock.
- A breakpoint inside a critical section can change the order of lock acquisition and release.
- Race conditions may fail to reproduce when the debugger slows down execution.
- When investigating concurrency issues, combine breakpoints with logs containing correlation IDs, thread dumps, and Java Flight Recorder.

Breakpoints let you inspect state at a single point in time, but they do not replace collecting a sequence of events over time.

## 13. Breakpoints and Virtual Threads

Virtual threads can be created in large numbers with short lifetimes. If a debugger continuously tracks every virtual thread, the volume of events and metadata can overwhelm the debugger.

In JDK 24, JDB does not track every virtual thread immediately upon creation by default. It tracks a virtual thread when a relevant event occurs, such as a breakpoint event.

You can instruct JDB to track all threads, including virtual threads:

```bash
jdb -trackallthreads -classpath out BreakpointDemo
```

This option also enables including virtual threads when JDB launches the application. When attaching to an already running JVM, some virtual threads created before the attach time may not be listed by the debug agent.

Enable tracking of all virtual threads only when you need to analyze specific threads and have accounted for thread count. For systems using virtual threads at large scale, choose narrow breakpoints and combine them with JFR to observe events over time.

Documentation: [Oracle Java SE 24 — Working With Virtual Threads in jdb](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdb.html).

## 14. Common Issues When Breakpoints Do Not Work

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Breakpoint is not hit | Code does not pass through that line or the line has no bytecode | Verify actual execution flow and choose a line with an executable statement |
| JDB reports deferred breakpoint | Class is not loaded yet | Normal behavior; continue execution so the class is loaded |
| Breakpoint stops on a different line | Source and bytecode are from different builds or line mapping differs | Clean/rebuild from the matching source and verify the classpath |
| Cannot inspect local variables | Missing `LocalVariableTable` | Recompile with `javac -g` or `-g:vars` |
| Source not found | Incorrect source path | Use `-sourcepath` or the `use` command in jdb |
| Method breakpoint is not hit | Wrong class name, method name, or overload | Check the package and specify parameter types |
| Exception breakpoint stops too often | Monitoring caught exceptions as well | Select `uncaught` or a more specific exception type |
| Field watchpoint not supported | VM does not provide access/modification watchpoint capability | Check debugger messages and VM capabilities |
| JDB cannot attach | Wrong host/port, JDWP agent not enabled, or blocked by firewall | Check JVM command line, connector, and port |
| Debugger does not see all virtual threads | Default virtual thread tracking has limitations | Use `-trackallthreads` when appropriate |
| Program hangs when hitting a breakpoint | Other threads are waiting on a lock held by the suspended thread | Inspect thread stacks and consider changing the suspend policy |

## 15. Effective Workflow for Using Breakpoints

When investigating a specific bug, you can follow this sequence:

1. Reproduce the bug and record the input, request ID, timestamp, and environment.
2. Identify the relevant method or code branch.
3. Verify that the source and class files come from the same build and contain debug metadata.
4. Place a breakpoint near the point where data first becomes invalid.
5. When suspended, inspect the stack frame, arguments, and local variables.
6. Use `step` or `next` to trace calculations and conditional branches.
7. If you do not know what is modifying a field, set a watchpoint.
8. If the bug starts with an exception, set an exception breakpoint to catch the throw site.
9. Remove temporary breakpoints once the root cause is identified.
10. Fix the code, run regression tests, and re-verify with the failing input.

Place breakpoints near the first error condition rather than scattering them across the entire application. At each pause, record key values and the hypothesis being tested to avoid changing multiple variables at once.

## 16. Summary

A breakpoint is a debugger mechanism used to suspend the JVM at a chosen location or event, enabling you to observe data and step through program execution.

Key points to remember:

- Compile with `javac -g` to include line number and local variable metadata.
- Use `stop at` for line breakpoints and `stop in` for method breakpoints in jdb.
- Use `catch` to stop when an exception is thrown and `watch` to monitor fields.
- Use `locals`, `print`, `dump`, `where`, `step`, `next`, and `cont` to inspect state.
- JDB can launch a new JVM or attach to a JVM with JDWP enabled.
- JPDA combines JVM TI, JDWP, and JDI to translate debugger requests into VM events.
- For virtual threads, understand the default tracking limitations and use `-trackallthreads` when genuinely needed.
- Breakpoints can alter timing and suspend threads; use them deliberately, especially in multithreaded systems.
- JDWP grants deep control over the JVM; keep the debug port on loopback or behind an SSH tunnel.

**Official references:**

- [Oracle Java SE 24 — The jdb Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdb.html)
- [Oracle Java SE 24 — Java Platform Debugger Architecture](https://docs.oracle.com/en/java/javase/24/docs/specs/jpda/jpda.html)
- [Oracle Java SE 24 — JPDA Structure Overview](https://docs.oracle.com/en/java/javase/24/docs/specs/jpda/architecture.html)
- [Oracle Java SE 24 — Connection and Invocation Details](https://docs.oracle.com/en/java/javase/24/docs/specs/jpda/conninv.html)
- [Oracle Java SE 24 — JDWP Protocol](https://docs.oracle.com/en/java/javase/24/docs/specs/jdwp/jdwp-protocol.html)
- [Oracle Java SE 24 — The javac Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html)
