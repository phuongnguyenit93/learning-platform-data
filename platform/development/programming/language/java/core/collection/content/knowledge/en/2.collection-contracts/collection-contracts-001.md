# Programming to Interfaces and Choosing Implementation Classes

## 1. Two Decisions in a Single Declaration

When managing multiple elements, we must answer two distinct questions:

1. **What capabilities must this structure provide?** A positional list, a set without duplicates, a queue, or a key–value mapping?
2. **Which object will implement those capabilities?** A dynamic array, a hash table, an ordered tree, or a double-ended structure?

In the Java Collections Framework, the interface expresses the first question; the implementation class is a key part of the second.

```java
List<String> names = new ArrayList<>();
```

Read this line in three parts:

- `List<String>`: the variable `names` is declared as a list of `String` elements.
- `new ArrayList<>()`: creates an object whose actual runtime class is `ArrayList`.
- `=`: stores a reference to that object in the variable; it does not create another `List` object.

`List` is an interface, so you cannot write `new List<>()`. The object remains an `ArrayList` after being assigned to a variable of type `List`.

The goal of this declaration style is to make calling code depend on the **required contract**, while keeping the storage choice at the instantiation site. It enables controlled change; it does not make all implementation classes equivalent.

The examples use APIs available in Java 17. Before practicing, you should be familiar with reference variables, methods, basic generics, and `for-each` loops.

## 2. What Roles Do the Declared Type and Actual Class Play?

### 2.1. The Declared Type Determines Which APIs Can Be Called Directly

The following two variables point to the same object:

```java
// Illustrative snippet inside a method; requires import java.util.*.
ArrayList<String> storage = new ArrayList<>();
List<String> names = storage;

names.add("Lan");
storage.ensureCapacity(100);

System.out.println(names.size()); // 1
```

`add` belongs to the `List` contract, so it can be called through `names`. `ensureCapacity` is an operation specific to `ArrayList` and is not part of the Java 17 `List` API. Therefore, `names.ensureCapacity(100)` does not compile, even though the actual object is an `ArrayList`.

Both references share the same object. Changes made through one reference can be observed through the other. Declaring with an interface does not copy data and does not create a wrapper class.

Reference types and the object values a variable can hold are specified in [JLS: Reference Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.3.1) and [Variables of Reference Type](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.2).

### 2.2. The Actual Object Provides the Implementation at Runtime

```java
// Illustrative snippet inside a method; requires import java.util.*.
List<String> tasks = new ArrayList<>();
tasks.add("code");

tasks = new LinkedList<>(tasks);
tasks.add("test");
```

Initially, `tasks` references an `ArrayList`. After the second assignment, it references a new `LinkedList`, initialized from the elements of the old list.

Normal instance method calls such as `tasks.add(...)` are dispatched to the appropriate implementation of the object at runtime. Callable signatures must still be valid for the declared type at compile time. This is the relationship between polymorphism, interfaces, and implementation classes; see [JLS: Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12).

Note: the assignment in the example **creates a new structural copy**; it does not turn the old `ArrayList` object into a `LinkedList`. If another variable holds the old list, that variable continues to see the old list. The elements themselves are copied references, not deep-cloned.

## 3. Choosing an Interface Based on Data Semantics

Choosing the highest interface in the inheritance hierarchy is not always best. Choose an interface that adequately expresses the operations and semantics your code needs.

| Need | Appropriate Interface | What It Expresses |
| --- | --- | --- |
| Only need to iterate over each element | `Iterable<E>` | Does not require indexing or size checks |
| Need a group of elements and common operations like `size`, `contains` | `Collection<E>` | Does not yet commit to a list or a set |
| Need positions, indices, and possibly duplicate elements | `List<E>` | Order of a sequence of elements |
| Need uniqueness | `Set<E>` | A set governed by equality rules |
| Need a sorted set | `SortedSet<E>` | Natural ordering or a `Comparator` |
| Need to find elements near a bound, such as `ceiling` or `floor` | `NavigableSet<E>` | Navigation capabilities on an ordered set |
| Need to insert/remove according to a queue policy | `Queue<E>` | Operations at the head of the queue |
| Need operations at both ends, FIFO or LIFO | `Deque<E>` | Intent to use both ends |
| Need to look up values by key | `Map<K, V>` | Each key maps to at most one value |
| Need a mapping ordered by keys | `SortedMap<K, V>` | Ordering of keys |
| Need navigation by key | `NavigableMap<K, V>` | For example, finding the smallest key not below a bound |

`Map` belongs to the Collections Framework, but **does not extend `Collection`**. It manages mappings rather than just a group of elements. Views such as `keySet()`, `values()`, and `entrySet()` provide collection-like views. See [Map API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).

For example, if an algorithm calls `get(i)`, a `Collection<String>` parameter is not sufficient. Conversely, a method that only iterates and computes a sum does not necessarily need to require `ArrayList<String>`.

```java
// Illustrative method snippet; requires import java.util.Collection.
static int totalLength(Collection<String> values) {
    int total = 0;
    for (String value : values) {
        total += value.length();
    }
    return total;
}
```

An additional contract of this method is that `values` and each element are non-`null`. The `Collection<String>` type alone does not express that condition.

Grouping and common operations are described in [Collection API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html). Positional sequence semantics are described in [List API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html); uniqueness is described in [Set API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html).

## 4. Choosing an Implementation Class Based on Specific Requirements

After choosing the interface, consider the required behavior first, and only then weigh the costs.

| Typical Need | Illustrative Declaration | Points to Note |
| --- | --- | --- |
| Indexed list, frequent reads and appends at the end | `List<String> x = new ArrayList<>();` | Dynamic array; suitable for most general list cases |
| Specific reason requiring a linked list structure | `List<String> x = new LinkedList<>();` | Indexed access must traverse links |
| Membership testing, no iteration order guarantee needed | `Set<String> x = new HashSet<>();` | Depends on `equals`/`hashCode` |
| Deduplicate and preserve insertion order | `Set<String> x = new LinkedHashSet<>();` | Not sorted by value |
| Ordered set with lookups around a bound | `NavigableSet<Integer> x = new TreeSet<>();` | Relies on natural ordering or a `Comparator` |
| Single-threaded FIFO | `Queue<String> x = new ArrayDeque<>();` | `offer` at the tail, `poll` from the head in this usage |
| Stack or single-threaded double-ended operations | `Deque<String> x = new ArrayDeque<>();` | Use `push/pop` for LIFO or the double-ended API |
| Retrieve highest-priority element first | `Queue<Integer> x = new PriorityQueue<>();` | Queue head is by priority, not insertion order |
| Key lookup, no iteration order required | `Map<String, Integer> x = new HashMap<>();` | No guarantee on key order |
| Mapping preserving insertion order by default configuration | `Map<String, Integer> x = new LinkedHashMap<>();` | The class also has a separate access-order configuration |
| Mapping ordered by keys with navigation | `NavigableMap<Integer, String> x = new TreeMap<>();` | Key order depends on comparison |

This is a starting selection table, not a substitute for reading the contract of the API you are using.

- `HashSet` makes no guarantees about iteration order. "No guarantee" does not mean every iteration is random. The fact that a single run appears sorted does not constitute a guarantee. [HashSet API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html)
- `LinkedHashSet` preserves insertion order; re-adding an already-present element does not move it to the end. [LinkedHashSet API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html)
- `TreeSet` uses comparison to determine position and treats two elements whose comparison result is `0` as the same element in the tree structure. The comparison should be consistent with `equals` to satisfy the general `Set` contract. [TreeSet API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)
- `PriorityQueue` does not guarantee that its iterator traverses in priority order. When retrieving by priority, use the contract's head-removal operations. [PriorityQueue API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html)
- `ArrayDeque` does not accept `null` and is not synchronized for multi-threaded access. [ArrayDeque API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html)

For `HashMap`, `LinkedHashMap`, and `TreeMap`, refer respectively to [hash table lookup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html), [insertion order or access order](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html), and [ordered tree mapping](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html).

## 5. Do Not Swap Implementation Classes Just Because Both Compile

Consider the requirement: "remove duplicate codes while preserving first-appearance order".

```java
// Illustrative snippet inside a method; requires import java.util.*.
Set<String> codes =
        new LinkedHashSet<>(List.of("B", "A", "B"));
System.out.println(codes); // [B, A]
```

Changing `LinkedHashSet` to `HashSet` still type-checks, but no longer guarantees output order. Changing to `TreeSet` with natural ordering produces `[A, B]` for this data, which violates the requirement to preserve appearance order.

Therefore, substitutability must be evaluated along at least the following dimensions:

| Check Dimension | Question Before Swapping |
| --- | --- |
| Duplicates | Does the business logic need to keep multiple occurrences? |
| Ordering | Positional, insertion order, comparison order, or none required? |
| `null` | Can `null` keys, values, or elements be added? |
| Mutability | Are `add`, `remove`, `set`, or entry updates needed? |
| Concurrency | Will multiple threads access and modify it concurrently? |
| Equality relation | Based on `equals/hashCode` or a comparator? |
| Cost | Does the algorithm mainly iterate, look up, append, or randomly access? |
| Data ownership | Is this dedicated data, a copy, or a view of other data? |

Writing `Set<String>` alone does not fully convey the requirement to preserve insertion order. If that order is part of the API, document it clearly and test it with observable results. Do not rely on the reader seeing `new LinkedHashSet<>()` somewhere far away.

## 6. Interface Contracts Do Not Guarantee Every Operation Succeeds

### 6.1. Having a Method Does Not Mean the Object Allows Mutation

```java
// Illustrative snippet inside a method; requires import java.util.List.
List<String> fixed = List.of("A", "B");
// fixed.add("C"); // Compiles, but throws UnsupportedOperationException at runtime.
```

`List.of` creates a list that does not allow modification through `List` mutator operations and does not accept `null` elements. `List<String>` is not a "read-only" type: the API still includes `add`. The restriction comes from the returned object. Do not rely on the internal class name of the result of `List.of`.

Four easily confused cases:

| Creation | Add/Remove Elements | Replace Elements with `set` | Relationship to Source |
| --- | --- | --- | --- |
| `new ArrayList<>(source)` | Allowed | Allowed | Shallow copy of elements |
| `Arrays.asList(array)` | Cannot resize | Allowed | View backed by the array |
| `Collections.unmodifiableList(source)` | Not allowed through view | Not allowed | Changes to the source may appear through the view |
| `List.copyOf(source)` | Not allowed | Not allowed | Does not reflect structural changes to the source collection |

`List.copyOf` does not necessarily create a new object if the source already qualifies; do not use it to demand a distinct object identity. The copies above do not deep-clone elements. An element with mutable state can still be modified through another reference.

See the contracts for [List factories and copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)), [Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)), and [Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)).

### 6.2. Programming to an Interface Does Not Provide Thread Safety

`List<String> x = new ArrayList<>();` is no safer for concurrency than declaring the variable as `ArrayList<String>`. If multiple threads modify it concurrently, you must choose a synchronization mechanism or concurrent structure appropriate for the entire sequence of operations.

Even when individual operations are protected, a "check-then-act" sequence may still require its own atomic guarantee. This topic does not replace concurrency design.

### 6.3. `final` Does Not Make a Collection Immutable

```java
// Illustrative snippet inside a method; requires import java.util.*.
final List<String> names = new ArrayList<>();
names.add("Lan"); // Valid: mutates the object, does not reassign the variable.
// names = new LinkedList<>(); // Does not compile: reassigns a final variable.
```

Separate three things: reassigning the reference, mutating the collection's structure, and mutating an element's state.

## 7. Considering Performance Costs Without Breaking the Contract

`ArrayList` provides constant-time indexed `get/set`; appending at the end has amortized constant cost, though a specific append may require resizing the backing array. Inserting or removing in the middle of the list typically requires shifting elements. See [ArrayList API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

`LinkedList` must traverse links for indexed access. Inserting or removing at a position already located by an iterator differs from having to find that position first. Therefore, concluding "always choose `LinkedList` for frequent insertions/deletions" ignores traversal cost, node allocation, and memory access characteristics. [LinkedList API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html)

The following algorithm example exposes the assumption that indexed access is cheap enough:

```java
// Illustrative method snippet; requires import java.util.List.
static int totalByIndex(List<String> values) {
    int total = 0;
    for (int i = 0; i < values.size(); i++) {
        total += values.get(i).length();
    }
    return total;
}
```

With `LinkedList`, repeated `get(i)` calls can cause the total traversal cost to grow quadratically with the number of elements. If you only need to visit each element, the `for-each` approach in `totalLength` is more appropriate and does not impose random access.

When performance characteristics genuinely matter:

1. Determine the data size and operation frequencies.
2. Choose a structure that satisfies the correct behavior first.
3. Measure on representative data and environments if this is a bottleneck.
4. Keep performance assumptions explicit in the algorithm or contract.

Interfaces reduce coupling to class names; they do not erase differences in complexity.

## 8. Applying This to Parameters, Return Values, and Fields

### 8.1. Parameters: Request Only the Capabilities Needed

If you only iterate, accepting `Iterable<String>` is an option. If you need `size` or `contains`, `Collection<String>` may be appropriate. If you need positions, accept `List<String>`. If you need uniqueness, `Set<String>` expresses intent more clearly.

If a method mutates the caller's collection, state that explicitly:

```java
// Illustrative method snippet; requires import java.util.List.
// Requires a list that supports add; the method mutates the argument directly.
static void appendReviewTask(List<String> tasks) {
    tasks.add("review");
}
```

Accepting `List` does not mean the method can safely call `add` on every `List` object. An argument from `List.of(...)` does not satisfy the precondition "supports adding elements".

### 8.2. Return Values: Commit to the Behavior the Caller Needs

```java
// Illustrative method snippet; requires import java.util.*.
// Returns a new, modifiable list; does not mutate the source collection.
static List<String> copyTasks(Collection<String> source) {
    return new ArrayList<>(source);
}
```

`List` conveys sequence and position information, while `ArrayList` is kept as an implementation decision. Document that the result is modifiable and is a shallow copy.

If the API requires an unmodifiable result, you can choose `List.copyOf(source)`, while noting the `null` restriction. If you want to return a live view backed by the source data, that is a different contract and must be stated clearly.

Do not return an internal collection directly just because the return type is an interface. Callers can still invoke any mutating operations that the underlying object supports.

### 8.3. Fields: Keep Intent Stable

```java
// Illustrative field declaration inside a class; requires import java.util.*.
private final Map<String, Integer> counts = new HashMap<>();
```

Here the class owns the map and keeps the choice of `HashMap` internal. When changing the implementation class, you still must check iteration order, `null` handling, concurrency, and any behaviors the rest of the class relies on.

## 9. When Should You Use a Concrete Class Type?

Declaring with a concrete class is reasonable when the code genuinely needs capabilities specific to that class.

```java
// Illustrative snippet inside a method; requires import java.util.ArrayList.
ArrayList<String> buffer = new ArrayList<>();
buffer.ensureCapacity(1_000);
buffer.add("A");
```

You can confine this dependency to the construction step, then pass the reference to code that only needs the interface:

```java
// Illustrative snippet inside a method; requires import java.util.*.
ArrayList<String> buffer = new ArrayList<>();
buffer.ensureCapacity(1_000);
List<String> result = buffer;
```

Conversely, do not cast to a class just to get an API that already exists on the appropriate interface. If you need `ceiling`, declare `NavigableSet`; if you need `addFirst` on Java 17, check whether `Deque` is the right intent.

Avoid taking a `List` and blindly casting it to `ArrayList`. A method might receive a `LinkedList` or an unmodifiable list, causing the cast to fail with `ClassCastException`. Having to cast repeatedly is usually a sign that the chosen interface does not accurately express your needs.

### `var` Still Infers a Concrete Type

```java
// Illustrative snippet inside a method; requires import java.util.*.
var first = new ArrayList<String>(); // Inferred type is ArrayList<String>.
List<String> second = new ArrayList<>();
```

`var` does not automatically widen the inferred type to `List`. It is static type inference for local variables, not dynamic typing. When the goal is to express the `List` boundary right at the declaration line, writing it explicitly communicates that intent. [Local Variable Type Inference](https://docs.oracle.com/en/java/javase/17/language/local-variable-type-inference.html)

Generics must also be compatible: `List<String>` is not a subtype of `List<Object>`. The `<>` on the instantiation side is type-argument inference; it does not bypass type checking. Wildcards can help design more flexible parameters, and you do not need raw types to solve this problem.

## 10. Complete Program

Save under the exact name `CollectionChoiceDemo.java`. The program uses non-`null` elements and has no concurrency handling.

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.LinkedList;
import java.util.List;
import java.util.Map;
import java.util.NavigableSet;
import java.util.Queue;
import java.util.Set;
import java.util.TreeSet;

public final class CollectionChoiceDemo {
    static void appendReviewTask(List<String> tasks) {
        tasks.add("review");
    }

    static int totalLength(Collection<String> values) {
        int total = 0;
        for (String value : values) {
            total += value.length();
        }
        return total;
    }

    static List<String> copyTasks(Collection<String> source) {
        return new ArrayList<>(source);
    }

    public static void main(String[] args) {
        List<String> arrayTasks =
                new ArrayList<>(List.of("code", "test"));
        List<String> linkedTasks =
                new LinkedList<>(List.of("code", "test"));

        appendReviewTask(arrayTasks);
        appendReviewTask(linkedTasks);
        System.out.println("ArrayList: " + arrayTasks);
        System.out.println("LinkedList: " + linkedTasks);
        System.out.println("Total length: " + totalLength(arrayTasks));

        Set<String> uniqueInOrder =
                new LinkedHashSet<>(List.of("b", "a", "b"));
        System.out.println("Unique in order: " + uniqueInOrder);

        NavigableSet<Integer> scores =
                new TreeSet<>(List.of(30, 10, 20));
        System.out.println("Sorted: " + scores);
        System.out.println("At least 15: " + scores.ceiling(15));

        Queue<String> jobs = new ArrayDeque<>();
        jobs.offer("first");
        jobs.offer("second");
        System.out.println("Queue: " + jobs.poll() + ", " + jobs.poll());

        Deque<String> history = new ArrayDeque<>();
        history.push("open");
        history.push("edit");
        System.out.println("Stack: " + history.pop() + ", " + history.pop());

        Map<String, Integer> counts = new LinkedHashMap<>();
        counts.put("code", 1);
        counts.put("test", 2);
        counts.put("code", 3);
        System.out.println("Counts: " + counts);

        List<String> snapshot = List.copyOf(arrayTasks);
        arrayTasks.add("deploy");
        System.out.println("Snapshot: " + snapshot);
        System.out.println("Original: " + arrayTasks);
        try {
            snapshot.add("extra");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Snapshot add: unsupported");
        }

        List<String> editableCopy = copyTasks(snapshot);
        editableCopy.add("extra");
        System.out.println("Editable copy: " + editableCopy);
    }
}
```

Compile and run from the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 CollectionChoiceDemo.java
java CollectionChoiceDemo
```

A JDK with `javac` is required; `--release 17` instructs the compiler to check code and APIs against Java 17. The program was tested with this command on a newer JDK.

Stdout:

```text
ArrayList: [code, test, review]
LinkedList: [code, test, review]
Total length: 14
Unique in order: [b, a]
Sorted: [10, 20, 30]
At least 15: 20
Queue: first, second
Stack: edit, open
Counts: {code=3, test=2}
Snapshot: [code, test, review]
Original: [code, test, review, deploy]
Snapshot add: unsupported
Editable copy: [code, test, review, extra]
```

Key results to be able to explain:

- `appendReviewTask` works with two classes that both satisfy the modifiable-list requirement; it does not need to accept `ArrayList`.
- Total length is `4 + 4 + 6 = 14`.
- `LinkedHashSet` preserves the first appearance of `b` then `a`, removing the duplicate `b`.
- `TreeSet` sorts `10, 20, 30`; `ceiling(15)` returns `20`.
- `ArrayDeque` is viewed through `Queue` for FIFO usage; the same class is viewed through `Deque` for LIFO usage.
- `LinkedHashMap` in default mode preserves key insertion order. Updating `code` to `3` does not create a second key and does not move that key to the end.
- `snapshot` does not receive the `deploy` element later added to the source list; calling `add` on it is rejected.
- `copyTasks` creates a new modifiable list, so `editableCopy` can add `extra`.

None of the output relies on the unguaranteed iteration order of `HashSet` or `HashMap`.

## 11. Common Mistakes and Fixes

| Practice | Why It Is Problematic | How to Handle It |
| --- | --- | --- |
| Using `ArrayList` in every parameter | Forces callers to use one class even when the algorithm does not need it | Choose `List`, `Collection`, or `Iterable` according to requirements |
| Using `Collection` even where `get(index)` is needed | Loses the required API | Use `List` if position is part of the contract |
| Swapping `LinkedHashSet` to `HashSet` because both are `Set` | Loses the ordering guarantee | Check observable requirements before swapping |
| Assuming every `Queue` is FIFO | `PriorityQueue` uses a different policy | Choose and document the implementation class's policy |
| Calling `add` on the result of `List.of` | Mutating operations are unsupported | Create a modifiable copy if updates are needed |
| Using `final` to guarantee immutable data | Only prevents reassigning the variable | Design collection and element mutability separately |
| Casting every `List` to `ArrayList` | The actual object may be another class | Use the interface API or express the specific requirement |
| Choosing `LinkedList` just for "fast removal" | Ignores position-lookup cost and algorithm behavior | Review the full operation pattern and measure when needed |
| Returning an internal collection as `List` and assuming it is safe | Callers can still mutate the object | Choose copy/view explicitly and document ownership |
| Assuming interface declarations provide thread safety | Reference types do not provide synchronization | Choose an appropriate concurrency policy |

## 12. Selection Process for New Problems

1. **Write down data requirements:** are duplicates allowed, what order is needed, is key lookup required?
2. **List operations:** iteration, indexed access, membership lookup, both-ends access, lookup around a bound?
3. **Choose the interface:** sufficient operations and semantics, without pulling in a concrete class unnecessarily.
4. **Choose the implementation class:** consider storage structure, ordering, `null` handling, and each class's constraints.
5. **Define mutability and ownership:** mutate the source, create a copy, or return a view?
6. **Consider concurrency and cost:** based on actual usage.
7. **Test the contract:** ensure output, ordering, and exceptions remain valid if the class is swapped.

For example: "store unique product codes in entry order" leads to `Set` at the usage boundary, `LinkedHashSet` at instantiation, plus documentation and tests for entry order. "Find the lowest price not below a budget" leads to `NavigableSet` and an ordered implementation such as `TreeSet`.

## 13. Self-Check and Practice

### Questions

1. In `List<String> x = new ArrayList<>();`, what are the declared type and the actual class?
2. Why does `x.ensureCapacity(100)` not compile on Java 17?
3. Does a function that only computes total string length need to accept `ArrayList<String>`?
4. Does replacing `LinkedHashSet` with `TreeSet` preserve entry order?
5. Why does `List<String> x = List.of("A");` still disallow `add`?
6. Why can a `final List<String>` still have its contents modified?
7. Does switching from `ArrayList` to `LinkedList` guarantee that an index-based algorithm keeps the same performance?
8. What else must an API returning `List` state about mutability and relationship to the source?

### Exercises

- Replace `arrayTasks` in the program with `LinkedList` without modifying `appendReviewTask`. Explain which behaviors remain preserved.
- Use the same data `"B", "A", "B"` to create a `HashSet`, a `LinkedHashSet`, and a `TreeSet`. Only assert order in cases where the contract guarantees it.
- Write a function that returns a list of unique codes in first-appearance order. Choose a return type that expresses a positional result, and document uniqueness and mutability.
- Modify `copyTasks` to return an unmodifiable result using `List.copyOf`; rename and document the method to match the new contract.
- Write a test verifying that adding to a modifiable copy does not structurally modify the source collection.

### Answer Key

1. `List<String>` is the declared type; `ArrayList` is the actual class.
2. `ensureCapacity` is not part of the `List` API on Java 17.
3. No; `Collection<String>` or `Iterable<String>` may be sufficient depending on the operations and contract.
4. No; `TreeSet` sorts by comparison, not by entry order.
5. The object does not support mutating operations, even though the signature exists on the interface.
6. `final` only fixes the reference.
7. No; repeated indexed access can significantly change the cost.
8. Whether it is modifiable, whether it is a copy or a view, whether changes to the source are reflected in the result, and any element restrictions callers need to know.
