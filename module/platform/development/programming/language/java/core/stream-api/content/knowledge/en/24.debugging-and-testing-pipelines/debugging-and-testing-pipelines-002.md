# Splitting Long Pipelines into Named Steps with Clear Contracts

## 1. Goal and Context

In the **`JAVA_STREAM_API`** module, declarative data processing with the Java Stream API usually starts from a source, passes through lazy intermediate operations like `filter`, `map`, and `flatMap`, and finishes with `reduce`, `collect`, or another terminal operation. As business rules, grouping, sorting, and error handling are added, an initially short pipeline can grow into **a very long chain of lambdas**.

The problem with a long pipeline isn't just its line count. It makes it hard to answer essential questions:

- What input format is expected? How are `null`, empty strings, and negative numbers handled?
- Is a step **normalizing**, **validating**, **filtering**, or **aggregating**?
- When data is invalid, does the system throw an exception, drop the record, or collect it into an error list?
- When results look wrong, which step dropped or duplicated elements?
- Does the result order carry meaning? Do `groupingBy` and `parallel` alter that assumption?
- Can individual rules be tested without running the entire application?

This lesson belongs to the **Debugging and Testing Pipelines** chapter and explains how to **split long pipelines into named steps with clear contracts**. We will work through an order-processing example, refactoring a hard-to-maintain expression into readable Java 8+ functions that are easy to test, measure, and evolve.

After this lesson, you will be able to:

1. Identify **business boundaries** for splitting operations in a pipeline.
2. Specify each step's contract: input/output types, preconditions, postconditions, ordering, side effects, and error policy.
3. Write functions like `normalize`, `paidOnly`, and `summarize` with meaningful types and names.
4. Distinguish **single-element functions**, **functions taking/returning `Stream`**, and **terminal operations returning materialized results**.
5. Test individual rules independently and verify end-to-end results against a reference algorithm.
6. Use logging, `peek`, and temporary materialization for diagnostics without relying on side effects.
7. Preserve laziness, single-use semantics, I/O resource management, and parallelization conditions.

## 2. Recognizing a Hard-to-Debug Pipeline

Suppose the business receives transactions consisting of an order ID, customer ID, status, and amount in **cents**. Requirements:

- Trim whitespace from the order ID and customer ID.
- Normalize the status to uppercase using `Locale.ROOT`.
- **Reject** invalid records: `null`, blank IDs, unsupported statuses, or negative amounts.
- Keep only **PAID** orders.
- Compute the total amount and order count per customer.
- Sort results by total amount **descending**, breaking ties by customer ID **ascending**.

A pipeline might be written all crammed together:

```java
List<CustomerSummary> result = source.stream()
    .map(row -> /* multiple normalize and validate branches */)
    .filter(sale -> "PAID".equals(sale.status))
    .collect(Collectors.groupingBy(
        sale -> sale.customerId,
        Collectors.summarizingLong(sale -> sale.amountCents)
    ))
    .entrySet().stream()
    .map(entry -> /* build CustomerSummary */)
    .sorted(/* multi-criteria comparator */)
    .collect(Collectors.toList());
```

This illustration intentionally leaves blanks for details that are extracted into **named functions** later. Reading the first `map` line, you can't tell which rules are enforced; if `null` or refund handling is added later, the rest of the pipeline can easily break unintentionally.

**Signs refactoring is needed:**

- Multi-line lambdas that transform data, validate errors, and write logs all at once.
- Expressions with deeply nested `collect` calls whose types are hard to trace.
- Every caller using the pipeline duplicates the same `filter`/`map` sequence.
- It is unclear which step alters element cardinality.
- Error-handling rules are hidden inside `filter(x -> x != null)` or a `catch` returning a default value.
- Tests only compare the final output on a few "happy" samples, missing error cases or empty inputs.

**The goal of refactoring is not to create as many functions as possible.** The goal is for each step name to represent one rule that can be described, verified, and changed independently.

## 3. What Should a Processing Step's Contract State?

For each step, briefly document:

| Component | Question |
| --- | --- |
| **Name and responsibility** | Which single rule does this step enforce? Does the name reflect it? |
| **Input/output types** | Does it take `RawSale` or `Sale`? Does it return `Stream<Sale>`, `List<Sale>`, or `Map`? |
| **Preconditions** | Must data be non-null? Already normalized? Ordered? |
| **Postconditions** | Is the output always valid? Can it be empty? Does it preserve order/duplicates? |
| **Error policy** | Throws an exception, skips the record, or collects errors separately? |
| **Cardinality** | One-to-one, filtering, expanding, or aggregating? |
| **Side effects** | Does it mutate the source, perform I/O, or update shared variables? |
| **Lazy/eager** | Does it only build the pipeline, or actually consume it and hold results in RAM? |

A contract can be expressed via Javadoc, a short table, or tests; you don't need lengthy documentation for a small helper.

### 3.1. Contracts of the steps in our example

| Step | Input → Output | Rule | Cardinality |
| --- | --- | --- | --- |
| `normalizeSale` | `RawSale → Sale` | Validate, trim IDs, normalize status; throw `IllegalArgumentException` if invalid | 1 → 1 or error |
| `normalize` | `Stream<RawSale> → Stream<Sale>` | Lazily apply `normalizeSale` to each element | Preserves count when error-free |
| `paidOnly` | `Stream<Sale> → Stream<Sale>` | Keep only `PAID` orders | 0 or 1 output per input |
| `summarize` | `Stream<Sale> → List<CustomerSummary>` | Group, sum amounts, count orders, sort | Many orders → one row/customer |
| `process` | `List<RawSale> → List<CustomerSummary>` | Wire steps together; return an unmodifiable list | Materialized result |

**Logical execution order:** `normalize` before `paidOnly` means **every record is validated**, even records not subsequently selected for aggregation. If the business wants to silently ignore malformed `PENDING` rows without failing, that is **a different policy** that must be defined explicitly rather than reordering filters to "fix a bug."

### 3.2. Contracts must specify ordering

A `List` source has an encounter order; `map` and `filter` on an ordered stream preserve the logical order of remaining elements. However, `Collectors.groupingBy` does **not guarantee iteration order of keys in the resulting `Map`** by default.

Therefore, after grouping you must **sort explicitly** by total amount and customer ID if the report requires deterministic order. Never rely on the display order of a `HashMap` in the current run.

## 4. Separating Two Levels: Single-Record Transformation and Stream Processing

A clean separation looks like this:

```text
RawSale
   |
normalizeSale(RawSale)            // Record-level rule
   |
Sale
   |
normalize(Stream<RawSale>)       // Lazy intermediate step
   |
Stream<Sale>
   |
paidOnly(Stream<Sale>)           // Business filter
   |
Stream<Sale>
   |
summarize(Stream<Sale>)          // Terminal: grouping + sort
   |
List<CustomerSummary>
```

Naming `normalizeSale` differently from `normalize` is intentional:

- `normalizeSale` is a **pure record-level function**, ideal for direct unit testing.
- `normalize` is a **pipeline-building function**. It does not validate all records when called; validation happens during consumption.
- `summarize` is the **terminal boundary**: it calls `collect` and creates a `List`. It is no longer lazy.

Merely naming variables `Stream<Sale> stage1` or `Stream<Sale> stage2` does not solve the contract problem. Name steps after **business rules or data meaning**, not sequence numbers.

## 5. Complete Java 8+ Program: Named Pipeline

Create `NamedPipelineExample.java`. The program avoids `record`, `Stream.toList()`, or APIs added only in newer JDKs, making it compatible with Java 8.

```java
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.LongSummaryStatistics;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class NamedPipelineExample {

    static final class RawSale {
        final String orderId;
        final String customerId;
        final String status;
        final long amountCents;

        RawSale(String orderId, String customerId,
                String status, long amountCents) {
            this.orderId = orderId;
            this.customerId = customerId;
            this.status = status;
            this.amountCents = amountCents;
        }
    }

    static final class Sale {
        final String orderId;
        final String customerId;
        final String status;
        final long amountCents;

        Sale(String orderId, String customerId,
                String status, long amountCents) {
            this.orderId = orderId;
            this.customerId = customerId;
            this.status = status;
            this.amountCents = amountCents;
        }
    }

    static final class CustomerSummary {
        final String customerId;
        final long orderCount;
        final long totalCents;

        CustomerSummary(String customerId,
                long orderCount, long totalCents) {
            this.customerId = customerId;
            this.orderCount = orderCount;
            this.totalCents = totalCents;
        }

        @Override
        public String toString() {
            return customerId
                + " total=" + totalCents
                + " count=" + orderCount;
        }
    }

    // Contract: null/empty is invalid; returns trimmed string.
    static String requiredText(String text, String field) {
        if (text == null || text.trim().isEmpty()) {
            throw new IllegalArgumentException(
                field + " khong duoc rong");
        }
        return text.trim();
    }

    // Contract: one valid RawSale -> one normalized Sale;
    // invalid data -> IllegalArgumentException.
    static Sale normalizeSale(RawSale raw) {
        if (raw == null) {
            throw new IllegalArgumentException(
                "Ban ghi khong duoc null");
        }

        String orderId = requiredText(
            raw.orderId, "orderId");
        String customerId = requiredText(
            raw.customerId, "customerId");
        String status = requiredText(
            raw.status, "status")
            .toUpperCase(Locale.ROOT);

        if (!status.equals("PAID")
                && !status.equals("PENDING")
                && !status.equals("REFUNDED")) {
            throw new IllegalArgumentException(
                "status khong ho tro: " + status);
        }
        if (raw.amountCents < 0) {
            throw new IllegalArgumentException(
                "amountCents phai >= 0");
        }

        return new Sale(
            orderId, customerId, status, raw.amountCents);
    }

    // Builds an intermediate stage only; does not consume the source.
    static Stream<Sale> normalize(
            Stream<RawSale> source) {
        Objects.requireNonNull(source, "source");
        return source.map(
            NamedPipelineExample::normalizeSale);
    }

    // Contract: input is already normalized; keeps only PAID.
    static Stream<Sale> paidOnly(Stream<Sale> sales) {
        Objects.requireNonNull(sales, "sales");
        return sales.filter(
            sale -> "PAID".equals(sale.status));
    }

    // Terminal stage: grouping, count/sum amounts, sort.
    static List<CustomerSummary> summarize(
            Stream<Sale> paidSales) {
        Objects.requireNonNull(paidSales, "paidSales");

        Map<String, LongSummaryStatistics> byCustomer =
            paidSales.collect(
                Collectors.groupingBy(
                    sale -> sale.customerId,
                    Collectors.summarizingLong(
                        sale -> sale.amountCents)
                )
            );

        Comparator<CustomerSummary> order =
            Comparator.comparingLong(
                    (CustomerSummary s) -> s.totalCents)
                .reversed()
                .thenComparing(s -> s.customerId);

        return byCustomer.entrySet().stream()
            .map(entry -> new CustomerSummary(
                entry.getKey(),
                entry.getValue().getCount(),
                entry.getValue().getSum()))
            .sorted(order)
            .collect(Collectors.toList());
    }

    // Business entry point: does not mutate source;
    // returns a structurally unmodifiable list.
    static List<CustomerSummary> process(
            List<RawSale> source) {
        Objects.requireNonNull(source, "source");

        List<CustomerSummary> result = summarize(
            paidOnly(normalize(source.stream())));

        return Collections.unmodifiableList(result);
    }

    public static void main(String[] args) {
        List<RawSale> input = Arrays.asList(
            new RawSale(" O-1 ", " KH-A ",
                "paid", 1000),
            new RawSale("O-2", "KH-B",
                "PAID", 2500),
            new RawSale("O-3", "KH-A",
                "REFUNDED", 9999),
            new RawSale("O-4", "KH-A",
                "PAID", 3000),
            new RawSale("O-5", "KH-C",
                "PENDING", 9900),
            new RawSale("O-6", "KH-B",
                "paid", 500),
            new RawSale("O-7", "KH-A",
                "PAID", 2000)
        );

        process(input).forEach(System.out::println);
    }
}
```

Expected output:

```text
KH-A total=6000 count=3
KH-B total=3000 count=2
```

### 5.1. Why is this separation easy to test?

- `normalizeSale` is tested with **a single record** without constructing an entire pipeline.
- `paidOnly` tests the remaining element count on a small already-normalized stream.
- `summarize` tests grouping, counts, totals, and sorting rules in isolation.
- `process` has an end-to-end test confirming the steps compose properly.
- Method names and return types clearly show **where lazy execution transitions to eager execution**.

In real applications, data classes can live in separate files. Here they are placed inside one class so the example is **self-contained** and easy to compile.

### 5.2. Contracts have numeric-range limits

`amountCents` uses `long`, and `Collectors.summarizingLong` aggregates using `long`. If totals can exceed `Long.MAX_VALUE`, the result risks overflowing. The example assumes **totals fit in `long`**; business domains requiring exact arithmetic beyond that range should use overflow-checked arithmetic or `BigInteger`.

`REFUNDED` orders are **excluded from the report**, rather than turning into negative amounts to subtract. If the business requires net revenue, define refund handling explicitly and write a dedicated step instead of quietly altering `paidOnly`.

### 5.3. Don't mix normalized data with raw data

`RawSale` and `Sale` are distinct types, even though their fields look almost identical. Separating the types prevents:

```java
// Idea to avoid:
// paidOnly(source.stream()); // Not a Stream<Sale>.
```

The compiler refuses to pass `Stream<RawSale>` into a method expecting `Stream<Sale>`. The validation contract no longer lives only in comments—it is partially enforced by the **type system**.

## 6. Named Functions Preserve Stream Laziness

Distinguish between two kinds of operations:

```java
Stream<NamedPipelineExample.Sale> pipeline =
    NamedPipelineExample.paidOnly(
        NamedPipelineExample.normalize(input.stream())
    );

// Here, normalizeSale is not guaranteed to have run yet.
long count = pipeline.count(); // Terminal: consumes the pipeline.
```

`normalize` and `paidOnly` return a `Stream` to assemble the pipeline. They do not allocate intermediate lists. Thus, you can split code by responsibility **while keeping lazy evaluation**.

However, `summarize` calls `collect`; that is a **terminal** boundary. Once `summarize(stream)` returns, the input stream has been consumed and cannot be reused.

### 6.1. Wrong: using one stream for two terminal operations

```java
Stream<NamedPipelineExample.Sale> sales =
    NamedPipelineExample.normalize(input.stream());

long count = sales.count();

// NOT ALLOWED: Stream has already been consumed.
// List<NamedPipelineExample.Sale> data =
//     sales.collect(Collectors.toList());
```

If you need both a count and a list over a **small, finite** dataset, collect once into a `List` and open new streams from that list. If you want to preserve lazy processing, create a fresh stream from a **re-openable source** for each terminal operation. Not every source (especially I/O sources) can be re-read for free.

### 6.2. Do not equate building a pipeline with running validation

Putting `normalizeSale` inside `map` causes validation to happen **when elements are consumed**:

```java
Stream<NamedPipelineExample.Sale> sales =
    NamedPipelineExample.normalize(input.stream());

// At this point, invalid data has not necessarily thrown an error yet.
List<NamedPipelineExample.Sale> checked =
    sales.collect(Collectors.toList());
```

Furthermore, a **short-circuiting** terminal operation like `findFirst` may not inspect every record; optimizations like `count` on a sized source may even skip `map` steps that do not change cardinality. Hence, **never use `map` as a guarantee that the entire source was validated**.

If the requirement is "validate all records before proceeding," provide **a fully consumed validation phase** or an explicit validation loop—do not merely build a pipeline and assume validation completed.


## 7. Test Each Contract Instead of Only the Final Output

A long pipeline is often tested only by passing a sample dataset and checking the final output. That is insufficient: if two steps have bugs that cancel each other out, an end-to-end test can still pass by accident.

Once functions are named and separated, test:

- **`normalizeSale`:** valid values are normalized; `null`, blank IDs, invalid statuses, and negative numbers are rejected.
- **`paidOnly`:** only `PAID` orders remain, preserving order and valid duplicates.
- **`summarize`:** per-customer counts and totals are accurate; tied totals sort by ID.
- **`process`:** steps connect properly with mixed statuses and amounts.
- **Boundary inputs:** empty source, single element, no PAID orders, multiple customers with tied totals, customer with multiple orders.
- **Non-interference:** neither the source nor shared state is mutated; the returned list is unmodifiable per our chosen contract.

### 7.1. Self-contained Java 8+ test program

Create `NamedPipelineTest.java` in the same directory as `NamedPipelineExample.java` from Section 5:

```java
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class NamedPipelineTest {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void expectInvalid(
            Runnable action, String message) {
        boolean rejected = false;
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        check(rejected, message);
    }

    public static void main(String[] args) {
        NamedPipelineExample.RawSale raw =
            new NamedPipelineExample.RawSale(
                " O-1 ", " KH-A ", "paid", 1000);

        NamedPipelineExample.Sale normalized =
            NamedPipelineExample.normalizeSale(raw);

        check("O-1".equals(normalized.orderId),
            "orderId chua trim");
        check("KH-A".equals(normalized.customerId),
            "customerId chua trim");
        check("PAID".equals(normalized.status),
            "status chua chuan hoa");
        check(normalized.amountCents == 1000,
            "amountCents bi thay doi");
        check("paid".equals(raw.status),
            "ham normalize da sua du lieu nguon");

        expectInvalid(
            () -> NamedPipelineExample.normalizeSale(null),
            "Phai tu choi ban ghi null");

        expectInvalid(
            () -> NamedPipelineExample.normalizeSale(
                new NamedPipelineExample.RawSale(
                    " ", "KH-A", "PAID", 100)),
            "Phai tu choi orderId trong");

        expectInvalid(
            () -> NamedPipelineExample.normalizeSale(
                new NamedPipelineExample.RawSale(
                    "O-2", null, "PAID", 100)),
            "Phai tu choi customerId null");

        expectInvalid(
            () -> NamedPipelineExample.normalizeSale(
                new NamedPipelineExample.RawSale(
                    "O-2", "KH-A", "UNKNOWN", 100)),
            "Phai tu choi status la");

        expectInvalid(
            () -> NamedPipelineExample.normalizeSale(
                new NamedPipelineExample.RawSale(
                    "O-2", "KH-A", "PAID", -1)),
            "Phai tu choi amount am");

        List<NamedPipelineExample.RawSale> source =
            Arrays.asList(
                raw,
                new NamedPipelineExample.RawSale(
                    "O-2", "KH-B", "PAID", 200),
                new NamedPipelineExample.RawSale(
                    "O-3", "KH-A", "REFUNDED", 5000),
                new NamedPipelineExample.RawSale(
                    "O-4", "KH-A", "PAID", 300)
            );

        List<NamedPipelineExample.Sale> paid =
            NamedPipelineExample.paidOnly(
                NamedPipelineExample.normalize(
                    source.stream()))
            .collect(Collectors.toList());

        check(paid.size() == 3,
            "Bo loc PAID sai so luong");
        check("O-1".equals(paid.get(0).orderId)
                && "O-2".equals(paid.get(1).orderId)
                && "O-4".equals(paid.get(2).orderId),
            "Bo loc PAID sai encounter order");

        List<NamedPipelineExample.CustomerSummary> result =
            NamedPipelineExample.process(source);

        check(result.size() == 2,
            "Sai so nhom khach hang");

        check("KH-A".equals(result.get(0).customerId)
                && result.get(0).totalCents == 1300
                && result.get(0).orderCount == 2,
            "Sai tong/so don KH-A");

        check("KH-B".equals(result.get(1).customerId)
                && result.get(1).totalCents == 200
                && result.get(1).orderCount == 1,
            "Sai tong/so don KH-B");

        List<NamedPipelineExample.CustomerSummary> empty =
            NamedPipelineExample.process(
                Collections.<NamedPipelineExample.RawSale>
                    emptyList());

        check(empty.isEmpty(), "Nguon rong phai tra rong");

        List<NamedPipelineExample.CustomerSummary> noPaid =
            NamedPipelineExample.process(
                Arrays.asList(
                    new NamedPipelineExample.RawSale(
                        "O-8", "KH-A", "PENDING", 77)));

        check(noPaid.isEmpty(),
            "Khong co PAID thi khong co nhom");

        List<NamedPipelineExample.CustomerSummary> tie =
            NamedPipelineExample.process(Arrays.asList(
                new NamedPipelineExample.RawSale(
                    "O-2", "KH-B", "PAID", 100),
                new NamedPipelineExample.RawSale(
                    "O-1", "KH-A", "PAID", 100)));

        check("KH-A".equals(tie.get(0).customerId)
                && "KH-B".equals(tie.get(1).customerId),
            "Thieu tie-breaker khi tong bang nhau");

        boolean unmodifiable = false;
        try {
            result.add(new NamedPipelineExample.CustomerSummary(
                "KH-X", 1, 10));
        } catch (UnsupportedOperationException expected) {
            unmodifiable = true;
        }
        check(unmodifiable,
            "Ket qua process phai unmodifiable");

        expectInvalid(
            () -> NamedPipelineExample.process(
                Arrays.asList(
                    new NamedPipelineExample.RawSale(
                        "O-9", "KH-X", "PAID", 1),
                    new NamedPipelineExample.RawSale(
                        "O-10", "KH-X", "BROKEN", 1))),
            "Phai phat hien ban ghi loi khi tieu thu het");

        System.out.println("PASS: named pipeline contracts");
    }
}
```

To compile and run it yourself:

```text
javac NamedPipelineExample.java NamedPipelineTest.java
java NamedPipelineExample
java NamedPipelineTest
```

When the program and all checks pass, `NamedPipelineTest` prints:

```text
PASS: named pipeline contracts
```

This is a **self-runnable test template**, not a claim that it was compiled during lesson authoring. The tests verify the selected contracts, not that every possible production input is covered.

### 7.2. Why are these tests valuable?

- Testing `normalizeSale` needs only **one record** to verify the rule.
- Testing `paidOnly` checks both count and **post-filter order**.
- Testing `summarize` via `process` verifies group count and totals, not just the first row's values.
- Testing tied totals forces code to include an **ascending secondary key**; without it, `Map` iteration order could make tests flaky.
- Testing invalid data verifies the **fail-fast policy**, rather than silent drops.
- Testing an empty source confirms no bogus groups are synthesized.
- Testing immutability of the source and result list verifies the state contract.

In production systems, add tests for integer overflow, Unicode customer IDs, very large inputs, duplicate order IDs, and concurrency cases if required by the domain.

## 8. Naming So Contracts Are Visible When Reading Code

A well-split pipeline should read clearly at the orchestration layer:

```java
List<CustomerSummary> result =
    summarize(paidOnly(normalize(source.stream())));
```

The names express the flow: **normalize → keep paid → summarize**.

### 8.1. Name by business intent, not incidental detail

| Vague name | Better name | Reason |
| --- | --- | --- |
| `step1` | `normalize` | Expresses the rule, not the position. |
| `fixData` | `normalizeSale` | States what record transformation happens. |
| `filterData` | `paidOnly` | States the filtering predicate. |
| `process2` | `summarize` | States the kind of output. |
| `doSomething` | `calculateCustomerTotals` | Conveys aggregation intent. |
| `check` | `validateStatus` | Names the condition being checked. |

A name like `paidOnly` fits when status is the sole condition. If the business later changes the rule to require both paid status and an amount threshold, consider renaming to `eligibleForRevenue` with an updated contract instead of secretly sneaking another condition into `paidOnly`.

### 8.2. Pick signatures by purpose

There are three common forms:

```java
// Single-element rule: pure, easy to unit test.
static Sale normalizeSale(RawSale raw);

// Intermediate step: keeps the pipeline lazy.
static Stream<Sale> normalize(Stream<RawSale> source);

// Aggregation boundary: returns a materialized result.
static List<CustomerSummary> summarize(
    Stream<Sale> paidSales);
```

If a step must return **both valid results and errors**, a plain `Stream<T>` may not capture the contract cleanly. In that case, design a `ValidationResult`, `Either`, or result object with two explicit collections rather than hiding errors inside `peek`.

### 8.3. Do you need a named function for every `map` and `filter`?

Not necessarily:

```java
List<String> names = users.stream()
    .filter(User::isActive)
    .map(User::getName)
    .collect(Collectors.toList());
```

When two method references are already self-explanatory, wrapping them in `activeUsers` and `extractNames` just to shorten one line can actually hurt readability. Extract a function when:

- The rule has a clear domain name.
- There is non-trivial branching or validation.
- Multiple places reuse the same rule.
- A behavior needs independent unit tests.
- You need to swap an error policy without touching the whole pipeline.

The goal is **meaningful boundaries**, not maximizing method count.

## 9. Use `peek` and Logging to Find Bugs, Not to Run Business Logic

`peek` is an intermediate operation that lets you observe elements consumed at a point in the pipeline. It is often handy for temporary logging:

```java
List<CustomerSummary> result = summarize(
    paidOnly(
        normalize(source.stream())
            .peek(sale ->
                System.out.println(
                    "Sau normalize: " + sale.orderId))
    )
);
```

When executed with the terminal `summarize`, this log reveals records after normalization **before status filtering**. To observe after filtering:

```java
Stream<NamedPipelineExample.Sale> paid =
    NamedPipelineExample.paidOnly(
        NamedPipelineExample.normalize(source.stream()));

List<NamedPipelineExample.Sale> snapshot = paid
    .peek(sale -> System.out.println(
        "Sau paidOnly: " + sale.orderId))
    .collect(Collectors.toList());
```

`peek` is not guaranteed to be invoked for every source element in **every pipeline**. Terminal operations can short-circuit and some operations can be optimized away, especially when elements are skipped or unneeded to compute the final result.

### 9.1. Do not use `peek` to update business state

Wrong:

```java
List<String> audit = new ArrayList<>();

long count = source.stream()
    .peek(sale -> audit.add(sale.orderId))
    .count();

// DO NOT assume audit contains all order IDs.
```

With a sized source and `count()`, the runtime may **skip executing `peek`** if traversal isn't needed to determine the count. In a parallel stream, adding to a shared `ArrayList` is also thread-unsafe.

If full audit logging is a requirement, build an **explicit business step** with proper failure, durability, and retry policies. `peek` is for **diagnostics**, not an essential part of the algorithm.

### 9.2. Logs must not leak sensitive data

In real applications, a record may hold email addresses, personal information, tokens, or payment details. Never dump full objects or sensitive salary/revenue figures into uncontrolled logs.

For example, log only **partially masked IDs** or aggregate counts; attach a request correlation ID, choose an appropriate log level, and turn off verbose debug logs once the incident is resolved. This is another benefit of named steps: logs can emit `stage=normalize` instead of an ambiguous `step=3`.

## 10. Materializing a Step to Inspect It: Useful, With Trade-offs

For finite in-memory sources, you can **temporarily** insert a terminal operation to capture each step's output:

```java
List<NamedPipelineExample.Sale> normalized =
    NamedPipelineExample.normalize(source.stream())
        .collect(Collectors.toList());

System.out.println("Normalized: " + normalized.size());

List<NamedPipelineExample.Sale> paid =
    NamedPipelineExample.paidOnly(normalized.stream())
        .collect(Collectors.toList());

System.out.println("Paid: " + paid.size());

List<NamedPipelineExample.CustomerSummary> result =
    NamedPipelineExample.summarize(paid.stream());
```

This creates three clear checkpoints: **after normalization**, **after filtering**, and **after summarization**. You can attach a debugger to inspect row counts, field values, ordering, and failing examples at each checkpoint.

However, materialization has costs:

| Benefit | Cost / Risk |
| --- | --- |
| Easy to inspect each step's list | Allocates intermediate collections and references |
| Easy to check counts/duplicates independently | Loses laziness; may consume the entire source |
| Easy to set breakpoints on small data | Unsuitable for very large or infinite streams |
| Easy to compare data before/after a step | Alters when errors surface, timing, and memory usage |
| Can open multiple new streams from the collected list | No longer identical to a time-varying I/O source |

**Core takeaway:** materialization is a **diagnostic technique or intentional data boundary**, not the default goal of refactoring. Once debugging is complete, consider returning to a lazy pipeline if keeping snapshots isn't required.

### 10.1. Never materialize an infinite source

```java
// AVOID: infinite source with an unbounded terminal collect.
// List<Integer> all = Stream.iterate(0, n -> n + 1)
//     .collect(Collectors.toList());
```

Set an explicit bound or write a finite aggregation:

```java
List<Integer> firstTen = Stream.iterate(0, n -> n + 1)
    .limit(10)
    .collect(Collectors.toList());

System.out.println(firstTen); // [0,1,2,3,4,5,6,7,8,9]
```

With I/O streams, `collect` does not automatically solve resource ownership either; a later section explains proper resource closing.

## 11. Choose an Error Policy Before Splitting the Pipeline

Three common policies:

| Policy | Behavior | When appropriate |
| --- | --- | --- |
| **Fail-fast** | Throw on an invalid record; do not publish partial results as success | Financial reports, data that must be 100% valid |
| **Skip invalid** | Drop invalid records and continue | Business allows skipping provided errors are tracked |
| **Collect errors** | Collect valid data and an error list together | Batch file imports, ETL, data-quality checks |

`NamedPipelineExample` uses **fail-fast**. Replacing `normalizeSale` with a `map` that catches all errors, returns `null`, and filters `Objects::nonNull` silently changes the contract:

```java
// AVOID if the business requires rejecting invalid data:
source.stream()
    .map(raw -> {
        try {
            return NamedPipelineExample.normalizeSale(raw);
        } catch (IllegalArgumentException ex) {
            return null; // Swallows the error and loses information.
        }
    })
    .filter(Objects::nonNull);
```

If the goal is importing data with per-row error reporting, a **simple, transparent loop** can be better than trying to cram two output streams into one pipeline:

```java
List<NamedPipelineExample.Sale> valid =
    new ArrayList<>();
List<String> errors = new ArrayList<>();

int index = 0;

for (NamedPipelineExample.RawSale raw : source) {
    try {
        valid.add(
            NamedPipelineExample.normalizeSale(raw));
    } catch (IllegalArgumentException ex) {
        errors.add(
            "Row " + index + ": " + ex.getMessage());
    }
    index++;
}

System.out.println("Valid: " + valid.size());
System.out.println("Errors: " + errors.size());
```

This snippet illustrates **a different policy** from fail-fast; when implementing it, decide whether to abort past an error threshold, whether to mask sensitive fields in error messages, and whether error reporting order matters.

What matters is that **the contract is explicitly named**: functions like `validateAll`, `partitionValidInvalid`, or `rejectInvalid` are far clearer than a `map` that secretly swallows exceptions.

### 11.1. When do exceptions happen?

With a lazy step:

```java
Stream<NamedPipelineExample.Sale> stage =
    NamedPipelineExample.normalize(
        source.stream());
```

`normalizeSale` has not necessarily executed yet. When the terminal operation consumes elements, `IllegalArgumentException` may be thrown from an invalid record. If the pipeline runs in parallel and multiple records are invalid, **do not depend on which record fails first**, as scheduling order is not guaranteed.

If you must report **all errors in row order**, run a controlled validation pass and collect errors before parallelizing valid records, instead of relying on parallel stream exception order.

## 12. Draw a Clear Boundary Between Processing and I/O Resources

Returning `Stream<T>` can be a clean contract when the source is a `List`. But with `Files.lines`, `Files.walk`, or a database cursor, the stream may hold an I/O resource that needs closing.

Wrong:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

// AVOID: returns an already-closed stream.
static Stream<String> brokenLines(Path path)
        throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.filter(s -> !s.isEmpty());
    }
}
```

When the method returns, `try-with-resources` has already closed `lines`. The caller cannot consume the pipeline as intended.

Correct approaches: **consume the source inside the resource-owning scope**, or transfer closing responsibility to the caller via a clearly documented API.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static List<String> firstNonEmptyLines(Path path)
        throws IOException {

    try (Stream<String> lines = Files.lines(
            path, StandardCharsets.UTF_8)) {

        return lines
            .filter(s -> !s.trim().isEmpty())
            .limit(10)
            .collect(Collectors.toList());
    }
}
```

This is a **controlled eager step**: it returns a list of up to 10 lines and closes the resource on time. Note that I/O errors can occur when opening the file (`IOException`) or lazily during traversal (`UncheckedIOException`). Do not collapse all failures into an empty list, because "no lines" is different from "failed to read file."

### 12.1. A method allowing the caller to close

If you must return an I/O-backed stream, the contract must state that the caller **owns closing it**:

```java
// Example API with an explicit responsibility contract:
static Stream<String> openLines(Path path)
        throws IOException {
    return Files.lines(path, StandardCharsets.UTF_8);
}

// Caller:
try (Stream<String> lines = openLines(path)) {
    long count = lines
        .filter(s -> !s.trim().isEmpty())
        .count();
}
```

In service applications, callback-accepting APIs are often preferred to keep closing centralized. Either way, splitting a pipeline into named steps **must never drop resource-cleanup ownership**.


## 13. Ordering, Grouping, and Cardinality Must Be Part of the Contract

When splitting a pipeline, don't write vaguely "this step preserves the data." Specify **how many elements enter, how many can exit**, and the output ordering.

| Operation | Cardinality relationship | Ordering notes |
| --- | --- | --- |
| `map` | One-to-one if no exception | Preserves logical order if source is ordered. |
| `filter` | At most one per input | Preserves relative order of remaining elements. |
| `flatMap` | Zero, one, or many per input | Depends on source order and sub-streams. |
| `distinct` | Never increases element count | On ordered streams keeps first occurrence per `equals`. |
| `sorted` | Preserves element count | Establishes order via comparator. |
| `skip` / `limit` | Drops/caps by count | Depends on encounter order if source is ordered. |
| `groupingBy` | Many elements into groups | No default map key iteration order guaranteed. |
| Lesson's `summarize` | Many orders into one row/customer | Sorts total descending, customer ascending on ties. |

### 13.1. Never treat a `Map` as an ordered list

Example:

```java
Map<String, Long> totals = sales.stream()
    .collect(Collectors.groupingBy(
        sale -> sale.customerId,
        Collectors.summingLong(
            sale -> sale.amountCents)));
```

This snippet assumes `sales` is a `Stream<Sale>` with those fields. `groupingBy` returns a `Map`; do not rely on the order of `totals.entrySet()` to decide which customer comes first.

If the report asks for "highest revenue first," sort by **the aggregated total** after grouping. The comparator needs a **secondary key** when totals tie so tests are deterministic.

### 13.2. Distinguish "no data" from "computation error"

On an empty source, `groupingBy` returns an empty map and `summarize` returns an empty list. That is a **valid result**.

By contrast, when `normalizeSale` sees a `null` record and throws `IllegalArgumentException`, do not interpret the failure as "zero revenue." These two states have distinct business meanings and require separate tests.

### 13.3. Do not overlook duplicate order ID constraints

The current aggregation counts **each PAID record as one order**, without deduplicating `orderId`. If a file contains two rows with the same ID, totals and counts are doubled. That is not a random bug in `groupingBy`, but **an unspecified contract requirement**.

If the business requires unique `orderId`s, introduce a `rejectDuplicateOrderIds` or `deduplicateById` step with an explicit policy:

- On duplicate IDs, throw an error or pick one record?
- If two rows share an ID but differ in amount, is dropping one allowed?
- Does encounter order decide which record is kept?
- Is memory needed to track seen IDs?

**Do not blindly use `distinct()`** if `Sale` does not define domain `equals`/`hashCode`, or if the requirement is to reject duplicates rather than deduplicate. A duplicate-check step may require a `Set` of seen IDs and careful design before parallel execution.

## 14. Do Step Contracts Change When Calling `parallel()`?

A pipeline split into named functions is **not automatically thread-safe in parallel**. Correctness still depends on:

- **Stateless** and **non-interfering** callbacks.
- Reduction operations and `combiner`s satisfying their contracts.
- Sources, state, and collectors suitable for splitting.
- Encounter-order requirements enforced via order-preserving operations.

In our example:

```java
List<NamedPipelineExample.CustomerSummary> parallel =
    NamedPipelineExample.summarize(
        NamedPipelineExample.paidOnly(
            NamedPipelineExample.normalize(
                source.parallelStream())));
```

`normalizeSale` constructs a new object without mutating source data. `paidOnly` only checks status. `Collectors.groupingBy` with `summarizingLong` uses combiners provided by standard collectors. The final output is sorted, so it **can** match sequential execution within the specified numeric range. That **does not guarantee it runs faster** or that future edits remain safe.

### 14.1. Testing sequential vs. parallel equivalence

```java
List<NamedPipelineExample.CustomerSummary> sequential =
    NamedPipelineExample.process(source);

List<NamedPipelineExample.CustomerSummary> parallel =
    NamedPipelineExample.summarize(
        NamedPipelineExample.paidOnly(
            NamedPipelineExample.normalize(
                source.parallelStream())));

if (sequential.size() != parallel.size()) {
    throw new AssertionError("Khac so nhom");
}

for (int i = 0; i < sequential.size(); i++) {
    NamedPipelineExample.CustomerSummary a =
        sequential.get(i);
    NamedPipelineExample.CustomerSummary b =
        parallel.get(i);

    if (!a.customerId.equals(b.customerId)
            || a.orderCount != b.orderCount
            || a.totalCents != b.totalCents) {
        throw new AssertionError(
            "Khac ket qua o vi tri " + i);
    }
}
```

This snippet can be placed in a Java 8+ test method in the same package as `NamedPipelineExample`. We compare **field values**, since `CustomerSummary` in the sample does not override `equals`. Never use `==` to compare result objects.

### 14.2. Small changes can break the contract

Wrong:

```java
List<String> seen = new ArrayList<>();

Stream<NamedPipelineExample.Sale> stage =
    NamedPipelineExample.normalize(
        source.parallelStream())
    .peek(sale -> seen.add(sale.orderId));
```

`ArrayList` is not safe for concurrent writes from multiple threads, and `peek` is not guaranteed to run for every element. This is not a valid way to maintain an audit log or count orders.

Similarly, replacing `summarize` with a `reduce` that mutates a shared `HashMap` via side effects can introduce race conditions. Use standard collectors or design a collector with proper supplier/accumulator/combiner instead of mutating an external accumulator.

### 14.3. Exception order may differ

If multiple rows are invalid, a parallel stream may discover a failing row that is not the first one in encounter order. Thus, to report errors in file order, **separate a sequential validation pass** or collect all errors in order before processing valid records in parallel.

**Summary:** sequential correctness is a necessary condition, not sufficient proof for parallel execution. Test both whenever a project actually uses `parallel()`, and benchmark performance separately.

## 15. Use an Independent Reference Algorithm for Verification

One way to catch subtle bugs is comparing the pipeline's output against a **reference loop** on small datasets. Avoid writing tests where the expected result is computed by calling `normalize`, `paidOnly`, and `summarize` again: if a rule is wrong in both places, the test won't catch it.

Independent reference example for totals (assuming normalized data and no `long` overflow):

```java
import java.util.HashMap;
import java.util.Map;

Map<String, Long> expected = new HashMap<>();

for (NamedPipelineExample.Sale sale : normalizedSales) {
    if (!"PAID".equals(sale.status)) {
        continue;
    }

    Long old = expected.get(sale.customerId);
    long newTotal = (old == null ? 0L : old)
        + sale.amountCents;

    expected.put(sale.customerId, newTotal);
}
```

Now compare every total against `summarize`, rather than only checking group counts. A reference loop can have bugs too, but two independent implementations greatly reduce the chance of **sharing the same implementation mistake**.

### 15.1. Properties worth verifying

For valid data, non-overflowing sums, and the "PAID only" policy:

1. **No phantom customers:** every `customerId` in the result must have at least one PAID order in the input.
2. **Order count:** sum of `orderCount` across all groups equals the number of PAID rows.
3. **Total amount:** sum of `totalCents` across all groups equals the sum of `amountCents` of PAID rows.
4. **Element preservation on normalization:** when error-free, `normalize` neither drops nor duplicates rows.
5. **Filtering never multiplies:** `paidOnly` never increases row count.
6. **Ordered output:** any two adjacent groups satisfy the published comparator.
7. **Input-order independence:** when only per-customer sums are required and output is sorted, shuffling valid rows must not change **the report values**.
8. **Non-interference:** raw input data is never mutated by the pipeline.

Avoid false properties: "changing input order never affects the result" is **not true for all Streams**. Operations like `findFirst`, `limit`, or string concatenation may intentionally depend on order; each step must state its own contract.

### 15.2. Valuable test cases

| Case | Input | Expected result / policy |
| --- | --- | --- |
| Empty source | `[]` | Returns empty list. |
| Single PAID order | One valid record | One group, count 1, exact amount. |
| No PAID orders | Only PENDING/REFUNDED | Returns empty list. |
| Mixed statuses | PAID and REFUNDED | Counts only PAID. |
| Whitespace/casing | Padded IDs, `paid` | Normalized per contract. |
| Invalid data | `null`, blank ID, unknown status | Throws `IllegalArgumentException`. |
| Tied totals | Two customers with equal sums | Sorted by secondary ID key. |
| Duplicate order IDs | Two rows with same ID | Follows business policy; current sample **does not auto-deduplicate**. |
| Numeric limits | Sums near `Long.MAX_VALUE` | Design overflow checks if domain requires. |
| Parallel | Sufficiently large, valid source | Matches sequential result per contract. |

For randomized property tests, **save a reproducible seed** and capture the smallest failing input instead of just printing "random test failed." That lets you reproduce the failure and pinpoint which step violated its contract.

## 16. Refactoring a Long Pipeline Under Control

Follow a practical step-by-step workflow:

### Step 1 — Freeze current behavior with tests

Take a representative dataset with both normal and boundary cases. Capture **the behavior to preserve**, without necessarily locking in undesired bugs.

If current behavior is ambiguous, document unconfirmed business assumptions explicitly. Structural refactoring must not silently decide null, refund, or deduplication policies.

### Step 2 — Identify boundaries by type and responsibility

Read the pipeline and mark its regions:

```text
input
  → parse/validate
  → normalize
  → filter
  → enrich/map
  → group/reduce
  → sort/present
  → output
```

Not every pipeline has all stages; extract only the boundaries that genuinely exist.

### Step 3 — Write the contract for each region

Record types, error conditions, ordering, and cardinality. For example:

```text
normalizeSale:
  input  : non-null RawSale
  output : Sale with trimmed IDs and uppercase status
  error  : IllegalArgumentException on missing/invalid fields
  order  : not applicable at single-element level
  effect : does not mutate RawSale

paidOnly:
  input  : normalized Stream<Sale>
  output : Stream<Sale> with PAID only
  order  : preserves encounter order if source is ordered
  effect : does not mutate Sale
```

### Step 4 — Extract the smallest pure functions first

Start with single-element functions like `normalizeSale`, as they are easiest to test. Only then name groups of stream operations like `paidOnly`. Avoid changing error policies and aggregation algorithms simultaneously when the initial goal is clarifying structure.

### Step 5 — Separate terminal boundaries cleanly

Make sure readers know which steps stay lazy and which consume the `Stream`. A method named `summarize` returning a `List` or `Map` is a much clearer boundary than a method returning a stream while quietly invoking multiple terminal operations.

### Step 6 — Re-run tests and check metadata

Verify invariants on row counts, total amounts, ordering, and exceptions. If `parallel` is used, verify that mode too.

### Step 7 — Measure performance when needed, then remove temporary diagnostics

After refactoring, having small named functions **does not necessarily** slow down a pipeline; the JIT and Stream runtime optimize calls well. However, materializing too many lists, adding unnecessary `sorted` steps, or logging every record can degrade performance significantly.

Never decide based on a hunch that "more methods means slower." Benchmark representative workloads with proper warm-up (considering JMH) and separate actual computation cost from I/O source cost.

## 17. Walkthrough of a Tricky Bug: Right Count, Empty Debug List

Suppose a developer adds logging inside `map`:

```java
List<String> visited = new ArrayList<>();

long count = source.stream()
    .map(sale -> {
        visited.add(sale.orderId);
        return sale;
    })
    .count();

System.out.println(count);
System.out.println(visited.size());
```

For a `List` source with known size, `count()` can optimize away running the mapper because `map` does not alter cardinality. Then `count` equals the source size while `visited` may be empty.

### 17.1. How to diagnose it properly

Clarify the goal:

- To **count elements**, call `source.size()` or `source.stream().count()`.
- To **transform and inspect results**, use `map(...).collect(Collectors.toList())` and inspect the collected result.
- To **guarantee per-record processing for business reasons**, write an operation step with an explicit contract instead of attaching side effects to `map` or `peek` followed by `count`.

Example for inspecting normalized data:

```java
List<NamedPipelineExample.Sale> checked =
    NamedPipelineExample.normalize(source.stream())
        .collect(Collectors.toList());

System.out.println(checked.size());
```

`collect` into a list requires obtaining the mapped value of each valid element, making it proper where `map` updating `visited` was wrong. Still, avoid placing mandatory side effects inside mappers; `normalizeSale` should return a new object without interfering with the source.

### 17.2. Regarding `findFirst` and `anyMatch`

These terminal operations can finish **before traversing the entire source**:

```java
boolean anyPaid = source.stream()
    .map(NamedPipelineExample::normalizeSale)
    .anyMatch(sale -> "PAID".equals(sale.status));
```

`anyPaid` only confirms that **at least one** PAID order exists within the prefix examined to reach a decision. It **does not guarantee** that all remaining rows were normalized, validated, or logged.

If the contract says "all rows must be valid," validate the whole dataset first; never use `anyMatch` to validate an entire collection.

## 18. Design Pitfalls and Remedies

| Pitfall | Consequence | Remedy |
| --- | --- | --- |
| Splitting pipeline into `step1`, `step2`, `step3` | Adds no self-documentation | Name steps after business responsibilities. |
| One method validates, logs, filters, and aggregates | Hard to test and evolve policies | Separate record rule, lazy step, terminal boundary. |
| Writing comments only, no boundary tests | Contracts break silently on refactor | Add tests for null, empty, status, tie-breaking. |
| Using `filter(Objects::nonNull)` to swallow errors | Silently drops records | Choose fail-fast or explicit error collection. |
| Calling `count` then reusing the same `Stream` | `IllegalStateException` | Create a new stream or materialize intentionally. |
| Calling `normalize` and assuming all items are validated | Intermediate operations are lazy | Consume with an appropriate terminal operation when full validation is needed. |
| Putting side effects in `peek`/`map` | Callbacks may be skipped or reordered | Use returned values or a dedicated business step. |
| Collecting intermediate lists everywhere just for debugging | Increases memory, shifts execution timing | Use only for diagnosis; avoid holding large snapshots. |
| Relying on `Map` order after grouping | Unstable results | Sort with comparator and tie-breaker. |
| Using `distinct()` to catch duplicate order IDs | May drop data under wrong policy | Define key and handle duplicate errors explicitly. |
| `reduce` with a shared mutable identity | Wrong results in parallel | Use a valid collector or non-shared accumulator. |
| `parallel` with external counters/lists | Race conditions, non-deterministic order | Stateless functions, standard collectors, parallel tests. |
| Logging full sensitive records | Data leaks and slowdowns | Controlled logging, mask sensitive fields. |
| Returning a stream out of `try-with-resources` | Stream closed before consumption | Consume inside or transfer closing ownership explicitly. |
| Ignoring `UncheckedIOException` from lazy sources | Mistakes I/O failures for empty data | Distinguish I/O errors from empty sets. |
| `long` totals that can overflow | Silent wrong numbers in reports | Define bounds; use `addExact`/`BigInteger` when needed. |
| Re-running the entire pipeline for multiple metadata | Wastes CPU/I/O, risks inconsistency | Snapshot or design a single-pass aggregation when appropriate. |
| Using `Stream.toList()` in Java 8 examples | Fails to compile on Java 8 | Use `collect(Collectors.toList())` in Java 8 code. |

## 19. Practice Exercises

### Exercise 1 — Identify boundaries

Given the pipeline:

```java
List<String> result = names.stream()
    .filter(s -> s != null)
    .map(String::trim)
    .filter(s -> !s.isEmpty())
    .map(String::toUpperCase)
    .distinct()
    .sorted()
    .collect(Collectors.toList());
```

Propose two or three named functions reflecting groups of rules. State input/output types, ordering, and the `null` policy.

### Exercise 2 — Specify a filter contract

Write `paidOnly(Stream<Sale>)` keeping only `PAID` status. Should null/unknown status checks live here or already belong in `normalizeSale`? Explain.

### Exercise 3 — Checking empty data

Given a list with no PAID orders, what should `process` return? Should it synthesize a `CustomerSummary` with total 0 for every customer seen?

### Exercise 4 — Deterministic output order

Two customers have equal total amounts. Why is sorting descending by total amount alone insufficient for a stable report? Write a comparator with a tie-breaker.

### Exercise 5 — The `peek` trap

Does `source.stream().peek(logAction).count()` guarantee `logAction` runs for every element? Does `parallel()` make all logs appear in source order?

### Exercise 6 — Avoiding double stream consumption

You need both a `count` and a `List` after normalization on a finite `List<RawSale>`. Propose a way to avoid reusing a consumed stream and state the memory trade-off.

### Exercise 7 — Spotting error-policy drift

Why can catching `IllegalArgumentException` inside `map`, returning `null`, and adding `filter(Objects::nonNull)` break a fail-fast contract? How should you collect per-row errors if needed?

### Exercise 8 — I/O and lifecycle

An `openLines(Path)` method returns `Files.lines(path)`. Who closes the stream? Why shouldn't a method open `Files.lines` inside a `try` block and return the stream for external reading?

### Exercise 9 — Parallel correctness

If `normalizeSale` is modified to increment a `static int counter` on each call, what issues can arise under `parallel()`? What should you use instead if the goal is merely counting PAID records?

### Exercise 10 — Designing a duplicate-ID check step

The business forbids two orders with the same `orderId` in one report. Name the new step, state its error policy, choose its position in the pipeline, and propose how to test it.

## 20. Answers and Hints

**Exercise 1.** You can create `normalizeNames(Stream<String>)` to drop nulls, trim, drop empty strings, and uppercase, then `uniqueSortedNames(Stream<String>)` for `distinct` and `sorted`. Or extract `normalizeName(String)` for the single-string rule and define an explicit null contract. Remember that filtering out nulls implements a **skip invalid** policy, not fail-fast.

**Exercise 2.** When an independent normalize/validate phase exists, `paidOnly` should only check `"PAID".equals(sale.status)` without repeating all rules. If input may arrive from unvalidated callers, document the precondition or validate at the API boundary.

**Exercise 3.** `process` returns an empty list per our contract, because it aggregates only PAID orders. Creating zero-total groups for customers without PAID orders is a different requirement that needs a separate customer master list.

**Exercise 4.**

```java
Comparator<CustomerSummary> cmp =
    Comparator.comparingLong(
            (CustomerSummary s) -> s.totalCents)
        .reversed()
        .thenComparing(s -> s.customerId);
```

This comparator assumes `CustomerSummary` is in scope. The secondary key guarantees deterministic ordering when two customers have equal totals.

**Exercise 5.** No. `peek` may not even be evaluated if `count` can determine the source size directly. In parallel mode, log ordering is even less guaranteed. Use logging for diagnostics, not mandatory auditing.

**Exercise 6.** Collect once into `List<Sale> normalized = normalize(source.stream()).collect(Collectors.toList());`, then read `long count = normalized.size();` and reuse the list. The trade-off is materializing the entire dataset in memory proportional to source size and losing laziness on very large inputs.

**Exercise 7.** That turns validation failures into silently dropped records, making a report look valid while missing data. If the business requires fail-fast, let the exception propagate. If it requires collecting errors, iterate through all rows and collect valid records separately alongside indexed errors using a loop or a dedicated result object.

**Exercise 8.** The caller of `openLines` must close it with `try (Stream<String> lines = openLines(path)) { ... }` when the API transfers ownership. Returning a stream from inside the opening method's `try-with-resources` fails because the block exits and closes the stream before the caller consumes it.

**Exercise 9.** An unsynchronized `static int counter` causes race conditions; even `AtomicInteger` will not yield numbers matching encounter order. If you only need to count PAID records, use `normalize(...).filter(...).count()` on an appropriate source; do not count via side effects in a mapper.

**Exercise 10.** Place `rejectDuplicateOrderIds` after normalization (to compare trimmed IDs)—either before `paidOnly` if uniqueness applies to **the entire source**, or after `paidOnly` if duplicates matter only among PAID orders. Contract: if a duplicate ID is detected, throw an informative error; otherwise, preserve all records and order. Test with duplicate IDs, distinct IDs, padded IDs, empty sources, and mixed statuses. If using a `Set` to track seen IDs, avoid shared-state predicates in parallel streams; use a controlled, separate checking step.

## 21. Refactoring Checklist for Pipelines

- [ ] Identified each stage's true responsibility, not just split by line count.
- [ ] Function names express **business rules**, avoiding `step1` or `doWork`.
- [ ] Each stage's input/output types are explicit, avoiding unnecessary `Object`.
- [ ] Preconditions and postconditions cover `null`, blank strings, negative numbers, and statuses.
- [ ] Error policy is explicit: fail-fast, skip invalid, or collect errors.
- [ ] Documented rules for **cardinality** and encounter order.
- [ ] Element-level transformations are pure and directly unit-tested.
- [ ] Filter and aggregation steps have their own tests, not just end-to-end tests.
- [ ] Grouping steps sort explicitly when output order matters.
- [ ] Test cases cover ties, empty input, no matches, and invalid records.
- [ ] Never reuse a `Stream` after a terminal operation.
- [ ] Do not rely on `peek`/`map` side effects to guarantee every record was processed.
- [ ] Do not materialize every step on infinite or very large sources.
- [ ] For I/O sources, `close` ownership is documented and enforced.
- [ ] Source data is not mutated during pipeline traversal unless concurrent mutation is supported.
- [ ] `reduce`/`collect` satisfy parallel contracts if parallelized.
- [ ] Separated correctness from performance; optimize only after measuring.
- [ ] Examples use APIs compatible with the target Java version.

## 22. Summary

A maintainable pipeline makes clear **which rules data passes through** and **which rule is currently under test**:

```text
RawSale
   |
 normalizeSale / normalize
   |       (validate and normalize, may fail)
   v
 Sale
   |
 paidOnly
   |       (filter by PAID status)
   v
 Stream<Sale>
   |
 summarize
   |       (grouping + count/sum + sort)
   v
 List<CustomerSummary>
```

Keep these principles in mind:

1. **One name — one responsibility:** name stages after business semantics.
2. **Testable contracts:** state preconditions, postconditions, error handling, cardinality, ordering, and side effects.
3. **Keep laziness where appropriate:** stream-returning functions build pipelines; terminal functions produce materialized results.
4. **Test in layers:** unit test single-record rules, test intermediate steps, test end-to-end, and cross-check against a reference implementation when useful.
5. **Debug purposefully:** use `peek` to observe, not to run business actions; materialize when diagnosing and understand its cost.
6. **Avoid resource and state bugs:** never reuse a consumed stream, never leak an I/O stream outside its closing scope, and never mutate the source mid-pipeline.
7. **Preserve semantics when optimizing:** grouping and sorting require explicit ordering; `parallel()` never fixes side effects or broken combiners.

Splitting long pipelines into **named steps with clear contracts** does more than tidy up orchestration code; more importantly, it lets you see where data changes, write reliable tests, diagnose issues quickly, and evolve Java Stream API pipelines without drifting from business rules.
