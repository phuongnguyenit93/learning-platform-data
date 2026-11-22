# Arrays.asList and Array-Backed Fixed-Size Lists

## 1. A List View Directly Into Array Slots

An API already has a `String` array, while another processing step expects a `List`. If the goal is to work with the elements currently in the array without increasing or decreasing the number of positions, `Arrays.asList` provides a suitable bridge.

The key point to understand from the start is that **the returned List is backed by the underlying array**. When you pass a compatible reference array to the method, the elements are not automatically copied into an independent `ArrayList` container. The `List` is a view that allows accessing the data through the `List` interface.

You can picture an array with three slots: slot 0, slot 1, and slot 2. Array access uses `array[index]`; view access uses `list.get(index)` or `list.set(index, value)`. Both still operate on the element slots of the same backing array.

Two characteristics must be kept separate:

- **Fixed size:** The `List` has a number of positions matching the array's length and does not support operations that change the number of positions.
- **Elements can be replaced:** Placing a different reference into an existing position is still supported as long as it satisfies the array's type constraint.

Therefore, fixed size does not mean read-only, nor does it mean immutable. This distinction affects write permissions, data copying, parameter passing, and how you choose a `List` for the next processing step.

This lesson starts with the bidirectional relationship between the array and the view, then verifies which operations are supported. After that, it examines varargs, primitive arrays, copy choices, and array type constraints. You should already be familiar with references, arrays, `List`, `get`/`set`, and basic exceptions.

All programs are self-contained and use Java 17; file names, compile commands, and stdout are recorded with each program. The examples use only the Java standard library.

## 2. The Contract of Arrays.asList

The method signature is `static <T> List<T> asList(T... array)`. The varargs syntax allows passing a compatible array or multiple element arguments; the result implements the `List` interface.

| Property | Practical Meaning |
| --- | --- |
| Ordering | Follows the positions of the argument array |
| Size | Fixed to the number of elements in the argument array |
| Relationship to array | Replacing an element on one side is visible on the other |
| Replacing elements | Yes, within valid index bounds and storage type |
| Adding/removing positions | Not supported |
| Null elements | Allowed in a reference array |
| Null input array itself | Not a valid input |
| Return type | `List`; not guaranteed to be `java.util.ArrayList` |

The method does not deduplicate. If the array has the same value at multiple positions, the `List` still has each corresponding position. A valid empty array produces an empty `List` with a fixed size of 0.

Indices used in `get`/`set` still run from `0` to `size - 1`. "Disallowing size changes" does not make out-of-bounds indices valid. A three-element `List` only has positions 0, 1, and 2 available for replacing elements.

Do not cast the result to `java.util.ArrayList` to gain `ArrayList` capabilities. The returned contract is a `List` with the behavior described above. When you need an independent `ArrayList`, create it using the constructor that takes a `Collection`.

Official documentation: [Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)). The "array-backed" behavior is an essential part of the contract, not an accidental detail discovered in a debugger.

## 3. Experiment: Replacing Elements in Both Directions

Save as `ArrayBackedViewDemo.java`:

```java
import java.util.Arrays;
import java.util.List;

public class ArrayBackedViewDemo {
    public static void main(String[] args) {
        String[] source = {"red", "green", "blue"};
        List<String> view = Arrays.asList(source);

        String old = view.set(1, "lime");
        System.out.println("old=" + old);
        System.out.println("arrayAfterSet=" + Arrays.toString(source));

        source[2] = "navy";
        System.out.println("viewAfterArrayEdit=" + view);
        System.out.println("size=" + view.size());

        source = new String[]{"new"};
        System.out.println("reassignedVariable=" + Arrays.toString(source));
        System.out.println("viewStillOnOriginal=" + view);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ArrayBackedViewDemo.java
java ArrayBackedViewDemo
```

Stdout:

```text
old=green
arrayAfterSet=[red, lime, blue]
viewAfterArrayEdit=[red, lime, navy]
size=3
reassignedVariable=[new]
viewStillOnOriginal=[red, lime, navy]
```

The call `view.set(1, "lime")` replaces the second slot and returns the old element `green`. The `source` array immediately has `lime` at that position. Next, assigning `navy` to `source[2]` is observed through `view` without calling `Arrays.asList` again.

Both edits take effect in opposite directions for the same reason: the array and the `List` both provide access paths to the element slots of the backing array. There is no manual data synchronization step in the program.

The final section reassigns the `source` variable to a new array with only one element. The view still displays the three elements of the original array. You must distinguish between:

| Operation | What Changes? |
| --- | --- |
| `source[2] = "navy"` | A slot in the array that `source` points to |
| `source = new String[]{"new"}` | The reference value of the `source` variable itself |

Reassigning the variable does not modify the old array and does not switch the view to the new array. The view maintains its link to the array object passed at creation time; it does not track the caller's local variable.

As long as the original array remains reachable through the view, it is still the data object in use even if the source variable has been redirected. This also helps explain why creating a view is not a copy operation that protects data from external references.

## 4. Fixed Size Still Allows Many Modification Operations

`set` replaces an element at an existing position, so it does not need to change the array's length. Several other operations also only need to replace or rearrange references within existing positions.

For example, sorting changes the order without creating additional positions. `List.replaceAll` uses the result of a function to replace each element, which also does not require increasing the size. `ListIterator.set` replaces the element most recently returned by the iterator.

In contrast, adding a new element, removing an existing element, or clearing a non-empty `List` all require changing the number of positions. A `List` from `Arrays.asList` does not support these requests.

Save as `FixedSizeOperationsDemo.java`:

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.ListIterator;
import java.util.Locale;

public class FixedSizeOperationsDemo {
    public static void main(String[] args) {
        List<String> values = Arrays.asList("C", "A", "B");
        ListIterator<String> cursor = values.listIterator();
        cursor.next();
        cursor.set("D");
        System.out.println("afterIteratorSet=" + values);

        values.sort(Comparator.naturalOrder());
        System.out.println("afterSort=" + values);
        values.replaceAll(value -> value.toLowerCase(Locale.ROOT));
        System.out.println("afterReplaceAll=" + values);

        try {
            values.add("E");
        } catch (UnsupportedOperationException e) {
            System.out.println("add=UnsupportedOperationException");
        }
        try {
            values.remove(0);
        } catch (UnsupportedOperationException e) {
            System.out.println("remove=UnsupportedOperationException");
        }
        try {
            values.clear();
        } catch (UnsupportedOperationException e) {
            System.out.println("clear=UnsupportedOperationException");
        }
        System.out.println("afterAttempts=" + values);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 FixedSizeOperationsDemo.java
java FixedSizeOperationsDemo
```

Stdout:

```text
afterIteratorSet=[D, A, B]
afterSort=[A, B, D]
afterReplaceAll=[a, b, d]
add=UnsupportedOperationException
remove=UnsupportedOperationException
clear=UnsupportedOperationException
afterAttempts=[a, b, d]
```

The iterator retrieves the first element and replaces `C` with `D`. Then the `List` is sorted into `A, B, D` and the strings are converted to lowercase. These operations succeed because they only modify the contents of existing positions.

The next three cases explicitly request a size change, so all three are rejected. After those attempts, the contents remain `a, b, d`. Catching exceptions here helps the program observe multiple cases; it is not a strategy for real APIs to guess write permissions by trial and error.

Do not conclude that every method with `remove` in its name always produces the same result regardless of arguments. A call that does not find a target might not need to change the size. To test removal capability, pick an item that actually exists, as this program does.

Also, do not treat the ability to sort or replace elements as isolated from the source: if the `List` is backed by another component's array, those transformations will mutate that component's own data.

## 5. Varargs Determines Which Array Backs the List

The signature `asList(T... array)` uses a variable-arity parameter. When passing several separate arguments such as two `String`s, Java prepares an argument array containing those `String`s. The view is still fixed-size even though the caller did not explicitly declare an array variable.

When passing a `String[]` to a call where `T` is `String`, that `String[]` itself is the matching argument array; the `List` has each `String` as an element. If you explicitly specify `T` as `String[]`, then a single element is the entire `String[]`, while the varargs array sits one level higher.

Primitive arrays introduce another distinction: `int[]` is an array object, but it is not an `Integer[]`. Java does not automatically box an entire `int[]` into an `Integer[]` to create a `List` of individual numbers.

Save as `AsListArrayShapesDemo.java`:

```java
import java.util.Arrays;
import java.util.List;

public class AsListArrayShapesDemo {
    public static void main(String[] args) {
        List<String> fromArguments = Arrays.asList("left", "right");
        System.out.println("fromArguments=" + fromArguments);

        String[] words = {"sun", "moon"};
        List<String> wordView = Arrays.asList(words);
        List<String[]> oneArray = Arrays.<String[]>asList(words);
        System.out.println("wordCount=" + wordView.size());
        System.out.println("arrayCount=" + oneArray.size());
        System.out.println("sameArray=" + (oneArray.get(0) == words));

        int[] raw = {10, 20};
        List<int[]> primitiveView = Arrays.asList(raw);
        System.out.println("primitiveListSize=" + primitiveView.size());
        System.out.println("samePrimitiveArray=" + (primitiveView.get(0) == raw));
        raw[0] = 99;
        System.out.println("primitiveElement="
                + Arrays.toString(primitiveView.get(0)));

        Integer[] boxed = {10, 20};
        List<Integer> boxedView = Arrays.asList(boxed);
        System.out.println("boxedListSize=" + boxedView.size());
        System.out.println("boxedView=" + boxedView);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 AsListArrayShapesDemo.java
java AsListArrayShapesDemo
```

Stdout:

```text
fromArguments=[left, right]
wordCount=2
arrayCount=1
sameArray=true
primitiveListSize=1
samePrimitiveArray=true
primitiveElement=[99, 20]
boxedListSize=2
boxedView=[10, 20]
```

The output should be read in terms of the type of **one List element**:

| Variable | Element Type | Number of Elements in Example |
| --- | --- | --- |
| `fromArguments` | `String` | Two |
| `wordView` | `String` | Two |
| `oneArray` | `String[]` | One |
| `primitiveView` | `int[]` | One |
| `boxedView` | `Integer` | Two |

The call `Arrays.<String[]>asList(words)` explicitly keeps `words` as a single array element. The line `sameArray=true` confirms that no deep copy of `words` was created.

For `raw`, the `List` has one element which is the `int[]` itself, so `primitiveListSize` is one, not two. Modifying `raw` at index 0 is visible when reading the array retrieved from the `List` element. The `Integer[]` at the end matches a sequence of `Integer` elements, so the `List` has two separate positions.

If you need a `List<Integer>` from an `int[]`, you need a step that extracts each value and boxes it appropriately. Do not use a cast to assume `int[]` is already an `Integer[]`, and do not predict the size merely by counting braces in the source data.

When a `List` contains arrays, use `Arrays.toString` on the element array to inspect the values inside. The default string representation of an array object does not prove that the numbers were converted into individual `Integer` elements.

## 6. Creating a Copy When You Need to Decouple the Container from the Array

There are three common requirements when starting from an `Arrays.asList` view:

1. You need an independent `List` that supports adding and removing.
2. You need a read-only snapshot that does not follow subsequent array slot updates.
3. You only want to block modifications through one `List` reference while still seeing live updates from the source.

These requirements are different. The constructor `new ArrayList<>(view)` creates a separate container and allows resizing. `List.copyOf(view)` freezes the data into an unmodifiable `List` container, provided there are no `null` elements. `Collections.unmodifiableList(view)` only blocks writes through the wrapper; the underlying view remains linked to the array.

Save as `AsListCopyChoicesDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class AsListCopyChoicesDemo {
    public static void main(String[] args) {
        String[] source = {"one", "two"};
        List<String> view = Arrays.asList(source);
        List<String> editableCopy = new ArrayList<>(view);
        List<String> snapshot = List.copyOf(view);
        List<String> readOnlyView = Collections.unmodifiableList(view);

        view.set(0, "changed");
        editableCopy.add("three");
        System.out.println("view=" + view);
        System.out.println("editableCopy=" + editableCopy);
        System.out.println("snapshot=" + snapshot);
        System.out.println("readOnlyView=" + readOnlyView);
        System.out.println("source=" + Arrays.toString(source));

        StringBuilder[] builders = {new StringBuilder("draft")};
        List<StringBuilder> shallowCopy =
                new ArrayList<>(Arrays.asList(builders));
        builders[0].append("-edit");
        System.out.println("sharedElement=" + shallowCopy.get(0));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 AsListCopyChoicesDemo.java
java AsListCopyChoicesDemo
```

Stdout:

```text
view=[changed, two]
editableCopy=[one, two, three]
snapshot=[one, two]
readOnlyView=[changed, two]
source=[changed, two]
sharedElement=draft-edit
```

The copies and wrappers are created before `view` replaces its first element. After the replacement:

- `view` and `source` both have `changed` at the first position.
- `editableCopy` keeps `one, two`, and allows appending `three` to its own container.
- `snapshot` keeps `one, two`.
- `readOnlyView` shows `changed, two` because the wrapper reads through the array-backed view.

Whether writes are allowed through a particular access path and whether the data tracks the source are two independent dimensions. You cannot use a rejected `add` call to prove that the source can no longer change the contents seen by the receiver.

The `StringBuilder` at the end of the program illustrates another limit. The new `ArrayList` separates the reference-holding slots from the original array, but still holds the same `StringBuilder`. The content `draft-edit` is observed in the copy because the element object itself is still shared.

Therefore, an "independent copy" in this context is primarily a copy of the container. If you also need element state to be independent, choose immutable elements or an appropriate element transformation/copying strategy for your data model.

One way to create a `List` that remains fixed-size while decoupling its slots from the source array is to copy the array first and then take a view over the new array. That approach still does not deep-copy element objects. You do not have to turn every requirement into an `ArrayList` if the actual requirement is simply a separate fixed-size sequence of slots.

Compare the add/remove capabilities of [ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html) and the snapshot contract of [List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)) when choosing the result you need.

## 7. Nulls and Runtime Array Type Remain Constraints

`Arrays.asList` accepts `null` elements inside a reference array. That is different from passing `null` as the array itself. You must be explicit about which data layer you are referring to.

In addition, Java arrays retain their actual component type at runtime. A `Number[]` variable may be referencing an `Integer[]` object. Deriving a `List` interface from the array variable's declared type does not remove the backing array's type check when writing elements.

Save as `AsListTypeConstraintsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class AsListTypeConstraintsDemo {
    public static void main(String[] args) {
        List<String> nullable = Arrays.asList("A", null);
        nullable.set(0, null);
        System.out.println("nullable=" + nullable);
        System.out.println("oneNullSize="
                + Arrays.asList((String) null).size());
        try {
            Arrays.asList((String[]) null);
        } catch (NullPointerException e) {
            System.out.println("nullArray=NullPointerException");
        }

        Integer[] storage = {1, 2};
        Number[] wider = storage;
        List<Number> numberView = Arrays.asList(wider);
        numberView.set(0, 3);
        System.out.println("afterInteger=" + Arrays.toString(storage));
        try {
            numberView.set(1, 2.5);
        } catch (ArrayStoreException e) {
            System.out.println("doubleStore=ArrayStoreException");
        }
        System.out.println("afterRejectedStore=" + Arrays.toString(storage));

        List<Number> independent = new ArrayList<>(numberView);
        independent.set(1, 2.5);
        System.out.println("independent=" + independent);
        System.out.println("storage=" + Arrays.toString(storage));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 AsListTypeConstraintsDemo.java
java AsListTypeConstraintsDemo
```

Stdout:

```text
nullable=[null, null]
oneNullSize=1
nullArray=NullPointerException
afterInteger=[3, 2]
doubleStore=ArrayStoreException
afterRejectedStore=[3, 2]
independent=[3, 2.5]
storage=[3, 2]
```

### 7.1. A Null Element Differs from a Null Array

The `nullable` list has two positions. The second position is already `null`, and the first position is set to `null`, resulting in two `null` elements. `Arrays.asList((String) null)` creates a `List` with one `null` element.

Meanwhile, `Arrays.asList((String[]) null)` passes a `null` array itself and throws an exception. Do not pass an untyped `null` and assume Java will treat it as "one `null` element"; write the type explicitly when you need to disambiguate your intent.

### 7.2. A Wider Declared Type Does Not Change the Created Array's Type

`storage` is an `Integer[]`. The `wider` variable has type `Number[]` yet still holds that same object. This is a feature of Java's array type system (array covariance), not a conversion from `List<Integer>` to `List<Number>`.

`numberView` is created via `wider` and has type `List<Number>`. When replacing with `3`, the `Integer` value fits the backing array and succeeds. When replacing with `2.5`, the `Double` value satisfies `Number` at compile time, but cannot be stored in the actual `Integer[]`; the write is rejected with an `ArrayStoreException`.

The independent `ArrayList<Number>` at the end has its own storage, so it can hold a `Double` without modifying `storage`. The program does not use raw types or `List` casts to produce this difference.

The key takeaway is: a `List` from `Arrays.asList` remains subject to the storage constraints of its backing array. If you need a separate `Number` container capable of holding other `Number` subtypes, create an appropriate container instead of assuming a wider variable declaration transformed the array.

The runtime check rules when writing to reference arrays are explained in [JLS 17, Array Store Exception](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html#jls-10.5).

## 8. When Should You Choose Arrays.asList?

`Arrays.asList` is useful when you already have an array and want to work with it through the `List` interface while accepting shared element slots. For example, a processing step needs to read via `List` or replace elements within a fixed-length sequence.

Determine three requirements up front:

1. Do you need to add or remove positions?
2. Do you want edits through the `List` to affect the array?
3. Do you also need to protect the state of element objects?

| Requirement | Suitable Container Choice | Additional Considerations |
| --- | --- | --- |
| Array-backed `List`, no position count changes | `Arrays.asList(array)` | `set` calls can modify the array |
| Independent `List` supporting add/remove | `new ArrayList<>(Arrays.asList(array))` | Elements may still be shared |
| Frozen read-only `List` from view | `List.copyOf(Arrays.asList(array))` | Rejects `null` elements; no deep copy |
| Block writes via `List` while tracking array | Unmodifiable wrapper over view | Array owner can still change observed data |
| Separate fixed-size sequence of slots | Copy array first, then create view on new array | Object elements still need their own policy |

If a method accepts a `List` and intends to call `add` or `remove`, passing `Arrays.asList` directly may not satisfy the requirement. Do not infer from the `List` type declaration that every optional operation is supported. The receiving method's contract should state the expected modification permissions.

If a method intends to sort or replace elements, a view can satisfy the operation capability, but it will mutate the caller's array. When you only want to compute a transformed result while preserving the original source, prepare a separate container.

If an API returns `Arrays.asList` over an internal array, the caller has a path to `set` elements in that array. The term "fixed-size" alone is not enough to call an output read-only. Conversely, wrapping it as unmodifiable does not promise fixed data if the owner continues to mutate the array.

You do not need to create a copy in every case. Sharing data may be the exact purpose of a view. What matters is documenting the relationship to the source accurately and not promising a level of independence that the implementation does not provide.

The programs in this lesson run on a single thread to make data relationships clear. Sharing elements between an array and a view does not automatically provide a synchronization mechanism when multiple threads read and write concurrently.

## 9. Diagnosing Bugs at the Right Data Layer

| Symptom | Cause to Check | Resolution |
| --- | --- | --- |
| Adding or removing an existing element is blocked | `List` has a fixed number of positions | Create a resizable container if needed |
| `set` through `List` changes the source array | Expected array-backed contract | Use a copy if you do not want to mutate the source |
| Reassigning array variable does not update old `List` | Variable changed reference; view still holds old array | Create a new view from the new array if intended |
| `int[]` produces a `List` with one element | Single element has type `int[]` | Convert each number if `List<Integer>` is needed |
| Calling with `null` throws instead of creating one `null` element | `null` is interpreted as the array argument | Specify the cast/type explicitly to express the right layer |
| Setting a `Double` via `List<Number>` throws `ArrayStoreException` | Actual backing array has a narrower component type | Choose an independent container supporting `Number` |
| Created a new `ArrayList` but element objects still change | Container copy still shares element references | Use immutable elements or copy/transform appropriately |
| Casting result to `java.util.ArrayList` fails | Implementation type is not promised by the contract | Work through `List` or construct a real `ArrayList` |

When investigating a bug, print or inspect both the array and the `List` before and after the operation. To distinguish a view from a copy, modify an array slot after creating the result and then read the result. To distinguish a shallow copy from state independence, test mutating an element object itself.

Do not rely solely on a class name seen in a debugger or an identity comparison. A different `List` object can still be a view over the same array. A new `ArrayList` with its own storage can still hold shared element objects.

For operations that require changing size, test a case that actually causes a change. Calling `remove` with a non-existent value or running on empty data does not prove that a `List` allows element removal.

## 10. Practice: Predict and Verify

### Exercise 1: Track Both Modification Paths

Create an array `[north, south]` and a `List` view. Replace index 0 with `east` through the `List`, then replace index 1 with `west` through the array.

Success criteria: both ways of reading show `east, west`; the `List` size remains 2. Explain this in terms of the array slots, not as a data-copying step between two objects.

### Exercise 2: Reference Variable vs. Array Object

After creating a view over a two-element array, reassign the array variable to a new array with three elements.

Predict the size of the old view and verify it. The old view still has two positions because it remains linked to the original array. To view the new array as a `List`, you must create a new result from the new array.

### Exercise 3: Choose the Right Modification Permission

A method needs to add an item to the `List` it receives. The caller currently has a `String[]` and uses `Arrays.asList`.

Choose how to prepare the input so the method can add an item without changing the slot count of the original array. A separate `ArrayList` constructed from the view supports adding; explain that this is a separate copy of the container.

### Exercise 4: Individual Numbers or an Array of Numbers?

Given an `int[]` of three numbers, predict the element type and size when calling `Arrays.asList` on that array. Compare this with an `Integer[]` that also has three numbers.

Success criteria: `int[]` creates a single array element in the `List` of the corresponding call; `Integer[]` creates separate `Integer` positions. Do not use a cast to treat both array types as identical.

### Exercise 5: Does Read-Only Track the Source?

From the same view, create an unmodifiable wrapper and a `List.copyOf` with non-null data. Modify an array slot after creating both.

Predict the outcome: the wrapper still sees the new value through the view; the snapshot keeps the values captured at creation time. Explain that both block writes through the `List`, but their relationships to the source differ.

### Exercise 6: Elements with Mutable State

An array contains a `StringBuilder`. Create a new `ArrayList` from `Arrays.asList` of the array, then modify the `StringBuilder` using `append`.

Success criteria: recognize that the new container does not automatically clone the builder. Propose converting to `String` or an appropriate value type if the output needs to keep stable text content.

### Exercise 7: Runtime Array Type

An `Integer[]` is held through a `Number[]` variable and used to create a `List<Number>`. Try replacing one position with an `Integer` and another position with a `Double`.

Success criteria: distinguish compile-time type checking on the Java call from runtime component-type checking when storing into the array. Compare with an independent `ArrayList<Number>` to explain the cause of `ArrayStoreException`.

## 11. Self-Check Questions

1. **Does `Arrays.asList` create a growable `ArrayList`?** No. It returns a fixed-size `List` backed by the argument array.
2. **Does fixed size forbid `set`?** No. Existing positions can still have their elements replaced if the index and storage type are valid.
3. **Are array edits made after creating the view visible in the `List`?** Yes, when editing the slots of that same backing array.
4. **Does reassigning the array variable switch the view's source?** No. The view remains linked to the old array object and does not track the variable.
5. **Does `int[]` automatically become `List<Integer>`?** No. You must account for varargs typing and convert each value individually if that is required.
6. **Are a `null` array and an array with a `null` element the same?** No. One lacks a valid array object, while the other is element data inside an array.
7. **How far does creating an `ArrayList` from the view protect you?** It separates the container so you can add/remove independently; element objects may still be shared.
8. **How do `List.copyOf` and an unmodifiable wrapper over the view differ?** One freezes the container's data, while the other continues to read through the array-backed view.
9. **Why can a `List<Number>` still fail to store a `Double` in the example?** Because the actual backing array is an `Integer[]` and still enforces its component type on writes.
10. **What should a good API choice specify?** Element replacement permission, size-change permission, relationship to the source array, and the level of element-state independence.
