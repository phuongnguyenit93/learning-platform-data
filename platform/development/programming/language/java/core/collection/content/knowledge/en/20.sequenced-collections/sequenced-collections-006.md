# SequencedSet and Repositioning Existing Elements

## 1. From a Set Without Duplicates to a Set with Positional Sequence

Suppose a screen is displaying selected steps in order:

~~~text
edit -> review -> publish
~~~

The user wants to pin `review` to the front. This requirement has two parts at the same time:

- `review` must still appear only once;
- its position in the sequence must change.

A list can change positions, but it does not automatically guarantee uniqueness. An ordinary set expresses uniqueness, but does not necessarily have an ordering contract. Since Java 21, `SequencedSet<E>` combines both aspects: **it is a set and has a well-defined encounter order**.

This interface extends both `Set<E>` and `SequencedCollection<E>`; its `reversed()` method returns a `SequencedSet<E>`. However, modification and positioning permissions still depend on the implementation. [Java 21: SequencedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedSet.html).

In this lesson, `LinkedHashSet` is the primary implementation for learning how to move existing elements to the front or back. We will clearly distinguish it from `TreeSet`, unmodifiable sets, and map key views. The complete program uses **Java 21 or later**, because `SequencedSet` and the positioning operations covered here belong to the API introduced in this version.

## 2. Three Questions to Separate

When calling an operation on a sequenced set, separate three questions:

1. **Membership:** does this element belong to the set?
2. **Sequence:** where does it currently stand in iteration order?
3. **Operation capability:** does the source allow imposing a position?

For example, with a `LinkedHashSet` currently holding `[edit, review, publish]`:

~~~text
membership:   edit, review, publish are all present
sequence:     edit before review, review before publish
new intent:   review at the front
~~~

After moving `review` to the front:

~~~text
sequence:     review -> edit -> publish
membership:   still the same three elements
size:         still 3
~~~

**Unchanged size does not mean unchanged state.** Sequence is data that can matter for UI, reports, or priority policies. A test that only checks the number of elements will miss the bug "received pin request but did not reposition".

Conversely, the mere fact that a type is ordered is not enough to prove repositioning capability. A sorted set determines positions by comparison; it cannot allow arbitrarily pinning any element to the front while keeping the same ordering rule.

## 3. LinkedHashSet: How add Differs from addFirst and addLast

`LinkedHashSet` maintains ordinary insertion order. Calling `add(e)` again when the element is already present does not change the order. Since Java 21, `addFirst(e)` and `addLast(e)` provide explicit positioning intent; if the element is already present, it is moved to the front or back as needed. [Java 21: LinkedHashSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashSet.html).

### 3.1. add: ensures membership, preserves the position of an existing element

Starting from `[A, B, C]`:

~~~java
boolean changed = items.add("B");
~~~

This is an illustrative snippet inside a method, where `items` is a modifiable `LinkedHashSet<String>`.

The result is `changed == false` and the sequence remains `[A, B, C]`. The method returns `false` because no new member was added. There is no automatic behavior like "B was just used, so B becomes the newest".

If you call `add("D")` with an absent element, the ordinary linked set appends it to the end, becoming `[A, B, C, D]` and returning `true`.

### 3.2. addFirst: adds if absent, moves to the front if present

Starting from `[A, B, C]`:

~~~text
addFirst(B)          [B, A, C]       size 3
~~~

`B` is not duplicated. The remaining elements keep their relative relationship with `A` before `C`.

If the argument is `D`, which is absent:

~~~text
[A, B, C]
addFirst(D)
[D, A, B, C]                        size 4
~~~

Therefore, `addFirst` is not a "move only if present" command. It is also a command to add a new element at the front when that element does not yet belong to the set.

### 3.3. addLast: adds if absent, moves to the end if present

Starting from `[A, B, C]`:

~~~text
addLast(A)           [B, C, A]       size 3
~~~

If the argument is absent, it is added at the end. If the element is already last, the resulting sequence does not change. Repeating `addLast("A")` on `[B, C, A]` still has the same three elements in the same sequence.

That is the logical outcome you can rely on. Do not infer further that every call at the exact front or back has the same internal details, never affects any iterator, or is completely free of cost.

### 3.4. Comparison table for a modifiable LinkedHashSet

| Operation | Absent argument | Present argument | Return value |
| --- | --- | --- | --- |
| `add(e)` | Adds to the end | Keeps current position | `boolean`, whether a new member was added |
| `addFirst(e)` | Adds to the front | Moves to the front if needed | `void` |
| `addLast(e)` | Adds to the end | Moves to the end if needed | `void` |

You cannot write `boolean moved = items.addFirst(e);`: the method returns `void`.

Also do not use a change in `size` to conclude whether repositioning occurred. An element in the middle can be moved to the front while `size` stays the same.

## 4. "Already Present" Relies on Equality, Not Just Reference Identity

For strings in a `LinkedHashSet`, two `String` objects with different references but equal content still represent the same member.

For example:

~~~java
var items = new java.util.LinkedHashSet<String>(
        java.util.List.of("A", "B", "C"));
boolean added = items.add(new String("B"));
items.addFirst(new String("B"));
~~~

This Java 21 illustrative snippet does not create an extra `B` member. The `add` call returns `false`; after the positioning call, the sequence is `[B, A, C]`.

`LinkedHashSet` belongs to the hash-based set family. You must implement `equals` and `hashCode` consistently for custom element types. Having the same hash code alone is not enough to make two elements equal; the hash code helps locate candidate buckets, while equality distinguishes values within a bucket. The basic operations of `HashSet` rely on a hash structure and have performance characteristics tied to hash code dispersion. [Java 21: HashSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HashSet.html).

For a business object with multiple fields, you must define what "the same element" means. If `equals` is based only on an identifier, a positioning call passing an object with the same ID does not mean the API has updated all descriptive fields of the stored object. **Repositioning and updating element data are two different responsibilities.** Do not use a positioning operation as a data-replacement API without defining the necessary contract.

### 4.1. Do not mutate equality keys while the element is in the set

If you mutate a field that affects `equals` or `hashCode` while the object is inside a hash-based set, lookups and subsequent positioning calls may no longer be reliable under the expected contract.

The `Set` documentation warns of undefined behavior when an object's value changes in a way that affects equality comparisons while it remains a member. [Java 21: Set](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Set.html).

An easily controllable option is to store an immutable identifier, such as a `String` or an immutable value type with proper equality. Changing a display label or processing status in another data source should not accidentally alter the identity of the element in the set.

### 4.2. null is also a repositionable member in LinkedHashSet

`LinkedHashSet` permits `null`. If it currently holds `[left, right]`:

~~~text
addFirst(null)       [null, left, right]       size 3
addLast(null)        [left, right, null]       size 3
add(null)            unchanged                 returns false
~~~

There is no "second null" after repositioning. However, this is a capability of a source that permits `null`, not a right to be assumed for every `SequencedSet`.

For task IDs or document IDs, business rules often forbid `null` to avoid confusion in display and processing. If forbidden, validate before modifying data. `Objects.requireNonNull` is one way to express that precondition; it does not replace designing the domain meaning of the data. [Java 21: Objects](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Objects.html#requireNonNull(T,java.lang.String)).

## 5. Add-or-Move Differs from Moving Only Existing Elements

A "pin to top" button on a panel that only shows already-selected items may not be allowed to introduce unknown IDs into the panel. In that case, calling `addFirst` directly is too broad.

The following helper moves only if already present:

~~~java
static <E> boolean moveExistingFirst(
        java.util.SequencedSet<E> items, E value) {
    if (!items.contains(value)) {
        return false;
    }
    items.addFirst(value);
    return true;
}
~~~

This is a Java 21 method snippet that must be placed inside a class; the complete program below shows its usage.

The helper's contract must clearly state:

- the source supports positioning when that branch is executed;
- there are no concurrent modifications during the check and the subsequent operation;
- `true` means the element was present and the positioning call completed; it does **not** promise that the element was previously at a different position;
- `false` means it was not found, so the helper did not add the element.

If the element is already at the front, the helper still returns `true`. To report specifically "whether the order changed", you need to design a different result and compare with the current front using appropriate equality. Do not name a flag `wasInserted` or `orderChanged` if it only indicates presence.

In a multithreaded system, another thread could remove the element after `contains`, and then `addFirst` would add it back. These two calls do not form an atomic transaction. You must synchronize the entire operation if the rule "move only existing elements" must hold under all interleavings.

### 5.1. Why not use remove followed by add as an unconditional replacement?

Legacy code might do:

~~~java
items.remove(value);
items.add(value);
~~~

With a modifiable linked set and suitable conditions, this can move an element to the end. However, the intent is split into two mutations, creating a moment when the element does not belong to the set; if another object with equivalent equality is used, removing and adding can also replace the stored representative object.

Moreover, a generic set does not necessarily preserve insertion order and does not necessarily support both operations. Do not turn a `remove + add` sequence into a "workaround" when `addLast` throws `UnsupportedOperationException` on a source that disallows positioning. First, choose the right data model.

`addLast` directly expresses the add-or-move-to-end intent on `LinkedHashSet`. It still does not make the surrounding business workflow atomic or thread-safe.

### 5.2. Do not use contains to automatically record accesses

`contains(e)` is a membership query. On an ordinary `LinkedHashSet`, it does not automatically push `e` to the front or back like a "recently used" policy.

If you want to track usage, you must call the positioning operation when the business event actually occurs. You must also agree on which end represents the most recent; different places choosing opposite ends will produce contradictory results even though each individual call is valid.

## 6. The reversed View Inverts the Meaning of Front and Back

`reversed()` returns a view with the opposite encounter direction. With `LinkedHashSet`, allowed modifications through the view propagate to the source, and changes to the source are also visible through the view.

Example initial source:

~~~text
source:        [A, B, C, D]
reverse view:  [D, C, B, A]
~~~

Calling `view.addFirst("B")` means moving `B` to the **front of the view**. The front of the view is the back in the source's direction:

~~~text
source after:  [A, C, D, B]
view after:    [B, D, C, A]
~~~

Then calling `view.addLast("D")` moves `D` to the back of the view, which corresponds to the front of the source:

~~~text
source after:  [D, A, C, B]
view after:    [B, C, A, D]
~~~

In the OpenJDK 21 source code, the reverse view of `LinkedHashSet` implements `addFirst` via the source's `addLast` and vice versa. This is a concrete implementation consistent with the reversed semantics of the view. [OpenJDK 21: LinkedHashSet.java](https://raw.githubusercontent.com/openjdk/jdk/jdk-21%2B35/src/java.base/share/classes/java/util/LinkedHashSet.java).

There are two common points of confusion:

1. Creating a view does not copy all members into an independent set.
2. "Move to front" must always be tied to **the direction currently used to view the data**.

If you need the original order preserved, create a suitable copy first and reposition on the copy. If the UI only needs to display newest-first while the source stores newest-last, you can read the reverse view without moving every element in the source.

Do not assume that ordinary `add` is always equivalent to `addLast` on every view. When the intent is a specific end, use `addFirst` or `addLast` and read the source's contract.

## 7. Moving Multiple Elements to the Front: Loop Order Matters

Start with `[A, B, C, D]`. The user selects the priority order `[B, D]` and wants them to appear first in that exact order.

If you iterate forward over the request and call `addFirst`:

~~~text
initial                    [A, B, C, D]
move B to front            [B, A, C, D]
move D to front            [D, B, A, C]
~~~

The priority group's order is reversed. The last call takes the front.

To get `[B, D, A, C]`, process the request in reverse order:

~~~java
for (String id : requested.reversed()) {
    selected.addFirst(id);
}
~~~

This Java 21 illustrative snippet assumes `requested` is a separate `List<String>`, `selected` is a modifiable `LinkedHashSet<String>`, and the requested IDs have no duplicates. `List.reversed()` provides the reverse traversal of the request list. [Java 21: List](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#reversed()).

After both operations, members outside the priority group preserve their relative order `A` before `C`.

### 7.1. Define a policy for duplicate or missing requests

If the request is `[B, D, B]`, saying "preserve request order" is not clear enough: a set cannot display `B` twice. You must choose whether to keep the first occurrence, the last occurrence, or reject duplicate input, and then normalize the input before positioning.

If the request contains an ID not yet in the source, `addFirst` will add that ID. To move only existing members, use the corresponding check policy under appropriate access control.

Do not let a loop accidentally define a policy that the product has not decided. Test duplicate IDs, unknown IDs, and empty groups separately.

### 7.2. Do not iterate the same source while arbitrarily relinking

A `for (E e : selected)` loop uses the source's iterator. Actually changing an element's position can invalidate the iterator even though the number of members remains unchanged.

The standard approach is to separate decision from update:

~~~java
java.util.List<String> toPin = new java.util.ArrayList<>();
for (String id : selected) {
    if (id.startsWith("urgent-")) {
        toPin.add(id);
    }
}
for (String id : toPin.reversed()) {
    selected.addFirst(id);
}
~~~

This is a Java 21 illustrative snippet inside a method, intended for a context without concurrent modifications. The first loop collects decisions without modifying the source; the second loop iterates over the separate list.

Iterators in general do not allow arbitrary structural modification of the source during traversal, except through mechanisms defined by the iterator or implementation. `Iterator.remove` grants permission to remove the last returned element, not an API to move it to the front or back. [Java 21: Iterator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Iterator.html#remove()).

## 8. Underlying Mechanism: Uniqueness and Sequence Work Together

You can picture `LinkedHashSet` from two perspectives:

~~~text
member lookup:      hash of value -> locate matching element

sequence traversal: head <-> A <-> B <-> C <-> tail
~~~

When moving `B` to the front, the logical model unlinks `B` from the middle and links it before `A`:

~~~text
before:             A <-> B <-> C
after:              B <-> A <-> C
~~~

The member lookup recognizes that `B` is already present; the linking maintains the traversal order. There is no need to create a new `B` member just because its position changed.

In OpenJDK 21, this set uses `LinkedHashMap` as its backing structure. The `LinkedHashMap` source has a branch that moves an existing node to the head or tail, updating the links and the modification count when the node actually moves. This explains the mechanism of that implementation, not a mandatory algorithm for every `SequencedSet`. [OpenJDK 21: LinkedHashMap.java](https://raw.githubusercontent.com/openjdk/jdk/jdk-21%2B35/src/java.base/share/classes/java/util/LinkedHashMap.java).

### 8.1. Why size is not enough to guarantee iterator validity

An iterator tracks progress through the sequence traversal. A node moving from the middle to the front can alter the traversal path even when the node count is unchanged. Therefore, "not adding or removing members" is not a valid justification for arbitrarily repositioning while an old iterator is in use.

Fail-fast modification detection is a bug-finding aid, not a synchronization tool or a business protocol. Do not rely on whether `ConcurrentModificationException` is thrown or not to decide whether a program is correct.

### 8.2. Performance does not come from the interface name

Good hashing and updating a few links can allow positioning operations on a linked implementation to avoid copying the entire sequence. However, cost still depends on hashing, equality, collisions, and the implementation.

A `SequencedSet<E>` parameter does not promise that every operation has the same time complexity or the same modification permissions. If performance and positioning capability are requirements of an API, state the specific requirements and measure with realistic workloads. Do not just rename a variable from `Set` to `SequencedSet` and claim performance has improved.

## 9. Sources That Are SequencedSet but Disallow Arbitrary Repositioning

### 9.1. TreeSet and SortedSet preserve order determined by comparison

A natural-order `TreeSet` containing `[A, B, C]` must preserve its comparison rule. `addFirst("B")` is not allowed to place `B` before `A`. `SortedSet.addFirst` and `addLast` throw `UnsupportedOperationException` because explicit positioning conflicts with the ordering rule.

Even calling `addFirst("A")` when `A` is already at the front is still not a supported usage. Use `add` to insert members, while position is determined by comparison. [Java 21: SortedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedSet.html#addFirst(E)).

If the requirement is "pin any arbitrary item to the front", sorting everything with a fixed comparator may no longer be the right model. You may need a separate priority sequence or a comparator that accurately reflects the policy; do not catch the exception, ignore it, and still report that pinning succeeded.

### 9.2. Unmodifiable wrappers

`Collections.unmodifiableSequencedSet(source)` preserves sequence reading in both directions, but rejects modifications through the view. A positioning call is rejected even if the argument already belongs to the source.

This wrapper is still a view; if the source is modified through another path, querying the view reflects the source. It does not create a fixed snapshot. [Java 21: Collections.unmodifiableSequencedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html#unmodifiableSequencedSet(java.util.SequencedSet)).

To keep a structurally independent copy of the data at the current moment, you can create `new LinkedHashSet<>(source)` first. That is a shallow copy: if elements have mutable state, the structures may still share references to them.

### 9.3. Map key views

`SequencedMap.sequencedKeySet()` returns a `SequencedSet<K>`, but it should not be understood as an independent set with full positioning permissions.

For example, the key view of `LinkedHashMap` does not support `addFirst` or `addLast`. If you need to position entries in a map, use the appropriate map API and provide the associated value, rather than treating the key view as a shortcut. [Java 21: LinkedHashMap, sequenced views](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html#sequencedKeySet()).

This shows that looking only at the `SequencedSet` type is not enough to promise that a pinning helper works on every input. Modification permission is part of the contract that the producer and consumer of the data must agree upon.

## 10. Repositioning Does Not Change the equals and hashCode Contract of Set

Two sets with the same members can still be `equals` even if their encounter orders differ. Adding a sequenced interface does not turn set equality into positional equality.

For example:

~~~text
x:    [A, B, C]
y:    [C, A, B]

x.equals(y)                      true
same encounter order?            false
~~~

If a test for a pinning feature only uses `expectedSet.equals(actualSet)`, it can pass even when the feature fails to change the order as required. You must compare a sequence, for example:

~~~java
java.util.List<String> actualOrder = new java.util.ArrayList<>(actual);
if (!actualOrder.equals(java.util.List.of("B", "A", "C"))) {
    throw new AssertionError("unexpected order: " + actualOrder);
}
~~~

This is a Java 21 verification snippet inside a method, assuming `actual` is a source not undergoing concurrent modification. Choosing a list for verification is intentional because `List.equals` checks positions.

In the complete program, the source and the reverse view have `equals == true`, as well as equal `hashCode`. Those two lines confirm the `Set` contract; they do not negate the fact that the reverse view reads in a different order.

## 11. Complete Program: Existing Elements, Views, Priority Groups, and Recent History

Save all of the following code to **`SetRepositionDemo.java`**. The program runs single-threaded, uses immutable strings, and keeps data update responsibilities inside the helpers.

The `touchRecent` helper illustrates an application policy: most recently used at the end, `null` IDs disallowed, and at most a fixed number of IDs retained. This is a sample algorithm for an ID history, not a complete cache or a concurrency mechanism.

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.SequencedSet;
import java.util.TreeSet;

public class SetRepositionDemo {
    // Requires supported positioning and exclusive access for the whole method.
    // true means the element was present, not necessarily that its order changed.
    static <E> boolean moveExistingFirst(SequencedSet<E> items, E value) {
        if (!items.contains(value)) {
            return false;
        }
        items.addFirst(value);
        return true;
    }

    // Application policy: newest at the end, no null IDs, positive capacity.
    // Requires exclusive access for the entire update.
    static void touchRecent(LinkedHashSet<String> recent, String id, int limit) {
        if (limit < 1) {
            throw new IllegalArgumentException("limit must be positive");
        }
        Objects.requireNonNull(id, "id");
        recent.addLast(id);
        while (recent.size() > limit) {
            recent.removeFirst();
        }
    }

    static String unsupported(Runnable action) {
        try {
            action.run();
            return "no exception";
        } catch (UnsupportedOperationException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        LinkedHashSet<String> steps =
                new LinkedHashSet<>(List.of("edit", "review", "publish"));
        System.out.println("initial: " + steps);
        boolean added = steps.add(new String("review"));
        System.out.println("ordinary add existing: " + added + ", order=" + steps);

        steps.addFirst("review");
        System.out.println("first existing: " + steps + ", size=" + steps.size());
        steps.addLast("edit");
        System.out.println("last existing: " + steps + ", size=" + steps.size());
        steps.addFirst("draft");
        System.out.println("first missing: " + steps + ", size=" + steps.size());
        steps.addLast("draft");
        System.out.println("last draft: " + steps + ", size=" + steps.size());
        steps.addLast("draft");
        System.out.println("last draft again: " + steps + ", size=" + steps.size());

        boolean foundMissing = moveExistingFirst(steps, "missing");
        System.out.println("move missing: " + foundMissing + ", order=" + steps);
        boolean foundPublish = moveExistingFirst(steps, "publish");
        System.out.println("move publish: " + foundPublish + ", order=" + steps);
        System.out.println("set equals reverse: " + steps.equals(steps.reversed()));
        System.out.println("hash equals reverse: "
                + (steps.hashCode() == steps.reversed().hashCode()));

        SequencedSet<String> readOnly =
                Collections.unmodifiableSequencedSet(steps);
        LinkedHashSet<String> saved = new LinkedHashSet<>(steps);
        System.out.println("read-only reposition: "
                + unsupported(() -> readOnly.addFirst("edit")));
        steps.addFirst("edit");
        System.out.println("read-only sees source: " + readOnly);
        System.out.println("saved copy stays: " + saved);

        LinkedHashSet<String> base =
                new LinkedHashSet<>(List.of("A", "B", "C", "D"));
        SequencedSet<String> reverse = base.reversed();
        reverse.addFirst("B");
        System.out.println("reverse first B, base: " + base);
        System.out.println("reverse first B, view: " + reverse);
        reverse.addLast("D");
        System.out.println("reverse last D, base: " + base);
        System.out.println("reverse last D, view: " + reverse);

        List<String> requested = List.of("B", "D");
        LinkedHashSet<String> forwardBatch =
                new LinkedHashSet<>(List.of("A", "B", "C", "D"));
        for (String id : requested) {
            forwardBatch.addFirst(id);
        }
        LinkedHashSet<String> preservedBatch =
                new LinkedHashSet<>(List.of("A", "B", "C", "D"));
        for (String id : requested.reversed()) {
            preservedBatch.addFirst(id);
        }
        System.out.println("batch forward input: " + forwardBatch);
        System.out.println("batch preserve input: " + preservedBatch);

        LinkedHashSet<String> nullable =
                new LinkedHashSet<>(List.of("left", "right"));
        nullable.addFirst(null);
        nullable.addLast(null);
        boolean duplicateNull = nullable.add(null);
        System.out.println("null moved: " + nullable + ", size=" + nullable.size()
                + ", ordinary add=" + duplicateNull);

        SequencedSet<String> sorted =
                new TreeSet<>(List.of("A", "B", "C"));
        System.out.println("sorted first existing A: "
                + unsupported(() -> sorted.addFirst("A")));
        System.out.println("sorted last existing C: "
                + unsupported(() -> sorted.addLast("C")));

        LinkedHashMap<String, Integer> counts = new LinkedHashMap<>();
        counts.put("A", 1);
        counts.put("B", 2);
        SequencedSet<String> keys = counts.sequencedKeySet();
        System.out.println("map key view reposition: "
                + unsupported(() -> keys.addFirst("B")));

        LinkedHashSet<String> recent =
                new LinkedHashSet<>(List.of("r1", "r2", "r3"));
        touchRecent(recent, "r1", 3);
        System.out.println("touch existing: " + recent);
        touchRecent(recent, "r4", 3);
        System.out.println("touch new and trim: " + recent);
        System.out.println("newest first display: " + recent.reversed());
    }
}
~~~

Use JDK 21 or later to compile and Java 21 or later to run:

~~~shell
javac --release 21 -encoding UTF-8 SetRepositionDemo.java
java SetRepositionDemo
~~~

No `--enable-preview` is needed. The example was compiled with release level 21 and ran successfully on OpenJDK 24.0.2. The stdout lines use ASCII strings so the output does not depend on terminal diacritic rendering.

Exact stdout:

~~~text
initial: [edit, review, publish]
ordinary add existing: false, order=[edit, review, publish]
first existing: [review, edit, publish], size=3
last existing: [review, publish, edit], size=3
first missing: [draft, review, publish, edit], size=4
last draft: [review, publish, edit, draft], size=4
last draft again: [review, publish, edit, draft], size=4
move missing: false, order=[review, publish, edit, draft]
move publish: true, order=[publish, review, edit, draft]
set equals reverse: true
hash equals reverse: true
read-only reposition: UnsupportedOperationException
read-only sees source: [edit, publish, review, draft]
saved copy stays: [publish, review, edit, draft]
reverse first B, base: [A, C, D, B]
reverse first B, view: [B, D, C, A]
reverse last D, base: [D, A, C, B]
reverse last D, view: [B, C, A, D]
batch forward input: [D, B, A, C]
batch preserve input: [B, D, A, C]
null moved: [left, right, null], size=3, ordinary add=false
sorted first existing A: UnsupportedOperationException
sorted last existing C: UnsupportedOperationException
map key view reposition: UnsupportedOperationException
touch existing: [r2, r3, r1]
touch new and trim: [r3, r1, r4]
newest first display: [r4, r1, r3]
~~~

### 11.1. Operations on steps

`new String("review")` creates a string object with a different reference but equal content. `add` neither creates a second member nor changes the position.

`addFirst("review")` moves the existing step to the front, and `addLast("edit")` moves the existing step to the back. The size stays 3. Only when adding the absent `draft` does the size increase to 4.

Calling `addLast("draft")` again keeps the same sequence. The move-only-existing helper does not add `missing`, while `publish` is moved successfully.

### 11.2. Read-only view and copy

The read-only view rejects the positioning call, and then sees the change made through the original source. The `saved` copy keeps the order copied prior to that change.

These are two different choices regarding data lifecycle: sharing a view of the source or keeping a separate structure. Do not call both "an immutable copy" without specifying the required guarantees.

### 11.3. Both directions and batch updates

The four lines on the reverse view allow direct comparison between the front of the view and the back of the source, and vice versa.

The two batch-update lines use the same initial data but different request traversal directions. Read them alongside the intermediate table in Section 7 to see why repeated `addFirst` calls reverse the processing order.

### 11.4. Sources that reject positioning and recent history policy

`TreeSet` rejects both calls even for elements already at the exact boundary. The map key view also rejects positioning, even though its type is `SequencedSet`.

In the recent history, reusing `r1` moves this ID to the end without increasing the member count. Adding `r4` creates a new member and then evicts the oldest head `r2`, leaving `[r3, r1, r4]` in the source. The reverse view displays newest first.

`LinkedHashMap` has a separate access-order mode for mappings, but here the set does not track accesses automatically; the helper itself receives usage events and explicitly repositions. If you need to store additional data per ID and a caching policy, design further on an appropriate model rather than assuming this set example solves the entire requirement.

## 12. Safe Usage in Applications

### 12.1. Name the policy after its meaning

Choose and document a clear convention such as "highest priority at the front" or "most recently used at the end". From that, derive whether to call `addFirst` or `addLast` on each event.

If you must support both user-customized order and recent access time, a single sequence may not be enough to express two independent relationships. You need two order sources or additional data, rather than letting pinning accidentally destroy access history.

### 12.2. Validate before reordering

Suppose a request contains an ID that does not exist in the business data store. If an API is only allowed to move already-selected items, verify that condition before calling an operation that could add elements.

For multi-item updates, validating the entire request upfront can prevent a data error on the third item after the first two have already been moved. However, validating first and then issuing multiple mutating calls does not automatically provide rollback; if you need "all or nothing", design a new state transition, lock, or appropriate transaction at the owning layer.

### 12.3. Synchronize the entire business unit when shared

`LinkedHashSet` is not synchronized. A positioning call, a `contains` check followed by positioning, or positioning followed by size trimming can all be parts of a larger business unit.

If external locking is used, all related readers and writers must follow the same discipline, and the lock must cover the entire sequence consistently. Wrapping with an API that returns `Set` may also remove direct access to `SequencedSet` methods in the signature; do not cast arbitrarily to regain capabilities not promised by the wrapper.

Fail-fast does not replace locking, and seeing no exception does not prove there is no data race. The examples in this lesson keep a single-threaded context to verify sequence without interleaving.

### 12.4. Persist and transmit sequences in a format that preserves them

If pinned order is business data, choose a representation with an explicit sequence when exporting or saving. Comparing only membership before and after can miss changes that need to be saved.

Similarly, do not convert through `HashSet` or `Set.copyOf` and assume the chosen display order is preserved. An ordinary immutable set does not automatically become a sequenced contract. If you need a read-only sequenced output, choose `unmodifiableSequencedSet` over a source with an appropriate lifecycle and ownership.

## 13. Common Mistakes

| Misconception or code pattern | Problem | Fix |
| --- | --- | --- |
| Calling `add(e)` to mark `e` as most recently used | Existing element does not move automatically in `LinkedHashSet` | Use positioning operations according to policy |
| Calling `addFirst` with an unknown ID in a "pin selected items only" feature | May add a new member | Validate and define the add/move contract |
| Assigning the result of `addFirst` to `boolean` | Wrong return type (`void`) | Produce a separate business result if needed |
| Using `size` to detect all changes | Misses order changes | Verify the sequence |
| Assuming every `SequencedSet` supports repositioning | `SortedSet`/read-only views may reject it | Specify the required positioning capability |
| Catching a positioning exception and falling back to remove/add | Can break ordering rules or swap the stored object | Choose the right structure and intent |
| Iterating a source and moving elements inside the same loop | Iterator may become invalid | Collect first, update afterward |
| Iterating a group forward with `addFirst` and expecting to keep group order | The group order is reversed | Choose the appropriate traversal direction |
| Using set `equals` to test ordering | Test can pass even when order is wrong | Compare the sequence using a list |
| Mutating fields used in `equals`/`hashCode` while the element is in the set | Lookup/positioning breaks assumptions | Use immutable identity or a proper update workflow |

## 14. Practice Exercises with Answers

### Exercise 1 — Same elements, different operations

The `LinkedHashSet` source is `[A, B, C]`. Call `add("B")`, `addFirst("C")`, and `addLast("A")` in sequence. What are the final sequence and size?

**Answer:** `add("B")` returns `false`, and the source remains `[A, B, C]`. After `addFirst("C")`, it is `[C, A, B]`. After `addLast("A")`, it is `[C, B, A]`. The size stays 3 because no new member was added.

### Exercise 2 — Move only if present

The source is `[A, B]`. Requirement: "move X to the front if X is currently selected; if not present, do nothing." Why does calling `addFirst("X")` directly violate the requirement?

**Answer:** the add-or-position operation will insert `X` into the source, resulting in `[X, A, B]`. You need a helper with a move-only-if-present policy, with consistent positioning capability and access control. If multiple threads are involved, the check and the positioning operation must be handled within an appropriate synchronization unit.

### Exercise 3 — Two equal objects

A string set contains `"B"`. You call `addFirst(new String("B"))`. Will there be two `B` members because the references differ?

**Answer:** no. Uniqueness is based on proper element equality, not just `==`. The new string is equal in content to the existing member. However, do not interpret a positioning call as an API that updates all attributes of a business object that happens to be equal by ID.

### Exercise 4 — Front of the reverse view

The source is `[A, B, C]`, so the reverse view is `[C, B, A]`. Call `view.addFirst("A")` and then `view.addLast("B")` on the view of a modifiable `LinkedHashSet`. What are the final source and view?

**Answer:** the first call moves `A` to the back of the source: source `[B, C, A]`, view `[A, C, B]`. The second call moves `B` to the front of the source; since `B` is already at the front, the sequence stays unchanged. The final result remains source `[B, C, A]` and view `[A, C, B]`.

### Exercise 5 — Ordered priority group

The source is `[A, B, C, D, E]`. You want the group `[C, E]` at the front in that exact order. Describe the sequence of `addFirst` calls.

**Answer:** process `E` first, then `C`. After the first call: `[E, A, B, C, D]`; after the second: `[C, E, A, B, D]`. If you process `C` first and then `E`, the leading group becomes `[E, C]`. This assumes no duplicates in the request and that all IDs are already present; other policies must be defined separately.

### Exercise 6 — Missed pinning test

A test creates two sets with the same members but different orders and checks `equals`. It passes. Does this prove the pinning feature is correct?

**Answer:** no. `Set.equals` ignores encounter order. Collect the sequence into a list and compare it against the expected sequence; also check the member count and exact members if those are separate requirements. Do not use a set's `hashCode` as a signal of order changes.

### Exercise 7 — Already at the front, yet still rejected

`SequencedSet<String> x` is actually a `TreeSet` containing `[A, B, C]`. Why can `x.addFirst("A")` still throw `UnsupportedOperationException` even though `A` is already at the front?

**Answer:** explicit positioning is not supported on a sorted set; position is determined by comparison. The current state does not grant extra permission for that API. Use `add` to insert members, or change the model if arbitrary pinning is required; do not catch the exception and report success.

### Exercise 8 — Bounded recent history

Keep at most 3 IDs, oldest at the front and newest at the back. Initial source is `[p1, p2, p3]`. Reuse `p2`, then use a new ID `p4`. What should the result be, and what should be tested besides the element count?

**Answer:** after reusing `p2`, the sequence is `[p1, p3, p2]`. Adding `p4` and evicting the oldest head gives `[p3, p2, p4]`. You should check the sequence, uniqueness, and that the exact right ID was evicted. You must also define the `null` policy, valid capacity, error handling, and synchronization of the entire update if shared across threads.

Add a self-check with an element already at the exact front or back, an empty request group, and an absent ID. Before running, write down which operations only move and which are allowed to add. When you can predict both membership and sequence after every call, you have grasped the exact meaning of repositioning in a sequenced set.
