# size, isEmpty, contains and the Meaning of Return Values

When working with collections, three questions come up very frequently:

- How many elements are currently present?
- Are there any elements at all?
- Is a specific value present in the collection?

Java provides `size()`, `isEmpty()`, and `contains(Object)` to answer those three questions. Although all three are query operations, they carry different meanings. Understanding their return values correctly helps avoid confusing the number of elements with capacity, existence with occurrence count, or two objects with equal content with the same reference.

This lesson presents the general contract in the Java Collections Framework and the points to check in concrete implementations. The complete example uses Java 17 or later.

## 1. Three methods, three kinds of information

The signatures in `Collection<E>` are:

```java
int size();
boolean isEmpty();
boolean contains(Object o);
```

These are API signatures, not a standalone Java program.

| Method | Question answered | Return value |
| --- | --- | --- |
| `size()` | How many elements currently belong to the collection? | An `int` integer |
| `isEmpty()` | Is the collection empty? | `true` if there are no elements; otherwise `false` |
| `contains(o)` | Is there at least one element matching the value `o`? | `true` if present; `false` if not, for valid input |

A list with 10 elements can still return `false` for `contains("Java")`: count says nothing about content. A list containing only a single `null` element is not empty: it has one slot occupied by a valid element of that implementation.

The operations above report the state of the queried object. They do not load data from a database, do not automatically filter elements by business conditions, and do not count elements that the program "intends" to add later. [Java 17: Collection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html)

## 2. size(): current number of elements

### 2.1. Size is not capacity

In an `ArrayList`, the internal array capacity and the current number of elements are two different quantities:

```java
List<String> names = new ArrayList<>(20);

System.out.println(names.size()); // 0
names.add("Lan");
System.out.println(names.size()); // 1
```

This is an illustrative snippet inside a method, with `java.util.List` and `java.util.ArrayList` imported.

The argument `20` prepares the initial capacity. It does not add 20 elements, nor does it create 20 `null` elements for the user to access. Immediately after initialization, `names.get(0)` is still invalid because the list has no elements yet.

Do not infer size from planned capacity or from the number of slots in the backing array. Only `size()` describes the number of elements belonging to the list according to the API. [Java 17: ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html)

### 2.2. Duplicates and null are still counted according to the structure

With a list that allows duplicate values and `null`:

```java
List<String> names = new ArrayList<>();
names.add("Lan");
names.add("Lan");
names.add(null);

System.out.println(names.size()); // 3
```

The two occurrences of `"Lan"` occupy two different positions. The `null` element occupies the third position. `size()` does not automatically deduplicate, ignore `null`, or count unique people.

If the data is transferred to a `HashSet`, the set structure keeps only one representative for each value according to its equality rules:

```java
Set<String> unique = new HashSet<>(names);
System.out.println(unique.size()); // 2: "Lan" and null
```

These snippets require importing the types used and placing them inside a method. The results differ because of the actual contents of the two different structures; `size()` does not carry two arbitrary meanings.

If you need to count how many times a value appears, `size()` is not the answer. For example, the list `["Lan", "Lan", null]` has size 3, while `"Lan"` appears 2 times. You can use a loop or a counting operation using the exact comparison required.

### 2.3. Size reflects completed changes

After removing one occurrence from the list:

```java
names.remove("Lan");
System.out.println(names.size());          // 2
System.out.println(names.contains("Lan")); // true
```

The list still has one `"Lan"` and one `null`. Removing one element does not mean removing every element equal to it.

After `clear()`, if the operation is supported by the implementation and succeeds, the collection has no remaining elements, so `size()` is 0.

### 2.4. The int type has a limit

The `Collection.size()` contract returns `Integer.MAX_VALUE` if the number of elements exceeds that representable limit. Therefore, this API should not be used as an unbounded `long` counter.

This is a contract limit, not a claim that a specific collection can actually hold that many elements in memory. For problems with extremely large datasets, both the storage structure and the actual counting API must be considered. [Java 17: Collection.size](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#size())

## 3. isEmpty(): are there any elements or not?

### 3.1. A boolean value expresses intent directly

`isEmpty()` returns:

- `true`: the collection has no elements.
- `false`: the collection has at least one element.

In a stable state, `collection.isEmpty()` and `collection.size() == 0` give the same answer. When you only need to know whether there is any data, `isEmpty()` expresses that intent more directly:

```java
if (orders.isEmpty()) {
    System.out.println("Chưa có đơn hàng");
}
```

This is an illustrative snippet; `orders` is an initialized collection. There is no need to compute the total count just to check for emptiness.

However, do not conclude that `isEmpty()` always has constant cost for every class, or is always faster than `size()` in every case. The interface specifies the meaning; the cost depends on the implementation.

### 3.2. Empty is different from null

The following three states are different:

```java
List<String> missing = null;
List<String> empty = new ArrayList<>();

List<String> oneNull = new ArrayList<>();
oneNull.add(null);
```

| Variable | Is there a list object? | Size |
| --- | --- | --- |
| `missing` | No | Cannot call `size()` or `isEmpty()` |
| `empty` | Yes | 0 |
| `oneNull` | Yes | 1 |

Calling `missing.isEmpty()` throws `NullPointerException`: there is no object to receive the call. Meanwhile, `oneNull.isEmpty()` is `false`.

If an API specifies that it always returns a collection, it should return an empty collection when there are no results. Callers can then use `isEmpty()` without having to guess what `null` means.

If you are integrating with an API that may return `null`, handle it according to its specific contract:

```java
if (items == null || items.isEmpty()) {
    System.out.println("Không có danh sách để xử lý");
}
```

This is an illustrative snippet for a business case that intentionally treats the two states as equivalent. Do not merge `null` and empty automatically if they represent two different states, such as "not yet loaded" and "loaded with no results".

## 4. contains(): asks about existence, not position or count

### 4.1. True means there is at least one matching element

With the list `["Lan", "Lan", null]`:

| Call | Result |
| --- | --- |
| `contains("Lan")` | `true` |
| `contains("Minh")` | `false` |
| `contains(null)` | `true`, because this `ArrayList` contains `null` |

A `true` result does not tell you:

- How many elements equal the searched value.
- Which index the element is at.
- When the element was added.
- Whether the stored object is the exact reference passed in.

To know the position in a `List`, you need an API like `indexOf`. To retrieve the matching object, you need to search for and return that object. To count, you need a counting operation.

Do not call `contains` and then search for the same element again if you can perform the lookup and retrieve the result in a single pass; doing so both avoids duplicate work and makes the code's intent clearer.

### 4.2. Value equality is different from reference identity

A general mental model for reading the `contains(o)` contract is: whether there exists an element `e` such that `Objects.equals(o, e)` is true.

With strings:

```java
List<String> names = new ArrayList<>();
names.add("Lan");

String query = new String("Lan");
System.out.println(names.contains(query)); // true
```

Even though `query` is a new object, `String.equals` compares contents, so `contains` still returns `true`.

For custom classes, the result depends on that class's equality rules. A class that does not override `equals` typically still uses reference equality from `Object`. Two objects whose fields look identical do not automatically become equal.

Nor should the contract description be read as requiring every class to call `equals` on every element. A hash-based structure may use hash codes to narrow down candidates first. The meaning of the result and the execution algorithm are two separate things to distinguish.

### 4.3. Contains accepts Object, so queries of a different type can compile

The signature is `contains(Object o)`, not `contains(E o)`. Therefore:

```java
List<Integer> numbers = List.of(1, 2, 3);

System.out.println(numbers.contains(1));   // true
System.out.println(numbers.contains(1L));  // false
```

`1` is boxed into an `Integer`; `1L` is boxed into a `Long`. `Integer.equals` does not consider a `Long` equal to it merely because they share the same numeric value.

This is not a "find the number 1 regardless of type" operation. If your data has multiple numeric types, normalize the type or write an explicit comparison condition before using the structure.

Do not assume that a mismatched-type query always returns `false`. Some collections may throw `ClassCastException` when the object is incompatible with the comparison mechanism or supported element type.

### 4.4. HashSet requires consistent equals and hashCode

When searching in a `HashSet`, the hash code helps locate the candidate bucket and the equality comparison confirms the matching value.

Two essential rules:

1. If `a.equals(b)` is `true`, `a.hashCode()` and `b.hashCode()` must be equal.
2. Do not mutate the fields used by `equals`/`hashCode` while the object is an element in a hash set.

If a class violates the contract or a key changes after insertion, a situation can arise where the element is still visible during iteration but `contains` fails to find it as expected. When diagnosing this, check the object's equality model rather than suspecting only the collection.

Having the same hash code does not guarantee equality: different values can collide on hash code and still coexist. [Java 17: HashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html)

### 4.5. TreeSet uses comparison ordering to find elements

`TreeSet` uses natural ordering or a comparator. In this structure, two elements whose comparison result is 0 are treated as equivalent for lookup and deduplication.

An easy-to-observe example is `BigDecimal`:

```java
BigDecimal first = new BigDecimal("1.0");
BigDecimal query = new BigDecimal("1.00");

System.out.println(first.equals(query));    // false
System.out.println(first.compareTo(query)); // 0
```

`BigDecimal.equals` considers both value and scale; `compareTo` compares by numeric value. Therefore:

```java
List<BigDecimal> list = List.of(first);
Set<BigDecimal> tree = new TreeSet<>();
tree.add(first);

System.out.println(list.contains(query)); // false
System.out.println(tree.contains(query)); // true
```

These illustrative snippets require importing `BigDecimal`, `List`, `Set`, and `TreeSet`.

The takeaway is not that "`contains` is unreliable", but that you must know the equality rules of both the data and the structure. For a tree set, an ordering consistent with `equals` is required for its behavior to fully obey the general `Set` contract. Do not choose a comparator just because it sorts nicely without considering that it also determines uniqueness. [Java 17: TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html), [BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)

### 4.6. Contains null does not always return false when a collection does not support null

A collection that forbids `null` may throw `NullPointerException` when `contains(null)` is called, or return `false` in cases permitted by its contract.

Therefore, do not rely on a generic "just call `contains(null)` and see" check as a substitute for knowing the input contract. The `ArrayList` example in this lesson allows `null`, but that expectation should not be applied to every other collection.

These exceptions do not turn `false` into an error indicator. `false` means not found according to the contract; an exception means the request cannot be validly processed in that situation.

## 5. With Map, you must specify whether you are searching for a key or a value

`Map<K,V>` does not extend `Collection<E>`, yet it also has `size()` and `isEmpty()`:

- `size()` counts the number of key–value mappings.
- `isEmpty()` asks whether there are any mappings.
- `containsKey(key)` asks whether the key exists.
- `containsValue(value)` asks whether at least one mapping points to that value.

```java
Map<String, String> notes = new HashMap<>();
notes.put("A", null);

System.out.println(notes.size());              // 1
System.out.println(notes.isEmpty());           // false
System.out.println(notes.containsKey("A"));    // true
System.out.println(notes.containsValue(null)); // true
```

The snippet uses `HashMap`, which allows `null` values. A mapping to `null` is still a mapping.

Do not write `map.get(key) != null` as a general existence check when the map allows `null` values: the key may already exist and be mapped to `null`.

`containsKey` and `containsValue` do not necessarily have the same cost either. A map organized for key lookup typically does not have an equivalent index by value. Ask the right question instead of treating the two methods as interchangeable. [Java 17: Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)

## 6. The general contract does not guarantee all queries are equally fast

| Structure | Typical `size()` | Typical `contains()` |
| --- | --- | --- |
| `ArrayList` | Reads the tracked count | Linear scan in the general case |
| `LinkedList` | Reads the tracked count | Traverses nodes to search |
| `HashSet` | Reads the tracked count | Favorable on average when hash codes distribute well |
| `TreeSet` | Reads the tracked count | Follows a tree search path, logarithmic cost |
| `ConcurrentLinkedQueue` | Must traverse to count | Must search through the queue's data |

The table highlights differences in execution paths. The cost of `equals`, comparators, hash codes, and memory access also affects actual runtime.

`AbstractCollection` provides an `isEmpty()` implementation based on `size() == 0` and a `contains` implementation based on iteration. Concrete classes may override them. Do not use the default implementation to infer that all collections have the same performance. [Java 17: AbstractCollection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractCollection.html)

For example, with a large list, calling `contains` repeatedly for each input element can incur high total cost. If the problem is mainly membership testing and duplicates do not need to be preserved, a set built once may be more suitable. Before switching, verify equality rules and ordering requirements.

## 7. Queries do not automatically protect concurrent operation sequences

### 7.1. A result true at check time may no longer be true at use time

The following snippet has a gap between the two operations:

```java
if (!queue.isEmpty()) {
    String job = queue.poll();
    // Another thread may have taken the last element before poll().
}
```

If `queue` is consumed by multiple threads, it can become empty after the check. For a queue that does not allow `null` elements, you can usually call the retrieval operation first and then process the result:

```java
String job = queue.poll();
if (job != null) {
    process(job);
}
```

This is a processing-flow snippet, not a standalone program: `queue` and `process` are supplied by the application. If you want to wait when empty, you may need an API such as `BlockingQueue.take()`, rather than polling repeatedly.

Similarly, `if (!list.contains(x)) list.add(x)` does not guarantee uniqueness when two threads run concurrently. You must use an operation that satisfies atomicity requirements or a synchronized region covering the entire sequence.

### 7.2. Size may not be a system-wide snapshot

The `ConcurrentLinkedQueue` documentation notes that `size()` must traverse the queue and may be inaccurate if the queue changes during counting. Do not use its result to enforce an atomic capacity limit on your own:

```java
// Not sufficient to guarantee the queue does not exceed 100 elements under concurrent writes.
if (queue.size() < 100) {
    queue.offer(job);
}
```

If you need to limit the number of pending jobs, choose a queue with a capacity bound and an insertion mechanism suited to that requirement.

Query methods also do not make a regular `ArrayList` or `HashSet` safe when another thread is modifying it without coordination. Do not call `size()` as a form of "implicit synchronization" or to guarantee visibility of all changes. [Java 17: ConcurrentLinkedQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html)

## 8. Complete Java 17 program

Save the following code to `CollectionQueriesDemo.java`:

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public class CollectionQueriesDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>(20);
        System.out.println("initial size = " + names.size());
        System.out.println("initial empty = " + names.isEmpty());

        names.add("Lan");
        names.add("Lan");
        names.add(null);
        System.out.println("list size = " + names.size());
        System.out.println("list empty = " + names.isEmpty());
        System.out.println("contains Lan = " + names.contains(new String("Lan")));
        System.out.println("contains null = " + names.contains(null));
        System.out.println("contains Minh = " + names.contains("Minh"));

        Set<String> unique = new HashSet<>(names);
        System.out.println("set size = " + unique.size());

        names.remove("Lan");
        System.out.println("after one removal size = " + names.size());
        System.out.println("after one removal contains Lan = " + names.contains("Lan"));

        List<Integer> numbers = List.of(1, 2, 3);
        System.out.println("contains Integer 1 = " + numbers.contains(1));
        System.out.println("contains Long 1 = " + numbers.contains(1L));

        BigDecimal first = new BigDecimal("1.0");
        BigDecimal query = new BigDecimal("1.00");
        List<BigDecimal> prices = List.of(first);
        Set<BigDecimal> sortedPrices = new TreeSet<>();
        sortedPrices.add(first);
        System.out.println("decimal equals = " + first.equals(query));
        System.out.println("decimal comparison = " + first.compareTo(query));
        System.out.println("price list contains = " + prices.contains(query));
        System.out.println("price tree contains = " + sortedPrices.contains(query));

        Map<String, String> notes = new HashMap<>();
        notes.put("A", null);
        System.out.println("map size = " + notes.size());
        System.out.println("map empty = " + notes.isEmpty());
        System.out.println("map contains key A = " + notes.containsKey("A"));
        System.out.println("map contains value null = " + notes.containsValue(null));

        names.clear();
        System.out.println("cleared size = " + names.size());
        System.out.println("cleared empty = " + names.isEmpty());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 CollectionQueriesDemo.java
java CollectionQueriesDemo
```

Stdout:

```text
initial size = 0
initial empty = true
list size = 3
list empty = false
contains Lan = true
contains null = true
contains Minh = false
set size = 2
after one removal size = 2
after one removal contains Lan = true
contains Integer 1 = true
contains Long 1 = false
decimal equals = false
decimal comparison = 0
price list contains = false
price tree contains = true
map size = 1
map empty = false
map contains key A = true
map contains value null = true
cleared size = 0
cleared empty = true
```

Each group of results demonstrates a specific point:

1. An initial capacity of 20 creates no elements, so the initial size is 0 and it is empty.
2. Two identical strings plus one `null` give the list 3 elements, whereas the hash set has 2 values.
3. A new `String` object is still found by content.
4. Removing `"Lan"` once decreases the size without removing every occurrence.
5. `Integer(1)` is not equal to `Long(1)` according to the `equals` method of their respective wrapper classes.
6. `BigDecimal` illustrates the difference between `equals` and natural ordering when searching in a tree set.
7. A mapping with a `null` value still makes the map non-empty.
8. After clearing all elements, `size()` and `isEmpty()` reflect the empty state.

The program does not print the element order of `HashSet`, so the output does not depend on an iteration order that the class does not guarantee.

## 9. Common mistakes and how to check

| Misconception | Actual fact to remember |
| --- | --- |
| `new ArrayList<>(100)` has size 100 | It only prepares capacity; the initial size is 0 |
| `isEmpty()` can check whether a variable is `null` | Calling a method on a `null` reference throws an error |
| Having one `null` element means the list is empty | It still has one element |
| `contains` returns the occurrence count or position | It only returns presence/absence |
| Two objects with different references cannot be found by `contains` | Value equality rules may consider them equal |
| `contains(1L)` must find the `Integer` value 1 | Wrapper numeric types and `equals` rules still matter |
| Every collection handles `contains(null)` the same way | You must check the class's policy |
| `contains` always scans everything and calls `equals` | Structures may use hashing or comparison ordering |
| A `false` result proves nobody adds the element right afterward | Queries do not lock state for subsequent operations |
| `size()` of every collection is O(1) | Some structures must traverse to count |

When a query returns an unexpected result, check in order: what the collection actually contains, the type of the query object, the `equals`/`hashCode` or comparator rules, the `null` policy, and then whether another thread is modifying the data.

## 10. Self-practice

1. An `ArrayList<String>` contains `"A"`, `"A"`, `null`. What do `size()`, `isEmpty()`, and `contains("A")` return?  
   **Answer:** 3, `false`, `true`.

2. Remove exactly one occurrence of `"A"` from that list. Is `contains("A")` still true?  
   **Answer:** Yes, because one `"A"` element still remains.

3. A `HashMap<String, String>` has key `"x"` mapped to `null`. Is the map empty?  
   **Answer:** No. The map has one mapping; `containsKey("x")` is `true`.

4. Why does `List.of(1, 2).contains(1L)` return `false`?  
   **Answer:** The elements are `Integer`, while the query is `Long`; having the same numeric value does not make them equal according to `equals`.

5. Why should you not use `queue.size() < limit` followed by `offer` to enforce capacity in a multithreaded system?  
   **Answer:** Checking and adding are two separate operations; the state can change between them. You need a structure or mechanism that enforces the limit atomically.

These three methods express three distinct intents: counting, checking emptiness, and checking membership. Each time you use them, identify the exact question being answered and the scope within which the result remains meaningful.
