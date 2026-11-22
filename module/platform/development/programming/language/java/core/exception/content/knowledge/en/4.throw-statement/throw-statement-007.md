# Unreachable Execution Paths After `throw` in Java

The `throw` statement **terminates normal execution at the point where it is executed**. Control transfers to the exception lookup and handling mechanism: it may enter a matching `catch`, execute `finally`, or propagate the exception to the caller. Therefore, a statement written **immediately after an unconditional `throw` in the same block** has no valid path reaching it and will be rejected by the Java compiler with an `unreachable statement` error.

However, three statements must be distinguished:

- **`throw` always completes abruptly**, according to the Java Language Specification (JLS) §14.18.
- **Whether a statement is reachable or not** (*reachability*) is a static analysis rule of the compiler, according to JLS §14.22.
- **Whether a line is executed in a specific run** is a dynamic observation, which does not necessarily match the reachability rule completely.

The scope of this article is the effect of `throw` on subsequent statements, how the compiler determines unreachable statements, and where exceptions are caught so that the program continues.

## 1. Why Does `throw` Block the Execution Path Behind It?

Syntax:

```java
throw expression;
```

The expression must produce a reference value assignable to `Throwable` (or `null`, which causes a `NullPointerException` at runtime). When the expression evaluates to an exception object, `throw` throws that object and **completes abruptly** with reason `throw`. If evaluating the expression itself throws another exception, `throw` also completes abruptly for that reason. There is no case where a `throw` statement completes normally to transfer directly to the next statement.

The following example **intentionally does not compile**:

```java
class InvalidAfterThrow {
    static void fail() {
        throw new IllegalStateException("Dừng tại đây");
        // System.out.println("Không tới được"); // If uncommented: compile error.
    }
}
```

If you uncomment the `System.out.println(...)` statement, `javac` rejects that statement as an **unreachable statement**. The commented version itself compiles; the example is meant to illustrate the error point rather than produce runtime output.

Why? Within the same block `{ ... }`, a subsequent statement is only *reachable* if the preceding statement **can complete normally**. `throw` never has this ability, so the next statement does not satisfy the reachability condition.

```text
Method block
    |
    v
throw new IllegalStateException(...)
    |
    +-- completes abruptly --> find catch / unwind stack / finally
    |
    X  No normal control edge to the next line
       System.out.println(...)
```

You cannot "fix" this error by placing `return;` after `throw`: `return` itself is also unreachable. You cannot ask the compiler to ignore a reachability error merely by commenting that it is fallback code.

## 2. `Unreachable statement` Is a Compile-Time Error, Distinct From Runtime Exceptions

Java analyzes reachability at **compile time** based on the structure of statements. It does not need to run the program to determine the path of an unconditional `throw`. For example:

```java
class AnotherInvalidExample {
    static int parse() {
        throw new IllegalArgumentException("Bad input");
        // return 42; // If uncommented, this will be an unreachable statement.
    }
}
```

A method returning `int` does not require adding `return` after `throw`, because the method can terminate via an exception instead of returning a value. The `throw` statement is a valid termination path. You should add a condition so that it only throws in the error case, and returns a value in the valid case.

**Two diagnostics that must not be confused:**

| Symptom | Example | Nature |
| --- | --- | --- |
| `unreachable statement` | There is a statement in the same block immediately after an unconditional `throw`. | Compile-time reachability error. |
| `missing return statement` | An `int` method has a path that falls off the end of the method body without `return` or `throw`. | Check that every path must return a value or terminate abruptly. |
| `unreported exception ... must be caught or declared to be thrown` | Throwing a checked exception without an appropriate `catch` or `throws` declaration. | Checked exception checking, independent of reachability. |
| `NullPointerException` at `throw null;` | The `throw` expression evaluates to `null` at runtime. | Runtime exception; `throw` still completes abruptly. |

Exact compiler error wording and positions may vary across JDK versions. What matters is the cause and how to fix it.

Example of a checked exception (the following snippet is **intentionally invalid**):

```java
import java.io.IOException;

class CheckedExceptionExample {
    static void load() {
        throw new IOException("Read failed"); // Must be caught or declared with throws.
    }
}
```

This snippet does not encounter an "unreachable statement" error, because there is no statement after `throw`. The error lies in the checked exception contract. You can fix the declaration to `static void load() throws IOException` and let the caller be responsible for catching/declaring it; or handle the exception in a `catch` with appropriate context.

## 3. Conditional `throw`: Valid Branches Still Continue

One `if` branch may throw, while another path can still reach the next statement:

```java
static int requirePositive(int value) {
    if (value <= 0) {
        throw new IllegalArgumentException("value phải dương");
    }
    return value * 2;
}
```

This is an illustrative method inside a class. For `value = -1`, the `throw` statement runs and `return` does not. For `value = 5`, the condition is false, the `if` block is skipped, and the method returns `10`. Because there is a valid path, `return value * 2;` is **reachable**.

When both branches cannot complete normally, a statement immediately after `if-else` may be unreachable. Example **that intentionally does not compile if uncommented**:

```java
class InvalidBothBranches {
    static void fail(boolean mode) {
        if (mode) {
            throw new IllegalArgumentException("A");
        } else {
            throw new IllegalStateException("B");
        }
        // System.out.println("after"); // If uncommented: unreachable statement.
    }
}
```

Each branch throws an exception, so there is no normal completion path through `if-else`. When one branch returns a value or uses `throw`, you need to look at the **entire `if` construct**, not just the last statement in one branch.

A common practical pattern is a *guard clause*:

```java
static String normalizeName(String name) {
    if (name == null || name.isBlank()) {
        throw new IllegalArgumentException("Tên không được để trống");
    }
    return name.trim();
}
```

This moves the error path out of the main flow, so the valid-case handling can be read sequentially. Place validation checks **before** using the value to avoid throwing exceptions lacking context (such as `NullPointerException`). This snippet is a method in a class, without a `main` to run standalone.

## 4. Runnable Java 17+ Example: Guard Clause, `throw`, and `catch`

Save the file `ThrowReachabilityDemo.java`:

```java
public class ThrowReachabilityDemo {
    static int parsePositive(String input) {
        final int value;

        try {
            value = Integer.parseInt(input);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("Not a number: " + input, ex);
        }

        if (value <= 0) {
            throw new IllegalArgumentException("Must be positive");
        }
        return value;
    }

    static void runTask(int kind) {
        try {
            if (kind == 0) {
                throw new IllegalStateException("stop");
            }
            System.out.println("try-ok");
        } catch (IllegalStateException ex) {
            System.out.println("caught=" + ex.getMessage());
        } finally {
            System.out.println("finally");
        }
        System.out.println("after-try");
    }

    public static void main(String[] args) {
        System.out.println("positive=" + parsePositive("7"));

        try {
            parsePositive("-2");
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }

        runTask(0);
        runTask(1);
    }
}
```

Compile and run in the directory containing the file:

```bash
javac -encoding UTF-8 ThrowReachabilityDemo.java
java ThrowReachabilityDemo
```

Output:

```text
positive=7
invalid=Must be positive
caught=stop
finally
after-try
try-ok
finally
after-try
```

**Analysis:**

1. `parsePositive("7")` does not throw because the condition `value <= 0` is false; the result `7` is returned normally.
2. `parsePositive("-2")` throws `IllegalArgumentException`. The `return value;` statement **is still reachable at compile time**, though it does not execute in this call. The outer `catch` handles the exception.
3. `runTask(0)` throws inside `try` and transfers to `catch`. The `try-ok` part is skipped, `finally` runs, and then `after-try` runs because the `try-catch-finally` construct completed normally.
4. `runTask(1)` does not throw: `try-ok` is printed, `catch` is skipped, `finally` still runs, and then `after-try` runs.

The **unreachable statement** error is a static concept; the outcome of a single call with specific arguments does not turn a valid statement into a compile error.

## 5. Why Is Code After `try-catch` Still Reachable?

Example:

```java
try {
    throw new IllegalArgumentException("bad");
} catch (IllegalArgumentException ex) {
    System.out.println("handled");
}
System.out.println("after");
```

This is an illustrative snippet placed inside a method body. The normal execution sequence is:

```text
throw "bad"
    |
    v
catch (IllegalArgumentException)
    |  print "handled"
    v
after try-catch
       print "after"
```

The `after` line is **outside** the `try` block containing `throw`. The `catch` catches and handles the abrupt completion reason; because `catch` completes normally, the entire `try-catch` construct can complete normally, making the subsequent statement valid.

Compare the following code (which has an error if uncommented):

```java
try {
    throw new IllegalArgumentException("bad");
    // System.out.println("in try"); // unreachable statement if uncommented
} catch (IllegalArgumentException ex) {
    System.out.println("handled");
}
System.out.println("after"); // reachable
```

The `catch` part does not make a line **inside the same `try` block, immediately after `throw`**, reachable. It only creates a valid continuation path after the `try` block has completed abruptly.

At the same time, `catch` must be type-compatible with the exception. If there is only `catch (NumberFormatException ex)`, it cannot catch a plain `IllegalArgumentException` thrown by the programmer (even though `NumberFormatException` is a subclass of `IllegalArgumentException`). In the example throwing `new IllegalArgumentException(...)`, the object's type is `IllegalArgumentException`, so a clause catching only `NumberFormatException` does not match. The exception path continues propagating outward.

## 6. `finally` Runs, But Does Not Reopen the Path After `throw`

When transferring control out of `try` due to `throw`, Java executes the corresponding `finally` during control transfer, according to the rules of `try-finally` and `try-catch-finally`. However, `finally` **does not go back into the part after `throw` inside the `try` block**.

Runnable program, saved as `FinallyThrowDemo.java`:

```java
public class FinallyThrowDemo {
    static void process() {
        try {
            System.out.println("before throw");
            throw new IllegalStateException("failed");
        } finally {
            System.out.println("cleanup");
        }
    }

    public static void main(String[] args) {
        try {
            process();
        } catch (IllegalStateException ex) {
            System.out.println("caught=" + ex.getMessage());
        }
        System.out.println("after call");
    }
}
```

```bash
javac -encoding UTF-8 FinallyThrowDemo.java
java FinallyThrowDemo
```

Output:

```text
before throw
cleanup
caught=failed
after call
```

Key point to remember: `process()` does not complete normally because the exception escapes; however, the call is inside `main`'s `try-catch`, and `main` can continue at `after call` after catching the error. There is no reason to allow adding a normal statement immediately after `throw` in the same `try` block.

**Warning about `finally`:** If `finally` itself executes `throw` or `return`, its new completion reason can **replace** the exception currently propagating. Avoid `return` in `finally` and do not lose the original exception during cleanup. For `AutoCloseable` resources, `try-with-resources` is designed to preserve errors thrown when closing resources in the `suppressed` list in appropriate situations.

## 7. Difference Between an Explicit `throw` and a Call That Always Throws

Consider two versions:

```java
static void alwaysFails() {
    throw new IllegalStateException("failed");
}

static void caller() {
    alwaysFails();
    System.out.println("after call"); // Java still considers this reachable.
}
```

Both methods are code snippets placed in a class. Even though `alwaysFails()` never returns normally when executed as written, the Java compiler **does not infer across methods** that the call `alwaysFails()` will definitely throw. A normal method invocation expression statement is considered able to complete normally under the reachability rules of JLS §14.22. Therefore, the `after call` line is accepted at compile time, even though it will not execute in this scenario.

Compare:

```java
static void directThrow() {
    throw new IllegalStateException("failed");
    // System.out.println("after throw"); // If uncommented, does not compile.
}
```

In `directThrow()`, the compiler sees `throw` directly before the next statement. This demonstrates that **"cannot execute in practice" is different from "unreachable according to the specification"**.

Similarly, the compiler does not deeply analyze every variable value to prove whether a path can or cannot occur. Use explicit control structures instead of relying on the assumption that the compiler will infer the business meaning of a method named `alwaysFails` or a local constant.

## 8. Special Exception: `if (true)` and Java's Reachability Rules

The `if` rule has a special case under JLS §14.22. Even if the condition is the constant `true` and the branch contains an unconditional `throw`, a statement **after the entire `if` without an `else`** can still be considered reachable. This example compiles:

```java
class IfReachabilityExample {
    static void example() {
        if (true) {
            throw new IllegalStateException("always");
        }
        System.out.println("reachable to compiler");
    }
}
```

At runtime, calling `example()` always raises the exception, so the print line does not execute. However, the JLS intentionally has a special rule for `if` to support "conditional compilation"-style idioms. Therefore, **do not conclude that `javac` must report unreachable for every piece of code that humans can prove will not run**.

Conversely, **inside the same block of the `if` branch**, placing a statement after an unconditional `throw` is still unreachable:

```java
class IfInvalidExample {
    static void example() {
        if (true) {
            throw new IllegalStateException("always");
            // System.out.println("never"); // If uncommented: unreachable.
        }
    }
}
```

Whereas `if-else` is a different construct: for the entire `if-else` to be able to complete normally, at least one branch must be able to complete normally. If both branches contain an unconditional `throw`, code after the construct is rejected as unreachable.

**Note:** This special rule does not allow placing a statement directly after `throw` in the same block; it pertains to normal completion modeled for **the entire `if` statement**.

## 9. `switch`, `case`, and Branches After `throw`

Another `case` is not necessarily blocked by a `throw` statement in a preceding `case`. `switch` has multiple entry points by `case` labels.

Valid example:

```java
static void choose(int code) {
    switch (code) {
        case 1:
            throw new IllegalArgumentException("bad code");
        case 2:
            System.out.println("code=2");
            break;
        default:
            System.out.println("other");
    }
    System.out.println("switch done");
}
```

This is an illustrative method, not a standalone file. For `code = 2`, the program enters `case 2` directly; it does not need to pass through `case 1` and the `throw` statement there. For `code = 1`, the exception is thrown. For values other than `1` and `2`, `default` runs. The statement after `switch` is reachable because there are paths that complete normally.

In a `switch` expression, a `throw` branch can also be valid because it represents an error case while other branches return a value:

```java
static int points(int level) {
    return switch (level) {
        case 1 -> 10;
        case 2 -> 20;
        default -> throw new IllegalArgumentException("unknown level");
    };
}
```

The `default` branch throws an exception, while the other two branches allow the `switch` expression to yield a normal result. There is no need to write a "dummy value" expression after `throw`. The code uses `switch` expression syntax stabilized in Java 17.

## 10. Loops and Unreachable Statements: Related, Not Identical

The JLS also has rules for loops that cannot complete normally, such as `while (true)` without a matching `break`:

```java
class InvalidInfiniteLoop {
    static void loop() {
        while (true) {
            System.out.println("running");
        }
        // System.out.println("after loop"); // If uncommented: unreachable.
    }
}
```

This is an example of reachability **without needing `throw`**. It shows that unreachable errors come from the language's general control-flow model. If the loop has a reachable `break` exiting it, the statement after the loop can be reachable.

A notable distinction:

```java
static void conditionalLoop(boolean keepRunning) {
    while (keepRunning) {
        if (Thread.currentThread().isInterrupted()) {
            break;
        }
    }
    System.out.println("after loop");
}
```

This method only illustrates control flow and **should not be used as a busy-wait spin loop in production code**. When the condition `keepRunning` is a variable (not the constant `true`), in terms of reachability it is possible to exit the loop to reach `after loop`. Reachability rules do not predict whether a loop definitely terminates in a specific run.

When compared with `throw`: an unconditional `throw` statement cannot complete normally in any case, whereas loop or `if` constructs must be evaluated according to their own rules.

## 11. Common Mistakes and How to Fix Them

| Mistake | Why It Is Wrong | Appropriate Fix |
| --- | --- | --- |
| Placing `System.out.println` or `return` after an unconditional `throw` in the same block. | The preceding statement cannot complete normally, so the next statement is unreachable. | Remove the dead line, or move the action that needs to run **before `throw`**. |
| Writing `throw ...; return defaultValue;` to ensure a return value. | `throw` is already a method termination path; `return` after it is unreachable. | Use `throw` for the error path and `return` separately for the valid path. |
| Assuming `catch` will run and then return to the line immediately after `throw`. | `catch` handles the error and continues after the appropriate `try` construct, not back at the throw site. | Move code that should run after handling to **after `try-catch`**. |
| Confusing a checked exception error with `unreachable statement`. | These are two independent checks. | For checked exceptions, `catch` or declare `throws` with the appropriate type. |
| Confusing an "always throws" call with a direct `throw`. | The compiler does not infer across methods in that way. | Express checks and error branches at the appropriate place; do not expect `javac` to perform whole-program analysis. |
| Interpreting `if (true) { throw ... }` as code that must cause unreachable outside the `if`. | `if` has a special reachability rule. | Apply the JLS rule accurately for the enclosing construct. |
| Putting `return` in `finally` to "clean up". | `return` in `finally` can mask the original exception. | Only put necessary cleanup work in `finally`; avoid replacing the propagating error reason. |

A small change is often clearer:

**Before (invalid if uncommented):**

```java
static String requireName(String name) {
    throw new IllegalArgumentException("invalid");
    // return name.trim(); // unreachable
}
```

**After (valid, with two paths):**

```java
static String requireName(String name) {
    if (name == null || name.isBlank()) {
        throw new IllegalArgumentException("invalid");
    }
    return name.trim();
}
```

With the condition, `return name.trim();` can execute when the input is valid; if the input is invalid, the method throws an exception and does not attempt to return a value.

## 12. How to Check Control Flow Yourself

For a piece of code containing `throw`, trace in order:

1. **Identify the level under consideration:** directly in a block, an entire `if-else`, a `case` of a `switch`, a loop, `try-catch-finally`, or a method call.
2. **Ask whether the preceding statement can complete normally:** if it is a direct `throw`, the answer is always **no**.
3. **Check whether an enclosing construct handles the abrupt reason:** a matching `catch` branch, `finally`, `switch`, and separate control paths are not the same kind of handling.
4. **Apply reachability according to the JLS:** do not infer a compile error merely from the fact that a line will not run with the current input.
5. **Check checked exceptions separately:** after concluding about control flow, still check whether the method needs `throws` or `catch`.

Try predicting the output of the following code when placed in a method:

```java
int value = 3;
try {
    if (value > 0) {
        throw new IllegalArgumentException("positive");
    }
    System.out.println("inside try");
} catch (IllegalArgumentException ex) {
    System.out.println("handled: " + ex.getMessage());
}
System.out.println("outside");
```

Output:

```text
handled: positive
outside
```

The `inside try` line is **reachable under static analysis** because the condition depends on an expression using a variable, even though it does not run in this execution. The exception is handled by `catch`, so the `outside` line runs. If you move the `inside try` line immediately after `throw` **inside the same sub-block of the `if` branch**, the new statement will be unreachable at compile time.

## 13. Quick Self-Check

**Question 1.** After an unconditional `throw new RuntimeException();`, can you place `return 0;` in the same block to avoid a missing `return` error?  
**No.** `throw` already ends the execution path and the `return` after it is unreachable.

**Question 2.** Can a statement outside `try-catch` run after a `throw` inside `try`?  
**Yes.** If a matching `catch` handles the error and the `try-catch` construct completes normally, flow continues at the statement after it.

**Question 3.** If `throw` is inside an `if` branch, is the statement after `if` always unreachable?  
**No.** You must consider the `if` construct and its special reachability rule.

**Question 4.** Can you place `case 2:` after `case 1: throw ...;` in a `switch` statement?  
**Yes.** `case 2` is another entry point of the `switch` and can be reachable.

**Question 5.** If you call a method whose body only contains `throw`, will the compiler report an unreachable error for the line after the call?  
**Not for that reason alone.** Java does not perform cross-method analysis to infer that a call always fails.

**Question 6.** Is `throw null;` considered to complete normally?  
**No.** At runtime, Java creates and throws a `NullPointerException`, so the statement still completes abruptly.

## Specification References

- [Java Language Specification 21 — §14.18 The `throw` Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.18).
- [Java Language Specification 21 — §14.22 Unreachable Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.22).
- [Java Language Specification 21 — §14.20 `try` Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20).
- [Java Language Specification 21 — §11.2 Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.2).

**Key takeaway:** `throw` always completes abruptly. A statement placed directly after an unconditional `throw` in the same block is unreachable, but a matching `catch` or another control branch can provide a valid continuation path **at the enclosing construct level**. Evaluate reachability according to Java's rules, not merely by predicting a single run.