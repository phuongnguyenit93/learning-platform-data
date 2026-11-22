# Only Cache Hash Codes When State and Synchronization Allow It

`hashCode()` is part of the equality contract between Java objects. When computing a hash code is expensive, you can **cache (memoize)** the result for reuse. However, a `cachedHash` field is only valid if that value still represents the state that `equals()` treats as logical identity, and—when accessed by multiple threads—both publication and reads/writes of the value are properly designed.

Three questions must be answered before caching a hash:

1. **What state determines `equals()` and `hashCode()`?** Does that state stay unchanged for the object's lifetime, or at least for as long as the cache is used?
2. **How is the hash computed and published?** Can another thread access it before or concurrently while the cache is being assigned?
3. **Where is the object used?** If it already serves as a `HashMap` key or `HashSet` element, changing the values that determine its hash can break lookup even if the cache is updated properly.

The goal is to protect correctness first, and optimize performance second.

## 1. The `equals()`–`hashCode()` Contract Governs Whether Caching Is Allowed

For two objects `a` and `b`:

- If `a.equals(b)` returns `true`, `a.hashCode() == b.hashCode()` **must** hold.
- Two unequal objects **are allowed** to have the same hash code: a hash collision does not mean they are equal.
- Within a single execution of a Java application, if the information used in equality comparisons **does not change**, multiple calls to `hashCode()` on the same object must return consistent results.
- If the information used in comparisons **changes**, the hash result may change; however, avoid mutating it while the object is actively used as a key in a hash structure.

A cached hash is a **derived value** from state. When logical state changes, the cache can become a **stale cache**. For example, the object currently has `code = "B"`, yet the cache field holds the hash of `"A"`. Another object that also has `code = "B"` will be equal under `equals()`, yet may return a different hash code. That is a contract bug, even though every method runs without throwing an exception.

Nor should `hashCode()` be mistaken for a unique, universally invariant ID. Hash codes can collide; stability must be designed around **the fields participating in equality**.

## 2. Choosing a Strategy Based on State Characteristics

| Case | Recommendation | Reason |
| --- | --- | --- |
| Immutable value object; hash is used frequently | Can **precompute eagerly** and store in a `final` field | No need to handle invalidation or visibility of a late cache write |
| Immutable value object; hash is expensive but rarely called | Can **compute lazily** with safe publication | Avoids computing hashes for instances that never need them |
| Mutable object used strictly within a single thread | Conditional caching; must invalidate when relevant state changes | Prevents returning stale results |
| Mutable object accessed concurrently by multiple threads | Consider redesigning; if caching, keep state, cache, and `equals()` consistent | `volatile` on the cache alone does not synchronize other state fields |
| Mutable object already inside `HashMap`/`HashSet` | Avoid mutating fields used for equality/hash | Invalidation does not relocate the element inside the hash structure |
| Hash is cheap to compute and rarely called | Usually compute directly | Caching costs memory, conditional branches, and sometimes synchronization |

Do not see `private final List<String> items` and assume the state is immutable: `final` fixes the **reference**, whereas the underlying `List` can still be modified. If the list's contents participate in the hash calculation, make a defensive copy and keep the contents truly immutable, or choose a different design.

## 3. Eager Caching: Simplest for Immutable Objects

When every field participating in `equals()` is immutable, you can compute the hash once in the constructor and store it in a `final` field. That avoids having to handle stale caches altogether.

Create the file **`EagerHashDemo.java`**:

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

final class AccountKey {
    private final String tenant;
    private final String account;
    private final int cachedHash;

    AccountKey(String tenant, String account) {
        this.tenant = Objects.requireNonNull(tenant);
        this.account = Objects.requireNonNull(account);
        this.cachedHash = Objects.hash(tenant, account);
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        return obj instanceof AccountKey other
                && tenant.equals(other.tenant)
                && account.equals(other.account);
    }

    @Override
    public int hashCode() {
        return cachedHash;
    }
}

public class EagerHashDemo {
    public static void main(String[] args) {
        AccountKey a = new AccountKey("north", "001");
        AccountKey b = new AccountKey("north", "001");
        AccountKey c = new AccountKey("south", "001");

        System.out.println("a equals b: " + a.equals(b));
        System.out.println("same hash: "
                + (a.hashCode() == b.hashCode()));

        Set<AccountKey> keys = new HashSet<>();
        keys.add(a);
        keys.add(b);
        keys.add(c);
        System.out.println("set size: " + keys.size());
    }
}
```

Compile and run with Java 17+:

```bash
javac EagerHashDemo.java
java EagerHashDemo
```

Stdout:

```text
a equals b: true
same hash: true
set size: 2
```

**Why is this pattern valid?**

- `tenant` and `account` are non-null, of the immutable `String` type, and assigned once.
- `equals()` and `Objects.hash(tenant, account)` use the **exact same two components**.
- `cachedHash` is `final`, assigned directly in the constructor, with no setter.
- `AccountKey` is a `final` class, preventing subclasses from adding state while inheriting the old equality rule.
- The object is properly constructed: `this` never escapes the constructor. The Java Memory Model provides special initialization guarantees for `final` fields; nevertheless, follow safe object publication for any other state if present.

`Objects.hash()` is easy to read, though because it uses varargs it carries extra overhead compared to a manual hash formula. Only optimize the formula after measuring, always staying consistent with `equals()`.

**Distinction:** eager calculation adds work to the constructor even if nobody ever calls `hashCode()`. For small objects with simple hashing, there is no reason to cache the hash unless measurements show a benefit.

## 4. Lazy Caching: Must Solve Cross-Thread Publication

**Lazy caching** computes the hash only on the first call. If the object is immutable, two threads might compute the hash concurrently from the same data and obtain the same result. In that case, duplicate computation only wastes a bit of CPU; correctness is unaffected provided the calculation is **pure and deterministic**, and the result is safely published.

An easy-to-verify approach is storing the hash in a **`volatile Integer`** field, using `null` to indicate "not yet computed":

```java
private volatile Integer cachedHash;

@Override
public int hashCode() {
    Integer local = cachedHash;
    if (local != null) {
        return local;
    }

    int computed = immutableCode.hashCode();
    cachedHash = computed;
    return computed;
}
```

This is an **illustrative code snippet**, assuming the class has an immutable `immutableCode` field. The `volatile` keyword ensures that once a thread reads the published cache reference, it observes the proper value; assigning a reference to a `volatile` field is atomic. Two threads can still both observe `null` and compute it, yet with immutable data both publish the same value.

### 4.1. Complete Example, Including a Hash of `0`

Create the file **`LazyHashDemo.java`**:

```java
import java.util.Objects;

final class LazyKey {
    private final String code;
    private volatile Integer cachedHash;

    LazyKey(String code) {
        this.code = Objects.requireNonNull(code);
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        return obj instanceof LazyKey other
                && code.equals(other.code);
    }

    @Override
    public int hashCode() {
        Integer local = cachedHash;
        if (local != null) {
            return local;
        }

        int computed = code.hashCode();
        cachedHash = computed;
        return computed;
    }
}

public class LazyHashDemo {
    public static void main(String[] args) {
        LazyKey first = new LazyKey("");
        LazyKey second = new LazyKey("");

        System.out.println("first hash: " + first.hashCode());
        System.out.println("repeat hash: " + first.hashCode());
        System.out.println("equals: " + first.equals(second));
        System.out.println("same hash: "
                + (first.hashCode() == second.hashCode()));
    }
}
```

Commands:

```bash
javac LazyHashDemo.java
java LazyHashDemo
```

Stdout:

```text
first hash: 0
repeat hash: 0
equals: true
same hash: true
```

`String.hashCode()` for the empty string is `0`. If you use an `int cachedHash = 0` field and treat `0` as meaning "not computed yet", an object whose true hash is `0` will recompute it every time. That **does not necessarily produce a wrong result**, but it breaks the "compute only once" expectation. Use a nullable `Integer`, a separate initialized flag, or another result structure to distinguish them.

**Costs to weigh:** `Integer` involves boxing, a `volatile` field has access overhead, and lazy init adds a conditional branch. For cheap hashes, calling `code.hashCode()` directly can be simpler. This is a **semantically valid pattern**, not a claim that caching is always faster.

### 4.2. When Is `synchronized` Needed?

If the hash computation itself is very heavy or resource-constrained so that **at-most-once execution** is required, you can guard checking and updating the cache with `synchronized` or an equivalent synchronized initialization mechanism. Even then, synchronization is not free and does not replace the requirement that the hashed data represent a stable snapshot.

Do not apply double-checked locking mechanically: that pattern requires careful visibility/publication design under the Java Memory Model and is only worth using when genuinely beneficial. If `hashCode()` has side effects, uses random values, reads a clock, or depends on mutating external data, the deeper flaw is an **inconsistent hash function design**.

## 5. Stale Cache Bugs on Mutable Objects

If an attribute participating in `equals()` changes without invalidating the cache, two objects can be equal while reporting different hashes.

Create the file **`StaleHashDemo.java`**:

```java
import java.util.Objects;

final class MutableKey {
    private String code;
    private Integer cachedHash;

    MutableKey(String code) {
        this.code = Objects.requireNonNull(code);
    }

    void changeCode(String newCode) {
        code = Objects.requireNonNull(newCode);
        // Intentional bug: fails to clear cachedHash.
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        return obj instanceof MutableKey other
                && code.equals(other.code);
    }

    @Override
    public int hashCode() {
        if (cachedHash == null) {
            cachedHash = code.hashCode();
        }
        return cachedHash;
    }
}

public class StaleHashDemo {
    public static void main(String[] args) {
        MutableKey a = new MutableKey("A");
        System.out.println("before: " + a.hashCode());

        a.changeCode("B");
        MutableKey b = new MutableKey("B");

        System.out.println("after: " + a.hashCode());
        System.out.println("b hash: " + b.hashCode());
        System.out.println("equals: " + a.equals(b));
        System.out.println("same hash: "
                + (a.hashCode() == b.hashCode()));
    }
}
```

Commands:

```bash
javac StaleHashDemo.java
java StaleHashDemo
```

Stdout:

```text
before: 65
after: 65
b hash: 66
equals: true
same hash: false
```

`"A".hashCode()` is `65`, and `"B".hashCode()` is `66`. After `a` changes `code` to `"B"`, `equals()` evaluates `a` and `b` as equal, yet `a.hashCode()` keeps returning the old cached `65`. **This directly violates the `equals()`/`hashCode()` contract.** This is an intentionally broken example for learning purposes only.

### 5.1. Invalidating the Cache in Setters Is Necessary but Not Sufficient

For a mutable object used in a controlled single thread, you can invalidate the cache when the relevant value changes:

```java
void changeCode(String newCode) {
    code = Objects.requireNonNull(newCode);
    cachedHash = null;
}
```

This is only a **snippet for a single-threaded or externally synchronized context**, not a complete solution. You must also consider:

- Every setter of **every** field participating in equality/hash must invalidate the cache.
- With multiple threads, one thread could be computing the old hash while another mutates state and clears the cache; the first thread might then write back the stale hash **after the cache was cleared**.
- There is no guarantee that reading multiple mutable fields forms a **consistent snapshot** without a shared synchronization protocol.
- If the object has already been inserted into a `HashMap`/`HashSet`, recomputing the hash after state changes does not automatically move the element's bucket in the hash table.

Thus, **proper cache invalidation** still does not mean **mutating a key inside a collection is safe**.

## 6. Multiple Threads: `volatile` Does Not Replace State Synchronization

Imagine an object's equality depends on two mutable fields `name` and `revision`. Thread A updates `name` and then updates `revision`; thread B computes the hash right in between those two steps. B may observe a pair of values that never represented a valid complete business state. Making `cachedHash` `volatile` only publishes the **cache value**; it does not turn reading two mutable fields into an atomic operation.

To cache a hash that depends on mutable state shared across multiple threads, you must design and verify **all** of the following relationships:

1. **State reads/writes:** setters and `hashCode()` use the same synchronization lock or an atomically published immutable snapshot.
2. **Cache tied to state version:** prevent a thread from computing from an old version and publishing after a newer version invalidated the cache.
3. **Consistent `equals()`:** comparing two objects must also read consistent logical states; if two objects must be locked, resolve lock ordering to avoid deadlock.
4. **Object publication:** construct and share instances across threads safely without leaking half-constructed state.
5. **Collection semantics:** regardless of the synchronization above, if key-defining attributes are modified **while the key resides in a map/set**, the internal storage slot may still fail to match the new hash value.

`volatile` solves visibility/ordering for **a single field or publication step**, not transactions across multiple fields. `synchronized` works only when every relevant access follows a compatible synchronization protocol. `ConcurrentHashMap` protects the map's internal structure, **not** a mutable key object from having its hash/equality mutated.

**A design that is usually easier to verify:** keep the key immutable and put mutable state in the map's value. For example, `Map<AccountKey, MutableAccountState>` using `AccountKey` from Section 3. To update identity, create a new key and perform the appropriate replacement under your application's synchronization policy. Alternatively, hold an **immutable snapshot** on each update; each snapshot has its own fixed state and hash code.

## 7. Checking the Difference Between Immutable and Mutable Keys

Hash-based structures typically compute/place entries using the hash **at insertion time** and then compute the hash of the lookup key when querying. If the same instance serves as a key yet its hash-participating values changed, the lookup may probe a different bucket. Even if the setter cleared the cache properly, the entry still sits in the slot from the earlier insertion. Calling a fresh `hashCode()` now cannot "repair" insertion history.

Therefore:

- `HashMap`, `HashSet`, and even `ConcurrentHashMap` require keys to keep stable `equals()`/`hashCode()` semantics **for the duration they act as keys**.
- Do not assume wrapping with `Collections.synchronizedMap(...)` makes key mutation safe.
- If an identity change is unavoidable, design a controlled update operation: remove the old key under its old state, create or select the new immutable key, and re-insert under the proper synchronization protocol. Never mutate hash fields of a stored key and hope `remove()` finds the right object.
- If a mutable object serves only as a map *value*, mutating the value does not cause key-bucket issues, though thread safety of the value still needs its own design.

## 8. Process for Deciding on `hashCode()` Caching in a Project

**Step 1: Identify equality data.** If only `id` defines identity, the hash should rely on `id`, without adding mutable names or timestamps. If it is a value object, examine the components that genuinely carry value semantics.

**Step 2: Check for deep mutability.** Are the hashed fields truly immutable? Are there arrays, lists, nested objects, or mutable references? Does `this` escape the constructor? Could a subclass alter the equality definition?

**Step 3: Measure cost.** Benchmark/profile with realistic workloads. Simple hashing is sometimes cheaper than maintaining a cache; adding a field can increase memory footprint across large object counts.

**Step 4: Pick a caching approach if warranted.** For immutable objects with frequently used hashes, prefer eager computation in a `final` field. For immutable objects with expensive but rarely used hashes, consider lazy computation with explicit publication. If hashing is very cheap, just compute it directly.

**Step 5: If mutable, be rigorous about invalidation and concurrency.** Every relevant write path must coordinate with the cache and read paths, avoiding stale write-backs after invalidation. In most applications, separating out an immutable key is simpler and less error-prone.

**Step 6: Audit set and map usage.** Can the object be used as a key while its equality/hash fields might change? If so, change the key design rather than just changing how caching is implemented.

**Step 7: Test edge cases.** Include two equal instances, hash collisions, a hash of `0`, cached hashes after state updates, concurrent multi-threaded computation, and `equals()`/`hashCode()` across inheritance hierarchies if any exist.

## 9. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| "Computing a hash once and caching it is a harmless optimization." | Benefit depends on workload; caching has costs and breaks if state changes. |
| "Having `final` fields means everything inside is immutable." | `final` fixes the reference, not the contents of the referenced object. |
| "`volatile cachedHash` makes the object thread-safe." | It only protects visibility/publication of the cache under the memory model. |
| "If the setter clears the cache, `HashMap` keys are always fine." | The bucket assigned at insertion is not automatically updated to the new hash. |
| "`ConcurrentHashMap` solves mutable keys." | Map thread safety does not make a key's hash or equality stable. |
| "A hash of 0 means uninitialized." | `0` is a valid hash code; use a proper flag or sentinel if `0` must be cached too. |
| "Two equal hash codes prove two objects are equal." | Hash collisions are valid; `equals()` is still required. |
| "Putting `synchronized` on `hashCode()` solves everything." | If state mutations and `equals()` do not use a compatible mechanism, inconsistent reads can still happen. |

## 10. Code Review Checklist

- [ ] `equals()` and `hashCode()` use consistent data; equal objects always produce the same hash.
- [ ] Hash-determining properties are immutable, or every mutation coordinates proper invalidation.
- [ ] `final` references are not mistaken for deep immutability.
- [ ] Eager caches are completely initialized before the object is published.
- [ ] Lazy caches use proper visibility, handle a hash value of `0`, and account for concurrent computation.
- [ ] Under multi-threaded access, consistency covers source data, cache, and `equals()`, not just a single field.
- [ ] Keys inside `HashMap`/`HashSet` never change equality/hash-defining fields while stored.
- [ ] Caching has measured performance benefit and does not add pointless maintenance complexity.

**Principle to remember:** cache `hashCode()` only when **the hashed state is sufficiently stable** and **the publication/synchronization mechanism permits safe reuse**. Without clear answers to both, keep hashing direct or use immutable key objects.