# Getting the Number of Rows and Each Row's Length in Java Multidimensional Arrays

## 1. A Two-Dimensional Array Is Really an Array of Arrays

In Java, `int[][]` is **an array of `int[]` arrays**. The outer array stores references to each subarray (each row). Therefore, rows **are not required to have the same number of elements**.

```java
int[][] data = {
    {10, 20, 30}, // row 0: 3 elements
    {40},         // row 1: 1 element
    {},           // row 2: 0 elements
    {50, 60}      // row 3: 2 elements
};
```

There are two different length lookups:

- **`data.length`** is the number of elements in the outer array, i.e., **the number of rows**: in the example above, `4`.
- **`data[i].length`** is the number of elements in the subarray at row `i`: respectively `3`, `1`, `0`, `2`.
- Valid row indices: `0 <= i && i < data.length`. Valid column indices for row `i`: `0 <= j && j < data[i].length`, if `data[i] != null`.

`length` is a **field** of an array, not written as `length()`. There is no `data.columns` property or fixed "column count" that applies to all Java two-dimensional arrays.

## 2. Distinguishing Rectangular Arrays and Jagged Arrays

| Creation | Outer array `length` | Length of each row |
| --- | ---: | --- |
| `new int[2][3]` | `2` | `3, 3` |
| `new int[3][0]` | `3` | `0, 0, 0` |
| `new int[0][3]` | `0` | No rows to access |
| `new int[][] {{1, 2}, {3}, {}}` | `3` | `2, 1, 0` |
| `new int[3][]` | `3` | All three rows are initially `null`; `.length` cannot yet be read on each row |

A **rectangular array** has all rows non-`null` and of equal length, such as `new int[2][3]`. A **jagged array** (ragged array) contains rows of different lengths. In Java, even rows that were initially the same size can be reassigned to subarrays of different lengths:

```java
int[][] grid = new int[2][3];
grid[1] = new int[5];
// grid.length == 2
// grid[0].length == 3
// grid[1].length == 5
```

The assignment above **replaces the subarray at row 1**; it does not change the `length` of the original subarray. The length of each array object is fixed after allocation; the number of rows is also fixed as long as the same outer array is used.

## 3. Compilable and Runnable Java 17+ Example

Create the file **`RowLengthsDemo.java`**:

```java
public class RowLengthsDemo {
    public static void main(String[] args) {
        int[][] data = {
            {10, 20, 30},
            {40},
            {},
            {50, 60}
        };

        System.out.println("So hang: " + data.length);

        int total = 0;
        for (int i = 0; i < data.length; i++) {
            int count = data[i].length;
            System.out.println("Hang " + i + ": " + count + " phan tu");
            total += count;
        }
        System.out.println("Tong so phan tu: " + total);

        // Rectangular array: each row has length 3.
        int[][] rectangle = new int[2][3];
        System.out.println("So hang chu nhat: " + rectangle.length);
        for (int i = 0; i < rectangle.length; i++) {
            System.out.println("Chu nhat hang " + i + ": " + rectangle[i].length);
        }

        // Outer array created, but individual rows may not have been created yet.
        int[][] pending = new int[3][];
        pending[0] = new int[2];
        pending[1] = new int[0];
        for (int i = 0; i < pending.length; i++) {
            if (pending[i] == null) {
                System.out.println("Chua tao hang " + i + ": null");
            } else {
                System.out.println("Chua tao hang " + i + ": " + pending[i].length);
            }
        }
    }
}
```

Open a terminal in the directory containing the file with JDK 17 or higher. Run on Windows (CMD/PowerShell) or Linux/macOS:

```bash
javac -encoding UTF-8 RowLengthsDemo.java
java RowLengthsDemo
```

Stdout output (a successful `javac` command prints no output):

```text
So hang: 4
Hang 0: 3 phan tu
Hang 1: 1 phan tu
Hang 2: 0 phan tu
Hang 3: 2 phan tu
Tong so phan tu: 6
So hang chu nhat: 2
Chu nhat hang 0: 3
Chu nhat hang 1: 3
Chua tao hang 0: 2
Chua tao hang 1: 0
Chua tao hang 2: null
```

The first `for` loop iterates over the rows using `data.length`, then reads the element count of **each row** using `data[i].length`. The actual total number of elements equals the sum of the lengths of the allocated rows. `new int[0]` is a row that is **empty yet exists**, unlike a `null` row which **does not yet reference any subarray**.

## 4. Safe Iteration and Calculations Based on Each Row's Length

Do not use `data[0].length` to iterate over all rows unless you know for sure that it is a rectangular array, has a first row, and that row is non-`null`. With a jagged array, retrieve `data[i].length` directly at row `i`:

```java
int[][] values = {{1, 2, 3}, {}, {4, 5}};
for (int row = 0; row < values.length; row++) {
    for (int col = 0; col < values[row].length; col++) {
        System.out.println(values[row][col]);
    }
}
// Prints in order: 1, 2, 3, 4, 5 (one number per line)
```

For data that might contain `null` rows, check before reading the length:

```java
int total = 0;
int[][] values = {new int[2], null, new int[3]};
for (int[] row : values) {
    if (row != null) {
        total += row.length;
    }
}
// total == 5
```

If the outer array itself might also be `null`, check `values != null` before reading `values.length`. Choosing to treat a `null` row as "having no elements" is just a convention for computing the sum; in terms of data representation, a `null` row differs from an empty row.

To check whether all rows have the same size (a rectangular array), compare **every row** against the expected length while ruling out `null` cases:

```java
int[][] values = {{1, 2}, {3, 4}, {5, 6}};
boolean rectangular = true;
int width = values.length == 0 ? 0 : (
        values[0] == null ? -1 : values[0].length);

for (int[] row : values) {
    if (row == null || row.length != width) {
        rectangular = false;
        break;
    }
}
// rectangular == true; width == 2
```

For an empty outer array, the convention here sets `width = 0` and `rectangular = true` because no row violates the condition. Depending on business requirements, you may choose a different way to handle the zero-row case.

## 5. Common Mistakes

1. **Confusing `a.length` with `a[0].length`:** the first expression counts the number of rows; the second only counts elements of row 0, not the number of rows.
2. **Assuming all rows have the same length:** a loop `for (int j = 0; j < a[0].length; j++)` can miss elements on longer rows or cause errors on shorter rows. Use `a[i].length` when iterating row `i`.
3. **Not checking for an empty outer array:** with `new int[0][3]`, `a.length == 0`, so `a[0]` throws `ArrayIndexOutOfBoundsException`.
4. **Not checking for `null` rows:** with `new int[3][]`, `a[0].length` throws `NullPointerException`; allocate the row first or check for `null`.
5. **Using `length()` instead of `length`:** arrays use the `length` field; `String` is what uses the `length()` method.
6. **Confusing length with the last index:** if row `i` has `k` elements and `k > 0`, then the last element is `a[i][k - 1]`, not `a[i][k]`.

**Key takeaway:** `a.length` is the number of rows; `a[i].length` is the individual length of row `i` (only when the row exists). Every traversal and access must respect each row's boundaries.