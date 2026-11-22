# How Primitive Arrays Differ from Wrapper Arrays in Java: Data Types, Equality Contracts, and Nested Structures

## 1. Distinguishing right from the declaration

In Java, a **primitive array** and a **wrapper array** are not two interchangeable ways of writing the same type. They differ in element type, storage layout, default values, ability to hold `null`, and comparison behavior.

Example:

```java
int[] primitive = {1, 2, 3};
Integer[] wrapper = {1, 2, 3};
```

These are two illustrative lines placed in an appropriate scope such as a Java method; the standalone program in section 6 will use both types.

- `int[]` holds elements of primitive type `int`. Each element is a 32-bit integer value; an element cannot be `null`.
- `Integer[]` holds **references** to objects of type `java.lang.Integer`. An element can reference an `Integer` or be `null`.
- Both variables `primitive` and `wrapper` are **references to array objects**. An array variable itself can be `null`; the difference is the **type of each element inside**.
- Java has **autoboxing** between `int` and `Integer` in appropriate contexts, such as assigning `Integer x = 1`. However, Java **does not automatically convert an entire array** `int[]` into `Integer[]`.

Comparison table:

| Characteristic | `int[]` | `Integer[]` |
| --- | --- | --- |
| Element type | Primitive value `int` | Reference `Integer` |
| Default element when `new ...[n]` | `0` | `null` |
| Can an element be `null`? | No | Yes |
| Typical memory | `int` elements are stored directly in the array | Array stores references; `Integer` objects may be stored separately |
| Reading an element as `int` | Direct | Requires unboxing; can fail if the element is `null` |
| Runtime type | `[I` | `[Ljava.lang.Integer;` |
| Using `Arrays.equals` by content | Overload `Arrays.equals(int[], int[])` | Overload `Arrays.equals(Object[], Object[])` |
| Passable to `Object[]` | No | Yes |
| Passed to `Arrays.asList` | One element of type `int[]` | One list element per `Integer` |
| Appropriate stream | `IntStream` from `Arrays.stream(int[])` | `Stream<Integer>` from `Arrays.stream(Integer[])` |

Runtime type names like `[I` and `[Ljava.lang.Integer;` are JVM array class name representations; normally when writing application code, you should use the readable declared types `int[]` and `Integer[]`.

## 2. Why can you not assign directly, cast, or auto-convert an entire array?

Autoboxing only converts **a single value** in an appropriate context:

```java
int n = 7;
Integer wrapped = n; // boxing: int -> Integer
int again = wrapped; // unboxing: Integer -> int
```

Conversely, all three lines below **do not compile** (shown to explain the error, not part of a complete program):

```java
// Integer[] boxed = new int[] {1, 2, 3}; // incompatible types
// int[] unboxed = new Integer[] {1, 2, 3}; // incompatible types
// Object[] objects = new int[] {1, 2, 3}; // incompatible types
```

Each array is an object with its own component type; there is no automatic boxing rule across all elements. A cast cannot turn an `int[]` array object into an `Integer[]` array object.

Intentional conversion:

```java
int[] numbers = {1, 2, 3};
Integer[] boxed = Arrays.stream(numbers)
        .boxed()
        .toArray(Integer[]::new);
```

This is an illustrative snippet that can be placed inside a method when `import java.util.Arrays` is present. `Arrays.stream(numbers)` creates an `IntStream`; `boxed()` creates a `Stream<Integer>`; `toArray(Integer[]::new)` creates a **new** `Integer[]` array. Conversion carries the cost of creating the array and may create/require wrapper objects.

The reverse direction must handle `null` elements:

```java
Integer[] boxed = {1, 2, 3};
int[] numbers = Arrays.stream(boxed)
        .mapToInt(Integer::intValue)
        .toArray();
```

If there is a `null` element, `Integer::intValue` will cause a `NullPointerException` at runtime. You must define the data domain policy before converting: reject null, filter out null (which can change the element count), or map null to an agreed value. Do not implicitly default null to 0 when business logic does not specify it.

## 3. The `equals()` contract: arrays differ from regular value objects

In Java, arrays **do not override `Object.equals` by content**. Therefore `array1.equals(array2)`, `Objects.equals(array1, array2)`, and the `==` operator all check for **the same reference**, if both are distinct array objects.

```java
int[] a = {1, 2, 3};
int[] b = {1, 2, 3};

System.out.println(a == b);                 // false
System.out.println(a.equals(b));            // false
System.out.println(Objects.equals(a, b));   // false
System.out.println(Arrays.equals(a, b));    // true
```

The snippet above is illustrative code placed inside a method with `import java.util.*`. An `Integer[]` array also has **the same distinction between reference and content**: two new arrays containing three identical `Integer` values are still two different **array objects**.

To compare elements of **two one-dimensional arrays of the same compatible type**, use:

- `Arrays.equals(int[], int[])` for `int[]` arrays: each pair of `int` elements is compared by value.
- `Arrays.equals(Object[], Object[])` for `Integer[]`: each pair of elements is compared via `Objects.equals`; hence two `Integer` elements with the same value are treated as equal, and two `null` elements at the same position are also equal.

**There is no `Arrays.equals(int[], Integer[])` overload to auto-box each element.** The statement below does not compile:

```java
// Arrays.equals(new int[] {1, 2}, new Integer[] {1, 2});
```

If business logic requires comparing **corresponding numeric values between the two types**, normalize to one form first, for example:

```java
int[] primitive = {1, 2, 3};
Integer[] boxed = {1, 2, 3};
Integer[] converted = Arrays.stream(primitive)
        .boxed()
        .toArray(Integer[]::new);
boolean equivalent = Arrays.equals(converted, boxed); // true
```

This is a comparison after **explicit conversion**, not two array types inherently equal under `equals`. If data can contain null, a separate business definition is needed because `int[]` cannot represent a null element.

### Do not confuse `Integer.equals` with `==` on `Integer`

`Integer.equals(Object)` compares by integer value, whereas `==` on two `Integer` variables compares same reference. `Integer` object caching for certain values can make `==` appear true in specific cases; do not rely on it to check values. For wrapper elements, `Arrays.equals(Integer[], Integer[])` is appropriate because it uses element equality logic instead of direct reference comparison.

## 4. Multidimensional arrays and `Arrays.deepEquals()`

A two-dimensional Java array is actually an **array of arrays**. Specifically:

- `int[][]` has direct element type `int[]`. The **outer array** is a reference array so it can be used as `Object[]`; the **inner `int[]` array** still holds primitives and is not an `Object[]`.
- `Integer[][]` has direct element type `Integer[]`; both the outer array and each inner array are reference arrays.
- `Arrays.equals(int[][], int[][])` uses the `Object[]` overload, then compares the `int[]` elements by array `equals` (reference). If the rows are two newly created arrays with the same content, the result may be `false`.
- `Arrays.deepEquals(int[][], int[][])` deeply checks corresponding sub-arrays, including comparing primitive contents with the appropriate overload. It is the right choice when comparing **nested structures** of the same representation.

Example:

```java
int[][] a = {{1, 2}, {3, 4}};
int[][] b = {{1, 2}, {3, 4}};

System.out.println(Arrays.equals(a, b));     // false
System.out.println(Arrays.deepEquals(a, b)); // true
```

`Arrays.deepEquals` takes two `Object[]` parameters; an `int[][]` can be passed in because the outer array holds `int[]` references. **A single `int[]` cannot be passed directly to `Arrays.deepEquals`.**

An important point in this lesson is that deep comparison **does not auto-box** between primitive and wrapper elements:

```java
int[][] primitiveNested = {{1, 2}, {3, 4}};
Integer[][] wrapperNested = {{1, 2}, {3, 4}};
System.out.println(
        Arrays.deepEquals(primitiveNested, wrapperNested)); // false
```

Although visually they have the same numbers, `int[]` and `Integer[]` rows have different types and cannot compare equal via `deepEquals` alone. To define cross-type *equivalence*, you must convert the data or write a comparator with explicit rules for the input types.

**Displaying data:** `Arrays.toString(int[])` and `Arrays.toString(Integer[])` both print one-dimensional elements; for nested arrays, `Arrays.deepToString(...)` displays sub-array contents instead of unreadable reference representations.

## 5. Consequences for null, memory, generics, and collections

### 5.1. Primitive arrays cannot hold null elements

`new int[3]` contains three default `0` values. `new Integer[3]` contains three **null references**. Reading `int x = boxed[0]` performs unboxing; if `boxed[0]` is null, it throws `NullPointerException`. Conversely, `Arrays.equals(Integer[], Integer[])` can compare two arrays that both have null at the corresponding position without unboxing them.

When external data has a notion of “missing value”, wrapper arrays allow representing null but also increase data validation requirements. Do not use `0` to implicitly represent a missing value if `0` is a valid value in the data domain.

### 5.2. Memory and performance costs

An `int[]` array stores primitive values directly, typically using less memory and offering better access locality than `Integer[]` containing references. `Integer[]` can cause the program to allocate additional objects, increasing boxing/unboxing overhead and garbage collection pressure. However, the JVM may optimize or reuse some wrapper objects, so **do not conclude a fixed overhead number** or performance ranking for every workload. When the choice significantly impacts the system, run benchmarks with actual data and JVM.

### 5.3. Reference arrays and generics

`Integer[]` works wherever `Object[]` is accepted because `Integer` is a reference subtype of `Object`. `int[]` **cannot** be used where `Object[]` is expected because the `int` element is primitive. However, both array objects are `Object`s and can be passed to an `Object` parameter.

`List<Integer>` accepts `Integer` elements; Java generics do not accept primitives as type arguments, e.g., `List<int>` is invalid. You can use `Integer[]` or `List<Integer>` when APIs require reference types, and `int[]` when operating in bulk on primitive data without needing null.

Reference arrays are *covariant*: `Integer[]` can be assigned to `Object[]`, but if you try to write a `String` into it through the `Object[]` reference, Java will throw `ArrayStoreException` at runtime. This covariance **does not apply** to turn `int[]` into `Object[]`.

### 5.4. `Arrays.asList()` is a common trap

`Arrays.asList` is a varargs method taking a reference type. Therefore:

```java
int[] raw = {1, 2, 3};
Integer[] boxed = {1, 2, 3};

System.out.println(Arrays.asList(raw).size());   // 1
System.out.println(Arrays.asList(boxed).size()); // 3
```

With `raw`, the entire `int[]` object becomes **a single element** in `List<int[]>`; there is no auto-boxing of the three numbers at all. With `boxed`, each array element becomes a `List<Integer>` element. The list returned by `Arrays.asList` has fixed size and is backed by the input array; if you need a list where elements can be added/removed, create another appropriate list.

To create a list of numbers from a primitive array:

```java
List<Integer> list = Arrays.stream(raw).boxed().toList();
```

This snippet uses Java 17 (`Stream.toList()` has been available since Java 16) and requires `import java.util.*`. The result is a list that does not allow structural/content modification via `List` mutator operations; if a mutable list is needed, `new ArrayList<>(list)` can be used.

## 6. Complete Java 17+ program and verified output

Save all code below as **`PrimitiveWrapperArraysDemo.java`**; the example focuses on runtime types, array equality contracts, deep comparison, and differences that commonly cause bugs.

```java
import java.util.*;

public class PrimitiveWrapperArraysDemo {
    public static void main(String[] args) {
        int[] raw = {1, 2, 3};
        int[] rawCopy = {1, 2, 3};
        Integer[] boxed = {1, 2, 3};
        Integer[] boxedCopy = {1, 2, 3};

        System.out.println("primitive class = " + raw.getClass().getName());
        System.out.println("wrapper class = " + boxed.getClass().getName());
        System.out.println("primitive is Object = " + (raw instanceof Object));
        System.out.println("primitive is Object[] = "
                + (((Object) raw) instanceof Object[]));
        System.out.println("wrapper is Object[] = " + (boxed instanceof Object[]));

        System.out.println("primitive content equal = "
                + Arrays.equals(raw, rawCopy));
        System.out.println("wrapper content equal = "
                + Arrays.equals(boxed, boxedCopy));
        System.out.println("Objects.equals primitive arrays = "
                + Objects.equals(raw, rawCopy));
        System.out.println("Objects.equals wrapper arrays = "
                + Objects.equals(boxed, boxedCopy));
        System.out.println("mixed deep equality = "
                + Arrays.deepEquals(new Object[] {raw}, new Object[] {boxed}));
        System.out.println("primitive content = " + Arrays.toString(raw));
        System.out.println("wrapper content = " + Arrays.toString(boxed));

        Integer[] converted = Arrays.stream(raw)
                .boxed()
                .toArray(Integer[]::new);
        System.out.println("converted content = "
                + Arrays.toString(converted));
        System.out.println("after conversion equal = "
                + Arrays.equals(converted, boxed));

        Integer[] withNull = {1, null, 3};
        System.out.println("wrapper with null = " + Arrays.toString(withNull));
        System.out.println("wrapper null equal = "
                + Arrays.equals(withNull, new Integer[] {1, null, 3}));
        try {
            int item = withNull[1];
            System.out.println(item);
        } catch (NullPointerException exception) {
            System.out.println("unboxing null = NullPointerException");
        }

        int[][] primitiveNested = {{1, 2}, {3, 4}};
        Integer[][] wrapperNested = {{1, 2}, {3, 4}};
        System.out.println("primitive nested is Object[] = "
                + (((Object) primitiveNested) instanceof Object[]));
        System.out.println("primitive deep equal = "
                + Arrays.deepEquals(
                        primitiveNested, new int[][] {{1, 2}, {3, 4}}));
        System.out.println("wrapper deep equal = "
                + Arrays.deepEquals(
                        wrapperNested, new Integer[][] {{1, 2}, {3, 4}}));
        System.out.println("nested cross-type deep equal = "
                + Arrays.deepEquals(primitiveNested, wrapperNested));

        System.out.println("asList primitive size = "
                + Arrays.asList(raw).size());
        System.out.println("asList wrapper size = "
                + Arrays.asList(boxed).size());
    }
}
```

Run from the directory containing the file:

```bash
javac PrimitiveWrapperArraysDemo.java
java PrimitiveWrapperArraysDemo
```

Output:

```text
primitive class = [I
wrapper class = [Ljava.lang.Integer;
primitive is Object = true
primitive is Object[] = false
wrapper is Object[] = true
primitive content equal = true
wrapper content equal = true
Objects.equals primitive arrays = false
Objects.equals wrapper arrays = false
mixed deep equality = false
primitive content = [1, 2, 3]
wrapper content = [1, 2, 3]
converted content = [1, 2, 3]
after conversion equal = true
wrapper with null = [1, null, 3]
wrapper null equal = true
unboxing null = NullPointerException
primitive nested is Object[] = true
primitive deep equal = true
wrapper deep equal = true
nested cross-type deep equal = false
asList primitive size = 1
asList wrapper size = 3
```

Looking at the output:

1. `primitive class` and `wrapper class` demonstrate two different **runtime array types**, despite having the same three numeric values.
2. `raw` is an `Object` but **not** an `Object[]`; `boxed` is an `Object[]`. The test on `raw` casts up to `Object` before using `instanceof Object[]` so that it is a valid Java expression evaluating to `false`.
3. Two separate pairs of arrays are equal by **content** with `Arrays.equals`, yet differ under `Objects.equals` because they are not the same object.
4. Deep comparison between `new Object[]{raw}` and `new Object[]{boxed}` is `false`; primitive array data is not automatically boxed in the deep comparison algorithm.
5. After converting `raw` into a new `Integer[]`, `Arrays.equals(converted, boxed)` is `true`: conversion gives both sides the same **appropriate representation type** allowing content comparison.
6. `Integer[]` containing `null` is valid and can be compared with `Arrays.equals`, but reading the null element as `int` throws `NullPointerException`.
7. `int[][]` can be used as `Object[]` at the **outer level**. `Arrays.deepEquals` is `true` when comparing two corresponding primitive matrices, or two corresponding wrapper matrices; cross-comparing the two representations remains `false`.
8. `Arrays.asList(raw)` has size 1; `Arrays.asList(boxed)` has size 3. This is a difference in varargs elements, not lost data.

## 7. Choosing the right comparison method in real problems

| What you want to check | API to use | Notes |
| --- | --- | --- |
| Do two references point to the same array object? | `a == b` or `Objects.equals(a, b)` | For arrays, `Objects.equals` still compares references |
| Do two `int[]` have the same number sequence? | `Arrays.equals(a, b)` | Compares each primitive value |
| Do two `Integer[]` have the same value sequence, including null? | `Arrays.equals(a, b)` | Elements use object equality; null is handled |
| Do two `int[][]` or `Integer[][]` have matching nested content? | `Arrays.deepEquals(a, b)` | Used at the outer array level of nested arrays |
| Do an `int[]` and an `Integer[]` represent the same sequence of numbers? | Convert to the same type then `Arrays.equals` | Define how to handle null before comparing |
| Display a one-dimensional array | `Arrays.toString(array)` | Avoid `array.toString()` |
| Display a nested array | `Arrays.deepToString(array)` | Displays contents of sub-arrays |
| Create a `List<Integer>` from `int[]` | `Arrays.stream(raw).boxed().toList()` | Do not use `Arrays.asList(raw)` if you want one list element per number |

## 8. Common mistakes and how to self-verify

1. **Believing autoboxing applies to an entire array:** `Integer[] b = intArray` is a type error. You must create a new array and convert each element.
2. **Calling `Objects.equals` or `array.equals` to compare content:** for both array kinds, it still checks for the same reference. Use `Arrays.equals` for one-dimensional arrays.
3. **Using `Arrays.equals` on two-dimensional arrays and expecting deep comparison:** direct elements of the outer array are sub-array references; for two separate matrices, `Arrays.deepEquals` is normally needed.
4. **Expecting `Arrays.deepEquals` to convert `int[]` to `Integer[]`:** the function does not perform such integer type conversions. Explicit normalization is required.
5. **Forgetting about null in `Integer[]`:** unboxing null throws `NullPointerException`; primitive arrays cannot have null elements.
6. **Confusing `Arrays.asList(int[])` with a list of individual numbers:** it creates a single-element list of `int[]`. Use stream `boxed()` or convert to wrapper first.
7. **Using `==` on two `Integer` objects to compare values:** that is reference comparison and can depend on caching. Use `Objects.equals`/`Integer.equals` when value equality is needed.
8. **Assuming every `Integer[]` element is created separately:** caching, autoboxing, and JVM optimizations can affect identity; do not build equality contracts based on how wrapper instances are created.

**Self-check:** Consider `int[][] a = {{1, 2}}`, `int[][] b = {{1, 2}}`, and `Integer[][] c = {{1, 2}}`. Why can `Arrays.equals(a, b)` be `false` while `Arrays.deepEquals(a, b)` is `true`, and yet `Arrays.deepEquals(a, c)` is `false`? Because `Arrays.equals` at the outer array compares two `int[]` references that are two different objects; `deepEquals` descends into the contents of the two corresponding `int[]` arrays; however, it **does not auto-box** an `int[]` row into `Integer[]` when comparing across types.

Key point: `int[]` and `Integer[]` may look alike when printed, but they **have different data types and operation contracts**. Choose primitive arrays when you need non-null values and direct numeric operations; choose wrapper arrays when APIs require objects, generics, or need to represent null. When comparing, clearly distinguish **reference equality**, **one-dimensional content equality**, **deep equality of nested structures**, and **equality after explicit conversion**.