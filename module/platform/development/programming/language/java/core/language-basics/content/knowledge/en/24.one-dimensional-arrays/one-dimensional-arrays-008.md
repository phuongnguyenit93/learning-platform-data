# `ArrayIndexOutOfBoundsException` and `NegativeArraySizeException` — Java 17+

## 1. Two distinct array errors

When working with one-dimensional arrays in Java, distinguish **element access errors** from **array allocation errors**:

| Exception | When does it occur? | Example |
|---|---|---|
| `ArrayIndexOutOfBoundsException` | Reading/writing an element at an index outside `0..length-1` | `a[-1]`, `a[a.length]` |
| `NegativeArraySizeException` | Allocating an array with a negative size | `new int[-2]` |
| `NullPointerException` (related) | Accessing an array through a `null` reference | `a.length` when `a == null` |

Both main exceptions are **unchecked exceptions** (subclasses of `RuntimeException`), so declaring `throws` or `catch` is not required. They arise **at runtime**; many expressions involving them still compile cleanly.

Standalone example:

~~~java
int[] a = {10, 20, 30};

System.out.println(a.length); // 3
System.out.println(a[0]);     // 10
System.out.println(a[2]);     // 30

// a[3] or a[-1]: invalid index.
// new int[-2]: invalid allocation size.
~~~

**Rule of thumb:** *Array already exists, wrong access position → index out of bounds; creating an array, negative size → negative array size.*

## 2. `ArrayIndexOutOfBoundsException` on read

~~~java
int[] numbers = {4, 8, 12};

// System.out.println(numbers[3]);
// At runtime: ArrayIndexOutOfBoundsException.
~~~

Java checks index bounds on access. Writing `numbers[3]` **passes compilation** because the index is an `int`, yet fails at runtime since the array only has three elements.

Demonstration catching the exception, without relying on JDK error messages:

~~~java
try {
    System.out.println(numbers[3]);
} catch (ArrayIndexOutOfBoundsException ex) {
    System.out.println("READ_OUT_OF_BOUNDS");
}
~~~

**Exact stdout:**

~~~text
READ_OUT_OF_BOUNDS
~~~

The message `ex.getMessage()` can depend on JDK version and context; the example uses a controlled message to ensure exact expected output.

## 3. `ArrayIndexOutOfBoundsException` on write

Not only reading, **writing** to an invalid index also goes out of bounds:

~~~java
int[] numbers = {4, 8, 12};

try {
    numbers[-1] = 99;
} catch (ArrayIndexOutOfBoundsException ex) {
    System.out.println("WRITE_OUT_OF_BOUNDS");
}
~~~

**Exact stdout:**

~~~text
WRITE_OUT_OF_BOUNDS
~~~

Assignment does not create a new slot. Java arrays have a **fixed length**: `numbers[numbers.length] = 99` does not mean "append an element to the end."

To add elements, create a new array of the appropriate size (e.g., `Arrays.copyOf`) or choose `ArrayList` if your domain needs a dynamically sized list.

## 4. `NegativeArraySizeException` when creating an array

When allocating with `new`, the size expression must be a **non-negative** integer:

~~~java
int[] empty = new int[0]; // Valid: length = 0.
int[] data = new int[3];  // Valid: length = 3.

// int[] bad = new int[-2]; // Compiles, throws NegativeArraySizeException at runtime.
~~~

Demonstration:

~~~java
try {
    int requestedLength = -2;
    int[] bad = new int[requestedLength];
    System.out.println(bad.length);
} catch (NegativeArraySizeException ex) {
    System.out.println("NEGATIVE_ARRAY_SIZE");
}
~~~

**Exact stdout:**

~~~text
NEGATIVE_ARRAY_SIZE
~~~

This is an error in the **size parameter during allocation**, not an index reading error. An array of length 0 is allowed to be created; a negative index is **never** valid when accessing.

## 5. Checking before array allocation

An API accepting a size from outside should decide its policy for negative input:

~~~java
static int[] createChecked(int size) {
    if (size < 0) {
        throw new IllegalArgumentException("size must be >= 0");
    }
    return new int[size];
}
~~~

Advantage: instead of letting `NegativeArraySizeException` arise from the allocation site, the API states the input requirement clearly via `IllegalArgumentException`. This is an **API design decision**, not a mandatory rule to convert every error to `IllegalArgumentException`.

Example:

~~~java
System.out.println(createChecked(0).length); // 0
System.out.println(createChecked(3).length); // 3
~~~

When calling `createChecked(-1)`, the method throws `IllegalArgumentException` with the defined message.

**Important:** a non-negative size does not guarantee allocation will succeed. Requesting an overly large array can lead to `OutOfMemoryError`; that is a different issue, not `NegativeArraySizeException`. Do not test allocating huge arrays just to experiment on a learning machine.

Once you have identified the two error sites, input validation is a common way to prevent errors:

## 6. Checking bounds before reading/writing

A reader method returning a label instead of making an invalid access:

~~~java
static String readSafely(int[] array, int index) {
    if (array == null) {
        return "NULL_ARRAY";
    }
    if (index < 0 || index >= array.length) {
        return "BAD_INDEX";
    }
    return "VALUE:" + array[index];
}
~~~

For the array `{10, 20, 30}`:

| Operation | Return value |
|---|---|
| `readSafely(a, -1)` | `BAD_INDEX` |
| `readSafely(a, 0)` | `VALUE:10` |
| `readSafely(a, 2)` | `VALUE:30` |
| `readSafely(a, 3)` | `BAD_INDEX` |
| `readSafely(null, 0)` | `NULL_ARRAY` |

In a real application, you can return `OptionalInt`, a structured domain result, or throw `IllegalArgumentException` depending on the API contract. Strings in this example are solely for observing flow easily.

**Not sufficient:** `index < array.length`, because `-1 < length` is still true for a non-empty array. You need both the **lower bound** `index >= 0` and the **upper bound** `index < length`.

## 7. The two exceptions occur at two different steps

~~~mermaid
flowchart TD
    A["Array operation"] --> B{"Creating a new array?"}
    B -- "Yes" --> C{"size < 0?"}
    C -- "Yes" --> D["NegativeArraySizeException"]
    C -- "No" --> E["Create array; sufficient memory required"]
    B -- "No, reading/writing" --> F{"array == null?"}
    F -- "Yes" --> G["NullPointerException"]
    F -- "No" --> H{"index < 0 or index >= length?"}
    H -- "Yes" --> I["ArrayIndexOutOfBoundsException"]
    H -- "No" --> J["Valid access"]
~~~

The diagram assumes allocating and reading/writing a one-dimensional array with integer size/index values. It only clarifies **common error types**, and does not represent every possible allocation failure or expressions with side effects.

Debugging rule: if the message contains `NegativeArraySizeException`, inspect the size expression at `new T[size]`; if it contains `ArrayIndexOutOfBoundsException`, inspect the array length and index at the `array[index]` access.

## 8. Standalone, runnable Java 17+ program

Create the exact file **`ArrayExceptionsDemo.java`**:

~~~java
import java.util.Arrays;

public final class ArrayExceptionsDemo {
    private ArrayExceptionsDemo() {}

    static boolean validIndex(int[] array, int index) {
        return array != null && index >= 0 && index < array.length;
    }

    static String readSafely(int[] array, int index) {
        if (array == null) return "NULL_ARRAY";
        if (index < 0 || index >= array.length) return "BAD_INDEX";
        return "VALUE:" + array[index];
    }

    static int[] createChecked(int size) {
        if (size < 0) {
            throw new IllegalArgumentException("size must be >= 0");
        }
        return new int[size];
    }

    static int sum(int[] array) {
        int total = 0;
        for (int i = 0; i < array.length; i++) {
            total += array[i];
        }
        return total;
    }

    public static void main(String[] args) {
        int[] values = {10, 20, 30};

        System.out.println("length=" + values.length);
        System.out.println("first=" + values[0]);
        System.out.println("last=" + values[values.length - 1]);
        System.out.println("sum=" + sum(values));

        System.out.println("valid -1=" + validIndex(values, -1));
        System.out.println("valid 0=" + validIndex(values, 0));
        System.out.println("valid 2=" + validIndex(values, 2));
        System.out.println("valid 3=" + validIndex(values, 3));
        System.out.println("valid null=" + validIndex(null, 0));

        System.out.println("safe -1=" + readSafely(values, -1));
        System.out.println("safe 0=" + readSafely(values, 0));
        System.out.println("safe 2=" + readSafely(values, 2));
        System.out.println("safe 3=" + readSafely(values, 3));
        System.out.println("safe null=" + readSafely(null, 0));

        try {
            System.out.println(values[-1]);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("read -1=ArrayIndexOutOfBoundsException");
        }

        try {
            values[values.length] = 99;
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("write length=ArrayIndexOutOfBoundsException");
        }

        try {
            int requestedLength = -2;
            int[] bad = new int[requestedLength];
            System.out.println(bad.length);
        } catch (NegativeArraySizeException ex) {
            System.out.println("size -2=NegativeArraySizeException");
        }

        int[] empty = new int[0];
        System.out.println("empty length=" + empty.length);
        try {
            System.out.println(empty[0]);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("empty[0]=ArrayIndexOutOfBoundsException");
        }

        int[] missing = null;
        try {
            System.out.println(missing.length);
        } catch (NullPointerException ex) {
            System.out.println("null.length=NullPointerException");
        }

        System.out.println("checked size 0=" + createChecked(0).length);
        System.out.println("checked size 3=" + createChecked(3).length);
        try {
            createChecked(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("guard -1=" + ex.getMessage());
        }

        int[] extended = Arrays.copyOf(values, 5);
        System.out.println("original=" + Arrays.toString(values));
        System.out.println("extended=" + Arrays.toString(extended));

        for (int i = values.length - 1; i >= 0; i--) {
            System.out.println("reverse=" + values[i]);
        }
    }
}
~~~

**Requirements:** JDK 17 or later, terminal in the directory containing the file. The program does not require libraries outside the JDK, Maven, Gradle, or preview features.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 ArrayExceptionsDemo.java
java -cp . ArrayExceptionsDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\ArrayExceptionsDemo.java
java -cp . ArrayExceptionsDemo
~~~

### Exact expected stdout

~~~text
length=3
first=10
last=30
sum=60
valid -1=false
valid 0=true
valid 2=true
valid 3=false
valid null=false
safe -1=BAD_INDEX
safe 0=VALUE:10
safe 2=VALUE:30
safe 3=BAD_INDEX
safe null=NULL_ARRAY
read -1=ArrayIndexOutOfBoundsException
write length=ArrayIndexOutOfBoundsException
size -2=NegativeArraySizeException
empty length=0
empty[0]=ArrayIndexOutOfBoundsException
null.length=NullPointerException
checked size 0=0
checked size 3=3
guard -1=size must be >= 0
original=[10, 20, 30]
extended=[10, 20, 30, 0, 0]
reverse=30
reverse=20
reverse=10
~~~

**Quick explanation:**

1. `values.length = 3`; indices 0 and 2 are valid, while -1 and 3 are invalid.
2. `readSafely` detects null or out-of-bounds indices before reading the array.
3. The two cases—reading -1 and writing at index equal to `length`—throw `ArrayIndexOutOfBoundsException`.
4. `new int[-2]` throws `NegativeArraySizeException`; `new int[0]` is valid, yet `empty[0]` is still out of bounds.
5. `missing.length` throws `NullPointerException`, not an index error.
6. `createChecked` turns negative input into `IllegalArgumentException` per the API contract.
7. `Arrays.copyOf` creates a new array of length 5 while leaving the original array at length 3.

## 9. Common mistakes and fixes

| Mistake | Consequence | Correct approach |
|---|---|---|
| `a[a.length]` to read the last element | `ArrayIndexOutOfBoundsException` | `a[a.length - 1]` when non-empty |
| Using `i <= a.length` to traverse | Out of bounds at `i == length` | `i < a.length` |
| Checking only `i < a.length` | Negative indices slip through | `0 <= i && i < a.length` |
| Creating `new int[-1]` | `NegativeArraySizeException` | Check `size >= 0` |
| Thinking `new int[0]` is an error | Misunderstands allocation condition | Empty arrays are valid |
| Reading `a[0]` when `length == 0` | Out of bounds | Check `length > 0` |
| Using `a.length` when `a == null` | `NullPointerException` | Check for null first |
| Assigning `a[a.length] = item` to add an element | Out of bounds; fixed length | Create a new array or use an appropriate List |
| Mixing both exceptions in one `catch` and guessing the cause | Harder diagnostics | Identify whether it is an allocation or access error |
| Relying on an exception's `getMessage()` as exact stdout | Can differ across environments/JDKs | Print a stable code-defined message |
| Catching `RuntimeException` around an entire algorithm to hide all errors | Can hide real bugs | Fix bounds/sizes at the root cause |
| Using a non-negative size that is too large | Can run out of memory | Constrain input sizes per requirements |

**Do not use `try/catch` to replace a properly bounded traversal algorithm.** In the example, catching only helps show the exception type clearly; prevention means validating before reading, writing, or allocating.

## 10. Exercises with answers

### A — Do these two expressions cause the same type of error?

~~~java
int[] a = {1, 2};
// a[2];
// new int[-2];
~~~

**Answer:** No. `a[2]` causes `ArrayIndexOutOfBoundsException` because the array has length 2, whereas `new int[-2]` causes `NegativeArraySizeException`.

### B — Empty array

~~~java
int[] a = new int[0];
System.out.println(a.length);
~~~

**Answer:** prints `0`. If you proceed to access `a[0]`, the runtime throws `ArrayIndexOutOfBoundsException`.

### C — Fix the broken `for` loop

~~~java
int[] a = {2, 4, 6};
// for (int i = 0; i <= a.length; i++) {
//     System.out.println(a[i]);
// }
~~~

**Answer:**

~~~java
for (int i = 0; i < a.length; i++) {
    System.out.println(a[i]);
}
~~~

**Exact stdout:**

~~~text
2
4
6
~~~

### D — Null and bounds check

Write a method indicating whether `index` is valid for `int[] a`.

**Answer:**

~~~java
static boolean isValid(int[] a, int index) {
    return a != null && index >= 0 && index < a.length;
}
~~~

Does not read `a.length` when `a == null` and does not miss negative indices.

### E — Negative size policy

Reject a negative size with an exception having a clear message.

**Answer:**

~~~java
static int[] allocate(int requested) {
    if (requested < 0) {
        throw new IllegalArgumentException("negative size");
    }
    return new int[requested];
}
~~~

The case `requested = 0` remains valid, whereas `-1` produces `IllegalArgumentException` per the API policy.

## 11. Checklist and conclusion

- [ ] Know that `ArrayIndexOutOfBoundsException` occurs when reading **or writing** at an invalid index.
- [ ] Remember the index range `0 <= index < array.length`.
- [ ] Know that `NegativeArraySizeException` occurs when creating an array with a negative size.
- [ ] Understand that `new int[0]` is valid, whereas `empty[0]` is invalid.
- [ ] Do not confuse `null` with an empty array; `null.length` causes `NullPointerException`.
- [ ] Use the loop condition `i < array.length` instead of `i <= array.length`.
- [ ] Validate non-negative sizes at API boundaries if clear error reporting is needed.
- [ ] Do not assume a non-negative size always has enough memory to allocate.
- [ ] Distinguish array allocation time from element access time.
- [ ] Do not rely on default exception messages to produce reproducible stdout.
- [ ] Run `ArrayExceptionsDemo.java` on JDK 17+, compare exact stdout, and verify boundaries `-1`, `0`, `length-1`, and `length`.

**Conclusion:** `ArrayIndexOutOfBoundsException` reports an invalid **access position** in an already created array; `NegativeArraySizeException` reports a **negative size during allocation**. Both can be avoided in normal flow by validating inputs properly, always looping within `0 <= i < length`, and explicitly handling both empty and null array cases.