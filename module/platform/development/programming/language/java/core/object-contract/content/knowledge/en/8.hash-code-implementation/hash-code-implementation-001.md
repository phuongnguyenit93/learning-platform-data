# Choosing Hash Data Consistent with the `equals()` Relation in Java

## 1. The Problem to Solve

When implementing **equals(Object)** and **hashCode()** yourself, the important question is not "include as many fields in the hash as possible", but rather: **which objects are considered equal according to `equals`, and how do we ensure they always have the same `hashCode`?**

For example, a product has the following fields:

- tenantId: the store that owns the product;
- sku: the product code, case-insensitive by convention;
- displayName: the name displayed on the UI;
- lastViewedAt: the most recent time a user opened the product page.

If the `equals` relation identifies the same product by the pair **(tenantId, normalized sku)**, `hashCode` must also produce the same result for every equivalent pair of these values. `displayName` or `lastViewedAt` must not cause two products with the same identity to have different hash codes.

Conversely, if `equals` actually compares `displayName` as well, `hashCode` cannot arbitrarily rely on a different equality relation. You must finalize the **equality definition first**, and then choose the appropriate hash data.

## 2. The `equals`–`hashCode` Contract: Two Non-Negotiable Principles

The Java `Object.hashCode()` contract requires:

1. **If `x.equals(y)` is `true`, then `x.hashCode()` must equal `y.hashCode()`.**
2. When no information used in `equals` changes, multiple invocations of `hashCode` on the same object during a single execution of a Java application must return the same integer.

What is **not** required:

- Two objects that are unequal according to `equals` must have different hash codes. **Hash collisions are allowed.**
- `hashCode` must remain identical across different executions of the program; Java does not guarantee every implementation is stable across runs.
- `hashCode` must be a unique identifier, a memory address, or a non-negative number.

You can think of the equality relation as partitioning objects into *equivalence classes*. Each class must receive **one** stable hash value under the conditions above; multiple distinct classes may still share the same hash value.

| Relation between `x` and `y` | Requirement for `hashCode` | Notes |
| --- | --- | --- |
| `x.equals(y) == true` | `hashCode` **must be equal** | Contract condition |
| `x.equals(y) == false` | `hashCode` may be equal or different | Do not infer equality from hash |
| State participating in `equals` stays unchanged | `hashCode` must be stable within a run | Do not use random/time values for hashing |
| State participating in `equals` is modified | Hash may change | Prone to bugs when currently used as a hash key |

It is important to distinguish: **"Data participating in `equals`" means the data that determines the logical equality relation**, not simply "every field of the object".

## 3. Process for Choosing Data to Hash

### Step 1: Define the Equality Criteria

Answer this first: when do two objects represent the same value—which attributes must match? For example:

~~~java
return tenantId.equals(other.tenantId)
        && normalizedSku.equals(other.normalizedSku);
~~~

If this is what determines equality, two objects with the same `tenantId` and `normalizedSku` must have equal hashes.

### Step 2: Examine How `equals` Compares Each Field

The same data field can be compared under different rules:

- Case-sensitive `String` comparison: the hash can be based on that `String` itself.
- Case-insensitive SKU comparison: the hash must use the same normalized form or a hashing approach compatible with case-insensitive equality.
- Array content comparison: use **Arrays.equals** in `equals` and the corresponding **Arrays.hashCode** in `hashCode`.
- Deep comparison of nested arrays: use **Arrays.deepEquals** together with **Arrays.deepHashCode**.
- Comparison of multiple nullable fields: use **Objects.equals** when comparing and `Objects.hash`/`Objects.hashCode` appropriately when hashing.

**Key rule:** the same *equality* semantics require the hash data to produce the same result. You do not necessarily have to call the exact same method in both places, but value normalization and handling must be compatible.

### Step 3: Exclude Fields That Do Not Define Equality

Do not add fields used for display, logging, counters, UI state, caches, access timestamps, or other data that `equals` ignores.

For example, if `equals` only uses `tenantId` and normalized SKU:

~~~java
// Wrong when equals does not consider displayName:
return Objects.hash(tenantId, normalizedSku, displayName);

// Right for the defined equals criteria:
return Objects.hash(tenantId, normalizedSku);
~~~

These are illustrative method-body snippets, not standalone programs. The first expression can cause two objects where `equals` returns `true` to have different `hashCode` values solely because `displayName` differs.

### Step 4: Choose a Valid, Well-Distributed Hashing Formula

For **correctness**, using the right set of fields and keeping them stable is the top priority. For **performance**, you should combine the identifying components sensibly to reduce collisions, especially with large `HashMap`/`HashSet` collections.

If `equals` compares both `id` and `version`, having `hashCode` return only `id.hashCode()` may still satisfy the contract because two equal objects always have the same `id`. However, it ignores `version`, so many unequal pairs can end up with the same hash, causing poor distribution. In practice, you should usually combine both `id` and `version`.

In other words, **`hashCode` is not required to use every field in `equals`**, but it must never distinguish two objects that `equals` considers equal. Using all the identifying attributes is usually the clearer choice and yields better distribution.

### Step 5: Keep Hash Data Stable While the Object Is in a Hash-Based Collection

When an object is used as a `HashMap` key or a `HashSet` element, avoid modifying the data that determines equality/hash while it resides in the collection. If that value changes, the collection may fail to find the key again because its initial storage bucket is tied to the old hash.

Prefer immutable keys: `final` fields with immutable types or defensive copies of mutable data.

## 4. Complete Java 17+ Example: Same `equals` Relation Yields Same Hash

Rule for `ProductKey`: **the same `tenantId` and case-insensitive `sku`** identify the same key. The display name does not participate in equality. The example uses ASCII SKUs, normalized via `Locale.ROOT`.

Create the file **HashCodeFieldSelectionDemo.java**:

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class HashCodeFieldSelectionDemo {
    public static void main(String[] args) {
        ProductKey a = new ProductKey("shop-1", "ax-7", "Blue hat");
        ProductKey b = new ProductKey("shop-1", "AX-7", "Red hat");
        ProductKey c = new ProductKey("shop-2", "ax-7", "Blue hat");

        System.out.println("a equals b: " + a.equals(b));
        System.out.println("a hash equals b hash: "
                + (a.hashCode() == b.hashCode()));
        System.out.println("a equals c: " + a.equals(c));

        Set<ProductKey> set = new HashSet<>();
        set.add(a);
        set.add(b);
        set.add(c);
        System.out.println("HashSet size: " + set.size());

        Map<ProductKey, String> map = new HashMap<>();
        map.put(a, "Saved");
        ProductKey lookup = new ProductKey(
                "shop-1", "aX-7", "Different display name");
        System.out.println("HashMap lookup: " + map.get(lookup));

        System.out.println("Aa hash equals BB hash: "
                + ("Aa".hashCode() == "BB".hashCode()));
        System.out.println("Aa equals BB: " + "Aa".equals("BB"));
    }

    static final class ProductKey {
        private final String tenantId;
        private final String normalizedSku;
        private final String displayName;

        ProductKey(String tenantId, String sku, String displayName) {
            this.tenantId = Objects.requireNonNull(tenantId);
            this.normalizedSku = Objects.requireNonNull(sku)
                    .toUpperCase(Locale.ROOT);
            this.displayName = Objects.requireNonNull(displayName);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof ProductKey other)) {
                return false;
            }
            return tenantId.equals(other.tenantId)
                    && normalizedSku.equals(other.normalizedSku);
        }

        @Override
        public int hashCode() {
            return Objects.hash(tenantId, normalizedSku);
        }

        @Override
        public String toString() {
            return "ProductKey{" + tenantId + ", "
                    + normalizedSku + ", " + displayName + "}";
        }
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac -encoding UTF-8 HashCodeFieldSelectionDemo.java
java HashCodeFieldSelectionDemo
~~~

Expected output:

~~~text
a equals b: true
a hash equals b hash: true
a equals c: false
HashSet size: 2
HashMap lookup: Saved
Aa hash equals BB hash: true
Aa equals BB: false
~~~

**Why does it produce this output?**

1. `a` and `b` share the same `tenantId` (`shop-1`); both SKUs `ax-7` and `AX-7` normalize to `AX-7`. Therefore, `equals` returns `true` and `hashCode` must be the same. Different display names have no effect.
2. `c` belongs to `shop-2`, so it has a different identity from `a`. Since `a` and `c` are not equal, their hashes are not required to differ.
3. `HashSet` holds two logical values: one for `shop-1`/`AX-7` and one for `shop-2`/`AX-7`. Adding `b` does not increase the size because `b` equals `a`.
4. `HashMap` lookup with a new key object still finds the stored value, even with a differently cased SKU string and a different display name.
5. The two `String` values `"Aa"` and `"BB"` have the same `String.hashCode` (`2112`) but are not equal. This is a valid collision: equal hashes **do not mean** `equals` is `true`.

**Why choose `normalizedSku` instead of the raw `sku`?** If `equals` compares case-insensitively while `hashCode` calls `hashCode` on the raw string, two values like `ax-7` and `AX-7` can have different hash codes even though `equals` treats them as equal. Normalizing once in the constructor both guarantees that `hash` and `equals` use the same value and avoids re-running the logic on every call.

**Why are `ProductKey` and its fields `final`?** To demonstrate a key with stable identity state. `String` is immutable; `final` fields cannot be reassigned after construction. However, for field types like `List` or arrays, marking only the reference `final` **does not prevent modifying the inner elements**.

## 5. Right and Wrong Implementation Pairs to Distinguish

### 5.1. `equals` ignores a field, but `hashCode` includes it

Suppose `equals` only compares `id`:

~~~java
@Override
public boolean equals(Object obj) {
    return obj instanceof Item other && id.equals(other.id);
}

// Wrong for the equals above if label can differ between Items with the same id.
@Override
public int hashCode() {
    return Objects.hash(id, label);
}
~~~

Two `Item` instances with the same `id` but different `label` values will be equal according to `equals`, while their hash codes may differ. The snippets above only illustrate methods inside a class with fields `id` and `label`; they are not a complete standalone class.

Fix:

~~~java
@Override
public int hashCode() {
    return Objects.hashCode(id);
}
~~~

If `id` is guaranteed non-null, you can use `id.hashCode()`. If `id` is allowed to be `null`, you must ensure `equals` handles `null` accordingly, for example `Objects.equals(id, other.id)`.

### 5.2. `equals` compares two fields, `hashCode` uses only one

~~~java
// In a class where equals compares id and version:
@Override
public int hashCode() {
    return Objects.hashCode(id);
}
~~~

This approach **can still satisfy the contract**: whenever both `id` and `version` match, `id` obviously matches as well. However, two different versions of the same `id` share the same hash, increasing collisions.

A better-distributed design:

~~~java
@Override
public int hashCode() {
    return Objects.hash(id, version);
}
~~~

The primary focus is **compatibility with `equals`**, and only then distribution quality. Do not misinterpret the rule as saying that omitting any field of `equals` from the hash formula automatically violates the contract.

### 5.3. `equals` ignores letter case, but `hashCode` uses the raw string

~~~java
// equals compares name using equalsIgnoreCase,
// but hashCode below hashes the raw name:
@Override
public int hashCode() {
    return Objects.hashCode(name); // Can violate the contract!
}
~~~

If `"ONE"` and `"one"` are equal under the class's `equals` rule, their raw hash codes differ. The fix is to **unify the value rule**. For case-insensitive ASCII codes, you can normalize with `toUpperCase(Locale.ROOT)` when constructing the object and use the normalized value in **both `equals` and `hashCode`**.

For Unicode text, locales, or complex comparison rules, never assume that a simple single-step case conversion is always equivalent to every comparison method. You must define normalization/collation and hashing consistently over the exact same relation.

### 5.4. `equals` uses array contents, but `hashCode` uses array identity

~~~java
// If tags is String[] and two arrays are considered equal by content:
return Arrays.equals(this.tags, other.tags); // In equals

// Correct content-based hash:
return Arrays.hashCode(tags);                 // In hashCode
~~~

These snippets illustrate two implementation fragments in a context where `tags` and `other` are already declared; `import java.util.Arrays` is required.

Do not use `Objects.hashCode(tags)` in this case: for a standard array, it invokes the array object's default `hashCode`, which is based on reference identity, whereas `Arrays.equals` compares elements.

For nested arrays, use the `Arrays.deepEquals` / `Arrays.deepHashCode` pair when deep comparison is intended. For a `List` whose `equals` is element-based, `List.hashCode` is also defined consistently over those elements; `Objects.hashCode(list)` can be used if that is the field under consideration. Note that mutable elements can still cause the hash to change.

### 5.5. `equals` has special numeric semantics

For example, `BigDecimal.equals` distinguishes both value **and scale**: `new BigDecimal("1.0")` does not `equals` `new BigDecimal("1.00")`, even though `compareTo` returns `0`.

If a custom class defines `equals` based on `BigDecimal.compareTo(...) == 0`, `hashCode` must not directly use `amount.hashCode()` because two `BigDecimal` values with different scales can produce different hashes. You can design a normalized form using `stripTrailingZeros()` and use that normalized form in both comparison and hashing. When doing so, clearly define how `null`, zero, and other fields are handled. Do not alter default `BigDecimal.equals` semantics without a specific business requirement.

Similarly for floating-point numbers, keep the handling of `NaN` and `+0.0`/`-0.0` consistent if the class defines custom `equals`. Prefer the `Double.compare`/`Double.hashCode` or `Float.compare`/`Float.hashCode` pairs when their exact distinctions match the relation you want to design.

## 6. Should You Use `Objects.hash`, `Objects.hashCode`, or a Manual Formula?

### `Objects.hash(...)`

Suitable for **multiple fields**:

~~~java
@Override
public int hashCode() {
    return Objects.hash(tenantId, normalizedSku);
}
~~~

Its advantages are brevity, `null` handling, and consistency with component hashes. It uses varargs and hashes over the array elements, so in performance-critical code you should measure rather than assuming it is the fastest option.

### `Objects.hashCode(value)`

Suitable for **a single nullable value**:

~~~java
@Override
public int hashCode() {
    return Objects.hashCode(id);
}
~~~

If `id` is `null`, the result is `0`; otherwise, the result is `id.hashCode()`. `Objects.hash(id)` is **not completely equivalent** to `Objects.hashCode(id)`, so use each formula deliberately and consistently with `equals`. Do not mix the two arbitrarily in tests that compare exact hash numbers.

### Manual Combination

For multiple fields, you can apply sequential accumulation, for example:

~~~java
@Override
public int hashCode() {
    int result = Objects.hashCode(tenantId);
    result = 31 * result + Objects.hashCode(normalizedSku);
    return result;
}
~~~

This illustrates a class with the two fields mentioned above. `int` multiplication/addition may overflow, which is deterministic Java integer behavior and does not make the hash formula violate the contract. A formula does not need to generate unique codes; what matters is that data equal under `equals` yields equal hash results.

**Never use** a random value, system time, or an auto-incrementing counter on each `hashCode` call for an object whose comparison state has not changed. Also do not use `System.identityHashCode(this)` to hash a class with value-based `equals`: two distinct but equal objects can receive different identity hashes.

## 7. Mutable Key Design and Caching `hashCode`

If a field used in `equals` is modified while the object is inside a `HashMap` or `HashSet`, its `hashCode` may change as well, causing key lookups or removals to behave unexpectedly.

Example of a dangerous workflow:

~~~java
// Logic illustration, not a standalone program:
set.add(key);
key.setId("new-id"); // id is used by equals and hashCode
set.contains(key);    // Cannot rely on the lookup result as before
~~~

You cannot simply "freeze" `hashCode` in a cache and keep letting `id` change: after the state changes, objects with the same new `id` under `equals` could carry different hashes if an old result was cached. That again violates the contract.

Practical ways to handle this:

1. Choose immutable identifying fields whenever possible. For keys containing arrays or `List`s, consider defensive copying and avoid exposing mutable structures.
2. If an object is already in a `HashSet`/`HashMap`, avoid mutating the fields that determine equality; if changing the identity is unavoidable, remove it under the old state before mutating and re-add it under the new state.
3. Cache `hashCode` only when all data affecting the hash value remains immutable throughout the relevant lifetime of the object. Caching is no substitute for the `equals`–`hashCode` contract.

Also consider concurrent access: mutable state requires proper synchronization or immutable design; a theoretically sound `hashCode` formula does not by itself provide thread safety.

## 8. Testing to Verify Proper Hash Field Selection

Do not test `hashCode` just once. Create **multiple distinct object instances** that are equal across every possible scenario: vary letter case if equality is case-insensitive; change ignored display fields; test valid `null` values; test arrays with identical content; test subclasses if an inheritance hierarchy exists.

For two objects `a` and `b` with the same logical identity:

~~~java
if (!a.equals(b)) {
    throw new AssertionError("Test inputs are not equal according to equals");
}
if (a.hashCode() != b.hashCode()) {
    throw new AssertionError("Violation of equals/hashCode contract");
}
~~~

This snippet runs in a context that has `a` and `b`; it is not a standalone program. Then verify the actual behavior of `HashSet.contains` or `HashMap.get` using a **new but equal** object.

Cases worth covering:

| Case | What to verify |
| --- | --- |
| Same identifying fields, different `displayName` | `equals` is `true`, hashes are equal |
| Same `tenantId`, SKU with different casing per rule | `equals` is `true`, hashes are equal |
| Different `tenantId`, same SKU | `equals` is `false`; hashes may collide |
| Different SKU and same `tenantId` | `equals` is `false`; hashes may collide |
| Two `String`s `"Aa"` and `"BB"` | Hash collision is valid, `equals` is `false` |
| Supported `null` values | No NPE thrown; `equals`/`hash` consistent |
| Comparison data unchanged, multiple `hash` calls | Hash code is stable |
| Create new key equal to a key stored in `Map` | Retrieves the corresponding value |

**Do not write tests requiring that `x` different from `y` must have different `hashCode` values.** That is not part of Java's contract and will falsely reject valid implementations that happen to have collisions.

In addition, the `equals` contract includes reflexivity, symmetry, transitivity, consistency, and `null` handling. Choosing the right fields in `hashCode` does not replace testing those properties. If inheritance is used and a subclass adds a field to `equals`, both the equality definition and the set of hash fields must be designed so they do not break symmetry or transitivity.

## 9. `hashCode` Review Checklist

- **Start from `equals`:** exactly which values and rules determine whether two objects are equal?
- **Use an equivalent representation:** if `equals` normalizes values, compares by content, or follows special numeric rules, the hash must reflect that same relation.
- **Do not add non-equality data** that could cause two equal objects to have different hashes.
- **Prefer using all identifying data** for reasonable distribution, while remembering that omitting a field does not automatically break the contract.
- **Pick the type-appropriate API:** `Objects.hash` for multiple fields, `Objects.hashCode` for a single nullable field, `Arrays.hashCode` for 1D arrays, `Arrays.deepHashCode` for nested arrays if `equals` compares deeply.
- **Ensure stability:** avoid random values, timestamps, identity hash for value-based equality, or mutable state in stored keys.
- **Test with equal-value, distinct-reference examples:** `equals == true` must imply equal hashes; `false` does not require different hashes.

**Remember:** choosing the right hash data means choosing a function that *never distinguishes two objects that `equals` considers equal*. Compatibility with `equals` is mandatory; distribution quality, speed, and implementation details are the secondary goals to optimize.