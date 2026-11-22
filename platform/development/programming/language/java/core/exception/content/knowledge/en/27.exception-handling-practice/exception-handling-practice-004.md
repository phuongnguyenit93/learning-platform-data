# Refactoring Manual Cleanup to Try-With-Resources

## 1. Practice Objectives

When reading legacy Java code, we often see resources opened, used, and then closed with a manually written **close()** call. That code may work fine on the success path, but an error occurring mid-way can prevent the close statement from running. Migrating to **try-with-resources** (TWR) is not merely a syntax change; it is a process of **establishing resource ownership, covering all exit paths, and preserving exception information**.

This practice guides you through **refactoring manual cleanup to try-with-resources** in Java Core, with the following objectives:

1. Accurately identify which resources need to be closed and who owns each resource.
2. Recognize anti-patterns: closing at the end of a method, closing in a mis-scoped `finally`, closing multiple resources sequentially, and ignoring errors when initializing subsequent resources.
3. Place **AutoCloseable** resources into the appropriate TWR scope without closing them prematurely or twice.
4. Understand closing order, how `return` is handled, and exception behavior on success/failure paths.
5. Keep the task failure as the **primary** exception and the cleanup failure as **suppressed** if both occur.
6. Perform safe migrations with APIs that have checked exceptions, pre-declared resources in Java 9+, wrappers, and callbacks.
7. Retest behavior, state, and ownership rather than just checking that the code compiles.

**Short definition:** With TWR, Java automatically calls **close()** on successfully opened resources when leaving the `try` scope. When the body throws a `Throwable` and `close` also fails, the close error is recorded in **getSuppressed()** of the primary error, provided the `Throwable` supports suppression.

Do not assume that TWR automatically rolls back databases, cancels external I/O, or cleans up all side effects. TWR addresses **resource closing lifecycle**; data atomicity is a separate guarantee.

## 2. Reading Anti-Patterns Before Fixing

Example of legacy code:

~~~java
// Illustrative code; appropriate imports and reader-creation API must be declared.
BufferedReader reader = Files.newBufferedReader(path);
String first = reader.readLine();
reader.close();
return first;
~~~

If **readLine()** throws an **IOException** or a `RuntimeException`, the **reader.close()** statement does not run. This is the **cleanup-only-on-happy-path** bug.

A version with `finally`:

~~~java
// Contextual illustrative code.
BufferedReader reader = Files.newBufferedReader(path);
try {
    return reader.readLine();
} finally {
    reader.close();
}
~~~

This version attempts to close even when the `try` body throws an exception or returns. However, two points still need consideration:

- If **reader.close()** throws an exception, it can mask the read exception that occurred inside `try`.
- If another resource was opened before `reader` and an error occurs before entering `try`, the `finally` block may not protect the earlier resource.

Therefore, migrating to TWR must preserve the practical requirements of the API: ensuring the right resource is closed, in the right scope, at the right time, and propagating full error details to the caller.

Target style:

~~~java
// Illustrative code with imports BufferedReader, Files, Path, IOException.
try (BufferedReader reader = Files.newBufferedReader(path)) {
    return reader.readLine();
}
~~~

If `reader` opens successfully, TWR is responsible for calling `close` when the `try` body finishes, whether by normal completion, exception, or `return`. If opening `reader` fails before a valid object exists, there is no `reader` to close; if earlier TWR resources were already opened, they are still cleaned up.

## 3. Determine Ownership First

**Ownership** is lifecycle management responsibility: who has the right to close the resource, who must guarantee `close`, and when that right transfers to someone else.

Questions to answer when refactoring:

| Case | Who is typically responsible for closing? | Notes |
| --- | --- | --- |
| Method opens a file to read and only returns data | The method itself | TWR directly inside the method is usually appropriate |
| Method receives an InputStream passed by the caller | Usually the caller, depending on the contract | Do not close it with TWR if not owned |
| Factory returns an open InputStream | Caller receives ownership | Do not wrap the returned resource in TWR |
| Wrapper stream closes its delegate automatically on close | Owner of the wrapper per contract | Avoid unnecessarily closing the delegate twice |
| Connection provided by a transaction-managing framework | Framework / transaction boundary | Mis-scoped TWR can break transactions |
| ResultSet/Statement created in a short block | Depends on JDBC API and owning layer | Determine scope and closing order |
| Cached resource shared across multiple requests | Cache/application management component | Do not close after each request if still shared |

If a method opens a resource and returns that resource itself:

~~~java
// Anti-pattern: method returns an already-closed resource.
InputStream createStream() throws IOException {
    try (InputStream input = Files.newInputStream(path)) {
        return input;
    }
}
~~~

TWR will call `close` **before the caller receives the result**. This is wrong if the caller intends to continue reading the stream. The right approach is to return the open stream and **explicitly document that the caller is responsible for closing it**, or change the API to return the fully read data within the method's closing scope.

TWR fits best when **the resource lifetime matches the lexical scope of `try`**. If the lifetime is longer, do not force it into an overly short block.

## 4. Step-by-Step Safe Migration Process

A systematic review/refactoring process:

**Step 1 — Read the resource acquisition paths.** Find where `FileInputStream`, `BufferedReader`, `Connection`, `Statement`, `Socket`, `ZipFile`, `Stream`, or custom `AutoCloseable` instances are created. If multiple resources are opened, note the order and the point at which each acquisition succeeds.

**Step 2 — Analyze ownership.** Determine whether the resource is currently owned by the method or borrowed/transferred. Do not "fix a leak" by closing a caller's resource against the contract.

**Step 3 — Find all exit paths.** Checked exceptions, `RuntimeException`, `Error`, early `return`, `break`, `continue`, conditional branches, and failures when opening subsequent resources.

**Step 4 — Check the close API.** Does the resource implement `AutoCloseable`/`Closeable`? Which checked exceptions does `close` throw? Does it close an underlying delegate? Does it require reverse closing order?

**Step 5 — Choose the TWR scope.** Put acquisition inside the `try` parentheses if possible. The block should cover the entire duration the resource is used without extending beyond the needed lifetime.

**Step 6 — Move the main processing logic.** Keep business logic inside the `try` body without accidentally re-invoking work or altering the order of side effects.

**Step 7 — Remove redundant manual close calls.** Once TWR owns the resource, remove the old `close` call to avoid double closing.

**Step 8 — Preserve the exception contract.** Compare the exception the caller receives when the `try` body fails, when `close` fails, and when both fail. If the legacy code had a bug masking the primary exception, proactively update tests to match the intended correct behavior rather than preserving the bug.

**Step 9 — Test with fault injection.** Make open/work/close fail in turn; verify the exact close count, order, primary/suppressed exceptions, and business outcome.

**Step 10 — Review operational impact.** Monitor connection leaks, file descriptors, complete `Throwable` logging, transaction state, and performance on real usage paths.

A refactoring is complete when the **behavioral contract** is clear and regression tests PASS; not merely when the IDE stops showing a "resource leak" warning.

## 5. Distinguishing AutoCloseable and Closeable

Java uses two related interfaces:

~~~java
// Conceptual signatures; located in standard JDK packages.
interface AutoCloseable {
    void close() throws Exception;
}

interface Closeable extends AutoCloseable {
    void close() throws IOException;
}
~~~

**AutoCloseable** is the general contract for resource cleanup. **Closeable** belongs to `java.io` and narrows the checked exception type to `IOException`. These two signatures only illustrate the contract, not code for redeclaring those standard interfaces.

If a variable has static type **AutoCloseable**, the compiler may require handling **Exception** from `close`. If a variable has type **BufferedReader** or **InputStream**, `close` is typically declared with `IOException`. When migrating to TWR, **do not unexpectedly widen `throws Exception`** on a public API just because a variable type was changed to an overly broad `AutoCloseable`.

Example:

~~~java
// Illustrative code inside a method with throws IOException.
try (BufferedReader reader = Files.newBufferedReader(path)) {
    return reader.readLine();
}
~~~

The concrete type is preserved, so the checked exception can be declared/propagated appropriately as `IOException`. For custom resources, choose the narrowest `close` signature that reflects the errors that can actually occur.

**Note:** Not every `close` is idempotent. `AutoCloseable` does not promise that calling `close` multiple times on every implementation is harmless. Therefore, after transferring ownership to TWR, removing the old cleanup is genuinely a correctness step, not just code tidying.

## 6. Runnable Java 17+ Example: Comparing Before and After

To avoid depending on a real database or files, the following program defines **Tracked implements AutoCloseable**. Its constructor prints the resource name when opened; **work()** can throw `IOException`; **close()** prints the name when closed and can also throw `IOException`.

The program includes:

1. **oldMissingFailureBranch** — the resource is opened but not closed if `work` throws.
2. **oldFinallyMasksWork** — `finally` closes the resource but masks the work exception.
3. **refactoredWorkFailure** — TWR preserves both primary and suppressed exceptions.
4. **twoResources** — closes in reverse order and attempts to close both even if both `close` calls fail.
5. **initializationFailure** — the first resource is closed if opening the next resource fails.
6. **returnWithCleanup** — `close` runs before `return` completes.
7. **java9ExistingVariable** — since Java 9, an effectively final local variable can appear in the resource specification.

Save as **ResourceRefactorDemo.java**:

~~~java
import java.io.IOException;

public class ResourceRefactorDemo {
    static final class Tracked implements AutoCloseable {
        private final String name;
        private final boolean failClose;
        private boolean closed;

        Tracked(String name, boolean failClose) {
            this.name = name;
            this.failClose = failClose;
            System.out.println("open " + name);
        }

        void work(boolean fail) throws IOException {
            System.out.println("work " + name);
            if (fail) {
                throw new IOException("work " + name + " failed");
            }
        }

        boolean isClosed() {
            return closed;
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            closed = true;
            if (failClose) {
                throw new IOException("close " + name + " failed");
            }
        }
    }

    static void oldMissingFailureBranch() throws IOException {
        Tracked resource = new Tracked("legacy", false);
        resource.work(true);
        resource.close();
    }

    static void oldFinallyMasksWork() throws IOException {
        Tracked resource = new Tracked("finally", true);
        try {
            resource.work(true);
        } finally {
            resource.close();
        }
    }

    static void refactoredWorkFailure() throws IOException {
        try (Tracked resource = new Tracked("safe", true)) {
            resource.work(true);
        }
    }

    static void twoResources() throws IOException {
        try (Tracked first = new Tracked("first", true);
             Tracked second = new Tracked("second", true)) {
            throw new IOException("body failed");
        }
    }

    static Tracked openSecondAndFail() throws IOException {
        System.out.println("opening second failed");
        throw new IOException("second open failed");
    }

    static void initializationFailure() throws IOException {
        try (Tracked first = new Tracked("prepared", true);
             Tracked second = openSecondAndFail()) {
            System.out.println("unreachable");
        }
    }

    static String returnWithCleanup() throws IOException {
        try (Tracked resource = new Tracked("return", false)) {
            System.out.println("prepare return");
            return "result";
        }
    }

    static void java9ExistingVariable() throws IOException {
        Tracked existing = new Tracked("existing", false);
        try (existing) {
            existing.work(false);
        }
        System.out.println("existing closed=" + existing.isClosed());
    }

    static void show(IOException problem) {
        System.out.println("primary: " + problem.getMessage());
        for (Throwable secondary : problem.getSuppressed()) {
            System.out.println("suppressed: " + secondary.getMessage());
        }
    }

    public static void main(String[] args) throws IOException {
        System.out.println("== Missing failure branch ==");
        try {
            oldMissingFailureBranch();
        } catch (IOException problem) {
            show(problem);
        }

        System.out.println("== Finally masks original ==");
        try {
            oldFinallyMasksWork();
        } catch (IOException problem) {
            show(problem);
        }

        System.out.println("== Refactored ==");
        try {
            refactoredWorkFailure();
        } catch (IOException problem) {
            show(problem);
        }

        System.out.println("== Reverse closing order ==");
        try {
            twoResources();
        } catch (IOException problem) {
            show(problem);
        }

        System.out.println("== Failure during acquisition ==");
        try {
            initializationFailure();
        } catch (IOException problem) {
            show(problem);
        }

        System.out.println("== Early return ==");
        System.out.println("returned: " + returnWithCleanup());

        System.out.println("== Java 9 existing variable ==");
        java9ExistingVariable();
    }
}
~~~

Compile and run on JDK 17 or newer:

~~~bash
javac --release 17 ResourceRefactorDemo.java
java ResourceRefactorDemo
~~~

Verified stdout when compiled and run:

~~~text
== Missing failure branch ==
open legacy
work legacy
primary: work legacy failed
== Finally masks original ==
open finally
work finally
close finally
primary: close finally failed
== Refactored ==
open safe
work safe
close safe
primary: work safe failed
suppressed: close safe failed
== Reverse closing order ==
open first
open second
close second
close first
primary: body failed
suppressed: close second failed
suppressed: close first failed
== Failure during acquisition ==
open prepared
opening second failed
close prepared
primary: second open failed
suppressed: close prepared failed
== Early return ==
open return
prepare return
close return
returned: result
== Java 9 existing variable ==
open existing
work existing
close existing
existing closed=true
~~~

**Reading the output across the before -> after sequence:** The **legacy** resource did not print `close` because `work` threw before the manual `close` call. The **finally** resource did print `close`, but the caller only received **close finally failed** — the `work` error was masked. When replaced with **safe** in TWR, the program printed the primary error **work safe failed** and the suppressed error **close safe failed**. That is an important improvement in **error information and lifecycle**, not just fewer lines of code.

The example simulates a simple resource for deterministic stdout. In real applications, `close` may flush, perform I/O, release locks, or send commands to a server; you must additionally verify the contract of that resource type.

## 7. Reading Primary and Suppressed Errors After Refactoring

TWR preserves `Throwable` semantics across these scenarios:

| Body | Close | Observed result |
| --- | --- | --- |
| Succeeds | Succeeds | Completes normally |
| Throws A | Succeeds | A is propagated |
| Succeeds | Throws B | B can become the primary error |
| Throws A | Throws B | A is primary, B is added to A.getSuppressed() |
| Returns a value | Succeeds | Close runs before return completes |
| Returns a value | Throws B | Normal return does not complete; B is propagated |
| Opening second resource throws C | Closing first resource succeeds | C is propagated |
| Opening second resource throws C | Closing first resource throws D | C is primary, D is suppressed |

**getCause() and getSuppressed() are different.** Cause describes the relationship where an error is the underlying reason for a wrapper; suppressed describes a secondary error that occurred while another operation was already failing.

Example:

~~~java
// Illustrative code in a valid catch block.
catch (IOException primary) {
    System.out.println(primary.getMessage());
    for (Throwable extra : primary.getSuppressed()) {
        System.out.println(extra.getMessage());
    }
}
~~~

In the runnable example, **show(IOException)** does exactly this. If a service layer creates **new IllegalStateException("read failed", primary)**, the suppressed exceptions remain on **primary** at **wrapper.getCause().getSuppressed()**, and do not automatically appear on **wrapper.getSuppressed()**. Therefore, loggers must display **the entire Throwable tree**, not just the outer message.

Some custom `Throwable` classes can disable suppression via a dedicated constructor. When suppression is disabled, `addSuppressed` does not store the information; in that case, it cannot be guaranteed that every close error is preserved in `getSuppressed`. For common JDK exceptions such as `IOException`, the mechanism works as expected.

## 8. Why Put Acquisition in the Resource Specification?

Anti-pattern when opening two resources:

~~~java
// Contextual anti-pattern.
Resource a = openA();
Resource b = openB(); // If this fails, try has not been entered yet.
try {
    work(a, b);
} finally {
    b.close();
    a.close();
}
~~~

If `openB` throws an exception, `a` is already open but `finally` never starts, so `a` is leaked.

Better pattern:

~~~java
// Illustrative; Resource implements AutoCloseable.
try (Resource a = openA();
     Resource b = openB()) {
    work(a, b);
}
~~~

Java tracks each resource that has been successfully opened. If **openB()** fails, `a` is attempted to be closed. If closing `a` also fails, the cleanup error is suppressed onto B's initialization error by the TWR mechanism.

**An important boundary:** If **openB()** allocates internal resources and then fails before returning object B, the outer TWR cannot close an object that was never handed over. B's **factory/constructor** must handle exception safety for its own internal ownership. TWR cannot fix every kind of resource leak inside a library.

## 9. Closing Order of Multiple Resources and Lifecycle Dependencies

In a resource specification:

~~~java
// Contextual illustration.
try (Resource first = openFirst();
     Resource second = openSecond(first)) {
    use(second);
}
~~~

Java closes **second before first**. In the runnable example, stdout shows **close second**, followed by **close first**, even when both `close` calls throw `IOException`.

This is a sensible design when `second` depends on `first`, yet **ownership** still needs checking. A wrapper may automatically close its delegate inside `close`; if you declare the wrapper and the delegate as two independent resources, the delegate may be closed twice. `AutoCloseable` does not guarantee that every `close` can be repeated harmlessly.

Example with `BufferedReader` wrapping a `Reader`:

~~~java
// Illustrative file reading.
try (BufferedReader buffered =
         new BufferedReader(Files.newBufferedReader(path))) {
    process(buffered);
}
~~~

In this case, `BufferedReader.close` closes the underlying reader per its contract. There is no need to declare a separate `Reader` variable just to close it again, unless there is a specific ownership requirement. If resources are split across multiple layers, ensure the closing order does not break wrapper dependencies and avoid duplicate closes.

## 10. Java 9+: Using Final or Effectively Final Local Variables

In Java 7/8, the common resource specification syntax is **try (Type variable = expression)**. Starting in Java 9, you can use an existing **final or effectively final local variable or parameter**:

~~~java
// Illustrative Java 9+ code.
BufferedReader reader = Files.newBufferedReader(path);
try (reader) {
    System.out.println(reader.readLine());
}
~~~

This syntax is only valid when the variable satisfies the final/effectively final condition. If the variable is reassigned after initialization, the compiler will reject it. For example, the runnable program has:

~~~java
// Excerpt.
Tracked existing = new Tracked("existing", false);
try (existing) {
    existing.work(false);
}
~~~

Here **existing** is not reassigned, so Java 17 compiles it. TWR closes the resource upon exiting `try`; the `existing` reference remains in scope, but the object is already closed. **Holding a reference does not mean it is valid to continue using the resource**.

### Pitfall When an Existing Variable Is Opened Outside

If code performs multiple operations between **open** and **try(existing)**, an exception in that gap can still leak the resource:

~~~java
// Contextual anti-pattern.
Resource existing = open();
prepareOtherState(); // May throw before try.
try (existing) {
    use(existing);
}
~~~

When refactoring, **start the ownership scope as close as possible to the point of successful acquisition**. Existing variables in Java 9+ are a syntactic convenience; they **do not guarantee cleanup for steps executed before entering `try`**.

Another point: do not put a caller-supplied resource into **try (parameter)** if the method **does not own** that resource. Java will still call `close`; valid syntax does not prove a correct ownership decision.

## 11. Refactoring with Multiple Returns and Conditional Branches

Cleanup at the end of a method is easily bypassed by early returns:

~~~java
// Contextual anti-pattern.
Resource resource = openResource();
if (shouldSkip()) {
    return;
}
perform(resource);
resource.close();
~~~

Refactored to:

~~~java
// Illustrative.
try (Resource resource = openResource()) {
    if (shouldSkip()) {
        return;
    }
    perform(resource);
}
~~~

TWR closes the resource before the method finishes. **Returning inside the `try` body** does not skip cleanup. By contrast, **returning inside `finally`** is an anti-pattern because it can mask pending exceptions or return values.

With **break** or **continue** from a loop, when control leaves the TWR scope, `close` is also executed. Choose the block placement according to the actual lifecycle: does the resource live across the whole loop, or does each iteration open a new resource? If a stream/connection must live across multiple iterations, place TWR around the loop; if each iteration uses an independent resource, place TWR inside the loop.

Example illustrating both strategies:

~~~java
// One resource used for the entire loop.
try (Resource shared = openResource()) {
    for (Item item : items) {
        process(shared, item);
    }
}

// Separate resource per item.
for (Item item : items) {
    try (Resource perItem = openResource(item)) {
        process(perItem, item);
    }
}
~~~

These two snippets only illustrate scope design; `Resource`, `Item`, and the methods must be defined in the project. The second approach performs more open/close calls and may be more expensive or more correct depending on the contract. Do not change the scope just because the syntax is convenient.

## 12. When Refactoring APIs That Do Not Implement AutoCloseable

Not every resource has a standard `close`. A `Lock` has **unlock()**; a native API has **release(handle)**; a transaction has **commit()/rollback()**. In those cases you can:

1. Keep manual cleanup with a properly scoped `finally` and an error-preserving strategy.
2. Create an **AutoCloseable adapter** if release semantics fit and ownership is clear.
3. Use a higher-order helper to wrap the lifecycle if the API has special commit/rollback steps.

Adapter example:

~~~java
// Contextual illustration; handle has been acquired successfully.
try (AutoCloseable scope = () -> handle.release()) {
    use(handle);
}
~~~

Because **AutoCloseable.close() throws Exception**, the containing method must declare or catch the appropriate checked exception. The adapter must also consider whether `release` is idempotent, what state remains if `release` fails, and whether ownership needs to be transferred afterward. Do not write an adapter just to "satisfy TWR" if it breaks transaction semantics.

An example with `Lock`:

~~~java
// Illustrative with java.util.concurrent.locks.Lock.
lock.lock();
try {
    performOperation();
} finally {
    lock.unlock();
}
~~~

This remains an appropriate structure because `Lock` is not directly `AutoCloseable`. Placing `lock.lock()` before `try` ensures `unlock` only runs when acquiring the lock completed normally. With **lock.lockInterruptibly()**, if `InterruptedException` occurs before acquiring the lock, the code must not attempt to `unlock`. Refactoring must respect the boundary of successful acquisition.

## 13. When Migration Changes Checked Exceptions

A legacy method might not declare a broad `Exception` because `close` was not handled properly or the resource had a specific type. After refactoring, the compiler will check the checked exceptions that **close()** in the resource specification can throw.

Example:

~~~java
// Illustrative code:
static String read(Path path) throws IOException {
    try (BufferedReader reader = Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
~~~

`BufferedReader.close` can throw `IOException`, so the `throws IOException` signature is appropriate.

If you change the declared type to **AutoCloseable**:

~~~java
// Illustrative; must handle checked Exception from AutoCloseable.close().
static void process(AutoCloseable resource) throws Exception {
    try (resource) {
        performOperation();
    }
}
~~~

Do not arbitrarily change every public method to **throws Exception** just to make it compile. Check the concrete static type, API overloads, wrapper constructors, and existing exception policy. You can use a resource wrapper whose **close() throws IOException** or a better-defined exception if it matches the semantics.

**Important:** TWR can make an exception **that legacy code was accidentally ignoring** observable—such as a `close` failure after the `work` body succeeded. This is a behavior change that must be reviewed against the contract. Do not catch and swallow all `close` errors just to preserve a previously buggy behavior.

## 14. Cleanup and Transactions Are Two Different Problems

Refactoring a database `Connection`'s `close` with TWR does not replace transaction policy. In JDBC:

- **Connection.close()** relates to the connection/handle lifecycle per the API or pool.
- **commit()** confirms the transaction.
- **rollback()** attempts to undo uncommitted changes.
- **setAutoCommit(false)** controls how JDBC ends transactions per contract.
- **close() failure** may require marking the handle untrusted, depending on the provider/pool.

Illustrative pattern for a method-owned transaction:

~~~java
// Illustrative code inside a method declaring throws SQLException.
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        performSql(connection);
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

This is a contextual snippet, not a standalone Java program. It only handles rollback in the inner `SQLException` branch; `RuntimeException` or `Error` from `performSql` must be considered separately if the contract requires rollback in those cases. If **setAutoCommit(false)** fails before the inner `try`, this rollback branch does not run, even though TWR still attempts to close the connection.

**Section takeaway:** TWR manages `close`; preserving data integrity requires a separate commit/rollback/compensation policy. Do not use resource refactoring to promise that "no error can ever leave state modified."

## 15. Handling Interruption and Cancellation During Cleanup

If a thread is waiting on work and throws **InterruptedException**, it may exit the `try` body early. If the resource belongs to TWR, Java still runs `close` on that exit path.

~~~java
// Illustrative code: resource implements AutoCloseable, waitForData
// may throw InterruptedException and the method has an appropriate contract.
try (Resource resource = openResource()) {
    waitForData(resource);
}
~~~

Distinguish between:

- **InterruptedException**: signal that a thread's blocking operation was interrupted.
- **CancellationException**: cancelled state of a `Future`/result.
- **TimeoutException**: a single wait timed out; does not automatically close all worker resources.
- **IOException from close**: may be a secondary error when the interrupt path already produced the primary exception, or the primary error when the `try` body completed.

TWR does not automatically cancel a task running in another thread. If the caller times out and closes a resource while a worker is still using it, races and new errors can occur. Refactoring must preserve **cross-thread ownership**.

When a method allows `InterruptedException` to propagate, it should usually propagate up to the layer owning the work. If a checked exception cannot be propagated at a `Runnable` boundary, the code may need to restore the interrupt flag and exit. This policy must not be replaced with `catch (Exception)` that ignores it just to "ensure cleanup."

## 16. Cases Where close Also Has Side Effects

Some `close` methods do more than free memory or file descriptors:

- **BufferedWriter.close()** may flush buffered data.
- **ZipOutputStream.close()** may finalize the archive structure.
- **Socket.close()** changes the I/O capability of the connection endpoint.
- **JDBC Connection.close()** has specific semantics depending on the datasource/pool.
- A custom resource may send data or publish information when closing.

If the `try` body returned a result but `close` throws an exception, TWR can replace the return value with the exception. This is usually right when the contract treats `close` as a mandatory step to complete the work. However, in API design, clearly define **when an operation is considered successful**.

**Do not unconditionally retry close** after it throws an error: `AutoCloseable` does not require every implementation to support calling `close` multiple times idempotently. Read the contract and determine the state after failure. Closing a resource also does not mean written bytes or side effects were rolled back.

In code review, separate the question "was `close` attempted?" from "did the operation achieve its business goal?" Both must be verified.

## 17. TWR with Additional catch/finally Blocks Is Still Valid

A TWR structure can still have its own `catch`/`finally` blocks:

~~~java
// Illustrative code.
try (Resource resource = openResource()) {
    perform(resource);
} catch (IOException failure) {
    log(failure);
    throw failure;
} finally {
    updateMetrics();
}
~~~

Automatic resource cleanup runs before the outer `catch`/`finally` handles the error outcome in this structure. `catch` can access both the primary exception and any suppressed exceptions attached when `close` ran.

However, if **updateMetrics()** in `finally` throws its own exception, it can still mask the exception being propagated. TWR only preserves errors from **close() of resources in the resource specification** via its mechanism; it **does not protect against other exceptions from a user-added `finally`**.

Do not move old cleanup into an outer `finally` outside TWR unnecessarily. If metrics/logging can fail, define the failure policy for those secondary steps: should they report errors, be suppressed, be logged separately, or avoid harming the primary error path?

## 18. Multiple Resource Layers and Nested Ownership

Example of a file-reading stream wrapped across layers:

~~~java
// Illustrative code inside a method with imports and throws IOException.
try (InputStream input = Files.newInputStream(path);
     BufferedInputStream buffered = new BufferedInputStream(input);
     DataInputStream data = new DataInputStream(buffered)) {
    return data.readInt();
}
~~~

TWR will close **data**, then **buffered**, then **input**. However, **data.close()** may already close `buffered`, and `buffered.close()` closes `input`. The subsequent `close` calls may be redundant. For many JDK streams, repeated closing is handled safely by the implementation, but **do not generalize this to every `AutoCloseable`**.

A cleaner form when the wrapper owns its delegate:

~~~java
// Illustrative code.
try (DataInputStream data = new DataInputStream(
        new BufferedInputStream(Files.newInputStream(path)))) {
    return data.readInt();
}
~~~

This relies on the wrapper's chained-closing contract. If a wrapper constructor can fail after the inner resource has already been opened, you must consider the exception safety of constructing the wrapper. When a factory can fail mid-way, declaring resources separately at appropriate levels can make cleanup easier to guarantee.

**There is no mechanical rule that "fewer lines is always safer."** TWR helps express ownership, but the person refactoring still needs to understand how `close` propagates through wrappers.

## 19. When Should You Not Replace All Manual Cleanup with TWR?

Some cases do not fit a simple TWR block:

1. The resource is a **borrowed object** owned by the caller or framework.
2. The resource must outlive the method scope, such as returning a stream for the caller to read.
3. Cleanup is not a simple `close` but requires multi-state **commit, rollback, or release**.
4. The resource is used across asynchronous steps and finishes after the initiating method returns.
5. The close API has specific thread requirements or ordering/conditions different from TWR.
6. The object does not implement `AutoCloseable` and a naive adapter distorts semantics.
7. Long-lived scoped resources such as caches, pools, or service lifecycles.

If a resource is created in a controller and handed off to a background worker, closing it as soon as the controller returns can cause the worker to fail. If a connection is provided by a transaction manager, closing it directly can violate framework policy. These cases require clearer ownership design, not just a syntax swap.

Most code that opens a resource for short-lived synchronous processing remains a very good candidate for TWR.

## 20. Regression Testing: Proving the New Behavior Is Correct

Testing only the success path can make a refactoring look fine while still losing errors when cleanup fails. You need a test double resource that can:

- Record open/close calls and their order.
- Throw an exception in `work`.
- Throw an exception in `close`.
- Fail while opening a second resource.
- Track resource state before and after `return`.

Minimum matrix:

| Acquisition | Work | Close | Key assertion |
| --- | --- | --- | --- |
| Succeeds | Succeeds | Succeeds | Resource is closed, result is correct |
| Succeeds | Throws A | Succeeds | A is propagated, close is called |
| Succeeds | Succeeds | Throws B | B is propagated, no false success reported |
| Succeeds | Throws A | Throws B | A is primary, B is suppressed |
| Open A succeeds, open B throws C | Does not run | Close A succeeds | C is primary, A is closed |
| Open A succeeds, open B throws C | Does not run | Close A throws D | C is primary, D is suppressed |
| Open A and B succeed | Throws C | Close B and A throw D/E | Order B->A, C is primary, suppressed D then E |
| Succeeds | Early return | Succeeds | Close runs before return |
| Succeeds | Early return | Throws B | Call throws B instead of returning normally |
| Succeeds | RuntimeException | Succeeds | RuntimeException is preserved, close is still attempted |

**A common test mistake:** Writing only **assertThrows(IOException.class)** when both `work` and `close` can throw `IOException`. If `close` masks `work`, the test still PASSes because the `IOException` type did not change. Check a **test-controlled message**, or better yet **object identity of the primary exception**, together with **getSuppressed()**.

With JUnit Jupiter you can use **assertThrowsExactly**, **assertSame**, **assertEquals**, and event-order assertions. Do not hardcode stack trace line numbers; line numbers change with source formatting, not the TWR contract.

## 21. Test Helper for Fault Injection in close

A custom test resource can have state flags:

~~~java
// Illustrative code to be placed in an appropriate test class.
final class Probe implements AutoCloseable {
    int closeCalls;
    boolean failClose;

    @Override
    public void close() throws IOException {
        closeCalls++;
        if (failClose) {
            throw new IOException("probe close failed");
        }
    }
}
~~~

In a test:

~~~java
// JUnit illustration; requires corresponding JUnit Jupiter static imports.
Probe probe = new Probe();
probe.failClose = true;

IOException failure = assertThrowsExactly(IOException.class, () -> {
    try (probe) {
        throw new IOException("work failed");
    }
});

assertEquals("work failed", failure.getMessage());
assertEquals(1, probe.closeCalls);
assertEquals(1, failure.getSuppressed().length);
assertEquals("probe close failed",
             failure.getSuppressed()[0].getMessage());
~~~

This example requires JUnit Jupiter on the classpath; it is not a standalone Java SE snippet. The **try (probe)** syntax is valid from Java 9 if the local variable is effectively final; mutating **probe.failClose** does not change the `probe` variable reference.

When testing multiple resources, use a **List<String> events** to record `open`, `work`, and `close`. When asserting, check the event order rather than only counting `closeCalls`. If a wrapper resource closes its delegate automatically, `close` count expectations must be based on that specific contract.

## 22. Ownership Regressions to Check

A "clean-looking" migration can introduce new bugs:

**Closing a caller's resource:** A method accepts an `InputStream` from the caller and immediately puts it in **try(input)**, closing the stream while the caller still intends to use it.

**Closing before returning a resource:** A factory returns a resource from a TWR block, giving the caller an already-closed object.

**Double closing:** TWR calls `close` automatically while an old `finally` still calls `close`; a custom resource may not tolerate a second call.

**Closing in the wrong order:** An underlying resource is closed before a wrapper that still needs to flush data.

**Opening a resource outside TWR and doing work before entering `try`:** An exception in that gap still causes a leak.

**Unintentionally changing the exception contract:** TWR starting to propagate `close` errors causes callers to receive a new checked exception, or changes the primary error compared to an old bug. Any justified change must be documented clearly.

**Skipping rollback thinking TWR handles everything:** A transaction fails, yet data may still be partially modified; transaction policy must be kept separate.

**Extending scope too far:** The resource holds a file descriptor or connection for too long, even with syntactically valid TWR.

**Shortening scope too much:** The resource is closed before an async task or lazy stream finishes processing.

Before merging, verify the **resource lifetime** with a real usage example, not just compilation.

## 23. Error Logging After Migration

One noticeable change is the appearance of **suppressed exceptions** in the error tree. For example, an `IOException` from `read` is kept as primary, while an `IOException` from `close` is attached as suppressed. Ensure your logging system preserves the full `Throwable`:

~~~java
// Illustrative code with a logger supporting error(String, Throwable).
logger.error("Resource operation failed", failure);
~~~

If you only log **failure.getMessage()**, you may miss the `close` error or the original failure location. If a service wraps the primary exception into a domain exception, the logger must display the cause chain so that suppressed exceptions on the cause remain visible.

However, do not log at every `catch` layer and rethrow. That easily produces multiple log entries for the same incident. Prefer preserving the full `Throwable` when propagating errors and logging once at the appropriate handling boundary, along with an operation ID, request ID, or non-sensitive resource name.

Avoid printing internal paths, tokens, credentials, or personal data in messages if logs are widely accessible. Such details can appear in the cause or suppressed exceptions of I/O resources.

## 24. Checklist for Refactoring Reviewers

Before approving a pull request that converts manual cleanup to TWR:

1. **Ownership:** Does this method own the resource, or is it managed by the caller/framework?
2. **Acquisition:** Is the resource initialized inside the resource specification or protected immediately after opening succeeds?
3. **Lifetime:** Does TWR close at the right time, without closing prematurely before the caller/worker needs it?
4. **API type:** Does the resource implement `AutoCloseable`/`Closeable`; have the `close` signature and checked exceptions been reviewed?
5. **Exit paths:** Are checked/unchecked exceptions, `Error`, `return`, `break`, and `continue` cleaned up properly?
6. **Dual failure:** Does the work failure remain primary and the close failure become suppressed?
7. **Order:** With multiple resources, does reverse-declaration closing order match dependencies?
8. **Duplicate close:** Have redundant manual `finally`/`close` calls or duplicate delegate closes been removed?
9. **Initialization failure:** If opening a subsequent resource fails, are previously opened resources cleaned up?
10. **Outcome:** If `close` fails after `work` succeeds, does the caller observe the failure per contract?
11. **Side effects:** Are transaction/rollback/compensation mechanisms still intact and separate from `close`?
12. **Async:** Is the resource used by a task that outlives the TWR scope?
13. **Tests:** Are there scenarios for open/work/close failures verifying primary/suppressed exceptions, state, and close counts?
14. **Observability:** Do logging and monitoring surface suppressed exceptions and causes without losing stack traces?

If any question cannot be answered because the API contract is unclear, that is a signal to investigate before changing code—not a reason to hastily put every resource into a TWR block.

## 25. Self-Check Questions

**Q: Does TWR always close resources when the `try` body throws an exception?**

Yes, for resources that were successfully initialized and belong to the resource specification, under standard Java rules. However, if a resource's constructor or factory fails before returning an object, the factory's own internal logic is responsible for releasing anything it allocated internally.

**Q: If both the body and `close` throw `IOException`, which one does the caller receive?**

The body exception is normally primary; the `close` exception is suppressed when suppression is enabled. Do not confuse this with a manual `finally` that can allow `close` to mask the body exception.

**Q: Do we still need `finally` after replacing manual cleanup with TWR?**

You do not need `finally` **just to call `close` on the resources already managed by TWR**. You may still need `finally` to update metrics, release other kinds of resources, or coordinate business logic, but you must consider whether that `finally` block can introduce new errors.

**Q: Can a resource opened before `try` be used with `try(existing)`?**

Yes, on Java 9+ when the variable is final or effectively final. However, any steps executed between opening and entering TWR **are not protected by that TWR**. Place the scope as close to successful acquisition as possible.

**Q: Does TWR automatically retry `close` if it fails?**

No. It calls `close` according to scope rules. Cleanup retry is a separate policy and may be unsafe if `close` is not idempotent.

**Q: Can TWR be used on `Lock` or transaction APIs?**

Only directly if the object implements `AutoCloseable` with appropriate semantics, or via a controlled adapter. For `Lock`/`unlock` and transaction `commit`/`rollback`, avoid a generic adapter if it compromises ownership or state recovery requirements.

**Q: If two resources depend on each other, in what order does Java close them?**

From the last-declared resource to the first. Order declarations according to dependencies and avoid redundantly closing delegates owned by a wrapper.

**Q: Does TWR make an operation atomic?**

No. It guarantees scoped cleanup, but does not undo written data, sent requests, or modified mutable state. Separate transactions, idempotency, or compensation are needed for side effects.

## 26. Practice Conclusion

**Refactoring manual cleanup to try-with-resources** is an improvement in **correctness, maintainability, and error reporting**. It eliminates forgotten failure paths, closes successfully opened resources, handles reverse closing order, and preserves the work error as primary when cleanup also fails.

However, a good refactoring is more than replacing **try/finally** with **try (...)** parentheses. It must preserve **ownership**, avoid premature or duplicate closes, account for **checked exceptions**, and include tests for acquisition failure, work failure, close failure, early returns, and dual failures. When resources are tied to transactions or async work, business contracts and lifecycles beyond the method scope must also remain intact.

**Quick rule of thumb:** If a method owns an **AutoCloseable** within a short scope, prefer TWR. If ownership is long-lived, shared, or cleanup has semantics different from `close`, design the lifecycle explicitly and test it thoroughly. In either case, do not only check that the resource is closed on the success path—prove that resources and exceptions are handled properly even when everything fails.
