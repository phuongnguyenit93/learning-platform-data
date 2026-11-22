# modCount and Detecting Structural Modification When Appropriate

## 1. The Problem to Solve When Implementing a Custom Collection

An iterator must remember where it currently stands. For an index-based list, it might store the position of the next element; for a linked list, it might hold a reference to the next node. If elements are inserted into, removed from, or reorganized within the collection while the iterator is still in use, that information can become stale.

For example, suppose the initial list is `[A, B, C]`. The iterator has already returned `A` and is preparing to read index `1`. If another piece of code removes the first element, the list becomes `[B, C]`. Reading index `1` next will return `C`, skipping `B`. Index-access methods may still run normally, but the traversal no longer corresponds to its original assumptions.

In a mutable collection, the designer must choose a policy for this situation. One common choice is to **detect disallowed modifications and report an error early**, known as fail-fast behavior. For a class extending `AbstractList`, the protected field `modCount` supports that choice; a subclass can use the iterators provided by the superclass. This is part of designing collection behavior, not an automatic mechanism available out of the box for every `Collection` implementation. [AbstractList in Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractList.html#modCount)

This lesson progresses from the stale-iterator scenario to three practical exercises:

1. Distinguishing structural modifications from value replacements.
2. Updating the counter properly in a custom class and understanding the expected value held by each iterator.
3. Examining indirect modification paths, views, and the limitations of fail-fast detection.

Required background knowledge includes `List`, `Iterator`, `ListIterator`, abstract class inheritance, and exceptions. The complete programs below use Java 17 and require no external libraries.

## 2. What Does modCount Record?

### 2.1. Structural Modification vs. Value Modification

In the context of a list, adding or removing an element is clearly a structural modification: both the number of elements and the relationship between indices and elements can change. The concept also includes modifications that disrupt an ongoing traversal; it cannot be defined solely by comparing two `size()` values.

A standard list's `set(index, value)` operation replaces the value at an existing position. It does not insert a new position, does not remove an old position, and is usually not counted as a structural modification. For example, the `ArrayList` documentation distinguishes adding/removing elements or resizing the backing array from setting an element's value. The specific policy must still be read according to the class being used. [ArrayList in Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html)

In the `TrackedList` class that we will build later, we deliberately choose a simple policy:

| TrackedList Operation | Structural Modification? | Counter Handling in This Class |
| --- | --- | --- |
| `get(i)`, `size()` | No | Unchanged |
| `set(i, x)` with a valid index | No | Unchanged |
| Successful `add(i, x)` | Yes | Increment by one |
| Successful `remove(i)` | Yes | Increment by one |
| `remove(Object)` when element is not found | No element removed | Unchanged via inherited execution path |
| `add(i, x)` or `remove(i)` failing due to invalid index | Data not updated | Unchanged |
| Removing a range containing two elements by removing each element individually | Two primitive removals | Increment by two via two `remove(int)` calls |

This table is the contract for our example, not a rule dictating the internal counter values of every JDK class. Operations such as capacity optimization, sorting, or bulk processing must be evaluated according to their own policies and implementations; do not infer that "if the size is unchanged, the iterator is definitely still valid."

### 2.2. Do Not Equate modCount with size or Method Call Count

Two lists that end up with the same size can still have different structural histories:

```text
Before: [A, B], size = 2
Remove A: [B], size = 1
Insert X: [X, B], size = 2
```

An iterator created before the removal must not conclude that everything is unchanged simply because the size is `2` again. The counter helps recognize that modifications occurred during that interval.

Conversely, calling `get(0)` a hundred times does not produce a hundred structural modifications. In this lesson's example, a call to `remove("missing")` also produces no modification if the element is not found. Designing the counter requires adhering to actual data-updating paths.

This value is not a business identifier, a persistent version number, or a change log. Do not expose it in the public API for callers to deduce what the list previously contained. The `revisionForDemo()` method in the first program is purely for educational observation.

### 2.3. Mutating an Element Object Is a Separate Issue

If a list contains mutable objects, calling a method on an element object does not pass through the list's mutating methods. A structural counter does not automatically track every internal field inside each element.

Therefore, the absence of a `ConcurrentModificationException` does not prove that element contents are immutable. For elements used as hash keys or participating in ordering comparisons, mutating the element's own state can break the invariants of the underlying storage structure itself. A counter on the collection cannot automatically fix that problem.

## 3. One Counter for the Collection, One Expectation per Iterator

We can visualize two roles:

- The collection holds `modCount`: shared information about the history of structural modifications.
- Each iterator holds `expectedModCount`: the value that specific iterator currently expects.

The following diagram illustrates the concept, not the complete iterator code:

```text
Creating an iterator:
    expectedModCount = modCount

Before a step requiring verification:
    if modCount != expectedModCount:
        throw ConcurrentModificationException

After the iterator performs a supported modification itself:
    adjust traversal position
    expectedModCount = modCount
```

In the OpenJDK 17 source code for `AbstractList`, `next()` checks the counter before reading the element. The iterator's `remove()` calls the list's removal path, adjusts its cursor, and then adopts the new counter value. `ListIterator` likewise manages its expected value when performing its own mutating operations. This describes a specific implementation used to explain the experiments in this lesson, not a promise that every iterator shares the exact same check points. [OpenJDK 17 AbstractList Source Code](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/AbstractList.java)

Example with two iterators `a` and `b`:

```text
Collection.modCount = 7
a.expected = 7
b.expected = 7

a removes an element via a.remove():
Collection.modCount = 8
a.expected = 8
b.expected = 7
```

Iterator `a` knows which element it just removed and has adjusted its position. Iterator `b` does not have its expected value updated along with `a`; it must recognize that the data it relies on has changed. If every iterator automatically accepted the new counter value on each read, the detection mechanism would lose its purpose.

The values `7` and `8` here only help explain the equality/inequality relationship. Code using the collection never needs to know what specific number the counter currently holds.

## 4. Proper Implementation When Extending AbstractList

### 4.1. Placing Responsibility on Primitive Add and Remove Operations

This example uses a private `ArrayList` to store data, but returns iterators provided by the outer class's `AbstractList` superclass. Consequently, the internal counter of the backing `ArrayList` cannot substitute for `TrackedList`'s own `modCount`.

Methods to pay attention to:

- `get` and `size` read data.
- `set` replaces a value, leaving the counter unchanged according to our chosen policy.
- `add(int, E)` and `remove(int)` modify the data successfully and then increment the outer class's counter.
- `data` is never exposed externally, ensuring structural modification paths cannot bypass the responsibility of updating the counter.

The `AbstractList` documentation requires subclasses wishing to use this fail-fast mechanism to update the field in overridden structural modification methods; a single call to a primitive add/remove operation specified in the contract must not increment the field by more than one. With the implementation below, each successful primitive operation increments the counter exactly once. [AbstractList modCount Contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractList.html#modCount)

### 4.2. Complete Program

Save to file `TrackedListDemo.java`. All operations in the program run sequentially on a single thread.

```java
import java.util.AbstractList;
import java.util.ArrayList;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;
import java.util.ListIterator;

public class TrackedListDemo {
    static final class TrackedList<E> extends AbstractList<E> {
        private final ArrayList<E> data = new ArrayList<>();

        @Override
        public E get(int index) {
            return data.get(index);
        }

        @Override
        public int size() {
            return data.size();
        }

        @Override
        public E set(int index, E element) {
            return data.set(index, element);
        }

        @Override
        public void add(int index, E element) {
            data.add(index, element);
            modCount++;
        }

        @Override
        public E remove(int index) {
            E old = data.remove(index);
            modCount++;
            return old;
        }

        int revisionForDemo() {
            return modCount;
        }
    }

    private static void expectCme(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected CME: " + label);
        } catch (ConcurrentModificationException ex) {
            System.out.println(label + "=CME");
        }
    }

    public static void main(String[] args) {
        TrackedList<Integer> list = new TrackedList<>();
        list.addAll(List.of(10, 20, 30));
        System.out.println("initial=" + list);
        System.out.println("revision=" + list.revisionForDemo());

        Iterator<Integer> first = list.iterator();
        System.out.println("first=" + first.next());
        list.set(1, 200);
        System.out.println("after-set revision=" + list.revisionForDemo());
        System.out.println("next-after-set=" + first.next());
        list.add(40);
        expectCme("external-add", () -> first.next());

        Iterator<Integer> owner = list.iterator();
        Iterator<Integer> observer = list.iterator();
        System.out.println("owner-next=" + owner.next());
        owner.remove();
        System.out.println("after-owner-remove=" + list);
        System.out.println("owner-continues=" + owner.next());
        expectCme("other-iterator", () -> observer.next());

        int beforeNoOp = list.revisionForDemo();
        System.out.println("remove-missing=" + list.remove(Integer.valueOf(999)));
        System.out.println("missing-keeps-revision="
                + (beforeNoOp == list.revisionForDemo()));
        try {
            list.remove(99);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("bad-index=IndexOutOfBoundsException");
        }
        System.out.println("failure-keeps-revision="
                + (beforeNoOp == list.revisionForDemo()));

        ListIterator<Integer> editor = list.listIterator();
        System.out.println("editor-next=" + editor.next());
        editor.set(201);
        editor.add(202);
        System.out.println("editor-continues=" + editor.next());
        System.out.println("after-editor=" + list);

        List<Integer> view = list.subList(1, 3);
        list.set(1, 222);
        System.out.println("view-after-set=" + view);
        view.remove(0);
        System.out.println("view-after-own-remove=" + view);
        System.out.println("root-after-view-remove=" + list);
        list.add(50);
        expectCme("old-view", () -> view.size());

        TrackedList<Integer> batch = new TrackedList<>();
        batch.addAll(List.of(1, 2, 3, 4));
        int batchStart = batch.revisionForDemo();
        batch.subList(1, 3).clear();
        System.out.println("batch=" + batch);
        System.out.println("batch-revision-delta="
                + (batch.revisionForDemo() - batchStart));
        int emptyStart = batch.revisionForDemo();
        batch.subList(1, 1).clear();
        System.out.println("empty-range-keeps-revision="
                + (emptyStart == batch.revisionForDemo()));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 TrackedListDemo.java
java TrackedListDemo
```

Stdout:

```text
initial=[10, 20, 30]
revision=3
first=10
after-set revision=3
next-after-set=200
external-add=CME
owner-next=10
after-owner-remove=[200, 30, 40]
owner-continues=200
other-iterator=CME
remove-missing=false
missing-keeps-revision=true
bad-index=IndexOutOfBoundsException
failure-keeps-revision=true
editor-next=200
editor-continues=30
after-editor=[201, 202, 30, 40]
view-after-set=[222, 30]
view-after-own-remove=[30]
root-after-view-remove=[201, 30, 40]
old-view=CME
batch=[1, 4]
batch-revision-delta=2
empty-range-keeps-revision=true
```

### 4.3. Interpreting the Output Along Data Modification Paths

`revision=3` appears because the example adds three elements through primitive add operations. After `set(1, 200)`, the counter remains `3`; the first iterator proceeds to read the new value `200`. This also demonstrates that the iterator does not hold an independent copy of the entire original contents.

After `list.add(40)`, the first iterator no longer holds a matching expected value. The call to `first.next()` throws an exception in our experiment. There is no second thread: a modification outside the iterator on the exact same thread is sufficient to create a situation requiring detection.

`owner.remove()` removes the element that `owner` itself just returned. That iterator can continue, whereas `observer`, which was created before the removal, becomes invalidated. This is why the expected value is updated only for the iterator performing the modification.

Next, removing a nonexistent value returns `false`; removing at index `99` throws `IndexOutOfBoundsException`. Both counter check lines print `true`, because neither branch performs a successful removal in our example class.

The `ListIterator` section replaces `200` with `201`, inserts `202`, and then continues to `30`. After an insertion, the cursor sits after the newly inserted element; the program did not forget to read `202`. Adjusting the cursor position and updating the expected counter value are both responsibilities of the iterator. The `set`, `add`, and `remove` rules of `ListIterator` must be respected alongside the counter mechanism. [ListIterator in Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html)

The final two segments covering views and range removal will be analyzed separately in later sections. They are included in the same program to test the class across multiple call paths, not just direct `add` and `remove` calls.

### 4.4. Why Increment Only After a Successful Modification?

In `add(int, E)`, `data.add` may reject an invalid index before modifying any data. If `modCount++` were written before that call, a failed operation could invalidate existing valid iterators even though the list never changed.

Similarly, `remove(int)` increments the counter only after retrieving the removed element. This rule is straightforward when the backing store's primitive operation either succeeds or rejects the request before mutating data.

Do not overgeneralize that conclusion into "any compound operation that throws an exception leaves everything unchanged." A bulk operation might partially modify the collection and then fail. If you implement such an algorithm yourself, you must ensure that any modifications that actually took place are reflected in the counter—or design the operation for atomicity/validation before mutating data. The counter does not automatically provide rollback capability.

### 4.5. Do Not Increment Twice Along the Same Call Path

If `add(E)` delegates to `add(size(), E)`, do not increment the counter a second time simply because both methods are named `add`. Identify the single place that owns the actual data modification.

Similarly, if the inherited `remove(Object)` uses an iterator and that iterator calls `remove(int)`, the responsibility of incrementing has already been fulfilled inside `remove(int)`. Adding another increment in an outer wrapper method can make the policy inconsistent.

When optimizing a method to access the backing store directly, re-verify its execution path. The fact that the counter was previously updated indirectly via an iterator does not guarantee that the optimized version still passes through that path.


## 5. Three Design Defects That the Counter Helps Distinguish

The next program deliberately constructs flawed variants relative to our goal: **a mutable list where value replacement is non-structural and iterators detect external structural modifications**.

`countStructural` and `countReplacement` are purely experimental switches. A real production class should never provide switches that toggle iterator contracts on and off like this.

### 5.1. Complete Program

Save to file `CounterDefectsDemo.java`.

```java
import java.util.AbstractList;
import java.util.ArrayList;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;

public class CounterDefectsDemo {
    static final class BrokenList<E> extends AbstractList<E> {
        private final ArrayList<E> data;
        private final boolean countStructural;
        private final boolean countReplacement;

        BrokenList(List<E> initial, boolean countStructural,
                   boolean countReplacement) {
            data = new ArrayList<>(initial);
            this.countStructural = countStructural;
            this.countReplacement = countReplacement;
        }

        @Override
        public E get(int index) {
            return data.get(index);
        }

        @Override
        public int size() {
            return data.size();
        }

        @Override
        public E set(int index, E element) {
            E old = data.set(index, element);
            if (countReplacement) {
                modCount++;
            }
            return old;
        }

        @Override
        public void add(int index, E element) {
            data.add(index, element);
            if (countStructural) {
                modCount++;
            }
        }

        @Override
        public E remove(int index) {
            E old = data.remove(index);
            if (countStructural) {
                modCount++;
            }
            return old;
        }
    }

    public static void main(String[] args) {
        BrokenList<String> missing =
                new BrokenList<>(List.of("A", "B", "C"), false, false);
        Iterator<String> stale = missing.iterator();
        System.out.println("missing-first=" + stale.next());
        missing.remove(0);
        System.out.println("missing-current=" + missing);
        System.out.println("missing-next=" + stale.next());

        BrokenList<String> tooEager =
                new BrokenList<>(List.of("A", "B"), true, true);
        Iterator<String> reader = tooEager.iterator();
        tooEager.set(1, "B2");
        try {
            reader.next();
            throw new AssertionError("Expected false positive");
        } catch (ConcurrentModificationException ex) {
            System.out.println("replacement=CME");
        }

        BrokenList<String> sameSize =
                new BrokenList<>(List.of("A", "B"), true, false);
        Iterator<String> old = sameSize.iterator();
        int savedSize = sameSize.size();
        sameSize.remove(0);
        sameSize.add(0, "X");
        System.out.println("same-size=" + (savedSize == sameSize.size()));
        try {
            old.next();
            throw new AssertionError("Expected CME");
        } catch (ConcurrentModificationException ex) {
            System.out.println("same-size-history=CME");
        }

        BrokenList<String> boundary =
                new BrokenList<>(List.of("A", "B"), true, false);
        Iterator<String> cursor = boundary.iterator();
        System.out.println("boundary-first=" + cursor.next());
        boundary.remove(0);
        System.out.println("boundary-hasNext=" + cursor.hasNext());
        System.out.println("boundary-current=" + boundary);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 CounterDefectsDemo.java
java CounterDefectsDemo
```

Stdout:

```text
missing-first=A
missing-current=[B, C]
missing-next=C
replacement=CME
same-size=true
same-size-history=CME
boundary-first=A
boundary-hasNext=false
boundary-current=[B]
```

### 5.2. Forgetting to Update the Counter: No Exception, but Traversal Violates Assumptions

The `missing` variant removes actual data without incrementing `modCount`. The iterator reads `A`, after which the list becomes `[B, C]`. The next read returns `C`.

Because this class inherits an index-based iterator, the cursor continues from index `1`. Nothing informs the iterator that the element at index `0` was just removed. In this experiment, the observable consequence is that `B` is silently skipped.

Do not try to fix this by catching an exception and ignoring it, because no exception is thrown here to catch. You must fix the structural modification path that neglected the counter. At the same time, write application code that respects the contract: if you need to remove elements during traversal, use an operation supported by the iterator or structure the work into separate traversal and update phases.

The absence of a counter update is only a bug when it contradicts the chosen mechanism and policy. `AbstractList` permits subclasses to opt out of fail-fast behavior; do not conclude from this example that every collection is required to have a field named `modCount`.

### 5.3. Counting Value Replacements: Throwing Exceptions Contrary to the Intended Policy

The `tooEager` variant increments the counter inside `set`. Even though `set` does not change the number of positions, it still causes the iterator to fail as soon as it reads.

If a class is designed with a standard value-replacement policy like `TrackedList`, this is a false positive caused by the class's own recording logic. The author made the counter mean "some data-modifying method was called," whereas the iterator uses it to mean "structural assumptions are no longer valid."

Another collection could publish a stricter traversal policy, but that policy would have to be explicitly designed and documented. Do not alter the meaning of the field merely to increase the number of cases that throw exceptions.

### 5.4. Checking Only Size: Missing a Remove-Then-Insert History

The `sameSize` variant removes `A` and then inserts `X`. The output `same-size=true` confirms that comparing sizes reveals no difference between before and after.

The counter in this variant increments on both structural modifications. The old iterator still recognizes that a modification occurred and throws an exception. What needs to be detected is whether the traversal's assumptions have been affected, not whether the final list has more or fewer elements.

This is also why you must never set `modCount = size()`. The two quantities represent two distinct concepts. Do not reset the counter to `0` in `clear()` simply because the list's size becomes `0` at that moment.

### 5.5. A Normal Return from hasNext Is Not a Certificate of Iterator Validity

The `boundary` section reads `A` and then removes the first element directly through the list. The iterator's cursor is currently `1`, and the modified list also has a size of `1`. `hasNext()` returns `false`, so a loop that continues only while `hasNext()` returns `true` will terminate without ever reaching the next read step.

This result is verified with the iterator inherited from `AbstractList` on the Java 17 runtime used in our experiment. It aligns with the OpenJDK 17 source code, where that iterator's `hasNext()` compares the cursor against the list size without checking `modCount` at that step. Do not turn that implementation detail into a universal rule for all iterators. [Iterator Code in OpenJDK 17 AbstractList](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/AbstractList.java)

Therefore, never write a workflow like "call `hasNext()`; if it hasn't thrown an error yet, go ahead and modify the list and keep using the iterator." You should avoid violating the traversal policy by design, rather than waiting for a specific method call to catch the mistake for you.

## 6. Tracking All Modification Paths, Including Inherited Methods

### 6.1. A Public API Call Can Traverse Multiple Layers

In `TrackedList`, overriding just the primitive operations is enough for several inherited methods to work properly through them. For example, in our program:

```text
addAll
  → adds each element
  → TrackedList.add(int, E)
  → modifies data
  → increments modCount

subList(...).clear()
  → inherited range-removal path
  → iterator removes each element in the range
  → TrackedList.remove(int)
  → modifies data
  → increments modCount
```

The diagram depicts the execution paths active in our example class and verified by stdout. When you override additional methods for performance, these execution paths may change.

The `AbstractCollection` documentation explains that many default method implementations rely on `iterator()`, `add`, and `Iterator.remove()`. Consequently, implementing a custom iterator affects more than `for` loops; it also affects inherited operations that use the iterator internally. [AbstractCollection in Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractCollection.html)

### 6.2. Bulk Operations Need Not Increment by the Input Element Count

In the first program:

```text
batch=[1, 4]
batch-revision-delta=2
```

The two elements `2` and `3` were removed via two primitive removal operations, resulting in a delta of `2`. This is the result of our example class's execution path, not a requirement that every `clear`, `removeAll`, or `addAll` implementation must increment the counter by the exact number of affected elements.

If another class removes an entire range using a direct algorithm on the backing store, it may record the modification as a single operation unit. What matters is keeping the detection mechanism consistent, honoring the superclass contract, and never overlooking modifications that older iterators must treat as invalidating.

When designing a bulk method, choose one clear path:

- **Delegate to primitive operations that already update the counter:** do not add an extra umbrella increment simply because the outer method is also a mutating method.
- **Modify the backing store directly:** that direct method takes responsibility for reflecting the changes in the detection mechanism.

Do not accidentally mix the two paths. If a method partially completes before failing, examine the remaining state and existing iterators rather than testing only the fully successful case.

### 6.3. No-Ops Must Be Understood per Specific Class

In `TrackedList`, clearing an empty range does not invoke any primitive removal operation, yielding:

```text
empty-range-keeps-revision=true
```

This is a verifiable characteristic of the class we built. Do not treat it as a universal guarantee for every operation that "looks like a no-op" across all collections.

An operation that leaves `size()` unchanged might still affect an iterator's assumptions. Conversely, a call that finds no element to remove might only read data and return `false`. Always read the contract and trace the specific execution path before deciding which category an operation falls into.

### 6.4. Easily Overlooked Paths in a Custom Class

When adding features, audit them based on their ability to mutate the backing store:

| Entry Point | What to Check in the Class You Are Writing |
| --- | --- |
| Primitive `add`, `remove` | A successful modification is recorded exactly once at the owning site |
| `clear`, range removal | Does it go through primitive removal or mutate the backing data directly? |
| `addAll`, `removeAll`, `retainAll` | Does an optimized branch still update the detection mechanism? |
| `removeIf` | Does it use the iterator according to contract, and how does it handle a predicate throwing an exception? |
| Iterator self-remove/insert | Updates the data, cursor position, and the iterator's own expected value |
| Mutable views | Modifications are properly forwarded to the backing structure |
| Direct backing-store access | Does any internal or external path bypass the tracking mechanism entirely? |

You do not need to override every method in this table. What you must verify is that every method the class supports travels through an appropriate path. Proper inheritance is often simpler and more reliable than a large set of nearly identical overrides.

## 7. subList: Same Backing Data, Multiple Observation States

`subList` is a view of a portion of a list, not an independent copied list. Non-structural value replacements are reflected across both sides. The `List` contract specifies that the semantics of the view become undefined if the backing list is structurally modified through any path other than the view itself. [List.subList in Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#subList(int,int))

The view section of `TrackedListDemo` demonstrates three distinct scenarios.

### 7.1. Replacing a Value via the Backing List

After creating `view = list.subList(1, 3)`, the program calls `list.set(1, 222)`. The first element of the view changes to `222`:

```text
view-after-set=[222, 30]
```

Our example class does not treat `set` as a structural modification. Iterators and views are not snapshots of old values; they continue to access the backing data.

### 7.2. Removing via the View Itself

The program calls `view.remove(0)`. The output is:

```text
view-after-own-remove=[30]
root-after-view-remove=[201, 30, 40]
```

The operation is forwarded to the backing list at the appropriate index, and the view's own state is updated through the path it supports. Both the backing list and the view remain consistent with this removal.

That does not mean every previously created iterator remains valid. If a separate iterator already existed on the backing data, a removal through the view is still an external modification relative to that iterator.

### 7.3. Adding via the Backing List and Reusing the Old View

After `list.add(50)`, the program attempts `view.size()` and observes `old-view=CME`. This is the detection mechanism of the inherited view in our experiment.

Do not extrapolate from this result that every `List` implementation is required to throw the exact same exception on the exact same method call after a caller violates the view usage conditions. Nor should you continue using an old view after catching the exception. Route modifications through valid paths, or recreate the view from the updated list when starting a new unit of work.

If you need an independent list to iterate over while the original list undergoes future modifications, choose copying deliberately. Copying does not automatically make element objects immutable, and creating a copy in an environment with concurrent writes still requires a thread-safe access policy.


## 8. When Not Inheriting AbstractList's Iterators

### 8.1. A Field Named modCount Does Not Automatically Create a Check Mechanism

`AbstractCollection` requires subclasses to provide an iterator and a size method to form a minimal collection. It does not provide a built-in `modCount` field paired with an iterator like `AbstractList` does. If you choose a counter-based modification detection mechanism, you must wire that counter to your custom iterator yourself. [AbstractCollection in Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractCollection.html)

The program below builds a small collection that allows duplicate elements. It is not a `Set` and exposes no index-based access API externally. Data is stored in a private `ArrayList`; the custom iterator reads data by index and uses the outer class's `structureVersion`.

The name `structureVersion` is chosen deliberately: this field is defined by this class, not inherited from `AbstractList`. The mechanism still consists of two parts: the current version on the collection and the expected version private to each iterator.

### 8.2. Complete Program

Save to file `ExplicitIteratorDemo.java`.

```java
import java.util.AbstractCollection;
import java.util.ArrayList;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;
import java.util.NoSuchElementException;

public class ExplicitIteratorDemo {
    static final class VersionedBag<E> extends AbstractCollection<E> {
        private final ArrayList<E> data = new ArrayList<>();
        private int structureVersion;

        @Override
        public int size() {
            return data.size();
        }

        @Override
        public boolean add(E value) {
            data.add(value);
            structureVersion++;
            return true;
        }

        private void removeAt(int index) {
            data.remove(index);
            structureVersion++;
        }

        @Override
        public Iterator<E> iterator() {
            return new Iterator<E>() {
                private int cursor;
                private int lastReturned = -1;
                private int expectedVersion = structureVersion;

                private void checkVersion() {
                    if (structureVersion != expectedVersion) {
                        throw new ConcurrentModificationException();
                    }
                }

                @Override
                public boolean hasNext() {
                    checkVersion();
                    return cursor < data.size();
                }

                @Override
                public E next() {
                    checkVersion();
                    if (cursor >= data.size()) {
                        throw new NoSuchElementException();
                    }
                    E value = data.get(cursor);
                    lastReturned = cursor;
                    cursor++;
                    return value;
                }

                @Override
                public void remove() {
                    checkVersion();
                    if (lastReturned < 0) {
                        throw new IllegalStateException();
                    }
                    removeAt(lastReturned);
                    cursor = lastReturned;
                    lastReturned = -1;
                    expectedVersion = structureVersion;
                }
            };
        }
    }

    public static void main(String[] args) {
        VersionedBag<String> bag = new VersionedBag<>();
        bag.addAll(List.of("A", "B", "C"));
        Iterator<String> it = bag.iterator();
        System.out.println("first=" + it.next());
        it.remove();
        System.out.println("after-remove=" + bag);
        try {
            it.remove();
        } catch (IllegalStateException ex) {
            System.out.println("double-remove=IllegalStateException");
        }
        System.out.println("continues=" + it.next());

        Iterator<String> stale = bag.iterator();
        bag.add("D");
        try {
            stale.hasNext();
            throw new AssertionError("Expected CME");
        } catch (ConcurrentModificationException ex) {
            System.out.println("custom-hasNext=CME");
        }

        System.out.println("remove-B=" + bag.remove("B"));
        System.out.println("after-inherited-remove=" + bag);
        System.out.println("remove-missing=" + bag.remove("missing"));
        bag.clear();
        System.out.println("after-inherited-clear=" + bag);
        Iterator<String> empty = bag.iterator();
        System.out.println("empty-hasNext=" + empty.hasNext());
        try {
            empty.next();
        } catch (NoSuchElementException ex) {
            System.out.println("empty-next=NoSuchElementException");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ExplicitIteratorDemo.java
java ExplicitIteratorDemo
```

Stdout:

```text
first=A
after-remove=[B, C]
double-remove=IllegalStateException
continues=B
custom-hasNext=CME
remove-B=true
after-inherited-remove=[C, D]
remove-missing=false
after-inherited-clear=[]
empty-hasNext=false
empty-next=NoSuchElementException
```

### 8.3. Invariants to Maintain When Writing a Custom Iterator

In this program, three private iterator fields work together:

| Field | Meaning in VersionedBag |
| --- | --- |
| `cursor` | The index to read on the next `next()` call |
| `lastReturned` | The index of the element most recently returned and still eligible for removal; `-1` means none |
| `expectedVersion` | The structural version that this iterator currently accepts |

After `next()` returns an element, `cursor` advances. When the iterator removes that element, subsequent elements shift left, so the program resets `cursor` back to the removed position. If this step is omitted, the next element can be skipped.

After a valid removal:

1. The collection increments `structureVersion` inside `removeAt`.
2. The iterator adjusts its read cursor.
3. The iterator resets `lastReturned` to prevent duplicate removals for the same `next()` result.
4. The iterator adopts the new version into `expectedVersion`.

Updating only the final step without adjusting the cursor can make the iterator "not throw an error" while reading the wrong element. Adjusting only the cursor without adopting the new version causes the iterator to throw an exception on account of its own valid removal.

The rule that `remove()` may only be called after a valid `next()` call and must not be called twice for the same result is part of the `Iterator` contract. Calling `next()` when no elements remain must throw `NoSuchElementException`; that is not a structural modification scenario. [Iterator in Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html)

### 8.4. Checking Inside hasNext Is a Choice Made by This Class

`VersionedBag` deliberately calls `checkVersion()` inside `hasNext()`, `next()`, and `remove()`. Consequently, `stale.hasNext()` throws an exception after an element is added to the collection.

Comparing this with the `boundary` experiment from Section 5 shows why you should not memorize a single fixed exception-throwing point for the entire Java Collections Framework. Implementing a custom iterator means explicitly choosing check points and fulfilling the published contract.

Adding a check point can help catch certain misuse patterns earlier. However, it does not create an atomic execution region around the entire read operation.

### 8.5. Inherited remove and clear Also Use This Iterator

`bag.remove("B")` returns `true`, leaving `[C, D]`. `bag.clear()` removes all elements. In our program, both work properly even though the class overrides neither method: the inherited execution paths rely on an iterator that supports removal.

This example tests more than an isolated `Iterator.remove()` call. It demonstrates that the iterator implementation forms the foundation for inherited collection operations.

Even so, this remains a small illustrative class: it makes no concurrency guarantees, does not analyze bulk-removal performance, and does not include a full library test suite. Do not interpret a single demonstration run as proof of every contract a public collection must satisfy.

## 9. When Is Choosing Fail-Fast Appropriate?

### 9.1. When the Class Has Mutable Structure and Wants to Detect Stale Iterators

Fail-fast behavior is useful when insertion/removal operations render old traversal positions unreliable, callers are required not to mutate the structure outside the iterator during traversal, and early failure helps expose misuse.

For `TrackedList`, leveraging `AbstractList`'s iterators alongside `modCount` is the natural approach. For `VersionedBag`, the iterator is custom-written, so the counter and check points must also be wired explicitly.

The deciding factor is **the traversal policy and data structure**, not the field name. Renaming `structureVersion` to `modCount` in the third program does not automatically turn it into an `AbstractList` subclass.

### 9.2. Do Not Force the Same Mechanism onto Every Collection Type

Different design choices serve different goals:

| Policy or Structure | What the Author Needs to Decide |
| --- | --- |
| Direct traversal over mutable data, with a rule prohibiting modification outside the iterator | A counter can be used to detect violations |
| Data that never changes structurally after creation | Do not add a counter just to have a field with that name |
| Iterator traverses a snapshot copy of the contents taken at creation time | Subsequent modifications to the source are handled according to the snapshot contract |
| Concurrent collection with weakly consistent iterators | Follow the observation policy of that concurrent structure |
| Wrapper or view over another collection | Determine which data is shared and which mechanism is responsible for detection |

For example, `CopyOnWriteArrayList`'s iterator uses an array snapshot and never throws `ConcurrentModificationException`; mutating operations directly on that iterator are unsupported. This is an intentional design choice of that class, not a fail-fast implementation missing a counter. [CopyOnWriteArrayList in Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html)

`ConcurrentHashMap`'s iterators are designed to reflect state at different points during traversal without throwing `ConcurrentModificationException`. Do not replace that policy with a standard fail-fast counter mechanism merely because you are writing a collection. [ConcurrentHashMap in Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

Furthermore, a read-only view that prohibits modification through itself does not guarantee immutable data: the backing structure might still be mutated through another reference. When choosing a detection mechanism, examine the entire data ownership and sharing graph.

### 9.3. For Custom Maps and Sets, Start from That Structure's Policy

`AbstractMap` does not provide a built-in `modCount` mechanism like `AbstractList`. Its methods are built around `entrySet`; the iterator and iterator-based removal capability of the entry set are key components when implementing a mutable map. [AbstractMap in Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractMap.html)

`AbstractSet` inherits its foundation from `AbstractCollection` and adds set semantics; extending it does not automatically give you a fail-fast iterator. [AbstractSet in Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractSet.html)

If you build a map with a custom detection mechanism, you must consider its key, value, and entry views as well. A modification that invalidates an iterator on the root structure might be performed through a view; that path still needs to be managed.

For a set, attempting to add an element that is already present does not perform an insertion. For a map, updating the value of an existing key must likewise be distinguished from creating a new mapping according to your chosen contract. Do not mechanically copy a list's modification table onto every data structure.

## 10. modCount Does Not Make a Collection Thread-Safe

`ConcurrentModificationException` can occur within a single thread. The exception's name does not prove that two threads are running concurrently. The programs in this lesson deliberately use sequential call order so that causes and stdout can be verified deterministically.

Conversely, when multiple threads mutate data without proper synchronization, fail-fast operates only on a best-effort basis. The exception's documentation explicitly warns against relying on it being thrown for program correctness. [ConcurrentModificationException in Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ConcurrentModificationException.html)

Comparing a counter does not:

- Lock the structure being read.
- Turn the combined check-and-fetch sequence into an atomic operation.
- Automatically guarantee memory visibility of data fields across threads.
- Roll back partial changes that occurred before the error was reported.

In `VersionedBag`, another thread could still mutate data between `checkVersion()` and `data.get(cursor)` if the program permitted unsynchronized concurrent access. Adding checks in more places cannot eliminate a concurrent access design flaw.

Changing only the counter to `volatile`, `AtomicInteger`, or a wider numeric type does not turn the entire collection into a thread-safe structure either. Operations on the backing store, cursors, and multi-step invariants still require a unified coordination policy.

Appropriate approaches include confining the collection to a single thread, guarding access with a consistent locking protocol, iterating over a safely created snapshot copy, or choosing a structure from `java.util.concurrent` with a suitable contract. If you use a synchronized wrapper from `Collections`, its documentation requires manual synchronization around traversal on the designated mutex object; synchronizing individual method calls does not make an entire iteration loop atomic. [Collections.synchronizedList in Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedList(java.util.List))

Never use a loop that "catches `ConcurrentModificationException` and retries until it succeeds" as a concurrency coordination mechanism. Work performed before the exception may be duplicated, the underlying data may continue changing, and there is no guarantee of termination or consistency. Fix how data is owned, mutated, and traversed first.

## 11. Verifying an Implementation Instead of Just Waiting for an Exception

### 11.1. Categories of Scenarios to Test

When writing a collection with this mechanism, test each category separately:

1. **Normal traversal:** returns elements in the right order or set according to contract; calling `next()` when exhausted throws `NoSuchElementException`.
2. **External modification:** test adding, removing, and remove-then-add restoring the original size; verify detection at the points the class promises to check.
3. **Modification via the iterator:** a valid removal must allow that iterator to continue while adjusting its cursor properly.
4. **Iterator operation state:** calling `remove()` before `next()`, calling `remove()` twice for the same element, and calling operations after exhaustion.
5. **Multiple iterators and views:** does a modification through one path cause other active observers to recognize that their state is stale?
6. **No-op or failed branches:** nonexistent elements, empty ranges, invalid indices; counter behavior must match the class policy.
7. **Bulk methods and optimized overrides:** must not bypass the counter, must not double-increment, and must not hide partial modifications if an operation fails mid-way.

Do not treat the raw count of `ConcurrentModificationException`s thrown as a quality metric. An iterator that throws exceptions on operations the class declares valid is also broken.

The three programs in this lesson verify a subset of these categories using sequential operations. They do not test thread contention and must not be used to conclude that a collection is thread-safe.

### 11.2. Practice Exercises and Self-Check Hints

**Exercise 1 — Removal via two paths.** In `TrackedListDemo`, create an iterator and then call `list.remove(Integer.valueOf(30))`. Next, recreate the equivalent situation, but call `iterator.remove()` after the iterator itself returns `30`. How do these two paths differ in meaning for the iterator held by application code?

Hint: `remove(Object)` may use its own internal iterator. That does not make it a removal performed by the iterator that the application code is holding.

**Exercise 2 — Counter update bug.** Remove the `modCount++` line from `TrackedList.remove(int)` while keeping it in `add`. Will testing only external additions detect this bug?

Hint: No. You must test every removal path, including removal via views and inherited operations. One properly updated path does not cover another.

**Exercise 3 — Breaking a custom iterator.** In `VersionedBag`, remove the `cursor = lastReturned` line while keeping the `expectedVersion` update. After reading and removing `A` from `[A, B, C]`, what element is read next?

Hint: The cursor remains at index `1` while the data has shifted to `[B, C]`, so the next read skips `B` and returns `C`. A working counter does not replace correct cursor logic.

**Exercise 4 — Counting does not equal thread safety.** If you replace `structureVersion` with an `AtomicInteger` and use atomic increments, which steps of `next()` and `remove()` are still not protected as a single atomic unit?

Hint: Checking the version, checking bounds, reading the backing store, mutating data, and updating cursor positions remain separate multi-step operations. You must design a synchronization protocol covering the entire structure.

**Exercise 5 — Optimizing range removal.** If you override the range-removal path to shift data once instead of removing elements one by one, what checks and behaviors must be preserved?

Hint: Validate bounds before mutating, update the backing store and size accurately, reflect the modification in the detection mechanism, avoid double-incrementing through primitive removal paths, and test both views and iterators created prior to the operation. Do not treat the old implementation's stdout delta of `2` as a requirement for every new algorithm.

### 11.3. Key Takeaways

`modCount` is useful when paired with a well-defined traversal policy that every structural modification path adheres to. Each iterator must maintain its own expected value while accurately managing its cursor position and operation state.

When extending `AbstractList`, updating primitive operations properly lets you take advantage of inherited iterators and execution paths. When writing a custom iterator, you take responsibility for wiring all of those pieces together yourself. When using structures with snapshot or concurrent traversal policies, read their respective contracts before choosing a mechanism.

A call that does not throw an exception does not prove the data never changed. A call that throws an exception does not automatically repair improper usage. The value of the mechanism lies in helping detect a class of bugs early, while program correctness always comes from adhering to contracts and designing sound data access.
