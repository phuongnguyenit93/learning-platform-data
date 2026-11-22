# Comprehensive Practice: Range Queries, Nearest Element Search, and Pagination Using Ordered Structures

## 1. Problem and Objectives

Suppose a system stores numeric product codes and needs to answer three types of queries simultaneously:

1. **Range query:** retrieve all codes from `20` (inclusive) to `60` (exclusive).
2. **Nearest element search:** for a requested code `35`, find the existing code with the smallest arithmetic distance; if tied on both sides, choose the smaller code.
3. **Pagination:** return products in ascending code order, up to three products per page, using the last code of the previous page as a cursor to fetch the next page.

If every query re-sorts the entire list and scans from the beginning, unnecessary work is repeated. Java Collections provides `NavigableSet` and `NavigableMap` to maintain order and locate boundaries before or after a key.

After this lesson, you will be able to:

- Choose `TreeSet` when you only need ordered unique values; choose `TreeMap` when each key has associated data.
- Use `subSet`/`subMap`, `headSet`/`headMap`, and `tailSet`/`tailMap` to retrieve ranges with clear boundaries.
- Distinguish `lower`, `floor`, `ceiling`, and `higher`, and handle cases where no element exists on one side.
- Build nearest-match queries and key-based pagination (keyset/cursor pagination), while understanding the limitations when data changes.

## 2. Choosing the Right Ordered Structure

| Requirement | Interface/API | Typical Implementation |
| --- | --- | --- |
| Store *unique* codes while maintaining order | `NavigableSet<E>` | `TreeSet<E>` |
| Map a *unique* code to data | `NavigableMap<K,V>` | `TreeMap<K,V>` |
| Only need ordered iteration without navigation boundary lookups | `SortedSet` / `SortedMap` | `TreeSet` / `TreeMap` still apply |

`TreeSet` and `TreeMap` typically use a balanced red-black tree. With `n` elements, searching, inserting, and removing by key take `O(log n)` time; after locating a boundary, iterating through `k` consecutive elements takes roughly an additional `O(k)`. This fits queries like "find from key X onward and take a few elements."

Ordering comes from `Comparable` (natural ordering) or a `Comparator` passed to the constructor, **not insertion order**. For example, `new TreeSet<>(List.of(40, 10, 30))` iterates as `[10, 30, 40]`.

**Important condition:** in a `TreeSet` or `TreeMap`, two keys are considered duplicates when the comparison returns `0`. For example, when using `String.CASE_INSENSITIVE_ORDER`, `"A"` and `"a"` are the same key in this structure. You should use a comparison consistent with `equals` if you need to fully comply with the `Set`/`Map` contract. If multiple products share the same price, do not use price alone as a unique key; you can use a composite key `(price, product code)` or store a group of products per price.

## 3. Finding Elements Within a Range

A common convention is the half-open interval `[from, to)`: include `from` but exclude `to`. This convention prevents adjacent ranges from overlapping at boundary elements.

~~~java
NavigableSet<Integer> ids = new TreeSet<>(
    List.of(10, 20, 30, 40, 50, 60, 70, 80)
);

NavigableSet<Integer> range = ids.subSet(20, true, 60, false);
// [20, 30, 40, 50]

NavigableSet<Integer> before = ids.headSet(40, false);
// [10, 20, 30]

NavigableSet<Integer> fromHere = ids.tailSet(40, true);
// [40, 50, 60, 70, 80]
~~~

With `subSet(from, fromInclusive, to, toInclusive)`, the two boolean parameters determine whether the endpoints are included. `headSet(bound, inclusive)` retrieves elements before the boundary; `tailSet(bound, inclusive)` retrieves elements from the boundary onward. The corresponding `NavigableMap` methods are `subMap`, `headMap`, and `tailMap`, which operate on **keys**:

~~~java
NavigableMap<Integer, String> products = new TreeMap<>();
products.put(10, "P10");
products.put(20, "P20");
products.put(30, "P30");
products.put(40, "P40");
products.put(50, "P50");

NavigableMap<Integer, String> selected =
    products.subMap(20, true, 50, false);
// keys: [20, 30, 40]
~~~

A few easily overlooked details:

- `subSet`/`subMap` return a **view backed by the original structure**, not an independent copy. Modifications through the view alter the original structure, and modifications to the original structure can appear in the view. If you need an independent snapshot, create `new TreeSet<>(range)` or `new TreeMap<>(selected)`.
- The upper bound must follow or equal the lower bound **according to the active comparator**. With natural ascending order, calling `subSet(60, true, 20, false)` throws an `IllegalArgumentException`.
- On an already restricted view, attempting to create a sub-view that exceeds the existing bounds can also throw an `IllegalArgumentException`.
- An empty range is a valid result: for instance, `subSet(20, false, 20, false)` contains no elements. Do not infer "no data exists at all" solely from an empty range.
- To iterate in descending order, consider `descendingSet()` or `descendingMap()` and re-evaluate how start and end points are interpreted under that view's comparator.

## 4. Finding Lower, Higher, and Nearest Elements

Navigation methods accept a key `x` and locate an element according to comparison order:

| `NavigableSet` Method | Condition of Returned Element | Example when `x = 40` |
| --- | --- | --- |
| `lower(x)` | Greatest element **strictly less than** `x` | `30` |
| `floor(x)` | Greatest element **≤ x** | `40` |
| `ceiling(x)` | Least element **≥ x** | `40` |
| `higher(x)` | Least element **strictly greater than** `x` | `50` |

If no element satisfies the condition, each method returns `null`. With `NavigableMap`, use `lowerKey`/`floorKey`/`ceilingKey`/`higherKey` when you need a key, or `lowerEntry`/`floorEntry`/`ceilingEntry`/`higherEntry` when you need the full key-value pair.

For **numeric keys**, an element nearest in absolute distance must be either `floor(target)` or `ceiling(target)`: every other element is at least as far away as one of these two candidates. You should define a tie-breaking rule when distances are equal (here, preferring the smaller key).

~~~java
static Integer nearest(NavigableSet<Integer> sorted, int target) {
    Integer left = sorted.floor(target);
    Integer right = sorted.ceiling(target);

    if (left == null) return right;  // no lower key exists
    if (right == null) return left;  // no higher key exists

    long leftDistance = (long) target - left;
    long rightDistance = (long) right - target;
    return leftDistance <= rightDistance ? left : right;
}
~~~

For example, `nearest([10,20,30,40,50], 35)` is `30` because `30` and `40` are both five units away from `35`, and the rule selects the smaller side. `nearest(..., 47)` is `50`; an empty set returns `null`. Casting to `long` before subtraction prevents `int` overflow when two keys are very far apart.

**Distinguishing order from distance:** a `Comparator` only tells which key comes first; it **does not automatically define business "closeness"**. For strings, timestamps, coordinates, or composite keys, you must define a clear distance metric before applying a nearest-element algorithm. If you simply want the immediately preceding or succeeding element in sort order, `lower`/`higher` are the appropriate operations.

## 5. Cursor Pagination over Ordered Keys

Suppose the keys are in ascending order: `10, 20, 30, 40, 50, 60, 70, 80`, with at most three keys per page.

- Page 1: start from the beginning; fetch `10, 20, 30`; return `nextCursor = 30` if more data remains.
- Page 2: fetch only keys **> 30** using `tailMap(30, false)`; receive `40, 50, 60`; `nextCursor = 60`.
- Page 3: fetch only keys **> 60**; receive `70, 80`; no data remains, so `nextCursor = null`.

The cursor is the **last returned key**, not an element index or page number. This variant is also known as *keyset pagination*. It locates the starting point by key in roughly `O(log n)` time and then iterates through at most `pageSize + 1` elements both to collect the page and to check whether another page follows, instead of repeatedly skipping thousands of elements via an offset index. With `NavigableMap`, use `tailMap(cursor, false)`; with `NavigableSet`, use `tailSet(cursor, false)`.

The API contract should clarify:

- `cursor = null` on **input** means starting from the beginning of the collection; `nextCursor = null` on **output** means there is no next page.
- `pageSize > 0`, and there should be a maximum limit to prevent overly large requests.
- The key order must be stable; if sorting by multiple fields, the cursor must include all of those fields plus a tie-breaker key to uniquely identify records. For example, when sorting by ascending price and then ascending ID, the cursor must be `(lastPrice, lastId)`.
- The cursor must share the same filtering and sorting order across requests. When the filter or comparator changes, pagination must restart from the beginning.
- When filtering within a bounded range `[min, max)`, the cursor must be validated to fall within the valid range before calling `tailMap` on a bounded view, because an out-of-bounds cursor can trigger an `IllegalArgumentException`.

Pagination over a mutating structure **does not guarantee the same data snapshot across calls**: records inserted after the cursor may appear, records inserted before or at the cursor may be missed, and deleted records will disappear. If business rules require strict consistency across multiple pages, you must use an appropriate snapshot/version or transaction mechanism at the storage layer. `TreeMap`/`TreeSet` are not self-synchronizing; do not modify the structure concurrently while iterating without proper synchronization.

## 6. Complete Java 17 Program

Save the following code as **`OrderedQueriesDemo.java`**. The program uses an ordered set of keys for range and nearest-element queries, and builds an ordered map from the same data to perform pagination. The `pageAfter` method captures returned `Map.Entry` objects using `SimpleImmutableEntry`; the resulting list is not directly coupled to the `TreeMap` after the method returns.

~~~java
import java.util.ArrayList;
import java.util.AbstractMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.NavigableMap;
import java.util.NavigableSet;
import java.util.TreeMap;
import java.util.TreeSet;

public class OrderedQueriesDemo {
    record Page(List<Map.Entry<Integer, String>> items, Integer nextCursor) {}

    static Integer nearest(NavigableSet<Integer> sorted, int target) {
        Integer left = sorted.floor(target);
        Integer right = sorted.ceiling(target);

        if (left == null) return right;
        if (right == null) return left;

        long leftDistance = (long) target - left;
        long rightDistance = (long) right - target;
        return leftDistance <= rightDistance ? left : right;
    }

    static Page pageAfter(
            NavigableMap<Integer, String> rows,
            Integer afterExclusive,
            int pageSize) {

        if (pageSize <= 0) {
            throw new IllegalArgumentException("pageSize must be positive");
        }

        NavigableMap<Integer, String> window =
            afterExclusive == null
                ? rows
                : rows.tailMap(afterExclusive, false);

        Iterator<Map.Entry<Integer, String>> it =
            window.entrySet().iterator();

        List<Map.Entry<Integer, String>> items = new ArrayList<>();
        while (items.size() < pageSize && it.hasNext()) {
            Map.Entry<Integer, String> entry = it.next();
            items.add(new AbstractMap.SimpleImmutableEntry<>(entry));
        }

        Integer nextCursor =
            it.hasNext() && !items.isEmpty()
                ? items.get(items.size() - 1).getKey()
                : null;

        return new Page(List.copyOf(items), nextCursor);
    }

    public static void main(String[] args) {
        NavigableSet<Integer> ids = new TreeSet<>(
            List.of(10, 20, 30, 40, 50, 60, 70, 80)
        );

        System.out.println(
            "Khoang [20, 60): " + ids.subSet(20, true, 60, false)
        );
        System.out.println(
            "floor(35): " + ids.floor(35)
                + ", ceiling(35): " + ids.ceiling(35)
        );
        System.out.println(
            "lower(40): " + ids.lower(40)
                + ", higher(40): " + ids.higher(40)
        );
        System.out.println("Gan 35: " + nearest(ids, 35));
        System.out.println("Gan 68: " + nearest(ids, 68));

        NavigableMap<Integer, String> products = new TreeMap<>();
        for (Integer id : ids) {
            products.put(id, "P" + id);
        }

        Integer cursor = null;
        int pageNumber = 1;
        while (true) {
            Page page = pageAfter(products, cursor, 3);
            System.out.println(
                "Trang " + pageNumber + ": "
                    + page.items().stream().map(Map.Entry::getKey).toList()
                    + ", next=" + page.nextCursor()
            );
            if (page.nextCursor() == null) {
                break;
            }
            cursor = page.nextCursor();
            pageNumber++;
        }
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac OrderedQueriesDemo.java
java OrderedQueriesDemo
~~~

Standard output:

~~~text
Khoang [20, 60): [20, 30, 40, 50]
floor(35): 30, ceiling(35): 40
lower(40): 30, higher(40): 50
Gan 35: 30
Gan 68: 70
Trang 1: [10, 20, 30], next=30
Trang 2: [40, 50, 60], next=60
Trang 3: [70, 80], next=null
~~~

**Explanation:** the range query excludes `60` because the upper bound is exclusive. For `35`, `floor = 30` and `ceiling = 40` are equidistant, so `30` is chosen; for `68`, `70` is closer than `60`. On page 1, after taking three records the iterator still has remaining data, so `nextCursor = 30`. The final page exhausts the data, so `nextCursor = null`. The loop never revisits records prior to the cursor.

In the pagination method, `items` consists of key-value pairs copied into immutable `SimpleImmutableEntry` instances and wrapped in `List.copyOf`. This is a snapshot of *only the current page*, not a snapshot of the entire map across multiple pagination calls.

## 7. Complexity and Approach Trade-offs

| Operation | With `TreeSet` / `TreeMap` | Notes |
| --- | --- | --- |
| `floor`, `ceiling`, `lower`, `higher` | `O(log n)` | Each query locates a single boundary |
| Numeric nearest-element search | `O(log n)` | Two boundary lookups plus an `O(1)` comparison |
| Locate boundary then iterate `k` elements in range | Roughly `O(log n + k)` | No need to copy the entire collection |
| Fetch a page of size `p` by cursor | Roughly `O(log n + p)` | Checks at most one extra element to detect a next page |
| Auxiliary memory of `pageAfter` | `O(p)` | Stores copies of the entries for a single page |

The complexities above describe operations on an already populated tree structure; if the input is an unsorted list, building the `TreeSet`/`TreeMap` also incurs a cost. If you only run a single query on a small list, a linear scan may be simpler. If the system must answer queries continuously while data is inserted and removed, maintaining data in an ordered tree structure offers a much clearer advantage.

When the dataset exceeds memory or pagination must work across multiple machines, use an **ordered database index** with a condition equivalent to `WHERE id > :cursor ORDER BY id LIMIT :pageSize`. The cursor concept remains the same, whereas `TreeMap` is neither a persistent storage engine nor a distributed index.

## 8. Common Mistakes and How to Avoid Them

1. **Confusing inclusive and exclusive bounds.** `tailMap(cursor, true)` causes the last record of the previous page to repeat on the next page. Use `false` when the cursor means "this record has already been emitted."
2. **Using `floor`/`ceiling` instead of "immediately before/after."** When a key matches `x` exactly, both `floor(x)` and `ceiling(x)` can return `x`. If you need a key *different from x*, use `lower(x)`/`higher(x)`.
3. **Forgetting to check for `null`.** On an empty collection or when no elements exist on one side, navigation methods return `null`. Do not unbox to `int` before handling `null`.
4. **Computing distance using `int`.** Subtracting two extreme integers can overflow; cast to `long` before subtracting, and define a clear tie-breaking rule for equidistant candidates.
5. **Using non-unique keys.** `TreeMap` keeps only one value per key according to its comparator; calling `put` with a duplicate key overwrites the previous value. When sorting by price, use price plus ID, or map each price to a collection of multiple products.
6. **Treating a view as an immutable list.** `subSet`, `subMap`, and `tailMap` are live views; mutating the backing structure can affect the contents during iteration. Make an explicit copy when you need an independent snapshot.
7. **Paginating by numeric offset over an ordered set.** `TreeMap` does not provide `O(log n)` access to the "i-th element." Computing `pageIndex * pageSize` does not turn `TreeMap` into a random-access list; use the last key of the previous page when appropriate.
8. **Changing sort order or filters between pages.** A cursor from ascending order cannot be arbitrarily reused for descending order or a different filter. With multiple sort columns, you must use a composite cursor key.
9. **Overlooking concurrent access limitations.** `TreeSet` and `TreeMap` are not thread-safe; iterators typically detect concurrent modifications on a best-effort basis via `ConcurrentModificationException`, and you must not rely on that exception for correctness.

## 9. Self-Check Exercises

**Exercise A — range queries.** Given `ids = [10,20,30,40,50,60,70,80]`, predict the results of:

~~~java
ids.subSet(20, false, 60, true);
ids.headSet(40, true);
ids.tailSet(40, false);
~~~

The answers are `[30, 40, 50, 60]`, `[10, 20, 30, 40]`, and `[50, 60, 70, 80]`, respectively. Each expression tests a different boundary inclusivity combination.

**Exercise B — nearest element at boundaries.** Using the `nearest` method from the program, test `target = 5`, `target = 80`, `target = 85`, and an empty `TreeSet<Integer>`. The results are `10`, `80`, `80`, and `null`, respectively. Explain why `null` candidates must be handled before subtracting distances.

**Exercise C — practical pagination.** Change `pageSize` to `2`. Predict the pages `[10,20]`, `[30,40]`, `[50,60]`, `[70,80]`. The output cursors are `20`, `40`, `60`, and `null`, respectively. Next, try calling `pageAfter(products, 35, 3)` directly; the result must start at `40`, without requiring key `35` to exist in the map.

**Exercise D — extension.** A warehouse needs to filter prices in the range `[100, 500)`, sort by ascending price, and paginate 20 products per page. Design a `Comparator`/key of the form `(price, productId)` so two products with the same price do not overwrite each other. The cursor must contain both `price` and `productId`; the next-page query must compare strictly greater than **the entire composite key**, not just greater than the price. When applying this to a database, preserve the same filter condition and ordering across all pages.

## 10. Implementation Takeaways

`NavigableSet` and `NavigableMap` are well suited when data is ordered and requires boundary-based queries: use `subSet`/`subMap` for range queries, `floor`/`ceiling` to pick the two nearest candidates, and `tailSet`/`tailMap` with an **exclusive** bound for cursor pagination. Choose a clear comparator, handle boundary conditions and `null` values, ensure keys uniquely distinguish records, and define the required data consistency level when paginating across multiple calls.
