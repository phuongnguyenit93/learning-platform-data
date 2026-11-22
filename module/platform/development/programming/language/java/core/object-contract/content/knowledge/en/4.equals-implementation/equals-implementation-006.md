# Using `Objects.equals()` for Nullable Fields When Implementing `equals()`

In Java, a reference-type field such as `String`, `Address`, or `Integer` can hold `null`. When overriding `equals(Object)`, calling `field.equals(other.field)` directly can throw `NullPointerException` if `field` is currently `null`. `java.util.Objects.equals(a, b)` is a concise, clear, and **safe expression when one or both references are `null`**.

This lesson focuses on how to use `Objects.equals()` to build a value-based equality contract, coordinate with `hashCode()`, and avoid common mistakes.

## 1. From Unsafe Comparison to `Objects.equals`

The snippet below only illustrates an expression placed inside an `equals` method; it is **not a standalone Java program**:

```java
// Wrong when displayName can be null:
return displayName.equals(other.displayName);
```

If `displayName == null`, accessing `.equals(...)` on a `null` reference will throw an exception. This happens even when `other.displayName` is also `null` and the two fields should be considered equivalent.

Both sides can be checked with an explicit condition, though a more concise form is usually used:

```java
// Equivalent expression in outcome, assuming equals is implemented per contract:
return displayName == other.displayName
        || (displayName != null && displayName.equals(other.displayName));

// Recommended way to write it for a nullable field:
return Objects.equals(displayName, other.displayName);
```

Remember `import java.util.Objects;`. `Objects.equals` is a `static` method, so it is not invoked on an object that might be `null`.

## 2. Rules of `Objects.equals(a, b)`

Behaviorally, `Objects.equals(a, b)` is equivalent to:

```java
a == b || (a != null && a.equals(b))
```

| `a` | `b` | Result | Explanation |
| --- | --- | --- | --- |
| `null` | `null` | `true` | Both are absent of a value |
| `null` | Non-`null` | `false` | Only one side is absent of a value |
| Non-`null` | `null` | `false` for classes adhering to the `equals` contract | `a.equals(null)` must return `false` |
| Same reference | Same reference | `true` | `a == b` holds |
| Two objects with different references, same value | Two objects with different references, same value | Depends on `a.equals(b)` | Delegates to the class's equality definition |

**Fundamental distinctions:**

- `==` on two reference variables checks **same object**; `Objects.equals` checks **equality according to `equals`** and adds `null` handling.
- `Objects.equals` does not automatically traverse fields for deep comparison. If a data type does not override `Object.equals`, two separate instances are still not equal.
- `Objects.equals(a, b)` cannot fix an `a.equals(b)` method that is implemented with broken symmetry or transitivity. It only makes `null` checking safe.

## 3. Complete Example, Runnable on Java 17+

A `ContactProfile` has two nullable fields (`email`, `displayName`) and one primitive field (`priority`). By the **business rule of the example**, all three fields participate in the equality comparison. The object is kept immutable using `private final` to be safer when used as a `HashSet` element or `HashMap` key.

Save the following program to **`NullableEqualsDemo.java`**:

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

final class ContactProfile {
    private final String email;
    private final String displayName;
    private final int priority;

    ContactProfile(String email, String displayName, int priority) {
        this.email = email;
        this.displayName = displayName;
        this.priority = priority;
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        if (!(obj instanceof ContactProfile that)) {
            return false;
        }

        return priority == that.priority
                && Objects.equals(email, that.email)
                && Objects.equals(displayName, that.displayName);
    }

    @Override
    public int hashCode() {
        return Objects.hash(email, displayName, priority);
    }
}

public class NullableEqualsDemo {
    public static void main(String[] args) {
        ContactProfile a = new ContactProfile("an@example.com", null, 1);
        ContactProfile b = new ContactProfile("an@example.com", null, 1);
        ContactProfile named = new ContactProfile("an@example.com", "An", 1);
        ContactProfile missing1 = new ContactProfile(null, null, 1);
        ContactProfile missing2 = new ContactProfile(null, null, 1);

        System.out.println("a.equals(b): " + a.equals(b));
        System.out.println("a.equals(named): " + a.equals(named));
        System.out.println("missing1.equals(missing2): "
                + missing1.equals(missing2));
        System.out.println("a.equals(null): " + a.equals(null));
        System.out.println("Objects.equals(null, null): "
                + Objects.equals(null, null));
        System.out.println("Objects.equals(null, \"x\"): "
                + Objects.equals(null, "x"));
        System.out.println("Objects.equals(\"x\", null): "
                + Objects.equals("x", null));

        Set<ContactProfile> profiles = new HashSet<>();
        profiles.add(a);
        profiles.add(b);
        profiles.add(named);
        System.out.println("HashSet size: " + profiles.size());
        System.out.println("Equal objects share hashCode: "
                + (a.hashCode() == b.hashCode()));
    }
}
```

Compile and run in the directory containing the file above:

```bash
javac NullableEqualsDemo.java
java NullableEqualsDemo
```

Exact output, independent of memory addresses or specific hash values:

```text
a.equals(b): true
a.equals(named): false
missing1.equals(missing2): true
a.equals(null): false
Objects.equals(null, null): true
Objects.equals(null, "x"): false
Objects.equals("x", null): false
HashSet size: 2
Equal objects share hashCode: true
```

**Explanation of output:**

1. `a` and `b` are two separate instances, but `email`, `displayName`, and `priority` are all equivalent. Specifically, `Objects.equals(null, null)` returns `true`.
2. `a` and `named` differ at `displayName`: one side is `null`, the other is `"An"`. The result is `false`, with no exception.
3. `missing1` and `missing2` are equal in this model because both nullable fields are `null` and `priority` is equal. If the domain does not want to treat two profiles with missing information as equal, you must change **the class's comparison rule**, instead of expecting `Objects.equals` to infer the meaning of `null`.
4. `a.equals(null)` returns `false`, adhering to the `equals` contract. The check `obj instanceof ContactProfile that` is `null`-safe and does not access fields before verifying the type.
5. `HashSet` keeps only one of the two equal elements `a` and `b`, while keeping `named` because it differs by `equals`. `HashSet` relies on both `hashCode` and `equals`, so the two methods must be consistent.

## 4. Connection to the `equals` and `hashCode` Contract

A proper `equals` method must satisfy **reflexivity** (`x.equals(x)` is `true`), **symmetry**, **transitivity**, **consistency** when state does not change, and `x.equals(null)` being `false`.

The required relationship with `hashCode` is:

> If `a.equals(b)` is `true`, then `a.hashCode() == b.hashCode()` must be `true`.

The converse is **not required**, because two different objects can share the same hash code. In the example, `equals` uses `email`, `displayName`, and `priority`, so `hashCode` is also computed from these fields using `Objects.hash(email, displayName, priority)`.

`Objects.hash` accepts `null` references, takes multiple arguments via varargs, and returns a combined hash integer. Do not confuse it with `Objects.hashCode(x)`: the `hashCode(x)` method returns `0` for `null`, and when `x != null` returns `x.hashCode()`; `Objects.hash(x)` uses a composite hashing algorithm and does not necessarily equal `Objects.hashCode(x)` even with only one argument.

Using `Objects.hash` is convenient for ordinary value objects; if `hashCode` is called at very high frequency, varargs and boxing can incur overhead, in which case you should only optimize after measuring performance. **Contract correctness and clarity** come first.

## 5. Choosing How to Compare by Field Type

| Data type | Appropriate comparison | Notes |
| --- | --- | --- |
| `String`, `Integer`, nullable child objects | `Objects.equals(x, that.x)` | Internally still calls `x.equals` when `x` has a value |
| Primitive types `int`, `long`, `boolean`, `char` | `==` | `null` does not exist; avoids unnecessary boxing |
| `float`, `double` | Choose a consistent rule, possibly using `Float.compare`/`Double.compare` | Mind NaN and `-0.0`, stay in sync with hash |
| Enum | `==` (even when one side is `null`) or `Objects.equals` | Each enum constant has a unique identity |
| Arrays `int[]`, `String[]` | `Arrays.equals` | `Objects.equals` on arrays typically compares references, not element by element |
| Nested arrays | `Arrays.deepEquals` | If included in `hashCode`, pair with `Arrays.deepHashCode` |

For example, `Objects.equals(new int[]{1}, new int[]{1})` is `false` because the two arrays are two different objects, whereas `Arrays.equals(new int[]{1}, new int[]{1})` is `true`. Therefore, `Objects.equals` is not a general-purpose deep comparison tool.

For `String`, `Objects.equals("A", "a")` is `false`. If case-insensitivity is needed, you must design a normalization/comparison rule and a **corresponding `hashCode`**; `Objects.equals` does not change `String.equals` behavior.

For a Java `record` class, the compiler automatically generates `equals`/`hashCode` for its components and handles nullable references according to the record's appropriate semantics. However, when you need to write a regular class by hand, `Objects.equals` remains a core pattern to master.

## 6. Common Mistakes

- **Using `field.equals(other.field)` when `field` can be `null`:** throws `NullPointerException`. For a reference field needing `equals`-based comparison, use `Objects.equals(field, other.field)`.
- **Using `field == other.field` for `String` or value objects:** that is a same-reference comparison. If content-based equality is desired, use `Objects.equals`.
- **Overriding `equals` while keeping `Object.hashCode`:** can cause `HashSet`/`HashMap` to mishandle objects that are equal. Override both.
- **Including in `hashCode` a field that is ignored in `equals`:** risks producing different hashes for two equal objects, violating the contract. A hash field set that is too under-discriminating may still be valid but causes many collisions; design the fields consistently.
- **Mutating a field participating in `equals`/`hashCode` after placing the object as a `HashMap` key:** the key may no longer be found on lookup. Prefer immutable value objects.
- **Assuming every two `null` values must be equal in the business domain:** `Objects.equals(null, null)` is always `true`, but the domain may require a different criterion (for example, an ID must not be absent); validate or normalize data when constructing the object.
- **Forgetting the inheritance strategy:** a subclass adding compared fields can break symmetry with the superclass. The example uses a `final class` to clearly define the comparison scope; for extensible hierarchies, design separately.
- **Assuming `Objects.equals` fixes a broken `equals` in a nested object:** it only delegates the comparison to `a.equals(b)` after handling `null`.

## 7. Self-Assessment Checklist

Before finalizing an `equals` with nullable fields, test these scenarios: (1) both fields `null`; (2) left `null`, right has a value; (3) left has a value, right `null`; (4) two child objects with different references but equal by `equals`; (5) two child objects differing in value. Next, verify `x.equals(null)` is `false`, `a.equals(b) == b.equals(a)`, and equal object pairs have the same `hashCode`.

**Key takeaway:** once `other`'s type has been verified, use **`Objects.equals(this.field, that.field)`** for nullable reference fields, use `==` for most primitive types, and implement `hashCode` consistently with the fields that determine `equals`. `Objects.equals` makes the comparison `null`-safe; the equality rule for the whole object is still defined by the class.