# `List<Integer>` Is Not `int[]` in Java

In Java, `int[]` is an **array of primitive `int` values**, whereas `List<Integer>` is a **list type holding references to `Integer` objects**. Both can represent a sequence of numbers like 2, 4, 6, but they **do not share the same type, storage layout, API, resizability, `null` handling, or operation costs**.

```java
int[] array = {2, 4, 6};
java.util.List<Integer> list = new java.util.ArrayList<>();
list.add(2);
list.add(4);
list.add(6);

System.out.println(array[0]);  // 2
System.out.println(list.get(0)); // 2
```

Identical printed output does not mean the two variables are interchangeable. Specifically, in **Boxing and unboxing**, `List<Integer>` also involves implicit conversions between `int` and `Integer`, allocating/holding object references, and the risk of `NullPointerException` during unboxing.

## 1. Quick comparison table

| Aspect | `int[]` | `List<Integer>` |
| --- | --- | --- |
| Data type | Array of primitive `int` | Generic `List` type with reference type argument `Integer` |
| Elements | 32-bit `int` values | References to `Integer` objects or `null` if the implementation permits |
| Get element | `a[i]` | `list.get(i)` |
| Set element | `a[i] = value` | `list.set(i, value)` if the list supports it |
| Element count | `a.length` (field) | `list.size()` (method) |
| Grow/shrink element count | No; array length is fixed | Depends on implementation: `ArrayList` supports add/remove; `List.of` is unmodifiable |
| Default elements when creating container | `new int[3]` holds three 0s | `new ArrayList<Integer>()` is empty; `new Integer[3]` holds three `null`s |
| Accepts `null` as an element | No | Possible, e.g., `ArrayList`, though `List.of` forbids it |
| Generic type argument | Not applicable | Must use `Integer`; cannot write `List<int>` |
| Access model | Array index access | `List` contract; complexity depends on list implementation |
| Manipulation libraries | `Arrays.sort`, `Arrays.stream`, `Arrays.equals` | `sort`, `stream`, `contains`, `add`, `remove`... depending on mutability |
| Memory usage | `int` elements stored in primitive array | Typically has reference backing storage and wrapper objects, adding management overhead |
| Type compatibility | Neither `Integer[]` nor `List<Integer>` | Does not automatically become `int[]`; requires explicit conversion |

**Remember:** `List<Integer>` specifies the *element type*, **not the internal structure**. `ArrayList<Integer>` typically stores references inside an `Object[]` array, whereas `LinkedList<Integer>` uses linked nodes. You must not infer that every `List<Integer>` is contiguous in memory or has array-like indexed access speed.

## 2. `int` is a primitive, `Integer` is a wrapper class

`int` is not an object. `Integer` is an immutable class in `java.lang` holding an `int` value and providing APIs such as `intValue`, `parseInt`, and `compare`.

```java
int primitive = 42;
Integer wrapper = Integer.valueOf(42);
int restored = wrapper.intValue();
```

Java supports **autoboxing** and **unboxing**, so many conversions are written more concisely:

```java
Integer boxed = 42; // Autoboxing: int -> Integer.
int unboxed = boxed; // Unboxing: Integer -> int.
```

When adding an `int` to a `List<Integer>`, boxing occurs implicitly:

```java
java.util.List<Integer> values = new java.util.ArrayList<>();
values.add(10);       // Semantically adds an Integer containing 10.
int first = values.get(0); // get returns Integer; assigning to int -> unboxing.
```

**Not every `List<Integer>` operation creates a new boxed object**: an existing `Integer` reference may be added; the JVM may also use wrapper caching for some values. Hence saying “every element always allocates exactly one new object” is inaccurate. What matters is that the API operates on **objects/references**, unlike primitive `int` slots.

### Why is `List<int>` invalid?

Traditional Java generics require **type arguments to be reference types**; primitive `int` is not a valid type argument:

```java
// List<int> bad = new ArrayList<>(); // Does not compile.

java.util.List<Integer> good = new java.util.ArrayList<>();
```

Java does not automatically transform `List<int>` into `List<Integer>` in generic syntax. When primitive-stream computation avoiding boxing is needed, Java provides `IntStream`; when contiguous primitive storage is needed, `int[]` is usually the better fit.

### `Integer[]` is also not `int[]`

`Integer[]` is an array of **references to `Integer`**, which can hold `null`. Meanwhile, `int[]` is an array holding **`int` values**. The two array types are not compatible via an ordinary cast:

```java
int[] primitives = {1, 2, 3};
Integer[] objects = {1, 2, 3}; // Each value is boxed.

// Integer[] wrong = primitives; // Does not compile.
// int[] wrong2 = objects;       // Does not compile.
```

`Integer[]` differs from `int[]` in elements and memory; it is closer to `List<Integer>` regarding object element types, yet remains a **fixed-length array**, not a List.

## 3. API differences: `length`, `size()`, `[]`, `get()`, `set()`

With an array:

```java
int[] ages = {18, 20, 22};
System.out.println(ages.length); // 3.
System.out.println(ages[1]);     // 20.
ages[1] = 21;
```

With a list:

```java
java.util.List<Integer> ages =
        new java.util.ArrayList<>(java.util.List.of(18, 20, 22));

System.out.println(ages.size()); // 3.
System.out.println(ages.get(1)); // 20.
ages.set(1, 21);
```

You cannot use `ages.length` or `ages[1]` when `ages` has type `List<Integer>`. Conversely, arrays do not have `get`, `set`, `add`, or `size()` like `List`.

### Size and mutability are two separate axes

Arrays have fixed length, but **elements can be modified**:

```java
int[] nums = {1, 2};
nums[0] = 9; // Valid.
// nums.add(3); // No add method.
```

`List<Integer>` is only an interface: it has data-mutation methods, yet an implementation might **not support them**. For example:

```java
java.util.List<Integer> resizable = new java.util.ArrayList<>();
resizable.add(1);
resizable.add(2); // Grows size to 2.

java.util.List<Integer> fixedValues = java.util.List.of(1, 2);
// fixedValues.add(3); // Throws UnsupportedOperationException at runtime.
// fixedValues.set(0, 9); // Also throws UnsupportedOperationException.
```

`List.of` (Java 9+) creates an **unmodifiable** list. It forbids adding/removing, forbids replacing elements, and **does not accept `null` elements**. `ArrayList` by default supports add/remove/set and can contain `null`.

You should not infer that `List<Integer>` is always “resizable”; that only holds for certain implementations and operating conditions.

## 4. Impact of `null` and unboxing

This is the most important difference in terms of safety.

`new int[3]` creates **three values of 0**. Every element of a primitive array is always a valid `int` and can never be `null`.

```java
int[] ints = new int[1];
System.out.println(ints[0]); // 0.
```

Conversely, a wrapper array `new Integer[3]` has elements defaulting to `null`, while `new ArrayList<Integer>()` initially has **size = 0** with no elements:

```java
Integer[] objects = new Integer[1];
System.out.println(objects[0]); // null.

java.util.List<Integer> empty = new java.util.ArrayList<>();
System.out.println(empty.size()); // 0.
```

Lists that permit `null` can throw errors when you extract primitive values:

```java
java.util.List<Integer> list = new java.util.ArrayList<>();
list.add(null);

// int x = list.get(0); // Throws NullPointerException during unboxing.
Integer value = list.get(0);
System.out.println(value == null); // true.
```

Similarly, `for (int x : list)` will unbox each `Integer` and can throw `NullPointerException` upon encountering `null`. `list.stream().mapToInt(Integer::intValue)` also does not implicitly handle `null`.

**API design:** if elements must always hold integer values, avoid `null` through validation or use a primitive container. If `null` means “unknown”, state the handling policy explicitly instead of unconditionally unboxing or automatically replacing with 0 (since 0 might be valid data).

## 5. Why are the two containers not directly compatible?

`int[]` is **a concrete runtime array type** (array component type is primitive `int`). `List<Integer>` is **an object implementing the `List` interface**. Java has no automatic conversion between these two structures:

```java
int[] raw = {1, 2, 3};

// List<Integer> list = raw; // Does not compile.
// int[] other = new ArrayList<Integer>(); // Does not compile.
```

Both are objects at the Java reference level (arrays are objects), yet **an `int[]` array does not implement `List`**. Casting `(List<Integer>) raw` is also no solution; it does not convert data into wrappers and a list.

`List<Integer>` does not mean “an int array with a different API”. Any real conversion must iterate over elements, perform boxing or unboxing, and build the appropriate target structure.

### Polymorphism and generic invariance

`List<Integer>` is **not a subtype of** `List<Number>`, even though `Integer extends Number`. Java generics follow *invariance* rules for types like `List<T>`:

```java
java.util.List<Integer> ints = java.util.List.of(1, 2);
// List<Number> numbers = ints; // Does not compile.

java.util.List<? extends Number> readOnlyView = ints;
Number x = readOnlyView.get(0);
```

`List<? extends Number>` allows reading elements as `Number`, but does not allow arbitrarily adding new `Number`s, because the actual list may only accept `Integer`. This is a matter of **generic type safety**, unrelated to being able to cast `int[]` to a List.

Object arrays have *covariance* rules distinct from generics and can raise `ArrayStoreException` at runtime, yet `int[]` is not a subtype of `Object[]`: elements of `int[]` are primitives, not references.

## 6. The most common trap: `Arrays.asList(int[])`

Many developers write:

```java
int[] raw = {2, 4, 6};
var list = java.util.Arrays.asList(raw);
```

The surprise: **`list` is not `List<Integer>`**. It is `List<int[]>` with **exactly one element, which is the entire `raw` array**.

```java
System.out.println(list.size());      // 1.
System.out.println(list.get(0).length); // 3.
```

`Arrays.asList(T... a)` accepts varargs of **reference** type `T`. With an `int[]` argument, `int[]` itself is an object; Java infers `T = int[]`. There is no automatic “unpacking” of each number in a primitive array into `Integer`.

Therefore:

```java
// List<Integer> wrong = Arrays.asList(new int[]{1,2,3});
// Compile-time error due to incompatible inferred type.
```

Do not try to fix it with raw types or unsafe casts: the consequence can be `ClassCastException` when retrieving elements.

### `Arrays.asList(Integer[])` is different

```java
Integer[] objects = {2, 4, 6};
java.util.List<Integer> list = java.util.Arrays.asList(objects);

System.out.println(list.size()); // 3.
list.set(0, 10);
System.out.println(objects[0]); // 10.
```

In this case, a reference-element array `Integer[]` is passed to `Arrays.asList`, so the list receives each `Integer` element. The returned list has **fixed size** and is **backed by** the `objects` array:

- `list.set` modifies the corresponding position in the original array.
- Modifying an element of the original array is reflected through the list.
- `list.add` and `list.remove` throw `UnsupportedOperationException` because they change the size.

**Do not confuse `Arrays.asList` with `new ArrayList<>()`.** Both implement the `List` interface, yet their resizability and relationship to the original array differ greatly.

### `List.of(raw)` also does not convert to `List<Integer>`

If `raw` is `int[]`, `List.of(raw)` creates a list containing **one element, the `int[]` array**, not a list of boxed integers. When a boxed list is needed, use stream `boxed()` or a loop.

## 7. Converting from `int[]` to `List<Integer>`

### Approach 1 — Loop and `ArrayList` (modifiable list)

```java
int[] raw = {2, 4, 6};
java.util.List<Integer> list = new java.util.ArrayList<>();

for (int value : raw) {
    list.add(value); // Autoboxing int -> Integer.
}
```

This approach is easy to understand and works on Java 17+. It creates a list **independent** of the original array: changing `list.set(0, 99)` **does not** modify `raw[0]`, and changing `raw[0]` **does not** modify the created list.

For large datasets, you can specify an expected capacity:

```java
java.util.ArrayList<Integer> list =
        new java.util.ArrayList<>(raw.length);
for (int value : raw) {
    list.add(value);
}
```

`new ArrayList<>(raw.length)` only sets the **initial capacity**; it does not create `raw.length` elements and initial `size()` remains 0. Do not call `set(i, value)` immediately if there is not yet an element at index `i`.

### Approach 2 — `Arrays.stream(...).boxed()`

```java
int[] raw = {2, 4, 6};
java.util.List<Integer> list =
        java.util.Arrays.stream(raw).boxed().toList();
```

`Arrays.stream(raw)` creates an `IntStream` receiving `int`s. `boxed()` converts to `Stream<Integer>`; Stream's `toList()` (available since Java 16) returns an **unmodifiable** list. Hence `list.add(8)`/`list.set(0,9)` will throw `UnsupportedOperationException`.

If you want a modifiable list:

```java
java.util.List<Integer> mutable =
        new java.util.ArrayList<>(
                java.util.Arrays.stream(raw).boxed().toList());
mutable.add(8);
```

Do not generally assume every terminal operation collecting a list returns a mutable `ArrayList`. The mutability contract must be checked explicitly.

### Using `List.of` for individual known numbers

```java
java.util.List<Integer> values = java.util.List.of(2, 4, 6);
```

Here each `int` argument is boxed into `Integer`. The result is an unmodifiable list. This form is convenient for short configuration data, **not** equivalent to `List.of(new int[]{2,4,6})`.

## 8. Converting from `List<Integer>` back to `int[]`

### Approach 1 — Manual traversal and unboxing

```java
java.util.List<Integer> list = java.util.List.of(2, 4, 6);
int[] raw = new int[list.size()];

for (int i = 0; i < list.size(); i++) {
    raw[i] = list.get(i); // Integer -> int.
}
```

For `ArrayList`, `get(i)` is typically O(1), so this approach works well. However, for some other `List`s like `LinkedList`, repeated indexed `get(i)` access can cost O(n²) overall. If the implementation is unknown or you want general-purpose code, use enhanced-for:

```java
int[] raw = new int[list.size()];
int i = 0;
for (Integer value : list) {
    raw[i++] = value; // Unboxing, can throw NPE if value is null.
}
```

If the List can be modified concurrently, reading `size()` beforehand and then iterating does not automatically guarantee a consistent snapshot. You must have synchronization/snapshot contracts suitable for the application.

### Approach 2 — Stream `mapToInt`

```java
java.util.List<Integer> list = java.util.List.of(2, 4, 6);

int[] raw = list.stream()
        .mapToInt(Integer::intValue)
        .toArray();
```

`mapToInt(Integer::intValue)` performs unboxing/conversion to `int`. If the list contains `null`, calling `intValue` on `null` throws `NullPointerException`.

If business rules wish to ignore `null`, write it explicitly, for example:

```java
int[] nonNullOnly = list.stream()
        .filter(java.util.Objects::nonNull)
        .mapToInt(Integer::intValue)
        .toArray();
```

However, **filtering out elements** can shift positional relationships, so do not apply it carelessly to indices, measurement samples, or fixed-order data. In many APIs, rejecting `null` with an explicit error is safer.

### `toArray` does not produce `int[]`

```java
java.util.List<Integer> list = java.util.List.of(2, 4, 6);
Integer[] boxedArray = list.toArray(new Integer[0]); // Valid: Integer[].
```

`List.toArray` operates on **object arrays**; there is no `toArray(new int[0])` call to automatically unbox everything. If `int[]` is needed, use a loop or `mapToInt(...).toArray()`.

## 9. Errors that only appear when using collection APIs

### `remove(1)` is not the same as `remove(Integer.valueOf(1))`

`List<Integer>` has two overloads:

- `remove(int index)` — removes by **index**.
- `remove(Object o)` — removes by **value** using object equality rules.

```java
java.util.List<Integer> nums =
        new java.util.ArrayList<>(java.util.List.of(10, 20, 30));

nums.remove(1);                  // Removes element at index 1 (value 20).
System.out.println(nums);       // [10, 30].

nums.remove(Integer.valueOf(30)); // Removes by value 30.
System.out.println(nums);          // [10].
```

`nums.remove(1)` picks the `remove(int)` overload, not “remove the number 1”. If you need to remove the value 1, write `nums.remove(Integer.valueOf(1))` or explicitly cast `remove((Object) 1)` after accounting for boxing.

With `int[]`, there is no `remove`; removing an element requires creating a new array or manually tracking a valid slice in the array.

### Comparing `Integer` with `==` has reference traps

`Integer` is an object; two references may or may not point to the same wrapper. Java caches some boxed values; do not rely on the cache for equality:

```java
Integer a = Integer.valueOf(1000);
Integer b = Integer.valueOf(1000);

System.out.println(a.equals(b)); // true.
```

You should not use `a == b` to check whether two wrappers have the same **numeric value**. It compares **object identity** when both operands are `Integer` (and there is no contextual unboxing). For nullable `Integer`, use `java.util.Objects.equals(a,b)` when null-safe equality is desired.

### `Arrays.equals` differs from `List.equals`

`int[]` does not override `equals` to compare element by element; `array1.equals(array2)` is reference comparison inherited from `Object`. To compare contents:

```java
int[] x = {1, 2};
int[] y = {1, 2};
System.out.println(java.util.Arrays.equals(x, y)); // true.
```

`List.equals`, by contrast, is defined by element order and equality:

```java
java.util.List<Integer> x = java.util.List.of(1, 2);
java.util.List<Integer> y = new java.util.ArrayList<>(x);
System.out.println(x.equals(y)); // true.
```

`Arrays.equals(int[],int[])` and `List.equals` are two different APIs; there is no default cross-type equals between `int[]` and `List<Integer>`.

## 10. Performance and memory: differences that matter at large data scales

With `int[]`, primitive elements use **4 bytes per `int` value**, excluding the array's header/alignment. The array stores values directly, typically yielding good locality during sequential traversal.

With `ArrayList<Integer>`:

- `ArrayList` normally stores **references** in an `Object[]` array, not raw 4-byte `int`s directly inside the backing array.
- `Integer` is a wrapper object; storage space, caching, and JVM optimization policies affect actual cost.
- Boxing/unboxing can carry overhead; boxing sometimes reuses cached objects or is optimized by the JVM, so one should not claim “every iteration always allocates an object”.
- `ArrayList` also manages capacity and may retain unused slots.
- `LinkedList<Integer>` typically requires linked nodes, leading to different memory/cache/access characteristics than `ArrayList`.

Exact heap footprint depends on **the JVM, pointer compression, layout, alignment, capacity, caching, object lifetimes, and JIT optimizations**. You should not treat a rule like “`List<Integer>` costs X times more” as universal across every environment.

### With millions of integers

If you perform simple integer arithmetic on millions of elements and **do not need collection APIs** or `null`, `int[]` typically offers advantages in space and sequential access. For example:

```java
long sum = 0L;
for (int value : data) {
    sum += value; // data is int[]; use long to reduce int sum overflow risk.
}
```

This snippet uses `long` for the sum variable, though the sum can still overflow `long` if the data is large enough; absolute exactness requires range-bounds analysis.

If you need add/remove operations, collection algorithms, polymorphic interfaces, and the convenience of Java Collections, `List<Integer>` can make sense. Yet because `List` is an interface, performance cannot be deduced from the declared type name alone.

### Benchmarking properly

If performance optimization genuinely matters, use a benchmark tool like **JMH** with warmup, multiple iterations, controlled data sizes, and safeguards preventing the compiler from optimizing away work. Do not draw conclusions from a single `System.nanoTime()` measurement or overly tiny loops. When measuring, distinguish **initialization/memory**, **access**, **boxing**, **GC**, and **resizing frequency** costs.

## 11. Iteration, sorting, and Stream API

### Loops

Array:

```java
int[] arr = {3, 1, 2};
for (int value : arr) {
    System.out.println(value);
}
```

List:

```java
java.util.List<Integer> nums = java.util.List.of(3, 1, 2);
for (int value : nums) { // Each Integer is unboxed to int.
    System.out.println(value);
}
```

If the List contains `null`, the loop `for (int value : nums)` can throw an NPE. Use `for (Integer value : nums)` if nullability needs handling, and define the meaning of `null` clearly.

### Sorting

```java
int[] arr = {3, 1, 2};
java.util.Arrays.sort(arr); // Mutates array, result {1,2,3}.
```

```java
java.util.List<Integer> nums =
        new java.util.ArrayList<>(java.util.List.of(3, 1, 2));
nums.sort(Integer::compareTo); // Mutates List if set is supported.
```

Sorting an unmodifiable List can throw `UnsupportedOperationException`. If the list contains `null`, a comparator that does not handle `null` can cause an NPE; the null-sorting policy should be transparent. When designing integer comparators, use `Integer.compare(a,b)` instead of subtraction `a-b` which can overflow.

### Primitive streams and boxed streams

```java
int[] raw = {1, 2, 3};
int sum = java.util.Arrays.stream(raw).sum(); // IntStream.

java.util.List<Integer> list = java.util.List.of(1, 2, 3);
int otherSum = list.stream().mapToInt(Integer::intValue).sum();
```

`IntStream` is specialized for primitives, avoiding some boxing in the pipeline. `Stream<Integer>` operates on wrappers and needs conversion to `IntStream` when primitive statistics like `sum`, `average`, or `summaryStatistics` are desired.

**Overflow warning:** `IntStream.sum()` returns `int`, which can overflow just like `int` addition. If a `long` sum is needed, map to `long` first:

```java
long total = java.util.Arrays.stream(raw).asLongStream().sum();
```

For large data exceeding `long` range, consider `BigInteger`/overflow checks.

## 12. Standalone runnable Java 17+ example

Save file `ListVsArrayDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class ListVsArrayDemo {
    public static void main(String[] args) {
        int[] raw = {2, 4, 6};
        List<Integer> boxed = new ArrayList<>();

        for (int n : raw) {
            boxed.add(n); // Boxing.
        }

        System.out.println("array length = " + raw.length);
        System.out.println("list size = " + boxed.size());

        boxed.set(0, 9);
        System.out.println("array first = " + raw[0]
                + ", list first = " + boxed.get(0));

        boxed.add(8);
        System.out.println("list after add = " + boxed);

        int[] unpacked = boxed.stream()
                .mapToInt(Integer::intValue)
                .toArray();
        System.out.println("unpacked = " + Arrays.toString(unpacked));

        List<Integer> streamList = Arrays.stream(raw).boxed().toList();
        System.out.println("stream boxed = " + streamList);
        try {
            streamList.add(8);
        } catch (UnsupportedOperationException ex) {
            System.out.println("toList is unmodifiable");
        }

        List<int[]> trap = Arrays.asList(raw);
        System.out.println("Arrays.asList(int[]) size = " + trap.size());
        System.out.println("its first element length = "
                + trap.get(0).length);

        Integer[] wrappers = {2, 4, 6};
        List<Integer> fixed = Arrays.asList(wrappers);
        fixed.set(0, 10);
        System.out.println("Integer[] after set = "
                + Arrays.toString(wrappers));
        try {
            fixed.add(8);
        } catch (UnsupportedOperationException ex) {
            System.out.println("Arrays.asList fixed size");
        }

        List<Integer> nullable = new ArrayList<>();
        nullable.add(null);
        try {
            int n = nullable.get(0); // Unboxing null.
            System.out.println(n);
        } catch (NullPointerException ex) {
            System.out.println("null unboxing: NullPointerException");
        }

        int[] defaultInts = new int[1];
        Integer[] defaultWrappers = new Integer[1];
        System.out.println("default int = " + defaultInts[0]);
        System.out.println("default Integer = " + defaultWrappers[0]);

        List<Integer> remove = new ArrayList<>(List.of(10, 20, 30));
        remove.remove(1);
        System.out.println("remove index 1 = " + remove);
        remove.remove(Integer.valueOf(30));
        System.out.println("remove value 30 = " + remove);
    }
}
```

Compile/run:

```bash
javac --release 17 ListVsArrayDemo.java
java ListVsArrayDemo
```

Stdout output:

```text
array length = 3
list size = 3
array first = 2, list first = 9
list after add = [9, 4, 6, 8]
unpacked = [9, 4, 6, 8]
stream boxed = [2, 4, 6]
toList is unmodifiable
Arrays.asList(int[]) size = 1
its first element length = 3
Integer[] after set = [10, 4, 6]
Arrays.asList fixed size
null unboxing: NullPointerException
default int = 0
default Integer = null
remove index 1 = [10, 30]
remove value 30 = [10]
```

**Explanation:** calling `set/add` on `boxed` does not mutate `raw` because they are two independent containers. `Arrays.asList(raw)` gives a `List<int[]>` of size 1. `Arrays.asList(wrappers)` gives a fixed-size list backed by the `Integer[]` array. `Stream.toList` returns an unmodifiable list; unboxing a `null` throws NPE; the `remove(int)` and `remove(Object)` overloads perform two different operations.

## 13. Should you choose `int[]` or `List<Integer>`?

| Need | Preferred choice | Reason |
| --- | --- | --- |
| Fixed-size integer sequence, high-volume processing | `int[]` | Stores primitives directly, generally good locality and low overhead |
| Java API requires `List<Integer>` | `List<Integer>` | Compatible with Collections/Streams/generic algorithms |
| Flexible additions/removals | `ArrayList<Integer>` | Resizable; watch boxing/memory |
| Only need a small constant list | `List.of(1,2,3)` | Readable, unmodifiable, forbids `null` |
| Need a view linked to an existing `Integer[]` without changing size | `Arrays.asList(integerArray)` | Backed by array; bidirectional `set` |
| Need an `int[]` from a List to call a primitive API | `mapToInt(Integer::intValue).toArray()` | Explicit structural conversion and unboxing |
| Need a List from a primitive array | `Arrays.stream(arr).boxed()` or loop | Boxes each element; choose mutability explicitly |
| Need to represent “no value” with `null` | `List<Integer>`/`Integer[]` if contract allows | Do not unbox before handling `null` |
| No `null` allowed and data is always integers | `int[]` or List validation | Eliminates risk of null elements |
| High precision per number and high performance required | `int[]`/`long[]` depending on range | Avoid floating-point or wrappers if unnecessary |
| Collection needing flexible equality/lookup/element removal | `List<Integer>` | Convenient API; must understand `remove` and equality |

### Checklist before converting back and forth

1. **What is the actual element type?** `int`, `Integer`, `int[]`, or `Integer[]`? Do not let `Arrays.asList` infer the wrong type.
2. **Does the element count need to change?** `int[]` is fixed; `ArrayList` resizes; `List.of` and `Stream.toList` are unmodifiable.
3. **Is `null` allowed?** If yes, decide the policy before unboxing; if no, validate or pick primitives.
4. **Do array and list need to stay synchronized?** `Arrays.asList(Integer[])` is backed by the array; stream boxing creates an independent container.
5. **Did you pick APIs matching the container type?** Arrays use `length`/`[]`; lists use `size()`/`get`/`set`.
6. **Is there a performance/memory risk from boxing?** Measure on real data, consider `int[]` and `IntStream`.
7. **When comparing/removing, are you matching content or reference/index?** `Arrays.equals` differs from `List.equals`, `remove(int)` differs from `remove(Object)`.
8. **Can an integer sum exceed `int`?** `IntStream.sum()` still yields `int`; use `long`/checked policies as needed.
9. **Are you depending on a specific List implementation?** `LinkedList`'s `get(i)` has different characteristics from `ArrayList`; do not assume every List has fast random access.
10. **Is there a specific Java compatibility requirement?** `Stream.toList` is from Java 16; main examples compile on Java 17+.

## 14. Common mistakes

| Mistake | Consequence | Right way |
| --- | --- | --- |
| Writing `List<int>` | Does not compile | `List<Integer>` |
| Treating `int[]` as `List<Integer>` and casting | Incompatible types | Convert via loop/stream boxing |
| `Arrays.asList(new int[]{1,2,3})` expecting a list of three numbers | Actually `List<int[]>` of size 1 | `Arrays.stream(raw).boxed().toList()` |
| Assuming `Arrays.asList(Integer[])` is resizable | `add/remove` throws exception | Copy into `new ArrayList<>(...)` |
| Assuming `Stream.toList()` returns a mutable `ArrayList` | Returned list is unmodifiable | Wrap with `new ArrayList<>(...)` |
| Calling `list.get(i)` without considering `null` | Unboxing can throw NPE | Null check/validation |
| Thinking `new ArrayList<>(capacity)` pre-populates `capacity` elements | `size()` is still 0 | Use `add` to populate |
| Using `list.remove(1)` to remove the number value 1 | Java removes index 1 | `remove(Integer.valueOf(1))` |
| Using `Integer == Integer` to compare numbers | May compare wrapper identity, result depends on objects | `equals`/`Objects.equals` or intentional unboxing |
| Using `array1.equals(array2)` to compare contents | Compares array identity | `Arrays.equals(array1,array2)` |
| Assuming a List must have contiguous storage | `LinkedList` and other implementations exist | Choose the right implementation |
| Treating `List.toArray(new Integer[0])` as `int[]` | Returns `Integer[]` | `mapToInt(...).toArray()` |
| Forgetting `IntStream.sum()` is still `int` | Can overflow | `asLongStream().sum()` and check bounds |
| Benchmarking with only a single run | Warmup/GC/JIT skew conclusions | Controlled benchmark like JMH |
| Treating nullable `Integer` as value 0 | Loses distinction between “missing” and 0 | Design explicit data semantics |

## 15. Self-check questions

1. Does `List<Integer>` store 32-bit `int` slots directly like `int[]`? Why or why not?
2. Why does `List<int>` fail to compile while `List<Integer>` is valid?
3. Write three ways to read the second element from `int[]`, `Integer[]`, and `List<Integer>`.
4. Why does `Arrays.asList(intArray)` have size 1? What is the element type of that list?
5. What kind of list does `Arrays.asList(integerArray)` return? Why is `set` valid while `add` is not?
6. If you use `Arrays.stream(raw).boxed().toList()` and then call `set`, what happens on Java 17?
7. Can `null` exist in `int[]`? What about in `ArrayList<Integer>`? When does unboxing cause an NPE?
8. Why does `new ArrayList<Integer>(100)` have `size() == 0`?
9. How does `List<Integer>.remove(1)` differ from `remove(Integer.valueOf(1))`?
10. Why is `Integer.valueOf(1000) == Integer.valueOf(1000)` not a reliable way to compare values?
11. How do you convert `List<Integer>` into `int[]` without keeping wrappers?
12. What problem does `Arrays.equals(int[],int[])` solve that `intArray.equals(otherIntArray)` does not?
13. When should you pick `int[]` over `ArrayList<Integer>` for millions of elements?
14. If you have a `List<? extends Number>`, can you add any `Number` to it? Why or why not?
15. Why does using `List<Integer>` not guarantee that `get(i)` can be called in O(1)?

## 16. Official references

- [Java SE 17 — `List<E>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): `get`, `set`, `add`, `remove`, `equals` contracts and unsupported modifications.
- [Java SE 17 — `ArrayList<E>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html): resizable list and access mechanism.
- [Java SE 17 — `Arrays.asList`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)): fixed-size list backed by an array.
- [Java SE 17 — `Arrays.stream(int[])`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#stream(int[])): creating an `IntStream` from a primitive array.
- [Java SE 17 — `IntStream.boxed()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html#boxed()): boxing a primitive stream into `Stream<Integer>`.
- [Java SE 17 — `Stream.toList()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()): unmodifiable list returned from a stream.
- [Java Language Specification `5.1.7–5.1.8](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html): boxing and unboxing conversions in Java.

**Conclusion:** `int[]` directly stores fixed-length primitive values; `List<Integer>` stores **`Integer` references** with structural behavior depending on the implementation. The two types **are not automatically interchangeable** and require boxing/unboxing when converting. Choose based on API requirements, resizability, `null`, performance, and data types; specifically avoid the `Arrays.asList(int[])` trap, `remove` overload confusion, and unmodifiable list surprises.