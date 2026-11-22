# Java record: `equals()`, `hashCode()`, `toString()`, and the Impact of Array Components

## 1. Why Is This Topic Important?

Records in Java 17+ allow defining a **value-carrying data type** using a list of components (*record components*) placed in the header:

```java
record Point(int x, int y) {}
```

If the author does not declare them explicitly, the compiler provides `equals(Object)`, `hashCode()`, and `toString()` based on the record components. For types like `int` or `String`, these three methods are usually exactly what the author expects from a value object.

But consider:

```java
record Numbers(int[] values) {}
```

An `int[]` array is a **reference object**. Java arrays do not override `Object.equals` to compare element by element; two different arrays that both contain 1, 2 **are not equal according to Object.equals**. The generated record methods do not automatically turn an array into a value object. As a result:

- The default `equals()` compares **the reference of the array component**, not the sequence of elements.
- The default `hashCode()` is consistent with that kind of equality, not the content hash of the array.
- The default `toString()` usually prints an array object identity representation such as `[I@...` instead of all the numbers.
- The component field is `final`, but **the array elements can still be modified**.
- Defensive copying only solves aliasing; if true value equality is desired, `equals`, `hashCode`, and possibly `toString` must be designed consistently.

> **Principle:** A record generates value-oriented methods according to the **semantics of its component types**. It does not automatically perform deep comparison, deep copying, or deep formatting for every object graph.

This lesson will analyze each case, experiment with one-dimensional arrays, two-dimensional arrays, `Object[]`, and `List`, compare copies and using them as keys in collections, and then build an array record with a consistent contract. The examples have standalone files for Java 17, run commands, and deterministic stdout.

## 2. Pure Primitive/String Records and the Three Default Methods

Create **`RecordSimpleValueDemo.java`**:

```java
record Employee(String id, int grade) {}

public class RecordSimpleValueDemo {
    public static void main(String[] args) {
        Employee a = new Employee("E-1", 3);
        Employee b = new Employee("E-1", 3);
        Employee c = new Employee("E-1", 4);

        System.out.println(a == b);
        System.out.println(a.equals(b));
        System.out.println(a.equals(c));
        System.out.println(a.hashCode() == b.hashCode());
        System.out.println(a);
    }
}
```

```bash
javac RecordSimpleValueDemo.java
java RecordSimpleValueDemo
```

```text
false
true
false
true
Employee[id=E-1, grade=3]
```

The two objects `a` and `b` are created with two `new` calls, so `==` is false, yet they are equal based on the two component values. Their `hashCode` values must be equal according to the contract. `toString` displays the names and values of the components.

**Limitation:** Two records with the same text in `toString` are not necessarily equal if the display policy hides differences. Identical hashCodes also do not imply equality, because collisions are valid.

## 3. What Exactly Does the Generated `equals` Mean?

The generated `equals` checks for **the same record class**, and then checks the equality of each corresponding component.

| Component type | Default comparison |
| --- | --- |
| `int`, `long`, `boolean`, `char`… | By the corresponding primitive type; for floating-point types, follows rules matching wrapper comparison |
| `String` | `String.equals` by content |
| `BigDecimal` | `BigDecimal.equals`, taking scale into account |
| `List<Integer>` | `List.equals` by elements and order |
| `int[]` | Array reference identity |
| `String[]` | Array reference identity |
| `int[][]` | Array reference identity on the outer array component |
| Arbitrary object | According to the object's `equals` implementation |
| `null` | Two nulls in the corresponding component are equal |

For `float`/`double`, the generated record equality behaves consistently with primitive-wrapper comparison, handling NaN and the sign of zero according to the record specification semantics; do not simplify every primitive type into an `==` expression.

**Having the same field name is not enough:** `record First(int n)` and `record Second(int n)` are two different types and are not equal even if n is the same.

## 4. Java Arrays: Reference Equality Differs from Content Equality

Create **`ArrayIdentityVersusContentDemo.java`**:

```java
import java.util.Arrays;

public class ArrayIdentityVersusContentDemo {
    public static void main(String[] args) {
        int[] a = {1, 2};
        int[] b = {1, 2};
        int[] alias = a;

        System.out.println(a == b);
        System.out.println(a.equals(b));
        System.out.println(Arrays.equals(a, b));
        System.out.println(a == alias);
        System.out.println(a.equals(alias));
    }
}
```

```bash
javac ArrayIdentityVersusContentDemo.java
java ArrayIdentityVersusContentDemo
```

```text
false
false
true
true
true
```

`a` and `b` are two different array objects, even though they have the same content. `a.equals(b)` is `Object.equals` based on identity. Only `Arrays.equals(a,b)` iterates through the elements of a one-dimensional array. `alias` points to the exact same object a, so the reference checks are all true.

This is the foundation for understanding all behavior of records with an array component.

## 5. Record Containing an Array: Same Content, but Generated equals Is False

Create **`RecordArrayEqualsDemo.java`**:

```java
import java.util.Arrays;

record Numbers(int[] values) {}

public class RecordArrayEqualsDemo {
    public static void main(String[] args) {
        Numbers first = new Numbers(new int[] {1, 2});
        Numbers second = new Numbers(new int[] {1, 2});

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(
                Arrays.equals(first.values(), second.values()));
        System.out.println(
                first.values() == second.values());
    }
}
```

```bash
javac RecordArrayEqualsDemo.java
java RecordArrayEqualsDemo
```

```text
false
false
true
false
```

`Numbers` has one component that is **a reference to int[]**. The generated equals compares the reference semantics of the component; it does not turn `values` into a logical sequence with content equality.

If the business goal is "two Numbers carrying the same sequence of numbers are equal", design intervention is needed. On the other hand, if the goal is "two Numbers are equal only when they share the same buffer", the default behavior may be intentional.

## 6. Two Records Using the Same Array Object Can Actually Be Equal

Create **`RecordSharedArrayDemo.java`**:

```java
record Numbers(int[] values) {}

public class RecordSharedArrayDemo {
    public static void main(String[] args) {
        int[] shared = {1, 2};

        Numbers a = new Numbers(shared);
        Numbers b = new Numbers(shared);
        Numbers c = new Numbers(shared.clone());

        System.out.println(a == b);
        System.out.println(a.equals(b));
        System.out.println(a.equals(c));
        System.out.println(a.values() == b.values());
    }
}
```

```bash
javac RecordSharedArrayDemo.java
java RecordSharedArrayDemo
```

```text
false
true
false
true
```

`a` and `b` are two different record instances, yet both hold the reference `shared`, so the generated equals is true. `c` holds a clone that is a different object: its values have identical content, yet the generated equals is false.

**General rule:** Record equality depends on the **equality of each component**, not on a "looks like a value" promise in the record's name.

## 7. If There Are Multiple Components, All Must Be Correspondingly Equal

Create **`RecordMixedComponentsDemo.java`**:

```java
import java.util.Arrays;

record Reading(String unit, int[] samples) {}

public class RecordMixedComponentsDemo {
    public static void main(String[] args) {
        int[] shared = {10, 20};

        Reading a = new Reading("C", shared);
        Reading b = new Reading("C", shared);
        Reading c = new Reading("C", new int[] {10, 20});
        Reading d = new Reading("F", shared);

        System.out.println(a.equals(b));
        System.out.println(a.equals(c));
        System.out.println(a.equals(d));
        System.out.println(
                Arrays.equals(a.samples(), c.samples()));
    }
}
```

```bash
javac RecordMixedComponentsDemo.java
java RecordMixedComponentsDemo
```

```text
true
false
false
true
```

a/b: String has the same value and the arrays share the same reference. a/c: String is the same, but the arrays have different references. a/d: arrays share the same reference, but unit is different. If you want content equality for the array, it must be handled explicitly; simply having another component be equal is not enough.

## 8. The `equals()` and `hashCode()` Contract

Two things must be distinguished:

- **If `a.equals(b)` is true, `a.hashCode() == b.hashCode()` must be true.**
- If two objects are not equal, their hashCodes **can still match** due to a collision.

The generated methods of a record are built to be consistent with one another. When an array component uses reference equality, the generated hash does not promise to reflect the array contents either. Therefore, the following test is meaningful:

Create **`RecordArrayHashContractDemo.java`**:

```java
record Data(int[] values) {}

public class RecordArrayHashContractDemo {
    public static void main(String[] args) {
        int[] shared = {2, 4};
        Data a = new Data(shared);
        Data b = new Data(shared);
        Data c = new Data(new int[] {2, 4});

        System.out.println(a.equals(b));
        System.out.println(a.hashCode() == b.hashCode());
        System.out.println(a.equals(c));
    }
}
```

```bash
javac RecordArrayHashContractDemo.java
java RecordArrayHashContractDemo
```

```text
true
true
false
```

There is no mandatory check that the hashCodes of a and c differ, because hash collisions are valid; nor are fixed hash numbers printed as expected output.

**A design principle:** If you override `equals` to use `Arrays.equals` on the contents, you must also override `hashCode` with a compatible algorithm such as `Arrays.hashCode`. You should not customize one side while omitting the other.

## 9. Default `toString()` Does Not Automatically Print Array Contents

The generated `toString()` usually represents a record in the form `Type[component=value]`. However, an array type does not have a content-based `toString`: `int[]` is usually displayed in the form `[I@...` containing the identity hash.

Create **`RecordArrayToStringDemo.java`**:

```java
import java.util.Arrays;

record Numbers(int[] values) {}

public class RecordArrayToStringDemo {
    public static void main(String[] args) {
        Numbers numbers = new Numbers(new int[] {1, 2});

        System.out.println(
                Arrays.toString(numbers.values()));
        System.out.println(
                numbers.toString().startsWith(
                        "Numbers[values=[I@"));
    }
}
```

```bash
javac RecordArrayToStringDemo.java
java RecordArrayToStringDemo
```

```text
[1, 2]
true
```

The example only prints a check of a display characteristic, **not the full `[I@...` string**, because the suffix depends on the object/JVM and should not be hardcoded.

`Arrays.toString` prints the values of a one-dimensional array. If you want clean record logging, override `toString` intentionally. However, custom display **does not change `equals/hashCode`**.

## 10. Two Identical toString Outputs Still Do Not Mean Equal

Create **`PrettyButUnequalDemo.java`**:

```java
import java.util.Arrays;

record Numbers(int[] values) {
    @Override
    public String toString() {
        return "Numbers" + Arrays.toString(values);
    }
}

public class PrettyButUnequalDemo {
    public static void main(String[] args) {
        Numbers a = new Numbers(new int[] {1, 2});
        Numbers b = new Numbers(new int[] {1, 2});

        System.out.println(a);
        System.out.println(b);
        System.out.println(a.equals(b));
    }
}
```

```bash
javac PrettyButUnequalDemo.java
java PrettyButUnequalDemo
```

```text
Numbers[1, 2]
Numbers[1, 2]
false
```

This is a reasoning error when debugging: two identical log lines prove that the formatter produced the same text; **they do not prove that `equals` returns true**.

`toString` is meant for reading/logging, not for stable serialization or an identity contract. With sensitive data, you must also check whether toString accidentally leaks secrets.

## 11. Choosing the Right `Arrays` Utilities for One-Dimensional Arrays

The overloads `Arrays.equals(int[],int[])`, `Arrays.hashCode(int[])`, and `Arrays.toString(int[])` work with the contents of a one-dimensional int array.

Create **`ArrayContentHelpersDemo.java`**:

```java
import java.util.Arrays;

public class ArrayContentHelpersDemo {
    public static void main(String[] args) {
        int[] first = {1, 2, 3};
        int[] same = {1, 2, 3};
        int[] reordered = {3, 2, 1};

        System.out.println(Arrays.equals(first, same));
        System.out.println(Arrays.equals(first, reordered));
        System.out.println(
                Arrays.hashCode(first) == Arrays.hashCode(same));
        System.out.println(Arrays.toString(first));
    }
}
```

```bash
javac ArrayContentHelpersDemo.java
java ArrayContentHelpersDemo
```

```text
true
false
true
[1, 2, 3]
```

**Element order matters:** two arrays containing the same set of numbers reordered are not equal. If the domain treats the contents as a set or multiset, a different representation or normalization/comparison is needed; do not use `Arrays.equals` mechanically.

## 12. Two-Dimensional Arrays: `equals` and `deepEquals` Differ

`int[][]` is an array containing array references. `Arrays.equals(matrixA,matrixB)` at the outer level uses the equality of the row array objects; to deeply compare the contents of each row, use `Arrays.deepEquals`.

Create **`NestedArrayComparisonDemo.java`**:

```java
import java.util.Arrays;

public class NestedArrayComparisonDemo {
    public static void main(String[] args) {
        int[][] a = {{1, 2}, {3, 4}};
        int[][] b = {{1, 2}, {3, 4}};

        System.out.println(Arrays.equals(a, b));
        System.out.println(Arrays.deepEquals(a, b));
        System.out.println(
                Arrays.deepHashCode(a) ==
                Arrays.deepHashCode(b));
        System.out.println(Arrays.deepToString(a));
    }
}
```

```bash
javac NestedArrayComparisonDemo.java
java NestedArrayComparisonDemo
```

```text
false
true
true
[[1, 2], [3, 4]]
```

`Arrays.deepEquals` and `Arrays.deepHashCode` are a compatible pair when deep array contents are wanted. `Arrays.deepToString` provides a representation of nested content.

**Do not mistake this:** A record containing an `int[][]` component still compares **the reference of the outer array** by default; the compiler does not automatically call `deepEquals`.

## 13. A Record with `String[]` Is Still Affected Even Though String Is Immutable

Create **`RecordStringArrayDemo.java`**:

```java
import java.util.Arrays;

record Tags(String[] values) {}

public class RecordStringArrayDemo {
    public static void main(String[] args) {
        Tags a = new Tags(new String[] {"java", "record"});
        Tags b = new Tags(new String[] {"java", "record"});

        System.out.println(a.equals(b));
        System.out.println(
                Arrays.equals(a.values(), b.values()));
    }
}
```

```bash
javac RecordStringArrayDemo.java
java RecordStringArrayDemo
```

```text
false
true
```

Two Strings have the same content at each position, yet **two different arrays** still cause the generated record equals to be false. The element type does not give an array object content equality automatically.

For an `Object[]` containing arrays, `Arrays.equals` at the outer layer still does not compare deeply inside. Use `Arrays.deepEquals` if the domain truly wants nested content equality.

## 14. A Record Component Being `private final` Does Not Mean the Array Is Immutable

Generated record component fields are `private final`. The final keyword **locks reassignment of the field reference**; it does not freeze the referenced object.

Create **`RecordArrayAliasingDemo.java`**:

```java
import java.util.Arrays;

record Snapshot(int[] values) {}

public class RecordArrayAliasingDemo {
    public static void main(String[] args) {
        int[] input = {5, 6};
        Snapshot snapshot = new Snapshot(input);

        input[0] = 9;
        System.out.println(
                Arrays.toString(snapshot.values()));

        snapshot.values()[1] = 8;
        System.out.println(Arrays.toString(input));
    }
}
```

```bash
javac RecordArrayAliasingDemo.java
java RecordArrayAliasingDemo
```

```text
[9, 6]
[9, 8]
```

The generated constructor stores the input array reference, and the generated accessor returns that reference. There is no implicit defensive copying.

This differs from a String component: String is immutable by contract, so its reference can be shared without allowing the contents of the String instance to be modified.

## 15. Equality Can Remain Unchanged After Modifying the Contents of a Shared Array

Create **`SharedArrayMutationDemo.java`**:

```java
record Data(int[] values) {}

public class SharedArrayMutationDemo {
    public static void main(String[] args) {
        int[] shared = {1};
        Data a = new Data(shared);
        Data b = new Data(shared);

        System.out.println(a.equals(b));
        shared[0] = 99;
        System.out.println(a.equals(b));
        System.out.println(b.values()[0]);
    }
}
```

```bash
javac SharedArrayMutationDemo.java
java SharedArrayMutationDemo
```

```text
true
true
99
```

`a` and `b` still share the same array reference after the mutation. Generated equality does not care whether the array contains 1 or 99. Therefore, **generated equals is not a check that array data remains unchanged**.

If the business contract wants a value snapshot, defensive copying and content-based equality are required.

## 16. Designing an `IntVector` Record with True Value Equality

Goal: two vectors with the same values are equal; input/output prevent aliases from mutating state; compatible hash; toString displays contents. Create **`IntVectorValueDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

record IntVector(int[] values) {
    IntVector {
        values = Objects.requireNonNull(values).clone();
    }

    @Override
    public int[] values() {
        return values.clone();
    }

    @Override
    public boolean equals(Object other) {
        return this == other
                || (other instanceof IntVector vector
                    && Arrays.equals(values, vector.values));
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(values);
    }

    @Override
    public String toString() {
        return "IntVector" + Arrays.toString(values);
    }
}

public class IntVectorValueDemo {
    public static void main(String[] args) {
        int[] source = {1, 2};

        IntVector a = new IntVector(source);
        IntVector b = new IntVector(new int[] {1, 2});

        System.out.println(a.equals(b));
        System.out.println(
                a.hashCode() == b.hashCode());

        source[0] = 9;
        int[] extracted = a.values();
        extracted[1] = 8;

        System.out.println(a);
        System.out.println(b);
        System.out.println(Arrays.toString(source));
    }
}
```

```bash
javac IntVectorValueDemo.java
java IntVectorValueDemo
```

```text
true
true
IntVector[1, 2]
IntVector[1, 2]
[9, 2]
```

### Why Is This Design Consistent?

1. The compact constructor clones the input `int[]`; `Objects.requireNonNull` defines the null policy.
2. The accessor override clones the output so the internal array is not exposed.
3. `equals` compares the **internal arrays by content** using `Arrays.equals`.
4. `hashCode` evaluates the same representation using `Arrays.hashCode`.
5. `toString` uses `Arrays.toString` to print the contents.
6. The numbers are primitives; cloning the one-dimensional array is sufficient to isolate element values.

Do not use a JavaBean-style getter name `getValues()` here: the record accessor is named `values()`, and the override must have a compatible signature.

## 17. Both Defensive Copy Boundaries Are Necessary

**Cloning only in the constructor** still leaves the generated accessor returning the internal array:

```java
record OnlyInput(int[] values) {
    OnlyInput {
        values = values.clone();
    }
}
```

A client can still modify `onlyInput.values()[0]`.

**Cloning only in the accessor** still leaves the constructor holding an alias to the input:

```java
record OnlyOutput(int[] values) {
    @Override
    public int[] values() {
        return values.clone();
    }
}
```

A client holding the original input array can mutate the data inside the record.

The two forms above are **two separate declarations illustrating two different flaws**, without a `main`. An immutable-value contract requires controlling both the **data-receiving** and **data-returning** boundaries.

## 18. Defensive Copying Can Break Record Copying Expectations if Generated equals Is Kept

This is a subtler trap: if you clone input and output while still keeping the generated identity-based equals, then a copy created from the component accessor may **not equal** the original.

Create **`RecordCopyInvariantTrapDemo.java`**:

```java
record SafeArray(int[] values) {
    SafeArray {
        values = values.clone();
    }

    @Override
    public int[] values() {
        return values.clone();
    }
}

public class RecordCopyInvariantTrapDemo {
    public static void main(String[] args) {
        SafeArray original =
                new SafeArray(new int[] {1, 2});
        SafeArray copy = new SafeArray(original.values());

        System.out.println(original.equals(copy));
        System.out.println(
                java.util.Arrays.equals(
                        original.values(), copy.values()));
    }
}
```

```bash
javac RecordCopyInvariantTrapDemo.java
java RecordCopyInvariantTrapDemo
```

```text
false
true
```

Because original and copy hold **two different internal array references**, the generated equals is false. Yet their contents are equal.

### Copying Invariant (*copy invariant*)

The value-carrier semantics of a record aim toward an invariant: if you retrieve the component values via accessors and reconstruct the same record type, the copy must be equal to the original.

```java
// Conceptual form, for record R(c1, c2, ...):
R copy = new R(original.c1(), original.c2(), ...);
// Desired: original.equals(copy) == true.
```

This is **illustrative pseudocode**, not standalone runnable Java.

Cloning combined with generated identity-based array equals can break that expectation. Therefore, **defensive copying must be paired with equality/hash matching the logical values**, or you need to change the representation.

## 19. Another Option: Structurally Immutable `List<Integer>`

If the API is not required to use a primitive array, a `List<Integer>` with immutable elements can simplify equality.

Create **`ImmutableListRecordDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

record Values(List<Integer> items) {
    Values {
        items = List.copyOf(items);
    }
}

public class ImmutableListRecordDemo {
    public static void main(String[] args) {
        List<Integer> input =
                new ArrayList<>(List.of(1, 2));

        Values first = new Values(input);
        Values second = new Values(List.of(1, 2));

        System.out.println(first.equals(second));
        System.out.println(
                first.hashCode() == second.hashCode());

        input.add(3);
        System.out.println(first);

        try {
            first.items().add(4);
        } catch (UnsupportedOperationException ex) {
            System.out.println("cannot add");
        }
    }
}
```

```bash
javac ImmutableListRecordDemo.java
java ImmutableListRecordDemo
```

```text
true
true
Values[items=[1, 2]]
cannot add
```

`List.copyOf` creates/provides an unmodifiable snapshot for a mutable input structure. `List.equals` compares the elements in order, and `Integer` is immutable. Therefore, the generated equals/hash/toString of this record have appropriate value semantics.

**Do not assume that `List.copyOf` deep-copies every element**. A `List<StringBuilder>` or `List<int[]>` can still hold references to mutable elements.

## 20. With `List<int[]>`, the Problem Still Exists at the Element Layer

Consider:

```java
record Rows(java.util.List<int[]> parts) {
    Rows {
        parts = java.util.List.copyOf(parts);
    }
}
```

This is an **illustrative declaration**.

`List.equals` compares elements using equals. However, each element is an `int[]`, meaning the array still uses identity equality. Two Rows with two Lists containing arrays that are different objects yet have the same contents are still not equal under default record equality.

**Multi-layer principle:** An outer collection having value equality does not automatically give every inner element value equality as well. You need to inspect the entire chain of nested types before choosing generated methods.

## 21. For a Matrix, Use the `deepEquals/deepHashCode` Pair

Create **`MatrixDeepMethodsDemo.java`**:

```java
import java.util.Arrays;

record Matrix(int[][] rows) {
    @Override
    public boolean equals(Object other) {
        return this == other
                || (other instanceof Matrix m
                    && Arrays.deepEquals(rows, m.rows));
    }

    @Override
    public int hashCode() {
        return Arrays.deepHashCode(rows);
    }

    @Override
    public String toString() {
        return "Matrix" + Arrays.deepToString(rows);
    }
}

public class MatrixDeepMethodsDemo {
    public static void main(String[] args) {
        Matrix a = new Matrix(
                new int[][] {{1, 2}, {3, 4}});
        Matrix b = new Matrix(
                new int[][] {{1, 2}, {3, 4}});

        System.out.println(a.equals(b));
        System.out.println(
                a.hashCode() == b.hashCode());
        System.out.println(a);
    }
}
```

```bash
javac MatrixDeepMethodsDemo.java
java MatrixDeepMethodsDemo
```

```text
true
true
Matrix[[1, 2], [3, 4]]
```

This approach customizes **two-dimensional content equality** and provides a readable display. However, it is **not yet immutable**, because the generated constructor/accessor still stores/returns array references. If the matrix serves as a HashMap key, defensive copying to the proper depth is required.

## 22. Copying Multi-Dimensional Arrays: Cloning the Outer Array Is Not Enough

For `int[][]`, calling `rows.clone()` only creates a new outer array; the inner `int[]` rows still share references.

To isolate primitive matrix values, clone both the **outer structure** and **each row**.

Create **`ImmutableMatrixRecordDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

record Matrix(int[][] rows) {
    Matrix {
        rows = copy(rows);
    }

    private static int[][] copy(int[][] source) {
        Objects.requireNonNull(source, "rows");

        int[][] result = new int[source.length][];
        for (int i = 0; i < source.length; i++) {
            result[i] = Objects.requireNonNull(
                    source[i], "row").clone();
        }
        return result;
    }

    @Override
    public int[][] rows() {
        return copy(rows);
    }

    @Override
    public boolean equals(Object other) {
        return this == other
                || (other instanceof Matrix m
                    && Arrays.deepEquals(rows, m.rows));
    }

    @Override
    public int hashCode() {
        return Arrays.deepHashCode(rows);
    }

    @Override
    public String toString() {
        return "Matrix" + Arrays.deepToString(rows);
    }
}

public class ImmutableMatrixRecordDemo {
    public static void main(String[] args) {
        int[][] input = {{1, 2}, {3, 4}};

        Matrix a = new Matrix(input);
        Matrix b = new Matrix(
                new int[][] {{1, 2}, {3, 4}});

        input[0][0] = 9;

        int[][] extracted = a.rows();
        extracted[1][1] = 8;

        System.out.println(a.equals(b));
        System.out.println(
                a.hashCode() == b.hashCode());
        System.out.println(a);
        System.out.println(
                Arrays.deepToString(input));
    }
}
```

```bash
javac ImmutableMatrixRecordDemo.java
java ImmutableMatrixRecordDemo
```

```text
true
true
Matrix[[1, 2], [3, 4]]
[[9, 2], [3, 4]]
```

### Scope of Guarantees

- Input/output do not share the outer array or primitive rows.
- `Arrays.deepEquals` and `Arrays.deepHashCode` are based on contents.
- A null outer array/row is explicitly rejected.
- The example accepts ragged arrays (rows of differing lengths); if the domain requires a rectangular matrix, add validation.
- For `Object[][]`, cloning each row **does not clone the object elements**. Deep immutability requires checking types and copying according to a dedicated policy.

## 23. `null` and an Empty Array Are Not the Same Value

Record reference components can be null if the constructor does not forbid it.

Create **`RecordNullArrayDemo.java`**:

```java
record Data(int[] values) {}

public class RecordNullArrayDemo {
    public static void main(String[] args) {
        Data a = new Data(null);
        Data b = new Data(null);
        Data c = new Data(new int[0]);

        System.out.println(a.equals(b));
        System.out.println(a.equals(c));
        System.out.println(a);
        System.out.println(
                java.util.Arrays.toString((int[]) null));
    }
}
```

```bash
javac RecordNullArrayDemo.java
java RecordNullArrayDemo
```

```text
true
false
Data[values=null]
null
```

A null component represents the absence of a reference; an empty array is an array object of length 0. If the domain forbids null, validate it in the compact/canonical constructor. If the domain wants to turn null into an empty array, make an explicit normalization decision.

`Arrays.equals`/`Arrays.hashCode` have overloads that handle null appropriately, but do not let API conveniences replace business validation.

## 24. Records Containing Arrays and `HashMap`: The Lookup Shock

Create **`RecordArrayMapKeyDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;

record Key(int[] numbers) {}

public class RecordArrayMapKeyDemo {
    public static void main(String[] args) {
        Map<Key, String> map = new HashMap<>();

        int[] shared = {1, 2};
        map.put(new Key(shared), "stored");

        System.out.println(map.get(new Key(shared)));
        System.out.println(
                map.get(new Key(new int[] {1, 2})));
        System.out.println(map.size());
    }
}
```

```bash
javac RecordArrayMapKeyDemo.java
java RecordArrayMapKeyDemo
```

```text
stored
null
1
```

HashMap is not broken: two keys with different component arrays are not equal under the generated methods, so looking up with a new array fails to find the entry. This is especially dangerous if you use the Key record expecting it to represent a "sequence of numbers as a key".

**How to fix:** Switch to an immutable value representation such as List<Integer>, or have the record defensively copy arrays and customize equals/hashCode by content.

## 25. When Using Content Hash, a Mutable Array Makes a Map Key Unstable

Suppose a record overrides `hashCode` with `Arrays.hashCode` without defensively copying input/output. The array contents can change **after map.put**, causing the key's hashCode to change. A subsequent `map.get` may then look in a different bucket and fail to find the entry.

This is an **ownership and mutability bug**, not a HashMap bug.

Create **`SafeVectorMapKeyDemo.java`**:

```java
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;

record VectorKey(int[] values) {
    VectorKey {
        values = values.clone();
    }

    @Override
    public int[] values() {
        return values.clone();
    }

    @Override
    public boolean equals(Object other) {
        return this == other
                || (other instanceof VectorKey v
                    && Arrays.equals(values, v.values));
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(values);
    }
}

public class SafeVectorMapKeyDemo {
    public static void main(String[] args) {
        int[] source = {1, 2};

        VectorKey key = new VectorKey(source);
        Map<VectorKey, String> map = new HashMap<>();
        map.put(key, "FOUND");

        source[0] = 99;

        System.out.println(
                map.get(new VectorKey(new int[] {1, 2})));
        System.out.println(map.containsKey(key));
    }
}
```

```bash
javac SafeVectorMapKeyDemo.java
java SafeVectorMapKeyDemo
```

```text
FOUND
true
```

`VectorKey` holds no alias to the source array; the hash is based on internal values that cannot be mutated through the accessor. This is a suitable approach for serving as a map key by sequence of values.

## 26. `HashSet` Also Operates According to the Existing Equality

Create **`RecordArraySetDemo.java`**:

```java
import java.util.HashSet;
import java.util.Set;

record Item(int[] digits) {}

public class RecordArraySetDemo {
    public static void main(String[] args) {
        Set<Item> items = new HashSet<>();

        items.add(new Item(new int[] {1, 2}));
        items.add(new Item(new int[] {1, 2}));

        System.out.println(items.size());
    }
}
```

```bash
javac RecordArraySetDemo.java
java RecordArraySetDemo
```

```text
2
```

Both entries exist because the two `int[]` arrays are different references. If the domain wants to deduplicate records with the same contents, the default record methods do not express the right contract.

**Do not test that two hashCodes must be different.** HashSet only requires the equality/hash contract; unequal objects can happen to have a hash collision, yet the Set still holds both.

## 27. Note on `Objects.hash` and Arrays

`Objects.hash` does not automatically perform deep hashing for arrays as one might expect.

Illustrative example inside a method:

```java
int[] array = {1, 2};

int byContents = java.util.Arrays.hashCode(array);
int byReferenceInVarargs =
        java.util.Objects.hash((Object) array);
```

`Arrays.hashCode(int[])` iterates through the elements; `Objects.hash((Object)array)` treats the array reference as a single element in the varargs list and does not automatically iterate through the int elements.

With `Object[]`, passing the array directly into varargs can also make the distinction between the entire array and its contents ambiguous. Choose the helper **that matches the equality you defined**:

- One-dimensional: `Arrays.equals` + `Arrays.hashCode`.
- Nested arrays: `Arrays.deepEquals` + `Arrays.deepHashCode`.
- Custom domain normalization: compute the hash from the same canonical representation.

## 28. When Are Generated Methods Still Suitable for Arrays?

Not every record with an array component must override these methods. There are business cases where you want to compare **the array/buffer object itself**—for example, two descriptors pointing to the same buffer resource are considered equal, whereas two different buffers are not equal even if their contents are the same.

In that case:

- Reference-based generated equality can be intentional.
- The generated hashCode is compatible with that equality.
- The generated toString may still not be readable enough, and you can still override the display separately.
- You need to clearly document that the array object can mutate, as well as aliasing and lifetime.

However, if the record represents a **logical value** such as an immutable vector, a time-series snapshot, or a binary content fingerprint, then array identity is usually **not** what API users expect.

## 29. When Should Array Components Be Avoided?

If the data has a small and fixed number of elements, named primitive components are usually simpler:

```java
record RGB(int red, int green, int blue) {}
record RGBArray(int[] channels) {}
```

Create **`FixedComponentsDemo.java`**:

```java
record RGB(int red, int green, int blue) {}
record RGBArray(int[] channels) {}

public class FixedComponentsDemo {
    public static void main(String[] args) {
        RGB a = new RGB(10, 20, 30);
        RGB b = new RGB(10, 20, 30);

        RGBArray x =
                new RGBArray(new int[] {10, 20, 30});
        RGBArray y =
                new RGBArray(new int[] {10, 20, 30});

        System.out.println(a.equals(b));
        System.out.println(x.equals(y));
        System.out.println(a);
    }
}
```

```bash
javac FixedComponentsDemo.java
java FixedComponentsDemo
```

```text
true
false
RGB[red=10, green=20, blue=30]
```

The three channels form a dataset with fixed names and dimension; placing them separately in the header takes advantage of the generated equality and natural display. When the sequence length varies by input, using an array/List or a dedicated array-wrapping type still makes sense.

## 30. Distinguishing `Arrays.toString` and `Arrays.deepToString` for Logging

For int[]:

```java
java.util.Arrays.toString(new int[] {1, 2})
```

returns the String `[1, 2]`.

For int[][]:

```java
java.util.Arrays.deepToString(
        new int[][] {{1, 2}, {3, 4}})
```

returns the String `[[1, 2], [3, 4]]`.

However, the generated `record.toString()` for an int[][] component does not automatically use deepToString. Do not hardcode strings like `[I@...` or `[[I@...` in tests; they contain unstable identity-based details.

Even if you customize toString to look nice, **do not use toString as a storage format, key, or JSON contract**. Serializers should be designed explicitly; the output of toString can change for debugging purposes without breaking data.

## 31. Be Careful with Sensitive Components

If a component holds `byte[] secret`, the generated toString usually does not directly print the bytes by content, yet this **is not a security mechanism**:

- The record accessor can return the internal array reference.
- Code with access to the record can still read the secret bytes.
- Other components such as a String token can be exposed verbatim in the generated toString.
- A custom formatter may print the bytes if it uses Arrays.toString without checking for sensitive data.
- Logs may be retained in systems long-term.

Therefore, build dedicated policies for redaction, key management, and access control. **Do not rely on an array identity string as a form of secret encryption**.

## 32. No Need to Deep-Clone Every Array at All Costs

Deep copying incurs memory, CPU, and design costs. Ask:

1. Is the object an immutable value?
2. Does anyone hold a reference to the input array?
3. Does the array contain primitives, immutable references, or mutable objects?
4. Is the object used as a map key?
5. Is it necessary to return data from the accessor with a no-copy performance contract?
6. Does a two-dimensional array need rectangular validation?
7. Is the dataset too large to clone on every read?

If the domain allows a mutable shared buffer, a record with a final reference and mutable contents can be an intentional API, provided the contract states it clearly. If a true immutable value is desired, consider a different representation rather than hiding the copy cost.

## 33. Self-Testing a Value Vector Record

Create **`VectorRecordSelfTest.java`**:

```java
import java.util.Arrays;

record Vector(int[] values) {
    Vector {
        values = values.clone();
    }

    @Override
    public int[] values() {
        return values.clone();
    }

    @Override
    public boolean equals(Object other) {
        return this == other
                || (other instanceof Vector v
                    && Arrays.equals(values, v.values));
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(values);
    }

    @Override
    public String toString() {
        return "Vector" + Arrays.toString(values);
    }
}

public class VectorRecordSelfTest {
    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        int[] input = {1, 2};

        Vector a = new Vector(input);
        Vector b = new Vector(new int[] {1, 2});
        Vector c = new Vector(new int[] {2, 1});
        Vector copy = new Vector(a.values());

        check(a.equals(a), "reflexive");
        check(a.equals(b) && b.equals(a), "symmetric");
        check(!a.equals(c), "ordered contents");
        check(a.equals(copy), "copy invariant");
        check(a.hashCode() == b.hashCode(),
                "hash consistency");
        check(!a.equals(null), "null");

        input[0] = 9;
        int[] exposed = a.values();
        exposed[1] = 8;

        check(a.equals(b), "defensive copies");
        check(a.toString().equals("Vector[1, 2]"),
                "display");

        System.out.println("vector PASS");
    }
}
```

```bash
javac VectorRecordSelfTest.java
java VectorRecordSelfTest
```

```text
vector PASS
```

`check` throws an AssertionError directly, without needing `-ea` enabled. Besides these checks, you can add empty arrays, null policy, large numbers of elements, and performance. A self-test does not by itself prove every concurrency property or deep immutability for object element types.

## 34. Exercise 1: Predict Equality and Mutation

Given the snippet:

```java
record Data(int[] values) {}

int[] source = {3, 4};
Data a = new Data(source);
Data b = new Data(source);
Data c = new Data(new int[] {3, 4});
```

This is an **illustrative fragment** positioned after the record declaration inside a valid method.

Answer for yourself:

1. `a == b`?
2. `a.equals(b)`?
3. `a.equals(c)`?
4. `Arrays.equals(a.values(), c.values())`?
5. `a.hashCode() == b.hashCode()`?
6. Can it be guaranteed that `a.hashCode() != c.hashCode()`?
7. After `source[0] = 99`, what is `a.values()[0]`?

**Answers:** 1 false; 2 true; 3 false; 4 true before the mutation; 5 true; 6 no, hash collisions can occur; 7 equals 99 due to the shared reference.

## 35. Exercise 2: Fix a Record with Unstable Values

Requirement: design `Measurements(int[] readings)` such that:

- Forbid null.
- Copy both input and output.
- Two records are equal when they have the same sequence of numbers in order.
- The hash is based on each element.
- toString prints exactly `Measurements[10, 20]` for the array 10,20.
- A copy created from the accessor must be equal.

### Runnable Solution

Create **`MeasurementsExercise.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

record Measurements(int[] readings) {
    Measurements {
        readings = Objects.requireNonNull(readings).clone();
    }

    @Override
    public int[] readings() {
        return readings.clone();
    }

    @Override
    public boolean equals(Object other) {
        return this == other
                || (other instanceof Measurements m
                    && Arrays.equals(readings, m.readings));
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(readings);
    }

    @Override
    public String toString() {
        return "Measurements" + Arrays.toString(readings);
    }
}

public class MeasurementsExercise {
    public static void main(String[] args) {
        int[] input = {10, 20};
        Measurements a = new Measurements(input);
        Measurements b =
                new Measurements(new int[] {10, 20});

        input[0] = 999;

        System.out.println(a.equals(b));
        System.out.println(
                a.hashCode() == b.hashCode());
        System.out.println(a);
    }
}
```

```bash
javac MeasurementsExercise.java
java MeasurementsExercise
```

```text
true
true
Measurements[10, 20]
```

**Limitation of the solution:** This is a one-dimensional primitive array with order-sensitive equality. If you need unordered set-like comparison or nested mutable objects, a different algorithm/representation is required.

## 36. Decision Table

| Component type and purpose | `equals` | `hashCode` | Display |
| --- | --- | --- | --- |
| Immutable primitive/String | Generated | Generated | Generated |
| Immutable `List<Integer>` | Generated | Generated | Generated |
| `int[]` where identity is the contract | Generated by reference | Generated | Generated or custom |
| `int[]` wanting content equality | `Arrays.equals` | `Arrays.hashCode` | `Arrays.toString` |
| `String[]` wanting content equality | `Arrays.equals` | `Arrays.hashCode` | `Arrays.toString` |
| `int[][]` wanting deep content | `Arrays.deepEquals` | `Arrays.deepHashCode` | `Arrays.deepToString` |
| `Object[]` with nested arrays | `Arrays.deepEquals` if appropriate | `Arrays.deepHashCode` | `Arrays.deepToString` |
| Secrets/tokens | Per business rules, avoid mutable alias | Consistent with equals | Redact, do not print raw secrets |

**Do not replace `deepHashCode` with plain `hashCode` while equals uses deepEquals**: two equal contents with different nested array references can produce different hashes, breaking the contract.

## 37. Review Checklist

- [ ] Do I know which records contain an array or a nested mutable reference?
- [ ] Does the data domain need to compare **array identity** or **array contents**?
- [ ] Have I avoided confusing `array.equals(other)` with `Arrays.equals`?
- [ ] For matrices, has `Arrays.deepEquals` been considered?
- [ ] If equals is customized, does the custom hash use the exact same semantics?
- [ ] Have I avoided asserting that unequal objects always have different hashes?
- [ ] Have I avoided hardcoding hash values or array identity suffixes in stdout/tests?
- [ ] Is a custom toString treated as a formatter rather than a serializer?
- [ ] Can the input array still be retained by the caller and mutated later?
- [ ] Does the accessor return the internal array reference?
- [ ] If an immutable value is needed, have both input and output been copied?
- [ ] For a 2D array, has each row been copied rather than only the outer array?
- [ ] For an object array, have mutable elements been accounted for?
- [ ] Is the copy invariant satisfied when customizing defensive copying?
- [ ] Is there a clear null policy, without confusing null with an empty array?
- [ ] Is the record used as a HashMap/HashSet key?
- [ ] Are logical hash values stable when the object is used as a key?
- [ ] Can the array component be replaced with an immutable List or named primitives?
- [ ] Could toString expose sensitive data?
- [ ] Do tests check reflexive/symmetric/transitive properties, equality/hash, and mutation aliasing?
- [ ] Do the Java 17 examples have matching filenames, public classes, run commands, and stdout?

## 38. Review Questions

**1.** Does generated record equals automatically compare int[] element by element?

*No. An array component uses reference equality.*

**2.** For two arrays that are different objects with the same contents, what does `Arrays.equals` return?

*True, if they have the same elements in the same order.*

**3.** Can generated equals be true for two records that are different objects sharing the same array reference?

*Yes, if the other corresponding components are also equal.*

**4.** If two records are equal, how must their hashCodes relate?

*They must be equal. The reverse is not required.*

**5.** What format does the generated toString of an int[] typically print?

*An array object representation such as `[I@...`, not automatically the sequence of numbers.*

**6.** How do `Arrays.toString` and `Arrays.deepToString` differ?

*toString handles one level, while deepToString traverses nested array layers.*

**7.** Which method does an `int[][]` with rows having different references but identical contents need?

*Arrays.deepEquals if deep contents are desired.*

**8.** Does a final array component field make the array contents immutable?

*No; final keeps the reference fixed, while the elements remain mutable.*

**9.** Why must input be cloned in the canonical/compact constructor?

*To prevent the caller from keeping an alias to the original array and modifying internal state.*

**10.** Why must output be cloned in the accessor?

*To prevent the caller from modifying the internal array via the returned reference.*

**11.** What can happen if you copy both sides while keeping generated equals?

*Cloning creates different array references; a record copy with identical contents is still not equal.*

**12.** Which pair of methods is used for content equals on int[]?

*Arrays.equals and Arrays.hashCode.*

**13.** Which pair is used for content equals on int[][]?

*Arrays.deepEquals and Arrays.deepHashCode.*

**14.** Does `List.copyOf` deep-copy mutable elements?

*No.*

**15.** Why can records with `List<int[]>` still be unequal even when the array contents are identical?

*List.equals uses the equals of each int[] element, which is array identity equality.*

**16.** Why might a lookup in a HashMap using an array record key fail when querying with a new array of the same content?

*The new key is not equal under generated array semantics.*

**17.** If hashCode is based on the contents of a mutable array, what is the risk when used as a Map key?

*Mutation can change the hash after map.put, causing lookups to fail.*

**18.** Why does having the same toString not imply equals?

*A formatter can produce the same text from unequal objects.*

**19.** When is keeping generated equality for an array actually right?

*When the domain intentionally compares the same buffer/array object identity instead of contents.*

**20.** When should you choose primitive components or an immutable List instead of an array?

*When logical value semantics and API clarity matter more than exposing an array reference.*

---

**Final takeaway:** A record generates `equals`, `hashCode`, and `toString` based on **the exact components declared**, but **does not automatically give arrays content equality**. With an `int[]` component, two records holding two arrays with different identities can still be unequal even when the numbers are equal. The generated `hashCode` is not a content hash of the array, and the generated `toString` is not a pretty printer of the contents. To create a record carrying a true **number-sequence value**: define a null/mutation policy, defensively copy in the constructor/accessor, use `Arrays.equals + Arrays.hashCode` (or the `deep` methods for nested arrays), and optionally customize `toString`. When elements already have value semantics and immutability, a `List.copyOf` or multiple named primitive components is sometimes simpler. Consistency across equality, hash, ownership, and lifecycle is especially important when the record is used as a key in a Map/Set.
