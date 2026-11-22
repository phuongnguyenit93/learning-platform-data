# Objects.hash() for multiple values and passing arrays

## 1. What is Objects.hash() used for?

`java.util.Objects.hash(Object... values)` is a utility method that computes **a single `int` value from multiple arguments**. It commonly appears when a class overrides `hashCode()` and needs to combine the fields participating in the equality relation:

```java
@Override
public int hashCode() {
    return Objects.hash(customerId, region, version);
}
```

The snippet above is an illustrative method body inside a class with those three fields, not a standalone Java file. The arguments are processed in exact order; the count and value of each argument affect the computed hash.

**Exact definition:** The Java 17 Javadoc for `Objects.hash(Object... values)` specifies that the result is equivalent to `Arrays.hashCode(Object[])` applied to **the actual argument array passed to the varargs parameter**. That means you can picture it as:

```java
// Equivalent idea, not a redeclaration of the JDK method:
static int hashMany(Object... values) {
    return java.util.Arrays.hashCode(values);
}
```

The commonly overlooked detail lies in the ellipsis `...`: in Java, a varargs call can pass **multiple individual values** or pass **an array compatible with the array parameter type**. If the last argument is already an array, the compiler may treat it as the varargs array itself, rather than as a single value inside the varargs array.

Key cases to distinguish in this lesson:

- `Objects.hash(a, b, c)`: combines three values.
- `Objects.hash(a)`: computes the hash of **a one-element list**, not necessarily equal to `a.hashCode()`.
- `Objects.hash((Object[]) array)`: when `array` is `Object[]` or a subtype reference array like `String[]`, passes the array itself as the varargs array.
- `Objects.hash((Object) array)`: forces the compiler to treat the entire array as **a single object**, then uses the hash of that array object itself.
- `Objects.hash(primitiveArray)`: primitive arrays such as `int[]` are not `Object[]`, so they become a single `Object` element inside varargs.

Do not confuse `Objects.hash` with a cryptographic hash algorithm, a unique identifier, or a method that automatically deep-compares every array structure. It is a utility for computing hashes for the `Object.hashCode` contract, which allows collisions.

## 2. Multiple arguments: combining in order

`Objects.hash("A", 7)` is computed as `Arrays.hashCode(new Object[] {"A", Integer.valueOf(7)})`. Using the `Object[]` formula, it starts with `result = 1`, then for each element performs `result = 31 * result + elementHash`. A `null` element contributes `0`; `int` arithmetic can overflow under Java semantics.

With `"A".hashCode() == 65` and `Integer.valueOf(7).hashCode() == 7`:

1. After `"A"`: `31 * 1 + 65 = 96`.
2. After `7`: `31 * 96 + 7 = 2983`.

Changing the order can change the hash because `Objects.hash("A", 7)` does not have the same argument array as `Objects.hash(7, "A")`. However, you cannot claim that every distinct sequence of arguments always produces a different hash: the result range is only 32-bit `int` and **hash collisions are permitted**.

### Runnable Java 17 example

```java
import java.util.Arrays;
import java.util.Objects;

public class ObjectsHashBasics {
    public static void main(String[] args) {
        System.out.println(Objects.hash("A", 7));
        System.out.println(
                Objects.hash("A", 7)
                == Arrays.hashCode(new Object[] {"A", 7})
        );
        System.out.println(Objects.hash("A"));
        System.out.println("A".hashCode());
        System.out.println(Objects.hash());
    }
}
```

Save as `ObjectsHashBasics.java` and run:

```bash
javac ObjectsHashBasics.java
java ObjectsHashBasics
```

Output:

```text
2983
true
96
65
1
```

Explanation: `Objects.hash("A")` does not simply return `"A".hashCode()`. It computes `Arrays.hashCode` on a varargs array containing **one** element `"A"`, so the result is `31 + 65 = 96`. With no arguments, the varargs array is empty and the result is `1`.

If you only want the hash of **a single individual object**, `Objects.hashCode(value)` usually expresses the intent better than `Objects.hash(value)`. The `Objects.hashCode(Object)` method returns `0` if the value is `null`, and `value.hashCode()` otherwise. These two overloads do not share the same formula.

## 3. Passing Object[]: spread into elements or treat the array as one object?

This is the most confusing case for `Objects.hash`.

Given:

```java
String[] codes = {"A", "B"};
```

`String[]` is a subtype of `Object[]`. Therefore, when calling `Objects.hash(codes)`, the compiler can select the **non-wrapping varargs invocation form**, using `codes` itself as the argument array. The Java compiler often issues a warning when such a call is ambiguous with respect to varargs.

Use a cast to state your intent clearly:

- `Objects.hash((Object[]) codes)`: treats `codes` as the **varargs array**; hashes the elements `"A"` and `"B"`.
- `Objects.hash((Object) codes)`: treats **the entire array object** as a single argument; the hash code uses `codes.hashCode()`, which is the array's identity hash.
- `Arrays.hashCode(codes)`: directly hashes the contents of a one-dimensional reference array; for these two example strings it matches the spread-array case.

Because `String.hashCode` for `"A"` is `65` and `"B"` is `66`, the result when spreading the array is `31 * (31 + 65) + 66 = 3042`.

### Example demonstrating the difference between the two ways of passing

```java
import java.util.Arrays;
import java.util.Objects;

public class ObjectArrayVarargsDemo {
    public static void main(String[] args) {
        String[] codes = {"A", "B"};

        int byElements = Objects.hash("A", "B");
        int byArrayAsVarargs = Objects.hash((Object[]) codes);
        int byOneArrayObject = Objects.hash((Object) codes);

        System.out.println(byElements);
        System.out.println(byArrayAsVarargs);
        System.out.println(byArrayAsVarargs == Arrays.hashCode(codes));
        System.out.println(
                byOneArrayObject == 31 + System.identityHashCode(codes)
        );
        System.out.println(
                byArrayAsVarargs == Objects.hash("A", "B")
        );
    }
}
```

Save `ObjectArrayVarargsDemo.java` and run:

```bash
javac ObjectArrayVarargsDemo.java
java ObjectArrayVarargsDemo
```

Output:

```text
3042
3042
true
true
true
```

The fourth line is `true` because `codes` is a Java array, `codes.hashCode()` has identity hash semantics like `System.identityHashCode(codes)`, and the hash of **one** element in `Object[]` is `31 + elementHash` (under normal `int` overflow rules).

Do not print `byOneArrayObject` expecting a constant value: an array's identity hash value is not specifically prescribed and can vary across runs. The two ways of passing have **different semantics**, even though in rare cases they might yield the same number due to a hash collision.

What matters is not memorizing a numeric value, but understanding **the varargs array structure the compiler passed to the method**.

## 4. Primitive arrays: int[] does not automatically spread into Object...

`int[]` is an object in Java, yet it is **not** a subtype of `Object[]`. Therefore, the call:

```java
int[] numbers = {1, 2};
int hash = Objects.hash(numbers);
```

is interpreted as hashing **a single argument which is the `numbers` array itself**, not two arguments `Integer.valueOf(1)` and `Integer.valueOf(2)`.

An `int[]` array does not override `Object.hashCode` to hash its contents, so `Objects.hash(numbers)` relies on the array's identity hash. To hash **the one-dimensional contents of a primitive array**, use:

`Arrays.hashCode(numbers)`

For example, `Arrays.hashCode(new int[]{1, 2})` is `994`, because it computes `31 * (31 * 1 + 1) + 2`.

### Example contrasting the two purposes

```java
import java.util.Arrays;
import java.util.Objects;

public class PrimitiveArrayHashDemo {
    public static void main(String[] args) {
        int[] data = {1, 2};

        System.out.println(Arrays.hashCode(data));
        System.out.println(
                Objects.hash(data)
                == 31 + System.identityHashCode(data)
        );
        System.out.println(
                Objects.hash((Object) data)
                == Objects.hash(data)
        );
        System.out.println(Objects.hash(Arrays.hashCode(data)));
        System.out.println(Objects.hash(1, 2));
    }
}
```

Save `PrimitiveArrayHashDemo.java` and run:

```bash
javac PrimitiveArrayHashDemo.java
java PrimitiveArrayHashDemo
```

Output:

```text
994
true
true
1025
994
```

The result `1025` explains another trap: `Objects.hash(Arrays.hashCode(data))` hashes **a single boxed int value**, producing `31 + 994 = 1025`, rather than returning `994` as-is. It is still a potentially valid hash function if used consistently, but it is not formula-equivalent to `Arrays.hashCode(data)`.

The last line `Objects.hash(1, 2)` also produces `994`, because the two elements contribute hashes `1` and `2` respectively. This is a coincidence **by the exact formula applied to two numeric element sequences**, not proof that `Objects.hash(data)` automatically spreads `int[]`.

## 5. Null and single-argument calls: casting matters

Because the declared type is `Object...`, a call with `null` can be interpreted at two levels: **the varargs array is `null`** or **the varargs array has one `null` element**.

| Call | Argument array received by Objects.hash | Result |
| --- | --- | --- |
| `Objects.hash()` | Empty `Object[]` array | `1` |
| `Objects.hash((Object) null)` | One-element array `[null]` | `31` |
| `Objects.hash((Object[]) null)` | The varargs array itself is `null` | `0` |
| `Objects.hash("A")` | One-element array `["A"]` | `96` |
| `Objects.hashCode(null)` | One `null` object | `0` |

The result `0` for the `null` varargs array case comes from `Arrays.hashCode((Object[]) null)`. When there is one `null` element, the algorithm starts from `1` and computes `31 * 1 + 0 = 31`.

Calling `Objects.hash(null)` directly does not convey clear intent and can trigger a compiler warning because the `null` expression fits multiple varargs interpretations. Cast explicitly when you need to distinguish the two cases; in application code, avoid designs that depend on this ambiguity.

Distinguish `null` as **a field inside an object** from `null` as **the entire argument array**. If your class uses `Objects.hash(name, nullableCode)`, a value `nullableCode == null` merely contributes 0 for that element; it is not a `null` varargs array.

## 6. Object[] with nested arrays: does not automatically deep-compare or deep-hash

Consider:

```java
Object[] nested = {new int[] {1, 2}};
```

`Objects.hash((Object[]) nested)` iterates over the **outer-level elements**. However, the sole element is an `int[]`, whose `hashCode()` is identity-based. It **does not automatically descend** to hash the two numbers `1` and `2`.

Therefore:

- `Arrays.hashCode(nested)`: computes the outer-level hash from each element's hash; the inner array contributes its identity hash.
- `Arrays.deepHashCode(nested)`: applies deep hashing rules to nested arrays, in this example using the contents `{1, 2}`.
- `Objects.hash((Object) nested)`: treats **the entire outer array** as a single value, then uses the identity hash of the outer array itself.

Similarly for equality:

- `Arrays.equals(nestedA, nestedB)` compares each outer-level element using `equals`; two inner arrays with different references are not automatically equal.
- `Arrays.deepEquals(nestedA, nestedB)` supports deep comparison of nested array contents.

To reliably test semantic differences, do not assert that two hash values must be different; collisions are valid. Instead, use guaranteed conditions:

```java
import java.util.Arrays;
import java.util.Objects;

public class NestedArrayHashDemo {
    public static void main(String[] args) {
        Object[] left = {new int[] {1, 2}};
        Object[] right = {new int[] {1, 2}};

        System.out.println(Arrays.equals(left, right));
        System.out.println(Arrays.deepEquals(left, right));
        System.out.println(
                Objects.hash((Object[]) left)
                == Arrays.hashCode(left)
        );
        System.out.println(
                Arrays.deepHashCode(left) == Arrays.deepHashCode(right)
        );
    }
}
```

Save `NestedArrayHashDemo.java` and run:

```bash
javac NestedArrayHashDemo.java
java NestedArrayHashDemo
```

Output:

```text
false
true
true
true
```

Both structures have the same deep contents, yet their inner arrays are two separate objects. `Arrays.deepHashCode` yields equal results for the two deeply equal structures. `Objects.hash` does not automatically turn into `deepHashCode` just because an element inside is an array.

## 7. Using Objects.hash() properly in equals/hashCode

The fundamental rule of `Object` is:

`a.equals(b) ⇒ a.hashCode() == b.hashCode()`

If a class compares across multiple fields, `Objects.hash` is a convenient choice when every field has a `hashCode()` compatible with that field's own `equals`. For example, with `String`, `Integer`, and immutable value objects that have proper equality/hash contracts, the code is usually very clean:

```java
@Override
public int hashCode() {
    return Objects.hash(countryCode, customerId);
}
```

This is an example method inside a class with two fields, not a standalone program.

However, there is an important trap when fields are **arrays**. If `equals` uses `Arrays.equals(data, other.data)` to compare **contents**, while `hashCode` returns `Objects.hash(data)` with `data` as `byte[]`, the hash code will be based on array identity, **not reliably compatible** with content-based equality.

Standard approach for a single array:

```java
@Override
public int hashCode() {
    return Arrays.hashCode(data);
}
```

When combining with other fields, you can pass the **content hash of the array** into `Objects.hash` as a single value:

```java
@Override
public int hashCode() {
    return Objects.hash(type, Arrays.hashCode(data));
}
```

This is a valid strategy because if two objects have the same `type` and the same `data` contents, their corresponding `type.hashCode()` and `Arrays.hashCode(data)` are also equal. However, the numeric result **does not have to match** `Arrays.hashCode(data)` alone, and hash distribution/collisions are a separate consideration.

### Complete Java 17 example: value object with an array field

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class MixedFieldsHashDemo {
    record AttachmentKey(String kind, byte[] bytes) {
        public AttachmentKey {
            Objects.requireNonNull(kind, "kind");
            Objects.requireNonNull(bytes, "bytes");
            bytes = bytes.clone();
        }

        @Override
        public byte[] bytes() {
            return bytes.clone();
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || other instanceof AttachmentKey that
                    && kind.equals(that.kind)
                    && Arrays.equals(bytes, that.bytes);
        }

        @Override
        public int hashCode() {
            return Objects.hash(kind, Arrays.hashCode(bytes));
        }
    }

    public static void main(String[] args) {
        byte[] source = {10, 20};
        AttachmentKey a = new AttachmentKey("image", source);
        AttachmentKey b = new AttachmentKey("image", new byte[] {10, 20});

        Set<AttachmentKey> keys = new HashSet<>();
        keys.add(a);

        System.out.println(a.equals(b));
        System.out.println(a.hashCode() == b.hashCode());
        System.out.println(keys.contains(b));

        source[0] = 99;
        System.out.println(a.bytes()[0]);

        byte[] copied = a.bytes();
        copied[1] = 77;
        System.out.println(a.bytes()[1]);

        System.out.println(a.equals(b));
    }
}
```

Save `MixedFieldsHashDemo.java` and run:

```bash
javac MixedFieldsHashDemo.java
java MixedFieldsHashDemo
```

Output:

```text
true
true
true
10
20
true
```

Here `equals` checks `kind` by string equality and `bytes` by byte-by-byte content. `hashCode` uses `Objects.hash(kind, Arrays.hashCode(bytes))` to combine values matching the same rules.

The constructor copies the input array and the accessor returns a copy, so callers cannot easily mutate the array defining equality after the object has been added to a `HashSet`. For multidimensional arrays, simply copying the outer array will not protect inner arrays; an appropriate deep copy must be designed.

**Note:** Default generated `equals`/`hashCode` of a record containing an array does not automatically compare/hash by array content. That is why the example overrode both methods. Overriding only `equals` by content while leaving `hashCode` by identity can break the contract with `HashSet`/`HashMap`.

## 8. How to choose the right hash method for arrays?

| Purpose | Usually suitable tool | Keep in mind |
| --- | --- | --- |
| Hashing multiple independent values | `Objects.hash(a, b, c)` | Varargs is an `Object[]` |
| Hashing a single object, possibly `null` | `Objects.hashCode(obj)` | For `null` returns 0; for arrays still identity hash |
| Hashing contents of one-dimensional `int[]`, `byte[]` | `Arrays.hashCode(array)` | Do not use `Objects.hash(array)` if content hash is wanted |
| Hashing contents of one-dimensional `String[]` | `Arrays.hashCode(array)` | `Objects.hash((Object[]) array)` gives the same result but is easily misunderstood |
| Hashing contents of nested arrays | `Arrays.deepHashCode(array)` | Pair with `Arrays.deepEquals` matching the structure |
| Combining String and array by content | `Objects.hash(name, Arrays.hashCode(array))` | Equality must also check name and array contents |
| Intentionally hashing an array's identity | `System.identityHashCode(array)` or identity hash by design | Do not treat it as a content hash or unique ID |

`Objects.hash` does not guarantee that all hash values are unique, is not a security algorithm, and does not promise a stable value across runs for every object type. For checksum or long-term storage requirements, specify a dedicated algorithm and data representation.

## 9. Performance and code readability

`Objects.hash(a, b, c)` is convenient and easy to maintain, especially for classes with a few fields. However, because varargs allocates or uses an `Object[]` array and primitive values may require boxing, it can add memory allocation and computation overhead.

For code called very frequently on a *hot path*, consider:

```java
@Override
public int hashCode() {
    int result = Integer.hashCode(id);
    result = 31 * result + name.hashCode();
    return result;
}
```

This snippet is an illustrative method inside a class with `int id` and non-`null` `String name`. A manually written combining algorithm can also be correct as long as equal objects produce equal hashes; Java **does not require** using `Objects.hash` or multiplier 31 in every class.

Do not optimize prematurely without measuring. For foundational lessons, **correct equality semantics**, `null` handling, and understanding varargs matter more than saving a utility call. If actual performance is an issue, measure with a benchmark tool that accounts for JIT, warmup, and application load.

## 10. Common mistakes and fixes

**Mistake 1 — assuming `Objects.hash(array)` is always a content hash.** For `int[]`, the call treats the array as a single object; for `String[]`, it may use the array as the varargs list. The fix is to express intent with `Arrays.hashCode(array)` when a one-dimensional content hash is needed.

**Mistake 2 — omitting the cast when passing Object[].** `Objects.hash((Object[]) array)` and `Objects.hash((Object) array)` have two different meanings. Write the cast explicitly or call `Arrays.hashCode` directly for readability.

**Mistake 3 — thinking `Objects.hash(x) == x.hashCode()`.** For an ordinary non-`null` `x`, `Objects.hash(x)` hashes a one-element array using the formula `31 + x.hashCode()`; `Objects.hashCode(x)` is what returns the object's raw hash.

**Mistake 4 — using `Objects.hash(data)` when `equals` compares byte[] contents.** Choose a compatible content hash, such as `Arrays.hashCode(data)`, and manage array immutability when used as a key.

**Mistake 5 — considering only the outer array when data has multiple nested levels.** `Arrays.hashCode(Object[])` and `Objects.hash((Object[]) outer)` do not automatically deep-hash inner arrays. If equality is deep, use `Arrays.deepEquals` with `Arrays.deepHashCode` according to the appropriate model.

**Mistake 6 — thinking equal hashes mean equal objects.** Two different objects are allowed to share the same hash code. Hashing helps organize/look up buckets; `equals` is the rule for identifying equal values.

**Mistake 7 — mutating an array after using the object as a hash key.** If hash/equality depends on array contents, modifying elements while the object is in a `HashSet` can make lookups unreliable. Prefer defensive copies and immutable data defining equality.

## 11. Practice questions

**Question 1.** Does `Objects.hash("A")` equal `"A".hashCode()`?

**Answer:** No. For `"A"`, the two numbers are `96` and `65`. `Objects.hash` hashes a one-element varargs array.

**Question 2.** `String[] codes = {"A", "B"};`. What is the difference between `Objects.hash((Object[]) codes)` and `Objects.hash((Object) codes)`?

**Answer:** The first passes the array itself as the argument list, hashing the first-level element contents; the second treats the whole array as a single Object and uses the array's identity hash.

**Question 3.** Must `Objects.hash(new int[]{1, 2})` equal `Arrays.hashCode(new int[]{1, 2})`?

**Answer:** No. A primitive array is treated as a single object in varargs and uses identity hash; `Arrays.hashCode(int[])` computes from the array's contents.

**Question 4.** Why can `Objects.hash(Arrays.hashCode(data))` differ from `Arrays.hashCode(data)`?

**Answer:** Because hashing **a single int value** adds the `31 + valueHash` step. For `data = {1, 2}`, the corresponding results are `1025` and `994`.

**Question 5.** Two objects have arrays with different references but the same contents and are considered equal by `equals`. How should `hashCode` be chosen?

**Answer:** It must compute the hash from the same contents examined by equality, such as `Arrays.hashCode` for a one-dimensional primitive array, or `Objects.hash(type, Arrays.hashCode(data))` if there are other fields. Also control whether the array can be mutated.

**Question 6.** Given `Object[] outer = {new int[]{1, 2}};`, does `Objects.hash((Object[]) outer)` deep-hash the two integers?

**Answer:** No. The outer element is an `int[]` array and contributes its identity hash. To deep-hash a nested structure, consider `Arrays.deepHashCode(outer)`.

**Question 7.** Why does `Objects.hash((Object[]) null)` produce a different result from `Objects.hash((Object) null)`?

**Answer:** The first passes a `null` varargs array and yields `0`; the second creates an array containing one `null` element and yields `31`.

## 12. Key takeaways

1. `Objects.hash(Object... values)` is equivalent to `Arrays.hashCode` on **the actual varargs array**.
2. `Objects.hash(a, b)` hashes two elements in order; `Objects.hash(a)` **does not necessarily** equal `Objects.hashCode(a)` or `a.hashCode()`.
3. `Object[]` (for example `String[]`) can be passed **directly as the varargs array**; `(Object[])` and `(Object)` casts express two different meanings.
4. `int[]` and primitive arrays are **not** `Object[]`; `Objects.hash(primitiveArray)` hashes the array's identity, not its elements.
5. When a **content hash** is needed, use `Arrays.hashCode` (one-dimensional) or `Arrays.deepHashCode` (nested), paired with the corresponding equality.
6. For classes with multiple fields including an array, you can combine `Objects.hash(name, Arrays.hashCode(array))` if `equals` also inspects name and array contents.
7. Preserving the `equals`/`hashCode` contract and key stability matters more than whether the hash expression is written short or long.

Official documentation: [`Objects.hash` / `Objects.hashCode` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html), [`Arrays.hashCode` and `Arrays.deepHashCode` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html), [`Object.equals/hashCode` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html).