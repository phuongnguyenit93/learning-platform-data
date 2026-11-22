# `ConcurrentModificationException` and the Limits of the Fail-Fast Mechanism in Java

> **Context:** Java Core → Exception → Runtime Exceptions. `java.util.ConcurrentModificationException` (CME) commonly occurs when a program **structurally modifies a collection while iterating over it** using a *fail-fast* iterator. The word “Concurrent” in the name is misleading: **two threads are not required** for this exception to be thrown. Conversely, in a multithreaded program, **the absence of CME does not prove that the code is thread-safe**. Fail-fast is a *best-effort* bug-detection mechanism, **not** a synchronization mechanism, lock, transaction, or guarantee that every modification will be detected.

## 1. Understanding the True Nature of `ConcurrentModificationException`

CME is an unchecked exception class:

```text
java.lang.Throwable
└── java.lang.Exception
    └── java.lang.RuntimeException
        └── java.util.ConcurrentModificationException
```

A common scenario:

```java
// Illustrative snippet, not a standalone file.
List<String> names = new ArrayList<>(
        List.of("An", "Bình", "Chi"));

for (String name : names) {
    if ("Bình".equals(name)) {
        names.remove(name); // Modifies the collection outside the iterator.
    }
}
```

The code above **may** throw CME depending on the iteration state; because fail-fast is best effort, **do not use this exact snippet to claim that the exception will always occur**. In particular, a removal can cause the iterator to have no remaining elements before the next check. The verification examples later in this article intentionally choose data and ordering so that the error occurs consistently on JDK 17.

Key takeaways:

- **Source of inconsistency:** an active iterator relies on assumptions about the collection's structure, while other code alters that structure without going through the iterator's permitted operations.
- **Reaction:** the iterator *may* detect the modification and throw CME, rather than continuing based on stale state.
- **Not definitive proof:** the fail-fast mechanism does not guarantee detection in every case and does not guarantee thread safety.
- **Concurrency is not required:** a single method in a single thread that iterates while calling `list.remove(...)` is enough to trigger CME.
- **Not a checked exception:** you are not required to declare `throws ConcurrentModificationException` or add a `catch` block for the code to compile.

### 1.1. CME Does Not Mean the Collection Is Permanently Corrupted

The exception reports that an iteration operation cannot safely continue under the fail-fast contract/implementation. It does not by itself mean that all memory or the entire collection is permanently corrupted. However, **business state may have already been partially modified before the error**: elements may have been removed, values may have been updated, or other side effects may have already occurred.

Therefore, when handling CME, you must distinguish:

1. **Identify the faulty logic path** and fix it at the root cause.
2. **Assess the already-modified state**; CME does not roll back prior operations.
3. **Do not catch CME to continue using the old iterator** hoping the state will recover on its own.

## 2. “Concurrent”, Yet a Single Thread Can Still Cause the Error

Example of a sequential program:

```text
Single thread
  ├── creates ArrayList
  ├── creates Iterator
  ├── iterator.next() returns the first element
  ├── list.remove(...) directly modifies the structure
  └── iterator.next() checks state → may throw CME
```

This is a *conflict between iteration and structural modification*, not necessarily a *data race between threads*.

Another example: a `forEach` callback modifies the very list being iterated over. The entire process can still run on a single thread while violating the iterator's assumptions.

Conversely, multiple threads can run **without** throwing CME, for example when:

- Concurrent operations are performed on a collection with a *weakly consistent* iterator such as `ConcurrentHashMap`.
- Iterating over a snapshot of `CopyOnWriteArrayList`.
- Threads are properly synchronized so that iteration never overlaps with an unsafe structural modification.
- Only operations that do not affect structure under the specific contract are performed.

Therefore, do not “fix” CME by simply turning off multithreading; instead, identify **the iterator, the collection type, the modification method, and the ownership scope**.

## 3. Fail-Fast: Concept, Purpose, and Scope

A *fail-fast iterator* attempts to detect when a collection's structure is modified outside the operations permitted by the iterator during traversal. For common collections such as `ArrayList` and `HashMap`, fail-fast iterators help surface bugs early instead of letting the program continue with unpredictable results.

The purpose is **to detect contract violations**, not “to forbid modifying the collection forever.”

For example, with `ArrayList`:

- After creating an iterator, calling `list.add(...)` or `list.remove(...)` can invalidate the iterator.
- Calling `iterator.remove()` after a valid `next()` can remove the current element **and synchronize the iterator's state**, allowing traversal to continue.
- `ListIterator.add(...)` and `ListIterator.remove()` are also modification paths with their own contracts.
- Not every mutating method is a *structural modification*: `list.set(index, newValue)` replaces the value at an existing position without **changing the number of elements** in `ArrayList`; typically, it does not cause a fail-fast iterator to fail merely due to replacing a value.
- Conversely, sorting or certain implementation-specific operations can affect the modification marker even when the size does not change. Do not turn “size changed” into an absolute definition across all classes and APIs.

### 3.1. Fail-Fast Does Not Mean Synchronized

A fail-fast iterator **does not lock the collection**. If two threads concurrently read/write an unprotected `ArrayList`, they can encounter data races, observe incorrect results, lose updates, throw CME, or fail in other ways. Even if CME is observed in one test run, it does not establish a *happens-before* relationship or safe access in another run.

An incorrect usage:

```java
// Anti-pattern: do not use exceptions as a synchronization alarm.
try {
    for (String x : sharedList) {
        consume(x);
    }
} catch (ConcurrentModificationException e) {
    // Assumes every unsafe situation has been detected.
}
```

This is an illustrative snippet where `sharedList` and `consume` are undefined. Catching CME does not fix a lack of synchronization. Design proper ownership, locking, snapshots, or concurrent collections according to your requirements.

## 4. Typical Mechanism: `modCount` and `expectedModCount`

In many JDK collection implementations, the fail-fast mechanism relies on two values:

- **`modCount`:** the collection's structural modification counter, typically incremented whenever a structural change occurs.
- **`expectedModCount`:** the value recorded by the iterator at creation time or after a valid modification performed through the iterator itself.
- When the iterator performs a checked operation and sees that the two values **differ**, it may throw `ConcurrentModificationException`.

Diagram:

```text
ArrayList: modCount = 5
New Iterator: expectedModCount = 5

iterator.next()
  expected = 5, actual = 5 → continue

direct list.remove(0)
  modCount = 6

iterator.next()
  expected = 5, actual = 6 → fail-fast (CME)
```

**Accuracy note:** the names `modCount` and `expectedModCount` are implementation details of specific collections/iterators, not a public `Iterator` API that every collection must use. Other containers may detect modifications differently, or may not be fail-fast at all. Do not write application logic that depends on internal counter values.

### 4.1. Why Can `Iterator.remove()` Be Valid?

When removing properly through the iterator:

```java
Iterator<String> it = list.iterator();
while (it.hasNext()) {
    String value = it.next();
    if (shouldRemove(value)) {
        it.remove();
    }
}
```

This is an **illustrative snippet** requiring appropriate `list` and `shouldRemove` definitions. The iterator performs the modification itself and updates the internal state needed to continue iterating consistently.

By contrast, `list.remove(value)` mutates the container directly while the iterator is active, so the iterator's observed state may no longer match.

**Do not assume every iterator supports `remove()`:** `Iterator.remove()` is an optional operation; many iterators from immutable, snapshot, or read-only collections do not support it and may throw `UnsupportedOperationException`. Always check the contract of the iterator you are using.

### 4.2. When Does the Check Happen?

Some iterators check in `next()`, `remove()`, or other operations. For `ArrayList`, `hasNext()` typically compares the cursor position against the size without necessarily checking `modCount` inside `hasNext()` itself. As a result, a structural modification can **go undetected** before the loop ends.

Do not claim that “every `hasNext()` checks for concurrent modification” or “once a list is modified, the next step is guaranteed to throw CME.” This is one of the core limitations of the mechanism.

## 5. Java 17 — Example 1: Intentionally Triggering CME in a Single Thread

Create **`SingleThreadCmeDemo.java`**:

```java
import java.util.ArrayList;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;

public class SingleThreadCmeDemo {
    public static void main(String[] args) {
        List<String> names =
                new ArrayList<>(List.of("An", "Bình", "Chi", "Dũng"));

        Iterator<String> iterator = names.iterator();
        System.out.println("First: " + iterator.next());

        names.add("Em"); // Structural modification via the list, not via the iterator.

        try {
            System.out.println("Second: " + iterator.next());
        } catch (ConcurrentModificationException e) {
            System.out.println("Caught: "
                    + e.getClass().getSimpleName());
        }

        System.out.println("Size after add: " + names.size());
    }
}
```

Compile and run with JDK 17:

```bash
javac -encoding UTF-8 SingleThreadCmeDemo.java
java SingleThreadCmeDemo
```

Stdout when run on JDK 17 `ArrayList`:

```text
First: An
Caught: ConcurrentModificationException
Size after add: 5
```

Analysis:

1. `iterator` is created when `names` contains four elements.
2. The first `iterator.next()` reads `"An"`.
3. `names.add("Em")` structurally modifies the container after the iterator was created.
4. The second `iterator.next()` detects the mismatch and throws CME under `ArrayList`'s fail-fast mechanism.
5. The program has only **one thread** and still throws CME.
6. The element `"Em"` **was already added** before the error occurred; catching the exception does not roll back the change.

This example uses an explicit `next()` call after the modification to observe the failure in JDK 17. It does not turn the **best-effort** rule into a contract that CME must be thrown across all implementations and execution schedules.

## 6. Enhanced `for` and `Iterator`: Short Syntax Still Follows Traversal Rules

For an `Iterable`, the loop:

```java
for (String value : list) {
    consume(value);
}
```

is typically compiled using an `Iterator` in a conceptually equivalent structure:

```java
Iterator<String> it = list.iterator();
while (it.hasNext()) {
    String value = it.next();
    consume(value);
}
```

Both snippets are illustrative and require appropriate variables/methods. Consequently, calling `list.remove(...)` or `list.add(...)` directly inside a `for-each` loop over that same list can violate the iterator contract.

**Distinction:** enhanced `for` over an **array** uses its own index-based traversal mechanism and does not create a fail-fast collection iterator; you cannot assume every `for (x : something)` loop uses `modCount`.

### 6.1. Anti-Pattern Example

```java
List<Integer> numbers =
        new ArrayList<>(List.of(1, 2, 3, 4));

for (Integer value : numbers) {
    if (value == 2) {
        numbers.remove(value);
    }
}
```

This is an illustrative snippet and should not be relied upon to guarantee CME in every case. Even if this code runs **without throwing an error**, it is still an error-prone way to mutate during iteration and should not be considered correct.

The accurate statement is: structurally modifying a list via the list's own methods while a fail-fast iterator is traversing it **can** lead to CME; you must use an iterator-compatible mutation API or switch to another strategy.

## 7. Java 17 — Example 2: Removing Safely with `Iterator.remove()`

Create **`IteratorRemoveDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

public class IteratorRemoveDemo {
    public static void main(String[] args) {
        List<Integer> numbers =
                new ArrayList<>(List.of(1, 2, 3, 4, 5));

        Iterator<Integer> it = numbers.iterator();
        while (it.hasNext()) {
            int value = it.next();
            if (value % 2 == 0) {
                it.remove();
            }
        }

        System.out.println("Remaining: " + numbers);
    }
}
```

Commands:

```bash
javac -encoding UTF-8 IteratorRemoveDemo.java
java IteratorRemoveDemo
```

Stdout:

```text
Remaining: [1, 3, 5]
```

Explanation:

- `it.next()` provides the current element; `it.remove()` removes **the element most recently returned by the iterator**.
- The iterator is aware of the removal and can continue iterating.
- Even elements `2` and `4` are removed, while the order of odd elements is preserved.
- There is no need to call `numbers.remove(value)` directly inside the loop.
- `Iterator.remove()` does not take an arbitrary element as an argument; it only removes the element corresponding to the most recent valid `next()`/`previous()` call (for `ListIterator`).

### 7.1. `remove()` Has a State Contract

An iterator's `remove()` is only allowed after a successful `next()` call and typically at most **once** per returned element before the next step. If you call `remove()` before `next()`, or call it twice consecutively without another `next()`, the `ArrayList` iterator can throw `IllegalStateException`.

`UnsupportedOperationException` means something different: the iterator **does not support** removal (for example, an iterator over an immutable list).

CME, `IllegalStateException`, and `UnsupportedOperationException` are **three distinct conditions** and cannot be fixed by swallowing them with a single catch block.

## 8. Java 17 — Example 3: Valid Add/Replace/Remove with `ListIterator`

`ListIterator<E>` extends `Iterator<E>` to allow bidirectional traversal, element insertion, and replacing the current element when the list supports it.

Create **`ListIteratorEditDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.ListIterator;

public class ListIteratorEditDemo {
    public static void main(String[] args) {
        List<String> tasks =
                new ArrayList<>(List.of("A", "B", "C"));

        ListIterator<String> it = tasks.listIterator();
        while (it.hasNext()) {
            String task = it.next();
            if ("B".equals(task)) {
                it.set("B-done");
                it.add("B-extra");
            }
        }

        System.out.println("Tasks: " + tasks);
    }
}
```

Run:

```bash
javac -encoding UTF-8 ListIteratorEditDemo.java
java ListIteratorEditDemo
```

Stdout:

```text
Tasks: [A, B-done, B-extra, C]
```

With `ArrayList`:

1. `it.set("B-done")` replaces the value of the element most recently returned by `next()`.
2. `it.add("B-extra")` inserts an element at the iterator's current position according to its contract.
3. The iterator manages its own state and position, so traversal continues without failing from these operations.
4. `ListIterator.add` is optional in some implementations; choose a mutable list that supports it.
5. After `it.add(...)`, the rules for the next `remove()`/`set()` call change according to `ListIterator`'s state; do not assume calling `set` immediately after `add` is always valid.

**Do not confuse this:** having a `ListIterator` does not mean other code is free to mutate the list via `list.add(...)` and expect the iterator to adapt. The valid updates here are performed **through the same iterator**.

## 9. A Simpler Approach: `removeIf`

For collections that support removal, the `removeIf(Predicate<? super E>)` API often expresses “remove elements matching a condition” more clearly than manually driving an iterator.

```java
List<Integer> numbers =
        new ArrayList<>(List.of(1, 2, 3, 4, 5));

numbers.removeIf(n -> n % 2 == 0);
System.out.println(numbers);
```

This in-method snippet produces:

```text
[1, 3, 5]
```

### 9.1. Java 17 — A `removeIf` Example with Deterministic Output

Create **`RemoveIfDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class RemoveIfDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>(
                List.of("An", "Bình", "Chi", "Dũng"));

        boolean changed =
                names.removeIf(s -> s.length() <= 2);

        System.out.println("Changed: " + changed);
        System.out.println("Names: " + names);

        boolean changedAgain =
                names.removeIf(s -> s.startsWith("X"));
        System.out.println("Changed again: " + changedAgain);
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 RemoveIfDemo.java
java RemoveIfDemo
```

Stdout:

```text
Changed: true
Names: [Bình, Chi, Dũng]
Changed again: false
```

**Explanation:**

- `removeIf` evaluates the predicate on elements and removes those that match.
- In this example, `"An"` and `"Chi"` have 2 and 3 UTF-16 code units respectively; the condition `length() <= 2` **only removes `"An"`**, not `"Chi"`.
- `changed` is `true` because an element was removed.
- On the second call, no name starts with `X`, so `changedAgain` is `false`.
- The API is more concise than a manual loop and uses a removal mechanism tailored to the implementation when used according to its contract.

**Note:** the `Names` output in this example is determined by character count (`String.length()`); rely on the actual condition rather than intuition about Vietnamese names having two or three letters. If the goal were to remove names shorter than four code units, the predicate would need to be `s.length() < 4`, and the result would differ.

> Study note: `removeIf` **does not mean the predicate is allowed to structurally modify the collection by other means**. If the predicate itself calls `names.add(...)` or `names.remove(...)`, the code can still trigger CME or produce undefined results under the contract. Keep predicates pure with respect to the element whenever possible.

## 10. Does “Unchanged Size” Guarantee No CME?

**There is no universal rule across all collections** that “as long as the size does not change, CME cannot happen.” You must look at what modifications the implementation considers structural or iteration-invalidating.

### 10.1. With `ArrayList`: `set` Only Replaces a Value

`ArrayList.set(index, element)` replaces the value at an existing index without changing the number of elements. In a standard `ArrayList`, calling `set` does not increment the structural modification counter, so the iterator does not fail-fast **solely because of `set`**.

Example:

```java
List<String> values =
        new ArrayList<>(List.of("A", "B", "C"));
Iterator<String> it = values.iterator();

values.set(1, "B2");
while (it.hasNext()) {
    System.out.println(it.next());
}
```

This is an illustrative snippet. With Java 17 `ArrayList`, it can print `A`, `B2`, `C` without throwing CME.

However:

- Seeing updated values mid-traversal does not mean multithreaded access is safe.
- Other collections have their own iterator and metadata behaviors.
- Changing element order via `sort` or altering internal structure can be detected differently from `set`, even when the size stays the same.

### 10.2. With `HashMap`: Replacing a Value for an Existing Key Differs from Adding/Removing a Key

When iterating over `HashMap.entrySet()`, adding a **new key** or removing an entry can cause the iterator to fail-fast. However, `map.put(existingKey, newValue)` only replaces the value of an existing entry and is typically **not a structural modification**.

This is a distinction between *value replacement* and *adding/removing mappings*, not a synchronization promise in a multithreaded environment.

## 11. Java 17 — Example 5: `HashMap` Also Has Fail-Fast Iterators

Create **`HashMapCmeDemo.java`**:

```java
import java.util.ConcurrentModificationException;
import java.util.HashMap;
import java.util.Iterator;
import java.util.Map;

public class HashMapCmeDemo {
    public static void main(String[] args) {
        Map<String, Integer> scores = new HashMap<>();
        scores.put("A", 10);
        scores.put("B", 20);

        Iterator<String> it = scores.keySet().iterator();
        System.out.println("Has first: " + it.hasNext());

        scores.put("C", 30); // Adding a key: structural modification.

        try {
            it.next();
        } catch (ConcurrentModificationException e) {
            System.out.println("HashMap: "
                    + e.getClass().getSimpleName());
        }

        System.out.println("Size: " + scores.size());
    }
}
```

Run:

```bash
javac -encoding UTF-8 HashMapCmeDemo.java
java HashMapCmeDemo
```

Stdout on JDK 17 `HashMap`:

```text
Has first: true
HashMap: ConcurrentModificationException
Size: 3
```

**Why doesn't the example print key order?** `HashMap` does not guarantee key iteration order; printing keys in iteration order could produce different stdout if the implementation or data changes. Here, the goal is to verify CME after a `put` that adds a new key, independent of bucket order.

### 11.1. Want to Remove Entries While Iterating a Map?

You can use the `entrySet()` iterator and `iterator.remove()` when the implementation supports it, or use `map.entrySet().removeIf(predicate)` per the contract.

```java
Map<String, Integer> scores = new HashMap<>();
scores.put("A", 10);
scores.put("B", 20);

scores.entrySet().removeIf(e -> e.getValue() < 15);
System.out.println(scores.size()); // 1
```

This is an in-method snippet. Do not call `scores.remove(e.getKey())` directly inside an enhanced-for loop over `scores.entrySet()` and expect the iterator to adapt.

## 12. The Biggest Limitation: Fail-Fast Is **Best Effort**

The documentation for standard collection fail-fast iterators emphasizes a crucial point: **reliable detection of unsynchronized concurrent modification cannot be guaranteed**. The fail-fast mechanism should be used **to detect bugs**, not to build program correctness logic.

### 12.1. Situations Where CME May Not Appear

1. The modification occurs **before the iterator is created**: the new iterator sees the updated state.
2. The operation is not considered structural/invalidating for that specific iterator.
3. The iterator **does not perform another check** after the modification, for example because the loop has ended or `hasNext()` determines no elements remain.
4. Modifications interleave across threads without proper synchronization; observed state and checks have no detection guarantee.
5. The collection uses a snapshot or weakly consistent iterator, which is not designed to throw CME on routine modifications.
6. An API uses a traversal mechanism or spliterator that behaves differently from the iterator you are assuming.

**Conclusion:** “did not throw CME” does not mean “valid code” or “no concurrent modification occurred.” Different runs can yield different outcomes if the program has a data race.

### 12.2. Do Not Use CME as an Accurate Signal to Retry

Anti-pattern:

```java
while (true) {
    try {
        traverse(sharedMutableList);
        break;
    } catch (ConcurrentModificationException ignored) {
        // Infinite retry hoping it will eventually succeed without error.
    }
}
```

This is an illustrative snippet where `traverse` and `sharedMutableList` are undefined. This approach can:

- Loop infinitely if the collection is continuously modified.
- Miss certain unsynchronized modifications because CME is only best effort.
- Re-run operations with side effects, causing duplicates.
- Cause CPU spin and destabilize the system.
- Fail to establish memory visibility or atomicity.

If consistent traversal is required, use a design with **proper locking**, **snapshots**, **immutable state**, or a collection/algorithm that provides the appropriate semantics.

## 13. A Subtle Case: Removing Without Seeing CME

On JDK 17, `ArrayList`'s iterator typically checks for modification in `next()`. `hasNext()` may simply compare the cursor and size. Therefore, the snippet below sometimes **does not throw CME**, even though mutating the list directly inside an enhanced-for loop is incorrect.

Consider a two-element example:

```java
List<String> names =
        new ArrayList<>(List.of("A", "B"));

for (String name : names) {
    if ("A".equals(name)) {
        names.remove("A");
    }
}
```

This is a **snippet for analysis only**, and the same behavior is not guaranteed across all `List` implementations. After removing `A`, the size drops to 1; the iterator has already advanced past one element, so the cursor is also 1. The next `hasNext()` call can return `false` and terminate the loop **without calling `next()` again to check `modCount`**.

Important takeaways:

- Not seeing an exception **does not make the code correct**.
- The mechanism can vary by implementation and version.
- Many similar bugs sit silently until data or ordering changes.
- This demonstrates the *best-effort* limitation, not a trick for avoiding CME.

### 13.1. Java 17 — Program Demonstrating the Check Limitation

Create **`FailFastNotGuaranteedDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

public class FailFastNotGuaranteedDemo {
    public static void main(String[] args) {
        List<String> values =
                new ArrayList<>(List.of("A", "B"));

        Iterator<String> it = values.iterator();
        System.out.println("First: " + it.next());

        values.remove("A");

        System.out.println("Has next: " + it.hasNext());
        System.out.println("Contents: " + values);
    }
}
```

Run on JDK 17:

```bash
javac -encoding UTF-8 FailFastNotGuaranteedDemo.java
java FailFastNotGuaranteedDemo
```

Stdout under `ArrayList.Itr.hasNext` behavior on JDK 17:

```text
First: A
Has next: false
Contents: [B]
```

**Interpretation:** `it` was created before the list was modified, yet after removing `A`, `hasNext` sees that cursor equals size and returns `false`. The code does not call `next()` again, so no subsequent check occurs to report CME. This proves that fail-fast **does not guarantee detecting every modification**, even in a single thread.

Do not turn JDK 17's specific behavior into a condition driving business logic. If your logic needs to know whether a list was modified, own or pass the data under a consistent contract instead of observing the presence or absence of CME.

## 14. Snapshot Iteration: `CopyOnWriteArrayList`

`java.util.concurrent.CopyOnWriteArrayList` copies its internal array on appropriate structural mutations. Its iterator operates on a **snapshot taken when the iterator was created**, is unaffected by subsequent updates, and **does not throw CME on routine list modifications**.

Strengths:

- Well-suited for **read-heavy, write-rare** workloads, such as a relatively small listener list.
- Iteration sees a stable view based on the iterator's snapshot.
- Reads/traversals do not contend on the same lock with every write the way a traditional synchronized list does.

Trade-offs:

- Updates typically copy the backing array, which is expensive for large lists or frequent writes.
- A snapshot iterator **does not reflect** new updates made after the iterator was created.
- `Iterator.remove()`, `set()`, and `add()` are not supported on the snapshot iterator and throw `UnsupportedOperationException`.
- A snapshot iterator is not a system-wide transaction; it is only a point-in-time view of that collection.

### 14.1. Java 17 — Snapshot Iterator Example

Create **`CopyOnWriteSnapshotDemo.java`**:

```java
import java.util.Iterator;
import java.util.concurrent.CopyOnWriteArrayList;

public class CopyOnWriteSnapshotDemo {
    public static void main(String[] args) {
        CopyOnWriteArrayList<String> names =
                new CopyOnWriteArrayList<>();

        names.add("A");
        names.add("B");

        Iterator<String> snapshot = names.iterator();
        names.add("C");

        System.out.print("Snapshot:");
        while (snapshot.hasNext()) {
            System.out.print(" " + snapshot.next());
        }
        System.out.println();

        System.out.println("Current: " + names);

        try {
            snapshot.remove();
        } catch (UnsupportedOperationException e) {
            System.out.println("Iterator remove unsupported");
        }
    }
}
```

Commands:

```bash
javac -encoding UTF-8 CopyOnWriteSnapshotDemo.java
java CopyOnWriteSnapshotDemo
```

Stdout:

```text
Snapshot: A B
Current: [A, B, C]
Iterator remove unsupported
```

Even though `C` was added before iterating the snapshot, the iterator was **created earlier**, so it only sees `A` and `B`. This is the intended snapshot semantics, not a silently ignored failure.

**When choosing:** avoid `CopyOnWriteArrayList` for write-heavy workloads or large lists where copy cost is significant; measure and verify your use case. Also, do not confuse “the iterator does not throw CME” with “every multi-step coordination across threads is atomic.”

## 15. Weakly Consistent Iterators: `ConcurrentHashMap`

`java.util.concurrent.ConcurrentHashMap` is a map designed for concurrent access. Iterators on views such as `keySet()`, `values()`, and `entrySet()` have **weakly consistent** semantics:

- They can traverse while the map is being updated.
- They do not throw CME on normal concurrent updates.
- **They are not fixed snapshots:** an iterator may observe some updates made during traversal.
- They do not guarantee seeing **all** changes that occur during traversal.
- They do not provide a transactionally consistent snapshot of the entire map under concurrent updates.

Differences compared to `CopyOnWriteArrayList`:

| Characteristic | `CopyOnWriteArrayList` iterator | `ConcurrentHashMap` iterator |
| --- | --- | --- |
| Consistency model | Snapshot at creation time | Weakly consistent |
| Sees elements added after iterator creation? | No | Possibly, not guaranteed |
| CME on routine collection modifications? | No, due to snapshot semantics | No, due to weakly consistent semantics |
| Typical update cost | Copying the backing array | Concurrent map structure, different cost profile |
| Can traversal be treated as a full-data transaction? | No | No |
| Best suited for | Very read-heavy, rarely modified lists | Maps accessed/updated concurrently by multiple threads |

### 15.1. Java 17 — Map-Order-Independent Example

Create **`ConcurrentHashMapIteratorDemo.java`**:

```java
import java.util.Iterator;
import java.util.concurrent.ConcurrentHashMap;

public class ConcurrentHashMapIteratorDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, Integer> counts =
                new ConcurrentHashMap<>();
        counts.put("A", 1);
        counts.put("B", 2);

        Iterator<String> it = counts.keySet().iterator();
        counts.put("C", 3);

        int seen = 0;
        while (it.hasNext()) {
            it.next();
            seen++;
        }

        System.out.println("Map size: " + counts.size());
        System.out.println("Seen between 0 and 3: "
                + (seen >= 0 && seen <= 3));
    }
}
```

Run:

```bash
javac -encoding UTF-8 ConcurrentHashMapIteratorDemo.java
java ConcurrentHashMapIteratorDemo
```

Stdout:

```text
Map size: 3
Seen between 0 and 3: true
```

The program does not print a specific key order or exact count of entries seen, because the key point is that the API **does not guarantee new changes will fully appear in the traversal**. Even though the example uses a single thread, it suffices to show that a `ConcurrentHashMap` iterator can still traverse after the map is updated and is not designed to throw CME.

Do not write an assertion that `seen` must equal 3 after adding `C` **after iterator creation**. That is not what the weakly consistent contract promises.

## 16. `Collections.synchronizedList`: Iterators Still Require External Synchronization

`Collections.synchronizedList(...)` returns a wrapper that synchronizes individual list operations. However, when **traversing with an iterator** while other operations may occur, the documentation requires callers to **manually synchronize the entire iteration block on the wrapper itself** to prevent overlapping modifications.

Common pattern:

```java
List<String> sync =
        Collections.synchronizedList(new ArrayList<>());

synchronized (sync) {
    Iterator<String> it = sync.iterator();
    while (it.hasNext()) {
        System.out.println(it.next());
    }
}
```

This is an illustrative snippet requiring imports for `List`, `Collections`, `ArrayList`, and `Iterator`. Important points:

1. Wrapping a list with a synchronized wrapper **does not turn its iterator into a snapshot**.
2. Other add/remove operations must **actually use the same wrapper/lock**, never bypassing the wrapper to access the backing list directly.
3. Hold the lock across both iterator creation and traversal.
4. If while holding the lock the same thread structurally mutates the list via `sync.remove(...)` instead of the iterator, CME can still occur because `synchronized` does not override iterator rules.
5. The lock prevents other threads from modifying inside the protected region **when all participants respect the same locking discipline**.

### 16.1. Java 17 — Example Safe Under a Shared Lock

Create **`SynchronizedListTraversalDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;

public class SynchronizedListTraversalDemo {
    public static void main(String[] args) {
        List<Integer> sync = Collections.synchronizedList(
                new ArrayList<>(List.of(10, 20, 30)));

        synchronized (sync) {
            Iterator<Integer> it = sync.iterator();
            int sum = 0;
            while (it.hasNext()) {
                sum += it.next();
            }
            System.out.println("Sum: " + sum);
        }

        sync.add(40);
        synchronized (sync) {
            System.out.println("Size: " + sync.size());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 SynchronizedListTraversalDemo.java
java SynchronizedListTraversalDemo
```

Stdout:

```text
Sum: 60
Size: 4
```

This is a single-threaded demo for deterministic output; in multithreaded code, both writers and readers must agree on locking/ownership. Avoid holding a broad lock while calling uncontrolled external code, as that can increase contention or cause deadlocks depending on the overall design.

### 16.2. Why Not Lock Only Each `hasNext`/`next` Call?

If each call has its own separate lock scope and another thread can modify the list between calls, the iterator can still be invalidated. To achieve a traversal free of interleaved structural modifications, hold the same lock across the **entire** traversal or take a snapshot and iterate over the snapshot.

## 17. Using an Immutable Snapshot When Only Consistent Reads Are Needed

If the data is not too large and point-in-time consistency is required, you can copy the list:

```java
List<String> snapshot = List.copyOf(source);
for (String value : snapshot) {
    process(value);
}
```

This illustrative snippet requires `source` and `process`, assuming no `null` elements since `List.copyOf` rejects `null`. Once the snapshot is created, structural changes to `source` do not affect the snapshot list. If the elements inside are mutable objects, `List.copyOf` **does not deep-copy them**.

**Important boundary:** creating a snapshot from a list that another thread is modifying **without synchronization** is still a consistency/concurrency problem. You need a proper read/capture protocol: a shared lock, safe publication, or a concurrent source with acceptable semantics. `List.copyOf` does not automatically turn a racy read into a clean atomic snapshot.

### 17.1. Snapshot vs. Locking vs. Concurrent Collections

- **Snapshot:** suitable when static point-in-time data is acceptable for a processing pass and you want to minimize lock holding during traversal.
- **Locking:** suitable when you need a view consistent with updates using the same mechanism and can lock for the entire traversal.
- **Concurrent collections:** suitable when you want concurrent reads/writes under weaker or stronger contracts; check the semantics of each operation.
- **Immutable/persistent data:** suitable when the design can pass immutable data structures between threads, eliminating an entire class of iterator bugs.

There is no single “safest choice for every application”; consistency requirements, update frequency, data size, and latency all matter.

## 18. `subList`: Views and Modifying the Backing List

`List.subList(from, to)` typically returns a **view** backed by the source list, not an independent copy. When the backing list is structurally modified **outside the view or without going through the view according to its contract**, the sublist's state can become invalid. Some implementations throw CME when detecting such changes.

Illustrative example:

```java
List<String> original =
        new ArrayList<>(List.of("A", "B", "C", "D"));
List<String> view = original.subList(1, 3);

original.add("E"); // Modifies the backing list without going through the view.

// Subsequent operations on the view may fail or
// behave outside the subList contract; do not continue using it as normal.
```

This is an in-method snippet. Do not treat CME when using `subList` as a “multithreading coincidence.” Even in a single thread, modifying the backing list after the view is created is enough to violate the contract.

### 18.1. Make a Copy If You Need an Independent List

```java
List<String> snapshot =
        new ArrayList<>(original.subList(1, 3));
```

This creates a structural copy of the list at creation time, unlike a view tied to the backing list. For mutable objects, elements may still be shared references, so this is not a deep copy.

**Contract accuracy note:** The `List.subList` documentation states that the semantics of the returned list become **undefined** if the backing list is structurally modified in any way other than via the returned list. CME is a possible outcome in a specific implementation, not an exception guaranteed in all situations.

## 19. Streams, Spliterators, and Source-Mutating Callbacks

A Stream can be created from a collection:

```java
List<Integer> values = new ArrayList<>(List.of(1, 2, 3, 4));

values.stream().forEach(v -> {
    if (v == 2) {
        values.add(5);
    }
});
```

This is an **anti-pattern**, not recommended code. A callback modifying the data source while the pipeline is traversing it can violate Stream **non-interference** rules. Depending on the pipeline and implementation, this can cause CME, skipped/duplicated elements, or unpredictable results; do not treat any single failure mode as guaranteed.

### 19.1. Are Streams Always Fail-Fast?

No. Streams use spliterators and pipelines whose actual characteristics depend on the source and operation types:

- `IMMUTABLE` or `CONCURRENT` sources have different contracts from `ArrayList`.
- Some spliterators are late-binding or check at different points.
- With parallel streams, when workers observe changes is even less predictable.
- You cannot conclude “every stream that mutates its source will throw CME” or “if it didn't throw CME, the result is correct.”

**Usually better solutions:** build a new result list using `filter`/`map` and use that result, or finish traversal before modifying the original collection. For mutable collections, `removeIf` is often better suited for predicate-based removal.

### 19.2. Pattern for Creating a New Result Without Mutating the Source

```java
List<Integer> source = List.of(1, 2, 3, 4);
List<Integer> odds = source.stream()
        .filter(v -> v % 2 != 0)
        .toList();

System.out.println(odds); // [1, 3]
```

This in-method snippet uses Java 16+ `Stream.toList()` (available in Java 17). The list returned by `toList()` is unmodifiable by contract; do not assume you can `add` to it.

### 19.3. Mutating Predicates Also Carry Risk

`list.removeIf(x -> { list.add(...); return ...; })` also mutates the source while traversing outside the mechanism managed by the `removeIf` implementation. A predicate is designed to **decide whether to remove** an element, not to structurally modify the list during predicate evaluation. If complex side effects are needed, separate phases clearly for easier testing.

## 20. `HashMap`, `HashSet`, and `LinkedHashMap`: Not Just `List`

In `java.util`, many traditional collections provide fail-fast iterators, such as `ArrayList`, `HashMap`, `HashSet`, and `LinkedHashMap`. Always read the contract of the specific implementation.

- `HashSet` is typically backed by a hash structure; adding/removing elements can invalidate existing iterators.
- `HashMap` has key/value/entry views; structural mapping changes to the map affect iterators over these views.
- `LinkedHashMap` maintains iteration order and has an access-order mode; in access-order configuration, certain access operations can alter structural ordering, invalidating iterators under the contract.
- Do not use “element count did not change” as the sole criterion to assume an iterator is safe across all collections.

### 20.1. Access-Order `LinkedHashMap` Is a Notable Case

If a `LinkedHashMap` is configured in **access-order** mode for an LRU cache, calling `get(key)` can change the iteration order. In this implementation, a “value-read-only” operation can cause a structural modification in the sense that it affects iteration.

Therefore, even when not calling `add/remove`, read the contract regarding iteration order and structural modification. Do not generalize from `ArrayList.set` to `LinkedHashMap.get` in access-order mode.

### 20.2. Different Valid Modification Methods Across Map and Iterator

`Map.replace(key, value)` or `entry.setValue(...)` can update an entry's value without changing the key set; that differs from `put` adding a new key. However, with access-order structures, mutable views, or implementation differences, the impact on iteration can vary. For portable code, rely on the collection's API contract rather than guessing from method names.

## 21. CME Is Not a Locking Tool or Correctness Mechanism

A good code review should ask:

1. How many **threads** can access the collection?
2. Who **owns** the collection? Are mutable references shared?
3. Where is the iterator created and how long does it stay alive?
4. Who is allowed to add/remove/sort while the iterator is traversing?
5. Is a **consistent snapshot** required, or is near-real-time observation sufficient?
6. Is **atomicity** required across multiple operations, such as check-then-update?
7. Does modifying the collection have side effects outside the container?
8. Can the **traversal/computation** phase and the **mutation** phase be separated?
9. If switching to a concurrent collection, is its iteration consistency contract acceptable?
10. What tests prove meaningful behavior, rather than merely proving “no CME was observed”?

A contract-driven approach is far better than a generic “try/catch CME” across all collections.

## 22. Common Mistakes and Fixes

| Misconception | Problem | Reasonable Approach |
| --- | --- | --- |
| “CME only happens when two threads run together.” | A single thread can also mutate a list outside the iterator. | Inspect iteration logic and mutation paths. |
| “CME is a checked exception.” | It extends `RuntimeException`. | No mandatory declaration needed; fix the bug at the source. |
| “No CME means thread-safe.” | Fail-fast is only best effort; some iterators are not fail-fast. | Locking, ownership, snapshots, concurrent contracts. |
| “Every collection has `modCount`.” | That is an implementation detail of certain classes. | Read the specific iterator contract. |
| “Every `hasNext()` checks for modifications.” | Not guaranteed; `ArrayList` may skip it. | Do not rely on CME to detect every modification. |
| “If size change is 0, the iterator is definitely safe.” | Ordering or internal state can still be invalidated. | Check structural modification per class/API. |
| “Using `list.remove(...)` in for-each is fine if tests pass.” | It may just happen to exit before the next check. | Use `Iterator.remove()` or `removeIf`. |
| “`Iterator.remove` can be called anytime.” | It has a state machine and is an optional operation. | Call after `next`, at most once per valid step. |
| “`removeIf` allows the predicate to add/remove on the list.” | Can violate traversal semantics. | Keep predicates simple and avoid mutating the source. |
| “`Collections.synchronizedList` makes iterators automatically safe.” | Iteration requires external locking across the entire traversal. | `synchronized(list) { ... iterator ... }`. |
| “Locking each `next()` call individually is enough.” | Another thread can mutate between steps. | Lock the entire traversal or use a snapshot. |
| “A CopyOnWrite iterator sees new updates.” | It iterates over the snapshot at creation time. | Choose snapshot semantics intentionally. |
| “A CopyOnWrite iterator supports `remove`.” | Snapshot iterators do not support direct mutation. | Mutate via the list or use an appropriate strategy. |
| “A ConcurrentHashMap iterator provides a point-in-time snapshot.” | It is weakly consistent, not a transactional snapshot. | Choose an algorithm that fits. |
| “Switching ArrayList to a concurrent collection always fixes logic.” | Semantics for ordering, consistency, and cost differ. | Define requirements first, then pick the collection. |
| “If a Stream doesn't throw CME, side effects are right.” | Non-interference can still be violated. | Separate source and result; use `filter`/`removeIf` appropriately. |
| “`subList` is an independent copy.” | It is usually a view of the backing list. | Copy if independence is needed. |
| “CME automatically rolls back prior operations.” | Exceptions do not undo mutations. | Design transactions/compensation if needed. |
| “You can catch and retry infinitely.” | Can spin, duplicate side effects, and still lack consistency. | Design proper synchronization or snapshots. |
| “`List.set` always causes CME like `add`.” | `ArrayList.set` is non-structural and usually does not invalidate. | Distinguish content mutation vs. structural mutation. |
| “`HashMap.put` is always structural.” | Updating an existing key's value differs from adding a mapping. | Check whether keys are added or removed. |

## 23. Debugging Skills When Facing `ConcurrentModificationException`

When a stack trace reports CME:

1. **Find the exact collection** being traversed, not just the class name at the top of the trace.
2. Identify the traversal style: enhanced for, `Iterator`, `ListIterator`, `forEach`, stream/spliterator, or a `subList` view.
3. Look for **structural modifications** that could happen between iterator creation and the check: `add`, `remove`, `clear`, `sort`, indirect method calls, callbacks, or other threads.
4. Check whether modifications go through **the iterator itself**.
5. If multiple threads are involved, verify **the same lock** or an appropriate concurrent collection; do not just wrap in a catch block.
6. If using `subList`, check whether the backing list was directly structurally modified.
7. If using an access-order `LinkedHashMap`, check whether `get` alters iteration order.
8. Inspect ownership, lifecycle, and aliases: the same list may be passed across multiple methods or layers.
9. Write a single-threaded test to reproduce a faulty mutation path if it is a pure logic bug; for concurrency, use appropriate tests/stress tests, but **never** rely on a single “no CME” run to conclude safety.
10. Fix the invariant, choose the right removal API, snapshot, or synchronization; verify state and side effects after failure.

### 23.1. Why Does the Stack Trace Often Point to `next()`?

CME can be thrown **at the point of detection**, not on the exact line that first mutated the collection. The stack trace may point to `ArrayList$Itr.next`, while the offending `list.add/remove` happened on an earlier line.

Therefore, trace backward along the structural modification path rather than concluding that `next()` is “the broken method” or that the JDK has a bug. If the modification comes from a deep callback or another thread, observing ownership and contextual logs matters more than staring at a single stack line.

### 23.2. What Should Logging Record?

You can log the operation name, collection type, size at a safe point, task/correlation ID, and the exception, without dumping the entire collection containing sensitive data. For concurrency bugs, logging contextual event ordering helps reproduction far more than the CME message alone (which usually carries little detail).

## 24. Testing and Verifying Behavior

Some testing directions:

- **Single-threaded iterator invalidation:** create an `ArrayList` iterator, call `next()`, structurally modify, then call `next()`; on JDK 17, expect CME in a controlled demo.
- **Iterator.remove:** verify the exact remaining elements after removal without needing a catch block.
- **ListIterator:** verify insertion/replacement through the iterator on a mutable list.
- **removeIf:** verify the predicate filters accurately without unintended side effects.
- **CopyOnWriteArrayList:** create an iterator, add a new element, and verify the snapshot does not see the new element.
- **ConcurrentHashMap:** test valid concurrent operations per the API, **without asserting order or that the iterator must see all interleaved updates**.
- **synchronizedList:** write tests designed around the shared lock, without treating the absence of CME in a stress test as the sole proof.
- **Stream:** test filtered/computed results, avoiding callbacks that mutate the source.

### 24.1. Illustrative JUnit 5 Example

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.ArrayList;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;
import org.junit.jupiter.api.Test;

class FailFastContractTest {
    @Test
    void iteratorDetectsDirectStructuralChangeOnArrayListJdk17() {
        List<String> values =
                new ArrayList<>(List.of("A", "B", "C"));
        Iterator<String> it = values.iterator();
        assertEquals("A", it.next());
        values.add("D");

        assertThrows(ConcurrentModificationException.class, it::next);
    }

    @Test
    void iteratorRemoveIsLegal() {
        List<Integer> values =
                new ArrayList<>(List.of(1, 2, 3, 4));
        Iterator<Integer> it = values.iterator();

        while (it.hasNext()) {
            if (it.next() % 2 == 0) {
                it.remove();
            }
        }

        assertEquals(List.of(1, 3), values);
    }
}
```

This is a **JUnit Jupiter test file**, not a standalone `javac` program runnable with only the JDK. The first test intentionally verifies JDK 17 `ArrayList` behavior under specific conditions; **it does not mean every fail-fast collection on every JVM must throw CME under all execution schedules**.

### 24.2. Concurrency Testing Is Not the Same as Verifying Concurrency Contracts

A stress test passing multiple times is still not enough to prove code with a data race is correct. You must reason against the **Java Memory Model**, ensuring synchronization and collection contracts are met. For high correctness, design with invariants, ownership, atomic operations, or appropriate concurrent structures first, then use tests to catch mistakes.

## 25. Frequently Asked Questions

**1. Why can a single thread still cause CME?** Because code can structurally modify an `ArrayList` outside an active iterator within the same thread. “Concurrent” in the name does not require two threads.

**2. Does adding `synchronized` always fix CME?** No. Proper locking coordinates threads, but the same thread calling `list.remove(...)` while iterating with an iterator can still break the contract; when supported, use `Iterator.remove()`.

**3. Why does CME happen sometimes and not other times?** Fail-fast detection is **best effort**; cursor position, check points, and concurrency timing affect detection. Do not use the exception as the sole correctness test.

**4. Can I catch CME, create a new iterator, and retry?** Only if you have accounted for data consistency, side effects, and retry safety; it is not a default substitute for ownership or synchronization.

**5. Does `ArrayList.set` always invalidate the iterator?** No. On `ArrayList`, replacing an existing element is generally not a structural modification; this **does not** provide thread-safety guarantees.

**6. Does `removeIf` apply to every collection?** No. Collections that do not support removal can throw `UnsupportedOperationException`; predicates also should not mutate the source being traversed.

**7. Are snapshot and weakly consistent the same?** No. A `CopyOnWriteArrayList` iterator uses a snapshot at creation time, whereas a `ConcurrentHashMap` iterator may observe some interleaved updates. “Fail-safe” is not the official contract name for either iterator type.

**8. Does fail-fast detect all data races?** No. The presence or absence of CME does not replace Java Memory Model rules, locking, and safe publication.

**9. Should I use `Collections.synchronizedList` or `CopyOnWriteArrayList`?** Choose based on read/write frequency, copy cost, and required consistency; with a synchronized list, you still need to lock **across the entire traversal** when using an iterator.

**10. Why is `subList` related to CME?** `subList` is typically a view of the backing list; structurally modifying the backing list outside supported mechanisms can invalidate the view or its iterator.

**11. How do `filter` and `removeIf` differ?** `filter` selects elements to build a pipeline/result, whereas `removeIf` mutates the source when the collection supports it; do not structurally mutate the source from a Stream callback.

**12. Does CME automatically roll back previous operations?** No. The check happens on already-mutated state; for instance, an `add` operation may complete before the next iterator check throws CME.

The summarized answers here should be understood alongside the iterator models, consistency guarantees, and examples analyzed in earlier sections; do not use them as a substitute for verifying the contract of a specific collection.

## 26. Practice Exercises

### Exercise 1 — Single-Threaded CME

Run `SingleThreadCmeDemo` and trace the sequence: create iterator → next → add → next. Why does having only one thread not prevent CME? **Hint:** the iterator recorded the old structure and was modified outside its own mechanism.

### Exercise 2 — Fixing Properly with an Iterator

Convert a `for-each` loop that removes names from a list to use `Iterator.remove()`. Test lists with 0, 1, 2, and many elements. Verify removing the first, middle, and last elements.

### Exercise 3 — Using `ListIterator`

Extend `ListIteratorEditDemo`: replace `A` with `A-done`, insert `B-extra` after `B`, and remove `C` using `it.remove()` after `next()` returns `C`. Predict the final list and run to verify.

### Exercise 4 — `removeIf` Without Relying on Fail-Fast Intuition

Use `List.of("An","Bình","Chi","Dũng")` as input, create a mutable copy, and remove strings with `length() <= 2`. Predict the exact remaining elements based on `String.length()`, not visual character counting.

### Exercise 5 — Finding the “No CME” Bug

Run `FailFastNotGuaranteedDemo`. Explain why `hasNext()` can return `false` after removing the first element and why this proves **you must not rely on fail-fast to validate structure**.

### Exercise 6 — Snapshot Iterator

Run `CopyOnWriteSnapshotDemo`. Add `D` after creating the iterator and before traversing. Does the snapshot see `D`? Does the current list see it? Try `snapshot.remove()` and predict the exception type.

### Exercise 7 — Weak Consistency

Using `ConcurrentHashMap`, create an iterator and then add a key. Write a test that only checks guarantees the API actually provides, **without asserting that the new key must be observed** during traversal concurrent with updates.

### Exercise 8 — Locking with Sufficient Scope

Given a `Collections.synchronizedList` and two threads—one iterating, one mutating—write an example where both follow `synchronized(syncList)`. Why is locking each `next()` call separately not equivalent to locking the entire traversal?

### Exercise 9 — `HashMap` Value vs. Structural Modification

Create a `HashMap` with two keys, create an iterator, then `put` an existing key with a new value and observe. Compare with adding a new key. Explain based on Map structural modification, not “`put` is always dangerous.”

### Exercise 10 — Stream and Non-Interference

Write a `source.stream().filter(...).toList()` pipeline to produce a list containing only odd numbers. Compare it with a `forEach` callback attempting to mutate `source` during traversal. Why is only one of them appropriate when you want to keep the source unchanged?

### Exercise 11 — Concurrency and Consistency

A service has a listener list that is updated very rarely but traversed thousands of times per second. Compare `CopyOnWriteArrayList` with a synchronized list: per-update cost, iterator consistency, and lock management.

### Exercise 12 — View Bug

Create a `subList` from an `ArrayList`, then mutate the backing list directly and attempt to read the view. Explain why code must not treat the resulting behavior or a specific CME as a portable contract; propose a snapshot when an independent view is needed.

## 27. Checklist Before Concluding Code Is Safe

- [ ] Have I distinguished that CME is an unchecked runtime exception and does not require `throws`?
- [ ] Do I know that a single thread can also trigger CME by mutating a collection outside the iterator?
- [ ] Do I understand that fail-fast is for **best-effort** bug detection, not a 100% guarantee?
- [ ] Do I know whether the current iterator/collection is fail-fast, snapshot, or weakly consistent?
- [ ] Have I identified what counts as a structural modification for that specific implementation?
- [ ] Am I avoiding direct `list.add/remove` calls inside an enhanced-for loop over the same list?
- [ ] If I need to remove during traversal, am I using `Iterator.remove` where supported and in the valid state?
- [ ] If inserting/replacing while iterating a list, have I considered `ListIterator` where appropriate?
- [ ] If the goal is conditional removal, does `removeIf` have a suitable contract for a mutable list?
- [ ] Am I avoiding using CME for infinite retries, measuring data races, or proving thread safety?
- [ ] Do I remember that `modCount/expectedModCount` are implementation details, not a general public contract?
- [ ] Have I considered the path where `hasNext()` ends before the next modification check?
- [ ] If using `CopyOnWriteArrayList`, do I accept the stale snapshot and the copy cost on writes?
- [ ] If using `ConcurrentHashMap`, am I avoiding the assumption that the iterator always sees all interleaved updates?
- [ ] If using `Collections.synchronizedList`, am I holding the lock across the entire traversal and ensuring all writers use the same lock?
- [ ] If taking a snapshot, have I ensured the snapshot is captured from a source in a consistent state?
- [ ] Am I avoiding out-of-contract modifications to the backing list while a `subList` is still in use?
- [ ] With Streams, do my callbacks avoid structurally mutating the source while the pipeline is running?
- [ ] When CME occurs, do I inspect side effects rather than assuming data rolled back automatically?
- [ ] Have I tested the required contract/behavior instead of only testing “did not throw CME”?

**Conclusion:** `ConcurrentModificationException` is **an inconsistency detection signal in certain traversal mechanisms**, not proof of two threads and not a system that guarantees catching every modification. Fail-fast works on a *best-effort* basis. Choose the right tool: `Iterator.remove()`, `ListIterator`, or `removeIf` for valid mutation; `CopyOnWriteArrayList` for snapshots in read-heavy, write-rare scenarios; `ConcurrentHashMap` for weakly consistent traversal; and external synchronization across the entire iteration when using `Collections.synchronizedList`. Most importantly, design **ownership, consistency, and concurrency contracts**, and never use the presence or absence of CME as the sole measure of correctness.
