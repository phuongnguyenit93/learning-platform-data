# `null` Fields and `Objects.hashCode()` in Java

## 1. The Problem When a Field Participating in `hashCode()` Can Be `null`

An object may contain a reference field that has not been assigned a value, such as `customerId` or `region`. If this field is part of the object's logical identity, `equals()` and `hashCode()` must handle it **consistently**, even when its value is `null`.

Calling a method directly on a null reference:

```java
String region = null;
int hash = region.hashCode(); // NullPointerException
```

The code above is an **error-illustration fragment**, not a safely runnable program. The error occurs because `region` does not point to an object on which to invoke the method. You could write `region == null ? 0 : region.hashCode()`, but Java already provides a dedicated utility for this operation: **`java.util.Objects.hashCode(Object)`**.

## 2. How Does `Objects.hashCode(Object)` Work?

The static method:

```java
int hash = java.util.Objects.hashCode(value);
```

returns:

- **`0`** if `value == null`;
- **`value.hashCode()`** if `value != null`.

You can think of the rule via this equivalent expression:

```java
static int nullSafeHash(Object value) {
    return value == null ? 0 : value.hashCode();
}
```

This is an illustrative method declaration; it contains only one method and is not a complete Java file with `main`. `Objects.hashCode(value)` guards the **hash call when the value is null**. It does not compute an "optimal hash code" on its own, nor does it check or fix the contract of the class providing `value`.

Examples:

| Value of `value` | `Objects.hashCode(value)` |
| --- | --- |
| `null` | `0` |
| `"A1"` | `2064`, equal to `"A1".hashCode()` |
| `Integer.valueOf(7)` | `7`, equal to `Integer.hashCode()` |
| Another non-`null` object | The result of `value.hashCode()` itself |

For the string `"A1"`, `String.hashCode()` uses the polynomial formula: `31 * 'A' + '1' = 31 * 65 + 49 = 2064`.

**Do not interpret `0` as "definitely null".** A non-null object is still allowed to have hash code `0`; unequal objects may also share the same hash. A hash is only a value for partitioning/lookup, not absolute proof of equality.

## 3. Runnable Java 17+ Example

In the following example, `CustomerKey` represents a logical key made up of two fields `tenant` and `externalId`; either may be `null`. We use `Objects.equals()` for comparison and `Objects.hashCode()` for hashing each field. Both methods follow the same set of fields, preventing cases where `equals()` says two keys match while `hashCode()` hashes different data.

Create the file `NullHashCodeDemo.java` with the following complete contents:

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class NullHashCodeDemo {

    static final class CustomerKey {
        private final String tenant;
        private final String externalId;

        CustomerKey(String tenant, String externalId) {
            this.tenant = tenant;
            this.externalId = externalId;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof CustomerKey that)) {
                return false;
            }
            return Objects.equals(tenant, that.tenant)
                    && Objects.equals(externalId, that.externalId);
        }

        @Override
        public int hashCode() {
            int result = 1;
            result = 31 * result + Objects.hashCode(tenant);
            result = 31 * result + Objects.hashCode(externalId);
            return result;
        }
    }

    public static void main(String[] args) {
        System.out.println("Objects.hashCode(null): "
                + Objects.hashCode(null));
        System.out.println("Objects.hashCode(A1): "
                + Objects.hashCode("A1"));
        System.out.println("Objects.hash((Object) null): "
                + Objects.hash((Object) null));
        System.out.println("Objects.hash(A1): "
                + Objects.hash("A1"));

        CustomerKey a = new CustomerKey(null, "A1");
        CustomerKey b = new CustomerKey(null, "A1");
        CustomerKey c = new CustomerKey(null, "B2");
        CustomerKey d = new CustomerKey(null, null);

        System.out.println("a equals b: " + a.equals(b));
        System.out.println("a hash: " + a.hashCode());
        System.out.println("b hash: " + b.hashCode());
        System.out.println("a equals c: " + a.equals(c));
        System.out.println("d hash: " + d.hashCode());
        System.out.println("Objects.hash(null, A1): "
                + Objects.hash(null, "A1"));

        Set<CustomerKey> keys = new HashSet<>();
        keys.add(a);
        System.out.println("set contains b: " + keys.contains(b));
        System.out.println("set contains c: " + keys.contains(c));
    }
}
```

Run from the directory where the file is saved:

```bash
javac NullHashCodeDemo.java
java NullHashCodeDemo
```

Exact expected stdout:

```text
Objects.hashCode(null): 0
Objects.hashCode(A1): 2064
Objects.hash((Object) null): 31
Objects.hash(A1): 2095
a equals b: true
a hash: 3025
b hash: 3025
a equals c: false
d hash: 961
Objects.hash(null, A1): 3025
set contains b: true
set contains c: false
```

Calculation breakdown:

- For `a`, we initialize `result = 1`; the `tenant = null` field gives `31 * 1 + 0 = 31`. Next, `externalId = "A1"` has hash `2064`, so the result is `31 * 31 + 2064 = 3025`.
- For `d`, both fields are `null`: `31 * (31 * 1 + 0) + 0 = 961`. This **does not contradict** `Objects.hashCode(null) = 0`: `d.hashCode()` is the hash **of the entire object**, combined from multiple components, whereas `Objects.hashCode(null)` hashes only **a single null value**.
- `a` and `b` are different instances with the same `tenant` and `externalId`, so `equals()` is true and both hashes equal `3025`.
- `a` and `c` are not equal because `"A1"` differs from `"B2"`. Whether their hashes differ or collide is both valid when objects are unequal.
- `HashSet.contains(b)` returns `true` after adding `a` because the pair is logically equal and shares the same hash. `contains(c)` is `false` because no key equivalent to `c` exists in the set.

The example deliberately uses `final String` fields so logical identity cannot change while the key resides in a collection. `String` is immutable, so `hashCode()` is also stable for the object's lifetime.

## 4. Watch Out: `Objects.hashCode(value)` Differs from `Objects.hash(values...)`

These two methods have similar names but **different** behavior:

| Method | Mechanism | When to use |
| --- | --- | --- |
| `Objects.hashCode(Object value)` | `null` → `0`; otherwise calls `value.hashCode()` | Safely get the hash of **one** nullable value |
| `Objects.hash(Object... values)` | Combines elements via an algorithm equivalent to `Arrays.hashCode(Object[])` | Get the combined hash of **multiple** fields |

Examples:

```java
Objects.hashCode(null);       // 0
Objects.hash((Object) null);  // 31
Objects.hashCode("A1");       // 2064
Objects.hash("A1");           // 2095
Objects.hash(null, "A1");     // 3025
```

The snippet above is an **expression-and-result fragment**, not a standalone program.

Why does `Objects.hash("A1") = 2095`? For a one-element varargs array, the `Arrays.hashCode` algorithm starts with `result = 1` and computes `31 * 1 + 2064 = 2095`. Similarly, a one-element varargs array containing `null` yields `31 * 1 + 0 = 31`.

The call `Objects.hash((Object) null)` intentionally casts to `Object`: it explicitly specifies **a single null element passed into the varargs array**, avoiding confusion with passing a null array argument directly. When working with varargs, `Objects.hash((Object[]) null)` means something different: passing a **null parameter array**, and `Arrays.hashCode` on a null array returns `0`. Do not rely on ambiguous calls to define a hash.

Importantly, you only need to obey **equal objects have equal hashes**. There is no requirement for `hashCode()` to use the exact formula of `Objects.hash()`; the `31 * result + ...` combination in the example and `Objects.hash(tenant, externalId)` are equivalent here because both start at `result = 1` and process the two fields in order.

`Objects.hash(...)` is concise and usually readable for a few fields, but it creates a varargs array (which may incur allocation/resource cost depending on runtime optimizations). In extremely hot code paths, manual combination can be useful after profiling. Do not "optimize" before confirming a need.

## 5. Relationship Between `equals()` and `hashCode()` with `null`

The core `Object` contract states: if `x.equals(y)` returns `true`, then **`x.hashCode() == y.hashCode()` must be true**. The converse does not hold: two colliding hashes do not force two objects to be equal.

For nullable fields, maintain **the same null-handling rule and the same set of fields**:

```java
// The following two snippets belong to the same illustrative class with field 'code':
@Override
public boolean equals(Object obj) {
    return obj instanceof Item that
            && Objects.equals(code, that.code);
}

@Override
public int hashCode() {
    return Objects.hashCode(code);
}
```

This is an **illustrative fragment placed inside a class named `Item` with field `code`**, not a complete program. It is consistent with respect to the `code` field when the class is `final` or when the class-hierarchy equality policy is properly designed. In practice, you still need to consider superclasses/subclasses, other attributes, and immutability.

`Objects.equals(a, b)` works as follows: if both references are `null`, it returns `true`; if only one is `null`, it returns `false`; if both are non-null, it calls `a.equals(b)`. `Objects.hashCode(a)` is not a "two-argument hash version", it simply takes one reference's hash in a null-safe manner.

A direct implementation is also valid:

```java
int codeHash = code == null ? 0 : code.hashCode();
```

However, `Objects.hashCode(code)` is shorter and easier to read, especially when there are multiple nullable fields. Never write `code.hashCode()` before checking for `null`.

### What Happens If a Field Does Not Participate in `equals()`?

If `equals()` relies solely on `id` while `hashCode()` also includes `description`, two objects with the same `id` but different `description` values can have different hashes, **violating the contract**. Conversely, a hash that omits some fields participating in `equals()` can still satisfy the contract, though it causes more collisions. It is best to compute the hash over the same identifying fields as `equals()`, unless there is a proven design reason otherwise.

Both `equals()` and `hashCode()` must stay stable when the relevant information does not change. For objects used as `HashMap` keys or `HashSet` elements, avoid modifying hash-related fields after inserting into the collection; if values change, lookups and removals can fail.

## 6. Pitfalls to Avoid

### Pitfall A — Confusing `Objects.hashCode(null)` with the Hash of the Whole Object

`Objects.hashCode(null)` yields `0`, yet an object with two `null` fields does not necessarily hash to `0`. Combining formulas involve seeds, multipliers, or other typed data that may produce `961`, `31`, or another value. **Only consistency with `equals()` is a mandatory constraint**; there is no fixed number reserved for an object "with null fields".

### Pitfall B — Calling `Objects.hashCode(this)` Inside `hashCode()` Itself

Wrong example:

```java
@Override
public int hashCode() {
    return Objects.hashCode(this); // Wrong: infinite recursion
}
```

Because `this` is non-null, `Objects.hashCode(this)` keeps calling `this.hashCode()` repeatedly until it causes a `StackOverflowError`. Hash **the fields that define identity**, never the object itself from inside that method.

### Pitfall C — Arrays Are Not Hashed by Content If You Only Use `Objects.hashCode(array)`

A standard Java array inherits `Object.equals()/hashCode()`, so two arrays with different references—even with identical elements—are not considered equal and may have different hashes. If equality is defined **by array content**, pick the appropriate algorithm pair:

- One-dimensional arrays: `Arrays.equals(a, b)` and `Arrays.hashCode(a)` (with overloads for primitive and object arrays).
- Multi-level arrays containing arrays: when nested content comparison is needed, use `Arrays.deepEquals(a, b)` and `Arrays.deepHashCode(a)` for appropriate `Object[]` arrays.

If `equals()` compares array content using `Arrays.equals` while `hashCode()` uses `Objects.hashCode(array)`, two objects with differently referenced arrays holding identical content can be equal yet have unequal hashes. That is a contract bug.

### Pitfall D — Using Hashes as Equality Comparison Results

Do not write `return this.hashCode() == other.hashCode();` to implement `equals()`. Two distinct objects can collide on hash, so such a method risks falsely treating them as equal. You must compare the business data that defines identity.

### Pitfall E — Believing `Objects.hashCode` Can Fix a Class with a Broken `hashCode()`

`Objects.hashCode(nonNullValue)` simply delegates to `nonNullValue.hashCode()`. If that class violates the contract with `equals()` or produces unstable results, `Objects.hashCode` cannot fix it. Its sole guarantee here is **not invoking a method on `null`**.

## 7. When Do You Not Need to Write `hashCode()` Manually?

For a value object with a few fields suitable for value-based comparison, a Java `record` can automatically generate `equals()` and `hashCode()`:

```java
record CustomerKeyRecord(String tenant, String externalId) {}
```

This is an **illustrative type declaration** that can be placed in an appropriate Java file. Two records of the same type with matching component values are considered equal, even when one or both components are `null`. This reduces the chance that one method omits a field included by the other.

However, a record **does not automatically make mutable data deeply immutable**. If a component is an array or an object with mutable state, you must review copying, comparison, and hashing policies. Nor does a record replace deciding which fields form the identity for the problem.

## 8. Quick Verification Checklist

1. **Identify which fields participate in identity:** which fields does `equals()` compare, and does `hashCode()` use the corresponding information?
2. **Test `null` on both sides:** two objects both having `null` in a field should be handled safely and per that field's equality rule; one `null` and one non-null must be distinguished.
3. **Use the right API:** `Objects.hashCode(field)` to hash one nullable field; `Objects.hash(field1, field2, ...)` to combine multiple fields. Do not assume both methods return the same result for a single argument.
4. **Verify the contract:** for every pair `x, y` where `x.equals(y)` is true, `x.hashCode() == y.hashCode()` is required. Equal hashes for unequal pairs are allowed.
5. **Avoid mutable state when used as keys:** prefer immutable objects; if array/nested object fields exist, check comparison semantics and content mutability.
6. **Test in collections:** insert a key into a `HashSet`, look it up with another instance holding the same data, and test both `null` and non-null field cases. This is a supplementary check, not a substitute for contract verification.

A small equivalence-pair check can be written as follows (fragment placed in a test where `x` and `y` already exist):

```java
if (x.equals(y) && x.hashCode() != y.hashCode()) {
    throw new AssertionError("equals/hashCode contract violated");
}
```

Test additional `null` and non-null datasets. A finite set of tests cannot prove all cases; review field-selection logic and stability as well.

## 9. Summary

- `Objects.hashCode(value)` returns `0` if `value` is `null`, otherwise `value.hashCode()`. It helps write `hashCode()` without `NullPointerException` for nullable fields.
- `Objects.hash(values...)` combines multiple values using the `Arrays.hashCode(Object[])` algorithm; even when passing a single value, the result **usually does not match** `Objects.hashCode(value)`.
- When overriding `hashCode()`, use the **same logical identity** as `equals()`, always guarantee `x.equals(y) => x.hashCode() == y.hashCode()`, and avoid using mutable data as keys.
- `null` yielding `0` at the **single-value** level does not mean an entire object containing multiple `null` fields must hash to `0`. Hash collisions are valid and distinct from the equality relation.