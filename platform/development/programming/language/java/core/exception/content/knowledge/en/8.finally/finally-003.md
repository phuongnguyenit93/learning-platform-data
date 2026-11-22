# Finally with `return`, `break`, or `continue` in Java

In Java, a `finally` block attached to a `try` construct is designed to perform final tasks when control flow **exits the `try/catch` construct**. A common point of confusion is that exiting `try` does not happen only when statements finish normally or when an exception occurs; it also happens when code executes `return`, `break`, or `continue`.

**Core rule:** If control flow is inside a `try` with a `finally`, when `try` or an associated `catch` begins to complete due to `return`, `break`, `continue`, or an exception, Java normally executes `finally` **before completing the transfer of control outward**. After `finally` finishes normally, the pending effect of `return`, `break`, `continue`, or the exception continues to be carried out.

It is also important to understand the special exception to this rule: if **`finally` itself completes abnormally** (for example, `throw` or `return` inside `finally`), it can replace the pending completion reason. Therefore, `finally` does not always "just clean up and preserve the original result."

This lesson belongs to Java Core – Exception, under the **finally Block** section, and focuses specifically on the three control-transfer statements `return`, `break`, and `continue`.

## 1. Reviewing the structure and scope of `finally`

Common syntax:

~~~java
try {
    // Main work.
} catch (SomeException e) {
    // Handle the corresponding exception type.
} finally {
    // Cleanup or final action.
}
~~~

You can use `try/finally` **without `catch`**:

~~~java
try {
    perform();
} finally {
    cleanup();
}
~~~

Both snippets are **illustrative syntax**, assuming that the `perform()` and `cleanup()` methods already exist. A `finally` block belongs to that specific `try` construct, not a global function that "always runs when the entire application exits."

Under normal Java execution conditions, `finally` is executed when leaving the `try/catch` region via the following paths:

| Path leaving the construct | Does `finally` normally run? | What happens next if `finally` completes normally |
| --- | --- | --- |
| Reaching the end of the `try` block | Yes | The program continues after `try/catch/finally` |
| An exception is caught and `catch` finishes normally | Yes | Continues after the construct |
| An exception is not caught here | Yes | Continues propagating to an outer handler |
| `return` inside `try` or `catch` | Yes | Completes returning from the method |
| `break` exits a loop/switch from inside the `try` region | Yes | Transfers to the position after the construct broken out of |
| `continue` to the next iteration from inside the `try` region | Yes | Performs the next step according to the loop type |

**The phrase "normally" matters:** there is no guarantee that `finally` will run when the JVM is forcibly terminated, the process is killed by the operating system, `Runtime.halt` terminates the VM, power is lost, or control flow never leaves the `try` region. These limitations are explained at the end.

## 2. `return` inside `try`: `finally` runs before the caller receives the value

Example:

~~~java
static int calculate() {
    try {
        System.out.println("try: prepare return");
        return 42;
    } finally {
        System.out.println("finally: cleanup");
    }
}
~~~

If you call `System.out.println("result=" + calculate());`, stdout is:

~~~text
try: prepare return
finally: cleanup
result=42
~~~

The order is:

1. Java begins evaluating the expression after `return` (`42` in the example).
2. The method prepares to complete by returning the value.
3. Before exiting, Java runs `finally`.
4. `finally` finishes normally.
5. Only then is the value `42` returned to the caller; the caller prints `result=42`.

Encountering `return` does not mean "skip all remaining statements" in the sense of skipping `finally`. Statements **after `return` in the same block** cannot continue normally, but the associated `finally` is still processed according to the language rules.

### The `return` expression is evaluated before `finally`

Consider the example:

~~~java
static int snapshot() {
    int value = 3;
    try {
        return value;
    } finally {
        value = 9;
        System.out.println("finally value=" + value);
    }
}
~~~

If you call `System.out.println("snapshot=" + snapshot());`:

~~~text
finally value=9
snapshot=3
~~~

Reason: the expression `return value;` is evaluated **before** `finally` runs. For the primitive type `int`, the value scheduled to be returned is already `3`. Reassigning the local variable `value = 9` inside `finally` does not cause the previous `return` expression to be re-evaluated, so the caller still receives `3`.

This does not mean Java prevents `finally` from modifying the state of any related object: the case of returning a reference is examined separately.

## 3. Returning an object: `finally` can mutate the object's state

A reference is also evaluated before `finally` runs. However, if the reference points to a **mutable object** and `finally` modifies that exact object, the caller can observe the change.

~~~java
static StringBuilder createText() {
    StringBuilder result = new StringBuilder("A");
    try {
        return result;
    } finally {
        result.append("B");
    }
}
~~~

After `System.out.println(createText());`, the output is:

~~~text
AB
~~~

Explanation:

- The expression `return result;` has already selected the reference to the `StringBuilder`.
- `finally` calls `append("B")` on the **same object**.
- The caller receives the selected reference, which now points to the object containing `"AB"`.

Distinguish between **reassigning a reference variable** and **mutating the object**:

~~~java
static StringBuilder replaceLocalReference() {
    StringBuilder result = new StringBuilder("A");
    try {
        return result;
    } finally {
        result = new StringBuilder("B");
    }
}
~~~

In the method above, the caller still receives the `"A"` object because the returned reference was already determined before `finally`; the assignment `result = ...` only changes the local variable.

This is why you should not rigidly interpret "`finally` does not affect the return result." It **does not re-evaluate the return value of the original expression**, but it can certainly change externally visible state, or replace the result itself via another control-transfer statement.

## 4. `break` inside `try`: `finally` runs before leaving the loop

`break` does not jump past `finally`. If a branch inside `try` executes `break` to exit an enclosing loop, Java executes the associated `finally` before transferring control to the position after the loop.

~~~java
static void breakExample() {
    for (int i = 0; i < 3; i++) {
        try {
            System.out.println("try " + i);
            if (i == 1) {
                break;
            }
        } finally {
            System.out.println("finally " + i);
        }
    }
    System.out.println("after loop");
}
~~~

Output:

~~~text
try 0
finally 0
try 1
finally 1
after loop
~~~

At `i = 0`, the `try` body finishes normally; `finally` runs, and then the loop advances to the next iteration. At `i = 1`, `break` is executed, yet `finally 1` **still prints before** exiting the loop. `i = 2` does not occur.

**Key takeaway:** `break` determines the jump target according to the loop/switch syntax; `finally` is the part that must execute while leaving the `try` regions that the jump path passes through. `finally` does not "cancel" `break` when it completes normally.

### Labeled `break`

In nested loops, `break label;` can exit multiple levels. If the exit path leaves multiple `try` blocks with `finally`, they are executed **from the inner region to the outer region**.

~~~java
static void labeledBreak() {
    OUTER:
    for (int i = 0; i < 2; i++) {
        try {
            for (int j = 0; j < 2; j++) {
                try {
                    System.out.println("body " + i + "," + j);
                    break OUTER;
                } finally {
                    System.out.println("inner finally");
                }
            }
        } finally {
            System.out.println("outer finally");
        }
    }
    System.out.println("after labeled break");
}
~~~

This is a valid Java method. When called once, stdout is:

~~~text
body 0,0
inner finally
outer finally
after labeled break
~~~

The inner `try` region is exited first, followed by the outer `try` region. Because the target of `break OUTER` lies outside both, both `finally` blocks run before the program prints the line after the loop.

## 5. `continue` inside `try`: `finally` runs before the next iteration

`continue` skips the remainder of the loop body for the current iteration to proceed to the next iteration. If `continue` originates from a `try` with a `finally`, the associated `finally` runs **before** the update/condition-check step for the next iteration.

~~~java
static void continueExample() {
    for (int i = 0; i < 3; i++) {
        try {
            System.out.println("try " + i);
            if (i < 2) {
                continue;
            }
            System.out.println("body " + i);
        } finally {
            System.out.println("finally " + i);
        }
    }
    System.out.println("after loop");
}
~~~

Output:

~~~text
try 0
finally 0
try 1
finally 1
try 2
body 2
finally 2
after loop
~~~

At `i = 0` and `i = 1`, the `continue` statement skips `System.out.println("body " + i)`, but it does not skip `finally`. At `i = 2`, the condition `i < 2` is false, so the program prints `body 2` and still runs `finally 2`.

With a `for (init; condition; update)` loop, after `finally` completes normally on a `continue` path, Java performs the **update** step and then checks the condition for the next iteration. With `while` or `do/while`, the next step is correspondingly evaluating the loop condition according to the rules of that loop type.

### Labeled `continue`

`continue OUTER;` jumps to the next iteration of the loop labeled `OUTER`, not necessarily the innermost loop. If the jump path leaves one or more `try` constructs, the associated `finally` blocks are still executed before moving to the step of the target loop.

~~~java
static void labeledContinue() {
    OUTER:
    for (int i = 0; i < 2; i++) {
        try {
            for (int j = 0; j < 2; j++) {
                try {
                    System.out.println("body " + i + "," + j);
                    continue OUTER;
                } finally {
                    System.out.println("inner finally " + i);
                }
            }
        } finally {
            System.out.println("outer finally " + i);
        }
    }
}
~~~

Output when called once:

~~~text
body 0,0
inner finally 0
outer finally 0
body 1,0
inner finally 1
outer finally 1
~~~

There is no `j = 1` iteration because `continue OUTER` skips the rest of the inner loop and jumps directly to the next iteration of `OUTER`, **after** the necessary `finally` blocks have run.

## 6. Complete Java 17+ program: `return`, `break`, and `continue` together

Create the file **`FinallyControlFlowDemo.java`**:

~~~java
public class FinallyControlFlowDemo {
    public static void main(String[] args) {
        System.out.println("== RETURN ==");
        System.out.println("return result: " + returnNormally());
        System.out.println("snapshot result: " + returnSnapshot());

        System.out.println("== BREAK ==");
        breakDemo();

        System.out.println("== CONTINUE ==");
        continueDemo();

        System.out.println("== EXCEPTION ==");
        try {
            throwingDemo();
        } catch (IllegalStateException e) {
            System.out.println("caught: " + e.getMessage());
        }

        System.out.println("== OVERRIDE ==");
        System.out.println("overridden result: " + overrideReturn());
    }

    static int returnNormally() {
        try {
            System.out.println("try return");
            return 10;
        } finally {
            System.out.println("finally after return");
        }
    }

    static int returnSnapshot() {
        int n = 3;
        try {
            return n;
        } finally {
            n = 9;
            System.out.println("finally local=" + n);
        }
    }

    static void breakDemo() {
        for (int i = 0; i < 3; i++) {
            try {
                System.out.println("break try " + i);
                if (i == 1) {
                    break;
                }
            } finally {
                System.out.println("break finally " + i);
            }
        }
        System.out.println("break exit");
    }

    static void continueDemo() {
        for (int i = 0; i < 3; i++) {
            try {
                System.out.println("continue try " + i);
                if (i < 2) {
                    continue;
                }
                System.out.println("continue body " + i);
            } finally {
                System.out.println("continue finally " + i);
            }
        }
        System.out.println("continue exit");
    }

    static void throwingDemo() {
        try {
            throw new IllegalStateException("boom");
        } finally {
            System.out.println("finally before propagation");
        }
    }

    // Only to illustrate a design flaw: do not return inside finally.
    static int overrideReturn() {
        try {
            return 1;
        } finally {
            System.out.println("finally overrides return");
            return 2;
        }
    }
}
~~~

Compile and run with JDK 17 or newer:

~~~bash
javac FinallyControlFlowDemo.java
java FinallyControlFlowDemo
~~~

**Deterministic stdout:**

~~~text
== RETURN ==
try return
finally after return
return result: 10
finally local=9
snapshot result: 3
== BREAK ==
break try 0
break finally 0
break try 1
break finally 1
break exit
== CONTINUE ==
continue try 0
continue finally 0
continue try 1
continue finally 1
continue try 2
continue body 2
continue finally 2
continue exit
== EXCEPTION ==
finally before propagation
caught: boom
== OVERRIDE ==
finally overrides return
overridden result: 2
~~~

### Mapping back to the rules

**`returnNormally()`:** The method prepares to return `10`; before the caller prints the result, it runs the `finally` block. There is no other `return` in `finally`, so the value `10` is preserved.

**`returnSnapshot()`:** The primitive value `3` is determined before `finally`; modifying the local variable to `9` and printing `9` does not change the result the caller receives.

**`breakDemo()`:** When `i = 1`, the `break` statement requests exiting the `for` loop, yet `finally` for that same iteration still runs. There is no `break try 2` because the loop has ended.

**`continueDemo()`:** The first two iterations execute `continue`, so `continue body 0` and `continue body 1` are not printed; both still print `finally` before continuing to the next iteration.

**`throwingDemo()`:** The `IllegalStateException` is thrown in `try`; `finally` prints the cleanup line before the outer `catch` receives the exception. There is no `catch` inside the `throwingDemo` method.

**`overrideReturn()`:** Both `return 1` in `try` and `return 2` in `finally` are valid syntax, but `finally`'s `return 2` **replaces** the scheduled result `1`. This is an intentional anti-pattern; you should not use this pattern in real applications.

## 7. When `finally` itself `return`s or `throw`s: it can override the pending flow

This is an important exception to the simplistic statement "`finally` always runs and then returns to the original flow."

If `finally` **finishes normally**, the previous completion reason is preserved:

~~~java
static int keepsReturn() {
    try {
        return 7;
    } finally {
        System.out.println("cleanup");
    }
}
~~~

If `finally` **itself completes abnormally** via `return` or `throw`, the result from `try` can be replaced.

### Case A: `return` in `finally` overrides `return` from `try`

~~~java
static int replacesReturn() {
    try {
        return 7;
    } finally {
        return 9;
    }
}
~~~

The method returns `9`, not `7`. The `finally` block's `return` statement is the completion reason that is kept. In real-world work, **avoid writing `return` in `finally`** because it makes control flow hard to reason about and can mask failures.

### Case B: `return` in `finally` hides an exception

~~~java
static int hidesFailure() {
    try {
        throw new IllegalStateException("original failure");
    } finally {
        return 9;
    }
}
~~~

This is **a valid Java method, but strongly discouraged**. If you call `hidesFailure()`, the method returns `9` and the original `IllegalStateException` is no longer propagated outward. This misleads the caller into thinking the operation succeeded and loses the error signal.

### Case C: `throw` in `finally` replaces `return`

~~~java
static int throwsInsteadOfReturning() {
    try {
        return 7;
    } finally {
        throw new IllegalStateException("cleanup failed");
    }
}
~~~

The method does not return `7`. It throws `IllegalStateException("cleanup failed")`. If the caller does not catch it, the exception continues propagating.

### Case D: `throw` in `finally` replaces an exception from `try`

~~~java
static void replacesFailure() {
    try {
        throw new IllegalArgumentException("original failure");
    } finally {
        throw new IllegalStateException("cleanup failure");
    }
}
~~~

The exception that exits is `IllegalStateException("cleanup failure")`. The original exception is not automatically saved as `cause` or `suppressed` merely because two `throw` statements occurred in a manual `try/finally`. If you need to preserve multiple errors, design an appropriate handling mechanism and cause chaining; for `AutoCloseable` resources, try-with-resources usually handles error preservation better.

**General rule:** When a `finally` block completes abnormally due to a new reason, that reason can **replace** the pending reason for exiting `try/catch`, whether the old reason was `return`, `break`, `continue`, or an exception.

## 8. Can `finally` change the target of `break` or `continue`?

You need to distinguish between two cases.

- If `finally` only executes normal statements and finishes, the original `break` or `continue` request will be carried out next.
- If `finally` throws an exception, returns from the method, or performs its own valid control transfer, the pending flow can be replaced.

Example:

~~~java
static void breakCancelledByException() {
    for (int i = 0; i < 1; i++) {
        try {
            break;
        } finally {
            throw new IllegalStateException("cleanup failed");
        }
    }
}
~~~

This is a valid illustrative method: `break` is requested, but `finally` throws an exception; the method terminates abnormally and the caller receives `IllegalStateException` if there is no handler here. Therefore, `finally` cannot be interpreted as a "callback function that always returns" in every situation.

Conversely, if `finally` only logs:

~~~java
static void breakPreserved() {
    while (true) {
        try {
            break;
        } finally {
            System.out.println("cleanup");
        }
    }
    System.out.println("done");
}
~~~

The order is `cleanup` then `done`. `finally` does not alter the `break` target.

A similar example with `continue`:

~~~java
static void continuePreserved() {
    for (int i = 0; i < 2; i++) {
        try {
            continue;
        } finally {
            System.out.println("finally " + i);
        }
    }
    System.out.println("done");
}
~~~

Stdout:

~~~text
finally 0
finally 1
done
~~~

There is no return value to assign for `continue`; it directs the loop. `finally` runs before each next step.

## 9. Nested `finally`: executes from inside out

When `return`, `break`, `continue`, or an exception must exit multiple `try` regions, Java executes the associated `finally` blocks in the order of unwinding nested regions.

~~~java
static int nestedFinally() {
    try {
        try {
            System.out.println("inner try");
            return 5;
        } finally {
            System.out.println("inner finally");
        }
    } finally {
        System.out.println("outer finally");
    }
}
~~~

Output when calling `nestedFinally()`:

~~~text
inner try
inner finally
outer finally
~~~

Then the caller receives `5` if both `finally` blocks complete normally.

In a program with multiple method calls, throwing an exception can also cause Java to run `finally` blocks of **methods currently unwinding off the stack** before reaching an outer handler. For `return`, only the relevant `try` regions on the exit path of the current method are executed; `return` does not itself propagate back through callers as an exception does.

## 10. `finally` with `catch` and exceptions

Example:

~~~java
static int recover(String text) {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException e) {
        System.out.println("parse failed");
        return -1;
    } finally {
        System.out.println("cleanup");
    }
}
~~~

If `text` is `"17"`, the method prints `cleanup` and then returns `17`. If it is `"abc"`, `catch` prints `parse failed`, prepares to return `-1`, `finally` prints `cleanup`, and only then is `-1` returned.

This illustrates that `finally` also runs after a `return` originating from a **`catch` block**, not only from the `try` body.

In the example in the earlier section, `throwingDemo()` showed the case with no handler in the method; `finally` still runs before the exception goes out to the caller. When an exception arises inside `finally` itself, the selection of the final exception depends on the abnormal completion rules already explained.

A `catch` block **does not catch** a new exception thrown inside the sibling `finally` block of that same `try` construct; the new error is propagated to enclosing handling regions.

## 11. Comparison with try-with-resources

A common purpose of `finally` is releasing resources:

~~~java
java.io.InputStream stream = openStream();
try {
    useStream(stream);
} finally {
    stream.close();
}
~~~

This is an **illustrative snippet**, assuming `openStream()` and `useStream(...)` are available and the enclosing method handles checked exceptions appropriately. If `useStream` executes `return`, `break`, `continue`, or throws an error causing code to exit the construct, Java still passes through `stream.close()` in `finally` according to the rule.

However, `close()` can also throw an exception and **mask the original error or alter the return result**. For resources implementing `AutoCloseable`, prefer **try-with-resources**:

~~~java
static String firstLine(String text) throws java.io.IOException {
    try (java.io.BufferedReader reader =
                 new java.io.BufferedReader(
                         new java.io.StringReader(text))) {
        return reader.readLine();
    }
}
~~~

This method can be placed in a Java 17+ class. The `reader` resource is closed automatically after the `try` body prepares to complete and before the method's `return` actually finishes.

With try-with-resources, if the `try` body has already thrown an exception and `close()` also throws an error, Java normally keeps **the exception from the `try` body as the primary exception** and attaches the resource-closing error to `getSuppressed()`. This mechanism differs from writing `finally { resource.close(); }` manually, where a new error from `close()` can replace the old error.

If the `try` body is **returning normally** but `close()` throws an error, the call can still end abnormally instead of returning the result. Therefore, the idea that "reaching `return` guarantees the caller receives the result" is also untrue in try-with-resources.

## 12. Cases where `finally` is not guaranteed to run

`finally` provides strong cleanup behavior in normal Java execution flow, but it is not an unconditional guarantee under all circumstances.

Situations to keep in mind:

- **The VM or process is terminated:** such as `Runtime.getRuntime().halt(...)`, the OS terminating the process, or a fatal JVM error.
- **`System.exit(...)` when it actually terminates the VM:** the program does not perform Java stack unwinding in a way that guarantees running `finally` for all threads.
- **Never leaving the `try` block:** for example, the thread is stuck in an infinite loop with no exit step.
- **Execution cannot continue normally due to the environment:** power loss, forced termination, or failures outside the application's control.

Even when `finally` runs, it can fail midway; do not assume every statement inside `finally` is guaranteed to finish. If you need durable guarantees for data, transactions, or progress, you must use appropriate designs such as transaction management, event logging, restart recovery mechanisms, or storage-level guarantees.

**Do not use `System.exit` to "test" `finally` ordering in the main program** because it terminates the process and can interfere with running other examples. Test `return`, `break`, and `continue` scenarios with small methods like those above.

## 13. Common misconceptions

### Misconception 1: "When `return` runs, `finally` is skipped"

False. When `return` is inside a `try`/`catch` with `finally`, `finally` normally runs **before the caller receives the result**.

### Misconception 2: "If `finally` modifies a primitive variable, the `return` value changes accordingly"

Not necessarily. The `return` expression's value is determined before `finally`. With `int value = 3; try { return value; } finally { value = 9; }`, the normal return value is still `3`.

### Misconception 3: "`finally` cannot affect the returned object"

False. If the expression returns a reference to a mutable object, `finally` can modify the state of that same object before the caller receives the reference. This differs from reassigning a local reference variable.

### Misconception 4: "`break` or `continue` jumps straight past `finally`"

False. Any `finally` regions exited by the jump path still run in order before Java proceeds to the jump target, unless a new abnormal completion reason replaces it.

### Misconception 5: "`continue` makes a `for` loop skip the increment step too"

False. After `finally` completes normally, `continue` in a `for` loop proceeds to the `update` part and then checks the condition for the next iteration. It skips the rest of the current iteration's body, not the loop's update mechanism by default.

### Misconception 6: "`finally` only runs when an exception occurs"

False. `finally` also runs when `try` completes normally, when `catch` has handled an error, and when preparing to exit due to `return`/`break`/`continue`.

### Misconception 7: "Put `return` in `finally` to guarantee a result"

This is a dangerous practice. A `return` in `finally` can replace a `return` in `try` and **swallow a propagating exception**, leaving the caller unaware that the operation failed.

### Misconception 8: "If `finally` throws an error, the old exception automatically becomes its cause"

No. In a manual `try/finally`, Java does not automatically chain the old exception as the `cause` of the new error. You need to design error handling explicitly, or leverage try-with-resources suppressed exceptions when appropriate.

### Misconception 9: "Nested `finally` blocks run from outside in"

False. When exiting multiple nested `try` regions, the inner region's `finally` block runs first, followed by the outer region's.

### Misconception 10: "`finally` is an absolute guarantee even if the JVM is killed"

No. Mechanisms that forcibly stop the VM/process or prevent exiting `try` can prevent `finally` from being executed.

### Misconception 11: "Another `return` statement in `finally` is just a code-style issue"

No. It changes **execution semantics** and can hide errors. Some code-analysis tools will warn about it, but the language rules are the main reason to avoid it.

### Misconception 12: "`break` in a `switch statement` and `yield` in a `switch expression` are the same"

No. In a classic `switch statement`, `break` terminates the statement; in a `switch expression`, `yield` provides the expression's value. When these paths exit a `try` construct with `finally`, the associated `finally` is still processed. Do not replace `yield` with `break value` in Java 17.

## 14. Self-check exercises

**Question 1.** A method contains `try { return 5; } finally { System.out.println("cleanup"); }`. What line does it print before the caller receives `5`?

**Question 2.** Does `int x = 1; try { return x; } finally { x = 2; }` return `1` or `2`? Why?

**Question 3.** If `try` returns a `StringBuilder` and `finally` calls `append(...)` on the same object, can the caller see the new content?

**Question 4.** Does `break` inside a `try` within a `for` loop cause `finally` to run before leaving the loop?

**Question 5.** With `continue` in a `for` loop, does the loop-variable update step happen before or after the associated `finally`?

**Question 6.** When `break OUTER` exits two nested `try` blocks, which `finally` block runs first?

**Question 7.** If `try` intends to return `7` but `finally` contains `return 9;`, what does the caller receive?

**Question 8.** If `try` throws `IllegalArgumentException` but `finally` contains `return 0;` in a method returning `int`, does the exception still propagate to the caller?

**Question 9.** If `try` intends to `return 7` but `finally` throws `IllegalStateException`, what is the outcome?

**Question 10.** Why can an error occurring in `finally { resource.close(); }` hide the original exception from `try`?

**Question 11.** Where does try-with-resources store the resource-closing error when the `try` body has already thrown a primary exception?

**Question 12.** When a `catch` executes `return -1;`, does the `finally` of the same construct normally run?

**Question 13.** An infinite loop sits inside `try` and never exits. Is there any basis to claim `finally` will run immediately?

**Question 14.** How can calling `System.exit(...)` break the expectation that "every `finally` runs"?

**Question 15.** If a `finally` completes normally, does it preserve or replace the pending completion reason of `try`?

### Suggested answers

1. It prints `cleanup` first, and only then does the caller receive `5`.
2. It returns `1` because the `return` expression's value is evaluated before `finally` modifies the variable.
3. Yes, because the returned reference still points to the same mutable object.
4. Yes, under normal Java execution flow.
5. After `finally`, before checking the condition for the next iteration.
6. The `finally` in the inner region runs first.
7. Receives `9`; `return` from `finally` replaces the pending result.
8. No, the error can be hidden and the caller receives `0`; this is dangerous code.
9. The method throws `IllegalStateException`, not returning `7`.
10. Because a new `throw` from `finally` can replace the previous abnormal completion reason.
11. Usually in `getSuppressed()` of the primary exception.
12. Yes; `finally` runs before `return -1` is completed.
13. No; there must be an execution path leaving `try` to reach cleanup processing.
14. The VM can terminate without unwinding all Java stack frames to run `finally`.
15. It preserves the old completion reason; only when `finally` itself completes abnormally can it replace it.

## 15. Key takeaways

**`finally` is not only for exceptions.** With `return`, Java evaluates the return expression first, runs the associated `finally`, and then completes the return if `finally` finishes normally. With `break` and `continue`, Java executes the necessary `finally` blocks before leaving the loop or moving to the next iteration. With nested regions, `finally` runs from inside out when exiting multiple scopes. **Avoid unintended `return` or `throw` in `finally`**, as they can override the original return value, jump request, or exception.
