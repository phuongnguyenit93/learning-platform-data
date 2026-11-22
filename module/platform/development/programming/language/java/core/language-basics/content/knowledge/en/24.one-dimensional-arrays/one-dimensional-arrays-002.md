# Declaring Array Variables and Creating Arrays with `new` — Java 17+

## 1. Distinguishing variable declaration from array object creation

In Java, an **array** is a fixed-length object containing elements of the same component type. An array-typed variable holds a **reference** to the array object, rather than containing the elements itself just because it was declared.

~~~java
int[] scores;           // Only declares the array reference variable.
scores = new int[3];    // Creates a three-element array object and assigns its reference.
scores[0] = 10;         // Accesses the first element.
~~~

You can combine declaration and allocation:

~~~java
int[] scores = new int[3];
~~~

| Syntax | What happens? |
|---|---|
| `int[] scores;` | Declares a local variable of type `int[]`; **no array has been created yet** |
| `new int[3]` | Allocates an `int` array object with **3 elements**; returns a reference |
| `scores = new int[3];` | Assigns the reference to the new array to the variable `scores` |
| `scores[0] = 10;` | Updates the value at index 0 in the array that `scores` points to |
| `scores.length` | Reads the array length, which is `3` here |

**Key takeaway:** *variable declaration* and *array creation* are two distinct operations. The `new` keyword performs array object creation at runtime.

## 2. Recommended declaration syntax

Java prefers placing **brackets on the type**:

~~~java
int[] numbers;
String[] names;
double[] temperatures;
boolean[] flags;
~~~

Java also accepts the older style:

~~~java
int numbers[];
~~~

However, `int[] numbers` is easier to read because it clearly shows that the variable's type is **an array of int**.

A trap when declaring multiple variables:

~~~java
int[] first, second; // Both first and second are int[].

int third[], count;  // third is int[]; count is int.
~~~

Therefore, it is usually best to use **one declaration per line** to avoid type confusion.

The `[]` denotes **an array type**, not a size. The length is specified in the allocation expression `new int[3]`, not in the declared type:

~~~java
int[] data = new int[3]; // Valid.
// int[3] data;           // Invalid Java syntax.
~~~

## 3. Creating an array with `new ElementType[size]`

~~~java
int[] scores = new int[3];
String[] labels = new String[2];
boolean[] enabled = new boolean[2];
double[] prices = new double[2];
~~~

`size` is an appropriate integer expression evaluated **at runtime**. The value must be non-negative:

~~~java
int size = 2 + 1;
int[] values = new int[size];   // length = 3.
int[] empty = new int[0];       // Valid: empty array.
~~~

`new int[-1]` is an expression that compiles, but throws `NegativeArraySizeException` at runtime. A non-negative size still does not guarantee enough memory; requesting an excessively large allocation can hit `OutOfMemoryError`.

An array has a **fixed length after creation**. You cannot assign `values.length = 5`; to get a different length, you must create a new array (for example via `Arrays.copyOf`) and use a reference to the new array.

## 4. After `new`, elements already have default values

`new int[3]` creates **an array** with three slots; the initial value in each slot is `0`. For `boolean[]`, the default is `false`; for `char[]`, it is NUL (code 0); for `String[]`, `Student[]`, or other reference arrays, the default is **`null`**, without automatically calling each object's constructor.

~~~java
int[] numbers = new int[2];         // [0, 0]
String[] names = new String[2];      // [null, null]
System.out.println(java.util.Arrays.toString(numbers));
System.out.println(java.util.Arrays.toString(names));
~~~

A local variable `int[] ref;` **has not been assigned** so it cannot be read immediately; this differs from elements of an allocated array. The detailed rules for all eight primitive types and reference types are explained separately in the lesson on default values.

## 5. Indices and `length` of a newly created object

With `new int[3]`, `length == 3` but the valid indices are `0`, `1`, `2`. `length` is a **field**, without parentheses `()`; it cannot be modified to extend that same array.

~~~java
int[] scores = new int[3];
scores[0] = 10;
scores[2] = 30;
System.out.println(scores.length); // 3
// scores[3] = 40; // At runtime: ArrayIndexOutOfBoundsException.
~~~

Check `0 <= i && i < scores.length` before reading or writing with a user-supplied index. This is a bound of an existing array, different from `NegativeArraySizeException` when **creating** an array with a negative size.

After distinguishing declaration and allocation, the following program applies additional related scenarios so you can observe the state of created arrays directly.

## 6. Standalone Java 17+ program

Save the file as **`ArrayDeclarationNewDemo.java`**:

~~~java
import java.util.Arrays;

public final class ArrayDeclarationNewDemo {
    private ArrayDeclarationNewDemo() {}

    static void show(String name, int[] array) {
        System.out.println(name + " length=" + array.length
                + " values=" + Arrays.toString(array));
    }

    public static void main(String[] args) {
        int[] numbers;             // Declared, no array created yet.
        numbers = new int[3];      // Creates three elements defaulting to 0.
        show("new", numbers);

        numbers[0] = 10;
        numbers[2] = 30;
        show("updated", numbers);

        int[] empty = new int[0];
        show("empty", empty);

        int[] initializer = {2, 4, 6};
        show("initializer", initializer);

        int[] explicit = new int[]{7, 8};
        show("explicit", explicit);

        int size = 2 + 1;
        int[] computed = new int[size];
        show("computed", computed);

        String[] labels = new String[2];
        boolean[] flags = new boolean[2];
        double[] prices = new double[2];
        System.out.println("labels=" + Arrays.toString(labels));
        System.out.println("flags=" + Arrays.toString(flags));
        System.out.println("prices=" + Arrays.toString(prices));

        int[] alias = numbers;
        alias[1] = 20;
        show("shared", numbers);
        System.out.println("same object=" + (numbers == alias));

        int[] independent = numbers.clone();
        independent[0] = 99;
        show("original", numbers);
        show("clone", independent);
        System.out.println("clone distinct=" + (numbers != independent));

        int[] extended = Arrays.copyOf(numbers, 5);
        show("extended", extended);
        show("original again", numbers);

        int[] missing = null;
        System.out.println("null ref=" + (missing == null));
        try {
            System.out.println(missing.length);
        } catch (NullPointerException ex) {
            System.out.println("null length=NullPointerException");
        }

        try {
            int[] bad = new int[-1];
            System.out.println(bad.length);
        } catch (NegativeArraySizeException ex) {
            System.out.println("negative size=NegativeArraySizeException");
        }

        try {
            System.out.println(empty[0]);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("empty index=ArrayIndexOutOfBoundsException");
        }
    }
}
~~~

**Bash (Linux/macOS), requires JDK 17+:**

~~~bash
javac --release 17 -encoding UTF-8 ArrayDeclarationNewDemo.java
java -cp . ArrayDeclarationNewDemo
~~~

**PowerShell (Windows), requires JDK 17+:**

~~~powershell
javac --release 17 -encoding UTF-8 .\ArrayDeclarationNewDemo.java
java -cp . ArrayDeclarationNewDemo
~~~

### Exact expected stdout

~~~text
new length=3 values=[0, 0, 0]
updated length=3 values=[10, 0, 30]
empty length=0 values=[]
initializer length=3 values=[2, 4, 6]
explicit length=2 values=[7, 8]
computed length=3 values=[0, 0, 0]
labels=[null, null]
flags=[false, false]
prices=[0.0, 0.0]
shared length=3 values=[10, 20, 30]
same object=true
original length=3 values=[10, 20, 30]
clone length=3 values=[99, 20, 30]
clone distinct=true
extended length=5 values=[10, 20, 30, 0, 0]
original again length=3 values=[10, 20, 30]
null ref=true
null length=NullPointerException
negative size=NegativeArraySizeException
empty index=ArrayIndexOutOfBoundsException
~~~

**Verification:** `new int[3]` produces zeros; assigning values updates elements without changing `length`. An alias affects the same array; `clone` creates a different `int[]` array; `copyOf` creates an array of length 5 while leaving the original array at length 3. The three edge/error cases—`null`, negative size, and reading an empty array—are caught separately and print stable labels without relying on JDK exception messages.

## 7. Common mistakes when first learning arrays

| Mistake | Problem | Correct approach |
|---|---|---|
| `int[] a;` then reading `a.length` | Unassigned local variable | `a = new int[3];` before reading |
| Thinking `int[] a = null;` creates an empty array | `null` has no object | `new int[0]` to create an empty array |
| Writing `int[3] a;` | Size in the wrong place | `int[] a = new int[3];` |
| `a.length()` | `length` is not a method | `a.length` |
| Accessing `a[a.length]` | Last index is `length-1` | Check `0 <= i && i < a.length` |
| Creating `new int[-1]` | `NegativeArraySizeException` | Validate that size is non-negative |
| `new int[2]{1, 2}` | Cannot specify size together with an initializer | `new int[]{1, 2}` |
| `a = {1,2};` after declaration | Shorthand initializer cannot be used here | `a = new int[]{1,2};` |
| Thinking `int[] b = a;` copies elements | Both variables share the same array | `a.clone()` or `Arrays.copyOf` |
| Thinking `new Student[2]` creates two Students | Only creates an array of two null references | Create each `Student` object individually |
| Thinking `a.length` can be changed | Arrays have a fixed length | Create a new array with the desired length |

## 8. Exercises with answers

**A.** Declare a variable of type `double[]` and allocate 4 elements.  
**Answer:**

~~~java
double[] temperatures = new double[4];
~~~

The default value of each element is `0.0`.

**B.** Why can `int[] a;` not immediately call `a.length`?  
**Answer:** Only the local variable has been declared, and it has not been assigned a reference to an array; the compiler enforces *definite assignment*.

**C.** Is `int[] a = new int[0];` valid, and what is `a.length`?  
**Answer:** Valid, `a.length == 0`; however, there is no element `a[0]`.

**D.** After the snippet below, what is `a[1]`?

~~~java
int[] a = {3, 4};
int[] b = a;
b[1] = 8;
~~~

**Answer:** `8`, because `a` and `b` point to the same array.

**E.** Rewrite properly for assigning an array to an existing variable:

~~~java
int[] a;
a = new int[]{5, 6};
~~~

**Answer:** The snippet above is already valid. `a = {5,6};` is the invalid syntax.

**F.** With `String[] names = new String[2];`, are two new String objects created automatically?  
**Answer:** No. The array has two reference elements, each defaulting to `null`.

## 9. Checklist and conclusion

- [ ] Know that `int[] x;` **only declares an array reference**, without creating an object.
- [ ] Know that `new int[n]` creates an array object of length `n`.
- [ ] Use `int[]` instead of the misleading syntax `int a[]`.
- [ ] Understand the default values of newly created array elements.
- [ ] Distinguish an unassigned local variable, a `null` reference, and an empty array.
- [ ] Read `length` and access valid indices from 0 to `length-1`.
- [ ] Create arrays using the `{...}` initializer and `new int[]{...}` in the right contexts.
- [ ] Know that assigning `b = a` shares a reference rather than copying elements.
- [ ] Know that an array has a fixed length, and changing length requires creating a new array.
- [ ] Distinguish a negative-size error from an out-of-bounds index access error.
- [ ] Run `ArrayDeclarationNewDemo.java` on JDK 17+ and verify the exact stdout.

**Conclusion:** **Array declaration** creates a reference-typed variable; **`new ElementType[size]`** actually creates the array object with a fixed length and elements holding default values. Clearly understanding these two steps is the foundation for handling `null`, empty arrays, indices, and array copying in Java.