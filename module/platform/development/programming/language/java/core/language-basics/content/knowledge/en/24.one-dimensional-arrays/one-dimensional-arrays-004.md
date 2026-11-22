# Zero-Based Indexing and the `length` Field — One-Dimensional Arrays in Java 17+

## 1. Goals

In Java, **arrays index elements starting from `0`**, not from `1`. For an array with `n` elements:

- The first element is at `array[0]`, if `n > 0`.
- The last element is at `array[n - 1]`, if `n > 0`.
- Valid indices are integers in the range **`0 <= index && index < array.length`**.
- `array.length` is a **field** holding the number of elements in the array, **not a method**; there are no parentheses `()`.
- If `array.length == 0`, **no valid index exists**.

Example:

~~~java
int[] numbers = {7, 0, -3, 5};
System.out.println(numbers.length); // 4
System.out.println(numbers[0]);      // 7
System.out.println(numbers[3]);      // 5
~~~

This array has four elements, yet the last element has index **3**, not 4.

## 2. Visualizing the index structure

~~~text
int[] numbers = { 7, 0, -3, 5 };

             +----+----+----+----+
Value        |  7 |  0 | -3 |  5 |
             +----+----+----+----+
Index        |  0 |  1 |  2 |  3 |
             +----+----+----+----+

numbers.length = 4
First index    = 0
Last index     = length - 1 = 3
~~~

| Expression | Result | Explanation |
|---|---:|---|
| `numbers.length` | `4` | Array contains four elements |
| `numbers[0]` | `7` | First value |
| `numbers[1]` | `0` | Second value |
| `numbers[2]` | `-3` | Third value |
| `numbers[3]` | `5` | Last value |
| `numbers[-1]` | Runtime error | Negative index |
| `numbers[4]` | Runtime error | Index equal to `length` is invalid |

**Key takeaway:** the number of elements and the last index are two different quantities. For a non-empty array, **`lastIndex = length - 1`**.

## 3. Characteristics of the `length` field

For any array in Java:

~~~java
int[] values = {4, 8};
int size = values.length; // Valid.
~~~

The `length` field is a **`public final int` member of the array type**. Because it is a `final` field, it cannot be reassigned:

~~~java
// values.length = 10; // COMPILE ERROR: cannot assign a value to final field.
// int x = values.length(); // COMPILE ERROR: array has no method length().
~~~

**The length is fixed after array creation.** To get a longer or shorter array, you must create **a new array**, for instance using `Arrays.copyOf`:

~~~java
int[] oldArray = {1, 2, 3};
int[] larger = java.util.Arrays.copyOf(oldArray, 5);
System.out.println(java.util.Arrays.toString(larger));
~~~

**Exact expected stdout:**

~~~text
[1, 2, 3, 0, 0]
~~~

`larger` is a new array of length 5; `oldArray` remains length 3. The `length` field does not mean the number of elements "filled with meaningful data." An array `new int[100]` always has `length == 100`, even if all elements are still the default 0.

## 4. Safe index checking condition

Before using `array[index]` where `index` comes from a user or a calculation, ensure:

~~~java
static boolean validIndex(int[] array, int index) {
    return array != null
            && index >= 0
            && index < array.length;
}
~~~

The order of conditions matters:

1. Check that the array is **non-null** first.
2. Reject negative indices.
3. Reject indices **greater than or equal to `length`**.

The `&&` operator **short-circuits**: if `array == null`, `array.length` is not accessed. Do not check only `index < array.length`, because `index = -1` still satisfies that condition for a non-empty array.

**Example results when the array has length 4:**

| `index` | `index >= 0` | `index < 4` | Valid |
|---:|---|---|---|
| `-1` | false | true | No |
| `0` | true | true | Yes |
| `3` | true | true | Yes |
| `4` | true | false | No |
| `5` | true | false | No |

You can let the runtime throw an exception naturally if an invalid index access is a programming bug; however, for user-supplied indices, validating the input usually produces clearer error reporting.

## 5. Out-of-bounds index error `ArrayIndexOutOfBoundsException`

The following expressions **compile**, yet cause an exception at runtime:

~~~java
int[] numbers = {7, 0, -3, 5};

// System.out.println(numbers[-1]); // ArrayIndexOutOfBoundsException.
// System.out.println(numbers[4]);  // ArrayIndexOutOfBoundsException.
~~~

`ArrayIndexOutOfBoundsException` is a **runtime** exception caused by a negative index or an index greater than or equal to `length`. Java performs bounds checking to protect the array's memory.

Example catching the error for demonstration:

~~~java
try {
    System.out.println(numbers[numbers.length]);
} catch (ArrayIndexOutOfBoundsException ex) {
    System.out.println("index == length is invalid");
}
~~~

**Exact expected stdout:**

~~~text
index == length is invalid
~~~

**Do not use exception catching to replace a properly bounded loop.** In normal code, fix `i <= numbers.length` to `i < numbers.length`; that is clearer and avoids throwing exceptions repeatedly.

## 6. Traversing from start to end with `for`

Common approach:

~~~java
int[] data = {7, 0, -3, 5};
for (int i = 0; i < data.length; i++) {
    System.out.println("index=" + i + ",value=" + data[i]);
}
~~~

**Exact expected stdout:**

~~~text
index=0,value=7
index=1,value=0
index=2,value=-3
index=3,value=5
~~~

Breaking down the three parts:

- **Initialization:** `int i = 0`, starting from the first index.
- **Condition:** `i < data.length`, accessing only while the index remains valid.
- **Update:** `i++`, moving to the next element.

If you use `i <= data.length`, the body runs when `i == 4`; the expression `data[4]` goes out of bounds. This is a classic **off-by-one** error.

### Reverse traversal

~~~java
for (int i = data.length - 1; i >= 0; i--) {
    System.out.println(data[i]);
}
~~~

**Exact expected stdout:**

~~~text
5
-3
0
7
~~~

For an empty array, `data.length - 1` is `-1`, so the condition `i >= 0` is immediately false and the loop body does not execute.

## 7. Empty array: `length == 0`

~~~java
int[] empty = new int[0];
System.out.println(empty.length);
~~~

**Exact expected stdout:**

~~~text
0
~~~

An empty array is a **valid array**, distinct from `null`:

- `empty.length == 0`.
- There is no `empty[0]`; accessing it throws `ArrayIndexOutOfBoundsException`.
- `for (int i = 0; i < empty.length; i++)` performs **0 iterations**.
- `for (int value : empty)` also performs **0 iterations**.
- To read the first or last element, you must check `empty.length > 0` first.

~~~java
if (empty.length == 0) {
    System.out.println("EMPTY");
} else {
    System.out.println(empty[0]);
}
~~~

**Exact expected stdout:**

~~~text
EMPTY
~~~

**Never assume** an array always has at least one element just because a variable is declared as `int[]`.

## 8. `array.length`, `String.length()`, and `List.size()` are different

These three ways of getting size are easily confused:

| Object | Syntax | Nature |
|---|---|---|
| Array `int[]`, `String[]`, `Object[]` | `array.length` | `int` **field** of the array |
| String `String` | `text.length()` | **Method** of String |
| `List` | `list.size()` | **Method** of List |

~~~java
int[] numbers = {1, 2, 3};
String text = "Java";
java.util.List<String> words = java.util.List.of("a", "b");

System.out.println(numbers.length);
System.out.println(text.length());
System.out.println(words.size());
~~~

**Exact expected stdout:**

~~~text
3
4
2
~~~

**Note on `String`:** `String.length()` measures the number of **UTF-16 code units**, not necessarily the number of user-perceived characters. That is a rule of String, **completely different** from counting array elements via `array.length`.

Although the syntax for accessing size differs, when indexing you still need to ensure a lower bound of 0 and an upper bound matching the data structure.

## 9. Self-contained Java 17+ program, runnable via CLI

Create a file named exactly **`ArrayIndexLengthDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.List;

public final class ArrayIndexLengthDemo {
    private ArrayIndexLengthDemo() {}

    static boolean validIndex(int[] array, int index) {
        return array != null && index >= 0 && index < array.length;
    }

    static int sum(int[] array) {
        int total = 0;
        for (int i = 0; i < array.length; i++) {
            total += array[i];
        }
        return total;
    }

    public static void main(String[] args) {
        int[] numbers = {7, 0, -3, 5};

        System.out.println("length=" + numbers.length);
        System.out.println("first=" + numbers[0]);
        System.out.println("last=" + numbers[numbers.length - 1]);

        for (int i = 0; i < numbers.length; i++) {
            System.out.println("index=" + i + ",value=" + numbers[i]);
        }
        System.out.println("sum=" + sum(numbers));

        System.out.println("valid -1=" + validIndex(numbers, -1));
        System.out.println("valid 0=" + validIndex(numbers, 0));
        System.out.println("valid 3=" + validIndex(numbers, 3));
        System.out.println("valid 4=" + validIndex(numbers, 4));
        System.out.println("valid null=" + validIndex(null, 0));

        try {
            System.out.println(numbers[-1]);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("negative index=OUT_OF_BOUNDS");
        }
        try {
            System.out.println(numbers[numbers.length]);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("length index=OUT_OF_BOUNDS");
        }

        int[] zeros = new int[3];
        System.out.println("new array=" + Arrays.toString(zeros));
        int[] larger = Arrays.copyOf(numbers, 6);
        System.out.println("copied length=" + larger.length);
        System.out.println("copied=" + Arrays.toString(larger));
        System.out.println("original length=" + numbers.length);

        int[] empty = new int[0];
        System.out.println("empty length=" + empty.length);
        int emptyVisits = 0;
        for (int i = 0; i < empty.length; i++) {
            emptyVisits++;
        }
        System.out.println("empty visits=" + emptyVisits);

        int[] absent = null;
        System.out.println("null reference=" + (absent == null));

        String text = "Java";
        List<String> words = List.of("A", "B");
        System.out.println("string length()=" + text.length());
        System.out.println("list size()=" + words.size());

        int[][] rows = {{1, 2}, {3}, {}};
        System.out.println("row count=" + rows.length);
        for (int row = 0; row < rows.length; row++) {
            System.out.println("row " + row + " length=" + rows[row].length);
        }

        for (int i = numbers.length - 1; i >= 0; i--) {
            System.out.println("reverse index=" + i + ",value=" + numbers[i]);
        }
    }
}
~~~

**Requirements:** JDK 17 or later, terminal in the directory containing the file. No Maven, Gradle, or preview features used.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 ArrayIndexLengthDemo.java
java -cp . ArrayIndexLengthDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\ArrayIndexLengthDemo.java
java -cp . ArrayIndexLengthDemo
~~~

### Exact expected stdout

~~~text
length=4
first=7
last=5
index=0,value=7
index=1,value=0
index=2,value=-3
index=3,value=5
sum=9
valid -1=false
valid 0=true
valid 3=true
valid 4=false
valid null=false
negative index=OUT_OF_BOUNDS
length index=OUT_OF_BOUNDS
new array=[0, 0, 0]
copied length=6
copied=[7, 0, -3, 5, 0, 0]
original length=4
empty length=0
empty visits=0
null reference=true
string length()=4
list size()=2
row count=3
row 0 length=2
row 1 length=1
row 2 length=0
reverse index=3,value=5
reverse index=2,value=-3
reverse index=1,value=0
reverse index=0,value=7
~~~

**Verification:** the `numbers` array has `length == 4`, yet its last index is 3; the sum is 9. Indices -1 and 4 are invalid; `new int[3]` has three default 0s. `Arrays.copyOf` creates a new array of length 6 while keeping the original array's length unchanged. An empty array has 0 iterations; a `null` reference differs from an empty array. Each row of a two-dimensional array has its own `length`.

## 10. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Thinking indices start at 1 | Skips the first element | Start at `i = 0` |
| Thinking the last index equals `length` | `ArrayIndexOutOfBoundsException` | Last index is `length - 1` when non-empty |
| `i <= array.length` when accessing `array[i]` | Out of bounds at `i == length` | `i < array.length` |
| Checking only `index < length` | Negative indices slip through | Add `index >= 0` |
| Using `array.length()` | Compile error | `array.length` |
| Using `array.length = n` | Error because the field is final | Create a new array |
| Reading `array[0]` when `length == 0` | Out of bounds | Check that the array is non-empty |
| Using `array.length` when `array == null` | `NullPointerException` | Check for null first |
| Equating `length` with the count of non-empty elements | Wrong meaning of length | `length` is the number of allocated slots |
| Confusing `String.length()` with `array.length` | Syntax/type error | Remember array field vs. String method |
| Using `rows.length` as the column count of every row | Wrong for jagged arrays | `rows[row].length` |
| Catching exceptions as a way to traverse an array | Hard-to-read code, exception overhead | Check bounds beforehand |

## 11. Exercises with answers

### Exercise A — Valid indices

Given `int[] a = {3, 6, 9, 12, 15};`, what are `a.length`, the first index, the last index, and `a[4]`?

**Answer:** `length = 5`, first index `0`, last index `4`, `a[4] = 15`. `a[5]` is invalid.

### Exercise B — Fix the off-by-one bug

~~~java
int[] a = {2, 4, 6};
// Wrong: for (int i = 0; i <= a.length; i++) System.out.println(a[i]);
~~~

**Answer:**

~~~java
for (int i = 0; i < a.length; i++) {
    System.out.println(a[i]);
}
~~~

**Expected stdout:**

~~~text
2
4
6
~~~

### Exercise C — Empty array

~~~java
int[] a = {};
System.out.println(a.length);
~~~

**Answer:** prints `0`. `a[0]` cannot be read because the array has no elements.

### Exercise D — Checking negative indices

Why is `if (index < a.length) ...` not sufficient?

**Answer:** when `index = -1` and `a.length = 3`, the condition is still true, yet `a[-1]` is invalid. You need `index >= 0 && index < a.length`.

### Exercise E — Distinguish the three ways to read size

Complete the statements to get the sizes of `int[] a`, `String s`, and `List<String> list`.

**Answer:**

~~~java
int arraySize = a.length;
int stringUnits = s.length();
int listSize = list.size();
~~~

### Exercise F — Create a new longer array

~~~java
int[] a = {1, 2};
int[] b = Arrays.copyOf(a, 4);
System.out.println(Arrays.toString(a));
System.out.println(Arrays.toString(b));
~~~

**Answer:**

~~~text
[1, 2]
[1, 2, 0, 0]
~~~

Array `a` does not grow in length; `b` is a new array.

## 12. Checklist and conclusion

- [ ] Know that `array[0]` is the first element.
- [ ] Remember that valid indices are `0 <= i && i < array.length`.
- [ ] Know that `length - 1` is the last index **only when the array is non-empty**.
- [ ] Distinguish the element count `length` from the value at an index.
- [ ] Use `array.length` as a **field**, without calling `length()`.
- [ ] Know that `length` cannot be changed after array creation; a new array must be created.
- [ ] Traverse with exact bounds using `for (int i=0; i<a.length; i++)`.
- [ ] Distinguish `ArrayIndexOutOfBoundsException` from `NullPointerException`.
- [ ] Know that an empty array has `length == 0` and has no valid indices.
- [ ] Distinguish `array.length`, `String.length()`, and `List.size()`.
- [ ] Run `ArrayIndexLengthDemo.java` with Java 17+, and verify each line of stdout.

**Conclusion:** In a Java array, `length` tells you **how many elements** there are, while indexing starts at **0**. Therefore, the valid upper bound is `length - 1`, not `length`. Use the condition `0 <= index && index < array.length`, handle empty and `null` arrays properly, and remember that `length` is a fixed field of the array.