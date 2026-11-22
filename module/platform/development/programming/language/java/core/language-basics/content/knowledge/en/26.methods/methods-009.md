# Varargs and Their Relationship with Arrays — Java 17+

## 1. What Is Varargs?

**Varargs** (*variable-length arguments*) allows a method to accept a **variable number of arguments**. The syntax uses three dots `...` after the element type:

~~~java
static int sum(int... numbers) {
    int total = 0;
    for (int number : numbers) {
        total += number;
    }
    return total;
}
~~~

You can call the same method in any of the following ways:

~~~java
System.out.println(sum());                  // No elements passed.
System.out.println(sum(7));                 // One element.
System.out.println(sum(1, 2, 3));           // Three elements.
System.out.println(sum(new int[]{4, 5}));   // Passing an existing int[] array.
~~~

**Exact expected stdout:**

~~~text
0
7
6
9
~~~

**Key point:** inside the method body, `numbers` has **type `int[]`**, so `numbers.length`, `numbers[i]`, and enhanced `for` work just like on a normal array. Varargs is primarily syntactic convenience for the **caller**, not a new data-storage structure.

## 2. Comparing `int...` and `int[]`

| Definition | `sum()` | `sum(1, 2)` | `sum(new int[]{1, 2})` |
|---|---|---|---|
| `static int sum(int... a)` | Valid | Valid | Valid |
| `static int sum(int[] a)` | Invalid | Invalid | Valid |

Inside the method, both declarations give a parameter of type `int[]`. However, only the `int...` form lets the compiler construct an array **from a list of multiple arguments** at the call site.

~~~java
static void inspect(int... data) {
    System.out.println("length=" + data.length);
}
~~~

~~~java
inspect();               // length=0
inspect(10, 20);         // length=2
inspect(new int[]{30});  // length=1
~~~

You cannot declare two methods differing only in `int[]` vs. `int...` with the same name in the same class: in terms of **compiled signature**, they have the same array parameter type.

~~~java
// Cannot coexist:
// static void f(int[] a) { }
// static void f(int... a) { } // Duplicate signature f(int[]).
~~~

## 3. Varargs Must Be the Last Parameter

Varargs can follow fixed parameters:

~~~java
static void log(String prefix, int... values) {
    System.out.println(prefix + ":" + values.length);
}
~~~

~~~java
log("empty");       // empty:0
log("count", 1, 2); // count:2
~~~

Syntax rules:

- Each method declaration has **at most one** varargs parameter.
- The varargs parameter must be the **last parameter**.
- `static void bad(int... a, String tag)` is invalid because another parameter follows varargs.
- `static void bad(int... a, String... b)` is also invalid.

Fixed parameters before varargs must still be passed properly: `log()` is invalid because `prefix` is missing, whereas `log("ok")` is valid and creates an empty number sequence.

## 4. Temporary Arrays vs. Existing Arrays: Difference in References

With the call `sum(1, 2, 3)`, Java treats those three arguments as the contents of **a new `int[]` array** passed into the varargs parameter. The caller has no variable pointing to that temporary array.

With the call `sum(existing)` where `existing` is an `int[]`, Java passes the **existing array reference**; it does not automatically copy the array.

~~~java
static void changeFirst(int... data) {
    if (data.length > 0) {
        data[0] = 99;
    }
}

int[] original = {2, 3, 4};
changeFirst(original);
System.out.println(java.util.Arrays.toString(original));
changeFirst(8, 9);
System.out.println(java.util.Arrays.toString(original));
~~~

**Exact expected stdout:**

~~~text
[99, 3, 4]
[99, 3, 4]
~~~

The first call mutates **the caller's own array element**. The second call mutates the array created for the argument list `8, 9`, without changing `original`. Java passes arguments **by value**, but for arrays the passed value is the **reference to the array object**.

If you do not want the method to alter a passed-in array, avoid mutating elements or explicitly copy it with `Arrays.copyOf`.

## 5. `sum()` Creates an Empty Array; Passing `null` Is Different

Passing no varargs arguments:

~~~java
sum(); // numbers is a non-null int[] of length 0.
~~~

Differs from intentionally passing a `null` array reference:

~~~java
sum((int[]) null); // Passes null as the array argument.
~~~

If the method body iterates over `numbers` or reads `numbers.length` immediately, the second case can cause a `NullPointerException`. An API can choose to reject null explicitly:

~~~java
static int checkedSum(int... numbers) {
    if (numbers == null) {
        throw new IllegalArgumentException("null array");
    }
    int result = 0;
    for (int n : numbers) result += n;
    return result;
}
~~~

| Call | State of `numbers` |
|---|---|
| `checkedSum()` | Empty array, `length == 0` |
| `checkedSum(1, 2)` | Array containing `1, 2` |
| `checkedSum(new int[0])` | Existing empty array |
| `checkedSum((int[]) null)` | Literally `null`; example throws `IllegalArgumentException` |

**Note:** `null` can make reference-type varargs calls ambiguous to resolve or emit warnings; use an explicit array cast when the intent is to pass a null array.

## 6. Varargs with Multidimensional Arrays

The element type of varargs can be **an array**:

~~~java
static void showRows(int[]... rows) {
    System.out.println("rows=" + rows.length);
    for (int[] row : rows) {
        System.out.println(java.util.Arrays.toString(row));
    }
}
~~~

Two valid calls:

~~~java
showRows(new int[]{1, 2}, new int[]{3});
int[][] matrix = {{4}, {5, 6}};
showRows(matrix);
~~~

**Exact expected stdout:**

~~~text
rows=2
[1, 2]
[3]
rows=2
[4]
[5, 6]
~~~

Here `int[]... rows` has the actual type **`int[][]`** inside the method. Each element `row` is an `int[]`. If a row can be null, check it separately before accessing `row.length`.

## 7. Method Overloading with Varargs

~~~java
static String choose(int value) {
    return "single";
}

static String choose(int... values) {
    return "varargs count=" + values.length;
}
~~~

~~~java
System.out.println(choose(4));
System.out.println(choose(4, 5));
System.out.println(choose());
~~~

**Exact expected stdout:**

~~~text
single
varargs count=2
varargs count=0
~~~

With a single `int` argument, the fixed overload `choose(int)` is selected before the applicable varargs form. With zero arguments or two arguments, only the varargs overload in the pair above applies.

**Be careful:** multiple similar varargs overloads can create **ambiguous** calls. For example, if both `f(String...)` and `f(Integer...)` exist, the call `f()` cannot determine which overload to pick. Avoid designing unpredictable varargs overloads solely to shorten call syntax.

## 8. Notes on Reference-Type or Generic Varargs

With `String... words`, the parameter in the body is `String[]`; each element can be null, so code using `words[i].length()` needs per-element null checks.

With varargs containing generic types, such as `List<String>... groups`, Java can emit warnings about **heap pollution** because arrays and generics have different type rules. Do not ignore warnings blindly or add `@SafeVarargs` when unsure whether the method is safe; in core Java basics, prefer simple varargs types like `int...` and `String...`.

If there are many arguments and the data is already in an array, passing the array directly is both clearer and avoids creating an extra array from an element list at the call site.

## 9. Java 17+ Program Run via CLI

Create the file with the exact name **`VarargsArrayDemo.java`**:

~~~java
import java.util.Arrays;

public final class VarargsArrayDemo {
    private VarargsArrayDemo() {}

    static int sum(int... values) {
        if (values == null) {
            throw new IllegalArgumentException("null array");
        }
        int total = 0;
        for (int value : values) total += value;
        return total;
    }

    static String describe(String title, String... names) {
        return title + " count=" + names.length
                + " " + Arrays.toString(names);
    }

    static void changeFirst(int... values) {
        if (values != null && values.length > 0) {
            values[0] = 99;
        }
    }

    static void showRows(int[]... rows) {
        System.out.println("row count=" + rows.length);
        for (int i = 0; i < rows.length; i++) {
            System.out.println("row " + i + "=" + Arrays.toString(rows[i]));
        }
    }

    static String choose(int value) {
        return "single";
    }

    static String choose(int... values) {
        return "varargs count=" + values.length;
    }

    public static void main(String[] args) {
        System.out.println("sum empty=" + sum());
        System.out.println("sum one=" + sum(7));
        System.out.println("sum many=" + sum(1, 2, 3));

        int[] existing = {2, 3, 4};
        System.out.println("array before=" + Arrays.toString(existing));
        System.out.println("sum array=" + sum(existing));
        changeFirst(existing);
        System.out.println("array after change=" + Arrays.toString(existing));
        changeFirst(8, 9);
        System.out.println("array after temporary=" + Arrays.toString(existing));

        System.out.println(describe("empty"));
        System.out.println(describe("names", "Lan", "Minh"));
        String[] savedNames = {"An", "Binh"};
        System.out.println(describe("array", savedNames));

        showRows(new int[]{1, 2}, new int[]{3});
        int[][] matrix = {{4}, {5, 6}};
        showRows(matrix);

        System.out.println("choose one=" + choose(4));
        System.out.println("choose two=" + choose(4, 5));
        System.out.println("choose empty=" + choose());

        try {
            sum((int[]) null);
        } catch (IllegalArgumentException ex) {
            System.out.println("null input=" + ex.getMessage());
        }
    }
}
~~~

**Bash (Linux/macOS), JDK 17+:**

~~~bash
javac --release 17 -encoding UTF-8 VarargsArrayDemo.java
java -cp . VarargsArrayDemo
~~~

**PowerShell (Windows), JDK 17+:**

~~~powershell
javac --release 17 -encoding UTF-8 .\VarargsArrayDemo.java
java -cp . VarargsArrayDemo
~~~

### Exact expected stdout

~~~text
sum empty=0
sum one=7
sum many=6
array before=[2, 3, 4]
sum array=9
array after change=[99, 3, 4]
array after temporary=[99, 3, 4]
empty count=0 []
names count=2 [Lan, Minh]
array count=2 [An, Binh]
row count=2
row 0=[1, 2]
row 1=[3]
row count=2
row 0=[4]
row 1=[5, 6]
choose one=single
choose two=varargs count=2
choose empty=varargs count=0
null input=null array
~~~

## 10. Common Mistakes and Exercises

| Mistake | Cause | How to fix |
|---|---|---|
| Thinking `int...` is a new data type | Inside the body it is `int[]` | Use `.length`, `[i]`, array iteration loops |
| Placing parameters after varargs | Varargs must come last | `f(String label, int... values)` |
| Having two varargs in one method | Invalid syntax | Use only one varargs parameter |
| Declaring both `f(int[])` and `f(int...)` | Duplicate signature | Keep one definition |
| Assuming `f(existingArray)` auto-copies the array | Passes the reference value of the old array | Avoid mutating or copy explicitly |
| Thinking `f()` creates a null parameter | An empty varargs call creates a length-0 array | Distinguish `f((int[]) null)` |
| Confusing `int[]...` with `int...` | Different element types | `int[]...` corresponds to `int[][]` |
| Overusing varargs overloads | Easily causes ambiguity at call sites | Use clear names/parameter categorization |

**Exercise A.** Given `static int count(String... words) { return words.length; }`, what does `count()` return? **0**; `count("a", "b")` returns **2**; `count(new String[]{"a"})` returns **1**.

**Exercise B.** Why can't `print(int[] a)` and `print(int... a)` be defined simultaneously? Because Java treats both forms as having the **same array parameter type**, causing a duplicate method signature.

**Exercise C.** Does `changeFirst(existing)` mutate the caller's array? **Yes**, if the array has elements and the method assigns to `values[0]`. With a separate argument list `changeFirst(1, 2)`, the caller has no corresponding original array to observe.

**Exercise D.** If `int[][] a = {{1}, {2, 3}}`, what parameter type does `showRows(a)` receive? **`int[][]`**, because declaring `int[]... rows` is varargs of `int[]`.

## 11. Checklist and Conclusion

- [ ] Know the syntax `T... values` and that varargs must be the last parameter.
- [ ] Understand that inside the method body, varargs is `T[]`.
- [ ] Call with 0, 1, many arguments, or with an existing array.
- [ ] Distinguish a temporary array from an argument list vs. a caller's array passed directly.
- [ ] Do not assume varargs automatically copies a passed array.
- [ ] Distinguish an empty array and an intentionally passed null value.
- [ ] Know `int[]...` corresponds to parameter type `int[][]`.
- [ ] Recognize ambiguous varargs overload cases.
- [ ] Run `VarargsArrayDemo.java` on JDK 17+ and verify exact stdout.

**Conclusion:** Varargs `T...` makes **calling** a method more flexible, while inside the **body** it remains an array `T[]`. When passing a list of elements, Java creates an array containing those values; when passing an existing array, the method receives a reference to **that very array**, so modifying elements can affect the caller.