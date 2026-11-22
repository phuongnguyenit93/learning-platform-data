# Logging and Debugging in Java

## 1. Purpose and Differences

When a Java application returns incorrect results, runs unusually slowly, or throws an exception, we need to answer three questions: **what happened**, **in what context did it happen**, and **why did the code behave that way**. Logging and debugging support these questions in two complementary ways.

- **Logging:** the program proactively emits records of runtime events: timestamp, severity level, action, context, and outcome. Records can be retained for analysis after an error has occurred, even when it cannot be reproduced immediately.
- **Debugging:** the process of observing and verifying program behavior to find the root cause of a bug. A debugger is a tool that allows setting breakpoints, inspecting variables, stepping through code, and viewing the call stack and execution flow. Debugging also includes reproducing the bug, forming hypotheses, testing, and verifying the fix.

| Criterion | Logging | Debugging with a debugger |
| --- | --- | --- |
| When useful | While the application is running, especially in integration or production environments | When the issue can be reproduced in an environment that allows pausing/inspecting the program |
| Observable | Events and data that the developer decided to record | Variable states, expressions, stack frames, and threads at breakpoints |
| Impact | Incurs CPU/I/O/storage overhead; usually does not require pausing the program | Breakpoints can alter execution timing and interactions between threads |
| Primary value | Reconstructing timelines, comparing multiple requests/runs, investigating past incidents | Tracing conditional branches, intermediate data, and root causes at the statement level |
| Limitations | Cannot see data that was never logged; logs lacking context can be misleading | Difficult to catch rare bugs, timing bugs, or issues that only appear in production |

For example, if an API occasionally returns an incorrect total amount, logs can reveal which request, which input, and which output was abnormal. Then, use a breakpoint with the corresponding dataset to inspect the calculation or conditional branch that caused the bug.

## 2. Logging: Recording the Right Information at the Right Level

### 2.1. Use a Logging API Instead of Ad-Hoc Printing

`System.out.println(...)` is useful for small exercises, but it lacks log levels, filtering configuration, output destinations, and operational policies. Java provides the standard `java.util.logging` (JUL) API; Java 9+ also has `System.Logger`. In applications that use external libraries, you will often see **SLF4J** as a facade API and **Logback/Log4j 2/JUL** as the underlying logging implementation. These are ecosystem choices, not libraries all built into the JDK. The examples below use only JDK 17's JUL.

A logger is typically created by class name: `Logger.getLogger(ClassName.class.getName())`. Log meaningful events instead of printing every intermediate value. Each log record should help answer **what event occurred, where, for which object/request, and what the outcome was**.

### 2.2. Choosing Log Levels

With JUL, the common levels (from most severe to most detailed) are:

| JUL Level | When to use | Examples |
| --- | --- | --- |
| `SEVERE` | Serious error requiring attention; the operation did not complete | Unable to connect to a required dependency, request processing failed |
| `WARNING` | Abnormal situation, but the program can continue or has a fallback | Invalid input, retry attempt after failure |
| `INFO` | Notable operational milestones | Successful startup, task completed, important state change |
| `CONFIG` | Configuration information for diagnostics | Selected mode or configuration options, excluding secrets |
| `FINE` / `FINER` / `FINEST` | Technical details needed for deep analysis | Processing branches, intermediate values, retry decisions |

`Level.OFF` disables logging; `Level.ALL` enables all levels. The level on both the **logger** and the **handler** affects whether a record is emitted. For instance, if the logger is set to `FINE` but `ConsoleHandler` only accepts `INFO` and above, `FINE` records will not appear. SLF4J/Logback level names and filtering typically use `ERROR/WARN/INFO/DEBUG/TRACE`; do not mechanically equate level names across different systems.

**Rule of thumb:** choose levels based on actionability and operational needs. Do not use `SEVERE` for normal, expected situations; likewise, do not use `INFO` to print the contents of every loop iteration.

### 2.3. Place Logs at Meaningful Boundaries

Logs should be placed at key milestones: task start/completion, interactions with external systems, fallback/retry decisions, failed input validation, and where exceptions are handled. Useful context fields typically include `requestId`, `operation`, `recordId`, `durationMs`, and `outcome`. When handling multiple concurrent requests, a correlation ID helps link log records belonging to the same execution flow.

Example log messages:

~~~text
INFO operation=checkout requestId=req-42 outcome=success durationMs=35
WARNING operation=checkout requestId=req-43 outcome=rejected reason=invalid_quantity
~~~

This is an **illustrative log pattern**, not a mandatory JUL format standard. Production applications may output logs in JSON or structured fields so search systems can query them easily. Do not rely on the ordering of log lines across threads to infer causality.

## 3. Runnable Example with JDK 17+

Create a file named **LoggingDebuggingDemo.java** with the following content. The example calculates a discounted price using integers to focus on observing program behavior; this is **not a pricing model with real-world rounding requirements**. The custom-formatted handler writing to stdout is only used to keep the practice output consistent; production applications typically configure handlers/appenders outside the code.

~~~java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class LoggingDebuggingDemo {
    private static final Logger LOG =
            Logger.getLogger(LoggingDebuggingDemo.class.getName());

    static {
        LOG.setUseParentHandlers(false); // Avoid duplicate output via the root logger.
        LOG.setLevel(Level.FINE);

        Handler output = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + ": "
                        + formatMessage(record) + System.lineSeparator();
            }
        }) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush(); // Immediately display logs in the example.
            }
        };
        output.setLevel(Level.FINE);
        LOG.addHandler(output);
    }

    static int finalPrice(int originalPrice, int discountPercent) {
        LOG.fine(() -> "originalPrice=" + originalPrice
                + ", discountPercent=" + discountPercent);

        if (originalPrice < 0 || discountPercent < 0
                || discountPercent > 100) {
            LOG.warning("Invalid input");
            throw new IllegalArgumentException("Invalid input");
        }

        // Cast to long before multiplication to avoid int overflow.
        long discount = (long) originalPrice * discountPercent / 100;
        int result = originalPrice - (int) discount;
        LOG.info(() -> "finalPrice=" + result);
        return result;
    }

    public static void main(String[] args) {
        System.out.println("Result=" + finalPrice(200, 10));
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac -encoding UTF-8 -g LoggingDebuggingDemo.java
java LoggingDebuggingDemo
~~~

The **stdout** output of the example above:

~~~text
FINE: originalPrice=200, discountPercent=10
INFO: finalPrice=180
Result=180
~~~

Explanation: `200 × 10 / 100 = 20`, so the result is `180`. Because both the logger and the handler allow `FINE`, both the detailed line and the `INFO` line are displayed. `-g` instructs `javac` to generate debug information (such as line numbers and local variables) so the debugger can inspect them easily; it does not change the calculation formula.

In a normal program, JUL usually has a default handler with different configuration and formatting; **do not assume you will get these exact three lines** when omitting the example's custom configuration.

## 4. Debugging: Finding Root Causes at the Statement Level

### 4.1. Essential Operations

- **Breakpoint:** pause before a line or inside a suspect method. Conditional breakpoints are very useful when a bug only occurs for a specific `requestId` or value.
- **Step Over:** execute the current line and pause at the next line in the same frame; does not step into method calls.
- **Step Into:** enter the called method to inspect how it processes data.
- **Step Out:** finish executing the current method and return to the caller.
- **Variables / Evaluate / Watch:** inspect variables, evaluate expressions, and watch changing values; be careful when evaluating expressions with side effects.
- **Call Stack:** see the chain of methods that led to the breakpoint; select the right frame to inspect its local variables and parameters.
- **Exception Breakpoint:** pause where an exception is thrown (or uncaught, depending on IDE settings), helping locate the source rather than just looking at where the stack trace is printed.
- **Threads:** in concurrent processing, see which thread is paused/waiting on a lock. Pausing one thread can alter race conditions or timeouts.

You do not need to set a breakpoint on every line. Pick a testable hypothesis: **at which step does the value become wrong?** Start near the input or the boundary where the error is detected, then narrow down the scope.

### 4.2. Practicing with an IDE or jdb

In IntelliJ IDEA, Eclipse, or VS Code with Java Debugger, set a breakpoint on the line that calculates `discount`, run in Debug mode, inspect `originalPrice`, `discountPercent`, `discount`, and `result`, and then Step Over each assignment.

The JDK also ships with **jdb**, which can be practiced in the terminal. After compiling with `-g` as shown in section 3:

~~~bash
jdb LoggingDebuggingDemo
~~~

Inside the jdb session, enter the following commands in order:

~~~text
stop in LoggingDebuggingDemo.finalPrice
run
locals
next
locals
cont
quit
~~~

`stop in` sets a breakpoint at the start of the method; `run` starts running the program; `locals` displays currently available local variables; `next` executes the next step; `cont` continues execution. Depending on the line where execution is paused, `locals` only shows variables that have already been initialized. jdb output also includes prompts/session messages, so it does not have a fixed transcript like the program's stdout.

### 4.3. Example of an Integer Division Bug

Suppose a progress-tracking system uses:

~~~java
int processed = 3;
int total = 10;
double ratio = processed / total; // Unintended behavior: ratio evaluates to 0.0
~~~

The log `processed=3, total=10, ratio=0.0` indicates the symptom. A breakpoint on the assignment reveals that **both operands are `int`**, so Java performs integer division `3 / 10 = 0` before converting the result to `double`. Fix it as follows:

~~~java
if (total <= 0) {
    throw new IllegalArgumentException("total must be positive");
}
double ratio = (double) processed / total; // 0.3
~~~

After fixing, rerun with the exact same input and test boundary cases such as `processed=0`, `processed=total`, and `total=0`. This example illustrates how logs help identify the situation, while the debugger explains the mechanism at the line of code.

## 5. Workflow Combining Logging and Debugging

1. **Describe the bug in a verifiable way.** Record the expected result, actual result, application/JDK version, inputs, environment, and timestamp; find a minimal reproduction.
2. **Reconstruct the timeline using logs.** Filter by time, request/correlation ID, and operation. Look for events before/after the error, external calls, warnings, and stack traces. Check whether logs are missing due to level filtering or sampling.
3. **Form a specific hypothesis.** For example: "the value undergoes integer division", "the retry branch runs twice", or "the data is modified by another thread". Avoid drawing conclusions from a single log line alone.
4. **Set breakpoints where they can distinguish between hypotheses.** Observe inputs, branch conditions, intermediate results, and the call stack; use conditional breakpoints when there are many iterations.
5. **Fix the root cause and run regression tests.** Write a test with the exact data that triggered the bug, add edge cases, and verify both the output behavior and useful log events. Remove noisy investigative logs or lower their level appropriately.
6. **Verify after deployment.** Use logs/metrics to confirm the symptom is gone under real conditions; do not treat one successful debug session as proof that every scenario is correct.

When a bug only occurs under load, in production, or due to timing, prioritize contextual logs, tracing/metrics, and reproducible data. Breakpoints can make race conditions disappear or cause requests to time out; conclusions should also be backed by load/concurrency testing.

## 6. Exceptions, Performance, and Information Security

**Logging exceptions with context and stack traces:** if this is the layer responsible for handling or reporting the error, JUL can log a `Throwable` object:

~~~java
// Illustrative snippet inside a catch block, not a standalone program.
catch (java.io.IOException e) {
    LOG.log(Level.SEVERE, "operation=loadConfig outcome=failed", e);
    throw e;
}
~~~

The `log(Level, String, Throwable)` method preserves the stack trace. Avoid logging only `e.getMessage()` when you need to pinpoint the source of an error. At the same time, avoid logging the same exception at every layer and producing a flood of duplicate `SEVERE` logs: choose an appropriate boundary for reporting, while other layers can propagate the error upward.

**Logging overhead:** building strings, serializing objects, or capturing stack traces can consume CPU, memory, and I/O. For data that is expensive to compute, `LOG.fine(() -> expensiveDescription())` uses a `Supplier` so the message is only constructed when that level is enabled. Even so, do not put logic with side effects inside a log-building lambda; do not log every element of a large data stream at `INFO`. In production, configure filtering, sampling, file rotation, retention, and access permissions according to operational needs.

**Sensitive data:** do not log passwords, tokens, API keys, session cookies, full personal data, or raw payloads containing secrets. Choose safe fields, mask/encrypt appropriately, and restrict access permissions and retention periods. Logs often pass through multiple systems; data once logged can be difficult to retract.

**Structured information:** try to keep field names and representations consistent. Recording both `durationMs` and `outcome` aids investigation far better than a vague `"done"` message. Propagate correlation IDs across asynchronous tasks if you want to link logs from multiple threads; thread-bound context does not automatically follow every task.

**Environment separation:** configure log levels via deployment configuration whenever possible. Enable detailed logging during a controlled investigation window and then revert to the appropriate operational level; do not let tutorial-style stdout logging or detailed per-request logging become the default convention for a large system.

## 7. Common Mistakes and How to Recognize Them

| Mistake | Consequence | Recommended practice |
| --- | --- | --- |
| Using only `System.out.println` in operations | Hard to filter by level, categorize, and preserve context | Use a logging API with consistent configuration |
| Expecting `FINE` when the handler only allows `INFO` | Mistakenly thinking the program never reached that code | Check both logger and handler levels |
| Logging "Error occurred" without data | Cannot locate the request or root cause | Log the operation name, correlation ID, outcome, and exception when appropriate |
| Logging the same exception at multiple layers | Noise, inaccurate error counts | Choose a clear boundary responsible for logging errors |
| Logging secrets or entire objects | Data leaks, bloated logs | Whitelist safe fields, mask sensitive data |
| Setting a breakpoint on a race condition and seeing the bug vanish | Execution timing is altered | Add logging/tracing, stress test, and observe threads |
| Fixing without reproducing or writing a test | No way to know if the true root cause was fixed | Create a reproduction case and regression tests |
| Treating logs as complete evidence | Missing unlogged state | Use a debugger, tests, and metrics to confirm |

## 8. Self-Check Exercises

1. Run the program in section 3 and explain why both `FINE` and `INFO` appear. Then change **only** `output.setLevel(Level.FINE)` to `Level.INFO`: predict which line disappears, and compare with the run output.
2. Set a breakpoint at the `discount` calculation and observe the `long` type of the multiplication expression. Try `finalPrice(100, 25)`; predict `75` before running.
3. Try the input `finalPrice(100, 120)` in a separate call, observe the `WARNING` log and exception; explain why there is no `finalPrice=...` log in that branch.
4. For the integer division bug in section 4.3, write a test verifying that `3/10` must produce `0.3` (with an appropriate floating-point tolerance), then fix the operand and rerun.

**Key takeaway for practice:** logs provide a traceable history; the debugger reveals state at breakpoints; tests verify the fix. Combining all three helps you move from symptom to root cause and prevent regressions.