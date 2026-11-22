# Stability of `hashCode()` Within a Single Execution When Information Used in `equals()` Is Unchanged

## 1. The Exact Rule of the `hashCode()` Contract

In Java, the `Object.hashCode()` method returns an `int` integer used primarily to support hash-table-based data structures, such as `HashMap` and `HashSet`. A core requirement of the contract is:

> During a single execution of a Java application, if no information used in `equals()` comparisons on the object is modified, then every invocation of `hashCode()` on that object must consistently return the same integer.

This can be expressed conditionally:

```text
If the information determining equals(x, ...) does not change during interval T,
then every call to x.hashCode() during interval T must produce the same result.
```

This is **conditional stability**, not a promise that the hash code can never change throughout an object's lifetime.

For example, consider an object representing a customer whose `customerId` determines `equals()`:

- If `customerId` does not change, `hashCode()` must stay the same within the same execution.
- If `customerId` **actually changes**, the consistency contract stated above does not require the old hash value to stay the same; however, mutating a key after inserting it into a hash table can cause lookups to miss it.
- If `displayName` changes while `equals()` does **not** use `displayName`, then changing only the display name is not a valid reason for `hashCode()` to change.

The phrase **“within a single execution”** is crucial: Java's contract does not require `hashCode()` of the same object, or of the same recreated value, to return an identical integer across different JVM startups. Do not store `hashCode()` as a persistent identifier in a database, URL, or file for use in a later run.

## 2. Relationship with `equals()`

Stability is only **one** part of the `hashCode()` contract. The remaining parts relate directly to `equals()`:

1. **Conditional consistency over time:** if the information used for equality comparison does not change, multiple calls to `x.hashCode()` in the same execution must return the same integer.
2. **Equal objects must have the same hash code:** if `x.equals(y)` is `true`, then `x.hashCode() == y.hashCode()` must be `true`.
3. **Unequal objects are allowed to share a hash code:** when `x.equals(y)` is `false`, the two hash codes may differ **or be identical**. Matching hash codes are a *collision*, which does not by itself violate the contract.

For example, a `hashCode()` that always returns `7` is stable and guarantees that equal objects share the same hash code. However, this puts every object under the same hash value, which can make hash tables inefficient. Therefore, we must distinguish **contract compliance** from **hash distribution quality**.

A class that overrides `equals()` by value must override `hashCode()` using information compatible with that equality criterion. Avoid using `System.identityHashCode(this)` when `equals()` defines two objects with *different references* as equal: identity hash codes do not guarantee equality for two objects with the same value.

## 3. What Does a Stable `hashCode()` Depend On?

Consider an `AccountKey` class with `tenantId`, `accountId`, and `description`:

- If `equals()` compares only `tenantId` and `accountId`, these are the pieces of information determining equality.
- A suitable `hashCode()` implementation computes from the **same logical key set**, `tenantId` and `accountId`.
- `description` is used for display and does not participate in `equals()`; changing it must not alter the key's hash code while the equality information remains the same.

“Using the same logical key set” is a practical design principle, not a requirement that the formula inside `hashCode()` call the exact same getters that `equals()` calls. What is mandatory is that **any two objects considered equal by `equals()` have the same hash code**, and that the stability condition in Section 1 is preserved.

The contract does not require hash results to be random, positive, unique, or reflective of memory addresses. Negative `int` values, `0`, or collisions are all valid.

## 4. A Runnable Java 17 Example

The following program illustrates three cases with different properties:

- `StableKey`: immutable equality criteria, stable hash code.
- `BrokenHashKey`: equality data never changes, yet each hash call returns a different number, **violating the contract**.
- `MutableKey`: consistent `equals()`/`hashCode()` formula, but a key field is mutated after being placed into a `HashMap`; this is the hazard of **mutable keys**, and conditional stability is no longer preserved once the key field is modified.

Save as **`HashCodeStabilityDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class HashCodeStabilityDemo {
    static final class StableKey {
        private final String id;

        StableKey(String id) {
            this.id = Objects.requireNonNull(id);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            return other instanceof StableKey that
                    && id.equals(that.id);
        }

        @Override
        public int hashCode() {
            return id.hashCode();
        }
    }

    static final class BrokenHashKey {
        private final String id;
        private int hashCalls;

        BrokenHashKey(String id) {
            this.id = Objects.requireNonNull(id);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            return other instanceof BrokenHashKey that
                    && id.equals(that.id);
        }

        @Override
        public int hashCode() {
            return ++hashCalls; // WRONG: hash code depends on call count.
        }
    }

    static final class MutableKey {
        private String id;

        MutableKey(String id) {
            this.id = Objects.requireNonNull(id);
        }

        void setId(String id) {
            this.id = Objects.requireNonNull(id);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            return other instanceof MutableKey that
                    && id.equals(that.id);
        }

        @Override
        public int hashCode() {
            return id.hashCode();
        }
    }

    public static void main(String[] args) {
        StableKey first = new StableKey("A");
        StableKey second = new StableKey("A");
        System.out.println("stable hash #1: " + first.hashCode());
        System.out.println("stable hash #2: " + first.hashCode());
        System.out.println("equal objects: " + first.equals(second));
        System.out.println("equal hashes: "
                + (first.hashCode() == second.hashCode()));

        BrokenHashKey broken = new BrokenHashKey("A");
        System.out.println("broken hash #1: " + broken.hashCode());
        System.out.println("broken hash #2: " + broken.hashCode());

        Map<BrokenHashKey, String> badMap = new HashMap<>();
        badMap.put(broken, "value");
        System.out.println("broken map get: " + badMap.get(broken));

        MutableKey mutable = new MutableKey("A");
        Map<MutableKey, String> mutableMap = new HashMap<>();
        mutableMap.put(mutable, "saved");
        System.out.println("mutable before: " + mutableMap.get(mutable));
        mutable.setId("B");
        System.out.println("mutable after: " + mutableMap.get(mutable));
        System.out.println("mutable hash after: " + mutable.hashCode());
    }
}
```

Compile and run:

```bash
javac --release 17 HashCodeStabilityDemo.java
java HashCodeStabilityDemo
```

Output:

```text
stable hash #1: 65
stable hash #2: 65
equal objects: true
equal hashes: true
broken hash #1: 1
broken hash #2: 2
broken map get: null
mutable before: saved
mutable after: null
mutable hash after: 66
```

**Output explanation:**

1. `String.hashCode()` of `"A"` is `65` and `"B"` is `66`. `StableKey` keeps `id` as a `final String`, so the data determining equality never changes; both calls to `first.hashCode()` return `65`. Two `StableKey("A")` objects with different references are equal and have equal hash codes.
2. `BrokenHashKey.hashCode()` returns `1`, then `2`, even though `id` never changed. This is a **clear violation** of the stability rule. When `HashMap.put` calls `hashCode()`, the counter increments to `3`; `get` increments it to `4`. The hash value used for lookup differs from the hash value stored when adding the key, so the example fails to find the entry.
3. `MutableKey("A")` is added to the map with hash code `65` and can be retrieved. After `setId("B")`, the new hash code is `66`; `HashMap` does not automatically move an already-stored entry to the new hash group. Therefore `get(mutable)` returns `null`. **The usage mistake is mutating a key while it is inside the map**, whereas the hash formula `id.hashCode()` itself remains consistent with the fields used in `equals()` in each state.
4. The example uses Java 17's default `HashMap` with values `65` and `66`, so the lookups above have deterministic results. The key principle is not the specific numeric values, but that different hash codes direct lookup to a different location.

Note: the two classes named `BrokenHashKey` and `MutableKey` are written **to demonstrate bugs and risks**, and should not be copied as keys for real applications.

## 5. Why Does Changing a Hash Code Make `HashMap` and `HashSet` Unusable?

At the time of `put(key, value)`, `HashMap` takes the key's hash code to locate where to store the entry. `get(key)` takes the current hash code to find where to look up, then compares keys when necessary. `HashSet` uses a similar hash table mechanism to manage elements.

Therefore, a key whose hash code changes while still inside a hash table can cause:

- `map.get(key)` to return `null` even though you just inserted that exact object.
- `map.containsKey(key)`, `set.contains(key)`, or `set.remove(key)` to fail unexpectedly.
- An equivalent key to fail to find the old entry if its `equals()`/`hashCode()` or the stored key's no longer share the same interpretation.
- Data to still show up when iterating over entries yet not be found through normal lookups.

Not **every** hash value change causes lookup failure in every configuration: buckets, collisions, and internal mechanisms can affect the outcome. Proper design must not rely on a lookup succeeding by chance. Keep the attributes used as keys unchanged for the entire time the object resides in a hash structure.

Even having `equals()` return `true` when an object is compared with itself cannot save a key with a mismatched hash code: `HashMap` may never reach the `equals()` comparison step if the current hash code differs from the stored entry's hash code.

## 6. When Can a Hash Code Change Without Automatically Violating the Contract?

The contract explicitly states **“if no information used in `equals()` is modified”**. For example:

```java
final class Task {
    private String taskCode;

    Task(String taskCode) {
        this.taskCode = taskCode;
    }

    void changeTaskCode(String newCode) {
        this.taskCode = newCode;
    }

    @Override
    public boolean equals(Object other) {
        return this == other
                || other instanceof Task that
                        && Objects.equals(taskCode, that.taskCode);
    }

    @Override
    public int hashCode() {
        return Objects.hashCode(taskCode);
    }
}
```

This is an **illustrative code snippet**; it requires `import java.util.Objects;` when placed in a Java file. When `taskCode` is changed, the information determining `equals()` has changed. Thus, changing the hash code accordingly does not automatically violate the conditional stability clause. However, avoid modifying `taskCode` if `Task` is currently being used as a `HashMap` key or `HashSet` element.

Conversely, if the class also has a `lastViewedAt` field **that does not participate in `equals()`**, `hashCode()` must not use that field's value to vary the hash code. Doing so can violate both stability and the rule that equal objects must share the same hash code.

You can design a mutable object with a **fixed logical key**: display attributes are allowed to be modified, while the fields used for `equals()` and `hashCode()` are kept immutable.

## 7. Implementations That Easily Break Stability

### 7.1. Calling Current Time, Random Generators, or Counters Inside `hashCode()`

Patterns such as:

```java
@Override
public int hashCode() {
    return (int) System.currentTimeMillis(); // WRONG
}
```

or:

```java
@Override
public int hashCode() {
    return ++counter; // WRONG if counter is not intentionally changing equals data
}
```

are unsuitable for an object's hash code when equality information stays unchanged. These are **illustrative buggy snippets**, not standalone programs.

Even if two calls might happen to return the same value by chance, randomness or time does not guarantee the required consistency. Avoid querying configuration state, external data, or network services to compute a hash if they are not stable identity values of the object.

### 7.2. Hashing from More Fields Than `equals()` Uses

Suppose `equals()` treats two products with the same `sku` as equal, while `hashCode()` uses both `sku` and `price`. Two objects with the same `sku` but different `price` can have different hash codes, violating the rule **equal implies same hash**. Furthermore, when `price` changes, the hash can change even though the information used for `equals()` stays the same.

Fix: use the same logical identity criteria in both methods; if `price` does not determine `equals()`, exclude it from the `hashCode()` formula.

### 7.3. Fields That Are Arrays or Mutable Collections

Declaring `final int[] values` fixes only the **reference to the array**, not the mutability of the elements inside it. When using `Arrays.equals(values, other.values)` along with `Arrays.hashCode(values)`, modifying an element after adding the key to a `HashMap` can still change the hash code.

The same applies to mutable collections: element mutations can alter `equals()`/`hashCode()`. Consider defensive copying, immutable types, or basing identity on an immutable ID.

In particular, an array's default `Object.hashCode()` evaluates array object identity, whereas `Arrays.hashCode(array)` computes from contents. Choose the approach matching the equality comparison in use.

### 7.4. Invalid Hash Code Caching

Caching `hashCode()` is a **conditional** optimization: it works when the values participating in equality are immutable and the hash is computed accurately from them. With mutable fields, a stale cached value can become wrong or out of sync with `equals()` after an update.

If you choose to cache on an object with mutable fields, you must design a cache invalidation mechanism and ensure correctness under concurrent access; a simpler and less error-prone solution is usually an immutable value object.

### 7.5. Confusing Hash Values with Long-Term Identity

`hashCode()` is not a UUID, database key, security token, or tamper-proof checksum. Collisions are allowed and the contract does not require stability across runs. If you need a stored identifier, use a clearly defined business ID (such as a UUID), and you can then compute `equals()`/`hashCode()` from that ID.

## 8. Recommended Design and Testing

For map keys, the easiest pattern to maintain is an immutable value object:

```java
import java.util.Objects;

public record CustomerKey(String tenantId, long customerId) {
    public CustomerKey {
        Objects.requireNonNull(tenantId);
    }
}
```

This is a valid Java 17 record declaration; when placed in `CustomerKey.java`, it compiles cleanly. Java automatically generates `equals()` and `hashCode()` matching the record components. Because `String` and `long` are both stable values and record components cannot be reassigned after creation, this type is a suitable choice for a key.

**Records do not guarantee deep immutability:** a record containing a mutable `List`, array, or mutable object can still see its component contents modified after creation. Therefore, evaluate the *data type of each component*, not just the `record` keyword.

When reviewing or writing tests for a class that overrides `equals()`/`hashCode()`, check the following cases:

1. **Unchanged repetition:** create `x`, call `x.hashCode()` multiple times while the data used for `equals()` is unchanged; all results must be identical.
2. **Equal implies same hash:** create `x` and `y` with different references where `x.equals(y)` returns `true`; verify `x.hashCode() == y.hashCode()`.
3. **Fields outside equality:** mutate an allowed mutable attribute that is not part of `equals()`; the hash result must remain contract-compliant, with stability preserved.
4. **Fields determining equality:** if the type allows mutating key fields, check the hash formula after mutation and do not use the object as a key in a hash table while mutating it.
5. **Collection interaction:** use an equal-valued key to `put/get` or `add/contains`; verify stable behavior while the key does not change.
6. **External data sources:** look for calls to clocks, random generators, global variables, network, getters with side effects, or unsafe caches in the hash computation path.

A small check can be written as follows (a snippet inside a test class method, not a standalone file):

```java
int expected = key.hashCode();

for (int i = 0; i < 100; i++) {
    if (key.hashCode() != expected) {
        throw new AssertionError("hashCode khong on dinh");
    }
}
```

Ensure `key` is non-`null` and the information used in `equals()` does not change during the check. Repeated checks help catch many bugs, though they cannot exhaustively prove every computation branch or multithreaded scenario. Combine this with code review and design inspection.

## 9. Key Points to Remember

- `hashCode()` must return **the same integer within a single execution** when the information used for `equals()` comparisons does not change.
- If two objects are equal according to `equals()`, their hash codes **must** be equal; unequal objects **may** share a hash code.
- Hash codes do not need to be identical across multiple JVM runs, and a hash code is not a long-term stored identifier.
- If a field used in `equals()` is changed, the hash code may change without automatically violating the conditional stability clause. Even so, **do not mutate a key while it is inside a `HashMap` or `HashSet`**.
- Avoid using current time, randomness, call counts, fields outside equality, or volatile external data to determine a hash code.
- Prefer immutable logical keys, design matching `equals()`/`hashCode()`, and test both stability and collection lookups.
