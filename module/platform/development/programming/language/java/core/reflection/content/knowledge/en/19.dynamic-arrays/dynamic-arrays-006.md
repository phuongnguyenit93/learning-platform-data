# Widening Conditions and Type Mismatch Errors When Assigning Array Elements with Java Reflection

In Java Reflection, the `java.lang.reflect.Array` class allows creating arrays and reading/writing elements when the type is only known at runtime. An easy point of confusion is that calling `Array.set(array, index, value)` **does not allow every numeric conversion**, nor does it behave identically to direct assignment on a reference array. A value can be written into an element when **the array's runtime type, the value's kind, and the permitted conversion rules** are compatible with each other.

Example:

```java
int[] values = new int[2];
Array.set(values, 0, Byte.valueOf((byte) 7)); // Allowed: byte -> int
Array.set(values, 1, Character.valueOf('A')); // Allowed: char -> int (65)
Array.set(values, 0, Long.valueOf(7));        // IllegalArgumentException
```

The snippet above illustrates the API after `import java.lang.reflect.Array;`. In the third call, the `long` value, even though equal to `7`, is not automatically narrowed (*narrowing*) to `int`. These checks are based on **type**, not on whether the current number fits within the representation limits of the target type.

This lesson belongs to the **Dynamic Arrays** group; the focus is on `Array.set`, `Array.setXxx`, primitive widening, reference arrays, exceptions, and validation steps before assigning via Reflection.

## 1. Dynamic Arrays and Element Types Determined at Runtime

A Java array always has a **component type** and a fixed length after creation. "Dynamic array" in the context of Reflection means **choosing the array kind/creating an array using `Class<?>` metadata at runtime**, not a self-resizing array like `ArrayList`.

```java
Class<?> componentType = int.class;
Object array = Array.newInstance(componentType, 3);

System.out.println(array.getClass().getTypeName());        // int[]
System.out.println(array.getClass().getComponentType());   // int
System.out.println(Array.getLength(array));                // 3
```

The snippet above requires `import java.lang.reflect.Array;`. `Array.newInstance(componentType, length)` returns `Object` at the API surface, but the actual object is still **a properly typed JVM array**, such as `int[]`, `String[]`, or `Number[]`.

What decides when calling `Array.set` is **the element type of the actual array object**, not merely the type of the variable holding the reference:

```java
Number[] numbers = new Integer[1];
// Declared type of the variable: Number[]
// Runtime type of the array: Integer[]
```

When writing, the JVM still enforces the runtime type `Integer[]`. A `Long` value cannot be stored into an element of `Integer[]` merely because the reference variable has type `Number[]`.

## 2. Element-Writing APIs: `Array.set` and Specialized Methods

`java.lang.reflect.Array` has the following APIs:

| API | Passed-in Value | Role |
| --- | --- | --- |
| `Array.set(Object array, int index, Object value)` | `Object`, including wrapper objects | Writes into a reference array or performs valid unbox/widen into a primitive array |
| `Array.setBoolean(array, index, boolean)` | `boolean` | Writes primitive boolean |
| `Array.setByte(array, index, byte)` | `byte` | Writes byte or widens to a compatible primitive type |
| `Array.setChar(array, index, char)` | `char` | Writes char or compatible widening |
| `Array.setShort(array, index, short)` | `short` | Writes short or compatible widening |
| `Array.setInt(array, index, int)` | `int` | Writes int or compatible widening |
| `Array.setLong(array, index, long)` | `long` | Writes long or compatible widening |
| `Array.setFloat(array, index, float)` | `float` | Writes float or compatible widening |
| `Array.setDouble(array, index, double)` | `double` | Writes double |

`Array.setXxx` supports primitive values and works only with **primitive arrays** that have an appropriate element type. It is not intended to auto-box in order to write into `Object[]`/`Number[]`. To write a wrapper into a reference array, use `Array.set` with the corresponding object.

With `Array.set`, a primitive passed in Java code will **be boxed first** because the last parameter of the API has type `Object`:

```java
int[] ints = new int[1];

Array.set(ints, 0, 5);                // Compiler boxes 5 into Integer
Array.set(ints, 0, Integer.valueOf(5)); // Equivalent argument type
Array.setInt(ints, 0, 5);             // Direct primitive-writing API
```

When receiving `Integer` to write into `int[]`, Reflection unboxes it to `int`. For another target primitive array, there may also be a **primitive widening** step.

## 3. Primitive Widening Rules When Writing Arrays

*Widening primitive conversion* is converting from one primitive to another according to Java's permitted rules without requiring an explicit cast. For example, `byte -> int`, `int -> long`, `float -> double`. Conversely, `long -> int`, `double -> float`, or `short -> byte` is *narrowing* and is not automatically performed by Reflection when writing.

The table below describes the **primitive source** and the **permitted target array element types** when writing via the appropriate `Array.setXxx` method or when `Array.set` receives the matching source wrapper:

| Source Type | Valid Target Types (Including Source Type Itself) |
| --- | --- |
| `boolean` | `boolean` |
| `byte` | `byte`, `short`, `int`, `long`, `float`, `double` |
| `short` | `short`, `int`, `long`, `float`, `double` |
| `char` | `char`, `int`, `long`, `float`, `double` |
| `int` | `int`, `long`, `float`, `double` |
| `long` | `long`, `float`, `double` |
| `float` | `float`, `double` |
| `double` | `double` |

Several important consequences:

- `byte -> char` is **not** a primitive widening. `short -> char` and `char -> short` are also not permitted automatically.
- `boolean` does not automatically convert to a number, and numbers do not automatically convert to `boolean`.
- `Integer -> long[]` is valid with `Array.set`: unboxes `Integer` to `int`, then widens `int -> long`.
- `Character -> int[]` is valid because `char -> int`, so the character `'A'` becomes the number `65`.
- `Long -> int[]` is **not** valid, even though the value `Long.valueOf(7)` can be represented by `int`.
- There is no automatic wrapper-to-wrapper conversion: `Integer` does not automatically turn into a `Long` object to be stored in `Long[]`.

**Widening does not always preserve all digits accurately.** Converting `long -> float` or `int -> float` can lose arithmetic precision due to floating-point precision limits; the widening rule still permits the conversion. Therefore, do not equate "writable" with "cannot lose precision".

## 4. `Array.set` on Primitive Arrays Performs Two Conversion Steps

With the general API `Array.set(array, index, value)`, the passed-in value has type `Object`. If the target array has a primitive element type:

1. `value` must be an object of **a corresponding primitive wrapper**, e.g., `Byte`, `Character`, `Integer`, `Long`, `Float`, `Double`, `Boolean`, `Short`.
2. Reflection unboxes the wrapper into the source primitive.
3. If the source primitive has the same type as the component type or has a **primitive widening** to the component type, the element is updated.
4. If narrowing is required, the conversion is invalid, or `value == null`, `Array.set` throws `IllegalArgumentException`.

Example:

```java
int[] ints = new int[2];

Array.set(ints, 0, Byte.valueOf((byte) 7));  // byte -> int
Array.set(ints, 1, Character.valueOf('A')); // char -> int
System.out.println(java.util.Arrays.toString(ints)); // [7, 65]
```

Conversely:

```java
Array.set(ints, 0, Long.valueOf(7L)); // IllegalArgumentException
Array.set(ints, 0, null);             // IllegalArgumentException
```

The number `7L` is not automatically narrowed even though it lies within the `int` value range; Reflection does not apply arbitrary conversions based on numeric content. Nor can `null` be unboxed to write into a primitive.

If an application wants to convert `long -> int` under a custom policy (e.g., allowing only values within the `int` range), the application must **check the value range itself, perform an intentional cast, and pass a valid `Integer`/`int`**. Do not let `Array.set` guess a narrowing policy.

## 5. `Array.setXxx` Also Allows Appropriate Widening

A false inference is that `Array.setInt` can only write to `int[]`. According to Reflection's contract, it can also write to arrays whose component type accepts widening from `int`:

```java
long[] longs = new long[1];
double[] doubles = new double[1];

Array.setInt(longs, 0, 99);       // int -> long
Array.setFloat(doubles, 0, 2.5f); // float -> double

System.out.println(longs[0]);   // 99
System.out.println(doubles[0]); // 2.5
```

Meanwhile:

```java
int[] ints = new int[1];
Array.setLong(ints, 0, 7L); // IllegalArgumentException
```

`long -> int` is narrowing, invalid for a specialized setter. `Array.setDouble(floatArray, i, value)` is also rejected because `double -> float` is narrowing.

Specialized getter functions like `Array.getInt(array, index)` have their own conversion rules when **reading**. You should not infer write rules solely from method names or from the fact that a read succeeds. In this lesson, we focus specifically on the **source value -> array component type** direction when assigning elements.

## 6. Reference Arrays: Requires Runtime Type Compatibility of the Element

If the component type is a **reference type**, `Array.set` does not use primitive widening to create a new reference object. The value must:

- Be `null`; or
- Be an object whose runtime type is compatible with the array's component type, under valid reference assignment rules.

Example:

```java
Number[] values = new Number[3];

Array.set(values, 0, Integer.valueOf(1)); // Integer extends Number
Array.set(values, 1, Long.valueOf(2));    // Long extends Number
Array.set(values, 2, null);               // Reference array accepts null
```

`Integer` and `Long` are both subtypes of `Number`, so they can be placed in `Number[]`. However, `Integer` is not a subtype of `Long` and vice versa:

```java
Long[] longValues = new Long[1];
Array.set(longValues, 0, Integer.valueOf(1)); // IllegalArgumentException
```

Reflection does not automatically perform `Integer -> int -> long -> Long` to write into `Long[]`.

### Be Careful with Array Covariance

Java allows:

```java
Number[] numbers = new Integer[1];
```

The **actual** array is still `Integer[]`. Therefore:

```java
Array.set(numbers, 0, Integer.valueOf(10)); // Succeeds
Array.set(numbers, 0, Long.valueOf(20));    // IllegalArgumentException
```

Even though the reference variable has type `Number[]`, the runtime component is `Integer`. Calling `Array.set` with an incompatible value reports `IllegalArgumentException`.

**Direct** array assignment reports a different exception:

```java
numbers[0] = Long.valueOf(20); // ArrayStoreException at runtime
```

This is a useful distinction:

| Write Path | Actual Array | Wrong-Type Value | Typical Error |
| --- | --- | --- | --- |
| `Array.set(numbers, 0, Long.valueOf(20))` | `Integer[]` | `Long` | `IllegalArgumentException` |
| `numbers[0] = Long.valueOf(20)` | `Integer[]` | `Long` | `ArrayStoreException` |

Do not lump the two exceptions into one category when catching errors and displaying diagnostics. Reflective operations and ordinary bytecode array assignments have different error-reporting contracts.

## 7. Complete, Standalone Java 17+ Example

Save all the code below into `ArrayWideningDemo.java`. The example includes dynamically created arrays via `Array.newInstance`, valid widening, rejected narrowing, reference arrays, and out-of-bounds access errors.

```java
import java.lang.reflect.Array;
import java.util.Arrays;

public class ArrayWideningDemo {
    public static void main(String[] args) {
        int[] ints = (int[]) Array.newInstance(int.class, 3);

        // Byte -> byte -> int (unboxing, widening).
        Array.set(ints, 0, Byte.valueOf((byte) 7));

        // Character -> char -> int. Character 'A' has code 65.
        Array.set(ints, 1, Character.valueOf('A'));

        // Write primitive int using specialized setter.
        Array.setInt(ints, 2, 42);
        System.out.println("int[]: " + Arrays.toString(ints));

        long[] longs = (long[]) Array.newInstance(long.class, 1);
        Array.setInt(longs, 0, 99);
        System.out.println("long[] from int: " + longs[0]);

        double[] doubles =
                (double[]) Array.newInstance(double.class, 1);
        Array.set(doubles, 0, Float.valueOf(2.5f));
        System.out.println("double[] from float: " + doubles[0]);

        // Narrowing long -> int is not automatic.
        try {
            Array.set(ints, 0, Long.valueOf(6L));
        } catch (IllegalArgumentException e) {
            System.out.println(
                    "long -> int: IllegalArgumentException");
        }

        // Primitives cannot hold null.
        try {
            Array.set(ints, 0, null);
        } catch (IllegalArgumentException e) {
            System.out.println(
                    "null -> int: IllegalArgumentException");
        }

        // short -> char is not primitive widening.
        try {
            Array.set(new char[1], 0, Short.valueOf((short) 1));
        } catch (IllegalArgumentException e) {
            System.out.println(
                    "short -> char: IllegalArgumentException");
        }

        // Declared type Number[] does not change runtime array type Integer[].
        Number[] numbers = new Integer[1];
        Array.set(numbers, 0, Integer.valueOf(10));
        System.out.println("runtime array type: "
                + numbers.getClass().getTypeName());

        try {
            Array.set(numbers, 0, Long.valueOf(20));
        } catch (IllegalArgumentException e) {
            System.out.println(
                    "Long -> Integer[] via Array.set: IllegalArgumentException");
        }

        try {
            numbers[0] = Long.valueOf(20);
        } catch (ArrayStoreException e) {
            System.out.println(
                    "Long -> Integer[] direct: ArrayStoreException");
        }

        Object[] objects = new Object[1];
        Array.set(objects, 0, Integer.valueOf(11));
        System.out.println("Object[]: "
                + objects[0].getClass().getSimpleName());

        try {
            Array.set(ints, 8, Integer.valueOf(1));
        } catch (ArrayIndexOutOfBoundsException e) {
            System.out.println(
                    "out-of-bounds: ArrayIndexOutOfBoundsException");
        }

        // General get API boxes primitive value into Integer.
        System.out.println("Array.get(int[]): "
                + Array.get(ints, 0).getClass().getSimpleName());
    }
}
```

Run with JDK 17 or later:

```bash
javac ArrayWideningDemo.java
java ArrayWideningDemo
```

Output:

```text
int[]: [7, 65, 42]
long[] from int: 99
double[] from float: 2.5
long -> int: IllegalArgumentException
null -> int: IllegalArgumentException
short -> char: IllegalArgumentException
runtime array type: java.lang.Integer[]
Long -> Integer[] via Array.set: IllegalArgumentException
Long -> Integer[] direct: ArrayStoreException
Object[]: Integer
out-of-bounds: ArrayIndexOutOfBoundsException
Array.get(int[]): Integer
```

Three groups of messages worth remembering:

1. `byte -> int`, `char -> int`, `int -> long`, and `float -> double` are all valid. Reflection applies the proper primitive widening paths.
2. `long -> int`, `short -> char`, and `null -> int` fail with `IllegalArgumentException` due to invalid conversion/value type, even though the array index is valid.
3. When writing `Long` into a runtime `Integer[]` array, `Array.set` reports `IllegalArgumentException`, whereas direct assignment through a `Number[]` variable reports `ArrayStoreException`. Both protect the runtime element type.

At the end of the example, `Array.get(ints, 0)` has return type `Object`, so the primitive `int` is boxed into an `Integer` object. This **does not turn `int[]` into `Integer[]`**.

## 8. Validating Before Assigning with Reflection

If writing a framework that receives a list of objects from an unknown data source, you should not merely look at the argument type and blindly call `Array.set`. A better sequence:

1. **Confirm the target object is an array:** `array != null` and `array.getClass().isArray()`.
2. **Determine the runtime element type:** `Class<?> component = array.getClass().getComponentType()`.
3. **Validate the index:** `0 <= index < Array.getLength(array)`.
4. **If component is primitive:** `null` is rejected; obtain the actual wrapper of `value`, map to the source primitive, and check whether primitive widening is valid.
5. **If component is reference:** `null` is accepted; other objects require `component.isInstance(value)`.
6. **Call `Array.set` once** after the policy is clear; still handle exceptions of the appropriate types because data/targets can change in a concurrent environment.

A simple helper for **reference** arrays can be written as:

```java
import java.lang.reflect.Array;

public final class ReferenceArrayGuard {
    public static void set(Object array, int index, Object value) {
        if (array == null || !array.getClass().isArray()) {
            throw new IllegalArgumentException("Expected array");
        }
        Class<?> component = array.getClass().getComponentType();
        if (component.isPrimitive()) {
            throw new IllegalArgumentException(
                    "This helper only supports reference arrays");
        }
        if (index < 0 || index >= Array.getLength(array)) {
            throw new IndexOutOfBoundsException("index=" + index);
        }
        if (value != null && !component.isInstance(value)) {
            throw new IllegalArgumentException(
                    value.getClass().getTypeName()
                    + " is not an instance of "
                    + component.getTypeName());
        }
        Array.set(array, index, value);
    }
}
```

This is a utility class **without `main`**; it can be compiled standalone, but only handles reference arrays per its stated purpose. For primitive arrays, a general helper needs a **widening table** like section 3. Do not infer widening from `component.isAssignableFrom(value.getClass())`: `Class.isAssignableFrom` checks type relationships and does **not** represent boxing/unboxing or primitive widening.

For example, `int.class.isAssignableFrom(Byte.class)` is `false`, yet `Array.set(new int[1], 0, Byte.valueOf((byte) 1))` still succeeds.

## 9. Errors to Distinguish When Operating on Arrays

| Exception | Common Situation | Resolution |
| --- | --- | --- |
| `IllegalArgumentException` | `Array.set` receives a value incompatible with the component type; or the passed object is not an array | Check the component type, source wrapper, and widening table |
| `NullPointerException` | The `array` argument of the API is `null` | Verify the array before the call; distinct from a `null` element value |
| `ArrayIndexOutOfBoundsException` | Negative index or greater than/equal to array length | Check `Array.getLength(array)` and the index range |
| `ArrayStoreException` | Direct assignment via a reference array variable where the element is incompatible with the runtime array type | Determine the actual array type, especially with array covariance |

Example where the array object is completely valid but the index is wrong:

```java
int[] data = new int[2];
Array.set(data, 2, Integer.valueOf(10)); // ArrayIndexOutOfBoundsException
```

This is an index-bounds error, not a widening error. On the other hand:

```java
int[] data = new int[2];
Array.set(data, 0, Long.valueOf(10L)); // IllegalArgumentException
```

Index 0 is valid, but `Long -> int` requires narrowing, so the error lies in the value type.

**Do not catch every `RuntimeException` and label them all generically as "type mismatch".** Accurate classification helps report actionable errors in data-import frameworks, mappers, serializers, or reflection plugins.

## 10. Cases Prone to False Assumptions

### 10.1. Small Values Do Not Turn Narrowing into Widening

`Long.valueOf(1L)` still carries type `Long`. Assigning it via `Array.set` into `int[]` fails, even though `1L` fits completely within the `int` range. If you deliberately allow range-checked narrowing:

```java
long raw = 1L;
int converted = Math.toIntExact(raw);
Array.setInt(new int[1], 0, converted);
```

`Math.toIntExact` throws `ArithmeticException` if the `long` value is outside the `int` range. This is an **explicit conversion policy of the application**, not the default rule of `Array.set`.

### 10.2. Different Wrappers Do Not Mean Primitive Compatibility

`Array.set(new Long[1], 0, Integer.valueOf(1))` fails. Although `int -> long` widening is permitted for **primitive array `long[]`**, the target `Long[]` is an **object** array, requiring a `Long` instance or `null`. To write as `Long`, create the object yourself:

```java
Long[] boxed = new Long[1];
Array.set(boxed, 0, Long.valueOf(1L));
```

### 10.3. No Casting for `boolean`

There is no widening between `boolean` and numeric types. `Array.set(new boolean[1], 0, Boolean.TRUE)` is valid; `Array.set(new boolean[1], 0, Integer.valueOf(1))` is invalid. Similarly, `Array.set(new int[1], 0, Boolean.TRUE)` is invalid.

### 10.4. Multidimensional Arrays Have an Array as Their Component

With:

```java
int[][] matrix = new int[2][3];
```

The component type of the **outer array** is `int[]`, which is a **reference type**. `Array.set(matrix, 0, new int[] {1, 2, 3})` is valid, whereas `Array.set(matrix, 0, Integer.valueOf(1))` is invalid because an outer-array element must be `int[]`, not an integer. If you want to write a numeric slot, retrieve the subarray or use two steps:

```java
Object row = Array.get(matrix, 0);
Array.setInt(row, 1, 9);
```

Only when writing `row[1]` is the component type of the **subarray** `int`. Always check the exact array level you are assigning into.

### 10.5. Widening Can Lose Precision

`long -> float` is permitted, yet `float` cannot accurately represent every 64-bit integer. Widening here means a conversion accepted by the language without an explicit cast; it **does not guarantee preserving the entire arithmetic value**. If the system requires absolute precision, you must add validation rules or use an appropriate data type.

## 11. Diagnostic Workflow When `Array.set` Fails

When seeing an exception in a reflection-driven array mapper, check in order:

1. **Actual array:** What is `array.getClass().getTypeName()`? Is it actually an array? Is it `Integer[]` even though the variable is declared `Number[]`?
2. **Actual component:** Is `getComponentType()` `int.class` or `Integer.class`? The two cases have different write rules.
3. **Index:** Is it within `[0, Array.getLength(array))`?
4. **Value:** Is it `null`? If not, what is `value.getClass().getTypeName()`?
5. **Primitive target:** Which primitive does the source wrapper correspond to? Is there a widening path in section 3's table? Did it accidentally require narrowing?
6. **Reference target:** Does `component.isInstance(value)` hold? Are you encountering array covariance?
7. **Call path:** Are you using `Array.set`, a specialized setter, or direct Java array assignment? The corresponding thrown exception can differ.
8. **Intentional conversion:** If business logic needs to parse a string, normalize a JSON number, or perform controlled numeric narrowing, do that step **before** `Array.set`, with a clear error policy.

Short example to inspect metadata:

```java
Object array = new int[2];
Object value = Long.valueOf(7L);
Class<?> component = array.getClass().getComponentType();

System.out.println("array type: "
        + array.getClass().getTypeName());
System.out.println("component: "
        + component.getTypeName());
System.out.println("value type: "
        + value.getClass().getTypeName());
```

Output:

```text
array type: int[]
component: int
value type: java.lang.Long
```

From this we deduce it requires `long -> int`, which Reflection does not permit; you must fix the value/array type or apply an explicit checked conversion.

## 12. Quick Self-Check

**Question 1.** Is `Array.set(new long[1], 0, Integer.valueOf(10))` valid?  
Yes. `Integer` is unboxed to `int`, then widened to `long`.

**Question 2.** Is `Array.set(new int[1], 0, Long.valueOf(10))` valid?  
No. `long -> int` is narrowing; `Array.set` throws `IllegalArgumentException`.

**Question 3.** Is `Array.set(new char[1], 0, Short.valueOf((short) 65))` valid?  
No. `short -> char` is not primitive widening even though the number 65 corresponds to the character `'A'`.

**Question 4.** Is `Array.set(new Number[1], 0, Integer.valueOf(1))` valid?  
Yes. `Integer` is a subtype of `Number`, so it is compatible with the reference component type `Number`.

**Question 5.** With `Number[] x = new Integer[1]`, what does `Array.set(x, 0, Long.valueOf(1))` throw?  
`IllegalArgumentException`, because the actual array object has component type `Integer`. If replaced with `x[0] = Long.valueOf(1)`, direct array assignment by the JVM may throw `ArrayStoreException`.

**Question 6.** Why is `Array.set(new Long[1], 0, Integer.valueOf(1))` not equivalent to `Array.set(new long[1], 0, Integer.valueOf(1))`?  
Because `Long[]` holds **`Long` objects** and requires reference compatibility; `long[]` holds **primitive `long`** and allows unboxing `Integer` then widening `int -> long`.

## Key Takeaways

- For **primitive arrays**, `Array.set` accepts a wrapper and then **unboxes and performs primitive widening** if the conversion path is valid. It does not automatically narrow and does not accept `null`.
- For **reference arrays**, `Array.set` requires the value to be `null` or an instance compatible with **the runtime component type**; it does not automatically convert one wrapper into another wrapper.
- `Array.setXxx` can write to wider primitive arrays according to the widening table, not only arrays of the exact same type as `Xxx`.
- **Type mismatch in `Array.set`** is typically `IllegalArgumentException`; direct assignment into a reference array of the wrong type can be `ArrayStoreException`.
- Always check **the array object, component type, index, and value** separately to distinguish type errors from out-of-bounds access errors.

Mastering the conditions of **unboxing → primitive widening** and **reference assignability by the actual array type** enables safe element writes and accurate error diagnosis when using Java Reflection with dynamic arrays.