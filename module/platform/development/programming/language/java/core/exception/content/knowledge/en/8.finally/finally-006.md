# `return` or `throw` in `finally` Masks the Previous Result

In Java, the `finally` block is normally executed when exiting a `try` construct, whether the control flow is completing normally, preparing to `return`, or propagating an exception. This is an important mechanism for resource cleanup, but it also carries a risk:

> **If `finally` itself completes abruptly with `return` or `throw`, the pending completion reason from `try` or `catch` is replaced by the new reason from `finally`.**

For example, if a method intends to return `10` but `finally` executes `return 20;`, the caller receives `20`. If a method intends to throw `IllegalStateException("original")` but `finally` throws `IllegalArgumentException("cleanup failed")`, the caller receives the **new exception**, not the original one. This is not merely a code style issue; it can erase error traces, return incorrect results, and cause a program to report success even when the operation actually failed.

## 1. Fundamental Rule: `finally`'s Completion Reason Can Override the Previous One

Java distinguishes two kinds of completion:

- **Normal completion:** a block runs to its end without transferring control out via `return`, `throw`, `break`, or `continue`.
- **Abrupt completion:** leaving a block due to a cause such as `return`, `throw`, `break`, or `continue`.

When exiting `try` or `catch`, a corresponding `finally` block is executed according to the language rules. At that point:

1. If `finally` **completes normally**, the previous completion reason is preserved. A `return` from `try` continues returning its result; an exception from `try` continues propagating.
2. If `finally` **completes abruptly**, the new reason from `finally` replaces the previous completion reason, whether that previous reason was a return value or an exception.

We can visualize this as follows:

```text
try or catch prepares to complete with reason R
                      │
                      ▼
                 run finally
                      │
          ┌───────────┴────────────┐
          ▼                        ▼
  finally completes        finally completes
      normally          abruptly with reason S
          │                        │
          ▼                        ▼
       keep R                    use S
                            (R is discarded)
```

In general, `R` or `S` can be `return`, `throw`, `break`, or `continue`. This lesson focuses on **`return` and `throw` inside `finally`** because they are the most likely to cause serious bugs: returning the wrong result or masking the real root cause.

## 2. Behavior Matrix: What Does `try` Do, and What Does `finally` Do?

| Result from `try` / `catch` | How does `finally` complete? | Result observed by caller |
| --- | --- | --- |
| Runs to end normally | Runs to end normally | Continues normal flow |
| `return A;` | Runs to end normally | Returns `A` |
| `throw E1;` | Runs to end normally | Throws `E1` |
| `return A;` | `return B;` | **Returns `B`**, `A` is discarded |
| `throw E1;` | `return B;` | **Returns `B`**, `E1` is masked |
| `return A;` | `throw E2;` | **Throws `E2`**, does not return `A` |
| `throw E1;` | `throw E2;` | **Throws `E2`**, `E1` is masked |
| Runs to end normally | `return B;` | Returns `B` |
| Runs to end normally | `throw E2;` | Throws `E2` |

In the table, `A` and `B` are illustrative values; `E1` and `E2` are exceptions. "Masked" means that **unless saved by a separate mechanism, the caller no longer receives the previous error or result**. Java does not automatically attach `E1` as the `cause` or a *suppressed exception* of `E2` just because `finally` throws a new error.

**Do not confuse this:** an ordinary `finally` block that only logs or releases resources and then completes normally **does not** cause the return value or exception from `try` to be lost.

## 3. `return` in `finally` Overrides `return` in `try`

Consider the method:

```java
static int wrongResult() {
    try {
        return 10;
    } finally {
        return 20;
    }
}
```

This is an **illustrative method** that needs to be placed inside a Java class. The result of `wrongResult()` is **`20`**.

Execution sequence:

1. `try` evaluates the expression `10` and prepares to return it.
2. Before the method actually returns to the caller, Java runs `finally`.
3. `finally` executes `return 20;`, creating **a new completion reason**.
4. The pending value `10` is discarded; the caller receives `20`.

Many people assume `finally` merely "runs afterward" once `return` has already finished. That is wrong: `finally` runs **before the call finishes**, and it can alter the completion result.

The danger is that the code may look as if it handled everything properly in `try`, yet an accidental `return` in the cleanup branch causes the result not to reflect the main operation.

### `return` in `catch` Can Also Be Overridden

```java
static String fallback() {
    try {
        throw new IllegalArgumentException("invalid");
    } catch (IllegalArgumentException ex) {
        return "recovered";
    } finally {
        return "overridden";
    }
}
```

The caller receives `"overridden"`, not `"recovered"`. `finally` is executed when the `catch` handler prepares to return, and the final `return` replaces the handler's value.

If `finally` had no `return`/`throw` causing abrupt completion, `"recovered"` would be preserved.

## 4. `return` in `finally` Can Swallow Exceptions Completely

Example:

```java
static int dangerouslySilent() {
    try {
        throw new IllegalStateException("database write failed");
    } finally {
        return 0;
    }
}
```

This is an illustrative method. **The result is `0`**; the caller does not receive `IllegalStateException`.

What happens:

1. The operation in `try` throws `IllegalStateException`.
2. Java prepares to propagate the exception to the caller.
3. `finally` runs and encounters `return 0;`.
4. The new `return` replaces the `throw` completion. The pending exception is discarded.

This is a **dangerous anti-pattern**: the method can report a normal value, or even be interpreted as succeeding, when the main operation actually failed.

If the caller uses the value `0` as the number of processed records or a result code, the database write failure can be completely hidden. Upper-layer mechanisms such as retries, exception-based transaction rollbacks, error logging, or monitoring alerts may never receive the signal they need.

**Do not use `return` in `finally` to provide a default value when `try` fails.** If you want a fallback, place the logic in an appropriate `catch` block, verify that recovery is valid, and then return a meaningful result.

## 5. `throw` in `finally` Overrides a Pending Return Value

```java
static int resultLost() {
    try {
        return 42;
    } finally {
        throw new IllegalStateException("cleanup failed");
    }
}
```

Here, the caller **does not receive `42`**. Instead, it receives `IllegalStateException("cleanup failed")`.

This can happen even when the main processing succeeds: a resource-release operation failing in `finally` causes the entire call to terminate with an exception. Sometimes that is a valid policy because closing or flushing final data failed, but it must be an intentional decision. Never assume that having a `return` in `try` guarantees the method will return normally.

Another point: **the return expression has already been evaluated before `finally` runs**, yet the result can still fail to reach the caller if `finally` throws a new exception.

## 6. `throw` in `finally` Masks a Previous Exception

```java
static void originalErrorLost() {
    try {
        throw new IllegalArgumentException("invalid request");
    } finally {
        throw new IllegalStateException("cleanup failed");
    }
}
```

The exception the caller receives is **`IllegalStateException("cleanup failed")`**. `IllegalArgumentException("invalid request")` does not automatically appear in `getCause()` or `getSuppressed()` of the new exception.

Distinguish between:

- **Primary operation exception:** thrown while processing the request, such as invalid input data.
- **Cleanup exception:** thrown while calling `close()`, logging, releasing resources, or performing another cleanup step.
- **Exception observed by the caller:** with a standard `finally` that throws a new error, this is usually the **cleanup exception**, because it replaces the primary failure.

When inspecting the stack trace, an investigator may see only the cleanup location and mistakenly believe cleanup was the initial failure. This is very costly in systems with multiple layers of `try-catch-finally`.

### `finally` Does Not Automatically Preserve `cause`

Suppose:

```java
try {
    throw new IllegalArgumentException("original");
} finally {
    throw new IllegalStateException("replacement");
}
```

There is no rule that automatically attaches `IllegalArgumentException` to `IllegalStateException`'s `getCause()`. To preserve the causal relationship, the code must **explicitly** retain the object or use a construct with the appropriate mechanism, such as `try-with-resources`.

This differs from a developer explicitly writing:

```java
throw new IllegalStateException("higher-level failure", original);
```

In the second statement, `original` is a `Throwable` variable validly saved in the current scope. It is the constructor accepting `cause` that creates the causal relationship, not the fact that the statement is written inside `finally`.

## 7. Complete Java 17+ Example: Four Ways to Override Results

Save the following program as **`FinallyOverrideDemo.java`**. All messages and error types are controlled, so stdout is completely predictable.

```java
public class FinallyOverrideDemo {

    static int returnOverReturn() {
        try {
            System.out.println("try A: return 10");
            return 10;
        } finally {
            System.out.println("finally A: return 20");
            return 20;
        }
    }

    static int returnOverThrow() {
        try {
            System.out.println("try B: throw original");
            throw new IllegalStateException("original");
        } finally {
            System.out.println("finally B: return 30");
            return 30;
        }
    }

    static int throwOverReturn() {
        try {
            System.out.println("try C: return 40");
            return 40;
        } finally {
            System.out.println("finally C: throw cleanup");
            throw new IllegalArgumentException("cleanup");
        }
    }

    static void throwOverThrow() {
        try {
            System.out.println("try D: throw original");
            throw new IllegalStateException("original");
        } finally {
            System.out.println("finally D: throw replacement");
            throw new IllegalArgumentException("replacement");
        }
    }

    static int safeFinally() {
        int value = 7;
        try {
            System.out.println("try E: return 7");
            return value;
        } finally {
            value = 8;
            System.out.println("finally E: local value is " + value);
        }
    }

    public static void main(String[] args) {
        System.out.println("A result=" + returnOverReturn());
        System.out.println("B result=" + returnOverThrow());

        try {
            System.out.println("C result=" + throwOverReturn());
        } catch (IllegalArgumentException ex) {
            System.out.println("C caught=" + ex.getMessage());
        }

        try {
            throwOverThrow();
        } catch (IllegalArgumentException ex) {
            System.out.println("D caught=" + ex.getMessage());
            System.out.println("D cause=" + ex.getCause());
            System.out.println(
                    "D suppressed=" + ex.getSuppressed().length);
        }

        System.out.println("E result=" + safeFinally());
    }
}
```

Compile and run with **JDK 17 or later**:

```bash
javac -encoding UTF-8 FinallyOverrideDemo.java
java FinallyOverrideDemo
```

**Exact stdout:**

```text
try A: return 10
finally A: return 20
A result=20
try B: throw original
finally B: return 30
B result=30
try C: return 40
finally C: throw cleanup
C caught=cleanup
try D: throw original
finally D: throw replacement
D caught=replacement
D cause=null
D suppressed=0
try E: return 7
finally E: local value is 8
E result=7
```

### Explanation of Each Case

**A — `return` overrides `return`:** `try` intends to return `10`, `finally` returns `20`. The caller sees `20`.

**B — `return` swallows `throw`:** `IllegalStateException("original")` in `try` is no longer propagated; `finally` returns `30`. The caller receives `30` as a normal result.

**C — `throw` overrides `return`:** `try` prepares to return `40`, but `finally` throws `IllegalArgumentException("cleanup")`. The call does not return `40`, so `"C result=..."` is not printed; the outer handler prints `C caught=cleanup`.

**D — `throw` overrides `throw`:** `try` throws `IllegalStateException("original")`, while `finally` throws `IllegalArgumentException("replacement")`. The caller catches the replacement error; `getCause()` is `null` and `getSuppressed()` is empty, proving that the original cause **is not automatically attached by Java** in this `try-finally` pattern.

**E — `finally` completes normally:** `try` evaluates `value` to `7` before returning, and `finally` only assigns the local variable to `8` and prints. Because `finally` does not `return` or `throw`, the result `7` is preserved.

This example intentionally demonstrates patterns **not to use in real applications** (A–D) to verify Java's rules. Learn the behavior, and **do not copy unconditional `return` or `throw` statements in `finally`** into production code.

## 8. Evaluation Order of `return` Expressions Before `finally`

A subtle detail: Java **evaluates the `return` expression first**, then executes `finally`, and only then completes returning the value if `finally` does not change the completion reason.

Example with a primitive type:

```java
static int primitiveSnapshot() {
    int n = 5;
    try {
        return n;
    } finally {
        n = 9;
    }
}
```

The result is **`5`**. Not `9`, because the value of the expression `return n` was already captured before reassigning `n` in `finally`.

### With Mutable Objects, the Caller Can See the Updated State

```java
static StringBuilder referenceResult() {
    StringBuilder builder = new StringBuilder("A");
    try {
        return builder;
    } finally {
        builder.append("B");
    }
}
```

The caller receives a reference to the `StringBuilder` object **already containing `"AB"`**. Because the expression `return builder` saves the **reference**, mutating the object's state before the call finishes is still visible through that reference.

This does not contradict the primitive-type rule:

- For `int`, the value `5` was already computed and is not retroactively changed by the local variable `n`.
- For `StringBuilder`, the reference was already computed, but the object that the reference points to can still be modified in `finally`.
- If `finally` only **reassigns the `builder` variable to another object**, the pending return reference still points to the object evaluated in the `return` expression.
- If `finally` throws an error or executes another `return`, the caller does not receive the initial result, even though the expression was already evaluated.

### What If the `return` Expression Itself Throws an Exception?

```java
static int expressionFails() {
    try {
        return Integer.parseInt("not-a-number");
    } finally {
        System.out.println("cleanup");
    }
}
```

Here, `Integer.parseInt` throws `NumberFormatException` **before there is an `int` value to return**. `finally` prints `cleanup`, and then the original exception continues propagating if `finally` completes normally. If `finally` instead executes `return 0;`, `NumberFormatException` can be swallowed just like in case B.

Thus, it is important to distinguish "having evaluated a value to return" from "a `return` expression failing during evaluation": both are exit paths that pass through `finally`.

## 9. `catch` and `finally`: Can a Sibling Handler Catch an Error Thrown by `finally`?

**No.** The `catch` clauses of a `try-catch-finally` construct handle exceptions exiting from the **`try` body**. They do not go back to catch a new exception thrown from that same construct's `finally` block.

Example:

```java
try {
    System.out.println("work completed");
} catch (IllegalStateException ex) {
    System.out.println("caught by sibling");
} finally {
    throw new IllegalStateException("cleanup failed");
}
```

The code above prints `work completed` and then throws `IllegalStateException` out of the entire construct. The sibling `catch (IllegalStateException)` clause **does not run** for the error thrown from `finally`.

If you want to handle cleanup errors in a separate scope, you can wrap the construct in an **outer** `try-catch`:

```java
try {
    try {
        System.out.println("work completed");
    } finally {
        throw new IllegalStateException("cleanup failed");
    }
} catch (IllegalStateException ex) {
    System.out.println("outer caught: " + ex.getMessage());
}
```

Output:

```text
work completed
outer caught: cleanup failed
```

This example explains **exception-catching boundaries**; it does not encourage intentionally throwing cleanup errors just for an outer layer to catch. If cleanup can fail, an appropriate resource-management policy is needed.

## 10. Nested `finally` Blocks: Completion Reasons Can Be Replaced Multiple Times

With nested `try-finally` blocks, each `finally` block has the opportunity to keep or replace the completion reason it receives.

```java
static int nestedReturns() {
    try {
        try {
            return 1;
        } finally {
            return 2;
        }
    } finally {
        return 3;
    }
}
```

The final result is **`3`**:

1. The inner `try` prepares to return `1`.
2. The inner `finally` replaces it with `return 2`.
3. The entire inner construct is now preparing to return `2`.
4. The outer `finally` replaces it again with `return 3`.

This is an example **intentionally demonstrating bad behavior**. The more `finally` blocks have abnormal control flow, the harder it becomes to know what the final completion reason is. The same rules apply when one or more `finally` blocks throw exceptions.

In real-world code, let `finally` perform **bounded cleanup**, while decisions about return values or business errors belong in `try`, `catch`, or the appropriate orchestration layer.

## 11. Why `return`/`throw` in `finally` Distorts Logs and Monitoring

Suppose you have a job:

```java
int processJob() {
    try {
        writeDatabase();
        return 1;
    } finally {
        return 0;
    }
}
```

This is an **anti-pattern snippet**, since `writeDatabase()` is just a hypothetical method. If the database reports an error via an unchecked exception, `finally` still returns `0`; the orchestrating system may treat that as a normal result rather than a failure that needs retrying.

Real-world consequences include:

- **Loss of root cause:** centralized logging does not receive the primary exception, or sees only a cleanup error at an outer layer.
- **Misclassification of status:** the caller receives a normal value even though the main operation did not complete.
- **Missed retries or alerts:** exception-driven retry mechanisms do not trigger if the error is swallowed by `return`.
- **Risk of inconsistent data:** partial side effects may have occurred before the exception; returning a false success does not guarantee rollback.
- **Misleading stack traces:** when `finally` throws a new exception without preserving the cause, the cleanup site can become the only error trace the caller sees.

That is why many lint and static-analysis rules warn against `return` in `finally`. This warning has a sound semantic basis, not just formatting preference.

## 12. How to Fix It: Let `finally` Complete Normally

A basic design:

```java
static int compute() {
    try {
        int answer = 42;
        return answer;
    } finally {
        System.out.println("compute: finished");
    }
}
```

The caller receives `42`, because `finally` only prints a message and then completes normally. If `try` throws an exception, the call still throws that exception, unless the logging statement in `finally` itself throws a new exception.

A construct with `finally` is useful when a task must always be attempted at the end of a scope, such as updating metrics or releasing state. However, **never assume every cleanup call is guaranteed not to throw**. If cleanup can fail, the handling policy must be designed explicitly.

### Do Not Put Fallbacks in `finally`

Faulty code:

```java
static int parseOrDefault(String raw) {
    try {
        return Integer.parseInt(raw);
    } finally {
        return 0;
    }
}
```

This code always returns `0`, even when the string is `"123"`. If `raw` is invalid, `NumberFormatException` is also masked.

Code that expresses the fallback policy more clearly:

```java
static int parseOrDefault(String raw) {
    try {
        return Integer.parseInt(raw);
    } catch (NumberFormatException ex) {
        return 0;
    }
}
```

This is only a valid choice **if the contract genuinely allows defaulting to `0` when the string cannot be parsed**. If `0` cannot distinguish an error from a valid value, use an explicit result type, an optional value, or let the error propagate.

The key point is that the fallback belongs in **a handler for a recoverable error**, not in `finally`, which also runs on the success path.

## 13. If Cleanup Can Fail, Use `try-with-resources` When Appropriate

For resources implementing `AutoCloseable`, Java provides `try-with-resources` to handle resource closing. When **the `try` body throws a primary exception** and `close()` throws another exception, Java stores the closing exception in the **suppressed list** of the primary exception according to `try-with-resources` rules.

That is an important difference from a hand-written `try-finally`, where a cleanup error can replace the primary error.

### Complete Java 17+ Example: Preserving Both Primary and Close Errors

Save the file **`SuppressedCloseDemo.java`**:

```java
public class SuppressedCloseDemo {

    static final class FailingResource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("resource: close");
            throw new IllegalStateException("close failed");
        }
    }

    static void work() {
        try (FailingResource resource = new FailingResource()) {
            System.out.println("body: fails");
            throw new IllegalArgumentException("body failed");
        }
    }

    public static void main(String[] args) {
        try {
            work();
        } catch (IllegalArgumentException ex) {
            System.out.println("primary: " + ex.getMessage());
            System.out.println("suppressed count: "
                    + ex.getSuppressed().length);
            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println("suppressed: "
                        + suppressed.getMessage());
            }
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 SuppressedCloseDemo.java
java SuppressedCloseDemo
```

**Exact stdout:**

```text
body: fails
resource: close
primary: body failed
suppressed count: 1
suppressed: close failed
```

### Why Doesn't the Original Error Disappear This Time?

1. The `try` body throws `IllegalArgumentException("body failed")`.
2. When exiting `try-with-resources`, Java automatically calls `close()` on `FailingResource`.
3. `close()` throws `IllegalStateException("close failed")`.
4. Instead of letting the `close()` error automatically override the error from the `try` body, the `try-with-resources` mechanism adds the closing error to the primary exception's `getSuppressed()`.
5. The caller catches `IllegalArgumentException` and can inspect both the primary cause and the closing error.

Because the example uses unchecked exceptions and a mock resource, the output does not depend on the operating system or real files.

**Important note:** if the `try` body completes **normally** or is about to `return` and `close()` throws an exception, the closing error can still cause the call to terminate with an exception rather than returning a result. `try-with-resources` does not mean all cleanup errors are ignored; it prioritizes **preserving the primary error when both the body and `close()` throw**.

### Suppressed Exceptions Are Not the Same as `cause`

- **`cause`:** represents an exception that caused another exception, typically attached by the developer via a constructor like `new X(message, cause)`.
- **`suppressed`:** a list of secondary errors attached to the primary exception, such as errors when closing resources in `try-with-resources`.
- `getCause()` does not automatically return suppressed closing errors; you need `getSuppressed()`.
- There is no rule that automatically adds a suppressed exception when a developer writes a new `throw` statement in a regular `finally`.

You can explicitly call `Throwable.addSuppressed(...)` in a complex cleanup mechanism, but you must maintain the proper reference to the original exception and avoid mishandling other error cases. In most code managing `AutoCloseable`, **prefer `try-with-resources`** over re-implementing suppression rules yourself.

## 14. Comparing Manual `try-finally` and `try-with-resources`

| Criterion | Manual `try-finally` calling `close()` | `try-with-resources` |
| --- | --- | --- |
| How cleanup happens | Developer calls it manually in `finally` | Java automatically calls `close()` on scope exit |
| Can it lose the primary error when `close()` throws? | **Yes**, if errors are not managed manually | Suppression mechanism preserves the primary error when both body and close fail |
| Closing multiple resources | Write the order and error handling yourself | Resources are closed in **reverse order** of declaration |
| Requires `AutoCloseable`? | Not required, depends on API | Yes; resources must implement `AutoCloseable` |
| Can it be combined with other `catch`/`finally`? | Yes | Yes |
| Does it replace all rollbacks/transactions? | No | No |

However, `try-with-resources` is **not suitable for all cleanup**: some tasks do not own an `AutoCloseable` resource or require special error-handling decisions. When using manual `finally`, keep the block clear and ensure it does not accidentally replace the primary result or error.

## 15. When `finally` Throws an Error: Where Should It Be Handled?

An error thrown from `finally` is not caught by **sibling** `catch` clauses of the same construct. To handle it in the caller:

```java
try {
    operationWithFinally();
} catch (IllegalStateException ex) {
    System.out.println("operation failed: " + ex.getMessage());
}
```

This is an **illustrative skeleton**, assuming `operationWithFinally()` can throw `IllegalStateException`. The outer handler can catch the error currently propagating up, but if the original error was already replaced in an inner `finally`, **the outer handler cannot automatically recover the original exception** simply by adding a `catch`.

The issue must be solved at **the cleanup site**, for example:

- Use `try-with-resources` for eligible resources.
- If cleanup can fail without being allowed to mask business errors, preserve the primary error object and record secondary errors according to a specific policy.
- If a cleanup failure is severe enough that the operation must be considered failed, allow that exception to propagate **intentionally** with the necessary diagnostic information, rather than placing a careless `throw` in `finally`.
- Never silently swallow every `Exception` in cleanup just to avoid masking errors; ignoring an error must be deliberate and documented.

Handling boundaries at outer layers determine the system's response, but **they cannot fully repair error information already lost by lower layers**.

## 16. Exceptions and `return` from `catch` Follow the Same Rule

`finally` does not only accompany a bare `try`. With this structure:

```java
static String recover() {
    try {
        throw new IllegalArgumentException("bad input");
    } catch (IllegalArgumentException ex) {
        return "fallback";
    } finally {
        System.out.println("cleanup");
    }
}
```

The caller receives `"fallback"`; `finally` just prints and completes normally.

If `finally` is changed to:

```java
finally {
    throw new IllegalStateException("cleanup failed");
}
```

then the caller will **receive `IllegalStateException`, not `"fallback"`**. The same happens if `catch` intends to rethrow the exception: another `return` in `finally` can swallow the rethrown error.

The accurate way to read this is: **any pending completion reason from `try` or `catch` can be replaced by a new reason created by `finally`**.

## 17. Is `finally` Always Executed?

Under normal Java control flow, `finally` is executed when exiting `try` or `catch`, including when there is a `return` or an exception. Even so, **do not treat this as an absolute guarantee across all ways a JVM/process can terminate**.

Situations that can prevent `finally` from running as expected:

- `Runtime.getRuntime().halt(...)` terminates the JVM directly.
- `System.exit(...)` initiates JVM shutdown without guaranteeing that `finally` blocks on active threads will run.
- The process is forcibly terminated by the operating system, crashes fatally, or the machine loses power.
- A thread is stuck in an operation that never finishes, so it never exits `try` to reach `finally`.

This does not change the main rule of this lesson: **when `finally` actually runs under normal flow and completes abruptly, it can replace the pending result**.

## 18. `break` and `continue` in `finally` Can Also Alter Control Flow

Besides `return` and `throw`, an abrupt completion reason can also come from `break` or `continue` in a loop.

Valid Java syntax example inside a method body:

```java
for (int i = 0; i < 2; i++) {
    try {
        System.out.println("try " + i);
        if (i == 0) {
            throw new IllegalStateException("failed");
        }
    } finally {
        continue;
    }
}
System.out.println("after loop");
```

**Stdout:**

```text
try 0
try 1
after loop
```

The `continue` in `finally` causes the loop to advance to the next iteration, preventing the `IllegalStateException` on the first iteration from **propagating outward**. This is the same rule — "a new completion reason replaces the old one" — even without using `return` or `throw`.

This snippet is shown to **recognize an anti-pattern**, not to recommend writing `continue` or `break` in `finally`. With loops, these control-flow statements also make behavior hard to read and easily hide errors.

## 19. Checklist for Detecting and Fixing Lost Results in `finally`

When reviewing a method with `try-catch-finally`, check:

1. **Does `finally` contain a `return`?** If so, identify which return value or exception it is replacing. Usually, the return policy should be moved out to `try`/`catch`.
2. **Does `finally` contain a direct `throw`?** Check whether it masks a propagating exception and whether the caller still has a way to trace the primary error.
3. **Can calls inside `finally` throw exceptions?** `close()`, logging, cleanup callbacks, and resource release can all fail depending on the API.
4. **Was `return` in `try` already evaluated before cleanup?** For primitive types, modifying a local variable in `finally` does not change the computed value; for mutable objects, state changes may still be observable.
5. **Is `catch` supposed to return a fallback or rethrow?** Make sure `finally` does not silently override the handler's decision.
6. **Can `try-with-resources` be used?** If the resource implements `AutoCloseable`, this mechanism manages closing and suppressed exceptions better in many scenarios.
7. **Are both primary errors and cleanup errors logged and handled according to policy?** Avoid losing the primary cause, while also not hiding important cleanup failures.
8. **Are there nested `finally` blocks?** Outer `finally` layers can further replace results that an inner construct was preparing to return.
9. **Are there `break` or `continue` statements in `finally`?** They also change the completion reason and can mask exceptions.
10. **Have error paths been tested?** At a minimum, test `return` before `finally`, `throw` before `finally`, failed cleanup, and the scenario where both body and `close()` fail simultaneously.

## 20. Self-Check Exercises

**Exercise A. What value is returned?**

```java
static int f() {
    try {
        return 1;
    } finally {
        return 2;
    }
}
```

**Answer:** `2`. The `return` in `finally` overrides the previous `return`.

**Exercise B. Does the error reach the caller?**

```java
static String f() {
    try {
        throw new IllegalStateException("fail");
    } finally {
        return "OK";
    }
}
```

**Answer:** the caller receives `"OK"`, and the exception is swallowed. This is a seriously misleading example if `"OK"` is interpreted as success.

**Exercise C. Which error does the caller receive?**

```java
static void f() {
    try {
        throw new IllegalArgumentException("original");
    } finally {
        throw new IllegalStateException("new");
    }
}
```

**Answer:** `IllegalStateException("new")`. Unless the code intentionally attaches `cause`/suppressed, the `original` error does not automatically appear in the new exception.

**Exercise D. The variable is modified in `finally`; does the return value change?**

```java
static int f() {
    int x = 3;
    try {
        return x;
    } finally {
        x = 4;
    }
}
```

**Answer:** `3`, because the return expression was evaluated before `finally` and there is no new `return` or `throw`.

**Exercise E. Why can a mutable object be different?**

```java
static StringBuilder f() {
    StringBuilder b = new StringBuilder("X");
    try {
        return b;
    } finally {
        b.append("Y");
    }
}
```

**Answer:** the returned object contains `"XY"`. The reference was evaluated before `finally`, but the object itself was mutated inside `finally`.

**Exercise F. What happens if both the `try-with-resources` body and `close()` throw errors?**

**Answer:** under the `try-with-resources` mechanism, the exception from the `try` body is typically the primary error, and the error from `close()` is added to the suppressed list. It can be inspected via `ex.getSuppressed()`; the original error is not lost by default like a new `throw` from a manual `finally`.

**Exercise G. Does a sibling `catch` handler handle an exception from `finally`?**

**No.** You must use an outer-scope handler or handle it directly inside cleanup; a sibling handler in the same construct only handles errors coming from the `try` body it guards.

**Exercise H. Nested `finally` blocks return `2` and then `3`; what is the final result?**

**`3`**, because the `return` in the outer `finally` replaces the pending result from the inner construct.

## Conclusion

Remember a single rule:

**When `finally` completes normally, Java keeps the completion reason from `try`/`catch`. When `finally` completes abruptly with `return` or `throw`, the new reason replaces the previous one.**

The consequences can be **returning the wrong value**, **swallowing the original exception**, or **leaving only a cleanup exception that misleads diagnosis**. Therefore, avoid `return` and unintentional `throw` operations in `finally`; keep result decisions in `try`/`catch`, place cleanup in clear scopes, and prefer `try-with-resources` to manage `AutoCloseable` resources along with suppressed closing errors.
