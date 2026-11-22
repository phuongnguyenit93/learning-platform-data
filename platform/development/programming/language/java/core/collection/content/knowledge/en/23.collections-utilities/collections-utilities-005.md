# fill and nCopies: Replacing Elements vs. Creating a List

## 1. Two Similar-Looking Needs, Different Operations

One list already has five statuses and needs all of them set to "pending". Another list does not exist yet and needs five initial positions holding the same value right away. Externally, both results can look like five identical strings, but the operations are different:

- `Collections.fill(list, value)` **replaces the elements at existing positions in `list`**.
- `Collections.nCopies(n, value)` **returns a `List` of size `n` representing `n` repetitions of the same `value`**.

`fill` is an operation that mutates the passed-in list; `nCopies` is a factory method that returns a result for the caller to use. Do not treat the two names as interchangeable ways to write the same thing.

Another difference to know right away: `nCopies` does not create `n` new element objects. If `value` is a reference to a mutable object, every repeated position shares that same reference. `fill` also places the same single reference into every replaced position.

| Question | fill(list,value) | nCopies(n,value) |
|---|---|---|
| Primary input | An existing list | Number of positions needed and the repeated element |
| Effect | Replaces elements of the input list | Returns a result list |
| Return value | void | List<T> |
| Size after operation | Preserves the list's size | Equal to n if n is valid |
| Requires an input list that supports element replacement? | Yes, when replacement actually occurs | Does not take an input list |
| Can the result's structure or positions be modified? | Depends on the list passed in | The returned list is unmodifiable |
| Creates a new value object for each position? | No | No |

This lesson uses Java 17 or later and only the standard library. Three complete programs test replacing elements, creating repeated lists, and shared-reference behavior. Explanations regarding `null`, empty lists, and wrappers are all evaluated against the contract of the actual list implementation.

## 2. fill: Replacing All Existing Elements

### 2.1. Operates on size, not capacity

`Collections.fill` can be understood in effect as: for each index from `0` to `size - 1`, set the element at that index to `value`. This describes the semantics; the library is not required to literally use a `set(index, ...)` loop on every `List` type.

After completing on a normal valid list:

- `size` is unchanged.
- The existing positions remain in place.
- The element at each position is replaced with `value`.
- No new elements are added to increase the size.

`new ArrayList<>(5)` creates an empty `ArrayList` with an initial capacity suitable for holding data added later. It does not pre-populate five `null` elements.

Because `size` is still `0`, calling `fill` on this list does not create five positions. Capacity is internal storage capability; size is the number of elements currently present according to the API.

The [ArrayList(int)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#%3Cinit%3E(int)) documentation specifies that this constructor creates an empty list. [Collections.fill](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#fill(java.util.List,T)) specifies the operation of replacing elements in an existing list.

### 2.2. Requires set support, not necessarily add/remove support

A fixed-size list can still allow replacing elements. `Arrays.asList(array)` is an example: you cannot add or remove elements to change its size, but you can `set` elements and update the backing array.

Therefore, `fill` can succeed on `Arrays.asList`. Conversely, unmodifiable lists such as `List.of` or the `Collections.unmodifiableList` wrapper block element replacement through the list interface, so `fill` will be rejected when it needs to replace elements.

Distinguish two properties:

- **Cannot change size:** not enough to conclude that `set` is unsupported.
- **Cannot replace elements through the list:** does not satisfy `fill`'s update requirement.

`fill` returns `void`. Do not assign the call's result to a `List` variable expecting to receive a "filled list"; the input list itself is what was modified.

### 2.3. Null values depend on the target list's policy

`fill` has no general rule forbidding `null` like `List.of` does. If the target list permits `null` and supports replacing elements, you can use `fill(list, null)`.

If the target list or wrapper has other constraints, the operation must still obey those constraints. A `List` type does not guarantee that every implementation accepts every value.

Passing `null` for `list` itself is a different case: there is no list to update, and it is invalid. Do not confuse "the replacement element can be `null`" with "the target list can be `null`".

## 3. fill Program: Size, Arrays, and a List Range

File **FillExistingListDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class FillExistingListDemo {
    private static void expectUOE(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + ": no exception");
        } catch (UnsupportedOperationException expected) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        List<String> values = new ArrayList<>(List.of("A", "B", "C"));
        Collections.fill(values, "x");
        System.out.println("filled=" + values);
        System.out.println("size=" + values.size());
        Collections.fill(values, null);
        System.out.println("filledNull=" + values);

        List<String> capacityOnly = new ArrayList<>(5);
        Collections.fill(capacityOnly, "ready");
        System.out.println("capacityOnlySize=" + capacityOnly.size());
        System.out.println("capacityOnlyValues=" + capacityOnly);

        String[] array = {"red", "green", "blue"};
        List<String> fixedSize = Arrays.asList(array);
        Collections.fill(fixedSize, "gray");
        System.out.println("fixedSize=" + fixedSize);
        System.out.println("backingArray=" + Arrays.toString(array));

        List<String> parent =
                new ArrayList<>(List.of("a", "b", "c", "d"));
        Collections.fill(parent.subList(1, 3), "m");
        System.out.println("parentAfterRangeFill=" + parent);

        expectUOE("fillReadOnly",
                () -> Collections.fill(List.of("a", "b"), "x"));
        List<String> wrapped = Collections.unmodifiableList(
                new ArrayList<>(List.of("a", "b")));
        expectUOE("fillWrapped",
                () -> Collections.fill(wrapped, "x"));

        int[] numbers = {1, 2, 3};
        Arrays.fill(numbers, 7);
        System.out.println("primitiveArray=" + Arrays.toString(numbers));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 FillExistingListDemo.java
java FillExistingListDemo
```

Exact stdout:

```text
filled=[x, x, x]
size=3
filledNull=[null, null, null]
capacityOnlySize=0
capacityOnlyValues=[]
fixedSize=[gray, gray, gray]
backingArray=[gray, gray, gray]
parentAfterRangeFill=[a, m, m, d]
fillReadOnly=UnsupportedOperationException
fillWrapped=UnsupportedOperationException
primitiveArray=[7, 7, 7]
```

### 3.1. Filling does not increase size

`values` initially has three elements. After filling with `"x"`, it still has three elements. After filling with `null`, it still has three positions, each holding `null`.

`capacityOnly` was initialized with `new ArrayList<>(5)`, so it remains empty before and after `fill`. There is no error in this modifiable empty-list example, but no five `"ready"` values are created either.

If you want five positions ready upfront, you must add five elements by an appropriate method or create initial data of size five. `nCopies` is one option when the initial positions use the same value.

### 3.2. Filling an array-backed list updates the source array

`fixedSize` is a list view of `array`. `fill` replaces the three elements of `fixedSize` with `"gray"`, so `array` also shows `"gray"` in all three slots.

It does not create a new array and does not make the list an independent structure. If you need a separate list, you must copy it into a separate structure first.

[Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)) describes this array-backed relationship. Having a fixed size does not prevent replacing values in existing positions.

### 3.3. Filling a range using subList

`parent.subList(1, 3)` is a view of indices 1 and 2, excluding index 3. Calling `fill` on that view changes `parent` from `[a, b, c, d]` to `[a, m, m, d]`.

This uses a view to restrict which positions are replaced, rather than `fill` itself having `from`/`to` parameters. The validity rules of `subList` still apply: do not structurally modify the parent list outside the view's rules while using it.

### 3.4. For primitive arrays, use the array API

The program uses `Arrays.fill(numbers, 7)` for `int[]`. `Collections.fill` takes a `List`, not an `int[]` directly.

Also do not treat `Arrays.asList(intArray)` as a `List<Integer>` containing each number. A primitive array can become a single element of type `int[]` in a list due to how type arguments are passed; it is not automatically converted into individual `Integer` elements to be filled as a list of numbers.

`Arrays.fill` is the right tool for assigning values to the slots of a primitive array. That operation still does not increase the array's length.

## 4. nCopies: Creating a Repeated List Without Modifying an Existing One

### 4.1. Size is n, value at every position is the passed element

`Collections.nCopies(n, value)` returns a `List<T>` representing `n` occurrences of `value`.

- `n > 0`: list has `n` positions.
- `n == 0`: empty list.
- `n < 0`: `IllegalArgumentException`.
- `value` may be `null`.
- The result does not allow replacing elements or modifying structure through the list interface.

This is a valid list with repeated elements, not a `Set`, and it does not deduplicate. The word `copies` in the name is not a promise to call `clone` or the constructor of `value` multiple times.

If you need to replace positions later, create a modifiable list from that repeated data, such as `new ArrayList<>(Collections.nCopies(n, value))`.

### 4.2. A compact representation rather than building n separate objects

The [Collections.nCopies](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#nCopies(int,T)) documentation describes a compact representation that holds a single reference to the repeated object.

This makes it possible to represent many positions with the same element without creating `n` element objects. Distinguish the logical size of the `List` from the number of actual data objects created for its elements.

Reading `get(i)` at valid indices returns the same `value` / reference. Iterating through the entire list or copying it into an `ArrayList` still has to process `n` logical positions.

### 4.3. An unmodifiable list does not mean immutable elements

If `value` is a `String`, sharing the reference usually raises no concern about mutating the `String`'s content because `String` is immutable.

If `value` is a mutable `Box`, the caller can still retrieve the `Box` via `get` and mutate the `Box`'s fields. That is not calling `set` on the `List` and is not automatically blocked by the `List`.

This will be verified using reference comparisons and constructor call counts in the third program.

## 5. nCopies Program: Read-Only List and Modifiable Pre-Sized Copy

File **NCopiesListDemo.java**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class NCopiesListDemo {
    private static void expect(String label,
            Class<? extends RuntimeException> type, Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + ": no exception");
        } catch (RuntimeException failure) {
            if (!type.isInstance(failure)) {
                throw failure;
            }
            System.out.println(label + "=" + failure.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        List<String> repeated = Collections.nCopies(4, "x");
        System.out.println("repeated=" + repeated);
        System.out.println("size=" + repeated.size());
        System.out.println("zero=" + Collections.nCopies(0, "x"));
        System.out.println("nullable=" + Collections.nCopies(2, null));
        expect("negativeCount", IllegalArgumentException.class,
                () -> Collections.nCopies(-1, "x"));
        expect("setRepeated", UnsupportedOperationException.class,
                () -> repeated.set(0, "y"));
        expect("addRepeated", UnsupportedOperationException.class,
                () -> repeated.add("y"));
        expect("fillRepeated", UnsupportedOperationException.class,
                () -> Collections.fill(repeated, "y"));

        List<String> editable = new ArrayList<>(repeated);
        editable.set(0, "first");
        editable.add("tail");
        System.out.println("originalRepeated=" + repeated);
        System.out.println("editable=" + editable);

        List<String> slots =
                new ArrayList<>(Collections.nCopies(3, null));
        slots.set(1, "ready");
        System.out.println("initializedSlots=" + slots);

        List<String> appended = new ArrayList<>(List.of("prefix"));
        appended.addAll(Collections.nCopies(2, "v"));
        System.out.println("appended=" + appended);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 NCopiesListDemo.java
java NCopiesListDemo
```

Exact stdout:

```text
repeated=[x, x, x, x]
size=4
zero=[]
nullable=[null, null]
negativeCount=IllegalArgumentException
setRepeated=UnsupportedOperationException
addRepeated=UnsupportedOperationException
fillRepeated=UnsupportedOperationException
originalRepeated=[x, x, x, x]
editable=[first, x, x, x, tail]
initializedSlots=[null, ready, null]
appended=[prefix, v, v]
```

### 5.1. nCopies has a real size under the List API

`repeated` has `size` equal to 4 and reads out `"x"` four times. Calls to `set`, `add`, or `fill` attempting to modify elements in this list itself are rejected.

Do not use `nCopies` as a "pre-populated `ArrayList`" and call `set` directly on it. It already has logical positions, but the returned list does not grant update permission.

When `n == 0`, there are no elements. Do not use the behavior of no-op operations on an empty list to conclude that any list is modifiable: whether a no-op throws an exception still depends on the specific contract.

### 5.2. new ArrayList<>(nCopies(...)) separates structure, does not clone elements

`editable` is a new `ArrayList` with four `"x"` elements taken from `repeated`. It supports `set` and `add`, so it becomes `[first, x, x, x, tail]`. `repeated` still retains its four `"x"` positions as before.

The modifiable copy has its own structure, but the initial element objects are still copied references. With immutable `String` in this example, sharing does not change the content of `"x"`. With mutable objects, we will examine the effect in the next program.

### 5.3. Preparing empty slots that can be assigned later

`slots` is created with `new ArrayList<>(Collections.nCopies(3, null))`, so from the start it already has `size` equal to 3. Therefore, `slots.set(1, "ready")` is valid and replaces only the middle position.

This differs from `new ArrayList<>(3)`, which only prepares capacity and does not yet have index 1 available for `set`.

Here `null` is the value chosen to represent a slot without data yet. If the application does not use `null` for that state, you can choose another default value or a more explicit state model.

### 5.4. Using nCopies as a source for addAll

`appended` initially has `"prefix"`. `addAll(nCopies(2, "v"))` appends two `"v"` elements, increasing `size` from 1 to 3.

It is `addAll` that increases the target list's size; `nCopies` only supplies a source collection with two repetitions. Do not confuse this case with `fill`, which replaces existing elements and does not add positions.

## 6. Shared References: Neither fill Nor nCopies Clones Elements

### 6.1. A new expression is not re-evaluated per position

In `Collections.nCopies(3, new Box(1))`, the argument `new Box(1)` is evaluated to create **one** `Box` before calling `nCopies`. `nCopies` receives the reference to that `Box` and represents it at three positions.

Similarly, `Collections.fill(list, new Box(5))` receives one new `Box` created before the call and places that same reference into every replaced position. It does not invoke the `Box` constructor separately for each element.

To observe this, the following program has a constructor call counter. It also distinguishes mutating a `Box`'s state, replacing a reference in a list, and creating independent `Box` instances.

File **SharedRepeatedElementDemo.java**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class SharedRepeatedElementDemo {
    static final class Box {
        static int constructions;
        int value;

        Box(int value) {
            constructions++;
            this.value = value;
        }
    }

    private static List<Integer> values(List<Box> boxes) {
        return boxes.stream().map(box -> box.value).toList();
    }

    public static void main(String[] args) {
        Box.constructions = 0;
        List<Box> repeated = Collections.nCopies(3, new Box(1));
        System.out.println("nCopiesConstructions=" + Box.constructions);
        System.out.println("sameElement=" + (repeated.get(0) == repeated.get(1)));
        repeated.get(0).value = 9;
        System.out.println("repeatedAfterMutation=" + values(repeated));

        List<Box> editableCopy = new ArrayList<>(repeated);
        editableCopy.get(1).value = 10;
        System.out.println("originalAfterCopyMutation=" + values(repeated));
        editableCopy.set(0, new Box(7));
        System.out.println("copyAfterReplacement=" + values(editableCopy));
        System.out.println("originalAfterReplacement=" + values(repeated));

        List<Box> filled = new ArrayList<>();
        for (int i = 0; i < 3; i++) {
            filled.add(new Box(-1));
        }
        Box oldFirst = filled.get(0);
        Box.constructions = 0;
        Collections.fill(filled, new Box(5));
        System.out.println("fillConstructions=" + Box.constructions);
        System.out.println("fillSharesElement=" + (filled.get(0) == filled.get(1)));
        filled.get(2).value = 8;
        System.out.println("filledAfterMutation=" + values(filled));
        System.out.println("oldObjectStill=" + oldFirst.value);

        List<Box> independent = new ArrayList<>();
        for (int i = 0; i < 3; i++) {
            independent.add(new Box(0));
        }
        independent.get(0).value = 7;
        System.out.println("independent=" + values(independent));
        System.out.println("differentElements=" +
                (independent.get(0) != independent.get(1)));

        List<List<Integer>> sharedRows = new ArrayList<>(
                Collections.nCopies(2,
                        new ArrayList<>(Collections.nCopies(3, 0))));
        sharedRows.get(0).set(1, 9);
        System.out.println("sharedRows=" + sharedRows);
        System.out.println("sameRow=" + (sharedRows.get(0) == sharedRows.get(1)));

        List<List<Integer>> separateRows = new ArrayList<>();
        for (int row = 0; row < 2; row++) {
            separateRows.add(new ArrayList<>(Collections.nCopies(3, 0)));
        }
        separateRows.get(0).set(1, 9);
        System.out.println("separateRows=" + separateRows);
        System.out.println("differentRows=" +
                (separateRows.get(0) != separateRows.get(1)));

        Box.constructions = 0;
        List<Box> empty = Collections.nCopies(0, new Box(99));
        System.out.println("zeroCountSize=" + empty.size());
        System.out.println("zeroCountArgumentConstructions=" + Box.constructions);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SharedRepeatedElementDemo.java
java SharedRepeatedElementDemo
```

Exact stdout:

```text
nCopiesConstructions=1
sameElement=true
repeatedAfterMutation=[9, 9, 9]
originalAfterCopyMutation=[10, 10, 10]
copyAfterReplacement=[7, 10, 10]
originalAfterReplacement=[10, 10, 10]
fillConstructions=1
fillSharesElement=true
filledAfterMutation=[8, 8, 8]
oldObjectStill=-1
independent=[7, 0, 0]
differentElements=true
sharedRows=[[0, 9, 0], [0, 9, 0]]
sameRow=true
separateRows=[[0, 9, 0], [0, 0, 0]]
differentRows=true
zeroCountSize=0
zeroCountArgumentConstructions=1
```

### 6.2. Three positions, one Box

`nCopiesConstructions` is `1` and `sameElement` is `true`. Mutating `repeated.get(0).value` to `9` makes all three positions read `9` because all three return that exact same `Box`.

There are not three objects automatically synchronizing values with each other. There is just one object referenced by three logical positions.

The `repeated` list still forbids `set`/`add` through its interface. The printed values changing does not mean the list became structurally modifiable; the operation mutated the `Box` object held inside.

### 6.3. Copying into an ArrayList does not separate the Box

`editableCopy` has its own `ArrayList` structure, but upon creation it still holds three references to `repeated`'s `Box`.

`editableCopy.get(1).value = 10` mutates the shared `Box`, causing `repeated` to also read `[10, 10, 10]`. Then `editableCopy.set(0, new Box(7))` replaces only the reference at index 0 of the `ArrayList` copy.

The copy now shows `[7, 10, 10]`, while `repeated` still shows `[10, 10, 10]`. This is the difference between:

- Mutating the object a reference points to.
- Replacing the reference stored at a position in a list.

A separate structure does not mean every element is separate too.

### 6.4. fill replaces references, not old objects

`filled` initially holds three separate `Box` objects with `value` equal to `-1`. `oldFirst` still holds a reference to that first `Box`.

After `fill(filled, new Box(5))`, the list holds the same new `Box` at all three positions. Mutating `value` through the third position to `8` makes the entire list read `[8, 8, 8]`. Yet `oldFirst.value` is still `-1`.

Thus `fill` does not call a "reset" operation on each old `Box`. It replaces the list's elements with the new reference, while the old objects retain their state if anything else still references them.

If the real task is to update the state of each existing object, you need to call an update method on those objects according to their own policy. `fill` does not substitute for that.

### 6.5. n equal to 0 still evaluates the argument expression

`Collections.nCopies(0, new Box(99))` returns an empty list, yet `new Box(99)` is still evaluated once before the call. The counter is therefore `1` even though `zeroCountSize` is `0`.

This is Java's argument evaluation rule for method calls, not `nCopies` proactively creating an element and putting it into an empty list. Do not pass an expensive or side-effecting expression assuming "since `n` is 0, the object creation expression won't run".

The same applies to `fill` on an empty list: an argument expression such as `new Box(...)` is evaluated before the method executes, even when there are no positions to replace.

## 7. When Independent Elements or Rows Are Needed, Create Them at the Right Level

### 7.1. A new object must be created in each iteration that needs separation

In the `independent` section, `new Box(0)` is inside the loop, so there is a separate `Box` for each position. Mutating the first `Box` to `7` produces `[7, 0, 0]`.

This is the core difference from `nCopies(3, new Box(0))`: one invokes the constructor on every iteration, while the other evaluates the argument expression once.

If element creation is encapsulated in a method or `Supplier`, it still must actually return a distinct object per the application's contract. Calling a method multiple times does not guarantee independence if that method always returns a shared object.

### 7.2. The matrix trap with multiple rows sharing a reference

`sharedRows` is created from `nCopies(2, a row ArrayList)`. Wrapping the result in `new ArrayList` only creates a separate outer structure; both row positions still point to the same inner `ArrayList`.

Therefore, `sharedRows.get(0).set(1, 9)` makes both rows see `9` in column 1. `sameRow` being `true` is direct proof of the shared row reference.

`separateRows` places `new ArrayList<>(nCopies(3, 0))` inside a loop for each row, so each row has its own structure. Updating the first row does not affect the second row.

In the correct example, the cell values are immutable `Integer` objects. If the cells were mutable objects, creating separate rows only solves the row level; you must still decide whether each cell needs its own separate object.

There is no outer `new ArrayList` wrapper that automatically makes every data layer independent.

### 7.3. Sharing is not always a bug

Repeating an immutable value, a shared status token, or an object designed to be shared can match the requirement.

A bug occurs when the caller expects each position to have its own updatable state, yet creates multiple references to the same object. Therefore, before choosing `nCopies` or `fill`, ask: "Do the positions need the same value or the same single object?" and "Will any position mutate its own state later?"

## 8. Choosing an Operation by Purpose

| Purpose | How to express it |
|---|---|
| Replace every element of an existing list with the same value | Collections.fill(list,value) |
| Create a read-only list with n copies of the same element | Collections.nCopies(n,value) |
| Create a modifiable list pre-populated with n initial positions | new ArrayList<>(Collections.nCopies(n,value)) |
| Append a value n times to the end of an existing list | list.addAll(Collections.nCopies(n,value)) |
| Create n independent mutable objects | Create each object in a loop or via an element generator matching the contract |
| Replace each element using a function of the old element | List.replaceAll(operator), if the list supports it |
| Remove all elements so size becomes 0 | clear(), if the list supports it |
| Assign a value to array slots | Arrays.fill(...) |

### 8.1. fill is not clear followed by add

`clear` empties a list, making `size` equal to 0. `fill` preserves `size` and replaces elements at existing positions.

If you call `clear` and then `fill` on the newly emptied `ArrayList`, there are no positions left to fill. To increase `size` again, you must add elements using an appropriate operation.

### 8.2. fill differs from replaceAll in how values are computed

`fill` takes an already-evaluated object and uses that same object for the replaced positions.

`replaceAll` takes a function applied to each element according to `List`'s contract. It fits when the new value depends on the old element or when you need to invoke a creation operation per existing element.

However, `replaceAll` also does not create positions for an empty list. Nor does it guarantee that the function's results are distinct objects: the function can return the same reference multiple times.

The [List.replaceAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#replaceAll(java.util.function.UnaryOperator)) specification clearly separates this per-element transformation from `fill`'s assignment of a single element.

### 8.3. nCopies does not flatten or copy the contents of a collection passed as an element

If `value` itself is a `List`, `nCopies(n, value)` creates an outer list repeating references to that inner list. It does not extract the elements of `value` and create `n` deep copies.

Similarly, `List.of(Collections.nCopies(3, "x"))` is a list with one element—the inner list—not a way to directly create three `"x"` strings at the outer level.

When reading code with multiple generic layers, identify the element type of each layer before reasoning about size and independence.

## 9. Cost, Modifiability, and Practical Limits

### 9.1. fill traverses the positions to be replaced

The `fill` documentation describes linear time in the number of elements. For normal lists with appropriate update operations, it must process the existing positions rather than just changing a single metadata variable for the whole dataset.

Do not assume every `List` has the same actual cost for `set`. Types with special update mechanisms, such as making an internal copy on write, can have significantly different costs. Understand the target data structure before using `fill` on a hot path.

### 9.2. nCopies's compact representation does not make downstream operations cheap

`nCopies` represents a repeated element and a repetition count compactly. However:

- Iterating through or printing all `n` positions still has to process `n` positions.
- `new ArrayList<>(nCopies(n, value))` materializes an `ArrayList` structure holding `n` references.
- `addAll` into a target list makes the target list store the corresponding additional elements.
- The `value` object has its own creation cost, incurred when the application evaluates the argument.

Do not use the compactness of the repeated list to conclude that an `ArrayList` copied from it also needs only constant memory with respect to `n`.

### 9.3. Modifiability of the source or view still matters

`fill` on a view can modify the source data, as seen with `Arrays.asList` and `subList` in the first program. If a method is only supposed to have read access, it should not accept a writable view and treat `fill` as "editing a temporary copy".

Conversely, wrapping a source with `unmodifiableList` does not strip the source's owner of write access. `fill` through the wrapper is blocked; `fill` directly through the modifiable source reference can still update the data observed by readers.

### 9.4. Does not automatically close resources, destroy objects, or roll back on error

Replacing a reference in a list does not call `close` on the old resource, does not clear all state of the old object, and does not guarantee it is immediately garbage-collected. `oldFirst` in the program still held and could read the old `Box`.

`fill` is also not a transaction that guarantees rolling back all positions if an update operation on the target list fails. For a list with constraints or a custom implementation, understand its update policy and do not assume the source is untouched after an error.

When multiple threads read and write concurrently, a sequence of replacing multiple positions does not automatically become an atomic publication of the entire list. Appropriate coordination mechanisms or data models are needed if readers must observe a consistent version.

## 10. Common Mistakes

| Misconception | Common Consequence | Correct Understanding |
|---|---|---|
| ArrayList<>(n) already has n elements | fill creates no data; set at a presumed position fails | This constructor creates an empty list with initial capacity |
| fill increases size to the desired count | List keeps its old size | fill replaces existing positions |
| Fixed-size lists cannot be filled | Misses the Arrays.asList case which supports set | Replacing elements is different from adding/removing |
| nCopies returns a modifiable ArrayList | set/add/fill throws UnsupportedOperationException | Create a separate ArrayList if structural modification is needed |
| Copies means n cloned copies of the element | Mutating one object makes every position show the same value | Repeated positions share the same reference |
| Outer new ArrayList makes all elements independent | The copy still mutates the source's objects | Copying the structure copies the references |
| fill "resets" each old object | Holders of old objects do not see their state reset | fill replaces references in the list |
| Creating a matrix with nCopies of one row | Updating one row changes the other rows too | Create each row separately if independence is needed |
| n equal to 0 means the argument expression does not run | Constructor/side effect still happens | Arguments are evaluated before the call |
| Filling with null makes old objects disappear immediately | Other references still hold them | It only replaces the references at the list's positions |

Regarding `null` and repetition count, remember specifically: `nCopies` accepts a `null` element but rejects negative `n`. `fill` depends on the target list's element-replacement support and value policy.

Do not use a no-op operation on an empty list as a general test of whether a list is modifiable. The examples throwing `UnsupportedOperationException` in this lesson all use non-empty lists and operations that actually attempt to replace or add elements.

## 11. Exercises and Solutions

### Exercise 1 — Capacity is not elements

Create `List<String> a = new ArrayList<>(4)`, then call `fill(a, "x")`. How many elements does `a` have?

**Solution:** `0`. Initial capacity 4 creates no elements. `fill` does not increase `size`, so no positions are added.

### Exercise 2 — Creating positions for set

If you want an `ArrayList` pre-populated with four `null` positions and then set index 2 to `"ready"`, is `new ArrayList<>(4)` enough?

**Solution:** No. You can create `new ArrayList<>(Collections.nCopies(4, null))`, then call `set(2, "ready")`. The result has `size` 4. A list directly from `nCopies` has the right size but does not allow `set`, so a separate `ArrayList` is needed if you want to update it.

### Exercise 3 — Fixed-size list

`String[] a = {"a", "b"}; List<String> v = Arrays.asList(a)`. Does filling `v` with `"x"` necessarily fail because elements cannot be added? What happens to array `a`?

**Solution:** No. This view supports replacing elements despite having a fixed size. `fill` succeeds, and array `a` also has `"x"` in both slots.

### Exercise 4 — Creating n copies or one instance?

How many times does `Collections.nCopies(5, new Box(0))` invoke the `Box` constructor due to that `new` expression? If you mutate the `Box` retrieved at index 2, what do the other positions see?

**Solution:** The `new` expression creates one `Box`. Every position returns the same reference, so the other positions also read the `Box`'s new state after mutation.

### Exercise 5 — fill vs. mutating old objects

A list holds three distinct `Box` objects. A variable `outside` holds the first `Box`. After `fill(list, new Box(10))`, does `outside` automatically point to the new `Box` or have its `value` changed to `10`?

**Solution:** No. `fill` replaces the references at the list's positions. `outside` still points to the old `Box`, with its old state if nothing else mutates it.

### Exercise 6 — Copying a repeated list

`b = new ArrayList<>(Collections.nCopies(3, sharedBox))`. `b` has a modifiable structure. Does that make the three `Box` elements independent?

**Solution:** No. `b` has three separate positions in its `ArrayList` structure, but all three hold the same `sharedBox` reference. To have independent `Box` instances, you must create a separate object for each position as needed.

### Exercise 7 — Two-row matrix

Create one modifiable row `r`, then `new ArrayList<>(Collections.nCopies(2, r))`. If you call `get(0).set(1, 7)`, can the second row also show `7`?

**Solution:** Yes, because both row positions point to `r`. Creating an outer `ArrayList` does not deep-copy the rows. To make the two rows independent, create a new row inside a loop.

### Exercise 8 — Repetition count boundaries

What are the results of `nCopies(0, "x")`, `nCopies(-1, "x")`, and `nCopies(2, null)`?

**Solution:** Respectively: an empty list, `IllegalArgumentException`, and an unmodifiable list of two `null` elements.

### Exercise 9 — n equal to 0 and argument evaluation

Does `nCopies(0, createExpensiveObject())` guarantee that `createExpensiveObject` will not be called?

**Solution:** No. Java evaluates arguments before the call, so the method is still called once. `nCopies` simply receives the result of that call and a repetition count of `0`.

### Exercise 10 — Choosing the right operation

You already have a three-number list `[1, 2, 3]`. You need to replace it with `[0, 0, 0]` while keeping the size; another requirement is to append three `0`s to the end to make `[1, 2, 3, 0, 0, 0]`. What should you use in each case?

**Solution:** In the first case, use `fill` on a list that supports element replacement. In the second case, use `addAll(Collections.nCopies(3, 0))` on a list that supports adding. `nCopies` provides the repeated data, while `addAll` is what grows the target list.

### Exercise 11 — One outer list or three elements?

What is the outer `size` of `List.of(Collections.nCopies(3, "x"))`?

**Solution:** `1`. The single element is the inner list containing three `"x"` strings. There is no automatic flattening of nested lists in this call.

### Exercise 12 — Values based on the old element

You already have a list of numbers and need each new number to be twice the old number. Does `fill` with a single value satisfy this?

**Solution:** It does not express per-element transformation. You can use `replaceAll` with the appropriate function if the list supports element replacement, or create a new result according to the desired contract. `fill` uses the same argument object for every position rather than computing from each old element.

## 12. References

- [Collections.fill — replacing list elements](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#fill(java.util.List,T)).
- [Collections.nCopies — list repeating a single object](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#nCopies(int,T)).
- [ArrayList — size, capacity, and constructors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).
- [Arrays.asList and Arrays.fill](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html).
- [List — set, replaceAll, and subList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html).
