# Collections.copy: Destination Size and How It Differs from Creating a New Copy

The name `copy` easily leads readers to assume that the call creates a new list containing the source data. `Collections.copy` does something more specific: it **writes the source elements into existing positions of the destination list**, starting at index 0.

The key rule to remember is `destination.size() >= source.size()`, not whether the destination's capacity is large enough. The destination must also support replacing elements. When the destination is longer than the source, the trailing portion of the destination is preserved; the method neither shrinks nor appends to the list.

This lesson explains that contract in Java 17 and contrasts it with `new ArrayList<>(source)`, `addAll`, and `List.copyOf`. The examples also separate copying the container from cloning the element objects.

## 1. Reading the Signature in the Right Data Direction

The method signature:

~~~java
public static <T> void copy(
        List<? super T> dest,
        List<? extends T> src
)
~~~

This is the API declaration, not a method you need to implement yourself. **Destination comes first, source comes second**:

~~~java
Collections.copy(destination, source);
~~~

The method returns `void`. There is no new result list to assign from the call. The destination list object already exists beforehand, and its own data is modified in place.

The source needs to be readable; it can be an unmodifiable list. The destination needs enough existing positions and must allow replacing elements at the written positions. The two requirements—"enough positions" and "permission to replace"—are independent.

In terms of types, the source produces elements so it uses `? extends T`; the destination consumes elements so it uses `? super T`. This allows passing `Integer` data into a `List<Number>` validly without raw casts.

~~~java
List<Integer> source = List.of(7, 8);
List<Number> destination =
        new ArrayList<>(List.<Number>of(0.5, 1.5, 2.5));

Collections.copy(destination, source);
~~~

The snippet above is illustrative code inside a method with all necessary imports. The destination becomes `[7, 8, 2.5]`. The broader type of the destination receives the integers; the remaining position keeps the original floating-point number.

## 2. Postcondition: Overwriting the Prefix and Keeping the Rest

Suppose two independent lists initially have the following contents:

~~~text
source:      [A, B]
destination: [old0, old1, tail2, tail3]
~~~

After `Collections.copy(destination, source)`:

~~~text
source:      [A, B]
destination: [A, B, tail2, tail3]
~~~

With a source of `n` elements and a destination of `m` elements, when a valid copy completes on two non-interfering regions:

- Positions `0` through `n - 1` of the destination receive the corresponding elements from the source.
- Positions `n` through `m - 1` of the destination remain unchanged.
- The size of the destination remains `m`.
- There is no `add` step to grow the destination or `remove` step to shorten it.

That is the contract of [Collections.copy, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#copy(java.util.List,java.util.List)).

### Copying a Shorter Source Does Not Erase Old Trailing Data

If you subsequently copy `[Z]` into a destination that is currently `[A, B, tail2, tail3]`, the destination becomes:

~~~text
[Z, B, tail2, tail3]
~~~

`B`, `tail2`, and `tail3` are still there. If the application requires that "the destination has the exact same contents and element count as the source," you need a different strategy to replace the entire data. `copy` by itself only replaces the prefix.

This matters when reusing a list as a result buffer: old trailing data does not automatically become invalid data. The application's API must explicitly specify the valid data length or manage the list size according to its requirements.

### Keeping the Destination Object Means Other References See the Changes

~~~java
List<String> alias = destination;
Collections.copy(destination, source);
~~~

`alias` and `destination` still point to the same list. Anyone holding `alias` sees the data at the replaced positions.

Unlike creating a new list and reassigning only a local variable, copying into an existing object preserves the container's identity. That is useful when a component intentionally owns pre-allocated data slots, but it can also cause unintended side effects if the destination is shared.

## 3. Size Is the Actual Element Count; Capacity Is Only Storage Space

### A Common Mistake with the Integer-Argument Constructor

~~~java
List<String> source = List.of("A", "B");
List<String> destination = new ArrayList<>(source.size());

Collections.copy(destination, source);
~~~

This is an intentionally wrong example: the destination has an initial capacity for 2 elements, yet `size()` is still 0. There is no index 0 or 1 to replace yet, so copying a non-empty source throws `IndexOutOfBoundsException`.

`new ArrayList<>(n)` creates an empty list with an initial capacity, not `n` `null` elements. `ensureCapacity(n)` does not add elements to the list either. [ArrayList(int) constructor, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#%3Cinit%3E(int)).

Valid indices are determined by `size`, not by how much internal memory has been reserved. After calling `clear` on a list, `size` becomes 0 even though the internal memory management may still retain the allocated array; that list also has no slots to `set` or copy into.

### Initial Elements Are Required If You Want to Copy into a New List

One way to create enough positions is:

~~~java
List<String> destination =
        new ArrayList<>(Collections.nCopies(source.size(), "?"));

Collections.copy(destination, source);
~~~

Here, the `ArrayList(Collection)` constructor receives a collection with the exact number of elements, so the new list has the corresponding positions. It allows replacing elements, thereby satisfying both requirements.

You can also use an `add` loop to create enough initial slots. Using `nCopies` is not mandatory; what matters is that the destination list actually already contains the number of elements to be replaced.

However, if the sole goal is a new list matching the source, creating slots and then copying is usually more roundabout than necessary:

~~~java
List<String> result = new ArrayList<>(source);
~~~

This approach both creates a new container and populates the source elements directly in the constructor. It does not need an existing destination object to overwrite.

### Similar-Looking States with Different Conditions

| How the destination is prepared | Size for `n > 0` | Supports replacing elements? | Suitable as destination for copying `n` elements? |
| --- | --- | --- | --- |
| `new ArrayList<T>(n)` | 0 | Supports replacing once positions exist, but none exist yet | No |
| `Collections.nCopies(n, value)` | n | Does not support replacing | No |
| `new ArrayList<>(Collections.nCopies(n, value))` | n | Yes | Yes |
| `new ArrayList<>(source)` | Size of source | Yes | Yes, though it usually already achieves the goal of creating a new copy |

Do not confuse a list's support for `add` with satisfying the size requirement. An empty `ArrayList` can have elements added, but it does not allow `set(0, value)` because index 0 does not exist yet.

## 4. A Long-Enough Destination Still Might Not Allow Replacing Elements

### `set` Permission Differs from Resize Permission

`copy` needs to replace values in existing slots. It does not require the destination to be an `ArrayList`, nor does it require the list to be resizable.

For example:

~~~java
String[] array = {"x", "y", "keep"};
List<String> destination = Arrays.asList(array);

Collections.copy(destination, List.of("A", "B"));
~~~

The list returned by `Arrays.asList` has a fixed size but allows replacing elements, so the copy succeeds. The array itself becomes `[A, B, keep]` because the list is a view backed by the array. [Arrays.asList API, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)).

This is a case where "cannot `add`" does not prevent using it as a copy destination.

### Unmodifiable Lists Do Not Grant Overwrite Permission

A list created by `List.of`, `List.copyOf`, or `Collections.nCopies` may have enough elements, yet does not support replacing them. Copying actual data into it throws `UnsupportedOperationException`.

~~~java
List<String> destination = List.of("?", "?");
Collections.copy(destination, List.of("A", "B"));
~~~

The snippet above intentionally demonstrates a modification-permission error. Having `destination` typed as `List<String>` does not mean every mutating method declared on the interface is supported.

`List.set` is an optional operation. Beyond modification permission, a specific list implementation may also impose restrictions on element types or `null`. [List.set contract, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#set(int,E)).

### The Source Does Not Need Modification Permission

The source is only read to retrieve elements. `List.of("A", "B")` is a valid source even though it does not allow `set`.

Do not mix up the two arguments and assume the error comes from the source. The destination is the first argument, and its element-replacement permission is what the write process requires.

Also do not use an empty source as a general test for destination mutability. When there are no elements to replace, no write operations may be performed at all; a call that does not throw does not prove the destination works for a non-empty source.

## 5. Comparing Copying into an Existing Object vs. Creating a New Result

| Operation | Creates a new result container? | Effect on existing destination | Size after operation | Mutability of result |
| --- | --- | --- | --- | --- |
| `Collections.copy(dest, src)` | Does not create one | Overwrites the prefix | Keeps `dest`'s original size | Depends on the chosen `dest` type |
| `new ArrayList<>(src)` | Yes, a new `ArrayList` | No existing `dest` needed | Equals source element count | Modifiable |
| `dest.addAll(src)` | Does not create one | Inserts/appends elements into `dest` | Increases by added element count | `dest` must support adding |
| `List.copyOf(src)` | Returns a list with an unmodifiable contract; may reuse an eligible result | Does not overwrite an existing `dest` | Equals source element count | Unmodifiable; rejects `null` elements |

### When You Need to Preserve the Destination Object and Trailing Slots

`Collections.copy` is appropriate when you already have a sufficiently large list buffer and intentionally want to replace a prefix. For example, a display component that owns fixed position slots and needs to update the leading positions while keeping the rest according to its own rules.

You must know who holds references to the destination. Copying makes changes visible to them. If the goal is to return an isolated value to the caller, reusing a shared destination may violate that requirement.

### When You Need a Structurally Independent Working Copy

`new ArrayList<>(source)` is the direct choice. Adding, removing, or replacing references on the new list does not affect the slots of the source list.

It still holds references to the same elements. Structural independence of the list is not yet independence of every object inside it. [ArrayList(Collection) constructor, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#%3Cinit%3E(java.util.Collection)).

### When You Need to Append Data

`addAll` keeps the existing elements and appends source elements at the end when using the non-indexed overload. A destination `[old, tail]` with `[A, B]` added becomes `[old, tail, A, B]`.

This differs from `copy`, because copying the same source into that destination yields `[A, B]` and does not increase size. Do not substitute one call for the other just because both move data from source to destination.

### When You Need an Unmodifiable List from a Source

`List.copyOf` returns a result that does not reflect subsequent structural changes to the source collection, though it does not deep-clone element objects. It rejects `null` in the source and does not guarantee that every call creates a new list identity.

Thus the name `copyOf` also does not imply "always allocates a brand-new object." Rely on the content and unmodifiability contract, not `==`, to verify a suitable data representation. [List.copyOf API, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)).

## 6. Copying Elements Here Means Copying Reference Values

Suppose the source holds a `Box` object with a mutable count:

~~~text
source[0] ───────> Box("stock", 1)
~~~

After copying into the destination, the relationship is:

~~~text
source[0] ───────┐
                ├──> same Box("stock", 1)
destination[0] ─┘
~~~

No new `Box` constructor call occurs. If you change that object's `count` to 2, both source and destination read `stock:2`.

Conversely, `destination.set(0, new Box("local", 9))` replaces only the reference in the destination slot. The source slot still points to the `stock` object. Two kinds of operations must be distinguished:

1. **Mutating the shared object:** visible through both lists.
2. **Replacing the reference at a position in the destination list:** does not automatically replace the corresponding reference in an independent source.

Creating `new ArrayList<>(source)` also copies elements this way. `List.copyOf(source)` does not freeze the objects inside just because the outer list is unmodifiable.

If the requirement is for the receiver to make completely isolated edits, you must decide how to copy each mutable part of the model. If the requirement is data that cannot change after publication, you need a fully protected representation. Neither goal is automatically solved by the word "copy."

The `Collection` documentation clearly distinguishes container unmodifiability from element state. [Collection, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#unmodcoll).

## 7. Copying into a Subrange and Handling Overlapping Regions

### Using `subList` as an Offset Destination

`Collections.copy` has no starting-index parameter. You can pass a view of the range to write:

~~~java
List<String> destination =
        new ArrayList<>(List.of("L", "x", "y", "R"));
List<String> source = List.of("A", "B");

Collections.copy(destination.subList(1, 3), source);
~~~

The view has two elements corresponding to indices 1 and 2 of the backing list. The resulting original list is `[L, A, B, R]`. Index 0 of the view is not index 0 of the original list.

The upper bound of `subList(from, to)` is exclusive. The range `[1, 3)` has length 2. You must still ensure the view has enough size for the source and supports element replacement.

`subList` does not create a copy by itself. Writes to the view affect the backing list. Do not structurally add or remove elements on the backing list through another path and then continue using the view as if its lifecycle were unchanged. [List.subList API, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#subList(int,int)).

### Source and Destination Can Share the Same Backing List

If you take two ranges of the same list, a write to the destination can alter data that the source still intends to read in a later step. You should not assume that `Collections.copy` always snapshots the entire source before writing or automatically handles every overlapping case like an array-copy API with a dedicated overlap contract.

If the intent is to transfer the **original** data of one range into an overlapping range, create a separate snapshot of the source first:

~~~java
List<String> values =
        new ArrayList<>(List.of("A", "B", "C", "D", "E"));

List<String> snapshot =
        new ArrayList<>(values.subList(0, 3));

Collections.copy(values.subList(1, 4), snapshot);
~~~

The source is fixed at the list level as `[A, B, C]`. Writing into indices 1, 2, 3 produces `[A, A, B, C, E]`.

The example does not rely on predicting the outcome of an overlapping call without a snapshot. It structures the source and destination so that the data to be read can no longer be altered by the write process itself.

If the elements are mutable objects and you also need their state at a point in time, a list copy alone is still not enough for a deep snapshot. In the example, the elements are strings, so the concern being examined is the list positions.

## 8. `null`, Failures, and the Limits of a Single Copy

### The Lists Themselves Must Not Be `null`

Passing `null` as source or destination throws `NullPointerException`. A `null` source does not mean the same thing as an empty source list.

An empty source has size 0, so there are no elements to transfer. A modifiable destination containing `[keep]` still keeps `[keep]` in the experiment. Do not use an empty source as a substitute for clearing the destination.

### `null` Elements Depend on the Destination Contract

With source `[null, N]` and an `ArrayList` destination having three slots `[?, ?, tail]`, copying yields `[null, N, tail]`. `ArrayList` permits `null`.

A specific list may reject `null` or certain kinds of values. Having enough size and a `set` method still does not guarantee that arbitrary data is valid for the destination.

Meanwhile, `List.copyOf(source)` rejects a source containing `null` elements. This is a behavioral difference you must consider when switching how data is created.

### Do Not Treat Errors as a Rollback Promise

Typical errors include a destination that is too short or does not support replacing elements. With custom lists or data invalid for the destination, errors can also occur while reading or writing elements.

The contract does not provide a transaction with a guarantee of automatically restoring all old data if all steps do not complete. Do not extrapolate from a size-error experiment to conclude that every error on every list type happens before the first write.

If you need to validate or transform data that might fail, prepare and validate on private data before publishing changes according to the application's ownership protocol. That is still different from guaranteeing atomic updates for a shared list.

### No Automatic Concurrent Snapshot

If the source changes during the copy, or another thread reads the destination between write steps, the result may not be a consistent state according to business requirements.

You need to keep the source stable and control read/write access to the destination across the entire operation if consistency is required. Synchronizing individual small calls does not automatically turn the whole copy process into an application transaction.

## 9. Complete Program and Execution Evidence

Save the code to **`ListCopyDemo.java`**. The `rejects` helper verifies the exact expected exception type; if an operation unexpectedly succeeds or throws the wrong type, the program stops with `AssertionError`.

Simple `String` sources are used to test size and trailing elements. `Box` objects are used specifically to observe element sharing; none of the list-creation methods in the experiment group automatically clone `Box`.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedList;
import java.util.List;

public class ListCopyDemo {
    static final class Box {
        private final String name;
        private int count;

        Box(String name, int count) {
            this.name = name;
            this.count = count;
        }

        @Override
        public String toString() {
            return name + ":" + count;
        }
    }

    private static void rejects(
            String label,
            Class<? extends RuntimeException> expected,
            Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + " unexpectedly succeeded");
        } catch (RuntimeException ex) {
            if (!expected.isInstance(ex)) {
                throw new AssertionError(label + " wrong exception", ex);
            }
            System.out.println(label + "=" + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        List<String> source = List.of("A", "B");
        List<String> destination = new ArrayList<>(
                List.of("old0", "old1", "tail2", "tail3"));
        List<String> alias = destination;
        Collections.copy(destination, source);
        System.out.println("prefix.destination=" + destination);
        System.out.println("prefix.size=" + destination.size());
        System.out.println("prefix.sameObject=" + (alias == destination));
        Collections.copy(destination, List.of("Z"));
        System.out.println("prefix.afterShortSource=" + alias);
        System.out.println("source.after=" + source);

        List<String> capacityOnly = new ArrayList<>(source.size());
        System.out.println("capacity.size=" + capacityOnly.size());
        rejects("capacity.copy", IndexOutOfBoundsException.class,
                () -> Collections.copy(capacityOnly, source));
        List<String> tooSmall = new ArrayList<>(List.of("old"));
        rejects("tooSmall.copy", IndexOutOfBoundsException.class,
                () -> Collections.copy(tooSmall, source));

        List<String> readyTarget =
                new ArrayList<>(Collections.nCopies(source.size(), "?"));
        Collections.copy(readyTarget, source);
        System.out.println("readyTarget=" + readyTarget);
        rejects("readonly.copy", UnsupportedOperationException.class,
                () -> Collections.copy(List.of("?", "?"), source));
        rejects("nCopies.copy", UnsupportedOperationException.class,
                () -> Collections.copy(Collections.nCopies(2, "?"), source));

        String[] backing = {"x", "y", "keep"};
        Collections.copy(Arrays.asList(backing), source);
        System.out.println("fixed.array=" + Arrays.toString(backing));

        List<String> fresh = new ArrayList<>(source);
        fresh.add("C");
        System.out.println("fresh.editable=" + fresh);
        List<String> appended = new ArrayList<>(List.of("old", "tail"));
        appended.addAll(source);
        System.out.println("append.result=" + appended);

        List<Number> numbers =
                new ArrayList<>(List.<Number>of(0.5, 1.5, 2.5));
        Collections.copy(numbers, List.of(7, 8));
        System.out.println("numbers.destination=" + numbers);

        List<Box> boxSource =
                new ArrayList<>(List.of(new Box("stock", 1)));
        List<Box> boxDestination =
                new ArrayList<>(Collections.<Box>nCopies(1, null));
        Collections.copy(boxDestination, boxSource);
        List<Box> freshBoxes = new ArrayList<>(boxSource);
        List<Box> readonlyBoxes = List.copyOf(boxSource);
        System.out.println("boxes.sameElement="
                + (boxSource.get(0) == boxDestination.get(0)));
        boxSource.get(0).count = 2;
        System.out.println("boxes.source=" + boxSource);
        System.out.println("boxes.destination=" + boxDestination);
        System.out.println("boxes.fresh=" + freshBoxes);
        System.out.println("boxes.readonly=" + readonlyBoxes);
        boxDestination.set(0, new Box("local", 9));
        System.out.println("boxes.afterDestinationReplace=" + boxDestination);
        System.out.println("boxes.sourceAfterReplace=" + boxSource);

        List<String> withNull = Arrays.asList(null, "N");
        List<String> nullableDestination =
                new ArrayList<>(List.of("?", "?", "tail"));
        Collections.copy(nullableDestination, withNull);
        System.out.println("nullable.destination=" + nullableDestination);
        rejects("nullable.copyOf", NullPointerException.class,
                () -> List.copyOf(withNull));

        List<String> window =
                new ArrayList<>(List.of("L", "x", "y", "R"));
        Collections.copy(window.subList(1, 3), source);
        System.out.println("window.destination=" + window);

        List<String> overlapping =
                new ArrayList<>(List.of("A", "B", "C", "D", "E"));
        List<String> snapshot =
                new ArrayList<>(overlapping.subList(0, 3));
        Collections.copy(overlapping.subList(1, 4), snapshot);
        System.out.println("overlap.withSnapshot=" + overlapping);

        List<String> linked =
                new LinkedList<>(List.of("x", "y", "tail"));
        Collections.copy(linked, source);
        System.out.println("linked.destination=" + linked);

        List<String> keep = new ArrayList<>(List.of("keep"));
        Collections.copy(keep, Collections.<String>emptyList());
        System.out.println("emptySource.destination=" + keep);
        rejects("null.destination", NullPointerException.class,
                () -> Collections.copy((List<String>) null, source));
        rejects("null.source", NullPointerException.class,
                () -> Collections.copy(keep, (List<String>) null));
    }
}
~~~

Compile and run in the directory containing the file:

~~~shell
javac --release 17 -encoding UTF-8 ListCopyDemo.java
java ListCopyDemo
~~~

JDK 17 or later is required for this compile command. The code was compiled with `--release 17` and run on OpenJDK 24.0.2, exiting successfully. Exact stdout:

~~~text
prefix.destination=[A, B, tail2, tail3]
prefix.size=4
prefix.sameObject=true
prefix.afterShortSource=[Z, B, tail2, tail3]
source.after=[A, B]
capacity.size=0
capacity.copy=IndexOutOfBoundsException
tooSmall.copy=IndexOutOfBoundsException
readyTarget=[A, B]
readonly.copy=UnsupportedOperationException
nCopies.copy=UnsupportedOperationException
fixed.array=[A, B, keep]
fresh.editable=[A, B, C]
append.result=[old, tail, A, B]
numbers.destination=[7, 8, 2.5]
boxes.sameElement=true
boxes.source=[stock:2]
boxes.destination=[stock:2]
boxes.fresh=[stock:2]
boxes.readonly=[stock:2]
boxes.afterDestinationReplace=[local:9]
boxes.sourceAfterReplace=[stock:2]
nullable.destination=[null, N, tail]
nullable.copyOf=NullPointerException
window.destination=[L, A, B, R]
overlap.withSnapshot=[A, A, B, C, E]
linked.destination=[A, B, tail]
emptySource.destination=[keep]
null.destination=NullPointerException
null.source=NullPointerException
~~~

### Reading the Result Groups

**`prefix`:** Copying two elements replaces only the first two positions in the four-element destination. Size remains 4 and the `alias` variable still points to the same destination. Copying a single-element source `Z` next does not erase `B` or the trailing slots.

**`source.after`:** The independent source retains its original order and contents. The program did not swap the two arguments.

**`capacity` and `tooSmall`:** Capacity equal to the source length with size 0 is still insufficient. A one-element destination for a two-element source is also too short. Both size checks are separate from mutability errors.

**`readyTarget`:** An `ArrayList` created from initial slots has both enough positions and replacement support. `readonly.copy` and `nCopies.copy` have enough size but reject writes.

**`fixed.array`:** A fixed-size destination still accepts data because it allows replacing elements. The printed array line confirms the effect on the view's backing object.

**`fresh` and `append`:** One operation creates a new working copy, while the other appends the source to the existing destination. Neither has the same postcondition as `copy`'s prefix overwrite.

**`numbers`:** The generic signature allows an integer source into a `Number`-typed destination. The trailing `2.5` remains.

**`boxes`:** Source and destination hold the same element, confirmed by element reference comparison in the experiment. Modifying `count` shows up across both the constructor-created copy and the unmodifiable list. Replacing the destination slot with a new `Box` changes only the destination's slot.

**`nullable`:** A `null` element is accepted into `ArrayList`, whereas the `List.copyOf` factory rejects a source containing `null`. Mutability and element policy are separate contracts.

**`window` and `overlap`:** The destination view replaces the exact subrange of the original list. The overlapping case uses a separate source snapshot, so it writes the exact chosen original data.

**`linked`:** The destination does not have to be an `ArrayList`; a `LinkedList` with enough positions and replacement support works too. This line checks content, not timing.

**`emptySource` and the `null` lines:** An empty source does not clear the destination; missing the source or destination object itself is reported via an exception.

## 10. Application and Cost

### Choose `copy` When an Existing Destination Is Part of the Requirement

If you already have a range of positions to update and must preserve the destination object, `Collections.copy` makes direct sense. Keeping the rest of the destination intact is a guarantee that should be used intentionally.

If you just create a new destination with dummy slots and then copy solely to return a new list matching the source, `new ArrayList<>(source)` usually expresses the intent more clearly. There is no need to optimize with a complex preparation sequence when there is no requirement to preserve the destination.

### Shorter Data Than Last Time Requires a Tail-Handling Rule

Suppose a destination is used for a batch of three results and the next batch has only one result. Copying the second batch will not automatically erase the two old slots.

You can design a fixed-length buffer and separately track the count of slots holding valid data. Or you may need to replace the entire list and size to reflect the new result batch accurately. Those are two different models; do not let an accidental tail dictate production behavior.

If you want to clear and re-add on the same list, you must know whether the destination supports those structural operations and who observes intermediate states. That is not an automatic variant of `Collections.copy`.

### Work Scales with the Number of Source Elements

`Collections.copy` is documented as running in linear time. For standard lists and typical access/replace operations, transferring `n` elements handles `n` reference values.

No element cloning is needed to fulfill this contract. If you add a transformation or deep-copy step for your model, that cost is separate work.

List classes have different access characteristics. `ArrayList` has constant-time positional access; `LinkedList` must traverse nodes for indexed access. Do not replace the utility with a manual `get(i)`/`set(i)` loop and assume every list type has the same cost. [ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html), [LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html).

For custom lists with expensive reads or writes, you must consider the cost of the operations they provide. The API name does not eliminate the cost of the destination or source.

## 11. How to Verify a `copy` Call

First, write down the desired state of the destination after the operation. If the goal is "append data," "create a new list," or "shrink the destination to match the source," recognize that those are not postconditions of `Collections.copy`.

Then check the details that actually matter:

1. Are the two arguments in the right destination–source order?
2. Does the destination already have at least `source.size()` actual elements?
3. Does the destination allow replacing elements and accept the source values?
4. Does keeping the trailing portion match the requirements?
5. Do the source and destination share a backing store or get modified by another party during the operation?
6. Does sharing element objects match the required ownership?

In tests, do not compare only the prefix. Test with a destination longer than the source to catch misunderstandings about the tail and size; test capacity-only lists to catch capacity confusion; test fixed-size modifiable lists and unmodifiable lists to separate replacement permission from resizing capability.

If the data contains mutable objects, test mutating an element separately from replacing a slot. Those two operations express two different relationships and are often conflated under the word "copy."

## 12. Practice with Answers

### Exercise 1 — Source of Two, Destination of Four

Destination is `[p, q, r, s]`, source is `[A, B]`. Both are independent lists, and the destination supports replacement.

**Question:** After copying, what are the destination and its size? Is the source consumed or emptied?

**Answer:** The destination is `[A, B, r, s]`, and its size remains 4. The source still has `A` and `B`; copying does not remove elements from the source. The last two positions stay unchanged because they are outside the written range.

### Exercise 2 — Capacity Allocated, Yet Still Fails

~~~java
List<Integer> source = List.of(10, 20, 30);
List<Integer> destination = new ArrayList<>(3);
Collections.copy(destination, source);
~~~

**Question:** Which condition is not met? Does `ensureCapacity(100)` fix it?

**Answer:** The destination has size 0; it does not have three actual elements yet. Capacity and `ensureCapacity` do not increase size, so they do not satisfy the condition. If you need to copy into existing slots, create enough elements first. If you only want a new list, use `new ArrayList<>(source)`.

### Exercise 3 — Enough Slots, Yet Cannot Write

The destination is created with `Collections.nCopies(3, 0)` and the source is `List.of(1, 2, 3)`.

**Question:** Is having enough size sufficient for the copy to succeed? How can you create a three-slot modifiable destination?

**Answer:** No. An `nCopies` list does not support replacement, so copying actual data into it is rejected with `UnsupportedOperationException`. You can use `new ArrayList<>(Collections.nCopies(3, 0))` to have both the slots and mutability. You should still use the source constructor if the goal is simply a new copy matching the source.

### Exercise 4 — Array-Backed List

~~~java
String[] array = {"x", "y", "z"};
Collections.copy(Arrays.asList(array), List.of("A", "B"));
~~~

**Question:** What does the array become? Why isn't a list that supports adding required?

**Answer:** The array becomes `[A, B, z]`. The view allows replacing existing slots and writes into the same array; there is no size-increasing step. The element `z` remains unchanged because the source only has two elements.

### Exercise 5 — `copy` or `addAll`?

Initial destination is `[old, tail]`, source is `[A, B]`.

**Question:** Compare the results of `Collections.copy(dest, src)` and `dest.addAll(src)` when executed separately from the same initial state.

**Answer:** `copy` yields `[A, B]` with size 2. `addAll` yields `[old, tail, A, B]` with size 4. One replaces existing positions; the other adds new positions. They cannot be swapped without considering the business goal.

### Exercise 6 — Sharing Elements

The source has a `Box` with `count` 1. Copy into a separate destination list and then change `source.get(0).count` to 5.

**Question:** What `count` does the destination see? If you then call `dest.set(0, new Box("other", 9))`, does the `Box` in the source automatically become `other`/`9`?

**Answer:** The destination initially sees `count` 5 because it holds the same `Box`. Replacing the destination slot with a new `Box` does not change the reference in the independent source slot; the source still holds the old `Box` with `count` 5. To get independent elements, you need a strategy for creating or copying `Box`, not just copying the list.

### Exercise 7 — Writing a Middle Range with Overlap

The list is `[A, B, C, D, E]`. You need to move the **original** data at indices 0–2 to indices 1–3.

**Question:** What approach avoids having the source reads altered by the destination writes? What is the expected result?

**Answer:** Create `new ArrayList<>(values.subList(0, 3))` first, then copy from that snapshot into `values.subList(1, 4)`. The result is `[A, A, B, C, E]`. Do not assume two overlapping views automatically have snapshot semantics for the original source.

### Exercise 8 — Three APIs That All Have "copy" in the Name

A source list contains a `null` element and another mutable object. Consider `Collections.copy(dest, src)`, `new ArrayList<>(src)`, and `List.copyOf(src)`.

**Question:** Which API requires an existing destination? Which API rejects `null`? Do any of the three automatically deep-clone the mutable object?

**Answer:** `Collections.copy` requires a destination with enough size that supports replacement; whether `null` is accepted also depends on the destination's contract. The `ArrayList` constructor creates a new modifiable list and can hold `null`. `List.copyOf` rejects sources containing `null` elements. None of them automatically deep-clones mutable objects; that requires rules specific to your model.

When reading `Collections.copy`, think of replacing a range of existing slots. Size, `set` permission, the trailing elements, and element sharing are the decisive details; the word "copy" does not carry a promise of allocating a new list, resizing, or deep copying.
