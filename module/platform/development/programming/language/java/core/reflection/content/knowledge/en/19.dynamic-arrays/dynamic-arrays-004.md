# Array.get, Array.set, and Primitive Variants in Java Reflection

`java.lang.reflect.Array` is a `final` utility class providing **static methods** to create, read, and write Java arrays when the component type is only known at runtime. The two central operations are `Array.get(array, index)` and `Array.set(array, index, value)`. For primitive arrays, the class also provides specialized getters/setters such as `getInt`, `getLong`, `getDouble`, `setInt`, `setLong`, `setDouble`.

Unlike ordinary indexing `ints[i]`, Reflection allows a variable of type `Object` to represent an `int[]`, `String[]`, or another array type and access elements dynamically. However, **not every type conversion is allowed**: the API only allows identity (*identity*) or primitive widening (*widening*) conversions when reading/writing primitive values; narrowing conversions (*narrowing*) are rejected.

Example:

```java
int[] scores = {10, 20};
Object array = scores;

Object boxed = Array.get(array, 0);  // Integer(10)
int exact = Array.getInt(array, 1);   // 20
long widened = Array.getLong(array, 1); // 20L

Array.set(array, 0, Byte.valueOf((byte) 7)); // byte -> int: valid
Array.setInt(array, 1, 99);                  // int -> int: valid
```

This is an illustrative snippet requiring `import java.lang.reflect.Array;`. The two variables `boxed` and `exact` demonstrate the difference between a **general getter returning `Object`** and a **primitive getter returning a primitive type**. A standalone program with exact outputs is presented in section 6.

## 1. What Does "Dynamic Array" Mean Here?

Java arrays still have a **fixed length after creation**. "Dynamic array" in the context of Reflection usually means **creating an array with an element type or number of dimensions determined at runtime**, not a structure that can automatically grow in capacity like `ArrayList`.

For example, if the program receives `componentType` from configuration:

```java
Class<?> componentType = int.class;
Object array = Array.newInstance(componentType, 3);
int length = Array.getLength(array); // 3
```

`Array.newInstance(int.class, 3)` creates a runtime object that is actually an `int[]`, but the static return type of the method is `Object`. `Array.getLength(array)` returns the outer dimension size of the passed-in array. To access data, you can use `Array.get`/`Array.set` without casting to `int[]`.

When the component type is statically known, the usual approach is `new int[3]` and `array[i]`: simpler, easier to read, and usually more appropriate. Reflection is useful for mappers, serializers, factories, dependency injection, frameworks, or tools handling many previously unknown array types.

**The object passed to `Array.get/set` must actually be a Java array**, for example `int[]`, `String[]`, `Object[]`, `int[][]`; a `List<Integer>` or `ArrayList` is not an array and cannot be used directly with these functions.

## 2. Array.get(array, index): Reading as Object

Signature:

```java
public static Object get(Object array, int index)
```

`Array.get` retrieves the element at `index`, without needing to know the array type at compile time.

**If the array has a primitive component type**, the value is **boxed** into the corresponding wrapper:

| Array Element Type | Object Type Received from `Array.get` |
| --- | --- |
| `boolean` | `Boolean` |
| `byte` | `Byte` |
| `short` | `Short` |
| `char` | `Character` |
| `int` | `Integer` |
| `long` | `Long` |
| `float` | `Float` |
| `double` | `Double` |

If the array has a **reference component type**, `get` returns the element's reference value itself (which may be `null`); it does not convert it to a primitive type.

Example:

```java
Object a = new int[] {4};
Object v = Array.get(a, 0);
System.out.println(v.getClass().getSimpleName()); // Integer
```

The illustrative snippet requires importing `Array`, showing that `get` does not keep the `int` return type on its Java signature: it returns an `Object` pointing to `Integer`.

Because `Array.get` does not take an extra target type, **it does not automatically convert `int` to `long` and then box to `Long`**. An `int[]` array returns `Integer` when using `get`. To read directly as `long`, use `Array.getLong` (if the array element type is compatible).

## 3. Primitive Getters and Widening Rules When Reading

Specialized getters include `getBoolean`, `getByte`, `getShort`, `getChar`, `getInt`, `getLong`, `getFloat`, `getDouble`. Example:

```java
int x = Array.getInt(array, index);
double y = Array.getDouble(array, index);
```

The `array` object must be a **primitive array whose component type is compatible with the getter's return type**. The validation rule is:

> **Source type = component type of the array. Target type = return type of the primitive getter.** Allowed if they are the same type or there is a widening primitive conversion from source to target.

Full table:

| Getter | Readable Component Types |
| --- | --- |
| `getBoolean` | `boolean` |
| `getByte` | `byte` |
| `getShort` | `byte`, `short` |
| `getChar` | `char` |
| `getInt` | `byte`, `short`, `char`, `int` |
| `getLong` | `byte`, `short`, `char`, `int`, `long` |
| `getFloat` | `byte`, `short`, `char`, `int`, `long`, `float` |
| `getDouble` | `byte`, `short`, `char`, `int`, `long`, `float`, `double` |

Valid examples:

- `Array.getInt(new byte[]{3}, 0)` returns `3` of type `int`.
- `Array.getLong(new int[]{7}, 0)` returns `7L` of type `long`.
- `Array.getDouble(new float[]{1.25f}, 0)` returns `1.25` of type `double`.
- `Array.getInt(new char[]{'A'}, 0)` returns `65`, which is the numeric UTF-16 code unit value of `'A'`.

Examples rejected with `IllegalArgumentException`:

- `Array.getInt(new long[]{7L}, 0)`: `long -> int` is narrowing.
- `Array.getInt(new double[]{7.0}, 0)`: `double -> int` is narrowing, **even though the current value is an integer**.
- `Array.getLong(new float[]{7.0f}, 0)`: `float -> long` is not widening.
- `Array.getInt(new boolean[]{true}, 0)`: there is no conversion from boolean to numeric.
- `Array.getInt(new Integer[]{7}, 0)`: **a wrapper array `Integer[]` is not `int[]`**; primitive getters do not perform unboxing on reference arrays.

A `char[]` array cannot be read with `getShort` because `char -> short` is not widening, even though both are 16-bit: `char` is an unsigned 16-bit code unit, while `short` is a signed 16-bit integer.

### Widening Can Round Numbers

`long -> double` and `int -> float` are **valid** under widening rules, yet may **lose precision**. For example, `Array.getDouble(new long[]{9_007_199_254_740_993L}, 0)` yields a rounded `double` because `2^53+1` is not exactly representable in `double`.

This does not throw `IllegalArgumentException`, because Java separates **conversion validity** from **whether every value is preserved exactly**. Do not use `getDouble` on large integers if preserving every digit is required.

## 4. Array.set(array, index, value): Writing via Object

Signature:

```java
public static void set(Object array, int index, Object value)
```

`Array.set` determines compatibility according to the **actual component type of the target array**:

**For reference arrays** (`String[]`, `Number[]`, `Object[]`...), the value must be `null` or a reference **assignable to the component type**. Example:

```java
String[] strings = new String[2];
Array.set(strings, 0, "Java");
Array.set(strings, 1, null);
```

Writing an `Integer` into `String[]` is invalid. In the Reflection environment, `Array.set` throws `IllegalArgumentException` if the value cannot be converted for the component type.

**For primitive arrays**, the `value` parameter is `Object`, so it is usually a wrapper. `Array.set` can **unbox the wrapper** and perform primitive widening if needed, but not narrowing:

```java
int[] integers = new int[2];
Array.set(integers, 0, Byte.valueOf((byte) 7)); // byte -> int: allowed
Array.set(integers, 1, Integer.valueOf(9));     // int -> int: allowed
```

Conversely:

- `Array.set(integers, 0, Long.valueOf(1))` fails because `long -> int` is narrowing.
- `Array.set(integers, 0, Double.valueOf(1.0))` also fails.
- `Array.set(integers, 0, null)` fails: `null` cannot be unboxed into a primitive value.
- `Array.set(new boolean[1], 0, Integer.valueOf(1))` fails: boolean does not convert to numeric.

Writing an `Integer` value into an array of type `Number[]` is valid because `Integer` is a `Number`; however, this **does not** mean `Array.set` turns an arbitrary `Number` into `int` on demand.

### Distinguishing Two Kinds of Conversion

- **Reference array:** checks reference assignability (or `null`).
- **Primitive array:** checks whether the wrapper can be unboxed to a primitive and converted further via identity/widening.

In Java Reflection, "seeing a value in numeric form" is not enough. For example, `Long.valueOf(3)` does not become a valid argument for `int[]` just because the number 3 lies within the `int` range.

## 5. Primitive Setters: Widening Direction Reversed Compared to Getters

Primitive setters include `setBoolean`, `setByte`, `setShort`, `setChar`, `setInt`, `setLong`, `setFloat`, `setDouble`.

Example calls:

```java
Array.setInt(array, index, 10);
Array.setFloat(array, index, 1.25f);
```

Unlike getters, when **writing**:

> **Source type = primitive parameter of the setter. Target type = component type of the array.** Allowed if source equals target or there is a widening primitive conversion from source to target.

Full table:

| Setter | Writable Array Component Types |
| --- | --- |
| `setBoolean` | `boolean` |
| `setByte` | `byte`, `short`, `int`, `long`, `float`, `double` |
| `setShort` | `short`, `int`, `long`, `float`, `double` |
| `setChar` | `char`, `int`, `long`, `float`, `double` |
| `setInt` | `int`, `long`, `float`, `double` |
| `setLong` | `long`, `float`, `double` |
| `setFloat` | `float`, `double` |
| `setDouble` | `double` |

**Symmetric examples to remember:**

- `Array.getLong(new int[1], 0)` is valid: **reading int as long**.
- `Array.setInt(new long[1], 0, 7)` is valid: **writing int into long[]**.
- `Array.getInt(new long[1], 0)` is invalid: reading long as int is narrowing.
- `Array.setLong(new int[1], 0, 7L)` is invalid: writing long into int[] is narrowing.

Similarly, `setFloat` can write into `double[]`, but cannot write into `long[]`; `getDouble` can read `float[]`, but `getFloat` cannot read `double[]`.

**A getter and setter can both be valid on the same array, yet not necessarily for the same pair of types.** You must determine the exact *conversion direction* for each operation.

### Not "Larger Type" by Bit Count

The widening relationship is not based solely on bit count. `char` does not widen to `short`, `float` does not widen to `long`, and `boolean` does not widen to any numeric type. Follow the Java Language Specification §5.1.2 rules; do not compare the memory sizes of primitives on your own.

## 6. Standalone Java 17+ Example: Reading, Writing, and Compatibility Errors

The following example uses `Array.newInstance` to create an `int[]` dynamically, uses both general `get`/`set` and primitive getters/setters, tests several rejected cases, and traverses a two-dimensional array.

Create the file `ArrayAccessDemo.java`:

```java
import java.lang.reflect.Array;

public class ArrayAccessDemo {
    public static void main(String[] args) {
        Object numbers = Array.newInstance(int.class, 3);
        Array.set(numbers, 0, Byte.valueOf((byte) 7));
        Array.setInt(numbers, 1, 42);
        Array.setShort(numbers, 2, (short) -5);

        System.out.println(
                "ints=" + Array.getInt(numbers, 0)
                + "," + Array.getInt(numbers, 1)
                + "," + Array.getInt(numbers, 2)
        );

        Object boxed = Array.get(numbers, 0);
        System.out.println(
                "get type=" + boxed.getClass().getSimpleName()
                + ",value=" + boxed
        );
        System.out.println(
                "getLong(int[])=" + Array.getLong(numbers, 1)
        );

        long[] longs = new long[2];
        Array.setInt(longs, 0, 100);
        Array.set(longs, 1, Integer.valueOf(200));
        System.out.println(
                "longs=" + Array.getLong(longs, 0)
                + "," + Array.getLong(longs, 1)
        );

        double[] real = new double[2];
        Array.setFloat(real, 0, 1.25f);
        Array.setLong(real, 1, 300L);
        System.out.println(
                "real=" + Array.getDouble(real, 0)
                + "," + Array.getDouble(real, 1)
        );

        char[] letters = {'A'};
        System.out.println(
                "char as int=" + Array.getInt(letters, 0)
        );

        String[] words = new String[2];
        Array.set(words, 0, "java");
        Array.set(words, 1, null);
        System.out.println(
                "words=" + Array.get(words, 0)
                + "," + Array.get(words, 1)
        );

        int[][] grid = (int[][]) Array.newInstance(int.class, 2, 2);
        Object row = Array.get(grid, 0);
        Array.setInt(row, 1, 99);
        System.out.println("matrix=" + grid[0][1]);

        try {
            Array.getInt(real, 0);
        } catch (IllegalArgumentException e) {
            System.out.println("getInt(double[])=rejected");
        }

        try {
            Array.setDouble(numbers, 0, 1.0);
        } catch (IllegalArgumentException e) {
            System.out.println("setDouble(int[])=rejected");
        }

        try {
            Array.set(numbers, 0, Long.valueOf(1));
        } catch (IllegalArgumentException e) {
            System.out.println("set(Long,int[])=rejected");
        }

        try {
            Array.set(numbers, 0, null);
        } catch (IllegalArgumentException e) {
            System.out.println("set(null,int[])=rejected");
        }

        try {
            Array.set(words, 0, Integer.valueOf(3));
        } catch (IllegalArgumentException e) {
            System.out.println("set(Integer,String[])=rejected");
        }

        try {
            Array.get(numbers, 3);
        } catch (ArrayIndexOutOfBoundsException e) {
            System.out.println("index=out of bounds");
        }
    }
}
```

Commands:

```bash
javac ArrayAccessDemo.java
java ArrayAccessDemo
```

Output:

```text
ints=7,42,-5
get type=Integer,value=7
getLong(int[])=42
longs=100,200
real=1.25,300.0
char as int=65
words=java,null
matrix=99
getInt(double[])=rejected
setDouble(int[])=rejected
set(Long,int[])=rejected
set(null,int[])=rejected
set(Integer,String[])=rejected
index=out of bounds
```

Points to understand:

1. `numbers` has variable type `Object`, but the **actual object** is `int[]`. `Array.getInt` handles that array properly thanks to runtime type checking.
2. `Array.set(numbers, 0, Byte)` unboxes `Byte` and then widens `byte -> int`. `Array.setShort` also widens `short -> int`.
3. `Array.get(numbers, 0)` boxes the `int` element into `Integer`. `getLong` validly reads an `int` value as `long`.
4. Writing `int` into `long[]` via `setInt` and `Array.set` is valid in both cases. Writing `float` or `long` into `double[]` is also valid.
5. `getInt` reads a `char[]` element as the UTF-16 numeric value `65` for `'A'`.
6. `Array.set(words, 1, null)` is valid because `String[]` is a reference array. The analogous case with `int[]` is rejected.
7. `grid` is `int[][]`; its first element is an **`int[]` object**, so `Array.get(grid, 0)` returns a row, after which `Array.setInt(row, 1, 99)` can be used.
8. The `try/catch` branches intentionally test conversion or index violations; they have nothing to do with Java `private` access errors or module issues.

The output is written explicitly without relying on exception message text (which can vary across JVM versions). The example simply catches the expected exception type and prints a fixed string.

## 7. Multidimensional Arrays: Array.get Does Not Descend Through All Levels Automatically

Multidimensional arrays in Java are **arrays of arrays**. Thus, for `int[][]`:

- The outer array has component type `int[]` (a **reference type**, not primitive `int`).
- `Array.get(matrix, rowIndex)` returns an `int[]` object for the row.
- Only after obtaining the row do you call `Array.getInt(row, columnIndex)` or `Array.setInt(row, columnIndex, value)`.

Conceptual standalone code example:

```java
Object matrix = Array.newInstance(int.class, 2, 3);
Object firstRow = Array.get(matrix, 0);

Array.setInt(firstRow, 1, 88);
int result = Array.getInt(firstRow, 1); // 88
```

`Array.getInt(matrix, 0)` is **not** valid: an element of `int[][]` is `int[]`, not a primitive `int`. Use `Array.get` at the outer layer and then a primitive getter at the inner layer.

`Array.getLength(matrix)` returns `2`, while `Array.getLength(firstRow)` returns `3`. In a jagged array (`int[][]` with rows of varying lengths), you must read the length **for each row individually**, without assuming all rows have the same size.

**There is no `Array.getLength` function that returns the entire multidimensional shape at once.** The program must navigate each subarray, check for `null`, and call `getLength` at each level as needed.

## 8. Checking the Component Type Before Reading or Writing

Since `Array.get`/`Array.set` accept `Object`, a general Reflection tool must determine whether an object is an array and what its component type is:

```java
Class<?> arrayClass = array.getClass();

if (!arrayClass.isArray()) {
    throw new IllegalArgumentException("Expected an array");
}

Class<?> component = arrayClass.getComponentType();
int count = Array.getLength(array);
```

The illustrative snippet assumes the `array` variable is non-`null`. If `array` is `int[]`, `component == int.class`. If `array` is `Integer[]`, `component == Integer.class`. If it is `int[][]`, the component of the **outer** array is `int[].class`, and `component.isPrimitive()` equals `false` because `int[]` itself is a reference type.

You can choose the access approach with an explicit branch:

```java
Object value;

if (component == int.class) {
    value = Array.getInt(array, index);  // Boxing when assigning to Object.
} else if (component == double.class) {
    value = Array.getDouble(array, index);
} else {
    value = Array.get(array, index);
}
```

This is an illustrative snippet, assuming `component`, `array`, and `index` are in range and the receiver has been validated. If the tool only needs the value as `Object`, **`Array.get(array, index)` is usually already sufficient**; only choose a primitive getter when a primitive result is needed or to reduce boxing in an appropriate design.

There is no need to branch on `if (value instanceof Integer)` to decide whether to use `setInt` on `Integer[]`: an `Integer[]` array is still a reference array. The component type *of the array* determines which primitive API applies.

## 9. Common Exceptions When Using Array

| Situation | Error / Condition |
| --- | --- |
| Passing `null` instead of an array object to `get`/`set` | `NullPointerException` |
| Passing `String`, `List`, or a non-array object | `IllegalArgumentException` |
| Negative index or `index >= length` | `ArrayIndexOutOfBoundsException` |
| `getInt` on `double[]`, `Integer[]`, or an incompatible type | `IllegalArgumentException` |
| `setLong` into `int[]` | `IllegalArgumentException` due to narrowing |
| `Array.set` passing `Long` into `int[]` | `IllegalArgumentException` due to narrowing |
| `Array.set` passing `null` into a primitive array | `IllegalArgumentException` |
| `Array.set` passing `Integer` into `String[]` | `IllegalArgumentException` because it is not assignable to the component type |
| `Array.newInstance(componentType, -1)` | `NegativeArraySizeException` |
| `Array.newInstance(void.class, length)` | `IllegalArgumentException`: cannot create a `void` array |

To avoid errors, check `array != null`, `array.getClass().isArray()`, `Array.getLength(array)`, `array.getClass().getComponentType()`, and then determine whether the conversion is permitted.

**Do not catch all `IllegalArgumentException`s and assume they are Reflection access errors.** `java.lang.reflect.Array` does not need `setAccessible(true)` to read an array to which the code has a reference. The errors here are usually **not an array**, **wrong component type**, or **conversion incompatibility**.

## 10. Common Misconceptions and How to Fix Them

**Misconception 1: `Array.get` returns a primitive if the array is primitive.** No. The signature returns `Object`; primitives are boxed. To get an `int` result, use `getInt`.

**Misconception 2: The `getDouble` getter can read any numeric object.** No. It is only for **numeric primitive arrays** whose component type widens to `double`. `Double[]` and `Number[]` are not automatically unboxed for primitive getters.

**Misconception 3: `Array.set` only accepts a wrapper of the exact type.** No. For primitive arrays, it can unbox and widen; for example, `Byte` into `int[]` is valid. However, it does not narrow.

**Misconception 4: `setInt` into `short[]` will automatically truncate the excess.** No. `int -> short` is narrowing and `Array.setInt` rejects it; if a narrowing conversion is desired, the application must perform it deliberately before calling the appropriate setter.

**Misconception 5: `getInt(long[])` and `setInt(long[])` are both valid.** Only the second is valid. The **read** and **write** conversion directions differ.

**Misconception 6: A multidimensional array is a memory region that can be indexed like a flat vector with `Array.getInt`.** No. Java uses nested arrays; you must retrieve each subarray using `get`.

**Misconception 7: `Array.newInstance` creates an array that can grow in length automatically.** No. Each array's size is fixed after initialization. Use a collection such as `ArrayList` if the goal is to grow/shrink the number of elements.

**Misconception 8: Widening guarantees preserving every digit.** No. `long -> float/double` and `int -> float` can round even though the conversion is valid.

## 11. Self-Check Questions

1. Does `Array.get(new int[]{5}, 0)` return `int` or `Integer`? **Returns `Object` containing `Integer(5)`**.
2. Is `Array.getLong(new int[]{5}, 0)` valid? **Yes**, because `int -> long` is widening.
3. Is `Array.getInt(new long[]{5L}, 0)` valid? **No**, because `long -> int` is narrowing.
4. Does `Array.setInt(new long[1], 0, 7)` work? **Yes**, because writing `int -> long`.
5. Does `Array.setLong(new int[1], 0, 7L)` work? **No**, because writing `long -> int` requires narrowing.
6. Does `Array.set(new double[1], 0, Integer.valueOf(7))` work? **Yes**, unboxes `int` then widens `int -> double`.
7. Does `Array.set(new int[1], 0, Long.valueOf(1))` work? **No**, even a small value must still obey type conversion rules.
8. Does `Array.getInt(new Integer[]{7}, 0)` work? **No**, `Integer[]` is a reference array.
9. How do you read the number at `matrix[1][2]` when `matrix` is `int[][]` held in a variable of type `Object`? **`Array.get(matrix, 1)` to get the row, then `Array.getInt(row, 2)`.**
10. When an array has size 3, what error does `Array.get(a, 3)` report? **`ArrayIndexOutOfBoundsException`**.

## 12. Official Documentation

- [Oracle Java SE 21 — `java.lang.reflect.Array`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Array.html): contract for `newInstance`, `getLength`, `get/set`, primitive getters/setters, and exceptions.
- [Java Language Specification SE 21 — §5.1.2 Widening Primitive Conversion](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.2): definition of allowed primitive conversions and rounding cases.
- [Oracle Java SE 21 — `Class.isArray()` and `getComponentType()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): checking whether a class object represents an array and its component type.

**Key takeaway:** `Array.get` **reads an element as `Object`**, boxing if the element is primitive; `Array.set` **writes an `Object`**, checking reference assignability or unboxing + widening into a primitive array. Primitive getters widen from **the array element type to the return type**, while primitive setters widen from **the written value type to the array element type**. Narrowing conversions are always rejected by the API, even when the actual value appears to fit within the target type's range.