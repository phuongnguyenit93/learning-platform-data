# `try-finally` and `try-catch-finally` Syntax in Java

`finally` is the section placed at the end of a `try` statement to execute code when control leaves the `try` block (and `catch` if present) according to Java's rules. The two main ways to write a standard `try` statement with `finally` are **`try-finally`** and **`try-catch-finally`**. The first executes the final block without a `catch` clause in the same construct; the second can both handle certain exceptions and run the final block before completing the statement.

This topic covers the **syntax, execution order, and scope of responsibility** of each block. To understand `finally` properly, two things must be distinguished: `catch` selects how to handle a compatible exception, while `finally` participates in completing the `try` statement regardless of whether the preceding part completed normally or abruptly, as long as the execution flow actually reaches Java's `finally` execution step.

## 1. Two basic syntactic constructs

### 1.1. `try-finally`: perform final work without catching errors locally

```java
try {
    // Operations to perform.
} finally {
    // Work to perform when leaving try.
}
```

This is a **syntax template**, where the two comment blocks represent application code. `try` comes first, `finally` comes after; there is no `catch` in the same construct.

If `try` completes normally and `finally` also completes normally, the program proceeds to the statement following the entire `try-finally`. If `try` throws an exception and `finally` completes normally, that exception **still propagates outward**; there is no `catch` in this construct to handle it. `finally` by itself does not mean the error has been "caught" or "resolved".

### 1.2. `try-catch-finally`: catch compatible errors then perform the final part

```java
try {
    // Operation that may throw an exception.
} catch (IllegalArgumentException ex) {
    // Handle appropriate argument error.
} catch (RuntimeException ex) {
    // Handle some other runtime errors.
} finally {
    // Perform the final step when leaving the construct.
}
```

The `catch` blocks are **optional in count**, but if present they must appear **before `finally`**. There can be one or more `catch` blocks, or no `catch` if `finally` is present. For sibling `catch` blocks, the first branch compatible with the **actual type** of the exception thrown from `try` is selected. Once the selected `catch` finishes executing, `finally` runs according to the statement's rules, and only then does control transfer outward.

In the template above, `IllegalArgumentException extends RuntimeException`, so the `IllegalArgumentException` branch must come before the `RuntimeException` branch. If the order is swapped, the specialized branch is shadowed and the code will not compile.

**The `finally` clause appears only once**, after the entire `catch` list. There is no syntax where `catch` is placed after `finally` in the same `try` statement.

### 1.3. Quick comparison

| Property | `try-finally` | `try-catch-finally` |
| --- | --- | --- |
| `try` | Required | Required |
| `catch` | None in the same construct | One or more branches |
| `finally` | Required | Required |
| Can catch errors in the same construct? | No | Yes, if the exception is compatible |
| If an error from `try` is uncaught and `finally` completes normally | Error continues propagating outward | Error continues propagating outward |
| If all parts finish normally | Continues execution after the construct | Continues execution after the construct |
| If `finally` itself executes `throw` or `return` | Can replace the previous completion reason | Can replace the previous completion reason |

A `try-catch` **without `finally`** is also valid, but that is a different form. Conversely, a standard standalone `try` **without either `catch` or `finally`** is invalid. The exception to this syntactic requirement is **`try-with-resources`**, which has a resource declaration in parentheses and is covered separately near the end.

## 2. Execution order in `try-finally`

For a standard `try-finally`, Java executes the `try` block first. After the `try` block completes, Java executes `finally`, and then determines how the entire statement completes.

```text
Start try-finally
        |
        v
    try block
        |
        +---- Normal completion -----------+
        |                                  |
        +---- return / break / continue ---+---> finally block
        |                                  |          |
        +---- Throws exception ------------+          v
                                            Check how finally completes
                                                       |
                              +------------------------+------------------+
                              |                                           |
                           Normal                                      Abrupt
                              |                                           |
                 Keep previous result/reason                  New reason replaces
```

Example inside a method:

```java
System.out.println("A");
try {
    System.out.println("B");
} finally {
    System.out.println("C");
}
System.out.println("D");
```

Output:

```text
A
B
C
D
```

The `try` block completes normally, then `finally` runs and completes normally. Therefore, `System.out.println("D")` is executed.

If `throw new IllegalStateException("failed");` is added after printing `B` inside `try`, line `C` is still executed in normal Java control flow; however, line `D` does not run on that exception-throwing path unless an **outer** `catch` handles the failure and directs control along another path.

## 3. Execution order in `try-catch-finally`

When `catch` is present, Java performs the handler selection step **before the `finally` completion step**:

1. Execute the `try` block.
2. If `try` completes normally, skip all `catch` blocks and execute `finally`.
3. If `try` throws an exception object, inspect the sibling `catch` blocks in declaration order. Only the **first compatible** branch is executed.
4. If no `catch` matches, the exception remains the pending completion reason, but `finally` is still executed before the exception propagates outward during normal Java processing.
5. If a matching `catch` completes normally, the construct can complete normally after `finally` completes normally.
6. If `catch` completes abruptly due to `throw` or `return`, `finally` is still executed; if `finally` completes normally, the pending reason is preserved.
7. If `finally` itself completes abruptly, **the new reason from `finally`** can replace the previous reason.

```text
                      try
                       |
          +------------+-------------+
          |                          |
     Normal exit             Throws exception
          |                          |
      Skip catch              Find matching catch
          |                     |           |
          |                   Found      Not found
          |                     |           |
          |                 Run catch   Propagate exception
          |                     |           |
          +---------------------+-----------+
                                |
                             finally
                                |
                   Check completion then exit
```

**There is no path that "executes all `catch` blocks and then runs `finally`".** Each primary exception causes at most one `catch` branch of the same `try` statement to be selected. `finally` is not an alternative `catch` branch.

## 4. Java 17+ example: observing both syntaxes

Save the complete file `FinallyFormsDemo.java`:

```java
public class FinallyFormsDemo {
    static void onlyFinally(boolean fail) {
        try {
            System.out.println("try-only");
            if (fail) {
                throw new IllegalStateException("failed");
            }
            System.out.println("work-ok");
        } finally {
            System.out.println("finally-only");
        }
        System.out.println("after-only");
    }

    static void catchFinally(int code) {
        try {
            System.out.println("try=" + code);
            if (code == 1) {
                throw new NumberFormatException("invalid number");
            }
            if (code == 2) {
                throw new IllegalStateException("state");
            }
            System.out.println("try-ok");
        } catch (NumberFormatException ex) {
            System.out.println("catch-number=" + ex.getMessage());
        } catch (RuntimeException ex) {
            System.out.println("catch-runtime=" + ex.getMessage());
        } finally {
            System.out.println("finally-mixed");
        }
        System.out.println("after-mixed");
    }

    public static void main(String[] args) {
        onlyFinally(false);

        try {
            onlyFinally(true);
        } catch (IllegalStateException ex) {
            System.out.println("outer=" + ex.getMessage());
        }

        catchFinally(0);
        catchFinally(1);
        catchFinally(2);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 FinallyFormsDemo.java
java FinallyFormsDemo
```

Exact output:

```text
try-only
work-ok
finally-only
after-only
try-only
finally-only
outer=failed
try=0
try-ok
finally-mixed
after-mixed
try=1
catch-number=invalid number
finally-mixed
after-mixed
try=2
catch-runtime=state
finally-mixed
after-mixed
```

Explanation:

- `onlyFinally(false)`: `try` finishes normally, then `finally` runs and the method prints `after-only`.
- `onlyFinally(true)`: `throw` causes `try` to complete abruptly. `finally` still prints `finally-only`. Because this construct has no local `catch`, the exception continues to the outer `catch` in `main`; `after-only` is not printed in that call.
- `catchFinally(0)`: `try` does not throw an error; both `catch` blocks are skipped; `finally` runs.
- `catchFinally(1)`: `NumberFormatException` matches the first specific branch; the `RuntimeException` branch does not run.
- `catchFinally(2)`: the exception does not match `NumberFormatException` but matches `RuntimeException`. After this branch, `finally` runs and the method continues to `after-mixed`.

The code intentionally uses unchecked exceptions to focus on observing the syntax and execution order without needing `throws` clauses in the signatures.

## 5. Checked exceptions must still be caught or declared

Adding `finally` **does not exempt code from Java's checked exception rules**. If a call can throw `IOException` and there is no `catch` handling that exception, the method containing `try-finally` usually must declare `throws IOException` or an allowed supertype.

Save as `CheckedFinallyDemo.java`:

```java
import java.io.IOException;

public class CheckedFinallyDemo {
    static void readConfig() throws IOException {
        try {
            System.out.println("read");
            throw new IOException("config missing");
        } finally {
            System.out.println("cleanup");
        }
    }

    public static void main(String[] args) {
        try {
            readConfig();
        } catch (IOException ex) {
            System.out.println("handled=" + ex.getMessage());
        }
        System.out.println("after main catch");
    }
}
```

```bash
javac -encoding UTF-8 CheckedFinallyDemo.java
java CheckedFinallyDemo
```

Output:

```text
read
cleanup
handled=config missing
after main catch
```

Key point: `readConfig()` declares `throws IOException` because the error can leave the method. `finally` only performs the final step; `main()` has the `catch` to handle that error.

If `catch (IOException ex)` is placed **before `finally`** inside `readConfig()` itself and handles the error without rethrowing a checked exception, the `throws IOException` declaration may no longer be needed. Even so, `catch` should only handle what the current layer actually knows how to handle, rather than automatically swallowing errors just to make the code look "clean".

## 6. `return`, `break`, and `continue` still go through `finally`

According to the JLS, statements such as `return`, `break`, and `continue` cause the running code to **complete abruptly** with a transfer-of-control reason, even though no exception is thrown. `finally` is executed before the pending reason completes transferring control out of the construct.

Runnable example, saved as `FinallyControlFlowDemo.java`:

```java
public class FinallyControlFlowDemo {
    static int returnValue() {
        int value = 10;
        try {
            return value;
        } finally {
            value = 99;
            System.out.println("finally value=" + value);
        }
    }

    static void loop() {
        for (int i = 0; i < 3; i++) {
            try {
                if (i == 0) {
                    continue;
                }
                if (i == 1) {
                    break;
                }
            } finally {
                System.out.println("finally i=" + i);
            }
        }
        System.out.println("loop finished");
    }

    public static void main(String[] args) {
        System.out.println("returned=" + returnValue());
        loop();
    }
}
```

```bash
javac -encoding UTF-8 FinallyControlFlowDemo.java
java FinallyControlFlowDemo
```

Output:

```text
finally value=99
returned=10
finally i=0
finally i=1
loop finished
```

In `returnValue()`, the expression `return value;` is already evaluated to the primitive value `10` before `finally` runs. Reassigning the local variable to `99` inside `finally` does not change the already-determined return value. Once `finally` finishes normally, the method returns `10`.

In the loop, `continue` at `i = 0` and `break` at `i = 1` both cause `finally` to execute. Each iteration runs `finally` once accordingly; the loop stops before `i = 2`.

**Note:** this is an example of `finally` when leaving a construct via Java control flow. It does not mean every way of terminating the JVM guarantees `finally` will run, for example if the process is forcibly terminated by the operating system.

## 7. What if `finally` itself throws an error or executes `return`?

`finally` is not restricted to completing normally. It can throw an exception, execute `return`, or perform another control-transfer action valid in its context. If it completes abruptly, the new reason **can replace** the original reason from `try` or `catch`.

| `try`/`catch` part | `finally` part | Overall statement result |
| --- | --- | --- |
| Completes normally | Completes normally | Completes normally |
| `return 10` | Completes normally | Proceeds with `return 10` |
| `throw A` | Completes normally | Proceeds with throwing exception `A` |
| `return 10` | `return 20` | Returns `20`, replacing the chosen value `10` |
| `throw A` | `throw B` | Throws `B`; the reason for throwing `A` is replaced |
| `catch` handles error and completes normally | `throw B` | The entire construct ends because of `B` |

Save as `FinallyOverrideDemo.java`:

```java
public class FinallyOverrideDemo {
    static int overriddenReturn() {
        try {
            return 10;
        } finally {
            return 20; // Illustrates behavior to avoid.
        }
    }

    static void maskedException() {
        try {
            throw new IllegalStateException("original");
        } finally {
            throw new IllegalArgumentException("cleanup"); // Should not be written like this.
        }
    }

    public static void main(String[] args) {
        System.out.println("value=" + overriddenReturn());

        try {
            maskedException();
        } catch (RuntimeException ex) {
            System.out.println("observed=" + ex.getMessage());
            System.out.println("cause=" + ex.getCause());
        }
    }
}
```

```bash
javac -encoding UTF-8 FinallyOverrideDemo.java
java FinallyOverrideDemo
```

Output:

```text
value=20
observed=cleanup
cause=null
```

Even though `try` initially intended to return `10`, `return 20` in `finally` replaced it. In `maskedException()`, `IllegalStateException("original")` is not the object propagated out: `finally` threw a new exception `IllegalArgumentException("cleanup")`. This new exception **does not automatically contain the old exception in `getCause()`**; the example prints `null`.

This is a **cautionary example**, not a design pattern to apply. Avoid `return` in `finally`, and avoid overriding the original exception during cleanup. For closeable resources, prefer `try-with-resources` so Java manages exceptions thrown during closing.

## 8. Exceptions from `catch` or `finally` are not caught by "sibling" `catch` blocks

A common misconception is that when a `catch` block throws a new error, Java falls through to the next `catch` branch of the **same** `try` statement. This is false. Sibling `catch` blocks are alternative handlers for errors thrown from the `try` block; they do not form a sequential processing chain.

```java
try {
    throw new IllegalArgumentException("input");
} catch (IllegalArgumentException ex) {
    throw new IllegalStateException("converted", ex);
} catch (IllegalStateException ex) {
    System.out.println("not selected for converted error");
} finally {
    System.out.println("finally");
}
```

This is a valid illustrative snippet inside a method. If there is no outer `catch`, `IllegalStateException("converted")` still propagates out after printing `finally`. The sibling `catch (IllegalStateException)` branch **does not handle** the exception just raised in the preceding `catch` branch.

Similarly, an exception raised **from `finally`** is not retried against the `catch` branches of the same construct. To handle the new exception, you must wrap it in an outer `try-catch` construct or handle it directly where it can occur.

Valid nested syntax:

```java
try {
    try {
        throw new IllegalArgumentException("input");
    } catch (IllegalArgumentException ex) {
        throw new IllegalStateException("converted", ex);
    } finally {
        System.out.println("inner-finally");
    }
} catch (IllegalStateException ex) {
    System.out.println("outer-catch=" + ex.getMessage());
}
```

Output of the second illustrative snippet:

```text
inner-finally
outer-catch=converted
```

The key point is the **boundary of the `try` construct**: an error thrown from a `catch` block of the inner construct exits that construct and can be caught by a handler of the outer construct.

## 9. Resource cleanup: standard `finally` vs. `try-with-resources`

`finally` can be used to restore temporary state or perform closing actions required by an application contract. However, using `finally` to close every resource object manually often makes code verbose, especially when **both the business logic and the close operation can throw exceptions**.

Manual approach, illustrative:

```java
Resource resource = openResource();
try {
    useResource(resource);
} finally {
    resource.close();
}
```

The snippet above is **illustrative code only**, assuming `Resource`, `openResource()`, and `useResource(...)` exist. It has limitations: `openResource()` is called **before `try`**, so if opening fails, this `finally` is not applied; additionally, a `close()` error can mask the original error if `try` also threw an error.

For `AutoCloseable` types, Java provides `try-with-resources`:

```java
try (Resource resource = openResource()) {
    useResource(resource);
} catch (IOException ex) {
    handleIoFailure(ex);
} finally {
    finishOperation();
}
```

This is an illustrative template with a `Resource` type implementing `AutoCloseable` and helper methods with matching signatures. This construct differs from standard `try-finally` because it has the resource specification `(...)` after `try`. A `try-with-resources` statement **can omit both `catch` and `finally`**, as long as there is at least one valid resource in `(...)`.

Successfully initialized resources are closed in the reverse order of their initialization. When `catch`/`finally` are present, the automatic close operations of `try-with-resources` happen **before** the `catch` and `finally` blocks of the same statement. If the `try` body throws an error and `close()` also throws an error, the close error can be preserved in `getSuppressed()` of the primary exception instead of overriding it.

### Runnable program illustrating close order and `catch-finally`

Save as `ResourceOrderDemo.java`:

```java
public class ResourceOrderDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("close");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("body");
            throw new IllegalStateException("failed");
        } catch (IllegalStateException ex) {
            System.out.println("catch=" + ex.getMessage());
        } finally {
            System.out.println("finally");
        }
        System.out.println("after");
    }
}
```

```bash
javac -encoding UTF-8 ResourceOrderDemo.java
java ResourceOrderDemo
```

Output:

```text
body
close
catch=failed
finally
after
```

This order shows: the `try-with-resources` body runs, the resource closes automatically, the `catch` branch handles the error, `finally` performs the final step, and then the program continues. Remember this is a **comparison with the resource-management syntax**; when learning the two foundational constructs, `try-finally` and `try-catch-finally` do not require `AutoCloseable` resources.

## 10. Distinguishing the `try` scope from code before/after the construct

`finally` is bound to **a specific `try` statement**. It is not a handler for "all code in the method", so you must choose where to place `try` accurately.

Illustrative example:

```java
String config = loadConfig(); // If this throws, execution has not entered the try below.
try {
    useConfig(config);
} finally {
    System.out.println("finally");
}
```

If `loadConfig()` throws an exception before the `try` statement begins executing, the `finally` below it **does not run** because the construct was never entered. To clean up across both operations, you need to redesign the `try` scope or use an appropriate resource construct, rather than just placing `finally` anywhere at the end of a method.

Variable scope also matters. A local variable declared **only inside the `try` block** is not visible in `finally`:

```java
try {
    int count = 10;
    System.out.println(count);
} finally {
    // System.out.println(count); // If uncommented: variable count cannot be found.
}
```

When you actually need to use a variable in both blocks, you must declare it in an enclosing scope while ensuring it is initialized according to the *definite assignment* rules:

```java
int count = 0;
try {
    count = 10;
} finally {
    System.out.println(count);
}
```

In the latter example, `count` is visible and already initialized before the construct, so the code is valid. These two snippets are illustrative code inside a method body, not standalone files with `main`.

## 11. Common syntax mistakes

### Mistake 1: standard `try` without `catch` or `finally`

```java
class InvalidBareTry {
    void run() {
        try {
            System.out.println("work");
        }
    }
}
```

**Intentionally does not compile.** This is not `try-with-resources`; at least one `catch` or `finally` is required.

### Mistake 2: placing `finally` before `catch`

```java
class InvalidClauseOrder {
    void run() {
        try {
            throw new IllegalArgumentException("bad");
        } finally {
            System.out.println("cleanup");
        } catch (IllegalArgumentException ex) {
            System.out.println("handled");
        }
    }
}
```

**Intentionally does not compile.** The correct order is `try { ... } catch (...) { ... } finally { ... }`. You cannot place `catch` after `finally` in the same construct.

### Mistake 3: catching a parent exception before a child exception

```java
class InvalidCatchOrder {
    void run() {
        try {
            throw new IllegalArgumentException("bad");
        } catch (RuntimeException ex) {
            System.out.println("general");
        } catch (IllegalArgumentException ex) {
            System.out.println("specific");
        } finally {
            System.out.println("cleanup");
        }
    }
}
```

**Intentionally does not compile** because `RuntimeException` already covers `IllegalArgumentException`. Place the child branch before the parent branch if specialized handling is actually needed.

### Mistake 4: treating `finally` as `catch` to swallow a checked exception

```java
import java.io.IOException;

class InvalidCheckedFinally {
    void run() {
        try {
            throw new IOException("failed");
        } finally {
            System.out.println("cleanup");
        }
    }
}
```

**Intentionally does not compile** because `IOException` is a checked exception and can escape `run()`. Fix it with `void run() throws IOException` or catch the appropriate type in the right scope. `finally` does not fulfill this obligation by itself.

### Mistake 5: thinking `finally` always rescues the process

Even when the syntax is valid, `finally` is not guaranteed to run if the process is abruptly terminated from outside, the JVM crashes, or a process-stop command does not allow normal Java flow to continue. Do not rely on `finally` as an absolute guarantee for writing critical data when the process could lose power or be forcibly killed.

## 12. How to choose the construct in practice

| Need | Appropriate construct |
| --- | --- |
| Need to do final work, while letting errors propagate up for higher layers to handle | `try-finally` |
| Can catch a specific error locally and still need to perform a final step | `try-catch-finally` |
| Want to catch an error with no separate final work | `try-catch` |
| Need to close one or more `AutoCloseable` resources | Prefer `try-with-resources`; add `catch`/`finally` if needed |
| Want to preserve original error info when translating exceptions | `catch` creating a new error with `cause`; avoid `finally` throwing and overriding |
| Only want to log and let the error continue propagating | Usually consider logging at an appropriate boundary; `try-finally` has no logging duty |
| Need to recover with a valid fallback | `catch` at a layer with context; `finally` only handles final work |

The right construct depends on the responsibility of the current layer. For example, a repository layer might let `IOException` propagate up to a service, while an API layer might use `catch` or a centralized error-handling mechanism. `finally` should contain work that must happen when leaving the scope, **not logic that replaces results or exceptions**.

## 13. How to predict the output of a `try-catch-finally` snippet

Read the code in the following order:

1. **What does the `try` block do?** Does it complete normally, `throw`, `return`, `break`, or `continue`?
2. **If there is an exception, which `catch` matches?** Check the actual type and the `catch` order; do not assume every branch will run.
3. **If `catch` ran, how does it complete?** Does it return a result, rethrow the error, create a new exception, or complete normally?
4. **Does the `finally` block do anything that changes control flow?** If it completes normally, the previous reason is kept; if it executes `throw` or `return`, it can replace it.
5. **After the entire construct, what runs?** The next statement runs only if the construct can complete normally on the path under consideration. If an error is propagating, check `catch` in outer scopes.

Try predicting the output of this snippet inside a method:

```java
try {
    System.out.println("start");
    throw new IllegalArgumentException("bad");
} catch (IllegalArgumentException ex) {
    System.out.println("handled");
} finally {
    System.out.println("end");
}
System.out.println("next");
```

Output:

```text
start
handled
end
next
```

The error is handled in the first compatible `catch`, `finally` completes normally so the entire `try-catch-finally` also completes normally, and then execution reaches `next`.

If `catch` is removed while keeping `finally`, the output before the exception propagates out consists only of `start` and `end`; the line `next` does not run on that path.

## 14. Self-check questions

**1.** Can you write `try { ... } finally { ... }` without a `catch`?  
**Yes.** That is `try-finally`. If `try` throws an error, a normal `finally` does not prevent the error from propagating outward.

**2.** In `try-catch-finally`, does `finally` come before or after the `catch` blocks?  
**After all `catch` blocks** of the same construct; writing them in reverse order is a syntax error.

**3.** When `try` does not throw an error, does `catch` run like an `else`?  
**No.** The `catch` blocks are skipped; `finally` is still executed according to the rules.

**4.** When `catch` has handled an error and completed normally, does `finally` run?  
**Yes.** Afterward, the program can continue to the next statement if `finally` also completes normally.

**5.** If `try` has `return 10` and `finally` only logs, what is the return value?  
**10**, unless `finally` itself causes another abrupt completion reason. `finally` runs before the method actually returns.

**6.** What happens if `finally` writes `return 20` while `try` intends `return 10`?  
The result becomes **20**. This is why `return` in `finally` should be avoided.

**7.** Is an exception thrown from `finally` automatically caught by a preceding sibling `catch`?  
**No.** It propagates to the outer scope; an enclosing handler is needed if you want to catch it.

**8.** Is closing resources with `try-with-resources` completely identical to writing `resource.close()` manually in `finally`?  
**No.** The resource syntax has its own initialization, automatic closing, and suppressed-exception rules.

**9.** Can `try { throw new IOException(); } finally { ... }` omit `throws IOException` on the method signature?  
**No**, if there is no suitable handler and `finally` can complete normally: a checked exception must still be caught or declared.

**10.** Does `finally` run if an operation before the `try` statement throws an error, preventing entry into `try`?  
**No.** The `finally` scope is bound to the `try` statement, which the program has not started.

## Official references

- [Java Language Specification 21 — §14.20: The `try` Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20).
- [JLS 21 — §14.20.1: Execution of `try-catch`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.1).
- [JLS 21 — §14.20.2: Execution of `try-finally` and `try-catch-finally`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.2).
- [JLS 21 — §14.20.3: `try-with-resources`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.3).
- [JLS 21 — §11.2: Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.2).

**Key takeaway:** `try-finally` is used when you need to execute a final step while allowing errors to continue propagating; `try-catch-finally` adds the ability to handle exceptions locally. In both constructs, `finally` runs before completing the exit from the statement under normal Java flow; if `finally` itself executes `return` or throws an error, it can replace the original result or exception.
