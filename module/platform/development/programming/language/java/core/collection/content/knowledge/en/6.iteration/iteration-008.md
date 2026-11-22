# Distinguishing Fail-Fast, Snapshot, and Weakly Consistent Iterators

An iterator is created when a collection is in state `S0`. Before the iterator finishes traversing, the program adds, removes, or replaces data so that the collection transitions to `S1`. What will the iterator do?

There are three contracts to distinguish:

- **Fail-fast:** attempts to detect unauthorized modifications to report a usage error.
- **Snapshot:** continues traversing the state captured by the iterator.
- **Weakly consistent:** allows traversal alongside updates according to the source's guarantees, without providing a complete point-in-time snapshot.

They differ in the meaning of observed data, how modifications are handled, and cost. Choosing cannot rely solely on asking "does it throw an exception or not?".

This article uses Java 17 as the baseline. Four complete programs have been compiled with `--release 17` and executed. For the weakly consistent example, the stdout from a single run is presented separately from the guarantees that can be relied upon; do not turn a single observed result into a promise for every execution.

After this lesson, you will be able to:

- Identify the three traversal styles through the contracts of concrete sources.
- Explain why `ConcurrentModificationException` does not always imply multiple threads.
- Distinguish a structural snapshot from a deep copy of elements.
- Explain why a thread-safe collection does not automatically produce an atomic traversal.
- Choose among locking, copying, and concurrent data structures based on data requirements.

## 1. Starting from a Change During an Iterator's Lifecycle

Suppose the initial source is:

```text
[A, B, C]
```

Sequence of events:

```text
t0: create iterator
t1: iterator receives A
t2: D is added to or B is removed from the source
t3: iterator continues
```

The question is not just "can the loop continue running?". We also need to know:

1. Which state does the data subsequently received by the iterator belong to?
2. Is the modification at `t2` permitted by the source's contract?
3. Can the result be used to draw conclusions about the entire source at a single point in time?
4. Who protects the element objects if they also mutate?

The same enhanced `for` syntax can traverse through iterators with very different contracts. Loop syntax does not determine consistency behavior on its own.

## 2. Comparison Table

| Question | Fail-fast | Snapshot | Weakly consistent |
| --- | --- | --- | --- |
| Primary goal | Detect invalid modifications | Traverse a well-defined structural state | Continue traversal while the source is being updated |
| Is it a full-source snapshot? | No | Yes, within the committed snapshot scope | Not by default |
| Changes after iterator creation | May be detected as an error | Does not change the captured set of references | May be reflected according to the source contract |
| CME due to source modification | Best-effort detection mechanism | Does not occur for changes allowed by the snapshot contract | Does not occur for updates allowed by the traversal contract |
| Modification via iterator | Depends on source and operation | CopyOnWriteArrayList iterator does not support it | Depends on the specific type |
| Example in this article | ArrayList | CopyOnWriteArrayList | ConcurrentHashMap views |

This table is a guide for orientation. When writing code, you must still identify the exact class and the exact API that creates the iterator. Do not infer the entire traversal policy from the interface names `List`, `Set`, or `Map`.

"No CME" also does not answer the snapshot question: both snapshot and weakly consistent iterators can continue when the source changes, but the resulting data carries different meanings.

## 3. Fail-Fast: A Tool for Detecting Usage Errors

An `ArrayList` iterator detects structural modifications that do not go through the mechanisms permitted by the iterator. Adding or removing elements are typical examples; replacing an element's value with `set` is not considered a structural modification by `ArrayList`. This mechanism does not guarantee detecting every violation, especially when updates are unsynchronized. See the [Java 17 ArrayList contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

### Explanatory Model Using Version Numbers

You can visualize an implementation tracking:

```text
Structural version of the source
Version expected by the iterator
```

When it detects that the two pieces of information no longer match, the iterator reports that it cannot continue under the current usage.

This is a conceptual model to understand the error-detection intent, not a requirement that every iterator must share the same field names, check timing, or implementation details.

It helps explain two situations:

- Modifying through the active iterator itself, if supported, can update the traversal state in a coordinated manner.
- Modifying the source directly can invalidate an existing iterator.

### A Single Thread Can Also Cause ConcurrentModificationException

A single thread can create an iterator, add directly to the list, and then call the iterator again. A second thread is not required to violate the contract. The [ConcurrentModificationException documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ConcurrentModificationException.html) also emphasizes that this is a bug-detection mechanism, not a condition to guarantee correctness.

Therefore, you should not:

- Treat the presence of the exception as definitive proof that two threads ran concurrently.
- Treat the absence of the exception as proof that the program is bug-free.
- Catch the exception and try to continue on the old iterator.
- Use retrying until the exception disappears as a synchronization mechanism.

An operation may have already caused side effects before the error was detected. Re-running the entire loop can also duplicate work, so "catch and retry" is not a general fix.

## 4. Single-Threaded Fail-Fast Program

Create the file **`FailFastIteratorDemo.java`**:

```java
import java.util.ArrayList;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;

public class FailFastIteratorDemo {
    public static void main(String[] args) {
        List<Integer> values = new ArrayList<>(List.of(1, 2, 3));
        Iterator<Integer> cursor = values.iterator();

        System.out.println("first = " + cursor.next());
        values.add(4);

        try {
            cursor.next();
        } catch (ConcurrentModificationException exception) {
            System.out.println("external add = "
                    + exception.getClass().getSimpleName());
        }

        Iterator<Integer> supported = values.iterator();
        while (supported.hasNext()) {
            if (supported.next() % 2 == 0) {
                supported.remove();
            }
        }
        System.out.println("after iterator removal = " + values);

        List<String> labels = new ArrayList<>(List.of("A", "B"));
        Iterator<String> labelCursor = labels.iterator();
        labels.set(1, "B*");

        List<String> observed = new ArrayList<>();
        labelCursor.forEachRemaining(observed::add);
        System.out.println("replacement observed = " + observed);
    }
}
```

Compile and run:

```text
javac -encoding UTF-8 --release 17 FailFastIteratorDemo.java
java -Dfile.encoding=UTF-8 FailFastIteratorDemo
```

Verified stdout:

```text
first = 1
external add = ConcurrentModificationException
after iterator removal = [1, 3]
replacement observed = [A, B*]
```

### Reading the Three Experimental Parts

**First part:**

1. The iterator receives `1`.
2. The same thread adds `4` directly to the list.
3. The next call to `next` detects the modification and throws CME in this specific scenario.

This is a controlled reproduction with `ArrayList`, not a claim that every kind of modification on every iterator will report an error at the exact same point.

**Second part:**

- The program creates a new iterator on the current list.
- It removes even numbers using `supported.remove()`, through the very iterator performing the traversal.
- The result is `[1, 3]`.

Creating a new iterator here starts a redesigned processing pass after the experiment. It does not illustrate a self-healing algorithm that loops indefinitely after each error.

**Third part:**

- The iterator is created before `labels.set(1, "B*")`.
- The traversal still reads `[A, B*]` in the test.
- This example shows that fail-fast does not mean "freezing all data from the moment of creation".

### Do Not Turn ArrayList Characteristics into Rules for Every Collection

The concept of structural modification depends on the source type. In particular:

- Replacing a value is not adding or removing an element.
- Mutating the internal state of an element object is yet another category of change.
- Operations such as sorting or modifying through a view must be evaluated according to their specific contracts.

Do not assume that as long as `size` stays the same, every change will be accepted by an iterator.

## 5. Snapshot: Preserving the Structural State of a Point in Time

The iterator of `CopyOnWriteArrayList` holds a reference to the state of the backing array at the time the iterator was created. Subsequent additions, removals, or element replacements on the list do not alter the structural data traversed by that iterator. Mutating operations through the iterator such as `remove`, `set`, and `add` are not supported. See [CopyOnWriteArrayList in Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html).

We can sketch the model as follows:

```text
t0:
old iterator -> array containing A, B, C
list         -> array containing A, B, C

t1 after changes:
old iterator -> old array containing A, B, C
list         -> new state containing A*, C, D
```

New elements belonging to the current list do not automatically appear in the old iterator.

### A Snapshot Does Not Mean the Live List Stops Changing

Two facts can be true at the same time:

- One party continues updating the list.
- An existing iterator still traverses a stable set of references.

This fits problems where a processing pass is allowed to use the list as it existed at the start, such as a list of event listeners for a single notification pass. A newly registered listener may simply participate in the next pass, according to the application policy chosen.

### A Structural Snapshot Is Not Automatically a Deep Copy

If an element is a mutable object, the snapshot can still hold a reference to that very same object.

Therefore, you must distinguish between:

1. Replacing the element at a position in the list.
2. Mutating a property inside the object referenced at that position.

The following program verifies this distinction in a single thread, isolating the example from separate questions about cross-thread memory visibility.

## 6. Snapshot Program and Mutable Elements

Create the file **`SnapshotIteratorDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

public class SnapshotIteratorDemo {
    private static final class Score {
        private int value;

        private Score(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        CopyOnWriteArrayList<String> values =
                new CopyOnWriteArrayList<>(List.of("A", "B", "C"));
        Iterator<String> beforeChanges = values.iterator();

        values.set(0, "A*");
        values.remove("B");
        values.add("D");

        List<String> oldView = new ArrayList<>();
        beforeChanges.forEachRemaining(oldView::add);

        System.out.println("old iterator = " + oldView);
        System.out.println("current list = " + values);

        Iterator<String> readOnlyCursor = values.iterator();
        readOnlyCursor.next();
        try {
            readOnlyCursor.remove();
        } catch (UnsupportedOperationException exception) {
            System.out.println("iterator remove = "
                    + exception.getClass().getSimpleName());
        }

        Score sharedScore = new Score(10);
        CopyOnWriteArrayList<Score> scores =
                new CopyOnWriteArrayList<>(List.of(sharedScore));
        Iterator<Score> oldScores = scores.iterator();

        sharedScore.value = 99;
        scores.set(0, new Score(20));

        System.out.println("old element state = " + oldScores.next().value);
        System.out.println("current element state = " + scores.get(0).value);
    }
}
```

Compile and run:

```text
javac -encoding UTF-8 --release 17 SnapshotIteratorDemo.java
java -Dfile.encoding=UTF-8 SnapshotIteratorDemo
```

Verified stdout:

```text
old iterator = [A, B, C]
current list = [A*, C, D]
iterator remove = UnsupportedOperationException
old element state = 99
current element state = 20
```

### String Group

- The iterator is created when the list is `[A, B, C]`.
- The live list changes to `[A*, C, D]`.
- The old iterator still traverses `[A, B, C]`.
- Calling `remove` through a new iterator is still rejected: the ability to modify the list does not imply the ability to modify through its iterator.

### Score Group

1. The old iterator holds a reference to the initial `Score` object.
2. That object's property is changed from `10` to `99`.
3. The live list replaces the element with a new `Score` object holding the value `20`.
4. The old iterator receives the initial object and therefore sees `99`; the current list holds a different object with `20`.

This proves that a snapshot of references does not automatically deep-copy the internal state of elements.

If multiple threads mutate `Score` properties concurrently, the application still needs an immutability or synchronization policy for `Score` itself. Using a concurrent collection does not automatically make every internal field of its elements thread-safe.

### Costs to Consider

From the model of retaining the old array, it follows that a long-lived iterator can extend the lifetime for which old references remain reachable. Writes in a copy-on-write model also incur the cost of copying the backing structure.

Therefore, weigh the read/write ratio, the number of elements, and how long iterators are held. Do not choose copy-on-write merely to silence an exception in code that is misusing its data source.

## 7. Weakly Consistent: Traversable While the Source Updates

Concurrent data structures can provide iterators that allow traversal alongside supported update operations. The [java.util.concurrent package documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html) calls this weakly consistent traversal: data modified after the iterator is created may be reflected, but not every change is guaranteed to appear.

With `ConcurrentHashMap`, iterators do not throw CME for supported updates; the returned elements reflect states at or after the creation of the iterator. It does not provide an atomic snapshot of the entire map. The iterators of this class are designed to be used by only one thread at a time. See the [Java 17 ConcurrentHashMap contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html).

### Conclusions You Must Not Assume

You should not infer that a weakly consistent iterator:

- Always sees all of the latest data by the time the loop finishes.
- Always skips every removed piece of data.
- Always preserves the exact data from when traversal began.
- Automatically captures the entire map at a single point in time.
- Automatically guarantees business invariants spanning multiple keys.

"Weakly" does not mean arbitrary data or the absence of a contract. It means the committed observation level differs from an atomic snapshot; you must rely on the specific guarantees of the class in use.

### Consistency and Ordering Are Two Separate Questions

A map may make no promise about key traversal order while still guaranteeing that traversal remains consistent with supported updates.

If you need to present results in order, you can sort **what has been observed**. However, that sorting step does not turn back time to make the collected data an atomic snapshot.

## 8. Program Observing Old and New Data in the Same Traversal

Create the file **`WeakIteratorDemo.java`**:

```java
import java.util.Iterator;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;

public class WeakIteratorDemo {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, Integer> values = new ConcurrentHashMap<>();
        values.put("A", 10);
        values.put("B", 20);
        values.put("C", 30);

        Iterator<Map.Entry<String, Integer>> cursor =
                values.entrySet().iterator();
        Map<String, Integer> observed = new TreeMap<>();

        Map.Entry<String, Integer> first = cursor.next();
        observed.put(first.getKey(), first.getValue());

        Thread writer = new Thread(() -> {
            values.replaceAll((key, value) -> value + 100);
            values.put("D", 40);
        });

        writer.start();
        writer.join();

        while (cursor.hasNext()) {
            Map.Entry<String, Integer> entry = cursor.next();
            observed.put(entry.getKey(), entry.getValue());
        }

        System.out.println("observed in this run = " + observed);
        System.out.println("after writer = " + new TreeMap<>(values));
        System.out.println("traversal completed = true");
    }
}
```

Compile and run:

```text
javac -encoding UTF-8 --release 17 WeakIteratorDemo.java
java -Dfile.encoding=UTF-8 WeakIteratorDemo
```

Stdout from the **verified run**:

```text
observed in this run = {A=10, B=120, C=130, D=40}
after writer = {A=110, B=120, C=130, D=40}
traversal completed = true
```

The `observed in this run` line shows the data observed in this particular execution, not a fixed value guaranteed across every implementation or execution environment. The map does not enforce alphabetical traversal order; the `TreeMap` in the code merely sorts the output after collection.

### Sequence Controlled by the Program

1. The main thread creates the iterator and retrieves the first entry.
2. It records that entry's key and value in the observation map.
3. The writer thread updates existing values and then adds key `D`.
4. `join()` waits for the writer thread to finish.
5. The main thread uses the **previously created iterator** to continue traversal.

A sleep interval is not used to guess that the writer thread "has probably finished". `join` clearly establishes completion timing and creates the necessary happens-before visibility relationship between the two threads in this example.

### Meaning of the Observed Result

In this run:

- The value for `A` was collected before the update, so the observation record retains `A` as `10`.
- The values for `B` and `C` observed afterward are the incremented values.
- The newly added `D` also appears.
- The map after the writer thread finishes has `A` equal to `110`.

Because `D` was added only after all existing values had already been incremented, there was never a point in time when the source simultaneously held `A` equal to `10` and `D` equal to `40`. Thus, the observed combination is not a point-in-time snapshot of the entire map.

This is an argument about the **actual result of the presented run**. If another run does not see `D` or produces a different observation permitted by the contract, you cannot conclude that the iterator is broken simply because it differs from this example.

### What Remains Constant in the Example

After `writer.join()` completes and no further writers exist:

- All values for `A`, `B`, and `C` have been incremented in the live map.
- Key `D` has been added.
- Printing the live map via `TreeMap` at that point reflects the stable final state.

Inspecting this final state is different from demanding that an old iterator see a complete final state.

## 9. The Three Iterator Types Are Not Three Levels of Increasing "Safety"

There is no universal ranking where fail-fast is poor, snapshot is better, and weakly consistent is best.

### When the Program Has Only One Data Owner

If a method manages its own private list, a regular `ArrayList` and proper modification through its iterator may be sufficient. Switching to a concurrent data structure does not automatically make the algorithm simpler.

### When a Processing Pass Needs the List as It Was at the Start

A snapshot is appropriate if updates are acceptable for subsequent passes. You must still consider mutable elements and the cost of retaining structural versions.

### When Reading While Multiple Parties Update

Weakly consistent traversal can fit observations that accept data gathered over a time window, such as displaying operational status where requirements are defined accordingly.

If you need an exact report of all data at the exact same moment, you should not assume such a traversal satisfies that requirement.

### When Multi-Step Business Modifications Are Required

"Find an element and then update it" or "check and then add" requires its own coordination policy.

An iterator contract answers how traversal behaves when the source changes. It does not automatically turn a sequence of application operations into an atomic transaction.

## 10. Locking the Entire Traversal or Creating a Protected Copy

Another option is to prevent coordinated updates during traversal or while creating a copy.

For a list wrapped by `Collections.synchronizedList`, the documentation requires users to synchronize manually on the wrapper list itself when traversing. Individually synchronized method calls do not hold the lock across the entire loop by default. See [Collections.synchronizedList in Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedList(java.util.List)).

There are two strategies:

| Strategy | Trade-off |
| --- | --- |
| Hold the lock throughout the entire traversal | Keeps the source stable under the locking protocol; writers may have to wait |
| Hold the lock to copy, then process the copy outside the lock | Adds copying overhead; reduces lock hold time for long processing tasks |

The prerequisite is that all writers follow the same protocol. A lock that writers do not acquire cannot block them on its own.

### Complete Program

Create the file **`LockedSnapshotDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class LockedSnapshotDemo {
    public static void main(String[] args) {
        List<String> shared = Collections.synchronizedList(
                new ArrayList<>(List.of("A", "B", "C")));

        List<String> snapshot;
        synchronized (shared) {
            snapshot = new ArrayList<>(shared);
        }

        shared.add("D");

        System.out.println("snapshot = " + snapshot);
        System.out.println("live list = " + shared);

        synchronized (shared) {
            for (String value : shared) {
                System.out.println("locked visit = " + value);
            }
        }
    }
}
```

Compile and run:

```text
javac -encoding UTF-8 --release 17 LockedSnapshotDemo.java
java -Dfile.encoding=UTF-8 LockedSnapshotDemo
```

Verified stdout:

```text
snapshot = [A, B, C]
live list = [A, B, C, D]
locked visit = A
locked visit = B
locked visit = C
locked visit = D
```

### Reading the Two Usage Patterns

- The copy is created inside a synchronized block.
- After adding `D` to the source, the copy still contains only `A`, `B`, and `C`.
- The final loop holds the lock on the wrapper list to illustrate a synchronization region covering the entire traversal.

The example uses a single thread to clearly show operation boundaries and output. When applied across multiple threads, all parties must use the wrapper list or the same protection mechanism; do not retain a separate reference to the backing array/list and mutate it through a path that bypasses the lock.

This is still a shallow copy of elements. If elements contain mutable data requiring a deep snapshot, the application must design an appropriate way to capture element state.

### Do Not Assume new ArrayList(concurrentValues) Is an Atomic Snapshot

A copy created by collecting from a weakly consistent source can freeze **the collected result**, but that result may still have been gathered across multiple points in time.

Similarly, wrapping `synchronized(map)` only around the reader does not make `ConcurrentHashMap` update calls elsewhere acquire that lock. To obtain a coordinated snapshot, you need a protocol obeyed by all participating parties, or a design that publishes versioned immutable state.

## 11. Misconceptions to Eliminate

### "Fail-Safe" Is a Complete Contract

Sometimes this term is used as an umbrella label for iterators that do not throw CME. It fails to answer whether the iterator uses a snapshot or weak consistency, whether it supports removal, or what data guarantees it provides.

When analyzing behavior, state the specific contract and class name rather than stopping at a generic label.

### No CME Means Thread-Safe

The absence of an exception does not prove that access is valid. You might be using a snapshot, a concurrent structure, or simply have not hit the error-detection path yet.

Furthermore, a thread-safe collection does not mean a single iterator instance should be shared freely across multiple threads.

### Snapshot Means All Internal Data Is Frozen

The `Score` example shows that old references still point to mutable objects. Structural immutability and element immutability must be evaluated separately.

### Weakly Consistent Always Sees the Latest Version

A traversal is not an atomic read of the entire source by default. If business requirements use the word "latest", you must define latest relative to what point in time and what level of coordination is required.

### Replacing a For-Each Loop with an Index Loop Eliminates the Bug

Changing loop syntax does not create a synchronization policy. Additions and removals also shift indices and can cause skipped elements or invalid accesses.

### Catching and Ignoring CME Resolves the Issue

Ignoring the exception can leave part of the data unprocessed or hide side effects that have already occurred. You need to fix data ownership, coordination, or traversal according to the contract.

### Checking Size Before and After Is Sufficient

Two points in time with the same size can still contain different elements or values. Some modifications may add and then remove elements, returning the count to its previous value.

`size` is neither a business version number nor proof that an entire traversal was consistent.

## 12. How to Verify Without Relying on Scheduling Luck

When writing tests:

1. Clearly identify when the iterator is created.
2. Record which modifications occur before retrieving the next element.
3. Use `join`, a latch, or an appropriate coordination mechanism if a specific event order is required.
4. Distinguish values guaranteed by the contract from a single observed outcome.
5. Do not use sleeping for a time interval as proof of synchronization.
6. Do not assert a general contract from a single run that threw no exception.

The examples in this article fix the sequence of events to clarify the **iterator lifecycle**, while still not forcing a weakly consistent iterator to act like a snapshot.

Some verification criteria:

| Test Type | What to Verify |
| --- | --- |
| Specific fail-fast behavior | Reproduce the violation on a defined source and sequence of operations |
| Snapshot | Old iterator retains the captured set of references after source updates |
| Mutable elements | Distinguish replacing an element from mutating a shared object |
| Weakly consistent | Assert only the class's guarantees; do not force an arbitrary result set to be fixed |
| Lock or copy | Verify that every writer goes through the same protection protocol |

For real systems, add checks ensuring that tasks neither duplicate nor drop work outside of policy, and that element data is also published, read, and mutated validly.

## 13. Practice

### Exercise 1: Classify Requirements

For each scenario, explain the appropriate contract:

- A method filtering a list that it owns exclusively.
- An event dispatch pass using the listener list as it existed at the start.
- A status dashboard that accepts observing updates as they happen during traversal.
- A report requiring the state of all data at a well-defined point in time.

State the reasoning behind your choice, not just the collection name.

### Exercise 2: Test Structural Replacement vs. Element Replacement

From `FailFastIteratorDemo`, create separate scenarios:

1. Add an element after creating the iterator.
2. Replace an element using `set`.
3. Remove through the iterator itself when supported.

Explain the results according to the `ArrayList` contract without overgeneralizing the exact error-throwing point to every class.

### Exercise 3: Distinguish Two Layers of Snapshot

From `SnapshotIteratorDemo`:

- Replace the object at a position after creating the iterator.
- In a separate test, mutate only a property of the object held by the iterator.
- Draw the old and new references.
- Explain which case changes the observed structure and which case changes the state of a shared object.

### Exercise 4: Evaluate Statements About Weak Consistency

Evaluate the following statements:

1. "There is no CME, so the data is a snapshot."
2. "Using `TreeMap` to print the result makes the read pass atomic."
3. "After `join`, the live map has finished updating, so the old iterator is required to see that entire state."
4. "An observed result that does not match the final state is not enough to conclude that `ConcurrentHashMap` is broken."
5. "With a concurrent collection, the application's check-then-update steps automatically become an atomic operation."

Relate each statement to the execution sequence in `WeakIteratorDemo`.

### Exercise 5: Design a Meaningful Copy

Suppose there is a shared list where each element is a mutable object.

Describe:

- The point in time at which data should be captured.
- Which parties must be blocked or coordinated during the capture.
- Whether copying references is sufficient or element properties must also be captured.
- How the copy will be processed outside the lock.
- Which limitations must be documented clearly for callers.

The completion criterion is being able to distinguish the iterator contract, the atomicity of a read pass, and the thread safety of element objects, and then choosing a mechanism that satisfies the exact level of consistency required.
