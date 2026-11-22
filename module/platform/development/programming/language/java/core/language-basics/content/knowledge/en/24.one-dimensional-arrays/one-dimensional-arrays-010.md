# Introducing `Arrays.toString()`, `Arrays.equals()`, and `Arrays.copyOf()`

> **Java core — language-basics / One-Dimensional Arrays**  
> **Environment:** Java 17+, JDK only.  
> **Goal:** Know how to **print contents**, **compare contents**, and **create array copies of a desired length**; avoid confusing `==` reference equality with content equality, empty arrays with `null`, and shallow copying with deep copying.

## 1. Three utilities in `java.util.Arrays`

~~~java
import java.util.Arrays;

int[] data = {2, 4, 6};

System.out.println(Arrays.toString(data));          // [2, 4, 6]
System.out.println(Arrays.equals(data, new int[] {2, 4, 6})); // true
int[] copy = Arrays.copyOf(data, 5);                 // [2, 4, 6, 0, 0]
~~~

| Method | Role | Return value |
| --- | --- | --- |
| `Arrays.toString(array)` | Formats elements of a one-dimensional array into a string | `String` |
| `Arrays.equals(a, b)` | Compares contents of two arrays in order | `boolean` |
| `Arrays.copyOf(original, newLength)` | Creates a **new array**, copies the prefix, and truncates or pads if needed | New array |

All three methods are `static`, called through the `Arrays` class. They do not mutate the source array object. Use `import java.util.Arrays;` or call `java.util.Arrays.toString(...)` explicitly.

## 2. `Arrays.toString()`: seeing the elements

~~~java
int[] values = {3, -1, 0};
String[] names = {"An", null, "Binh"};

System.out.println(Arrays.toString(values)); // [3, -1, 0]
System.out.println(Arrays.toString(names));  // [An, null, Binh]
System.out.println(Arrays.toString(new int[0])); // []
~~~

`System.out.println(values)` invokes the array's default object representation (usually looking like `[I@...`), and **does not** automatically print the numbers as a list. `Arrays.toString(values)` is convenient for debugging and writing verifiable output.

- For primitive arrays, elements are formatted according to their respective types.
- For reference arrays, displayed content depends on each element object's `toString()`; null elements render as `null`.
- For **multidimensional arrays**, `Arrays.toString(outer)` does not print nested sub-arrays deeply; use `Arrays.deepToString(outer)` when you want to see nested structures.

`Arrays.toString((int[]) null)` returns the **string `"null"`**, without throwing `NullPointerException`. This is merely how a null reference is formatted, not an indication that an array was created.

## 3. `Arrays.equals()` differs from the `==` operator

~~~java
int[] a = {1, 2};
int[] b = {1, 2};
int[] alias = a;

System.out.println(a == b);            // false: two distinct objects.
System.out.println(a == alias);        // true: same object.
System.out.println(Arrays.equals(a, b)); // true: elements are equal.
~~~

`Arrays.equals(a, b)` for primitive arrays compares corresponding elements in the same order; different lengths yield false. For reference arrays, the method uses the equality rules of the **elements**, including `equals`, rather than strictly comparing by reference.

~~~java
String[] x = {new String("Java")};
String[] y = {"Java"};
System.out.println(Arrays.equals(x, y)); // true: String.equals compares contents.
~~~

Conversely, objects that keep only the default `Object.equals` typically compare by identity:

~~~java
StringBuilder[] x = {new StringBuilder("A")};
StringBuilder[] y = {new StringBuilder("A")};
// Arrays.equals(x, y) is false: StringBuilder does not override equals by content.
~~~

This differs from **comparing nested arrays**: `Arrays.equals(int[][], int[][])` only compares sub-array references using each array's `equals`; to compare numbers inside nested arrays, use `Arrays.deepEquals(...)`.

## 4. `Arrays.copyOf()`: a new array, longer or shorter

~~~java
int[] original = {5, 7, 9};

int[] sameLength = Arrays.copyOf(original, original.length);
int[] longer = Arrays.copyOf(original, 5);   // [5, 7, 9, 0, 0]
int[] shorter = Arrays.copyOf(original, 2);  // [5, 7]
~~~

Rules:

1. Java creates a **new array** with length equal to `newLength`.
2. Copies the first `min(original.length, newLength)` elements, preserving order.
3. If extra slots are needed, each added slot is filled with **the component type's default value**: 0 for numbers, false for boolean, null for references.
4. If the new length is smaller, trailing elements of the source array are omitted from the new array.

~~~java
String[] colors = {"red", "blue"};
String[] padded = Arrays.copyOf(colors, 4);
// padded = [red, blue, null, null].
~~~

`Arrays.copyOf` does not change `original.length`. If you write `original = Arrays.copyOf(original, 5)`, the variable `original` will **point to the new array object**; any alias pointing to the old array still sees the old length.

A negative new length throws `NegativeArraySizeException`. A null source array throws `NullPointerException` when calling `copyOf`; validate inputs if your API permits null.

## 5. Independent copy at the array level, while element objects can still be shared

For `int[]` arrays, copying creates independent numeric slots:

~~~java
int[] a = {2, 4};
int[] copy = Arrays.copyOf(a, a.length);
copy[0] = 99;
// a = [2, 4]; copy = [99, 4]; a == copy is false.
~~~

For arrays of mutable objects, `copyOf` only **copies reference values** (*shallow copy*):

~~~java
StringBuilder[] source = {new StringBuilder("A")};
StringBuilder[] copy = Arrays.copyOf(source, source.length);

copy[0].append("!");
// source[0].toString() is also "A!".
copy[0] = new StringBuilder("B");
// source[0] still points to the original object "A!".
~~~

Multidimensional arrays in Java are **arrays containing references to sub-arrays**. Therefore, when copying the outer array, the inner sub-arrays are still shared:

~~~java
int[][] rows = {{1, 2}, {3}};
int[][] outerCopy = Arrays.copyOf(rows, rows.length);

outerCopy[0][0] = 99;
// rows[0][0] also equals 99.
~~~

To deep-copy two-dimensional data, you must create copies of each sub-array or use an appropriate object-copying approach. `Arrays.deepEquals` and `Arrays.deepToString` are for **deep comparison/display**, and do not create deep copies.

## 6. Empty arrays, `null`, and complexity

| Call | Result |
| --- | --- |
| `Arrays.toString(new int[0])` | `"[]"` |
| `Arrays.toString((int[]) null)` | `"null"` |
| `Arrays.equals(new int[0], new int[0])` | `true` |
| `Arrays.equals((int[]) null, (int[]) null)` | `true` |
| `Arrays.equals((int[]) null, new int[0])` | `false` |
| `Arrays.copyOf(new int[0], 3)` | New array `[0, 0, 0]` |
| `Arrays.copyOf((int[]) null, 3)` | `NullPointerException` |

`Arrays.equals(null, null)` simply means both references are null by the API's convention; **no** two array objects were created. When writing your own domain methods, you still must decide whether null is valid.

For an array of length `n`, `toString` reads elements to build the string, and `equals` may read up to `n` elements (or stop early on a mismatch). `copyOf` allocates memory for **a new array of length `newLength`** and copies the relevant slice. These are handy operations, though not free when data is very large.

## 7. Standalone Java 17+ example

Create the file **ArraysBasicsDemo.java**:

~~~java
import java.util.Arrays;

public final class ArraysBasicsDemo {
    public static void main(String[] args) {
        int[] numbers = {2, 4, 6};
        int[] sameValues = {2, 4, 6};
        System.out.println("initial=" + Arrays.toString(numbers));
        System.out.println("sameReference=" + (numbers == sameValues));
        System.out.println("sameContent=" + Arrays.equals(numbers, sameValues));

        int[] alias = numbers;
        alias[0] = 9;
        System.out.println("afterAlias=" + Arrays.toString(numbers));
        System.out.println("equalAfterAlias=" + Arrays.equals(numbers, sameValues));

        int[] copy = Arrays.copyOf(numbers, numbers.length);
        copy[1] = 40;
        System.out.println("originalAfterCopy=" + Arrays.toString(numbers));
        System.out.println("changedCopy=" + Arrays.toString(copy));
        System.out.println("copySameReference=" + (numbers == copy));

        System.out.println("longer="
                + Arrays.toString(Arrays.copyOf(numbers, 5)));
        System.out.println("shorter="
                + Arrays.toString(Arrays.copyOf(numbers, 2)));
        String[] words = {"red", "blue"};
        System.out.println("paddedReferences="
                + Arrays.toString(Arrays.copyOf(words, 4)));

        String[] firstWords = {new String("Java")};
        String[] secondWords = {"Java"};
        System.out.println("stringContentEqual="
                + Arrays.equals(firstWords, secondWords));

        StringBuilder[] buildersA = {new StringBuilder("A")};
        StringBuilder[] buildersB = {new StringBuilder("A")};
        System.out.println("builderContentEqual="
                + Arrays.equals(buildersA, buildersB));

        int[][] nestedA = {{1, 2}, {3}};
        int[][] nestedB = {{1, 2}, {3}};
        System.out.println("nestedShallowEqual="
                + Arrays.equals(nestedA, nestedB));
        System.out.println("nestedDeepEqual="
                + Arrays.deepEquals(nestedA, nestedB));
        System.out.println("nestedDeepText="
                + Arrays.deepToString(nestedA));

        int[][] outerCopy = Arrays.copyOf(nestedA, nestedA.length);
        outerCopy[0][0] = 99;
        System.out.println("nestedAfterCopy="
                + Arrays.deepToString(nestedA));
        System.out.println("outerSame=" + (nestedA == outerCopy));
        System.out.println("innerSame=" + (nestedA[0] == outerCopy[0]));

        String[] missing = null;
        System.out.println("nullText=" + Arrays.toString(missing));
        System.out.println("nullEqualsNull="
                + Arrays.equals(missing, (String[]) null));
        System.out.println("nullEqualsEmpty="
                + Arrays.equals(missing, new String[0]));
        System.out.println("emptyToThree="
                + Arrays.toString(Arrays.copyOf(new int[0], 3)));

        try {
            Arrays.copyOf(missing, 2);
        } catch (NullPointerException ex) {
            System.out.println("copyNull=NullPointerException");
        }
        try {
            Arrays.copyOf(numbers, -1);
        } catch (NegativeArraySizeException ex) {
            System.out.println("copyNegative=NegativeArraySizeException");
        }
    }
}
~~~

Compile/run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 ArraysBasicsDemo.java
java ArraysBasicsDemo
~~~

**Exact expected stdout:**

~~~text
initial=[2, 4, 6]
sameReference=false
sameContent=true
afterAlias=[9, 4, 6]
equalAfterAlias=false
originalAfterCopy=[9, 4, 6]
changedCopy=[9, 40, 6]
copySameReference=false
longer=[9, 4, 6, 0, 0]
shorter=[9, 4]
paddedReferences=[red, blue, null, null]
stringContentEqual=true
builderContentEqual=false
nestedShallowEqual=false
nestedDeepEqual=true
nestedDeepText=[[1, 2], [3]]
nestedAfterCopy=[[99, 2], [3]]
outerSame=false
innerSame=true
nullText=null
nullEqualsNull=true
nullEqualsEmpty=false
emptyToThree=[0, 0, 0]
copyNull=NullPointerException
copyNegative=NegativeArraySizeException
~~~

The lines `sameReference=false` yet `sameContent=true` prove that `==` differs from `Arrays.equals`. The two lines `nestedDeepEqual` and `nestedAfterCopy` show how deep comparison **differs** from shallow copying. The lines `copyNull` and `copyNegative` illustrate errors that need handling.

## 8. Common pitfalls and exercises

| Error / misconception | How to handle |
| --- | --- |
| Printing an array directly and thinking elements were printed | Use `Arrays.toString(array)` |
| Comparing two arrays with `==` to compare contents | Use `Arrays.equals(a, b)` |
| Using `Arrays.equals` on multidimensional arrays expecting to compare every number | Use `Arrays.deepEquals` |
| Using `Arrays.toString` to deeply print nested arrays | Use `Arrays.deepToString` |
| Thinking `copyOf` changes `length` of the original array | It creates a **new array** |
| Thinking `copyOf` deep-copies every object | It only copies elements/references |
| Calling `copyOf(null, n)` | Check for null first if that is possible |
| Using a negative `newLength` | Validate length, because runtime throws `NegativeArraySizeException` |

**Exercise 1.** Create two independent `int[] {1, 2, 3}` arrays. Compare them with `==` and `Arrays.equals`, then modify one element.

**Exercise 2.** From `int[] {4, 5}`, create one copy of length 4 and one of length 1. Predict the appended default values and the truncated element.

**Exercise 3.** Using `String[] {"A", "B"}`, call `Arrays.copyOf` with length 4 and explain why the two new slots are null rather than empty strings.

**Exercise 4.** Write a two-dimensional array whose sub-arrays are independent yet have equal contents; compare the results of `Arrays.equals` and `Arrays.deepEquals`.

**Exercise 5.** Copy a `StringBuilder[]` array using `copyOf`, then call `append` on an element of the copy. Why does the source also see the modified content?

### Key takeaways

**`Arrays.toString` to view contents; `Arrays.equals` to compare contents; `Arrays.copyOf` to create a new array.** `==` on two array variables only asks whether they refer to the same object. `copyOf` can truncate or pad with default values, yet it is a **shallow copy** for object references. For nested arrays, use `deepToString`/`deepEquals` if you need to inspect or compare elements deeply.