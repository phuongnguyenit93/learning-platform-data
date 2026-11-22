# `IndexOutOfBoundsException` and `ArrayIndexOutOfBoundsException` in Java

> **Topic:** Java Core → Exception → Runtime exceptions. `IndexOutOfBoundsException` indicates that an **index or range** is outside the bounds permitted by an API. `ArrayIndexOutOfBoundsException` is a **specialized subclass** commonly encountered when directly accessing a Java array with an invalid index. Both belong to the `RuntimeException` branch (unchecked), so the compiler does not require declaring `throws` or catching them with `catch`. To write correct code, you need to understand the bounds of arrays, collections, strings, and subranges, and how to check conditions **before accessing**, rather than treating `try/catch` as a normal way to fix index bugs.

## 1. How do the two exception classes differ?

Abbreviated inheritance tree:

```text
java.lang.Throwable
└── java.lang.Exception
    └── java.lang.RuntimeException
        └── java.lang.IndexOutOfBoundsException
            ├── java.lang.ArrayIndexOutOfBoundsException
            └── java.lang.StringIndexOutOfBoundsException
```

- `IndexOutOfBoundsException`: general class reporting an **index/range** error, such as `List.get(index)`, `List.subList(from,to)`, or range-checking helpers.
- `ArrayIndexOutOfBoundsException`: subtype of `IndexOutOfBoundsException`; thrown when an **array** element access has a negative index or an index not less than `array.length`.
- `StringIndexOutOfBoundsException`: another subtype, commonly encountered when accessing a string character at an invalid position, such as `String.charAt(index)`.
- Because `ArrayIndexOutOfBoundsException extends IndexOutOfBoundsException`, a `catch (IndexOutOfBoundsException e)` can also catch exceptions from arrays.
- The reverse **is not true**: `catch (ArrayIndexOutOfBoundsException)` does not catch every `IndexOutOfBoundsException`, for example index exceptions thrown by a `List` or `String`.

### 1.1. Quick comparison table

| Criterion | `IndexOutOfBoundsException` | `ArrayIndexOutOfBoundsException` |
| --- | --- | --- |
| Role | General for out-of-bounds index/range | Specialized for array access |
| Package | `java.lang` | `java.lang` |
| Direct superclass | `RuntimeException` | `IndexOutOfBoundsException` |
| Checked or unchecked? | Unchecked | Unchecked |
| Common source examples | `List.get`, `List.subList`, `Objects.checkIndex` | `arr[i]`, per-dimension array access |
| Caught by `catch(IndexOutOfBoundsException)`? | Yes | Yes |
| Caught by `catch(ArrayIndexOutOfBoundsException)`? | Not in all cases | Yes |
| Is the message always the same? | No | No |
| Prevention | Check the specific index/range contract | Ensure `0 <= i && i < arr.length` |

**Rule for choosing catch:** When you want to handle index errors uniformly regardless of the data structure, catch the superclass `IndexOutOfBoundsException`. When you only want to handle a specific array access error, you can catch the subclass. However, in most business code, **fixing the index-checking logic** is better than catching these exceptions and continuing as if nothing happened.

## 2. Both are unchecked exceptions

Subtypes of `RuntimeException` are **unchecked**: Java does not enforce the checked rule of catching or declaring `throws` as it does with `IOException`.

Example:

```java
static int elementAt(int[] array, int index) {
    return array[index];
}
```

This method is valid without `throws ArrayIndexOutOfBoundsException`. If `index` is outside the allowed domain, `ArrayIndexOutOfBoundsException` may be thrown at runtime.

A declaration may also explicitly declare `throws` with an unchecked exception for documentation:

```java
static int elementAt(int[] array, int index)
        throws ArrayIndexOutOfBoundsException {
    return array[index];
}
```

However, this declaration is **not required** and does not change compile-time checking.

### 2.1. Why is the caller not required to handle it?

An invalid index is usually a sign that the program violated a **precondition** of the access operation, for example:

- wrong loop termination condition;
- forgetting to validate input data;
- confusing index and length;
- using the length of one structure to access another structure;
- confusing inclusive/exclusive endpoints;
- the data changed size after being checked.

Java does not require every call site to wrap these runtime errors in `try/catch`. Good design typically identifies and enforces invariants, then tests the boundaries. If a user enters an arbitrary index, validation at the system boundary is still necessary to return a friendly input error.

### 2.2. Does the compiler automatically block every invalid index?

No. Example:

```java
int[] values = {10, 20};
System.out.println(values[2]); // Compiles, fails at runtime.
```

Even when the index is the constant `2`, Java generally checks array access bounds **at runtime**. Static analysis tools or IDEs may warn ahead of time, but such warnings should not be treated as a compiler guarantee.

## 3. Valid index domain of an array

For an array of length `n = array.length`:

```text
Valid indices:    0, 1, 2, ..., n-1
Correct check:    0 <= index && index < n
Invalid indices:  index < 0 or index >= n
```

Example `int[] a = {5, 9, 12};`:

| Expression | Result |
| --- | --- |
| `a[0]` | `5` |
| `a[1]` | `9` |
| `a[2]` | `12` |
| `a[-1]` | `ArrayIndexOutOfBoundsException` |
| `a[3]` | `ArrayIndexOutOfBoundsException` |
| `a[100]` | `ArrayIndexOutOfBoundsException` |
| `a[a.length - 1]` | Last element, provided the array is non-empty |
| `a[a.length]` | Invalid: `length` is the number of elements, not the last position |

**Length is not the last index.** When `n > 0`, the last index is `n - 1`. For an empty array `n == 0`, **there is no valid element access index at all**, not even `0`.

### 3.1. Java 17 — array error example with different indices

Create the file **`ArrayBoundsDemo.java`**:

```java
public class ArrayBoundsDemo {
    static void inspect(int[] values, int index) {
        try {
            System.out.println(
                    "index " + index + " = " + values[index]);
        } catch (ArrayIndexOutOfBoundsException e) {
            System.out.println("index " + index + " ngoài giới hạn");
        }
    }

    public static void main(String[] args) {
        int[] numbers = {10, 20, 30};
        System.out.println("length = " + numbers.length);

        inspect(numbers, 0);
        inspect(numbers, 2);
        inspect(numbers, -1);
        inspect(numbers, 3);

        int[] empty = {};
        inspect(empty, 0);
    }
}
```

Compile/run with JDK 17 or later:

```bash
javac -encoding UTF-8 ArrayBoundsDemo.java
java ArrayBoundsDemo
```

Exact stdout:

```text
length = 3
index 0 = 10
index 2 = 30
index -1 ngoài giới hạn
index 3 ngoài giới hạn
index 0 ngoài giới hạn
```

In this program, `catch` is only used to demonstrate the exception path without stopping subsequent test cases. In real applications, if the index is already validated before access, you do not need `catch` around every `a[i]` operation. Especially avoid ignoring an array error and continuing with data assumed to have been read successfully.

### 3.2. What happens when assigning to an invalid index?

Not only **reading** but also **writing** an array element requires a valid index:

```java
int[] values = {3, 4};
values[2] = 99; // Throws ArrayIndexOutOfBoundsException.
```

No new element `values[2]` is created. Java arrays have a **fixed length after creation**; assigning at an out-of-bounds index does not automatically grow the array.

If you need a list that can grow in element count, use a structure like `ArrayList` with the appropriate add operation; do not try to "append" via `arr[arr.length] = value`.

## 4. Index and length: three conditions to remember

For an element index `i` in a structure of length `n`:

```java
boolean validElementIndex = i >= 0 && i < n;
```

For an **insertion position boundary** into a list of length `n`, `i == n` can be valid if the API allows inserting at the end, such as `List.add(index, element)`:

```java
boolean validInsertionPosition = i >= 0 && i <= n;
```

For an **endpoint pair of the range [from, to)**:

```java
boolean validRange = 0 <= from && from <= to && to <= n;
```

These three contracts are **not the same**. A common source of bugs is taking the condition for an **insertion position** (allowing `i == n`) and using it to **read an element** (which does not allow `i == n`).

### 4.1. Why do less-than and less-than-or-equal matter?

- `array[index]` or `list.get(index)`: `index < length/size`.
- `list.add(index, value)`: usually allows `index <= size` to append.
- `list.subList(from, to)`: can allow `to == size` because `to` is an **exclusive end**.
- `String.substring(begin, end)`: `end == length` is valid, whereas `charAt(length)` is invalid.

Do not memorize a single condition and apply it to every method that takes an `index` parameter. Read each API's contract.

## 5. `off-by-one` loop error with `<=`

Common case:

```java
int[] numbers = {4, 7, 9};

for (int i = 0; i <= numbers.length; i++) {
    System.out.println(numbers[i]); // Fails when i == 3.
}
```

The condition `i <= numbers.length` allows `i` to equal the length, but the last index is `length - 1`. Fix it to:

```java
for (int i = 0; i < numbers.length; i++) {
    System.out.println(numbers[i]);
}
```

### 5.1. Java 17 — running the buggy version and the fixed version

Create **`OffByOneDemo.java`**:

```java
public class OffByOneDemo {
    public static void main(String[] args) {
        int[] scores = {8, 13};

        try {
            for (int i = 0; i <= scores.length; i++) {
                System.out.println("Sai: " + scores[i]);
            }
        } catch (ArrayIndexOutOfBoundsException e) {
            System.out.println("Bắt lỗi tại i == length");
        }

        for (int i = 0; i < scores.length; i++) {
            System.out.println("Đúng: " + scores[i]);
        }

        for (int score : scores) {
            System.out.println("For-each: " + score);
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 OffByOneDemo.java
java OffByOneDemo
```

Stdout:

```text
Sai: 8
Sai: 13
Bắt lỗi tại i == length
Đúng: 8
Đúng: 13
For-each: 8
For-each: 13
```

Explanation:

1. The first traversal uses the wrong condition, accessing `scores[2]` when the array has length `2`.
2. The handler only keeps the example program running for comparison; it **does not fix** the loop bug.
3. The second traversal uses `i < scores.length`, so `i` only takes values 0, 1.
4. `for-each` does not require manually computing an index for direct element access. It is a good choice if the goal is only to iterate over values without needing positions.
5. `for-each` does not prevent every bug: if inside the loop there is still an `otherArray[i]` operation using an invalid index, an exception can still occur.

### 5.2. Off-by-one variants

- A loop starts at `i = 1` and reads `array[i]`, accidentally skipping the first element.
- A backward loop uses `i >= 0` but initializes `i = array.length`, accessing out of bounds on the very first iteration.
- After calling `list.remove(index)`, `size()` decreases, yet the code still uses an index based on the old size.
- Using `i <= upperBound` when `upperBound` is **exclusive**.
- Confusing a `[start, end)` range with a `[start, end]` range.

The best fix is to use semantically clear names: `exclusiveEnd`/`inclusiveLastIndex`, and write tests at the start, end, and immediately before/after boundaries.

## 6. `List` and `IndexOutOfBoundsException`

For a `List<T>` of size `n = list.size()`, `list.get(i)` requires `0 <= i < n`. By the List contract, an invalid index leads to `IndexOutOfBoundsException`.

Example:

```java
java.util.List<String> names =
        java.util.List.of("An", "Bình");

System.out.println(names.get(0)); // "An"
System.out.println(names.get(1)); // "Bình"
// names.get(2); // Out of bounds.
```

This is a snippet inside a method. `list.size()` is the **number of elements**, just as `array.length` is the number of array elements. However, List uses the **`size()`** method, whereas arrays use the **`length` field**:

```java
int[] array = {1, 2};
int arraySize = array.length;

java.util.List<Integer> list = java.util.List.of(1, 2);
int listSize = list.size();
```

**Important note on runtime exception type:** The `List.get` contract specifies `IndexOutOfBoundsException`; different implementations may use a specific subclass depending on how they are implemented. Do not use a subtype name appearing in logs as a definitive way to identify which data structure was accessed. When handling code written against the `List` interface, you should generally rely on the superclass contract rather than depending on internal messages or subtypes.

### 6.1. `get` vs. `add(index, element)`

For a List with `size() == 2`:

```java
java.util.List<String> names =
        new java.util.ArrayList<>(
                java.util.List.of("A", "B"));

names.add(2, "C");  // Valid: insert at the end.
System.out.println(names.get(2)); // Valid after adding.
```

This snippet inside a method will print `C`. Before `add(2,"C")`, `names.get(2)` is invalid; after adding, the size becomes 3, so index 2 is valid.

With `List.of(...)`, mutating operations like `add` throw `UnsupportedOperationException`, **not** `IndexOutOfBoundsException` just because the list is immutable. Therefore, when reading a stack trace, distinguish **index range** errors from **collection mutability** errors.

## 7. `StringIndexOutOfBoundsException`: a sibling under the same superclass

`String.charAt(index)` requires `0 <= index < string.length()`. An invalid index typically throws `StringIndexOutOfBoundsException`, which is also a subtype of `IndexOutOfBoundsException`.

```java
String text = "Java";
// text.charAt(4); // Invalid because length == 4.
```

A superclass handler catches multiple cases:

```java
try {
    String text = "Java";
    System.out.println(text.charAt(text.length()));
} catch (IndexOutOfBoundsException e) {
    System.out.println("Vị trí ký tự không hợp lệ");
}
```

This demonstration snippet prints `Vị trí ký tự không hợp lệ`.

### 7.1. Do not confuse `String.length()` with the number of Unicode code points

Java strings store values as **UTF-16 units**. A Unicode character outside the Basic Multilingual Plane (such as many emojis) uses **two UTF-16 code units** (a surrogate pair). Therefore:

- `String.length()` returns the number of **UTF-16 code units**, not necessarily the number of user-perceived characters.
- `charAt(i)` returns a `char` — a single code unit — not necessarily a complete Unicode code point.
- `codePointCount(begin,end)` counts Unicode code points in the selected range.
- `offsetByCodePoints(index, codePointOffset)` helps shift positions by code points.
- The index accepted by `charAt` is always a UTF-16 index, not a "display character" ordinal.

### 7.2. Java 17 — Unicode does not change bounds rules

Create **`StringBoundsUnicodeDemo.java`**:

```java
public class StringBoundsUnicodeDemo {
    public static void main(String[] args) {
        String text = "A😀B";

        System.out.println("UTF-16 length: " + text.length());
        System.out.println("Code points: "
                + text.codePointCount(0, text.length()));
        System.out.println("Low surrogate at 2: "
                + Character.isLowSurrogate(text.charAt(2)));

        int offsetOfB = text.offsetByCodePoints(0, 2);
        System.out.println("Offset of B: " + offsetOfB);

        try {
            text.charAt(text.length());
        } catch (StringIndexOutOfBoundsException e) {
            System.out.println("Exception: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 StringBoundsUnicodeDemo.java
java StringBoundsUnicodeDemo
```

Stdout:

```text
UTF-16 length: 4
Code points: 3
Low surrogate at 2: true
Offset of B: 3
Exception: StringIndexOutOfBoundsException
```

Because `😀` uses two code units, `text` has `length() == 4` even though it contains three code points (`A`, emoji, `B`). `charAt(2)` is valid **with respect to bounds** but returns the second half of the surrogate pair; to get the full code point, use `codePointAt` or appropriate Unicode APIs.

There is still a caveat: a *code point* is not synonymous with a display character (grapheme cluster), because many sequences have combining marks. When working with user interfaces, you must understand which level of abstraction you want to count.

## 8. Subranges: `[from, to)` and `IndexOutOfBoundsException`

Many Java APIs use a **half-open interval**:

```text
[fromIndex, toIndex)
inclusive of fromIndex, exclusive of toIndex
```

For a structure of length `n`, the valid condition is typically:

```text
0 <= fromIndex <= toIndex <= n
```

Two examples:

- `list.subList(1, 3)` takes elements at indices 1, 2.
- `text.substring(1, 3)` takes the UTF-16 code units corresponding to indices 1, 2.

Each API has additional conditions and specific exception types. If `fromIndex > toIndex`, some APIs (like `List.subList`) may throw `IllegalArgumentException` rather than necessarily `IndexOutOfBoundsException`; read the method contract instead of guessing from the name "slice".

### 8.1. Java 17 example with an exclusive upper bound

Create **`RangeBoundsDemo.java`**:

```java
import java.util.List;

public class RangeBoundsDemo {
    public static void main(String[] args) {
        List<String> names = List.of("A", "B", "C");

        System.out.println("subList(1, 3): "
                + names.subList(1, 3));
        System.out.println("subList(3, 3): "
                + names.subList(3, 3));

        try {
            names.subList(2, 4);
        } catch (IndexOutOfBoundsException e) {
            System.out.println("toIndex 4 vượt size 3");
        }

        String text = "Java";
        System.out.println("substring(1, 4): "
                + text.substring(1, 4));
        System.out.println("substring(4, 4): '"
                + text.substring(4, 4) + "'");
    }
}
```

Run:

```bash
javac -encoding UTF-8 RangeBoundsDemo.java
java RangeBoundsDemo
```

Stdout:

```text
subList(1, 3): [B, C]
subList(3, 3): []
toIndex 4 vượt size 3
substring(1, 4): ava
substring(4, 4): ''
```

**Takeaways:**

1. `toIndex == size` is valid in `subList` because the upper endpoint is **exclusive**.
2. `fromIndex == toIndex == size` represents a valid empty subrange.
3. `toIndex > size` is rejected; in this example the `IndexOutOfBoundsException` handler catches it.
4. For `String.substring`, `endIndex == length` is valid; this **differs from `charAt(length)`**.
5. In real code, `subList` is usually a **view** of the backing list, so structurally modifying the original list while still using the view can cause issues independent of bounds. `List.of` in the example is unmodifiable, making it simpler.

## 9. Standard index-checking utility: `Objects.checkIndex`

Since Java 9, `java.util.Objects` provides methods to check indices and ranges:

```java
Objects.checkIndex(index, length);
Objects.checkFromToIndex(fromIndex, toIndex, length);
Objects.checkFromIndexSize(fromIndex, size, length);
```

These helpers throw `IndexOutOfBoundsException` if the arguments are invalid, and return `index` or `fromIndex` when valid. They are especially useful when **building APIs that operate on data regions** and need consistent validation before access.

| Helper | Validity condition (semantically) | Common use case |
| --- | --- | --- |
| `checkIndex(i, n)` | `0 <= i < n` | Accessing a single element |
| `checkFromToIndex(a,b,n)` | `0 <= a <= b <= n` | Range `[a,b)` |
| `checkFromIndexSize(a,size,n)` | `0 <= a`, `0 <= size`, and `a + size <= n` using overflow-safe checking | Range starting at `a` with `size` elements |

The mathematical condition `a + size <= n` must be enforced in a way that does not break due to integer overflow; use the standard helper or safe comparisons—do not arbitrarily add two `int` values and trust the result to be checked accurately.

**Version distinction:** `Objects.checkIndex` and the two range-checking methods above **do not exist in Java 8**. Projects using Java 17 can use them directly.

### 9.1. Java 17 — `Objects` example with deterministic output

Create **`ObjectsIndexCheckDemo.java`**:

```java
import java.util.Objects;

public class ObjectsIndexCheckDemo {
    static void test(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": OK");
        } catch (IndexOutOfBoundsException e) {
            System.out.println(label + ": OUT");
        }
    }

    public static void main(String[] args) {
        test("index 2", () -> Objects.checkIndex(2, 3));
        test("index 3", () -> Objects.checkIndex(3, 3));
        test("index -1", () -> Objects.checkIndex(-1, 3));

        test("range 0..3",
                () -> Objects.checkFromToIndex(0, 3, 3));
        test("empty range",
                () -> Objects.checkFromToIndex(3, 3, 3));
        test("range 0..4",
                () -> Objects.checkFromToIndex(0, 4, 3));

        test("size fits",
                () -> Objects.checkFromIndexSize(1, 2, 3));
        test("size exceeds",
                () -> Objects.checkFromIndexSize(2, 2, 3));
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 ObjectsIndexCheckDemo.java
java ObjectsIndexCheckDemo
```

Stdout:

```text
index 2: OK
index 3: OUT
index -1: OUT
range 0..3: OK
empty range: OK
range 0..4: OUT
size fits: OK
size exceeds: OUT
```

The snippet uses `Runnable` to test the checks and prints only the result, without relying on exception text. Because the three `Objects` helpers throw unchecked exceptions, the `Runnable.run()` callback (which declares no checked exceptions) fits well.

### 9.2. Where should index checks live?

- Input-receiving layer: validate user-supplied indices and return a clear message.
- Library methods: check preconditions if index/range is part of the public contract; you can use `Objects.checkIndex` or custom checks to provide an appropriate message.
- Internal loops: guarantee invariants through loop conditions/algorithm design rather than wrapping each access in `try/catch`.
- Pre-validated inputs: you must still consider cases where the data structure changes size between **check** and **use** if shared mutable state/concurrency is involved.

## 10. Two-dimensional arrays: each dimension has its own length

In Java, a "2D array" is an **array containing sub-arrays**. Rows can have different lengths (*jagged array*) or even be `null`:

```java
int[][] matrix = {
    {1, 2, 3},
    {4}
};
```

For the structure above:

- `matrix.length == 2`: there are two rows.
- `matrix[0].length == 3`: the first row has three elements.
- `matrix[1].length == 1`: the second row has one element.
- `matrix[1][1]`: invalid **column index of the second row**, causing `ArrayIndexOutOfBoundsException`.
- `matrix[2][0]`: invalid **row index**, also causing `ArrayIndexOutOfBoundsException`.
- If `matrix[1] == null`, `matrix[1][0]` causes `NullPointerException`, **not** an out-of-bounds error at the row.

### 10.1. Java 17 — accessing a jagged array

Create **`JaggedArrayBoundsDemo.java`**:

```java
public class JaggedArrayBoundsDemo {
    static void inspect(int[][] matrix, int row, int column) {
        try {
            System.out.println("(" + row + "," + column + ") = "
                    + matrix[row][column]);
        } catch (ArrayIndexOutOfBoundsException e) {
            System.out.println("(" + row + "," + column
                    + ") ngoài giới hạn");
        }
    }

    public static void main(String[] args) {
        int[][] matrix = {
                {1, 2, 3},
                {4}
        };

        System.out.println("Số hàng: " + matrix.length);
        System.out.println("Độ dài hàng 1: "
                + matrix[1].length);

        inspect(matrix, 0, 2);
        inspect(matrix, 1, 0);
        inspect(matrix, 1, 1);
        inspect(matrix, 2, 0);
    }
}
```

Run:

```bash
javac -encoding UTF-8 JaggedArrayBoundsDemo.java
java JaggedArrayBoundsDemo
```

Stdout:

```text
Số hàng: 2
Độ dài hàng 1: 1
(0,2) = 3
(1,0) = 4
(1,1) ngoài giới hạn
(2,0) ngoài giới hạn
```

**Lesson:** you cannot use `matrix[0].length` for every row if the data is a jagged array. Safe traversal:

```java
for (int row = 0; row < matrix.length; row++) {
    if (matrix[row] == null) {
        continue; // Policy depends on data contract.
    }
    for (int col = 0; col < matrix[row].length; col++) {
        System.out.println(matrix[row][col]);
    }
}
```

This is a snippet inside a method, not a standalone file. Checking `null` is a separate condition from checking indices; avoid conflating `NullPointerException` with `ArrayIndexOutOfBoundsException`.

## 11. External data: validate before accessing

An index coming from a form, CLI, or HTTP request might be:

- a non-numeric string (`"abc"`);
- a negative number (`"-1"`);
- an integer exceeding the array size;
- an integer too large to parse as `int`;
- a 1-based index from the client while Java uses 0-based indexing.

Distinguish **parsing errors** from **out-of-range errors**. `Integer.parseInt("abc")` throws `NumberFormatException`; it does not directly throw an array `IndexOutOfBoundsException`.

### 11.1. Java 17 — validating input before reading

Create **`ValidatedIndexInputDemo.java`**:

```java
import java.util.List;

public class ValidatedIndexInputDemo {
    static void lookup(int[] values, String raw) {
        try {
            int index = Integer.parseInt(raw);

            if (index < 0 || index >= values.length) {
                System.out.println(raw + ": ngoài phạm vi");
                return;
            }

            System.out.println(raw + ": " + values[index]);
        } catch (NumberFormatException e) {
            System.out.println(raw + ": không phải số nguyên");
        }
    }

    public static void main(String[] args) {
        int[] values = {100, 200};

        for (String raw : List.of("0", "1", "2", "-1", "abc")) {
            lookup(values, raw);
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 ValidatedIndexInputDemo.java
java ValidatedIndexInputDemo
```

Stdout:

```text
0: 100
1: 200
2: ngoài phạm vi
-1: ngoài phạm vi
abc: không phải số nguyên
```

Here, the array exception **never needs to occur** for out-of-range data because the code checks beforehand. The application layer can map invalid input cases to a validation result or HTTP 400/422 depending on the contract, without waiting for the JVM to throw `ArrayIndexOutOfBoundsException` and treating that as the way to report user errors.

### 11.2. What if the user counts positions starting at 1?

For example, the UI says "choose item 1, 2, 3" while Java stores them at indices 0, 1, 2. Define a controlled conversion:

```java
int oneBasedPosition = 2;
int zeroBasedIndex = oneBasedPosition - 1;
```

Avoid subtracting 1 if the input is already zero-based. Also, do not compute `input - 1` before considering overflow risk with `Integer.MIN_VALUE`; ensure the input is in the `1..n` domain first, and only then convert to `0..n-1`.

## 12. Catching exceptions: superclass or subclass?

Because of the inheritance relationship, both approaches have value in their own contexts.

### 12.1. General handler for multiple data structures

```java
try {
    useIndex();
} catch (IndexOutOfBoundsException e) {
    reportInvalidPosition(e);
}
```

This is an illustrative pattern; `useIndex()` and `reportInvalidPosition(...)` are not defined. A superclass handler can catch both `ArrayIndexOutOfBoundsException` and `StringIndexOutOfBoundsException`.

### 12.2. Specialized handler for arrays

```java
try {
    int value = numbers[index];
    System.out.println(value);
} catch (ArrayIndexOutOfBoundsException e) {
    System.out.println("Truy cập mảng sai vị trí");
}
```

A snippet inside a method, assuming `numbers` and `index` have appropriate types. The handler catches only the specialized subtype.

### 12.3. Order of two handlers when using both

```java
try {
    readSomething();
} catch (ArrayIndexOutOfBoundsException e) {
    System.out.println("Lỗi chỉ số mảng");
} catch (IndexOutOfBoundsException e) {
    System.out.println("Lỗi chỉ số khác");
}
```

This is an illustrative pattern; `readSomething()` is not defined. The **subclass** handler must come before the **superclass** handler, because putting `catch(IndexOutOfBoundsException)` first would also catch `ArrayIndexOutOfBoundsException` and make the specialized branch unreachable.

The following snippet is **intentionally invalid**:

```java
try {
    readSomething();
} catch (IndexOutOfBoundsException e) {
    // Catches too broadly first.
} catch (ArrayIndexOutOfBoundsException e) {
    // Compiler reports unreachable catch.
}
```

A multi-catch `catch (IndexOutOfBoundsException | ArrayIndexOutOfBoundsException e)` is also **invalid** because the alternatives have a superclass–subclass relationship; keep only the superclass if unified handling is truly needed.

## 13. Java 17 program — three error types caught by one superclass

Create **`BoundsHierarchyDemo.java`**:

```java
import java.util.List;

public class BoundsHierarchyDemo {
    static void inspect(String label, Runnable operation) {
        try {
            operation.run();
        } catch (IndexOutOfBoundsException e) {
            System.out.println(label + ": "
                    + e.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        inspect("array", () -> {
            int[] numbers = {1, 2};
            System.out.println(numbers[2]);
        });

        inspect("list", () -> {
            List<String> names = List.of("A", "B");
            System.out.println(names.get(2));
        });

        inspect("string", () -> {
            String text = "AB";
            System.out.println(text.charAt(2));
        });
    }
}
```

Run:

```bash
javac -encoding UTF-8 BoundsHierarchyDemo.java
java BoundsHierarchyDemo
```

**Output when run on standard JDK 17:**

```text
array: ArrayIndexOutOfBoundsException
list: IndexOutOfBoundsException
string: StringIndexOutOfBoundsException
```

Analysis:

1. `numbers[2]` fails when length is 2: exception from array access.
2. `names.get(2)` fails when list size is 2: JDK 17's `List.of` implementation typically throws `IndexOutOfBoundsException`.
3. `text.charAt(2)` fails on a string of length 2: `StringIndexOutOfBoundsException`.
4. All three are caught by `catch(IndexOutOfBoundsException)` due to the inheritance relationship.
5. **Do not couple production code to the exact subtype/message of every `List` implementation.** The public contract of `List.get` is `IndexOutOfBoundsException`, and implementations may have different internal characteristics.

API lesson: choose handlers based on **contract and recovery policy**, not just to print a fixed exception name.

## 14. Prevent beforehand or catch afterward?

In internal code, an out-of-bounds error usually indicates a bug. Catching it and silently continuing can hide bugs and leave application state incorrect.

Anti-pattern:

```java
for (int i = 0; i <= values.length; i++) {
    try {
        total += values[i];
    } catch (ArrayIndexOutOfBoundsException ignored) {
        // Silently skip the last iteration.
    }
}
```

Illustrative snippet, assuming `values` and `total` are already defined. The current result may "look right" by coincidence because the exception only occurs on the last iteration; however, the loop is wrong and unsafe if the algorithm changes. Fix the condition to `i < values.length`.

### 14.1. When is catching reasonable?

- In educational examples and tests that need to demonstrate the exception.
- At the boundary of an independent request, to turn unexpected errors into an explicit failure, log them, and prevent them from breaking other task orchestration.
- In APIs with a special contract relying on an exception to signal an invalid index, where the caller genuinely has a plan to adjust the index or fall back.
- When processing untrusted data sources and the corresponding exception is established as part of the control contract.

Even when catching is reasonable, ask: **can this layer fix the error?** If not, report the failure or rethrow. Do not treat `catch` as having "cured" the root cause.

### 14.2. Why not parse the message?

Error strings can vary across JDKs, array types, implementers, contexts, and releases. Example to avoid:

```java
try {
    useIndex();
} catch (IndexOutOfBoundsException e) {
    if (e.getMessage().contains("Index 3")) {
        // Logic based on error text: fragile.
    }
}
```

This illustration requires `useIndex()`, and the message can be `null`. If you need to return index and bound information to the UI, **keep them in the input/validation data** instead of trying to parse `getMessage()`. If logging is needed, log the exception object and the index/size context separately, following security policy.

## 15. `NullPointerException`, `ArrayStoreException`, and other errors are not bounds errors

The following errors have different causes:

| Exception | Situation |
| --- | --- |
| `ArrayIndexOutOfBoundsException` | Array element access index outside `[0, length)` |
| `IndexOutOfBoundsException` | Index/range outside a List/helper contract |
| `StringIndexOutOfBoundsException` | Invalid string index |
| `NullPointerException` | Using a `null` reference as an object/array to access |
| `ArrayStoreException` | Assigning an incompatible object to the runtime component type of a reference array |
| `UnsupportedOperationException` | Operation not supported by the collection, e.g., adding to `List.of` |
| `NegativeArraySizeException` | Creating an array with a negative size |

Two easily confused examples:

```java
int[] a = null;
// int x = a[0]; // NullPointerException, not a bounds error.

int[] b = new int[-1];
// NegativeArraySizeException when creating the array.
```

These are illustrative snippets that **intentionally cause runtime errors**.

With a reference array:

```java
Object[] values = new String[1];
// values[0] = Integer.valueOf(123); // ArrayStoreException.
```

Index `0` is **valid**, but the `Integer` object type does not match the runtime component type `String`. This is an array store type error, not an out-of-bounds index error.

### 15.1. Multidimensional arrays can fail with null at inner levels

```java
int[][] rows = new int[2][];
rows[0] = new int[] {1};
// rows[1][0]; // NullPointerException because rows[1] has no sub-array yet.
```

Even when `rows.length == 2` and row index `1` is valid, the sub-array can still be `null`. You must check each level for its corresponding risk.

## 16. Data boundaries and consistency when size changes

Suppose a mutable `List` is shared between two threads:

```java
if (index >= 0 && index < list.size()) {
    return list.get(index);
}
```

This is an illustrative method assuming `list` is already defined. The condition does **not** guarantee safety if another thread can shrink the size between the check and the `get` call. This is a *time-of-check to time-of-use* (TOCTOU) case.

Strategies depending on context:

- Confine ownership of the collection to a single thread.
- Synchronize both check and use under the same appropriate lock (all list-mutating operations must also obey the lock).
- Use an immutable snapshot (`List.copyOf`) when appropriate for a stable size and contents.
- Use concurrent structures and understand their operation contracts; do not assume all thread-safe structures share the same index semantics.
- Design APIs to avoid sharing indices into a mutating container when possible.

**Do not claim** "we checked `index < list.size()` so a bounds error can never happen": that claim also depends on there being no unsynchronized mutation, overflow, or mismatch in the variable holding the collection.

### 16.1. `List.subList` and modifying the backing list

`subList` is normally a **view** over the original list, not necessarily an independent copy. Structurally modifying the original list outside the sublist can make the view's semantics undefined/invalid according to the contract. If a snapshot is needed, choose `new ArrayList<>(list.subList(...))` or `List.copyOf(...)` when appropriate, after validating the range and concurrency.

## 17. How to debug a bounds exception

When `ArrayIndexOutOfBoundsException` or `IndexOutOfBoundsException` appears in production, follow this process:

1. **Read the stack trace** to identify the method and line of code actually performing the indexed access.
2. **Identify the container**: array, list, string, buffer, view, or 2D array data.
3. **Read the index/range contract** of the API being called; do not assume every API uses `[0,n)`.
4. **Log the index and length/size in the same context** (do not put sensitive data into logs).
5. **Check boundary cases**: empty, single element, index 0, last index, `index == n`, negative index.
6. **Inspect index transformations**: addition/subtraction, one-based to zero-based conversion, offsets, start/end calculation.
7. **With multiple containers**, verify that the size being used belongs to the exact container being accessed.
8. **Check concurrency**: can anything change the size after validation?
9. **Fix the invariant or input validation**, rather than just adding a `catch` to suppress logs.
10. **Add a regression test** with the minimal input that reproduces the bug.

### 17.1. Read the exception type before reading the message

Example:

```text
java.lang.ArrayIndexOutOfBoundsException: Index 3 out of bounds for length 3
    at example.OrderService.calculate(OrderService.java:42)
```

This is an **illustrative message**, not a fixed output across all JDKs. Read it as: an array operation used an index equal to the length; inspect that line in `calculate` and check the loop or index formula. Do not build production logic that parses the string `"Index 3..."`, because the message can vary.

### 17.2. What should be logged when debugging?

As long as it does not contain sensitive data, useful information includes `index`, `size`, the operation name, and a request correlation ID. For Unicode strings, note whether you are dealing with a **UTF-16 offset** or a **code point offset**. For jagged arrays, log the row index, row count, column index, and corresponding row length.

Do not log the entire input/request just because of a bad index; minimal logging is usually enough to find the bug.

## 18. Performance: bounds checks are part of Java's safety

Every indexed array access must obey bounds-checking semantics. The JVM/JIT can **optimize away redundant checks** in certain loops if it can prove the index is always valid, but it must not alter the observable Java behavior when an index is actually invalid.

This leads to several guidelines:

- Do not use `try/catch` as a "fast" check instead of a proper loop condition.
- Avoid intentionally indexing `array[index]` hoping to get a default value when out of bounds; Java does not do that.
- Frequent bounds errors on a hot path indicate a need to fix the algorithm/validation, not just optimize logging.
- The compiler/JIT does not skip checking invalid indices just because a loop is considered "fast".
- `for-each`, `Arrays`, and collection APIs can help reduce manual indexing bugs; choose the right tool for the job.

There is no need to guess whether the JIT eliminated a bounds check at a specific runtime. If performance matters, benchmark on real workloads and keep correctness tests first.

## 19. Unit testing boundaries

Valuable test cases:

| Structure size | Input | Expected |
| --- | --- | --- |
| Empty array `n=0` | `0` | `ArrayIndexOutOfBoundsException` or validation failure before access |
| Single-element array `n=1` | `0` | Valid |
| Single-element array `n=1` | `1` | Out of bounds |
| Three-element array `n=3` | `2` | Valid last element |
| Three-element array `n=3` | `3` | Out of bounds |
| Any `n>=0` | `-1` | Out of bounds |
| Subrange `n=3` | `[3,3)` | Valid empty range if allowed by API |
| Subrange `n=3` | `[2,4)` | Out of bounds |
| Jagged array | Row 1 with length 1, col 1 | Out of bounds for that row |

### 19.1. Illustrative JUnit 5 example

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;

class BoundsContractTest {
    @Test
    void arrayRejectsInvalidIndex() {
        int[] values = {4, 5};
        assertEquals(5, values[1]);
        assertThrows(ArrayIndexOutOfBoundsException.class,
                () -> { int ignored = values[2]; });
    }

    @Test
    void listRejectsInvalidIndexByContract() {
        List<Integer> values = List.of(4, 5);
        assertThrows(IndexOutOfBoundsException.class,
                () -> values.get(2));
    }

    @Test
    void halfOpenRangeAllowsEmptyTail() {
        List<String> names = List.of("A", "B");
        assertTrue(names.subList(2, 2).isEmpty());
    }
}
```

**This is a test file for a project with JUnit Jupiter**, not a standalone `javac` program using only the standard library. The tests verify the operation's contract rather than comparing exception messages. `assertThrows(IndexOutOfBoundsException.class, ...)` accepts subclass instances if an implementation uses a subtype.

### 19.2. Testing validation vs. testing naturally thrown exceptions

If a public API validates `index` and explicitly returns an error `Result`, test the **validation result**, rather than forcing it to throw `ArrayIndexOutOfBoundsException`. Runtime exceptions from array access usually reflect a bug path; an application may choose to report input errors differently before touching the array.

## 20. Common mistakes and how to fix them

| Mistake | Result | Fix |
| --- | --- | --- |
| Using `i <= array.length` when reading `array[i]` | Accesses index equal to length | Use `i < array.length` |
| Reading `array[array.length]` to get the last element | Always out of bounds | Use `array[array.length-1]` if non-empty |
| Reading `array[0]` when length is 0 | `ArrayIndexOutOfBoundsException` | Check for empty / handle empty case |
| Using `list.get(list.size())` to append | Read index out of bounds | `list.add(element)` or `list.add(size, element)` if mutable |
| Using row 0's length for all rows | Jagged array has rows of different lengths | Use `matrix[row].length` |
| Using `String.charAt(length)` | Invalid string index | Determine valid index, or use end-exclusive `substring` |
| Confusing code point offset with UTF-16 index | Accessing inside a surrogate pair or wrong position | Use `codePointAt`/`offsetByCodePoints` |
| Assuming `[from,to]` when API expects `[from,to)` | Off by one element | Read the exclusive-endpoint contract |
| Treating `i==n` as always invalid | Wrong for some insert/empty-end-range operations | Distinguish element index from insertion/range position |
| Catching `ArrayIndexOutOfBoundsException` for all List index errors | May miss plain `IndexOutOfBoundsException` | Follow API contract; catch superclass when truly needed |
| Placing `catch(IndexOutOfBoundsException)` before subclass catch | Subclass handler is unreachable | Put the specific catch first |
| Multi-catch superclass + subclass | Does not compile | Keep the superclass or two valid separate catches |
| Catching and ignoring inside a loop | Hides loop condition bug | Fix the invariant |
| Parsing `getMessage()` to extract index | Message varies by runtime/version | Keep index and size separately |
| Forgetting `null` array | `NullPointerException`, not bounds | Check data/`null` independently |
| Using `new int[-1]` and thinking it's an access error | `NegativeArraySizeException` on creation | Validate creation size |
| Modifying List concurrently after checking size | Check/use can diverge | Synchronize, snapshot, or enforce ownership |
| Taking 1-based index and using it directly on an array | Off by 1 | Validate one-based position then subtract 1 |
| Using computed index with overflow risk | Index becomes negative or wrong | Use overflow-safe math/validation |
| Returning raw stack trace to client | Exposes internal details | Map to a safe error response and log carefully |

## 21. Frequently asked questions

### 21.1. Is `ArrayIndexOutOfBoundsException` an `IndexOutOfBoundsException`?

Yes, because it **extends** `IndexOutOfBoundsException`. Therefore `catch(IndexOutOfBoundsException)` can catch `ArrayIndexOutOfBoundsException`, while `catch(ArrayIndexOutOfBoundsException)` is not guaranteed to catch errors from `List.get` or `String.charAt`.

### 21.2. Are these two exceptions checked exceptions?

No. They belong to `RuntimeException`, so code is not required to declare `throws` or catch them. However, they can still be caught when an appropriate handling policy exists.

### 21.3. Is `array.length` the last index?

No. For a non-empty array, the last index is `array.length - 1`. If the array is empty, no index is valid.

### 21.4. Can I access `array[-1]` to get the last element like in Python?

No. Java **does not** use negative indexing to access from the end. `array[-1]` throws `ArrayIndexOutOfBoundsException`. To get the last element, check that the array is non-empty and use `array[array.length-1]`.

### 21.5. Why can `list.add(list.size(), x)` be valid, while `list.get(list.size())` is not?

`add(index, element)` (on a mutable `List`) typically accepts an **insertion position** in `[0,size]`, including the end. `get(index)` accepts an **element position** in `[0,size)`. These are two different contracts.

### 21.6. Why is `substring(0, length)` valid while `charAt(length)` is invalid?

Because `substring(begin,end)` is **end-exclusive**; the `end` index is the boundary after the last element. `charAt(index)` needs the exact position of an existing code unit, so `index` must be strictly less than `length`.

### 21.7. Should every access be wrapped in `try/catch(IndexOutOfBoundsException)`?

Usually no. For internal code, fixing loops/validation and testing boundaries is clearer. Catching the exception is only appropriate if that layer has a genuine handling policy or error-translation responsibility.

### 21.8. Can we rely on the message "Index X out of bounds for length N"?

Not as a **stable protocol**. Some JDKs produce such messages, but the text can differ across implementations and APIs. Use the exception type and original index/size data instead of parsing the message.

### 21.9. Does `List.of` with an invalid index always throw `ArrayIndexOutOfBoundsException`?

You should not assume that. `List` publishes the `IndexOutOfBoundsException` contract; JDK implementations may use specific checks and subtypes. If you need to handle List index errors generally, catch the superclass.

### 21.10. Does a bounds check guarantee thread safety?

No. A bounds check validates the index against the state observed at one operation; a mutable list modified by another thread can still cause errors or consistency issues. You need an independent synchronization/snapshot policy.

## 22. Practice exercises

### Exercise 1 — Predict the indices

`int[] a = {2, 4, 6};`. State the results of `a[0]`, `a[2]`, `a[3]`, and `a[-1]`. **Answer:** `2`, `6`, and two `ArrayIndexOutOfBoundsException` errors.

### Exercise 2 — Fix the loop

Given `for (int i = 0; i <= a.length; i++)`, rewrite the condition to iterate over all elements and handle the empty-array case. **Answer:** `i < a.length`; the loop naturally skips if the array is empty.

### Exercise 3 — Catch by hierarchy

Write a snippet with `catch(ArrayIndexOutOfBoundsException)` before `catch(IndexOutOfBoundsException)`. Explain why reversing the order makes the second handler unreachable.

### Exercise 4 — Jagged array

Given `int[][] a = {{1,2,3}, {4}}`, explain `a[1][0]`, `a[1][1]`, and `a[2][0]`. Why is using `a[0].length` for all rows wrong?

### Exercise 5 — String and UTF-16

Run `StringBoundsUnicodeDemo`. Explain why `length()` is 4 while `codePointCount` is 3. Is `charAt(2)` an invalid index or just retrieving part of a surrogate pair? **Answer:** index 2 is valid, but it returns the low surrogate.

### Exercise 6 — Starting at 1

A CLI accepts a user position `1..5`. Write validation before converting it to a `0..4` index. Test `0`, `-1`, `6`, and `Integer.MIN_VALUE` without subtracting 1 before validation.

### Exercise 7 — End-exclusive

Given `List.of("A","B","C")`, predict `subList(1,3)`, `subList(3,3)`, and `subList(2,4)`. **Answer:** `[B,C]`, `[]`, out-of-bounds error.

### Exercise 8 — `Objects.checkIndex`

Run `ObjectsIndexCheckDemo`. Modify the calls to check the range `[2,2)`, `[0,4)`, and `from=3,size=0` with length 3. Which conditions are valid? Why can an empty range at the end be valid while an element at index 3 does not exist?

### Exercise 9 — Effect of mutation

An `ArrayList` has size 4; thread A checks that index 3 is valid, and thread B removes an element before A calls `get(3)`. Explain why the earlier check is insufficient and propose an appropriate ownership/snapshot/lock solution.

### Exercise 10 — Regression test

Write a JUnit 5 test for a method `elementAt(int[], int)`: test an empty array, a negative index, the last index, and an index equal to length. Assert only the exception type and behavior, without relying on message text.

## 23. Pre-completion checklist

- [ ] Can I distinguish the superclass `IndexOutOfBoundsException` from the subclass `ArrayIndexOutOfBoundsException`?
- [ ] Do I know both classes are unchecked `RuntimeException`s, not checked exceptions?
- [ ] For element access, do I always verify `0 <= i && i < length/size`?
- [ ] Do I avoid confusing `length`/`size()` with the last element's index?
- [ ] Do I handle empty arrays before using `arr[0]` or `arr[length-1]`?
- [ ] Do I use `<` instead of `<=` in loops reading `arr[i]`?
- [ ] Do I distinguish an element index from an insertion position that allows `size`?
- [ ] Do I understand that `[from,to)` allows `to == length` and can be empty?
- [ ] Do I know `List.get` by contract throws `IndexOutOfBoundsException`, without depending on a specific runtime subtype?
- [ ] Do I know `String.length` counts UTF-16 code units, not always the number of Unicode code points?
- [ ] For multidimensional arrays, do I use `row.length` for each row rather than assuming all rows have the same length?
- [ ] Do I distinguish bounds errors from `NullPointerException`, `ArrayStoreException`, and `NegativeArraySizeException`?
- [ ] Do I validate user input and convert one-based/zero-based indices properly?
- [ ] Do I consider `Objects.checkIndex`/`checkFromToIndex`/`checkFromIndexSize` when writing range-based APIs?
- [ ] Do I avoid using `try/catch` to hide loop bugs or return false success?
- [ ] Do I place the subtype catch before the superclass catch when both are present?
- [ ] Have I considered concurrency and size changes between check and use?
- [ ] Do I avoid depending on exception messages or stack trace line numbers as a business protocol?
- [ ] Have I tested inputs `-1`, `0`, `n-1`, `n`, empty arrays, and empty ranges?

**Conclusion:** `ArrayIndexOutOfBoundsException` is **a type of `IndexOutOfBoundsException`** specialized for array access. Both are unchecked exceptions. Valid element access uses **`0 <= index < length/size`**; some insertion-position APIs or **`[from,to)`** ranges allow an endpoint equal to `length/size`. Keep loop conditions accurate, understand each API's contract, validate data at boundaries, handle jagged arrays and Unicode with the right index type, and when a bug occurs, fix the invariant rather than just catching and ignoring it.