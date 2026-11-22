# Designing Exception-Safe APIs That Preserve Valid State

A Java API is not considered correct merely because it throws an appropriately named exception. After a method fails, the object it was modifying may still exist, be called again, and be observed by other components. If an exception occurs after a partial update, the API risks leaving behind a **half-baked state**, breaking invariants, leaking resources, or reporting a result to the caller that does not reflect what actually happened.

**The goal of exception-safe API design** is to define and enforce a clear contract: when a method returns or throws an exception, what valid states can the object remain in; which changes have been committed; which resources have been released; and can the caller retry, continue reading, or is it forced to create a new object?

For example, an inventory management API must avoid a state like `availableStock = -3` if the business invariant requires it to be non-negative. A money transfer API must avoid a state where the source account has been debited while the destination account has not been credited **when the contract promises atomicity**. A service might fail when sending a notification after writing data: in that case, the write may have already succeeded, so it must not arbitrarily claim that the entire business operation was rolled back.

This practice uses Java 17+ to design and verify the *validate → prepare → commit* boundary, exception-safety guarantees, resource management, multi-step updates, publication, and concurrency. Standalone examples include compile/run commands and deterministic stdout; snippets requiring frameworks/databases outside the JDK are marked as illustrative.

## 1. Valid state is a contract, not just a few fields

Before writing a method, explicitly write down the **invariants**: conditions that must hold true at the points where callers are allowed to observe the object.

For example, with a simple inventory:

- `available >= 0`.
- Each reservation has a non-empty identifier and a positive quantity.
- A duplicate reservation ID cannot be created if the contract requires uniqueness.
- All committed reservations are consistent with the remaining stock quantity.
- When a method call fails under the strong guarantee, the state snapshot afterward must equal the snapshot before.
- When the operation finishes, resources owned by the method are not left behind.
- If the object is in the `CLOSED` state, operations requiring `OPEN` must be clearly rejected.

Invariants are **design assumptions of a specific API**. A system that allows backorders might permit controlled negative stock; in that case, the requirement `available >= 0` no longer applies. Do not copy invariants from an example and impose them onto a different domain.

Ask these questions for every public method:

| Question | Example contract decision |
| --- | --- |
| What are the preconditions? | `quantity > 0`, `orderId` is not blank, object is not closed. |
| Which state is modified? | Stock, reservation list, version, and pending events. |
| When does commit happen? | After validating and building the complete candidate. |
| What if validation fails? | Throw `IllegalArgumentException`, state remains unchanged. |
| What if stock is insufficient? | Throw domain exception, state remains unchanged. |
| What if building the candidate fails? | Do not publish the candidate; old state is preserved. |
| What if an external dependency fails? | Track by transaction/operation ID; may have to report UNKNOWN. |
| Who owns the resources? | The scope that creates the resource closes that exact resource. |
| What does the caller do after an error? | Can continue using the object, retry conditionally, or transition to FAILED. |

If these questions do not have answers yet, adding `catch` blocks to “handle exceptions” usually only hides the problem.

## 2. Three levels of exception safety to distinguish

The following concepts are very useful when describing API contracts, even though Java does not provide standard annotations to enforce them automatically.

| Level | What must hold after an exception | Example |
| --- | --- | --- |
| **Strong guarantee** | Failure does not change observable state within the committed scope. | `reserve` rejects a request exceeding stock without adding a reservation and without deducting stock. |
| **Basic guarantee** | Invariants still hold and resources do not leak, but state may have permitted partial progress. | `importBatch` keeps 7 successful records, fails on the 8th record, and reports a checkpoint to resume. |
| **No-throw guarantee** | An operation is designed not to throw within the contract scope; usually applies to simple, reliable cleanup steps. | Updating an in-memory `closed` flag without performing I/O and without throwing. |

### Strong does not mean everything in the world is rolled back

If the API only commits the **in-memory state of an object**, a file written or an HTTP request sent before the error is not automatically revoked. The boundary of the strong guarantee must be documented clearly: object state, a DB transaction, or an entire workflow with compensation mechanisms.

### Basic does not mean the object is allowed to be corrupted

A batch import may keep records that were written successfully, but indices/counters/lists must remain consistent. The caller needs to know what completed and what did not. Half-initialized state, negative quantities violating invariants, or resource leaks are not a “basic guarantee”.

### No-throw must be based on the real implementation

`AutoCloseable.close()` can throw an exception. Writing a file, flushing a buffer, or closing a network connection is not automatically no-throw. Only advertise the no-throw level when justified and after accounting for cases where resource errors must be handled.

## 3. Anti-pattern: mutating state before verification

A basic mistake:

```java
void reserve(int quantity) {
    available -= quantity;
    if (available < 0) {
        throw new IllegalStateException("insufficient stock");
    }
}
```

This is an illustrative snippet, assuming `available` is a field. If there are 5 items and the caller orders 7, the method throws the right exception but leaves `available=-2`.

A subtler mistake:

```java
void reserve(String id, int quantity) {
    reservations.add(id);
    validateQuantity(quantity);
    available -= quantity;
}
```

This is a non-standalone snippet. If `validateQuantity` throws, the reservation list has already been modified. If `available -= quantity` executes after multiple auxiliary calls that can fail, the state becomes even harder to reconcile.

**Practical rule:** check all preconditions and business state that can be verified before mutating; prepare new data outside the main state; commit only after preparation succeeds. However, you must also consider exceptions coming from **post-commit steps**: logging, callbacks, persistence, or event publication can break the assumption “if it throws, nothing changed.”

## 4. The validate → prepare → commit design pattern

Model:

```text
State S0
    |
    +--> VALIDATE (read, check preconditions/invariants)
    |       \-- error: throw, S0 unchanged
    |
    +--> PREPARE (create new structures/value objects)
    |       \-- error: discard candidate, S0 unchanged
    |
    +--> COMMIT (publish new state at a controlled point)
    |       \-- committed: caller must know post-commit semantics
    |
    +--> AFTER-COMMIT (outbox/notification per contract)
            \-- error: do not arbitrarily claim transaction rollback
```

When holding all mutable state in an immutable value object, committing can be **a single reference swap**. For concurrently updated state, the commit operation also requires appropriate locking/CAS/transactions. A reference assignment by itself does not handle races when multiple threads read S0 concurrently.

An illustrative sketch:

```java
State original = state;
validate(input, original);
State candidate = calculateNewState(original, input);
state = candidate; // Commit after prepare succeeds.
```

This is an illustrative snippet; `State`, `input`, `validate`, and `calculateNewState` are defined elsewhere. If `calculateNewState` only builds local data and has no external side effects, a failure before the assignment preserves the original state. If the prepare function itself makes an HTTP call to execute a payment, it is **no longer side-effect-free**, and the strong guarantee of the entire workflow is no longer ensured merely by the final assignment statement.

## 5. Complete Java 17 example: designing an exception-safe Inventory

The following program uses an immutable `record` as state, an unmodifiable reservation list, and `synchronized` to serialize calls to the same Inventory. It simulates three cases: insufficient stock, an error injected **before commit**, and a successful operation. Any exception occurring **before commit** preserves the old snapshot.

Create `ExceptionSafeInventoryDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class ExceptionSafeInventoryDemo {

    private record State(int available, List<String> reservations) {
        State {
            if (available < 0) {
                throw new IllegalArgumentException("negative stock");
            }
            reservations = List.copyOf(reservations);
        }
    }

    private static final class Inventory {
        private State state = new State(5, List.of());

        synchronized State snapshot() {
            return state;
        }

        synchronized void reserve(
                String orderId, int quantity, boolean failBeforeCommit) {
            Objects.requireNonNull(orderId, "orderId");

            if (orderId.isBlank() || quantity <= 0) {
                throw new IllegalArgumentException("invalid reservation");
            }

            State old = state;
            if (quantity > old.available()) {
                throw new IllegalStateException("insufficient stock");
            }

            List<String> candidateReservations =
                    new ArrayList<>(old.reservations());
            candidateReservations.add(orderId + ":" + quantity);

            State candidate = new State(
                    old.available() - quantity, candidateReservations);

            if (failBeforeCommit) {
                throw new IllegalStateException("injected before commit");
            }

            state = candidate;
        }
    }

    public static void main(String[] args) {
        Inventory inventory = new Inventory();
        State initial = inventory.snapshot();

        try {
            inventory.reserve("order-A", 7, false);
        } catch (IllegalStateException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }
        System.out.println("unchanged after rejection: "
                + initial.equals(inventory.snapshot()));

        try {
            inventory.reserve("order-B", 2, true);
        } catch (IllegalStateException ex) {
            System.out.println("injected: " + ex.getMessage());
        }
        System.out.println("unchanged after injection: "
                + initial.equals(inventory.snapshot()));

        inventory.reserve("order-C", 2, false);
        System.out.println("after success: " + inventory.snapshot());
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 ExceptionSafeInventoryDemo.java
java ExceptionSafeInventoryDemo
```

Deterministic stdout:

```text
rejected: insufficient stock
unchanged after rejection: true
injected: injected before commit
unchanged after injection: true
after success: State[available=3, reservations=[order-C:2]]
```

**Why does the example keep state valid?**

1. Checking `orderId`, quantity, and stock happens **before** assigning `state`.
2. `candidateReservations` is a new list, not the internal list currently in use.
3. The `State` constructor enforces the non-negative stock invariant and copies the list; an error during candidate construction does not alter the current state.
4. The `failBeforeCommit` branch intentionally throws after prepare and before assignment. Therefore, the snapshot does not change.
5. Assigning `state = candidate` is the in-memory commit point. Afterward, the method ends immediately without invoking a callback that could throw and make the exception semantics ambiguous.
6. `synchronized` on `reserve` and `snapshot` prevents two calls on the **same object** from reading and overwriting each other's state in the example code.

**Limitations:** the example does not check for duplicate order IDs, and has no DB, events, or retries. If the domain requires unique IDs, that invariant must be checked or encoded before commit. `List.copyOf` only performs a shallow copy, though the elements here are immutable `String`s. For nested mutable objects, an appropriate deep snapshot or value type is needed.

`synchronized` protects the synchronized methods on the same Inventory monitor; it does not create a transaction across multiple JVMs and does not protect any shared variables outside the lock.

## 6. When is a single reference swap enough?

With completely immutable in-memory state and all pre-commit computations being side-effect-free, swapping a reference at a clear point can help implement the strong guarantee **for pre-commit failures**.

However, three types of atomicity must be distinguished:

- **Atomic reference publication:** concurrent callers see the state either before or after the reference swap, never a half-updated record.
- **Atomic read-modify-write:** two concurrent calls do not overwrite each other's updates; requires locks, a CAS loop, or an equivalent mechanism.
- **Atomic persistence/side effects:** databases, caches, queues, and external services remain consistent under a single transaction/contract. This cannot be achieved by assigning a Java field.

If the API allows reads from other threads without synchronization, merely assigning a normal reference is not enough to guarantee **visibility** under the Java Memory Model. You can use `synchronized`, `volatile`, or `AtomicReference` as appropriate, but you must choose them so that the entire read-modify-write logic is correct.

When multiple objects participate in one operation, a shared lock, transaction, or coordinator is sometimes required. Do not confuse a clean immutable state with a guarantee that the entire workflow cannot expose intermediate state.

## 7. Designing pre-commit and post-commit separately

An anti-pattern:

```java
void createOrder(Order order) {
    database.insert(order);
    emailService.sendConfirmation(order); // May throw IOException.
}
```

This is an illustrative snippet with hypothetical dependencies. When sending the email throws, the database may have already saved the order. If the caller catches the exception and calls `createOrder` again, the order/email may be duplicated.

The solution must be based on the **business contract**:

- If you want **the order and the email-sending task** to be recorded atomically, you can insert an **outbox event** in the same DB transaction as the order.
- Another worker processes the outbox and retries event dispatch with idempotency/deduplication; actually sending the email is a separate lifecycle.
- If the API returns right after the DB commit, it should clearly state that the notification may be **pending**, rather than falsely turning an email-sending failure into “the order was not created.”
- If a dependency can commit and then lose the response, an operation ID and reconciliation are needed; do not infer “unchanged” from the caller's `IOException`.

With a real DB transaction, state is committed when the database confirms according to the contract. A JVM crash between steps is not solved by `finally` or an in-memory by-value record.

### When should side effects be executed?

There is no universal rule that all side effects must be placed after commit. For example, authorization is needed before commit; some read-only dependency calls must complete before making a decision. What matters is knowing **which steps have side effects, which steps can fail, and which commit point is the contract boundary**.

For post-commit event publication, tests must verify “order committed while event is still pending” per design; do not force an unconditional rollback just because a downstream callback throws.

## 8. Complete Java 17 example: recording business state and outbox in the same snapshot

The following in-memory example demonstrates the *outbox* principle: a single commit places both the order and the event into the same immutable state. An error injected before commit keeps both unchanged; after commit, the event is in a pending-send state, not yet delivered to a broker.

Create `OrderOutboxStateDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class OrderOutboxStateDemo {

    private record State(List<String> orders, List<String> pendingEvents) {
        State {
            orders = List.copyOf(orders);
            pendingEvents = List.copyOf(pendingEvents);
        }
    }

    private static final class OrderService {
        private State state = new State(List.of(), List.of());

        synchronized State snapshot() {
            return state;
        }

        synchronized void create(String orderId, boolean failBeforeCommit) {
            if (orderId == null || orderId.isBlank()) {
                throw new IllegalArgumentException("invalid orderId");
            }

            State old = state;
            if (old.orders().contains(orderId)) {
                throw new IllegalStateException("duplicate order");
            }

            List<String> nextOrders = new ArrayList<>(old.orders());
            nextOrders.add(orderId);

            List<String> nextEvents =
                    new ArrayList<>(old.pendingEvents());
            nextEvents.add("OrderCreated:" + orderId);

            State candidate = new State(nextOrders, nextEvents);

            if (failBeforeCommit) {
                throw new IllegalStateException("injected before commit");
            }

            state = candidate;
        }
    }

    public static void main(String[] args) {
        OrderService service = new OrderService();
        State before = service.snapshot();

        try {
            service.create("A", true);
        } catch (IllegalStateException ex) {
            System.out.println("failed: " + ex.getMessage());
        }

        System.out.println("unchanged: " + before.equals(service.snapshot()));

        service.create("A", false);
        System.out.println("orders: " + service.snapshot().orders());
        System.out.println("outbox: " + service.snapshot().pendingEvents());

        try {
            service.create("A", false);
        } catch (IllegalStateException ex) {
            System.out.println("duplicate: " + ex.getMessage());
        }
        System.out.println("still one order: "
                + service.snapshot().orders().size());
    }
}
```

Run:

```bash
javac --release 17 -encoding UTF-8 OrderOutboxStateDemo.java
java OrderOutboxStateDemo
```

Stdout:

```text
failed: injected before commit
unchanged: true
orders: [A]
outbox: [OrderCreated:A]
duplicate: duplicate order
still one order: 1
```

In the program:

- The initial state has no orders/events.
- A failure before commit does not publish `candidate`, so both orders and events remain unchanged.
- A successful creation puts `A` and the `OrderCreated:A` event into the **same snapshot**.
- A duplicate creation is rejected before commit, without duplicating the order.
- The event remains in `pendingEvents`, **without pretending it has already been sent**.

**Very important limitation:** this example illustrates the commit boundary **within a single JVM and a single object**; there is no DB transaction, crash safety, multiple nodes, event-dispatch worker, persistence, or acknowledgment. A production transactional outbox needs to write the order and outbox row **within the same durable transaction**, have a worker dispatch events with at-least-once semantics when appropriate, and have the consumer/delivery handle duplicates.

Do not use this in-memory `List<String>` as a “data-guaranteed outbox” for real-money business operations.

## 9. Limits of the validate-before-mutate principle

For invalid input, **validate first** usually keeps state unchanged:

```java
void setQuantity(int quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException("quantity <= 0");
    }
    this.quantity = quantity;
}
```

This is a snippet in a hypothetical class; `quantity` is a field. For updating just a single primitive with no subsequent side effects, this is a simple structure.

However, if the method also has:

```java
this.quantity = quantity;
notifyListeners(); // May throw an exception.
```

then an exception in `notifyListeners` occurs **after mutation**. If the API still promises a strong guarantee, the boundary must be redesigned:

- Can callbacks be prepared/checked beforehand without side effects?
- Can the update and notification be split into two separate operations/contracts?
- Can a durable event/outbox be recorded instead of invoking callbacks directly under the transaction?
- Can both the mutation and any callback effects that already occurred be rolled back? If not, do not promise a full rollback.
- Can the caller distinguish “update succeeded, notification not yet delivered” via a result/status?

**Placing validation before mutation is necessary but not sufficient** for a method with multiple steps that can throw.

## 10. Method contract on error: throw, return, or domain status?

An API can choose how to report errors:

**Throw an exception** when preconditions are wrong, invariants are violated, or an unexpected error occurs according to the contract.

```java
void reserve(String orderId, int quantity);
```

If using `IllegalStateException` when stock is insufficient, document: after throwing, do stock and reservations remain unchanged? Can the caller retry after restocking?

**Return a result type** when “unable to execute” is a common outcome and the caller needs to distinguish multiple controlled cases.

```java
sealed interface ReserveResult
        permits Reserved, Rejected, Pending {}

record Reserved(String reservationId) implements ReserveResult {}
record Rejected(String reasonCode) implements ReserveResult {}
record Pending(String operationId) implements ReserveResult {}
```

This is an illustrative snippet using Java 17 syntactically valid sealed interfaces/records; the declarations must be placed in an appropriate file or class. `Pending` represents an incomplete/uncertain outcome, not a swallowed exception disguised as success.

**Do not turn every exception into `true`/`false` or `null`** if the caller needs the cause, transaction status, and recovery path. A result type is only good when its semantics, invariants, and returned states are clearly defined.

### Checked vs. unchecked does not tell you whether state rolled back

`IOException`, `SQLException`, and `RuntimeException` belong to different compile-time categories, but **none of them automatically guarantees the object is unchanged**. The contract documentation must specify what happens for each kind of failure.

## 11. Choosing the right transaction or unit-of-work boundary

If a method modifies two accounts:

```java
from.debit(amount);
to.credit(amount);
```

this is a dangerous illustrative snippet if `to.credit` can throw after `from.debit` has already succeeded. If the contract promises an atomic transfer, you must:

- Verify balances/conditions before committing.
- Build candidates for **both accounts**.
- Commit under a lock/transaction covering those exact objects.
- Or delegate the entire operation to a real database transaction with proper isolation/constraints.
- When network side effects are involved, use an operation ID and an appropriate coordination protocol.

If the domain allows partial progress, report the status explicitly instead of pretending the transfer is atomic. For real money flows, do not rely solely on `synchronized` across two Java objects: multiple processes/nodes/database transactions and lost-response failures must all be considered.

### Do not just roll back the first field in a catch block

Anti-pattern:

```java
try {
    from.debit(amount);
    to.credit(amount);
} catch (Exception ex) {
    from.credit(amount);
    throw ex;
}
```

This is an illustrative anti-pattern snippet. The rollback command itself can throw or create new side effects; `to.credit` might have succeeded before throwing; and the code might be running concurrently with other threads. This approach does not automatically become a safe transaction.

For small in-memory state, staged immutable state is a good choice. For a DB, the transaction is the boundary. For multiple systems, a workflow/Saga/compensation and explicit intermediate states may be required.

## 12. Cleanup is part of the post-failure state contract

An API can **preserve business data** after an error yet still leak a connection, semaphore permit, or listener. Thus, promising “valid state after exception” is not enough if the contract also governs resource lifecycles.

When a method acquires resource A and then B, specify: if A was acquired successfully, it must be released if step B fails. For resources owned by the scope itself, use:

~~~java
try (Resource first = acquireFirst();
     Resource second = acquireSecond(first)) {
    performWork(first, second);
}
~~~

This is an illustrative snippet, with `Resource extends AutoCloseable` and custom factories. If `acquireSecond` fails, Java attempts to close `first`. If both succeed, they are closed in **reverse order**. In tests, do not just assert the exception type: also measure `closeCalls` and the object's state after failure.

**Ownership must be exact:** do not close a stream that the API only borrows from the caller; do not shut down a shared executor just because one job failed. For `Semaphore.acquire()`, `Lock.lockInterruptibly()`, or a registration token that can fail before acquisition, only release/unlock/unsubscribe when ownership was actually acquired. Cleanup failures also do not automatically undo already-committed data.

The next section uses fake resources to clearly verify that **when acquiring B fails, A is still closed**, rather than depending on real files or connections.

## 13. Complete Java 17 example: cleanup when acquisition fails

The example uses a simulated `AutoCloseable` resource that records the order of steps in a list. The second scenario fails to open resource B, so A must be closed before the exception reaches the caller.

Create `PartialAcquisitionDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class PartialAcquisitionDemo {

    private static final class Lease implements AutoCloseable {
        private final String name;
        private final List<String> events;

        Lease(String name, List<String> events) {
            this.name = name;
            this.events = events;
            events.add("open " + name);
        }

        @Override
        public void close() {
            events.add("close " + name);
        }
    }

    private static Lease acquireSecond(
            List<String> events, boolean fail) {
        if (fail) {
            throw new IllegalStateException("second unavailable");
        }
        return new Lease("B", events);
    }

    private static void execute(List<String> events, boolean failSecond) {
        try (Lease first = new Lease("A", events);
             Lease second = acquireSecond(events, failSecond)) {
            events.add("work");
        }
    }

    public static void main(String[] args) {
        List<String> failed = new ArrayList<>();
        try {
            execute(failed, true);
        } catch (IllegalStateException ex) {
            failed.add("caught " + ex.getMessage());
        }
        failed.forEach(System.out::println);

        System.out.println("---");

        List<String> success = new ArrayList<>();
        execute(success, false);
        success.forEach(System.out::println);
    }
}
```

Compile/run:

```bash
javac --release 17 -encoding UTF-8 PartialAcquisitionDemo.java
java PartialAcquisitionDemo
```

Stdout:

```text
open A
close A
caught second unavailable
---
open A
open B
work
close B
close A
```

Observations:

- The `acquireSecond` error occurs **before** B is created; there is no `close B`.
- Because A was created successfully, try-with-resources closes A when exiting due to the exception.
- On the success path, B closes before A due to reverse declaration order.
- `Lease.close()` in the demo does not throw and only records events. Real resources may require different cleanup or have close failures, which must have separate tests.

Avoid making cleanup depend on “after catching, I'll remember to close it”: placing the resource scope close to where it is acquired is much more resilient.

## 14. Double failure in cleanup: asserting invariants after failure

If the body throws exception A and `close()` throws B, `try-with-resources` keeps A as the **primary** exception and puts B in `A.getSuppressed()` when suppression is enabled. This is an error-information preservation mechanism, **not a data rollback mechanism**.

For an exception-safe API, test assertions should combine **two groups**:

| Error information | Post-failure state |
| --- | --- |
| Cause / primary still accurately describes the operation failure | Business data snapshot still satisfies invariants; unchanged if strong guarantee is promised |
| `getSuppressed()` preserves close error details | Owned resources were properly *attempted* to be closed, even if close failed |
| Close-only error is reported when the try body succeeds | Caller does not mistake a pre-close result for complete success |
| If cleanup/undo fails further | Lifecycle may be `FAILED`/unusable; do not report that rollback succeeded |

The `PartialAcquisitionDemo` program in section 13 only records successful closes; when extending the fake so that close throws an exception, assert primary/suppressed **and** the resource state machine. Three-resource scenarios and in-depth suppressed-order testing belong to a dedicated lesson on multiple suppressed exceptions; here the focus is on **the API's postcondition contract**.

## 15. Distinguishing pre-commit, in-commit, and post-commit errors

A failure can happen in three different phases:

| Timing | Example | Reasonable conclusion |
| --- | --- | --- |
| **Pre-commit** | Validation fails; candidate state cannot be built | If prepare is side-effect-free, published state can remain unchanged. |
| **In-commit** | DB commit returns a connection error; driver does not know the result | Outcome may be unknown; check contract and reconcile. |
| **Post-commit** | Sending email/event or logging callback fails | Business state may have committed; do not claim rollback without a mechanism. |

On an in-memory JVM, a field assignment does not throw checked exceptions and is executed by the JVM according to its semantics; however, having **only a single assignment** does not solve external side effects, visibility, or races. The API must separate phases along the right observation boundaries.

A good design generally does not try to catch any exception and unconditionally call `rollback()`. It records committed state, state needing retry/compensation, and the operation ID to return an honest result to the caller.

## 16. Do not let callbacks break state atomicity

Suppose a method calls an observer while the state is incomplete:

```java
state = new State(...);
listener.onChanged(state); // uncontrolled callback
commitOtherPart();
```

This is an illustrative snippet. The listener can throw or reenter the API; meanwhile, other components have already seen part of the new state. In particular, untrusted callbacks should not be invoked while holding a lock if there is a risk of deadlock or exposing intermediate state.

Improvement approach:

1. Validate and build a new snapshot.
2. Commit all state belonging to an invariant in a controlled manner.
3. Record events or invoke callbacks in a **post-commit phase** with separate semantics.
4. If the callback fails, have a retry/durable-event policy or a notification-failed status; do not turn it into “state unchanged.”
5. Ensure listeners cannot directly mutate internal collections.

If notification is needed **in the same transaction** as the business update, use an outbox/transaction mechanism; an in-memory callback cannot replace a distributed transaction.

## 17. APIs with lifecycles: OPEN, FAILED, CLOSED

Not every error allows an object to keep operating as before. If a connection/session is broken to the point where it cannot safely recover, the object may have to transition to `FAILED` to reject subsequent operations.

```text
NEW → OPEN → CLOSED
        |
        +→ FAILED → CLOSED
```

When a method fails, the contract should specify:

- Ordinary validation errors: the object remains `OPEN` and can continue to be used.
- Severe protocol errors causing desynchronization: the object becomes `FAILED` and subsequent commands are rejected.
- Errors during `close()`: the object may be in `CLOSING`/`CLOSED_WITH_ERRORS` or another defined state; do not report a clean `CLOSED` if resources have not been released.
- Repeated `close()` calls: is it idempotent, does it throw?
- Should the caller use `reset()`, create a new object, or close and discard it?

Do not write an API where the `ACTIVE` state appears before the resources required for ACTIVE have finished being created. Also do not catch every error and silently set `OPEN` when invariants may have been broken.

If the object is shared, lifecycle transitions must be synchronized with threads currently processing, not just updating an enum without memory visibility.

## 18. When a method permits partial progress

The strong guarantee is not always cheap or feasible. A batch API can publicly declare the **basic guarantee**:

```java
BatchResult importRecords(List<Record> records);
```

This is an illustrative signature; `BatchResult` and `Record` must be defined. The contract may allow processing N records successfully and then stopping when the next record fails. In that case:

- The N committed records must be consistent and free of duplicates.
- The resume/checkpoint position must be accurate.
- The failing record must not leave behind a half-formed invalid structure.
- Owned resources must be cleaned up.
- The caller receives the success count, error list, or status enabling recovery.
- Retry/resume must not repeat side effects of already-written records.

If the contract is “atomic batch”, keeping 7/10 records after an exception **violates** the contract. Choose the guarantee according to domain needs, document it, and test it specifically.

A result type reporting `PARTIAL_SUCCESS` can be clearer than throwing a generic exception and forcing the caller to guess how many items were written.

## 19. Using try/catch for bounded rollback

Some code genuinely needs compensating actions on failure:

```java
boolean registered = false;
try {
    registerListener(listener);
    registered = true;
    activate();
} catch (RuntimeException failure) {
    if (registered) {
        try {
            unregisterListener(listener);
        } catch (RuntimeException cleanupFailure) {
            failure.addSuppressed(cleanupFailure);
        }
    }
    throw failure;
}
```

This is an illustrative snippet; `registerListener`, `activate`, `unregisterListener`, and `listener` are not defined. It shows **cleaning up only what was successfully acquired**, and not letting a cleanup error mask the primary error.

However, there are two issues the API must handle itself:

- `registerListener` might have registered successfully and then **thrown after the side effect occurred**, so `registered=false` does not necessarily mean no cleanup is needed. Ideally, registration returns a handle with a clear contract, or the operation is idempotent/reconcilable.
- `activate` may have effects beyond registering the listener. Cleaning up the listener does not roll back other side effects, so do not hastily promise a strong guarantee for the whole workflow.

Better yet, design acquisition/registration steps so that they either return a clear handle or have a deterministic safety mechanism if an error occurs mid-way.

## 20. Designing error contracts that are easy for callers to understand

Javadoc or API descriptions should state:

**Preconditions:** what inputs and lifecycle state are required?

**Failure types:** how are validation errors, resource exhaustion, dependency failures, cancellation, and illegal state represented?

**State guarantee:** what remains unchanged on failure? Is there partial commit?

**Resource ownership:** what does the API close itself, and what must the caller close?

**Retry semantics:** which errors are retryable, is the operation idempotent, is there an operation ID?

**Concurrency:** is the method thread-safe, and to what extent are snapshots consistent?

**Unknown outcome:** if the response is lost during commit, how does the caller look up the result?

Illustrative Javadoc example:

```java
/**
 * Reserves a quantity of stock for an order.
 *
 * @throws IllegalArgumentException if id is blank or quantity is non-positive
 * @throws IllegalStateException if stock is insufficient
 *
 * Exception safety: if validation or the stock check fails,
 * the inventory state remains unchanged. The method is thread-safe within
 * the scope of a single Inventory instance.
 */
void reserve(String orderId, int quantity);
```

This is an illustrative signature/doc without a defined body. `@throws` describes the conditions under which errors occur; the “Exception safety” section describes the consequences for the object. The two parts complement each other.

Do not use a broad `throws Exception` just because an API has many steps. Clear error types are helpful, but even multiple specific exception types do not replace a description of the state guarantee.

## 21. Testing: is the state still valid after an exception?

A test suite that only has:

```java
assertThrows(IllegalStateException.class, () -> inventory.reserve("x", 99));
```

is not enough. This is a JUnit 5 snippet requiring an external dependency outside the JDK. It proves that an exception of the `IllegalStateException` family was thrown; it does not prove that the state is still valid.

A good test should:

1. Prepare the object in a valid state.
2. Take an independent snapshot before the call.
3. Trigger a deterministic failure.
4. Assert the exception type/code/cause when required by the contract.
5. Assert that the snapshot afterward equals the one before for a strong guarantee, or satisfies the documented basic guarantee.
6. Assert the object's invariants.
7. Assert there are no out-of-scope side effects, or that unknown status matches the contract.
8. Assert that resources were cleaned up.
9. Try a **successful operation after the error** if the object is promised to remain usable.
10. For concurrency, verify state and commit ordering under controlled interleaving.

### Snapshots must not point to mutable collections

Wrong:

```java
List<Item> before = inventory.items();
```

If `items()` returns an internal mutable list, `before` and `inventory.items()` may be the same object; a mutation after failure changes the snapshot as well, causing a false-pass test.

Better:

```java
List<ItemView> before = snapshotItems(inventory);
```

This is an illustrative snippet, with `ItemView` immutable and `snapshotItems` creating an appropriate deep/semantic copy. `List.copyOf` only creates a shallow copy; if elements are still mutable, a safer snapshot is needed.

## 22. Testing failures at multiple checkpoints

Do not test only validation failures. An API consisting of acquire, transform, commit, and publish can fail at any step:

| Failure point | What to check |
| --- | --- |
| Null/blank/out-of-range input | Does not mutate state, does not trigger side effects. |
| Business invariant violated | State remains preserved per contract. |
| Acquire resource A succeeds, B fails | A is cleaned up, B is not closed if it never existed. |
| Candidate collection creation fails | Published state remains unchanged. |
| Before commit | Candidate is not published. |
| Inside DB transaction | Rollback/UNKNOWN per DB contract, no guessing. |
| Post-commit when sending event fails | State is committed, event is pending or failure is meaningfully recorded. |
| Close also fails | Primary/cause/suppressed and resource state are preserved. |
| Caller interrupted while waiting | Not confused with worker failure; cleanup belongs to the right owner. |
| Duplicate operation ID | Does not create duplicate side effects when the domain requires idempotency. |

You can use a fake adapter with a “fail at step N” switch or JUnit mocks with deterministic behavior. However, unit tests do not prove real database transactions; integration tests with an appropriate real or emulated system are needed.

## 23. Testing for failures that silently corrupt an object

An object may keep its visible fields unchanged yet get stuck because:

- A `busy=true` flag was not reset.
- A semaphore permit/lock was not released.
- A listener remains registered and receives unwanted callbacks.
- A stream is closed while a field still reports `OPEN`.
- Cache version and DB version are out of sync.
- An async task still writes state after the API reported canceled.
- A thread was interrupted, yet a loop continues applying effects.

Beyond snapshots, perform a **valid operation right after the failure**. If the contract says the object remains operational, the next method call must not get stuck due to leftover resources/lifecycle state. If the contract says it must transition to `FAILED`, the next call should clearly report `IllegalStateException`/domain error rather than using potentially unsafe state.

For async cleanup, wait for acknowledgment/latch per contract before asserting “closed”; `Future.isCancelled()` does not necessarily mean the worker's `finally` block has finished.

## 24. Concurrency: exception safety is not thread safety

This code:

```java
State old = state;
State next = compute(old);
state = next;
```

may satisfy the strong guarantee for a single thread, but **two threads reading `old` concurrently and committing separately can lose updates**. Therefore, a shared API must consider:

- Atomic read-modify-write via lock/CAS/transaction.
- Visibility: `volatile` or synchronization for publication.
- Multi-field invariants must be observed consistently.
- Callbacks must not run on half-committed state.
- If CAS fails, recomputing a new candidate must not unintentionally repeat side effects.
- Cancellation occurring between prepare and commit must have a clear policy.

If using a CAS loop, `compute(old)` must have no non-idempotent side effects, because CAS can fail and force recomputation. Do not charge payments, send emails, or increment external counters before each CAS retry.

**A single reference assignment does not make an entire workflow thread-safe.** It is only one technical building block in concurrency design.

## 25. Exception safety and cancellation/interruption

An operation may receive `InterruptedException` at a blocking step. Handling depends on the boundary:

- If the API can propagate `InterruptedException` to the caller, propagate the signal so the lifecycle owner decides.
- If converting to an unchecked exception and stopping, usually restore the interrupt flag with `Thread.currentThread().interrupt()`.
- Place cleanup of owned resources in `finally`/`try-with-resources`.
- Do not release a lock/permit when it was not acquired.
- If cancellation occurs after a side effect, state is not guaranteed to roll back.
- If cleanup requires blocking operations, consider when to restore the flag so cleanup is not immediately interrupted itself; set a reasonable deadline.

Example:

```java
try (OwnedHandle handle = acquireOwnedHandle()) {
    performInterruptibleWork(handle);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new OperationInterruptedException("interrupted", ex);
}
```

This is an illustrative snippet with application-provided types/methods. Placing the catch **outside** try-with-resources means the handle is closed before the catch restores the flag, which can be useful when cleanup is sensitive to interruption. If `close` has other checked exceptions, the actual signature/catch must handle those types properly.

Do not treat interruption as a transient error to retry infinitely; it is usually a stop request.

## 26. Common API design mistakes

**1. Throwing the right exception but mutating state before checking.** Type tests pass while invariants are broken. Validate first and prepare candidates before committing.

**2. Returning internal mutable collections to callers.** Callers can modify state directly, bypassing invariants/validation. Return immutable views or snapshots per contract.

**3. Copying only references for snapshots.** Nested mutable data changes alongside the original, creating false-pass tests. Use immutable value objects or deep snapshots.

**4. Mistaking a field assignment for a DB transaction.** It does not roll back the filesystem, queues, external APIs, or another process's state.

**5. Catching all exceptions and rolling back manually unconditionally.** Rollback can also fail and side effects may have already committed; clear transactions/compensation/status are needed.

**6. Treating a post-commit callback error as proof of no commit.** Can cause duplicates when the caller retries. Distinguish business commit from notification.

**7. Closing a shared resource when one request fails.** Wrong ownership disrupts other requests. Close only handles owned by the scope.

**8. Releasing a permit or unlocking without having acquired it.** Interruption can arrive before acquisition succeeds; check the exact ownership point.

**9. Turning all exceptions into a single “failed” message.** Loses the cause and the rollback/unknown status callers need.

**10. Swallowing cleanup exceptions.** Can lose data during flush/close; preserve cause/suppressed and error status.

**11. Promising a strong guarantee while allowing unreported partial progress.** Contract and tests must align; if basic, expose checkpoints.

**12. Using `synchronized` on one method while reading state from another unsynchronized method.** Prone to visibility/race issues. Protect the entire read/write contract.

**13. Calling observers while the object is in an intermediate state.** Callbacks can throw or reenter; publish consistent state first and choose notification semantics.

**14. Checking only the exception class with `assertThrows`.** Fails to verify state, invariants, cleanup, and whether the object remains usable.

**15. Retrying the whole operation after a timeout when side effects may have occurred.** Needs idempotency/operation IDs and reconciliation mechanisms.

## 27. Practice exercises

**Exercise 1 – Inventory:** `reserve(7)` from stock 5 throws an error but still adds a reservation. Describe the violated invariant and change the processing order.

*Hint:* check quantity/stock and duplicate IDs first; prepare a new list; commit once. Test both state and exception.

**Exercise 2 – Account:** `transfer(30)` debits the source and then fails when crediting the destination. If the contract promises atomicity, why is `catch { source += 30; }` not enough?

*Hint:* rollback can also fail, the destination might have been credited before throwing, and concurrency can interleave. A stronger atomic boundary is needed.

**Exercise 3 – Listener:** `register` A succeeds, B fails; A remains subscribed. Where should cleanup happen?

*Hint:* use a scope-owned registration handle or a `finally` block that cancels only registrations already acquired. Test failed initialization and callbacks after cleanup.

**Exercise 4 – DB + email:** the DB committed, but sending email failed. Can you claim that order creation failed completely?

*Hint:* no if the DB already committed; use pending events/outbox or report the appropriate status.

**Exercise 5 – Concurrency:** two threads both read stock 5, both want to reserve 4, and each computes `next=1` and assigns it. The invariant `available >= 0` may still hold, so what bug occurred?

*Hint:* lost update/over-reserving beyond actual stock. Synchronization/CAS/transactions are needed, and invariants must include total reservations.

**Exercise 6 – Cleanup:** the `try` body throws `IllegalStateException`, and `close` throws `IOException`. What should the test check?

*Hint:* primary exception, suppressed close exception, that the resource was attempted to close, and cleanup state per contract.

**Exercise 7 – Interruption:** a thread is interrupted before `Semaphore.acquire()` obtains a permit. Why is an unconditional `finally { semaphore.release(); }` wrong?

*Hint:* the permit is not owned yet, so releasing corrupts the count; design the scope around the successful acquisition point.

## 28. Checklist before publishing an exception-safe API

- [ ] Every public method has clear preconditions, postconditions, and invariants.
- [ ] Strong/basic/no-throw is chosen, or operation-specific guarantees are documented.
- [ ] Validation errors do not mutate published state.
- [ ] Candidate data is prepared independently without accidentally mutating shared collections.
- [ ] Commit sits at an identifiable/controllable boundary.
- [ ] Operations that can fail post-commit have separate semantics and do not promise fake rollbacks.
- [ ] DB/outbox/event/network operations have appropriate transactions, idempotency, or reconciliation.
- [ ] Resource ownership is clear: release/close only what was successfully acquired.
- [ ] try-with-resources/finally covers error paths and cleanup failures are considered.
- [ ] Exception types, causes, and UNKNOWN/PENDING states are adequately documented.
- [ ] The API does not expose mutable state that lets callers break invariants externally.
- [ ] Concurrency/read-write visibility is protected according to the contract.
- [ ] Tests cover fault injection before commit, during cleanup, and post-commit.
- [ ] Tests take independent state snapshots and assert invariants after failure.
- [ ] Tests verify successful operations after an exception or proper transition to the `FAILED` lifecycle.
- [ ] Integration tests exist for out-of-JVM transactions/side effects when needed.
- [ ] No blind retries when a response is lost and the server result may have already committed.

## 29. Summary

Designing APIs that preserve valid state on error requires **explicitly stating which states are allowed after an exception**, not just deciding which exception to throw. For in-memory state, the **validate → prepare → commit** pattern together with immutable value objects and appropriate synchronization reduces partial mutations; for resources, ownership and structured cleanup are required; for DB/network/events, transactions, outbox, idempotency, or reconciliation are needed along real boundaries.

A trustworthy API can state precisely: **this error occurred before commit so state is unchanged; that error occurred after commit so business state succeeded while notification is pending; this fatal error transitioned the object to FAILED and it can no longer be used.** When those contracts are reflected in both design and tests, exceptions are no longer ambiguous signals—they become a controllable part of system correctness.
