# Preserving Both Primary and Cleanup Failures During Manual Resource Management in Java

## 1. Learning Objectives

When an operation fails, a program may need to **clean up resources** such as streams, files, connections, locks, or temporary state. If cleanup also throws an exception, you have **two important pieces of failure information**: the error that caused the work to fail initially and the error that occurred during cleanup.

A seemingly correct `finally` block can cause a cleanup failure to **mask the primary failure**:

```java
try {
    doWork();        // Throws IOException("work failed").
} finally {
    resource.close(); // Also throws IOException("close failed").
}
```

This is an **illustrative snippet** that depends on an existing `doWork()` and `resource`. If both lines throw, the exception exiting `finally` can replace the exception propagating from `try`; the caller directly observes only the `close failed` error, while `work failed` can be lost from the diagnostic chain.

To preserve both, prefer `try-with-resources` when appropriate. If you must manage resources manually, identify the **primary exception** and attach cleanup failures to it via `Throwable.addSuppressed(...)`. When the work succeeds but cleanup fails, **the cleanup failure must be propagated or handled**, rather than silently ignored.

After this lesson, you will be able to:

- Distinguish between primary failure, cleanup failure, `cause`, and `suppressed`.
- Explain why a plain `finally { close(); }` can mask a pending exception.
- Write a correct manual cleanup pattern for both the success path and the failure path.
- Preserve ordering when multiple resources are closed; continue attempting to close remaining resources if one `close()` fails.
- Properly handle failures when **initializing a second resource** or **returning early**.
- Avoid missing `RuntimeException`/`Error` when catching only `IOException`; understand the limits of `catch (Throwable)`.
- Preserve stack traces, cause, and suppressed exceptions rather than copying only messages.
- Know when to use `try-with-resources` and when manual cleanup is genuinely warranted.

Examples compile and run with Java 17+, have no filesystem or network dependencies, and produce deterministic `stdout`.

## 2. Distinguishing Primary Failures from Cleanup Failures

Suppose a data-sending operation does two things:

1. `writeData()` writes data and fails: `IOException("write failed")`.
2. When finishing, `close()` also fails: `IOException("close failed")`.

Both errors matter, but they do not have the same role:

```text
operation starts
      |
      v
writeData() throws IOException("write failed")
      |
      |  primary failure
      v
cleanup: close() throws IOException("close failed")
      |
      |  suppressed failure
      v
Caller receives IOException("write failed")
  + getSuppressed()[0] = IOException("close failed")
```

The **primary failure** is the original reason the unit of work did not complete. A **cleanup failure** is a subsequent failure while releasing resources. Java provides `Throwable.addSuppressed(Throwable)` to associate a cleanup failure with the primary failure without replacing it.

Key points to understand:

- `primary.addSuppressed(cleanup)` **does not throw** `cleanup`; it records the additional failure on the `primary` object.
- `primary.getSuppressed()` returns a `Throwable[]` array containing the recorded failures.
- `getCause()` represents a causal relationship when one exception is wrapped by another; it is **not synonymous** with `getSuppressed()`.
- If the work succeeds but cleanup fails, the cleanup failure typically becomes the **primary**, because there was no prior primary failure.
- "Suppressed" means **it does not replace the primary**, not "unimportant".

Decision table:

| Work | Cleanup | Observed Result |
| --- | --- | --- |
| Succeeds | Succeeds | Completes normally |
| Fails with A | Succeeds | Throws A |
| Succeeds | Fails with B | Throws B |
| Fails with A | Fails with B | Throws A, with B attached via `addSuppressed` |

This is the original error-preservation policy that `try-with-resources` provides for `AutoCloseable` resources.

## 3. Why a Manual `finally` Can Lose the First Error

Java executes `finally` when exiting `try` via normal completion, `return`, or an exception. If `finally` itself completes abruptly with a new exception, the abrupt-completion reason from `try` can be **replaced**.

Create the file **`LosingPrimaryDemo.java`**:

```java
import java.io.IOException;

public class LosingPrimaryDemo {
    static void run() throws IOException {
        try {
            throw new IOException("work failed");
        } finally {
            throw new IOException("cleanup failed");
        }
    }

    public static void main(String[] args) {
        try {
            run();
        } catch (IOException failure) {
            System.out.println("observed=" + failure.getMessage());
            System.out.println("suppressed="
                    + failure.getSuppressed().length);
        }
    }
}
```

Compile/run:

```bash
javac LosingPrimaryDemo.java
java LosingPrimaryDemo
```

`stdout`:

```text
observed=cleanup failed
suppressed=0
```

Mechanism:

1. `try` throws `IOException("work failed")`.
2. Before that exception escapes, `finally` runs.
3. `finally` throws `IOException("cleanup failed")`.
4. The second exception becomes the observed exception; the work failure is not automatically attached as `suppressed`.
5. `getSuppressed().length` of the new exception is 0 in this example.

Do not try to "fix" this by putting a `return` inside `finally`: `return` can also **completely swallow a pending exception**. A `finally` block dedicated to cleanup should not unexpectedly alter the exit reason.

### Why Catching and Only Logging Cleanup Is Also Insufficient

Consider this style:

```java
try {
    doWork();
} finally {
    try {
        resource.close();
    } catch (IOException cleanupFailure) {
        System.err.println(cleanupFailure.getMessage());
    }
}
```

This is an **illustrative snippet**. It prevents the close failure from replacing the `doWork()` failure, but it can **violate the contract by ignoring close failures**: if the work succeeds and `close()` fails, the method can still complete normally. For write streams, a `close`/`flush` failure can be a serious error indicating data was not safely written out.

To preserve both errors in a structured way, you must distinguish **whether a primary already exists**. If it does, attach the cleanup failure; if not, the cleanup failure becomes the reported error.

## 4. `addSuppressed` and `getSuppressed` in the Manual Management Pattern

The API on `java.lang.Throwable`:

```java
primary.addSuppressed(cleanupFailure);
Throwable[] extras = primary.getSuppressed();
```

This is a **code snippet** assuming two existing `Throwable` variables.

Rules to know:

- `addSuppressed` **adds a `Throwable` object** to the receiver error.
- You must not pass `null` (causes `NullPointerException`) or the primary object itself to `primary.addSuppressed(primary)` (causes `IllegalArgumentException`).
- For a normally constructed exception, suppression is enabled by default. A specialized throwable class can disable suppression via the appropriate protected constructor, in which case `getSuppressed()` remains an empty array.
- `getSuppressed()` never returns `null`. The returned array is a copy, though it contains references to the attached `Throwable` objects.
- Attaching a suppressed exception does not `throw` the primary error by itself. You still must **rethrow the primary**, return a failure status, or handle it according to the contract.
- Do not add a cleanup exception to the primary multiple times if `try-with-resources` has already recorded it automatically.
- A suppressed exception can also have its own `cause` and suppressed exceptions; do not read only the primary's message and conclude there are no other errors.

### Core Algorithm Pattern

```text
primary = null
try to perform work
    if work fails:
        primary = that failure

try to clean up
    if cleanup fails:
        if primary is not set:
            primary = cleanup failure
        else:
            attach cleanup failure as suppressed on primary

if primary exists:
    throw primary or report failure per contract
```

This is **pseudocode**, not directly runnable Java code. The key difference compared to a plain `finally` is **preventing a cleanup exception from accidentally replacing the primary**.

## 5. Complete Java Example: Managing One Resource Across Four Scenarios

Create the file **`ManualCleanupDemo.java`**:

```java
import java.io.IOException;

public class ManualCleanupDemo {
    static class TrackedResource implements AutoCloseable {
        private final boolean closeFails;

        TrackedResource(boolean closeFails) {
            this.closeFails = closeFails;
        }

        void work(boolean fail) throws IOException {
            if (fail) {
                throw new IOException("work failed");
            }
        }

        @Override
        public void close() throws IOException {
            System.out.println("closing");
            if (closeFails) {
                throw new IOException("close failed");
            }
        }
    }

    static void execute(boolean workFails, boolean closeFails)
            throws IOException {
        TrackedResource resource = new TrackedResource(closeFails);
        Throwable primary = null;

        try {
            resource.work(workFails);
        } catch (Throwable failure) {
            primary = failure;
            throw failure;
        } finally {
            if (primary != null) {
                try {
                    resource.close();
                } catch (Throwable cleanup) {
                    if (cleanup != primary) {
                        primary.addSuppressed(cleanup);
                    }
                }
            } else {
                resource.close();
            }
        }
    }

    static void show(String label, boolean workFails,
                     boolean closeFails) {
        System.out.println("-- " + label + " --");
        try {
            execute(workFails, closeFails);
            System.out.println("success");
        } catch (IOException failure) {
            System.out.println("primary=" + failure.getMessage());
            for (Throwable extra : failure.getSuppressed()) {
                System.out.println("suppressed=" + extra.getMessage());
            }
        }
    }

    public static void main(String[] args) {
        show("both ok", false, false);
        show("work only", true, false);
        show("close only", false, true);
        show("both fail", true, true);
    }
}
```

```bash
javac ManualCleanupDemo.java
java ManualCleanupDemo
```

Exact `stdout`:

```text
-- both ok --
closing
success
-- work only --
closing
primary=work failed
-- close only --
closing
primary=close failed
-- both fail --
closing
primary=work failed
suppressed=close failed
```

**Each branch of `execute`:**

1. **Both succeed:** `work()` completes, `primary` remains null; `finally` calls `close()` successfully; the method finishes normally.
2. **Only work fails:** `catch (Throwable failure)` records the primary failure and rethrows it. `finally` closes successfully; the original `IOException` continues to propagate.
3. **Only close fails:** there is no primary yet, so `resource.close()` is called in the `else` branch and throws `IOException("close failed")` as the primary failure.
4. **Both fail:** the primary is the `IOException("work failed")` instance itself. In the cleanup branch, the `IOException` from `close()` is caught and added to `primary` via `addSuppressed`. `finally` completes normally, so Java continues throwing the **original primary object** along with its suppressed list.

### Why Does `catch (Throwable)` Here Still Compile with `throws IOException`?

This is the **precise rethrow** mechanism (Java 7+). The `catch` parameter `failure` is not reassigned, so the compiler can rely on the checked exceptions that `try` can actually throw. In the example, `resource.work(...)` declares `IOException`; unchecked exceptions can be thrown without adding them to `throws`. Therefore, `throw failure;` does not force the signature of `execute` to declare `throws Throwable`.

This snippet intentionally uses `catch (Throwable)` **inside the failure-preservation boundary** so it does not miss attaching a cleanup failure to a `RuntimeException` or `Error` primary. It **does not mean** an application should catch and recover from every `Error`. The `throw failure;` statement propagates the original error outward; the code does not attempt to continue business logic after the failure.

Be even more cautious in production:

- If a serious `Error` occurs (for example, out of memory), creating suppressed exceptions, logging, or cleanup may also be unsafe or fail.
- Some programs prefer a more specific type to narrow what is caught. However, catching only `IOException` will not preserve the suppressed policy for an unexpected `RuntimeException` or `Error` in the body.
- General-purpose code must account for **all checked exceptions** that the work and `close()` can throw, rather than hardcoding the example's `IOException`.
- `try-with-resources` already handles this logic and is usually easier to verify.

### Why Check `cleanup != primary`?

`addSuppressed` forbids a `Throwable` from suppressing itself. Although rare, a custom resource could throw **the exact same `Throwable` instance that is already the primary**. In the manual pattern, `if (cleanup != primary)` avoids creating a new `IllegalArgumentException` due to self-suppression, preventing it from accidentally masking the original error.

**Do not assume** this pattern always reproduces every bytecode detail of `try-with-resources`. This is an **intentional** error-preservation policy for the example; the JLS defines the formal semantics of TWR, and when the same object is thrown in unusual scenarios, self-suppression handling in manual code must be designed explicitly.

## 6. Minimalist Pattern When Only `IOException` Exists: Know Its Limits

If an API is certain it only wants to handle checked I/O errors and does not need to fully emulate unchecked cases, you may see code like this:

```java
IOException primary = null;
try {
    performIo();
} catch (IOException failure) {
    primary = failure;
} finally {
    try {
        resource.close();
    } catch (IOException cleanup) {
        if (primary == null) {
            primary = cleanup;
        } else if (primary != cleanup) {
            primary.addSuppressed(cleanup);
        }
    }
}
if (primary != null) {
    throw primary;
}
```

This is an **illustrative code snippet** inside a method declaring `throws IOException`, assuming compatible `performIo()` and `resource`. It demonstrates how to combine a primary I/O failure and a cleanup I/O failure; however, it is **not a general-purpose version safe for all `Throwable`s**.

**Dangerous limitation:** if `performIo()` throws a `RuntimeException` or `Error` that `catch (IOException)` does not catch, the `finally` block still runs. If `close()` throws an `IOException`, the cleanup handler catches that `IOException` and assigns it to `primary` (which is still null). Because control flow is exiting due to the unchecked error, the `if (primary != null)` check **after `finally` does not execute**, and the cleanup exception is never attached to the unchecked primary. The work failure still propagates, but you have lost the cleanup diagnostic.

If the requirement is to **preserve both the primary failure and the cleanup failure regardless of which branch the primary comes from**, use the `catch (Throwable)`-and-rethrow pattern (within an appropriate scope), or `try-with-resources`.

Do not present this minimalist pattern as a complete replacement for TWR.

## 7. `AutoCloseable` Resources and Checked Exceptions

`AutoCloseable.close()` declares `throws Exception`; implementations may narrow the exception type when overriding, such as `Closeable.close() throws IOException` or a closing class that throws no checked exceptions.

When writing manual cleanup, the **static type** of the resource affects catch/declare obligations:

```java
AutoCloseable resource = obtainResource();
try {
    useResource(resource);
} finally {
    resource.close(); // May throw Exception per AutoCloseable.
}
```

This is an illustrative snippet. The enclosing method must handle or declare `Exception`, unless structured otherwise. You cannot assume every `AutoCloseable` throws only `IOException`.

By contrast, in `ManualCleanupDemo`, the resource type is `TrackedResource` with `close() throws IOException`, so `execute` only needs to declare checked `IOException`.

A few notes:

- `close()` can throw unchecked exceptions even if its signature lists only checked exceptions; check the implementation's contract.
- `close()` can have side effects and is not necessarily idempotent for every `AutoCloseable`.
- Do not use `catch (Exception)` and return a success result if a cleanup failure is significant for the data.
- `ThreadDeath` and serious `Error`s should not become default recovery conditions; suppression only preserves error information while still propagating the primary outward.

## 8. Managing **Multiple** Resources Manually: Close All and Preserve Order

When you have two independent resources, good cleanup usually attempts to close both in the reverse order of how they were acquired or successfully initialized. A simple `finally` like the following is **problematic**:

```java
finally {
    second.close();
    first.close();
}
```

If `second.close()` throws, Java skips `first.close()`. Consequence: the first resource can leak. Moreover, the second close failure can mask an error from the body.

A controlled pattern is:

1. Keep a `Throwable primary` variable representing the initial failure (if any).
2. Close `second`; if it fails, add it to `primary` or make it `primary` if none exists yet.
3. **Regardless of whether step 2 failed**, proceed to close `first`.
4. Record any subsequent failure as suppressed on the current `primary`.
5. After cleanup, throw `primary` or return normally if no failure occurred.

This is also the intuitive mechanism behind `try-with-resources` when multiple resources are involved.

### Runnable Program: Multiple Close Calls Failing

Create the file **`ManualMultipleResourcesDemo.java`**:

```java
import java.io.IOException;

public class ManualMultipleResourcesDemo {
    static class Resource implements AutoCloseable {
        private final String name;
        private final boolean failOnClose;

        Resource(String name, boolean failOnClose) {
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

    static Throwable closeKeepingPrimary(
            Resource resource, Throwable primary) {
        if (resource == null) {
            return primary;
        }

        try {
            resource.close();
        } catch (Throwable cleanup) {
            if (primary == null) {
                return cleanup;
            }
            if (cleanup != primary) {
                primary.addSuppressed(cleanup);
            }
        }
        return primary;
    }

    static void execute(boolean failBody) throws Throwable {
        Resource first = new Resource("first", true);
        Resource second = new Resource("second", true);

        Throwable primary = null;
        try {
            System.out.println("body");
            if (failBody) {
                throw new IOException("body failed");
            }
        } catch (Throwable failure) {
            primary = failure;
        } finally {
            primary = closeKeepingPrimary(second, primary);
            primary = closeKeepingPrimary(first, primary);
        }

        if (primary != null) {
            throw primary;
        }
    }

    public static void main(String[] args) {
        for (boolean failBody : new boolean[] {true, false}) {
            System.out.println("-- failBody=" + failBody + " --");
            try {
                execute(failBody);
            } catch (Throwable failure) {
                System.out.println("primary=" + failure.getMessage());
                for (Throwable extra : failure.getSuppressed()) {
                    System.out.println("suppressed=" + extra.getMessage());
                }
            }
        }
    }
}
```

```bash
javac ManualMultipleResourcesDemo.java
java ManualMultipleResourcesDemo
```

`stdout`:

```text
-- failBody=true --
body
close second
close first
primary=body failed
suppressed=close second failed
suppressed=close first failed
-- failBody=false --
body
close second
close first
primary=close second failed
suppressed=close first failed
```

In the `failBody=true` case, the failure from the body already exists. Both close failures become suppressed in closing order: `second` first, then `first`.

In the `failBody=false` case, the first close call to fail is `second.close()`. Because there is no primary yet, the second resource's close failure chronologically becomes the primary; the failure from `first.close()` is attached to it. Both resources are still attempted to be closed even when `second.close()` throws.

**Why does the example declare `throws Throwable`?** This is a **general-purpose learning model** that needs to propagate the exact primary object whether it is a checked exception, `RuntimeException`, or `Error`. In production APIs, `throws Throwable` is usually too broad. You can narrow the signature to the actual error types, use precise rethrow, or write resource-management helpers parameterized by generic exception types, but you should not sacrifice correctness just to drop a keyword. If you use `try-with-resources` with concrete resource types, the compiler usually checks the valid checked exceptions for your API much better.

### Self-Suppression and Duplicate Suppressed Exceptions

The helper checks `cleanup != primary` because you cannot suppress the same object onto itself. If a resource repeatedly throws **the same cleanup object that was already attached** in multiple places, `addSuppressed` does not deduplicate it; closing and ownership management must prevent accidentally adding duplicate errors.

In real code, when cleanup can mutate the state of multiple components, you must decide whether to keep attempting cleanup after certain serious `Error`s. The pattern above reflects a clear error-collection policy, but it does not promise recovery from every JVM failure.

## 9. Failures During Resource **Initialization**

An easily missed case is a failure occurring **before entering the final `try` block**:

```java
Resource first = openFirst();   // Succeeds.
Resource second = openSecond(); // Throws IOException.
try {
    doWork(first, second);
} finally {
    second.close();
    first.close();
}
```

This is an **intentionally flawed code snippet**: if `openSecond()` throws, Java has not entered `try/finally`, so `first` is not cleaned up by this block.

A better structure is to start the protection scope **immediately after taking ownership** of `first`. If you must use manual cleanup, initialize `second` in an unacquired state or scope, and ensure `first` is closed even if creating `second` fails.

### Runnable Example: Second Resource Initialization Fails

Create the file **`InitializationCleanupDemo.java`**:

```java
import java.io.IOException;

public class InitializationCleanupDemo {
    static class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            throw new IOException(name + " close failed");
        }
    }

    static Resource openSecond() throws IOException {
        throw new IOException("open second failed");
    }

    static void run() throws IOException {
        Resource first = new Resource("first");
        Throwable primary = null;

        try {
            Resource second = openSecond();
            try {
                System.out.println(second);
            } finally {
                second.close();
            }
        } catch (Throwable failure) {
            primary = failure;
            throw failure;
        } finally {
            if (primary != null) {
                try {
                    first.close();
                } catch (Throwable cleanup) {
                    if (cleanup != primary) {
                        primary.addSuppressed(cleanup);
                    }
                }
            } else {
                first.close();
            }
        }
    }

    public static void main(String[] args) {
        try {
            run();
        } catch (IOException failure) {
            System.out.println("primary=" + failure.getMessage());
            for (Throwable extra : failure.getSuppressed()) {
                System.out.println("suppressed=" + extra.getMessage());
            }
        }
    }
}
```

```bash
javac InitializationCleanupDemo.java
java InitializationCleanupDemo
```

`stdout`:

```text
close first
primary=open second failed
suppressed=first close failed
```

Analysis:

1. `first` is created successfully and owned by `run()`.
2. `openSecond()` throws `IOException("open second failed")`.
3. `second` is not initialized, so the inner `try/finally` block **never starts**.
4. The outer scope's `catch (Throwable)` keeps the initialization failure as primary and rethrows it.
5. The outer `finally` closes `first`; that close also fails and is attached to the primary.
6. The caller sees the initialization failure reason along with the cleanup failure of the previously opened resource.

In real code, the structure is much simpler if you can use `try-with-resources`:

```java
try (Resource first = openFirst();
     Resource second = openSecond()) {
    doWork(first, second);
}
```

This is an **illustrative snippet**. When initializing the second resource fails in the header, Java automatically closes the first successfully initialized resource and manages any close failure as suppressed.

## 10. `return` Inside `try` and `close()` Failures on Return

A method can prepare its return value before running `finally`. If cleanup throws an exception, the call **may fail to return a value** even though the `return` expression has already been evaluated.

Example:

```java
static String calculate() throws IOException {
    Resource resource = open();
    try {
        return "ok";
    } finally {
        resource.close(); // May throw IOException.
    }
}
```

This is an illustrative snippet, requiring `Resource` and `open()` to be defined. If `close()` fails, the close error escapes and **replaces the intended return value**. Because the body only had `return "ok"`, there was no work exception to preserve; the close failure becomes the primary. That matches the policy of "do not report success if cleanup fails."

If an expression `return compute();` throws an exception itself, then the primary arises while evaluating the expression. Cleanup must preserve that error and attach any close failure as suppressed if one occurs, instead of replacing the original cause.

**Do not put `return` in `finally`** to try to preserve a result: it can mask both work failures and cleanup failures. For value-returning APIs, complete cleanup before deciding success, or use `try-with-resources` so the language does the right thing.

## 11. Resources That Cannot Be Closed Twice and Resource Ownership

Exception preservation cannot be separated from **resource ownership**.

- If a method **opens a stream itself** and does not transfer ownership outward, it is usually responsible for closing it.
- If a method only **borrows** an `InputStream` or `Connection` from its caller, calling `close()` itself can be wrong even if the suppressed-exception code is exact.
- If returning an open stream to the caller, the method must not close the stream before returning; the caller assumes cleanup responsibility after ownership is transferred.
- If multiple wrappers manage the same delegate, closing a wrapper may close the delegate and lead to a **double-close**. Some APIs allow repeated closes, but `AutoCloseable` does not guarantee that every implementation is idempotent.
- With a JDBC pool, `Connection.close()` may mean returning a logical handle to the pool; you must consider the transaction scope or which caller holds management responsibility.

**A cleanup failure on a resource not currently owned** is the consequence of a wrong closing decision, not an issue you can "fix" merely with `addSuppressed()`.

When writing manual cleanup code, clearly document which objects have been successfully initialized and who has the right to close them before designing exception preservation.

## 12. Difference Between `cause` and `suppressed` When Wrapping Errors

Sometimes the application layer needs to translate an `IOException` into a domain exception. **Keep the original object itself** as the cause; any cleanup failures attached to it will remain intact:

```java
try {
    lowLevelOperation();
} catch (IOException original) {
    throw new IllegalStateException("Import failed", original);
}
```

This is an illustrative snippet; `lowLevelOperation()` must be declared appropriately.

If `original.getSuppressed()` contains a stream-closing failure, the caller can observe:

```text
IllegalStateException: Import failed     [wrapper]
    |
    +-- getCause() -> IOException        [lower-level primary]
                          |
                          +-- getSuppressed() -> close failure
```

There is no need to manually copy every suppressed exception from the cause to the wrapper if you just want to **preserve error information**. The `(message, cause)` constructor already stores the original object along with its suppressed list. If you manually copy each suppressed exception and attach them to the wrapper as well, logs may contain duplicate information or misrepresent the error relationship.

Cases for `cause` and `suppressed`:

| API | Purpose |
| --- | --- |
| `new DomainException("...", original)` | Wraps an error, preserving the causal link to the original error |
| `primary.addSuppressed(cleanup)` | Attaches an additional cleanup failure without changing the primary |
| `wrapper.getCause()` | Reads the cause of the wrapper |
| `primary.getSuppressed()` | Reads secondary errors attached directly to the primary |
| `printStackTrace()` | Displays the stack trace, cause, and suppressed exceptions if present |

### Runnable Example: Manually Wrapping Errors While Preserving Suppressed

Create the file **`WrappedManualCleanupDemo.java`**:

```java
import java.io.IOException;

public class WrappedManualCleanupDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("cleanup failed");
        }
    }

    static class ImportException extends Exception {
        ImportException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static void importData() throws ImportException {
        Resource resource = new Resource();
        IOException primary = null;

        try {
            throw new IOException("read failed");
        } catch (IOException failure) {
            primary = failure;
        } finally {
            try {
                resource.close();
            } catch (IOException cleanup) {
                if (primary == null) {
                    primary = cleanup;
                } else if (primary != cleanup) {
                    primary.addSuppressed(cleanup);
                }
            }
        }

        if (primary != null) {
            throw new ImportException("cannot import", primary);
        }
    }

    public static void main(String[] args) {
        try {
            importData();
        } catch (ImportException failure) {
            System.out.println("outer=" + failure.getMessage());
            System.out.println("cause="
                    + failure.getCause().getMessage());
            System.out.println("suppressed="
                    + failure.getCause().getSuppressed()[0].getMessage());
        }
    }
}
```

```bash
javac WrappedManualCleanupDemo.java
java WrappedManualCleanupDemo
```

`stdout`:

```text
outer=cannot import
cause=read failed
suppressed=cleanup failed
```

Here the code intentionally creates only **checked `IOException`s** in `try` and `close`, which is enough to illustrate that the wrapper preserves a cause carrying a suppressed exception. It is not a general-purpose template for all unchecked exceptions like the pattern in Section 5. When writing a general-purpose helper, preserve cases where the body throws `RuntimeException`/`Error` as well.

## 13. Comparing Manual Cleanup with `try-with-resources`

One goal of `try-with-resources` (Java 7+) is to avoid rewriting complex primary/suppressed preservation logic.

### Manual

```java
Resource resource = acquire();
Throwable primary = null;
try {
    work(resource);
} catch (Throwable failure) {
    primary = failure;
    throw failure;
} finally {
    if (primary != null) {
        try {
            resource.close();
        } catch (Throwable cleanup) {
            if (cleanup != primary) {
                primary.addSuppressed(cleanup);
            }
        }
    } else {
        resource.close();
    }
}
```

This is a **conceptual code snippet**; the enclosing method must handle or declare the checked exceptions of `acquire`, `work`, and `close`, while following precise rethrow rules if `catch (Throwable)` is used. The code must cover all resource acquisition paths, especially if multiple initialization steps can fail.

### TWR

```java
try (Resource resource = acquire()) {
    work(resource);
}
```

This is also an **illustrative snippet**. If the resource implements `AutoCloseable` and the scope owns closing it, TWR guarantees cleanup upon leaving the scope, keeps the body failure as primary, and records close failures as suppressed per JLS rules.

| Criterion | Manual Cleanup | `try-with-resources` |
| --- | --- | --- |
| Minimal boilerplate | No | Yes |
| Closes on `return`/exception | Must be structured correctly by hand | Managed by the language |
| Preserves body and close errors | Must catch, keep, and `addSuppressed` properly | Automatic in standard cases |
| Multiple resources | Must ensure all close, in the right order | Closes in reverse header order |
| Later resource fails initialization | Must protect already-created resources | Automatically closes previously managed resources |
| Checked exception checking | Must match each method's signature | Compiler infers from resources and body |
| Cleanup not modeled by `AutoCloseable` | May be needed | Needs an adapter or additional mechanism |
| Resource ownership | Must be considered | **Still must be considered** |

Use manual cleanup when there is a real need: legacy APIs that only have custom release methods, multi-step rollback requiring specialized handling, or resources that do not implement `AutoCloseable` where an adapter is unsuitable. Do not choose manual cleanup just for "more control" while overlooking primary/suppressed preservation.

## 14. When Cleanup Is Not Just `close()`

A transaction may have multiple undo steps: rollback, deleting temporary files, releasing locks. Not every step fits mechanically into `try-with-resources`.

Pseudocode example:

```text
primary = work failure (if any)
if work failed:
    try rollback
        if rollback also fails: addSuppressed to primary
try deleting temporary file
    if it fails: addSuppressed to primary; or become primary if none yet
try releasing remaining resources
    if it fails: record similarly
throw primary or complete normally
```

This is **policy-describing pseudocode**. In real applications, rollback only needs to run conditionally on a transaction, whereas cleanup of mandatory resources is still required on both success and failure paths.

### Do Not Try to Keep Using Failed State

Recording a suppressed exception does not make rollback succeed, fix data, restore a connection, or release a resource for you. If a cleanup step fails, the resource may remain in an indeterminate state. The system needs an observability/remediation policy: log the error alongside the primary, mark the job failed, cancel the scope, or require intervention depending on severity.

### Do Not Use a Cleanup Failure as the `cause` of an Earlier Work Failure

If a write failure occurred **first**, and a close failure happened afterward, the close failure is not what caused the write failure to happen. Setting the close failure as the `cause` of the work failure usually misrepresents causality; using `suppressed` is more accurate.

## 15. Less Common Cases Worth Knowing

### 15.1. Suppression Can Be Disabled

A custom exception can call the protected constructor of `Throwable`/`Exception` with `enableSuppression=false`. When that happens, `primary.addSuppressed(cleanup)` does not record additional errors, and `primary.getSuppressed()` returns an empty array.

In most applications, keeping suppression enabled is the right choice. Do not claim that `addSuppressed` is guaranteed to always store secondary errors for every custom `Throwable`.

### 15.2. The Exception from `close()` Can Be the Same Object as Primary

If **the exact same `Throwable` instance** is rethrown from `close()`, calling `addSuppressed` on that same object causes self-suppression. The manual pattern in this lesson avoids that via the reference comparison `cleanup != primary`. If you need a different policy, you must build an appropriate error-representation mechanism rather than removing the check and letting the new error mask the primary.

### 15.3. `finally` Is Not Guaranteed on Forced JVM Termination

`finally` and TWR operate along normal Java execution paths. They are not guaranteed to run when the JVM is forcibly terminated, `Runtime.halt` is called, or the process crashes outside the normal exception model. Do not rely solely on cleanup to maintain data integrity when power-loss resilience is required.

### 15.4. `close()` Can Also Be an Important Business Operation

A buffered output stream may flush on close. If closing fails, do not print "saved successfully" or proceed as if the data were durable. Sometimes **the cleanup failure is the primary**, and that is the right behavior if the preceding work did not fail.

### 15.5. Logging Error Details Without Losing Structure

`System.err.println(failure.getMessage())` does not display the cause or suppressed exceptions. When analysis is needed, use `failure.printStackTrace()` or a logging framework that accepts the **`Throwable` object**. Avoid printing sensitive stack traces to end users and avoid logging the same error repeatedly at every layer.

## 16. Common Mistakes and Misconceptions

**"`finally { resource.close(); }` always preserves the original error."** False. If `close` throws, the close exception can replace the exception from `work`.

**"Catching the close error and doing nothing is safe."** Not necessarily. If `work` succeeds and `close` fails, you may falsely report success and lose track of a flush/close failure.

**"`addSuppressed` throws the primary by itself."** False. It only records a secondary error on the primary object; your code still has to handle or propagate the error per contract.

**"A close error is always suppressed."** False. If there is no prior primary, the close error becomes the primary.

**"Catching only `IOException` in `work` is enough to save every primary."** False. `work` can still throw a `RuntimeException` or `Error`, which must be accounted for when designing a general-purpose cleanup pattern.

**"Once the second resource's `close()` is called, the first resource is guaranteed to be closed too."** False in manual cleanup using two consecutive calls if the first call throws an uncaught exception.

**"Two resources must be closed from left to right."** Not the TWR rule; TWR closes in reverse header order. When managing manually, choose the order based on actual dependencies, typically closing in reverse order of ownership/initialization.

**"If creating the second resource fails, a `finally` written afterward will still always close the first resource."** False. If execution has not entered the `try` block, its `finally` block does not run.

**"Wrapping an exception with just a message is enough."** False. You must keep the primary object itself as the `cause` to preserve stack traces and suppressed exceptions.

**"`getSuppressed()` returns null when empty."** False. It returns an empty array.

**"You can do `primary.addSuppressed(primary)`."** False. Java rejects direct self-suppression.

**"If there are no suppressed exceptions, there was definitely no cleanup failure."** Not certain. Cleanup may not have run, the error may have been ignored, or suppression on the primary may have been disabled.

**"Every `AutoCloseable.close()` throws only `IOException`."** False. `AutoCloseable.close()` declares `throws Exception`; concrete types can differ.

**"Using TWR means you don't need to consider ownership."** False. If a resource is borrowed from a caller or framework, closing it automatically in the wrong scope still breaks the workflow.

**"A suppressed error is an error that has been fixed."** False. It is only an **information-preservation** mechanism, not recovery.

**"Closing the same resource twice is always harmless."** No. Depending on the API, `close` may have side effects, throw errors, or not be idempotent.

**"Catching every `Throwable` and continuing to run after an `Error` is good practice."** No. If you catch `Throwable` to preserve the error during cleanup, you must **rethrow** it and not treat serious `Error`s as default recovery situations.

## 17. Self-Check Exercises

1. **Work throws A, close throws B, `finally` calls close directly: which error may be observed?** B can replace A if there is no mechanism preserving A.
2. **To keep A, where does B go?** A is the primary; B is suppressed and attached to A via `addSuppressed`.
3. **Work succeeds, close throws B: what should happen?** B becomes the primary or is handled as a failure per contract; do not report success.
4. **Does `addSuppressed(B)` change the type of A?** No.
5. **If there are B and C from two cleanup steps, can both be attached?** Yes, via two `addSuppressed` calls on the primary, in the order recorded.
6. **Two resources `first`/`second`, `second` close fails: should you still try to close `first`?** Yes, if the cleanup contract requires it and it can be done safely; do not let the first failure prevent closing the remaining resource.
7. **If work succeeds and `second` close fails first, then `first` close fails afterward, what is the primary?** The `second` close failure; the `first` close failure is its suppressed exception.
8. **If creating `second` fails before entering `try`, is `first` guaranteed to be closed by the subsequent `finally`?** No.
9. **Why is catching only `IOException` insufficient as a general-purpose pattern?** Because work/cleanup can produce unchecked `RuntimeException` or `Error`.
10. **Can you call `primary.addSuppressed(primary)`?** No, it causes `IllegalArgumentException`.
11. **If a custom primary has suppression disabled, what does `getSuppressed()` return?** An empty array; secondary errors cannot be recorded with this standard mechanism.
12. **When wrapping `primary` into a `DomainException`, where is it stored?** In the wrapper's `cause`; `primary`'s suppressed exceptions stay attached to that cause object.
13. **Is a rollback failure occurring after a data-write failure the `cause` of the write failure?** Usually not; it is an additional failure and should be `suppressed` if part of the same unit of work.
14. **Why is TWR usually safer?** Java closes in the right scope automatically, preserves primary/suppressed, and handles multiple resources according to specified rules.
15. **Should a method passed a borrowed resource close it automatically to prevent leaks?** No, if the contract says the caller retains ownership; determine who owns closing.
16. **Is `finally` guaranteed to run when the process is forcibly killed?** No.
17. **Is reading only `getMessage()` enough to diagnose cleanup failures?** Usually not; you need to inspect the full throwable and `getSuppressed()`.
18. **If a handler catches `Throwable` to remember the primary, should it swallow the error after cleanup?** No; it must rethrow or pass it to the corresponding failure-reporting mechanism, never assuming execution can continue.

## 18. Java 17 Reference Documentation

- [Java Language Specification 17 — `14.20.2, Execution of try-finally`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.2): a new exception from `finally` can replace the previous exit reason.
- [Java Language Specification 17 — `14.20.3, try-with-resources`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): how Java preserves primary/suppressed, closing order, and resource initialization failures.
- [Java Language Specification 17 — `11.2, Compile-Time Checking of Exceptions`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): checked exceptions and precise rethrow.
- [Java SE 17 API — Throwable.addSuppressed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#addSuppressed(java.lang.Throwable)): null check and self-suppression.
- [Java SE 17 API — Throwable.getSuppressed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getSuppressed()): reading the list of secondary errors.
- [Java SE 17 API — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): `close()` contract, checked exceptions, and idempotency.
- [Java SE 17 API — Throwable.getCause](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getCause()): distinguishing cause from suppressed errors.

**Takeaway:** When you must clean up manually, do not let a cleanup failure **mask** a work failure. If a primary already exists, keep that exact object and attach the cleanup failure with `addSuppressed`; if there is no primary yet, the cleanup failure must be reported as a real error. With multiple resources, attempt to close all resources you still own, preserving order and all resulting errors. Whenever `try-with-resources` is applicable, prefer it so you avoid hand-rolling an exception-handling flow where branches are easy to miss.
