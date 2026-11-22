# Handling Cleanup Failures While Preserving the Original Exception

## 1. When Both Primary Work and Cleanup Fail

In Java, a method often performs its primary work while also managing the resources it uses. The primary work might be reading a file, writing data, executing a query, calling a service, or processing business logic. Cleanup might be closing a stream, returning a connection, releasing a lock, stopping a session, or reclaiming temporary resources.

A tricky situation occurs when **both the primary work and the cleanup throw an exception**. For example, a file write operation fails due to an I/O error; while exiting the method, closing the stream also fails. In this case, there are two distinct pieces of information that must be preserved:

- **Primary exception**: the error from the main operation, explaining why the work in progress did not complete.
- **Cleanup exception**: the error arising when attempting to finalize or release resources, indicating that a reclamation step also failed.

If the cleanup exception replaces the primary exception, developers might only see "close failed" and not know that the real root cause was "write failed". If the cleanup error is swallowed, operators lose the information that closing or finalizing the resource had a problem.

**Design goal:** When the primary work has already failed, keep the original exception as the propagated exception and attach the cleanup exception for diagnostics. When the primary work succeeds but cleanup fails, the cleanup exception itself is usually the failure of the call.

Exception preservation is part of **state preservation**: it helps the system determine the outcome, record the incident, and handle consequences properly. However, preserving an exception **does not mean** automatically rolling back written data or restoring resources.

## 2. Why Can finally Mask the Original Exception?

A **finally** block executes when control flow leaves a **try/catch** under normal conditions, including when the **try** body throws an exception. Because of this, it is commonly used for cleanup. The problem is that **if finally throws another exception, the pending exception from try can be replaced**.

The following illustrative snippet is not a standalone Java program:

~~~java
void save() throws java.io.IOException {
    try {
        throw new java.io.IOException("write failed");
    } finally {
        throw new java.io.IOException("close failed");
    }
}
~~~

The caller receives the **close failed** error; the **write failed** error does not automatically appear in **getCause()** or **getSuppressed()**. Simply wrapping **close()** in **finally** is not enough to preserve the primary error information.

An even more dangerous variant is **return inside finally**:

~~~java
// Anti-pattern illustration; not a standalone program.
try {
    performWork();  // May throw an exception.
} finally {
    return;         // Can obscure a pending exception.
}
~~~

If finally exits via return, the pending exception can be discarded. Therefore, avoid **return** in finally and prevent unexpected cleanup errors from masking the error that needs to be reported.

Conversely, this pattern is also problematic:

~~~java
// Anti-pattern illustration; resource is already declared elsewhere.
try {
    resource.close();
} catch (Exception ignored) {
    // No evidence remains that close() failed.
}
~~~

Catching and ignoring all cleanup errors destroys diagnostic data; in some systems, it is also a sign that a connection or transaction is already in an untrusted state.

## 3. The Standard Mechanism: try-with-resources

Java has provided **try-with-resources** since Java 7. Any resource implementing **java.lang.AutoCloseable** can be declared in the parentheses of try so that Java automatically calls **close()** when exiting the block:

~~~java
// Syntax illustration; openResource() returns AutoCloseable.
try (var resource = openResource()) {
    performWork(resource);
}
~~~

When both the try body and **close()** throw an exception, the rules are:

1. Keep the exception from the try body as the **primary exception**.
2. Call close according to the resource lifecycle rules.
3. Add exceptions thrown by close to the **suppressed exceptions** list on the primary exception itself.
4. Throw the primary exception to the caller. The list of cleanup errors can be retrieved via **primary.getSuppressed()**.

If the body does not throw an error but close fails, the error from close becomes the primary exception. Java does not fabricate a dummy body exception to act as the primary.

**Try-with-resources is the preferred solution** when cleanup mainly consists of calling close on AutoCloseable resources. It avoids writing multiple manual catch/finally branches and reduces the risk of losing the original error.

### Important Lifecycle Points

- Resources in try-with-resources are closed in **reverse order of declaration**.
- If the body fails and multiple close calls also fail, the close errors are suppressed onto the body exception in order.
- If initializing the second resource fails after the first resource has already been opened, Java still attempts to close the first resource.
- If the try body is about to **return**, close is still executed before the method completes; a failed close can cause the method to throw an exception instead of returning a value.
- Try-with-resources handles calling close and preserving exceptions; it **does not guarantee** that all prior side effects are undone.

## 4. A Compilable and Runnable Java 17+ Example

The following program demonstrates four cases: both the body and two close calls fail, only close fails, finally masks the original error, and manual cleanup preserves the original error using **addSuppressed**.

Create the file **CleanupFailureDemo.java**:

~~~java
import java.io.IOException;

public class CleanupFailureDemo {
    static final class DemoResource implements AutoCloseable {
        private final String name;
        private final boolean failOnClose;

        DemoResource(String name, boolean failOnClose) {
            this.name = name;
            this.failOnClose = failOnClose;
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            if (failOnClose) {
                throw new IOException("close " + name + " failed");
            }
        }
    }

    static void badFinally() throws IOException {
        try {
            throw new IOException("operation failed");
        } finally {
            throw new IOException("cleanup failed");
        }
    }

    static void manualPreserve() throws IOException {
        DemoResource resource = new DemoResource("manual", true);
        IOException primary = null;

        try {
            throw new IOException("operation failed");
        } catch (IOException original) {
            primary = original;
            throw original;
        } finally {
            try {
                resource.close();
            } catch (IOException cleanup) {
                if (primary != null) {
                    primary.addSuppressed(cleanup);
                } else {
                    throw cleanup;
                }
            }
        }
    }

    static void printFailure(IOException failure) {
        System.out.println("primary: " + failure.getMessage());
        Throwable[] suppressed = failure.getSuppressed();
        for (int i = 0; i < suppressed.length; i++) {
            System.out.println("suppressed " + (i + 1) + ": "
                    + suppressed[i].getMessage());
        }
    }

    public static void main(String[] args) {
        System.out.println("== Work and two close failures ==");
        try (DemoResource a = new DemoResource("A", true);
             DemoResource b = new DemoResource("B", true)) {
            throw new IOException("operation failed");
        } catch (IOException failure) {
            printFailure(failure);
        }

        System.out.println("== Close failure only ==");
        try (DemoResource r = new DemoResource("single", true)) {
            System.out.println("operation succeeded");
        } catch (IOException failure) {
            printFailure(failure);
        }

        System.out.println("== Finally masks primary ==");
        try {
            badFinally();
        } catch (IOException failure) {
            printFailure(failure);
        }

        System.out.println("== Manual cleanup preserves primary ==");
        try {
            manualPreserve();
        } catch (IOException failure) {
            printFailure(failure);
        }
    }
}
~~~

Compile and run with JDK 17 or newer:

~~~bash
javac --release 17 CleanupFailureDemo.java
java CleanupFailureDemo
~~~

Stdout output verified directly with **javac --release 17** and **java**:

~~~text
== Work and two close failures ==
close B
close A
primary: operation failed
suppressed 1: close B failed
suppressed 2: close A failed
== Close failure only ==
operation succeeded
close single
primary: close single failed
== Finally masks primary ==
primary: cleanup failed
== Manual cleanup preserves primary ==
close manual
primary: operation failed
suppressed 1: close manual failed
~~~

### Execution Path Analysis

**Try body and two close calls both fail:** the body throws **IOException("operation failed")**. Upon exiting try, B is closed before A. Both close calls throw IOException; both are stored in the suppressed list of the body error. Therefore, the output still shows **primary: operation failed**, followed by **close B failed** and **close A failed**.

**Try body succeeds, close fails:** the program prints **operation succeeded** before closing single. Because close fails and there is no exception from the body, **close single failed** becomes the primary; there are no other suppressed exceptions.

**Finally masks the primary error:** badFinally throws the work error first and the cleanup error second. The exception escaping the method is **cleanup failed**. This is a counterexample of careless manual cleanup.

**Manual cleanup preserves the primary error:** manualPreserve saves the original IOException object and rethrows it. In finally, if close fails, it is added to the original exception via **addSuppressed**; the body exception continues to propagate.

The **manualPreserve example only handles the IOException failure path**: if the body can throw RuntimeException or Error, catch(IOException) will not record them; a close error thrown from finally could mask another error. Do not copy this manual pattern as a general-purpose mechanism for all Throwables. For AutoCloseable resources, **try-with-resources handles those cases much more thoroughly**.

## 5. What Is a Suppressed Exception?

Every **Throwable** object can hold a list of suppressed exceptions. The two main methods are:

- **addSuppressed(Throwable other)**: attaches a secondary error to the current Throwable.
- **getSuppressed()**: retrieves an array of attached Throwables, in the order they were added.

For example, outside a try-with-resources block:

~~~java
// Illustrative example inside a catch block.
catch (java.io.IOException failure) {
    System.err.println("Primary: " + failure);
    for (Throwable cleanup : failure.getSuppressed()) {
        System.err.println("Cleanup: " + cleanup);
    }
    throw failure;
}
~~~

The snippet above only illustrates the body of a catch block, not a standalone program; a catch must be paired with a matching try.

**Suppressed is not cause.** Suppressed describes a secondary error that occurred while another error was being handled or while finalizing resources. Cause describes the causal chain of an exception that was wrapped or translated to a different abstraction level.

| Relationship | Meaning | How to Access |
| --- | --- | --- |
| **Primary** | The main error thrown to the caller | The exception caught by the caller |
| **Cause** | The lower-level error that caused the higher-level error | **getCause()** |
| **Suppressed** | Secondary error kept alongside the primary, typically from cleanup | **getSuppressed()** |

For example, the service layer wraps an IOException into an IllegalStateException with a cause. If that IOException carries suppressed close errors, the caller must follow **getCause()** to find the suppressed exceptions on the IOException. There is no rule that automatically copies a cause's suppressed list onto the wrapper object.

~~~java
// Illustration inside a valid catch block:
catch (java.io.IOException failure) {
    throw new IllegalStateException("Unable to save data", failure);
}
~~~

This approach preserves the original error as the **cause**. Conversely, creating a new exception with only **failure.getMessage()** loses the cause chain and the original's stack trace information.

### Constraints of addSuppressed

**Throwable.addSuppressed(null)** throws NullPointerException. Attaching a Throwable to itself throws IllegalArgumentException due to self-suppression. You must never attach the same primary error to its own suppressed list. In addition, certain special Throwable classes can be constructed with suppression disabled; in that case, addSuppressed does not actually store the error. Therefore, recording suppression must respect the throwable's contract and does not replace other logging/diagnostic mechanisms in all cases.

## 6. Closing Multiple Resources in Reverse Order

Suppose there are multiple interdependent resources:

~~~java
// Illustrative example: both classes implement AutoCloseable.
try (ConnectionLike connection = openConnection();
     ReaderLike reader = openReader(connection)) {
    process(reader);
}
~~~

Java closes **reader before connection**, because reader may still need connection during its close process. If the body fails and both reader.close and connection.close fail, both are suppressed onto the primary in the order the close failures occur.

When analyzing the closing order, consider:

1. **Creation order** of resources from left to right.
2. **Closing order** from right to left.
3. **Failure path during initialization**: resources created earlier are still closed.
4. **Failure path during closing**: remaining resources are still attempted to be closed by try-with-resources.
5. **Primary preservation**: body errors or initialization errors take precedence over close errors.

A resource declared in the header that evaluates to null will not have close called on it. In API design, avoid using null to signal a valid resource when you can design the resource-opening method to return a valid object or throw an explicit exception.

### If Initializing an Intermediate Resource Fails

Consider the order: open A, then open B:

~~~text
open A: succeeds
open B: throws exception E
close A: throws exception C

Escaping exception: E
Suppressed on E: C
~~~

B was never successfully initialized, so it is not closed; A was successfully opened, so it is closed. Because E occurred earlier during resource setup, C is retained as suppressed rather than replacing E.

This is a major difference between try-with-resources and naive manual cleanup: self-managed code very easily forgets to close previously opened resources when a later resource fails.

## 7. Closeable, AutoCloseable, and Exception Types

**AutoCloseable** defines close, which may declare **throws Exception**. **java.io.Closeable** extends AutoCloseable, but its close method declares **throws IOException**. Thus, the resource type determines which checked exceptions the code must catch or declare.

Common JDK classes such as InputStream, OutputStream, Reader, Writer, and many JDBC objects support a lifecycle suitable for try-with-resources. Other APIs may throw SQLException or custom exceptions. A custom class can also implement AutoCloseable and define close behavior according to the resources it owns.

File reading example:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

// Contextual illustrative method; not a complete program file.
static String readFirstLine(Path path) throws IOException {
    try (BufferedReader reader = Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
~~~

If readLine throws an IOException and reader.close also throws an IOException, the read error remains the primary. If readLine completes but close fails, readFirstLine can throw the close error instead of returning the line that was read. A return statement inside the try body does not bypass the resource-closing process.

Since Java 9, try-with-resources syntax can use a **final or effectively final** resource variable declared before the block:

~~~java
// Illustrative example; reader is already initialized and not reassigned.
try (reader) {
    process(reader);
}
~~~

This syntax does not turn an arbitrary variable into an AutoCloseable; reader's type must still be compatible, and the variable must satisfy the final/effectively final requirement. After exiting the block, the resource has been closed, even though the reference variable remains in scope.

Do not assume that every AutoCloseable allows calling close multiple times safely. Idempotency belongs to the specific contract of each resource. Avoid manually closing the same resource inside a try-with-resources body unless there is a clear reason.

## 8. When Is Manual Cleanup Necessary?

Not all cleanup is equivalent to a single AutoCloseable.close call. You may need to roll back a transaction, restore temporary state, cancel a request, release a lock that cannot be conveniently wrapped, or perform multiple operations with dependency rules.

If you must perform manual cleanup, design it explicitly:

1. Save **primary** right where the primary work fails.
2. Attempt cleanup in an appropriate guaranteed control path, usually finally.
3. If cleanup fails and **there is no primary yet**, propagate the cleanup exception according to the contract.
4. If cleanup fails and **a primary already exists**, record it as suppressed (or via another structured observability mechanism) while keeping the primary for the caller to receive.
5. Do not swallow **Error** or an unexpected RuntimeException just to continue running as if everything succeeded.
6. If a cleanup failure leaves infrastructure in an indeterminate state, mark or discard the resource as no longer trustworthy.

Limited helper example, illustrating only how to attach a cleanup error:

~~~java
// Illustrative code: called when the caller is managing the primary Throwable.
static void closePreserving(AutoCloseable resource,
                            Throwable primary) throws Exception {
    if (resource == null) {
        return;
    }
    try {
        resource.close();
    } catch (Exception cleanup) {
        if (primary == null) {
            throw cleanup;
        }
        if (primary != cleanup) {
            primary.addSuppressed(cleanup);
        }
    }
}
~~~

This snippet is **not** a complete replacement for try-with-resources. It only catches Exception from close, not Error; it does not run the body itself, does not rethrow primary itself, and does not handle every branch of the calling code. If primary is already an Error or a RuntimeException, the outer calling code must handle preserving and rethrowing it according to the contract. Use try-with-resources whenever possible so Java handles the standard paths.

### Multi-Step Cleanup

Suppose you must close a stream, a connection, and delete a temporary file. If an earlier cleanup step throws an exception that the code does not catch, subsequent cleanup steps may never be attempted. Decide which steps are independent and should still be attempted after a failure. If a later cleanup step is dangerous when an earlier step fails, do not proceed just to collect another exception.

For multiple independent AutoCloseable resources, a try-with-resources block is usually the best choice: it attempts to close resources in the right order and collects secondary exceptions. For business-level cleanup steps that do not fit that model, you need a dedicated strategy and tests for dual-failure, triple-failure, and mid-initialization failure scenarios.

## 9. Preserving cause and suppressed When Translating Exceptions Across Layers

An API may translate a low-level IOException into a business-level exception. It is crucial **not to lose the original exception**:

~~~java
// Illustration inside an appropriate method.
try {
    storeRecord();
} catch (java.io.IOException failure) {
    throw new IllegalStateException("Store operation failed", failure);
}
~~~

The constructor accepting a cause preserves the exception tree. If the IOException has suppressed exceptions from resource.close, those suppressed exceptions remain on the IOException in the cause tree; the caller or logger can traverse the cause and inspect suppressed.

Anti-pattern:

~~~java
// Anti-pattern illustration.
catch (java.io.IOException failure) {
    throw new IllegalStateException(failure.getMessage());
}
~~~

This approach does not pass the cause; the error class, origin site, and suppressed exceptions of the original IOException are detached from the new exception. Someone reading the logs will have a hard time determining where the operation actually broke.

When adding context is needed, prefer wrapping with a constructor that takes a cause. If abstraction translation is not needed, keep and rethrow the original itself. Do not use suppressed to represent an error that is actually a cause; the two relationships have different semantics.

## 10. Logging Cleanup Failures Without Masking the Original Exception

The goal of logging is to let operators see the entire **Throwable tree**: primary, cause, suppressed, and stack trace. Simply calling **getMessage()** and printing a string usually omits critical parts.

If the logging framework has an API accepting a Throwable, you can usually pass the throwable directly:

~~~java
// Illustration with a logger supporting the error(String, Throwable) signature.
logger.error("Operation failed; cleanup may also have failed", failure);
~~~

This snippet is logger-specific and not standalone Java SE code. With custom loggers or JSON pipelines, verify that the formatter actually records cause/suppressed rather than just outputting the message. Some log collectors truncate stack traces or drop the suppressed list if misconfigured.

A full stack trace typically looks like:

~~~text
java.io.IOException: operation failed
    ... stack trace of original failure ...
    Suppressed: java.io.IOException: close B failed
        ... stack trace ...
    Suppressed: java.io.IOException: close A failed
        ... stack trace ...
~~~

This is an **illustrative format**, different from the exact stdout in the section 4 example. Specific line numbers depend on the program and how logs are rendered.

Another note: the incident-recording system itself can also fail. If a logging callback throws an exception while processing the primary, avoid letting the logging failure mask the primary information. Design the error-reporting path to be simple, properly observable, and not automatically replace a diagnostically valuable Throwable.

## 11. How Does Cleanup Relate to State Preservation?

Successful cleanup does not mean data has definitely been rolled back:

- **Closing an OutputStream** does not automatically delete bytes already written. Partial data may already be persisted, and a close error may relate to flushing or finalizing the write.
- **Closing a connection** does not implicitly confirm that all SQL operations were rolled back as the developer intended. You must understand the transaction mode and API being used.
- **Releasing a lock** frees the synchronization mechanism, but does not revert variables or collections modified while holding the lock.
- **Rollback** is a recovery operation at the transaction layer; rollback itself can fail and must be recorded.
- **Canceling a remote request** may not undo side effects if the receiving side has already processed it.

For example, a service fails while writing to a database, then calls rollback, and rollback also throws an exception. The write error must still be preserved because it explains why the transaction entered the failure path; the rollback error must be attached because it indicates the recovery state is uncertain. **Adding a rollback error to suppressed does not prove that rollback succeeded.** The application may need to discard the connection, mark the state as indeterminate, or use a dedicated recovery mechanism.

Conversely, a **commit failure** can be the primary failure of a business operation even if it happens near the end of a method. Do not equate every operation at the end with negligible cleanup. The business contract and storage mechanism determine what belongs to the primary work and what is merely resource lifecycle cleanup.

In programs with external side effects, suppressed information aids diagnostics, but cannot replace transactions, idempotency, or proper compensation mechanisms.

## 12. Checked Exceptions, RuntimeException, Error, and Interruption

The suppression rules of try-with-resources apply to **Throwable**, not just IOException. If the body throws a RuntimeException and close throws an IOException, the RuntimeException can still be the primary, while the resource-closing IOException is suppressed. If the body throws an Error, Java still applies cleanup and suppression rules; however, applications should not abuse **catch(Throwable)** to swallow serious errors.

When performing manual cleanup, understand the exact exception types the code catches:

- **catch(IOException)** misses RuntimeException and Error.
- **catch(Exception)** catches checked exceptions and RuntimeException, but does not catch Error.
- **catch(Throwable)** catches Error as well; use it only if genuinely needed for information preservation, and rethrow or handle it appropriately by nature—never silently recover as if all errors were normal.

A special case is **InterruptedException**. If code catches and decides not to rethrow InterruptedException, you should usually consider **Thread.currentThread().interrupt()** to preserve the interruption signal. However, resetting the interrupt flag depends on the API contract and thread state; it should not become a mechanical action in every catch block. When cleanup encounters an interruption, consider both the primary error and the meaning of task cancellation.

Do not assume that close can never fail just because it is in finally; nor assume by default that AutoCloseable.close is idempotent or that every close call is safe to retry. Deciding whether to retry cleanup must be based on the specific resource and the side effects of the previous call.

## 13. Testing Cleanup Failures and Dual-Failure Scenarios

A test that only checks **assertThrows(IOException.class, ...)** is not enough. Both exceptions are IOExceptions, yet the first explains the failed operation while the second only explains cleanup. If the code accidentally masks the primary, a test that only checks the exception type can still PASS.

The test suite should cover this matrix:

| Primary Work | Cleanup | Propagated Exception | Suppressed |
| --- | --- | --- | --- |
| Succeeds | Succeeds | None | None |
| Fails A | Succeeds | A | None |
| Succeeds | Fails B | B | None |
| Fails A | Fails B | A | B |
| Fails A | Both B and C fail | A | B, C in close order |
| Later resource init fails | Closing earlier resource also fails | Init error | Earlier resource close error |

For try-with-resources, a strong test should:

1. Create a specific exception instance A for the primary operation.
2. Create a specific exception instance B for close.
3. Have the try body throw the exact object A, and have close throw object B.
4. Catch from the outside and verify that the received exception **is the exact instance A** (reference comparison, not just message).
5. Verify that **getSuppressed()** contains the exact object B, with the right count and order.
6. Verify that close was called even when the body failed.
7. Also test the path where work succeeds but close fails to ensure B is propagated.

When multiple resources are involved, verify that close order is the reverse of declaration. When a constructor or resource-opening factory fails partway through, verify that previously opened resources are cleaned up. If cleanup involves real I/O or a database, add integration tests for external state; an accurate exception tree is no substitute for verifying transaction outcomes or written data.

The Java program in section 4 simulates the necessary branches using custom resources, making the results deterministic, easy to observe, and independent of real files or networks.

## 14. Common Mistakes

**Mistake 1 — finally loses the original exception.** A close call in finally can throw a new exception that masks the body error. Use try-with-resources or attach cleanup errors with addSuppressed when manual handling is required.

**Mistake 2 — swallowing all cleanup exceptions.** It becomes hard to tell whether a stream, connection, or rollback actually completed. If the contract allows ignoring a specific error, there must be a reason; avoid ignoring every Exception.

**Mistake 3 — logging only getMessage().** The message omits cause, stack trace, and suppressed exceptions. Pass the Throwable to a logger capable of displaying the exception tree.

**Mistake 4 — treating suppressed like cause.** Cause is a causal relationship between error layers; suppressed is a secondary error kept alongside the primary. Use getSuppressed to inspect cleanup errors from try-with-resources.

**Mistake 5 — thinking cleanup failures can always be ignored.** If the body succeeds but close fails, the close exception is usually the main failure of the entire call.

**Mistake 6 — closing only the last resource.** If multiple resources are opened and a later resource fails to initialize, previously opened resources must still be closed. Try-with-resources handles this path according to Java's rules.

**Mistake 7 — a cleanup helper catches only one type.** A RuntimeException or Error from the body can be masked when finally throws a checked exception. Understand all Throwable types that can arise.

**Mistake 8 — creating a new exception without passing cause.** When wrapping, always preserve the original exception in cause if it is the real root cause, so accompanying suppressed exceptions remain accessible.

**Mistake 9 — calling close twice without checking the contract.** Not every AutoCloseable is idempotent. Avoid manually closing inside the body and then letting automatic close run again unnecessarily.

**Mistake 10 — confusing error preservation with state recovery.** Suppressed can indicate that rollback or close failed, but it does not automatically revert data to its pre-operation state.

## 15. Design Checklist for Java Code

Before finalizing a method with cleanup, check:

1. **Resource type:** can AutoCloseable and try-with-resources be used?
2. **Primary failure paths:** which statements in the primary work can throw exceptions?
3. **Cleanup failure paths:** what checked, unchecked, or Error types can close/rollback/release throw?
4. **Primary:** if both steps fail, does the caller still receive the first exception from the primary work?
5. **Suppressed:** are cleanup errors attached to the primary and accessible via getSuppressed?
6. **Close-only:** if the primary work succeeds but cleanup fails, does the caller see the cleanup error according to the contract?
7. **Multiple resources:** have closing order, mid-initialization failure, and subsequent cleanup failures been considered?
8. **Logs:** do they preserve cause, suppressed, and stack trace while protecting sensitive information?
9. **State:** if cleanup or rollback fails, does the system need to mark the resource as no longer trustworthy?
10. **Tests:** do tests trigger dual failures and verify primary identity and suppressed contents?

**Remember:** For AutoCloseable resources, **try-with-resources** is the standard way to perform cleanup while preserving primary work errors. If both the try body and close fail, the body error is the **primary**, and close errors go into **suppressed**. When manual cleanup is required, proactively protect the original exception, retain secondary error details, and clearly determine data/resource state after the failure path.