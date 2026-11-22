# Impact of Hash Functions and Comparators

## 1. Why Can the Same Collection Be Fast, Slow, or Produce Unexpected Results?

A collection does not inherently know whether two objects are "the same" according to business logic or which object should come first. It must invoke the rules provided by the data type or the program:

- `equals`: are two objects considered equal?
- `hashCode`: which candidate bucket in a hash table should an object be routed to?
- `Comparator.compare` or `Comparable.compareTo`: which object comes before, comes after, or is at the same level in ordering?

These rules affect both **correctness** and **performance** simultaneously. A hash function that returns the same number for every key may still satisfy the contract, yet make lookups slow. A comparator that only compares scores may sort a list as required, yet when used for a `TreeSet`, it causes two different people with the same score to be treated as the same element.

This article uses Java 17 to analyze two questions: which rule does a collection call, and how much does each call cost?

## 2. Understanding the Role of Each Rule

| Structure/Operation | Key Rule | Consequence |
| --- | --- | --- |
| `HashMap`, `HashSet` | `hashCode` to locate; `equals` to distinguish keys/elements | Good hashing reduces the number of candidates to examine |
| `LinkedHashMap`, `LinkedHashSet` | Also uses hashing and equality | Additional links maintain iteration order |
| `TreeMap`, `TreeSet` | Comparator or natural ordering | A comparison result of 0 determines key/element equivalence in the tree |
| `PriorityQueue` | Comparator or natural ordering to maintain the heap | Determines which element is polled first; does not deduplicate |
| `List.sort(comparator)` | Comparator | Determines ordering; the list still retains elements at the same level |

A standard `HashMap` does not accept a `Comparator` to sort keys. Conversely, improving `hashCode` does not make `TreeMap.get` faster because the tree's search path relies on comparisons. Do not choose an optimization target solely from the class name; identify the actual operation and the rule it uses.

## 3. Hash Functions: Contract Correctness First, Good Distribution Second

### 3.1. HashCode Is Not a Unique Identifier

A hash code is an `int` number. Multiple distinct objects can share the same hash code, which is called a collision. Therefore:

~~~text
a.equals(b) == true  =>  a.hashCode() == b.hashCode()
a.hashCode() == b.hashCode()  does not imply  a.equals(b) == true
~~~

If the information used for equality comparisons does not change, the hash code must remain stable within the same execution of a program. Java does not require the hash code to remain identical across different executions.

When overriding `equals`, you must override `hashCode` consistently with the same equality relation. Do not use random numbers or the current time to generate a hash code on each call. Also, do not rely solely on a hash code to decide whether two records are business duplicates. [Object.hashCode and Object.equals Contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html)

### 3.2. Two Different Kinds of Failures

**Contract violation:** two equal keys have different hash codes. The collection may look in a location that does not contain the stored key, causing `contains`, `get`, and `remove` to stop working as expected. This is a data and correctness bug.

**Poor distribution:** distinct keys all share the same hash code. The collection can still distinguish them using `equals`, but it must examine many more candidates. This is primarily a performance problem when the contract remains satisfied.

For example, a class that defines equality by `id` might return `id % 2` from `hashCode`. This function is consistent with equality but produces only two hash codes, so most distribution benefits disappear when the dataset grows large.

A good hash function for collections must preserve the contract, be cheap enough to compute, and distribute keys well for realistic data. Adding complex calculations does not necessarily make the program faster.

### 3.3. Cost of a Lookup

You can visualize it as:

~~~text
Lookup cost =
    cost of computing the hash code
  + cost of locating the bucket
  + cost of checking candidates in the bucket
~~~

If we denote:

- H as the cost of computing the hash code;
- E as the cost of a single `equals` call;
- q as the number of candidates to examine;

then an approximate model is H + O(q) + O(qE), plus related structural overhead. This is an analytical model, not a number of method invocations guaranteed by the API. An implementation may avoid calling `equals` by checking reference equality or hash codes first. [Map Specification on Lookup and equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)

When hash codes are well-distributed and the operations above take constant time, basic `HashMap` operations have an expected O(1) cost. If keys are very large, H or E may grow with key size; O(1) with respect to the number of entries n does not mean the operation is free.

### 3.4. Collisions Are Not Solved by Increasing Capacity Indefinitely

Increasing capacity can help when many different hash codes are landing in crowded buckets. If every key produces the exact same hash code, increasing capacity does not create any new distinction among them.

Java has mechanisms to mitigate the impact of collisions in certain situations, potentially leveraging the natural ordering of keys to break ties. That does not turn every poor hash function into a good one, nor is it a general guarantee that every lookup is O(1) or that the worst case is always O(log n).

Inserting keys can also trigger table resizing and redistribution of entries. The amortized cost of a sequence of insertions must be distinguished from the latency of a single insertion. An overly large capacity also wastes memory and can make table iteration slower. [Java 17 HashMap Performance Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html)

## 4. Mutable Keys and Hashing Cost

### 4.1. Do Not Mutate Identifying Information While a Key Is in a Table

Suppose you store a `Customer` object in a `HashSet`, where `equals` and `hashCode` use `customerId`. Later, `customerId` is modified.

The storage node remains in the bucket chosen at insertion time, whereas subsequent lookups compute the hash code from the new data. A lookup may fail to find the object even though iterating over the set still reveals it. Do not rely on any specific manifestation of this bug, because the collection contract has been violated.

Better approaches:

- Use immutable keys, such as a `long` ID or a type containing only immutable identifying components.
- If a key must change, remove it using the old key state before modifying it, then re-insert it.
- If you only change attributes that do not participate in equality/hashing, separately evaluate the impact on other structures such as trees or heaps.

A collection that disallows additions/removals can still contain mutable objects; a wrapper does not make the internal elements immutable. [Warning on Mutable Elements in Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html)

### 4.2. Caching Hash Codes Is Only Useful When Data Is Stable

If every call to `hashCode` has to scan a long list, fast table indexing does not eliminate that scanning cost. You can consider using a smaller key or precomputing the value when constructing an immutable object.

Do not cache the hash code of an object that can still mutate without a mechanism to maintain consistency. A stale hash code combined with an `equals` method based on new data is even more dangerous than a slow hash function.

A `record` helps represent data with `final` components, but it does not automatically enforce deep immutability on referenced objects. A component of type `List` still needs protection if the list's contents participate in identity.

## 5. Comparator: Ordering Must Be a Consistent Rule

### 5.1. Only the Sign of the Result Matters

`compare(a, b)` returns:

- A negative number if a comes before b.
- 0 if a and b are at the same level according to the comparator.
- A positive number if a comes after b.

It is not required to return exactly -1, 0, or 1. When checking the result, use `< 0`, `== 0`, or `> 0`.

A valid comparator must guarantee properties such as:

- Swapping the two arguments must invert the sign of the result.
- Transitivity: if a is greater than b and b is greater than c, then a must be greater than c.
- If a and b compare as 0, they must produce the same sign relationship when compared against any third object.
- The same data and the same rule must produce stable results.

Do not compare based on randomly changing state or the number of times the comparator has been called. An observation-only counter may increment on each call, but it must not alter the comparison result.

### 5.2. Using Subtraction Can Break Ordering

The following snippet fails for certain boundary values:

~~~java
java.util.Comparator<Integer> unsafe = (a, b) -> a - b;
~~~

With a = `Integer.MIN_VALUE` and b = 1, the subtraction overflows and yields a positive result, even though a is less than b.

Use `Integer.compare(a, b)` or `Comparator.comparingInt` for integer fields; for `long`, use `Long.compare` or `comparingLong`. Do not cast the difference of two `long` values to `int` to produce a comparison result.

Similarly, reversing an order with `reversed()` is clearer and safer than manually negating an arbitrary result: the negation of `Integer.MIN_VALUE` still overflows. [Comparator Contract and Combinator Methods](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html)

## 6. Comparing Equal to 0 Means Different Things Depending on Where It Is Used

### 6.1. TreeSet and TreeMap Use Ordering to Detect Duplicates

If a comparator only compares scores, two people with different IDs but the same score have `compare(a, b) == 0`.

In `TreeSet`, the element added second does not create a separate element. In `TreeMap`, a `put` with an equivalent-level key updates the existing mapping rather than creating a distinct key entry in the tree order.

Therefore, a comparator for a tree must be consistent with `equals` if it is to obey the general contract of `Set`/`Map`. "Comparing equal to 0" is not merely a way to display two objects next to each other. [TreeSet and Equality Relation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html), [TreeMap and Key Ordering](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html)

You can add a secondary tie-breaker using `thenComparing`. However, this is not an automatic fix for every model: if `equals` checks only ID while the comparator compares score first, two objects with the same ID but different scores can still compare as non-zero. You must clearly choose your identity model; sometimes it is better to store items by ID in a map and create a separate sorted list for presentation.

### 6.2. BigDecimal Is a Built-in Example in Java

`new BigDecimal("1.0")` and `new BigDecimal("1.00")`:

- Natural ordering comparison returns 0 because they have the same numeric value.
- `equals` returns `false` because they have different scales.

Consequently, under natural ordering, a `TreeSet<BigDecimal>` retains one element while a `HashSet<BigDecimal>` retains two. This is a documented difference that requires a business-logic decision before switching collections. [Java 17 BigDecimal Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)

### 6.3. PriorityQueue Does Not Use Compare Equal to 0 for Deduplication

Two tasks with the same priority level can coexist in a `PriorityQueue`. The queue does not guarantee that tied elements will be polled in insertion order. If you need priority first and FIFO on ties, add a monotonically increasing sequence number as a secondary criterion and maintain this number properly throughout the queue's lifetime.

The queue's `contains(x)` and `remove(Object)` search by equality, not "every object for which the comparator returns 0". Iterating via its iterator is also not guaranteed to traverse in priority order. [Java 17 PriorityQueue Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html)

### 6.4. Sorting Retains Elements and Has Its Own Stability Rule

Sorting a list by score does not remove people with the same score. `List.sort` is a stable sort: elements at the same level preserve their initial relative order.

That stability cannot be extrapolated to FIFO behavior in `PriorityQueue`, nor does it change how `TreeSet` determines duplicates. A comparator may be suitable for presenting a list while being unsuitable as an identifying order for a tree set. [List.sort Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator))

## 7. An Expensive Comparator Multiplies Structural Costs

If a single comparison has cost C, familiar bounds need to be re-read:

| Operation | Typical Number of Comparisons Analyzed | When Each Comparison Costs O(C) |
| --- | --- | --- |
| Lookup/insert/remove key in a balanced tree | O(log n) | The comparison cost portion is O(C log n) |
| Heap adjustment on offer/poll | O(log n) | The comparison cost portion is O(C log n) |
| Comparison-based sorting in the general case | O(n log n) | The comparison cost portion is O(C n log n) |

The table describes the comparison cost portion; it does not eliminate other costs such as allocation or backing-array growth when adding to a heap. For sorting, nearly sorted inputs and specific algorithms may perform fewer comparisons than the general bound.

If a comparator parses a date string, normalizes a name, queries a database, or reads a file on every invocation, C can dominate the entire workload. A comparator that looks like a single line of code can still be very expensive.

Common ways to improve:

1. Compute a stable sort key for each object before sorting.
2. Compare the precomputed keys inside the comparator.
3. Use a meaningful secondary criterion for ties.
4. Only update or recompute keys when the source data changes.

For example, if you need to sort by month from a validated date string, parsing n strings once and then comparing the month is typically much more reasonable than re-parsing on every `compare` call. Business rules must be preserved: time zone handling, locale, or Vietnamese diacritics cannot be arbitrarily replaced just to make a comparator faster.

`comparingInt` and `thenComparingInt` express primitive key comparisons clearly and avoid the boxing overhead of an object-key design for `int` keys. The actual impact should still be measured on the execution path being optimized.

## 8. Data and Comparison Rules Must Remain Stable While Stored

Inserting a task into a `PriorityQueue` and then mutating its priority field does not automatically reorder the heap. Similarly, mutating a field that participates in the comparator of a `TreeMap` key or `TreeSet` element can leave its current position inconsistent with the new ordering.

The proper way to update is to poll/remove the entry using its old state, mutate it or create a new object, and then re-insert it; when this operation cannot be guaranteed to be safe, rebuild the structure from the canonical data source. Do not alter the behavior of a tree's comparator by changing external configuration while the tree still holds data.

For `null`, there are two independent layers of rules:

- A comparator can be designed using `nullsFirst`/`nullsLast`.
- The collection itself may forbid `null`.

For instance, a comparator that handles `null` does not make `PriorityQueue` accept `null` elements. If natural ordering is used, you must also ensure that element types are mutually comparable.

## 9. Java 17 Demonstration Program

This example clearly separates hash collisions, duplicate equivalence in trees, priority ties, and integer overflow. It verifies behavioral outcomes rather than using a handful of elements to draw conclusions about speed.

Save as `HashComparatorDemo.java`:

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.PriorityQueue;
import java.util.Set;
import java.util.TreeSet;

public class HashComparatorDemo {
    record BadHashKey(int id) {
        @Override
        public int hashCode() {
            return 0; // Valid contract, very poor distribution.
        }
    }

    record Student(int id, int score) {
    }

    public static void main(String[] args) {
        Set<BadHashKey> keys = new HashSet<>();
        keys.add(new BadHashKey(1));
        keys.add(new BadHashKey(2));
        keys.add(new BadHashKey(3));

        System.out.println("colliding keys size = " + keys.size());
        System.out.println("contains id 2 = "
                + keys.contains(new BadHashKey(2)));

        List<Student> students = List.of(
                new Student(1, 90),
                new Student(2, 90),
                new Student(3, 80)
        );

        Comparator<Student> byScore =
                Comparator.comparingInt(Student::score).reversed();

        Set<Student> scoreOnly = new TreeSet<>(byScore);
        scoreOnly.addAll(students);
        System.out.println("score-only tree size = " + scoreOnly.size());

        Comparator<Student> byScoreThenId =
                byScore.thenComparingInt(Student::id);
        Set<Student> fullOrder = new TreeSet<>(byScoreThenId);
        fullOrder.addAll(students);

        List<Integer> orderedIds = new ArrayList<>();
        for (Student student : fullOrder) {
            orderedIds.add(student.id());
        }
        System.out.println("score-and-id tree size = " + fullOrder.size());
        System.out.println("ordered ids = " + orderedIds);

        PriorityQueue<Student> queue = new PriorityQueue<>(byScore);
        queue.addAll(students);
        System.out.println("priority queue size = " + queue.size());

        List<Integer> scores = new ArrayList<>();
        while (!queue.isEmpty()) {
            scores.add(queue.poll().score());
        }
        System.out.println("polled scores = " + scores);

        BigDecimal a = new BigDecimal("1.0");
        BigDecimal b = new BigDecimal("1.00");
        System.out.println("decimal equals = " + a.equals(b));
        System.out.println("decimal compare = " + a.compareTo(b));
        System.out.println("decimal hash set size = "
                + new HashSet<>(List.of(a, b)).size());
        System.out.println("decimal tree set size = "
                + new TreeSet<>(List.of(a, b)).size());

        Comparator<Integer> unsafe = (x, y) -> x - y;
        Comparator<Integer> safe = Integer::compare;
        System.out.println("unsafe sign = "
                + Integer.signum(unsafe.compare(Integer.MIN_VALUE, 1)));
        System.out.println("safe sign = "
                + Integer.signum(safe.compare(Integer.MIN_VALUE, 1)));
    }
}
~~~

Compile and run:

~~~shell
javac --release 17 HashComparatorDemo.java
java HashComparatorDemo
~~~

Exact stdout:

~~~text
colliding keys size = 3
contains id 2 = true
score-only tree size = 2
score-and-id tree size = 3
ordered ids = [1, 2, 3]
priority queue size = 3
polled scores = [90, 90, 80]
decimal equals = false
decimal compare = 0
decimal hash set size = 2
decimal tree set size = 1
unsafe sign = 1
safe sign = -1
~~~

Explanation:

- `BadHashKey` uses the record-generated `equals` based on `id`, while its hash code is always 0. All three IDs are still kept as distinct elements; a collision does not imply equality.
- The score-only tree treats the two students with a score of 90 as the same element. The comparator by score then ID aligns with this record because it examines both components.
- The priority queue retains all three students. The program only prints scores as they are polled, making no assumption about which of the two tied students is polled first.
- `BigDecimal` illustrates the difference between object equality and value equivalence under ordering.
- Subtraction returns the wrong sign at boundary values; `Integer.compare` handles it properly.

## 10. Evidence-Based Verification and Optimization

Before optimizing, verify the contracts against meaningful test cases:

- Two equal objects must have the same hash code; collisions between distinct objects remain permissible.
- A comparator must properly handle minimum/maximum values, equivalent-level objects, and chains of three objects to verify transitivity.
- Does comparing equal to 0 match the intended semantics of where it is used: list sorting, unique set, or priority queue?
- Can data participating in identity and ordering mutate while stored?
- Have rules for `null`, letter casing, locale, and missing data been defined?

When measuring performance, use realistic data distributions, including duplicate keys, many colliding keys, and objects with high comparison costs. Separate key preparation time, collection construction time, and query time if you need to understand each phase; when evaluating the end-to-end workload, sum all of them together.

You can count invocations of `hashCode`, `equals`, or `compare` to understand execution paths, but call counts are not wall-clock time. Logging inside every call will distort measurements. Also, do not treat the invocation count of a particular JDK version as an API contract.

A good hash function narrows down candidates; a good comparator directs searches and maintains order. Their quality is evaluated first by relational correctness, and second by total cost on real data.