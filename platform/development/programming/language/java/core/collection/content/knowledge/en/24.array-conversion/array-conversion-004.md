# toArray(), toArray(T[]), and toArray(IntFunction)

## 1. From collection to array: choosing both the type and the storage

A library might return a `List<String>`, while the next API expects a `String[]`. Both represent multiple elements, but their contracts differ: a collection manages its element count according to its implementation; an array object has a fixed length and a component type checked at runtime.

The `toArray` methods form the **collection → array** bridge. They place elements into a resulting array; they do not convert strings to numbers, sort data, or automatically deep-copy element objects.

Before choosing which overload to call, answer three questions:

1. Does the receiving API need `Object[]`, `String[]`, `Number[]`, or another array type?
2. Do you want to provide an already-allocated array for reuse?
3. Does the resulting array need to have the exact number of slots for the elements, or is a larger buffer acceptable?

Two concepts are especially important:

- **Declared type of the variable:** the type seen by the compiler, such as `Object[]`.
- **Runtime component type:** the kind of object the actual array can hold. An `Object[]` variable can still point to a `String[]` object.

Changing the declared type or casting a reference does not recreate the array object with a new component type. This is the source of many bugs when using `toArray`.

This lesson examines array types, buffer reuse, array generator functions, and then ownership and reference sharing of the resulting data.

## 2. The three call forms and how to choose

The signatures below belong to `Collection<E>`; these are abbreviated API declarations, not a standalone runnable program:

```java
Object[] toArray();
<T> T[] toArray(T[] array);
default <T> T[] toArray(IntFunction<T[]> generator);
```

The `IntFunction` form has been available since Java 11. The programs in this lesson use APIs compatible with Java 17 and compile with `--release 17`.

| Call form | Caller provides | Resulting array type | Common use case |
| --- | --- | --- | --- |
| `items.toArray()` | No arguments | `Object[]` | Only a general-purpose object array is needed |
| `items.toArray(new String[0])` | Sample array of type `String[]` | Same runtime array type as the argument array | Needs a string array; also works prior to Java 11 |
| `items.toArray(buffer)` | An existing array | Same runtime array type as `buffer` | Explicitly provides storage and accepts reuse rules |
| `items.toArray(String[]::new)` | String array generator | Array type provided by the generator | Expresses the array type directly on Java 11+ |

The name `T` in the two typed methods is a type parameter of the **method**, not a mandatory restatement of `E` in `Collection<E>`. Therefore, choosing a target array type incompatible with the elements may still compile and then fail at runtime.

A collection of strings can be placed into an `Object[]` or `CharSequence[]`. Conversely, a collection of numbers containing both `Integer` and `Double` cannot be stored completely in an `Integer[]`. You must consider the actual elements and the kind of objects the target array accepts.

The [`Collection.toArray` contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#toArray()) specifies the result type, ordering, and rules for accepting an array or array generator.

## 3. toArray(): the actual result is Object[]

When called with no arguments, the runtime type of the resulting array is `Object[]`, even when all elements are `String`. The returned array has as many slots as there are elements and is not an internal backing array held by the collection that reflects slot modifications to the result.

The following snippet only illustrates the idea and is not a standalone program:

```java
List<String> words = List.of("red", "blue");
Object[] objects = words.toArray();

// Still compiles, but fails at runtime:
String[] strings = (String[]) objects;
```

The cast checks whether the existing object is a `String[]`. It does not inspect each slot to see that every element is a string and replace the `Object[]` with a new string array. The result is therefore a `ClassCastException`.

If the next API expects `String[]`, request the right kind of array from the start using `toArray(new String[0])` or `toArray(String[]::new)`. Adding a cast to avoid changing the call does not solve the problem.

With an `Object[]` returned by `toArray()`, modifying a slot of the array does not replace the corresponding slot in the collection's structure. However, the object that the slot points to can still be shared; the section on shallow copying distinguishes these two kinds of changes.

## 4. toArray(T[]): the argument array is both storage and type information

Let:

- `n` be the number of elements to put into the array.
- `m` be the length of the argument `array`.
- The elements have types suitable for storing in that array.

This analysis assumes there is no concurrent modification altering the data during the conversion and that the call completes successfully.

| Size relationship | Returned array | Result length | Key takeaway |
| --- | --- | --- | --- |
| `m < n` | A new array with the same runtime type as the argument array | `n` | Must use the return value; the passed-in array was not large enough |
| `m == n` | The argument array itself | `m` | All slots hold elements of the collection |
| `m > n` | The argument array itself | `m` | The slot at index `n` is set to `null` after the data |

An array cannot grow in place. When it is too small, the method creates another array and returns the new reference. Therefore, the call must retain the result:

```java
// Illustrative snippet: buffer is already declared as String[].
buffer = names.toArray(buffer);
```

If you only call `names.toArray(buffer)` and discard the return value, the code may appear to work when `buffer` is large enough but mistakenly read the old buffer when the collection gains more elements.

### 4.1. A zero-length array still provides type information

In `names.toArray(new String[0])`, the empty array is not meant to hold all the elements itself. It provides the kind of array to create. If the collection is non-empty, the new resulting array has the appropriate length; its runtime type is still `String[]`.

Do not interpret `new String[0]` as "take only 0 elements". `toArray` outputs all elements according to the collection's contract.

If the collection is empty and the argument array is also empty, no extra space is needed: the argument array can be returned directly under the sufficient-space branch. This differs from assuming that every `toArray` form always allocates a new array object.

### 4.2. A null after the data is not a new array length

For example, suppose a collection has two strings while the target array has five slots. After a successful call, the first two slots hold the data, the third slot is `null`, and the array's length is still five.

There is no guarantee that the entire trailing portion will be cleared. In the `ArrayList` example below, the slots after the `null` marker still retain their old values. Thus, iterating over the entire `result.length` as if all slots were elements of the collection can mistakenly process stale data.

If the collection is known for certain not to contain `null`, the `null` marker right after the data region can help identify the end. If the collection allows `null`, finding the first `null` is not a valid way to determine the number of elements.

The empty collection case also warrants attention: with a target array that has room, slot `0` is set to `null`; old elements at subsequent positions may remain.

### 4.3. Type rules are based on the actual array

A `Number[]` variable can point to `new Integer[0]`. Passing this variable into `toArray` does not tell the method to create a broader `Number[]`. The actual array type is still `Integer[]`, so a `Double` element cannot be stored in that result.

Distinguish between:

```java
// Illustrative snippet of two array objects with different runtime types.
Number[] wide = new Number[0];
Number[] narrow = new Integer[0];
```

Having the same declared type `Number[]` does not mean the two arrays have the same ability to hold elements. [Java's array rules](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html#jls-10.5) explain the check performed when storing an object into an array.

## 5. Program: Observing the size branches

The following program uses `ArrayList` so that data ordering is deterministic. The variables `small`, `exact`, and `large` test arrays smaller than, equal to, and larger than the number of elements, respectively.

File `ToArrayOverloadsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class ToArrayOverloadsDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>(List.of("Lan", "Minh"));

        Object[] objects = names.toArray();
        System.out.println("plainType=" + objects.getClass().getTypeName());
        System.out.println("plain=" + Arrays.toString(objects));
        try {
            String[] invalid = (String[]) objects;
            throw new AssertionError("Cast unexpectedly succeeded: " + invalid.length);
        } catch (ClassCastException expected) {
            System.out.println("plainCast=ClassCastException");
        }

        String[] small = {"old"};
        String[] grown = names.toArray(small);
        System.out.println("smallReused=" + (grown == small));
        System.out.println("smallAfter=" + Arrays.toString(small));
        System.out.println("grown=" + Arrays.toString(grown));

        String[] exact = new String[2];
        String[] exactResult = names.toArray(exact);
        System.out.println("exactReused=" + (exactResult == exact));
        System.out.println("exact=" + Arrays.toString(exact));

        String[] large = {"x0", "x1", "x2", "x3", "x4"};
        String[] largeResult = names.toArray(large);
        System.out.println("largeReused=" + (largeResult == large));
        System.out.println("large=" + Arrays.toString(large));

        String[] zeroResult = names.toArray(new String[0]);
        String[] generated = names.toArray(String[]::new);
        System.out.println("zeroType=" + zeroResult.getClass().getTypeName());
        System.out.println("generated=" + Arrays.toString(generated));

        generated[0] = "changed";
        names.set(1, "owner");
        System.out.println("namesAfter=" + names);
        System.out.println("arrayAfter=" + Arrays.toString(generated));

        String[] emptyTarget = {"old0", "old1", "old2"};
        String[] emptyResult = List.<String>of().toArray(emptyTarget);
        System.out.println("emptyReused=" + (emptyResult == emptyTarget));
        System.out.println("emptyTarget=" + Arrays.toString(emptyTarget));

        List<String> withNull = Arrays.asList(null, "x");
        String[] nullableTarget = {"a", "b", "c", "d"};
        withNull.toArray(nullableTarget);
        System.out.println("nullable=" + Arrays.toString(nullableTarget));
    }
}
```

Compile and run in the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 ToArrayOverloadsDemo.java
java ToArrayOverloadsDemo
```

Output:

```text
plainType=java.lang.Object[]
plain=[Lan, Minh]
plainCast=ClassCastException
smallReused=false
smallAfter=[old]
grown=[Lan, Minh]
exactReused=true
exact=[Lan, Minh]
largeReused=true
large=[Lan, Minh, null, x3, x4]
zeroType=java.lang.String[]
generated=[Lan, Minh]
namesAfter=[Lan, owner]
arrayAfter=[changed, Minh]
emptyReused=true
emptyTarget=[null, old1, old2]
nullable=[null, x, null, d]
```

### 5.1. Reading the output in three categories

`plainType=java.lang.Object[]` explains why casting this array to `String[]` fails. The array object's type never became a string array merely because its contents were two strings.

`smallReused=false` shows that the one-slot array was not returned to hold two elements. In this experiment, `small` still keeps `"old"`, while the data resides in `grown`. This is why you must keep the return value.

`exactReused=true` and `largeReused=true` show that the method can write into the provided array itself when there is enough room. In the large array, `x2` is replaced by a `null` marker right after the data; `x3` and `x4` remain.

`namesAfter` and `arrayAfter` demonstrate that replacing a slot in the resulting array and replacing an element in the list do not make the two structures a live view of each other in this example.

Finally, `nullable=[null, x, null, d]` contains two `null` values with different roles: the first slot is an actual element of the collection, and the third slot is the terminator after the two elements. Reading only up to the first `null` would miss the element `"x"`.

## 6. Type errors across the three ways to convert to an array

`toArray()` creates an `Object[]`; casting that array object itself to `String[]` throws `ClassCastException`. With the two overloads that accept an array or an array generator, the runtime also checks whether each element can be stored into the **actual component type** of the target array. If not, `ArrayStoreException` occurs.

Illustrative example inside a method with `Collection` and `List` imported:

```java
Collection<Number> values = List.of(1, 2.5);
Number[] accepted = values.toArray(Number[]::new); // [1, 2.5]
// Both of the following calls throw ArrayStoreException:
values.toArray(new Integer[0]);
values.toArray(Integer[]::new);
```

`Number[]` accepts both `Integer` and `Double`, whereas `Integer[]` cannot hold `Double`. Generics do not eliminate runtime store checks. Even a `Number[]` variable can hold an `Integer[]` object and reject a `Double` when writing. Details on covariance, actual array types, and partially copied results are analyzed in the upcoming dedicated `ArrayStoreException` lesson.

Also distinguish the following cases:

| Situation | Result or requirement |
| --- | --- |
| `(String[]) list.toArray()` | `ClassCastException`, because the actual type is `Object[]` |
| `toArray(new Integer[0])` with data containing `Double` | `ArrayStoreException` when storing the element |
| `toArray((String[]) null)` or `toArray((IntFunction<String[]>) null)` | `NullPointerException`; the cast here is only to resolve the overload |
| `toArray(null)` without a type when both overloads exist | Ambiguous call at compile time |
| Converting `List<Integer>` to `int[]` | Requires an `IntStream`/explicit unboxing step; `Collection.toArray` returns a reference array |

If the conversion fails, do not treat the provided buffer as a complete result or assume it was rolled back. `toArray` copies references; it does not automatically convert `Integer[]` to `int[]` or enforce a `null` policy for unboxing.

## 7. toArray(IntFunction): delegating array creation to a function

`IntFunction<R>` is a functional interface that takes an `int` and returns `R`. With `toArray`, `R` is `T[]`: the function receives the requested length and creates an array of that type and length.

Two equivalent ways to express creating a string array:

```java
// Illustrative snippet, where names is a Collection<String>.
String[] first = names.toArray(String[]::new);
String[] second = names.toArray(length -> new String[length]);
```

The `String[]::new` syntax is a reference to the array creation operation. Populating elements from the collection into the array is still performed by `toArray`; the generator only provides the array.

[`IntFunction.apply(int)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/IntFunction.html) explains the input and output types of this interface. A parameterless lambda such as `() -> new String[0]` does not match the function shape taking an `int` required by this overload.

### 7.1. The received argument is not necessarily size()

The published default implementation in `Collection` calls the generator with `0`, then passes the resulting array to `toArray(T[])`. You can picture the mechanism with this illustrative snippet:

```java
// Simplified model of the default method, not a standalone program.
return toArray(generator.apply(0));
```

With `String[]::new`, the first step creates an empty string array; the array-taking method then allocates enough space if needed. Thus, having a collection of three elements while the default generator still receives `0` is clearly documented behavior, not a bug.

A collection class may override the default method. Therefore:

- The generator should use the exact length it receives, rather than relying on an element count captured from outside.
- Do not write a generator that is only correct when the argument is always `0` or always `size()`.
- Do not rely on the number of invocations or side effects of the generator as part of application logic.
- The generator should not modify the collection being converted.

The [default method specification](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#toArray(java.util.function.IntFunction)) explicitly describes the call with `0`. The next program uses a class that inherits the default method to observe this exact case.

### 7.2. Difference from calling via Stream

`collection.toArray(String[]::new)` calls the API on the collection. `collection.stream().toArray(String[]::new)` creates a stream and invokes `Stream`'s terminal operation.

They can yield the same sequence of elements in a simple scenario, yet they have distinct execution contracts and implementation mechanisms. Do not take the observation "generator receives 0" in `Collection`'s default method and infer that every stream's generator—especially under parallel processing—must be called identically.

If you only need to convert a collection to a typed array, the direct call expresses the intent clearly. If you need to filter or transform elements first, a stream pipeline can address that additional need; the transformation step itself is what justifies using a stream.

The [`Stream.toArray(IntFunction)` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toArray(java.util.function.IntFunction)) has its own specification for creating arrays to serve stream results.

## 8. Array ownership and shallow copying

There are three things to distinguish:

1. The collection holding element references.
2. The resulting array whose slots hold references.
3. The element objects that both structures may point to at the same time.

Creating a new array does not mean recreating every element object. If an element is a mutable object, mutating that object's state through the array can still be observed when reading through the collection.

Conversely, replacing a slot in a new array with a different reference only changes that array's slot. It does not call `set` or `add` on the collection. Subsequent growth of the collection also does not lengthen an existing array.

This is a **shallow copy** from the perspective of the structure holding references, not a deep copy of the entire object graph.

### 8.1. Providing an existing array does not erase existing sharing relationships

With `toArray()`, the collection must provide a new array that is safe for the caller to mutate slots on.

With `toArray(T[])`, the caller explicitly supplies an array. If that array has enough room, it is returned itself. The method does not isolate that array from other components that are already using it.

A particularly notable example:

- `Arrays.asList(backing)` creates a list backed by `backing`.
- Calling `list.toArray(backing)` with that same original array can return `backing`.
- The result still shares array slots with the list via the pre-existing relationship.

If you want a separate new array in this situation, pass a new array generator such as `String[]::new` or a suitable new target array. Even when the array slots are separate, the element objects themselves can still be shared.

The [`Arrays.asList` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)) specifies that the list is backed by the input array. Reading both the source and target contracts helps avoid assuming that a conversion call automatically erases all sharing relationships.

### 8.2. Program: Three layers of sharing and the default generator

`Counter` is an object with a mutable field. The first part of the program distinguishes mutating a `Counter` object from replacing an array slot that holds a reference to a `Counter`.

The later part uses `Arrays.asList` to check the relationship with the backing array. Finally, a class extending `AbstractCollection` only provides `iterator` and `size`, keeping the default implementation of the generator overload. Recording the length argument in the example is solely for observation, not a side effect to rely on in applications.

File `ToArrayOwnershipDemo.java`:

```java
import java.util.AbstractCollection;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Iterator;
import java.util.List;

public class ToArrayOwnershipDemo {
    private static final class Counter {
        int value;

        Counter(int value) {
            this.value = value;
        }

        @Override
        public String toString() {
            return Integer.toString(value);
        }
    }

    public static void main(String[] args) {
        List<Counter> counters = new ArrayList<>(
                List.of(new Counter(1), new Counter(2)));
        Counter[] captured = counters.toArray(Counter[]::new);
        System.out.println("sameElement=" + (captured[0] == counters.get(0)));

        captured[0].value = 10;
        captured[1] = new Counter(99);
        counters.add(new Counter(3));
        System.out.println("collection=" + counters);
        System.out.println("captured=" + Arrays.toString(captured));
        System.out.println("capturedLength=" + captured.length);

        String[] backing = {"left", "right"};
        List<String> backedList = Arrays.asList(backing);
        String[] detached = backedList.toArray(String[]::new);
        detached[0] = "copy";
        backing[1] = "owner";
        System.out.println("backing=" + Arrays.toString(backing));
        System.out.println("detached=" + Arrays.toString(detached));
        System.out.println("backedList=" + backedList);

        String[] alreadyAliased = backedList.toArray(backing);
        System.out.println("suppliedBackingReused=" + (alreadyAliased == backing));
        alreadyAliased[0] = "shared";
        System.out.println("afterAliasedWrite=" + backedList);

        Collection<Integer> inheritedDefault = new AbstractCollection<>() {
            private final List<Integer> values = List.of(3, 4, 5);

            @Override
            public Iterator<Integer> iterator() {
                return values.iterator();
            }

            @Override
            public int size() {
                return values.size();
            }
        };

        List<Integer> requestedLengths = new ArrayList<>();
        Integer[] result = inheritedDefault.toArray(length -> {
            requestedLengths.add(length);
            return new Integer[length];
        });
        System.out.println("defaultRequests=" + requestedLengths);
        System.out.println("defaultResult=" + Arrays.toString(result));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ToArrayOwnershipDemo.java
java ToArrayOwnershipDemo
```

Output:

```text
sameElement=true
collection=[10, 2, 3]
captured=[10, 99]
capturedLength=2
backing=[left, owner]
detached=[copy, right]
backedList=[left, owner]
suppliedBackingReused=true
afterAliasedWrite=[shared, owner]
defaultRequests=[0]
defaultResult=[3, 4, 5]
```

### 8.3. Explaining the seemingly contradictory results

`sameElement=true` shows that `captured[0]` and the first element of the collection point to the same object. Modifying the `value` field through `captured[0]` makes the collection observe `10`.

Replacing `captured[1]` with a `Counter(99)` does not change the second element in the collection. The collection still sees `2`, while the array sees `99`. When element `3` is added to the collection, the array's length remains two.

In the string example, `detached` is created via a new array generator. Changing `detached[0]` does not change `backing[0]`. Changing `backing[1]` is visible through `backedList`, but `detached[1]` remains `"right"`.

Next, `suppliedBackingReused=true` confirms that when `backing` itself is provided as the target array, the method returns the array backing the list. Writing `"shared"` through the result is now visible in the list. The difference comes from which array object was chosen as the storage, not from whether `String` itself is mutable.

Finally, `defaultRequests=[0]` matches the described default implementation. The resulting array still holds all three elements. The argument passed to the generator and the length of the final returned array do not have to be equal in this default mechanism.

[`AbstractCollection`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractCollection.html) is a skeletal implementation class, useful for observing the default mechanism without building a whole collection from scratch.

## 9. Applying the contract correctly in real code

### 9.1. Choosing based on the receiving API's goal

| Need | Option to choose | Additional check required |
| --- | --- | --- |
| API expects a general-purpose object array | `collection.toArray()` | Is `Object[]` really what is needed? |
| API expects a string array on Java 11+ | `collection.toArray(String[]::new)` | Elements must be storable in `String[]` |
| API expects a string array, pre-Java 11 compatibility needed | `collection.toArray(new String[0])` | Always retain the returned array |
| Want to reuse a buffer | `buffer = collection.toArray(buffer)` | Accept that the array may have extra slots and pre-existing sharing relationships |
| API needs `int[]` from `Collection<Integer>` | Explicit transform/unboxing, such as `mapToInt` | Have a policy for `null` and invalid data |

If the downstream API requires an array whose physical length is exactly `n` elements, do not pass a larger buffer and assume `result.length` is the collection size. Choosing a new array of the appropriate size keeps the contract between the two APIs simpler.

Conversely, when an API is designed to accept a buffer and a separate data length, reusing a large array can be appropriate. The data length must be managed explicitly; a `null` marker cannot substitute for that length when `null` is also valid data.

### 9.2. Order follows the collection; it is not sorted automatically

If a collection guarantees an iteration order, `toArray` must preserve the corresponding order. A `List` provides a sequential element order, so the programs in this lesson produce deterministic output.

A collection without an ordering guarantee does not become ordered merely by being converted to an array. For example, do not use the result of a `HashSet` to assert that the element at index `0` is always the smallest or the first one added.

Similarly, the fact that the head of a priority queue has priority significance does not mean the entire iterator or resulting array of a `PriorityQueue` is sorted. The [`PriorityQueue` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html) clearly distinguishes accessing the head element from iteration order. If the target API requires a sorted sequence, the sorting step must be performed intentionally according to the appropriate rule.

### 9.3. Map does not have toArray directly

`Map` is not a `Collection`. To export keys, values, or mapping entries, you must select the corresponding collection view.

The following snippet illustrates two different choices and is not a standalone runnable program:

```java
// scores is a Map<String, Integer>.
String[] keys = scores.keySet().toArray(String[]::new);
Integer[] values = scores.values().toArray(Integer[]::new);
```

Choose the right data semantics for the target API. If the key–value relationship must be kept together, exporting two separate arrays via two calls does not produce an atomic snapshot of the mapping entries if the map can change between the two calls.

### 9.4. The resulting array does not prove atomicity under concurrent modification

The size rules in the earlier section describe a single valid conversion; they do not implicitly add a synchronization policy to the collection.

For example, calling `size()` to allocate an array and then calling `toArray` are two separate operations. The collection can change between them if there is a concurrent modification path. Do not infer that the read size is the exact element count of a shared point in time for all data exported to the array.

Follow the access policy of the specific collection type or use an appropriate coordination mechanism for the export operation. Receiving an array successfully does not by itself prove that all related business data was captured at the same point in time.

For an unmodifiable collection such as `List.of`, `toArray` is still a valid read operation. The newly returned array may allow its slots to be modified; that does not grant permission to modify the structure of the source list.

### 9.5. Cost and performance conclusions to avoid

Typically, exporting `n` elements requires placing `n` references into the target array. With a new array sized for the data, memory for the array slots scales with the number of elements; element objects are not deep-copied because of it.

An already-allocated array with enough room can reduce the need to allocate a new result array. However, you also have to account for buffer management overhead, excess slots, retained old references, and the type of collection being used.

There is no universal conclusion that `new T[0]`, `new T[size()]`, or the generator reference form is always fastest across every JDK and every collection. The implementation, JVM optimizations, data size, and measurement methodology all affect the outcome. A benchmark snippet that is too short or discards results may measure compiler optimizations rather than actual conversion cost.

Prefer the form that expresses the needed array type and ownership clearly. Only choose a more complex approach for performance after obtaining measurements relevant to the actual execution path.

### 9.6. Inspecting array contents with the right tools

The examples use `Arrays.toString` to display array slots. Printing an array object directly with `System.out.println(array)` usually displays the object's identity representation rather than a readable sequence of elements.

Similarly, when comparing the contents of two one-dimensional arrays, use an appropriate comparison such as `Arrays.equals` instead of treating `array1.equals(array2)` as a slot-by-slot comparison. A correct conversion combined with an incorrect way of inspecting or comparing can lead to wrong conclusions during testing.

## 10. Practice exercises for self-checking

### Exercise 1: Retaining the result when the array is too small

Create a list of three strings and a one-slot target array. Call `toArray` once while keeping the result, and once while discarding the result.

**Key point to explain:** an array does not grow in place. The complete result is in the returned array when the buffer is insufficient. Code that discards the result only appears to work if it happens to hit the reuse branch.

### Exercise 2: Distinguishing the null marker from null data

Create a collection with three elements where the second element is `null`. Provide a five-slot array that already holds old values, then inspect the entire array.

**Key point to explain:** there is one `null` belonging to the data and one `null` right after the three elements. You must not use the position of the first `null` to measure data size. Slots outside the data region do not become new elements of the collection.

### Exercise 3: Changing the declared type while keeping the actual array type

Declare `Number[] buffer = new Integer[0]`, then try exporting a collection containing `Integer` and `Double` into `buffer`. Afterward, replace it with `new Number[0]`.

**Key point to explain:** the storage constraint lies in the actual array object. A broader declared type does not turn an integer array into a general number array.

### Exercise 4: Separating slot replacement from mutating an element object

Use a list of objects with a mutable field. Obtain an array using a new array generator, mutate the field through one slot, and then replace another slot with a new object.

**Key point to explain:** mutating the state of a shared object differs from replacing a reference in a containing structure. `toArray` does not deep-copy elements.

### Exercise 5: Tracing why the result still shares slots with the list

Use `Arrays.asList(backing)`, then compare the result of `toArray(backing)` with `toArray(String[]::new)`.

**Key point to explain:** in the first call, the caller supplied the very array backing the list and it had enough room, so reuse preserved the sharing relationship. In the second call, the generator allocated a new array. Even when the slots are separated, the element type still determines whether object state can be shared.

### Exercise 6: Explaining the generator's 0 argument

Run the `inheritedDefault` section in the third program. Try replacing the data with an empty list and a larger list, while still creating the array according to the length the lambda receives.

**Key point to explain:** `Collection`'s default method uses the array created from the `0` argument to proceed into the array-taking overload. There is no need to read `size()` outside the generator to "fix" this mechanism.

A solid way to choose a call form is to read in order: **array type required by the target API → actual array created/supplied → size rules → reference sharing possibility → ordering and access policy of the collection**.
