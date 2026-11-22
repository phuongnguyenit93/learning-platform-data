# getFirst, getLast, removeFirst, and removeLast

## 1. Reading the Two Ends and Removing from the Two Ends Are Different Needs

An application has a list of processing steps `[fetch, check, save]`. A preview screen needs to know the opening step and the closing step without modifying the data. A processor, on the other hand, may need to remove the first step from the list after accepting the job.

Those two needs correspond to two groups of methods:

- `getFirst()` and `getLast()` **inspect** the elements at the two ends;
- `removeFirst()` and `removeLast()` **remove** the element while also returning the element that was just removed.

Since Java 21, these methods are part of the `SequencedCollection<E>` contract, allowing many ordered collection families to share a common vocabulary. Similar APIs on `Deque` and `LinkedList` existed beforehand; what is new in Java 21 is placing them at the shared contract level and adding them to types such as `List`.

This lesson focuses on the meaning of the four operations: which end is selected, how the data changes, what happens when the collection is empty or does not support removal, and how to use them properly when `null`, a single element, or a reversed view is involved. The full example requires **Java 21 or later** and cannot be used when targeting the Java 17 API.

## 2. How Are “First” and “Last” Determined?

**Encounter order** is the logical sequence from the first element to the last element of a collection. It is not physical layout in memory.

~~~text
current sequence:    fetch ---- check ---- save
                     first                 last

getFirst()           fetch
getLast()                                  save
~~~

This order is determined by the contract and state of the structure:

| Structure | Meaning of first/last |
| --- | --- |
| `List` | The first and last positions of the current list |
| `Deque` | The head and tail of the double-ended queue |
| `LinkedHashSet` with standard insertion | The first and last in insertion order of distinct elements |
| `SortedSet` | The first and last according to the comparison used by the set |
| `reversed()` view | First/last according to the reversed direction of the view |

`SequencedCollection` guarantees that a sequence exists to express these operations; it does not state that every sequence is ascending order or insertion order. The four methods take no arguments because the target position is already specified by the operation name. [Java 21: SequencedCollection](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html).

An example to keep in mind: if a linked set currently holds `[z, a, m]`, `getFirst()` returns `z`; it does not automatically look for `a` as the smallest letter. If a set sorted in descending numeric order currently holds `[40, 30, 20, 10]`, the first element is `40`. To understand the result, you must first understand the ordering rule of the source.

## 3. Contract of Each Method

All four have return type `E`, the element type of the collection. They do not return a new collection, nor do they return a `boolean` success flag.

| Method | When a matching element exists | Does it remove from the collection? |
| --- | --- | --- |
| `E getFirst()` | Returns the current first element | No |
| `E getLast()` | Returns the current last element | No |
| `E removeFirst()` | Returns the first element that was just removed | Yes, if the operation is supported |
| `E removeLast()` | Returns the last element that was just removed | Yes, if the operation is supported |

### 3.1. getFirst and getLast Leave the Structure Unchanged

Given a regular list `[fetch, check, save]`:

~~~java
String first = steps.getFirst();
String last = steps.getLast();
~~~

This is a Java 21 illustrative snippet inside a method, assuming `steps` is a non-empty `List<String>`.

After the two statements:

- `first` equals `"fetch"`;
- `last` equals `"save"`;
- `steps` still has three elements in the same sequence.

If the element is an object, the result is a reference to that element, not an automatic deep copy. Calling `getFirst` does not remove or replace the element; if you mutate the state of the returned object, that is a separate action that must be evaluated against your data model.

### 3.2. removeFirst and removeLast Both Return a Value and Mutate the Collection

Consider the following sequence of operations on an `ArrayList` that supports removal:

~~~text
initial                         [fetch, check, save]

x = removeFirst()
x                               fetch
after first removal             [check, save]

y = removeLast()
y                               save
after last removal              [check]
~~~

After each successful removal, the size decreases by one. The second step operates on **the state after the first step**, rather than automatically working on a shared snapshot.

There is no need to call `getFirst` and then `removeFirst` just to obtain the removed value. `removeFirst` already returns that value. Writing an extra read can be both redundant and misleading to readers, making it look like there is a shared transaction between the two operations.

### 3.3. A Single Element Is Both First and Last

With `[only]`, both `getFirst()` and `getLast()` see `only`. However, after `removeFirst()`, the collection becomes empty. Calling `removeLast()` next on a mutable collection like `ArrayList` will not retrieve the same element again; it throws `NoSuchElementException`.

Therefore, “remove both ends” does not necessarily mean “always return exactly two values.” You must decide on a policy for sizes 0, 1, and at least 2. In the program below, `takeEnds` takes each existing boundary element exactly once: a single-element input yields only one result.

## 4. Empty Collections: There Is No Default Value for These Four Operations

On an empty `ArrayList`, all four of the following statements throw `NoSuchElementException`:

~~~java
empty.getFirst();
empty.getLast();
empty.removeFirst();
empty.removeLast();
~~~

These are four independent cases for illustration. If placed sequentially in the same execution flow without catching exceptions, the program stops at the first failing statement; the remaining three do not run automatically.

### 4.1. getFirst Differs from get(0) in the Empty Case

On a non-empty `List`, `getFirst()` can be thought of as corresponding to `get(0)`, and `getLast()` to `get(size() - 1)`. When the list is empty, however, the boundary API uses `NoSuchElementException`, whereas accessing an invalid index uses `IndexOutOfBoundsException`.

Similarly, the default methods on `List` express removing the first element using position `0` and removing the last element using `size() - 1` when elements exist, while handling the empty case according to the boundary-operation contract. Implementing classes may override them to use their own implementation. [Java 21: List, boundary operations](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#getFirst()).

Therefore, when migrating legacy code from `get(0)` to `getFirst()`, review your exception handling. The results for valid data may be identical, but the failure contract should not be overlooked.

### 4.2. Handling Empty Collections According to Business Meaning

There are three common approaches:

1. **Empty is a precondition violation:** call the boundary operation directly and let the caller handle the appropriate exception, or check and throw an explicit domain error.
2. **Empty is a normal outcome:** return a result representing the absence of data, or choose a queue API with suitable conventions.
3. **Need to wait for data:** use an appropriate blocking/queue mechanism; these four methods do not wait for an element to appear.

A pattern like `if (!items.isEmpty())` followed by `getFirst` is appropriate when you have exclusive access throughout the entire operation. It does not turn two separate calls into an atomic operation when multiple threads concurrently modify the collection.

### 4.3. Do Not Ignore Removal Restrictions When Interpreting Exceptions

`removeFirst` and `removeLast` are optional operations. If the source does not support removal, you may receive `UnsupportedOperationException`. Do not design generic code assuming “when empty, `NoSuchElementException` is always prioritized over every other exception” across all implementations.

Unmodifiable collections have their own rules for mutating methods. The `Collection` documentation states that implementations may reject unsupported operations even if the operation would not actually modify the data. [Java 21: Collection, optional operations](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collection.html).

The empty-case output in this lesson’s program uses a fresh `ArrayList`, so it does not conflate “no element present” with “removal not permitted.”

## 5. A null Value Does Not Mean an Empty Collection

Some implementations allow `null` elements. For the list `[null, tail]`:

- `getFirst()` returns `null`, yet the size remains 2;
- `removeFirst()` returns `null` and actually removes one element, leaving `[tail]`;
- only after removing `tail` as well does the list become empty.

`ArrayList` permits `null` elements, so this is a valid data state for this class. [Java 21: ArrayList](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ArrayList.html).

The danger lies in writing a custom helper that returns `null` for both “no element” and “an element whose value is `null`.” Two distinct states get merged, leaving callers unable to tell whether the operation removed data or not.

### 5.1. Optional Also Needs a Policy for null

The following illustrative snippet can lose information:

~~~java
return java.util.Optional.ofNullable(items.removeFirst());
~~~

If the first element is `null`, the removal succeeds, yet the result is `Optional.empty()`. That is indistinguishable from a convention meaning “no element to remove.”

`Optional.ofNullable` is defined to return an empty `Optional` when the argument is `null`. [Java 21: Optional](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Optional.html#ofNullable(T)).

If the data domain forbids `null`, a helper returning `Optional<E>` can make sense with a clear contract. If you need to preserve the possibility of `null`, use a result type that separates **whether an element was present** from **the element’s value**, such as `Removal<E>(boolean present, E value)` in the full program.

That is a type created for the lesson’s example, not a standard type built into the JDK. The check-and-remove helper here requires no concurrent modifications throughout the operation.

### 5.2. Distinguishing a null Element from a null Source Reference

If the `items` variable itself is `null`, calling `items.getFirst()` causes a `NullPointerException` because there is no receiver object for the call. That is not a way to signal an empty collection.

For public inputs, you can explicitly specify “`null` source not accepted” and validate with `Objects.requireNonNull`. Do not catch all `RuntimeException`s and convert them into “no data”; doing so can hide argument-passing bugs or sources that do not support the operation.

## 6. Same Method Names, Different Removal Permissions

The static type `List<E>` or `SequencedCollection<E>` does not guarantee that every implementation allows removal. You must check the concrete data source.

| Example source | Inspect ends when non-empty | Remove ends |
| --- | --- | --- |
| `new ArrayList<>(...)` | Yes | Yes |
| `new LinkedList<>(...)` | Yes | Yes |
| `new ArrayDeque<>(...)` | Yes | Yes |
| `Arrays.asList(...)` | Yes | Resizing not supported |
| `List.of(...)` | Yes | Not supported |
| Unmodifiable wrapper | Yes | Not supported through wrapper |

### 6.1. Arrays.asList Is Fixed-Size, Not Completely Immutable

`Arrays.asList(array)` returns a list backed by the given array, with a fixed size. `set` can replace elements and the change is visible in the array; add/remove operations that change the size are not supported. [Java 21: Arrays.asList](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html#asList(T...)).

Thus, a list can simultaneously allow `getFirst`, `getLast`, and `set`, while rejecting `removeFirst` and `removeLast`. Asking only “is it mutable?” is too broad; you need to ask **which operations** are permitted.

When you genuinely need a copy that supports resizing, you can create `new ArrayList<>(fixed)`. That is a decision about copying and data ownership, not a cast that unlocks permissions on the original source.

### 6.2. List.of and Unmodifiable Wrappers

A list from `List.of` does not allow adding, removing, or replacing elements. The demonstration program shows that reading the last element succeeds, whereas removing the last element fails.

`Collections.unmodifiableList(source)` and corresponding wrappers block mutating operations through the view. Blocking removal does not automatically create an independent copy; the underlying source can still be modified through another reference. [Java 21: Collections](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html).

If a method only needs to inspect the ends, it should not require the source to support removal. If a method needs to remove from the ends, that requirement must be stated in its contract rather than letting users discover it late via an exception.

## 7. Linked Sets, Sorted Sets, and Reversed Views

### 7.1. LinkedHashSet: Removing by Position in the Set’s Sequence

A `LinkedHashSet` created from `[z, a, m]` has `z` as first and `m` as last. `removeLast()` returns `m` and leaves `[z, a]` in the set.

This removes a boundary element, not the element with the largest value. `LinkedHashSet` maintains standard insertion order and provides the two-end operations in Java 21. [Java 21: LinkedHashSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashSet.html).

Set uniqueness still holds. If you previously attempted to add a duplicate value, do not assume there is a second occurrence for the two removal methods to pull out one after the other.

### 7.2. SortedSet: Both Ends Are Determined by the Comparison

`SortedSet` uses natural ordering or a `Comparator`. `getFirst` corresponds to the first element in that order, and `getLast` corresponds to the last element. With descending order on integers, they are the largest and smallest values in the usual arithmetic sense, respectively.

Boundary removal can still be supported on a mutable sorted set. The fact that `addFirst`/`addLast` are unsupported due to imposing a position does not mean `removeFirst`/`removeLast` are forbidden as well. Removing an existing element does not require placing data against the sorting rule. [Java 21: SortedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedSet.html).

Do not hardcode the assumption that `getFirst` is always the smallest number. Check the comparator. The main program intentionally uses `Comparator.reverseOrder()` to verify this point.

### 7.3. A Reversed View Flips Both the Read Ends and the Removal Ends

Given a mutable list and its `reversed()` view:

~~~text
source:                   [1, 2, 3, 4]
reversed view:            [4, 3, 2, 1]

view.getFirst()           4
view.getLast()            1

view.removeFirst()        returns 4, source remains [1, 2, 3]
view.removeLast()         returns 1, source remains [2, 3]
~~~

An allowed removal operation on the view propagates back to the underlying source structure. It does not merely drop the element from an imaginary copy.

However, the general contract of a reversed view leaves certain change-observation characteristics up to the implementation; do not automatically attribute every property of an `ArrayList` to all `SequencedCollection`s. In this example, both the source and the view are list usages verified by the program.

## 8. Comparing with Deque’s peek and poll

`Deque` has two styles for handling missing data:

| Intent | Throws an exception when empty | Returns a special value when empty |
| --- | --- | --- |
| Inspect first | `getFirst()` | `peekFirst()` returns `null` |
| Inspect last | `getLast()` | `peekLast()` returns `null` |
| Remove first | `removeFirst()` | `pollFirst()` returns `null` |
| Remove last | `removeLast()` | `pollLast()` returns `null` |

`peek` does not remove, while `poll` does remove. This is the `Deque` API family; do not call `peekFirst` on a variable declared only as `SequencedCollection` assuming the general interface has that method as well. [Java 21: Deque](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Deque.html).

If “the queue currently has no work” is a frequent situation, `pollFirst` usually expresses intent better than repeatedly calling `removeFirst` and catching exceptions to control a loop. However, the `null` convention is only easy to interpret when the source does not store `null`.

`ArrayDeque` forbids `null` and is not safe for concurrent modification across multiple threads without external synchronization. Most of its operations run in amortized constant time; operations that search by value or remove via an iterator position are different cases. [Java 21: ArrayDeque](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ArrayDeque.html).

By contrast, `LinkedList` permits `null`. If you use it as a `Deque` and insert `null`, `pollFirst() == null` could be the element just removed, which is not enough to conclude that the source was empty. [Java 21: LinkedList](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedList.html).

### 8.1. “Inspect Then Remove” Is Not a Transaction Across Multiple Threads

An interleaving schedule can look like this:

~~~text
Thread A: getFirst() sees job X
Thread B: removeFirst() takes X
Thread A: removeFirst() takes job Y or encounters an empty source
~~~

Even if each individual call on a concurrent structure is thread-safe on its own, Thread A’s two calls are not automatically bound to the same element.

If the goal is to claim ownership of the removed element for processing, use a single removal operation that returns the element, and choose an appropriate concurrency mechanism. `ConcurrentLinkedDeque` supports safe concurrent additions, removals, and reads, and forbids `null` elements, so a single `pollFirst` has a clearer empty convention. It does not turn a sequence of multiple calls into an atomic transaction. [Java 21: ConcurrentLinkedDeque](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentLinkedDeque.html).

If you must inspect, check multiple conditions, and remove multiple elements together as one unit, you need a synchronization design suited to the entire requirement. Do not use `isEmpty` or `size` as proof that the state will remain unchanged on the next call.

## 9. Complete Program to Verify Edge Cases

Save all the code below into **`EndOperationsDemo.java`**.

The program runs single-threaded. The two helpers `takeFirstIfPresent` and `takeEnds` assume exclusive access throughout the operation, as well as a source that supports the removals actually invoked. They do not provide rollback if a custom implementation allows the first step but rejects the subsequent one.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.Deque;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.SequencedCollection;
import java.util.SequencedSet;
import java.util.TreeSet;

public class EndOperationsDemo {
    record Removal<E>(boolean present, E value) {}

    // Requires exclusive access for the whole check-and-remove operation.
    static <E> Removal<E> takeFirstIfPresent(SequencedCollection<E> items) {
        if (items.isEmpty()) {
            return new Removal<>(false, null);
        }
        return new Removal<>(true, items.removeFirst());
    }

    // Removes each existing boundary once, including the singleton case.
    // Requires supported removals and exclusive access for the whole method.
    static <E> List<E> takeEnds(SequencedCollection<E> items) {
        List<E> removed = new ArrayList<>();
        if (!items.isEmpty()) {
            removed.add(items.removeFirst());
        }
        if (!items.isEmpty()) {
            removed.add(items.removeLast());
        }
        return removed;
    }

    static String failure(Runnable action) {
        try {
            action.run();
            return "no exception";
        } catch (NoSuchElementException | UnsupportedOperationException
                 | IndexOutOfBoundsException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        List<String> plan = new ArrayList<>(List.of("fetch", "check", "save"));
        System.out.println("read bounds: " + plan.getFirst() + " / " + plan.getLast());
        System.out.println("after reads: " + plan + ", size=" + plan.size());
        String first = plan.removeFirst();
        String last = plan.removeLast();
        System.out.println("removed bounds: " + first + " / " + last);
        System.out.println("remaining plan: " + plan);

        List<String> empty = new ArrayList<>();
        System.out.println("empty getFirst: " + failure(() -> empty.getFirst()));
        System.out.println("empty getLast: " + failure(() -> empty.getLast()));
        System.out.println("empty removeFirst: " + failure(() -> empty.removeFirst()));
        System.out.println("empty removeLast: " + failure(() -> empty.removeLast()));
        System.out.println("empty get(0): " + failure(() -> empty.get(0)));

        List<String> nullable =
                new ArrayList<>(Arrays.asList((String) null, "tail"));
        System.out.println("nullable getFirst: " + nullable.getFirst()
                + ", size=" + nullable.size());
        Removal<String> taken = takeFirstIfPresent(nullable);
        System.out.println("nullable removal: " + taken + ", remaining=" + nullable);
        System.out.println("nullable removeLast: " + nullable.removeLast());
        System.out.println("absent removal: " + takeFirstIfPresent(nullable));

        String[] backing = {"left", "right"};
        List<String> fixed = Arrays.asList(backing);
        System.out.println("fixed bounds: " + fixed.getFirst() + " / " + fixed.getLast());
        fixed.set(0, "changed");
        System.out.println("fixed set changes array: " + Arrays.toString(backing));
        System.out.println("fixed removeFirst: " + failure(() -> fixed.removeFirst()));

        List<String> readOnly = List.of("north", "south");
        System.out.println("read-only last: " + readOnly.getLast());
        System.out.println("read-only removeLast: " + failure(() -> readOnly.removeLast()));

        SequencedSet<String> selected =
                new LinkedHashSet<>(List.of("z", "a", "m"));
        System.out.println("linked set bounds: " + selected.getFirst()
                + " / " + selected.getLast());
        System.out.println("linked set removeLast: " + selected.removeLast());
        System.out.println("linked set remains: " + selected);

        SequencedSet<Integer> descending = new TreeSet<>(Comparator.reverseOrder());
        descending.addAll(List.of(10, 40, 20, 30));
        System.out.println("sorted bounds: " + descending.getFirst()
                + " / " + descending.getLast());
        int high = descending.removeFirst();
        int low = descending.removeLast();
        System.out.println("sorted removed: " + high + " / " + low
                + ", remaining=" + descending);

        List<Integer> source = new ArrayList<>(List.of(1, 2, 3, 4));
        List<Integer> backwards = source.reversed();
        System.out.println("reverse bounds: " + backwards.getFirst()
                + " / " + backwards.getLast());
        int reverseFirst = backwards.removeFirst();
        int reverseLast = backwards.removeLast();
        System.out.println("reverse removed: " + reverseFirst + " / " + reverseLast);
        System.out.println("source and reverse: " + source + " / " + backwards);

        List<String> singleton = new ArrayList<>(List.of("only"));
        System.out.println("singleton taken: " + takeEnds(singleton)
                + ", remaining=" + singleton);
        List<Integer> four = new ArrayList<>(List.of(1, 2, 3, 4));
        System.out.println("two ends taken: " + takeEnds(four) + ", remaining=" + four);

        Deque<String> queue = new ArrayDeque<>();
        System.out.println("deque empty getFirst: " + failure(() -> queue.getFirst()));
        System.out.println("deque empty peek/poll: " + queue.peekFirst()
                + " / " + queue.pollFirst());
        queue.addAll(List.of("W1", "W2", "W3"));
        List<String> drained = new ArrayList<>();
        String job;
        while ((job = queue.pollFirst()) != null) {
            drained.add(job);
        }
        System.out.println("deque drained: " + drained + ", empty=" + queue.isEmpty());
    }
}
~~~

Compile with JDK 21 or later and run on Java 21 or later:

~~~shell
javac --release 21 -encoding UTF-8 EndOperationsDemo.java
java EndOperationsDemo
~~~

`--enable-preview` is not needed. The example was compiled with release level 21 and run successfully using OpenJDK 24.0.2. The output uses ASCII strings so it does not depend on terminal accent rendering.

Exact stdout:

~~~text
read bounds: fetch / save
after reads: [fetch, check, save], size=3
removed bounds: fetch / save
remaining plan: [check]
empty getFirst: NoSuchElementException
empty getLast: NoSuchElementException
empty removeFirst: NoSuchElementException
empty removeLast: NoSuchElementException
empty get(0): IndexOutOfBoundsException
nullable getFirst: null, size=2
nullable removal: Removal[present=true, value=null], remaining=[tail]
nullable removeLast: tail
absent removal: Removal[present=false, value=null]
fixed bounds: left / right
fixed set changes array: [changed, right]
fixed removeFirst: UnsupportedOperationException
read-only last: south
read-only removeLast: UnsupportedOperationException
linked set bounds: z / m
linked set removeLast: m
linked set remains: [z, a]
sorted bounds: 40 / 10
sorted removed: 40 / 10, remaining=[30, 20]
reverse bounds: 4 / 1
reverse removed: 4 / 1
source and reverse: [2, 3] / [3, 2]
singleton taken: [only], remaining=[]
two ends taken: [1, 4], remaining=[2, 3]
deque empty getFirst: NoSuchElementException
deque empty peek/poll: null / null
deque drained: [W1, W2, W3], empty=true
~~~

### 9.1. Read Group and Removal Group

The first two lines show that inspecting first/last does not change the list. Afterward, the values returned from the two removals are `fetch` and `save`; the middle element `check` remains.

Notice how the program stores the removed values in variables before printing. This style makes the order of mutation clear, facilitates testing, and avoids reading a long expression with multiple side effects.

### 9.2. Empty Group and null Group

The five lines for the empty case distinguish boundary-operation exceptions from the index-access exception.

The two `Removal` objects share `value=null` but differ in `present`: the first case removed a valid element, while the second case had no element. The separate flag prevents callers from drawing the wrong conclusion from a `null` value.

### 9.3. Mutation Permissions and Ordering Semantics

The fixed-size list can be read and have elements replaced, but cannot have its first element removed. The read-only list can also have its last element read, but rejects removing the last element.

The linked set takes ends by insertion sequence; the descending sorted set takes ends according to its comparator. The reversed view removes from the source at the opposite end. These results illustrate that the method names are the same, while each source retains its own rules.

### 9.4. Singleton Group and Deque Loop

`takeEnds` checks again after the first removal. Consequently, a single element is not requested to be removed a second time. With four elements, the method returns both ends and keeps the middle.

The loop using `ArrayDeque.pollFirst` claims each job upon removal. The `null` termination condition relies on the chosen source’s policy of disallowing `null`; do not copy this pattern verbatim to a source that allows `null` without reviewing the contract.

## 10. Default Mechanism and Actual Cost

An interface provides a shared vocabulary; it does not unify every underlying algorithm.

At the `SequencedCollection` level, the default method obtains the first element via the iterator, and the last element via the iterator of the reversed view; removal retrieves the element and then uses the iterator’s remove operation. Sub-hierarchies like `List` and concrete classes may provide more suitable implementations.

For `ArrayList`, reading the two ends is no reason to replace a dynamic array with another structure. However, if you repeatedly remove from the front, the remaining elements must shift forward. With n elements, removing from the front until empty can require a total number of shifts equal to:

~~~text
(n - 1) + (n - 2) + ... + 1
= n * (n - 1) / 2
~~~

This is an analysis of the number of elements that must be shifted when using a dynamic array, not a timing measurement from a benchmark. The sum grows quadratically with n. Renaming `remove(0)` to `removeFirst()` does not eliminate that shifting work.

When business logic primarily adds/removes at both ends, a suitable `Deque` may be a better choice. When heavy index-based access is needed, an array-backed list still has its own advantages. Choose based on the actual set of operations, not merely because both have `removeFirst`.

A generic method accepting `SequencedCollection` must not promise that the four operations always run in constant time. To state performance guarantees, you must rely on the source’s documentation and constrain usage accordingly.

## 11. Applying This in Application Code

### 11.1. Reading Only Boundary Info: Keep Mutation Outside the Method

A summary method can accept `SequencedCollection<? extends E>` and only call read methods. It should still define its empty-collection policy and avoid promising that first/last represent a consistent snapshot if the data is changing concurrently.

Do not call `removeFirst` just because you want an element to display. That wrong choice can cause a “preview” UI to accidentally consume jobs.

### 11.2. Consuming Work: Use the Value Returned by the Removal Operation

If removal is permitted, process the element actually returned by `removeFirst` or `pollFirst`. Do not process a value from an earlier `getFirst` call and then remove a different element afterward.

You must also decide what happens when processing fails after removal: should the job be put back, written to a retry source, or saved under another status? The collection only performs the data operation; it does not automatically guarantee a transactional workflow or “exactly-once processing” for your business logic.

### 11.3. Two Ends Are Not Two Occurrences of the Same Value

With `[A, B, A]`, inspecting first and last both return the value `A`, yet those are two distinct positions. Removing first and then last succeeds twice, leaving `[B]`.

With `[A]`, there is only one position. A “take each boundary element once” policy must distinguish the two cases. Do not use `first.equals(last)` to guess that the collection has only one element, because two different positions can hold equal elements or even the same reference.

### 11.4. Do Not Confuse with Map Boundary APIs

`SequencedMap` uses `firstEntry`, `lastEntry`, `pollFirstEntry`, and `pollLastEntry` for key–value mappings. It is not a `SequencedCollection` of entries; do not call `map.getFirst()` by guessing from this lesson’s title.

The boundary entry methods of `SequencedMap` can return `null` when the map is empty, differing from the exception convention of the four collection methods covered here. [Java 21: SequencedMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html).

## 12. Common Mistakes and How to Spot Them

| Mistake | Consequence or symptom | Contract-based fix |
| --- | --- | --- |
| Using `getFirst` when intending to claim work | Element remains in the source | Use the appropriate removal operation |
| Using `removeLast` for previewing | Data is lost from the end | Use `getLast` |
| Assuming empty returns `null` | `NoSuchElementException` on mutable sources | Choose an empty policy or suitable API |
| Seeing a `null` result and concluding empty | Valid `null` element is missed | Separate presence state from value |
| Calling both-end removals unconditionally | Fails on 0- or 1-element inputs | Define and handle each case |
| Removing on `Arrays.asList` | `UnsupportedOperationException` | Use a source supporting removal or create a copy intentionally |
| Treating first as the smallest element for every set | Wrong result under insertion order or descending comparator | Read the source’s ordering rule |
| Removing from a reversed view expecting the source to stay unchanged | Source is modified at the opposite end | Recognize views and data ownership |
| Repeatedly removing from the front of a large `ArrayList` | Costly element shifting | Re-evaluate data structure for the workload |
| Checking empty then assuming the state is reserved | Bugs when another thread interleaves | Design synchronization or use an appropriate concurrent operation |

When encountering a bug, separate three questions: **which direction are you viewing from, does the source currently have elements, and is removal supported?** They are independent; fixing one question will not necessarily resolve the other two.

## 13. Practice with Answers

### Exercise 1 — Predict the State After Each Statement

An `ArrayList<Integer>` holds `[7, 8, 9]`. Call `getLast()`, `removeFirst()`, `getFirst()`, and `removeLast()` in sequence. What are the return values and the final data?

**Answer:** they return `9`, `7`, `8`, and `9` in sequence. After the first read, the list is unchanged. After the two removals, `[8]` remains.

### Exercise 2 — Single Element

A mutable list holds `[X]`. Can you write `List.of(items.removeFirst(), items.removeLast())` to take both ends?

**Answer:** inappropriate. The first removal empties the source, and the last removal throws an exception. The expression does not become an atomic operation or automatically roll back. Additionally, `List.of` does not accept `null`, so constructing the result that way imposes an extra constraint on the data. Define a 0/1/n-size policy and use a suitable result structure.

### Exercise 3 — null Value

The source is an `ArrayList<String>` containing a single `null` element. What does `removeFirst()` return, and how do you know it succeeded in removing?

**Answer:** it returns `null` and the source becomes empty. The return value itself does not mean “failure.” In an exclusive-access context, you can rely on the operation completing normally and an explicit presence result like the helper in this lesson. Do not use `Optional.ofNullable` if you need to preserve both states fully when the domain permits `null`.

### Exercise 4 — Read Permission and Resize Permission

Given `String[] a = {"L", "R"}` and `List<String> x = Arrays.asList(a)`. Why can `x.getFirst()` and `x.set(0, "N")` succeed while `x.removeFirst()` fails?

**Answer:** the array-backed list has a fixed size. Reading and replacing elements do not change the size; removing does. After `set`, the array also contains `"N"` at the first position. To remove in a structurally independent copy, you can create `new ArrayList<>(x)` and remove from the copy, if that matches the business intent.

### Exercise 5 — Descending Comparator

A `TreeSet<Integer>` using `Comparator.reverseOrder()` contains `2, 5, 1`. What do `getFirst()` and `removeLast()` return? What remains after the removal?

**Answer:** the sequence is `[5, 2, 1]`. `getFirst()` returns `5` and leaves the source unchanged. `removeLast()` returns `1`, leaving `[5, 2]`. “First” follows the comparator, not the usual smallest-value default.

### Exercise 6 — Removing from a Reversed View

The source is `[P, Q, R]`. Obtain the reversed view `v`, then call `v.removeLast()`. Which value is removed and what remains in the source?

**Answer:** the view is `[R, Q, P]`, so the view’s last element is `P`. The call removes `P` from the source, leaving `[Q, R]` in the source and `[R, Q]` in the view. This is an operation on a mutable view, not on a copy.

### Exercise 7 — Choosing an API for a Non-null Queue

A loop pulls jobs from an `ArrayDeque` and stops when there is no work. Should you use `isEmpty` followed by `removeFirst`, or a single `pollFirst` in the condition?

**Answer:** in a context suited for `ArrayDeque`, `pollFirst` directly expresses “take if available,” returning `null` when empty; the convention is unambiguous because the source forbids `null`. If multiple threads access it concurrently, you must switch to an appropriate structure or synchronization rather than assuming `ArrayDeque` is thread-safe. With a `LinkedList` containing `null`, the termination condition must be reconsidered.

### Exercise 8 — Verifying Contract and Performance

You replace a removal loop `list.remove(0)` with `list.removeFirst()` on a large `ArrayList`. Can you claim the algorithm has changed from quadratic to linear? What tests are still needed for the change?

**Answer:** no. The new API name does not eliminate element shifting when removing from the front of a dynamic array. You should re-evaluate the data structure for the workload. Behavioral tests must cover an empty source, a single element, multiple elements, `null` data if permitted, and a source that does not support removal if the method accepts that type; also review exception types if legacy code relied on `IndexOutOfBoundsException`.

After running the example, replace the input data to `takeEnds` with cases of 0, 1, 2, and 3 elements. Record the state after each removal and explain why the method cannot remove the same position twice when the source has only one element.
