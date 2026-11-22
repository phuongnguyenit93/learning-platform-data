# State-Sharing Limitations and Contracts of Default Methods

Default methods share **how a behavior is performed**, do not create separate state for each object, and do not automatically guarantee that every implementing class follows the same business rules. State, invariants, and synchronization must still belong to the owner of the data.

## 1. Shared behavior is not shared state

```java
interface Greeter {
    String name();

    default String greet() {
        return "Xin chào, " + name();
    }
}
```

`greet()` relies only on the `name()` contract. The name may come from a class field, a database, a component object, or a computed value. The default method does not need to know that detail; nor can it directly access a private field that exists only in a class.

Interfaces do not have constructors and cannot declare instance fields. Every field declared in an interface is implicitly `public static final`. Therefore:

```java
interface Settings {
    int MAX_RETRIES = 3;
}
```

`MAX_RETRIES` is an interface-level constant, not a separate variable per instance. The `final` keyword prevents reassigning the reference variable, but it does not make the mutable object it points to immutable.

## 2. Be careful with mutable objects in interface fields

```java
import java.util.ArrayList;
import java.util.List;

interface SharedRecords {
    List<String> RECORDS = new ArrayList<>();

    default void record(String value) {
        RECORDS.add(value);
    }
}
```

This code is valid, but the `RECORDS` list is a shared `public static final` reference, not a separate list for each object. Any code with access can modify its contents; `ArrayList` also does not guarantee thread safety on its own. Placing a cache or mutable collection in an interface often inadvertently creates shared state that is hard to control.

If per-instance state is needed, place it in the implementing class. If shared state is needed, place it in a component with a clear owner, lifecycle, and synchronization policy.

## 3. Example: sharing an algorithm while keeping separate state

```java
public class DefaultStateDemo {
    interface Counter {
        int value();
        void add(int delta);

        default void increment() {
            add(1);
        }

        default boolean isZero() {
            return value() == 0;
        }
    }

    static final class MemoryCounter implements Counter {
        private int current;

        @Override
        public int value() {
            return current;
        }

        @Override
        public void add(int delta) {
            if (delta < 0) {
                throw new IllegalArgumentException("delta must be non-negative");
            }
            current = Math.addExact(current, delta);
        }
    }

    public static void main(String[] args) {
        Counter first = new MemoryCounter();
        Counter second = new MemoryCounter();
        first.increment();
        first.increment();

        System.out.println(first.value());
        System.out.println(second.value());
        System.out.println(first.isZero());
        System.out.println(second.isZero());
    }
}
```

Output:

```text
2
0
false
true
```

Both objects share the implementation of `increment()` and `isZero()`, but each `MemoryCounter` has its own `current` field. The example runs sequentially; it does not make `MemoryCounter` safe when multiple threads update it at the same time.

## 4. Contracts must clearly state preconditions and effects

A default method can combine multiple operations, but a Java signature does not fully define their meaning on its own. For each contract method, clarify:

| Aspect | What to specify |
| --- | --- |
| Preconditions | How are null, negative, empty, or out-of-range inputs handled? |
| Postconditions | Upon success, what is the result and how does the state change? |
| Exceptions | Are errors returned via a value, or which exception is thrown? |
| Side effects | Does the method modify data, perform I/O, or call other services? |
| Concurrency | Does the operation need to be atomic or thread-safe? |
| Overriding | Must custom implementations preserve the same semantic guarantees? |

Example of a problematic design:

```java
interface Inventory {
    int available();
    void reserve(int units);

    default boolean tryReserve(int units) {
        if (available() >= units) {
            reserve(units);
            return true;
        }
        return false;
    }
}
```

The two calls `available()` and `reserve()` are independent. Another thread can change the inventory between the check and the update; a default method does not turn a sequence of operations into an atomic transaction. The example also lacks rules for `units <= 0` and how failure is reported.

If checking and updating must be an atomic operation, let the class that owns the state implement a single contract method such as `tryReserve(int units)`. A default method can compose safe read operations, but it should not assume it can enforce invariants on state that the interface does not own.

## 5. Choosing the right mechanism

| Need | Typically suitable choice |
| --- | --- |
| Small behavior computed from clear contract methods | Default method |
| Each implementation must independently decide an important behavior | Abstract method |
| Shared instance state, constructors, and core logic | Abstract class if an inheritance relationship is appropriate |
| Caches, transactions, I/O, or dependencies with a lifecycle | Service or component object |
| Helpers serving only methods within the interface | Private interface method since Java 9 |

A default method can also be overridden; it is not a mechanism that guarantees the algorithm will always run. When releasing an API, check for method conflicts and behavioral compatibility with existing implementers. Code that compiles is not enough to prove that every implementation preserves the preconditions, postconditions, or concurrency guarantees.

## Self-check

1. Why are fields declared in an interface not separate state for each object?
2. Why does `static final` not make an `ArrayList` immutable?
3. Why doesn't `available()` followed by `reserve()` in a default method automatically create atomicity?
4. When should an operation be placed in an abstract method owned by the class instead of being composed in a default method?

**Remember:** default methods share logic. The implementing class or a dedicated component owns the data, invariants, and synchronization mechanisms. The contract must clearly describe how inputs, errors, side effects, and concurrency are handled.
