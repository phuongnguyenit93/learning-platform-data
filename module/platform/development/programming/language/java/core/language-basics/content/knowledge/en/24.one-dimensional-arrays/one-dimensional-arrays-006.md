# Empty Arrays Differ from `null` Array References in Java

> **Java core — language-basics / One-Dimensional Arrays**  
> **Environment:** JDK 17+, a self-contained Java file using only the standard library.  
> **Goal:** Distinguish an array with `length == 0` from a reference not pointing to any array (`null`), predict behavior when reading `length`, accessing elements, or iterating with `for-each`, and design clear null/empty handling.

## 1. Two completely different states

~~~java
int[] empty = new int[0]; // Has an array object; length = 0.
int[] alsoEmpty = {};     // Another empty array object.
int[] missing = null;     // Points to no array object.

System.out.println(empty.length);    // 0
System.out.println(missing == null);  // true
~~~

An **empty array** exists in memory, has a concrete array type, and has a `length` property equal to 0. A **null array reference** does not point to any object; it has no `length` property to access.

This is not a difference in **element values**: an empty array has **no elements at all**. The array `new int[2]` has two elements equal to 0, and `new String[2]` has two elements equal to `null` — both are **non-empty**.

| Aspect | Empty array `new int[0]` | Reference `int[] a = null` |
| --- | --- | --- |
| Has an array object? | Yes | No |
| `a == null` | `false` | `true` |
| `a.length` | `0` | Throws `NullPointerException` |
| Iterating `for (int x : a)` | 0 iterations, no error | Throws `NullPointerException` |
| Reading `a[0]` | `ArrayIndexOutOfBoundsException` | `NullPointerException` |
| `a instanceof int[]` | `true` | `false` |

Declaring `int[] data;` makes an **unassigned** local variable, which differs from `int[] data = null;`. Java does not allow reading an uninitialized local variable.

## 2. How to create an empty array and fixed length

You can create an empty array in several ways:

~~~java
int[] first = new int[0];
int[] second = {};
int[] third = new int[] {};
String[] names = {};
~~~

Each time an array creation expression executes, **a new array object** is created. Objects can have the same length and contents without necessarily sharing the same reference:

~~~java
int[] a = {};
int[] b = {};
System.out.println(a == b);                     // false
System.out.println(java.util.Arrays.equals(a,b)); // true
~~~

`a == b` compares **references**; `Arrays.equals(a, b)` compares **elements** (two empty arrays with the same component type have equal contents under the appropriate comparison).

Array length is fixed. To go from an empty array to an array with two elements, you must create a new array and reassign the reference variable:

~~~java
int[] data = {};
data = new int[] {5, 7}; // data points to a different object, length = 2.
~~~

This does not "expand" the original empty object. If another variable was referencing the old empty object, it still points to the array of length 0.

## 3. `length`, indices, and two types of exceptions

For a valid array with `n` elements, valid indices are from `0` to `n - 1`. When `n = 0`, **there are no valid indices**:

~~~java
int[] empty = new int[0];
System.out.println(empty.length); // 0
// int x = empty[0]; // At runtime: ArrayIndexOutOfBoundsException.
~~~

With a `null` reference, any operation that needs to access the object will fail:

~~~java
int[] missing = null;
// int size = missing.length; // At runtime: NullPointerException.
// int x = missing[0];        // At runtime: NullPointerException.
~~~

Reading `empty.length` is valid because the object exists; reading `missing.length` is impossible. `ArrayIndexOutOfBoundsException` occurs when **an array already exists** but the index is out of range; `NullPointerException` occurs when attempting to access through a **null reference**.

Java does not automatically convert `null` into an empty array, nor does it make `a[0]` equal 0 when the array has no elements.

## 4. `for-each` traversal and safe accumulation

~~~java
static long sum(int[] values) {
    long total = 0;
    for (int value : values) {
        total += value;
    }
    return total;
}
~~~

If an empty array is passed, the `for-each` body runs **0 times** and the method returns `0`. If `null` is passed, the `for-each` loop attempts to retrieve the data source to iterate and throws `NullPointerException`.

For data that may be null, decide the **method contract**:

**Approach A — null is an invalid input (strict):**

~~~java
static long strictSum(int[] values) {
    java.util.Objects.requireNonNull(values, "values");
    long sum = 0;
    for (int value : values) {
        sum += value;
    }
    return sum;
}
~~~

**Approach B — null is treated as having no elements (intentional):**

~~~java
static long sumOrZero(int[] values) {
    if (values == null) {
        return 0;
    }
    long sum = 0;
    for (int value : values) {
        sum += value;
    }
    return sum;
}
~~~

The two choices have different semantics: *strict* catches contract violations early; *null-as-empty* can be convenient for optional data, yet it can also mask upstream bugs. **Do not silently turn null into an empty array** if the domain distinguishes "data not present" from "data present but empty."

## 5. Distinguishing three states: null, empty, non-empty

When you need to return different statuses, check for null **first**:

~~~java
static String classify(int[] values) {
    if (values == null) {
        return "NULL";
    }
    if (values.length == 0) {
        return "EMPTY";
    }
    return "NON_EMPTY:" + values.length;
}
~~~

This order both avoids `NullPointerException` and preserves clear state semantics:

| Input | Return value |
| --- | --- |
| `null` | `"NULL"` |
| `new int[0]` | `"EMPTY"` |
| `new int[] {0}` | `"NON_EMPTY:1"` |
| `new int[] {4, 5}` | `"NON_EMPTY:2"` |

If you only need to sum or count, the null-as-empty policy may suffice. If the application needs to distinguish data not yet loaded from data that was loaded with zero items, keep the two states separate.

## 6. `Arrays.toString`, copying, and arrays containing `null` elements

`java.util.Arrays.toString(...)` is useful for printing array contents and **handles a null array reference**:

~~~java
int[] empty = {};
int[] missing = null;
System.out.println(java.util.Arrays.toString(empty));   // []
System.out.println(java.util.Arrays.toString(missing)); // null
~~~

The second line prints the literal text `null`, which **does not mean an array was created**. That is the behavior of the formatting method, not of `missing.length`.

A reference array can hold `null` values in its existing slots:

~~~java
String[] slots = new String[2];
System.out.println(java.util.Arrays.toString(slots)); // [null, null]
System.out.println(slots.length); // 2.
~~~

`slots` is not empty even though each element is null. `slots[0] == null` checks the first element; `slots == null` checks the **array reference** itself.

You can `clone()` an empty array to create **another** empty array. Trying to call `missing.clone()` when `missing == null` throws `NullPointerException`.

## 7. Standalone Java 17+ program

Create the file **EmptyVsNullArrayDemo.java**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public final class EmptyVsNullArrayDemo {
    private static String classify(int[] values) {
        if (values == null) {
            return "NULL";
        }
        if (values.length == 0) {
            return "EMPTY";
        }
        return "NON_EMPTY:" + values.length;
    }

    private static long strictSum(int[] values) {
        Objects.requireNonNull(values, "values");
        long sum = 0;
        for (int value : values) {
            sum += value;
        }
        return sum;
    }

    private static long sumOrZero(int[] values) {
        if (values == null) {
            return 0;
        }
        long sum = 0;
        for (int value : values) {
            sum += value;
        }
        return sum;
    }

    public static void main(String[] args) {
        int[] empty = new int[0];
        int[] anotherEmpty = {};
        int[] missing = null;
        int[] oneZero = {0};
        String[] references = new String[2];

        System.out.println("emptyNull=" + (empty == null));
        System.out.println("missingNull=" + (missing == null));
        System.out.println("emptyLength=" + empty.length);
        System.out.println("emptyIsArray=" + (empty instanceof int[]));
        System.out.println("missingIsArray=" + (missing instanceof int[]));
        System.out.println("differentObjects=" + (empty != anotherEmpty));
        System.out.println("equalContents="
                + Arrays.equals(empty, anotherEmpty));

        System.out.println("classNull=" + classify(missing));
        System.out.println("classEmpty=" + classify(empty));
        System.out.println("classZero=" + classify(oneZero));
        System.out.println("classTwo="
                + classify(new int[] {4, 5}));

        System.out.println("emptyText=" + Arrays.toString(empty));
        System.out.println("missingText=" + Arrays.toString(missing));
        System.out.println("nullElements="
                + Arrays.toString(references));
        System.out.println("referenceLength=" + references.length);

        System.out.println("strictEmpty=" + strictSum(empty));
        System.out.println("strictValues="
                + strictSum(new int[] {3, 5}));
        System.out.println("nullAsEmpty=" + sumOrZero(missing));

        int visits = 0;
        for (int value : empty) {
            visits++;
        }
        System.out.println("emptyVisits=" + visits);

        try {
            int ignored = empty[0];
            System.out.println(ignored);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("emptyIndex=ArrayIndexOutOfBoundsException");
        }

        try {
            System.out.println(missing.length);
        } catch (NullPointerException ex) {
            System.out.println("missingLength=NullPointerException");
        }

        try {
            strictSum(missing);
        } catch (NullPointerException ex) {
            System.out.println("strictMissing=NullPointerException");
        }

        int[] alias = empty;
        empty = new int[] {9, 10};
        System.out.println("newLength=" + empty.length);
        System.out.println("oldAliasLength=" + alias.length);
    }
}
~~~

Compile and run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 EmptyVsNullArrayDemo.java
java EmptyVsNullArrayDemo
~~~

**Exact expected stdout:**

~~~text
emptyNull=false
missingNull=true
emptyLength=0
emptyIsArray=true
missingIsArray=false
differentObjects=true
equalContents=true
classNull=NULL
classEmpty=EMPTY
classZero=NON_EMPTY:1
classTwo=NON_EMPTY:2
emptyText=[]
missingText=null
nullElements=[null, null]
referenceLength=2
strictEmpty=0
strictValues=8
nullAsEmpty=0
emptyVisits=0
emptyIndex=ArrayIndexOutOfBoundsException
missingLength=NullPointerException
strictMissing=NullPointerException
newLength=2
oldAliasLength=0
~~~

`differentObjects=true` illustrates that two empty arrays can have different references; `nullElements` shows that an array of length 2 can still contain null elements. `emptyIndex` and `missingLength` clearly distinguish the two exceptions; `oldAliasLength=0` proves that reassigning a variable to another array does not mutate the old array.

## 8. Common pitfalls and exercises

| Misconception / error | Correct understanding |
| --- | --- |
| `new int[0] == null` | False: an empty array is still an object |
| Can access `missing.length` | False: a null reference causes `NullPointerException` |
| `empty[0]` has default value 0 | False: element 0 does not exist; access is out of bounds |
| `new String[2]` is an empty array because all elements are null | False: it has two elements, `length == 2` |
| `for-each` on null skips like on an empty array | False: null causes `NullPointerException` |
| `Arrays.toString(nullArray)` prints `null` so an array was created | False: that is only the formatted string for a null reference |
| Always replace null with empty | Only when the business contract allows it |

**Exercise 1.** Create `int[] a = new int[0]` and `int[] b = null`. Predict `a == null`, `b == null`, `a.length`, and `b.length`.

**Exercise 2.** Compare `new int[0]`, `new int[1]`, and `new String[2]` in terms of `length` and default values.

**Exercise 3.** Write a method returning `"NULL"`, `"EMPTY"`, or `"NON_EMPTY"` to distinguish the three states without causing an NPE.

**Exercise 4.** Choose a contract for a sum method: reject null or treat null as having no elements? Write both, and explain why the empty result is 0.

**Exercise 5.** Assign an empty array reference to a variable `alias`, then reassign the original variable to `new int[] {1, 2, 3}`; explain why `alias.length` is still 0.

### Key takeaways

**An empty array is a valid object with `length == 0`; a `null` reference points to no array object.** A `for-each` loop on an empty array performs 0 iterations, whereas on null it causes an NPE. An empty array has no index 0. In APIs, explicitly decide when null is allowed, rather than accidentally equating "no data" with "present but empty data."