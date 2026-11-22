# What Is an Object Contract and Why Should Calling Code Rely on It?

## 1. Understanding Object Contracts Correctly

In object-oriented programming, a **contract** is the set of commitments about an object's **externally observable behavior**: what users are allowed to call, what conditions must be met, and what can be relied upon after calling. A contract can be described through public interfaces, API documentation, business specifications, tests, and Java's general rules.

For example, a queue object promises that the element added first will be retrieved first (FIFO). Calling code can rely on that order without needing to know whether the object stores data internally in an array, a linked list, or another structure.

**A method signature is not the entire contract.** Two classes that both have `String dequeue()` will both compile; however, if one class removes the oldest element and the other removes the newest element, they do not implement the same contract. The compiler helps check data types and accessibility, while many behavioral rules must be defined and verified separately.

It is also important to distinguish: an "object contract" in the broad sense refers to the behavioral commitments of any object; it is not only about the `java.lang.Object` class or `equals()`/`hashCode()` alone.

## 2. What Does a Contract Typically Contain?

| Component | What needs to be defined | Queue example |
| --- | --- | --- |
| Public operations | What does the object allow to be done? | `enqueue`, `dequeue`, `size` |
| Precondition | What must calling code guarantee before calling? | An added task must not be `null` or a blank string |
| Postcondition | If the operation succeeds, what must the result or state be? | `dequeue` returns the oldest task and reduces the size by 1 |
| Invariant | What is always true in a valid state of the object? | `size() >= 0`; pending tasks follow FIFO |
| Error case handling | What happens when input is invalid or data is missing? | Dequeuing from an empty queue throws `NoSuchElementException` |
| Other guaranteed properties | Mutability, ordering, consistency, threading, etc. | Only considered thread-safe if the contract explicitly promises it |

Not every API needs to record every item in a formal format. Even so, **anything that affects proper usage must be clear enough that callers do not have to guess**.

Three important responsibility boundaries:

- **The caller** complies with the published preconditions: for example, not passing an empty task.
- **The implementing object** guarantees the promised postconditions, invariants, and error reporting when used validly.
- **The contract documentation** must clearly state special cases: `null` values, empty collections, failed operations, data limits, or concurrent usage capability.

If the contract does not promise something, callers should not infer that commitment merely because the current version happens to behave that way.

## 3. Why Must Calling Code Rely on the Contract?

**Decoupling usage needs from implementation details.** Calling code only needs to know that `dequeue()` returns the oldest task. When changing the storage structure, calling code does not need to be modified as long as this commitment remains intact. This is the foundation of encapsulation and abstraction-based design.

**Enabling implementation substitution.** Another object can be used as a replacement if it satisfies the same requirements that the caller relies on. This substitutability is the central idea of the Liskov Substitution Principle: matching method signatures alone is not enough; results, calling conditions, and error behavior must also be compatible.

**Reducing fragile dependencies.** If calling code reads internal fields directly, assumes a class always uses `ArrayDeque`, or relies on an unpromised ordering, an internal optimization can break program correctness even though the public API has not changed.

**Helping pinpoint bugs and write tests.** When the specification states "retrieves in FIFO order", we can test FIFO across every implementation. If the result differs, the bug lies with the side that violated the contract; there is no need to guess based on internal details.

**Making APIs easier to learn and maintain.** New users clearly know valid inputs, expected results, and exceptions to handle. The development team knows which behaviors must be preserved when refactoring.

## 4. Java 17+ Example: Caller Only Knows the Queue Contract

Suppose a system processes tasks in the order they are submitted. We publish the `TaskQueue` contract:

1. `enqueue(task)` only accepts non-`null` and non-blank strings; a successful call appends the task to the end of the queue.
2. `dequeue()` retrieves and removes the oldest task; if empty, it throws `NoSuchElementException` and does not change state.
3. `size()` indicates the number of pending tasks; this number is non-negative.
4. The example does not promise safety when multiple threads access it concurrently.

Create the file `ContractDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.NoSuchElementException;

public final class ContractDemo {
    interface TaskQueue {
        void enqueue(String task);
        String dequeue();
        int size();
    }

    static final class InMemoryTaskQueue implements TaskQueue {
        private final Deque<String> tasks = new ArrayDeque<>();

        @Override
        public void enqueue(String task) {
            if (task == null || task.isBlank()) {
                throw new IllegalArgumentException("task must not be blank");
            }
            tasks.addLast(task);
        }

        @Override
        public String dequeue() {
            return tasks.removeFirst();
        }

        @Override
        public int size() {
            return tasks.size();
        }
    }

    static void process(TaskQueue queue) {
        queue.enqueue("build");
        queue.enqueue("test");
        System.out.println(queue.dequeue());
        System.out.println(queue.dequeue());
        System.out.println(queue.size());
        try {
            queue.dequeue();
        } catch (NoSuchElementException ex) {
            System.out.println("empty");
        }
    }

    public static void main(String[] args) {
        process(new InMemoryTaskQueue());
    }
}
```

Compile and run:

```bash
javac ContractDemo.java
java ContractDemo
```

Standard output:

```text
build
test
0
empty
```

**Explanation of the commitments being fulfilled:**

- `process` accepts the `TaskQueue` type and only calls the published operations. In the example, it receives a new, initially empty queue.
- `addLast` and `removeFirst` implement FIFO; calling code does not need to know about `Deque`.
- Input validation happens before adding; `enqueue(null)` or `enqueue("   ")` throws `IllegalArgumentException` and does not add a task.
- `ArrayDeque`'s `removeFirst()` throws `NoSuchElementException` when empty without removing anything; `process` can handle this case according to the contract.
- `size()` reads the exact number of current elements. If `ArrayDeque` is replaced by another structure, the new implementation must still preserve FIFO, input conditions, exceptions, and the meaning of `size`.

External code will encounter logic bugs if a new implementation silently switches to LIFO, even if the method names and return types remain unchanged. This is precisely why calling code depends on **committed behavior**, not just the interface.

## 5. Familiar Contracts Right Inside Java

Java has many examples showing that a contract goes beyond method signatures:

- **`Object.equals(Object)`:** when used to define equality, the method must obey reflexivity, symmetry, transitivity, consistency (when relevant information does not change), and `x.equals(null)` must be `false` for non-`null` `x`.
- **`Object.hashCode()`:** two objects equal according to `equals` must have the same hash code; two objects with the same hash code are not necessarily equal. Therefore, `HashMap`/`HashSet` can rely on both contracts.
- **`Comparable.compareTo`:** callers use negative, 0, and positive signs to infer order; implementations must ensure the published consistent comparison rules. Sorting can produce wrong results or throw exceptions if a comparator violates the contract.
- **`List.get(index)`:** callers rely on the index, ordering, and out-of-bounds exceptions, not on whether the list stores elements in an array or linked nodes.

These contracts still have boundaries that must be read in the specific API documentation. For example, `toString()` does **not** by default guarantee a string with a stable format for other machines to parse; if a data exchange format is needed, use an explicit format specification.

## 6. How to Read and Design Contracts in Practice

1. **State observable behavior.** For each method, ask: what are the valid inputs, what does the result mean, and what state is allowed to change?
2. **Clarify boundary cases.** Specify `null`, empty values, negative numbers, non-existent elements, integer overflow, and errors; do not leave callers to guess.
3. **Document the contract where API users can see it.** In Java, use clear type and method names, JavaDoc (`@param`, `@return`, `@throws`), interfaces, and invariant documentation. Null-checking or validation annotations can assist, but do not express every behavioral rule on their own.
4. **Write contract tests.** For example: adding A then B must retrieve A then B; removing from an empty queue must throw the stated exception; invalid input must not change the size. Run the same test suite against every implementation.
5. **Check substitutability.** When creating a subclass or a new implementation, do not arbitrarily require stronger preconditions, return weaker results, or change error rules that callers depend on.
6. **Distinguish guarantees from implementation details.** FIFO is a contract in the example; using `ArrayDeque`, memory capacity, private field order, or internal log lines are not commitments to calling code.

A good API must also clearly state thread-safety guarantees, whether input data is stored or copied, resource ownership, and state-mutation policies **when those factors affect users**. Do not assume an object is immutable or thread-safe just because it has a small interface.

## 7. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| "Having the same interface means they are substitutable." | The behavioral rules that callers have a right to expect must also be preserved. |
| "Running a test once and seeing it work means that is the contract." | A single observed result does not prove a long-term guarantee; rely on the specification and tests. |
| "Even if a precondition is violated, the object must still succeed." | The caller is responsible for preconditions; behavior upon violation must be checked in the specific specification. |
| "Having `equals()` means you have the entire object contract." | `equals`/`hashCode` are just specific contracts among many behavioral contracts. |
| "As long as the right data is returned, any exception is fine." | The error type, when it is thrown, and whether state is mutated can also be an important part of the contract. |

**Self-check:** If you replace the queue implementation and `dequeue()` retrieves the last element first, does the Java code still compile? Possibly yes. Is the calling code still correct? No, because the new implementation violated the FIFO commitment. If you change the storage structure while all public commitments remain valid, does calling code need to know about the change? No.

**Takeaway:** A contract is the trust boundary between an object and the code using it. Encapsulation hides how things are done; the contract tells you what must remain true regardless of how the implementation changes.
