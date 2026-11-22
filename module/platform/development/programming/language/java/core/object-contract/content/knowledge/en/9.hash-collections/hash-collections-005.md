# Duplicate Keys and Replaced Values When Calling `Map.put()`

When working with hash data structures in Java, `Map.put(key, value)` is not simply "adding an element". If the map **does not yet have an equivalent key**, the operation creates a new mapping. If the map **already has an equivalent key**, the operation **replaces the value associated with the existing key**. This is a crucial behavior of `HashMap` and is the foundation for understanding why two key objects with different identities can still represent the same entry.

For example: after `scores.put("java", 10)`, calling `scores.put("java", 20)` changes the value of key `"java"` to `20`, the entry count does not increase, and the second call returns the old value `10`. To understand this fully, we need to clarify **how duplicate keys are determined**, **how `hashCode` and `equals` cooperate**, **what `put` returns**, and **how `null` changes how results are interpreted**.

## 1. Meaning and Basic Contract of `Map.put()`

General declaration of the method in the `Map<K, V>` interface:

~~~java
V put(K key, V value);
~~~

`put` associates a `value` with `key`; if the map previously contained a mapping for this key, the new value replaces the old value. The return value is the **previous value** for the key, or `null` if there was no previous mapping; a `null` can also mean **the previous value itself was `null`** in maps that allow `null`.

| State before `put(k, v)` | After the call | Return value | Map size |
| --- | --- | --- | --- |
| No key equivalent to `k` | Creates mapping `k → v` | `null` | Increases by 1 |
| Already has `k → old`, `old != null` | Changes to `k → v` | `old` | Unchanged |
| Already has `k → null` and map allows null values | Changes to `k → v` | `null` | Unchanged |

`put` is a mutating operation. Not every `Map` implementation supports it: for instance, a map created with `Map.of(...)` cannot be modified, so calling `put` throws `UnsupportedOperationException`. The examples in this lesson mainly use a **modifiable `HashMap`**.

With `HashMap`, **each distinct key by `equals` has only one entry**, regardless of how many times a value is reassigned to that key. Replacing a value **does not** increase the size. Conversely, adding a new key increases `size()` even if the new value equals another key's value: uniqueness applies to the **key**, not the **value**.

## 2. Two Independent Key Objects Can Still Be Considered Duplicate Keys

A common misconception is thinking only references to the same object (`==`) can replace the same entry. With `HashMap`, keys are located via hash and checked for equality via `equals`. Thus, **two independent objects** can represent **the same logical key**, provided `equals`/`hashCode` are properly defined.

Suppose `ProductKey` identifies a product by `sku`. Two `ProductKey("P-01")` instances are created separately yet represent the same product code. A `record` in Java 17 automatically generates `equals` and `hashCode` based on the `sku` component.

File **`MapPutDemo.java`**, standalone runnable on Java 17+:

~~~java
import java.util.HashMap;
import java.util.Map;

public class MapPutDemo {
    record ProductKey(String sku) {}

    public static void main(String[] args) {
        Map<ProductKey, String> products = new HashMap<>();

        ProductKey first = new ProductKey("P-01");
        ProductKey sameValue = new ProductKey("P-01");
        ProductKey other = new ProductKey("P-02");

        System.out.println(first == sameValue);
        System.out.println(first.equals(sameValue));
        System.out.println(first.hashCode() == sameValue.hashCode());

        System.out.println(products.put(first, "Draft"));
        System.out.println(products.put(other, "Active"));
        System.out.println(products.size());

        System.out.println(products.put(sameValue, "Published"));
        System.out.println(products.size());
        System.out.println(products.get(first));
        System.out.println(products.get(sameValue));
        System.out.println(products.get(other));

        System.out.println(products.put(first, "Archived"));
        System.out.println(products.get(sameValue));
        System.out.println(products.size());
    }
}
~~~

Compile and run:

~~~bash
javac MapPutDemo.java
java MapPutDemo
~~~

Exact output:

~~~text
false
true
true
null
null
2
Draft
2
Published
Published
Active
Published
Archived
2
~~~

Explanation of each group of results:

1. `first == sameValue` is `false` because these are two independently created instances. Yet `first.equals(sameValue)` is `true` because both records have the same `sku`. When `equals` is `true`, the contract requires their corresponding `hashCode` values to be equal.
2. `put(first, "Draft")` and `put(other, "Active")` both return `null` because there was no corresponding mapping beforehand. The map now has **2 entries**.
3. `put(sameValue, "Published")` returns **`"Draft"`**, which is the old value of key `"P-01"`. Although `sameValue` does not share a reference with `first`, they are equal under `ProductKey`'s contract, so the entry is updated without creating a third entry. `size()` remains `2`.
4. Both `get(first)` and `get(sameValue)` return `"Published"`. `get(other)` still returns `"Active"` because `"P-02"` is a separate key.
5. `put(first, "Archived")` returns `"Published"`. Afterward, `get(sameValue)` returns `"Archived"` and the size remains `2`.

Core point: **`put` decides "whether a key already exists" according to the map's key semantics**, not simply based on whether the key variable is a newly created object.

### At which step does the hash code participate?

In `HashMap`, the hash code helps locate the candidate group to look up. Next, the map must check key equality to know which candidate represents the same logical key. For a normal key class:

- If `k1.equals(k2) == true`, then `k1.hashCode() == k2.hashCode()` is **mandatory**. If violated, `put` or `get` may fail to find the equivalent entry.
- `k1.hashCode() == k2.hashCode()` **does not imply** `k1.equals(k2)`. Two distinct keys are still allowed to share a hash; `HashMap` must distinguish them.

Details such as bucket count, bit mixing, or internal structure under collisions are implementation details. What application code should rely on is **the key contract** and the documented `Map` behavior, not assumptions about bucket locations.

## 3. Duplicate Keys Differ From Hash Collisions

The two strings `"Aa"` and `"BB"` have the **same** `String.hashCode() == 2112`, yet are not equal in content. When inserting them sequentially into `HashMap`, **both entries remain present**.

~~~java
Map<String, Integer> scores = new HashMap<>();

scores.put("Aa", 10);
scores.put("BB", 20);

System.out.println("Aa".hashCode() == "BB".hashCode()); // true
System.out.println("Aa".equals("BB"));                  // false
System.out.println(scores.size());                      // 2
System.out.println(scores.get("Aa"));                   // 10
System.out.println(scores.get("BB"));                   // 20
~~~

The snippet above is illustrative code placed **inside a method**, with `import java.util.HashMap;` and `import java.util.Map;` if compiled separately. Comments reflect exact Java output.

If you continue with `scores.put(new String("Aa"), 30)`, only the value of the entry for key `"Aa"` changes to `30`; the `"BB"` entry keeps `20`, and the size remains `2`. This is **duplicate key by `equals`**, which differs from **duplicate hash code**.

| Case | `equals` of the two keys | Hash code | `put` into `HashMap` |
| --- | --- | --- | --- |
| Two `ProductKey("P-01")`s | `true` | Must be equal | Later key updates value of old entry |
| `"Aa"` and `"BB"` | `false` | Both equal `2112` | Keeps two separate entries |
| `"P-01"` and `"P-02"` | `false` | May differ or match | Keeps two separate entries |

**Do not use `hashCode` as a unique key identifier** in business logic. If you replace `Map<ProductKey, ...>` with `Map<Integer, ...>` storing only the key's hash, you may cause unequal keys to be mistakenly merged.

## 4. Return Value of `put` and the `null` Trap

With `HashMap`, you can store a **`null` key** and **`null` values**. This creates a subtlety: looking only at a `null` return value from `put` is **not enough to tell** whether a new key was just added or an old value that happened to be `null` was just replaced.

File **`MapNullAndCollisionDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class MapNullAndCollisionDemo {
    public static void main(String[] args) {
        Map<String, String> states = new HashMap<>();

        System.out.println(states.put("task", null));
        System.out.println(states.containsKey("task"));
        System.out.println(states.size());

        System.out.println(states.put("task", "Queued"));
        System.out.println(states.size());
        System.out.println(states.get("task"));

        System.out.println(states.put("task", "Done"));
        System.out.println(states.get("task"));
        System.out.println(states.containsKey("missing"));
        System.out.println(states.get("missing"));

        Map<String, Integer> numbers = new HashMap<>();
        System.out.println(numbers.put(null, 1));
        System.out.println(numbers.put(null, 2));
        System.out.println(numbers.size());
        System.out.println(numbers.get(null));

        numbers.put("Aa", 10);
        numbers.put("BB", 20);
        System.out.println("Aa".hashCode() == "BB".hashCode());
        System.out.println(numbers.size());
        System.out.println(numbers.get("Aa"));
        System.out.println(numbers.get("BB"));
    }
}
~~~

Compile and run:

~~~bash
javac MapNullAndCollisionDemo.java
java MapNullAndCollisionDemo
~~~

Exact output:

~~~text
null
true
1
null
1
Queued
Queued
Done
false
null
null
1
1
2
true
3
10
20
~~~

Interpretation:

- Calling `states.put("task", null)` on an empty map returns `null`, **yet the map now contains key `"task"`**: `containsKey("task")` is `true`, `size() == 1`.
- Calling `states.put("task", "Queued")` also returns `null`, this time because **the old value was `null`**. This is a **replacement**, so the size remains `1`.
- Calling `states.put("task", "Done")` returns `"Queued"`; `get("task")` is `"Done"`.
- For key `"missing"`, `containsKey` is `false`, while `get` is `null`. Therefore, you should not use `get(k) == null` alone to conclude a key does not exist in a map that permits `null` values.
- In `HashMap`, a `null` key is accepted. The call `put(null, 2)` replaces `put(null, 1)`, returns `1`, and the `numbers` map still has only one entry before adding the two strings.
- `"Aa"` and `"BB"` share the same hash code yet differ in `equals`, so both are added to `numbers`; together with the `null`-key entry, the total is **3 entries**.

If you need to know for sure whether a key already existed **before calling** `put`, you can use `containsKey` prior to the operation:

~~~java
boolean existedBefore = states.containsKey("task");
String previous = states.put("task", "Reviewed");
~~~

This is an example for distinguishing before/after state **in a simple single-threaded flow without concurrent updates**. In a multithreaded program, the `containsKey` followed by `put` pair **does not form an atomic operation**; you must use an implementation/construct supporting synchronization or appropriate atomic operations when needed. Additionally, some `Map`s do not allow `null` keys or values: `Map.of` does not accept `null`; `ConcurrentHashMap` also does not accept `null` keys/values. Do not generalize the `HashMap` example to every `Map` implementation.

## 5. How Do `put`, `putIfAbsent`, and `replace` Differ?

These three methods have different intents:

| Method | Primary behavior |
| --- | --- |
| `put(k, v)` | Writes value `v` whether the key is absent or already present; if already present, replaces the old value. |
| `putIfAbsent(k, v)` | Only sets the value when there is no mapping, or the key currently maps to `null` per `Map`'s default contract. |
| `replace(k, v)` | Only replaces if the key already has a mapping; does not create an entry when the key does not exist yet. |

File **`MapUpdateVariantsDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class MapUpdateVariantsDemo {
    public static void main(String[] args) {
        Map<String, String> map = new HashMap<>();

        System.out.println(map.putIfAbsent("A", "First"));
        System.out.println(map.putIfAbsent("A", "Second"));
        System.out.println(map.get("A"));

        System.out.println(map.replace("B", "Ignored"));
        System.out.println(map.containsKey("B"));

        System.out.println(map.replace("A", "Updated"));
        System.out.println(map.get("A"));

        map.put("C", null);
        System.out.println(map.containsKey("C"));
        System.out.println(map.putIfAbsent("C", "Filled"));
        System.out.println(map.get("C"));
    }
}
~~~

Compile and run:

~~~bash
javac MapUpdateVariantsDemo.java
java MapUpdateVariantsDemo
~~~

Exact output:

~~~text
null
First
First
null
false
First
Updated
true
null
Filled
~~~

The call `putIfAbsent("A", "Second")` does not replace the existing `"First"`. The call `replace("B", "Ignored")` does not create key `"B"`. In `HashMap`, when `"C"` currently exists with value `null`, `putIfAbsent("C", "Filled")` can still write `"Filled"`, whereas `put("C", "Filled")` always writes regardless of the old value. Read the specific method contract when you need to distinguish unconditional update, insert-only, replace-only, or atomic updates in concurrent environments.

## 6. Ensuring Keys Have Suitable `equals` and `hashCode`

If you use a custom-defined object as a key, you must accurately identify the fields representing the key's **logical** identity. For instance, two `InvoiceKey`s with the same `invoiceNumber` are considered the same key in the application; they must be equal by `equals`, and also have the same `hashCode`.

File **`InvoiceKeyDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class InvoiceKeyDemo {
    static final class InvoiceKey {
        private final String invoiceNumber;

        InvoiceKey(String invoiceNumber) {
            this.invoiceNumber = Objects.requireNonNull(invoiceNumber);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof InvoiceKey that)) {
                return false;
            }
            return invoiceNumber.equals(that.invoiceNumber);
        }

        @Override
        public int hashCode() {
            return invoiceNumber.hashCode();
        }
    }

    public static void main(String[] args) {
        Map<InvoiceKey, Integer> totals = new HashMap<>();
        InvoiceKey original = new InvoiceKey("INV-01");
        InvoiceKey duplicate = new InvoiceKey("INV-01");

        System.out.println(original == duplicate);
        System.out.println(original.equals(duplicate));
        System.out.println(totals.put(original, 100));
        System.out.println(totals.put(duplicate, 250));
        System.out.println(totals.size());
        System.out.println(totals.get(original));
    }
}
~~~

Compile and run:

~~~bash
javac InvoiceKeyDemo.java
java InvoiceKeyDemo
~~~

Exact output:

~~~text
false
true
null
100
1
250
~~~

Rules to preserve:

- **`equals`/`hashCode` consistency:** if two keys are equal by `equals`, they must produce the same hash. Overriding `equals` yet forgetting `hashCode` can cause `HashMap` to fail to find the entry to replace when receiving a different key instance with the same value.
- **Key stability:** avoid modifying data participating in `equals`/`hashCode` after putting the key into `HashMap`. If the hash code changes, `get`, `put`, and `remove` using the mutated key can produce unexpected results. The `InvoiceKey` class uses a `final` field with immutable `String` to avoid this issue.
- **Business-model accuracy:** do not assume every field must participate in `equals`. For example, in `InvoiceKey`, `invoiceNumber` is defined as the key; if real business logic needs both company code and invoice number, both must be included in `equals` **and** `hashCode`.
- **Do not infer overwritten values from key references:** the two `InvoiceKey`s are two different instances, yet the map keeps only **one entry** because of the same key value.

In typical `HashMap` implementations, updating with an equivalent key modifies the value of the stored entry rather than replacing the key object residing in the entry. However, **do not build application logic on which physical key instance is retained**: the rule guaranteed by the `Map` interface is the key→value mapping relationship, not the persistence of a specific original key object. In particular, specialized maps may define key comparison differently from `HashMap`.

## 7. Special Cases and Common Mistakes

### 7.1. Two equal values do not mean two equal keys

~~~java
Map<String, Integer> counts = new HashMap<>();
counts.put("A", 1);
counts.put("B", 1);
System.out.println(counts.size()); // 2
~~~

Two entries can have the **same value** yet still be two separate entries because **the keys differ**. A map is not a set of unique values.

### 7.2. Keys with the same hash code are not necessarily duplicate keys

~~~java
Map<String, Integer> counts = new HashMap<>();
counts.put("Aa", 1);
counts.put("BB", 2);
System.out.println(counts.size()); // 2
~~~

`"Aa"` and `"BB"` share `hashCode` yet differ in `equals`. This is a valid collision; `HashMap` still keeps both.

### 7.3. Do not rely on `HashMap` print order to verify replacement

`HashMap` **does not guarantee key/entry iteration order**. When verifying, call `size()`, `get(key)`, `containsKey(key)`, or inspect the return value of `put`, rather than inferring from the printed string of the whole map.

If guaranteed iteration order is needed, you must choose another structure meeting that requirement, such as `LinkedHashMap` (in insertion order by default). Even so, the main topic of this lesson remains **when a key's value is replaced**, not iteration order.

### 7.4. Do not assume every `Map` uses the same "duplicate key" rule

`HashMap` relies on the key's `equals` and `hashCode` (with appropriate special handling for `null`). However:

- `TreeMap` distinguishes keys based on the **ordering comparison** result of a provided `Comparator` or `Comparable`. Two keys can be treated as equivalent when `compare(k1, k2) == 0`.
- `IdentityHashMap` intentionally uses **reference identity** (`==`) instead of `equals`, serving specialized scenarios.
- `Map.of` creates an unmodifiable map; calling `put` fails with `UnsupportedOperationException`, and duplicate keys among arguments at creation time are rejected.

Therefore, always check **the specific map type** before making assumptions about key equivalence and mutability.

### 7.5. Do not use `get(k) == null` to determine that a key does not exist

With `HashMap`, `null` values are valid. `get(k) == null` can mean the key does not exist yet **or** currently maps to `null`. When you need to determine whether a key is truly present, use `containsKey(k)`. Similarly, `put(k, v)` returning `null` could be a new addition or replacing an old `null` value.

### 7.6. Do not treat `put` on a regular `HashMap` as a thread-safe update

Regular `HashMap` is not designed for concurrent modification by multiple threads without coordination. The **check-then-act** pattern (`containsKey`/`get` followed by `put`) is also not an atomic operation. In concurrent problems, you need appropriate data structures and operations, such as `ConcurrentHashMap` with `putIfAbsent`, `compute`, or `merge` when suitable; note that `ConcurrentHashMap` does not allow `null` keys/values and operation semantics differ.

## 8. Checklist When Using `Map.put()`

1. **Identify the map type:** `HashMap`, `TreeMap`, `IdentityHashMap`, immutable maps, or concurrent maps have different key-equivalence rules and mutability capabilities.
2. **Define what constitutes the same logical key:** for `HashMap`, check the key class's `equals`/`hashCode` and ensure key state is stable.
3. **Predict the behavior:** a new key adds an entry; an existing equivalent key replaces the value and keeps the size unchanged.
4. **Interpret the return value properly:** `put` returns the old value; `null` may leave it ambiguous whether the key existed beforehand if the map allows `null` values.
5. **Separate collisions from duplicate keys:** equal hashes are not enough; the key's equality relation must be checked.
6. **Choose the right update variant:** use `putIfAbsent` when you only want to assign if absent/`null`, `replace` when you only want to replace an existing key, or appropriate atomic operations when multiple threads are involved.

## 9. Self-Check

1. After `map.put("A", 1); map.put("A", 2);`, what are `map.size()` and `map.get("A")`? What does the second `put` call return?
2. If you call `map.put(new String("A"), 3)` on a map containing `"A" → 2`, is this a new key? Why?
3. Two keys have the same `hashCode` yet `equals` returns `false`. When using `HashMap`, does the second `put` call necessarily overwrite the first key's value?
4. Why is `put("A", "ready")` returning `null` insufficient to conclude that `"A"` did not exist beforehand?
5. What can happen if a key has a field used in `hashCode` modified after being added to `HashMap`?
6. In what situation is `putIfAbsent` more appropriate than `put`? If the key exists yet its current value is `null`, what does `HashMap`'s `putIfAbsent` do?

**Remember:** With `HashMap`, `Map.put(k, v)` **adds an entry if the key is new**, but **replaces the value if an equivalent key by `equals`/`hashCode` already exists**, even when using a different key object with the same value. `put` returns the old value (which may be `null`), and **matching hash codes do not automatically mean duplicate keys**.