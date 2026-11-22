# Arrays Are Objects Holding a Fixed Number of Elements of the Same Component Type in Java

> **Java core — language-basics / One-Dimensional Arrays**  
> **Version:** Java 17+, single-file program, no libraries outside the JDK required.  
> **Goal:** Understand why an array is an **object** with a fixed length and a defined **runtime component type**; distinguish primitive arrays from reference arrays, and observe covariance and `ArrayStoreException`.

## 1. A one-dimensional array is an object

In Java, an `array` is an object used to store **a fixed number of slots**, each having the same **component type**.

~~~java
int[] scores = new int[3]; // An int array object with 3 slots.
scores[0] = 7;
scores[1] = 8;
scores[2] = 9;
~~~

- `int[]` is the **array type**, and `int` is the **component type**. `String[]` is similar, except its elements hold `String` references.
- `new int[3]` creates **an array object** with `length == 3`. The slots are indexed **0, 1, 2**.
- The variable `scores` holds a **reference** to the array object. That reference can be assigned to another variable, passed to a method, or set to `null`.
- Because an array is an object, it can be assigned to a variable of type `Object`. Arrays also implement `Cloneable` and `java.io.Serializable`.
- The number of slots of **the array object itself** cannot change after creation; however, the values stored in those slots can change.

An `int[]` only holds `int` values, whereas a `String[]` holds `null` or references to objects compatible with the `String` component type. A reference array whose component type is a superclass or interface can hold objects of different subclasses; it is not required that all elements have **the same runtime class**.

The next section focuses on **the component type and runtime type checking**. Declaring with `new`, index-based traversal, default values, empty arrays, and copying will be practiced in their respective lessons in this chapter.

## 2. Component type and runtime type checking

An array has an actual runtime type, even when referenced through `Object`:

~~~java
int[] values = {1, 2};
Object obj = values;

System.out.println(obj instanceof int[]);     // true
System.out.println(obj instanceof Object);    // true
System.out.println(obj instanceof Object[]);  // false
System.out.println(values.getClass().getComponentType().getTypeName()); // int
~~~

`int[]` is an object, yet it is **not an `Object[]`**, because the array's elements are primitive `int` values, not object references.

Reference arrays follow **covariance** rules: `String[]` can be used where `Object[]` is expected, while Java still protects the **actual** component type of the array object:

~~~java
String[] words = {"a", "b"};
Object[] objects = words; // Valid: covariance.
objects[0] = "X";         // Valid: String.
try {
    objects[1] = Integer.valueOf(42); // Not a String!
} catch (ArrayStoreException ex) {
    System.out.println("ArrayStoreException");
}
~~~

`objects` has static type `Object[]`, while the runtime array is still `String[]`. Assigning an `Integer` to this slot throws `ArrayStoreException` — this is a different error from `ArrayIndexOutOfBoundsException`.

**Same component type** means the slots conform to **the array object's component type**, not that every element has the exact same runtime class. For example, `Number[]` can hold both `Integer` and `Double`, because both are subtypes of `Number`.

## 3. Standalone Java 17+ program

Create the file **OneDimensionalArrayDemo.java**:

~~~java
import java.util.Arrays;

public final class OneDimensionalArrayDemo {
    public static void main(String[] args) {
        int[] numbers = new int[3];
        String[] names = new String[2];

        System.out.println("intDefaults=" + Arrays.toString(numbers));
        System.out.println("referenceDefaults=" + Arrays.toString(names));
        System.out.println("initialLength=" + numbers.length);

        numbers[0] = 7;
        numbers[2] = 9;
        System.out.println("changed=" + Arrays.toString(numbers));

        int[] empty = new int[0];
        System.out.println("emptyLength=" + empty.length);

        Object asObject = numbers;
        System.out.println("isObject=" + (asObject instanceof Object));
        System.out.println("componentType="
                + numbers.getClass().getComponentType().getTypeName());

        int[] alias = numbers;
        alias[1] = 5;
        System.out.println("aliasShares=" + (alias == numbers));
        System.out.println("afterAlias=" + Arrays.toString(numbers));

        int[] copied = numbers.clone();
        copied[0] = 100;
        System.out.println("afterCopyOriginal=" + Arrays.toString(numbers));
        System.out.println("afterCopyNew=" + Arrays.toString(copied));

        numbers = Arrays.copyOf(numbers, 5);
        System.out.println("resizedNewLength=" + numbers.length);
        System.out.println("resizedValues=" + Arrays.toString(numbers));
        System.out.println("oldAliasLength=" + alias.length);

        String[] words = {"a", "b"};
        Object[] refArray = words;
        refArray[0] = "X";
        System.out.println("referenceChanged=" + Arrays.toString(words));
        try {
            refArray[1] = Integer.valueOf(42);
        } catch (ArrayStoreException ex) {
            System.out.println("covariantStore=ArrayStoreException");
        }

        Object primitiveArray = new int[] {1, 2};
        System.out.println("primitiveObjectArray="
                + (primitiveArray instanceof Object[]));

        try {
            int invalid = numbers[5];
            System.out.println(invalid);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("badIndex=ArrayIndexOutOfBoundsException");
        }

        try {
            int[] negative = new int[-1];
            System.out.println(negative.length);
        } catch (NegativeArraySizeException ex) {
            System.out.println("negativeLength=NegativeArraySizeException");
        }

        int[] missing = null;
        try {
            System.out.println(missing.length);
        } catch (NullPointerException ex) {
            System.out.println("nullArray=NullPointerException");
        }
    }
}
~~~

In the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 OneDimensionalArrayDemo.java
java OneDimensionalArrayDemo
~~~

**Exact expected stdout:**

~~~text
intDefaults=[0, 0, 0]
referenceDefaults=[null, null]
initialLength=3
changed=[7, 0, 9]
emptyLength=0
isObject=true
componentType=int
aliasShares=true
afterAlias=[7, 5, 9]
afterCopyOriginal=[7, 5, 9]
afterCopyNew=[100, 5, 9]
resizedNewLength=5
resizedValues=[7, 5, 9, 0, 0]
oldAliasLength=3
referenceChanged=[X, b]
covariantStore=ArrayStoreException
primitiveObjectArray=false
badIndex=ArrayIndexOutOfBoundsException
negativeLength=NegativeArraySizeException
nullArray=NullPointerException
~~~

The lines `oldAliasLength=3` and `resizedNewLength=5` prove that a new array is created rather than changing the length of the old array. `covariantStore` demonstrates that the component type constraint is checked at runtime; `badIndex` and `negativeLength` are distinct errors.

## 4. Common pitfalls and exercises

| Misconception / error | Correct understanding or handling |
| --- | --- |
| Calling `array.length()` | Use the `array.length` field |
| Thinking indices start at 1 | Arrays start at index 0 |
| Assigning `array.length = n` | Invalid; create a new array if a different number of slots is needed |
| Using `array[array.length]` | Out of bounds; the last index is `array.length - 1` when non-empty |
| Equating an empty array with `null` | An empty array has `length == 0`; `null` refers to no object |
| Assigning an array to another variable and thinking it was copied | That only creates an alias; use `clone()` or `Arrays.copyOf` when a new array is needed |
| Thinking `int[]` is an `Object[]` | `int[]` is an `Object`, but its elements are primitives |
| Storing the wrong type through an `Object[]` alias pointing to a `String[]` | Throws `ArrayStoreException` at runtime |

**Exercise 1.** Create a `boolean[3]` array and a `String[2]` array, predict their default values, and then print them with `Arrays.toString`.

**Exercise 2.** Given `int[] a = {2, 4}; int[] b = a;`, change `b[0]` and explain why `a[0]` also changes. Then use `clone()` to create an independent array.

**Exercise 3.** Use `Arrays.copyOf` to expand an array from 2 to 4 elements, and explain the added values and the state of any old reference.

**Exercise 4.** Try `Number[] values = {Integer.valueOf(1), Double.valueOf(2.5)};`; why can two objects with different runtime classes reside in the same array?

**Exercise 5.** Create a `String[]`, assign it to an `Object[]`, and then try to store an `Integer`; predict the error. State how it differs from index errors and negative size errors.

### Key takeaways

**An array is an object whose component type and `length` are fixed at creation.** You can modify elements, but you cannot change the number of slots of the array object. A primitive array holds primitive values; a reference array holds `null` or objects compatible with its runtime component type. When you need to resize, create a new array; when sharing a reference, element changes can be seen through every alias.
