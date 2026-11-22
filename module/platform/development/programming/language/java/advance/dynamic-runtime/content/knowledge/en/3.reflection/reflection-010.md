# 3.10. Creating and Manipulating Arrays with Unknown Component Types Using java.lang.reflect.Array

## Learning Objectives

After this lesson, you will be able to:

1. Explain why when **the element type is only known at runtime**, you cannot directly use the syntax `new T[n]` or `new SomeType[n]` with a type name that is undetermined at compile time.
2. Use `java.lang.reflect.Array` to create an array with the exact **component type**, even when it is `int`, `boolean`, `String`, a custom class, or an array type itself.
3. Read the length, get/set elements, check the runtime type, and work with multidimensional arrays without casting every array to `Object[]`.
4. Distinguish between boxing/unboxing, primitive widening, reference assignment, index errors, and type errors.
5. Build a general-purpose utility that handles both primitive arrays and reference arrays; know when to return to a statically typed API.

**Context:** Java supports reflection so frameworks can map data from schemas, metadata, annotations, plugins, or type names in configuration. For example, a serializer might receive `Class<?> componentType` at runtime and need to create the exact `String[]`, `long[]`, or `Customer[]` without knowing which kind it is when writing the source code.

## 1. Why Is `java.lang.reflect.Array` Needed?

The normal way:

```java
String[] names = new String[3];
int[] scores = new int[3];
```

In these two lines, the compiler already knows `String` and `int`. If you only receive a variable `Class<?> componentType`, you **cannot** write `new componentType[3]`: this is a variable holding type information, not a type name in Java syntax. With a generic `T`, you also cannot directly write `new T[3]` because of type erasure.

In that case, use:

```java
Class<?> componentType = String.class; // Illustration: this value could come from metadata.
Object array = java.lang.reflect.Array.newInstance(componentType, 3);
```

Even though the declared type of the variable `array` is `Object`, **the runtime type of the created object is still `String[]`**. The JVM does not create an `Object[]` as a substitute for `String[]`. You must keep two concepts separate:

- **The type of the variable at compile time:** `Object`, because `Array.newInstance(...)` must be able to return both `int[]` and `String[]`.
- **The actual type of the object at runtime:** for example `int[]`, `String[]`, `java.time.LocalDate[]`; the JVM uses this type to check assignments and element access.

Every Java array is an object, has a fixed length, and is indexed from `0` to `length - 1`. An array can contain primitives, references, or another array type as elements.

## 2. Core API of `java.lang.reflect.Array`

`Array` belongs to the `java.lang.reflect` package and provides **static methods**; you do not use `new Array(...)`.

| API | Role | Key Points |
| --- | --- | --- |
| `Array.newInstance(Class<?> componentType, int length)` | Creates an array with the given component type and length | Returns `Object`; runtime type matches `componentType` |
| `Array.newInstance(Class<?> componentType, int... dimensions)` | Creates a multidimensional array | The passed dimensions are initialized; total dimensionality also depends on `componentType` if it is already an array type |
| `Array.getLength(Object array)` | Reads the length of an array | Applies to both `int[]` and `Object[]`; does not accept non-array objects |
| `Array.get(Object array, int index)` | Gets an element as `Object` | Primitive values are **boxed** into their wrapper |
| `Array.set(Object array, int index, Object value)` | Writes an element | If it is a primitive array, an unboxing step occurs and only valid conversions are accepted |
| `Array.getInt(...)`, `getLong(...)`, `getBoolean(...)`, ... | Reads an element as a specific primitive type | Can perform appropriate primitive **widening**; avoids boxing when used properly |
| `Array.setInt(...)`, `setLong(...)`, `setBoolean(...)`, ... | Writes a specific primitive type | Only accepts identity or widening to the target element type |

`getXxx/setXxx` has variants for all eight primitive types: `boolean`, `byte`, `char`, `short`, `int`, `long`, `float`, and `double`.

**Key takeaway:** there is no single common `Object[]` type that can hold every array. `int[]` is an `Object`, but **not** an `Object[]`, because its elements are primitive values. `Array.getLength/get/set` bridges that gap.

## 3. Creating a One-Dimensional Array from a Runtime Type

### 3.1. Reference Arrays

```java
Class<?> type = String.class;
Object dynamicNames = Array.newInstance(type, 2);
Array.set(dynamicNames, 0, "Java");
Array.set(dynamicNames, 1, "Reflection");

String[] names = (String[]) dynamicNames; // Only cast after validating the runtime type.
```

This is an **illustrative snippet, used in a context where `java.lang.reflect.Array` is already imported**. `dynamicNames.getClass() == String[].class` returns `true`. Newly created reference array elements default to `null`.

When a type comes from a fully qualified name in configuration, you can resolve `Class<?>` with `Class.forName("java.lang.String")` and pass it to `Array.newInstance`. `Class.forName("int")` is not the way to look up the primitive `int`; primitives have a class literal `int.class` (or `Integer.TYPE`). Do not accept arbitrary class names from untrusted input and blindly load any class in the application.

### 3.2. Primitive Arrays

```java
Object dynamicScores = Array.newInstance(int.class, 3);
Array.setInt(dynamicScores, 0, 10);
Array.set(dynamicScores, 1, Integer.valueOf(20));
int value = Array.getInt(dynamicScores, 1); // 20
```

This is also an illustrative snippet in a context where `Array` is already imported. The runtime type is `int[]`, not `Integer[]`. Newly created `int[]` elements default to `0`. `Array.set` accepts `Integer` and unboxes it appropriately into `int`; `Array.get` will return `Integer` when reading an `int` value.

Do not do this:

```java
Object array = Array.newInstance(int.class, 3);
Object[] wrong = (Object[]) array; // ClassCastException at runtime!
```

If you know for sure the element type is `int`, you can cast to `int[]` and use direct syntax. If you do not know the type at compile time, continue using the `Array` APIs.

### 3.3. Checking Type and Length

```java
Object array = Array.newInstance(String.class, 3);

Class<?> arrayClass = array.getClass();
boolean isArray = arrayClass.isArray();            // true
Class<?> elementClass = arrayClass.getComponentType(); // String.class
int length = Array.getLength(array);               // 3
```

This illustrative snippet imports `Array` as above. `Class.getComponentType()` returns the component **of one dimension**; for `int[][]`, it returns `int[].class`, not `int.class` immediately. If you need the base type, loop `getComponentType()` until the result is no longer an array class.

`Array.getLength(...)` returns **the number of elements in the current dimension**, and does not automatically count all values in a multidimensional structure. To know the length of a row, get that row using `Array.get(matrix, rowIndex)` and then call `Array.getLength(row)`.

## 4. Reading/Writing Elements and Type Conversion Rules

### 4.1. General `get` and `set`

For any array, `Array.get(array, i)` returns an `Object`. If the array holds references, you receive the corresponding reference; if it holds primitives, the value is boxed into `Integer`, `Double`, `Boolean`, etc. Therefore, generic operations using `get/set` are very useful for frameworks, but in tight loops they can incur boxing/unboxing overhead.

`Array.set(array, i, value)` respects the runtime type of the array. For example, `String[]` accepts `String` or `null`, and does not accept an `Integer`. `int[]` accepts `Integer` (unboxed to `int`), but does not accept `Long` by narrowing from `long` to `int`.

### 4.2. `getXxx` and `setXxx` for Primitives

You can use typed methods when you know the primitive conversion relationships:

| Call | Valid? | Explanation |
| --- | --- | --- |
| `Array.getInt(new short[] {7}, 0)` | Yes | Reads `short` and widens it to `int` |
| `Array.getLong(new int[] {7}, 0)` | Yes | Reads `int` and widens it to `long` |
| `Array.setInt(new long[1], 0, 7)` | Yes | Writes `int` to a `long` element via widening |
| `Array.setLong(new int[1], 0, 7L)` | No | `long → int` is narrowing; `IllegalArgumentException` |
| `Array.getInt(new Integer[] {7}, 0)` | No | `getInt` applies to primitive element types with a suitable conversion; it does not automatically unbox `Integer[]` |
| `Array.setInt(new Integer[1], 0, 7)` | No | `setInt` does not automatically turn a typed primitive write into an assignment to a wrapper array |
| `Array.set(new int[1], 0, null)` | No | `null` cannot be unboxed to `int` |

**Note:** widening is a supported type conversion rule, not a guarantee of preserving every numeric value with absolute precision when converting to floating point (for example, `long → float` can lose precision). `boolean` does not widen to numeric types.

### 4.3. Exceptions to Anticipate

| Situation | Common Error |
| --- | --- |
| `componentType == null` when creating an array | `NullPointerException` |
| `componentType == void.class` | `IllegalArgumentException` |
| Negative size | `NegativeArraySizeException` |
| Reading length / interacting with a non-array object | `IllegalArgumentException` |
| Array argument is `null` when reading/writing/getting length | `NullPointerException` |
| Negative index or ≥ length | `ArrayIndexOutOfBoundsException` |
| Writing wrong element type, invalid unboxing, or narrowing | `IllegalArgumentException` |
| Casting an `int[]` to `Object[]` | `ClassCastException` |

`Array.newInstance(componentType, dimensions)` also rejects an empty dimensions list and arrays whose total number of dimensions exceeds the JVM limit (255 dimensions). Do not use exceptions for normal control flow: check `array != null`, `getClass().isArray()`, length/index, element type, and input validity beforehand.

## 5. Multidimensional Arrays and Jagged Arrays

In Java, `int[][]` is actually an “array of `int[]`”. This explains why reflection accesses each dimension as a separate array.

### 5.1. Pre-creating All Specified Dimensions

```java
Object matrix = Array.newInstance(int.class, 2, 3); // Runtime: int[2][3]
Object secondRow = Array.get(matrix, 1);             // Runtime: int[3]
Array.setInt(secondRow, 2, 9);
int cell = Array.getInt(Array.get(matrix, 1), 2);    // 9
```

This is an illustrative snippet with `Array` imported. The new structure has 2 rows, each with 3 `int` cells defaulting to `0`. Get a row via `Array.get(matrix, 1)` and continue using the `Array` API. If the caller knows the exact type, `matrix` can be cast to `int[][]`.

### 5.2. Creating a Jagged Array

```java
Object rows = Array.newInstance(int[].class, 2); // Runtime: int[][]
// Initially both rows are null, because the elements of the outer array have type int[].
Array.set(rows, 0, new int[] {1});
Array.set(rows, 1, new int[] {2, 3, 4});
```

`Array.newInstance(int[].class, 2)` creates an `int[][]` with **two references to rows**, with the rows initially unallocated. We assign sub-arrays of different lengths, creating a jagged structure. Conversely, `Array.newInstance(int.class, 2, 3)` already allocates rows of length 3 according to all passed dimensions.

When `componentType` **is already an array type**, the total number of dimensions = the dimensions of `componentType` + the number of dimensions passed in. For example, `Array.newInstance(String[].class, 2)` creates `String[][]`; `Array.newInstance(String[].class, 2, 3)` creates `String[][][]` with the first two dimensions allocated and the `String[]` arrays at the last level initially `null`.

This is useful when you want to build a multidimensional array from metadata, but you need to control the sizes to avoid excessive memory allocation.

## 6. Complete Example: Creating, Reading, Writing, Manipulating, and Error Checking

Create the file **`ReflectArrayDemo.java`**. The program below runs standalone on Java 17+ and uses a `reverseCopy` method that handles both primitive arrays and reference arrays **without casting the input to `Object[]`**.

```java
import java.lang.reflect.Array;
import java.util.Arrays;

public class ReflectArrayDemo {
    static Object reverseCopy(Object source) {
        if (source == null || !source.getClass().isArray()) {
            throw new IllegalArgumentException("Expected an array");
        }

        Class<?> componentType = source.getClass().getComponentType();
        int length = Array.getLength(source);
        Object result = Array.newInstance(componentType, length);

        for (int i = 0; i < length; i++) {
            Array.set(result, i, Array.get(source, length - 1 - i));
        }
        return result;
    }

    public static void main(String[] args) {
        Object scores = Array.newInstance(int.class, 3);
        Array.setInt(scores, 0, 2);
        Array.set(scores, 1, Integer.valueOf(3));
        Array.setInt(scores, 2, 5);

        System.out.println("type=" + scores.getClass().getTypeName());
        System.out.println("length=" + Array.getLength(scores));
        System.out.println("values=" + Arrays.toString((int[]) scores));
        System.out.println("boxed=" + Array.get(scores, 1).getClass().getSimpleName());
        System.out.println("reverse=" + Arrays.toString((int[]) reverseCopy(scores)));

        Object tags = Array.newInstance(String.class, 2);
        Array.set(tags, 0, "JVM");
        Array.set(tags, 1, "Reflection");
        System.out.println("tags=" + Arrays.toString((String[]) tags));

        Object matrix = Array.newInstance(String.class, 2, 3);
        Array.set(Array.get(matrix, 1), 2, "X");
        System.out.println("matrix=" + Arrays.deepToString((Object[]) matrix));

        Object jagged = Array.newInstance(String[].class, 2);
        Array.set(jagged, 0, new String[] {"A"});
        Array.set(jagged, 1, new String[] {"B", "C"});
        System.out.println("jagged=" + Arrays.deepToString((Object[]) jagged));

        try {
            Array.set(scores, 0, Long.valueOf(7L));
        } catch (IllegalArgumentException expected) {
            System.out.println("narrowing=" + expected.getClass().getSimpleName());
        }
    }
}
```

Compile and run in the directory containing the file:

```bash
javac --release 17 ReflectArrayDemo.java
java ReflectArrayDemo
```

**Exact stdout:**

```text
type=int[]
length=3
values=[2, 3, 5]
boxed=Integer
reverse=[5, 3, 2]
tags=[JVM, Reflection]
matrix=[[null, null, null], [null, null, X]]
jagged=[[A], [B, C]]
narrowing=IllegalArgumentException
```

### Analysis of Each Result

- `type=int[]` confirms that `Array.newInstance(int.class, 3)` creates a **true primitive array**, even though the result is held in an `Object` variable.
- `Array.getLength(scores)` works with `int[]`, without requiring a cast to `Object[]`.
- `Array.setInt` writes `int` directly; `Array.set(..., Integer)` unboxes to `int`; `Array.get(scores, 1)` boxes to `Integer` as shown by `boxed=Integer`.
- `reverseCopy` reads `componentType` **from the source array itself**, creates a destination array of the same type, and copies in reverse using `Array.get/set`. It works with `int[]`, `String[]`, `boolean[]`, or other reference arrays. The method reverses **the element order of one dimension**; if elements are sub-arrays or objects, this is a reference copy at the element level, not a deep clone.
- `matrix` uses `newInstance(String.class, 2, 3)`: all 3-element rows are already created, with reference values defaulting to `null`. `Arrays.deepToString` is used because the `String[][]` object can be viewed as `Object[]` at the outer dimension.
- `jagged` uses `String[].class` as the component type: the two rows are only allocated when we assign them.
- The last call tries to put a `Long` into an `int` element, which requires narrowing from `long` to `int` and therefore throws `IllegalArgumentException`. The fact that the number `7` is within the `int` range **does not** cause reflection to automatically allow narrowing.

### Why Does the `reverseCopy` Approach Preserve the Actual Type?

When the input is `String[]`, `source.getClass().getComponentType() == String.class`, so `Array.newInstance` also creates `String[]`. For `int[]`, the component type is `int.class`, so the new array is also `int[]`. We do not create `new Object[length]` because doing so would **lose the original array type** and could not substitute for `int[]` or `String[]` in all contexts.

This is a common strategy when a framework receives an `Object` confirmed to be an array: **discover the actual type → create an array of the exact type → access via `Array` → convert to a specific type at the boundary if the contract allows**.

## 7. Combining with Generics and Understanding the Limitations

When your code **knows the reference type via `Class<T>`**, you can create a helper that returns `T[]`:

```java
static <T> T[] newReferenceArray(Class<T> type, int length) {
    if (type == null || type.isPrimitive()) {
        throw new IllegalArgumentException("Expected a reference type");
    }
    @SuppressWarnings("unchecked")
    T[] result = (T[]) Array.newInstance(type, length);
    return result;
}

// Used in a program that has imported java.lang.reflect.Array:
String[] names = newReferenceArray(String.class, 2);
```

This is an **illustrative snippet that must be placed inside a class containing the static method**, not a standalone Java file. The unchecked cast line is justified when `type` is the exact token of the reference type `T`; the helper blocks primitives to avoid casting `int[]` to a reference array. Do not use a raw `Class` or unsafe casts to bypass the type system.

Note the distinctions:

- `String[]` retains its element type at runtime; assigning an `Integer` through an incorrect reference alias can be prevented by the JVM.
- `List<String>` is subject to generic type erasure: reflection cannot create an “array of `List<String>`” with all generic parameters guaranteed at runtime using only `List.class`.
- Arrays are **covariant**: `Object[] alias = new String[1]` compiles, but `alias[0] = Integer.valueOf(1)` will throw `ArrayStoreException`. Reflection also checks assignments against the actual type, though the exception thrown may differ depending on the API called.
- You should not try to use `Object[]` to generalize all arrays; primitive arrays are the clearest counterexample.

If you need to store a collection of elements that can be added/removed and **do not need an exact runtime array type**, a `List<?>` or a collection with a generic contract is usually easier to maintain. Arrays have a fixed length; to change the length, you must create a new array and copy the data (for example, `System.arraycopy` if you already have two compatible arrays).

## 8. Real-World Use Cases and Design Patterns

### 8.1. Schema-Driven Serializer or Mapper

A schema might declare “this is an array of `Customer`, `String`, or `double`”. The framework reads the component type, validates the data, allocates using `Array.newInstance`, and then populates each element. For primitives, it must verify that input values can be converted according to the rules, rather than relying on arbitrary casts.

Typical flow:

1. Obtain `Class<?> componentType` from **validated** metadata.
2. Check the maximum allowed size and allocate the array with `newInstance`.
3. For each item, convert the source data to a valid Java type; check `null`/primitive, reference assignability, and numeric conversion.
4. Write using `Array.set` or the appropriate `setXxx` method; report an error with the item position when conversion is invalid.
5. Return the array through a defined contract; avoid forcing clients to guess and cast.

### 8.2. Reflection with an Array-Typed `Field`

A field can carry metadata for an array type:
- `Field.getType().isArray()` identifies it as an array field.
- `Field.getType().getComponentType()` gets the one-dimensional component type.
- `Array.newInstance(componentType, n)` creates a compatible array to assign to the field, **if** the caller has permission to set the field, the target object is valid, and the data has the right type.

Clearly distinguish `Field.get(obj)` / `Field.set(obj, value)` for getting/setting **the entire field**, from `Array.get(array, i)` / `Array.set(array, i, value)` for manipulating **individual elements** of the array object. `Field` access control still must obey Java/module rules; `Array` cannot bypass a blocked private field.

### 8.3. Plugins and Dynamic Configuration

You can select the element type by plugin at runtime and then create an array to serve a legacy API that requires a specifically typed array. Discovery/validation should be performed at the plugin boundary, keeping interfaces clear so that reflective operations are not scattered throughout business logic.

## 9. Performance, Memory, and Operational Limits

- `Array.get/set` works for any array type, but `Object` operations with primitive arrays can cause boxing/unboxing; a direct `int[]` code path or `getInt/setInt` APIs may be more suitable when the type is known and the task is performance-sensitive.
- `Array.newInstance` allocates an actual array; large sizes or many dimensions can cause `OutOfMemoryError`. Always check element count/size limits from configuration or request data.
- `int[]` stores primitive values; `Integer[]` stores references to wrapper objects. The two types are **not equivalent** in API, nullability, allocation cost, or access cost.
- For multidimensional arrays, creating with all dimensions allocates the corresponding sub-array layers. If you want a jagged array or lazy allocation, create only the outer dimension and allocate sub-arrays when needed.
- Do not optimize merely by assuming “reflection is always slow”. Use a profiler or benchmark appropriate to the workload; parsing/config, data conversion, and allocation can often account for most of the total cost.
- Do not replace application invariants, validation, or resource limits with `Array.set`: the JVM only enforces type and bounds rules at the array level.

## 10. Common Mistakes and Misconceptions

1. **Casting every array to `Object[]`.** This works for `String[]`, but not for `int[]`/`double[]`; use `Array.getLength/get/set` when the component type is unknown.
2. **Assuming `Array.newInstance(Object.class, n)` suffices for all types.** It only creates `Object[]`; it does not preserve `Customer[]` or `int[]` that another API might require.
3. **Confusing `int[]` with `Integer[]`.** One stores primitives, the other stores wrapper references; `getInt/setInt` does not automatically work with `Integer[]`.
4. **Relying on implicit narrowing.** `Array.set(new int[1], 0, Long.valueOf(1))` is still invalid, even though the number is within the `int` range.
5. **Accessing a multidimensional array as a flat block of data.** `Array.getLength(matrix)` only returns the outer dimension; retrieve the row and operate further.
6. **Forgetting that the outer array can contain `null` rows.** `Array.newInstance(String[].class, 2)` creates `String[][]` without allocating the two `String[]` rows.
7. **Assuming reflection can bypass `Field` access control or circumvent type rules.** `Array` only operates on valid array objects, while metadata/member access obeys its own rules.
8. **Using an array when a flexible size is needed.** Arrays are fixed; use `List` if the number of elements changes frequently and the API does not mandate an array.

## 11. Self-Check

**Exercise 1.** Given `Class<?> c = int.class` and `length = 4`. Create the array, write the values `1, 2, 3, 4`, and compute the sum **without casting to `int[]`**. Hint: `Array.newInstance`, `Array.setInt`, `Array.getInt`. The correct sum is `10`.

**Exercise 2.** Compare:
- `Array.newInstance(double.class, 2, 3)`
- `Array.newInstance(double[].class, 2)`

Both have runtime type `double[][]`, but the first pre-creates two `double[3]` rows; the second has two rows that are initially `null`.

**Exercise 3.** Why does `Array.get(new long[] {4L}, 0)` have a static type of `Object`, while `Array.getLong(new long[] {4L}, 0)` returns `long`? Answer: The first API is a generic accessor so it boxes to `Long`; the second API is a primitive accessor.

**Exercise 4.** Write a `copyOf(Object source, int newLength)` that automatically creates an array with the right component type, copies `min(oldLength, newLength)` elements, and handles non-array input. Compare it with `java.util.Arrays.copyOf` for known types. When the API allows, `System.arraycopy` is an efficient way to copy array regions; compatible array types must be verified.

## Official Documentation

- [Java SE 17 API — java.lang.reflect.Array](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Array.html)
- [Oracle Java Tutorials — Arrays and Reflection](https://docs.oracle.com/javase/tutorial/reflect/special/array.html)

## Conclusion

`java.lang.reflect.Array` is the standard tool when **the component type is known at runtime, yet you need to create and manipulate the exact JVM array type**. Obtain `Class<?>` from a trusted source, create the array with `newInstance`, read/write with `get/set` or the primitive variants, check indices/conversions, and distinguish pre-allocated multidimensional arrays from jagged arrays. Once dynamic integration is complete, prefer returning a clearly typed contract to the business layer.
