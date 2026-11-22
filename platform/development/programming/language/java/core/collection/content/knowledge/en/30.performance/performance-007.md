# Reducing Nested Loops with a Set or Map Index

## 1. Recognizing Repeated Search Work

Suppose there are `n` orders and `m` customers. To find the customer for each order, the direct approach is to iterate through each order and then scan the customer list until a matching ID is found. The problem does not lie in the syntactic form of "two `for` loops", but in the fact that **the same dataset is searched repeatedly under the same condition**.

The optimization idea is to perform the preparation work once:

```text
Repeated scan approach:
  each left element -> scan right dataset -> get result

Indexed approach:
  right dataset -> build Set/Map once
  each left element -> look up by key -> get result
```

An index in this article is an in-memory Java data structure, not a database index. It reorganizes how data already present in the program is looked up.

Choose the structure based on the question asked by the inner loop:

| Question to answer | Typically suitable structure |
| --- | --- |
| Is there at least one element with this key? | `Set<K>` |
| What is the single record for this key? | `Map<K, V>` |
| What are all the records sharing this key? | `Map<K, List<V>>` |
| How many records have this key? | `Map<K, Long>` or an appropriate counter type |

Do not switch to a Map just to make the code shorter. First, identify the key, equality semantics, result cardinality, and the ordering that must be preserved.

## 2. Analyzing Before-and-After Costs

### 2.1. Repeated Scanning

For each of the `n` left elements, if up to `m` right elements must be checked, the number of comparisons can reach `n × m`. When both `n` and `m` grow with data scale, this exhibits quadratic growth.

Using `break` after finding the first matching record may do less work on some inputs, but missing matches or late matches still require extensive scanning. For example, `n = 100,000` and `m = 50,000` give an upper bound of 5,000,000,000 pair checks in a full scan. This is a theoretical pair count, not a measured runtime.

### 2.2. Building an Index and Looking Up

With a hash table whose keys are well-distributed and treating key hashing/comparison cost as constant:

- Building the index from `m` elements: expected cost O(m).
- Looking up for `n` elements: expected cost O(n).
- Total: **O(m + n)** for existence checks or single-record lookups, plus the cost of producing the output.
- Auxiliary memory: O(u + c), where `u` is the number of distinct keys and `c` is the hash table capacity; a `Collection` constructor such as `new HashSet<>(allowed)` may allocate O(m) based on the source element count even when many duplicate elements exist.

This trades memory to avoid repeated searching. Do not call `HashMap` or `HashSet` unconditionally O(1) for every key and every scenario. The documentation states conditions on hash code distribution; `hashCode` and `equals` themselves can also be expensive if keys are large or poorly designed. [`HashMap` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HashMap.html).

### 2.3. When Multiple Results Must Be Produced

Let `r` be the number of result items emitted in a one-to-many or many-to-many join. Building a grouped index and then iterating through the matching groups has an expected cost of **O(m + n + r)**, not always O(m + n).

If every left element matches every right element and the requirement is to output all pairs, `r = n × m`. No lookup structure eliminates the cost of generating results that the problem specification genuinely requires. The benefit of an index is avoiding checks on unrelated pairs.

## 3. The Set Pattern: Only Membership Matters

Suppose we need to keep request codes that appear in an allowed list. The scanning loop uses `break` upon the first match; the result must preserve both the order and multiplicity of the request list.

How to refactor:

1. Create a `HashSet` from the allowed list **before the outer loop**.
2. Continue iterating over the request list in its original order.
3. For each code, call `contains`; if present, append the current element being iterated to the result list.

A Set deduplicates elements on the lookup side, which does not lose duplicates on the request side because we still iterate over the request list. Conversely, if we also converted the result into a Set, we would change the output contract.

Example:

```text
wanted:   [A, C, A, null, B]
allowed:  [B, A, null]
result:   [A, A, null, B]
```

`HashSet` permits the `null` element and does not guarantee iteration order. In this pattern, we do not iterate over the Set to produce output, so the Set's iteration order does not determine the output order. [`HashSet` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HashSet.html).

### When a Set Changes the Problem

If occurrence counts must be enforced, a Set is not enough. For example, if the right side has two `A` codes, the left side has three `A` codes, and each right-side code may only be consumed once: a `contains` check will accept all three, violating the quota-matching requirement.

In that case, you may need a Map counting remaining quantities and decrementing after each match. If the full corresponding records must be retained, you need a Map holding lists rather than just a Set of keys.

## 4. The Map Pattern: Fetching a Single Record by Key

For orders and customers, the natural key can be the customer ID:

```text
customers -> Map<customerId, Customer>
orders    -> look up customerId -> get Customer
```

### 4.1. Duplicate Keys Require a Clear Policy

A Map holds at most one value per key. If two records share the same ID, how the Map is built must accurately reflect the data contract:

| Contract | How to build the index when values are always non-`null` | Meaning |
| --- | --- | --- |
| Key must be unique | Detect duplicates and throw an error | Duplicate data is invalid input |
| Keep the first record | `putIfAbsent` | Matches scanning in order and `break`ing on the first match |
| Keep the last record | `put` in source order | Later record overwrites earlier record |
| Need all records | `Map<K, List<V>>` | Preserves count and order within each group |

Do not use an overwriting `put` and treat it as a behavior-preserving optimization for a scan loop that took the first record. If duplicate data is permitted, choose the proper first/last policy instead of inventing a deduplication rule or throwing an error.

`Collectors.toMap(keyMapper, valueMapper)` does not automatically resolve every contract either: the overload without a merge function throws an exception on duplicate keys. When using the overload with a merge function, that function must express clear domain semantics. [`Collectors` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collectors.html).

### 4.2. Not Found Is Different from a `null` Value

`HashMap.get(key)` can return `null` either when the key is absent or when the key is mapped to a `null` value. If `null` values are permitted, inspecting the return value of `get` alone cannot distinguish the two cases; `containsKey` or a redesigned representation of missing data may be needed.

The example program below specifies that `Customer` values in the index are always non-`null`. Therefore, `get(...) == null` is used to represent a missing match. This invariant belongs to the example, not to every `Map` in general.

### 4.3. Preserving the Join Output

If every order must be retained—even orders whose customer cannot be found—always emit one item per order and handle the missing value. Only skip unmatched rows if the requirement is strictly to keep orders that have a matching customer.

That is the difference between a left join (preserving the entire left side) and an inner join (keeping only matched rows). Optimizing the lookup must not silently change the join type.

## 5. The Map-of-Lists Pattern: Fetching All Matching Records

Suppose an order has multiple order lines. A `Map<orderId, Line>` index would lose data if it overwrote entries. Use:

```java
Map<String, List<Line>> byOrder = new HashMap<>();
for (Line line : lines) {
    byOrder.computeIfAbsent(line.orderId(), key -> new ArrayList<>()).add(line);
}
```

This snippet requires the `Line` type and imports; the complete program in the next section provides them. `computeIfAbsent` creates a list when no value exists for the key, and then appends the line to the group. Do not modify the Map itself inside the mapping function. [`Map.computeIfAbsent` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html#computeIfAbsent(K,java.util.function.Function)).

When iterating through orders:

```java
for (Order order : orders) {
    for (Line line : byOrder.getOrDefault(order.id(), List.of())) {
        result.add(order.id() + ":" + line.sku());
    }
}
```

Syntactically, the code still has two nested loops. The difference is that the inner loop only iterates over the lines belonging to that specific order, rather than scanning all of `lines` each time. Do not judge an algorithm merely by the number of visible loops.

If groups are built in `lines` order, each List in a group preserves that relative order. If `orders` continues to be iterated in its original order, the output preserves the exact order of the original nested scan: order by order, followed by matching lines in source order.

If `orders` repeats the same order ID, the group is emitted again for each occurrence, matching a full nested loop. If two order lines have identical content, the List keeps both. Do not use a Set as the group collection if the requirement is to preserve multiplicity.

## 6. Complete Java 17+ Program: Comparing the Three Patterns

Save the following code as `IndexDemo.java`. Customer data in a valid join has unique IDs; `uniqueCustomers` also demonstrates how to reject data that violates that rule. The Set-based filter actively supports `null` by choosing `HashSet` and using the same `Objects.equals` semantics in the scanning version.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class IndexDemo {
    record Customer(String id, String name) {
        Customer {
            Objects.requireNonNull(id);
            Objects.requireNonNull(name);
        }
    }

    record Order(String id, String customerId) {}
    record Line(String orderId, String sku) {}

    static List<String> filterNested(List<String> wanted, List<String> allowed) {
        List<String> result = new ArrayList<>();
        for (String value : wanted) {
            for (String candidate : allowed) {
                if (Objects.equals(value, candidate)) {
                    result.add(value);
                    break;
                }
            }
        }
        return result;
    }

    static List<String> filterIndexed(List<String> wanted, List<String> allowed) {
        Set<String> allowedIndex = new HashSet<>(allowed);
        List<String> result = new ArrayList<>();
        for (String value : wanted) {
            if (allowedIndex.contains(value)) {
                result.add(value);
            }
        }
        return result;
    }

    static Map<String, Customer> uniqueCustomers(List<Customer> customers) {
        Map<String, Customer> index = new HashMap<>();
        for (Customer customer : customers) {
            Customer previous = index.putIfAbsent(customer.id(), customer);
            if (previous != null) {
                throw new IllegalArgumentException("duplicate customer: " + customer.id());
            }
        }
        return index;
    }

    static List<String> customerJoinNested(List<Order> orders, List<Customer> customers) {
        List<String> result = new ArrayList<>();
        for (Order order : orders) {
            String name = "UNKNOWN";
            for (Customer customer : customers) {
                if (Objects.equals(order.customerId(), customer.id())) {
                    name = customer.name();
                    break;
                }
            }
            result.add(order.id() + "->" + name);
        }
        return result;
    }

    static List<String> customerJoinIndexed(List<Order> orders, List<Customer> customers) {
        Map<String, Customer> byId = uniqueCustomers(customers);
        List<String> result = new ArrayList<>();
        for (Order order : orders) {
            Customer customer = byId.get(order.customerId());
            String name = customer == null ? "UNKNOWN" : customer.name();
            result.add(order.id() + "->" + name);
        }
        return result;
    }

    static List<String> allLinesNested(List<Order> orders, List<Line> lines) {
        List<String> result = new ArrayList<>();
        for (Order order : orders) {
            for (Line line : lines) {
                if (Objects.equals(order.id(), line.orderId())) {
                    result.add(order.id() + ":" + line.sku());
                }
            }
        }
        return result;
    }

    static List<String> allLinesIndexed(List<Order> orders, List<Line> lines) {
        Map<String, List<Line>> byOrder = new HashMap<>();
        for (Line line : lines) {
            byOrder.computeIfAbsent(line.orderId(), key -> new ArrayList<>()).add(line);
        }
        List<String> result = new ArrayList<>();
        for (Order order : orders) {
            for (Line line : byOrder.getOrDefault(order.id(), List.of())) {
                result.add(order.id() + ":" + line.sku());
            }
        }
        return result;
    }

    public static void main(String[] args) {
        List<String> wanted = Arrays.asList("A", "C", "A", null, "B");
        List<String> allowed = Arrays.asList("B", "A", null);
        List<String> filtered = filterIndexed(wanted, allowed);
        System.out.println("membership=" + filtered);
        System.out.println("membership same=" + filtered.equals(filterNested(wanted, allowed)));

        List<Customer> customers = List.of(
                new Customer("c1", "Lan"),
                new Customer("c2", "Minh"));
        List<Order> orders = List.of(
                new Order("o2", "c2"),
                new Order("o1", "c1"),
                new Order("o9", "missing"));

        List<String> names = customerJoinIndexed(orders, customers);
        System.out.println("customer join=" + names);
        System.out.println("customer join same=" + names.equals(customerJoinNested(orders, customers)));

        List<Line> lines = List.of(
                new Line("o1", "pen"),
                new Line("o2", "book"),
                new Line("o1", "ink"),
                new Line("o1", "pen"));
        List<String> allLines = allLinesIndexed(orders, lines);
        System.out.println("line join=" + allLines);
        System.out.println("line join same=" + allLines.equals(allLinesNested(orders, lines)));

        try {
            uniqueCustomers(List.of(
                    new Customer("c1", "Lan"),
                    new Customer("c1", "Other")));
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

Compile and run:

```shell
javac --release 17 IndexDemo.java
java IndexDemo
```

Exact stdout:

```text
membership=[A, A, null, B]
membership same=true
customer join=[o2->Minh, o1->Lan, o9->UNKNOWN]
customer join same=true
line join=[o2:book, o1:pen, o1:ink, o1:pen]
line join same=true
duplicate customer: c1
```

### Reading the Evidence in the Program

- `filterNested` and `filterIndexed` return the same List, containing two occurrences of `A`, one `null`, and preserving the order of `wanted`.
- Both customer joins produce the same result on data satisfying the unique-ID precondition. Order `o9` is still retained with the `UNKNOWN` label.
- Both order-line joins keep both `o1:pen` lines; the indexed version does not lose duplicates.
- The `HashMap` itself is not printed, so stdout does not depend on Map iteration order.
- The duplicate customer ID case is rejected by `uniqueCustomers`. This enforces the declared input precondition. The first-match scanning version does not perform this check, so one must not claim the two methods behave identically across arbitrary invalid inputs.

If first-record behavior must be preserved even when duplicate IDs are allowed, replace the customer index construction with a loop using `putIfAbsent` and **do not throw an exception when a value is already present**. This works in the example because every `Customer` value placed into the Map is non-`null`. If all customers sharing a duplicate ID must be retained, change the index type to a List per key.

The program verifies results on sample inputs; it does not benchmark execution speed or prove every edge condition. In production use, you must test against your own data contracts.

## 7. Designing Keys So the Index Returns the Right Data

### 7.1. Equality Semantics Must Match the Original Scan

If the old loop compared via `customer.id().equals(...)`, indexing by `id` is appropriate. If the old loop compared case-insensitively or normalized whitespace, using the raw string as the key will change the matching relation.

Normalize only according to established domain rules and apply the exact same normalization both when building and when querying the index. Do not arbitrarily call `trim()` or change case on identifiers that are meant to be case- or whitespace-sensitive. For specialized comparisons such as comparator-based equivalence or object identity, double-check carefully because a standard `equals`-based `HashSet` is not necessarily equivalent.

### 7.2. Composite Keys Should Have Clear Structure

If the matching condition consists of a shop ID and a product SKU, a record works well:

```java
record ProductKey(String shopId, String sku) {}

// Illustration inside a method where the corresponding variables exist:
Map<ProductKey, Product> byKey = new HashMap<>();
byKey.put(new ProductKey(product.shopId(), product.sku()), product);
Product found = byKey.get(new ProductKey(shopId, sku));
```

This snippet illustrates key design rather than a standalone program: the `Product` type and variables must be provided by the application. Do not build composite keys by ad-hoc string concatenation without a strict delimiter/encoding scheme; for instance, directly concatenating two components can cause distinct pairs to produce the exact same string.

A record with `String` fields fits this example well because equality is based on stable components. A record containing mutable components still requires caution; shallow immutability of reference fields does not automatically make the entire object graph immutable.

### 7.3. Respecting `equals` and `hashCode`

Objects that are equal according to `equals` must have the same hash code. Conversely, having the same hash code does not prove equality. Using a custom key class that overrides `equals` without overriding `hashCode` can cause the index to fail to find data as expected. [`Object.hashCode` contract](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html#hashCode()).

Do not mutate fields that participate in equality or hash code calculation while an object is serving as a Map key or an element in a hash-based Set. Choosing a stable key separate from a mutable domain entity is usually much easier to manage. The `Map` documentation explicitly warns that behavior is not specified if mutable keys are modified in a manner that affects `equals` comparisons. [`Map` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html).

## 8. Ordering and Index Lifetime

### 8.1. Where Does Result Ordering Come From?

If a Map is only used for `get` lookups while the output is produced by iterating over a source List, the output order comes from that List. You do not need a `LinkedHashMap` just to preserve the order of orders in this pattern.

If you subsequently need to iterate over the groups themselves in the order keys were first encountered, an insertion-ordered `LinkedHashMap` is appropriate. If keys need to be sorted, that is a separate requirement. [`LinkedHashMap` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html).

### 8.2. Building Once at the Right Scope

An example of a flawed optimization:

```java
for (String value : wanted) {
    Set<String> index = new HashSet<>(allowed);
    if (index.contains(value)) {
        result.add(value);
    }
}
```

Rebuilding the same index on every iteration still performs roughly O(n × m) construction work while creating even more allocations. Move index construction outside the lookup loop.

If the same dataset is used across multiple batches, reusing the index can amortize construction cost across many lookups. However, when the source data changes, a previously built index does not automatically update its structure to match the source List.

A Map holds references to data objects rather than deep copies. Consequently, mutating a value's fields may be visible through the reference, whereas adding/removing records or mutating a key does not keep the index valid. You must define a policy for rebuilding, synchronized updates, or using an immutable snapshot of data for the entire operation. Do not promote a local index into a global cache just to save a few builds without addressing data freshness and lifetime.

If multiple threads perform updates, thread safety for both the source data and the index is a dedicated requirement. Switching to a concurrent Map does not automatically turn the sequence "read source → build → query" into a consistent snapshot.

## 9. When Is an Index Not Worth Building or Not Enough?

| Scenario | Evaluation guideline |
| --- | --- |
| Single lookup over a very small collection | A direct scan can be simpler and avoids extra memory |
| Many lookups over the same large collection | Index construction cost amortizes well |
| Tight memory constraints | Account for hash table arrays, nodes, new key objects, and group Lists—not just the element count |
| Matching condition is a range, prefix, or similarity | An equality-keyed hash table does not directly solve the whole problem; bucketing, ordered structures, or another algorithm may be needed |
| Every pair must be processed | Output cost or per-pair work can still be O(n × m) |
| Keys change continuously | Account for the cost of maintaining the index and synchronizing data |

A grouped index can narrow the search space while still requiring secondary filtering within each group. In that case, you must include the cost of the candidate elements actually inspected; do not claim O(n + m) if large buckets are still scanned repeatedly.

## 10. Two-Step Verification of the Optimization

### 10.1. First Prove Correctness

Compare the scanning version and the indexed version across scenarios that match the contract:

- One or both collections are empty.
- No matching elements; all elements match; matches at the first/last position.
- Duplicate elements on the lookup side and on the output-producing side.
- Duplicate keys: unique enforcement, keep-first, keep-last, or keep-all according to the chosen policy.
- `null`, missing values, composite keys, and normalization rules if supported.
- Result List ordering and duplicate counts—do not merely compare a Set of results.

In code with side effects or impure comparison functions, changing the lookup mechanism can also alter invocation counts, invocation order, and when exceptions are thrown. Do not assume that producing the same result set is sufficient if those behaviors are part of the application contract.

### 10.2. Then Measure the Right Scope

If the index is built per request, measure both index construction and output generation together. If the index already exists to serve many lookups, you may measure the lookup phase separately, but you must document where construction and maintenance costs occur.

Test across multiple scales of `n` and `m`, hit rates, and key duplication levels. For multi-match joins, also record `r`. Use JMH when reliable microbenchmarks are needed, and run realistic load tests to verify whether the change actually improves application-level goals. Do not convert lookup counts into fixed millisecond estimates.

## 11. Self-Application Exercise

A program iterates through 200,000 transactions and, for each transaction, scans 80,000 configurations to find the configuration matching the pair `(merchantId, currency)`.

1. Determine whether a Set is sufficient or whether a Map keyed by a composite key is required.
2. Clarify what happens if two configurations share the same key: throw an error, keep the first, keep the last, or merge them?
3. State how transaction order is preserved and how missing matches are handled.
4. Write the cost formula covering index construction, lookups, and output generation; state the assumptions regarding key hashing and comparison.
5. If configurations change mid-processing, define a data versioning strategy or how the index is updated.

A sound solution must eliminate unnecessary repeated searches while preserving the contract for matching semantics, ordering, multiplicity, and missing data.
