# The `finally` Block When `try` Completes Normally or Throws an Exception in Java

The **`finally`** block is an optional part of the `try` construct in Java, used to perform work that must run **when control flow exits the `try` construct**, regardless of whether the `try` block completes normally or completes abruptly due to an exception. If there is a `catch` block, `finally` also runs after the selected `catch` branch completes or before an exception from `catch` continues propagating outward.

Importantly, **`finally` does not catch exceptions on its own and does not guarantee that the program will continue running normally**. It is a step in the process of exiting the block; after `finally` completes normally, the pending result from `try`/`catch` is preserved. If `finally` itself throws an exception or executes `return`, it can replace the pending result and even mask the original error.

This lesson focuses on the two core paths: **`try` completes normally** and **`try` throws an exception**. At the same time, you will see cases involving `catch`, `return`, `throw`, nested `finally` blocks, execution guarantee limits, and proper resource cleanup on Java 17+.

## 1. Syntax and Position of `finally`

A typical `try-catch-finally` construct:

~~~java
try {
    // Task that may succeed or throw an exception.
} catch (SomeException ex) {
    // Handle the corresponding exception.
} finally {
    // Work to perform when exiting the construct.
}
~~~

This is an illustrative skeleton; `SomeException` must be a valid exception type and the bodies must be replaced with real code.

Java allows several ways to organize it:

~~~java
// try-finally only, without catch.
try {
    work();
} finally {
    cleanup();
}
~~~

~~~java
// With catch and finally.
try {
    work();
} catch (IOException ex) {
    handle(ex);
} finally {
    cleanup();
}
~~~

~~~java
// With multiple catch blocks and one finally.
try {
    work();
} catch (FileNotFoundException ex) {
    handleMissing(ex);
} catch (IOException ex) {
    handleOtherIo(ex);
} finally {
    cleanup();
}
~~~

The snippets above are **structural illustrations**, assuming the methods/types/imports are already defined. A traditional `try` must have at least one `catch` or one `finally`. The `finally` block comes **after all `catch` blocks** of that construct, and there is only **one direct `finally` block** per `try`.

`finally` is not a method, has no return type, takes no parameters, and has no `throws` exception list of its own. If a statement inside `finally` can throw a checked exception, the responsibility to catch or declare it belongs to the enclosing method or constructor.

## 2. When `try` Completes Normally

**Normal completion** means execution reaches the end of the `try` body without being redirected by an abrupt completion cause such as an exception or `return`. In that case:

1. The statements in `try` are executed sequentially.
2. No `catch` branch of this construct is selected.
3. The `finally` block runs.
4. If `finally` completes normally, the program continues at the statement after the entire `try`/`catch`/`finally` construct.

Short example:

~~~java
// Illustrative snippet inside a method.
try {
    System.out.println("A. Trong try");
    System.out.println("B. Try thành công");
} finally {
    System.out.println("C. Trong finally");
}
System.out.println("D. Sau try");
~~~

Stdout:

~~~text
A. Trong try
B. Try thành công
C. Trong finally
D. Sau try
~~~

**Key takeaway:** `finally` does not only run when an exception occurs. If `try` runs to completion normally, `finally` still runs as the final step before exiting the construct. Therefore, `finally` should not be treated as a special kind of `catch` or a place solely for error-handling logic.

## 3. When `try` Throws an Exception and Has a Matching `catch`

If an exception is thrown from the `try` body, Java searches for a matching `catch` in the declared order. When a `catch` catches and handles it successfully:

1. The remaining statements in the `try` body after the throw point are skipped.
2. The matching `catch` branch is executed.
3. After `catch` completes normally, `finally` is executed.
4. If `finally` also completes normally, the program continues after the entire construct.

Example:

~~~java
// Illustrative snippet inside a method.
try {
    System.out.println("Trong try");
    throw new IllegalArgumentException("dữ liệu sai");
} catch (IllegalArgumentException ex) {
    System.out.println("Đã bắt: " + ex.getMessage());
} finally {
    System.out.println("Trong finally");
}
System.out.println("Sau cấu trúc");
~~~

Stdout:

~~~text
Trong try
Đã bắt: dữ liệu sai
Trong finally
Sau cấu trúc
~~~

Here, the exception **was handled in `catch`**. Therefore, after `finally`, execution can continue normally. This does not mean `finally` handled the exception. `catch` did that; `finally` only performed the final step when exiting the construct.

Another `catch` at the same level does not run additionally just because the first `catch` has finished. `catch` blocks are alternative branches for handling an exception from the `try` scope, not a sequential execution chain.

## 4. When `try` Throws an Exception Without a Matching `catch`

If no `catch` can handle the exception, **`finally` still gets a chance to run before the exception continues propagating** to the caller or an enclosing handler.

~~~java
// Illustrative snippet inside a method that does not catch IllegalStateException itself.
try {
    System.out.println("Trong try");
    throw new IllegalStateException("trạng thái sai");
} finally {
    System.out.println("Trong finally");
}
~~~

When executed, the program prints:

~~~text
Trong try
Trong finally
~~~

After that, `IllegalStateException` is still being thrown. If the calling method does not catch it, the error continues up the call chain. If there is no suitable handler, the thread may terminate abnormally and the uncaught exception handler may print the stack trace to stderr.

In this case, `finally` **does not turn an abrupt path into a normal one**. It runs and then allows the original exit cause to continue, provided `finally` itself completes normally.

The same happens when `catch` is selected but **rethrows** the exception or creates another exception: `finally` is executed on the path as the exception propagates outward. The difference is that the exception ultimately propagated may be the original error or a new exception created by code in `catch`.

## 5. Complete Program: Comparing Three Execution Paths

Save the following program to `FinallyPathsDemo.java`:

~~~java
public class FinallyPathsDemo {
    static void run(String mode) {
        System.out.println("Bắt đầu: " + mode);
        try {
            System.out.println("Trong try");
            if (mode.equals("caught")) {
                throw new IllegalArgumentException("đầu vào sai");
            }
            if (mode.equals("uncaught")) {
                throw new IllegalStateException("trạng thái sai");
            }
            System.out.println("Try hoàn tất");
        } catch (IllegalArgumentException ex) {
            System.out.println("Catch: " + ex.getMessage());
        } finally {
            System.out.println("Finally: " + mode);
        }
        System.out.println("Sau try: " + mode);
    }

    public static void main(String[] args) {
        run("normal");
        run("caught");
        try {
            run("uncaught");
        } catch (IllegalStateException ex) {
            System.out.println("Catch ngoài: " + ex.getMessage());
        }
        System.out.println("Kết thúc main");
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 FinallyPathsDemo.java
java FinallyPathsDemo
~~~

Exact stdout:

~~~text
Bắt đầu: normal
Trong try
Try hoàn tất
Finally: normal
Sau try: normal
Bắt đầu: caught
Trong try
Catch: đầu vào sai
Finally: caught
Sau try: caught
Bắt đầu: uncaught
Trong try
Finally: uncaught
Catch ngoài: trạng thái sai
Kết thúc main
~~~

**Run-by-run analysis:**

- **`normal`:** no exception. `try` completes, `finally` runs, and then the line `Sau try: normal` runs.
- **`caught`:** `IllegalArgumentException` is thrown and handled by the `catch` in the same construct. `finally` runs after the handler, and the line `Sau try: caught` is still printed.
- **`uncaught`:** `IllegalStateException` does not match `catch (IllegalArgumentException)`. `finally` still runs, and then the error propagates to `catch (IllegalStateException)` in `main`. The line `Sau try: uncaught` **does not run**, because the `run` method terminated abruptly.

This is a concrete illustration of the difference between **whether `finally` runs** and **whether execution continues after the `try` construct**. Those two outcomes must be evaluated separately.

## 6. Control-Flow Progression Table

| Case | Same-construct `catch` | `finally` | After the `try` construct |
| --- | --- | --- | --- |
| `try` body completes normally | Does not run | Runs | Runs if `finally` completes normally |
| `try` throws exception, matching `catch` handles it | Runs | Runs | Runs if `catch` and `finally` complete normally |
| `try` throws exception, no matching `catch` | Does not handle that error | Runs on the exit path | Does not run on the same execution path if the exception keeps propagating |
| `catch` rethrows or throws another exception | Selected branch completes abruptly | Runs before exiting | Does not run if the exception keeps propagating |
| `try` or `catch` executes `return` | Depends on path | Runs before returning | Does not run in that method if `return` remains in effect |
| `finally` itself throws or executes `return` | Depends on path | Completes abruptly | Pending result may be replaced |

The table assumes the code actually reaches the construct exit point and the execution environment allows Java steps to continue. Cases of forced JVM termination, threads never leaving a loop, or severe machine failures are discussed in the limitations section.

## 7. `finally` Also Runs When `try` or `catch` Has `return`

A common point of confusion is that `return` is not an exception, yet it is still an **abrupt completion cause of the `try` statement in JLS terminology**: control is about to leave the method. Before the return takes effect, Java executes the `finally` block.

Example:

~~~java
// Illustrative snippet placed in a class.
static int ten() {
    try {
        return 10;
    } finally {
        System.out.println("Finally trước return");
    }
}
~~~

If `ten()` is printed, the order will be:

~~~text
Finally trước return
10
~~~

With `return expression;`, Java **evaluates the return expression before running `finally`**. If `finally` completes normally, the already-computed value is returned. This is especially important when `finally` modifies a **local variable** after a primitive value has already been prepared for return.

### Complete Java Example with `return`

File `FinallyReturnDemo.java`:

~~~java
public class FinallyReturnDemo {
    static int compute() {
        int value = 10;
        try {
            System.out.println("Try chuẩn bị return");
            return value;
        } finally {
            value = 20;
            System.out.println("Finally đổi local thành " + value);
        }
    }

    static int catchAndReturn() {
        try {
            throw new IllegalArgumentException("lỗi");
        } catch (IllegalArgumentException ex) {
            System.out.println("Catch chuẩn bị return");
            return 3;
        } finally {
            System.out.println("Finally chạy sau catch");
        }
    }

    public static void main(String[] args) {
        System.out.println("Kết quả: " + compute());
        System.out.println("Kết quả catch: " + catchAndReturn());
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 FinallyReturnDemo.java
java FinallyReturnDemo
~~~

Stdout:

~~~text
Try chuẩn bị return
Finally đổi local thành 20
Kết quả: 10
Catch chuẩn bị return
Finally chạy sau catch
Kết quả catch: 3
~~~

The reason `compute()` returns `10` is that the expression `return value` is evaluated **before** `finally` modifies the variable `value` to `20`. `finally` does not re-evaluate the return expression.

Note: for **reference types**, the return value is the computed reference. If `finally` mutates the state of **the referenced object itself**, the caller can observe that change; however, reassigning the local variable to a different reference in `finally` does not change the reference already chosen to be returned.

The `catchAndReturn()` method shows that a `return` inside `catch` also goes through `finally` before exiting the method.

## 8. When `finally` Also Throws an Exception: Risk of Masking the Original Error

Suppose the `try` block throws error A, but during cleanup, `finally` throws error B:

~~~java
// Illustrative snippet showing a dangerous situation.
try {
    throw new IllegalStateException("lỗi A");
} finally {
    throw new IllegalArgumentException("lỗi B");
}
~~~

On this path, error B from `finally` **replaces the pending exit cause**, which was error A. If an outer handler catches `RuntimeException`, it sees `IllegalArgumentException("lỗi B")`. Java does not automatically attach error A as the `cause` or `suppressed` exception of error B for a manual `finally`.

Likewise, `return` inside `finally` can **mask even a propagating exception**. That is why you should not write `return` or `throw` casually inside `finally`.

### Program Verifying Error-Masking Behavior

File `FinallyOverridesDemo.java`:

~~~java
public class FinallyOverridesDemo {
    static int unsafe() {
        try {
            throw new IllegalStateException("lỗi gốc");
        } finally {
            return 99;
        }
    }

    public static void main(String[] args) {
        System.out.println("Kết quả: " + unsafe());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 FinallyOverridesDemo.java
java FinallyOverridesDemo
~~~

Exact stdout:

~~~text
Kết quả: 99
~~~

This example **intentionally demonstrates an unsafe coding style**. The `IllegalStateException` is dropped from the outward error path because `finally` ends with `return 99`. In a real application, this can make a serious failure look like a successful execution.

Especially with manual cleanup:

~~~java
// Illustrative snippet where close() may throw IOException.
try {
    doWork();
} finally {
    resource.close();
}
~~~

If both `doWork()` and `resource.close()` throw exceptions, the resource-closing error can mask the error from `doWork()`. When managing an `AutoCloseable`, prefer **`try-with-resources`** for its suppressed exception mechanism rather than writing uncontrolled manual cleanup.

## 9. `finally` and `try-with-resources`: Timing and Error Preservation

`try-with-resources` syntax:

~~~java
// Illustrative snippet using an AutoCloseable object returned by openResource().
try (Resource resource = openResource()) {
    work(resource);
} catch (IOException ex) {
    handle(ex);
} finally {
    afterWork();
}
~~~

The snippet above requires appropriate declarations of `Resource`, `openResource`, `work`, `handle`, `afterWork`, and imports. With `try-with-resources`, Java automatically closes resources that were successfully initialized when exiting the `try` body, in the **reverse** order of successful initialization.

In the construct above, closing the resource happens **before** the `catch` or `finally` attached to that same construct runs. Thus, the handler can receive an exception thrown from the body or from closing the resource.

When the `try` body throws a primary exception and `close()` also throws, the close exception is normally added to the **suppressed exceptions** list of the primary exception. Check `ex.getSuppressed()` if you need to diagnose multiple errors at once.

| Mechanism | Error from body and error from closing resource |
| --- | --- |
| Manual `try` + `finally { resource.close(); }` | The `close()` error can replace the original error if `finally` itself throws |
| `try-with-resources` | The `close()` error is normally attached as suppressed on the primary error |
| `catch` wrapping the error with `new ...(..., cause)` | The original error is stored as **cause**, which differs from suppressed |

`try-with-resources` is suitable for `AutoCloseable` resources such as streams, readers, or connections. `finally` remains useful for other final actions, such as restoring state or recording completion time, but its body should be kept concise and avoid operations that can fail while another error is propagating.

Do not close a resource twice manually if `try-with-resources` is already responsible for it; duplicate closing can be redundant or cause side effects depending on the resource type.

## 10. `finally` Runs After `catch`, Even When `catch` Rethrows

Example:

~~~java
// Illustrative snippet inside a method that may throw IllegalStateException.
try {
    throw new IllegalArgumentException("đầu vào sai");
} catch (IllegalArgumentException ex) {
    System.out.println("Trong catch");
    throw new IllegalStateException("xử lý thất bại", ex);
} finally {
    System.out.println("Trong finally");
}
~~~

Stdout before the new exception continues propagating:

~~~text
Trong catch
Trong finally
~~~

Here, `IllegalStateException` is created inside `catch`, with `IllegalArgumentException` as its cause. After `finally` (if it completes normally), the new exception continues to the enclosing `try` construct or the calling method.

Sibling `catch` blocks of the same construct **do not catch a new exception thrown from another `catch`**. When you need to handle an error thrown inside a handler, place a nested `try/catch` inside the handler or an outer `try` that truly wraps the entire construct.

This reinforces two distinct roles:

- `catch` chooses how to handle a matching exception and may complete normally or throw onward.
- `finally` performs the construct's final step regardless of how the selected `catch` branch completed, as long as execution continues to that step.

## 11. In What Order Do Nested `finally` Blocks Run?

In nested `try` constructs, an exception thrown at a deep level may pass through multiple `finally` blocks. In terms of control flow, the `finally` in the **inner construct** runs first, followed by the outer `finally` blocks as control continues exiting each construct.

~~~java
// Illustrative snippet inside a method.
try {
    try {
        System.out.println("Trong try trong");
        throw new IllegalStateException("lỗi");
    } finally {
        System.out.println("Finally trong");
    }
} catch (IllegalStateException ex) {
    System.out.println("Catch ngoài");
} finally {
    System.out.println("Finally ngoài");
}
~~~

Stdout:

~~~text
Trong try trong
Finally trong
Catch ngoài
Finally ngoài
~~~

Explanation: the exception occurs in the inner `try`; because there is no handler in the inner construct itself, its `finally` runs and then the error is passed to the outer `catch`. After the outer handler completes normally, the outer `finally` executes.

If an inner `finally` throws a new exception, the outer level may receive that new exception; this makes reading stack traces and cause chains even more important when debugging.

## 12. Is `finally` Guaranteed to Run Under All Circumstances?

**Not under all absolute circumstances.** According to Java semantics, when control flow **exits a `try` construct along the specified paths** (success, exception, `return`, `break`, `continue`), the associated `finally` is executed before completing the exit from the construct. However, that does not guarantee `finally` always runs even if the program or environment has stopped executing.

Examples of limitations:

- **`System.exit(...)` or `Runtime.halt(...)`:** can cause the JVM to terminate without continuing to execute `finally` blocks of active calls; `System.exit` runs shutdown mechanisms, but does not unwind stacks as in a normal `throw`.
- **Process forcefully killed, JVM crash, power loss:** you cannot rely on `finally` to complete an external operation.
- **Thread never leaves `try`** (for example, stuck in an infinite loop): `finally` never gets a chance to run.
- **Extremely severe VM or environment failure:** cleanup steps cannot always be guaranteed to continue.

Therefore, `finally` is suitable for cleanup **within normal Java execution lifecycles**, but it does not replace durable storage, transactions, or fault-tolerant design when crash recovery guarantees are needed.

Avoid confusing this with ordinary runtime errors such as `NullPointerException`: they are still `Throwable` objects; when thrown and Java follows a handleable exit path, the associated `finally` still runs.

## 13. `finally` in Loops with `break` and `continue`

When a `try` body is placed inside a loop, `break` or `continue` may request transferring control out of the block. If that transfer exits the `try` construct, `finally` still runs before the loop exits or starts the next iteration.

~~~java
// Illustrative snippet inside a method.
for (int i = 0; i < 3; i++) {
    try {
        if (i == 1) {
            continue;
        }
        System.out.println("Try: " + i);
    } finally {
        System.out.println("Finally: " + i);
    }
}
~~~

Stdout:

~~~text
Try: 0
Finally: 0
Finally: 1
Try: 2
Finally: 2
~~~

At `i == 1`, `continue` skips the print statement in `try`, but `finally` still executes before moving to iteration `i == 2`. With `break`, `finally` will likewise run before exiting the loop.

This is why when reading code with `return`, `break`, `continue`, or `throw`, you must account for the effect of `finally` before deciding which statement actually runs next.

## 14. Common Mistakes When Using `finally`

| Misconception or design mistake | Consequence | How to handle |
| --- | --- | --- |
| Thinking `finally` only runs on error | Missing final work on the success path | Understand that `finally` runs when exiting `try` both normally and abruptly |
| Thinking `finally` catches unhandled exceptions itself | The exception still propagates outward after `finally` | Use an appropriate `catch` where the error can be handled |
| Thinking statements after `throw` in `try` still run before `finally` | Misreading control flow | Trace from the throw point to the handler/`finally`, skipping the rest of the normal path |
| Putting `return` in `finally` | Can replace `return` or mask exceptions from `try`/`catch` | Avoid `return` in `finally` |
| Performing error-prone cleanup in a manual `finally` | Can mask the original error | Prefer `try-with-resources` or handle cleanup errors intentionally |
| Thinking modifying a local variable in `finally` makes `return value` return the new value | `return` already evaluated the expression earlier | Identify the pending return value and distinguish primitive vs. reference types |
| Ignoring `finally` blocks of nested `try` constructs | Mispredicting log/cleanup order | Trace block exit order from inner to outer |
| Treating `finally` as the place to handle all exceptions | Loses error classification and per-error recovery | Use `catch` for handling, `finally` for final work |
| Assuming `finally` is guaranteed to run even if `System.exit` is called | Cleanup may be skipped when the JVM terminates | Use appropriate lifecycle mechanisms when shutdown handling is needed |
| Testing only the success path | Missing cleanup bugs or masked exceptions | Test success, caught, uncaught, and errors thrown during cleanup |

Keep work inside `finally` **short, predictable, and unlikely to fail**. If business logic requires real rollback or data atomicity, use transactions or an appropriate mechanism; `finally` only governs Java control flow.

## 15. Self-Check Questions

**Question 1.** `try` runs successfully to the end. Does `finally` run?

**Answer:** Yes, provided control flow exits the construct normally and the environment continues executing.

**Question 2.** `try` throws `IllegalArgumentException`, and a matching `catch` handles it. What is the order?

**Answer:** Throw point in `try` → matching `catch` → `finally` → statement after the entire construct (if `finally` completes normally).

**Question 3.** `try` throws `IllegalStateException`, but there is no matching `catch`. Does `finally` make the error disappear?

**Answer:** No. `finally` runs before the error continues propagating outward, provided `finally` completes normally.

**Question 4.** `return 10;` in `try`, then `finally` assigns the original local variable to `20`. What is the return value?

**Answer:** If the `return` expression was already evaluated as `10` and `finally` completes normally, the result is `10`. For reference objects, distinguish mutating the object itself.

**Question 5.** If `finally` has `return 99;` while `try` throws an exception, what can happen?

**Answer:** `return 99` can replace the exit cause from `try`, masking the exception.

**Question 6.** If `finally` throws `IOException` while `try` is throwing another error, which error can propagate out?

**Answer:** The exception from `finally` can replace the earlier error when using manual cleanup. If managed with `try-with-resources`, the resource-closing error has the suppressed exception mechanism.

**Question 7.** Does a nested `try`'s `finally` run before or after the outer `finally`?

**Answer:** Following the construct exit order, the inner `finally` normally runs before the outer one.

**Question 8.** Does `continue` inside `try` skip `finally`?

**Answer:** No, the associated `finally` runs before moving to the next loop iteration, if that transfer exits the construct.

**Question 9.** Should you use `finally` to manually close every `AutoCloseable` resource?

**Answer:** You should generally prefer `try-with-resources` because it manages closing and helps preserve close errors via suppressed exceptions.

**Question 10.** Is `finally` guaranteed to run after `System.exit(0)`?

**Answer:** No; you should not depend on `finally` for cleanup when the JVM is terminated.

## References

- [Java Language Specification 17, §14.20.2 — Execution of try-finally and try-catch-finally](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.2): rules for `finally` when `try` completes normally or abruptly.
- [Java Language Specification 17, §14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): resource closing, suppressed exceptions, and execution order.
- [Java Language Specification 17, §14.17 — The return Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.17): evaluation of the `return` expression before exiting a method.
- [Java SE 17 API — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getCause()`, `getSuppressed()`, and stack traces.
- [Oracle Java Tutorials — The finally Block](https://docs.oracle.com/javase/tutorial/essential/exceptions/finally.html): intuitive explanation of cleanup (historical tutorial examples, foundational rules still apply).

**Remember:** when `try` completes normally, `finally` runs before the program continues; when `try` throws an exception, `finally` runs on the handling or error-propagation path. If `finally` itself completes abruptly, it can change the entire outcome. Therefore, use `catch` to handle exceptions, `finally` for final work, and `try-with-resources` to manage `AutoCloseable` resources when appropriate.
