# Normal Completion and Abrupt Completion in Java

When executing a statement, Java does not only care about the computed result, but also about **how the statement finishes**. The Java Language Specification (JLS) calls these two possibilities *normal completion* and *abrupt completion*. This concept explains precisely why `return` exits a method, `break` exits a loop, `continue` skips the remainder of a loop iteration, `yield` provides a value to a `switch` expression, exceptions alter the execution path, and `finally` still executes during a transfer of control.

Key point: **"abrupt" does not mean "an exception occurred"**. A `return 10;` statement also completes abruptly in the terminology of the language, even though the method may return a value completely successfully.

## 1. What are the two kinds of completion?

### Normal completion

A statement completes normally when it finishes executing all the steps specified for its normal execution path, without any abrupt transfer of control. Control normally continues to the next statement in the same block.

```java
int count = 0;
count++;
System.out.println(count); // Prints 1
```

The three statements above complete normally one after another if no exception is thrown. This snippet only illustrates statements inside a method body; it is not a standalone program. A block `{ ... }` also completes normally if all statements actually executed within the block complete in a way that allows the block to finish normally.

### Abrupt completion

A statement completes abruptly when it does not finish the normal execution flow because **a reason for transferring control** occurs. That reason propagates through enclosing statements or blocks until it reaches a construct that handles it; at that point, the outer construct may continue to complete normally.

JLS §14.1 classifies eight kinds of reasons:

| Reason | Explanation |
| --- | --- |
| `break;` | Transfers control out of the innermost enclosing `switch` statement or loop. |
| `break label;` | Exits the matching labeled statement. |
| `continue;` | Advances to the next iteration of the innermost enclosing loop. |
| `continue label;` | Advances to the next iteration of the matching labeled loop. |
| `return;` | Completes abruptly with `return;`, returning control from a matching `void` method, constructor, or lambda body; returns no value. |
| `return value;` | Returns a value from a method/lambda with a matching return type. |
| `throw exception;` | Throws an exception object, including exceptions raised by the JVM during expression evaluation. |
| `yield value;` | Transfers a value from a `switch` expression block to the entire `switch` expression. |

**Syntax note:** The two forms of `break`, the two forms of `continue`, and the two forms of `return` are distinct reasons according to the JLS; `throw` and `yield` each have one corresponding reason form. The label of `continue label` must be attached to an enclosing loop; the label of `break label` can be attached to a matching enclosing statement. You cannot arbitrarily use them outside valid constructs.

In the case of `throw`, a statement may throw explicitly, or an expression such as `10 / zero` may cause an `ArithmeticException`. When evaluating **expressions**, according to the JLS, abrupt completion occurs only because an exception is thrown; `break`, `continue`, `return`, and `yield` are **statement** mechanisms.

## 2. Propagation rules: from inner statements to enclosing constructs

Consider the typical flow:

```text
Start of block
    │
    ▼
Statement A ── normal completion ──► Statement B ──► Statement C
                                          │
                                          └── abrupt completion
                                                    │
                                                    ▼
                                    Find construct handling the reason
                                         │                      │
                                         ▼                      ▼
                                      Handled            Continues propagating
                                         │                      │
                                         ▼                      ▼
                                   May execute            May exit the
                                  next part              current scope
```

If an expression used inside a statement throws an exception, the enclosing statement also completes abruptly for the same reason, unless a specific rule handles the exception. Subsequent steps that belong to the normal execution path are skipped.

```java
System.out.println("Trước");
int value = Integer.parseInt("abc");
System.out.println("Sau");
```

Suppose this snippet is inside a method with an exception-handling call path: the first line prints `Trước`; `parseInt` throws `NumberFormatException`, so the assignment statement and the rest of the block do not complete normally. The line printing `Sau` **is not executed on that path**, unless the exception is caught in a construct that can return control after an appropriate `try` block. Java does not automatically jump back to the failing site to resume midway through an expression.

However, **each structural level must be examined separately**. A `break` statement causes the loop body to complete abruptly, but the loop itself can **handle `break` and then complete normally**. Similarly, a `return` statement completes abruptly, but the outer method call can evaluate normally and receive the return value. This is a very common source of confusion when reading JLS terminology.

## 3. `break`, `continue`, and `yield`: abrupt inside, normal outside

For `for` or `while`:

- `break` exits the loop that receives the `break` reason; the statement after the loop can continue executing.
- `continue` ends the current iteration; the loop proceeds to the update/condition part according to the rules of that loop kind.
- An **uncaught** exception is not automatically handled by a regular loop; it continues propagating outward.
- `yield` is used to produce a value from a `switch` expression block. The `yield` statement completes abruptly, but the `switch` expression receives the value and can complete normally. `yield` is not equivalent to `return` from a method.

Example:

```java
int sum = 0;
for (int i = 0; i < 5; i++) {
    if (i == 1) continue;
    if (i == 3) break;
    sum += i;
}
System.out.println(sum); // Prints 2: sums i=0 and i=2
```

The `continue` and `break` steps are part of the expected control flow. They do not create a `Throwable` and do not trigger `catch`.

In a `switch` expression:

```java
int level = 2;
int points = switch (level) {
    case 1 -> 10;
    default -> {
        yield 20;
    }
};
System.out.println(points); // Prints 20
```

The `yield 20;` statement terminates abruptly at the statement level, while the outer `switch` expression completes normally with the value `20`. The arrow `case 1 -> 10` also supplies a value without requiring the `yield` keyword. These two examples are code snippets placed inside a method, not standalone Java files.

## 4. `return` and `throw`: similar in leaving the execution path, different in cause

`return` passes a result back to the caller and ends the current method execution in the specified manner. `throw` triggers a search for a compatible `catch` in enclosing blocks, or propagates the exception out of the call if unhandled.

| Situation | Inner statement | Outcome at the outer level |
| --- | --- | --- |
| `return 5;` in an `int` method | Completes abruptly with the reason of returning value 5. | The method call expression can receive 5 and complete normally. |
| `throw new IllegalArgumentException(...)` | Completes abruptly with the reason of throwing an exception. | If there is no matching `catch`, the call also completes abruptly. |
| `throw ...` inside `try` handled by `catch`, then `catch` finishes normally | The `try` block first completes abruptly. | The entire `try-catch` construct can complete normally. |
| `return` inside `try` with `finally` | `return` remains the abrupt completion reason of the `try` block. | `finally` runs before the method actually transfers control outward, if execution conditions allow. |

One distinction to keep in mind: **finishing a method call** and **completing a `return` statement** are not at the same level of analysis. The `return` statement has an *abrupt completion* reason, yet the call can yield a normal result for the caller's expression.

## 5. Java 17+ program: observing multiple completion kinds

Save the following content as `FlowCompletionDemo.java`:

```java
public class FlowCompletionDemo {
    static void normalBlock() {
        int count = 0;
        {
            count++;
        }
        System.out.println("normal=" + count);
    }

    static int returnWithFinally() {
        try {
            System.out.println("in try");
            return 10;
        } finally {
            System.out.println("in finally");
        }
    }

    static void catchAndContinue() {
        try {
            throw new IllegalArgumentException("bad");
        } catch (IllegalArgumentException ex) {
            System.out.println("caught=" + ex.getMessage());
        }
        System.out.println("after catch");
    }

    static void loopAndYield() {
        int sum = 0;
        for (int i = 0; i < 5; i++) {
            if (i == 1) continue;
            if (i == 3) break;
            sum += i;
        }

        int level = 2;
        int points = switch (level) {
            case 1 -> 10;
            default -> {
                yield 20;
            }
        };
        System.out.println("loop=" + sum + ", switch=" + points);
    }

    public static void main(String[] args) {
        normalBlock();
        System.out.println("method result=" + returnWithFinally());
        catchAndContinue();
        loopAndYield();
    }
}
```

Compile and run from the directory containing the file:

```bash
javac -encoding UTF-8 FlowCompletionDemo.java
java FlowCompletionDemo
```

Exact output:

```text
normal=1
in try
in finally
method result=10
caught=bad
after catch
loop=2, switch=20
```

Execution path explanation:

1. The nested block in `normalBlock` finishes normally, so the next print statement executes.
2. `return 10` causes the `try` block to finish abruptly with a `return` reason. Java still runs `finally`, and then the value `10` is returned to the outer call.
3. `throw` causes the `try` block of `catchAndContinue` to complete abruptly; `catch (IllegalArgumentException)` handles the exception and completes normally, so the `after catch` line still runs.
4. `continue` skips the `i=1` iteration; `break` stops the loop at `i=3`. The sum is `0 + 2 = 2`. `yield 20` fulfills its role of providing a value for the `switch` expression.

No exception escapes `main` in this example, even though several inner statements completed abruptly.

## 6. How does `try-catch-finally` determine completion?

### `try-catch`

For a `try-catch` without `finally`, Java executes the `try` block first:

- If the `try` block completes normally, no `catch` needs to be entered; the `try-catch` construct completes normally.
- If the `try` block throws an exception, Java checks the `catch` clauses in declaration order to select the first one compatible with the actual exception type.
- If the selected `catch` clause completes normally, the `try-catch` construct also completes normally.
- If no `catch` matches, the exception continues propagating.
- If `catch` itself produces a new abrupt completion reason, the outer construct receives that new reason.

`catch` only handles compatible `throw` reasons; it **does not catch `return`, `break`, `continue`, or `yield`**.

### `try-finally` and `try-catch-finally`

After the `try` part (and `catch` if selected) finishes, Java executes `finally` before completing the transfer of control for the pending reason. This yields four core possibilities:

| Completion of the part before `finally` | Completion of `finally` | Completion of the entire construct |
| --- | --- | --- |
| Normal | Normal | Normal |
| Abrupt with reason R | Normal | Abrupt with R (continues the previous reason) |
| Normal | Abrupt with reason S | Abrupt with S |
| Abrupt with reason R | Abrupt with reason S | Abrupt with S; R is replaced |

Important consequence: a `return` or `throw` inside `finally` can **overwrite the return value or mask the original exception**. That is why `finally` should be used for cleanup work while **avoiding `return` in `finally`**. Cleanup logic also needs care when it might throw a new error.

## 7. Java 17+ program: `finally` preserving or replacing results

Save as `FinallyCompletionDemo.java`:

```java
public class FinallyCompletionDemo {
    static int preservedReturn() {
        int local = 1;
        try {
            return local;
        } finally {
            local = 99;
            System.out.println("finally local=" + local);
        }
    }

    static int replacedReturn() {
        try {
            return 1;
        } finally {
            return 2;
        }
    }

    static void maskedException() {
        try {
            try {
                throw new IllegalStateException("original");
            } finally {
                throw new IllegalArgumentException("cleanup");
            }
        } catch (RuntimeException ex) {
            System.out.println("seen=" + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        System.out.println("preserved=" + preservedReturn());
        System.out.println("replaced=" + replacedReturn());
        maskedException();
    }
}
```

```bash
javac -encoding UTF-8 FinallyCompletionDemo.java
java FinallyCompletionDemo
```

Output:

```text
finally local=99
preserved=1
replaced=2
seen=cleanup
```

In `preservedReturn()`, the value of `local` is evaluated to `1` for the `return` statement **before** `finally` runs; changing the local variable to `99` does not change the primitive value already selected to be returned. In `replacedReturn()`, `finally` itself completes abruptly due to `return 2`, so the `1` result from `try` is replaced by `2`.

In `maskedException()`, the inner `try` attempts to throw `IllegalStateException("original")`, but `finally` throws `IllegalArgumentException("cleanup")`. The new `throw` reason **replaces** the original reason; the outer `catch` sees `cleanup`. This pattern is shown to illustrate a design flaw; you should not use `return` or intentionally throw new exceptions in `finally` in business code. The `original` error information also does not automatically become a `cause` or `suppressed` exception in a regular `try-finally` construct.

## 8. `try-with-resources`: completion and exceptions when closing resources

`try-with-resources` also follows completion rules, but includes a mechanism for **closing resources** that implement `AutoCloseable`. Resources are closed in the reverse order of their initialization. If the `try` body throws an exception and the `close()` operation also throws an exception, Java typically keeps the error from the body as the **primary exception** and adds the resource-closing error to the **suppressed** list. This mechanism avoids losing the original error in the way that throwing a new error from `finally` can cause.

Save as `ResourceCompletionDemo.java`:

```java
public class ResourceCompletionDemo {
    static class BrokenResource implements AutoCloseable {
        @Override
        public void close() {
            throw new IllegalStateException("close failed");
        }
    }

    public static void main(String[] args) {
        try (BrokenResource resource = new BrokenResource()) {
            throw new IllegalArgumentException("work failed");
        } catch (Exception ex) {
            System.out.println("primary=" + ex.getMessage());
            System.out.println("suppressed count=" + ex.getSuppressed().length);
            System.out.println("suppressed=" + ex.getSuppressed()[0].getMessage());
        }
        System.out.println("after try");
    }
}
```

```bash
javac -encoding UTF-8 ResourceCompletionDemo.java
java ResourceCompletionDemo
```

Output:

```text
primary=work failed
suppressed count=1
suppressed=close failed
after try
```

The `try` body completes abruptly because of `throw`; `close()` also fails, but the resource-closing error is kept as an attached suppressed exception. `catch` handles the primary exception and completes normally, so the `after try` line still executes. If the `try` body finishes normally while `close()` fails, the resource-closing error can become the primary exception.

Do not confuse `getSuppressed()` with `getCause()`: `cause` represents the causal chain, whereas `suppressed` records additional exceptions encountered during the same handling process.

## 9. Abrupt completion also affects compilation

Java performs **statement reachability analysis** (*reachability*) and **return-path checking** based on possible control-flow paths. These rules are checked at compile time; they are related to, but not identical to, what is observed in a single runtime execution.

Compile error example:

```java
class InvalidExample {
    static int bad(int number) {
        if (number > 0) {
            return number;
        }
        // Missing return or throw on the number <= 0 path.
    }
}
```

This is an **intentionally non-compiling** example: the method is declared to return `int`, yet there is still a path reaching the end of the method body without returning a value; the compiler reports `missing return statement`. The fix can be adding a `return` on the remaining path or throwing an appropriate exception:

```java
class ValidExample {
    static int positiveOnly(int number) {
        if (number > 0) {
            return number;
        }
        throw new IllegalArgumentException("number must be positive");
    }
}
```

`ValidExample` is valid Java code, though it has no `main` to run standalone. The method has two paths: returning a value or throwing an exception. No valid execution path falls off the end of the method body without a return value.

Unreachable statement example:

```java
class UnreachableExample {
    static void bad() {
        return;
        // System.out.println("never"); // Uncommenting this will cause an unreachable statement error.
    }
}
```

The compiler can detect cases that cannot execute due to an unconditional transfer-of-control statement. However, **do not treat every branch that does not occur in test data as unreachable according to the JLS**: reachability is a static analysis with specific language rules, not a general proof over all runtime conditions.

## 10. How to analyze a practical scenario

When reading code combining loops, exceptions, `try-catch-finally`, and `return`, follow four steps:

1. **Identify the level being examined:** expression, statement, loop body, `try` block, entire `try-catch-finally`, or method call.
2. **Note the reason at the transfer point:** `break`, `continue`, `return`, `throw`, `yield`; for `throw`, also note the exception type and object if needed.
3. **Work from the inside out:** does a loop/`switch` receive and handle `break` or `continue`; does a `switch` expression receive `yield`; does `catch` catch the exception type; does `finally` complete normally or overwrite the reason?
4. **Draw conclusions only at the right level:** an inner block may complete abruptly while an enclosing construct handles it and completes normally. From there, determine which statement runs next and whether the method returns or throws.

Quick mental trace example:

```java
int result;
try {
    result = Integer.parseInt("oops");
} catch (NumberFormatException ex) {
    result = -1;
} finally {
    System.out.println("done");
}
System.out.println(result);
```

This is an illustrative snippet placed inside a method. `parseInt` throws an exception, so the assignment statement in `try` completes abruptly. `catch` catches the matching type, assigns `-1`, and completes normally. `finally` prints `done` and completes normally. The entire `try-catch-finally` completes normally, and then the last line prints `-1`. The output in exact order is:

```text
done
-1
```

## 11. Common misconceptions to avoid

- **"Abrupt = error"**: false. `return`, `break`, `continue`, and `yield` can all be intended behavior.
- **"With `return`, `finally` does not run"**: false in normal Java flow; `finally` runs before completing the transfer of control.
- **"`finally` always preserves the original exception"**: false. A `return` or `throw` from `finally` itself can replace the earlier reason. Use `try-with-resources` for closeable resources to manage suppressed exceptions properly.
- **"`catch (Exception)` handles every abrupt reason"**: false. It only handles exceptions compatible with `Exception`; it does not handle `return`, `break`, `continue`, or `yield`, and does not catch the `Error` branch.
- **"An abrupt `return` statement means the method call also failed"**: false. The caller can receive the value and continue normally.
- **"`finally` is guaranteed to run even if the JVM terminates abruptly"**: incorrect. Situations such as the process being forcefully terminated or the JVM stopping before executing the block do not guarantee `finally` will run.
- **"Catching an error resumes execution right at the failing statement"**: false. Handling takes place in the corresponding `catch`, and afterward control follows the structure of `try-catch`.

## 12. Self-check

1. Is `return 42;` an abrupt completion? **Yes**, with the reason of `return` with a value. Receiving `42` at the method call site can be a normal result at the outer level.
2. Does `break;` inside a loop throw an exception on its own? **No.** It transfers control out of the appropriate loop.
3. When `try` throws an error caught by `catch` and `catch` finishes normally, can the `try-catch` construct finish normally? **Yes.**
4. What happens if `finally` throws a new exception while an earlier exception is pending? **Typically the new reason replaces the old reason** in a regular `try-finally`; the earlier error is not automatically attached.
5. Does `yield` exit a method like `return`? **No.** It transfers a value out of the appropriate `switch` expression.
6. Can an expression complete abruptly because of `continue`? **No.** According to the JLS, an expression completes abruptly only due to a thrown exception.

## References

- [Java Language Specification, Java SE 21 — §14.1 Normal and Abrupt Completion of Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.1).
- [JLS Java SE 21 — §14.20 `try` statement and `finally`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20).
- [JLS Java SE 21 — §14.20.3 `try-with-resources`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.3).
- [JLS Java SE 21 — §15.6 Normal and Abrupt Completion of Evaluation](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.6).

**Takeaway:** The two concepts *normal completion* and *abrupt completion* describe **how an execution unit finishes at a specific level**. Identify the abrupt reason, trace how enclosing constructs handle that reason, and always check `finally` before concluding what is returned, thrown, or executed next.
