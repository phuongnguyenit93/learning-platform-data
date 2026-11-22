# Checking `null`, Empty Arrays, and `null` Array Elements in Java

When designing `equals()`/`hashCode()` for objects containing arrays or nested structures, three states that are easily confused are a **`null` array**, an **empty array**, and an **array with `null` elements**. They carry different meanings and often lead to different equality results, hash codes, or exceptions. Choosing `Arrays.equals()`, `Arrays.deepEquals()`, and the corresponding hash functions must closely match the actual structure of the data.

Example:

```java
String[] missing = null;           // No array object.
String[] empty = {};               // Array exists, length 0.
String[] oneNull = { null };       // Array exists, length 1; element 0 is null.
String[] oneEmpty = { "" };        // Array exists, length 1; element 0 is the empty string.
```

These four states are **not synonymous**. In particular, `null` for the whole array variable differs from `null` at a position **inside the array**.

## 1. Distinguishing by properties and business meaning

| State | Example | `array == null` | `array.length` | Common interpretation |
| --- | --- | --- | --- | --- |
| `null` array | `String[] a = null;` | `true` | Throws `NullPointerException` if accessed | No data yet, not provided, or absent |
| Empty array | `String[] a = {};` | `false` | `0` | Data provided, but with zero elements |
| Array containing `null` | `String[] a = {null};` | `false` | `1` | There is a slot with no value yet |
| Array containing empty string | `String[] a = {""};` | `false` | `1` | There is a real `String` value of length 0 |

In an API accepting a list of selections, `null` may mean “unspecified”; `[]` may mean “specified, nothing selected”; `[null]` may be considered invalid data or a valid blank slot. **The exact meaning is determined by the API contract**, not by collapsing all states into the same value.

Primitive arrays such as `int[]` **cannot contain `null` elements**. For example, `int[] a = {null};` does not compile. However, `int[] a` itself can still be `null`, and a multidimensional array `int[][]` can contain a **`null` `int[]` row**, because those rows are references.

## 2. Checking safely before access

Accessing `array.length`, `array[0]`, or iterating with a `for` loop will throw `NullPointerException` if the array itself is `null`. For a non-`null` but empty array, `array[0]` throws `ArrayIndexOutOfBoundsException`.

```java
static boolean hasFirstNonNull(String[] values) {
    return values != null
            && values.length > 0
            && values[0] != null;
}
```

This is an **illustrative method fragment**, not a standalone program. Thanks to the short-circuiting `&&` operator, the right-hand condition is not evaluated if the left-hand condition is false; thus you can check the array, its length, and then the element in the proper order.

If the requirement is that no `null` elements appear anywhere in the array, check each element after handling a `null` array according to the defined policy:

```java
static boolean hasNoNullElement(String[] values) {
    if (values == null) {
        return false;
    }
    for (String value : values) {
        if (value == null) {
            return false;
        }
    }
    return true;
}
```

This snippet accepts an empty array because no element violates the rule; if business logic requires **at least one element**, also check `values.length > 0`.

`Objects.requireNonNull(values, "values")` fits when an API forbids `null` arrays; it throws an exception right at the input boundary, helping catch errors early. If both the array and its elements must be non-null, you must check **both levels**: `requireNonNull` on the array variable does not automatically check elements.

## 3. How does `Arrays.equals()` distinguish the three states?

Use `java.util.Arrays.equals(...)` to compare **contents of one-dimensional arrays** instead of the `==` operator or `array.equals(other)`.

Main rules:

1. Two array variables that are both `null` are treated as equal by `Arrays.equals()`.
2. A `null` array and an empty array are **different**.
3. Two empty arrays of the corresponding matching type are equal by content even with different references.
4. Two arrays of the same length are compared **position by position**.
5. For reference arrays such as `String[]`, two `null` elements at the same position are equal; a `null` and a non-null `String` are different; two non-null elements are compared using the corresponding `equals()`.
6. For primitive arrays such as `int[]`, each primitive value is compared per the corresponding overload's rules, with no null elements.

### 3.1. Runnable Java 17+ example

Save as **`NullArrayDemo.java`**:

```java
import java.util.Arrays;

public class NullArrayDemo {
    public static void main(String[] args) {
        String[] missing = null;
        String[] empty = {};
        String[] oneNull = {null};
        String[] anotherNull = {null};
        String[] oneEmpty = {""};

        System.out.println("missing is null: "
                + (missing == null));
        System.out.println("empty length: " + empty.length);
        System.out.println("oneNull length: " + oneNull.length);

        System.out.println("null vs null: "
                + Arrays.equals(missing, (String[]) null));
        System.out.println("null vs empty: "
                + Arrays.equals(missing, empty));
        System.out.println("empty vs empty: "
                + Arrays.equals(empty, new String[0]));
        System.out.println("null-element vs null-element: "
                + Arrays.equals(oneNull, anotherNull));
        System.out.println("null-element vs empty: "
                + Arrays.equals(oneNull, empty));
        System.out.println("null-element vs empty-string: "
                + Arrays.equals(oneNull, oneEmpty));

        System.out.println("hash null array: "
                + Arrays.hashCode(missing));
        System.out.println("hash empty array: "
                + Arrays.hashCode(empty));
        System.out.println("hash [null]: "
                + Arrays.hashCode(oneNull));
    }
}
```

Compile/run:

```bash
javac NullArrayDemo.java
java NullArrayDemo
```

Stdout:

```text
missing is null: true
empty length: 0
oneNull length: 1
null vs null: true
null vs empty: false
empty vs empty: true
null-element vs null-element: true
null-element vs empty: false
null-element vs empty-string: false
hash null array: 0
hash empty array: 1
hash [null]: 31
```

`Arrays.hashCode((Object[]) null)` returns `0`; an empty array has hash code `1`; a one-element object array `{null}` has hash code `31` because accumulation starts at `1`, then computes `31 * 1 + 0`. These values are determined by `Arrays.hashCode()` for the illustrated reference array; they are **not unique identifiers**.

When calling directly with a `null` literal, avoid calling `Arrays.equals(null, null)` or `Arrays.hashCode(null)` without a target type: the `Arrays` class has many overloads for different array types, so the call can be **ambiguous at compile time**. Use a typed variable or an appropriate cast such as `(String[]) null`.

## 4. `==`, `Objects.equals()`, and `Arrays.equals()` do not replace each other

For two separate arrays with the same elements:

```java
String[] a = {"Java", null};
String[] b = {"Java", null};
```

- `a == b` is `false` because they are **two different references**.
- `a.equals(b)` is `false` because array classes do not override `Object.equals()` to compare contents.
- `Objects.equals(a, b)` is also `false`: this function handles null, yet for non-null arrays it still calls `a.equals(b)`.
- `Arrays.equals(a, b)` is `true`: compares length and each element at the same position.
- `Objects.deepEquals(a, b)` is also `true` because both are arrays; however, for one-dimensional arrays, `Arrays.equals()` usually makes the intent clearer.

`Objects.equals()` is useful when a property is a value object with a proper `equals()`; it **does not automatically turn an array field into an element-by-element comparison**. Inside `equals()` of a class containing arrays, use the right `Arrays.equals()` or `Arrays.deepEquals()` overload according to structure.

Parallel rule: if an array field participates in `equals()` via `Arrays.equals()`, the corresponding part of `hashCode()` should use `Arrays.hashCode()`; if `Arrays.deepEquals()` is used, use `Arrays.deepHashCode()` for the corresponding nested structure. Avoid using `Objects.hashCode(array)` or `array.hashCode()` itself and expecting content-based results: they use the hash code of the **array object**, not replacing `Arrays.hashCode()`.

## 5. Nested arrays: why are `deepEquals()` and `deepHashCode()` needed?

Two-dimensional arrays in Java are **arrays containing arrays**. For `String[][]`, each row element can be a `String[]` or `null`. A non-null row can in turn be empty, or contain `String` elements equal to `null`. These levels must be distinguished.

`Arrays.equals(String[][], String[][])` actually selects the `equals(Object[], Object[])` overload: it compares **row elements** using `equals()`. Because each row is an array object, two separate rows with identical contents are **not equal** under `Object.equals`. That is *shallow* comparison at the nesting layer.

`Arrays.deepEquals(Object[], Object[])` recursively compares array-typed elements; it also handles inner primitive arrays using the corresponding content-comparison overload. `Arrays.deepHashCode(Object[])` computes a hash compatible with the `deepEquals()` relation.

### 5.1. Example distinguishing `null` rows, empty rows, and `null` elements

Create file **`NestedArrayDemo.java`**:

```java
import java.util.Arrays;

public class NestedArrayDemo {
    public static void main(String[] args) {
        String[][] left = {
            null,
            {},
            {null, "ok"}
        };
        String[][] same = {
            null,
            {},
            {null, "ok"}
        };
        String[][] changed = {
            null,
            {},
            {"", "ok"}
        };
        String[][] nullRow = {null};
        String[][] emptyRow = {new String[0]};

        System.out.println("shallow equals: "
                + Arrays.equals(left, same));
        System.out.println("deep equals: "
                + Arrays.deepEquals(left, same));
        System.out.println("null vs empty row: "
                + Arrays.deepEquals(nullRow, emptyRow));
        System.out.println("null vs empty element: "
                + Arrays.deepEquals(left, changed));
        System.out.println("same deep hash: "
                + (Arrays.deepHashCode(left)
                        == Arrays.deepHashCode(same)));
        System.out.println("nested data: "
                + Arrays.deepToString(left));

        int[][] numbers = {{1, 2}, null, {}};
        int[][] copy = {{1, 2}, null, {}};
        System.out.println("primitive nested equal: "
                + Arrays.deepEquals(numbers, copy));
    }
}
```

Run:

```bash
javac NestedArrayDemo.java
java NestedArrayDemo
```

Stdout:

```text
shallow equals: false
deep equals: true
null vs empty row: false
null vs empty element: false
same deep hash: true
nested data: [null, [], [null, ok]]
primitive nested equal: true
```

**Level-by-level analysis:**

- `left` and `same` are two separate outer arrays; the empty rows and rows containing `null` are also created as separate array objects. Therefore shallow comparison `Arrays.equals(left, same)` is `false`.
- `Arrays.deepEquals(left, same)` returns `true`: the first rows are both `null`; the second rows are both empty; the third rows share the string `"ok"` and the `null` element at the first position.
- `nullRow` differs from `emptyRow`, because **a nonexistent row** differs from **an existing row with 0 elements**.
- `changed` contains `""` instead of `null` at the first position of the third row, so deep comparison differs.
- `Arrays.deepHashCode(left)` equals `Arrays.deepHashCode(same)` because the deeply compared data is equal.
- `int[][]` is also an `Object[]` at the **outer level** (each element is an `int[]`), so calling `Arrays.deepEquals(numbers, copy)` is valid. Inside, elements of `int[]` are primitive integers and cannot be `null`; however, an entire `int[]` row can be `null`.

Remember: `Arrays.deepEquals()` and `Arrays.deepHashCode()` accept `Object[]`, so use them for reference arrays and nested structures. For **one-dimensional primitive arrays** (`int[]`, `byte[]`, `long[]`, ...), use the matching `Arrays.equals(int[], int[])` / `Arrays.hashCode(int[])` overload. You cannot pass an `int[]` directly into the `Object[]` parameter of `Arrays.deepEquals()`.

For arrays with **self-referential/cyclic** structures (an array containing itself directly or indirectly), do not mechanically apply deep recursion operations: the contract of deep comparison/hashing methods does not guarantee deterministic results for cyclic arrays. Avoid cycles or design a custom identity/cycle-handling algorithm.

## 6. Nesting inside a class: `equals()` and `hashCode()` must match in depth

Suppose a value class represents an `int[][]` matrix. If `equals()` uses `Arrays.deepEquals(rows, other.rows)` while `hashCode()` uses `Arrays.hashCode(rows)`, two matrices whose rows have **different references yet identical contents** can be evaluated as equal while their hash codes rely on row identities and differ. That is a **risk of violating the contract**.

The right pair is:

```java
boolean same = Arrays.deepEquals(rows, other.rows);
int hash = Arrays.deepHashCode(rows);
```

This is an **illustrative code fragment**, assuming `rows` and `other.rows` are both of type `int[][]`. For a flat `byte[]` array, the corresponding pair is `Arrays.equals(bytes, other.bytes)` and `Arrays.hashCode(bytes)`.

Do not infer that `Objects.hash(rows)` is an equivalent alternative to `Arrays.deepHashCode(rows)`. `Objects.hash(...)` uses varargs, easily causing confusion about how arrays are expanded into elements; for nested arrays, it does not automatically have the required deep hash semantics.

## 7. Example of an immutable value class accepting `null` rows

An object used as a `HashMap` key or `HashSet` element should keep the fields participating in equality/hash **stable**. With arrays, `final int[][] rows` only makes the **outer reference** unchangeable; calling code can still mutate `rows[0][0]` through an alias if not copied. For an `int[][]` matrix, both the **outer array and each non-null row** must be copied on input, and the internal array must not be returned directly externally.

Create file **`MatrixKeyDemo.java`**:

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

final class MatrixKey {
    private final int[][] rows;

    MatrixKey(int[][] source) {
        Objects.requireNonNull(source, "source");
        this.rows = deepCopy(source);
    }

    private static int[][] deepCopy(int[][] source) {
        int[][] copy = new int[source.length][];
        for (int i = 0; i < source.length; i++) {
            copy[i] = source[i] == null
                    ? null
                    : source[i].clone();
        }
        return copy;
    }

    public int[][] rowsCopy() {
        return deepCopy(rows);
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        return obj instanceof MatrixKey other
                && Arrays.deepEquals(rows, other.rows);
    }

    @Override
    public int hashCode() {
        return Arrays.deepHashCode(rows);
    }
}

public class MatrixKeyDemo {
    public static void main(String[] args) {
        int[][] input = {{1, 2}, null, {}};
        MatrixKey first = new MatrixKey(input);
        MatrixKey second =
                new MatrixKey(new int[][] {{1, 2}, null, {}});
        MatrixKey different =
                new MatrixKey(new int[][] {{1, 2}, {}, {}});

        System.out.println("equal contents: "
                + first.equals(second));
        System.out.println("same hash: "
                + (first.hashCode() == second.hashCode()));
        System.out.println("null row vs empty row: "
                + first.equals(different));

        Set<MatrixKey> keys =
                new HashSet<>(List.of(first, second));
        System.out.println("set size: " + keys.size());

        input[0][0] = 99;
        System.out.println("after source mutation: "
                + first.equals(second));

        int[][] externalCopy = first.rowsCopy();
        externalCopy[0][0] = 77;
        System.out.println("after copy mutation: "
                + first.equals(second));
    }
}
```

Run:

```bash
javac MatrixKeyDemo.java
java MatrixKeyDemo
```

Stdout:

```text
equal contents: true
same hash: true
null row vs empty row: false
set size: 1
after source mutation: true
after copy mutation: true
```

**Why is this example important?**

1. The matrix has a `null` row, an empty row, and a populated row; that distinction is preserved by `deepCopy`.
2. `Arrays.deepEquals()` and `Arrays.deepHashCode()` inspect rows by content correspondingly.
3. The `final` class keeps `rows` as `private final`, copying each row on input and output, so external mutations do not corrupt key state.
4. Two keys with the same logical content are treated as one by `HashSet`; a key with a `null` row differs from a key with an empty row.
5. The example is specific to `int[][]`; if nested elements are **mutable objects** (e.g., `List<MutableItem>[]`), cloning each row only copies element references and **is not enough to achieve deep immutability**. Copying/freezing appropriate to the data model is needed.

Depending on the API, you may choose to **forbid `null` rows altogether** instead of preserving them. However, you must validate in the constructor and make it explicit to callers, not silently normalize if `null` carries business meaning.

## 8. When should `null` be normalized to an empty array?

Both choices are valid, as long as reading data, `equals()`, and `hashCode()` stay consistent:

### Option A: preserve the distinction

If `null` means “unknown” while empty means “known to have none”, preserve both. Use `Arrays.equals()` and `Arrays.hashCode()` for flat arrays; `Arrays.deepEquals()` and `Arrays.deepHashCode()` for nested arrays. The two states will differ under standard content comparison.

### Option B: treat `null` as empty right at the boundary

If business logic treats **not provided** and **empty list** as the same value, you can normalize in the constructor:

```java
this.tags = tags == null ? new String[0] : tags.clone();
```

This is an **illustrative code fragment** for a `String[] tags` field. After normalization, there is no longer a distinction between `null` input and empty input. Using `Arrays.equals(this.tags, other.tags)` and `Arrays.hashCode(this.tags)` will be consistent, provided the internal array cannot be mutated via a getter. If you still need to distinguish “not provided”, store presence information separately or keep `null`.

**Do not normalize in only one method.** If `equals()` treats `null` and `[]` as equal while `hashCode()` still returns `0` for `null` and `1` for `[]`, you have broken the contract. It is best to normalize data **once at the boundary**, then use the same normalized state for both comparison and hashing.

Also do not automatically strip `null` elements or convert `null` into `""`: `[null]`, `[]`, and `[""]` carry different information, and data-sanitizing behavior must be an **explicit business decision**.

## 9. Very common errors

| Error | Consequence | Resolution |
| --- | --- | --- |
| Accessing `array.length` when array is `null` | `NullPointerException` | Check the array variable first |
| Accessing `array[0]` when array is empty | `ArrayIndexOutOfBoundsException` | Check `length > 0` |
| Checking only outer array and forgetting `null` elements/rows | `NullPointerException` when using element/row | Check each level appropriately |
| Using `==`, `array.equals()`, or `Objects.equals()` to compare array content | Compares references, differing from content | Use `Arrays.equals()` or `Arrays.deepEquals()` |
| Using `Arrays.equals()` for two nested arrays, expecting all levels to be compared | Sub-arrays with different references are treated as unequal | Use `Arrays.deepEquals()` when deep comparison is desired |
| Using `Arrays.deepEquals()` while `hashCode()` computes by sub-array references | Risk of two equal objects having different hashes | Use matching `Arrays.deepHashCode()` |
| Unconditionally treating `null`, `[]`, and `[null]` as the same | Loss of data meaning | Unify input rules |
| Using `Arrays.equals(null, null)` without specifying type | Overload call can be ambiguous | Use typed variables or cast |
| Putting a mutable array directly as a hash key | Mutating data breaks lookups | Create an immutable wrapper and copy defensively |
| Calling `clone()` only on the outer array of a nested structure | Inner arrays/rows can still be mutated externally | Copy to the full nesting depth of the data |

**Note on `Arrays.toString()` / `Arrays.deepToString()`:** They help inspect data, yet the display string is not an equality/hash definition. For example, `Arrays.toString(new String[]{null})` displays `[null]`, and `Arrays.toString(new String[]{"null"})` also displays `[null]`. Do not compare `toString()` outputs to decide whether two arrays are equal. For nested arrays, use `deepToString()` to observe content levels while debugging.

## 10. Practical checklist

- [ ] Clearly determine whether `null` for **the whole array**, an array with `length == 0`, and a `null` element are three distinct states under business rules.
- [ ] If only non-null inputs are allowed, validate early with `Objects.requireNonNull()`; if null elements must be forbidden, check every element/row.
- [ ] When accessing `length` or `[0]`, ensure the array has been checked for non-null and sufficient element count.
- [ ] Flat arrays use the `Arrays.equals()` / `Arrays.hashCode()` pair with the matching overload.
- [ ] Nested arrays use the `Arrays.deepEquals()` / `Arrays.deepHashCode()` pair when the intent is comparing contents across levels.
- [ ] Do not confuse `Objects.equals()` with array content comparison; do not confuse an empty `String` with a `null` element.
- [ ] Do not automatically normalize `null` to empty or drop `null` elements unless the contract specifies it.
- [ ] If an array participates in key equality/hash inside `HashMap`/`HashSet`, its state is protected from unintended mutation.
- [ ] Test both arrays null, one null and one empty, both empty, `[null]`, `[""]`, null/empty rows in nested arrays, and primitive arrays.

**Principle to remember:** `null` does not mean “array of length 0”, and a `null` element does not mean “no element”. Define the meaning of the data first, then choose the corresponding checks, comparisons, and hash codes. When structures are nested, ensure **comparison depth and hashing depth are consistent**.