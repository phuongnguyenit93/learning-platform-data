# Skeletal implementation: combining a skeletal class with an interface

A **skeletal implementation** is an abstract class that provides most of the shared behavior of an interface, so each concrete implementation class only needs to write the missing core parts. This pattern combines the advantages of an interface — describing a contract and allowing a class to implement multiple interfaces — with the advantages of an abstract class — sharing implementation code, algorithms, and state when needed.

For example, an interface can define a sequence of numbers using basic operations such as getting the size and reading an element. A skeletal class can use those two operations to implement iteration, searching, summation, and string representation out of the box. The concrete class only needs to provide how data is stored and accessed.

## 1. Three roles in the design pattern

| Component | Responsibility |
| --- | --- |
| Interface | Publishes the contract: the operations that every implementation must provide |
| Skeletal implementation | Implements the operations that can be derived from the contract, consolidates shared logic, and keeps algorithms consistent |
| Concrete implementation | Provides the foundational operations that depend on a specific storage mechanism or data source |

The relationship typically looks like:

```text
Client
  |
  v
Interface (contract)
  ^
  |
Abstract/Skeletal implementation
  ^
  |
Concrete implementation
```

The client should work through the interface type whenever possible. By doing so, the client depends on the public contract rather than depending on a concrete implementation class.

Skeletal implementation is a design pattern, not a Java keyword or special mechanism. Class names typically start with `Abstract`, such as `AbstractList` or `AbstractCollection`.

## 2. Why combine an interface with an abstract class?

Interfaces and abstract classes address related but different needs:

- An **interface** defines the API and allows a class to implement multiple interfaces. Implementations can differ completely in their data structures.
- An **abstract class** can provide actual executable code, instance fields, constructors, `protected` methods, and shared helpers. A Java class can directly `extends` only one class.
- A **skeletal implementation** puts the contract in the interface and the shared code in the abstract class. An implementation can extend the skeletal class, while the client still uses the interface.

If only an interface is used, `default` methods can be used to provide default behavior. However, default methods do not completely replace a skeletal implementation. An abstract class can store state, have constructors, provide `protected` helpers, and organize a common algorithm into steps that subclasses customize. In addition, an abstract class can also support older Java versions when default methods did not yet exist.

There is no need to create a skeletal class if the interface only has a few independent operations, has no significant shared logic, or an abstract class would be an obstacle because the implementation classes already need to extend another class. Choose this pattern when it genuinely reduces duplicate code and keeps behavior consistent.

## 3. How to design a skeletal implementation

An effective approach is:

1. **Define the minimal contract.** The interface only requires the operations that every implementation can actually provide.
2. **Identify derivable behavior.** If an operation can be built from the foundational operations, implement it in the skeletal class.
3. **Keep extension points.** Operations that depend on a specific data structure can be abstract for subclasses to implement.
4. **Use foundational methods consistently.** Skeletal methods should call the interface methods instead of assuming that subclasses store data in a specific way.
5. **Verify the contract and edge cases.** Clearly define the behavior for empty data, invalid indices, nonexistent elements, and exceptions.
6. **Create small concrete implementations.** If a concrete class only has to implement a few foundational methods, the skeletal class is fulfilling its role properly.

For example, for a sequence of numbers, `size()` and `get(index)` can be two foundational operations. From there, the skeletal class can implement `contains(value)`, `sum()`, `iterator()`, and `toString()` out of the box. The concrete class only needs to define how to compute the size and read an element.

## 4. Runnable Java example

The example below illustrates the three roles. `IntSequence` is the interface; `AbstractIntSequence` is the skeletal class providing shared behavior; `ArrayIntSequence` is an array-backed implementation.

Save the entire program in the file `Main.java`:

```java
import java.util.Iterator;
import java.util.NoSuchElementException;
import java.util.StringJoiner;

interface IntSequence extends Iterable<Integer> {
    int size();
    int get(int index);
    boolean contains(int value);
    int sum();

    default boolean isEmpty() {
        return size() == 0;
    }
}

abstract class AbstractIntSequence implements IntSequence {
    @Override
    public boolean contains(int target) {
        for (int i = 0; i < size(); i++) {
            if (get(i) == target) {
                return true;
            }
        }
        return false;
    }

    @Override
    public int sum() {
        int total = 0;
        for (int value : this) {
            total += value;
        }
        return total;
    }

    @Override
    public Iterator<Integer> iterator() {
        return new Iterator<>() {
            private int index;

            @Override
            public boolean hasNext() {
                return index < size();
            }

            @Override
            public Integer next() {
                if (!hasNext()) {
                    throw new NoSuchElementException();
                }
                return get(index++);
            }
        };
    }

    @Override
    public String toString() {
        StringJoiner result = new StringJoiner(", ", "[", "]");
        for (int value : this) {
            result.add(Integer.toString(value));
        }
        return result.toString();
    }
}

final class ArrayIntSequence extends AbstractIntSequence {
    private final int[] values;

    ArrayIntSequence(int... values) {
        this.values = values.clone();
    }

    @Override
    public int size() {
        return values.length;
    }

    @Override
    public int get(int index) {
        return values[index];
    }
}

public class Main {
    public static void main(String[] args) {
        IntSequence sequence = new ArrayIntSequence(10, 20, 30);

        System.out.println("size=" + sequence.size());
        System.out.println("empty=" + sequence.isEmpty());
        System.out.println("contains20=" + sequence.contains(20));
        System.out.println("sum=" + sequence.sum());
        System.out.println("values=" + sequence);
    }
}
```

Compile and run using Java 17 or later:

```text
javac Main.java
java Main
```

Exact stdout output:

```text
size=3
empty=false
contains20=true
sum=60
values=[10, 20, 30]
```

### Reading the example by role

- `IntSequence` declares `size()`, `get()`, `contains()`, and `sum()`. Every implementation must fulfill those contracts. The interface also provides `isEmpty()` via a `default` method.
- `AbstractIntSequence` implements `contains()`, `sum()`, `iterator()`, and `toString()`. These methods rely only on the `size()` and `get()` contract, so they do not need to know whether the data is stored in an array or another source.
- `ArrayIntSequence` only provides a way to get the size and elements from an array. It inherits the remaining behaviors from the skeletal class.
- The variable `sequence` has the declared type `IntSequence`. The client can replace `ArrayIntSequence` with another implementation without changing how the operations declared in the interface are called.

`ArrayIntSequence` copies the input array so that modifying the external array after object creation does not alter the internal data. The example is kept simple, so no API for modifying elements is added.

## 5. Template method and extension points

A skeletal implementation often uses the **Template Method** idea: the skeletal class defines a general workflow, in which some steps call methods implemented by subclasses. For example, `sum()` iterates over `this`; the iterator in turn calls `size()` and `get(index)`. As a result, the summation algorithm is written once yet still works with many storage representations.

Extension points need to be designed carefully:

- Abstract methods should only represent operations that the concrete implementation must decide.
- Skeletal methods should clearly specify preconditions, postconditions, and exceptions; they should not rely on private state that the interface does not guarantee.
- When a skeletal method calls an overridable method, consider whether a subclass could break invariants or produce unexpected behavior.
- Do not mechanically make every method `final`. Doing so can prevent implementations that optimize algorithms or need to adjust behavior within the scope of the contract.

In the example, `contains()` can be optimized in an implementation using a set or hash table, whereas an array implementation can use the default linear traversal. The skeletal class should provide a reasonable shared implementation without taking away the ability to optimize when there is a clear reason.

## 6. Skeletal implementations in the Java library

The Java Collections Framework uses this pattern extensively:

- `AbstractCollection<E>` provides part of the shared behavior for collections and requires subclasses to implement the appropriate foundational operations.
- `AbstractList<E>` is the skeleton for `List` types; some implementations rely on `get(index)` and `size()`, while other implementations can override operations for optimization.
- `AbstractSet<E>` and `AbstractMap<K,V>` also provide shared behavior for their respective type families.

When using these classes, read the interface contract and the documentation of the specific abstract class to know which methods must be overridden, which methods are already implemented, and which operations may throw `UnsupportedOperationException`. Do not assume that every method declared in the interface already has an efficient or suitable implementation for every data structure.

## 7. Default methods versus skeletal implementation

| Criterion | Interface `default` method | Skeletal implementation |
| --- | --- | --- |
| Location of shared code | Directly in the interface | In an abstract class |
| Inheriting multiple contracts | Can implement multiple interfaces | Can directly extend only one class |
| Instance state and constructors | No instance constructors; cannot hold regular instance fields | Can have constructors and state |
| `protected` helpers | Not provided through a class protected mechanism | Can be provided |
| Primary goal | Add default behavior to an interface | Share a structured set of implementations, which may include both algorithms and state |

An interface can work alongside a skeletal implementation: the interface holds the contract and small, independent default methods; the abstract class holds larger algorithms or helpers that require state. However, avoid placing the same behavior in both places in a way that makes the rules for choosing an implementation hard to understand.

If a class inherits from an existing superclass, it cannot simultaneously `extends AbstractIntSequence`. In that case, an implementation can be provided via composition, appropriate default methods can be used, or the logic can be extracted into a standalone helper. The choice depends on the contract and practical reusability.

## 8. Common design mistakes

- **Putting too many foundational operations into the interface:** new implementations have to write a lot of repetitive code, making the contract hard to satisfy.
- **Skeletal class assuming a specific storage representation:** for example, accessing an internal array that does not exist in other implementations. Work through the contract methods.
- **Ignoring exception contracts:** `get(index)` may throw `IndexOutOfBoundsException`; the iterator must throw `NoSuchElementException` when there are no more elements. Behavior needs to be consistent and clearly documented.
- **Using a skeletal class just to have a superclass:** if there is no useful shared code, the abstract class adds complexity without providing benefits.
- **Forgetting the single-inheritance limitation:** an implementation cannot extend two skeletal classes at the same time. Do not make the skeletal implementation the sole requirement for using the interface.
- **Treating default code as optimal for every case:** subclasses may need to override methods that are unsuitable in terms of performance, as long as the contract is preserved.

## 9. Checklist when applying

Before creating a skeletal implementation, ask yourself:

1. Does the interface accurately describe the minimal contract?
2. Which behaviors can be derived from a small number of foundational operations?
3. Does the skeletal class avoid depending on specific storage details?
4. Are edge cases and exceptions defined consistently?
5. Is there a clear reason to use an abstract class instead of default methods or composition?
6. Can a concrete implementation be written concisely by providing only the foundational operations?
7. Can the client continue programming against the interface type rather than the concrete class type?

A skeletal implementation is suitable when you want to define a flexible interface while still providing a structured shared implementation. Design the contract first, identify the foundational operations, and then place reusable logic into the abstract class. The result is shorter concrete implementations, more consistent behavior, and clients that depend less on implementation details.
