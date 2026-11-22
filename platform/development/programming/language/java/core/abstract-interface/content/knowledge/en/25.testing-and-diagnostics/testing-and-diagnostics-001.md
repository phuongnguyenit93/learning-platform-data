# Testing the Same Contract Across Multiple Implementations

When an interface has multiple implementation classes, each class may use a different data structure or algorithm while still having to comply with the same public behavior. A **contract test** is a test suite that describes the required behavior of an abstraction and runs that test suite against each implementation. This approach helps detect an implementation class that violates the contract without having to rewrite the same set of tests for each class.

For example, an interface for storing key-value pairs can be implemented using `HashMap` or `TreeMap`. Both implementations must produce the same results when adding, reading, overwriting, and removing data, even though their internal structures differ.

## 1. What Is a Contract?

A contract is the set of rules that callers are allowed to rely on when using an interface. A contract typically defines:

- **Preconditions:** which input data is accepted or rejected.
- **Postconditions:** what must be true after an operation completes.
- **Invariants:** what is always true about an object's state.
- **Edge-case behavior:** the result when a key does not exist, a collection is empty, input is invalid, or an operation is repeated.
- **Specified errors:** the types of errors that a caller can expect for invalid input.

A Java interface that only declares method signatures does not necessarily express the full contract. Javadoc, API conventions, and tests need to clarify points such as the return value when data is not found, the `null` policy, the meaning of `false` on removal, or whether calling an operation again creates additional elements.

A contract test verifies **externally observable behavior**. It should not depend on field names, the internal collection type, iteration order if the contract does not guarantee ordering, or how the algorithm is implemented.

## 2. Example of a Shared Contract

Suppose an application needs a simple store:

| Operation | Contract rule |
| --- | --- |
| Creating a new store | `size()` is `0`. |
| `put(key, value)` | Both key and value must be non-`null`; stores the value for the key. |
| Overwriting an existing key | The new value replaces the old value; the number of keys does not increase. |
| `get(key)` | Returns an `Optional` containing the value if the key exists; otherwise `Optional.empty()`. |
| `remove(key)` with an existing key | Returns `true` and removes the key. |
| `remove(key)` with a non-existent key | Returns `false`, and the store state remains unchanged. |
| Passing `null` as the key or value | Throws `NullPointerException` according to the chosen policy. |

In this example, the contract intentionally leaves the order of keys unspecified. Therefore, an implementation using `TreeMap` is not considered more correct than one using `HashMap` just because it sorts the keys. If the application requires ordering, include the ordering requirement explicitly in the contract and test it.

## 3. Complete Java 17+ Program

The example below runs without any external testing libraries. The `runContract` method contains a single suite of checks. The program runs that suite against two independent implementations: `HashMapStore` and `TreeMapStore`.

Save the entire code to a file named `ContractTestDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.TreeMap;
import java.util.function.Supplier;

public class ContractTestDemo {
    public static void main(String[] args) {
        runContract("HashMapStore", HashMapStore::new);
        runContract("TreeMapStore", TreeMapStore::new);
        System.out.println("All contract checks passed.");
    }

    private static void runContract(
            String name, Supplier<KeyValueStore> factory) {
        // Each implementation starts with a new object.
        KeyValueStore store = factory.get();

        require(store.size() == 0, "new store must be empty");
        require(store.get("missing").isEmpty(),
                "missing key must return Optional.empty");

        store.put("alpha", "one");
        require(store.get("alpha").equals(Optional.of("one")),
                "get must return the stored value");
        require(store.size() == 1,
                "put must add one key");

        store.put("alpha", "two");
        require(store.get("alpha").equals(Optional.of("two")),
                "put must replace the existing value");
        require(store.size() == 1,
                "overwriting a key must not increase size");

        store.put("beta", "value");
        require(store.size() == 2,
                "a different key must add one entry");

        require(store.remove("alpha"),
                "removing an existing key must return true");
        require(store.get("alpha").isEmpty(),
                "removed key must no longer be present");
        require(store.size() == 1,
                "removing a key must decrease size");

        require(!store.remove("missing"),
                "removing a missing key must return false");
        require(store.size() == 1,
                "removing a missing key must not change size");

        expectNullPointer(
                () -> store.put(null, "value"),
                "null key must be rejected");
        expectNullPointer(
                () -> store.put("key", null),
                "null value must be rejected");
        expectNullPointer(
                () -> store.get(null),
                "null lookup key must be rejected");
        expectNullPointer(
                () -> store.remove(null),
                "null removal key must be rejected");

        System.out.println("PASS " + name);
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void expectNullPointer(
            Runnable action, String message) {
        try {
            action.run();
        } catch (NullPointerException expected) {
            return;
        }
        throw new AssertionError(message);
    }

    interface KeyValueStore {
        void put(String key, String value);
        Optional<String> get(String key);
        boolean remove(String key);
        int size();
    }

    static final class HashMapStore implements KeyValueStore {
        private final Map<String, String> data = new HashMap<>();

        @Override
        public void put(String key, String value) {
            Objects.requireNonNull(key, "key");
            Objects.requireNonNull(value, "value");
            data.put(key, value);
        }

        @Override
        public Optional<String> get(String key) {
            Objects.requireNonNull(key, "key");
            return Optional.ofNullable(data.get(key));
        }

        @Override
        public boolean remove(String key) {
            Objects.requireNonNull(key, "key");
            return data.remove(key) != null;
        }

        @Override
        public int size() {
            return data.size();
        }
    }

    static final class TreeMapStore implements KeyValueStore {
        private final Map<String, String> data = new TreeMap<>();

        @Override
        public void put(String key, String value) {
            Objects.requireNonNull(key, "key");
            Objects.requireNonNull(value, "value");
            data.put(key, value);
        }

        @Override
        public Optional<String> get(String key) {
            Objects.requireNonNull(key, "key");
            return Optional.ofNullable(data.get(key));
        }

        @Override
        public boolean remove(String key) {
            Objects.requireNonNull(key, "key");
            return data.remove(key) != null;
        }

        @Override
        public int size() {
            return data.size();
        }
    }
}
```

Compile and run with JDK 17 or later:

```text
javac --release 17 ContractTestDemo.java
java ContractTestDemo
```

Standard output of the program:

```text
PASS HashMapStore
PASS TreeMapStore
All contract checks passed.
```

If an implementation violates a rule, `require` or `expectNullPointer` throws `AssertionError`; the program does not print the `PASS` line for that implementation and exits with an error. Therefore, the `PASS` line appears only after all checks for that implementation have completed.

## 4. Why Is the Same Test Suite Valuable?

`runContract` does not check whether the class uses `HashMap` or `TreeMap`. It only calls the public methods of `KeyValueStore` and verifies the results against the contract.

This provides three benefits:

1. **Consistency:** every implementation must satisfy the same set of behaviors.
2. **Extensibility:** when adding a third implementation, you only need to provide a factory and rerun the contract tests.
3. **Centralized maintenance:** when the contract changes intentionally, you update one shared test suite and rerun it against all implementations.

However, contract tests do not replace all other tests. Each implementation may still need its own tests for algorithms, performance, capacity limits, thread synchronization, or additional characteristics not in the interface.

## 5. Organizing Contract Tests with JUnit 5

In real-world projects, JUnit 5 helps make each rule an independent test. A common pattern is to place the shared tests in an abstract class and let concrete test classes provide the implementation via a factory method.

The following example assumes the interface and the two implementations are separated into production classes in the same package. The abstract test class can reside in `src/test/java`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

abstract class KeyValueStoreContractTest {
    protected abstract KeyValueStore newStore();

    @Test
    void newStoreIsEmpty() {
        assertEquals(0, newStore().size());
    }

    @Test
    void missingKeyReturnsEmpty() {
        assertTrue(newStore().get("missing").isEmpty());
    }

    @Test
    void storedValueCanBeRead() {
        KeyValueStore store = newStore();
        store.put("alpha", "one");

        assertEquals("one", store.get("alpha").orElseThrow());
    }

    @Test
    void puttingExistingKeyReplacesValue() {
        KeyValueStore store = newStore();
        store.put("alpha", "one");
        store.put("alpha", "two");

        assertEquals("two", store.get("alpha").orElseThrow());
        assertEquals(1, store.size());
    }

    @Test
    void removingExistingKeyReturnsTrue() {
        KeyValueStore store = newStore();
        store.put("alpha", "one");

        assertTrue(store.remove("alpha"));
        assertTrue(store.get("alpha").isEmpty());
    }

    @Test
    void removingMissingKeyReturnsFalse() {
        KeyValueStore store = newStore();

        assertFalse(store.remove("missing"));
        assertEquals(0, store.size());
    }

    @Test
    void nullKeyIsRejected() {
        assertThrows(
                NullPointerException.class,
                () -> newStore().get(null));
    }

    @Test
    void nullValueIsRejected() {
        assertThrows(
                NullPointerException.class,
                () -> newStore().put("alpha", null));
    }
}
```

Next, create a concrete test class for each implementation:

```java
import org.junit.jupiter.api.Test;

class HashMapKeyValueStoreTest extends KeyValueStoreContractTest {
    @Override
    protected KeyValueStore newStore() {
        return new HashMapKeyValueStore();
    }
}

class TreeKeyValueStoreTest extends KeyValueStoreContractTest {
    @Override
    protected KeyValueStore newStore() {
        return new TreeKeyValueStore();
    }
}
```

This is an illustrative structure; in a project, each top-level test class is typically placed in its own correspondingly named file. `HashMapKeyValueStore` and `TreeKeyValueStore` are example names for the two production implementations.

JUnit Jupiter discovers the `@Test` methods inherited from the abstract superclass when running a concrete subclass. Therefore, both test classes execute the same rules without duplicating the test bodies. The `newStore()` factory creates a new object for each test, preventing state from a previous test from affecting subsequent ones.

With Maven, you need to declare JUnit Jupiter in the `test` scope and use a Maven Surefire version that supports JUnit Platform. You can then run:

```text
mvn test
```

The JUnit test suite above illustrates the core rules. Add tests for any remaining contract guarantees, such as `size()` after each operation and the behavior when removing a key that has just been overwritten.

## 6. Distinguishing Contract Tests from Implementation-Specific Tests

Use contract tests for what every implementation is required to do the same way. Use dedicated tests for properties advertised specifically by a single implementation.

| Test type | Example | Where to place it |
| --- | --- | --- |
| Shared contract | Writing then reading returns the same value. | Shared contract test suite. |
| Shared contract | A missing key returns `Optional.empty()`. | Shared contract test suite. |
| Shared contract | Overwriting does not create an extra key. | Shared contract test suite. |
| Implementation-specific property | `TreeMap` returns keys in sorted order. | Dedicated test for the implementation, if this behavior is provided. |
| Implementation-specific property | A cache must evict entries according to an LRU policy. | Dedicated test for the cache. |
| Implementation-specific property | An implementation has a capacity limit or retry policy. | Dedicated test for that feature. |
| Integration | Database connections, transactions, or serialization work properly. | Integration test suited to the real infrastructure. |

Do not add a key-sorting requirement to the contract just because the current implementation uses `TreeMap`. Doing so forces all implementations to adhere to a property that may not be necessary. Conversely, if callers are permitted to rely on ordering, ordering must be stated explicitly in the contract and every implementation must satisfy it.

## 7. Common Design and Testing Mistakes

**Duplicating tests per class.** When tests are copied, an implementation can easily be missed when the contract changes. Put shared rules in a single contract suite and use a factory to supply the implementations.

**Testing internal details.** A test that requires an implementation to have a field named `map`, or to specifically use `HashMap`, will fail when there is an equivalent yet valid implementation. Verify results through the interface.

**Introducing assumptions not in the contract into tests.** For example, comparing key order when the API does not guarantee ordering produces brittle tests. Test only the promised behaviors.

**Failing to create fresh state for each test.** If multiple tests share an instance, execution order can affect the results. Each test should create its own object or use a fixture with an explicit state-reset mechanism.

**Testing only the happy path.** Common bugs occur with missing keys, `null` data, repeated operations, and empty state. Include edge cases in the contract when they affect the caller.

**Using an overly broad test suite for different APIs.** If two implementations have intentionally different behavior, do not force them into the same mismatched contract. Split the abstraction or divide the contract into feature groups that each implementation commits to supporting.

**Using mocks instead of real implementations in contract tests.** The goal of a contract test is to confirm that an implementation actually adheres to the contract. Mocks can be useful for testing callers, but they do not prove that a real implementation class satisfies the rules.

**Assuming passing tests prove all behavior is correct.** Contract tests only cover the rules and scenarios that have been written. They do not by themselves prove formal correctness, thread safety, performance, or every possible input.

## 8. How to Investigate When a Contract Test Fails

1. Identify which implementation failed and which contract rule was violated.
2. Check whether the test relies on specified behavior or assumes an implementation detail.
3. If the test accurately expresses the contract, fix the implementation or clearly identify its bug.
4. If the contract is ambiguous, decide on the API behavior to guarantee, then update the documentation and tests consistently.
5. Rerun the contract suite across all implementations, not just the class you fixed.
6. Run additional implementation-specific tests or integration tests for risks that the shared contract does not cover.

Do not delete an assertion just to make the test suite green. First determine whether that assertion represents a real API commitment.

## 9. Checklist When Adding a New Implementation

- Read the interface contract and clearly identify preconditions, return values, errors, and edge cases.
- Confirm that the new implementation genuinely fulfills the same abstraction; do not skip rules just because the class compiles.
- Run the entire contract suite against the new implementation.
- Ensure each test has an independent initial state and does not depend on execution order.
- Keep checks for internal structure, performance, and implementation-specific features in the appropriate tests for that implementation.
- When adding or changing a public rule, update the contract and rerun the suite for every implementation.
- When an implementation cannot satisfy the contract, reconsider the abstraction or create a separate interface for the differing capability instead of silently changing the meaning of a method.

Contract tests turn an interface into a verifiable commitment. When the same test suite runs across every implementation, the development team can change internal structures with greater confidence while preserving the behavior promised to callers.
