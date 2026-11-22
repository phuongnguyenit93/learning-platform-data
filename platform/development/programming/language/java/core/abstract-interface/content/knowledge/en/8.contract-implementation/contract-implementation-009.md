# Preserving Contract Semantics Alongside Successful Compilation

## Objectives

In Java, a class can successfully `implements` an interface, declare all required methods, compile without errors, and still **violate what users of the interface have the right to expect**. This lesson helps you distinguish between an **API shape** contract and a **behavioral** contract, express behavioral rules clearly, design interchangeable implementations, and verify those rules using Java 17+ examples.

This is a core skill when implementing an interface or extending an abstract class: the compiler protects part of the program's structure; implementation quality also depends on the semantics promised by the API.

## 1. A Contract Has Multiple Layers

Consider the following interface:

```java
interface Counter {
    void increase();
    int value();
}
```

A `Counter` class that implements `increase()` by setting the value to `0` can still compile, because Java checks that the method exists and is compatible in signature, return type, access level, certain exception constraints, and type relationships. However, if the published meaning is “`increase()` increments the counter by one unit”, that implementation violates the contract.

We need to distinguish:

| Contract layer | Example | Does the Java compiler guarantee it automatically? |
| --- | --- | --- |
| Type/signature contract | Has `increase()`, `value()` returns `int`, valid method override | Yes, within the scope of language rules |
| Precondition | Input parameter must be positive, string must not be `null` | Not inferred automatically from a standard signature |
| Postcondition | After `increase()`, the new value equals the old value plus one | No |
| Invariant | The counter is always non-negative | No |
| Call ordering / relationship between calls | Queue returns elements in FIFO order | No |
| Side effects and errors | A failed call does not mutate state; throws the documented exception | Not completely |
| Promised operational characteristics | Thread safety, atomicity, ordering stability, or consistency | Not guaranteed automatically merely by `implements` |

In an interface, method names, parameter types, and return types form the **surface** of the contract. The meaning of operations, data bounds, effects on state, possible errors, and what is *not* permitted determine whether an implementation can be used correctly.

`@Override` helps detect mismatches in an overridden method, but it does not prove that the method performs the right functionality.

## 2. Behavioral Contracts Are What Callers Can Observe

A good behavioral contract answers specific questions:

- **Valid inputs:** Does it accept `null`, empty strings, negative numbers, or out-of-range values?
- **Results:** What does the return value mean? Is it allowed to return `null` or a special value?
- **State before and after:** Which data does the method add, remove, replace, or leave unchanged?
- **Ordering:** Across consecutive operations, does the result depend on the order of calls?
- **Errors:** What happens on invalid input? Which exception is thrown? Does the state remain intact?
- **Repeatability:** Does calling it again cause additional side effects? If it is idempotent, within what scope is that guaranteed?
- **Concurrency:** If multiple threads call it concurrently, does the API promise thread safety or atomicity? If not promised, it must not be assumed.

Example contract for a work queue:

> `offer(task)` appends a valid task to the end of the queue. `poll()` retrieves and removes the task that has been present the longest without yet being taken (FIFO). When empty, `poll()` returns `Optional.empty()`. `offer(null)` throws `NullPointerException` and does not modify the contents. This contract does not promise thread safety.

The statements above can be verified through behavior observed via the API, rather than depending on details such as using `ArrayDeque`, an array, a linked list, or a database.

**Clarity of the promise matters:** if FIFO has not been specified, the author of a LIFO implementation might interpret it differently and still feel they are right. Therefore, behavioral contracts should be documented directly on the interface or in the relevant API documentation.

## 3. Runnable Example: Same Interface, One Semantically Wrong Implementation

Save all of the following code in a single file `ContractDemo.java`.

```java
import java.util.ArrayDeque;
import java.util.Objects;
import java.util.Optional;

public class ContractDemo {
    /** FIFO; null is invalid; empty poll() returns Optional.empty(). */
    interface WorkQueue {
        void offer(String task);
        Optional<String> poll();
    }

    static final class FifoQueue implements WorkQueue {
        private final ArrayDeque<String> tasks = new ArrayDeque<>();

        @Override
        public void offer(String task) {
            tasks.addLast(Objects.requireNonNull(task, "task"));
        }

        @Override
        public Optional<String> poll() {
            return Optional.ofNullable(tasks.pollFirst());
        }
    }

    // Type-valid but violates the FIFO requirement.
    static final class LifoQueue implements WorkQueue {
        private final ArrayDeque<String> tasks = new ArrayDeque<>();

        @Override
        public void offer(String task) {
            tasks.addLast(Objects.requireNonNull(task, "task"));
        }

        @Override
        public Optional<String> poll() {
            return Optional.ofNullable(tasks.pollLast());
        }
    }

    static void check(String name, WorkQueue queue) {
        queue.offer("A");
        queue.offer("B");
        String first = queue.poll().orElseThrow();
        String second = queue.poll().orElseThrow();
        boolean fifo = first.equals("A") && second.equals("B");
        boolean empty = queue.poll().isEmpty();
        boolean nullRejected = false;
        try {
            queue.offer(null);
        } catch (NullPointerException expected) {
            nullRejected = true;
        }
        System.out.printf("%s: fifo=%s, empty=%s, nullRejected=%s%n",
                name, fifo, empty, nullRejected);
    }

    public static void main(String[] args) {
        check("FifoQueue", new FifoQueue());
        check("LifoQueue", new LifoQueue());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 --release 17 ContractDemo.java
java ContractDemo
```

Verified stdout output:

```text
FifoQueue: fifo=true, empty=true, nullRejected=true
LifoQueue: fifo=false, empty=true, nullRejected=true
```

### Reading the Results Against the Contract

1. **Both classes compile.** Each class implements both `offer` and `poll`, uses the correct return types, and has valid override visibility.
2. **`FifoQueue` implements FIFO.** It inserts at the tail with `addLast()` and removes from the head with `pollFirst()`, so the two calls return `"A"` and then `"B"`.
3. **`LifoQueue` violates FIFO.** `pollLast()` returns `"B"` before `"A"`. This is a **semantic** error, not a signature error. Therefore `fifo=false` even though the program runs.
4. **Both return empty once all elements have been removed.** Both elements are removed before the `poll()` call that checks for emptiness, so `empty=true`.
5. **Both reject `null`.** `Objects.requireNonNull` throws `NullPointerException` before adding, matching the documented behavior; `nullRejected=true`.

The `check` example is an illustrative check, **not a complete test suite**. It does not cover many elements, varied operation sequences, recovery after errors, or concurrent handling. Its goal is to show the difference between “compiling successfully” and “fulfilling the contract”.

You can fix `LifoQueue.poll()` to `tasks.pollFirst()` so it complies with FIFO. In a real application, however, fix the root cause in the design and check all paths through the API.

## 4. A Common Reference Type Does Not Automatically Guarantee Substitutability

Calling code typically sees only the interface:

```java
WorkQueue queue = obtainQueue();
queue.offer("A");
queue.offer("B");
String next = queue.poll().orElseThrow();
```

This is an illustrative snippet placed within a context that provides an appropriate `WorkQueue` and `obtainQueue()`; it is not a standalone program by itself. If every `WorkQueue` implementation respects FIFO, `next` must be `"A"`. The caller can replace `FifoQueue` with another implementation without changing business assumptions.

The Liskov Substitution Principle (LSP) expresses that expectation: wherever an object matching the contract of a supertype/interface is required, an object of a subtype/implementation must be usable **without breaking the promised contract properties**.

For each method, the practical formulation is:

- **Do not strengthen preconditions** compared to the published contract. If `offer` promises to accept any non-null string, an implementation must not arbitrarily accept at most 10 characters unless permitted by the contract.
- **Do not weaken postconditions.** If `poll` promises FIFO, an implementation must not switch to LIFO or return an arbitrary element.
- **Preserve state invariants.** If the contract requires not losing untaken elements, an error must not silently clear the queue.
- **Honor commitments regarding exceptions and side effects.** If the API promises not to modify state on failure, an implementation must not mutate data and then report an error.

The criteria above apply equally to `extends` in abstract classes and method overriding in classes, not only to interfaces. They are design and behavioral criteria; the Java compiler has no general-purpose reasoning engine to prove them.

## 5. Clearly Separating Preconditions, Postconditions, and Invariants

### Preconditions: What Must the Caller Provide?

Suppose `reserve(String sku, int quantity)` only accepts a non-empty `sku` and `quantity > 0`. The documentation should explicitly state how invalid input is rejected, such as `IllegalArgumentException`, rather than leaving each class to interpret it on its own.

You should not silently introduce a new condition in an implementation, for example capping `quantity <= 5` when the interface publishes no such limit. Users swapping implementations will encounter failures even though they complied with the interface's preconditions.

### Postconditions: What Must Be True After the Call?

If the `reserve` contract states “returns `true` when reservation succeeds and reduces stock by exactly `quantity`; returns `false` when stock is insufficient and leaves stock unchanged”, an implementation that always returns `true` without reducing stock is wrong. It may still be valid with respect to the `boolean` return type.

### Invariants: Which Properties Must Always Hold?

For inventory data, `stock >= 0` can be an invariant. When managing state across multiple operations, the invariant must continue to hold after every public operation, including specified exception paths.

Do not turn every internal structural detail into an API invariant. For example, using `ArrayDeque` is only an implementation detail; FIFO ordering is the property that callers must be able to observe.

## 6. Exceptions, `null`, and Failures Are Also Part of the Contract

A contract should specify what can happen on **error paths**, not only on the success path.

For example, with `WorkQueue`:

| Scenario | Required behavior |
| --- | --- |
| `offer("A")` on a usable queue | Stores element `"A"` at the end of the FIFO order |
| `poll()` when the queue has elements | Returns the oldest untaken element and removes it at the same time |
| `poll()` when the queue is empty | Returns `Optional.empty()`; does not return `null` |
| `offer(null)` | Throws `NullPointerException`, does not add an element |
| Multiple threads accessing concurrently | Not guaranteed; needs additional agreement if the application requires it |

This prevents implementations that return `null` instead of `Optional.empty()`, or silently ignore `offer(null)`. Those alternatives can still be expressed in Java, but **they differ from the rules users rely on**.

If an API declares a specific exception, you should verify both the exception type and any state changes. Java's `throws` clause expresses certain checked-exception constraints; it does not automatically describe unchecked exceptions, error messages, or the atomicity of the operation.

When state can be mutated, clearly state whether failure means “no changes made”, “partial success”, or “may have already committed”. This is a major distinction for network operations, file writes, and database transactions.

## 7. Documenting the Contract Where the Interface Is Declared

Write documentation before multiple implementations exist. Javadoc delivers the rules to both implementers and callers.

The following example is an **independent illustrative declaration**, not combined with the `WorkQueue` declaration in `ContractDemo.java`:

```java
import java.util.Optional;

/**
 * FIFO task queue.
 *
 * <p>Thread safety is not guaranteed. All implementations must preserve the
 * insertion order of elements that have not yet been taken.</p>
 */
interface WorkQueue {
    /**
     * Appends a task to the end of the queue.
     *
     * @param task non-null task
     * @throws NullPointerException if task is null;
     *                              in this case the queue remains unchanged
     */
    void offer(String task);

    /**
     * Retrieves and removes the earliest added element still remaining.
     *
     * @return the retrieved element, or Optional.empty() if empty
     */
    Optional<String> poll();
}
```

For an interface that needs to be exposed to other packages, use `public` on the top-level interface (and place it in the corresponding Java file). A type's access level is separate from its behavioral semantics.

Write Javadoc as specifically as possible: ordering, nullability, postconditions, error boundaries, concurrency, and return values. Avoid vague phrases like “handles appropriately”, “returns the right result”, or “usually returns the next element”. If behavior is conditional, state those conditions.

**Documentation is the source of commitments, not an automated verification mechanism.** You need tests derived directly from the published rules themselves.

## 8. Designing Shared Contract Tests for Every Implementation

An effective approach is to write **contract tests**: a single test suite executed against every implementation of the interface, including new versions added later.

For `WorkQueue`, the test suite should observe:

1. Newly created queue is empty: `poll()` returns `Optional.empty()`.
2. Adding one element: `offer("A")` then `poll()` returns `"A"`, and the next call is empty.
3. Adding multiple elements: insert `A, B, C` sequentially and retrieve exactly `A, B, C`.
4. Inserting after removal: `offer(A), offer(B), poll(), offer(C)` must continue returning `B, C`.
5. Adding `null`: throws `NullPointerException`; existing elements remain intact in unchanged order.
6. Other scenarios in the documentation: repeatability, capacity limits, resource failures, or concurrency (if promised).

You can use JUnit 5 with parameterized tests or a test helper accepting a `Supplier<WorkQueue>` to create a fresh queue for each test case. The `Supplier` here must create a new instance; reusing a queue mutated by a previous test alters state and makes tests unreliable.

Pseudo-flow for a contract test:

```text
List of accepted implementations
    -> create a new instance for each test
    -> execute the same sequence of public operations
    -> compare outputs, observed state, and exceptions
    -> report a failure when any implementation breaks a promise
```

The `check` method in the runnable example applies this exact idea on a small scale. In a real system, tests should **fail explicitly** when expectations are not met (for example, using JUnit assertions), rather than merely printing `false`.

Behavioral verification can also use property-based testing: generate many valid `offer/poll` sequences and compare the results against a FIFO reference model. Even so, no finite test suite can absolutely prove that every implementation is always correct across all inputs and concurrent execution schedules.

## 9. Default Methods and Abstract Classes Do Not Waive the Contract

### `default` in Interfaces

A `default method` with a body enables logic reuse, but the default logic must also satisfy the published meaning. An implementation overriding a `default` method is allowed to change the algorithm, **but must not arbitrarily change the API promise**.

For example, if an interface declares `isEmpty()` to be true when no elements remain, an implementation overriding it to return `true` unconditionally may compile yet violate the contract, unless special contexts are explicitly specified.

### Abstract Classes

An abstract class can provide shared state and logic. Inheriting ready-made methods reduces the amount of code to write, but does not automatically guarantee that subclasses preserve preconditions, postconditions, and invariants when overriding methods or adding paths that mutate state.

Do not equate “inheriting code”, “implementing an interface”, and “having correct behavior”. A class can reuse entirely wrong code or override a small part in a way that breaks the overall rules.

### Composition

If multiple implementations must uphold shared rules, you can consolidate algorithms or validation steps into collaborator objects, internal utility functions, or appropriate template methods. Reusing common logic helps reduce behavioral drift, though testing at the interface boundary is still required.

## 10. Common Design Pitfalls

**Pitfall 1 — Matching signature, different meaning.** Defining `sort()` where the implementation only reverses the list; the program may run, yet callers assume the result is sorted in ascending order.

**Pitfall 2 — Adding restrictions absent from the contract.** The interface accepts any quantity within the valid `int` range, while the implementation silently caps it at 100. This strengthens preconditions, causing calls that are valid under the interface to fail.

**Pitfall 3 — Weakened postconditions.** The interface promises that a successful `save` means data has been durably persisted, while the implementation only pushes it into a volatile buffer and still returns success. If the system only guarantees “queued for writing”, it must state that exact level of guarantee.

**Pitfall 4 — Wrong behavior on edge cases.** `poll()` works properly when elements are present, but returns `null` instead of `Optional.empty()` when empty; the application breaks on a rarely executed branch.

**Pitfall 5 — Exceptions corrupting state.** Deleting part of the data first and then throwing an error, when the contract committed that a failed operation must leave state unchanged.

**Pitfall 6 — Using `instanceof` to compensate for non-conforming implementations.** If clients constantly check “if class A then FIFO, if class B then LIFO”, the interface no longer provides a reliably substitutable contract. You should only branch on explicitly modeled capabilities rather than hiding deviations.

**Pitfall 7 — Promising thread safety by guesswork.** Working functionally in a single thread does not mean working across multiple threads. If an API must be thread-safe, you need to clearly define concurrency conditions, state visibility, and appropriate tests.

**Pitfall 8 — Changing documentation without updating tests.** When publishing a new contract or revising an existing one, review the related implementations and test suites. You should not edit Javadoc merely to legitimize a bug that has already appeared.

## 11. Practical Workflow When Implementing an Interface

1. **Read operation names and Javadoc** to identify what clients have the right to rely on, especially boundary states.
2. **Write down the list of preconditions, postconditions, and invariants upfront.** For operations that can fail, clearly specify the post-failure state.
3. **Choose algorithms/data structures** that satisfy those conditions. For instance, FIFO with `ArrayDeque` should add at the tail and remove from the head.
4. **Use `@Override` and check compilation** to ensure structural conformance; then test semantics separately.
5. **Run contract tests across all implementations**, including fake implementations for testing and performance-optimized classes.
6. **Test error paths and interactions across multiple calls**, not just a single “happy path”.
7. **Evaluate implementation substitutability**: can clients still work properly without knowing the concrete implementation class?

For practice, try creating an additional `PriorityQueueWork` that implements `WorkQueue` and orders tasks by priority. Ask: if `WorkQueue` currently guarantees FIFO, is this a valid implementation? **No**, if reordering violates FIFO. To support a priority queue, you must define a different contract or intentionally revise the design and update all dependent clients and tests.

## Key Takeaways

`implements` and successful compilation prove that a class is compatible with the interface's **type** at the language level; they do not prove that the class obeys its **business semantics**. A contract is valuable when callers can trust its observable promises — valid inputs, results, ordering, state, errors, and published operational properties — regardless of which implementation provides the object. Writing those commitments clearly and verifying them with a shared suite of contract tests is the foundation that enables interfaces to truly allow safe implementation substitution.
