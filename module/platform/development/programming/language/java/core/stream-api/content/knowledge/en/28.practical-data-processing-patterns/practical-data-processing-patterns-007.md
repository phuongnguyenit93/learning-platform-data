# In-Memory Data Pagination and the Limits of `skip` and `limit`

## 1. Lesson Objectives and Real-World Scenario

In the **Java Stream API** (`JAVA_STREAM_API`), declarative data processing typically consists of a source, lazy intermediate operations such as `filter` and `map`, and a terminal operation such as `collect`. When data already resides in RAM yet the UI displays only one slice at a time, we need **pagination**: extracting a slice of the result set by page number and page size.

For example, an application has 23 products, and the screen displays at most 5 products per page. The user selects the third page; the program must return the exact products for that page, along with total page count and whether a next page exists.

The Stream API provides two intermediate operations:

- `skip(n)`: discards **at most the first `n` elements** of the stream in encounter order, if the stream is ordered.
- `limit(n)`: retains **at most the first `n` elements** of the remaining stream.

A basic pagination pipeline:

```java
List<T> items = source.stream()
    .skip(offset)
    .limit(pageSize)
    .collect(Collectors.toList());
```

This is a **practical data processing pattern**, yet `skip` and `limit` alone do not solve everything: page-numbering conventions, `offset` overflow, total result counts, empty data, filtering and sorting, data mutations between page fetches, deep-skip cost, and parallel stream semantics.

After this lesson, you will be able to:

1. Compute `offset` from `pageIndex` and `pageSize`, and handle empty pages and invalid inputs.
2. Explain how `skip` and `limit` interact with `filter`, `sorted`, `distinct`, and `map`.
3. Choose between `List.subList` and a Stream pipeline when data already lives in memory.
4. Design a `Page<T>` carrying data, total records, total pages, and navigation metadata.
5. Distinguish **encounter order**, display order, and stability across pagination requests.
6. Recognize performance limits on large datasets, deep pages, or parallel execution.
7. Write tests verifying no dropped or duplicated elements when stitching pages from a single data snapshot.

This lesson belongs to the **Practical Data Processing Patterns** chapter and connects with grouping, collectors, `Spliterator`, and the state, resource, and performance limits of the Java Stream API.

## 2. Page Conventions and Basic Formulas

In this lesson, **`pageIndex` is 0-based**:

| `pageIndex` | UI Page Displayed to User | `pageSize` | `offset` | Positions Retrieved |
| ---: | ---: | ---: | ---: | --- |
| 0 | 1 | 5 | 0 | 0–4 |
| 1 | 2 | 5 | 5 | 5–9 |
| 2 | 3 | 5 | 10 | 10–14 |
| 3 | 4 | 5 | 15 | 15–19 |
| 4 | 5 | 5 | 20 | 20–22 (given 23 elements) |
| 5 | 6 | 5 | 25 | Empty |

Formulas:

```text
offset = pageIndex * pageSize

fromInclusive = offset
toExclusive   = min(totalElements, offset + pageSize)

totalPages = ceil(totalElements / pageSize)
```

**Warning:** computing `offset` as `int pageIndex * int pageSize` can overflow `int` **before the result is widened to `long`**. Cast before multiplying or use `Math.multiplyExact`.

```java
int pageIndex = 2;
int pageSize = 5;

// Good for two non-negative ints: promote to long before multiplying.
long offset = (long) pageIndex * pageSize;

System.out.println(offset); // 10
```

If your API accepts `long pageIndex` or can receive very large values, use `Math.multiplyExact(pageIndex, (long) pageSize)` to **detect `long` overflow**. Never handle overflow by passing a negative offset into `skip`.

### 2.1. Valid Input Conditions

A clear contract:

- `pageIndex >= 0`.
- `pageSize > 0`.
- `offset >= 0` and multiplication does not overflow.
- A page past the end of data **returns an empty list**, not an error, if that is the API contract.
- Empty data has `totalElements = 0` and `totalPages = 0` under this lesson's convention.

`skip(n)` and `limit(n)` throw `IllegalArgumentException` if `n < 0`. Notably, `limit(0)` is valid in Stream API and returns an empty result; **do not conflate** that with accepting `pageSize = 0` in pagination, which produces no navigable page.

If the UI uses 1-based page numbers, convert explicitly to the internal index:

```java
long pageNumber = 3L; // User selects page 3.
if (pageNumber < 1) {
    throw new IllegalArgumentException(
        "pageNumber must start from 1");
}
long pageIndex = pageNumber - 1L; // 2
```

Never mix `pageNumber` (1-based) and `pageIndex` (0-based) in the same formula. That is a classic cause of off-by-one bugs.

## 3. First Example with `skip` and `limit`

Java 8+ example:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class SimplePaging {
    public static void main(String[] args) {
        List<String> ten = Arrays.asList(
            "An", "Binh", "Chi", "Dung", "Giang",
            "Ha", "Hieu", "Khanh", "Lan", "Minh",
            "Nam", "Oanh"
        );

        int pageSize = 5;
        int pageIndex = 1; // Page 2 in UI.

        long offset = (long) pageIndex * pageSize;

        List<String> page = ten.stream()
            .skip(offset)
            .limit(pageSize)
            .collect(Collectors.toList());

        System.out.println(page);
        // [Ha, Hieu, Khanh, Lan, Minh]
    }
}
```

Explanation:

```text
Source:    [An, Binh, Chi, Dung, Giang, Ha, Hieu, Khanh, Lan, Minh, Nam, Oanh]
                    skip(5) ─────────────┘
Remaining: [Ha, Hieu, Khanh, Lan, Minh, Nam, Oanh]
                    limit(5) ────────────┘
Result:    [Ha, Hieu, Khanh, Lan, Minh]
```

`skip` **does not mutate `ten`**, and `limit` does not materialize an independent list until a terminal operation runs. `collect` consumes the pipeline and creates the result collection.

### 3.1. Boundary Cases

```java
List<Integer> so = Arrays.asList(10, 20, 30);

System.out.println(
    so.stream().skip(0).limit(2)
        .collect(Collectors.toList())
); // [10, 20]

System.out.println(
    so.stream().skip(2).limit(2)
        .collect(Collectors.toList())
); // [30]

System.out.println(
    so.stream().skip(3).limit(2)
        .collect(Collectors.toList())
); // []

System.out.println(
    so.stream().skip(100).limit(2)
        .collect(Collectors.toList())
); // []

System.out.println(
    so.stream().skip(1).limit(0)
        .collect(Collectors.toList())
); // []
```

When `skip` exceeds the element count, nothing remains for `limit` to take. **No extra elements are synthesized** to pad a page.

Also remember a stream **can be consumed only once**: in this snippet, each statement opens a fresh stream via `so.stream()`. Never store a `Stream` and invoke `collect` a second time on the same consumed instance.

## 4. Operation Order Determines Each Page's Content

`skip` and `limit` slice the **element stream at the exact point where they appear in the pipeline**. Moving `filter`, `sorted`, or `distinct` can completely alter the answer.

### 4.1. Filter First, Then Paginate

Suppose the source is `[1, 2, 3, ..., 10]`. The UI displays only **even numbers**, 3 per page. `pageIndex = 0` must show `[2, 4, 6]`, and the next page `[8, 10]`.

```java
import java.util.stream.IntStream;

List<Integer> dung = IntStream.rangeClosed(1, 10)
    .boxed()
    .filter(n -> n % 2 == 0)
    .skip(0)
    .limit(3)
    .collect(Collectors.toList());

System.out.println(dung); // [2, 4, 6]
```

If you paginate **before** filtering:

```java
List<Integer> saiYeuCau = IntStream.rangeClosed(1, 10)
    .boxed()
    .skip(0)
    .limit(3)
    .filter(n -> n % 2 == 0)
    .collect(Collectors.toList());

System.out.println(saiYeuCau); // [2]
```

The second pipeline is valid Java, yet it returns a **page with only one element** even though plenty of even numbers exist. The two forms express **two different requirements**:

- `filter(...).skip(...).limit(...)`: paginate the **filtered result set**.
- `skip(...).limit(...).filter(...)`: take a slice of the **raw data** and filter only within that slice.

In search UIs and filtered lists, **filtering before pagination** is almost always the intended behavior.

### 4.2. Sort First, Then Paginate

```java
List<Integer> so = Arrays.asList(9, 1, 7, 2, 5);

List<Integer> dung = so.stream()
    .sorted()
    .skip(2)
    .limit(2)
    .collect(Collectors.toList());

List<Integer> khac = so.stream()
    .skip(2)
    .limit(2)
    .sorted()
    .collect(Collectors.toList());

System.out.println(dung); // [5, 7]
System.out.println(khac); // [2, 7]
```

`sorted().skip(2).limit(2)` selects the 3rd and 4th elements of the **entire sorted dataset**. `skip(2).limit(2).sorted()` sorts only the two elements from the original slice. When the UI expects **globally sorted results**, sort before slicing.

### 4.3. Deduplicate First, Then Paginate

```java
List<String> ma = Arrays.asList("A", "B", "A", "C", "D");

List<String> uniquePage = ma.stream()
    .distinct()
    .skip(2)
    .limit(2)
    .collect(Collectors.toList());

List<String> pageThenDistinct = ma.stream()
    .skip(2)
    .limit(2)
    .distinct()
    .collect(Collectors.toList());

System.out.println(uniquePage);        // [C, D]
System.out.println(pageThenDistinct);  // [A, C]
```

If the requirement is paginating **unique codes**, put `distinct` before `skip`/`limit`. Calling `distinct` after slicing cannot prevent the same code from appearing across **two different pages**.

### 4.4. `map` Before or After Slicing?

If `map` is a **pure, one-to-one** transformation (neither dropping nor adding elements) and ordering is unaffected, you can map after `skip`/`limit` to transform only the items on the requested page:

```java
List<String> ten = Arrays.asList("java", "go", "kotlin", "rust");

List<String> page = ten.stream()
    .skip(2)
    .limit(2)
    .map(String::toUpperCase)
    .collect(Collectors.toList());

System.out.println(page); // [KOTLIN, RUST]
```

However, if you need to **sort or filter by the mapped value**, `map` must run early enough. And if `map` had side effects, moving it would change how often or under what conditions it runs; side effects should never form the logic of a pagination pipeline.

## 5. Stable Pages Require a Defined Encounter Order

On an `ArrayList` or array, streams have positional encounter order. On an **unordered source** such as `HashSet`, or a pipeline calling `unordered()`, "skip the first 10 elements" **does not identify 10 fixed business items**.

```java
import java.util.HashSet;
import java.util.Set;

Set<Integer> nguon = new HashSet<>(Arrays.asList(5, 1, 4, 2, 3));

List<Integer> page = nguon.stream()
    .skip(2)
    .limit(2)
    .collect(Collectors.toList());

// Do not rely on the specific contents of page to define a page.
```

To paginate deterministically by value, establish order via `sorted`:

```java
List<Integer> page = nguon.stream()
    .sorted()
    .skip(2)
    .limit(2)
    .collect(Collectors.toList());

System.out.println(page); // [3, 4]
```

`unordered()` **does not force shuffling** on a single run, yet it drops the encounter-order guarantee, making it unsuitable when users expect pages 1, 2, and 3 to remain consistent under a defined ordering.

### 5.1. Stable Encounter Order Alone Is Insufficient If the Source Mutates

Even with a `List`, data can change **between two page requests**:

```text
Initially: [A, B, C, D, E, F]
Page 1:    [A, B, C]

Insert X at the front before loading page 2:
After insert: [X, A, B, C, D, E]
Page 2 (skip 3): [C, D, E]
```

Element `C` appears on both pages. Conversely, deletions or moves can cause users to **miss** an item.

This is **not a bug specific to `skip`**: offset pagination depends on positions in the collection at **query time**. When users need consistent paging across multiple requests, use a stable snapshot, data versioning, or a cursor/keyset strategy depending on the system.

### 5.2. Sort by a Unique Key to Avoid Ties

When multiple records share the same score or timestamp, `sorted` on that single field does not produce a **unique** business order. On an ordered source, Java preserves encounter order among tied items; however, if the source is unordered or reloaded in another order, pages can shift.

Append a **tie-breaker** such as a unique identifier:

```java
Comparator<SanPham> theoGiaRoiMa =
    Comparator.comparingLong((SanPham p) -> p.gia)
        .thenComparing(p -> p.ma);
```

Assume `SanPham` has a `long gia` field and a non-null `String ma` field. A unique secondary key yields a clean total order, though it still cannot **prevent insertions/deletions between requests**; that requires fixing a snapshot or switching pagination strategies.

## 6. Safe `offset` Calculation Without Overflow

Do not write the following if page numbers can be large:

```java
int pageIndex = 1_500_000_000;
int pageSize = 100;

// WRONG: int multiplication overflows before widening to long.
long offsetSai = pageIndex * pageSize;
```

A validation and offset calculation helper for a 0-based API:

```java
static long checkedOffset(long pageIndex, int pageSize) {
    if (pageIndex < 0) {
        throw new IllegalArgumentException("pageIndex must be >= 0");
    }
    if (pageSize <= 0) {
        throw new IllegalArgumentException("pageSize must be > 0");
    }

    try {
        return Math.multiplyExact(pageIndex, (long) pageSize);
    } catch (ArithmeticException ex) {
        throw new IllegalArgumentException("offset overflowed long", ex);
    }
}
```

Java 8's `Math.multiplyExact(long, long)` catches overflow instead of silently wrapping to a bad offset. If a valid offset exceeds element count, the resulting page is **empty**; these are two distinct states:

- **Invalid request**: negative `pageIndex`, non-positive `pageSize`, or overflowed multiplication.
- **Valid empty page**: valid offset with no remaining elements.

Do not "fix" an out-of-range request by clamping `Math.min(offset, total)` or silently redirecting to page 0. Callers need to know the requested page has no data.

### 6.1. Total Page Count Without Overflowing Rounding

Given non-negative `totalElements` and `pageSize > 0`:

```java
static long totalPages(long totalElements, int pageSize) {
    if (totalElements < 0 || pageSize <= 0) {
        throw new IllegalArgumentException("invalid metadata");
    }

    return totalElements == 0
        ? 0
        : 1 + (totalElements - 1) / pageSize;
}
```

Avoid `(totalElements + pageSize - 1) / pageSize` when `totalElements` can approach `Long.MAX_VALUE`, because the addition can overflow. `1 + (totalElements - 1) / pageSize` avoids adding `pageSize` to a huge total.

Examples:

```text
totalElements = 0, pageSize = 5  → totalPages = 0
totalElements = 5, pageSize = 5  → totalPages = 1
totalElements = 6, pageSize = 5  → totalPages = 2
totalElements = 23, pageSize = 5 → totalPages = 5
```

Defining `totalPages = 0` when there are zero records is an explicit choice. Some UIs still display an empty "Page 1"; that is a **presentation convention**, not an indication that a page of real data exists.

## 7. `List.subList`: A More Direct Option When Data Is Already in RAM

Once you hold a complete `List<T>`, especially an `ArrayList`, you can slice pages by index:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

List<Integer> so = Arrays.asList(10, 20, 30, 40, 50, 60, 70);
int from = 3;
int to = Math.min(from + 3, so.size());

List<Integer> page = new ArrayList<>(so.subList(from, to));

System.out.println(page); // [40, 50, 60]
```

`subList(fromInclusive, toExclusive)` slices the half-open interval `[from, to)`. Indices must remain within bounds with `from <= to`; otherwise the list throws index-bounds exceptions.

### 7.1. View vs. Copy

**`source.subList(from, to)` returns a *view* backed by the original list**, not an independent snapshot. Therefore:

```java
List<String> source = new ArrayList<>(
    Arrays.asList("A", "B", "C", "D"));

List<String> view = source.subList(1, 3);
System.out.println(view); // [B, C]

view.set(0, "X");
System.out.println(source); // [A, X, C, D]
```

Modifications through `view` reflect in the source list. If the source is structurally modified outside the view, the view's behavior becomes undefined per the `List.subList` contract.

When returning page data to another layer or wanting a stable slice snapshot, copy it:

```java
List<String> copy = new ArrayList<>(source.subList(1, 3));
```

`copy` decouples list structure from the source. This is a **shallow copy**: if elements are mutable objects, mutating an object's fields remains visible across all references to that object.

### 7.2. Choosing `subList` vs. `stream().skip().limit()`

| Criterion | `List.subList(from, to)` | `stream().skip(offset).limit(size)` |
| --- | --- | --- |
| Source | Requires a `List` | Any suitable `Stream` source |
| Direct index slicing | Explicit | Expressed by elements skipped/retained |
| Initial result | View of original list | Intermediate Stream, not yet a list |
| Independent list | Wrap in `new ArrayList<>(...)` | Collect with `collect(Collectors.toList())` |
| Combined with `filter` / `map` | Needs prior step or separate loop | Natural inside the pipeline |
| Deep pages on `ArrayList` | Indexed slice, avoids walking skipped items | `skip` may have to advance past prefixes; runtime may optimize depending on source |
| `LinkedList` source | Index access / slicing can be costly | Also traverses elements; measure if large |

**Never claim `skip` is always O(offset) in every case.** On `SIZED` / `SUBSIZED` sources splittable by position, the runtime may optimize skipping. Yet the API does not guarantee instant random access for arbitrary `Stream`s, especially with `filter` upstream or sequential sources.

When your source is already a large `ArrayList` and you only want a slice, `subList` plus copying that slice is usually **simpler with more predictable cost**.

## 8. Complete Example: `Page<T>` with Metadata and Both Slicing Approaches

Real-world pagination needs more than a list: **total elements**, **total pages**, **page index**, and **hasNext**. The Java 8+ program below implements:

- `checkedOffset` for input validation and overflow detection.
- `pageByStream` using `skip`/`limit`.
- `pageByList` using `subList`.
- `Page<T>` carrying content and metadata; content is wrapped in a structurally unmodifiable list.

Complete single-file `InMemoryPaginationDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

public class InMemoryPaginationDemo {
    static final class Page<T> {
        final long pageIndex;
        final int pageSize;
        final long totalElements;
        final long totalPages;
        final List<T> items;

        Page(long pageIndex, int pageSize,
                long totalElements, List<T> items) {

            this.pageIndex = pageIndex;
            this.pageSize = pageSize;
            this.totalElements = totalElements;
            this.totalPages = totalElements == 0
                ? 0
                : 1 + (totalElements - 1) / pageSize;

            // Structural copy; never expose a mutable internal list.
            this.items = Collections.unmodifiableList(
                new ArrayList<>(items));
        }

        boolean hasNext() {
            return pageIndex < totalPages - 1;
        }

        @Override
        public String toString() {
            return "Page{index=" + pageIndex
                + ", size=" + pageSize
                + ", total=" + totalElements
                + ", pages=" + totalPages
                + ", next=" + hasNext()
                + ", items=" + items + "}";
        }
    }

    static long checkedOffset(long pageIndex, int pageSize) {
        if (pageIndex < 0 || pageSize <= 0) {
            throw new IllegalArgumentException(
                "pageIndex >= 0 and pageSize > 0");
        }

        try {
            return Math.multiplyExact(pageIndex, (long) pageSize);
        } catch (ArithmeticException ex) {
            throw new IllegalArgumentException(
                "offset exceeds long range", ex);
        }
    }

    static <T> Page<T> pageByStream(
            List<T> source, long pageIndex, int pageSize) {

        Objects.requireNonNull(source, "source");
        long offset = checkedOffset(pageIndex, pageSize);

        List<T> items;
        if (offset >= source.size()) {
            items = Collections.emptyList();
        } else {
            items = source.stream()
                .skip(offset)
                .limit(pageSize)
                .collect(Collectors.toList());
        }

        return new Page<>(pageIndex, pageSize,
            source.size(), items);
    }

    static <T> Page<T> pageByList(
            List<T> source, long pageIndex, int pageSize) {

        Objects.requireNonNull(source, "source");
        long offset = checkedOffset(pageIndex, pageSize);

        List<T> items;
        if (offset >= source.size()) {
            items = Collections.emptyList();
        } else {
            int from = (int) offset;
            int to = (int) Math.min(
                (long) source.size(), offset + pageSize);

            items = new ArrayList<>(source.subList(from, to));
        }

        return new Page<>(pageIndex, pageSize,
            source.size(), items);
    }

    public static void main(String[] args) {
        List<Integer> data = Arrays.asList(
            1, 2, 3, 4, 5, 6, 7,
            8, 9, 10, 11, 12
        );

        System.out.println(pageByStream(data, 0, 5));
        System.out.println(pageByList(data, 1, 5));
        System.out.println(pageByStream(data, 2, 5));
        System.out.println(pageByList(data, 3, 5));
    }
}
```

Output:

```text
Page{index=0, size=5, total=12, pages=3, next=true, items=[1, 2, 3, 4, 5]}
Page{index=1, size=5, total=12, pages=3, next=true, items=[6, 7, 8, 9, 10]}
Page{index=2, size=5, total=12, pages=3, next=false, items=[11, 12]}
Page{index=3, size=5, total=12, pages=3, next=false, items=[]}
```

`hasNext()` relies on metadata from the **data snapshot used for that pagination call**. For pages beyond `totalPages`, it returns `false`. If another thread mutates the source mid-call, `source.size()` and traversal can become inconsistent; the sample assumes **an immutable source for the duration of the call**.

`Page<T>` is a learning template, not a mandatory API format. Applications may add `hasPrevious`, navigation links, or sort criteria while keeping index and total contracts consistent.

**Immutability note:** `Collections.unmodifiableList` prevents structural edits through the returned list; it does not make mutable elements inside immutable.


## 9. Real-World Pattern: Filter, Stable Sort, Then Paginate

A product catalog endpoint often combines multiple rules:

- Show only **active** products.
- Sort by **price descending**.
- On equal price, sort by **ID ascending** for deterministic ordering.
- Return `pageIndex` with `pageSize` to the UI.
- Compute total result count **after filtering**, not from the current page's row count.

Proper pipeline order:

```text
In-memory List
    |
  filter(active)
    |
  sorted(price DESC, id ASC)
    |
  skip(pageIndex * pageSize)
    |
  limit(pageSize)
    |
  collect
```

### 9.1. Complete Java 8+ Program

This snippet is self-contained and can be saved to `ProductPaginationExample.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

public class ProductPaginationExample {
    static final class Product {
        final String id;
        final String name;
        final long price;
        final boolean active;

        Product(String id, String name,
                long price, boolean active) {
            this.id = id;
            this.name = name;
            this.price = price;
            this.active = active;
        }

        @Override
        public String toString() {
            return id;
        }
    }

    public static void main(String[] args) {
        List<Product> source = Arrays.asList(
            new Product("P04", "Mouse", 100, true),
            new Product("P01", "Keyboard", 120, true),
            new Product("P03", "Headset", 120, false),
            new Product("P02", "Speaker", 120, true),
            new Product("P06", "Cable", 70, true),
            new Product("P05", "Mousepad", 100, true),
            new Product("P07", "Stand", 90, true)
        );

        Comparator<Product> byPriceThenId =
            Comparator.comparingLong((Product p) -> p.price)
                .reversed()
                .thenComparing(p -> p.id);

        // Fix the filtered/sorted result set once,
        // then serve multiple pages from that same list.
        List<Product> filteredSorted = source.stream()
            .filter(p -> p.active)
            .sorted(byPriceThenId)
            .collect(Collectors.toList());

        int pageSize = 3;
        int total = filteredSorted.size();
        int totalPages = total == 0
            ? 0 : 1 + (total - 1) / pageSize;

        for (int pageIndex = 0; pageIndex < totalPages;
                pageIndex++) {
            int from = pageIndex * pageSize;
            int to = Math.min(from + pageSize, total);

            List<Product> page = new ArrayList<>(
                filteredSorted.subList(from, to));

            System.out.println(
                "Page " + (pageIndex + 1) + ": " + page);
        }

        System.out.println("Total: " + total);
        System.out.println("Total pages: " + totalPages);
    }
}
```

Output:

```text
Page 1: [P01, P02, P04]
Page 2: [P05, P07, P06]
Total: 6
Total pages: 2
```

**Analysis:** `P03` is inactive and excluded before counting or paginating. `P01` and `P02` share price 120, so secondary key `id` fixes their order. We avoid re-running `filter` and `sorted` per page by creating **one processed result list**.

**Important condition:** `filteredSorted` must not be structurally mutated while serving pages from that snapshot. `Product` has `final` fields here, keeping values stable; if real elements are mutable objects, copying the list does not deep-copy products.

### 9.2. When Is Materializing a Snapshot Reasonable?

Creating a filtered/sorted snapshot list is a good choice when:

- Data already fits in RAM and is small enough to hold one more list.
- Users are likely to browse **multiple pages** of the same result set.
- Filtering and sorting are expensive and shouldn't re-run on every page click.
- A **consistent** result set is needed across UI navigation.

In return, holding a snapshot consumes memory proportional to the filtered element count. For huge or rapidly mutating lists, consider alternatives like time-bounded caches, versioned snapshots, source-side processing, or database pagination.

## 10. Total Record Count Must Be Computed After Filtering, Not After Slicing

Suppose there are 10 numbers from 1 to 10, of which 5 even numbers are valid. If `pageSize = 3`:

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

List<Integer> even = IntStream.rangeClosed(1, 10)
    .filter(n -> n % 2 == 0)
    .boxed()
    .collect(Collectors.toList());

int totalElements = even.size(); // 5
int pageSize = 3;
int totalPages = 1 + (totalElements - 1) / pageSize; // 2

List<Integer> firstPage = even.stream()
    .limit(pageSize)
    .collect(Collectors.toList());

System.out.println(firstPage); // [2, 4, 6]
System.out.println(totalElements); // 5
System.out.println(totalPages); // 2
```

Never use `firstPage.size()` as total results; that is only **the current page's element count**. Also never use `source.size()` when the source still contains filtered-out elements.

If you do not store `even`, you can count and slice using **two separate streams**:

```java
long total = source.stream()
    .filter(predicate)
    .count();

List<Item> items = source.stream()
    .filter(predicate)
    .skip(offset)
    .limit(pageSize)
    .collect(Collectors.toList());
```

This is a **generic illustrative snippet**: declare `Item`, `source`, `predicate`, and `offset` in a real program. Both passes must apply the same filter to a stable source so metadata matches page data. Moreover, this **evaluates the filter twice**, which can be costly on large data.

When the source is an in-memory processed result, collecting into a list once is usually simpler:

```text
filter/sort → stable result List → total = size()
                                 → subList per page
```

For more complex statistics, you can use combined collectors or auxiliary data structures while keeping correctness and resource usage balanced.

## 11. Real Limits of `skip` and `limit`

`skip` and `limit` are **stateful intermediate operations**: they track how many elements have been discarded or retained. Both operate on **the stream of elements flowing through the pipeline**, not as a random-access API for every source.

### 11.1. Deep Pages May Traverse Many Elements

```java
List<Integer> page = java.util.stream.IntStream
    .range(0, 1_000_000)
    .boxed()
    .skip(900_000)
    .limit(20)
    .collect(Collectors.toList());

System.out.println(page.get(0)); // 900000
System.out.println(page.size()); // 20
```

Semantically, the pipeline skips 900,000 elements before taking 20. **Do not claim every implementation runs 900,000 `tryAdvance` calls**: sized, position-splittable sources let the runtime optimize. Yet on sequential sources lacking positional access, skipping many elements can indeed take proportional time.

`skip` is convenient in pipelines; it **does not promise** O(1) complexity for every source or every chain of intermediate operations.

### 11.2. `filter` Before `skip` Can Make Deep Pages Costlier

```java
List<Integer> page = java.util.stream.IntStream
    .range(0, 1_000_000)
    .filter(n -> n % 17 == 0)
    .skip(20_000)
    .limit(10)
    .boxed()
    .collect(Collectors.toList());
```

To skip **20,000 matching values**, the pipeline must inspect far more than 20,000 source values. `skip(20_000)` counts **elements passing `filter`**, not raw source elements.

In memory, when users page back and forth frequently, consider **filtering once and storing a snapshot** rather than re-running an expensive filter on every request.

### 11.3. `sorted` May Buffer the Entire Input

```java
List<Integer> page = numbers.stream()
    .sorted()
    .skip(100)
    .limit(20)
    .collect(Collectors.toList());
```

For general unsorted data, `sorted` is stateful and typically must examine all input elements to establish global order. Thus a downstream `limit(20)` **does not guarantee** only 120 elements are inspected or only tiny memory is used.

If data is already sorted, avoid re-sorting on every page. If you only need top-k from a massive source, a priority-queue top-k algorithm fits better than full sorting—though that is a different problem from arbitrary index pagination.

### 11.4. Infinite Sources: Watch Operation Placement

```java
import java.util.stream.LongStream;

List<Long> page = LongStream.iterate(0L, n -> n + 1L)
    .skip(1_000_000L)
    .limit(5)
    .boxed()
    .collect(Collectors.toList());

System.out.println(page);
// [1000000, 1000001, 1000002, 1000003, 1000004]
```

This source can emit infinitely many elements. `limit(5)` guarantees the pipeline terminates after **skipping** the requested prefix, though it still must advance to that position.

Conversely, a whole-stream stateful operation like `sorted()` on an unbounded infinite source may never produce an element. Placing `limit` **after `sorted`** does not make it feasible.

### 11.5. Returning a `Stream<T>` Does Not Auto-Close Resources

With `List.stream()`, there is no OS handle or database connection owned by the list. However, when inputs come from I/O sources like `Files.lines(...)` or `Files.walk(...)`, `skip`/`limit` **do not close resources automatically**. Use `try-with-resources`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static List<String> readLinesPage(
        Path path, long offset, long pageSize)
        throws IOException {

    if (offset < 0 || pageSize < 0) {
        throw new IllegalArgumentException("negative offset/size");
    }

    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {
        return lines.skip(offset)
            .limit(pageSize)
            .collect(Collectors.toList());
    }
}
```

This illustrates **resource lifecycle**, not a recommended RAM pagination API: fetching deep pages from a file must read and discard preceding lines, and the file may change between requests.

## 12. Does `parallelStream()` Speed Up Pagination?

Possibly, but do not assume so:

```java
List<Integer> page = java.util.stream.IntStream
    .range(0, 1_000_000)
    .parallel()
    .skip(900_000)
    .limit(20)
    .boxed()
    .collect(Collectors.toList());
```

`IntStream.range` is ordered and sized, so the logical result must be 900,000 through 900,019. However, on an **ordered parallel stream**, `skip` and `limit` can require cross-task coordination to preserve exact positional slicing. Performance depends on the source spliterator, data size, core count, per-element cost, and upstream operations.

If you just want a slice of an `ArrayList`, spawning parallel tasks often adds **more overhead** than calling `subList`. Measure on realistic workloads before adding `parallel()`.

### 12.1. `unordered()` Is Unsuitable for Positional Pages

```java
List<Integer> page = java.util.stream.IntStream.range(0, 100)
    .parallel()
    .unordered()
    .skip(20)
    .limit(10)
    .boxed()
    .collect(Collectors.toList());
```

`unordered()` lets the runtime relax ordering constraints and can improve throughput when which elements are chosen does not matter. Yet there is **no longer any guarantee** this page holds 20, 21, ..., 29. If the UI expects fixed positions, never drop encounter order just to optimize.

### 12.2. `forEach` Is Not How You Build an Ordered Page

```java
List<Integer> output = new ArrayList<>();

// AVOID: ArrayList is not thread-safe for concurrent adds,
// and forEach does not guarantee encounter order.
numbers.parallelStream()
    .skip(10)
    .limit(10)
    .forEach(output::add);
```

Use `collect(Collectors.toList())` instead—or when the source is already a `List` and you only need a slice, use `subList` with a copy. `forEachOrdered` enforces action order, yet still lags a proper collector for building lists.

## 13. Multi-Page Access: Consistency, Memory, and Algorithms

When a user loads pages 0, 1, 2, ..., 100 sequentially from **the same in-memory snapshot**, repeatedly calling:

```java
source.stream().skip((long) pageIndex * pageSize)
    .limit(pageSize)
    .collect(Collectors.toList());
```

can repeat prefix traversal or pipeline work. If data is already indexed and ordered, slice directly with `subList`.

For a stable design:

1. Normalize one result set with **filter + total ordering**.
2. Create a snapshot per data version or point in time.
3. Compute `totalElements` and `totalPages` on **that exact result set**.
4. Use validated offsets to slice pages from the snapshot.
5. Return page metadata alongside content; when snapshots expire, define invalidation/refresh rules clearly.

For very large sources, loading everything into RAM can be an architectural mistake. `skip` does not reduce the cost of **loading every record** into memory before slicing.

### 13.1. Difference from Database Pagination

With millions of rows, let the storage engine filter, sort, and limit rather than loading everything:

```sql
-- Example syntax; LIMIT/OFFSET varies across DBMSs.
SELECT id, name, price
FROM products
WHERE active = TRUE
ORDER BY created_at DESC, id ASC
LIMIT :page_size OFFSET :offset;
```

That **does not mean database LIMIT/OFFSET is O(1)**: deep pages may still scan/discard many rows, and concurrent inserts/deletes can cause duplicates or skipped rows.

For fast-changing feeds needing "next page" navigation, **keyset/cursor pagination** is often chosen:

```text
Remember the key of the last record on the previous page.
The next page filters records strictly after that key
under the exact same deterministic ordering.
```

Keyset pagination has its own trade-offs: it does not natively jump to arbitrary page numbers and requires a suitable sort key. Use this as architectural guidance, not a blanket rule to replace `skip` in every RAM-backed tool.

## 14. Verifying Pagination with Boundary Cases (Java 8+)

A strong test **concatenates all valid pages** from the same snapshot and compares against the source: no items may be dropped or duplicated. When data can contain duplicate values, assert `List.equals` rather than only `Set` equality.

The program below reuses `InMemoryPaginationDemo` from section 8; place it beside that file and run on Java 8+:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class PaginationCheck {
    static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        List<Integer> source = IntStream.rangeClosed(1, 23)
            .boxed().collect(Collectors.toList());

        List<Integer> joined = new ArrayList<>();

        for (int page = 0; page < 5; page++) {
            InMemoryPaginationDemo.Page<Integer> a =
                InMemoryPaginationDemo.pageByStream(
                    source, page, 5);

            InMemoryPaginationDemo.Page<Integer> b =
                InMemoryPaginationDemo.pageByList(
                    source, page, 5);

            check(a.items.equals(b.items),
                "Two approaches gave different pages: " + page);
            check(a.totalElements == 23L, "Wrong total elements");
            check(a.totalPages == 5L, "Wrong total pages");

            joined.addAll(a.items);
        }

        check(joined.equals(source),
            "Lost or duplicated elements across pages");

        check(InMemoryPaginationDemo.pageByStream(
                source, 4, 5).items
            .equals(Arrays.asList(21, 22, 23)),
            "Wrong last page");

        check(InMemoryPaginationDemo.pageByStream(
                source, 5, 5).items.isEmpty(),
            "Out-of-bounds page must be empty");

        check(InMemoryPaginationDemo.pageByList(
                Collections.<Integer>emptyList(), 0, 5)
            .totalPages == 0L, "Empty source");

        boolean rejectedNegative = false;
        try {
            InMemoryPaginationDemo.pageByStream(source, -1, 5);
        } catch (IllegalArgumentException ex) {
            rejectedNegative = true;
        }
        check(rejectedNegative, "Must reject negative pageIndex");

        boolean rejectedZeroSize = false;
        try {
            InMemoryPaginationDemo.pageByList(source, 0, 0);
        } catch (IllegalArgumentException ex) {
            rejectedZeroSize = true;
        }
        check(rejectedZeroSize, "Must reject pageSize 0");

        boolean rejectedOverflow = false;
        try {
            InMemoryPaginationDemo.pageByStream(
                source, Long.MAX_VALUE, 2);
        } catch (IllegalArgumentException ex) {
            rejectedOverflow = true;
        }
        check(rejectedOverflow, "Must detect offset overflow");

        System.out.println("PASS: in-memory pagination");
    }
}
```

Expected output:

```text
PASS: in-memory pagination
```

These checks test specific contract cases, not concurrent mutations from another thread. If your app serves concurrent requests, specify snapshot creation and immutable sharing boundaries explicitly.

## 15. Common Bugs and Misconceptions

| Symptom | Cause | Fix |
| --- | --- | --- |
| First page is wrong | Confusing 1-based `pageNumber` with 0-based `pageIndex` | Normalize index at the API boundary. |
| `skip` throws `IllegalArgumentException` | Negative offset from negative input or integer overflow | Validate inputs and use `Math.multiplyExact` on `long`. |
| `limit(0)` makes UI always empty | `pageSize = 0` accepted | Require `pageSize > 0`. |
| Last page has fewer items | Not enough data to fill a full page | Expected behavior; never pad dummy records. |
| `totalElements` equals page size | Counting after `limit` | Count after filtering, **before** slicing. |
| Page has 1 item despite many valid records | `filter` placed after `limit` | Filter before paginating filtered results. |
| Duplicate codes appear across pages | `distinct` placed after `skip`/`limit` | Deduplicate before paginating if uniqueness is required. |
| Price-sorted pages are out of order | `sorted` placed after `skip`/`limit` | Sort the full result set before slicing. |
| Page contents shift between two queries | Source mutated without a snapshot | Use snapshots/versions or cursor pagination. |
| Order flips among equal-priced items | Comparator lacks a unique secondary key | Add a deterministic tie-breaker. |
| `HashSet` gives unpredictable pages | Source has no encounter order | Establish explicit order with `sorted`. |
| `parallel().unordered()` returns wrong positions | Positional encounter order was dropped | Never use `unordered` for positional paging. |
| `List.subList` breaks when source changes | `subList` is a view, not a copy | Copy with `new ArrayList<>(subList)` and manage source lifecycle. |
| Deep pages are slow | `skip` may traverse large prefixes | Use an indexed snapshot list or push pagination to the source. |
| `sorted().limit(...)` uses lots of memory | `sorted` is stateful over the full input | Consider pre-sorted data, top-k, or source-side limits. |
| Creating second stream on consumed instance | Streams are single-use | Open a fresh stream from the source; never reuse a Stream object. |
| Parallel `forEach` corrupts order/data | Unsynchronized mutation of external list | Use `collect` or `subList`. |
| Fetching 20 rows reads whole table | Filtering/paging in RAM after loading all rows | Push filtering/pagination down to the data source when appropriate. |

## 16. Practice Exercises

### Exercise 1 — Offset Formula

With `pageSize = 8`, compute `offset` for `pageIndex` 0, 1, and 4. Given 35 elements, what is the 0-based index of the last page and how many elements does it contain?

### Exercise 2 — Paginating Even Numbers

Given numbers 1 through 20, keep only even numbers, 4 per page. Write a pipeline for `pageIndex = 1`. Predict the result and explain `filter` placement relative to `skip`.

### Exercise 3 — Slicing vs. Sorting

Source `[9, 1, 7, 2, 5]`. Compare:

```java
source.stream().sorted().skip(2).limit(2)
source.stream().skip(2).limit(2).sorted()
```

Are the results identical? If the UI expects ascending order across the whole dataset, which is right?

### Exercise 4 — Out-of-Range Pages and Invalid Parameters

A list has 12 elements, `pageSize = 5`. Write logic returning pages for `pageIndex = 2`, 3, and -1 under the chosen contract. Should a request for page 3 automatically fall back to page 2?

### Exercise 5 — Snapshots and Views

An `ArrayList` holds `[A, B, C, D]`. Create `subList(1, 3)` and call `view.set(0, "X")`. What happens to the original list? If page results must remain structurally isolated when the source list is edited, what must you do?

### Exercise 6 — Total Records and Last Page

There are 23 records after filtering, `pageSize = 5`. Compute `totalPages` and list the elements (numbered 1..23) on `pageIndex = 4`. Why can `pageIndex = 5` return an empty page rather than an error?

### Exercise 7 — Architectural Decision

An app has 2 million database rows, yet users view only 20 rows at a time. Explain why loading all rows into RAM and calling `skip`/`limit` is a poor default. Compare pros and cons of database offset pagination, stable snapshots, and keyset/cursor pagination.

## 17. Answers and Hints

**Exercise 1.** `offset = pageIndex * pageSize` gives 0, 8, and 32. With 35 elements, `totalPages = 1 + (35 - 1) / 8 = 5`; the last page has `pageIndex = 4` and holds 3 elements.

**Exercise 2.** Even numbers are `[2, 4, 6, 8, 10, 12, 14, 16, 18, 20]`. The second page (`pageIndex = 1`) skips the first four even numbers and takes the next four:

```java
List<Integer> result = java.util.stream.IntStream
    .rangeClosed(1, 20)
    .filter(n -> n % 2 == 0)
    .skip(4)
    .limit(4)
    .boxed()
    .collect(Collectors.toList());

System.out.println(result); // [10, 12, 14, 16]
```

Filter before paginating because we are paging **even numbers**, not filtering four raw source positions.

**Exercise 3.** `sorted().skip(2).limit(2)` yields `[5, 7]`; `skip(2).limit(2).sorted()` yields `[2, 7]`. When the whole dataset must be sorted ascending before selecting a page, use the first form.

**Exercise 4.** `pageIndex = 2` returns the 11th and 12th elements (1-based display). `pageIndex = 3` has `offset = 15` and returns an empty list by contract. `pageIndex = -1` must be rejected. Never silently clamp page 3 down to page 2 unless the API explicitly specifies that behavior.

**Exercise 5.** `subList` is a view; changing the view's first element from `B` to `X` changes the source to `[A, X, C, D]`. Use `new ArrayList<>(source.subList(from, to))` to decouple list structure. If elements are mutable objects, also copy elements if a deep snapshot is required.

**Exercise 6.** `totalPages = 5`. `pageIndex = 4` returns `[21, 22, 23]`. `pageIndex = 5` has valid parameters beyond available data, so it returns empty—distinct from negative indices or offset overflow.

**Exercise 7.** Loading 2 million rows wastes memory, network transfer, and CPU just to keep 20 rows. Database offset pagination pushes filtering/limiting to storage, though deep pages can still scan many rows and concurrent edits cause duplicates/gaps. Snapshots/versions keep pages consistent within a fixed set at higher management/memory cost. Keyset/cursor pagination excels at "next page" along a stable sort key, though jumping to arbitrary page numbers is harder and requires careful key/query design.

## 18. Application Implementation Checklist

Before shipping an in-memory pagination API, verify:

- [ ] Whether `pageIndex` is 0-based or 1-based is explicitly documented.
- [ ] `pageSize > 0`, `pageIndex >= 0`, and reasonable max page-size bounds are enforced.
- [ ] `offset` is computed in `long` with overflow protection for large page numbers.
- [ ] `filter`, `distinct`, and `sorted` precede `skip`/`limit` when paging **processed results**.
- [ ] Deterministic ordering with a tie-breaker is defined when sort keys can tie.
- [ ] Total record count and total pages reflect the **post-filter dataset**, not page size.
- [ ] Partial last pages and out-of-range pages follow the published API contract.
- [ ] Source state stays stable during paging; cross-request snapshot needs are decided.
- [ ] If using `subList`, view vs. copy semantics and source-mutation consequences are handled.
- [ ] Positional paging never relies on `unordered` or parallel `forEach`.
- [ ] Costs of deep `skip`, `sorted`, and per-request pipeline re-evaluation are assessed.
- [ ] For very large datasets, source-side pagination or cursor models have been considered.
- [ ] For I/O-backed sources, stream/resource lifecycles are properly closed.
- [ ] Tested with empty sources, 1 element, exact multiples of `pageSize`, partial last page, past-end page, 0/negative args, and overflow.

## 19. Summary

The basic positional pagination pattern:

```java
long offset = Math.multiplyExact(pageIndex, (long) pageSize);

List<T> page = source.stream()
    .skip(offset)
    .limit(pageSize)
    .collect(Collectors.toList());
```

This is an illustrative template: before running, validate indices and page sizes, and declare `source` and `T` in your program.

Core principles:

- **Right content:** establish ordering, filtering, and sorting **before** slicing when paging the processed result set.
- **Right indices:** standardize 0-based vs. 1-based indexing, compute offsets in `long`, and detect overflow.
- **Right metadata:** count after filtering, compute total pages without overflow, and never confuse page size with total records.
- **Right data lifecycle:** if data mutates between page loads, offsets can duplicate or skip items; use snapshots or cursors as required.
- **Right tool:** for an `ArrayList` already in RAM needing a single slice, `subList` with a copy is usually clearer; for processing pipelines, `skip`/`limit` are handy yet do not guarantee fast deep paging on all sources.
- **Right resources:** loading huge datasets into RAM just to paginate them does not substitute for source-side pagination.

Understanding the limits of `skip` and `limit` lets you design Java Stream API pipelines that are accurate, testable, and performant in practice rather than merely producing a shorter list.
