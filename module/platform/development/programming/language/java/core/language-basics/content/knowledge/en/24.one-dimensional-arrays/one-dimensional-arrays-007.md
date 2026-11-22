# Reading, Updating, and Traversing Elements of a One-Dimensional Array in Java

## 1. Indices, length, and element values

A one-dimensional array (`T[]`) holds a **fixed** number of elements after creation. All elements have the same type `T` and are accessed by an **index** starting at **0**. For an array `a` of length `n`, valid indices are `0` through `n - 1`.

```java
int[] a = {10, 20, 30};
int first = a[0];          // Read: 10
int second = a[1];         // Read: 20
a[1] = 25;                 // Update the second element
int last = a[a.length - 1];// Read: 30
int count = a.length;      // 3
```

- `a[i]` **reads** the value at index `i` in an expression; `a[i] = value` **overwrites** the value at that index. The assigned value must be compatible with the element type.
- `a.length` is a **field** of the array, not a method `length()` like on `String`, and does not change when elements are assigned.
- The first element is `a[0]`; the last element is `a[a.length - 1]` **only when the array is non-empty**.
- With `new int[3]`, all three elements default to `0`; `new boolean[3]` defaults to `false`; reference-type elements such as `String[]` default to `null`. An unassigned local variable cannot be read, even though elements in a newly allocated array already have default values.

Reading or updating an element at a valid index has **O(1)** time complexity. An array does not automatically grow or shrink in element count; to get a new size, you must create a new array (such as with `Arrays.copyOf`).

## 2. Ways to traverse an array

| Traversal style | When to use? | Can update elements directly inside the loop? |
| --- | --- | --- |
| `for (int i = 0; i < a.length; i++)` | Need the index, forward traversal, updating values, filtering by position | Yes: `a[i] = ...` |
| `for (int i = a.length - 1; i >= 0; i--)` | Reverse traversal from end to start | Yes: `a[i] = ...` |
| `while (i < a.length)` | Flexible loop condition or step size | Yes, when using a valid index |
| `for (int value : a)` (*enhanced for*, *for-each*) | Only need to **read** each value in order | Assigning to `value` does not change the array element |

Full traversals typically take **O(n)** time where `n = a.length`. When only reading or aggregating, `for-each` is easy to read and less prone to index bugs; when modifying primitive-type elements, prefer an indexed loop.

Note carefully: `for (int value : a) { value *= 2; }` only modifies the **local variable** `value`. Array `a` remains unchanged. Similarly, for an array of objects, reassigning the loop reference variable in `for-each` does not replace the reference stored in the array slot; however, calling a method that mutates the state of the referenced object itself can still affect that object.

## 3. Standalone Java 17+ example

Save to the file **`DemoMang.java`**:

```java
import java.util.Arrays;

public class DemoMang {
    public static void main(String[] args) {
        int[] diem = {4, 7, 9};
        System.out.println("Ban dau: " + Arrays.toString(diem));

        // Read and then update an element by index.
        int giaTriCu = diem[1];
        diem[1] = 8;
        System.out.println("Gia tri cu: " + giaTriCu);
        System.out.println("Sau cap nhat: " + Arrays.toString(diem));

        // Forward traversal using index.
        System.out.print("For:");
        for (int i = 0; i < diem.length; i++) {
            System.out.print(" " + diem[i]);
        }
        System.out.println();

        // Read-only traversal: for-each.
        System.out.print("For-each:");
        for (int value : diem) {
            System.out.print(" " + value);
        }
        System.out.println();

        // Update all elements; must assign back to diem[i].
        for (int i = 0; i < diem.length; i++) {
            diem[i] += 1;
        }
        System.out.println("Tang moi phan tu: " + Arrays.toString(diem));

        // Aggregate data using for-each.
        int tong = 0;
        for (int value : diem) {
            tong += value;
        }
        System.out.println("Tong: " + tong);

        // Reverse traversal using index.
        System.out.print("Nguoc:");
        for (int i = diem.length - 1; i >= 0; i--) {
            System.out.print(" " + diem[i]);
        }
        System.out.println();
    }
}
```

Open a terminal in the directory containing the file, using **JDK 17 or later** (PowerShell, CMD, and bash all work):

```bash
javac -encoding UTF-8 DemoMang.java
java DemoMang
```

Output on stdout (**`javac` prints nothing on a successful compile**):

```text
Ban dau: [4, 7, 9]
Gia tri cu: 7
Sau cap nhat: [4, 8, 9]
For: 4 8 9
For-each: 4 8 9
Tang moi phan tu: [5, 9, 10]
Tong: 24
Nguoc: 10 9 5
```

In the program: the value `7` read into `giaTriCu` does not change automatically when `diem[1]` is assigned `8`; after the loop that increments each element, the array becomes `[5, 9, 10]`. Calling `Arrays.toString(diem)` prints the contents of a one-dimensional array instead of the default `diem.toString()` output.

## 4. Bounds checking and empty arrays

Java checks the index at access time. `a[-1]` and `a[a.length]` throw **`ArrayIndexOutOfBoundsException`**; accessing `a.length` or `a[i]` when `a == null` throws **`NullPointerException`**. You should not rely on exceptions to control normal execution flow.

```java
int[] a = {};
if (a != null && a.length > 0) {
    System.out.println(a[a.length - 1]);
} else {
    System.out.println("Mang rong");
}

int index = 2;
if (a != null && index >= 0 && index < a.length) {
    System.out.println(a[index]);
}
```

An empty array (`new int[0]` or `{}`) has `length == 0`; `for` and `for-each` loops traversing from the start execute zero times, so they are safe. However, accessing `a[0]` or the last element is invalid. For user-entered indices, check **`0 <= index && index < a.length`** before both reading and writing.

## 5. Common operations

**Find the first element matching a condition**: an indexed `for` loop returns the position, or `-1` when not found:

```java
int[] a = {4, 8, 9};
int foundIndex = -1;
for (int i = 0; i < a.length; i++) {
    if (a[i] == 8) {
        foundIndex = i;
        break;
    }
}
// foundIndex == 1
```

**Conditional update**: traverse by index and write back the desired elements:

```java
for (int i = 0; i < a.length; i++) {
    if (a[i] % 2 == 0) {
        a[i] *= 2;
    }
}
// a = [8, 16, 9]
```

**Avoid unintended side effects when sharing references**:

```java
int[] original = {1, 2};
int[] alias = original;
alias[0] = 99;               // original[0] also becomes 99
int[] copy = original.clone(); // Separate int[] array
copy[0] = 5;                  // original[0] is still 99
```

For arrays containing objects, `clone()` only copies the array structure and **the references**, without deep-copying each object. If you need to set the same value for many elements, you can use `Arrays.fill(a, value)`; to compute new values from indices, you can use `Arrays.setAll(a, i -> ...)` matching the corresponding array type.

## 6. Common pitfalls and selection principles

- **Off-by-one index**: `for (int i = 0; i <= a.length; i++)` will attempt to access `a[a.length]`. When traversing forward over the whole array, use the condition `i < a.length`.
- **Confusing ordinal position with index**: the `k`-th element (counting from 1) has index `k - 1`; the last element is at `length - 1`.
- **Confusing `length` with `length()`**: `array.length` differs from `string.length()`.
- **Assigning to a `for-each` variable and expecting the array to change**: use `a[i] = newValue` if you actually need to modify elements.
- **Forgetting empty or `null` arrays**: check before reading the first/last element and when handling untrusted input.
- **Confusing replacing a value with adding an element**: `a[i] = ...` only replaces at an existing slot; the number of elements does not increase.
- **Confusing values and references**: `int x = a[i]` copies an `int` value; when elements are objects, reading copies the reference to that object.

**Key takeaway:** use `a[i]` to read/write at the exact position, `a.length` to enforce bounds, indexed `for` to modify elements, and `for-each` for read-only traversal.