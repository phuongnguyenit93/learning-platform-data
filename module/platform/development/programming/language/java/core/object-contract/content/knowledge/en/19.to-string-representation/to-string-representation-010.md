# `Arrays.toString()`, `Arrays.deepToString()`, and Representing Nested Components

When logging or displaying an object with an array field, many developers try `System.out.println(array)` or concatenate the array with a string and get output like `[I@4e25154f` instead of `[1, 2, 3]`. That is because arrays in Java are **objects** and array classes themselves do not override `Object.toString()` to present individual elements. The `java.util.Arrays` API addresses two distinct needs: **`Arrays.toString(...)`** represents one array level, while **`Arrays.deepToString(Object[])`** descends through nested sub-arrays to represent nested data.

The goal is to choose the right API for one-dimensional arrays, multi-dimensional arrays, and arrays containing components of mixed types, while understanding the limits of display strings when writing `toString()` for custom classes.

## 1. Why Does Printing an Array Directly Show `[I@...`?

For an object without its own `toString()`, the default representation from `Object.toString()` consists of the class name, the `@` character, and the `hashCode()` value in hex form. Java arrays also have this default `toString()`, so:

```java
// Illustrative snippet inside a method, not a standalone program:
int[] values = {1, 2, 3};
System.out.println(values);            // May show a form like [I@<hex>
System.out.println("" + values);       // Also the default object representation
System.out.println(Arrays.toString(values)); // [1, 2, 3]
```

Some common internal class names:

| Array Type | JVM Array Class Name | Common Prefix Seen When Printed Directly |
| --- | --- | --- |
| `int[]` | `[I` | `[I@...` |
| `byte[]` | `[B` | `[B@...` |
| `String[]` | `[Ljava.lang.String;` | `[Ljava.lang.String;@...` |
| `int[][]` | `[[I` | `[[I@...` |

The hex part after `@` **is not a memory address** and has no uniqueness guarantee across all objects. It comes from the default hash code for display and can vary between runs. You should not store such strings as IDs or use them to check whether two arrays have the same contents.

For a one-dimensional array holding meaningful values, calling `Arrays.toString(array)` produces a much more readable representation. `import java.util.Arrays;` is required.

## 2. `Arrays.toString()`: Representing One Array Level

The `Arrays` class has `toString` overloads for each primitive array type (`int[]`, `long[]`, `boolean[]`, `char[]`, `float[]`, `double[]`, `byte[]`, `short[]`) and for reference arrays `Object[]`.

Examples:

```java
// Illustrative snippet inside a method:
Arrays.toString(new int[]{1, 2, 3});          // "[1, 2, 3]"
Arrays.toString(new boolean[]{true, false});  // "[true, false]"
Arrays.toString(new String[]{"A", "B"});      // "[A, B]"
Arrays.toString(new int[0]);                 // "[]"
Arrays.toString((int[]) null);               // "null"
```

The display syntax normally uses square brackets, separating elements with a comma and a space. If a reference array has a `null` element, it displays as the word `null`. For elements that are ordinary objects, `Arrays.toString(Object[])` obtains the string representation of **each element** (via the appropriate `String.valueOf`/`toString`), so a custom `toString()` on a class directly affects the output.

**However, `Arrays.toString` does not automatically descend into sub-arrays.** For example, `int[][] matrix = {{1, 2}, {3, 4}}` is actually an outer array containing two elements of type `int[]`. When `matrix` is passed to `Arrays.toString`, the `Object[]` overload is selected, and each `int[]` row is presented using the default `toString()`:

```java
// Illustrative snippet; hex hash parts vary across runs:
int[][] matrix = {{1, 2}, {3, 4}};
System.out.println(Arrays.toString(matrix));
// Example display form: [[I@<hash-1>, [I@<hash-2>]
```

This is why you may see multiple `[I@...` inside square brackets. `Arrays.toString(matrix)` only processes the **outer array**, without interpreting the contents of the row arrays.

## 3. `Arrays.deepToString(Object[])`: Descending Through Nested Arrays

For arrays whose **outermost level is a reference array** (`Object[]`, `String[][]`, `int[][]`, etc.), `Arrays.deepToString` can be used. This method inspects each element: if an element is an array, it renders the sub-array's contents using the appropriate rule; if it is an ordinary object, it uses that object's `toString` representation.

```java
// Illustrative expressions placed inside a method:
int[][] matrix = {{1, 2}, {3, 4}};
String[][] groups = {{"A", "B"}, {"C"}};

Arrays.deepToString(matrix); // "[[1, 2], [3, 4]]"
Arrays.deepToString(groups); // "[[A, B], [C]]"

Object[] mixed = {"row", new int[]{7, 8},
        new Object[]{new boolean[]{true, false}, "end"}};
Arrays.deepToString(mixed);
// "[row, [7, 8], [[true, false], end]]"
```

`int[][]` is valid because the outer array has elements of type `int[]` (a reference type), so `int[][]` itself can be passed to an `Object[]` parameter. Conversely, a single `int[]` **is not an `Object[]`**, so `Arrays.deepToString(new int[]{1, 2})` does not compile. For one-dimensional primitive arrays, use `Arrays.toString`.

Quick selection table:

| Data at Hand | How to Display Contents | What to Avoid |
| --- | --- | --- |
| `int[]`, `byte[]`, `double[]` | `Arrays.toString(array)` | `array.toString()` or `Arrays.deepToString(array)` |
| `String[]` | `Arrays.toString(array)` | Printing the array directly if you want to see the strings |
| `int[][]`, `double[][]` | `Arrays.deepToString(array)` | `Arrays.toString(array)` if you want to read the row array elements |
| `String[][]`, `Object[][]` | `Arrays.deepToString(array)` | Assuming one-level display is sufficient |
| `Object[]` mixing strings, objects, and arrays | `Arrays.deepToString(array)` when needing to descend through array elements | Assuming it automatically understands every arbitrary container type |

For `null` data, both `Arrays.toString((Object[]) null)` and `Arrays.deepToString((Object[]) null)` return the string `"null"`. If an array element is `null`, that element is also displayed as `null`. This is a representation string, **not a Java `null` reference being returned**.

## 4. Complete Java 17+ Example and Deterministic Output

Create the file **`ArrayRenderingDemo.java`**:

```java
import java.util.Arrays;

public class ArrayRenderingDemo {
    record Part(String name, int quantity) {}

    public static void main(String[] args) {
        int[] scores = {8, 9, 10};
        String[] tags = {"java", null, "core"};
        int[][] matrix = {{1, 2}, {3, 4}};
        Object[] nested = {
                "header",
                new int[]{7, 8},
                new Object[]{"deep", new boolean[]{true, false}},
                null
        };

        System.out.println("scores: " + Arrays.toString(scores));
        System.out.println("tags: " + Arrays.toString(tags));
        System.out.println("empty: " + Arrays.toString(new int[0]));
        System.out.println("null array: "
                + Arrays.toString((int[]) null));

        System.out.println("matrix deep: "
                + Arrays.deepToString(matrix));
        System.out.println("nested deep: "
                + Arrays.deepToString(nested));
        System.out.println("matrix shallow contains row identity: "
                + Arrays.toString(matrix).contains("[I@"));
        System.out.println("nested shallow contains primitive identity: "
                + Arrays.toString(nested).contains("[I@"));

        Object[] parts = {
                new Part("bolt", 2),
                new int[]{5, 6}
        };
        System.out.println("record and array: "
                + Arrays.deepToString(parts));

        Object[] selfReference = new Object[1];
        selfReference[0] = selfReference;
        System.out.println("cycle has marker: "
                + Arrays.deepToString(selfReference).contains("..."));
    }
}
```

Compile and run from the directory containing the file using JDK 17 or later:

```bash
javac ArrayRenderingDemo.java
java ArrayRenderingDemo
```

Output:

```text
scores: [8, 9, 10]
tags: [java, null, core]
empty: []
null array: null
matrix deep: [[1, 2], [3, 4]]
nested deep: [header, [7, 8], [deep, [true, false]], null]
matrix shallow contains row identity: true
nested shallow contains primitive identity: true
record and array: [Part[name=bolt, quantity=2], [5, 6]]
cycle has marker: true
```

Meaning:

1. `scores` and `tags` are one-dimensional arrays so `Arrays.toString` is sufficient; `null` elements are displayed safely.
2. `matrix` is a two-dimensional array. `deepToString` displays every element of each row; one-level `toString` still exposes the default identifier form of the `int[]` rows. The program only prints the result of checking `contains("[I@")` so as **not to depend on unstable hash digits**.
3. `nested` contains mixed element types, including primitive arrays inside another `Object[]`. `deepToString` correctly interprets the nested array structure.
4. `Part` is a record, so `toString` is generated by Java from the record name and components. When an element is not an array, `deepToString` uses how that element represents itself; it does not automatically reflect fields of arbitrary classes.
5. `selfReference` is an array holding a reference to itself. `deepToString` detects the array cycle and uses a truncation marker (containing `...`) instead of recursing endlessly. This mechanism is for nested reference array structures.

Do not use the printed string itself as proof of equality between two objects: two different objects can be represented identically by `toString`, and `toString` output can also change when state changes.

## 5. Limitations When Nested Components Are Not Arrays

`Arrays.deepToString` traverses **array levels** deeply, not every kind of data structure in Java. If an element of `Object[]` is a `List<int[]>`, `Map<String,int[]>`, or a POJO containing an array, `deepToString` calls the `toString` of that `List`, `Map`, or POJO; it **does not automatically traverse through those classes to reach inner arrays**.

Conceptual example (not a standalone program):

```java
Object[] data = {
        java.util.List.of(new int[]{1, 2})
};
String rendered = Arrays.deepToString(data);
// List.toString() is used at the List element level;
// you cannot assume the array contents inside List will be "[1, 2]".
```

Therefore, when building a `toString` representation for multi-level objects, clearly decide **which class owns the presentation responsibility**. A class holding an array can itself use `Arrays.toString`/`deepToString` in its own `toString`. `Map` or `List` structures may need to map components to clear strings before displaying.

For business objects:

```java
// Illustrates only the body of toString inside a class with fields:
@Override
public String toString() {
    return "Report[scores=" + Arrays.toString(scores)
            + ", matrix=" + Arrays.deepToString(matrix) + "]";
}
```

The illustration assumes field `scores` has type `int[]` and `matrix` has type `int[][]`, not a standalone program. This approach produces a more readable string than concatenating `scores` or `matrix` directly.

Another note: an ordinary object may have a custom `toString` implementation that includes side effects, heavy access cost, or errors if state is invalid. `deepToString` **does not control the behavior of component `toString` methods**. Logging the representation of an entire structure should only be used when the data is genuinely safe and the cost is acceptable.

## 6. `deepToString` and Self-Referential Arrays

A reference array `Object[]` can contain itself or form a circular reference chain:

```java
// Illustrative snippet:
Object[] a = new Object[1];
a[0] = a;
String text = Arrays.deepToString(a);
```

If an algorithm descended through arrays without tracking already-seen arrays on the traversal branch, it would call itself forever and cause `StackOverflowError`. `Arrays.deepToString` has a cycle-detection mechanism across object arrays, using the `[[...]]` notation for an array encountered again in a cycle, thereby avoiding infinite recursion **for cycles formed through arrays**.

However:

- This mechanism does not mean `Arrays.deepToString` is a general *object graph* serialization tool covering every kind of cycle through POJOs, collections, and maps.
- The display string can repeat the contents of a sub-array referenced from multiple places that **do not form an active recursion cycle**. Thus, you cannot read the string as a diagram preserving reference identity.
- With deeply nested or large data, building the entire string can consume memory and CPU; consider bounding depth or log size at the application layer.

The cycle-handling mechanism is primarily meant to aid array representation for diagnostics; it does not replace data design and is not a stable data interchange format.

## 7. Display Strings Differ from Content Comparison and Hash Codes

`Arrays.toString`/`deepToString` only produce **text strings**. They do not decide whether objects are equal and do not issue unique IDs:

| Purpose | One-Dimensional Array | Nested Array |
| --- | --- | --- |
| **Readable representation** | `Arrays.toString(a)` | `Arrays.deepToString(a)` |
| **Content comparison** | `Arrays.equals(a,b)` | `Arrays.deepEquals(a,b)` |
| **Content-based hashing** | `Arrays.hashCode(a)` | `Arrays.deepHashCode(a)` |

These three rows often appear together in a value object with array fields, yet serve separate functions. If a custom class implements `equals` by array content and a matching `hashCode`, `toString` can display using the API of the same depth level to help debugging. Even so, identical display strings **do not create an `equals` contract guarantee**: a class's `toString` may intentionally omit information or abbreviate.

For example, the following two arrays can render identically in one context without representing the exact same typed structure:

```java
// Illustrative example:
String[] withComma = {"a, b", "c"};
String[] separate = {"a", "b", "c"};
// Arrays.toString(withComma) -> "[a, b, c]"
// Arrays.toString(separate)  -> "[a, b, c]"
// Arrays.equals(withComma, separate) -> false
```

In particular, `Arrays.toString` does not fully escape or quote string contents, so it is **not a reliable serialization format to parse back**. Delimiters appearing inside values can make the rendered output ambiguous.

## 8. When Is JSON or a Schema-Backed Structure Needed?

If you need to send data over an API, write configuration files, store in a database, or need a format that another machine can parse back accurately, use a maintained serialization library (such as Jackson JSON in an appropriate application) with an explicit structure/schema. Do not use `Arrays.deepToString` in place of JSON or a communication protocol:

- There is no escaping/quoting system like JSON to preserve arbitrary strings.
- It does not carry enough Java type, nullability, and object identity information for all cases.
- There is no stable format contract for classes with custom `toString`.
- It is not designed to represent cycles, shared references, or nested collections in a decodable form.
- It can expose sensitive fields if entire objects are printed for logging.

If the goal is just a quick look at an array on the console or in safe debug logs, `Arrays.toString` and `deepToString` are sensible choices because they are concise and built into the JDK. If the goal is **structured, reusable data**, design dedicated serialization.

## 9. Common Mistakes and How to Self-Check

1. **`System.out.println(intArray)` expecting to see contents:** in reality you usually see `[I@...`; use `Arrays.toString(intArray)`.
2. **`Arrays.toString(intMatrix)` expecting all rows printed:** inner `int[]` arrays still print with the default form; use `Arrays.deepToString(intMatrix)`.
3. **Using `Arrays.deepToString(intArray)` for a one-dimensional `int[]`:** type mismatch, does not compile because the method takes `Object[]`; use `Arrays.toString`.
4. **Assuming `deepToString` descends into every `List`, `Map`, and POJO:** it only descends through arrays. Handle representations of other containers with appropriate APIs/designs.
5. **Thinking `[I@<hex>` is a RAM address or immutable ID:** it is an `Object.toString` representation based on a hash, with no such guarantee.
6. **Using `Arrays.toString` strings as machine-parseable data:** delimiters and element types can be ambiguous; use a schema-backed format like JSON when interchange or storage is needed.
7. **Logging arrays of passwords, tokens, or personal data:** the array's contents may appear in full; filter/mask sensitive information before logging.
8. **Letting custom `toString` recurse unchecked on cyclic object graphs:** `Arrays.deepToString` handles array cycles, yet does not protect against all cycles created by custom `toString` code.
9. **Assigning "equality" meaning from `toString`:** two objects that print identically can still differ by `equals`; use the appropriate comparison.
10. **Building a string for a huge array on every operation:** in high-performance code, generate representations only when needed for diagnosis; consider bounding element counts and avoiding overly verbose logging.

### Checklist

- Is the object to print a **one-dimensional primitive array**, one-dimensional reference array, or multi-dimensional array?
- Have you chosen the right overload of `Arrays.toString` or `Arrays.deepToString`?
- Does the array contain nested sub-arrays, `List`, `Map`, or POJOs needing separate representation?
- Are there potential reference cycles, overly deep/large data, or element `toString` methods with side effects?
- Is the string meant for **human-readable debugging** or for **transmitting/storing parseable data**?
- Does the content contain secrets or sensitive data that must be masked before logging?

**Key takeaway:** use **`Arrays.toString` for one-dimensional arrays**, and use **`Arrays.deepToString` when there are nested array levels whose outer array is a reference array**. These two APIs make data easy to read when printed, yet do not turn display strings into object identity, `equals` comparison, or a reliable serialization format.