# Exceptions from the `try` Body, `close()`, and Primary Exception Selection Rules in Java

A resource can fail **during initialization**, **when used inside the `try` body**, or **when `close()` is called**. If two or more failures occur within the same `try-with-resources` statement, Java does not simply pick one exception to throw and discard all others: the language defines rules to determine the **primary exception** and record secondary exceptions in the **suppressed exceptions** list.

This is a very important difference compared to manually calling `resource.close()` inside `finally`: with a manual `try-finally`, an exception thrown from `finally` can replace an exception from the `try` body. With `try-with-resources`, when the `try` body has already thrown an exception, Java normally keeps **that exception** as the primary exception, while the resource-closing error is attached via `Throwable.addSuppressed(...)`.

This lesson focuses on **event ordering and primary exception selection rules**, covering single-resource cases, multiple resources, initialization failures, `return`, `catch`, `finally`, how to inspect `getSuppressed()`, and how to avoid losing the original error when translating exceptions. The complete programs use **Java 17+**.

## 1. Concept: Primary Exception and Suppressed Exceptions

Consider a data-reading scenario:

```text
Open resource            succeeded
      |
      v
try body                 throws IOException("read failed")
      |
      v
Automatic close()        throws IOException("close failed")
      |
      v
Thrown exception         IOException("read failed")   ← primary
      |
      +-- getSuppressed() -> IOException("close failed")
```

Here:

- **Primary exception** is the `Throwable` object propagated out of `try-with-resources` for outer `catch` blocks to inspect. In this scenario, it is the read error.
- **Suppressed exception** is an additional exception that occurs while handling an already-pending exception. It is stored in the array returned by `primary.getSuppressed()`.
- **Cause** is a different relationship: `primary.getCause()` describes the underlying exception that caused a wrapped or causally linked exception. A suppressed exception **does not automatically become** the `cause`.
- An exception can have **both a cause and suppressed exceptions**. The two mechanisms hold different information.

**Do not conclude that "the last exception thrown is always the primary exception."** In `try-with-resources`, closing happens after the `try` body has already failed, yet the `try` body exception retains its primary role. If the `try` body did not fail, the first exception arising in **closing order** can become the primary exception.

## 2. Foundational Rules According to JLS §14.20.3

The Java Language Specification (JLS) defines `try-with-resources` as a construct with automatic resource-closing rules:

1. Resources are **initialized from left to right**.
2. If initialization fails on a later resource, any earlier resources that **were already initialized successfully** are closed.
3. If initialization succeeds, the `try` body executes; upon leaving the `try` body, resources are closed in **reverse order** of initialization.
4. Every non-`null` resource is closed. An exception from one close operation **does not by default prevent** Java from attempting to close the remaining resources.
5. If a primary exception already exists from initialization, the `try` body, or an earlier close operation (for a resource declared later), subsequent close exceptions are **suppressed** onto the primary exception.
6. If no exception was pending before `close()` is called, and `close()` fails, that close exception becomes the **primary exception**.
7. For an extended `try-with-resources` statement with `catch`/`finally` clauses, resources are closed **before** Java selects a `catch` clause of that statement and executes `finally`.

These rules apply to objects implementing both `AutoCloseable` and `Closeable`, provided they are used as valid resources in `try (...)`. They also apply when the `try` body completes via `return`, `break`, or `continue`, although the primary exception outcome differs from the case where the body already threw an exception.

### Quick Decision Table

| What happens first | When `close()` runs | Final exception / control transfer |
| --- | --- | --- |
| `try` body completes normally | `close()` succeeds | The entire statement can complete normally |
| `try` body throws A | `close()` succeeds | A continues to be thrown |
| `try` body throws A | `close()` throws B | A is **primary**, B is **suppressed** on A |
| `try` body completes normally | `close()` throws B | B becomes **primary** |
| Second resource initialization throws A | `close()` of first resource throws B | A is **primary**, B is suppressed |
| `try` body intends `return 42` | `close()` succeeds | Continues returning 42 |
| `try` body intends `return 42` | `close()` throws B | B is thrown; 42 is not returned |
| `try` body throws A, multiple `close()` calls throw B, C in turn | Closing steps continue | A is **primary**, B and C are recorded as suppressed in the order they occur |

This table describes the normal flow of `try-with-resources` with distinct exception objects. Rare cases—such as a resource intentionally rethrowing **the exact same `Throwable` instance** that is already the primary exception—can trigger a special *self-suppression* situation; you should not design `close()` this way.

## 3. Single Resource: Error in the Body and Error in `close()`

This is the most basic example: both the business operation and cleanup fail. Save as `BodyAndCloseDemo.java`:

```java
import java.io.IOException;

public class BodyAndCloseDemo {
    static class Resource implements AutoCloseable {
        Resource() {
            System.out.println("open");
        }

        @Override
        public void close() throws IOException {
            System.out.println("close");
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("body");
            throw new IllegalStateException("work failed");
        } catch (Exception ex) {
            System.out.println("primaryType="
                    + ex.getClass().getSimpleName());
            System.out.println("primaryMessage=" + ex.getMessage());
            System.out.println("suppressedCount=" + ex.getSuppressed().length);

            for (Throwable extra : ex.getSuppressed()) {
                System.out.println("suppressedType="
                        + extra.getClass().getSimpleName());
                System.out.println("suppressedMessage=" + extra.getMessage());
            }
        }
        System.out.println("after");
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 BodyAndCloseDemo.java
java BodyAndCloseDemo
```

Deterministic output:

```text
open
body
close
primaryType=IllegalStateException
primaryMessage=work failed
suppressedCount=1
suppressedType=IOException
suppressedMessage=close failed
after
```

Analysis:

- The `Resource()` constructor completes, so the object is registered as a resource.
- The `try` body throws `IllegalStateException("work failed")`. This object is retained as the pending `throw` reason.
- During automatic closing, `close()` prints `close` and then throws `IOException("close failed")`.
- Because a primary exception from the body already exists, the `close()` error is attached via the suppression mechanism; it **does not replace** `IllegalStateException`.
- The `catch (Exception ex)` clause outside the resource-management section receives **IllegalStateException**, not the `IOException` from closing.
- The `catch` block completes normally, so the `after` line still executes.

In real systems, `catch (Exception)` should be used carefully: the example uses it to observe the mechanism across multiple exception types; in production business code, catch only the exception types that the current layer can actually handle.

## 4. What If the `try` Body Succeeds but `close()` Fails?

A resource may operate normally and then fail when flushing data, synchronizing state, or closing a connection. In that case, **there is no exception from the `try` body** to take precedence: the close error itself becomes the exception propagated outward.

Save as `CloseOnlyFailureDemo.java`:

```java
import java.io.IOException;

public class CloseOnlyFailureDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("close");
            throw new IOException("flush failed");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("work complete");
        } catch (IOException ex) {
            System.out.println("primary=" + ex.getMessage());
            System.out.println("suppressedCount=" + ex.getSuppressed().length);
        }
        System.out.println("after");
    }
}
```

```bash
javac -encoding UTF-8 CloseOnlyFailureDemo.java
java CloseOnlyFailureDemo
```

Output:

```text
work complete
close
primary=flush failed
suppressedCount=0
after
```

The main operation prints `work complete`, yet the `try-with-resources` statement does not complete normally: `close()` throws `IOException`. This error is caught by `catch (IOException)`, with no other exceptions to suppress.

**Do not ignore close errors just because the body finished running.** For some write formats, an error during flush/close can indicate that data was not durably persisted. The handling policy depends on the resource's contract, but you cannot arbitrarily treat the operation as successful.

## 5. Multiple Resources: First Close Failure Is Primary If No Earlier Error Exists

With multiple resources, Java initializes **left → right** and closes **right → left**. If the `try` body does not throw and both `close()` calls fail, **the `close()` called first** produces the primary exception; the subsequent close error is suppressed.

Save as `TwoCloseFailuresDemo.java`:

```java
import java.io.IOException;

public class TwoCloseFailuresDemo {
    static class FailingResource implements AutoCloseable {
        private final String name;

        FailingResource(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            throw new IOException("close " + name + " failed");
        }
    }

    public static void main(String[] args) {
        try (FailingResource a = new FailingResource("A");
             FailingResource b = new FailingResource("B")) {
            System.out.println("body ok");
        } catch (IOException ex) {
            System.out.println("primary=" + ex.getMessage());
            System.out.println("suppressedCount=" + ex.getSuppressed().length);
            for (Throwable extra : ex.getSuppressed()) {
                System.out.println("suppressed=" + extra.getMessage());
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 TwoCloseFailuresDemo.java
java TwoCloseFailuresDemo
```

Output:

```text
open A
open B
body ok
close B
close A
primary=close B failed
suppressedCount=1
suppressed=close A failed
```

Key takeaways:

1. Both A and B initialize successfully; `body ok` is printed.
2. B is closed before A because B was declared later.
3. `close B` throws an `IOException` when no exception is pending; it becomes **primary**.
4. Java still attempts to close A; the `IOException` from `close A` is added to B's suppressed list.
5. The outer handler receives `IOException("close B failed")` along with one suppressed exception.

With three resources A, B, C closed in the order C → B → A, if only close errors occur, the first error encountered in C → B → A order is the primary exception. Do not assume "the first declared resource" determines the primary exception.

## 6. `try` Body Throws and Multiple Resources Also Throw on Close

If the `try` body has already thrown exception A, the error from each subsequent close operation is recorded in A's suppressed list, regardless of how many resources there are.

Save as `BodyAndMultipleClosesDemo.java`:

```java
import java.io.IOException;

public class BodyAndMultipleClosesDemo {
    static class Failing implements AutoCloseable {
        private final String name;

        Failing(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            throw new IOException("close " + name + " failed");
        }
    }

    public static void main(String[] args) {
        try (Failing first = new Failing("first");
             Failing second = new Failing("second");
             Failing third = new Failing("third")) {
            System.out.println("work");
            throw new IllegalArgumentException("invalid input");
        } catch (Exception ex) {
            System.out.println("primary=" + ex.getMessage());
            System.out.println("suppressedCount=" + ex.getSuppressed().length);
            for (Throwable extra : ex.getSuppressed()) {
                System.out.println("suppressed=" + extra.getMessage());
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 BodyAndMultipleClosesDemo.java
java BodyAndMultipleClosesDemo
```

Output:

```text
open first
open second
open third
work
close third
close second
close first
primary=invalid input
suppressedCount=3
suppressed=close third failed
suppressed=close second failed
suppressed=close first failed
```

The order of suppressed exceptions reflects the order in which errors were detected during closing. The fact that `close third` fails before `close first` **does not make any close error primary**, because the `try` body already established `IllegalArgumentException("invalid input")` as the primary exception.

You can see `getSuppressed().length == 0` even when an error occurred if the resources do not throw on close; do not treat `getSuppressed()` as a general-purpose business-error counter.

## 7. If a Later Resource Initialization Throws, Which Exception Is Chosen?

When a resource initializer throws an exception, the `try` body **has not executed yet**. Java still closes any previously declared resources that were already initialized successfully.

If closing those earlier resources also throws an exception, **the exception from the failed initialization** is the primary exception; any close errors that occur while rolling back initialization are suppressed onto that exception.

Save as `InitializationFailureDemo.java`:

```java
import java.io.IOException;

public class InitializationFailureDemo {
    static class Resource implements AutoCloseable {
        private final String name;

        Resource(String name, boolean failOpen) throws IOException {
            this.name = name;
            System.out.println("init " + name);
            if (failOpen) {
                throw new IOException("init " + name + " failed");
            }
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            throw new IOException("close " + name + " failed");
        }
    }

    public static void main(String[] args) {
        try (Resource a = new Resource("A", false);
             Resource b = new Resource("B", true)) {
            System.out.println("body");
        } catch (IOException ex) {
            System.out.println("primary=" + ex.getMessage());
            System.out.println("suppressedCount=" + ex.getSuppressed().length);
            for (Throwable extra : ex.getSuppressed()) {
                System.out.println("suppressed=" + extra.getMessage());
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 InitializationFailureDemo.java
java InitializationFailureDemo
```

Output:

```text
init A
init B
close A
primary=init B failed
suppressedCount=1
suppressed=close A failed
```

Notable point: resource B throws **inside its constructor**, so B's initializer never completes normally. Java does not have a successfully initialized and registered B object on which to call `B.close()`; A was initialized successfully, so A is closed. The `try` body does not run.

If B's constructor opened an internal resource and then threw before returning the object, B's constructor/factory must have its own cleanup strategy for what it allocated; the outer `try-with-resources` cannot release a resource that was never handed to it.

## 8. Not Just Errors: `return` Must Still Go Through `close()`

`return` is an abrupt completion of a statement in the Java language, but it **does not create a primary exception object**. Therefore, if `try` intends to return a value and `close()` throws an exception, **the `close()` exception is thrown instead of returning the value**.

Save as `ReturnAndCloseFailureDemo.java`:

```java
import java.io.IOException;

public class ReturnAndCloseFailureDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("close");
            throw new IOException("cleanup failed");
        }
    }

    static int calculate() throws IOException {
        try (Resource resource = new Resource()) {
            System.out.println("body");
            return 42;
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println("value=" + calculate());
        } catch (IOException ex) {
            System.out.println("caught=" + ex.getMessage());
            System.out.println("suppressedCount=" + ex.getSuppressed().length);
        }
    }
}
```

```bash
javac -encoding UTF-8 ReturnAndCloseFailureDemo.java
java ReturnAndCloseFailureDemo
```

Output:

```text
body
close
caught=cleanup failed
suppressedCount=0
```

The expression `return 42` is evaluated, but before the value reaches the caller, Java runs `close()`. It fails, so the `calculate()` call throws `IOException`; `System.out.println("value=" + calculate())` does not execute because no value is produced for string concatenation.

If `close()` completes normally, the method returns `42`. Similarly, with `break` or `continue` exiting the resource-management scope, `close()` runs before control completes its transfer; if it throws, the intended normal path is replaced by throwing the exception.

**Distinction:** when the `try` body has already thrown exception A, a `close()` error is suppressed onto A. When the `try` body only intends to `return`, there is no A to suppress onto, so the `close()` error becomes primary.

## 9. Which Exception Does a `catch` Clause on the Same Statement See?

A `try-with-resources` statement can have `catch` and `finally`:

```java
try (Resource resource = open()) {
    perform(resource);
} catch (IOException ex) {
    handleIo(ex);
} catch (RuntimeException ex) {
    handleRuntime(ex);
} finally {
    afterOperation();
}
```

This is an illustrative pattern assuming the supporting types and methods already exist. Execution order matters:

1. Initialize the resource and execute the `try` body.
2. Execute the **automatic closing** logic and determine the primary/suppressed exceptions.
3. If an exception is thrown out of the resource-management part, select **the first `catch` clause compatible with the runtime type of the primary exception**.
4. Execute the selected `catch` block, if any.
5. Execute `finally`, then complete the transfer of control.

Each suppressed exception does not trigger an additional `catch` clause. A suppressed error is **supporting information attached** to the primary object, not a separate `throw` to sibling `catch` blocks.

### Java 17+ Program: `catch` Selection Based on the Primary Exception

Save as `CatchPrimaryDemo.java`:

```java
import java.io.IOException;

public class CatchPrimaryDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("close");
            throw new IOException("close io");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("body");
            throw new IllegalArgumentException("body invalid");
        } catch (IOException ex) {
            System.out.println("io catch");
        } catch (IllegalArgumentException ex) {
            System.out.println("runtime catch=" + ex.getMessage());
            System.out.println("suppressed="
                    + ex.getSuppressed()[0].getMessage());
        } finally {
            System.out.println("finally");
        }
        System.out.println("after");
    }
}
```

```bash
javac -encoding UTF-8 CatchPrimaryDemo.java
java CatchPrimaryDemo
```

Output:

```text
body
close
runtime catch=body invalid
suppressed=close io
finally
after
```

Here `IOException("close io")` occurs during closing, but `catch (IOException)` is not selected because it was suppressed onto `IllegalArgumentException("body invalid")`. The runtime `catch` receives the **primary exception**, prints the secondary error info, and then `finally` runs.

If you remove `throw new IllegalArgumentException(...)` from the `try` body so it completes normally, the `IOException` from `close()` becomes primary and `catch (IOException)` is selected.

## 10. Comparing Manual `try-finally` and `try-with-resources`

With manual closing:

```java
try {
    throw new IllegalStateException("work failed");
} finally {
    throw new IllegalArgumentException("close failed");
}
```

This is valid illustrative code when placed in a method, but it is a **cleanup pattern to avoid**. Under `finally` rules, the new reason from `finally` replaces the prior `throw` reason. An outer handler receives `IllegalArgumentException("close failed")`, while `IllegalStateException("work failed")` is not automatically recorded as `cause` or `suppressed`.

By contrast:

```java
try (Resource resource = new Resource()) {
    throw new IllegalStateException("work failed");
}
```

This pattern makes sense when `Resource implements AutoCloseable`, `Resource.close()` can throw, and the enclosing method handles or declares the appropriate exceptions. `try-with-resources` is designed not to arbitrarily discard a `try`-body failure because of an ordinary resource-closing error.

**Do not interpret `try-with-resources` as "`finally` simply calling `close()`" in all cases.** The JLS semantics maintain a primary exception variable and call `addSuppressed` when appropriate. That is the core difference.

When designing code, prefer `try-with-resources` for resources implementing `AutoCloseable`. If additional cleanup must be done manually, check what happens when cleanup throws so it does not overwrite critical information.

## 11. `getSuppressed()`, `getCause()`, and Wrapping Exceptions at Higher Layers

A repository layer might throw a primary `IOException` with a suppressed close error. The service layer might decide to translate it into a business exception `DataLoadException` by **attaching the original exception as the cause**. Then:

```text
DataLoadException("cannot load")
   |
   +-- getCause() ---> IOException("read failed")       ← original primary
                           |
                           +-- getSuppressed()[0]
                                   |
                                   └── IOException("close failed")
```

The new exception at the service layer does not automatically copy the suppressed list onto itself. **The suppressed list remains on the original cause object**, unless code explicitly manipulates it otherwise.

Save as `WrappedPrimaryDemo.java`:

```java
import java.io.IOException;

public class WrappedPrimaryDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static class DataLoadException extends Exception {
        DataLoadException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static void repository() throws IOException {
        try (Resource resource = new Resource()) {
            throw new IOException("read failed");
        }
    }

    static void service() throws DataLoadException {
        try {
            repository();
        } catch (IOException ex) {
            throw new DataLoadException("cannot load", ex);
        }
    }

    public static void main(String[] args) {
        try {
            service();
        } catch (DataLoadException ex) {
            Throwable cause = ex.getCause();
            System.out.println("wrapper=" + ex.getMessage());
            System.out.println("wrapperSuppressed="
                    + ex.getSuppressed().length);
            System.out.println("cause=" + cause.getMessage());
            System.out.println("causeSuppressed="
                    + cause.getSuppressed()[0].getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 WrappedPrimaryDemo.java
java WrappedPrimaryDemo
```

Output:

```text
wrapper=cannot load
wrapperSuppressed=0
cause=read failed
causeSuppressed=close failed
```

This is a common way to translate exceptions across layer boundaries without losing the root cause. When printing a stack trace with `printStackTrace()` or using a logging framework that supports `Throwable`, both `cause` and `suppressed` are formatted accordingly.

Avoid doing `throw new DataLoadException(ex.getMessage(), null)` or logging a generic message and dropping `ex`: that loses the stack trace, cause, and suppressed exceptions needed for investigation.

## 12. Exception Type Checking on Close Is Still a Compile-Time Concern

`AutoCloseable.close()` is declared `throws Exception`; `Closeable.close()` is declared `throws IOException`. A concrete class may override it with narrower checked exceptions or no checked exceptions. When using `try-with-resources`, the compiler considers:

- Checked exceptions that can arise **during resource initialization**.
- Checked exceptions that can arise from the **`try` body**.
- Checked exceptions that **`close()` of the resource type** can throw.
- Exceptions handled locally by `catch` and those that can still escape and require `throws`.

Example of valid code with a concrete resource type:

```java
class SilentResource implements AutoCloseable {
    @Override
    public void close() { }
}

class TypeCheckExample {
    static void useSilent() {
        try (SilentResource r = new SilentResource()) {
            System.out.println("work");
        }
    }
}
```

This is a valid illustrative class without `main`. Because `SilentResource.close()` declares no checked exceptions, `useSilent()` does not need `throws Exception` just because the class implements `AutoCloseable`.

By contrast, with a static type reference `AutoCloseable`:

```java
static void useAsAutoCloseable(AutoCloseable resource) throws Exception {
    try (resource) {
        System.out.println("work");
    }
}
```

The second snippet is an illustrative method (Java 9+) that can be placed in a class. The parameter `resource` is not reassigned, so it is effectively final and valid in `try (resource)`. The static type `AutoCloseable` has `close() throws Exception`, so the method must handle or declare that checked exception. In Java 17, this pattern is valid.

The primary/suppressed rule is **runtime behavior**. It does not allow you to skip compile-time checked-exception obligations, even if you think a `close()` error will "only be suppressed." If the `try` body completes normally, the `close()` error can be the primary exception.

## 13. `Error`, Interrupted Cleanup, and Rare Edge Cases

`AutoCloseable.close()` can also throw unchecked exceptions. If a resource's `close()` throws a `RuntimeException` or `Error`, `try-with-resources` still determines primary/suppressed semantically according to the `Throwable` rules; however, **you should not catch `Throwable` indiscriminately just to keep the program running**. A serious `Error` can indicate that the JVM or application state is no longer suitable for recovery.

According to the `AutoCloseable` Javadoc, `close()` should avoid throwing `InterruptedException`. If it occurs during cleanup when a primary error already exists, the suppressed exception can make managing the interrupt status difficult; cleanup APIs should be designed so they do not lose thread cancellation requests.

In addition, `Throwable.addSuppressed(...)` has limitations:

- You cannot suppress **the exact same** `Throwable` instance onto itself (*self-suppression*), as that is an invalid operation.
- A `Throwable` subclass can be constructed with suppression disabled (via the appropriate constructor in a subclass). In that case, `addSuppressed(...)` does not record secondary errors in the list as usual.
- If a resource's `close()` intentionally rethrows the exact same object that is already the primary exception, automatic closing can hit a self-suppression error. Do not design around such behavior.
- If the JVM/process is terminated outside normal Java control flow, there is no guarantee that `close()` or `finally` has run.

These rare cases do not change the practical rule: **design `close()` responsibly, avoid throwing the same in-flight exception object, and always preserve the primary error context**.

## 14. How to Read Logs and Stack Traces with Suppressed Exceptions

When debugging a failure with multiple error traces:

1. Read **the type and message of the primary exception** first. It tells you which operation caused the `try-with-resources` construct to fail along the outward propagation path.
2. Inspect the **cause chain** via `getCause()` to see whether this exception was translated by another layer from a specific underlying cause.
3. Inspect `getSuppressed()` on **each important object in the cause chain**, not only on the outermost wrapper.
4. Check the order of suppressed errors. This order typically reflects the closing steps—that is, **the reverse of declaration order**.
5. Based on the resource type, determine whether a close error is merely secondary cleanup noise or could indicate that data was not safely finalized (such as a flush failure).
6. Decide on retry, rollback, or recovery according to business contracts; do not automatically retry just because the message contains the word "close".

An informative way to log errors:

```java
try (Resource resource = open()) {
    process(resource);
} catch (Exception ex) {
    logger.error("Operation failed", ex);
    throw ex;
}
```

This is an **illustrative pattern**, assuming `Resource implements AutoCloseable`, the functions and logger are defined, and the enclosing method declares `throws` matching any checked exceptions that may escape. Because the logger receives the full `ex` object, it can render the stack trace, cause, and suppressed exceptions.

Avoid logging the same full exception at every layer before rethrowing, as that creates duplicate logs. Designate a single layer responsible for final logging; intermediate layers should only add context when truly needed.

## 15. Common Misconceptions

| Misconception | What to remember instead |
| --- | --- |
| "`close()` runs later, so `close()`'s error is always the primary exception." | If the body already threw error A, A is normally primary; the close error is suppressed. |
| "If the `try` body succeeds, a `close()` error doesn't matter." | The close error can become the primary exception; the business operation may not have completed safely. |
| "If two `close()` calls fail, the resource declared first determines the primary." | If no error occurred earlier, the first `close()` to throw in **reverse closing order** determines the primary. |
| "When B fails to open, Java does not close A." | Java closes resources that were already initialized successfully before it. |
| "A `close()` error prevents Java from closing the remaining resources." | `try-with-resources` continues attempting to close the remaining resources. |
| "Each suppressed exception enters a different `catch` branch." | `catch` is selected by the primary exception; suppressed exceptions are attached metadata only. |
| "`getCause()` and `getSuppressed()` return the same array." | Cause is a causal link; suppressed is a list of additional exceptions. |
| "`return` inside `try` definitely wins over an error in `close()`." | A close error can replace the intended `return` path. |
| "When wrapping into `ServiceException`, the suppressed list is automatically copied to the wrapper." | It usually stays on the cause object; inspect cause and then suppressed. |
| "Manual `finally` has the same exception-priority logic as `try-with-resources`." | A `finally` block throwing an exception can overwrite the old error; `try-with-resources` has its own suppression mechanism. |
| "Having `getSuppressed()` means you don't need to manage resource ownership." | Ownership still determines which object is closed and whether it is closed too early or on the wrong instance. |
| "`try-with-resources` guarantees closing if the process is killed." | No; it executes along Java control flow while the JVM is still running normally. |

## 16. Step-by-Step Procedure for Analyzing a Primary Exception Problem

Given a specific `try-with-resources` snippet, analyze it in exact order:

**Step 1 — Initialization:** read resources from **left to right**. If an initializer throws, record the exception type and the list of resources already created successfully before it.

**Step 2 — `try` body:** executes only if all required resources initialize. Note whether the body completes normally, executes `return`, executes `throw`, or transfers control otherwise.

**Step 3 — Closing:** walk through the successfully initialized resources in **reverse order**. For each `close()`, determine whether it completes normally or throws an exception.

**Step 4 — Selecting primary/suppressed:** if an exception already exists from an initializer or the body, it takes precedence; otherwise, the first `close()` error becomes primary; subsequent close errors are suppressed according to the rules.

**Step 5 — Outer handling:** after automatic closing, find the first `catch` matching the **primary exception's type**, then run `finally` if present. If uncaught, the exception continues propagating.

**Step 6 — Preserving information:** when translating or logging errors, ensure `cause` and `suppressed` of the original object remain accessible; do not keep only the message.

Apply this to the following three scenarios:

```text
Scenario A:
  body        -> throw IOException("read")
  close B     -> throw IOException("close B")
  close A     -> normal
  primary     -> IOException("read")
  suppressed  -> IOException("close B")

Scenario B:
  body        -> normal
  close B     -> throw IOException("close B")
  close A     -> throw IOException("close A")
  primary     -> IOException("close B")
  suppressed  -> IOException("close A")

Scenario C:
  init A      -> succeeded
  init B      -> throw IOException("init B")
  close A     -> throw IOException("close A")
  body        -> does not run
  primary     -> IOException("init B")
  suppressed  -> IOException("close A")
```

Writing events top-to-bottom like this helps avoid confusing initialization order with closing order, confusing "last thrown" with primary, and confusing suppressed with cause.

## 17. Self-Check

**Question 1.** The `try` body throws `IOException("read")`, and `close()` throws `IOException("close")`. What is the primary exception?  
**`IOException("read")`.** The close error becomes a suppressed exception on the read error.

**Question 2.** The `try` body completes normally, and `close()` throws `IOException("flush")`. Primary exception?  
**`IOException("flush")`.** There is no earlier error to take precedence.

**Question 3.** Resources A then B are declared; both `close()` calls throw, and the body succeeds. Which error is primary?  
**The error from `B.close()`**, because B closes before A. `A.close()`'s error is suppressed.

**Question 4.** The body throws error X; `close(B)` and `close(A)` both throw. How many suppressed errors are there normally in total?  
**Two**, in the order B then A; X remains primary.

**Question 5.** Initialization of B fails, while A initialized successfully. Is A closed?  
**Yes.** If `A.close()` also throws, the error from B's initializer takes precedence as primary.

**Question 6.** `return 42` in the `try` body, and `close()` throws `IOException`. Does the method return 42 or throw `IOException`?  
**Throws `IOException`.** When closing fails, the intended value-return path is replaced.

**Question 7.** If there are `catch (IOException)` and `catch (IllegalStateException)`, the body throws `IllegalStateException` and `close()` throws `IOException`, which branch runs?  
**The `catch (IllegalStateException)` branch**, because the closing `IOException` was suppressed, not primary.

**Question 8.** A `ServiceException` wraps a primary `IOException` as its cause. Where can the close error be found?  
Usually in `serviceException.getCause().getSuppressed()`, not necessarily in `serviceException.getSuppressed()`.

**Question 9.** Do `getSuppressed()` and `getCause()` return the same information?  
**No.** Cause links the underlying causal exception; suppressed stores secondary errors from the same processing flow.

**Question 10.** Should you catch all `Throwable`s to "just keep going after a close error"?  
**No.** An error can indicate that the resource or JVM is no longer in a suitable state to continue; handling must be based on contracts and actual recoverability.

## Official References

- [Java Language Specification, Java SE 21 — §14.20.3: `try-with-resources`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.3).
- [JLS 21 — §14.20.3.1: Basic `try-with-resources` and translation to `try-catch-finally`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.3.1).
- [JLS 21 — §14.20.3.2: Extended `try-with-resources` with `catch`/`finally`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.3.2).
- [JLS 21 — §11.2: Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.2).
- [Java SE 21 API — `Throwable.addSuppressed()` and `getSuppressed()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Throwable.html).
- [Java SE 21 API — `AutoCloseable.close()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/AutoCloseable.html).

**Remember:** In `try-with-resources`, an exception already thrown during initialization or in the `try` body is normally kept as **primary**; exceptions from `close()` are **suppressed** onto it. If no error occurred yet, the first close error in **reverse closing order** becomes primary. Java automatically closes remaining resources, and `catch` then dispatches on the **primary exception**, not on each suppressed exception.
