# `Iterable` and `Iterator`: Data Traversal Contracts

`Iterable` and `Iterator` are two foundational interfaces in Java for iterating over a sequence of elements without needing to know how the data is stored or generated. `Iterable<T>` represents an object that can provide an iterator to traverse elements of type `T`; `Iterator<T>` represents the state and operations of a specific traversal.

These two interfaces have related yet distinct roles: `Iterable` provides the starting point to obtain an iterator, while `Iterator` controls checking for the next element and retrieving it. Understanding the contract properly helps you use the `for-each` loop, write your own iterable data types, and avoid errors when an iterator has reached the end.

## 1. The `Iterable<T>` Contract

`Iterable<T>` is located in `java.lang`, so no separate import is required. The most important part of the contract is the method:

```java
Iterator<T> iterator();
```

The `iterator()` method returns an object used to traverse the elements. A class that wants to work with the collection-style `for-each` loop can implement `Iterable<T>` and provide this method. For example, `List<T>` inherits the `Iterable<T>` contract through `Collection<T>`.

`Iterable` does not require an object to store all elements in memory or to be a collection. An object can generate values during traversal, read from a data source, or compute elements on demand. Details regarding ordering, the ability to iterate multiple times, and whether the data changes depend on the specific type.

Besides `iterator()`, `Iterable` has useful default methods such as `forEach(Consumer<? super T>)` and `spliterator()`. `forEach` applies an action to elements in the traversal order provided; `spliterator` provides a traversal mechanism that can support splitting work for APIs such as Stream.

## 2. The `Iterator<T>` Contract

An iterator manages a single traversal. The two core methods are:

```java
boolean hasNext();
T next();
```

- `hasNext()` returns `true` if the traversal still has at least one element; this method does not retrieve or consume the next element.
- `next()` returns the next element and advances the traversal state. If no elements remain, `next()` must throw `NoSuchElementException`.

`Iterator` also has `remove()`, an optional operation to remove the most recent element returned by `next()`. An iterator that does not support removal may throw `UnsupportedOperationException`. You should not assume that every iterator allows modifying the collection during traversal. The default method `forEachRemaining(Consumer<? super T>)` performs an action for the remaining elements.

Typically, call `hasNext()` to check before calling `next()` in a loop. Do not call `next()` another time after all elements have been exhausted. An iterator is normally a forward-moving cursor; to traverse again, obtain another iterator from the `Iterable` if the data type supports repeated iteration.

## 3. Runnable Java 17+ Example

The example below defines `IntRange`, a sequence of integers from `startInclusive` up to (but excluding) `endExclusive`. This class implements `Iterable<Integer>`, and each call to `iterator()` creates an iterator with its own state.

Save to the file `IterableIteratorDemo.java`:

```java
import java.util.Iterator;
import java.util.NoSuchElementException;

public class IterableIteratorDemo {
    static final class IntRange implements Iterable<Integer> {
        private final int startInclusive;
        private final int endExclusive;

        IntRange(int startInclusive, int endExclusive) {
            if (endExclusive < startInclusive) {
                throw new IllegalArgumentException("endExclusive must be >= startInclusive");
            }
            this.startInclusive = startInclusive;
            this.endExclusive = endExclusive;
        }

        @Override
        public Iterator<Integer> iterator() {
            return new Iterator<>() {
                private int current = startInclusive;

                @Override
                public boolean hasNext() {
                    return current < endExclusive;
                }

                @Override
                public Integer next() {
                    if (!hasNext()) {
                        throw new NoSuchElementException();
                    }
                    return current++;
                }
            };
        }
    }

    public static void main(String[] args) {
        Iterable<Integer> numbers = new IntRange(1, 5);

        System.out.println("for-each:");
        for (int number : numbers) {
            System.out.println(number);
        }

        System.out.println("manual iterator:");
        Iterator<Integer> iterator = numbers.iterator();
        while (iterator.hasNext()) {
            System.out.println(iterator.next());
        }
    }
}
```

Compile and run from the directory containing the file:

```text
javac IterableIteratorDemo.java
java IterableIteratorDemo
```

Exact output:

```text
for-each:
1
2
3
4
manual iterator:
1
2
3
4
```

## 4. How to Read the Example

`IntRange` stores two bounds. The condition `current < endExclusive` excludes the end value from the sequence; for `new IntRange(1, 5)`, the elements are `1`, `2`, `3`, `4`. The constructor rejects an end bound smaller than the start bound to avoid an invalid range under the chosen contract.

Inside `iterator()`, the anonymous class holds the `current` variable. `hasNext()` only checks the condition, while `next()` checks the condition again, throws `NoSuchElementException` if exhausted, and then returns the current value and increments the counter. The check inside `next()` is still necessary because the caller may invoke `next()` without calling `hasNext()` first.

The `for (int number : numbers)` loop is a convenient traversal syntax for an `Iterable` object. Conceptually, the compiler obtains an iterator and loops while `hasNext()` remains true, calling `next()` on each iteration to receive the value. The `while` loop that follows directly expresses that contract. Because `IntRange.iterator()` in the example creates new state each time it is called, both traversals start from `1`.

## 5. Quick Comparison

| Component | Responsibility | Usage Example |
| --- | --- | --- |
| `Iterable<T>` | Provides an iterator for an iterable object. | `for (String s : names)` |
| `Iterator<T>` | Tracks the position of a traversal, checks for and returns the next element. | `while (it.hasNext()) { use(it.next()); }` |
| `Collection<T>` | Represents a group of elements and extends `Iterable<T>`. | `List<String> names = new ArrayList<>();` |

Choose `Iterable` when you want users to be able to iterate over your data type with `for-each`. Work directly with `Iterator` when you need to control traversal progress, call `remove()` if supported, or stop at a specific condition.

## 6. Common Mistakes and Caveats

1. **Calling `next()` after running out of elements.** Always check `hasNext()` or use `for-each`; if no elements remain, `next()` throws `NoSuchElementException`.
2. **Confusing `hasNext()` with retrieving an element.** `hasNext()` only checks whether any elements remain; `next()` is what returns the element and advances the iterator.
3. **Assuming `remove()` is always supported.** This is an optional operation. Read the documentation of the specific iterator type and handle `UnsupportedOperationException` if your design needs to account for that case.
4. **Modifying the collection externally during traversal.** Some JDK iterators are fail-fast and may throw `ConcurrentModificationException` when detecting a disallowed modification. The fail-fast mechanism is only intended for best-effort error detection; it is neither a synchronization guarantee nor a guarantee to detect all modifications. Use a modification API supported by the iterator or an appropriate synchronization mechanism.
5. **Assuming every `Iterable` can be traversed again.** The `Iterable` contract provides `iterator()`, but repeatability and source state depend on the implementation. If multiple traversals are needed, confirm that the specific type supports it.
6. **Ignoring traversal order.** Element ordering is defined by the implementation. A `List` preserves index-based order, whereas another collection type may have a different ordering rule.

## 7. Key Takeaways

- `Iterable<T>` provides `iterator()`; `Iterator<T>` provides `hasNext()` and `next()`.
- `hasNext()` checks; `next()` returns the next element and throws `NoSuchElementException` when exhausted.
- The `for-each` loop makes iterating over an `Iterable` more concise; an explicit iterator is useful when you need control over the traversal.
- `remove()` is an optional operation, and fail-fast is not a synchronization mechanism.
- When implementing `Iterable` yourself, clearly define the ordering, termination condition, behavior when elements are exhausted, and the ability to create new iterators.
