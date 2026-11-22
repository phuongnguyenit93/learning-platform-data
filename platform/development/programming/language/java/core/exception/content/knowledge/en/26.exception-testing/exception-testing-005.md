# Checking Object State After a Method Fails

An exception test should not only ask **“did the method throw the right exception?”**. An equally important question is: **“what state is the object in after throwing?”** If a method has already deducted a balance, added an element, changed an order status, or acquired a resource before detecting an error, the caller may receive the expected exception type while the object has been partially mutated and is no longer valid.

For example: `reserve(10)` throws `InsufficientStockException` but 10 units have already been deducted from stock; `transfer()` throws `IOException` when sending a notification but the amount has already been debited from the source account; `registerListener()` throws midway through but the listener remains in the registration list. These bugs **go undetected** if the test only uses `assertThrows`.

This topic belongs to **Testing** in Java Core – Exception. The goal is to know how to define exception-safety guarantees, capture before/after snapshots, verify invariants and side effects, inject failures at execution checkpoints, and write reliable Java 17 tests.

## 1. The Right Exception Type Does Not Guarantee Valid Object State

The following code only **illustrates an anti-pattern** and is not a standalone program:

```java
class Inventory {
    private int stock = 5;

    void reserve(int quantity) {
        stock -= quantity;  // Mutate state first.
        if (stock < 0) {
            throw new IllegalStateException("not enough stock");
        }
    }
}
```

If the caller invokes `reserve(10)`, the method throws `IllegalStateException` as expected, but `stock` has become `-5`. A test that only checks the exception will **PASS even though the object is corrupted**.

```java
assertThrows(IllegalStateException.class,
        () -> inventory.reserve(10)); // Not enough.
```

This is a JUnit 5 snippet that requires a project with the JUnit library configured and an `inventory` variable. After the exception is thrown, the test must also verify stock, reservation lists, status flags, and related resources according to the contract.

A logically complete test has the following structure:

```text
Given: valid initial state S0
When:  invoke the method with an intentionally triggered failure
Then:  exception has the expected type/cause
And:   post-failure state satisfies the documented guarantee level
And:   invariants still hold
And:   resources and side effects do not leak
```

Not every method has to preserve its state unchanged after every failure. What must be verified is the **guarantee level promised by the API**: completely unchanged, valid state with permitted partial changes, or merely cleaning up certain resources.

## 2. Three Levels of Exception Safety Guarantees

A useful classification is the *exception safety guarantee* levels. They describe the **observable state after failure**, not just the type of exception thrown.

| Guarantee Level | What Is Guaranteed on Failure | Example |
| --- | --- | --- |
| **No-throw guarantee** | By contract, the operation does not throw exceptions, typically very simple cleanup; the scope of the guarantee must be clearly defined | `close()` of an in-memory handle designed not to throw. |
| **Strong exception guarantee** | If the operation fails, the observable state is unchanged compared to before the operation; “commit or no change” | Build the new state and assign it only after every failable step succeeds. |
| **Basic exception guarantee** | Even on failure, object invariants still hold and no resources leak, though permitted partial changes may have occurred | An import successfully processes 7 records and fails on the 8th; the 7 records remain in effect per contract. |

These terms are useful for designing and testing Java, but **they are not three annotations or three standard exception types in the Java language**. An API must explicitly document the appropriate guarantee level.

### The Strong Guarantee Is Scoped

“Unchanged” must be defined in terms of **observable state through the contract**. A method might increment an internal telemetry counter on failure without altering business state, but if the counter is part of the observable API, the test must account for it. Likewise, caches, listeners, temporary files, events, and databases may live outside the object’s fields yet still be important side effects.

Do not promise “everything rolls back” if the API only guarantees in-memory object state. For databases, networks, and third parties, undoing work has its own transaction or reconciliation boundaries.

### The Basic Guarantee Must Still Preserve Invariants

Basic does not mean leaving the object arbitrarily corrupted. If inventory does not allow negative stock, `stock >= 0` must hold **even after a failure**, even if some earlier items were successfully reserved. Do not invoke “partial progress” to legitimize an impossible state.

### No-Throw Is Not Exempt from Testing

A cleanup method designed not to throw still needs tests for idempotency, state changes, listener removal, permit release, and behavior when called twice. Do not assume every `AutoCloseable.close()` is no-throw: `AutoCloseable.close()` declares `throws Exception`, and implementations can fail.

## 3. Define Invariants Before Writing Tests

An *invariant* is a condition that must hold at valid observation points of an object’s state, especially after a constructor or a public method completes — whether it succeeds or fails, depending on the contract.

Example for a shopping cart / inventory object:

- `availableStock >= 0`.
- `reservedQuantity >= 0`.
- `reservedQuantity <= initialStock` within an inventory scope that assumes no replenishment.
- Total allocated quantity is consistent with remaining stock.
- No orphaned reservation records exist when the operation is guaranteed atomic.
- No open resources are left behind if the method exits and ownership scope has ended.

An invariant must have **clear business meaning**. If the system allows negative stock to represent backorders, testing `stock >= 0` violates the contract. Avoid encoding unguaranteed implementation details into tests, which causes tests to break on harmless refactors.

When defining state for comparison, do not look only at a single field like `status`. State can be corrupted in a collection, balance, version, resource handle, cache, subscription, or external side effect even if the `status` enum remains the same.

## 4. Do Not Use assertThrows Alone

In JUnit 5, `assertThrows` checks that a code block throws an exception of the required type or a subtype. It **does not check** object state:

```java
IllegalStateException thrown =
        assertThrows(IllegalStateException.class,
                () -> inventory.reserve(10));

assertEquals("not enough stock", thrown.getMessage());
assertEquals(5, inventory.availableStock());
assertEquals(List.of(), inventory.reservations());
```

This is a **JUnit 5 snippet** requiring JUnit imports/static imports, the `Inventory` class, and methods matching the actual API; it cannot be run with bare `javac` alone. Checking the message is useful when the message is part of the contract; if the message is diagnostic text that may change, it is usually better to check the stable type, error code, and cause rather than locking tests to exact wording.

Post-exception assertions should verify:

1. **Failure type:** checked/unchecked, subtype, domain code, cause.
2. **Unchanged or partially changed state:** according to the guarantee level.
3. **Invariants:** validity of all critical fields and relationships.
4. **Side effects:** persistence, events, email, queues, files, logs if required by the contract.
5. **Resource lifecycle:** closing handles, releasing permits, unlocking, unregistering.
6. **Usability afterward:** can the object continue operating validly after the failure?
7. **Concurrency:** is state consistent with other threads according to the contract?

**A test with the right exception but wrong state must FAIL.** That is the core value of this lesson.

## 5. Before/After Snapshots: The Clearer Comparison

To verify a strong guarantee, capture an **independent snapshot** of the observable state before the call, then compare it with a snapshot taken after the exception has been caught.

Mental template:

```java
State before = object.snapshot();

assertThrows(ExpectedException.class,
        () -> object.perform(invalidInput));

State after = object.snapshot();
assertEquals(before, after);
```

This is an illustrative JUnit snippet with application-specific `State` and `ExpectedException` types. The snapshot must capture all parts of the state required by the contract; a snapshot containing only `status` may not be enough.

### Snapshots Must Be Truly Independent

If a snapshot holds a reference to a mutable `ArrayList` owned by the object, subsequent mutations can cause the snapshot to “change along with it,” producing a **false pass** on the before/after comparison.

Wrong example:

```java
List<String> before = inventory.getReservations();
inventory.reserve(...);
assertEquals(before, inventory.getReservations());
```

If `getReservations()` returns the internal list itself, `before` and the post-call value are the **exact same object**; both observe the mutation. Fix: copy it:

```java
List<String> before = List.copyOf(inventory.getReservations());
```

`List.copyOf` creates an unmodifiable list, but this is only a **shallow copy**: if elements are mutable objects, mutating an element’s field will still appear in the snapshot. For object graphs with nested mutable state, you need a **deep snapshot** per contract, using immutable DTOs/records or controlled serialization/copying.

Note that `List.copyOf` rejects `null` elements. If the domain allows nulls, choose an appropriate representation/copy mechanism so you do not accidentally break the test while taking the snapshot.

## 6. Complete Java 17 Example: Detecting Corrupted State and Fixing with Staged Commit

The following example shows two ways to update the same `Inventory` type:

- `reserveUnsafe` mutates state first and checks the stock condition afterward.
- `reserveSafe` validates first, builds a candidate state **in a local variable**, and then commits via **a single reference assignment**; if validation or candidate construction fails before commit, the old state is preserved.

Create `InventoryExceptionStateDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class InventoryExceptionStateDemo {

    private record State(int available, List<String> reservations) {
        State {
            reservations = List.copyOf(reservations);
        }
    }

    private static final class Inventory {
        private State state = new State(5, List.of());

        State snapshot() {
            return state;
        }

        void reserveUnsafe(String item, int quantity) {
            Objects.requireNonNull(item, "item");
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity <= 0");
            }

            State old = state;
            List<String> next = new ArrayList<>(old.reservations());
            next.add(item + ":" + quantity);

            // Wrong: commit before checking the failure condition.
            state = new State(old.available() - quantity, next);

            if (state.available() < 0) {
                throw new IllegalStateException("insufficient stock");
            }
        }

        void reserveSafe(String item, int quantity) {
            Objects.requireNonNull(item, "item");
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity <= 0");
            }

            State old = state;
            if (quantity > old.available()) {
                throw new IllegalStateException("insufficient stock");
            }

            List<String> next = new ArrayList<>(old.reservations());
            next.add(item + ":" + quantity);
            State candidate =
                    new State(old.available() - quantity, next);

            // Commit after all validation/preparation succeeds.
            state = candidate;
        }
    }

    public static void main(String[] args) {
        Inventory unsafe = new Inventory();
        State beforeUnsafe = unsafe.snapshot();

        try {
            unsafe.reserveUnsafe("book", 7);
        } catch (IllegalStateException ex) {
            System.out.println("unsafe exception: " + ex.getMessage());
        }
        System.out.println("unsafe unchanged: "
                + beforeUnsafe.equals(unsafe.snapshot()));
        System.out.println("unsafe state: " + unsafe.snapshot());

        Inventory safe = new Inventory();
        State beforeSafe = safe.snapshot();

        try {
            safe.reserveSafe("book", 7);
        } catch (IllegalStateException ex) {
            System.out.println("safe exception: " + ex.getMessage());
        }
        System.out.println("safe unchanged: "
                + beforeSafe.equals(safe.snapshot()));
        System.out.println("safe state: " + safe.snapshot());

        safe.reserveSafe("book", 2);
        System.out.println("safe success: " + safe.snapshot());
    }
}
```

Run with Java 17+:

```bash
javac -encoding UTF-8 InventoryExceptionStateDemo.java
java InventoryExceptionStateDemo
```

Stdout:

```text
unsafe exception: insufficient stock
unsafe unchanged: false
unsafe state: State[available=-2, reservations=[book:7]]
safe exception: insufficient stock
safe unchanged: true
safe state: State[available=5, reservations=[]]
safe success: State[available=3, reservations=[book:2]]
```

Analysis:

1. `beforeUnsafe` and `beforeSafe` are `record State` instances that are immutable with respect to the `String` elements in this example; the list is copied in the constructor. Therefore, the prior snapshot does not mutate with the current state.
2. `reserveUnsafe("book", 7)` assigned a new state with `available=-2` and reservation `book:7` before throwing. The exception is right, but the **non-negative stock** invariant is broken.
3. `reserveSafe("book", 7)` checks for failure **before any commit**. When it throws, `state` still references the previous record; `equals` returns `true`.
4. Calling `reserveSafe("book", 2)` succeeds and produces `State[available=3, reservations=[book:2]]`.
5. The safe method prepares the new state before assigning it. This achieves a strong guarantee **within the scope of this example’s in-memory state, when executed exclusively by a single thread**.

**Important limitation:** `Inventory` has no synchronization and is therefore **not thread-safe**; two threads reading the same `State` and overwriting each other can cause a lost update. An exception-safety guarantee does not replace thread safety. `List.copyOf` is a shallow copy; in this example the elements are immutable `String`s. For databases/networks, you need transactions or idempotency/reconciliation rather than expecting a single Java field assignment to roll back out-of-process side effects.

## 7. Stronger Testing: Self-Contained Java 17 Assertions Without JUnit

To clearly show that tests must verify both the exception and the state, the following example **runs standalone with the JDK** and throws `AssertionError` explicitly instead of relying on the `-ea` flag.

Create `ExceptionStateAssertionsDemo.java`:

```java
import java.util.List;
import java.util.Objects;

public class ExceptionStateAssertionsDemo {

    private static final class Account {
        private int balance = 100;
        private List<String> history = List.of();

        int balance() {
            return balance;
        }

        List<String> history() {
            return history;
        }

        void withdraw(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
            if (amount > balance) {
                throw new IllegalStateException("insufficient funds");
            }

            List<String> nextHistory =
                    new java.util.ArrayList<>(history);
            nextHistory.add("withdraw:" + amount);

            // All steps that can detect errors have completed.
            history = List.copyOf(nextHistory);
            balance -= amount;
        }
    }

    private static <T extends Throwable> T expectThrows(
            Class<T> type, Runnable action) {
        try {
            action.run();
        } catch (Throwable error) {
            if (type.isInstance(error)) {
                return type.cast(error);
            }
            throw new AssertionError("wrong exception type", error);
        }
        throw new AssertionError("expected " + type.getSimpleName());
    }

    private static void check(boolean condition, String explanation) {
        if (!condition) {
            throw new AssertionError(explanation);
        }
    }

    public static void main(String[] args) {
        Account account = new Account();
        int balanceBefore = account.balance();
        List<String> historyBefore = List.copyOf(account.history());

        IllegalStateException ex = expectThrows(
                IllegalStateException.class,
                () -> account.withdraw(120));

        check(Objects.equals(ex.getMessage(), "insufficient funds"),
                "wrong message");
        check(account.balance() == balanceBefore,
                "balance changed after failure");
        check(account.history().equals(historyBefore),
                "history changed after failure");
        check(account.balance() >= 0, "negative balance");

        System.out.println("exception checked");
        System.out.println("state unchanged: true");
        System.out.println("invariants checked");

        account.withdraw(40);
        check(account.balance() == 60, "success balance wrong");
        check(account.history().equals(List.of("withdraw:40")),
                "success history wrong");
        System.out.println("success after failure: " + account.balance());
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 ExceptionStateAssertionsDemo.java
java ExceptionStateAssertionsDemo
```

Stdout:

```text
exception checked
state unchanged: true
invariants checked
success after failure: 60
```

A key takeaway is testing **continued usability** after a failure. `withdraw(120)` must be rejected and preserve state; afterward, `withdraw(40)` must still work normally. If the object was silently corrupted after the failure, the subsequent happy-path test can catch issues that inspecting a single field misses.

In the demo, `expectThrows` catches `Throwable` only to demonstrate a deterministic assertion helper; **this is not a production business error-handling strategy**. Real tests should use JUnit 5 `assertThrows` or `assertThrowsExactly` with appropriate semantics and avoid writing custom utilities when the framework already provides them.

## 8. Test Exception Guarantees from the Outside, Not Coupled to Private Fields

If an object exposes a public API:

```java
int availableStock();
List<ReservationView> reservations();
InventoryStatus status();
```

then tests should prioritize checking these **contract-level observations**. There is no need to read private fields via reflection unless you genuinely must verify an unexposed invariant and the test is explicitly designed for that implementation.

A test should follow this structure:

```text
Given:
  - construct the object in a well-defined valid state
  - take a snapshot via the public/read-only API
When:
  - invoke the method and force a specific failure path
Then:
  - assert exception type/code/cause
  - assert state per strong or basic guarantee
  - assert invariants across fields
  - assert no out-of-scope side effects
  - assert continued usability or transition to FAILED state per contract
```

If the implementation changes from a mutable collection to an immutable record while public state stays the same, contract tests should still PASS. Tests that depend too heavily on setter call counts or field assignment order break unnecessarily during refactoring.

However, when you must guarantee **external systems are not called if validation fails**, using a fake/mock adapter to verify “not called” is appropriate, because that is a contract-level side effect rather than an accidental implementation detail.

## 9. When Only the Basic Guarantee Applies: Verify Permitted Progress

A batch-processing API might not promise atomicity for the entire list. For example:

```java
void importRows(List<Row> rows) throws ImportException;
```

This is an illustrative signature; application-specific `Row` and `ImportException` are not defined. If the contract states “records completed before the failing record remain persisted,” the test must **not assert that the entire batch is unchanged**.

Suppose row 1 and row 2 are written successfully, and row 3 is invalid. A basic-guarantee test can check:

- Row 1 and row 2 exist exactly once.
- Row 3 is not written as a malformed or half-written record.
- Counters/sequences are not corrupted.
- Indexes/caches preserve invariants.
- No resource or transaction handles leak.
- Checkpoints or resume cursors match the contract.
- Re-invoking with retry/resume mechanisms does not duplicate already succeeded records.

If the system **promises an atomic batch**, that same outcome is a bug — the test must verify full rollback. Therefore, **state the guarantee first, write assertions second**. Do not apply a single generic “unchanged” assertion suite to every API.

## 10. Catching Partial Mutation When Validation Comes Too Late

A very common bug:

```java
void updateProfile(UserProfile profile, String newEmail) {
    profile.setEmail(newEmail);
    if (!isValidEmail(newEmail)) {
        throw new IllegalArgumentException("invalid email");
    }
    notifyObservers(profile);
}
```

This is an illustrative snippet assuming `UserProfile`, `isValidEmail`, and `notifyObservers`. A test that only checks the exception will miss that `profile.email` was already changed to the invalid value.

The usual improvement is **validate first**:

```java
void updateProfile(UserProfile profile, String newEmail) {
    if (!isValidEmail(newEmail)) {
        throw new IllegalArgumentException("invalid email");
    }
    profile.setEmail(newEmail);
    notifyObservers(profile);
}
```

However, this fix only handles validation errors that occur before mutation. If `notifyObservers` throws an exception after `setEmail`, the profile **has still changed**. Thus, validate-first is **not sufficient for a strong guarantee if post-commit steps can fail**.

Possible designs:
- Prepare data and run all validation before commit.
- Commit in-memory state via an atomic assignment point at the object boundary.
- Perform notification post-commit as a separate effect with a clear contract: if notification fails, does the profile update roll back or remain committed?
- If the API requires atomicity together with notification, you need coordination/transactions/an outbox, not simply swapping two lines.

Tests must inject failures at **every failable step**, not only with invalid input.

## 11. Failure Injection Testing at Execution Checkpoints

Invalid input only exercises one failure path. To know whether a method satisfies a strong or basic guarantee, you must trigger failures at multiple points:

| Failure Point | What to Verify After Failure |
| --- | --- |
| Input validation | No mutation; no dependency calls. |
| After building candidate state | Candidate is discarded; old state remains intact. |
| When allocating the second resource | The first resource is closed if the owner already acquired it. |
| After first mutation but before second mutation | Invariants and rollback per contract. |
| When saving to the database | Transaction rolls back or pending/unknown state is accurate. |
| When emitting event/notification | Record business commit state separately from event delivery. |
| When cleanup/close throws an exception | Primary error/suppressed exceptions are not lost; resource state is observable. |
| When callback/retry is interrupted | Stops per policy; object is not left in a broken half-closed state. |

**Failure injection** can use a fake adapter configured to throw an exception on the N-th call, or a fault injector in integration tests. Do not rely on the real network failing naturally at the right spot — such tests are hard to reproduce and often miss the most dangerous checkpoints.

In Java, small interfaces make testing easier:

```java
interface Store {
    void save(Order order) throws IOException;
}
```

This snippet only describes the contract; `Order` and imports must be defined. Tests use a fake `Store` that can throw `IOException` before/after the write operation to verify that the service handles state properly in each scenario.

**Important:** simulating “throw before write” and “throw after write” must be **two distinct scenarios**. If a timeout arrives after the server commits, rolling back client-side memory does not undo the server-committed transaction. The outcome may be *unknown/pending*, not “no side effect.”

## 12. Java 17 Example: Single Commit Point

For in-memory state, a “compute first, assign later” design achieves a strong guarantee if there are no observable side effects before commit.

Create `AtomicStateCommitDemo.java`:

```java
import java.util.Objects;

public class AtomicStateCommitDemo {

    private record Balance(int alice, int bob) {}

    private static final class Ledger {
        private Balance balance = new Balance(100, 50);

        Balance snapshot() {
            return balance;
        }

        void transfer(int amount, boolean failBeforeCommit) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount <= 0");
            }

            Balance old = balance;
            if (amount > old.alice()) {
                throw new IllegalStateException("insufficient funds");
            }

            Balance candidate =
                    new Balance(old.alice() - amount, old.bob() + amount);

            if (failBeforeCommit) {
                throw new IllegalStateException("injected failure");
            }

            // Single state reference assignment.
            balance = candidate;
        }
    }

    public static void main(String[] args) {
        Ledger ledger = new Ledger();
        Balance before = ledger.snapshot();

        try {
            ledger.transfer(30, true);
        } catch (IllegalStateException ex) {
            System.out.println("failure: " + ex.getMessage());
        }
        System.out.println("unchanged: " + before.equals(ledger.snapshot()));
        System.out.println("after failure: " + ledger.snapshot());

        ledger.transfer(30, false);
        System.out.println("after success: " + ledger.snapshot());
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 AtomicStateCommitDemo.java
java AtomicStateCommitDemo
```

Stdout:

```text
failure: injected failure
unchanged: true
after failure: Balance[alice=100, bob=50]
after success: Balance[alice=70, bob=80]
```

This is a single commit point for two balances **within the same in-memory object**. If an exception is triggered before the assignment, state remains unchanged. However, this is **not a real money transaction**: a production ledger also involves concurrency, persistence, auditing, isolation guarantees, and external side effects.

Even with a single reference field, if multiple threads read/write concurrently, you need appropriate synchronization such as locks or atomic CAS with invariants; a single-threaded test does not prove linearizability or concurrency safety. When `Balance` is an immutable record, a single reference swap avoids a “new alice, old bob” state within the same record, but proper publication/visibility is still required.

## 13. Testing Multiple Fields and Object Graphs

Real-world objects have complex relationships:

```text
Order
 ├── status
 ├── total
 ├── List<OrderLine>
 │    ├── quantity
 │    └── price
 └── paymentReference
```

A shallow snapshot that only copies `OrderLine` references may miss mutations to `quantity`. If the strong guarantee applies to the entire observable `Order`, the test must read/copy all fields of nested objects:

- Create immutable views/DTOs for each line.
- Compare lists by **value**, not just size.
- Verify consistency between total amount and quantities.
- Verify no events/records in secondary stores were added after the method call.
- When the object exposes collection views, verify they cannot be mutated internally in violation of the contract.

One strategy is to model business state as an immutable record/value object and have the owning object swap the entire state via a new reference. Do not confuse an immutable outer record with deep immutability if a field of the record is still a mutable `List` or entity.

When identity is intentional (e.g., guaranteeing the exact same object instance is returned), `assertSame` may be appropriate. When only state value equality is required, `assertEquals` or a semantic comparator is better and less coupled to implementation.

## 14. State Outside the Object: Database, Files, Events, and Email

If a method fails after affecting external systems, checking Java fields alone is **not enough**.

| Side Effect | Post-Failure Observation to Check |
| --- | --- |
| Database | Was the record committed? Did the transaction truly roll back? Was a unique key consumed? |
| File | Does a new or partially written file exist? Were temporary files cleaned up? |
| Queue/message | Was the event enqueued or published? Are duplicate sends deduplicated? |
| HTTP to another service | Is a lost response an unknown outcome? Is there an operation ID for reconciliation? |
| Email/notification | Was it sent before throwing? Does retry send it twice? |
| Cache/index | Is cache invalidation consistent with the source of truth? |
| Metrics/logs | If part of the observable contract, are counts/outcomes accurate? |

A failure after the commit step may be documented as **“operation succeeded, but reporting the result failed”** or **“outcome unknown”**; in that case, expecting the object/DB to be unchanged is unrealistic. The API should use a transaction/operation ID or stateful result so callers do not retry blindly.

The goal of testing is not to magically make every exception erase all side effects; it is to **accurately detect what happened and verify the contract**.

## 15. Cleanup and Ownership Are Also Testable State

A method may open a stream, acquire a permit, lock a mutex, or subscribe a listener. When it throws an exception, **proper cleanup** is part of preserving state.

Example:

```java
try (InputStream in = Files.newInputStream(path)) {
    parse(in);
}
```

This is an illustrative snippet; `path`, `parse`, and relevant imports are not declared. When `parse` throws an exception, try-with-resources still closes `in`. A test using a fake resource can count `close()` invocations and verify that **the right owner closed the right scope**.

Cases that need testing:

1. First resource opens successfully, opening the second resource fails: the first is closed.
2. Body throws an exception, `close()` succeeds: the primary error is preserved and the resource is closed.
3. Both body and `close()` throw: the exception from `close` is added to `getSuppressed()`, unless the implementation handles it differently.
4. A borrowed resource is passed into the method: the method **does not close it** if the contract does not transfer ownership.
5. Listener registered, then startup fails midway: the previously registered handle is unregistered if ownership was not transferred.
6. Failure in `Semaphore.acquire()` or `Lock.lockInterruptibly()`: do not release/unlock when acquisition did not succeed.
7. Cancellation/interruption: lifecycle returns an observable state; do not assume `cancel(true)` proves cleanup has finished.

Closing a resource does not necessarily roll back business state. `FileOutputStream.close()` does not erase already written bytes; `unsubscribe` does not undo callbacks that already ran. Therefore, tests must separate **lifecycle cleanup** from **business rollback**.

## 16. Java 17 Example: Both Body and close Throw

This example illustrates how to check object state when **two related exceptions** occur: the body error is primary; the `close()` error is suppressed; the resource-closed flag is verified independently.

Create `CleanupAfterFailureDemo.java`:

```java
import java.io.IOException;
import java.util.concurrent.atomic.AtomicBoolean;

public class CleanupAfterFailureDemo {

    private static final class Resource implements AutoCloseable {
        private final AtomicBoolean closed;

        Resource(AtomicBoolean closed) {
            this.closed = closed;
        }

        @Override
        public void close() throws IOException {
            closed.set(true);
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) {
        AtomicBoolean closed = new AtomicBoolean(false);

        try (Resource resource = new Resource(closed)) {
            throw new IllegalStateException("work failed");
        } catch (IllegalStateException ex) {
            System.out.println("primary: " + ex.getMessage());
            System.out.println("suppressed: " + ex.getSuppressed().length);
            System.out.println(
                    "cleanup error: " + ex.getSuppressed()[0].getMessage());
        } catch (IOException ex) {
            System.out.println("unexpected close-only: " + ex.getMessage());
        }

        System.out.println("close invoked: " + closed.get());
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 CleanupAfterFailureDemo.java
java CleanupAfterFailureDemo
```

Stdout:

```text
primary: work failed
suppressed: 1
cleanup error: close failed
close invoked: true
```

**Accurate interpretation:** `closed=true` in this example only means **`close()` ran up to the point of setting the flag**. Because `close()` still threw `IOException`, you must not conclude that all production resources were successfully released. For real files, sockets, connections, or buffer flushes, complete cleanup must be evaluated according to that API’s contract and state.

A complete test verifies the primary exception, suppressed exceptions, recorded cleanup state, and whether the object/application can proceed after the failure per contract.

## 17. Checking State When Exceptions Are Wrapped or Translated

A method may catch a low-level error and throw a more stable exception type:

```java
try {
    repository.save(entity);
} catch (SQLException ex) {
    throw new RepositoryException("save failed", ex);
}
```

This is an illustrative fragment; `repository`, `entity`, `RepositoryException`, and imports are not defined. Tests should not stop at `RepositoryException`:

- Is `getCause()` the original SQL error?
- Did the repository transaction roll back or commit?
- Was the in-memory entity mistakenly marked `SAVED`?
- Was the cache partially updated?
- If the operation might have committed but the response was lost, is there a **pending/unknown** state and reconciliation mechanism?

If the method catches and **swallows the exception**, the test must verify an explicit fallback or domain result; an error must never turn into a false success with inconsistent state.

### Catching Failures at the Right Boundary

When testing at the service layer, inject repository failures into a fake; assert service state and dependency calls. When testing at the repository layer, use a real transaction/test database to verify rollbacks and constraints. **Do not try to use a mocked unit test to prove all ACID guarantees of a production database.**

## 18. JUnit 5: Template for Testing Exceptions and State with Snapshots

For a class with appropriate public methods and snapshot support, a JUnit 5 test can look like:

```java
import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

class InventoryTest {

    @Test
    void reserveFailureLeavesStateUnchanged() {
        Inventory inventory = new Inventory(5);
        InventorySnapshot before = inventory.snapshot();

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> inventory.reserve("book", 7));

        InventorySnapshot after = inventory.snapshot();

        assertAll(
                () -> assertEquals("insufficient stock", error.getMessage()),
                () -> assertEquals(before, after),
                () -> assertEquals(5, after.available()),
                () -> assertEquals(0, after.reservations().size())
        );
    }
}
```

**This is a JUnit template, not a standalone JDK-runnable file:** `Inventory`/`InventorySnapshot` are application types that must be implemented, and JUnit 5 is an external dependency outside the JDK. The snippet demonstrates checking both the exception and state; do not assume JUnit is built into Java 17.

`assertAll` runs a group of assertions and collects multiple failures, aiding diagnosis of complex state. However, if `after` is null or a getter throws an exception, one assertion may need to be ordered earlier to avoid masking the root cause of the test failure.

If subtypes are acceptable, `assertThrows(ExpectedException.class, ...)` is appropriate. If the contract demands the **exact type without subtypes**, JUnit 5 provides `assertThrowsExactly` in supported versions; use it only when truly required, not merely to make tests overly brittle.

## 19. Testing Recovery After an Object Fails Once

An object may pass an “unchanged state” test yet remain unusable because a `busy` flag, lock, queue, or resource is stuck.

A useful test sequence:

1. Create a valid object.
2. Call the method with failing input.
3. Assert the exception type, state, and invariants after failure.
4. Call **a valid operation**.
5. Verify the valid operation succeeds and the new state is correct.
6. If the object must transition to an unusable state (`FAILED`/`CLOSED`), verify that subsequent calls are rejected with the contract-defined exception.

The `Account` example in section 7 rejected withdrawing `120` yet still allowed withdrawing `40` afterward. This is a very valuable check for stateful service/resource objects with a lifecycle.

For objects marked `FAILED`, tests should not demand normal operation if the contract requires discarding/recreating them. The right guarantee is **never pretending to be usable when state is unsafe**.

## 20. State Machines and Transition Validity

For a lifecycle:

```text
NEW → OPEN → ACTIVE → CLOSED
             |
             +→ FAILED
```

If `activate()` throws midway, the object must end up in a designed state: still `OPEN` (strong guarantee), or `FAILED` (basic guarantee) if rollback is impossible. An object must never have `state=ACTIVE` while lacking the resources required to actually operate.

Tests should specify:

- Which states are valid?
- Which transitions are allowed?
- On exception at each transition, what is the resulting state?
- Are resources cleaned up when transitioning to `FAILED` or `CLOSED`?
- Are repeated `close`/`activate` calls idempotent or clearly throwing?
- Can the object recover, or must it be recreated?
- Can any event callbacks still fire after unregistering?

If the state enum changed while the corresponding resources did not, invariants may be broken. You must check the **state machine and its dependencies**, not only the enum.

## 21. Concurrency: Correct Post-Exception State Still Needs Thread Safety

Single-threaded tests only verify part of the picture. A method can preserve state on the exception path yet still have a race condition:

```java
State old = state;
State next = compute(old);
state = next;
```

This is an illustrative snippet. If two threads both compute from `old` and assign, one update can be lost. A strong exception guarantee **does not imply** linearizability, cross-thread atomicity, or safe publication.

Testing approaches:

- Use `CountDownLatch`/`CyclicBarrier` to create controlled interleavings right before commit.
- Inject a failure in one thread while another thread is reading or updating.
- Verify invariants hold and observed results match the synchronization contract.
- When using `synchronized`/locks/CAS, verify there are no deadlocks or lost updates.
- If cleanup callbacks happen on a background thread, **wait for an explicit completion signal**, rather than guessing with `Thread.sleep(50)`.
- With `Future.cancel(true)`, the future’s canceled status does not prove the worker finished cleanup; use an acknowledgment/`CountDownLatch` when required by the contract.

**Do not inspect state immediately after merely requesting cancellation and claim cleanup is broken** if the API allows asynchronous cleanup. Distinguish the “cancellation requested” checkpoint from the “cleanup completed” checkpoint.

## 22. Property-Based and Fault-Injection Testing

A few isolated examples are not enough to prove general invariants. You can test across many inputs and failure points:

- Generate negative, zero, less-than-stock, equal-to-stock, and greater-than-stock quantities; check invariants and guarantees for each branch.
- Generate interleaved sequences of valid and failing operations; the object remains valid after every step.
- Inject failures after preparation steps A, B, and C and before commit to verify state stays unchanged if the API promises strong guarantees.
- Inject cleanup failures to verify suppressed exceptions.
- With multiple resources, fail when opening the N-th resource; verify earlier resources are closed.
- With retries, throw transient errors after side effects occurred to detect duplicates.
- With transactions, simulate lost responses after commit and verify UNKNOWN marking/idempotency logic.
- With concurrent APIs, deliberately vary thread ordering and check invariants under contention.

You can use an external property-based testing framework (such as jqwik) or write data-driven loops. Do not rely on unseeded random inputs that cause non-reproducible flaky tests. Save the seed and scenario whenever a trial fails for debugging.

### Useful Properties

```text
If reserve(q) fails under a strong guarantee:
    snapshotAfter == snapshotBefore

In every valid inventory state:
    available >= 0
    all reservation quantities > 0

If transfer(a→b,q) succeeds in a zero-fee ledger:
    balanceA + balanceB is unchanged

If transfer fails before commit:
    both balanceA and balanceB are unchanged

If close/cleanup completes per contract:
    the owner no longer holds open resources
```

These are **conditional illustrative properties**. For instance, total balance is invariant only when there are no fees or transfers leaving the ledger; do not apply them outside their assumptions.

## 23. Distinguishing Unit, Integration, and End-to-End Tests

| Level | Well Suited to Verify | Limitations |
| --- | --- | --- |
| **Unit** with fakes/mocks | Java state, snapshots, call counts, injected exception checkpoints, basic/strong logic | Does not prove real transactions or network commits. |
| **Integration** with test DB/filesystem/message broker | Rollbacks, constraints, file cleanup, transaction boundaries, interacting side effects | May not cover every race or infrastructure outage. |
| **End-to-end** across multi-service systems | Operation IDs, retry/idempotency, UNKNOWN state, post-incident recovery | Expensive and hard to fault-inject at every exact point; requires stability tracking. |

Every layer must verify both exceptions **and state** at that boundary. A fake DB throwing `IOException` before writing helps unit-test the service, but does not prove the real DB won’t commit if the connection drops right after the `COMMIT` statement.

## 24. Common Testing Mistakes

**Asserting only the exception type.** Misses mutations and broken invariants. Always add state/side-effect assertions per contract.

**Taking snapshots by referencing a mutable list.** Before and after states mutate together, causing false passes. Create independent snapshots.

**Checking the wrong guarantee level.** The API only promises basic, yet the test demands all state be unchanged — or the API promises strong, yet the test checks only one field.

**Injecting failures only at the first step.** Misses bugs that happen after mutation or during cleanup. Use fault injection at key checkpoints.

**Checking only one field like `status`.** Misses balances, collections, versions, resources, events, and DB state.

**Asserting on unstable exception messages.** Tests break on wording tweaks even when the contract hasn’t changed. Prefer stable types, codes, and causes.

**Ignoring nested mutable objects.** Shallow snapshots can miss mutations inside elements.

**Using a mock’s `save` invocation as proof of DB rollback.** A mock only verifies invocation, not real transaction semantics.

**Confusing a timeout with definite failure of a remote operation.** The outcome may be unknown; tests must represent PENDING/UNKNOWN and reconciliation where appropriate.

**Ignoring cleanup.** Object fields look fine while connections or listeners leak. Verify ownership and lifecycle.

**Reading state before async cleanup completes.** Wait for completion signals per contract.

**Not testing a valid operation after a failure.** May miss a stuck `busy` flag or held lock that leaves the object unusable.

**Creating non-deterministic tests with `Thread.sleep`.** Use latches, barriers, or fake clocks whenever possible.

**Assuming fail-fast input validation covers all exceptions.** After validation, I/O, allocations, observer callbacks, and persistence can still throw.

**Using reflection to test implementation details instead of the API contract.** Makes tests brittle and blocks refactoring; use only when truly necessary.

## 25. Checklist for Post-Exception State Tests

Before considering a test complete, ask:

- [ ] Is the method’s guarantee stated as strong/basic/no-throw or another specific contract?
- [ ] Was a valid initial state created and an **independent snapshot** saved?
- [ ] Was the expected failure triggered, and were type/code/cause checked?
- [ ] Was the entire contract-relevant state compared, not just a single field?
- [ ] Were invariants verified after the failure?
- [ ] Were external side effects checked when the operation touches DB/files/events/network?
- [ ] Was resource-owner cleanup checked, ensuring borrowed resources were not closed?
- [ ] Were failures tested after partial work and during cleanup?
- [ ] Was rollback distinguished from unknown outcome when responses can be lost?
- [ ] Was continued usability or transition to the proper lifecycle state tested?
- [ ] Were concurrency/synchronization checked if the object is shared?
- [ ] Was ordering controlled with fakes/latches rather than arbitrary sleeps?
- [ ] Is there a happy-path test to ensure the error-handling fix did not break successful operations?
- [ ] Were tests re-run after refactoring without locking into unnecessary implementation details?

## 26. Self-Check Exercises

**Q1:** `reserve(7)` throws the expected `IllegalStateException`, but `available=-2`. Can an `assertThrows` test pass? Does the object preserve the non-negative stock invariant?

**Answer:** `assertThrows` can pass, but the object has violated its invariant. The test must assert `available` and reservations after the exception.

**Q2:** You write `List<Item> before = object.items()`; `items()` returns the internal list. After the method fails, `before.equals(object.items())` returns true. Is that enough to prove a strong guarantee?

**Answer:** No. Both references may point to the same mutated list. You need an independent snapshot; if `Item` is mutable, use a deep copy or an appropriate semantic comparison.

**Q3:** A batch imports 10 records and fails on record 8; the first 7 records committed. Can the basic guarantee still hold?

**Answer:** Yes, **if the contract allows partial progress**, all invariants hold, and no resources leak. If the API promises an atomic batch / strong guarantee, the test must fail.

**Q4:** An object updates the DB successfully, but the response is lost. The client receives a timeout. Can you assert the DB is unchanged just because the client saw an exception?

**Answer:** No. The remote outcome may already be committed. You must inspect actual state or use an operation ID/idempotency for reconciliation rather than inferring rollback from a client-side exception.

**Q5:** A `try-with-resources` body throws `IllegalStateException` and `close` throws `IOException`. What should the test check?

**Answer:** The body error is primary, the close error should be in `getSuppressed()`, and cleanup state must be checked per the resource’s contract. Calling `close` alone does not prove complete release.

**Q6:** A test calls `future.cancel(true)` and immediately asserts the listener is unregistered, but the test intermittently fails. Is the implementation definitely wrong?

**Answer:** Not necessarily. The `Future`’s cancellation state can change before worker cleanup finishes. You must wait for an acknowledgment or synchronization per contract if the test checks the cleanup-completed checkpoint.

**Q7:** `Inventory` uses an immutable record and a single `state = candidate` assignment, giving a strong guarantee in a single thread. Does that guarantee safety when two threads call `reserve` concurrently?

**Answer:** No. Two threads can read the same old state and assign different results, losing an update. You need synchronization/CAS or an appropriate concurrency mechanism.

**Q8:** After an exception, the state looks valid, but the next valid command always throws `IllegalStateException("busy")`. Which test can catch this?

**Answer:** A test that runs a **successful operation after a failure**, verifying the object remains usable per contract, will catch a stuck `busy` flag or lifecycle state.

## 27. Conclusion

**The right exception type only confirms the error-reporting path; the state after the exception reveals whether the object still honors its contract.** To test thoroughly, declare a strong/basic/no-throw guarantee or equivalent conditions, take an independent snapshot before the call, inject failures at multiple checkpoints, and verify state, invariants, side effects, cleanup, and continued usability.

Fault-resilient design typically relies on **validating before mutation**, **preparing a candidate before commit**, **committing at a clear boundary**, and **transactions/compensation/idempotency** when side effects extend beyond memory. Tests should anchor on observable guarantees rather than assuming rollback from an exception alone. Doing so ensures the system both reports errors accurately and maintains reliable state after unsuccessful execution paths.