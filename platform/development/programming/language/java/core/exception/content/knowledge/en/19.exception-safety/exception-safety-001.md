# Failure Atomicity and the Risk of Partial State Changes in Java

## 1. The problem: a method can throw an exception after modifying data

Suppose an operation to add an item to a cart must simultaneously update the product list and the total quantity. If the method adds to the list first and only then checks whether the quantity is valid, an exception will interrupt the execution flow midway. The caller receives a "failed to add" notification, yet the cart already contains an invalid line item. Subsequent operations may read an inconsistent state, even though the exception was caught and the program continues running.

**Failure atomicity** is an operation-level guarantee: **either the operation succeeds and leaves a complete state, or the operation fails and the observable state remains as it was before the operation began**. This is an important API design goal when a method can throw an exception while updating an object.

To evaluate an operation, it is necessary to clearly identify:

- **Prior state**: which values and resources are allowed to be modified by the operation?
- **Invariants**: which conditions must always hold true, such as every quantity being positive and the total equaling the sum of all line items?
- **Potential failure points**: input validation, arithmetic overflow, memory allocation, callbacks, file writes, data queries, or external service calls?
- **State after failure**: is the object still valid, or must it be identical to the prior state? Can external actions observe a partial change?

An exception **does not automatically restore** variables, collections, files, or written data. The **catch** statement only intercepts control flow; **finally** and try-with-resources handle resource cleanup. None of those mechanisms automatically revert changes that have already occurred.

## 2. Distinguishing exception-safety guarantees

Commonly used guarantee levels to describe state-mutating operations:

| Guarantee level | When the operation throws an exception | Example meaning |
| --- | --- | --- |
| No explicit guarantee | State may be invalid or no longer safe to use | The list has added the new line item, but the total variable has not been updated |
| **Basic guarantee** | Invariants are preserved; the object remains valid, though it may have changed partially | Some valid items were added before the operation stopped |
| **Strong guarantee / failure atomicity** | State within the committed scope is preserved as it was before the operation | If adding fails, neither the list nor the total changes |
| **No-throw guarantee** | The operation is designed not to throw exceptions within the guaranteed scope | A reference assignment that has already been prepared, under normal operating conditions |

The **basic guarantee** is sufficient for some sequential processing operations: if a failure occurs at the third record, the first two records may have been processed while the overall object remains consistent. The **strong guarantee** is a stricter requirement when the API means "succeed completely or fail completely."

You must not infer the guarantee level from whether a method declares **throws**, from checked/unchecked exception types, or from whether the code has **try/catch**. The guarantee level depends on the order of data modifications, state design, and actual side effects.

This concept also differs from two other common meanings of "atomic":

- **Atomicity in concurrency**: whether other threads can see intermediate states. An operation can be synchronized with a lock and still leave partial data behind after an exception.
- **Atomicity in storage transactions**: database management systems or file-writing mechanisms provide their own rules. Assigning a reference in RAM does not automatically turn two file writes or two HTTP calls into a transaction.

## 3. Java 17+ example: seeing partial state and how to fix it

The following example uses an immutable snapshot consisting of a list of quantities and a total quantity. Both methods take the same input but differ in their update order:

- **addBroken** publishes the new list first and only then validates the condition and computes the total. When an exception is thrown, the caller still sees the modified list.
- **addSafe** validates the input, computes, and builds the entire new snapshot first; only when no exception occurs does it swap a single state reference.

Save the following program to **FailureAtomicityDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class FailureAtomicityDemo {
    static final class Cart {
        record Snapshot(List<Integer> quantities, int total) {}

        private volatile Snapshot state =
                new Snapshot(List.of(), 0);

        Snapshot snapshot() {
            return state;
        }

        synchronized void addBroken(int quantity) {
            Snapshot before = state;
            List<Integer> updated = new ArrayList<>(before.quantities());
            updated.add(quantity);

            // Publish a partial change too early.
            state = new Snapshot(List.copyOf(updated), before.total());

            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }

            int newTotal = Math.addExact(before.total(), quantity);
            state = new Snapshot(List.copyOf(updated), newTotal);
        }

        synchronized void addSafe(int quantity) {
            // All steps that can fail happen before commit.
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }

            Snapshot before = state;
            int newTotal = Math.addExact(before.total(), quantity);
            List<Integer> updated = new ArrayList<>(before.quantities());
            updated.add(quantity);
            Snapshot candidate =
                    new Snapshot(List.copyOf(updated), newTotal);

            // A single step to publish the complete state.
            state = candidate;
        }
    }

    public static void main(String[] args) {
        Cart broken = new Cart();
        broken.addBroken(2);

        try {
            broken.addBroken(-1);
        } catch (IllegalArgumentException e) {
            System.out.println("Broken rejected: " + e.getMessage());
        }

        System.out.println("Broken: "
                + broken.snapshot().quantities()
                + ", total=" + broken.snapshot().total());

        Cart safe = new Cart();
        safe.addSafe(2);
        Cart.Snapshot beforeFailure = safe.snapshot();

        try {
            safe.addSafe(-1);
        } catch (IllegalArgumentException e) {
            System.out.println("Safe rejected: " + e.getMessage());
        }

        System.out.println("Safe: "
                + safe.snapshot().quantities()
                + ", total=" + safe.snapshot().total());

        if (!beforeFailure.equals(safe.snapshot())) {
            throw new AssertionError("State changed after failure");
        }

        try {
            safe.addSafe(Integer.MAX_VALUE);
        } catch (ArithmeticException e) {
            System.out.println("Overflow rejected: " + e.getMessage());
        }

        System.out.println("After overflow: "
                + safe.snapshot().quantities()
                + ", total=" + safe.snapshot().total());
    }
}
~~~

Compile and run with Java 17 or later:

~~~bash
javac FailureAtomicityDemo.java
java FailureAtomicityDemo
~~~

Expected output:

~~~text
Broken rejected: quantity must be positive
Broken: [2, -1], total=2
Safe rejected: quantity must be positive
Safe: [2], total=2
Overflow rejected: integer overflow
After overflow: [2], total=2
~~~

**Why do the results differ?**

In the broken version, **state** is replaced with a snapshot containing the list **[2, -1]** while the total remains **2**. Then the condition **quantity <= 0** throws an exception, skipping the final total update. The remaining data both contains an invalid quantity and violates the invariant "total equals the sum of elements."

In the safe version, the negative-quantity branch fails **before** replacing **state**. The overflow branch uses **Math.addExact**, so it does not silently wrap the integer and also does not update the state. The check using **equals** verifies that the snapshot after the exception equals the previous snapshot.

There are three important design details:

1. **List.copyOf** creates a list that cannot be modified through the **List** API and rejects **null** elements. It should only be called a deeply immutable snapshot if the elements inside are themselves immutable; here the elements are **Integer**.
2. **volatile** ensures reading threads see the published snapshot; **synchronized** serializes writes, preventing two threads from reading the same old state and overwriting each other's updates. Using **volatile** alone without coordinating multiple writers is not enough.
3. Building the new snapshot can throw an exception before assigning **state**. Within the scope of this in-memory state operation, a final reference assignment is the publication point of the complete state. The example does **not** claim to recover from all fatal VM errors, such as an **OutOfMemoryError** occurring at an arbitrary point.

The example intentionally keeps both methods in the same class for comparison; in a real API, only the variant that satisfies the chosen contract should be exposed.

## 4. Design pattern: prepare first, publish later

For an aggregate that can be represented by a single state value, a reliable approach is:

1. **Define invariants and the scope of the guarantee**: which fields, collections, and relationships must be consistent together?
2. **Validate preconditions** before mutation: arguments, permissions, business rules, and feasibility.
3. **Compute results that may fail**: such as **Math.addExact**, parsing, conversions, copying, collection allocation, and data mapping.
4. **Build a complete state instance** using local values or new objects, not yet published to other callers.
5. **Commit at a single clear point**: assign a fully constructed snapshot, or use a transactional mechanism appropriate for the data.
6. **Specify post-commit consequences**: if callbacks, notifications, logging, or event emission fail, how will the method reflect that?

The flow diagram can be visualized as follows:

~~~text
State S0
    |
    v
Validate and prepare candidate S1
    |               |
  Error          Success
    |               |
    v               v
Keep S0        Commit S1 once
                    |
                    v
                   End
~~~

Do not treat "validate upfront" as a universal solution. If two truly independent writes can both fail, early input validation still cannot prevent a failure in the second write. In that case, you need to change the state representation, use staging, transactions, or an explicit contract that only guarantees the basic level.

### When an object contains multiple interdependent fields

With state such as **balance**, **reserved**, and **available**, updating each field individually creates an inconsistent window if one step throws an exception. Encapsulating them into an immutable record, building a new record, and then publishing a single reference helps avoid partially coordinated states in RAM.

For collections, the sequence **clear → addAll → fix total** is still multiple mutating steps. Finishing the computation of a temporary collection is not enough if you then copy it back into the public collection through multiple calls that can fail. You need to keep the old state intact until you can swap in a reference pointing to the new collection.

### When there are multiple writers and readers

A copy computed from S0 can become stale if another writer has committed S1 in the meantime. You can synchronize the entire read-compute-write sequence, or use **AtomicReference** with a compare-and-set loop when appropriate. With compare-and-set, every attempt must recompute from the currently valid snapshot; do not run non-idempotent side effects inside the retry loop. If each computation calls a billing service or sends an email, a failed CAS iteration can produce duplicate side effects.

Conversely, **AtomicInteger**, **volatile**, or **synchronized** do not automatically guarantee rollback when the code inside has already modified data before an exception. They solve certain visibility and thread-contention issues, whereas failure atomicity requires designing the failure path.

## 5. Money transfer case: two changes that must commit together

Suppose two balances **source** and **destination** are managed within the same object. Code like the following risks a partial update:

~~~java
// Illustrative code; source and destination are two
// mutable balance fields declared elsewhere.
source -= amount;
destination = Math.addExact(destination, amount);
~~~

If adding to the destination throws an **ArithmeticException**, money has already been deducted from the source. Swapping the order of the two lines does not fundamentally solve the problem; the second update line can still fail.

If all balances are owned by a single in-memory aggregate, you can prepare the result as a shared snapshot:

~~~java
record Balances(long source, long destination) {}

// Illustration inside a method with permission to write state.
// before is the current immutable snapshot.
if (amount <= 0 || amount > before.source()) {
    throw new IllegalArgumentException("invalid amount");
}

long nextSource = Math.subtractExact(before.source(), amount);
long nextDestination = Math.addExact(before.destination(), amount);
Balances next = new Balances(nextSource, nextDestination);

// Commit: swap a single shared reference from before to next;
// requires writer synchronization or appropriate CAS.
balances = next;
~~~

The two snippets above are **contextual illustrative code**, not standalone programs. They highlight the difference in mutation ordering and do not replace the runnable example in Section 3.

If the source and destination reside in **two database records**, the operation must use a real transaction with an appropriate rollback path according to the storage engine. If they reside in **two independent services or two independent databases**, a local transaction does not create global atomicity. You must design a distributed workflow, idempotency, transitional states, and failure handling; techniques such as saga/compensation can restore business consistency, but they do not mean external parties never observed intermediate changes.

## 6. Why manual rollback with catch can still be wrong

The pattern below looks as if it handles errors, but it is not enough to claim atomicity:

~~~java
// Illustrative code: undo() can also fail.
applyFirstChange();
try {
    applySecondChange();
} catch (RuntimeException failure) {
    undoFirstChange();
    throw failure;
}
~~~

Scenarios to consider:

- **applyFirstChange** completes partially and throws an exception itself before entering the **try** block; no undo branch runs.
- **undoFirstChange** may throw another exception, leaving the state unrestored and masking the original exception.
- Another observer has already seen the first change; undoing it later cannot erase the observed experience or side effect.
- An external call has already sent an email, emitted an event, or transferred real money; calling an inverse function is unlikely to make everything as if it had never happened.

If you must roll back, document the scope, reversal order, what happens when rollback fails, how the original exception is preserved, and the subsequent recovery mechanism. For resources with real transactions, prefer using that system's transaction. For in-memory state, it is usually easier to verify when you avoid modifying the live state until preparation is complete.

**finally** and try-with-resources are essential for closing streams, returning connections, and releasing locks as contracted. They ensure resource lifecycle cleanup on both success and failure paths; they **do not automatically undo** written content, sent requests, or mutated objects.

## 7. Subtle pitfalls often overlooked in real-world APIs

### Post-commit callbacks and notifications

Suppose a method updates successfully and then invokes a listener:

~~~java
state = candidate;                 // Committed.
listener.onChanged(candidate);     // May throw an exception.
~~~

If the listener throws an error, the caller receives an exception even though the state has already changed. That method **does not satisfy** a promise that "any exception preserves the old state." You can choose a different contract: the commit succeeds, and notification failures are reported/logged separately, retried independently, or handled via an outbox. The key is that the API contract and the execution path must match reality.

Calling the listener **before commit** is not necessarily safe either: the listener may trigger side effects or retain a reference to the candidate data. Separate the pure preparation phase from operations that produce external side effects.

### Writing files and replacing data

Overwriting a target file directly can leave partial content behind if the write fails. One design approach is to create a **temporary file on the same filesystem**, write all data, close the resource, and only then replace the target path using an atomic move operation **when the filesystem supports it**. In Java, **Files.move** with **StandardCopyOption.ATOMIC_MOVE** can throw **AtomicMoveNotSupportedException**; you must decide whether to accept a weaker fallback. Rename atomicity also differs from durability after power loss; for durability guarantees, you must consider flush/fsync and the specific filesystem.

### Databases, networks, and events

- A database transaction only protects operations that actually participate in that transaction according to the database's mechanism. An HTTP request or an email lies outside that transaction.
- A network timeout does not prove the remote operation failed; the server may have committed while the response was lost.
- When retrying an operation with side effects, consider idempotency keys, deduplication, result states, and retry policies.
- Do not emit a "success" message from an uncommitted state; if you need coordinated guarantees between data and events, consider a transactional outbox at the appropriate architectural layer.

### Aliases, mutable objects, and snapshot scope

A new list that contains the same mutable elements can still be modified through another reference. **List.copyOf** only protects the list structure; it does not make nested objects deeply immutable. If a caller directly receives an internal mutable object, they can modify data without going through the commit path. To make a reliable snapshot guarantee, control ownership, copy appropriately, or use immutable value objects throughout.

### Which error types are covered by the contract?

API documentation should specify which errors are guaranteed to be handled, such as **IllegalArgumentException**, **ArithmeticException**, or I/O errors accounted for in the design. You should not promise absolute rollback when the process is killed, the machine loses power, the VM encounters fatal errors, or external systems lack transactions. You can apply strong failure atomicity within a very specific scope, such as "the in-memory snapshot of Cart remains unchanged when addSafe throws an exception before commit," and a different guarantee level for networking or storage.

## 8. How to test failure paths

Tests must **prove the state after failure**, rather than only checking that an exception was thrown. A useful workflow:

1. Set up a valid state S0 and capture a complete snapshot of all parts covered by the guarantee.
2. Trigger a failure at each potential failure point: invalid arguments, overflow, computation steps, allocation, simulated storage, callbacks.
3. Catch the **exact expected exception type**, then verify the current state against S0 according to the published guarantee level.
4. Perform another valid operation after the failure to prove the object continues working properly.
5. Test concurrency separately if multiple threads can read/write; sequential failure-atomicity tests do not prove linearizability across threads.

In the runnable example, **beforeFailure.equals(safe.snapshot())** verifies the strong guarantee for negative input. The call with **Integer.MAX_VALUE** verifies another failure path: arithmetic overflow. In real projects, you can add fault injection to force errors in dependencies; avoid writing mocks just to reassert the mock's own logic instead of observing application state.

A scenario checklist is often more useful than testing only the happy path:

| Failure point | Expectation for the aggregate's strong guarantee |
| --- | --- |
| Argument validation fails | No changes are published |
| Computation causes overflow | Current snapshot remains unchanged |
| Creating new collection/record fails before commit | Old snapshot remains |
| Two writers update concurrently | No lost updates; each commit is based on a valid state |
| Post-commit callback fails | Must have its own contract; cannot casually be called a whole-method strong guarantee |
| External storage/network operation fails | Must evaluate transaction mechanisms, idempotency, and corresponding guarantee scope |

## 9. Common misconceptions and how to spot them

**"Throwing an exception means nothing happened."** False: an exception only indicates that execution branched onto the error path. Inspect all mutations performed before the throw point.

**"Wrapping with synchronized makes the operation atomic."** A lock can prevent other threads from observing intermediate states when they obey the same lock, but it does not restore data if the last statement throws; once the lock is released, the corrupted state can be exposed.

**"Putting validation at the top is enough."** Not enough if after validation there are still computations, allocators, callbacks, or I/O that can fail after mutation.

**"I copied the collection, so it must be atomic."** If you publish the copy too early or use **clear/addAll** to mutate the original collection back, the operation still has multiple update points.

**"Just catch and ignore so the application keeps running."** Swallowing errors makes partial state hard to detect. Only recover when you have a real recovery plan; otherwise, rethrow with appropriate context and let the responsible layer handle it.

**"Manual rollback always returns the world to its old state."** Undoing can also fail and cannot retract side effects that others have already observed.

**"All exceptions must guarantee no state change."** An API may intentionally provide the basic guarantee or report partial progress. What matters is stating the contract clearly and implementing it consistently.

## 10. Applying this in Java method design

Before writing a multi-step state-mutating method, ask yourself:

- If an exception occurs after each potentially failing line, what state is the data in?
- Which fields form **a single shared invariant**? Can they be stored together in an immutable snapshot?
- Are the preparation steps completely internal and free of side effects?
- Can a **single commit point** be created? If not, what is the actual transactional mechanism?
- On retry, is there a risk of repeating a side effect or losing updates between writers?
- When a caller receives an exception, does the API documentation promise "unchanged," "still valid," or "may partially complete"?
- Which tests compare before-and-after state, including overflow, I/O, and thread contention paths?

**Key takeaway:** Failure atomicity is a guarantee about **the observable state after an operation fails**, not an automatic property of exception handling. For in-memory data, the most verifiable approach is **validate → compute and build candidate state → commit once**. When an operation spans databases, files, or external services, you must redefine the scope of the guarantee and use the corresponding transaction/recovery mechanisms.