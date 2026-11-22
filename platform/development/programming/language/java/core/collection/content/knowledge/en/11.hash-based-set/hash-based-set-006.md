# Reinserting Existing Elements and LinkedHashSet Order

## 1. The Problem to Solve: Which Order to Keep When Data Appears Multiple Times?

Suppose a program records workflow stages in the order `draft → review → done`. Another `review` event arrives. You want to deduplicate them, but should the resulting order be `draft → review → done` or `draft → done → review`?

These two outcomes serve two different requirements. The first preserves the position of the initial record while the element remains in the set. The second reflects a more recent occurrence. Knowing only that "a set does not contain duplicate elements" is not enough to distinguish between them.

`LinkedHashSet` is suitable when you need a duplicate-free collection with a deterministic iteration order. With the regular `add` method, adding an element that is already present **does not move that element to the end**. The call returns `false` and the existing position is preserved. Removing an element and then adding it again is a different sequence of operations: the element actually leaves the set, and is then newly added at the end.

This lesson focuses on that boundary: duplicate `add`, remove-then-add, batch addition, and equivalent objects. The main examples use only APIs available in Java 17. The final part separately notes positioning methods introduced in Java 21 so that the rules of `add` are not mistakenly applied to every method.

You should know how to declare variables, call methods, use `List`, and write loops. Concepts such as `equals`, `hashCode`, iteration order, and the meaning of return values will be revisited in place.

## 2. Three Questions to Separate

When facing a call to `set.add(element)`, ask these questions in order:

1. Before the call, did the set already contain an equivalent element?
2. After the call, did the set gain a new member?
3. How does the iteration order of members change?

The first question determines whether this is a new insertion or a duplicate insertion. The second is reflected by the returned `boolean` value. The third relates to the ordering contract of the specific implementation.

Key terms:

| Term | Meaning in this lesson |
| --- | --- |
| Member | An element currently belonging to the set |
| Equivalent elements | Two objects considered to have the same value under the set's equality rules |
| Iteration order | The sequence in which elements are received via an `iterator` or a `for-each` loop |
| Insertion order | The order of successful new insertions, taking into account elements that have been removed |
| Representative object | The actual object currently stored for a value in the set |
| Access order | Order based on recent usage; different from preserving position on new insertion |

One set can have the same members as another set while iterating in a different order. A newly created object can also be equivalent to an existing object. Therefore, do not infer order from element count, and do not infer "new to the set" from the `new` operator.

## 3. The Rules of add in LinkedHashSet

For data with valid `equals/hashCode` rules that are not mutated incorrectly while stored, the behavior of `add` can be read as follows:

| Before `add(e)` | Return value | Element count | Iteration order |
| --- | --- | --- | --- |
| No element equivalent to `e` | `true` | Increases by one | `e` is added at the end |
| Already has an element equivalent to `e` | `false` | Unchanged | Existing position is preserved |

The `LinkedHashSet` documentation explicitly specifies that re-inserting an element already present does not affect insertion order. This is an API contract, not an accidental result of a single run. [Java 17: LinkedHashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html).

The illustration below assumes `java.util.LinkedHashSet` and `java.util.List` have been imported:

~~~java
LinkedHashSet<String> stages =
        new LinkedHashSet<>(List.of("draft", "review", "done"));

boolean changed = stages.add("review");
System.out.println(changed);
System.out.println(stages);
~~~

Output:

~~~text
false
[draft, review, done]
~~~

There is no new position for `review`. Nor is there a second `review` hidden at the end. The set still contains exactly three elements.

`false` does not mean "the element is absent after the call." In the example, `review` was already present before and remains present after the call. It indicates that the `add` call did not cause the set to gain a new member. Do not use `if (!set.add(x))` as evidence that `x` was lost.

With `contains("draft")`, the program only queries presence. The call does not move `draft` behind the other elements. Thus, neither seeing a value again via `add` nor checking it via `contains` turns the set into a "recently used" list.

## 4. Why Does a Hash Table Still Come with Insertion Order?

The name `LinkedHashSet` indicates two cooperating roles:

- The hash part supports looking up whether a value is already present.
- The links between elements support iterating in the maintained order.

You can visualize the current data with a simple diagram:

~~~text
Members by equality rules: {draft, review, done}

Chain for iteration:
head → draft ⇄ review ⇄ done ← tail
~~~

The diagram does not depict physical memory locations or hash table bucket counts. It helps separate membership lookup from operations that alter the order chain.

When a new value is added, the set creates a new membership and links it to the end of the chain. When a value already exists, there is no need to create a second member to append. Finding an existing member does not inherently mean "move this member to the end."

In OpenJDK 17, `HashSet` has a backing map to store elements; `LinkedHashSet` uses a variant backed by an insertion-ordered `LinkedHashMap`. Set elements are stored as keys. Therefore, duplicate-add behavior corresponds to finding an existing key, not removing and recreating the key. This is an implementation description that helps explain the outcome; applications should still rely on the API contract. [HashSet Source Code, OpenJDK 17](https://github.com/openjdk/jdk/blob/jdk-17%2B35/src/java.base/share/classes/java/util/HashSet.java).

You do not need to know the hash bucket selection formula to predict the `draft/review/done` example. `LinkedHashSet`'s insertion order is guaranteed at the API level. Table resizing or hash collisions are not reasons for an application to accept arbitrary iteration order.

## 5. Removing and Re-adding Creates a New Position

Compare two operation sequences starting from `[draft, review, done]`.

Case A:

~~~text
add(review) → false
result      → [draft, review, done]
~~~

Case B:

~~~text
remove(review) → true
state          → [draft, done]
add(review)    → true
result         → [draft, done, review]
~~~

In Case B, when `add` is called, the set no longer has `review`. That call is a new insertion for the current state, even though the program previously held the same value.

The understanding of "first-seen order" needs this boundary. `LinkedHashSet` does not permanently store the historical positions of removed elements. If you remove `review` and add it back, the set does not automatically place it back between `draft` and `done`.

You also need to check the result of `remove`. If you remove an element that is not present, `remove` returns `false`. Then `add` may create a new member, increasing the size. For example, starting from `[draft, done]`, executing `remove("archive")` followed by `add("archive")` yields `[draft, done, archive]`. That is no longer "only moving an existing element."

If `clear` is called, all members are removed from the set. Subsequent `add` calls establish a new order based on the incoming data, without restoring the order from before `clear`.

In business requirements, clearly choose one of two intents:

- "If already present, keep its position": only `add` is needed.
- "If currently present, move to the end": you need a positioning operation appropriate for your Java version, or an explicitly designed remove/add procedure.

## 6. addAll Does Not Move Existing Elements to the End

Suppose the current state is:

~~~text
[draft, review, done]
~~~

The next batch has the order:

~~~text
[review, publish, draft, archive]
~~~

In this batch, `review` and `draft` are already present. They keep their old positions. `publish` and `archive` are not present yet, so they are appended in the order they are encountered in the batch:

~~~text
[draft, review, done, publish, archive]
~~~

`addAll` returns `true` because there is at least one new member. That value does not mean "every element in the batch was new" or "the set was reordered to match the input batch." The `addAll` implementation inherited from `AbstractCollection` iterates over the source and calls `add` for each element. [Java 17: AbstractCollection.addAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractCollection.html#addAll(java.util.Collection)).

If the entire batch consists only of elements already present, the set gains no new members and the order remains unchanged. There is no mechanism to refresh positions on every duplicate encounter.

However, you must know the source's order. `List.of("review", "publish", "draft", "archive")` provides a definite sequence. If the source is a `HashSet`, the source's iteration order is not guaranteed. Copying into a `LinkedHashSet` only records the sequence that the source happens to provide during that iteration; it does not recover lost original insertion order.

With an ordered source, you can explain the result by crossing out values already in the target set, then appending the new values to the end in source order. When the same new value repeats within the batch, only the first successful new insertion creates a position.

## 7. Different References Can Still Be a Duplicate Insertion

For hash-based sets, element identification requires consistent `equals` and `hashCode` rules. If two objects are considered equal, they must have the same hash code. Two objects with the same hash code are not necessarily equal.

Consider a ticket with `number` and `note`. Suppose business rules treat the ticket number as its identity: two tickets with the same `number` are the same element to the set, regardless of `note`. The complete program below explicitly defines `Ticket`'s `equals` and `hashCode` using only `number`. This is an explicit choice; `record Ticket(int number, String note)` by default compares both components unless overridden.

We have two objects:

~~~text
original    = #10:old
replacement = #10:new
~~~

They are two different references, yet `original.equals(replacement)` is `true`. When the set already contains `original` and receives `add(replacement)`, there is no new member. In `LinkedHashSet`'s implementation, the old object is retained; calling `add` does not update its `note` field.

If the set is currently:

~~~text
[#10:old, #20:other]
~~~

then adding `#10:new` produces neither `[#10:new, #20:other]` nor `[#20:other, #10:new]`. The result remains:

~~~text
[#10:old, #20:other]
~~~

If you want to replace the representative with the new object via remove/add, you must also accept the ordering consequence:

~~~text
remove(#10:new) → removes the equivalent element #10:old
add(#10:new)    → adds the new object at the end
result          → [#20:other, #10:new]
~~~

Because `remove` also searches by equality rules, the object used for lookup does not have to be the exact reference currently stored.

If the requirement is "keep the original position while always updating details by ticket number," do not expect `Set.add` to mutate data in place. A `LinkedHashMap<Integer, Ticket>` with the ticket number as the key expresses the value-update requirement much more clearly: in insertion-order mode, updating the value for an existing key does not move the key's position. That is a different design from removing and re-adding a set element. [Java 17: LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html).

For these deductions to hold, do not mutate fields involved in `equals/hashCode` while the object is in the set. If the hash code or equality relation changes while stored, lookup and removal can behave contrary to what you expect. This lesson uses immutable `record` components and a fixed ticket number to separate that concern from ordering rules.

## 8. null Also Has a Position, but Only One Membership

`LinkedHashSet` allows `null`. Starting from `[start, null, end]`:

- `add(null)` returns `false` and keeps `[start, null, end]`.
- Removing `null` and then adding `null` back yields `[start, end, null]`.

There is no special rule that "`null` is always first" or "`null` is always last." The observed position comes from when it was inserted into the set and subsequent operations.

`null` is a special value with no methods to call. You do not need to call `null.equals(...)`; the set implementation handles this case.

Do not use `List.of("start", null, "end")` to build the input for the example because `List.of` does not allow `null`. The program below adds each element individually to verify `LinkedHashSet`'s exact behavior without failing early on list creation.

## 9. Complete Program: Predict Before Running

Save the following as `LinkedHashSetReinsertDemo.java`. The program has no dependencies outside the JDK. It individually tests duplicate insertion, batch addition, remove/add, representative of equivalent objects, `null`, order comparison, and iterators.

Before running, predict three things:

1. Where does `review` stand after `add("review")` and after remove/add?
2. Which `note` does ticket 10 keep when adding an equivalent object?
3. Are the two sets `[A, B]` and `[B, A]` equal according to `Set.equals`?

~~~java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.LinkedHashSet;
import java.util.List;

public class LinkedHashSetReinsertDemo {
    record Ticket(int number, String note) {
        @Override
        public boolean equals(Object other) {
            return other instanceof Ticket ticket
                    && number == ticket.number;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(number);
        }

        @Override
        public String toString() {
            return "#" + number + ":" + note;
        }
    }

    static <E> boolean moveExistingToEnd(LinkedHashSet<E> set, E element) {
        if (!set.remove(element)) {
            return false;
        }
        set.add(element);
        return true;
    }

    public static void main(String[] args) {
        LinkedHashSet<String> steps =
                new LinkedHashSet<>(List.of("draft", "review", "done"));

        System.out.println("initial=" + steps);
        System.out.println("add(review)=" + steps.add("review"));
        System.out.println("after duplicate=" + steps);
        System.out.println("contains(draft)=" + steps.contains("draft"));
        System.out.println("after contains=" + steps);
        System.out.println("addAll="
                + steps.addAll(List.of("review", "publish", "draft", "archive")));
        System.out.println("after addAll=" + steps);
        System.out.println("remove(review)=" + steps.remove("review"));
        System.out.println("add(review) after remove=" + steps.add("review"));
        System.out.println("after reinsert=" + steps);
        System.out.println("remove(missing)=" + steps.remove("missing"));
        System.out.println("after missing remove=" + steps);
        System.out.println("move(draft)=" + moveExistingToEnd(steps, "draft"));
        System.out.println("after move=" + steps);
        System.out.println("move(missing)=" + moveExistingToEnd(steps, "missing"));
        System.out.println("after missing move=" + steps);

        Ticket original = new Ticket(10, "old");
        Ticket replacement = new Ticket(10, "new");
        LinkedHashSet<Ticket> tickets = new LinkedHashSet<>();
        tickets.add(original);
        tickets.add(new Ticket(20, "other"));
        System.out.println("tickets initial=" + tickets);
        System.out.println("equal ticket=" + original.equals(replacement));
        System.out.println("add equal ticket=" + tickets.add(replacement));
        System.out.println("tickets after duplicate=" + tickets);
        System.out.println("original retained=" + (tickets.iterator().next() == original));
        System.out.println("remove equal ticket=" + tickets.remove(replacement));
        System.out.println("add replacement=" + tickets.add(replacement));
        System.out.println("tickets after replace=" + tickets);
        System.out.println("replacement retained="
                + (new ArrayList<>(tickets).get(1) == replacement));

        LinkedHashSet<String> withNull = new LinkedHashSet<>();
        withNull.add("start");
        withNull.add(null);
        withNull.add("end");
        System.out.println("null initial=" + withNull);
        System.out.println("add(null)=" + withNull.add(null));
        System.out.println("null after duplicate=" + withNull);
        withNull.remove(null);
        withNull.add(null);
        System.out.println("null after reinsert=" + withNull);

        LinkedHashSet<String> forward =
                new LinkedHashSet<>(List.of("A", "B"));
        LinkedHashSet<String> backward =
                new LinkedHashSet<>(List.of("B", "A"));
        System.out.println("set equality=" + forward.equals(backward));
        System.out.println("iteration order equality="
                + new ArrayList<>(forward).equals(new ArrayList<>(backward)));

        LinkedHashSet<Integer> many = new LinkedHashSet<>(1);
        List<Integer> expected = new ArrayList<>();
        for (int value : new int[] {40, 10, 30}) {
            many.add(value);
            expected.add(value);
        }
        for (int value = 100; value < 200; value++) {
            many.add(value);
            expected.add(value);
        }
        System.out.println("many size=" + many.size());
        System.out.println("many insertion order="
                + new ArrayList<>(many).equals(expected));
        System.out.println("many add(10)=" + many.add(10));
        System.out.println("many order after duplicate="
                + new ArrayList<>(many).equals(expected));

        LinkedHashSet<String> directions =
                new LinkedHashSet<>(List.of("north", "south", "west"));
        Iterator<String> iterator = directions.iterator();
        System.out.println("iterator first=" + iterator.next());
        System.out.println("iterator duplicate=" + directions.add("south"));
        System.out.println("iterator next=" + iterator.next());
    }
}
~~~

Compile and run in the directory containing the file:

~~~shell
javac --release 17 -encoding UTF-8 LinkedHashSetReinsertDemo.java
java LinkedHashSetReinsertDemo
~~~

`--release 17` instructs the compiler to check code and APIs against Java 17. Use JDK 17 or newer for these commands. `record` classes are included in that version scope.

Expected output:

~~~text
initial=[draft, review, done]
add(review)=false
after duplicate=[draft, review, done]
contains(draft)=true
after contains=[draft, review, done]
addAll=true
after addAll=[draft, review, done, publish, archive]
remove(review)=true
add(review) after remove=true
after reinsert=[draft, done, publish, archive, review]
remove(missing)=false
after missing remove=[draft, done, publish, archive, review]
move(draft)=true
after move=[done, publish, archive, review, draft]
move(missing)=false
after missing move=[done, publish, archive, review, draft]
tickets initial=[#10:old, #20:other]
equal ticket=true
add equal ticket=false
tickets after duplicate=[#10:old, #20:other]
original retained=true
remove equal ticket=true
add replacement=true
tickets after replace=[#20:other, #10:new]
replacement retained=true
null initial=[start, null, end]
add(null)=false
null after duplicate=[start, null, end]
null after reinsert=[start, end, null]
set equality=true
iteration order equality=false
many size=103
many insertion order=true
many add(10)=false
many order after duplicate=true
iterator first=north
iterator duplicate=false
iterator next=south
~~~

## 10. Reading the Output by Each State Change

### 10.1. Duplicate Insertion and Presence Check

The two lines `add(review)=false` and `after duplicate=[draft, review, done]` answer two different questions: there is no new member, and the order did not change.

After `contains(draft)=true`, `draft` is still first. The set tracks the order in which elements were added, not when they were looked up.

### 10.2. Batch Insertion

`addAll=true` occurs because `publish` and `archive` are new. `review` is not pulled behind `done`; `draft` is not pulled behind `publish`. The sequence of existing elements is preserved.

The key part to observe is the new tail `publish, archive`. That is the order in which the new values were encountered in the input `List` batch.

### 10.3. Removing/Adding and Moving an Existing Element

After removing and re-adding `review`, the result is `[draft, done, publish, archive, review]`. The final element count is still five, yet two membership changes occurred.

`moveExistingToEnd` then moves `draft` to the end. The method returns `false` when the name to move is not in the set and does not add that name. The condition `if (!set.remove(element))` is what defines the semantics of "move only an existing element."

If you use a method that always calls `remove` then `add` without checking the removal result, a missing value will be newly added. Both methods can produce the same result for existing data while behaving differently for absent data.

### 10.4. Old Representative and New Representative

`equal ticket=true` confirms the two ticket-10 objects are equivalent under the chosen rules. `add equal ticket=false` confirms no member was added.

`original retained=true` intentionally uses `==`: it checks the actual reference of the stored representative, not just business equality. The `#10:old` output shows that a duplicate `add` does not update content from the `replacement` object.

After remove/add, ticket 20 moves ahead and `#10:new` moves to the end. `replacement retained=true` confirms the new object has become the representative. To conclude that the representative was replaced, checking `contains(replacement)` alone is not enough, because that result would also be `true` while the old representative was still in the set.

### 10.5. Comparing Membership vs. Comparing Sequence

`set equality=true` while `iteration order equality=false` is completely consistent. Both sets contain the same `A` and `B`, yet have different iteration sequences.

Converting each set to an `ArrayList` creates two order snapshots to compare with `List.equals`. This step checks what `Set.equals` does not check. Do not use the equality of two sets as proof that they will print the same sequence. The `Set.equals` contract is based on membership, not position. [Java 17: Set.equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#equals(java.lang.Object)).

### 10.6. Many Insertions Do Not Break the Ordering Contract

The `many` section starts with a small initial capacity and adds 103 distinct numbers in a sequence recorded separately in `expected`. The program prints `many insertion order=true` and still prints `true` after a duplicate `add` of 10.

This check compares the iteration result against the operation sequence. It does not measure table resizes, bucket counts, or internal layout. Do not infer a capacity formula from the number `103`. What is verified here is that many insertions still preserve order per the contract.

### 10.7. Duplicate Insertion While Using an Iterator

The `directions` iterator has already retrieved `north`. The call to add `south` returns `false`, neither adding nor removing a member; the subsequent `next` call still retrieves `south`.

This case differs from removing `south` and adding it back while an old iterator is active. A remove/add sequence modifies the structure even though the final size may equal the initial size. Do not use a before/after `size` comparison to decide whether an existing iterator is still valid.

## 11. A Move-to-End Helper Needs Its Own Contract

The method in the program:

~~~java
static <E> boolean moveExistingToEnd(LinkedHashSet<E> set, E element) {
    if (!set.remove(element)) {
        return false;
    }
    set.add(element);
    return true;
}
~~~

This is an excerpt from the complete program, not a built-in JDK API. It has three characteristics that must be read accurately.

First, a return value of `true` indicates that the element existed and the remove/add procedure ran. It does not assert that the final position differs from the previous position. If the element was already last, the method still removes and re-adds it and returns `true`.

Second, the method inserts the passed-in `element` object itself as the representative when re-adding. With immutable `String` values that are equal, reference differences are usually unnoticeable. With `Ticket`, where `note` does not participate in equality, this behavior can change stored data. The method name only speaks of position; the designer still has to decide whether replacing the representative is allowed or whether the old object must be kept.

Third, the two operations are not an atomic action. Another thread can interleave if the data is shared without synchronization. If business logic requires "check then move" as an uninterruptible step, you must guard the entire procedure along with related accesses. Seeing a short method or a final result with the same element count does not create thread safety.

In the example, the data is stable, the equality rules are valid, and only one thread operates on it. The method helps observe how to create a new position in Java 17. For complex objects or multi-threaded contention requirements, define the data contract before reusing it as-is.

## 12. Preserving Insertion Order Does Not Automatically Track Most Recent Use

A "recently used" queue often needs to move an element to a priority position after each use. For example, if a user just reopened document `draft`, that document should become the most recently used item.

`LinkedHashSet.add("draft")` on a set that already contains `draft` does not do that. Calling `contains("draft")` does not do that either. If you use these calls as a way to "touch to refresh," the UI may keep the old order even though a new event arrived.

Distinguish the requirements:

| Requirement | Meaning of a repeat encounter |
| --- | --- |
| Keep initial recorded position while element remains in set | Ignore duplicate and keep old spot |
| Order by most recent occurrence | Must update position when a new event arrives |
| Update data by identity, keep identity order | Replace info attached to the identity, keep the key's spot |
| Record every event | Every occurrence must be stored, including repeated values |

These four requirements cannot be inferred solely from "need to keep order." You must clarify which event determines order and whether every occurrence should be kept.

`LinkedHashMap` has an access-order mode when constructed with `accessOrder=true`; specified access operations, such as `get`, can affect position. That capability does not become the behavior of `LinkedHashSet.add` just because the two classes are related in implementation. Nor does access-order mode alone provide a full capacity, expiration, or synchronization policy for a cache. [Java 17: LinkedHashMap, access-order mode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html).

If you need to record the history of every occurrence, a deduplicating set has already discarded occurrence count information. In that case, choose an appropriate event-storage model instead of trying to reconstruct history from the final `LinkedHashSet`.

## 13. Version Note: add Differs from addFirst and addLast

The rule "adding an existing element does not change its position" in this lesson applies to the regular `add` method. Starting in Java 21, `LinkedHashSet` implements `SequencedSet` and has explicit positioning methods such as `addFirst` and `addLast`.

Per the Java 21 API, when an element already exists, `addFirst` can move it to the front and `addLast` can move it to the end. If the element is not present, they add it at the respective position. Both methods return `void` and do not share the signature or semantics of `boolean add(E)`. [Java 21: LinkedHashSet.addFirst and addLast](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashSet.html#addFirst(E)).

Therefore, read method names in code carefully. An observation that holds for `set.add(e)` does not prove the result of `set.addLast(e)`. Conversely, seeing `addLast` move positions in Java 21 code does not mean `add` changed its behavior.

This lesson's program uses remove/add to maintain compatibility when compiling for Java 17. The new methods are not in the API set allowed by `--release 17`. If your project targets Java 21 or newer and needs explicit positioning, you can consider those APIs according to their exact contracts.

Also do not automatically equate "repositioning an existing element" with "removing and adding a different equivalent object." The ticket-10 example shows that this lesson's remove/add sequence has an additional consequence for the stored representative. When requirements call for updating both data and position, check each consequence separately.

## 14. Costs and Limitations That Directly Affect Usage

With a well-distributed hash function, the basic operations `add`, `contains`, and `remove` offer constant-time performance under typical usage expectations. That does not mean every object type or every hash distribution yields the same cost. The time to compute `hashCode` and `equals` for elements also contributes to actual cost.

`LinkedHashSet` must maintain links to preserve order. Full iteration takes time proportional to the number of current elements, rather than having to find positions by scanning a list from the start on every insertion. In exchange, link metadata must be stored and updated. Do not use the reasoning "it has links so it is always faster" to choose a structure.

A remove/add sequence performs two membership-changing operations and discards the old position. If the requirement is simply to ignore duplicates, calling `add` directly both expresses the intent accurately and avoids unnecessary side effects.

While iterating, do not remove or add through the set yourself and then continue using the old iterator. `LinkedHashSet`'s iterator has a modification detection mechanism to fail early; `ConcurrentModificationException` aids bug detection and is not a guaranteed synchronization mechanism. Even if no exception appears in one test run, you still cannot rely on that to prove code that mutates a set during iteration is correct. [Java 17: HashSet, iterators and fail-fast limitations](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html).

If you need to reorder multiple elements based on iteration results, a clearer approach is to record a plan in a separate structure, finish the iteration, and then apply the changes. Clearly define the outcome when multiple elements are moved so the final order does not depend on a hard-to-follow mutating loop.

## 15. Common Reasoning Pitfalls

| Claim | How to verify properly |
| --- | --- |
| "Calling `add` moves the element to the end" | Check whether the element is already present; a duplicate `add` preserves position |
| "`add` returned `false`, so the element is not in the set" | `false` indicates no new member was added; the element may already exist |
| "An object just created with `new` is definitely a new element" | Compare using `equals/hashCode`, not just references |
| "Adding an object with the same ID updates the old data" | Check the representative object; `Set.add` is not a record-update operation |
| "Removing and re-adding only changes position" | It can also replace the representative and invalidate existing iterators |
| "The element count didn't change, so there was no structural modification" | Removing one and adding one is still two modifications |
| "`addAll` sorts the set according to the latest batch" | Existing members keep their spots; only new members are appended |
| "Two equal sets have the same order" | `Set.equals` ignores position; compare `List` snapshots if order is a requirement |
| "Preserving order means sorted in ascending order" | Insertion order depends on operations; it does not automatically become value order |
| "Copying from a `HashSet` restores insertion history" | The copy only receives the iteration order that the source provides |
| "Having a `LinkedHashMap` inside means it's an access-ordered set" | Read the `LinkedHashSet` contract; `add` and `contains` do not refresh position |
| "Every add method behaves like `add`" | Separate Java 21's positioning APIs `addFirst/addLast` from `add` |

A useful habit is to write down the state before, operation, return value, and state after on four lines. Doing so forces you to distinguish "no new member" from "no element," as well as "same size" from "same modification history."

## 16. Practice with Solutions

### Exercise 1: Predicting duplicate add

The initial state is `[red, green, blue]`. Execute `add("green")`, then `add("yellow")`. What are the two return values and the final order?

**Solution:** The first returns `false` because `green` is already present and keeps its middle position. The second returns `true` and appends `yellow` to the end. The result is `[red, green, blue, yellow]`. Neither step moves `green`.

### Exercise 2: Distinguishing duplicate add from re-entry

Starting from `[red, green, blue]`, execute `remove("red")`, `add("green")`, `add("red")`.

**Solution:** Removing `red` succeeds, giving `[green, blue]`. Adding duplicate `green` returns `false` and leaves things unchanged. Adding `red` after it was removed returns `true`, giving `[green, blue, red]`. The set does not remember `red`'s old first spot.

### Exercise 3: Batch with both old and new elements

The initial set is `[A, B]`. The source has order `[B, C, A, D, C]`. What is the result of calling `addAll`?

**Solution:** `B` and `A` are already present so they do not move. The first `C` and `D` are new. The final `C` is a duplicate. The result is `[A, B, C, D]` and `addAll` returns `true`. This is not the order of last occurrence.

### Exercise 4: Replacing element details

Use the `Ticket` rules from the program. The set is `[#10:old, #20:other]`. Add `new Ticket(10, "new")` and then check `contains` with the new ticket. Can you conclude that the `new` info was saved?

**Solution:** No. `contains` searches by ticket number, so it can return `true` even though the representative is still `#10:old`. You must inspect the representative or choose a structure that supports updating info by key. A duplicate `add` does not mean a successful update.

### Exercise 5: Writing the right check for order

You create two `LinkedHashSet` instances with the same members but inserted in two different sequences. Checking `first.equals(second)` returns `true`. How do you detect the order difference?

**Solution:** At a point when the data is stable, create `new ArrayList<>(first)` and `new ArrayList<>(second)`, then compare the two lists. `List.equals` considers sequence. This check covers the ordering requirement that set equality does not express.

### Exercise 6: Move helper and missing element

With `[A, B]`, call `moveExistingToEnd(set, "C")` from the program. Then call `moveExistingToEnd(set, "A")`. What are the set and return values?

**Solution:** The first returns `false` and remains `[A, B]` because the method does not automatically add a missing value. The second returns `true` and gives `[B, A]`. If the method always removed and added without checking the result, the first call would have created `C` and carried different semantics.

### Exercise 7: Choosing a call by Java version

You need to move an existing element to the end. The code must compile with `--release 17`. Can you replace `add` with `addLast`?

**Solution:** Not in the Java 17 API set. You need a version-compatible procedure, such as remove/add with a clear contract regarding absent elements, representatives, and synchronization. If the project upgrades to Java 21 or newer, you can consider `addLast` according to that method's contract. Renaming the call does not make the new API exist in Java 17.

## 17. Self-Check When Applying to Real Code

Before using `LinkedHashSet` for a data stream, make sure you can answer these questions:

- What is the rule for determining duplicates, and do `equals/hashCode` reflect it?
- Do you need to preserve the spot of the first still-active insertion, or prioritize the most recent occurrence?
- Is an incoming value merely a duplicate, or does it carry information that must be updated?
- When removing and re-adding an equivalent object, is replacing the stored representative acceptable?
- Does the source of `addAll` have a guaranteed order?
- Is your check comparing membership or actually comparing iteration sequence?
- Is an existing iterator or another thread using the set while you modify it?
- Does the project's Java version match the positioning API that the code calls?

The point to keep exact in every example is the moment presence is evaluated. If the element is already present immediately before `add`, that call does not move it to the end. If it has been removed, the next `add` is a new entry and creates a new position at the end under the standard operations in this lesson.
