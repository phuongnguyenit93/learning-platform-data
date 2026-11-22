# Using a New Yet Equal Object to Look Up a Key in HashMap

## 1. A New Key Can Find a Stored Mapping

When storing data in a `HashMap<K, V>`, you do not necessarily have to keep the exact key instance passed into `put()`. You can create a new object with the same **business key value** to call `get()` or `containsKey()`.

For example: an account is identified by the pair `(tenantId, userId)`. A map stores user names keyed by `AccountKey("team-a", "u-42")`. Later, another request creates a **new instance** with the same two fields and retrieves the old value. This works if `AccountKey` accurately defines when two instances are considered equal, while also providing a `hashCode()` consistent with `equals()`.

Distinguish right from the start:

- `first == second` checks whether two variables point to **the same instance**. Two separate `new` calls normally return `false`.
- `first.equals(second)` checks logical equality defined by the object's type. Two distinct instances can return `true`.
- `first.hashCode() == second.hashCode()` is **mandatory** if `first.equals(second)` is true, though matching hashes alone do not prove two objects are equal.

The default `Object.equals()` compares reference identity. Therefore, creating a custom key class and simply keeping the same fields **is not enough** to look up with a new instance. `String` and other value types already define an appropriate contract; a custom key class must be deliberately designed.

## 2. How HashMap Uses Hashing and Equality

You can picture adding and retrieving elements through the following conceptual flow:

```text
put(keyA, value)
    │
    ├─ compute keyA.hashCode()
    ├─ determine the appropriate bucket
    ├─ compare with candidate keys using equals() when needed
    └─ add mapping or update equivalent mapping

get(keyB)    // keyB is a new object
    │
    ├─ compute keyB.hashCode()
    ├─ locate corresponding storage region
    ├─ check equivalent key using equals()
    └─ return value or null if no mapping exists
```

With Java `HashMap`, a lookup key can find a mapping stored under another key if they are equivalent according to `equals()` and have compatible hash values. Internal details such as hash bit mixing, bucket selection, list/tree structure, and resizing depend on the JDK implementation; you should not build application logic on bucket indices or `HashMap` iteration order.

**Two rules must go together:**

1. **Equality implies same hash.** If `a.equals(b)` returns `true`, `a.hashCode()` and `b.hashCode()` must be identical. If violated, `HashMap` may search the wrong region and miss the key.
2. **Same hash does not guarantee equality.** Hash collisions legitimately occur: unequal objects can share the same hash. `HashMap` needs to use equality checks to distinguish them.

When calling `put()` with a new key **equivalent** to an existing key, the map updates the existing value rather than increasing the entry count. The two references do not need to satisfy `==`.

## 3. Key Design: Choosing the Right Equality Fields

There is no "compare all fields" rule applicable to every class. For an account key across multiple tenants, a `userId` may repeat across tenants, so `(tenantId, userId)` forms a composite key. Omitting `tenantId` would cause two accounts from two different tenants to be treated as one. Conversely, if `displayName` were added to equality, changing a name could turn the same account into a different key.

A good set of key fields should have:

- **Clear business meaning:** two objects with those same fields genuinely represent the same key.
- **Proper uniqueness scope:** if the ID is only unique within a tenant, tenant must be included; if the ID is already globally unique, an extra namespace may not be needed.
- **Stability:** data participating in `equals()/hashCode()` should not change while the object remains a key in `HashMap`.
- **Consistent comparison:** component types have suitable equality policies; for example, `String.equals()` is case-sensitive and `BigDecimal.equals()` considers scale.

The `equals()` contract includes: reflexivity (`x.equals(x)`), symmetry (`x.equals(y)` equivalent to `y.equals(x)`), transitivity, consistency when relevant data does not change, and `x.equals(null) == false`. Two keys considered equal must have the same `hashCode()`. Do not use continuously changing timestamps, random values, or reference addresses in the hash if equality is based on value fields.

## 4. Complete Java 17+ Program

Place the following code in `HashMapEqualKeysDemo.java`. We write `equals()` and `hashCode()` manually to see the contract clearly:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class HashMapEqualKeysDemo {

    static final class AccountKey {
        private final String tenantId;
        private final String userId;

        AccountKey(String tenantId, String userId) {
            this.tenantId = Objects.requireNonNull(tenantId);
            this.userId = Objects.requireNonNull(userId);
            if (tenantId.isBlank() || userId.isBlank()) {
                throw new IllegalArgumentException("IDs must not be blank");
            }
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof AccountKey that)) return false;
            return tenantId.equals(that.tenantId)
                    && userId.equals(that.userId);
        }

        @Override
        public int hashCode() {
            return Objects.hash(tenantId, userId);
        }
    }

    public static void main(String[] args) {
        Map<AccountKey, String> accounts = new HashMap<>();

        AccountKey inserted = new AccountKey("team-a", "u-42");
        accounts.put(inserted, "Profile page");

        AccountKey lookup = new AccountKey("team-a", "u-42");
        AccountKey otherTenant = new AccountKey("team-b", "u-42");

        System.out.println(inserted == lookup);
        System.out.println(inserted.equals(lookup));
        System.out.println(inserted.hashCode() == lookup.hashCode());
        System.out.println(accounts.containsKey(lookup));
        System.out.println(accounts.get(lookup));
        System.out.println(accounts.containsKey(otherTenant));
        System.out.println(accounts.get(otherTenant));

        accounts.put(lookup, "Updated");
        System.out.println(accounts.size());
        System.out.println(accounts.get(inserted));

        AccountKey nullValueKey = new AccountKey("team-b", "u-01");
        accounts.put(nullValueKey, null);
        System.out.println(accounts.containsKey(
                new AccountKey("team-b", "u-01")));
        System.out.println(accounts.get(nullValueKey));
        System.out.println(accounts.getOrDefault(
                new AccountKey("team-c", "u-99"), "Not found"));
    }
}
```

Compile/run using JDK 17 or higher:

```bash
javac HashMapEqualKeysDemo.java
java HashMapEqualKeysDemo
```

Output:

```text
false
true
true
true
Profile page
false
null
1
Updated
true
null
Not found
```

Each group of results carries meaning:

1. `inserted == lookup` is `false` because two instantiations create two instances. However, `inserted.equals(lookup)` is `true` because the two key fields match; their hashes are also equal.
2. `accounts.containsKey(lookup)` is `true` and `accounts.get(lookup)` returns `Profile page`, even though the `lookup` instance itself was never passed into `put()`.
3. `otherTenant` carries the same `userId` but a different tenant, so it is not an equivalent key. `containsKey()` yields `false`; `get()` yields `null`.
4. `accounts.put(lookup, "Updated")` updates the old mapping. Because the two keys are equal, `size()` remains `1` and `get(inserted)` returns `Updated`.
5. A mapping can legitimately store a `null` value. `containsKey(new AccountKey("team-b", "u-01"))` yields `true`, while `get(nullValueKey)` returns `null`. This does not mean the key is absent.
6. `getOrDefault()` with the unstored key `("team-c", "u-99")` returns `Not found`. If a mapping exists and stores `null`, `getOrDefault()` returns `null`, without using the default.

In this design, `AccountKey` is `final`, both key fields are `private final String`, the constructor rejects `null` or blank strings, and `String` is immutable. Therefore, once a key is created, there is no valid way to change the values of the two equality components; using it as a `HashMap` key is stable.

## 5. Differences Between get, containsKey, and getOrDefault

| Call | Meaning |
| --- | --- |
| `map.get(key)` | Retrieves the value of the equivalent key, or `null` if no mapping exists; also `null` if the stored value is `null`. |
| `map.containsKey(key)` | Confirms whether a mapping exists for the equivalent key, even when the stored map value is `null`. |
| `map.getOrDefault(key, fallback)` | Returns fallback if **no mapping exists**. A mapping to `null` still returns `null`. |
| `map.put(key, value)` | Adds a new mapping or replaces the value of a mapping with an equivalent key; returns the old value or `null`. |
| `map.remove(key)` | Removes the mapping identified via the equivalent key; the return value may be `null`. |

`HashMap` supports one `null` key and `null` values. When you need to distinguish whether a mapping exists or not, you must not rely solely on `get(key) != null`. This semantics differs from `ConcurrentHashMap`, which does not allow `null` keys or values.

Beyond `HashMap`, other `Map` implementations can choose different key-equivalence criteria: `IdentityHashMap` intentionally compares by reference identity, and `TreeMap` relies on comparison ordering via `Comparable`/`Comparator`. Thus, the "create a new yet equal key" technique in this lesson is tied to **HashMap and the equals/hashCode contract**, and does not automatically generalize to every map.

## 6. Mistake: Overriding Only One of the Two Methods

### Overriding only equals()

If two objects have the same `tenantId` and `userId` yet `hashCode()` remains the default identity-based computation, they can have different hashes. Looking up with a new object becomes unreliable because the hash may lead to a different region. Contract-violating example:

```java
// Just a method example inside a class with two fields:
@Override
public boolean equals(Object other) {
    return other instanceof AccountKey that
            && tenantId.equals(that.tenantId)
            && userId.equals(that.userId);
}
// Forgot to override hashCode(): WRONG, because two equal instances can have different hashes.
```

The comment above assumes the class is using `Object.hashCode()`. If `AccountKey` already had a compatible hash calculation, the `equals` method would not cause this issue; the bug lies in lacking a synchronized contract.

### Overriding only hashCode()

If `hashCode()` returns the same value for every instance while `equals()` remains the default `Object.equals()`, two distinct objects still will not be treated as the same key. The hash only narrows down candidates, whereas `equals()` decides whether they are equivalent.

### Hash collision is not an equality bug

You must not use `a.hashCode() == b.hashCode()` to assert `a.equals(b)`. A 32-bit hash cannot distinguish every object that can be created; collisions are normal. Even if two keys have the same hash, `HashMap` can still store both if they are not equal. Nor should you try to create an "absolutely unique" hash because the Java contract does not promise that.

## 7. Mistake: Mutating State That Determines the Key After put

This is a real-world trap. Suppose `MutableKey.id` participates in computing both `equals()` and `hashCode()`:

```java
// Illustrates flawed logic, not a standalone runnable program.
MutableKey key = new MutableKey("U-100");
map.put(key, "An");

key.setId("U-200"); // Change the value participating in hash/equality.
System.out.println(map.get(key)); // Can be null even though the map still contains the entry.
```

The entry is placed according to the hash at the time of `put()`. If the key field changes, `get(key)` computes the new hash and may search the wrong region. Even when passing back **the exact instance** that was stored, lookup can still fail. `HashMap` does not automatically relocate an entry when an object's fields change.

Solution:

- Prefer immutable keys or a key snapshot frozen at creation time.
- If you need to change a key's identity, remove the old mapping before changing it and add a mapping under the new key, or create a new key instead of mutating the old key.
- For reference fields, `final` only prevents reassigning the variable; a `final List<String>` or `final StringBuilder` can still hold mutable contents affecting equality/hash.
- If a database ID is only assigned after persisting, do not accidentally use an object with a changing ID as a key. Design the equality policy for the entity's entire lifecycle before storing it in a hash collection.

Auxiliary fields such as `displayName` or `lastLogin` can be mutable if they are completely unused in `equals()/hashCode()`. What must be stable is **the part forming the key**, not necessarily every state of the entity.

## 8. Writing Keys More Concisely With record (Java 17)

If a key has just two value components, `record` helps auto-generate `equals()` and `hashCode()`:

```java
record AccountKey(String tenantId, String userId) {
    AccountKey {
        java.util.Objects.requireNonNull(tenantId);
        java.util.Objects.requireNonNull(userId);
        if (tenantId.isBlank() || userId.isBlank()) {
            throw new IllegalArgumentException("IDs must not be blank");
        }
    }
}
```

*This is an alternative declaration; do not merge it into the program in section 4 because the name `AccountKey` would conflict.* Java generates equality based on **all** record components. Consequently, two separate `new AccountKey("team-a", "u-42")` objects have compatible equality/hash for use with `HashMap`.

A record **does not automatically deep-copy** components that are arrays, lists, or mutable objects. In particular, a record containing an array uses the array's default equality semantics for that component; if you want to compare array contents and hash by content, you must design it separately. A record with a component carrying state that should not affect identity will include that component in default equality, so choose components suited to the domain.

## 9. Component Data and Key Normalization

Some situations cause two objects to look "the same" to a user yet differ under `equals()`:

| Component | Policy to determine |
| --- | --- |
| `String` | `"U-42"` and `"u-42"` are two different strings under `equals()`; normalize case only if the domain allows it. |
| `BigDecimal` | `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` is `false` due to differing scale, even though `compareTo() == 0`. If the same numeric value is needed, normalize consistently before creating the key. |
| Array | Default equality on references does not compare element-by-element. If using contents as a key, `Arrays.equals()/hashCode()` or `deepEquals()/deepHashCode()` compatible with the data type is needed. |
| `List` | `List.equals()` considers elements **in order**; mutability must be controlled while the key resides in the map. |
| `Set` | `Set.equals()` considers the set of elements regardless of order; elements changing equality/hash can also break logic. |

Data normalization policies (for instance, whether codes need leading/trailing whitespace trimmed) must be decided **before** constructing keys and applied uniformly to both `equals()` and `hashCode()`. Do not silently call `toLowerCase()` on every code, username, or email without knowing whether the domain is case-sensitive.

`toString()` is not a proper way to construct a key. Two identical display strings do not guarantee two objects are equal, and `toString()` can change solely for debugging purposes.

## 10. Checklist and Self-Check

Before using a custom class as a `HashMap` key, you can check:

| Test scenario | Required outcome |
| --- | --- |
| Create two independent objects with the same key value | `a != b` by reference; `a.equals(b)` is `true` and hashes are equal. |
| `put(a, v)` then `get(b)` | Receives `v` accurately and `containsKey(b)` is `true`. |
| `put(b, newValue)` when `a.equals(b)` | Only updates the mapping, `size()` does not increase. |
| Keys with different tenants despite same userId | Does not accidentally retrieve data across tenants. |
| Two different keys with the same hash | Still distinguished via `equals()`. |
| Modify a field not belonging to equality | Lookup does not change. |
| Modify a field belonging to equality while key is in the map | This is a dangerous design and must be avoided. |
| Mapping storing a `null` value | `containsKey()` distinguishes it from the absent-mapping case. |

**Question 1:** Why can `new String("java")` find a mapping stored by another `String` instance with content `"java"`?  
**Answer:** Because `String.equals()` compares content and `String.hashCode()` is consistent with equality.

**Question 2:** Are two objects with the same `hashCode()` guaranteed to return the same value on `map.get()`?  
**Answer:** No; two keys can collide while `equals()` is still `false`.

**Question 3:** When `put()` is called with a new key instance equal to an existing key, does the entry count increase?  
**Answer:** No; the value associated with the equivalent key is replaced.

**Question 4:** Does `map.get(key) == null` guarantee that no mapping exists?  
**Answer:** Not for `HashMap`: a mapping can exist and hold a `null` value. Use `containsKey()`.

**Question 5:** Why should you not modify the `id` of an object currently inside a `HashMap` if `id` participates in equality/hash?  
**Answer:** Because the hash used during lookup can differ from the hash at storage time, causing the map to fail to find the existing entry.

**Question 6:** Does changing `tenantId` make the same `userId` become the same key?  
**Answer:** Not in this lesson's model; tenant is part of the key to prevent accidental cross-namespace lookup.

Directly actionable conclusion: **A new key instance can look up a mapping in `HashMap` if it `equals()` the stored key, has a compatible `hashCode()`, and the data forming the key is kept stable during use.**