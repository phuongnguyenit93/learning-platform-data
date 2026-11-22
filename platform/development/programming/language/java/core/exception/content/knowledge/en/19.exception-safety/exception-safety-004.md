# State Recovery and the Limits of Rollback When Handling Exceptions in Java

## 1. Why Is State Recovery Important?

A method may consist of multiple steps: validating inputs, modifying objects, writing to a database, calling another service, and returning a result. If an exception occurs after several steps have already completed, the program may leave behind new data **even though the call reported a failure**. Therefore, proper exception handling does not stop at `try/catch`; it also requires deciding what state remains and who is responsible for recovery.

**Rollback** means undoing changes within a **controllable scope** back to a consistent state committed to by the contract. It is important to distinguish:

- **In-memory rollback:** restoring field or collection values to what they were before the operation; or better, preparing an independent state and only publishing it once all fallible work has succeeded.
- **Transaction rollback:** discarding uncommitted changes within a transaction of a system that supports transactions, such as a database via JDBC.
- **Compensation:** creating a new business operation to offset the effect of an already executed operation, such as issuing a refund after a charge has been recorded. It cannot erase all history or guarantee that others have not already observed the initial effect.
- **Recovery:** the process of bringing the system back to proper operation after a failure, which may include rollback, log replay, reconciliation, safe retry, or compensation.

Exceptions **do not automatically roll back** Java data, files, databases, or network services. `throw` only transfers control flow; any changes already made can still persist.

## 2. Exception Safety Guarantee Levels

When designing or reviewing an API, ask “after the method fails, what does the caller observe?” rather than only asking “where is the error caught?”.

| Guarantee Level | State After Failure | Example |
| --- | --- | --- |
| **Strong exception guarantee** | Within the declared scope, the operation either succeeds completely or leaves observable state unchanged | Compute all data on a copy, validate, then swap a single reference |
| **Basic exception guarantee** | Objects preserve their invariants and no resources are leaked, though some values may have changed | A processor saves step-by-step progress and maintains a valid state on failure |
| **No guarantee** | State may be half-updated, inconsistent, or have an unknown outcome | Mutate multiple fields and throw mid-way without recovery handling |
| **No-throw guarantee** | An operation designed not to throw exceptions under defined contract conditions and scope | Swap a pre-prepared reference within an appropriate synchronized block without performing I/O |

These levels are **guarantees about state**, not Java exception types. A checked exception like `IOException` does not inherently have “better rollback” than `RuntimeException`. Likewise, *no-throw* does not mean every JVM `Error` or infrastructure failure is impossible; it requires specific preconditions and scope.

The phrase “unchanged state” must have a **boundary**: an object, an aggregate, a DB transaction, or an entire multi-service workflow? An API can provide a strong guarantee for local memory while an external message send has already completed. Do not document “atomic” or “full rollback” without defining the scope.

## 3. What `try/catch/finally` Actually Does

The example below is a code snippet inside a method that already has a `balance` variable and a `notifyRemote()` method:

```java
balance -= 20;       // If it was 100 before, it is now 80
notifyRemote();      // May throw IOException
```

If `notifyRemote()` throws an error, `balance` **remains 80** unless there is explicit logic to restore it. Java does not automatically snapshot object fields.

Mechanisms commonly confused with rollback:

- `catch` decides how to handle or propagate an exception; it does not undo any assignments.
- `finally` runs when leaving a block to clean up resources and auxiliary state; by itself it has no transactional semantics.
- `try-with-resources` calls `close()` according to the resource's contract. Closing a file does not delete bytes already written, and closing a connection does not replace designing `commit()/rollback()`.
- `synchronized` automatically releases the monitor when a block/method exits due to an exception, but updates already performed are not undone.
- `Thread.currentThread().interrupt()` relates to propagating cancellation/wait signals, not restoring data.

To design recovery properly, first list every **side effect** and determine when each can occur.

## 4. When Can Independent Preparation Replace Manual Rollback?

If all changes are confined to **an in-memory snapshot owned by the method**, it is best to prevent half-baked state from appearing in the first place: prepare a candidate value and replace the published version only after all checks succeed.

~~~java
// Illustration in a class with current: Map<String, Integer>.
Map<String, Integer> candidate = new HashMap<>(current);
candidate.put("items",
        Math.addExact(candidate.get("items"), increment));
Map<String, Integer> ready = Map.copyOf(candidate);
current = ready; // Publication point within a single-writer scope.
~~~

If `Math.addExact` or creating `ready` fails **before the final assignment**, `current` still references the old version. However, `HashMap` only performs a shallow copy: do not mutate shared value objects during preparation. With multiple writers, appropriate locking/CAS is needed to avoid lost updates; `volatile` alone does not make read–compute–write atomic.

**Important boundary with rollback:** this approach **avoids having to undo** internal assignments before commit; it does not restore a DB, file, network request, or callback that has already caused side effects. Once changes occur outside the snapshot, you need a transaction/undo/compensation with its own contract and must account for the possibility that **the undo operation itself fails**. Therefore, try prepare–publish first, and choose rollback only when the data scope and recovery mechanism genuinely permit it.

## 5. Runnable Java 17+ Example: Before Commit and After Commit

This program models an in-JVM balance ledger. The `transfer` operation computes on a copy and publishes the new version only at the end. The `transferThenNotify` operation demonstrates that a **post-commit failure** does not automatically revert balances to their old state.

Save the file as **`StateRollbackDemo.java`**:

```java
import java.io.IOException;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class StateRollbackDemo {
    @FunctionalInterface
    interface Notifier {
        void send() throws IOException;
    }

    static final class Ledger {
        private volatile Map<String, Long> balances =
                Map.of("A", 100L, "B", 50L);

        synchronized void transfer(
                String from, String to, long amount, boolean failBeforeCommit)
                throws IOException {
            Objects.requireNonNull(from, "from");
            Objects.requireNonNull(to, "to");
            if (from.equals(to) || amount <= 0) {
                throw new IllegalArgumentException("invalid transfer");
            }

            Map<String, Long> next = new HashMap<>(balances);
            Long source = next.get(from);
            Long target = next.get(to);
            if (source == null || target == null) {
                throw new IllegalArgumentException("unknown account");
            }
            if (source < amount) {
                throw new IllegalArgumentException("insufficient funds");
            }

            next.put(from, source - amount);
            next.put(to, Math.addExact(target, amount));
            if (failBeforeCommit) {
                throw new IOException("simulated failure");
            }

            balances = Map.copyOf(next);
        }

        void transferThenNotify(String from, String to, long amount,
                                Notifier notifier) throws IOException {
            Objects.requireNonNull(notifier, "notifier");
            transfer(from, to, amount, false);
            notifier.send();
        }

        @Override
        public String toString() {
            Map<String, Long> snapshot = balances;
            return "A=" + snapshot.get("A") + ", B=" + snapshot.get("B");
        }
    }

    public static void main(String[] args) throws IOException {
        Ledger ledger = new Ledger();
        System.out.println("Initial: " + ledger);

        try {
            ledger.transfer("A", "B", 20, true);
        } catch (IOException ex) {
            System.out.println("Before commit: " + ex.getMessage());
        }
        System.out.println("After failure: " + ledger);

        ledger.transfer("A", "B", 20, false);
        System.out.println("After success: " + ledger);

        try {
            ledger.transferThenNotify("A", "B", 5, () -> {
                throw new IOException("delivery timeout");
            });
        } catch (IOException ex) {
            System.out.println("Notify failure: " + ex.getMessage());
        }
        System.out.println("After notify failure: " + ledger);
    }
}
```

Compile and run on JDK 17 or later:

```bash
javac -encoding UTF-8 StateRollbackDemo.java
java StateRollbackDemo
```

Standard output:

```text
Initial: A=100, B=50
Before commit: simulated failure
After failure: A=100, B=50
After success: A=80, B=70
Notify failure: delivery timeout
After notify failure: A=75, B=75
```

**Analysis:**

- After building the intended state `A=80, B=70`, the fault-injection branch throws `IOException` before assigning `balances`. Consequently, readers still see `100, 50`.
- The non-failing call completes the assignment of the new map; the published state is `80, 70`.
- The third call transfers another `5` and **commits internally**; then the notifier throws `IOException`. The ledger data remains `75, 75`. Receiving an exception does not allow the caller to infer that “the transfer did not happen”; retrying the entire method could deduct money again.

The published map is immutable and holds immutable `Long` values. `synchronized` serializes the `transfer` writer; `volatile` safely publishes the reference so the `toString()` reader sees a consistent snapshot. However, this example only models two in-memory accounts without a real DB or network, and is not a substitute for real-money system design. The `failBeforeCommit` flag is solely a fault-injection mechanism. `Math.addExact` can throw an overflow error before commit, leaving the published state unchanged.

## 6. Manual Rollback with Snapshots: Usable but Easy to Get Wrong

For small changes, you can remember the old value:

```java
int oldBalance = balance;
try {
    balance -= amount;
    performNextStep();
} catch (Exception original) {
    balance = oldBalance;
    throw original;
}
```

This is an **illustrative snippet inside a method** that already has `balance`, `amount`, and `performNextStep()`; it does not compile standalone. It is safe only if reassigning `oldBalance` truly restores **all observable state** under the contract. Common pitfalls include:

- The same operation modified multiple fields, child objects, files, or external services; reassigning `balance` alone is not enough.
- A shallow snapshot may hold references to mutable objects that were already mutated.
- Another thread may have made a valid update in the meantime; rolling back to the old value will **overwrite that thread's update**.
- The undo operation itself can fail, especially if it must call a dependent system that is experiencing an outage.
- If a step already sent an email or payment, there is no “inverse assignment” in the JVM.
- `catch (Exception)` does not include `Error`. Do not arbitrarily widen it to `catch (Throwable)` just to claim rollback support for every failure.

When multiple steps have their own undo functions, they usually need to be undone **in reverse order**: `A → B → C`, then `undo(C) → undo(B) → undo(A)`. However, reverse order is **only an organizational condition**; it does not guarantee that undo will succeed or avoid additional side effects. Some actions, such as sending notifications, have no true inverse operation.

If possible, preserve the old state until the commit point and avoid needing manual rollback. If an undo log is unavoidable, accurately record which steps completed, the idempotency of undo operations, and which state is durably persisted for crash recovery.

## 7. JDBC Transactions: Rollback Only Within Transaction Scope

When multiple SQL statements must succeed together or fail together, use **a single connection and a single transaction**, rather than relying on Java exceptions. With JDBC, the basic flow is to disable auto-commit, execute all statements, and call `commit()` on success; if a `SQLException` occurs before commit, attempt `rollback()`.

The example below is **an illustrative JDBC method** requiring a configured `DataSource`, driver, `accounts(id, balance)` table, and a transaction-capable DB. It is **not a standalone program**. It assumes each `id` is unique, `balance` uses an appropriate numeric type, and each successful update affects exactly one row.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public static void moveMoney(DataSource dataSource,
                             long fromId, long toId, long amount)
        throws SQLException {
    if (amount <= 0 || fromId == toId) {
        throw new IllegalArgumentException("invalid transfer");
    }

    try (Connection conn = dataSource.getConnection()) {
        conn.setAutoCommit(false);
        try {
            try (PreparedStatement debit = conn.prepareStatement(
                    "UPDATE accounts SET balance = balance - ? " +
                    "WHERE id = ? AND balance >= ?")) {
                debit.setLong(1, amount);
                debit.setLong(2, fromId);
                debit.setLong(3, amount);
                if (debit.executeUpdate() != 1) {
                    throw new SQLException("source missing or insufficient funds");
                }
            }

            try (PreparedStatement credit = conn.prepareStatement(
                    "UPDATE accounts SET balance = balance + ? WHERE id = ?")) {
                credit.setLong(1, amount);
                credit.setLong(2, toId);
                if (credit.executeUpdate() != 1) {
                    throw new SQLException("destination missing");
                }
            }

            conn.commit();
        } catch (SQLException original) {
            try {
                conn.rollback();
            } catch (SQLException rollbackFailure) {
                original.addSuppressed(rollbackFailure);
            }
            throw original;
        }
    }
}
```

If the destination update fails **before `commit()`** and the DB allows rollback to succeed, the source debit in the same transaction is also discarded. Placing `balance >= ?` directly in the `UPDATE` statement avoids reading the balance in Java only for a concurrent transaction to change it before the write. However, real systems also need isolation design, locking, deadlock retries, constraints, overflow handling, monetary precision, and connection pooling.

**Important limitations:**

1. `rollback()` affects **the transaction on that connection**. It does not unsend emails, revert transactions committed on another DB, undo written files, or cancel HTTP requests already processed.
2. Some DBs, storage engines, or DDL statements have their own commit semantics; check the specific DB documentation.
3. If `rollback()` throws an exception, the system cannot claim recovery succeeded. `original.addSuppressed(rollbackFailure)` preserves the secondary error details.
4. If `commit()` throws an exception due to a lost connection, the outcome **may be indeterminate from the application's perspective**: the DB may have already committed while the response was lost. Attempting a rollback afterward does not prove the transaction did not commit.
5. `try-with-resources` closes `Connection` and `PreparedStatement`; it does not replace explicit transaction boundaries and rollback design.

In Java SE/JDBC, throwing an exception from calling code **does not implicitly call rollback on all connections**. Transaction frameworks may provide automatic rollback according to their own rules, but you still must know which method opens the transaction, when it commits, whether exceptions are swallowed, and which resources actually participate.

## 8. Rolling Back a File: Closing a Stream Does Not Delete Written Data

An error mid-way through writing a file can leave partial content behind; `try-with-resources` only manages closing the handle. When replacing **the entire content of a file**, the standard approach is:

1. Create a temporary file in the same filesystem/directory as the target file.
2. Write and close the temporary file; proceed only once the full new content is written.
3. Replace the target file with an atomic move/rename operation if supported by the filesystem.
4. If an exception occurs before replacement, delete the temporary file and keep the old target file.

Example snippet inside a method that already has `Path target`, `String newContent`, declares `throws IOException`, and imports `java.nio.file.Files`, `Path`, `StandardCopyOption`, `java.nio.charset.StandardCharsets`:

```java
Path absolute = target.toAbsolutePath();
Path directory = absolute.getParent();
Path temporary = Files.createTempFile(directory, ".staging-", ".tmp");
try {
    Files.writeString(temporary, newContent, StandardCharsets.UTF_8);
    Files.move(temporary, absolute,
            StandardCopyOption.ATOMIC_MOVE,
            StandardCopyOption.REPLACE_EXISTING);
} finally {
    Files.deleteIfExists(temporary);
}
```

This is an **illustrative snippet**, not a standalone program. `ATOMIC_MOVE` may not be supported by the filesystem and may throw `AtomicMoveNotSupportedException`; replacing an existing file during an atomic move is also implementation-dependent. *Atomic visibility* is also **different from durability across power loss**; systems requiring high durability must consider platform-specific file and directory flush/sync. Cleaning up the temporary file in `finally` can also fail. Do not silently fall back to a non-atomic copy if the contract requires strong guarantees.

Even when file replacement succeeds atomically, it is still **not in the same transaction** as a DB or HTTP service that the method may also have called.

## 9. Why Rollback Does Not Cover Distributed Systems

Each system has its own state and commit boundary. If A has already committed and B fails, rolling back B cannot automatically reverse A's result. Events already observed externally cannot be “un-happened” either.

| External Operation | What Local Rollback Cannot Solve | Mechanism to Consider |
| --- | --- | --- |
| Send email/SMS/push | Recipient may have already seen the notification | Outbox, delivery status, follow-up correction when needed |
| Call payment API | Receiver may have processed it while ACK was lost | Idempotency key, status lookup, business compensation |
| DB A commits then DB B fails | Two DBs do not automatically share a transaction | Distributed transaction when supported, or Saga/outbox |
| Write file then roll back DB | File is outside DB transaction scope | Commit ordering plan, recovery, and reconciliation |
| Send message then fail | Consumer may have received/processed it | Delivery guarantees, deduplication, idempotent consumer |

**A timeout does not mean failure.** The client may have sent the command; the server committed; the network dropped before the response arrived. If the client sends a **new command** assuming the first did not execute, it can cause duplicate side effects. For critical workflows, you need an “**unknown outcome**” state, stable request/transaction IDs, and a way to query status.

### Saga and Compensation

A Saga breaks a multi-system workflow into local transactions and corresponding compensating actions. For example, booking: **reserve → charge → confirm**. If charging fails, the reservation can be released; if charging succeeded but confirmation failed, a refund may be needed. Each compensating action can also fail, so you need bounded retry rules, durable progress tracking, idempotency, monitoring, and reconciliation. Sagas typically yield *eventual consistency* and **do not automatically provide system-wide ACID**.

A refund **does not erase the charge history**; it is a new transaction that may incur fees and emit other events. Do not call compensation an “atomic rollback” if external parties can observe intermediate states.

### Transactional Outbox

If a business operation must both update a DB and emit an event, one approach is to write **the business data and an outbox record in the same DB transaction**. After commit, a process reads the outbox and sends the message. This prevents the case where the DB commits but the program crashes before recording the intent to send; however, a consumer can still receive the same message multiple times if the sender loses the ACK. Therefore, you need an idempotent consumer and duplicate handling. Outbox is a scoped coordination mechanism, **not default end-to-end exactly-once**.

## 10. When Rollback Also Throws: Preserving the Root Cause

A common bug occurs when handling an `IOException` triggers an undo task that also throws `IOException`, overwriting the original error. You can preserve both using `addSuppressed`:

```java
try {
    performOperation();
} catch (IOException original) {
    try {
        undoOperation();
    } catch (IOException undoFailure) {
        original.addSuppressed(undoFailure);
    }
    throw original;
}
```

This is a **snippet inside a method declared with `throws IOException`** where `performOperation()` and `undoOperation()` are already defined. `addSuppressed` only preserves diagnostic information; it does not restore data by itself. If rollback fails, the state must be recorded as **unverified or requiring further handling** per the contract; never silently report “recovered”.

`try-with-resources` can also attach exceptions thrown during `close()` to the primary exception via `getSuppressed()`. This aids diagnosis, but closing a resource does not mean the business operation was undone.

If you must handle `InterruptedException`, preserve or restore the interrupt status according to the contract; do not collapse all exceptions and errors into a generic “rollback failed” that hides the critical root cause.

## 11. Retrying After Failure: Pre-Commit, Post-Commit, and Indeterminate

| When Failure Occurs | What Is Usually Known | Appropriate Action |
| --- | --- | --- |
| Invalid arguments before mutating data | Business action has not run | Fix input; do not retry with the same data |
| Validation fails on staged copy | Published state is unchanged | Fix the cause; conditional retry |
| DB error before commit, rollback confirmed | Transaction discarded within that DB scope | Retry if error is transient and operation is safe |
| Error during commit / lost response | Outcome may be unknown | Reconcile status by transaction/request ID |
| Notify error after commit | Core business action already succeeded | Do not re-run the whole workflow; recover only the notify step |
| Error during compensation | Compensation effect may be unknown | Record progress, inspect, bounded retry, or intervene |

Configure sensible timeouts, retry budgets, backoff/jitter, and idempotency for operations with side effects. For payments/transfers, avoid retrying with a new command if you do not know whether the previous command was recorded. There is no retry policy that is “safe for every exception”.

## 12. Documenting the Contract When a Method Throws Exceptions

Alongside `@throws`, an API should clearly document **the state after failure**. For example:

> If an error occurs before updating the ledger state, the published balances remain unchanged. If the update succeeds and sending the notification fails, the balances have changed; the caller must check the state before retrying.

The contract should answer:

1. Is the **recovery scope** an object, a collection, a DB transaction, or multiple systems?
2. What is the exact **commit point**? Are there multiple commit points across different dependencies?
3. What can a caller or another thread observe before commit?
4. On failure, is the state guaranteed to be **unchanged**, **valid though possibly modified**, or **indeterminate**?
5. Who owns the transaction and has authority to decide rollback?
6. How does the caller know whether to retry, query status, or perform compensation?

A well-named exception is helpful, but **it does not replace describing the actual state**. If wrapping exceptions at layer boundaries, preserve `cause` for traceability and do not turn every infrastructure error into an argument or state error.

## 13. Testing Recovery Conditions, Not Just Exceptions

A test that only asserts `assertThrows` does not prove safety. Tests should verify **before/after state**, dependency call counts, open resources, transaction traces, and side effects.

| Scenario | Expected Observation |
| --- | --- |
| Invalid arguments | No state change, no dependency calls |
| Failure while computing staged copy | Published copy unchanged, no leaked reference to partial copy |
| Failure between two transactional steps | All updates in the same transaction rolled back; DB invariants hold |
| Rollback also fails | Primary error preserved with rollback error attached; state marked unverified |
| Connection lost during `commit()` | Do not assume uncommitted; reconciliation workflow exists |
| Message send fails after commit | Core transaction persists; retry does not cause duplicate updates |
| Two concurrent requests mutate data | No lost updates; invariants remain intact |
| JVM crashes at different points | Recovers from durable storage without relying on RAM variables |

For `StateRollbackDemo`, the two key assertions are: after a fault injected **before commit**, balances remain `A=100, B=50`; after a notifier exception, balances are `A=75, B=75`. This clearly separates **failure of the overall step** from **state of the committed work**.

In integration testing, inject faults at exact boundaries: before write, after write but before commit, during commit, after commit before ACK, during rollback, and on restart. Mocking exceptions within the same JVM is insufficient to prove recovery after real power loss or network disconnection.

## 14. Common Mistakes When Implementing Rollback

- **Believing `catch` automatically reverses assignments:** exceptions only transfer control flow.
- **Using `finally` to restore everything:** it should generally be used for cleanup; undo has its own conditions and failure modes.
- **Taking a shallow copy and mutating child objects:** the snapshot is not truly isolated.
- **Restoring old values under concurrent writes:** easily overwrites valid updates from other threads.
- **Rolling back one DB and claiming the entire request was undone:** dependencies outside the transaction are unaffected.
- **Swallowing exceptions when rollback fails:** loses diagnostic traces and leads to false conclusions about data.
- **Treating a `commit()` timeout as definitely uncommitted:** can cause duplicate transactions.
- **Treating compensation as erasing all history:** compensation is a new action with its own risks.
- **Retrying the entire workflow after a notification failure:** may execute the core business operation a second time.
- **Testing only the happy path:** rollback guarantees must be exercised at specific failure points.

## 15. Practical Implementation Checklist

1. Map out the sequence of steps with side effects and the resources involved.
2. Specify the **post-failure guarantee level** for each resource and observable scope.
3. Push fallible operations before the commit point whenever possible.
4. For Java state, prefer copy/staging + single publication; protect concurrency and mutable child objects.
5. For DBs, clearly define transaction boundaries, isolation, locking, and rollback.
6. For files, define atomicity and durability requirements and a temporary-file cleanup plan.
7. For multiple services, design outbox, idempotency, compensation, or appropriate coordination.
8. Preserve the root cause and recovery failure details; record state when the outcome is uncertain.
9. Reconcile before retrying when commit or ACK is uncertain.
10. Test both state and side effects before/after commit, when undo fails, and when the application crashes.

**Key principle:** proper exception handling must ensure **post-failure state conforms to the contract**. Rollback is meaningful only within a controllable scope; once a side effect has been recorded by an external system, the solution is usually controlled reconciliation and compensation—not a `catch` block that can “turn back time”.
