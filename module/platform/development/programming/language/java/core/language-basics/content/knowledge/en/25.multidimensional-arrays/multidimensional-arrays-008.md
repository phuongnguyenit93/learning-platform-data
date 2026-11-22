# Covariant Reference Arrays and the Risk of `ArrayStoreException` in Java

> **Java core — language-basics / Multidimensional arrays**  
> **Requirements:** Java 17+, JDK, no external libraries required.  
> **Goal:** Explain why `String[]` can be assigned to `Object[]`, why assigning an element can still fail at runtime, how to inspect an array's actual element type, and apply this correctly with `String[][]`, `Object[][]`, and `int[][]`.

## 1. Covariance of Reference Arrays

Suppose `String` is a subclass of `Object`. Java allows treating a **reference array** `String[]` as an `Object[]`:

~~~java
String[] names = {"An", "Binh"};
Object[] view = names; // Valid: String[] is a subtype of Object[].
System.out.println(view == names); // true
~~~

This is called **reference array covariance**: if `Sub` is a subtype of `Super` and both are appropriate reference types, `Sub[]` can be assigned to a `Super[]` variable. Examples:

| Relationship | Directly assignable? | Reason |
| --- | --- | --- |
| `String[]` → `Object[]` | Yes | `String` is a subtype of `Object` |
| `Integer[]` → `Number[]` | Yes | `Integer` is a subtype of `Number` |
| `Dog[]` → `Animal[]` if `Dog extends Animal` | Yes | Subtype relationship of the component type |
| `Object[]` → `String[]` | No, unless cast with a runtime check | The reverse direction is unsafe |
| `int[]` → `Object[]` | **No** | `int` is primitive, not a subtype of `Object` |
| `int[]` → `Object` | Yes | The array itself is an object |
| `String[][]` → `Object[][]` | Yes | Array types at each level have matching subtype relationships |

**Distinguish the reference variable from the actual object:** In `Object[] view = names;`, Java **does not create a new `Object[]` array**. Both variables simply hold references to an object whose **actual runtime type is `String[]`**.

## 2. Why Compile-Time Checking Is Not Enough for Safety

Consider this snippet:

~~~java
String[] names = {"An", "Binh"};
Object[] items = names;

items[1] = "Chi";            // Valid: String.
System.out.println(names[1]); // Chi.

// items[0] = Integer.valueOf(7); // Compiles,
// but throws ArrayStoreException at runtime.
~~~

Looking at the **declared type** `Object[]`, the compiler allows placing an `Integer` reference into an `Object` element. However, the actual array object is still `String[]`, which only permits each element to receive a `String` (or `null`). The JVM checks at the moment of the write operation and throws `ArrayStoreException` if the value is incompatible with the **runtime component type**.

In other words, there are **two layers of checks**:

1. **Compile time:** the expression on the right-hand side must be assignable to the element type according to the **static type** of the array variable (`Object` for `Object[]`).
2. **Runtime:** if the element is a non-null reference, the JVM checks whether the object being written is compatible with the **actual component type of the array object** (`String` for `new String[n]`).

Therefore, `Object[]` is the type name that code sees, not a promise that the current array object can hold any kind of `Object`.

A method accepting `Object[]` carries the same risk:

~~~java
static void replaceFirst(Object[] array, Object value) {
    array[0] = value; // May throw ArrayStoreException.
}

// replaceFirst(new String[1], Integer.valueOf(10));
// Call is valid at compile time, fails at write time.
~~~

## 3. When Does `ArrayStoreException` Occur?

`ArrayStoreException` is a **runtime** exception thrown when attempting to store an incompatible reference value into an array with a specific reference component type. It extends `RuntimeException`, so no `throws` declaration is needed to compile the call.

~~~java
Object[] values = new String[2];
values[0] = "Java";       // Valid.
values[1] = null;         // Valid: null is allowed for reference types.

try {
    values[1] = Integer.valueOf(42); // Wrong actual type String[].
} catch (ArrayStoreException ex) {
    System.out.println("Rejected");
}
~~~

**How to distinguish errors:**

| Situation | Behavior |
| --- | --- |
| `Object[] a = new String[2]; a[0] = "x";` | Write succeeds |
| `a[0] = null;` | Write succeeds; `null` is valid |
| `a[0] = 42;` | `ArrayStoreException` (autoboxes 42 to `Integer`) |
| `Object[] b = new Object[2]; b[0] = 42;` | Write succeeds because the actual array is `Object[]` |
| `String[] s = (String[]) new Object[2];` | `ClassCastException` when casting the array, **not** an element write error |
| `String[] s = null; s[0] = "x";` | `NullPointerException` |
| `new String[0][0];` then access element `[0]` | `ArrayIndexOutOfBoundsException` |

**Do not assert exceptions by JVM message text:** `ex.getMessage()` content can vary across environments; in demos, print the exception type so expected stdout stays stable.

## 4. The Actual Component Type Is Retained at Runtime

Unlike generic type information which is usually erased (*type erasure*), Java array objects **know their runtime component type**:

~~~java
Object[] strings = new String[2];
Object[] objects = new Object[2];

System.out.println(strings.getClass().getComponentType().getTypeName());
// java.lang.String
System.out.println(objects.getClass().getComponentType().getTypeName());
// java.lang.Object
~~~

Hence, `Object[] strings` and `Object[] objects` have **the same declared variable type**, yet different element-write checks.

When assigning `Object[] alias = strings;`, the runtime type does not change. `strings.clone()` also creates a new array **with the same runtime type `String[]`** and copies the current elements; the cloned array still will not accept an `Integer` merely because it was assigned to an `Object[]` variable.

If you want an array that can genuinely hold multiple object types, you must **create a new `Object[]` array** and copy the appropriate elements into it, such as `Object[] copy = java.util.Arrays.copyOf(strings, strings.length, Object[].class);`.

## 5. Covariance in Multidimensional Arrays

A `String[][]` is **an outer array containing references to `String[]`**. It can be viewed through an `Object[][]` variable:

~~~java
String[][] names = {{"A", "B"}, {"C"}};
Object[][] grid = names;

Object[] firstRow = grid[0]; // Actually a String[].
firstRow[1] = "BB";           // Valid.
System.out.println(names[0][1]); // BB.
~~~

There are **two write locations** to consider, each checking the type of the array being written to:

| Statement via `Object[][] grid` | Actual array written to | Result |
| --- | --- | --- |
| `grid[0][0] = "X";` | Actual subarray `String[]` | Valid |
| `grid[0][0] = 5;` | Actual subarray `String[]` | `ArrayStoreException` |
| `grid[1] = new String[] {"Y"};` | Actual outer array `String[][]`, element type `String[]` | Valid |
| `grid[1] = new Object[] {"Y"};` | Actual outer array `String[][]` | `ArrayStoreException` |
| `grid[0] = null;` | Actual outer array `String[][]` | Valid; row becomes `null` |

Thus, an error can occur both **when replacing a subarray** (`grid[row] = ...`) and **when replacing an element inside a subarray** (`grid[row][column] = ...`).

`String[][]` can also be assigned to an `Object[]` variable because its elements (type `String[]`) are themselves objects. However, the runtime type of the outer array remains `String[][]`; storing an `Object[]` that is not a `String[]` into a row slot will still be rejected.

**Jagged arrays** do not change this principle: rows may have different lengths, but every non-null row must still be a subarray of a type compatible with the outer array.

## 6. Important Exception: `int[]` and `int[][]`

With primitive arrays:

~~~java
int[] numbers = {1, 2};
Object asObject = numbers; // Valid: every array is an Object.
// Object[] invalid = numbers; // COMPILE ERROR: int[] is not Object[].
~~~

`int[]` holds elements of primitive type `int`, not `Object` references. However, `int[][]` is **an outer array containing elements of reference type `int[]`**, because each `int[]` itself is an object. Therefore:

~~~java
int[][] matrix = new int[2][];
Object[] rows = matrix;              // Valid.
rows[0] = new int[] {1, 2};         // Valid.
System.out.println(matrix[0][0]);  // 1.

// rows[1] = new long[] {3L};
// Compiles via Object[], but throws ArrayStoreException:
// the actual outer array requires each row to be int[].
~~~

This is not "primitive array covariance" in the sense of `int[]` being assignable to `long[]` or `Object[]`. Covariance here occurs at **the outer level**, where the element type `int[]` is a reference type.

## 7. Comparison with Generic `List` and Prevention

Standard Java generics are **invariant** (*invariant*):

~~~java
java.util.List<String> names = new java.util.ArrayList<>();
names.add("Java");

// java.util.List<Object> objects = names;
// Does not compile: List<String> is not a subtype of List<Object>.

java.util.List<? extends Object> readable = names;
System.out.println(readable.getClass().getSimpleName()); // ArrayList.
~~~

A `List<? extends Object>` reference allows **reading** elements as `Object`, but prevents arbitrarily calling `add(new Object())` on a list of unknown element type (except `null`). This catches early the class of operations that could otherwise cause runtime errors with covariant arrays.

**Design recommendations:**

- If an API only **reads data**, avoid modifying elements in a method taking `Object[]`; use a specific parameter type or an appropriate read-only abstraction.
- If an API needs to **write**, use an array with the exact component type, or use `List<T>` with a clear generic contract.
- When you already have an `Object[] view` and need to know what array type was actually received, inspect the source and `view.getClass().getComponentType()` while debugging; do **not** use runtime checks as a substitute for proper type design.
- An array object received via a cast, method parameter, or `clone` does not change its runtime component type on its own.
- `final Object[] view` only forbids **reassigning the `view` variable**, not modifying elements of the array object; `ArrayStoreException` can still occur.

If you need to copy from `String[]` into an array with runtime type `Object[]`, create a genuinely new array:

~~~java
String[] source = {"A", "B"};
Object[] flexible = java.util.Arrays.copyOf(
        source, source.length, Object[].class);
flexible[0] = Integer.valueOf(99); // Valid: the runtime array is Object[].
~~~

`Arrays.copyOf(..., Object[].class)` returns a new array of type `Object[]`, unlike `source.clone()` which preserves the runtime type `String[]`.

## 8. Standalone Java 17+ Example

Create the file **CovariantArrayDemo.java**:

~~~java
import java.util.Arrays;

public final class CovariantArrayDemo {
    private static void replaceFirst(Object[] target, Object value) {
        target[0] = value; // May throw ArrayStoreException at runtime.
    }

    public static void main(String[] args) {
        String[] words = {"A", "B"};
        Object[] view = words;
        System.out.println("sameArray=" + (view == words));
        System.out.println("actualComponent="
                + view.getClass().getComponentType().getTypeName());

        view[1] = "BB";
        view[0] = null; // null is always valid for reference elements.
        System.out.println("validWrites=" + Arrays.toString(words));

        try {
            replaceFirst(view, Integer.valueOf(7));
        } catch (ArrayStoreException ex) {
            System.out.println("stringReject=ArrayStoreException");
        }
        System.out.println("afterReject=" + Arrays.toString(words));

        Object[] general = new Object[1];
        general[0] = Integer.valueOf(42);
        System.out.println("objectAccept=" + general[0]);

        Number[] numbers = new Integer[2];
        numbers[0] = Integer.valueOf(5);
        try {
            numbers[1] = Double.valueOf(1.5);
        } catch (ArrayStoreException ex) {
            System.out.println("numberReject=ArrayStoreException");
        }
        System.out.println("numbersAfter=" + Arrays.toString(numbers));

        String[] cloned = words.clone();
        System.out.println("cloneDifferent=" + (cloned != words));
        System.out.println("cloneComponent="
                + cloned.getClass().getComponentType().getTypeName());
        try {
            ((Object[]) cloned)[0] = Integer.valueOf(8);
        } catch (ArrayStoreException ex) {
            System.out.println("cloneReject=ArrayStoreException");
        }

        String[][] names = {{"A", "B"}, {"C"}};
        Object[][] grid = names;
        Object[] firstRow = grid[0];
        firstRow[1] = "BB";
        System.out.println("innerValid=" + Arrays.toString(names[0]));
        try {
            firstRow[0] = Integer.valueOf(9);
        } catch (ArrayStoreException ex) {
            System.out.println("innerReject=ArrayStoreException");
        }
        try {
            grid[1] = new Object[] {"X"};
        } catch (ArrayStoreException ex) {
            System.out.println("outerReject=ArrayStoreException");
        }
        System.out.println("afterOuterReject=" + Arrays.deepToString(names));

        grid[1] = new String[] {"OK"};
        System.out.println("outerValid=" + Arrays.deepToString(names));

        int[][] primitiveRows = new int[2][];
        Object[] rowView = primitiveRows;
        rowView[0] = new int[] {1, 2};
        System.out.println("intRow=" + Arrays.toString(primitiveRows[0]));
        try {
            rowView[1] = new long[] {3L};
        } catch (ArrayStoreException ex) {
            System.out.println("primitiveRowReject=ArrayStoreException");
        }
        System.out.println("secondRowNull=" + (primitiveRows[1] == null));

        Object primitiveAsObject = new int[] {5};
        System.out.println("primitiveIsObjectArray="
                + (primitiveAsObject instanceof Object[]));

        Object[] flexible = Arrays.copyOf(
                words, words.length, Object[].class);
        flexible[0] = Integer.valueOf(99);
        System.out.println("flexible=" + Arrays.toString(flexible));
        System.out.println("sourceUnchanged=" + Arrays.toString(words));

        try {
            String[] badCast = (String[]) new Object[1];
            System.out.println(badCast.length);
        } catch (ClassCastException ex) {
            System.out.println("badCast=ClassCastException");
        }
    }
}
~~~

Compile and run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 CovariantArrayDemo.java
java CovariantArrayDemo
~~~

**Exact expected stdout:**

~~~text
sameArray=true
actualComponent=java.lang.String
validWrites=[null, BB]
stringReject=ArrayStoreException
afterReject=[null, BB]
objectAccept=42
numberReject=ArrayStoreException
numbersAfter=[5, null]
cloneDifferent=true
cloneComponent=java.lang.String
cloneReject=ArrayStoreException
innerValid=[A, BB]
innerReject=ArrayStoreException
outerReject=ArrayStoreException
afterOuterReject=[[A, BB], [C]]
outerValid=[[A, BB], [OK]]
intRow=[1, 2]
primitiveRowReject=ArrayStoreException
secondRowNull=true
primitiveIsObjectArray=false
flexible=[99, BB]
sourceUnchanged=[null, BB]
badCast=ClassCastException
~~~

The example catches each exception individually so the run output stays consistent. `stringReject` shows the failure after assigning `String[]` to an `Object[]` variable; `innerReject` and `outerReject` demonstrate the two levels of type checking in `String[][]`; `primitiveRowReject` illustrates that the outer array of `int[][]` is also a **reference** array; `flexible` demonstrates how to create an array whose actual type is `Object[]`.

## 9. Common Mistakes and Exercises

| Mistake/misconception | Correct understanding |
| --- | --- |
| `Object[] view = new String[2]` creates a new `Object[]` | No: the actual object is still `String[]` |
| If `view[0] = 7` compiles, it will definitely run | No: the JVM checks the actual element type at write time |
| `ArrayStoreException` occurs when declaring the alias | No: it occurs when attempting to **write** an incompatible element |
| Assigning `null` to `String[]` causes `ArrayStoreException` | No: `null` is valid for every reference type |
| `int[]` is a subtype of `Object[]` | No; `int[]` is only an `Object` |
| `int[][]` cannot be assigned to `Object[]` | Wrong: the outer array's component type is `int[]`, a reference type |
| Assigning `String[][]` to `Object[][]` creates a copy | No; both still use the same multidimensional array object |
| `String[]`'s `clone()` creates an `Object[]` array | No: the runtime array type is preserved |
| `ArrayStoreException` and `ClassCastException` are the same | No: one is an **array write** error, the other is an invalid **cast** error |
| `List<String>` can be assigned to `List<Object>` | No: standard generics are invariant |

**Exercise 1.** Create `String[] source = {"a"}; Object[] alias = source;`. Try writing `"b"`, `null`, and `Integer.valueOf(2)`. Note when `ArrayStoreException` occurs.

**Exercise 2.** Create `Number[] values = new Integer[2];`. Try storing `Integer.valueOf(1)` and `Double.valueOf(2.0)` in turn. Why does the compiler accept the second value while the runtime rejects it?

**Exercise 3.** Create a two-row `String[][] grid` and assign it to `Object[][] alias`. Compare the behavior of `alias[0][0] = 5` and `alias[0] = new Object[] {"x"}`.

**Exercise 4.** Explain why `Object[] rows = new int[2][];` is valid while `Object[] oneRow = new int[2];` does not compile.

**Exercise 5.** Write an example copying `String[]` into a genuine `Object[]` via `Arrays.copyOf(..., Object[].class)`; prove that the new array can store `Integer` without modifying the source array.

### Key Takeaway

**Reference arrays in Java are covariant:** `String[]` can be viewed as `Object[]`, but **the component type of the array object does not change**. When writing to the array, the JVM checks the actual type and may throw `ArrayStoreException`. With multidimensional arrays, checks occur both when replacing a **row** and when replacing an **element in a row**. Avoid APIs that write into overly broad array types; choose specific types, create an array with the right actual type, or use an appropriate generic `List<T>`.