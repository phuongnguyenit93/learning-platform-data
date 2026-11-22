# Default Values of Primitive and Reference Elements in Java Arrays

> **Java core — language-basics / One-Dimensional Arrays**  
> **Applies to:** Java 17+ (JDK); a standalone program run with `javac`/`java`.  
> **Goal:** Know the exact value each element receives after `new Type[length]`; distinguish primitive-type arrays from reference-type arrays; recognize `null`, explicitly unassigned elements, and uninitialized local variables.

## 1. When creating an array, elements are initialized automatically

A Java array is a **fixed-length object** containing elements of the same component type. When an array is created with `new` and a length, every element is initialized to **the default value of its component type** before the program reads it:

~~~java
int[] numbers = new int[3];
System.out.println(numbers.length); // 3
System.out.println(numbers[0]);     // 0
System.out.println(numbers[1]);     // 0
System.out.println(numbers[2]);     // 0
~~~

The statement `new int[3]` creates three elements indexed `0`, `1`, and `2`. There is no need to write a loop to assign each element to 0. This is a **guarantee of the Java language**, not accidental memory behavior.

**Note:** Default values depend on **the element type**, not on the array name, variable name, or the data type you plan to assign later. Using `new` here creates a new array; declaring an array reference variable **without creating an array yet** is a different situation.

## 2. Default value table for the eight primitive types

If the array's component type is a *primitive* type, each element initially has the following value:

| Element type | Creation example | Default value of each element |
| --- | --- | --- |
| `byte` | `new byte[2]` | `0` |
| `short` | `new short[2]` | `0` |
| `int` | `new int[2]` | `0` |
| `long` | `new long[2]` | `0L` (the number 0 of type `long`) |
| `float` | `new float[2]` | `0.0f` (positive zero) |
| `double` | `new double[2]` | `0.0d` (positive zero) |
| `char` | `new char[2]` | character with Unicode code **0**, usually written as `'\0'` |
| `boolean` | `new boolean[2]` | `false` |

The notations `0L`, `0.0f`, `0.0d` describe **the value and type**, not text strings stored in the array. The default floating-point 0.0 values are **positive zero** (`+0.0`), not `NaN`.

~~~java
long[] counts = new long[2];
boolean[] flags = new boolean[2];
char[] letters = new char[2];

System.out.println(counts[0] == 0L);   // true
System.out.println(flags[0]);          // false
System.out.println((int) letters[0]);  // 0
System.out.println(letters[0] == '\0'); // true
~~~

**Specifically for `char`:** the default is the NUL character with code 0, **not** the digit character `'0'` (Unicode code 48), **not** a space (code 32), and **not** the word `null`. If you print the NUL character directly, human eyes may see nothing; cast with `(int) letters[0]` to observe the code value.

`boolean[]` receives `false`; `false` is not equivalent to integer 0, and Java does not allow converting directly between `boolean` and `int` as some other languages do.

## 3. Reference-type arrays: each element defaults to `null`

When the component type is a **reference** type such as `String`, `Integer`, or a user-defined class, the default value of each element is `null`:

~~~java
String[] names = new String[3];
Integer[] scores = new Integer[2];

System.out.println(names[0] == null);  // true
System.out.println(scores[0] == null); // true
~~~

This means:

- **The array itself** `names` exists because `new String[3]` was executed, so `names.length` is 3.
- However, each **reference element** such as `names[0]` remains `null` until an appropriate reference is assigned.
- `new String[3]` **does not automatically create three empty `String` objects**, nor does it set the elements to `""`.
- `new Student[2]` **does not automatically call the `Student` constructor twice**; it creates an array holding two `null` references.

Example of the difference between primitive types and *wrapper* classes:

~~~java
int[] primitive = new int[2];
Integer[] boxed = new Integer[2];
boolean[] primitiveFlags = new boolean[2];
Boolean[] boxedFlags = new Boolean[2];

System.out.println(primitive[0]);        // 0
System.out.println(boxed[0]);            // null
System.out.println(primitiveFlags[0]);   // false
System.out.println(boxedFlags[0]);       // null
~~~

`Integer` and `Boolean` are **reference classes**, not `int` and `boolean`. Therefore, you must not assume an `Integer[]` element defaults to 0 or a `Boolean[]` element defaults to `false`.

If you try to *unbox* a `null` element of `Integer[]` into an `int`, Java throws `NullPointerException`.

## 4. Reading, assigning elements, and handling `null` properly

After creating an array, its elements already have default values and can be **read** immediately if the index is valid:

~~~java
String[] words = new String[3];
System.out.println(words[0]); // Prints the text null.

words[1] = "Java";
words[2] = "";
System.out.println(words[1].length()); // 4
System.out.println(words[2].length()); // 0
~~~

`null` and the empty string `""` are different: the empty string is **a `String` object of length 0**, whereas `null` indicates that no object is referenced.

Reading `words[0]` directly or comparing `words[0] == null` is valid. However, calling an instance method such as `words[0].length()` when that element is `null` causes `NullPointerException`.

~~~java
static int safeLength(String[] words, int index) {
    String value = words[index]; // Requires words non-null and index valid.
    return value == null ? -1 : value.length();
}
~~~

The method `safeLength` returns `-1` to represent a `null` element according to the example's contract; it **does not** handle a `null` `words` array or an out-of-range index. In an application, clearly define how `null`, empty strings, and index errors should be distinguished.

**Explicit assignment** replaces the default at that slot:

~~~java
int[] numbers = new int[3];       // [0, 0, 0]
numbers[1] = 7;                   // [0, 7, 0]

String[] words = new String[3];   // [null, null, null]
words[1] = "Java";                // [null, Java, null]
~~~

Assigning `numbers[1]` does not change `numbers[0]` or `numbers[2]`. Elements that have not been explicitly assigned continue to hold their default values until modified.

## 5. List initialization, `Arrays.fill`, and empty arrays

If all values are known at creation time, you can initialize using a **list**:

~~~java
int[] points = {4, 5, 6};
String[] labels = {"A", null, "C"};
~~~

Here the elements receive **the values from the list** in order, rather than remaining only default values. The alternative valid syntax in expressions is `new int[] {4, 5, 6}`.

If you want every element to have **the same non-default value**, you can use `java.util.Arrays.fill`:

~~~java
int[] offsets = new int[3]; // Initially [0, 0, 0].
java.util.Arrays.fill(offsets, -1);
// Now [-1, -1, -1].
~~~

`Arrays.fill` is an assignment operation performed **after the array is created**; it does not change Java's default value rules.

**A zero-length array** is also a valid array object:

~~~java
int[] empty = new int[0];
System.out.println(empty.length);  // 0
System.out.println(empty == null); // false
// System.out.println(empty[0]);    // At runtime: ArrayIndexOutOfBoundsException.
~~~

A zero-length array **has no elements**, so there is no default value to read at index 0; this differs from an array reference variable equal to `null`.

## 6. Do not confuse array elements with uninitialized local variables

This is an important distinction in Java:

~~~java
static void valid() {
    int[] data = new int[2]; // The data variable is assigned a new array reference.
    System.out.println(data[0]); // 0: the array element already has a default.
}
~~~

In contrast, a **local variable** is not automatically assigned a default value so that it can be read immediately:

~~~java
// DOES NOT COMPILE if uncommented:
// static void invalid() {
//     int number;
//     System.out.println(number); // Local variable has not been assigned.
//
//     String[] names;
//     System.out.println(names);  // Local variable names has not been assigned.
// }
~~~

Pay attention to the two levels:

| Situation | Has a value to read immediately? | Explanation |
| --- | --- | --- |
| `int[] data = new int[2]; data[0]` | Yes: `0` | Array elements are defaulted |
| `String[] data = new String[2]; data[0]` | Yes: `null` | Element is a reference |
| `int n;` inside a method, read `n` immediately | No | Local variable has not achieved *definite assignment* |
| `int[] data;` inside a method, read `data` immediately | No | Local reference variable has not been assigned |
| `int[] data = null; data.length` | Does not succeed at runtime | `data` is assigned `null`; accessing `length` causes `NullPointerException` |
| Field `int number;` in an object | Yes: `0` | Fields also have default values |
| Field `String text;` in an object | Yes: `null` | Reference fields default to `null` |

**Scope** only determines where a name can be used; **definite assignment** determines whether a local variable has definitely been assigned before being read. The default value of **an element in a created array** cannot be used to justify reading an **uninitialized local variable**.

## 7. Standalone Java 17+ program and exact stdout

Create the file **ArrayDefaultValuesDemo.java**:

~~~java
import java.util.Arrays;

public final class ArrayDefaultValuesDemo {
    private static final class Student {
        private final String name;

        Student(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }
    }

    public static void main(String[] args) {
        byte[] bytes = new byte[2];
        short[] shorts = new short[2];
        int[] integers = new int[3];
        long[] longs = new long[2];
        float[] floats = new float[2];
        double[] doubles = new double[2];
        char[] chars = new char[2];
        boolean[] flags = new boolean[2];

        System.out.println("byte=" + Arrays.toString(bytes));
        System.out.println("short=" + Arrays.toString(shorts));
        System.out.println("int=" + Arrays.toString(integers));
        System.out.println("long=" + Arrays.toString(longs));
        System.out.println("float=" + Arrays.toString(floats));
        System.out.println("double=" + Arrays.toString(doubles));
        System.out.println("boolean=" + Arrays.toString(flags));
        System.out.println("charCodes=" + (int) chars[0] + "," + (int) chars[1]);
        System.out.println("charIsNul=" + (chars[0] == '\0'));

        String[] words = new String[3];
        Integer[] boxed = new Integer[2];
        Boolean[] boxedFlags = new Boolean[2];
        Student[] students = new Student[2];

        System.out.println("wordsInitial=" + Arrays.toString(words));
        System.out.println("boxedInitial=" + Arrays.toString(boxed));
        System.out.println("boxedFlagsInitial=" + Arrays.toString(boxedFlags));
        System.out.println("studentsInitial=" + Arrays.toString(students));
        System.out.println("arrayExists=" + (words != null));
        System.out.println("firstWordNull=" + (words[0] == null));

        integers[1] = 7;
        words[1] = "Java";
        boxed[0] = 42;
        students[0] = new Student("Lan");

        System.out.println("intAfter=" + Arrays.toString(integers));
        System.out.println("wordsAfter=" + Arrays.toString(words));
        System.out.println("boxedAfter=" + Arrays.toString(boxed));
        System.out.println("firstStudent=" + students[0].name());
        System.out.println("secondStudentNull=" + (students[1] == null));

        int[] filled = new int[3];
        Arrays.fill(filled, -1);
        System.out.println("filled=" + Arrays.toString(filled));

        int[] explicit = {4, 5};
        System.out.println("explicit=" + Arrays.toString(explicit));

        int[] empty = new int[0];
        System.out.println("emptyLength=" + empty.length);
        System.out.println("emptyIsNull=" + (empty == null));

        try {
            System.out.println("badLength=" + words[0].length());
        } catch (NullPointerException ex) {
            System.out.println("nullElement=NullPointerException");
        }

        try {
            System.out.println("badIndex=" + empty[0]);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("emptyIndex=ArrayIndexOutOfBoundsException");
        }

        int[] missing = null;
        System.out.println("missingArrayNull=" + (missing == null));
    }
}
~~~

Compile and run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 ArrayDefaultValuesDemo.java
java ArrayDefaultValuesDemo
~~~

**Exact expected stdout:**

~~~text
byte=[0, 0]
short=[0, 0]
int=[0, 0, 0]
long=[0, 0]
float=[0.0, 0.0]
double=[0.0, 0.0]
boolean=[false, false]
charCodes=0,0
charIsNul=true
wordsInitial=[null, null, null]
boxedInitial=[null, null]
boxedFlagsInitial=[null, null]
studentsInitial=[null, null]
arrayExists=true
firstWordNull=true
intAfter=[0, 7, 0]
wordsAfter=[null, Java, null]
boxedAfter=[42, null]
firstStudent=Lan
secondStudentNull=true
filled=[-1, -1, -1]
explicit=[4, 5]
emptyLength=0
emptyIsNull=false
nullElement=NullPointerException
emptyIndex=ArrayIndexOutOfBoundsException
missingArrayNull=true
~~~

The example uses `Arrays.toString(...)` to clearly view the elements. Specifically, `char[]` is printed as **numeric codes** so that the NUL character is not mistaken for an empty string. `Student[]` starts with two `null` values; only when `new Student("Lan")` is assigned at position 0 does a `Student` object appear.

The two `catch` blocks have fixed output demonstrating **accessing a null element** and **an index error on an empty array**, without depending on the JVM's exception message text.

## 8. Common pitfalls, verification, and exercises

| Misconception or error | Correct understanding |
| --- | --- |
| `new String[3]` creates 3 empty strings | False: it creates 3 `null` reference elements |
| `new Integer[3]` creates 3 integers equal to 0 | False: `Integer` is a class, so elements are `null` |
| `new boolean[2]` contains `null` | False: `boolean` is primitive, defaulting to `false` |
| `new char[2]` contains the character `'0'` | False: it defaults to the NUL character with code 0 |
| Accessing a `null` element via `.length()` | Can cause `NullPointerException` |
| A new array of length 0 equals `null` | False: it is still an object, just with no elements |
| Local `int number;` automatically defaults to 0 | False: it must be assigned before reading |
| `new Student[2]` calls the constructor for each `Student` | False: it only creates an array of references, without creating each object |
| Need a non-default initial value for every element | Use a loop, an initializer list, or `Arrays.fill` as appropriate |
| Reading `data[0]` when `data == null` | There is no array to index; causes `NullPointerException` |

**Exercise 1.** Create `double[] temperatures = new double[4]`, print each element, and explain why they are `0.0`.

**Exercise 2.** Create `char[] symbols = new char[3]`, print `(int) symbols[0]`, and compare `symbols[0] == '0'` with `symbols[0] == '\0'`.

**Exercise 3.** Create `Integer[] ids = new Integer[2]` and `int[] indexes = new int[2]`. Predict `ids[0]` and `indexes[0]`; try assigning `ids[0] = 9` and printing again.

**Exercise 4.** Create a `Book` class with a constructor taking a title; declare `Book[] books = new Book[2]`. Why can `books[0].title()` not be called before `books[0] = new Book("Java")`?

**Exercise 5.** Compare `int[] a = new int[0]`, `int[] b = null`, and `int[] c = new int[1]` in terms of `length`, `== null`, and whether `[0]` can be read.

**Exercise 6.** Create `int[] values = new int[5]`, use `Arrays.fill(values, -1)`, and then update only `values[2] = 10`. Predict the entire array.

### Key takeaways

**Every element of an array newly created with `new Type[length]` has a default value according to its component type:** integer types are 0, floating-point types are +0.0, `char` is NUL (code 0), `boolean` is `false`, and **all reference types are `null`**. The default of an **array element** is not an automatic assignment rule for **uninitialized local variables**. To have an object at a reference element, you must assign a suitable object reference.