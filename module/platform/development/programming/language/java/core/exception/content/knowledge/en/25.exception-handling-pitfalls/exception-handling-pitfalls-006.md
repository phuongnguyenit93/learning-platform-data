# Manual Resource Closing Missing Failure Branches

## 1. The Problem: The Success Path Has `close`, While the Failure Path Does Not

A Java method may use a file, stream, socket, database connection, lock, or another resource with its own lifecycle. When the work finishes, the resource must be reclaimed according to its contract. A **common mistake** is calling the cleanup method only on the **success path**, forgetting that resource acquisition, the main operation, validation checks, return statements, or the cleanup operation itself can all fail.

For example:

~~~java
// Illustrative anti-pattern; openReader() returns java.io.BufferedReader.
BufferedReader reader = openReader();
String firstLine = reader.readLine();  // May throw IOException.
reader.close();                        // Does not run if readLine() throws an error.
return firstLine;
~~~

In the normal case, `close` is called. However, if `readLine()` throws `IOException`, control exits the method and **the `close` line is never executed**. The resource may continue holding a file descriptor, buffer, or internal data that needs to be reclaimed. If a similar method is called repeatedly, omitting the failure branch can accumulate leaked resources and cause failures to surface only after running for some time.

Another naive fix is moving `close` into `finally`, **without considering that `close` itself can also throw an exception**. When both the body and cleanup fail, the exception from `finally` can mask the primary work exception, leaving only "close failed" in the logs and losing track of "read failed".

**Goal of this article:** ensure that resources opened successfully are attempted to be closed at the right time on every exit path from their ownership scope, while preserving both the work failure and cleanup failure. The preferred approach in Java 17+ for **AutoCloseable** resources is **try-with-resources**; manual cleanup should only be used when the resource lifecycle or API contract requires special logic.

## 2. Branches to Consider When Reading Code with Resources

Do not just ask "is there a `close`?". List the **points where the method can exit** and the **resource state at each point**:

| Occurrence point | Risk if manual cleanup is written naively | How to handle |
| --- | --- | --- |
| Opening the first resource fails | No valid resource to close; attempting to close a null variable or unowned resource | Only close resources that were actually opened successfully |
| Opening the second resource fails | The first resource is already open but left behind | Close previously opened resources |
| Main operation throws a checked exception | Execution jumps past the `close` line after the operation | Guarantee cleanup on all throwing paths |
| Main operation throws a `RuntimeException` or `Error` | Catching a single checked exception type is not enough | Prefer a cleanup mechanism independent of exception type |
| Early return when a resource is already held | Skips `close` placed at the end of the method | Close before the return completes |
| `break`/`continue`/conditional branches | Skips one or more cleanup steps | Bind ownership to the appropriate scope |
| Cleanup also throws an exception | Cleanup error masks the work error or prevents remaining cleanup | Preserve primary, collect secondary errors |
| Task cancellation/interruption | Thread exits a waiting operation while the resource is still held | Cleanup and interruption policy must be consistent |
| Multiple resources used together | Wrong closing order, only one resource gets closed | Close in the appropriate order and still attempt the rest |
| Operation completes but `close`/`flush` fails | Caller receives "success" even though the finalization step failed | Propagate cleanup failure according to contract |

The core concept is **resource ownership**: which method or object is responsible for closing, at what point in time, and who remains responsible after ownership is transferred. A variable name or the fact that an object is still reachable does not establish ownership on its own; you must read the API contract.

## 3. Anti-Pattern: `close` at the End Does Not Protect Exception Paths

Consider this hypothetical method:

~~~java
// Contextual illustrative code; not a standalone program.
static byte[] readAll(Path path) throws IOException {
    InputStream input = Files.newInputStream(path);
    byte[] bytes = input.readAllBytes();
    input.close();
    return bytes;
}
~~~

If **`readAllBytes()`** throws `IOException` or `OutOfMemoryError`, **`input.close()`** is not called. Even if the caller catches the error, the responsibility to release the resource inside the method has been missed.

Fix using try-with-resources:

~~~java
// Java 17+ method illustration, with appropriate imports.
static byte[] readAll(Path path) throws IOException {
    try (InputStream input = Files.newInputStream(path)) {
        return input.readAllBytes();
    }
}
~~~

Because **`InputStream` implements `Closeable`** (and thereby implements `AutoCloseable`), Java calls **`close()`** when exiting the `try` block, even if `readAllBytes` throws an error or the `try` body exits via `return`.

If the body fails and `close` also fails, the body error is preserved as the **primary exception**; the `close` error is attached to the **suppressed** list on the primary. Closing a file can report an error: the caller needs to know both the work result and whether resource reclamation succeeded.

This does not guarantee that bytes read before the failure are "rolled back"; it only guarantees that **the close lifecycle is handled** and exceptions are reported according to contract.

## 4. Why `finally` Is Not Enough When Cleanup Can Also Fail

An older common fix is:

~~~java
// Illustrative anti-pattern.
InputStream input = Files.newInputStream(path);
try {
    return input.readAllBytes();
} finally {
    input.close();
}
~~~

This pattern is better than `close` at the end because **`close` is attempted when the body fails or returns**. However, if `readAllBytes` throws an `IOException` and then `close` throws another `IOException`, the exception thrown in `finally` can **replace the original read error**. The caller only sees the resource closing error and loses sight of the failure path that caused the main operation to fail.

If `finally` also contains a **`return`**, it can mask both a pending exception and a pending return value:

~~~java
// Illustrative anti-pattern; never use as a cleanup solution.
try {
    performOperation();
} finally {
    return; // Can make an exception from try disappear.
}
~~~

**Never use `return` inside `finally` to "guarantee cleanup"**. And do not assume that catching and ignoring cleanup exceptions is safe:

~~~java
// Illustrative anti-pattern.
try {
    resource.close();
} catch (Exception ignored) {
    // Cleanup error is swallowed, reclamation state is unknown.
}
~~~

When `close` fails, the caller may need to know whether the resource is still valid, whether data was flushed completely, or whether to retry. Hiding all errors in a `catch` reduces the ability to detect these cases.

## 5. Java's Standard Mechanism: try-with-resources

**Try-with-resources** was introduced in Java 7 and is available in Java 17+. Each resource declared in the parentheses must be **`AutoCloseable`**:

~~~java
// Illustration; openResource() returns an appropriate AutoCloseable.
try (var resource = openResource()) {
    performOperation(resource);
}
~~~

Java automatically manages calling **`resource.close()`** at the end of the `try` scope. The guarantees relevant to this topic:

1. If the body runs successfully, `close` is still called.
2. If the body throws an exception, `close` is still attempted.
3. If the body executes a `return`, `close` is executed **before the method completes the return**.
4. If there are multiple resources, they are closed in **reverse order of declaration**.
5. If opening a later resource fails, previously opened resources are still closed.
6. If the body has already failed and `close` also fails, the `close` error is recorded as a **suppressed exception**, without masking the primary under the standard mechanism.
7. If the body succeeds but `close` fails, the `close` error can be thrown as the primary exception of the call.

This reduces the number of branches you have to write manually, especially when an API has many checked and unchecked exceptions. The syntactic structure makes **ownership and closing scope** clearer.

Keep in mind that **`AutoCloseable`** declares **`close() throws Exception`**; **`java.io.Closeable`** has the signature **`close() throws IOException`**. Declaring or catching checked exceptions depends on the **static type** of the resource and the APIs called by the method; try-with-resources does not eliminate checked exceptions on its own.

## 6. Complete Java 17+ Example: Six Exit Paths and Cleanup Failures

The program below uses a mock resource type to observe behavior clearly without depending on real files, databases, or networks. **`DemoResource`** prints its name on open/close and can be configured to throw `IOException` during `close`.

Six scenario groups are run sequentially:

- **No `finally`**: work fails before `close`, resource is never attempted to close.
- **Incorrect `finally`**: cleanup throws an error and masks the work error.
- **Correct try-with-resources**: preserves the work error as primary and the close error as suppressed.
- **Two resources**: closes in reverse order and preserves all secondary errors.
- **Second resource initialization failure**: still closes the previously opened resource.
- **Return with `close` failure**: does not return a result as if successful when `close` fails.

Save the file as **`CleanupBranchesDemo.java`**:

~~~java
import java.io.IOException;

public class CleanupBranchesDemo {
    static final class DemoResource implements AutoCloseable {
        private final String name;
        private final boolean closeFails;

        DemoResource(String name, boolean closeFails) {
            this.name = name;
            this.closeFails = closeFails;
            System.out.println("open " + name);
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            if (closeFails) {
                throw new IOException("close " + name + " failed");
            }
        }
    }

    static DemoResource openSecondAndFail() throws IOException {
        System.out.println("opening second failed");
        throw new IOException("second open failed");
    }

    static void wrongWithoutFinally() throws IOException {
        DemoResource resource = new DemoResource("leaky", false);
        throw new IOException("work failed");
    }

    static void wrongWithFinally() throws IOException {
        DemoResource resource = new DemoResource("masked", true);
        try {
            throw new IOException("work failed");
        } finally {
            resource.close();
        }
    }

    static void correctWorkAndCloseFailure() throws IOException {
        try (DemoResource resource = new DemoResource("safe", true)) {
            throw new IOException("work failed");
        }
    }

    static void correctSeveralResources() throws IOException {
        try (DemoResource first = new DemoResource("first", true);
             DemoResource second = new DemoResource("second", true)) {
            throw new IOException("work failed");
        }
    }

    static void correctInitializationFailure() throws IOException {
        try (DemoResource first = new DemoResource("opened", true);
             DemoResource second = openSecondAndFail()) {
            System.out.println("unreachable");
        }
    }

    static String returnAfterClose() throws IOException {
        try (DemoResource resource = new DemoResource("return", true)) {
            return "done";
        }
    }

    static void show(IOException failure) {
        System.out.println("primary: " + failure.getMessage());
        for (Throwable secondary : failure.getSuppressed()) {
            System.out.println("suppressed: " + secondary.getMessage());
        }
    }

    public static void main(String[] args) {
        System.out.println("== No finally ==");
        try {
            wrongWithoutFinally();
        } catch (IOException failure) {
            show(failure);
        }
        System.out.println("== Incorrect finally ==");
        try {
            wrongWithFinally();
        } catch (IOException failure) {
            show(failure);
        }
        System.out.println("== Try-with-resources ==");
        try {
            correctWorkAndCloseFailure();
        } catch (IOException failure) {
            show(failure);
        }
        System.out.println("== Two resources ==");
        try {
            correctSeveralResources();
        } catch (IOException failure) {
            show(failure);
        }
        System.out.println("== Initialization failure ==");
        try {
            correctInitializationFailure();
        } catch (IOException failure) {
            show(failure);
        }
        System.out.println("== Return then close failure ==");
        try {
            System.out.println("result: " + returnAfterClose());
        } catch (IOException failure) {
            show(failure);
        }
    }
}
~~~

Compile and run on JDK 17 or newer:

~~~bash
javac --release 17 CleanupBranchesDemo.java
java CleanupBranchesDemo
~~~

Directly verified stdout:

~~~text
== No finally ==
open leaky
primary: work failed
== Incorrect finally ==
open masked
close masked
primary: close masked failed
== Try-with-resources ==
open safe
close safe
primary: work failed
suppressed: close safe failed
== Two resources ==
open first
open second
close second
close first
primary: work failed
suppressed: close second failed
suppressed: close first failed
== Initialization failure ==
open opened
opening second failed
close opened
primary: second open failed
suppressed: close opened failed
== Return then close failure ==
open return
close return
primary: close return failed
~~~

### Reading the Output: No finally

The resource **leaky** is opened and the program throws **work failed**. There is no **close leaky** line. This is an anti-pattern illustrating a **missing close branch when work fails**. The mock resource only prints logs; in a real system, a similar stream/socket/connection can hold underlying resources until released by another mechanism, and you must not rely on the garbage collector to guarantee timely closing.

### Reading the Output: Incorrect finally

The body throws **work failed**, then `finally` calls `close` on **masked**, and `close` throws **close masked failed**. The exception escaping is the cleanup error, causing **work failed** to be masked. There is no automatic suppressed exception in this `finally` pattern.

### Reading the Output: Try-with-resources

The resource **safe** is closed when the `try` body fails. **work failed** remains primary; **close safe failed** is in the suppressed list. The program shows both pieces of information are preserved without writing complex manual `catch`/`finally` blocks.

### Reading the Output: Two resources

Java closes **second** then **first**. When both closes throw `IOException`, the body error **work failed** remains primary, while the close errors for `second` and `first` are added to suppressed in order. This is an easy path to miss if you write sequential `close` calls in `finally` without a strategy to catch each error individually.

### Reading the Output: Initialization failure

The resource **opened** was created successfully. Opening the next resource via **`openSecondAndFail()`** throws **second open failed** before the second resource exists. Try-with-resources still calls `close` on **opened**. If closing `opened` also fails, that error is suppressed onto the second open exception. This prevents leaking resources **already opened before full initialization completes**.

### Reading the Output: Return then close failure

The `return "done"` statement is evaluated inside the `try` body, but Java must close the resource before the method actually completes. `close` throws `IOException`, so the caller does not receive **"done"**; instead `catch` prints **close return failed**. This is important for streams that flush/finalize data upon closing: reaching a `return` statement does not mean the entire call succeeded.

## 7. Failure When Opening the Second Resource: A Frequently Forgotten Branch

A multi-resource initialization anti-pattern:

~~~java
// Contextual illustration; both a and b need to be closed.
Resource a = openA();
Resource b = openB(); // May throw an exception.
try {
    use(a, b);
} finally {
    b.close();
    a.close();
}
~~~

If **`openB()`** throws an exception, **the `try/finally` block has not started yet**, so `a` is not closed. This is why "having `finally`" is still not enough if **the `finally` scope starts after allocations that can fail**.

Fix with try-with-resources:

~~~java
// Illustration: Resource implements AutoCloseable.
try (Resource a = openA();
     Resource b = openB()) {
    use(a, b);
}
~~~

If `a` opens successfully and then `b` fails to open, Java closes `a` on the failure path. If `a.close()` also throws an error, the `b` initialization error is still preserved as primary when suppression is enabled.

If a resource provider has a factory with side effects **before returning the object**, and the factory fails and leaks its internal resource, an outer try-with-resources **cannot close an object that was never returned**. The factory itself must perform cleanup when it partially allocates:

~~~java
// Illustrative logic inside a factory; not a standalone program.
ResourcePartial partial = openPartial();
try {
    finishInitialization(partial);
    return partial;
} catch (Exception failure) {
    // Must clean up partial with an appropriate primary-preserving mechanism.
    throw failure;
}
~~~

Do not copy this snippet as a complete factory: the comment represents the cleanup step that still needs to be implemented, and the example only illustrates **the boundary of responsibility during initialization**. In real code, prefer designing constructors/factories with clear exception safety guarantees or using try-with-resources directly inside the factory whenever possible.

## 8. `try` Body Failure vs. `close` Failure: Primary vs. Suppressed

`try-with-resources` normally preserves **the `try` body error A as primary** when `close()` also throws B. Callers inspect `A.getSuppressed()` to see B. If a service wraps A into C, B remains on `C.getCause().getSuppressed()`, and does not automatically move to C's suppressed list.

~~~text
body: throw A      -> primary A
close(): throw B   -> A.getSuppressed() contains B
wrap A into C      -> C.getCause() is A
~~~

When only `close()` fails, the `close` error itself is primary. If multiple resources fail to close, the **first `close` error in reverse closing order** becomes primary, and subsequent `close` errors are kept as suppressed; Java still attempts to close the remaining resources.

In cleanup logic, **never assume `close` errors are always harmless**: depending on the API, closing may flush/finalize or confirm data completion. Read the resource contract and test the operation's postconditions, not just the exception count.

## 9. Closing Multiple Resources: Subsequent Closes Must Still Be Attempted

Anti-pattern:

~~~java
// Illustrative anti-pattern, when both a and b are already held.
finally {
    b.close(); // If this throws, a.close() does not run.
    a.close();
}
~~~

A `close` call that throws an exception skips subsequent statements in the same `finally`, unless you explicitly catch and handle it. Resource `a` can be abandoned simply because `b.close()` failed.

With try-with-resources:

~~~java
// Illustration of resources implementing AutoCloseable.
try (Resource a = openA();
     Resource b = openB()) {
    use(a, b);
}
~~~

Java closes `b` first, then `a`. Each `close` is handled with error-preserving semantics; an error from the first `close` does not stop the mechanism from attempting to close the remaining opened resources.

**Note on order:** Reverse-declaration closing usually matches lifecycle dependencies. For example, a stream wrapping another stream normally requires closing the wrapper first or letting the wrapper own closing the underlying stream; **do not close the same resource twice** just because two different variables reference it. Some wrappers automatically close the underlying resource; read the ownership contract.

### Closing Order Is Not a Formality

If `B` depends on `A` when closing, declare **`A` before `B`** so `B` closes before `A`:

~~~java
// Contextual illustration.
try (Resource connection = openConnection();
     Resource statement = openStatement(connection)) {
    use(statement);
}
~~~

If `A` is responsible for owning/closing `B` automatically, declaring both `A` and `B` as independent resources should be evaluated carefully to avoid unintended double-closing. **`AutoCloseable`** does not guarantee idempotent `close` by default for every resource type.

## 10. Null Variables, Failed Factories, and Scope

A common manual cleanup pattern:

~~~java
// Contextual illustration.
Resource resource = null;
try {
    resource = openResource();
    work(resource);
} finally {
    resource.close(); // If openResource fails, resource == null.
}
~~~

If `openResource` throws an error before assigning the variable, `finally` dereferences `null` and can throw `NullPointerException`, masking the resource opening error.

You can guard against `null`:

~~~java
// Illustrative manual cleanup branch.
finally {
    if (resource != null) {
        resource.close();
    }
}
~~~

However, this still does not solve the problem of **`close` also throwing an error**, and you must consider exceptions from the body. If the resource is `AutoCloseable`, **try-with-resources** is usually cleaner. Java will **not call `close` if the resource value in the resource specification is `null`**; nevertheless, factory design should prefer returning a valid object or throwing a clear error so code does not have to rely on `null`.

If a library only returns a special handle and does not implement `AutoCloseable`, wrap the handle in an ownership-managing adapter or design manual cleanup with complete branches.

## 11. Manual Cleanup When an API Does Not Have `AutoCloseable`

Not every API provides `AutoCloseable`. Sometimes you must call methods like **`release()`**, **`unlock()`**, **`rollback()`**, or a dedicated cancel method. In that case, the code must clarify:

- **When does ownership begin?** After opening/locking succeeds.
- **When does ownership end?** After cleanup succeeds or ownership is transferred.
- **What kinds of errors can occur?** Checked, unchecked, `Error`, interruption.
- **Which error is primary if multiple steps fail?**
- **Can cleanup of other resources still proceed?**
- **If cleanup fails, is the system state still trustworthy?**

A relatively safe example with **`Lock`**:

~~~java
// Illustration: lock is java.util.concurrent.locks.Lock.
lock.lock();
try {
    performOperation();
} finally {
    lock.unlock();
}
~~~

The lock is placed inside the `finally` scope **only after `lock()` succeeds**. However, if **`unlock()`** throws an error while the `try` body also fails, the primary-masking issue can still arise. Standard `Lock` implementations normally do not declare checked exceptions on `unlock`, though they can throw unchecked exceptions if used against their contract.

With an interruptible API:

~~~java
// Illustration: java.util.concurrent.locks.Lock.
lock.lockInterruptibly();
try {
    performOperation();
} finally {
    lock.unlock();
}
~~~

Place **`lockInterruptibly()` before `try`** so that if it throws `InterruptedException` before acquiring the lock, the code does not call `unlock` on a lock it does not own. This is a cleanup-scope bug that is especially hard to spot if you only check whether `finally` is present.

### Using an `AutoCloseable` Adapter

For a resource that has **`release()`** but does not implement `AutoCloseable`, you can create an adapter:

~~~java
// In-method illustration, assuming handle was acquired successfully.
try (AutoCloseable scope = () -> handle.release()) {
    use(handle);
}
~~~

Note that **`AutoCloseable.close()`** can throw `Exception`, so the enclosing method must declare or catch the exception appropriately. If the handle type requires cleanup exactly once or can partially fail, the adapter must adhere to that contract; the lambda expression above is only a brief illustration of the pattern.

## 12. Cleanup When Catching One Error Type While Missing Others

An error-prone manual pattern:

~~~java
// Contextual illustrative anti-pattern.
try {
    performOperation();
} catch (IOException failure) {
    resource.close();
    throw failure;
}
resource.close();
~~~

The code handles `IOException`, but if **`performOperation()` throws `RuntimeException` or `Error`**, that cleanup path is bypassed. Catching only the anticipated exception types does not prove that cleanup covers all failure paths.

Even if changed to **`catch (Exception)`**, `Error` types are not caught. Attempting **`catch (Throwable)`** to continue running is also risky because `Error` can represent a severe JVM condition rather than a normal recoverable condition.

**Try-with-resources** handles closing the resource on block exit without writing separate `catch` blocks for `IOException`, `RuntimeException`, `Error`, or `return`.

If manual cleanup is still required, design it around the *resource ownership contract* and all possible exit points; avoid assuming a broad `catch` is a substitute for `finally` or `AutoCloseable`.

## 13. Fixing with Error-Preserving `finally` When Truly Required

If the cleanup API does not fit `AutoCloseable` or has special constraints, you must preserve the primary work error and attach the cleanup error. A pattern that **only illustrates the logic**, not a general replacement for try-with-resources:

~~~java
// Scope illustration: resource implements AutoCloseable;
// work(resource) may throw IOException, and close() throws IOException.
IOException primary = null;
try {
    work(resource);
} catch (IOException original) {
    primary = original;
    throw original;
} finally {
    try {
        resource.close();
    } catch (IOException cleanup) {
        if (primary != null && primary != cleanup) {
            primary.addSuppressed(cleanup);
        } else {
            throw cleanup;
        }
    }
}
~~~

Here **`primary`** is the exact `IOException` object that was caught, not a copy containing only the message. When cleanup throws `IOException`, **`addSuppressed()`** attaches the secondary error to `primary`, and the rethrown `original` from `catch` remains in effect.

**Serious limitation of this pattern:** The code only catches `IOException`. If `work` throws `RuntimeException` or `Error` and `close` throws `IOException`, `finally` can still mask the `work` error. If the resource has a broader `close() throws Exception`, this signature is also insufficient. Therefore, do not copy this pattern for every resource and assume all error paths are solved.

If you need a truly comprehensive priority rule, you can organize the code around `Throwable`, but you must preserve the exact error types and avoid swallowing `Error`. For pure `AutoCloseable` closing, **try-with-resources** remains the simpler and more accurate choice.

### Avoiding Self-Suppression

**`Throwable.addSuppressed()`** does not allow adding a `Throwable` as a suppressed exception of itself. If **`primary == cleanup`**, calling `addSuppressed` throws `IllegalArgumentException`. This is a rare case, but it must be considered if cleanup and work could share the same `Throwable` instance (for example, a reused exception). Java documentation also does not guarantee that suppression is enabled on every custom `Throwable`; if suppression is disabled, `addSuppressed` does not retain secondary errors.

Do not try to store every cleanup error as the **`cause`** of primary: `cause` describes a causal relationship, while `suppressed` describes secondary errors arising during handling/reclamation. Using both relationships properly makes logs much easier to diagnose.

## 14. Resource Closing and Transactions: Do Not Confuse Cleanup with Rollback

The question of "enough cleanup branches" is often confused with "is data restored on failure?". These are two different guarantees.

**Closing a stream** does not erase bytes already written. **Closing a connection** does not mean commit or rollback succeeded under every JDBC/pool contract. **Releasing a lock** does not revert an object to its pre-modification state. **Canceling a `Future`** does not reverse a network request that was already sent.

Example with a manual JDBC transaction, assuming the connection is owned by this scope:

~~~java
// Contextual illustrative code; DataSource and SQLException are imported.
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        doSqlWork(connection);
        connection.commit();
    } catch (SQLException workFailure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            workFailure.addSuppressed(rollbackFailure);
        }
        throw workFailure;
    }
}
~~~

This example is for analyzing **`SQLException`** paths, not a standalone class; **`doSqlWork`** represents application logic. Try-with-resources ensures `connection.close()` is attempted on exit paths. The `catch` branch actively attempts rollback if `doSqlWork`/`commit` throws `SQLException`; any rollback error is suppressed instead of masking the primary error. If `close` also fails, try-with-resources adds the close error to the primary exception when suppression is enabled.

**Limitations to remember:**

- If `doSqlWork` can throw `RuntimeException`/`Error`, `catch (SQLException)` does not perform rollback for those paths; the transaction boundary must be designed to cover the application contract properly.
- If **`setAutoCommit(false)`** fails before entering the inner `try`, the rollback branch above does not run; `close` is still attempted on the connection, but transaction state must be analyzed separately.
- Rollback itself may fail; attaching the rollback exception as suppressed **does not guarantee the transaction recovered**.
- Some frameworks manage transactions automatically; calling commit/rollback manually outside your ownership scope can violate the framework's contract.
- After a transaction failure, the connection may need to be marked untrusted or evicted from the pool according to the datasource's mechanism, rather than being reused as if safe.

For external data, **exception safety** and **state recovery** require dedicated transaction, idempotency, or compensation policies. Try-with-resources only manages the `AutoCloseable` lifecycle and `close` exceptions; it does not turn arbitrary side effects into atomic transactions.

## 15. Early Returns, Loops, and Ownership Transfer

Non-throwing branches are also easy to forget:

~~~java
// Illustrative anti-pattern.
Resource resource = openResource();
if (skip(resource)) {
    return; // Skips close if written at the end of the method.
}
use(resource);
resource.close();
~~~

With try-with-resources:

~~~java
// Same contextual illustration.
try (Resource resource = openResource()) {
    if (skip(resource)) {
        return;
    }
    use(resource);
}
~~~

Java still closes the resource when `return` is reached. Similarly, exiting a `try` scope via `break` or `continue` in an appropriately structured loop still performs cleanup.

**However, do not return the resource itself and close it before the caller uses it:**

~~~java
// Illustrative anti-pattern.
Resource openAndReturn() throws Exception {
    try (Resource resource = openResource()) {
        return resource; // Resource is already closed before the caller receives it.
    }
}
~~~

If the method's job is to **transfer resource ownership to the caller**, it must not close the resource before handing it over. The contract must state that the caller is responsible for closing—for example, returning an open `InputStream` that the caller then places in its own try-with-resources. Do not apply TWR mechanically when ownership genuinely needs to be transferred.

A similar case is returning a **`Stream`** from a lazy API: the stream may still need to read from a datasource after the method returns. If the datasource was already closed inside the method, subsequent operations can fail. API documentation should clearly state ownership and the caller's closing responsibility.

## 16. Closing When a Task Is Interrupted or Canceled

In concurrency, a task may exit a blocking call via **`InterruptedException`**. If a resource is open, cleanup must still run. Placing the resource in try-with-resources handles this checked-exception branch alongside other failure paths.

~~~java
// Illustration: resource implements AutoCloseable;
// waitForWork may throw InterruptedException.
try (Resource resource = openResource()) {
    waitForWork(resource);
}
~~~

However, there are two distinct concerns:

1. **Preserving `InterruptedException` information:** If the method signature allows it, let `InterruptedException` propagate; otherwise, the boundary may need to restore **`Thread.currentThread().interrupt()`** and terminate according to contract.
2. **Cleanup does not automatically cancel side effects:** Closing a resource does not mean an external request is guaranteed to stop or roll back.

Be careful if cleanup itself calls a blocking API that can be interrupted. When the thread's interrupt flag is set, cleanup may fail immediately. Design timeouts and cleanup error-handling policies to avoid turning a stop request into an indefinite wait or masking the original error.

If a `Future` is **`cancel(true)`**, the `Future` being in the canceled state does not prove the worker has stopped using the resource. Ownership rules must account for when the worker actually finishes and when the cleanup scope runs.

## 17. When Should a Failed `close` Be Retried?

Do not assume `close` is safe to call repeatedly. **`AutoCloseable`** does not guarantee that every implementation is **idempotent**; some types allow multiple `close` calls, while others cause errors or other side effects.

When `close` throws an exception:

- Read the resource contract to see whether the post-failure state is defined.
- Do not immediately call `close` a second time just to "make sure it's closed" without understanding the consequences.
- Some finish/flush/commit operations are not pure cleanup; retrying can cause duplicate writes or state errors.
- If the API allows it and retries are explicitly designed, cap the attempt count, apply backoff, and log the result.
- If the resource could be dangerous to reuse, mark it untrusted and let a higher ownership layer decide.

For pooled resources, `close` sometimes returns the connection to the pool rather than actually closing the socket. A failed `close` may require the pool to discard the handle. This belongs to the specific implementation's contract; do not assume every `Connection.close` behaves identically.

## 18. Cleanup Blocks Can Have Their Own Side Effects

Do not treat cleanup as "logic-free" code:

- A **`Writer.close()`** may flush buffers.
- A **`ZipOutputStream.close()`** may need to finalize compressed data structures.
- A session or transaction API may require an explicit commit/rollback.
- A lock-release handler can affect other threads' access.
- A cleanup callback may write logs, emit metrics, or cancel scheduled work.

If `close`/cleanup fails, the final state may be ambiguous. A file-writing application might have written partial data; a remote request might already have been processed. Do not record **SUCCESS** merely because the main processing reached the end if the contract still requires cleanup/finalization to succeed.

Similarly, do not mark every cleanup error as **FATAL**. Severity depends on the resource type, usage phase, data impact, and recoverability. It is best to have a clear contract defining what constitutes a "completed" operation.

## 19. Logging Primary Errors and Cleanup Errors

Applications often make two opposite mistakes:

**Logging only the first message:**

~~~java
// Illustrative anti-pattern.
logger.error("Operation failed: " + failure.getMessage());
~~~

This can omit suppressed exceptions from `close`, the `cause`, and the stack trace. In Java logging frameworks that support throwables, pass the full error object:

~~~java
// Illustration with a logger providing an error(String, Throwable) API.
logger.error("Operation failed", failure);
~~~

This logger call depends on the corresponding framework, not a standalone Java SE class. In production, verify that the formatter actually displays **`getCause()`**, **`getSuppressed()`**, and the stack trace; JSON pipelines may require separate configuration.

**Logging at every `catch` and rethrowing:** The same error can be logged at multiple layers, causing duplicate incident counts. Usually it is better to preserve `cause`/`suppressed` while propagating the error and log once at an appropriate boundary, adding correlation ID, resource identifier, and operation name in accordance with security policies.

If a suppressed exception sits on the `cause` of a wrapper, inspecting only **`wrapper.getSuppressed()`** may miss it. Inspect the entire exception tree, not just one level.

## 20. Testing Each Branch Instead of Only the Happy Path

A cleanup unit test that only calls the method on the success path does not prove exception safety. You need a mock resource that lets you control **`open`**, **`work`**, and **`close`** to clearly reproduce each failure path.

Minimum test matrix:

| Resource open | Work | Close | Expected |
| --- | --- | --- | --- |
| Success | Success | Success | Normal result, `close` called |
| Success | Fails A | Success | A is thrown, `close` attempted |
| Success | Success | Fails B | B is thrown; no false success reported |
| Success | Fails A | Fails B | A is primary, B is suppressed |
| A opens; B fails C | Not run | A closes successfully | C is primary, A was closed |
| A opens; B fails C | Not run | A close fails D | C is primary, D is suppressed |
| A and B open | Fails C | B and A close fail D/E | C is primary, suppressed D then E |
| Success | Early return | Close fails B | Does not return normally if `close` must report failure |
| Success | `RuntimeException` | Close succeeds | `RuntimeException` still thrown, resource closed |
| Success | `Error` | Close may fail | TWR still follows cleanup and suppressed rules; do not use `catch (Throwable)` to swallow `Error` |

In JUnit tests, it is best to use **`assertSame`** (identity) to verify that the primary is the exact exception instance from `work`, and **`assertArrayEquals`** or per-element identity checks for suppressed exceptions to verify order. If you only check **`assertThrows(IOException.class)`**, the test can PASS even when **`work failed`** was replaced by **`close failed`**.

The runnable program in Section 6 demonstrates six failure paths with easy-to-follow output. Real tests should also cover non-error cases, unchecked errors, interrupted callers, and contract-specific resource state.

### Verifying Cleanup Is Called the Right Number of Times

A test resource can count `close` calls:

~~~java
// Contextual illustrative code.
final class CountingResource implements AutoCloseable {
    int closes;

    @Override
    public void close() {
        closes++;
    }
}
~~~

Where the resource is directly owned, assert **`closes == 1`** after both success and failure paths. However, do not assert that every real API must call `close` exactly once inside a wrapper's internal logic; a wrapper may close underlying resources or manage its own lifecycle. Tests should model the contract in use, not merely count invocations.

## 21. Code Review Checklist for Code with Resources

When reviewing a pull request containing files, streams, connections, locks, sessions, or handles, ask:

1. **Who owns the resource?** The current method, a long-lived object, or the caller?
2. **Where is the resource opened?** Can an error occur between multiple acquisitions?
3. **If the main operation throws an exception**, is `close` attempted?
4. **If `return`/`break`/`continue` occurs**, does `close` run before exiting the scope?
5. **If `close` throws an exception**, is the primary error masked?
6. **If there are multiple resources**, does a failure in the first `close` prevent subsequent closes?
7. **Is the closing order correct**, and is the same resource closed twice via both a wrapper and the underlying variable?
8. **If a resource has not finished opening**, does the code avoid calling `close`/`unlock` on an unowned handle?
9. **Is separate rollback/compensation needed**, or is the author confusing `close` with data recovery?
10. **If cleanup fails**, is the resource state still trustworthy, or must it be marked or discarded?
11. **If interrupted/canceled**, are cleanup and thread state handled properly?
12. **Does the logger preserve `cause`/`suppressed`**, or only log the message?
13. **Do unit tests inject faults into `open`/`work`/`close`** and verify primary/suppressed and before/after state?

**Fix priority:** For scope-owned `AutoCloseable` resources, replace manual open/use/close blocks with **try-with-resources**. Use manual `finally` only for APIs or semantics that truly differ, accompanied by full error handling and tests.

## 22. Cascading Mistakes Often Overlooked

**Mistake 1 — putting `close` at the very end and assuming it is enough.** Earlier exceptions or returns will skip `close`. Bind `close` to scope using TWR or a contract-compliant `finally`.

**Mistake 2 — having `finally`, but starting the scope too late.** If the second resource fails to open before entering `try`, the first resource leaks. Declare multiple resources in TWR or manage each acquisition as soon as it succeeds.

**Mistake 3 — closing multiple resources sequentially in `finally`.** An error in the first `close` can skip subsequent closes. Use multi-resource TWR with an appropriate declaration order.

**Mistake 4 — a `close` exception masking the work exception.** This can send the debugging team after the wrong error. TWR preserves primary/suppressed using the standard mechanism.

**Mistake 5 — catching cleanup errors and ignoring them.** The outcome of reclamation, flushing, or transactions becomes unknown. There must be a clear justification if a specific error is ever ignored.

**Mistake 6 — catching only `IOException` around `work`.** `RuntimeException`/`Error` still jumps past manual cleanup paths. TWR does not require predicting every error class.

**Mistake 7 — closing an unowned handle.** With `lockInterruptibly`, calling `unlock` after a failed acquisition can throw `IllegalMonitorStateException`. Establish ownership before entering `finally` for `unlock`.

**Mistake 8 — returning an already-closed resource.** TWR closes before `return`; only use it if returning read data, not a handle the caller still needs to use.

**Mistake 9 — treating `close` as rollback.** Partially modified data may remain. Transactions, idempotency, or compensation are needed when side effects exist.

**Mistake 10 — forgetting `close` errors at the end of a successful operation.** If `close` reports an error, do not automatically record `SUCCESS` when the contract requires closing/flushing to complete.

**Mistake 11 — retrying `close` unconditionally.** Not every `AutoCloseable` is idempotent. Check the resource contract.

**Mistake 12 — missing dual-failure tests.** Asserting only the exception type is not enough when both `work` and `close` throw `IOException`; you must check the specific primary and suppressed exceptions.

## 23. Process for Refactoring a Manual Cleanup Block

A controlled refactoring approach:

**Step 1: List resources and ownership.** If a wrapper already owns the underlying resource, avoid creating two overlapping closing paths. Identify which APIs implement `AutoCloseable` or `Closeable`.

**Step 2: Map acquisition points.** For each resource, note when opening succeeds and all paths that can throw during subsequent acquisitions.

**Step 3: Enumerate exit paths.** Checked/unchecked exceptions, early returns, loop control, timeouts, interruption, and normal completion.

**Step 4: Choose the TWR scope.** Move acquisitions into the `try` parentheses where appropriate so Java guarantees cleanup for successfully opened resources.

**Step 5: Establish declaration order.** If resource B depends on A, declare A before B so B closes before A; verify the wrapper's actual contract.

**Step 6: Define the exception contract.** How will callers receive primary, suppressed, and checked exceptions from `close`? When work succeeds but `close` fails, is the call considered failed?

**Step 7: Handle state recovery separately.** For transactions or operations with side effects, decide on rollback/commit/compensation and how errors in those steps are handled.

**Step 8: Write fault-injection tests.** Cover work failure, close failure, acquisition failure, and multiple close failures. Verify exact identity, order, and close attempts.

**Step 9: Observe in a real environment.** Ensure logs display `cause`/`suppressed`, and monitor long-lived open resources, file descriptors, connection pools, and timeouts.

**Step 10: Clean up old code.** Remove redundant manual `close` calls once TWR owns the resource; do not leave two mechanisms closing the same object without an explicit contract.

## 24. Self-Check Questions

**If `return` is inside try-with-resources, can `close` be skipped?**

No. `close` runs before the method completes the return. If `close` throws an error, the expected return value can be replaced by the exception, as shown in the runnable example.

**If `openB()` fails after `openA()` succeeded, does try-with-resources close A?**

Yes. Previously opened resources are closed on the initialization failure path of a subsequent resource. If closing A also fails, the close error can be suppressed onto the initialization error.

**If both `work` and `close` throw `IOException`, which error does an outer `catch` receive?**

With TWR and suppression enabled, the `work` error is primary, and the `close` error is in **`getSuppressed()`**. With manual `finally` that does not preserve errors, `close` can mask `work`.

**If `close` fails while `work` succeeds, can the method still return successfully?**

It depends on API design and contract, but TWR propagates the `close` exception instead of completing a normal return when `close` reports an error. Do not discard the error just to report success.

**With two resources, why must they close in reverse order?**

Because a resource opened later often depends on one opened earlier; TWR closes from right to left. This is a rule of Java syntax, though the design must still clarify ownership and avoid duplicate closes.

**If `finally` has a null check, is that sufficient?**

No. A null check only avoids dereferencing an unassigned handle; it does not solve `close` failures, dual errors, multi-resource ordering, or side effects requiring rollback.

**Does try-with-resources automatically roll back a transaction?**

No. It calls `close` according to the `AutoCloseable` lifecycle. Transaction state/commit/rollback depends on the API and transaction management mechanism. A separate policy is required.

**Is `catch (Throwable)` needed to guarantee cleanup?**

Not if the resource fits `AutoCloseable` and uses TWR. Arbitrary `catch (Throwable)` can swallow serious `Error`s. If manual management is required, define propagation clearly and do not hide exceptions.

## 25. Technical Decision Summary

**Manual resource closing missing failure branches** is a bug when code only closes on the happy path or only handles a few error types. Adding `finally` can fix resource leaks, but it does not necessarily preserve the **primary error** when cleanup also fails. A subsequent resource open failure, a failing `close` in a chain, or an early `return` are all branches that must be tested.

For **`AutoCloseable`** resources, **try-with-resources** is the standard choice because it handles these branches directly in the language construct: closing successfully opened resources, closing in reverse order, never skipping cleanup when the `try` body fails or returns, keeping the work exception as primary, and attaching secondary `close` errors as suppressed.

For APIs requiring **`unlock`, `rollback`, `cancel`, or `release`** with custom semantics, deliberate manual cleanup is still necessary. In those cases, do not merely check "does `finally` run?"; check **ownership responsibility, all exit paths, errors during cleanup, data state after failure, and observability**. Testing dual failures and initialization failure paths often reveals flaws that happy-path tests cannot see.
