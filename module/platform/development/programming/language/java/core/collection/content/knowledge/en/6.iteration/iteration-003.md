# Iterator.remove and Valid Call Conditions

When you need to remove elements from a collection while iterating through it, `Iterator.remove()` provides an operation tied directly to **the iteration process itself**.

It does not take an element or an index. If supported, it removes from the underlying collection **the element returned by the most recent call to `next()` on that iterator**, with a limit of one removal per element retrieval.

To use it properly, you need to distinguish three questions:

1. Does this iterator support removal?
2. Does the current state allow calling `remove` yet?
3. Has the collection been modified through another path in a way that breaks the iteration guarantees?

## 1. Why Is There a Remove Operation on an Iterator?

Suppose a list of numbers contains:

```text
[-2, 0, 3, -1, 4]
```

We want to iterate through each number and remove negative numbers in place. The iterator keeps track of the position for retrieving the next element. Removing an element can cause subsequent elements to shift or alter internal links inside the collection.

If you use the iterator's own remove operation, the implementing class has the opportunity to update its traversal state to match the removal just performed.

Illustrative pattern inside a method:

```java
Iterator<Integer> iterator = numbers.iterator();

while (iterator.hasNext()) {
    int number = iterator.next();
    if (number < 0) {
        iterator.remove();
    }
}
```

Here, `numbers` is a list whose iterator supports removal. The removal operation is tied to the number just returned, without needing to search for that number again by value.

This is also useful when there are multiple equal elements: the iterator knows which occurrence has just been reached.

## 2. Three Methods and Three Distinct Roles

| Method | Role | Does It Establish a New Element Eligible for Removal? |
| --- | --- | --- |
| `hasNext()` | Asks whether more elements remain to be retrieved | No |
| `next()` | Retrieves the next element | Yes, if retrieval succeeds |
| `remove()` | Removes the most recently retrieved element | Consumes the removal right for that element |

`remove()` has a `void` return type. It does not return the removed element and does not return a boolean.

This is an **optional** operation of the `Iterator` interface. If the iterator does not support it, the call may be rejected with an `UnsupportedOperationException`.

The formal specifications regarding the removed element, call frequency, exceptions, and collection modifications are stated in the [Java 17 Iterator.remove API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html#remove()).

## 3. Viewing remove as a Small State Machine

For an iterator that supports removal and does not suffer from contract-violating collection modifications, two states can be used:

| State | Meaning |
| --- | --- |
| No element eligible for removal | `next` has not succeeded yet, or the most recent element has already been removed |
| An element is eligible for removal | `next` has returned an element and that element has not yet been removed |

State transitions:

```text
Newly created iterator
    |
    v
CANNOT REMOVE YET
    |
    | next() succeeds
    v
CAN REMOVE JUST-RETURNED ELEMENT
    |
    | remove() succeeds
    v
CANNOT REMOVE YET
```

You can call `next()` again without removing the previous element. When you do so, the target of `remove` moves to the newly returned element. Removal allowances do not accumulate.

### 3.1. Before next, There Is No Removal Target

The following snippet is in an invalid state for an iterator that supports `remove`:

```java
Iterator<String> iterator = values.iterator();
iterator.remove();
```

No element has been returned by the iterator yet. Do not interpret `remove` as "remove the first element" or "remove the element about to be read".

With `ArrayList`'s iterator, this situation throws `IllegalStateException`.

### 3.2. One Call to next Allows Only One Call to remove

Valid sequence:

```text
next -> remove -> next -> remove
```

Invalid-state sequence:

```text
next -> remove -> remove
```

The second `remove` has no new element to remove. It does not mean "continue removing the following element".

If you want to remove the next element, you must retrieve it with `next` and then decide to remove it.

### 3.3. Multiple Calls to next Do Not Build a Pool of remove Allowances

With data:

```text
[A, B, C]
```

after two calls to `next` returning A and then B, a single call to `remove` removes B. You cannot call `remove` again to go back and remove A.

If you need to decide whether to remove A, you must do so while A is still the most recently returned element, or choose a different processing strategy.

### 3.4. hasNext Does Not Replace next

Calling `hasNext()` one or more times does not produce a newly returned element.

After:

```text
next returns A -> hasNext -> hasNext -> remove
```

`remove` still targets A as long as no other operation has invalidated the state.

Similarly, after retrieving the last element, `hasNext()` may return `false`, yet `remove` remains valid for the last element just retrieved. "No more elements ahead" is different from "no most recent element to remove".

A failed call to `next` does not return a new element; do not use such a call as a way to grant another `remove` allowance.

## 4. Complete Program on Valid States

Save as **IteratorRemoveStateDemo.java**. The program uses `ArrayList` so that removal operations are supported, and is compatible with Java 17 and above.

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

public class IteratorRemoveStateDemo {
    public static void main(String[] args) {
        List<String> values =
                new ArrayList<>(List.of("A", "B", "A", "C"));
        Iterator<String> iterator = values.iterator();

        try {
            iterator.remove();
        } catch (IllegalStateException ex) {
            System.out.println("Before next: " + ex.getClass().getSimpleName());
        }

        System.out.println("Next: " + iterator.next());
        System.out.println("hasNext: " + iterator.hasNext());
        iterator.remove();
        System.out.println("After first remove: " + values);

        try {
            iterator.remove();
        } catch (IllegalStateException ex) {
            System.out.println("Twice: " + ex.getClass().getSimpleName());
        }

        System.out.println("Skip removal for: " + iterator.next());
        System.out.println("Next: " + iterator.next());
        iterator.remove();
        System.out.println("After removing second A: " + values);

        System.out.println("Last next: " + iterator.next());
        System.out.println("hasNext at end: " + iterator.hasNext());
        iterator.remove();
        System.out.println("After remove at end: " + values);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 IteratorRemoveStateDemo.java
java IteratorRemoveStateDemo
```

Stdout:

```text
Before next: IllegalStateException
Next: A
hasNext: true
After first remove: [B, A, C]
Twice: IllegalStateException
Skip removal for: B
Next: A
After removing second A: [B, C]
Last next: C
hasNext at end: false
After remove at end: [B]
```

### 4.1. Reviewing Each Stage

**Before `next`:** no element has just been retrieved, so `remove` reports an invalid state.

**After `next` returns A:** there is a removal target. Calling `hasNext` only checks whether another element follows, so it does not clear target A.

**After the first removal:** the list retains `[B, A, C]`. The iterator proceeds to retrieve B without skipping it because the removal was performed through the iterator itself.

**Two consecutive `remove` calls:** the second call throws `IllegalStateException`.

**B then A:** the program does not remove B. When `next` continues and returns A, `remove` targets that new A.

**After the last element C:** `hasNext` is `false`, but C has not been removed yet, so a single `remove` is still valid. The result leaves `[B]`.

The exceptions caught in this program are only for observing the contract. In normal application code, structure the call flow properly rather than using exceptions as loop control.

## 5. remove Deletes the Just-Traversed Occurrence, Not by Value Search

Consider:

```text
[A, B, A]
```

If the iterator has stepped through the first A, B, and then the second A, `iterator.remove()` targets **the second A**.

Meanwhile, `list.remove("A")` on an `ArrayList` searches for the first matching occurrence by value. Even though both mean "remove A", the two calls can act on different positions.

Furthermore, with `List<Integer>`, `list.remove(number)` may resolve to the index-based removal overload if `number` has primitive type `int`. `Iterator.remove()` takes no parameters, so there is no ambiguity between value and index at that call site.

Removing an element from a collection also does not destroy the object referenced elsewhere. A local variable that received the object from `next` can still reference that object after the element has been removed from the collection.

## 6. Why Not Call collection.remove While Iterating?

The following pattern is not a generally safe substitute:

```java
// Snippet illustrating incorrect usage for a standard ArrayList.
for (String value : values) {
    if ("A".equals(value)) {
        values.remove(value);
    }
}
```

The `for-each` loop uses an underlying iteration process. The `remove` call here goes directly to the list, not to that iterator's `remove` operation.

With `ArrayList`, the iterator has a mechanism to detect certain structural modifications made outside supported paths and may throw `ConcurrentModificationException`. This exception does not require multiple threads: a single thread modifying a list while iterating over it can also trigger it.

However, fail-fast detection is only a best-effort bug-detection mechanism. An incorrect loop that happens not to throw an exception on a small dataset does not become valid usage. Never write program correctness to depend on catching `ConcurrentModificationException`. See the [ArrayList API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

The clear approach when you need to remove during a traversal pass is to hold an explicit iterator and call its own `remove`.

### Two Iterators Also Have Two Separate States

If two iterators traverse a standard list at the same time, a valid removal by the first iterator does not automatically update the state of the second iterator.

"Remove through the iterator" must be understood as removing through **the iterator performing that traversal**, not that calling `remove` on any iterator makes all other active traversals safe.

If a collection class has its own concurrent traversal policy, follow that class's contract; do not apply a single fail-fast rule to every iterator in the JDK.

## 7. Supporting Collection Modification and Supporting iterator.remove Are Two Different Things

The fact that an object has a `remove` method does not mean every iterator over it allows removal.

| Common Iterator Source | `Iterator.remove` | Reason to Remember |
| --- | --- | --- |
| `new ArrayList<>(...)` | Supported | Can remove the element and update traversal state |
| `Arrays.asList(...)` | Structural removal not supported | Fixed-size list |
| `List.of(...)` | Not supported | Unmodifiable list |
| `CopyOnWriteArrayList` | Not supported on iterator | Iterator observes a snapshot |
| View from a modifiable map such as `LinkedHashMap.entrySet()` | May be supported | Removes the mapping through the map view |

Always read the contract of the specific source rather than inferring capability from the declared type `Iterator<E>`.

### 7.1. Fixed Size Is Different from Completely Unmodifiable

`Arrays.asList` returns a list backed by an array; you can replace elements with `set`, but you cannot shrink its size with `remove`. The rejection of iterator removal does not prove that every update operation is forbidden.

If you need to filter and reduce the number of elements, you can create `new ArrayList<>(source)` to work on a list with its own modifiable structure. See the [Arrays.asList API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)).

### 7.2. The Collection Is Modifiable, but the Iterator Reads a Snapshot

`CopyOnWriteArrayList` allows adding or removing through the collection's own methods. Its iterator traverses a snapshot taken when the iterator was created and does not support `remove`.

Therefore, "the collection supports removal" does not imply "the iterator supports removal". If you need to mutate a collection with a concurrency policy, choose the operation specified by that class rather than forcing a single pattern across all sources. See the [CopyOnWriteArrayList API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html).

### 7.3. Do Not Confuse Capability Errors with State Errors

`IllegalStateException` typically reflects an invalid call order when the operation is supported. `UnsupportedOperationException` reflects that the iterator does not provide that operation.

If a call is both in an invalid state and made on an iterator that does not support `remove`, do not rely on a universal exception precedence rule to guess what happens. Check support through documentation, and write a valid call sequence.

## 8. Complete Program: Filtering Data and Observing Support Capabilities

Save as **IteratorRemoveUsageDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;

public class IteratorRemoveUsageDemo {
    private static void showUnsupported(
            String label, Iterable<String> source) {
        Iterator<String> iterator = source.iterator();
        iterator.next();
        try {
            iterator.remove();
        } catch (UnsupportedOperationException ex) {
            System.out.println(label + ": " + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        List<Integer> numbers =
                new ArrayList<>(List.of(-2, 0, 3, -1, 4));
        int removed = 0;
        Iterator<Integer> iterator = numbers.iterator();
        while (iterator.hasNext()) {
            int number = iterator.next();
            if (number < 0) {
                iterator.remove();
                removed++;
            }
        }
        System.out.println("Numbers: " + numbers);
        System.out.println("Removed negatives: " + removed);

        Map<String, Integer> stock = new LinkedHashMap<>();
        stock.put("pen", 0);
        stock.put("book", 3);
        stock.put("bag", 0);

        Iterator<Map.Entry<String, Integer>> entries =
                stock.entrySet().iterator();
        while (entries.hasNext()) {
            Map.Entry<String, Integer> entry = entries.next();
            if (entry.getValue() == 0) {
                entries.remove();
            }
        }
        System.out.println("Stock: " + stock);

        showUnsupported("Arrays.asList", Arrays.asList("A", "B"));
        showUnsupported("List.of", List.of("A", "B"));

        CopyOnWriteArrayList<String> snapshots =
                new CopyOnWriteArrayList<>(List.of("A", "B"));
        showUnsupported("CopyOnWrite iterator", snapshots);
        snapshots.remove("A");
        System.out.println("CopyOnWrite direct remove: " + snapshots);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 IteratorRemoveUsageDemo.java
java IteratorRemoveUsageDemo
```

Stdout:

```text
Numbers: [0, 3, 4]
Removed negatives: 2
Stock: {book=3}
Arrays.asList: UnsupportedOperationException
List.of: UnsupportedOperationException
CopyOnWrite iterator: UnsupportedOperationException
CopyOnWrite direct remove: [B]
```

### 8.1. Filtering Negative Numbers

The loop calls `next` exactly once per iteration. Only negative numbers are removed, so `0`, `3`, and `4` are kept.

The counter increments after `remove` succeeds. It does not increment based on a boolean return value because `Iterator.remove()` does not return a boolean.

### 8.2. Removing Mappings via entrySet

`Map` does not have a direct `iterator` method; the program obtains an iterator from the `entrySet()` view.

When `entries.remove()` removes an entry with quantity `0`, it removes the corresponding mapping from `stock`. After the traversal, only `book=3` remains.

This is not removal from a detached copy of entries. The view is backed by the underlying map. Whether entries can be removed depends on whether the map and its view support the operation; see the [Map.entrySet API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#entrySet()).

After removing an entry, do not hold onto it as a reliable way to keep updating the same mapping in the map. If you need data for reporting, extract the required values according to the contract before or during processing.

### 8.3. Distinguishing the Iterator from the Collection

The `showUnsupported` helper calls `next` first and only then attempts `remove`. As a result, it avoids triggering an error due to not having read an element yet.

The three sources in the example reject the operation due to the iterator's capability. Finally, direct removal on `CopyOnWriteArrayList` succeeds after the test, demonstrating that a collection can be modifiable even when its iterator does not provide `remove`.

These examples do not use exception catching to deduce every property of a data source. They verify known contracts of specific classes.

## 9. forEachRemaining Is Not a Shortcut for Calling remove

You might look at the default implementation of `forEachRemaining` as a loop that retrieves the remaining elements and invokes the action. However, you must not infer from this that calling `remove` inside the action or immediately after `forEachRemaining` finishes is always permitted.

The `Iterator` contract states that:

- Behavior is generally unspecified if the action modifies the collection, even by calling `remove`, unless an overriding class defines its own policy.
- Subsequent behavior is generally unspecified if `remove` is called after `forEachRemaining`.

Therefore, if your goal is to traverse and conditionally remove elements under the standard iterator contract, use an explicit loop:

```java
while (iterator.hasNext()) {
    String value = iterator.next();
    if ("obsolete".equals(value)) {
        iterator.remove();
    }
}
```

This snippet illustrates usage with an `Iterator<String>` that supports `remove`.

Do not rely on an implementation class or a particular JDK version accidentally allowing `remove` after `forEachRemaining` as if it were an interface guarantee. See the [Iterator.forEachRemaining API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html#forEachRemaining(java.util.function.Consumer)).

## 10. Relationship with ListIterator and removeIf

### 10.1. ListIterator Has a Broader Contract

`ListIterator` extends `Iterator`, supporting both `next` and `previous`. Its `remove` targets the element most recently returned by either traversal direction.

It also provides `add` and `set`, so its state preconditions must be read separately. For example, calling `add` after a read operation makes a subsequent `remove` invalid until another `next` or `previous` call.

Do not carry the `next`-only state machine from this article directly over to the full `ListIterator` API while ignoring `previous` or `add`. If you only need forward one-way traversal, you do not need those extended APIs. See the [ListIterator.remove API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html#remove()).

### 10.2. removeIf Fits Simple Filtering Conditions

If you only need to remove all elements matching a condition, you can express it as:

```java
numbers.removeIf(number -> number < 0);
```

This line is an illustrative snippet with a list of non-null integers.

It clearly expresses the intent "remove elements matching the condition", and some classes provide optimized implementations. The default implementation of `Collection.removeIf` iterates and uses `iterator.remove` for matching elements.

That does not guarantee `removeIf` will run on every source. On sources that do not support the required mutation operation, it may be rejected. The predicate should also not structurally modify the collection being filtered on its own. See the [Collection.removeIf API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#removeIf(java.util.function.Predicate)).

Choose an explicit iterator when you need step-by-step traversal control or per-element side processing. Choose `removeIf` when the filtering predicate fully describes the intent.

## 11. Concurrency and Performance: Limits of the Guarantees

### 11.1. Valid Within a Single Traversal Pass Does Not Mean Thread-Safe

`Iterator.remove` coordinates removal with the iterator's state. It does not automatically lock an `ArrayList` against other threads.

Even when using `Collections.synchronizedList`, traversal must be synchronized according to the wrapper class's guidelines. Under the standard pattern, obtaining the iterator and performing the entire traversal must be enclosed in a `synchronized` block on the wrapped list object itself, and all other access points must follow the same mechanism.

Synchronizing individual method calls alone does not turn the whole `hasNext`–`next`–`remove` sequence into an atomic transaction. See the [Collections.synchronizedList API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedList(java.util.List)).

### 11.2. Semantically Correct Is Not Always Cost-Optimal

With `ArrayList`, removing a single element may require shifting subsequent references. Removing many elements through repeated `remove` calls can incur significant overhead.

If the goal is bulk filtering:

- Consider `removeIf` when the condition can be expressed clearly.
- If the original source must be preserved, build a new result containing the retained elements.
- Benchmark with realistic data and collection types when performance matters.

Do not conclude that every `Iterator.remove` has the same complexity. The interface defines the semantics, whereas the underlying data structure determines the cost.

## 12. Common Mistakes and Fixes

| Mistake | Misconception | Fix |
| --- | --- | --- |
| Calling `remove` immediately after creating the iterator | Treating `remove` as deleting the element about to be read | Call `next` to retrieve an element first |
| Calling `remove` twice in a row | Assuming each `remove` automatically advances to the next element | Each element returned by `next` allows only one `remove` |
| Calling `hasNext` and then `remove` | Assuming checking for remaining data establishes a removal target | `hasNext` does not replace `next` |
| Calling `next` in the condition and calling `next` again to remove | Already advanced past the element that needed processing | Store the result of a single `next` call in a local variable |
| Calling `list.remove` inside a `for-each` loop | Structurally modifying the collection outside the active iterator's path | Use an explicit iterator or `removeIf` as appropriate |
| Using an iterator from `List.of` or `Arrays.asList` | Ignoring the source's mutation limits | Choose a source that supports shrinking or work on a modifiable copy |
| Assuming every concurrent collection supports `iterator.remove` | Confusing concurrency guarantees with iterator mutability | Read the contract of the specific class |
| Calling `remove` during or after `forEachRemaining` | Treating default implementation details as a general interface guarantee | Use an explicit `while` loop when removal is needed |
| Relying on the absence of `ConcurrentModificationException` | Treating fail-fast behavior as synchronization or proof of correctness | Fix the traversal logic instead of relying on exceptions |
| Having another iterator remove and continuing with the current iterator | Assuming multiple iterators share a single traversal state | Avoid external structural changes during the current traversal or use an appropriate concurrent policy |

## 13. Self-Check

1. Given `[A, B, C]`, after `next` returns A and then `next` returns B, which element does `remove` delete?
2. After the final `next` call when `hasNext` returns `false`, is `remove` still allowed? What conditions must hold?
3. Why does `hasNext` not grant a new `remove` allowance after a `remove` call?
4. Given `[A, B, A]`, compare the removal target of the iterator when positioned at the second A with `list.remove("A")`.
5. Explain why `CopyOnWriteArrayList` allows direct removal on the collection while its iterator does not allow `remove`.
6. Why does a single run of a `for-each` loop combined with `list.remove` that throws no error still fail to prove that the code is safe?
7. When you only need to remove negative numbers, should you choose an explicit iterator or `removeIf`? State your reasoning and the requirements on the data source.

The key points to keep clear are **support capability**, **the most recently returned element**, and **traversal state**. When all three are controlled, `Iterator.remove` lets you remove an element at the exact current position without searching for it again or manually guessing how to adjust the traversal.
