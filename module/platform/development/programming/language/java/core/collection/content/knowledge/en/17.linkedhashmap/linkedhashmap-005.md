# removeEldestEntry and a Simple LRU Cache Model

## 1. Starting from a Cache with Finite Capacity

A cache temporarily holds computed or loaded results so that subsequent requests can reuse them. For example, suppose a program has loaded the description for product code `A`; if the user asks for `A` again, the program can return the held copy instead of reloading it immediately. A lookup that finds a result is called a **cache hit**; one that does not find it is called a **cache miss**. A cache is only useful when the program accepts reusing data according to the chosen policy.

If results are simply added to a `Map` without eviction, the number of entries can grow with the number of distinct keys encountered. A simple cache needs to answer two different questions:

1. How many entries may be kept at most?
2. When capacity is full and a new key arrives, which entry must leave the cache?

**LRU — Least Recently Used** selects the entry that has been used least recently. LRU does not ask which entry was created earliest, which value is smallest, or which key was used most often across the entire history. It relies solely on the order of accesses tracked by the structure. A recently accessed entry on a successful lookup is moved toward the newest end; the entry sitting longest at the oldest end is the candidate for eviction.

In this article, the order is written from left to right:

```text
[least recently used, ..., most recently used]
[LRU, ..., MRU]
```

`MRU` stands for Most Recently Used. With a limit of three entries, the following sequence of operations illustrates what needs to be built:

| Operation | LRU → MRU order after operation | Explanation |
|---|---|---|
| Add A | `[A]` | A is the only entry |
| Add B | `[A, B]` | B was just inserted |
| Add C | `[A, B, C]` | Three entries reached |
| Read A successfully | `[B, C, A]` | A was just used; B becomes the oldest |
| Add D | `[C, A, D]` | D enters the cache; B is evicted because the limit is exceeded |

B leaving the cache is called **eviction**. Evicting an entry from the cache does not mean deleting the product from the database or deleting the source data. A cache should hold data that can be reloaded or recomputed. If dropping an entry means losing the only copy of the data, a different storage design is needed before applying an eviction policy.

The goal here is to understand and write a small, single-threaded, entry-count-bounded LRU cache based on `LinkedHashMap`. The two main components are **access order** and **the eviction rule after adding an entry**. Understanding each component separately helps avoid creating a bounded map that evicts the wrong entry.

## 2. Which Part of the LRU Mechanism Does LinkedHashMap Provide?

### 2.1. Key Lookup and Maintaining an Iteration Order

`LinkedHashMap` combines hash-table key lookup with a linked list that maintains entry order. When using access-order mode, the iteration order of `keySet()`, `values()`, and `entrySet()` reflects the order from least recently accessed to most recently accessed.

Because the structure already maintains this order, the cache does not need to find the entry with the smallest access time by scanning the entire map after every insertion. The program also does not need to record a timestamp for each `get`. Access order here is the order of operations on the map, not a real-time history with dates and times.

The following snippet only illustrates configuration; it is not a standalone runnable program:

```java
LinkedHashMap<String, String> entries =
        new LinkedHashMap<>(16, 0.75f, true);
```

The three arguments have different roles:

| Argument | Meaning in the example | Is it the cache entry-count limit? |
|---|---|---|
| `16` | Requested initial capacity for the hash table | No |
| `0.75f` | Load factor of the hash table | No |
| `true` | Enables access order (`accessOrder`) | No; only chooses how order is maintained |

`new LinkedHashMap<>(3)` does not create a cache that holds only three entries. Initial capacity relates to hash-table allocation and resizing; it does not forbid the map from holding more than that number. A cache limit must be expressed through a separate policy.

### 2.2. Insertion Order and Access Order Answer Two Different Questions

The default constructor of `LinkedHashMap` uses **insertion order**. In that mode, reading A after inserting A, B, and C does not move A to the end. If you always evict the head entry, the policy is close to FIFO — First In, First Out: the entry that entered first leaves first.

The three-argument constructor with `accessOrder=true` uses **access order**. When `get(A)` finds A, entry A becomes the most recently used. Then evicting the head entry matches LRU.

Therefore, a bounded LRU cache needs both parts:

```text
accessOrder=true
    → maintains the usage order correctly

removeEldestEntry returns size() > maximumEntries
    → evicts the head entry when an insertion exceeds the limit
```

Enabling `accessOrder=true` alone still allows the map to grow without bound. Overriding `removeEldestEntry` alone while keeping insertion order limits the number of entries, but it is not yet LRU.

### 2.3. Which Accesses Change Recency?

For the operations used in this article, keep in mind:

| Operation on an access-ordered map | Changes entry count? | Effect on order |
|---|---|---|
| `get(key)` finds the key | No | The entry becomes the newest |
| `get(key)` does not find the key | No | No entry to move |
| `put(key, value)` with a new key | Yes, before eviction is checked | New entry is at the end; may evict the head entry |
| `put(key, value)` with an existing key | No | Updates the value and moves that entry toward the newest end |
| `containsKey(key)` | No | Does not count as an access to change order |
| Iterating `entrySet()` or copying `keySet()` | No | Iteration itself does not refresh entries |

Do not infer that every method that looks like a "read" leaves the structure unchanged. `get` can change the order links even though it does not change `size()`. Conversely, `containsKey` checks existence without substituting for the usage semantics of `get` in an LRU policy.

The documentation also specifies access-producing operations such as `getOrDefault`, `putIfAbsent`, the `compute` methods, and `merge` when the corresponding entry exists after the operation. The `replace` methods only produce an access when the value is actually replaced. With `putAll`, each mapping generates one access in the iteration order of the input map's `entrySet()`. When extending a cache API, check the exact contract of any additional methods used; do not assume that only `get` affects LRU.

## 3. removeEldestEntry Is the Eviction Decision Point

### 3.1. Signature and Meaning of the boolean Result

`LinkedHashMap` declares the method `protected boolean removeEldestEntry(Map.Entry<K,V> eldest)`. This is a method provided by the class for subclasses to override. The method name does not mean that the override itself must always call `remove`.

The core snippet below illustrates the override inside a subclass; it is not a standalone Java file:

```java
@Override
protected boolean removeEldestEntry(Map.Entry<K, V> eldest) {
    return size() > maximumEntries;
}
```

Read the snippet in three steps:

1. `LinkedHashMap` has just added a new entry and asks the policy whether the oldest entry should be removed.
2. `eldest` is the entry currently at the head of the map's order: the oldest in insertion order or the least recently accessed in access order.
3. Returning `true` instructs the map to remove that entry; returning `false` keeps it.

The return value is a `boolean` decision, not the evicted entry. The default implementation returns `false`, so a plain `LinkedHashMap` does not automatically become a bounded cache.

### 3.2. When It Is Called: After Adding a New Entry

The most important point is that the method is called after `put` or `putAll` inserts a new entry into the map. While the condition is being checked, `size()` already includes the newly inserted entry.

With a limit of three:

```text
Before put(D):             [B, C, A]       size=3
After D is inserted:       [B, C, A, D]    size=4
removeEldestEntry(B):      4 > 3 → true
After evicting B:          [C, A, D]       size=3
```

The right condition is `size() > maximumEntries`. If you write `size() >= maximumEntries`, the third entry already triggers eviction as soon as the map reaches the limit of three; the cache can hold at most two entries after normal insertions.

`get` does not invoke this eviction mechanism simply because a read just happened. Updating an existing key with `put` may change the access order, but it does not add a new entry to trigger this check point. Distinguish **refreshing the order** from **triggering the post-insertion check**.

With `putAll`, do not imagine that Java receives all the data and then calls the policy only once at the end. New entries are inserted one by one; the policy is evaluated after those insertions. Which entries remain also depends on the access order produced during loading.

### 3.3. A Single Decision Only Requests Evicting the Head Entry

A single `true` requests removing one `eldest` entry. It is not a statement that means "loop until any arbitrary limit is satisfied." In a simple design, the limit is fixed in the constructor, the map starts empty, and each `put` of a new key increases the entry count by only one. Checking and dropping one entry is therefore enough to return to the limit.

If a limit of 100 is lowered to 2 while the cache already holds 100 entries, you cannot just change a variable and expect a single hook call to clean up everything. A deliberate shrinking operation is required. The classes in this article keep the limit fixed so that responsibility is not added to the API.

### 3.4. Do Not Remove Manually and Also Return true

The clean approach in this article is to let the override compute only the decision. Do not call `remove(eldest.getKey())` here and then also return `true`. The documentation allows the override to modify the map directly, but when doing so it must return `false`; if it both modifies the map and returns `true`, the effect of the call is unspecified. An entry-count cache does not need that complexity.

Do not use this method to load data, trigger business logic, or perform slow tasks. It runs on the map's entry-insertion path. Keeping the decision short and easy to inspect makes it clear when data is evicted.

## 4. Program 1: Observing Exactly When the Hook Runs

Save the complete program below into `LinkedHashMapLruHookDemo.java`. The example uses Java 17 or newer. The counter variable and `hook:` lines only help observe the mechanism in this article.

```java
import java.util.LinkedHashMap;
import java.util.Map;

public class LinkedHashMapLruHookDemo {
    static final class LruMap<K, V> extends LinkedHashMap<K, V> {
        private final int maximumEntries;
        private int hookCalls;

        LruMap(int maximumEntries) {
            super(16, 0.75f, true);
            if (maximumEntries < 0) {
                throw new IllegalArgumentException("negative limit");
            }
            this.maximumEntries = maximumEntries;
        }

        @Override
        protected boolean removeEldestEntry(Map.Entry<K, V> eldest) {
            hookCalls++;
            boolean evict = size() > maximumEntries;
            System.out.println("hook: size=" + size()
                    + ", eldest=" + eldest.getKey()
                    + ", evict=" + evict);
            return evict;
        }
    }

    public static void main(String[] args) {
        LruMap<String, Integer> cache = new LruMap<>(3);
        cache.put("A", 1);
        cache.put("B", 2);
        cache.put("C", 3);
        System.out.println("initialLruToMru=" + cache.keySet());

        System.out.println("getA=" + cache.get("A"));
        System.out.println("afterGetA=" + cache.keySet());

        cache.put("D", 4);
        System.out.println("afterPutD=" + cache.keySet());
        System.out.println("hasB=" + cache.containsKey("B"));
        System.out.println("size=" + cache.size());

        int beforeUpdate = cache.hookCalls;
        cache.put("C", 30);
        System.out.println("afterExistingPut=" + cache);
        System.out.println("hookCountUnchanged="
                + (beforeUpdate == cache.hookCalls));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 LinkedHashMapLruHookDemo.java
java LinkedHashMapLruHookDemo
```

Stdout:

```text
hook: size=1, eldest=A, evict=false
hook: size=2, eldest=A, evict=false
hook: size=3, eldest=A, evict=false
initialLruToMru=[A, B, C]
getA=1
afterGetA=[B, C, A]
hook: size=4, eldest=B, evict=true
afterPutD=[C, A, D]
hasB=false
size=3
afterExistingPut={A=1, D=4, C=30}
hookCountUnchanged=true
```

### 4.1. Reading the Output Stage by Stage

The first three `put` calls all insert new keys, so three `hook:` lines appear. On the first call, the newly added entry A is also `eldest`, because the map has only one entry. `size=1`, `2`, and `3` do not exceed three, so no entry is evicted.

`get("A")` returns `1` and moves A to the end: `[A, B, C]` becomes `[B, C, A]`. No `hook:` line appears between `getA` and `afterGetA`. That is proof that updating order via a read does not mean calling `removeEldestEntry`.

When D is added, `hook: size=4, eldest=B, evict=true` shows all three facts: the size already counts D, B is at the head of the access order, and the limit-exceeded condition is true. After `put` finishes, the map retains `[C, A, D]`, B is absent, and `size()` returns to three.

Finally, `put("C", 30)` replaces the value of existing key C. The entry count does not increase. C becomes the newest, so the map prints as `{A=1, D=4, C=30}`; `hookCountUnchanged=true` confirms no new hook call occurred during that update.

### 4.2. Role of Each Implementation Detail

`super(16, 0.75f, true)` enables access order when the map is created. `maximumEntries` is a `final` field, separating the business limit from hash-table capacity. Checking for negative values ensures configuration errors are reported at construction time. `@Override` lets the compiler catch typos in the method name or signature.

`eldest.getKey()` is used to print the entry about to be evaluated. An entry-count decision does not need to inspect the key or value, because the only question is whether `size()` exceeds the limit. Do not add key-name conditions when trying to learn a pure LRU policy.

Printing `keySet()` and printing the entire map reflect the current order. They do not silently call `get` for each key to refresh the entire order. That is why the example can use those print statements to observe LRU.

## 5. Program 2: Same Limit, Different Evictions for FIFO and LRU

A common mistake is overriding `removeEldestEntry` correctly while forgetting the `true` argument. The following program creates two maps with the same limit of three, differing only in how order is maintained. Save it to `LinkedHashMapLruFifoDemo.java`.

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class LinkedHashMapLruFifoDemo {
    static final class BoundedMap<K, V> extends LinkedHashMap<K, V> {
        private final int maximumEntries;

        BoundedMap(int maximumEntries, boolean accessOrder) {
            super(16, 0.75f, accessOrder);
            if (maximumEntries < 0) {
                throw new IllegalArgumentException("negative limit");
            }
            this.maximumEntries = maximumEntries;
        }

        @Override
        protected boolean removeEldestEntry(Map.Entry<K, V> eldest) {
            return size() > maximumEntries;
        }
    }

    public static void main(String[] args) {
        BoundedMap<String, String> fifo = new BoundedMap<>(3, false);
        BoundedMap<String, String> lru = new BoundedMap<>(3, true);

        for (String key : List.of("A", "B", "C")) {
            fifo.put(key, key);
            lru.put(key, key);
        }

        fifo.get("A");
        lru.get("A");
        System.out.println("fifoBeforeD=" + fifo.keySet());
        System.out.println("lruBeforeD=" + lru.keySet());

        fifo.put("D", "D");
        lru.put("D", "D");
        System.out.println("fifoAfterD=" + fifo.keySet());
        System.out.println("lruAfterD=" + lru.keySet());
        System.out.println("fifoHasA=" + fifo.containsKey("A"));
        System.out.println("lruHasA=" + lru.containsKey("A"));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 LinkedHashMapLruFifoDemo.java
java LinkedHashMapLruFifoDemo
```

Stdout:

```text
fifoBeforeD=[A, B, C]
lruBeforeD=[B, C, A]
fifoAfterD=[B, C, D]
lruAfterD=[C, A, D]
fifoHasA=false
lruHasA=true
```

After adding A, B, and C and then reading A, the `fifo` map is still `[A, B, C]`; the `lru` map has become `[B, C, A]`. When D is added, both see size four and both return `true`, but `eldest` differs:

| Map | Head entry before adding D | Evicted entry | Remaining order |
|---|---|---|---|
| Insertion order (`false`) | A | A | `[B, C, D]` |
| Access order (`true`) | B | B | `[C, A, D]` |

`fifoHasA=false` while `lruHasA=true` is the practical policy difference. A was just used, yet it still leaves the FIFO cache because its insertion age did not change. In the LRU cache, using A protected A from the next eviction; B is the entry that went unused the longest.

Both structures are bounded in entry count. Therefore, checking only `size() <= maximumEntries` is not enough to verify that a cache implements LRU properly. You must check both **which entry is evicted** and **the order after accesses**.
## 6. Program 3: Wrapping the Map in a Small Cache with a Clear Contract

### 6.1. Why Not Simply Expose LinkedHashMap Directly?

Subclassing `LinkedHashMap` as in the previous two examples makes the mechanism easy to see. However, handing the entire map object to callers gives them the full `Map` API, views backed by the map, and many paths to mutate data. It then becomes harder to control the contract of "which operations this cache supports."

The second approach is to **hold a map internally**. The cache class exposes only the operations needed: `get`, `put`, `containsKey`, `size`, and a copy of the key order for observation. The internal map is `private`; callers never directly receive `keySet()` or `entrySet()` backed by it.

The cache in the example chooses specific rules:

- Non-negative limit, fixed when creating the cache.
- A limit of 0 is valid: data can be inserted and immediately evicted, so no entries are retained.
- Rejects `null` keys and `null` values.
- `get` returns `null` only when there is no matching entry.
- `containsKey` checks existence without refreshing the LRU position.
- `keysLruToMru()` returns a copied list, from oldest to newest.

These are policies of the wrapper class, not inherent limitations of `LinkedHashMap`. `LinkedHashMap` itself allows `null` keys and `null` values. Forbidding them here allows distinguishing a cache miss by `get == null` without needing an extra wrapper state for empty values.

Save the complete program into `SimpleLruCacheDemo.java`:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class SimpleLruCacheDemo {
    static final class SimpleLruCache<K, V> {
        private final LinkedHashMap<K, V> entries;

        SimpleLruCache(int maximumEntries) {
            if (maximumEntries < 0) {
                throw new IllegalArgumentException("negative limit");
            }
            entries = new LinkedHashMap<K, V>(16, 0.75f, true) {
                @Override
                protected boolean removeEldestEntry(Map.Entry<K, V> eldest) {
                    return size() > maximumEntries;
                }
            };
        }

        V get(K key) {
            Objects.requireNonNull(key, "key");
            return entries.get(key);
        }

        void put(K key, V value) {
            Objects.requireNonNull(key, "key");
            Objects.requireNonNull(value, "value");
            entries.put(key, value);
        }

        boolean containsKey(K key) {
            Objects.requireNonNull(key, "key");
            return entries.containsKey(key);
        }

        int size() {
            return entries.size();
        }

        List<K> keysLruToMru() {
            return new ArrayList<>(entries.keySet());
        }
    }

    private static void expectNullPointer(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected NullPointerException");
        } catch (NullPointerException expected) {
            System.out.println(label + "=NullPointerException");
        }
    }

    public static void main(String[] args) {
        SimpleLruCache<String, String> cache = new SimpleLruCache<>(2);
        cache.put("A", "a");
        cache.put("B", "b");
        System.out.println("getA=" + cache.get("A"));
        System.out.println("afterHit=" + cache.keysLruToMru());
        System.out.println("getMissing=" + cache.get("missing"));
        System.out.println("afterMiss=" + cache.keysLruToMru());
        System.out.println("hasB=" + cache.containsKey("B"));
        System.out.println("afterContains=" + cache.keysLruToMru());

        cache.put("C", "c");
        System.out.println("afterPutC=" + cache.keysLruToMru());
        System.out.println("getEvictedB=" + cache.get("B"));
        cache.put("A", "a2");
        System.out.println("afterUpdateA=" + cache.keysLruToMru());
        System.out.println("size=" + cache.size());

        List<String> snapshot = cache.keysLruToMru();
        snapshot.clear();
        System.out.println("afterSnapshotClear=" + cache.keysLruToMru());

        SimpleLruCache<String, String> disabled = new SimpleLruCache<>(0);
        disabled.put("A", "a");
        System.out.println("zeroLimitSize=" + disabled.size());
        System.out.println("zeroLimitGetA=" + disabled.get("A"));

        try {
            new SimpleLruCache<String, String>(-1);
            throw new AssertionError("Expected IllegalArgumentException");
        } catch (IllegalArgumentException expected) {
            System.out.println("negativeLimit=IllegalArgumentException");
        }

        expectNullPointer("nullKey", () -> cache.put(null, "value"));
        expectNullPointer("nullValue", () -> cache.put("X", null));
        System.out.println("afterRejectedNulls=" + cache.keysLruToMru());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SimpleLruCacheDemo.java
java SimpleLruCacheDemo
```

Stdout:

```text
getA=a
afterHit=[B, A]
getMissing=null
afterMiss=[B, A]
hasB=true
afterContains=[B, A]
afterPutC=[A, C]
getEvictedB=null
afterUpdateA=[C, A]
size=2
afterSnapshotClear=[C, A]
zeroLimitSize=0
zeroLimitGetA=null
negativeLimit=IllegalArgumentException
nullKey=NullPointerException
nullValue=NullPointerException
afterRejectedNulls=[C, A]
```

### 6.2. Hits, Misses, and Existence Checks

After adding A and B, the order is `[A, B]`. `get("A")` finds `a`, so the order becomes `[B, A]`. `get("missing")` returns `null` and does not create a new entry; the order remains `[B, A]`.

`containsKey("B")` returns `true`, yet `afterContains` is still `[B, A]`. If checking existence is meant to count as using the data in the application, choose an operation that matches that meaning. You cannot call `containsKey` and assume B was refreshed in LRU.

When C is added to the two-entry cache, B leaves the cache. `get("B")` afterward returns `null`, which is completely normal even though B existed earlier. A cache miss does not prove that the source data disappeared; it only proves that the cache currently lacks the requested entry.

`put("A", "a2")` updates an existing key, so the size remains two. After this operation A is newest and the order is `[C, A]`. Even if you write the exact same value for an existing key, `put` is still an access operation under the contract of an access-ordered map; do not use old/new value equality to infer that recency stays unchanged.

### 6.3. What Does Copying the Key List Protect?

`new ArrayList<>(entries.keySet())` iterates the current order and stores the key references in a new list. Calling `snapshot.clear()` only removes elements from the new list; `afterSnapshotClear=[C, A]` shows that the cache is not cleared along with it.

This differs from returning `entries.keySet()` directly: that view is backed by the map, and supported removal operations on the view mutate the map. Not exposing the view helps the cache class keep state-mutation paths in one easy-to-inspect place.

However, this is only a copy of the **list structure**. It does not deep-copy each key object. The cache also holds value references rather than deep-copying data. If a key is a mutable object, fields participating in `equals`/`hashCode` must not be modified while the key is in the map. If values are mutable, decide whether callers are allowed to mutate them. The LRU policy does not solve those contracts for you.

### 6.4. Limits of 0, 1, and Negative Numbers

With a limit of 0, `put("A", "a")` inserts the first entry, `size()` is temporarily one, and then the hook returns `1 > 0`. That sole entry is also `eldest` and is evicted. After `put` returns, `size()` is 0 and `get("A")` is `null`.

This behavior can be used to configure caching off while keeping the same API call path. It is an explicit decision in the example; another API might choose to reject a limit of 0, but it must document and test its policy consistently.

With a limit of 1, the first entry is kept because `1 > 1` is `false`. Adding another key temporarily brings the size to two and the old entry is evicted. This is also an easy way to catch a `>=` bug: with that wrong condition, the very first entry is already evicted.

Negative limits are rejected with `IllegalArgumentException` right in the constructor. Do not use a negative number as an ambiguous signal for "unlimited" in this class, because then the eviction condition would no longer match the contract being learned.

### 6.5. Rejecting null Before Mutating the Map

`put` checks both key and value with `Objects.requireNonNull` before calling `entries.put`. Thus, when the two attempts `put(null, "value")` and `put("X", null)` fail, no new entry is inserted, no existing entry is evicted, and the order remains `[C, A]`.

Do not validate the value only after inserting it and then throw an error. In a bounded cache, inserting an invalid entry could already have evicted a valid entry. Validating before the mutating operation keeps error behavior predictable.

If an application needs to cache a "not found" result to avoid repeated loads, a dedicated result type or sentinel value may be needed. Simply removing the `null` check in the example would make `get(key) == null` ambiguous: it could mean a miss or a hit with a `null` value. This article keeps a no-`null` policy so the hit/miss path stays clear.

## 7. Program 4: Fetch from Cache, Load on Miss

### 7.1. Request Processing Path

A cache class is often used according to this pattern:

```text
Receive key
    ↓
Look up cache with get
    ├─ Value present → return immediately; entry becomes newest
    └─ Absent → load/compute result
                      ↓
                put into cache
                      ↓
           may evict LRU entry if full
                      ↓
                 return result
```

The data-loading function, called `loader` in the program, takes a key and produces a value. Here the function simply converts a string to uppercase so that results and call counts are completely deterministic. In a real application, loading cost may be much higher; the principle of checking the cache first remains the same.

Save the following program into `ReadThroughLruDemo.java`. It is independent of the previous three examples; there is no need to copy classes from other files.

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;

public class ReadThroughLruDemo {
    static final class Cache<K, V> {
        private final LinkedHashMap<K, V> entries;

        Cache(int maximumEntries) {
            if (maximumEntries < 0) {
                throw new IllegalArgumentException("negative limit");
            }
            entries = new LinkedHashMap<K, V>(16, 0.75f, true) {
                @Override
                protected boolean removeEldestEntry(Map.Entry<K, V> eldest) {
                    return size() > maximumEntries;
                }
            };
        }

        V getOrLoad(K key, Function<? super K, ? extends V> loader) {
            Objects.requireNonNull(key, "key");
            Objects.requireNonNull(loader, "loader");
            V cached = entries.get(key);
            if (cached != null) {
                return cached;
            }
            V loaded = Objects.requireNonNull(loader.apply(key), "loaded value");
            entries.put(key, loaded);
            return loaded;
        }

        List<K> keysLruToMru() {
            return new ArrayList<>(entries.keySet());
        }
    }

    private static int loadCount;

    private static String load(String key) {
        loadCount++;
        System.out.println("load=" + key);
        return key.toUpperCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        Cache<String, String> cache = new Cache<>(2);
        for (String key : List.of("a", "b", "a", "c", "b")) {
            String value = cache.getOrLoad(key, ReadThroughLruDemo::load);
            System.out.println("result=" + key + ":" + value
                    + ", order=" + cache.keysLruToMru());
        }
        System.out.println("loadCount=" + loadCount);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ReadThroughLruDemo.java
java ReadThroughLruDemo
```

Stdout:

```text
load=a
result=a:A, order=[a]
load=b
result=b:B, order=[a, b]
result=a:A, order=[b, a]
load=c
result=c:C, order=[a, c]
load=b
result=b:B, order=[c, b]
loadCount=4
```

### 7.2. Five Requests, Only Four Loads

The cache holds at most two entries. Each request is handled as follows:

| Request | Hit or miss? | Calls loader? | Order after request | Evicted entry |
|---|---|---|---|---|
| `a` | Miss | Yes, call 1 | `[a]` | None |
| `b` | Miss | Yes, call 2 | `[a, b]` | None |
| `a` | Hit | No | `[b, a]` | None |
| `c` | Miss | Yes, call 3 | `[a, c]` | `b` |
| `b` | Miss | Yes, call 4 | `[c, b]` | `a` |

The third request proves the cache is reusing results: before `result=a:A, order=[b, a]`, there is no new `load=a` line. This request also makes `a` the newest, so when `c` is added, `b` must leave the cache.

The final request for `b` must load again because `b` was evicted. LRU prioritizes recently used data; it does not guarantee that a key is loaded only once in the lifetime of the program. The number of loads depends on the request sequence and the cache limit.

`Locale.ROOT` keeps the uppercase conversion independent of the machine's default locale. It only keeps the example's output deterministic; it is not part of the LRU mechanism.

### 7.3. Why Is Checking cached != null Enough Here?

The internal map only receives data through `getOrLoad`, and the result of `loader.apply(key)` is checked to be non-`null` before `put`. Thus there are no entries with a `null` value; `entries.get(key)` returning `null` can be interpreted as a miss.

The key and the `loader` object itself are also checked upfront. Under this contract, passing `loader=null` is an error even when the key is already in the cache. That is an input-validation choice of the API being written, not mandatory behavior for every cache.

If the loader throws an exception, execution never reaches `entries.put`; a failed result does not become an entry. If the loader returns `null`, `requireNonNull` throws `NullPointerException`, and the cache does not insert a `null` value either. The loader in the example only computes a value and does not directly mutate the cache itself.

An empty value such as `""` is still a non-`null` object and can still be stored. Do not conflate "no entry present," "a business-valid empty value," and "the loader failed" into the same branch without defining the contract.

With a limit of 0, `getOrLoad` can still load and return the value for the current request. The newly inserted entry is evicted immediately, so the next request misses again. "Retaining no results" does not mean the method is forbidden from returning the value it just computed.

## 8. Reading the Model's Limitations Correctly

### 8.1. An Entry-Count Limit Is Not a Byte Limit

`size() > maximumEntries` counts mappings. An entry holding a small string and an entry holding a huge data structure each contribute one unit to `size()`. Therefore, a cache of at most 100 entries does not guarantee a fixed number of megabytes.

The map, keys, values, and order links all have memory overhead. An entry limit caps the growth of mappings with the number of distinct keys seen; it does not replace evaluating data size and lifetime. Do not call this a mechanism for measuring or precisely managing heap usage.

Evicting an entry only drops the cache's reference to that data. If references remain elsewhere, the object can still be used. Even when no strong references remain, garbage collection timing is up to the JVM; `removeEldestEntry` is not a command telling the JVM to immediately free a specific number of bytes.

### 8.2. LRU Is Not an Expiration Time

LRU is based on recency of access, whereas expiration is commonly called TTL — Time To Live. An entry unused for an hour can still remain in an LRU cache if no insertion has caused the limit to be exceeded. Conversely, a newly loaded entry can still be evicted if other keys continue to be used.

`removeEldestEntry` is not called periodically by a timer. The clock passing a threshold does not automatically run this method. A `get` call also does not invoke the hook to clean up expired data. Therefore, you cannot achieve true TTL merely by changing the condition expression and assuming the cache cleans itself continuously.

This article implements only an entry-count LRU policy. When expiration, size weighting, or data-refresh policies are needed, design the corresponding checks and eviction logic separately. Do not attach those feature names to a class just because it has an eviction method.

### 8.3. Holding Results Does Not Guarantee Fresh Data

If the source data changes while an old copy remains in the cache, a hit can return stale data. LRU only decides which entries to prioritize keeping; it does not know that the data source was just updated. Invalidating on source changes, writing through new values, or choosing an acceptable staleness window is a separate decision.

This cache also does not persist data across program restarts. Creating a new cache object starts with an empty map. Do not use this example in place of durable storage or treat it as the sole copy of data that must be preserved.

### 8.4. get Can Modify the Order Structure

`LinkedHashMap` is not synchronized for concurrent access. In access-order mode in particular, `get` can modify the order links. You cannot split operations into "reads need no protection, only `put` does" and assume the map is safe when used by multiple threads.

If multiple threads are needed, every path accessing the related state must be coordinated under a consistent design. Merely adding a synchronized wrapper around individual `get` and `put` calls does not make the entire **check-miss → load → insert** sequence atomic. Two threads can both observe a miss and both load the same key.

The programs here run in a single thread and provide no mechanism for coalescing concurrent loads, canceling tasks, or handling in-flight loads. Do not infer those guarantees just because the cache has LRU ordering. When moving to concurrent requirements, revisit the contract before choosing locking and how loading work is executed.

### 8.5. Iterating the Map and Calling get on It Is a Trap

In an access-ordered map, iterating `keySet()` with an iterator and calling `get(key)` on the same map can alter the order while the iterator is running. That can lead to `ConcurrentModificationException`, even in a single-threaded program.

The iterator's fail-fast mechanism only makes a best effort to detect structural modification; do not use the presence or absence of an exception as a concurrency-safety test. If an entry is already in the newest position, some calls may not change the order; do not infer from one working case that the iteration pattern is safe.

When you only need to inspect key-value pairs in a single thread, you can iterate `entrySet()` and read `entry.getKey()` / `entry.getValue()` to avoid triggering `get` accesses on the map. When the cache API returns a copy of the key order as in the example, calling `clear` on the copy does not modify the cache. However, if you then use each key from the copy to call `cache.get`, those calls will still refresh entries in the real cache. Having a copy avoids a backed view; it does not turn `get` into an operation that leaves LRU untouched.

## 9. How to Test an LRU Cache

### 9.1. Check Both Data and Order

A good test must observe the policy itself, not just the entry count. With a limit of three, the sequence `put(A)`, `put(B)`, `put(C)`, `get(A)`, `put(D)` must satisfy:

- A is still present and D is in the cache.
- B is no longer in the cache.
- The final order is `[C, A, D]`.
- The final entry count is three.

If you only check the entry count, a FIFO cache with the wrong policy can also pass. If you only compare two maps with `Map.equals`, the comparison checks mappings, not LRU order. Likewise, comparing two key sets does not verify order. When order must be checked, convert it to a `List` and compare lists in the exact expected order.

Avoid accidentally mutating the very state under test: calling `get` to check the existence of a batch of keys refreshes each entry in call order. You can use `containsKey` to check presence/absence without refreshing, and use the copied order list to verify LRU. If you intentionally test the effect of `get`, account for that effect in the expected result.

### 9.2. Edge Cases Worth Testing

| Case | Expected result under the article's cache classes | Bug it can catch |
|---|---|---|
| Insert up to the limit | Keeps the full allowed number of entries | Using `>=` instead of `>` |
| Insert a new key beyond the limit | Evicts the current head entry | Missing hook override or wrong condition |
| Successfully read an old key | Moves that entry to newest | Forgetting `accessOrder=true` |
| Read a missing key | Returns `null`, creates no entry | Mixing reads with inserting a default value outside the contract |
| `containsKey` on an old entry | Does not change order | Misunderstanding that all lookups refresh |
| `put` an existing key | Updates and refreshes without increasing entry count | Treating every `put` as a new-key insertion |
| Limit of 0 | After `put`, cache is empty | Failing to define caching-disabled configuration clearly |
| Negative limit | Constructor throws `IllegalArgumentException` | Letting configuration errors surface later at runtime |
| `null` key/value in the wrapper | Throws before mutating the map | Letting `null` in and making hit/miss ambiguous |
| Clearing the copied key list | Cache is unchanged | Exposing a map-backed view |

In on-demand loading, counting how many times the loader actually runs is useful evidence: the sequence `a, b, a, c, b` at limit two must load four times, not three times (distinct keys) and not five times (total requests).

The `size() <= maximumEntries` invariant of this design holds after public insertion operations finish normally. Inside the hook itself, the map can temporarily have `maximumEntries + 1` entries. An assertion that fails simply upon seeing that temporary size would contradict the insert-then-evict mechanism being used.

### 9.3. Cost of Operations

With a suitable hash distribution, basic operations such as `get` and `put` take constant average time under the hash-table model. Maintaining order and evicting the head entry do not require scanning the entire cache in this policy. That is one reason `LinkedHashMap` is well suited for demonstrating a small LRU cache.

However, not every method on the wrapper has the same cost. `keysLruToMru()` copies `n` keys into a new list, taking time and memory proportional to `n`. The full-order print lines in the examples are for observation; they also traverse the data. The loader has its own cost, which may be much greater than a map lookup.

Do not turn the observation "average `get`/`put` is fast" into a guarantee that every operation has fixed latency. Hash quality, data size, allocation, table resizing, and data-loading work can all affect actual cost.

## 10. Common Mistakes and Targeted Fixes

| Wrong code or reasoning | Why it is wrong | How to handle it |
|---|---|---|
| `new LinkedHashMap<>(3)` is a three-entry cache | `3` is the requested initial capacity | Keep a separate limit and eviction rule |
| Enabling `accessOrder=true` creates a bounded cache | It only maintains access order | Override the hook according to the limit |
| Right hook, but using the default constructor | The head entry is oldest by insertion order | Enable access mode if you want LRU |
| `size() >= maximumEntries` | The new entry is already in the map when the hook runs | Use `size() > maximumEntries` |
| Every `get` invokes the hook | Reads can change order, but do not add a new entry | Distinguish recency updates from eviction checks |
| `put` of an old key always creates a new entry | The existing key's mapping is updated | Consider insertion and update paths separately |
| Manually `remove` and return `true` | Mutating the map and asking it to evict again has unspecified behavior | In this pattern, return only the decision |
| Evicting an LRU entry deletes source data | A cache only holds copies or recomputable results | Separate caching from source storage |
| Entries unread for a long time expire automatically | There is no timer in this LRU mechanism | Do not attach TTL guarantees to the cache |
| Locking only `put` and leaving `get` unlocked across threads | `get` can modify access order | Design coordination for the entire state |
| Using `null` both as data and as a miss signal | `get == null` can no longer distinguish the two cases | Choose a clear value policy or result type |
| Comparing key sets to verify LRU | A set does not encode order in equality | Compare an ordered list |

## 11. Self-Check

1. Why is `removeEldestEntry` with insertion order not enough to make an LRU cache?
2. With a limit of three, when the hook is called after inserting the fourth key, what is `size()`?
3. Why does the `>=` condition cause a cache with a limit of one entry to retain no entries after `put`?
4. Do `get` finding an entry and `containsKey` finding an entry have the same effect on LRU?
5. Does updating an existing key's value with `put` increase the entry count? Can it change the order?
6. Does a single `true` return clean up all excess entries down to a sharply reduced limit?
7. Why does the wrapper check for non-`null` before calling `entries.put`?
8. Can a cache with a limit of 0 return the newly loaded result for the current request?
9. Why does synchronizing `get` and `put` individually not guarantee that a key has only one in-flight load?
10. With a two-entry cache, how many loads does the request sequence `x, y, x, z, y` require, and what is the final order?

### Answers and Reasoning

1. Insertion order does not change when A is read again. Evicting the head entry will evict the earliest-inserted entry, even if it was just used. LRU needs access order so that the head entry reflects the least recently used entry.
2. Four. The new entry has already been added; the hook decides whether to evict the head entry to return to three.
3. The first entry produces `size=1`; `1 >= 1` is true, so it is evicted immediately. The correct condition `1 > 1` is false, so that entry is kept.
4. No. A successful `get` makes the entry the newest; `containsKey` does not refresh access order.
5. It does not increase the entry count. In an access-ordered map, `put` on an existing key still makes that entry the newest; there is no new insertion to trigger the hook on the insertion path.
6. No. One `true` decision requests removing the single `eldest` entry. A fixed-limit design only needs one eviction after each insertion; changing the limit dynamically requires a dedicated shrinking mechanism.
7. So invalid input is rejected before any mutation and before risking the eviction of a valid entry. It also preserves the contract that `null` from `get` means a miss.
8. Yes. The method can load, attempt to store, and return the computed result. The cache does not retain the entry afterward, so the next request must load again.
9. Two threads can check in turn and both observe a miss before either writes the result. A multi-step sequence requires its own coordination contract; locking individual calls does not combine them into one atomic step.
10. Four loads: `x`, `y`, `z`, and then `y` again. The orders after each request are `[x]`, `[x, y]`, `[y, x]`, `[x, z]`, `[z, y]`. The second use of `x` is a hit; `y` was evicted when `z` was added.

## 12. Practice with Expected Results

### Exercise 1: Confirming the Boundary Bug

In a copy of the hook-observation program, change the condition to `size() >= maximumEntries` and run with a limit of three. Before running, predict which keys remain after inserting A, B, and C. The result should leave only B and C: A was evicted as soon as the size reached three. Then restore the correct condition and confirm the map keeps A, B, and C.

The point is to understand when the condition is evaluated, not to add a special branch for the third insertion. The same `>` condition must handle limits of 0, 1, and larger.

### Exercise 2: Separating Observation and Usage

With a limit of two, insert A and B, call `containsKey("A")`, and then insert C. Predict that A is evicted and the remaining order is `[B, C]`. Repeat from an empty map, replacing `containsKey("A")` with `get("A")`; this time B is evicted and the remaining order is `[A, C]`.

The two trials must initialize separate caches so they share the same starting point. Continuing on a cache already mutated by the previous trial will no longer reflect the single difference between the two methods.

### Exercise 3: Tracing the Existing-Key Update Path

With a limit of two, insert `A=a`, `B=b`, and then `put("A", "a2")`. Confirm the size is still two, the order is `[B, A]`, and A's value is `a2`. Then insert C and confirm B is evicted. If you use `get("A")` to check the value, note that the call is also an access; at this point A is already newest, so the observed order stays the same.

### Exercise 4: Proving Eviction Does Not Lose the Source

In the on-demand loading program, keep a loader that can recompute the same result for the same key. Run the sequence `a, b, a, c, b` and verify that `b` is loaded twice yet returns `B` both times. Data leaves the cache and is recomputed; the load count increases, while the meaning of the result does not change.

The completion criterion is being able to explain why a request hits, why one misses, and which entry must leave the cache at each step. Merely seeing the program run without errors does not prove the LRU policy is correct.

## 13. References and Runtime Environment

The programs in this article use Java 17-compatible syntax and APIs. They were compiled with `javac --release 17 -encoding UTF-8` and run on JDK 24.0.2; the stdout above is the verified output from those runs. Each file contains only one `public` class matching the file name, with no external library dependencies.

- [LinkedHashMap — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html): insertion/access order, access-producing operations, timing and contract of `removeEldestEntry`, synchronization and iterator limitations.
- [Map — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): mapping contract, meaning of `get`, `null` values, equality, and views.
- [Objects.requireNonNull — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T,java.lang.String)): checking that input references are non-`null`.
