# Checking Conditions Before Mutating State in Java

> **Topic:** Java Core — Exception · **Knowledge Group:** State Preservation. The goal is to design methods so that invalid input or invalid business conditions are detected before an object is partially updated, thereby preserving invariants and providing a predictable failure contract.

## 1. Why Must You Validate Before Mutating State?

An operation can fail due to invalid arguments, a current state that does not meet requirements, arithmetic overflow, exhausted resource capacity, or an external dependency throwing an exception. If a method modifies part of the data before detecting an error, the object can end up in a confusing state: a balance is deducted while the transaction history is not recorded, one item's inventory is reduced while a second item remains unchanged, or configuration is only half-updated.

For stateful objects, three concepts should be distinguished:

- **Precondition:** a condition that must be satisfied *before the operation*, such as order quantity being greater than 0, the product SKU existing, or the target account being valid.
- **Invariant:** a condition that must hold true in every valid observable state, such as non-negative inventory, total balance across accounts not being created out of thin air or lost during an internal transfer, or the item list and total price remaining consistent.
- **Postcondition:** a condition that holds true when the operation succeeds, such as inventory decreasing by the exact requested amount.

**Practical rule:** verify preconditions and compute in advance anything that can fail, and only then publish the new state. If an exception is thrown along the validation path, the observable state of the object should remain unchanged unless the API explicitly documents a weaker guarantee.

Order matters because `throw` immediately transfers control out of the normal execution flow. Assignments that have already executed **do not automatically roll back** just because code enters a `catch` or `finally` block.

## 2. Anti-Pattern: Mutating Partially Before Detecting an Error

Suppose a shopping cart stores quantity and total price, with invariants `quantity >= 0` and `totalCents >= 0`. The following **incomplete illustration** is very error-prone:

~~~java
// Incorrect illustration: only the method body of a class with fields quantity, totalCents.
void add(int amount, long unitPriceCents) {
    quantity += amount;                      // State is mutated first
    if (amount <= 0) {
        throw new IllegalArgumentException("amount must be positive");
    }
    if (unitPriceCents < 0) {
        throw new IllegalArgumentException("negative price");
    }
    totalCents += amount * unitPriceCents;  // Can overflow long
}
~~~

There are at least three risks:

1. `amount <= 0` is detected **after** `quantity` has already changed.
2. `unitPriceCents < 0` stops the method after one update but before the next update.
3. Multiplication or addition on `long` overflows according to Java arithmetic rules **without throwing an exception**; the result can be wrong and cause the state to violate business domain rules.

Moving all `if` checks before the two assignments improves the design, but it is still not enough if subsequent computations, allocations, callbacks, or I/O can fail. You must consider all steps capable of throwing an exception, not just explicit `throw` statements.

## 3. Implementation Pattern: Validate → Prepare → Commit

A controllable design approach is to clearly separate three phases:

1. **Validate:** verify that inputs have the right type, are non-null, and fall within allowed ranges; confirm the current state satisfies requirements; check permissions, relational constraints, and any conditions known in advance.
2. **Prepare:** compute results, copy or construct the new state in local variables, and detect overflow using `Math.addExact`/`Math.multiplyExact`. If this step fails, the live state remains intact.
3. **Commit:** put the validated state into use at a single clear point, such as assigning one reference to a new immutable value. If multiple places are updated, an appropriate mechanism is required to ensure atomicity.

~~~text
input + current state
          |
     valid checks?
       /       \
      no       yes
      |         |
 throw exc.   build proposed state
  no state        |
  mutation    prepare succeeded?
                /          \
               no          yes
               |            |
          throw exc.      commit
           no state         |
           mutation    valid new state
~~~

A useful rule: **try to move operations that can fail before the commit point**, while the commit operation itself should be short, simple, and free of arbitrary user code calls. Do not confuse "checked all `if` conditions" with "no remaining statement can throw an exception".

### Common Checks Needed

| Constraint type | Java example / how to evaluate | Consequence if omitted |
|---|---|---|
| Null | `Objects.requireNonNull(value, "value")` | NPE occurs mid-way instead of at the API boundary |
| Numeric range | `amount > 0`, `discount <= 100` | Negative or out-of-bounds values are persisted |
| Index | `index >= 0 && index < size` | `IndexOutOfBoundsException` after other side effects |
| Cross-parameter relation | `start <= end`, quantity and unit price compatible | Inconsistent internal data |
| Object state | sufficient stock, currently open, still authorized | Mutation while state forbids it |
| Collection-wide constraint | all elements valid; no duplicate keys; total demand within budget | Updating elements one by one before hitting an invalid one |
| Arithmetic overflow | `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact` | Arithmetic wraps around and breaks invariants |
| Mutable input data | create a reasonable copy before iterating; require caller not to mutate concurrently | Each validation pass sees different contents |

Validation must be based on **the exact state at the time of writing**, especially under concurrency. Early validation at the UI layer is helpful for error messages, but it cannot replace consistent validation at the state-management layer.

## 4. Standalone Java 17+ Example: Batch Inventory Reservation

Requirement: an inventory stores available quantities by SKU; a single `reserve` call may request multiple items. If **any** SKU does not exist, has an invalid quantity, or has insufficient stock, the entire call must fail **without reducing inventory for any item**.

The design uses a `Map` as private state. The method builds a proposed copy in memory, validates all requests, computes the new stock levels, and reassigns the state field **at the very end**. All observer and mutator methods use the same `synchronized` lock so another thread cannot interleave between this object's validation and commit.

Save the program as **`ValidateBeforeMutationDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class ValidateBeforeMutationDemo {
    static final class Inventory {
        private Map<String, Integer> stock;

        Inventory(Map<String, Integer> initial) {
            Objects.requireNonNull(initial, "initial");
            Map<String, Integer> copy = new HashMap<>();

            for (Map.Entry<String, Integer> entry : initial.entrySet()) {
                String sku = Objects.requireNonNull(entry.getKey(), "sku");
                Integer count = Objects.requireNonNull(entry.getValue(), "count");
                if (count < 0) {
                    throw new IllegalArgumentException("negative initial stock: " + sku);
                }
                copy.put(sku, count);
            }

            stock = copy;
        }

        public synchronized void reserve(Map<String, Integer> request) {
            Objects.requireNonNull(request, "request");

            // Phase 1: validate the entire request before mutating real state.
            Map<String, Integer> validated = new HashMap<>();
            for (Map.Entry<String, Integer> entry : request.entrySet()) {
                String sku = Objects.requireNonNull(entry.getKey(), "sku");
                Integer quantity = Objects.requireNonNull(entry.getValue(), "quantity");
                if (quantity <= 0) {
                    throw new IllegalArgumentException("quantity must be positive");
                }

                Integer available = stock.get(sku);
                if (available == null) {
                    throw new IllegalArgumentException("unknown SKU: " + sku);
                }
                if (quantity > available) {
                    throw new IllegalArgumentException("insufficient stock: " + sku);
                }

                validated.put(sku, quantity);
            }

            // Phase 2: all updates only affect a local copy.
            Map<String, Integer> next = new HashMap<>(stock);
            for (Map.Entry<String, Integer> entry : validated.entrySet()) {
                String sku = entry.getKey();
                next.put(sku, next.get(sku) - entry.getValue());
            }

            // Phase 3: publish the new state in a single assignment.
            stock = next;
        }

        public synchronized int available(String sku) {
            Objects.requireNonNull(sku, "sku");
            Integer count = stock.get(sku);
            if (count == null) {
                throw new IllegalArgumentException("unknown SKU: " + sku);
            }
            return count;
        }
    }

    public static void main(String[] args) {
        Inventory inventory = new Inventory(Map.of("book", 4, "pen", 3));

        try {
            inventory.reserve(Map.of("book", 2, "pen", 5));
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected: " + ex.getMessage());
        }

        System.out.printf("After failure: book=%d, pen=%d%n",
                inventory.available("book"), inventory.available("pen"));

        inventory.reserve(Map.of("book", 2, "pen", 1));

        System.out.printf("After success: book=%d, pen=%d%n",
                inventory.available("book"), inventory.available("pen"));
    }
}
~~~

Compile and run (JDK 17 or newer):

~~~bash
javac ValidateBeforeMutationDemo.java
java ValidateBeforeMutationDemo
~~~

**Exact standard output:**

~~~text
Rejected: insufficient stock: pen
After failure: book=4, pen=3
After success: book=2, pen=2
~~~

In the first reservation, `pen` requests 5 while only 3 remain; even though `book` is valid, its stock is **not reduced** because `stock` has not been reassigned. Iteration order of `Map.of` is not guaranteed, but this sample has only one invalid item so the exception message remains deterministic. The second call succeeds and updates both SKUs together at the state level observable through `Inventory`'s API.

**Why is this stronger than merely adding `if` statements?** After the validation phase, two steps can still fail: creating the `HashMap` copy and writing values into that copy. Both happen before `stock = next`; if an error is thrown during those operations, the `stock` field still points to the old map. The object never exposes its internal `Map` for external callers to mutate directly.

**Chosen limitations:** calls accessing `Inventory` must go through the synchronized methods above. Callers must not mutate `request` concurrently while `reserve` is iterating; supporting concurrently mutated input requires designing a snapshot mechanism or synchronizing with the input's owner. This example operates within a single JVM's memory; it does not by itself provide transactions for databases or multiple processes.

## 5. How Correct Must State Be After Throwing an Exception?

The following terms help express an API's **guarantee level**. This describes exception safety, not Java's `throws` syntax classification.

| Guarantee level | When an operation fails | Example |
|---|---|---|
| No explicit guarantee | The object may no longer satisfy its invariants | Deducting balance then throwing before completing the update |
| **Basic guarantee** | The object remains valid per its invariants, but partial changes may have occurred | A collection adds some elements, then a subsequent operation fails |
| **Strong guarantee** | Failure does not change the observable state of the object (*all-or-nothing*) | Building a copy and swapping the reference only after preparation succeeds |
| No-throw within committed scope | The step produces no errors within the defined contract scope | A simple reference assignment at commit under normal runtime conditions |

For multi-step operations that represent a transaction, the **strong guarantee** is usually a reasonable target: on success apply everything, on failure apply nothing. However, you must never promise absolute guarantees for infrastructure failures such as sudden JVM termination, out-of-memory errors, power loss, or an external system having already received part of a request. Define the state scope and failure types that the API commits to preserving.

Do not infer a strong guarantee merely because every invalid-input branch has a `throw` before updating. An `OutOfMemoryError`, a setter invoking a callback, an unchecked arithmetic operation, or an I/O call can still cause the operation to fail mid-update.

## 6. Checking Arithmetic Before Commit: Avoiding Silent Overflow

Checking `amount >= 0` does not mean `balance + amount` stays within integer bounds. With `long`, overflowing addition wraps around according to Java's fixed-width arithmetic rules and **does not** throw an exception automatically.

How to guard when updating a single field:

~~~java
// Snippet in a class with field private long balance;
// requires balance >= 0 and rejects negative amounts.
public void deposit(long amount) {
    if (amount < 0) {
        throw new IllegalArgumentException("negative amount");
    }
    long next = Math.addExact(balance, amount);
    balance = next;
}
~~~

`Math.addExact` throws `ArithmeticException` if `long` overflows, and the assignment is not executed. In multithreaded systems, reading `balance`, checking, computing, and assigning must all be protected by the same synchronization mechanism; this snippet only illustrates update logic in a single-threaded context or while holding a lock.

For price × quantity multiplication, compute beforehand:

~~~java
// Snippet: amount and unitPriceCents have already been validated.
long addedCents = Math.multiplyExact((long) amount, unitPriceCents);
long nextTotal = Math.addExact(totalCents, addedCents);
int nextQuantity = Math.addExact(quantity, amount);

// Only commit after all three calculations succeed.
totalCents = nextTotal;
quantity = nextQuantity;
~~~

The last two assignments are two separate updates. For an object only observed while holding the same lock, the operation can achieve atomicity at the API level; if there are callbacks, unsynchronized getters, or direct observation between the two assignments, redesign to protect a consistent snapshot. A cleaner approach is to encapsulate quantity and total price in an immutable value object and swap a single reference to that object.

## 7. Distinguishing Parameter Validation from Business State Validation

**Invalid arguments:** values that are inherently incompatible with the contract, such as a negative quantity, a `null` input ID, or an out-of-range index. In many Java APIs, `IllegalArgumentException`, `NullPointerException` (via `Objects.requireNonNull`), and `IndexOutOfBoundsException` are clear choices.

**State forbids the operation:** arguments may be valid, but the object is closed, the order is already confirmed, or the transaction is already finalized. `IllegalStateException` is typically appropriate for API state-usage violations.

**Rejection by normal business rules:** for example, out of stock or exceeding a credit limit. For systems that need to classify and handle these conditions, a dedicated business exception (or a result type representing an expected failure) can be clearer. Not every rejection needs to be treated as a programming bug. Choosing checked vs. unchecked depends on the caller's ability to recover and the published public contract.

Example:

~~~java
// Snippet validating input and state inside a method.
Objects.requireNonNull(orderId, "orderId");
if (quantity <= 0) {
    throw new IllegalArgumentException("quantity must be positive");
}
if (closed) {
    throw new IllegalStateException("order is already closed");
}
if (quantity > availableStock) {
    throw new InsufficientStockException(orderId);
}
~~~

This is **illustrative code**, assuming the variables and `InsufficientStockException` class already exist in the application. Exception types and error messages should be documented parts of the API when clients rely on them.

Before allowing a state-mutating operation, validation should read from the **current source of truth**. With a database, a value read earlier in the UI or cache may be stale; with an object, state must be protected against concurrent updates.

## 8. Avoiding "Check-Then-Act" Bugs Under Concurrency

Unsafe pattern:

~~~java
// Incorrect if multiple threads access concurrently without synchronization.
if (account.balance() >= amount) {
    account.withdraw(amount);
}
~~~

Between `balance()` and `withdraw()`, another thread may have already withdrawn funds. The check was true at read time but no longer true at write time: this is a *time-of-check to time-of-use* (TOCTOU) bug.

The solution is to put **validation and update into the same atomic operation over the relevant state scope**:

- Within a single JVM object: protect read-validate-compute-write with the same lock, or use CAS with `AtomicReference` pointing to immutable state where appropriate.
- In a database: use a transaction with an appropriate isolation level, row locks, or conditional update statements; check the updated row count to verify the condition still held at commit time.
- Across multiple objects/resources: define lock scopes and a consistent lock ordering to avoid deadlocks; do not assume `synchronized` on one object automatically protects other objects.
- With caller-owned mutable input: require a copy/snapshot or a no-concurrent-mutation contract; locking on the target object does not lock a `Map` that the caller is still modifying.

**Note:** `volatile` establishes visibility and memory ordering for certain accesses, but it does not make a "check-then-update" sequence atomic. For the pattern of swapping an immutable snapshot, `volatile` can help publish the reference safely; a lock or CAS is still needed to prevent writers from overwriting each other's results.

## 9. Updating Multiple Fields, Multiple Objects, or External Resources

### 9.1. Multiple Fields Within One Object

You can validate everything first and then perform two assignments; however, if two fields must stay semantically synchronized, prefer grouping them into an immutable state:

~~~java
// Conceptual standalone snippet; MoneyState is an immutable record.
record MoneyState(long cents, int version) {}

private MoneyState state = new MoneyState(0L, 0);

public synchronized void add(long cents) {
    if (cents < 0) {
        throw new IllegalArgumentException("negative cents");
    }
    long nextCents = Math.addExact(state.cents(), cents);
    int nextVersion = Math.addExact(state.version(), 1);
    state = new MoneyState(nextCents, nextVersion);
}
~~~

This snippet lives inside a class containing `state` and `add`, not a standalone Java file. Both `MoneyState` and its replacement values are constructed before assignment; APIs reading `state` need a consistent synchronization/publication policy. A `record` is a useful tool for representing immutable data as long as its components do not expose mutable state either.

### 9.2. Two Objects or Multiple Resources

Transferring money from account A to B involves at least one debit and one credit. Checking that A has sufficient funds is necessary, but **if debiting A succeeds and crediting B fails**, the prior check cannot save data integrity. You must combine pre-validation with an atomic commit mechanism for both accounts, such as locking both in the same JVM in a consistent lock order, or using a transaction when the data resides in a database.

### 9.3. I/O, Network, and Side Effects

Writing a file, sending an email, processing a payment, publishing an event, or calling a remote API may have already caused side effects before the client receives a timeout error. Not receiving a success response **does not prove** the remote operation did not happen. Therefore:

- Validate data before creating side effects.
- When a database transaction is available, place updates that must be consistent in the same transaction.
- When publishing an event must accompany a data commit, consider the *transactional outbox* pattern.
- For retryable commands, design an *idempotency key* to reduce the risk of duplicate execution.
- Define the "committed but notification failed" state and its reconciliation strategy; `finally` is only useful for cleanup and does not automatically roll back side effects.

Separate **precondition validation failures** from **post-commit execution failures** in the API contract. If listeners or callbacks are invoked before commit, they might see stale state or throw errors that abort the process; if invoked after commit, you must document the possibility of "state changed, but notification failed".

## 10. Common Mistakes

1. **Mutating data first and then calling `throw`:** the error path leaves the object half-updated. Move checks and computations before the commit.
2. **Validating and mutating element by element:** the third element is invalid, but the first two have already been mutated. Validate the whole batch or build a separate result structure.
3. **Validating arithmetic inputs while ignoring overflow:** `int`/`long` can wrap around; use `Math.*Exact` or enforce domain-appropriate bounds.
4. **Relying on `assert` for input validation:** `assert` can be disabled when running the JVM; never use it to enforce public contracts or validate untrusted input.
5. **Retaining a caller's mutable reference:** the caller can modify the collection after validation. Make defensive copies or use immutable value objects; under concurrency, require a snapshot.
6. **Putting getters/setters with side effects into the validation phase:** these calls can throw exceptions or mutate state. Minimize reliance on callbacks and external code before commit.
7. **Overwriting the original exception with an error-handling failure:** rollback, cleanup, or logging can also fail. Preserve `cause` and suppressed exceptions where appropriate; do not swallow the original error.
8. **Catching `Exception` and pretending it succeeded:** if you cannot roll back or prove invariants still hold, report failure properly.
9. **Checking outside a lock, updating inside a lock:** the check result may already be stale; re-validate inside the same synchronized region.
10. **Assuming throwing `RuntimeException` guarantees rollback:** the exception type does not automatically revert in-memory state. You must design operation ordering and transaction boundaries explicitly.

## 11. How to Test State-Preservation Contracts

Design tests from the perspective of observable state **before and after failure**, rather than only writing `assertThrows`:

| Scenario | What to verify |
|---|---|
| `null` argument, negative number, out-of-bounds value | Correct exception type; prior state unchanged |
| One invalid element at the start/middle/end of a batch | No valid elements were committed early |
| Insufficient resources, exceeded limit, closed state | Invariants remain true; message is clear enough for caller decisions |
| Arithmetic overflow | No corrupted arithmetic result is committed |
| Preparation step throws an error | Live state still points to the old snapshot |
| Two concurrent operations on the same resource | No lost updates, negative quantities, or constraint violations |
| I/O/transaction/callback failure | Accurately observe and record whether state was committed or not |
| Success | Postconditions are exact; new state satisfies all invariants |

For `Inventory` in the full example, a minimal test verifies both **failure and success**: call `reserve(book=2, pen=5)`, assert `book=4`, `pen=3`; then call `reserve(book=2, pen=1)` and assert `book=2`, `pen=2`. If a test only checks for `IllegalArgumentException`, it can miss a bug that already decremented `book` before throwing.

For multithreaded systems, add controlled contention tests (barriers/latches), verify final invariants, and apply appropriate concurrency testing techniques. A single passing test run does not prove an algorithm is race-free; lock/CAS design and reasoning about the commit point remain essential.

## 12. Checklist When Designing a New Method

- **Define invariants:** what constitutes valid state, and through which APIs is it observed externally?
- **Write preconditions:** parameters, permissions, business state; specify the exception or result when violated.
- **Mark every side effect:** assignments, collection mutations, DB writes, I/O, callbacks, event publishing.
- **Identify steps that can fail:** memory allocation, arithmetic, type conversions, dependent services, validations with side effects.
- **Choose the commit point:** prefer swapping a valid snapshot; for multiple resources, use transactions or an appropriate coordination mechanism.
- **Keep validation and commit consistent under concurrency:** same lock, CAS, or conditional transaction.
- **Do not let mutable references escape before commit:** prevent external code from observing an in-progress draft.
- **Test failure paths:** after every possible exception, do invariants and the promised guarantee level still hold?
- **Document non-rollbackable cases:** especially for network, files, payments, or emitted events.

## 13. Key Takeaways

**Checking conditions before mutating state** is the first step in designing exception-safe APIs. To achieve the strong guarantee, extend it into the **validate → prepare → commit** pipeline, where failure-prone computations and modifications run on temporary data before real state becomes observable. Under concurrency or with external resources, the commit point must be protected by locks, CAS, transactions, or an equivalent protocol. The most important self-review question is: *If this operation throws an exception at any step, what state will the caller observe?*

### References

- [Java SE 17 — `Objects.requireNonNull`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T))
- [Java SE 17 — `Math.addExact` and overflow-checked operations](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html)
- [Java SE 17 — `synchronized` and the Java Memory Model (JLS §17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html)
- [Java SE 17 — `AtomicReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html)
