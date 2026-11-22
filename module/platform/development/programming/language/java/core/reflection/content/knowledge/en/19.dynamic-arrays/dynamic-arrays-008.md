# Diagnosing Dynamic Array Errors: Indices, Negative Sizes, and Non-Array Inputs

## 1. Each Error Pinpoints a Single Kind of Violation

`java.lang.reflect.Array` operates on real arrays at runtime, even when the caller only has an `Object` variable. The same system might receive an array type from configuration, create the array, and then read/write elements. Errors carry different meanings depending on **the failing step**:

| Step | Invalid Input | Native API Exception |
| --- | --- | --- |
| `Array.newInstance` allocation | Negative size in a dimension | `NegativeArraySizeException` |
| Array creation | `componentType == null` | `NullPointerException` |
| Array creation | `void.class`, no dimensions, or total rank exceeds 255 | `IllegalArgumentException` |
| `Array.getLength`/`get`/`set` | Array reference is `null` | `NullPointerException` |
| `Array.getLength`/`get`/`set` | Non-`null` object that is not an array | `IllegalArgumentException` |
| `Array.get`/`set` | Negative index or `index >= length` | `ArrayIndexOutOfBoundsException` |
| `Array.set` | Value incompatible with component type | `IllegalArgumentException` |

From this table, three core cases stand out:

- **`ArrayIndexOutOfBoundsException`:** the array object already exists, but the index is out of bounds.
- **`NegativeArraySizeException`:** an allocation parameter for one or more dimensions is a negative number.
- **`IllegalArgumentException` due to non-array:** the API received an object, yet that object is not an array instance.

`null` is a different case: `Array.getLength(null)` causes `NullPointerException`; `new int[0]` is still a completely valid array. Rely on **the API called and the data at that step**, because a single exception name can represent multiple distinct causes.

## 2. Checking Length Before Creating

`Array.newInstance(Class<?> componentType, int length)` creates an array of length `length`; the `int... dimensions` overload creates multiple dimensions in outer-to-inner order.

~~~java
Array.newInstance(int.class, 0);         // int[0], valid.
Array.newInstance(int.class, -1);        // NegativeArraySizeException.
Array.newInstance(String.class, 2, -1);  // NegativeArraySizeException.
Array.newInstance(void.class, 1);        // IllegalArgumentException.
Array.newInstance(int.class, new int[0]); // IllegalArgumentException.
~~~

These are illustrative calls with `java.lang.reflect.Array` imported; calls that throw errors should not be run consecutively outside `try/catch`.

A **dimension equal to 0** is still valid, unlike **passing no dimensions**. `Array.newInstance(String.class, 2, 0)` allocates two empty subarrays, whereas `Array.newInstance(String[].class, 2)` only allocates the outer array and leaves the two subarrays `null`.

If the component type is already an array class, the resulting total number of dimensions equals the existing rank plus the added dimensions. Java limits array type rank to 255, so `Array.newInstance(int[][].class, new int[254])` requests 256 dimensions and is rejected. To study array shapes in detail, see the multidimensional array creation lesson in the same chapter; when diagnosing errors, first identify **the target rank** and **each size**.

### Size Data from External Sources

Checking `length >= 0` is necessary but not sufficient. A very large positive value can cause `OutOfMemoryError` or hit JVM allocation limits. If a length is computed via addition/multiplication, `int` overflow can turn positive inputs into negative or incorrect numbers. Set business limits and use `Math.addExact`/`multiplyExact` when overflow detection is needed.

Helper example with a policy maximum of 10,000 outer-layer elements:

~~~java
static Object newBoundedArray(Class<?> type, int length) {
    if (type == null || type == void.class) {
        throw new IllegalArgumentException("Invalid component type");
    }
    if (length < 0 || length > 10_000) {
        throw new IllegalArgumentException("Unsupported length: " + length);
    }
    return java.lang.reflect.Array.newInstance(type, length);
}
~~~

The `IllegalArgumentException` above is **chosen by the helper** to report configuration errors early, rather than `NegativeArraySizeException` from `Array.newInstance`. The 10,000 limit is also an application policy example, **not a Java limit**.

## 3. Checking for a Real Array Before Measuring Length

`Array.getLength(Object)` accepts **an array object**, such as `new int[]{1}`, `new String[0]`, or `new int[2][3]`. It does not accept `String`, `List`, or the `Class` object itself describing an array type.

~~~java
Object actual = new int[] {1, 2};
Object metadata = int[].class;

System.out.println(actual.getClass().isArray());   // true
System.out.println(metadata.getClass().isArray()); // false
System.out.println(Array.getLength(actual));       // 2
// Array.getLength(metadata); // IllegalArgumentException.
~~~

The snippet above uses imported `Array`. `int[].class.isArray()` is true because that token **describes an array type**, yet `int[].class` is still a `Class` object rather than an `int[]` instance.

Input-guarding pattern:

~~~java
static int requireLength(Object candidate) {
    if (candidate == null) {
        throw new IllegalArgumentException("Array is required");
    }
    if (!candidate.getClass().isArray()) {
        throw new IllegalArgumentException(
                "Not an array: " + candidate.getClass().getTypeName());
    }
    return java.lang.reflect.Array.getLength(candidate);
}
~~~

The helper intentionally returns `IllegalArgumentException` for both `null` and non-array. This is **the application's contract**; the raw API still distinguishes `NullPointerException` for `null` and `IllegalArgumentException` for a non-array object.

Do not adopt `0` as a convention meaning "not an array". `new int[0]` is a real array, has length 0, and contains no valid indices.

## 4. Checking the Index on the Exact Array Being Accessed

For a concrete array of length `n`, the condition to read/write is:

\[0 \leq index < n\]

If `n == 0`, then **there is no valid index**. `Array.get(new int[0], 0)` throws `ArrayIndexOutOfBoundsException` even though creating the empty array succeeded.

You can validate:

~~~java
static Object checkedGet(Object array, int index) {
    if (array == null || !array.getClass().isArray()) {
        throw new IllegalArgumentException("Expected an array");
    }
    int length = java.lang.reflect.Array.getLength(array);
    if (index < 0 || index >= length) {
        throw new IndexOutOfBoundsException(
                "index=" + index + ", length=" + length);
    }
    return java.lang.reflect.Array.get(array, index);
}
~~~

The helper uses the application's `IndexOutOfBoundsException` to explain the error, whereas `Array.get` directly uses the `ArrayIndexOutOfBoundsException` subclass. `Objects.checkIndex(index, length)` also helps check bounds, though it does not guarantee the exact subclass thrown by Reflection. When diagnosing, you must know **which API emitted the exception**.

### Multidimensional Arrays Have Separate Bounds at Each Layer

~~~java
int[][] rows = {{1, 2, 3}, {}, null, {4}};
~~~

`Array.getLength(rows)` equals 4; the four rows have length 3, 0, no subarray yet, and 1. To get `rows[3][0]` using Reflection:

1. Verify row index 3 against the outer array length.
2. `Object row = Array.get(rows, 3)` and then check `row != null`.
3. Measure `Array.getLength(row)` equals 1, verify column index 0.
4. `Array.get(row, 0)` returns an `Integer` containing 4 because the subarray has primitive `int` component.

For row 1, column index 0 is out of bounds; for row 2, calling `Array.getLength` on `null` causes `NullPointerException`. Two distinct errors even though both appear when processing one matrix.

## 5. Java 17+ Program Verifying Exception Identities

Create the file `ReflectArrayFailureAtlas.java`:

~~~java
import java.lang.reflect.Array;

public class ReflectArrayFailureAtlas {
    static void show(String name, Runnable action) {
        try {
            action.run();
            System.out.println(name + ": OK");
        } catch (RuntimeException ex) {
            System.out.println(name + ": "
                    + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        Object array = Array.newInstance(String.class, 2);
        Array.set(array, 0, "A");
        System.out.println("length=" + Array.getLength(array));

        show("negative", () -> Array.newInstance(int.class, -1));
        show("negative dimension",
                () -> Array.newInstance(int.class, 2, -1));
        show("void", () -> Array.newInstance(void.class, 1));
        show("no dimension",
                () -> Array.newInstance(int.class, new int[0]));

        show("null length", () -> Array.getLength(null));
        show("non-array", () -> Array.getLength("hello"));
        show("class token", () -> Array.getLength(int[].class));

        show("index -1", () -> Array.get(array, -1));
        show("index at length", () -> Array.get(array, 2));
        show("wrong element", () -> Array.set(array, 0, 123));

        Object partial = Array.newInstance(int[].class, 1);
        show("missing subarray",
                () -> Array.getLength(Array.get(partial, 0)));
        show("empty array index", () -> Array.get(new int[0], 0));
    }
}
~~~

~~~bash
javac --release 17 ReflectArrayFailureAtlas.java
java ReflectArrayFailureAtlas
~~~

Output:

~~~text
length=2
negative: NegativeArraySizeException
negative dimension: NegativeArraySizeException
void: IllegalArgumentException
no dimension: IllegalArgumentException
null length: NullPointerException
non-array: IllegalArgumentException
class token: IllegalArgumentException
index -1: ArrayIndexOutOfBoundsException
index at length: ArrayIndexOutOfBoundsException
wrong element: IllegalArgumentException
missing subarray: NullPointerException
empty array index: ArrayIndexOutOfBoundsException
~~~

`show` catches `RuntimeException` solely to **print the error type during practice**. In a real application, such a broad catch block easily hides programming bugs; validate upfront, report the invalid data accurately, and catch specific errors at boundaries that can handle them.

## 6. Do Not Confuse Element Errors with Non-Array Input Errors

`IllegalArgumentException` does not only mean "not an array". For instance:

~~~java
Array.set(new String[1], 0, 42);     // Wrong component type.
Array.set(new int[1], 0, 3L);        // long -> int is narrowing.
Array.set(new int[1], 0, null);      // Primitives do not accept null.
~~~

The operations above all have a **valid array and valid index**, yet the value cannot be converted under `Array.set`'s contract. For primitive arrays, Reflection can unbox wrappers and perform valid widening; it does not automatically narrow. For reference arrays, the value must be `null` or compatible with the array's **runtime** component type.

One difference worth remembering:

~~~java
Object[] refs = new String[1];
refs[0] = Integer.valueOf(5); // ArrayStoreException.

Object array = new String[1];
Array.set(array, 0, Integer.valueOf(5)); // IllegalArgumentException.
~~~

The two write APIs differ and have different error-reporting contracts. To find the cause, record which operation occurred, the runtime type of the array, the component type, the index, and the type of value (if non-`null`).

## 7. Diagnostic Workflow for Mappers or Plugins

When handling data whose type is unknown in advance, proceed in order:

1. **Array creation:** is component type non-`null`, not `void.class`, is the rank valid, and are all sizes non-negative and within the memory budget?
2. **Handling an existing array:** is the value non-`null`, and does its runtime class have `isArray() == true`?
3. **Reading/writing:** does index satisfy `0 <= index < Array.getLength(array)` at the right layer?
4. **Writing elements:** what is `array.getClass().getComponentType()`, is value `null`, and is a custom conversion (string parsing, controlled numeric narrowing) needed before calling `Array.set`?
5. **Multidimensional arrays:** has the current subarray been allocated yet? It can be `null` even when the outer array's runtime class already has multiple dimensions.
6. **Error messages:** state the input field name, operation kind, index, length, and component type; keep the information needed to fix configuration while avoiding logging entire sensitive element payloads.

Do not treat every `RuntimeException` arising in the pipeline as "wrong array type". `NegativeArraySizeException` is a creation error, `ArrayIndexOutOfBoundsException` is a position error, and `IllegalArgumentException` can be a non-array input **or** an element conversion error.

### Quick Decision Table

| Symptom | Check Next |
| --- | --- |
| Cannot create array | Negative dimension, dimension count, `void.class`, `null` component, memory |
| `getLength` fails | Null or non-array object? |
| `get`/`set` fails | Actual index, length of the right layer, array kind |
| `set` type mismatch | Primitive/reference component, value type, widening/narrowing |
| Fails only when descending into inner layer | `null` subarray, jagged length, confused dimension count |
| Confusing `ArrayStoreException` with `IllegalArgumentException` | Direct assignment syntax or `Array.set`? |

## 8. Self-Check

1. Does `Array.newInstance(int.class, 0)` fail? What about `Array.get(new int[0], 0)`?
2. What does `Array.newInstance(String.class, 2, -3)` throw? How does a helper that explicitly throws `IllegalArgumentException` beforehand differ?
3. Why is `Array.getLength(int[].class)` invalid even though `int[].class.isArray()` is true?
4. Given `int[][] rows = {{1}, null}`, how does the error when reading `rows[0][1]` differ from the error when measuring the length of `rows[1]`?
5. Why does `Array.set(new String[1], 0, Integer.valueOf(1))` not throw the same exception as assigning via `Object[] alias = new String[1]`?
6. If a source sends a very large but non-negative size, is allocation guaranteed to succeed?

**Key takeaway:** distinguish **allocation** errors, **array identification** errors, **index** errors, and **value type** errors according to the API step called. When you have a valid array object, check bounds at the right layer; when you only have configuration input, validate component type/sizes before allocating. Do not equate an empty array with `null` and do not treat `0` as a code meaning "not an array".

Official documentation: [Java SE 17 — `java.lang.reflect.Array`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Array.html), [Java SE 17 — `Class.isArray`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html), [Java SE 17 — `Objects.checkIndex`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html).