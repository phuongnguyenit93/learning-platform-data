# Distinguishing `int[]` from `Integer[]` and Assignability via `Object` in Java

## 1. Two Different Array Types

In Java, both `int[]` and `Integer[]` are **reference types pointing to array objects**, but their **element types** differ:

| Criterion | `int[]` | `Integer[]` |
| --- | --- | --- |
| Element type | Primitive `int` | Reference to a `java.lang.Integer` object |
| Default element value in a new array | `0` | `null` |
| Can an element be `null`? | No | Yes |
| Assigning an element from an `int` value | Direct | Autoboxing `int` to `Integer` |
| Reading an element into an `int` variable | Direct | Unboxing; can throw `NullPointerException` if the element is `null` |
| Assigning the whole array to `Object` | Allowed | Allowed |
| Assigning the whole array to `Object[]` | **Not allowed** | **Allowed** |
| Directly converting `int[]` to `Integer[]` via cast/autoboxing | No | Not applicable |

Every array object has a fixed `length` after initialization. `int[]` usually saves memory and avoids boxing when processing numeric data; `Integer[]` is appropriate when `null` elements are needed or an API requires `Integer` references. These two array types cannot be treated as interchangeable.

```java
int[] primitive = new int[3];     // [0, 0, 0]
Integer[] wrappers = new Integer[3]; // [null, null, null]

primitive[0] = 10;
wrappers[0] = 10; // autoboxing: Integer.valueOf(10)

int a = primitive[0]; // 10
int b = wrappers[0];  // unboxing: intValue(), result 10
```

The statements above are **illustrative snippets placed inside a method**, not a standalone program. If `wrappers[1]` is `null`, the assignment `int x = wrappers[1]` throws `NullPointerException`.

## 2. Why Both Are Assignable to `Object`, Yet Only One Is Assignable to `Object[]`

In Java, **an array itself is always an object**: every array type, including arrays of primitive elements, can be assigned to `Object`. They also implement `Cloneable` and `java.io.Serializable`.

```java
int[] a = {1, 2};
Integer[] b = {1, 2};

Object oa = a; // Valid: Object holds a reference to int[]
Object ob = b; // Valid: Object holds a reference to Integer[]

Object[] refs = b; // Valid: Integer is a reference type
// Object[] invalid = a; // COMPILE ERROR: int[] is not Object[]
```

`Object[]` is an array whose **elements are object references**. `Integer[]` is an array of `Integer` references (a subtype of `Object`), so it can be assigned to `Object[]`. Conversely, the elements of `int[]` are primitive values; `int` **is not a subtype** of `Object`, so `int[]` cannot be assigned to `Object[]`.

Assigning an array to `Object` **does not convert its elements**:

- `Object o = new int[]{1, 2};` only stores a reference to **the `int[]` array itself**.
- `(int[]) o` restores a reference of type `int[]` when the object actually has that type.
- `(Integer[]) o` does not convert each element's type; if `o` actually points to an `int[]`, this cast throws `ClassCastException`.
- Autoboxing `int` → `Integer` and unboxing `Integer` → `int` apply to **individual values**, not automatically converting an entire `int[]` ↔ `Integer[]`.

## 3. Multidimensional Arrays: `int[][]` Can Be Assigned to `Object[]`

This is a particularly easy point of confusion in multidimensional arrays. In Java, `int[][]` is an **outer array**, each element of which is **a reference to an `int[]`**. Because `int[]` is an object, the outer array's elements are of a reference type.

```java
int[][] matrix = {{10, 20}, {30}};
Object asObject = matrix;   // Valid: every array is an Object
Object[] rows = matrix;     // Valid: each element of matrix is an int[]
Object first = rows[0];     // Actual object is int[]
int[] firstRow = (int[]) first;
int item = firstRow[1];     // 20

// Object[][] invalid = matrix; // ERROR: int[][] is not Object[][]
```

Comparing three levels:

| Expression type | Nature of the array object | Assignable to `Object[]`? |
| --- | --- | --- |
| `int[]` | Elements are primitive `int` | No |
| `Integer[]` | Elements are `Integer` references | Yes |
| `int[][]` | Elements are `int[]` references | Yes |

Important depth distinction: `int[][]` is an `Object[]`, yet each row `matrix[i]` still has type `int[]` and **cannot** be assigned directly to `Object[]`. Similarly, `Integer[][]` can be assigned to `Object[][]` because each `Integer[]` row is an `Object[]`.

## 4. Covariance and Type Checking When Writing Through `Object[]`

Reference arrays in Java are **covariant** (*covariant*): since `Integer` is a subtype of `Number` and `Object`, `Integer[]` can be assigned to `Number[]` and `Object[]`.

```java
Integer[] numbers = {1, 2};
Number[] asNumbers = numbers;
Object[] asObjects = numbers;
asObjects[0] = Integer.valueOf(10); // Valid
// asObjects[1] = "hello";          // Compiles, but fails at runtime
```

Because `asObjects` and `numbers` both point to **an actual array of type `Integer[]`**, the JVM checks the object type when assigning elements. Even though the variable has type `Object[]`, assigning a `String` into an actual `Integer[]` array throws **`ArrayStoreException`**. The same applies to `Object[] rows = new int[2][]`: only `int[]` or `null` can be stored in each element, never an `Integer[]`.

Do not confuse `ArrayStoreException` when assigning the wrong type to a **reference array element** with `ClassCastException` when **casting the array object itself**.

## 5. Standalone Runnable Java 17+ Program

Create the file **`ArrayTypeDemo.java`**:

```java
import java.util.Arrays;

public class ArrayTypeDemo {
    public static void main(String[] args) {
        int[] raw = {1, 2, 3};
        Integer[] wrapped = {1, null, 3};

        Object rawAsObject = raw;
        Object wrappedAsObject = wrapped;
        System.out.println("raw la Object: " + (rawAsObject instanceof Object));
        System.out.println("raw la Object[]: " + (rawAsObject instanceof Object[]));
        System.out.println("wrapped la Object[]: " + (wrappedAsObject instanceof Object[]));

        Object[] elements = wrapped;
        elements[0] = 99;  // Autoboxing; mutates the original wrapped array
        System.out.println("wrapped: " + Arrays.toString(wrapped));

        try {
            elements[1] = "wrong"; // JVM rejects because the actual array is Integer[]
        } catch (ArrayStoreException ex) {
            System.out.println("Gan sai kieu: ArrayStoreException");
        }

        int[][] matrix = {{10, 20}, {30}};
        Object[] rows = matrix;
        System.out.println("matrix la Object[]: " + (matrix instanceof Object[]));
        System.out.println("rows[0] la int[]: " + (rows[0] instanceof int[]));
        rows[1] = new int[]{40, 50};
        System.out.println("Hang thu 2: " + Arrays.toString(matrix[1]));

        try {
            rows[0] = new Integer[]{7}; // Actual element must be int[]
        } catch (ArrayStoreException ex) {
            System.out.println("Gan sai hang: ArrayStoreException");
        }

        System.out.println("asList(int[]): " + Arrays.asList(raw).size());
        System.out.println("asList(Integer[]): " + Arrays.asList(wrapped).size());

        Integer[] boxedCopy = Arrays.stream(raw).boxed().toArray(Integer[]::new);
        int[] primitiveCopy = Arrays.stream(boxedCopy)
                                    .mapToInt(Integer::intValue).toArray();
        System.out.println("Boxed: " + Arrays.toString(boxedCopy));
        System.out.println("Unboxed: " + Arrays.toString(primitiveCopy));
    }
}
```

In the directory containing the file, using JDK 17 or higher:

```bash
javac -encoding UTF-8 ArrayTypeDemo.java
java ArrayTypeDemo
```

Exact stdout output (a successful compilation prints no messages):

```text
raw la Object: true
raw la Object[]: false
wrapped la Object[]: true
wrapped: [99, null, 3]
Gan sai kieu: ArrayStoreException
matrix la Object[]: true
rows[0] la int[]: true
Hang thu 2: [40, 50]
Gan sai hang: ArrayStoreException
asList(int[]): 1
asList(Integer[]): 3
Boxed: [1, 2, 3]
Unboxed: [1, 2, 3]
```

Explanation: `elements` is an `Object[]` reference to the same `Integer[]` object as `wrapped`, so modifying `elements[0]` affects `wrapped[0]`. `rows` points to the same outer array `matrix`, so replacing `rows[1]` changes the second row of `matrix`. Both invalid write operations are blocked by the JVM at runtime.

## 6. Converting Array Contents When Truly Needed

Because there is no automatic whole-array conversion, **create a new array** and convert each element.

**From `int[]` to `Integer[]`:**

```java
int[] source = {5, 6};
Integer[] boxed = java.util.Arrays.stream(source)
                                  .boxed()
                                  .toArray(Integer[]::new);
// boxed has contents [5, 6]
```

**From `Integer[]` to `int[]`:**

```java
Integer[] source = {5, 6};
int[] plain = java.util.Arrays.stream(source)
                              .mapToInt(Integer::intValue)
                              .toArray();
// plain has contents [5, 6]
```

These two snippets are illustrative code inside a method; the example in section 5 is a complete runnable program. If `Integer[]` contains `null`, unboxing at `Integer::intValue` throws `NullPointerException`. You must decide how to handle `null` according to the problem before converting (for example, reject the data, skip it, or substitute an intentional default value).

**A related API pitfall:** `Arrays.asList(raw)` where `raw` is `int[]` creates a list with **one element, which is the entire `int[]` array**; `Arrays.asList(wrapped)` where `wrapped` is `Integer[]` creates a list of `Integer` elements one by one. In the runnable example, the sizes are `1` and `3` respectively. To obtain a `List<Integer>` from `int[]`, use `Arrays.stream(raw).boxed().toList()` (Java 16+); this result is a list of boxed values.

## 7. Common Mistakes and Takeaways

- `int[]` is an array **containing primitives**, yet it **is still an object**, so it can be assigned to `Object`.
- `Object[]` requires **a reference element type**: it accepts `Integer[]`, `String[]`, `int[][]`; it **does not accept** `int[]`.
- Do not use `(Integer[]) someIntArray` to box an entire array; casting does not convert elements, so you must create a new array.
- Avoid unboxing an `Integer` that may be `null` without checking.
- Even through an `Object[]` variable, writes are still checked against the actual runtime array type; `ArrayStoreException` protects the array's type integrity.
- With multidimensional arrays, always inspect **the element type at the level under consideration**: `int[][]` contains `int[]` elements (references), whereas `int[]` contains `int` elements (primitives).

**Core rule:** the data type of **the array's elements** determines whether that array can be an `Object[]`; the fact that "an array is an object" is only enough to assign **the array itself** to `Object`.