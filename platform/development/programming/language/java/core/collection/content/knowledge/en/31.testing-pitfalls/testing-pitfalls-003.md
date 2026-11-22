# Testing Insertion Order, Sorted Order, and Priority Order

## 1. “Right Elements” Does Not Always Mean “Right Order”

A result containing all of `A`, `B`, `C` can still be wrong if the caller needs to receive `B`, `A`, `C`. Conversely, a test that forces the order `A`, `B`, `C` can be wrong if the collection does not promise that order.

When testing collections, distinguish three meanings:

- **Insertion order:** the order in which elements or keys are added, according to the data structure's rules.
- **Sorted order:** the order determined by `Comparable` or `Comparator`.
- **Priority order:** the order in which elements are retrieved from a queue according to priority rules.

With data inserted sequentially as `30`, `10`, `20`:

| Structure and Observation Action | Expected Order |
| --- | --- |
| Iterating over `LinkedHashSet` | `30, 10, 20` |
| Iterating over `TreeSet<Integer>` using natural ordering | `10, 20, 30` |
| Repeatedly calling `poll()` on `PriorityQueue<Integer>` using natural ordering | `10, 20, 30` |
| Iterating over `PriorityQueue` with an iterator | No guarantee of iterating as a sorted sequence |

The last two rows are especially easy to confuse. `PriorityQueue` guarantees selecting the head element of the queue according to priority order; it does not turn every way of observing its contents into a sorted sequence.

The testing goal is to protect **the order at the exact observation point committed by the API or business logic**, while also checking for all elements and their occurrence counts.

## 2. Identify the Contract Before Choosing an Assertion

A requirement like “return results in the right order” is still missing information. Clarify:

1. Is it the order of elements, keys, or values?
2. Is it observed via an iterator, an output list, or a sequence of element retrieval-and-removal operations?
3. Is it ascending or descending, and by which attribute?
4. If two elements are tied, is there a secondary rule (tie-breaker)?
5. Does re-adding, updating, or accessing an element change its position?
6. Is the check allowed to consume the source structure?

For example, two different queue contracts:

```text
Contract A:
    a higher priority number is processed first;
    jobs with the same priority are retrieved in any order.

Contract B:
    a higher priority number is processed first;
    if priorities are equal, the job submitted earlier is processed first.
```

You must not use an assertion requiring a specific order among tied jobs when only Contract A applies. With Contract B, there must be a mechanism representing submission order, and it must be tested.

In the examples in this article, a larger `priority` means higher priority. This is a business choice for the example, not how Java automatically interprets a field named `priority`.

## 3. Testing Insertion Order

### 3.1. Choose Inputs That Distinguish Insertion Order from Sorted Order

If you always insert `A`, `B`, `C`, a structure that accidentally sorts in ascending order will still return the expected sequence. Use data such as `B`, `A`, `C`.

With `LinkedHashMap` in default insertion order:

```text
put(B, 2)
put(A, 1)
put(C, 3)

Expected key iteration order: B, A, C
```

Replacing the value of an existing key `A` does not move that key to the end. However, removing the key and then adding it back is a different sequence of operations: the key is newly added at the end. [Java 17 LinkedHashMap Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html)

Therefore, include distinguishing test cases:

| Action After Having `B, A, C` | Expected Key Order in Insertion-Order Mode |
| --- | --- |
| `put(A, new_value)` | `B, A, C` |
| `get(B)` | `B, A, C` |
| `remove(A)`, then `put(A, ...)` | `B, C, A` |
| Add key `D` | `B, A, C, D` |

Test results must follow the exact state prior to each test case. Create separate data or reinitialize when test cases are not designed to run sequentially on shared state.

### 3.2. LinkedHashSet: Re-adding a Duplicate Is Not Remove-Then-Reinsert

With `LinkedHashSet`, adding an element that already exists does not change the order. The source `B, A, B, C` produces the iteration order `B, A, C`. If `A` is removed and then added back, the order becomes `B, C, A`. [Java 17 LinkedHashSet Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html)

A test case that only compares sets of values cannot detect this ordering bug. Collect the iteration order into a `List` for comparison.

### 3.3. Access-Order Is a Different Mode

`LinkedHashMap` has a constructor that enables access order:

```java
Map<String, Integer> cache = new LinkedHashMap<>(16, 0.75f, true);
```

This illustrative snippet requires importing `java.util.Map` and `java.util.LinkedHashMap`. In this mode, a successful `get` can move the accessed entry toward the most-recently-accessed end. For example, after inserting `B, A, C`, calling `get(B)` yields the iteration order `A, C, B`.

Do not apply insertion-order expectations to a map created in access-order mode. When testing a structure used as a cache, also remember that a read call made to “check a value” can mutate the ordering state before the next assertion.

## 4. Testing Sorted Order

### 4.1. TreeSet and TreeMap Rely on Comparison Rules

`TreeSet` iterates according to natural ordering or a configured comparator. `TreeMap` sorts by **key**, and does not automatically sort by value. [TreeSet Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html), [TreeMap Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html)

A well-discriminating test case:

```text
Mappings inserted:
    B -> 2
    A -> 3
    C -> 1

Iterating TreeMap by natural key order:
    keys:   A, B, C
    values: 3, 2, 1
```

If you only use `A->1`, `B->2`, `C->3`, it is hard to detect confusion between “sorted by key” and “sorted by value”.

Test cases should include already-ascending, already-descending, and mixed-order inputs, but expectations must all follow the comparator. There is no need to preserve insertion order in a structure committed to sorting.

### 4.2. Checking Comparison Direction and Secondary Rules

For integers using natural ordering, ascending order is typically expected. For structures using `Comparator.reverseOrder()`, the expected order changes to descending.

For domain objects, include at least:

- Two elements that differ in the primary attribute.
- Two elements that are equal in the primary attribute but differ in the secondary attribute.
- Meaningful boundary values, if the comparator handles numbers or special data.

Do not write numeric comparators using subtraction like `a.priority() - b.priority()`. The difference can overflow an integer and invert the comparison sign. Use `Integer.compare`, `Comparator.comparingInt`, or an appropriate combinator function. The `Comparator` API provides methods to build, reverse, and chain comparison rules. [Java 17 Comparator Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html)

### 4.3. compare Returning 0 Has Special Meaning for Tree Structures

`TreeSet` uses comparison results to identify elements occupying the same position in the set. If a comparator only compares string length, `"AA"` and `"BB"` compare as `0`; the set may keep only one of the two even though `String.equals()` returns false.

This can cause a test suite to fail not because the sequence is misordered, but because elements were lost under an incompatible contract. Check both size/count and contents, not just ascending order.

For sorted sets/maps that need to obey the general `Set`/`Map` contract, the ordering rule must be consistent with `equals`. If the problem requires keeping multiple distinct objects that share the same primary attribute value, you may need a sufficiently distinguishing secondary rule or a different structure such as a sorted list.

### 4.4. The Stability of List.sort Does Not Automatically Carry Over to Queues

`List.sort` guarantees a stable sort: elements that compare equal preserve their relative order prior to sorting. [Java 17 List.sort Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator))

For example, `B` and `C` have the same priority, with `B` appearing before `C` in the source list. A stable sort by priority alone preserves that relative order.

This is a guarantee of list sorting, not a reason to assume `PriorityQueue` also processes tied elements in insertion order. Each data structure must be tested according to its own guarantees.

## 5. Testing Priority Order via Retrieval Sequences

### 5.1. The Smallest Element According to the Comparator Is Retrieved First

In `PriorityQueue`, the head element is the smallest element according to natural ordering or the configured comparator. If multiple tied elements sit at the head, the queue does not promise to pick them in insertion order. The iterator is not guaranteed to traverse in priority order. [Java 17 PriorityQueue Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html)

With integers and natural ordering:

```text
Inserted: 30, 10, 20, 10
Repeated poll: 10, 10, 20, 30
```

With the convention “higher priority number runs first”, the comparator needs to reverse the direction of that attribute:

```java
Comparator<Job> byPriority = Comparator.comparingInt(Job::priority).reversed();
```

This is an illustrative snippet using the `Job` type from the full program below. A large priority value becomes the “smaller” element under the reversed comparator, so it is retrieved first.

### 5.2. Do Not Test Using the Heap's Iterator Order

The following approaches only obtain internal traversal order and do not represent the priority retrieval sequence:

```java
new ArrayList<>(queue);
queue.toArray();
queue.stream().toList();
```

They are illustrative expressions, not valid assertions for `poll()` order. Even if a single run happens to produce a sequence that looks sorted, do not turn that observation into an API guarantee.

If you need to test the job retrieval process, actually retrieve items using the operation that production code uses. If you only need to display a sorted view of the values, that is a different goal and should be specified separately.

### 5.3. Inspect via a Copy to Preserve the Source Queue

`poll()` removes elements, so a test helper can create a copy of the `PriorityQueue` and drain the copy. The constructor accepting a `PriorityQueue` preserves the source's ordering rule.

```java
static <E> List<E> pollOrder(PriorityQueue<E> source) {
    PriorityQueue<E> copy = new PriorityQueue<>(source);
    List<E> result = new ArrayList<>();
    while (!copy.isEmpty()) {
        result.add(copy.poll());
    }
    return result;
}
```

This method snippet requires the corresponding imports shown in the full program. It is intended for cases without concurrent modification and where elements do not mutate their comparison attributes during inspection.

The copy retains element references; it does not deep-copy objects. Do not mutate the priority inside an object and expect the queue to reposition that object automatically. The example in this article uses a record that is immutable with respect to comparison fields to avoid breaking this assumption.

## 6. Tied Elements: Two Assertion Strategies

### 6.1. No Secondary Order Required: Assert at the Exact Guarantee Level

Suppose `B` and `C` both have priority `5`, `A` and `E` both have priority `2`, and `D` has priority `1`. If the contract only specifies descending priority, the following sequences are both valid:

```text
B, C, A, E, D
C, B, E, A, D
```

One verification approach consists of two conditions:

1. Consecutively retrieved elements never invert order under the comparator.
2. The multiset of elements (including occurrence counts) exactly matches the input.

Checking only the first condition fails to detect missing elements. Simply converting to a `Set` to check the second condition can lose duplicate element information. A frequency map counting occurrences is appropriate when element equality accurately reflects the identity under test.

You can verify that the priority sequence is `[5, 5, 2, 2, 1]` and separately verify that all jobs are present; do not force an ID order among tied jobs.

### 6.2. Tie-Breaking by Submission Order Required: Include It in the Comparator

You can attach a monotonically increasing sequence number when submitting jobs:

```java
Comparator<Job> byPriorityThenSequence =
        Comparator.comparingInt(Job::priority).reversed()
                .thenComparingLong(Job::sequence);
```

This comparator has two rules:

1. Descending priority.
2. If priorities are equal, ascending sequence.

To express submission order, `sequence` must be assigned at the exact time/coordination point of job submission and be sufficiently distinct within the scope of the queue. Do not use duplicate sequence numbers while still promising a strictly deterministic order. Issuing sequence numbers across multiple threads is a separate design requirement; the example here processes data on a single thread.

Pay attention to where `reversed()` is called:

```java
Comparator.comparingInt(Job::priority).reversed()
        .thenComparingLong(Job::sequence);
```

differs from reversing the entire comparator after chaining `sequence`. Reversing the whole comparator also reverses the direction of the secondary rule. Testing with multiple elements sharing the same priority helps catch this mistake.

## 7. Java 17+ Program Testing All Three Order Types

The program uses self-checking helper methods that throw `AssertionError` on mismatch. No external libraries are needed and `-ea` does not need to be enabled.

Save as `CollectionOrderDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.PriorityQueue;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class CollectionOrderDemo {
    record Job(String id, int priority, long sequence) { }

    private static int passed;

    private static void checkEquals(String label, Object expected, Object actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(label + ": expected=" + expected
                    + ", actual=" + actual);
        }
        passed++;
    }

    private static <E> List<E> pollOrder(PriorityQueue<E> source) {
        PriorityQueue<E> copy = new PriorityQueue<>(source);
        List<E> result = new ArrayList<>();
        while (!copy.isEmpty()) {
            result.add(copy.poll());
        }
        return result;
    }

    private static <E> Map<E, Integer> frequencies(Collection<E> values) {
        Map<E, Integer> counts = new HashMap<>();
        for (E value : values) {
            counts.merge(value, 1, Integer::sum);
        }
        return counts;
    }

    private static <E> boolean isOrdered(List<E> values, Comparator<? super E> order) {
        for (int i = 1; i < values.size(); i++) {
            if (order.compare(values.get(i - 1), values.get(i)) > 0) {
                return false;
            }
        }
        return true;
    }

    private static List<String> ids(List<Job> jobs) {
        return jobs.stream().map(Job::id).toList();
    }

    public static void main(String[] args) {
        Map<String, Integer> insertion = new LinkedHashMap<>();
        insertion.put("B", 2);
        insertion.put("A", 1);
        insertion.put("C", 3);
        checkEquals("insertion order", List.of("B", "A", "C"),
                new ArrayList<>(insertion.keySet()));
        System.out.println("insertion keys = " + new ArrayList<>(insertion.keySet()));
        insertion.put("A", 10);
        checkEquals("updating existing key keeps insertion position",
                List.of("B", "A", "C"), new ArrayList<>(insertion.keySet()));
        insertion.remove("A");
        insertion.put("A", 20);
        checkEquals("remove then insert appends key", List.of("B", "C", "A"),
                new ArrayList<>(insertion.keySet()));

        Map<String, Integer> access = new LinkedHashMap<>(16, 0.75f, true);
        access.put("B", 2);
        access.put("A", 1);
        access.put("C", 3);
        access.get("B");
        checkEquals("access order after get", List.of("A", "C", "B"),
                new ArrayList<>(access.keySet()));

        Set<String> insertionSet = new LinkedHashSet<>(List.of("B", "A", "B", "C"));
        checkEquals("set duplicate does not move value", List.of("B", "A", "C"),
                new ArrayList<>(insertionSet));
        insertionSet.remove("A");
        insertionSet.add("A");
        checkEquals("set remove and reinsert", List.of("B", "C", "A"),
                new ArrayList<>(insertionSet));

        Set<String> sortedSet = new TreeSet<>(List.of("B", "A", "B", "C"));
        checkEquals("natural sorted set", List.of("A", "B", "C"),
                new ArrayList<>(sortedSet));
        Set<String> descendingSet = new TreeSet<>(Comparator.reverseOrder());
        descendingSet.addAll(List.of("B", "A", "C"));
        checkEquals("reverse sorted set", List.of("C", "B", "A"),
                new ArrayList<>(descendingSet));

        Map<String, Integer> sortedMap = new TreeMap<>();
        sortedMap.put("B", 2);
        sortedMap.put("A", 3);
        sortedMap.put("C", 1);
        checkEquals("map sorted by keys", List.of("A", "B", "C"),
                new ArrayList<>(sortedMap.keySet()));
        checkEquals("values follow keys, not value sorting", List.of(3, 2, 1),
                new ArrayList<>(sortedMap.values()));
        System.out.println("sorted keys = " + new ArrayList<>(sortedMap.keySet()));

        PriorityQueue<Integer> numbers = new PriorityQueue<>(List.of(30, 10, 20, 10));
        List<Integer> numberOrder = pollOrder(numbers);
        checkEquals("natural priority order with duplicate", List.of(10, 10, 20, 30),
                numberOrder);
        checkEquals("peek reads first priority", 10, numbers.peek());
        checkEquals("copy leaves source size unchanged", 4, numbers.size());
        System.out.println("priority values = " + numberOrder);

        List<Job> jobs = List.of(
                new Job("A", 2, 0),
                new Job("B", 5, 1),
                new Job("C", 5, 2),
                new Job("D", 1, 3),
                new Job("E", 2, 4));
        Comparator<Job> byPriority = Comparator.comparingInt(Job::priority).reversed();
        List<Job> stableSorted = new ArrayList<>(jobs);
        stableSorted.sort(byPriority);
        checkEquals("stable list sorting", List.of("B", "C", "A", "E", "D"),
                ids(stableSorted));

        PriorityQueue<Job> priorityOnly = new PriorityQueue<>(byPriority);
        priorityOnly.addAll(jobs);
        List<Job> priorityResult = pollOrder(priorityOnly);
        List<Integer> levels = priorityResult.stream().map(Job::priority).toList();
        checkEquals("priority levels", List.of(5, 5, 2, 2, 1), levels);
        checkEquals("all jobs preserved", frequencies(jobs), frequencies(priorityResult));
        checkEquals("ordered under comparator", true, isOrdered(priorityResult, byPriority));
        System.out.println("priority-only levels = " + levels);

        Comparator<Job> withSequence = byPriority.thenComparingLong(Job::sequence);
        PriorityQueue<Job> deterministic = new PriorityQueue<>(withSequence);
        deterministic.addAll(jobs);
        List<Job> exactOrder = pollOrder(deterministic);
        checkEquals("priority then sequence", List.of("B", "C", "A", "E", "D"),
                ids(exactOrder));
        checkEquals("job source queue not consumed", jobs.size(), deterministic.size());
        System.out.println("priority with sequence = " + ids(exactOrder));

        PriorityQueue<Integer> empty = new PriorityQueue<>();
        checkEquals("empty queue output", List.of(), pollOrder(empty));
        checkEquals("empty peek", null, empty.peek());
        PriorityQueue<Integer> singleton = new PriorityQueue<>(List.of(7));
        checkEquals("singleton queue output", List.of(7), pollOrder(singleton));

        System.out.println("PASS: " + passed + " checks");
    }
}
```

Compile and run:

```shell
javac --release 17 CollectionOrderDemo.java
java CollectionOrderDemo
```

Stdout when all checks pass:

```text
insertion keys = [B, A, C]
sorted keys = [A, B, C]
priority values = [10, 10, 20, 30]
priority-only levels = [5, 5, 2, 2, 1]
priority with sequence = [B, C, A, E, D]
PASS: 22 checks
```

The program intentionally does not print or assert the ID order of `priorityOnly` on ties, because that comparator's contract does not define it. It still verifies the priority sequence, non-inversion under the comparator, and the occurrence count of each job.

`isOrdered()` in the program receives an `ArrayList` created by `pollOrder()`, so indexed access here is appropriate. If reusing this helper with large linked lists, switch to iterator traversal to avoid re-traversing indices on each comparison.

## 8. Why Do Set.equals and Map.equals Not Test Order?

Two `LinkedHashSet` instances can contain the same elements but iterate in different orders. Set equality still considers them equivalent in content. Similarly, two maps containing the same mappings can be equal even if their key iteration orders differ.

Example data:

```text
First map:  insert B then A
Second map: insert A then B

Same mappings:        yes
Same iteration order: no
```

If you need to test order, convert the observed order into a `List`:

```java
List<String> actualKeys = new ArrayList<>(actualMap.keySet());
```

Then compare it against an ordered expected list. If both mappings and order matter, test both; checking ordered keys does not replace checking the value associated with each key.

In JUnit 5, you can use `assertIterableEquals(expectedList, actualMap.keySet())` or compare `List` instances using `assertEquals`. For `PriorityQueue`, the observed target should be the result of `pollOrder(queue)` rather than the queue's own iterator. These assertion calls are suggestions for environments already using JUnit Jupiter; the full program in Section 7 runs standalone.

## 9. Testing Practices That Destroy Information You Need to Protect

### 9.1. Sorting actual Before Comparing Insertion Order

Suppose the contract requires `B, A, C`, but the code returns `A, B, C`. If the test sorts both expected and actual before comparing, both sides become `A, B, C` and the bug is masked.

Normalizing by sorting is only appropriate when the contract does not care about order and the goal is to compare membership. Do not use it for an insertion-order test.

### 9.2. Converting Priority Results to a Set

A queue can contain multiple equal elements. Converting to a `Set` loses occurrence counts, so it fails to detect when the queue is missing a duplicate or has an extra duplicate.

To verify complete contents when no secondary order is required, use per-element counts or an equivalent multiset representation. In this article, `frequencies()` uses a `HashMap` and the `equals/hashCode` contract of the `Job` record.

### 9.3. Computing expected Using the Exact Comparator Under Test

If a domain comparator has its direction inverted, using it both in the production structure and to sort `expected` can cause both sides to be wrong in the same way while the test still passes.

Concrete expected examples such as `[5, 5, 2, 2, 1]` or `[B, C, A, E, D]` must derive from written business rules. Checking orderedness using the comparator is an additional verification layer, not the sole source of truth for what priority means.

### 9.4. Asserting on toString Instead of Behavior

Printed strings are useful for explanation and diagnosis, but an assertion relying on the `toString()` format of a collection or element can break due to display changes without any change in behavior.

In the program, the stdout lines are merely illustrative output. The real checks compare `List` instances, frequency maps, or specific values.

## 10. Test Case Matrix with Strong Discriminating Power

| Goal | Data / Action | What to Assert |
| --- | --- | --- |
| Insertion order differs from natural order | Insert `B, A, C` | Iterates as `B, A, C` |
| Updating an existing key | Change value of `A` | Position stays unchanged in insertion-order; value updates properly |
| Remove then re-add | Remove `A`, add `A` | `A` moves to the end according to insertion contract |
| Access-order mode | Insert `B, A, C`, read `B` | Iterates as `A, C, B` |
| Sort by key, not by value | `B->2`, `A->3`, `C->1` | Keys `A,B,C`; values following keys `3,2,1` |
| Reversed sort direction | Descending comparator | Sequence decreases properly, does not accidentally increase |
| Ties in TreeSet | Two elements compare as 0 | Element count and element identification policy are accurate |
| Ties in PriorityQueue | Multiple jobs with same priority | Check priority groups; only enforce secondary order if promised |
| Secondary sequence rule | Same priority, different sequence | Smaller sequence is retrieved first |
| Duplicate elements in queue | Two `10` values | Both occurrences are retrieved |
| Empty and singleton | No elements or single element | Accurate output sequence; does not access nonexistent elements |
| Preserve source during inspection | Drain from copy | Source size and state are not consumed |
| Add new priority item after a retrieval | Poll one element then offer a new job | Subsequent retrievals pick the best among the remaining set |

The last case serves as a reminder that a dynamic queue does not have a globally monotonic priority sequence if new jobs continue to be added between retrievals. A higher-priority job can be added after a lower-priority job has already been processed. In that scenario, tests must follow step-by-step state transitions: each retrieval selects the top element from **the set currently present at that moment**, rather than applying a static sorted sequence across the entire history.

## 11. Testing Dynamic Priority and Avoiding In-Place Mutation of Sort Keys

A small scenario:

```text
Offer: A(priority=2), B(priority=5)
Poll:  B
Offer: C(priority=9)
Poll:  C
Poll:  A
```

The retrieved priority sequence is `5, 9, 2`. It is not descending across the entire history, but every retrieval is accurate for the jobs currently in the queue.

Do not directly mutate the priority field of an element currently residing in a queue and expect the structure to reorder itself. If an application needs to change priorities, the design must update the structure through a defined procedure, such as finding/removing the old job and inserting an updated version, or using a specialized data structure. Test that procedure separately, including job identity and the policy for handling stale versions.

With `TreeSet` or `TreeMap` keys, mutating comparison attributes while the element/key remains inside the structure similarly breaks lookup and ordering invariants. Use immutable keys or an explicit remove/update/re-insert procedure.

## 12. Self-Check and Exercises

### Question 1: Do two LinkedHashMap instances that are equal according to Map.equals guarantee the same iteration order?

No. Map equality checks mappings. You need to observe the key or entry order as a sequence and check it separately when order is part of the contract.

### Question 2: Why shouldn't you use new ArrayList<>(priorityQueue) as actual for priority order?

Because that captures iterator order, not the sequence of elements retrieved from the head of the queue. Draining via `poll()` from the source or an appropriate copy is what observes the behavior under test.

### Question 3: Must two jobs with the same priority be retrieved in insertion order?

Not if you only rely on `PriorityQueue` and a comparator that only compares priority. If this rule is needed, add a secondary key expressing submission order and test it.

### Question 4: Is a descending priority sequence sufficient to prove the queue processed the entire input properly?

Not yet. Elements could be missing or duplicated while the remaining sequence is still descending. You must verify contents and occurrence counts alongside the tie-breaking policy.

### Exercises

1. Add a check verifying that changing the value of `A` in an insertion-order map both preserves key order and actually updates the value.
2. Add a job with priority `Integer.MAX_VALUE` and a job with `Integer.MIN_VALUE`; write the expected output manually following the rule that higher priority runs first.
3. Write a test for the dynamic priority scenario in Section 11; verify each `poll()` call step by step rather than sorting the entire history.
4. Intentionally move `reversed()` to after `thenComparingLong()` and identify which test case catches the reversal of the secondary rule.
5. Replace the queue with a set in an experimental build; identify which test case proves that duplicate or tied elements were lost outside the contract.

A reliable ordering test must choose the right observation action, data that distinguishes policies, and assertions that preserve critical information. Insertion order, sorted order, and priority retrieval order each require their corresponding verification approach.
