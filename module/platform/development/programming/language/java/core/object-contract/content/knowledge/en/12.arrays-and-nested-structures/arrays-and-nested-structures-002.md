# `Arrays.equals()` and `Arrays.hashCode()` for One-Dimensional Arrays in Java

## 1. The Problem: Two arrays with the same elements are not necessarily the same object

In Java, **arrays are objects**. Two array variables can reference **the same array**, or reference **two separate arrays** with identical elements.

~~~java
int[] a = {1, 2, 3};
int[] b = {1, 2, 3};
int[] alias = a;
~~~

- `a == b` returns `false`: the two array initializer expressions created **two different array objects**.
- `a == alias` returns `true`: the assignment `alias = a` only copies the **reference**, without creating a new array.
- `a.equals(b)` returns `false`: arrays do not override the `equals(Object)` method from `Object` to compare element by element.
- `Arrays.equals(a, b)` returns `true`: compares the **positional content** of two one-dimensional arrays.

Similarly, the `hashCode()` method inherited from `Object` on an array object **does not define a hash based on its elements**. If you need to compare two arrays as **two values with equal content**, use the API pair:

~~~java
java.util.Arrays.equals(a, b);
java.util.Arrays.hashCode(a);
~~~

This method pair is especially important when an array is part of the state of a value object or an object used as a `HashMap` key / `HashSet` element.

## 2. How does `Arrays.equals()` check equality by content?

`java.util.Arrays` provides `equals` overloads for one-dimensional arrays containing each primitive type (`boolean[]`, `byte[]`, `short[]`, `char[]`, `int[]`, `long[]`, `float[]`, `double[]`) and reference arrays `Object[]`.

For two arrays of the appropriate matching component type:

1. Two references pointing to the same array are equal, including when **both are `null`**.
2. One side is `null` and the other is not `null` means not equal.
3. Different lengths means not equal.
4. Equal lengths means checking **each pair of elements at the same index**, from start to end.
5. If the first unequal pair of elements is encountered, the result is `false`; only when all corresponding positions are equal does it return `true`.

Element order matters: `[1, 2, 3]` is not equal to `[3, 2, 1]`. With this content comparison, two arrays do not need to share the same address or reference.

### Runnable example: `int[]` arrays

Create file `PrimitiveArraysDemo.java`:

~~~java
import java.util.Arrays;

public class PrimitiveArraysDemo {
    public static void main(String[] args) {
        int[] a = {1, 2, 3};
        int[] b = {1, 2, 3};
        int[] differentOrder = {3, 2, 1};
        int[] alias = a;

        System.out.println("a == b: " + (a == b));
        System.out.println("a == alias: " + (a == alias));
        System.out.println("a.equals(b): " + a.equals(b));
        System.out.println("Arrays.equals(a,b): " + Arrays.equals(a, b));
        System.out.println("same contents hash: "
                + (Arrays.hashCode(a) == Arrays.hashCode(b)));
        System.out.println("order equal: "
                + Arrays.equals(a, differentOrder));
        System.out.println("hash(a): " + Arrays.hashCode(a));
        System.out.println("null equals null: "
                + Arrays.equals((int[]) null, (int[]) null));
        System.out.println("null equals a: "
                + Arrays.equals((int[]) null, a));
        System.out.println("hash(null): " + Arrays.hashCode((int[]) null));
        System.out.println("hash(empty): " + Arrays.hashCode(new int[0]));

        b[0] = 9;
        System.out.println("after mutation: " + Arrays.equals(a, b));
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac -encoding UTF-8 PrimitiveArraysDemo.java
java PrimitiveArraysDemo
~~~

Stdout:

~~~text
a == b: false
a == alias: true
a.equals(b): false
Arrays.equals(a,b): true
same contents hash: true
order equal: false
hash(a): 30817
null equals null: true
null equals a: false
hash(null): 0
hash(empty): 1
after mutation: false
~~~

`Arrays.hashCode(new int[] {1, 2, 3})` is `30817` according to the formula in the next section. This is the value of the **content-based hashing algorithm**; do not confuse it with `a.hashCode()`, which inherits the object hashing mechanism.

In a direct call to `Arrays.equals(null, null)` or `Arrays.hashCode(null)`, the compiler may not be able to choose an overload because there are multiple array types. Explicit casting, such as `(int[]) null`, or passing a variable with declared type `int[]` helps select the right overload.

## 3. `Arrays.hashCode()` generates content-based hash codes

`Arrays.hashCode` also has overloads corresponding to the primitive one-dimensional array types and `Object[]`. For a non-`null` array, the function iterates through the elements **in order**, starting with `result = 1` and repeating the formula:

~~~text
result = 1
for each element:
    result = 31 * result + elementHash
return result
~~~

Here `elementHash` is the hash value of each element according to the rule for its element type:

- `int[]`: the `int` value of the element itself.
- `long[]`: a value as from `Long.hashCode(long)`.
- `boolean[]`: a value as from `Boolean.hashCode(boolean)`.
- `byte[]`, `short[]`, and `char[]`: the numeric value of the element via appropriate conversion to `int`.
- `float[]` and `double[]`: hashing corresponding to `Float.hashCode` or `Double.hashCode`.
- `Object[]`: `0` if the element is `null`; if non-`null`, calls `element.hashCode()`.

For array `int[] {1, 2, 3}`:

~~~text
initially:          result = 1
after element 1:    result = 31 * 1   + 1 = 32
after element 2:    result = 31 * 32  + 2 = 994
after element 3:    result = 31 * 994 + 3 = 30817
~~~

For a `null` array, `Arrays.hashCode` returns `0`; for an **empty but non-`null`** array, the result is `1`. The calculation uses `int` and can overflow according to Java integer semantics; this is not an algorithm bug.

### The contract between `equals` and `hashCode`

If `Arrays.equals(a, b)` returns `true` with the appropriate overload, then `Arrays.hashCode(a) == Arrays.hashCode(b)` must also hold. The converse is **not guaranteed**: two arrays with different contents can still have the same hash code because the result has only 32 bits.

Therefore, **do not** use the condition `Arrays.hashCode(a) == Arrays.hashCode(b)` in place of actual content comparison. Hashing is suited for selecting buckets or speeding up lookups; `equals` is what determines value equality.

## 4. Primitive arrays and reference arrays differ in element comparison

### Primitive arrays

For `int[]`, `byte[]`, `char[]`, and other primitive types, `Arrays.equals` applies the value comparison appropriate for the type. For example, `char[] {'a', 'b'}` and `char[] {'b', 'a'}` are not equal because the order differs.

There is no `Arrays.equals(int[], long[])` overload to automatically convert types and compare. Two primitive arrays of different types must be intentionally converted/normalized if business requirements need cross-type content comparison.

### Reference arrays `Object[]`

For arrays containing objects, `Arrays.equals(Object[] a, Object[] b)` compares each pair of elements using **the element's `equals()`** (handling `null`), without requiring the two elements to be the same object.

~~~java
String[] first = {"Java", "Core"};
String[] second = {new String("Java"), "Core"};
System.out.println(Arrays.equals(first, second)); // true
~~~

The two strings at the first position may be different `String` objects, but `String.equals` compares contents, so the two arrays are equal. When hashing `Object[]`, `Arrays.hashCode` calls `hashCode()` on each element; if the elements properly implement the `equals/hashCode` contract, the whole array maintains consistency.

If an element is a class you wrote and that class **does not override `equals`**, the result is still based on element identity. Thus `Arrays.equals(Object[], Object[])` is only a **single-level comparison** following the elements' own rules; it does not automatically turn every kind of object into values compared by deep internal fields.

### Runnable example: `String[]`, null elements, and order

Create file `ReferenceArraysDemo.java`:

~~~java
import java.util.Arrays;

public class ReferenceArraysDemo {
    public static void main(String[] args) {
        String[] first = {"Java", "Core"};
        String[] second = {new String("Java"), "Core"};
        String[] reordered = {"Core", "Java"};

        Object[] left = {null, new String("A"), 7};
        Object[] right = {null, "A", Integer.valueOf(7)};

        System.out.println("same String content: "
                + Arrays.equals(first, second));
        System.out.println("same String hash: "
                + (Arrays.hashCode(first) == Arrays.hashCode(second)));
        System.out.println("different order: "
                + Arrays.equals(first, reordered));
        System.out.println("null and objects equal: "
                + Arrays.equals(left, right));
        System.out.println("null and objects hash: "
                + (Arrays.hashCode(left) == Arrays.hashCode(right)));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReferenceArraysDemo.java
java ReferenceArraysDemo
~~~

Stdout:

~~~text
same String content: true
same String hash: true
different order: false
null and objects equal: true
null and objects hash: true
~~~

`Integer.valueOf(7)` is a wrapper object; `Integer.equals` compares same type and same value. An `Object[]` array can contain multiple element types, provided each pair of elements offers `equals/hashCode` semantics compatible with the requirement.

## 5. Special cases of `float[]` and `double[]` arrays

For `float[]` and `double[]`, `Arrays.equals` handles two corresponding floating-point values according to the semantics of the wrapper comparison methods (`Float.compare`, `Double.compare`), rather than relying only on intuition about the primitive `==` operator:

- `NaN` values are considered equal to each other when compared with `Arrays.equals` (NaN representations are canonicalized according to the corresponding rules).
- `+0.0` and `-0.0` are considered **different**.
- `Arrays.hashCode` generates hashes consistent with those semantics, so arrays considered equal by `Arrays.equals` have the same hash.

Create file `FloatingArraysDemo.java`:

~~~java
import java.util.Arrays;

public class FloatingArraysDemo {
    public static void main(String[] args) {
        double[] plusZero = {+0.0d};
        double[] minusZero = {-0.0d};
        double[] nanA = {Double.NaN};
        double[] nanB = {
                Double.longBitsToDouble(0x7ff0000000000001L)
        };

        System.out.println("primitive +0 == -0: " + (+0.0d == -0.0d));
        System.out.println("array +0 equals -0: "
                + Arrays.equals(plusZero, minusZero));
        System.out.println("primitive NaN == NaN: "
                + (Double.NaN == Double.NaN));
        System.out.println("NaN arrays equal: "
                + Arrays.equals(nanA, nanB));
        System.out.println("NaN hashes match: "
                + (Arrays.hashCode(nanA) == Arrays.hashCode(nanB)));
    }
}
~~~

~~~bash
javac -encoding UTF-8 FloatingArraysDemo.java
java FloatingArraysDemo
~~~

Stdout:

~~~text
primitive +0 == -0: true
array +0 equals -0: false
primitive NaN == NaN: false
NaN arrays equal: true
NaN hashes match: true
~~~

For numerical problems that want to treat two values as nearly equal within an **error tolerance**, `Arrays.equals(double[], double[])` does not do that. You need custom comparison rules. If an object needs a `hashCode()` corresponding to a “nearly equal” rule, it must be designed very carefully because standard tolerance-based comparison relations may not be **transitive**, causing difficulties or breaking the `equals()` contract.

## 6. One-dimensional arrays containing array objects: the boundary of shallow comparison

An `int[][]` array may look like a two-dimensional array, but at the Java level it is a **one-dimensional array containing references to `int[]`**. Therefore:

~~~java
int[][] left = {{1, 2}, {3, 4}};
int[][] right = {{1, 2}, {3, 4}};
~~~

- `Arrays.equals(left, right)` uses the `Object[]` overload (because `int[][]` is an array of `int[]` objects) and then calls `equals` on **each sub-array**. Sub-arrays do not define content comparison; newly created sub-arrays do not share identity, so the result is `false`.
- `Arrays.hashCode(left)` hashes the sub-array references/objects using each element's `hashCode`; this is **not a deep hash of the integer contents**.
- `Arrays.deepEquals(left, right)` and `Arrays.deepHashCode(left/right)` are the appropriate API pair if you want to go deep into nested arrays.

Short example:

~~~java
System.out.println(Arrays.equals(left, right));       // false
System.out.println(Arrays.deepEquals(left, right));   // true
~~~

The snippets above assume they are inside a method where `left`, `right` are already declared and `import java.util.Arrays;` is present. The scope of the current article is **one-dimensional arrays**. The `deepEquals/deepHashCode` pair is mentioned only to identify the boundary accurately: the regular `Arrays.equals/hashCode` **does not recursively hash or compare the contents of inner array objects**.

## 7. Using the right method pair in `equals()` and `hashCode()` of a value object

Suppose there is a class representing an identifier in `byte[]` form. If two instances are defined as equal when **the byte sequences have the same content**, then:

~~~java
@Override
public boolean equals(Object obj) {
    if (this == obj) return true;
    if (!(obj instanceof ByteArrayKey other)) return false;
    return Arrays.equals(bytes, other.bytes);
}

@Override
public int hashCode() {
    return Arrays.hashCode(bytes);
}
~~~

This is an **illustrative excerpt**, assuming the class has a `byte[] bytes` field and `import java.util.Arrays`. If you use `bytes.equals(other.bytes)` or `bytes.hashCode()`, the meaning reverts to **array identity**; it is especially dangerous if `equals` compares content while `hashCode` hashes identity, because it can violate the `Object` contract.

### Runnable example: `HashMap` key using array content

Create file `ByteArrayKeyDemo.java`:

~~~java
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;

public class ByteArrayKeyDemo {
    static final class ByteArrayKey {
        private final byte[] bytes;

        ByteArrayKey(byte[] input) {
            this.bytes = input.clone();
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof ByteArrayKey other)) return false;
            return Arrays.equals(bytes, other.bytes);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(bytes);
        }

        byte[] copyBytes() {
            return bytes.clone();
        }
    }

    public static void main(String[] args) {
        byte[] source = {10, 20, 30};
        ByteArrayKey first = new ByteArrayKey(source);
        ByteArrayKey same = new ByteArrayKey(new byte[] {10, 20, 30});

        Map<ByteArrayKey, String> map = new HashMap<>();
        map.put(first, "found");

        System.out.println("equal content: " + first.equals(same));
        System.out.println("matching hashes: "
                + (first.hashCode() == same.hashCode()));
        System.out.println("lookup: " + map.get(same));

        source[0] = 99;
        byte[] exposedCopy = first.copyBytes();
        exposedCopy[1] = 88;

        System.out.println("key stayed unchanged: "
                + Arrays.equals(first.copyBytes(), new byte[] {10, 20, 30}));
        System.out.println("lookup after edits: " + map.get(same));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ByteArrayKeyDemo.java
java ByteArrayKeyDemo
~~~

Stdout:

~~~text
equal content: true
matching hashes: true
lookup: found
key stayed unchanged: true
lookup after edits: found
~~~

**Why does the constructor use `clone()`?** Arrays are mutable: external code could change elements after the key has already been placed into `HashMap`. When the hash depends on content, mutating content can cause lookups to fail to behave as expected. The demo class defends by cloning the input array and only returning **copies** via `copyBytes()`; the class is also `final` and has no method that mutates the internal array.

If a class has both `id` and `byte[] bytes` participating in equality, combine the hashes of both:

~~~java
int result = Integer.hashCode(id);
result = 31 * result + Arrays.hashCode(bytes);
return result;
~~~

The snippet above is merely an illustration in a class with fields `int id` and `byte[] bytes`, where `equals` also compares `id` and `Arrays.equals(bytes, other.bytes)`. In cases with multiple array fields, each field must be compared and hashed according to the same chosen shallow/deep policy.

## 8. Similarly named APIs that are easily confused

| Expression | What does it compare/hash by? | When is it appropriate? |
| --- | --- | --- |
| `a == b` for two array variables | Identity: whether they are the same array object | Need to know if two references share the same array |
| `a.equals(b)` | Usually identity, since arrays use `Object.equals` | Rarely appropriate for checking array data |
| `Arrays.equals(a, b)` | **One-dimensional** content, same order, element-by-element per corresponding type | Primitive arrays, one-dimensional object arrays |
| `Arrays.hashCode(a)` | **One-dimensional** content hash | Paired with `Arrays.equals` in a value object |
| `Arrays.deepEquals(a, b)` | Goes deep into arrays nested inside an object array | Nested array structures |
| `Arrays.deepHashCode(a)` | Corresponding deep hash | Paired with `Arrays.deepEquals` |
| `Objects.equals(a, b)` where `a`, `b` are arrays | Null-safe, but if references differ it calls `a.equals(b)`, **does not compare elements automatically** | Regular object values; avoid using instead of `Arrays.equals` for arrays |
| `Objects.hash(a)` where `a` is a primitive array | One array reference argument; **does not hash each primitive element** | Not suitable as a replacement for `Arrays.hashCode(a)` |

For `Object[]`, `Objects.hash(array)` also has a **varargs trap**: depending on the expression type, the array may be treated as the `Object...` parameter array itself, or as a single element wrapped in varargs. When you want to hash the contents of a one-dimensional array, `Arrays.hashCode(array)` expresses the intent directly and clearly.

## 9. Execution cost: when are array comparison and hashing expensive?

`Arrays.equals` may have to check up to `n` elements sequentially if the two arrays have the same length; if lengths differ or an unequal element is encountered early, the method can exit early. In terms of complexity, the worst case is **O(n)** in the array length.

`Arrays.hashCode` must combine all elements to produce the content hash code, so it has **O(n)** complexity. For reference arrays, it also depends on the `hashCode()` complexity of **each element**. `Arrays.hashCode(int[])` itself does not need to box each element into `Integer`; primitive array overloads process primitive values directly.

Some JVMs may optimize array comparison implementations (especially for certain primitive types), but you should not assume a fixed speedup. When hashing large arrays in a hot loop, measure with a profiler/JMH under real conditions before deciding on a hash caching strategy or changing data structures.

Do not use hashes as a conclusive fast comparison: two equal hashes **do not prove** two arrays are equal. For large immutable array keys, you may consider caching the hash, but you must ensure no array mutations remain that affect equality; caching also carries memory and synchronization costs in designs shared across threads.

## 10. Common mistakes

| Misconception | Accurate understanding |
| --- | --- |
| Two arrays with the same values make `a.equals(b)` `true`. | Arrays use `Object.equals`; use `Arrays.equals(a, b)`. |
| Two arrays with equal hashes definitely have the same elements. | Hashes can collide; use `Arrays.equals` to conclude equality. |
| `Arrays.equals` ignores element positions. | Order **matters**; this is not a set comparison. |
| `Arrays.equals(null, null)` always compiles without a specific type. | Multiple overloads can make the call ambiguous; use typed array variables or cast. |
| `Arrays.hashCode(new int[0])` equals `0` like a `null` array. | An empty array returns `1`; a `null` array returns `0`. |
| `+0.0` and `-0.0` are treated as equal by `Arrays.equals(double[])`. | False: they are treated as different under the corresponding comparison rules. |
| `Arrays.equals` automatically goes deep into `int[][]`. | False: the `int[]` elements of the outer array are compared by object `equals`; consider `deepEquals`. |
| In a value object, `equals` uses `Arrays.equals` while `hashCode` uses `array.hashCode()`. | Risks breaking the contract; use the corresponding `Arrays.hashCode`. |
| Putting a mutable array into a hash key and then modifying elements still guarantees accurate lookups. | Changing content and hash can cause lookups to stop finding the key; copy defensively or keep data immutable. |
| `Objects.equals(a,b)` automatically compares array contents. | It is only null-safe and delegates to `a.equals(b)`; arrays still use identity comparison. |

## 11. Application checklist

When you need to compare or hash **one-dimensional arrays**:

1. Clearly determine whether the goal is **identity** comparison or **content** comparison. Choose `==` for identity, `Arrays.equals` for content.
2. Choose the overload matching the array type. `Arrays.equals(int[], int[])` differs from `Arrays.equals(Object[], Object[])` in element comparison rules.
3. Account for `null`, empty arrays, length, and element order.
4. For `float[]`/`double[]`, remember the rules for `NaN` and the two signs of zero.
5. When used in a value object, implement `equals()` and `hashCode()` consistently: `Arrays.equals` goes with `Arrays.hashCode`, not with `array.hashCode()`.
6. If array elements are themselves arrays, consider a **shallow or deep** policy; do not automatically assume one-dimensional `Arrays.equals/hashCode` is recursive.
7. If the array participates as a hash key, restrict content mutations; consider defensive copies when accepting and returning arrays.
8. Test pairs of arrays with different references but identical data: `Arrays.equals(a,b)` must be `true` and `Arrays.hashCode(a) == Arrays.hashCode(b)` must also be `true`. Also test differing data pairs, `null`, empty arrays, and floating-point edge cases where appropriate.

**Key takeaway:** `Arrays.equals()` and `Arrays.hashCode()` are the standard tool pair for expressing **content-based equality and content-based hashing of one-dimensional arrays**. They differ from the `equals()/hashCode()` inherited from `Object` on the array itself. When placing an array inside a class, the array comparison policy must match the array hashing policy for hash-based structures to work properly.