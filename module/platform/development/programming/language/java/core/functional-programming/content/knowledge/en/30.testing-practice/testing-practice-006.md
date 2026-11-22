# Practicing Filtering, Normalizing, and Summing Orders with Java Streams

## 1. Practice goal and context

A sales system receives a list of raw orders, including paid, pending, and cancelled orders. Order IDs, customer IDs, and SKUs may contain whitespace or inconsistent uppercase/lowercase letters. Each order has multiple line items, each with a quantity and unit price. The task is to **build a clear, verifiable processing pipeline**:

1. **Filter** only orders in the paid status (**PAID**).
2. **Normalize** order IDs, customer IDs, and SKUs according to a consistent rule.
3. **Validate** required data: non-blank codes, non-null line items, positive quantity, non-negative unit price.
4. **Calculate line subtotal** = quantity × unit price; **order total** = sum of line subtotals.
5. **Aggregate total revenue by customer**, and also compute the **grand total revenue across all selected orders**.
6. **Test** the happy path, empty sets, invalid orders, arithmetic overflow, ordering, statuses, and missing-data scenarios.

This is a Java core — **functional programming** practice exercise, so the focus is not merely writing a `stream().filter().map().collect()` chain. More importantly, it is about clearly defining **input contracts**, **data transformations**, **result invariants**, and **error-handling policies**.

Monetary scope of the example:

- All monetary values are stored as **long amountCents**, i.e., the **smallest currency unit** of a hypothetical currency. No currency conversion.
- No tax, discount, shipping fee, refund, or percentage rounding is applied. If business rules include those factors, calculation rules must be added before counting revenue.
- **PAID** is treated as the eligible revenue status under the exercise's assumptions. Real accounting systems may need to distinguish paid, recognized revenue, refunded, and accounting adjustments.
- **Do not silently swallow errors** on PAID orders. In the main approach, bad data causes processing to fail; a later section shows how to collect per-order errors if business rules require continuing.

### 1.1. Sample data

| Raw order ID | Raw customer | Status | Line items | Valid total |
| --- | --- | --- | --- | ---: |
| " so-01 " | " kh01 " | PAID | 2 × 12,500; 1 × 15,000 | 40,000 |
| "SO-02" | "kh02" | PENDING | Invalid test line item | Not counted |
| " so-03 " | "kh01" | PAID | 1 × 12,500; 3 × 7,000 | 33,500 |
| "SO-04" | "kh03" | CANCELLED | No line items | Not counted |

Expected result:

~~~text
Paid receipts: 2
SO-01 | KH01 | 40000
SO-03 | KH01 | 33500
Customer totals: {KH01=73500}
Grand total: 73500
~~~

Amounts in stdout are **amountCents**, not formatted for display currency. Grand total = **40,000 + 33,500 = 73,500**.

## 2. Designing the data model before writing Streams

We use Java 17 **records** to represent raw data and processed data:

~~~java
enum Status {
    PAID, PENDING, CANCELLED, REFUNDED
}

record RawLine(String sku, int quantity, long unitPriceCents) {}

record RawOrder(
        String id,
        String customerId,
        Status status,
        List<RawLine> lines
) {}

record BillLine(
        String sku,
        int quantity,
        long amountCents
) {}

record Receipt(
        String orderId,
        String customerId,
        List<BillLine> lines,
        long amountCents
) {}
~~~

This is an **illustrative set of model declarations**, requiring `import java.util.List`. The complete program in section 5 has all needed declarations and imports.

Distinctions:

- **RawLine** holds raw SKU, quantity, and unit price.
- **RawOrder** holds source data. It does not assume strings are normalized.
- **BillLine** holds the normalized SKU and computed line amount. Quantity may still be needed for explanation and reconciliation.
- **Receipt** represents a normalized and priced order, along with its list of lines and total.

**Why separate RawOrder from Receipt?** A pipeline is easier to test when it does not mutate source objects directly. Using **map** to create new records lets later steps trust the normalized-data contract instead of repeatedly handling varied raw code formats.

Records reduce boilerplate and provide accessors, equals/hashCode, and toString; however, **records do not validate inputs automatically**. If a record holds a mutable List, the record declaration itself does not provide deep immutability. In the main program, we intentionally construct results so the List structure cannot be modified.

### 2.1. Naming by currency unit

The names **unitPriceCents** and **amountCents** intentionally include the unit. A common mistake is mixing units:

~~~java
long amountCents = quantity * unitPriceCents;
double amountMajor = amountCents / 100.0;
~~~

This is an illustrative snippet without input variable declarations. Converting to major units for display should happen only at the UI boundary if the currency contract allows it. **Do not use double for financial calculations requiring decimal precision** without evaluating rounding and precision requirements.

**Special note:** the normal expression **quantity * unitPriceCents** **does not report overflow**. This exercise uses **Math.multiplyExact** and **Math.addExact** so wrong revenue is never produced silently.

## 3. Dividing pipeline responsibilities

Design a sequence of steps with clear responsibilities:

~~~text
List<RawOrder>
       |
       |  check source collection is non-null
       v
Stream<RawOrder>
       |
       |  check each RawOrder is non-null
       v
filter(status == PAID)
       |
       |  drop PENDING / CANCELLED / REFUNDED
       v
map(toReceipt)
       |
       |  normalize codes
       |  validate line items
       |  compute amountCents per line
       |  sum order total with Math.addExact
       v
List<Receipt>
       |
       +-- collect(toMap(..., Math::addExact, TreeMap::new))
       |                  -> revenue by customer
       |
       +-- mapToLong(...).reduce(0L, Math::addExact)
                          -> grand total revenue
~~~

**Step order is not arbitrary.** Under this exercise's contract:

- **Only PAID orders are processed into Receipts**. Line item data on PENDING orders is skipped during revenue calculation. Moving **map(toReceipt)** before **filter** could cause a PENDING order with an invalid line item to fail the entire report even though its lines are not needed.
- **Null RawOrder is treated as a source structure error**, not silently dropped.
- **Null Status is treated as an input error**, not automatically treated as "not PAID".
- Errors on **PAID orders** must be caught; there is no default rule turning errors into 0 revenue.

This is the **specific policy of this practice exercise**. Another program might require **validating all orders before filtering** because bad data on unpaid orders must also be reported. In that case, change the order intentionally and write tests for the new rule.

## 4. Data normalization: pure, clear, testable

A common code-normalization function:

~~~java
static String normalizeCode(String raw, String fieldName) {
    if (raw == null) {
        throw new IllegalArgumentException(fieldName + " is null");
    }
    String result = raw.strip().toUpperCase(Locale.ROOT);
    if (result.isEmpty()) {
        throw new IllegalArgumentException(fieldName + " is blank");
    }
    return result;
}
~~~

This is an **illustrative method**, requiring `import java.util.Locale` and placement inside a class.

Steps:

1. **Check null before calling strip()**. Otherwise, **NullPointerException** occurs before we can provide a helpful error message.
2. **strip()** removes Unicode whitespace at both ends per `Character.isWhitespace`, differing slightly from the older `trim()`.
3. **toUpperCase(Locale.ROOT)** produces codes independent of the running machine's default locale.
4. **isEmpty()** checks for an empty code after normalization, preventing whitespace-only strings from slipping through.
5. The function returns a new String and does not mutate source data. Same input produces the same output under the applied rules.

Examples:

~~~text
" so-01 "    -> "SO-01"
" kh01 "     -> "KH01"
" cf-01 "    -> "CF-01"
" bánh "     -> "BÁNH"
"   "        -> IllegalArgumentException
null         -> IllegalArgumentException
~~~

**Not every code should be uppercased.** This assumes IDs/SKUs are **case-insensitive**. If an inventory system uses case-sensitive codes, uppercasing can merge two distinct codes into one; in that case this rule must not be applied. For SKUs with meaningful internal spaces, **strip** only removes leading and trailing spaces without deleting the middle.

### 4.1. Normalization vs validation

- **Normalization**: converts equivalent representations into a canonical form, such as strip and uppercase.
- **Validation**: checks whether data satisfies constraints, such as non-empty code, quantity greater than 0.
- **Calculation**: applies arithmetic rules and domain bounds.
- **Aggregation**: sums validated results.

Do not write a long lambda that mutates strings, queries a database, checks permissions, and adds money into an external variable. Extract small functions with meaningful names so they can be tested independently.

### 4.2. Do not treat a normalized code as a verified identity

`"KH01"` after uppercasing is still just a **normalized string**. Whether that customer ID exists, belongs to the order placer, or is authorized to purchase must be verified by the responsible business/data layer. **Normalization does not replace identity verification.**

## 5. Complete Java 17 program: filter, normalize, sum

Create the file **OrderPipelineDemo.java**:

~~~java
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.stream.Collectors;

enum Status {
    PAID, PENDING, CANCELLED, REFUNDED
}

record RawLine(String sku, int quantity, long unitPriceCents) {}

record RawOrder(
        String id,
        String customerId,
        Status status,
        List<RawLine> lines
) {}

record BillLine(
        String sku,
        int quantity,
        long amountCents
) {}

record Receipt(
        String orderId,
        String customerId,
        List<BillLine> lines,
        long amountCents
) {}

public class OrderPipelineDemo {
    static String normalizeCode(String raw, String fieldName) {
        if (raw == null) {
            throw new IllegalArgumentException(fieldName + " is null");
        }

        String normalized = raw.strip().toUpperCase(Locale.ROOT);
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException(
                    fieldName + " is blank");
        }
        return normalized;
    }

    static Receipt toReceipt(RawOrder order) {
        String orderId = normalizeCode(order.id(), "order id");
        String customerId =
                normalizeCode(order.customerId(), "customer id");

        List<RawLine> rawLines =
                Objects.requireNonNull(order.lines(), "lines");

        List<BillLine> billLines = rawLines.stream()
                .map(line -> {
                    Objects.requireNonNull(line, "line");
                    String sku = normalizeCode(line.sku(), "sku");

                    if (line.quantity() <= 0) {
                        throw new IllegalArgumentException(
                                "quantity must be positive");
                    }
                    if (line.unitPriceCents() < 0L) {
                        throw new IllegalArgumentException(
                                "unit price must be nonnegative");
                    }

                    long amount = Math.multiplyExact(
                            (long) line.quantity(),
                            line.unitPriceCents());

                    return new BillLine(
                            sku, line.quantity(), amount);
                })
                .toList();

        long orderTotal = billLines.stream()
                .mapToLong(BillLine::amountCents)
                .reduce(0L, Math::addExact);

        return new Receipt(
                orderId,
                customerId,
                List.copyOf(billLines),
                orderTotal);
    }

    static List<Receipt> process(List<RawOrder> source) {
        Objects.requireNonNull(source, "source");

        return source.stream()
                .map(order -> Objects.requireNonNull(
                        order, "order"))
                .filter(order -> {
                    if (order.status() == null) {
                        throw new IllegalArgumentException(
                                "status is null");
                    }
                    return order.status() == Status.PAID;
                })
                .map(OrderPipelineDemo::toReceipt)
                .toList();
    }

    static Map<String, Long> totalsByCustomer(
            List<Receipt> receipts) {
        return receipts.stream()
                .collect(Collectors.toMap(
                        Receipt::customerId,
                        Receipt::amountCents,
                        Math::addExact,
                        TreeMap::new));
    }

    static long grandTotal(List<Receipt> receipts) {
        return receipts.stream()
                .mapToLong(Receipt::amountCents)
                .reduce(0L, Math::addExact);
    }

    public static void main(String[] args) {
        List<RawOrder> orders = List.of(
                new RawOrder(
                        " so-01 ", " kh01 ", Status.PAID,
                        List.of(
                                new RawLine(" cf-01 ", 2, 12_500),
                                new RawLine(" te-02 ", 1, 15_000)
                        )),
                new RawOrder(
                        "SO-02", "kh02", Status.PENDING,
                        List.of(new RawLine("not-used", 0, -50))),
                new RawOrder(
                        " so-03 ", "kh01", Status.PAID,
                        List.of(
                                new RawLine("cf-01", 1, 12_500),
                                new RawLine(" bánh ", 3, 7_000)
                        )),
                new RawOrder(
                        "SO-04", "kh03", Status.CANCELLED,
                        List.of())
        );

        List<Receipt> receipts = process(orders);

        System.out.println("Paid receipts: " + receipts.size());
        receipts.forEach(receipt ->
                System.out.println(
                        receipt.orderId() + " | "
                        + receipt.customerId() + " | "
                        + receipt.amountCents()));

        System.out.println(
                "Customer totals: " + totalsByCustomer(receipts));
        System.out.println(
                "Grand total: " + grandTotal(receipts));
    }
}
~~~

Compile/run with **JDK 17 or later**:

~~~bash
javac -encoding UTF-8 OrderPipelineDemo.java
java OrderPipelineDemo
~~~

Stdout:

~~~text
Paid receipts: 2
SO-01 | KH01 | 40000
SO-03 | KH01 | 33500
Customer totals: {KH01=73500}
Grand total: 73500
~~~

### 5.1. Tracing step by step

**Step 1 — source:** there are four RawOrders. Two are PAID, one is PENDING, and one is CANCELLED.

**Step 2 — structure check:** **map(Objects::requireNonNull)** catches a null RawOrder element if present. Because the sample data uses **List.of** and contains no nulls, this step passes normally.

**Step 3 — status filter:** only PAID orders reach **toReceipt**. The PENDING order has a line with quantity=0 and unitPriceCents=-50, yet it is not processed in this revenue calculation. This rule is defined in section 3; it is not a recommendation to skip data quality checks across the whole system.

**Step 4 — normalization:** " so-01 " becomes **SO-01**, " kh01 " becomes **KH01**, " cf-01 " becomes **CF-01**, and " bánh " becomes **BÁNH**. All codes in Receipt are now in canonical form.

**Step 5 — line calculation:** order SO-01 has 2 × 12,500 = **25,000**, plus 1 × 15,000 = **15,000**; order total is **40,000**.

**Step 6 — second order calculation:** SO-03 has 1 × 12,500 = **12,500** and 3 × 7,000 = **21,000**; total is **33,500**.

**Step 7 — group by customer:** both Receipts have customerId "KH01", so **Collectors.toMap** uses merge function **Math::addExact** to sum 40,000 + 33,500 = **73,500**.

**Step 8 — grand total:** **mapToLong(Receipt::amountCents).reduce(0L, Math::addExact)** produces 73,500.

**Step 9 — deterministic display order:** **TreeMap::new** fixes customer key order when printing the Map. With only one customer in the sample, no difference is visible, yet choosing TreeMap keeps reports stable when there are multiple customers.

### 5.2. Why does List.copyOf not make output data deeply immutable?

**List.copyOf(billLines)** creates a structurally unmodifiable list. The **BillLine** instances in the example are records containing String, int, and long, so this modeling is fairly safe for the practice exercise.

However, the general rule remains: **List.copyOf does not deep-copy mutable objects**. If BillLine had a field referencing a mutable List or object, you would have to check ownership and deeper mutability.

**Stream.toList()** in Java 17 also produces an unmodifiable list. Using `copyOf` in the example clarifies Receipt's return contract; in production you can optimize away an unnecessary copy after verifying ownership requirements.

## 6. Distinguishing filtering before vs after normalization

This is an important business decision:

~~~java
source.stream()
        .filter(order -> order.status() == Status.PAID)
        .map(OrderPipelineDemo::toReceipt);
~~~

This is an illustrative snippet; it assumes `source` contains non-null RawOrders and `OrderPipelineDemo` is declared. In this problem, only PAID orders are priced.

If the order is reversed:

~~~java
source.stream()
        .map(OrderPipelineDemo::toReceipt)
        .filter(receipt -> ...);
~~~

This is an **intentionally incomplete snippet and should not be copied as-is**, because Receipt in the example model **no longer has status** to filter on later. More importantly, running `toReceipt` first can throw exceptions on PENDING/CANCELLED order data, changing reporting behavior.

**Why not put status on Receipt?** Receipt is already the model of a **selected and priced PAID order**, so it does not need to carry status unless another business scenario requires it. Separating RawOrder/Receipt avoids "filtering later after losing the filter field".

On the other hand, if the requirement is to **validate every input order** before generating the report, build a separate validation step for the entire RawOrder list. Do not accidentally change policy merely by reordering Stream stages.

### 6.1. Do not use peek to normalize or update

Anti-pattern:

~~~java
orders.stream()
        .peek(order -> order.setStatus(Status.PAID))
        .filter(order -> order.getStatus() == Status.PAID)
        .toList();
~~~

This is an **illustrative anti-pattern** assuming a mutable Order class with setter/getter; it does not apply to the RawOrder record in the main example. **peek** is mainly for observation/debugging, not for mandatory business state updates. Under Stream optimizations, side effects in intermediate operations are not something to rely on to guarantee results.

Instead, use **filter** to select, **map** to create new normalized data, and **collect/toList** to obtain results. If database state must be updated, use an explicit workflow with transactions, error handling, and appropriate idempotency.

## 7. Distinguishing map, flatMap, mapToLong, and collect

An order has multiple line items, so the pipeline has **two data levels**:

~~~text
Stream<RawOrder>
    -> map(toReceipt)
    -> Stream<Receipt>
    -> toList()
    -> List<Receipt>

RawOrder.lines(): List<RawLine>
    -> stream().map(toBillLine)
    -> Stream<BillLine>
    -> toList()
    -> List<BillLine>
~~~

Here **map** fits because each PAID RawOrder produces one Receipt; each valid RawLine produces one BillLine.

If you need statistics across **all line items** of multiple Receipts, there is a one-to-many relationship and **flatMap** can be used:

~~~java
long lineCount = receipts.stream()
        .flatMap(receipt -> receipt.lines().stream())
        .count();
~~~

This is an illustrative snippet assuming `receipts` is `List<Receipt>`. **flatMap** flattens the line lists into a single `Stream<BillLine>`. With the sample data, there are 2 lines in SO-01 and 2 lines in SO-03, so **lineCount = 4**.

To sum amounts, you can flatten directly per line:

~~~java
long byLines = receipts.stream()
        .flatMap(r -> r.lines().stream())
        .mapToLong(BillLine::amountCents)
        .reduce(0L, Math::addExact);
~~~

The result **73,500** equals the sum of Receipts if the invariant **Receipt.amountCents == sum(Receipt.lines.amountCents)** holds.

**Why use mapToLong instead of map?** **mapToLong(BillLine::amountCents)** creates a **LongStream**, avoiding boxing into Long for primitive processing. **reduce(0L, Math::addExact)** uses overflow-checked addition, unlike **LongStream.sum()** which does not throw on `long` overflow.

### 7.1. Identity 0L in reduce

For `long` addition:

~~~java
long total = amounts.reduce(0L, Math::addExact);
~~~

This is an illustrative snippet assuming `amounts` is an unconsumed `LongStream`. **0L** is the addition identity: adding 0 does not change the value. When the stream is empty, reduce returns **0L**, matching the empty-set sum rule in this exercise.

**Note:** `Math.addExact(long,long)` throws **ArithmeticException** if addition overflows `long`. Some large values whose mathematical sum fits in `long` could overflow in a particular intermediate grouping; if the problem requires the sum to always succeed under any grouping even when intermediates exceed bounds, use a wider numeric type such as `BigInteger` or `BigDecimal`.

## 8. Safe money calculation: avoid multiplication/addition with silent overflow

### 8.1. Why Math.multiplyExact?

Anti-pattern:

~~~java
long lineTotal = quantity * unitPriceCents;
~~~

Illustrative snippet. If `quantity × unitPriceCents` exceeds `long` range, ordinary multiplication **does not throw ArithmeticException**, instead wrapping per Java integer rules. The total could become negative or a wrong positive number.

Checked version:

~~~java
long lineTotal = Math.multiplyExact(
        (long) quantity, unitPriceCents);
~~~

If multiplication overflows `long`, **Math.multiplyExact** throws ArithmeticException. Casting **(long) quantity** selects the **long,long** overload, avoiding multiplying two ints first before widening to long when both operands are ints.

### 8.2. Why Math.addExact?

Anti-pattern:

~~~java
long grandTotal = receipts.stream()
        .mapToLong(Receipt::amountCents)
        .sum();
~~~

Illustrative snippet. **LongStream.sum()** sums longs but is not an overflow-checking API. To detect overflow:

~~~java
long grandTotal = receipts.stream()
        .mapToLong(Receipt::amountCents)
        .reduce(0L, Math::addExact);
~~~

This uses checked addition. If an arithmetic error occurs, the pipeline fails instead of outputting a wrong revenue report.

### 8.3. When is long still not enough?

If unit prices, quantities, or aggregations exceed **long** range, choose another model. For money with fractional parts and rounding policies, **BigDecimal** is usually appropriate; for very large integer units, consider **BigInteger**. Do not switch to **double** just to avoid overflow, because double has representation error and does not represent all large integers exactly.

## 9. Java 17 program: testing invalid data and overflow

Create the file **OrderValidationDemo.java**:

~~~java
import java.util.List;
import java.util.Objects;

record Line(int quantity, long unitPriceCents) {}

public class OrderValidationDemo {
    static long total(List<Line> lines) {
        Objects.requireNonNull(lines, "lines");

        return lines.stream()
                .mapToLong(line -> {
                    Objects.requireNonNull(line, "line");

                    if (line.quantity() <= 0) {
                        throw new IllegalArgumentException(
                                "quantity must be positive");
                    }
                    if (line.unitPriceCents() < 0L) {
                        throw new IllegalArgumentException(
                                "unit price must be nonnegative");
                    }
                    return Math.multiplyExact(
                            (long) line.quantity(),
                            line.unitPriceCents());
                })
                .reduce(0L, Math::addExact);
    }

    public static void main(String[] args) {
        long valid = total(List.of(
                new Line(2, 1_200),
                new Line(1, 700)));

        System.out.println("Valid total: " + valid);
        System.out.println("Empty total: " + total(List.of()));

        try {
            total(List.of(new Line(0, 1_000)));
        } catch (IllegalArgumentException failure) {
            System.out.println("Invalid: " + failure.getMessage());
        }

        try {
            total(List.of(new Line(2, Long.MAX_VALUE)));
        } catch (ArithmeticException failure) {
            System.out.println(
                    "Overflow: " + failure.getClass().getSimpleName());
        }
    }
}
~~~

Run:

~~~bash
javac OrderValidationDemo.java
java OrderValidationDemo
~~~

Stdout:

~~~text
Valid total: 3100
Empty total: 0
Invalid: quantity must be positive
Overflow: ArithmeticException
~~~

Analysis:

1. **2 × 1,200 + 1 × 700 = 3,100**.
2. An empty list is reduced with identity 0L, so total = 0. This is the **sum rule**, not a claim that an order with no lines is business-valid.
3. Quantity=0 is blocked before multiplication, throwing IllegalArgumentException with an exact message.
4. **2 × Long.MAX_VALUE** exceeds `long` range; Math.multiplyExact throws ArithmeticException. The program catches the error and prints the exception type instead of recording a wrong negative total.
5. Negative unit price is checked before multiplication. If negative unit prices represent business discounts/refunds, do not mix them into the same regular Line model without explicit rules.

**Key point:** the example uses **catch** in main to demonstrate the failure branches. The `total` method **does not swallow errors**; the caller learns of invalid input or overflow via exceptions.

## 10. Aggregating by customer: why use toMap with a merge function?

A customer can have multiple Receipts. If you only use:

~~~java
Collectors.toMap(
        Receipt::customerId,
        Receipt::amountCents)
~~~

then with two Receipts sharing a customerId, the collector **encounters duplicate keys** and throws IllegalStateException per its default contract. That is not the right way to compute customer revenue totals.

You must specify a **merge function**:

~~~java
Collectors.toMap(
        Receipt::customerId,
        Receipt::amountCents,
        Math::addExact,
        TreeMap::new)
~~~

This is an illustrative collector expression, requiring imports for `Collectors` and `TreeMap`. When two Receipts share a key, **Math.addExact** sums the two `amountCents` with overflow checking.

Roles:

| Component | Function |
| --- | --- |
| **Receipt::customerId** | Determines the customer grouping key |
| **Receipt::amountCents** | Selects the value to sum |
| **Math::addExact** | Handles duplicate keys with overflow-checked addition |
| **TreeMap::new** | Chooses a Map with deterministic key order |

**Do not use merge function `(old, next) -> next`** if the goal is total revenue: that keeps only the last value on duplicate keys, losing the amounts from earlier orders.

### 10.1. groupingBy is also an option

Alternative:

~~~java
Map<String, Long> totals = receipts.stream()
        .collect(Collectors.groupingBy(
                Receipt::customerId,
                TreeMap::new,
                Collectors.summingLong(Receipt::amountCents)));
~~~

Illustrative snippet assuming `receipts` exists and `Map`, `TreeMap`, `Collectors` are imported.

For small data, both **toMap + merge** and **groupingBy + summingLong** can produce the same total. However, **Collectors.summingLong** has no overflow-checking contract. This exercise prefers **Math::addExact** to protect arithmetic correctness within the `long` range.

If multiple statistics per customer are needed—such as count, min, max, average—use an appropriate downstream collector or a richer result type. There is no need to create an external map and mutate it inside `forEach` when collectors already express grouping cleanly.

### 10.2. Case of no Receipts

If the post-filter list is empty:

- **totalsByCustomer** returns an **empty Map**.
- **grandTotal** returns **0L** per reduce's identity.
- **Paid receipts** equals **0**.

Do not invent a customer named `UNKNOWN` to hold a 0 total unless business rules require it. On the other hand, an accounting report may need to show all customers including those with no purchases, in which case you must merge in the customer list from another business source.

## 11. Sorting the total report by revenue and handling ties

After building the customer totals Map, you sometimes need to rank by **descending revenue**, breaking ties by customer ID for a deterministic order.

Create the file **OrderRankingDemo.java**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

record Sale(String customer, long amountCents) {}
record CustomerTotal(String customer, long amountCents) {}

public class OrderRankingDemo {
    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("KH02", 10_000),
                new Sale("KH01", 25_000),
                new Sale("KH02", 30_000),
                new Sale("KH03", 40_000)
        );

        Map<String, Long> totals = sales.stream()
                .collect(Collectors.toMap(
                        Sale::customer,
                        Sale::amountCents,
                        Math::addExact,
                        TreeMap::new));

        List<CustomerTotal> ranking = totals.entrySet().stream()
                .map(entry -> new CustomerTotal(
                        entry.getKey(), entry.getValue()))
                .sorted(Comparator
                        .comparingLong(CustomerTotal::amountCents)
                        .reversed()
                        .thenComparing(CustomerTotal::customer))
                .toList();

        System.out.println("Totals: " + totals);
        System.out.println("Ranking:");
        ranking.forEach(item -> System.out.println(
                item.customer() + ": " + item.amountCents()));
    }
}
~~~

Run:

~~~bash
javac OrderRankingDemo.java
java OrderRankingDemo
~~~

Stdout:

~~~text
Totals: {KH01=25000, KH02=40000, KH03=40000}
Ranking:
KH02: 40000
KH03: 40000
KH01: 25000
~~~

**Explanation:**

- KH02's two Sales sum to 10,000 + 30,000 = **40,000**.
- KH03 has **40,000**, KH01 has **25,000**.
- The Comparator sorts by descending revenue, then ascending customer ID on ties. Thus KH02 comes before KH03.
- `sorted` **does not drop duplicates**; each CustomerTotal corresponds to one unique aggregated key. If you used a TreeSet with a comparator based only on `amountCents`, KH02 and KH03 could be treated as equal and one customer would disappear — violating the report requirement.

**Difference between the two orderings:** TreeMap during aggregation gives **key order**; the Comparator in ranking gives **revenue order**. Pick the right one for the display goal.

## 12. Null data: detect, filter, or report an error?

A pipeline can encounter different kinds of null:

1. **Null source List<RawOrder>**.
2. **A null RawOrder element**.
3. **Null status**.
4. **Null order ID, customer ID, or SKU**.
5. **Null RawLine list on an order**.
6. **A null RawLine inside the list**.

In the main program:

| Situation | Policy |
| --- | --- |
| Null source List | `Objects.requireNonNull`, fails |
| Null RawOrder | `Objects.requireNonNull` in `map` before `filter`, fails |
| Null Status | `IllegalArgumentException` in `filter`, fails |
| Null or blank code on PAID order | `IllegalArgumentException` from `normalizeCode` |
| Null lines on PAID order | `NullPointerException` with message `"lines"` |
| Null RawLine on PAID order | `NullPointerException` with message `"line"` |
| Quantity <= 0 on PAID order | `IllegalArgumentException` |
| Unit price < 0 on PAID order | `IllegalArgumentException` |
| Arithmetic exceeding long | `ArithmeticException` |

The key is that **each kind of null needs a contract**. A filter like **filter(Objects::nonNull)** can drop a null RawOrder while silently losing a record from the report without anyone knowing. In this lesson, a null RawOrder is a source structure error, so it must fail fast.

**An alternative:** If data read from a legacy API contains null values explicitly defined as "no order", you can filter nulls right after the source. However, that choice must be documented, tested, and not applied mechanically to every source.

### 12.1. List.of and Arrays.asList

**List.of** rejects null elements; if you need to test null-detection policies in a Stream, build the list with **Arrays.asList(...)** or an `ArrayList`. Do not pass a List containing null into `List.of` and think you tested the pipeline: the program will throw NPE when constructing `List.of`.

### 12.2. Stream.toList and output data

Java 17's **Stream.toList()** returns a structurally unmodifiable List; **List.of()** is also an unmodifiable collection, yet it forbids null elements. Do not lump all factory/terminal operations together under one meaning. In this program, Receipt and BillLine are validated against null, so the output has no reason to contain null.

## 13. Errors on PAID orders: stop everything or keep per-order results?

There are at least two reasonable business policies:

**Policy A — fail fast (main program):**

- Encountering an invalid PAID order → throw an exception, do not publish a successful revenue report.
- Advantage: never silently publishes an incomplete revenue total.
- Limitation: requires error handling at the caller level; does not list all bad orders in one pass if it stops at the first error.

**Policy B — collect per-order results:**

- Process each order into **Success(receipt)** or **Failure(orderId, reason)**.
- Report failed orders separately; revenue from successful orders is only published with a **partial/incomplete** status flag if the problem allows it.
- Advantage: helps batch data ingestion, diagnosing and fixing multiple records at once.
- Limitation: requires a richer result type and discipline never to mislabel a partial total as a complete total.

Do not write:

~~~java
try {
    return calculate(order);
} catch (RuntimeException ignored) {
    return 0L;
}
~~~

This is an **illustrative anti-pattern**, assumed inside a method returning `long` with `calculate` defined. It can turn a broken order into 0 revenue; report readers will have no idea an order was excluded due to bad data.

If implementing Policy B, a model like **sealed interface OrderOutcome permits Success, Failure** or a record holding receipt/error with clear invariants is usually better than throwing and swallowing exceptions. You can include stable error codes, record positions, and severity levels to aid data remediation.

### 13.1. Distinguishing business errors from system errors

- **Quantity <= 0** or blank SKU may be input validation errors.
- **ArithmeticException** indicates a number exceeded the `long` range of the design.
- **Database/network errors** (if any) are operational failures, not "order does not exist".
- **Cancelled/refunded** are business statuses, not errors throwing exceptions just because they are excluded from the selected PAID set.

The processing layer should preserve the actual cause rather than collapsing every exception into a string like "No orders".

## 14. Testing the happy path and error paths

A good pipeline must **be testable via small functions** rather than just running `main` and eyeing stdout.

### 14.1. Core test table

| Case | Input | Expected result |
| --- | --- | --- |
| Normalize code | `" so-01 "` | `"SO-01"` |
| Normalize blank | `"   "` | `IllegalArgumentException` |
| Normalize null | `null` | `IllegalArgumentException` |
| Valid PAID order | 2 × 12,500; 1 × 15,000 | 40,000 |
| PAID order with quantity=0 | Quantity 0 | `IllegalArgumentException` |
| PAID order with negative price | Unit price -1 | `IllegalArgumentException` |
| Multiplication exceeding long | 2 × Long.MAX_VALUE | `ArithmeticException` |
| Sum exceeding long | Long.MAX_VALUE + 1 | `ArithmeticException` |
| PENDING with broken line | Status PENDING | Excluded from report per Policy A |
| Valid CANCELLED | Status CANCELLED | Excluded from report |
| No PAID orders | Only PENDING/CANCELLED | Empty List, empty Map, total 0 |
| Two orders same customer | 40,000 + 33,500 | One key KH01, total 73,500 |
| Two customers same revenue | KH02 40,000, KH03 40,000 | Ranked by ascending customer on tie |
| Null RawOrder | One null source element | Fail fast |
| Null Status | An order with null status | Reports error |
| Null line on PAID | A null RawLine | Reports error |

**Do not test only the final amount.** A pipeline could produce the right total by filtering out one order by mistake and summing another by mistake. Check the **selected Receipt IDs, line counts, customer, source status, ordering**, and then check the totals.

### 14.2. Pure-function-style assertion example

You can test methods in `OrderPipelineDemo` from a separate test program:

~~~java
// Illustrative snippet for a test or main in the same package:
String code = OrderPipelineDemo.normalizeCode(" kh01 ", "customer");
if (!"KH01".equals(code)) {
    throw new AssertionError("normalize failed");
}

long total = OrderPipelineDemo.grandTotal(List.of(
        new Receipt("A", "KH01", List.of(), 100L),
        new Receipt("B", "KH01", List.of(), 50L)
));
if (total != 150L) {
    throw new AssertionError("sum failed");
}
~~~

This is an **illustrative test snippet**, not a standalone file. It requires the types declared in the main program and importing `List`. Note that the two test Receipts are constructed directly, so **empty lines with positive amountCents** do not reflect `toReceipt`'s output invariant. To test the full flow, construct `RawOrder`/`RawLine` and call **process** instead of creating Receipts that bypass validation.

### 14.3. Why not rely solely on Java assert?

Java's **assert** statement can be disabled in normal runs if the JVM does not have assertions enabled with **-ea**. For important tests, use **JUnit 5** or throw `AssertionError` directly when a condition fails as in the snippet above. Do not treat a normal run printing no errors as proof that tests ran if you only used `assert` and forgot `-ea`.

### 14.4. Useful property-based / invariant tests

Beyond concrete cases, test these invariants:

1. **Every Receipt appearing in the result** originates from a selected PAID order.
2. **Each Receipt.amountCents** equals the sum of `amountCents` of its BillLines.
3. **grandTotal(receipts)** equals the sum of values in the `totalsByCustomer` Map, given no overflow and the same Receipt set.
4. **Number of Receipts** equals the number of valid PAID RawOrders, unless the system has a duplicate-ID policy.
5. **Normalized codes** have no leading/trailing whitespace and follow the case rule.
6. **The result of process** does not depend on external mutable state, given the same valid source and no concurrent mutation.
7. **No lost amounts** when one customer has multiple orders: the merge function must add, not overwrite.
8. **No missed arithmetic errors**: `multiplyExact`/`addExact` must throw when exceeding `long` range.

Strong invariants help catch bugs that a small fixture cannot fully expose, especially when adding new customer groups or changing status logic.

## 15. Correctness before performance

In Streams, **filter/map** functions should be stateless and non-interfering:

~~~java
List<Receipt> receipts = orders.stream()
        .filter(order -> order.status() == Status.PAID)
        .map(OrderPipelineDemo::toReceipt)
        .toList();
~~~

This is an illustrative snippet on non-null data; the main program has additional guards. A few tips:

- **Do not update an external sum variable inside forEach/peek** as a substitute for reduce/collector. That creates shared mutable state prone to races if switched to parallel.
- **Do not use AtomicLong.increment/add** inside filter/map and treat it as a contract-compliant Stream aggregation. Atomics protect a single update operation; they do not guarantee side effects happen the expected number of times under optimizations or short-circuiting.
- **Do not treat peek log line counts as the number of processed orders**. Streams can be lazy and some terminal operations are optimized.
- **Produce structurally immutable results** when sharing across multiple processing layers; avoid mutating RawOrder/RawLine directly in the pipeline.
- **Do not blindly enable parallel()** just because the source has many elements. Splitting/merging overhead and exception rules in parallel pipelines must be evaluated on real workloads.

### 15.1. Ordering and report stability

On a List with encounter order, sequential **filter** and **map** preserve the order of remaining orders. **Stream.toList()** also preserves encounter order if the Stream is ordered. That is why SO-01 appears before SO-03 in stdout.

If only **total revenue** is needed, Receipt order does not affect mathematical addition (aside from intermediate overflow issues when using checked `long`). However, if the report needs **top customers**, or displays orders by date/ID, add **sorted(comparator)** with a clear order and tie-breaker.

**Do not rely on HashMap iteration order** for stdout tests. The example uses `TreeMap` to fix key order.

### 15.2. Multiple passes or a single pass?

The main program:

- Builds **List<Receipt>** once from the source.
- Iterates Receipts to compute the customer revenue Map.
- Iterates Receipts to compute grandTotal.

For small/medium data when detailed Receipts are also needed, this design is clear and easy to test. If the source is a huge I/O stream or single-pass only, consider a **combined downstream collector** or batch processing. Do not switch to an overly complex collector just to save one pass over a small List.

**Do not call multiple terminal operations on the same Stream instance.** After **toList, collect, reduce, count**, the Stream is consumed; to compute multiple things, create a new Stream from re-iterable data or collect into an intermediate result like `List<Receipt>`.

## 16. Extended scenarios: taxes, discounts, and cancellations/refunds

The sample program **does not compute taxes or discounts**. If the problem adds a 10% discount rate, you must determine:

1. Is the discount applied before or after tax?
2. Is rounding done per line, per order, or at the end of the report?
3. Currency unit and valid number of decimal places?
4. Can a discount be negative? What is the maximum value?
5. Should refunds be subtracted from same-period revenue or reported separately?
6. Can data contain multiple currencies? If so, **never directly add** `amountCents` of different currencies.

In real systems, you can use **BigDecimal** for percentage calculations and explicit rounding rules. With integer minor units, convert using checked operations and documented rounding, avoiding ad-hoc `double` math followed by casting to `long`.

### 16.1. Do not treat PAID as a universal accounting conclusion

A PAID order may be partially or fully refunded; a SHIPPED order may be recognized as revenue under other standards/conditions. The status filter in this lesson is an **assumption of the practice requirements**, not a universal accounting rule.

If multiple statuses share the same meaning or eligibility depends on time, put the rule into a named **Predicate/Policy** and test it independently, rather than scattering conditions across many places:

~~~java
Predicate<RawOrder> eligible = order ->
        order.status() == Status.PAID;
~~~

This illustrative snippet requires importing `Predicate` and assumes `order` is non-null; when adding new policies, update and test in one place.

## 17. Common mistakes in this practice exercise

| Mistake | Why wrong | Fix |
| --- | --- | --- |
| Calling normalize before filter without defining policy | Uncounted orders can still cause failures | Define validation scope clearly, then order stages |
| Not checking null status | May silently be treated as not PAID | Fail or apply a contract-defined rule |
| Using default-locale trim/uppercase | Behavior can vary across environments | Specify `Locale.ROOT` if codes are case-insensitive |
| Treating normalized code as verified identity | Business error | Verify existence/permissions at the right boundary |
| Computing qty × price with plain multiplication | Can overflow silently | `Math.multiplyExact` |
| Using `LongStream.sum` for reports needing overflow detection | `sum` does not throw on overflow | `reduce(0L, Math::addExact)` or another numeric type |
| Using `toMap` without merge when a customer has multiple orders | Duplicate-key exception | Appropriate merge function |
| Using merge `(a,b) -> b` | Loses revenue from earlier orders | Checked addition |
| Using `double` for exact money | Binary representation / rounding error | `long` minor units or `BigDecimal` |
| Testing only `grandTotal` | Wrong filtering can yield the same total by coincidence | Test IDs, statuses, lines, groups, and total |
| Returning 0 when catching all exceptions | Hides corrupt data and underreports | Fail fast or partial results with metadata |
| Using `filter(Objects::nonNull)` unintentionally | Drops bad records | Choose an explicit null policy |
| Mutating `RawOrder` inside `peek` | Unreliable side effect | Use `map` to create new records |
| Using a shared List/Map to collect in `parallelStream` | Race/order issues | Standard Collector or reduction |
| Confusing empty order with 0 total | Fails to distinguish no lines from zero-priced lines | Check counts/validation per requirements |
| Relying on HashMap order for report printing | Order is not guaranteed | TreeMap or `sorted` for stable output |
| Using TreeSet for top customers with revenue-only comparator | Two customers with equal totals can lose one | Use List and `sorted`, add a tie-breaker |
| Ignoring duplicate `orderId` | May double-count the same transaction | Design dedupe/idempotency before reporting |
| Mutating source while pipeline runs | Violates non-interference, prone to races | Snapshot or immutable data |
| Directly summing multiple currencies | Sum is meaningless | Group by currency or convert with rules |

## 18. Practice exercises by level

### Exercise 1: Rewrite the pipeline from requirements

From `List<RawOrder>`, use Streams to select PAID orders, normalize codes, compute each line, and return `List<Receipt>`. State clearly **which input errors must be blocked** at each stage.

### Exercise 2: Change data without changing code

Add a PAID order for customer **KH02**, with 3 items at unit price 9,000. Predict the new grandTotal: **73,500 + 27,000 = 100,500**, and the Map gains key KH02 with value 27,000.

### Exercise 3: Test overflow in addition

Create one Receipt with total `Long.MAX_VALUE` and one Receipt with total `1`. Call `grandTotal`. Prove **Math.addExact** throws `ArithmeticException` instead of returning a wrong number.

### Exercise 4: Null and blank

Try a PAID RawOrder with code `"  "`, null customer, or null lines list. What behavior should each case have? Why **cannot they be treated as unpaid orders** just to filter them out?

### Exercise 5: Time-window filter

Add a **paidAt** property to RawOrder and filter PAID orders within a date range. Define timezone, start/end bounds, and inclusive/exclusive rules. Do not compare timestamps as strings by guesswork.

### Exercise 6: Multiple customers with equal revenue

Using **OrderRankingDemo**, create two customers with equal revenue and test the customer tie-breaker. Explain why **List + sorted** is needed instead of a TreeSet with an amount-only comparator.

### Exercise 7: Aggregate by SKU

Use:

~~~java
receipts.stream()
        .flatMap(r -> r.lines().stream())
        .collect(Collectors.toMap(
                BillLine::sku,
                BillLine::amountCents,
                Math::addExact,
                TreeMap::new));
~~~

This is an illustrative snippet requiring `Collectors`/`TreeMap` imports and a `receipts` variable. Compute total revenue by SKU. Distinguish **total amount by SKU** from **total quantity by SKU**; to sum quantity, change the value mapper and merge function appropriately.

### Exercise 8: Choose a per-order error policy

Design a record/Sealed Result that records success and failure. Create three PAID orders, one missing an SKU. The report must list errors while marking **computed revenue as partial**, not publishing it as a complete revenue total.

### Exercise 9: Test stability

Run the pipeline twice on the same immutable data; compare the Receipt list and Map. Why should you not use an external counter to assign sequence numbers inside `map`? If sequence numbers are needed, derive them from source indices or use an explicit sorting step.

### Exercise 10: Upgrade to BigDecimal

Design a discount and rounding rule per line. Why should percentage calculations not use `double` and then cast to `long` without stating rules? Use `BigDecimal` and `RoundingMode` per contract.

## 19. Acceptance checklist for an order-processing pipeline

Before shipping to production, check:

1. **Source and schema**: are required fields, null rules, and currency units known precisely?
2. **Filter**: which statuses count toward revenue, and what is the policy for bad data on unselected orders?
3. **Normalization**: do strip/case/locale rules match real identifiers?
4. **Line items**: are quantity, unitPriceCents, and SKU validated?
5. **Arithmetic**: do multiplyExact/addExact cover the data range, or are BigInteger/BigDecimal needed?
6. **Receipt invariants**: does order total equal line sum, and are codes normalized?
7. **Grouping**: are duplicate keys summed instead of overwritten, and is Map order defined if needed?
8. **Empty set**: do 0 orders, 0 total, and empty Map match the contract?
9. **Errors**: is bad data never silently treated as 0 revenue; are messages and causes preserved?
10. **Duplicate orders**: are duplicate IDs and idempotency handled if the source can emit the same transaction multiple times?
11. **Purity**: do filter/map avoid shared mutable state or mandatory side effects?
12. **Tests**: are there tests for PAID/PENDING/CANCELLED, null, blank, overflow, multiple customers, and ranking?
13. **Performance**: was it measured before using parallel or complex collectors?
14. **Security/privacy**: do reports/logs show only necessary info, avoiding printing sensitive customer data to console?
15. **Reconciliation**: is there a mechanism to compare totals, line counts, and results against a trusted source when publishing reports?

## 20. Key takeaways

A reliable Stream workflow is not just chaining method references. It is **a sequence of contracts**:

**Select the right orders** with `filter`; **normalize identifiers** with pure functions; **validate required data** before using it; **compute money with bounds-checked arithmetic**; **group by customer with the right merge policy**; then **test both success and failure branches**.

In Java 17, the typical tools for this problem are **Stream.filter**, **map**, **flatMap**, **mapToLong**, **reduce**, **Collectors.toMap**, **TreeMap**, **Locale.ROOT**, **Math.multiplyExact**, and **Math.addExact**. Each tool handles only one part; correctness comes from using them according to the business contract.

Final self-check question: **"If an order is excluded, a code is modified, a line has an error, or an addition overflows, can I explain exactly which data is counted, which is not, and why?"** If yes, the pipeline is not only concise, but also maintainable, testable, and reconcilable.
