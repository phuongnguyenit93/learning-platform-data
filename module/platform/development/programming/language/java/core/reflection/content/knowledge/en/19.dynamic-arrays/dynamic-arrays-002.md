# Creating Multidimensional Arrays and the Meaning of the Dimensions List in Java Reflection

When the element type, number of dimensions, or array lengths are only known at runtime, Java provides **java.lang.reflect.Array.newInstance(Class<?> componentType, int... dimensions)**. The method creates a real array at runtime, using **componentType** to determine the type and the integer array **dimensions** to determine the lengths of the dimensions to allocate.

Most importantly: **each element of dimensions is the length of one dimension, ordered from outermost to innermost**. This is not a list of indices, not an inclusive upper bound, and not the lengths of different rows. For example:

~~~java
int[][] matrix = (int[][]) java.lang.reflect.Array.newInstance(int.class, 2, 3);
~~~

The result is equivalent in type and initial shape to **new int[2][3]**: 2 rows, each with 3 int elements defaulting to 0.

This lesson dives deeper into the meaning of dimensions, especially when **componentType is already an array class**, partial allocation to build jagged arrays, the zero-size case, exceptions, and verification operations using Reflection.

## 1. The Two Overloads of Array.newInstance

The java.lang.reflect.Array class provides:

~~~java
static Object newInstance(Class<?> componentType, int length)
static Object newInstance(Class<?> componentType, int... dimensions)
~~~

- **newInstance(componentType, length):** creates an outer array of length `length`, holding elements of `componentType`. If `componentType` is an array type, the outer elements are references to subarrays, initially `null`.
- **newInstance(componentType, dimensions):** accepts one or more integers to create the corresponding outer dimensions. The `int...` form allows passing separate integers or an `int[]`.
- **Static result is Object:** because `componentType` can vary at runtime. The actual object is still a Java array carrying the right class type; you can cast it or operate on it further using `Array.get`, `Array.set`, `Array.getLength`.
- **Valid componentType:** a primitive type such as `int.class`, a reference type such as `String.class`, or an array class such as `String[].class`. Cannot be `void.class`.

Example where the first two expressions create arrays of the same shape as the last expression, though each call allocates a new object:

~~~java
Object first = Array.newInstance(String.class, 4, 5);
Object second = Array.newInstance(String.class, new int[] {4, 5});
String[][] third = new String[4][5];
~~~

These examples use **import java.lang.reflect.Array;**. `first`, `second`, and `third` all have runtime class `String[][]`, but do not reference the same array.

## 2. Reading the dimensions List Accurately

When `componentType` is a **non-array** class, the resulting number of dimensions equals **dimensions.length**:

| Array.newInstance Call | Runtime Type | Allocated Dimension Lengths | Leaf Slot Count |
| --- | --- | --- | --- |
| (int.class, 5) | int[] | 5 | 5 |
| (int.class, 2, 3) | int[][] | 2 then 3 | 6 |
| (int.class, 2, 3, 4) | int[][][] | 2 then 3 then 4 | 24 |
| (String.class, 3, 2) | String[][] | 3 then 2 | 6 |
| (String.class, 2, 0, 4) | String[][][] | 2 then 0; deeper dimension has no reachable position | 0 |

If **{2, 3, 4}** is passed, we read it as:

1. **dimensions[0] = 2:** the outer array contains two elements.
2. **dimensions[1] = 3:** each outer element contains an array with three elements.
3. **dimensions[2] = 4:** each second-level element contains an array with four leaf elements.

For an `int[][]` of size 2 × 3, the initial structure is:

~~~text
int[][] data, data.length = 2
    data[0] -> int[3] = [0, 0, 0]
    data[1] -> int[3] = [0, 0, 0]

data[1][2] -> third element of the second row.
~~~

The indices of a dimension of length 2 are 0 and 1; the indices of a dimension of length 3 are 0, 1, and 2. Accessing `data[2]` in an outer array of length 2 throws **ArrayIndexOutOfBoundsException**.

The **product of the sizes** can give the logical number of leaf element positions if all dimensions down to the leaf element type are allocated. It does not directly indicate the number of heap bytes, because Java allocates separate subarray objects and per-object overhead.

## 3. A Multidimensional Array Is Actually an Array of Arrays

In Java, `int[][]` is an array where each element has type `int[]`. Similarly, `String[][][]` contains elements of type `String[][]`. This is not a model that enforces every row to always have the same size.

When calling `Array.newInstance(int.class, 2, 3)`, Java creates an initially uniform shape: two subarrays of length 3. However, afterward you can still replace one subarray with an array of a different length:

~~~java
int[][] rows = new int[3][];
rows[0] = new int[1];
rows[1] = new int[4];
rows[2] = new int[2];

System.out.println(rows.length);     // 3
System.out.println(rows[1].length);  // 4
~~~

This is a **jagged/ragged array**, having three rows of lengths 1, 4, 2. Each row is a separate object, so Java has no invariant requiring all rows to have the same length.

**Distinction needed:** passing the list `{1, 4, 2}` to `Array.newInstance(int.class, 1, 4, 2)` creates a **three-dimensional array**, not a two-dimensional array with three rows of lengths 1, 4, 2.

## 4. When componentType Is Already an Array: The Dimension Count Increases

According to the Javadoc, if `componentType` is **not an array class**, the resulting number of dimensions is the number of elements in `dimensions`. However, if `componentType` **is already an array class**, the final number of dimensions equals:

**rank of componentType + dimensions.length**

The numbers in `dimensions` are used to allocate **new outer array layers**. The layers already present inside the array-typed component **are not allocated**; elements representing the subarray at the last created level are initially `null`.

| Call | Runtime Type | Allocated |
| --- | --- | --- |
| Array.newInstance(String.class, 2) | String[] | 2 String slots, default null |
| Array.newInstance(String.class, 2, 3) | String[][] | Two rows, each row has 3 String slots |
| Array.newInstance(String[].class, 2) | String[][] | Only outer array of length 2; each String[] initially null |
| Array.newInstance(String[].class, 2, 3) | String[][][] | Two outer dimensions 2 × 3; each final String[] initially null |
| Array.newInstance(int[][].class, 2, 3) | int[][][][] | Two outer layers 2 × 3; each int[][] at the next layer initially null |

Two different calls can yield the **same runtime type** while allocating different layers:

~~~java
String[][] full = (String[][]) Array.newInstance(String.class, 2, 3);
String[][] outerOnly = (String[][]) Array.newInstance(String[].class, 2);

System.out.println(full[0].length); // 3
System.out.println(outerOnly[0]);    // null
~~~

With `outerOnly`, accessing `outerOnly[0].length` before assignment throws **NullPointerException**, rather than returning 0. Conversely, `full` already has subarrays of length 3.

You can think of **Array.newInstance(String[].class, 2, 3)** as equivalent in initial shape to **new String[2][3][]**. The type has three dimensions, but only the first two dimensions are allocated.

### Class.getComponentType Strips Only One Layer

~~~java
String[][][] values = (String[][][]) Array.newInstance(String[].class, 2, 3);
System.out.println(values.getClass().getTypeName()); // java.lang.String[][][]
System.out.println(values.getClass().getComponentType().getTypeName());
                                                   // java.lang.String[][]
~~~

`Class.getComponentType()` on `String[][][]` returns `String[][]`, because one element of the outer array is a two-dimensional array. To reach `String.class`, you must continue peeling one layer at a time:

~~~java
Class<?> leaf = values.getClass();
int rank = 0;
while (leaf.isArray()) {
    rank++;
    leaf = leaf.getComponentType();
}
// rank is 3, leaf is String.class
~~~

This is a fragment using the `values` variable created above. **Do not equate the rank of the runtime type with the count of lengths passed in** if the initial `componentType` is already an array class.

## 5. Complete Java 17+ Program

This example covers full allocation, zero length, jagged arrays, array `componentType`, and size-related errors.

Save verbatim to the file **MultiArrayDemo.java**:

~~~java
import java.lang.reflect.Array;

public class MultiArrayDemo {
    public static void main(String[] args) {
        int[][] grid = (int[][]) Array.newInstance(int.class, 2, 3);
        Array.setInt(Array.get(grid, 1), 2, 17);
        System.out.println("grid type=" + grid.getClass().getTypeName());
        System.out.println("grid lengths=" + Array.getLength(grid)
                + "x" + Array.getLength(Array.get(grid, 0)));
        System.out.println("grid default=" + grid[0][0] + ", changed=" + grid[1][2]);

        String[][][] zero = (String[][][]) Array.newInstance(String.class, 2, 0, 4);
        System.out.println("zero lengths=" + zero.length + "," + zero[0].length);

        String[][] ragged = (String[][]) Array.newInstance(String[].class, 2);
        System.out.println("ragged before=" + ragged[0]);
        ragged[0] = new String[] {"A"};
        ragged[1] = new String[] {"B", "C", "D"};
        System.out.println("ragged lengths=" + ragged[0].length + "," + ragged[1].length);

        String[][][] partial =
                (String[][][]) Array.newInstance(String[].class, 2, 3);
        System.out.println("partial type=" + partial.getClass().getTypeName());
        System.out.println("partial lengths=" + partial.length + "," + partial[0].length);
        System.out.println("partial innermost=" + partial[0][0]);
        System.out.println("partial component=" +
                partial.getClass().getComponentType().getTypeName());

        try {
            Array.newInstance(int.class, 2, -1);
        } catch (NegativeArraySizeException ex) {
            System.out.println("negative=" + ex.getClass().getSimpleName());
        }
        try {
            Array.newInstance(void.class, 2);
        } catch (IllegalArgumentException ex) {
            System.out.println("void=" + ex.getClass().getSimpleName());
        }
        try {
            Array.newInstance(int.class, new int[0]);
        } catch (IllegalArgumentException ex) {
            System.out.println("zero ranks=" + ex.getClass().getSimpleName());
        }
        try {
            Array.newInstance(int[][].class, new int[254]);
        } catch (IllegalArgumentException ex) {
            System.out.println("too many ranks=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 -encoding UTF-8 MultiArrayDemo.java
java MultiArrayDemo
~~~

**Actually verified stdout** with javac supporting `--release 17`:

~~~text
grid type=int[][]
grid lengths=2x3
grid default=0, changed=17
zero lengths=2,0
ragged before=null
ragged lengths=1,3
partial type=java.lang.String[][][]
partial lengths=2,3
partial innermost=null
partial component=java.lang.String[][]
negative=NegativeArraySizeException
void=IllegalArgumentException
zero ranks=IllegalArgumentException
too many ranks=IllegalArgumentException
~~~

Explanation:

1. **grid:** `int[][]` consisting of 2 × 3 slots, default `int` value equal to 0. `Array.get(grid, 1)` gives the second `int[]` array; `Array.setInt(..., 2, 17)` assigns the third slot of the subarray.
2. **zero:** `String[][][]` with sizes 2 × 0 × 4 is still valid. The outer array has two slots, but the second-level subarrays both have length 0, with no position `[0][0]` to continue down to the last dimension.
3. **ragged:** when passing `String[].class` with a single length 2, we only receive the outer `String[][]` array with `null` child elements. Then we assign `String[]` of lengths 1 and 3 in turn.
4. **partial:** passing `String[].class` with two lengths 2, 3 creates `String[][][]`; the first two layers are allocated, while the `String[]` elements at the deep layer are `null`. `getComponentType()` from the runtime class returns `String[][]`, not `String`.
5. **negative:** any negative length leads to `NegativeArraySizeException`.
6. **void / zero ranks / too many ranks:** correspond respectively to an invalid `componentType`, no dimensions provided, and requesting 256 dimensions when `int[][].class` already exists plus 254 dimensions; all throw `IllegalArgumentException`.

## 6. Creating a Jagged Array Completely with Reflection

When the number of rows is known in advance but each row has a different length, create only the outer dimension and then allocate each row:

~~~java
int[][] jagged = (int[][]) Array.newInstance(int[].class, 3);

for (int row = 0; row < jagged.length; row++) {
    int size = row + 1;
    Object inner = Array.newInstance(int.class, size);
    Array.set(jagged, row, inner);
}
~~~

After the loop, the three rows have lengths 1, 2, 3. `Array.set` receives an **int[] object** to assign into a slot of `int[][]`; it does not accept an `int` number directly because the elements of the outer array have type `int[]`.

Equivalent static Java syntax:

~~~java
int[][] jagged = new int[3][];
for (int row = 0; row < jagged.length; row++) {
    jagged[row] = new int[row + 1];
}
~~~

If the number of dimensions and component type are both known at compile time, direct **new** syntax is usually simpler and more type-safe. Reflection is advantageous when the type or sizes are determined from metadata/configuration at runtime.

### Creating from Dynamic Configuration

Suppose the program receives the configuration list `{2, 3, 4}`:

~~~java
int[] sizes = {2, 3, 4};
Class<?> component = double.class;
Object data = Array.newInstance(component, sizes);
~~~

The runtime type of `data` is `double[][][]`. **sizes.length** is 3 dimensions, **not** three rows of lengths 2, 3, 4 respectively. If you want three corresponding jagged rows, create `double[3][]` and allocate three separate rows.

## 7. Reading and Writing Multidimensional Arrays with Reflection

Useful APIs in `java.lang.reflect.Array`:

| Method | Meaning |
| --- | --- |
| **Array.getLength(array)** | Array length at the **current layer** |
| **Array.get(array, index)** | Reads element; primitives are boxed if returning `Object` is needed |
| **Array.set(array, index, value)** | Writes a type-compatible element, including subarrays |
| **Array.getInt(array, index)** | Reads an `int` value from a compatible primitive array |
| **Array.setInt(array, index, intValue)** | Writes an `int` into a compatible primitive array |
| **Class.isArray()** | Is the runtime class an array? |
| **Class.getComponentType()** | Peels off exactly one level of component type |

When traversing a multidimensional array with Reflection, each `Array.get` goes down **one layer**:

~~~java
Object cube = Array.newInstance(String.class, 2, 3, 4);
Object plane = Array.get(cube, 1);  // String[][]
Object row = Array.get(plane, 2);   // String[]
Array.set(row, 3, "ok");
System.out.println(Array.get(row, 3)); // ok
~~~

This is a fragment running inside a method after importing `Array`. You cannot assign a `String` directly into `Array.set(cube, 0, "x")`, because an element at the outer layer of `String[][][]` must have type `String[][]`.

Note that **int[] cannot be cast to Object[]** even though an array is an `Object` in Java. However, **int[][] can be treated as Object[] at the outer layer**, because its elements are `int[]` objects. If code needs to apply to every primitive array, keep the variable typed as `Object` and use the `Array` API.

## 8. Dimensions Limits and Exceptions

According to the Java SE 17 Javadoc:

| Condition | Result |
| --- | --- |
| `dimensions` has at least one element, all lengths >= 0 | Valid if resources are sufficient |
| Has a length equal to 0 | Valid: zero-length array at the corresponding layer |
| Has a negative length | **NegativeArraySizeException** |
| `componentType` is null | **NullPointerException** |
| `dimensions` is null | **NullPointerException** |
| `dimensions` is an empty array (0 elements) | **IllegalArgumentException** |
| `componentType` is `void.class` | **IllegalArgumentException** |
| Final dimension count exceeds 255 | **IllegalArgumentException** |
| Requests allocating too much memory | Possible **OutOfMemoryError** |

The final dimension count **does not depend only on dimensions.length**. If `componentType` is already `String[][].class`, 2 dimensions must be added. For example, `Array.newInstance(int[][].class, new int[254])` requests 256 dimensions and is therefore rejected.

**An empty sizes list differs from a size equal to 0**:

~~~java
Array.newInstance(int.class, new int[0]); // IllegalArgumentException
Array.newInstance(int.class, 0);          // int[] of length 0, valid
Array.newInstance(int.class, 2, 0);       // int[][] with 2 rows, each row of length 0
~~~

A dimension of 0 has no elements to traverse deeper into. Therefore `Array.getLength` of the subarray at the preceding layer can still be 0, while accessing index `[0]` of that subarray throws `ArrayIndexOutOfBoundsException`.

Operations after creation also have their own exceptions:

- `Array.getLength(null)` throws **NullPointerException**.
- `Array.getLength` on a non-array object throws **IllegalArgumentException**.
- `Array.get`/`Array.set` with a negative or out-of-bounds index throws **ArrayIndexOutOfBoundsException**.
- `Array.set` with a value incompatible with the element type may throw **IllegalArgumentException**.
- Casting an `Object` to an array type with an incompatible rank/component type throws **ClassCastException**.
- For an outer-only array, reading deeper from a `null` element causes **NullPointerException**.

An array-building tool from untrusted configuration should validate the number of dimensions, the lengths, allocation limits, and the element type to avoid incorrect or excessively large allocations.

## 9. Formulas for Checking Shape and Rank

Suppose:

~~~java
Object created = Array.newInstance(componentType, dimensions);
~~~

The rules:

1. **rank(created)** = **rank(componentType) + dimensions.length**; a non-array class has rank 0.
2. The newly created layers have lengths **dimensions[0], dimensions[1], ...** respectively.
3. If `componentType` is already an array, the layers already inside `componentType` **are not allocated** by the call above.
4. The runtime type tells **how many levels of `[]` brackets exist**, but does not automatically guarantee that every branch currently has all subarrays or the same lengths after the program modifies them.
5. To get the leaf type, call `getComponentType` repeatedly until `Class.isArray()` returns `false`.

| Call | Rank | Element State at the Deepest Allocated Level |
| --- | --- | --- |
| newInstance(int.class, 2, 3) | 2 | `int` default 0 |
| newInstance(int[].class, 2) | 2 | Two `null` `int[]` |
| newInstance(int[].class, 2, 3) | 3 | Six `null` `int[]` |
| newInstance(String.class, 2, 3) | 2 | `String` default null |
| newInstance(String.class, 0, 3) | 2 | No rows to read |

You should not estimate capacity by multiplying all `dimensions` when `componentType` is already an array class: in that case, the unallocated layers do not have corresponding leaf element slots.

## 10. Common Mistakes

1. **Reading {2,3} as two rows of lengths 2 and 3:** this is 2 dimensions of size 2 × 3; a jagged array requires allocating each row individually.
2. **Ignoring the rank already present in componentType:** `String[].class` plus `{2,3}` creates `String[][][]`, not `String[][]`.
3. **Assuming all dimensions in the runtime type are allocated:** with an array-typed component, the remaining dimensions have `null` subarray elements.
4. **Confusing null with a zero-length array:** `null` means there is no array object yet; a 0 dimension is a valid array with `length == 0`.
5. **Calling Array.getLength once to get all dimensions:** the method only returns the length of the specific array object.
6. **Using Object[] for int[]:** a one-dimensional primitive array type is not `Object[]`.
7. **Assuming Array.newInstance automatically invokes the constructor of every reference element:** `String` or object references are initially `null`, not automatically instantiated.
8. **Passing negative/empty dimensions:** rejected; validate before allocating.
9. **Forgetting the 255-dimension limit:** count the existing rank of `componentType` as well.
10. **Creating a huge array from configuration without a capacity limit:** even valid sizes can still cause `OutOfMemoryError`.

## 11. Self-Check

**Question 1.** What type and how many leaf elements does `Array.newInstance(double.class, 4, 2)` have?

**Answer:** `double[][]`, 4 rows × 2 elements, totaling 8 `double` numbers defaulting to `0.0`.

**Question 2.** Does `Array.newInstance(double[].class, 4)` have the same type as Question 1? Have the rows been allocated yet?

**Answer:** Same type `double[][]`, but only the outer array of length 4 exists; all four `double[]` are still `null`.

**Question 3.** What runtime type does `Array.newInstance(String[][].class, 2, 3)` have?

**Answer:** `String[][][][]` with total rank 4; the two new layers have lengths 2 and 3, and the `String[][]` references at the last created layer are still `null`.

**Question 4.** Is `{3,0,5}` valid? Can `[0][0]` be accessed?

**Answer:** Valid. The outer array has length 3, and the second-level subarray has length 0. Accessing `[0][0]` causes `ArrayIndexOutOfBoundsException`.

**Question 5.** If we want three rows of lengths 2, 5, 1, should we call `newInstance(int.class, 2,5,1)`?

**Answer:** No. That is a three-dimensional array 2 × 5 × 1. Create `int[3][]` or `Array.newInstance(int[].class, 3)` and then create the rows of lengths 2, 5, 1.

**Question 6.** Why does `newInstance(int.class, new int[0])` fail while `newInstance(int.class, 0)` succeeds?

**Answer:** The first size array is empty, meaning **no dimensions are provided**. The second call creates **one dimension with length 0**.

**Key takeaway:** the `dimensions` list specifies **the lengths of the new dimensions, ordered from outermost to innermost**. If `componentType` is an array class, the resulting number of dimensions increases, yet the dimensions already present inside `componentType` remain unallocated. Java uses arrays of arrays, so you can create rectangular arrays or jagged arrays with different row lengths.

### Reference Materials

- Java SE 17, Array.newInstance/get/set/getLength: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Array.html
- Java SE 17, Class.isArray and getComponentType: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java Language Specification 17, Chapter 10 — Arrays: https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html
