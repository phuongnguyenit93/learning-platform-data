# Comparing Arrays and Collections: Size, Types, and Operations

Arrays and collections can both manage multiple values, but they organize data and provide operations under different contracts. Choosing the right model helps avoid bugs such as treating reserve capacity as the element count, removing by index by mistake, or assuming a list backed by an array can grow on its own.

Three guiding questions for this lesson:

1. **Size:** Does the number of storage slots change, and how many elements are currently managed?
2. **Type:** Are the elements primitive values or objects; does type checking happen at compile time or at runtime?
3. **Operations:** Do you need positional access, adding, removing, searching, sorting, or converting between data forms?

The complete examples use the Java 17 API. They were compiled with `--release 17` and run to verify stdout.

## 1. Two Models to Picture

### Arrays: A Number of Slots Determined at Creation

Declaring `new String[3]` creates an array object with three slots. The slots are accessed by indices from `0` to `2`. That length is fixed for the entire lifetime of the array object.

The slots always exist after the array is created, even if you have not assigned your own data to them yet. Java initializes elements with the default value of their type:

| Element Type | Example Default Value |
| --- | --- |
| `int` | `0` |
| `boolean` | `false` |
| Reference types such as `String` | `null` |

If only two slots contain business-meaningful data, the program must distinguish "the array length is three" from "there are currently two valid records."

### Collections: A Group of Elements with an Operational Contract

`Collection<E>` is the common interface for many collection types in `java.util`. A collection reports its current number of elements via `size()`; the specific collection type defines ordering, duplicates, and supported operations.

When comparing directly with an indexed array, `List<E>` is the closest counterpart. `ArrayList<E>` is a list implementation class capable of changing its number of elements.

However:

- `Collection` is broader than `List`; a `Set` does not provide `get(index)`.
- A collection might not support adding or removing elements.
- `Map` belongs to the Java Collections Framework, but it does not extend `Collection`.

Therefore, the statement "a collection can change size" must be tied to the actual type and object. For a mutable `ArrayList`, that is true; for a list created with `List.of`, adding or removing is forbidden.

## 2. Foundational Comparison Table

| Criterion | Array | Collection |
| --- | --- | --- |
| Type examples | `int[]`, `String[]` | `Collection<String>`, `List<Integer>`, `Set<String>` |
| Count measure | The array's `length` field | The collection's `size()` method |
| Number of slots/elements | Fixed length of the array object | Number of elements can change if the object supports it |
| Primitive types | Can directly hold `int`, `double`, ... | Type parameters use reference types such as `Integer`, `Double` |
| Indexed access | `array[index]` | Available on `List` via `get(index)`, not on every `Collection` |
| Replace an element | Assign to a valid slot | `List.set` if supported |
| Add or remove elements | Manage data manually or create another array | Operations exist in the contract; mutability depends on the object |
| Duplicate rules | Slots can hold the same value | Depends on the collection type; `List` generally allows duplicates, `Set` enforces uniqueness per its rules |
| Operation tools | Array syntax and `java.util.Arrays` | Interface/class methods and appropriate utilities |
| Runtime type info | Arrays retain the actual element type | Generics are mainly checked at compile time, with type erasure |

The table does not mean one side is always better. For example, needing frequent add/remove operations is different from needing to store a block of integers with a known number of slots.

## 3. Size, Element Count, and Capacity

### Array Length Does Not Grow Automatically

Illustrative snippet inside a method:

```java
int[] scores = new int[3];
```

`scores.length` is `3`. Assigning `scores[0] = 10` only changes the data in one slot, not the length. Accessing `scores[3]` goes out of bounds and throws `ArrayIndexOutOfBoundsException`.

You can create a larger array with `Arrays.copyOf` and reassign the variable:

```java
int[] scores = {10, 20, 30};
scores = Arrays.copyOf(scores, 5);
```

This snippet requires `import java.util.Arrays;`. It creates **another array object** and makes the `scores` variable reference the new array. The original array object is not stretched. The two new slots of the integer array are filled with the default value `0`.

If another variable still references the old array, that variable still sees a three-element array.

### Size and Capacity of ArrayList Are Different

Given:

```java
List<String> values = new ArrayList<>(3);
```

- `3` is the initial reserve capacity requested for the backing storage structure.
- `values.size()` is still `0`.
- There is no element at index `0` yet.
- `values.set(0, "A")` will not create a new element; that index is not valid yet.
- `values.add("A")` is what adds the first element.

`ArrayList` manages an internal storage area. When needed, it can increase capacity and copy data over. Callers do not have to track the internal array themselves.

`Collection` does not provide a general capacity concept for all collection types. Nor should you rely on a specific growth factor when writing business logic.

### Complete Program

Create the file **`ArrayAndListDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class ArrayAndListDemo {
    public static void main(String[] args) {
        String[] unusedSlots = new String[3];
        String[] array = {"A", "B", "C"};
        List<String> list = new ArrayList<>(3);

        System.out.println("default array = " + Arrays.toString(unusedSlots));
        System.out.println("array.length = " + array.length);
        System.out.println("list.size before add = " + list.size());

        list.add("A");
        list.add("B");
        list.add("C");
        list.add("D");
        System.out.println("list.size after add = " + list.size());

        array[1] = "X";
        list.set(1, "X");
        list.remove("C");

        System.out.println("array = " + Arrays.toString(array));
        System.out.println("list = " + list);
        System.out.println("list.size after remove = " + list.size());
    }
}
```

Compile and run:

```text
javac -encoding UTF-8 --release 17 ArrayAndListDemo.java
java -Dfile.encoding=UTF-8 ArrayAndListDemo
```

Stdout:

```text
default array = [null, null, null]
array.length = 3
list.size before add = 0
list.size after add = 4
array = [A, X, C]
list = [A, X, D]
list.size after remove = 3
```

Observations:

1. The new array has three reference slots, all `null`.
2. The list that reserved space for three elements still starts with a size of zero.
3. After four `add` calls, the list holds four elements.
4. Assigning `array[1]` and calling `list.set(1, ...)` both replace an existing element.
5. `list.remove("C")` reduces the element count from four to three; the array still has length three.

The number `3` at the end of both models happens to be equal by coincidence, but the data mutation process and operational contract differ.

## 4. Element Types and Type Checking

### Arrays Can Directly Hold Primitive Values

```java
int[] quantities = {2, 4, 6};
String[] labels = {"small", "medium"};
```

These two lines illustrate a primitive array and a reference array.

With generics, declaring `List<int>` is invalid. We use the wrapper type:

```java
List<Integer> quantities = new ArrayList<>();
quantities.add(2);
```

The lines using `List` require the corresponding imports from `java.util`. An `int` value can be autoboxed into an `Integer` when added.

Consequences:

- `int[]` holds integer values directly.
- `List<Integer>` manages references to `Integer` objects.
- A list that allows `null` can contain an element that cannot be unboxed into an `int`.
- The memory model and overhead are not the same.

You should not convert a primitive array into a collection just for syntactic uniformity while ignoring these differences.

### Reference Arrays Are Covariant

In Java, you can assign a `String[]` to an `Object[]` variable:

```java
Object[] values = new String[1];
```

The variable is declared as `Object[]`, but the actual object is still `String[]`. When you assign an `Integer` into that array, Java checks the element type at runtime and throws `ArrayStoreException`.

Allowing assignment between array types based on subtype relationships is called **covariance**. It offers flexibility but requires runtime checks when storing elements.

### Generics Have Different Assignment Rules

The snippet below **intentionally does not compile**:

```java
List<Object> values = new ArrayList<String>();
```

`List<String>` is not a subtype of `List<Object>`. If this assignment were allowed, code using the `List<Object>` variable could add a non-string object to a list of strings.

Parameterized types like `List<T>` are **invariant** with respect to their type parameter. When an API needs to accept multiple element types, Java provides wildcards such as `? extends ...` or `? super ...`, with their own read/write restrictions. That is a type-design choice, not a reason to use raw types and bypass checking.

### Runtime Type Information Differs

- A `String[]` array retains its actual component type for store checks.
- A `List<String>` uses generics to verify most type usage at compile time.
- Using raw types or unsafe casts can break generic guarantees and cause `ClassCastException` when retrieving data.

Type erasure does not mean "generics are unsafe." It explains why you should preserve compile-time type checking and avoid unsafe operations.

## 5. Boxing and the Primitive Array Trap

`Arrays.asList` takes arguments of a reference type. An `int[]` is itself an object, so calling `Arrays.asList(intArray)` creates a list with **one element, which is the entire array**, rather than a list of boxed numbers.

The following program also demonstrates array type checking and `null` unboxing errors.

Create the file **`ArrayTypeDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class ArrayTypeDemo {
    public static void main(String[] args) {
        Object[] values = new String[1];
        try {
            values[0] = Integer.valueOf(7);
        } catch (ArrayStoreException exception) {
            System.out.println("array store: " + exception.getClass().getSimpleName());
        }

        int[] numbers = {2, 4, 6};
        List<int[]> oneArray = Arrays.asList(numbers);
        System.out.println("asList(int[]).size = " + oneArray.size());
        System.out.println("same array = " + (oneArray.get(0) == numbers));

        List<Integer> boxed = new ArrayList<>();
        for (int number : numbers) {
            boxed.add(number);
        }
        System.out.println("boxed = " + boxed);
        System.out.println("boxed.size = " + boxed.size());

        List<Integer> withNull = Arrays.asList(1, null, 3);
        try {
            int number = withNull.get(1);
            System.out.println(number);
        } catch (NullPointerException exception) {
            System.out.println("unboxing: " + exception.getClass().getSimpleName());
        }
    }
}
```

Compile and run:

```text
javac -encoding UTF-8 --release 17 ArrayTypeDemo.java
java -Dfile.encoding=UTF-8 ArrayTypeDemo
```

Stdout:

```text
array store: ArrayStoreException
asList(int[]).size = 1
same array = true
boxed = [2, 4, 6]
boxed.size = 3
unboxing: NullPointerException
```

Explanation:

1. The `String[]` object rejects storing an `Integer`, even though the variable has type `Object[]`.
2. `oneArray` has type `List<int[]>` and a size of `1`.
3. The sole element of the list is the reference to `numbers`.
4. The loop explicitly adds each `int` value to `List<Integer>`, creating three elements via boxing.
5. Retrieving `null` from `List<Integer>` and assigning it to an `int` variable requires unboxing, which triggers `NullPointerException`.

Choose the conversion approach based on the desired result. A "list of arrays" and a "list of numbers" are two different models.

## 6. Comparing Common Operations

For collections, the last column should be read with the right interface in mind: indexed operations belong to `List`, not every `Collection`.

| Purpose | Array | Appropriate Collection or List |
| --- | --- | --- |
| Count | `array.length` | `group.size()` |
| Check if empty | `array.length == 0` | `group.isEmpty()` |
| Get by position | `array[index]` | `list.get(index)` |
| Replace existing element | `array[index] = value` | `list.set(index, value)` if supported |
| Add element | Manage free slots manually or create a new array | `add`, or `List.add(index, value)` if supported |
| Remove by value | Find and reorganize data manually | `remove(value)` per contract |
| Check existence | Write a loop or use an appropriate utility | `contains(value)` |
| Iterate elements | `for`, `for-each` | `for-each`; iterator and mechanisms of the specific type |
| Sort in place | `Arrays.sort(array)` | `list.sort(comparator)` when supported |
| Display contents | `Arrays.toString(array)` for 1D arrays | Standard collection classes provide a `toString()` representation |
| Compare contents | `Arrays.equals(a, b)` for appropriate 1D arrays | Per the `equals` contract of the collection type |

### Replacing an Element vs. Adding an Element

With an array, assigning to a slot does not create a new slot. With a list, `set` replaces an element while `add` inserts/appends an element. The two operations are not interchangeable.

In an ordered list, adding or removing in the middle can also shift the indices of subsequent elements. When saving an index for later use, you must account for the possibility that the structure has changed.

### Removing Integer Elements Has Two Interpretations

`List<Integer>` can cause confusion between:

- `remove(int index)`: removes by index.
- `remove(Object value)`: removes by value.

Illustrative example inside a method:

```java
List<Integer> byIndex = new ArrayList<>(List.of(1, 2, 1));
byIndex.remove(1); // Remove the element at index 1: the value 2.

List<Integer> byValue = new ArrayList<>(List.of(1, 2, 1));
byValue.remove(Integer.valueOf(1)); // Remove one occurrence of the value 1.
```

Afterward, `byIndex` contains `[1, 1]`, while `byValue` contains `[2, 1]`. This difference comes from method overloading and argument types.

### Equality Rules Differ

Calling `a.equals(b)` on two arrays does not compare elements one by one like `Arrays.equals(a, b)`; arrays use object identity rules for `equals`.

For lists, the `List.equals` contract checks corresponding elements and order. For sets, the `Set.equals` contract checks membership according to set rules.

You should not assume a single content-based `equals` rule for every `Collection` type. Check the contract of the collection type you are using. For nested arrays, when deep comparison is needed, choose an appropriate utility such as `Arrays.deepEquals`.

## 7. From Array to List: View or Copy?

This is where the concepts of "fixed-size," "unmodifiable," and "data-independent" are often confused.

Suppose `source` is a `String[]` containing no `null` values:

| Creation Method | Add/Remove Elements | Replace Element via `set` | Relationship to Source Array |
| --- | --- | --- | --- |
| `Arrays.asList(source)` | No | Yes | View backed by the source array |
| `new ArrayList<>(Arrays.asList(source))` | Yes | Yes | List structure is copied |
| `List.copyOf(Arrays.asList(source))` | No | No | Snapshot that does not reflect structural/element changes in the source after creation |

Here, "snapshot" means the resulting list preserves the set of elements at the time of creation per its contract. You should not infer that the call always allocates a new object for every possible input.

### Arrays.asList Is a Fixed-Size List

For a reference array, the list returned by `Arrays.asList` has the same number of elements as the array:

- `set` updates a slot and can be observed through the array.
- Changing an element in the array is also observed through the list.
- `add` or `remove` would change the element count, so they are unsupported.

It is a **view** sharing the underlying data, not a resizable `java.util.ArrayList`.

### Unmodifiable Lists Have Different Rules

`List.of(...)` and `List.copyOf(...)` return lists that disallow modification. Mutating calls such as `add`, `remove`, and `set` are unsupported; these factory methods also do not accept `null` elements.

A list's unmodifiability applies only to its structure and the elements stored in its slots. If an element is a mutable object, the data inside that object can still be modified.

All the common copying approaches in this section are **shallow copies** with respect to element objects: they copy references, without cloning the entire object graph.

## 8. Complete Program: Distinguishing View, Copy, and Snapshot

Create the file **`ArrayViewCopyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class ArrayViewCopyDemo {
    public static void main(String[] args) {
        String[] source = {"red", "blue"};
        List<String> view = Arrays.asList(source);
        List<String> copy = new ArrayList<>(view);

        view.set(0, "green");
        copy.add("black");

        List<String> snapshot = List.copyOf(view);
        source[1] = "white";

        System.out.println("source = " + Arrays.toString(source));
        System.out.println("view = " + view);
        System.out.println("copy = " + copy);
        System.out.println("snapshot = " + snapshot);

        try {
            view.add("yellow");
        } catch (UnsupportedOperationException exception) {
            System.out.println("view.add: " + exception.getClass().getSimpleName());
        }

        try {
            snapshot.set(0, "yellow");
        } catch (UnsupportedOperationException exception) {
            System.out.println("snapshot.set: " + exception.getClass().getSimpleName());
        }

        String[] exported = view.toArray(String[]::new);
        exported[0] = "detached";

        System.out.println("exported = " + Arrays.toString(exported));
        System.out.println("source after export = " + Arrays.toString(source));
    }
}
```

Compile and run:

```text
javac -encoding UTF-8 --release 17 ArrayViewCopyDemo.java
java -Dfile.encoding=UTF-8 ArrayViewCopyDemo
```

Stdout:

```text
source = [green, white]
view = [green, white]
copy = [red, blue, black]
snapshot = [green, blue]
view.add: UnsupportedOperationException
snapshot.set: UnsupportedOperationException
exported = [detached, white]
source after export = [green, white]
```

### Tracing Each Variable

- `view.set(0, "green")` replaces the element in the data shared with `source`.
- `copy` was created before that change, so it still holds `"red"` at the first position. Calling `copy.add("black")` only grows the copied list.
- `snapshot` was created after the first replacement, so it holds `[green, blue]`.
- `source[1] = "white"` affects `view` but does not change the elements of `copy` or `snapshot`.
- `view.add` fails because its size is tied to the fixed-length array.
- `snapshot.set` fails because the list is unmodifiable.
- The `exported` array created by `toArray` has its own structure; reassigning `exported[0]` does not change the element in `source`.

All elements are `String`, an immutable type. When replacing a string at a slot, the program replaces the reference at that slot. If elements are mutable objects, internal modifications to a shared object can still be seen across multiple structures.

## 9. From Collection to Array

### Use the Right Array Type

Given a `Collection<String>`, you can write:

```java
String[] result = values.toArray(String[]::new);
```

This snippet requires a declared `values` variable containing valid elements. The `String[]::new` syntax provides a way to create an array of the right type. Elements are placed in the collection's iteration order, if the collection guarantees an order.

Another approach is:

```java
String[] result = values.toArray(new String[0]);
```

Both options avoid getting the wrong result array type. The complete program in the previous section uses the first approach.

### Do Not Speculatively Cast Object[] to String[]

`values.toArray()` with no arguments returns `Object[]`. You should not write:

```java
String[] result = (String[]) values.toArray();
```

This snippet compiles, but the actual resulting array is `Object[]`, so casting it to `String[]` throws `ClassCastException`. The fact that the elements happen to be strings does not change the runtime type of the array object.

### Returning to a Primitive Array Requires Converting Each Value

From a `List<Integer>`, calling `toArray` cannot directly produce an `int[]`. You must convert each value, for example using a loop with unboxing or an appropriate conversion utility.

When unboxing, you must decide how to handle `null`. Do not let an assumption that "every element has a number" be discovered only through a runtime exception.

## 10. Costs and Choosing a Structure

Arrays and collections cannot be ranked by a single "which one is faster" statement.

### Costs to Consider

- **Storing primitives:** `int[]` avoids the wrapper-object overhead of `List<Integer>`.
- **Changing element count:** `ArrayList` manages capacity growth; some additions may require copying data.
- **Inserting/removing in the middle of a list:** `ArrayList` typically needs to shift subsequent elements.
- **Searching by value:** scanning an array or list may require checking many elements.
- **Collections with specialized lookup structures:** there are options optimized for lookup or uniqueness, with different costs and rules.
- **Copying and converting:** adds allocation, data reads, and potentially boxing or unboxing.

Both array indexed access and `ArrayList.get` have costs that do not grow with the number of elements in typical usage. That does not mean all their operations have the same cost.

Nor can you assume that all collections have equally efficient indexed access or support indexing at all. Read the characteristics of the specific class and measure if performance is an actual requirement.

### A Selection Process

1. **Clarify the meaning of the data.** A fixed-length numeric vector differs from a shopping cart with a changing number of line items.
2. **Determine the element type.** Do you need to store primitive values directly?
3. **Determine group rules.** Do you need duplicates, ordering, indexing, or uniqueness?
4. **Identify primary operations.** Reading, iterating, searching, appending, inserting in the middle, or removing?
5. **Determine mutability.** Should the data be an independent copy, a shared view, or a snapshot?
6. **Check the consumer's contract.** Does the API require an array or a collection interface?
7. **Evaluate concurrency and cost.** Do not assume arrays or `ArrayList` automatically protect against concurrent modifications.

Guiding examples:

| Scenario | Option to Consider |
| --- | --- |
| Storing a block of integers with a known number of slots | `int[]` |
| An ordered list of data rows where items are added/removed | `List` with an appropriate implementation class |
| A set of codes where duplicates are not allowed | `Set` |
| Looking up data by key | `Map` |
| Calling an API that accepts an array parameter | Convert to the right array type at the API boundary |

The word "list" in everyday requirements is not enough to decide the data structure. Rules and operations are what you should use to choose.

## 11. Common Pitfalls

### Confusing Capacity with Size

`new ArrayList<>(100)` creates an empty list with an initial capacity request; it does not create a hundred `null` elements. Use `add` to populate elements.

### Assigning null and Treating It as Removed from an Array

`array[index] = null` only changes the value at that slot. `array.length` does not decrease. If you use an array as a container with an active region, you must manually update the rules and the active element count.

### Assuming Every Collection Has get(index)

`get` is a `List` operation. When code only has a `Collection<E>`, work within the general contract or refine the parameter type to match actual needs.

### Assuming Every List from an Array Can Grow

`Arrays.asList` creates a fixed-size list. When you need to add or remove elements, create a suitable mutable collection, such as `new ArrayList<>(...)`.

### Using Arrays.asList to Autobox an int[]

This call creates a `List<int[]>` with one element. Check the declared type and element count instead of relying only on the method name.

### Equating a Structural Copy with a Deep Copy

A new array or new list may still reference the same element objects. You need an explicit copying strategy if you want the elements themselves to be independent.

### Confusing Fixed-Size with Unmodifiable

A list from `Arrays.asList` allows `set`; a list from `List.of` does not allow `set`. Neither supports adding or removing, but their mutability levels are not the same.

## 12. Verification Exercises

### Exercise 1: Predict Size and Contents

Modify `ArrayAndListDemo`:

1. Change the initial capacity of `ArrayList` to `1`.
2. Keep the `add`, `set`, and `remove` calls unchanged.
3. Predict how many elements there will be after the four additions.
4. Run and compare with the original output.

Initial reserve capacity is not a limit on the number of elements in an `ArrayList`. With the operations unchanged, the element count after adding is still `4`.

### Exercise 2: Track Shared Data

In `ArrayViewCopyDemo`, change:

```java
source[1] = "white";
```

to:

```java
source[0] = "orange";
```

Before running, write down your predicted contents for `source`, `view`, `copy`, and `snapshot`. Explain your prediction based on creation timing and sharing relationships, rather than memorizing stdout.

### Exercise 3: Choose Types and Operations

For each requirement below, determine the structure, element type, and how to add/remove:

- Store 24 hourly temperatures for a single day.
- Store product line items in an editable shopping cart.
- Store flagged product codes, with no duplicates allowed.
- Return a string array to a legacy API from data currently held in a collection.

Indicate which operations change values, which change element counts, which cases require conversion, and whether any data is shared after conversion.
