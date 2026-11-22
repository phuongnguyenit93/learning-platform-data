# Array Components in Java Records Are Not Automatically Deep-Compared

## 1. What Happens with Arrays in a Record?

A Java `record` is a class form for concisely declaring data, for example:

```java
record Packet(byte[] payload) {}
```

If not manually declared, Java generates the constructor, `payload()` accessor, and `equals(Object)`, `hashCode()`, and `toString()` methods. However, **records have no mechanism to automatically deep-compare array elements**.

Suppose two `Packet` objects both contain the byte sequence `{1, 2, 3}`. If each object receives a separately allocated array, generated `equals` treats them as **different**. The reason is that Java arrays use `Object.equals` by **reference identity**, without comparing individual element values.

Distinguish three conditions:

- **Same reference:** `arrayA == arrayB` — two variables point to the exact same array object.
- **Same 1D array contents:** `Arrays.equals(arrayA, arrayB)` — same length and corresponding elements equal.
- **Same multi-level array contents:** `Arrays.deepEquals(arrayA, arrayB)` for appropriate reference/nested array types — deeply inspects sub-arrays.

There is no general rule saying that because a record "carries values", every mutable or array-shaped component automatically gets value equality. You must choose equality semantics that fit the problem.

## 2. What Does the Java SE 17 Contract Specify?

The `java.lang.Record` documentation and Java Language Specification §8.10 specify that generated `equals` checks for the same record class and equality of **each component field**:

1. Primitive-type components are compared according to the corresponding wrapper's `compare` rule; for instance, two `int` components with the same number are equal.
2. Reference-type components use semantics equivalent to `Objects.equals(a, b)`.
3. The `Objects.equals` rule considers two references equal when they are the same object or when `a.equals(b)` returns `true` (with `null` handling).

Array classes in Java do not override `Object.equals` to traverse elements; two arrays with different references remain unequal even when holding identical values.

| Component | Generated Record Equality | Example |
| --- | --- | --- |
| `int number` | By primitive value | `4` equals `4` |
| `String title` | By `String.equals` | Two `String`s with the same contents are equal |
| `List<String> items` | By `List.equals` | `List` compares elements in order |
| `byte[] data` | By array reference | Two new arrays containing `{1, 2}` are not equal |
| `int[][] matrix` | By outer array reference | Does not automatically traverse rows |

Generated `hashCode` is derived from the components and is compatible with generated `equals`. **Do not confuse this with `Arrays.hashCode` or `Arrays.deepHashCode`**: a record does not automatically compute hashes based on array contents. Nor is the exact hash combining algorithm promised by Java in general, so you should not rely on specific hash numbers or believe hash codes can serve as durable IDs.

Generated `toString` is also based on components, yet it does not commit to printing arrays across all elements like `Arrays.toString`. When you want to display byte contents, format them explicitly.

## 3. Runnable Java 17 Example: Same Elements Still Not Equal

```java
import java.util.Arrays;

public class RecordArrayDemo {
    record RawPacket(byte[] payload) {}

    public static void main(String[] args) {
        byte[] firstArray = {1, 2, 3};
        byte[] secondArray = {1, 2, 3};

        RawPacket a = new RawPacket(firstArray);
        RawPacket b = new RawPacket(secondArray);
        RawPacket c = new RawPacket(firstArray);

        System.out.println(firstArray == secondArray);
        System.out.println(Arrays.equals(firstArray, secondArray));
        System.out.println(a.equals(b));
        System.out.println(a.equals(c));
        System.out.println(a.payload() == firstArray);

        firstArray[0] = 9;
        System.out.println(a.payload()[0]);
        System.out.println(b.payload()[0]);
    }
}
```

Save the program as `RecordArrayDemo.java` and run:

```bash
javac RecordArrayDemo.java
java RecordArrayDemo
```

Deterministic output:

```text
false
true
false
true
true
9
1
```

**Analysis:**

- `firstArray == secondArray` is `false` because creating two arrays allocates two objects.
- `Arrays.equals(firstArray, secondArray)` is `true` because at the time of comparison, their contents match.
- `a.equals(b)` is `false` because the two `payload` components do not share the same array reference.
- `a.equals(c)` is `true` because both use `firstArray` and the same record type.
- The default `payload()` accessor returns the field reference, so `a.payload() == firstArray` is `true`.
- Modifying `firstArray[0] = 9` changes the data visible through `a.payload()` to `9`, while `b`'s array still holds `1` at the first element.

The results above clarify two distinct issues: **generated equality does not compare array contents**, and **records do not guarantee deep immutability**.

## 4. Why Are Records Only Shallowly Immutable?

For a record, each component has a corresponding `private final` field. For an array, this prevents the field from being reassigned to a new reference after initialization, **without preventing modification of the elements inside the referenced array**.

Illustrative example (placed inside a method with access to the `Numbers` type):

```java
record Numbers(int[] values) {}

Numbers numbers = new Numbers(new int[] {1, 2});
numbers.values()[0] = 99;
```

This is a conceptual snippet consisting of a record declaration and usage statements; if placed into a complete file, the `record Numbers...` declaration goes where type declarations are valid, and the remaining two statements go inside a method. Array values seen through the accessor can change even though the record field is final.

Similarly, with `record Item(List<String> tags) {}`, if an `ArrayList` is passed in and an external reference is kept, modifying the `ArrayList` can change the data the record sees, unless the constructor copied/defended against it. `List.equals` compares by contents, so those changes can also affect `equals` and `hashCode` results. With arrays, generated equality still checks reference identity, yet the data users read through the record can change.

**Shallow immutability** describes the fixedness of the fields; **deep immutability** requires examining the mutability of the entire data structure referenced by the fields.

## 5. One-Dimensional and Multi-Dimensional Arrays Need Different Methods

For 1D primitive arrays such as `byte[]`, `int[]`, `long[]`, use the pair:

- `Arrays.equals(a, b)` when comparing element-by-element.
- `Arrays.hashCode(a)` when producing a hash consistent with that equality.

For 1D reference arrays such as `String[]`, `Arrays.equals` also compares corresponding elements using each element's equality. However, if each element is itself **an array**, nested array equality remains by identity. To descend into child arrays, `Arrays.deepEquals` and `Arrays.deepHashCode` are needed for appropriate types.

Standalone program example:

```java
import java.util.Arrays;

public class NestedArrayDemo {
    record Matrix(int[][] cells) {}

    public static void main(String[] args) {
        int[][] a = {{1, 2}, {3, 4}};
        int[][] b = {{1, 2}, {3, 4}};

        System.out.println(a == b);
        System.out.println(Arrays.equals(a, b));
        System.out.println(Arrays.deepEquals(a, b));
        System.out.println(new Matrix(a).equals(new Matrix(b)));
    }
}
```

Save to `NestedArrayDemo.java`:

```bash
javac NestedArrayDemo.java
java NestedArrayDemo
```

Output:

```text
false
false
true
false
```

The second line is `false` because `Arrays.equals` on the outer array compares the `int[]` rows with each other using reference equality. `Arrays.deepEquals` recurses through the rows and thus returns `true`. The `Matrix` record only compares the two `cells` components at the outer array reference level, so generated equality is `false`.

For `int[][]`, `clone()` on the outer array only creates a copy of **the row references**, without automatically copying each inner `int[]`. Deep immutability requires creating new rows (and continuing deeper when data has more levels).

## 6. Records Representing Byte Sequences: Choose Explicit Content Equality

If the business domain defines two `Packet`s as equal when they contain the same byte sequence, override **both `equals` and `hashCode`** by contents. For that type to also be safe as a `HashMap`/`HashSet` key, prevent the internal array from being mutated after initialization.

The following example protects both the constructor and the accessor:

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class SafePacketDemo {
    record ContentPacket(byte[] payload) {
        public ContentPacket {
            Objects.requireNonNull(payload, "payload");
            payload = payload.clone();
        }

        @Override
        public byte[] payload() {
            return payload.clone();
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || other instanceof ContentPacket that
                    && Arrays.equals(payload, that.payload);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(payload);
        }

        @Override
        public String toString() {
            return "ContentPacket[payload=" + Arrays.toString(payload) + "]";
        }
    }

    public static void main(String[] args) {
        byte[] left = {1, 2, 3};
        byte[] right = {1, 2, 3};

        ContentPacket a = new ContentPacket(left);
        ContentPacket b = new ContentPacket(right);
        System.out.println(a.equals(b));
        System.out.println(a.hashCode() == b.hashCode());

        Set<ContentPacket> packets = new HashSet<>();
        packets.add(a);
        System.out.println(packets.contains(b));

        left[0] = 9;
        System.out.println(a.payload()[0]);

        byte[] exposed = a.payload();
        exposed[1] = 8;
        System.out.println(a.payload()[1]);

        System.out.println(a.equals(b));
        System.out.println(a);
    }
}
```

Save the file `SafePacketDemo.java` and run:

```bash
javac -encoding UTF-8 SafePacketDemo.java
java SafePacketDemo
```

Output:

```text
true
true
true
1
2
true
ContentPacket[payload=[1, 2, 3]]
```

Reading the code against the contract:

1. The record's compact constructor copies the array parameter via `payload.clone()`; the compiler stores the processed parameter into the component field. `ContentPacket` does not retain a reference to the external input array.
2. The accessor is overridden to return **a copy**, so code calling the getter cannot directly mutate the internal array.
3. `equals` uses `Arrays.equals` to compare contents; two inputs with different objects yet identical bytes become two equal records.
4. `hashCode` uses `Arrays.hashCode`, ensuring equal value pairs receive the same hash.
5. `HashSet.contains(b)` succeeds after adding `a` because both equality and hash are consistent.
6. Modifying the `left` array or the copy returned by the accessor does not affect `a`'s data, so the record maintains stable equality/hash.
7. `toString` formats the 1D contents itself using `Arrays.toString` for convenient inspection.

**Both sides of defensive copying are required:** Copying only in the constructor still exposes the array via the default accessor; copying only in the accessor still keeps the mutable original input array. When the goal is a content-immutable value object, every path holding or returning mutable references must be controlled.

The example uses `byte[]` so `clone()` copies all primitive data. Multi-dimensional arrays and arrays containing mutable objects must be examined more deeply; copying the outer array does not guarantee copying the contents of element objects.

## 7. Another Approach: Using a List with Element-Based Equality

For data that is genuinely an ordered list, you can use `List` in a record instead of an array. `List.equals` already defines comparison of corresponding elements.

```java
import java.util.List;

public class ListValueDemo {
    record Codes(List<String> values) {
        public Codes {
            values = List.copyOf(values);
        }
    }

    public static void main(String[] args) {
        Codes a = new Codes(List.of("A", "B"));
        Codes b = new Codes(List.of("A", "B"));

        System.out.println(a.equals(b));
        System.out.println(a.hashCode() == b.hashCode());
    }
}
```

Save the file `ListValueDemo.java`, run `javac ListValueDemo.java` and `java ListValueDemo`:

```text
true
true
```

Because the component is `List<String>`, generated record equality uses `List.equals`; `String` is immutable so it is easy to keep stable. `List.copyOf` creates a structurally unmodifiable list and also disallows `null` elements.

This **does not mean `List.copyOf` deep-copies**. If the list consists of mutable objects, mutating an element object's contents can still affect equality/hash. Choose data types and immutability policies according to the actual contract, not merely coding convenience.

## 8. Are There Cases Where Generated Array Equality Is What You Want?

Yes. If the goal of the record is to **tag a specific buffer** or hold the identity of a resource rather than byte values, two separate arrays even with the same data may be treated as two distinct objects. In that case, generated equality can match the intent.

However, if the record represents:

- Binary payload of a message;
- A vector of numeric values;
- A matrix or numeric table in array form;
- A data snapshot needing element-by-element comparison;

then content comparison usually needs to be considered. There is no single design rule applicable to every class, yet **the contract must be defined before trusting generated equality**.

## 9. The hashCode Contract and Collections

Mandatory constraint:

`a.equals(b) ⇒ a.hashCode() == b.hashCode()`

If you override `equals` to call `Arrays.equals` while leaving the generated `hashCode` intact, the hash result remains based on the components under the generated contract, i.e., not bound to array contents. Two arrays with identical elements but different identities can produce different hashes while the new `equals` returns `true`: **a contract violation**.

Choose the appropriate pair of methods:

| Desired Semantics | Equality | Compatible Hash |
| --- | --- | --- |
| 1D primitive array | `Arrays.equals` | `Arrays.hashCode` |
| 1D reference array | `Arrays.equals` | `Arrays.hashCode` |
| Nested array requiring recursive comparison | `Arrays.deepEquals` | `Arrays.deepHashCode` |
| Array identity | Generated record equality | Generated record hashCode |
| Ordered list with element-based equality | `List.equals` | `List.hashCode` |

If array contents participate in equality/hash, mutating the array while the record is in a `HashSet` or used as a `HashMap` key can make lookups unreliable. This is why defensive copying accompanies a value equality strategy.

Do not assert in tests that two unequal values must always produce different hashes. Hash collisions are permitted. Nor should you depend on a specific hash number or generated `toString` format as protocol data.

## 10. Incomplete Fixes

**Adding `Arrays.equals` at only one call site:** That does not change `record.equals`, so when the record enters another library or is used as a `Map` key, generated equality still uses array identity.

**Overriding only `equals` while keeping the old `hashCode`:** Equal pairs are no longer guaranteed to have the same hash. You must override hash accordingly.

**Cloning the array only in the constructor:** Protects against external input mutation, yet two records holding two different copies still are not equal under generated equality. Moreover, the accessor may return the internal array and allow mutation.

**Cloning only in the accessor:** Does not solve the constructor holding a reference to an input array already mutated by the caller; nor does it turn generated equality into content equality. Generated equality/hash use component fields and do not necessarily call the record's accessor.

**Using `Arrays.equals` for `int[][]` and thinking all numbers are compared:** The outer array has child arrays as elements; shallow comparison only sees the identity of child arrays. If deep comparison is needed, choose `Arrays.deepEquals` and `Arrays.deepHashCode`, and also consider defensive deep copying.

## 11. Self-Practice Questions

**Question 1.** Two `record R(int[] data) {}` instances are created with two independent arrays both containing `{1, 2}`. What does generated `equals` return?

**Answer:** `false` because the `int[]` component uses reference equality.

**Question 2.** Two records of the same type receive the exact **same** array as their component. Can generated equality return `true`?

**Answer:** Yes, when all remaining components are also equal. For the array component, both sides share the same reference so they are equal.

**Question 3.** A record uses `Arrays.equals` for `equals` but does not override `hashCode`. Where is the flaw?

**Answer:** Two arrays with different references yet identical contents can be equal under `equals` while component-generated hashes are not guaranteed to match, violating the `Object` contract. Use `Arrays.hashCode` on the same array contents.

**Question 4.** With `int[][]`, why can `Arrays.equals(a, b)` be `false` while `Arrays.deepEquals(a, b)` is `true`?

**Answer:** Shallow comparison on the outer array encounters each `int[]` element and compares child array identity. Deep comparison descends into each row to compare the integers.

**Question 5.** A record copies `byte[]` in the constructor, yet the accessor returns the field directly. Is it immutable by contents yet?

**Answer:** Not yet. Users can mutate the array through the accessor. You need to copy on return or use a truly immutable representation.

**Question 6.** When can generated equality with a `byte[]` component be appropriate?

**Answer:** When the data type's contract genuinely wants the identity of the **array object** rather than the contents of the byte sequence.

## 12. Key Takeaways

1. A record's generated `equals` uses the equality semantics of each **component**, without automatically deep-comparing all structures.
2. Java arrays use **reference** equality; two arrays with identical contents do not automatically make two records equal.
3. `Arrays.equals` fits comparing 1D arrays; `Arrays.deepEquals` fits nested arrays needing recursive comparison.
4. When defining equality by array contents, you must define the corresponding hash using `Arrays.hashCode` or `Arrays.deepHashCode`.
5. Records are only **shallowly immutable**; a final field does not protect the contents of an array or mutable object.
6. To build a stable value object based on arrays, defensive copying is needed **on input** and **on output**, along with considering deep copying when nested structures exist.
7. If the problem needs array identity rather than content equality, generated equality can be kept; document that intent clearly in the design.

Official documentation: [`java.lang.Record` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html), [JLS §8.10 – Record Classes](https://docs.oracle.com/en/java/javase/specs/jls/se17/html/jls-8.html#jls-8.10), [`java.util.Arrays`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html), and [`Objects.equals`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#equals(java.lang.Object,java.lang.Object)).