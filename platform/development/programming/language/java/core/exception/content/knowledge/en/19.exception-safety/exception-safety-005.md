# Exceptions Do Not Automatically Undo Files, Data, or External Effects

## 1. Understanding What an Exception Actually Does

In Java, **throwing an exception (`throw`) changes control flow**; it does not automatically roll back changes that have already occurred. The JVM searches for a matching `catch` by unwinding the stack; the associated `finally` blocks are executed according to language rules, and `try-with-resources` attempts to close managed resources. There is no default step in Java that performs an "undo" for file writes, object mutations, committed SQL statements, HTTP requests, emails, or sent messages.

Suppose an operation consists of:

1. Appending content to a file.
2. Sending a command to record an order in a database.
3. Calling an external payment service.
4. Throwing `IllegalStateException` because a final validation step fails.

An exception in step 4 **does not prove** that steps 1–3 were rolled back. To know the actual state after a failure, you must examine each effect separately: how far the file write got, which transaction the SQL is in, whether the payment provider received/processed the request, and what the program did to recover.

This lesson focuses on preserving state when exceptions occur: distinguishing **resource release**, **change recovery**, **atomicity**, **transactions**, and **compensating external side effects**, and practicing appropriate patterns in Java 17+.

## 2. Distinguishing Five Easily Confused Actions

| Action | Purpose | Automatically reverses modified content? |
| --- | --- | --- |
| `throw` an exception | Signals that normal execution flow cannot continue | **No** |
| `catch` an exception | Gives the caller an opportunity to handle it, decide whether to continue or propagate | **No**, unless code inside `catch` actively recovers |
| `finally` | Executes cleanup tasks when leaving a `try` block under normal circumstances | **No**; to undo, you must write appropriate logic |
| `try-with-resources` | Calls `close()` on resources declared in the `try` parentheses | **Not by default**; `close()` does not mean rollback |
| Transaction `rollback()` | Requests the transaction system to discard uncommitted changes belonging to that transaction | **Yes within the supported transaction scope**, does not cover files, emails, HTTP, or already-committed transactions |

For example, `FileOutputStream.close()` releases the file resource, but does not erase bytes that have already been written. Similarly, `BufferedWriter.close()` may flush buffered data; the close operation can even cause data to be written out during exception handling. Conversely, closing a JDBC connection **is not a rollback contract you can rely on in all cases**: transaction management must be performed explicitly or delegated to a transaction manager.

An exception can occur **after an effect succeeds**; therefore, "the method threw an exception" and "the method changed nothing" are two completely different assertions.

## 3. In-Memory State Does Not Automatically Revert Either

Java does not save a copy of objects before entering a `try` block. If you have modified a `List`, `Map`, an object field, or an object shared between threads, throwing an exception does not undo the previous assignment or mutation.

~~~java
import java.util.ArrayList;
import java.util.List;

class MemoryStateExample {
    public static void main(String[] args) {
        List<String> steps = new ArrayList<>();
        steps.add("created");

        try {
            steps.add("charged");
            throw new IllegalStateException("report failed");
        } catch (IllegalStateException e) {
            System.out.println(e.getMessage());
        }

        System.out.println(steps);
    }
}
~~~

Save as `MemoryStateExample.java` and run:

~~~bash
javac --release 17 MemoryStateExample.java
java MemoryStateExample
~~~

Stdout:

~~~text
report failed
[created, charged]
~~~

This is a standalone Java 17 example: `steps.add("charged")` persists after `catch`. `finally`, if added, would not automatically remove this element either.

When you need an **all-or-nothing commit or preservation of the old state**, a clearer approach is usually to validate first, build the new result in a local variable, and then update the shared state at a single controlled final point. For example, compute a complete `List.copyOf(...)` before swapping the state reference. Keep in mind that a single reference assignment does not turn a multi-resource chain of effects into a transaction, and concurrency handling still requires appropriate synchronization mechanisms.

## 4. Writing Files: Data May Already Have Changed Before an Exception Is Thrown

### 4.1. Standalone Java 17 Example: Partial Write and Writing via a Temporary File

The following example intentionally throws an exception **after appending to a file** to demonstrate that data is not automatically undone. Then it creates a separate candidate file and intentionally rejects it before the publish step, to show that the operation on the **target file** has not happened. Finally, it illustrates a normal replacement.

Save as **`ExceptionSideEffectDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;

public class ExceptionSideEffectDemo {
    static void appendThenFail(Path file) throws IOException {
        Files.writeString(file, "|append", StandardCharsets.UTF_8,
                StandardOpenOption.APPEND);
        throw new IllegalStateException("failure after append");
    }

    static void stagedReplace(Path target, String next, boolean reject)
            throws IOException {
        Path candidate = Files.createTempFile(
                target.getParent(), "candidate-", ".txt");
        try {
            Files.writeString(candidate, next, StandardCharsets.UTF_8);
            if (reject) {
                throw new IllegalArgumentException("rejected before publish");
            }
            Files.move(candidate, target, StandardCopyOption.REPLACE_EXISTING);
        } finally {
            Files.deleteIfExists(candidate);
        }
    }

    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("exception-state-");
        Path file = dir.resolve("data.txt");
        try {
            Files.writeString(file, "initial", StandardCharsets.UTF_8);
            try {
                appendThenFail(file);
            } catch (IllegalStateException e) {
                System.out.println("1. " + e.getMessage());
            }
            System.out.println("2. " + Files.readString(file));

            try {
                stagedReplace(file, "candidate", true);
            } catch (IllegalArgumentException e) {
                System.out.println("3. " + e.getMessage());
            }
            System.out.println("4. " + Files.readString(file));

            stagedReplace(file, "published", false);
            System.out.println("5. " + Files.readString(file));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Compile and run from the directory containing the file with JDK 17 or later:

~~~bash
javac --release 17 ExceptionSideEffectDemo.java
java ExceptionSideEffectDemo
~~~

Stdout when file operations are permitted by the operating system:

~~~text
1. failure after append
2. initial|append
3. rejected before publish
4. initial|append
5. published
~~~

**Why does it produce this output?**

- Initially, `data.txt` contains `initial`.
- `appendThenFail` executes `Files.writeString(..., APPEND)` and then throws `IllegalStateException`. After `catch` receives the error, the data has become `initial|append`, proving the exception did not reverse the append.
- `stagedReplace(..., true)` writes the new data to **another** temporary file; it throws before `Files.move`. `finally` deletes the temporary file, while the target file still contains `initial|append`.
- `stagedReplace(..., false)` reaches `Files.move` to replace the target file with `published`. This is only an illustration of the happy path; `Files.move` with `REPLACE_EXISTING` **does not guarantee atomic replacement in all situations**, because `ATOMIC_MOVE` is not used.

The example intentionally uses a temporary directory and deletes it in `finally` so it leaves no data behind after a successful run. In environments where creating, writing, moving, or deleting files is denied, the program may throw `IOException` and fail to print the full stdout. Exceptions from cleanup must also be considered separately in production code.

### 4.2. Why Even a Failing Write Method Does Not Prove the File Is Intact

Writing a file is not necessarily an "all-or-nothing" operation. A loop writing multiple chunks may succeed on several chunks and then encounter an `IOException`; the target file's contents may already have changed. `Files.writeString` or `OutputStream.write` does not provide a transaction contract for multiple consecutive write operations. In-memory buffers, the OS page cache, and durable data on the storage device are also different layers.

Incorrect example:

~~~java
// Anti-pattern: write directly to the target file and hope an exception will automatically recover it.
Files.writeString(target, generatedText);
runValidationThatMayThrow();
~~~

This is an illustrative snippet assuming `target`, `generatedText`, and the validation function already exist. If validation throws an exception, the file's contents may already have been altered.

You should distinguish:
- **Before the publish step:** create the new result in a temporary file, validate integrity, checksum/length, or format, and only then consider publishing.
- **At the publish step:** if atomic replacement is required and the filesystem supports it, you can use `Files.move(candidate, target, ATOMIC_MOVE)`; catch `AtomicMoveNotSupportedException` to apply an explicit policy.
- **After publishing:** if the new file has already been published and another operation fails, you cannot assume the file reverted to the old version.

In the JDK, `ATOMIC_MOVE` is an option requesting that the move be performed as **an atomic filesystem operation**, but the provider may not support it and may throw `AtomicMoveNotSupportedException`. When `ATOMIC_MOVE` is specified, the behavior for replacing an existing target is implementation-dependent and other options are ignored per the API contract; it does not promise target replacement on every filesystem. Do not silently fall back to a non-atomic move if atomicity is a strict requirement. Safe execution may require failing fast or designing a dedicated recovery strategy for the deployment environment.

Even an atomic rename/move **does not guarantee data survival after a power loss**. You need to evaluate data flushing, `FileChannel.force`, directory metadata, and filesystem/OS guarantees if crash durability is required. In particular, writing two separate files and moving each one does not create an atomic transaction across both files.

### 4.3. What Are the Limitations of Recovering via a Temporary File?

Typical sequence:

~~~text
Read current version
    -> create new version in temporary file
    -> validate new version
    -> publish new version
    -> clean up temporary file / record result
~~~

This strategy limits the window during which the target file is affected, ensuring that errors occurring **before publishing** do not corrupt the target data. However, you still need to handle:
- Errors right at publish time, especially when the filesystem does not support atomic replacement.
- Process crashes leaving temporary files undeleted; there should be a safe mechanism to clean up orphaned files.
- Multiple competing writers: do not let an older version overwrite a newer version if not allowed; consider locking, version/checksum checks, or an appropriate synchronization protocol.
- Permissions, ownership, attributes, and symlinks: replacing a file can affect metadata; do not assume all attributes remain unchanged.
- Errors **after publishing**: the new file may still exist even though the caller receives an exception from cleanup or a subsequent operation.

Therefore, you must clearly define the **publish/commit point** so you can answer: "If an error occurs before or after this point, what is the resulting state?"

## 5. `finally` and try-with-resources Only Solve Part of the Problem

`finally` is well suited for releasing locks, cleaning up temporary files, resetting temporary state, or freeing resources. However, it cannot automatically infer a valid undo operation. If code inside `try` has already sent an email, calling `close()` on the client will not recall the email.

Example:

~~~java
try (var writer = Files.newBufferedWriter(path)) {
    writer.write("updated");
    throw new IllegalStateException("later step failed");
}
~~~

This is a non-standalone illustrative snippet (assuming `path` is already declared and writable). When exiting `try` due to an exception, `writer.close()` is called; that does not mean the file returns to its previous state. With `newBufferedWriter(path)` using default options, the file may already have been created or truncated as soon as it was opened. Closing typically flushes buffered data; it is not a rollback.

**If closing the resource also throws an error**, try-with-resources applies the *suppressed exceptions* rule: when the body has already thrown an exception and `close()` also throws, the close error is attached to the primary error via `getSuppressed()`. With manually written `finally` logic, an exception in `finally` can mask the original exception if not handled carefully.

Therefore, separate two goals:
- **Resource safety:** resources are closed, temporary files are cleaned up, locks are released.
- **State/transaction safety:** are business changes fully committed, can a rollback be performed, and what are the boundaries of recovery?

A program can do well on resource safety while failing on state safety, or vice versa.

## 6. Databases: Only a Properly Scoped Transaction Can Roll Back

With JDBC, each new `Connection` typically starts in `autoCommit = true` mode. In this mode, each SQL statement completes according to the JDBC/database commit mechanism; an exception thrown **after a committed statement** does not automatically undo the change. For multiple statements to participate in the same transaction, you need to manage `autoCommit(false)`, `commit()`, and `rollback()` appropriately, or use a properly configured transaction manager/framework.

Diagram:

~~~text
BEGIN transaction
    UPDATE accounts SET balance = ... WHERE ...
    INSERT INTO ledger (...)
    check final invariant
    +-- success ------------> COMMIT
    +-- error before commit -> ROLLBACK
~~~

This is a conceptual diagram, not runnable SQL code. When the database supports transactions properly and statements participate in the right transaction, a rollback can discard **uncommitted** changes from those statements. Once `commit()` has succeeded, a subsequent `rollback()` does not undo the earlier commit.

A JDBC pattern needs to guard several points:
1. Only disable `autoCommit` when you actually own the transaction scope; avoid accidentally interfering with a connection managed by a pool/framework.
2. Execute related statements through **the same appropriate transaction**; do not assume multiple connections automatically share a transaction.
3. Call `commit()` after all conditions required for the internal transaction are satisfied.
4. If a failure occurs before commit, call `rollback()` and try to preserve the original exception; if `rollback()` also fails, record it as a secondary error rather than silently swallowing it.
5. Restore/close the connection according to the library contract or return it to the pool; avoid leaking transaction state to the next request.

Two important caveats must be added to this reasoning:
- **Not every storage system/DDL/engine rolls back the same way.** Transaction mechanisms and rollback capabilities depend on the database, statement type, engine, and isolation level. Do not place a statement outside the transaction scope and claim it will be undone.
- **`commit()` throwing an error does not always prove the transaction did not commit.** For example, losing the connection right while receiving the response can leave the outcome uncertain; you need to query back by transaction ID/idempotent identifier or follow a pre-designed recovery procedure.

### 6.1. The "Exception After Commit" Trap

~~~text
BEGIN DB transaction
    INSERT order
COMMIT succeeds
send confirmation email
email service throws exception
catch -> call DB rollback
~~~

The `rollback` at the end **does not undo the already-committed order**. Conversely, if you send the email before committing and the commit fails, the user may receive an "order placed" message even though the database recorded no order. Two independent resources do not automatically belong to a shared transaction just because they are called in the same Java method.

For Spring or other frameworks, transaction annotations/rules only apply when the transaction manager actually wraps supported resources and the invocation conditions are met. For example, a DB transaction does not automatically extend to HTTP, the filesystem, or email. Do not assume every unchecked/checked exception triggers a rollback in every framework configuration; rollback rules must be verified for the technology in use.

## 7. External Side Effects: There Is No Universal Undo Button

A call with an external side effect can be:
- an HTTP POST creating an order in another service;
- sending an email or message;
- publishing an event to a message broker;
- charging money, creating a payment request, or saving an object in remote storage;
- sending a command to a device or another process.

Once the call returns successfully or the receiver executes the command, a Java exception in the caller **does not send a default cancellation request**. Even when the caller sees a timeout, the receiver may already have processed it successfully while the response was lost. This is an **indeterminate outcome**, not automatically "failed with no side effect."

### 7.1. Retries Require Idempotency and Traceable State

For example, a payment API accepts a fixed `paymentRequestId` idempotency key per **logical request**. When an HTTP timeout occurs, the client can query status by that identifier or retry with the **same key** if the service genuinely guarantees idempotency: duplicate requests with the same key are interpreted as the same operation and do not create a second charge.

Merely setting a header named "Idempotency-Key" without server-side support for recording state and preventing race conditions provides **no guarantee**. The server typically needs a mechanism to record results by key, uniqueness constraints, and rules for key/payload lifecycle. For non-idempotent operations, do not automatically retry when you do not know whether the first request was already applied.

### 7.2. Transactional Outbox

When you must update a database **and** send an event, a common strategy is:

~~~text
Within 1 DB transaction:
    INSERT/UPDATE business data
    INSERT outbox record
    COMMIT

After commit:
    worker reads outbox
    sends event
    marks as sent or retries
~~~

The strength of this pattern is that the business data and the "need to send event" record are committed in the same transaction **within the same database/transaction scope**. This avoids the situation where the business change commits but the intent to publish the event is completely lost. However, the worker can send successfully and crash before marking it as sent, leading to **redelivery**. Therefore, consumers still need idempotent/deduplicating handling. An outbox **does not guarantee end-to-end exactly-once delivery** merely by having an outbox table.

### 7.3. Compensation / Saga

If a workflow has already created an order, reserved inventory, and requested payment across multiple independent systems, a failure in a later step can trigger compensating actions such as releasing the inventory reservation or issuing a refund. These are **new operations**, not the JVM turning back time or a global transaction rollback. Compensation can also fail and require retries, monitoring, and reconciliation; not every effect has a reversible operation (an email cannot be reliably "unsent," and an event that has reached listeners may already have triggered downstream effects).

You need to design:
- A transaction identifier and workflow state (`PENDING`, `CONFIRMED`, `COMPENSATING`, `FAILED`, or appropriate states);
- Ordering and conditions for executing the next step;
- Specific compensating actions and idempotency of each step;
- Retry policies, retry limits, and dead-letter/manual reconciliation when needed;
- Rules for updating state when a remote result is uncertain.

Do not use compensation as an excuse to skip a simple local transaction where one can be used.

## 8. Safety Guarantees Based on Where the Side Effect Occurs

For files or external services, evaluate guarantees based on the **timing of the failure** rather than treating all exceptions the same:

| Where does the error occur? | What can be asserted | What must not be inferred |
| --- | --- | --- |
| Before sending the command / writing target data | No side effect **from that step** yet; internal state may still need checking | The entire system is definitely unchanged |
| While writing directly to a file | The file may contain partial data | The file automatically rolled back because an exception occurred |
| After successfully replacing with a candidate file | The target file may already be the new version | An exception in the notification step will restore the file |
| After sending a remote request but before ACK | The remote outcome is **uncertain**; must query status or reconcile | The remote definitely did not process it, so retry unconditionally |
| During cleanup or compensation | A secondary error may have occurred that should be recorded via `suppressed`/log | Undo definitely succeeded just because code entered `finally` |

Within the scope of a single object, the **basic guarantee** preserves invariants even if values may have changed; the **strong guarantee** preserves the observable state if a failure occurs within the published scope. Across networks, files, and multiple resources, these two terms **do not automatically extend** into application-wide guarantees.

A clearer postcondition than "an exception will roll back everything" is:

> If validation rejects before publish, the target file is not replaced by the candidate version. If the file has been published but sending the notification fails, the target file may still be the new version; the system records the notification state for controlled retry.

Thus, **occurred**, **did not occur**, and **unknown** states must be represented explicitly when integrating with external systems; an exception by itself cannot fully distinguish all three cases.

## 9. Designing a Staged Safe Operation

Suppose you need to update a JSON configuration and emit a configuration-changed event:

1. **Define invariants and scope:** the JSON must be valid, have a new version, and the current data must remain readable; the event can be safely resent keyed by version.
2. **Prepare:** build the new JSON in memory; validate schema, size, checksum/related logic before modifying the target file.
3. **Stage:** write a temporary file in an appropriate location; verify it was written completely. If an error occurs at this stage, delete the candidate.
4. **Publish:** use a file replacement mechanism suited to the filesystem and atomicity requirements; if `ATOMIC_MOVE` is required, handle the case where it is unsupported.
5. **Record the published version:** avoid a state after a crash where you do not know which version is current; there must be a way to read back the actual state.
6. **Emit event:** choose a mechanism matching the durability scope—for example, an outbox if the primary data lives in a DB; design version/idempotency so consumers avoid duplicate processing.
7. **Clean up and monitor:** delete unused temporary files, record recovery errors, and distinguish "failed before publish" from "published but notification failed."

With file + database + broker as **three separate resources**, the workflow above does not automatically become a global transaction. If the system requires atomicity across all three, you must design a consistency protocol and recovery states; it cannot be solved with a single `try/catch`.

### 9.1. Why Side-Effect Ordering Affects Recovery

Compare two workflows:

~~~text
Option A:
    send "succeeded" email
    -> write data
    -> data write fails
Result: email sent, data missing.

Option B:
    commit data and outbox in the same transaction
    -> worker sends email based on outbox
    -> temporary send failure, worker retries
Result: data committed and send request preserved for recovery.
~~~

Option B works well when the data and outbox are in a supported transaction, the worker is idempotent, and monitoring is in place. It still cannot guarantee that the email is delivered exactly once in all situations. Outgoing messages should reflect actual state: for example, an "order recorded" event is different from "payment definitely completed."

## 10. Anti-Patterns in Exception and State Handling

### 10.1. Swallowing Exceptions and Reporting Success

~~~java
try {
    writeToDisk();
} catch (Exception ignored) {
    // Do not report the error, so callers above still think the entire operation succeeded.
}
return true;
~~~

Non-standalone illustrative snippet: `writeToDisk` and the enclosing method are hypothetical. If the write partially modifies the file and then throws an exception, returning `true` hides both the error and the uncertain state. You should propagate the error, return a structured status, or initiate recovery according to the contract.

### 10.2. Calling Rollback After Every Exception Even After Commit

~~~text
try:
    commit succeeds
    external call (throws error)
catch:
    rollback and declare everything cancelled
~~~

Rollback has no effect on an **already-committed** transaction. You must distinguish pre-commit errors, post-commit errors, and errors where it is unknown whether the commit succeeded.

### 10.3. Using `finally` to Always Delete the Target File

~~~java
try {
    produceOutput();
} finally {
    Files.deleteIfExists(target);
}
~~~

Fragment assuming variables and methods exist. If `target` is the official output of an operation that already succeeded, deleting it in `finally` destroys the result. Only clean up **temporary resources owned by the current invocation**; do not delete primary data or data owned by other requests.

### 10.4. Retrying a POST After Timeout Without Idempotency

A timeout can occur **after the server has already created the resource**. Uncontrolled retries can create duplicate orders or double-charge. Use a stable request identifier and a status lookup or server-supported idempotency mechanism.

### 10.5. Assuming `close()` Means Rollback

Closing a writer/stream does not retract bytes already written; closing a network client does not retract a request that already reached the server. JDBC connections must have transactions managed according to the contract; do not delegate correctness to assumptions about `close` behavior.

### 10.6. Recovering with a New Operation Without Preparing for That Operation to Fail

For example, an API deducts inventory and, after an error, calls an API to add the quantity back. Both operations can lose connectivity or race with another transaction; adding back can also be wrong if applied twice. Compensating operations need idempotency, causal identifiers, and concurrency bounds—or a real transaction when possible.

## 11. Testing by Failure Point, Not Just by Exception Type

To prove state-preservation promises, merely asserting `assertThrows(...)` is not enough. You must inspect **the state after each possible failure point**.

| Fault injection point | What to verify |
| --- | --- |
| Before mutating state | File/database/object remains intact |
| After a partial append | Data may have changed; does the contract report the state accurately |
| When creating/writing a temporary file | Does not affect the target file; temporary file cleanup is appropriate |
| When validation rejects before publish | The old version still exists and is readable |
| During move/publish | System detects the failure, reads back actual state, does not assume publish definitely did not happen |
| Right after DB commit | Subsequent rollback is not treated as having undone the commit |
| While sending a remote request | Distinguishes "response failed" from "server never executed" |
| When cleanup/close fails | Primary exception and secondary error are not conflated; resource/state is recorded |
| When retrying with the same idempotency key | Does not produce additional effects beyond what the service guarantees |

You can use real temporary files for small I/O tests; use fakes/stubs capable of throwing errors **before/after mutating state** for other services; and use transaction tests against a real database when verifying rollback. When testing remote timeouts, simulate the case where **the server processed the request but the response was lost**, not only the case where the server rejects immediately.

Some invariants to assert:
- Do not emit a "success" notification before the result actually meets publish conditions.
- Uncommitted data can be rolled back according to the engine and transaction; committed data is not mistakenly treated as discarded.
- The target file is not modified by errors occurring in the staging step per the contract.
- Every repeatable step has verified idempotency or safety conditions.
- When the outcome is uncertain, the system retains state for investigation/reconciliation instead of returning `false` and pretending no side effect occurred.

## 12. Checklist When Writing Java APIs with Side Effects

1. **Document the invariance scope:** if the method throws an exception, which parts may have changed? Which parts are guaranteed to remain unchanged?
2. **Separate resource cleanup from rollback:** `finally`/try-with-resources closes and cleans up; rollback only exists when the resource/protocol actually supports it.
3. **Minimize side effects before validation:** validate and compute first, write through staging when appropriate.
4. **Define the commit/publish point:** errors before and after this milestone have different consequences.
5. **Preserve exceptions and causes:** errors during cleanup/compensation must be recorded, avoiding masking the first error and avoiding swallowing exceptions.
6. **Use transactions at the right boundary:** operations in the same DB transaction can roll back per DB guarantees; non-DB actions do not automatically participate.
7. **Accept uncertain states from remote systems:** a timeout does not prove non-execution; use status queries, idempotency, and reconciliation.
8. **Design controlled compensation and retries:** a compensating action is a new side effect that can fail and may need to be retried.
9. **Test post-failure state:** test failures before write, after write, after commit, after publish, during cleanup, and on lost responses.
10. **Do not promise full rollback without proof:** API documentation should clearly state what stays invariant, what can partially change, and how callers recover.

### Practice Exercise

Design a method `saveReportAndNotify(Path path, Report report)` that generates report content, saves it to a file, and sends a notification via a remote service. Describe the state of the file and the notification when an error occurs at three points: (a) before writing the candidate file, (b) after publishing the file but before sending the notification, and (c) after the remote service executes the notification but the client times out. Then propose a mechanism for recording version/state and retrying without creating duplicate notifications. Clearly state which guarantees apply only to **a single file**, which apply to **a DB transaction**, and which require a dedicated protocol for **external side effects**.

Key takeaway: **an exception says that Java execution flow was interrupted; it does not say that the outside world returned to the state before the method was called.**
