# Debugging with Breakpoints, Stepping, and Variable Inspection in Java

## 1. What is debugging?

**Debugging** is the process of finding out why a program behaves incorrectly and verifying the fix. A program can **compile cleanly** and still calculate the wrong number, take the wrong `if` branch, skip an element, or throw an exception at runtime. A **debugger** lets you inspect the actual state of a program at specific moments instead of guessing the cause from the final output alone.

Three foundational skills:

- **Setting breakpoints:** telling the debugger to pause a thread when execution reaches a chosen location or condition.
- **Stepping:** controlling which statement executes next, either stepping over or stepping into method calls.
- **Inspecting variables:** checking local variables, parameters, object fields, watch expressions, and the call stack while the program is paused.

A debugger helps you **observe bugs**; it does not by itself prove an algorithm is correct. After fixing a bug, you still need to recompile, run tests, and check edge cases.

## 2. What is a breakpoint, and where should you place one?

A **breakpoint** is a stopping point configured in the debugger. When execution reaches that point, the debugger normally **pauses** before executing the corresponding line and lets you view the program state at that location. How the debugger displays the position and pause timing can vary when a line has multiple expressions, code is optimized, or proper debug info is missing.

How to set one in common IDEs such as IntelliJ IDEA, Eclipse, or Visual Studio Code (with Java debugging extensions):

1. Open the `.java` file containing the code you want to inspect.
2. Click in the gutter next to an **executable statement line** to toggle a breakpoint; the icon is usually a colored dot.
3. Launch with **Debug**, not just **Run**, so the debugger manages the breakpoints.
4. When paused, inspect the current line, variables in scope, and the **Call Stack**.
5. Use controls such as Continue/Resume, Step Over, Step Into, or Step Out to proceed.

**Place breakpoints where state can change or conditions decide behavior**, for example:

- Right before `if (value > 0)`: which value is about to enter the branch?
- On `sum += value;`: what is `sum` before and after the addition?
- On `count++;`: is it counting the right kind of element?
- Right before `return`: do the aggregated variables hold the expected results?

A breakpoint can only be observed if execution actually reaches that location. If you place it inside a branch that never runs for the current input, the program will not stop there. Breakpoints generally need to be placed on **lines with executable code**; you cannot expect a breakpoint on a comment line or blank line to work reliably.

## 3. Step Over, Step Into, Step Out, and Resume

| Control | Meaning while paused | When to use |
| --- | --- | --- |
| **Step Over** | Executes the current step and pauses at the next appropriate step in the current context, **without entering called methods** | You want to see how a statement changes variables without inspecting the internals of the call |
| **Step Into** | Steps into the code of the called method when accessible to the debugger | You suspect the bug is inside a custom method like `analyze(...)` |
| **Step Out** | Continues execution until exiting the current method, returning to the caller context when possible | You understand the method's internals and want to see the result back at the call site |
| **Resume/Continue** | Continues running until the next breakpoint, an error/event pause, or program termination | You do not need to observe every statement |
| **Stop/Terminate** | Ends the debug session or program as supported by the tool | You want to abort the current session; unlike Resume |

Example:

```java
int result = computeTotal(values);
System.out.println(result);
```

This is an **illustrative snippet**, assuming `computeTotal` is a method you defined. If paused at the call line:

- **Step Into** can take you inside `computeTotal` to observe its calculations.
- **Step Over** runs the call and moves to the next step in the current method, with `result` assigned if the call completed normally.
- Once inside `computeTotal`, **Step Out** lets you return to the caller after the method finishes.

Do not confuse **Step Over** with "skipping execution": the statement still runs. Likewise, debuggers may offer variants of **Step Into** such as Smart Step Into; exact names and shortcuts depend on the IDE. When an exception or another breakpoint occurs during a step, the next pause location may differ from the normal path.

## 4. Inspecting Locals, Watches, and the Call Stack

When the debugger pauses, several key panels give you visibility:

| Panel / feature | What you can inspect | Examples to check |
| --- | --- | --- |
| **Variables/Locals** | Parameters and local variables currently in scope for the selected stack frame | `i`, `value`, `count`, `sum`, `max` |
| **Watch/Expressions** | Values of expressions you want to track at the pause point | `value > 0`, `sum + value`, `count == 0` |
| **Call Stack** | Chain of method calls leading to the pause point | `main → printReport → analyze` |
| **Breakpoints** | List of breakpoints, conditions, and enabled/disabled state | Is the breakpoint enabled? |
| **Debug Console/Evaluate** | Evaluates expressions in the paused context, if supported by the debugger | `nums.length`, `sum`, `i + 1` |

**Variable values depend on the exact pause moment.** If the debugger pauses **before** `sum += value;`, `sum` usually does not include the current `value` yet. After you Step Over that line, `sum` reflects the addition. Therefore, when comparing against a trace table, note clearly whether you are checking **before or after the statement**.

**Variable scope** also matters. A variable `value` declared inside a loop body will not necessarily be visible once you leave the loop. A watch expression for an out-of-scope variable may report an error or no value, which does not mean the variable itself was set to `null`.

In a debugger, evaluating a method call or directly modifying a variable **can alter execution state**. While learning, prefer read-only expressions such as `i < nums.length` or `sum + value`. Avoid expressions with side effects like `list.remove(0)` or `i++` in the Evaluate window unless you intentionally want to mutate the program.

## 5. Baseline input for comparison during debugging

The practice program uses `int[] nums = {4, -2, 7, 0, 3}`: count, sum, and find the largest value **only among positive elements**. `-2` and `0` must be skipped; if there are no positive numbers, do not compute an average or print a placeholder `max` value.

Hand-calculated results to verify while paused in the debugger: `count = 3`, `sum = 14`, `max = 7`, and `average = 4.67` (formatted to two decimal places). The trace table in the pseudocode lesson explains how these values are derived; here the focus shifts to **observing state right before and after each statement** to pinpoint which step diverges.

### Standalone Java 17+ program

Create the file **`DebugStepDemo.java`**:

```java
import java.util.Locale;
import java.util.Objects;

public class DebugStepDemo {
    record Stats(int count, long sum, int max) {}

    static Stats analyze(int[] nums) {
        Objects.requireNonNull(nums, "nums");

        int count = 0;
        long sum = 0;
        int max = 0;

        for (int i = 0; i < nums.length; i++) {
            int value = nums[i]; // BREAKPOINT A: observe i and value

            if (value > 0) {
                if (count == 0 || value > max) {
                    max = value;
                }
                sum += value;     // BREAKPOINT B: inspect sum before/after
                count++;         // BREAKPOINT C: inspect count before/after
            }
        }

        return new Stats(count, sum, max); // BREAKPOINT D
    }

    static void printReport(String title, int[] values) {
        Stats result = analyze(values);    // BREAKPOINT E
        System.out.println(title);
        System.out.println("count=" + result.count());
        System.out.println("sum=" + result.sum());

        if (result.count() == 0) {
            System.out.println("no positive numbers");
        } else {
            System.out.println("max=" + result.max());
            double average = result.sum() / (double) result.count();
            System.out.printf(Locale.US, "average=%.2f%n", average);
        }
    }

    public static void main(String[] args) {
        printReport("Case A", new int[] {4, -2, 7, 0, 3});
        printReport("Case B", new int[] {0, -1});
    }
}
```

Use **JDK 17 or later**. From a terminal in the file's directory:

```bash
javac -g -encoding UTF-8 DebugStepDemo.java
java DebugStepDemo
```

The **`-g`** option instructs `javac` to generate debug information such as source line numbers and local variables, helping the debugger inspect state accurately; it does not change the algorithm's output.

**Exact stdout when running normally:**

```text
Case A
count=3
sum=14
max=7
average=4.67
Case B
count=0
sum=0
no positive numbers
```

`record Stats` is a concise way to bundle results available in Java 17; its accessors are `count()`, `sum()`, and `max()`. The variable `max = 0` is only a placeholder when no positive numbers have been seen yet and must not be treated as a meaningful result if `count == 0`.

## 6. Walking through a debugging session step by step

Open `DebugStepDemo.java` in an IDE with Java debugger support, ensure the project uses **JDK 17+**, and start **Debug**.

### Step 1 — Pause at the method call site

Set breakpoint E at:

```java
Stats result = analyze(values);
```

The first pause happens during the call `printReport("Case A", ...)`. In the Variables panel, you can see `title = "Case A"` and `values = [4, -2, 7, 0, 3]`. The `result` variable does not have an assigned value yet because execution paused before the call.

Click **Step Into** to enter `analyze(values)`. Once inside, selecting the `analyze` stack frame shows parameter `nums` and, after executing the initialization statements, variables `count`, `sum`, and `max`. Initially they are `0`, `0`, and `0`.

### Step 2 — Pause at the top of each iteration

Set breakpoint A at `int value = nums[i];`. On the first iteration, `i = 0`; if the debugger pauses **before** this line, `value` has not been assigned for this iteration yet. Step Over once to execute the assignment and verify `value = 4`.

Add read-only watches:

```text
i
nums.length
value
value > 0
count
sum
max
```

Once `value` is in scope, the watch `value > 0` should evaluate to `true` for `4` and `7`, and `false` for `-2` and `0`.

### Step 3 — Track state updates

When `value = 4`, execution enters the `if` branch. Before `sum += value;`, `sum = 0`; after Step Over, `sum = 4`. Before `count++;`, `count = 0`; after Step Over, `count = 1`. Because `count == 0` when handling the first positive number, `max` is set to `4`.

If you click **Resume** and hit breakpoint A on the next iteration, `i = 1` and `nums[1] = -2`. Since `value > 0` is false, the aggregate variables stay unchanged: `count = 1`, `sum = 4`, `max = 4`.

### Step 4 — Verify state **before and after breakpoints**

Instead of only checking an end-of-iteration summary table, observe the **exact pause timing of the debugger**. For `nums = {4, -2, 7, 0, 3}`, the table below selects meaningful checkpoints in `DebugStepDemo`:

| Pause location | What is happening / has happened | Values to observe |
| --- | --- | --- |
| A, `i=0`, before `int value = nums[i]` | First element not yet assigned to local `value` in this pass | `i=0`, `count=0`, `sum=0`; **do not evaluate** watch `value` before assignment |
| B, `i=0`, before `sum += value` | `value=4`, `max` is already 4; addition has not run | `count=0`, `sum=0`, `max=4` |
| C, `i=0`, before `count++` | Addition just executed; counter not incremented yet | `sum=4`, `count=0`; Step Over → `count=1` |
| A, `i=1`, after assigning `value=-2` | `value > 0` is false, skips B and C | After this pass: `count=1`, `sum=4`, `max=4` |
| B, `i=2`, `value=7` | Updated `max=7`, but 7 not added yet | Before B: `sum=4`, `count=1`; after B: `sum=11` |
| A, `i=3`, `value=0` | Does not enter positive branch | After this pass: `sum=11`, `count=2`, `max=7` |
| B/C, `i=4`, `value=3` | `max` stays 7; adds first, then increments count | Before B: `sum=11`, `count=2`; after C: `sum=14`, `count=3` |
| D, before `return new Stats(...)` | All iterations completed | `count=3`, `sum=14`, `max=7` |

**Note on timing:** If breakpoint A pauses *before* the assignment, the local `value` may not yet hold the current iteration's value. Only check `value > 0` after stepping over the assignment or when paused on the `if` statement. Breakpoints B and C are not hit on `i=1` and `i=3` because the condition is false; that is the expected behavior, not a broken breakpoint.

At point D, use **Step Out** to return to `printReport`, check `result` after `analyze` returns, and confirm the average `14 / 3.0` prints as `4.67`. This table adds a **before/after-statement** perspective to the dry-run table; it does not replace testing all boundary inputs.

### Step 5 — Observe the case with no positive numbers

Resume until the call `printReport("Case B", new int[] {0, -1})`. Here, `value > 0` is always false, and `count` and `sum` stay `0`; the program enters `if (result.count() == 0)` and prints `no positive numbers`, performing no division.

Testing this edge case confirms the program does not work only on one "nice" array.

## 7. Using conditional breakpoints to avoid pausing too often

In a loop with thousands of elements, a regular breakpoint can pause the program thousands of times. A **conditional breakpoint** only pauses when a specified condition evaluates to true.

Examples in the program above:

- Condition `i == 2`: pause right before processing the third element.
- Condition `value == 7`: pause at a location where `value` is already assigned and in scope.
- Condition `count > 1`: focus on the state after encountering multiple positive numbers; place the breakpoint on the right line so you know whether `count` is pre- or post-update.

**Watch out for placement:** if you place a breakpoint right on `int value = nums[i];`, the current iteration's `value` may **not yet hold a valid value for the condition**. Use `i == 2` on that line, or place the breakpoint on `if (value > 0)` to test `value == 7` after the assignment executes.

Some IDEs support **logpoints/tracepoints**: logging a message without pausing the program. This helps when observing many iterations, though pausing with a breakpoint remains more direct when inspecting detailed state at one moment.

In multithreaded programs, a breakpoint may pause **one thread or all threads** depending on debugger configuration. Never assume other threads are also paused; check the suspend policy and the Threads view when analyzing concurrency bugs.

## 8. Logic bug example: finding the wrong line with the debugger

An incorrect version of the loop:

```java
for (int i = 0; i < nums.length - 1; i++) {
    int value = nums[i];
    if (value > 0) {
        sum += value;
        count++;
    }
}
```

This is a **buggy illustrative snippet**, not a full Java file. On `{4, -2, 7, 0, 3}`, the condition `i < nums.length - 1` only runs `i = 0, 1, 2, 3`; the last element at `i = 4` is skipped. Looking only at `sum += value`, a beginner might wrongly suspect the addition itself.

Using the debugger:

1. Place a breakpoint inside the loop and watch `i`, `nums.length`, `value`, `sum`, `count`.
2. Resume iteration by iteration or set a conditional breakpoint near the last iteration.
3. Notice that `i` **never reaches `4`**, even though `nums.length = 5`.
4. Check the loop condition and change it to `i < nums.length`.
5. Rerun and confirm the sum is `14` and the positive count is `3`.

For an update in the wrong branch, such as placing `count++` **outside** `if (value > 0)`, a breakpoint after the increment shows `count` changing even when `value = -2` or `0`. Checking against the trace table pinpoints the first step where state diverges.

**Takeaway:** place breakpoints based on a **hypothesis about the cause**, inspect state **before and after** a statement, and fix the faulty statement rather than masking symptoms with a hardcoded result.

## 9. How the Call Stack shows where the program is

At breakpoints A/B/C inside `analyze`, the Call Stack of a normal run shows the call sequence:

```text
DebugStepDemo.analyze(...)
DebugStepDemo.printReport(...)
DebugStepDemo.main(...)
```

The top frame is the current method. Selecting another frame displays local variables in **that method's context**, not values of same-named variables in every method. While stepping in `analyze`, `nums` is `analyze`'s parameter; in `printReport`, the parameter is named `values`. Those are two distinct local variables referencing the same array object in this example.

When an exception occurs, inspect the stack trace or enable an **exception breakpoint** to pause when a specific exception type is thrown (or uncaught, depending on IDE settings). Exception breakpoints are useful when an error is caught at a higher layer and the final message hides where it originated.

Distinguish the **call stack** from array/collection contents: the call stack shows the chain of active calls; Variables shows the data available in each frame.

## 10. Running from the terminal and attaching a debugger (optional)

Running normally with `java DebugStepDemo` will **not automatically pause** at IDE breakpoints. To debug in an IDE, use the IDE's **Debug** action or configure the debugger to **Attach** to a JVM launched with JDWP enabled.

Example with **JDK 17+**, after compiling with `javac -g`:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 DebugStepDemo
```

Meaning of options:

- `transport=dt_socket`: uses a socket connection for debugger communication.
- `server=y`: the JVM opens a listening socket to accept a debugger connection.
- `suspend=y`: the JVM pauses at startup and waits for a debugger to attach before running the application.
- `address=127.0.0.1:5005`: listens only on the machine's **loopback** interface at port 5005.

In your IDE, create an **Attach to Remote JVM / Remote Debug** configuration targeting `127.0.0.1:5005`, pointing to the matching source code and compiled classes; once attached and resumed, the debugger can stop at breakpoints. This mode **does not match the normal stdout of the example**, because the JVM may print a listening message while waiting to attach.

**Security:** the JDWP port grants deep control over the Java process; never expose it publicly on the Internet or untrusted networks, and especially avoid `address=*:5005` without proper safeguards. For beginners, debugging directly from the IDE is simpler and avoids manual port management.

## 11. Things a debugger cannot replace

- **No breakpoint is hit:** check that you ran in Debug mode, placed the breakpoint on an executable line, execution actually reaches that line, the breakpoint is enabled, and running classes match the edited source.
- **Cannot see local variables:** verify the selected Call Stack frame, variable scope, and try compiling with `javac -g`. Certain libraries or optimized code may limit debug info.
- **Step Into enters library code instead of your code:** use Step Over, Smart Step Into, or step filters if supported by your IDE.
- **Breakpoint in a loop pauses too frequently:** use a conditional breakpoint or logpoint.
- **Behavior changes under the debugger:** a debugger alters execution timing, especially in multithreaded code; do not assume a race condition disappeared just because stepping made it pass.
- **Watch shows a scope error:** evaluate the expression on a line and stack frame where the variable actually exists.
- **Debugger shows correct results on one input:** you still must test empty arrays, boundary indices, invalid inputs, large values, and special cases.
- **Debug Console Evaluate changes state:** avoid expressions with side effects or data mutations when your goal is strictly observation.

### Quick debugging checklist

1. Describe the **expected result** and the **actual result**.
2. Create a small input that **reproduces the bug**.
3. Set a breakpoint **before the suspected location** and run Debug.
4. Inspect Locals/Watch/Call Stack, distinguishing values **before and after statements**.
5. Use Step Into to inspect internals, Step Over when you only need the result, Step Out to return to the caller, and Resume to move to the next key point.
6. Compare against a trace table or hand calculation to identify the **first step that diverges**.
7. Fix the **root cause**, then rerun normal and boundary tests.
8. Disable or remove unnecessary breakpoints once finished.

**Remember:** breakpoints pause at the right moment; stepping shows which statement changes state; Variables/Watch/Call Stack answer "which value is wrong, where, and via which call path?" Combining debugger observation with hand calculation and testing finds Java bugs far more accurately than adding random `println()` calls.
