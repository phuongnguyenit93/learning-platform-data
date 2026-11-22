# ConcurrentModificationException and Multi-Path Source Modification

## 1. What Does the Exception Say and Not Say?

`ConcurrentModificationException` (CME) indicates that an operation has detected an impermissible modification of an object currently in use. A common situation is when an iterator is traversing a collection while the underlying backing structure is modified through another path.

The exception's name easily leads newcomers to think only of multiple threads. In reality, a single thread can also trigger a CME: a loop is using an iterator, while code inside the loop or a callback removes from or adds to the backing collection.

This early-termination mechanism upon detecting an inconsistency is commonly called **fail-fast**. It aids bug detection; it is not a lock, a transaction, or a thread-safety guarantee. Detection is on a best-effort basis only; a program must not rely on a CME being thrown for correctness. [ConcurrentModificationException documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ConcurrentModificationException.html).

This article focuses on one debugging question: **what structure is the iterator traversing, and what other paths can modify that exact structure?**

## 2. The Backing Source Model and the Iterator's Expected State

In common implementations such as OpenJDK's `ArrayList`, the collection tracks structural modifications using a counter. An iterator holds a corresponding expected value. When reaching a check point, if the two values do not match, the iterator may throw a CME.

```text
Create iterator
  source has modification state M
  iterator records expected state M

Modify source via a path outside that iterator
  source transitions to state M'
  iterator still holds expected state M

Iterator continues at a check point
  current state differs from expected -> mismatch detected -> CME
```

The names `modCount`, `expectedModCount`, and the specific check locations are implementation details, not a public protocol for applications to manipulate. Do not use reflection to alter counters or "resynchronize" an iterator. [OpenJDK 21 ArrayList source code](https://raw.githubusercontent.com/openjdk/jdk21u/master/src/java.base/share/classes/java/util/ArrayList.java).

The crucial point is **which specific iterator is allowed to modify the source**. For an iterator that supports `remove`, removing through that same iterator updates its internal state appropriately. Removing through a different iterator is still an external modification relative to the iterator under consideration.

### Not Every Point Checks Immediately

Do not assume that the `add` or `remove` line itself must be where the exception is thrown. The modification may have happened earlier; the exception only surfaces when `next`, a subsequent traversal operation, or a final check in a bulk operation detects it.

Likewise, do not assume that if calling `hasNext()` succeeds without error, `next()` is guaranteed to be valid after an out-of-contract modification. Check locations are implementation-dependent. An execution path that finishes early without encountering a CME does not prove that the modification was valid.

## 3. "Structural Modification" Is More Than Changing Size

For `ArrayList`, adding or removing elements is a structural modification; replacing the value at a position via `set` is not a structural modification according to the class specification. The class's fail-fast iterators are designed to detect structural modifications made outside supported modification paths. [ArrayList documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ArrayList.html).

However, do not apply a blanket rule of "the size stayed the same, so it is safe" across all operations:

| Typical Operation | What to Understand |
| --- | --- |
| Adding and then removing so size returns to its previous value | The source still underwent modifications; this does not restore the validity of an existing iterator |
| `ArrayList.set(index, value)` | Not a structural modification; does not turn the iterator into a data snapshot |
| `ArrayList.sort(...)` | Can cause an existing iterator to detect a mismatch in the OpenJDK implementation, even though the element count is unchanged |
| Adding a new key to a Map | Modifies the set of mappings |
| Replacing only the value of an existing key in `HashMap` | Differs from adding/removing a mapping; still provides no snapshot or synchronization guarantees |
| `get` on an access-ordered `LinkedHashMap` | Can change the linkage order and affect iterators |
| Mutating an internal field of an element | Does not necessarily change the collection structure; can cause separate hashing/ordering issues that CME does not detect |

Always read the contract of the specific implementation class and operation. Do not equate "does not throw CME" with "results remain unchanged", "safe for multithreaded execution", or "meets business requirements".

## 4. Paths Leading to the Same Backing Source

### 4.1. Two Variables Do Not Mean Two Collections

```java
List<String> first = new ArrayList<>(List.of("A", "B"));
List<String> second = first;
```

`first` and `second` are two reference paths pointing to the same object. Modifying `second` modifies the backing source of an iterator obtained from `first`. Naming a variable `copy`, `backup`, or `readOnly` does not determine whether the data was actually copied.

### 4.2. List and Map Views

A view is a window into data stored elsewhere, not a copy by default:

```text
Backing List <---- subList
     ^
     +------------ unmodifiable wrapper
     +------------ multiple iterators

Backing Map <----- keySet
     ^
     +------------ values
     +------------ entrySet
```

Modifications made through a view can write through to the backing source. For example, `map.keySet().remove(key)` removes the mapping from the Map, which can invalidate an iterator currently traversing that Map's `entrySet`. Views are not isolated data stores. [Map documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html#keySet()).

With `subList`, supported modifications made through the view itself take effect on the backing List. If the backing List is structurally modified in any way other than through the subList, the semantics of the subList become undefined under its contract. An implementation may throw a CME when an invalidated view is used, but you must not write application logic that requires every implementation to throw that exact exception. When you need a structurally independent slice of data, create a copy rather than continuing to use an old view. [List.subList documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#subList(int,int)).

### 4.3. Unmodifiable Wrappers Still Read a Changing Source

`Collections.unmodifiableList(source)` prevents modifications through the wrapper, but it does not prevent other code holding `source` from modifying it. An iterator obtained from the wrapper still relies on the underlying data. Therefore, "cannot be modified through this variable" does not mean "nobody can modify the backing source".

To decouple the structure at a point in time, you can create `new ArrayList<>(source)` or choose an appropriate copying method. That copy still shares references to the elements themselves; it does not automatically perform a deep copy of each element's internal state.

### 4.4. Callbacks and Nested Calls

The following snippet is an intentionally flawed example; `notifyListener` represents a method in the application:

```java
for (Listener listener : listeners) {
    notifyListener(listener); // may indirectly call listeners.remove(...)
}
```

Not seeing `remove` directly inside the loop body is not enough to rule out modification. You need to trace methods, events, or utility functions that hold a reference to the same List. A listener registering or unregistering itself while being notified is a common scenario.

Similarly, `list.forEach`, `removeIf`, a mapping function, or a stream can invoke custom code. That callback should not add to or remove from the source currently being operated on unless the API explicitly permits it. Record the intended changes to apply later, or choose a snapshot-based traversal policy when requirements allow.

### 4.5. An Operation That Looks Like a Read Can Also Modify Related Structure

A `LinkedHashMap` configured with `accessOrder = true` maintains access order. Calling `get` on a key can move its mapping to a new position. Consequently, iterating over `keySet` and calling `get` on the same Map to retrieve values can trigger a CME if the access alters the iteration order.

If you need both keys and values during traversal, consider iterating over `entrySet` and reading each entry's value in accordance with the contract, rather than performing order-altering lookups unnecessarily. Do not assume insertion-ordered Map behavior applies to an access-ordered Map. [LinkedHashMap documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html).

## 5. Java 17+ Program Reproducing Modification Paths

Save as `CmePathsDemo.java`. The program runs single-threaded and uses no `sleep` or timing races. The CME lines demonstrate the fail-fast behavior of the specific JDK implementations instantiated in the code, such as `ArrayList` and `LinkedHashMap`; they are not a promise that every collection or every violation will throw a CME.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.ListIterator;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;

public class CmePathsDemo {
    static void expectCme(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("expected CME for demonstration: " + label);
        } catch (ConcurrentModificationException ex) {
            System.out.println(label + "=CME");
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A", "B", "C"));
        List<String> alias = source;
        Iterator<String> aliasCursor = source.iterator();
        alias.add("D");
        expectCme("alias next", aliasCursor::next);

        List<String> parent = new ArrayList<>(List.of("A", "B", "C", "D"));
        List<String> window = parent.subList(1, 3);
        Iterator<String> parentCursor = parent.iterator();
        window.remove("B");
        System.out.println("parent after view remove=" + parent);
        expectCme("parent iterator after view edit", parentCursor::next);

        List<String> backing = new ArrayList<>(List.of("A", "B"));
        List<String> readOnly = Collections.unmodifiableList(backing);
        Iterator<String> readOnlyCursor = readOnly.iterator();
        backing.add("C");
        expectCme("read-only view iterator", readOnlyCursor::next);

        Map<String, Integer> map = new LinkedHashMap<>();
        map.put("A", 1);
        map.put("B", 2);
        map.put("C", 3);
        Iterator<Map.Entry<String, Integer>> entries = map.entrySet().iterator();
        map.keySet().remove("B");
        expectCme("entry iterator after keySet edit", entries::next);

        List<String> shared = new ArrayList<>(List.of("A", "B", "C"));
        Iterator<String> first = shared.iterator();
        Iterator<String> second = shared.iterator();
        first.next();
        first.remove();
        System.out.println("same iterator continues=" + first.next());
        expectCme("other iterator after remove", second::next);

        List<String> replacement = new ArrayList<>(List.of("A", "B"));
        Iterator<String> replacementCursor = replacement.iterator();
        replacement.set(0, "Z");
        System.out.println("ArrayList set then next=" + replacementCursor.next());

        List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3, 4, 5));
        Iterator<Integer> numberCursor = numbers.iterator();
        while (numberCursor.hasNext()) {
            if (numberCursor.next() % 2 == 0) {
                numberCursor.remove();
            }
        }
        System.out.println("iterator filtered=" + numbers);

        List<Integer> bulk = new ArrayList<>(List.of(1, 2, 3, 4, 5));
        bulk.removeIf(number -> number % 2 == 0);
        System.out.println("removeIf filtered=" + bulk);

        List<String> editable = new ArrayList<>(List.of("A", "C"));
        ListIterator<String> editCursor = editable.listIterator();
        editCursor.next();
        editCursor.add("B");
        editCursor.next();
        editCursor.set("Z");
        System.out.println("ListIterator edited=" + editable);

        List<String> original = new ArrayList<>(List.of("A", "B"));
        List<String> snapshot = new ArrayList<>(original);
        for (String value : snapshot) {
            original.add(value + "*");
        }
        System.out.println("snapshot=" + snapshot);
        System.out.println("original after processing=" + original);

        Map<String, Integer> accessOrdered = new LinkedHashMap<>(16, 0.75f, true);
        accessOrdered.put("A", 1);
        accessOrdered.put("B", 2);
        accessOrdered.put("C", 3);
        Iterator<String> accessCursor = accessOrdered.keySet().iterator();
        accessOrdered.get("A");
        expectCme("access-order get", accessCursor::next);
        System.out.println("keys after access=" + accessOrdered.keySet());

        CopyOnWriteArrayList<String> copyOnWrite =
                new CopyOnWriteArrayList<>(List.of("A", "B"));
        Iterator<String> oldSnapshot = copyOnWrite.iterator();
        copyOnWrite.add("C");
        List<String> seen = new ArrayList<>();
        oldSnapshot.forEachRemaining(seen::add);
        System.out.println("copy-on-write iterator=" + seen);
        System.out.println("copy-on-write current=" + copyOnWrite);
    }
}
```

Compile and run:

```shell
javac --release 17 CmePathsDemo.java
java CmePathsDemo
```

Stdout of the example on corresponding standard OpenJDK implementations:

```text
alias next=CME
parent after view remove=[A, C, D]
parent iterator after view edit=CME
read-only view iterator=CME
entry iterator after keySet edit=CME
same iterator continues=B
other iterator after remove=CME
ArrayList set then next=Z
iterator filtered=[1, 3, 5]
removeIf filtered=[1, 3, 5]
ListIterator edited=[A, B, Z]
snapshot=[A, B]
original after processing=[A, B, A*, B*]
access-order get=CME
keys after access=[B, C, A]
copy-on-write iterator=[A, B]
copy-on-write current=[A, B, C]
```

### Reading Each Result Group

- `alias` modifies the same object as `source`, so the existing iterator detects a mismatch when continuing.
- Removing through `window` modifies via the subList and mutates the parent List. The iterator created earlier on the parent List is not updated by the view's operation.
- An unmodifiable wrapper does not protect its iterator from modifications performed directly through `backing`.
- `keySet` and `entrySet` share the same backing Map; modifying through one view affects traversal of the other.
- `first.remove()` is valid for `first` itself, but does not keep iterator `second` valid after the change.
- `ArrayList.set` does not perform a structural modification in the demonstrated case; the iterator reads the current value `Z` rather than holding a snapshot of the initial value `A`.
- Filtering via the loop's own iterator and via `removeIf` both produce the same desired result.
- `ListIterator` allows adding and replacing elements within its own valid state.
- Iterating over a copy does not directly traverse the `original` structure; adding to `original` does not alter the copy's structure.
- `get("A")` on an access-ordered Map moves `A` to the end; the source does not need to change its element count for the iterator to detect a modification.
- The `CopyOnWriteArrayList` iterator still sees `A`, `B`, while the current List now includes `C` in accordance with the class's snapshot policy.

The `expectCme` helper intentionally catches the exception to present the experiment and aborts with `AssertionError` if the expected demonstration behavior is not observed. This is not a business error-handling pattern to put inside application loops.

## 6. Choosing a Fix Based on Modification Intent

### 6.1. Removing the Currently Traversed Element: Use an Iterator That Supports remove

```java
Iterator<Item> cursor = items.iterator();
while (cursor.hasNext()) {
    Item item = cursor.next();
    if (shouldRemove(item)) {
        cursor.remove();
    }
}
```

This snippet is an application template; you need to supply the `Item` type, `items`, and the predicate method. Do not call `items.remove(item)` inside the loop, because that would once again be a modification path outside the iterator.

`Iterator.remove` is an optional operation; some iterators do not support it. For standard iterators that do support it, `next` must be called first, and `remove` may be called at most once per `next` call. Violating this state rule results in `IllegalStateException`, which is distinct from CME. Do not assume that every iterator, especially snapshot iterators, permits removal. [Iterator.remove documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Iterator.html#remove()).

Do not take the fact that `Iterator.remove` works inside a `while` loop and assume you can call it from the action passed to `forEachRemaining`. The contract of `forEachRemaining` does not define behavior when the action modifies the underlying source, even through the iterator's own mutator methods, unless a specific implementation explicitly documents otherwise.

### 6.2. Conditional Filtering: Use removeIf with a Non-Mutating Predicate

```java
items.removeIf(item -> shouldRemove(item));
```

The predicate only decides whether to keep or remove an element. Do not call `items.add`, `items.remove`, or any function with an equivalent effect on the same backing source from inside the predicate. `removeIf` also requires the collection to support removal; unmodifiable wrappers may throw `UnsupportedOperationException`. [Collection.removeIf documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collection.html#removeIf(java.util.function.Predicate)).

### 6.3. Adding or Replacing at the Cursor: Use ListIterator When Appropriate

For Lists that support it, `ListIterator.add`, `set`, and `remove` allow modifications coordinated with the cursor's own state. The calling rules for each method must still be followed. They do not grant permission for external methods to freely mutate the same List or keep other active iterators valid after modifications.

### 6.4. Deciding First and Applying Later

You can collect intended changes into a separate collection, finish traversing the source, and then apply them. Take care to preserve the exact semantics:

- If removing by value, `removeAll` removes all elements equal to that value, not just a single selected occurrence.
- If removing by index, subsequent indices shift after each removal; you must use an appropriate application strategy.
- If new elements need to be added without being processed in the current pass, a separate pending-additions list makes the pass boundary explicit.

Do not replace a CME bug with a removal approach that loses duplicate occurrences or targets the wrong positions.

### 6.5. Traversing the Membership Set at the Start of a Pass: Use a Snapshot

A structural copy is appropriate when the requirement is to process the elements present when the pass begins. Subsequent additions or removals on the backing source do not alter the membership of the copy. However, the element objects themselves may still be shared and mutated.

If the source is being modified concurrently by multiple threads, the copying operation itself must also be protected according to the source's contract. `new ArrayList<>(source)` does not automatically make reading an unsynchronized, concurrently modified `ArrayList` safe. Additionally, `List.copyOf` disallows `null` elements; choose the copying API that matches your data constraints.

## 7. Streams and Callbacks Still Share the Same Backing Source

Replacing a `for` loop with a stream does not resolve interference with the backing source:

```java
// Incorrect source policy; do not use as a removal idiom.
items.stream().forEach(item -> items.remove(item));
```

For sources not designed for concurrent modification, functions in a stream pipeline must not interfere with the source while the pipeline is executing. The result of a violation is not guaranteed to be only a CME; incorrect behavior or other exceptions may occur. This non-interference requirement applies to both sequential and parallel streams. [Stream documentation: non-interference](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/package-summary.html).

Also, do not treat stream creation time as data snapshot time: pipelines are typically evaluated lazily, and many sources bind their traversal late. Questions like "I modified the List after creating the stream but before the terminal operation" require reading the source's binding policy rather than blindly applying the create-iterator-then-modify model to every stream.

A clear alternative is to produce a new result using `filter` if the source does not need to be mutated in place, or to use `removeIf` if the goal is in-place removal on the source and the API permits it. Side effects inside predicates should still be avoided per the contract.

## 8. When Multiple Threads Are Actually Involved

### 8.1. Synchronized Wrappers Require Locking the Proper Scope

`Collections.synchronizedList` synchronizes individual method calls according to the wrapper's policy, but when traversing, you must manually synchronize the entire iteration block on the wrapper object as required by the API specification:

```java
List<String> shared = Collections.synchronizedList(new ArrayList<>());
synchronized (shared) {
    for (String value : shared) {
        consume(value);
    }
}
```

This is an illustrative snippet requiring a `consume` method. All other access paths must obey the same locking policy; retaining and using a direct reference to the backing List outside the wrapper defeats the protection. When iterating over a view of a synchronized wrapper, you must lock on the exact object required by the API specification, rather than locking on a different view object. [Collections.synchronizedList documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html#synchronizedList(java.util.List)).

Locking does not make it valid for `consume` itself to structurally modify the backing source outside the iterator on the same thread. Java monitors are reentrant for the same thread; therefore, a callback can still trigger a CME if it modifies the collection improperly. Thread synchronization and the in-traversal modification policy are two distinct requirements that must both be satisfied.

### 8.2. Choosing a Concurrent Collection Based on Desired Data Visibility

| Traversal Policy | Example | Trade-offs to Accept |
| --- | --- | --- |
| Fail-fast iterator on standard collections | `ArrayList`, views of standard Maps | Must not modify the source outside paths permitted by the iterator/API |
| Snapshot iterator | `CopyOnWriteArrayList` | Does not see membership changes made after iterator creation; high write cost and iterator mutator methods are unsupported |
| Weakly consistent traversal | `ConcurrentHashMap` | May reflect state changes occurring during traversal; not an atomic snapshot of the entire Map |

A `CopyOnWriteArrayList` iterator is guaranteed not to throw a CME under its policy; `remove`, `set`, and `add` operations via the iterator are unsupported. It is a choice for workloads where reads vastly outnumber writes, not a drop-in class swap to hide arbitrary bugs. [CopyOnWriteArrayList documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html).

Iterators of `ConcurrentHashMap` do not throw CME, but traversal is not guaranteed to represent the exact state of the entire Map at a single point in time. Do not assume a fixed element order or fixed membership set while concurrent updates are occurring. Sequences of multiple business operations still require their own atomicity analysis. [ConcurrentHashMap documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html).

## 9. How to Debug Multi-Path Source Modifications

1. Identify the actual collection class and traversal mechanism: explicit iterator, enhanced `for` loop, view, stream, or callback-accepting operation.
2. Note where the iterator or traversal pass starts and which line detected the failure. Do not assume the stack trace line is where the source was actually modified.
3. Map out all references to the same backing source: differently named variables, object fields, getters returning the live collection, `subList`, Map views, and wrappers.
4. Trace every call inside the traversal body, especially callbacks, listeners, utility methods, and lookups that may alter ordering.
5. Distinguish element state mutation from structural collection modification; check the policy of the exact implementation rather than just comparing sizes before and after.
6. Choose the appropriate fix—iterator mutators, bulk operations, two-phase collection, snapshots, or synchronization/concurrent collections—based on the required outcome.
7. Verify the resulting contents and processing counts after the fix, not just "CME no longer occurs".

Do not catch a CME and continue using the invalidated iterator. Likewise, do not blindly retry an entire traversal pass if the failed pass already performed side effects such as sending notifications or updating external state: retrying may duplicate those side effects. A retry policy is only sound when the application has explicit mechanisms for consistency and idempotency.

## 10. Testing After Fixing

Separate experiments that reproduce a specific implementation's failure mode from tests that verify application correctness:

- CME reproduction experiments should use a single thread and a deterministic call order when the goal is simply to demonstrate aliasing or view invalidation; there is no need to create random thread races.
- Tests for the fix should verify the kept/removed elements, ordering, callback invocation counts, and effects on the backing source or views.
- For snapshot approaches, explicitly test whether elements added after the pass starts are processed immediately or deferred to a subsequent pass.
- For concurrent operations, coordinate threads using synchronization primitives such as latches or barriers when controlling test interleavings; do not rely on a few milliseconds of `sleep` to assume a specific execution schedule.
- Do not write tests requiring an unsynchronized data race to always throw a CME. Fail-fast makes no such guarantee.

Self-check questions:

1. Why can modifying `alias` cause an iterator obtained from `source` to fail even though the two variable names are different?
2. Why can removing via a first iterator be valid for that iterator while invalidating a second iterator?
3. How do an unmodifiable wrapper and a structural copy differ?
4. In an access-ordered Map, why can a `get` call be involved in a CME?
5. If CMEs disappear after switching to a snapshot or a concurrent collection, what else must be verified regarding the set of processed elements?

To explain a CME bug, pinpoint the shared backing source, the modification path, and the violated traversal policy. To fix it properly, decide what data the processing pass must see and who is authorized to modify it.
