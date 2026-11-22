# Do Not Cast `int[]` to `Object[]` in Java Reflection

## Learning Objectives

After this lesson, you can explain why a primitive integer array `int[]` is a Java object yet is not an `Object[]`; recognize compile-time errors and `ClassCastException` when casting; operate on arrays of unknown element types via `java.lang.reflect.Array`; and deliberately convert data to `Integer[]` when an API truly requires an object array.

## 1. Understanding Array Types Correctly

In Java, **every array is an object**: whether it holds primitive or reference elements, every array has a runtime type, a `length` property, inherits `Object` behaviors, and implements `Cloneable`, `Serializable`. However, "being an `Object`" does not mean "being an `Object[]`".

- `int[]` holds primitive `int` values. Its component type is `int`; the elements are not `Integer` objects.
- `Integer[]`, `String[]`, and `Object[]` are **reference arrays**: each slot holds a reference to an object (or `null`).
- `Object[]` only represents arrays whose **component type is an appropriate reference type**. It does not generically represent all kinds of arrays.
- `Object` can refer to `int[]`, `long[]`, `String[]`, `Integer[]`, and `int[][]`.

| Runtime Value | Assignable to `Object` | Assignable to `Object[]` | Element Type |
| --- | --- | --- | --- |
| `new int[3]` | Yes | No | Primitive `int` |
| `new Integer[3]` | Yes | Yes | `Integer` |
| `new String[3]` | Yes | Yes | `String` |
| `new Object[3]` | Yes | Yes | `Object` |
| `new int[2][3]` | Yes | Yes, at the **outer array** | `int[]` (reference type) |

The last point is easy to confuse: `int[][]` is an array of `int[]`; the outer array holds **references** to subarrays. Therefore `int[][]` can be treated as `Object[]`, yet each `int[]` inside is still **not** an `Object[]`.

### Type Diagram

~~~text
Object
├── int[]              (primitive-element array)
├── long[]             (primitive-element array)
├── Object[]           (reference-element array)
│   ├── String[]
│   ├── Integer[]
│   └── int[][]       (outer array elements are int[])
└── ...
~~~

The diagram illustrates useful type-assignment relationships for this lesson; it is not an `extends` declaration you can write in Java source code.

## 2. Two Forms of Casting Errors to Distinguish

### 2.1. Compile-Time Error When the Type Is Known in Advance to Be `int[]`

~~~java
int[] numbers = {10, 20, 30};

Object anyArray = numbers;             // Valid: every array is an Object.
Object[] refs = numbers;               // COMPILE-TIME ERROR.
Object[] casted = (Object[]) numbers;   // STILL A COMPILE-TIME ERROR.
~~~

This is a **snippet intentionally containing errors** to recognize type rules; do not put the entire snippet into a program meant to compile. The compiler knows `numbers` has static type `int[]` and there is no valid conversion to `Object[]`. Adding an explicit cast cannot turn primitive `int` values into reference elements.

### 2.2. Compiles via `Object`, but Fails at Runtime

File `ArrayCastPitfall.java`:

~~~java
public class ArrayCastPitfall {
    public static void main(String[] args) {
        int[] numbers = {10, 20, 30};
        Object unknown = numbers;

        System.out.println(unknown instanceof Object);
        System.out.println(unknown instanceof Object[]);
        System.out.println(
                unknown.getClass().getComponentType().getTypeName()
        );

        try {
            Object[] wrong = (Object[]) unknown;
            System.out.println(wrong.length); // Never reached.
        } catch (ClassCastException ex) {
            System.out.println(ex.getClass().getSimpleName());
        }
    }
}
~~~

Run with JDK 17 or newer:

~~~bash
javac ArrayCastPitfall.java
java ArrayCastPitfall
~~~

Standard output:

~~~text
true
false
int
ClassCastException
~~~

The `unknown` variable has **declared type** `Object`, so the compiler allows attempting a downcast to `Object[]`. However, the actual object was created with `new int[]{...}`, having runtime type `int[]`; the JVM checks and rejects the cast with `ClassCastException`. A cast only checks/changes the view to a compatible type; **it does not convert or box each element**.

Checking `instanceof Object[]` before casting only avoids the exception. It does not make `int[]` become a reference array.

## 3. Why Does This Issue Appear When Using Reflection?

Reflection often handles an array object whose **element type is not known in advance at compile time**. For example, `Field.get(instance)` might return `int[]`, `String[]`, or another array type as `Object`. A utility function taking `Object array` and unconditionally casting it to `Object[]` breaks immediately upon encountering a primitive array.

Do not write:

~~~java
// Wrong if the field holds int[], long[], boolean[], or another primitive array.
Object value = field.get(instance);
Object[] elements = (Object[]) value;
~~~

This is an **isolated illustrative snippet**: `field` and `instance` must be declared in an actual Reflection context. The mistake lies in the cast, not in `Field.get`.

Java provides `java.lang.reflect.Array` to operate on **both primitive arrays and reference arrays** when you only have an `Object` variable:

| Need | Appropriate API |
| --- | --- |
| Determine whether an object is an array | `value != null && value.getClass().isArray()` |
| Get runtime component type | `value.getClass().getComponentType()` |
| Detect primitive component type | `componentType.isPrimitive()` |
| Get number of elements | `Array.getLength(value)` |
| Read element at index `i` | `Array.get(value, i)` |
| Write compatible element | `Array.set(value, i, element)` |
| Create array with component type determined at runtime | `Array.newInstance(componentType, length)` |

`Array.get` returns `Object`; when reading an element from `int[]`, the `int` value is **boxed into `Integer`**. Specialized methods such as `Array.getInt` and `Array.setInt` work with primitive values according to their type-compatibility rules, avoiding boxing where appropriate. `Array.getLength` and `Array.get` require an array argument; passing `null`, an ordinary object, or an invalid index throws the corresponding exception.

## 4. Complete Example: Creating and Traversing Dynamic Arrays with Reflection

"Dynamic array" here means **creating/inspecting an array when the component type is decided at runtime** via Reflection. A Java array after creation has a fixed `length`; it does not expand its size automatically like `ArrayList`.

File `ReflectiveArrayDemo.java`:

~~~java
import java.lang.reflect.Array;
import java.util.StringJoiner;

public class ReflectiveArrayDemo {
    public static void main(String[] args) {
        // Create int[3]; Array.newInstance returns Object.
        Object ints = Array.newInstance(int.class, 3);
        Array.setInt(ints, 0, 7);
        Array.setInt(ints, 1, 14);
        Array.setInt(ints, 2, 21);
        printArray(ints);

        // Create String[2] using runtime component type.
        Object words = Array.newInstance(String.class, 2);
        Array.set(words, 0, "Java");
        Array.set(words, 1, "Reflection");
        printArray(words);

        // Only compatible reference arrays cast to Object[].
        if (words instanceof Object[] refs) {
            System.out.println(refs[0]);
        }
    }

    private static void printArray(Object array) {
        if (array == null || !array.getClass().isArray()) {
            throw new IllegalArgumentException("Expected an array");
        }

        Class<?> componentType = array.getClass().getComponentType();
        int length = Array.getLength(array);
        StringJoiner joined = new StringJoiner(", ", "[", "]");

        for (int i = 0; i < length; i++) {
            joined.add(String.valueOf(Array.get(array, i)));
        }

        System.out.println(
                componentType.getTypeName() + "[" + length + "] = " + joined
        );
    }
}
~~~

Run:

~~~bash
javac ReflectiveArrayDemo.java
java ReflectiveArrayDemo
~~~

Standard output:

~~~text
int[3] = [7, 14, 21]
java.lang.String[2] = [Java, Reflection]
Java
~~~

Explanation: `Array.newInstance(int.class, 3)` actually creates an `int[]`; `Array.newInstance(String.class, 2)` creates a `String[]`. Both are held in `Object` variables, and `printArray` iterates via `Array.getLength`/`Array.get` so no cast to `Object[]` is needed. For the `String[]` array, the `instanceof Object[]` check is true and the cast is valid. When calling `Array.get` on `int[]`, the numbers are boxed for generic handling.

You can check before creating or processing an array:

~~~java
Class<?> arrayClass = ints.getClass();
System.out.println(arrayClass.isArray());                       // true
System.out.println(arrayClass.getComponentType().isPrimitive()); // true
~~~

This is an **additional snippet** using the `ints` variable declared in `main` in the example above.

## 5. When an API Strictly Requires `Object[]`: Real Conversion

If you need to interface with an API having signature `consume(Object[] values)`, merely casting is not enough. You must **create a new reference array** and box each element, or use a stream to create `Integer[]`.

File `BoxArrayDemo.java`:

~~~java
import java.util.Arrays;

public class BoxArrayDemo {
    public static void main(String[] args) {
        int[] numbers = {1, 2, 3};

        Integer[] boxed = Arrays.stream(numbers)
                .boxed()
                .toArray(Integer[]::new);
        Object[] refs = boxed; // Valid: Integer[] is a reference array.

        System.out.println(Arrays.toString(refs));

        refs[0] = 99;
        System.out.println(numbers[0]); // Original int[] array unchanged.
        System.out.println(boxed[0]);   // New Integer[] array changed.

        int[] backToPrimitives = Arrays.stream(boxed)
                .mapToInt(Integer::intValue)
                .toArray();
        System.out.println(Arrays.toString(backToPrimitives));
    }
}
~~~

Run:

~~~bash
javac BoxArrayDemo.java
java BoxArrayDemo
~~~

Standard output:

~~~text
[1, 2, 3]
1
99
[99, 2, 3]
~~~

`boxed()` turns each `int` into an `Integer` object; `toArray(Integer[]::new)` creates a **new array**. The assignment `Object[] refs = boxed` is valid, yet the new array does not share element slots with `numbers`. Boxing incurs extra memory and object-handling overhead; for pure arithmetic computation, you should usually continue using `int[]` or `IntStream`.

### Converting Any Array Kind to `Object[]` When Needed

The method below is a **helper placed inside a class**, not a standalone program. It creates a one-dimensional copy; primitive elements are boxed:

~~~java
import java.lang.reflect.Array;

static Object[] copyElements(Object source) {
    if (source == null || !source.getClass().isArray()) {
        throw new IllegalArgumentException("Expected an array");
    }

    int length = Array.getLength(source);
    Object[] result = new Object[length];
    for (int i = 0; i < length; i++) {
        result[i] = Array.get(source, i);
    }
    return result;
}
~~~

For example, `copyElements(new int[]{4, 5})` returns an `Object[]` containing two `Integer`s; `copyElements(new String[]{"a"})` returns an `Object[]` containing `String`. This is **data conversion and copying**, not casting `int[]`. For multidimensional arrays, the function only copies the **outer layer**, without deep-copying subarrays.

If the API supports `Collection<Integer>`, Java 17 can use `Arrays.stream(numbers).boxed().toList()`; the result is a list whose structure cannot be modified via `add`/`set`. If you need to dynamically grow or shrink the number of elements, consider `ArrayList<Integer>` instead of expecting a Java array to change its `length`.

## 6. Common Related Pitfalls

### 6.1. `Arrays.asList(int[])` Does Not Box Each Number

~~~java
int[] numbers = {1, 2, 3};

java.util.List<int[]> oneElement = java.util.Arrays.asList(numbers);
System.out.println(oneElement.size()); // 1

java.util.List<Integer> eachNumber =
        java.util.Arrays.stream(numbers).boxed().toList();
System.out.println(eachNumber.size()); // 3
~~~

`Arrays.asList` accepts elements of **reference type** via generic varargs. For `int[]`, it treats the entire array as **one element object**, rather than splitting it into three `Integer`s. The snippet above is an illustration placed inside a method, not a complete class.

### 6.2. Two-Dimensional Arrays Still Require Inspecting Each Layer

~~~java
int[][] matrix = {{1, 2}, {3, 4}};
Object[] outer = matrix; // Valid: elements at the outer layer are int[].

System.out.println(outer.length);                 // 2
System.out.println(outer[0] instanceof Object[]); // false
~~~

The outer layer is a reference array; each inner element has runtime type `int[]`. You cannot use `(Object[]) outer[0]` to read numbers in the subarray. To traverse safely, call `Array.getLength(outer[0])` and `Array.get(outer[0], i)`, or cast to the exact `int[]` if the type is known for sure.

### 6.3. Confusing Covariance with Boxing

In Java, `String[]` can be assigned to `Object[]` due to **array covariance**. However, if you assign a non-`String` object through this `Object[]` reference, the JVM throws `ArrayStoreException`. Covariance rules apply only to **reference element types**, and do not turn `int[]` into `Object[]`; this mechanism also **does not auto-box** an entire array.

### 6.4. Using Primitive Arrays Just to Print Data

To print `int[]`, use `Arrays.toString(numbers)` directly because the library already has an overload taking `int[]`. There is no need to create `Object[]`, no need for Reflection, and no need to box the whole array. `System.out.println(numbers)` by itself does not print the list of element values.

## 7. Choosing the Right Solution for the Context

| Situation | Recommended | Avoid |
| --- | --- | --- |
| Passing/holding any array without traversing yet | `Object` | Declaring every array as `Object[]` |
| Traversing an array whose component type is only known at runtime | `Array.getLength`, `Array.get` | Direct cast `(Object[]) array` |
| Knowing for sure the data is a primitive integer array | `int[]`, `Arrays.stream(int[])` | Unnecessary boxing |
| API requires a reference array | `Integer[]` or `Object[]` created from boxed data | Casting `int[]` |
| Needing a resizable list | `ArrayList<Integer>` | Expecting `int[]` to grow `length` automatically |
| Only needing to print `int[]` contents | `Arrays.toString(int[])` | Casting to call `Arrays.toString(Object[])` |

## 8. Self-Check

1. Why is `Object a = new int[4]` valid yet `Object[] a = new int[4]` invalid? Because every array is an object, whereas `Object[]` requires an array whose elements are of a reference type.
2. Why does `(Object[]) (Object) new int[4]` still fail? The intermediate static type `Object` allows attempting the cast, but the runtime type is still `int[]`; the JVM throws `ClassCastException`.
3. To read the third value from an `Object x` verified to be an array, what is needed? Use `Array.getLength(x)` to check the index and then `Array.get(x, 2)`; if it is actually an `int[]`, you can cast to `int[]` and read `[2]`.
4. Why does an `Integer[]` created from `int[]` not reflect changes to the original array? Because a different array was created and the values were boxed, with no shared data slots.

**Key takeaway:** `int[]` is an `Object`, **not** an `Object[]`. In Reflection, work directly with `java.lang.reflect.Array` when the element type is unknown; only create a new `Integer[]`/`Object[]` when the API requirement truly calls for a reference array type.