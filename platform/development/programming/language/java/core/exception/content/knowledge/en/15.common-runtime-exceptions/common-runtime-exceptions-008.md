# `NegativeArraySizeException` in Java: Creating an Array with a Negative Size

`NegativeArraySizeException` is an **unchecked** exception in Java, thrown when a program attempts to create an array with **at least one negative dimension size**. This exception is distinct from array index out-of-bounds errors, `null` access errors, out-of-memory errors, and invalid input errors in other collections. Understanding it properly helps you track down invalid length data, integer overflow in calculations, or invalid multi-dimensional array allocations.

Minimal example:

~~~java
int requestedSize = -3;
int[] numbers = new int[requestedSize]; // Throws NegativeArraySizeException at runtime.
~~~

In the example above, `new int[-3]` **compiles successfully**; the error occurs when the statement is executed. The number `-3` is not an element value, but the requested length of the array.

If the length is `0`:

~~~java
int[] empty = new int[0];
System.out.println(empty.length); // 0
~~~

this is a **completely valid** empty array. The error condition is **less than 0**, not less than or equal to 0.

This lesson targets Java 17+ and covers: array creation mechanics, one-dimensional and multi-dimensional arrays, evaluation order of dimension expressions, distinguishing related exceptions, reflection cases, integer overflow, safe validation, error handling, and runnable Java examples with verified output.

## 1. Where Does `NegativeArraySizeException` Sit in the Exception Hierarchy?

~~~text
java.lang.Object
    └── java.lang.Throwable
        └── java.lang.Exception
            └── java.lang.RuntimeException
                └── java.lang.NegativeArraySizeException
~~~

Because it extends `RuntimeException`, `NegativeArraySizeException` is an **unchecked exception**: the compiler does not require a method that may throw it to declare `throws NegativeArraySizeException`, and does not require the caller to `catch` it.

Key characteristics:

| Property | Value / Meaning |
| --- | --- |
| Full name | `java.lang.NegativeArraySizeException` |
| Direct superclass | `java.lang.RuntimeException` |
| Checked or unchecked? | Unchecked |
| When does it occur? | Requesting array creation with a negative integer size |
| Direct examples | `new int[-1]`, `new String[-5]` |
| Creating an empty array | `new int[0]` is valid |
| Is `throws` required? | No |
| How to prevent | Validate input data, valid ranges, integer overflow, and allocation limits |

`NegativeArraySizeException` has a no-argument constructor and a constructor accepting a `String`, like many `RuntimeException` subclasses. When Java throws it automatically, the content of `getMessage()` is **not a stable contract for programmatic parsing**; rely on the exception type and the original length data instead.

You should not proactively use `NegativeArraySizeException` to represent every negative numeric value in business logic. It is tied to **array creation operations**. For example, a negative order quantity in an API contract is usually better suited to `IllegalArgumentException` or a more specific domain exception.

## 2. Arrays in Java Require a Non-Negative Size

An array creation expression uses the syntax:

~~~java
int[] a = new int[3];
String[] names = new String[2];
double[] none = new double[0];
~~~

These examples create three, two, and zero elements respectively. Initial element values are assigned default values based on their type, such as `0` for `int` and `null` for `String` references.

A Java array's length is a non-negative `int` value, readable via the `length` field. Once created, **the length of that array instance cannot change**; you can modify its elements, but you cannot directly increase `array.length`.

~~~java
int[] scores = new int[2];
System.out.println(scores.length); // 2
scores[0] = 10;
scores[1] = 20;

// Invalid: array.length is a read-only field.
// scores.length = 5;
~~~

The syntax `new int[-1]` passes syntax and type checking; the length expression still has type `int`. When **runtime evaluation** encounters a negative size, Java throws `NegativeArraySizeException` and does not return the requested array.

Key takeaway: **the size is computed by an expression**, not necessarily a literal. Negative values often originate from configuration data, an element count after subtraction, or an integer arithmetic result.

## 3. A Negative Value as Size vs. as an Element

Compare these three examples:

~~~java
int[] a = new int[-3];   // Throws NegativeArraySizeException at runtime.
int[] b = {-3};          // Valid: one element with value -3.
int[] c = new int[0];    // Valid: empty array.
~~~

- `a` requests **length -3**: the array cannot be created.
- `b` has **length 1**, and its first element holds a negative value.
- `c` has **length 0**; the array exists, though it has no valid element indices.

Do not assume that merely having a negative number in your data causes Java to throw `NegativeArraySizeException`. An array of negative integers is completely normal:

~~~java
int[] temperatures = {-5, -2, 0, 7};
System.out.println(temperatures.length); // 4
System.out.println(temperatures[0]);     // -5
~~~

What you need to inspect is **the expression inside `[...]` of the array creation operation**, such as `new int[size]`, rather than values inside an array initializer `{...}`.

## 4. Java 17+: Basic Program Testing Negative, Zero, and Positive Sizes

Save the file `NegativeArraySizeDemo.java`:

~~~java
public class NegativeArraySizeDemo {
    static void allocate(int size) {
        try {
            int[] numbers = new int[size];
            System.out.println("size=" + size + ", length=" + numbers.length);
        } catch (NegativeArraySizeException ex) {
            System.out.println("size=" + size + ", caught=" + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        allocate(-3);
        allocate(0);
        allocate(2);

        int[] values = {-3};
        System.out.println("Phần tử âm: " + values[0]);

        int[] empty = new int[0];
        System.out.println("Mảng rỗng: " + empty.length);
    }
}
~~~

Run:

~~~bash
javac --release 17 -encoding UTF-8 NegativeArraySizeDemo.java
java NegativeArraySizeDemo
~~~

Exact stdout:

~~~text
size=-3, caught=NegativeArraySizeException
size=0, length=0
size=2, length=2
Phần tử âm: -3
Mảng rỗng: 0
~~~

### Analysis

1. `allocate(-3)` evaluates the length expression to `-3`; Java throws `NegativeArraySizeException` directly at the array creation expression.
2. The `catch` block catches the exception. The program does not print `numbers.length` on the failure path, because no array was successfully created.
3. `allocate(0)` creates an empty array and prints `length=0`.
4. `allocate(2)` creates a two-element array.
5. `int[] values = {-3}` only contains a negative element, not a negative size.
6. `new int[0]` still returns a valid array object.

In a real system, you should investigate **where the `size` value comes from**, rather than just writing `catch (NegativeArraySizeException)` and continuing by returning an empty array. Silently treating a negative length request as "no data" often hides data bugs or calculation errors.

## 5. When Does the Exception Occur: Compile Time or Runtime?

Java allows writing the expression:

~~~java
int[] numbers = new int[-1];
~~~

Even though `-1` is an obviously negative constant, this array creation syntax still **compiles validly** under Java 17. When the creation expression is executed, the JVM throws `NegativeArraySizeException`.

This is not a type error (`type mismatch`) or a syntax error. The expression `-1` has type `int`, which satisfies the type requirement for a dimension expression. The invalid value is detected at runtime during array creation.

Contrast this with a compile-time error:

~~~java
// INTENTIONALLY INVALID: requires an appropriate integer type for the array dimension.
int[] bad = new int[3.5];
~~~

Here, `3.5` has type `double` and cannot be used directly as a valid array dimension. The compiler rejects it due to a **type mismatch**, not a negative size.

An expression of type `long` also cannot be used directly as `new int[someLong]` without an appropriate type conversion. Casting `long` to `int` can lose data, so only cast after validating the value range.

## 6. Multi-Dimensional Arrays: Any Negative Dimension Is an Error

Java supports creating multi-dimensional arrays with the syntax:

~~~java
int[][] matrix = new int[2][3];
~~~

In this example, Java creates an outer array of two elements, each holding a reference to an `int` array of length three. Java uses **arrays of arrays**, and does not require every dimension to have the same length when you reassign individual rows.

Cases that cause errors:

~~~java
int[][] a = new int[-1][3]; // Error: outer dimension is negative.
int[][] b = new int[2][-3]; // Error: inner dimension is negative.
int[][] c = new int[0][-1]; // Error: inner dimension is negative even though outer dimension is 0.
~~~

The third case can be surprising. You cannot assume that a first dimension of `0` causes Java to skip checking the remaining dimensions. **Every dimension expression written in an array creation expression is evaluated and checked according to array creation semantics.**

Conversely:

~~~java
int[][] rows = new int[2][];
System.out.println(rows.length);  // 2
System.out.println(rows[0]);      // null
~~~

This syntax is valid. Only the first dimension is allocated at that time; the two elements in the outer array are initially `null`, and each sub-array can be created/assigned later. This is the basis for **jagged arrays**.

~~~java
rows[0] = new int[2];
rows[1] = new int[5];
System.out.println(rows[0].length); // 2
System.out.println(rows[1].length); // 5
~~~

If you use `rows[0]` before assigning a sub-array, the error will be `NullPointerException`, not `NegativeArraySizeException`.

## 7. Evaluation Order of Dimension Expressions: An Important Detail

Given the expression:

~~~java
int[][] array = new int[first()][second()];
~~~

Java **evaluates dimension expressions from left to right**, before checking for negative sizes and allocating according to array creation semantics. Therefore, a **side effect** in `second()` can still occur even if `first()` returns a negative number.

If `second()` **throws an exception itself**, the exception from `second()` occurs before the negative-size check; `NegativeArraySizeException` for the negative value from `first()` will not be thrown during that evaluation.

This does not mean the negative value became valid. It means **expression evaluation terminated abruptly before reaching the value-checking step**.

Diagram:

~~~text
Evaluate first()
    ↓
If first() throws → stop, propagate first()'s exception
    ↓ if it returns normally
Evaluate second()
    ↓
If second() throws → stop, propagate second()'s exception
    ↓ if it returns normally
Check the evaluated dimension values
    ↓
If any value is negative → NegativeArraySizeException
    ↓ if all are non-negative
Allocate the corresponding arrays
~~~

You should not rely on side effects in dimension expressions to drive business logic. A more readable and testable approach is to compute the length variables, validate them, and then create the array.

## 8. Java 17+: Verifying Evaluation Order and Multi-Dimensional Arrays

File `DimensionEvaluationDemo.java`:

~~~java
public class DimensionEvaluationDemo {
    static int first() {
        System.out.println("Đánh giá chiều 1");
        return -1;
    }

    static int second() {
        System.out.println("Đánh giá chiều 2");
        return 2;
    }

    static int fails() {
        System.out.println("Chiều 2 ném lỗi");
        throw new IllegalStateException("lỗi biểu thức");
    }

    public static void main(String[] args) {
        try {
            int[][] numbers = new int[first()][second()];
            System.out.println(numbers.length);
        } catch (NegativeArraySizeException ex) {
            System.out.println("Bắt kích thước âm");
        }

        try {
            int[][] numbers = new int[first()][fails()];
            System.out.println(numbers.length);
        } catch (IllegalStateException ex) {
            System.out.println("Bắt lỗi biểu thức: " + ex.getMessage());
        }

        try {
            int[][] numbers = new int[0][-2];
            System.out.println(numbers.length);
        } catch (NegativeArraySizeException ex) {
            System.out.println("Chiều sau âm dù chiều đầu bằng 0");
        }

        int[][] rows = new int[2][];
        System.out.println("Mảng ngoài: " + rows.length
                + ", hàng đầu null: " + (rows[0] == null));
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 -encoding UTF-8 DimensionEvaluationDemo.java
java DimensionEvaluationDemo
~~~

Exact stdout:

~~~text
Đánh giá chiều 1
Đánh giá chiều 2
Bắt kích thước âm
Đánh giá chiều 1
Chiều 2 ném lỗi
Bắt lỗi biểu thức: lỗi biểu thức
Chiều sau âm dù chiều đầu bằng 0
Mảng ngoài: 2, hàng đầu null: true
~~~

**Proven conclusions:**

- The first path evaluates both `first()` and `second()`; even though `first()` returns `-1`, `second()` is still called, and then Java throws `NegativeArraySizeException`.
- The second path evaluates `first()`, then `fails()` throws `IllegalStateException`. It never reaches the negative-size check.
- `new int[0][-2]` fails because the second dimension size is negative.
- `new int[2][]` is valid, but does not create the sub-arrays yet.

If you write more dimensions, the same rule applies to all specified dimension expressions. Do not confuse dimensions **without a specified size** (trailing empty `[]`) with a dimension specified as `0`.

## 9. How `NegativeArraySizeException` Differs from `ArrayIndexOutOfBoundsException`

Both errors can involve arrays, but they occur at **two different stages**:

| Error | When? | Example |
| --- | --- | --- |
| `NegativeArraySizeException` | **Creating an array** with a negative dimension expression | `new int[-1]` |
| `ArrayIndexOutOfBoundsException` | **Accessing an existing array** with an index outside `[0, length)` | `new int[2]` then reading `a[2]` |
| `NullPointerException` | Using an array reference that is `null` | `int[] a = null; a[0]` |

These examples are illustrative snippets, not standalone programs. `NegativeArraySizeException` extends `RuntimeException` directly, whereas `ArrayIndexOutOfBoundsException` extends `IndexOutOfBoundsException`; therefore, `catch (IndexOutOfBoundsException)` **does not catch negative-size errors**. Index-access errors and `[from, to)` bounds rules are covered in the bounds lesson; here, you need to trace back **the value computed for the size at array creation time**, including possible `int` overflow.

## 10. Reflection: `Array.newInstance` Can Also Throw This Exception

Java supports creating arrays via reflection:

~~~java
Object array = java.lang.reflect.Array.newInstance(String.class, 3);
~~~

When using `Array.newInstance(componentType, length)`, if `length` is negative, the API can also throw `NegativeArraySizeException`. With the multi-dimensional overload taking an array of dimensions, any negative dimension is also an error.

This is useful in frameworks, serializers, dynamic table libraries, or code where the component type is only known at runtime. **It is not only the `new T[n]` syntax that can encounter negative-size errors.**

However, you must read the contract of the specific API. For example, an `ArrayList` is not a Java array at runtime; the constructor `new ArrayList<>(-1)` uses a capacity parameter rule and throws **`IllegalArgumentException`**, not `NegativeArraySizeException`.

## 11. Java 17+: Reflection, `ArrayList`, and Index Errors

File `ReflectionAndIndexDemo.java`:

~~~java
import java.lang.reflect.Array;
import java.util.ArrayList;

public class ReflectionAndIndexDemo {
    public static void main(String[] args) {
        try {
            Array.newInstance(String.class, -5);
        } catch (NegativeArraySizeException ex) {
            System.out.println("Reflection: " + ex.getClass().getSimpleName());
        }

        try {
            Array.newInstance(int.class, 2, -3);
        } catch (NegativeArraySizeException ex) {
            System.out.println("Reflection nhiều chiều: "
                    + ex.getClass().getSimpleName());
        }

        try {
            new ArrayList<String>(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("ArrayList capacity: " + ex.getClass().getSimpleName());
        }

        int[] numbers = new int[2];
        try {
            System.out.println(numbers[-1]);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("Index: " + ex.getClass().getSimpleName());
        }
    }
}
~~~

Run:

~~~bash
javac --release 17 -encoding UTF-8 ReflectionAndIndexDemo.java
java ReflectionAndIndexDemo
~~~

Exact stdout:

~~~text
Reflection: NegativeArraySizeException
Reflection nhiều chiều: NegativeArraySizeException
ArrayList capacity: IllegalArgumentException
Index: ArrayIndexOutOfBoundsException
~~~

This shows that **you cannot guess the exception type just by seeing a negative argument**. You must know the specific operation:

- Creating a Java array with a negative size → `NegativeArraySizeException`.
- Creating an `ArrayList` with a negative capacity → `IllegalArgumentException` per the `ArrayList(int)` constructor contract.
- Accessing an array element with a negative index → `ArrayIndexOutOfBoundsException`.

`NegativeArraySizeException` arises from array allocation operations, not as a general error type for all collections.

## 12. Common Sources: Incorrectly Computed Lengths

In production code, few people intentionally write `new int[-1]`. The error usually happens when a **size expression** unexpectedly evaluates to a negative value.

### 12.1. Off-by-One or Reversed Subtraction

~~~java
int remaining = endExclusive - startInclusive;
int[] data = new int[remaining];
~~~

If `endExclusive < startInclusive`, `remaining` is negative. You need to define the contract for the index pair:

- Is an empty range (`startInclusive == endExclusive`) allowed?
- Is `startInclusive > endExclusive` allowed?
- Are both values within the bounds of the data source?
- Does the subtraction risk **`int` overflow**?

Simply writing `Math.max(0, remaining)` is not always the right fix. If the index pair was reversed due to a bug, clamping the length to 0 will **hide the bug and alter semantics**.

### 12.2. Sentinel Value `-1`

Many APIs use `-1` as a special value, such as "not found", "unknown", or "EOF" depending on the contract. If you pass that value directly into `new byte[count]`, you are treating a **status code as an array size**.

~~~java
int count = -1; // Illustrates an "unknown" sentinel.
byte[] payload = new byte[count]; // Wrong if the sentinel state is not handled first.
~~~

You must handle `-1` according to the source API's meaning **before** using it as a length. Do not automatically treat `-1` as an empty array.

### 12.3. Values from Configuration or User Input

~~~java
int configuredSize = Integer.parseInt(input);
byte[] buffer = new byte[configuredSize];
~~~

In this illustrative snippet, `input` is a variable in the enclosing scope. There are two different failure paths:

- If the string cannot be parsed as an integer → `NumberFormatException` may occur.
- If the string parses to `-7` → `new byte[-7]` may throw `NegativeArraySizeException`.

If the configured size is too large even when positive, allocation can still run into memory issues. Therefore, validation must include **both lower and upper bounds**, not just `>= 0`.

### 12.4. Size Derived from Multiplication

~~~java
int totalCells = rows * columns;
int[] matrix = new int[totalCells];
~~~

Both `rows` and `columns` can be positive, yet `int` multiplication overflows, producing a negative value or an incorrect positive number. Thus, checking `totalCells >= 0` **after multiplying** is not enough to guarantee the calculation is correct.

## 13. Integer Overflow: Negative Values Do Not Always Come from Negative Inputs

Java `int` values range from `-2_147_483_648` to `2_147_483_647`. Standard integer arithmetic can overflow, and Java does not automatically throw `ArithmeticException` on overflowing addition or multiplication.

Example:

~~~java
int max = Integer.MAX_VALUE;
int overflowed = max + 1;
System.out.println(overflowed); // -2147483648
byte[] data = new byte[overflowed]; // NegativeArraySizeException.
~~~

Both inputs can be non-negative, yet the intermediate result becomes negative due to overflow.

Use overflow-checking methods where appropriate:

~~~java
int safeSum = Math.addExact(a, b);
int safeProduct = Math.multiplyExact(a, b);
int narrowed = Math.toIntExact(longLength);
~~~

This is an **illustrative snippet**; the variables `a`, `b`, and `longLength` must be declared. These methods throw `ArithmeticException` when the calculation or narrowing conversion cannot be represented exactly in the target type. They **do not allocate memory** and do not automatically validate business limits; you still need to check for a reasonable maximum length.

For counts computed from two indices, using `long` for the intermediate step can help avoid `int` overflow:

~~~java
long length = (long) endExclusive - startInclusive;
if (length < 0 || length > MAX_ALLOWED) {
    throw new IllegalArgumentException("Khoảng dữ liệu không hợp lệ");
}
int[] data = new int[Math.toIntExact(length)];
~~~

This is an **illustrative snippet inside a method** where `endExclusive`, `startInclusive`, and `MAX_ALLOWED` are properly declared. This approach clearly separates **range validation** from **allocation**.

## 14. Java 17+: Overflow and Size Validation Before Array Creation

File `LengthOverflowDemo.java`:

~~~java
public class LengthOverflowDemo {
    static int validatedLength(long length) {
        if (length < 0 || length > 1_000_000) {
            throw new IllegalArgumentException("độ dài ngoài miền cho phép");
        }
        return Math.toIntExact(length);
    }

    public static void main(String[] args) {
        int max = Integer.MAX_VALUE;
        int overflowed = max + 1;
        System.out.println("Sau tràn số: " + overflowed);
        try {
            byte[] bytes = new byte[overflowed];
            System.out.println(bytes.length);
        } catch (NegativeArraySizeException ex) {
            System.out.println("Cấp phát: NegativeArraySizeException");
        }

        try {
            Math.addExact(max, 1);
        } catch (ArithmeticException ex) {
            System.out.println("addExact: ArithmeticException");
        }

        for (long candidate : new long[] {-2, 0, 2, 2_147_483_648L}) {
            try {
                byte[] data = new byte[validatedLength(candidate)];
                System.out.println("candidate=" + candidate + ", length=" + data.length);
            } catch (IllegalArgumentException ex) {
                System.out.println("candidate=" + candidate + ", invalid");
            }
        }
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 -encoding UTF-8 LengthOverflowDemo.java
java LengthOverflowDemo
~~~

Exact stdout:

~~~text
Sau tràn số: -2147483648
Cấp phát: NegativeArraySizeException
addExact: ArithmeticException
candidate=-2, invalid
candidate=0, length=0
candidate=2, length=2
candidate=2147483648, invalid
~~~

Explanation:

1. `Integer.MAX_VALUE + 1` overflows to `Integer.MIN_VALUE`, which is `-2147483648`.
2. Using that value as an array size throws `NegativeArraySizeException`.
3. `Math.addExact(max, 1)` **detects the overflow** and throws `ArithmeticException`, allowing the error to be caught at the **arithmetic operation** before reaching allocation.
4. `validatedLength` rejects negative numbers and numbers exceeding the **example's** limit (1,000,000), then uses `Math.toIntExact`.
5. `0` and `2` are valid, creating arrays of the corresponding lengths.
6. `2_147_483_648L` exceeds the `int` range and the application's limit; the validation method throws `IllegalArgumentException` instead of allowing a lossy cast.

The 1,000,000 limit in the example is **not a fixed limit for all Java arrays**; it is an intentional size policy. A program should choose a threshold based on its requirements and memory budget.

## 15. Large Positive Sizes Can Encounter Other Errors

`NegativeArraySizeException` only indicates that **a negative size** was used. You cannot conclude that a positive size is guaranteed to allocate successfully.

Example:

~~~java
// DO NOT run arbitrarily: this may request a very large amount of memory.
// byte[] huge = new byte[Integer.MAX_VALUE];
~~~

The outcome depends on the JVM's allocation capacity, heap memory, array size limits, and runtime environment. With excessively large requests, `OutOfMemoryError` or a message related to array size limits may occur. **`OutOfMemoryError` is a subclass of `Error`, not `NegativeArraySizeException`.**

Do not write production tests that attempt to allocate huge arrays just to "see what error happens" on a shared environment; this can slow down the JVM, trigger continuous garbage collection, or exhaust resources.

Good policy:

- Define a **reasonable size limit** for the problem.
- Check `length >= 0` and `length <= maxAllowed`.
- Check for overflow in additions/multiplications that compute the length.
- For large data, consider **streaming, chunking/batching**, or data structures that do not require allocating one massive contiguous array.
- Do not rely on catching `OutOfMemoryError` as a normal resource-management strategy.

## 16. Should You `catch (NegativeArraySizeException)` in Real Applications?

Syntactically, you can catch it directly:

~~~java
try {
    int[] data = new int[requestedSize];
    use(data);
} catch (NegativeArraySizeException ex) {
    logInvalidSize(requestedSize, ex);
}
~~~

The snippet above is **illustrative**, with `requestedSize`, `use`, and `logInvalidSize` belonging to the enclosing context. However, you should evaluate the intent:

- If a negative length can come from **untrusted input**, validate the input **before allocation**, choosing an input error type meaningful to the caller.
- If a negative length comes from an **internal calculation bug**, catching and ignoring it usually masks the bug. Log sufficient context and fix the calculation.
- If you are implementing a **boundary that accepts arbitrary data** or a testing tool, catching `NegativeArraySizeException` to translate it into a safe message can be reasonable.
- If you catch the exception and return an empty array, make sure that is a **defined business rule**, not a way to hide an invalid state.
- Never equate unchecked exceptions with errors that can be arbitrarily ignored.

A better example at the validation layer:

~~~java
static byte[] allocateBuffer(long requested) {
    final int maxAllowed = 1_000_000;
    if (requested < 0 || requested > maxAllowed) {
        throw new IllegalArgumentException(
                "requested phải trong [0, " + maxAllowed + "]");
    }
    return new byte[Math.toIntExact(requested)];
}
~~~

This is a **compilable Java method** when placed inside a class. It clearly defines the input preconditions and business limits before allocation. `IllegalArgumentException` signals to the caller that **the method contract was violated**, rather than relying on an allocation failure occurring deep inside.

## 17. Manual `throw` vs. Runtime-Generated Exceptions

You can throw an instance yourself:

~~~java
throw new NegativeArraySizeException("Kích thước không hợp lệ: " + requested);
~~~

This syntax is valid when `requested` exists. However, for **API validation**, a standard `IllegalArgumentException` or a specific domain exception is usually clearer. `NegativeArraySizeException` specifically indicates that the error condition relates to **array creation**, so using it for an unrelated error can be confusing.

A `NegativeArraySizeException` generated by the runtime when an array creation expression encounters a negative size may have a different message than one you construct yourself. **Do not parse `getMessage()`** to infer the size or recover data; the message should not be treated as a stable structured API.

If you need the negative size value for investigation, log the inputs and relevant calculation steps, while ensuring you do not expose sensitive data in logs outside your policy.

## 18. Comparing Common Array-Related Errors

| Situation | Typical Exception / Error |
| --- | --- |
| `new int[-4]` | `NegativeArraySizeException` |
| `new int[0]` | Succeeds, empty array |
| `new String[2][-1]` | `NegativeArraySizeException` |
| `new int[2][]` | Succeeds, sub-arrays not yet created (initially `null`) |
| `int[] a = new int[2]; a[-1]` | `ArrayIndexOutOfBoundsException` |
| `int[] a = new int[2]; a[2]` | `ArrayIndexOutOfBoundsException` |
| `int[] a = null; a[0]` | `NullPointerException` |
| `Integer.parseInt("abc")` | `NumberFormatException` |
| `new ArrayList<>(-1)` | `IllegalArgumentException` |
| `Math.addExact(Integer.MAX_VALUE,1)` | `ArithmeticException` |
| `new byte[very_large_positive_value]` | May encounter `OutOfMemoryError`; exact outcome is not guaranteed across all JVMs |
| `Array.newInstance(int.class, -2)` | `NegativeArraySizeException` |

This table assumes the expressions are executed and no other exception occurs before the step of interest; for example, a length-computing method with side effects that throws before returning can produce a different exception type.

## 19. Debugging by Tracing Back the Size Value

When you see a stack trace with `NegativeArraySizeException`, trace backward from the array creation site:

1. **Locate the array creation expression**: `new byte[size]`, `new T[n][m]`, `Array.newInstance(...)`, or an indirect API?
2. **Record the actual size value** (if safe to do so), including each dimension of a multi-dimensional array.
3. **Trace the data source**: method parameter, configuration, line count read, index subtraction, `-1` sentinel, parser result, or arithmetic expression?
4. **Check for overflow**: could length multiplication/addition exceed `int`? Is there a `long → int` cast?
5. **Check zero-length logic**: is the empty case allowed, or is it a sign of bad data?
6. **Check the evaluation order of dimension expressions**, if there are multiple dimensions or side effects.
7. **Add validation at the appropriate boundary** before allocation.
8. **Write tests for boundary cases**: negative, 0, 1, maximum allowed limit, and values exceeding the limit.
9. If the array is created inside a constructor/factory, check whether **state/resources allocated before the failure point** are handled properly.
10. Do not replace all negative values with `0` without knowing why the negative value occurred.

For computing the length of a range `[start, end)`, you can assert `start <= end` and then check bounds; for a buffer size depending on a payload, you need to enforce a maximum payload size. What matters is the **business relationship**, not just the `new int[n]` syntax.

## 20. Guide to Testing Boundary Cases

A reasonable test suite:

| Size Input | Expected for Direct Array Allocation | Expected for Validated API |
| --- | --- | --- |
| `-1` | `NegativeArraySizeException` | Input error per contract, e.g., `IllegalArgumentException` |
| `0` | Succeeds, `length=0` | Succeeds if the application allows empty data |
| `1` | Succeeds, `length=1` | Succeeds |
| `maxAllowed` | Can be created if sufficient memory is available | Succeeds if resources permit |
| `maxAllowed+1` | May succeed or fail depending on the exact number and environment | Rejected per contract before allocation |
| Value that overflows to negative | `NegativeArraySizeException` | Overflow should be detected in the prior calculation |
| Non-numeric input | Parser error before array allocation | Data error with an appropriate message/code |

In unit tests, do not try to allocate arrays near the JVM limit; instead, use a **small application-level limit** to test validation reliably without exhausting the heap.

You can check both the **exception type** and **published error information**, without asserting on the JVM-generated message:

~~~java
// JUnit-style example illustrating intent; requires the JUnit library to run.
assertThrows(NegativeArraySizeException.class, () -> new int[-1]);
~~~

This snippet only illustrates the testing idea; it is **not a standalone Java 17 program**, and lambda/method-reference context should be checked against your specific test API. The Java 17 programs in sections 4, 8, 11, and 14 are complete examples with no external dependencies.

## 21. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "`new int[-1]` does not compile." | It compiles; the error occurs at runtime when the allocation expression is evaluated. |
| "`new int[0]` also fails because it has no elements." | No. A size of 0 is valid. |
| "Having a negative element makes the array invalid." | No. `int[] a={-5}` is completely valid. |
| "If the first dimension is 0, subsequent dimensions are not checked." | False. `new int[0][-1]` still throws `NegativeArraySizeException`. |
| "If the first dimension is negative, Java does not call the expression for the second dimension." | False when the first dimension **returns normally**: Java continues evaluating dimension expressions before checking for negatives. |
| "If a later dimension expression throws, Java still catches `NegativeArraySizeException` for the first dimension." | An exception from a later expression can terminate evaluation before the negative-size check runs. |
| "`NegativeArraySizeException` is a subclass of `IndexOutOfBoundsException`." | No; its direct superclass is `RuntimeException`. |
| "Negative index and negative size are the same error." | Accessing a negative index usually throws `ArrayIndexOutOfBoundsException`; allocating with a negative size throws `NegativeArraySizeException`. |
| "`new ArrayList<>(-1)` also throws `NegativeArraySizeException`." | The `ArrayList(int)` constructor throws `IllegalArgumentException` for a negative capacity. |
| "A negative size can never happen if the initial inputs are positive." | Integer overflow or incorrect arithmetic can still produce a negative number. |
| "Just clamping with `Math.max(0, size)` is always right." | It can hide bugs, break semantics, and lose data. |
| "A positive value is guaranteed to allocate successfully." | Large sizes can still exceed memory budgets or JVM limits. |
| "Just catching the exception fixes the issue." | If the size was computed incorrectly, you must fix the source and validate preconditions. |
| "The `getMessage()` text of a runtime error is a stable API." | You should not depend on the specific message format generated by the JVM. |

## 22. Self-Check Questions

**Question 1.** What error does `new int[-2]` cause, and when?

**Answer:** `NegativeArraySizeException` at runtime when the array creation expression is executed.

**Question 2.** Is `new int[0]` valid?

**Answer:** Yes. An empty array with `length=0`.

**Question 3.** Does `int[] x={-2}` throw `NegativeArraySizeException`?

**Answer:** No. `-2` is an element value; the array has length 1.

**Question 4.** Is `new int[0][-1]` valid?

**Answer:** No. The negative size of the second dimension is still checked.

**Question 5.** In `new int[first()][second()]`, if `first()` returns `-1` and `second()` has a side effect and returns `2`, does `second()` run?

**Answer:** Yes. Java evaluates dimension expressions from left to right before checking for negative values.

**Question 6.** If `second()` throws `IllegalStateException`, will Java necessarily also throw `NegativeArraySizeException` because `first()=-1`?

**Answer:** No. Expression evaluation terminated abruptly at `second()`.

**Question 7.** What does `int[] a=new int[2]; a[-1]` throw?

**Answer:** `ArrayIndexOutOfBoundsException`, because it accesses an element at an invalid index.

**Question 8.** Does `new ArrayList<String>(-1)` throw `NegativeArraySizeException`?

**Answer:** No. The `ArrayList` capacity constructor throws `IllegalArgumentException`.

**Question 9.** What does `Math.addExact(Integer.MAX_VALUE, 1)` throw?

**Answer:** `ArithmeticException` due to `int` addition overflow.

**Question 10.** If a buffer needs a size taken from a `long`, how do you prevent narrowing errors?

**Answer:** Verify that the value is within the valid range and memory budget, then use `Math.toIntExact` or cast after controlled validation.

**Question 11.** Does `NegativeArraySizeException` require a `throws` declaration?

**Answer:** No, because it is an unchecked exception.

**Question 12.** Why shouldn't you just write `catch (NegativeArraySizeException)` and return an empty array?

**Answer:** Because it can hide input or calculation bugs; negative values usually need to be identified and handled semantically at the source of the size calculation.

## 23. Official References

- [Java SE 17 API — `NegativeArraySizeException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NegativeArraySizeException.html): hierarchy, throw conditions, and constructors.
- [Java Language Specification 17 — §15.10.1, Array Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.10.1): array creation syntax.
- [Java Language Specification 17 — §15.10.2, Run-Time Evaluation of Array Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.10.2): evaluation order of dimension expressions and negative-size checks.
- [Java Language Specification 17 — §10, Arrays](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html): arrays, `length`, component types, and multi-dimensional structure.
- [Java SE 17 API — `java.lang.reflect.Array`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Array.html): `newInstance` and reflection operations on arrays.
- [Java SE 17 API — `ArrayList`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html): distinguishing the initial capacity contract from Java array size.
- [Java SE 17 API — `Math`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `addExact`, `multiplyExact`, and `toIntExact` for overflow checking.
- [Java SE 17 API — `ArrayIndexOutOfBoundsException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ArrayIndexOutOfBoundsException.html): index access errors, distinct from allocation errors.

**Conclusion:** `NegativeArraySizeException` occurs when **the size used to create a Java array is negative**, including multi-dimensional arrays and array-creation reflection APIs. A length of `0` is valid; negative element values are also valid. To avoid this error, **validate data sources, compute lengths without integer overflow, enforce allocation bounds, and clearly distinguish size errors from index-access errors**.
