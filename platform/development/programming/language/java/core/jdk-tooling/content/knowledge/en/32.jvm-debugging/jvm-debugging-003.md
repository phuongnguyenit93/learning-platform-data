# Local Debugging of Java Applications

## Objectives

After this lesson, you will be able to set up a local debugging session for a Java application; understand the roles of source code, bytecode, debug information, and the JVM; set breakpoints; step through code using Step Into, Step Over, and Step Out; inspect local variables, fields, the call stack, and threads; break on exceptions; use an IDE debugger or jdb; attach to a local JVM with JDWP enabled; reproduce and fix logic bugs; and troubleshoot common debugging issues.

## 1. What Is Local Debugging?

**Local debugging** is the process of running a Java application on a development machine under the control of a debugger. The debugger lets you pause the program at a specific location, inspect JVM state, examine variable values, and trace how execution flows through branches.

Instead of only looking at the final output or adding numerous `System.out.println` statements, you can pause right before or after a suspicious line to inspect data and execution flow.

Local debugging is commonly used to:

- Find logic bugs such as incorrect conditions, wrong calculations, or boundary-handling errors.
- Diagnose the root cause of `NullPointerException`, `IndexOutOfBoundsException`, and other exceptions.
- Inspect input values, local variables, fields, and object state.
- Trace the call stack to see which method called the current code.
- Observe loops, `if`/`switch` branches, and execution paths.
- Inspect the state of multiple threads when race conditions or deadlocks occur.
- Verify that a fix actually changes behavior as intended.

Local debugging is well suited when the issue can be reproduced using source code, configuration, and data on a development machine. If a bug only appears in production due to load, data, timing, or environment differences, combine debugging with logs, metrics, JFR, and appropriate diagnostic data.

## 2. How Does a Debugger Work?

A Java debugging session has three main components:

- **Debuggee:** The JVM running the application under inspection.
- **Debugger:** An IDE or a tool such as `jdb` that controls the debug session and displays program state.
- **Debug interface/protocol:** The mechanism that allows the debugger to instruct the JVM to set breakpoints, suspend threads, read variables, and resume execution.

In the Java Platform Debugger Architecture (JPDA):

- **JDI (Java Debug Interface)** is the high-level API used by debuggers to control and inspect a JVM.
- **JDWP (Java Debug Wire Protocol)** is the protocol for exchanging commands and responses between the debugger and the target JVM.
- **JVM TI (JVM Tool Interface)** provides a native interface for agents/debuggers to interact with the VM.

When you click Debug in an IDE, the IDE typically launches the application with a debug configuration or connects to a JVM with the debug agent enabled. The debugger sends requests to set breakpoints. When the JVM reaches that location, a breakpoint event is sent back to the debugger and the relevant thread is suspended according to the suspend policy.

You can inspect variables and the call stack while the thread is suspended. When you click Resume/Continue, the debugger tells the JVM to continue running.

## 3. Preparing Source Code and Debug Information

The debugger needs information that maps bytecode back to source code.

When compiling Java with `javac`, the compiler generates line number and source file information by default. To include local variable information as well, use `-g`.

~~~bash
javac -g --release 17 LocalDebugDemo.java
~~~

| Option | Generated Information |
|---|---|
| `-g` | All debug information, including source, line numbers, and local variables |
| `-g:lines` | Line number information |
| `-g:source` | Source file name |
| `-g:vars` | Local variable information |
| `-g:none` | No debug information |

Without local-variable information, the debugger may still pause at a breakpoint, but it cannot display local variable names or values. In that case, recompile with `-g`.

### Source and Bytecode Must Match

The debugger relies on the line number table in the `.class` file. If the source file you have open differs from the source that produced the running bytecode, breakpoints may land on the wrong line or the IDE may report a source mismatch.

Before debugging:

1. Rebuild the exact module and profile you want to inspect.
2. Verify that the IDE runs with the right output directory/classpath.
3. Ensure the open source file is the version that generated the `.class` file.
4. Delete stale build artifacts if you suspect old classes are still being used.
5. Use the same JDK/toolchain as the application configuration you are reproducing.

Breakpoints are usually only valid on lines that have executable bytecode. Lines with comments, braces, or declarations that emit no instructions may not accept breakpoints.

## 4. Local Debugging Workflow in an IDE

Popular Java IDEs such as IntelliJ IDEA, Eclipse, and Visual Studio Code with Java extensions all provide debug modes. Button names and layouts vary, but the core workflow is similar.

### Step 1: Open the Right Project and Run Configuration

Check that:

- The project has been imported/built successfully.
- The JDK and language level are correct.
- The main class or test to run is correct.
- The classpath/module path contains all dependencies.
- The working directory is accurate.
- Program arguments, environment variables, and VM options match what is needed.
- The local profile/configuration has the data required to reproduce the issue.

A program can work in the terminal yet fail in an IDE because of differences in the working directory, environment variables, or VM options.

### Step 2: Set Breakpoints

Click the left gutter next to a line of code to create a breakpoint. When running in Debug mode, the program pauses at that line before executing the corresponding instruction.

Good places to set breakpoints include:

- The line immediately before a suspicious calculation or condition.
- The entry point of a method you want to inspect.
- Lines handling user input or incoming requests.
- Exception-handling branches.
- State transition points between business logic steps.

Do not set too many breakpoints upfront. Start at the boundary between input and the logic under investigation, then narrow down the location once you understand the execution flow.

### Step 3: Launch in Debug Mode

Select the run configuration and click Debug. The IDE launches the JVM under the debugger or attaches to a JVM with JDWP enabled.

When a breakpoint is hit, the application pauses. The debugger typically displays the current source line, call stack, local variables and fields, suspended threads, the breakpoints list, watches, and an expression evaluator.

### Step 4: Inspect State

Check the inputs first, then examine each intermediate variable:

- Are the input values correct?
- Could the data type cause a loss of precision?
- Does the collection contain the expected elements?
- Is an object `null`?
- Does the `if` condition evaluate to the expected result?
- Was the variable overwritten by another method?
- Does the call stack pass through the expected methods?

Do not look only at the final value. Inspect variables at the moment they are assigned or right before a decision branch.

### Step 5: Step Through Code

| Action | Meaning |
|---|---|
| Resume/Continue | Continue until the next breakpoint or program termination |
| Step Over | Execute the current line and pause at the next line in the current frame |
| Step Into | Enter the method called on the current line |
| Step Out | Run until the current method returns to its caller |
| Run to Cursor | Run until the selected line if supported by the IDE |
| Evaluate Expression | Compute an expression's value in the current context |
| Drop Frame | Some IDEs let you rewind to the caller frame; re-running may cause side effects |

Step Over is appropriate when you trust the called method and only want to observe the next line. Step Into is useful when you need to inspect inside a method. Step Out helps you quickly exit the current method once you have seen enough.

### Step 6: Fix and Verify

1. Record the failing input and the incorrect output.
2. Identify the condition or calculation causing the bug.
3. Fix the source code.
4. Re-run the test or debug configuration with the same input.
5. Verify that the new result is correct.
6. Test boundary and adjacent cases to avoid introducing regressions.

One passing run is not enough to prove every case is handled. Add tests for the failing scenario and boundary values.

## 5. Breakpoints and Breakpoint Types

A breakpoint is a point where the debugger instructs the JVM to pause when execution reaches a specific location or event.

### Line Breakpoint

Pauses at a source line that has executable instructions. This is the most common breakpoint type. Use it when you already know the suspect area and want to inspect variables before or after a calculation.

### Method Breakpoint

Pauses when a method is called or starts executing. Useful when you do not know which caller invokes the method or when tracking a specific API.

Method breakpoints can cause frequent pauses and higher overhead than line breakpoints in heavily called methods.

### Exception Breakpoint

Pauses when an exception is thrown or when an exception goes uncaught, depending on the breakpoint type and IDE.

Use this to find where an exception originates, even when the final stack trace only shows where the exception escaped the application.

### Conditional Breakpoint

IDEs can let you attach a condition, such as pausing only when `itemCount == 10`. This is useful when a breakpoint sits inside a loop or a frequently called method.

The condition must be a valid expression in the current context. It may be evaluated many times and can invoke methods, so avoid conditions that cause side effects or are expensive to compute.

### Logpoint or Tracepoint

Some IDEs support logging a message when reaching a line without suspending the thread. Use this to trace values in a continuous run, especially when pausing the program changes timing.

### Field Watchpoint

Some debuggers support pausing when a field is read or written. Availability depends on the IDE, VM, and field type. Use this when you do not know what code is mutating an object's state.

## 6. Inspecting Variables, Objects, and the Call Stack

### Local Variables

Local variables only exist within the scope of their method/frame and corresponding execution lifetime. For the debugger to show local variable names, the class must be compiled with local-variable debug information, typically via `javac -g`.

A local variable might not be initialized yet at the current line or may have already reached the end of its lifetime. If the debugger does not display its value, check the breakpoint position and debug information.

### Fields and Objects

Objects in the debugger can usually be expanded to inspect their fields. When checking an object, look at whether any field is `null`, whether collections have the expected size, whether the object is shared across threads, and whether mutable fields change after another method runs.

Evaluating expressions or calling methods in the debugger can execute application code. If a method mutates state, sends a network request, writes a file, or acquires a lock, inspecting it can alter the very behavior you are investigating.

### Call Stack

The call stack shows the sequence of method calls that led to the current location. Read from the current frame up toward callers to find where a request/event started, which methods data passed through, which method modified state, whether there is unexpected recursion/callbacks, and where an exception originated.

In an IDE, select a different frame in the Call Stack to view that frame's local variables. When switching frames, distinguish caller variables from those of the current method.

### Watches

Watch expressions let you monitor specific expressions while the debugger is paused. For example:

~~~java
itemCount
itemCount >= 10
order.getItems().size()
~~~

Only add safe expressions. A method call in a watch executes real code and can cause side effects or alter timing.

## 7. Debugging Exceptions

When an exception occurs, find where the exception was created before just patching the last line shown in the stack trace.

Workflow:

1. Enable an exception breakpoint for the exception type under investigation.
2. Choose whether to pause when the exception is thrown or when it is uncaught, depending on your goal.
3. When the debugger pauses, inspect the exception type and message.
4. Read the call stack and select the first frame belonging to application code.
5. Inspect inputs, object references, and state in that frame.
6. Step through the lines leading up to where the exception is raised.
7. Identify the condition that triggers the exception and fix it at the source.

For example, with a `NullPointerException`:

- Identify which expression holds the `null` reference.
- Check where that reference is initialized.
- Trace the data flow and branches that might skip assignment.
- Check the contract of the method returning that object.
- Add appropriate validation or `null` handling at data boundaries.

Do not simply wrap code in `try`/`catch` to hide an exception if the root cause is a violated application invariant.

## 8. Debugging Threads and Multithreaded Applications

In a multithreaded application, the debugger can suspend a single thread or all threads depending on the IDE's suspend policy and the breakpoint event.

When paused at a breakpoint, check which thread is stopped, which threads are still running, which monitors/locks a thread holds, whether other threads are waiting on a lock, whether there is shared mutable state, and whether a variable can be modified by another thread between two observations.

Suspending a thread that holds a lock can block other threads. If you suspend all threads, the entire application may stop processing while you inspect it.

### Race Conditions

A race condition can disappear when a debugger alters timing. Breakpoints pause threads and change the relative ordering of operations.

To investigate a race condition:

1. Reproduce it with a controlled concurrency test.
2. Add logging with timestamps and thread names.
3. Use thread dumps/JFR to observe activity over time.
4. Check synchronization, lock ordering, atomic operations, and visibility.
5. Use breakpoints selectively and avoid pausing for long inside critical sections.
6. Write tests that repeat the scenario many times to verify the fix.

Never treat the disappearance of a bug under a debugger as proof that the bug is fixed.

## 9. Debugging Virtual Threads

Virtual threads can be created in large numbers. Because of this, JDB does not track all virtual threads upon creation by default; it tracks virtual threads that have triggered an event of interest to the debugger, such as a breakpoint.

JDK 26 supports the option:

~~~bash
jdb -trackallthreads LocalDebugDemo
~~~

This option instructs JDB to track virtual threads as they are created. The Debug Agent also provides the `includevirtualthreads` option to include known virtual threads in the thread list when connecting.

Tracking all virtual threads can generate a large volume of information. The Debug Agent might not know about virtual threads created before the debugger attached. Do not treat the thread list shown in the debugger as proof that every virtual thread in the process is listed.

## 10. Using jdb for Local Debugging from the Terminal

`jdb` is the Java Debugger bundled with the JDK. It is a command-line debugger demonstrating the Java Platform Debugger Architecture and can launch or attach to a local or remote JVM.

Check the tool:

~~~bash
jdb -help
jdb -listconnectors
~~~

### Launching an Application Under jdb

If the main class is `LocalDebugDemo`, run:

~~~bash
jdb LocalDebugDemo
~~~

JDB launches a new JVM, loads the class, and stops before the first instruction of the application class. You can set breakpoints and then use `run` to start.

If the classes are in a different output directory:

~~~bash
jdb -classpath out com.example.LocalDebugDemo
~~~

You can use `-sourcepath` to specify the directory containing source files:

~~~bash
jdb -sourcepath src -classpath out com.example.LocalDebugDemo
~~~

On Windows, multiple directories in a path list are separated by semicolons; on Linux/macOS, colons are typically used.

### Common jdb Commands

| Command | Effect |
|---|---|
| `help` or `?` | Display the list of commands |
| `stop at Class:line` | Set a breakpoint at a line |
| `stop in Class.method` | Set a breakpoint at the start of a method |
| `clear Class:line` | Remove a breakpoint |
| `run` | Run the application launched by jdb |
| `cont` | Continue after a breakpoint, step, or exception |
| `step` | Step into the method called on the current line |
| `next` | Step over the current line without entering called methods |
| `step up` | Return to the caller frame after stepping |
| `where` | Print the call stack of the current thread |
| `where all` | Print the stacks of threads in the current thread group |
| `threads` | List threads tracked by the debugger |
| `thread <id>` | Select the current thread |
| `locals` | Print local variables in the current frame if debug info is present |
| `print expression` | Print the value of an expression |
| `dump expression` | Print the fields of an object |
| `up` / `down` | Move between stack frames |
| `catch ExceptionClass` | Pause when an exception of the specified class is thrown |
| `ignore ExceptionClass` | Remove an exception breakpoint set with `catch` |
| `exit` | Exit the debugger |

Command names and supported details can vary across JDK releases. Run `help` inside your `jdb` session to confirm available commands.

### Line and Method Breakpoints

For example:

~~~text
stop at LocalDebugDemo:12
stop in LocalDebugDemo.shippingFee
~~~

When a method is overloaded, specify parameter types to select the right overload:

~~~text
stop in LocalDebugDemo.calculate(int,java.lang.String)
~~~

Running `stop` with no arguments lists the current breakpoints. `clear` with no arguments can also be used to view breakpoints.

### Inspecting Source and Variables

When paused at a breakpoint:

~~~text
list
locals
print itemCount
where
~~~

`list` displays the source around the current location if the debugger can find the source. `locals` and `print` inspect variables in the selected stack frame. If local variables cannot be viewed, verify that the class was compiled with `-g`.

## 11. Hands-On Example: Finding a Conditional Bug with jdb

This example contains a boundary bug: the business rule requires orders of 10 or more items to get free shipping, but the code uses `>` instead of `>=`.

Create `LocalDebugDemo.java`:

~~~java
public class LocalDebugDemo {
    private static int shippingFee(int itemCount) {
        if (itemCount > 10) {
            return 0;
        }
        return 25;
    }

    public static void main(String[] args) {
        int itemCount = 10;
        int fee = shippingFee(itemCount);

        System.out.println("items=" + itemCount);
        System.out.println("shippingFee=" + fee);
    }
}
~~~

### Step 1: Compile with Debug Information

~~~bash
javac -g --release 17 LocalDebugDemo.java
~~~

### Step 2: Run Normally to Reproduce

~~~bash
java LocalDebugDemo
~~~

Output before fixing:

~~~text
items=10
shippingFee=25
~~~

According to the business requirement, this result is wrong because 10 items should qualify for free shipping.

### Step 3: Launch with jdb

~~~bash
jdb -classpath . LocalDebugDemo
~~~

At the `jdb` prompt, set a breakpoint at the start of the method:

~~~text
stop in LocalDebugDemo.shippingFee
run
~~~

JDB will pause when `shippingFee` is called.

### Step 4: Inspect Inputs and Call Stack

~~~text
where
locals
print itemCount
list
~~~

Confirm that `itemCount` has the value `10`, the call stack shows `main` calling `shippingFee`, and `list` displays the exact source code version under inspection.

### Step 5: Step Through the Condition

Use `next` to execute line by line without stepping into other methods:

~~~text
next
list
~~~

Observe the condition `itemCount > 10`. With input `10`, this expression evaluates to `false`, so execution proceeds to `return 25`.

You can evaluate the expression directly:

~~~text
print itemCount > 10
~~~

The boolean value shown is `false`. This is the direct reason the free-shipping branch is not taken.

### Step 6: Continue to Observe Output

~~~text
cont
~~~

The application finishes and prints:

~~~text
items=10
shippingFee=25
~~~

### Step 7: Fix the Bug

Update the condition in `shippingFee` to:

~~~java
if (itemCount >= 10) {
    return 0;
}
~~~

Recompile and run:

~~~bash
javac -g --release 17 LocalDebugDemo.java
java LocalDebugDemo
~~~

Expected output after fixing:

~~~text
items=10
shippingFee=0
~~~

### Step 8: Test Adjacent Boundary Values

Besides `10`, test at least these values:

| itemCount | Expected Result |
|---:|---:|
| 0 | 25 |
| 9 | 25 |
| 10 | 0 |
| 11 | 0 |

If the business rule disallows negative `itemCount` values, verify validation at the input boundary. This example illustrates how a debugger helps pinpoint an incorrect condition; it does not replace automated tests for boundary cases.

## 12. Attaching jdb to a Running Local JVM

Launching with `jdb` is the simplest approach when you can start the application directly. If the application is already running and was configured with the debug agent from startup, you can attach the debugger to that process.

### Step 1: Start the JVM with JDWP

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 LocalDebugDemo
~~~

Meaning of the options:

- `transport=dt_socket`: Use the socket transport.
- `server=y`: The target JVM listens for incoming debugger connections.
- `suspend=n`: The JVM does not wait for the debugger to attach before running `main`.
- `address=127.0.0.1:5005`: Listen on local loopback, port `5005`.

If you need the debugger to attach before `main` runs, use `suspend=y`. The JVM will pause during debug session initialization until a debugger connects and resumes it.

### Step 2: Attach with jdb

Open another terminal on the same machine:

~~~bash
jdb -attach 127.0.0.1:5005
~~~

Set a breakpoint:

~~~text
stop in LocalDebugDemo.shippingFee
~~~

Because the JVM may have already executed past the method before attaching, trigger the flow again or send another request/test to hit the breakpoint.

### Step 3: Verify and Exit

Use `where`, `locals`, `print`, `threads`, and `cont` just as in a launched session. When finished, use `exit` to close the debugger. The target application may continue running depending on its state and how the debugger detaches.

You cannot attach a debugger to an arbitrary JVM by default unless it was started with an appropriate debug agent/connector. When you need to debug a local process, configure debugging at startup or use an IDE to launch in Debug mode.

## 13. Local Debugging with an IDE vs. jdb

| Criterion | IDE Debugger | jdb |
|---|---|---|
| Interaction | Graphical user interface | Terminal |
| Breakpoints | Line, method, conditional, exception depending on IDE | Line, method, exception, and supported commands |
| Inspecting variables | Variables/Watches windows | `locals`, `print`, `dump` |
| Call stack | Call Stack window | `where`, `up`, `down` |
| Stepping | Step Into/Over/Out buttons | `step`, `next`, `step up` |
| Best suited for | Daily development, large projects | Terminal-only environments, quick checks, learning JPDA |
| Source mapping | IDE manages project/sources | Requires appropriate classpath and sourcepath |

An IDE is usually more convenient when browsing object graphs, switching across multiple frames, and setting conditional breakpoints. `jdb` is helpful in terminal-only environments or when learning how a debugger operates through basic commands.

## 14. Local Configuration Checks When a Program Behaves Unexpectedly

During local debugging, a run configuration that differs from your terminal command can produce different behavior.

Check the actual JDK runtime, classpath/module path, working directory, program arguments, environment variables, system properties passed with `-D`, VM options, local/profile configuration files, ports and dependent services, test data, and database/cache state.

If the program runs with the `dev` profile locally but the bug occurs in the `test` profile, local debugging should use the matching profile to reproduce it. Do not change code based on results from a configuration that does not match the failing environment.

### Checking the JDK and Executed Classes

~~~bash
java -version
javac -version
jdb -help
~~~

If multiple JDKs are installed on your machine, verify that `java`, `javac`, and `jdb` belong to the intended toolchain. On Windows you can run `where java`, `where javac`, `where jdb`; on Linux/macOS you can run `which java`, `which javac`, `which jdb`.

## 15. Local Debugging and Automated Tests

A debugger helps observe the state of a single execution. Automated tests verify repeatable behavior.

A solid workflow:

1. Write a test that reproduces the bug with the smallest possible input.
2. Run the test and confirm it fails as expected.
3. Set a breakpoint in the method handling the logic.
4. Debug to inspect inputs, branches, and state.
5. Fix the code.
6. Re-run the test to confirm it passes.
7. Run additional boundary and regression tests.
8. Remove temporary breakpoints or disable the debug configuration before running the regular test suite.

For the bug in the shipping fee example, you can write a test:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class ShippingFeeTest {
    @Test
    void tenItemsAreEligibleForFreeShipping() {
        assertEquals(0, LocalDebugDemo.shippingFee(10));
    }
}
~~~

This test only illustrates the assertion and assumes the method is changed to package-private so the test can call it. If you keep the method `private`, test it through the public API or redesign the testing boundary appropriately.

Do not rely on the debugger as the sole proof that a bug is fixed. Keep the reproducing test in your regression suite.

## 16. Limitations and Side Effects of Debugging

Debugging changes how an application is controlled:

- Breakpoints pause threads and can alter timing.
- Suspending all threads can halt other threads as well.
- Method evaluation can execute code and trigger side effects.
- Conditional breakpoints may be evaluated frequently.
- The debug agent can add runtime overhead.
- The debugger may not show full local variables if classes lack debug information.
- Source differing from bytecode can cause breakpoints to align to the wrong lines.
- JIT optimizations and the compiler can make some variables or source lines harder to observe as expected.

Therefore, a debugger is great for understanding a single execution, but not always suitable for measuring performance or investigating timing-sensitive bugs. Use JFR, profilers, GC logs, and application metrics when you need to observe behavior over longer periods.

## 17. Security Considerations When Enabling JDWP

JDWP grants the debugger control over and inspection access to the target JVM. If the debug socket is exposed on an untrusted network interface, anyone who can connect can control execution and access data inside the process.

When debugging locally:

- Prefer loopback addresses such as `127.0.0.1`.
- Do not bind to the wildcard `*` without a clear need and strict access controls.
- Never expose debug ports to the Internet.
- Use firewalls and restrict source addresses if you must debug over a network.
- Disable the debug agent once finished.
- Do not enable JDWP in production as a default configuration.
- Protect terminal output and sensitive data displayed in the debugger.

The `address=127.0.0.1:5005` example above restricts the socket to loopback. Changing it to `*:5005` makes the JVM listen on all network interfaces; only do that when proper access controls are in place.

## 18. Common Issues and Troubleshooting

### Breakpoint Is Not Hit

**Symptoms:** Execution passes the line without the debugger pausing.

**Causes:** The class has not been loaded, the breakpoint is on a line with no bytecode, stale classes are running, or the breakpoint failed to bind.

**Resolution:** Verify the target process and classpath; rebuild; ensure the breakpoint is on an executable line; use a method breakpoint to confirm whether the method is being called.

### Breakpoint Hits, but Source Does Not Match

**Symptoms:** The debugger pauses on a different line or reports a source mismatch.

**Causes:** Current source differs from compiled bytecode, the output directory contains stale classes, or the IDE is running the wrong module.

**Resolution:** Clean and rebuild the correct module; check the run configuration; verify classpath and sourcepath; open the matching source revision.

### Cannot View Local Variables

**Symptoms:** The debugger reports that local variable information is unavailable or omits variable names.

**Causes:** The class was compiled without local-variable debug information.

**Resolution:** Compile with `javac -g`; if using a build tool, enable debug information in the compiler configuration; rebuild and run the newly compiled classes.

### jdb Cannot Find the Main Class

**Symptoms:** JDB reports that the class does not exist or could not be loaded.

**Causes:** Incorrect classpath, missing package name in the class argument, or running from the wrong working directory.

**Resolution:** Use `jdb -classpath out package.MainClass`; verify the package declaration and `.class` file location; ensure dependencies are on the classpath/module path.

### jdb Attach Fails

**Symptoms:** Connection refused, timeout, or inability to attach.

**Causes:** The JVM does not have JDWP enabled, wrong host/port, the process has exited, a firewall is blocking the connection, or the debug agent is in client mode instead of server mode.

**Resolution:** Check `-agentlib:jdwp`, `server=y`, address/port, and JVM status; verify debugger and JVM use the same transport; try loopback for local debugging.

### JVM Hangs Before main

**Symptoms:** The application does not progress after starting with the debug agent.

**Causes:** `suspend=y` makes the JVM wait for a debugger connection before executing `main`.

**Resolution:** Attach the debugger and Resume/Continue; if you do not need to pause before `main`, use `suspend=n`.

### Expected Thread Is Missing

**Symptoms:** The thread list in the debugger does not show the desired thread.

**Causes:** The thread has not been created yet, has already terminated, the debugger is not tracking all virtual threads, or the thread belongs to a different process.

**Resolution:** Confirm you are attached to the right JVM; use `threads`/the thread view; on supported JDKs, consider `jdb -trackallthreads`; combine with thread dumps/JFR for a broader view.

### Debugger Makes Timing Bugs Disappear

**Symptoms:** A race condition stops occurring when breakpoints are set.

**Causes:** Suspending threads changed the execution schedule and timing relationships.

**Resolution:** Use timestamped logging, stress tests, JFR, and synchronization audits; minimize breakpoints inside critical sections.

### Evaluating an Expression Mutates State

**Symptoms:** After inspecting an object, the application behaves differently.

**Causes:** The expression called a method with side effects, acquired a lock, or performed I/O.

**Resolution:** Inspect fields and simple values directly whenever possible; avoid calling mutating methods; use safe watch expressions and read a method's code before evaluating it.

### Program Behaves Differently in IDE vs. Terminal

**Symptoms:** Same source code produces different output or errors.

**Causes:** Differences in JDK, profile, environment variables, working directory, VM options, or program arguments.

**Resolution:** Compare the entire run configuration against the terminal command; verify the right configuration files and dependent services are used.

## 19. Local Debugging Checklist

### Before Debugging

- [ ] Reproduce the bug with a specific input or test.
- [ ] Select the right JDK and run configuration.
- [ ] Build the right module and source revision.
- [ ] Ensure source code matches bytecode.
- [ ] Generate debug information with `-g` if local variables are needed.
- [ ] Check working directory, arguments, environment variables, and VM options.
- [ ] Place breakpoints at meaningful locations.

### During Debugging

- [ ] Confirm the breakpoint is hit.
- [ ] Check inputs before inspecting results.
- [ ] Read the call stack to identify callers.
- [ ] Use Step Over/Into/Out appropriately.
- [ ] Observe variables before and after decision branches.
- [ ] Inspect exceptions at the point where they are thrown.
- [ ] Pay attention to threads and suspend policies.
- [ ] Avoid evaluating methods with side effects.

### After Debugging

- [ ] Document the root cause and reproducing input.
- [ ] Fix the code at the source.
- [ ] Add a test that reproduces the bug.
- [ ] Check boundary cases and regressions.
- [ ] Re-run tests and builds.
- [ ] Remove temporary breakpoints and stop the debug agent.
- [ ] Do not leave debug ports open after finishing.

## 20. Official References

- [The jdb Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdb.html) — launching/attaching to a JVM, breakpoints, stepping, exceptions, sourcepath, connectors, and virtual-thread tracking.
- [The javac Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html) — `-g`, `-g:lines`, `-g:vars`, `-g:source`, and `-g:none` options.
- [Java Platform Debugger Architecture: Connection and Invocation — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/jpda/conninv.html) — JDWP agent, socket/shared-memory transport, server/client, suspend, and connectors.
- [Java Debug Wire Protocol — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/jdwp/jdwp-protocol.html) — protocol between the debugger and target JVM.
- [Java Debug Interface — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jdi/module-summary.html) — JDI API for debuggers and administrative tools.
- [Troubleshooting Guide — Java SE 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshooting-guide.pdf) — guide to using `jdb` and JDWP for debugging applications.

Local debugging lets you observe exact inputs, branches, variables, and call stacks at the moment a failure occurs. Reproduce the bug with a small test, set targeted breakpoints, verify source/bytecode alignment and debug information, and confirm the fix with automated tests so the result stays repeatable.
