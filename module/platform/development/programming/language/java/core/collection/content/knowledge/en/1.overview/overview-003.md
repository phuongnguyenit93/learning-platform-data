# Relationships Among Iterable, Collection, List, Set, Queue, and Deque

When choosing a data structure in Java, the first question is not "which class should I use?", but "what contract does this code need?". Do you only need to iterate over elements, access them by position, eliminate duplicates, or retrieve elements from one or both ends? The six interfaces in this lesson describe those needs at different levels.

A single object can be viewed through multiple interfaces. For example, an `ArrayList<String>` is simultaneously a `List<String>`, a `Collection<String>`, and an `Iterable<String>`. This is the exact same object, not three copies. The type of the variable determines which operations the compiler allows you to call through that variable; the actual runtime class determines how those operations are executed.

## 1. Map of Contracts

| Interface | Question the contract answers | Key characteristics |
| --- | --- | --- |
| `Iterable<E>` | Can elements be traversed sequentially using an iterator? | Provides the starting point for iteration; does not inherently include size or add/remove operations. |
| `Collection<E>` | Can a group of elements be worked with as a single unit? | Provides common operations such as checking size, checking membership, and optional mutating operations. |
| `List<E>` | Is a positional sequence with index-based access needed? | The order of the sequence is significant; duplicate elements are allowed by the general contract. |
| `Set<E>` | Is a guarantee of no duplicate elements needed? | Uniqueness is the core characteristic; ordering depends on the specific contract. |
| `Queue<E>` | Is it necessary to add elements waiting for processing and retrieve the head element? | How the head element is determined depends on the queue type, not necessarily FIFO. |
| `Deque<E>` | Are operations at both the front and back of the sequence needed? | Double-ended queue; can be used in either FIFO or LIFO fashion. |

`E` is the element type parameter, such as `String`, `Integer`, or `Order`. These interfaces are not concrete storage classes.

`Iterable` belongs to the `java.lang` package and is implicitly imported like `String`. The remaining interfaces in the list belong to `java.util`.

## 2. Inheritance Relationships and Version Differences

In Java 17, the direct `extends` relationships among the six interfaces are represented as follows. Arrows point from the subinterface to the superinterface:

~~~mermaid
flowchart BT
    C["Collection<E>"] -->|extends| I["Iterable<E>"]
    L["List<E>"] -->|extends| C
    S["Set<E>"] -->|extends| C
    Q["Queue<E>"] -->|extends| C
    D["Deque<E>"] -->|extends| Q
~~~

From the diagram, we can deduce:

- Every `List`, `Set`, `Queue`, and `Deque` is a `Collection`, and therefore is an `Iterable`.
- Every `Deque` is a `Queue`; the converse is not true.
- Not every `Iterable` is a `Collection`.
- `List`, `Set`, and `Queue` do not inherit from one another.
- `Deque` does not inherit from `List`, even though both can represent data in an order.

### Since Java 21: Addition of SequencedCollection

Starting in Java 21, Java added interfaces for collections with a defined encounter order, including `SequencedCollection<E>`. When describing direct relationships, the following updates apply:

| Interface | Java 17 | Since Java 21 |
| --- | --- | --- |
| `Collection<E>` | Extends `Iterable<E>` | Still extends `Iterable<E>`. |
| `List<E>` | Directly extends `Collection<E>` | Extends `SequencedCollection<E>`, which extends `Collection<E>`. |
| `Set<E>` | Extends `Collection<E>` | Still extends `Collection<E>`; not every `Set` has a defined encounter order. |
| `Queue<E>` | Extends `Collection<E>` | Still extends `Collection<E>`. |
| `Deque<E>` | Extends `Queue<E>` | Extends both `Queue<E>` and `SequencedCollection<E>`. |

`SequencedCollection<E>` extends `Collection<E>`. `SequencedSet<E>` combines the contract of `Set<E>` with `SequencedCollection<E>`. This does not turn every `Set` into an indexed sequence.

Operations such as `getFirst()`, `getLast()`, and `reversed()` are available through the sequenced contract in Java 21. `reversed()` provides a reverse-ordered view, not a command that reverses the sequence in place. Whether add/remove operations are possible still depends on what the concrete object supports.

The subtyping deductions among the six interfaces above remain true. The important change is not drawing `List extends Collection` as a direct relationship for Java 21. The runnable examples in this lesson only use APIs available since Java 17 so that learners can run them on Java 17 or later.

## 3. Iterable: Traversal Capability, Not Yet a Collection

The central contract of `Iterable<E>` is providing `iterator()`. A for-each loop can use that iterator to retrieve each element.

~~~java
// Code snippet inside a method; not a standalone program.
Iterable<String> values = List.of("A", "B");

for (String value : values) {
    System.out.println(value);
}
~~~

Through the `values` variable, you can iterate, but you cannot call `size()`, `add(...)`, or `get(...)`, because those methods do not belong to the `Iterable` contract.

`Iterable` does not require the object to store all data in memory beforehand. It can represent a source that generates elements on demand during iteration. Knowing only that an object is `Iterable` is not enough to conclude:

- Whether the number of elements can be known in advance.
- Whether the source can be modified.
- Whether the data is finite.
- Whether repeated iterations will yield the same results.

### Iterable and Iterator Have Different Roles

`Iterable` is an object that provides a way to start an iteration. `Iterator` holds the state of a single traversal, with operations like `hasNext()` and `next()`.

Do not use these two names interchangeably. `Iterator` does not extend `Iterable`, and an `Iterator` variable cannot be passed directly into a for-each loop. An iterator that has already traversed elements also does not automatically reset to the beginning.

Java arrays work in a for-each loop, but they do not implement `Iterable`. The for-each syntax separately supports both arrays and `Iterable` objects; syntactic similarity does not prove an inheritance relationship.

## 4. Collection: The General Contract for a Group of Elements

`Collection<E>` adds common operations for a group of elements, such as:

- `size()`, `isEmpty()`: query the size and whether it is empty.
- `contains(Object)`: check whether an element belongs to the collection.
- `iterator()`: iterate over the elements.
- `add(E)`, `remove(Object)`, `clear()`: optional mutating operations.
- `addAll(...)`, `containsAll(...)`, `removeAll(...)`: work with multiple elements.
- `toArray()`, `stream()`: convert to other forms of processing.

Knowing only that an object is a `Collection` does not tell you whether it allows duplicate elements, what ordering it has, whether it allows `null`, or whether it is thread-safe for concurrent use. Those details must be determined from a more specific interface and the implementing class.

### Having a Method Does Not Mean Mutation Is Permitted

`Collection` declares mutating operations, but many of them are optional. For example:

~~~java
// Illustrative code snippet inside a method.
Collection<String> values = List.of("A", "B");

// values.add("C"); // Compiles, but throws UnsupportedOperationException at runtime.
~~~

`List.of(...)` returns a list that does not allow structural modification or replacing elements. Assigning it to a `Collection` variable does not make it a modifiable object.

Another example is `Arrays.asList(...)`: a fixed-size list that allows `set(...)` but does not support `add(...)` or `remove(...)` to change its size. Therefore, "unmodifiable", "fixed-size", and "modifiable" are distinct capabilities.

## 5. List: Positional Sequence

`List<E>` describes a sequence where the position of an element is significant. Indices start at `0`.

~~~java
// Requires importing java.util.ArrayList and java.util.List.
List<String> names = new ArrayList<>(List.of("An", "Bình", "An"));

System.out.println(names.get(1)); // Bình
System.out.println(names.size()); // 3
~~~

The two `"An"` elements coexist because `List` does not impose a uniqueness condition like `Set`.

Operations that characterize `List` include `get(index)`, `set(index, value)`, `add(index, value)`, `remove(index)`, and `listIterator()`.

It is important to distinguish:

- **Ordered**: the elements form a sequence with defined positions.
- **Sorted**: the elements follow a comparison rule, such as ascending order.

A `List` is ordered, but it is not inherently sorted. `List.of(30, 10, 20)` preserves the sequence `30, 10, 20` and does not automatically reorder it to `10, 20, 30`.

The indexed access contract also does not guarantee that `get(index)` is always equally fast. `ArrayList` and `LinkedList` are both `List` implementations, but they have different underlying structures and operation costs.

### Watch Out for the Two Forms of remove on List

With `List<Integer>`, `remove(1)` selects the method taking an `int` index, whereas `remove(Integer.valueOf(1))` selects the method taking the object to remove. This is a difference in method signatures, not Java guessing intent from the data.

Do not use this example to infer that every `Collection<Integer>` has `remove(index)`: the index-based method belongs to `List`, not to the general `Collection` contract.

## 6. Set: Uniqueness, Not "Always Unordered"

`Set<E>` guarantees no duplicate elements according to the set's contract. Here is an example using a set that preserves insertion order:

~~~java
// Requires importing java.util.LinkedHashSet and java.util.Set.
Set<String> tags = new LinkedHashSet<>();

System.out.println(tags.add("java")); // true
System.out.println(tags.add("java")); // false
System.out.println(tags.size());      // 1
~~~

The second addition does not modify the set.

You should not define `Set` as an "unordered Collection", because implementations behave differently:

| Implementation | Iteration order to understand |
| --- | --- |
| `HashSet` | Makes no guarantees as to the iteration order. Do not rely on an accidentally observed order. |
| `LinkedHashSet` | Commonly used when insertion order needs to be preserved across normal insertions. |
| `TreeSet` | Iterates according to natural ordering or a `Comparator`. |

`Set` does not provide `get(index)` like `List`. The fact that an implementation has an iteration order does not mean it supports random access by index.

For hash-based sets such as `HashSet`, the design of `equals()` and `hashCode()` must be consistent. For `TreeSet`, a comparison result of `0` determines whether two elements occupy the same position in the set; the comparison order should be consistent with `equals()` to fully satisfy the `Set` contract. This is why uniqueness should not be explained merely by looking at an object's string representation.

Do not arbitrarily mutate fields that affect hashing or comparison while an object is inside a set, as doing so can cause lookups to behave unexpectedly.

## 7. Queue: Retrieving Elements According to Queue Rules

`Queue<E>` describes a collection designed for holding elements prior to processing. An important concept is the **head**: the element that the next retrieval operation will return.

Many queues operate in FIFO order, meaning the first element in is the first element out. However, FIFO is not the only rule for every `Queue`.

For example, `PriorityQueue` determines the head based on priority. With the natural ordering of integers, adding `30, 10, 20` and repeatedly calling `poll()` will yield `10, 20, 30`.

Do not infer the `poll()` order from a for-each loop or `toString()` on a `PriorityQueue`. Its iterator does not guarantee traversal in priority order; you must retrieve elements using queue operations if the goal is priority-based processing.

### Two Groups of Methods

| Purpose | Throws exception | Returns special value |
| --- | --- | --- |
| Insert element | `add(e)` | `offer(e)` |
| Retrieve and remove head | `remove()` | `poll()` |
| Examine head without removing | `element()` | `peek()` |

When the queue is empty, `remove()` and `element()` throw `NoSuchElementException`; `poll()` and `peek()` return `null`.

When an insertion fails due to capacity restrictions, `offer(e)` returns `false`, while `add(e)` can throw `IllegalStateException`. "Returns a special value" does not mean exceptions are never thrown: invalid input, such as `null` in an implementation that forbids `null`, can still be rejected with an exception.

The parameterless `remove()` on `Queue` differs from `remove(Object)` inherited from `Collection`. The former removes the head of the queue; the latter searches for and removes the specified element.

Avoid using `null` as queue data because `null` is also used as a sentinel value meaning "no element". Not all implementations share the same policy regarding `null`.

## 8. Deque: One Sequence, Operations at Both Ends

`Deque` stands for double-ended queue.

In addition to being a `Queue`, it allows explicit operations at both the front and the back:

| Position | Insert | Retrieve and remove | Examine only |
| --- | --- | --- | --- |
| Front of sequence | `offerFirst(e)` | `pollFirst()` | `peekFirst()` |
| Back of sequence | `offerLast(e)` | `pollLast()` | `peekLast()` |

Besides these forms, there are also exception-throwing forms: `addFirst`, `removeFirst`, `getFirst`, `addLast`, `removeLast`, and `getLast`.

### Using as a FIFO Queue

Insert at the back, retrieve from the front:

~~~java
// Requires importing java.util.ArrayDeque and java.util.Deque.
Deque<String> tasks = new ArrayDeque<>();
tasks.offerLast("A");
tasks.offerLast("B");

System.out.println(tasks.pollFirst()); // A
System.out.println(tasks.pollFirst()); // B
~~~

When viewing a `Deque` through the `Queue` contract, `offer(e)` corresponds to `offerLast(e)`, `poll()` to `pollFirst()`, and `peek()` to `peekFirst()`.

### Using as a LIFO Stack

Insert and retrieve at the same end:

~~~java
// Code snippet inside a method, with the same imports as the example above.
Deque<String> stack = new ArrayDeque<>();
stack.push("A");
stack.push("B");

System.out.println(stack.pop()); // B
System.out.println(stack.pop()); // A
~~~

`push(e)` corresponds to `addFirst(e)`; `pop()` corresponds to `removeFirst()`. Calling `pop()` on an empty deque throws an exception, whereas `pollFirst()` returns `null`.

`Deque` provides stack operations without relying on the legacy `Stack` class. `ArrayDeque` is a common choice for a stack or queue in single-threaded code; it does not allow `null` elements.

Having two ends does not mean having `get(index)`. A `Deque` is not a `List`.

## 9. Declared Type vs. Actual Object

The following snippet does not create additional collections when changing the reference type:

~~~java
// Code snippet inside a method, with the corresponding java.util imports.
List<String> list = new ArrayList<>(List.of("A", "B"));
Collection<String> collection = list;
Iterable<String> iterable = collection;

System.out.println(list.get(0));       // A
System.out.println(collection.size()); // 2

// collection.get(0); // Does not compile: Collection does not declare get(index).
// iterable.size();   // Does not compile: Iterable does not declare size().

list.add("C");
System.out.println(collection.size()); // 3
~~~

All three variables point to the same `ArrayList` object. Therefore, changes made through `list` are visible through `collection`. However, the fact that the actual object has a `get` method does not make the compiler allow calling `get` on a variable of type `Collection`.

Parameters should be declared using the contract that matches the method's needs:

- Only iterating: consider `Iterable<?>` or `Iterable<? extends T>`.
- Also need `size()` or `contains(...)`: consider `Collection<T>`.
- Need positional access: use `List<T>`.
- Need to express uniqueness: use `Set<T>`.
- Need queue operations: use `Queue<T>`.
- Need both ends or a stack: use `Deque<T>`.

Do not declare an overly general type and then cast it back just to call a method that the design needed from the start. Casting an arbitrary `Collection` to `List` can cause a `ClassCastException` if the actual object is a `HashSet`.

### One Class Can Satisfy Multiple Contracts

`LinkedList` implements both `List` and `Deque`:

~~~java
// Code snippet inside a method; requires importing java.util.LinkedList.
LinkedList<String> actual = new LinkedList<>();
List<String> listView = actual;
Deque<String> dequeView = actual;
~~~

This does not create a `List extends Deque` or `Deque extends List` relationship. Relationships of an implementing class must not be inferred backward as inheritance relationships between two interfaces.

Similarly, `Collection<Integer>` is not a subtype of `Collection<Number>`, even though `Integer` is a subtype of `Number`. This is a rule of generics, separate from `List<E>` being a subtype of `Collection<E>`. When accepting multiple element types for read-only purposes, wildcards can express the appropriate intent.

## 10. Complete Program

Save the code below in a file named **CollectionRelationshipsDemo.java**. The program only uses APIs available in Java 17; `Iterable` does not need to be imported because it belongs to `java.lang`.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Deque;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.PriorityQueue;
import java.util.Queue;
import java.util.Set;
import java.util.StringJoiner;

public class CollectionRelationshipsDemo {
    public static void main(String[] args) {
        List<String> list = new ArrayList<>(List.of("A", "B", "A"));
        Collection<String> collectionView = list;
        Iterable<String> iterableView = collectionView;

        printAll("Iterable view", iterableView);
        System.out.println("Collection size = " + collectionView.size());
        System.out.println("List get(1) = " + list.get(1));

        Set<String> unique = new LinkedHashSet<>(list);
        System.out.println("Set = " + unique);

        Queue<Integer> priority = new PriorityQueue<>(List.of(30, 10, 20));
        List<Integer> removed = new ArrayList<>();
        Integer next;
        while ((next = priority.poll()) != null) {
            removed.add(next);
        }
        System.out.println("Queue poll order = " + removed);

        Deque<String> deque = new ArrayDeque<>();
        deque.offerLast("A");
        deque.offerLast("B");
        System.out.println("Deque after offerLast = " + deque);
        System.out.println("Deque pollFirst = " + deque.pollFirst());

        deque.offerFirst("Z");
        System.out.println("Deque after offerFirst = " + deque);
        System.out.println("Deque pollLast = " + deque.pollLast());

        Queue<String> queueView = deque;
        System.out.println("Queue view peek = " + queueView.peek());

        Iterable<Integer> onlyIterable = () -> List.of(1, 2, 3).iterator();
        printAll("Only Iterable", onlyIterable);
        System.out.println(
                "Only Iterable is Collection = "
                        + (onlyIterable instanceof Collection<?>)
        );
    }

    private static void printAll(String label, Iterable<?> values) {
        StringJoiner result = new StringJoiner(", ", "[", "]");
        for (Object value : values) {
            result.add(String.valueOf(value));
        }
        System.out.println(label + " = " + result);
    }
}
~~~

Compile and run from the directory containing the file using JDK 17 or later:

~~~shell
javac --release 17 -encoding UTF-8 CollectionRelationshipsDemo.java
java CollectionRelationshipsDemo
~~~

Stdout:

~~~text
Iterable view = [A, B, A]
Collection size = 3
List get(1) = B
Set = [A, B]
Queue poll order = [10, 20, 30]
Deque after offerLast = [A, B]
Deque pollFirst = A
Deque after offerFirst = [Z, B]
Deque pollLast = B
Queue view peek = Z
Only Iterable = [1, 2, 3]
Only Iterable is Collection = false
~~~

### Reading the Output by Contract

1. `Iterable view` and `Collection size` observe the same original list without creating a copy.
2. `List get(1)` uses positional access, which is only available on the appropriate contract.
3. `LinkedHashSet` eliminates the duplicate `A` element while preserving insertion order in this example, resulting in `[A, B]`.
4. `PriorityQueue` retrieves numbers in priority order; the result is collected using `poll()`, not by using an iterator.
5. `Deque` allows inserting/retrieving at both ends. When switched to a `Queue` variable, `peek()` inspects the head of the same object.
6. The lambda object `onlyIterable` only provides `Iterable`; the object itself is not a `Collection`, even though the iterator it returns comes from a list.

The `printAll` method accepts `Iterable<?>` because it only needs to iterate. It does not require the caller to pass a `List` or a modifiable collection.

## 11. Choosing an Implementation After Choosing the Contract

| Code requirement | Typically appropriate declared type | Illustrative implementation | Additional checks |
| --- | --- | --- | --- |
| Positional list, index-based access | `List<E>` | `ArrayList<E>` | Insert/remove costs, size, and mutability. |
| Unique members, no iteration order needed | `Set<E>` | `HashSet<E>` | `equals/hashCode` contract; do not rely on accidental order. |
| Unique members, insertion order needed | `Set<E>` | `LinkedHashSet<E>` | If sequenced APIs are needed, check the Java version and a more specific declared type. |
| Unique members in comparison order | `Set<E>` or an appropriate sorted set interface | `TreeSet<E>` | Comparison rules and consistency with `equals`. |
| Priority-based processing | `Queue<E>` | `PriorityQueue<E>` | How elements are compared; iterator order is not retrieval order. |
| Single-threaded FIFO queue or LIFO stack | `Queue<E>` or `Deque<E>` | `ArrayDeque<E>` | Choose front/back operations matching intent; `null` is not allowed. |

This table does not claim that one implementation suits every data volume. When multiple threads, capacity bounds, blocking for elements, or concurrent access requirements are involved, specialized contracts and implementations must be considered. Merely changing a variable from `List` to `Collection` does not make an object thread-safe.

## 12. Easily Confused Relationships

### Collection vs. Collections

`Collection` is an interface describing a group of elements. `Collections` is a utility class containing static methods, such as sorting, reversing a list, or creating wrapper views.

Similar names do not mean `Collections` is a superinterface or implementation class of every `Collection`.

### Map Does Not Extend Collection

`Map<K, V>` describes a key-value mapping; it does not extend `Collection` and is not inherently `Iterable`.

It provides related views:

- `keySet()`: a `Set<K>`.
- `values()`: a `Collection<V>`, because values can be duplicated.
- `entrySet()`: a `Set<Map.Entry<K, V>>`.

You can use a for-each loop over these views. This is not evidence that `Map` itself is a `Collection`. A view is also not necessarily an independent copy, and not every mutating operation is supported.

### Stream Is Neither Iterable Nor Collection

`Stream` describes a data processing pipeline, not a collection for storing and accessing elements like `List`. `Collection.stream()` is a way to create a stream from a collection, not an inheritance relationship.

Do not assume a stream can be reused after a terminal operation has been executed, and do not use `Stream` in place of `Iterable` just because both can process elements one by one.

## 13. Common Misconceptions About Interface Relationships

| Misconception | Accurate understanding |
| --- | --- |
| Every `Iterable` has `size()`. | Traversal capability alone does not imply a size contract. |
| Every `Collection` allows adding/removing. | Mutating operations may be unsupported. |
| `List` means sorted data. | `List` is a positional sequence; sorting is a separate condition. |
| `Set` is always unordered. | `Set` focuses on uniqueness; implementations decide ordering. |
| Every `Queue` is FIFO. | The head element can be selected by priority or another rule. |
| `PriorityQueue` can be treated like a sorted list. | `poll` retrieval order and iteration order are two different contracts. |
| `Deque` is a `List` because both have a front and back. | `Deque` does not provide an indexed access contract. |
| Changing a variable's type creates a new collection. | Reference assignment does not copy the object. |
| A class implementing two interfaces means those interfaces extend each other. | That is the relationship of the class to each interface, not between the two interfaces. |
| Java 17's direct relationship diagram always applies unchanged in Java 21. | Java 21 adds the `SequencedCollection` layer for `List` and adds it to the supertypes of `Deque`. |

Another practical point is not to arbitrarily modify a collection's structure during a for-each loop. Depending on the implementation, the iterator may detect the modification and throw `ConcurrentModificationException`; this detection mechanism is not a synchronization solution across threads. If removal during traversal is needed, you must use an operation supported by the contract and concrete object, such as `Iterator.remove()` or `removeIf(...)` in an appropriate context.

## 14. Self-Check

1. Does a method that only prints elements sequentially need to accept a `List`? Why might `Iterable` be a more appropriate contract?
2. Why can calling `add` through a `Collection` variable compile yet still fail at runtime?
3. If you need a list of unique names that preserves input order, is knowing only "use a `Set`" enough to pick an implementation?
4. Why is a for-each loop on a `PriorityQueue` not the way to retrieve elements in priority order?
5. Use `ArrayDeque` to process three tasks in FIFO order, then change the operations to process them in LIFO order.
6. Why can a `LinkedList` be assigned to both `List` and `Deque`, yet we cannot conclude that `List` extends `Deque`?
7. When updating an architecture description from Java 17 to Java 21, what needs to be corrected in the direct relationships of `List` and `Deque`?

Once you can explain these questions on your own, you can read a type declaration and know what the code is entitled to expect before considering storage classes, performance, or concurrency.
