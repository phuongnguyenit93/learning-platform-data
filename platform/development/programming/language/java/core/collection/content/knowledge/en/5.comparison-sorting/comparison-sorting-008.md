# Using the Same Comparison Rule for sort, binarySearch, TreeSet, and TreeMap

A comparator decides more than display order. It also answers two critical questions:

1. **Which value comes before or after another?**
2. **Which values are considered tied in rank when the comparison result is 0?**

When a dataset is sorted, searched, and placed into ordered tree structures, all of those places must interpret the answers according to the chosen rule. If each place uses a different rule unintentionally, the results can look contradictory: searches fail to find data, two records get merged, or a `put` operation replaces an existing value instead of increasing the size.

A manageable approach is to define a named rule and pass it explicitly to operations that represent the same data index.

## 1. The Role of a Comparator Across Four Use Sites

| Use Site | What Is the Comparator Used For? | When `compare` Returns 0 |
| --- | --- | --- |
| `list.sort(rule)` | Reorders elements in the list | Tied elements are both kept |
| `Collections.binarySearch(list, key, rule)` | Chooses which half to search and recognizes a matching result | May return the position of any element tied in rank with `key` |
| `new TreeSet<>(rule)` | Organizes the tree, and finds, adds, or removes elements | Treated as the same element according to the tree's ordering |
| `new TreeMap<>(rule)` | Organizes, finds, and updates entries by key | Two keys are treated as the same key according to the tree's ordering |

The common thread is the comparison relation. The difference is **what each structure does with values tied in rank**.

A comparator may have multiple criteria, descending direction, or a null policy. Those details all belong to the rule; they are not cosmetic decoration meant only for sorting.

## 2. First, Give the Entire Rule a Name

Suppose a product has a SKU and a price:

```java
record Product(String sku, int price) {}
```

Requirements for the index:

- Price in ascending order.
- When prices are equal, SKU in ascending `String` order.
- SKU is non-null in the data domain of this example.

Declaration:

```java
private static final Comparator<Product> ORDER =
        Comparator.comparingInt(Product::price)
                .thenComparing(Product::sku);
```

This is a declaration inside a class, not a standalone program.

The name `ORDER` represents **both criteria**, not just price. If the search code accidentally omits `thenComparing`, it changes the meaning of a zero comparison result: from equal price and equal SKU to equal price alone.

Using `comparingInt` instead of subtracting prices avoids introducing integer overflow bugs into the comparator.

### Same Rule Does Not Require the Same Reference

Two separately created comparator objects that produce the same ordering relation over the data domain are behaviorally equivalent.

You do not need to check `sortRule == searchRule`. Nor can you rely entirely on `sortRule.equals(searchRule)` to confirm that two lambda expressions describe the same rule.

Sharing a named constant reduces the risk of configuration drift and makes the intent clear to readers. What ultimately matters is the **actual ordering relation**, not the memory address of the comparator object.

## 3. sort Establishes the Precondition for binarySearch

### 3.1. The List Must Be Sorted According to the Search Comparator

Binary search relies on eliminating half of the data at each step: when comparing the middle element with the search key, it must trust that the values on each side follow the ordering.

Therefore, before calling:

```java
Collections.binarySearch(products, query, ORDER);
```

the list must currently be sorted according to `ORDER`.

Clear usage:

```java
products.sort(ORDER);
int index = Collections.binarySearch(products, query, ORDER);
```

The lines above are an illustration inside a method with appropriate variables in scope.

You must not sort by ascending price and then search by descending price, or sort by SKU and search by price, unless the list simultaneously satisfies the ordering of the search comparator.

When the precondition is not met, the result is undefined. The API does not promise to throw an exception to warn you that you used the wrong comparator. See the [Collections.binarySearch with Comparator contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#binarySearch(java.util.List,T,java.util.Comparator)).

### 3.2. The Exact Requirement Is "Currently Ordered Compatibly"

Using two different comparators does not automatically make a search invalid.

For example, a list sorted by **price then SKU** is also sorted by **price** if the price comparator uses the same direction. Searching by price alone can satisfy the ordering precondition.

However, the question being asked has changed:

- Searching by price then SKU: requires a product matching both price and SKU rank.
- Searching by price alone: requires any product belonging to that price rank.

If the goal is to find a specific SKU, using a price-only comparator violates the intent even though the search algorithm is given a validly ordered list.

Therefore, check both the **ordering precondition** and the **match semantics**, rather than concluding that everything is right simply because `binarySearch` returned a non-negative index.

### 3.3. Do Not Omit the Comparator in Follow-Up Calls

The overload without a comparator uses natural ordering. It does not remember which comparator was used in a previous `sort` call.

```java
List<Integer> numbers = new ArrayList<>(List.of(4, 1, 9));
Comparator<Integer> descending = Comparator.reverseOrder();

numbers.sort(descending);
int index = Collections.binarySearch(numbers, 4, descending);
```

This snippet illustrates a pair of operations sharing the same rule.

Do not replace the final call with the natural-ordering overload and rely on the fact that it might accidentally find `4` in a small dataset. A coincidental match does not validate the precondition.

A list does not carry metadata saying "I was sorted with comparator X." The caller must maintain that information.

## 4. Interpreting binarySearch Results Properly

### 4.1. A Non-Negative Result Is an Element of the Same Rank

When `result >= 0`, the element at that position satisfies:

```text
rule.compare(list.get(result), key) == 0
```

This does not automatically guarantee `list.get(result).equals(key)`, because a comparator may intentionally ignore some differences between objects.

If multiple elements share the same rank, the API does not guarantee whether it returns the first or last element of the group. Retrieving the entire group requires a separate boundary search or an appropriate algorithm.

### 4.2. A Negative Result Encodes the Insertion Point

If no element of the same rank is found:

```text
result = -(insertionPoint) - 1
insertionPoint = -result - 1
```

The insertion point is the index where the element would be placed to preserve the ordering according to the comparator in use. In descending order, the "insertion point" is still defined along the comparator's direction, not by default numeric magnitude.

General handling pattern:

```java
int result = Collections.binarySearch(products, query, ORDER);

if (result >= 0) {
    Product match = products.get(result);
    System.out.println("Found: " + match);
} else {
    int insertionPoint = -result - 1;
    products.add(insertionPoint, query);
}
```

This is an illustrative snippet inside a method. The insertion branch is only appropriate when the list is mutable and the business policy wants to insert `query` when no element of the same rank is present.

Do not use a negative result directly as a list index. A negative result is not always `-1` either: `-1` specifically corresponds to insertion point `0`.

For object arrays, the pair `Arrays.sort(array, rule)` and `Arrays.binarySearch(array, key, rule)` has the same ordering coordination requirements; see the [Arrays.binarySearch API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#binarySearch(T%5B%5D,T,java.util.Comparator)).

## 5. TreeSet Retains the Rule and Uses It Throughout Its Lifecycle

When created with:

```java
TreeSet<Product> orderedSet = new TreeSet<>(ORDER);
```

the tree stores the comparator and uses it for subsequent operations. You do not pass the comparator again to `contains`, `add`, or `remove`.

A pre-sorted list does not automatically teach a `TreeSet` the list's rule:

```java
TreeSet<Product> orderedSet = new TreeSet<>(ORDER);
orderedSet.addAll(products);
```

This explicitly expresses the shared rule.

### Tied in Ordering Means Duplicate in the Tree

If the comparator uses only price, two products with different SKUs but the same price compare as `0`. `TreeSet` treats them as the same element by ordering and therefore does not keep both the way a list does.

Adding the SKU criterion changes the tie relation: products with the same price but different SKUs are distinguished.

However, adding an arbitrary secondary criterion does not automatically make a comparator consistent with the type's `equals` method. You must check the full definition of the type. For the `Product` record in our example, comparing both price and non-null SKU matches the components that the record uses for `equals`.

If the ordering is inconsistent with `equals`, element identity in the tree can diverge from the standard `equals`-based `Set` contract. This must be addressed at the design level, never masked with a broken comparator that artificially returns non-zero for every call. See the [TreeSet API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html).

## 6. TreeMap Applies the Rule to Keys

```java
TreeMap<Product, String> labels = new TreeMap<>(ORDER);
```

Here, `Product` is the **key**, and `String` is the value.

If you put a new `Product` that has the same price and SKU according to `ORDER`, it maps to the same ordered key as the existing key. `put` updates the value for that mapping instead of increasing the key count.

With a price-only comparator, two different SKUs with the same price would also update the same mapping. If the goal is one label per product, that indicates the key rule is not granular enough.

### Do Not Confuse a Key Comparator with a Value Comparator

If the model changes to:

```java
Map<String, Product> bySku;
```

then the rule of a `TreeMap<String, Product>` applies to `String` (the key), not to `Product` (the value).

Sorting a product list by price while storing a map keyed by SKU represents two different indexes, which can be completely reasonable. "Using the same rule" only applies when representing the same relation over the same key/element domain; it does not mean forcing every data structure in an application to share a single comparator.

Key-based lookup operations and the role of the comparator are described in the [TreeMap API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html).

## 7. Complete Program: One Rule Used End-to-End

Save as **SharedOrderingDemo.java**. Prices here are integers used for ordering demonstration; the program is compatible with Java 17 and later.

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.TreeMap;
import java.util.TreeSet;

public class SharedOrderingDemo {
    record Product(String sku, int price) {}

    private static final Comparator<Product> ORDER =
            Comparator.comparingInt(Product::price)
                    .thenComparing(Product::sku);

    private static List<String> describe(Collection<Product> products) {
        return products.stream()
                .map(product -> product.sku() + ":" + product.price())
                .toList();
    }

    public static void main(String[] args) {
        List<Product> products = new ArrayList<>(List.of(
                new Product("D", 300),
                new Product("B", 200),
                new Product("A", 100),
                new Product("C", 200)));

        products.sort(ORDER);
        System.out.println("Sorted: " + describe(products));

        Product query = new Product("C", 200);
        int found = Collections.binarySearch(products, query, ORDER);
        System.out.println("Found index: " + found);

        Product missing = new Product("X", 200);
        int result = Collections.binarySearch(products, missing, ORDER);
        int insertionPoint = -result - 1;
        System.out.println("Missing result: " + result);
        System.out.println("Insertion point: " + insertionPoint);

        TreeSet<Product> orderedSet = new TreeSet<>(ORDER);
        orderedSet.addAll(products);
        System.out.println("TreeSet: " + describe(orderedSet));
        System.out.println("TreeSet contains C: " + orderedSet.contains(query));
        System.out.println("TreeSet contains X: " + orderedSet.contains(missing));

        TreeMap<Product, String> labels = new TreeMap<>(ORDER);
        for (Product product : products) {
            labels.put(product, "label-" + product.sku());
        }
        String previous = labels.put(new Product("C", 200), "updated");
        System.out.println("TreeMap key order: "
                + describe(labels.navigableKeySet()));
        System.out.println("Previous C label: " + previous);
        System.out.println("Current C label: " + labels.get(query));
        System.out.println("TreeMap size: " + labels.size());

        products.add(insertionPoint, missing);
        System.out.println("After ordered insert: " + describe(products));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SharedOrderingDemo.java
java SharedOrderingDemo
```

Stdout:

```text
Sorted: [A:100, B:200, C:200, D:300]
Found index: 2
Missing result: -4
Insertion point: 3
TreeSet: [A:100, B:200, C:200, D:300]
TreeSet contains C: true
TreeSet contains X: false
TreeMap key order: [A:100, B:200, C:200, D:300]
Previous C label: label-C
Current C label: updated
TreeMap size: 4
After ordered insert: [A:100, B:200, C:200, X:200, D:300]
```

### 7.1. Ordering and Searching

The list is sorted by price then SKU:

```text
A:100 -> B:200 -> C:200 -> D:300
```

The query `C:200` matches a single rank in this dataset, so it is found at index `2`.

The query `X:200` is absent. It belongs after `C:200` and before `D:300`. Its insertion point is `3`, encoded as `-4`.

The code decodes the insertion point directly in the program only because the query `X:200` is known in advance to be missing. For a general query, always branch on the sign of the result as shown earlier.

### 7.2. Tree Set and Tree Map

`TreeSet` retains both `B:200` and `C:200` because SKU is the secondary criterion. It finds `C:200`, and does not treat `X:200` as already present merely because it shares price `200`.

`TreeMap` traverses its keys in the same order. `new Product("C", 200)` is a new object instance, but it compares as `0` against the existing key, so `put` returns the old label and replaces it with the new label. The map size remains `4`.

### 7.3. Adding to the List Does Not Automatically Update the Trees

The final line inserts the missing query into the list at the calculated insertion point, preserving the list's ordering.

`TreeSet` and `TreeMap` are independent data structures in this example. Adding to `products` does not automatically add to them. "Same comparator" means the same comparison rule, not automatic content synchronization.

If an application maintains multiple indexes over the same data, you must design a consistent update mechanism or designate a single source of truth from which projections are rebuilt.

## 8. Comparator Equivalence Is Not Always `equals`

To see this clearly, let's use a case-insensitive string comparison rule.

Save as **ComparisonEquivalenceDemo.java**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.TreeMap;
import java.util.TreeSet;

public class ComparisonEquivalenceDemo {
    public static void main(String[] args) {
        Comparator<String> rule = String.CASE_INSENSITIVE_ORDER;
        List<String> names =
                new ArrayList<>(List.of("beta", "ALPHA", "alpha", "Gamma"));
        names.sort(rule);

        String query = "AlPhA";
        int index = Collections.binarySearch(names, query, rule);
        String matched = names.get(index);

        System.out.println("Sorted: " + names);
        System.out.println("Binary search found: " + (index >= 0));
        System.out.println("Comparator match: " + (rule.compare(matched, query) == 0));
        System.out.println("Equals match: " + matched.equals(query));
        System.out.println("List contains exact query: " + names.contains(query));

        TreeSet<String> set = new TreeSet<>(rule);
        set.addAll(names);
        System.out.println("TreeSet size: " + set.size());
        System.out.println("TreeSet contains query: " + set.contains(query));

        TreeMap<String, Integer> counts = new TreeMap<>(rule);
        counts.put("ALPHA", 1);
        Integer previous = counts.put("alpha", 2);
        System.out.println("TreeMap previous: " + previous);
        System.out.println("TreeMap size: " + counts.size());
        System.out.println("TreeMap query value: " + counts.get(query));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ComparisonEquivalenceDemo.java
java ComparisonEquivalenceDemo
```

Stdout:

```text
Sorted: [ALPHA, alpha, beta, Gamma]
Binary search found: true
Comparator match: true
Equals match: false
List contains exact query: false
TreeSet size: 3
TreeSet contains query: true
TreeMap previous: 1
TreeMap size: 1
TreeMap query value: 2
```

### 8.1. Why Not Print the Specific Index Within the Alpha Group?

`"ALPHA"` and `"alpha"` have the same rank under `String.CASE_INSENSITIVE_ORDER`. The query `"AlPhA"` also belongs to that rank.

Binary search may return any matching position in the group, without guaranteeing the first or the last. The program prints only what is guaranteed: a match was found, the comparison result is `0`, and `equals` against the query is `false`.

`List.sort` keeps both elements; stability keeps `"ALPHA"` before `"alpha"` because that was their initial relative order. See the [List.sort API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)).

### 8.2. Why Do `List.contains` and `TreeSet.contains` Differ?

`names.contains(query)` uses element equality (`equals`). Because the dataset does not contain the exact string `"AlPhA"`, the result is `false`.

`TreeSet.contains(query)` uses the tree's comparison rule, so the result is `true`. The two alpha strings occupy only one rank in the tree; combined with `beta` and `Gamma`, the size is `3`.

Here the comparator is intentionally inconsistent with `String.equals`. The example demonstrates the consequences so you can recognize them; you should not casually use such a set and expect all operations with `equals`-based collections to preserve the same semantics.

If business logic treats case variants of a name as the same key, define a clear key policy or canonical representation. Do not let different parts of the codebase silently normalize keys in different ways.

### 8.3. Why Doesn't `put` Create a Second Key?

`TreeMap` receives `"ALPHA"` and then `"alpha"`. Both compare as `0` under the map's rule, so the second call replaces the value from `1` to `2`. Querying with the variant `"AlPhA"` retrieves `2`.

`String.CASE_INSENSITIVE_ORDER` is a Java string comparison rule; it does not automatically provide locale-sensitive collation for every language. If an application requires locale-specific ordering rules, choose them explicitly and apply them consistently. See the [String.CASE_INSENSITIVE_ORDER API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#CASE_INSENSITIVE_ORDER).

## 9. Refining a Rule Can Change Match Results Too

Consider two rules:

```java
Comparator<Product> priceOnly =
        Comparator.comparingInt(Product::price);

Comparator<Product> priceThenSku =
        priceOnly.thenComparing(Product::sku);
```

If the dataset contains `B:200` and `C:200`:

| Use Site | Price Only | Price Then SKU |
| --- | --- | --- |
| List sort | Both elements are tied | `B` comes before `C` |
| Binary search for `X:200` | May match an element with price 200 | Does not find `X:200` |
| `TreeSet` | `B` and `C` share one rank; only one representative is kept | Keeps both `B` and `C` |
| `TreeMap` with `Product` as key | `B` and `C` belong to the same ordered key | Can hold two distinct mappings |

Do not add a secondary criterion in just one place to "make the output order look nicer" without considering how it changes the compare-to-zero condition.

Similarly, flipping ascending to descending or changing null placement in the sort code while leaving the search code unchanged can break the precondition.

If you want all products at a given price point, finding a single index with binary search is not enough to retrieve the whole group. Choose a range search operation or a price-based index suited to that goal.

## 10. Changes That Invalidate the Ordering

### 10.1. Mutating the List After Sorting

Once a list is sorted, operations such as appending an element that belongs in the middle, replacing an element at an arbitrary index, or calling `shuffle` can break the ordering precondition.

Your options:

- Compute the insertion index using the same comparator.
- Re-sort before searching.
- Use a data structure that maintains ordering automatically when updates are frequent.

Re-sorting is unnecessary if an operation genuinely preserves the ordering, but there must be a clear justification for that guarantee.

### 10.2. Mutating Properties Used as Comparison Keys

A list whose elements have not changed positions can still lose its ordering if a price field inside an element is mutated in place.

With trees, the problem is even worse because the element or key has already been placed at a specific node position. A tree does not automatically detect that an object's field changed and rebalance the node to a new location.

Key objects whose ordering fields are immutable are much easier to manage. If an ordering field must be updated, remove the entry while the old value is still intact, create or update the object, and re-insert it. Using a `Product` record with `String` and `int` components prevents direct in-place mutation of those fields.

### 10.3. Mutating Comparator Configuration

A comparator that reads a mutable weight table or a toggleable sort-direction flag can also change the comparison rule underneath a collection without the collection itself being modified.

Avoid changing a live tree's comparator behavior mid-stream. If the ordering policy changes, rebuild the structure under the new rule or perform a controlled migration.

Multithreading makes all of these issues more severe. Sharing a comparator does not provide thread synchronization for a `List`, `TreeSet`, or `TreeMap`.

## 11. Notes on Copying and Converting Between Structures

### 11.1. Constructors Do Not Always Inherit the Source's Comparator

Constructors that accept a general `Collection` cannot infer a comparator from the order in which elements happen to arrive:

```java
// Product does not implement Comparable.
// Do not use this expecting it to inherit ORDER from a List:
// TreeSet<Product> set = new TreeSet<>(products);
```

The `TreeSet(Collection)` constructor uses natural ordering. The `TreeSet(SortedSet)` constructor has a specific contract to preserve the ordering of the source sorted set.

Similarly:

- `TreeMap(Map)` orders by the natural ordering of keys.
- `TreeMap(SortedMap)` uses the ordering of the source sorted map.

Overload resolution depends on the static type of the argument, so verify which constructor is actually being called. The transparent approach used in our example is to construct the tree explicitly with `ORDER` and then add the data.

### 11.2. A List Copied from a Tree Does Not Carry the Comparator

`new ArrayList<>(orderedSet)` receives elements in the tree's iterator order at the time of copying, but the list itself does not store the tree's comparator.

When running binary search on that list, you must pass the appropriate rule again. You can obtain the rule from `sortedSet.comparator()` or `sortedMap.comparator()`; a `null` return value from these methods indicates natural ordering.

Do not misinterpret that `null` return value as a "nulls-first" or "nulls-last" policy for data elements.

### 11.3. A Key-Ordered TreeMap Does Not Keep Values Sorted

A list created from `treeMap.values()` follows the key order of the map. It is not automatically sorted according to a comparator on the values.

Only run binary search on values if the current value list genuinely satisfies the value ordering, or after sorting it explicitly with the value comparator.

## 12. Verification and Diagnostics

A useful check for a list's ordering precondition is verifying every adjacent pair:

```java
// Illustrative method, placed in a class with appropriate imports.
static <T> boolean isSorted(
        List<T> values, Comparator<? super T> rule) {
    for (int i = 1; i < values.size(); i++) {
        if (rule.compare(values.get(i - 1), values.get(i)) > 0) {
            return false;
        }
    }
    return true;
}
```

This checks the current ordering against the supplied comparator. It does not by itself prove that the comparator is transitive across all triples or safe against concurrent modification. For large linked lists, indexed loop access also carries performance costs; the snippet focuses on illustrating the ordering invariant.

When you encounter unexpected results, check in order:

1. What comparator is actually passed to `sort` and `binarySearch`?
2. Was a secondary criterion omitted, the direction reversed, or the null policy changed at one of the call sites?
3. Does the search query populate all fields required by the comparison key?
4. Was the list added to, modified, reordered, or had element fields mutated after sorting?
5. Is the expected match based on `compare == 0` or `equals`?
6. Which comparator is the tree using, and which constructor overload was invoked?
7. Are you expecting a tree to retain multiple elements that the comparator considers tied in rank?

If you only know a product's SKU, but the index order is price then SKU, you cannot arbitrarily plug a dummy price into the query and treat it as a SKU lookup. Choose an index keyed by SKU—such as a `Map` with SKU as the key—or filter with an appropriate predicate.

## 13. Self-Check Exercises

1. Sort a list of numbers in descending order, then write the matching `binarySearch` call. Explain why the natural-ordering overload does not remember the sort rule.
2. Using `priceThenSku`, calculate the negative return value and insertion point for a product with an existing price but a missing SKU.
3. If you use `priceOnly` to search a list sorted by `priceThenSku`, the ordering precondition may still hold—how does the meaning of "found" change?
4. Predict the sizes of a `List`, `TreeSet`, and `TreeMap` when given two products with different SKUs but the same price, under each comparator.
5. Copy a `TreeSet` into an `ArrayList`. State the two pieces of information that must be preserved for `binarySearch` to work properly after copying.
6. Describe how to update the price of a key currently stored in a `TreeMap` without leaving the tree structure dependent on stale comparison key data.

The goal is to keep a clear chain of contracts: **the rule that defines ordering, the precondition for searching, the compare-to-zero equivalence relation, and how each structure identifies elements or keys**. Whenever you change the rule, re-evaluate the entire chain rather than just looking at the printed sort order.
