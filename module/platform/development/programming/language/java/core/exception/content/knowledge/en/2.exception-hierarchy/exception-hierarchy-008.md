# Why Doesn't `catch (Exception)` Catch Every `Throwable` in Java?

> **Topic:** Java Core — Exception · Exception Hierarchy. The core answer: **`Exception` is only one branch under `Throwable`.** `catch (Exception e)` handles objects of type `Exception` or its subclasses, whereas objects belonging to the `Error` branch (and other direct subclasses of `Throwable`) are not `Exception`s, so they do not match. The fact that Java allows `catch (Throwable)` does not mean an application should catch every error at that level.

## 1. Looking at the Inheritance Tree Correctly

`Throwable` is the root class of objects that can be thrown with `throw` and caught with `catch` in Java's exception system. Its two familiar branches underneath are `Exception` and `Error`:

```text
java.lang.Object
└── java.lang.Throwable
    ├── java.lang.Exception
    │   ├── java.io.IOException
    │   │   └── java.io.FileNotFoundException
    │   └── java.lang.RuntimeException
    │       ├── java.lang.IllegalArgumentException
    │       │   └── java.lang.NumberFormatException
    │       ├── java.lang.NullPointerException
    │       └── java.lang.IllegalStateException
    │
    ├── java.lang.Error
    │   ├── java.lang.AssertionError
    │   ├── java.lang.LinkageError
    │   └── java.lang.VirtualMachineError
    │       ├── java.lang.OutOfMemoryError
    │       └── java.lang.StackOverflowError
    │
    └── (other classes if directly extending Throwable)
```

The tree above lists **representative examples**, not all subclasses in the JDK. This branching means:

- `Exception extends Throwable`: every `Exception` object is a `Throwable`.
- `RuntimeException extends Exception`: every `RuntimeException` is an `Exception` and a `Throwable`.
- `Error extends Throwable`: every `Error` object is a `Throwable`, **but is not of type `Exception`**.
- Java allows writing a class that directly `extends Throwable`. That class does not automatically become an `Exception` or an `Error` either. This is a capability of the language, though you should generally choose one of the standard branches when designing an API.

**The decisive relationship:** `Exception` and `Error` are sibling branches, not a parent–child relationship. `catch (Exception)` is not meant to “catch everything throwable”; it only catches objects compatible with the `Exception` type.

## 2. How Does Java Select a `catch`?

When an exception or error is thrown inside a `try` block, the runtime checks the `catch` clauses attached to that block in declaration order to find a handler whose type is compatible with the **actual object being thrown**.

A `catch (T e)` handler can handle an object with runtime type `T` or a subclass of `T`. In practice, there is also multi-catch such as `catch (IOException | IllegalArgumentException e)`, which matches when the object matches one of the listed types.

Suppose the object being thrown is a `NumberFormatException`:

- `catch (NumberFormatException e)` matches exactly.
- `catch (IllegalArgumentException e)` matches because `NumberFormatException` is a subclass of `IllegalArgumentException`.
- `catch (RuntimeException e)` matches because it is an ancestor of it.
- `catch (Exception e)` matches because `RuntimeException extends Exception`.
- `catch (Throwable e)` also matches because `Throwable` is the common ancestor.
- `catch (Error e)` **does not match**.

If the object is an `AssertionError`:

- `catch (AssertionError e)` matches.
- `catch (Error e)` matches.
- `catch (Throwable e)` matches.
- `catch (Exception e)` **does not match**, because `AssertionError` sits under `Error`.

### 2.1. Quick Comparison Table

| Thrown Object | `catch (Exception)` | `catch (RuntimeException)` | `catch (Error)` | `catch (Throwable)` |
| --- | --- | --- | --- | --- |
| `new IOException("...")` | Yes | No | No | Yes |
| `new NumberFormatException("...")` | Yes | Yes | No | Yes |
| `new NullPointerException("...")` | Yes | Yes | No | Yes |
| `new AssertionError("...")` | **No** | No | Yes | Yes |
| `new LinkageError("...")` | **No** | No | Yes | Yes |
| Object from a class that directly `extends Throwable` | **No** | No | No | Yes |

Here “Yes” means **type-compatible**, and does not imply that the handler is guaranteed to execute in every piece of code: an earlier handler might have already caught the object, or the exception might occur in a different `try` block. In addition, Java has compile-time rules about unreachable handlers (unreachable catch), so not every ordering of the branches above is a valid program.

### 2.2. Handler Ordering When Multiple `catch` Clauses Match

Within **the same `try`**, Java evaluates `catch` clauses in declaration order and picks the first matching branch. Therefore, `catch (NumberFormatException)` must come **before** `catch (Exception)`: if reversed, the compiler reports that the subclass handler is unreachable.

```java
try {
    Integer.parseInt("abc");
} catch (NumberFormatException e) {
    System.out.println("Chuỗi không phải số");
} catch (Exception e) {
    System.out.println("Exception khác");
}
```

This is a code snippet placed inside a method; it prints `Chuỗi không phải số`. Handler ordering explains **which handler is selected within the Exception branch**; the core question here is the type boundary: regardless of where it is placed, `catch (Exception)` still does not match `Error` because `Error` does not inherit from `Exception`.

## 3. Java 17 Program: `catch (Exception)` Bypassed by `AssertionError`

This is a standalone example demonstrating both scenarios by separating handlers at an inner and outer layer. To observe safely, it uses an `AssertionError` **explicitly thrown** by the program. Do not trigger real `OutOfMemoryError`/`StackOverflowError` for testing.

Save as `CatchExceptionBoundaryDemo.java`:

```java
public class CatchExceptionBoundaryDemo {
    static void runCase(String label, Runnable operation) {
        try {
            try {
                operation.run();
                System.out.println(label + ": thành công");
            } catch (Exception e) {
                System.out.println(label + ": catch Exception -> "
                        + e.getClass().getSimpleName());
            }
        } catch (AssertionError e) {
            System.out.println(label + ": catch AssertionError bên ngoài -> "
                    + e.getClass().getSimpleName());
        } finally {
            System.out.println(label + ": finally");
        }
    }

    public static void main(String[] args) {
        runCase("Parse", () -> {
            Integer.parseInt("abc");
        });

        runCase("Kiểm tra", () -> {
            throw new AssertionError("Chủ động tạo để minh họa");
        });
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 CatchExceptionBoundaryDemo.java
java CatchExceptionBoundaryDemo
```

**Exact stdout:**

```text
Parse: catch Exception -> NumberFormatException
Parse: finally
Kiểm tra: catch AssertionError bên ngoài -> AssertionError
Kiểm tra: finally
```

**Explanation of each path:**

1. `Integer.parseInt("abc")` throws `NumberFormatException`, which is a subclass of `RuntimeException` → `Exception`. The inner `catch (Exception)` handler catches it, so no outer handler needs to be searched. Then `finally` runs.
2. `throw new AssertionError(...)` throws an object from the `Error` branch. The `catch (Exception)` handler is incompatible, so the exception propagates out of the inner block and is caught by the outer `catch (AssertionError)` handler. The outer `finally` still runs according to Java's normal control flow.
3. The `"...: thành công"` print statement does not execute in either case because `operation.run()` ends by throwing a `Throwable` in both cases.

**Important point:** the example intentionally catches `AssertionError` **solely to demonstrate the matching mechanism**. It does not encourage applications to catch `Error`-branch errors as a routine recovery policy.

### 3.1. What Happens Without the Outer `catch (AssertionError)`?

If the outer handler is removed and `AssertionError` is left unhandled at higher layers, the error continues propagating through the calling methods. If a `Throwable` goes uncaught up to the top boundary of the thread, the thread's uncaught exception handler may report a stack trace or handle it according to configuration. You cannot predict every printed line of a stack trace as stable stdout: line numbers vary by file, errors are typically reported to stderr, and handlers can be configured.

The key takeaway is that **`catch (Exception)` does not turn an `Error` into a valid result**, even when there is a `finally` block in the same method.

## 4. `Exception` Is Not Synonymous with “Checked Exception”

Another common misconception is thinking `catch (Exception)` only catches checked exceptions, while `RuntimeException` is “unchecked so it cannot be caught.” This is false.

**Checked/unchecked** is how the Java compiler enforces the obligation to catch or declare errors, which is different from how the runtime matches handler types:

- `Exception` and its subclasses, **excluding `RuntimeException` and its subclasses**, are generally checked exceptions.
- `RuntimeException` and its subclasses are unchecked, yet **still belong to the `Exception` branch**, so `catch (Exception)` catches them.
- `Error` and its subclasses are unchecked, and **do not belong to the `Exception` branch**, so `catch (Exception)` does not catch them.
- A custom class that directly `extends Throwable` (outside `RuntimeException` and `Error`) is checked according to the language rules, yet `catch (Exception)` still does not catch it.

More precisely, an exception class is **unchecked** if it is a subclass of `RuntimeException` or `Error`; all other throwable classes are **checked**. Therefore, “checked” is not a name for the entire `Exception` branch and only that branch.

### 4.1. Runnable Classification Example

Create `ThrowableTypeDemo.java`:

```java
import java.io.IOException;

public class ThrowableTypeDemo {
    static final class CustomSignal extends Throwable {
        CustomSignal(String message) {
            super(message);
        }
    }

    static void describe(Throwable value) {
        System.out.println(value.getClass().getSimpleName()
                + " | Exception=" + (value instanceof Exception)
                + " | Error=" + (value instanceof Error));
    }

    public static void main(String[] args) {
        describe(new IOException("I/O"));
        describe(new NumberFormatException("parse"));
        describe(new AssertionError("assert"));
        describe(new CustomSignal("direct Throwable child"));
    }
}
```

Run:

```bash
javac -encoding UTF-8 ThrowableTypeDemo.java
java ThrowableTypeDemo
```

Stdout:

```text
IOException | Exception=true | Error=false
NumberFormatException | Exception=true | Error=false
AssertionError | Exception=false | Error=true
CustomSignal | Exception=false | Error=false
```

The `describe(Throwable value)` method accepts all objects because its parameter type is `Throwable`. However, passing an object as a parameter is **different** from using `catch`: in this example, the program only checks types with `instanceof` without throwing them.

The `CustomSignal extends Throwable` class is included to prove the inheritance tree can have other branches. Because it does not belong to `RuntimeException` or `Error`, if a method actually executes `throw new CustomSignal(...)`, the compiler will require catching or declaring this type. In typical Java design, you should extend `Exception` or `RuntimeException` depending on the contract rather than extending `Throwable` directly.

## 5. Why Are There Two Branches: `Exception` and `Error`?

The separation helps distinguish **the kinds of situations application code can typically handle** from problems that may lie in the execution mechanism, class linkage, the virtual machine, or broken program assumptions.

### 5.1. The `Exception` Branch

Examples:

- `IOException`: reading/writing data failed, file could not be opened, stream encountered an error.
- `FileNotFoundException`: a specific case under `IOException`.
- `NumberFormatException`: string cannot be parsed into the requested number.
- `IllegalArgumentException`: invalid argument according to the API.
- `IllegalStateException`: current state does not allow the operation.
- `NullPointerException`: invalid operation on a `null` reference, usually a programming bug or contract violation.

Some have reasonable recovery strategies: prompting the user to re-enter input, choosing another file, canceling the current operation, or translating into a context-appropriate error message. However, not every `Exception` is “mild” or safely recoverable. For instance, `NullPointerException` often indicates a bug that needs fixing; catching it and continuing unconditionally can corrupt data further.

### 5.2. The `Error` Branch

Examples:

- `OutOfMemoryError`: the JVM lacks sufficient memory for an allocation request or related memory limit.
- `StackOverflowError`: call depth is too deep, overflowing the stack.
- `LinkageError`: an issue in class linking, loading, or compatibility checks.
- `AssertionError`: an assertion failed, or code explicitly threw this object.
- `ThreadDeath`: also an `Error` in Java, related to the deprecated thread-stopping mechanism.

Many `Error`s reflect broken environmental conditions or foundational assumptions, where continuing normal execution may be unsafe. However, **you should not claim that every `Error` is uncatchable or always terminates the entire JVM**. They are still `Throwable` objects that can be caught by a compatible handler at the language level. A test-generated `AssertionError` is an example that is readily caught in a testing environment. The real question is **whether you should recover**, depending on the error kind and the handling boundary.

Java does not guarantee that after an `OutOfMemoryError`, the program has enough resources to log, instantiate new exceptions, close all resources, or run complex recovery logic. Therefore, you should not write programs on the assumption that `catch (Throwable)` guarantees “never crashing.”

## 6. Comparing `catch (Exception)`, `catch (Error)`, and `catch (Throwable)`

| Handler | Type Coverage | Typical Usage | Risk If Abused |
| --- | --- | --- | --- |
| `catch (NumberFormatException e)` | One parse error type and its subclasses | At input boundaries, when you can explain the error or prompt for re-entry | Only appropriate if you have a specific handling plan. |
| `catch (IOException e)` | I/O errors and subclasses | Add context, choose an alternate source, report operation failure | Swallowing the error may make the caller think it succeeded. |
| `catch (Exception e)` | All `Exception`s and subclasses, both checked and unchecked | Application boundaries with broad handling policies; sometimes adapters converting errors | Hides programming bugs if caught too broadly and silenced. **Does not catch `Error`.** |
| `catch (RuntimeException e)` | `RuntimeException` and subclasses | Boundaries responsible for isolating certain unexpected errors | May hide bugs and corrupt business state. |
| `catch (Error e)` | `Error` and subclasses | Very specific scenarios, e.g., testing an intentionally thrown `AssertionError` | Attempting to recover from VM/linkage errors can be dangerous or impossible. |
| `catch (Throwable t)` | Both `Exception`, `Error`, and other subclasses | Very low-level diagnostic tools/frameworks, with policies to preserve and rethrow serious errors | Swallows critical errors, corrupts state, turns a broken system into “success.” |

**Practical rule:** catch the most specific type that the current layer actually knows how to handle. If recovery is not possible, let the exception propagate upward, adding context when crossing layers while preserving `cause`. “Catching broadly” is a design choice at tightly controlled boundaries, not a trick to make every method safe.

### 6.1. Does `catch (Throwable)` Prevent Every Failure in the World?

No. It is the broadest handler in terms of **throwable Java object types**, yet it still has limits:

1. It only catches `Throwable`s thrown within the corresponding `try` scope and propagated through control flow to that handler. An exception on **another thread** does not jump to the current thread's handler.
2. It cannot guarantee handling when the OS terminates the process, the JVM halts abruptly, power fails, or a native crash brings down the process.
3. There may not be enough memory/resources to execute the handler reliably after a severe failure.
4. It does not turn side effects that have already occurred into a rolled-back operation.
5. It does not detect logic bugs that produce wrong results **without throwing** an exception.

Do not interpret `catch (Throwable)` as an “absolute shield.”

### 6.2. Why Does `catch (Exception)` Still Appear in Production Code Sometimes?

At the boundary of a request handler, task executor, CLI command, or job runner, an application may need to translate various exceptions into a task-specific failure. For example, when an individual task fails, the system logs it, marks the task as failed, and moves on to other work. This is only reasonable when:

- the catch scope and recoverable state are well defined;
- a failure is reported as a failure, not disguised as success;
- the task's resources are properly cleaned up;
- severe `Error`-branch failures are not silently swallowed;
- there are policies for retries, monitoring, and isolating corrupted state.

Even in those places, more specific handlers usually lead to better decisions than a generic `catch (Exception)`.

## 7. From `throw` and `throws` to Handlers: Don't Confuse Compile Time with Runtime

Consider this example method:

```java
static void readData() throws java.io.IOException {
    throw new java.io.IOException("Không đọc được");
}
```

This is an illustrative snippet, not a complete program. Because `IOException` is a checked exception, a direct caller must catch or re-declare it. You can write `catch (Exception)` to catch it because `IOException extends Exception`, though using `catch (IOException)` expresses more specific intent.

Meanwhile:

```java
static void detectInvalidState() {
    throw new AssertionError("Giả định chương trình bị phá vỡ");
}
```

The second snippet throws `AssertionError`, which is an unchecked `Error`. It does not require declaring `throws AssertionError`. A caller wrapping the call in `catch (Exception)` **still cannot catch `AssertionError`**. The compiler's checked/unchecked rules and runtime type relationships are **two separate concerns**.

### 7.1. Can a Method Declaring `throws Exception` Throw an `Error`?

Yes. `throws Exception` declares the possible exit of the corresponding checked exceptions; it does not forbid `RuntimeException` or `Error` from occurring at runtime.

Conversely, a method declaring `throws Throwable` does not force callers to use `catch (Throwable)`. Callers can declare `throws Throwable`, or catch appropriate types according to checked exception rules. In standard API design, avoid overly broad declarations when specific error types can be described.

### 7.2. What Does the Compiler Check?

The compiler checks constraints such as handlers shadowed by an earlier handler, uncaught/undeclared checked exceptions, and certain checked handlers that cannot receive any exception thrown from the `try` block. However, the compiler does not decide that an `Error` “cannot happen” just because a method does not declare `throws Error`.

Not every piece of code containing `catch (Error)` is a good design choice. Compilability does not replace evaluating recoverability.

## 8. Wrapped Exceptions: Handlers Inspect the **Thrown Object**, Not `cause`

The root failure may be an `Error`, yet outer code throws a new `Exception` wrapping that error as its cause. In that case, `catch (Exception)` catches **the wrapper**, because the object actually thrown is an `Exception`. It does not automatically “directly catch the inner `Error`.”

Create `WrappedThrowableDemo.java`:

```java
public class WrappedThrowableDemo {
    static void callService() {
        try {
            throw new AssertionError("Gốc");
        } catch (AssertionError original) {
            throw new IllegalStateException("Bọc lỗi để minh họa", original);
        }
    }

    public static void main(String[] args) {
        try {
            callService();
        } catch (Exception e) {
            System.out.println("Bắt được: "
                    + e.getClass().getSimpleName());
            System.out.println("Cause: "
                    + e.getCause().getClass().getSimpleName());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 WrappedThrowableDemo.java
java WrappedThrowableDemo
```

Stdout:

```text
Bắt được: IllegalStateException
Cause: AssertionError
```

The example uses `AssertionError` to illustrate the wrapper/cause relationship, **not as a recommended Error-handling pattern**. In real applications, you generally avoid converting every `Error` into a normal exception to keep running. The contract and policy at that layer determine when wrapping a cause is appropriate.

The symmetric case: if an `Error` has an `IOException` as `getCause()`, `catch (Exception)` **cannot** catch the propagating `Error` object, even though the underlying cause is a checked exception. Handlers match against the **outer object being thrown**, without digging into `getCause()` to pick a catch clause.

## 9. `finally`, try-with-resources, and Propagation

When `catch (Exception)` does not match an `Error`, handlers in higher call frames may still be considered. While unwinding out of the block, a normal `finally` block still executes; try-with-resources also invokes `close()` on resources according to its rules.

Example:

```java
try {
    throw new AssertionError("Báo lỗi");
} catch (Exception e) {
    System.out.println("Không chạy");
} finally {
    System.out.println("Dọn dẹp");
}
```

This is an illustrative snippet inside a method. When run, `catch (Exception)` is not selected; `finally` prints “Dọn dẹp”; then `AssertionError` continues propagating outward if no handler exists at an upper layer. Therefore, an executed `finally` block **does not prove** the exception was handled.

You should not claim that `finally` is guaranteed to run in every situation; if the process/JVM is terminated abnormally, there is no universal guarantee. Avoid `return` or throwing a new error inside `finally` because it can mask the original error.

### 9.1. Avoiding Lost Errors During Cleanup

If the body of a try-with-resources block throws an exception and `close()` also throws, Java generally preserves the body's error as the primary exception; the closing error is added to `getSuppressed()`. This mechanism follows try-with-resources rules and does not depend on any assumption that “`catch (Exception)` will catch every error.”

If the primary exception is an `Error`, a `catch (Exception)` handler still cannot handle it, even if an `IOException` from `close()` was suppressed onto the primary object. The branch of the error **thrown outward** determines which handler matches.

## 10. When Should You Catch `Error`?

There is no “never ever catch `Error`” rule in the Java language. Certain specialized environments may need to recognize a specific error:

- Testing frameworks may record `AssertionError` as a test failure for reporting.
- Diagnostic tools or very low-level runtime boundaries may observe the error to record minimal information and then **rethrow**.
- Code with a very specific isolation and recovery protocol may handle a particular `Error` type; this decision requires deep understanding of the API and system state.

For ordinary business code, however, you should not do this:

```java
// Anti-pattern: do not use as a general error-handling strategy.
try {
    performBusinessOperation();
} catch (Throwable ignored) {
    // Swallows every Throwable and continues as if it succeeded.
}
```

The snippet above is **non-standalone illustrative code**: `performBusinessOperation()` is undefined. It shows an anti-pattern to avoid, not a complete Java program.

A better approach at application handling boundaries is typically to catch the exact exceptions you have a recovery plan for; clean up resources with try-with-resources; log or propagate failures you cannot recover from yourself; and let serious errors be handled by appropriate operational/retry/restart policies.

In particular, do not try to trigger `OutOfMemoryError` or `StackOverflowError` in a working environment just to test the matching table. Using an explicitly thrown `AssertionError` is sufficient to demonstrate inheritance relationships and handler matching.

## 11. Misconceptions to Avoid

| Misconception | Accurate Explanation |
| --- | --- |
| “`Throwable` and `Exception` are the same type.” | `Exception` is **a subclass** of `Throwable`; `Error` is a different branch. |
| “`catch (Exception)` catches everything that can be `throw`n.” | It does not catch `Error` or other direct subclasses of `Throwable` outside `Exception`. |
| “`RuntimeException` is unchecked, so `catch (Exception)` cannot catch it.” | `RuntimeException extends Exception`; it is still caught. |
| “`Error` cannot be `catch`ed.” | It can be caught with a compatible type (`Error`, `Throwable`, or a specific subclass), though recovery is not necessarily advisable. |
| “`catch (Throwable)` guarantees the app will never stop.” | It does not protect against JVM/process termination, native crashes, severe resource exhaustion, or exceptions on other threads. |
| “Checked exception means directly extending `Exception`.” | Checked/unchecked follows the `RuntimeException`/`Error` branches; a class that directly `extends Throwable` can be checked. |
| “`throws Exception` prevents a method from throwing an `Error`.” | `throws` does not impose that restriction on unchecked `Error`s. |
| “An `Error` inside `getCause()` will cause `catch (Exception)` to fail.” | Handlers match against the **thrown wrapper**; if the wrapper is an `Exception`, the catch still matches. |
| “If `finally` runs, the exception was caught.” | `finally` normally runs even while an exception is propagating; it is not a handler. |
| “Catching broadly and ignoring makes the program safe.” | It can hide serious errors and allow corrupted state to keep being used. |
| “Handlers check the exception type by the initially declared variable.” | Handlers are selected by the **actual runtime type of the thrown object** and its inheritance hierarchy. |

## 12. Exercises to Check Deep Understanding

### Exercise 1 — Predict the Catch Branch Without Running the Program

For each of the following objects, state whether `catch (Exception)` catches it, and explain the inheritance relationship:

1. `new ArithmeticException("division")`.
2. `new java.io.EOFException("end")`.
3. `new AssertionError("broken invariant")`.
4. `new java.lang.NoClassDefFoundError("missing")`.
5. `new IllegalStateException("state")`.

**Answer:** (1) yes, (2) yes, (3) no, (4) no, (5) yes. `ArithmeticException` and `IllegalStateException` are subclasses of `RuntimeException` → `Exception`; `EOFException` belongs to the `IOException` branch → `Exception`. `AssertionError` and `NoClassDefFoundError` belong to the `Error` branch.

### Exercise 2 — Fix Handler Ordering

Given the snippet:

```java
try {
    Integer.parseInt("?");
} catch (Exception e) {
    System.out.println("Chung");
} catch (NumberFormatException e) {
    System.out.println("Riêng");
}
```

Why does it fail to compile? Fix it by moving the specific branch first. After fixing, stdout is `Riêng`, because the thrown object is `NumberFormatException` and the first compatible handler receives it.

### Exercise 3 — Does Wrapping Change the Matching Result?

In `WrappedThrowableDemo`, replace `new IllegalStateException("...", original)` with `new AssertionError("...", original)`. Will `catch (Exception)` in `main` catch the error? Why?

**Hint:** handlers do not automatically unwrap `cause`. The outer thrown error is now `AssertionError` (the `Error` branch), so `catch (Exception)` does not match.

### Exercise 4 — Errors on Another Thread

If `main` writes `try { new Thread(task).start(); } catch (Exception e) { ... }`, and `task` throws an exception after the thread starts running, will the handler in `main` catch that exception? **No**, because the exception occurs on a different thread; `main`'s handler only applies to the control flow of the current thread. Look up `Thread.UncaughtExceptionHandler` or error collection via `Future` when studying concurrency.

### Exercise 5 — Designing a Policy

For an application processing a user-selected file, decide which layer will catch `FileNotFoundException`/`IOException`, which layer notifies the user, and what you would do if an `OutOfMemoryError` occurs. Explain why you should not use `catch (Throwable)` and return to display “Đọc file thành công”.

## 13. Retention Checklist

- [ ] Can draw `Throwable` with its two representative branches `Exception` and `Error`.
- [ ] Can explain that `RuntimeException` is unchecked yet still belongs to `Exception`.
- [ ] Can explain why `AssertionError` is not caught by `catch (Exception)`.
- [ ] Ran `CatchExceptionBoundaryDemo.java` and explained all four lines of stdout.
- [ ] Ran `ThrowableTypeDemo.java` and verified a class can directly `extends Throwable`.
- [ ] Distinguished compile-time checked/unchecked checks from runtime handler matching.
- [ ] Can name a scenario where `catch (Throwable)` may be justified and why it requires a very strict policy.
- [ ] Can read wrapper exceptions and `getCause()` without confusing the type of the thrown error.
- [ ] Understands that `finally`/try-with-resources supports cleanup but does not handle or roll back errors by itself.
- [ ] Always prefers catching the error types you can actually handle rather than swallowing `Throwable`.

**Conclusion:** `catch (Exception)` is a broad handler **within the `Exception` branch**, not a handler for every `Throwable`. `Error` and other branches of `Throwable` fall outside that scope. The difference comes from Java's inheritance tree and matching rules, while the decision of whether to catch an error depends on recoverability and the handling contract at each application layer.