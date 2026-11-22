# Fail-Fast Mechanism and the Guarantee Limits of ConcurrentModificationException

While iterating over a collection, adding or removing elements through another path can cause the position held by the iterator to no longer correspond to the data source. Many iterators of general-purpose collections use a **fail-fast** mechanism to detect certain improper modifications and throw `ConcurrentModificationException`.

The most important point is: **fail-fast is a bug-detection aid, not a mechanism that guarantees data access or iteration is always correct**. The exception can occur in a single-threaded program. Conversely, the absence of an exception does not prove that iteration did not skip elements or that multi-threaded access is safe.

Throughout this article, the abbreviation `CME` refers to `ConcurrentModificationException`.

## 1. The Problem That Fail-Fast Attempts to Detect

Suppose an iterator is traversing A, B, C:

~~~text
Source when iterator was created: [A, B, C]
Iterator has retrieved: A
Expected next elements: B, C
~~~

Another piece of code removes B directly from the list:

~~~text
Current source: [A, C]
Iterator still carries state from the traversal before the modification
~~~

The iterator may be holding an index, a node, an expected modification count, or other information belonging to a structure that has changed. If it simply continues without a clear policy, the program might skip elements, read duplicates, observe unexpected data, or fail.

Fail-fast chooses to detect signs of inconsistency at certain checkpoints and report an error. This helps uncover bugs earlier in many situations, but it does not turn the iterator into an independent snapshot of the source.

## 2. ConcurrentModificationException Does Not Require Multiple Threads

A single-threaded example:

~~~java
// Code snippet inside a method; requires corresponding java.util imports.
List<String> values = new ArrayList<>(List.of("A", "B", "C"));
Iterator<String> iterator = values.iterator();

System.out.println(iterator.next()); // A
values.remove("B"); // Modify directly via List, not through the active iterator.

iterator.next(); // May detect modification and throw CME in a fail-fast implementation.
~~~

There is no `Thread`, executor, or parallel execution. The very same thread:

1. Created the iterator.
2. Traversed part of the data.
3. Structurally modified the source via `values`.
4. Continued using the old iterator.

The name “concurrent modification” does not only describe situations where multiple threads execute simultaneously. A single thread can also violate the usage rules of a data source while an active traversal is still in progress. The documentation for [ConcurrentModificationException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ConcurrentModificationException.html) explicitly states this limitation and warns against relying on the exception for program correctness.

`CME` is an unchecked exception extending `RuntimeException`. There is no requirement to catch it at every iterator call.

## 3. Common Model: Modification Counter and Expected Value

In an implementation such as `ArrayList`'s iterator, you can picture the model as follows:

- The collection maintains a modification counter, commonly seen under the name `modCount`.
- When an iterator is created, it records the expected value, commonly seen under the name `expectedModCount`.
- Certain iterator operations check whether the two values still match.
- If a mismatch is detected, the iterator throws `CME`.

Pseudocode illustrating the idea:

~~~java
// Pseudocode explaining the mechanism, not a standalone program.
void checkForModification() {
    if (collectionVersion != iteratorExpectedVersion) {
        throw new ConcurrentModificationException();
    }
}
~~~

This is not an API protocol that every collection is required to use. Do not access or modify internal counters from application code to “repair” an invalidated iterator.

A simple flow:

~~~mermaid
flowchart TD
    A["Create iterator and store expected version"] --> B["Proceed to a checked operation"]
    B --> C{"Does source version still match?"}
    C -->|Yes| D["Continue traversal operation"]
    C -->|No| E["Throw ConcurrentModificationException"]
    D --> B
~~~

The diagram does not say that every method performs a check or that modifying the source throws an error immediately at the moment of modification.

### The Counter Is Not Just the Size

Adding an element and then removing that exact element may restore the contents and size to what they were before, yet structural modifications have occurred since the iterator was created.

~~~java
List<String> values = new ArrayList<>(List.of("A", "B", "C"));
Iterator<String> iterator = values.iterator();

values.add("D");
values.remove("D");

// Contents are [A, B, C] again, but the iterator must not be assumed valid again.
~~~

The verification program below detects the modification when continuing with this iterator. Do not compare `size()` before and after to conclude that no traversal-relevant modification occurred.

Also, do not assume that every method updates the counter according to a single formula or always increments it by exactly one unit. That is an implementation detail, not a version-control interface for applications.

## 4. Structural Modification vs. Value Replacement

For `ArrayList`, adding or removing elements or explicitly altering the backing array structure are structural modifications. Merely replacing an element with `set` is not considered a structural modification according to the class definition. At the same time, the documentation emphasizes that fail-fast is a best-effort detection mechanism, not an absolute guarantee. See the [ArrayList API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

Table for a standard `ArrayList` context:

| Operation | Meaning Relative to Traversal |
| --- | --- |
| `list.add(value)` | Structurally modifies the source. |
| `list.remove(...)` that actually removes an element | Structurally modifies the source. |
| `list.set(index, value)` | Replaces the value at an existing position; not a structural modification by ArrayList's definition. |
| Mutating a property of an object inside the list | Does not itself structurally modify the list; the object's content may still have changed. |
| Modifying through another iterator of the same source | Still represents an external modification path relative to the current iterator. |

In a sequential example:

~~~java
List<String> values = new ArrayList<>(List.of("A", "B", "C"));
Iterator<String> iterator = values.iterator();

iterator.next(); // A
values.set(1, "B*");
System.out.println(iterator.next()); // B* with ArrayList in this example.
~~~

An iterator is not an immutable snapshot. The absence of `CME` after `set` does not mean the iterator still observes the initial contents.

Do not generalize this table into a rule that “every collection type can only invalidate an iterator when its size changes.” Each data source has its own structure, method contracts, and traversal policy.

In particular, do not use the fact that a certain kind of modification goes undetected by the counter to conclude that it is thread-safe or valid for the business algorithm being executed.

## 5. Why Modifying Through the Iterator Itself Can Be Valid

When an iterator supports `remove()`, it can both modify the underlying source and adjust its own traversal state and expected version:

~~~java
List<String> values = new ArrayList<>(List.of("A", "B", "C"));
Iterator<String> iterator = values.iterator();

while (iterator.hasNext()) {
    String value = iterator.next();
    if (value.equals("B")) {
        iterator.remove();
    }
}

System.out.println(values); // [A, C]
~~~

Do not replace `iterator.remove()` with `values.remove(value)` and assume the two operation paths are equivalent.

A mutable `ListIterator` additionally provides `add` and `set` with their own state rules. Such permitted modifications must go through **the exact iterator currently in use**, under valid state conditions, and on a source that supports them.

### One Valid Iterator Does Not Protect Other Iterators

If two iterators `first` and `second` exist on the same ArrayList, `first.remove()` can properly update `first`'s state. However, `second` does not automatically get its expected state updated as a result.

Similarly, modifying a list properly in one section of code does not automatically revalidate older iterators still retained elsewhere.

This is why you must define the lifecycle and source-modification authority of each traversal rather than merely asking whether “`iterator.remove` was used somewhere.”

## 6. Fail-Fast Does Not Mean Checking on Every Call

An iterator may check during `next()`, `remove()`, certain steps of `forEachRemaining`, or other points. There is no universal rule that `hasNext()` always performs a complete check for all modifications.

With OpenJDK 24.0.2 used to run the examples in this article, inspecting the bytecode of `ArrayList$Itr` shows:

- `hasNext()` compares the cursor position against the current size.
- `next()` invokes the modification check before retrieving data.

You can inspect this yourself on the JDK you are using:

~~~shell
javap -c -p 'java.util.ArrayList$Itr'
~~~

Internal class names and bytecode details are only for understanding the running version. Application code must not rely on them to choose source-modification paths that “evade the check.”

### Example Where Elements Can Be Skipped Without CME

~~~java
List<String> values = new ArrayList<>(List.of("A", "B"));
List<String> visited = new ArrayList<>();

for (String value : values) {
    visited.add(value);
    if (value.equals("A")) {
        values.remove(value);
    }
}
~~~

In the verification run for this article:

~~~text
visited = [A]
values  = [B]
No CME thrown
~~~

What happens in the observed implementation:

1. The iterator retrieves A, and the cursor advances to index `1`.
2. Removing A directly leaves B at index `0`, with size `1`.
3. `hasNext()` compares cursor `1` against size `1`, and therefore terminates.
4. `next()` is never called again to reach the point where the version mismatch would be detected.

B remains in the list but is never added to `visited`.

This illustrates the limits of detection, not valid behavior for an application to exploit. Do not write logic that depends on “this loop silently skipping an element” or cross-platform tests forcing every JDK to reproduce this exact phenomenon.

## 7. Best-Effort: Guarantee Limits to Understand

“Best-effort detection” in the fail-fast context has the following implications:

- A detected sign of modification may cause the traversal to fail.
- There is no guarantee that every improper modification will be detected.
- There is no guarantee that the exception will occur right at the statement that modifies the source.
- There is no guarantee that every iterator method checks at the exact same point across versions.
- There is no guarantee that the absence of an exception means you have a consistent data snapshot.

In unsynchronized multi-threaded situations, memory visibility and execution ordering issues also come into play. A modification-detection counter does not by itself provide locking, atomicity, happens-before relationships, or a read transaction.

Even if an observed field were changed to `volatile` in a custom design, seeing the new counter value would not automatically turn the sequence “check then retrieve element” into an atomic operation. Synchronization must be designed at the appropriate level.

Do not build program correctness around the model:

~~~text
CME occurs -> data is unsafe
No CME occurs -> data is safe
~~~

The second branch does not exist as a general guarantee.

## 8. Fail-Fast Does Not Roll Back Completed Work

In the example where B is removed after A has already been processed, the error may only surface on the subsequent iterator call. Before that point:

- The action for A may have already executed.
- The list may have already been modified.
- Logs, counters, files, or external tasks may have already been written.

Catching `CME` neither restores the source data nor undoes those side effects.

Do not catch and ignore it:

~~~java
// Insufficient idea to guarantee algorithmic correctness.
try {
    // Traverse and perform work.
} catch (ConcurrentModificationException exception) {
    // Ignoring the exception does not prove all elements were processed.
}
~~~

Likewise, do not automatically rerun the entire loop just because `CME` was caught. If a notification was already sent for A during the previous attempt, retrying may send A a second time, while the source data may continue changing.

Only retry when you have an appropriate design for data ownership, snapshots, idempotency, and business checkpoints. For many single-threaded bugs, the proper fix is simply changing how the source is modified or separating the read and update phases.

## 9. Hard-to-Spot Source Modification Paths

Direct calls to `values.add/remove` inside the loop body are not the only ones that matter.

### Aliases to the Same Object

Two variables with different names can point to the exact same collection:

~~~java
List<String> values = new ArrayList<>(List.of("A", "B", "C"));
List<String> alias = values;
Iterator<String> iterator = values.iterator();

alias.remove("B"); // Still modifies the exact source used by the iterator.
~~~

Renaming a variable does not create a copy or a new ownership boundary.

### Views and Backing Collections

Views such as `subList`, `keySet`, `values`, or `entrySet` remain connected to their backing collection. Modifying through one path can affect an active traversal on another path, according to the contract of the specific source type.

Do not assume a view is an independent snapshot. With `ArrayList`, structurally modifying the parent list while still using a `subList` carries contract limitations of its own, beyond just invalidating an individual iterator.

### Callbacks or Nested Calls

A loop body might simply call:

~~~java
process(value);
~~~

yet `process` modifies the source collection, or publishes an event to code that modifies it. When investigating, trace actual write paths rather than just searching for the word `remove` within the same method.

### Unmodifiable Views Are Not Snapshots

`Collections.unmodifiableList(backing)` blocks modifications through that view. If another place still holds and modifies `backing`, the view's data and iterators do not automatically become an immutable copy.

Holding a read-only wrapper is different from creating an independent dataset for iteration.

## 10. Choosing the Right Approach for a Single Thread

| Need | Commonly Appropriate Approach |
| --- | --- |
| Remove elements matching a condition from a mutable source | `removeIf`, or a loop with `iterator.remove` if supported. |
| Traverse a List while inserting/replacing/removing at the current position | `ListIterator` with a valid sequence of operations. |
| Keep the source intact and produce filtered data | Create a new result collection. |
| Add multiple elements after traversing the source | Collect into an auxiliary collection and add in a subsequent phase. |
| Read a fixed state | Capture a snapshot using an appropriate procedure, then iterate over the snapshot. |

Example of conditional removal:

~~~java
List<String> values = new ArrayList<>(List.of("A", "B", "C"));
values.removeIf(value -> value.equals("B"));

System.out.println(values); // [A, C]
~~~

Do not mutate the source collection itself inside the predicate of `removeIf`. Using a dedicated API does not grant the callback permission to perform arbitrary extra modifications on the collection being processed.

If you merely rewrite the loop to use index-based iteration so that no iterator is involved, the program might no longer throw the same exception. However, the logic can still skip elements due to index shifting, and multi-threaded access remains unsolved. The goal is algorithmic correctness, not making an error message disappear.

## 11. With Multiple Threads: Locking Must Protect the Entire Traversal

`ArrayList` does not provide built-in synchronization for concurrent access and structural modification across multiple threads. One option is wrapping it with `Collections.synchronizedList`, but during iteration you must hold the lock across the proper scope and every access path to the source must follow the same synchronization protocol. See [Collections.synchronizedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedList(java.util.List)).

~~~java
// Illustrates part of a design; requires corresponding java.util imports.
List<String> shared =
        Collections.synchronizedList(new ArrayList<>());

// Other code sections must also access shared following the proper synchronization rules.
synchronized (shared) {
    Iterator<String> iterator = shared.iterator();
    while (iterator.hasNext()) {
        String value = iterator.next();
        System.out.println(value);
    }
}
~~~

Locking only when creating the iterator and releasing the lock before the loop does not protect the entire traversal.

Locking each individual `hasNext` and `next` call is also not equivalent to holding a single lock throughout the loop if the algorithm requires an uninterrupted read pass without interleaved modifications.

Even while holding the lock, the current thread itself can still improperly modify the source inside the loop body and invalidate the iterator. Locking resolves interleaved access across threads according to a protocol; it does not abolish the iterator's state rules.

### Taking a Quick Snapshot Under Lock and Processing Outside the Lock

If processing takes a long time and only requires the contents at the moment of capture:

~~~java
List<String> snapshot;
synchronized (shared) {
    snapshot = new ArrayList<>(shared);
}

for (String value : snapshot) {
    System.out.println(value);
}
~~~

The snapshot is structurally independent as a list, but it is a shallow copy: the element objects themselves may still be shared. You must define a policy for any mutable state inside the elements.

Also, do not create a snapshot of an `ArrayList` while another thread is modifying it without a proper synchronization protocol and assume the copy operation itself guarantees a consistent snapshot.

## 12. Iterator Policies Other Than Fail-Fast

Not every iterator chooses to detect modifications and throw `CME`.

| Policy | Example | What to Understand |
| --- | --- | --- |
| Fail-fast | Iterators of many general-purpose collections such as ArrayList | Helps detect improper modifications on a best-effort basis. |
| Snapshot at iterator creation time | Iterator of CopyOnWriteArrayList | Traverses the state captured when the iterator was created; does not reflect subsequent structural changes. |
| Weakly consistent | Iterator of ConcurrentHashMap | Can operate concurrently with updates according to the source's policy; not an atomic point-in-time snapshot of the entire map. |

The iterator of [CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html) holds a structural snapshot taken when it is created; mutating operations through the iterator such as `remove` are unsupported. This mechanism carries write and memory overhead that must be weighed carefully—it is not a default replacement for every list.

Example:

~~~text
Source when iterator was created: [A, B]
Source later adds C and removes A: [B, C]
Snapshot iterator still traverses: [A, B]
~~~

The snapshot covers the set of element references for the traversal; it does not automatically deep-copy the objects themselves.

The iterator of [ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html) does not throw `CME` by policy. That does not mean a traversal yields a transactional snapshot of the entire map, and an iterator instance itself is not meant to be arbitrarily shared across multiple threads concurrently advancing its cursor.

Do not lump these alternatives under a single “fail-safe” label and assume all guarantees regarding update visibility, snapshots, write operations, or synchronization are identical. Always refer to the specific policy documented by the concrete class.

## 13. Complete Verification Program

Save as **FailFastLimitsDemo.java**.

The code uses APIs available since Java 17. The sections that deliberately violate traversal rules are **observational experiments**, not sample application code to copy into production. The observed output below was verified on OpenJDK 24.0.2; in particular, the faulty loop that does not throw `CME` is an implementation-dependent detail that should be re-observed if you change runtimes.

Do not turn an unguaranteed phenomenon into a cross-version behavioral requirement.

~~~java
import java.util.ArrayList;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

public class FailFastLimitsDemo {
    public static void main(String[] args) {
        System.out.println("Runtime feature = " + Runtime.version().feature());
        directModification();
        sameSizeAfterTwoChanges();
        nonStructuralReplacement();
        skippedWithoutException();
        safeIteratorRemoval();
        safeRemoveIf();
        snapshotIteration();
    }

    private static void directModification() {
        List<String> values = new ArrayList<>(List.of("A", "B", "C"));
        Iterator<String> iterator = values.iterator();
        System.out.println("Direct edit first = " + iterator.next());
        values.remove("B");
        try {
            System.out.println("Direct edit next = " + iterator.next());
        } catch (ConcurrentModificationException exception) {
            System.out.println("Direct edit detected = "
                    + exception.getClass().getSimpleName());
        }
        System.out.println("After detected edit = " + values);
    }

    private static void sameSizeAfterTwoChanges() {
        List<String> values = new ArrayList<>(List.of("A", "B", "C"));
        Iterator<String> iterator = values.iterator();
        values.add("D");
        values.remove("D");
        System.out.println("Same contents restored = " + values);
        try {
            iterator.next();
            System.out.println("Restored contents detected = false");
        } catch (ConcurrentModificationException exception) {
            System.out.println("Restored contents detected = true");
        }
    }

    private static void nonStructuralReplacement() {
        List<String> values = new ArrayList<>(List.of("A", "B", "C"));
        Iterator<String> iterator = values.iterator();
        iterator.next();
        values.set(1, "B*");
        System.out.println("Next after ArrayList.set = " + iterator.next());
    }

    private static void skippedWithoutException() {
        List<String> values = new ArrayList<>(List.of("A", "B"));
        List<String> visited = new ArrayList<>();
        boolean detected = false;
        try {
            for (String value : values) {
                visited.add(value);
                if (value.equals("A")) {
                    values.remove(value);
                }
            }
        } catch (ConcurrentModificationException exception) {
            detected = true;
        }
        System.out.println("Short loop visited = " + visited);
        System.out.println("Short loop remaining = " + values);
        System.out.println("Short loop detected = " + detected);
    }

    private static void safeIteratorRemoval() {
        List<String> values = new ArrayList<>(List.of("A", "B", "C"));
        Iterator<String> iterator = values.iterator();
        while (iterator.hasNext()) {
            String value = iterator.next();
            if (value.equals("B")) {
                iterator.remove();
            }
        }
        System.out.println("Iterator removal = " + values);
    }

    private static void safeRemoveIf() {
        List<String> values = new ArrayList<>(List.of("A", "B", "C"));
        values.removeIf(value -> value.equals("B"));
        System.out.println("removeIf = " + values);
    }

    private static void snapshotIteration() {
        CopyOnWriteArrayList<String> values =
                new CopyOnWriteArrayList<>(List.of("A", "B"));
        Iterator<String> snapshot = values.iterator();
        values.add("C");
        values.remove("A");

        List<String> observed = new ArrayList<>();
        snapshot.forEachRemaining(observed::add);
        System.out.println("Snapshot observed = " + observed);
        System.out.println("Copy-on-write current = " + values);
    }
}
~~~

Compile with JDK 17 or later:

~~~shell
javac --release 17 -encoding UTF-8 FailFastLimitsDemo.java
java FailFastLimitsDemo
~~~

`--release 17` checks the target language/API level at compile time; it does not turn the JVM executing the program into Java 17.

Stdout from the verification run on OpenJDK 24.0.2:

~~~text
Runtime feature = 24
Direct edit first = A
Direct edit detected = ConcurrentModificationException
After detected edit = [A, C]
Same contents restored = [A, B, C]
Restored contents detected = true
Next after ArrayList.set = B*
Short loop visited = [A]
Short loop remaining = [B]
Short loop detected = false
Iterator removal = [A, C]
removeIf = [A, C]
Snapshot observed = [A, B]
Copy-on-write current = [B, C]
~~~

### Interpreting the Evidence Within Its Proper Limits

**Direct edit**

A was retrieved, and then B was removed directly. The next call to `next` detected the modification. The list had already become A, C before the exception was reported; the exception did not undo the removal of B.

**Same contents restored**

Adding D and then removing D restored the contents to A, B, C. The iterator created before those two changes was still detected as invalid. The final size or contents cannot substitute for the modification history relevant to the iterator.

**ArrayList.set**

Replacing B with B* is not a structural change under `ArrayList`'s policy. The sequential `next` call observes B*, showing that the iterator does not hold an initial copy of the elements.

**Short loop**

Only A was added to `visited`, B remained in the source, and no `CME` occurred in this run. This is concrete evidence that the absence of an exception does not mean the algorithm traversed all elements.

**Iterator removal and removeIf**

Both contractual approaches on `ArrayList` modify the source cleanly and produce A, C as intended. They do not depend on whether a fail-fast exception happens to be triggered.

**Copy-on-write snapshot**

The iterator was created when the source contained A, B. The source later became B, C, yet the iterator still observed A, B according to its snapshot policy. This is a different policy from fail-fast, not fail-fast “failing to work.”

The program does not involve random multi-threaded scheduling. Consequently, the examples isolate single-threaded iterator misuse from synchronization issues. When studying concurrent access, test the specific guarantees of your concurrency design rather than using the probability of `CME` appearing as a metric.

## 14. How to Investigate When Encountering CME

1. **Identify the actual source:** Is it an `ArrayList`, `HashMap`, a view, a wrapper class, or a concurrent structure?
2. **Identify when the iterator is created:** Is it retained across multiple phases, callbacks, or method calls?
3. **Find all write paths:** Alias variables, parent lists, views, callbacks, listeners, or other threads.
4. **Check the policy:** Is the modification performed through the exact active iterator and supported by it?
5. **Review work executed before the error:** Are there side effects that need handling or must not be repeated when fixing the issue?
6. **Choose the right model:** Modify via the iterator, separate phases, take a data snapshot, lock across the proper scope, or use an appropriate concurrent data structure.

A stack trace typically points to where the iterator **detected** the inconsistency, not necessarily to the statement that modified the source. Therefore, only changing the line that throws without tracing the write path may mask the symptom without fixing the root cause.

After fixing the issue, verify the resulting contents, the number of processed elements, the number of side effects, and the update visibility policy. Do not stop at “it runs without throwing an exception.”

## 15. Testing and Common Pitfalls

Test cases to cover:

- Direct modification on the same thread after creating an iterator.
- Modification through an alias or the backing collection behind a view.
- Removing the first, middle, and near-last elements in lists of various sizes.
- Adding and then removing an element so the final contents return to their original state.
- Using `iterator.remove` under valid conditions.
- Two iterators on the same source where only one iterator performs a modification.
- Capturing a snapshot and verifying the policy for observing the previous state.
- Concurrent read and write paths following the designed synchronization protocol.

An experimental test case may record `CME` for illustration. However, correctness tests for application code must verify business invariants and results. Do not require that a source-misuse bug must always throw `CME` at a specific line across every Java version.

| Misconception | Proper Understanding to Keep |
| --- | --- |
| CME is only caused by multiple threads | A single thread modifying the source while an iterator is still in use can also trigger it. |
| Modifying the source throws immediately | The error is typically detected at a subsequent checkpoint during traversal. |
| hasNext always checks the counter | Checkpoints depend on the implementation; do not rely on this assumption. |
| No CME means everything was traversed | Elements can be skipped or observed inconsistently without an exception being thrown. |
| Unchanged final size means the iterator is still valid | Structural modifications may still have caused the expected version to diverge. |
| set does not cause CME so it is automatically thread-safe | Non-structural modification does not imply synchronization or snapshot semantics. |
| Catching and retrying is a general fix | Completed work may be duplicated while the source continues changing. |
| A synchronized wrapper automatically locks the whole loop | You must synchronize across the entire traversal scope per contract and across all access paths. |
| Concurrent structures always provide a full snapshot | Weakly consistent semantics differ from a point-in-time snapshot. |
| Switching to an index-based loop solves everything | It can still be broken due to index shifting, skipped elements, and concurrent access. |

## 16. Practice

1. Run the sample program on your current JDK and record the exact version. Distinguish observed behavior from contractual API guarantees.
2. Replace the two-element list in `skippedWithoutException` with three or four elements. Do not pre-impose a requirement that it “must always throw”; inspect which elements are actually visited.
3. Rewrite the direct removal example to use `iterator.remove`, and then `removeIf`. Verify the resulting data rather than merely verifying the absence of an exception.
4. Create two variables referencing the same list and modify it through the second variable. Explain why the iterator is still tied to the same underlying source.
5. Design one read pass that requires a consistent snapshot and one monitoring pass that tolerates updates during traversal. Choose an appropriate data policy for each case.
6. For a loop that sends notifications, analyze the risks of catching `CME` and restarting from the beginning. Determine where processing records or idempotency guarantees must be maintained.

`CME` indicates that a sign of improper collection usage has been detected. Correctness must come from source ownership, modification strategy, traversal policy, and synchronization protocol; the presence or absence of the exception is only one piece of evidence when diagnosing bugs.
