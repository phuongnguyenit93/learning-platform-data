# Building Lookup Indexes from a List of Objects

> **Chapter:** Collecting to Maps  
> **Module:** JAVA_STREAM_API  
> **Focus:** Use the `filter`, `map`, and `collect` pipeline of the Java Stream API to transform object lists into lookup indexes by ID, email, category, or composite keys. Understand how to choose `toMap`, `groupingBy`, merge functions, Map types, immutability, and how to verify indexes when data or pipeline execution changes.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish a raw source list from a **lookup index** in the form `Map<K, V>` or `Map<K, List<V>>`.
2. Build a unique-key index with `Collectors.toMap` and handle duplicate keys intentionally.
3. Use `Collectors.groupingBy` for **one-key–many-objects** relationships, or `toMap` with a merge function when appropriate.
4. Create multi-criteria indexes, nested indexes, and normalized-key indexes.
5. Choose `HashMap`, `LinkedHashMap`, `TreeMap`, or `ConcurrentMap` based on real requirements.
6. Control `null` keys, `null` values, mutable objects, unmodifiable copies, and consistency when the source list changes.
7. Verify exact record counts, ordering, duplicate-key policies, and correctness under parallel execution.
8. Know when to pre-build a Map for repeated lookups and when `findFirst` or `anyMatch` is enough.

The examples use **Java 17+**. `Collectors.toMap` and `groupingBy` have existed since Java 8; `record` requires Java 16+, and `Stream.toList()` has existed since Java 16. Standalone snippets represent the body of a method with the corresponding `import` statements; complete examples declare their own class.

## 1. What Is a Lookup Index?

Suppose an application has a list of customers:

~~~java
import java.util.List;

record Customer(long id, String email, String city, boolean active) {}

List<Customer> customers = List.of(
        new Customer(101L, "an@example.vn", "Hanoi", true),
        new Customer(102L, "binh@example.vn", "Ho Chi Minh City", true),
        new Customer(103L, "chi@example.vn", "Hanoi", false),
        new Customer(104L, "dung@example.vn", "Ho Chi Minh City", true)
);
~~~

To find the customer with ID `103`, one way is scanning the list:

~~~java
import java.util.Optional;

Optional<Customer> found = customers.stream()
        .filter(c -> c.id() == 103L)
        .findFirst();

System.out.println(found.map(Customer::email).orElse("Not found"));
// chi@example.vn
~~~

Each search this way may inspect up to `n` elements, costing linear **O(n)** time in the worst case. If the application must look up the same list many times, you can build an index:

~~~text
List<Customer>
    ├── Customer(id=101, email="an@example.vn",   city="Hanoi")
    ├── Customer(id=102, email="binh@example.vn", city="Ho Chi Minh City")
    ├── Customer(id=103, email="chi@example.vn",  city="Hanoi")
    └── Customer(id=104, email="dung@example.vn", city="Ho Chi Minh City")
                  │
                  │ collect(toMap(Customer::id, identity()))
                  ▼
Map<Long, Customer>
    101 ──> Customer(101, ...)
    102 ──> Customer(102, ...)
    103 ──> Customer(103, ...)
    104 ──> Customer(104, ...)

index.get(103L) ──> Customer(103, ...)
~~~

With a standard hash-based Map and keys having a well-distributed `hashCode`, a `get` lookup is **typically O(1) on average**. However, there is no O(1) guarantee in all scenarios. Building an index has an upfront cost, consumes extra memory, and introduces synchronization requirements when source data changes.

**An index in this lesson is an in-memory Java data structure.** It differs from a database index: after building the Map, Java does not automatically track subsequent edits to the source list.

## 2. Creating a Unique Single-Key Index with toMap

`Collectors.toMap` has the basic form:

~~~java
static <T, K, U> Collector<T, ?, Map<K, U>> toMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper
);
~~~

- `keyMapper` extracts the index key from each object.
- `valueMapper` selects the value stored in the Map.
- Each key may map to only one value under the current policy; the two-argument overload **throws an exception on duplicate keys**.

### 2.1. ID → object index

~~~java
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

Map<Long, Customer> byId = customers.stream()
        .collect(Collectors.toMap(
                Customer::id,
                Function.identity()
        ));

Customer customer = byId.get(103L);

System.out.println(customer.email()); // chi@example.vn
~~~

`Function.identity()` means **keeping the input object itself** as the value. The Map holds references to the `Customer` objects; it is not a *deep copy* mechanism.

The pipeline above reads clearly:

~~~text
customers.stream()
  └── collect(toMap(Customer::id, identity()))
          ├── key  : c.id()
          └── value: c itself
                  ↓
          Map<Long, Customer>
~~~

`toMap` is the collector passed to the terminal operation `collect`. Data is traversed when `collect` is called, yielding a lookup Map.

### 2.2. Storing only the field needed for lookup

If business logic only needs to look up email by ID:

~~~java
Map<Long, String> emailById = customers.stream()
        .collect(Collectors.toMap(
                Customer::id,
                Customer::email
        ));

System.out.println(emailById.get(102L)); // binh@example.vn
~~~

This can reduce the amount of data referenced by the index, at the cost of losing access to other fields through that index. The result of `valueMapper` can be an object, a string, a number, or a transformed DTO.

**Having a key alone is not enough to use two-argument `toMap`**: you must verify key uniqueness in the source and ensure the values returned by the mapper comply with the collector contract.

## 3. Duplicate Keys: Decide the Policy Explicitly Before Collecting

Two records with the same key can arise from dirty data, historical records, newer revisions, or because the chosen key is inherently non-unique.

~~~java
import java.util.List;

List<Customer> duplicates = List.of(
        new Customer(101L, "an@example.vn", "Hanoi", true),
        new Customer(101L, "an.new@example.vn", "Hanoi", true)
);
~~~

The following statement **does not produce a valid Map**:

~~~java
// Runtime: IllegalStateException because key 101 appears twice.
Map<Long, Customer> invalid = duplicates.stream()
        .collect(Collectors.toMap(
                Customer::id,
                java.util.function.Function.identity()
        ));
~~~

This is helpful behavior when **IDs must be unique**. Do not silently drop a record just to keep the program running if violating uniqueness indicates a data error.

### 3.1. Failing on duplicate keys with a business message

Three-argument overload:

~~~java
import java.util.function.Function;
import java.util.stream.Collectors;

Map<Long, Customer> strictIndex = duplicates.stream()
        .collect(Collectors.toMap(
                Customer::id,
                Function.identity(),
                (previous, incoming) -> {
                    throw new IllegalStateException(
                            "Duplicate customer ID: " + previous.id()
                    );
                }
        ));
~~~

Here, the merge function decides how to handle two values sharing the **same key**. Because duplicate data is considered invalid, the function intentionally throws an exception.

On a parallel Stream, when detection occurs and which objects reach the merge function may vary; error messages **should not depend on processing order** to explain the cause.

### 3.2. Keeping the first or last record when business logic permits

~~~java
Map<Long, Customer> keepFirst = duplicates.stream()
        .collect(Collectors.toMap(
                Customer::id,
                Function.identity(),
                (first, later) -> first
        ));

Map<Long, Customer> keepLast = duplicates.stream()
        .collect(Collectors.toMap(
                Customer::id,
                Function.identity(),
                (first, later) -> later
        ));
~~~

With an ordered `List` source and a sequential pipeline, the two examples represent two clear policies. However, **"last record" does not mean "newest record"**: position in the List tells you nothing about timestamp or version unless specified by the input contract.

If the intent is **picking the latest version**, it is better to compare the version/timestamp field directly, with a rule for when two records share the same version. Selections depending on element encounter order are unsuitable for switching casually to an `UNORDERED` or concurrent collector without reviewing the contract.

### 3.3. Selecting the record with the highest revision and a clear tie-breaker

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.function.BinaryOperator;
import java.util.function.Function;
import java.util.stream.Collectors;

record Product(long id, int revision, String name) {}

List<Product> revisions = List.of(
        new Product(7L, 1, "Blue pen"),
        new Product(7L, 3, "New blue pen"),
        new Product(9L, 2, "Notebook")
);

// Defined rule: higher revision takes priority;
// if revisions are equal, the greater name by String.compareTo is chosen.
Comparator<Product> priority =
        Comparator.comparingInt(Product::revision)
                  .thenComparing(Product::name);

BinaryOperator<Product> choosePreferred = BinaryOperator.maxBy(priority);

Map<Long, Product> latestById = revisions.parallelStream()
        .collect(Collectors.toMap(
                Product::id,
                Function.identity(),
                choosePreferred
        ));

System.out.println(latestById.get(7L).revision()); // 3
~~~

`maxBy` over this consistent comparison order makes selection independent of left/right combination order whenever distinct values can be distinguished by the comparator. Since `id` is the shared key within a group, `revision` and `name` establish priority order for the data in the example.

**Business limitation:** If two records share the same ID and revision yet have different contents, picking by name is valid only if that is **truly an approved rule**. In many systems, reporting a version conflict is better. Do not invent an arbitrary tie-breaking rule merely to paper over data errors.

## 4. Non-Unique Keys: groupingBy Builds a One-to-Many Index

If you want to look up **all customers in a city**, city is obviously not a unique key. Two-argument `toMap(Customer::city, identity())` will throw an exception upon encountering the second person in the same city.

Use `groupingBy`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<Customer>> byCity = customers.stream()
        .collect(Collectors.groupingBy(Customer::city));

System.out.println(byCity.get("Hanoi").size()); // 2
System.out.println(byCity.get("Ho Chi Minh City").size()); // 2
~~~

This is a **one key → many elements** index:

~~~text
"Hanoi"              ──> [Customer(101), Customer(103)]
"Ho Chi Minh City"   ──> [Customer(102), Customer(104)]
~~~

Points to keep in mind:

- `groupingBy` can produce a `Map<K, List<T>>`, preserving multiple records sharing a classification key.
- The returned Map **has no guarantee of implementation class, mutability, or thread-safety** unless specific overloads and conditions are chosen.
- Each group's `List` is a collected result, not necessarily a synchronized structure; do not mutate them concurrently without proper synchronization.
- With standard `groupingBy`, **classification keys must be non-null**; if the classifier returns null, the operation can throw `NullPointerException`.

### 4.1. Returning an empty list when the key is absent

~~~java
List<Customer> inDaNang = byCity.getOrDefault(
        "Da Nang", List.of()
);

System.out.println(inDaNang.size()); // 0
~~~

`Map.get` returns `null` when a key is not found (in Maps that permit null values, `get` can also return null because the stored value is null). For indexes containing only non-null values, `getOrDefault` clearly expresses returning an empty list.

### 4.2. Storing only the information needed per group

Example of city → list of emails:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<String>> emailsByCity = customers.stream()
        .collect(Collectors.groupingBy(
                Customer::city,
                Collectors.mapping(
                        Customer::email,
                        Collectors.toList()
                )
        ));

System.out.println(emailsByCity.get("Hanoi"));
// [an@example.vn, chi@example.vn]
~~~

`Collectors.mapping` is a downstream collector: it maps each `Customer` to a `String` and collects them within the corresponding group.

If you only need the **customer count per city**, there is no need to allocate lists:

~~~java
Map<String, Long> countByCity = customers.stream()
        .collect(Collectors.groupingBy(
                Customer::city,
                Collectors.counting()
        ));

System.out.println(countByCity.get("Hanoi")); // 2
~~~

Choosing the index value type `V` is a design decision: store the whole object, store a single field, store a list, or store an aggregated value.

## 5. Multiple Indexes Over the Same Dataset

An application may need three lookup paths:

- By ID: `Map<Long, Customer>`.
- By email: `Map<String, Customer>`.
- By city: `Map<String, List<Customer>>`.

~~~java
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

List<Customer> snapshot = List.copyOf(customers);

Map<Long, Customer> idIndex = snapshot.stream()
        .collect(Collectors.toMap(
                Customer::id, Function.identity()
        ));

Map<String, Customer> emailIndex = snapshot.stream()
        .collect(Collectors.toMap(
                Customer::email, Function.identity()
        ));

Map<String, List<Customer>> cityIndex = snapshot.stream()
        .collect(Collectors.groupingBy(Customer::city));
~~~

`List.copyOf` returns a structurally unmodifiable list and rejects null elements; here `Customer` is a record containing primitives and `String`, so the fields in use are also stable. For records containing mutable fields, this copy does **not** deep-copy each object.

**Important:** The three Maps are built from the same snapshot, yet they remain **three independent indexes**. When a new record arrives, an email changes, or a city changes, the Maps **do not update automatically**.

### 5.1. The same object can appear in multiple Maps

The Maps above typically share references to the same `Customer` objects in the snapshot. An index does not necessarily copy objects; adding another index mainly adds overhead for key structures, buckets, entries, and group lists.

If objects are mutable, changing an object's field can alter the value returned by a Map while **the old Map key remains unchanged**, making the email/city index inconsistent. For example:

~~~text
Initially built index:
   emailIndex["old@example.vn"] -> Customer(email="old@example.vn")

After mutating Customer's email field:
   emailIndex["old@example.vn"] -> Customer(email="new@example.vn")

   emailIndex["new@example.vn"] -> null   (not yet rebuilt)
~~~

That is why immutable data models for snapshots and explicit index-update strategies should be preferred.

## 6. Normalizing Keys to Avoid Lookup Misses

Emails or partner codes may be entered with extra whitespace and varying letter cases. If business rules allow case-insensitive matching, normalize **at both indexing time and lookup time**.

~~~java
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

static String normalizedEmail(String raw) {
    return raw.strip().toLowerCase(Locale.ROOT);
}
~~~

Place `normalizedEmail` in a utility class or as a static method of the enclosing class. Usage:

~~~java
Map<String, Customer> byNormalizedEmail = customers.stream()
        .collect(Collectors.toMap(
                customer -> normalizedEmail(customer.email()),
                Function.identity()
        ));

Customer found = byNormalizedEmail.get(
        normalizedEmail("  AN@EXAMPLE.VN ")
);

System.out.println(found.id()); // 101
~~~

Using `Locale.ROOT` keeps lowercasing consistent across environments instead of depending on the host machine's default locale.

**Normalization changes duplicate-key relationships.** For instance, `"AN@EXAMPLE.VN"` and `"an@example.vn"` can map to the same key; two-argument `toMap` will detect a collision. You need a data policy for when that happens.

For real-world email addresses, case sensitivity of the local part, Unicode, IDN, and valid normalization rules can be complex. The snippet above is merely an **illustrative application lookup convention**; do not apply it as a global email validation/identity rule.

For product codes or document IDs, also consider whether stripping characters, removing leading zeros, or changing formatting could cause **two distinct values to collapse into one key**. Normalization is valid only when it matches the business key definition.

## 7. Choosing the Map Type and Controlling Order

The default overloads of `Collectors.toMap` and `groupingBy` do not guarantee the returned Map implementation. If specific characteristics are needed, use the overload with `mapFactory`.

### 7.1. HashMap for standard lookups

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

Map<Long, Customer> index = customers.stream()
        .collect(Collectors.toMap(
                Customer::id,
                Function.identity(),
                (a, b) -> {
                    throw new IllegalStateException("Duplicate ID " + a.id());
                },
                HashMap::new
        ));
~~~

`HashMap` provides hash-based lookups with good average performance if the key's `equals`/`hashCode` are well designed; it **makes no guarantees on iteration order**.

### 7.2. LinkedHashMap when insertion order is needed

~~~java
import java.util.LinkedHashMap;

Map<Long, Customer> indexInEncounterOrder = customers.stream()
        .collect(Collectors.toMap(
                Customer::id,
                Function.identity(),
                (a, b) -> a,
                LinkedHashMap::new
        ));

System.out.println(indexInEncounterOrder.keySet());
// [101, 102, 103, 104] with this List source and sequential pipeline
~~~

`LinkedHashMap` preserves insertion order by default. The example uses an **ordered sequential Stream** to express insertion order matching the list. If the contract requires strict result ordering across all usage modes, design and test separately before switching to parallel processing; do not infer order from `HashMap`.

### 7.3. TreeMap when key ordering is needed

~~~java
import java.util.TreeMap;

TreeMap<Long, Customer> sortedIndex = customers.stream()
        .collect(Collectors.toMap(
                Customer::id,
                Function.identity(),
                (a, b) -> a,
                TreeMap::new
        ));

System.out.println(sortedIndex.firstKey()); // 101
~~~

`TreeMap` iterates in **key order** (natural order or comparator), typically with **O(log n)** lookup/insertion cost. The comparator must be designed carefully: if it treats two distinct keys as equal with `compare(a,b) == 0`, `TreeMap` will treat them as a single key.

### 7.4. Maps by business requirement

| Requirement | Typical choice | What to verify |
|---|---|---|
| ID lookup, no ordering needed | `HashMap` | `equals`/`hashCode` and stable keys |
| Iterate results in insertion order | `LinkedHashMap` | Source, pipeline, and duplicate-key policy |
| Need range queries / sorted key order | `TreeMap` | Comparator, performance, and ordering semantics |
| Concurrent per-key accumulation | `ConcurrentHashMap` or standard concurrent collector | Thread-safety, duplicate-key handling, no order guarantee |
| Forbid modifying index structure after creation | `toUnmodifiableMap` or `Map.copyOf` | Nulls, duplicates, shallow immutability |

No single Map type is right by default for every problem. Choose the structure based on **access paths and consumer constraints**, then verify with data.

## 8. Nested Indexes: City → ID → Customer

When lookups are needed by both city and ID:

~~~java
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

Map<String, Map<Long, Customer>> byCityThenId = customers.stream()
        .collect(Collectors.groupingBy(
                Customer::city,
                Collectors.toMap(
                        Customer::id,
                        Function.identity()
                )
        ));

Customer result = byCityThenId
        .getOrDefault("Hanoi", Map.of())
        .get(103L);

System.out.println(result.email()); // chi@example.vn
~~~

This is a two-level index:

~~~text
"Hanoi"
    ├── 101 -> Customer(101)
    └── 103 -> Customer(103)

"Ho Chi Minh City"
    ├── 102 -> Customer(102)
    └── 104 -> Customer(104)
~~~

A two-level index is useful when:

- The application frequently **filters by city first**, then looks up an ID within that group.
- IDs only need to be unique **within each group** (if the domain permits).
- The grouped structure must be kept for repeated queries.

If IDs are already globally unique across the system, looking up via `idIndex.get(id)` can be simpler. When IDs are **not** globally unique, explicitly define a composite key such as `(tenantId, id)` or a nested index to prevent accidental overwrites.

### 8.1. Using a record as a composite key

~~~java
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

record CityCustomerKey(String city, long id) {}

Map<CityCustomerKey, Customer> byCityAndId = customers.stream()
        .collect(Collectors.toMap(
                c -> new CityCustomerKey(c.city(), c.id()),
                Function.identity()
        ));

Customer found = byCityAndId.get(
        new CityCustomerKey("Hanoi", 103L)
);

System.out.println(found.email()); // chi@example.vn
~~~

`record` auto-generates `equals` and `hashCode` from its components, making it well suited for **value** keys. Key components must still behave immutably: in this example, `String` and `long` satisfy this well.

## 9. Unmodifiable Indexes and Data Lifecycle

If a Map is built once for other components to **read only**, returning a structurally unmodifiable index prevents confusion about update ownership.

### 9.1. toUnmodifiableMap (Java 10+)

~~~java
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

Map<Long, Customer> immutableById = customers.stream()
        .collect(Collectors.toUnmodifiableMap(
                Customer::id,
                Function.identity()
        ));

// immutableById.put(105L, anotherCustomer);
// Throws UnsupportedOperationException if called.
~~~

`toUnmodifiableMap` rejects null keys and null values, and also throws on duplicate keys when using the two-argument overload.

### 9.2. Map.copyOf is a structurally shallow copy

~~~java
import java.util.Map;

Map<Long, Customer> readOnlyIndex = Map.copyOf(byId);
~~~

`Map.copyOf` returns a Map that forbids structural changes. It **does not deep-copy** value objects: if a target object is mutable, it can still be modified through another reference. `Map.copyOf` also rejects null keys and values; iteration order of the result is not guaranteed.

Comparing three options:

| API | Allows modifying returned Map? | Deep-copies values automatically? |
|---|---|---|
| `Collectors.toMap` | No immutability guarantee; usually returns a mutable Map | No |
| `Collectors.toUnmodifiableMap` | No | No |
| `Map.copyOf(existingMap)` | No | No |

`Collections.unmodifiableMap(existing)` creates a **view** that blocks modifications through the view itself; if `existing` is still modified elsewhere, the view reflects those changes. This differs from creating a value-level Map snapshot.

## 10. Nulls, Malformed Data, and Key Contracts

A well-designed index must explicitly specify whether identifier fields may be null, blank, or malformed.

Example requiring all emails to be present:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;
import java.util.stream.Collectors;

Map<String, Customer> safeEmailIndex = customers.stream()
        .collect(Collectors.toMap(
                c -> Objects.requireNonNull(
                        c.email(), "Email must not be null, id=" + c.id()
                ),
                Function.identity()
        ));
~~~

If business logic allows `null` emails, you should generally **not** use null as a single key grouping many people. You can filter for those who have an email:

~~~java
Map<String, Customer> knownEmails = customers.stream()
        .filter(c -> c.email() != null)
        .collect(Collectors.toMap(
                Customer::email,
                Function.identity()
        ));
~~~

This result **excludes** customers without an email. If missing data must be reported as an error, validate input and return error details according to business policy.

**Notes on null:**

- `Collectors.toUnmodifiableMap` and `Map.copyOf` reject nulls.
- With `Collectors.toMap`, do not rely on storing null values; standard JDKs throw `NullPointerException` when the value mapper returns null, and the contract does not promise null support.
- `Collectors.groupingBy` requires the classifier to produce non-null keys in standard usage; to group "unknown city", create an explicit representative key such as `"UNKNOWN"`, provided it cannot collide with real keys.
- Use `Objects.requireNonNull` to catch bad data at the processing boundary, including identifying record details.

~~~java
Map<String, List<Customer>> byKnownCity = customers.stream()
        .collect(Collectors.groupingBy(
                c -> c.city() == null ? "UNKNOWN" : c.city()
        ));
~~~

In systems with complex data, an `Optional` model or a dedicated key type representing missingness can be clearer than a sentinel string.

## 11. Keys Must Be Stable: equals, hashCode, and Mutable Objects

`HashMap` uses the key's `hashCode` and `equals` to locate entries. If **state used to compute `hashCode`/`equals` changes after insertion**, lookups can fail even when holding the exact same object reference.

~~~java
import java.util.HashMap;
import java.util.Map;

final class MutableKey {
    String code;

    MutableKey(String code) {
        this.code = code;
    }

    @Override public boolean equals(Object other) {
        return other instanceof MutableKey k
                && java.util.Objects.equals(code, k.code);
    }

    @Override public int hashCode() {
        return java.util.Objects.hashCode(code);
    }
}

MutableKey key = new MutableKey("A");
Map<MutableKey, String> index = new HashMap<>();
index.put(key, "Product A");

key.code = "B"; // Changes hashCode of an already-inserted key.

// May fail to find the expected result:
System.out.println(index.get(new MutableKey("B")));
~~~

In the example, mutating `code` breaks the assumption that the key remains stable in the bucket where it was inserted. Do not rely on `get` after mutating a key as a dependable contract.

Solutions:

- Use `String`, `Long`, or a `record` composed of immutable fields as keys.
- Do not use a mutable entity as a key if fields participating in `equals`/`hashCode` can change.
- When a business key changes, **remove the old entry and insert the new entry** through a controlled update procedure, or rebuild the index snapshot.
- With `TreeMap`, also keep fields affecting the comparator stable.

**Distinction:** Mutating a `Customer` value inside an entry does not necessarily corrupt the hash table if the **`Long` key** does not change. However, modifying `email` or `city` on `Customer` can make the corresponding **secondary indexes** stale.

## 12. Rebuilding Indexes When Data Changes

An in-memory index should have a clear lifecycle:

1. Receive or load a validated **snapshot** of the input data.
2. Build the required Maps from that snapshot.
3. Publish the Maps to readers once construction is complete.
4. When source data updates, decide whether to **rebuild completely** or update individual entries under a consistent protocol.

Example rebuilding an immutable index from a new list:

~~~java
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

static Map<Long, Customer> buildIdIndex(List<Customer> source) {
    return source.stream()
            .collect(Collectors.toUnmodifiableMap(
                    Customer::id,
                    Function.identity()
            ));
}
~~~

When the source list may be modified by another writing thread, **do not** run a stream over a mutable collection while it is concurrently mutated unless the collection supports it. Take a consistent snapshot under proper synchronization or obtain an immutable snapshot from the data layer.

### 12.1. Multiple indexes must stay consistent with one another

Suppose email must be updated for customer `101`. If the system updates the email in `byId` before updating `byEmail`, an in-flight read request may observe two different versions of the data.

One solution is to build **an immutable index bundle** and swap the entire bundle reference atomically:

~~~java
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

record CustomerIndexes(
        Map<Long, Customer> byId,
        Map<String, Customer> byEmail
) {}

static CustomerIndexes buildIndexes(List<Customer> snapshot) {
    Map<Long, Customer> byId = snapshot.stream()
            .collect(Collectors.toUnmodifiableMap(
                    Customer::id, Function.identity()
            ));

    Map<String, Customer> byEmail = snapshot.stream()
            .collect(Collectors.toUnmodifiableMap(
                    Customer::email, Function.identity()
            ));

    return new CustomerIndexes(byId, byEmail);
}
~~~

If the system has multiple reader/writer threads, publishing the new bundle requires an appropriate visibility/thread-safety mechanism (such as a `volatile` reference or `AtomicReference<CustomerIndexes>`). Each read request should capture **one** bundle reference and use it throughout that request. This prevents reading individual Maps from two different versions.

Do not regard multiple mutable Maps as "synchronized" merely because each Map uses a concurrent structure: **cross-index consistency** is a stronger requirement than thread-safety of individual Map operations.

## 13. Building Indexes with Parallel Collectors

`parallelStream` can split the source, create intermediate Maps, and combine results. The merge-function contract becomes especially critical when keys collide.

~~~java
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

Map<Long, Customer> parallelById = customers.parallelStream()
        .collect(Collectors.toMap(
                Customer::id,
                Function.identity()
        ));

System.out.println(parallelById.get(101L).email()); // an@example.vn
~~~

With unique IDs and data that does not mutate during execution, this usage is valid. However, **parallel is not guaranteed to be faster** on a small list: splitting and merging intermediate Maps can cost more than building a Map sequentially.

### 13.1. toConcurrentMap

~~~java
import java.util.concurrent.ConcurrentMap;
import java.util.function.Function;
import java.util.stream.Collectors;

ConcurrentMap<Long, Customer> concurrentById = customers.parallelStream()
        .collect(Collectors.toConcurrentMap(
                Customer::id,
                Function.identity()
        ));
~~~

`toConcurrentMap` creates a concurrent/unordered collector per the contract of its overload. Use it when encounter order is not needed and the workload genuinely benefits from concurrent collection. **`ConcurrentMap` does not guarantee iteration order matching input order**.

If duplicate keys occur, specify an appropriate merge policy, just like `toMap`:

~~~java
ConcurrentMap<Long, Product> latestConcurrent = revisions.parallelStream()
        .collect(Collectors.toConcurrentMap(
                Product::id,
                Function.identity(),
                choosePreferred
        ));
~~~

In this example, `choosePreferred` is the selector declared in Section 3, based on an explicit priority order; there is no need to rely on thread scheduling to decide which record wins.

### 13.2. groupingByConcurrent

~~~java
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

ConcurrentMap<String, List<Customer>> concurrentByCity =
        customers.parallelStream()
                .collect(Collectors.groupingByConcurrent(Customer::city));

System.out.println(concurrentByCity.get("Hanoi").size()); // 2
~~~

This collector enables concurrent grouping and **does not guarantee encounter order of elements within groups**. `ConcurrentMap` may be thread-safe for Map operations, yet **the value Lists are not guaranteed to be safe for concurrent modification after collection**. If deterministic ordering inside each group is needed, choose an appropriate `groupingBy` on an ordered source, or sort results by a business sort key.

### 13.3. Merge functions need an appropriate contract

When multiple intermediate results share the same key, the merge function should ensure no data is lost and the result satisfies requirements:

- **Exact integer addition:** use `BigInteger::add` or a sufficiently large numeric type.
- **Merging by version:** use a selector with a fully deterministic priority order.
- **Collecting multiple values:** usually use `groupingBy`; do not manually mutate a shared `ArrayList` in a parallel stream.
- **Keeping first/last:** define whether "first/last" is by encounter order or by a business field; do not let thread order become an unintended criterion.

To verify, compare sequential Map, parallel Map, and an independent oracle, covering duplicates, empty sources, and multiple data orderings. For `Map<K, V>`, `Map.equals` compares mappings by content regardless of Map iteration order.

## 14. Verifying Indexes with Oracles and Invariants

For a **unique-ID** index, basic invariants are:

1. Entry count equals source object count (if IDs are truly unique).
2. For each source object `c`, `index.get(c.id())` is an object with data equivalent to `c`.
3. No keys exist outside the source.
4. Duplicate-key policy is tested with an intentionally duplicated dataset.
5. Index query results match direct lookups from the list.
6. When rebuilt on a new snapshot, the index accurately reflects the new snapshot.

Example verification helper:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Objects;

static void verifyIdIndex(
        List<Customer> source,
        Map<Long, Customer> index) {

    if (index.size() != source.size()) {
        throw new AssertionError(
                "Key count does not match customer count"
        );
    }

    for (Customer expected : source) {
        Customer actual = index.get(expected.id());
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    "Lookup mismatch for ID " + expected.id()
            );
        }
    }
}
~~~

This helper assumes `Customer` is a record with value-based `equals`. If `Customer` is a mutable class without data-based `equals`, design a comparator/field-by-field check or compare normalized immutable DTOs.

**Adding a duplicate-key test** is mandatory if uniqueness comes from external data; the helper above only detects inconsistency against a source already assumed valid.

### 14.1. Checking groups without losing or duplicating records

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<Customer>> groups = customers.stream()
        .collect(Collectors.groupingBy(Customer::city));

long totalMembers = groups.values().stream()
        .mapToLong(List::size)
        .sum();

if (totalMembers != customers.size()) {
    throw new AssertionError("Groups lost or duplicated customers");
}
~~~

This is a necessary invariant, yet **not sufficient**: a record could be placed in the wrong group while the total count still matches. Also verify that every object in each list actually has the `city` matching its key and that occurrence counts match the source.

### 14.2. Comparing against direct search

~~~java
import java.util.Objects;
import java.util.Optional;

long targetId = 102L;

Optional<Customer> fromList = customers.stream()
        .filter(c -> c.id() == targetId)
        .findFirst();

Optional<Customer> fromIndex =
        Optional.ofNullable(byId.get(targetId));

if (!Objects.equals(fromList, fromIndex)) {
    throw new AssertionError("Index does not match source");
}
~~~

An index optimizes subsequent searches once built; direct search remains useful as an oracle on small test datasets. If the source permits duplicate IDs, both lookup paths must apply the **same selection policy** for the comparison to be meaningful.

## 15. When Is a Map Better Than Scanning a Stream Every Time?

Suppose there are `n` customers and `q` ID lookups must be performed.

| Approach | Typical work | Trade-off |
|---|---|---|
| Calling `stream().filter(...).findFirst()` each time | Up to O(n) per lookup, up to O(qn) total | No index structure cost; always reads source at query time |
| Building a `HashMap` once, then calling `get` | Typically O(n) build, O(1) average per `get` | Costs O(n) extra memory and index maintenance effort |
| Building a `TreeMap` | Roughly O(n log n) build, O(log n) lookup | Supports key ordering and range queries |
| `groupingBy` on a non-unique key | Scans source to group, stores lists per key | Useful for per-group queries; costs reference memory |
| Updating individual records in an existing Map | Can avoid full rebuild | Must keep multiple indexes and key policies in sync |

This is a qualitative cost model: actual performance depends on key distribution, Map implementation, GC, data volume, update frequency, and cache locality. Do not enable `parallelStream` just because you are building an index; verify correctness first and benchmark with real data.

**When searching only once**, scanning with `findFirst` is usually clear enough and can be cheaper than the total cost of building a Map. **When thousands of lookups are needed against the same snapshot**, a Map index is usually worth considering.

## 16. Common Errors

| Error | Consequence | Resolution |
|---|---|---|
| Choosing email/city as a unique key when duplicates exist | `toMap` throws `IllegalStateException` | Check uniqueness; use a policy-driven merge or `groupingBy` |
| Merging with `(old, next) -> next` without knowing data order | "Winning record" may not reflect the right version | Use explicit version/timestamp and tie-breaker |
| Normalizing keys only during indexing | `get` returns null even though data exists | Use the same normalization function for both writes and reads |
| `null` values in `toMap` | May throw `NullPointerException` | Validate/normalize data beforehand |
| Mutating an object used as a HashMap key | Lookups become unreliable | Immutable keys with stable `equals`/`hashCode` |
| Mutating Customer after building an email index | Secondary Map retains the stale email key | Rebuild or update atomically/in sync |
| Treating `toUnmodifiableMap` as a deep copy | Mutable values can still change | Immutable DTOs or defensive deep copies as needed |
| Relying on `HashMap` iteration order | Display order becomes unstable | Sequential `LinkedHashMap` or sort by key |
| `groupingByConcurrent` followed by mutating Lists from multiple threads | Race condition | Do not mutate shared Lists; choose an appropriate concurrent structure/method |
| Running two terminal operations on the same Stream | `IllegalStateException` | Create a new Stream from a re-traversable snapshot |
| Forgetting to handle missing keys | `NullPointerException` when calling methods on `get` result | `Optional.ofNullable`, `getOrDefault`, or null checks |
| Checking only entry count in an index | Wrong key mappings can slip through | Verify every key/value pair and compare against an oracle |

## 17. Complete Example: Building and Verifying Two Indexes

The standalone program below builds a unique index by ID, a multi-value index by city, and then verifies the output. `Customer` objects are modeled as immutable `record`s for the fields used.

~~~java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;
import java.util.stream.Collectors;

public class CustomerIndexDemo {

    record Customer(long id, String email, String city, boolean active) {}

    record Indexes(
            Map<Long, Customer> byId,
            Map<String, List<Customer>> byCity
    ) {}

    static Indexes build(List<Customer> source) {
        List<Customer> snapshot = List.copyOf(source);

        Map<Long, Customer> byId = snapshot.stream()
                .collect(Collectors.toUnmodifiableMap(
                        Customer::id,
                        Function.identity()
                ));

        Map<String, List<Customer>> grouped = snapshot.stream()
                .collect(Collectors.groupingBy(
                        Customer::city,
                        Collectors.collectingAndThen(
                                Collectors.toList(),
                                List::copyOf
                        )
                ));

        // Create a structurally unmodifiable Map snapshot.
        Map<String, List<Customer>> byCity = Map.copyOf(grouped);

        return new Indexes(byId, byCity);
    }

    static void check(List<Customer> source, Indexes indexes) {
        if (indexes.byId().size() != source.size()) {
            throw new AssertionError("IDs must be unique");
        }

        for (Customer customer : source) {
            if (!Objects.equals(
                    customer,
                    indexes.byId().get(customer.id()))) {
                throw new AssertionError(
                        "Lookup mismatch for ID " + customer.id()
                );
            }
        }

        long groupedCount = indexes.byCity().values().stream()
                .mapToLong(List::size)
                .sum();

        if (groupedCount != source.size()) {
            throw new AssertionError("Grouped customer count mismatch");
        }
    }

    public static void main(String[] args) {
        List<Customer> customers = List.of(
                new Customer(101L, "an@example.vn", "Hanoi", true),
                new Customer(102L, "binh@example.vn", "Ho Chi Minh City", true),
                new Customer(103L, "chi@example.vn", "Hanoi", false)
        );

        Indexes indexes = build(customers);
        check(customers, indexes);

        System.out.println(indexes.byId().get(102L).email());
        // binh@example.vn

        System.out.println(indexes.byCity().get("Hanoi").size());
        // 2

        System.out.println("INDEX_OK");
    }
}
~~~

Here, `collectingAndThen(toList(), List::copyOf)` makes each group list structurally unmodifiable. `Map.copyOf` makes the group Map disallow adding or removing entries, fitting a read-only snapshot.

**Limitation to understand:** This is a basic illustrative check and does not yet verify individual city group memberships. For real data, add checks for email keys, duplicate keys, null cases, large volumes, and source update rules. If mutable object types are used as Map values, copying the Map does not automatically protect their internal state.

## 18. Self-Check Exercises (with Answers)

### Exercise 1. Building an ID index

**Prompt:** Given `List<Product> products`, where `record Product(long id, String name) {}` and IDs are unique, build a `Map<Long, Product>` to look up products by ID.

**Answer:**

~~~java
Map<Long, Product> byId = products.stream()
        .collect(Collectors.toMap(
                Product::id,
                Function.identity()
        ));
~~~

`Function.identity()` keeps the object as the value. If the source contains duplicate IDs, the two-argument collector throws `IllegalStateException`.

### Exercise 2. Multiple customers in one city

**Prompt:** If two customers live in `"Hanoi"`, can you use `toMap(Customer::city, identity())`?

**Answer:** Do not use the two-argument overload for this relationship because keys collide. Choose `groupingBy(Customer::city)` to produce `Map<String, List<Customer>>`.

### Exercise 3. Duplicate keys caused by normalization

**Prompt:** `" AN@EXAMPLE.VN "` and `"an@example.vn"` become the same key after normalization. What happens with two-argument `toMap`?

**Answer:** It detects a duplicate key and throws `IllegalStateException`. You must determine whether the two records truly represent the same identifier under business rules and decide to throw an error, merge, or pick a record by explicit criteria.

### Exercise 4. Choosing by revision

**Prompt:** Two records share the same ID with revisions 3 and 5. Which selection approach is semantically safer than `(old, next) -> next`?

**Answer:** Select the record with the higher revision using a comparator or merge function with explicit rules. If revisions match yet data conflicts, define a tie-breaking policy or throw an error; do not let thread execution order act as a policy.

### Exercise 5. Checking missing keys

**Prompt:** What can `byId.get(999L)` return? How do you avoid `NullPointerException`?

**Answer:** When that ID is absent, it returns `null`. Use a conditional check, `Optional.ofNullable(byId.get(999L))`, or an appropriate default value.

### Exercise 6. Indexes do not auto-update

**Prompt:** After building `emailIndex`, a customer's email changes from `a@example.vn` to `b@example.vn`. Will `emailIndex.get("b@example.vn")` automatically find that person?

**Answer:** No. Maps do not automatically update keys. You must rebuild the index or update the key via a consistent procedure, ensuring related indexes stay on the same data version.

### Exercise 7. Ordering

**Prompt:** The application must display IDs in the order they appear in the List. Which Map should be used?

**Answer:** You can use `LinkedHashMap` via `toMap(..., LinkedHashMap::new)` with an ordered sequential Stream. If ascending ID order is needed, use `TreeMap` or sort explicitly.

### Exercise 8. Group invariant

**Prompt:** Does the sum of sizes of the Lists in `Map<String, List<Customer>> byCity` equal the number of source customers?

**Answer:** If every customer is placed into exactly one group without being filtered out or duplicated, **yes**. Also check that each customer actually belongs to the right city to avoid false passes when records are assigned to the wrong group.

### Exercise 9. Sources with null keys

**Prompt:** If `Customer.city() == null`, should you call `groupingBy(Customer::city)` directly?

**Answer:** No. Validate the data or map null to a key representing missing information according to application rules. `groupingBy` does not accept a classifier returning null in standard usage.

### Exercise 10. When is a Map unnecessary?

**Prompt:** There are 10 customers and the program looks up one ID exactly once. Should you build `Map<Long, Customer>`?

**Answer:** Not necessarily. `stream().filter(c -> c.id() == target).findFirst()` is simple and likely fast enough. Building an index usually pays off when the same dataset must serve **many** lookups or key-based access operations.

---

**Takeaway:** Building indexes from a list with the Java Stream API means clearly establishing **which keys are unique, which keys repeat, what values to store, and how long the Map is used**. Use `toMap` for unique-key lookups with explicit collision policies, `groupingBy` for one key with many objects, and `mapFactory` when a specific Map structure is needed. Normalize keys consistently, keep keys stable, handle nulls, treat Maps as snapshots requiring maintenance, and verify indexes against source data and edge cases before optimizing or switching to parallel execution.
