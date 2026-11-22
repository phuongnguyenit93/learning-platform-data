# Default Values of Fields and Array Elements in Java

> **Java core — language-basics / Variables and Constants**  
> **Requirement:** JDK 17 or later.  
> **Objective:** Know what values Java automatically provides for fields and array elements; distinguish `static`/instance fields, primitive/reference types, multidimensional arrays, and local variables; avoid confusing `null` with an allocated object.

## 1. Which Storage Locations Have Default Values?

Java automatically initializes the following storage locations according to their **declared type**:

- **Instance field:** each new object gets its own set of fields, initially receiving default values; field initializers and constructors may later change them.
- **Static field:** belongs to the class, receiving default values before running the corresponding class initializers and static initializers.
- **Array element:** as soon as a new array is allocated with `new`, every element that **actually exists** receives a default value. This rule holds even if the variable holding the array reference lives inside a method.

Example:

~~~java
class Account {
    int points;         // 0
    boolean active;     // false
    String owner;       // null
    static long total;  // 0L
}
~~~

There is no need to write `= 0` or `= null` for the fields above. However, default values are only the **initial state**; if an initializer or constructor reassigns them, the values seen after creating the object will differ.

## 2. Table of Default Values by Type

| Field / element type | Default value | Explanation |
| --- | --- | --- |
| `byte`, `short`, `int` | `0` | Integer zero |
| `long` | `0L` | Integer zero of type `long` |
| `float` | `0.0f` | Positive floating-point 0.0 |
| `double` | `0.0d` | Positive floating-point 0.0 |
| `char` | `'\u0000'` | UTF-16 code 0 (NUL), **not** the character `'0'` or a space |
| `boolean` | `false` | Boolean false |
| Any **reference type** | `null` | No object referenced yet |

Reference types include `String`, other classes, interfaces, and **array types themselves** such as `int[]`. Thus `String[]` contains default elements of `null`, not automatically created `""`. `Integer[]` contains `null`, and does **not** automatically create `Integer.valueOf(0)` wrappers.

When printing the default `char` directly, it is hard to observe because it is NUL. Cast it to `int` to see code **0**: `System.out.println((int) character);`.

## 3. Standalone Java 17+ Program

Create the file **DefaultValuesDemo.java**:

~~~java
import java.util.Arrays;

public class DefaultValuesDemo {
    static int sharedCount;
    static boolean enabled;

    int quantity;
    double price;
    char initial;
    String label;

    public static void main(String[] args) {
        DefaultValuesDemo first = new DefaultValuesDemo();
        DefaultValuesDemo second = new DefaultValuesDemo();

        int[] scores = new int[3];
        boolean[] flags = new boolean[2];
        char[] letters = new char[1];
        String[] names = new String[2];
        Integer[] wrappers = new Integer[1];

        int[][] partial = new int[2][];
        int[][] complete = new int[2][3];

        System.out.println("static=" + sharedCount + "," + enabled);
        System.out.println("instance=" + first.quantity + ","
                + first.price + "," + (int) first.initial + ","
                + first.label);
        System.out.println("scores=" + Arrays.toString(scores));
        System.out.println("flags=" + Arrays.toString(flags));
        System.out.println("charCode=" + (int) letters[0]);
        System.out.println("names=" + Arrays.toString(names));
        System.out.println("wrapper=" + wrappers[0]);
        System.out.println("partialRow=" + partial[0]);
        System.out.println("completeRow="
                + Arrays.toString(complete[0]));

        first.quantity = 7;
        scores[0] = 9;
        System.out.println("objects=" + first.quantity + ","
                + second.quantity);
        System.out.println("scoresAfter=" + Arrays.toString(scores));
    }
}
~~~

Open a terminal in the directory containing the file and run (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 DefaultValuesDemo.java
java DefaultValuesDemo
~~~

**Expected output:**

~~~text
static=0,false
instance=0,0.0,0,null
scores=[0, 0, 0]
flags=[false, false]
charCode=0
names=[null, null]
wrapper=null
partialRow=null
completeRow=[0, 0, 0]
objects=7,0
scoresAfter=[9, 0, 0]
~~~

Explanation: `static` fields have values `0`/`false`; each new `DefaultValuesDemo` object has field `quantity` equal to `0`, `price` equal to `0.0`, `initial` equal to NUL, and `label` equal to `null`. New primitive arrays have elements `0`/`false`/NUL, while `String` and `Integer` arrays have `null` elements.

After `first.quantity = 7`, the `second` object still keeps `quantity = 0`: each object has its own instance fields. After `scores[0] = 9`, the remaining two positions of the array are still `0`.

## 4. Multidimensional Arrays: Only Allocated Arrays Are Initialized

Distinguish:

~~~java
int[][] partial = new int[2][];
int[][] complete = new int[2][3];
~~~

- `partial` is an **outer array of two `int[]` references**; those two references default to `null` because the inner row arrays have not been allocated yet. Hence `partial[0]` is `null`.
- `complete` has allocated the outer array and two `int[3]` inner rows. All six integer elements default to **0**.
- Running `partial[0][0]` before assigning `partial[0] = new int[3];` will throw a `NullPointerException`.

Do not confuse `new int[0]` with a `null` array: `new int[0]` is a valid array object **of length 0**, just with no elements whose default values could be read.

## 5. Local Variables Do NOT Have Readable Default Values

This is an important exception for beginners. Local variables inside a method must be **definitely assigned before being read** (*definite assignment*):

~~~java
void example() {
    int count;
    // System.out.println(count); // Compile error if uncommented.
    count = 3;
    System.out.println(count); // 3
}
~~~

There is no rule that "an unassigned local `int` variable reads as `0`". The compiler will report something like `variable count might not have been initialized`.

However, **an array created from a local variable** still gets default values assigned to each element:

~~~java
int[] values = new int[2];
System.out.println(values[0]); // 0
~~~

Here the local variable `values` has been assigned a reference to the new array; while `values[0]` receives the default value `0` from array allocation. The two rules do not contradict each other.

## 6. Explicit Initialization and `final`

With field initializers/constructors, the final value after creating an object can differ from the default:

~~~java
class Ticket {
    int count = 5;

    Ticket() {
        count = 8;
    }
}
~~~

When reading `new Ticket().count` after the constructor, the value is **8**. Prior to explicit assignments, default initialization had set `0`.

An uninitialized `final` field (blank final) must still be assigned according to appropriate *definite assignment* rules, such as inside the constructor:

~~~java
class Product {
    final int id;

    Product(int id) {
        this.id = id;
    }
}
~~~

`final` prevents reassigning the field after valid initialization, but it does not make an object held through a `final` reference immutable. Nor does it cause array elements to take on values other than their defaults.

## 7. Common Pitfalls and Practice

| Situation | Correct understanding |
| --- | --- |
| `String[] a = new String[2];` | Elements are **`null`**, not `""` |
| `Integer[] a = new Integer[2];` | Elements are `null`; unboxing `a[0]` to `int` throws `NullPointerException` |
| `int[] a = new int[2];` | Two zeros (`0`) |
| `int[][] a = new int[2][];` | Two unallocated rows, both `null` |
| `int[][] a = new int[2][3];` | Two allocated rows, six zeros (`0`) |
| Default `char` | NUL with code `0`, not the printable character `'0'` |
| `String label;` as a field | `null`; calling `label.length()` before assigning an object can throw `NullPointerException` |

**Exercise 1:** Create a class with unassigned `byte`, `float`, `char`, `boolean`, and `String` fields. Print their values; for `char`, cast to `int` to confirm code `0`.

**Exercise 2:** Print `Arrays.toString(new String[3])`. Then assign the second element to `"Java"` and print again: which elements are still `null`?

**Exercise 3:** Create `int[][] rows = new int[2][];`. Predict `rows[0]`; then assign `rows[0] = new int[2];` and print `rows[0][0]`.

**Exercise 4:** Explain why `int local; System.out.println(local);` does not compile, whereas `int[] array = new int[1]; System.out.println(array[0]);` prints `0`.

### Takeaway

**Fields and array elements** have default values based on type: primitives receive `0`/`0.0`/`false`/NUL accordingly; references receive `null`. **Local variables must be definitely assigned before being read.** Assignments in initializers, constructors, and after allocation can change the default values.
