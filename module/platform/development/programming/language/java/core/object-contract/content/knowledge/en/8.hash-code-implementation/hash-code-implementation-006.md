# `Objects.hash()` for Multiple Fields and How It Differs from a Single Field's `hashCode()`

## 1. Three Easily Confused Calls

In Java, `java.util.Objects` provides two different utility methods:

```java
public static int Objects.hash(Object... values);
public static int Objects.hashCode(Object o);
```

The lines above only describe **signatures**, not source code to paste directly into a class; the `Objects.` prefix is written to clarify the owning class.

Distinguish them from the **instance method** `public int hashCode()` inherited from `java.lang.Object`:

| Call | Meaning | When data is `null` |
| --- | --- | --- |
| `x.hashCode()` | Uses the hashing algorithm provided by object `x` | If **receiver `x` is `null`**, throws `NullPointerException` |
| `Objects.hashCode(x)` | Returns `x.hashCode()` if `x != null`; returns `0` if `x == null` | Null-safe |
| `Objects.hash(x)` | Computes the combined hash of an **argument list** containing one element `x` | If a single `null` is passed as an element, the result usually differs from `Objects.hashCode(null)` |
| `Objects.hash(a, b, c)` | Produces a combined hash in order from multiple values | May contain `null` elements |

**Rule to remember:** `Objects.hash(x)` does not mean `Objects.hashCode(x)` and is not guaranteed to equal `x.hashCode()`, even when there is only one argument. `Objects.hash(...)` processes a sequence of elements via `Arrays.hashCode(Object[])`; it applies an extra initialization and combining step.

## 2. Why Does `Objects.hash(x)` Differ from `x.hashCode()`?

`Objects.hash(Object... values)` takes a variable-length parameter (**varargs**). When individual arguments are passed, Java packs them into an `Object[]` array, and `Objects.hash` computes the result like `Arrays.hashCode(values)`.

For a non-null sequence `values`, the `Arrays.hashCode(Object[])` algorithm is equivalent to:

```java
int result = 1;
for (Object element : values) {
    result = 31 * result + (element == null ? 0 : element.hashCode());
}
return result;
```

This is an **algorithm illustration**, not a standalone Java program. Arithmetic uses `int`; if overflow occurs, Java follows 32-bit integer wrap-around rules, which is permitted in hashing.

Because `result` starts at `1`, for **a single element `x`** passed as a single argument:

```text
Objects.hash(x) = 31 + Objects.hashCode(x)  (computed in 32-bit int arithmetic)
```

Specifically, if `x` is non-null, `Objects.hashCode(x) == x.hashCode()`, whereas `Objects.hash(x)` adds the `31` combining step. This is the direct reason why the outputs differ. This formula assumes a single element is actually passed into the varargs array; syntactic exceptions exist when the argument is a reference-typed array or an uncast `null`, explained in the pitfalls section.

Example with the string `"abc"`:

- `"abc".hashCode()` returns `96354`.
- `Objects.hashCode("abc")` also returns `96354`.
- `Objects.hash("abc")` returns `31 + 96354 = 96385`.

With a single `null` element written explicitly as `(Object) null`, `Objects.hash((Object) null)` returns `31`, whereas `Objects.hashCode(null)` returns `0`; meanwhile, `((String) null).hashCode()` throws `NullPointerException`.

## 3. `Objects.hash(a, b, ...)` Combines Multiple Fields

When a class's `equals()` defines equality using **multiple fields**, `hashCode()` must compute consistently from those fields. For example, a book key identified by `code` and `edition`:

```java
@Override
public int hashCode() {
    return Objects.hash(code, edition);
}
```

The snippet above is a **method inside a class with fields `code` and `edition`**, not a standalone program. `Objects.hash(code, edition)` produces an `int` depending on both values and their order. The compiler boxes the primitive field `edition` into an `Integer` when packing it into the varargs array.

Formula example with `code = "ab"`, `edition = 7`:

```text
"ab".hashCode() = 3105
initial result = 1
result after code = 31 * 1 + 3105 = 3136
result after edition = 31 * 3136 + 7 = 97223
Objects.hash("ab", 7) = 97223
```

You cannot just take `code.hashCode()` if `equals()` also checks `edition`: two objects with the same `code` but different `edition` may validly share a hash, yet ignoring a field generally degrades hash distribution. The mandatory rule is: **if two objects are equal according to `equals()`, their hashes must be equal**. The converse does not hold: matching hashes do not prove two objects are equal.

## 4. Complete, Runnable Java 17+ Example

Save the following code into `ObjectsHashDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class ObjectsHashDemo {
    static final class BookKey {
        private final String code;
        private final int edition;

        BookKey(String code, int edition) {
            this.code = Objects.requireNonNull(code);
            this.edition = edition;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof BookKey other)) return false;
            return edition == other.edition && code.equals(other.code);
        }

        @Override
        public int hashCode() {
            return Objects.hash(code, edition);
        }
    }

    public static void main(String[] args) {
        String value = "abc";
        System.out.println("instance: " + value.hashCode());
        System.out.println("Objects.hashCode: " + Objects.hashCode(value));
        System.out.println("Objects.hash(one): " + Objects.hash(value));
        System.out.println("Objects.hashCode(null): " + Objects.hashCode(null));
        System.out.println("Objects.hash((Object) null): " + Objects.hash((Object) null));
        System.out.println("Objects.hash(ab, 7): " + Objects.hash("ab", 7));

        BookKey first = new BookKey("ab", 7);
        BookKey equal = new BookKey("ab", 7);
        BookKey different = new BookKey("ab", 8);

        Map<BookKey, String> books = new HashMap<>();
        books.put(first, "available");
        System.out.println("equal keys: " + first.equals(equal));
        System.out.println("equal hashes: " + (first.hashCode() == equal.hashCode()));
        System.out.println("lookup equal: " + books.get(equal));
        System.out.println("lookup different: " + books.get(different));
    }
}
```

Run with JDK 17 or later:

```bash
javac ObjectsHashDemo.java
java ObjectsHashDemo
```

Output:

```text
instance: 96354
Objects.hashCode: 96354
Objects.hash(one): 96385
Objects.hashCode(null): 0
Objects.hash((Object) null): 31
Objects.hash(ab, 7): 97223
equal keys: true
equal hashes: true
lookup equal: available
lookup different: null
```

`BookKey` has `equals()` check both `code` and `edition`; `hashCode()` also passes both fields to `Objects.hash`. Therefore, two equivalent keys can look up the same entry in `HashMap`. Creating a new key with a different `edition` does not retrieve the stored entry.

The output `lookup different: null` means `Map.get` found no mapping for that key in this example, not that the hash values were guaranteed to differ. Even when a collision occurs, `HashMap` still checks key equality to tell them apart.

## 5. Compared with Writing the `hashCode()` Formula Manually

`Objects.hash(code, edition)` is simple and helps prevent omitting a field. For the two example fields, you can manually write the equivalent algorithm:

```java
@Override
public int hashCode() {
    int result = 1;
    result = 31 * result + code.hashCode();
    result = 31 * result + Integer.hashCode(edition);
    return result;
}
```

This is a **replacement method** in the `BookKey` class, not pasted alongside the old `hashCode()` method. With `code` non-`null` and `edition` of type `int` as declared, this manual formula yields the exact same result as `Objects.hash(code, edition)`.

Pros and cons comparison:

| Criterion | `Objects.hash(code, edition)` | Manual formula |
| --- | --- | --- |
| Conciseness | Short, easy to read with many fields | Longer, though the algorithm is explicit |
| Handling `null` in reference fields | `null` elements contribute `0` | Must handle manually if a field can be `null` |
| Extra overhead | Varargs creates an array; primitives may require boxing | Can avoid array allocation and boxing |
| `equals`/`hashCode` contract | Must manually pick fields consistent with `equals()` | Also must manually pick fields consistent with `equals()` |

In typical business code, prioritize clarity and contract compliance. In code invoked continuously with high performance demands, measure first before replacing `Objects.hash` with manual calculation; do not claim `Objects.hash` is always a bottleneck.

## 6. Important Pitfalls When Using Varargs, `null`, and Arrays

### `Objects.hash(null)` Can Have an Unexpected Meaning

A bare `null` argument can be interpreted by the compiler as a **`null` `Object[]` varargs array** rather than a single `null` element, accompanied by a compiler warning. In that case `Arrays.hashCode((Object[]) null)` returns `0`. To explicitly express one argument whose value is `null`, write `Objects.hash((Object) null)`, which yields `31`. If the goal is merely to get the hash of **one** nullable reference, writing `Objects.hashCode(x)` is usually more appropriate.

### Arrays Are Not Hashed by Content by Default

For an `Object[] elements` variable, calling `Objects.hash(elements)` may use that array itself as the **entire varargs array**—meaning it hashes each element—rather than creating a one-element array containing `elements`. By contrast, `Objects.hash((Object) elements)` hashes one element of array type; an array's default `hashCode()` is based on array identity.

If `equals()` compares array contents, pair `Arrays.equals(a, b)` with `Arrays.hashCode(a)` (or `Arrays.deepEquals`/`Arrays.deepHashCode` as appropriate for nested array structures), instead of blindly calling `Objects.hash(array)` without considering how varargs are passed.

### `Objects.hash()` Does Not Replace the `equals()` Contract

Overriding `equals()` without a consistent `hashCode()` can cause `HashMap.get` and `HashSet.contains` to miss entries. Even when using `Objects.hash`, you must still choose the fields that define equality, and avoid mutating them once the object is used as a key in a hash structure.

`Objects.hash()` is also not a cryptographic hash function, does not guarantee uniqueness, and should not be used as a stable cross-system identifier. Its `int` result can be negative and can collide.

## 7. Quick Selection Guide

- **One reference field guaranteed non-`null`:** `field.hashCode()` is direct, with no varargs combining step.
- **One nullable field:** `Objects.hashCode(field)` returns `0` when `null` and the normal hash otherwise.
- **Multiple fields participating in `equals()`:** `Objects.hash(fieldA, fieldB, ...)` creates a clear combined hash, provided it matches `equals()`.
- **Optimizing hot code:** You can write `31 * result + ...` or use `Integer.hashCode`, `Long.hashCode`, and specialized methods after profiling.
- **Array fields:** Choose `Arrays.hashCode`/`Arrays.deepHashCode` matching the chosen content-comparison method.

## 8. Self-Check

1. Why is `Objects.hash("abc")` equal to `96385`, while `"abc".hashCode()` is `96354`? — Because the varargs array algorithm starts with `result = 1`, then adds `31 * 1` before the element's hash.
2. Are `Objects.hashCode(null)` and `Objects.hash((Object) null)` equal? — No: they are `0` and `31` respectively.
3. If `equals()` checks both `code` and `edition`, does hashing only `code` automatically violate the contract? — Not automatically: equal keys still share the same `code`. However, omitting `edition` can increase collisions; using both usually distributes better.
4. If two keys produce the same `Objects.hash` result, must they be equal? — No. Hash structures still must check `equals()`.

**Remember:** `x.hashCode()` gets the hash provided by one object; `Objects.hashCode(x)` is its null-safe counterpart; and `Objects.hash(...)` **combines elements in an argument sequence**. They differ in both purpose and return value when given a single element.