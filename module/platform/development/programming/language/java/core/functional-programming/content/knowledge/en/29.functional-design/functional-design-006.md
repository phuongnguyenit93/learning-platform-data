# Considering Memoization and Conditions to Avoid Altering Behavior

In functional design (*functional design*), a computation may be called multiple times with the same input. If the computation is CPU-intensive, allocates memory, or runs a complex algorithm, **storing the result for reuse**—often called *memoization*—can reduce repeated work. However, not every function is safe to cache.

What matters is not just “same parameters means cacheable”, but rather: **does replacing the computation call with a stored value preserve the behavior observed by users and the rest of the program?** If the output depends on time, external state, login session info, changing configuration, or mandatory side effects, wrong caching can turn a correct program into a buggy one.

Conceptual example:

~~~java
int first = expensiveSquare(4);  // Computes 16.
int second = expensiveSquare(4); // Also yields 16 if the function is stable.
~~~

If `expensiveSquare` truly depends only on the number 4 and has no mandatory side effects, the second call can receive 16 from the cache. Conversely, a `getStock("SKU-1")` function reading current inventory from a database **cannot** be cached forever just because the SKU parameter stays the same.

The goal of this lesson is to understand **when memoization is valid, how to choose the right cache key and value, and how to handle data changes, concurrency, errors, and memory**, while keeping the design easy to test.

## 1. Memoization, Caching, and Referential Transparency

A pure mathematical function `f(x)` can be replaced by its result `y = f(x)` anywhere without changing the meaning of the program. This property is related to **referential transparency** (*referential transparency*).

Example function:

~~~java
static int square(int n) {
    return Math.multiplyExact(n, n);
}
~~~

With `n = 4`, it always returns 16; for inputs that cause integer multiplication overflow, it always throws `ArithmeticException` by the same rule. The function does not read the clock, network, or external mutable variables. Therefore, memoizing **successful results** can be equivalent in terms of return value.

**Memoization** typically caches results by **a function's arguments**, right next to the computation. **Caching** is a broader concept: it can cache HTTP responses, query results, business objects, or datasets shared across components. Both must answer questions about validity, scope, expiration, and invalidation.

Basic processing flow:

~~~text
Call f(x)
   |
   v
Build cache key K(x)
   |
   +---- Valid entry exists? -- Yes ---> Use stored result
   | 
   No
   |
   v
Compute f(x)
   |
   v
Decide whether to store the result
   |
   v
Return result to caller
~~~

“An entry exists” **does not** automatically mean “the entry is still correct”. A cached entry may exist yet be stale, belong to another user's permissions, or use old configuration. Validation rules must reflect the business contract.

### Decision Questions

Suppose there are two calls to `f(x)` at different times. Ask yourself:

1. Is **all data affecting the result** represented in `x` or in a corresponding immutable context?
2. Is the result allowed to be reused across time, user sessions, and access permissions?
3. Does the call have mandatory **side effects** that must execute every time?
4. Can arguments and return values be mutated via references?
5. When a computation fails or returns `null`, what is the caching policy?
6. Are memory, storage/lookup overhead, and concurrent access requirements reasonable?

If the answers are still vague, there is not yet enough basis to add caching to the function.

## 2. Pure Functions and the Boundary of “Same Input”

A **pure function** has two important characteristics:

- No observable side effects: does not modify a database, increment a business counter, send emails, write files, or mutate program state.
- For the same meaningful input, returns **the same result**, independent of external state not described in the parameters.

Good example:

~~~java
static long subtotal(long unitPriceCents, int quantity) {
    return Math.multiplyExact(unitPriceCents, (long) quantity);
}
~~~

The output is determined by the two input values, according to the semantics and `long` bounds of overflow-checked multiplication.

Cases that are **impure or only conditionally pure**:

~~~java
// Impure: current time changes.
Instant currentTime() {
    return Instant.now();
}

// Impure: stateful random generator.
int nextRoll(Random random) {
    return random.nextInt(1, 7);
}

// Impure: external source can change.
long currentBalance(String accountId) {
    return repository.loadBalance(accountId);
}
~~~

This is **illustrative code**, not a standalone program; it requires imports and a suitable `repository` object. These functions may be completely valid business choices, but they cannot be cached based solely on explicit parameters and assumed equivalent.

### Hidden Dependencies Break Caching

A calculation may look like a pure function:

~~~java
long finalPrice(String sku) {
    return priceCatalog.get(sku) * currentExchangeRate;
}
~~~

But the result depends on both the price catalog and the current exchange rate. If cached by `sku` while data changes, the result goes stale.

A more controllable design is to push dependencies into explicit input data:

~~~java
record PriceInput(long baseCents, int quantity, int taxBasisPoints) {}

static long taxCents(PriceInput in) {
    long subtotal = Math.multiplyExact(in.baseCents(), in.quantity());
    return Math.multiplyExact(subtotal, in.taxBasisPoints()) / 10_000L;
}
~~~

This code is a deterministic arithmetic operation on `PriceInput`. However, **rounding, tax, and overflow policies** must still be defined by the business domain. Never switch to a different formula just for caching convenience.

Self-contained inputs make caching easier to verify. Still, if tax logic or regulation versions change while the cache remains alive, the algorithm/configuration version may also need to be part of the key or trigger cache invalidation.

## 3. Memoizing with `Map.computeIfAbsent()`

In Java, a concise way to cache non-null results by key is:

~~~java
Map<Integer, Integer> cache = new HashMap<>();

Function<Integer, Integer> memoizedSquare =
        n -> cache.computeIfAbsent(n, k -> Math.multiplyExact(k, k));
~~~

This is an illustrative snippet in a **sequential context**, requiring `Map`, `HashMap`, `Function`. `computeIfAbsent` only invokes the mapping function when the key is not associated with a non-null value; if the mapping function returns a non-null result, the Map stores it for reuse.

In multithreaded environments, `HashMap` is generally **unsafe** for concurrent modification and lookup. Do not use the snippet above as a shared cache across parallel calls without synchronization.

### When Shared Across Multiple Threads

You can replace it with `ConcurrentHashMap`:

~~~java
ConcurrentHashMap<Integer, Integer> cache = new ConcurrentHashMap<>();

Function<Integer, Integer> memoizedSquare =
        n -> cache.computeIfAbsent(n, k -> Math.multiplyExact(k, k));
~~~

`ConcurrentHashMap.computeIfAbsent` has an atomic per-key update contract when computing the mapping. It suits scenarios where multiple threads share a cache; once a value is stored, subsequent calls receive that result.

That **does not** solve every caching problem:

- The cache can still hold **stale results** if external dependencies change.
- The Map can still grow **unbounded** without a capacity policy.
- If the computation is slow, related operations may suffer contention. Mapping functions should be short and never recursively update the same map.
- If the cache stores mutable objects, multiple callers can receive **the exact same reference** and mutate it.
- **Do not** cache side effects just because `computeIfAbsent` avoids duplicate computation.

### Why Should the Mapping Function Not Modify the Same Map?

The mapping function in `computeIfAbsent` should focus on producing a value for the requested key. Do not perform recursive updates on the same Map inside the mapping function; especially with `ConcurrentHashMap`, recursive updates can throw errors or deadlock depending on the situation/contract.

Do not treat `computeIfAbsent` as a complete caching system with TTL, quotas, metrics, circuit breakers, or automatic refresh: JDK `ConcurrentHashMap` **does not provide those policies out of the box**.

## 4. Java 17+ Example with Verified Behavior

The following program illustrates three things:

1. Memoization of a numeric computation by `Integer` key.
2. Multi-attribute keys using an immutable `record`.
3. `null` results are not stored by `ConcurrentHashMap.computeIfAbsent`.

Save file **`MemoizationDemo.java`**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;
import java.util.stream.Stream;

public class MemoizationDemo {
    record TaxInput(long subtotalCents, int taxBasisPoints) {}

    public static void main(String[] args) {
        AtomicInteger computations = new AtomicInteger();
        ConcurrentHashMap<Integer, Integer> squares = new ConcurrentHashMap<>();
        Function<Integer, Integer> square = n -> squares.computeIfAbsent(n, k -> {
            computations.incrementAndGet();
            return Math.multiplyExact(k, k);
        });

        System.out.println("results=" + Stream.of(4, 4, 5, 4).map(square).toList());
        System.out.println("computations=" + computations.get());
        System.out.println("cache=" + new TreeMap<>(squares));

        ConcurrentHashMap<TaxInput, Long> taxCache = new ConcurrentHashMap<>();
        Function<TaxInput, Long> tax = input -> taxCache.computeIfAbsent(input,
                k -> Math.multiplyExact(k.subtotalCents(), k.taxBasisPoints()) / 10_000L);
        System.out.println("tax1=" + tax.apply(new TaxInput(10_000L, 800)));
        System.out.println("tax2=" + tax.apply(new TaxInput(10_000L, 800)));
        System.out.println("tax3=" + tax.apply(new TaxInput(10_000L, 500)));
        System.out.println("taxKeys=" + taxCache.size());

        AtomicInteger misses = new AtomicInteger();
        Map<String, String> missingCache = new ConcurrentHashMap<>();
        Function<String, String> nullable = k -> missingCache.computeIfAbsent(k, key -> {
            misses.incrementAndGet();
            return null;
        });
        System.out.println("missing1=" + nullable.apply("unknown"));
        System.out.println("missing2=" + nullable.apply("unknown"));
        System.out.println("missingCalls=" + misses.get());
        System.out.println("missingSize=" + missingCache.size());
    }
}
~~~

Compile/run with JDK 17:

~~~bash
javac MemoizationDemo.java
java MemoizationDemo
~~~

**Exact stdout:**

~~~text
results=[16, 16, 25, 16]
computations=2
cache={4=16, 5=25}
tax1=800
tax2=800
tax3=500
taxKeys=2
missing1=null
missing2=null
missingCalls=2
missingSize=0
~~~

Analysis:

- `Stream.of(4, 4, 5, 4)` has four elements, but squaring is executed for only two distinct keys: 4 and 5. The output list still preserves all four positions from the source.
- `computations` is **an illustrative counter for how many times the algorithm ran**, not a mandatory business side effect. If the caller requires a side effect on every call, memoization **is not equivalent**; this very example shows the core invocation count changes.
- `new TreeMap<>(squares)` is used to print the cache in deterministic key order; `ConcurrentHashMap` does not guarantee order when printed directly.
- Two `TaxInput(10_000L,800)` instances are two records with equal values, so they share the same cache key and get 800 cents. `TaxInput(10_000L,500)` produces a different key, giving 500 cents. Omitting `taxBasisPoints` from the key would risk applying the wrong tax rate.
- `missingCache` does not accept `null` values from the mapping function. Two lookups for `"unknown"` both execute the lookup attempt, so `missingCalls=2` and the cache size remains 0.

The code was compiled with `javac --release 17` and executed to verify all stdout. It does not depend on timing, parallel execution order, or random values, so the output can be matched exactly.

## 5. Cache Keys Must Capture All Inputs Affecting the Result

A cache can be viewed as a mapping:

~~~text
cacheKey -> cachedResult
~~~

Necessary condition: **if two calls use the same cache key, they must be allowed to share the same result** under the application's contract. This is stronger than two arguments “looking similar”.

For example, calculating a final price needs these attributes:

~~~java
record PriceKey(
        String sku,
        String currency,
        String customerTier,
        int discountBasisPoints,
        long priceCatalogVersion
) {}
~~~

This is an **illustrative type declaration**. Which fields are needed must be based on actual pricing rules. If `customerTier` is omitted when promotional pricing depends on tier, the cache will serve one tier's price to another. If `priceCatalogVersion` is omitted when the catalog changes, the cache can go stale.

### Records as Keys

Java records automatically generate `equals`/`hashCode` from their components (using each component type's semantics). They are often well-suited for value-based cache keys:

~~~java
record TaxKey(long subtotalCents, int rateBasisPoints) {}

TaxKey first = new TaxKey(10_000L, 800);
TaxKey second = new TaxKey(10_000L, 800);

boolean same = first.equals(second); // true
~~~

However, a record **does not automatically deep-freeze** objects referenced by its components. If a record contains a mutable `List`, a `byte[]` array, a stateful config object, or a mutable collection, the key can still be unstable.

### Why Are Mutable Keys Dangerous?

Anti-pattern example:

~~~java
// Do not use objects whose hashCode depends on mutable state as Map keys:
List<String> key = new ArrayList<>(List.of("A"));
Map<List<String>, Integer> cache = new HashMap<>();
cache.put(key, 10);
key.add("B");
// Key hash/equality may have changed after insertion.
// cache.get(key) is no longer guaranteed to find the old entry as expected.
~~~

This is an illustrative snippet inside a method with `List`, `ArrayList`, `Map`, `HashMap` imported. Mutating a key object after insertion breaks hash-based Map assumptions. The right approach is to use an immutable value type or snapshot the key (e.g., `List.copyOf` with immutable elements) before storing.

For keys containing arrays, default array `equals` compares references, not contents; design a value object or compare elements explicitly if array contents form the logical identity.

## 6. Cached Results Must Have a Mutability-Safe Contract

Suppose a function returns `List<String>`, and the cache stores that List directly:

~~~java
Map<String, List<String>> cache = new HashMap<>();

List<String> result = cache.computeIfAbsent("team-A",
        key -> new ArrayList<>(List.of("An", "Binh")));
result.add("Chi"); // Mutated the very object sitting inside the cache.
~~~

This is an illustrative snippet, not a recommended API. A subsequent call for the same key may receive the mutated List. If the business logic expects each call to return an independent list, caching by returning **the same mutable reference** changes behavior.

Some strategies:

- **Immutable values:** keep returned data as `String`, `Integer`, records with immutable components, or truly immutable structures. Returning the same value object is usually low-risk.
- **Unmodifiable snapshot:** if elements are suitable, store `List.copyOf(computedList)`; callers cannot `add/remove` on the returned List, though you still must check whether **inner elements** are mutable.
- **Defensive copy:** store an unmodifiable or private copy in the cache; on each call return `new ArrayList<>(cached)` when the contract expects callers to receive an independent mutable collection.
- **Deep copy when needed:** for object graphs with mutable nodes, a shallow copy does not protect data. Design immutable values or copy according to domain semantics.

Do not silently change an API from “returns a new mutable List each time” to “returns a shared unmodifiable List” just to optimize, if callers are permitted to mutate the result. **Behavioral compatibility** includes mutability and object identity when the contract allows observing them.

## 7. Side Effects Make Memoization Non-Equivalent

Consider:

~~~java
int processPayment(String paymentId) {
    paymentGateway.charge(paymentId);
    auditLogger.record(paymentId);
    return 1;
}
~~~

This is **illustrative code**, not a standalone program. If cached by `paymentId` and subsequent calls are skipped, the payment charge or audit logging may **not happen**. In payment processing, avoiding duplicate charges may be the right requirement, but it must be expressed via **idempotency keys, transaction protocols, and persisted payment state**, not by silently memoizing a side-effecting function.

Often-overlooked side effects:

1. Writing audit logs or incrementing mandatory counters.
2. Updating “last accessed” or recording business-required telemetry.
3. Emitting events, sending notifications, sending emails.
4. Database reads with locks that synchronize or check permissions at access time.
5. Reading random numbers, clocks, or auto-increment sequences.
6. Mutating internal state of the target object.

Even when **the return value** is identical, reducing the number of executions can alter observable user behavior. Separate pure computation from side-effecting parts before caching:

~~~text
Business call
   |
   +--> Authorization check / audit / mandatory action (every time per contract)
   |
   +--> Pure computation expensive(input) (memoizable if conditions hold)
   |
   +--> Return result per contract
~~~

Do not dismiss logging as an “unimportant side effect”: some systems require audit logs for compliance. Whether reducing log entries is allowed must be a business decision.

## 8. Time, External Data, and Invalidation Policies

Memoizing a pure function can often live as long as the function itself, but many business caches are only valid **for a time window or data version**.

Example:

~~~java
long stock(String sku) {
    return warehouseRepository.currentStock(sku);
}
~~~

The result depends on warehouse state, so the same `sku` at two different times may differ. Caching indefinitely would be wrong. Common strategies:

| Strategy | When Appropriate | Limitations |
| --- | --- | --- |
| No caching | Must always read the latest value | Higher load on source |
| TTL (time-based expiration) | Stale data is acceptable within a defined window | TTL does not guarantee strict freshness |
| Invalidate on source change | Reliable update signals exist | Easy to miss or delay events |
| Version in key | Data has an explicit revision | Old keys still consume memory |
| Request-scoped cache | Only need reuse within one request | Not shared across requests |
| Session / tenant-scoped cache | Reuse within a clear permission boundary | Must manage scope and cleanup |
| Immutable snapshot | Result is determined by a stable revision | Needs a mechanism to create/hold snapshots |

**TTL is an agreement on acceptable staleness**, not proof that data is always accurate. If inventory or price must be exact at transaction decision time, even a short cache may be insufficient; use proper read/write protocols and consistency checks.

When changing algorithms, tax configs, locales, or data versions, check whether old entries remain valid. Updating code while keeping a persistent cache under old keys can cause results from a different algorithm version to be served.

## 9. Cache Scope and Access Control: Same Technical Key Is Not Enough

Suppose two users both call `getDiscount("SKU-1")`, yet the discount depends on membership tier. If cached only by SKU, another user could receive wrong or sensitive information.

Conditions for sharing a cache across callers:

- Is the result **truly independent of identity, permissions, and tenant**?
- Does the key include all required contextual attributes?
- Can an entry outlive the validity of access permissions?
- Is an authorization check required **on every call**, even on a cache hit?
- Does the cache store personal data, tokens, or secrets that must be protected or invalidated?

Do not put sensitive information directly into loggable keys, URLs, or observability tools just for caching convenience. Use non-secret internal IDs and partition the cache according to the permission model.

**Important:** a cache hit must never become a bypass around access control if policy requires checking permissions on every request. Separate authorization from the cacheable pure computation.

## 10. Caching `null`, Missing Results, and Exceptions

### `ConcurrentHashMap` Does Not Allow Null Values

`ConcurrentHashMap` rejects `null` as a key or value. With `computeIfAbsent`, if the mapping function returns `null`, no mapping is created:

~~~java
ConcurrentHashMap<String, String> cache = new ConcurrentHashMap<>();

String first = cache.computeIfAbsent("missing", key -> null);
String second = cache.computeIfAbsent("missing", key -> null);
// Both are null and key "missing" is not written into the Map.
~~~

This is an illustrative snippet requiring `ConcurrentHashMap` imported. If querying a missing result is expensive, consecutive calls will keep repeating the lookup.

### Negative Caching When Business Rules Allow

To explicitly represent **“searched and confirmed absent”**, you can store a non-null wrapper value:

~~~java
ConcurrentHashMap<String, Optional<String>> cache = new ConcurrentHashMap<>();

Optional<String> result = cache.computeIfAbsent(
        "missing",
        key -> Optional.empty()
);
~~~

This snippet requires `ConcurrentHashMap` and `Optional` imported. `Optional.empty()` is a **non-null object value**, so it can be stored; it represents an absent result. However, negative caching also needs an expiration policy: data “not found” today might be created tomorrow.

### Should Exceptions Be Cached?

If the mapping function in `computeIfAbsent` throws a `RuntimeException` or `Error`, no mapping is created by the failed call. Subsequent calls may recompute and throw again.

For transient errors (network timeout, rate limit), retrying can help, though it also risks creating heavy load. For deterministic errors (invalid input), consider early validation or caching an error state **if the contract permits**, rather than accidentally changing exception behavior.

Distinguish clearly:

- **No valid result** — a data state.
- **Not found** — may be a business outcome and can change over time.
- **Transient error** — not equivalent to missing data.
- **Permanent input error** — should be validated and represented clearly.

Never cache all exceptions forever under a generic “error value”: that can prevent the system from recovering after a temporary outage.

## 11. Concurrency: A Thread-Safe Cache Does Not Make the Cached Function Safe

Using `ConcurrentHashMap` helps manage mappings from multiple threads. It **does not** make a side-effecting function pure, protect returned mutable objects, or fix stale data.

Example:

~~~java
ConcurrentHashMap<String, MutableResult> cache =
        new ConcurrentHashMap<>();

MutableResult a = cache.computeIfAbsent("A", this::compute);
MutableResult b = cache.get("A");

// a and b can be the exact same mutable object.
~~~

This is **illustrative code**, where `MutableResult` and `compute` are application-defined components. If multiple threads mutate `a` and `b`, races can occur inside the object even though the map is thread-safe.

### `computeIfAbsent` Is Not a System-Wide Lock

Within one JVM, `ConcurrentHashMap.computeIfAbsent` provides atomic per-key computation/insertion per its contract. However, if the application runs across multiple instances or processes, each instance has its own Map; the same work can still run concurrently on different nodes.

If a side effect **must happen only once** system-wide, you need an appropriate idempotency/transaction/coordination protocol. Do not use local memoization as a substitute for distributed transaction correctness.

For asynchronous tasks, caching `CompletableFuture<R>` can help share in-flight work within a scope, but you must design cancellation, timeouts, error handling, removing failed entries, and sharing future ownership. That is a more complex lifecycle problem than caching integer results.

### Parallel Streams and Memoization

~~~java
List<Integer> values = source.parallelStream()
        .map(memoizedFunction)
        .toList();
~~~

This is an illustrative snippet with `source` and `memoizedFunction` defined beforehand. If the cache uses a plain `HashMap` and lambdas update it concurrently, there is a data race risk. Use an appropriate thread-safe implementation when multiple threads access it.

Also note that Streams use **lazy evaluation** and may optimize away calling certain behavioral parameters in suitable pipelines. If the caller requires an exact number of side-effect executions, do not attach side effects to `map` and rely on caching or non-caching to control call counts.

## 12. Cache Size, Eviction, and Real Costs

Caching avoids recomputation, but also costs:

- Memory to store keys, values, and metadata.
- Hashing, key comparison, locking/synchronization, and lifetime management overhead.
- Entry construction time, retaining objects over time, and garbage collector pressure.
- Invalidation or synchronization costs with the source.

A `ConcurrentHashMap` storing every input ever seen can grow without bound. When the key space is large (user IDs, request IDs, timestamps…), reuse rates are low, and a cache easily **costs more than it saves**.

Questions to ask before enabling a cache:

1. How expensive is recomputation?
2. How often is a key repeated within a useful window?
3. What is the unique key count and per-entry size?
4. Does the cache live for one request, one thread, one JVM, or the whole system?
5. Do results expire or get invalidated by events/versions?
6. When memory is tight, can old entries be evicted and recomputed without breaking the contract?
7. How will latency, throughput, hit rate, miss rate, and memory/GC be measured?

JDK `ConcurrentHashMap` is a concurrent map; it **does not natively provide TTL, entry limits, or eviction policies**. If the system needs those features, use a dedicated caching library evaluated as suitable or design a well-tested policy; do not tack clumsy TTL checks onto multithreaded operations.

### Do Not Cache Just Out of Fear of Calling a Function Often

A very cheap function like `n -> n + 1` can be faster than hashing and a map lookup. When elements almost never repeat, memoization only increases memory usage. Effectiveness should be based on **hit rate and actual computation cost**, not an assumption that “a Map lookup is always cheap”.

## 13. Testing Behavioral Equivalence

Before accepting a cache, clearly define what **must remain identical** between the original and memoized versions. Valuable test groups:

| Scenario | What to Verify |
| --- | --- |
| Same input multiple times | Return value is correct; recomputation skipped only when allowed |
| Two different inputs | Do not accidentally share a key |
| Multiple records with equal values | `equals/hashCode` make them share the valid key |
| Mutable input | Not mutated after insertion into cache, or properly snapshotted |
| Mutable result | Caller cannot corrupt cache, or receives independent copy per contract |
| Source data update | Invalidation/version/TTL applies properly |
| Not found | Negative caching policy is clear |
| Mapping function returns null | Not confused with a cached entry |
| Mapping function throws | Error is not hidden or cached in a bad state |
| Concurrent callers | No races in map or values; results are accurate |
| Different permissions/tenants | Data is not reused beyond allowed scope |
| Large data / many keys | Memory does not grow unbounded |
| Config/algorithm change | Old entries are not used once invalidated |

A good testing workflow can include:

1. Run the original and cached computations on the same input suite, comparing **values and exceptions per contract**.
2. Call the same key multiple times; use instrumentation that does not affect business results to observe cache hits/misses.
3. Intentionally vary each attribute affecting the result to verify the key has enough dimensions.
4. Simulate config/source updates and verify invalidation.
5. For concurrency, run multithreaded tests and appropriate race-detection tools; one passing run is not proof of safety.
6. Measure with warm-up benchmarks on representative data; if using JMH, avoid dead-code elimination and measure allocation/GC cost too.

**Do not treat matching output from a single run as proof that caching preserves behavior.** Security state, update timing, errors, object identity, and side effects may only surface across many requests or concurrent threads.

## 14. Safer Design Patterns

### Pattern A: Separate Pure Computation from I/O

~~~text
Service layer:
  1. Read latest data / check permissions per business rules.
  2. Convert into an immutable input snapshot.
  3. Call pureCalculation(snapshot), memoizable with a complete key.
  4. Write audit / emit events if required on every request.
~~~

The pure computation can be cached without skipping steps required by the service contract. If the snapshot changes version, keys or invalidation must update accordingly.

### Pattern B: Request-Scoped Cache

Within a single request, computations or lookups that are immutable for the request's scope can use a local Map, reducing staleness across requests and multithreaded synchronization overhead. However, if the request runs parallel subtasks, the local Map may still need thread safety depending on how it is shared.

### Pattern C: Versioned Keys

~~~java
record CalculationKey(String productId, long ruleVersion, int quantity) {}
~~~

When `ruleVersion` changes, the new key does not accidentally hit old entries. However, old entries still need cleanup to prevent memory leaks; versioning alone is not eviction.

### Pattern D: Immutable Results or Defensive Copies

The cache holds immutable values. If callers need a new mutable List, return a copy after reading from the cache. Check element contents too; `new ArrayList<>(cached)` only copies **references**, not deep-copying each object.

### Pattern E: Do Not Memoize on Hot Paths If Lookup Costs More Than Computation

For simple arithmetic and mostly unique data, having no cache is an intentional and right choice. Optimize only when profiling and tests demonstrate a benefit.

## 15. Common Mistakes and How to Spot Them

**Caching a time-dependent function:** `Instant.now()`, system date, “current price”, or “current status” are not stable under old keys. Include the timestamp/snapshot in the model or accept a clearly bounded TTL.

**Forgetting a parameter that affects the result:** Caching only by `sku` when price also depends on currency, customer, and price-list version. Missing key fields return wrong results across contexts.

**Using mutable keys:** Mutating an object after inserting it into a hash map can make the entry unfindable. Use immutable keys with stable `equals/hashCode`.

**Returning the same mutable object:** Caller A mutates the cached List, causing Caller B to receive altered data. Prefer immutable values or defensive copies per contract.

**Confusing null with uncomputed:** `computeIfAbsent` does not store null in `ConcurrentHashMap`. To remember “not found”, use a value explicitly representing absence along with an expiration policy.

**Caching every exception:** A temporary timeout should not turn into permanent “no data”. Classify errors and design retries/backoff.

**Using `HashMap` with `parallelStream()`:** Concurrent updates to the map usually cause races. Use synchronization or `ConcurrentHashMap` per contract, and review value state as well.

**Attaching a cache to a side-effecting function:** Sending emails, charging payments, auditing, or incrementing business counters may need to run every time; a cache hit skips them. Separate side effects from pure calculation.

**Unbounded global caches:** High-cardinality inputs can make the heap grow forever. Design quotas, eviction, TTL, or shorter scopes.

**Assuming deterministic results are always cacheable:** A function may always return `true` while also writing an audit record every time. A deterministic return value is not enough; consider all observable behavior.

**Using a cache to “patch” impure results:** If a function returns varying data due to hidden dependencies, caching just hides the bug. First fix dependencies and data contracts.

## 16. Decision Checklist Before Memoizing a Function Result

| Question | If the Answer Is “No” or “Unclear” |
| --- | --- |
| Does the function have stable output given full inputs? | Do not cache under the current key yet |
| Does the function have no mandatory side effects? | Extract the pure part; keep side effects running each time |
| Does the key include all attributes and versions affecting output? | Expand the key or add invalidation |
| Is the key immutable with stable `equals/hashCode`? | Snapshot or change key type |
| Can the value be shared safely? | Return immutable values or defensive copies |
| Is there a policy for `null` and missing values? | Design a state-wrapping value |
| Is there a policy for exceptions/retries? | Distinguish transient, permanent, and input errors |
| Does the cache have the right scope and access control? | Partition by tenant/request or do not cache |
| Does the cache meet required thread safety? | Choose the right Map/concurrency model |
| Are there expiration rules and memory bounds? | Add lifecycle/eviction |
| Is there measurement data proving benefit? | Consider not caching |

**Conclusion:** Memoization is a very useful technique when **the computation is pure, inputs are complete and immutable, and results are reusable**. To avoid altering behavior, never rely solely on two calls having the same explicit parameters. You must check **hidden dependencies, side effects, object mutability, access permissions, stale data, `null`/exceptions, concurrency, and memory lifecycle**. Only store results when replacing the computation with a cache hit still satisfies the system's contract.
