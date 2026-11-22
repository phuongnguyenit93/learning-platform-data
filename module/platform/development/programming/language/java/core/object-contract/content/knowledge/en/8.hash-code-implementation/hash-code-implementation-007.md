# Using `Arrays.hashCode()` or `deepHashCode()` Matching How Arrays Are Compared

## 1. Why Do Arrays Need a Dedicated Way to Compute `hashCode`?

In Java, arrays are objects, yet **arrays do not override `Object.equals(Object)` or `Object.hashCode()` to compare contents**. Therefore, two separately created arrays holding identical elements are still two distinct objects under default `equals`. If you design a value class containing an array and want two instances to be equal **based on array content**, you must explicitly pick a **content comparison method** and the **corresponding hash function**.

The most important contract rule:

> If `a.equals(b)` returns `true`, then `a.hashCode()` must equal `b.hashCode()`.

The converse is **not required**: two unequal values can share the same hash due to a hash collision. Never use **equal `hashCode()`** as proof that two arrays are equal.

For arrays, you must agree on the **depth of comparison**:

- One-dimensional arrays such as **`int[]`**, **`byte[]`**, **`char[]`**: use **`Arrays.equals(...)`** to compare element values and **`Arrays.hashCode(...)`** for the same array type to compute content-based hashes.
- One-dimensional object arrays such as **`String[]`**: **`Arrays.equals(Object[], Object[])`** uses **`Objects.equals(...)`** for each element; **`Arrays.hashCode(Object[])`** calls `hashCode` on the corresponding elements.
- Nested arrays such as **`int[][]`**, **`String[][]`**, or **`Object[]`** containing arrays: to compare **deeply over the contents of nested sub-arrays**, use **`Arrays.deepEquals(Object[], Object[])`** and **`Arrays.deepHashCode(Object[])`**.

Do not choose a hash function mechanically by counting square brackets: **`String[]`** is a one-dimensional object array where shallow comparison is usually sufficient because `String` elements compare content themselves; meanwhile, a one-dimensional **`Object[]`** holding **`int[]`** elements still needs deep comparison if the value rule requires comparing the contents of those sub-arrays.

## 2. Reference Table of Comparison and Hashing Functions

| Data type and intended semantics | Value comparison | Matching hash calculation |
| --- | --- | --- |
| **`int[]`** / **`long[]`** / **`byte[]`** / **`char[]`** / 1D primitive arrays | **`Arrays.equals(a, b)`** | **`Arrays.hashCode(a)`** |
| **`String[]`** or **`Integer[]`**, comparing elements with `equals` | **`Arrays.equals(a, b)`** | **`Arrays.hashCode(a)`** |
| **`Object[]`** whose elements are regular objects, compared directly | **`Arrays.equals(a, b)`** | **`Arrays.hashCode(a)`** |
| **`int[][]`**, **`long[][]`**, **`String[][]`**, comparing rows deeply | **`Arrays.deepEquals(a, b)`** | **`Arrays.deepHashCode(a)`** |
| **`Object[]`** containing arrays at one or more levels with deep comparison | **`Arrays.deepEquals(a, b)`** | **`Arrays.deepHashCode(a)`** |
| **`Object[]`** containing sub-arrays where business logic **compares only sub-array references** | **`Arrays.equals(a, b)`** | **`Arrays.hashCode(a)`** |

**"Shallow"** in the table means the method inspects **the elements of the outer array** one by one: if an element itself is an array, that sub-array's default `equals`/`hashCode` remains object-based—that is, usually by reference. **"Deep"** means that when an element is also an array, Java recurses into the sub-arrays and handles the nested elements inside.

A note on the word **deep**: this is deep comparison of **array nesting layers**, not automatic traversal of every field of arbitrary objects. When encountering a regular object element, **`Arrays.deepEquals`** still relies on that object's **`equals`** method, and **`Arrays.deepHashCode`** relies on its **`hashCode`**. If an element's class violates the `equals`/`hashCode` contract, deep array methods cannot fix that bug on their own.

## 3. Example 1: One-Dimensional Primitive Array Using `Arrays.equals` and `Arrays.hashCode`

Create the file **`PrimitiveArrayHashDemo.java`**:

~~~java
import java.util.Arrays;

public class PrimitiveArrayHashDemo {
    public static void main(String[] args) {
        int[] first = {1, 2, 3};
        int[] second = {1, 2, 3};
        int[] third = {1, 2, 4};

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(Arrays.equals(first, second));
        System.out.println(Arrays.hashCode(first));
        System.out.println(Arrays.hashCode(second));
        System.out.println(Arrays.equals(first, third));
        System.out.println(Arrays.hashCode(first) == Arrays.hashCode(second));
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac PrimitiveArrayHashDemo.java
java PrimitiveArrayHashDemo
~~~

Output:

~~~text
false
false
true
30817
30817
false
true
~~~

**Explanation:** **`first`** and **`second`** are two distinct array instances, so both **`==`** and **`first.equals(second)`** are `false`. However, **`Arrays.equals(first, second)`** iterates through every `int` element and returns `true`. **`Arrays.hashCode(int[])`** also operates over the same sequence of values and produces the same result.

For `int[]`, Java defines the hash accumulation as:

~~~text
result = 1
for each element v:
    result = 31 * result + v
~~~

Multiplication and addition use Java **`int`** arithmetic, so overflow is valid and can occur. For **`{1, 2, 3}`**:

~~~text
31 * 1   + 1 = 32
31 * 32  + 2 = 994
31 * 994 + 3 = 30817
~~~

This illustrates the formula for **`int[]`**; the other primitive overloads convert each element to a hash number appropriate for its element type. **There is no need to write your own hash loop**, because `Arrays.hashCode` already provides a mechanism consistent with `Arrays.equals`.

### Empty Arrays, `null`, and Ordering

- Two **empty `int[]`** arrays are equal under **`Arrays.equals`** and have the same `Arrays.hashCode`.
- **`Arrays.equals((int[]) null, (int[]) null)`** returns `true`; if one side is `null` and the other is non-null, it returns `false`.
- **`Arrays.hashCode((int[]) null)`** returns `0`.
- Element order is part of the value: **`{1, 2}`** differs from **`{2, 1}`** under `Arrays.equals`. Two arrays with different element order might happen to share a hash, yet they are still unequal.
- If business logic treats the array as an **unordered set**, ordered `Arrays.equals`/`hashCode` is **unsuitable** for that definition. You need a different value model or normalized key with consistent `equals`/`hashCode`.

## 4. Example 2: Why Do Nested Arrays Need `deepEquals` and `deepHashCode`?

For **`int[][]`**, each element of the outer array is an **`int[]`**. If you call **`Arrays.equals(int[][], int[][])`**, Java selects the **`Object[]`** overload; at the outer array level, the elements are sub-arrays. Two separately constructed rows **`new int[]{1, 2}`** are not equal under default `Object.equals`.

Create the file **`NestedArrayHashDemo.java`**:

~~~java
import java.util.Arrays;

public class NestedArrayHashDemo {
    public static void main(String[] args) {
        int[][] first = {
            {1, 2},
            {3, 4}
        };
        int[][] second = {
            {1, 2},
            {3, 4}
        };
        int[][] changed = {
            {1, 2},
            {3, 9}
        };

        System.out.println("shallow equals: " +
            Arrays.equals(first, second));
        System.out.println("deep equals: " +
            Arrays.deepEquals(first, second));
        System.out.println("deep hash equal: " +
            (Arrays.deepHashCode(first) == Arrays.deepHashCode(second)));
        System.out.println("changed deep equals: " +
            Arrays.deepEquals(first, changed));
        System.out.println("matrix: " +
            Arrays.deepToString(first));
    }
}
~~~

Compile and run:

~~~bash
javac NestedArrayHashDemo.java
java NestedArrayHashDemo
~~~

Output:

~~~text
shallow equals: false
deep equals: true
deep hash equal: true
changed deep equals: false
matrix: [[1, 2], [3, 4]]
~~~

**How it works:**

1. **`Arrays.equals(first, second)`** inspects the elements of the outer array. Those elements are sub-arrays with distinct references, so the result is `false`.
2. **`Arrays.deepEquals(first, second)`** accepts **`Object[]`** at the outer level (`int[][]` is an `Object[]`), recognizes each child element as an **`int[]`**, and invokes the appropriate primitive comparison.
3. **`Arrays.deepHashCode(first)`** recurses through the sub-arrays to hash every `int` value. If two structures are equal under `deepEquals` and element objects obey the contract, they share the same deep hash.
4. **`Arrays.deepToString`** is handy for printing nested structures during inspection. It is a string-formatting helper, **not a replacement** for `equals`/`hashCode`.

There is no **`Arrays.deepHashCode(int[])`** overload: the deep method takes **`Object[]`**, whereas **`int[]` is not an `Object[]`**. For a standalone **`int[]`**, use **`Arrays.hashCode(int[])`**. For **`int[][]`**, you can use **`Arrays.deepHashCode(int[][])`** because **`int[][]` is an array of `int[]` elements**, making it compatible with an `Object[]` parameter.

## 5. Example 3: One-Dimensional `Object[]` Containing Mixed Arrays

The declared dimension of the outer array is not the whole story. An **`Object[]`** can hold **`int[]`**, **`String[]`**, multidimensional arrays, and ordinary objects all at once.

Create the file **`MixedNestedArrayDemo.java`**:

~~~java
import java.util.Arrays;

public class MixedNestedArrayDemo {
    public static void main(String[] args) {
        Object[] left = {
            "header",
            new int[]{5, 8},
            new String[]{"A", "B"}
        };

        Object[] right = {
            "header",
            new int[]{5, 8},
            new String[]{"A", "B"}
        };

        System.out.println("shallow: " +
            Arrays.equals(left, right));
        System.out.println("deep: " +
            Arrays.deepEquals(left, right));
        System.out.println("deep hash equal: " +
            (Arrays.deepHashCode(left) == Arrays.deepHashCode(right)));
        System.out.println("display: " +
            Arrays.deepToString(left));
    }
}
~~~

Output when running **`javac MixedNestedArrayDemo.java`** then **`java MixedNestedArrayDemo`**:

~~~text
shallow: false
deep: true
deep hash equal: true
display: [header, [5, 8], [A, B]]
~~~

Because the **`int[]`** and **`String[]`** elements are independently allocated, shallow comparison returns `false`. Deep comparison knows how to handle both nested primitive arrays and nested reference arrays.

**`Arrays.deepEquals/deepHashCode` still care about array type and structure.** For example, **`new int[]{1}`** is not automatically considered equal to **`new Integer[]{1}`**; having "the same numbers" is not enough for two differently typed arrays to share value semantics. If business logic wants to treat them as equivalent, you must convert them to a common value representation **before** comparing or hashing.

## 6. Implementing `equals` and `hashCode` for a Class with a 1D Array Field

This is the most common case: an object holds **`int[] samples`**, and the sequence of numbers constitutes the object's value. Using only **`Objects.equals(samples, other.samples)`** compares array references; using only **`Objects.hash(samples)`** can make the hash depend on the array's identity rather than the numbers inside.

Create the file **`IntVectorDemo.java`** with an externally immutable-looking key type:

~~~java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class IntVectorDemo {
    static final class IntVector {
        private final int[] values;

        IntVector(int[] values) {
            this.values = Arrays.copyOf(
                Objects.requireNonNull(values, "values"),
                values.length
            );
        }

        public int[] values() {
            return values.clone();
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof IntVector other)) {
                return false;
            }
            return Arrays.equals(values, other.values);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(values);
        }

        @Override
        public String toString() {
            return Arrays.toString(values);
        }
    }

    public static void main(String[] args) {
        int[] input = {2, 4};
        IntVector one = new IntVector(input);
        IntVector two = new IntVector(new int[]{2, 4});

        System.out.println("equal: " + one.equals(two));
        System.out.println("hash equal: " +
            (one.hashCode() == two.hashCode()));

        Set<IntVector> unique = new HashSet<>();
        System.out.println("add one: " + unique.add(one));
        System.out.println("add two: " + unique.add(two));
        System.out.println("set size: " + unique.size());

        input[0] = 99;
        System.out.println("after editing input: " + one);
        int[] exposedCopy = one.values();
        exposedCopy[1] = 77;
        System.out.println("after editing getter copy: " + one);
    }
}
~~~

Run:

~~~bash
javac IntVectorDemo.java
java IntVectorDemo
~~~

Output:

~~~text
equal: true
hash equal: true
add one: true
add two: false
set size: 1
after editing input: [2, 4]
after editing getter copy: [2, 4]
~~~

**Why must the array be copied?** If you retain the input reference directly or return the internal array from a getter, external code can mutate elements after the object is placed as a `HashMap`/`HashSet` key. Then **`hashCode` changes with the contents**, and lookups may stop working properly. The class above copies in the constructor and copies on return, so the data participating in `hashCode` cannot be mutated by external code.

**A `final` field does not mean an immutable array.** Declaring **`private final int[] values`** only prevents reassigning the `values` reference inside the class; it does not prevent **`values[0] = ...`**. If the class itself exposes a method that mutates the internal array, it is still a mutable key; for a stable key, ensure there is no path that mutates its contents.

**When there are multiple value fields:** include all fields compared by `equals`. For example, a class with **`String id`** and **`int[] samples`** can implement:

~~~java
// Snippet inside equals(Object), after confirming the type:
return Objects.equals(id, other.id)
    && Arrays.equals(samples, other.samples);

// Snippet inside hashCode():
return 31 * Objects.hashCode(id) + Arrays.hashCode(samples);
~~~

This is an **illustrative code snippet inside a class**, not a standalone program. Combining with multiplier `31` is a common choice, not the only one. What is mandatory is that **every pair equal under `equals` has the same `hashCode`**, not any single specific hash formula.

## 7. Implementing `equals` and `hashCode` for a Class Containing a Nested Array

For **`int[][] matrix`** treated as a structural value, you need **`Arrays.deepEquals`** and **`Arrays.deepHashCode`**. To keep the object stable as a key, you must also **copy every row**: cloning only the outer array is insufficient because the sub-arrays would still be shared.

Create the file **`MatrixKeyDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class MatrixKeyDemo {
    static final class MatrixKey {
        private final int[][] matrix;

        MatrixKey(int[][] source) {
            Objects.requireNonNull(source, "source");
            this.matrix = copyMatrix(source);
        }

        private static int[][] copyMatrix(int[][] source) {
            int[][] copy = new int[source.length][];
            for (int i = 0; i < source.length; i++) {
                copy[i] = source[i] == null
                    ? null
                    : source[i].clone();
            }
            return copy;
        }

        public int[][] getMatrix() {
            return copyMatrix(matrix);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof MatrixKey other)) {
                return false;
            }
            return Arrays.deepEquals(matrix, other.matrix);
        }

        @Override
        public int hashCode() {
            return Arrays.deepHashCode(matrix);
        }
    }

    public static void main(String[] args) {
        int[][] input = {
            {1, 2},
            null,
            {3}
        };

        MatrixKey one = new MatrixKey(input);
        MatrixKey two = new MatrixKey(new int[][]{
            {1, 2},
            null,
            {3}
        });

        System.out.println("equal: " + one.equals(two));
        System.out.println("hash equal: " +
            (one.hashCode() == two.hashCode()));

        Set<MatrixKey> keys = new HashSet<>();
        keys.add(one);
        keys.add(two);
        System.out.println("set size: " + keys.size());

        input[0][0] = 999;
        int[][] copy = one.getMatrix();
        copy[2][0] = 888;

        System.out.println("stable: " + one.equals(two));
    }
}
~~~

Run commands:

~~~bash
javac MatrixKeyDemo.java
java MatrixKeyDemo
~~~

Output:

~~~text
equal: true
hash equal: true
set size: 1
stable: true
~~~

In this example, both the outer array and each inner **`int[]`** are copied. The copy helper accepts `null` rows to match the inputs supported by **`deepEquals`/`deepHashCode`**. After construction, mutating the input array or the copy returned by the getter does not affect `MatrixKey`'s value.

If a matrix holds **mutable** objects at its leaves, cloning the outer and sub-arrays still copies only **references to those leaf objects**. When deep immutability is required, you need an appropriate copy policy or immutable types for the leaf objects; **`Arrays.deepHashCode` does not make contents immutable**.

## 8. Pitfalls with `Objects.hash`, `Objects.hashCode`, and `record`

### 8.1. `Objects.hash` Is Not a Drop-In Replacement for `Arrays.hashCode` on Every Array

**`Objects.hash(Object... values)`** is a varargs method that essentially hashes a **parameter `Object[]`**. For **`int[]`**, it treats the primitive array as **a single object element**, so the hash can rely on **the array's identity `hashCode`**. Therefore:

~~~java
int[] first = {1, 2};
int[] second = {1, 2};

// Illustrative snippet:
boolean contentEqual = java.util.Arrays.equals(first, second);  // true
boolean correctHashEqual =
    java.util.Arrays.hashCode(first) ==
    java.util.Arrays.hashCode(second);                           // true
~~~

This is a snippet, not a standalone file. **Do not replace `Arrays.hashCode(first)` with `Objects.hash(first)`** expecting the same primitive content-hashing rule.

For **`Object[]`**, a varargs call like **`Objects.hash(objectArray)`** may use the elements of `Object[]` directly as the parameter list, so behavior depends on array type and call form. Use the explicit **`Arrays.hashCode(Object[])`** or **`Arrays.deepHashCode(Object[])`** overload to avoid ambiguity and stay paired with `equals`.

**`Objects.hashCode(array)`** (singular, taking one `Object`) only calls **`array.hashCode()`** when non-null, so for arrays it **does not hash by content** either.

### 8.2. A `record` with an Array Field Does Not Automatically Compare Array Contents

A `record` generates **`equals`/`hashCode`** from its components, yet an array-typed component still uses **array `equals`/`hashCode`** semantics rather than automatically switching to **`Arrays.equals`** and **`Arrays.hashCode`**.

Create the file **`RecordArrayDemo.java`**:

~~~java
import java.util.Arrays;

public class RecordArrayDemo {
    record RawReading(int[] values) {}

    record ValueReading(int[] values) {
        ValueReading {
            values = values.clone();
        }

        @Override
        public int[] values() {
            return values.clone();
        }

        @Override
        public boolean equals(Object obj) {
            return obj instanceof ValueReading other
                && Arrays.equals(values, other.values);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(values);
        }
    }

    public static void main(String[] args) {
        RawReading raw1 = new RawReading(new int[]{1, 2});
        RawReading raw2 = new RawReading(new int[]{1, 2});
        ValueReading good1 = new ValueReading(new int[]{1, 2});
        ValueReading good2 = new ValueReading(new int[]{1, 2});

        System.out.println("generated equals: " + raw1.equals(raw2));
        System.out.println("custom equals: " + good1.equals(good2));
        System.out.println("custom hash equal: " +
            (good1.hashCode() == good2.hashCode()));
    }
}
~~~

Run:

~~~bash
javac RecordArrayDemo.java
java RecordArrayDemo
~~~

Output:

~~~text
generated equals: false
custom equals: true
custom hash equal: true
~~~

In **`ValueReading`**, the compact constructor clones the array component before storing it, the overridden accessor returns a copy, and `equals`/`hashCode` explicitly use the same `int[]` contents. Apply similar care to a **`record` with nested arrays**: cloning only the outer array is not enough; when using `deepEquals`/`deepHashCode`, you need a matching deep-immutability policy.

### 8.3. Floating-Point Types and `null` Elements

- **`Arrays.equals(float[], float[])`** and **`Arrays.equals(double[], double[])`** use rules matching **`Float.compare`** and **`Double.compare`** per element. This handles `NaN` and distinguishes **`+0.0`** from **`-0.0`** according to wrapper rules, rather than using the floating-point **`==`** operator directly.
- **`Arrays.hashCode(float[])`** and **`Arrays.hashCode(double[])`** are defined consistently with that exact array comparison. Do not write your own `equals` loop using **`==`** while keeping `Arrays.hashCode` without understanding the difference.
- **`Arrays.equals(Object[], Object[])`** handles `null` elements: two `null`s at the same index are equal; one `null` and one non-null value are not. **`Arrays.hashCode(Object[])`** and `deepHashCode` compute the matching hash for `null` positions.
- For top-level `null` arrays, **`Arrays.deepEquals((Object[]) null, (Object[]) null)`** returns `true` and **`Arrays.deepHashCode((Object[]) null)`** returns `0`. When a variable's declared type is ambiguous, specify the right overload or cast intentionally.

## 9. Limitations of `deepEquals` and `deepHashCode` You Should Know

**Do not use on cyclic-reference arrays.** An `Object[]` can contain itself or form a cycle across multiple arrays. The deep APIs are not designed to handle recursive array structures as general cyclic graphs; `deepHashCode` can recurse indefinitely and throw **`StackOverflowError`**. For cyclic graphs, you need a custom comparison/hashing model that tracks visited nodes alongside a clear definition of when two graphs are equal.

**Depth has a cost.** `Arrays.hashCode` on a 1D array must iterate over elements at that level; `deepHashCode` must traverse all nested arrays. Calling `hashCode` repeatedly on a key carries a real cost. Consider caching the hash only after designing the object to be truly immutable and having profiling justification; caching over mutable data can make `equals`/`hashCode` inconsistent.

**Element objects must have valid contracts.** If an `Object[]` holds a custom class whose `equals` checks field A while its `hashCode` uses field B, neither `Arrays.hashCode` nor `deepHashCode` can rescue the contract. Array methods only inherit correctness from their elements.

**Two unequal arrays can share the same hash.** For instance, 31-based hashing is a compression function mapping vast numbers of sequences into a 32-bit `int`. Never use a hash as a replacement for `equals`, content deduplication, or a security fingerprint.

**Dimensions and shape are part of the structure.** A matrix of one row with two elements and a matrix of two rows with one element each do not have the same `deepEquals` structure, even though a flattened listing of numbers might look similar. If the business domain wants to ignore shape, you must normalize the data to a canonical representation first.

**`Arrays.compare`, `Arrays.mismatch`, and `Comparator`** solve different problems: lexicographical ordering, first mismatch index, or custom-criteria comparison. Do not alter a key's `equals`/`hashCode` by default just because a `Comparator` is used in `TreeMap`/`TreeSet`. Sorted structures detect duplicate keys via **`compare == 0`**, which can differ from `equals` if the comparator is inconsistent with `equals`.

## 10. Testing the Contract and Making Choices in Real Problems

For a class with an array component, construct at least three objects **`a`, `b`, `c`**:

- **`a`** and **`b`** have identical content data, but their internal arrays are independently allocated.
- **`c`** differs from **`a`** in one element, one nested row, or another value field.
- Add edge cases for empty arrays, `null` sub-arrays (if allowed), `null` object elements, different element ordering, and objects whose input/getter arrays are mutated after construction.

Verify the following:

1. **`a.equals(b)`** is `true` if and only if contents are genuinely equal by business criteria; when using deep comparison, replacing a sub-array with a new array holding identical data does not change the result.
2. Whenever **`a.equals(b)`** is `true`, **`a.hashCode() == b.hashCode()`** is always `true`.
3. **`a.equals(c)`** is `false` if value criteria distinguish `a` and `c`. Do not assert that hashes must differ: collisions are valid.
4. Reflexivity, symmetry, transitivity, consistency, and `null` handling of **`equals`** must still hold.
5. Adding equal instances into a **`HashSet`** retains only one logical key; `HashMap` lookup using a distinct but equal-valued instance must succeed.
6. Try mutating the **input array** and the **array from the getter** after creating the key; if the class is designed to be immutable, the key's `equals`/`hashCode` do not change.
7. With nested arrays, ensure every array level participates in comparison under the chosen semantics; do not test only one row or cases that reuse the same array reference.

### Quick Decision Flow

| Question | What to choose |
| --- | --- |
| Is it a **1D** primitive array compared element-by-element? | **`Arrays.equals`** + **`Arrays.hashCode`** |
| Is it an **`Object[]`** without nested sub-arrays requiring deep traversal? | **`Arrays.equals`** + **`Arrays.hashCode`** |
| Is it a multidimensional array or an `Object[]` containing sub-arrays **where nested content comparison is desired**? | **`Arrays.deepEquals`** + **`Arrays.deepHashCode`** |
| Is the array field inside a **`record`** or custom class? | Override **both `equals` and `hashCode`** if you want array-content equality |
| Is the object used as a `HashMap`/`HashSet` key? | Ensure arrays participating in comparison are **stable/immutable**, using defensive copies when needed |
| Does the data contain cyclic structures or special comparison criteria? | Design a **custom value type and algorithm**, rather than relying directly on deep APIs |

**Remember:** **`equals` and `hashCode` must look at the same "value shape"**. If `equals` compares 1D contents, `hashCode` hashes 1D contents; if `equals` recurses into sub-arrays, `hashCode` must also recurse using the matching rule. **`Arrays.hashCode`** pairs with **`Arrays.equals`**; **`Arrays.deepHashCode`** pairs with **`Arrays.deepEquals`**. In a class containing arrays, picking the right function is only the first step: keeping key data stable is what makes the contract work reliably in hash-based structures.