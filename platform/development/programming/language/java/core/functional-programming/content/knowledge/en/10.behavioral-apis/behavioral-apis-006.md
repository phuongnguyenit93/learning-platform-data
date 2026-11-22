# Map.computeIfAbsent(), compute(), and merge(): Passing Value-Handling Behavior in Java

## Learning Objectives

The three methods `Map.computeIfAbsent()`, `Map.compute()`, and `Map.merge()` accept **functions as arguments** to decide the value associated with a key. They replace many sequences of operations like `containsKey` → `get` → `put` with an API that directly expresses the update rule. Although they have similar syntax, **when the lambda is called, the input values, and how `null` is handled differ significantly**.

After this lesson, you can:

- Choose the right API when you need on-demand initialization, recomputing from an old value, or accumulating/combining a new value.
- Read the signatures and clearly identify the function descriptors of `Function` and `BiFunction`.
- Predict when the callback is invoked and when it is **not** invoked, including when the key has a `null` value.
- Explain how returning `null` avoids adding or removes a mapping, while distinguishing **absent key** from **key currently pointing to null**.
- Properly handle cases where a lambda throws an exception, mutable data, and concurrent updates.
- Write, run, and verify a Java 17 program with deterministic output.

## 1. Map Accepts Behavior Instead of Only Values

`Map<K,V>` is an interface mapping keys of type `K` to values of type `V`. In `java.util.Map`, the three methods are declared conceptually as follows:

```java
V computeIfAbsent(
        K key,
        Function<? super K, ? extends V> mappingFunction);

V compute(
        K key,
        BiFunction<? super K, ? super V, ? extends V> remappingFunction);

V merge(
        K key,
        V value,
        BiFunction<? super V, ? super V, ? extends V> remappingFunction);
```

These are **simplified signatures for learning the API**, not standalone code to place in a class. The functional interfaces belong to `java.util.function`. A `null` value is used to express a special state according to each method's contract; how `null` is handled also depends on the specific Map implementation.

Core differences:

| API | What does the lambda receive? | When is the lambda called? | If the lambda returns `null` |
| --- | --- | --- | --- |
| `computeIfAbsent(key, f)` | `key` | When the key has no mapping **or currently maps to `null`** | Does not record a new value; an existing `null` mapping may still remain |
| `compute(key, f)` | `key`, `oldValue` | For the requested key, whether a previous value exists or not | Removes the mapping if present; if absent, adds nothing |
| `merge(key, value, f)` | `oldValue`, `value` | Only when the key currently has a **non-`null` value** | Removes the mapping |

`merge` also requires that the `value` parameter and `remappingFunction` **must not be `null`**. It uses `value` directly to create the mapping when there was no previous non-`null` value, so it does not invoke the remapping function in that branch.

**Important note:** `Map` is an interface. Some implementations allow `null` keys or values, such as `HashMap` and `LinkedHashMap`; `ConcurrentHashMap` allows neither `null` keys nor `null` values. Furthermore, guarantees regarding synchronization and the number of function executions may differ across implementations.

## 2. computeIfAbsent(): Create a Value Only When Needed

### 2.1. Syntax and Execution Flow

```java
Map<String, Integer> cache = new HashMap<>();

Integer length = cache.computeIfAbsent(
        "Java",
        key -> key.length()
);
```

This is an illustrative snippet that requires importing `java.util.Map` and `java.util.HashMap` and placing it inside a valid method. `Function<? super K, ? extends V>` has a function descriptor equivalent to `(K) -> V` in the context of a typed Map. With `Map<String,Integer>`, `key` has type `String`, and the `int` result from `length()` is boxed into an `Integer`.

Scenarios:

1. If the key **has no mapping**: calls `mappingFunction.apply(key)`. If it returns a non-null value, stores the value and returns it.
2. If the key **already maps to null** and the Map permits `null`: also calls the mapping function; if it returns non-null, replaces the null value with the new value.
3. If the key **already has a non-null value**: returns the old value, **without calling** the mapping function.
4. If the mapping function returns `null`: does not create a new mapping. If the key previously had a `null` mapping, that mapping is not automatically removed just because the function returned null.

The last point is easy to misunderstand. `computeIfAbsent` does not mean "if not found, always add an entry". Only a **non-null** result is stored as the new value.

### 2.2. Null Values and Non-Existent Keys

```java
Map<String, String> names = new HashMap<>();
names.put("Mai", null);

names.computeIfAbsent("Mai", key -> "Mai Anh");
System.out.println(names.get("Mai")); // Mai Anh

names.computeIfAbsent("Lan", key -> null);
System.out.println(names.containsKey("Lan")); // false
```

Here the Map initially has key `"Mai"` with value `null`, so the callback for `"Mai"` is still called. For `"Lan"`, which does not exist, the callback returns null and the key is not added.

If you need to determine accurately whether a key is present, `containsKey` has a different meaning from `get(key) == null` when the Map permits null values. `get` returns null in both cases: when the key is absent and when the key has a null mapping.

### 2.3. Application: On-Demand Collection Initialization

```java
Map<String, List<String>> groups = new HashMap<>();

groups.computeIfAbsent("java", key -> new ArrayList<>())
      .add("Lan");
groups.computeIfAbsent("java", key -> new ArrayList<>())
      .add("Mai");
```

This is an illustrative snippet that requires importing `Map`, `List`, `HashMap`, and `ArrayList`. The first call with `"java"` creates a new list; the next call reuses the existing list. The expected result at `groups.get("java")` is `[Lan, Mai]`.

However, the list here is **mutable**. If multiple threads add elements concurrently, the thread safety of the Map does not guarantee safety when calling `List.add`. To handle concurrency, you must design synchronization for the value structure as well, not just the Map.

## 3. compute(): Deciding the New Value from Key and Old Value

`compute` accepts a `BiFunction<? super K, ? super V, ? extends V>`. With `Map<String,Integer>`, the lambda can be written as:

```java
points.compute("Mai", (key, oldValue) -> {
    return oldValue == null ? 1 : oldValue + 1;
});
```

This is illustrative code; `points` must be declared with type `Map<String,Integer>` beforehand.

**Contract:**

- The callback receives the **key** as its first parameter.
- The callback receives the **old value** as its second parameter.
- If there is no mapping yet, or the old mapping is null, `oldValue` is passed as null.
- If the callback returns a **non-null** value, the Map associates the key with that value and returns the new value.
- If the callback returns `null`, the mapping is **removed if present**, or not added if it was previously absent.

Because `oldValue == null` represents both "key does not exist" and "key has value null", if your logic needs to distinguish between these two cases, looking at `oldValue` alone is not enough. When you must read external state inside the callback, consider consistency and concurrency rather than assuming a separate `containsKey` check is updated atomically.

### 3.1. Updating or Initializing with a Single Rule

```java
Map<String, Integer> visits = new HashMap<>();

visits.compute("article-1",
        (key, old) -> old == null ? 1 : old + 1);
visits.compute("article-1",
        (key, old) -> old == null ? 1 : old + 1);

// visits.get("article-1") is 2.
```

`compute` invokes the remapping function on both calls. Checking `old == null` handles the case where there is no value initially.

### 3.2. Removing a Mapping with a Null Result

```java
Map<String, Integer> quota = new HashMap<>();
quota.put("Mai", 5);

quota.compute("Mai", (key, old) -> null);
System.out.println(quota.containsKey("Mai")); // false
```

This is an intentional convention of the API, not a "lost data" bug. If `null` represents a business value that must be preserved, you should choose an appropriate wrapper type or Map structure and avoid arbitrarily returning null from the callback.

**Choose `compute` when:** the formula needs both `key` and the old value; you want a single extension point to handle all states; or you may want to remove the mapping conditionally.

## 4. merge(): Combining a New Value with an Existing Value

`merge` is well suited for accumulating counts, summing amounts, concatenating strings, or combining results by key.

```java
Map<String, Integer> counts = new HashMap<>();

counts.merge("java", 1, Integer::sum);
counts.merge("java", 1, Integer::sum);
counts.merge("java", 1, Integer::sum);

// counts.get("java") is 3.
```

With `Map<String,Integer>`, the `value` parameter here is `1`. When there is no non-null value yet, the Map inserts `1` directly; on subsequent calls, `Integer::sum` receives the old value and `1` to add them together.

### 4.1. The Remapping Function Parameters Do Not Include the Key

`merge(key, value, (oldValue, newValue) -> result)` has the descriptor `(V,V) -> V`, **with no `key` parameter in the callback**.

Example:

```java
Map<String, String> messages = new HashMap<>();

messages.merge("errors", "E1", (oldText, incoming) ->
        oldText + "," + incoming);
messages.merge("errors", "E2", (oldText, incoming) ->
        oldText + "," + incoming);

// messages.get("errors") is "E1,E2".
```

If the combining rule needs to read the key to make a decision, `compute(key, (key, old) -> ...)` may be more suitable. `merge` already receives the new value as a method argument, so the absent-mapping branch does not need to call the callback to produce that value.

### 4.2. The Three Cases of merge

| State before call | Behavior of `merge(k, v, f)` |
| --- | --- |
| Key `k` is absent | Associates `k -> v`; does not call `f` |
| `k` currently maps to null (for Maps allowing null) | Associates `k -> v`; does not call `f` |
| `k` currently maps to a non-null value `old` | Calls `f.apply(old, v)`, stores result if non-null; if it returns null, removes the key |

`v` **must not be null**, and `f` must not be null either. Notably, the argument `v` is evaluated by Java **before calling the method**. Therefore:

```java
// Illustration: expensiveValue() is an external method.
map.merge("key", expensiveValue(), (oldValue, incoming) ->
        combine(oldValue, incoming));
```

Even if the remapping function is skipped because the key is absent, `expensiveValue()` is still evaluated to pass as the `value` argument. It is not a lazy supplier. If you only want to create an expensive value when the key is missing, `computeIfAbsent` or another design may be more appropriate.

### 4.3. Removing with Null

```java
Map<String,Integer> counts = new HashMap<>();
counts.put("java", 5);

counts.merge("java", 1, (oldValue, incoming) -> null);
System.out.println(counts.containsKey("java")); // false
```

Do not confuse a null **`value` argument** with a null **callback result**: passing `value = null` is invalid; returning null from the remapping function means removing the mapping when the callback is invoked.

## 5. Decision Table: Which API to Use?

| Business need | Suitable API | Why |
| --- | --- | --- |
| Retrieve cached data, loading only when no value exists | `computeIfAbsent` | Calls the initializer function only when needed |
| Initialize a list and add an element for a key | `computeIfAbsent` | Creates the collection when missing, then operates on the returned collection |
| Modify a value based on both key and old value | `compute` | Callback receives `key` and `oldValue` |
| Set/remove a mapping based on a rule that may return null | `compute` | Callback is invoked with the current state |
| Increment a counter by key | `merge(k,1,Integer::sum)` | Absent-key branch uses `1` directly |
| Combine an incoming external value into an existing one | `merge` | Callback receives the old and new values |
| Only need to read an existing value | `get` or `getOrDefault` | No need to pass an update callback into the Map |
| Update with a fixed value without recomputing | `put` or `replace` depending on condition | Simpler contract |

There is no single "best" method for every situation. Choose based on **when the callback is needed**, the arguments actually required, and the meaning of `null`.

## 6. Complete Java 17 Program

This is a complete runnable example using `LinkedHashMap` so the output order is deterministic, while also demonstrating `ConcurrentHashMap.merge` for accumulation.

Create the file **`MapCallbacksDemo.java`**:

```java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

public class MapCallbacksDemo {
    public static void main(String[] args) {
        Map<String, Integer> scores = new LinkedHashMap<>();
        scores.put("Mai", null);

        AtomicInteger loads = new AtomicInteger();
        int first = scores.computeIfAbsent("Mai", key -> {
            loads.incrementAndGet();
            return 10;
        });
        int second = scores.computeIfAbsent("Mai", key -> {
            loads.incrementAndGet();
            return 99;
        });
        System.out.println("computeIfAbsent: " + first + ", " + second
                + ", loads=" + loads.get());
        System.out.println("Map: " + scores);

        Integer updated = scores.compute("Mai",
                (key, old) -> old == null ? 0 : old + 5);
        System.out.println("compute: " + updated);

        Integer merged = scores.merge("Mai", 7, Integer::sum);
        System.out.println("merge existing: " + merged);

        Integer newValue = scores.merge("Lan", 3, Integer::sum);
        System.out.println("merge new: " + newValue + ", map=" + scores);

        scores.compute("Lan", (key, old) -> null);
        System.out.println("after compute null: " + scores);

        scores.merge("Mai", 1, (oldValue, incoming) -> null);
        System.out.println("after merge null: " + scores);

        Integer absent = scores.computeIfAbsent("Unknown", key -> null);
        System.out.println("absent null: " + absent
                + ", contains=" + scores.containsKey("Unknown"));

        scores.put("Nullable", null);
        scores.computeIfAbsent("Nullable", key -> null);
        System.out.println("existing null mapping: "
                + scores.containsKey("Nullable") + "/" + scores.get("Nullable"));

        ConcurrentHashMap<String, Integer> counts = new ConcurrentHashMap<>();
        for (int i = 0; i < 3; i++) {
            counts.merge("clicks", 1, Integer::sum);
        }
        System.out.println("counts: " + counts);
    }
}
```

Compile with JDK 17 or later:

```bash
javac MapCallbacksDemo.java
java MapCallbacksDemo
```

**Exact stdout:**

```text
computeIfAbsent: 10, 10, loads=1
Map: {Mai=10}
compute: 15
merge existing: 22
merge new: 3, map={Mai=22, Lan=3}
after compute null: {Mai=22}
after merge null: {}
absent null: null, contains=false
existing null mapping: true/null
counts: {clicks=3}
```

### 6.1. Step-by-Step Analysis

1. `scores.put("Mai", null)` creates a mapping with key `"Mai"` but no actual value yet. `LinkedHashMap` accepts null values.
2. `computeIfAbsent("Mai", ...)` sees the value is null, invokes the function, increments `loads` to `1`, and stores `10`. The second call sees `10` and therefore **does not call** the function; `loads` remains `1`. Both `first` and `second` are `10`.
3. `compute("Mai", ...)` receives `key = "Mai"` and `old = 10`, returns `15`; the Map stores `15`.
4. `merge("Mai", 7, Integer::sum)` receives old value `15` and new value `7`, returning `22`.
5. `merge("Lan", 3, Integer::sum)` has no old value, so it stores `3` directly without calling `Integer::sum`. `LinkedHashMap` preserves insertion order: `Mai` then `Lan`.
6. `compute("Lan", ..., null)` returns null, removing the `Lan` mapping.
7. `merge("Mai", 1, (old,incoming) -> null)` runs the callback because `Mai` currently has `22`; the null result removes the `Mai` mapping, leaving the Map empty.
8. `computeIfAbsent("Unknown", key -> null)` does not add a new mapping. `containsKey("Unknown")` is `false`.
9. `Nullable -> null` is inserted into the Map. The callback again returns null, so **the existing null mapping remains**. Hence the final line prints `true/null`.
10. `ConcurrentHashMap` with key `"clicks"` is summed three times using `merge` and yields `3`. This example runs sequentially; it does not prove that the program handles all concurrency issues if values are complex or callbacks have side effects.

The program uses types and APIs available in Java 17, has a filename matching the `public class`, and has no network or external data dependencies. To display Vietnamese diacritics in comments and accompanying exercises, the terminal environment should use UTF-8; the main example output uses ASCII characters and can be compared directly.

## 7. When Callbacks Throw Exceptions or Cause Side Effects

All three APIs accept lambdas that may fail at runtime. If a callback throws an **unchecked exception**, the method call may terminate with that exception and no normal return value. With standard implementations and the API contract, the mapping associated with the failed operation is not updated to a new result. However, if the callback modifies external objects on its own, **those side effects are not automatically rolled back**.

Example:

```java
// Illustration: cache is an already declared Map<String,Integer>.
cache.compute("key", (key, old) -> {
    auditLog.add("attempt " + key); // side effect outside the Map
    throw new IllegalStateException("failed");
});
```

This snippet is not standalone: `cache` and `auditLog` must be declared. If an exception occurs, the line adding to `auditLog` has already executed. You should not treat `compute` as a transaction that automatically rolls back all external changes.

Another pitfall: the standard functional interfaces `Function.apply` and `BiFunction.apply` **do not declare checked exceptions** like `IOException` or `SQLException`. If a lambda calls an API that throws a checked exception, you must handle it inside, wrap it into an unchecked exception according to business policy, or move the I/O out of the callback. Declaring `throws IOException` on the outer calling method does not automatically extend the contract of `Function`.

### 7.1. Avoid Mutating the Same Map Inside the Callback

Code like:

```java
// DO NOT do this: modifying the Map itself from inside the remapping callback.
map.compute("k", (key, old) -> {
    map.put("other", 123);
    return 456;
});
```

Risks breaking the assumptions of the update algorithm. Java documentation requires that callbacks not modify the Map itself while computing a mapping. For non-concurrent Maps, some implementations may detect this and throw `ConcurrentModificationException`; for concurrent Maps, the behavior may be blocked or cause recursive update errors. Do not write logic that relies on this "happening to work" on a particular runtime version.

If you need to update multiple keys under a consistent rule, design a separate coordinated operation with appropriate synchronization/transactions for your data types and environment. `compute` only expresses computing a single mapping per key, not turning the entire Map into a multi-key transaction.

### 7.2. Callbacks Should Be Short and Have Minimal Side Effects

A concise callback like `Integer::sum` is easy to reason about. Callbacks that write logs, send emails, or make REST calls may be invoked at unexpected times; in a concurrent environment, they may have to deal with retries or cross-thread interactions. Separate pure computations from I/O tasks whenever possible.

## 8. Concurrency: Regular Maps vs. ConcurrentHashMap

**Do not assume** `Map.computeIfAbsent`, `Map.compute`, or `Map.merge` have the same atomicity guarantees across all implementations.

### 8.1. HashMap/LinkedHashMap

`HashMap` and `LinkedHashMap` do not provide concurrent update safety merely because they are called via `compute`. If multiple threads operate on them simultaneously, proper synchronization or a concurrent implementation is required; sequences like `get` → `put` are even more prone to lost updates.

For example, two threads both reading `0` and both writing `1` can lose an increment. Moving the logic into `compute` on a non-thread-safe Map does not fix the problem on its own.

### 8.2. ConcurrentHashMap

`ConcurrentHashMap` implements these update methods with atomicity guarantees for per-key mapping operations according to its own contract. With `computeIfAbsent`, determining/establishing the mapping for a key is performed atomically; other updates may be blocked while the computation is running. With `compute` and `merge`, the specific update is also synchronized according to the concurrent Map's contract.

`ConcurrentHashMap` **does not allow `null` as a key or value**. Therefore, you cannot try `put("Mai", null)` on it as in the `LinkedHashMap` example. A null result from a mapping function generally means not establishing a mapping (or removing the mapping when specified by the method), not storing a null value.

```java
java.util.concurrent.ConcurrentHashMap<String, Integer> counts =
        new java.util.concurrent.ConcurrentHashMap<>();

counts.merge("views", 1, Integer::sum);
counts.merge("views", 1, Integer::sum);
System.out.println(counts.get("views")); // 2
```

This is a valid illustrative snippet when placed inside a method. If multiple threads increment the same key, `ConcurrentHashMap.merge` is preferable to an unsynchronized read-then-write loop.

**Points to be careful about:**

- Computation inside the callback should be **short and simple**; do not hold update operations for long when many threads are contending.
- Do not update the same Map from within the callback that is computing a mapping. With `ConcurrentHashMap`, recursive updates can throw `IllegalStateException` if detected.
- Do not implicitly treat the callback as a mechanism that executes I/O exactly once over the entire application lifecycle: mapping removals, errors, or subsequent calls can cause the computation to run again.
- Atomicity of the mapping in `ConcurrentHashMap` does not automatically make **mutable value objects** (such as an `ArrayList` stored in the Map) thread-safe.

If a system needs to aggregate many counters at very high frequency, you can consider `LongAdder` combined with `computeIfAbsent` per key, while still understanding the value lifecycle and how to read counts consistently.

## 9. Edge Cases to Remember

### 9.1. Map Containing a Key with a Null Value

With `HashMap`:

```java
Map<String,Integer> map = new HashMap<>();
map.put("k", null);
```

- `map.get("k")` is null, yet `map.containsKey("k")` is true.
- `computeIfAbsent("k", key -> 7)` replaces null with `7`.
- `compute("k", (key, old) -> old == null ? 5 : old + 1)` receives `old = null` and can write `5` if called when no value is present.
- `merge("k", 2, Integer::sum)` writes `2` without calling `Integer::sum` if the previous value was null.

The lines above are **separate cases to analyze**, not a sequential series of operations on the same Map if you want each line to start from `k -> null`.

### 9.2. Callback Returning Null

| Call | When the key is absent | When the key has a non-null value |
| --- | --- | --- |
| `computeIfAbsent(k, key -> null)` | Does not add | Does not call lambda, returns old value |
| `compute(k, (key, old) -> null)` | Does not add | Removes mapping |
| `merge(k, v, (old, incoming) -> null)` with `v != null` | Adds `v`, callback does not run | Removes mapping |

This table does not replace considering the case where "the key currently maps to null"; in that state `computeIfAbsent` calls the function, `compute` receives `old=null`, and `merge` uses `v` directly.

### 9.3. Lambdas Receive Different Information

`computeIfAbsent` receives `key` but not the old value; `compute` receives both `key` and `old`; `merge` only receives the two values `old`/`incoming` (no direct `key`). If you choose the wrong API, you may have to capture external state unnecessarily, making the code harder to test.

### 9.4. When Creating a New Value from Expensive Data

`computeIfAbsent("key", k -> load(k))` is one way to call `load` only when no value exists yet. `merge("key", load("key"), combiner)` will **call `load` to evaluate the argument** before entering `merge`, even if an old value already exists. Consider both the cost and the number of invocations; do not assume every API accepting a lambda is lazy.

## 10. Common Mistakes and How to Avoid Them

1. **Confusing "absent" with "key not present".** `computeIfAbsent` treats a current null value as a case that needs recomputing; `containsKey` is what distinguishes whether a key is present if the Map permits null values.
2. **Using `computeIfAbsent` when you always want to update.** When a non-null value already exists, the callback will not run. Use `compute` or `merge` as needed.
3. **Using `compute` and forgetting `oldValue` can be null.** When the key is absent or points to null, `oldValue` is null; `oldValue + 1` will cause an unboxing NPE.
4. **Confusing the parameter order of `merge`.** The `merge` callback receives `(oldValue, incoming)`, **not `(key, oldValue)`**.
5. **Passing a null value to `merge`.** The API requires a non-null `value` argument; do not use null to signal deletion. To delete conditionally, the callback can return null when it is invoked.
6. **Assuming `null` always has the same meaning.** In `computeIfAbsent`, null means do not set a new value; in `compute` and the remapping branch of `merge`, null can remove the mapping.
7. **Assuming Map default methods are always atomic.** There is no such general guarantee on regular Maps; you must choose the right implementation and synchronization.
8. **Causing side effects on the same Map inside the callback.** This easily causes reentrancy errors or implementation-dependent undefined results; avoid doing this.
9. **Hiding slow or non-idempotent I/O in a callback.** This can cause delays, errors, contention, and require separate retry rules.
10. **Forgetting mutable values.** A `Map<String,List<Item>>` using `computeIfAbsent` does not make the `List` thread-safe.
11. **Assuming callbacks can throw arbitrary checked exceptions.** `Function`/`BiFunction` do not declare checked exceptions; you must catch/handle them according to the contract.
12. **Choosing `merge` for every update.** When the logic truly depends on the key, `compute` usually expresses the intent better.

## 11. Practice Exercises

1. Given `Map<String,Integer> map = new HashMap<>()`, predict how many times `computeIfAbsent("a", k -> 5)` runs its callback if called twice in a row without modifying the Map.
2. Suppose `map.put("a", null)` on a `HashMap`. When calling `computeIfAbsent("a", k -> 7)`, is the callback invoked? What are `containsKey("a")` and `get("a")`?
3. Given `map.put("b", 2)`, call `compute("b", (k,old) -> old * 3)`. What is the new value of `"b"`? What happens if the callback returns null?
4. Write a `merge` expression that increments the visit count for key `"home"` by 1, starting when the Map does not have the key yet.
5. In `merge("k", 10, (oldValue, incoming) -> oldValue - incoming)`, which value is `old` and which is `incoming`? Does the callback run when `"k"` currently maps to null?
6. Why does `merge("k", expensive(), f)` still call `expensive()` before knowing whether the Map has an old value?
7. If you use `ConcurrentHashMap<String, List<String>>` and `computeIfAbsent` returns an `ArrayList`, is it automatically safe for multiple threads to call `add` concurrently?
8. A `compute` callback calls `map.put` on the same Map. Why should this be avoided, especially on implementations with concurrency support?
9. For a `Map<String,Integer>` that can contain null, distinguish `get("x") == null` from `containsKey("x") == false`.
10. Suppose a `merge` callback returns null when the sum exceeds a threshold. Explain the new state of the key if it previously had a non-null value, and compare it to when the key did not exist.

**Answer Hints:** (1) Once, if the first call returns `5`; the second call reads the existing value. (2) Yes, because the old value is null; the results are `true` and `7`. (3) `6`; returning null removes the mapping. (4) `map.merge("home", 1, Integer::sum)`. (5) `oldValue` is the existing Map value, `incoming` is `10`; when the Map value is null, the callback does not run and the Map receives `10` directly. (6) Java evaluates arguments before calling the method. (7) No; the List structure needs its own synchronization mechanism. (8) It conflicts with the remapping process and may be detected and throw an error. (9) `get==null` covers both missing keys and keys with a null value; `containsKey==false` confirms the key is absent. (10) Returning null in the remapping branch removes the mapping; for a non-existent key, `merge` inserts the input value and does not call the callback.

## Conclusion

`Map.computeIfAbsent()`, `Map.compute()`, and `Map.merge()` are clear examples of **Java APIs accepting behavior via functional interfaces**. The decisive differences lie in **the callback's inputs, the conditions under which it is called, and the meaning of a null result**:

- **`computeIfAbsent`:** initializes when there is no non-null value yet.
- **`compute`:** recomputes from the key and old value in all cases.
- **`merge`:** combines an existing value with a new value, or uses the new value directly when there is no non-null value yet.

To apply them safely in real applications, determine the Map implementation, concurrency requirements, side effects, exception handling, and value mutability before choosing an API. Writing a short lambda is no substitute for understanding the update contract.
