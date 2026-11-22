# Array.newInstance with Component Type Determined at Runtime

## 1. From a Class Object to a Real Array

When writing `new String[3]`, we explicitly specify the `String` type in the source code. However, a data converter, testing tool, or library handling multiple object types might only receive a `Class<?>` while the program is running. In that case, `java.lang.reflect.Array.newInstance` creates an array based on that `Class` object.

Here, the **component type** is the type of each direct slot in the array. For `String[]`, it is `String`; for `String[][]`, it is `String[]`. This lesson focuses on choosing the right type and allocating the right array shape.

"Dynamic array" in this context means **determining the type or size at runtime**. The created array still has a fixed length. To add elements beyond the old length, you must create another array and copy the data, or use a structure like `ArrayList`.

An illustrative example inside a method, with `java.lang.reflect.Array` imported:

~~~java
Class<?> componentType = String.class;
Object result = Array.newInstance(componentType, 3);
~~~

The result is an object whose runtime type is `String[]`, even though the `result` variable is declared as `Object`. This is **array allocation**, not merely querying information about a type.

## 2. Contract of the Two Overloads

Two primary usage forms:

~~~java
Array.newInstance(Class<?> componentType, int length)
Array.newInstance(Class<?> componentType, int... dimensions)
~~~

The snippet above represents how the API is called, not a complete compilable method declaration.

- `componentType` describes the type used to create the array.
- `length` is the length of a single new dimension.
- `dimensions` specifies the lengths of the new dimensions.
- The return value has declared type `Object`, while the actual array type is determined by the input.

Quick-reference table:

| Call | Actual Type | Contents Immediately After Creation |
| --- | --- | --- |
| `Array.newInstance(String.class, 3)` | `String[]` | Three slots containing `null` |
| `Array.newInstance(int.class, 3)` | `int[]` | Three slots containing `0` |
| `Array.newInstance(Integer.class, 3)` | `Integer[]` | Three slots containing `null` |
| `Array.newInstance(Runnable.class, 2)` | `Runnable[]` | Two slots containing `null` |
| `Array.newInstance(String.class, 2, 3)` | `String[][]` | Two subarrays, each with three `null` slots |
| `Array.newInstance(String[].class, 2)` | `String[][]` | Two outer slots containing `null`; subarrays not yet created |

A call with a single integer, such as `newInstance(String.class, 3)`, uses the `int length` overload. To pass the sizes as a single value, you can use `newInstance(String.class, new int[] {2, 3})`.

Do not write `new componentType[3]`: a variable of type `Class<?>` cannot replace a type name in the `new T[n]` syntax.

## 3. Runnable Example: One Processing Flow, Two Array Types

Save as `DynamicArrayCreationDemo.java`. The program uses a command-line argument to select the component type at runtime:

~~~java
import java.lang.reflect.Array;

public class DynamicArrayCreationDemo {
    private static Class<?> selectComponentType(String choice) {
        return switch (choice) {
            case "text" -> String.class;
            case "count" -> int.class;
            default -> throw new IllegalArgumentException(
                    "Expected text or count");
        };
    }

    public static void main(String[] args) {
        String choice = args.length == 0 ? "text" : args[0];
        Class<?> componentType = selectComponentType(choice);
        Object array = Array.newInstance(componentType, 3);

        System.out.println("type=" + array.getClass().getTypeName());
        System.out.println("component="
                + array.getClass().getComponentType().getTypeName());
        System.out.println("length=" + Array.getLength(array));
        System.out.println("default[0]=" + Array.get(array, 0));

        if (componentType == int.class) {
            Array.setInt(array, 0, 7);
        } else {
            Array.set(array, 0, "Lan");
        }

        System.out.println("value[0]=" + Array.get(array, 0));
        System.out.println("is Object[]=" + (array instanceof Object[]));
    }
}
~~~

Compile with JDK 17 or later:

~~~bash
javac --release 17 DynamicArrayCreationDemo.java
java DynamicArrayCreationDemo text
~~~

Output:

~~~text
type=java.lang.String[]
component=java.lang.String
length=3
default[0]=null
value[0]=Lan
is Object[]=true
~~~

Run again with the remaining option:

~~~bash
java DynamicArrayCreationDemo count
~~~

Output:

~~~text
type=int[]
component=int
length=3
default[0]=0
value[0]=7
is Object[]=false
~~~

Read the example in three steps:

1. `selectComponentType` determines the `Class` object from the input data.
2. `Array.newInstance` uses that type to create an array with three slots, with the corresponding default values.
3. `Array.getLength`, `Array.get`, and `Array.setInt`/`Array.set` operate on the array through the `Object` variable.

Writing and reading an element is only meant to prove that the array was created with the right type. Creating the array does not automatically populate business values like `"Lan"` or `7`.

The way the type is chosen in the example is a small, easy-to-control list of choices. In a real application, `Class<?>` can also come from a method parameter, metadata of a field, or the actual type of an existing array. You must clearly determine which source is the right contract for the data being processed.

## 4. Why Is the Result Object, and When Can You Cast?

Primitive arrays like `int[]` are also objects, so they can be assigned to an `Object` variable. However, `int[]` is **not** an `Object[]`. Its elements are `int` values, not object references.

The following snippets are illustrations inside a method with `java.lang.reflect.Array` imported:

~~~java
Object raw = Array.newInstance(int.class, 2);
int[] numbers = (int[]) raw;       // Valid: actual type is int[].
// Object[] wrong = (Object[]) raw; // If run: ClassCastException.
~~~

Conversely:

~~~java
Object raw = Array.newInstance(String.class, 2);
String[] names = (String[]) raw;  // Valid: actual type is String[].
Object[] references = names;     // String[] is a kind of Object[].
~~~

A cast does not convert one array into another. It only checks whether the existing object matches the target type. Therefore:

- If the caller knows for sure the return contract is `String[]`, it can cast to `String[]`.
- If the caller must support `String[]`, `int[]`, `boolean[]`, and other types, it should keep the `Object` variable and use the `Array` API.
- To turn an `int[]` into an `Integer[]`, you must create the target array and transfer each value; casting does not box the entire array.

`Array.get` returns `Object`; when reading from a primitive array, the value is boxed. That explains why the print statement in the example can handle both kinds of arrays, yet **does not turn `int[]` into a reference array**.

The types `int.class` and `Integer.class` are two different inputs. Choosing the wrong one between them creates the wrong kind of array right from the allocation step.

## 5. Multidimensional Arrays: Distinguishing the Type from the Already-Created Subarrays

Java represents multidimensional arrays as arrays containing references to subarrays. Therefore, two separate questions must be answered:

1. What type does the outermost object have?
2. Which subarrays have been allocated, and with what lengths?

If the input type already has `k` dimensions and the call adds `d` sizes, the resulting type has `k + d` dimensions. The dimensions already present in the input type are not automatically allocated into subarrays.

Examples:

| Input | Result Type | Allocated Part |
| --- | --- | --- |
| `String.class, 2, 3` | `String[][]` | Outer array of length 2 and two `String[]` arrays of length 3 |
| `String[].class, 2` | `String[][]` | Outer array of length 2; each slot is currently `null` |
| `String[].class, 2, 3` | `String[][][]` | Outer array of length 2, next-level arrays of length 3; the slots holding `String[]` at that level remain `null` |

Do not pass `String[].class` when the intention is to create a `String[]`. That input is already an array type; adding one dimension creates `String[][]`.

Save the following program as `ArrayDimensionsDemo.java`:

~~~java
import java.lang.reflect.Array;
import java.util.Arrays;

public class ArrayDimensionsDemo {
    public static void main(String[] args) {
        Object rectangular = Array.newInstance(String.class, 2, 3);
        Object outerOnly = Array.newInstance(String[].class, 2);

        System.out.println("rect.type="
                + rectangular.getClass().getTypeName());
        System.out.println("rect.component="
                + rectangular.getClass().getComponentType().getTypeName());
        System.out.println("rect.rows=" + Array.getLength(rectangular));
        System.out.println("rect.row0.length="
                + Array.getLength(Array.get(rectangular, 0)));
        System.out.println("rect.values="
                + Arrays.deepToString((Object[]) rectangular));

        System.out.println("outer.type="
                + outerOnly.getClass().getTypeName());
        System.out.println("outer.row0=" + Array.get(outerOnly, 0));

        Array.set(outerOnly, 0, new String[] {"A"});
        System.out.println("outer.values="
                + Arrays.deepToString((Object[]) outerOnly));
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 ArrayDimensionsDemo.java
java ArrayDimensionsDemo
~~~

Output:

~~~text
rect.type=java.lang.String[][]
rect.component=java.lang.String[]
rect.rows=2
rect.row0.length=3
rect.values=[[null, null, null], [null, null, null]]
outer.type=java.lang.String[][]
outer.row0=null
outer.values=[[A], null]
~~~

Both arrays have the same actual type `String[][]`, but their data shapes differ. The first array is fully created across two dimensions. The second array only has the outer layer; the code must assign each subarray when needed.

`getComponentType()` peels off exactly **one layer**. For `String[][]`, it returns `String[].class`, not `String.class` directly. To find the element type at the deepest level, you need to keep peeling while `Class.isArray()` still returns `true`.

A length of 0 is still valid: `Array.newInstance(int.class, 2, 0)` creates an `int[][]` with two empty subarrays. Length and number of dimensions are two different pieces of information.

## 6. Getting the Component Type from an Existing Array

A practical need is creating a new array of the same type as a source array, but with a different length. The snippet below is a utility method; place it in a class with `java.lang.reflect.Array` and `java.util.Objects` imported:

~~~java
static Object emptyLike(Object sourceArray, int newLength) {
    Objects.requireNonNull(sourceArray, "sourceArray");
    Class<?> arrayType = sourceArray.getClass();
    if (!arrayType.isArray()) {
        throw new IllegalArgumentException("Expected an array");
    }
    return Array.newInstance(arrayType.getComponentType(), newLength);
}
~~~

Example calls in the same class:

~~~java
Object first = emptyLike(new long[] {10L, 20L}, 4);
// first is long[4], all initial values equal 0L.

Object second = emptyLike(new String[][] {{"A"}}, 3);
// second is String[3][], all three subarray references are null.
~~~

This function **only creates an empty array of the same type**, without copying elements. For multidimensional arrays, it allocates the outer layer and preserves the type of the inner slots; it does not clone the subarrays.

You must check `isArray()` before getting the component type. For a non-array class, `getComponentType()` returns `null`; passing that value to `Array.newInstance` cannot create the desired array.

You also need to distinguish between **declared type** and **actual type**. If a variable declared as `Number[]` is pointing to an `Integer[]`, obtaining the type from `sourceArray.getClass()` preserves `Integer[]`. If the business requirement is to create a `Number[]`, you must pass `Number.class` explicitly instead of inferring it from the source object.

## 7. Creating an Array Does Not Create Each Element

For reference types, the allocation step creates slots containing `null`. For example, `Array.newInstance(Runnable.class, 2)` is valid even though `Runnable` is an interface. No object implementing `Runnable` is produced by that call.

Similarly, you can create an array of an abstract class or a class without a no-argument constructor. There is no need to invoke the component class's constructor to create a reference array. Creating or finding individual objects to fill the slots is a separate step.

For primitive types, slots receive default values: numeric types receive the corresponding 0, `boolean` receives `false`, and `char` receives the character `'\u0000'`. This character is not the digit `'0'` and is usually invisible when printed directly.

Therefore, when designing a data converter, clearly separate:

1. Choosing the right target array type.
2. Allocating the right length/shape.
3. Converting and assigning each compatible value.

Success in step 2 does not prove that the input data can be converted in step 3.

## 8. Input Limits and Common Errors

| Situation | Expected Result |
| --- | --- |
| `Array.newInstance(null, 3)` | `NullPointerException`: missing component type |
| `Array.newInstance(String.class, -1)` | `NegativeArraySizeException` |
| `Array.newInstance(String.class, 0)` | Valid: creates an empty array |
| `Array.newInstance(void.class, 1)` | `IllegalArgumentException`: there is no `void[]` array |
| `Array.newInstance(String.class, new int[0])` | `IllegalArgumentException`: no dimensions provided |
| Total requested dimensions exceed 255 | `IllegalArgumentException` |
| Valid length but insufficient memory to allocate | May encounter `OutOfMemoryError` |

`new int[0]` in the table is **an empty list of sizes**, not a single dimension of length 0. An empty dimension must be expressed using `new int[] {0}` or the overload taking `length = 0`.

Checking for non-negative length is not enough for external data. A very large size can still cause the application to consume too much memory; you should enforce an application-specific limit before allocating. For multiple dimensions, you must inspect the entire shape, not just the outer array length.

Do not catch every error and silently return `new Object[0]` as a "fallback". That loses the target type and hides invalid input; downstream calling code will have a hard time identifying the cause.

## 9. Connection to Generics and API Choice

Java does not allow writing `new T[n]` with an ordinary generic type parameter, because the type `T` does not provide enough concrete information to allocate the array in that code. Passing an extra `Class` object is one way to supply the runtime type to `Array.newInstance`.

However, Reflection does not recover all erased generic information:

- There is no `List<String>.class` syntax.
- `Array.newInstance(List.class, n)` creates an array whose actual type is `List[]`; the JVM does not thereby verify that every list inside contains only `String`.
- Do not promise that a function returning `T[]` supports every `Class` input, including primitive types, merely by an unchecked cast.

In this lesson, the `Object` return type preserves the ability to support both primitive arrays and reference arrays. When designing your own generic function, you must define the reference-type contract and control the cast site; do not copy a `(T[])` cast while omitting validity conditions.

Use `new String[n]` when the type is already known in source code: this approach is direct and clearly checked by the compiler. Use `Array.newInstance` when choosing the type is runtime data. If the primary need is continuously growing/shrinking the number of elements, consider a collection instead of using Reflection for every operation.

## 10. Self-Check

1. Does `Array.newInstance(Integer.class, 2)` create `Integer[]` or `int[]`? What are the default values?
2. Why can an `int[]` be assigned to `Object` yet cannot be cast to `Object[]`?
3. Does `Array.newInstance(String[].class, 4)` create four strings or four subarrays?
4. To fully create a `String[4][2]` table, what type and sizes should be passed?
5. Does the `emptyLike` function copy values from the source array?

Answers:

1. `Integer[]`, two `null` slots; `int.class` is what creates the primitive array `int[]`.
2. The array itself is an object, but the `int` slots are not object references to form an `Object[]`.
3. It creates `String[4][]`; all four outer slots are `null`, and no subarrays or strings have been created yet.
4. `Array.newInstance(String.class, 4, 2)`.
5. No. The function only preserves the array's actual type and allocates a new array with default values.

Key takeaway: the `Class` object is the input information for selecting the type; `Array.newInstance` uses that information to allocate a real array. The array type, number of dimensions, lengths, and slot values are aspects that must be checked separately.

## Reference Materials

- [Java 17 — Array.newInstance and Array Manipulation API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Array.html).
- [Java 17 — Class.getComponentType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getComponentType()).
- [JLS 17 — Chapter 10: Array Types and Multidimensional Arrays](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html).
- [JLS 17 — Array Creation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.10.1).
- [JLS 17 — Reifiable Types (Types with Complete Runtime Information)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7).
