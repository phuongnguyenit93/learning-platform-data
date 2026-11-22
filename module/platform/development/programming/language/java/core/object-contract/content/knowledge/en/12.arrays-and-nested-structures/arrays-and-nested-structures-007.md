# Array Fields in Custom Classes: Synchronizing `equals()` with `hashCode()`

When a custom Java class has an **array** field (`int[]`, `String[]`, `Object[]`, `int[][]`…), the decision of “whether two objects are equal” must be accompanied by **a matching way to compute the hash code**. Arrays are special objects in Java: they do not override `Object.equals()` and `Object.hashCode()` by element content. Therefore, even when two arrays contain the exact same values, `array1.equals(array2)` or `Objects.equals(array1, array2)` can still return `false` if they are two different instances.

If a class wants to define equality **by array content**, use the right API pair:

- One-dimensional arrays: **`Arrays.equals(...)` paired with `Arrays.hashCode(...)`**.
- Nested arrays requiring deep comparison: **`Arrays.deepEquals(...)` paired with `Arrays.deepHashCode(...)`**.
- Other fields participating in `equals` must also be reflected consistently in `hashCode`.

Using different rules between the two methods can cause `HashMap` and `HashSet` to handle objects contrary to expectations.

## 1. Starting from the `equals`/`hashCode` contract

For a custom class, the most important contract is:

> If `a.equals(b)` returns `true`, it is **mandatory** that `a.hashCode() == b.hashCode()`.

The reverse is **not required**: unequal objects may still have colliding hash codes.

In addition, `equals` must guarantee reflexivity, symmetry, transitivity, consistency when data used for comparison does not change, and `x.equals(null)` returning `false`. Whenever overriding `equals`, override `hashCode` so that hash-based structures can find equal objects properly.

An easy-to-make mistake (merely illustrative snippets inside a class, **not a standalone program**):

```java
// Wrong if you want to compare array content:
return Objects.equals(scores, other.scores);

// Wrong if equals already uses Arrays.equals(scores, other.scores):
@Override
public int hashCode() {
    return scores.hashCode();
}
```

`Objects.equals` only handles `null` and calls `equals` on the argument; for arrays, the `equals` inherited from `Object` checks **same reference**. Similarly, `scores.hashCode()` does not hash individual elements. If two objects containing **two different arrays with identical content** are considered equal, they could receive different hashes, violating the contract.

Note: if a class **intentionally** treats an array as a component with reference-identity semantics, using `==`/`Objects.equals` and the corresponding hash may be valid. However, that is a **semantic decision** that must be chosen consistently, not the default assumption for every value object.

## 2. One-dimensional arrays: `Arrays.equals` and `Arrays.hashCode`

Use `import java.util.Arrays;`.

Common overloads of `Arrays.equals` include arrays of primitive types such as `int[]`, `long[]`, `byte[]`, `char[]`, `boolean[]`, and reference arrays such as `String[]`, `Object[]`.

```java
// Standalone expressions for illustration, placed in main or a method:
int[] x = {1, 2, 3};
int[] y = {1, 2, 3};

// x == y                 -> false (two different array instances)
// Objects.equals(x, y)   -> false (arrays do not override equals by value)
// Arrays.equals(x, y)    -> true  (compares elements at matching positions)
// Arrays.hashCode(x) == Arrays.hashCode(y) -> true
```

For `int[]`, elements are compared by primitive value. For `String[]`, each pair of elements is compared via `Objects.equals`, so two strings that are different instances yet have identical content are considered equal. For `Object[]`, how each element's content is compared **depends on the element class's `equals`**.

Two one-dimensional arrays are equal only when they have the same length and every corresponding position is equal. Therefore order matters:

```text
[1, 2, 3]  and  [1, 2, 3]  -> equal
[1, 2, 3]  and  [3, 2, 1]  -> not equal
[1, 2, 3]  and  [1, 2]     -> not equal
```

`Arrays.hashCode` hashes in the same element order, ensuring that two arrays considered equal by `Arrays.equals` have the same hash. Matching hashes do not prove two arrays are equal because collisions can still happen.

These overloads also handle `null`: two `null` arrays are considered equal by `Arrays.equals`; one `null` array and one non-`null` array are not equal; `Arrays.hashCode` returns `0` for a `null` array. Thus they can be used directly on nullable array fields with the proper overload.

## 3. Nested arrays: when are `deepEquals` and `deepHashCode` needed?

In Java, `int[][]` is an **array containing references to `int[]`**, not a monolithic “matrix” region with its own equality mechanism. If you call `Arrays.equals(int[][], int[][])`, the method uses the `Object[]` overload and compares **each row element**. Each `int[]` row uses default `Object.equals`, so two rows that are different instances—even with identical numbers—are not equal.

For nested data needing full content comparison, use:

```java
// Two matrices with different instances, including row arrays:
int[][] first = {{1, 2}, {3, 4}};
int[][] second = {{1, 2}, {3, 4}};

// Arrays.equals(first, second)       -> false
// Arrays.deepEquals(first, second)   -> true
// Arrays.deepHashCode(first) == Arrays.deepHashCode(second) -> true
```

`Arrays.deepEquals(Object[] a1, Object[] a2)` accepts outer reference arrays. It descends through array-typed elements, including nested primitive arrays, and uses the appropriate comparison at each level. `Arrays.deepHashCode(Object[] a)` computes the corresponding hash code. This pair fits structures like `int[][]`, `String[][]`, or `Object[]` containing sub-arrays.

**Limitation to understand:** `Arrays.deepEquals` is not a mechanism that automatically traverses every field of **any arbitrary object**. If an element is a regular Java object, its comparison semantics are still governed by that class's `equals`. Array structures with circular references back to themselves are also unsuitable for naive deep comparison: this can lead to infinite recursion or stack overflow errors.

`Arrays.deepHashCode` and `Arrays.deepEquals` form mutually compatible rules; do not use `deepEquals` in `equals` while calling `Arrays.hashCode` at the outer array level in `hashCode`.

## 4. Complete Java 17+ example with a class having three kinds of array fields

Let us design class `CourseReport` containing:

- `title`: nullable string, compared with `Objects.equals`.
- `scores`: `int[]`, compared and hashed by one-dimensional content.
- `tags`: `String[]`, compared and hashed element by element by string value.
- `matrix`: `int[][]`, deeply compared and hashed by row contents.

All of these fields participate in the equality criteria of `CourseReport`. The class is `final`, keeps `private final` fields, and **copies inputs** to prevent external mutation of arrays after object creation.

Save as file **`ArrayFieldContractDemo.java`**:

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

final class CourseReport {
    private final String title;
    private final int[] scores;
    private final String[] tags;
    private final int[][] matrix;

    CourseReport(String title, int[] scores, String[] tags, int[][] matrix) {
        this.title = title;
        this.scores = Objects.requireNonNull(scores, "scores").clone();
        this.tags = Objects.requireNonNull(tags, "tags").clone();
        this.matrix = copyMatrix(matrix);
    }

    private static int[][] copyMatrix(int[][] source) {
        Objects.requireNonNull(source, "matrix");
        int[][] copy = new int[source.length][];
        for (int i = 0; i < source.length; i++) {
            copy[i] = Objects.requireNonNull(source[i], "matrix row").clone();
        }
        return copy;
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        if (!(obj instanceof CourseReport other)) {
            return false;
        }
        return Objects.equals(title, other.title)
                && Arrays.equals(scores, other.scores)
                && Arrays.equals(tags, other.tags)
                && Arrays.deepEquals(matrix, other.matrix);
    }

    @Override
    public int hashCode() {
        int result = Objects.hashCode(title);
        result = 31 * result + Arrays.hashCode(scores);
        result = 31 * result + Arrays.hashCode(tags);
        result = 31 * result + Arrays.deepHashCode(matrix);
        return result;
    }
}

public class ArrayFieldContractDemo {
    public static void main(String[] args) {
        int[] scores = {9, 10};
        String[] tags = {"java", "core"};
        int[][] matrix = {{1, 2}, {3, 4}};

        CourseReport a = new CourseReport("lesson", scores, tags, matrix);
        CourseReport b = new CourseReport(
                "lesson",
                new int[]{9, 10},
                new String[]{"java", "core"},
                new int[][]{{1, 2}, {3, 4}}
        );

        System.out.println("a equals b: " + a.equals(b));
        System.out.println("Equal hash: " + (a.hashCode() == b.hashCode()));

        scores[0] = 0;
        tags[0] = "changed";
        matrix[0][0] = 99;

        System.out.println("Equal after changing inputs: " + a.equals(b));
        System.out.println("Hash still equal: "
                + (a.hashCode() == b.hashCode()));

        CourseReport different = new CourseReport(
                "lesson",
                new int[]{9, 11},
                new String[]{"java", "core"},
                new int[][]{{1, 2}, {3, 4}}
        );
        System.out.println("Different scores: " + a.equals(different));

        Set<CourseReport> reports = new HashSet<>();
        reports.add(a);
        reports.add(b);
        reports.add(different);
        System.out.println("HashSet size: " + reports.size());

        int[][] nested1 = {{1, 2}};
        int[][] nested2 = {{1, 2}};
        System.out.println("Nested shallow equals: "
                + Arrays.equals(nested1, nested2));
        System.out.println("Nested deep equals: "
                + Arrays.deepEquals(nested1, nested2));
        System.out.println("Nested deep hashes equal: "
                + (Arrays.deepHashCode(nested1)
                        == Arrays.deepHashCode(nested2)));

        System.out.println("Array Objects.equals: "
                + Objects.equals(new int[]{1}, new int[]{1}));
        System.out.println("Array Arrays.equals: "
                + Arrays.equals(new int[]{1}, new int[]{1}));
    }
}
```

Compile and run from the directory containing the file using JDK 17 or later:

```bash
javac ArrayFieldContractDemo.java
java ArrayFieldContractDemo
```

Deterministic output:

```text
a equals b: true
Equal hash: true
Equal after changing inputs: true
Hash still equal: true
Different scores: false
HashSet size: 2
Nested shallow equals: false
Nested deep equals: true
Nested deep hashes equal: true
Array Objects.equals: false
Array Arrays.equals: true
```

### Explaining the output and design

1. `a` and `b` have two sets of arrays with **different references** yet identical content. Thanks to `Arrays.equals` and `Arrays.deepEquals`, `a.equals(b)` is `true`.
2. `hashCode()` computes using the same fields and same comparison rules, so `a.hashCode() == b.hashCode()` is guaranteed to hold.
3. After mutating the original `scores`, `tags`, and `matrix`, the internal contents of `a` **do not change** thanks to cloning at every needed level. Thus `a` and `b` remain equal and have the same hash.
4. `different` has a differing score element so it does not equal `a`, even though the remaining fields match. `HashSet` holds two logical elements: one equivalent to `a`/`b` and one for `different`.
5. Two independent `int[][]` yield `false` for `Arrays.equals` because the row arrays are different instances; `Arrays.deepEquals` is `true` and their deep hashes are equal.
6. `Objects.equals` on two newly created `int[]` is `false`, while `Arrays.equals` is `true`, accurately illustrating the difference between identity and content.

The program **does not print concrete hash codes** because the task needs to verify the equality contract rather than rely on a coincidental numeric hash value. Moreover, two different objects can still have the same hash, so inequality is not checked via a “different hash” condition.

## 5. Why must input arrays be copied?

A field declared `private final int[] scores` only prevents **reassigning the `scores` reference**; it does not prevent `scores[0] = ...`. If the constructor keeps the array passed by the caller directly, the caller can mutate the array after the object is already used as a key in `HashMap`/`HashSet`. When `hashCode` changes with the elements, key lookups can fail.

In the example:

- `int[]`: `clone()` copies primitive values; sufficient to isolate content.
- `String[]`: `clone()` copies the array structure, while `String` objects are already immutable; sufficient within the example's scope.
- `int[][]`: `matrix.clone()` **only copies the outer array**, while the inner `int[]` rows still share references. Each row must be cloned, as in `copyMatrix`.
- If an array holds **mutable** object elements, such as `Address[]`, cloning the array does not clone each `Address`; an appropriate defensive copying policy or keeping element objects immutable is required.

The principle also applies to **getters**: if you provide a getter returning the internal array directly, external code can still mutate it. Return a copy or an appropriate read-only/immutable structure. A “read-only view” does not imply the underlying data is immutable if elsewhere still has permission to mutate it.

If the problem genuinely requires an object with mutable arrays, you must clearly define when mutation is allowed, synchronization mechanisms under multithreading, and effects on collections. Usually, **not using mutable fields in the hash of a stored key** is simpler.

## 6. Common ways to combine hashes and the `Objects.hash` trap

A manual approach like the example:

```java
int result = Objects.hashCode(title);
result = 31 * result + Arrays.hashCode(scores);
result = 31 * result + Arrays.hashCode(tags);
result = 31 * result + Arrays.deepHashCode(matrix);
return result;
```

For two `CourseReport` instances considered equal by `equals`, each corresponding component hash is equal, so combining via the same formula yields the same result. Multiply-and-add on `int` can overflow under Java arithmetic; **int overflow does not break the contract** if the formula is applied consistently.

Component hashes can also be combined using:

```java
return Objects.hash(
        title,
        Arrays.hashCode(scores),
        Arrays.hashCode(tags),
        Arrays.deepHashCode(matrix)
);
```

This is still an ordinary `int` hash code, subject to collisions, yet consistent with `equals`.

**Do not use directly:**

```java
// Wrong for a class using Arrays.equals/deepEquals in equals:
return Objects.hash(title, scores, tags, matrix);
```

Reason: `Objects.hash` does not automatically convert every array reference into the appropriate content/deep hash; when an array appears as an element of the varargs list, it is processed via the array's own `hashCode`. Two instances with different array instances yet equal content could receive different hashes, violating the contract of `CourseReport.equals`.

Also do not confuse `Objects.hash(array)` with `Arrays.hashCode(array)`: how overloading/varargs interprets arguments can be surprising, especially with `Object[]`; **explicitly choose the `Arrays` API at the right depth**.

## 7. Decision table by field type

| Field in class | If content equality is desired | Corresponding hash |
| --- | --- | --- |
| `int[]`, `long[]`, `byte[]`, `boolean[]`… | `Arrays.equals(a, b)` | `Arrays.hashCode(a)` |
| `String[]`, `Object[]` without sub-arrays needing deep comparison | `Arrays.equals(a, b)` | `Arrays.hashCode(a)` |
| `int[][]`, `String[][]`, `Object[]` with sub-arrays | `Arrays.deepEquals(a, b)` | `Arrays.deepHashCode(a)` |
| `String` or regular nullable object | `Objects.equals(a, b)` | `Objects.hashCode(a)` or equivalent component |
| Primitive types such as `int`, `boolean` | `==` | `Integer.hashCode`, `Boolean.hashCode`, or appropriate combination |

For `float[]` or `double[]` arrays, use `Arrays.equals` and `Arrays.hashCode` together; the rules for handling `NaN` and `-0.0` in these overloads are designed consistently. Avoid mixing `==` comparison on individual float elements with `Float.hashCode` without considering special values.

If a field is a collection like `List<String>`, it has `equals`/`hashCode` according to collection conventions; **do not automatically apply `Arrays.equals`** to collections. Choose the right comparison for the actual data type.

## 8. Records containing arrays and cases needing caution

Java `record` auto-generates `equals`/`hashCode` from its components, but for an array-typed component, the generated comparison follows **the array's reference semantics**, not automatically turning into content-based `Arrays.equals` or `Arrays.deepEquals`. For example:

```java
record Sample(int[] values) {}

// These two Samples are not automatically equal by values content:
Sample x = new Sample(new int[]{1, 2});
Sample y = new Sample(new int[]{1, 2});
// x.equals(y) -> false
```

This snippet is illustrative only, **not a standalone program**. If you need a record with an array that compares by content, you must explicitly consider overriding both `equals` and `hashCode`, along with defensive copying on construction/return if stability is needed. Another easier-to-control option is storing data in an immutable value type with content-based `equals`/`hashCode` such as `List.copyOf(...)` when appropriate, though the list elements themselves still need proper equality semantics.

## 9. Common mistakes and how to review

1. **Using `Objects.equals(array1, array2)` thinking it compares element by element:** it usually only compares array identity. Use `Arrays.equals` or `Arrays.deepEquals` depending on structure.
2. **Using `Arrays.equals` for `int[][]` when wanting to compare all numbers:** the `Object[]` overload only compares rows via each row's `equals`; use `Arrays.deepEquals`.
3. **Implementing `equals` by array content but `hashCode` by reference:** violates the requirement that hashes match when objects are equal.
4. **Using `Objects.hash(title, array)` thinking it hashes deeply:** convert arrays into `Arrays.hashCode(array)` or `Arrays.deepHashCode(array)` before combining.
5. **Omitting a field in `equals` while including it in `hashCode`:** two objects could compare equal via `equals` yet have different hashes. Conversely, omitting fields from hashing may still satisfy the contract while causing many collisions; keep the rules aligned.
6. **Cloning only the outer array of a multidimensional structure:** sub-row data can still be mutated. Clone every level that needs isolation.
7. **Letting the caller mutate the array after inserting the object into `HashSet` or as a `HashMap` key:** hashes or equality relations can change; prefer immutable value objects and immutable keys.
8. **Relying on matching/differing hash codes to conclude `equals`:** equal hashes do not guarantee equal objects; compare using actual `equals`.
9. **Assuming a cloned array containing objects is deeply immutable:** mutable element objects can still be modified through other references.
10. **Confusing `Arrays.deepEquals` with an arbitrary object-graph comparator:** it mainly descends through nested arrays, and does not automatically understand all business relations or arbitrary reference cycles.

### Checklist for custom classes containing arrays

- Have you determined for each array whether comparison is by **reference** or **content** per business rules?
- Do one-dimensional arrays use the `Arrays.equals`/`Arrays.hashCode` pair, and nested arrays use the `Arrays.deepEquals`/`Arrays.deepHashCode` pair?
- Are other regular fields handled consistently in both `equals` and `hashCode`?
- Have you tested two instances with **arrays of different references but identical content**, arrays differing in one element, arrays of different lengths, nested arrays, and (if permitted) `null` arrays?
- Do constructors/getters expose mutable arrays participating in `equals`/`hashCode`? Are multidimensional arrays copied deeply enough for the specific structure?
- Is the object used as a `HashMap` key or `HashSet` element? Is the data participating in hashing stable throughout its storage lifetime?

**Key takeaway:** when a class's array field is treated as a **value**, `equals` and `hashCode` must use **the same level of content comparison/hashing**: `Arrays.equals` goes with `Arrays.hashCode`, and `Arrays.deepEquals` goes with `Arrays.deepHashCode`. Protect array contents from unintended mutation to preserve consistency in hash-based collections.